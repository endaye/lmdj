# Pin the audio clock epoch before asynchronous input-profile refresh

Parent: #2112 / #2232. Consumer: Draft #2359.
Task branch: `fix/count-in-clock-epoch`, base/main
`24d2545c6c14e175e1b3cb8e73071374fd900e92`.

## Premise disposition

At this refreshed main, both explicit activation and automatic recovery await
`refreshPatternInputProfile()` between the positive `audio.activate` result and
`engineEpochHeartbeat` sampling in the public Runtime Session. The engine is
already rendering while this extra RPC runs. Creator's existing clock converter
counts callbacks from that sampled epoch, so this delay becomes a permanent
phase offset. The positive control is the existing public `sampleAudioClock`
activation/re-activation tests, which use an immediately settled profile and do
not advance its heartbeat during the await. No later main successor changes
these sites; the current open clock issues #1973/#2235/#2236 concern other Bar
geometry and preview work and are not reimplemented.

S7 clean head `50754ace` retained a complete packaged result: 17 PASS / 3 FAIL.
Both full UI recording cases reached Applied but failed the unchanged
Native-to-JS two-render-quantum assertion (1280 frames at 120 BPM; 1024 at 40).
The third test expected replacement confirmation before the Sample inspection
was ready; its trace shows the direct A01 Capture dialog. S7 must wait for the
actual assigned-Sample projection before exercising that confirmation leg.
All seven original native count-in and five original metronome journeys passed.
Bluetooth was observed at both ends; no device causality or #2358 closure is
claimed. No timeout or precision assertion is relaxed.

## Declared files

- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `docs/plans/2026-10-18-count-in-clock-epoch.md`

## Task and verification

Capture the callback heartbeat directly after the original positive activation
result, before the extra asynchronous capability refresh, in explicit activation
and automatic recovery. Keep the state/generation checks after refresh: this is
an epoch sample, not permission to publish Running early. Do not change Native,
wire DTOs, device/Control/opening budgets, graph ownership or count-in admission.

First demonstrate a deterministic red public clock test: hold the actual
capability refresh after successful activation, advance the modeled callback
heartbeat, release it, and require that the epoch remains the pre-refresh value
while the sampled current heartbeat includes all callbacks. Cover initial and
resumed activation. Run the complete loader/Session Node selection, Portal check,
staged ownership and declaration/diff checks before the atomic commit. S7 must
then adopt the actual squash and rerun its complete unchanged 20-journey packaged
selection before its own merge. Those future results are not claimed here.

## Version Management

Version impact: Web Runtime Platform PATCH debt, subsumed by its pending MINOR
settlement in #2237. No Product/Assembly/Contract or manifest identity allocation.

## Documentation Impact

Documentation impact: required.
Affected portal pages: /platform/web-runtime/
Describe the activation-edge epoch and the independent post-activation profile
refresh; the native callback clock and all existing authority boundaries remain.

## Local verification

- The first test fixture reused one audio-node handle for both Native outputs
  and did not reach its held-refresh assertion; that run was stopped and is not
  a red clock proof. Corrected the fixture to allocate distinct handles, matching
  the existing input-profile harness, and bound the missing-refresh diagnostic.
  The public tests then both failed at their actual clock assertion:
  actual epoch 110/210 versus independently pinned activation epoch 100/200.
- With the capture moved before profile refresh, the complete loader/Session
  selection passes 427 tests, zero failures/skips. All existing lifecycle,
  activation, input and retained-consumer tests remain intact.
- Portal check passes 179 tests and 50 routes/internal links. Staged ownership
  passes all 76 tests. Current main remains the declared base before commit.
- This is the producer correction only. S7's complete real UI/PCM/Truth/reopen
  rerun and current-head independent review remain required for its own merge;
  no packaged phase correction or physical listening result is claimed here.

## Scope refresh before Native epoch follow-up

Main is still `24d2545c`. The complete focused consumer result on `f3429648`
is 1 PASS / 2 FAIL: the 120 BPM case passes phase/raw PCM/Master/Record-off
Truth and fails its later Stop observation; 40 BPM retains a 768-frame phase
error; Sample/Performance exclusion passes. The earlier assumption that both
recording cases reached Stop was corrected in the live PR before any merge.
#2360 remains Draft: moving the browser sample before one extra RPC proves
that reduced defect, but the asynchronous activation reply itself can already
arrive several callbacks after Native's first open callback.

At this main revision the adapter exposes current callback heartbeat and
acknowledged generation, but no actual engine-epoch heartbeat. The existing
first-open callback consumes `activation_generation` and publishes the positive
acknowledgement; it alone can publish the heartbeat immediately preceding its
first engine render. Capture that original scalar locally from the existing
heartbeat increment and publish it before the existing acknowledgement. This
adds one lock-free uint32 store per activation, no new realtime allocation,
lock, queue, gate or callback deadline. Paused callbacks never claim the epoch;
ordinary later callbacks and Bank publications never replace it. Gate reopening
gets its own actual epoch. Control/main-thread receipt latency cannot move it.

Expand the declared files, before editing, to this exact twelve-file Task:

- `packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp`
- `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- `packages/web-runtime-platform/CMakeLists.txt`
- `packages/web-runtime-platform/src/bridge.cpp`
- `packages/web-runtime-platform/src/web-runtime-pre.js`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/test/runtime_loader.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `docs/plans/2026-10-18-count-in-clock-epoch.md`

Expose an additive direct Native getter through the existing per-Runtime
publisher; Session's existing three-field public AudioClockSample uses it when
available, with the old activation-return sample retained for legacy runtimes.
Keep Running/recovery validation and original count-in capability shape. The
new Node cases must hold both the original positive activation reply and profile
refresh while modeled callbacks continue, and require the original Native epoch
for initial/resumed activation. Loader tests bind the actual native export and
uint32 decoding. Build/link the normal pinned Wasm producer and TypeScript,
run all owning loader/Session tests and Portal/ownership checks, then freeze and
adopt this exact producer in S7 for its independent Native PCM calibration and
unchanged strict two-quantum phase witnesses. Retain every initial failure and
all original 20 journeys; add the actual terminal UI unlock before the next Stop
instead of treating a Host reply or idle-looking REC alone as that far side.

Version impact now includes additive nonvirtual Audio Runtime / Runtime export
MINOR debt and compatible Session clock correction; existing pending MINOR debts
in #2237 subsume these changes, without manifest/Product/Contract allocation.
Documentation impact: required.
Affected portal pages: /core/modules/audio-runtime/ /platform/web-runtime/

## Native follow-up local freeze

- The native-epoch delayed-reply tests first failed at their actual public clock
  assertions: epoch 106/206 versus 100/200. The actual publisher getter test also
  failed before the new getter/wrap decoding existed. These original red outputs
  are retained; the old two-profile-delay-only cases stay as legacy coverage.
- The final complete loader/Session selection passes 430 tests, zero failures or
  skips. It includes initial/resumed Native epochs with both a delayed activation
  reply and a held profile refresh, legacy fallback, actual per-Runtime getter
  publication and unsigned callback/epoch wrap.
- Normal pinned Emscripten 6.0.5 / Node 26 build/link and Creator TypeScript/UI
  build pass, including the real adapter, Bridge and retained Native export.
  Portal passes 179 tests and 50 routes/internal links; ownership passes 76.
- A clean local freeze is required before packaging. S7 must adopt this exact
  producer source and rebuild its artifact, then retain all 20 complete journeys.
  Native PCM calibration/phase and terminal UI unlock/Stop/reopen are still
  pending; neither this freeze nor the old 2c9ada26 review authorizes merge.
