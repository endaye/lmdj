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

Documentation impact: required. Current routes updated by this Task include
Assembly, Project and Bundle Contracts, Core Modules, Hosts, storage, Web
Runtime, Native Audio, input, workflows, capability map, versioning and
testing/proof. Source diagrams for the product, Core, Project I/O, Cooker,
Facade, Audio Runtime and Web Runtime Platform are updated in the same Task.

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
| Concurrency | closed settings-only selective rebase, Sample mutation rejection, writer lease observer/busy and fail-closed unknown commands |
| Timing | Audio Runtime integer BPM anchor and Bar boundary; no Host quantizer, floating musical clock or fallback sequencer |
| Switching | old Pattern remains active until the acknowledged next-Bar boundary |
| Recovery | owner-loss artifact, fingerprint-gated original Pattern, explicit valid destination or discard |
| Hosts | CLI/MCP parity, Native CaptureWriter and Web Runtime/Creator journeys use the Application Facade |
| Evidence privacy | reports contain semantic state, session/receipt identities, revisions and counters, never samples or local paths |

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
| `npm --prefix apps/creator-web test -- --run` | PASS: 344/344 across 19 files |
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
| M2 / #373 | RED: the real `SIGKILL` restart journey found a candidate without the two acknowledged unflushed events, while the Project I/O test could not compile without durable-tail API/metadata. GREEN: focused 2/2, Core fast 38/38, full 79/79 and stress 4/4 pass with monotonic canonical tail reload/consumption, actionable torn-tail rejection, signal-verified `SIGKILL`, a two-event `owner_lost` candidate, preserved recovered identity/order, and exactly one Project revision increment. Portal check passes 59/59 tests, 37 current pages, 10 diagram sources/20 outputs and 42 routes; dependency, active-tree, version and production hook-symbol gates pass. | This is functional source evidence only. #379 owns accumulated Module/Host/Product identity and complete integrated automated acceptance; #380 owns the clean exact-main immutable snapshot. The five #360 physical/manual rows above remain `deferred / unverified`. |

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
