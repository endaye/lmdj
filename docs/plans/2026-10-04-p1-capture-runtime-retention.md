# P1 Pad capture retention across Runtime replacement

Relates to #1664. This Task repairs independent finding R23 without changing the
approved immediate-press capture or explicit interrupted-take decision.

## Declared files

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/capture/pad_capture.ts`
- `apps/creator-web/test/pad_capture.test.ts`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- This plan.

## Behavior and verification

Keep one Pad controller and its exact original Project/slot/buffer in the
Workspace while the Runtime changes. Register its asynchronous permission,
startup, stop and save work with the actual Runtime shutdown barrier. Bind
explicit saving to the current ready Session only when the original Project is
open; inspect the original empty slot and preserve the existing revision retry
guards. Fence callbacks from a completed/discarded take before admitting a new
one. Unmount retires UI notifications but still releases owned resources.

The lowest tests are real App/RuntimeProvider/CaptureController callbacks with
controlled browser resources: observe blocked replacement during old Context
cleanup, resolve cleanup, observe the original review, refuse another Pad's
capture, explicitly Save or Discard and inspect the exact trimmed WAV/slot, then
admit the successor take without old publications. Companion controller tests
cover late old-source callbacks, pending permission/startup/master cleanup and
in-flight saving. Each catches the named ownership or resource-lifetime defect.
Run all Creator component tests, TypeScript/build, staged ownership and official
Portal checks before commit. Complete committed-head selected batch lanes and
independent current-head review remain shipping requirements. Preserve raw RED
results; do not lower budgets, skip journeys or transfer earlier-head approval.
These controlled callbacks do not prove physical Safari/iPad or hearing.

## Version Management

Version impact: none — this repairs Host lifecycle ownership, introduces no
public Contract/API or allocated Product Build, and retains P1's coordinated T8
version settlement obligation.

## Documentation impact

Documentation impact: required — `/hosts/creator-web/` records retained Pad-take
ownership and Runtime cleanup. Frozen historical snapshots remain immutable.
