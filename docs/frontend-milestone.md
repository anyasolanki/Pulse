# Radar and Investigate frontend

Pulse now has a local working interface over the existing read-only API.

## Radar

- Shows live collection state, a timestamped radar snapshot, and the sampled-story/eligible/candidate counts.
- Lists qualifying signals with the channel, recent increase, rate multiple, and whether a baseline floor was used.
- Keeps an empty radar honest: it explains whether stories are quiet or still collecting usable history.
- Lists recently observed stories even when none are accelerating.
- Shows exclusion categories such as stale data and insufficient history.

## Investigate

- Preserves the selected radar cutoff in the URL so the investigation uses the same historical evidence as the radar view.
- Shows cumulative HN score and comment charts over the available 63-minute history.
- Breaks lines across collection gaps longer than three minutes and marks them in amber instead of drawing artificial continuity.
- Provides 5/30/60-minute net changes, sampling status, detector-channel results, and the original observation table.
- Links to the corresponding Hacker News discussion.

## Local-only scope

The browser calls a local frontend proxy, which calls the existing local API. No database credentials are exposed to the browser. The prototype remains local because the data pipeline is local. A later remote product needs an API accessible from the hosted frontend, configuration for its allowed origin, and an explicit decision about user access.

## Validation

- TypeScript check passed.
- Production frontend build passed.
- The root route and an Investigate URL for historical story 49605915 returned 200 locally.
- The evidence endpoint returned the real “Navier-Stokes – Tristan Buckmaster [pdf]” history with 24 observations for the selected historical cutoff.
