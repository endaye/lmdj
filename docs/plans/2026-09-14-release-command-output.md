# Bounded command output for release recovery receipts

Delivery base: c27a2512cbac8e6a7d79897ad8b66b4d27a9c9b3.

## Task

The retained-source witness verifier emits an actual JSON receipt, but the
existing release command executor returns only exit code, digest and length.
Add an opt-in bounded byte capture using the same subprocess execution path.
Return the complete original combined stdout/stderr only when it fits the
caller's limit; overflow returns no bytes, never a parseable truncated prefix.
Always return the actual exit code and whole-stream digest/length after normal
termination, including nonzero exits and overflow. Existing callers keep their
three-field result and never capture raw output.

The maximum requested capture is 65536 bytes. Reject invalid budgets before
launch. Preserve scrubbed environment, inherited writer lock, process-group
timeout handling and no automatic retries. Raw output is private in-memory
data, not a validated receipt: the consuming controller must check exit,
absence of overflow, schema, exact identity, authorization, live files and
durable state before recording success. This adds no public CLI or journal
schema, no authentication, no witness generation and no new release authority.
The temporary output spool is unchanged and is not a new disk-usage quota.

## Declared files

- tools/release/task_verification.py
- tests/build/release_command_output_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-14-release-command-output.md

## Verification

New real-subprocess contract tests cover complete binary stdout/stderr,
nonzero exit, exact limit, empty output, overflow with full digest, invalid
budgets before launch, legacy return shape, environment isolation, inherited
writer descriptor, invalid writer before launch and process-group timeout.
Run the unchanged publication Task verifier regression population as the
companion durable intent, crash/orphan lock and no-replay proof. Register the
new tests with a 30-second CTest budget before running them; retain the
existing Task verifier's 60-second budget. Run both through CTest as well as
directly, staged ownership, Portal check and rendered-page assertions.

The complete witness journey remains generation intent -> official generation
-> official verifier's emitted receipt -> durable binding -> cold recovery
without regeneration -> witness Task/PR -> fresh-clone verification. This Task
only delivers the byte-capture prerequisite; it does not claim that journey,
candidate completion, remote integration, signing or unattended release.
Retain every failed iteration. Obtain independent current-head review and
commit the five declared files; keep the dependent stack local while the
upstream owner-adoption boundary remains unresolved.

### Executed evidence

- Before implementation, the new suite executed 12 cases: the legacy case
  passed and the capture cases refused because the method did not yet exist
  (18 errors including invalid-limit subtests), exit 1. This is a missing
  interface baseline, not a discovered defect in the old digest-only contract:
  /tmp/lmdj-command-output-red-v1.log.
- New real-process tests passed 12/12, 0.375s, exit 0:
  /tmp/lmdj-command-output-tests-v1.log. The unchanged existing Task verifier
  tests passed 25/25, 27.911s, exit 0:
  /tmp/lmdj-command-output-regression-v1.log. No tests were skipped.
- Configured CTest selected exactly both groups and ran them with Python
  3.14.7: 2/2 groups, 37 child cases, zero skipped, 32.91s, exit 0;
  existing Task tests took 31.969s, new capture tests 0.514s. Original 60s and
  predeclared new 30s budgets were unchanged:
  /tmp/lmdj-command-output-ctest-v1.log. Configuration separately exited 0:
  /tmp/lmdj-command-output-config-v1.log.
- Staged ownership passed 74/74, 5.572s, exit 0:
  /tmp/lmdj-command-output-scope-v1.log. Locked Node 22 installation exited 0:
  /tmp/lmdj-command-output-deps-v1.log. All tracked symlinks were checked as
  actual filesystem symlinks; no checkout repair was needed.
- Node 22 `scripts/docs-site.sh check` passed 170/170 tests, zero skipped
  (41.012s test population), production build, all 47 routes/internal links,
  exit 0: /tmp/lmdj-command-output-docs-v1.log. Four assertions against the
  actual generated operations HTML passed, exit 0:
  /tmp/lmdj-command-output-rendered-v1.log. No implementation or Portal source
  changed after these checks; only this evidence record was completed.
- Independent complete five-file review found no actionable finding and
  independently executed the new tests: 12/12, 0.385s, exit 0. It confirmed the
  subprocess environment, inherited lock, process group and timeout block is
  unchanged and raw output capture is not a durable witness success claim.
- Pitfall disposition: the new byte-capture contract is directly expressed by
  its regression tests; no new process-only recurrence was found. No remote
  action, provider call, auth/key/Environment change or release was performed.

## Version Management

Version impact: none. Internal release execution plumbing only; no Product,
Assembly, Module, Provider, Host, Contract, Build or snapshot identity changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
