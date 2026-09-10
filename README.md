# Pulse

Know what's happening before everyone else.

Pulse is a local prototype for detecting emerging internet topics. It collects Hacker News story observations, preserves history, and ranks stories whose recent attention growth has accelerated. A separate opt-in Reddit collector stores public submission-level metrics for a second source; it is not yet mixed into the HN detector or presented as a cross-source match.

## Data path

```text
HN API → Python → Kafka observations ─────────→ ClickHouse raw history
                       ↓                                 ↓
                  Flink SQL                    5/30/60-minute deltas
             event-time minute windows          + original evidence
                       ↓
                Kafka window results → ClickHouse story_windows_v2
```

Raw history is independent of Flink window completion. Even observations arriving after a window closes remain available for investigation. The archived fields are normalized API observations, not full original HN JSON responses.

## Start locally

Requires Python 3.9+ and Docker with Compose v2. Allocate approximately 6 GB RAM to Docker. Services use local development credentials and bind exposed ports to localhost.

On macOS, if Docker or its credential helper is missing from your terminal path:

```sh
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

```sh
docker compose up -d --build
```

Wait for a registered task manager in the [Flink dashboard](http://localhost:8081), then:

```sh
python3 scripts/pipeline.py start
python3 scripts/check_pipeline.py
```

`start` refuses to submit when another job is active or a saved restore point exists. If you previously stopped the pipeline with a savepoint, use `restore` instead. The live check waits up to five minutes for recent event-time windows.

For an existing phase-1 database, apply the additive migration once (safe to repeat):

```sh
docker compose exec -T clickhouse clickhouse-client --user pulse --password pulse-local --multiquery < infra/clickhouse/002_observations.sql
```

Fresh databases run it automatically. The old processing-time table and topic are retained for comparison; current queries use `story_windows_v2`.

## Investigate a story

Find recently observed IDs:

```sh
docker compose exec clickhouse clickhouse-client --user pulse --password pulse-local --query "SELECT story_id, argMax(title, observed_at) AS title, max(observed_at) AS latest FROM pulse.observations FINAL GROUP BY story_id ORDER BY latest DESC LIMIT 10"
```

Use one of those IDs:

```sh
python3 scripts/story_history.py 49593563 --evidence
```

The JSON includes 5/30/60-minute score and comment changes, rates per actual elapsed minute, freshness, sampling gaps, and both endpoint observations. `--evidence` adds every available sample from the last 63 minutes. `--as-of 2026-09-08T07:05:00Z` queries a historical point. Late data can revise historical query results: `--as-of` is an observation-time cutoff, not a snapshot of what the database knew then.

ClickHouse connection overrides: `CLICKHOUSE_URL`, `CLICKHOUSE_USER`, and `CLICKHOUSE_PASSWORD`.

## Meaning of the metrics

- The poller samples up to 50 new plus 50 top stories, deduplicating list overlap. Polls take time, followed by a 60-second pause. This is not complete HN coverage.
- Score and comments are cumulative snapshots. Their differences are net changes, not exact counts of new votes or comments. Decreases are preserved.
- Each horizon uses the latest sample and the most recent sample at or before its target boundary. Both endpoints must be within three minutes of their target time. Rates use actual elapsed time, which is returned explicitly.
- Missing boundary history produces null changes with `insufficient_history`; stale latest data produces `stale`. An interior gap longer than three minutes produces `sampling_gap`: endpoint changes are still returned, but intermediate acceleration is unknown. `complete` means sampling met this tolerance, not that every HN event was captured.
- Flink windows use `observed_at` (UTC collection time), not story publication or processing time. A two-minute watermark allowance handles bounded reordering. Completion waits for later observations to advance the watermark; a fully idle stream does not close its final windows on a wall-clock timer.
- Events arriving behind the watermark may be excluded from Flink windows. Raw history still stores them, and attention queries use raw history. Rebuilding a window with a different late-arrival order can yield a different result; event-time attribution alone is not universal deterministic replay.
- Delivery remains at least once. Queries use `FINAL` on `ReplacingMergeTree` to collapse immutable raw event keys and repeated window keys. Do not sum cumulative snapshots or query physical duplicate rows as logical activity.
- Story IDs are not cross-source topic identities. There is no historical anomaly baseline or Pulse Score yet.

## Find accelerating stories

```sh
python3 scripts/radar.py
python3 scripts/radar.py --format json --output .pulse/radar.json
```

The report compares approximately the last five minutes against the preceding fifteen. It runs on demand over raw history; Kafka/Flink and the ingestion service continue collecting independently. Use `--as-of` for a historical cutoff and `--limit` for the Markdown display length. JSON includes all decisions, even stories that did not qualify.

Each result links to the HN discussion, explains rate and volume changes, and includes the collection times used as evidence. Stale and incomplete stories are excluded and counted separately. An empty candidate list is a valid result.

See [detector rules and validation](docs/detector-v1.md) and the [saved live report](docs/reports/radar-snapshot.md). The initial thresholds are explicitly provisional, not learned or statistically calibrated.

For a coverage and signal-frequency check across historical cutoffs:

```sh
python3 scripts/evaluate_detector.py --lookback-minutes 60 --step-minutes 5
```

This reports available history and candidate IDs at each cutoff. It excludes future observation times but is not a point-in-time arrival-log backtest or a measure of predictive accuracy.

## Investigation API

The FastAPI service runs locally at `http://localhost:8000`. Start it against the running database with `docker compose up -d --build api`. Interactive endpoint documentation is at [localhost:8000/docs](http://localhost:8000/docs).

| Route | Purpose |
| --- | --- |
| `/health` | Database availability and recent collection freshness; stale collection returns 503 |
| `/v1/radar?limit=10` | Ranked candidates plus eligibility/exclusion counts and rules |
| `/v1/stories?limit=20&offset=0` | Recently sampled stories, including quiet ones |
| `/v1/stories/{story_id}/history` | Attention changes and raw samples over the last 63 minutes |
| `/v1/stories/{story_id}/explanation` | Candidate/quiet/excluded decision and channel-level evidence |
| `/v1/reddit/posts` | Recent Reddit submissions and their latest observed metrics |
| `/v1/reddit/posts/{post_id}/history` | Reddit's source-specific raw observations over two hours |

All `/v1` routes accept `as_of`, a timezone-aware ISO timestamp. Future or malformed cutoffs and invalid IDs/limits return 422. An unavailable observation store returns a sanitized 503. A story with no observations in the requested interval returns 404; this does not mean the story never existed. Empty rankings return 200 with coverage counts so insufficient evidence is distinguishable from quiet activity. Use `evidence=false` to omit raw samples from history responses.

The API uses the same calculation code as the CLI. Requests have bounded observation windows and run as synchronous FastAPI handlers so database reads do not block the event loop. It is read-only and bound to localhost; authentication, caching, WebSockets and public deployment are not implemented. `/health` checks collection/database freshness, not Flink checkpoint health.

## Reddit source: approval required

Reddit's current Responsible Builder Policy requires explicit approval before any API data access. It directs developers to the [Developer Platform](https://developers.reddit.com/) and says to [file a ticket](https://support.reddithelp.com/hc/en-us/requests/new) when the use case is not supported there. Pulse must not collect Reddit data until that approval is granted and the app has a registered developer profile and app-profile label.

The code and storage schema are present but the Docker collector has a mandatory approval guard. Do not set `REDDIT_ACCESS_APPROVED=yes`, add credentials, or start `reddit-ingestion` until Reddit approves the use case. The planned scope is deliberately limited to public submission-level metrics for selected subreddits; it does not store authors or post bodies, infer characteristics about users, or join Reddit users to off-platform identities. When approval arrives, copy `.env.example` to `.env`, record the approval's app-profile label, and add the approved credentials there. `.env` is ignored by Git.

The registered Devvit app is named `pulse-signal-2026`; its local source is in `integrations/reddit-devvit/`. It is a bare, buildable starting point and has not been playtested, installed in a subreddit, or submitted for review. Verify its local build with `cd integrations/reddit-devvit && npm run build`. `npm run playtest` uploads and installs the app, while `npm run publish` files an app-review request, so neither is part of the local setup.

Once approved, start collection and confirm it is receiving data:

```sh
docker compose --profile reddit up -d --build reddit-ingestion
docker compose exec clickhouse clickhouse-client --user pulse --password pulse-local --query "SELECT subreddit, count() FROM pulse.reddit_observations FINAL GROUP BY subreddit ORDER BY count() DESC"
```

The collector retains only post-level fields needed for Pulse (title, subreddit, permalink, creation time, score, comment count, and vote ratio). The raw Reddit table automatically removes observations after 30 days.

Until approval, the Reddit endpoint correctly returns no posts:

```sh
curl 'http://127.0.0.1:8000/v1/reddit/posts'
```

The Reddit routes are intentionally source-specific for now. A post ID and an HN story ID do not establish that they describe the same topic; cross-source matching needs an explicit evidence rule before it can produce combined alerts.

Run the complete suite (41 analytics tests plus 12 API tests) with Python 3.12 supplied by Docker:

```sh
docker compose run --rm --build --no-deps api-tests
```

The original `python3 -m unittest discover -s tests -v` command still runs the dependency-free analytics suite. API tests live separately under `tests/api`.

## Local frontend

The Radar and Investigate screens live in `frontend/` and connect to the local API through the same origin. Keep the Docker API running, then start the frontend:

```sh
cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. The Radar view refreshes every 30 seconds and makes empty rankings explicit. Select any recently observed story to inspect its 5/30/60-minute changes, detector explanation, charts, and original samples. Observation gaps longer than three minutes appear as chart breaks and amber evidence-table rows.

The frontend is deliberately local because its live data service runs on this Mac. It does not authenticate users, publish the data, or provide a remote deployment. Validate it with:

```sh
cd frontend
npm run build
```

## Stop and restore

Save open windows and source offsets before shutting down:

```sh
python3 scripts/pipeline.py stop
docker compose down
```

Restart services, wait for Flink readiness, and restore:

```sh
docker compose up -d
python3 scripts/pipeline.py restore
python3 scripts/pipeline.py status
```

Savepoints and checkpoints live in the `flink-state` Docker volume. The local `.pulse/savepoint.json` records the restore path and SQL checksum. Keep it and the volume. Restore refuses a changed SQL definition because state compatibility needs review.

This is a single-node development cluster, not automatic JobManager high availability. Worker failures can recover from checkpoints while the JobManager survives. After an unplanned JobManager loss, restoring the last saved point may replay newer Kafka records; inspect retained checkpoints when a more recent recovery point is needed. Kafka retains seven days of data, so recovery also depends on source offsets still being available. Do not remove Docker volumes if you want to keep history or recovery state.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_pipeline.py
python3 scripts/check_history.py
```

The history check compares a closed event-time window with raw evidence, then republishes one existing observation twice and verifies both consumer offsets, deduplication and an unchanged closed window. It creates no synthetic stories. Requires an active v2 job and completed windows.

For a direct ingestion preview without Docker or third-party Python packages:

```sh
python3 -m ingestion.hacker_news --stdout --once --limit 3
```

See `docs/phase-2-verification.md` for storage/recovery validation and `docs/detector-v1.md` for detector validation. Next: gather a longer, more varied history and evaluate which alerts were useful before tuning thresholds or introducing a Pulse Score.

## References

- [Hacker News API](https://github.com/HackerNews/API)
- [Flink Kafka SQL connector](https://nightlies.apache.org/flink/flink-docs-release-1.20/docs/connectors/table/kafka/)
- [Flink savepoints](https://nightlies.apache.org/flink/flink-docs-release-1.20/docs/ops/state/savepoints/)
- [ClickHouse Kafka engine](https://clickhouse.com/docs/engines/table-engines/integrations/kafka)
- [Reddit Data API Terms](https://redditinc.com/policies/data-api-terms)
