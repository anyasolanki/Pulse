# Raw history and attention changes

Verified locally on 2026-09-08 UTC, using real Hacker News data.

## Implemented

- A separate Kafka consumer archives normalized observations into `pulse.observations`. Queries deduplicate immutable event IDs using `FINAL`.
- Flink v2 groups by UTC collection time with a two-minute watermark allowance. Versioned output preserves the phase-1 results.
- `scripts/story_history.py` returns 5/30/60-minute net score and comment changes, elapsed-time rates, explicit data-quality status, endpoint evidence and optional full sample history.
- Persistent checkpoint/savepoint storage and guarded `start`, `stop`, `restore`, and `status` commands.

## Evidence

- Fifteen unit tests passed, including all three horizons, duplicate observations, decreasing counts, stale data, missing history, numeric JSON strings, boundary selection and interior sampling gaps.
- The live history check passed: a historical Flink window matched the timestamps, maxima and distinct count in raw history.
- Re-published one existing immutable observation twice through Kafka, waited until both raw and Flink consumers committed past those exact offsets, and verified one logical raw event and an unchanged closed window.
- Stopped job `1e100f96629bfef85320554cac7f527f` with a savepoint, restarted both JobManager and TaskManager, then restored as job `1b0a088d46cc8a1d17a6bc35ecf3951b`.
- Flink's checkpoint API reported `is_savepoint: true`, the saved path, three newly completed checkpoints and zero failed checkpoints after restore.
- Compared 1,325 completed event-time windows against raw history after recovery: zero aggregate/count mismatches. Latest window at that check was 07:06 UTC.
- The final live pipeline check passed with 290 recent event-time windows.

Example live query at 07:05 UTC for story `49593563` returned 13 observations. Its five-minute view showed score growth of 1 and comment growth of 0 across 5.101 actual sampled minutes. Thirty- and sixty-minute views reported `insufficient_history`, not invented zeros. Unit fixtures verify those longer calculations without claiming an hour of live collection.

## Repeating the restart check

With a running v2 job:

```sh
python3 scripts/pipeline.py stop
docker compose restart jobmanager taskmanager
```

Wait until the task manager registers, then:

```sh
python3 scripts/pipeline.py restore
python3 scripts/pipeline.py status
python3 scripts/check_pipeline.py
python3 scripts/check_history.py
```

The Flink dashboard's checkpoint view should identify a restored savepoint and new successful checkpoints.

## Limits

This verifies a controlled stop/restore and duplicate replay, not automatic recovery from every failure. No throughput benchmark, anomaly model, hour-long live validation, or full-source coverage is claimed. Late observations remain in raw history but may miss finalized Flink windows. The attention calculation therefore uses raw evidence directly. Kafka source retention and preserving the local state volume remain prerequisites for recovery.
