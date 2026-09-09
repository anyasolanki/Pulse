# HN acceleration detector v1

This detector ranks accelerating stories within Pulse's bounded Hacker News sample. It does not claim internet-wide emergence, statistical anomaly significance, or future virality. The baseline is a story's preceding fifteen minutes of observed activity, not a population model.

## Window selection and eligibility

At a requested cutoff, select three snapshots: the latest at or before the cutoff, the latest at or before five minutes earlier, and the latest at or before twenty minutes earlier. Baseline and recent intervals share one endpoint; their changes do not overlap.

- Every endpoint must be within two minutes of its target.
- No internal observation gap may exceed three minutes.
- Require at least eight baseline samples and three recent samples, including endpoints.
- A new story without twenty minutes of sampled history is excluded. This version intentionally cannot detect a breakout immediately on first discovery.
- Future samples are ignored. Identical immutable event IDs are deduplicated.
- Rates divide endpoint differences by actual elapsed minutes, not nominal durations.
- Any observed counter decrease disqualifies that channel for this comparison. The other channel can still qualify. These are net score/comment changes, not individual vote/comment events.

## Initial rules

Each channel must satisfy every rule below. At least one channel must qualify for a story to enter the candidate list.

| Rule | Comments | HN score |
| --- | ---: | ---: |
| Minimum recent net increase | 5 | 10 |
| Minimum growth-rate multiple | 2× | 2× |
| Minimum excess above baseline expectation | 3 | 5 |
| Baseline rate floor per minute | 0.2 | 0.5 |

The rate multiple is `recent_rate / max(baseline_rate, floor)`. This avoids infinite ratios for a zero baseline. The report explicitly identifies when a floor is used.

Expected recent change is `max(0, baseline_rate) × actual_recent_minutes`. Excess is recent change minus that expectation. Requiring both volume and excess prevents a tiny-count jump from qualifying solely on its ratio.

These are starting engineering thresholds, not evidence of optimal performance. They are versioned in `analytics/detector.py`; changes that alter behavior should receive a new detector version.

## Ordering

For each qualifying channel, calculate `excess_change / minimum_recent_increase`. A story's ordering value is the larger of its qualifying channel values. Sort descending, breaking ties by ascending story ID. This puts more substantial excess growth first without treating score and comments as independent source confirmation.

The internal `priority` is an ordering aid, not a probability, percentile, rating, or Pulse Score. Both channels and their thresholds remain visible in JSON, including reasons why a channel did not qualify.

## Live verification on 2026-09-08 UTC

- All 41 tests passed. Coverage includes known acceleration, steady high-volume stories, zero-to-one jumps, zero baselines, exact threshold edges, counter decreases, insufficient history, stale data, gaps, sparse samples, deterministic ranking, duplicate replay and future-sample exclusion.
- The first live scan at 07:14:54 UTC evaluated 101 stories: 91 eligible, 7 without enough history, 3 stale, and zero candidates.
- The saved report at approximately 07:16:37 UTC evaluated 101 stories: 90 eligible, 7 without enough history, 4 stale, and zero candidates.
- Historical evaluation at 07:08:32, 07:13:32 and 07:16:20 UTC produced zero candidates. Eligible populations were 1, 90 and 90 respectively as the collection warmed up.
- The original story-history command was checked against live data after sharing the ClickHouse reader.

The live data did not contain a qualifying acceleration in these checks. Positive detection and ranking are verified with explicitly synthetic unit fixtures, not presented as live discoveries. No thresholds were relaxed to populate the report.

## What is still unknown

Roughly half an hour of one-source data is insufficient to measure useful-alert rates or calibrate a score. The new/top sampling policy can miss stories, and entering or leaving the sample affects eligibility. Queries at historical observation-time cutoffs may include data that arrived later; an ingestion-arrival log would be needed for a strict historical knowledge cutoff.

Next evaluation should use longer collection, inspect candidate evidence, and define an explicit future outcome before claiming predictive precision or recall. Preserve the distinction between accelerating now and predicting a later breakout.
