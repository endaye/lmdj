# Stage 9 Sequence Recording Acceptance — 2026-08-23

## Current status

Product Build candidate `1.0.37.0` implements Project v3 event-only
Sequence recording across the Core, CLI/MCP/Native/Web Hosts and Creator.
This ledger records only evidence actually produced from the local candidate.
Draft PR [#334](https://github.com/endaye/lmdj/pull/334) exists at the pushed
Task 8 head; its Draft routing, Docs/static, CI contract and PR Gate checks
passed. Task 9 is committed locally and the immutable Portal snapshot has been
generated from that exact revision. Push, full Ready-PR CI, merged-main,
publication and promotion evidence remain pending until those boundaries
occur.

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
| Assembly lock SHA-256 | `0aaab0918ad53a43a5e12b3d42a35ef38142343738637516d544d66ca21bef85` |
| Portal snapshot metadata SHA-256 | `a73a85981fd88c07752310182bb0cb3237238fa6ff161e04e7e05de194e28c66` |
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

## Local verification

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
| `scripts/core.sh test dev full` before Task 10 | not a final pass: 68 tests passed; release-audit tests correctly require the absent `1.0.37.0` snapshot, while three filesystem/proof cases require the planned ext4 clean-worktree rerun |
| Web Runtime Host non-browser suites | PASS: Python package/deployment/server suites, Node 28/28, native control/realtime/manifest 3/3 |
| Web Runtime Host formal Chromium gate | PASS: 20 passed, 1 WebKit-only case skipped |
| WebKit capability gate | PASS: 2 passed, 14 non-capability cases skipped; structured limitation `UNSUPPORTED_WEB_RUNTIME` records missing `opfs`, `opfsSyncAccessHandle`, and `opfsWritableReplace` |
| Creator build and `scripts/creator-web.sh test` | PASS: production Vite build, Creator 344/344, package 9/9, server 3/3, shared Platform 131/131 |
| `npm --prefix apps/architecture-portal run check:current` | PASS: 59 tests, 37 docs pages, 10 diagram sources/20 outputs, production build and 42 routes |
| `scripts/core.sh proof` in the ext4 Task 10 verification worktree | PASS: 61/61 non-stress CTest registrations, schema/module/CLI/MCP parity, Golden WAV, failed-Attempt isolation, idempotent flush, next-Bar switch, owner-loss recovery, package acceptance and Assembly lock |
| Core full/coverage and Creator packaged Playwright proof | pending final clean Task 10 revision |
| `scripts/architecture-portal.sh version 1.0.37.0 canary` | PASS: snapshot generated from Task 9 revision `e0f2de5b6453855f6def6407f962de8f8442c210` |
| `scripts/architecture-portal.sh check` after snapshot generation | PASS: immutable/current provenance, 59 tests, 37 current docs pages, 10 diagram sources/20 outputs, production build and 42 routes |
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

## External state

| Transition | Status |
| --- | --- |
| Push | authorized; Tasks 2–8 pushed at `fc7827d4946894da8ecb6822bdb725c13cccb402` |
| Pull Request | authorized; Draft [#334](https://github.com/endaye/lmdj/pull/334) open with `ci:full`; Ready conversion pending final evidence |
| Merge | not authorized / not performed |
| Product tag / Release | not authorized / not created |
| Runtime deployment / publication | not authorized / not performed |
| Channel promotion | not authorized / not performed |

Each transition remains a separate authorization and verification boundary.
