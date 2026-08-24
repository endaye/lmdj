# LMDJ Creator Capture Input Gate and Identity (F4)

**Goal:** close the F4 silent-capture gap exactly as decided in
[`docs/prd/decisions/2026-08-24-capture-input-gate-and-identity.md`](../../prd/decisions/2026-08-24-capture-input-gate-and-identity.md):
(a) a commit-time input-level gate that refuses a digitally silent take, and
(b) visible input identity in the Capture panel. No device picker.

**Tech Stack:** React `19.2.8`, TypeScript `7.0.2`, Vitest, Playwright
`1.62.1`, Docusaurus Architecture Portal.

## Why this plan exists

`apps/creator-web/src/capture/capture_controller.ts` requests audio with no
`deviceId`, so capture follows the OS default input. The 2026-08-17 physical
session (F4, section F of
[`2026-08-16-outstanding-work-before-stage9.md`](../../quality/2026-08-16-outstanding-work-before-stage9.md))
proved that when the default input is silently switched (macOS Continuity
rerouting to an iPhone), `getUserMedia` succeeds, the stream carries digital
silence, and the Creator commits 5 s of silence onto a Pad with no warning.
F4 was explicitly out of scope for the Capture UI remediation plan; the
product decision landed 2026-08-24 and this plan is its implementation.

## Scope boundary

- Creator front end only. If a fix appears to require a Core, Facade,
  Contract or Assembly change, stop and report instead of widening the diff.
- Do not change `resource_limits`, `COMMIT_MAX_FRAMES`, the capture state
  machine's transition matrix semantics, the single-owner controller
  lifecycle, or the blur/hidden stop semantics.
- No device picker: its absence is a declared scope boundary since
  `1.0.23.0`; this decision does not widen it.
- Strict zero only: the gate refuses a take whose whole-take measured peak is
  exactly zero. Quiet-but-nonzero real takes must never be blocked. Higher
  level thresholds need physical data and are deferred by the decision.
- Local commits only. Push, PR, merge, tag, Release, publication, deployment
  and Channel promotion each require separate explicit authorization.

## Tasks

### Task 1 — Whole-take peak accessor on `CaptureBuffer`

Add an exact whole-take max-abs peak accessor. `append()` already folds every
sample into the per-block peak summaries (`ENVELOPE_BLOCK_FRAMES`), so the
maximum over all block peaks of all channels is the exact take peak in
O(blocks) — no rescan of the take, and Crop rebuilds the summaries before
publishing the replacement revision, so the accessor stays correct after
Crop.

**Files:** `apps/creator-web/src/capture/capture_buffer.ts`,
`apps/creator-web/test/capture_buffer.test.ts`.

**Verification:** new unit tests — all-zero take peaks at exactly `0`;
nonzero values across blocks/channels give the exact max-abs; peak follows
Crop. `npm --prefix apps/creator-web test -- run` and `npx tsc --noEmit`.

### Task 2 — Input identity on `CaptureController`

Expose the capture track's `MediaStreamTrack.label` on the controller as
`inputLabel` (empty string before start or when the browser withholds the
label). This is the smaller honest change versus extending `CaptureListener`:
the panel already owns the controller ref and reads the label once `start()`
resolves. `browserCaptureDeps()` is unchanged; the test fakes gain the label
field.

**Files:** `apps/creator-web/src/capture/capture_controller.ts`,
`apps/creator-web/test/capture_controller.test.ts`.

**Verification:** new unit tests — label exposed after `start()`, empty
string before start and when the track label is empty.

### Task 3 — Panel gate, identity display and devicechange notice

In `apps/creator-web/src/components/capture_panel.tsx`:

- **Silence gate:** `handleCommit` measures the WHOLE take via the Task 1
  accessor before the existing `commit` dispatch. Exactly-zero peak refuses
  the commit: an inline `role="alert"` explanation inside the panel
  ("Nothing but digital silence was captured. The input device may have been
  switched by the system."), the take stays intact (re-record or discard),
  and the commit path is not called. The gate reads the whole take, never
  the current selection. Panel-level gate; the reducer's transition matrix
  is untouched.
- **Input identity:** the panel shows `Input: <label>` during `recording`
  and `trimming` (and the commit-error retry view, which is the trimming
  view); an empty label falls back to `Input: Default input`.
- **devicechange notice:** while `recording`, listen to
  `navigator.mediaDevices` `devicechange` (guarded for availability) and
  show a non-blocking in-panel notice when the device set changes; the
  listener is scoped to the recording phase exactly like the blur/hidden
  listeners and is removed when recording ends.

**Files:** `apps/creator-web/src/components/capture_panel.tsx`,
`apps/creator-web/test/capture_panel.test.tsx`.

**Verification:** component tests — silent take refused with the explanation
visible and the take preserved; quiet-but-nonzero take commits; the gate
reads the whole take, not the selection; label displayed; empty label shows
the placeholder; devicechange notice appears during recording and the
listener is removed after. Full `npm --prefix apps/creator-web test -- run`
and `npx tsc --noEmit` stay green.

### Task 4 — Version allocation, docs and portal

Creator Web Host **patch** `1.5.2` → `1.5.3` (module.json, package.json,
package-lock.json); the final integration combines this change into Product
Build **1.0.36.0** on the latest `main`. Regenerate with repo tooling
(`python3 scripts/version.py lock`, runtime-identity generator) and update
the literal expectations (`tests/build/version_test.py`,
`tests/conformance/module_graph_test.py`, portal repo-facts,
`products/lmdj/CMakeLists.txt`, `products/lmdj/README.md`,
`products/lmdj/assembly.json`). Update the current portal pages (at minimum
`hosts/creator-web` — the capture surface description and the device-picker
boundary note both change) and the quality ledgers: mark F4 fixed in
`1.0.36.0` in section F of
`docs/quality/2026-08-16-outstanding-work-before-stage9.md` (F3/F5
convention), mark the F4 row done in
`docs/quality/2026-08-17-machine-task-todo.md`, and note the build number on
the open "F4 resolution lands" trigger row in
`docs/quality/2026-08-17-manual-verification-todo.md` (physical rows
untouched; the human re-run stays open). Then freeze the portal snapshot as
a SECOND commit: `scripts/architecture-portal.sh version 1.0.36.0 canary`
(freezer needs a clean worktree); post-freeze
`scripts/architecture-portal.sh check` must exit 0.

**Verification:** `python3 scripts/version.py verify --version-file
products/lmdj/version.json`, `python3 tests/build/version_test.py`,
`python3 tests/conformance/module_graph_test.py`, portal gates, and the
post-freeze `scripts/architecture-portal.sh check`.

## Playwright note

The Chromium fake device replays a synthetic tone, so the existing capture
journeys exercise the non-silent path; they must keep passing structurally.
A silent-device journey is not expressible in the current harness (the fake
device cannot emit digital silence), so the refusal path is covered by
Vitest component tests only — stated explicitly rather than forced.

## Version Management

**Version impact: required.**

- `creator-web` takes a SemVer **patch** bump `1.5.2` → `1.5.3`: the gate
  and identity display repair a defective Host surface behaviour without
  changing any public Host boundary, Contract or protocol.
- Product Build **1.0.36.0** is allocated for the integrated Assembly composition,
  with its immutable Architecture Portal snapshot
  (`scripts/architecture-portal.sh version 1.0.36.0 canary`).
- No Core Module, Provider, Contract or Application Facade version changes;
  the diff does not reach them.

## Documentation impact

**Documentation impact: required.**

- `hosts/creator-web` describes the Capture surface and declares the
  device-picker boundary; both change when this lands (silence gate, input
  identity, devicechange notice; the picker remains out of scope).
- The version-carrying portal pages change with the new Product Build, and
  the `1.0.36.0` snapshot is frozen in the same Task (second commit).
- The quality ledgers listed in Task 4 change in the same commit that closes
  F4.
- Run `scripts/architecture-portal.sh check` before every commit (the
  pre-freeze missing-snapshot failure is the known accepted state; run the
  other portal gates individually pre-commit as prior tasks did).

## Out of scope

Device picker; any silence threshold above strict zero (needs physical
data); the F6 render-path amplitude ramp (separate decision and task);
physical re-walk of the F4 trigger row (human, per
`2026-08-17-manual-verification-todo.md`); Sequence and Perform surfaces;
anything behind a Stage 9 or later boundary.
