# Sound Set audition: independent golden verification

Related: [#994](https://github.com/endaye/lmdj/issues/994).
Status: design only; the audio verification described below remains unimplemented.

## 1. Refreshed premises

Inspected base: `1f20e8f63e6a7ed333fa1de1a5503dbb88ce59b7`, refreshed
2026-10-09. The live Issue remains open with no comments. Its original finding
predates two deliveries; retain that history without repeating delivered work:

| Original premise | Current disposition and evidence |
| --- | --- |
| A new production offline audition entry point is necessary. | Already delivered through existing APIs. Device-free `RealtimeEngine::render` dates to `4e508fc3b048bc871049ff302668bd27a46edbe4` (#74). [#1001](https://github.com/endaye/lmdj/pull/1001), merged as `e8c583b4d352d20aa4e7738713333f8359320974` on 2026-09-08 at 18:04:41Z, added reserved audition publication and a direct render test. [#1003](https://github.com/endaye/lmdj/pull/1003), merged as `7337ccef11e064c53aa39fab90fd0ef562b4daf4` at 18:04:59Z, supplied typed Facade prepared PCM. Both merges followed #994's 16:15:07Z creation. Add no production renderer. |
| Any wrong rate or gain passes all existing tests. | Overbroad. `sample_analysis_test.cpp` locks a 44.1 kHz resample vector, last-frame clamp and stereo order. `audition_renders_its_own_bytes_while_the_project_bank_stays_current` checks absolute 0.25-input attack samples. These assertions remain valuable. |
| Real Sound Set audition lacks an independent full-waveform integration assertion. | Still outstanding. Typed `soundset_facade_test.cpp` checks artifact identity and source/prepared geometry. Engine audition tests use handcrafted input. The existing golden script and offline test explicitly cover the Project Pattern one-bar case, not the Facade producer-to-reserved-audition chain. |

Presence controls were the existing one-bar golden assertion and actual engine
audition render test. Inspection included the owning Facade/engine APIs, test
calls and registration, generator output enumeration and merged history; an
empty name search was not used as absence evidence. The intervening #1900 merge
changes Pad colour dispatch/projection and adds a test target; its diff leaves
audition production logic, the relevant tests and golden generator unchanged.

Before future implementation, refresh these dispositions against live main,
Issue comments and successor PRs, following `issue-done` §0. Relevant producer,
consumer or acceptance changes require another check before commit/premerge.

## 2. Two Task boundaries

**Current design Task — one declared file:**
`docs/plans/2026-10-09-soundset-audition-golden-verification.md`.
Deliver this executable plan with independent review, staged new-file ownership
verification, whitespace checks and only the lanes selected for its exact head.
It adds no tests, product code or fixture; #994 remains open for implementation.

**Future test implementation — six declared files:**

| File | Responsibility |
| --- | --- |
| `tests/core/facade/soundset_facade_test.cpp` | Actual Facade-to-reserved-audition harness; separate identity/geometry, waveform and silence assertions with diagnostics. |
| `tests/fixtures/golden/reference_render.py` | Independent raw-source oracle and explicit default verification of the new WAV/checksum pair; preserve the one-bar pair byte-for-byte. |
| `tests/fixtures/golden/soundset_audition_slot3.wav` | Reproducible oracle output; follow existing WAV Git LFS policy. |
| `tests/fixtures/golden/soundset_audition_slot3.sha256` | Detached output checksum with the correct basename. |
| `docs/plans/2026-10-09-soundset-audition-golden-verification.md` | Record implementation evidence and unresolved boundaries. |
| `apps/docs-site/docs/core/modules/audio-runtime.mdx` | Describe the verified waveform chain and its Host/device limits. |

No root/Facade CMake, public API, production audio, Host, Creator, CI policy,
Contract, version or Assembly edits are planned. Report any necessary scope
expansion before editing. Temporary producer mutations below are proof inputs,
restored before commit; they are not implementation files.

## 3. One pinned, discriminating input

Use the existing Foundry `Foundry Hat Closed`, manifest JSON `slot: 3` (the
typed request uses `slot_index`; the parsed C++ manifest uses `index`):

- Set ID: `11111111-1111-4111-8111-111111111111`, version `1.0.0`.
- Manifest SHA:
  `33175f66912a9add3e4e551d19d85072adcd1f0331fcc9fed80ab0bc18dd9111`.
- Artifact/raw blob SHA:
  `ede3cc971041736b34a866bb00c24ef1c687ec09570a0e0e1815c3dd89b208b2`.
- Blob path: `tests/fixtures/soundset/blob/<artifact SHA>`; 10628 bytes,
  `audio/wav`, PCM16, 44100 Hz, stereo, 2646 frames.
- Prepared expectation: 48000 Hz, stereo, 2880 frames. Render a fixed 3008
  stereo frames: 2880 audio frames followed by 128 exact silent frames.

The manifest and blob bytes were independently hashed and the actual WAV
header read at the inspected base. The nontrivial stereo source covers both
resampling and downmix, so a second demo fixture adds no necessary rate/gain
proof. Distinguish source-blob, generated-reference and actual-output hashes;
none substitutes for another, and no exploratory output hash is a fixture.

## 4. Actual production chain through a test-local seam

1. Reuse the existing fixture Catalog transport/Set Store setup and real
   `Application`. Cache/verify the Set through its existing catalog flow, then
   call `Application::audition_soundset` for the pinned identity and slot 3.
   The actual must traverse decode and `cooker::prepare_runtime_pcm`; never
   pre-resample or inject expected 48 kHz PCM in place of this producer.
2. Put the returned typed `prepared` PCM in `PreparedSampleBank::empty` using
   the existing audition project/revision sentinels and `kAuditionSampleSlot`.
   Use `set_pcm_sample`, full-frame one-shot playback, unity gain, unmuted and
   neutral DSP; retain the real PCM owner.
3. Start a fresh exclusive, device-free `RealtimeEngine`, publish its audition
   bank, enqueue `PadControlKind::audition_start` at velocity 127 and render
   fixed chunks totaling 3008 frames, then stop. Exercise the real publication,
   control queue and audition voice branch; do not use an ordinary Pad trigger
   or fabricate a Project Snapshot.

`render_offline` accepts a Project Snapshot and its neutral integer Pattern
path omits the audition attack/end ramps. It is not the selected seam.
Existing `facade.soundset` component registration already compiles this source,
runs from the repository root and links audio_runtime via `lmdj::application`.
Call the new cases from the existing test main; add no CMake registration.

The current Host converts prepared PCM to mono float and uses `set_sample`;
this harness uses typed PCM. Both engine representations share
`prepared_material_sample`, and an existing PCM/float audition parity test is
supporting evidence only. It cannot be the independent expected waveform.
This Task does not verify private Host float-vector assembly, Creator UI,
AudioContext/Worklet, a native device, physical output or listening acceptance.

## 5. Independent oracle and separate facts

Extend the existing stdlib-only Python reference entry point. Pin and hash the
original blob, then independently compute rational-time linear 44100→48000
interpolation, symmetric PCM16 rounding and last-source-frame clamp. Normalize
positive PCM by 32767 and negative PCM by 32768, average the stereo channels,
apply unity gain and the existing 96-frame attack/end ramps, duplicate mono
into stereo and append 128 silent frames. Do not import/call cooker, engine or
their kernels, consume actual prepared PCM, or regenerate expected from actual.
For final float-to-PCM16 output, scale negatives by 32768 and nonnegatives by
32767, round halfway away from zero (`lround` semantics), then clamp to the
signed PCM16 range. Implement this mathematical convention independently in
the reference and actual-output test conversion; do not share renderer code.

Separate the assertions so each fixes one fact:

1. **Identity/geometry:** exact source SHA/length, reference checksum/header,
   actual prepared rate/channels/frame count and fixed render size.
2. **Waveform:** every actual frame/channel agrees with the independent
   reference within a predeclared maximum of 1 PCM16 LSB. The neutral bounded
   normalization/downmix/ramp path uses fewer than ten binary32 operations;
   their error is below 0.02 PCM steps, while independent final quantization
   can cross one rounding boundary. Validate this budget on Mac/Linux; if it
   fails, diagnose instead of widening it to observed errors. Reference bytes
   and checksum are exact; actual-output hash equality is not required.
3. **Termination:** every sample of the 128-frame tail is exactly zero.

Mismatch diagnostics name case/frame/channel, actual/expected sample, error,
maximum error and reference/actual hashes. Default generator verification must
reject missing, half-present or drifting new pairs; explicit update writes
the oracle artifacts. Keep existing one-bar output unchanged. The Sound Set
corpus validators enumerate their own generated directories, not sibling
`golden/`; no original corpus or its inventory is changed.

## 6. Producer rebuilt red proofs and verification

Pure-Python design experiments separated wrong-phase rate and half gain with
identical 48000 Hz/stereo/2880-frame prepared metadata and 3008-frame render
geometry. This establishes oracle discrimination only: no C++ mutation,
rebuild, new test execution or formal golden adoption has happened yet.

In the future owned implementation worktree, fix expected artifacts and mutate
only `prepare_runtime_pcm` in `packages/project-cooker/src/sample_analysis.cpp`:

- **Wrong rate:** use a 48000 source phase advance while preserving output
  metadata and frame count. Geometry must pass; the named waveform assertion
  must fail on the actual rebuilt Facade producer output.
- **Wrong gain:** halve the resampled PCM amplitude with identical geometry.
  Again require the named waveform assertion to fail with both sample values.

For each mutation separately retain baseline PASS → edit → successful fresh
rebuild (confirm producer compilation) → new assertion RED → pristine restore
with a fresh mtime → successful fresh rebuild → restored PASS. An old unit
failure, build failure or unrelated failure is not this proof. Follow
`issue-done`'s artifact/Make 3.81 whole-second mtime rule; preserve external logs
and inspect the restored clean production diff before commit.

Lowest-tier verification: hydrate fixture LFS; run default Python reference
verification; configure/build the existing Facade target and run
`ctest --test-dir build/core/dev --output-on-failure -R '^facade\.soundset$'`;
execute both rebuilt proofs. Resolve adjacent bank/engine/cooker test names from
the actual CTest inventory and run them. Stage new files before ownership
verification, run whitespace checks and the complete Portal check.

Existing Core Ubuntu/ASan/Coverage/macOS lanes already invoke this reference
script. Add no generic CI gate or new lane. `tests/fixtures/golden/` is a
conservative full-scope rule: classify the future committed head and run all
selected `batch_only` lanes with real exact-input pass keys before merge.
Coordinate Linux/Mac/Web resources; focused tests or this design PR's green
checks cannot satisfy that future obligation.

## Version Management

Version impact: none
Reason: This design changes no production artifact. The future
six-file test Task also reuses existing APIs without changing behavior,
API/ABI, Contracts or Assembly, so allocates no Module version or Product Build.
A new public renderer or behavioral fix would require a separate reassessment.

## Documentation Impact and ownership

Documentation impact: none
Reason: This Task only records implementation scope and
verification design, without changing Portal pages or operating procedures.
Future implementation: Documentation impact: required.
Affected portal pages: `/core/modules/audio-runtime`.
Update coverage evidence and boundaries in that same future Task; no immutable
Product snapshot, release or deployment is authorized by this plan.

The six files do not overlap #1900/#1901's Pad colour/Creator work; #1900 is now
merged. Do not access or change mbp-m1. Refresh shared Facade dependencies and
active ownership before implementation and use an isolated build/cache.
No new product decision is needed: preserve existing 48 kHz runtime, mono
downmix, one-shot/unity playback, declick and best-effort played semantics.
Public export, stereo product behavior and physical audition acceptance remain
outside this scope; do not settle an open Contract question through this test.
