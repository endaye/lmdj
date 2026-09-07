# T1 — Commit-bound test scope records

Implements the internal scope protocol from the 2026-09-08 incremental batch
design. No workflow trigger, merge protection, publication or production test
entry point changes in this Task.

## Declared files

- `scripts/ci/test_scope.py`
- `scripts/ci/test_scope_policy.json`
- `tests/build/ci_test_scope_test.py`
- This implementation record.

## Behavior and consumer audit

The canonical change classifier remains the routing authority. Suite expansion
uses the complete self-test inventory's `origin.scope_lane` mapping, including
the non-lane stress suites for full selection. No duplicate lane/job list is
introduced. Core execution changes add Web/Creator and stress consumers; Web
toolchain and runtime changes add the host callers. Shared foundation, Facade
and audio concurrency changes are full. Existing canonical full rules remain.

The only documentation exemption is a Markdown file in an explicit explanatory
directory whose canonical routing has no consumer beyond docs_static and no
full reason. Existing documented-input consumer rules override the exemption.
The canonical document-read-site parity gate remains required. A new consumer
must update canonical routing; a suffix alone cannot grant none.

Selection always unions deterministic floor and valid AI suggestions. Strict
records bind complete paths, policy digest, exact PR/head/base/control identity,
backend and run/attempt. All validations recompute the same selection functions.
Digest consistency is not authentication: T2/T3 must independently verify writer,
workflow/run, actual Git path digest and PR-to-main mapping. A record is not a
release verdict. Policy snapshot reads must use trusted historical data, never
execute historical Python code. Missing snapshots select current full.
When policies differ, compute dependency closure over the union of all applicable
dependency edges after combining selections. Closing each policy separately can
miss current consumers of a suite selected only by an older policy. The two
cross-policy regressions were observed red before this implementation fix.

First-parent history uses real Git, each commit versus its first parent, and a
path union that retains rename/delete/revert changes. Missing, shallow or
non-first-parent baseline history blocks instead of claiming an empty interval.
This library does not fetch history or perform GitHub pagination; callers own
those external boundaries and must not mark incomplete input complete.

## Verification

Lowest tier: Python contract tests plus actual temporary Git repositories.

- `python3 tests/build/ci_test_scope_test.py`
- `python3 tests/build/ci_change_scope_test.py` after staging new paths
- `python3 tests/build/ci_self_test_test.py`
- `python3 tests/build/ci_classification_inputs_test.py`
- `git diff --cached --check`

The new gates detect scope subtraction, stale/forged/inconsistent records,
missing interval changes and canonical consumer loss. Rejections name why and
remedy. No coverage floor, suite budget or test assertion is reduced.
Remote publisher authentication, scheduler recovery and real platform journeys
remain T2–O1 acceptance gaps, not passes claimed by these pure contracts.

Pitfall impact: none. Existing open CI and mandatory shipping pitfalls inspected;
this Task prevents known classes without asserting a new historical recurrence.

## Documentation Impact

Documentation impact: none

Reason: Internal unused CI protocol and its Task record only; no current Portal
page, active identity, Product Assembly or runtime behavior changes.

## Version Management

Version impact: none

Reason: The v1 schema is CI-internal, not a Product or cross-language Contract;
no build allocation, tag, Release, deployment or Channel promotion occurs.
