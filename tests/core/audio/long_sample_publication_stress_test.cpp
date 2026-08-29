#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/runtime_preparation_limits.hpp>

#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <exception>
#include <iostream>
#include <span>
#include <thread>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::EnqueueResult;
using lmdj::audio::PadControlEvent;
using lmdj::audio::PadControlKind;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::ReclaimedBankTelemetry;
using lmdj::audio::RuntimePreparationLimits;
using lmdj::audio::TriggerEvent;
using lmdj::cooker::ResolvedPlayback;
using lmdj::domain::TriggerMode;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";
constexpr std::uint32_t kMaximumBankPadFrames = 16'777'216;
constexpr std::uint64_t kMaximumBankBytes = 67'108'864;
constexpr std::uint64_t kMaximumGenerationBytes = 134'217'728;
constexpr std::uint64_t kMaximumResidentBytes = 268'435'456;
constexpr RuntimePreparationLimits kLimits{
    68'157'440,
    kMaximumBankBytes,
    kMaximumGenerationBytes,
    kMaximumResidentBytes,
};

static_assert(
    lmdj::audio::kRealtimeMaximumSampleFrames >= kMaximumBankPadFrames);
static_assert(
    kMaximumBankPadFrames * sizeof(float) == kMaximumBankBytes);
static_assert(kMaximumResidentBytes == 2 * kMaximumGenerationBytes);

PreparedSampleBank maximum_single_pad_bank(
    std::uint64_t revision,
    float marker,
    std::uint8_t slot = 0) {
  const std::vector<float> sample(kMaximumBankPadFrames, marker);
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, revision);
  LMDJ_CHECK(
      bank.set_sample(
              slot,
              std::span<const float>(sample),
              ResolvedPlayback{
                  0,
                  kMaximumBankPadFrames,
                  TriggerMode::loop_gate,
                  1.0F,
                  false})
          .has_value());
  LMDJ_CHECK(bank.decoded_pcm_bytes() == kMaximumBankBytes);
  return bank;
}

PreparedSampleBank maximum_generation(
    std::uint64_t revision,
    float first_marker,
    float second_marker) {
  auto bank = maximum_single_pad_bank(revision, first_marker, 0);
  const std::vector<float> second(kMaximumBankPadFrames, second_marker);
  LMDJ_CHECK(
      bank.set_sample(
              16,
              std::span<const float>(second),
              ResolvedPlayback{
                  0,
                  kMaximumBankPadFrames,
                  TriggerMode::loop_gate,
                  1.0F,
                  false})
          .has_value());
  LMDJ_CHECK(bank.decoded_pcm_bytes() == kMaximumGenerationBytes);
  return bank;
}

class ResidencyLedger {
 public:
  bool can_prepare_maximum_generation() const noexcept {
    return kLimits.maximum_resident_bytes >=
               kLimits.maximum_generation_bytes &&
           reserved_bytes_ <= kLimits.maximum_resident_bytes -
                                  kLimits.maximum_generation_bytes;
  }

  void reserve(std::uint64_t bytes) {
    const auto aggregate =
        lmdj::audio::checked_runtime_byte_sum(reserved_bytes_, bytes);
    LMDJ_CHECK(aggregate.has_value());
    LMDJ_CHECK(kLimits.allows_resident_bytes(*aggregate));
    reserved_bytes_ = *aggregate;
  }

  void reclaim(const ReclaimedBankTelemetry& reclaimed) {
    LMDJ_CHECK(reclaimed.decoded_pcm_bytes <= reserved_bytes_);
    reserved_bytes_ -= reclaimed.decoded_pcm_bytes;
  }

  std::uint64_t reserved_bytes() const noexcept { return reserved_bytes_; }

 private:
  std::uint64_t reserved_bytes_ = 0;
};

class ConcurrentRenderer {
 public:
  explicit ConcurrentRenderer(RealtimeEngine& engine) : engine_(engine) {
    thread_ = std::thread([this] {
      std::array<float, 64> left{};
      std::array<float, 64> right{};
      while (running_.load(std::memory_order_acquire)) {
        engine_.render(
            left.data(),
            right.data(),
            static_cast<std::uint32_t>(left.size()));
        for (std::size_t frame = 0; frame < left.size(); ++frame) {
          if (!std::isfinite(left[frame]) || !std::isfinite(right[frame]) ||
              std::abs(left[frame]) > 1.0F ||
              std::abs(right[frame]) > 1.0F) {
            invalid_samples_.fetch_add(1, std::memory_order_relaxed);
          }
        }
      }
      for (int drain = 0; drain < 64; ++drain) {
        engine_.render(
            left.data(),
            right.data(),
            static_cast<std::uint32_t>(left.size()));
      }
    });
  }

  ConcurrentRenderer(const ConcurrentRenderer&) = delete;
  ConcurrentRenderer& operator=(const ConcurrentRenderer&) = delete;

  ~ConcurrentRenderer() { join(); }

  void stop() {
    join();
    LMDJ_CHECK(invalid_samples_.load(std::memory_order_relaxed) == 0);
  }

 private:
  void join() noexcept {
    if (!thread_.joinable()) {
      return;
    }
    running_.store(false, std::memory_order_release);
    thread_.join();
  }

  RealtimeEngine& engine_;
  std::atomic<bool> running_{true};
  std::atomic<std::uint64_t> invalid_samples_{0};
  std::thread thread_;
};

template <typename Predicate>
void wait_for(Predicate predicate) {
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(10);
  while (!predicate()) {
    LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    std::this_thread::yield();
  }
}

void release_slot(RealtimeEngine& engine, std::uint64_t sequence,
                  std::uint8_t slot) {
  LMDJ_CHECK(
      engine.enqueue_control(PadControlEvent{
          sequence,
          slot,
          0,
          PadControlKind::release,
          {},
      }) == EnqueueResult::accepted);
}

void test_maximum_single_pad_publishes_and_retires_under_trigger_load() {
  RealtimeEngine engine;
  ResidencyLedger ledger;
  auto full_pad = maximum_single_pad_bank(1, 0.25F);
  LMDJ_CHECK(full_pad.sample_count() == 1);
  LMDJ_CHECK(full_pad.availability_mask() == 1);
  ledger.reserve(full_pad.decoded_pcm_bytes());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(full_pad)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  auto replacement =
      PreparedSampleBank::empty(ProjectId{kProjectId}, 2);
  const auto before_rejection = engine.bank_telemetry();
  LMDJ_CHECK(engine.publish_sample_bank(std::move(replacement)) ==
             PublishResult::events_pending);
  const auto after_rejection = engine.bank_telemetry();
  LMDJ_CHECK(
      after_rejection.current_generation == before_rejection.current_generation);
  LMDJ_CHECK(after_rejection.accepted_publications ==
             before_rejection.accepted_publications);
  LMDJ_CHECK(ledger.reserved_bytes() == kMaximumBankBytes);

  ConcurrentRenderer renderer(engine);
  wait_for([&] { return engine.telemetry().active_voices == 1; });
  wait_for([&] { return engine.telemetry().queued_events == 0; });
  LMDJ_CHECK(engine.publish_sample_bank(std::move(replacement)) ==
             PublishResult::accepted);
  wait_for([&] {
    return engine.bank_telemetry().current_generation == 2;
  });
  LMDJ_CHECK(engine.reclaim_retired_bank_telemetry().count == 0);

  release_slot(engine, 2, 0);
  wait_for([&] { return engine.telemetry().active_voices == 0; });
  const auto reclaimed = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(reclaimed.count == 1);
  LMDJ_CHECK(reclaimed.decoded_pcm_bytes == kMaximumBankBytes);
  ledger.reclaim(reclaimed);
  LMDJ_CHECK(ledger.reserved_bytes() == 0);
  renderer.stop();
  engine.stop();
}

void test_two_maximum_generations_reach_but_never_cross_residency_limit() {
  RealtimeEngine engine;
  ResidencyLedger ledger;
  auto first = maximum_generation(10, 0.125F, 0.25F);
  ledger.reserve(first.decoded_pcm_bytes());
  LMDJ_CHECK(ledger.reserved_bytes() == kMaximumGenerationBytes);
  LMDJ_CHECK(ledger.can_prepare_maximum_generation());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(first)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{10, 0, 127}) ==
             EnqueueResult::accepted);

  ConcurrentRenderer renderer(engine);
  wait_for([&] { return engine.telemetry().active_voices == 1; });
  wait_for([&] { return engine.telemetry().queued_events == 0; });

  auto second = maximum_generation(11, 0.5F, 0.75F);
  ledger.reserve(second.decoded_pcm_bytes());
  LMDJ_CHECK(ledger.reserved_bytes() == kMaximumResidentBytes);
  LMDJ_CHECK(!ledger.can_prepare_maximum_generation());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::accepted);
  wait_for([&] {
    return engine.bank_telemetry().current_generation == 2;
  });
  LMDJ_CHECK(engine.reclaim_retired_bank_telemetry().count == 0);

  release_slot(engine, 11, 0);
  wait_for([&] { return engine.telemetry().active_voices == 0; });
  const auto reclaimed_first = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(reclaimed_first.count == 1);
  LMDJ_CHECK(
      reclaimed_first.decoded_pcm_bytes == kMaximumGenerationBytes);
  ledger.reclaim(reclaimed_first);
  LMDJ_CHECK(ledger.reserved_bytes() == kMaximumGenerationBytes);
  LMDJ_CHECK(ledger.can_prepare_maximum_generation());

  LMDJ_CHECK(engine.enqueue(TriggerEvent{12, 16, 127}) ==
             EnqueueResult::accepted);
  wait_for([&] { return engine.telemetry().active_voices == 1; });
  release_slot(engine, 13, 16);
  wait_for([&] { return engine.telemetry().active_voices == 0; });

  renderer.stop();
  engine.stop();
  auto empty = PreparedSampleBank::empty(ProjectId{kProjectId}, 12);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(empty)) ==
             PublishResult::accepted);
  const auto reclaimed_second = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(reclaimed_second.count == 1);
  LMDJ_CHECK(
      reclaimed_second.decoded_pcm_bytes == kMaximumGenerationBytes);
  ledger.reclaim(reclaimed_second);
  LMDJ_CHECK(ledger.reserved_bytes() == 0);
}

}  // namespace

int main() {
  try {
    test_maximum_single_pad_publishes_and_retires_under_trigger_load();
    test_two_maximum_generations_reach_but_never_cross_residency_limit();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "long-sample publication stress tests: PASS\n";
  return 0;
}
