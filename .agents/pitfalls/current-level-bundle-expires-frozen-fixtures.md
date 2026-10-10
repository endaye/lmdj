---
id: current-level-bundle-expires-frozen-fixtures
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-22
    occurrence: https://github.com/endaye/lmdj/pull/1596
    observed_by: Kimi Code (k3)
  - date: 2026-10-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/37721222350
    observed_by: Codex
exit: gate:tests/platform/web/deployment/creator_web_deployment.spec.mjs
escalation: https://github.com/endaye/lmdj/issues/1883
---

# A frozen Project Bundle fixture dies at every Contract level bump.

## Why

Project Bundles carry no backward compatibility during active development
(`docs/prd/decisions/2026-09-15-project-bundle-current-level-only.md`):
readers accept exactly the current envelope. Any test fixture that freezes a
bundle as bytes — the Creator deployment spec's base64 fixture froze
`lmdj.project.v3` / bundle contract `1.1.0` — becomes invalid the moment the
writer level moves, and the failure surfaces far from the cause (a deployed
Host rejecting the import with `INVALID_PROJECT` inside a browser journey,
not a fixture test). The batch proofs never caught it because they regenerate
their fixtures at proof time; only the frozen deployment fixture went stale.
UI renames have the same shape: the spec's `heading "Sequence"` assertion
outlived the D01-D04 rename to `GROOVE / NN` while the surface rendered fine.
Build 87 repeated this with `Activate audio`: the released Host already used
musical gesture activation, but its deployment smoke still waited for the
removed button. Report export had also moved into System. The immutable
Preview browser check failed before production promotion; signed input and
HTTP verification had passed. [Issue #1883](https://github.com/endaye/lmdj/issues/1883)
tracked the second recurrence and the missing freshness mechanism.

## How to apply

The creator proof (`scripts/creator-web.sh proof`) runs the deployment
journey — frozen fixture import, gesture activation, System report export,
sample replacement, Sequence readiness and durable reload — against the
locally built Host. Every change that moves the writer level
(`packages/project-io/`, `contracts/`) or renames the Creator surface
(`apps/creator-web/`) selects the creator lane, so a stale frozen bundle or a
renamed locator fails that proof at the causing change, with the remedy in
its failure message. When that leg goes red: regenerate the frozen fixture
with the current writer (`scripts/creator-web.sh generate_project_fixture`,
then gzip+base64 into
`tests/platform/web/deployment/creator_project_fixture.mjs`) and refresh the
renamed locators in the same Task. Deployed-release journeys keep exercising
the same spec against immutable Hosts through the deploy workflows'
`smoke_revision`.
