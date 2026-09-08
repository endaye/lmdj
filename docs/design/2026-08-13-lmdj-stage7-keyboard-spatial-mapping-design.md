# LMDJ Stage 7 Keyboard Spatial Mapping Design

**Date:** 2026-08-13

**Status:** proposed for written review

**Scope:** Creator Web default keyboard mapping and visible Pad key hints

## 1. Problem

Creator Web renders one Bank as sixteen stable Pad addresses in ascending visual
order. In the current 4 x 4 layout, Pads 1-8 occupy the upper half and Pads
9-16 occupy the lower half. The current default mapping does the opposite in
physical keyboard space:

- the lower `A S D F G H J K` row triggers Pads 1-8;
- the upper `Q W E R T Y U I` row triggers Pads 9-16.

Stage 7 also requires each Pad to display its keyboard mapping, but the current
Pad surface displays only the Pad address and assignment state. With no visible
bottom-origin convention, the existing mapping conflicts with the spatial model
presented by the UI and makes the mapping harder to learn.

## 2. Decision

Use the physical keyboard's top-to-bottom order as the default Pad order for
every active Bank:

| Physical key row | Local Pad indexes | Visible Pad addresses |
| --- | --- | --- |
| `Q W E R T Y U I` | `0..7` | `1..8` |
| `A S D F G H J K` | `8..15` | `9..16` |

The mapping continues to use `KeyboardEvent.code`, not localized character
values. Bank selection continues to add the active Bank's stable sixteen-Slot
offset. Therefore `Q` triggers A1, B1, C1, or D1 according to the selected Bank,
and `K` triggers A16, B16, C16, or D16.

Each Pad displays its physical key hint from the same exported default mapping
used by the keyboard adapter. The visible hint uses a semantic `kbd` element,
and the accessible name includes the key. No second hard-coded key table is
introduced in Creator Web.

## 3. Alternatives considered

### 3.1 Keep the mapping and reverse visual Pad order

Rejected. Pad addresses are stable product identities shared by Pointer, MIDI,
Project Truth, Runtime Snapshot, reports, and later editors. Reversing the UI to
fit one input adapter would make the rest of the product harder to understand.

### 3.2 Keep the current mapping and add labels only

Rejected. Labels would document the spatial inversion rather than remove it.
This is acceptable only for an explicitly designed bottom-origin hardware
convention, which Stage 7 does not declare or visualize.

### 3.3 Swap the two rows and show labels

Selected. This preserves stable Pad identity, aligns the physical and visual
vertical order, and fulfills the existing Stage 7 key-hint requirement.

## 4. Boundaries

This change modifies only the default physical-keyboard interaction:

- Pointer and Touch continue to trigger the selected Pad directly.
- MIDI note mapping is unchanged.
- Project Truth, Bundle, Runtime Snapshot, Provider, audio, and persistence
  Contracts are unchanged.
- Bank addresses and flattened Slot identities are unchanged.
- Input lifecycle rules remain unchanged: repeat is ignored, editable targets
  suppress shortcuts, and blur/visibility/disposal releases pressed state.
- User-remappable keyboard settings remain future scope; the displayed hint is
  sourced from the active Stage 7 default map.

Import recovery and Audio suspend lifecycle behavior are outside this change.

## 5. UI behavior

In the current 4 x 4 layout, the visible key hints are:

```text
Q  W  E  R      Pads 1-4
T  Y  U  I      Pads 5-8
A  S  D  F      Pads 9-12
G  H  J  K      Pads 13-16
```

If the desktop surface later renders as 8 x 2, the same mapping naturally
becomes one physical key row per visual Pad row. Responsive reflow does not
change Slot order or mapping.

The key hint is secondary metadata: Pad address remains the primary label and
assignment/outcome remains the primary state. The hint must remain legible in
idle, disabled, admitted, started, and capacity states without relying on color.

## 6. Verification

Automated verification must prove:

1. the one frozen platform mapping is exactly `Q..I -> 0..7` and
   `A..K -> 8..15`;
2. Creator's selected-Bank offset maps representative keys (`Q`, `I`, `A`,
   `K`) to the correct stable Slots;
3. every visible Pad renders the key obtained from that mapping, including in
   accessible names, with no duplicate Creator key table;
4. packaged Chromium exercises all sixteen keys and asserts the corresponding
   Pad admission/outcome addresses;
5. existing repeat, editable-focus, release, blur, visibility, MIDI, Pointer,
   and lifecycle tests remain green;
6. Creator Proof, Web Runtime Host Proof, Core Proof, dependency/active-tree,
   version, Assembly Lock, and Architecture Portal gates pass.

Manual canary step 5 must record address correspondence, not only that every key
produces sound. Because the mapping changes the candidate's observable behavior,
the corrected package starts a new ten-step canary from step 1; results from the
1.0.19.0 package are not carried forward.

## 7. Version Management

Version impact: required.

Based on the current branch identities, implementation allocates provisional
targets below. The implementation plan must re-read the merged baseline and
choose the next unused identities before editing version files.

| Identity | Current | Provisional target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.19.0` | `1.0.20.0` | Observable Host behavior and Assembly identities change. |
| `web-runtime-platform` | `0.2.0` | `0.2.1` | Correct the shared default keyboard map without changing its API shape. |
| `creator-web` | `1.1.1` | `1.1.2` | Correct keyboard behavior and expose the existing key-hint requirement. |
| `web-runtime-host` | `1.2.7` | `1.2.8` | Propagate the exact Platform dependency; diagnostic UI semantics otherwise remain unchanged. |
| Project/Bundle/Error Contracts | current | unchanged | No Contract shape or semantic change. |

The Product Build receives a new immutable `canary` Architecture Portal
snapshot only after the implementation source is clean and committed.

## 8. Documentation impact

Documentation impact: required.

Implementation updates:

- the current Creator Host and Product Build facts in the Architecture Portal;
- `/hosts/creator-web/` key mapping behavior;
- the Stage 7 manual acceptance wording so physical keys are checked against
  exact Pad addresses;
- a new immutable Product Build `canary` snapshot and new release-evidence
  record for the corrected package.

The 1.0.19.0 evidence remains immutable historical evidence and is not rewritten
to claim the corrected mapping.
