from datetime import timedelta
import unittest

from analytics.predictions import evaluate_prediction
from test_detector import NOW, series


class PredictionResolutionTests(unittest.TestCase):
    def test_resolves_yes_when_story_reaches_top_ten(self):
        result = evaluate_prediction(series(), 42, NOW - timedelta(minutes=10), NOW)
        self.assertEqual(result['status'], 'resolved')
        self.assertTrue(result['outcome'])
        self.assertEqual(result['reason'], 'top_ten_signal_seen')
        self.assertIsNotNone(result['first_qualified_at'])

    def test_missing_collection_is_not_a_false_no(self):
        result = evaluate_prediction([], 42, NOW - timedelta(minutes=10), NOW)
        self.assertEqual(result['status'], 'unverifiable')
        self.assertEqual(result['reason'], 'insufficient_collection')
