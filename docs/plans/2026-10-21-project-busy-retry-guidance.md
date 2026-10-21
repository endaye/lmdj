# Busy Project retry guidance without a takeover action

## Refreshed premises before edits

Exact integration/worktree parent: e1f6dfc3694ab04bcc1fb66599f8aa4015bc95d0.
Live #2229 is OPEN with zero comments. This is one presentation Task within
U12e; the whole Issue/2112 and remaining layout/browser/device acceptance stay
open. No new modal framework or ownership/recovery decision.

Source evidence: ErrorPanel always shows userMessage(PROJECT_BUSY).nextStep,
which says Choose Continue here. Workspace legitimately supplies Retry project
and no Continue here when its optional takeover coordinator is absent; existing
project_takeover_workspace test already proves those actual rendered controls.
The source is therefore giving an unavailable next step. Positive control:
with a coordinator the existing busy-open journey offers Continue here and
opens only after a released receipt. Preserve that behavior and catalogue.

The Native Web transport separately requires its terminal BroadcastChannel;
removing the browser-wide primitive is not a valid real-Native proof of this
optional UI state. Do not fake a Native capability pass. Owning component/App
state verification exercises the legitimate configured Host state directly.
Existing real default-coordinator takeover journeys remain separate evidence;
this text-only Task does not claim new Native/device or full U12e acceptance.

## Bounded status inventory

| State | Existing source boundary | Current disposition |
| --- | --- | --- |
| Duplicate ID | ErrorPanel + Workspace open-local callback | existing implementation; full current-page audit remains |
| Busy + coordinator | Retry/Continue callbacks and actual outcome note | delivered logic; preserve |
| Busy + only Retry | rendered button exists, missing Continue button, catalogue still asks for it | this Task's one verified presentation gap; reproduce in owning test |
| pending/cancel/refused/unanswered/release-failed/released-busy | TakeoverPending/Note and existing coordinator/workspace tests | preserve protocol/owner, no policy change |
| holder released/owner-lost | TakenOverPanel and Runtime closed gates | existing implementation; broader focus/layout audit remains |
| saved but prepare failed | Sample saved/readiness status/details and Retry Prepare | existing implementation; broader real-page audit remains |

This is a bounded source inventory, not a claim all tests or browser states ran.

## Exact five-file Task scope

- apps/creator-web/src/components/error_panel.tsx
- apps/creator-web/test/project_takeover_workspace.test.tsx
- apps/docs-site/docs/hosts/creator-web.mdx
- apps/docs-site/docs/hosts/creator-interactions.mdx
- docs/plans/2026-10-21-project-busy-retry-guidance.md

Only the rendered next-step for PROJECT_BUSY with an actual Retry project
callback and no Continue here callback changes. Do not alter shared catalogue,
App mounting/commands, coordinator, Native, timers, action availability, unknown
results, diagnostics, CSS, focus or background input. Ordinary with-coordinator
wording/actions remain unchanged.

## Verification

Add one App owning regression: a real rendered configured Host without a
coordinator must not direct to Continue here, and its actual Retry project
still opens once the fixture's owner releases. Observe RED before the renderer
fix. Run complete project_takeover and project_takeover_workspace suites,
strict Creator types, staged/committed ownership and body/declaration checks.
Complete Portal check for the two source-fact routes before commit. No new
required gate, timeout/threshold, test de-selection or journey-leg reduction.
Unit configured-Host proof does not claim real Native/device proof. Broader
U12e long-message/focus/current-owner/saved-not-ready and original real-page
journeys remain owned by the ongoing audit, not silently marked complete.

## Version Management

Version impact: compatible Creator Host presentation PATCH debt, deduped under
existing higher Host MINOR/other debt in #2237. No public API/ABI/Contract,
persistence/dependency/manifest/Product/Build/Channel/snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Document only available Retry guidance. No source diagram/identity change.

## Pitfall Impact

Pitfall impact: none. The product presentation defect is directly expressed
by the owning availability-and-action regression; no generic gate/process rule.

## Shipping boundary

Standing Task authorization covers commit/push/PR/current-head review and
guarded squash after Task verification, findings/conversations/conflicts/live
protection pass; safe postmerge cleanup is authorized. No other writer's dirty
work, original stack or root main checkout is touched. Fixed candidate8c361623f
and frozen workflow/release/evidence/versioned-release paths remain excluded.
No auto-merge/tag/Release/Runtime deployment/Channel. #2229 remains OPEN.

## Verified source before commit

The new owning assertion first failed with the literal unavailable Continue here
instruction in the actual rendered alert (guidance-owning-red). The preceding
command used a wrong relative append path, so the intended test was not added;
that invocation selected zero cases/13 skips and is explicitly not a RED or PASS
proof. Its output is retained separately, not overwritten or counted.

Fixed complete coordinator + configured-Host workspace suites35/35 PASS3.693s,
zero skips. Retry opens the expected11111111 Project projection and no alert
remains; all original cancel/refused/unanswered/release-failed/holder cases stay.
Creator TypeScript PASS0.564s. Complete Portal179tests/53pages/51routes and links
PASS70.117s; the two changed prose facts were separately checked against the
renderer/callbacks, not inferred from a mechanical green. Staged ownership76
passes; five exact paths, diff-check0. No Native/browser/device/candidate pass
is claimed, no frame/timeout/threshold/action/owner policy changed.

Fresh main before commit: e1f6dfc3694ab04bcc1fb66599f8aa4015bc95d0. Its intervening changes do not touch the
five Task paths; all seven applicable governance hashes are unchanged. This
Task's unavailable-action premise remains and no successor delivered it.
