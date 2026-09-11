#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <new>
#include <span>
#include <thread>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

thread_local bool callback_active{};
thread_local bool track_allocators{};
thread_local std::size_t allocator_calls{};
void allocator_boundary() {
  if (callback_active) std::abort();
  if (track_allocators) ++allocator_calls;
}
void* ordinary_allocate(std::size_t bytes) {
  allocator_boundary();
  if (auto* result = std::malloc(bytes == 0 ? 1 : bytes)) return result;
  throw std::bad_alloc{};
}
void* aligned_allocate(std::size_t bytes, std::size_t alignment) {
  allocator_boundary();
  void* result{};
  if (posix_memalign(&result, alignment, bytes == 0 ? alignment : bytes) == 0)
    return result;
  throw std::bad_alloc{};
}
void release_allocation(void* memory) noexcept {
  if (!memory) return;
  allocator_boundary();
  std::free(memory);
}

void pattern_transport_receipts_race_publication_and_reclaim() {
  using namespace lmdj;
  using namespace lmdj::audio;
  const foundation::ProjectId project{"00000000-0000-4000-8000-000000000001"};
  const foundation::PatternId pattern{"00000000-0000-4000-8000-000000000002"};
  auto make_view = [&] {
    auto pcm = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
        48'000, 1, std::vector<std::int16_t>(128, 12'000)});
    cooker::RuntimeSnapshot snapshot{project, pattern, 1, 120, 1,
        domain::kPpq, domain::kBarTicks4x4,
        {{domain::PadSlotId{0, 0},
          foundation::ArtifactRef{std::string(64, 'a'), "audio/wav", 256}, pcm,
          {0, 128, domain::TriggerMode::loop_gate, 1.0F, false}}},
        {{domain::PadSlotId{0, 0}, 0, domain::kBarTicks4x4, 127, pcm}}};
    auto result = PreparedPatternView::from_snapshot(snapshot);
    LMDJ_CHECK(result.has_value());
    return std::move(result.value());
  };
  RealtimeEngine engine;
  LMDJ_CHECK(engine.enable_pattern_transport(17).has_value());
  auto publication = engine.publish_pattern_view(make_view());
  LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  std::atomic<bool> done{};
  std::thread callback([&] {
    std::array<float, 64> left{}, right{};
    while (!done.load(std::memory_order_acquire)) {
      callback_active = true;
      engine.render(left.data(), right.data(), left.size());
      callback_active = false;
      for (const auto sample : left) LMDJ_CHECK(std::isfinite(sample));
      std::this_thread::yield();
    }
  });
  std::uint64_t epoch = 0, accepted = 0, refused = 0;
  std::uint64_t current = publication.generation;
  auto apply = [&](PatternTransportAction action,
                   std::optional<PatternReplacementAuthority> authority = {}) {
    const PatternTransportCommand command{17, ++epoch, current, action, authority};
    LMDJ_CHECK(engine.submit_pattern_transport(command) == PatternTransportSubmit::accepted);
    ++accepted;
    LMDJ_CHECK(engine.submit_pattern_transport(command) == PatternTransportSubmit::busy);
    ++refused;
    LMDJ_CHECK(engine.publish_pattern_view(make_view()).result == PatternPublishResult::publication_pending);
    std::optional<PatternTransportReceipt> receipt;
    while (!(receipt = engine.inspect_pattern_transport_receipt(17, epoch)))
      std::this_thread::yield();
    LMDJ_CHECK(receipt->runtime_generation == 17 && receipt->epoch == epoch);
    LMDJ_CHECK(receipt->pattern_id == pattern && receipt->bpm == 120);
    LMDJ_CHECK(receipt->playing == (action != PatternTransportAction::stop));
    if (authority) {
      LMDJ_CHECK(receipt->switch_authority->generation == authority->generation);
      if (receipt->switch_decision == PatternCutoffDecision::applied_before_cutoff) {
        LMDJ_CHECK(receipt->switch_applied_frame &&
            *receipt->switch_applied_frame < receipt->effective_frame);
        LMDJ_CHECK(receipt->pattern_generation == authority->generation);
      } else {
        LMDJ_CHECK(receipt->switch_decision == PatternCutoffDecision::canceled_at_cutoff);
        LMDJ_CHECK(!receipt->switch_applied_frame && receipt->pattern_generation == current);
      }
    }
    const auto retained = engine.inspect_pattern_transport_receipt(17, epoch);
    LMDJ_CHECK(retained->effective_frame == receipt->effective_frame &&
        retained->origin_frame == receipt->origin_frame &&
        retained->pattern_generation == receipt->pattern_generation);
    LMDJ_CHECK(engine.acknowledge_pattern_transport_receipt(17, epoch));
    LMDJ_CHECK(!engine.inspect_pattern_transport_receipt(17, epoch));
    LMDJ_CHECK(engine.submit_pattern_transport(command) == PatternTransportSubmit::stale_epoch);
    ++refused;
    current = receipt->pattern_generation;
    return *receipt;
  };
  for (unsigned cycle = 0; cycle < 300; ++cycle) {
    const auto start = apply(PatternTransportAction::start);
    LMDJ_CHECK(start.origin_frame == start.effective_frame);
    const auto fence = apply(PatternTransportAction::fence);
    LMDJ_CHECK(fence.origin_frame == start.origin_frame);
    engine.reclaim_retired_patterns();
    publication = engine.publish_pattern_view_immediate(make_view());
    LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
    apply(PatternTransportAction::stop,
        PatternReplacementAuthority{publication.generation, pattern, publication.activation_frame});
    engine.reclaim_retired_patterns();
    LMDJ_CHECK(engine.telemetry().active_voices <= kRealtimeVoiceCapacity);
  }
  done.store(true, std::memory_order_release);
  callback.join();
  LMDJ_CHECK(accepted == 900 && refused == 1800);
  const auto telemetry = engine.pattern_telemetry();
  LMDJ_CHECK(telemetry.pending_publications == 0);
  LMDJ_CHECK(telemetry.accepted_publications ==
      telemetry.applied_publications + telemetry.canceled_publications);
  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  std::array<float, 128> left{}, right{};
  engine.render(left.data(), right.data(), left.size());
  LMDJ_CHECK(std::all_of(left.begin(), left.end(), [](float value) { return value == 0; }));
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.submit_pattern_transport(
      {17, epoch + 1, current, PatternTransportAction::start, {}}) ==
      PatternTransportSubmit::stale_generation);
}

void pcm_publication_retirement_races_real_render_without_owner_destruction() {
  using namespace lmdj;
  using namespace lmdj::audio;
  track_allocators = true;
  allocator_calls = 0;
  auto* ordinary = ::operator new(37);
  auto* aligned = ::operator new(129, std::align_val_t{64});
  ::operator delete(ordinary);
  ::operator delete(aligned, std::align_val_t{64});
  track_allocators = false;
  LMDJ_CHECK(allocator_calls == 4);

  RealtimeEngine engine;
  LMDJ_CHECK(engine.start().has_value());
  std::atomic<bool> done{};
  std::thread callback([&] {
    std::array<float, 64> left{}, right{};
    while (!done.load(std::memory_order_acquire)) {
      callback_active = true;
      engine.render(left.data(), right.data(), left.size());
      callback_active = false;
      std::this_thread::yield();
    }
  });
  std::uint64_t sequence = 0;
  for (std::uint64_t generation = 1; generation <= 1000; ++generation) {
    auto owner = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
        48'000, 1, std::vector<std::int16_t>(256, 16'384)});
    std::weak_ptr<const cooker::PcmSample> lifetime = owner;
    auto bank = PreparedSampleBank::empty(
        foundation::ProjectId{"00000000-0000-4000-8000-000000000001"}, generation);
    LMDJ_CHECK(bank.set_pcm_sample(0, owner,
        {0, 256, domain::TriggerMode::loop_gate, 1, false}).has_value());
    owner.reset();
    LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) == PublishResult::accepted);
    for (;;) {
      const auto observed = engine.bank_telemetry();
      // Generation becomes visible before the pending-zero admission handoff.
      if (observed.current_generation == generation * 2 - 1 &&
          observed.pending_publications == 0) break;
      std::this_thread::yield();
    }
    (void)engine.reclaim_retired_banks();
    LMDJ_CHECK(engine.enqueue_control(
        {++sequence, 0, 127, PadControlKind::press, {}}) == EnqueueResult::accepted);
    while (engine.telemetry().started_voices != generation)
      std::this_thread::yield();

    auto next = PreparedSampleBank::empty(
        foundation::ProjectId{"00000000-0000-4000-8000-000000000001"}, generation + 1);
    LMDJ_CHECK(next.set_pcm_sample(0,
        std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
            48'000, 2, std::vector<std::int16_t>(512, -16'384)}),
        {0, 256, domain::TriggerMode::one_shot, 1, false}).has_value());
    LMDJ_CHECK(engine.publish_sample_bank(std::move(next)) == PublishResult::accepted);
    while (engine.bank_telemetry().current_generation != generation * 2)
      std::this_thread::yield();
    LMDJ_CHECK(!lifetime.expired());
    LMDJ_CHECK(engine.reclaim_retired_banks() == 0);
    LMDJ_CHECK(engine.enqueue_control(
        {++sequence, 0, 0, PadControlKind::stop_all, {}}) == EnqueueResult::accepted);
    for (;;) {
      const auto telemetry = engine.telemetry();
      if (telemetry.dequeued_events == sequence && telemetry.active_voices == 0) break;
      std::this_thread::yield();
    }
    LMDJ_CHECK(!lifetime.expired());
    const auto reclaimed = engine.reclaim_retired_bank_telemetry();
    LMDJ_CHECK(reclaimed.count == 1 && reclaimed.decoded_pcm_bytes == 512);
    LMDJ_CHECK(lifetime.expired());
    std::array<RuntimeVoiceStateEvent, 8> states{};
    std::array<RuntimeTriggerOutcomeEvent, 8> outcomes{};
    LMDJ_CHECK(engine.drain_voice_states(states) == 2);
    LMDJ_CHECK(engine.drain_trigger_outcomes(outcomes) == 1);
  }
  done.store(true, std::memory_order_release);
  callback.join();
  engine.stop();
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
}

void pcm_audition_replacement_keeps_both_owners_until_audio_release() {
  using namespace lmdj;
  using namespace lmdj::audio;
  RealtimeEngine engine;
  LMDJ_CHECK(engine.start().has_value());
  const auto make_bank = [](std::shared_ptr<const cooker::PcmSample> owner) {
    auto bank = PreparedSampleBank::empty(kAuditionBankProjectId(),
                                           kAuditionBankProjectRevision);
    LMDJ_CHECK(bank.set_pcm_sample(0, std::move(owner),
        {0, 256, domain::TriggerMode::loop_gate, 0.5F, false}).has_value());
    return bank;
  };
  std::atomic<bool> done{};
  std::thread callback([&] {
    std::array<float, 64> left{}, right{};
    while (!done.load(std::memory_order_acquire)) {
      callback_active = true;
      engine.render(left.data(), right.data(), left.size());
      callback_active = false;
      std::this_thread::yield();
    }
  });
  std::uint64_t sequence = 0;
  std::size_t full_refusals = 0;
  for (std::uint64_t generation = 1; generation <= 1000; ++generation) {
    auto owner = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
        48'000, 1, std::vector<std::int16_t>(256, 16'384)});
    std::weak_ptr<const cooker::PcmSample> lifetime = owner;
    auto old = make_bank(std::move(owner));
    LMDJ_CHECK(engine.publish_audition_bank(std::move(old)) == PublishResult::accepted);
    LMDJ_CHECK(engine.enqueue_control(
        {++sequence, 0, 127, PadControlKind::audition_start, {}}) == EnqueueResult::accepted);
    while (engine.telemetry().started_voices != generation * 2 - 1)
      std::this_thread::yield();
    (void)engine.reclaim_retired_banks();
    const auto next_owner = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
        48'000, 2, std::vector<std::int16_t>(512, 8192)});
    LMDJ_CHECK(engine.publish_audition_bank(make_bank(next_owner)) == PublishResult::accepted);
    LMDJ_CHECK(engine.enqueue_control(
        {++sequence, 0, 127, PadControlKind::audition_start, {}}) == EnqueueResult::accepted);
    while (engine.telemetry().started_voices != generation * 2)
      std::this_thread::yield();
    LMDJ_CHECK(engine.telemetry().active_voices == 2);
    LMDJ_CHECK(!lifetime.expired());
    LMDJ_CHECK(engine.reclaim_retired_banks() == 0);
    LMDJ_CHECK(engine.publish_audition_bank(make_bank(next_owner)) == PublishResult::bank_slots_full);
    ++full_refusals;
    LMDJ_CHECK(engine.enqueue_control(
        {++sequence, 0, 0, PadControlKind::audition_stop, {}}) == EnqueueResult::accepted);
    for (;;) {
      const auto telemetry = engine.telemetry();
      if (telemetry.dequeued_events == sequence && telemetry.active_voices == 0) break;
      std::this_thread::yield();
    }
    LMDJ_CHECK(!lifetime.expired());
    const auto reclaimed = engine.reclaim_retired_bank_telemetry();
    LMDJ_CHECK(reclaimed.count == 1 && reclaimed.decoded_pcm_bytes == 0);
    LMDJ_CHECK(lifetime.expired());
    std::array<RuntimeVoiceStateEvent, 8> states{};
    std::array<RuntimeTriggerOutcomeEvent, 8> outcomes{};
    LMDJ_CHECK(engine.drain_voice_states(states) == 0);
    LMDJ_CHECK(engine.drain_trigger_outcomes(outcomes) == 0);
  }
  done.store(true, std::memory_order_release);
  callback.join();
  engine.stop();
  LMDJ_CHECK(full_refusals == 1000);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
}

template <typename Queue>
void check_voice_state_contention(Queue& queue) {
  constexpr std::uint64_t kEvents = 1'000'000;
  std::thread producer([&] {
    for (std::uint64_t index = 0; index < kEvents; ++index) {
      const lmdj::audio::RuntimeVoiceStateEvent event{
          std::numeric_limits<std::uint64_t>::max() - index,
          static_cast<std::uint8_t>(index % 256),
          static_cast<lmdj::audio::RuntimeVoiceState>(index % 3),
          (std::uint64_t{1} << 63) + index,
          std::numeric_limits<std::uint32_t>::max() -
              static_cast<std::uint32_t>(index),
      };
      while (!queue.try_push(event)) {
        std::this_thread::yield();
      }
    }
  });
  for (std::uint64_t index = 0; index < kEvents; ++index) {
    lmdj::audio::RuntimeVoiceStateEvent event{};
    while (!queue.try_pop(event)) {
      std::this_thread::yield();
    }
    LMDJ_CHECK(event.sequence ==
               std::numeric_limits<std::uint64_t>::max() - index);
    LMDJ_CHECK(event.slot == index % 256);
    LMDJ_CHECK(event.state ==
               static_cast<lmdj::audio::RuntimeVoiceState>(index % 3));
    LMDJ_CHECK(event.runtime_frame == (std::uint64_t{1} << 63) + index);
    LMDJ_CHECK(event.source_frame ==
               std::numeric_limits<std::uint32_t>::max() - index);
  }
  producer.join();
  LMDJ_CHECK(queue.size_approx() == 0);
}

void preserves_compact_voice_states_under_spsc_contention() {
  // Retain the tiny-ring test and also exercise both actual storage branches.
  lmdj::audio::detail::RuntimeVoiceStateQueue<7> small;
  check_voice_state_contention(small);
  lmdj::audio::detail::RuntimeVoiceStateStorage full;
  check_voice_state_contention(full);
  lmdj::audio::detail::RuntimeVoiceStateStorage bounded(true);
  check_voice_state_contention(bounded);
  for (const std::size_t pending : {1U, 128U, 1024U}) {
    lmdj::audio::detail::RuntimeVoiceStateStorage sized(true, pending);
    check_voice_state_contention(sized);
  }
}

template <typename Queue>
void check_trigger_contention(Queue& queue) {
  constexpr std::uint64_t kEvents = 1'000'000;
  std::atomic<bool> producer_done{false};

  std::thread producer([&] {
    for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
      while (!queue.try_push(lmdj::audio::PadControlEvent{
          sequence,
          static_cast<std::uint8_t>(sequence % 64),
          100,
          lmdj::audio::PadControlKind::preview_set,
          lmdj::cooker::ResolvedPlayback{
              1,
              3,
              lmdj::domain::TriggerMode::loop_gate,
              0.5F,
              false,
          },
      })) {
        std::this_thread::yield();
      }
    }
    producer_done.store(true, std::memory_order_release);
  });

  std::uint64_t expected = 0;
  while (expected < kEvents ||
         !producer_done.load(std::memory_order_acquire)) {
    lmdj::audio::PadControlEvent event{};
    if (!queue.try_pop(event)) {
      std::this_thread::yield();
      continue;
    }
    LMDJ_CHECK(event.sequence == expected);
    LMDJ_CHECK(event.slot == expected % 64);
    LMDJ_CHECK(event.velocity == 100);
    LMDJ_CHECK(event.kind == lmdj::audio::PadControlKind::preview_set);
    LMDJ_CHECK(event.playback.start_frame == 1);
    LMDJ_CHECK(event.playback.end_frame == 3);
    LMDJ_CHECK(
        event.playback.trigger_mode == lmdj::domain::TriggerMode::loop_gate);
    LMDJ_CHECK(event.playback.linear_gain == 0.5F);
    LMDJ_CHECK(!event.playback.muted);
    ++expected;
  }
  producer.join();
  LMDJ_CHECK(expected == kEvents);
  LMDJ_CHECK(queue.size_approx() == 0);
}

void preserves_all_trigger_events_under_spsc_contention() {
  lmdj::audio::detail::FixedSpscQueue<lmdj::audio::PadControlEvent, 1024> fixed;
  check_trigger_contention(fixed);
  for (const std::size_t capacity : {1U, 128U, 1024U}) {
    lmdj::audio::detail::RuntimeSpscStorage<lmdj::audio::PadControlEvent> sized(capacity);
    check_trigger_contention(sized);
  }
}

void transports_all_voice_starts_to_concurrent_bounded_drains() {
  constexpr std::uint64_t kEvents = 100'000;
  constexpr std::uint64_t kMaxInFlightVoices = 1;
  constexpr std::uint64_t kMaxCaptureBacklog = 256;
  constexpr std::uint64_t kMaxOutcomeBacklog = 256;
  constexpr std::uint64_t kMaxVoiceStateBacklog = 512;
  lmdj::audio::RealtimeEngine engine;
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  std::array<float, 1> left{};
  std::array<float, 1> right{};

  std::atomic<bool> render_done{false};
  std::vector<std::uint64_t> admitted(kEvents);
  std::vector<lmdj::audio::CapturedTriggerEvent> captured(kEvents);
  std::vector<lmdj::audio::RuntimeTriggerOutcomeEvent> outcomes(kEvents);
  std::vector<lmdj::audio::RuntimeVoiceStateEvent> voice_states(kEvents * 2);
  std::size_t captured_count = 0;
  std::size_t outcome_count = 0;
  std::size_t voice_state_count = 0;

  std::thread renderer([&] {
    while (!render_done.load(std::memory_order_acquire)) {
      engine.render(left.data(), right.data(), 1);
    }
  });

  // Exercise the first allocation/publication with an already-running audio
  // consumer, not merely queue transport after a quiescent preparation.
  while (engine.telemetry().callback_count == 0) {
    std::this_thread::yield();
  }
  LMDJ_CHECK(engine.arm_capture().has_value());
  while (engine.capture_telemetry().state !=
         lmdj::audio::CaptureState::active) {
    std::this_thread::yield();
  }
  const auto capture_origin = engine.capture_telemetry().capture_origin_frame;
  LMDJ_CHECK(capture_origin > 0);

  std::uint64_t admitted_count = 0;
  while (admitted_count < kEvents) {
    bool made_progress = false;
    const auto realtime = engine.telemetry();
    const auto capture = engine.capture_telemetry();
    const auto outcome = engine.trigger_outcome_telemetry();
    const auto voice_state = engine.voice_state_telemetry();
    const auto capture_backlog =
        capture.captured_events >= capture.drained_events
            ? capture.captured_events - capture.drained_events
            : 0;
    const auto outcome_backlog =
        outcome.published_outcomes >= outcome.drained_outcomes
            ? outcome.published_outcomes - outcome.drained_outcomes
            : 0;
    const auto voice_state_backlog =
        voice_state.published_voice_states >= voice_state.drained_voice_states
            ? voice_state.published_voice_states -
                  voice_state.drained_voice_states
            : 0;
    if (admitted_count - realtime.completed_voices < kMaxInFlightVoices &&
        capture_backlog < kMaxCaptureBacklog &&
        outcome_backlog < kMaxOutcomeBacklog &&
        voice_state_backlog < kMaxVoiceStateBacklog) {
      const auto sequence = admitted_count * 3 + 7;
      if (engine.enqueue_control(lmdj::audio::PadControlEvent{
              sequence,
              0,
              100,
              lmdj::audio::PadControlKind::press,
              {},
          }) ==
          lmdj::audio::EnqueueResult::accepted) {
        admitted.at(admitted_count) = sequence;
        ++admitted_count;
        made_progress = true;
      }
    }

    const auto capture_capacity =
        std::min<std::size_t>(64, captured.size() - captured_count);
    if (capture_capacity != 0) {
      const auto drained = engine.drain_capture(
          std::span<lmdj::audio::CapturedTriggerEvent>(
              captured.data() + captured_count,
              capture_capacity));
      captured_count += drained;
      made_progress = made_progress || drained != 0;
    }
    const auto outcome_capacity =
        std::min<std::size_t>(64, outcomes.size() - outcome_count);
    if (outcome_capacity != 0) {
      const auto drained = engine.drain_trigger_outcomes(
          std::span<lmdj::audio::RuntimeTriggerOutcomeEvent>(
              outcomes.data() + outcome_count,
              outcome_capacity));
      outcome_count += drained;
      made_progress = made_progress || drained != 0;
    }
    const auto voice_state_capacity =
        std::min<std::size_t>(128, voice_states.size() - voice_state_count);
    if (voice_state_capacity != 0) {
      const auto drained = engine.drain_voice_states(
          std::span<lmdj::audio::RuntimeVoiceStateEvent>(
              voice_states.data() + voice_state_count,
              voice_state_capacity));
      voice_state_count += drained;
      made_progress = made_progress || drained != 0;
    }
    if (!made_progress) {
      std::this_thread::yield();
    }
  }

  while (engine.telemetry().completed_voices < kEvents) {
    const auto captured_now = engine.drain_capture(
        std::span<lmdj::audio::CapturedTriggerEvent>(
            captured.data() + captured_count,
            std::min<std::size_t>(
                64, captured.size() - captured_count)));
    const auto outcomes_now = engine.drain_trigger_outcomes(
        std::span<lmdj::audio::RuntimeTriggerOutcomeEvent>(
            outcomes.data() + outcome_count,
            std::min<std::size_t>(
                64, outcomes.size() - outcome_count)));
    const auto voice_states_now = engine.drain_voice_states(
        std::span<lmdj::audio::RuntimeVoiceStateEvent>(
            voice_states.data() + voice_state_count,
            std::min<std::size_t>(
                128, voice_states.size() - voice_state_count)));
    captured_count += captured_now;
    outcome_count += outcomes_now;
    voice_state_count += voice_states_now;
    if (captured_now == 0 && outcomes_now == 0 && voice_states_now == 0) {
      std::this_thread::yield();
    }
  }

  render_done.store(true, std::memory_order_release);
  renderer.join();
  LMDJ_CHECK(engine.disarm_capture().has_value());
  engine.stop();

  while (captured_count < captured.size() ||
         outcome_count < outcomes.size() ||
         voice_state_count < voice_states.size()) {
    const auto captured_now = engine.drain_capture(
        std::span<lmdj::audio::CapturedTriggerEvent>(
            captured.data() + captured_count,
            std::min<std::size_t>(
                64, captured.size() - captured_count)));
    const auto outcomes_now = engine.drain_trigger_outcomes(
        std::span<lmdj::audio::RuntimeTriggerOutcomeEvent>(
            outcomes.data() + outcome_count,
            std::min<std::size_t>(
                64, outcomes.size() - outcome_count)));
    const auto voice_states_now = engine.drain_voice_states(
        std::span<lmdj::audio::RuntimeVoiceStateEvent>(
            voice_states.data() + voice_state_count,
            std::min<std::size_t>(
                128, voice_states.size() - voice_state_count)));
    captured_count += captured_now;
    outcome_count += outcomes_now;
    voice_state_count += voice_states_now;
    if (captured_now == 0 && outcomes_now == 0 && voice_states_now == 0) {
      break;
    }
  }

  LMDJ_CHECK(captured_count == captured.size());
  LMDJ_CHECK(outcome_count == outcomes.size());
  LMDJ_CHECK(voice_state_count == voice_states.size());
  for (std::uint64_t sequence = 0; sequence < kEvents; ++sequence) {
    LMDJ_CHECK(captured.at(sequence).sequence == admitted.at(sequence));
    LMDJ_CHECK(outcomes.at(sequence).sequence == admitted.at(sequence));
    LMDJ_CHECK(
        outcomes.at(sequence).outcome ==
        lmdj::audio::RuntimeTriggerOutcome::voice_started);
    LMDJ_CHECK(outcomes.at(sequence).runtime_frame ==
               capture_origin + captured.at(sequence).frame_offset);
    const auto& started = voice_states.at(sequence * 2);
    const auto& completed = voice_states.at(sequence * 2 + 1);
    LMDJ_CHECK(started.sequence == admitted.at(sequence));
    LMDJ_CHECK(started.slot == 0);
    LMDJ_CHECK(started.state == lmdj::audio::RuntimeVoiceState::started);
    LMDJ_CHECK(started.runtime_frame ==
               capture_origin + captured.at(sequence).frame_offset);
    LMDJ_CHECK(started.source_frame == 0);
    LMDJ_CHECK(completed.sequence == admitted.at(sequence));
    LMDJ_CHECK(completed.slot == 0);
    LMDJ_CHECK(completed.state == lmdj::audio::RuntimeVoiceState::completed);
    LMDJ_CHECK(completed.runtime_frame == started.runtime_frame + 1);
    LMDJ_CHECK(completed.source_frame == 1);
  }
  const auto realtime = engine.telemetry();
  const auto capture = engine.capture_telemetry();
  const auto outcome = engine.trigger_outcome_telemetry();
  const auto voice_state = engine.voice_state_telemetry();
  LMDJ_CHECK(realtime.enqueued_events == kEvents);
  LMDJ_CHECK(realtime.dequeued_events == kEvents);
  LMDJ_CHECK(realtime.started_voices == kEvents);
  LMDJ_CHECK(realtime.completed_voices == kEvents);
  LMDJ_CHECK(realtime.queue_drops == 0);
  LMDJ_CHECK(realtime.voice_drops == 0);
  LMDJ_CHECK(
      realtime.dequeued_events ==
      outcome.published_outcomes + outcome.runtime_outcome_drops);
  LMDJ_CHECK(realtime.started_voices + realtime.voice_drops ==
             realtime.dequeued_events);
  LMDJ_CHECK(outcome.published_outcomes == kEvents);
  LMDJ_CHECK(outcome.drained_outcomes == kEvents);
  LMDJ_CHECK(outcome.runtime_outcome_drops == 0);
  LMDJ_CHECK(voice_state.published_voice_states == kEvents * 2);
  LMDJ_CHECK(voice_state.drained_voice_states == kEvents * 2);
  LMDJ_CHECK(voice_state.voice_state_drops == 0);
  LMDJ_CHECK(capture.state == lmdj::audio::CaptureState::idle);
  LMDJ_CHECK(capture.captured_events == kEvents);
  LMDJ_CHECK(capture.drained_events == kEvents);
  LMDJ_CHECK(capture.capture_drops == 0);
}

void corrupted_voice_state_stream_never_returns_a_partial_drain() {
  std::atomic<lmdj::audio::RuntimeVoiceStateStreamState> state{
      lmdj::audio::RuntimeVoiceStateStreamState::healthy};
  std::array<lmdj::audio::RuntimeVoiceStateEvent, 2> output{};
  std::size_t pops = 0;
  const auto drained = lmdj::audio::detail::drain_voice_states_fail_closed(
      state,
      output,
      [&](lmdj::audio::RuntimeVoiceStateEvent& event) noexcept {
        if (pops != 0) {
          return false;
        }
        event = lmdj::audio::RuntimeVoiceStateEvent{
            71,
            3,
            lmdj::audio::RuntimeVoiceState::started,
            11,
            5,
        };
        ++pops;
        state.store(
            lmdj::audio::RuntimeVoiceStateStreamState::corrupted,
            std::memory_order_release);
        return true;
      });

  LMDJ_CHECK(pops == 1);
  LMDJ_CHECK(output.at(0).sequence == 71);
  LMDJ_CHECK(drained == 0);
}

}  // namespace

void* operator new(std::size_t bytes) { return ordinary_allocate(bytes); }
void* operator new[](std::size_t bytes) { return ordinary_allocate(bytes); }
void* operator new(std::size_t bytes, std::align_val_t alignment) {
  return aligned_allocate(bytes, static_cast<std::size_t>(alignment));
}
void* operator new[](std::size_t bytes, std::align_val_t alignment) {
  return aligned_allocate(bytes, static_cast<std::size_t>(alignment));
}
void operator delete(void* p) noexcept { release_allocation(p); }
void operator delete[](void* p) noexcept { release_allocation(p); }
void operator delete(void* p, std::size_t) noexcept { release_allocation(p); }
void operator delete[](void* p, std::size_t) noexcept { release_allocation(p); }
void operator delete(void* p, std::align_val_t) noexcept { release_allocation(p); }
void operator delete[](void* p, std::align_val_t) noexcept { release_allocation(p); }
void operator delete(void* p, std::size_t, std::align_val_t) noexcept { release_allocation(p); }
void operator delete[](void* p, std::size_t, std::align_val_t) noexcept { release_allocation(p); }

int main() {
  pattern_transport_receipts_race_publication_and_reclaim();
  pcm_audition_replacement_keeps_both_owners_until_audio_release();
  pcm_publication_retirement_races_real_render_without_owner_destruction();
  preserves_compact_voice_states_under_spsc_contention();
  preserves_all_trigger_events_under_spsc_contention();
  transports_all_voice_starts_to_concurrent_bounded_drains();
  corrupted_voice_state_stream_never_returns_a_partial_drain();
}
