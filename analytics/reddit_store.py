"""Read Reddit's source-specific raw observations from local ClickHouse."""
import base64
from datetime import timedelta
import json
import os
from urllib.request import Request, urlopen
from analytics.attention import timestamp


def observations(as_of, minutes=120, post_id=None):
    end = timestamp(as_of)
    start = end - timedelta(minutes=minutes)
    safe_post_id = post_id.replace("'", "") if post_id else None
    post_filter = "AND post_id = '{}'".format(safe_post_id) if safe_post_id else ""
    sql = f"""SELECT * FROM pulse.reddit_observations FINAL
        WHERE schema_version = 1 {post_filter}
        AND observed_at >= '{start.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'
        AND observed_at <= '{end.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'
        ORDER BY post_id, observed_at, event_id FORMAT JSONEachRow"""
    credentials = (os.getenv('CLICKHOUSE_USER', 'pulse') + ':' + os.getenv('CLICKHOUSE_PASSWORD', 'pulse-local')).encode()
    request = Request(os.getenv('CLICKHOUSE_URL', 'http://localhost:8123'), data=sql.encode(),
                      headers={'Authorization': 'Basic ' + base64.b64encode(credentials).decode()})
    with urlopen(request, timeout=15) as response:
        return [json.loads(line) for line in response if line.strip()]
