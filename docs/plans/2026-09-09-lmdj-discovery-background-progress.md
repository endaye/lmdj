# Distinguish bounded discovery progress from unresolved evidence

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).

## Task and observed evidence

Run `34257998450/1` completed its control and report steps, but discovery and
the final unresolved-status step exited nonzero. The existing CLI returns 1
both for genuine evidence problems and for an otherwise healthy unfinished
metadata round or later inventory window. Its status details only enter the
step summary, so the log alone cannot determine which category occurred in
that historical run. Do not claim its exact cause was ordinary backlog.

Add an explicit automatic-only `--background` CLI mode. A successfully
persisted bounded round with only pending work returns 0 in this mode, while
retaining the original `incomplete` report and a `pending` diagnostic. Default
manual behavior remains strict: incomplete discovery returns 1. Exact-attempt
manual requests cannot use background mode. Inventory errors/gaps, metadata
errors, unresolved authenticated evidence, retention loss, malformed state and
exceptions remain nonzero in every mode. No test scope, timeout, retry budget,
journal identity or outbox behavior changes.

Print a bounded diagnostic containing finite status and numeric counters,
never provider text, URLs, raw exceptions or credentials. This is observation
progress, not product health, complete review coverage, Issue delivery or
release evidence. Preserve durable obligations and the existing independent
report failure gate. Enable the flag only in the automatic discovery step.

Declared files:

- `scripts/ci/review_discovery_runtime.py`
- `tests/build/ci_review_discovery_runtime_test.py`
- `tests/build/ci_review_discovery_workflow_test.py`
- `tests/build/ci_incremental_cutover_workflow_test.py`
- `.github/workflows/self-test-report.yml`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- This plan.

## Verification and acceptance

Reproduce healthy incomplete discovery with the real reducer, journal and
runtime HTTP fixture before implementing the new diagnostic. Exercise the CLI
on that actual result, preserved manual nonzero behavior, every genuine error
category, invalid summaries, sanitized exception paths and actual automatic
workflow arguments. Retain fresh-process scan recovery, source authentication,
unknown POST and no-product-execution tests. Run complete CI contract discovery,
staged ownership, Portal check and final committed-range/PR declarations.

After merge inspect an exact-main log for the new diagnostic and distinguish
pending from blocked; the old nonzero log does not prove the new branch ran.
The already-dispatched manual outbox run `34263950671/1` and active batch
`34256523536/1` remain independent live acceptance work. Do not restart either
because polling took time. Full test→persist→Issue→external repair→revalidation
and version/canary delivery remain open under the overall plan.

## Version Management

Version impact: none
Reason: internal discovery progress/exit reporting only; no version, Assembly
or snapshot identity change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Reason: explain background progress versus strict manual discovery and genuine
errors. No existing Core/Assembly source diagram depicts this control flow.
