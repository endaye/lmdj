# Live Pad Mute/Solo: immediate input cutoff

Task: Relates to #2112. Status: owning Native/PCM, stress and Portal verification
complete; final Task checks and shipping follow the recorded authorization.
Current-head review and merge remain with Root. No release or cleanup is included.

## Premises and ownership

At source admission, fetched `origin/main` and GitHub main-ref agreed at
`28ff18c5c1f3790157193e900b5c7980cc595026`. The isolated no-upstream branch is
`fix/live-pad-immediate-input` in `lmdj-goal-live-pad-immediate-input`.
Live #2112 is OPEN and still records this producer mismatch separately from C2.
All four existing declared files are byte-identical to the proposal's committed
`0c873e6755fa5753f38ce4bf5267ea5cee00f080`; intervening history touches none.
M1's mask producer is already delivered by #2037; this Task does not recreate it.

Approved authority is [navigation and live mute tails](../prd/decisions/2026-10-11-creator-navigation-and-live-mute-tails.md):
block current and future affected-Pad input immediately while preserving samples
already in shared Delay/Reverb and other Pads. The approved boundary is the
first sample rendered under the applied mask pair, not enqueue acceptance or a
wall-clock click. The existing close ramp is still outstanding: it feeds up to
96 further samples into the bus. Merely zeroing the pre-Tone/EQ gain can still
feed filter memory into that bus. These are source findings, not executed PCM
observations. Ordinary voice stop/release/end behavior remains governed by the
[voice endings decision](../prd/decisions/2026-10-02-sample-voice-endings-and-stops.md).

Root admitted exactly the shared hunks released by S6's 2026-10-13 10:31:46Z
receipt. Only that receipt was read in S6's worktree, never frozen source or
held R-H objects. The released common gate/ToneEQ band matches this base at
SHA256 `d9f955150badb1fb3e27930e88a373954aa3c2bd5094160320b6916a52e68c05`.
The accepted proposal SHA256 is
`b55c2ec1c0bb17a1c8a663c0b51d0134bb357abc8a03bf51248870914df0ff86`.
Root's 53-row MBP metadata audit found no other M1 repair writer within that
inventory; it is not a global absence claim. S6 retains queues, epochs, ACK,
capture, scheduler, PatternInputProfile/muted_no_voice, lifetime/shutdown,
shared64, unrelated tests/registration, ABI debt and diagrams. C2 remains an
independent consumer Task. Its current validation is not producer acceptance.

## Declared files

1. `packages/audio-runtime/src/realtime_engine.cpp`: common live gate closes
   immediately; suppress final gated DSP contribution after Tone/EQ/declick.
2. `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`: live_gate
   comment only; field, layout and public API unchanged.
3. `tests/core/audio/realtime_engine_test.cpp`: correct the close oracle and
   add finite input-boundary regressions alongside existing pad_gates cases.
   Insert registrations beside those calls, preserving all other main/EOF work.
4. `apps/docs-site/docs/core/modules/audio-runtime.mdx`: existing M1 behavior
   and coverage paragraphs only.
5. This plan.

No controller, App, Contract, producer queue, scheduling, DSP algorithm, source
diagram, manifest or other owner file is included. An insufficient five-file
scope must be reported before expansion.

## Implementation and causal tests

Close the common per-voice live gain at the applied mask immediately. Keep the
existing reopen ramp and neutral multiply bypass. Run DSP/filter state,
envelopes, cursor progression, release accounting and voice reclamation as
before; no early continue, stop_voice call or shared-FX reset is introduced.
After Tone/EQ and ordinary post-filter end declick, discard the contribution
of a currently live-gated project voice. Audition remains outside the gate.

The complete existing component binary retains every unrelated test and all
prior pad-gate legs. The contradictory close-ramp oracle changes to first-frame
silence/unaffected-Pad equality; its original windows, reopen/no-retrigger and
positive shared Delay tail/later-decay assertions remain.

New cases independently cover both output channels:

- Current sustained voices: Mute and newly-disallowed Solo on slots 0 and 63,
  alone and alongside a known unaffected signal. Assert accepted vs applied
  sequence/epoch and exact output from the first newly applied sample.
- Primed per-voice Tone/EQ memory: gate after positive output with a continuing
  unaffected Pad. Compare exact known surviving contribution from frame zero;
  this distinguishes closing only the pre-filter gain from final bus cutoff.
- Current and subsequent prepared Pattern notes: preserve Pattern admission,
  scheduler, active voice counts and reopening; assert zero while already
  gated, including the future note's attack, against an ungated positive control.
- Shared Delay and Reverb, separately: feed a direct MasterFxChain an independent
  known bus stream with identical finite prefix and zero affected-Pad input
  thereafter. Compare the complete engine waveform exactly, including the first
  gated frame and later echoes, with and without another Pad. Retain positive
  tail and later-decay evidence; this tests input routing, not the FX algorithm.
- Gate during an ordinary release: silence its contribution without shortening
  the original voice lifetime or inventing a lifecycle edge. Existing ordinary
  stop/end, user envelope, post-EQ declick, cursor wrap, audition, priority,
  bank replacement, queue-full and epoch tests remain intact.

## Verification plan and evidence

At source freeze the sequence below was **UNRUN**, awaiting Root's Native
window after U06b. It is retained as the verification design; actual execution
and the two recorder errors are recorded below. Source preparation alone was
never called RED/GREEN, PCM PASS or Task completion. Initial 1.1 GiB available disk is historical;
the 11:21 UTC read-only observation was 5.3 GiB. Recheck immediately before
Native admission and after builds; no cleanup or capacity guarantee is implied.

The 2026-10-13 read-only refresh used committed main
`c4bde2ffa4390eb83e5ccc1e0313f933732bf88a`. All 15 inspected entrypoint,
dependency, stress and identity files matched this worktree's base exactly.
The original five-file source packet remains preserved separately at SHA256
`8ae00aaea6a8cf768c740893505698db19b7d32e7c67c831b7ab26a6fe8f91b9`.
This plan-only refinement does not alter the other four declared files.

Normal `scripts/core.sh configure dev` delegates to `cmake --preset dev`.
The stable build wrapper has no target option, so use the existing CMake dev
preset directly to select the nine explicit targets below. They build the
normal, testable and DSP-disabled AudioRuntime variants plus their real
foundation/authoring/cooker/performance-runtime dependencies. Dependencies are
vendored locally; no dependency clone or another owner's build tree is needed.
Do not invoke whole Core build/proof/package just to produce these test binaries.

Preserve old source, repaired candidate and the complete dirty five-file patch
before any causal proof. In an ignored execution recorder, capture intentional
old/mutant/repaired states, exact source hashes and mtimes, raw argv, start/end,
exit codes, complete logs, actual engine compile lines, binary/object hashes and
owned child identities. Every negative proof restores the exact candidate with
a fresh mtime in a finally path, even when setup or the negative test fails.
Never restore dirty implementation from HEAD. A returned candidate source alone
does not make an old/mutant binary valid; final repaired compilation is mandatory.

Future sequence, serially from this worktree, with no automatic retries:

1. Write only the preserved base engine with a fresh mtime; keep candidate tests.
   Configure normally, fresh-build only the realtime test target, and execute
   the complete existing binary. Require failure at the intended first closed
   gate frame PCM assertion. A setup error, compile failure, unexpected assertion
   or timeout is not product RED and stops the sequence after restoring source.

```sh
bash scripts/core.sh configure dev
cmake --build --preset dev --parallel 2 --target lmdj_realtime_engine_tests
ctest --preset dev --output-on-failure -R '^audio\.realtime_engine$'
```

2. If separately admitted, run the optional post-filter mutation **before** final
   repaired proofs: preserve immediate close but remove only final post-Tone/EQ
   contribution suppression. Fresh-build the same realtime target and run the
   same full entry; require the primed Tone/EQ memory PCM failure, then restore
   the exact candidate. Keep the original negative receipt. Do not edit the
   tests, reorder registrations, filter inside the binary or change budgets.

3. Fresh-write the exact repaired engine, build the nine existing targets, run
   all eight owning non-stress entries, then the entire original stress entry:

```sh
cmake --build --preset dev --parallel 2 --target \
  lmdj_realtime_engine_tests \
  lmdj_audio_voice_dsp_tests \
  lmdj_audio_voice_dsp_parity_tests \
  lmdj_audio_voice_dsp_disabled_tests \
  lmdj_master_fx_tests \
  lmdj_master_fx_determinism_tests \
  lmdj_master_fx_allocation_guard_tests \
  lmdj_facade_performance_engine_adapter_tests \
  lmdj_realtime_engine_stress_tests
ctest --preset dev --output-on-failure -R '^(audio\.(realtime_engine|voice_dsp|voice_dsp_parity|voice_dsp_disabled|master_fx|master_fx_determinism|master_fx_allocation_guard)|facade\.performance_engine_adapter)$'
ctest --preset dev --output-on-failure -R '^audio\.realtime_spsc_stress$'
```

The eight test entries remain complete. The stress name is
`audio.realtime_spsc_stress`, not historical engine_stress prose; its entire
binary retains the 180-second CTest timeout and 50,000 gate updates. Default dev
unit/component timeouts remain 10/30 seconds. Keep every Facade adapter
live/replay/header/neutral-reset leg. Compile parallelism 2 reduces resource
concurrency, never owning coverage. The optional mutation is not run after an
already valid final full-eight/stress proof just to repeat it unnecessarily.

4. Portal dependencies are known missing in this isolated worktree. During the
   future admitted window, first verify its node_modules is not a shared symlink,
   snapshot its package manifest/lock hashes, run the official locked install,
   require exit 0 and unchanged hashes, then run the whole check once:

```sh
bash scripts/docs-site.sh install
bash scripts/docs-site.sh check
python3 tests/build/ci_change_scope_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
git diff --cached --check
```

The sequence was proposed before execution. Every concrete failure stops the
sequence and retains its original result; actual command outcomes follow below. Final plan-result recording and atomic
commit wait for actual required verification. Report natural completion and
owned child cleanup before returning the shared heavy window. Full
Core/ASan/TSan, Web/Creator, integrated C2/S6, device and hearing acceptance
remain separate and unverified; local Task PASS does not clear them.

## Version Management

Version impact: patch-level compatible AudioRuntime behavior correction to the
approved M1 contract; no new API, exported layout, storage or Contract shape.
Identity allocation is folded into the separately owned V1 version settlement
under version-management §§6/11; this five-file Task allocates no identity.

Actual manifests read at own base and refreshed main above agree:

| Version domain / manifest | Start | Target allocated by this Task |
| --- | --- | --- |
| AudioRuntime `packages/audio-runtime/module.json` | 5.2.0 | 5.2.0 (unchanged) |
| AudioRuntime `api_version` | 2 | 2 (unchanged) |
| Assembly AudioRuntime reference `products/lmdj/assembly.json` | 5.2.0 | 5.2.0 (unchanged) |
| Product Build, Assembly/product version manifest | 2.0.96.0 | 2.0.96.0 (unchanged) |

The Assembly contract remains `lmdj.assembly.v2`; the lock and all manifests are
unchanged. The eventual V1 identity is not guessed here. Existing M1/exported
layout ABI/version debt remains explicitly open for that separate owner; this
repair neither clears it nor treats an unchanged identity as ABI acceptance.

## Documentation Impact

Documentation impact: required — `/core/modules/audio-runtime/`. Correct the
two current M1 paragraphs in this Task; retain historical #2037 receipts,
accepted/applied authority, S6 sections, diagrams and existing ABI debt. The
gate's per-voice-before-shared-FX topology is unchanged, so no diagram changes
are required. Whole Portal is required before shipping and passed as recorded below.

## Pitfall disposition

Read issue-done §0 and the relevant ledger before editing. Apply
`revert-proof-rebuild-skipped`, `mutation-proof-restores-away-uncommitted-work`
and `assertion-observed-after-a-later-transition`: preserve dirty source, prove
the rebuilt artifact, and observe the first applied frame before later silence
can hide the defect. No new pitfall entry is warranted from this product-logic
defect alone; its regression expresses the invariant. The two ignored execution-recorder defects are preserved below with independent
dispositions. They changed no reusable repository tool or product test and do
not justify expanding this five-file product Task into a new infrastructure Task.

## Actual verification and shipping premise — 2026-10-13

Root admitted the sole finite window at 11:41:12.595811 UTC (Orca
`msg_d897291ac202`). Every product/test/Portal input remained bound to the
reviewed five-file source patch SHA256
`9e9bae67fe54e5ffb5eb5673639452ce1ab2ef01a72268c2225f07b1f4f45394`;
the four implementation/test/Portal files were unchanged after these checks.
Only this plan receives the final result record. The tested tree used base
`28ff18c5c1f3790157193e900b5c7980cc595026` plus that reviewed patch, not a
claimed pre-existing clean commit.

| Actual command / proof | Actual outcome and boundary |
| --- | --- |
| `bash scripts/core.sh configure dev` | Exit 0, 11:41:55.798–11:41:58.040 UTC. Normal own build; no borrowed dependencies. |
| Old engine plus candidate tests: `cmake --build --preset dev --parallel 2 --target lmdj_realtime_engine_tests`, then full `ctest --preset dev --output-on-failure -R '^audio\.realtime_engine$'` | Build exit 0; CTest exit 8 at line 6278. First gated frame was −0.00520834327 instead of −0.5. This is the intended rebuilt PCM RED, with fresh engine compile line/object/binary hashes. |
| Exact post-filter contribution-only mutation, same build and full realtime selection | Build exit 0; CTest exit 8 at line 6336: frame 0 output (0.624797583, 0.624797583) instead of (0.125, 0.125), proving primed Tone/EQ memory must be blocked after DSP. No negative test was rerun. |
| Repaired exact nine-target build listed above | Exit 0, 11:47:09.078–11:47:30.240 UTC; real repaired engine compile recorded. |
| Complete owning eight-entry CTest regex listed above | Exit 0, 11:47:30.365–11:47:38.915 UTC; all exact eight names Passed, CTest elapsed 8.16 seconds. No selection or assertion was reduced. |
| `ctest --preset dev --output-on-failure -R '^audio\.realtime_spsc_stress$'` | First/only run exit 0, 11:51:25.434–11:51:28.725 UTC; original entire executable, 180-second timeout and 50,000 gate updates retained. |
| `bash scripts/docs-site.sh install` | Exit 0, 11:51:28.857–11:51:33.221 UTC; own non-symlink node_modules, locked package/lock bytes unchanged. |
| `bash scripts/docs-site.sh check` | First/only run exit 0, 11:51:33.351–11:52:19.839 UTC; 179 tests passed, zero failures; 50 routes and internal links valid. |

Two recorder failures are retained, not converted to successful original runs:

1. The post-filter classifier found a duplicate assertion expression in an old
   helper at line 516 rather than the new gate helper at 6336. Original outer
   session 51922 exited 1; terminal ERROR and classifier false remain intact.
   Root independently read the actual PCM failure, exact mutant source/object/
   binary and child receipts, and accepted that original negative in sidecar
   SHA256 `d74d7e947922874e615747958697234f3251fab3043be613964721fdbfd4ca5f`.
   A finite ignored-script correction constrained future lookup to the gate
   helper; continuation required that exact sidecar and all original hashes.
2. CMake 4.4 printed `100% tests passed out of 8`; the recorder expected an
   older summary containing `0 tests failed`. Original outer session 60575
   exited 1 and terminal ERROR remains. Root independently verified all eight
   exact full-name Passed lines, actual exit 0, repaired compile identities and
   source hashes in sidecar SHA256
   `720d8c0be1563be7196aa8829317d7eb3e8b3497d99ab80711c991503cf1c090`.
   An immutable-receipt-bound continuation ran only the still-unrun stress and
   Portal commands. It neither rebuilt nor repeated the eight passing tests.

Both negative sequences restored the exact candidate bytes with a fresh mtime;
restoration alone was never called a valid compiled repair. The final repaired
realtime binary SHA256 is
`0c9b2aeee6c254b877f0b97adfbe3c1863326eccc14e2bf4d3886d04a3598994`.
Final outer session 37158 exited 0. At 11:53:28.485534 UTC all 262 observed owned
process identities were absent, all five frozen source hashes and nine built
binary hashes matched, and package/lock readback was unchanged. The window was
explicitly released. Ignored evidence is under `.local/m1-execution/`; the
63-file heavy manifest and original receipts are immutable. Release receipt
SHA256 is `912af49679a63503d7fe1f4b241398382316226d3349151d786d03dc075394da`.
This is an observed process census, not enumeration of every short-lived child.

Before final plan recording, fresh `origin/main` was
`12dcdfee511ff9093b95014c72af6188eb90a8c1`. Live umbrella #2112 remained OPEN
with no comments. All four existing declared files at that revision are still
byte-identical to this Task's base: immediate cutoff remains outstanding there.
Intervening U03/U10/U06 presentation work and the MasterFX deadline-accounting
proof affect neither this producer nor the owning realtime stress. Governance
and shipping rules also have no delta. No rebase or product rerun is required
for that unrelated main movement. Final staged ownership/version/PR-body checks
are recorded in the shipping receipt and PR; they are separate from this heavy
verification. Existing C2/S6, full candidate, sanitizers, Web and physical/hearing
acceptance remain unverified by M1.

User direction after this Task: finish existing work, then stop new Task
creation/automatic advancement. M1 shipping is included; no new Task, release,
deployment or cleanup is started here.
