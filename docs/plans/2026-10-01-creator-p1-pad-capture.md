# P1 T6: immediate empty-Pad capture

Relates to #1664. Depends on the P1 musical gesture and default initialization Tasks.

## Declared files

Creator `src/capture/pad_capture.ts`, `pad_capture_sources.ts`, `src/app.tsx`,
`src/runtime/input_controller.ts`, Pad/Capture/Sample/Perform surfaces, matching capture,
input, workspace and Perform tests; packaged capture and Perform journeys;
`docs/prd/decisions/2026-10-01-creator-p1-pad-capture.md`, this plan, and current
Creator portal page.

## Behavior and verification

Native empty Pad press begins capture immediately. Release stops acquired resources
before committing one strict-zero-trimmed Artifact through the existing Facade
sample ingest path. First microphone permission prepares only; a fresh press is
required. Sources are remembered Host settings. Internal source uses the native
post-FX master tap. Owners exclude Pattern/Perform recording but allow playback.
Cancellation/blur/navigation and capacity preserve explicit Save/Discard takes.
Revision refusal retains bytes; explicit retry revalidates the original Project
and empty target. Existing Undo remains the authoring mechanism. Saved Performance
replay remains while manual resample frame controls are removed.

Lowest tests: immediate start and one release commit, first permission/new press,
startup/release and cancellation races, strict silence/quiet attacks, capacity,
exclusive ownership, revision refusal/retry, input lifecycle cleanup and UI import
reachability. Packaged mic/master journeys require actual Artifact identity and
reopen assertions; fake microphone evidence does not claim physical device acceptance.

## Version Management

Version impact: Creator behavior changes settle in T8's coordinated Host/Product
allocation. Existing Facade and Platform capture Contracts are reused.

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Reason: immediate recording, remembered sources, owner exclusion and explicit recovery.
