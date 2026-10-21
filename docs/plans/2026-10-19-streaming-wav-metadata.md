# #2403 main integration premises, before edits

Current main 0f1ef312dea10bd18750cba80f09e01c445bdded; original source 4bd64adb8dfd92a40cdb1d9c19e5ea78f336c20c.

- B0 raw ranges and full bounded Performance recording integrity are already delivered by #2432 / 9b48e23f and #2434 / 0f1ef312. Reuse actual main code; do not repeat or import ancestor stack commits.
- Bounded metadata remains outstanding on main. The complete Cooker public include inventory/CMake contains no streaming inspector; sample_analysis.cpp::inspect_wav still calls the known-present decode_wav and allocates complete PCM. Its exact function body is the positive/negative discriminator, not an empty name search.
- All seven existing inputs of the original eleven-file delta equal the original parent7719e295; four new paths are absent. Main's unrelated COUNT-IN withdrawal remains preserved. Re-home the existing pure parser and retained complete owning proofs only.
- Preserve the unchanged decoder's strict RIFF length/chunk extents/padding, unique16-byte PCM fmt and nonempty data, PCM16 mono/stereo44.1/48k, unknown chunks/data-before-fmt. Parser complete-input count and terminal boundary remain necessary; a header alone must fail. Literal independent metadata expectations constrain decoder/parser shared defects.
- Source inspection confirms a fixed16-byte header/counters, no payload/view retention, sticky typed failure and no successful-parser heap allocation. Full hash/owner verification is still supplied separately by the already-merged scan. Actual three-variant Web composition must discard metadata after a late digest mismatch.
- Live #2135 and comments retain raw/scan/format/Facade/SDK/Host/Take boundaries. Original #2403 and successor #2406 are unmerged, not delivering the missing main parser. Existing worker/cancellation/owner-retirement and duration consumers stay separate downstream Tasks.
- Original Native/C++ grammar/allocation checks, rebuilt allocation/truncation/shared-defect controls and full Chromium/WebKit selections remain declared. Old B0 WebKit lifecycle failures, the original corrected harness failure and candidate/device/hearing/full-lane gaps remain historical evidence.
- One Task, eleven declared files, one Conventional Commit. User authorizes sequential ordinary protected integration and proven-safe cleanup. Preserve original published stack refs, #2430 pending discussion exception and #2433/frozen release paths. No release/tag/Runtime deploy/Channel action.

## Current integration verification

- Baseline current-main Sample Analysis/Project Cooker two CTests PASS; final production and no-voice-DSP Native builds plus original complete owning3/3 CTests PASS1.273s. New inspector consumes a real345600044-byte30-minute stream from a reused64KiB buffer with exact86400000 frames and zero successful-parser heap allocations.
- Three actual rebuilt controls: PCM allocation assertion88 RED; partial-input assertion207 RED after bypassing completeness/terminal guards; shared decoder/parser wrong-rate metadata first passes parity then literal-rate assertion75 RED. Temporary driver retains every original call. Every snapshot restored exactly with strictly newer mtime, source recompilation confirmed and owning GREEN; final production/no-DSP rebuild and original complete selection GREEN. Decoder/driver unchanged in final source.
- Independent producer make_fixtures.py at current main (SHA256b4749d62abe0ca38658e1bcb97fe0af9a99e38983d9c587c81d5b7fcb451620e) supplies the seven accepted fixture identities/counts; fresh Python struct/hashlib independently reproduces all three192124-byte Web fixture digest/layout constants.
- Pinned Emscripten6.0.5/Node26 configure/build/build-project-io PASS, including no-hook production link. Complete unchanged owning Chromium7 PASS68.737s, supported OPFS WebKit2361 four PASS64.632s; zero skipped/flaky/retries, original half-stack/timeout/recovery/owner/range/scan legs retained. Each browser retains and read-backs nine exact reports/physical full digest/length/prefix/tail results and nine closed pages: valid, unsupported, late mismatch each reopen twice. Mismatch publishes no metadata or verified receipt.
- All ten implementation inputs byte-identical to original4bd64adb throughout staged Native/Wasm/browser proof; only this integration plan differs. Full Portal179tests/53pages/51routes/internal links PASS66.145s; dependencies, original Web timeout policy, staged ownership76 and diff checks PASS. No clean Product distribution or full candidate claim.
- Precommit main refresh 0f1ef312dea10bd18750cba80f09e01c445bdded; 0 intervening paths, no Task overlap; seven governance hashes unchanged. Original2403 reviews/threads0. Current user authorizes ordinary protected merge and safe cleanup; exact-head independent review remains required before integration.
- Original corrected browser fixture failure and old failed shared-mutant driver remain historical records. Older B0 WebKit lifecycle failures retain unexplained status. Complete batch/candidate, sanitizer, device/hearing and public async/Host consumer remain unverified; no new process-pitfall incident, release or version allocation claimed.

Original records/freeze statements below remain historical evidence.

---

# Streaming WAV metadata — #2135 B

## Premises before edits

Main refreshed to `8c361623f2c1bf32460c32793a33a4d7e204fb7f`; Task parent is
Draft #2402 / `7719e29576c3af6f50a74ac18b629f3400b14b53`. Live #2112/#2135,
comments and all fourteen open Drafts were inspected; no successor owns this
parser. The new isolated `feat/streaming-wav-metadata` starts clean with ten
actual tracked symlinks. One writer, no sub-agents.

| Premise | Disposition |
| --- | --- |
| Bounded recording input and owner verification are missing | Already delivered on the stack: #2401 provides raw ranges; #2402 provides full bounded digest/length/owner/revision/binding verification with provisional consumer bytes. Reuse them. |
| Existing WAV metadata inspection is bounded | False: sample_analysis.cpp::inspect_wav invokes decode_wav, allocating the complete PCM vector. The existing metadata result needs only rate/channels/frames. |
| A metadata-only parser may accept a different format | No. Preserve wav_reader.cpp's strict RIFF length, chunk extent/padding, exactly one16-byte PCM fmt and one nonempty aligned data chunk, PCM16 mono/stereo at44.1/48k. Unknown chunks and data-before-fmt remain supported. |
| A header proves complete input | False. Require the declared complete input count and valid terminal chunk boundary before finish succeeds. This parser proves format/metadata only; #2402's final receipt separately proves Artifact/owner. |
| A new synchronous Performance query can run safely on Control | Unproven and not suitable for long recordings: current Performance queries call Application synchronously inside the serialized Control dispatch. No generic long-read executor was found; existing Pattern transport worker serves its own durable lifecycle. Facade/SDK/Host still require an explicit asynchronous/cancellation/owner-retirement design, without relaxing real-time admission or taking over recording writers. This Task supplies their necessary pure bounded parser. |

Storage/cooker/Facade premises are unchanged at refreshed main. Its independent
COUNT-IN withdrawal #2396 remains an integration divergence; preserve the owner
freeze and the linear Draft stack.

## One Task / declared files

1. `packages/project-cooker/include/lmdj/cooker/wav_metadata_inspector.hpp`
2. `packages/project-cooker/src/wav_metadata_inspector.cpp`
3. `packages/project-cooker/src/sample_analysis.cpp`
4. `packages/project-cooker/CMakeLists.txt`
5. `tests/core/cooker/wav_metadata_inspector_test.cpp`
6. `tests/platform/web/project_io/project_io_web_test.cpp`
7. `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
8. `apps/docs-site/docs/core/modules/project-cooker.mdx`
9. `apps/docs-site/docs/core/modules/project-io.mdx`
10. `apps/docs-site/docs/platform/storage.mdx`
11. `docs/plans/2026-10-19-streaming-wav-metadata.md`

Expand before another path. No decoder/PCM/DSP policy, storage/writer behavior,
Facade/SDK/Host request, Project Truth/format, CI or manifest change. B and Take
duration UI remain outstanding; do not publish an unknown label as delivery.

## API and implementation

`WavMetadataInspector(total_byte_length)` accepts arbitrary contiguous chunks
through `feed(span<const byte>)`, then `finish()` returns the existing
`WavMetadata`. It retains only a16-byte header buffer, counters, format fields
and an optional sticky typed error. It retains no input view or PCM/JUNK/data
payload. Empty feeds are identity operations; failure is sticky. Premature
finish is failure; no reset or implicit retry. Extra bytes are rejected.

The RIFF/header/fmt/payload/padding state machine supports every split boundary
and validates the same grammar as the unchanged decoder. Format validation is
deferred until all structural chunks are checked, preserving error priority.
Rate/channels/frame results use the actual fmt and data chunk, not total file
length, event cursor, elapsed wall time or an unchecked header hint.

Route existing inspect_wav(span) through this parser so it no longer decodes
PCM. Preserve its public shape and strict format acceptance; decode_wav itself
remains untouched. A later Facade consumer must retain a parser error while
continuing #2402's complete hash, and only publish metadata/unsupported format
after the final verification receipt succeeds. Parser success alone grants no
Artifact integrity, capture completeness, owner authority or physical-close
receipt.

## Verification / defect ownership

- Baseline the original sample-analysis and Project Cooker suites before edits.
  Preserve all original tests/thresholds and the unchanged decoder as an
  independent grammar comparator, alongside literal expected metadata/errors.
- Native streaming suite covers every split of valid and malformed input,
  one-byte/empty/reused windows, data-before-fmt, unknown odd padded chunks,
  duplicates, missing fields, unsupported encodings, byte-rate/alignment errors,
  bad extents, RIFF length, missing padding, partial/extra input and sticky
  failure. Every valid result has literal rate/channels/frames assertions.
- Feed a real30-minute48k stereo PCM16 stream (345600044 bytes) from a reusable
  fixed buffer with no heap allocation during successful parsing. Instrument
  allocation with the repository's existing test-binary operator-new pattern;
  do not allocate the recording in the fixture or use a forged span. The
  existing full-span inspect path must also allocate no decoded PCM.
- Mutate inspect_wav back to decode_wav and mutate the complete-input guard:
  each owning allocation/truncation assertion must fail on an actual rebuilt
  artifact. Restore exact source with strictly newer mtime and read rebuild
  exits before claiming restored GREEN. Never commit a mutant.
- Real C++/Wasm/Asyncify/OPFS scan-to-parser composition: a multi-window silent
  WAV with odd JUNK has exact frames/rate/channels and independent full digest;
  verified unsupported encoding is separate from a late digest mismatch, which
  must publish no metadata. All three cases actually close/reopen twice and
  retain every selected common parity/recovery, ownership and earlier range /
  scan journey with original budgets and stack gate. Persist and read back
  successful JSON by output path; use the WebKit protocol wrapper from outset.
- Production Native (including no-voice-DSP variant), pinned Wasm production
  link, full Portal, dependencies, ownership and exact body/declaration checks.
  Heavy Native/Wasm, browser and Portal windows run serially. Candidate/full
  lanes, physical devices and hearing remain unverified; old WebKit lifecycle
  failures remain an open review finding without a cause/fix claim.

Refresh main/relevant successors before commit/publication. Inspect the full
staged diff, exact committed paths and final worktree. One Conventional Commit,
push and Draft successor of #2402; no merge/auto-merge, release/tag/deployment/
Channel or Git cleanup while frozen. Independent current-head review PENDING,
no self-waiver. Record a pitfall only for a qualifying non-product cause.

## Version Management

Version impact: additive Project Cooker C++ API MINOR debt; existing full-span
inspection's allocation reduction is compatible and deduplicated in that domain
under #2237. No Module dependency, Project/Facade/SDK/cross-language Contract,
manifest, Product/Assembly/Build or snapshot allocation.

## Documentation Impact

Documentation impact: required — `/core/modules/project-cooker/`,
`/core/modules/project-io/`, `/platform/storage/`: streaming grammar, complete
input and bounded lifetime, scan/format evidence distinction and the remaining
async query/Host consumer. No dependency or diagram edge change.

## Task evidence and precommit refresh

Main refreshed again before commit to the same
`8c361623f2c1bf32460c32793a33a4d7e204fb7f`; fourteen live open Drafts and
#2112/#2135/#2237 still have no parser successor. No intervening source change
affects the premises. Main COUNT-IN withdrawal remains a future integration
reconciliation; it does not unfreeze this stack.

Original Native baseline2/2 and final owning3/3 pass; production and no-voice-DSP
Cooker builds pass. Rebuilt PCM-allocation and premature-finish mutants fail their
respective owning assertions. A shared sample-rate mutation passes decoder parity
then fails the literal mono rate oracle. Snapshot restores have newer mtimes,
confirmed source compilation and successful restored owning tests. The first
shared-mutant driver failed on unused functions before reaching tests; the corrected
driver retains all calls and supplies the actual semantic RED.

Pinned Wasm/production-link build passes. Initial Chromium6/7 passed the six old
selections but the new expected format refusal used the harness-reserved error
field. The fixture now uses failureCode; generic runtime-error detection remains
strict. Final full unchanged selection: Chromium7/7 and OPFS WebKit4/4 pass.
All three WAV variants complete prepare plus two real close/reopen/inspect legs.
Output-path JSONs/attachments were read back: nine exact reports and independent
physical full digest/length/prefix/tail checks per browser; new-action stack peak
68564/262144. The mismatch publishes no parser metadata or verification receipt.
No thresholds, deadlines, old assertions or journey legs were reduced. Failed
logs/traces are retained separately; old B0 lifecycle findings remain unresolved.

Dependency and original Web timeout-policy checks pass. Full Portal, staged
ownership, exact body/declaration and final committed-range classification remain
mandatory before Draft publication. Independent current-head review stays PENDING;
B/Facade/SDK/Host and UI acceptance remain OPEN. No version identity allocated.

Final full Portal check passed before staging:179 tests,52 page validations,
10 diagram sources/20 outputs, typecheck, production build and50 routes/internal
links. This validates current inherited inputs, not a new release allocation.
