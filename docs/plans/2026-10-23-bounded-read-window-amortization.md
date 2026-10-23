# Bounded read windows amortize the OPFS per-call cost (#2477)

## Premise

`thirty-minute recording Save and bind preserve full identity through two page
reopens` (`tests/platform/web/audio/realtime_audio_worklet.spec.mjs`) exceeds
its unchanged 180 s case budget on every CI Linux host. Since 2026-10-21 it has
failed `web_runtime_host` and `web_toolchain_conformance` on netcup and on the
en-home overflow runner.

On the en-home runner host, current main `469f4ad` took 238 s; for that
measurement only the case budget was raised and per-RPC timing added, neither
committed. Each full Wasm verification of the 345,600,056-byte file took
9.1–12.5 s, and there are 23 of them across the six pages. The browser's own
SHA-256 of the same bytes takes 0.48 s. The vendored PicoSHA2, built em++ `-O3`
under Node 26 on the same host, hashes those bytes in 64 KiB chunks in 1.49 s
(220 MiB/s). The cost is therefore the read path, not hashing.

All three bounded loops read through `ProjectStorageRangeReader::read_range` in
64 KiB windows, about 5,274 calls per file:

- recording verification for Save, bind and open (`project_store.cpp`, `matches`);
- recording scan for metadata (`ProjectStore::scan_performance_recording`);
- discovery inventory (`project_bundle_transfer.cpp`, `read_inventory_entry`).

Each OPFS call pays an Asyncify suspend, a per-segment directory lookup,
`getFileHandle`, `getFile`, `slice` and `arrayBuffer`. That fixed cost of
roughly 1.5 ms per call dominates. It also stalls Creator startup discovery for
10–20 s for every thirty-minute recording.

## Decision

Enlarge the three windows from 64 KiB to 1 MiB. Measured on the same host, the
case takes 68 s at 1 MiB and 57 s at 4 MiB. At 1 MiB a verification is
2.5–2.9 s and is bounded by SHA-256, so 4 MiB buys about 0.4 s at four times the
buffer. The window stays a fixed heap buffer independent of recording length.

Unchanged: every byte is still hashed, and the pre/post length, EOF, short-read,
zero-progress and invalid-count checks remain. The no-fallback rule, writer and
history ownership, the 64 MiB transfer limits and the legacy complete-read path
are unchanged. No case or RPC budget, journey leg or assertion is changed in
the failing test.

Scan consumers (`WavMetadataInspector` via the Facade metadata reader) are
streaming and accept any span size. The `scan_performance_recording` API never
promised 64 KiB spans.

## Tests

The suites below pin the window: `≤ 65536`, `maximum_request == 65536`, a fault
at the second window, `calls == 3`, or `range_calls == 4`. They used fixtures of
131,089 bytes (2 × 64 KiB + 17) and 192,124 bytes (2 × 64 KiB + 61,052) to cross
two window boundaries. A 1 MiB window with the same fixtures would collapse each
case to one window and silently drop that coverage. Each fixture therefore keeps
its shape at the new window: 2,097,169 bytes (2 × 1 MiB + 17) and a
2,158,204-byte WAV (2 × 1 MiB + 61,052; 539,537 frames). Every new literal is an
independent Python `hashlib`/`struct` value, and the same generator reproduces
each old literal exactly:

| Fixture | Old | New |
| --- | --- | --- |
| pattern `ab\0\xffcdxy` | `d257cf3b…` | `766a883d…` |
| `'x'` | `e3c33f1a…` | `647720d9…` |
| WAV 48 kHz | `985ee1bb…` | `b29079c0…` |
| WAV 32 kHz | `62aedd33…` | `e120c174…` |
| WAV last byte changed | `6517a13a…` | `1432d250…` |
| WAV `XIFF` | `61347c7a…` | `1c4adbe8…` |

The two Web witnesses now seed their fixture with `replace_complete` instead of
`create_immutable`. In this test build the OPFS test observer writes immutable
files two bytes per call to exercise the short-write loop, which keeps its own
dedicated test. Through that path the 131,089-byte seed already took ~40 s per
page on the en-home host (measured on unpatched main), and a 2 MiB seed exceeds
the 180 s case budget. The witnesses assert nothing about how the bytes were
written; their immutable-write counters are sampled after seeding. With one
complete write, the 2 MiB scan witness completes in under 5 s.

Window bounds, the fault offset, the truncation point and the EOF offsets move
to the 1 MiB equivalents. `project_bundle_transfer_test`'s default per-call cap
moves to 1 MiB too, so its full reads are not silently turned into short reads.
Fixtures that pin no window are left alone: the Creator, protocol, runtime-session
and realtime-worklet uses of the 192,124-byte WAV.

Defect caught: a regression to small windows fails
`performance_recording_verification_test` at `maximum_request == 1048576` and
the three-window count. The failing browser case itself returns under 180 s.

## Exact declared files

- `packages/project-io/src/project_store.cpp`
- `packages/project-io/src/project_bundle_transfer.cpp`
- `tests/core/project_io/performance_recording_verification_test.cpp`
- `tests/core/project_io/performance_recording_scan_test.cpp`
- `tests/core/project_io/project_bundle_transfer_test.cpp`
- `tests/core/facade/performance_recording_metadata_test.cpp`
- `packages/web-runtime-platform/test/recording_metadata_query_test.cpp`
- `tests/platform/web/project_io/project_io_web_test.cpp`
- `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/platform/storage.mdx`
- `docs/plans/2026-10-23-bounded-read-window-amortization.md`

## Verification

- Owning Native suites for the four Core tests above, plus the metadata query
  test, on Linux.
- Mutation: restore the 64 KiB windows in a rebuilt artifact. The owning
  Native assertion must fail at the window bound, and restoration must pass.
- Formal Wasm audio runtime build, then the Chromium Project I/O conformance
  (scan, WAV metadata and Facade metadata through two reopens) and the
  thirty-minute case on the en-home CI-class host under the unchanged 180 s
  budget.
- `scripts/docs-site.sh check`.

## Version Management

Version impact: compatible internal Project I/O PATCH debt under #2237. No
API/ABI, Contract, Project Truth, key, dependency, manifest, Product, Assembly,
Build or snapshot change.

## Documentation Impact

Documentation impact: required — `/core/modules/project-io/` and
`/platform/storage/` state the 1 MiB windows, the reason and the new composite
OPFS fixture size.
