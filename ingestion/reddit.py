"""Collect public Reddit submission metrics through OAuth; do not archive authors or bodies."""
import argparse
from datetime import datetime, timezone
import json
import logging
import os
import signal
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOG = logging.getLogger("pulse.reddit")
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_URL = "https://oauth.reddit.com"


def required(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required; see .env.example and README.md")
    return value


class RedditClient:
    def __init__(self, client_id, client_secret, user_agent, opener=urlopen):
        self.client_id, self.client_secret, self.user_agent = client_id, client_secret, user_agent
        self.opener, self.token, self.token_expires_at = opener, None, 0

    def access_token(self):
        if self.token and time.time() < self.token_expires_at:
            return self.token
        request = Request(TOKEN_URL, data=urlencode({"grant_type": "client_credentials"}).encode(),
                          headers={"User-Agent": self.user_agent})
        import base64
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        request.add_header("Authorization", f"Basic {credentials}")
        with self.opener(request, timeout=20) as response:
            result = json.load(response)
        self.token = result["access_token"]
        self.token_expires_at = time.time() + max(60, int(result.get("expires_in", 3600)) - 60)
        return self.token

    def new_posts(self, subreddit, limit):
        request = Request(f"{API_URL}/r/{subreddit}/new?limit={limit}&raw_json=1", headers={
            "Authorization": f"Bearer {self.access_token()}", "User-Agent": self.user_agent,
        })
        with self.opener(request, timeout=20) as response:
            return json.load(response).get("data", {}).get("children", [])


def normalize(item, observed_at):
    post = item.get("data", item) if item else None
    if not post or post.get("kind") not in (None, "t3") or post.get("removed_by_category"):
        return None
    if not isinstance(post.get("id"), str) or not isinstance(post.get("title"), str):
        return None
    if not isinstance(post.get("created_utc"), (int, float)) or not isinstance(post.get("subreddit"), str):
        return None
    timestamp = observed_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    post_id = post["id"]
    permalink = post.get("permalink") or f"/comments/{post_id}"
    return {
        "schema_version": 1, "event_id": f"reddit:{post_id}:{timestamp}", "source": "reddit",
        "post_id": post_id, "subreddit": post["subreddit"], "title": post["title"],
        "url": f"https://www.reddit.com{permalink}", "created_at_epoch": int(post["created_utc"]),
        "observed_at": timestamp, "score": int(post.get("score") or 0),
        "comments": int(post.get("num_comments") or 0), "upvote_ratio": float(post.get("upvote_ratio") or 0),
    }


def collect(client, subreddits, limit, now=None):
    for subreddit in subreddits:
        try:
            for item in client.new_posts(subreddit, limit):
                event = normalize(item, now or datetime.now(timezone.utc))
                if event:
                    yield event
        except (OSError, ValueError, KeyError, TypeError):
            LOG.exception("Could not observe r/%s; retry next cycle", subreddit)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true", help="Fetch real data without Kafka")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=int(os.getenv("REDDIT_POSTS_PER_SUBREDDIT", "25")))
    parser.add_argument("--interval", type=int, default=int(os.getenv("REDDIT_POLL_INTERVAL", "120")))
    args = parser.parse_args()
    if args.limit < 1 or args.interval < 30:
        parser.error("limit must be positive and interval must be at least 30 seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = RedditClient(required("REDDIT_CLIENT_ID"), required("REDDIT_CLIENT_SECRET"), required("REDDIT_USER_AGENT"))
    subreddits = [value.strip() for value in os.getenv("REDDIT_SUBREDDITS", "technology,programming,science").split(",") if value.strip()]
    if not subreddits:
        parser.error("REDDIT_SUBREDDITS must contain at least one subreddit")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, lambda *_: stop.set())
    producer = None
    if not args.stdout:
        from kafka import KafkaProducer
        producer = KafkaProducer(bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            acks="all", retries=10, max_in_flight_requests_per_connection=1,
            value_serializer=lambda value: json.dumps(value).encode(), key_serializer=lambda key: key.encode())
    try:
        while not stop.is_set():
            count = 0
            for event in collect(client, subreddits, args.limit):
                if producer: producer.send("reddit.observations.v1", key=event["post_id"], value=event).get(timeout=60)
                else: print(json.dumps(event), flush=True)
                count += 1
            LOG.info("Published %s Reddit post observations", count)
            if args.once: break
            stop.wait(args.interval)
    finally:
        if producer: producer.close(timeout=30)


if __name__ == "__main__": main()
