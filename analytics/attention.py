"""Explainable snapshot deltas, with explicit freshness and sampling limits."""
from datetime import datetime, timedelta, timezone


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def attention(observations, as_of, horizons=(5, 30, 60), tolerance_seconds=180):
    as_of = timestamp(as_of)
    # A replay of the same immutable event cannot increase activity.
    unique = {row['event_id']: dict(row, score=int(row['score']), comments=int(row['comments']))
              for row in observations if timestamp(row['observed_at']) <= as_of}
    rows = sorted(unique.values(), key=lambda row: (timestamp(row['observed_at']), row['event_id']))
    if len({row['story_id'] for row in rows}) > 1:
        raise ValueError('attention() accepts one story at a time')
    result = {'as_of': as_of.isoformat(), 'observation_count': len(rows), 'windows': []}
    if not rows:
        result['status'] = 'no_data'
        return result
    latest = rows[-1]
    latest_time = timestamp(latest['observed_at'])
    fresh = (as_of - latest_time).total_seconds() <= tolerance_seconds
    result.update(story_id=latest['story_id'], title=latest['title'], latest=latest,
                  status='fresh' if fresh else 'stale')
    for minutes in horizons:
        target = as_of - timedelta(minutes=minutes)
        candidates = [row for row in rows if timestamp(row['observed_at']) <= target]
        baseline = candidates[-1] if candidates else None
        window = {'minutes': minutes, 'status': 'insufficient_history', 'score_change': None,
                  'comment_change': None, 'score_per_minute': None, 'comments_per_minute': None,
                  'baseline': baseline, 'latest': latest}
        if not fresh:
            window['status'] = 'stale'
        elif baseline and (target - timestamp(baseline['observed_at'])).total_seconds() <= tolerance_seconds:
            start = timestamp(baseline['observed_at'])
            span = (latest_time - start).total_seconds() / 60
            interval = [row for row in rows if timestamp(row['observed_at']) >= start]
            gaps = [(timestamp(b['observed_at']) - timestamp(a['observed_at'])).total_seconds()
                    for a, b in zip(interval, interval[1:])]
            max_gap = max(gaps, default=0)
            score_delta = latest['score'] - baseline['score']
            comments_delta = latest['comments'] - baseline['comments']
            window.update(status='complete' if max_gap <= tolerance_seconds else 'sampling_gap',
                          elapsed_minutes=round(span, 3), max_gap_seconds=max_gap,
                          score_change=score_delta, comment_change=comments_delta,
                          score_per_minute=round(score_delta / span, 4),
                          comments_per_minute=round(comments_delta / span, 4))
        result['windows'].append(window)
    return result
