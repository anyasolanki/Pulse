"""Coverage/signal sanity check over historical cutoffs, not a precision backtest."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.attention import timestamp
from analytics.detector import detect, VERSION
from analytics.store import observations


def evaluate_history(rows, end, lookback_minutes=60, step_minutes=5):
    if lookback_minutes < 1 or step_minutes < 1:
        raise ValueError('lookback and step must be positive')
    end = timestamp(end)
    available = [row for row in rows if timestamp(row['observed_at']) <= end]
    snapshots = []
    if available:
        earliest = min(timestamp(row['observed_at']) for row in available)
        cursor = max(end - timedelta(minutes=lookback_minutes), earliest + timedelta(minutes=20))
        cutoffs = []
        while cursor < end:
            cutoffs.append(cursor)
            cursor += timedelta(minutes=step_minutes)
        cutoffs.append(end)
        for cutoff in cutoffs:
            report = detect(available, cutoff)
            snapshots.append({'as_of': report['as_of'], **report['summary'],
                              'candidate_story_ids': [row['story_id'] for row in report['candidates']]})
    return {'detector_version': VERSION, 'as_of': end.isoformat(), 'snapshots': snapshots,
            'unique_candidates': sorted({story for row in snapshots for story in row['candidate_story_ids']}),
            'scope': 'Historical coverage and signal frequency only. No outcome labels, precision, recall or predictive accuracy. '
                     'Cutoffs exclude future observation times, but later-arriving historical data may be included.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of')
    parser.add_argument('--lookback-minutes', type=int, default=60)
    parser.add_argument('--step-minutes', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 1 <= args.lookback_minutes <= 1440 or args.step_minutes < 1:
        parser.error('lookback must be 1–1440 minutes and step must be positive')
    end = timestamp(args.as_of) if args.as_of else datetime.now(timezone.utc)
    rows = observations(end, minutes=args.lookback_minutes + 22)
    result = evaluate_history(rows, end, args.lookback_minutes, args.step_minutes)
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
        print(f'Saved {args.output.resolve()}')
    else:
        print(rendered)


if __name__ == '__main__':
    main()
