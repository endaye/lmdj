# Creator Capture Pre-commit Crop Design

Date: 2026-08-23

Status: approved by the user on 2026-08-23

Issue: [#213](https://github.com/endaye/lmdj/issues/213)

## Context

Creator Pad Capture stores microphone frames in an append-only
`CaptureBuffer`. The trimming surface can move and resize a selection, but it
does not edit the buffer: Commit still receives the original buffer plus that
selection. The incremental block peaks maintained by `append()` are therefore
correct today only because stored samples and their frame origin never change.

Issue #213 deliberately deferred peak invalidation until a real pre-commit
edit existed. This design adds that edit as an explicit **Crop to selection**
action. Crop mutates only the ephemeral capture buffer before Commit. It does
not mutate Project Truth, introduce a persisted edit history, or change the
Facade/Project Contract.

## Goals

- Let the user permanently reduce the current capture buffer to the selected
  half-open frame range before Commit.
- Make the mutation atomic: an invalid range or failed preparation leaves the
  original buffer unchanged.
- Rebuild every frame-derived index and summary from the new frame origin so
  no peak outside the crop can appear in a later envelope.
- Keep Commit compatible with the existing buffer-plus-selection interface.
- Support repeated Crop operations without accumulating stale offsets or
  summaries.

## Non-goals

- Undo/redo, crop history, or recovery of discarded pre-commit frames.
- Normalize, fades, reverse, silence trimming, resampling, or channel changes.
- Editing an already committed Asset or persisted Project sample.
- A new Facade action, Project mutation, Contract field, Provider, or Runtime
  Snapshot shape.
- Tag, Release, deployment, publication, physical-device acceptance, or
  Channel promotion.

## Decisions

### CC-D1: One synchronous, atomic buffer mutation

`CaptureBuffer` gains one public method:

```ts
crop(startFrame: number, frameCount: number): void
```

Both values must be integers, `startFrame >= 0`, `frameCount > 0`, and the
half-open range `[startFrame, startFrame + frameCount)` must fit inside the
current buffer. Invalid input throws `RangeError` before any field changes.

Crop first materializes every selected channel into replacement arrays. Only
after all replacement data and summaries have been prepared does it publish
the new internal state. Allocation or preparation failure therefore cannot
leave channel data, frame count, chunk starts, block peaks, and cache describing
different revisions of the buffer.

### CC-D2: Crop rebases the selected audio to frame zero

After a successful Crop:

- `frameCount` equals the requested `frameCount`;
- each retained channel contains exactly the selected samples in order;
- the retained audio begins at buffer frame `0`;
- chunk starts are rebuilt against that new origin;
- `slice(0, frameCount)` returns the complete cropped capture; and
- a later `append()` continues from the cropped length and updates a partial
  final summary block correctly.

The implementation may store each cropped channel as one replacement chunk.
The capture is already bounded to 60 seconds and Crop is an explicit control
thread/UI action, so a bounded copy is preferred over persistent offset state
or a fragmented edit graph.

### CC-D3: All waveform acceleration state is rebuilt

Crop must not merely clear the one-entry envelope cache. It rebuilds
`#blockPeaks` from the replacement channel data using the same
`ENVELOPE_BLOCK_FRAMES` and maximum-absolute-magnitude rule as `append()`, then
clears `#envelopeCache`.

This is eager rebuilding, not a lazy dirty flag. The user sees the cropped
waveform immediately, the first redraw cannot observe incomplete summaries,
and `append()` retains one invariant: every stored frame has already been
folded into its current block summary.

### CC-D4: The trimming UI exposes an explicit destructive action

`CapturePanel` renders **Crop to selection** in both `trimming` and
`commit-error` phases. The action is disabled when the selection already spans
the whole current buffer, because that operation would have no visible effect.

On activation the panel calls `buffer.crop(selectionStart, selectionFrames)`
and dispatches the successful new frame count to the reducer. The reducer:

- stays in `trimming`;
- replaces `frameCount` with the cropped length;
- resets the selection to `{start: 0, frames: croppedLength}`;
- clears a prior Commit error and conflict flag; and
- retains the original recording stop reason.

The paint effect then requests `envelope(400, 0, croppedLength)` from the
mutated buffer. The user may choose a smaller selection and Crop again.

The action has no confirmation dialog and no Undo in this version. It is
explicitly named, occurs before persisted Commit, and the approved first slice
keeps only Discard/re-record as recovery from an unwanted crop.

### CC-D5: Commit remains compatible and byte-exact

The `onCommit(buffer, selection)` boundary does not change. After Crop, Commit
receives the same `CaptureBuffer` instance and the rebased whole-buffer
selection `{startFrame: 0, frameCount: buffer.frameCount}`. The committed PCM
must be byte-equivalent to committing the same selected frames before Crop.

Crop during `commit-error` removes the obsolete error before another Commit.
An unsuccessful Commit still retains the already-cropped buffer for retry;
Commit failure never restores discarded frames or mutates the buffer again.

## State and Data Flow

```text
recording
  -> Stop
  -> trimming(original buffer, bounded selection)
  -> Crop to selection
  -> CaptureBuffer.crop(start, count)
       prepare replacement PCM + block peaks
       atomically publish chunks/starts/frames/peaks
       invalidate envelope cache
  -> trimming(cropped buffer, selection 0..count)
  -> optional repeated selection + Crop
  -> Commit(existing buffer + selection contract)
```

The capture buffer remains Host-local ephemeral state. Project Truth changes
only through the existing successful Commit path.

## Failure Handling

- `CaptureBuffer.crop()` rejects non-integer, empty, negative, or
  out-of-buffer ranges with `RangeError` and preserves every observable buffer
  value.
- The UI calls Crop only from reducer-validated trimming selections, so an
  invalid-range exception is an invariant violation rather than a new product
  error class.
- Replacement arrays and summaries are prepared before assignment. No partial
  mutation is published.
- Existing Commit conflict/failure handling is unchanged; cropping from that
  state clears the obsolete error and returns to ordinary trimming.

## Correctness and Acceptance

### Buffer tests

- Crop retains exact mono and stereo samples across arbitrary append chunks
  and rebases them to frame zero.
- Invalid Crop ranges throw without changing frame count, sliced PCM, cached
  envelope identity, or summary results.
- A high peak outside the selected range but inside the same old summary block
  cannot leak into the cropped envelope.
- Summary-path envelopes after Crop match an exact oracle, including partial
  first/last blocks and stereo maximum folding.
- Repeated Crop produces the expected PCM and envelope.
- Appending after Crop extends the cropped data and its partial block summary
  correctly.

### Reducer and component tests

- The reducer accepts a successful Crop only in `trimming` or `commit-error`,
  resets selection/frame count, clears error/conflict, and retains stop reason.
- The button is disabled for a whole-buffer selection and enabled for a strict
  subset.
- Clicking Crop mutates the same buffer instance, repaints the rebased whole
  cropped range, and supports another selection/Crop cycle.
- Crop from `commit-error` clears the alert.
- Commit after Crop receives `{startFrame: 0, frameCount: croppedLength}` and
  exact cropped PCM.

### Verification layers

- Focused CaptureBuffer, reducer, and CapturePanel tests.
- Complete Creator Vitest suite and production build.
- Clean-source Creator Proof, including the packaged Chromium/WebKit lanes.
- Product/version, generated identity, dependency, active-tree, module-graph,
  and Core Proof checks required by the final changed-file inventory.
- Full Architecture Portal check and immutable `1.0.30.0 · canary` snapshot
  provenance verification.

Automated evidence does not claim a new real-microphone, hearing, Safari,
iPadOS, deployment, release, or Channel acceptance session.

## Alternatives Rejected

- **One-level Undo retaining the original buffer:** rejected for the first
  slice because it doubles peak capture memory, adds edit-history ownership,
  and is not required to make pre-commit mutation or invalidation real.
- **A lazy crop window over the original buffer:** rejected because it is
  another selection alias, not buffer editing, and would leave #213's mutation
  premise unexercised.
- **Apply Crop only while encoding Commit:** rejected because the existing
  Commit selection already does that; it would add no pre-commit edit and no
  visible rebased buffer.
- **Clear summaries and rebuild lazily on the next envelope:** rejected because
  it introduces a second validity state and permits the first post-edit redraw
  to become the hidden repair boundary.

## Version Management

- Product Build: `1.0.29.0 -> 1.0.30.0`. This is the already reserved Build for
  the #213 pre-commit Crop capability; the change updates Creator identity in
  Product Assembly and therefore cannot use a Product PATCH.
- Creator Web Host: `1.3.6 -> 1.4.0`. Crop is a new backwards-compatible Host
  capability, so MINOR changes while Host API version `1` remains unchanged.
- Core Module, Formal Web Runtime Host, Provider, Contract, and persisted
  Project identities do not change.
- Stage 9 remains allocated to Product Build `1.0.31.0`; this Task does not
  consume or move that identity.
- A clean committed source revision for `1.0.30.0` must be frozen as the
  immutable `canary` Portal snapshot. The snapshot is evidence, not a tag,
  Release, deployment, publication, or Channel promotion.

## Documentation Impact

Documentation impact: required.

Affected Portal routes:

- `/overview/`
- `/assembly/lmdj/`
- `/hosts/overview/`
- `/hosts/creator-web/`
- `/hosts/web-runtime/`
- `/platform/input/`
- `/platform/web-runtime/`
- `/product/capability-map/`
- `/product/workflows/`
- `/operations/testing-and-proof/`
- `/operations/version-and-release/`

Reason: Creator gains a new pre-commit Crop workflow, Creator/Product Assembly
identities change, automated proof changes, and Product Build `1.0.30.0`
requires a matching immutable Portal snapshot. No architecture source diagram
changes because the Host, Platform, Facade, Contract, Provider, and Project
boundaries remain unchanged.
