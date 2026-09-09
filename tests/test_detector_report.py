from datetime import timedelta
import unittest
from analytics.detector import detect
from scripts.radar import markdown
from scripts.evaluate_detector import evaluate_history
from test_detector import NOW, series


class DetectorReportTests(unittest.TestCase):
    def test_empty_candidate_list_is_explicit(self):
        rendered = markdown(detect(series(comments=lambda i: 0), NOW), 10)
        self.assertIn('No stories currently meet the rules', rendered)

    def test_report_shows_actual_rates_and_evidence(self):
        rendered = markdown(detect(series(), NOW), 10)
        self.assertIn('+15 net comments in 5.0 minutes', rendered)
        self.assertIn('3.00× the previous rate', rendered)
        self.assertIn('item?id=42', rendered)
        self.assertIn('--evidence', rendered)

    def test_floor_is_disclosed(self):
        rendered = markdown(detect(series(comments=lambda i: max(0, i-15)), NOW), 10)
        self.assertIn('against the minimum baseline rate', rendered)

    def test_evaluation_excludes_future_rows(self):
        rows = series()
        future = [dict(row, observed_at=(NOW+timedelta(minutes=1)).isoformat()) for row in series(999)]
        result = evaluate_history(rows + future, NOW)
        self.assertEqual(result['unique_candidates'], [42])
        self.assertEqual(result['snapshots'][-1]['stories_evaluated'], 1)

    def test_evaluation_reports_insufficient_warmup(self):
        result = evaluate_history(series()[10:], NOW)
        self.assertEqual(len(result['snapshots']), 1)
        self.assertEqual(result['snapshots'][0]['eligible'], 0)
