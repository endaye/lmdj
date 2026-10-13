# Creator Slice interaction layout — #2112 U10

## Premise refresh

Fresh integration/worktree base:
`50ecc7107a3347878e1d5aa7f72b031d7d58eb98`. Live #2112 and comments, the
open PR inventory, current Candidate surface/state/App owners and their tests
were inspected before editing. Slice is U10; U08 is Perform Slots/Takes/Replay.
U09 #2122, U11 #2121 and U03a #2119 were separately owned in-flight Tasks at
initial inspection. U09 actually merged as
`613e23c26bb0ae54dccd75003b8858ac484b0faf`; before shared-file edits, all four
owned dirty files were backed up with hashes and an explicit-path stash, the
branch rebased onto that merge, and restored bytes matched all four hashes.
The stash remains `bb0ec3ce8ff99a7e8d8e35bbdb35299758bb06b2`; receipts are in
`build/verification/u10/integration-613e`. No shared-file conflict occurred.

Already delivered: explicit Provider selection/permission merging, retained
Asset discovery, source-bound durable Job inspection, public-audio consent,
fresh Attempt analysis, active/empty/failed/cancelled/interrupted results,
audition/stop, blank explicit target rows, duplicate-Pad rejection, repeated
recipe adoption to distinct Pads, revision-bound single commands, uncertainty
across source changes, and Project/audio refresh after adoption. The existing
Candidate owner/state/Host journeys prove these contracts; do not recreate them.

Still outstanding: the compact Figma Slice touch layout and its layout/return
verification. High-fidelity context and screenshot were read via
`figma-design-to-code` for file `GPFarNiZNsjLQzfG9kR8DO`, frame `406:2154`,
touch workspace `406:2345`. The design is one combined workspace, not five
separate Source/Analyze/Candidates/Preview/Adopt pages. It provides no numeric
analysis-progress signal. Shared rail/Pad/overview assets are outside this
Task; the owned touch panel contains no static image assets.

## Declared files and ownership

1. `apps/creator-web/src/components/candidate_surface.tsx`
2. `apps/creator-web/src/components/candidate_surface.css` (new page CSS)
3. `apps/creator-web/src/app.tsx` (Slice Back callback/navigation only)
4. `apps/creator-web/test/candidate_surface.test.tsx`
5. `apps/creator-web/test/workspace_shell.test.tsx` (Slice return only)
6. `tests/platform/web/creator/creator_web_candidate.spec.mjs`
7. `apps/docs-site/docs/hosts/creator-web.mdx` (Slice section only)
8. `apps/docs-site/docs/hosts/creator-interactions.mdx` (section 7.2 only)
9. This plan.

Initial source preparation owned only files 1, 2, 4 and 9. After the actual U09
merge and verified byte-preserving integration, Root admitted App Slice Back,
shared workspace Slice-only assertions and both Portal Slice sections.
State helpers, Core, producer contracts, `styles.css`, ASSIGN, S6 and U03b's
upper-screen business summary are outside scope. No heavy Portal/build/browser
checks, checkpoint or shipping before Root admits the resource window.

## Design and real-data boundaries

Use existing tokens and native selects/buttons/checkbox semantics. Header names
SLICE and the actual selected source Asset's short identity; a presentation-only
counter reads the current active result. Source/provider rows precede a compact
permission/consent row and Analyze. Preserve all existing guards and callbacks.

Candidate cards show the actual slice ordinal, interval and frame information,
plus Preview. Targets remain a separate compact card group: every row still
requires Slice, Bank and Pad explicitly. This preserves one recipe to several
Pads; Figma's single candidate/B01 example cannot supply an implicit target.
Keep Stop accessible, Adopt after targets, Refresh/Back after Adopt, and Discard
last. Back changes the existing mode; Candidate teardown owns audition stop.

The Source projection has only Asset identity and generated Source N/short-ID
labels, including unassigned Assets. Do not claim the mockup's A03/Bass, four
candidates or waveform when no corresponding data exists. Counts come from
actual active recipes, including zero; unknown/loading remains unknown. Do not
invent percentages, persistent playing indicators, successful adoption or audio
readiness. Existing Host outcomes and actual Project refresh determine them.

Provider selection does not grant permission. Consent remains an unchecked
native checkbox, and changing source resets its own CandidateJob. Granting
analysis permission preserves other grants. Keep the existing public/local/test
policy explanation available. A failed or unknown adoption remains locked until
successful Project inspection; never retry it automatically.

## Verification and acceptance

Each new assertion targets a distinct layout or truth defect. First run the
new component assertions against the old source and retain RED output; then
implement and run the complete `candidate_surface.test.tsx` plus unchanged
`candidate_state.test.ts` (baseline 16 + 4 cases) and TypeScript. Cover real
counter/unknown/empty states, action hierarchy and explicit Back without a
hidden Analyze/Adopt. Preserve every existing refusal and lifetime assertion.

After shared-file admission, run the mounted App's existing Candidate publication
wait, failed prepare/retry, input isolation and late-unmount/history cases,
existing Slice entry, and new Back-to-Sample/stop/no-adoption case. Root controls
Portal section ownership and the heavy execution window.

Run whole Portal and scope/whitespace checks before the clean source checkpoint.
Normal packaging needs clean tracked source: checkpoint is local/unpublished,
not completion. Fresh normal build/package must use the final source head.
Run all 14 existing Chromium Candidate cases, without reducing deadlines/legs:

- UI full journey: preview not-played/played, stop, mode exit, reload and inspect
  without re-analysis, duplicate target refusal, one recipe adopted to two Pads,
  complete Artifact SHA/length/PCM/lineage/source/Pattern evidence, reload, discard.
- UI zero-onset and stale-revision/missing-source/discarded-set refusals, each
  preserving Truth/files through refresh and reopen.
- UI actual Worklet audio after adoption into occupied A1 and empty B1, and
  publication of the selected non-current Pattern.
- Unchanged runtime owner journeys: preview/adopt/restart, no-onset/restart,
  stale/discarded/superseded/corrupt refusal/restart.

Extend only the UI spec with three viewports (1440×900, 1280×600, 768×600),
0/multiple candidates, multiple explicit targets, long real source identity,
all reachable actions, no overlapping/horizontal/nested scrolling, actual
rendered rectangles and centre/edge hit checks. Save JSON and screenshots to
unique output directories. The Back leg reads real Truth/files before and
after, stop/adopt counters and the actual Sample mode; a cached projection is
not its oracle. U01 separately owns actual >=44 CSS px compliance after scaling;
record actual measurements and do not treat design-coordinate height as proof.

Every failure is retained. Fix only its cause, rerun affected checks and all
original owning journey legs against a fresh package, retaining one atomic
unpublished Task commit. Push/PR only after all Task checks pass; Root performs
current-head review/protection/guarded merge. Complete Creator, devices and
release/deployment remain separate acceptance.

## Documentation impact

Documentation impact: required. `/hosts/creator-web` Slice and
`/hosts/creator-interactions` section 7.2 describe the new hierarchy and existing
real-data/explicit-adoption limits in the same Task. Do not rewrite historical,
Sound Sets, System or overview sections owned elsewhere.

## Version Management

Version impact: none. Existing Host capabilities and persisted contracts remain
unchanged. No Product Build or component version is allocated; no release or
deployment is initiated.

## Evidence

Source preparation receipts live under ignored `build/verification/u10`.
Four new component assertions failed against the previous source, then all
20 Candidate surface cases plus four unchanged state cases passed. TypeScript
passed. The new mounted return assertion first failed at the old outer Back
button, which was not in the Slice footer. The App now delegates its existing
mode transition to the Candidate footer. A first mounted green attempt retained
seven passes and one test failure because the new test used the wrong existing
not-played message; that assertion was corrected to the unchanged source copy.

After integration, all 24 component/state cases passed again; eight mounted
cases passed (publication wait, failure/preparation retry, three input sources,
existing Slice/Sound Sets entry, late-unmount history and new footer return).
TypeScript, browser spec syntax and 77 scope-policy tests passed. Whitespace
checks passed. Logs retain both negative runs and the corrected passes.

The UI browser spec keeps all eight original cases and every original leg,
adding a Back/real inspection/complete persisted-byte/stop/counter leg and
rendered geometry/screenshots at three viewports for zero and three candidates,
including two explicit targets. The six runtime owner journeys are unchanged.
Whole Portal, normal build/package and all 14 browser cases remain UNRUN until
Root admits the heavy window. Actual rendered hit sizes and visual results are
therefore not yet known; U01 still owns scaled 44 CSS px compliance.

Root subsequently admitted the exclusive heavy window. Fresh remote main was
still `613e23c26bb0ae54dccd75003b8858ac484b0faf`; no intervening premise changed.
Whole Portal completed with exit 0: 177 tests and 50 routes/internal links passed.
The next commit is an unpublished clean-source checkpoint required by the
official packager, not completed Task verification or shipping authorization.
Normal build/package and all 14 browser cases must still pass before push/PR.

Checkpoint `cb676969b55c087b22eb7696ebc2de45fbfa5259` produced a fresh normal
Creator build/package (both exit 0; manifest SHA-256
`5b5b1f31fa51489478fa97a8f786af9853f9125df0a5879ce19ce52c3de4fe27`). The
dedicated recorded-Pattern/negative-PCM fixture was generated by this worktree's
fresh official dev `lmdj_core_cli` target and the tracked generator, then passed
bundle verification; no general empty-Pattern fixture or borrowed artifact was
substituted. Its source/binary/bundle hashes are in `fixture-identity.json`.

The first full browser run exited 1: 13 passed, one failed in 1.8 minutes. The
new third-preview leg incorrectly required `played: true` after an earlier
preview/stop. The actual Host returned `played: false`, and the UI accurately
displayed not-played; no page error was recorded. `publish_audition_pcm` may
refuse publication while its two audition slots drain, so running audio alone
does not guarantee this outcome (the response does not expose the precise
admission cause). The leg now waits for its distinct response and verifies the
UI against that actual boolean before Back; both original exact false/true
preview assertions and the original Stop/mode-exit legs remain unchanged.

Screenshot review also found the outer Provider/Source gaps were ineffective:
the previous base had no grid display on CandidateSurface. A new rendered gap
assertion failed against the freshly built checkpoint (`spacing-red-cb676969`),
then the owned CSS gained `display: grid` and `align-content: start`. The original
failure, trace, screenshots and both negative logs are retained. These fixes
require a fresh normal package and another complete 14-case run.

Root admitted one additional isolated fresh-session Back case: after the first
post-wake audition confirms `played: true`, Back must return to Sample, receive
an actual `candidate.audition.stop` response with `accepted: true`, then preserve
fresh Project inspection, complete OPFS bytes and adoption/analysis counts.
The existing Back leg also checks accepted stop before its far-side reads; its
false-played branch does not claim active audible preview. The final selection
is now all 14 original cases plus this new case (15 total), with unchanged
original assertions, request deadlines and no audition retry.

Checkpoint `ddae8961e4fe009d3dc2f04b5593e9411e7d4c67` passed a fresh normal
build/package and all 15 browser cases (exit 0, 1.5 minutes). The three-viewpoint
measurements contain 87 controls with all centre/four-inner-edge hits passing;
the minimum actual rendered height is 34.649993896484375 CSS px, explicitly
below U01's 44 CSS px requirement. Both zero-result and multi-candidate/target
screenshots were inspected. This pass includes the independent first-played
Back case and its accepted stop response before Truth/OPFS checks.

Final screenshot review found two page CSS tokens not yet defined on this
base: the checkbox radius now uses `--creator-control-radius` with the actual
Figma permission/Public-audio component's 6 px fallback, and Discard
uses the same rose fallback `#e5adc4` as PhysicalControls. Primary `.is-primary`
semantics are present; shared control face/accent/actual-44 compliance remains
U01's separate owner, as for U09. The final amended source is rebuilt normally
and all 15 cases rerun; final exact-head receipts live in ignored verification
evidence and the PR body to avoid changing the source revision to record itself.
No additional pitfall entry is warranted: the gaps and token fallback are direct
CSS causes covered by source/geometry review, and the audition outcome follows
the existing explicit Host contract.

## Current-head review: unavailable Slice return

Authenticated review `5500160275` on `537aada21e5ad9a51addbbba2089383b2d6715c9`
identified a missing Back in the Slice fallback. The actionable cause is a failed
Project projection read: Slice Refresh calls the existing App refresh journey,
whose failure clears the current Project and unmounts CandidateSurface without
changing the selected mode. Moving Back into that surface removed the old
touch return action in this state. PRJ and SMP remain enabled and can still
exit; this is not a reload-only trap. The production Runtime factory always
includes Candidate methods, so ordinary restart or Provider permission changes
do not demonstrate capability loss. A replacement Host session without those
optional methods is a separate supported fallback boundary.

Root admitted a finite repair in three existing declared paths only:
`app.tsx` (Slice fallback Back using the existing mode callback),
`workspace_shell.test.tsx` (the actual refresh-failure and RuntimeProvider
replacement journeys), and this plan. No mode-reset, reducer, Runtime, preview
lifetime, recording, or Sound Sets behavior changes are admitted. Existing
normal footer Back remains unique. These assertions catch the loss of a touch
return after either render prerequisite disappears, without bypassing the
capability/Project guards or silently retrying an authoring operation.

Before editing, the complete old nine-file source, diff, hashes and commit bundle
were retained under `build/verification/u10/review-fallback-repair`. Fresh main
is `0909a3015d8f19ee91dab415cd682822e9d3d3b5`, including Recovery #2142 and typed
Perform controls #2139. The old U10 commit was rebased onto that exact revision.
The only conflict was the Recovery insertion next to Slice navigation; both the
new Recovery location and U10 navigation were retained. Range-diff showed only
that context change. C1's existing Perform controller/Runtime wiring, source,
tests and complete browser legs stay unchanged; this repair only selects Sample
from Slice. The original Candidate browser file is byte-identical to `537aada`.

Prepare two mounted regressions: enter Slice, fail its next Project inspection
through Refresh, then return to Sample; and enter Slice, replace its session via
the actual host restart callback with a non-Candidate session, await retained
Project reopen, then return. Each must assert the fallback, usable PRJ/SMP keys,
the far-side Sample mode, disabled Slice reentry, unchanged authoritative fixture
Truth/revision, and no new analysis/adoption/trigger. Retired preview cleanup must
still occur. Preserve the normal footer test and all original owning cases.

Source preparation was admitted while S6 owned its Portal window. Root later
admitted the lowest-tier checks after the preceding light owner released. The
retained unfixed App was restored with a new mtime: both new tests reached their
intended fallback and failed exactly at the missing Back button (exit 1), after
their fault/restart and retirement assertions passed. No fixture correction or
retry was needed. Restoring the fixed App with a new mtime then passed all ten
mounted Candidate/Slice cases (the original eight plus both regressions), all
24 Candidate surface/state cases, TypeScript and browser-spec syntax, each with
exit 0. The existing jsdom stylesheet-parse warning remains recorded. Every run
retains its actual argv, times, exit, log digest, nine-file input hashes and empty
owned-process-group readback under `review-fallback-repair`.

The integrated normal build/package, Portal and all original fifteen browser
journeys remain UNRUN for this repair. Historical `537aada` passes do not describe
the repaired/integrated source. Root reviews the final packet before any
checkpoint, push, PR update or review reply; the separate heavy owner keeps its
window. No new product-version, deployment or device acceptance is claimed.

The final precommit main refresh found U06a #2123 at `97897f88` after the U09
base. Its Sequence Grid Tools component/tests and Sequence-only Portal sections
do not overlap Slice behavior, App wiring or these acceptance assertions.
The shared document diffs were inspected; no rebase or repeated implementation
is needed for this unrelated integration movement.

## Repaired integrated-source acceptance — 2026-10-13

Root admitted the queued exclusive heavy window after the prior owner released.
Before running, all nine files and the complete 69,187-byte patch matched the
independently reviewed fallback-repair packet (SHA256
`7abcadd5a9412bd949e6f0dbe121d14b2f74589d0348b7f2fc6ce1ed696c1760`).
Fresh published main was `0c873e6755fa5753f38ce4bf5267ea5cee00f080`; intervening
version/snapshot, Pad and Perform-type changes left the Slice App wiring,
Candidate source/state and both owning browser specs unchanged. The approved
integrated base remains `0909a3015d8f19ee91dab415cd682822e9d3d3b5`; no new
rebase or source expansion occurred.

- The retained lowest-tier results remain two discriminating missing-Back RED
  cases followed by the complete ten mounted cases (original eight plus two),
  24 Candidate surface/state cases, TypeScript, browser syntax and 77 staged
  ownership cases, all green checks exiting 0. The real fault/restart fallback
  and far-side Sample/Truth/no-authoring assertions belong to those mounted
  tests; they are not claimed as injected browser cases.
- The original single `bash scripts/docs-site.sh check` ran from
  10:24:05.966058 to 10:24:49.457338 UTC: **179 tests PASS, 50 routes/internal
  links valid**, exit 0.
- After cached whitespace passed, the repaired nine-file Task became local
  clean checkpoint `aaea4937ed90a8385f4baf968cf8e22498c83e86`. Normal pinned
  Creator configure, build and package all exited 0. This is the actual tested
  source/artifact identity; a subsequent plan-results-only amendment does not
  imply another build at its new Git identity.
- The original official Candidate fixture was reused byte-for-byte and passed
  the official bundle verifier, exit 0: 127,305 bytes, SHA256
  `e55bb562f6398df1489acc23cafb7fa8963e0581f8547550de3f1c28f26f8c4e`.
  Its recorded Pattern, assigned Pad and negative PCM provenance remain bound
  to the retained original generator receipt; no Native regeneration occurred.
- A prelaunch evidence script incorrectly asserted that the host manifest
  includes a Git-head field. It failed before any server/browser launch. That
  setup-only error is retained; the actual schema has no such field. Root
  admitted the corrected external binding of clean HEAD, normal build receipts,
  unchanged source snapshots and all ten distribution hashes. Product source,
  assertions, budgets and the package were unchanged; no browser retry occurred.
- The first complete repaired-source browser invocation used the standard
  audio-output wrapper, Chromium, one worker, the verified private server and
  both complete `creator_web_candidate.spec.mjs` and
  `creator_web_candidate_runtime.spec.mjs`. It naturally completed **15 PASS,
  0 FAIL, 0 SKIP**, exit 0, from 10:28:47.226452 to 10:30:18.310490 UTC.
  All original preview/stop/adoption/PCM/Artifact/Pattern/refusal/restart legs
  and the independent first-played Back case retain their far-side assertions.
- Three viewports retained zero and multiple-candidate/explicit-target
  screenshots and geometry. All 87 observed controls now measure at least
  **44 actual CSS px high** (minimum width 152), and all 435 centre/edge hits
  pass on this integrated U01 base. The previous 34.65px historical result is
  retained above. This proves these observed controls, not universal control
  or physical-device compliance. Representative screenshots covering all three
  viewports were inspected with no new actionable Slice layout finding.
- All 3,767 tracked inputs and nine frozen files remained identical throughout
  each heavy command; all ten distribution files remained unchanged across
  browser execution. The 17 resulting browser artifacts were hashed. At
  10:31:06.367127 UTC all 209 observed owned PID identities were absent, the
  private server had stopped, and the heavy window was explicitly released.

Evidence is retained in `build/verification/u10/repair-heavy-20261013/`, indexed
by `final-nine-tested-verification-packet.json` and `heavy-release-receipt.json`.
Each command records actual argv/start/end/exit/log hash and before/after source
inputs. The browser log is 3,632 bytes, SHA256
`7b8dea715961eb34359b15e9a216388861e930568d6bfa1bda4e41b6be8cf7f3`.
The original source, negative evidence and old artifact identities remain intact.

Only this plan-result appendix changes after the tested checkpoint. Push and PR
mutation await Root's final readback; the coordinator owns current-head review
and guarded merge. Full Creator/Core, WebKit, physical-device/hearing, release
and deployment acceptance remain separate. No new pitfall-ledger change is
needed for the product fallback regression; its discriminating owning tests
capture the defect and no product or runner workaround was introduced.

The final plan-only commit premise refresh reached published main
`28ff18c5c1f3790157193e900b5c7980cc595026`. Newly merged Capture and Trim
presentation changes touch their own components, tests and distinct Portal
sections; their full shared-page diff was inspected and does not alter Slice
producer/consumer or its owning assertions. No forced rebase is needed.
