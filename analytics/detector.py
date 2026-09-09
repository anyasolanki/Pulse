"""A versioned heuristic for accelerating HN stories, not a viral predictor."""
from collections import Counter, defaultdict
from datetime import timedelta
from analytics.attention import timestamp

VERSION = 'hn-acceleration-v1'
RULES = {
    'recent_minutes': 5,
    'baseline_minutes': 15,
    'boundary_tolerance_seconds': 120,
    'max_gap_seconds': 180,
    'min_recent_samples': 3,
    'min_baseline_samples': 8,
    'minimum_rate_multiple': 2.0,
    'channels': {
        'comments': {'min_recent_change': 5, 'min_excess_change': 3, 'baseline_rate_floor': 0.2},
        'score': {'min_recent_change': 10, 'min_excess_change': 5, 'baseline_rate_floor': 0.5},
    },
}


def evaluate(observations, as_of):
    """Evaluate one story. Future samples and duplicate event IDs are excluded."""
    end = timestamp(as_of)
    earliest = end - timedelta(minutes=22)
    by_id = {}
    for row in observations:
        if earliest <= timestamp(row['observed_at']) <= end:
            by_id[row['event_id']] = dict(row, story_id=int(row['story_id']),
                                         score=int(row['score']), comments=int(row['comments']))
    rows = sorted(by_id.values(), key=lambda row: (timestamp(row['observed_at']), row['event_id']))
    if len({row['story_id'] for row in rows}) > 1:
        raise ValueError('evaluate() accepts one story at a time')
    result = {'status': 'excluded', 'reason': 'no_data', 'priority': None, 'channels': {}}
    if not rows:
        return result
    latest = rows[-1]
    result.update(story_id=latest['story_id'], title=latest['title'], url=latest.get('url'),
                  evidence_url=f"https://news.ycombinator.com/item?id={latest['story_id']}",
                  observations=len(rows), latest_observed_at=latest['observed_at'])
    def exclude(reason):
        result['reason'] = reason
        return result
    if (end - timestamp(latest['observed_at'])).total_seconds() > RULES['boundary_tolerance_seconds']:
        return exclude('stale')
    pivot_target = end - timedelta(minutes=RULES['recent_minutes'])
    start_target = pivot_target - timedelta(minutes=RULES['baseline_minutes'])
    pivots = [row for row in rows if timestamp(row['observed_at']) <= pivot_target]
    starts = [row for row in rows if timestamp(row['observed_at']) <= start_target]
    if not pivots or not starts:
        return exclude('insufficient_history')
    pivot, start = pivots[-1], starts[-1]
    result['evidence'] = {'baseline_start': start, 'recent_start': pivot, 'latest': latest}
    for row, target in ((start, start_target), (pivot, pivot_target)):
        if (target - timestamp(row['observed_at'])).total_seconds() > RULES['boundary_tolerance_seconds']:
            return exclude('missing_boundary')
    start_time, pivot_time, latest_time = (timestamp(row['observed_at']) for row in (start, pivot, latest))
    baseline = [row for row in rows if start_time <= timestamp(row['observed_at']) <= pivot_time]
    recent = [row for row in rows if pivot_time <= timestamp(row['observed_at']) <= latest_time]
    interval = [row for row in rows if start_time <= timestamp(row['observed_at']) <= latest_time]
    gaps = [(timestamp(b['observed_at']) - timestamp(a['observed_at'])).total_seconds()
            for a, b in zip(interval, interval[1:])]
    baseline_minutes = (pivot_time - start_time).total_seconds() / 60
    recent_minutes = (latest_time - pivot_time).total_seconds() / 60
    result['sampling'] = {'baseline_minutes': baseline_minutes, 'recent_minutes': recent_minutes,
                          'baseline_samples': len(baseline), 'recent_samples': len(recent),
                          'max_gap_seconds': max(gaps, default=0)}
    if max(gaps, default=0) > RULES['max_gap_seconds']:
        return exclude('sampling_gap')
    if len(baseline) < RULES['min_baseline_samples'] or len(recent) < RULES['min_recent_samples']:
        return exclude('sparse_samples')
    priorities = []
    for name, rule in RULES['channels'].items():
        baseline_change = pivot[name] - start[name]
        recent_change = latest[name] - pivot[name]
        baseline_rate = baseline_change / baseline_minutes
        recent_rate = recent_change / recent_minutes
        # Any observed decrease makes this channel unsuitable for an acceleration
        # claim in v1. Another independently eligible channel may still qualify.
        decreasing = any(b[name] < a[name] for a, b in zip(interval, interval[1:]))
        denominator = max(baseline_rate, rule['baseline_rate_floor'])
        multiple = recent_rate / denominator
        excess = recent_change - max(0, baseline_rate) * recent_minutes
        reasons = []
        if decreasing:
            reasons.append('counter_decreased')
        if recent_change < rule['min_recent_change']:
            reasons.append('low_volume')
        if multiple < RULES['minimum_rate_multiple']:
            reasons.append('not_accelerating')
        if excess < rule['min_excess_change']:
            reasons.append('low_excess')
        qualifies = not reasons
        result['channels'][name] = {
            'qualifies': qualifies, 'reasons': reasons,
            'baseline_change': baseline_change, 'recent_change': recent_change,
            'baseline_rate_per_minute': baseline_rate, 'recent_rate_per_minute': recent_rate,
            'rate_multiple': multiple, 'rate_floor_applied': baseline_rate < rule['baseline_rate_floor'],
            'expected_recent_change': max(0, baseline_rate) * recent_minutes,
            'excess_change': excess,
        }
        if qualifies:
            priorities.append(excess / rule['min_recent_change'])
    result['status'] = 'candidate' if priorities else 'quiet'
    result['reason'] = 'accelerating' if priorities else 'below_thresholds'
    # Transparent ordering aid, deliberately not a probability or Pulse Score.
    result['priority'] = max(priorities) if priorities else None
    return result


def detect(observations, as_of):
    groups = defaultdict(list)
    end = timestamp(as_of)
    for row in observations:
        if end - timedelta(minutes=22) <= timestamp(row['observed_at']) <= end:
            groups[int(row['story_id'])].append(row)
    evaluated = [evaluate(groups[story], as_of) for story in sorted(groups)]
    candidates = sorted((row for row in evaluated if row['status'] == 'candidate'),
                        key=lambda row: (-row['priority'], row['story_id']))
    for rank, row in enumerate(candidates, 1):
        row['rank'] = rank
    return {
        'detector_version': VERSION, 'as_of': timestamp(as_of).isoformat(), 'rules': RULES,
        'summary': {'stories_evaluated': len(evaluated), 'candidates': len(candidates),
                    'eligible': sum(row['status'] != 'excluded' for row in evaluated),
                    'exclusions': dict(Counter(row['reason'] for row in evaluated if row['status'] == 'excluded'))},
        'candidates': candidates, 'evaluated': evaluated,
    }
