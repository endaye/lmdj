# Retain verified live-control identity for the writer lease

## Premises and remaining scope

Relates to #2112. Original base `86ad15ed2aa095bd54c25601d736db56838d956b`;
refreshed integration base `a6526e768b4604b05e8dd624174106976348a062`;
branch `fix/performance-control-deadline`, isolated worktree. The preceding
#2466–#2469 changes are already merged and must not be repeated. Main's later
#2475 changes release governance, not these product inputs. Frozen CI/release
paths and other worktrees remain outside this Task.

The retained #2469 browser failure names `performance.live.control`, the
unchanged 1000ms deadline and cancellation return1. A complete unchanged repeat
passed; that does not establish its cause or repair. Current Host dispatch
forwards live status/control to Facade; `verified_live_epoch` calls
`ProjectStore::load`, which validates the tree, replays history and verifies
Assets. An independently instrumented copy of the existing owning Native test
on unchanged current libraries measures three complete file reads for each
operation even on an empty Project. Original owning component baseline passes.
This proves repeated storage work, not the sole cause of the historical timeout.

Retain the Core-verified immutable Project UUID inside the existing opaque
writer lease. An explicit preparation on the long Project-create/open turn
performs the original complete load and verification. The live-only Facade
entry accepts only a prepared, still-owned lease from this Application and the
same normalized path. Reuse the existing live admission/status implementation,
including real Engine epoch binding, CAS, exact retry, recording-route refusal
and existing command service. No arbitrary Project ID supplied by a Host is
trusted. Lease move/replacement/release bounds the retained identity; no
process-wide path cache or second controller. Failed preparation clears the
identity. Legacy public command/query behavior stays available unchanged.

This removes repeated identity-loading I/O from the bound live path. It does
not claim all operations or Performance service are I/O-free, change deadlines,
or resolve S5 long-note and Native metronome product decisions. Whole Host TSan
480s and historical browser failures remain recorded unless separately resolved.

## Declared files

1. This plan.
2. `packages/application-facade/include/lmdj/facade/application.hpp`
3. `packages/application-facade/src/application.cpp`
4. `tests/core/facade/performance_gesture_admission_test.cpp`
5. `packages/web-runtime-platform/src/control_runtime.cpp`
6. `packages/web-runtime-platform/test/control_runtime_test.cpp`
7. `apps/docs-site/docs/core/modules/application-facade.mdx`
8. `apps/docs-site/docs/platform/web-runtime.mdx`

Amend before expanding. No protocol/SDK/Engine/Project Store/Truth format,
App/stylesheet, build manifest, workflow, release tooling or version allocation.

## Verification and defect oracles

Keep the complete owning Facade and Native Host suites. A storage-count oracle
must distinguish a known-present read on the legacy path from zero identity
reads on the prepared path; execute its RED with actual old dispatch before
the optimized dispatch, then GREEN without weakening the assertion. Verify
full preparation failure, wrong Application/path, unprepared/moved lease,
exact retry, stale epoch and recording exclusion retain their far-side state
and admission counts. The Host owning test must exercise the production route.
Retain real Engine accepted/applied, stop/reopen and existing ownership tests.

Build/package the ordinary own-tree Creator artifact with pinned Emscripten
6.0.5, Node26 and locked browsers. Run the unchanged complete hardware/a11y
selection, including the original HOLD/MASTER journey, with original budgets.
Record input hashes, actual output device, both failures and successful
attachments in unique output slots. A green browser run is Task evidence, not
proof that every historical timing failure or candidate debt is repaired.
Run dependency, staged new-path ownership, declaration and full Portal checks
for the documentation changes. Recheck current main premises before commit
and merge; independent current-head review and live protection remain required.

### Source refresh and retained negative evidence

The original Native component and complete Host baselines passed3.399s and
84.573s on86ad15ed. Adding the prepared-entry oracle while retaining old live
dispatch produced actual RED0.860s at the exact zero-read assertion. The real
Host route's new regression likewise produced RED20.652s at
`storage->complete_reads() == before_live`, before Host dispatch changed.
An intermediate Facade GREEN3.932s is retained; final canonical-dispatch and
Host wiring were then rebuilt against the refreshed main. All eight complete
owning selections pass103.845s: real Engine adapter, tempo journey/identity/
uncertain/ownership and stress, Facade gesture admission, and the entire Host
suite (93.19s). The Host regression proves actual Engine apply and exact retry,
unchanged complete Truth and zero Project reads on the prepared live calls.
Portal, clean artifact/browser and current-head shipping evidence remain.

On2026-10-24, refreshed main to
`a6526e768b4604b05e8dd624174106976348a062`. Incoming40 paths do not overlap the
six in-progress files; fast-forward kept every Task byte and its patch exactly.
#2478 amortizes existing Artifact reads to1MiB windows, without preparing live
identity; rebuild the owning targets against this source. #2479 actually merged
COUNT-IN with the owner's selected JS pre-arm and documented late-refusal risk.
Do not duplicate or replace that delivered scope; the separate I2c same-clock
question remains outside this Task. Release-only changes stay outside its diff.

After owning Native, source/ownership and Portal checks pass, an unpublished
clean local checkpoint may bind the official ordinary browser artifact. It is
not shipping or Task completion: full declared browser journeys, current-head
review and integration checks must finish before push/PR/merge; retain failures
and fix the owned source rather than relaxing the journeys.

## Version Management

Version impact: Application Facade MINOR for additive nonvirtual methods;
Web Runtime Platform PATCH for existing-operation dispatch. Opaque lease and
Application object layouts are unchanged. Retain higher existing same-domain
debts in #2237; no manifest/Product/Assembly/Build/snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /platform/web-runtime/
Reason: document verified lease identity and the long preparation/short live
dispatch boundary. Existing modules, ownership and wire operations stay the
same; no topology diagram change is needed.
