from datetime import datetime, timedelta, timezone
import unittest
from analytics.attention import attention

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def sample(age, score=10, comments=5):
    return {'event_id': str(age), 'story_id': 42, 'title': 'Test story',
            'observed_at': (NOW - timedelta(minutes=age)).isoformat(),
            'score': score, 'comments': comments}


class AttentionTests(unittest.TestCase):
    def test_all_horizons_and_duplicate_replay(self):
        rows = [sample(age, 100 - age, 80 - age) for age in range(61)]
        result = attention(rows + rows, NOW)
        self.assertEqual(result['observation_count'], 61)
        for window in result['windows']:
            self.assertEqual(window['status'], 'complete')
            self.assertEqual(window['score_change'], window['minutes'])
            self.assertEqual(window['comment_change'], window['minutes'])
            self.assertEqual(window['score_per_minute'], 1)

    def test_decreases_preserved(self):
        result = attention([sample(5, 20, 10), sample(3, 18, 9), sample(0, 17, 8)], NOW)
        self.assertEqual(result['windows'][0]['score_change'], -3)
        self.assertEqual(result['windows'][0]['comment_change'], -2)

    def test_missing_history_is_not_zero(self):
        result = attention([sample(0)], NOW)
        self.assertEqual(result['windows'][0]['status'], 'insufficient_history')
        self.assertIsNone(result['windows'][0]['score_change'])

    def test_stale_latest_sample(self):
        result = attention([sample(5)], NOW)
        self.assertEqual(result['status'], 'stale')
        self.assertTrue(all(w['score_change'] is None for w in result['windows']))

    def test_interior_gap_flagged(self):
        window = attention([sample(30), sample(0, 40)], NOW)['windows'][1]
        self.assertEqual(window['status'], 'sampling_gap')
        self.assertEqual(window['score_change'], 30)
        self.assertEqual(window['max_gap_seconds'], 1800)

    def test_future_events_excluded_and_numeric_strings(self):
        rows = [sample(5, '10', '5'), sample(0, '12', '6'), sample(-1, 100)]
        self.assertEqual(attention(rows, NOW)['windows'][0]['score_change'], 2)

    def test_boundary_uses_previous_sample_and_actual_elapsed_time(self):
        window = attention([sample(6, 10), sample(3, 13), sample(1, 15)], NOW)['windows'][0]
        self.assertEqual(window['elapsed_minutes'], 5)
        self.assertEqual(window['score_per_minute'], 1)

    def test_baseline_too_far_from_boundary(self):
        window = attention([sample(10), sample(0)], NOW)['windows'][0]
        self.assertEqual(window['status'], 'insufficient_history')

    def test_mixed_stories_rejected(self):
        with self.assertRaises(ValueError):
            attention([sample(5), dict(sample(0), story_id=43)], NOW)

    def test_empty_history(self):
        self.assertEqual(attention([], NOW)['status'], 'no_data')
