from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from api import wikipedia


class WikipediaTests(unittest.TestCase):
    def setUp(self):
        wikipedia._cache.clear()

    def test_found_context_has_attributed_article_and_completed_days(self):
        search = {'pages': [{'title': 'OpenAI', 'key': 'OpenAI', 'description': 'AI research lab'}]}
        views = {'items': [
            {'timestamp': '2026091000', 'views': 12},
            {'timestamp': '2026091100', 'views': 15},
        ]}
        with patch('api.wikipedia._request_json', side_effect=[search, views]) as request:
            result = wikipedia.for_story('Show HN: OpenAI', datetime(2026, 9, 12, tzinfo=timezone.utc))
        self.assertEqual(result['status'], 'found')
        self.assertEqual(result['searched_title'], 'OpenAI')
        self.assertEqual(result['article']['url'], 'https://en.wikipedia.org/wiki/OpenAI')
        self.assertEqual(result['pageviews']['recent_7_days'], 27)
        self.assertIn('search/page', request.call_args_list[0].args[0])
        self.assertIn('limit=5', request.call_args_list[0].args[0])
        self.assertIn('/20260829/20260911', request.call_args_list[1].args[0])

    def test_missing_search_result_does_not_make_a_pageview_request(self):
        with patch('api.wikipedia._request_json', return_value={'pages': []}) as request:
            result = wikipedia.for_story('No matching reference')
        self.assertEqual(result['status'], 'not_found')
        request.assert_called_once()

    def test_irrelevant_top_search_result_is_not_returned_as_context(self):
        payload = {'pages': [
            {'title': 'Fuzzy concept', 'key': 'Fuzzy_concept'},
            {'title': 'Machine learning', 'key': 'Machine_learning'},
        ]}
        with patch('api.wikipedia._request_json', return_value=payload) as request:
            result = wikipedia.for_story("Retrospectively Reverse-Engineering Apple's Neural Engine")
        self.assertEqual(result['status'], 'not_found')
        request.assert_called_once()
