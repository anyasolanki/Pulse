from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.error import URLError
from fastapi.testclient import TestClient
from api.main import app
from analytics.detector import detect
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_detector import NOW, series


class APITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patch = patch('api.main.store.observations', return_value=series())
        self.read = self.patch.start()
        self.addCleanup(self.patch.stop)
        self.params = {'as_of': NOW.isoformat()}

    def test_radar_matches_detector(self):
        response = self.client.get('/v1/radar', params=self.params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['candidates'], detect(series(), NOW)['candidates'])
        self.assertNotIn('evaluated', response.json())

    def test_history_exposes_evidence(self):
        response = self.client.get('/v1/stories/42/history', params=self.params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['evidence']), 21)
        self.read.assert_called_once_with(NOW, minutes=63, story_id=42)

    def test_history_evidence_can_be_omitted(self):
        response = self.client.get('/v1/stories/42/history', params={**self.params, 'evidence': 'false'})
        self.assertNotIn('evidence', response.json())

    def test_explanation_includes_failed_channels(self):
        response = self.client.get('/v1/stories/42/explanation', params=self.params)
        self.assertEqual(response.json()['story']['status'], 'candidate')
        self.assertFalse(response.json()['story']['channels']['score']['qualifies'])

    def test_missing_interval_is_404(self):
        self.read.return_value = []
        self.assertEqual(self.client.get('/v1/stories/42/history', params=self.params).status_code, 404)

    def test_empty_radar_is_not_database_error(self):
        self.read.return_value = []
        response = self.client.get('/v1/radar', params=self.params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['eligible'], 0)

    def test_unavailable_store_is_sanitized(self):
        self.read.side_effect = URLError('secret database details')
        response = self.client.get('/v1/radar', params=self.params)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.text)

    def test_invalid_queries_rejected_before_database_read(self):
        for params in ({'limit': 101}, {'limit': 0}, {'as_of': 'bad'},
                       {'as_of': '2026-01-01T00:00:00'}, {'as_of': '2099-01-01T00:00:00Z'}):
            self.assertEqual(self.client.get('/v1/radar', params=params).status_code, 422)
        self.read.assert_not_called()

    def test_invalid_story_id(self):
        for story in ('0', '-1', 'abc'):
            self.assertEqual(self.client.get(f'/v1/stories/{story}/history').status_code, 422)

    def test_pagination_and_numeric_fields(self):
        self.read.return_value = series(42) + series(43)
        response = self.client.get('/v1/stories', params={**self.params, 'limit': 1, 'offset': 1})
        self.assertEqual(response.json()['total'], 2)
        self.assertEqual(response.json()['stories'][0]['story_id'], 43)

    def test_health_distinguishes_stale_collection(self):
        self.read.return_value = []
        self.assertEqual(self.client.get('/health').status_code, 503)
        row = series()[-1]
        row['observed_at'] = datetime.now(timezone.utc).isoformat()
        self.read.return_value = [row]
        self.assertEqual(self.client.get('/health').json()['status'], 'ok')

    def test_openapi_available(self):
        paths = self.client.get('/openapi.json').json()['paths']
        self.assertIn('/v1/stories/{story_id}/explanation', paths)
