# Preserve actual control size on short landscape stages

## Task and authority

Corrective prerequisite under #2112, found by #2226's six-viewport acceptance.
Isolated `fix/creator-short-landscape-controls`, parent Draft #2419 /
`27483b1f3df80d6dcd74b33c9e0efc6639c9f1e2`. Fresh integration base remains
`1581f3bd42616d36637b1d3131747bb51dee5f8e`. Main is frozen. Complete Task
verification, commit/push and a Draft stack child are authorized; no merge,
auto-merge, release/tag, deployment, Channel promotion or Git cleanup.

Root owns this five-file prerequisite. The unpublished Pad Task9a7c88a7 and
its two local CSS/plan corrections remain preserved in their own worktree;
they will follow this producer in the same linear stack. #2236's unrelated
Native-metronome decision remains pending; no dependent audio change starts.

## Premise audit before edits

- Already delivered: full880x592 shell, regular compact752x544 and portrait
  stack, native relative encoder/keys, one4x4 MPC Pad matrix, read-only overview,
  one vertical touch-workspace scroller and real resize/rAF fitting. Reuse them.
- Still outstanding: the viewport selector correctly chooses compact at
  844x390, but its544px console plus chrome still does not fit. `fitStage()`
  measures it and scales the entire workspace to0.619565..., turning44 units
  into27.260864 CSS pixels. Changing the Sample consumer alone leaves the
  physical keys equally small. Existing narrow rules only handle portrait.
- Actual rebuilt9a7c88a7 evidence: all six new Pad journeys failed, with full
  JSON/trace retained. The short-landscape receipt records a DRUMS target of
  37.667633x27.260864px. Its inherited `styles.css` is
  byte-identical to this Task's #2419 parent. The Pad-only stylesheet does not
  control the shared stage or physical keys, so this is a separate producer gap.
- Authority is already approved: `2026-10-13-creator-interaction-ui-baseline`
  explicitly permits smaller-screen reflow and implementation-chosen dimensions
  while preserving all operations, native focus order,32-unit faces and44px
  actual targets. This does not reopen a product-level decision.

No JavaScript handler, stage-fit algorithm, parameter/capture owner, sound,
public API, Project Truth or stored layout preference changes. Source facts
and existing real geometry distinguish this gap from a status/title match.

## Declared files

1. This plan.
2. `apps/creator-web/src/styles.css` (one bounded short-landscape profile).
3. `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`.
4. `apps/docs-site/docs/hosts/creator-web.mdx`.
5. `apps/docs-site/docs/platform/input.mdx`.

No new asset, SVG replacement, React component, SDK/Core/Contract, manifest,
Product/Assembly/Build/snapshot or CI/workflow change. A further file requires
an evidence-backed amendment before editing.

## Layout and invariants

Use a compact short-landscape profile for width>=648px and
364px<=height<600px. These are geometry bounds, not tuned passing thresholds:
48px existing compact System mark +8px gap +188px four-encoder row +8px gap
+380px eight-column key row =632px; two8px horizontal margins require648px.
The two44px key rows take88px (zero inter-row target gap; faces remain32px).
The existing SHIFT spans two cells, so its DOM order and92px target persist.

Keep the same four regions, reflowing their existing DOM only:

- A632x88 physical strip across the top: the existing48px System mark,
  four44px encoders and two key rows. Mode/Bank keys occupy the first row;
  SHIFT then directions and Record/Play occupy the second. No key disappears.
- The4x4 Pad matrix is244x244 below it at y88. Four55px Pads plus three8px
  gaps preserve actual size and the existing9/13 labels. Use small text insets
  and put the selection dot in the bottom gutter so it cannot overlap a
  category; two-line transient captions remain below the address, without
  reducing fonts or dropping text.
- Read-only overview starts at x252/y88, retains its152px height and all
  fields; the touch workspace starts at x252/y248 and scrolls vertically.
- Header/footer are16px each, with readable native text. The console takes
  the remaining stage height without vertical margins. At the364px bound,
  its332px height leaves84px for the touch region:32px padding and at least
  one complete44px action. Wider/taller short viewports gain usable space.

Ordinary full/compact/portrait layouts outside the profile keep their original
dimensions, selection and fitting assertions. This improves a bounded range;
it does not claim every arbitrarily small viewport is newly verified. Source
minima are not implemented by hiding controls, truncating labels, overlap,
horizontal scroll or shrinking targets. The original no-below1 scale invariant
is asserted on the new actual browser layouts too.

## Verification

Before edits, retain the actual old packaged failure and hash-match its global
stylesheet with this parent. Add real short-stage geometry journeys that reject
the old scale; no fake transform or screenshot-as-implementation.

Use the existing `resizeViewport` helper, which observes real resize metrics
and a far-side rendering frame. At648x364,667x375 and844x390, verify:

- actual scale1, inside-stage console, no horizontal overflow;
- all four regions present and non-overlapping, one4x4 Pad matrix;
- every actual System/encoder/key/Pad target>=44px, native order,32px key faces;
- hit owners at centres and four mid-edges after scrolling, with no neighbouring
  control interception; long Pad labels and selection dot do not collide;
- real mode/Bank/System navigation uses the same handlers, focus and current Pad;
  resizing to the original regular compact/full/portrait cases preserves all
  original oracles and complete Project Truth.

Run the complete unchanged hardware-layout spec plus the new journeys on a
formal clean package; retain every original viewport and interaction leg. Run
the owning hardware-console component file and TypeScript, full Creator tests
if the final diff extends beyond CSS, complete Portal for changed source facts,
staged/committed ownership and exact-file/body/declaration checks. A local clean
source checkpoint needed by official package verification is unpublished until
the owning journeys pass. Full candidate/device/hearing remain separate.

Keep #2226's stricter six scoped hit/face/focus/Truth/reopen journeys intact;
they still rerun after restacking onto this correction. Their corner and
five-column defects remain owned by that Pad Task, not hidden by this profile.

## Version Management

Creator Host compatible PATCH debt, absorbed into existing same-domain MINOR
rollup in #2237. No public interface, persisted schema or ABI impact. Retain
every higher debt and allocate no Product/Assembly/Build/snapshot identity.

## Documentation Impact

Documentation impact: required
Reason: document the actual bounded short-landscape reflow and44px controls
Affected portal pages: /hosts/creator-web/ /platform/input/

The four-region source diagram remains the unmodified default880x592 model;
components and edges are unchanged. Document the responsive variant in current
pages, not by hand-editing frozen diagrams or snapshots.

## Evidence

Original U05c failures:
`/Users/endaye/.codex/task-evidence/lmdj-2226/geometry-v1-20261020T074110Z/`,
manifest SHA256 `45fcd225e31c62dd4ba0c9159fa07bcf090db271f147958a8a8a6551ce6ec092`.
No public PR or completion claim for this prerequisite yet.

Before the fix, the three new geometry journeys ran against an
immutable copy of the official9a7c88a7 package with the hash-matched parent
global stylesheet. All three failed on the actual stage-scale assertion:
648x364 scale0.572464 / encoder25.1884px;667x375 scale0.592391 /
26.0652px;844x390 scale0.619565 /27.2609px. Browser terminal1, original
traces/geometry retained under `short-landscape-red`; the owned server was
stopped and its terminal143 read. No test threshold or viewport changed.
The owning hardware component baseline24/24 and TypeScript passed before
product edits. Positive clean-package verification remains outstanding.

Pre-freeze24/24 hardware-console tests, TypeScript and the pinned6.0.5
Wasm/Creator build passed. The first build invocation correctly refused a
missing EMSDK setting; the corrected invocation used the existing pinned
toolchain explicitly, with no source or toolchain change. Full Portal passed
179 tests,52 current pages,10 diagram sources/20 outputs and50 built routes.
Precommit refresh still resolves main1581f3bd with no intervening successor.
The official fixture generator source matches9a7c88a7 byte-for-byte, so the
same reproducible Project/Sample fixtures may be reused with their full
SHA256/byte lengths verified before each run.

The next local commit is an unpublished clean-source checkpoint required by
official package verification. Browser acceptance and independent review
remain pending; a checkpoint is not a shipped or completed Task.

Checkpoint2cac23c5 passed all14 hardware-layout journeys (1.4m), including
all three new short viewports, old desktop/portrait and navigation/Truth/reopen
legs. Screenshot review then found ASSIGNED wrapping close to the address.
A stronger real-glyph collision assertion rejected that same rebuilt package
at all three short viewports (terminal1, `short-landscape-caption-red`). The
caption now gets its full width and lower inset; the selection dot occupies
the bottom gutter. Preserve both prior outcomes. The strengthened complete
selection remains required before any push or Draft PR.
