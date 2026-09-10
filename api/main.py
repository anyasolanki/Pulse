"""Read-only investigation API over the same evidence and rules as the CLI."""
from datetime import datetime, timezone
from typing import Annotated
from urllib.error import URLError

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from analytics import reddit_store, store
from analytics.attention import attention, timestamp
from analytics.detector import detect, evaluate, VERSION, RULES

app = FastAPI(title='Pulse API', version='0.1.0', description=
              'Local Hacker News attention investigation. Signals are heuristic, not predictions. '
              'Historical cutoffs use observation time and can incorporate late-arriving evidence.')


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
