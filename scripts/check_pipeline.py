"""Bounded end-to-end check: run after ingestion and SQL job are running."""
import base64
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

query = "SELECT count() FROM pulse.story_windows_v2 FINAL WHERE window_end > now() - INTERVAL 6 MINUTE"
deadline = time.monotonic() + 300
while time.monotonic() < deadline:
    try:
        request = Request("http://localhost:8123/", data=query.encode(), headers={
            "Authorization": "Basic " + base64.b64encode(b"pulse:pulse-local").decode()
        })
        with urlopen(request, timeout=5) as response:
            count = int(response.read())
        if count > 0:
            print(f"PASS: ClickHouse contains {count} recent Flink story windows.")
            break
    except (URLError, ValueError) as error:
        print(f"Waiting for pipeline: {error}", flush=True)
    time.sleep(5)
else:
    raise SystemExit("FAIL: No recent event-time windows within 300 seconds. Check ingestion logs and Flink jobs at localhost:8081.")
