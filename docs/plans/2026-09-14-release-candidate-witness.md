# Durable retained-source candidate witness execution

Delivery base: 119bfb3f85b22e6fe11d44cbfd74778055657d1d.

## Task

Implement one registered witness generation followed only by bounded official
verification. Require the concrete source/cut verifier and preserve its writer
lock throughout verification, enrollment and child execution. Authenticate
original request, source/cut/frozen input identities and actual squash on
freshly observed main. The trusted caller owns main observation, original
authority, control/toolchain and current-head Task review. A later main may
advance without changing the frozen squash target.

Before generation persist a separate operation marker and command intent. An
unknown/failed generation is never replayed. Missing state after enrollment
fails closed. Existing artifacts are verified rather than overwritten. Every
command persists its actual exit/output digest/length; successful verification
also retains the exact bounded output bytes and validates the emitted JSON
against live canonical artifact identities. Never synthesize a positive
verifier output from reconstructed metadata. Failed/unknown attempts remain
in history; verification attempts have a fixed 1..3 budget. Corrupt state,
scope drift, writer/authority loss, dirty source or output drift stop execution.

The cut HEAD/index/tracked bytes do not move. The only additional untracked
artifact allowed is the canonical witness path for this Build. Metadata and
witness reads are no-follow, regular single-link files with a 64 MiB bound,
matching the standalone retained-source verifier's artifact bound. The source
verification lock seam accepts only the workspace's currently active journal;
the ordinary passive verifier continues to acquire its own lock.

## Declared files

- tools/release/candidate_source.py
- tools/release/candidate_witness.py
- tests/build/release_candidate_witness_test.py
- tests/build/release_candidate_source_test.py
- tests/build/release_candidate_portal_journey.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-14-release-candidate-witness.md

## Verification

Use actual temporary Git source/material/snapshot/cut journals and distinct
one-parent squash commits. The snapshot fixture is intentionally minimal and
not a complete Portal snapshot. Copy the unchanged official witness producer,
verifier and library into that fixture before freezing its baseline. Its
snapshot-only shell seam must not replace witness semantics. Assert actual
emitted output bytes, live artifact digest/length, unchanged Git source and
cold controller recovery; inject process death before/after command receipts,
generation failure, bounded retry exhaustion, state/authority/file drift,
malformed/overflow output, and an alien/closed verifier lock.

Register lifecycle, state, boundary and actual-output groups with 120-second per-group
budgets before the first run: these tests execute the concrete Git proof and
live command-boundary guards, not a stub verifier. Existing source groups retain
their 30-second budgets. Run the unchanged source tests, new tests through
CTest, standalone official Node witness tests, staged ownership, full Portal
check and actual rendered-page assertions. Obtain independent exact-head
review and commit only declared files. No provider retries or dependent-stack
push while upstream owner adoption remains unresolved.

The complete journey remains source/snapshot/cut -> protected squash ->
witness generation -> emitted verification receipt -> durable cold recovery
-> reviewed witness PR -> source-absent fresh-clone full Portal proof. This
Task delivers the local witness runner, not the witness PR, production parent
factory, complete CI/intent, signing or release/Site
acceptance. These remain required; do not report candidate/release completion.

The schema-only parser group has a separate predeclared 30-second budget.
Reject integer/float scope and receipt substitutions by exact canonical bytes
and closed field types. Reserve the whole bounded command/output history
before enrollment, including repeated argument vectors and base64 expansion.

Extend and run the existing retained full Portal rehearsal separately from
recursive CTest/npm suites. Preserve its real source -> official snapshot ->
cut (both actual Task gate phases) -> actual one-parent squash -> source-absent
fresh clone. Replace the direct witness command with this concrete runner and
an independently reconstructed runner's cold resume. Verify actual retained
commands, unchanged source HEAD/refs/raw index and identical witness identities
before transferring the exact output bytes and running full Portal in the
source-absent clone. Record dirty control-module hashes alongside the control
base; this is not an exact committed-control run. Use a new evidence directory,
never change or overwrite the previous retained rehearsal. This closes the
local full-snapshot/runner/fresh-clone seam, not live main authorization,
reviewed witness PR, trusted production factories or end-to-end release.

### In-lock proof reuse

The first CTest lifecycle group timed out at its unchanged 120-second budget.
A real profile of the exact two-run lifecycle showed 11 full source verifier
calls consuming 29.388s of 33.743s spent inside the two witness runs; 2239
subprocess.run calls across the whole fixture consumed 54.560s. The profile
itself passed its one test in 58.851s. This establishes duplicated proof work,
not an assertion that machine load alone caused the timeout.

Reconstruct the full immutable source/cut/squash proof once per acquired writer
and per run. Every boundary still checks the exact four durable source/snapshot
bindings before and after callbacks, original authority, snapshot authority,
source/cut/squash commit identity and presence, fresh main ancestry, source
retention, raw tracked files, branch/index and allowed untracked inventory.
No in-memory proof is reused across lock release or cold resume. Git objects
remain immutable under the same trusted object-store assumption as the source
verifier; this is not an object-store corruption scrub. Regression tests mutate
a durable cut binding and main ancestry between commands and require refusal.
No timeout, population or journey leg was reduced to address this failure.
Keep the initial failed CTest and profile alongside final verification.

The next complete CTest run passed all 23 new witness cases, but the unchanged
source-projection group timed out at 29.97s (no case output). Its separate real
Python 3.14 profile passed 3/3 in 29.246s: three repeated cut preparations cost
7.477s, while four actual source proofs cost 9.661s. Preserve the 30s budget
and every source assertion. The source-consumer fixture now produces its real
completed cut once before the existing independent full-state copies per
case; all private paths, bindings, object identities and journals remain the
actual producer's bytes. The source verifier still executes separately in
every test, including all parent/squash mutations. Cut producer tests remain
unchanged. Add verbose output to locate any subsequent failure; do not claim
timing variability alone was diagnosed or that either old red was a pass.

The third complete CTest run also failed: source projection timed out at
30.46s after two cases reported success; source binding passed 3/3 in 28.446s,
and all 23 witness cases passed. Preserve
`/tmp/lmdj-candidate-witness-ctest-v3.log` (exit 8, total 296.43s). The separate
post-fixture-change profile passed 3/3 in 25.680s, with one real cut preparation
(2.880s) and all four source proofs (8.924s). Independent inspection found no
additional unnecessary proof leg or fixture correctness defect. Await the
already-running full Portal rehearsal, then run the same seven CTest groups
sequentially without a concurrent rehearsal. This changes neither budgets nor
test populations. Any later pass does not prove concurrency caused this red.

### Retained verification evidence

Control base is the delivery base above. Final controller and rehearsal bytes
are authenticated individually in the retained `events.jsonl`; the rehearsal
ran before this Task's commit, not from a claimed committed final control.
Node commands used Node 22.22.2; configured CTest used Python 3.14.7.

- `/tmp/lmdj-candidate-witness-schema-red-v1.log`: exact numeric binding
  regression, two expected failures before the canonical-byte fix.
- `/tmp/lmdj-candidate-witness-ctest-v1.log`: exit 8; lifecycle hit its 120s
  budget. `/tmp/lmdj-candidate-witness-ctest-v2.log`: exit 8; source projection
  hit 30s, all 23 witness cases passed. The third red is detailed above.
  These are failed iterations, never reconstructed or reclassified as passes.
- `/tmp/lmdj-candidate-witness-node-v1.log`: unchanged official standalone
  witness verifier tests, 11/11, no skips, exit 0.
- `/tmp/lmdj-candidate-witness-scope-v3.log`: staged ownership, 74/74, exit 0.
- `/tmp/lmdj-candidate-witness-docs-v2.log`: complete local Portal check,
  170/170 tests, 47 routes, exit 0. The four actual rendered-page assertions
  in `/tmp/lmdj-candidate-witness-rendered-v1.log` also passed.
- `/private/tmp/lmdj-candidate-witness-portal.YeXkAS/run-v1`: earlier complete
  rehearsal passed naturally. It recorded the pre-optimization runner bytes;
  it is retained separately and is not final controller acceptance.
- `/private/tmp/lmdj-candidate-witness-final.FOaIq6/run-v2`: final production
  controller and harness rehearsal, exit 0. Real source, official snapshot and
  resume, both cut Task phases, distinct squash, witness generation/verification,
  cold-run verification, exact-byte transfer and source-absent fresh-clone
  full Portal check all ran. Far-side Portal: 170/170, zero skips, 47 routes.
  Final clone was clean; the original source object was absent before and
  after the journey. No original source hydration occurred in that clone.

Final rehearsal identities (fixture only, not an allocated release):

- source: `29d121ad2b76c3b7f0c85bdf2b942a81591e6c9f`
- cut: `14952094a7f8b908ca48fe7dd1bfe78574eaeb16`
- introducing squash: `b81418ed4fdeac212c84cc7a2bbd8ef57ff11770`
- metadata: 53045 bytes,
  `37420932b65525728359629a30777c8f1da11958e332d3a990e0dfe0d6b8f275`
- witness: 10995 bytes,
  `b5fc24653112a192898ddc39d99e6e23e129498eba62832fc2afb2745c40c5c5`
- cold-resumed witness history:
  `1e366c007e05afba812cbb6f3e8d4dd704d2d764f47bc7a82976653bb5b0c579`

`/tmp/lmdj-candidate-witness-audit.py` independently re-read the retained raw
evidence after completion. `/tmp/lmdj-candidate-witness-audit-v2.log` records
exit 0: all 19 outer commands paired with actual stdout/stderr byte counts and
digests (17 successes and two expected source-absence exit-1 probes), all 11
executor output spools matched their recorded results, actual verifier output
bytes matched the retained base64 and both artifact copies, and controller /
harness hashes matched the current files. This audit is a consumer of raw
evidence, not a substitute for it or a claim of remote release/deployment.

Final sequential CTest verification:
`/tmp/lmdj-candidate-witness-ctest-v4.log`, exit 0, seven groups / 29 actual
child cases, no skipped cases, total 210.54s. Source projection passed 3/3 in
18.841s and source binding 3/3 in 12.752s, both within their unchanged 30s
budgets. Witness lifecycle/state/boundary/output/schema passed 4/4/7/4/4.
No controller, fixture, group selection or budget changed between v3 and v4;
only this plan's evidence was appended. The three prior failed iterations
remain failures; this pass does not establish the cause of their timing.

Independent precommit inspection of all eight files and a separate execution
of the retained-evidence audit found no additional actionable issue. Final
committed-head review is a separate handoff. This code remains local while
the upstream owner-adoption hold remains unresolved. No new process-only
pitfall was established: numeric identity and boundary invariants have direct
regressions; the remaining timing cause is not proven.

## Version Management

Version impact: none. Orchestration plumbing only; no actual Product Build,
Assembly, Module, Provider, Host, Contract or snapshot allocation.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
