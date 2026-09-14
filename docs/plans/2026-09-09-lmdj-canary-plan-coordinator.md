# Durable result-driven Canary planning coordinator

Status: source implemented and locally verified; live activation remains separate.

## Task and boundaries

Connect the real authenticated scheduler reader to a dedicated planning Journal
and an authenticated manual Actions entry. This is one control-plane Task. It
does not execute models/tests, allocate versions, create version PRs, change site
progress, publish, deploy or promote. Automatic wake-up wiring and live reserved
storage initialization remain separate activation work, not implied by merge.

Declared files:

- `tools/canary/planning_journal.py`
- `tools/canary/planning_entry.py`
- `.github/workflows/canary-planning.yml`
- `scripts/ci/scope_policy.json`
- `tests/build/ci_canary_planning_journal_test.py`
- `tests/build/ci_canary_planning_entry_test.py`
- this plan and `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`

## Frozen-input and recovery contract

Use a dedicated exact reserved empty Issue and dedicated epoch, never scheduler,
report or review-discovery storage. Initialization and explicit progress bootstrap
are separate commands. Missing progress blocks observation; initial null pointers
mean a conservative new-system bootstrap, not proof of historical nondeployment.
Importing nonempty progress requires real receipts and is not supported here.

The entry accepts only an operation and exact scheduler request ID, not caller
scheduler/progress/plan JSON. Authenticate the current main first-attempt workflow
and controller, then replay the actual scheduler read-only (including forbidding
checkpoint repair). Verify the retained verdict with the existing planner.

Before storing any potentially chunked plan, append a small intent freezing main,
control, exact scheduler storage identity, independent progress, source digest and expected complete decision
digest. Recovery of a partial append recollects the original retained scheduler
source and recomputes only against those frozen inputs, requiring exact digests.
A completed observation returns its retained complete bytes without scheduler or
artifact rereads. Another source cannot overtake an unfinished intent.

One active plan remains pinned. Newer successful targets coalesce into one pending
slot; late older or equal targets cannot replace it. Git first-parent ancestry
and target ordering are established by the authenticated entry, not by hashes
alone. Failed/missing/not-required and nonautomatic results remain ignored wakeups,
never synthetic passes. No active retirement or progress advancement is introduced
before the later assessment/delivery coordinator can prove those transitions.

## Verification and far-side evidence

- Real Git and real Journal composition with strict GitHub-shaped transport
  fixtures: authenticated source -> durable intent -> complete plan -> fresh
  process recovery preserves complete canonical bytes/digest and input identity.
- Inject response loss before/after intent and each chunk/terminal append;
  restart, retain original identity, resume partial bytes and prove no duplicate
  observation or active-target replacement. Corruption and missing source fail.
- Missing bootstrap, aliased storage, forged provenance, wrong lock/attempt,
  caller input injection and pending scheduler checkpoint cannot write plans.
- Newer pending coalescence and late older completion preserve the active plan.
- Workflow semantics and enabled shell analysis; focused suites, complete CI
  discovery, staged/committed ownership, Portal check and final range inspection.

Local fixtures do not prove live Actions scheduling, credentials, Issue setup,
quota, runner availability or remote recovery. Those acceptance legs remain open.
No new required PR gate or reduced test/timeout budget is introduced.

Local verification on September 9:

- Entry 19 tests and Journal 19 tests pass. The latter includes two genuine
  child-process replay/recovery journeys over serialized transport state.
- Full `ci_*_test.py` discovery passes 2,160 tests with no skips, including after
  staging all nine declared files; new-file ownership passes all 66 tests.
- Portal check passes 112 tests, production build and all 44 route/link checks.
  The first check lacked this fresh worktree's npm dependencies; the canonical
  `scripts/docs-site.sh install` supplied them before the complete passing run.
- Pinned actionlint 1.7.12 with explicit ShellCheck 0.9.0 passes the new workflow
  using the existing CI's exact concurrency.queue compatibility exception.
  The workflow test independently requires queue=max, cancel=false and its
  dedicated job lock; no linter or concurrency check is weakened by this Task.
- Product version verification passes without allocating a Build. No release
  audit, live storage initialization, model invocation or deployment was run.

Independent review requested real process-boundary evidence and negative recovery
source tests; both are now present. The complete decision is pack-checked before
intent persistence so oversized input cannot reserve an unfinishable slot.
No new qualifying pitfall recurrence: these invariants have direct regressions.

## Version Management

Version impact: none

Reason: internal planning control only; no Product, Host, Module, Provider,
Contract, Assembly, version or snapshot allocation changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/testing-and-proof/

Document the actual manual commands, frozen recovery and disabled downstream
boundaries without presenting a plan as deployment or release evidence.
