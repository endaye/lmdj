#include <array>
#include <atomic>

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <memory>
#include <new>
#include <span>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

#include "pattern_generation.hpp"
#include "realtime_engine_audio_access.hpp"
#include "testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

std::atomic<bool> g_track_allocations{false};
std::atomic<std::uint64_t> g_allocations{0};
std::atomic<std::uint64_t> g_deallocations{0};
std::atomic<std::uint64_t> g_allocation_bytes{0};
thread_local bool g_fail_allocations = false;

void count_allocation(std::size_t bytes) noexcept {
  if (g_track_allocations.load(std::memory_order_relaxed)) {
    g_allocations.fetch_add(1, std::memory_order_relaxed);
    g_allocation_bytes.fetch_add(bytes, std::memory_order_relaxed);
  }
}

void ordinary_deallocation(void* memory) noexcept {
  if (g_track_allocations.load(std::memory_order_relaxed)) {
    g_deallocations.fetch_add(1, std::memory_order_relaxed);
  }
  std::free(memory);
}

void* ordinary_allocation(std::size_t size) {
  count_allocation(size);
  if (g_fail_allocations) {
    throw std::bad_alloc{};
  }
  if (void* memory = std::malloc(size == 0 ? 1 : size)) {
    return memory;
  }
  throw std::bad_alloc{};
}

void* aligned_allocation(std::size_t size, std::size_t alignment) {
  count_allocation(size);
  if (g_fail_allocations) {
    throw std::bad_alloc{};
  }
  void* memory = nullptr;
  if (posix_memalign(&memory, alignment, size == 0 ? 1 : size) == 0) {
    return memory;
  }
  throw std::bad_alloc{};
}

using lmdj::audio::CapturedTriggerEvent;
using lmdj::audio::CaptureState;
using lmdj::audio::EnqueueResult;
using lmdj::audio::PadControlEvent;
using lmdj::audio::PadControlKind;
using lmdj::audio::PadControlOrigin;
using lmdj::audio::PatternPublishResult;
using lmdj::audio::PreparedPatternView;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PreparedSampleMaterialView;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RealtimeState;
using lmdj::audio::RuntimeTriggerOutcome;
using lmdj::audio::RuntimeTriggerOutcomeEvent;
using lmdj::audio::RuntimeVoiceState;
using lmdj::audio::RuntimeVoiceStateEvent;
using lmdj::audio::TriggerEvent;
using lmdj::cooker::ResolvedEvent;
using lmdj::cooker::ResolvedPad;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::PadSlotId;
using lmdj::domain::TriggerMode;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";
constexpr auto kPatternA = "30000000-0000-4000-8000-000000000001";
constexpr auto kPatternB = "30000000-0000-4000-8000-000000000002";

constexpr std::uint32_t kRampFrames = lmdj::audio::kRealtimeRampFrames;
constexpr float kRampScale = 1.0F / static_cast<float>(kRampFrames);
constexpr std::uint32_t kMaximumBankPadFrames = 16'777'216;
static_assert(
    lmdj::audio::kRealtimeMaximumSampleFrames >= kMaximumBankPadFrames);

void engine_queue_profiles_account_for_all_allocated_payloads() {
  using namespace lmdj::audio;
  // 0 is the unchanged default, -1 the unchanged tag-only constructor.
  for (const int profile : {0, -1, 1, 128, 1024}) {
    g_allocations.store(0); g_deallocations.store(0); g_allocation_bytes.store(0);
    g_track_allocations.store(true);
    auto engine = profile == 0 ? std::make_unique<RealtimeEngine>()
        : profile == -1 ? std::make_unique<RealtimeEngine>(RealtimeEngine::ReceiptBoundedVoiceStates{})
        : std::make_unique<RealtimeEngine>(RealtimeEngine::ReceiptBoundedVoiceStates{},
                                           static_cast<std::size_t>(profile));
    g_track_allocations.store(false);
    const auto controls = profile > 0 ? static_cast<std::size_t>(profile) : 1024;
    const auto outcomes = profile > 0 ? static_cast<std::size_t>(profile) : 4096;
    const auto states = profile > 0 ? static_cast<std::size_t>(2 * profile + 128)
                                    : (profile == 0 ? 10240U : 2176U);
    const auto payload = (controls + 1) * sizeof(PadControlEvent) +
        (outcomes + 1) * sizeof(RuntimeTriggerOutcomeEvent) +
        (states + 1) * sizeof(detail::RuntimeVoiceStateCell);
    LMDJ_CHECK(g_allocations.load() == 4); // Engine plus three fixed cell arrays.
    LMDJ_CHECK(g_deallocations.load() == 0);
    LMDJ_CHECK(g_allocation_bytes.load() == sizeof(RealtimeEngine) + payload);
    if (profile > 0) {
      LMDJ_CHECK(RealtimeEngine::receipt_bounded_storage_bytes(controls) == payload);
    }

    LMDJ_CHECK(engine->start().has_value());
    for (std::size_t index = 0; index < controls; ++index) {
      LMDJ_CHECK(engine->enqueue_control(PadControlEvent{
          index + 1, 0, 0, PadControlKind::stop_all, {}}) == EnqueueResult::accepted);
    }
    LMDJ_CHECK(engine->enqueue_control(PadControlEvent{
        controls + 1, 0, 0, PadControlKind::stop_all, {}}) == EnqueueResult::queue_full);
    LMDJ_CHECK(engine->telemetry().queued_events == controls);
    float left{}, right{};
    g_allocations.store(0); g_deallocations.store(0);
    g_track_allocations.store(true);
    engine->render(&left, &right, 1);
    g_track_allocations.store(false);
    LMDJ_CHECK(g_allocations.load() == 0 && g_deallocations.load() == 0);
    LMDJ_CHECK(left == 0 && right == 0);
    LMDJ_CHECK(engine->telemetry().queued_events == 0);
    LMDJ_CHECK(engine->telemetry().dequeued_events == controls);
    engine->stop();
    g_deallocations.store(0); g_track_allocations.store(true);
    engine.reset();
    g_track_allocations.store(false);
    LMDJ_CHECK(g_deallocations.load() == 4);
  }
}

void receipt_profile_rejects_invalid_capacity() {
  using namespace lmdj::audio;
  for (const auto invalid : {std::size_t{0}, std::size_t{1025},
                             std::numeric_limits<std::size_t>::max()}) {
    LMDJ_CHECK(!RealtimeEngine::receipt_bounded_storage_bytes(invalid));
    bool rejected = false;
    try { RealtimeEngine engine(RealtimeEngine::ReceiptBoundedVoiceStates{}, invalid); }
    catch (const std::invalid_argument&) { rejected = true; }
    LMDJ_CHECK(rejected);
  }
}

// Mirrors the engine's ramp arithmetic exactly (same operands, same order):
// one ramp component is `frames * (1/96)` and components multiply into a
// single factor that scales `sample * gain`.
float ramp_part(std::uint32_t frames) noexcept {
  return static_cast<float>(frames) * kRampScale;
}

PreparedSampleBank bank_with_sample(
    std::uint64_t revision,
    std::span<const float> sample,
    std::uint8_t slot = 0) {
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, revision);
  LMDJ_CHECK(bank.set_sample(slot, sample).has_value());
  return bank;
}

PreparedSampleBank bank_with_playback(
    std::uint64_t revision,
    std::span<const float> sample,
    ResolvedPlayback playback,
    std::uint8_t slot = 0) {
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, revision);
  LMDJ_CHECK(bank.set_sample(slot, sample, playback).has_value());
  return bank;
}

RuntimeSnapshot pattern_snapshot(
    const char* pattern_id,
    PadSlotId slot,
    std::uint8_t velocity,
    std::uint16_t bpm = 120,
                                 std::int16_t sample_value = 1) {
  auto sample = std::make_shared<const lmdj::cooker::PcmSample>(
      lmdj::cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(128, sample_value)});
  return RuntimeSnapshot{
      ProjectId{kProjectId},
      PatternId{pattern_id},
      1,
      bpm,
      1,
      lmdj::domain::kPpq,
      lmdj::domain::kBarTicks4x4,
      {ResolvedPad{
          slot,
          lmdj::foundation::ArtifactRef{
              std::string(64, 'a'), "audio/wav", 256},
          sample,
          ResolvedPlayback{
              0, 128, TriggerMode::loop_gate, 1.0F, false},
      }},
      {ResolvedEvent{
          slot,
          0,
          lmdj::domain::kBarTicks4x4,
          velocity,
          sample,
      }},
  };
}

void render_frames(RealtimeEngine& engine, std::uint64_t frames) {
  std::array<float, 256> left{};
  std::array<float, 256> right{};
  while (frames != 0) {
    const auto block = static_cast<std::uint32_t>(
        std::min<std::uint64_t>(frames, left.size()));
    engine.render(left.data(), right.data(), block);
    frames -= block;
  }
}

PadControlEvent control(
    std::uint64_t sequence,
    std::uint8_t slot,
    PadControlKind kind,
    std::uint8_t velocity = 0,
    ResolvedPlayback playback = {}) {
  return PadControlEvent{sequence, slot, velocity, kind, playback};
}

std::array<RuntimeVoiceStateEvent, 16> drain_voice_states(
    RealtimeEngine& engine,
    std::size_t expected) {
  std::array<RuntimeVoiceStateEvent, 16> states{};
  LMDJ_CHECK(engine.drain_voice_states(states) == expected);
  return states;
}

PreparedSampleBank bank_with_pcm_snapshot(const RuntimeSnapshot& snapshot) {
  auto bank = PreparedSampleBank::empty(snapshot.project_id,
                                         snapshot.project_revision);
  for (const auto& pad : snapshot.pads) {
    LMDJ_CHECK(bank.set_pcm_sample(
        static_cast<std::uint8_t>(pad.slot.bank * 16 + pad.slot.pad),
        pad.sample, pad.playback).has_value());
  }
  return bank;
}

void pcm_and_float_banks_render_identical_live_pattern_and_audition() {
  for (const auto channels : {std::uint16_t{1}, std::uint16_t{2}}) {
    for (const auto mode : {TriggerMode::one_shot, TriggerMode::gate,
                           TriggerMode::loop_gate, TriggerMode::loop_toggle}) {
      for (const bool muted : {false, true}) {
        auto snapshot = pattern_snapshot(kPatternA, {0, 0}, 79);
        std::vector<std::int16_t> values(512 * channels);
        constexpr std::array<std::int16_t, 7> extremes{
            -32'768, 32'767, -16'384, 16'384, -1, 1, 0};
        for (std::size_t index = 0; index < values.size(); ++index)
          values[index] = extremes[index % extremes.size()];
        const auto pcm = std::make_shared<const lmdj::cooker::PcmSample>(
            lmdj::cooker::PcmSample{48'000, channels, std::move(values)});
        snapshot.pads[0].sample = pcm;
        snapshot.pads[0].playback = {3, 410, mode, 0.25F, muted};
        snapshot.events[0].sample = pcm;
        auto second = snapshot.pads[0];
        second.slot = {0, 1};
        second.playback = {5, 380, mode, 0.5F, muted};
        snapshot.pads.push_back(std::move(second));
        auto floats = PreparedSampleBank::from_snapshot(snapshot);
        LMDJ_CHECK(floats.has_value());
        RealtimeEngine reference, actual;
        LMDJ_CHECK(reference.publish_sample_bank(std::move(floats.value())) ==
                   PublishResult::accepted);
        LMDJ_CHECK(actual.publish_sample_bank(bank_with_pcm_snapshot(snapshot)) ==
                   PublishResult::accepted);
        for (auto* engine : {&reference, &actual}) {
          auto pattern = PreparedPatternView::from_snapshot(snapshot);
          LMDJ_CHECK(pattern.has_value());
          LMDJ_CHECK(engine->publish_pattern_view(std::move(pattern.value())).result ==
                     PatternPublishResult::accepted);
          LMDJ_CHECK(engine->start().has_value());
        }
        const auto submit = [&](PadControlEvent event) {
          LMDJ_CHECK(reference.enqueue_control(event) == EnqueueResult::accepted);
          LMDJ_CHECK(actual.enqueue_control(event) == EnqueueResult::accepted);
        };
        const auto compare = [&](std::uint32_t frames) {
          std::array<float, 256> left{}, right{}, expected_left{}, expected_right{};
          g_allocations.store(0);
          g_deallocations.store(0);
          g_track_allocations.store(true);
          reference.render(expected_left.data(), expected_right.data(), frames);
          actual.render(left.data(), right.data(), frames);
          g_track_allocations.store(false);
          LMDJ_CHECK(g_allocations.load() == 0 && g_deallocations.load() == 0);
          LMDJ_CHECK(left == expected_left && right == expected_right);
          LMDJ_CHECK(actual.telemetry().active_voices ==
                     reference.telemetry().active_voices);
          return std::any_of(left.begin(), left.end(), [](float value) {
            return value != 0;
          });
        };
        submit(control(1, 1, PadControlKind::press, 103));
        LMDJ_CHECK(compare(127) == !muted);
        submit(control(2, 1, PadControlKind::preview_set, 0,
                       {7, 300, mode, 0.375F, muted}));
        submit(control(3, 1, PadControlKind::press, 91));
        (void)compare(127);
        submit(control(4, 1, PadControlKind::release));
        (void)compare(256);
        submit(control(5, 1, PadControlKind::stop_slot));
        (void)compare(256);
        submit(control(6, 1, PadControlKind::preview_clear));
        snapshot.pads.erase(snapshot.pads.begin() + 1, snapshot.pads.end());
        snapshot.pads[0].playback = {3, 410, mode, 0.25F, false};
        auto audition_float = PreparedSampleBank::from_snapshot(snapshot);
        LMDJ_CHECK(audition_float.has_value());
        LMDJ_CHECK(reference.publish_audition_bank(std::move(audition_float.value())) ==
                   PublishResult::accepted);
        LMDJ_CHECK(actual.publish_audition_bank(bank_with_pcm_snapshot(snapshot)) ==
                   PublishResult::accepted);
        submit(control(7, 0, PadControlKind::audition_start, 127));
        LMDJ_CHECK(compare(127));
        submit(control(8, 0, PadControlKind::audition_stop));
        (void)compare(256);
        reference.stop();
        actual.stop();
        LMDJ_CHECK(!compare(256));
      }
    }
  }
}

void pcm_replacement_releases_the_actual_float_allocation() {
  g_allocations.store(0);
  g_deallocations.store(0);
  g_track_allocations.store(true);
  auto* ordinary = ::operator new(37);
  auto* aligned = ::operator new(129, std::align_val_t{64});
  ::operator delete(ordinary);
  ::operator delete(aligned, std::align_val_t{64});
  g_track_allocations.store(false);
  LMDJ_CHECK(g_allocations.load() == 2 && g_deallocations.load() == 2);
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, 1);
  const std::array<float, 4> floats{0, 0.25F, 0.5F, 1};
  LMDJ_CHECK(bank.set_sample(0, floats).has_value());
  const auto pcm = std::make_shared<const lmdj::cooker::PcmSample>(
      lmdj::cooker::PcmSample{48'000, 1, {0, 8192, 16384, 32767}});
  g_allocations.store(0);
  g_deallocations.store(0);
  g_track_allocations.store(true);
  const auto assigned = bank.set_pcm_sample(0, pcm,
      {0, 4, TriggerMode::one_shot, 1, false});
  g_track_allocations.store(false);
  LMDJ_CHECK(assigned.has_value());
  LMDJ_CHECK(g_allocations.load() == 0 && g_deallocations.load() == 1);
  LMDJ_CHECK(bank.decoded_pcm_bytes() == 8);
}

void pcm_old_bank_lives_until_control_reclaims_after_voice_completion() {
  RealtimeEngine engine;
  auto owner = std::make_shared<const lmdj::cooker::PcmSample>(
      lmdj::cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(1024, 16'384)});
  std::weak_ptr<const lmdj::cooker::PcmSample> lifetime = owner;
  auto old_bank = PreparedSampleBank::empty(ProjectId{kProjectId}, 1);
  LMDJ_CHECK(old_bank.set_pcm_sample(0, owner,
      {0, 1024, TriggerMode::one_shot, 1, false}).has_value());
  owner.reset();
  LMDJ_CHECK(engine.publish_sample_bank(std::move(old_bank)) == PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue({1, 0, 127}) == EnqueueResult::accepted);
  render_frames(engine, 1);
  const std::array<float, 1> next{0.25F};
  LMDJ_CHECK(engine.publish_sample_bank(bank_with_sample(2, next)) == PublishResult::accepted);
  std::array<float, 128> left{}, right{};
  g_allocations.store(0);
  g_deallocations.store(0);
  g_track_allocations.store(true);
  engine.render(left.data(), right.data(), left.size());
  g_track_allocations.store(false);
  LMDJ_CHECK(g_allocations.load() == 0 && g_deallocations.load() == 0);
  LMDJ_CHECK(engine.bank_telemetry().current_generation == 2);
  LMDJ_CHECK(left.back() == lmdj::audio::prepared_pcm16_to_float(16'384));
  LMDJ_CHECK(!lifetime.expired());
  LMDJ_CHECK(engine.reclaim_retired_banks() == 0);
  g_track_allocations.store(true);
  render_frames(engine, 1024);
  g_track_allocations.store(false);
  LMDJ_CHECK(g_allocations.load() == 0 && g_deallocations.load() == 0);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(!lifetime.expired());
  const auto reclaimed = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(reclaimed.count == 1 && reclaimed.decoded_pcm_bytes == 2048);
  LMDJ_CHECK(lifetime.expired());
  LMDJ_CHECK(engine.reclaim_retired_banks() == 0);
}

void fixed_control_and_voice_messages_are_realtime_safe_values() {
  static_assert(std::is_trivially_copyable_v<PadControlEvent>);
  static_assert(std::is_trivially_copyable_v<RuntimeVoiceStateEvent>);
  static_assert(lmdj::audio::kRealtimeQueueCapacity == 1'024);
  static_assert(
      lmdj::audio::kRealtimeVoiceStateCapacity ==
      (lmdj::audio::kRealtimeCaptureCapacity +
       lmdj::audio::kRealtimeQueueCapacity) * 2);
}

void one_shot_snapshots_trim_gain_and_ignores_release() {
  RealtimeEngine engine;
  const std::array<float, 5> sample{0.05F, 0.2F, 0.3F, 0.4F, 0.95F};
  auto bank = bank_with_playback(
      1,
      sample,
      ResolvedPlayback{1, 4, TriggerMode::one_shot, 0.5F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue_control(control(10, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);

  std::array<float, 2> left{};
  std::array<float, 2> right{};
  // F6 ramp: the first rendered frame carries attack gain 0/96.
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.0F && right.at(0) == 0.0F);
  LMDJ_CHECK(
      engine.enqueue_control(control(11, 0, PadControlKind::release)) ==
      EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 2);
  // F6 ramp: attack (1/96 then 2/96) times the non-looping boundary fade
  // (end_frame - cursor is 2 then 1).
  LMDJ_CHECK(left.at(0) == 0.3F * 0.5F * (ramp_part(1) * ramp_part(2)));
  LMDJ_CHECK(left.at(1) == 0.4F * 0.5F * (ramp_part(2) * ramp_part(1)));
  LMDJ_CHECK(right == left);

  const auto states = drain_voice_states(engine, 2);
  LMDJ_CHECK(states.at(0).sequence == 10);
  LMDJ_CHECK(states.at(0).slot == 0);
  LMDJ_CHECK(states.at(0).state == RuntimeVoiceState::started);
  LMDJ_CHECK(states.at(0).runtime_frame == 0);
  LMDJ_CHECK(states.at(0).source_frame == 1);
  LMDJ_CHECK(states.at(1).sequence == 10);
  LMDJ_CHECK(states.at(1).slot == 0);
  LMDJ_CHECK(states.at(1).state == RuntimeVoiceState::completed);
  LMDJ_CHECK(states.at(1).runtime_frame == 3);
  LMDJ_CHECK(states.at(1).source_frame == 4);
}

void gate_release_fades_a_ramp_tail_from_the_exact_cursor() {
  RealtimeEngine engine;
  const std::array<float, 5> sample{0.1F, 0.2F, 0.3F, 0.4F, 0.5F};
  auto bank = bank_with_playback(
      2,
      sample,
      ResolvedPlayback{1, 5, TriggerMode::gate, 1.0F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue_control(control(20, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  std::array<float, 2> left{};
  std::array<float, 2> right{};
  engine.render(left.data(), right.data(), 2);
  const std::array<float, 2> expected_gate{
      0.0F,
      0.3F * (ramp_part(1) * ramp_part(3))};
  LMDJ_CHECK(left == expected_gate);

  LMDJ_CHECK(
      engine.enqueue_control(control(21, 0, PadControlKind::release)) ==
      EnqueueResult::accepted);
  left.fill(1.0F);
  right.fill(1.0F);
  engine.render(left.data(), right.data(), 2);
  // F6 ramp: the release no longer silences the voice at once. The stopped
  // edge is published at stop initiation (below) while the voice renders a
  // ramped tail: attack times boundary times the release factor (full scale
  // on the first tail frame, 95/96 on the second). The tail reaches
  // end_frame on the second frame and the voice deactivates there.
  const std::array<float, 2> expected_tail{
      0.4F * (ramp_part(2) * ramp_part(2)),
      0.5F * ((ramp_part(3) * ramp_part(1)) * ramp_part(95))};
  LMDJ_CHECK(left == expected_tail);
  LMDJ_CHECK(right == left);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.telemetry().cancelled_voices == 1);

  const auto states = drain_voice_states(engine, 2);
  LMDJ_CHECK(states.at(0).state == RuntimeVoiceState::started);
  LMDJ_CHECK(states.at(0).runtime_frame == 0);
  LMDJ_CHECK(states.at(0).source_frame == 1);
  LMDJ_CHECK(states.at(1).sequence == 20);
  LMDJ_CHECK(states.at(1).state == RuntimeVoiceState::stopped);
  LMDJ_CHECK(states.at(1).runtime_frame == 2);
  LMDJ_CHECK(states.at(1).source_frame == 3);
}

void loop_gate_wraps_only_inside_the_selection_then_releases() {
  RealtimeEngine engine;
  const std::array<float, 4> sample{0.9F, 0.1F, 0.2F, 0.8F};
  auto bank = bank_with_playback(
      3,
      sample,
      ResolvedPlayback{1, 3, TriggerMode::loop_gate, 1.0F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue_control(control(30, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  std::array<float, 5> left{};
  std::array<float, 5> right{};
  engine.render(left.data(), right.data(), 5);
  // F6 ramp: the attack counter keeps rising across the loop wrap — the
  // wrap does NOT restart the ramp — and looping voices get no boundary
  // fade.
  const std::array<float, 5> expected_loop{
      0.0F,
      0.2F * ramp_part(1),
      0.1F * ramp_part(2),
      0.2F * ramp_part(3),
      0.1F * ramp_part(4)};
  LMDJ_CHECK(left == expected_loop);
  LMDJ_CHECK(right == left);

  LMDJ_CHECK(
      engine.enqueue_control(control(31, 0, PadControlKind::release)) ==
      EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: the stopped edge is published at stop initiation (below) while
  // the voice renders its release tail; the first tail frame carries the
  // full release scale times the current attack factor.
  LMDJ_CHECK(left.at(0) == 0.2F * ramp_part(5));
  LMDJ_CHECK(right == left);
  const auto states = drain_voice_states(engine, 2);
  LMDJ_CHECK(states.at(1).sequence == 30);
  LMDJ_CHECK(states.at(1).state == RuntimeVoiceState::stopped);
  LMDJ_CHECK(states.at(1).runtime_frame == 5);
  LMDJ_CHECK(states.at(1).source_frame == 2);
}

void loop_toggle_is_latched_per_pad_and_stops_on_its_next_press() {
  RealtimeEngine engine;
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, 4);
  const std::array<float, 2> first{0.1F, 0.2F};
  const std::array<float, 2> second{0.3F, 0.4F};
  const auto toggle =
      ResolvedPlayback{0, 2, TriggerMode::loop_toggle, 1.0F, false};
  LMDJ_CHECK(bank.set_sample(0, first, toggle).has_value());
  LMDJ_CHECK(bank.set_sample(1, second, toggle).has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};

  LMDJ_CHECK(
      engine.enqueue_control(control(40, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: the first rendered frame carries attack gain 0/96.
  LMDJ_CHECK(left.at(0) == 0.0F);
  LMDJ_CHECK(
      engine.enqueue_control(control(41, 1, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.2F * ramp_part(1));
  LMDJ_CHECK(engine.telemetry().active_voices == 2);

  LMDJ_CHECK(
      engine.enqueue_control(control(42, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: the toggled voice keeps rendering its release tail, so it is
  // still active and audible (first tail frame at full release scale). The
  // expectation mirrors the engine's per-voice rounding exactly: each
  // voice term is rounded through a named value before the accumulation,
  // so no FMA contraction can reorder rounding.
  const float toggle_tail = 0.1F * ramp_part(2);
  const float latched_second = 0.4F * ramp_part(1);
  float expected_mix = 0.0F;
  expected_mix += toggle_tail;
  expected_mix += latched_second;
  LMDJ_CHECK(left.at(0) == expected_mix);
  LMDJ_CHECK(engine.telemetry().active_voices == 2);
  // The tail lasts exactly kRealtimeRampFrames rendered frames: one above
  // plus 95 more, then the voice deactivates.
  std::array<float, 95> tail_left{};
  std::array<float, 95> tail_right{};
  engine.render(tail_left.data(), tail_right.data(), 95);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
  LMDJ_CHECK(engine.telemetry().cancelled_voices == 1);
  const auto states = drain_voice_states(engine, 3);
  LMDJ_CHECK(states.at(0).sequence == 40);
  LMDJ_CHECK(states.at(0).slot == 0);
  LMDJ_CHECK(states.at(0).state == RuntimeVoiceState::started);
  LMDJ_CHECK(states.at(1).sequence == 41);
  LMDJ_CHECK(states.at(1).slot == 1);
  LMDJ_CHECK(states.at(1).state == RuntimeVoiceState::started);
  LMDJ_CHECK(states.at(2).sequence == 40);
  LMDJ_CHECK(states.at(2).slot == 0);
  LMDJ_CHECK(states.at(2).state == RuntimeVoiceState::stopped);
  LMDJ_CHECK(states.at(2).runtime_frame == 2);
  LMDJ_CHECK(states.at(2).source_frame == 0);
}

void mute_starts_no_voice_and_invalid_preview_bounds_are_rejected() {
  RealtimeEngine engine;
  const std::array<float, 3> sample{0.25F, 0.5F, 0.75F};
  auto bank = bank_with_playback(
      5,
      sample,
      ResolvedPlayback{0, 3, TriggerMode::one_shot, 1.0F, true});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{50, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 3> left{};
  std::array<float, 3> right{};
  engine.render(left.data(), right.data(), 3);
  const std::array<float, 3> silence{};
  LMDJ_CHECK(left == silence);
  LMDJ_CHECK(right == left);
  LMDJ_CHECK(engine.telemetry().started_voices == 0);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.drain_voice_states(
                 std::span<RuntimeVoiceStateEvent>{}) == 0);

  for (const auto invalid : {
           ResolvedPlayback{1, 1, TriggerMode::gate, 1.0F, false},
           ResolvedPlayback{0, 4, TriggerMode::gate, 1.0F, false},
           ResolvedPlayback{
               0,
               3,
               TriggerMode::gate,
               std::numeric_limits<float>::infinity(),
               false},
       }) {
    LMDJ_CHECK(
        engine.enqueue_control(control(
            51, 0, PadControlKind::preview_set, 0, invalid)) ==
        EnqueueResult::invalid_velocity);
  }
}

void preview_set_and_clear_affect_only_later_voice_snapshots() {
  RealtimeEngine engine;
  const std::array<float, 4> sample{0.2F, 0.4F, 0.6F, 0.8F};
  auto bank = bank_with_playback(
      6,
      sample,
      ResolvedPlayback{0, 4, TriggerMode::one_shot, 1.0F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue_control(control(
          60,
          0,
          PadControlKind::preview_set,
          0,
          ResolvedPlayback{
              1, 3, TriggerMode::one_shot, 0.5F, false})) ==
      EnqueueResult::accepted);
  LMDJ_CHECK(
      engine.enqueue_control(control(61, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  LMDJ_CHECK(
      engine.enqueue_control(control(62, 0, PadControlKind::preview_clear)) ==
      EnqueueResult::accepted);

  std::array<float, 4> left{};
  std::array<float, 4> right{};
  engine.render(left.data(), right.data(), 3);
  // F6 ramp: attack 0/96 on the first frame, then attack times the
  // non-looping boundary fade (the preview selection is 2 frames long).
  LMDJ_CHECK(left.at(0) == 0.0F);
  LMDJ_CHECK(left.at(1) == 0.6F * 0.5F * (ramp_part(1) * ramp_part(1)));
  LMDJ_CHECK(left.at(2) == 0.0F);
  LMDJ_CHECK(right == left);

  LMDJ_CHECK(
      engine.enqueue_control(control(63, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 4);
  const std::array<float, 4> expected_second{
      0.0F,
      0.4F * (ramp_part(1) * ramp_part(3)),
      0.6F * (ramp_part(2) * ramp_part(2)),
      0.8F * (ramp_part(3) * ramp_part(1))};
  LMDJ_CHECK(left == expected_second);
  LMDJ_CHECK(right == left);
  const auto states = drain_voice_states(engine, 4);
  LMDJ_CHECK(states.at(0).sequence == 61);
  LMDJ_CHECK(states.at(0).source_frame == 1);
  LMDJ_CHECK(states.at(1).sequence == 61);
  LMDJ_CHECK(states.at(1).state == RuntimeVoiceState::completed);
  LMDJ_CHECK(states.at(1).runtime_frame == 2);
  LMDJ_CHECK(states.at(1).source_frame == 3);
  LMDJ_CHECK(states.at(2).sequence == 63);
  LMDJ_CHECK(states.at(2).runtime_frame == 3);
  LMDJ_CHECK(states.at(2).source_frame == 0);
  LMDJ_CHECK(states.at(3).sequence == 63);
  LMDJ_CHECK(states.at(3).runtime_frame == 7);
  LMDJ_CHECK(states.at(3).source_frame == 4);
}

void legacy_enqueue_uses_published_snapshot_while_preview_is_active() {
  RealtimeEngine engine;
  const std::array<float, 4> sample{0.2F, 0.4F, 0.6F, 0.8F};
  auto bank = bank_with_playback(
      7,
      sample,
      ResolvedPlayback{0, 2, TriggerMode::one_shot, 0.5F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue_control(control(
          64,
          0,
          PadControlKind::preview_set,
          0,
          ResolvedPlayback{
              2, 4, TriggerMode::one_shot, 0.25F, false})) ==
      EnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{65, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 2> left{};
  std::array<float, 2> right{};
  engine.render(left.data(), right.data(), 2);

  // F6 ramp: attack times the boundary fade on the 2-frame published
  // selection.
  const std::array<float, 2> published{
      0.0F,
      0.4F * 0.5F * (ramp_part(1) * ramp_part(1))};
  LMDJ_CHECK(left == published);
  LMDJ_CHECK(right == published);
  const auto states = drain_voice_states(engine, 2);
  LMDJ_CHECK(states.at(0).sequence == 65);
  LMDJ_CHECK(states.at(0).state == RuntimeVoiceState::started);
  LMDJ_CHECK(states.at(0).runtime_frame == 0);
  LMDJ_CHECK(states.at(0).source_frame == 0);
  LMDJ_CHECK(states.at(1).sequence == 65);
  LMDJ_CHECK(states.at(1).state == RuntimeVoiceState::completed);
  LMDJ_CHECK(states.at(1).runtime_frame == 2);
  LMDJ_CHECK(states.at(1).source_frame == 2);
}

void direct_press_never_falls_back_from_non_sentinel_invalid_playback() {
  RealtimeEngine engine;
  const std::array<float, 2> sample{0.25F, 0.5F};
  auto bank = bank_with_playback(
      8,
      sample,
      ResolvedPlayback{0, 2, TriggerMode::one_shot, 1.0F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue_control(control(
          66,
          0,
          PadControlKind::preview_set,
          0,
          ResolvedPlayback{
              0, 1, TriggerMode::one_shot, 1.0F, false})) ==
      EnqueueResult::accepted);
  LMDJ_CHECK(
      engine.enqueue_control(control(
          67,
          0,
          PadControlKind::press,
          127,
          ResolvedPlayback{
              0, 3, TriggerMode::one_shot, 1.0F, false})) ==
      EnqueueResult::accepted);

  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  LMDJ_CHECK(left.at(0) == 0.0F);
  LMDJ_CHECK(right.at(0) == 0.0F);
  LMDJ_CHECK(engine.telemetry().invalid_events == 1);
  std::array<RuntimeVoiceStateEvent, 1> states{};
  LMDJ_CHECK(engine.drain_voice_states(states) == 0);
}

void control_queue_overflow_rejects_preview_without_applying_it() {
  RealtimeEngine engine;
  const std::array<float, 2> sample{0.25F, 0.5F};
  auto bank = bank_with_playback(
      7,
      sample,
      ResolvedPlayback{0, 2, TriggerMode::one_shot, 1.0F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  for (std::uint64_t sequence = 0;
       sequence < lmdj::audio::kRealtimeQueueCapacity;
       ++sequence) {
    LMDJ_CHECK(engine.enqueue_control(control(
                   sequence, 0, PadControlKind::preview_clear)) ==
               EnqueueResult::accepted);
  }
  LMDJ_CHECK(
      engine.enqueue_control(control(
          1'024,
          0,
          PadControlKind::preview_set,
          0,
          ResolvedPlayback{
              1, 2, TriggerMode::one_shot, 0.25F, false})) ==
      EnqueueResult::queue_full);
  LMDJ_CHECK(engine.telemetry().queue_drops == 1);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  LMDJ_CHECK(
      engine.enqueue_control(control(1'025, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: attack gain 0/96 on the first rendered frame.
  LMDJ_CHECK(left.at(0) == 0.0F && right.at(0) == 0.0F);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(
      left.at(0) == 0.5F * (ramp_part(1) * ramp_part(1)) &&
      right.at(0) == left.at(0));
}

void stop_slot_targets_one_pad_and_stop_all_clears_latched_voices() {
  RealtimeEngine engine;
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, 8);
  const std::array<float, 4> ordinary{0.1F, 0.1F, 0.1F, 0.1F};
  const std::array<float, 2> latched{0.3F, 0.4F};
  LMDJ_CHECK(bank.set_sample(
                     0,
                     ordinary,
                     ResolvedPlayback{
                         0, 4, TriggerMode::one_shot, 1.0F, false})
                 .has_value());
  LMDJ_CHECK(bank.set_sample(
                     1,
                     latched,
                     ResolvedPlayback{
                         0, 2, TriggerMode::loop_toggle, 1.0F, false})
                 .has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue_control(control(70, 0, PadControlKind::press, 127)) ==
             EnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue_control(control(71, 1, PadControlKind::press, 127)) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: both voices are on attack frame 0/96.
  LMDJ_CHECK(left.at(0) == 0.0F);

  LMDJ_CHECK(engine.enqueue_control(control(72, 0, PadControlKind::stop_slot)) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: the stopped one-shot keeps rendering its release tail
  // (full release scale on the first tail frame) next to the latched loop.
  // Each voice term is rounded through a named value before accumulation
  // so no FMA contraction can reorder rounding.
  const float stopped_tail = 0.1F * (ramp_part(1) * ramp_part(3));
  const float latched_loop = 0.4F * ramp_part(1);
  float expected_mix = 0.0F;
  expected_mix += stopped_tail;
  expected_mix += latched_loop;
  LMDJ_CHECK(left.at(0) == expected_mix);
  LMDJ_CHECK(engine.telemetry().active_voices == 2);
  LMDJ_CHECK(engine.enqueue_control(control(73, 0, PadControlKind::press, 127)) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.telemetry().active_voices == 3);

  LMDJ_CHECK(engine.enqueue_control(control(74, 0, PadControlKind::stop_all)) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: stop_all hard-kills the already-releasing one-shot (no second
  // stopped publication) and starts release tails on the other two voices.
  const float latched_tail = 0.4F * ramp_part(3);
  const float restarted_tail = 0.1F * (ramp_part(1) * ramp_part(3));
  float expected_stop_all = 0.0F;
  expected_stop_all += latched_tail;
  expected_stop_all += restarted_tail;
  LMDJ_CHECK(left.at(0) == expected_stop_all);
  LMDJ_CHECK(engine.telemetry().active_voices == 2);
  // The tails last exactly kRealtimeRampFrames rendered frames: one above
  // plus 95 more, then both voices deactivate.
  std::array<float, 95> tail_left{};
  std::array<float, 95> tail_right{};
  engine.render(tail_left.data(), tail_right.data(), 95);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.telemetry().cancelled_voices == 3);
  const auto states = drain_voice_states(engine, 6);
  LMDJ_CHECK(states.at(2).sequence == 70);
  LMDJ_CHECK(states.at(2).slot == 0);
  LMDJ_CHECK(states.at(2).state == RuntimeVoiceState::stopped);
  LMDJ_CHECK(states.at(2).runtime_frame == 1);
  LMDJ_CHECK(states.at(3).sequence == 73);
  LMDJ_CHECK(states.at(3).state == RuntimeVoiceState::started);
  LMDJ_CHECK(states.at(4).state == RuntimeVoiceState::stopped);
  LMDJ_CHECK(states.at(5).state == RuntimeVoiceState::stopped);
}

void check_voice_state_overflow(RealtimeEngine& engine, std::size_t capacity) {
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  for (std::uint64_t sequence = 1;
       sequence <= capacity / 2;
       ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
    engine.render(left.data(), right.data(), 1);
    std::array<RuntimeTriggerOutcomeEvent, 1> outcome{};
    LMDJ_CHECK(engine.drain_trigger_outcomes(outcome) == 1);
  }
  LMDJ_CHECK(
      engine.enqueue(TriggerEvent{3'000, 0, 127}) == EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);

  const auto states = engine.voice_state_telemetry();
  LMDJ_CHECK(
      states.state == lmdj::audio::RuntimeVoiceStateStreamState::corrupted);
  LMDJ_CHECK(
      states.published_voice_states == capacity);
  LMDJ_CHECK(states.drained_voice_states == 0);
  LMDJ_CHECK(states.voice_state_drops == 1);
  const auto outcomes = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(
      outcomes.published_outcomes ==
      capacity / 2);
  LMDJ_CHECK(
      outcomes.drained_outcomes ==
      capacity / 2);
  LMDJ_CHECK(outcomes.runtime_outcome_drops == 0);
  LMDJ_CHECK(engine.telemetry().started_voices ==
             capacity / 2);
  LMDJ_CHECK(engine.telemetry().voice_drops == 1);

  std::array<RuntimeVoiceStateEvent, 1> first{};
  LMDJ_CHECK(engine.drain_voice_states(first) == 0);
  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  const auto reset = engine.voice_state_telemetry();
  LMDJ_CHECK(
      reset.state == lmdj::audio::RuntimeVoiceStateStreamState::healthy);
  LMDJ_CHECK(reset.published_voice_states == 0);
  LMDJ_CHECK(reset.drained_voice_states == 0);
  LMDJ_CHECK(reset.voice_state_drops == 0);
  LMDJ_CHECK(engine.drain_voice_states(first) == 0);
}

void voice_state_overflow_raises_the_existing_fail_closed_signal() {
  RealtimeEngine engine;
  check_voice_state_overflow(engine, lmdj::audio::kRealtimeVoiceStateCapacity);
  RealtimeEngine bounded(RealtimeEngine::ReceiptBoundedVoiceStates{});
  // Deliberately violate the opt-in caller's receipt/drain obligation. A smaller
  // profile still corrupts/refuses rather than dropping history silently.
  check_voice_state_overflow(bounded, lmdj::audio::kRealtimeReceiptVoiceStateCapacity);
}

void plays_a_sample_and_reports_render_telemetry() {
  RealtimeEngine engine;
  const std::array<float, 2> sample{0.5F, -0.5F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{9, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: attack gain 0/96 on the first rendered frame.
  LMDJ_CHECK(left[0] == 0.0F && right[0] == 0.0F);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(
      left[0] == -0.5F * (ramp_part(1) * ramp_part(1)) &&
      right[0] == left[0]);

  std::array<RuntimeTriggerOutcomeEvent, 1> outcomes{};
  LMDJ_CHECK(engine.drain_trigger_outcomes(outcomes) == 1);
  LMDJ_CHECK(outcomes.at(0).sequence == 9);
  LMDJ_CHECK(
      outcomes.at(0).outcome == RuntimeTriggerOutcome::voice_started);
  LMDJ_CHECK(outcomes.at(0).runtime_frame == 0);

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.enqueued_events == 1);
  LMDJ_CHECK(telemetry.dequeued_events == 1);
  LMDJ_CHECK(telemetry.started_voices == 1);
  LMDJ_CHECK(telemetry.completed_voices == 1);
  LMDJ_CHECK(telemetry.active_voices == 0);
  LMDJ_CHECK(telemetry.callback_count == 2);
  LMDJ_CHECK(telemetry.rendered_frames == 2);
  LMDJ_CHECK(telemetry.max_callback_frames == 1);
  const auto outcomes_telemetry = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(outcomes_telemetry.published_outcomes == 1);
  LMDJ_CHECK(outcomes_telemetry.drained_outcomes == 1);
  LMDJ_CHECK(outcomes_telemetry.runtime_outcome_drops == 0);
}

void rejects_invalid_samples_and_running_time_mutation() {
  RealtimeEngine engine;
  const std::array<float, 1> valid{0.25F};
  const std::array<float, 1> nan{std::numeric_limits<float>::quiet_NaN()};
  const std::array<float, 1> infinity{
      std::numeric_limits<float>::infinity()};
  const std::span<const float> empty;

  const auto invalid_slot = engine.load_sample(64, valid);
  LMDJ_CHECK(!invalid_slot.has_value());
  LMDJ_CHECK(invalid_slot.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!engine.load_sample(0, empty).has_value());
  LMDJ_CHECK(!engine.load_sample(0, nan).has_value());
  LMDJ_CHECK(!engine.load_sample(0, infinity).has_value());
  LMDJ_CHECK(!engine.clear_sample(64).has_value());

  LMDJ_CHECK(engine.load_sample(0, valid).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(!engine.load_sample(0, valid).has_value());
  LMDJ_CHECK(!engine.clear_sample(0).has_value());
  LMDJ_CHECK(!engine.start().has_value());
}

void supports_exact_64_slot_boundary() {
  static_assert(lmdj::audio::kRealtimeSampleSlots == 64);

  RealtimeEngine engine;
  const std::array<float, 1> sample{0.625F};
  LMDJ_CHECK(engine.load_sample(63, sample).has_value());
  const auto invalid_load = engine.load_sample(64, sample);
  LMDJ_CHECK(!invalid_load.has_value());
  LMDJ_CHECK(invalid_load.error().code == ErrorCode::invalid_argument);

  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 63, 127}) ==
             EnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 64, 127}) ==
             EnqueueResult::invalid_slot);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: a one-frame voice renders only its attack-0 frame; the voice
  // still completes on schedule.
  LMDJ_CHECK(left[0] == 0.0F && right[0] == 0.0F);
  LMDJ_CHECK(engine.telemetry().completed_voices == 1);

  engine.stop();
  LMDJ_CHECK(engine.clear_sample(63).has_value());
  const auto invalid_clear = engine.clear_sample(64);
  LMDJ_CHECK(!invalid_clear.has_value());
  LMDJ_CHECK(invalid_clear.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 63, 127}) ==
             EnqueueResult::sample_unavailable);
}

void validates_events_and_cleared_slots() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{1.0F};

  LMDJ_CHECK(engine.enqueue(TriggerEvent{0, 0, 127}) ==
             EnqueueResult::not_running);
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.load_sample(1, sample).has_value());
  LMDJ_CHECK(engine.clear_sample(1).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 64, 127}) ==
             EnqueueResult::invalid_slot);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 0}) ==
             EnqueueResult::invalid_velocity);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 0, 128}) ==
             EnqueueResult::invalid_velocity);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{4, 2, 127}) ==
             EnqueueResult::sample_unavailable);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{5, 1, 127}) ==
             EnqueueResult::sample_unavailable);

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.invalid_events == 5);
  LMDJ_CHECK(telemetry.stopped_rejections == 0);
}

void applies_velocity_gain_and_clamps_after_mixing() {
  RealtimeEngine engine;
  const std::array<float, 2> unit{1.0F, 1.0F};
  LMDJ_CHECK(engine.load_sample(0, unit).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 64}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: attack gain 0/96 on the first rendered frame.
  LMDJ_CHECK(left[0] == 0.0F && right[0] == 0.0F);
  engine.render(left.data(), right.data(), 1);
  const auto expected_velocity =
      1.0F * (64.0F / 127.0F) * (ramp_part(1) * ramp_part(1));
  LMDJ_CHECK(left[0] == expected_velocity);
  LMDJ_CHECK(right[0] == expected_velocity);

  engine.stop();
  // Long enough to reach full scale: 96 attack frames, then a full-gain
  // plateau before the 96-frame boundary fade.
  const std::array<float, 200> loud = [] {
    std::array<float, 200> value{};
    value.fill(0.8F);
    return value;
  }();
  LMDJ_CHECK(engine.load_sample(0, loud).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 100> mix_left{};
  std::array<float, 100> mix_right{};
  engine.render(mix_left.data(), mix_right.data(), 100);
  // On the full-gain plateau the two voices sum to 1.6 and clamp to 1.0.
  LMDJ_CHECK(mix_left[96] == 1.0F && mix_right[96] == 1.0F);
  LMDJ_CHECK(mix_left[99] == 1.0F && mix_right[99] == 1.0F);
}

void reports_queue_capacity_and_drops() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{1.0F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (std::uint64_t sequence = 0; sequence < 1'024; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1'024, 0, 127}) ==
             EnqueueResult::queue_full);

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.enqueued_events == 1'024);
  LMDJ_CHECK(telemetry.queued_events == 1'024);
  LMDJ_CHECK(telemetry.queue_drops == 1);
}

void caps_simultaneous_voices_and_mixes_each_admitted_voice() {
  RealtimeEngine engine;
  constexpr float kVoiceAmplitude = 1.0F / 1'024.0F;
  const std::array<float, 2> sample{kVoiceAmplitude, kVoiceAmplitude};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (std::uint64_t sequence = 0; sequence < 129; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  // F6 ramp: every admitted voice is on attack frame 0/96.
  LMDJ_CHECK(left[0] == 0.0F);
  LMDJ_CHECK(right[0] == 0.0F);
  const auto during = engine.telemetry();
  LMDJ_CHECK(during.started_voices == 128);
  LMDJ_CHECK(during.active_voices == 128);
  LMDJ_CHECK(during.voice_drops == 1);
  engine.render(left.data(), right.data(), 1);
  // The second frame mixes every admitted voice at attack 1/96 times the
  // boundary fade 1/96 (the sample is 2 frames long). The term is rounded
  // through a named value before accumulation, mirroring the engine's
  // per-voice rounding (no FMA contraction).
  const float ramped_voice = kVoiceAmplitude * (ramp_part(1) * ramp_part(1));
  float expected_mix = 0.0F;
  for (std::uint32_t voice = 0; voice < 128; ++voice) {
    expected_mix += ramped_voice;
  }
  LMDJ_CHECK(left[0] == expected_mix);
  LMDJ_CHECK(right[0] == expected_mix);
  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.started_voices == 128);
  LMDJ_CHECK(telemetry.completed_voices == 128);
  LMDJ_CHECK(telemetry.active_voices == 0);
  LMDJ_CHECK(telemetry.voice_drops == 1);
}

void publishes_ordered_mixed_outcomes_at_128_frame_boundaries() {
  RealtimeEngine engine;
  const std::array<float, 256> sample{};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());

  for (std::uint64_t sequence = 1; sequence <= 128; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  engine.render(left.data(), right.data(), 128);

  LMDJ_CHECK(engine.enqueue(TriggerEvent{129, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 128);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{130, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 128);

  std::array<RuntimeTriggerOutcomeEvent, 130> outcomes{};
  LMDJ_CHECK(engine.drain_trigger_outcomes(outcomes) == outcomes.size());
  for (std::uint64_t sequence = 1; sequence <= 128; ++sequence) {
    const auto& outcome = outcomes.at(sequence - 1);
    LMDJ_CHECK(outcome.sequence == sequence);
    LMDJ_CHECK(outcome.outcome == RuntimeTriggerOutcome::voice_started);
    LMDJ_CHECK(outcome.runtime_frame == 0);
  }
  LMDJ_CHECK(outcomes.at(128).sequence == 129);
  LMDJ_CHECK(
      outcomes.at(128).outcome == RuntimeTriggerOutcome::voice_capacity);
  LMDJ_CHECK(outcomes.at(128).runtime_frame == 128);
  LMDJ_CHECK(outcomes.at(129).sequence == 130);
  LMDJ_CHECK(
      outcomes.at(129).outcome == RuntimeTriggerOutcome::voice_started);
  LMDJ_CHECK(outcomes.at(129).runtime_frame == 256);

  const auto realtime = engine.telemetry();
  const auto outcome_telemetry = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(realtime.dequeued_events == outcomes.size());
  LMDJ_CHECK(realtime.started_voices == 129);
  LMDJ_CHECK(realtime.voice_drops == 1);
  LMDJ_CHECK(outcome_telemetry.published_outcomes == outcomes.size());
  LMDJ_CHECK(outcome_telemetry.drained_outcomes == outcomes.size());
  LMDJ_CHECK(outcome_telemetry.runtime_outcome_drops == 0);
}

void outcome_ring_reports_capacity_drop_and_restart_resets_it() {
  static_assert(lmdj::audio::kRealtimeTriggerOutcomeCapacity == 4'096);
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};

  for (std::uint64_t sequence = 1;
       sequence <= lmdj::audio::kRealtimeTriggerOutcomeCapacity + 1;
       ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
    engine.render(left.data(), right.data(), 1);
    std::array<RuntimeVoiceStateEvent, 2> voice_states{};
    LMDJ_CHECK(engine.drain_voice_states(voice_states) == 2);
  }

  const auto full = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(
      full.published_outcomes == lmdj::audio::kRealtimeTriggerOutcomeCapacity);
  LMDJ_CHECK(full.drained_outcomes == 0);
  LMDJ_CHECK(full.runtime_outcome_drops == 1);
  LMDJ_CHECK(engine.telemetry().dequeued_events ==
             full.published_outcomes + full.runtime_outcome_drops);

  std::array<RuntimeTriggerOutcomeEvent, 1> first{};
  LMDJ_CHECK(engine.drain_trigger_outcomes(first) == 1);
  LMDJ_CHECK(first.at(0).sequence == 1);
  LMDJ_CHECK(first.at(0).outcome == RuntimeTriggerOutcome::voice_started);
  LMDJ_CHECK(first.at(0).runtime_frame == 0);

  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  const auto reset = engine.trigger_outcome_telemetry();
  LMDJ_CHECK(reset.published_outcomes == 0);
  LMDJ_CHECK(reset.drained_outcomes == 0);
  LMDJ_CHECK(reset.runtime_outcome_drops == 0);
  LMDJ_CHECK(engine.drain_trigger_outcomes(first) == 0);
}

void completes_a_sample_across_callback_blocks() {
  RealtimeEngine engine;
  const std::array<float, 5> sample{0.1F, 0.2F, 0.3F, 0.4F, 0.5F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 3> left{};
  std::array<float, 3> right{};
  engine.render(left.data(), right.data(), 2);
  // F6 ramp: attack 0/96 on the first frame, then attack times the
  // non-looping boundary fade.
  LMDJ_CHECK(left[0] == 0.0F && left[1] == 0.2F * (ramp_part(1) * ramp_part(4)));
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
  engine.render(left.data(), right.data(), 3);
  LMDJ_CHECK(left[0] == 0.3F * (ramp_part(2) * ramp_part(3)));
  LMDJ_CHECK(left[1] == 0.4F * (ramp_part(3) * ramp_part(2)));
  LMDJ_CHECK(left[2] == 0.5F * (ramp_part(4) * ramp_part(1)));
  LMDJ_CHECK(engine.telemetry().completed_voices == 1);
  LMDJ_CHECK(engine.telemetry().max_callback_frames == 3);
}

void publishes_sample_banks_only_at_safe_render_boundaries() {
  static_assert(lmdj::audio::kRealtimeBankCapacity == 4);
  static_assert(lmdj::audio::kRealtimePublishQueueCapacity == 4);
  RealtimeEngine engine;
  const std::array<float, 3> old_sample{0.1F, 0.2F, 0.1F};
  auto first = bank_with_sample(10, old_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(first)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.bank_telemetry().current_generation == 1);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: attack gain 0/96 on the first rendered frame.
  LMDJ_CHECK(left.at(0) == 0.0F);

  const std::array<float, 1> new_sample{0.4F};
  auto second = bank_with_sample(11, new_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.bank_telemetry().pending_publications == 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::bank_transition);

  engine.render(left.data(), right.data(), 1);
  // The previous Bank keeps serving the in-flight voice (attack times the
  // boundary fade on the 3-frame sample).
  LMDJ_CHECK(left.at(0) == 0.2F * (ramp_part(1) * ramp_part(2)));
  LMDJ_CHECK(engine.bank_telemetry().current_generation == 2);
  LMDJ_CHECK(engine.bank_telemetry().pending_publications == 0);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // The old voice renders its last faded frame; the new voice is on attack
  // frame 0/96.
  LMDJ_CHECK(left.at(0) == 0.1F * (ramp_part(2) * ramp_part(1)));
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.reclaim_retired_banks() == 1);
  LMDJ_CHECK(engine.bank_telemetry().reclaimed_banks == 1);
  LMDJ_CHECK(engine.reclaim_retired_banks() == 0);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{4, 0, 127}) ==
             EnqueueResult::accepted);
}

void rejects_publication_until_trigger_queue_is_empty() {
  RealtimeEngine engine;
  const std::array<float, 2> first_sample{0.25F, 0.25F};
  auto first = bank_with_sample(20, first_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(first)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  const std::array<float, 2> second_sample{0.75F, 0.75F};
  auto second = bank_with_sample(21, second_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::events_pending);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: attack gain 0/96 on the first rendered frame.
  LMDJ_CHECK(left.at(0) == 0.0F);

  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // The in-flight voice keeps rendering from the previous Bank (attack
  // times the boundary fade on the 2-frame sample).
  LMDJ_CHECK(left.at(0) == 0.25F * (ramp_part(1) * ramp_part(1)));
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.0F);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.75F * (ramp_part(1) * ramp_part(1)));
}

// #799. An audition Bank carries a sentinel identity, not a Project's, because
// no Project produced it. `project_id()` is diagnostic-only and nothing in the
// engine reads it.
PreparedSampleBank audition_bank_with_sample(std::span<const float> sample) {
  auto bank = PreparedSampleBank::empty(
      lmdj::audio::kAuditionBankProjectId(),
      lmdj::audio::kAuditionBankProjectRevision);
  LMDJ_CHECK(
      bank.set_sample(lmdj::audio::kAuditionSampleSlot, sample).has_value());
  return bank;
}

// The defect this catches: an audition that is silent, or that plays the
// Project's bytes. Reserving a Bank slot alone does not make a Set audible --
// `current_sample` always reads `bank_slots_[current_bank_slot_]`, so without a
// voice-start path that reads the audition pool the preview plays the Project's
// Pad 0, or nothing. Asserted on rendered sample values, not on a state flag.
void audition_renders_its_own_bytes_while_the_project_bank_stays_current() {
  RealtimeEngine engine;
  // Samples longer than kRealtimeRampFrames on both sides, so the only gain
  // factor in play is the attack ramp. A short sample also applies a tail fade
  // (`ramp_part(frames_remaining)`), which would put ramp arithmetic rather
  // than the byte source in the assertion.
  const std::array<float, 256> project_sample = [] {
    std::array<float, 256> filled{};
    filled.fill(0.5F);
    return filled;
  }();
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_with_sample(1, project_sample)) ==
      PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  const std::array<float, 256> audition_sample = [] {
    std::array<float, 256> filled{};
    filled.fill(0.25F);
    return filled;
  }();
  LMDJ_CHECK(
      engine.publish_audition_bank(audition_bank_with_sample(audition_sample)) ==
      PublishResult::accepted);

  PadControlEvent audition{};
  audition.sequence = 1;
  audition.velocity = 127;
  audition.kind = PadControlKind::audition_start;
  LMDJ_CHECK(engine.enqueue_control(audition) == EnqueueResult::accepted);

  std::array<float, 2> left{};
  std::array<float, 2> right{};
  engine.render(left.data(), right.data(), 2);
  // Audition bytes (0.25), not the Project's Pad 0 (0.5), under the attack
  // ramp alone. If the voice-start path had read `current_sample`, frame 1
  // would be 0.5 * ramp_part(1) -- exactly twice this.
  LMDJ_CHECK(left.at(0) == 0.25F * ramp_part(0));
  LMDJ_CHECK(left.at(1) == 0.25F * ramp_part(1));

  // The Project Bank is untouched: still current, still the source for Pads.
  LMDJ_CHECK(engine.bank_telemetry().current_generation == 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 2);
  // Both sound at once: the audition continues on its own bytes while Pad 0
  // enters on the Project's, so the mix exceeds the audition's own contribution
  // at that frame.
  LMDJ_CHECK(left.at(1) > 0.25F * ramp_part(3));
}

// #799. The defect this catches: an audition publishing anything at all onto
// the voice-state stream. The start edge is already suppressed for auditions
// where the voice is created; the completion edge was not, so an audition
// emitted a `completed` with no `started` before it and with `sequence == 0`,
// because an audition is enqueued as
// `PadControlEvent{0, 0, 127, audition_start, {}}` and has no request to
// number. The Web session requires a positive sequence, so it rejected the
// event and failed the whole Host with HOST_PROTOCOL_MISMATCH roughly a second
// after an audition that had already answered `played: true` -- silently, with
// no page error and no console error.
//
// Rendering to completion is the whole point: one callback reproduces nothing,
// which is why the in-process audition legs never saw this and only a browser
// did.
void an_audition_publishes_no_voice_state_edge() {
  RealtimeEngine engine;
  const std::array<float, 256> project_sample = [] {
    std::array<float, 256> filled{};
    filled.fill(0.5F);
    return filled;
  }();
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_with_sample(1, project_sample)) ==
      PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  const std::array<float, 64> audition_sample = [] {
    std::array<float, 64> filled{};
    filled.fill(0.25F);
    return filled;
  }();
  LMDJ_CHECK(
      engine.publish_audition_bank(audition_bank_with_sample(audition_sample))
      == PublishResult::accepted);

  // Exactly the event the Web Host enqueues, sequence and all. A test that
  // numbered it would pass while the product still failed.
  PadControlEvent audition{};
  audition.sequence = 0;
  audition.slot = 0;
  audition.velocity = 127;
  audition.kind = PadControlKind::audition_start;
  LMDJ_CHECK(engine.enqueue_control(audition) == EnqueueResult::accepted);

  std::array<float, 128> left{};
  std::array<float, 128> right{};
  // Well past the 64-frame preview, so the voice starts, finishes and is
  // accounted for.
  for (int callback = 0; callback < 8; ++callback) {
    engine.render(left.data(), right.data(), 128);
  }
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.telemetry().completed_voices == 1);

  // The far side: nothing reached the stream. Not a started, not a completed.
  std::array<RuntimeVoiceStateEvent, 16> states{};
  LMDJ_CHECK(engine.drain_voice_states(states) == 0);

  // and the stream is still usable -- a Pad trigger after the audition still
  // publishes its own pair, so this suppresses auditions rather than the
  // stream.
  LMDJ_CHECK(engine.enqueue(TriggerEvent{7, 0, 127}) ==
             EnqueueResult::accepted);
  for (int callback = 0; callback < 8; ++callback) {
    engine.render(left.data(), right.data(), 128);
  }
  const auto pad_states = drain_voice_states(engine, 2);
  LMDJ_CHECK(pad_states.at(0).sequence == 7);
  LMDJ_CHECK(pad_states.at(0).state == RuntimeVoiceState::started);
  LMDJ_CHECK(pad_states.at(1).state == RuntimeVoiceState::completed);
}

// The defect this catches: an audition consuming or freeing a Project Bank
// slot. This is the regression the "reserve a slot" decision creates, and the
// named test the Issue asked for -- it fails if a fourth concurrent Project
// publication ever becomes reachable through the audition path.
void audition_never_consumes_a_project_bank_slot() {
  static_assert(lmdj::audio::kRealtimeBankCapacity == 4);
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.125F};
  for (std::uint64_t revision = 1; revision <= 4; ++revision) {
    LMDJ_CHECK(
        engine.publish_sample_bank(bank_with_sample(revision, sample)) ==
        PublishResult::accepted);
    if (revision == 1) {
      LMDJ_CHECK(engine.start().has_value());
    } else {
      std::array<float, 1> left{};
      std::array<float, 1> right{};
      engine.render(left.data(), right.data(), 1);
    }
  }
  // All four Project slots are taken.
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_with_sample(5, sample)) ==
      PublishResult::bank_slots_full);

  // An audition still succeeds: it draws from the reserved pool, so a full
  // Project pool cannot make a preview impossible.
  const std::array<float, 1> audition_sample{0.25F};
  LMDJ_CHECK(
      engine.publish_audition_bank(audition_bank_with_sample(audition_sample)) ==
      PublishResult::accepted);

  // And it neither stole a Project slot nor freed one: the Project pool is
  // exactly as full as it was.
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_with_sample(6, sample)) ==
      PublishResult::bank_slots_full);
  LMDJ_CHECK(engine.bank_telemetry().bank_slot_rejections == 2);
}

// The defect this catches: a replaced audition whose buffer is freed while
// voices are still reading it, or whose slot is never reclaimed so the third
// audition reports the pool full forever.
void replacing_an_audition_drains_the_outgoing_bank() {
  RealtimeEngine engine;
  const std::array<float, 8> project_sample{};
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_with_sample(1, project_sample)) ==
      PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  const std::array<float, 8> first{0.5F, 0.5F, 0.5F, 0.5F, 0.5F, 0.5F, 0.5F, 0.5F};
  LMDJ_CHECK(engine.publish_audition_bank(audition_bank_with_sample(first)) ==
             PublishResult::accepted);
  PadControlEvent start{};
  start.velocity = 127;
  start.kind = PadControlKind::audition_start;
  start.sequence = 1;
  LMDJ_CHECK(engine.enqueue_control(start) == EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  // Replace while the first audition is still ringing.
  const std::array<float, 8> second{0.25F, 0.25F, 0.25F, 0.25F,
                                    0.25F, 0.25F, 0.25F, 0.25F};
  LMDJ_CHECK(engine.publish_audition_bank(audition_bank_with_sample(second)) ==
             PublishResult::accepted);
  start.sequence = 2;
  LMDJ_CHECK(engine.enqueue_control(start) == EnqueueResult::accepted);

  // A third publication while both slots are still held is refused rather than
  // overwriting a buffer a voice is reading.
  const std::array<float, 8> third{};
  LMDJ_CHECK(engine.publish_audition_bank(audition_bank_with_sample(third)) ==
             PublishResult::bank_slots_full);
  // and that refusal is not accounted against the Project pool.
  LMDJ_CHECK(engine.bank_telemetry().bank_slot_rejections == 0);

  // Drain: stop the auditions and render past the release ramp.
  PadControlEvent stop{};
  stop.kind = PadControlKind::audition_stop;
  stop.sequence = 3;
  LMDJ_CHECK(engine.enqueue_control(stop) == EnqueueResult::accepted);
  for (int pass = 0; pass < 400; ++pass) {
    engine.render(left.data(), right.data(), 1);
  }
  LMDJ_CHECK(engine.reclaim_retired_banks() >= 1);

  // With a slot reclaimed, auditioning works again.
  LMDJ_CHECK(engine.publish_audition_bank(audition_bank_with_sample(second)) ==
             PublishResult::accepted);
}

// Audition storage comes from its own reserved pool: reclaiming it must not
// refund bytes charged to the Host's Project Bank reservation.
void audition_reclamation_preserves_project_pcm_reservations() {
  RealtimeEngine engine;
  const std::array<float, 8> samples{0.25F};
  LMDJ_CHECK(engine.publish_sample_bank(bank_with_sample(1, samples)) == PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.publish_audition_bank(audition_bank_with_sample(samples)) == PublishResult::accepted);
  std::array<float, 1> left{}, right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.publish_audition_bank(audition_bank_with_sample(samples)) == PublishResult::accepted);
  engine.render(left.data(), right.data(), 1);
  const auto audition = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(audition.count == 1);
  LMDJ_CHECK(audition.decoded_pcm_bytes == 0);
  LMDJ_CHECK(engine.publish_sample_bank(bank_with_sample(2, samples)) == PublishResult::accepted);
  LMDJ_CHECK(engine.publish_audition_bank(audition_bank_with_sample(samples)) == PublishResult::accepted);
  engine.render(left.data(), right.data(), 1);
  const auto mixed = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(mixed.count == 2);
  LMDJ_CHECK(mixed.decoded_pcm_bytes == samples.size() * sizeof(float));
  engine.stop();
  const auto stopped = engine.reclaim_retired_bank_telemetry();
  // Stop retains current Banks; it must not emit a second refund.
  LMDJ_CHECK(stopped.count == 0);
  LMDJ_CHECK(stopped.decoded_pcm_bytes == 0);
}

// The defect this catches: an audition leaking into Pad state. It must never
// become the current Bank, never alter the Pad availability the Host reports,
// and never be stopped by a Pad stop or by stop-all.
void audition_never_becomes_current_and_never_moves_availability() {
  RealtimeEngine engine;
  // Long enough that neither voice ends on its own during this test: a voice
  // that ran out of samples would look exactly like one that was stopped.
  const std::array<float, 4096> project_sample = [] {
    std::array<float, 4096> filled{};
    filled.fill(0.5F);
    return filled;
  }();
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_with_sample(7, project_sample)) ==
      PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  const auto generation_before = engine.bank_telemetry().current_generation;
  // Pad availability has no public accessor, so it is asserted through the
  // behaviour it governs: Pad 0 carries the sample, Pad 1 does not.
  PadControlEvent absent_pad{};
  absent_pad.slot = 1;
  absent_pad.velocity = 127;
  absent_pad.kind = PadControlKind::press;
  absent_pad.sequence = 100;
  LMDJ_CHECK(engine.enqueue_control(absent_pad) ==
             EnqueueResult::sample_unavailable);

  const std::array<float, 4096> audition_sample = [] {
    std::array<float, 4096> filled{};
    filled.fill(0.25F);
    return filled;
  }();
  LMDJ_CHECK(
      engine.publish_audition_bank(audition_bank_with_sample(audition_sample)) ==
      PublishResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  // Publishing an audition applies no Project publication and moves no Pad.
  LMDJ_CHECK(engine.bank_telemetry().current_generation == generation_before);
  LMDJ_CHECK(engine.bank_telemetry().pending_publications == 0);
  // Availability is exactly where it was: the empty Pad is still empty, and
  // the occupied one is still playable. An audition that had written
  // `availability_mask_` would flip one of these.
  absent_pad.sequence = 101;
  LMDJ_CHECK(engine.enqueue_control(absent_pad) ==
             EnqueueResult::sample_unavailable);
  PadControlEvent present_pad{};
  present_pad.slot = 0;
  present_pad.velocity = 127;
  present_pad.kind = PadControlKind::press;
  present_pad.sequence = 102;
  LMDJ_CHECK(engine.enqueue_control(present_pad) == EnqueueResult::accepted);

  PadControlEvent start{};
  start.velocity = 127;
  start.kind = PadControlKind::audition_start;
  start.sequence = 103;
  LMDJ_CHECK(engine.enqueue_control(start) == EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // Two voices: the Pad 0 press enqueued above, and the audition.
  LMDJ_CHECK(engine.telemetry().active_voices == 2);

  // stop_all is a Pad gesture. It must silence the Pad and leave the preview
  // running -- otherwise a performer stopping playback also kills the Set they
  // are auditioning, and auditioning during playback becomes unusable.
  PadControlEvent stop_all{};
  stop_all.kind = PadControlKind::stop_all;
  stop_all.sequence = 104;
  LMDJ_CHECK(engine.enqueue_control(stop_all) == EnqueueResult::accepted);
  // Render past kRealtimeRampFrames so the stopped Pad voice finishes its
  // release tail and deactivates; a stop is not an immediate silence.
  for (int pass = 0; pass < 200; ++pass) {
    engine.render(left.data(), right.data(), 1);
  }
  LMDJ_CHECK(engine.telemetry().active_voices == 1);

  // And `audition_stop` does reach it, so the preview is stoppable.
  PadControlEvent audition_stop{};
  audition_stop.kind = PadControlKind::audition_stop;
  audition_stop.sequence = 105;
  LMDJ_CHECK(engine.enqueue_control(audition_stop) == EnqueueResult::accepted);
  for (int pass = 0; pass < 400; ++pass) {
    engine.render(left.data(), right.data(), 1);
  }
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
}

// The defect this catches: an audition request accepted with nothing published,
// which would be discarded on the audio thread where the caller cannot see it.
void audition_without_a_published_bank_is_refused_at_enqueue() {
  RealtimeEngine engine;
  const std::array<float, 1> project_sample{0.5F};
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_with_sample(1, project_sample)) ==
      PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  PadControlEvent start{};
  start.velocity = 127;
  start.kind = PadControlKind::audition_start;
  start.sequence = 1;
  LMDJ_CHECK(engine.enqueue_control(start) ==
             EnqueueResult::sample_unavailable);
}

void applies_explicit_bank_slot_backpressure_until_reclaimed() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.125F};
  for (std::uint64_t revision = 1; revision <= 4; ++revision) {
    auto bank = bank_with_sample(revision, sample);
    LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
               PublishResult::accepted);
    if (revision == 1) {
      LMDJ_CHECK(engine.start().has_value());
    } else {
      std::array<float, 1> left{};
      std::array<float, 1> right{};
      engine.render(left.data(), right.data(), 1);
    }
  }
  auto fifth = bank_with_sample(5, sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(fifth)) ==
             PublishResult::bank_slots_full);
  LMDJ_CHECK(engine.bank_telemetry().bank_slot_rejections == 1);
  LMDJ_CHECK(engine.reclaim_retired_banks() == 3);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(fifth)) ==
             PublishResult::accepted);
}

void reports_exact_bytes_for_non_fifo_heterogeneous_bank_reclaim() {
  RealtimeEngine engine;
  const std::array<float, 512> older_large_sample{};
  const std::array<float, 1> newer_small_sample{};
  const std::array<float, 2> current_sample{};

  auto older_large = bank_with_sample(40, older_large_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(older_large)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 512> left{};
  std::array<float, 512> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);

  auto newer_small = bank_with_sample(41, newer_small_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(newer_small)) ==
             PublishResult::accepted);
  engine.render(left.data(), right.data(), 1);

  auto current = bank_with_sample(42, current_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(current)) ==
             PublishResult::accepted);
  engine.render(left.data(), right.data(), 1);

  const auto out_of_order = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(out_of_order.count == 1);
  LMDJ_CHECK(out_of_order.decoded_pcm_bytes == sizeof(float));
  LMDJ_CHECK(engine.telemetry().active_voices == 1);

  engine.render(left.data(), right.data(), 509);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  const auto older_after_voice = engine.reclaim_retired_bank_telemetry();
  LMDJ_CHECK(older_after_voice.count == 1);
  LMDJ_CHECK(
      older_after_voice.decoded_pcm_bytes ==
      older_large_sample.size() * sizeof(float));
  LMDJ_CHECK(engine.reclaim_retired_bank_telemetry().count == 0);
  LMDJ_CHECK(engine.bank_telemetry().reclaimed_banks == 2);
}

void preserves_high_frame_trim_loop_and_ramp_arithmetic() {
  std::vector<float> sample(kMaximumBankPadFrames, 0.0F);
  sample.at(kMaximumBankPadFrames - 3) = 0.25F;
  sample.at(kMaximumBankPadFrames - 2) = 0.5F;
  sample.at(kMaximumBankPadFrames - 1) = 0.75F;

  RealtimeEngine engine;
  auto bank = bank_with_playback(
      43,
      sample,
      ResolvedPlayback{
          kMaximumBankPadFrames - 3,
          kMaximumBankPadFrames,
          TriggerMode::one_shot,
          1.0F,
          false});
  LMDJ_CHECK(bank.decoded_pcm_bytes() == 67'108'864);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 5> left{};
  std::array<float, 5> right{};
  engine.render(left.data(), right.data(), 3);
  LMDJ_CHECK(left.at(0) == 0.0F);
  LMDJ_CHECK(
      left.at(1) == 0.5F * (ramp_part(1) * ramp_part(2)));
  LMDJ_CHECK(
      left.at(2) == 0.75F * (ramp_part(2) * ramp_part(1)));

  std::array<RuntimeVoiceStateEvent, 2> one_shot_states{};
  LMDJ_CHECK(engine.drain_voice_states(one_shot_states) == 2);
  LMDJ_CHECK(
      one_shot_states.at(0).source_frame == kMaximumBankPadFrames - 3);
  LMDJ_CHECK(
      one_shot_states.at(1).source_frame == kMaximumBankPadFrames);

  LMDJ_CHECK(
      engine.enqueue_control(PadControlEvent{
          2,
          0,
          127,
          PadControlKind::preview_set,
          ResolvedPlayback{
              kMaximumBankPadFrames - 2,
              kMaximumBankPadFrames,
              TriggerMode::loop_gate,
              1.0F,
              false},
      }) == EnqueueResult::accepted);
  LMDJ_CHECK(
      engine.enqueue_control(PadControlEvent{
          3,
          0,
          127,
          PadControlKind::press,
          {},
      }) == EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 5);
  LMDJ_CHECK(left.at(0) == 0.0F);
  LMDJ_CHECK(left.at(1) == 0.75F * ramp_part(1));
  LMDJ_CHECK(left.at(2) == 0.5F * ramp_part(2));
  LMDJ_CHECK(left.at(3) == 0.75F * ramp_part(3));
  LMDJ_CHECK(left.at(4) == 0.5F * ramp_part(4));

  LMDJ_CHECK(
      engine.enqueue_control(PadControlEvent{
          4,
          0,
          127,
          PadControlKind::release,
          {},
      }) == EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  std::array<RuntimeVoiceStateEvent, 2> loop_states{};
  LMDJ_CHECK(engine.drain_voice_states(loop_states) == 2);
  LMDJ_CHECK(
      loop_states.at(0).source_frame == kMaximumBankPadFrames - 2);
  LMDJ_CHECK(
      loop_states.at(1).source_frame == kMaximumBankPadFrames - 1);
}

void capture_storage_is_allocated_only_on_first_arm() {
  RealtimeEngine engine;
  LMDJ_CHECK(engine.start().has_value());
  g_allocations.store(0);
  g_track_allocations.store(true);
  const auto armed = engine.arm_capture();
  g_track_allocations.store(false);
  LMDJ_CHECK(armed.has_value());
  LMDJ_CHECK(g_allocations.load() == 1);
}

void capture_allocation_failure_leaves_playback_running_and_retryable() {
  RealtimeEngine engine;
  const std::array<float, 2> sample{0.25F, 0.25F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  g_allocations.store(0);
  g_track_allocations.store(true);
  // Fail every subsequent allocation, not just the ring. Error formatting
  // inside noexcept must not allocate again or terminate the process.
  g_fail_allocations = true;
  const bool prepared = engine.prepare_capture();
  const auto armed = engine.arm_capture();
  g_fail_allocations = false;
  g_track_allocations.store(false);
  LMDJ_CHECK(!prepared);
  LMDJ_CHECK(!armed.has_value());
  LMDJ_CHECK(armed.error().code == ErrorCode::internal_error);
  LMDJ_CHECK(armed.error().message.empty());
  LMDJ_CHECK(armed.error().details.is_null());
  LMDJ_CHECK(g_allocations.load() == 2);
  LMDJ_CHECK(engine.capture_telemetry().state == CaptureState::idle);
  LMDJ_CHECK(engine.telemetry().state == RealtimeState::running);
  std::array<CapturedTriggerEvent, 1> captured{};
  captured[0].sequence = 99;
  LMDJ_CHECK(engine.drain_capture(captured) == 0);
  LMDJ_CHECK(captured[0].sequence == 99);
  LMDJ_CHECK(engine.enqueue({1, 0, 100}) == EnqueueResult::accepted);
  std::array<float, 1> left{}, right{};
  engine.render(left.data(), right.data(), 1);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] > 0.0F && right[0] == left[0]);
  LMDJ_CHECK(engine.telemetry().started_voices == 1);
  LMDJ_CHECK(engine.capture_telemetry().captured_events == 0);
  LMDJ_CHECK(engine.arm_capture().has_value());
  LMDJ_CHECK(engine.enqueue({2, 0, 100}) == EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.drain_capture(captured) == 1);
  LMDJ_CHECK(captured[0].sequence == 2);
}

void capture_storage_survives_stop_and_restart_without_reallocation() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.25F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_capture());
  LMDJ_CHECK(engine.capture_telemetry().state == CaptureState::idle);
  LMDJ_CHECK(engine.start().has_value());
  g_allocations.store(0);
  g_deallocations.store(0);
  g_track_allocations.store(true);
  LMDJ_CHECK(engine.prepare_capture());
  LMDJ_CHECK(engine.arm_capture().has_value());
  LMDJ_CHECK(engine.enqueue({42, 0, 100}) == EnqueueResult::accepted);
  std::array<float, 1> left{}, right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.disarm_capture().has_value());
  engine.render(left.data(), right.data(), 1);
  engine.stop();
  std::array<CapturedTriggerEvent, 1> captured{};
  LMDJ_CHECK(engine.drain_capture(captured) == 1);
  LMDJ_CHECK(captured[0].sequence == 42);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  LMDJ_CHECK(engine.enqueue({43, 0, 100}) == EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  engine.stop();
  // Existing start semantics discard unread events, unlike stop/disarm.
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.drain_capture(captured) == 0);
  LMDJ_CHECK(engine.arm_capture().has_value());
  engine.render(left.data(), right.data(), 1);
  engine.stop();
  g_track_allocations.store(false);
  LMDJ_CHECK(g_allocations.load() == 0);
  LMDJ_CHECK(g_deallocations.load() == 0);
}

void captures_voice_starts_at_exact_runtime_frames_and_disarms_at_end() {
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.25F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  LMDJ_CHECK(engine.capture_telemetry().state == CaptureState::arm_pending);

  std::array<float, 6> left{};
  std::array<float, 6> right{};
  engine.render(left.data(), right.data(), 4);
  LMDJ_CHECK(engine.capture_telemetry().state == CaptureState::active);
  LMDJ_CHECK(engine.capture_telemetry().capture_origin_frame == 0);
  engine.render(left.data(), right.data(), 6);

  LMDJ_CHECK(engine.enqueue(TriggerEvent{7, 0, 100}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 3);
  LMDJ_CHECK(engine.disarm_capture().has_value());
  LMDJ_CHECK(engine.capture_telemetry().state ==
             CaptureState::disarm_pending);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{8, 0, 110}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 2);
  LMDJ_CHECK(engine.capture_telemetry().state == CaptureState::idle);

  LMDJ_CHECK(engine.enqueue(TriggerEvent{9, 0, 120}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  std::array<CapturedTriggerEvent, 3> captured{};
  LMDJ_CHECK(engine.drain_capture(captured) == 2);
  LMDJ_CHECK(captured.at(0).sequence == 7);
  LMDJ_CHECK(captured.at(0).slot == 0);
  LMDJ_CHECK(captured.at(0).velocity == 100);
  LMDJ_CHECK(captured.at(0).frame_offset == 10);
  LMDJ_CHECK(captured.at(1).sequence == 8);
  LMDJ_CHECK(captured.at(1).velocity == 110);
  LMDJ_CHECK(captured.at(1).frame_offset == 13);
  const auto telemetry = engine.capture_telemetry();
  LMDJ_CHECK(telemetry.captured_events == 2);
  LMDJ_CHECK(telemetry.drained_events == 2);
  LMDJ_CHECK(telemetry.capture_drops == 0);
}

void replay_origin_uses_scheduled_release_without_live_identity_streams() {
  RealtimeEngine engine;
  std::array<float, 128> sample{};
  sample.fill(-0.25F);
  std::array<std::int16_t, 128> replay_sample{};
  replay_sample.fill(12'000);
  auto bank = bank_with_playback(
      90, sample,
      ResolvedPlayback{0, 128, TriggerMode::loop_gate, 1.0F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  render_frames(engine, 1);

  LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                 0,
                 0,
                 127,
                 PadControlKind::press,
                 ResolvedPlayback{0, 128, TriggerMode::loop_gate, 1.0F, false},
                 PadControlOrigin::performance_replay,
                 8,
                 PreparedSampleMaterialView{replay_sample.data(),
                                            replay_sample.size(), 1},
             }) == EnqueueResult::accepted);
  std::array<float, 2> left{};
  std::array<float, 2> right{};
  engine.render(left.data(), right.data(), 2);
  LMDJ_CHECK(left.at(1) > 0.0F);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
  render_frames(engine, 6);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
  render_frames(engine, 1 + kRampFrames);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);

  std::array<RuntimeTriggerOutcomeEvent, 1> outcomes{};
  std::array<RuntimeVoiceStateEvent, 1> states{};
  std::array<CapturedTriggerEvent, 1> captured{};
  LMDJ_CHECK(engine.drain_trigger_outcomes(outcomes) == 0);
  LMDJ_CHECK(engine.drain_voice_states(states) == 0);
  LMDJ_CHECK(engine.drain_capture(captured) == 0);
  LMDJ_CHECK(engine.capture_telemetry().captured_events == 0);
}

void live_release_does_not_stop_same_slot_replay_voice() {
  RealtimeEngine engine;
  std::array<float, 512> live_sample{};
  live_sample.fill(0.1F);
  std::array<std::int16_t, 512> replay_sample{};
  replay_sample.fill(12'000);
  auto bank = bank_with_playback(
      91, live_sample,
      ResolvedPlayback{0, 512, TriggerMode::loop_gate, 1.0F, false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                 0,
                 0,
                 127,
                 PadControlKind::press,
                 ResolvedPlayback{0, 512, TriggerMode::loop_gate, 1.0F, false},
                 PadControlOrigin::performance_replay,
                 10'000,
                 PreparedSampleMaterialView{replay_sample.data(),
                                            replay_sample.size(), 1},
             }) == EnqueueResult::accepted);
  render_frames(engine, 2);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  render_frames(engine, 2);
  LMDJ_CHECK(engine.telemetry().active_voices == 2);
  LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                 1,
                 0,
                 0,
                 PadControlKind::release,
                 {},
             }) == EnqueueResult::accepted);
  render_frames(engine, 1 + kRampFrames);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
}

void captures_only_successfully_allocated_voices() {
  RealtimeEngine engine;
  const std::array<float, 2> sample{0.1F, 0.2F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  for (std::uint64_t sequence = 0; sequence < 128; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{128, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);

  std::array<CapturedTriggerEvent, 129> captured{};
  LMDJ_CHECK(engine.drain_capture(captured) == 128);
  for (std::uint64_t sequence = 0; sequence < 128; ++sequence) {
    LMDJ_CHECK(captured.at(sequence).sequence == sequence);
  }
  LMDJ_CHECK(engine.capture_telemetry().captured_events == 128);
  LMDJ_CHECK(engine.telemetry().voice_drops == 1);
}

void capture_overflow_remains_observable_without_a_voice_state_consumer() {
  static_assert(lmdj::audio::kRealtimeCaptureCapacity == 4'096);
  RealtimeEngine engine;
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);

  for (std::uint64_t sequence = 1;
       sequence <= lmdj::audio::kRealtimeCaptureCapacity;
       ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
    engine.render(left.data(), right.data(), 1);
  }
  LMDJ_CHECK(engine.enqueue(TriggerEvent{4'097, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  const auto corrupted = engine.capture_telemetry();
  LMDJ_CHECK(corrupted.state == CaptureState::corrupted);
  LMDJ_CHECK(corrupted.captured_events == 4'096);
  LMDJ_CHECK(corrupted.capture_drops == 1);

  std::array<CapturedTriggerEvent, 4'095> captured{};
  LMDJ_CHECK(engine.drain_capture(captured) == captured.size());
  for (std::uint64_t index = 0; index < captured.size(); ++index) {
    LMDJ_CHECK(captured.at(index).sequence == index + 1);
    LMDJ_CHECK(captured.at(index).frame_offset == index + 1);
  }

  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  const auto reset = engine.capture_telemetry();
  LMDJ_CHECK(reset.state == CaptureState::idle);
  LMDJ_CHECK(reset.captured_events == 0);
  LMDJ_CHECK(reset.drained_events == 0);
  LMDJ_CHECK(reset.capture_drops == 0);
  LMDJ_CHECK(engine.drain_capture(captured) == 0);
}

void stop_cancels_queued_events_and_active_voices() {
  RealtimeEngine engine;
  const std::array<float, 3> sample{0.1F, 0.2F, 0.3F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  engine.stop();

  const auto telemetry = engine.telemetry();
  LMDJ_CHECK(telemetry.state == RealtimeState::stopped);
  LMDJ_CHECK(telemetry.cancelled_events == 1);
  LMDJ_CHECK(telemetry.cancelled_voices == 1);
  LMDJ_CHECK(telemetry.queued_events == 0);
  LMDJ_CHECK(telemetry.active_voices == 0);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{3, 0, 127}) ==
             EnqueueResult::not_running);
  LMDJ_CHECK(engine.telemetry().stopped_rejections == 1);
}

void restart_resets_counters_retains_samples_and_replays_no_event() {
  RealtimeEngine engine;
  const std::array<float, 3> sample{0.75F, 0.5F, 0.25F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.telemetry().start_epoch == 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{0, 64, 127}) ==
             EnqueueResult::invalid_slot);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 3> left{};
  std::array<float, 3> right{};
  engine.render(left.data(), right.data(), 3);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  for (std::uint64_t sequence = 3; sequence < 132; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  engine.render(left.data(), right.data(), 1);
  for (std::uint64_t sequence = 132; sequence < 1'156; ++sequence) {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{sequence, 0, 127}) ==
               EnqueueResult::accepted);
  }
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1'156, 0, 127}) ==
             EnqueueResult::queue_full);

  const auto before_stop = engine.telemetry();
  LMDJ_CHECK(before_stop.state == RealtimeState::running);
  LMDJ_CHECK(before_stop.queued_events > 0);
  LMDJ_CHECK(before_stop.active_voices > 0);

  engine.stop();
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1'157, 0, 127}) ==
             EnqueueResult::not_running);
  const auto after_stop = engine.telemetry();
  LMDJ_CHECK(after_stop.state == RealtimeState::stopped);
  LMDJ_CHECK(after_stop.start_epoch == before_stop.start_epoch);
  LMDJ_CHECK(after_stop.enqueued_events > 0);
  LMDJ_CHECK(after_stop.dequeued_events > 0);
  LMDJ_CHECK(after_stop.cancelled_events > 0);
  LMDJ_CHECK(after_stop.started_voices > 0);
  LMDJ_CHECK(after_stop.completed_voices > 0);
  LMDJ_CHECK(after_stop.cancelled_voices > 0);
  LMDJ_CHECK(after_stop.invalid_events > 0);
  LMDJ_CHECK(after_stop.stopped_rejections > 0);
  LMDJ_CHECK(after_stop.queue_drops > 0);
  LMDJ_CHECK(after_stop.voice_drops > 0);
  LMDJ_CHECK(after_stop.callback_count > 0);
  LMDJ_CHECK(after_stop.rendered_frames > 0);
  LMDJ_CHECK(after_stop.max_callback_frames > 0);
  LMDJ_CHECK(after_stop.queued_events == 0);
  LMDJ_CHECK(after_stop.active_voices == 0);
  LMDJ_CHECK(after_stop.enqueued_events ==
             after_stop.dequeued_events + after_stop.cancelled_events);
  LMDJ_CHECK(after_stop.dequeued_events ==
             after_stop.started_voices + after_stop.voice_drops);
  LMDJ_CHECK(after_stop.started_voices ==
             after_stop.completed_voices + after_stop.cancelled_voices);

  LMDJ_CHECK(engine.start().has_value());
  const auto reset = engine.telemetry();
  LMDJ_CHECK(reset.state == RealtimeState::running);
  LMDJ_CHECK(reset.start_epoch == before_stop.start_epoch + 1);
  LMDJ_CHECK(reset.enqueued_events == 0);
  LMDJ_CHECK(reset.dequeued_events == 0);
  LMDJ_CHECK(reset.queued_events == 0);
  LMDJ_CHECK(reset.cancelled_events == 0);
  LMDJ_CHECK(reset.started_voices == 0);
  LMDJ_CHECK(reset.completed_voices == 0);
  LMDJ_CHECK(reset.active_voices == 0);
  LMDJ_CHECK(reset.cancelled_voices == 0);
  LMDJ_CHECK(reset.invalid_events == 0);
  LMDJ_CHECK(reset.stopped_rejections == 0);
  LMDJ_CHECK(reset.queue_drops == 0);
  LMDJ_CHECK(reset.voice_drops == 0);
  LMDJ_CHECK(reset.callback_count == 0);
  LMDJ_CHECK(reset.rendered_frames == 0);
  LMDJ_CHECK(reset.max_callback_frames == 0);

  left.fill(1.0F);
  right.fill(1.0F);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == 0.0F && right[0] == 0.0F);

  LMDJ_CHECK(engine.enqueue(TriggerEvent{1'158, 0, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 1);
  // F6 ramp: attack gain 0/96 on the first rendered frame; the retained
  // sample is audible from the next frame on.
  LMDJ_CHECK(left[0] == 0.0F && right[0] == 0.0F);
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == 0.5F * (ramp_part(1) * ramp_part(2)));
  LMDJ_CHECK(right[0] == left[0]);
}

void start_epoch_overflow_fails_before_mutating_engine_state() {
  RealtimeEngine engine;
  constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
  engine.set_start_epoch_for_testing(maximum - 1);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.telemetry().start_epoch == maximum);

  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  engine.stop();
  const auto before = engine.telemetry();
  LMDJ_CHECK(!engine.start().has_value());
  const auto after = engine.telemetry();
  LMDJ_CHECK(after.state == RealtimeState::stopped);
  LMDJ_CHECK(after.start_epoch == maximum);
  LMDJ_CHECK(after.rendered_frames == before.rendered_frames);
  LMDJ_CHECK(after.callback_count == before.callback_count);
}

void render_does_not_allocate_or_deallocate() {
  RealtimeEngine engine;
  const std::array<float, 2> old_sample{0.25F, 0.5F};
  auto first = bank_with_sample(30, old_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(first)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.arm_capture().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  g_allocations.store(0, std::memory_order_relaxed);
  g_deallocations.store(0, std::memory_order_relaxed);
  g_track_allocations.store(true, std::memory_order_relaxed);
  engine.render(left.data(), right.data(), 1);
  g_track_allocations.store(false, std::memory_order_relaxed);

  const std::array<float, 1> new_sample{0.75F};
  auto second = bank_with_sample(31, new_sample);
  LMDJ_CHECK(engine.publish_sample_bank(std::move(second)) ==
             PublishResult::accepted);

  g_track_allocations.store(true, std::memory_order_relaxed);
  engine.render(left.data(), right.data(), 1);
  g_track_allocations.store(false, std::memory_order_relaxed);
  LMDJ_CHECK(g_allocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(g_deallocations.load(std::memory_order_relaxed) == 0);
  // F6 ramp: attack 1/96 times the boundary fade 1/96 on the second frame
  // of the 2-frame sample.
  LMDJ_CHECK(left.at(0) == 0.5F * (ramp_part(1) * ramp_part(1)));
  LMDJ_CHECK(engine.capture_telemetry().captured_events == 1);
  LMDJ_CHECK(engine.reclaim_retired_banks() == 1);
}

void attack_ramps_to_full_gain_over_exactly_the_ramp_frames() {
  static_assert(kRampFrames == 96);
  RealtimeEngine engine;
  const std::array<float, 200> sample = [] {
    std::array<float, 200> value{};
    value.fill(1.0F);
    return value;
  }();
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 104> left{};
  std::array<float, 104> right{};
  engine.render(left.data(), right.data(), 104);
  for (std::uint32_t frame = 0; frame < kRampFrames; ++frame) {
    LMDJ_CHECK(left[frame] == ramp_part(frame));
    LMDJ_CHECK(right[frame] == ramp_part(frame));
  }
  // Full scale from frame 96 on; the boundary fade has not started yet
  // (end_frame - cursor is still above the ramp length).
  for (std::size_t frame = kRampFrames; frame < left.size(); ++frame) {
    LMDJ_CHECK(left[frame] == 1.0F);
    LMDJ_CHECK(right[frame] == 1.0F);
  }
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
}

void non_loop_boundary_fades_to_exact_zero_at_end_frame() {
  RealtimeEngine engine;
  const std::array<float, 200> sample = [] {
    std::array<float, 200> value{};
    value.fill(1.0F);
    return value;
  }();
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 200> left{};
  std::array<float, 200> right{};
  engine.render(left.data(), right.data(), 200);
  // Past the attack, every frame inside the last kRealtimeRampFrames is
  // scaled by (end_frame - cursor)/96 alone; the last rendered frame
  // carries exactly 1/96 and the voice completes at end_frame.
  for (std::uint32_t frame = 105; frame < 200; ++frame) {
    LMDJ_CHECK(left[frame] == ramp_part(200 - frame));
    LMDJ_CHECK(right[frame] == ramp_part(200 - frame));
  }
  LMDJ_CHECK(left[199] == ramp_part(1));
  LMDJ_CHECK(engine.telemetry().completed_voices == 1);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
}

void stop_voice_renders_a_full_ramp_tail_then_deactivates() {
  RealtimeEngine engine;
  const std::array<float, 300> sample = [] {
    std::array<float, 300> value{};
    value.fill(1.0F);
    return value;
  }();
  auto bank = bank_with_playback(
      9,
      sample,
      ResolvedPlayback{
          0,
          static_cast<std::uint32_t>(sample.size()),
          TriggerMode::gate,
          1.0F,
          false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue_control(control(90, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  std::array<float, 100> warmup_left{};
  std::array<float, 100> warmup_right{};
  engine.render(warmup_left.data(), warmup_right.data(), 100);
  LMDJ_CHECK(warmup_left[99] == 1.0F);

  LMDJ_CHECK(
      engine.enqueue_control(control(91, 0, PadControlKind::release)) ==
      EnqueueResult::accepted);
  std::array<float, kRampFrames> left{};
  std::array<float, kRampFrames> right{};
  engine.render(left.data(), right.data(), kRampFrames);
  // The first tail frame carries the full release scale; frame k carries
  // (96 - k)/96; the last tail frame carries exactly 1/96.
  LMDJ_CHECK(left[0] == 1.0F);
  for (std::uint32_t frame = 1; frame < kRampFrames; ++frame) {
    LMDJ_CHECK(left[frame] == ramp_part(kRampFrames - frame));
    LMDJ_CHECK(right[frame] == ramp_part(kRampFrames - frame));
  }
  LMDJ_CHECK(left[kRampFrames - 1] == ramp_part(1));
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.telemetry().cancelled_voices == 1);
  LMDJ_CHECK(engine.telemetry().completed_voices == 0);

  // The stopped edge is published at stop initiation, not after the tail.
  const auto states = drain_voice_states(engine, 2);
  LMDJ_CHECK(states.at(0).sequence == 90);
  LMDJ_CHECK(states.at(0).state == RuntimeVoiceState::started);
  LMDJ_CHECK(states.at(0).runtime_frame == 0);
  LMDJ_CHECK(states.at(1).sequence == 90);
  LMDJ_CHECK(states.at(1).state == RuntimeVoiceState::stopped);
  LMDJ_CHECK(states.at(1).runtime_frame == 100);
  LMDJ_CHECK(states.at(1).source_frame == 100);
}

void releasing_voice_is_hard_killed_by_a_second_stop() {
  RealtimeEngine engine;
  const std::array<float, 200> sample = [] {
    std::array<float, 200> value{};
    value.fill(0.5F);
    return value;
  }();
  auto bank = bank_with_playback(
      10,
      sample,
      ResolvedPlayback{
          0,
          static_cast<std::uint32_t>(sample.size()),
          TriggerMode::loop_toggle,
          1.0F,
          false});
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue_control(control(95, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  std::array<float, 100> warmup_left{};
  std::array<float, 100> warmup_right{};
  engine.render(warmup_left.data(), warmup_right.data(), 100);

  LMDJ_CHECK(
      engine.enqueue_control(control(96, 0, PadControlKind::press, 127)) ==
      EnqueueResult::accepted);
  std::array<float, 10> tail_left{};
  std::array<float, 10> tail_right{};
  engine.render(tail_left.data(), tail_right.data(), 10);
  LMDJ_CHECK(tail_left[0] == 0.5F);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);

  // A second stop hard-kills the releasing voice: no ramp, no second
  // stopped publication, immediate silence.
  LMDJ_CHECK(engine.enqueue_control(control(97, 0, PadControlKind::stop_all)) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) == 0.0F && right.at(0) == 0.0F);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.telemetry().cancelled_voices == 1);

  const auto states = drain_voice_states(engine, 2);
  LMDJ_CHECK(states.at(0).state == RuntimeVoiceState::started);
  LMDJ_CHECK(states.at(1).state == RuntimeVoiceState::stopped);
  LMDJ_CHECK(states.at(1).runtime_frame == 100);
}

void voice_shorter_than_the_ramp_multiplies_attack_and_boundary() {
  RealtimeEngine engine;
  const std::array<float, 4> sample{0.1F, 0.2F, 0.4F, 0.8F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 4> left{};
  std::array<float, 4> right{};
  engine.render(left.data(), right.data(), 4);
  const std::array<float, 4> expected{
      0.0F,
      0.2F * (ramp_part(1) * ramp_part(3)),
      0.4F * (ramp_part(2) * ramp_part(2)),
      0.8F * (ramp_part(3) * ramp_part(1))};
  LMDJ_CHECK(left == expected);
  LMDJ_CHECK(right == expected);
  LMDJ_CHECK(engine.telemetry().completed_voices == 1);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
}

void publishes_immutable_patterns_at_the_next_bar_boundary() {
  RealtimeEngine engine;
  LMDJ_CHECK(!engine.current_pattern_origin_frame().has_value());
  std::array<float, 128> old_sample{};
  std::array<float, 128> next_sample{};
  old_sample.fill(-0.25F);
  next_sample.fill(-0.75F);
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, 1);
  const auto looping = ResolvedPlayback{
      0, 128, TriggerMode::loop_gate, 1.0F, false};
  LMDJ_CHECK(bank.set_sample(0, old_sample, looping).has_value());
  LMDJ_CHECK(bank.set_sample(1, next_sample, looping).has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);

  auto first = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 127, 120, 12'000));
  const std::array overlay{lmdj::domain::PatternEvent{
      PadSlotId{0, 1}, 0, lmdj::domain::kBarTicks4x4, 96}};
  auto second = PreparedPatternView::from_snapshot_with_overlay(
      pattern_snapshot(kPatternB, PadSlotId{0, 1}, 127, 120, 16'000),
      overlay);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(second.has_value());
  const auto first_publication =
      engine.publish_pattern_view(std::move(first.value()));
  LMDJ_CHECK(first_publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(first_publication.activation_frame == 0);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternA});
  LMDJ_CHECK(engine.current_pattern_origin_frame() == 0);
  LMDJ_CHECK(engine.start().has_value());

  render_frames(engine, 100);
  const auto pending =
      engine.publish_pattern_view(std::move(second.value()));
  LMDJ_CHECK(pending.result == PatternPublishResult::accepted);
  LMDJ_CHECK(pending.activation_frame == 96'000);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternA});
  LMDJ_CHECK(engine.pending_pattern_id() == PatternId{kPatternB});
  LMDJ_CHECK(engine.pattern_telemetry().pending_generation ==
             pending.generation);

  render_frames(engine, 95'899);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left.at(0) > 0.0F);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternA});
  LMDJ_CHECK(engine.pending_pattern_id() == PatternId{kPatternB});

  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternB});
  LMDJ_CHECK(engine.current_pattern_origin_frame() == 96'000);
  LMDJ_CHECK(!engine.pending_pattern_id().has_value());
  LMDJ_CHECK(engine.pattern_telemetry().current_generation ==
             pending.generation);
  LMDJ_CHECK(engine.pattern_telemetry().applied_publications == 2);
  LMDJ_CHECK(engine.current_pattern_has_overlay() == true);
  LMDJ_CHECK(left.at(0) > 0.0F);
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 0);
  render_frames(engine, kRampFrames);
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
  LMDJ_CHECK(!engine.clear_pattern_view().has_value());
  engine.stop();
  LMDJ_CHECK(engine.clear_pattern_view().has_value());
  LMDJ_CHECK(!engine.current_pattern_id().has_value());
  LMDJ_CHECK(!engine.current_pattern_origin_frame().has_value());
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
}

void newest_same_boundary_pattern_supersedes_overlay_without_realtime_free() {
  RealtimeEngine engine;
  const std::array<float, 128> sample = [] {
    std::array<float, 128> value{};
    value.fill(0.5F);
    return value;
  }();
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, 1);
  LMDJ_CHECK(bank.set_sample(0, sample).has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);

  auto initial = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
  LMDJ_CHECK(initial.has_value());
  LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value())).result ==
             PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  render_frames(engine, 100);

  const std::array first_event{lmdj::domain::PatternEvent{
      PadSlotId{0, 0}, 0, lmdj::domain::kBarTicks4x4, 80}};
  const std::array replacement_event{lmdj::domain::PatternEvent{
      PadSlotId{0, 0}, 0, lmdj::domain::kBarTicks4x4, 100}};
  auto first = PreparedPatternView::from_snapshot_with_overlay(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64), first_event);
  auto replacement = PreparedPatternView::from_snapshot_with_overlay(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64), replacement_event);
  auto committed = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 100));
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(replacement.has_value());
  LMDJ_CHECK(committed.has_value());

  const auto first_publication =
      engine.publish_pattern_view(std::move(first.value()));
  const auto replacement_publication =
      engine.publish_pattern_view(std::move(replacement.value()));
  const auto committed_publication =
      engine.publish_pattern_view(std::move(committed.value()));
  LMDJ_CHECK(first_publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(replacement_publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(committed_publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(first_publication.activation_frame == 96'000);
  LMDJ_CHECK(replacement_publication.activation_frame == 96'000);
  LMDJ_CHECK(committed_publication.activation_frame == 96'000);
  LMDJ_CHECK(engine.pattern_telemetry().pending_generation ==
             committed_publication.generation);

  render_frames(engine, 95'899);
  std::array<float, 2> left{};
  std::array<float, 2> right{};
  g_allocations.store(0, std::memory_order_relaxed);
  g_deallocations.store(0, std::memory_order_relaxed);
  g_track_allocations.store(true, std::memory_order_relaxed);
  engine.render(left.data(), right.data(), 2);
  g_track_allocations.store(false, std::memory_order_relaxed);

  const auto telemetry = engine.pattern_telemetry();
  LMDJ_CHECK(g_allocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(g_deallocations.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(telemetry.current_generation == committed_publication.generation);
  LMDJ_CHECK(telemetry.pending_generation == 0);
  LMDJ_CHECK(telemetry.accepted_publications == 4);
  LMDJ_CHECK(telemetry.applied_publications == 2);
  LMDJ_CHECK(telemetry.superseded_publications == 2);
  LMDJ_CHECK(engine.current_pattern_has_overlay() == false);
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 2);
  render_frames(engine, kRampFrames);
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
}

void authoritative_switch_supersedes_only_the_exact_pending_overlay() {
  RealtimeEngine engine;
  auto initial = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
  const std::array overlay_event{lmdj::domain::PatternEvent{
      PadSlotId{0, 0}, 0, lmdj::domain::kBarTicks4x4, 100}};
  auto overlay = PreparedPatternView::from_snapshot_with_overlay(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64), overlay_event);
  auto rejected_target = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternB, PadSlotId{0, 1}, 96));
  auto wrong_target = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternB, PadSlotId{0, 1}, 96));
  auto target = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternB, PadSlotId{0, 1}, 96));
  LMDJ_CHECK(initial.has_value());
  LMDJ_CHECK(overlay.has_value());
  LMDJ_CHECK(rejected_target.has_value());
  LMDJ_CHECK(wrong_target.has_value());
  LMDJ_CHECK(target.has_value());
  LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value())).result ==
             PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  render_frames(engine, 100);

  const auto overlay_publication =
      engine.publish_pattern_view(std::move(overlay.value()));
  LMDJ_CHECK(overlay_publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(overlay_publication.activation_frame == 96'000);
  LMDJ_CHECK(
      engine.publish_pattern_view(std::move(rejected_target.value()), 96'000)
          .result == PatternPublishResult::publication_pending);
  LMDJ_CHECK(
      engine.publish_pattern_view(
                std::move(wrong_target.value()),
                96'000,
                lmdj::audio::PatternReplacementAuthority{
                    overlay_publication.generation + 1,
                    PatternId{kPatternA},
                    96'000})
          .result == PatternPublishResult::publication_pending);

  const auto switched = engine.publish_pattern_view(
      std::move(target.value()),
      96'000,
      lmdj::audio::PatternReplacementAuthority{
          overlay_publication.generation, PatternId{kPatternA}, 96'000});
  LMDJ_CHECK(switched.result == PatternPublishResult::accepted);
  LMDJ_CHECK(switched.activation_frame == 96'000);
  LMDJ_CHECK(engine.pending_pattern_id() == PatternId{kPatternB});
  render_frames(engine, 95'901);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternB});
  LMDJ_CHECK(engine.current_pattern_origin_frame() == 96'000);
  LMDJ_CHECK(!engine.pending_pattern_id().has_value());
}

void exact_cancellation_distinguishes_unclaimed_and_audio_owned_switches() {
  RealtimeEngine engine;
  auto initial = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
  auto target = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternB, PadSlotId{0, 1}, 96));
  auto audio_owned_target = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternB, PadSlotId{0, 1}, 96));
  LMDJ_CHECK(initial.has_value());
  LMDJ_CHECK(target.has_value());
  LMDJ_CHECK(audio_owned_target.has_value());
  LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value())).result ==
             PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  render_frames(engine, 100);
  const auto pending =
      engine.publish_pattern_view(std::move(target.value()), 96'000);
  LMDJ_CHECK(pending.result == PatternPublishResult::accepted);
  LMDJ_CHECK(!engine.cancel_pattern_publication(
      lmdj::audio::PatternReplacementAuthority{
          pending.generation + 1, PatternId{kPatternB}, 96'000}));
  LMDJ_CHECK(engine.cancel_unclaimed_pattern_publication(
      lmdj::audio::PatternReplacementAuthority{
          pending.generation, PatternId{kPatternB}, 96'000}));
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);

  const auto audio_pending = engine.publish_pattern_view(
      std::move(audio_owned_target.value()), 96'000);
  LMDJ_CHECK(audio_pending.result == PatternPublishResult::accepted);
  render_frames(engine, 1);
  LMDJ_CHECK(engine.pattern_telemetry().pending_generation ==
             audio_pending.generation);
  LMDJ_CHECK(!engine.cancel_unclaimed_pattern_publication(
      lmdj::audio::PatternReplacementAuthority{
          audio_pending.generation, PatternId{kPatternB}, 96'000}));
  LMDJ_CHECK(engine.cancel_pattern_publication(
      lmdj::audio::PatternReplacementAuthority{
          audio_pending.generation, PatternId{kPatternB}, 96'000}));
  render_frames(engine, 96'000);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternA});
  LMDJ_CHECK(!engine.pending_pattern_id().has_value());
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
  const auto telemetry = engine.pattern_telemetry();
  LMDJ_CHECK(
      telemetry.accepted_publications ==
      telemetry.applied_publications + telemetry.superseded_publications +
          telemetry.canceled_publications + telemetry.pending_publications);
  LMDJ_CHECK(telemetry.canceled_publications == 2);
}

void apply_point_claim_preserves_authorized_switch_and_rejects_overlap() {
  RealtimeEngine engine;
  auto initial = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
  const std::array overlay_event{lmdj::domain::PatternEvent{
      PadSlotId{0, 0}, 0, lmdj::domain::kBarTicks4x4, 100}};
  auto overlay = PreparedPatternView::from_snapshot_with_overlay(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64), overlay_event);
  auto ordinary_target = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternB, PadSlotId{0, 1}, 96));
  auto authorized_target = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternB, PadSlotId{0, 1}, 96));
  LMDJ_CHECK(initial.has_value());
  LMDJ_CHECK(overlay.has_value());
  LMDJ_CHECK(ordinary_target.has_value());
  LMDJ_CHECK(authorized_target.has_value());
  LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value())).result ==
             PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  render_frames(engine, 100);
  const auto overlay_publication =
      engine.publish_pattern_view(std::move(overlay.value()));
  LMDJ_CHECK(overlay_publication.result == PatternPublishResult::accepted);
  render_frames(engine, 95'899);

  struct ApplyGate final {
    std::atomic<bool> claimed{false};
    std::atomic<bool> release{false};
  } gate;
  lmdj::audio::testing::PatternClaimHook hook{
      &gate,
      [](void* context) noexcept {
        auto& apply_gate = *static_cast<ApplyGate*>(context);
        apply_gate.claimed.store(true, std::memory_order_release);
        while (!apply_gate.release.load(std::memory_order_acquire)) {
          std::this_thread::yield();
        }
      }};
  lmdj::audio::testing::set_pattern_apply_hook(&hook);

  std::array<float, 2> left{};
  std::array<float, 2> right{};
  std::thread callback([&] { engine.render(left.data(), right.data(), 2); });
  while (!gate.claimed.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }
  const auto authority = lmdj::audio::PatternReplacementAuthority{
      overlay_publication.generation, PatternId{kPatternA}, 96'000};
  LMDJ_CHECK(!engine.cancel_pattern_publication(authority));
  LMDJ_CHECK(
      engine.publish_pattern_view(std::move(ordinary_target.value()), 192'000)
          .result == PatternPublishResult::publication_pending);
  const auto switched = engine.publish_pattern_view(
      std::move(authorized_target.value()), 192'000, authority);
  gate.release.store(true, std::memory_order_release);
  callback.join();

  LMDJ_CHECK(switched.result == PatternPublishResult::accepted);
  LMDJ_CHECK(switched.activation_frame == 192'000);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternA});
  LMDJ_CHECK(engine.current_pattern_has_overlay() == true);
  LMDJ_CHECK(engine.pending_pattern_id() == PatternId{kPatternB});
  render_frames(engine, 96'000);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternB});
  const auto telemetry = engine.pattern_telemetry();
  LMDJ_CHECK(
      telemetry.accepted_publications ==
      telemetry.applied_publications + telemetry.superseded_publications +
          telemetry.canceled_publications + telemetry.pending_publications);
  LMDJ_CHECK(telemetry.canceled_publications == 0);
}

void stop_terminally_accounts_every_distinct_pending_pattern() {
  {
    RealtimeEngine engine;
    auto initial = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
    auto queued = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 80));
    LMDJ_CHECK(initial.has_value());
    LMDJ_CHECK(queued.has_value());
    LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value())).result ==
               PatternPublishResult::accepted);
    LMDJ_CHECK(engine.start().has_value());
    render_frames(engine, 100);
    LMDJ_CHECK(
        engine.publish_pattern_view(std::move(queued.value())).result ==
        PatternPublishResult::accepted);

    engine.stop();
    const auto stopped = engine.pattern_telemetry();
    LMDJ_CHECK(stopped.pending_generation == 0);
    LMDJ_CHECK(stopped.accepted_publications == 2);
    LMDJ_CHECK(stopped.applied_publications == 1);
    LMDJ_CHECK(stopped.canceled_publications == 1);
    LMDJ_CHECK(
        stopped.accepted_publications ==
        stopped.applied_publications + stopped.superseded_publications +
            stopped.canceled_publications + stopped.pending_publications);
    LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
    LMDJ_CHECK(engine.start().has_value());
    const auto restarted = engine.pattern_telemetry();
    LMDJ_CHECK(restarted.accepted_publications == 2);
    LMDJ_CHECK(restarted.applied_publications == 1);
    LMDJ_CHECK(restarted.canceled_publications == 1);
    engine.stop();
  }

  {
    RealtimeEngine engine;
    auto initial = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
    auto audio_owned = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 80));
    LMDJ_CHECK(initial.has_value());
    LMDJ_CHECK(audio_owned.has_value());
    LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value())).result ==
               PatternPublishResult::accepted);
    LMDJ_CHECK(engine.start().has_value());
    render_frames(engine, 100);
    LMDJ_CHECK(
        engine.publish_pattern_view(std::move(audio_owned.value())).result ==
        PatternPublishResult::accepted);
    render_frames(engine, 1);

    engine.stop();
    const auto stopped = engine.pattern_telemetry();
    LMDJ_CHECK(stopped.pending_generation == 0);
    LMDJ_CHECK(stopped.accepted_publications == 2);
    LMDJ_CHECK(stopped.applied_publications == 1);
    LMDJ_CHECK(stopped.canceled_publications == 1);
    LMDJ_CHECK(
        stopped.accepted_publications ==
        stopped.applied_publications + stopped.superseded_publications +
            stopped.canceled_publications + stopped.pending_publications);
    LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
  }

  {
    RealtimeEngine engine;
    auto initial = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
    auto audio_owned = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 80));
    auto queued = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 96));
    LMDJ_CHECK(initial.has_value());
    LMDJ_CHECK(audio_owned.has_value());
    LMDJ_CHECK(queued.has_value());
    LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value())).result ==
               PatternPublishResult::accepted);
    LMDJ_CHECK(engine.start().has_value());
    render_frames(engine, 100);
    const auto first =
        engine.publish_pattern_view(std::move(audio_owned.value()));
    LMDJ_CHECK(first.result == PatternPublishResult::accepted);
    render_frames(engine, 1);
    const auto second = engine.publish_pattern_view(
        std::move(queued.value()), first.activation_frame);
    LMDJ_CHECK(second.result == PatternPublishResult::accepted);
    LMDJ_CHECK(first.generation != second.generation);
    const auto concurrently_pending = engine.pattern_telemetry();
    LMDJ_CHECK(concurrently_pending.pending_generation == second.generation);
    LMDJ_CHECK(concurrently_pending.pending_publications == 2);
    LMDJ_CHECK(
        concurrently_pending.accepted_publications ==
        concurrently_pending.applied_publications +
            concurrently_pending.superseded_publications +
            concurrently_pending.canceled_publications +
            concurrently_pending.pending_publications);

    engine.stop();
    const auto stopped = engine.pattern_telemetry();
    LMDJ_CHECK(stopped.pending_generation == 0);
    LMDJ_CHECK(stopped.accepted_publications == 3);
    LMDJ_CHECK(stopped.applied_publications == 1);
    LMDJ_CHECK(stopped.canceled_publications == 2);
    LMDJ_CHECK(
        stopped.accepted_publications ==
        stopped.applied_publications + stopped.superseded_publications +
            stopped.canceled_publications + stopped.pending_publications);
    LMDJ_CHECK(engine.reclaim_retired_patterns() == 2);
  }
}

void publication_claim_race_preserves_the_claimed_boundary_and_phase() {
  RealtimeEngine engine;
  auto initial = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
  const std::array pending_event{lmdj::domain::PatternEvent{
      PadSlotId{0, 0}, 0, lmdj::domain::kBarTicks4x4, 100}};
  auto pending = PreparedPatternView::from_snapshot_with_overlay(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64, 90), pending_event);
  auto replacement = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 100, 90));
  LMDJ_CHECK(initial.has_value());
  LMDJ_CHECK(pending.has_value());
  LMDJ_CHECK(replacement.has_value());
  LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value())).result ==
             PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  render_frames(engine, 100);

  const auto pending_publication =
      engine.publish_pattern_view(std::move(pending.value()));
  LMDJ_CHECK(pending_publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(pending_publication.activation_frame == 96'000);
  render_frames(engine, 95'899);

  struct ClaimGate final {
    std::atomic<bool> claimed{false};
    std::atomic<bool> release{false};
  } gate;
  lmdj::audio::testing::PatternClaimHook hook{
      &gate,
      [](void* context) noexcept {
        auto& claim_gate = *static_cast<ClaimGate*>(context);
        claim_gate.claimed.store(true, std::memory_order_release);
        while (!claim_gate.release.load(std::memory_order_acquire)) {
          std::this_thread::yield();
        }
      }};
  lmdj::audio::testing::set_pattern_claim_hook(&hook);

  std::array<float, 2> left{};
  std::array<float, 2> right{};
  std::thread callback([&] { engine.render(left.data(), right.data(), 2); });
  while (!gate.claimed.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }
  const auto replacement_publication =
      engine.publish_pattern_view(std::move(replacement.value()));
  gate.release.store(true, std::memory_order_release);
  callback.join();

  LMDJ_CHECK(replacement_publication.result ==
             PatternPublishResult::accepted);
  LMDJ_CHECK(replacement_publication.activation_frame == 224'000);
  LMDJ_CHECK(engine.current_pattern_origin_frame() == 96'000);
  LMDJ_CHECK(engine.current_pattern_has_overlay() == true);

  render_frames(engine, 127'999);
  LMDJ_CHECK(engine.current_pattern_origin_frame() == 96'000);
  render_frames(engine, 1);
  LMDJ_CHECK(engine.current_pattern_origin_frame() == 224'000);
  LMDJ_CHECK(engine.current_pattern_has_overlay() == false);
}

void pattern_generation_preserves_its_non_reused_exhaustion_boundary() {
  constexpr auto kLastGeneration =
      (std::uint64_t{1} << 63U) - std::uint64_t{1};
  auto next_generation = kLastGeneration;
  const auto accepted =
      lmdj::audio::detail::take_pattern_generation(next_generation);
  LMDJ_CHECK(accepted == kLastGeneration);
  LMDJ_CHECK(next_generation == lmdj::audio::detail::kPatternGenerationLimit);
  LMDJ_CHECK(!lmdj::audio::detail::take_pattern_generation(next_generation)
                  .has_value());
}

}  // namespace

void* operator new(std::size_t size) { return ordinary_allocation(size); }
void* operator new[](std::size_t size) { return ordinary_allocation(size); }
void* operator new(std::size_t size, std::align_val_t alignment) {
  return aligned_allocation(size, static_cast<std::size_t>(alignment));
}
void* operator new[](std::size_t size, std::align_val_t alignment) {
  return aligned_allocation(size, static_cast<std::size_t>(alignment));
}
void operator delete(void* memory) noexcept { ordinary_deallocation(memory); }
void operator delete[](void* memory) noexcept {
  ordinary_deallocation(memory);
}
void operator delete(void* memory, std::size_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete[](void* memory, std::size_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete(void* memory, std::align_val_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete[](void* memory, std::align_val_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete(
    void* memory, std::size_t, std::align_val_t) noexcept {
  ordinary_deallocation(memory);
}
void operator delete[](
    void* memory, std::size_t, std::align_val_t) noexcept {
  ordinary_deallocation(memory);
}

namespace {
struct PausedRealtimeHook {
  std::atomic<bool> entered{false};
  std::atomic<bool> released{false};
  lmdj::audio::testing::PatternClaimHook hook{
      this, [](void* context) noexcept {
        auto& gate = *static_cast<PausedRealtimeHook*>(context);
        gate.entered.store(true, std::memory_order_release);
        while (!gate.released.load(std::memory_order_acquire)) {
          std::this_thread::yield();
        }
      }};
  void wait() const {
    while (!entered.load(std::memory_order_acquire)) {
      std::this_thread::yield();
    }
  }
  void release() { released.store(true, std::memory_order_release); }
};

void occupancy_includes_one_reservation_and_one_popped_entry(bool fx) {
  using lmdj::audio::testing::RealtimeHookPoint;
  RealtimeEngine engine;
  if (fx) {
    LMDJ_CHECK(engine.prepare_master_fx(120).has_value());
  }
  LMDJ_CHECK(engine.start().has_value());
  const auto enqueue = [&] {
    if (fx) {
      return engine.enqueue_fx_gesture({
          lmdj::audio::FxGestureKind::hold_on, {}, 0}) ==
          lmdj::audio::FxEnqueueResult::accepted;
    }
    return engine.enqueue_control({0, 0, 0, PadControlKind::stop_all, {}}) ==
           EnqueueResult::accepted;
  };
  const auto occupancy = [&] {
    return fx ? engine.master_fx_telemetry().queued_gestures
              : engine.queued_host_input_events_for_testing();
  };
  for (std::size_t i = 0; i < lmdj::audio::kRealtimeQueueCapacity; ++i) {
    LMDJ_CHECK(enqueue());
  }
  PausedRealtimeHook popped;
  lmdj::audio::testing::set_realtime_hook(
      fx ? RealtimeHookPoint::fx_popped : RealtimeHookPoint::host_input_popped,
      &popped.hook);
  std::array<float, 1> left{}, right{};
  std::thread audio([&] { engine.render(left.data(), right.data(), 1); });
  popped.wait();
  LMDJ_CHECK(enqueue());  // Replace the popped-but-still-counted entry.
  LMDJ_CHECK(occupancy() == lmdj::audio::kRealtimeQueueCapacity + 1);
  struct ReservedObservation {
    RealtimeEngine& engine;
    bool fx;
    std::uint64_t count = 0;
  } observed{engine, fx};
  lmdj::audio::testing::PatternClaimHook reserved{
      &observed, [](void* context) noexcept {
        auto& value = *static_cast<ReservedObservation*>(context);
        value.count = value.fx
            ? value.engine.master_fx_telemetry().queued_gestures
            : value.engine.queued_host_input_events_for_testing();
      }};
  lmdj::audio::testing::set_realtime_hook(
      fx ? RealtimeHookPoint::fx_reserved : RealtimeHookPoint::host_input_reserved,
      &reserved);
  LMDJ_CHECK(!enqueue());
  LMDJ_CHECK(observed.count == lmdj::audio::kRealtimeQueueCapacity + 2);
  LMDJ_CHECK(occupancy() == lmdj::audio::kRealtimeQueueCapacity + 1);
  popped.release();
  audio.join();
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(occupancy() == 0);
  engine.stop();
}

void bank_mask_handoff_preserves_both_32_bit_halves() {
  RealtimeEngine engine;
  const std::array sample{0.25F};
  LMDJ_CHECK(engine.publish_sample_bank(bank_with_sample(1, sample)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  auto bank = bank_with_sample(2, sample);
  LMDJ_CHECK(bank.set_sample(63, sample).has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) == PublishResult::accepted);
  PausedRealtimeHook gate;
  lmdj::audio::testing::set_realtime_hook(
      lmdj::audio::testing::RealtimeHookPoint::bank_mask_written, &gate.hook);
  std::array<float, 1> left{}, right{};
  std::thread audio([&] { engine.render(left.data(), right.data(), 1); });
  gate.wait();
  LMDJ_CHECK(engine.enqueue({1, 0, 127}) == EnqueueResult::bank_transition);
  LMDJ_CHECK(engine.enqueue({2, 63, 127}) == EnqueueResult::bank_transition);
  gate.release();
  audio.join();
  LMDJ_CHECK(engine.enqueue({3, 0, 127}) == EnqueueResult::accepted);
  LMDJ_CHECK(engine.enqueue({4, 63, 127}) == EnqueueResult::accepted);
  engine.stop();
}

void pattern_claim_uses_latest_slot_owner_after_reuse() {
  RealtimeEngine engine;
  engine.set_next_pattern_generation_for_testing(0x100000001ULL);
  const auto make_pattern = [] {
    auto pattern = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
    LMDJ_CHECK(pattern.has_value());
    return std::move(pattern.value());
  };
  const auto initial = engine.publish_pattern_view(make_pattern());
  LMDJ_CHECK(initial.generation == 0x100000001ULL);
  LMDJ_CHECK(engine.start().has_value());
  auto pending = engine.publish_pattern_view(make_pattern(), 1);
  LMDJ_CHECK(pending.result == PatternPublishResult::accepted);
  PausedRealtimeHook gate;
  lmdj::audio::testing::set_realtime_hook(
      lmdj::audio::testing::RealtimeHookPoint::before_pattern_claim, &gate.hook);
  std::array<float, 1> left{}, right{};
  std::thread audio([&] { engine.render(left.data(), right.data(), 1); });
  gate.wait();
  for (int reuse = 0; reuse < 64; ++reuse) {
    LMDJ_CHECK(engine.cancel_unclaimed_pattern_publication({
        pending.generation, PatternId{kPatternA}, 1}));
    LMDJ_CHECK(engine.pattern_telemetry().pending_publications == 0);
    LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
    pending = engine.publish_pattern_view(make_pattern(), 1);
    LMDJ_CHECK(pending.result == PatternPublishResult::accepted);
  }
  gate.release();
  audio.join();
  const auto claimed = engine.pattern_telemetry();
  LMDJ_CHECK(claimed.pending_generation == pending.generation);
  LMDJ_CHECK(claimed.pending_activation_frame == 1);
  LMDJ_CHECK(claimed.pending_publications == 1);
  engine.render(left.data(), right.data(), 1);
  const auto applied = engine.pattern_telemetry();
  LMDJ_CHECK(applied.current_generation == pending.generation);
  LMDJ_CHECK(applied.pending_generation == 0);
  LMDJ_CHECK(applied.pending_publications == 0);
  LMDJ_CHECK(applied.canceled_publications == 64);
  engine.stop();
}

void cancel_audio_then_queued_is_final_without_another_callback() {
  RealtimeEngine engine;
  const auto make_pattern = [] {
    auto pattern = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
    LMDJ_CHECK(pattern.has_value());
    return std::move(pattern.value());
  };
  LMDJ_CHECK(engine.publish_pattern_view(make_pattern()).result ==
             PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  const auto audio_pending = engine.publish_pattern_view(make_pattern(), 100);
  LMDJ_CHECK(audio_pending.result == PatternPublishResult::accepted);
  render_frames(engine, 1);
  const auto queued = engine.publish_pattern_view(make_pattern(), 100);
  LMDJ_CHECK(queued.result == PatternPublishResult::accepted);
  LMDJ_CHECK(engine.pattern_telemetry().pending_publications == 2);
  LMDJ_CHECK(engine.cancel_pattern_publication({
      audio_pending.generation, PatternId{kPatternA}, 100}));
  LMDJ_CHECK(engine.pattern_telemetry().pending_publications == 1);
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 0);  // Audio still owns L.
  LMDJ_CHECK(engine.cancel_unclaimed_pattern_publication({
      queued.generation, PatternId{kPatternA}, 100}));
  const auto final = engine.pattern_telemetry();
  LMDJ_CHECK(final.pending_generation == 0);
  LMDJ_CHECK(final.pending_activation_frame == 0);
  LMDJ_CHECK(final.pending_publications == 0);
  LMDJ_CHECK(final.canceled_publications == 2);
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
  engine.stop();
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
  LMDJ_CHECK(engine.pattern_telemetry().canceled_publications == 2);
}

void transport_and_telemetry_preserve_64_bit_frame_carry() {
  RealtimeEngine engine;
  LMDJ_CHECK(engine.start().has_value());
  engine.set_rendered_frames_quiescent_for_testing(0xffffffffULL);
  render_frames(engine, 2);
  LMDJ_CHECK(engine.telemetry().rendered_frames == 0x100000001ULL);
  auto pattern = PreparedPatternView::from_snapshot(
      pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
  LMDJ_CHECK(pattern.has_value());
  const auto publication = engine.publish_pattern_view_immediate(
      std::move(pattern.value()));
  LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(publication.activation_frame == 0x100000001ULL);
  render_frames(engine, 1);
  LMDJ_CHECK(engine.current_pattern_origin_frame() == 0x100000001ULL);
  LMDJ_CHECK(engine.pattern_telemetry().pending_generation == 0);
  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.telemetry().rendered_frames == 0);
  LMDJ_CHECK(engine.current_pattern_origin_frame() == 0);
  engine.stop();
}
}  // namespace

namespace {
void admission_retry_recomputes_boundary_without_audio_waiting(bool queued) {
  using lmdj::audio::testing::RealtimeHookPoint;
  RealtimeEngine engine;
  const auto make_pattern = [] {
    auto pattern = PreparedPatternView::from_snapshot(
        pattern_snapshot(kPatternA, PadSlotId{0, 0}, 64));
    LMDJ_CHECK(pattern.has_value());
    return std::move(pattern.value());
  };
  auto current = engine.publish_pattern_view(make_pattern());
  LMDJ_CHECK(current.result == PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  if (queued) {
    current = engine.publish_pattern_view(make_pattern(), 1);
    LMDJ_CHECK(current.result == PatternPublishResult::accepted);
  }
  PausedRealtimeHook audio_gate, control_gate;
  lmdj::audio::testing::set_realtime_hook(
      RealtimeHookPoint::pattern_admission_closed, &audio_gate.hook);
  lmdj::audio::testing::set_realtime_hook(
      RealtimeHookPoint::control_pattern_admission_retry, &control_gate.hook);
  std::array<float, 2> left{}, right{};
  std::thread audio([&] { engine.render(left.data(), right.data(), 2); });
  audio_gate.wait();
  lmdj::audio::PatternPublication next{};
  std::thread control([&] { next = engine.publish_pattern_view(make_pattern()); });
  control_gate.wait();
  audio_gate.release();
  audio.join();  // Audio finishes while the control producer is still paused.
  LMDJ_CHECK(engine.pattern_telemetry().current_generation == current.generation);
  LMDJ_CHECK(engine.pattern_telemetry().pending_publications == 0);
  control_gate.release();
  control.join();
  LMDJ_CHECK(next.result == PatternPublishResult::accepted);
  LMDJ_CHECK(next.activation_frame == (queued ? 96'001U : 96'000U));
  LMDJ_CHECK(engine.pattern_telemetry().pending_generation == next.generation);
  engine.stop();
}

void capture_handoff_exposes_origin_and_final_count_before_callback_return() {
  RealtimeEngine engine;
  const std::array sample{0.25F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  render_frames(engine, 100);
  LMDJ_CHECK(engine.arm_capture().has_value());
  LMDJ_CHECK(engine.enqueue({1, 0, 127}) == EnqueueResult::accepted);
  PausedRealtimeHook event_gate, idle_gate;
  lmdj::audio::testing::set_realtime_hook(
      lmdj::audio::testing::RealtimeHookPoint::capture_event_published,
      &event_gate.hook);
  lmdj::audio::testing::set_realtime_hook(
      lmdj::audio::testing::RealtimeHookPoint::capture_idle_published,
      &idle_gate.hook);
  std::array<float, 1> left{}, right{};
  std::thread audio([&] { engine.render(left.data(), right.data(), 1); });
  event_gate.wait();
  std::array<CapturedTriggerEvent, 1> captured{};
  LMDJ_CHECK(engine.drain_capture(captured) == 1);
  const auto active = engine.capture_telemetry();
  LMDJ_CHECK(active.state == CaptureState::active);
  LMDJ_CHECK(active.capture_origin_frame + captured[0].frame_offset == 100);
  LMDJ_CHECK(engine.disarm_capture().has_value());
  PausedRealtimeHook observer_gate;
  lmdj::audio::testing::set_realtime_hook(
      lmdj::audio::testing::RealtimeHookPoint::capture_observe_state,
      &observer_gate.hook);
  lmdj::audio::CaptureTelemetry final{};
  std::thread observer([&] { final = engine.capture_telemetry(); });
  observer_gate.wait();  // Pause immediately before acquiring capture state.
  event_gate.release();
  idle_gate.wait();
  observer_gate.release();
  observer.join();  // New idle must not be paired with pre-handoff counts.
  LMDJ_CHECK(final.state == CaptureState::idle);
  LMDJ_CHECK(final.captured_events == 1);
  LMDJ_CHECK(final.drained_events == 1);
  idle_gate.release();
  audio.join();
  engine.stop();
}

void render_and_adapter_status_finish_while_observer_holds_reader_lock() {
  RealtimeEngine engine;
  LMDJ_CHECK(engine.start().has_value());
  const std::array sample{0.25F};
  LMDJ_CHECK(engine.publish_sample_bank(bank_with_sample(1, sample)) ==
             PublishResult::accepted);
  PausedRealtimeHook reader_gate;
  lmdj::audio::testing::set_realtime_hook(
      lmdj::audio::testing::RealtimeHookPoint::observation_read, &reader_gate.hook);
  std::thread observer([&] { static_cast<void>(engine.telemetry()); });
  reader_gate.wait();
  lmdj::audio::detail::RealtimeEngineAudioAccess::Status status{};
  std::thread audio([&] {
    std::array<float, 1> left{}, right{};
    engine.render(left.data(), right.data(), 1);
    status = lmdj::audio::detail::RealtimeEngineAudioAccess::status(engine);
  });
  audio.join();  // Must not require the observer to finish its copy/unlock.
  LMDJ_CHECK(status.bank_generation == 1);
  LMDJ_CHECK(status.voice_state ==
             lmdj::audio::RuntimeVoiceStateStreamState::healthy);
  reader_gate.release();
  observer.join();
  LMDJ_CHECK(engine.bank_telemetry().current_generation == status.bank_generation);
  engine.stop();
}
}  // namespace

int main() {
  engine_queue_profiles_account_for_all_allocated_payloads();
  receipt_profile_rejects_invalid_capacity();
  pcm_replacement_releases_the_actual_float_allocation();
  pcm_and_float_banks_render_identical_live_pattern_and_audition();
  pcm_old_bank_lives_until_control_reclaims_after_voice_completion();
  capture_storage_is_allocated_only_on_first_arm();
  capture_allocation_failure_leaves_playback_running_and_retryable();
  capture_storage_survives_stop_and_restart_without_reallocation();
  capture_handoff_exposes_origin_and_final_count_before_callback_return();
  render_and_adapter_status_finish_while_observer_holds_reader_lock();
  admission_retry_recomputes_boundary_without_audio_waiting(false);
  admission_retry_recomputes_boundary_without_audio_waiting(true);
  occupancy_includes_one_reservation_and_one_popped_entry(false);
  occupancy_includes_one_reservation_and_one_popped_entry(true);
  bank_mask_handoff_preserves_both_32_bit_halves();
  pattern_claim_uses_latest_slot_owner_after_reuse();
  cancel_audio_then_queued_is_final_without_another_callback();
  transport_and_telemetry_preserve_64_bit_frame_carry();
  fixed_control_and_voice_messages_are_realtime_safe_values();
  one_shot_snapshots_trim_gain_and_ignores_release();
  gate_release_fades_a_ramp_tail_from_the_exact_cursor();
  loop_gate_wraps_only_inside_the_selection_then_releases();
  loop_toggle_is_latched_per_pad_and_stops_on_its_next_press();
  mute_starts_no_voice_and_invalid_preview_bounds_are_rejected();
  preview_set_and_clear_affect_only_later_voice_snapshots();
  direct_press_never_falls_back_from_non_sentinel_invalid_playback();
  legacy_enqueue_uses_published_snapshot_while_preview_is_active();
  control_queue_overflow_rejects_preview_without_applying_it();
  stop_slot_targets_one_pad_and_stop_all_clears_latched_voices();
  voice_state_overflow_raises_the_existing_fail_closed_signal();
  plays_a_sample_and_reports_render_telemetry();
  rejects_invalid_samples_and_running_time_mutation();
  supports_exact_64_slot_boundary();
  validates_events_and_cleared_slots();
  applies_velocity_gain_and_clamps_after_mixing();
  reports_queue_capacity_and_drops();
  caps_simultaneous_voices_and_mixes_each_admitted_voice();
  publishes_ordered_mixed_outcomes_at_128_frame_boundaries();
  outcome_ring_reports_capacity_drop_and_restart_resets_it();
  completes_a_sample_across_callback_blocks();
  publishes_sample_banks_only_at_safe_render_boundaries();
  rejects_publication_until_trigger_queue_is_empty();
  applies_explicit_bank_slot_backpressure_until_reclaimed();
  audition_renders_its_own_bytes_while_the_project_bank_stays_current();
  an_audition_publishes_no_voice_state_edge();
  audition_never_consumes_a_project_bank_slot();
  replacing_an_audition_drains_the_outgoing_bank();
  audition_reclamation_preserves_project_pcm_reservations();
  audition_never_becomes_current_and_never_moves_availability();
  audition_without_a_published_bank_is_refused_at_enqueue();
  reports_exact_bytes_for_non_fifo_heterogeneous_bank_reclaim();
  preserves_high_frame_trim_loop_and_ramp_arithmetic();
  captures_voice_starts_at_exact_runtime_frames_and_disarms_at_end();
  replay_origin_uses_scheduled_release_without_live_identity_streams();
  live_release_does_not_stop_same_slot_replay_voice();
  captures_only_successfully_allocated_voices();
  capture_overflow_remains_observable_without_a_voice_state_consumer();
  stop_cancels_queued_events_and_active_voices();
  restart_resets_counters_retains_samples_and_replays_no_event();
  start_epoch_overflow_fails_before_mutating_engine_state();
  render_does_not_allocate_or_deallocate();
  attack_ramps_to_full_gain_over_exactly_the_ramp_frames();
  non_loop_boundary_fades_to_exact_zero_at_end_frame();
  stop_voice_renders_a_full_ramp_tail_then_deactivates();
  releasing_voice_is_hard_killed_by_a_second_stop();
  voice_shorter_than_the_ramp_multiplies_attack_and_boundary();
  publishes_immutable_patterns_at_the_next_bar_boundary();
  newest_same_boundary_pattern_supersedes_overlay_without_realtime_free();
  authoritative_switch_supersedes_only_the_exact_pending_overlay();
  exact_cancellation_distinguishes_unclaimed_and_audio_owned_switches();
  apply_point_claim_preserves_authorized_switch_and_rejects_overlap();
  stop_terminally_accounts_every_distinct_pending_pattern();
  publication_claim_race_preserves_the_claimed_boundary_and_phase();
  pattern_generation_preserves_its_non_reused_exhaustion_boundary();
}
