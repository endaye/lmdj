# Current incremental CI trigger documentation

## Scope and declared files

This Task starts from `4eb6a13958543af377437658ad6ba788ec279880` (PR #904)
on isolated branch `docs/ci-trigger-status`. It corrects current operational
wording, not historical test evidence or the CI implementation.

Declared files:

- `docs/governance/architecture-portal.md`: replace two current daily/node
  suite statements with full incremental and explicit full candidate/node scope.
- `docs/governance/git-workflow.md`: update only the introductory trigger status.
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx`: distinguish
  the earlier self-subscription failure from the merged repair's actual startup.
- This plan.

PR #904 merged the completion relay. Actual main-push run `34188723712/1`
under the same SHA started controller `101942196371` at `04:55:44Z`; its
read-only API observation subsequently showed that controller successful.
This proves the entry ran after repair, not full product success, completion
relay delivery, platform chain-limit recovery or O2 acceptance. Those real
far-side checks remain explicit. The earlier HTTP 422 remains historical fact.

No trigger, policy, permission, storage identity, protection, product version,
release/deployment fact, diagram source or frozen snapshot changes. Existing
source diagrams describe product/Core boundaries, not this operational status.

## Verification

Verification completed in the isolated tree:

- `node --test apps/architecture-portal/test/content-inventory.test.mjs`:
  four tests passed.
- `scripts/architecture-portal.sh install`: lockfile-based local dependencies
  installed, with no lockfile or tracked dependency change.
- `scripts/architecture-portal.sh check`: complete pass, including 65 tests,
  39 page metadata checks, 10 source diagrams/20 outputs, release-document
  checks, type checking, production build and all 42 routes/internal links.
- `python3 tests/build/ci_change_scope_test.py`: 66 tests passed with all four
  declared paths staged, including the new plan's ownership.
- `git diff --cached --check`: passed. The final four-file commit inventory
  and clean worktree status are checked at handoff.

Logs are retained at `/tmp/lmdj-trigger-status-{content,install,portal,ownership}.log`.
No test or coverage threshold was lowered, and no new gate was introduced.
These local results are not remote O2 callback-chain acceptance.

Local commit only; root owns any later shipping. This Task does not dispatch
or cancel a workflow or claim a manufactured acceptance event.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Reason: current testing obligations and actual trigger-repair status are clarified.

## Version Management

Version impact: none
Reason: documentation-only correction; no Product Build, Module, Provider,
Contract, candidate, release or deployment identity changes.

Pitfall impact: none — apply the existing complete-journey and platform event
validation guidance; this is stale operational wording, not a new mechanism.
