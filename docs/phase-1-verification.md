# First local pipeline verification

Verified on 2026-09-08 UTC (2026-09-07 evening in Los Angeles), on an Apple silicon Mac with Docker Desktop 4.90.0.

## Observed results

- Compose configuration validation passed and all service images built.
- Kafka initialized both topics; the Python container published real Hacker News observations.
- Flink accepted job `d99d85f6b8d2769b9d25e10e328a8816`; its status was `RUNNING`.
- `python3 scripts/check_pipeline.py` passed with 96 recent story windows in ClickHouse.
- Queries returned one-minute aggregates containing real story titles, scores and comment totals.
- Successive windows arrived: 96 story rows at 06:54 UTC and 21 at 06:55 UTC, confirming continued processing after the initial backlog.
- All five ingestion unit tests passed.

The SQL client initially bypassed Flink's Docker entrypoint, so its cluster settings were never applied. Keeping the image entrypoint and passing the SQL client as the command fixed submission.

## Scope of this check

This proves the live API → Python → Kafka → Flink → Kafka → ClickHouse path on one machine. It does not establish throughput, detection quality, exactly-once delivery or recovery after full shutdown. The first processing-time window includes the observations accumulated before job submission and is not a one-minute measure of internet activity.

## Repeat

With Docker and the existing Flink job running:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_pipeline.py
```

See the README for startup and job submission after a full shutdown. Do not submit a second copy while the job is running.
