# Collection review and API milestone

Reviewed on 2026-09-09 UTC after approximately 23 hours of elapsed collection time.

## History and continuity

At the initial check, ClickHouse held 64,435 logical observations across 1,169 stories, spanning 2026-09-08 06:48:32 UTC through 2026-09-09 05:40:42 UTC. The collector was active and data was current.

There were 17 collection-wide gaps longer than three minutes. The largest was 3,962 seconds (66 minutes), from 12:42:20 to 13:48:22 UTC on September 8. Other large gaps were 3,931, 3,179, 3,060 and 2,925 seconds. These are intervals with no observations across any story, not a per-story sampling analysis. The data alone does not establish whether sleep, connectivity or source delays caused them. Container uptime does not prove continuous collection.

The current scan at review time had 106 stories, zero eligible and zero candidates: 99 lacked baseline history and seven were stale. Coverage states were retained; thresholds were not relaxed.

## Historical signals

The historical evaluation examined 272 cutoffs and found 25 distinct candidate stories. This measures signal frequency, not predictive accuracy; no future-outcome labels were used.

Inspected example: story 49605915, “Navier-Stokes – Tristan Buckmaster [pdf]”, at 2026-09-08 07:18:32 UTC:

- Six net comments over about 5.2 minutes, versus two over the preceding 15.4 minutes.
- The reported multiple was 5.80 against the minimum baseline rate, explicitly identified as a floor rather than the raw previous rate.
- Approximately 5.3 comments above the baseline expectation.
- Largest sample gap was 79 seconds.

The supporting endpoint samples were collected at 06:57:38, 07:12:59 and 07:18:09 UTC. The calculation was consistent with this evidence; this does not establish future virality.

## API

Added read-only endpoints for collection health, recent stories, radar candidates, attention history and detector explanations. Historical requests use observation-time cutoffs. API results use the same analytics as the CLI and retain stale/missing-history states. Database failures return 503 without exposing connection details.

The test suite includes 41 existing analytics tests and 12 API tests covering real routing, validation, evidence, missing intervals, empty radar results, sanitized database errors, pagination and health freshness. Live endpoint verification is performed against the running ClickHouse instance.

All 53 tests passed. Live requests to `/health`, `/v1/stories`, `/v1/radar`, historical story history, historical explanation and `/openapi.json` returned 200. The historical explanation reproduced the six-comment candidate. By the final live check, the radar had recovered to 92 eligible stories out of 107, with no current candidates; eight were stale and seven lacked sufficient history. This demonstrates why eligibility counts must accompany an empty ranking.
