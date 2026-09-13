"""Local evidence API and immutable 24-hour calls over the same detector rules."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.error import URLError
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from analytics import reddit_store, store
from analytics.attention import attention, timestamp
from analytics.detector import detect, evaluate, VERSION, RULES
from analytics.predictions import evaluate_prediction
from api import prediction_store

app = FastAPI(title='Pulse API', version='0.2.0', description=
              'Local Hacker News attention investigation and browser-local 24-hour calls. '
              'Signals are heuristic, and resolutions use only observations available by the call deadline.')


def cutoff(as_of: Annotated[datetime | None, Query(description='Timezone-aware ISO cutoff; defaults to now in UTC')] = None):
    now = datetime.now(timezone.utc)
    if as_of is None:
        return now
    if as_of.tzinfo is None:
        raise HTTPException(422, 'as_of must include a timezone, for example Z or +00:00')
    if as_of > now:
        raise HTTPException(422, 'as_of cannot be in the future')
    return as_of.astimezone(timezone.utc)


Cutoff = Annotated[datetime, Depends(cutoff)]
StoryID = Annotated[int, Path(gt=0, le=9223372036854775807)]


class PredictionRequest(BaseModel):
    call: Literal['yes', 'no']


def local_user(x_pulse_local_user: Annotated[str | None, Header(alias='X-Pulse-Local-User')] = None):
    if not x_pulse_local_user:
        raise HTTPException(422, 'A local Pulse user ID is required to lock a call')
    try:
        return UUID(x_pulse_local_user)
    except ValueError as error:
        raise HTTPException(422, 'The local Pulse user ID is invalid') from error


LocalUser = Annotated[UUID, Depends(local_user)]


def read(end, minutes=22, story_id=None):
    try:
        return store.observations(end, minutes=minutes, story_id=story_id)
    except (OSError, URLError, ValueError) as error:
        # Do not return upstream errors that can contain SQL, addresses or credentials.
        raise HTTPException(503, 'Observation store is unavailable; try again shortly') from error


def read_reddit(end, minutes=120, post_id=None):
    try:
        return reddit_store.observations(end, minutes=minutes, post_id=post_id)
    except (OSError, URLError, ValueError) as error:
        raise HTTPException(503, 'Reddit observation store is unavailable; try again shortly') from error


@app.get('/health', summary='Database availability and recent collection freshness')
def health():
    end = datetime.now(timezone.utc)
    rows = read(end, minutes=5)
    latest = max((timestamp(row['observed_at']) for row in rows), default=None)
    age = (end-latest).total_seconds() if latest else None
    fresh = age is not None and age <= 180
    return JSONResponse(status_code=200 if fresh else 503, content={
        'status': 'ok' if fresh else 'stale_data', 'checked_at': end.isoformat(),
        'latest_observed_at': latest.isoformat() if latest else None,
        'age_seconds': age, 'scope': 'ClickHouse availability and collection freshness; not full pipeline health',
    })


@app.get('/v1/radar', summary='Ranked accelerating stories with coverage and supporting evidence')
def radar(end: Cutoff, limit: Annotated[int, Query(ge=1, le=100)] = 10):
    report = detect(read(end), end)
    report.pop('evaluated')  # Individual explanations are available via the story endpoint.
    report['candidates'] = report['candidates'][:limit]
    report['returned'] = len(report['candidates'])
    return report


@app.get('/v1/stories', summary='Discover recently sampled stories, including quiet ones')
def stories(end: Cutoff, limit: Annotated[int, Query(ge=1, le=100)] = 20,
            offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    latest = {}
    for row in read(end):
        story = int(row['story_id'])
        if story not in latest or timestamp(row['observed_at']) > timestamp(latest[story]['observed_at']):
            latest[story] = row
    ordered = sorted(latest.values(), key=lambda row: (-timestamp(row['observed_at']).timestamp(), int(row['story_id'])))
    return {'as_of': end.isoformat(), 'total': len(ordered), 'offset': offset, 'stories': [
        {'story_id': int(row['story_id']), 'title': row['title'], 'url': row.get('url'),
         'observed_at': row['observed_at'], 'score': int(row['score']), 'comments': int(row['comments']),
         'fresh': (end-timestamp(row['observed_at'])).total_seconds() <= 120}
        for row in ordered[offset:offset+limit]]}


@app.get('/v1/stories/{story_id}/history', summary='5/30/60-minute changes and original observations')
def history(story_id: StoryID, end: Cutoff, evidence: bool = True):
    rows = read(end, minutes=63, story_id=story_id)
    if not rows:
        raise HTTPException(404, 'No observations for this story in the requested 63-minute interval')
    report = attention(rows, end)
    if evidence:
        report['evidence'] = rows
    return report


@app.get('/v1/stories/{story_id}/explanation', summary='Explain why a story qualifies, is quiet, or is excluded')
def explanation(story_id: StoryID, end: Cutoff):
    rows = read(end, story_id=story_id)
    if not rows:
        raise HTTPException(404, 'No observations for this story in the requested 22-minute interval')
    return {'as_of': end.isoformat(), 'detector_version': VERSION, 'rules': RULES,
            'story': evaluate(rows, end)}


@app.get('/v1/reddit/posts', summary='Recently observed Reddit submissions by source-specific metrics')
def reddit_posts(end: Cutoff, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                 subreddit: str | None = Query(default=None, min_length=1, max_length=100)):
    latest = {}
    for row in read_reddit(end):
        if subreddit and row['subreddit'].casefold() != subreddit.casefold():
            continue
        post_id = row['post_id']
        if post_id not in latest or timestamp(row['observed_at']) > timestamp(latest[post_id]['observed_at']):
            latest[post_id] = row
    ordered = sorted(latest.values(), key=lambda row: (-timestamp(row['observed_at']).timestamp(), row['post_id']))
    return {'as_of': end.isoformat(), 'total': len(ordered), 'posts': [
        {'post_id': row['post_id'], 'subreddit': row['subreddit'], 'title': row['title'], 'url': row['url'],
         'observed_at': row['observed_at'], 'score': int(row['score']), 'comments': int(row['comments']),
         'upvote_ratio': float(row['upvote_ratio']),
         'fresh': (end-timestamp(row['observed_at'])).total_seconds() <= 180}
        for row in ordered[:limit]]}


@app.get('/v1/reddit/posts/{post_id}/history', summary='Reddit post-level observations; not yet part of the HN detector')
def reddit_history(post_id: Annotated[str, Path(min_length=1, max_length=100)], end: Cutoff):
    rows = read_reddit(end, minutes=120, post_id=post_id)
    if not rows:
        raise HTTPException(404, 'No Reddit observations for this post in the requested two-hour interval')
    return {'as_of': end.isoformat(), 'post_id': post_id, 'source': 'reddit', 'evidence': rows,
            'note': 'Reddit metrics are collected separately while cross-source topic matching is developed.'}


def prediction_error(error):
    if isinstance(error, prediction_store.StoreUnavailable):
        raise HTTPException(503, 'Prediction store is unavailable; try again shortly') from error
    raise error


@app.post('/v1/stories/{story_id}/predictions', status_code=201,
          summary='Lock a local 24-hour top-ten Pulse signal call')
def lock_prediction(story_id: StoryID, request: PredictionRequest, user: LocalUser):
    created_at = datetime.now(timezone.utc)
    rows = read(created_at, minutes=63, story_id=story_id)
    if not rows:
        raise HTTPException(404, 'This story is no longer in the recent observation window')
    latest = max(rows, key=lambda row: timestamp(row['observed_at']))
    try:
        prediction = prediction_store.create(user, story_id, latest['title'], request.call,
                                             created_at, created_at + timedelta(hours=24))
    except Exception as error:
        prediction_error(error)
    if prediction is None:
        raise HTTPException(409, 'You already locked a call for this story on this browser')
    return {'prediction': prediction,
            'rule': 'Correct when this story is ranked in the top 10 HN detector candidates at any five-minute check in the next 24 hours.'}


@app.get('/v1/predictions', summary='Local browser calls and their latest resolution state')
def predictions(user: LocalUser):
    try:
        return {'predictions': prediction_store.list_for_owner(user)}
    except Exception as error:
        prediction_error(error)


@app.post('/v1/predictions/resolve', summary='Resolve expired calls from stored HN observations')
def resolve_predictions(user: LocalUser):
    now = datetime.now(timezone.utc)
    try:
        due = prediction_store.due_for_owner(user, now)
    except Exception as error:
        prediction_error(error)
    resolved = []
    for prediction in due:
        rows = read(timestamp(prediction['expires_at']), minutes=24 * 60 + 27)
        resolution = evaluate_prediction(rows, prediction['story_id'], prediction['created_at'], prediction['expires_at'])
        resolution['call'] = prediction['call']
        try:
            result = prediction_store.resolve(prediction['id'], user, resolution, now)
        except Exception as error:
            prediction_error(error)
        if result:
            resolved.append(result)
    return {'resolved': resolved, 'checked_at': now.isoformat()}
