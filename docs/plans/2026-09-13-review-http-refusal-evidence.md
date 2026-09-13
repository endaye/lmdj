# Bounded HTTP refusal evidence for review publication

## Task

PR #1278 run `34758019629/1`, controlled by main `1ec4b829`, failed
before producing `scope.json` with `category=http-error status=403`.
The status alone cannot distinguish permission refusal from rate limiting.
Do not attribute that historical failure to either cause without evidence.

Declared files:

- `scripts/ci/review_pipeline.py`
- `tests/build/ci_review_pipeline_test.py`
- `docs/plans/2026-09-13-review-http-refusal-evidence.md`

Add diagnostic-only projection for HTTP 403/429: a closed endpoint category,
three allowlisted decimal rate-limit headers, and a closed reason derived from
at most 4096 bytes of complete JSON. Unknown, oversized, malformed, consumed or
unreadable bodies remain unknown. Never output response text, arbitrary header
values, URLs, credentials, exception messages or dynamic class names. The
shared write adapter may already consume its body; do not reconstruct it.
No retries, token/permission changes, new requests, provider calls or relaxed
review eligibility. Preserve the original nonzero exit and known refusals.

GitHub documents the diagnostic distinctions in its official
[REST troubleshooting guide](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api)
and [rate limits guide](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
Hints are not authorization or proof of review publication.

## Verification

Baseline: `python3 tests/build/ci_review_pipeline_test.py` discovered 46 tests,
45 passed and the existing opt-in provider integration skipped, exit 0.
Add focused CLI regressions through the real API exception wrapper before
implementation: primary limit, secondary limit, integration permission,
secret-bearing headers/body/URL, bounded malformed/oversized/unreadable bodies,
and non-publisher isolation. Run the complete same suite and staged ownership
suite before commit. No new CI gate or timeout change.

Historical GitHub response headers/body are not retained; these tests do not
recover them or prove a live 403 repair. A future trusted-control review must
exercise the new diagnostic before that external distinction is established.

Observed local verification:

- Focused pre-fix primary-limit regression: exit 1, expected
  `reason=primary-rate-limit` absent from the actual CLI error wrapper output.
- Final publisher suite: 54 discovered, 53 passed, one existing opt-in provider
  integration skipped, 3.979 seconds, exit 0. Includes non-publisher and
  non-refusal HTTP isolation, and an actual 4097-byte read overflow assertion.
- `git diff --check`: exit 0.
- Staged path ownership and top-level admission: 74/74, 5.719 seconds, exit 0.

## Version Management

Version impact: none

Reason: internal CI diagnostics only; no Product Assembly, public API,
Contract, Provider or model identity changes. No release is initiated.

## Documentation Impact

Documentation impact: none

Reason: no Portal-documented command, workflow, release state or product fact
changes; this Task only enriches the existing internal failure diagnostic.

Pitfall disposition: the lost diagnostic fields are fully expressed by the
focused regression tests; no new process-ledger entry is required. Preserve
the failed run and do not turn an inability to classify into success.
