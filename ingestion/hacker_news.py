"""Poll a bounded sample of HN stories; publish observations, not vote events."""
import argparse
from datetime import datetime, timezone
import html
import json
import logging
import os
import signal
import threading
import time
from urllib.request import Request, urlopen

API = "https://hacker-news.firebaseio.com/v0"
LOG = logging.getLogger("pulse.ingestion")


def fetch(path):
    request = Request(f"{API}/{path}.json", headers={"User-Agent": "Pulse-local-prototype/0.1"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def normalize(item, observed_at):
    if not item or item.get("type") != "story" or item.get("deleted") or item.get("dead"):
        return None
    if not isinstance(item.get("id"), int) or not isinstance(item.get("title"), str):
        return None
    if not isinstance(item.get("time"), int):
        return None
    story_id = item["id"]
    timestamp = observed_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return {
        "schema_version": 1,
        "event_id": f"hn:{story_id}:{timestamp}",
        "source": "hacker_news",
        "story_id": story_id,
        "title": html.unescape(item["title"]),
        "url": item.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
        "created_at_epoch": item["time"],
        "observed_at": timestamp,
        "score": max(0, int(item.get("score", 0))),
        "comments": max(0, int(item.get("descendants", 0))),
    }


def collect(limit, fetcher=fetch, now=None):
    # Union new and top lists; one observation per story per polling cycle.
    ids = dict.fromkeys((fetcher("newstories") or [])[:limit] + (fetcher("topstories") or [])[:limit])
    for story_id in ids:
        try:
            item = fetcher(f"item/{story_id}")
            event = normalize(item, now or datetime.now(timezone.utc))
            if event:
                yield event
        except (OSError, ValueError, TypeError):
            LOG.exception("Could not observe story %s; retry next cycle", story_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true", help="Fetch real data without Kafka")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=50, help="Stories per new/top list")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    if args.limit < 1 or args.interval < 1:
        parser.error("limit and interval must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    producer = None
    if not args.stdout:
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            acks="all", retries=10, max_in_flight_requests_per_connection=1,
            value_serializer=lambda value: json.dumps(value).encode(),
            key_serializer=lambda key: key.encode(),
        )
    try:
        while not stop.is_set():
            count = 0
            for event in collect(args.limit):
                if stop.is_set():
                    break
                if producer:
                    producer.send("hn.observations.v1", key=str(event["story_id"]), value=event).get(timeout=60)
                else:
                    print(json.dumps(event), flush=True)
                count += 1
            LOG.info("Published %s story observations", count)
            if args.once:
                break
            stop.wait(args.interval)
    finally:
        if producer:
            producer.close(timeout=30)


if __name__ == "__main__":
    main()
