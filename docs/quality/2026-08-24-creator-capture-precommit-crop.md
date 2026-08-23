# Creator Capture Pre-commit Crop Acceptance — 2026-08-24

## Current status

Issue [#213](https://github.com/endaye/lmdj/issues/213) implements a real,
destructive edit of the Host-local capture buffer before Commit. Product Build
candidate `1.0.30.0` allocates Creator Web Host `1.4.0`; Core Modules,
Providers, Contracts, the Formal Web Runtime Host, Host API `1`, resource
limits, persisted Project Truth and Runtime Snapshot identities do not change.

Crop is deliberately narrow. It keeps the selected PCM, rebases it to frame
zero, rebuilds chunks, indexes and block-peak summaries before publishing the
new buffer revision, and clears the envelope cache. It does not add Undo,
persisted Asset editing, automatic silence trimming, fade, normalization or
other DSP.

## Acceptance mapping

| Design acceptance | Automated evidence | Required result |
| --- | --- | --- |
| Exact PCM across arbitrary append chunks | `capture_buffer.test.ts` — `crops exact stereo frames across append chunks and rebases to zero` | Both channels retain the selected frames exactly and `slice(0, count)` starts at the old selection start |
| Invalid Crop is atomic | `capture_buffer.test.ts` — `rejects invalid crops atomically without invalidating the envelope cache` | Negative, fractional, empty and out-of-range requests throw `RangeError`; frame count, PCM and cached envelope identity are unchanged |
| Old summary peaks cannot leak | `capture_buffer.test.ts` — `rebuilds block peaks without retaining an excluded peak from the old block` | A peak outside the selected range but inside an old 256-frame block is absent after Crop |
| Repeat and continue capture | `capture_buffer.test.ts` — `supports repeated crops and append after crop` | A second Crop and a later append produce exact PCM and envelope peaks |
| Reducer owns the new revision | `capture_state.test.ts` — Crop transition cases | Only `trimming` / `commit-error` with the exact selection length may transition; selection becomes the new whole buffer and stale error/conflict state clears while stop reason remains |
| Visible editing and unchanged Commit contract | `capture_panel.test.tsx` — Crop component cases | Whole-buffer Crop is disabled; strict selection Crop mutates the same `CaptureBuffer`, repaints `0..croppedLength`, and Commit receives the same instance plus `{startFrame: 0, frameCount: croppedLength}` |
| Retry after failure | `capture_panel.test.tsx` — `Crop clears a commit error and remains available for another edit` | Crop removes the obsolete alert and permits another selection/Crop/Commit cycle |

## Local verification recorded before snapshot

| Gate | Result |
| --- | --- |
| Focused CaptureBuffer/reducer/panel Vitest | `58/58` pass |
| Complete Creator Vitest | `304/304` pass across 16 files |
| Creator TypeScript and Vite production build | pass |
| Product/version, module graph, dependency and active-tree gates | pass; Product `1.0.30.0`, Creator `1.4.0` |
| Architecture Portal current-source gate | pass: 50/50 tests, 37 pages, 10 diagram sources / 20 outputs, 42 built routes |
| Full `scripts/architecture-portal.sh check` before snapshot | precise expected stop only: `1.0.30.0` absent from versions, snapshot source and metadata; all preceding tests/docs/diagrams/facts passed |
| `scripts/creator-web.sh proof` | pending clean-source proof run |
| `scripts/core.sh proof` | pending clean-source proof run |
| Immutable `1.0.30.0 · canary` Portal snapshot | pending clean committed source |

Pending rows are not claimed as passes. This record is updated only from
actual command results before the source/snapshot commits.

## Evidence boundaries

This change has no new real-microphone, hearing, Safari, iPadOS or external
audio-interface session. Existing physical rows remain unchanged. Local tests,
Proof, an immutable snapshot, remote CI, merge, signed tag, Release,
deployment, publication and Channel promotion are separate facts.

At the time this source record was introduced, push, Pull Request, merge,
Issue closure, Product tag, Release, deployment, publication and Channel
promotion had not been performed for #213.
