"""Query real raw observations and print evidence-backed attention changes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.attention import attention, timestamp
from analytics.store import observations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('story_id', type=int)
    parser.add_argument('--as-of', help='ISO timestamp; defaults to now in UTC')
    parser.add_argument('--evidence', action='store_true', help='Include every raw sample')
    args = parser.parse_args()
    end = timestamp(args.as_of) if args.as_of else datetime.now(timezone.utc)
    rows = observations(end, minutes=63, story_id=args.story_id)
    result = attention(rows, end)
    if args.evidence:
        result['evidence'] = rows
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
