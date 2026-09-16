# Creator UI migration acceptance ledger

Date: 2026-09-16. Task: U7 ([#1221](https://github.com/endaye/lmdj/issues/1221)).

**Status: U7's physical rows are not accepted. The default layout is switched
anyway, by owner decision** (§7). The hardware four-region layout is the
only layout: U8 removed the workspace shell the same day, by the same decision. This ledger records what was
actually established and what was not; it is not a release record and
allocates no Product Build.

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
| Perform | `ModeRail` → `PerformSurface` | `Perform` physical key → `PerformSurface` (same component) | reachable; see §3.5 for the deliberate gating difference |
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

## 6. Physical and manual rows

These are the rows U7's exit condition turns on. Every one is `deferred /
unverified`: no physical acceptance of the four-region layout has been
performed.

| Platform | Journey | Reused tracking | Status |
| --- | --- | --- | --- |
| iPadOS Safari | Four-region touch ergonomics: 80 × 80 Pad aiming, 32 × 32 physical keys under a real finger, the 368 × 368 touch workspace's faders and segments | [#248](https://github.com/endaye/lmdj/issues/248), [#365](https://github.com/endaye/lmdj/issues/365) | `deferred / unverified` |
| macOS Safari | Hardware layout pointer journey and subjective hearing across the six workspaces | [#362](https://github.com/endaye/lmdj/issues/362) | `deferred / unverified` |
| macOS Chrome | Hardware layout pointer journey and subjective hearing across the six workspaces | [#366](https://github.com/endaye/lmdj/issues/366) | `deferred / unverified` |
| iPadOS Safari | Assistive technology over the four-region shell: the read-only upper screen's announcement, physical-key navigation, focus after a mode switch | — | `deferred / unverified` |
| macOS + iPadOS | 200 % browser zoom, and the small-viewport path beyond the 768 × 600 the packaged journey already asserts | — | `deferred / unverified` |
| macOS Safari, iPadOS Safari | Device lifecycle in the hardware layout: background, lock screen, interruption, continuous OPFS recording | [#249](https://github.com/endaye/lmdj/issues/249), [#717](https://github.com/endaye/lmdj/issues/717), [#718](https://github.com/endaye/lmdj/issues/718), [#720](https://github.com/endaye/lmdj/issues/720) | `deferred / unverified` |
| macOS, iPadOS | Physical MIDI Pad and control input in the hardware layout | [#243](https://github.com/endaye/lmdj/issues/243) | `deferred / unverified` |
| iPadOS Safari | Same-origin fallback during an armed Pad capture or a playing/recording transport — the legs §5's drill deliberately does not cover | — | `deferred / unverified` |
| any | No-guidance usability: a non-developer reaches the four regions without being told how | [#251](https://github.com/endaye/lmdj/issues/251) | `deferred / unverified` |

Automation does not convert any row above into a pass. Neither does a Product
Build allocation, an immutable snapshot, a Release, a deployment, or a green
`scripts/creator-web.sh proof`. Listing a tracking Issue is reuse of its
evidence boundary, not a claim about its state; none of them is closed by this
ledger.

### What a row must record

A row moves off `deferred / unverified` only with the per-leg observable
results U7 asks for, not a screenshot and not an impression. For each journey
leg, record what was observable after the transition in all five shapes:

1. the normal result;
2. the refusal, where the product declines;
3. the failure, where something breaks;
4. cancel or back;
5. what is there after reopening.

A leg that was not exercised stays an explicit gap inside the row. A row with
any unexercised leg is not a pass.

### Retained evidence per row

| Field | Where it comes from |
| --- | --- |
| Product Build | the report's identity block, `product_build` |
| Host id and version, platform version, protocol version | the same identity block |
| Export report revision, admitted / outcomes / rejected counts, SHA-256 | Creator's `Export report`, which calls `createAcceptanceReport` |
| Device model, OS version, browser version | recorded by the operator |
| Operator and date | recorded by the operator |
| Origin the Build was served from | recorded by the operator |

The completed precedent is [#245](https://github.com/endaye/lmdj/issues/245):
*"passed on deployed Product Build 1.0.41.0. The retained refreshed report is
revision 83 with 2 admitted / 2 outcomes / 0 rejected and SHA-256 fb87f54f…"*.

Whether a locally served Build can stand in for a deployed one is not settled
here. This ledger records the origin a row was observed from and leaves that
judgement to the release and product owners; it does not quietly widen the
precedent above.

### Exploratory observations, which upgrade no row

| Date | Device | Origin | Observation |
| --- | --- | --- | --- |
| 2026-09-17 | iPad Air 6, iPadOS Safari | `https://endaye-mbp-m1.tail2c9ce3.ts.net/` — a tailnet-only HTTPS proxy in front of a locally served distribution | The four-region layout was exercised by hand and reported as no problems found, including the 32 × 32 physical keys. |

That session established the path works: a real browser on that origin reports
`isSecureContext`, `crossOriginIsolated`, `sharedArrayBuffer`, `webAssembly`,
`audioWorklet` and `opfs` all true, so the Runtime's fail-closed preflight
passes and the Host boots. Plain HTTP to a LAN address does not: the server
already sends `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp`, but a non-loopback HTTP origin is
not a secure context, so `SharedArrayBuffer` is absent and preflight refuses
with `UNSUPPORTED_WEB_RUNTIME`.

It upgrades no row. It ran against a locally served distribution rather than a
deployed Product Build, no per-leg observable results were recorded in the
five shapes above, and no Export report was retained. It is recorded because a
real device was used and the result was positive, and because the next
operator should not have to rediscover the secure-context constraint.

## 7. Why the default is switched — owner decision, 2026-09-17

U7's exit condition requires the full Creator proof and its new journeys to
pass, applicable real-device candidate evidence to exist, and no unreachable
key function, unrecoverable edit loss or false success. The proof passes and
the false success it named is fixed and gated. Every row in §6 is still
`deferred / unverified`.

On 2026-09-17 the repository owner directed that the hardware layout become
the default and that the workspace layout then be removed (U8), on the
strength of the exploratory iPad session recorded in §6 and the automated
evidence in §5, without waiting for the §6 rows. This section records that as
what it is: an owner decision to proceed ahead of acceptance. It is not
acceptance. No §6 row is upgraded by it, and none may be upgraded by citing
it. The rows stay open for the operator who eventually runs them, against
whatever Build is then deployed.

What the switch did: `readCreatorLayout` and `readStoredCreatorLayout` default
to `hardware`; a stored `workspace` preference and `?layout=workspace` are
still honoured; `Existing workspace` still returns to the old shell. The upper
screen gained `Pads` and `Assets` facts so the shell no longer shows less
Project truth than the summary it replaced.

Discharging a named U7 risk is not discharging U7, and switching the default
by decision is not discharging it either.

### U8, same decision

The owner also directed that the workspace shell be removed rather than kept
as a fallback through an observation period. U8's plan text asked for that
period; this records that it was waived. What U8 removed: the `layout` state,
the `Existing workspace` and `Hardware layout` controls, `?layout=`, the
`lmdj.creator.layout` preference (the stale key is removed once on boot so no
browser resolves a shell that no longer exists), `SequenceSurface`,
`SequenceTransport`, `StatusBar`, `ModeRail`, the `.workspace` grid and the
styles only it used, and the tests and journey legs whose premise was a
fallback. `CreatorMode`, `midiLabel` and `transportStatusLabel` moved to
`creator_mode.ts`, `midi_status.ts` and `transport_status.ts`; the four-region
shell still consumes all three. `BankSelector`, `ProjectSurface` and every mode
surface are shared and stay. The mode rail's `aria-current` exposure retired
with the rail; the active mode is exposed by the upper screen's context label.
