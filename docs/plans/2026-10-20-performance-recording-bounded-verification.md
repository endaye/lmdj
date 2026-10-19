# Bounded verification before saving or binding Performance audio

## Premises and current evidence

Integration main is `1c4462aa8436f81da1db2a9e6420d94f0e84ccb4`.
This isolated prerequisite starts at Draft #2408,
`26a31132470e3a46dcd24b1ecd0885f970430cb4`. Live #2112, #2135,
#2237 and their comments, and all17 open Draft heads were refreshed. No
successor implements this fix. Main retains the same whole-file verifier;
its intervening release work does not change this premise or lift the freeze.

The unpublished U08b source checkpoint `aebb0e6547b49b4f2831389075af0243ae472050`
failed its actual thirty-minute WAV browser journey: Wasm emitted
`Aborted(OOM)` during fixture Save, before metadata/UI verification. Retain
the original trace and terminal failure under
`take-audio-initial-target-chromium`; it is not a metadata-query pass.

| Premise | Disposition before edits |
| --- | --- |
| Metadata must decode the complete recording | False: #2401/#2402/#2403/#2406/#2408 already provide bounded raw scanning, parsing and worker-owned queries. Preserve them. |
| Save/bind already use bounded recording verification | Outstanding: `verify_managed_wav_artifact` calls `describe_artifact`/`read_complete`; OPFS allocates the full file, then C++ duplicates it into a vector. A345600056-byte WAV exceeds the fixed512MiB heap during those simultaneous allocations. |
| Fixing the OOM permits weaker integrity checks | False: verify the complete digest, byte length before/after, and EOF under the existing writer/history ownership. Short successful range reads must continue; zero progress, invalid counts, changed length, extra bytes and read errors fail without publishing. |
| Every custom platform implements the optional range companion | False: preserve the existing complete-read behavior for legacy platforms without the companion. Production Native/OPFS implement it. Errors from a present companion must never fall back to a whole-file read. |
| This repair should include the Take UI | False: it is an independently reviewable producer prerequisite. Keep the unpublished consumer commit and original failure intact; rebase it only after this layer is verified. |

## One Task / declared files

1. `packages/project-io/src/project_store.cpp`
2. `packages/project-io/CMakeLists.txt`
3. `tests/core/project_io/performance_recording_verification_test.cpp`
4. `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`
5. `apps/docs-site/docs/core/modules/project-io.mdx`
6. `docs/plans/2026-10-20-performance-recording-bounded-verification.md`
7. `CMakeLists.txt` — register the new native test executable in coverage inputs.

Only the save/bind verifier changes; no public interface, storage schema,
writer ownership, general Asset importer, scheduler or heap budget changes.
No PCM decoding or WAV format validation is added to this raw identity check.

## Implementation and verification

Use the existing optional range reader, one64KiB heap buffer and incremental
SHA-256. Keep existing invalid-reference and missing/unverified failure shapes.
Keep legacy no-companion behavior unchanged. Preserve the existing locks,
recovery, command identity, save/bind replay and unknown-outcome semantics.

- Baseline: configure Native dev and run the original Performance lifecycle,
  recording scan and storage platform tests before product edits.
- Lowest owning tests: real Native-backed save and bind, exact reference and
  reopen/replay; reject complete audio reads while accepting metadata reads.
  Separate tests cover short reads, tail corruption, wrong/truncated/growing
  lengths, EOF disagreement, range failure/zero/oversized count, no-companion
  compatibility, and no fallback after a present reader fails. Failed Save
  retains the stopped draft and revision; failed bind leaves null binding.
- Prove the bounded-read assertion RED against the unchanged verifier, then
  GREEN against the rebuilt fix. Preserve actual compilation/terminal exits.
- Native owning persistence/recovery suites, including existing fault matrix,
  lifecycle and scan tests; dependencies/source ownership and complete diff.
- Real OPFS through formal Wasm: extend the existing metadata RPC browser file with a
  thirty-minute physical WAV Save/bind journey, exact digest/length/frames,
  two fresh reopens and physical readback. Retain original cases and deadlines;
  metadata RPC keeps its original30-second budget. No device-PCM claim for
  the controlled fixture. Do not enlarge heap or weaken the failed U08b test.
- Full Portal check for the changed module page, staged/committed new-file
  ownership, final PR body lint/declarations and committed range classification.
- Official clean-source package uses an unpublished atomic checkpoint only
  after owning source checks pass. Publish Draft only after browser checks.

## Version Management

Version impact: compatible Project I/O PATCH debt, deduplicated under #2237
without reducing higher debt. No public ABI/Contract, manifest, dependency,
Product Build, Assembly or snapshot allocation changes.

## Documentation Impact

Documentation impact: required — `/core/modules/project-io/`. Explain which
write-admission path now uses bounded integrity verification, legacy capability
compatibility, and the unchanged distinction from WAV metadata/completeness.

## Shipping boundary

One Conventional Commit, push and Draft successor of #2408 on the single
linear stack. Independent current-head review remains pending. No merge or
auto-merge, release/tag/publication/deployment/Channel or Git cleanup.
This prerequisite does not finish U08b, U08c, #2135 or the #2112 goal.

## Source checkpoint evidence

Original Native baseline3/3 passes. The new bounded observer rebuilt against
the unchanged verifier fails at its positive Save assertion (CTest exit8),
then the rebuilt fix passes. Final owning persistence10/10 and the existing
writer lease stress test pass. Dependency, Runtime/Host source boundaries
and Core script policy pass. An initial Host-boundary command omitted its
required HOST_ROOT argument; retain that usage failure and the corrected
explicit-root PASS without changing source or relaxing any gate.

Pinned Emscripten6.0.5 formal Wasm build and the new real Chromium journey
pass. Save and bind each publish a physical345600056-byte WAV; three fresh
pages per admission (prepare plus two reopens) retain the exact digest,
86400000 frames/48000Hz/stereo, complete physical readbacks and512MiB heap.
No original RPC or test deadline was increased. This is controlled OPFS audio,
not device-captured PCM. Original U08b OOM evidence remains retained.

Full Portal passes179 tests,52 pages,10 diagram sources/20 outputs and50
routes/internal links. Full original-plus-new selected Chromium4/4 and supported
OPFS WebKit3/3 pass. Each browser retains nine original metadata physical
reports plus six long-recording reports; all JSON was read back. The formal
build enables its existing conformance harness; a production Creator build/
package is a separate postcheckpoint check. Device/hearing and the Creator
consumer journey are not established by the formal harness.

An initial declaration command omitted `--declaration-only` and started the
broad advisory local preflight. Only its verified owned process subtree was
terminated; terminal-15 is retained, not PASS. The corrected declaration-only
check passes. Source checks and complete staged inspection remain required.
Official production build/package follows the unpublished clean checkpoint;
its result must be recorded before Draft publication. Independent review,
complete candidate/device evidence and historical WebKit findings remain open.
