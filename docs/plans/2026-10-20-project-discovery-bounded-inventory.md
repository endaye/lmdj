# Current-main integration of #2410

# #2410 integration premises before source edits

Main5ec03d715b2fbf2323219537be159336f5b6f315; original sourcec3edab71c0ad6eb380e0d9a8837dd56a67db7ee2, original parent3a62b103c7c79cbfb8c18e4849b3cd477318df4c. Clean isolated fix/project-discovery-bounded-inventory-main has10 actual symlinks. Live #2112/#2135/#2237/comments and #2410/#2411/#2438 refreshed. No competing discovery implementation exists; #2411 owns subsequent Take consumer.

- Outstanding: actual Creator App startup calls listLocalProjectsJourney before opening remembered Project; SDK/Control project.list calls public Application list_local_projects -> ProjectBundleTransfer list_local_projects -> summarize_project -> project_digest -> collect_inventory. Current collector calls read_complete on every file and only afterward applies64MiB entry/512MiB transfer payload limits. Current summary load does not retain history/writer across full inventory. Read authoritative dispatch/handlers, not only name search.
- Already delivered: bounded Save/bind5ec03d71 (#2438) and raw/scan/WAV/Facade/Runtime/SDK producers through #2437. Save now accepts the physical345600056-byte recording under fixed512MiB; direct reopen/metadata is not startup discovery. Do not repeat those fixes or import held meter/capture-progress/withdrawn COUNT-IN ancestors.
- Four non-new inputs compared: C++ collector, original Native test and real RPC spec equal original parent; only ProjectIO Portal differs by the verified Facade/SDK status correction from #2438. Re-home only this five-file delta and retain that correction plus all original tests/journeys.
- Local discovery requires full canonical identity, stable history-before-writer ownership and bounded64KiB ranges with complete digest, pre/post lengths and EOF. Preserve keys/path validation/4096 count bounds/unsigned canonical order and uint64 overflow protection. Existing local long recordings are not Bundle import/copy authorization; transfer64MiB/512MiB caps remain at their original boundaries. Legacy small complete reads stay compatible; oversized legacy files refuse before allocation, present-reader errors never fall back.
- Original full Native bundle-transfer baseline must pass before edits. Apply added observer against unchanged collector for actual rebuilt RED at complete_recording_reads==0 while digest agrees, then exact fix/rebuild GREEN. Preserve all original import/copy/publication/recovery tests and complete12-suite persistence/stress selection. Real Chromium4/WebKit3 retains all original metadata/live-Control/longSave/bind/two-reopen legs and adds public project.list plus independent browser-Crypto full physical canonical inventory digest in every long-file report; no increased512MiB,30s RPC or180s case budgets.
- Formal staged-source proof and clean-head production Creator configure/build/package are separate boundaries. Run heavy Native/Wasm/browser/Portal/production phases sequentially. Full Portal/ownership/source boundaries/current-head independent review and guarded merge remain required. Preserve the second original U08b discovery OOM trace take-audio-bounded-parent-target-chromium, earlierSaveOOM/fixture mistake and oldB0 WebKit negative evidence.
- Exact five-file Task, one Conventional Commit; current normal push/review/squash and safe postmerge cleanup authorized. Original published stack, rootmain6ca4c9cf and both dirtyWIPs remain untouched. Release-owned path freeze, fixedcandidate8c361623f and pending #2430 owner exception stillapply; no hand-resolve, subagents, auto-merge/tag/Release/deploy/Channel.

Original complete Native bundle-transfer baseline passed3.263s before any Task
edit. The added observer first runs against the unchanged collector; a matching
digest alone cannot establish bounded reads. Later verification and shipping
boundaries remain pending until actual receipts exist.

## Additional startup discovery verification

Source inspection confirms Creator lists before selecting/opening the remembered
Project. Preserve all original post-open complete-inventory digest assertions,
and additionally list on each fresh reopen page before project.open. Exact
Project/Pattern/revision/summary-key identity and digest shape prove startup
admission with no selected Project; the independent full physical digest remains
asserted after the original list. No original leg, limit or budget is removed.

## Current-main source verification

Original complete Native bundle-transfer baseline passed3.263s. Added observer
rebuilt against unchanged main fails at complete_recording_reads==0 (exit8),
after the exact complete-digest assertion succeeds. Applying the exact original
collector fix recompiles project_bundle_transfer.cpp and passes; final original
persistence/component/writer-stress selection12/12 passed30.870s. Full original
import/copy/publication/recovery cases and limits remain called. Independent
Python hashlib confirms the literal131089-byte recording digest. Dependencies,
Runtime and explicit-root Host source boundaries pass. Pinned formal Wasm configure/build passed. Actual complete Chromium4/4
passed106.317s and supported OPFS WebKit3/3 passed141.618s, with no skips/flaky/
retries and original budgets unchanged. Each browser retains9 metadata reports,
6 long-file full physical canonical inventory comparisons and15 closed pages.
Four fresh-page pre-open lists additionally pass exact identity/revision/key/
digest-shape assertions; complete artifact readback verifies those digests also
match the unchanged fixture's independent post-open inventory digest. Full WAV
345600056-byte SHA/header/tail/86400000frames at48kHz/stereo and512MiB memory
remain exact. Built-in speakers observed at both endpoints, no warnings; this
is controlled OPFS fixture evidence, not captured PCM or device hearing.
Full Portal passed64.070s:179 tests,53 pages,51 routes/internal links.
Precommit main5ec03d71 and all seven read governing files are unchanged; all
four non-plan verified input hashes remain exact. A clean unpublished source
checkpoint is required for official production Creator configure/build/package;
those receipts and independent review remain pending until their boundaries.

## Retained original Task record

The following is the published original implementation record. Its older base,
freeze, counts and unverified boundaries are historical; current authorization,
refreshed premises and new receipts above govern this integration.

# Bounded local Project discovery for saved long recordings

## Premises before implementation

Integration main remains `1c4462aa8436f81da1db2a9e6420d94f0e84ccb4`.
The isolated prerequisite starts at Draft #2409,
`3a62b103c7c79cbfb8c18e4849b3cd477318df4c`. All18 Drafts and live
#2112/#2135/#2228/comments were refreshed; no discovery repair exists.
The previous goal turn delivered #2409; this turn's actual clean rebased U08b
checkpoint `d97d10e2606e4986f2b44c66d1793005e1f4671c` passes Creator1930,
types and official production build/package, then fails its original browser
journey with a new OOM during first page reopen. Preserve the terminal1/trace
in `take-audio-bounded-parent-target-chromium` as well as the earlier Save OOM.

| Premise | Disposition before edits |
| --- | --- |
| Long Save/bind verification still allocates the whole WAV | Already repaired in #2409; seeded Save/close now completes. Keep that implementation and all original failure evidence. |
| Creator reload only opens its remembered Project | False: App first calls `listLocalProjects`; `summarize_project` calls `project_digest`/`collect_inventory`, which reads each whole file before enforcing a64MiB transfer-entry cap. The345600056-byte recording traps during discovery, before the remembered Project can reopen. |
| Public local summaries can return a fabricated or partial digest | False: preserve the exact canonical inventory digest and every existing summary key. Hash all physical bytes, with bounded windows and stable ownership, or fail. |
| Local saved Performance recordings have the Bundle transport's byte caps | False: the active Product admits86400000 recording frames and #2409 stores those raw bytes locally; local ProjectStore/metadata open already accepts them. The per-entry64MiB and aggregate512MiB caps describe Bundle import/copy admission. Keep those caps at those boundaries; this is not a bundle-format migration or a higher transfer limit. |
| Full inventory can be read across unowned mutations | False: retain a reentrant Project writer lease across summary load and complete inventory, including bounded reads. Keep managed-path validation, canonical ordering, count/depth bounds and exact digest identity. |

## One Task / declared files

1. `packages/project-io/src/project_bundle_transfer.cpp`
2. `tests/core/project_io/project_bundle_transfer_test.cpp`
3. `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`
4. `apps/docs-site/docs/core/modules/project-io.mdx`
5. `docs/plans/2026-10-20-project-discovery-bounded-inventory.md`

U08b remains an unpublished separate Task. No Host/App, SDK/public key shape,
persisted Contract, schema, recorded bytes, quota/heap, manifest or CI change.

## Implementation and owning checks

Separate local discovery inventory from transfer admission privately. Discovery
keeps the exact digest for ordinary Projects and can describe local recordings
larger than transfer byte caps; no success implies export/copy eligibility.
Import/commit/duplicate retain all their original transfer caps. Production
Native/OPFS use the existing optional range companion and one64KiB heap buffer,
full SHA, lengths and EOF. A present reader's errors never fall back. Legacy
platforms keep their small complete-read path; oversized input without bounded
capability fails before allocation. Protect uint64 totals against overflow.
Reuse the existing shared history guard before the writer lease, in the
established lock order, throughout summary load and inventory reads.

- Baseline: original complete Native bundle-transfer suite before source edits.
- Native regression: forbid whole audio reads while using the real Native
  backend; discover the same full inventory/digest under bounded short reads.
  Complete raw reads, bad counts/zero progress/error, length/EOF disagreement
  and concurrent writer access have direct oracles. Existing small transfer
  identities and all import/copy payload limits remain unchanged. Demonstrate
  rebuilt RED against the original collector, then GREEN with the fix.
- Run original bundle-transfer, Project Store/history, recording persistence,
  platform and writer-lease integration/stress checks, without budget changes.
- Extend the original formal long Save/bind journey with public `project.list`
  after every Save and both reopens, independent full physical inventory digest
  readback, exact headers/ref/frames and512MiB memory. Preserve original cases,
  budgets and the30-second RPC deadline. Test Chromium and supported OPFS WebKit.
- Pinned production build/package and source boundaries; full Portal, declared
  paths, ownership, complete diff and committed-range/PR checks before Draft.
  Controlled fixture files do not establish physical capture or hearing.

## Version Management

Version impact: compatible internal Project I/O PATCH debt under #2237; retain
the higher existing same-domain MINOR debt. No ABI/Contract/key or dependency
change, version/manifest/Product/Assembly/Build/snapshot allocation.

## Documentation Impact

Documentation impact: required — `/core/modules/project-io/`. Distinguish local
discovery's complete inventory identity from unchanged transfer eligibility,
bounded reads and writer ownership. No diagram edge changes.

## Shipping boundary

One Conventional Commit, verified push and Draft successor of #2409, then
rebase the unpushed U08b Task. No merge/auto-merge until owner unfreezes main;
no release, deployment, Channel or Git cleanup. Independent review, complete
candidate/device evidence, U08b/U08c and #2112 completion remain open.

## Verified source checkpoint

Original Native Bundle baseline passes. The first added digest fixture used
the default Project ID instead of its actual source ID; retain that failed
attempt. Correcting only the fixture yields actual rebuilt RED at
`complete_recording_reads == 0` while the full digest agrees. The rebuilt fix
passes; final original-plus-new persistence/component/stress selection12/12
passes, including all original import/copy/resource/publication/recovery tests.
No original deadline, quota, floor or acceptance leg was reduced.

Pinned Emscripten6.0.5 formal build passes. Target Chromium and then full
selected Chromium4/4 and supported OPFS WebKit3/3 pass. Per browser, six
Save/bind/preparation/two-reopen reports contain independent browser-Crypto
canonical full-inventory digest readbacks, exact345600056-byte WAV identity,
86400000frames/48000Hz/stereo and fixed512MiB heap. All JSON is read back;
the nine original metadata reports per browser also remain. Formal harness
evidence is distinct from complete Creator UI or physical/hearing acceptance.

Full Portal179 tests/52 pages/10 diagrams/20 outputs/50 routes and dependency/
Runtime source-boundary checks pass. Precommit main remains1c4462aa and the
#2409 head is exact3a62b103. An unpublished clean checkpoint is needed for the
official production build/package; that result and final ownership/body/range
checks must be read before Draft publication. U08b remains unpublished at
d97d10e2 until this prerequisite is delivered and integrated into its branch.
