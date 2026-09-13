"""Small, on-demand Wikimedia context lookups for an HN investigation."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html import unescape
import json
import os
import re
import time
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SEARCH_URL = 'https://en.wikipedia.org/w/rest.php/v1/search/page'
PAGEVIEWS_URL = 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article'
CACHE_SECONDS = 15 * 60
USER_AGENT = os.getenv(
    'WIKIMEDIA_USER_AGENT',
    'Pulse/0.3 (https://github.com/anyasolanki/Pulse)',
)
STOP_WORDS = frozenset({
    'about', 'after', 'and', 'are', 'for', 'from', 'have', 'into', 'news', 'show',
    'that', 'the', 'this', 'was', 'with', 'your',
})

_cache: dict[str, tuple[float, dict]] = {}
_cooldown_until = 0.0


class LookupUnavailable(Exception):
    """Wikimedia could not be read without risking a misleading result."""


def _request_json(url: str):
    global _cooldown_until
    if time.monotonic() < _cooldown_until:
        raise LookupUnavailable('Wikimedia is temporarily rate-limited')
    request = Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': USER_AGENT,
        'Api-User-Agent': USER_AGENT,
    })
    try:
        with urlopen(request, timeout=4) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        if error.code == 429:
            retry_after = error.headers.get('Retry-After', '300')
            try:
                _cooldown_until = time.monotonic() + max(1, min(int(retry_after), 900))
            except ValueError:
                _cooldown_until = time.monotonic() + 300
        raise LookupUnavailable('Wikimedia request failed') from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise LookupUnavailable('Wikimedia request failed') from error


def _search_title(story_title: str) -> str:
    title = re.sub(r'^\s*show hn\s*:\s*', '', story_title, flags=re.IGNORECASE)
    return ' '.join(title.split())[:240]


def _plain(value) -> Optional[str]:
    if not value:
        return None
    return ' '.join(unescape(re.sub(r'<[^>]+>', '', str(value))).split()) or None


def _words(value: str) -> set[str]:
    return {word.casefold() for word in re.findall(r"[a-zA-Z0-9]{3,}", value)
            if word.casefold() not in STOP_WORDS}


def _matching_page(pages: list[dict], query: str) -> Optional[dict]:
    """Pick only a result whose *article title* supports a direct context claim."""
    query_words = _words(query)
    query_normalized = ' '.join(query.casefold().split())
    matches = []
    for page in pages:
        title = str(page.get('title') or '')
        title_normalized = ' '.join(title.casefold().split())
        overlap = len(query_words & _words(title))
        exact_phrase = len(title_normalized) >= 4 and title_normalized in query_normalized
        # A single generic word is too weak for a three-or-more-term HN title.
        if exact_phrase or overlap >= (1 if len(query_words) <= 2 else 2):
            matches.append((exact_phrase, overlap, page))
    return max(matches, default=(False, 0, None), key=lambda match: (match[0], match[1]))[2]


def _pageviews(article: str, now: datetime) -> dict:
    # Current UTC days are incomplete, so use fourteen fully completed daily buckets.
    last_day = now.date() - timedelta(days=1)
    first_day = last_day - timedelta(days=13)
    encoded_article = quote(article.replace(' ', '_'), safe='')
    url = (f'{PAGEVIEWS_URL}/en.wikipedia.org/all-access/user/{encoded_article}/daily/'
           f'{first_day:%Y%m%d}/{last_day:%Y%m%d}')
    payload = _request_json(url)
    if payload is None:
        return {'status': 'unavailable', 'daily': []}
    daily = [
        {'date': f"{item['timestamp'][:4]}-{item['timestamp'][4:6]}-{item['timestamp'][6:8]}",
         'views': int(item['views'])}
        for item in payload.get('items', [])
        if item.get('timestamp') and item.get('views') is not None
    ]
    daily.sort(key=lambda item: item['date'])
    total = sum(item['views'] for item in daily)
    recent = sum(item['views'] for item in daily[-7:])
    prior = sum(item['views'] for item in daily[-14:-7])
    return {
        'status': 'available' if daily else 'unavailable',
        'daily': daily,
        'total_14_days': total,
        'recent_7_days': recent,
        'prior_7_days': prior,
    }


def for_story(story_title: str, now: Optional[datetime] = None) -> dict:
    """Return clearly labelled context, never a claim that two sources are the same topic."""
    query = _search_title(story_title)
    key = query.casefold()
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return deepcopy(cached[1])

    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result = {
        'searched_title': query,
        'checked_at': checked_at.isoformat(),
        'provider': 'Wikimedia',
        'note': ('This is automated reference context and recent public page-view history. '
                 'It does not establish that the Wikipedia page and HN story describe the same topic.'),
    }
    if not query:
        return {**result, 'status': 'not_found'}
    try:
        payload = _request_json(f'{SEARCH_URL}?{urlencode({"q": query, "limit": 5})}')
        pages = payload.get('pages', []) if payload else []
        page = _matching_page(pages, query)
        if page is None:
            result['status'] = 'not_found'
        else:
            title = str(page['title'])
            result.update({
                'status': 'found',
                'article': {
                    'title': title,
                    'description': _plain(page.get('description') or page.get('excerpt')),
                    'url': f'https://en.wikipedia.org/wiki/{quote(str(page.get("key") or title).replace(" ", "_"), safe="/")}',
                },
                'pageviews': _pageviews(title, checked_at),
            })
    except (LookupUnavailable, KeyError, TypeError, ValueError):
        result['status'] = 'unavailable'
    _cache[key] = (time.monotonic(), deepcopy(result))
    return result
