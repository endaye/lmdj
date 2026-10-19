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
