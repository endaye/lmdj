# Stage 9 Sequence Recording Acceptance — 2026-08-23

## Current status

Product Build candidate `1.0.37.0` implements Project v3 event-only
Sequence recording across the Core, CLI/MCP/Native/Web Hosts and Creator.
This ledger records only evidence actually produced for the candidate and its
integrated tree. PR [#334](https://github.com/endaye/lmdj/pull/334) reached
snapshot commit `147ab6cd3bff19d6bea0089ec3c8380b1dac98bd`. Full CI run
[`33047854982`](https://github.com/endaye/lmdj/actions/runs/33047854982),
including every selected lane and the aggregate PR Gate, passed. Corrective
integration changes after the original Task 9 commit were closed before the
immutable Portal snapshot was regenerated from exact source revision
`f9b82d40517ddaafb757352ab92ea96916362af2`. The final PR head
`4bce976c0d6878de9894d4d28c7cfab4a4bb0140` was squash-merged as exact
`main` commit `1bc79006121cee77ba6d19e882890dc0aa95c95a`; both commits have
tree `433969283ab0a091caa1f6e6b2f954bc0d9cc91d`. Exact-main Core CI run
[`33058032797`](https://github.com/endaye/lmdj/actions/runs/33058032797)
passed every selected lane, including the landed snapshot projection check.
Product tag, Release, deployment, publication and Channel promotion remain
pending until their separately authorized boundaries occur.

## Post-delivery source remediation — 2026-08-29

Issue #376 corrects review finding H2 without rewriting the historical
`1.0.37.0` candidate or its immutable snapshot. The shared Web Runtime Session
now retains the Facade switch authority, accepts only the matching
session/Pattern/frame/generation boundary, reserves it before dispatch, and
serializes one generated-command flush before both Host acknowledgement and
the first later Pad event. Creator changes selected Pattern only after a fresh
Facade query reports that target active. Duplicate, reordered, stopped, and
superseded boundaries cannot publish optimistic authority or issue a second
flush.

Source-level verification produced by the remediation Task includes:

| Command / journey | Result |
| --- | --- |
| `node --test packages/web-runtime-platform/test/runtime_session.test.mjs` | PASS: 54/54; exact-one matching boundary flush, duplicate/reordered rejection, and flush-before-post-boundary-event ordering |
| Web Runtime Platform plus Formal Host Node suites | PASS: 159/159 |
| `npm --prefix apps/creator-web test -- --run` | PASS: 344/344 across 19 files; boundary state requires confirmed active authority |
| Creator TypeScript and production Vite build | PASS |
| Formal Web Runtime Host targeted Chromium journey | PASS: old-Pattern record → acknowledged exact-one flush → new-Pattern record → stop → both committed Patterns inspected → new Pattern reload |
| Creator targeted Chromium Sequence journey | PASS: switch-pending keeps old selection; confirmed flush selects the target; first later unified input records without ErrorPanel or terminal Runtime failure |
| `scripts/core.sh test dev fast` / `scripts/core.sh test dev stress` | PASS: 36/36 fast and 4/4 stress; Native/CLI/MCP Facade contract remains green |
| `scripts/architecture-portal.sh check` | PASS: 59 tests, 37 current pages, 10 diagram sources/20 outputs, production build, and 42 routes/internal links |

The full packaged-browser suites, full Pull Request CI, integrated identities,
and a corrected immutable snapshot remain separate evidence boundaries. The
targeted browser journeys above extend through post-boundary recording, stop,
reload, and committed-event inspection; #379 owns the integrated version audit
and #380 owns the new immutable snapshot. The five physical/manual rows below
remain unchanged and unverified.

Documentation impact: required. Current routes updated by this Task include
Assembly, Project and Bundle Contracts, Core Modules, Hosts, storage, Web
Runtime, Native Audio, input, workflows, capability map, versioning and
testing/proof. Source diagrams for the product, Core, Project I/O, Cooker,
Facade, Audio Runtime and Web Runtime Platform are updated in the same Task.

## Post-delivery remediation

Issue #372 closes review finding M3 in current source. Sequence Journal now
deduplicates exact `command_id` appends and rejects conflicting payloads before
write. Application Facade retains an in-flight durable flush across a
post-commit return failure, replays only that identity, and leaves events
accepted between attempts pending for a fresh command. Component evidence
covers same-bundle retry and restart reconciliation for receipt-reload and
journal-completion faults, plus the active-Facade retry/new-event/stop journey.
Product Build and module identity refresh, integrated-main evidence, and final
remediation acceptance remain assigned to #379; this entry does not claim
those transitions are complete.

## Identity

| Identity | Candidate |
| --- | --- |
| Product Build | `1.0.37.0` |
| Project Contract | `lmdj.project.v3 · 3.0.0` |
| Project Bundle Contract | `lmdj.project-bundle.v1 · 1.1.0` |
| Foundation | `0.3.0` |
| Authoring Domain / Project I/O / Project Cooker / Audio Runtime / Web Runtime Platform | `1.0.0` |
| Application Facade / CLI / MCP / Native Host / Web Runtime Host / Creator Web | `2.0.0` |
| Task 9 exact revision | `e0f2de5b6453855f6def6407f962de8f8442c210` |
| Final snapshot source revision | `f9b82d40517ddaafb757352ab92ea96916362af2` |
| Snapshot commit | `147ab6cd3bff19d6bea0089ec3c8380b1dac98bd` |
| Final PR head | `4bce976c0d6878de9894d4d28c7cfab4a4bb0140` |
| Integrated `main` revision | `1bc79006121cee77ba6d19e882890dc0aa95c95a` |
| Integrated tree | `433969283ab0a091caa1f6e6b2f954bc0d9cc91d` |
| Assembly lock SHA-256 | `0aaab0918ad53a43a5e12b3d42a35ef38142343738637516d544d66ca21bef85` |
| Portal snapshot metadata SHA-256 | `240253c735b10f8a49e60492e55533843cdbd9fdd998b177cff0e3f4b4b15506` |
| Portal snapshot sidebars SHA-256 | `0b53c96bf33887703ac2c93177f8ef18b23fb480ffd81bc31aeeaeba0ccdb9c8` |

## Automated acceptance contract

| Boundary | Required evidence |
| --- | --- |
| Project Truth | v1/v2 deterministic read migration and v3-only writes with PPQ 960 Pattern events |
| Recording | begin/event/flush/stop, overdub replacement, idempotent replay and a manifest publication commit point |
| Concurrency | closed selective rebase for BPM, Quantize/Swing, and only the ongoing Pad Capture commit to its exact armed empty Pad; every other Sample mutation, changed/unarmed target, and unknown command fails closed without stopping the session |
| Timing | Audio Runtime integer BPM anchor and Bar boundary; no Host quantizer, floating musical clock or fallback sequencer |
| Switching | old Pattern remains active until the acknowledged next-Bar boundary |
| Recovery | owner-loss artifact, fingerprint-gated original Pattern, explicit valid destination or discard |
| Hosts | CLI/MCP parity, Native CaptureWriter and Web Runtime/Creator journeys use the Application Facade |
| Evidence privacy | reports contain semantic state, session/receipt identities, revisions and counters, never samples or local paths |

### #374 review-fix acceptance

Armed-Pad Capture publication now has a durable precommit boundary before the
Project manifest commit point. A retry with a fresh UI command/asset identity
may reconcile only the exact original session, armed slot, expected revision
and artifact bytes. It must validate the original transaction command,
receipt/event, committed revision, Asset and Pad assignment before completing
the journal; any mismatch fails closed without a second Project mutation.
Restart recovery applies the same receipt check before owner-loss sealing.

The pre-publication side of that boundary is also checked. If the durable
prepare exists but Project publication never happened, Discard/disarm acquires
the Project writer lease and compares the exact original session, slot,
command, Asset, artifact, expected revision, empty Pad, and absent receipt
against Project Truth. Exact unchanged truth appends one durable
`capture-abort`, clears only the Capture marker/arm, preserves pending Sequence
events and lets the same session flush/Stop. A matching published receipt takes
the completion path instead; any mismatch fails closed. Restart performs this
same decision before owner-loss sealing.

While that durable marker exists, the settings selective-rebase path is closed:
`UpdateSequenceSettings` must fail before Project publication with
`armed_capture_recovery_pending`. Project Truth and the journal stay exactly at
`N`; after checked Discard/abort, the retained session can still flush and Stop.
This prevents settings from committing `N + 1` and then failing the journal
rebase behind the Capture marker.

The packaged Creator gate records assigned A2 before the armed A1 stop gesture,
keeps A1 as the Sample mutation selection while A2 remains ordinary Sequence
input, proves that stop gesture is absent from Sequence, records A1 only after Capture
commit, stops, reloads/reopens, and inspects Project Truth. The exact acceptance
is revision `48`, one A2 and one A1 event added in that order (no third armed-hit
event), A1 assigned to the newly committed Asset, and the exact `audio/wav`
artifact identity including its SHA-256 and byte length across reload/reopen.
The unrelated running-audio BPM-update → immediate switch failure remains a
#375 blocker and is not removed from the full Proof journey.

Review fix 2 local verification on 2026-08-29 is green: Project Store,
Sequence Journal, Project I/O fault matrix, Facade Sequence surface and Web
Control Runtime focused executables; Web Runtime protocol/session `76/76`;
Creator Vitest `349/349` plus production build; Core full `79/79` and stress
`4/4`; Architecture Portal `59/59`, 37 current pages, 10 diagram sources/20
outputs and 42 routes; dependency, active-tree and version gates with Product
Build unchanged at `1.0.37.0`. The clean packaged Creator Proof is run from the
new commit so its deterministic revision describes the tested source; its
shared #375 failure, if still present, is reported separately rather than
reclassified as a #374 defect.

## Automated verification

| Command | Result |
| --- | --- |
| `python3 tests/conformance/schema_contract_test.py` | PASS: 11 positive, 11 negative, 17 Product artifacts |
| `python3 tests/conformance/project_bundle_contract_test.py` | PASS |
| `python3 tests/conformance/module_graph_test.py` | PASS |
| `bash scripts/verify-core-dependencies.sh` | PASS: vendored and offline |
| `bash tests/build/test_active_tree.sh` | PASS |
| `PYTHONPATH=apps/core-mcp python3 tests/host/mcp_stdio_test.py build/core/dev/lib/liblmdj_core_c.so` | PASS: 10 fixtures |
| `node --test packages/web-runtime-platform/test/project_bundle_reader.test.mjs packages/web-runtime-platform/test/protocol.test.mjs` | PASS: 28/28 |
| `npm --prefix apps/creator-web test -- --run` | PASS: 348/348 across 19 files for #374 review fix; Product Build integration remains deferred to #379 |
| `python3 scripts/version.py verify --version-file products/lmdj/version.json` | PASS: `1.0.37.0` |
| `python3 tests/build/version_test.py` | PASS |
| `scripts/core.sh build dev` | PASS with GCC 13.3 |
| `scripts/core.sh test dev fast` | PASS: 36/36 |
| `scripts/core.sh test dev stress` | PASS: 4/4 |
| `scripts/core.sh test dev full` | PASS: 77/77 |
| `scripts/core.sh coverage check` | PASS: 79/79; overall lines 81.75%, branches 67.29%, every per-object floor passed |
| Web Runtime Host non-browser suites | PASS: Python package/deployment/server suites, Node 28/28, native control/realtime/manifest 3/3 |
| Web Runtime Host formal Chromium gate | PASS: 20 passed, 1 WebKit-only case skipped; Stage 9 record/overdub/replay/reload lifecycle repeated 5/5 locally |
| WebKit capability gate | PASS: 2 passed, 14 non-capability cases skipped; structured limitation `UNSUPPORTED_WEB_RUNTIME` records missing `opfs`, `opfsSyncAccessHandle`, and `opfsWritableReplace` |
| `scripts/creator-web.sh proof` | PASS: reproducible production build, Creator 344/344, package 9/9, server 3/3, shared Platform 131/131 and packaged Playwright journeys; Sequence switch Host acknowledgement repeated 5/5 locally |
| `npm --prefix apps/architecture-portal run check:current` | PASS: 59 tests, 37 docs pages, 10 diagram sources/20 outputs, production build and 42 routes |
| `scripts/core.sh proof` | PASS: non-stress CTest registrations, schema/module/CLI/MCP parity, Golden WAV, failed-Attempt isolation, idempotent flush, next-Bar switch, owner-loss recovery, package acceptance and Assembly lock |
| `scripts/architecture-portal.sh version 1.0.37.0 canary` | PASS: snapshot regenerated from final source revision `f9b82d40517ddaafb757352ab92ea96916362af2` |
| `scripts/architecture-portal.sh check` after snapshot generation | PASS: immutable/current provenance, 59 tests, 37 current docs pages, 10 diagram sources/20 outputs, production build and 42 routes |
| Architecture Portal snapshot projection against the merge target | PASS on the staged tree, committed head and final PR CI |
| Full PR CI run `33047854982` at snapshot commit `147ab6cd3bff19d6bea0089ec3c8380b1dac98bd` | PASS: Docs, Portal, Core full/stress/ASAN/coverage/package, macOS, Web Toolchain, Web Runtime Host, Creator, deployment contracts, labs and aggregate PR Gate |
| Final PR CI run `33050896995` at head `4bce976c0d6878de9894d4d28c7cfab4a4bb0140` | PASS: every selected lane and aggregate PR Gate |
| Squash tree equivalence | PASS: final PR head and integrated `main` commit both have tree `433969283ab0a091caa1f6e6b2f954bc0d9cc91d` |
| Exact-main Core CI run `33058032797` at `1bc79006121cee77ba6d19e882890dc0aa95c95a` | PASS: package, Linux full/proof, ASAN full/stress, coverage, macOS/native, Web Toolchain, Web Runtime Host, Creator, Portal/projection, deployment contracts and labs |
| Stage 9 Issue acceptance | PASS: prerequisite #321, umbrella #265 and Tasks #266–#275 are `CLOSED / COMPLETED`; semantic gate #238 is also closed |
| Immutable `1.0.37.0 · canary` snapshot | generated under `apps/architecture-portal/versioned_docs/version-1.0.37.0/`, `static/versions/1.0.37.0/`, `versioned_metadata/version-1.0.37.0.json` and `versioned_sidebars/version-1.0.37.0-sidebars.json` |

## #375 pending-overlay source remediation — 2026-08-29

This source Task closes the SR-D13 M1 wiring gap without changing Project
Truth or persistence semantics. Application Facade exposes an immutable,
active-owner-only pending-event projection; Web Runtime Platform combines it
with the committed Runtime Snapshot; Audio Runtime schedules the newest view
at the next Bar and retires superseded same-boundary views without allocation,
deallocation, locking, Project access or journal access in the realtime
callback. A successful flush or Stop publishes the clean committed view, so a
pending event is audible from the next Bar and cannot survive as a stale or
duplicate overlay after commit.

The review fix makes the publication handoff linearizable: Audio Runtime marks
the mailbox generation callback-owned before a producer can replace it, so a
view already claimed for a Bar cannot be invalidated between dequeue and apply.
It also preserves pending events across an active-session BPM rebuild, schedules
a clean committed view on owner-loss sealing, and returns the durable committed
Pattern identity needed for exact Stop replay after a clean-publication failure.

Review Fix 2 additionally proves that a 90-BPM view claimed at frame `96000`
owns its transport basis: a concurrent replacement activates at `224000`, not
the stale 120-BPM boundary `192000`. If owner-loss clean publication itself
fails, the Host quiesces, stops, and clears the engine before owner abandonment.
Private gated testable libraries contain the deterministic hooks; the production
Audio/Web archives contain neither hook symbols nor embedded hook markers. The
generation allocator also rejects bit 63 before it can alias the claimed marker.

Review Fix 3 integrates that mailbox with #376 switch authority. A different
Pattern can supersede a pending overlay only when the control path presents the
exact generation, source Pattern, and activation frame it is authorized to
replace; ordinary different-Pattern overlap remains rejected. Stop uses the
same authority to cancel or replace a queued target and retains the durable
receipt for exact replay after publication failure. A BPM change while a switch
owns a boundary is rejected before Project mutation; a previously accepted BPM
view can still be deterministically superseded by the later authoritative
switch. The acknowledged boundary remains retained until the exactly-once
Facade flush finishes, preventing a clean old-Pattern republish from reverting
the target.

Review Fix 4 closes the remaining terminal-state races. A Stop receipt no
longer stores a one-use audio activation: after exact target cancellation, each
publication attempt derives the clean committed old-Pattern view from current
transport, so a replay after the original boundary gets a fresh next Bar while
retaining the same durable receipt and Project revision. Audio publication
masks the claimed bit consistently for queued and audio-owned generations,
including the frame-exact apply point; validated switch authority can therefore
reserve the next Bar while ordinary different-Pattern overlap remains rejected.
Cancellation is now an explicit telemetry terminal, with conservation
`accepted = applied + superseded + canceled + pending` across queued,
audio-owned, apply-point, and concurrent handoffs.

Review Fix 5 makes `pending` an explicit cardinality instead of an inferred
boolean: an audio-owned A and simultaneously queued B are two distinct pending
authorities and `pending_publications == 2`. Quiescent `stop()` moves every
distinct queued/audio-owned generation to canceled exactly once, including
when both exist, while cumulative Pattern counters survive a later `start()`.
Web Stop also closes its cancellation TOCTOU: if the target applies and clears
pending after the first current-generation read, the no-pending branch rereads
current generation and fails closed instead of claiming cancellation success.

| Source boundary | Fresh local evidence |
| --- | --- |
| Facade owner/generation/replace/reject/flush projection | PASS: `facade.sequence_surface` |
| Audio same-boundary newest-view wins, zero realtime allocation/free | PASS: `audio.realtime_engine` |
| Deterministic claimed-boundary race keeps onset zero and exact phase | PASS: `audio.realtime_engine` |
| Claimed 90-BPM transport basis and bit-63 generation boundary | PASS: `audio.realtime_engine` |
| Concurrent accepted = applied + superseded + canceled + pending_publications conservation | PASS: `audio.snapshot_publication_stress` plus deterministic two-pending component gate |
| Production Facade → ControlRuntime → Audio path | PASS: `host.web_control_runtime`; authoritative target supersedes the exact pending view; Stop cancels the target, fails closed if it applies between cancellation queries, and delayed exact replay derives a fresh boundary without a second Project mutation; boundary flush preserves the target |
| Owner-loss cleanup-publication failure stops and clears Runtime Pattern | PASS: `host.web_control_runtime` |
| Production Audio/Web hook symbol and embedded-marker exclusion | PASS: `build.project_io_test_hook_symbols` + unit contract |
| Shared Runtime Session | PASS: stopped switch authority ignores a later stale boundary without a second flush |
| Packaged Chromium switch journey | PASS: pending overlay → authoritative switch → exact boundary flush, plus switch-pending BPM rejection and Stop cancellation before target activation |
| Focused suite | PASS: 6/6 |
| `scripts/core.sh test dev full` | PASS: 79/79 |
| `scripts/core.sh test dev stress` | PASS: 4/4 |
| `scripts/core.sh proof` | PASS: 63/63 non-stress CTest plus schema/module/CLI/MCP/Golden/Sequence/package/Assembly proof |
| `scripts/architecture-portal.sh check` | PASS: 59 Portal tests, 37 current pages, 10 diagram sources/20 outputs and 42 rendered routes |
| Dependency / active-tree / version gates | PASS: vendored offline dependencies, active tree, product version tests and `1.0.37.0` verification |

This is local source evidence only. Version allocation and integrated Product
identity remain deferred to #379; the immutable Portal snapshot remains
deferred to #380. No push, Pull Request, merge, tag, Release, deployment,
publication or Channel promotion is established here. The physical/manual
rows below remain unchanged and unverified. Hard-crash pending-tail persistence
remains #373 and switch-boundary flushing remains #376.

## Physical and manual rows

| Platform | Journey | Status |
| --- | --- | --- |
| macOS Chrome | Pointer Sequence recording and subjective audio | `deferred / unverified` |
| macOS Chrome | Physical MIDI Sequence recording | `deferred / unverified` |
| macOS Safari | Pointer, audio and recovery | `deferred / unverified` |
| iPadOS Safari | Touch ergonomics | `deferred / unverified` |
| iPadOS Safari | Background/lock-screen owner-loss recovery | `deferred / unverified` |

Automation does not convert any physical row into a pass.

## Post-delivery remediation source evidence

| Finding | Local source evidence | Remaining boundary |
| --- | --- | --- |
| M2 / #373 | RED: the real `SIGKILL` restart journey found a candidate without the two acknowledged unflushed events, while the Project I/O test could not compile without durable-tail API/metadata. Review RED: after F1 append/execute failure, a successful cumulative F2 left F1 recoverable; apply could double-mutate and overwrite F2's newer same-key event. Complete-line checksum/sequence/canonical corruption also returned generic path/detail. Review Fix 2 RED: with F0…F31 equivalent retries durable before completion, F0 completion left F1…F31 incomplete; the same gap followed an ambiguous post-commit F0 error plus F1 retry. Review Fix 3 RED: after F0 manifest/receipt commit plus completion failure, an accepted durable A+B/A+A'+B tail with no later flush exposed committed A again; equivalent-only A could create a second candidate/revision. Integration RED: F0(A) completion mutated durable F1(A+B) to residual B, so exact F1 replay was rejected while residual-only collision could be accepted. Precedence RED: incomplete F0(A-old) plus acknowledged tail A-new+B reported three events and apply let A-old overwrite the newer tail value. GREEN: focused 2/2 passes with semantic bidirectional coverage—later completion resolves covered earlier batches; earlier completion resolves exact-value-covered later retries and subtracts the same exact committed batch from the current pending tail; non-equivalent flushes/tails retain only new/different residual in canonical order. Immutable original command payload drives exact replay/collision while a separately versioned recovery residual drives reconcile/apply; effective recovery merges incomplete residuals in flush order and durable tail last, so status/list/apply share the unique canonical A-new+B batch. Reload, fail-safe v2 parsing, legacy recovery-only parsing, and 32-thread completion order are covered. Recovery/apply remains one revision and preserves newer same-key values; equivalent-only work produces no candidate. Torn and complete-line corruption retain exact bytes and uniform actionable evidence. Fresh precedence verification passes focused 2/2, full 79/79, stress 4/4, Web 54/54, Creator 344/344 and Portal 59/59 with 37 pages/10 diagram sources/20 outputs/42 routes, plus dependency, active-tree, version and production hook-symbol gates. | This is functional source evidence only. #379 owns accumulated Module/Host/Product identity and complete integrated automated acceptance; #380 owns the clean exact-main immutable snapshot. The five #360 physical/manual rows above remain `deferred / unverified`. |

The #373 Task does not rewrite the historical `1.0.37.0` evidence table or
promote the candidate. Push, Pull Request, merge, remote CI, Product tag,
Release, deployment, publication and Channel promotion are not implied by this
local source gate.

## External state

| Transition | Status |
| --- | --- |
| Push | completed; final PR head `4bce976c0d6878de9894d4d28c7cfab4a4bb0140` was pushed to the short-lived branch |
| Pull Request | completed; [#334](https://github.com/endaye/lmdj/pull/334) passed final full CI and was merged on 2026-08-27 |
| Merge | authorized and completed; squash commit `1bc79006121cee77ba6d19e882890dc0aa95c95a`, exact-main CI `33058032797` PASS, and Issues #265 and #267–#275 closed as completed |
| Product tag / Release | not authorized / not created |
| Runtime deployment / publication | not authorized / not performed |
| Channel promotion | not authorized / not performed |

Each transition remains a separate authorization and verification boundary.
