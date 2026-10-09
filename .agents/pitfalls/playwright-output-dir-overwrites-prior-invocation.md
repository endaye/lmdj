---
id: playwright-output-dir-overwrites-prior-invocation
area: web-host
status: absorbed
recurrences:
  - date: 2026-10-09
    occurrence: https://github.com/endaye/lmdj/pull/1910
    observed_by: Codex (GPT-6)
exit: gate:apps/web-runtime-host/test/package_test.py
---

# Playwright clears outputDir for each invocation, so a later passing project can erase an earlier project's failure traces.

## Why

The Host proof ran Chromium and WebKit consecutively with the shared default
output directory. WebKit cleared the failed Chromium Candidate traces before
the CI action could upload them. This is upstream runner cleanup behavior,
not evidence that the earlier failure was resolved. A shim that implements
its own cleanup cannot prove the locked runner's behavior.

## How to apply

Give each proof invocation a distinct `LMDJ_WEB_RESULTS_SLOT` below the
existing uploaded result tree. Rerun
`PackageTest.test_proof_retains_each_invocations_evidence_after_webkit` when
changing the Host invocations, shared outputDir mapping or Playwright lock.
The gate runs the locked real CLI and production config, retains all three
invocations' bytes and the unchanged failure trace, and preserves a failing
exit after WebKit passes. Its browser-free fixture is a retention oracle,
not browser, audio or product acceptance.
