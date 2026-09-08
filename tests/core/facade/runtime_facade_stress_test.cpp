#include <lmdj/facade/runtime_facade.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <string_view>
#include <thread>
#include <vector>

#include <lmdj/cooker/runtime_content.hpp>
#include "packages/audio-runtime/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using namespace lmdj::facade;
RuntimeConfig config() {
  return {{65'536, 32'768, 16'384, 64, 1024},
          16'777'216, 65'536, 128, 10'000, 10'000};
}
cooker::EncodedRuntimeContent content() {
  auto pcm = std::make_shared<const cooker::PcmSample>(
      cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(4096, 16384)});
  cooker::RuntimeSnapshot snapshot{
      foundation::ProjectId{"00000000-0000-4000-8000-000000000001"},
      foundation::PatternId{"00000000-0000-4000-8000-000000000002"},
      1, 120, 1, 960, 3840,
      {{{0, 0}, {}, pcm, {0, 4096, domain::TriggerMode::one_shot, 1.0F, false}}}, {}};
  auto result = cooker::encode_runtime_content(snapshot, config().content_limits);
  LMDJ_CHECK(result.has_value());
  return std::move(result.value());
}

#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
void await(const std::atomic<bool>& flag) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (!flag.load(std::memory_order_acquire)) {
    if (std::chrono::steady_clock::now() >= deadline) {
      std::cerr << "why: callback handoff did not arrive within the 5-second per-handoff budget; "
                   "remedy: inspect the callback admission/drain ordering\n";
      std::abort();
    }
    std::this_thread::yield();
  }
}

struct PausedCallback {
  std::atomic<bool> entered{};
  std::atomic<bool> resume{};
  audio::testing::PatternClaimHook hook{this, [](void* pointer) noexcept {
    auto& self = *static_cast<PausedCallback*>(pointer);
    self.entered.store(true, std::memory_order_release);
    await(self.resume);
  }};
};

void exact_stop_barrier() {
  const auto bytes = content();
  RuntimeFacade runtime(config());
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.submit({epoch, 1}) == RuntimeResult::accepted);
  PausedCallback paused;
  // Existing Engine-only test build seam pauses after Facade admission and
  // before command consumption. Production libraries contain no callback hook.
  audio::testing::set_realtime_hook(audio::testing::RealtimeHookPoint::before_pattern_claim,
                                   &paused.hook);
  std::array<float, 256> left{}, right{};
  std::thread callback([&] { runtime.render(left.data(), right.data(), left.size()); });
  await(paused.entered);
  std::array<RuntimeReceipt, 2> receipts;
  LMDJ_CHECK(runtime.poll(receipts) == 0);
  // A second callback is rejected without entering Engine or disturbing the
  // admitted callback's output buffers.
  std::array<float, 16> refused_left{}, refused_right{};
  refused_left.fill(1); refused_right.fill(1);
  runtime.render(refused_left.data(), refused_right.data(), refused_left.size());
  LMDJ_CHECK(std::all_of(refused_left.begin(), refused_left.end(), [](float v) { return v == 0; }));
  LMDJ_CHECK(std::all_of(refused_right.begin(), refused_right.end(), [](float v) { return v == 0; }));
  runtime.request_stop();
  LMDJ_CHECK(runtime.phase() == RuntimePhase::draining);
  LMDJ_CHECK(runtime.finish_stop() == RuntimeResult::draining);
  LMDJ_CHECK(runtime.unload() == RuntimeResult::wrong_state);
  LMDJ_CHECK(runtime.submit({epoch, 2}) == RuntimeResult::wrong_state);
  paused.resume.store(true, std::memory_order_release);
  callback.join();
  audio::testing::set_realtime_hook(audio::testing::RealtimeHookPoint::before_pattern_claim, nullptr);
  LMDJ_CHECK(runtime.finish_stop() == RuntimeResult::ok);
  LMDJ_CHECK(runtime.phase() == RuntimePhase::stopped);
  LMDJ_CHECK(runtime.poll(receipts) == 1);
  LMDJ_CHECK(receipts[0].sequence == 1);
  LMDJ_CHECK(receipts[0].outcome == RuntimeCommandOutcome::voice_started);
  LMDJ_CHECK(runtime.unload() == RuntimeResult::ok);
  left.fill(1); right.fill(1);
  runtime.render(left.data(), right.data(), left.size());
  LMDJ_CHECK(std::all_of(left.begin(), left.end(), [](float v) { return v == 0; }));
  LMDJ_CHECK(std::all_of(right.begin(), right.end(), [](float v) { return v == 0; }));
}
#endif

void lifecycle_stress() {
  const auto bytes = content();
  RuntimeFacade runtime(config());
  std::atomic<bool> done{};
  std::atomic<std::uint32_t> calls{};
  std::thread callback([&] {
    std::array<float, 64> left{}, right{};
    while (!done.load(std::memory_order_acquire)) {
      runtime.render(left.data(), right.data(), left.size());
      calls.fetch_add(1, std::memory_order_release);
      std::this_thread::yield();
    }
  });
  RuntimeEpoch previous;
  constexpr std::uint32_t generations = 300;
  for (std::uint32_t generation = 0; generation < generations; ++generation) {
    LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
    RuntimeEpoch epoch;
    LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
    LMDJ_CHECK(runtime.submit({previous, 1}) == RuntimeResult::stale_epoch);
    for (std::uint32_t sequence = 1; sequence <= 64; ++sequence) {
      LMDJ_CHECK(runtime.submit({epoch, sequence}) == RuntimeResult::accepted);
    }
    runtime.stop();
    LMDJ_CHECK(runtime.phase() == RuntimePhase::stopped);
    std::array<RuntimeReceipt, 128> receipts;
    const auto count = runtime.poll(receipts);
    LMDJ_CHECK(count == 64);
    for (std::size_t index = 0; index < count; ++index) {
      LMDJ_CHECK(receipts[index].epoch == epoch && receipts[index].sequence == index + 1);
    }
    runtime.reset();
    LMDJ_CHECK(runtime.phase() == RuntimePhase::empty);
    // Callback thread continues calling the closed gate during unload/load.
    // No forced state replaces the actual callback or ownership transfer.
    previous = epoch;
  }
  done.store(true, std::memory_order_release);
  callback.join();
  LMDJ_CHECK(calls.load() > 0);
  std::array<float, 16> left{}, right{};
  left.fill(1); right.fill(1);
  runtime.render(left.data(), right.data(), left.size());
  LMDJ_CHECK(std::all_of(left.begin(), left.end(), [](float v) { return v == 0; }));
  LMDJ_CHECK(std::all_of(right.begin(), right.end(), [](float v) { return v == 0; }));
}
}  // namespace

int main(int argc, char** argv) {
  if (argc == 2 && std::string_view(argv[1]) == "--stress") lifecycle_stress();
  else {
    LMDJ_CHECK(argc == 1);
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
    exact_stop_barrier();
#else
    LMDJ_CHECK(false);
#endif
  }
}
