# Audio Publication Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the bank-publication ordering failures blocking global Pattern transport and Creator UI migration (#1207, #1230).

**Architecture:** Keep the independent fixed audition pool and single-producer/single-consumer queues. After acquiring an audition-start command, apply preceding audition publications before selecting PCM. Preserve the Project Bank pending-zero admission gate; correct the stress harness to wait for that gate rather than generation visibility alone.

**Tech Stack:** C++20, CMake/CTest, production-linked stress and private deterministic test hooks, GNU ASan/UBSan and TSan.

**Spec:** Existing `publish_audition_bank` latest-publication-wins contract and `realtime_engine.hpp` Bank pending-zero release/acquire contract; user-approved prerequisite repair. This is an internal correctness repair, not a new product interaction decision. The larger scope remains `docs/plans/2026-09-11-creator-ui-migration.md`.

## Global Constraints

- Realtime callbacks do not allocate, lock, destroy PCM owners, mutate Project Truth, or perform I/O.
- Audition uses its separate two-slot pool; Project Pad input ownership and #725 outcome semantics do not change.
- Publish A, enqueue audition start, publish B before audio selection still plays B. Do not pin a click to A or add Project-style `events_pending` refusal to audition.
- Publication application after command acquire is bounded by `kRealtimeAuditionBankCapacity`; do not introduce a producer-dependent unbounded drain.
- Private hooks compile only into the testable library. Public API and Engine storage layout remain unchanged.
- Preserve stress iterations, accepted/refused assertions, weak-owner lifetime, byte refunds, stop/release behavior and far-side assertions. No retry-to-green or blanket enqueue retries.
- Original uncommitted transport work stays in its other worktree; this repair builds independently from main.

## Version Management

Version impact: none for identity allocation in this source-only Task. This is an implementation bug fix with no public API, ABI, Contract, Product or Assembly identity change. It is patch-level behavior for the next authorized Audio Runtime allocation; this Task does not allocate or distribute a Build. Do not edit manifests or consumer pins.

Documentation impact: none for portal routes. The repair restores existing audition selection and Bank admission contracts; the portal already describes pending-zero handoff and separate audition ownership. This plan records the failure and verification without changing documented architecture or projected identities.

### Task 1: Restore publication-before-use handoff

**Files:**
- Modify: `packages/audio-runtime/src/realtime_engine.cpp`
- Modify: `packages/audio-runtime/src/testing_hooks.hpp`
- Test: `tests/core/audio/realtime_engine_test.cpp`
- Test: `tests/core/audio/realtime_engine_stress_test.cpp`
- Create: `docs/superpowers/plans/2026-09-12-audio-publication-order.md`

**Interfaces:** Consume existing `publish_audition_bank`, `enqueue_control`, `render`, `bank_telemetry`, `reclaim_retired_banks` and private hook API. Produce no new public interface.

- [ ] Capture deterministic audition RED on fresh main. Seed old negative PCM, pause audio at `before_pattern_claim` after its initial audition drain, publish positive PCM and enqueue audition start on control, then release/join audio. The first attack sample at F is zero; assert the next sample at F+1 is positive. Add the no-current-bank variant to catch silently discarded admitted starts. Register tests in `main`, without removing existing calls.

```cpp
LMDJ_CHECK(engine.publish_audition_bank(audition_bank_with_sample(new_pcm)) ==
           PublishResult::accepted);
LMDJ_CHECK(engine.enqueue_control({1, 0, 127, PadControlKind::audition_start, {}}) ==
           EnqueueResult::accepted);
// Release the deterministic callback gate, then join the callback thread.
LMDJ_CHECK(left[0] == 0.0F);
LMDJ_CHECK(left[1] > 0.0F); // Old negative PCM or discarded start must fail.
```

- [ ] Add a private hook immediately after `apply_published_bank` and before pending decrement. Prove the exact legal intermediate tuple and refusal, then release/join, prove admission and actual new PCM playback. This is characterization of a correct gate, not a demand to admit early.

```cpp
const auto observed = engine.bank_telemetry();
LMDJ_CHECK(observed.current_generation == 1);
LMDJ_CHECK(observed.pending_publications == 1);
LMDJ_CHECK(engine.enqueue_control({1, 0, 127, PadControlKind::press, {}}) ==
           EnqueueResult::bank_transition);
// After release/join, the same sequence's first actual admission is accepted.
```

- [ ] Build the named component target and run `ctest --preset dev --output-on-failure -R '^audio\.realtime_engine$'`. Retain the exact wrong-source RED and captured `bank_transition` evidence before production repair.
- [ ] Add a bounded audition publication refresh after acquiring `audition_start`, before source selection. A render-local helper can share the bounded drain with the initial publication drain. The loop uses the existing fixed capacity:

```cpp
for (std::size_t applied = 0;
     applied < kRealtimeAuditionBankCapacity &&
     audition_publish_queue_.try_pop(published_audition);
     ++applied) {
  apply_published_audition(published_audition);
}
```

- [ ] Correct the PCM stress readiness predicate, reading one telemetry value per iteration. Keep the subsequent single enqueue and exact `accepted` assertion; do not change production admission semantics.

```cpp
for (;;) {
  const auto observed = engine.bank_telemetry();
  if (observed.current_generation == generation * 2 - 1 &&
      observed.pending_publications == 0) break;
  std::this_thread::yield();
}
```

- [ ] Verify latest-wins with distinct-sign A/B PCM before the first callback; retain existing replacement/live-owner/full-pool tests. In the drain-gap test, prove the unused old owner can be reclaimed and the newly playing owner cannot. Verify first audition is not lost.
- [ ] Configure each of `dev`, `asan`, `tsan` with `bash scripts/core.sh configure PRESET`; build `cmake --build --preset PRESET --parallel 8 --target lmdj_realtime_engine_tests lmdj_realtime_engine_stress_tests`; run `ctest --preset PRESET --output-on-failure -R '^audio\.(realtime_engine|realtime_spsc_stress)$'`. Preserve any distinct failure, not just the final pass. Check the production archive has no new test-hook symbols.
- [ ] Independently review the complete repair diff and evidence against these contracts, resolve findings, verify declared-path ownership and staged whitespace, then create atomic `fix(audio): preserve publication-before-use ordering`. Ship under repository issue-done/current-head review rules. No A1 source or unrelated files enter this commit.
