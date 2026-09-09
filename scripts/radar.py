"""Print or save an evidence-backed ranking of accelerating HN stories."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.attention import timestamp
from analytics.detector import detect
from analytics.store import observations


def markdown(report, limit):
    summary = report['summary']
    lines = ['# Pulse — accelerating Hacker News stories', '',
             f"As of {report['as_of']} · detector `{report['detector_version']}`", '',
             f"{summary['stories_evaluated']} stories checked; {summary['eligible']} have usable history; "
             f"{summary['candidates']} meet the acceleration rules.", '',
             'Comparison: approximately the last 5 minutes versus the preceding 15 minutes. '
             'Rates use actual sampled durations. These are heuristic signals within the sampled HN stories, not predictions of virality.', '']
    if not report['candidates']:
        lines += ['No stories currently meet the rules. Thresholds are not relaxed to fill the list.', '']
    for story in report['candidates'][:limit]:
        title = story['title'].replace('\n', ' ').replace('[', '\\[').replace(']', '\\]')
        lines += [f"## {story['rank']}. [{title}]({story['evidence_url']})", '']
        sample = story['sampling']
        for channel, values in story['channels'].items():
            if not values['qualifies']:
                continue
            label = 'net comments' if channel == 'comments' else 'HN score points'
            lines.append(f"- +{values['recent_change']} {label} in {sample['recent_minutes']:.1f} minutes "
                         f"({values['recent_rate_per_minute']:.2f}/min), versus "
                         f"+{values['baseline_change']} in the prior {sample['baseline_minutes']:.1f} minutes "
                         f"({values['baseline_rate_per_minute']:.2f}/min).")
            floor = ' against the minimum baseline rate' if values['rate_floor_applied'] else ' the previous rate'
            lines.append(f"- {values['rate_multiple']:.2f}×{floor}; "
                         f"{values['excess_change']:.1f} more than the previous rate would imply.")
        ev = story['evidence']
        lines += ['', f"Evidence times (UTC): {ev['baseline_start']['observed_at']} → "
                  f"{ev['recent_start']['observed_at']} → {ev['latest']['observed_at']}.",
                  f"Largest sampling gap: {sample['max_gap_seconds']:.0f} seconds. "
                  f"Inspect all samples with `python3 scripts/story_history.py {story['story_id']} "
                  f"--as-of {report['as_of']} --evidence`.", '']
    if summary['exclusions']:
        lines += ['## Coverage exclusions', '']
        lines += [f'- {reason}: {count}' for reason, count in sorted(summary['exclusions'].items())]
        lines.append('')
    lines += ['The JSON format includes thresholds, both channels, exclusion reasons, endpoint values and the ranking calculation. '
              'This ranking uses recent excess growth; it is not a calibrated Pulse Score. '
              'Historical queries can change when late observations arrive.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', help='ISO timestamp; defaults to now in UTC')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    end = timestamp(args.as_of) if args.as_of else datetime.now(timezone.utc)
    report = detect(observations(end), end)
    # JSON deliberately preserves every decision for audit; limit is display-only.
    rendered = json.dumps(report, indent=2) if args.format == 'json' else markdown(report, args.limit)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + '\n')
        print(f'Saved {args.output.resolve()}')
    else:
        print(rendered)


if __name__ == '__main__':
    main()
