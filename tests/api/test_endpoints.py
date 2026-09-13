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

    def test_wikipedia_context_uses_the_latest_story_title(self):
        context = {'status': 'found', 'article': {'title': 'Story 42'}, 'pageviews': {'status': 'available'}}
        with patch('api.main.wikipedia.for_story', return_value=context) as lookup:
            response = self.client.get('/v1/stories/42/wikipedia', params=self.params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['article']['title'], 'Story 42')
        lookup.assert_called_once_with('Story 42')

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

    def test_reddit_posts_are_source_specific(self):
        rows = [{
            'post_id': 'a1', 'subreddit': 'technology', 'title': 'A launch', 'url': 'https://reddit.com/x',
            'observed_at': NOW.isoformat(), 'score': '12', 'comments': '4', 'upvote_ratio': '0.8',
        }]
        with patch('api.main.reddit_store.observations', return_value=rows) as reddit_read:
            response = self.client.get('/v1/reddit/posts', params=self.params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['posts'][0]['post_id'], 'a1')
        reddit_read.assert_called_once_with(NOW, minutes=120, post_id=None)

    def test_reddit_history_has_no_detector_claim(self):
        rows = [{'post_id': 'a1', 'observed_at': NOW.isoformat()}]
        with patch('api.main.reddit_store.observations', return_value=rows):
            response = self.client.get('/v1/reddit/posts/a1/history', params=self.params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['source'], 'reddit')

    def test_prediction_locks_a_call_for_the_local_browser(self):
        saved = {'id': '9fbdc9d6-6100-44cd-b00e-670acfb20e7c', 'story_id': 42,
                 'story_title': 'Story 42', 'call': 'yes', 'status': 'pending',
                 'created_at': NOW, 'expires_at': NOW + timedelta(hours=24)}
        with patch('api.main.prediction_store.create', return_value=saved) as create:
            response = self.client.post('/v1/stories/42/predictions', json={'call': 'yes'},
                                        headers={'X-Pulse-Local-User': '00000000-0000-4000-8000-000000000001'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['prediction']['call'], 'yes')
        self.assertEqual(create.call_args.args[4], 50)

    def test_prediction_rejects_out_of_range_confidence(self):
        response = self.client.post('/v1/stories/42/predictions', json={'call': 'no', 'confidence': 45},
                                    headers={'X-Pulse-Local-User': '00000000-0000-4000-8000-000000000001'})
        self.assertEqual(response.status_code, 422)

    def test_profile_returns_verified_record_for_the_local_browser(self):
        record = {'total': 3, 'pending': 1, 'resolved': 2, 'unverifiable': 0,
                  'scored': 2, 'correct': 1, 'accuracy': 50.0, 'average_early_minutes': 180.0}
        with patch('api.main.prediction_store.profile_for_owner', return_value=record) as profile:
            response = self.client.get('/v1/profile', headers={'X-Pulse-Local-User': '00000000-0000-4000-8000-000000000001'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['accuracy'], 50.0)
        profile.assert_called_once()

    def test_prediction_rejects_invalid_local_user(self):
        response = self.client.post('/v1/stories/42/predictions', json={'call': 'no'},
                                    headers={'X-Pulse-Local-User': 'not-a-uuid'})
        self.assertEqual(response.status_code, 422)

    def test_prediction_store_failure_is_sanitized(self):
        from api.prediction_store import StoreUnavailable
        with patch('api.main.prediction_store.list_for_owner', side_effect=StoreUnavailable('secret connection')):
            response = self.client.get('/v1/predictions', headers={'X-Pulse-Local-User': '00000000-0000-4000-8000-000000000001'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.text)
