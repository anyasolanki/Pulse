from datetime import datetime, timedelta, timezone
import unittest
from analytics.detector import detect, evaluate

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def series(story=42, comments=None, score=None, minutes=20):
    comments = comments or (lambda i: 20 + i if i <= 15 else 35 + 3 * (i - 15))
    score = score or (lambda i: 100 + i)
    return [{'event_id': f'{story}:{i}', 'story_id': story, 'title': f'Story {story}',
             'observed_at': (NOW - timedelta(minutes=20-i)).isoformat(),
             'score': score(i), 'comments': comments(i)} for i in range(minutes+1)]


class DetectorTests(unittest.TestCase):
    def test_acceleration_has_numeric_evidence(self):
        result = evaluate(series(), NOW)
        self.assertEqual(result['status'], 'candidate')
        channel = result['channels']['comments']
        self.assertEqual(channel['baseline_change'], 15)
        self.assertEqual(channel['recent_change'], 15)
        self.assertEqual(channel['rate_multiple'], 3)
        self.assertEqual(channel['excess_change'], 10)
        self.assertEqual(result['priority'], 2)
        self.assertEqual(result['evidence']['recent_start']['comments'], 35)

    def test_popular_but_steady_is_quiet(self):
        result = evaluate(series(comments=lambda i: 1000 + 20*i, score=lambda i: 1000 + 50*i), NOW)
        self.assertEqual(result['status'], 'quiet')

    def test_zero_to_one_does_not_trigger(self):
        result = evaluate(series(comments=lambda i: int(i == 20), score=lambda i: 100), NOW)
        self.assertEqual(result['status'], 'quiet')
        self.assertIn('low_volume', result['channels']['comments']['reasons'])

    def test_zero_baseline_is_finite_and_explicit(self):
        result = evaluate(series(comments=lambda i: max(0, i-15)), NOW)
        self.assertEqual(result['status'], 'candidate')
        self.assertTrue(result['channels']['comments']['rate_floor_applied'])
        self.assertEqual(result['channels']['comments']['rate_multiple'], 5)

    def test_exact_thresholds(self):
        rows = series(comments=lambda i: int(i*0.4) if i <= 15 else 6 + i-15)
        result = evaluate(rows, NOW)
        self.assertEqual(result['status'], 'candidate')
        self.assertEqual(result['channels']['comments']['recent_change'], 5)
        self.assertEqual(result['channels']['comments']['excess_change'], 3)

    def test_decreasing_counter_does_not_create_acceleration(self):
        rows = series()
        rows[10]['comments'] = 0
        result = evaluate(rows, NOW)
        self.assertEqual(result['status'], 'quiet')
        self.assertIn('counter_decreased', result['channels']['comments']['reasons'])

    def test_other_channel_can_qualify(self):
        rows = series(score=lambda i: 100+i if i <= 15 else 115+4*(i-15))
        rows[10]['comments'] = 0
        result = evaluate(rows, NOW)
        self.assertEqual(result['status'], 'candidate')
        self.assertFalse(result['channels']['comments']['qualifies'])
        self.assertTrue(result['channels']['score']['qualifies'])

    def test_replay_and_input_order_do_not_change_result(self):
        rows = series()
        self.assertEqual(evaluate(rows, NOW), evaluate(list(reversed(rows)) + rows, NOW))

    def test_missing_early_history(self):
        self.assertEqual(evaluate(series()[1:], NOW)['reason'], 'insufficient_history')

    def test_stale(self):
        self.assertEqual(evaluate(series()[:-3], NOW)['reason'], 'stale')

    def test_sampling_gap(self):
        rows = [row for i, row in enumerate(series()) if i not in (8, 9, 10)]
        self.assertEqual(evaluate(rows, NOW)['reason'], 'sampling_gap')

    def test_no_future_lookahead(self):
        rows = series()
        future = dict(rows[-1], event_id='future', observed_at=(NOW+timedelta(minutes=1)).isoformat(), comments=1000)
        self.assertEqual(evaluate(rows, NOW), evaluate(rows + [future], NOW))

    def test_ranking_excess_growth_and_stable_ties(self):
        report = detect(series(44) + series(43) + series(45, comments=lambda i: i if i <= 15 else 15+5*(i-15)), NOW)
        self.assertEqual([row['story_id'] for row in report['candidates']], [45, 43, 44])
        self.assertEqual([row['rank'] for row in report['candidates']], [1, 2, 3])

    def test_summary_separates_quiet_and_excluded(self):
        report = detect(series(1) + series(2)[10:] + series(3, comments=lambda i: 0), NOW)
        self.assertEqual(report['summary'], {'stories_evaluated': 3, 'candidates': 1,
                         'eligible': 2, 'exclusions': {'insufficient_history': 1}})

    def test_actual_durations_not_nominal_duration(self):
        rows = series()
        for row in rows:
            if row == rows[-1]:
                row['observed_at'] = (NOW - timedelta(seconds=30)).isoformat()
        channel = evaluate(rows, NOW)['channels']['comments']
        self.assertAlmostEqual(channel['recent_rate_per_minute'], 15/4.5)

    def test_string_integer_fields_from_clickhouse(self):
        rows = [dict(row, story_id=str(row['story_id']), score=str(row['score']), comments=str(row['comments'])) for row in series()]
        self.assertEqual(evaluate(rows, NOW)['status'], 'candidate')

    def test_mixed_stories_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(series(1) + series(2), NOW)

    def test_empty_report(self):
        self.assertEqual(detect([], NOW)['candidates'], [])

    def test_missing_recent_boundary(self):
        rows = [row for i, row in enumerate(series()) if i not in (13, 14, 15)]
        self.assertEqual(evaluate(rows, NOW)['reason'], 'missing_boundary')

    def test_sparse_but_not_gapped(self):
        rows = [row for i, row in enumerate(series()) if i in (0, 3, 6, 9, 12, 15, 17, 20)]
        self.assertEqual(evaluate(rows, NOW)['reason'], 'sparse_samples')

    def test_old_stories_not_in_current_population(self):
        rows = [dict(row, observed_at=(NOW-timedelta(hours=2)).isoformat()) for row in series()]
        self.assertEqual(detect(rows, NOW)['summary']['stories_evaluated'], 0)
