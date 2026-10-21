# Creator stereo output meter consumer (#2231 / D04)

## Current main integration (2026-10-21)

The owner now authorizes sequential integration of the 19 open PRs under #2112.
This section supersedes the historical Draft/freeze transition wording below;
the original receipts remain historical evidence. Integration base is
`54439f207926841b9411c805d70252c5df66b33f`, which already contains the meter
producer through #2430, metadata query, capture progress and telemetry isolation.
The producer is not reimplemented. Creator consumption remains outstanding at
that exact base, as confirmed at App, OverviewDisplay and PerformOverview.

Preserve the published #2384 head `8d85f862e08ee1f7306ecb27146dde35af490059`
as the first parent of a normal main-integration merge. The resolved tree is
current main plus this Task's original 16-file delta, with the two Overview
conflicts resolved to retain only meter binding/test additions. COUNT-IN imports
and tests that main withdrew in #2396 are not meter-Task additions and remain
withdrawn; #2377 and its explicit acceptance decision remain separate. No other
old stack ancestor is imported, no published history is rewritten, and every
non-Task path must equal this integration base.

Version impact: existing compatible Creator Host MINOR debt in #2237; no identity
allocation. Documentation impact: required for /hosts/creator-web/ and
/hosts/creator-interactions/. Retain all original meter journey legs and budgets.
Re-run complete Creator UI, types, dependencies, pitfall/ownership checks,
Portal, clean official production package and both packaged meter journeys.
Current-head independent review and all conversation/conflict/protection checks
remain required. Full candidate, physical-device and hearing acceptance remain
unverified. No release, deployment, Channel or cleanup is included.

The first integration browser run failed both initial stereo signal predicates.
Retained traces show actual nonzero left and right output, sampled in different
polls; the default 100/250/500/1000ms backoff can miss the shared steady interval
of two asynchronously started one-second voices. Two unchanged-package full
reruns passed, which does not establish a product fix or an environment cause.
Keep those failed and passed receipts. Match the signal observer to the existing
20ms silence/display polling cadence, retaining the 35s deadline, both exact
Native started receipts, 50ms steady-window bound, literal PCM oracle, ratios
and every downstream journey leg. Add passive first-signal/voice diagnostics
for future failures. This addresses the test's sampling gap; Native input
latency and the separate #2395 investigation remain unresolved.
The current integration therefore declares one additional existing path,
`.agents/pitfalls/live-phase-polling-alias.md`, for this recurrence and its
already-open #2382 escalation: 17 net paths, with no additional product scope.

One implementation Task, one Conventional Commit, above Draft #2383 full head
`3cdf2ef9350e37d3ac4f0cb0e693e7d27362b083`. Main remains explicitly frozen:
develop, verify, commit, push and Draft stack only. No merge/auto-merge, release,
deployment, Channel promotion or Git/resource cleanup. Independent current-head
review remains PENDING until the real integration boundary after owner unfreeze.

## Refreshed premises before implementation

Integration main: `1e9e5fbea57f2250b6fda7c39634d1a4d542438b`. Its AGENTS,
CLAUDE, issue-done and Git workflow are byte-identical to this Task parent.
Live #2231 is OPEN, no comments; #2383 is OPEN Draft with the expected head,
base #2381 and no auto-merge. The complete open-PR inventory has no meter
consumer successor. Preserve the approved D04 decision and historical receipts.

| Claim | Disposition and instrument |
| --- | --- |
| Real always-on measurement missing | Already delivered in the stack by #2383: Worklet/manager/typed SDK `outputMeter()`, actual L/R peaks/frames, owner/freshness/unavailable and fault fallback. Do not modify or repeat it. Main alone does not contain this unmerged producer. |
| Creator meter missing | Still outstanding at both exact main and parent. Read complete PerformOverview props/render, OverviewDisplay's Perform branch, App's actual overview binding and CreatorRuntimeSession type. Transport/controller/sampleAudioClock are positive controls; none carries or renders meter measurements. |
| Existing controls and facts | Already delivered: shared ENC4/MASTER, independent applied Filter, current/queued Pattern facts, launch ACK cue, progress and recording phase. Retain their sources and assertions; no new gain, DSP, Truth, capture storage or transport query. |
| Design authority | Current read-only Figma context `GPFarNiZNsjLQzfG9kR8DO` / `410:4369`, child meter `410:4551`, read with screenshot on 2026-10-19. Two horizontal 3px rails, L lime/R sky, small inline L/R dBFS text below the four existing facts. Existing current launch/progress facts must also fit without collisions. All shapes are dynamic UI geometry, no static asset/Code Connect mapping returned. |
| Approved units and hold | D04: Post-FX/Pre-ENC4, exclude click, separate L/R, range -60..0 dBFS, real zero is -infinity, one-second peak hold, explicit unavailable. Producer owns the measurement point; this Task only consumes it. |

Shared App/overview/runtime types/browser and Portal have one writer. Work in
this isolated `feat/creator-stereo-meter` worktree. Heavy Native/Wasm, Portal
and browser/audio verification is serial. Preserve all original source refs,
failures, release-owned resources and the existing six Draft layers.

## Exact declared files

Only these 16 paths (the new tool-boundary pitfall is declared after the observed artifact gap):

- `.agents/pitfalls/playwright-success-body-attachment-not-persisted.md`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `apps/creator-web/src/state/output_meter.ts`
- `apps/creator-web/src/components/stereo_output_meter.tsx`
- `apps/creator-web/src/components/perform_overview.tsx`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/overview_display.css`
- `apps/creator-web/test/output_meter.test.ts`
- `apps/creator-web/test/stereo_output_meter.test.tsx`
- `apps/creator-web/test/perform_overview.test.tsx`
- `apps/creator-web/test/overview_display.test.tsx`
- `tests/platform/web/creator/creator_web_output_meter.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/plans/2026-10-19-creator-stereo-meter.md`

## Consumer rules

Reuse the SDK's actual `StereoOutputMeter` type and getter signature; an
optional Creator capability admits older adapters without inventing a second
measurement DTO. Missing, throwing or unavailable sources render UNAVAILABLE,
never zero/0dBFS. No commands, capture dependency or persistence.

Project raw sample peaks with `20 * log10(peak)`, clamp nonzero display to
-60..0, keep digital zero distinct as -infinity. Display one decimal place.
Use actual AudioContext frame age and each channel's actual peak frame for
one-second hold, not receipt time, RAF timestamp, Date or another wall clock.
Equal/higher peaks refresh only to their measured frame; rereading the same
packet cannot extend its hold. After expiry use the current measured peak.
No invented decay or interpolation between measurements.

Keep view/hold ownership bound to Session, Project, actual meter owner and
sample rate. Clear it on unavailable, non-running audio, scope replacement or
unmount. First render of a replacement must not borrow an old value. One local
cancel-safe animation-frame reader exists only while the Perform meter is
mounted and eligible; it reads the synchronous getter, never an RPC. Keep
frequent rendering in the small meter component, outside App/controller state.

Render the two live rails, independent hold markers and accessible read-only
L/R values using current fonts/tokens. Keep existing current/queued/counter,
launch cue, Pattern progress, Performance phase and assigned-slot facts visible.
Reserve a distinct meter row and avoid overlap with the encoder row at all
declared viewports; no out-of-scope layout/controls redesign.

## Verification

Baseline before source edits:

```sh
npm --prefix apps/creator-web test -- --run test/perform_overview.test.tsx test/overview_display.test.tsx test/monitor_output_controls.test.tsx
```

Lowest owning checks: new pure output-meter and component tests, existing
Perform/Overview files plus monitor controls; then Creator TypeScript and the
complete current Creator unit selection because App/types/overview are shared.
New file registration: staged and final committed
`python3 tests/build/ci_change_scope_test.py` (76 tests). Inspect the actual
terminal exits, staged/committed file lists and final clean worktree.

Each unit test fixes one fact: independent literal dBFS/zero/range, actual-frame
hold including exact expiry/repeated reads/rate and owner changes, unavailable,
Session/Project replacement, no command writes and queued-RAF-after-unmount.
Discriminating controls must actually fail owning assertions for wrong dBFS,
receipt-time/repeated-packet hold or missing real UI binding as applicable;
restore WIP bytes with fresh mtime, retain real RED and restored GREEN.

Retain and extend both complete existing packaged meter journeys, including
dry unequal stereo/literal oracle, FX, monitor zero, real capture/PCM/Stop/seal,
click, System suspend, actual context interruption/return, accepted voice/new
owner and 1000 zero-RPC reads; actual render-fault candidate must retain
hash-correct/offline-ready/unchanged-Wasm and nonzero direct-monitor fallback.
Add far-side DOM/rail/readout/owner assertions to the actual SDK measurements,
including hold expiry and unavailable/recovery. Never replace the real producer
with fake packets, inferred trigger levels, synthetic error or animated data.
Keep all original 300s/240s and 35s/125s budgets, thresholds and journey legs.
Check meter geometry/readability at 1440x900, 1280x720, 1024x768, 820x1180,
768x1024 and 390x844; wait for real viewport/refit before measurements.

Run the complete Portal check for both changed routes. No Module boundary or
diagram edge changes: reuse the existing read-only four-region source diagram;
all ten architecture diagrams remain untouched. Do not edit generated diagrams.
Use an unpublished clean verified-source checkpoint for official Native/Wasm/UI
configure/build/package; any browser finding leaves this Task incomplete.
Correct, reverify and amend the same atomic Task before publishing its Draft.
Run PR-body lint and actual-parent declaration to terminal0 after the final
body edit. Parent-relative ownership is not proof of complete lane execution;
retain explicit full platform/candidate/device/hearing gaps.

## Source verification receipts before clean packaging

Baseline three existing files:39 PASS. Initial owning selection:82 PASS/1 FAIL;
the strict equal-peak one-second assertion exposed ceil turning a rational
sample time at frame119999 into phantom120000. Recover the nearest sample
frame with round, retaining the exact deadline/peak-frame semantics. After the
fix all five owning files83 PASS; Creator TypeScript PASS. Initial exact-optional
prop/fixture typing errors were corrected without widening public types.

Complete Creator selection:82 files /1884 PASS (88.07s), repeated1884 PASS
(89.02s). Owning83 PASS again after narrow-only layout changes; the measurement/reader logic and
tests are identical to the complete selection; a later explicit aria-live=off
on the leaf output is checked by owning tests and the final real journey.
The final stylesheet independently parses52 CSS rules; native browser geometry
remains required. No test deadline, skip, assertion or original journey is removed.

Three fresh controls actually fail owning semantic assertions:10log instead of
20log, receipt/read-time hold instead of actual peak frame, and foreign-owner
hold inheritance. Each exits1 at its named assertion, WIP is restored byte-for-
byte with a strictly fresh mtime, and the exact original test exits0 in a new
process. All15 WIP file hashes match after each restoration. Later changes are
CSS/documentation and an explicit leaf aria-live attribute; owning control
inputs (the pure projection and its tests) stay unchanged.

Portal complete check PASS:179 tests, production build and50 routes/internal
links. All architecture diagram inputs/outputs remain unchanged. Core dependency
check and TypeScript PASS. Original negative runs and stylesheet warnings remain
retained. This is not packaged/browser, device or acoustic evidence yet.

Create an unpublished clean source checkpoint only after staged new-file
ownership and diff checks pass; browser/layout/fault and final committed-path
checks remain pending. No push/Draft or completion claim until those real gates
finish on a clean package. Keep all six ancestor Drafts unchanged.

## First packaged and retained-evidence observations

Clean source checkpoint `c10a118d73e6f98f925afe819f62d6b8e649be7e` passed
Native CLI, pinned Wasm/UI configure/build/package and both complete Chromium
journeys (39.6s). Real DOM/packet correlation, literal -5.1/-17.1dBFS, actual
held-zero then frame-aged expiry, all six meter layouts and actual render-fault
UNAVAILABLE/direct-monitor PCM passed, preserving every original transition.
Actual audio output start/end was built-in MacBook Pro Speakers.

The post-run artifact audit found six PNGs but no success trace/JSON. The locked
Playwright line reporter and retain-on-failure policy keep body-only attachments
in memory; inspecting its actual normalizeAndSaveAttachment confirms only path
attachments copy bytes. The attempted trace-based extraction exited1, not proof
of missing product behavior or a failing browser journey. Retain this finding;
write owned JSON files through test.info.outputPath and attach by path, then
actually read their frame/owner/PCM/geometry data after the final complete PASS.
Declare the existing-spec proof fix and the first tool-boundary pitfall in this
same Task, without changing shared Playwright config, reporters, trace policy,
CI, thresholds or deadlines. First recurrence stays open with no claimed gate.

Read the 1440,1280 and390 screenshots. The new meter has the intended pair of
3px rails/current values; preserve the existing Pattern facts/footer/progress.
At390 the unchanged mode/transport header is already crowded; it is outside the
meter component and does not become full-console/device acceptance from these
meter-only geometry checks. Keep it in the later Perform layout/acceptance scope.
The final proof also checks the two retained footers do not overlap each other,
retains a real unequal-signal screenshot, and explicitly silences live output
announcements. No measurement/hold/SDK algorithm changes follow this first PASS.

## Version Management

Version impact: Creator Host compatible additive MINOR debt in #2237.
Reason: new truthful user-visible readout using the existing SDK API; no SDK,
native ABI, Project Contract/persistence, manifest, Assembly, Build, Channel or
immutable snapshot allocation. Keep earlier Audio Runtime ABI MAJOR debt.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/
Reason: actual meter rendering/hold/unavailable and lifecycle behavior changes.
Existing source diagrams retain identical boundaries; no new Module/Host or
measurement graph is introduced. Keep measured automation, candidate, merge,
physical-device and acoustic acceptance as distinct facts.

## Shipping boundary

Commit, push, Draft PR with base `feat/stereo-output-meter-producer` (#2383).
Keep #2231/#2112/#2237 OPEN pending independent review/integration, version and
final acceptance. Only explicit owner unfreeze lifts the merge hold; external
release/deployment/merge activity does not. No auto-merge or cleanup.
