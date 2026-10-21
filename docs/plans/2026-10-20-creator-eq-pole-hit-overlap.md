# Creator EQ pole hit collisions (#1667 / #2112)

## Task and authority

One corrective Task on isolated `fix/creator-eq-pole-hit-overlap`, parent
Draft #2423 / `ce6b5e94e0a347e49a1a308352a7b387aaded3f6`.
Initial main: `1581f3bd42616d36637b1d3131747bb51dee5f8e`.
Root alone owns the shared Sample files. Commit/push and a Draft child on the
same stack are authorized. The 2026-10-20 owner notice permits ordinary
feature/fix/test integration after Task verification and exact-head review,
while workflow/release-tool/release-evidence paths remain frozen. This child
stays Draft behind the unintegrated parent stack. No release/tag, deployment,
Channel or Git cleanup. No subagents.

Resumption main: `8126d401bae8681caca98af32594458edc4be9ba`.
#2373 has actually merged as `8c1ee714`; later release publication/promotion
does not deliver an EQ successor. Main still has the original EqEditor and
band ranges. The parent #2423 remains OPEN Draft at ce6b5e94 with this finding
explicitly open; #1667 likewise retains the strict negative. No competing EQ
implementation is presumed from release changes. C4's original COUNT-IN
journeys remain pending behind #2394/#2395 and the explicit #2396 withdrawal;
this correction neither restores that UI nor removes those acceptance legs.

Baseline receipts from the unchanged parent are retained: all 85 owning
component tests and TypeScript pass; the restored unconditional six-viewport
browser oracle against the actual ce6b5e94 package exits1 (5 PASS/1 FAIL),
at the phone Mid edge owned by High. Its 26-file manifest is
`378f4e7047aaa36b549d8339fb5e1603e801986e50611ded4df8b8f07cdf2f68`.

## Refreshed premise and correction

The approved `docs/prd/decisions/2026-10-13-creator-interaction-ui-baseline.md`
requires44px actual targets without clipping, neighbour misactivation or using
overlap to fit the layout. It permits adaptive geometry without renewed owner
approval and preserves every operation. This is the binding positive authority.

#2423 already delivers the responsive132px graph,12px dots, response curve,
correct SVG screen mapping and original typed gesture/data semantics. Reuse
all of it. Its follow-up oracle incorrectly accepted a later High ellipse
intercepting Mid's right-edge hit at390px (Mid1840Hz/+3.9dB, High8000Hz).
The parent negative capsule actually records that wrong owner:
`/Users/endaye/.codex/task-evidence/lmdj-1667/tone-v3-20261020T104055Z`,
manifest `a15d84979204bed2b81dce26aa1d64a21884b06f3646743ae151ce90c680d5ac`.
The then-adopted DOM-order exception contradicts the approved policy; it is not
an owner waiver. Restore unconditional centre/four-edge ownership checks,
retain44px, all data comparisons, all six viewports and every existing leg.

Current main has the original three controls and unrestricted valid band
ranges, so restricting values, removing a band, shrinking hits, changing the
selected band or adding an extra selection step is not a fix. #2229 was only
read/audited; its source remains untouched while this real regression is fixed.

Fresh high-fidelity Figma403:738 context and screenshot were inspected. The
Three-band-EQ prototype represents interactive data; retain the existing real
graph, tokens and handlers, no static SVG substitute, asset URL or dependency.

## Declared files

1. This plan.
2. `apps/creator-web/src/components/eq_editor.tsx`.
3. `apps/creator-web/src/components/eq_handle_layout.ts` (new pure geometry).
4. `apps/creator-web/src/components/sample_tone_layout.css`.
5. `apps/creator-web/test/eq_editor.test.tsx`.
6. `apps/creator-web/test/eq_handle_layout.test.ts` (new).
7. `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`.
8. `apps/docs-site/docs/hosts/creator-web.mdx`.
9. `apps/docs-site/docs/hosts/creator-interactions.mdx`.
10. `docs/plans/2026-10-20-creator-tone-eq-layout.md` (correct the prior package-source audit claim).

No App/global stylesheet/Core/SDK/Contract/manifest/lockfile/CI changes. Amend
this exact declaration before any additional tracked file.

## Implementation

Keep the response and true frequency/gain coordinates unchanged. Ordinary
separated handles remain at their data points. In a collision, only move the
12px draggable control marker enough to place its entire44px footprint inside
the plot and outside every other hit footprint. A subtle band-coloured leader
connects a displaced handle to its actual data point; do not falsely move the
response or frequency/gain/Q values to manufacture space. Keep DOM/focus order.

Compute placement in local CSS pixels, with a small positive gap between44px
footprints, then project into the existing viewBox. Deterministic candidate
positions and three-band ordering make layout reproducible. During a gesture,
prefer the active handle at its original display offset so it tracks pointer
travel; the original data-space grab offset still preserves exact deltas and
press-without-travel. Neighbours move aside, never receive the active gesture.
All cut/Q/keyboard/preview/commit-once/Escape/pointercancel/suspend/unmount rules
remain. No data/persistence fields, new selector or alternate gesture model.

Use 46px centre separation for non-overlapping 44px footprints and a small
outward-rounding margin. Search the bounded three-handle candidates, retaining
an unchanged first handle when feasible and preferring the active pointer's
display offset. Contain edge markers in the SVG; leaders are separate from
interactive groups. Below the width for two columns, allow only the graph's
minimum height to grow enough for three targets; the six supported layouts
retain the Figma132px graph. Never change frequency/gain to fit controls.

## Verification

Before product edits, run the original complete owning component files and
TypeScript, then all six restored strict browser journeys against the actual
parent official package. The narrow edited Mid hit must fail for the real
wrong owner, not imports or startup. Retain full trace/measurements.

Independent geometry properties assert actual44px containment and pairwise
non-overlap for ordinary, near, coincident and edge anchors in measured canvas
sizes, plus unchanged separated points and active-offset preservation.
Component tests prove displaced press/no travel, exact frequency/gain deltas,
Q, cancel and real response coordinates. Real browser journeys require all five
samples to belong to their own band, including the original phone collision,
resize, rotation and cold reopen, with full Truth/file SHA256/length assertions.
Add actual permitted coincident/edge band cases without reducing ranges or
skipping original journeys.

Run complete owning files, TypeScript, complete Creator UI at final source,
pinned official configure/build/package, the complete original Sample browser
selection plus the unchanged recorded-Master Tone PCM owner. Full Portal is
required for current source facts. Stage-only declared files, diff/ownership,
committed-range classification and PR body/declaration checks before push.
Clean source/head and exact distribution hashes bind packaging/browser evidence.
Both full proof and standalone package enforce clean Git: the actual
`apps/creator-web/tools/package.py` calls `require_clean_source` before writing
distribution files. The prior contrary audit note was wrong and is corrected
in the parent plan. The manifest still does not embed Git HEAD, so retain the
external source and complete distribution hashes/lengths as well.

No new universal full13 gate. Independent review, final integrated candidate,
35screens, real devices/hearing and original budgets remain separate. Preserve
all earlier negatives and correct the current Issue/Portal claims; do not
rewrite historical comments or claim #1667/#2112 fully complete.

## Version Management

Creator Host compatible PATCH debt for correcting the promised hit geometry,
absorbed by existing same-domain MINOR/higher debt in #2237. No new identity,
Core/Contract/ABI/persistence impact or Product/Assembly/Build/snapshot allocation.

## Documentation Impact

Documentation impact: required
Reason: correct the prior overlapping-hit exception and describe truthful handle displacement.
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/

No new source-diagram edges. Independent current-head review stays PENDING.

## Source checkpoint verification (2026-10-20)

The resumed original owning selection passes85 tests and TypeScript. The new
pure three-target geometry properties plus displaced press/travel/Q/Escape
cases bring that complete selection to103 PASS. Full Creator UI passes2018
tests across86 files (99.01s), with the existing CSS-parser/localStorage
warnings retained; TypeScript passes. One intermediate sample-controls test
correctly caught a new inline minimum overriding its old container. Move the
new variables into the scoped Tone stylesheet; keep the original test and the
old unscoped320px minimum unchanged. All103 then pass.

Official Emscripten6.0.5 configure/build and complete Portal check pass:
179 tests,52 pages,10 source diagrams/20 outputs and50 routes/links. The actual
standalone package exits2 on this dirty tree, explicitly requiring clean Git;
this is preserved evidence, not a package PASS. A local unpublished source
checkpoint is needed before the real package/browser verification. Do not
push, open a child PR or call the Task complete until those checks pass.

Two added real coincident/edge journeys against the unchanged parent package
both exit1 at Low's actual five hit samples (390x844 and768x1024), after actual
import, legal parameter setup and App reopen succeed. The13-file negative
capsule manifest is
`9eb72850ea2b2e2431c69df036f05d542bfbd95462f1c85e2480738b354c6cc6`.
The original six complete journeys, all five strict hit samples, actual132px
height, full44px containment/non-overlap, history and exact cold-reopen files
remain. All positive packaged journeys and unchanged Master Tone PCM are
still pending at this local source checkpoint.

## Complete packaged receipt

Clean tested source: `e85b6b4e59af0fda47e35f164e8923a82391e291`.
Official configure/build/package each exit0 from that clean HEAD. The owned
runner verifies the complete ten-file distribution, all ten declared source
files and three fixtures by SHA256/byte length before and after each run,
plus the actual server PID/nonce and unchanged clean HEAD.

- Eight complete geometry journeys PASS (1.5m): all original six viewports,
  plus actual coincident/edge states on phone and rotated tablet. Every target
  keeps five unconditional own-band samples; complete footprints remain inside
  the plot and pairwise disjoint. The graph stays132px at those sizes. Preview,
  Escape, no-travel press, original drag/Q/Cut/bypass, commit-once, full Undo/
  Redo, resize and cold-reopen Truth/files are retained.
- Complete original Sample selection exits0:40 PASS/1 existing WebKit-only
  skip (6.9m), including those eight cases and every original import/recovery/
  ASSIGN/history/Pad/Playback/Trim journey. The repeated geometry pass is not
  counted as additional delivered features.
- Original recorded-Master Tone PCM owner exits0:1 PASS (14.0s). All three
  invocations observe MacBook Pro Speakers through the normal wrapper; this
  is actual browser/Native PCM evidence, not physical listening or Safari/iPad.
- Staged and committed ownership each pass77 tests. Parent-relative scope is
  focused: creator/docs_static/portal; it is selection, not execution of full13.
  Body lint and Portal impact declaration pass before publication.

The355-file immutable capsule at
`/Users/endaye/.codex/task-evidence/lmdj-eq-hit/verified-20261020T123853Z`
has manifest SHA256
`c4409a696fbaeaa472e890afbe7834acec070f62ce0d60be51427cf1e3c5cb01`.
It retains package/source/fixtures, screenshots, complete run receipts and all
negative diagnostics. The tested Git object is retained at
`refs/codex-evidence/creator-eq-hit-tested-e85b6b4e`. Both owned servers and
all browser invocations are terminal; no branch/worktree cleanup is performed.

Finalization changes only this plan's receipt text. Regenerate the official
package from the resulting clean head and require its entire ten-file path,
SHA256 and byte-length inventory to equal the tested package; report the
actual comparison before push. Behavior, tests and Portal bytes stay unchanged.
Independent review, parent correction integration, full candidate/35screens,
real devices/hearing and original budgets remain unverified. The parent at
ce6b5e94 still contains the defect until this correction is included in its
reviewed main-target head. #1667/#2112 stay OPEN.
