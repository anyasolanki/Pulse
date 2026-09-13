"""Resolve a Pulse call from historical detector snapshots without future look-ahead."""
from datetime import timedelta

from analytics.attention import timestamp
from analytics.detector import detect


def evaluate_prediction(observations, story_id, created_at, expires_at, step_minutes=5):
    """Return a deterministic resolution for a top-ten call made before ``expires_at``.

    A check is usable only when the HN collection has an observation within three
    minutes of its cutoff. This prevents a missing collector interval becoming a
    false "no" result.
    """
    created, expires = timestamp(created_at), timestamp(expires_at)
    if expires <= created:
        raise ValueError('expires_at must be after created_at')
    rows = [row for row in observations if created - timedelta(minutes=25) <= timestamp(row['observed_at']) <= expires]
    cutoff = created + timedelta(minutes=step_minutes)
    checks, covered, first_qualified = 0, 0, None
    while cutoff <= expires:
        checks += 1
        if any(0 <= (cutoff - timestamp(row['observed_at'])).total_seconds() <= 180 for row in rows):
            covered += 1
            candidate = next((row for row in detect(rows, cutoff)['candidates']
                              if int(row['story_id']) == int(story_id) and row['rank'] <= 10), None)
            if candidate and first_qualified is None:
                first_qualified = cutoff
        cutoff += timedelta(minutes=step_minutes)
    coverage = covered / checks if checks else 0
    if coverage < 0.9:
        return {'status': 'unverifiable', 'reason': 'insufficient_collection',
                'checks': checks, 'covered_checks': covered, 'coverage': coverage}
    return {'status': 'resolved', 'outcome': first_qualified is not None,
            'first_qualified_at': first_qualified.isoformat() if first_qualified else None,
            'checks': checks, 'covered_checks': covered, 'coverage': coverage,
            'reason': 'top_ten_signal_seen' if first_qualified else 'no_top_ten_signal_seen'}
