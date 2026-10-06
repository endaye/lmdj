# P1 Creator Proof runtime

## Task and declared files

Current protected Main `a33ed4c9609f226ae4a4b9d92356b916b8af5b53` has
15 passing selected suites in run `37371804087`, attempt 1. Creator exceeded
its unchanged 35-minute job limit after 1,079 UI cases and the first Chromium
group (72 passed, two capability skips). The remaining browser groups were
not completed. Retain that cancellation; it is not a passing whole Proof.

This Task changes only:

- `scripts/creator-web.sh`
- `tests/platform/web/playwright.config.mjs` (result-directory comment)
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- this plan

## Behavior and verification

Partition the existing Git tracked general browser specs into disjoint groups.
Chromium specs with independent browser contexts use two Playwright workers,
with serial execution inside each spec. The Sound Set and default-streaming
specs both mutate the one owned Catalog upstream file, so they run together
with one worker after the independent group. WebKit still receives the full
original general spec list. All existing Sample Editor, Capture, denied
permission and capability groups remain serial. Give the added invocation its
own result directory so it cannot destroy another group's failure evidence.

The defect is that serial execution of independent browser journeys exhausts
the job budget before the remaining required journeys run. No timeout,
assertion, journey leg, capability boundary, clean rebuild or selected test is
removed or weakened. The partition refuses missing Catalog specs or an empty
independent group: passing no positional specs to Playwright would select
unrelated tests instead of the intended group. No other new check is introduced.

Lowest-tier checks: shell syntax, the existing owned-server contract suite,
complete tracked spec partition/inventory equality and staged ownership.
Run the Portal check before committing. Run the original complete Creator
Proof on the clean committed head, preserving all original output and exit
status. Run every canonically selected batch-only lane before shipping, then
current-head review and protected squash. A green local Proof does not prove
the remote CI job meets its budget; verify the integrated protected-Main job
separately before recording whole-CI success.

This Task allocates no Build and performs no release or deployment. Subsequent
P1 version settlement and physical/device acceptance remain separate.

## Version Management

Version impact: none. Only Proof scheduling and its documentation change;
Product, Module, Host, Provider and Contract identities remain unchanged.

Documentation impact: required
Affected portal page: `/operations/testing-and-proof/`
Update the current Proof scheduling description; historical snapshots remain
immutable.
