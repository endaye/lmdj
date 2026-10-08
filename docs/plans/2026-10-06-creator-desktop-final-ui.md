# Creator：对齐 Figma Desktop Final 新界面（#1207）

## Outcome and authority

Creator Web's four-zone hardware console reaches the Figma **Desktop Final** design: one visual system and type face across all four pages, and the decided D02 Sequence revision.

This plan revises a layout that already exists. It does not migrate from an older one. The earlier migration ([`2026-09-11-creator-ui-migration.md`](2026-09-11-creator-ui-migration.md), U0–U8) already delivered the 880×592 console and removed the old layout. That plan's Global Constraints still apply:

- Hosts use only the Facade.
- Layout and view preferences stay out of Project Truth.
- A control drawn in Figma is not assumed to have a runtime action.

Authority, in precedence order:

1. **Product decisions**, which win over the drawing where they differ:
   - [`2026-10-07-pad-colour-source.md`](../prd/decisions/2026-10-07-pad-colour-source.md) (category defaults, five-colour user override and persistence; T7 addendum below);
   - [`2026-10-04-sequence-hardware-ui-revision.md`](../prd/decisions/2026-10-04-sequence-hardware-ui-revision.md) (D02 Sequence);
   - [`2026-10-02-sequence-grid-editing.md`](../prd/decisions/2026-10-02-sequence-grid-editing.md) and its [live-edit erratum](../prd/decisions/2026-10-02-sequence-grid-live-edit.md);
   - [`2026-10-02-creator-tempo-metronome.md`](../prd/decisions/2026-10-02-creator-tempo-metronome.md);
   - [`2026-09-29-creator-user-workflow-baseline.md`](../prd/decisions/2026-09-29-creator-user-workflow-baseline.md).
2. **Figma Desktop Final** (`GPFarNiZNsjLQzfG9kR8DO`, page 0:1, START HERE 252:42). This is the layout and visual source only.
   - Pages: D01 Project 88:1569, D02 Sequence 88:706, D03 Sample 88:1892, D04 Perform 88:2389, D04a filter states 95:746.
   - Developer notes: 91:754, 91:746, 91:762, 91:770.
   - The design's own boundary note (252:61) says feature scope and persistence semantics follow the implementation Tasks and product Contracts, not the drawing.
3. **Out of authority:** page 69:666 (the older Hardware Sequence baseline) and Figma page 99 (archive). The Mobile & iPad page 02 is out of scope for this plan.

Each Task is one Conventional Commit on its own short-lived `feat/` branch, with verified commit, push, current-head review and squash merge. No Task releases, allocates a Product Build or cleans worktrees.

## Facts this plan relies on

Checked on `43c7f136f`.

- **Stack.**
  - `apps/creator-web` is React 19 with Vite and Vitest. The Host is `creator-web` 5.0.1, depending on `web-runtime-platform` 5.7.0.
  - `app.tsx` (about 2900 lines) owns mode selection and touch-workspace routing.
- **Styling.**
  - One stylesheet, `src/styles.css`, about 1480 lines.
  - Every colour is hard-coded hex. There are no design tokens.
  - The font stack is `Inter, ui-sans-serif, system-ui`.
  - No font file is bundled, so nothing typographic is in the offline shell (`src/runtime/offline_shell.ts`).
- **Geometry.**
  - `.hardware-console` is a fixed 880×592 box with absolutely positioned zones: physical column 80×560, overview 752×176, Pad matrix and touch workspace 368×368 each. These match Desktop Final.
  - A short viewport scrolls the stage instead of scaling it. `creator_web_hardware_layout.spec.mjs` asserts the 768×600 scrolling leg, and portrait under 960 px rotates the stage.
- **Upper screen.**
  - `overview_display.tsx` dispatches to `project_overview.tsx`, `sample_overview.tsx`, `sequence_overview.tsx` and `perform_overview.tsx`.
  - Sequence currently draws the 64-row thumbnail that the 10-04 decision replaces.
- **Physical controls** (`physical_controls.tsx`).
  - Four encoders are rendered disabled ("unassigned until hardware mapping is approved").
  - `←`/`→` only perform Undo/Redo with SHIFT. `↑`/`↓` are disabled.
- **Pad addressing.** `state/view_model.ts:9` `padAddress` yields `A1`. Accessible names such as `Pad A1 — assigned — Key Q` are pinned by about 370 test matches.
- **Sequence touch** (`sequence_touch_workspace.tsx`).
  - It already has a `GROOVE / NN` header.
  - Patterns are still chosen with a native `<select>`. Tempo, Swing, Bars and TAP share one screen with `sequence_grid.tsx`.
- **D04.** `fx_slider_bank.tsx` renders live Filter and Delay faders and puts the rest behind FX / MORE. The MASTER fader and the LP/HP/BP type have no Host action and are deliberately not rendered.
- **D01.** The Project page has no Save or Save As action, because authoring commits go straight to Truth.
- **Tests.**
  - About 70 Vitest files and 18 Playwright Creator specs under `tests/platform/web/creator/`.
  - There are no screenshot comparisons. Geometry is pinned by bounding boxes in the hardware-layout journey.
  - The most-used DOM contracts are the `data-testid` values `audio-state`, `creator-phase`, `physical-controls`, `touch-workspace`, `sequence-grid*`, `pad-matrix`, `overview-display` and `hardware-console`, plus role and name selectors on the mode, Bank, System and Undo buttons.
- **Concurrent work.** Draft PR #1741 (`feat/p1-integration-proof`) edits `app.tsx`, `physical_controls.tsx`, `pad_surface.tsx`, `perform_surface.tsx`, `sample_surface.tsx` and `system_surface.tsx`, and already conflicts with `main`. Each Task rechecks it before starting.

## Blocked or undecided — not settled by this plan

| Item | Tracking | Effect on this plan |
|---|---|---|
| Pad colour Contract/Core and Host projection implementation | [#1821 decision](../prd/decisions/2026-10-07-pad-colour-source.md) | The product choice is settled: category default plus a persistent user override from five colours. T7 waits for its independent Contract/Core plan and implementation; current colours remain until then. |
| ENC1, `↑`/`↓`, and the encoders and keys on Project, Sample and Perform | #1822 | T6 wires only the decided Sequence controls. Everything else stays disabled. |
| Semantics of changing an existing Pattern's length (`BARS`) and of `COPY` | #1823 | T8 (Core and Host operations) waits. Until then T5 shows `BARS` as read-only and does not render `COPY`. |
| D01 Save / Save As / unsaved-changes confirmation | new question | Not rendered, because there is no Host action. Needs a product decision before any Task adds them. |
| D03 Assign → Pad target confirmation; the "tap to edit" fine-adjust editor (D02 and D03) | new question | Not drawn in Figma. T10 restyles the existing assign and numeric entry and invents no new flow. |
| D04 MASTER fader, LP/HP/BP type, Mute/Solo on the TARGET Pad | new question | Rendered only where a Host action exists. The others stay out, as `fx_slider_bank.tsx` already documents. |
| Figma D02 lags the 10-04 decision | design update (owner) | Before T4/T5 review, the owner updates D02 or confirms that the decision text is the reference. |

## T1 — design tokens and the console font stack

Amended when T1 started. The distribution CSP (`apps/creator-web/deploy/_headers`, which `apps/web-runtime-host/tools/deployment_smoke.py` matches exactly) has `default-src 'none'` and no `font-src`. It blocks every web font, whether a same-origin file or a `data:` URI. On 2026-10-06 the owner split font bundling into T1b. Button isolation moves to T5, where the touch kit takes over the styles the global `button` rule now supplies.

**Behaviour.**

- **Tokens.** `:root` declares the Desktop Final colours as `--creator-*` custom properties. Only the ones in use are declared: base, screen, touch, raised, line, text, muted, lime, blue, purple, blue tint and purple tint.
  - Every stylesheet literal equal to one of those values now reads the token.
  - Accents are named by hue, not page. These shared UI accents are separate from the five Pad category colours decided on 10-07; T7 owns that mapping and its selected-state distinction.
  - Radius and spacing tokens arrive with their first consumer, the T5 kit.
- **Shared surfaces.** The console and the upper screen take the Desktop Final surfaces: `#202321` (was `#22241f`) and `#292d29` (was `#141613`).
- **Font.** The console body uses a stack that starts with IBM Plex Mono and falls back to the system monospace font.

**Declared files.** `apps/creator-web/src/styles.css`, `apps/creator-web/test/hardware_console.test.tsx`, this plan, and portal `/hosts/creator-web/`.

**Lowest-tier tests.** A component test that the console resolves the mono stack and the two surface tokens. A revert of the stylesheet fails it.

**Gate defect caught.** The console silently keeping the old sans-serif face or the old surfaces.

## T1b — bundle IBM Plex Mono (needs a CSP `font-src`)

**Behaviour.**

- Bundle IBM Plex Mono Regular (OFL, Latin subset) with Creator, so that it ships inside the packaged, offline-cached Host.
- Add the narrowest `font-src` the bundling needs to the Creator CSP. Update the deployment smoke's expected CSP in the same change.
- Keep validating previously published deployments, which carry the old CSP, as rollback anchors (see the `manifest-role-validator-sync` pitfall for that failure shape).

**Lowest-tier tests.**

- The deployment smoke accepts the new CSP and the prior published one.
- An offline journey leg resolves the bundled face (`document.fonts.check`).

This Task selects the batch-only `deploy_contract` lane.

## T2 — scale the whole console to fit the window (needs owner confirmation)

**2026-10-08: confirmed.** The owner confirmed that START HERE supersedes the scrolling short stage: the console scales proportionally to fit and centres, enlarging as well as shrinking.

**Behaviour.**

- START HERE asks for the device to scale proportionally and centre itself, keeping the internal layout and the aspect ratio. The console therefore scales by `min(viewportW / 880, viewportH / 592)`, centred.
- The portrait rotation rule stays. Hit-testing code (grid, waveform handles, faders) reads coordinates via `getBoundingClientRect` and is checked under scale.

**Why owner confirmation is needed.** This reverses the asserted behaviour that a short viewport scrolls the stage (hardware-layout journey, 768×600 leg). It ships only once the owner confirms that START HERE supersedes it. Otherwise T2 is dropped and no other Task depends on it.

**Declared files.** `src/styles.css`, a `hardware_console.tsx` scale hook, `creator_web_hardware_layout.spec.mjs`, and the grid, waveform and fader pointer tests.

**Lowest-tier tests.**

- A unit test of the scale computation.
- A journey that, at 1440×900, 768×600 and 1280×720, checks the console's box ratio is 880:592 and centred, and that a grid tap at a known cell still lands on that cell.

## T3 — Pad address `A01` everywhere

**Behaviour.**

- `padAddress` yields the Bank letter plus a two-digit number (`A01`–`D16`). This is item 2 of the 10-04 decision.
- Every Creator label and accessible name follows: Pad matrix, overview, grid rows, Sample and Perform targets, and error text.
- Keyboard shortcut labels do not change.
- This mechanical rename is isolated from visual work so that a red journey points straight at the rename.

**Declared files.** `state/view_model.ts`, the components that format addresses, the Vitest files and Playwright specs and fixtures that select by Pad name, and portal `/hosts/creator-web/`.

**Lowest-tier tests.**

- A view-model test for `A01`, `A16` and `D16`.
- All existing journeys with selectors renamed, with no leg dropped.

## T4 — Sequence upper screen: 8 scrollable rows

**Behaviour** (10-04 decision, item 1).

- **Status and context lines.** IBM Plex Mono throughout.
  - The status line shows `SEQUENCE / NN`, BPM, Swing, and transport plus bar:beat (`STOPPED / 001:01`).
  - The context line shows the bar range and step count, the snap, `TRACKS A01–A08 / 64`, the Bank, and the selected-note count and velocity when notes are selected.
- **Rows.** Eight rows are shown, each 10 px tall with a 3 px gap. A narrow row-name column lists the address only.
  - Step cells are divided by the snap (1/16 when snap is off), with an alternating shade per beat.
  - A note's onset cell is solid and its tail is lighter.
- **Playhead and frame.** The live playhead and the frame marking the touch grid's visible window both stay.
- **Removed.** The Project/Rev/Pads/Assets/MIDI line goes.
- **Window state.** The window offset (0–56) is Creator view state, not Truth. Pressing a Bank key jumps it to that Bank's first row. Scrolling never changes the active Bank.

**Declared files.** `components/sequence_overview.tsx` (replacing the 64-row thumbnail), `state/sequence_grid_model.ts` for the row window, `components/bank_selector.tsx` wiring, `src/styles.css` and their tests, the Sequence grid journey, and portal `/hosts/creator-web/`.

**Lowest-tier tests.**

- Model: window clamping at 0 and 56, the Bank jump, snap and beat shading, onset vs tail cells.
- Component: the status and context text for a fixture Pattern, the playhead and the frame.
- Journey: record notes on B05, press Bank B, and the overview shows the B05 row with its notes.

## T5a — free the touch area: System entry on the brand mark

Added on 2026-10-07, when T5 started. Three controls added during P1 sit at the top of every page's touch area and take about 150 of its 336 px:

- the always-shown Pad recording source and status;
- Retry default sounds;
- the System button.

With them there, T5's EDIT layer cannot show all 16 grid rows. The owner chose to free that height in a separate Task before T5.

**Behaviour.**

- **System entry.** The brand mark at the top of the physical column becomes the System entry, keeping the accessible name "System". Desktop Final START HERE names the brand mark as the settings entry. Back to music returns focus to it. The touch area loses its System button.
- **Pad recording.** The row appears only while a take is recording, awaiting review or saving, or reporting a message.
- **Recording source.** The source selector moves into System.
- **Unchanged.** Retry default sounds still appears only on a default-sound failure. Sound Sets, Slice and their Back buttons are unchanged.

**Declared files.** `src/app.tsx`, `src/components/physical_controls.tsx`, `src/styles.css`, `test/workspace_shell.test.tsx`, `creator_web_perform.spec.mjs`, `creator_web_capture.spec.mjs`, this plan, and portal `/hosts/creator-web/`.

**Lowest-tier tests.** Component tests:

- System is not in the touch area, and the brand mark opens it;
- the rail's first tab stop is System;
- no Pad recording row appears while idle;
- System shows the remembered source;
- the row leaves once a take is resolved, and returns for the next take.

## T5 — Sequence touch area: EDIT/SETUP layers and the touch control kit

**Behaviour** (10-04 decision, items 6–7).

- **Touch control kit.** `TouchButton`, `SegmentedSelect`, `ToggleSwitch`, `ValueCard` and `PatternStepper` are built to the D02 spec: 44 px tall, 8 px radius, `--raised` fill, solid accent with dark text when selected. They replace native `<select>` and checkboxes inside the Sequence touch area. D01, D03 and D04 later reuse the kit. The kit also stops the global `button` rule from applying inside the console; this was moved here from T1.
- **Header.** `‹ GROOVE / NN ›` plus `current / total` replaces the Pattern combobox and is disabled while playing. EDIT and SETUP toggles sit on the right; EDIT is the default.
- **EDIT layer.**
  - One toolbar row: snap 1/4, 1/8, 1/16, 1/32 or off, plus NOTE/VEL.
  - The grid fills the remaining space: all 16 rows on one screen, one bar per screen width.
  - Box-selection delete and clear float at the grid's bottom right.
- **SETUP layer.**
  - Tempo and Swing cards with faders, labelled ENC 3 and ENC 4.
  - `BARS` shows the current Pattern's length, read-only until #1823.
  - Quantize and metronome toggles.
  - `+ NEW`, which then chooses the new Pattern's length using the existing new-Pattern behaviour, and `TAP`.
  - `COPY` is not rendered until #1823.
- **Grid editing.** Grid editing behaviour (#1671 T3) is unchanged, only re-laid out.
- **Implementation notes, recorded when T5 started.**
  - Selection uses aria-pressed toggle buttons rather than `radiogroup`/`switch`, keeping the existing Snap, Bars, mode and Metronome names.
  - `+ NEW` opens the length choice and then CREATE.
  - Refresh authority moves into SETUP.
  - With ‹ › disabled while playing, the Sequence journey's "switch while playing is refused by the Host" leg becomes "‹ › are disabled while playing and no Pattern reload is attempted".

**Declared files.** New `components/touch_kit/*.tsx`, `components/sequence_touch_workspace.tsx`, `components/sequence_grid.tsx` (layout only), `src/styles.css` and their tests, `creator_web_sequence.spec.mjs`, `creator_web_sequence_grid.spec.mjs`, `creator_web_metronome.spec.mjs`, and portal `/hosts/creator-web/` and `/product/workflows/`.

**Lowest-tier tests.**

- Kit components: keyboard and ARIA roles (`radiogroup`, `switch`), the selected state, the disabled state.
- Workspace: EDIT is the default, the layer switch keeps the grid selection, the stepper is disabled while playing, `BARS` reflects a 2-bar Pattern.
- Journey legs, each with a far-side Truth assertion:
  1. switch Pattern with the stepper;
  2. Tempo fader drag commits once on release;
  3. Quantize and metronome toggles;
  4. a grid edit in EDIT is still undoable.

## T6 — Sequence physical controls: ENC2–4 and `←`/`→`

**Behaviour** (10-04 decision, items 4–5).

- **Encoders.**
  - On the Sequence page, the encoder buttons gain a web input binding: wheel, vertical drag, and arrow keys when focused, each giving ±1 detent.
  - ENC2 scrolls the overview by one row.
  - ENC3 sets Tempo (±1 BPM) and ENC4 sets Swing (±1%). Both are locked while recording, using the existing locks.
- **Commit rule, proposed and adjustable in review.** The tempo decision says a drag previews and commits once on release, but an encoder has no release. Consecutive detents preview immediately and commit once after 400 ms without a detent, so one turn is one undo entry. The owner confirms or replaces this rule in T6 review; it is not settled silently.
- **Direction keys.**
  - Without SHIFT, `←`/`→` select the previous or next Pattern. They are refused while playing, and their indicator goes off when unavailable.
  - SHIFT+`←`/`→` remain Undo/Redo.
- **Other pages.** ENC1, `↑`/`↓`, and every control on other pages stay disabled (#1822).

**Declared files.** `components/physical_controls.tsx`, a new `state/encoder_input.ts`, the Sequence actions wiring in `app.tsx`, their tests, `creator_web_sequence.spec.mjs`, and portal `/hosts/creator-web/` and `/platform/input/`.

**Lowest-tier tests.**

- Encoder model: detent accumulation, idle commit, lock while recording.
- Journey legs:
  1. three ENC3 detents produce one Tempo commit of +3 BPM in `project.inspect` and one undo entry;
  2. ENC2 moves the overview window;
  3. `→` switches Pattern while stopped and is refused while playing;
  4. SHIFT+`←` still undoes.

## T7 — one Pad colour across matrix, overview and grid (Contract/Core prerequisite)

**2026-10-07 addendum.** [The Pad colour decision](../prd/decisions/2026-10-07-pad-colour-source.md) settles #1821: category provides the default, a user override selects one of D02's five colours and persists in Project Truth, re-separation preserves the override, and restore-default removes it. The Pad matrix border, overview lane and touch notes use one effective colour. Selected Pads use a white border plus a lime dot so that BASS does not masquerade as selected state.

**Prerequisite plan:** [`2026-10-08-pad-colour-contract-core.md`](2026-10-08-pad-colour-contract-core.md) (P1–P4), with the owner choices in [`2026-10-08-pad-colour-defaults-and-retention.md`](../prd/decisions/2026-10-08-pad-colour-defaults-and-retention.md). **Prerequisite.** A separate Contract/Core plan and its implementation must provide the category, stable palette-index override, authoring commands, migration and Facade/Host projection. It must explicitly settle unclassified/empty Pad defaults, stem-label mapping and Pad matching/retention during re-separation and assign/replace/clear/move. This plan does not invent those Contract details or implement persistence in Host preferences. T7 remains unimplemented until that prerequisite lands.

**Behaviour after the prerequisite.** Offer five-colour selection and restore-category-default, and use one effective-colour resolver for all three surfaces. The detailed control placement and exact declared files belong in the implementation addendum once the projection is designed.

**Lowest-tier verification to declare in that addendum.** Core tests cover category default versus explicit override, restore-default, preservation and migration. Creator component tests assert all three surfaces resolve the same colour and distinguish selected BASS. The packaged journey follows category default → manual override → re-separation → save/reopen → restore-default, with far-side Truth and display assertions at every transition and corresponding Undo/Redo checks. The defect caught is loss of the user's colour choice or drift between Truth and the three surfaces. These future checks have not run in this decision Task; no new gate is added here.

**2026-10-08 implementation addendum.** P1–P4 of the prerequisite plan provide `project.inspect` `category` / `colour_override` / `colour` per Pad and `pad.colour.set`; T7 consumes them.

- **Rendering.** `colour` (the Core-resolved index, or null) is the only input. The Pad matrix, the Sequence overview row name and notes, and the touch grid row and notes carry it as `data-pad-colour` (`0`–`4` or `neutral`). `styles.css` maps it to the palette once. The slot%5 rotation is removed. The selected Pad (Sample page) has a white border and a lime dot, and keeps `aria-pressed`.
- **Control placement.** PAD COLOUR sits under the Sample editor in the Sample touch area, for the selected Pad: five colour buttons plus "Restore category default". Sample is the page that owns Pad selection, and D03 already names the selected Pad and its category ("A03 / BASS"). No Desktop Final frame draws a colour control, so this adds one compact block to a page that already edits the selected Pad, rather than a new layer on Sequence, whose SETUP layer holds Pattern settings and has no selected Pad.
- **Commit.** The control queues on the Sequence authoring tail. It names the Project view's revision, then re-reads the view from Truth as a grid edit does. The stored override, or a restore with no override, makes no call. The control is disabled for an empty Pad, while recording, while the transport settles, and while another Project change or parameter edit is pending. Playing is allowed.
- **Declared files.** `src/components/pad_colour_controls.tsx`, `pad_surface.tsx`, `sequence_overview.tsx`, `sequence_grid.tsx`, `sequence_touch_workspace.tsx`, `src/state/pad_colour.ts`, `src/runtime/project_actions.ts`, `src/runtime/runtime_types.ts`, `src/state/creator_state.ts`, `src/state/view_model.ts`, `src/app.tsx`, `src/styles.css`, their tests, `creator_web_soundset.spec.mjs`, this plan, and portal `/hosts/creator-web/`.
- **Lowest-tier tests.** `test/pad_colour.test.tsx` asserts that the three surfaces resolve the same colour (override, category default, neutral), that a selected BASS Pad differs from an unselected one, the set/restore/no-op calls, and that the controls are disabled for an empty Pad and while recording. `project_actions.test.ts` asserts the inspection mapping. `workspace_shell.test.tsx` covers the app round trip and a refusal. The packaged journey is in `creator_web_soundset.spec.mjs`. It runs category default (Sound Set install) → override → re-install `replace` → reload/reopen → restore, and checks Truth, the three surfaces and Undo/Redo at each step.

## T8 — `BARS` change and `COPY` (blocked on #1823)

A separate plan follows once #1823 is decided. It adds Authoring Commands and Host operations, then enables the T5 controls.

**2026-10-08 addendum.** [#1823 is decided](../prd/decisions/2026-10-08-pattern-length-and-copy.md). The separate plan is [`2026-10-08-pattern-length-and-copy.md`](2026-10-08-pattern-length-and-copy.md): its P1 adds the Core commands and Host operations, and its P2 is this T8.

## T9 — D01 Project to Desktop Final

**Behaviour.**

- **Upper screen.** `PROJECT / <name>` with save state, a summary line, and PROJECT / CONTENT / WORKSPACE columns. It always shows the current Project, never the hovered card.
- **Touch area.**
  - `YOUR PROJECTS · NN LOCAL` above 56 px cards.
  - Tapping a card selects it; only `OPEN PROJECT` (blue accent) opens it.
  - `+ NEW PROJECT`.
- **Not rendered.** Save, Save As and the unsaved-changes dialog stay out until a product decision exists (see Blocked).
- **Coordination.** #1665 (System entry and Project tab restructure) is checked before this Task starts, and the plan is amended if it moved.

**Declared files.** `components/project_overview.tsx`, `components/project_touch_workspace.tsx`, `components/project_surface.tsx`, `src/styles.css` and their tests, the Project legs of `creator_web_browser.spec.mjs` and `creator_web_lifecycle.spec.mjs`, and portal `/hosts/creator-web/`.

**Lowest-tier tests.**

- A component test that selecting does not open and Open does.
- A journey leg: open a second Project and check its id in the upper screen and in Truth.

## T10 — D03 Sample to Desktop Final

**Behaviour.**

- **Upper screen.** Sample name, `PAD A03 · <category>`, the format and selection line, and the whole waveform with the selection marked.
- **Touch area.**
  - A 336×128 waveform whose start and end handles are drawn 20 px wide with 40 px hit areas.
  - START and END value cards using the existing numeric entry.
  - `AUDITION` (purple), `TRIM SELECTION`, `BROWSE`, and `ASSIGN → <pad>` styled on the existing actions.
- **Unchanged.** No new flow is invented, and the semantics of trim, undo and assign stay as they are.

**Declared files.** `components/sample_overview.tsx`, `components/sample_surface.tsx`, `components/waveform_editor.tsx`, `components/sample_controls.tsx`, `src/styles.css` and their tests, `creator_web_sample_editor.spec.mjs`, and portal `/hosts/creator-web/`.

**Lowest-tier tests.**

- A component test that the handle hit area is 40 px while the visible handle is 20 px.
- A journey leg: drag the end handle by its edge, trim, check the Truth range, then undo.

## T11 — D04 Perform to Desktop Final

**Behaviour.**

- **Upper screen.** `PERFORM / <project>`, BPM and play state, a now/next line, `BAR nn / nn · BEAT nn / nn`, a progress strip, and L/R meters if a meter projection exists. Without one, the meters stay out.
- **Sections.**
  - Section buttons are 78×56. Playing is solid with a `PLAYING` label; queued is outlined with a `QUEUED` label.
  - State is never shown by colour alone.
- **Faders.**
  - The existing live faders are 104×152, each with a 24 px curve slot.
  - The Filter curve follows D04a. It is illustrative, not measured DSP.
- **Target row.** A `TARGET / PAD A03` row, with FX / MORE.
- **Not rendered.** MASTER, filter type, and Mute/Solo appear only if a Host action exists. Today they do not.

**Declared files.** `components/perform_overview.tsx`, `components/perform_surface.tsx`, `components/pattern_launch_strip.tsx`, `components/fx_slider_bank.tsx`, `src/styles.css` and their tests, `creator_web_perform.spec.mjs`, and portal `/hosts/creator-web/`.

**Lowest-tier tests.**

- A component test of the playing and queued labels and ARIA state.
- A journey leg: queue a section, see QUEUED, then PLAYING after the bar.

## Order

```
T1 ─┬─ T3 ─┬─ T4 ─ T5a ─ T5 ─ T6
    │      ├─ T9
    │      ├─ T10   (T9–T11 reuse the T5 kit; they can follow T5 in any order)
    │      └─ T11
    ├─ T1b (font bundling + CSP; independent)
    └─ T2 (only after owner confirmation; independent)
T7 ← Pad colour Contract/Core + Host projection      T8 ← #1823
```

T3 goes before the visual Tasks so that their selector churn lands once.

## Verification

- Each Task runs its lowest-tier tests, then `scripts/creator-web.sh test` and `scripts/creator-web.sh proof`.
- `scripts/docs-site.sh check` runs, because every Task updates `/hosts/creator-web/`.
- Each batch-only lane the change selects runs on the committed head. Its `pass key=` goes into the Pull Request under `## Batch-only Lanes`.
- Revert proofs run against rebuilt artefacts.
- No timeout, coverage floor, owned lane or journey leg is relaxed. A selector rename is not a dropped leg.
- At each visual Task's review, a screenshot of the console (`LMDJ_HARDWARE_CONSOLE_SHOT`) is compared by eye with the Figma frame and attached to the Pull Request. This is advisory: there is no pixel gate.

Not inferred from automation: the feel of the encoders on a real wheel or trackpad, touch ergonomics on iPad, real Safari font rendering, and visual fidelity to Figma. These remain owner acceptance rows in `docs/quality/2026-09-11-creator-ui-migration-acceptance.md`.

## Version Management

Version impact: none in this plan Pull Request (documentation only).

The implementation Tasks owe bumps at the next coordinated version settlement. No numbers are pre-filled.

- **`creator-web` MINOR** for T4, T5, T6, T9, T10 and T11, all user-visible capability or layout. T1, T1b, T2 and T3 owe at least a PATCH and fold into the same settlement. T1b's CSP change is part of the Creator deploy surface, not a Product Build change.
- **T8** (later plan) also owes MINOR bumps for `authoring-domain`, `application-facade` and `web-runtime-platform`.
- **T7's prerequisite** persists Pad colour in Truth and owes a Contract compatibility review and SemVer change; affected Core/Host version impacts are declared in its separate plan. T7 owes a Creator MINOR for the user-visible colour controls and unified rendering.
- No Product Build or Assembly change happens in these Tasks.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/

Reason: the 2026-10-07 decision addendum records approved Pad colour behaviour in the portal as designed, with Contract/Core and T7 implementation still outstanding.

Each implementation Task is `required`:

- every Task updates `/hosts/creator-web/`;
- T5 also updates `/product/workflows/`;
- T6 also updates `/platform/input/`.


## Pitfall Impact

Pitfall impact: none expected. Each Task searches open `area:creator` and `area:web-host` entries before starting and again before shipping.
