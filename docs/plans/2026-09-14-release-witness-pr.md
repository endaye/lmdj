# Independent witness branch and reviewed PR subjourney

Delivery base: 4cac09bc1311599fed1e3331a941684a7b77f13b.

## Task

Connect the verified witness Task identity to create-only branch transport and
the existing durable exact-head PR/review/squash machinery. The witness has a
distinct operation (`candidate-witness`), branch prefix, closed specification
and parent state schema. It must not be confused with candidate allocation or
publication evidence. Preserve the original candidate target, source, witness
bytes, Task binding and actual Task verification digest across cold recovery.

Reuse the existing branch/PR effects and sequence transitions. Add only trusted
class hooks for the sequence's concrete children, specification and state
identity; keep old candidate defaults and all old tests/budgets unchanged.
The witness transport permits only its own fixed branch GET/POST routes and
exact-head squash PUT. No update/delete/admin/auto-merge capability is added.

Authority remains trusted controller code: it verifies original request,
completed witness Task/source/command proof, live protections and actual Task
checks. Review verifies current head, findings, conversations and closing
relations. Merged verification checks the actual squash and immutable witness
bytes, main ancestry and historical review proof. A receipt/specification does
not authenticate itself. The production parent/factories remain a subsequent
dependency; a merged witness PR is not complete CI or release completion.

Only new local fixtures may execute transport in this development Task. The
upstream PR #1296 is still OPEN at its original head; the inherited hold keeps
the dependent stack local/unpushed. No real GitHub write, provider call,
release, signer, host, authentication or protection change is authorized here.

## Declared files

- tools/release/witness_pr.py
- tools/release/candidate_pr_sequence.py
- tools/release/github_api.py
- tests/build/release_witness_pr_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-14-release-witness-pr.md

## Verification

Lowest tier: contract tests over the real durable controllers, actual temporary
Git ref transport, and the existing bounded HTTP fixture. Cover scope/document
and route separation, body declarations, wrong path/byte/hash/target identity,
pending/stale review, unknown push/POST/PUT, missing/rebound state, writer/parent
authority loss and cold recovery without duplicate effects. Preserve actual
crash tests. Register PR/branch/sequence/journey groups with initial budgets
30/60/60/120 seconds before execution; retain every old test and timeout.

The producer-to-transport integration consumes a real CandidateWitnessTask
commit produced from the unchanged official witness generator/verifier in its
narrow snapshot fixture. Push that exact commit to a new local bare remote,
let the bounded HTTP fixture cause an actual one-parent squash in the far-side
Git store, and verify the real blob/parent/tree and cold observation. Keep
fixture review/protection explicit; it is not live GitHub acceptance or a full
Portal snapshot. The preceding Task's retained full Portal rehearsal is the
companion snapshot proof, not new transport acceptance.

Run unchanged candidate sequence, candidate/publication PR and branch regression
groups, staged ownership/admission, locked Node install and full local Portal
check. Inspect rendered documentation, retain raw failures/results, obtain
independent complete-diff and exact-head review, then commit the declared Task.
No skipped test, widened budget or successful prefix replaces the whole journey.

## Version Management

Version impact: none

Reason: release orchestration only; no Product Build, Assembly, Module, Host,
Provider, Contract, immutable snapshot or tag is allocated by this Task.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document implemented witness PR transport and recovery boundaries while
keeping production parent composition and real release acceptance explicitly open.

## Execution evidence

The seven declared files are the complete Task scope. Node 22.22.2 was explicitly
on PATH for every Portal, producer fixture and CTest command. Direct Python was
3.11.15; CMake selected Python 3.14.7. No production code or old test was changed
to accommodate a failed test, and no timeout was widened.

- Initial transport contracts: 69/69, exit 0, 26.369 seconds,
  `/tmp/lmdj-witness-pr-contract-v1.log`. This preceded the two additional
  POST/PUT parent-guard cases and is not the final population.
- Initial sequence plus producer journey: 13 cases, two failures, exit 1,
  59.160 seconds, `/tmp/lmdj-witness-pr-journey-v1.log`. Both journeys stopped
  before PR creation. The fixture's scratch-transport matcher also intercepted
  its own bare-repository `--git-dir` read and raised `KeyError: env`.
  `/tmp/lmdj-witness-pr-fixture-red-v1.log` retains the minimal actual failure.
  The new fixture now uses equivalent `git -C <bare> rev-parse <ref>` for that
  local API projection, outside the scratch-transport seam. Production and the
  prior fixture remain unchanged.
- Corrected real producer journeys: 2/2, exit 0, 68.780 seconds,
  `/tmp/lmdj-witness-pr-journey-v2.log`. The unchanged official witness bytes
  flow through the actual independent Task, real create-only push and real
  one-parent squash. Cold observation and advancement verify the committed
  blob, parent and tree with exactly one push, POST and PUT. The one-byte
  far-side committed-blob negative returns conflict on cold recovery and never
  repeats an effect. Both cases assert the far-side verifier actually executed.
- Locked install and configure: exit 0,
  `/tmp/lmdj-witness-pr-install-v1.log` and
  `/tmp/lmdj-witness-pr-configure-v1.log`.
- Full local Portal: 170/170, zero failures/skips, build and all 47 routes valid,
  exit 0, `/tmp/lmdj-witness-pr-docs-v1.log`. Four actual rendered HTML claims,
  including the unfinished production boundary, passed in
  `/tmp/lmdj-witness-pr-rendered-v1.log`. This is a local documentation check,
  not publication or a new immutable snapshot.
- Ownership/admission after staging exactly the seven declared files: 74/74,
  exit 0, 5.956 seconds, `/tmp/lmdj-witness-pr-scope-v1.log`.
- First complete CTest: all 10 groups and 216 cases executed, 9 groups passed,
  one error in the witness branch crash fixture; exit 8, 130.97 seconds,
  `/tmp/lmdj-witness-pr-ctest-v1.log`. After the controller exited with code 32,
  the attempted journal reopen encountered `flock` EAGAIN before any new push.
  Twenty isolated diagnostic repetitions did not reproduce the contention
  (`/tmp/lmdj-witness-pr-lock-diagnostic-v1.log`, exit 0, 26.681 seconds), so the
  actual remaining holder is not identified and is not attributed to a specific
  Git subprocess. Controller exit alone is not proof that all inherited Git
  writer descriptors have closed.
- The new witness crash fixture now waits at most five seconds for the original
  writer to become available, within its unchanged 60-second group budget.
  It retries only a journal error caused by EAGAIN/EACCES `BlockingIOError`,
  checks the same lock inode, performs no remote operation while waiting,
  verifies unchanged journal bytes, then invokes recovery exactly once and
  still requires zero new pushes. Other safety errors fail immediately. The
  unchanged inherited orphan test separately proves refusal while the actual
  Git child remains active. The corrected crash case passed, exit 0, 1.299
  seconds, `/tmp/lmdj-witness-pr-crash-v2.log`. Independent review accepted this
  distinction; neither production locking nor old tests were relaxed.
- Final staged ownership/admission after the fixture correction: 74/74,
  exit 0, 5.859 seconds, `/tmp/lmdj-witness-pr-scope-v2.log`.
- Final complete CTest: 10/10 groups, 216/216 cases (73 witness and 143
  unchanged candidate/publication regressions), zero failures/skips, exit 0,
  128.70 seconds, `/tmp/lmdj-witness-pr-ctest-v2.log`. Raw individual cases are
  also retained in `build/core/dev/Testing/Temporary/LastTest.log` in this
  worktree. All original group budgets remain in force. The six executable,
  test/configuration and Portal source files match the tested-byte manifest
  `/tmp/lmdj-witness-pr-tested-files-v2.sha256`; only this execution record was
  extended after the run.
- Independent complete-diff review and the subsequent fixture/locking reviews
  found no remaining actionable issue. Commit remains local; exact-head review
  follows the atomic commit and does not constitute GitHub review or release
  acceptance.
- The live upstream refresh remains OPEN/UNSTABLE at
  `7edeeac9c5efb2e17577431a31774404a2813300`, with no merge identity,
  `/tmp/lmdj-witness-pr-upstream-v2.json`. This is not owner adoption or
  authorization to ship the dependent stack.

The reviewed open pitfalls remain applicable; this fixture-seam correction is
recorded with its causal failure and regression rather than a new policy or gate.
The upstream hold is unchanged. No GitHub write, provider call, signing,
release, deployment, host/authentication change or cleanup occurred.
