# Creator touch refinement — #1917–#1926

## Goal and scope

Owner authorized the ten issues, one bounded Task at a time, through commit,
push, current-head review and guarded squash merge. No release, deployment or
cleanup. #1207 comment 6083817700 is the issue index. #1665, #1670, #1822,
#1214, #1221 and #1911 are coordination/dependency sources, not additional
whole-issue delivery obligations. Device acceptance remains separately recorded.

## Current premises (2026-10-09)

Integration and Task base: `50d79fa894f3483d6593d50fafcfd3e1bff28ce0`.
All ten issues are open with no implementation comments. Creator source is
unchanged from the finding's `502932e345b621abc5533431e61adf0d0253a189`.
Open #1913 owns MPC Pad ordering; #1910 owns monitor-output producer work.
Their unmerged changes are neither missing work to duplicate nor delivery on
main. The latter carries a newer proposed/owner-recorded encoder decision;
re-read it and its authority before the later encoder/visual Task.

| Issue | Disposition and order |
| --- | --- |
| #1917 | First: fixed-panel fit and SETUP crowding remain; implement below. |
| #1918 / #1919 | Next: Sample and Perform contextual pages; preserve all existing actions. |
| #1922 / #1923 | Sequence bar navigation and Sound Set install steps, with distinct Pad semantics. |
| #1920 / #1921 | Mode-specific overview and draft feedback. |
| #1925 / #1924 | Status consolidation then shared visual treatment. |
| #1926 | Bounded local boot investigation; advance early if it prevents dynamic checks. |

Each later Task re-reads its issue, current source, successor PRs and decisions
before editing. Closed historical UI tasks do not prove current usability.

## Task #1917 — fixed touch-panel fit

Verified owning paths: `styles.css` defines 368×368 touch bounds, padding 16
and `overflow:auto`; the Sample layout switches only at a viewport media query.
The Sequence header combines nonwrapping PatternStepper and a fixed-width layer
selector. Swing actions have three markup children but a two-column override.
These are still outstanding. SequenceGrid has its own intentionally wide time
axis; it is an explicit editing exception until #1922, not an outer-panel fix.
Perform/Sound Sets and candidate lists inherit additional scroll containers.

Figma high-fidelity context `88:1512` and screenshot `88:706` were retrieved:
336-unit inner content, 8-unit rhythm, equal Tempo/Swing cards. Only layout fit
is in this Task; existing interactive sliders remain, with their visual
restyling and assets in #1924. Do not replace controls with screenshot assets.

Declared files:

- `apps/creator-web/src/styles.css`
- `tests/platform/web/creator/creator_web_touch_fit.spec.mjs`
- this plan

Use shrinkable grid tracks, panel-scoped form layouts and wrapping text,
with a single primary vertical touch scroller. Preserve independent waveform
and Sequence editing gestures. Keep Sequence navigation reachable while its
settings scroll. Do not clip overflowing actions or change four-region sizes.

Verification: existing hardware-console component baseline, TypeScript/Vite
build, and new real-browser geometry regressions for SETUP, Swing and Sample
empty/assigned/error-recovery states across wide and short viewports, plus
Perform and Sound Sets outer scrolling. Check reachable controls,
new-Pattern cancel, long text and contained editor exceptions. Red/green on
the local source development UI is distinct from subsequent committed-head
packaged Creator lane evidence. The development UI uses the unchanged packaged
Runtime assets; it is not a release artifact. New-file ownership runs after
staging. Full selected batch-only evidence and exact-head review precede merge.

The geometry tests do not prove physical touch or audio quality. Those rows
remain in #248/#365/#721/#1854 and the #1221 acceptance follow-up; no issue is
closed on the basis of an unexecuted acceptance row.

## Version Management

Version impact: none for this internal layout repair; no public Host API,
Project format, Package publication or Product Build allocation. Reassess
PATCH/MINOR for later navigation/features using the then-current manifests.

## Documentation Impact

Documentation impact: none for #1917. Existing four-region geometry,
available actions, navigation and source-of-truth contracts remain the same;
this corrects overflow within their documented bounds. Later page/navigation
tasks update `/hosts/creator-web/` and applicable usage documentation.

## Pitfall Impact

Pitfall impact: none — these layout defects are expressible by rendered
geometry and control reachability assertions, not new governance rules.

## Task #1917 verification record (2026-10-10)

Premises refreshed before commit: origin/main remains
`50d79fa894f3483d6593d50fafcfd3e1bff28ce0`; no successor landed.

- Fresh locked installs in the owned Task and baseline worktrees completed.
- `npm --prefix apps/creator-web test -- run test/hardware_console.test.tsx
  test/sequence_surface.test.tsx test/sequence_pattern_structure.test.tsx`:
  35 passed.
- `npm --prefix apps/creator-web run build`: passed after final CSS edits.
- Chromium `creator_web_touch_fit.spec.mjs`: 5 passed against the source UI
  with the owned baseline's verified Runtime assets and actual manifest metadata.
  No manifest verifier or Runtime gate was disabled. This is development UI
  evidence, not a packaged-head or release claim.
- Discriminating baseline: the four initial geometry tests against the clean
  packaged base all failed at the intended assertions: offscreen layer header,
  Swing row misalignment (63.79 rendered pixels), unbroken title overflow
  (1438 layout pixels), assigned Sample overflow (44 layout pixels).
  Perform additionally measured scrollWidth 564 vs clientWidth 353 before its
  implicit grid track was constrained, and 353 vs 353 after.
- Invalid audio selection displayed the real ingest error; selecting the valid
  WAV, committing its Long Source selection, and observing the assigned Pad
  and cleared alert proved the recovery leg. New Pattern cancellation returns
  to reachable EDIT/SETUP navigation. Disabled empty-Pad actions remain visible.
- The long-title case substitutes text only to stress geometry; it does not
  claim Pattern renaming or persistence. Source UI screenshots were inspected.
- A supplemental WebKit attempt reached `unsupported` before opening a Project;
  it provides no WebKit layout acceptance. The repository's existing WebKit
  capability-boundary lane remains mandatory, and physical Safari remains open.
- Earlier attempts against a removed old distribution (HTTP 404), unconfigured
  Vite manifest, and an incomplete import fixture are retained as harness
  failures, not product regression evidence. The corrected run owns its server.

Committed-head packaging, full selected batch-only lanes, independent review,
and merge remain required. Logs and screenshots for this Task are retained in
`/tmp/lmdj-ui-goal-20261009/`; packaged evidence will be recorded in its PR.
