# PR-Agent production review quality retrospective (2026-10-10)

Task: LMDJ #1154 item 4 / umbrella #1149. Owner confirmed the sampling
criteria in the #1154 thread on 2026-10-10 before statistics began.

## Window and denominator (frozen before counting)

- **Window**: 2026-10-09T16:25Z (first production review after the reliability
  repair chain #1912/#1916/#1927 was live) through 2026-10-10T03:35Z.
- **Denominator**: window runs of the `PR Review` workflow with an actual
  engine call, identified by the retained `pr-review-diagnostics-*` artifact's
  `t2-result.json` — 41 runs. Runs that made no model call (49: reruns of
  already-reviewed heads, merge-map passes, draft/docs skips) are reported
  separately and count neither as effective reviews nor as failures.
  Cancelled/superseded runs are listed under observability evidence in the
  issue thread, not in the denominator.
- Earlier failure periods (DeepSeek balance outage, GLM identity defect) are
  historical contrast only and are excluded from production quality ratios by
  the confirmed criteria.

## Results

**Effective review rate.** 39 of 41 engine-reviewed runs published a verified
`lmdj-review-v2` marker at the exact head (95.1%). The two exceptions, both
retained and explained: run 37971385452 completed a GLM review during the
fault-injection leg but was rejected by the pre-fix error-class mapping (the
defect repaired by #1939 and re-proven by run 38016455358); run 38015219256's
publisher correctly refused a stale head after #1952 moved mid-run (the
newer head was reviewed separately).

**Fallback recovery.** 7 runs saw the primary DeepSeek attempt fail first;
GLM recovered and reviewed in all 7 (100%). Split per the criteria: 4 natural
provider-side failures (37987686360, 37995977265, 38014990336 with
invalid_output model variance, and 38015219256 with a transient internal_error)
and 3 controlled fault-injection runs with the unroutable DeepSeek endpoint
(37971385452 in the first injection window, 38016019416 and 38016455358 in the
second), reported separately from natural results.

**Latency and queueing.** Across the 41 runs: execution p50 96 s, p95 226 s,
max 731 s; 40/41 completed within 10 minutes of execution start (the 731 s
outlier is a 475K-token review). GitHub-side queue p50 0 s, p95 0 s, with one
941 s outlier under multi-review contention.

**Tokens and cost.** Prompt sizes min 2,278 / median ~113K / max 735,004
tokens. Host ledger for the window: 60 provider requests (49 DeepSeek, 11
GLM), reconciled actual USD 3.45; 12 uncertain records are failed/unpriced
requests with zero confirmed spend. Lifetime ledger actual: USD 39.84 against
the USD 100 caps.

**Review quality.** 30 inline bot findings across the window's reviewed PRs,
30/30 resolved (author fix or verified repair-recheck). Spot-checked findings
are specific and code-anchored (unmount cleanup, prop/state initialization,
error-masking order). False positives: none observed as owner-rejected;
"all findings resolved" is author-acknowledgment evidence, not independent
proof of correctness — this limitation is recorded, not smoothed over.
False negatives: no judgeable instance in the window; the window is ~12 hours
and the method cannot prove absence, recorded as insufficient-sample honesty
per the confirmed criteria.

## Historical contrast (excluded from ratios)

Pre-repair October: GLM 53/53 requests failed on the identity binding defect;
DeepSeek failed with HTTP 402 from 2026-10-08T16:13Z until the owner restored
balance; 14% of runs finalized not-reviewed. These failures produced the repair
chain and are retained in the operations record and run artifacts.

## Evidence

Run-level receipts live in the retained run artifacts (`pr-review-result-*`,
`pr-review-diagnostics-*`) and the host monetary ledger; the measurement,
observability-path and rollback evidence is in
`docs/quality/2026-09-10-pr-agent-netcup-operations.md` and the #1153/#1154
issue threads. Statistics were computed read-only from those receipts.
