# Stopped Pattern selection preserves transport authority

## Premises

Integration and Task base: `0ce865fe55445f89f2a117ee18e75acb8b81cdb9`.
The full Creator proof on `f1d17ba328ba1f9ea4713e4d281414d9f11cf0af`
failed after an accepted epoch 3 Stop and successful stopped Pattern selection:
its next new Record request named epoch 1 and was refused INVALID_ARGUMENT.
That run did not reissue the old Stop. Preserve the original failed journey,
its traces and the separate tone-recording/BPM failures.

Current main's cross-Pattern `snapshot.reload` destroys the stopped engagement
without stopping the audio engine. The empty subsequent inspection reports
epoch/generation zero; the running engine retains its accepted transport epoch.
The existing native reload journey avoids that observation by maintaining its
own increasing request counter. The independently approved 2026-09-16
reanchor decision already lets a surviving coordinator open the next Record
journal on the engine's current Pattern.

Disposition: verify this authority gap in the real native Host journey before
repairing it. Current source still contains the reset; no successor implements
the fix. The new SEQ SNAP/count-in decisions are not implementations and do not
change this stopped-selection invariant. Implement no new timing, switch or
concurrency policy in this Task.

## T1

Declared files:

- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `apps/docs-site/docs/hosts/web-runtime.mdx`
- `docs/plans/2026-10-10-stopped-pattern-transport-authority.md`

Preserve the existing controller, session, Runtime generation and command
ledger during a stopped cross-Pattern reload while the engine stays running.
Update the Host's selected Pattern binding after successful publication so a
later reload checks the current selection. The coordinator's existing
current-Pattern reanchor handles the next Record journal. Audio suspension or
Project replacement retains its actual retirement and fresh-generation rules;
pending publication remains honestly refused for a new command.

Lowest-tier verification: extend the existing native reload acceptance journey
to inspect the stopped epoch before selection and inspect it again afterward.
Derive the resumed Record epoch from that authority rather than the private
counter. The original source must fail the new preservation assertion; the
fix must complete all existing recording, retry, second-Pattern truth,
playing-reload refusal, suspension/rearm and first-Pattern truth legs under the
original test bound. Run the complete native Host group, with actual rebuild
status and red/green receipts. This fixes one authority defect and adds no gate
or test-budget change.

Before shipping, refresh relevant main source/policies, run portal checks,
stage only declared files, run staged ownership, create one Conventional
Commit, classify the clean committed range and collect the selected batch-only
evidence. Independent exact-head review and guarded merge remain required.
Retain full Creator acceptance, physical audio/device checks, the parent
four-encoder integration and other pending Goal obligations as unfinished.

## Verification and precommit refresh

Fresh integration revision before commit:
`c390b0849b6f28bedb6ed544629ca316a8db68d9`. Intervening PRs #1975 and #1976
add a future switching/count-in plan and a review retrospective. The declared
Host source, native tests, portal page, scope policy and shipping policies are
byte-identical to this Task's base. The stopped-selection authority gap remains
outstanding on that revision; neither successor implements it.

The native journey was rebuilt against the original source and failed at the
new epoch-preservation assertion in 55.996 seconds (CTest exit 8). After the
repair and the added old-Stop replay assertion, the rebuilt complete
`host.web_control_runtime` group passed in 79.85 seconds under its unchanged
120-second bound. Source and test SHA-256 values match before and after the
final run. `scripts/docs-site.sh check` passed, including all 50 portal routes
and their internal links.

The existing native journey retains the following far-side observations:

| Transition | Verified result |
| --- | --- |
| Record A, trigger/release, Record-off, Stop | Recording settles and transport is stopped/idle. |
| Select B with the engine running | Inspection retains the stopped epoch and Runtime generation; publication is pending. |
| Record B before publication applies, retry the same identity | Initial transient refusal occurs; the same command subsequently records successfully. Its epoch is derived from inspection. |
| Trigger/release B and Record-off | Persisted B truth contains one event. |
| Replay the old A Stop while B is playing | Result is `replayed`; B remains playing. |
| Attempt playing reload, then Stop and Record again | Reload is honestly refused; later transport requests still settle successfully. |
| Suspend, select A, activate, Record from epoch 1 on a second Pad | Fresh generation accepts recording; persisted A truth contains both events. |

Receipts are retained outside the checkout under
`/Users/endaye/Projects/lmdj-followup-evidence/2026-10-09-monitor-output/stopped-pattern-reselection/`:
`native-red-terminal.json`, `native-final-terminal.json`,
`portal-check-terminal.json` and `precommit-premise-refresh.json`.
These native and portal results do not discharge the original complete
Creator browser journey or its other BPM/tone failures. Committed lane
classification, selected batch-only runs and independent exact-head review
remain shipping obligations.

## Version Management

Version impact: Web Runtime Platform PATCH debt.
Reason: restores the existing stopped Record/transport authority behavior,
without adding or changing a public API or Contract. Settle with the Goal's
V1; allocate no Product Build or identity here.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/web-runtime/
Reason: document the stopped-selection ownership and epoch behavior on the
current Host page in the same Task.

## Pitfall Impact

Pitfall impact: none — the product authority defect belongs in its native
regression journey. Existing exact-source and complete-journey procedures apply.
