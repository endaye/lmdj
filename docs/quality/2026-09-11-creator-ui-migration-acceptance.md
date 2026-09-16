# Creator UI migration acceptance ledger

Date: 2026-09-16. Task: U7 ([#1221](https://github.com/endaye/lmdj/issues/1221)).

**Status: U7 is not complete. The default layout is not switched.** The
hardware four-region layout stays opt-in behind `?layout=hardware` and the
`Hardware layout` button, and the existing workspace stays reachable through
`Existing workspace`. This ledger records what was actually established and
what was not; it is not a release record and allocates no Product Build.

## 1. What this ledger covers

U7's first acceptance item is the six-workspace coverage comparison: every
existing operation must have an entry point in the new layout, or a usable
fallback to the old one. This section records that comparison, the differences
that are not gaps, the one defect it found, and the evidence that is still
missing.

The comparison was made mechanically, by rendering the same `CreatorState` in
both layouts and diffing the accessible names of every `button`, `textbox`,
`combobox`, `slider`, `spinbutton` and `checkbox` per mode. It is a DOM
reachability comparison in jsdom, not a geometry, pointer or hearing check;
browser geometry is asserted by
`tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`, and jsdom
never stands in for it.

## 2. Reachability by mode

| Mode | Workspace entry | Hardware entry | Verdict |
| --- | --- | --- | --- |
| Project | `ModeRail` → `ProjectSurface` | `Project` physical key → `ProjectTouchWorkspace` | reachable; `Open local`, `Import .lmdj`, per-Project `Open` all present |
| Sample | `ModeRail` → `SampleSurface` | `Sample` physical key → `SampleSurface` (same component) | reachable; identical inventory |
| Sequence | `ModeRail` → `SequenceSurface` | `Sequence` physical key → `SequenceTouchWorkspace` | reachable; see §4 for the gating defect this comparison found |
| Perform | `ModeRail` → `PerformSurface` | `Perform` physical key → `PerformSurface` (same component) | reachable; see §3.4 for the deliberate gating difference |
| Slice | `ModeRail` → `CandidateSurface` | `Slice` touch button → `CandidateSurface` | reachable; both gate on the same `sliceEnabled` |
| Sound Sets | `ModeRail` → `SoundSetSurface` | `Sound Sets` touch button → `SoundSetSurface` | reachable; both gate on the same `soundSetEnabled` |

Global Runtime actions — `Activate audio`, `Suspend audio`, `Enable MIDI`,
`Export report` — appear in the workspace `StatusBar` and in the hardware
`System` touch section, gated identically. No Runtime action is reachable in
one layout only.

## 3. Differences that are not coverage gaps

Each of these appeared in the mechanical diff and each was checked rather than
waved through.

1. **Layout entry pair.** `Hardware layout` exists only in the workspace and
   `Existing workspace` only in the hardware layout. That is the opt-in and
   the fallback, not a missing control.
2. **Mode control naming.** The workspace rail renders `▣Project` / `∿Sample`
   with glyphs; the hardware physical keys render `Project` / `Sample`. The
   accessible names are the Figma names in both, and both carry the same
   disabled reason text when a mode is unreachable.
3. **Pad key hints.** Hardware Pads are named `Pad A1 — empty — Key Q`;
   workspace Pads in Sequence and Perform are named `Pad A1 — empty`. Same
   control, same slot identity, one extra hint. Pad identity is asserted to
   survive every hardware mode switch in `workspace_shell.test.tsx`.
4. **Sample assignment depth.** In the workspace layout, `Add Sample to Pad A1`
   and `Record Sample` also render under Sequence and Perform, because the old
   shell keeps one pad strip below every mode. In the hardware layout they
   live in Sample mode only. The operations remain reachable, one mode switch
   away; this is a navigation-depth difference, recorded here rather than
   treated as equivalent.
5. **Perform gating.** The workspace rail requires a Perform controller and
   configured capture before Perform is reachable; the hardware `Perform` key
   requires only a ready Project. This difference is deliberate and is left
   in place: the hardware Perform workspace renders a placeholder that states
   `Launch and FX wait for running audio and capture storage`, so the looser
   key leads to an honest explanation rather than to controls that appear
   operable. `workspace_shell.test.tsx` asserts that placeholder.

## 4. Defect found and fixed by this comparison

The hardware `Sequence` physical key gated on `project.phase === "ready" &&
project.current !== null`, while the workspace mode rail gated the same mode on
`isSequenceSession(session) && …`. With a ready Project behind a session that
carries no Sequence capability the two layouts disagreed:

| | Workspace rail | Hardware key (before) |
| --- | --- | --- |
| Accessible name | `Sequence — open a playable Project first` | `Sequence` |
| Disabled | yes | no |
| On activation | unreachable | full `SequenceTouchWorkspace` mounts |

The mounted editor offered `Apply BPM`, `Apply Swing`, `Create Pattern`,
`Refresh authority`, the Pattern selector and both sliders. Every one of their
handlers begins with `if (!isSequenceSession(session) …) return`, so each
control accepted the interaction and silently did nothing — no refusal, no
alert, no disabled state. That is a false success, which U7's exit condition
forbids by name.

The hardware key now consumes the same `sequenceEnabled` value the rail
consumes, so both layouts answer the reachability question from one source.
`gates the hardware Sequence key on the same reachability as the mode rail` in
`apps/creator-web/test/workspace_shell.test.tsx` locks this: it asserts the two
layouts agree on the accessible name and the disabled state, and that no
Sequence editor or `Apply BPM` mounts behind a disabled key. Reverting the fix
fails that test with
`expected 'Sequence' to be 'Sequence — open a playable Project fi…'`.

Perform's looser gate (§3.5) is retained on purpose and is not the same defect:
it degrades to a stated reason instead of to silent no-ops.

## 5. Evidence

### Established here

- Mechanical six-mode reachability comparison of both layouts, §2 and §3.
- `npm --prefix apps/creator-web test -- --run test/workspace_shell.test.tsx test/hardware_console.test.tsx test/shell_polish.test.tsx test/perform_surface.test.tsx test/sequence_surface.test.tsx` — 5 files, 144 tests passed.
- Perturbation proof of the new gate, §4.
- `scripts/creator-web.sh proof` — exit 0 end to end, chromium lane 55 passed,
  including the layout fallback drill added for this ledger entry. The proof
  entry itself was unusable until the reds in #1433, #1436 and #1427 were
  cleared; those are fixed and merged.

### Not established — these block the default switch

- **Real-device touch acceptance.** No touch device ran this layout. The
  368 × 368 Pad and touch regions and the 32 × 32 physical keys have never
  been exercised by a finger, only by synthetic pointer events.
- **Real hearing acceptance.** No listening pass was made in the hardware
  layout. Automation asserts state transitions, never that the instrument
  sounded correct.
- **Assistive-technology acceptance.** Accessible names and roles are
  asserted in jsdom and in
  `tests/platform/web/creator/creator_web_accessibility.spec.mjs`; no screen
  reader or switch-access pass was made against the four-region shell.
- **200 % zoom acceptance.** No recorded observation. Playwright exposes no
  browser zoom, and emulating it with a viewport change or CSS `zoom` would be
  a different thing wearing its name, so this stays an explicit gap rather
  than a proxy. The small-viewport half is covered: `opts into the 880×592
  hardware shell, keeps overview read-only, and returns` drops the viewport to
  768×600 and asserts the fallback control stays reachable and the upper
  screen still carries no button. An earlier revision of this ledger listed
  both halves as unobserved; that was wrong about the small-viewport one.
- **Same-origin fallback drill under an active capture or a live transport.**
  `carries Project Truth and running audio across a layout fallback drill`
  now walks the boundary with an open Project, running audio and an unapplied
  Tempo draft: into the hardware shell, back to the existing workspace, in
  again, then a reload, asserting after every transition that the published
  tempo never moved and that the Runtime survived — and, after the reload,
  that audio honestly did not. What that drill does not cover is a switch
  during an armed Pad capture or a playing/recording transport; those legs
  remain unobserved.
- **Device-lifecycle legs.** The existing device tasks (#248, #249, #251,
  #243, #250, #360, #721, #1167, #961) have no candidate evidence recorded
  against the current hardware layout. They stay open; none of them is closed
  by this ledger.

## 6. Why the default is not switched

U7's exit condition requires the full Creator proof and its new journeys to
pass, applicable real-device candidate evidence to exist, and no unreachable
key function, unrecoverable edit loss or false success. §5 lists six classes of
evidence that do not exist yet, all of them about real devices and real
hearing. Under the plan's own instruction — stop at the evidence gap, do not
switch the default, do not lower a test to make a run green — the layout stays
opt-in and U8 stays blocked.

The one false success this comparison did find is fixed and gated. That
discharges a named U7 risk; it does not discharge U7.
