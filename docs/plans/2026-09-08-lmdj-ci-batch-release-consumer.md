# Read-only full-batch release evidence consumer — Task A

Status: implemented locally, not activated as release authority. Task B must
separately bind the reference in intent/model, prospective policy, prepare,
permanent plan marker and audit, update governance/Portal, and complete real O1.
Neither this Task nor a passing test authorizes release operations.

## Declared files

- `tools/release/batch_evidence.py`
- `tests/build/release_batch_evidence_test.py`
- `scripts/ci/batch_evidence_validation.py`
- `scripts/ci/batch_runtime.py`
- this plan

The shared pure module extracts the existing bundle reconstruction, API job
name mapping, aliases, prerequisite map, producer step checks and the narrowly
reviewed macOS primary continuation exception. Runtime calls the same logic;
its admission, result/debt classification, storage and permissions do not
change. The release consumer never imports or instantiates Runtime, invokes a
write API, replays Issue Journal, fetches Git or runs historical/target Python.

## Closed reference and authority

`lmdj.ci-batch-release-reference.v1` contains the complete existing T3 `request`,
`executor_control_revision`, first `run_attempt`, `origin_record_digest`,
`admission_record_digest` and `evidence_digest`. The caller separately supplies
the intent's exact target and executor run ID. Task B must bind the trusted
repository ID, workflow ID and producer deployment lower bound in reviewed
policy; these are not fields an untrusted reference may select.

All source runs belong to the canonical repository, stable
`self-test-report.yml` workflow and protected main history after the trusted
producer. Both latest and exact-attempt views must describe the first attempt.
The actual executor can be newer than the frozen request control, but the four
existing execution workflow sources must remain compatible. All three frozen,
actual-executor and applicable-main policy digests agree; the release-owned
inventory is exactly the fourteen canonical suites plus both stress suites.

The original controller artifact retains the exact request: a waiting origin
must have it queued, while an executing origin has its own exact admission and
claim. The executor controller artifact must have `action=execute` and the
same epoch/request plus exact executor/claim. A settle/idle snapshot cannot
substitute for the admission artifact. Both snapshots and the final artifact
must be independently authenticated, uniquely identified and unexpired.

This is a **trusted-producer durable-claim attestation**, not independent
replay of the latest Issue Journal. It deliberately requires only existing
read-only Actions/content capabilities. The consumer must not claim that a
retained snapshot proves the latest mutable scheduler state. Loss or expiry
of an original snapshot fails closed, even when a compressed verdict survives
in the scheduler journal.

The three-file verdict bundle remains closed: `execution.json`, `needs.json`
and `verdict.json`. Pure execution reconstruction and the existing aggregate
independently reproduce the document; exact API job/step observations must
agree under the shared reviewed mapping. Only full, passed, same-target,
current-policy sixteen-suite evidence is returned. Focused/none, missing
stress, failures, contradictory needs, reruns, unknown sources, mixed controls
or attempts and incomplete inventories cannot become candidate evidence.
Historical failures and `history_unknown` are not blanket rejection gates:
they describe history, not the independently verified current exact full run.

Missing/expired evidence is `unverifiable`; malformed or contradictory evidence
is `conflict`; API, pagination and transport uncertainty is `external-error`.
Every failure names why and remedy without printing raw API exception bodies.

## Verification and remaining legs

Lowest tier: `python3 tests/build/release_batch_evidence_test.py` exercises
temporary real Git, actual policies, real reducer enqueue/admit/claim, actual
prepare/from-needs producers, closed ZIP/JSON and a strict GET-only HTTP fixture.
The far-side result is the entire unchanged full verdict, including all suites,
not just a green scalar. Fixtures reject undeclared API routes and test complete
pagination; they do not prove real GitHub permissions, retention, locks, source
job names or actual hosted product execution.

During implementation, three new regressions first failed: missing origin
queue membership, cross-epoch snapshot borrowing and Python `True == 1` in an
execution projection. They now pass. Release adds strict canonical/type checks;
the runtime's pre-existing equality behavior is not silently changed by this
Task. Its separate hardening remains outside this extraction's scope.

Root's early independent review identified a fourth negative case: producer
visibility claimed `skipped` while its step was still `in_progress`. The new
regression was run red, then a release-only terminal-step check made it green;
runtime's extraction remains behavior-preserving.
An additional red-to-green regression rejects a latest run projection that
disagrees with its exact-attempt conclusion; neither view can silently win.

Local verification so far:

- consumer: 55 tests passed, no skips;
- existing runtime: 59 passed; execution: 23 passed; verdict: 35 passed;
- complete `ci_*test.py`: final run 1424 passed, no skips, with pinned
  `LMDJ_ACTIONLINT=/tmp/lmdj-t2-shipping.MTX7q1/actionlint` (1.7.12). The initial
  run omitted that environment variable and skipped one YAML semantic check;
  the final run exercised it. This is not an all-platform product test;
- unchanged release self-test consumer: 18 passed; legacy CI evidence: 16 passed;
- precommit `scripts/architecture-portal.sh check`: 54 passed, 3 failed because
  Portal dependencies are absent in the isolated worktree, no tests skipped.

Staged ownership: 66 tests passed with all four new files tracked; no missing
ownership or document-consumer route was hidden by an unstaged file.
Task B activation, new reference/marker historical compatibility and real
full-candidate acceptance remain unimplemented/unverified here. Legacy native
`self-test-v1` is unchanged; this Task must not be described as completing T4/O1.
No dispatch, Issue mutation, tag, release, deploy or protection change occurs.

### Separate fix: authenticated lightweight tick event compatibility

Root's exact-head review of `536be3ee524b6cbb5d2ac452c1c4532be76923f6`
found P2: the consumer's event allowlist omitted `schedule`, although the
trusted journal supports scheduled controller wakes and T5 plans to use a
lightweight tick for admission/recovery. The rejection would discard valid
full evidence based only on the wake event. This is not an authorization to
restore daily product testing or enable the T5 trigger before its own cutover.

This follow-up Task declares only `tools/release/batch_evidence.py`, its
dedicated test file and this plan, in a separate Conventional Commit. Two
new real-Git/reducer/prepare/three-file fixture journeys first failed at the
event check: scheduled same-run bootstrap and a scheduled executor admitting
a queued explicit candidate from another control SHA. Adding only `schedule`
to the closed event set makes them pass. Unknown origin and executor events
remain rejected, and no source, repository, controller, epoch, claim, policy,
full-suite or retention check is weakened. This is fixture evidence, not a
claim that a real T5 scheduled candidate has passed platform O1.

Follow-up verification: 59 consumer, 59 runtime, 23 execution, 35 verdict,
18 existing self-test release and 16 legacy release tests passed. Pinned
actionlint 1.7.12 CI contracts: 1424 passed, no skips. Staged ownership: 66
passed. Portal rerun: 54 passed, the same 3 missing-dependency failures
(`glob`, `gray-matter`, `cheerio`), no skips. Shipping remains held;
Task B activation and actual full-candidate acceptance are still outstanding.

## Pitfall disposition

### Task A integration onto current main

After root released the code hold following actual host-focused admission
34164424476, integrate Task A alone onto main
`4a8de6edfbfa238d93b3207a6c776f0dc163043f`. The four implementation/test files
are byte-identical to reviewed `761f2cef36e1a1f098287ed25b6487b2d1e67dda`;
the original Task A and its schedule correction form one reviewable integration
commit. No Task B design, reference/model binding or activation is included.
This paragraph is the only addition to that reviewed five-file content.

Fresh-base verification: 59 consumer, 59 runtime, 23 execution, 35 verdict,
18 old self-test release and 16 legacy release tests pass. Complete CI
discovery passes 1,443 tests with no skips using pinned actionlint 1.7.12;
all 66 staged ownership tests and staged whitespace checks pass. Portal check
again reports 54 passes and three unavailable-package failures (glob,
gray-matter, cheerio), no skips. Exact-head root review precedes any shipping.
The real full-passed candidate acceptance gap and Task B remain outstanding;
host admission is not completion or release evidence. No remote release audit,
tag, publication, deployment or workflow dispatch is performed for this Task.

Applied gate-failure readability, acceptance-journey completeness,
synthetic-platform-side-effect and fake-tool-stub guidance. The new local
parser/identity mistakes have deterministic regressions and do not add a
process-ledger recurrence. The broader fake-tool escalation #726 remains open;
real Git plus HTTP fixtures is explicitly not a substitute for platform O1.

## Version Management

Version impact: none

Reason: inactive internal CI evidence protocol and shared verification only;
no Product Build, Assembly, Contract, Module, Host or Provider identity changes.
No existing intent data or published historical evidence changes.

## Documentation Impact

Documentation impact: none

Reason: this prerequisite is not wired into any release entry point or policy;
operational release behavior is unchanged. Task B must update the affected
current Portal pages when it activates the new candidate source.
