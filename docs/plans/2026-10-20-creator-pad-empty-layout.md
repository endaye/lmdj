# Sample Pad and Empty Pad interaction layout (#2226)

## Task and authority

One reviewable Task on `feat/creator-pad-empty-layout` in its isolated
worktree, initially parent Draft #2419 /
`27483b1f3df80d6dcd74b33c9e0efc6639c9f1e2`; now restacked onto the
verified shared-layout Draft #2420 / `3c67eea8eceb6acbdbbba823dfc5abc97f23de18`.
Refreshed integration main is `1581f3bd42616d36637b1d3131747bb51dee5f8e`.
The initial live open-PR inventory contained27 entries, none implementing or
referencing this U05c slice. #2226 is OPEN with no comments. The owner permits
development, Task verification, commit/push and a Draft child in the one
linear stack. Main is frozen: no merge/auto-merge, release/tag, deployment,
Channel promotion or Git cleanup. Independent current-head review is pending.

## Premise audit before implementation

- Already delivered: Pad palette/index/category override and default restore;
  current Pad identity; Reset/Delete/Replace/Capture semantics; Sample numeric,
  Playback, Trim and Slice; actual retained-Asset ASSIGN consumer in the stack.
  Reuse these handlers and their existing refusal/UNKNOWN/recovery states.
- Still outstanding at both main and this stack parent: Pad management renders
  technical details first, then ungrouped Replace/Delete/Record/Reset, then the
  palette. Slice lives in a separate global Sample navigation strip. This does
  not express the approved palette -> action rows -> destructive action ->
  category restore -> details hierarchy.
- Still outstanding: the default empty Sample view only says to select an
  assigned Pad and offers Add. Record is available only on Pad, and the empty
  entry lacks the current target, capture/permission explanation and primary
  Add/secondary Record grouping. The actual capture owner already exists;
  do not create another one or request microphone access on render.
- Authoritative source inspection includes SampleSurface's actual JSX,
  SampleControls Reset dialog, PadColourControls, App's Slice admission and
  the shared 32-face/44-target rules. The same sites visibly contain the
  already-delivered Replace/Record/Reset/colour handlers, so absence of the new
  grouping is not inferred from a name search.
- Fresh high-fidelity Figma context plus screenshots were read for file
  `GPFarNiZNsjLQzfG9kR8DO`, roots `403:784` and `407:6847`, then scoped touch
  children `403:1111` and `407:7174`. The touch children contain no static
  image/SVG assets. The screenshots are visual targets, never implementation
  assets. Existing physical/logo/Pad regions remain outside this Task.

All ten tracked symlinks are real links. Root is the sole writer. The separate
unpublished #2236 worktree retains its four diagnostic edits and evidence;
its Native-metronome decision is pending and no audio process is live. This
UI Task needs no answer to that decision. Shared App and metronome-spec edits
are serialized by this same writer, then rebased as necessary before shipping.

## Declared files

1. This plan.
2. `apps/creator-web/src/components/sample_surface.tsx`.
3. `apps/creator-web/src/components/sample_controls.tsx`.
4. `apps/creator-web/src/components/pad_colour_controls.tsx`.
5. `apps/creator-web/src/components/sample_pad_layout.css` (new).
6. `apps/creator-web/src/app.tsx` (existing Slice/colour composition only).
7. `apps/creator-web/test/pad_colour.test.tsx`.
8. `apps/creator-web/test/workspace_shell.test.tsx`.
9. `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`.
10. `tests/platform/web/creator/fixtures/creator_navigation.mjs` (existing Slice
    journey enters its actual Pad page before choosing Slice).
11. `tests/platform/web/creator/creator_web_metronome.spec.mjs` (preserve the
    original six-page COUNT-IN journey's actual Slice navigation).
12. `apps/docs-site/docs/hosts/creator-web.mdx`.
13. `apps/docs-site/docs/hosts/creator-interactions.mdx`.
14. `tests/platform/web/creator/creator_web_soundset.spec.mjs` (its existing
    independent five-colour oracle checks the actual new filled face instead
    of the former unselected label colour; preserve every index/history leg).

No Core, Facade, SDK, persistence/Contract, Provider, CI, manifest or identity
change. A further file requires an evidence-backed amendment before editing.

## Implementation

Reuse the existing colour component as a composition boundary: palette first,
then supplied Pad actions, then its original category-default action. Do not
duplicate the effective colour calculation, its index, writer or callbacks.
Keep visual and DOM/focus order aligned; do not rearrange interactive controls
using CSS order or move buttons into a second portal.

Pad actions use native scoped CSS/tokens: Replace/Record in a two-column row,
Slice/Reset in a second row, Delete as a full-width danger action, category
restore and technical details afterwards. Move the existing admitted Slice
navigation into that row; retain its actual disabled predicate and existing
mode transition. Keep Reset's exact confirmation/consequences/focus return,
Delete's preserved Pattern events and refused/pending cancellation outcomes,
Replace's final-Commit semantics and Record's confirmation-before-permission.
Existing accessible operation names and actual Pad address remain stable.

The default non-Pad empty view gets a native base-colour card naming the real
selected target, primary Add and secondary Record, and honest first microphone
permission/held-Pad guidance. Reuse the exact existing file/capture callbacks
and all current admission predicates. No selection means no invented target.
Retain the Pad-page cleanup operations for in-flight/failed imports even when
there is no assigned sound. Assigned-but-unavailable is not an Empty Pad;
preserve existing error/retry reporting rather than hiding it in this layout.

Ordinary actions retain a 32-unit visible face and at least44 CSS-pixel actual
hit area under the approved small-screen layout. Reuse the existing shared
touch primitive, focus/selected/disabled/danger tokens and five palette values.
Long labels wrap/grow; the one touch workspace scrolls vertically. No clipped,
overlapping hit targets, horizontal scroll or hidden EQ/owner/recovery branches.

## Verification

Before product edits: locked offline Creator install, complete original
`sample_controls`, `pad_colour`, `sample_assignment`, `workspace_shell` component
files and TypeScript. Read every terminal exit. New App regressions use actual
bindings/DOM focus order and target changes, not a fake copy of the layout.

Required far sides:

| Journey | Required observation |
| --- | --- |
| Assigned Pad -> Pad page | Actual palette/default identity and grouped actions, one Slice entry, correct disabled/focus order, full details retained |
| Reset cancel/confirm | Cancel no command; actual original defaults/full range/Mute semantics, Truth/Undo and reopen retained |
| Delete | Original Pattern events retained; correct current Pad; in-flight/unknown and retry/recovery paths retained |
| Replace -> cancel/commit | No Truth change on cancel, one final change on Commit, original Asset/Undo/reopen identities |
| Empty target -> Add/Record | Real selected target, existing file chooser/capture owner and permission timing, cancellation and save/reopen far sides |
| Colour override/default | All existing stable indices, category/custom/default readbacks and complete persistence/Undo journey |
| Slice and global COUNT-IN | Existing Slice capability/admission and candidate flow; all original six pages and both physical cancellation keys still reached |
| Six viewports | Wide,1280x600,768x600,portrait/tablet and phone: measured non-overlapping44px targets,32-unit faces, focus/labels/danger, one scroll layer and no horizontal overflow; retain PNG/JSON |

After implementation: owning complete component files, TypeScript and actual
official pinned build/clean package. Run the complete original Sample-editor
browser spec, existing candidate/Slice journeys and affected complete COUNT-IN
page journey without shrinking original budgets or assertions. Keep all PCM,
Truth, Artifact digest/length, save/Undo/reopen and failure/recovery legs. The
full Creator lane is required only if the final change's affected consumers
cannot be bounded by those owning selections; selected checks are never called
full-candidate proof.

Run the complete original three-case Sound Set spec too: the colour selector
now paints five filled faces from the unchanged palette. Its independent
approved RGB oracle must check those visible faces and the selected outline,
not a hidden label; every original actual index, retained category, installation,
history, Undo/Redo and reopen leg remains.

Run the complete Portal check for changed current source facts, staged and
committed new-path ownership, PR body/declaration validation, exact declared
staging/diff check and final committed files/status readback. Formal packaging
still requires clean Git; an unpublished source freeze is not push/PR or Task
completion until the unchanged owning checks pass. Preserve all negative and
interrupted evidence. No physical touch/hearing acceptance inferred.

## Version Management

Creator Host compatible feature MINOR debt, deduplicated with existing same-domain
debt in #2237. Preserve every existing Platform/Facade MINOR and Audio Runtime
ABI MAJOR source. No manifest, Product/Assembly/Build identity, snapshot, tag or
Channel allocation; internal React composition is not a new public SDK API.

## Documentation Impact

Documentation impact: required
Reason: current Sample Pad action hierarchy, Empty Pad entry and Slice route change
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/

The console's components, data sources and architecture edges are unchanged;
current page facts change with implementation. Existing Diagram output assets
are not manually redrawn or copied.

## Execution receipts

Fresh locked offline Creator install passed, terminal0. Baseline component and
TypeScript verification passed before product edits: four complete files,
280/280 tests,85.03s, both terminal0. The new empty-entry assertion fails on
the unchanged product with the missing target card, terminal1; its original
Pad-page Capture/close legs are retained. Fresh high-fidelity
Figma child code/screenshots are retained at `/tmp/lmdj-2226-figma-context/`.

The first complete four-file rerun retained277 PASS /4 FAIL: three original
fixtures still accessed Slice's old global navigation rather than its actual
Pad page; the standalone Reset size test read a raw CSS variable after adding
a redundant shared-control class. The fixtures now enter the real new page,
retaining the exact disabled/fallback/Truth assertions and Recovery precedence.
Reset keeps its original class; the actual Host already applies the shared
32/44 primitive to every action. The unchanged strict44px assertion passes.

Final owning component rerun: **281/281 PASS**, TypeScript terminal0. Broadened
full Creator Vitest after the App composition/route change: **84 files /
1988 tests PASS**, terminal0,91.80s. Official pinned Emscripten6.0.5 Creator
build passed, terminal0. Complete Portal passed, terminal0:179 tests,52 pages,
10 diagram sources/20 outputs, production build and50 routes/internal links.
Fresh precommit main is unchanged at the declared1581f3bd revision.

Six new real-browser journeys are written, not yet executed: assigned action
rows/actual face RGB/44px edge hits/32-unit faces/Tab order/details; actual
silent Pad navigation to A02; file-picker cancellation; same Capture dialog
without premature microphone permission, close/focus restoration; complete
Truth and Project file SHA/length inventory before and after cold reopen.
All browser source syntax and whitespace checks pass. No full browser/device
or shipping claim follows from this unpublished clean-source freeze.

First six-viewport execution at the unpublished9a7c88a7 package exited1:
six FAIL, all original JSON/trace retained. Four normal/rotated cases measured
valid44px bounds but the rounded hit box excluded all four1px-inset corners.
The phone's five fixed columns shrank a colour target to38.796875px. The
844x390 landscape additionally exposed the pre-existing shared console scale
of0.619565... (the44-unit target became27.260864px). No assertion, viewport,
threshold or journey leg is dropped. Keep rounded32-unit painted faces, reserve
rectangular hit boxes and wrap the unchanged five swatches when needed.

The shared landscape fitter was isolated as a separate prerequisite under
#2112: a compact544px-tall console was scaled when the stage was shorter.
Draft #2420 reflows that shared shell under the existing approved D0 adaptation.
Its24 component tests/types/pinned build+clean package, complete14 browser
layout journeys and full Portal passed, including actual44px targets and real
glyph collision RED/GREEN. All28 published PRs remain one OPEN Draft stack.
This unpublished Pad Task now follows it; no consumer-only compensation leaves
the physical keys below44px. This Task remains unpublished/incomplete.

Six failed traces/JSON have immutable readback at
`/Users/endaye/.codex/task-evidence/lmdj-2226/geometry-v1-20261020T074110Z/`,
manifest SHA256 `45fcd225e31c62dd4ba0c9159fa07bcf090db271f147958a8a8a6551ce6ec092`.
The owned artifact server ended143 after tests; that intentional termination is
not a product-test PASS. The new local CSS correction has not been packaged or
retested yet and must not be pushed as completed work.

Restack9a7c88a7 onto3c67eea8 produced unpublished0704136f. `git range-diff`
proves the Pad implementation patch unchanged. Both owned uncommitted files
were copied, hashed and saved as one binary patch, then restored byte-for-byte
after the clean rebase; no unrelated stash/reset or cleanup. Receipt and exact
original bytes are in
`/Users/endaye/.codex/task-evidence/lmdj-2226/restack-20261020T082920Z/`.
The first wrapper stopped on an incorrect expected range-diff delimiter after
the rebase/restore had succeeded; authoritative readback confirmed the exact
patch and new parent, and only the receipt was corrected. Rebuild and repeat
all six original failed journeys plus the original declared browser selections;
the shared producer's pass is not a Pad acceptance receipt.

Restacked source plus the two owned corrections passed completeCreator UI
84 files/1988 tests (107.59s), TypeScript, pinned Wasm/UI build and full Portal
179 tests/52 pages/10 diagram sources/20 outputs/50 routes. The next unpublished
checkpoint includes only those same declared CSS/plan changes so the official
clean package can exercise the original six failures. All original browser
legs, viewports, deadlines and pointer/Truth/file-identity assertions remain.

Rebuilt clean checkpointf3043e01 again failed all six original journeys
(terminal1, `u05c-restack-geometry-v2`). The first five palette targets now
pass the unchanged rectangle/edge tests in ordinary/phone/rotated cases;
execution advances to Replace, where the shared Host selector's `:not()`
specificity still wins the local radius declaration. In844x390 all sizes are
now valid but the sticky Sample tab row covers the first scrolled swatch.
Increase the existing scoped selector to include its real console ancestor;
only the painted face stays rounded. In the bounded shared short-landscape
profile let Sample tabs scroll with content, preserving every tab and handler.
Add actual hit-owner/radius/panel receipts without relaxing any assertion.
These changes stay in the existing declared local CSS/browser/Portal files;
no new capture owner or global stylesheet/fit algorithm change. Both full six
failure sets remain evidence and all six journeys must be replayed unchanged.

After the priority/tab-scroll correction, all four original owning component
files pass in full (262 across sample_controls/pad_colour/workspace_shell,
then19 sample_assignment; all four actual file paths checked). TypeScript,
pinned build and full Portal pass. The prior restacked84-file1988 UI pass
remains its own source receipt; no broader rerun is implied. Only CSS, browser
diagnostic fields and already-declared plan/Portal text changed since it.
Freeze these corrections locally for the original six packaged journeys;
do not push or claim completion before they and every declared old selection
have passed. No deadline, input point or acceptance leg is reduced.

Checkpoint522942bd replayed all six, again terminal1: all five swatches pass
now in every viewport, including844x390, proving the tab overlap corrected.
Replace still reports computed radius6px with actual DIV owners at the missed
corners. A separate read-only real-browser CSSOM probe confirms both scoped
and shared rules match: the shared `:not(.waveform-editor [role=slider])`
contributes two specificity units, so the four-unit local rule ties and loses
to the later Host rule. Bind the local rule to its actual Touch-workspace
ancestor as well (five units), retaining the same0px target/6px painted face.
No `!important`, token override, DOM mutation or relaxed corner test is used.
The complete v3 failure traces, per-point owners and CSSOM receipt remain at
`/Users/endaye/.codex/task-evidence/lmdj-2226/geometry-v3-20261020T084904Z/`,
manifest SHA256 `e7baf4e77f19f9dca74f51f85d6597cb85b6d533e0ea1c9894cdafba55390aa3`.
All original browser selections remain required.

Checkpoint5de5926e now passes all12 assigned-control rectangles, visible-face
heights, all five corner/centre hit owners and complete overflow assertions
at every viewport. All six advance to the action-row oracle, which correctly
rejects Slice/Reset: inherited `.hardware-workspace .reset-sample` pins Reset
to column1 after auto-placed Slice, producing two rows. Clear that placement
only inside this new Pad edit row, preserving the original Reset handler,
native order and original rule everywhere else. Persist actual row boxes
before the unchanged equality/non-overlap assertions. The v4 terminal1 and
complete six traces remain retained; every later journey leg still must run.

Checkpoint9891adbd passes all original six complete journeys (22.8s), then
the original complete Sample selection32 PASS/1 original WebKit-only skip
(5.5m), actual Capture trim/Commit plus exact-byte cold reopen2 PASS,
denied-permission1 PASS and complete candidate/Slice9 PASS. Full SoundSet
retains2 PASS/1 genuine FAIL: its original category/override/install/reopen/
restore journey reads selected BASS grey41/45/41 instead of approved221/244/120.
The nested Host pressed rule overrides the four-unit local palette variables,
the same CSSOM-confirmed selector-list specificity mechanism. Scope all three
existing palette rules through the real console/Touch-workspace ancestors,
keeping every stable index, RGB and white-selection assertion unchanged.
COUNT-IN did not run after the failure and remains explicitly unverified.
Retain the combined terminal/trace evidence and rerun the owning selections
on the corrected clean package before publishing this Task.

Palette correction pre-freeze: all four complete owning component files281
PASS, TypeScript terminal0, pinned Wasm/UI build terminal0 and full Portal
179/52 pages/10 sources20 outputs/50 routes terminal0. No JSX, handlers,
indices, Truth or test oracle changed; only the three scoped CSS selectors
and this evidence ledger differ from9891adbd. Retain that source's successful
functional journeys and failed selected-colour proof as separate receipts;
the corrected formal package still must pass the original owning selections.
