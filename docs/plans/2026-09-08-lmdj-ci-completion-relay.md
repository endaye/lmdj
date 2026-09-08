# Incremental CI completion relay repair

## Observed defect and boundary

PR #898 installed the T5 trigger patch at main
`7eff0a1cb4d95b4b4f38f09acaafd51f2707a5f8`; actual run
[34187049368](https://github.com/endaye/lmdj/actions/runs/34187049368)
failed with zero jobs. Root's explicit manual settle command was rejected with
HTTP 422: `Workflow 'Self-test Report' cannot listen to itself`. That dispatch
created no run. Local tests had not caught the direct self-subscription.
This Task repairs completion routing, not product tests, storage, permissions,
release policy or branch protection. Remote acceptance is still pending.

## Declared files and ownership

One shared Task and eventual reviewable commit, with disjoint agent ownership:

- Root/runtime/test work: `.github/workflows/self-test-report.yml`,
  `.github/workflows/incremental-completion.yml`,
  `scripts/ci/incremental_entry.py`, `scripts/ci/incremental_completion.py`,
  `tests/build/ci_incremental_cutover_workflow_test.py`,
  `tests/build/ci_workflow_event_graph_test.py`,
  `tests/build/ci_incremental_entry_test.py`,
  `tests/build/ci_incremental_completion_test.py`,
  `scripts/ci/hosted_runner_policy.json`,
  `scripts/ci/scope_policy.json`,
  `tests/build/ci_batch_runtime_workflow_test.py`,
  `tests/build/ci_o1_claim_probe_workflow_test.py`,
  `tests/build/ci_o1_probe_workflow_test.py`.
- Documentation work: this plan, `docs/design/2026-09-08-lmdj-ci-incremental-batches.md`,
  `docs/plans/2026-09-08-lmdj-ci-incremental-batches.md`,
  `docs/governance/git-workflow.md` (stale introduction only),
  `apps/architecture-portal/docs/operations/testing-and-proof.mdx`,
  `.agents/pitfalls/workflow-self-subscription-unvalidated.md`.

The existing `ci_*_test.py` discovery includes the new tests; no manual test
registry edit is required. Existing ten `.architecture.json` sources describe
product/Core/module boundaries, not CI event delivery. No related source diagram
exists, so this Task does not change those sources or generated/frozen diagrams.

## Minimal routing and authentication

`Self-test Report` remains the only journal writer/controller and reusable
product executor caller. New read-only `Incremental Completion` listens for its
completion and retains a closed artifact associating the exact parent run and
attempt with the relay's own run, attempt and control. The controller listens
to the relay instead of itself. Its consumer reauthenticates actual repository,
workflow/source/control, exact runs, producer steps and artifact association,
then retains the original active-executor check before settlement or admission.
An untrusted receipt is not a parent and not permission to start tests.

The relay adds no write permission, secret, storage identity, journal schema or
permanent service. It does not call a dispatch API or hold the writer lock.
Its hosted-minute use is recorded as control-plane evidence that must survive
a self-hosted outage; the job count is bounded, not free or a product runner.
The existing controller's permissions and state identity remain unchanged.
Its source witness uses v2 for the relay path: original batch parent in
`source_run`, and immediate relay `{run_id, attempt, control}`. Existing direct
source witnesses remain v1. Neither witness asserts a platform chain depth.

An irrelevant or already-settled parent may cause a bounded lightweight wrapper
because GitHub delivers completion events. It must not create a new scheduler
admission, product execution or an unbounded immediate loop. Reports remain
separate from heavy work and cannot manufacture a test verdict.

## Verification and real O2 acceptance

Local verification: 1,699 CI contract tests passed without skips (including
24 completion, 27 Entry, 9 cutover and 7 event-graph tests); staged ownership
passed 66 tests after adding the explicit relay workflow route. Actionlint
1.7.12 with explicit ShellCheck 0.9.0 passed; only the pre-existing platform
`concurrency.queue` syntax unsupported by that actionlint version is excluded.
Full Architecture Portal check passed 65 tests, 39 current source documents,
10 diagrams / 20 outputs, production build and 42 routes with internal links.
The final committed nonempty-range docs-static check remains a shipping step.
The first broad regression exposed three stale trigger expectations and a
missing hosted-runner spending record; these were repaired, not skipped.
The new deterministic graph gate catches direct self-subscription and must name
why/remedy; it does not certify cross-workflow delivery or a cycle remotely.

GitHub documents a maximum three-level `workflow_run` chain in its
[event reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run).
Proposed real journey: controller A → relay B → controller C → relay D; the
next controller E reaches the platform chain boundary, then an independent
scheduled health run recovers the already-retained tail and progresses to idle.
The alternating cross-workflow route itself still needs actual platform
acceptance. This sequence is an expectation to test, not evidence it happened.

Retain each exact parent/relay API identity, authenticated source witness,
artifact association and journal transition. Prove that pending tail existed
before the independent tick, that no newer push/manual root consumed it first,
that the tick actually settled/admitted the retained obligation, and that
catch-up followed by no-change work launched no heavy job. A missing callback
alone does not prove a depth limit; failed validation or delayed delivery must
remain separate findings. Keep every original O2 leg; arbitrary callbacks,
mock payloads or an idle local test do not substitute for remote evidence.

The existing UTC 7/22/37/52 lightweight health schedule is recovery for existing
work, not date-driven product testing. Actions delay/outage may delay recovery;
retain manual reconciliation without promising infinite or immediate chaining.
No remote action is authorized by this document. Root owns any separately
authorized dispatch, merge or acceptance exercise.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Reason: completion transport and actual platform-failure/recovery boundaries change.

## Version Management

Version impact: none
Reason: no Product Build, Module, Provider, Contract, deployment or release identity changes.

Pitfall impact: new workflow-self-subscription-unvalidated — deterministic direct
self-edge coverage, with actual cross-workflow delivery acceptance still required.
