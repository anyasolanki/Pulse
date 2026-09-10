import unittest
from datetime import datetime, timezone
from ingestion.hacker_news import collect, normalize
from ingestion.reddit import normalize as normalize_reddit

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
STORY = {"id": 42, "type": "story", "title": "Ask HN: A &amp; B", "time": 100, "score": 7, "descendants": 3}


class IngestionTests(unittest.TestCase):
    def test_snapshot_contract(self):
        event = normalize(STORY, NOW)
        self.assertEqual(event["title"], "Ask HN: A & B")
        self.assertEqual(event["score"], 7)
        self.assertEqual(event["comments"], 3)
        self.assertEqual(event["observed_at"], "2026-09-08 12:00:00.000")
        self.assertEqual(event["url"], "https://news.ycombinator.com/item?id=42")
        self.assertEqual(event, normalize(STORY, NOW))

    def test_skip_unusable_items(self):
        for item in (None, {}, dict(STORY, deleted=True), dict(STORY, dead=True), dict(STORY, type="comment")):
            with self.subTest(item=item):
                self.assertIsNone(normalize(item, NOW))

    def test_optional_fields(self):
        event = normalize({k: v for k, v in STORY.items() if k not in ("score", "descendants")}, NOW)
        self.assertEqual((event["score"], event["comments"]), (0, 0))

    def test_list_overlap_not_double_counted(self):
        data = {"newstories": [42, 43], "topstories": [42], "item/42": STORY, "item/43": dict(STORY, id=43)}
        events = list(collect(2, data.__getitem__, NOW))
        self.assertEqual([e["story_id"] for e in events], [42, 43])

    def test_one_bad_story_does_not_drop_other_stories(self):
        data = {"newstories": [42, 43], "topstories": [], "item/42": dict(STORY, score="invalid"), "item/43": dict(STORY, id=43)}
        with self.assertLogs("pulse.ingestion", level="ERROR"):
            events = list(collect(2, data.__getitem__, NOW))
        self.assertEqual([e["story_id"] for e in events], [43])

    def test_reddit_snapshot_contract(self):
        event = normalize_reddit({'kind': 't3', 'data': {
            'id': 'abc123', 'subreddit': 'technology', 'title': 'Useful launch', 'created_utc': 100,
            'score': 7, 'num_comments': 3, 'upvote_ratio': 0.92, 'permalink': '/r/technology/comments/abc123/x/',
        }}, NOW)
        self.assertEqual(event['event_id'], 'reddit:abc123:2026-09-08 12:00:00.000')
        self.assertEqual(event['url'], 'https://www.reddit.com/r/technology/comments/abc123/x/')
        self.assertEqual((event['score'], event['comments'], event['upvote_ratio']), (7, 3, 0.92))

    def test_reddit_skips_removed_or_incomplete_posts(self):
        self.assertIsNone(normalize_reddit({'data': {'id': 'x', 'removed_by_category': 'moderator'}}, NOW))
        self.assertIsNone(normalize_reddit({'data': {'id': 'x', 'title': 'x'}}, NOW))


if __name__ == "__main__":
    unittest.main()
