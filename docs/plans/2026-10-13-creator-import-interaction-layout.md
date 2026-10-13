# Creator Import Audio interaction layout (U12d)

Relates to #2112 and #2225. Final results on the rebased head are recorded in the last section.

## Current-base premise audit

Fresh `git fetch origin main` resolved `c4bde2ffa4390eb83e5ccc1e0313f933732bf88a` on 2026-10-13. This isolated `feat/creator-import-interaction-layout` worktree starts at that exact revision with `--no-track` and command-local `core.symlinks=true`. All tracked symlink entries were checked as actual symlinks. Live #2112 body/comments were read and retained at `/tmp/lmdj-u12d-issue-2112-start.json`.

| Premise | Disposition and current evidence |
| --- | --- |
| Right touch-panel modal placement absent | Already delivered by Capture #2148 / `0ae6dbd2`; `ModalDialog` has optional `touch-workspace`, same native lifecycle and upright rotated behavior. Reuse it; no Modal edits. |
| Import needs the new layout | Outstanding: `long_source_editor.tsx` still uses the default centered dialog and shared Capture header/actions. The scoped Import layout has not landed. |
| Separate Preview and Stop | Outstanding: current `togglePreview` uses local `previewing`; source preview resolves after start, natural ended is private. Expose two existing operations, never a fabricated Playing state. |
| Trim/Playback and shared Sample browser | Already delivered by #2140 / `14fcb4df` and #2150 / `28ff18c5`. Preserve the complete 20 current cases, all deadlines and every idempotent SHIFT History helper. Current file is 91,279 bytes / SHA256 `f1c2ea1d3d09866e356a9711816cf3ad6d278869aa3f6acb3ede3a9b91e1fab2`. |
| Target/quota/commit/cancel/Delete lifecycle | Already delivered: `SampleSurface.startLongImport`, `commitLongSource`, `releaseLongSource` and the captured draft quota/source owner remain authoritative and untouched. Import layout must preserve these branches. |
| Geometry, keyboard and real far-side acceptance | Outstanding for this Task; prior unrelated passes do not prove this layout. Keep full original journeys and append the six named viewport Import cases below. |

Root received positive narrow shared-browser custody from MBP at 11:35:15Z (`msg_a321727b8d65`, `msg_873f2453e7e2`, retained `/tmp/lmdj-mbp-inbox-latest.json`). This releases only current-main Sample browser append-six work; it does not transfer D03 ownership or permit reading/editing/copying D03 WIP. Numeric stays frozen in its separate worktree.

## Design evidence

Mandatory `figma-design-to-code` was read before high-fidelity context/screenshot of file `GPFarNiZNsjLQzfG9kR8DO`, node `407:6408`. Complete fresh evidence at `/tmp/lmdj-u12d-import-figma-20261013T113300Z/`; report SHA256 `7fa9196f9d53fc57dcba1d7bb0ac643722a6ca74333e585d412fd91620d677ed`, PNG SHA256 `a1ca685863e95bdb6dcef63d29dab41cc7865d875df08b786bfd116b392e4a61`.

The pane is 368 square,16 inset,8 group gaps; IMPORT AUDIO/TARGET header, waveform, SELECTION START/LENGTH, separate Preview/Stop, Commit/Cancel, full-width Delete last. Faces are32 high/Mono9-13; ranges have16-high graphics. Actual targets must remain >=44 CSS px under the approved small-screen policy. The static frame's child layout totals382 in368 and already requires vertical scroll; retained quota/errors and full targets need real internal scrolling. A reachable stable action footer is the scoped adaptation, not a claimed Figma sticky annotation. All normal/failed/committing states and lifecycle absent from artwork retain source semantics. Dynamic waveform is real source data; no static Figma waveform/image replaces it. No in-scope static image assets exist.

## Exact seven-file task

1. `apps/creator-web/src/components/long_source_editor.tsx`: import its scoped CSS, use existing `ModalDialog placement="touch-workspace"`, organize Import Audio heading/target, source waveform, selection rows, quota/details/error region and stable actions. Separate explicit Preview selection and Stop preview using the existing source methods. Keep Delete and all committing/no-room/error branches.
2. New `apps/creator-web/src/components/long_source_editor.css`: scope all appearance to this dialog; reuse current control tokens/32-face/actual-44 target policy, internally scroll metadata/errors while action region stays reachable. No global control override.
3. `apps/creator-web/test/long_source_editor.test.tsx`: keep the existing quota/failure/retry case and add discriminating component cases described below.
4. `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`: preserve all current 20 generated cases and append six viewport Import journeys; only narrow additional helpers or an unavoidable label locator adjustment may affect the original prefix, with an explicit retention diff.
5. `apps/docs-site/docs/hosts/creator-web.mdx`: narrow current long-source presentation fact adjacent to its existing ingestion explanation; retain Delete's committing/import-cancellation description and all unrelated Capture/Trim/history facts.
6. `apps/docs-site/docs/hosts/creator-interactions.mdx`: only §4.6 Long Source and directly corresponding source/test mapping if needed; retain its target, failure, Delete and Escape semantics.
7. New `docs/plans/2026-10-13-creator-import-interaction-layout.md`: these files, current premises, original checks, causal RED, actual results and explicitly outstanding acceptance.

No changes to SampleSurface, App, ModalDialog, controller/reducer, ingest source/API, global styles, Numeric browser, Capture browser, Core, SDK or producer. If the seven paths cannot implement a required invariant, stop for a finite scope decision rather than moving ownership to another file.

## What exists, what changes, what remains real

`long_source_editor.tsx` already renders source-derived waveform/format/duration, start and length ranges, revision-bound quota/Pad usage, no-room rejection, commit failure retention, Delete, Cancel and commit. Its current `previewing` local toggle is not playback truth: `DecodedLongSource.preview()` resolves after starting; natural `ended` privately clears its node/context. The layout must not expose continuous Playing/progress/duration claims from that flag.

The existing preview method (`long_source_ingest.ts:468–516`) validates the exact frame range, calls `stopPreview()` before every start, creates an actual AudioBufferSourceNode, and starts `(0, startFrame / 48000, frameCount / 48000)`. Stop clears ownership first and safely stops/disconnects/closes whatever remains; repeated Stop is idempotent. Separate Preview and Stop are direct access to these existing operations. Preview always restarts the current selection, including after natural completion; Stop remains callable without pretending the UI knows whether a node is sounding. Preserve selection validation and committing guards. Do not change pending-preview, cancellation or ownership semantics inside this presentation task.

`SampleSurface.startLongImport` captures slot, quota revision and decoded owner. Its epoch check releases late decoded results. `commitLongSource` encodes the current selection against that captured quota and imports to the draft slot at its captured expected revision; success releases the source, failure retains it. `releaseLongSource` invalidates the epoch and releases its source. These functions stay untouched. The panel's TARGET comes from `quota.slot`, never a later selected Pad. Decode errors stay at their existing Sample entry point.

Capture's merged ModalDialog option already positions the same native dialog against the touch workspace, repositions on resize/scroll, remains upright in rotated layouts and uses scale >= 1 with viewport clamping. It preserves showModal, inert/aria-hidden background, focus trap, non-dismissable backdrop, Escape and return focus. Import opts in; it does not remount or implement another modal. Existing committing Escape/Delete behavior is retained, not silently redefined.

## Complete owning low-tier checks (future; all UNRUN here)

Whole unchanged owning files plus added component cases:

```sh
npm --prefix apps/creator-web test -- run test/long_source_editor.test.tsx test/long_source_ingest.test.ts test/modal_dialog.test.tsx
npm --prefix apps/creator-web exec -- tsc --noEmit -p apps/creator-web/tsconfig.json
node --check tests/platform/web/creator/creator_web_sample_editor.spec.mjs
```

Current source inventory is 1 LongSourceEditor case, 15 ingest cases (8 ordinary plus 3 post-decode and 4 failure-language rows), and 8 ModalDialog cases. New editor cases must distinguish old markup/control behavior: touch placement; exact original target and bounded long name; valid/no-room/saving/failure/conflict states; Preview twice with a changed selection restarts and Stop twice is harmless; natural ended followed by Preview; Cancel/unmount/commit cleanup; failed commit retains exact selection and retry works. Use the real DecodedLongSource with an observed AudioContext boundary for start/stop arguments, not assertions against a synthetic playing boolean. Preserve the original quota-bound failure→retry test in full.

Run these eight existing mounted cases in `test/workspace_shell.test.tsx` unchanged (file is read-only for this Task), with an exact alternation of these full names via `-t`:

- `bounds and escapes Replace display names, warns, cancels, and restores focus`
- `keeps pre-commit Sample import abort ownership on unmount`
- `keeps an imported empty Pad assigned and playable after selecting another Pad`
- `uses the same accept-filtered import path and keeps selection on unsupported audio`
- `Delete cancels a pending import and ignores its late completion`
- `Delete failure remains visible and does not project an empty Pad`
- `Delete invalidates a decoding source and discards its eventual result`
- `Delete waits for the selected Pad inspection to match the current Project revision`

These retain actual abort ownership, original selection, successful assigned/playable readback after selecting another Pad, exact projection/revision refresh, failure visibility, late import suppression and late decoder disposal. Do not replace them with shallow snapshots. Scope classification/declaration and whitespace checks follow the repository's current task procedure; stage only the seven declared paths.

## Full packaged Sample selection, retained without shortening

The current Sample browser file has 20 generated cases, not the old plan's 11: the original 11, U05a's 3 Playback viewport cases, and Trim's 6 cases. Original names and budgets remain intact:

- `packaged Sample Editor proves the real Facade v1-to-v2 journey` (600000 ms).
- `packaged Sample Editor clamps a plus-one-frame source and admits the quota-bound selection` (300000 ms).
- `Sample Editor WebKit capability boundary is explicit, private, and non-physical` (existing WebKit-only case and own timeouts).
- `re-importing a diverged Project Bundle recovers through Open local Project without a reload` (300000 ms).
- `Creator history preserves sound identity across modes, cancelled edits and persisted reopen` (300000 ms).
- `Sample playback parity commits, cancels, refuses, fails and reopens through the real Runtime` (300000 ms).
- `Sample tone parity commits, cancels, refuses, fails and reopens through the real Runtime` (300000 ms).
- `Pattern history keeps the Project open when its inventory anchor changes` (180000 ms).
- `Pad Delete commits while audio is inactive after a reopen` (300000 ms).
- `Pad Delete preserves recorded rhythm through Undo, Redo, reassignment and reopen` (300000 ms).
- `contextual Sample encoders merge one save, cancel old targets and restore monitoring level` (300000 ms).
- `Playback groups real toggle readbacks and keyboard actions at …`: 1440×900, 1024×768, 768×600; each 180000 ms.
- `Trim groups preserve real local viewport and editing at …`: 1440×900, 1280×720, 1280×600, 1024×768, 768×600, 768×1024; each 180000 ms.

Retain every old leg: real v1 import/assignment/revision; trim and PCM/playhead observations; reset; Replace cancel and commit; unsupported import; protocol/revision refusal; failed preparation and audio recovery; exact persisted reopen; quota +1 frame/chunk counts; history/Undo/Redo; playback/tone preview/cancel/refusal/failure/reopen; Delete/reassign; old encoder targets; all Playback and Trim geometry, native keyboard and Truth assertions. No skip/deadline/threshold change.

Once Root admits the heavy window, use one clean source checkpoint and fresh normal `bash scripts/creator-web.sh configure`, `build`, `package`, after the whole `bash scripts/docs-site.sh check`. Reuse official U05a/Trim Project and Sample fixtures only after `python3 tools/project-bundle/project_bundle.py verify <each-path>` and byte/hash readback; no Native regeneration is needed by this layout. Their prior identities are Project 767554 B/SHA256 `66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f` and Sample 995873 B/SHA256 `1f1dc9cf1c48626bd94d0096170d5c0832ca0aadfe2240d7253635f747b1dce3`; future reuse must verify actual files, not assume these receipts carry forward.

With a task-owned normal dist server and explicit existing `LMDJ_CREATOR_WEB_EXTERNAL_SERVER`, `LMDJ_CREATOR_WEB_BASE_URL`, `LMDJ_CREATOR_WEB_BUNDLE`, `LMDJ_CREATOR_WEB_SAMPLE_BUNDLE`, full Chromium and separate results-slot settings:

```sh
python3 scripts/local-audio-output.py --lane creator -- npm --prefix tests/platform/web test -- --project=creator-sample-chromium --workers=1 creator/creator_web_sample_editor.spec.mjs
python3 scripts/local-audio-output.py --lane creator -- npm --prefix tests/platform/web test -- --project=creator-sample-webkit --workers=1 creator/creator_web_sample_editor.spec.mjs
```

Both commands must select all original 20 plus the six additions, without grep. Retain the existing WebKit-only skip under Chromium and all 25 Chromium-only skips under WebKit; the latter actually executes the capability boundary. Numeric's separate spec is untouched and remains with its current owner; the prior Trim 21-case combined run is not misreported as today's Import selection.

## Six additional viewport journeys and far-side evidence

Use the same six current Trim viewports (including actual rotated portrait 768×1024), one deterministic complete Import case each, with a declared finite 180000-ms budget per new case. Add source/preview observation only through wrappers that call the original browser AudioContext methods and record actual starts/stops/ended; do not substitute audio or fake Runtime responses.

Each case opens a long-name file through the real Add/Replace path, reads Project Truth before edit, checks fixed target, waveform and quota, adjusts both ranges by native keyboard, then Preview→change selection→Preview restart→Stop→Stop→Preview→natural ended→Preview→Cancel. Read exact start offset/duration and observed stop/cleanup of the prior node after each relevant transition. After every draft-only action and cancel, re-read real `project.inspect` and compare authoring state/revision; confirm no import commit and no background Pad trigger. Reopen the file and commit an exact nonzero-start selection, read back sample metadata/frame count and new asset/Pad identity/revision, then reload/reopen and compare persisted Truth. The accepted commit must use the captured Pad, not a visible selection guess.

Retain failure/conflict/failed-selection retry coverage at component and existing mounted tiers. The original complete browser already owns real playback/tone failure→reopen legs; do not claim these exercise an Import commit failure. A new browser Import failure leg can use a real stale captured quota revision induced by a bounded public Project mutation while the modal is open: snapshot after that external mutation, click Commit, observe actual revision refusal with retained selection, and compare post-refusal Truth to that snapshot. Close and reopen refreshes quota before the successful commit. If the current public helper cannot achieve this without extra production source, report the finite test-only seam decision before implementation rather than manufacturing a successful/failing product response.

For each modal state, capture actual `getBoundingClientRect` of dialog/controls and center plus four edge `elementFromPoint` hit evidence for every enabled action/range; assert actual interactive targets >=44 CSS px, no target overlap, legible untruncated labels/values, dialog within viewport, upright portrait mapping, internal scrolling and reachable stable actions. Do not treat layout/offsetHeight/design-unit values as rendered size. Check native Tab/Shift+Tab containment, Escape cleanup, exact opener focus restoration and blocked background pointer/Pad keyboard input; backdrop alone must not dismiss. Save screenshots before and after scrolling plus geometry/readback JSON. Physical audio, Safari device behavior and screen-reader speech remain separate acceptance.

## Coordination and completion boundary

Capture and Trim placement dependencies are now committed. Shared `creator_web_sample_editor.spec.mjs` ownership was positively returned to D03 after Trim; the positive narrow handoff above is retained before touching it. Coordinate the two Portal Import paragraphs with their current owners. Existing Numeric work owns a separate Numeric browser file and is not an obstacle or a reason to edit it. No SampleSurface/App/controller writer permission is sought.

Root admitted this exact source preparation after positive shared-writer coordination. A later heavy window is separately required; retain every original negative/exit and stop for a concrete failure rather than retrying automatically. Bind tests to source hashes and the normal dist/package; record natural child cleanup and window return. Review, commit, push/PR, merge and physical acceptance remain distinct.

Documentation impact: required — `/hosts/creator-web` and `/hosts/creator-interactions`, Import-only current facts. Version impact: none — presentation reuses existing contract/API and does not allocate a Product Build. Pitfall impact: none presently — this read-only refresh found no new process invariant; implementation must re-evaluate actual events.

## Source preparation and dependency evidence

Root admits only source plus the declared focused component/tsc/syntax checks after source freeze. No install, Portal, Creator/Native/Wasm build or browser run during M1 heavy. The new worktree initially had no Creator dependencies. Before the explicitly authorized APFS private clone from frozen Numeric, package/lock hashes, Node26.7.0/darwin-arm64/ABI147 and all9 internal dependency symlinks were verified; no external symlink or package mismatch. The source dependency tree remains untouched and no build output is borrowed. Audit and exact clone argv/natural exit are in `build/verification/u12d/dependency-{preparation-audit,copy-receipt}.json`.

All Task tests and rendered acceptance remain UNRUN at plan creation. An independent source-review packet is required before any commit.

## Version Management

Version impact: none — this Task changes Host presentation using existing APIs/contracts and allocates no Product Build.

## Documentation Impact

Documentation impact: required — `/hosts/creator-web` and `/hosts/creator-interactions`, Import-only current facts. The full owning Portal check passed on the rebased head (last section).

## Source/light checkpoint — 2026-10-13 11:59 UTC

All seven declared files are authored; the current Sample prefix remains the exact91,279 original bytes, with six Import viewport cases appended. New cases import the existing official Sample bundle so emptyA01 and another assigned Pad are explicit prerequisites, independent of default catalog seeding. A public sample.update_pad on that other Pad advances the real revision and makes captured quota stale; no manufactured Runtime refusal is used by the new Import legs. Browser/source review and actual rendering remain pending.

- Original product + new editor tests:5FAIL/5PASS, naturalexit1 at11:48:54; expected missing independent Stop/restart/header/placement assertions. Receipt/log `build/verification/u12d/editor-red.{json,log}` retain source before/after hashes and all observed processes absent.
- Complete editor/ingest/Modal:33PASS, naturalexit0 at11:57:03; `components.{json,log}`.
- All eight named mounted import/Delete cases:8PASS/187 unrelated cases unselected, naturalexit0 at11:57:28; `mounted.{json,log}`.
- TypeScript attempt: naturalexit1 at11:57:41; `tsc.{json,log}`. The invocation without explicit-project remained at the WT root and printed compiler help; it did not check Creator and is not a product-type failure. Keep the original command/result. The command above now identifies the actual Creator tsconfig; a corrective check is pending coordination.
- Each executed command has contemporaneous declared-file before/after hashes and unchanged inputs; original33/8 passes bind the product/component source at that point. The final browser prerequisite/comment and plan receipt were added afterward, with no product/component edits.
- Browser syntax, scope/whitespace and independent source review remain pending at this checkpoint. WholePortal, normalbuild/package, all original20+new6 browser cases and physical acceptance are UNRUN. No stage, commit, push or PR.

User requested finishing already-started Tasks and stopping new derivation. Only existing Numeric8 and Import7 continue; no new work is derived from out-of-scope findings. Numeric received the next finite heavy window; this Import source packet is paused intact while Numeric runs.

### Corrected light checks and final source freeze

Root admitted correcting the same Task invocation. Explicit-project TypeScript found five test-only `ByRoleOptions` errors: Testing Library does not accept Playwright's `exact` option. Only those five redundant options were removed; literal-name matching remains exact. The actual type failure is retained as `tsc-project.{json,log}`, not folded into the earlier help-only setup failure.

The same complete three files passed again:33PASS (`components-corrected`,12:00:28–12:00:29Z). The owning TypeScript invocation passed (`tsc-corrected`,12:01:08–12:01:09Z), as did browser syntax and tracked diff whitespace at12:01:28Z. Each has explicit input hashes/natural exit/observed-child readback. The prior8 mounted cases bind identical product input; only test options, browser fixture preparation and plan receipts changed later. No mounted repeat was required.

All seven source files are frozen for independent review; source manifest/full patch are in `build/verification/u12d/source-seven-manifest.json` and `source-seven.patch`. Original Sample prefix remains byte-exact. No stage/commit or heavy checks; new-file scope77, wholePortal and complete packaged browsers remain pending later admission. This final plan receipt is a documentary delta after the checks, not a claim that those command receipts contain these later words.

## Independent SOURCE review correction — 2026-10-13

The frozen seven-file packet `source-seven.patch` (69,758 B, SHA256
`eb87da24aa5eda81576079baf38763d98c62955932ceaa88a4f8231cbffee216`) and its
manifest remain preserved. Independent reviewer capability_audit read all
seven source files, owning producers, original browser prefix and receipts;
report `/tmp/lmdj-u12d-import-independent-review.md` SHA256
`595e8f43f8e4d8383fdd045e087ddae3c82c89889ba9a9d99701fe3cf7397e1c` found one P2:
the new sky/dim custom properties had no definitions. This is a source-proven
colour defect; no prior browser colour PASS or measured failure is claimed.

The existing Task now defines those properties only on the Import dialog,
using Figma's selected sky `#95D4DF` and unselected dim `#7C877B`. No global
palette, event, handler, target, preview, commit or native Modal code changes.
Each existing new viewport journey records actual selected/unselected SVG
computed fills and the computed length-track background after its real partial
selection, before asserting independent literal RGB values. Both bin groups
must exist; a shared missing variable cannot make the two sides agree falsely.
Original20 cases, six additions, all geometry/journey legs and deadlines remain.
The eventual two browser invocations now both select the full26 (WebKit retains
its25 existing Chromium-only skips); no filtered WebKit invocation is planned.

Only CSS, the appended browser evidence and this plan changed after review.
Existing whole33 components,8 mounted and locked tsc remain historical behavior
and type evidence for unchanged TSX/test inputs; jsdom does not prove this CSS
colour correction. Browser syntax and whitespace are the affected light checks.
Actual computed-colour proof, complete26×2 browser selections, whole Portal and
normal build/package remain UNRUN pending Root's explicit heavy admission.

## Admitted dependency, staged scope and Portal checkpoint — 2026-10-13

After Numeric's actual release, Root admitted only this existing Import Task's
original finite sequence. The seven source hashes matched the independently
reviewed `79b600c0…` packet; current main `3f05b962902c9bf2d9c8c5f558ab3b4d033f5492`
does not change Import/Modal/ingest/App/shared Sample browser premises since
this Task's base. Its independent Sequence paragraphs in the two Portal files
do not replace this Task's Import paragraphs. No other owner's WIP was copied.

Own official docs install completed12:54:20–12:54:24 UTC, web `npm ci` completed
12:54:40, and its existing WebKit postinstall readiness `check` completed
12:54:49: all actual exit0, all six package/lock inputs unchanged. Exact seven
paths were staged, including the new local CSS and plan. A private preparation
assertion incorrectly compared the aggregate staged patch hash with the earlier
tracked-plus-untracked packet: both72,976-byte patches have seven byte-identical
diff sections in different order. This preparation error is preserved, not
reported as a pass. The shell mistakenly proceeded to scope via a newline;
its eventual outer0 does not prove that failed Python assertion passed.
The original scope run naturally completed77 PASS at12:55:12, exit0, with source
and locks unchanged. Root independently checked both complete patches, source
hashes and staged whitespace before explicitly admitting continuation. The
correct staged identity is `3b320e1e61a0e87840c1f56549a6714b5838ff6dc74574c8f6b89d8484d3118f`;
no scope repeat or product edit was needed.

The original whole `bash scripts/docs-site.sh check` completed
12:57:11.606389–12:57:57.224407 UTC, actual outer exit0:179 tests PASS,50 routes
and internal links valid. Raw log SHA256
`ae4ba71a2f913ce3cd9c0d88c563a5962368b19ab510909e859492bc10295af1`.
Before/after source/locks and observed child readbacks remain in
`build/verification/u12d/heavy-20261013/`; all children from these commands had
exited. This paragraph is the only source delta after that Portal input.
The upcoming atomic source checkpoint permits the normal own build/package;
packaged browsers, real computed colours and all52 selected journeys are still
UNRUN here. A source checkpoint is not completed delivery.

## Original packaged failure — 2026-10-13

The clean checkpoint `93955e8e` passed configure/build/package. Its complete
26-case Chromium selection ended 16 PASS / 9 FAIL / 1 existing WebKit-only
skip. All nine failures stopped in the original `importV1SampleProject` at the
retired Project overview phrase `44 / 64 Pads used`, before Import Audio
opened: three original cases and all six additions. The display already
existed on that base; the Import layout did not cause it. A test-only oracle
correction was prepared but never committed or pushed.

## Rebase onto main and final verification — 2026-10-15

Rebased onto `f2324bb395501916e13e18b21e6b5c32ae27ca8e`. Main had meanwhile
corrected the same retired overview assertion itself, keeping the visible
`44 Pads · 1 Patterns` count, the current Project card revision and a public
`project.inspect` inventory of four Banks of 16 Pads. The prepared correction
conflicted with that and was dropped in full. The original 20-case prefix of
`creator_web_sample_editor.spec.mjs` is byte-identical to main; this Task only
appends the six Import journeys, unchanged from `93955e8e`. Main did not touch
`long_source_editor.tsx`, ModalDialog, ingest or the Sample surface after this
Task's base, so every premise above still holds: Import still used the centred
dialog and a single local Preview/Stop toggle on main.

Results on the rebased head:

- `npm --prefix apps/creator-web test -- run test/long_source_editor.test.tsx
  test/long_source_ingest.test.ts test/modal_dialog.test.tsx
  test/workspace_shell.test.tsx`: 4 files, 232 PASS.
- `tsc --noEmit -p apps/creator-web/tsconfig.json`, `node --check` on the
  browser spec and `git diff --check`: all exit 0.
- `python3 tests/build/ci_change_scope_test.py`: 76 PASS with both new files
  staged; `scripts/local-ci.sh --list` selects creator, docs_static, portal.
- `bash scripts/docs-site.sh check`: 179 PASS, 50 routes and internal links
  valid.
- Packaged distribution built and packaged from the clean head, served by the
  proof's own `serve_distribution.py` invocation with no Catalog upstream,
  both proof fixtures generated by the proof's own functions:
  `creator-sample-chromium` 25 PASS / 1 existing WebKit-only skip, including
  all six Import journeys at 1440×900, 1280×720, 1280×600, 1024×768, 768×600
  and 768×1024; `creator-sample-webkit` 1 PASS / 25 existing Chromium-only
  skips.

An earlier run on the same head used `scripts/creator-web.sh serve`, which
defaults to the deployed Catalog. A live Sound Set install landed mid-journey
in four original history/parity cases and added unrelated revisions. The same
nine cases passed against main under that server, so it is a harness
difference, not a product defect; the proof server above has no Catalog and
removed it. That run is retained as evidence, not reported as a pass.

Not exercised here: real Safari/iPadOS, physical audio output and touch, and
the complete Creator proof's other lanes. They stay with their own owners.
