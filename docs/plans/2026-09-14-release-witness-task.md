# Verified witness to recoverable Task commit

Delivery base: 8448949274cef3f30b83d68a847b2e99adb5d485.

## Task

Connect the actual retained-source witness runner to a separate, operation-bound
linked worktree based on the actual introducing main commit or its descendant.
Import only the exact canonical witness file whose bytes were emitted and
verified by the official commands. Preserve the original source/cut branch,
immutable snapshots, candidate target and all unrelated main changes. This is
the local producer for the subsequent reviewed witness PR, not an alternative
to that PR or a declaration that candidate preparation is complete.

Hold source and destination writers in that fixed order. Authenticate the
original request, concrete source/cut/squash proof, the last fully confirmed
command history, the emitted receipt and the live artifact bytes. Consuming a
confirmed receipt must not execute another verifier or consume its retry budget.
Revalidate authority, original journal state and artifact bytes across the
destination's mutations and Task verification callbacks. Missing enrollment,
changed receipt/scope/state, wrong ancestry, existing witness, unrelated dirty
files and changed metadata/snapshot bytes fail closed and remain untouched.

Use the existing private-index and atomic OLD/NEW commit installation machinery.
Persist a separate operation marker before binding; missing bound state after
enrollment is unknown, never a new Task. Run the trusted Task verifier before
and after the exact ref update; a crash or a failed postcommit check resumes the
same commit without replaying generation, moving the candidate or rolling back.
No branch push, PR creation, merge, provider call, real release or host mutation
is part of executing this development Task. The existing upstream owner hold
keeps the dependent stack local.

## Declared files

- tools/release/candidate_witness.py
- tools/release/candidate_witness_task.py
- tests/build/release_candidate_witness_task_test.py
- tests/build/release_candidate_portal_journey.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-14-release-witness-task.md

## Verification

Lowest tier: contract tests with real Git and the unchanged official witness
producer/verifier. Use the existing real cut fixture, actual emitted receipt,
independent destination worktree and raw far-side blob assertions. Tests cover
one-file successful commit and cold resume, staged/postcommit failure, process
death after installation/ref update/enrollment, exact receipt/history binding,
authority or source artifact drift during callbacks, dirty destination and
unexpected preexisting paths. Register new test groups at 120 seconds before
their first execution; retain all old groups and budgets.

Extend the existing explicit full Portal rehearsal without dropping any leg:
real source -> snapshot/resume -> verified cut -> actual squash -> official
witness/run/cold resume -> new recoverable witness Task with actual staged and
committed checks -> actual witness squash -> clean source-absent full Portal
consumer. Preserve all raw commands/results and emitted bytes in a new evidence
directory. This local rehearsal does not simulate GitHub review/protection as
passed; live reviewed PR and production parent composition remain required.

Run old witness regressions, Task CTest groups, staged ownership, locked Node
install and full local Portal check; inspect rendered updated documentation.
Independent review covers the exact committed diff and raw Task evidence.
Retain failures rather than increasing budgets or restarting live work.

## Version Management

Version impact: none. Release orchestration only; no real Product Build,
Assembly, Module, Provider, Host, Contract or immutable snapshot is allocated.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document the actual witness Task production and recovery boundary,
without claiming the still-unconnected reviewed PR or production release.

## Retained verification evidence

The independent review found a real last-guard ordering defect: source authority
could remove the destination binding after enrollment, and the original code
installed/staged the witness before a later verification refused it. The actual
regression in `/tmp/lmdj-witness-task-guard-red-v1.log` failed (exit 1, one test,
24.941 seconds) because the destination index had changed. The fix checks both
destination enrollment records before and after the source guard while both
writers remain held. Separate marker-loss and binding-loss tests require no
file, index or HEAD mutation. This product-logic defect is fully expressed by
its regression; no separate process pitfall entry is added.

Earlier iterations remain retained, not relabeled as final-source acceptance:
the missing consumer interface red is `/tmp/lmdj-witness-task-red-v1.log`;
the initial lifecycle 4/4 and boundary 5/5 logs are
`/tmp/lmdj-witness-task-lifecycle-v1.log` and
`/tmp/lmdj-witness-task-boundary-v1.log`. After the guard fix,
`/tmp/lmdj-witness-task-authority-crash-v1.log` passed 11/11 in 133.482 seconds;
that invocation did not yet include the subsequently added upper-bound case.

Node 22.22.2 is selected explicitly; locked install and CMake configure exited
0 (`/tmp/lmdj-witness-task-install-v1.log`,
`/tmp/lmdj-witness-task-config-v1.log`). The local Portal check passed 170/170
tests and 47 routes (`/tmp/lmdj-witness-task-docs-v1.log`); four assertions over
the actual rendered operations page passed
(`/tmp/lmdj-witness-task-rendered-v1.log`). After staging all seven declared
files, ownership/admission passed 74/74 in 5.998 seconds
(`/tmp/lmdj-witness-task-scope-v1.log`). These are local Task results, not a
remote review, release, provider, host or deployment result.

Final CTest `/tmp/lmdj-witness-task-ctest-v1.log` exited 0: all 10 selected
groups, 44 actual cases, 436.08 seconds. The retained
`build/core/dev/Testing/Temporary/LastTest.log` records Python 3.14.7 and each
case: old witness lifecycle/state/boundary/output/schema 4/4/7/4/4; new Task
lifecycle/boundary/authority/crash/artifact 4/5/6/3/3. No group was skipped and
no timeout was widened. The new group wall times were 93.65, 37.64, 71.08,
57.67 and 0.15 seconds under the original 120/120/120/120/30-second budgets.

The complete explicit Portal rehearsal exited 0, retained at
`/private/tmp/lmdj-witness-task-portal.e7PEjm/run-v1`; the outer transcript is
`/tmp/lmdj-witness-task-portal-v1.log`. Actual source, snapshot/resume, cut
staged/committed checks, squash, official witness generation/verification and
cold verification, separate witness Task staged/committed checks, cold Task
recovery, actual witness squash and source-absent far-side Portal all ran.
The final `logs/019.log` reports 170/170, zero skipped, and 47 valid routes;
`logs/020.log` records a clean final worktree. Both source-object absence
queries exited 1 as required; the other 19 outer commands exited 0.

The fixture-only identities are source
`bec933247fd107e23dae736397a76f61caea241e`, cut
`44f3b7e45f0bafcece0278187d4a92c5749621e1`, introducing squash
`c9e31843d69695af1e0d6a14df0a92dbbc869cfd`, independent witness Task
`b2cb24afe0711046178240649bf73ca05ca7762a` (also returned by cold recovery),
and final witness squash `360949cd97bc14d5c5219197e9d3d67a4bc72262`.
Fixture Build 1.0.57.0 is not a real allocation. The witness is 10,995 bytes,
SHA-256 `b3115a2fb3d07cb773f481dc362011d5c602cc8fe058a24b780b6428b04c17f1`;
the confirmed original command history remains
`facfa06e8b4099186ae585cb3cc9201d519942bf714e8cf68d21b33024fd0eed`.

The separately retained read-only `/tmp/lmdj-witness-task-audit.py` exited 0
(`/tmp/lmdj-witness-task-audit-v1.log`). It checked all 21 outer raw log pairs,
20 actual executor outputs (including nine new Task gates), canonical source
history and Task marker/binding bytes, emitted receipts, exact witness blobs,
single-file commits and parents, original-source absence records, final clean
state, and seven controller plus harness byte hashes. The control checkout
was based on the declared delivery base; its Task controller/harness bytes
were explicitly hashed, not misrepresented as already committed in that base.

Independent review corrected two issues in the external audit script itself:
Git now uses an isolated read-only environment, and Python optimization mode
is refused before reading evidence. Actual `python3 -O` refusal exited 1
(`/tmp/lmdj-witness-task-audit-optimized-refusal-v1.log`); an actual audit with
hostile ambient Git directory/worktree/index variables still exited 0
(`/tmp/lmdj-witness-task-audit-env-v1.log`). Earlier raw results are retained.

No GitHub review or protection outcome is fabricated by the rehearsal. The
dependent implementation stack remains local and unpushed under the inherited
upstream hold. Reviewed witness PR transport, production parent composition
and the full release goal remain incomplete; this Task establishes only the
verified local witness commit/recovery producer.

The independent reviewer inspected the complete seven-file diff and final
CTest evidence, then actually reran the retained audit (exit 0), confirming the
far-side raw test counts and controller hashes with no remaining actionable
finding. Final staged ownership/admission also passed 74/74 in 6.030 seconds
(`/tmp/lmdj-witness-task-scope-v2.log`). Exact committed-head review remains a
separate postcommit boundary; none of these local reviews is owner adoption
of an upstream PR or a live GitHub merge approval.
