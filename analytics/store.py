"""Read normalized observations from local ClickHouse with bounded time ranges."""
import base64
from datetime import timedelta
import json
import os
from urllib.request import Request, urlopen
from analytics.attention import timestamp


def observations(as_of, minutes=22, story_id=None):
    end = timestamp(as_of)
    start = end - timedelta(minutes=minutes)
    story_filter = f'AND story_id = {int(story_id)}' if story_id is not None else ''
    sql = f"""SELECT * FROM pulse.observations FINAL
        WHERE schema_version = 1 AND source = 'hacker_news' {story_filter}
        AND observed_at >= '{start.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'
        AND observed_at <= '{end.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'
        ORDER BY story_id, observed_at, event_id FORMAT JSONEachRow"""
    credentials = (os.getenv('CLICKHOUSE_USER', 'pulse') + ':' + os.getenv('CLICKHOUSE_PASSWORD', 'pulse-local')).encode()
    request = Request(os.getenv('CLICKHOUSE_URL', 'http://localhost:8123'), data=sql.encode(),
                      headers={'Authorization': 'Basic ' + base64.b64encode(credentials).decode()})
    with urlopen(request, timeout=15) as response:
        return [json.loads(line) for line in response if line.strip()]
