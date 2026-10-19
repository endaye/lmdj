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
