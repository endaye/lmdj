# Creator Capture Range Envelope and Selection Zoom Design

Date: 2026-08-23

Status: approved by the user on 2026-08-23

Issue: [#212](https://github.com/endaye/lmdj/issues/212)

## Context

`CaptureBuffer.envelope(bins)` currently renders the complete append-only
capture. During recording that is correct, but the trimming surface already
owns a bounded selection. Rendering the same complete buffer after either trim
slider changes means the visible waveform is not a zoom of the selection and a
future narrow-window request would still scan unrelated samples.

Issue #212 deliberately prohibited a speculative range parameter until there
was a real caller. This design adds that caller: trimming and commit-error
render the current selection at the canvas's fixed 400-bin resolution.

## Decisions

### CR-D1: One explicit range API

The buffer API becomes:

```ts
envelope(bins: number, startFrame: number, frameCount: number): Float32Array
```

All three arguments are explicit. `bins` and the two range values must be
integers, `bins > 0`, `startFrame >= 0`, `frameCount > 0`, and the half-open
range `[startFrame, startFrame + frameCount)` must fit within the stored
buffer. Invalid bin counts remain `TypeError`; invalid ranges are `RangeError`.
The panel never asks for an envelope before the first frame arrives.

### CR-D2: Recording stays whole-buffer; trimming is selection zoom

- `recording` renders `[0, buffer.frameCount)`.
- `trimming` and `commit-error` render
  `[selectionStart, selectionStart + selectionFrames)`.
- selection start and length are paint-effect dependencies, so either slider
  immediately repaints the canvas.
- committing still receives the same buffer plus selection. Zoom changes only
  presentation and does not mutate captured samples or Project Truth.

### CR-D3: Exact bins never visit samples outside the window

When `frameCount / bins < ENVELOPE_BLOCK_FRAMES`, the exact path traverses only
the requested window. Bin assignment uses the sample's window-relative index,
so a non-zero `startFrame` cannot shift samples into the wrong bin. Traversal
works across arbitrary append chunk boundaries and combines channels by
maximum absolute magnitude.

### CR-D4: Block summaries are used only for fully covered blocks

When each bin spans at least one summary block, the block path may consume an
existing peak only if the entire block lies inside that bin's exact sample
interval. Samples in partial blocks at either bin edge are scanned exactly.
This prevents a peak immediately outside the selection, or across a bin
boundary, from leaking into the displayed result while retaining
`O(bins + covered blocks + edge samples)` work for long windows.

### CR-D5: The cache identity includes the range

The memoization key is `(stored frames, bins, startFrame, frameCount)`. Repeating
the same request returns the cached object; changing either range value cannot
reuse another view. `append()` continues to invalidate the cache.

## Correctness and Acceptance

Unit tests must prove:

- exact-path ranges across append chunks and stereo channels;
- cache separation by start and length;
- validation of out-of-buffer and malformed ranges;
- block-path exclusion of high peaks immediately outside both window edges;
- exact handling of partial per-bin edge blocks; and
- compatibility of whole-buffer rendering through explicit `0, frameCount`.

Component tests must prove that recording requests the whole buffer, trimming
requests the current selection, and both selection sliders trigger repaint.
Focused Creator tests, the complete Creator proof, version verification, and
the Architecture Portal check remain separate gates.

## Alternatives Rejected

- Adding optional range arguments without changing the panel was rejected as
  speculative API with no product benefit.
- Slicing the capture into a temporary buffer before every paint was rejected
  because it copies audio and discards the existing block summaries.
- Outward-snapping partial blocks was rejected because it can display peaks
  that are not inside the user's selected window.

## Version Management

- Product Build: `1.0.27.0 -> 1.0.28.0`. Creator Host identity changes in the
  Product Assembly, so the prospective BUILD rule applies.
- Creator Web Host: `1.3.4 -> 1.3.5`. This is a backward-compatible refinement
  of the existing capture-trim surface; no Host protocol, Facade, Contract, or
  persisted Project shape changes.
- Product Build `1.0.29.0` is reserved for the separately approved #213 Crop
  capability. Stage 9 is reallocated from `1.0.28.0` to `1.0.30.0`; abandoned
  or superseded Build allocations are not reused.
- No tag, Release, deployment, publication, or Channel promotion is authorized
  by this design or by snapshot generation.

## Documentation Impact

Documentation impact: required.

Affected Portal routes:

- `/core/modules/web-runtime-platform/`
- `/hosts/overview/`
- `/hosts/creator-web/`
- `/platform/input/`
- `/platform/web-runtime/`
- `/product/capability-map/`
- `/operations/testing-and-proof/`
- `/operations/version-and-release/`

Reason: the Creator capture workflow gains selection-driven waveform zoom and
the Product Build/Creator Host identities change. A clean committed source
revision must be frozen as the immutable Product Build `1.0.28.0 · canary`
Portal snapshot after current-source integration.
