# Creator hardware UI migration — U0 source-backed design draft

Date: 2026-09-11. Status: design DRAFT with narrow shown-preview approval (“我觉得没有问题👍”), recorded in the [preview approval](https://github.com/endaye/lmdj/issues/1214#issuecomment-5634900788), and the subsequent binding global transport decision in §7: independent global Pattern Play/Stop and Pad-action Record toggles. Combined-state details remain open; unrelated D02–D08 and keyboard/focus behavior are not thereby approved. U0 remains incomplete. Full migration-plan execution is authorized subject to its applicable U0 gates.

Source HEAD: `b9cb540fe7e1001e22569c0cbf48c7bb60426f02`.
Tracking: [U0 #1214](https://github.com/endaye/lmdj/issues/1214), [migration #1207](https://github.com/endaye/lmdj/issues/1207), [visual language #522](https://github.com/endaye/lmdj/issues/522).

This spec covers real-code inventory, proposed locations, state/control contracts and the existing Figma draft evidence in §10. Every proposed mapping remains a proposal until approved. Existing behavior is identified separately, including limitations that must not be silently repaired during migration. Prototype existence is not evidence that all flows work.

## 1. Authority and fixed geometry

Read alongside [hardware reference](../../design/2026-09-11-lmdj-hardware-ui-layout-reference.md), [parallel roadmap W1/W2](../../plans/2026-09-11-parallel-product-roadmap.md), and repository `AGENTS.md`. Subsequent implementation depends on the applicable U0 gates, including approved layout/focus/state rules and W2 interactive evidence.

| Region | Design rectangle (x, y, width, height) | Responsibility |
| --- | --- | --- |
| Whole instrument | 0, 0, 880, 592 | Design units, not pixels of a physical device or millimetres |
| Physical controls (L) | 16, 16, 80, 560 | Four navigation keys, Banks A–D, value/direction and transport controls; four encoders in 2×2 placeholders |
| Overview display (O) | 112, 16, 752, 176 | Read-only context, authoritative state, pending state and feedback; no hit targets, dragging, scrolling or parameter editing |
| Pad region (P) | 112, 208, 368, 368 | Fixed 4×4 arrangement; 80×80 Pads, gaps 16; address remains Bank + slot |
| Touch screen (T) | 496, 208, 368, 368 | Context-specific forms, menus, confirmations and recovery; usable inner region 336×336 |

Margins and inter-region spacing are 16. Small physical buttons are 32×32 with gaps 16. The eight button rows occupy 368 units. Do not squeeze six modes into the four reference navigation keys or assume a printed Logo is a physical switch. Software System and More modes entries must be explicit controls in T. Proposed System access is persistent in T's header even without an open Project; hardware access mechanism remains a decision.

Pad icons require an existing, reliable role value. `PadView` identity/assignment does not establish a musical category; Sound Set metadata may name a role but does not prove that role survives into every Project Pad projection. Use neutral assignment/empty graphics until a verified field is available. Position the visual subject at the Pad centre, not merely its SVG bounds. State text and markers remain separate from identity graphics.

## 2. Source index and audit conventions

All paths in the tables are repository-relative and refer to the source HEAD above. `C/` means `apps/creator-web/src/components/`; `R/` means `apps/creator-web/src/runtime/`; `S/` means `apps/creator-web/src/state/`. These are path abbreviations, not new modules. Source symbols give a re-resolvable anchor if line numbers move.

| Anchor | Source and authority |
| --- | --- |
| A | `apps/creator-web/src/app.tsx`: `Workspace`, mode guards, project action lane, input ownership, capture handoff, preparation retries, Sequence handlers |
| M | `C/mode_rail.tsx`: `CreatorMode` is project/sample/sequence/perform/soundset/slice; `C/bank_selector.tsx`, `C/pad_surface.tsx`; `R/input_controller.ts`: `createCreatorInputController`, `trigger` |
| G | `C/status_bar.tsx`: `StatusBar`; `C/error_panel.tsx`: `ErrorPanel`; `R/runtime_context.tsx`; `src/report/acceptance_report.ts` under Creator |
| J | `C/project_surface.tsx`: `ProjectSurface`; `R/project_actions.ts`; `S/creator_state.ts` selectors |
| S | `C/sample_surface.tsx`: `SampleSurface`; `C/sample_controls.tsx`; `C/waveform_editor.tsx`; `R/sample_actions.ts`; `S/sample_state.ts` |
| C | `C/capture_panel.tsx`, `C/long_source_editor.tsx`, `C/modal_dialog.tsx`; `S/capture_state.ts`; `src/capture/capture_controller.ts` and `src/ingest/long_source_ingest.ts` under Creator |
| Q | `C/sequence_surface.tsx`, `C/sequence_transport.tsx`; `R/sequence_actions.ts`; `S/sequence_state.ts`; A's `recordSequence`, `stopSequence`, `selectSequencePattern`, `createPattern`, `updateSequenceSettings` |
| F | `C/perform_surface.tsx`, `C/pattern_launch_strip.tsx`, `C/fx_slider_bank.tsx`; `S/perform_state.ts`: `createPerformController` |
| X | `C/candidate_surface.tsx`: `CandidateSurface`, `CandidateJob`, `isCandidateSession`; `S/candidate_state.ts` |
| B | `C/soundset_surface.tsx`: `SoundSetSurface`; `S/soundset_state.ts` |

Available means a current UI handler calls a current session/controller operation, not that every browser/device supports it. Runtime capability checks, current authority and refusals remain decisive. A state/reducer symbol alone does not imply a reachable control.

Each inventory row supplies the original action, source/handler, proposed destination, draft/return behavior and refusal/recovery route. A grouped row enumerates its distinct controls explicitly. “Fallback” means the existing layout is still reachable through a proposed T “Existing workspace” entry during that workflow's migration; that entry is not implemented today. Only one layout may own the session/input/capture resources at a time.

## 3. Global and mode reachability matrix

| ID / original entry and action | Current source/handler and guard | Proposed location | Draft, return, refusal and recovery |
| --- | --- | --- | --- |
| G01 Mode Rail: Project | M/A `setActiveMode`; Project always in rail | L Project; T project chooser/summary | Return via navigation. Preserve project identity. Opening chooser is not opening another Project. |
| G02 Mode Rail: Sample | Current M/A stops active Sequence recording/switch before Sample entry; flushing prevents transition | L Sample | This source mode-leave stop is a migration gap, not the approved target: page navigation must not automatically stop the global session. Capture trim overlay remains a separate owned flow. |
| G03 Mode Rail: Sequence | M/A `isSequenceSession`, ready Project | L Sequence | Missing capability/Project: disabled with reason and Project route; active Pattern selection comes from Sequence state. |
| G04 Mode Rail: Perform | M/A controller + configured capture + ready Project; performance recording uses stricter `canRecord()` | L Perform | Current Perform leave awaits `controller.leave()`; this must not be repurposed to stop global Pattern transport on navigation. Preserve separate performance/capture cleanup; visible Perform does not mean performance-record-ready. |
| G05 Mode Rail: Slice | M/A candidate capability + ready Project + Sequence stopped | T More modes → Slice, initially fallback | Disabled explanation names stop/open prerequisite; leaving stops candidate audition on unmount, not implicit adoption or cancellation of an analysis job. |
| G06 Mode Rail: Sound Sets | M/A `isSoundSetSession` | T More modes → Sound Sets, initially fallback | Can browse without Project; installation requires Project. Return to originating mode; preserve current Bank semantics. |
| G07 Bank A/B/C/D | M/A `clearPressed`, `bank-selected`; Perform also `setBank` | L A–D; T labelled equivalent where needed | Stable 16 positions over 64 slots. Release pressed inputs before switching. Bank selection must not imply an edit or trigger. Sound Set target selection invalidates old preview. |
| G08 Pad press/release/cancel, keyboard and MIDI | M/R input controller → session `trigger`; sample options can select/inspect or request a file; armed capture Pad requests capture stop | P, with existing input controller | Retain velocity/source, release and cancellation. Distinguish accepted/rejected/empty/disabled from selected. Do not solve #725 enqueue semantics. Details in §7. |
| G09 Activate audio | G/A `activateAudio` → `activateCreatorAudio`; state selector, callback and host `audio-suspended` required | Persistent T System → Activate audio; prominent T prompt when needed; O status only | Genuine user activation event required. Loading/failed host is not resumable audio. Refusal remains visible; retry only through applicable runtime/audio action. |
| G10 Suspend audio | G/A `suspendAudio`; only running | T System → Suspend audio | Clear/release owned input and obey capture/Sequence/Perform shutdown barriers. Remain in context with suspended text. Re-enter via Activate audio, never background auto-resume. |
| G11 Enable MIDI | G/A `inputController.enableMidi`; runtime ready, not already granted/requesting | T System → MIDI | Show off/requesting/denied/input count as text. No invented device selector or note remapping. Permission refusal → browser/device guidance and existing explicit retry eligibility. |
| G12 Export report; inspect Build, Project, revision, BPM, key and MIDI facts | G/A `exportReport`, acceptance report serialization, build identity | T System → Diagnostics → Export report; O compact status, T details | Current export disabled unless runtime ready/callback exists. Do not promise offline diagnostic export. Download JSON is diagnostic output, not a Project save. Return restores System opener. |
| G13 Open local Project after duplicate import | G/A `DUPLICATE_ID`, `onOpenLocalProject` triggers chooser/list attempt | T error sheet → Open local, with explicit Project chooser destination | Do not overwrite newer local copy. Existing callback sets chooser state; new shell must make chooser visibly reachable from any origin. |
| G14 Retry project | G/A only `PROJECT_BUSY` with remembered list/open operation | T error sheet → Retry project | Retry that operation after lock clears; no generic retry for every IO failure. Dismiss does not resolve the lock. |
| G15 Retry runtime; Dismiss error | G/A timeout/restart error + callback; Dismiss only when runtime ready | T error sheet; System remains available | Existing shutdown barrier owns restart. Retain code/details and context; restart is not a successful replay of the failed mutation. |
| G16 Retry Prepare | S/A `retryPrepare`, guarded against pending sample action/retry | T Sample audio-status sheet, reachable from System status | Explicitly distinguish saved Project revision from older/unavailable runtime. Retry cook/prepare, never resubmit saved Sample mutation. |
| G17 Retry audio preparation after candidate adoption | A `refreshCandidateProject`; disabled while preparing, project lane busy or runtime not ready | Persistent T audio-status sheet | Reconcile Project then prepare. Show saved revision separately from ready audio; do not repeat adoption. |
| G18 Close/Escape/Tab/backdrop modal behavior | C `ModalDialog` / `ConfirmationDialog` | T modal or accessible fallback dialog | Inert background, trapped focus and opener restore remain required. Escape cancelling an edit is not undoing a committed operation. Hardware-specific dialog navigation remains proposed. |

Proposed global Back always means “leave this local panel after resolving its owned draft”; it is not a new Facade undo/stop command. No generic Save, Undo, Redo, Settings persistence, user login or Project export is inferred from the status bar or Figma.

## 4. Project and Sample action inventory

| ID / original action | Current source/handler | Proposed location | Draft, return, refusal and recovery |
| --- | --- | --- | --- |
| J01 Open local; Back to Project | J `onShowLocal`/`onHideLocal`, A's list journey | T Project list ↔ summary, fallback first | Chooser state only; no current-project replacement until Open. No projects → Import prompt. Back returns to current Project if one exists. |
| J02 Open a listed Project | J `onOpen` → A `openProject`/`openProjectJourney`, `canOpenProject` | T explicit Open on selected card | Proposed card selection is UI draft; selection alone must not open. Pending lane/sample mutation disables. `PROJECT_BUSY` retry; preserve refusal details and previous context where authority permits. |
| J03 Import .lmdj; native picker cancel | J file input → A `importProject`/`importProjectJourney`, `canImportProject` | T Project Import, progress in T/O | Picker cancel does nothing; importing shows completed/total bytes. No in-flight Cancel control exists. Invalid bundle/IO/quota/duplicate refused; duplicate routes to local copy. No cross-origin storage migration (#961). |
| J04 Project summary/read details | J project summary, G status facts | O context plus T details | Authoritative counts/IDs/revision only; no invented file name, unsaved indicator or New/Save/Save As actions. |
| S01 Select assigned Pad; Add Sample to empty Pad | S selection dispatch, R input `trigger`, `chooseFile`, `inspectSampleJourney` | P keeps trigger semantics; explicit T Pad selector proposed, fallback first | Current Sample interaction can select AND sound; empty Pad may request picker. Inspect/loading and unavailable Project are distinct. New silent select requires decision D02. |
| S02 Replace Sample; drag/drop file; Confirm/Cancel replace | S `setPendingFile`, `startLongImport`; C confirmation | T Sample Browse/Replace; fallback drag/drop retained | Occupied Pad requires confirmation. Cancel leaves assignment intact and restores opener. Replacement resets trim, trigger, Loop, Volume, Mute; no new copy semantics. Pending action/session/Project guards remain. |
| S03 Long source start and length; Preview/Stop preview; Commit; Cancel | C `LongSourceEditor`: `selectStart`, `selectFrames`, `togglePreview`, `commit`; S `commitLongSource`, `releaseLongSource` | T source-selection stage; O whole-source overview; fallback until migrated | Integer-frame selection bounded by source and `effectiveRemainingFrames`; pending commit disables cancel/actions. Decode/preview/commit error shown with retry/edit opportunity. Cancel disposes draft source and audition; no Project change before commit. |
| S04 Playback trim Start/End by handles or numeric seconds | S `WaveformEditor`: `preview`, `commitGesture`, `cancelGesture`, `keyboardEdit`; `performUpdate` → `updateSampleJourney` | T local waveform/numbers; optional K1/K2; O overview only | Existing gesture previews then commits; Escape/pointercancel cancels. One-frame minimum, source bounds; arrows one frame, Shift about 10ms. Missing/invalid metadata/waveform disables relevant editing, not fake waveform. Revision conflict requires fresh inspect; saved-but-cook-failed uses G16. |
| S05 Zoom in/out, Fit waveform, Pan left/right | S `applyViewport`, `zoomSampleViewport`, `fitSampleViewport`, `panSampleViewport`, `queryWaveformJourney` | T viewport controls; O reflects selection/context | Viewport is UI state, not trim/Project Truth. Query failure must not substitute stale envelope for another identity. Returning to edit preserves valid context; actual per-mode draft retention needs D03. |
| S06 Loop; One Shot/Hold | S `SampleControls.modeFor`, `onCommit` | T Sample playback toggles | Existing modes exactly `one_shot`, `gate`, `loop_gate`, `loop_toggle`. Preserve boolean mapping and actual handler, not a new duration/latch model. Disabled for no assigned inspected Pad/pending action. Update failure uses sample error path. |
| S07 Mute; Volume | S `onCommit(muted)`, `previewGain`/`commitGain`/`cancelGain` | T Sample Mute/Volume, proposed K3 Volume | Sample Mute EXISTS; Perform Solo does not follow from it. Volume −60 to +6dB, step 0.1, underlying millidB. Pointer/key gesture commit; cancel restores preview. Suspended audio can show “Activate Audio to preview”; do not label edit refusal as audio playback. |
| S08 Reset Pad to Defaults; Confirm/Cancel | S confirmation → `reset`/`resetSampleJourney` | T Sample More → Reset | Keep Sample; restore full range, One Shot, 0dB and Mute off. Cancel leaves it intact. Commit receipt then prepare; no global Undo is available in this surface. |
| C01 Record Sample; replace confirmation; Record into Pad | S `openCapture`, C `handleRecord`, capture controller | T capture stage; O input level/time; fallback first | Choose target and obtain quota; occupied confirmation occurs before microphone request. Idle/permission-error offers Record; requesting is busy. Device/permission failures retain honest error and explicit record retry. |
| C02 Stop capture; Continue in Sequence; press armed Pad | C `handleStop`/`onContinueInSequence`; A `stopArmedCapture`, R armed-slot branch | T Stop/Continue; armed P stop; O capture badge | Continue keeps ONE capture pipeline alive through hidden Sample host. Armed Pad stops capture instead of firing ordinary sample; other Pads remain Sequence input without retargeting capture. Do not duplicate subscriptions. |
| C03 Capture Start/End trim, drag/keyboard; Crop to selection | C `handleSelectStart/End`, grip handlers, `handleTrimKeyDown`, `handleCrop` | T capture trim; O read-only selection | Trim/commit-error retains buffered take. Arrow/Shift and Escape gesture restoration remain; crop changes precommit buffer, is disabled for full-range selection, and is not a Project trim/Undo command. |
| C04 Commit captured take; retry Commit; Discard; Close | C `handleCommit`, `handleDiscard`, `handleClose`; S `captureCommitJourney` through import lane | T capture resolution with distinct actions | Silent take refusal and quota/commit errors must be shown. Commit error retains editable take where current pipeline allows. Close explicitly stops controller then closes; it is NOT currently a keep-draft action. Discard releases take. Sequence-linked resolution disarms capture and refreshes authority before trim overlay closes. Confirm-close policy is D03, not current behavior. |

Sample file chooser accepts WAV/MP3/M4A/AAC/FLAC for the long-source decode route. Existing lower-layer “Accepted format: PCM16 WAV…” copy is not proof all compressed input is unsupported: distinguish browser source decoding from canonical audio accepted by the import/runtime boundary. Keep format/quota failures at the correct stage.

## 5. Sequence action inventory and first slice

| ID / original action | Current source/handler | Proposed location | Draft, return, refusal and recovery |
| --- | --- | --- | --- |
| Q01 Select Pattern while stopped | Q/A `selectSequencePattern` → reducer `selected` | T Pattern list; O selected identity and bars | Only stopped reducer accepts ordinary selection. Selection is UI state; not Pattern launch or new Project mutation. Back to Sequence overview leaves selected identity. |
| Q02 Switch Pattern while recording | Q/A `requestPatternSwitch`, reducer `switch-pending`; subscribed boundary | T Pattern list with current/pending labels; O pending frame | Do not show target active on click. Wait for matching authority/boundary. While switch-pending current selection handler does not queue another request; proposed disable with explanation avoids a silent no-op. Flushing already disables selection. |
| Q03 Quantize toggle | Q/A `updateSequenceSettings({quantizeEnabled})` | T Quantize On/Off | Immediate existing settings action, serialized authoring tail; refresh authority afterwards. No Grid subdivision control is established by this boolean. Flushing disables. Errors retain committed value. |
| Q04 Swing draft; Apply Swing | Q local `swing`, A settings action | T Swing slider + Apply; proposed K2 | 50–75%, integer step 1. Display committed and draft separately. Current form uses explicit Apply; incoming committed value updates local copy. Back draft policy requires D03; no invented unquantized swing range. |
| Q05 BPM draft; Apply BPM | Q local `bpm`, A settings action | T BPM control + Apply; proposed K1 | Integer 40–240. Invalid/out-of-range disables Apply, not silently clamped saved data. Serial revision update and authority refresh. Explicit Apply retained for initial slice. |
| Q06 Bars selection; Create Pattern | Q local `bars`, A `createPattern` → session | T New Pattern → 1/2/4/8 bars → Create | Bars is NEW Pattern length, not resizing current Pattern. Create only stopped; generates ID and uses expected revision. Failure keeps selection/typed draft; success adds and selects receipt Pattern. No Copy/delete/rename inferred. |
| Q07 Record | Current Q/A `recordSequence` → `beginSequenceJourney` opens event journal; requires running audio/session/Project and awaits settings tail | Approved global Record toggle, same responsibility on every page; second click ends Pattern-event recording | Records Pad actions into current Pattern for sequencing/overdub, never microphone/master WAV. Current UI disables repeated Record; replace that source behavior with the approved toggle through the §7 dependency. Combined-state rules remain open. |
| Q08 Stop (current journal operation) | Current Q/A `stopSequence` → `stopSequenceJourney` flushes/closes journal, not general playback Stop | Reuse for global Record-off where resolved semantics permit. Approved separate global Play/Stop controls Pattern playback, not this journal operation | Current journal recording/switch → flushing → stopped receipt; update/show committed revision only when a Project exists and receipt `committedRevision` is non-null; otherwise retain revision and inspect authority. Preserve failure/recovery handling. Playback Stop needs separate authority; its effect during recording remains a bounded decision. |
| Q09 Refresh authority | Q transport → A `refreshSequence`/`refreshSequenceJourney` | T Sequence More/Recovery → Refresh authority; available on error | Queries status AND recovery; updates journal revision reconciliation. Not “retry last write”. Does not establish runtime audio freshness on its own. |
| Q10 Recover original Pattern; destination selector; Recover selected Pattern | Q/A `applySequenceRecovery` with null for original or an explicit alternate existing Pattern ID; selector excludes original | T recovery sheet, O recovery count | Require selection of an alternate existing Pattern for alternate recovery. No new-Pattern recovery action exists. Apply receipt updates revision then refreshes; on refusal keep candidate/reason and route to refresh. Choosing destination is an uncommitted UI draft. |
| Q11 Discard recovery | Q/A `discardSequenceRecovery` | T recovery sheet distinct Discard | Existing destructive action is immediate; propose confirmation as D03. Refresh after success; failure does not remove candidate optimistically. Back leaves durable recovery untouched. |

### First implementable candidate slice (subject to approval and prototype evidence)

Recommended approach: shared four-region shell with only the existing Sequence workflow migrated first. Project/Sample/Slice/Sound Sets/Perform stay explicitly reachable via the existing workspace fallback until their own slices pass. Alternative: migrate all six surfaces at once (large state/focus/resource risk); alternative: build static hardware facade first (useful visual exploration but does not prove a workflow). The recommended slice keeps the real Sequence state and session operations while constraining layout work.

Entry requires a real existing/imported Project with an assigned Pad. Empty Project entry routes to Project Import or Sample in fallback; do not invent New Project. Sequence remains inspectable with suspended audio, and its T Activate audio prompt resolves the prerequisite.

The journey below describes existing journal operations and their acceptance evidence, not the new global Play/Stop coupling. The approved global controls require the §7 capability dependency and bounded combined-state decisions; audio activation is not the target Play action.

1. Open Project through the existing journey. Observe actual identity/revision and assigned Pad; return from chooser without opening must leave Project unchanged.
2. Enter Sequence. Observe selected Pattern/Bars, active Bank, audio readiness. Choose another existing Pattern or create a 1/2/4/8-bar Pattern; observe created receipt/selection. Cancel New Pattern before Create must not alter Project.
3. Set BPM 40–240 and Swing 50–75 with existing explicit Apply; toggle Quantize. Observe committed values/revision separately from drafts. Reject invalid BPM. No “Grid 1/16” is implied.
4. Activate audio via T, then Record Sequence. Observe recording authority, not a speculative click animation. Trigger/release actual Pads through existing pointer/keyboard/MIDI ownership; selected edit object must not become an event Asset reference.
5. Request another Pattern during recording. Observe current + pending + effective boundary; only matching authority makes new Pattern active. This is not Perform launch acknowledgment.
6. End Pattern-event recording (current `stopSequence` journal operation, not global playback Stop). Observe flushing then stopped; update/show committed revision only when a Project exists and the receipt's `committedRevision` is non-null; otherwise retain the current revision and inspect authority. Refresh authority and reopen/inspect the Project to verify persisted Pattern outcome in eventual implementation acceptance. A journal-stop failure retains recovery/refresh routes.
7. Exercise recovery to original (null destination) or selected alternate existing Pattern and Discard separately; assert the far-side candidate/Project state. Do not substitute New Pattern creation for a recovery destination. Navigate back with focus restored and no held input. Capture continuation/trim uses fallback and is not claimed exercised by this slice.

The desired final Sequence overview includes a read-only event grid alongside Project/Pattern identity, bars, BPM, Quantize, Swing, Bank, phase, pending identity/frame and errors. The reference's 8-track/64-step example does not establish projection availability or fixed product limits. Verify an authoritative Facade event projection before connecting the grid. If missing, record a dependent capability Task with exact source/API scope and verification for Pattern events referencing Pad Slots, then connect the grid after that dependency is satisfied. This dependency is not created or implemented by this spec. A provisional metadata-only display may be used in an explicitly bounded slice, but it does not replace or complete the desired event-grid outcome. Do not fabricate events, playhead data, note-editing capability or waveform values from nonexistent fields.

## 6. Perform, Slice and Sound Sets inventory

| ID / original action | Current source/handler | Proposed location | Draft, return, refusal and recovery |
| --- | --- | --- | --- |
| F01 Pattern assignment + destination + Assign; Clear selector + Clear; Move from/to + Move | F `PatternLaunchStrip` → controller `assignPattern/clearPattern/movePattern` | T Perform Pattern slots, fallback first | Form selections are local drafts. Mutation enabled only recording phase idle; Move rejects same slot. Revision/refusal shown via controller; no Pattern content Copy. Back must not implicitly apply forms. |
| F02 Launch Pattern slot (including empty) | F `launchPattern` | T Pattern launch blocks, not automatic Pad repurposing | Enabled recording/flushing. Pending and acknowledged reflect actual receipts. Empty acknowledged slot is silent gap. Do not relabel acknowledgment as next-bar behavior without runtime evidence. |
| F03 Eight FX sliders: Filter, Delay, Reverb, Stutter, Gate, Reverse, Crush, Cutter | F `PERFORMANCE_FX_ORDER`, `engageFx/moveFx/releaseFx` | T FX pages; proposed K1–4 mirror page of four | Each 0–1000 step 1. Only recording/flushing; preserve gesture ID and release on cancel/blur/disable/unmount. Page change must release old gestures before reassignment. No LP/HP/BP selector, Hz curve or Master slider inferred. |
| F04 HOLD | F `toggleHold` | T explicit HOLD with text/pressed state | Only recording/flushing. Preserve controller semantics; not Sample Loop. Leave/stop neutral state must follow authoritative cleanup. |
| F05 Record Performance; Flush Performance; Stop Performance | F controller `record/flush/stop`, `canRecord` | Separately named T performance-recording actions; never the global Record key | Performance Record requires audio running, OPFS, matching capability/capture readiness and idle controller. Starting/recording/flushing/stopping distinct. Flush is not final Stop; failures surface with take state intact as controller permits. |
| F06 Performance name; Save; Discard | F recording panel → `save(name.trim())`/`discard()` | T take resolution | Name draft; Save requires stopped and nonblank; Discard stopped. Saving/discarding status shown. Do not treat name as Project rename or Save as global Project save. Back/leave policy D03 must preserve current recovery safeguards. |
| F07 Export Performance WAV; Retry WAV bind | F `exportWav` when WAV exists; `retryWavBind` when binding retry | T take details, persistent failed-binding route | Recording/WAV/binding status are separate. A saved event journal does not prove WAV binding. Retry bind does not rerecord; export failure retains output/reference where supported. |
| F08 Replay saved Performance; Stop Replay | F `beginReplay`, `stopReplay`, `refreshReplay` | Separately named T saved-performance replay actions; never the global Play/Stop key | Observe replay playing/neutral/resolved revision. Replay Stop waits for neutral confirmation, with bounded status queries and timeout. Leaving must not silently claim stop success. |
| F09 Resample start/end frames, target Pad; Resample selection | F `resample` → `commitPerformanceResample` | T replay range/target page | Integer start/end and end>start, target 0–63, selected Performance required; current UI start input min=0 but submit predicate does not explicitly test start>=0 (retain server refusal, do not claim stronger current guard). Success reports target Bank/Pad. No inferred preview/overwrite confirmation; D03 flags destructive target policy. |
| F10 Apply recovery; Discard recovery | F `applyRecovery`/`discardRecovery` | T recovery page | Display reason and separate recovery status. Retain errors and candidate until authoritative resolution; proposed confirmation is not existing behavior. |
| X01 Provider selector; Grant analysis permission | X `selectProvider('sample.slice.v1', ...)`, `listProviders`, `configureProviderPermissions` | T Slice setup/System shortcut, fallback first | Workspace/Host settings, never Project Truth. Serialize while busy; merge permission `sample.slice.execute` with known current grants. Unknown grants refuse mutation. Back does not undo already granted permission. |
| X02 Source selector; public-audio checkbox | X source state and `publicSource` | T Slice source/setup | Sources from Project inspection. Empty → Sample import/record route. Checkbox is explicit classification for current public/local/test policy, not consent to arbitrary remote upload. Source change remounts job draft; no guaranteed cross-source draft persistence. |
| X03 Analyze/Retry analysis; Cancel analysis | X `runCandidateJob`, `cancelCandidateJob` | T Slice progress/actions | Requires Provider, permission, explicit public classification and no uncertain adoption. Jobs have attempt IDs; pending/interrupted cancellation available. Failure/cancel preserves earlier active slices; interrupted requires explicit retry. |
| X04 Refresh slices and Project | X `refresh`/`inspectCandidateJob`, parent refresh | T Slice persistent refresh/error route | Disabled while busy/adoption pending. Reconcile Project before another adoption, including after source change. NOT_FOUND clears missing job/results; other refusal retains error. |
| X05 Preview each detected slice; Stop preview | X `auditionCandidate`, `stopCandidateAudition` | T result list; O selected slice readout | Busy blocks Preview; played=false says Activate audio. Stop stays explicit; pagehide/unmount stops audition. Candidate preview is not Pad assignment. |
| X06 Discard slices | X `discardCandidateSet`, stop audition first | T result More → Discard | No active set/empty recipes shown honestly. Removes candidate set through session, not source or recorded Pattern. Proposal confirmation D03; no automatic destructive Back. |
| X07 Add target; select slice/Bank/Pad; Remove target | X local rows, `candidatePlan` validation | T target editor, paged rows | Local plan only; validation copy controls adoption eligibility. A–D/16 slots unchanged. Remove row does not clear a Project Pad. New active set resets rows. |
| X08 Adopt selected slices | X `adoptCandidates`, `onUncertain`, refresh committed revision | T explicit adoption confirmation summary | Writes selected Pads, replaces sounds, preserves source/Pattern. Every failed/unknown response requires Project refresh before another adoption; no blind retry. #536 adoption strategy is out of scope. Audio preparation can fail AFTER successful adoption: G17 remains visible. |
| B01 Refresh Catalog; Inspect set; Close inspect; Dismiss error | B `refresh/listSoundSets`, `inspect/inspectSoundSet`, reducer closed/error-dismissed | T Sound Sets list/detail, fallback first | List/inspect/preview/install busy states distinct. Offline cached list and refused sets retained as text. Close is not rollback; dismiss is not retry. |
| B02 Audition set demo; Audition occupied slot; Stop audition | B `auditionSoundSet`, `stopSoundSetAudition` | T inspect demo/slot buttons and Stop | These handlers EXIST at source HEAD despite obsolete “This surface plays nothing” comment. Empty slot has no audition control. No local now-playing state; do not claim engine completion based on request. Refusals show set error. |
| B03 Select target Bank; Preview mapping | B bank-selected; `previewSoundSetMap` | T install target + preview; O mapping summary | Requires Project for preview. Changing Bank invalidates prior mapping. Mapping is draft, not installed state; empty Set slot is “Pad unchanged”, never Clear. |
| B04 Keep/Replace occupied Pads | B policy-selected, `selectCanInstall`/`selectWriteCount` | T collision review | No default policy when collision exists; explicit choice required. No collision sends no policy. Back preserves no false installed state; reopen/repreview if target/revision changes. |
| B05 Install into Bank | B `installSoundSet` with preview revision/command ID; A projection refresh | T explicit Install N of 16 confirmation | Revision-bound preview; license/content/audio/occupied/IO refusals visible. Success receipt distinguishes committed revision from refreshed audible projection. Retry after conflict requires fresh preview; unknown outcome must be inspected before a new install proposal. |

## 7. Control context proposal and unresolved semantics

### Approved global transport and capability dependency

Play/Stop is one global toggle: click begins Pattern playback, click while playing stops it. Record is a separate global toggle: click begins recording Pad actions into the current Pattern for sequencing/overdub, next click ends that recording. The controls are independent, not mutually exclusive, and page navigation neither redefines them nor automatically stops the global session. This supersedes disabled Play, touch-only Stop and mode-dependent Record proposals. Sample microphone capture, Perform/master recording, auditions and saved replay retain separately named actions.

Still unspecified: Record pressed while Pattern transport is stopped; Play/Stop pressed during recording; restart versus resume and count-in. Do not silently choose these transitions or infer that Record starts playback or playback Stop closes the journal. This bounded gap does not retract the approved controls or block unrelated work.

Source audit at `2b34e83c541a6af426e6eb63b1c04d3821a010a8`: JS `beginSequence/stopSequence` in `packages/web-runtime-platform/web/runtime_session.mjs` send `sequence.record.begin/stop` through protocol/bridge to `control_runtime.cpp`. Begin uses an already-running Pattern origin and calls Facade `begin_sequence`; stop calls `flush_sequence(..., true)`, closes the journal and may republish the Pattern. These journal operations are reusable Record lifecycle building blocks; they are not playback start/stop. `sequence.capture.disarm` only clears the armed Sample target, not the event journal.

Core Pattern playback already exists: `RealtimeEngine::schedule_pattern_events` in `packages/audio-runtime/src/realtime_engine.cpp` loops the published Pattern during render without requiring a journal. Public `publish_pattern_view`, cancellation and clock/identity queries are available; `clear_pattern_view` requires the engine stopped, and engine `start/stop` affect all audio/voices. The inspected public Web/Facade operation surfaces lack independent Pattern playing-state/start-stop authority. Required bounded dependency: separate Pattern scheduling/playing state from engine/audio running, expose authoritative controls/status through supported runtime/bridge/Facade boundaries, and reconcile journal anchors, pending publication and Pattern voice cleanup. Reuse existing journal/overlay/flush/recovery; do not implement Play as audio suspend or Record as capture disarm. Exact combined-state rules, API names and contract/version implications belong to that dependency's design; no product implementation is claimed here.

Current input fact: in `R/input_controller.ts`, Sample-enabled `trigger` selects the Pad when no capture owns it, may inspect/play an assigned Pad, and may request file selection for an empty Pad. An armed capture Pad instead requests stop; other input must not retarget the armed capture. Generic PadSurface does not establish a universal independent editing selection. DOM click, pointer-down and keyboard synthetic click are not interchangeable.

Proposed separation: P always keeps existing performance input ownership; an explicit T object selector supplies silent editing focus. Do not implement this until D02 confirms the exact behavior across all modes and inputs. Never consume an ordinary performance hit solely to move focus. Do not add long-press/double-tap/encoder-push requirements without device and accessibility decisions.

| Context | K1 | K2 | K3 | K4 | Direction / −+ proposal; approved global transport applies in every row |
| --- | --- | --- | --- | --- | --- |
| Project browse | Unassigned | Unassigned | Unassigned | Unassigned | Directions move list focus, T Open explicit. −+ only adjusts a focused numeric control. Global Pattern controls do not change responsibility on this page; missing Project remains a prerequisite. |
| Sequence settings | BPM draft, 1 BPM | Swing draft, 1% | New Pattern bars 1/2/4/8 only in creation stage | Unassigned | Directions move T focus; −+ adjusts focused value. Independent global Record and Play/Stop retain §7 semantics. |
| Sample edit | Start frame | End frame | Volume 0.1dB | Viewport zoom, UI only | Directions navigate unless waveform/range owns arrows. T Record Sample and audition are separate from global Pattern controls. |
| Capture trim overlay | Selection start | Selection end | Unassigned | Unassigned | Capture modal owns focus, not a redefinition of global Record. T capture Commit/Discard/Close remain explicit; input routing must preserve capture ownership. |
| Perform FX | Filter / Gate | Delay / Reverse | Reverb / Crush | Stutter / Cutter | T names FX page and separate performance recording/replay actions. Global Record/Play remain Pattern controls. −+ and keys preserve gesture release. |
| Slice / Sound Sets | Unassigned in first slice | Unassigned | Unassigned | Unassigned | T forms/list/actions and existing fallback. No encoder audition/auto-adopt/auto-install inferred. |

Every encoder has a visible T label, unit, draft/committed value and disabled reason. Encoder rotation must not silently switch from draft to live commit. Sequence retains Apply; Sample has current gesture-end commit; Perform uses engage/move/release. Unassigned encoders cannot mutate anything. Encoder detents, acceleration, push capability, end-of-gesture signal and pickup rules are unconfirmed hardware properties. Touch/keyboard alternatives must provide all implemented actions.

### Product decisions pending confirmation

| Decision | Proposed bounded resolution | Why confirmation is required / consequence until resolved |
| --- | --- | --- |
| D01 Global transport — approved responsibility, bounded transitions open | Independent global Play/Stop and current-Pattern Pad-action Record toggles; page navigation does not redefine/stop them | Disabled Play/touch-only Stop/mode-local Record proposals are superseded. Decide Record-while-stopped and Play/Stop-during-recording, restart/resume/count-in without retracting approved responsibilities. Current source separation is a capability dependency, not a product redefinition. |
| D02 Pad select versus trigger | Add explicit silent T selection; preserve existing P performance path and capture ownership | Decoupling existing Sample select+play changes interaction. Define pointer/keyboard/MIDI behavior, empty Pad picker and whether any focus follows hits. |
| D03 Back, drafts and destructive confirmation | Local unapplied forms get discard/keep-editing choices; irreversible write actions keep explicit confirmation where already present | Current captures Close stops/closes; several recovery/set discard actions are immediate. Do not claim universal preservation/undo. Decide dirty-form lifetime, source/mode switch and stopped Performance behavior individually. |
| D04 Four encoders / −+ | Mirror currently visible existing controls and units; no push/acceleration assumption | Device signals and gesture commit boundary unverified. Limit U1 to touch forms until approved. |
| D05 Six modes and System | T More modes for Slice/Sound Sets, persistent T System; four L navigation keys unchanged | Software settings is reachable without pretending Logo is physical. Decide hardware System access and mode-menu return focus. |
| D06 Event-grid target and projection dependency | Preserve a real read-only Sequence event grid as the desired final outcome; verify its Facade projection and record a dependent capability Task if absent | Define verified event data and grid scope without assuming the example's 8 tracks/64 steps are limits. A provisional text/metadata slice cannot silently redefine the final UI. Missing projection is a dependency, not grounds to remove the grid; approved global playback has the separate §7 capability dependency. |
| D07 Visual direction / device / scale | Preserve reference geometry; desktop first with usable fallback at small/zoomed viewport | Reconcile older #522 shell/viewport brief with four-region direction, pick target devices and approved tokens/type/motion. Static reference does not settle #522 phases. |
| D08 Extra pictured controls | Keep unsupported actions out of active UI | New/Save/Save As/Copy/Grid subdivision/Master/Solo/LP/HP/BP lack corresponding current surface actions. Sample Mute and Sound Set audition ARE present; do not misclassify those. |

No new Contract, concurrency rule or Provider is decided here. Hosts continue through Application Facade; layout preferences stay out of Project Truth; derived Runtime Snapshot never becomes persisted authoring state.

## 8. State, focus, accessibility and scale proposal

| State | O display | T/P behavior and recovery |
| --- | --- | --- |
| Empty/no Project | “No Project” | Project Import/Open route; disabled capability-dependent modes explain prerequisites; System still reachable |
| Assigned/idle/selected | Stable address and context; selection labelled | Empty text/icon distinct from Assigned; selected outline + text, not color alone. Selection is not a played receipt. |
| Loading/import/inspect/prepare | Named operation and available progress/revision | Busy controls use current guards; show loaded metadata only for matching identity. Cancel only where a real cancellation path exists. |
| Audio suspended | Suspended text | Explicit Activate audio in T; no clickable upper-screen prompt |
| Recording/capturing/switch pending/flushing | Label exact owner and phase; pending target separate from active | Capture modal and armed Pad semantics take precedence; disable duplicate/inapplicable actions; never use a red dot alone |
| Playing / rejected / muted | Only verified outcome; muted icon/text | Current trigger outcome does not prove sustained acoustic playback duration. Errors need code and route; identity color cannot imply acceptance. |
| Draft / submitting / saved but not prepared | Distinguish draft value, committed revision, runtime revision | Apply or current gesture commit; cancel restores local preview only. Retry Prepare/Refresh, not repeat already committed mutation |
| Recovery / unknown outcome | Candidate count or “result needs inspection” | Inspect/Refresh before retry; original/alternate destination controls; Discard separate from Back |
| Disabled / failure | Readable reason, stable context | Reachable prerequisite/recovery action in T; non-color marker, accessible names and error announcement; no hidden essential control in O |

Navigation proposal: L mode keys → Banks → context controls → P → T follows a documented, predictable DOM focus order; changing mode restores that mode's valid focus target, else its T heading/first control. Selectors and numeric fields keep their native arrow behavior. Global hotkeys must ignore editing targets and inert/modal background. Tab moves focus, never triggers Pads; Enter/Space use current semantic button/Pad behavior. A modal returns to a connected opener or a defined T context fallback. Do not disable browser zoom or intercept shortcuts globally to simulate hardware.

The 880×592 geometry is the reference at scale 1. Proposal: fit/reflow using a usable fallback rather than shrinking controls until unreadable; preserve 4×4 spatial identity. Verify at desktop 1440×900 and widths near 1024/880/768 with browser zoom 100/125/150/200%, keyboard-only and a real touch device. These are proposed test points, not a certified minimum viewport or device list. At high zoom/small viewport use accessible scrolling/reflow or existing layout; never make O interactive to compensate. Final physical hit area in mm and CSS pixels requires measurement on named devices; 32 design units is not a touch compliance claim.

Target contrast, text scaling, visible focus, accessible names and non-color state need measured review. Reduced-motion removes pulsing/decorative transitions while keeping static recording/pending/selection cues and state announcements. Existing Three.js decision remains a future visual-layer constraint: DOM owns input, focus and text; WebGL failure must leave a playable semantic UI. No renderer dependency or GPU performance proof is part of this draft.

## 9. #522 artifact and stage evidence audit

Read-only live issue body and five comments inspected on 2026-09-11. Issue is OPEN. The body's descriptions of old disabled Perform and historical `docs/superpowers` paths are not current capability evidence; current code and relocated documents take precedence for this mapping.

| Stage/material | Evidence actually found | Reuse and remaining gap |
| --- | --- | --- |
| July visual history / Stage 7 IA | Existing `docs/design/2026-07-24-stage1-creator-workspace-ui-design.md`, `2026-07-27-polanyi-living-instrument-ui-design.md`, reference HTML directory, `2026-08-07-lmdj-stage7-creator-editor-design.md` | Historical artifacts/IA inputs, not three new specimens or current hardware prototype. No retired Host/contract workflow adopted. |
| Confirmed constraints brief | `docs/research/2026-09-01-creator-visual-language-brief.md`; [comment](https://github.com/endaye/lmdj/issues/522#issuecomment-5496550905) explicitly says specimens not started | Reuse instrument body, fixed identity, honest state, desktop audience. Four-region evolution needs reconciliation with older shell wording. |
| ThreeUI research | `docs/research/2026-09-02-threeui-creator-visual-effects-research.md`; [shipping comment](https://github.com/endaye/lmdj/issues/522#issuecomment-5498619959) names PR #545 and squash `28af2795f9eacc39413efed00abc2ee499b84807` | Landed research input; comment explicitly leaves specimens/direction/approved design/implementation outstanding. Historical reported portal pass is not U0 verification. |
| Three.js visual constraint | `docs/prd/decisions/2026-09-02-creator-web-threejs.md`, `docs/research/2026-09-02-creator-visual-language-threejs-amendment.md`; [comment](https://github.com/endaye/lmdj/issues/522#issuecomment-5498392722) | Reuse single visual layer/semantic UI/fallback constraint. Does not select direction, prove GPU performance or authorize dependency addition. |
| Hardware reference | `docs/design/2026-09-11-lmdj-hardware-ui-layout-reference.md` records geometry and Figma reference nodes | Historical pages were static. The current twenty-four-frame draft is recorded separately in §10; neither establishes device acceptance. |
| Migration handoff | [comment](https://github.com/endaye/lmdj/issues/522#issuecomment-5633697107) assigns #1214–#1222 under #1207 | Confirms U0 carries W1/W2 review; explicitly does not change historical completion. |
| Phase 1 specimens / Phase 2 selection | Reviewed comments plus local artifact inventory contain research/constraints but do not demonstrate three qualifying specimens and an accepted direction | Evidence not established by this audit; do not claim no such artifact could exist elsewhere. Explicit qualifying links and decisions are still required. |
| Phase 3 / W2 | Source mapping, twenty-four draft frames, narrow shown-preview approval and partial pointer observations (§10) | Not Phase 3 exit. Unshown decisions/focus/state approval and remaining stable-slice observations require disposition, alongside `/hosts/creator-web/` impact. Record actual touch precheck OR an explicit gap; full device/audio acceptance is not a newly imposed U1 prerequisite. |
| Phase 4 | Existing Creator functions are implemented source, not proof this new visual spec landed | U0 does not close #522 or authorize subsequent implementation. |

## 10. Existing Figma draft and remaining verification

The following twenty-four frame nodes exist in the Figma design file, as reported by the prototype updates on 2026-09-11. Links identify existing draft frames, not completed acceptance flows. Partial actual-pointer observations are recorded below. The example branches, Pattern 02 resolution and empty-context handoffs are simulations; they are not working forms or an embedded existing application. Verified readback and remaining limitations are distinguished below.

These historical prototypes do not implement the subsequent approved global transport decision (§7). Their Record/Stop labels, touch-only routes and disabled repeat Record controls document earlier simulations, not the final global toggle mapping or combined-state acceptance.

| Draft frame | Node link | Source interpretation / limitation |
| --- | --- | --- |
| Audio required | [100:746](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=100-746) | Draft entry for audio prerequisite; not a verified empty/no-Project entry |
| Ready | [100:1611](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=100-1611) | Sequence stopped with recording prerequisites available; Ready is a presentation label |
| Recording | [100:2476](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=100-2476) | Corresponds to accepted `recording` state, not merely a Record click |
| Flushing | [100:3341](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=100-3341) | Corresponds to Stop in progress; draft uses a simulated 1.5-second transition |
| Committed | [100:4206](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=100-4206) | Feedback for stopped plus committed revision; `committed` is not a SequencePhase |
| Command error | [100:5071](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=100-5071) | Error overlays retained phase; source has no generic `failed` SequencePhase |
| Recovery | [100:5936](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=100-5936) | Original or selected alternate existing Pattern only; corrected original-recovery action is linked below |
| Discard confirmation | [100:6801](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=100-6801) | Proposed D03 safeguard; cancel/back must leave the recovery candidate intact |
| Sequence menu | [103:842](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-842) | Example branch entry; Ready→menu and Tempo cancel return observed in current pointer recheck |
| BPM draft | [103:1715](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-1715) | Preset example 120→124, not full 40–240 integer editing |
| BPM applied | [103:2588](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-2588) | Simulated applied feedback, not a settings receipt |
| New Pattern draft | [103:3461](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-3461) | Four-bar preset example, not a complete 1/2/4/8-bar form |
| Pattern created | [103:4334](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-4334) | Simulated creation feedback, not persisted Pattern identity/revision |
| Pattern selection | [103:5207](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-5207) | Example selection; do not assume alternate recovery is implemented by this frame |
| Switch pending | [103:6080](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-6080) | Simulates current/pending distinction; no actual boundary receipt |
| Switch confirmed | [103:6953](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-6953) | Simulated confirmation; real source requires matching authority/boundary |
| System | [103:7826](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-7826) | Describes handoff/actions; no actual old-app/runtime integration |
| More modes | [103:8699](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-8699) | Describes mode handoff; does not prove live fallback reachability |
| No Project | [103:9572](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-9572) | Empty-context System/handoff/return navigation observed; actual import not verified |
| Existing workspace handoff | [103:10445](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-10445) | Handoff explanation only, not the existing application |
| Pattern 02 flushing | [106:988](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=106-988) | Upper display SEQUENCE/02; simulated Stop resolution with a 1.5-second timer |
| Pattern 02 committed | [106:1861](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=106-1861) | Upper display SEQUENCE/02; simulated committed feedback, repeat Record disabled/unwired |
| System — empty | [114:1012](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=114-1012) | Dedicated empty-context System proposal; no live System action |
| Existing workspace handoff — empty | [114:1886](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=114-1886) | Dedicated handoff proposal; not running the app or opening a Project |

The earlier reported structural readback covers the first twenty roots: each is 880×592 with a 368×368 touch region, expected fonts and zero interactive descendants in the upper display; the reported check result is `faults: []`. Sequence menu and No Project screenshots were also inspected. Pattern 02 frames subsequently formed the earlier twenty-two-frame baseline; the empty-context additions now bring the inventory to twenty-four. Their separate evidence below does not expand the historical twenty-root structural audit.

All U0 grids are labelled “ILLUSTRATIVE GRID / NOT LIVE EVENT DATA”. No Project hides the grid and shows sixteen neutral disabled Pads. These labels preserve the distinction between simulated artwork and the desired live read-only event grid in D06; they do not discharge the projection dependency.

Reported inspection: all eight frames are 880×592 with a 368×368 touch screen; upper display has zero interactive descendants. Space Grotesk / IBM Plex Mono fonts were verified, and Ready + Discard confirmation screenshots were inspected without clipping. Original reference page 19, node `88:706`, had no prototype reactions. These are layout/structure/visual findings, not end-to-end input evidence.

Existing flow names: **U0 draft / Sequence recording**, entry `100:746`; **Uncertain result and recovery**, entry `100:5071`. Subsequent correction/readback verified [Recover original Pattern, 101:893](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=101-893) → Committed `100:4206`; [description 101:892](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=101-892) now describes original/existing targets. [Error Back control 101:886](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=101-886) has its reaction removed and is disabled with “Refresh before continuing”. The incorrect new-Pattern recovery route is corrected; this does not establish an alternate-existing-Pattern selection/apply flow.

Configured touch-only draft navigation: Audio required → Ready → Recording → Flushing → Committed (simulated 1.5-second timer); Command error → Refresh → Recovery; Recovery → Discard confirmation → cancel/back. Configuration does not prove actual pointer playback or real runtime receipts. In source, Refresh enters recovery only when queried authority/candidates warrant it; not every command error implies recovery.

Latest reported link readback: Ready “Sequence options” → Sequence menu `103:842`; Recording “Switch Pattern” → Pattern selection `103:5207`; Switch pending uses a simulated two-second timer → Switch confirmed `103:6953`. Example reset links explicitly say “Restart menu example”. Pattern created's Record control is not wired; it does not incorrectly record the old Pattern 01. Neither timer represents an actual runtime boundary or persistence acknowledgment.

Earlier correction readback verified the actual reaction IDs for [Stop 103:7811](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=103-7811) in Switch confirmed → Pattern 02 flushing `106:988` → simulated 1.5-second timer → Pattern 02 committed `106:1861`. Both resolution frames show SEQUENCE/02. The wrong-Pattern-01 Stop context was fixed structurally, and the corrected branch is now pointer-observed in the current evidence table. It remains simulated feedback, not a real stop receipt. Repeat Record from created/committed Pattern 02 is explicitly disabled and unwired; menu reset remains explicitly labelled Restart. The earlier pre-review editing status is historical; shown-preview approval and subsequent current observations are recorded below. No additional prototype edits accompanied this final evidence batch.

### Pointer observations and approval scope

Evidence update recorded at documentation HEAD `fbc41830e67e60f3f134d547aa348e76c3ee3877`; the code inventory's source HEAD above remains unchanged. The shown layout/flow preview has the narrow approval linked at the top of this spec. That preview did not approve unshown choices or focus/keyboard behavior. The subsequent D01 global-control responsibilities are approved separately; their bounded combined-state details and unrelated D02–D08 remain open.

The following observations were supplied by the controller from actual in-app-browser pointer navigation. Current recheck viewport: 998×1128; accessibility-tree (AX) URL checked after every click, screenshots inspected after key far-side states, not after every repeated navigation. Node links above identify the frames; these are reported observations, not an independent rerun in this documentation update.

| Evidence scope | Pointer action / path | Observed destination and feedback |
| --- | --- | --- |
| Current recheck | TAKE COMMITTED `100:4206` → Back to Sequence | `100:1611`, READY |
| Current recheck | READY → Sequence options | `103:842`, Sequence menu |
| Current recheck | Menu → Tempo | `103:1715`, upper BPM 120, draft 124 |
| Current recheck | Draft → Cancel | `103:842`, upper BPM remains 120 |
| Current recheck | Menu → Tempo again | `103:1715`, preset draft reopened |
| Current recheck | Draft → Apply 124 | `103:2588`, upper BPM 124 / TEMPO APPLIED |
| Current recheck, final batch | Applied `103:2588` → Restart menu → New Pattern | `103:842` → `103:3461`, four-bar preset, current Pattern 01 |
| Current recheck, final batch | New Pattern draft → Cancel | `103:842`, current Pattern remains 01 |
| Current recheck, final batch | Reenter New Pattern → Create 4 bar | `103:4334`, upper SEQUENCE/02 / PATTERN CREATED; Record dim and labelled not wired |
| Current recheck, final batch | Restart menu → Back → Record → Switch Pattern | `103:842` → `100:1611` → `100:2476` → `103:5207` |
| Current recheck, final batch | Request 02 | `103:6080`, upper 01, current 01 / pending 02, switch-pending |
| Current recheck, final batch | Observe pending timer completion | `103:6953`, upper 02, current 02 / pending none |
| Current recheck, final batch | Click Stop `103:7811` | `106:988`, upper 02 / flushing |
| Current recheck, final batch | Observe flushing timer completion | `106:1861`, upper 02 / stopped / COMMIT CONFIRMED; repeat Record dim and not wired |
| Current recheck, direct scenario entry | Navigate directly to prototype `100:5071`, then click Refresh | `100:5936`, RECOVERABLE TAKE; error was not induced from live recording |
| Current recheck, final batch | Recovery → Discard | `100:6801`, DISCARD THIS TAKE confirmation |
| Current recheck, final batch | Confirmation → Cancel | `100:5936`, candidate fixture still present |
| Current recheck, final batch | Recover original | `100:4206`, upper 01 / TAKE COMMITTED fixture |
| Carried-forward controller history, not current recheck | Audio `100:746` → Ready `100:1611` → Recording `100:2476` → Flushing `100:3341` → Committed `100:4206` | Earlier pointer path reported observed; simulated recording/flush/commit feedback only |

Playback is now accessible for the current recheck. The earlier login-wall observation is historical and no longer describes a blanket access blocker; no authentication method or login change is inferred. The final batch uses AX URLs after every click and screenshots after key far-side states; no screenshot coverage is claimed for every repeated navigation. No additional Figma edits were made in that batch. These observations establish only the listed pointer-enabled prototype simulations. Preset 120→124 and four-bar creation are not full value editing; simulated labels/timers are not native audio, revision persistence, storage, physical touch, keyboard or focus evidence.

### Subsequent empty-context correction and pointer evidence

After documentation HEAD `53f13e32abf98457f987d6629a21c0f94a6f5c99`, a supplied canvas-click check reproduced No Project→shared System incorrectly showing Sequence 01, 120 BPM and assigned Pads; the shared handoff also returned to a populated menu. These were prototype fixture-context defects, not Project mutations. Dedicated empty System `114:1012` and handoff `114:1886` now replace those empty-context routes; populated System/handoff remain unchanged. Both new roots are reported 880×592, reuse existing neutral components/fonts, preserve empty overview/Pads in screenshots, and pass the reported font assertion `wrongFonts: []`.

Corrected edges: `103:10430`→`114:1886`, `103:10431`→`114:1012`; Existing controls `114:1870`→`114:1886`, Back `114:1871`→`103:9572`, Return `114:2744`→`103:9572`, System `114:2745`→`114:1012`.

Separate fresh two-root readback: `114:1012` and `114:1886` each measure 880×592, upper display 752×176 and both lower P/T regions 368×368; upper root and descendant reactions are all empty. System P/T IDs are `114:1682` / `114:1818`; handoff P/T IDs are `114:2556` / `114:2692`. Existing populated return controls `103:8685` and `103:11303` still target `103:842`. This is a scoped new-two-root check, not a twenty-four-root aggregate pass.

| Subsequent pointer check after fresh browser reload | Observed far-side result |
| --- | --- |
| No Project `103:9572` → System empty `114:1012` → Handoff empty `114:1886` → Return No Project | Empty context retained throughout; no populated Pattern/Pad fixture introduced |
| No Project → Open/Import → Handoff empty → System empty → Back No Project | No Project and unavailable Sequence retained throughout; handoff explicitly remains a proposal, not the running app, with no Project opened |

AX checked after every click; screenshots inspected at key far-side states. This supplied correction/readback and pointer evidence closes the empty-context navigation defect only. It is not actual import, live System/fallback, audio/persistence, focus or device evidence and does not broaden the shown-preview approval.

Explicit open gaps:

- No Project's simulated System/Open-Import handoff and return paths are now observed with empty context preserved. Actual Project import/open, System operations and live fallback remain unverified; these handoff simulations do not establish an operational start journey.
- Physical shortcuts are not connected. Ready/Recording Refresh controls are presentation only.
- The requested switch to Pattern 02, timer confirmation, Stop and Pattern 02 flushing/committed feedback are now pointer-observed. Switch Cancel and Stop while switch-pending were not clicked. Repeat Record from created/committed Pattern 02 remains explicitly disabled/unwired and was not clicked.
- Direct error-scenario entry, Refresh, Discard confirmation, Cancel with candidate fixture retained, and Recover original are now pointer-observed. The error was not reached by inducing a recording failure; confirmation's actual Discard action was not clicked. Recovery's Committed fixture is not an actual `applySequenceRecovery` receipt. Alternate recovery still requires selection of an existing Pattern before apply; no new-Pattern recovery capability is inferred.
- The timer does not prove persistence, Stop acknowledgment, revision reconciliation or reopen/inspect. Discard cancellation does not prove actual discard success.
- BPM preset open/cancel/reopen/apply, four-bar New Pattern cancel/reenter/create, return to Ready and the listed Pattern-switch branch are now pointer-observed. Full BPM value editing, invalid input, other Pattern lengths, Swing and Quantize remain gaps; presets do not discharge these requirements. Unwired controls were not clicked.
- Alternate-existing-Pattern recovery selection/apply, actual System/runtime actions, Sample capture/trim fallback and live More modes/existing-workspace handoff remain gaps. The twenty-four frames do not cover or verify all flows.

Record actual selection → operation → feedback → cancel/back observations for each required flow. Add real node IDs as the missing states are created; do not assign invented IDs to planned coverage. Static screenshots and configured reactions alone do not satisfy W2.

Physical touch prevalidation: not performed; explicitly recorded as a gap. The exact U0 brief requires “记录真实触摸预验或其明确缺口” (record a real touch precheck OR its explicit gap), and separately requires user approval of layout, focus and state proposals before U1. It does not require a complete physical audio journey before U1. Preserve W2 interactive-prototype observation requirements without replacing them with static boards; an explicit touch gap is not a claimed touch pass and does not supply missing layout/focus/state approval.

To close the touch gap later, record a named device/browser/orientation/viewport/zoom and observations of hit areas, mistaken hits and focus/scroll interference. Full audio journeys, simultaneous input, keyboard/MIDI alternatives, reduced-motion and broader browser/device acceptance belong to their applicable implementation/acceptance scope; do not promote all of them into new U0 gates. Partial browser playback is now observed as documented above; unreported branches remain gaps.

### Remaining U0 disposition before U1 versus later acceptance

- Lock the bounded slice's still-unshown control/state rules: Pad selection versus triggering, applicable encoder/transport/direction behavior, Back/draft ownership, System and layout-selector/fallback access and preference location. Confirm or explicitly defer inapplicable D01–D08 details; do not require all future screen content to be designed or implement unresolved semantics.
- Obtain approval for the remaining applicable focus/state proposal and device/scale/non-color/keyboard-alternative/reduced-motion design boundaries. The shown-preview approval stands; it is not evidence that these unshown details were approved or tested.
- Complete/disposition W2 observations for the stable slice's empty/loading/failure/disabled/recovery and cancel/back paths, and confirm every inventoried operation has a new route or retained usable old-layout route, including audio/MIDI/retry/reports. Current pointer observations close only the table's paths. Keep the explicit physical-touch gap; a full physical audio journey is not a prerequisite.
- Complete the U0 spec review/file checks and authorized integration required by the plan. Neither approval of a preview nor documentation commit alone completes U0 or #522.

U1 implementation owns the actual opt-in shell, one session/input owner, non-interactive overview DOM, usable old-layout fallback and 200%/small-viewport paths with its declared tests. U2 owns real Sequence value editing, persistence/recovery and boundary verification; later mode Tasks own their working workflows. Prototype presets and handoff descriptions need not become live product forms before U1, but their design rules/routes must be resolved for the bounded slice. D06's desired real event grid and conditional projection-capability dependency remain intact; metadata-only feedback does not redefine the final outcome.

Manual inventory review covered six `CreatorMode` members, global StatusBar/ErrorPanel actions, all listed action-bearing components, source handlers, current guards and source/draft/receipt distinctions. Known behavioral ambiguities are in D01–D08; this is coverage of the design audit, not runtime acceptance.

U0 file checks: `git diff --check`; ownership gate `python tests/build/ci_change_scope_test.py -k test_every_tracked_path_has_explicit_ownership_or_full_rule` against an index containing this new spec. An index that omits the new file cannot establish its ownership. No new product tests or gates are introduced for a prose draft.

Eventual Sequence implementation should declare exact files separately and select existing low-tier suites as appropriate: `test/sequence_surface.test.tsx`, `sequence_state.test.ts`, `sequence_actions.test.ts`, `workspace_shell.test.tsx`, `input_controller.test.ts` under Creator. Browser acceptance must assert actual state after each §5 transition and verify non-interactive O, stable P, focus ownership and one input/capture owner. These suites were inspected as available paths, not executed as evidence of a new UI. No implementation Task is opened by this section.

## Version Management

Version impact: none

Reason: source-backed design draft only; no Product Build, Host, Module, Provider, Contract or Assembly identity changes. No release or immutable snapshot allocation.

## Documentation Impact

Documentation impact: none

Reason: this bounded update records the approved global transport responsibilities and source-backed capability dependency, retaining narrow shown-preview approval, historical prototype evidence and unresolved proposals; it changes no implemented behavior, portal facts, diagrams, tooling or projected identities. It is not the final approved #522 Phase 3 policy/spec exit. Final approved design integration must reassess required `/hosts/creator-web/` updates (and any affected diagrams) in its declared Task and run `scripts/docs-site.sh check` when required.
