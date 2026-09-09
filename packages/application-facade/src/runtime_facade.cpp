#include <lmdj/facade/runtime_facade.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <new>
#include <thread>
#include <utility>
#include <vector>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/cooker/runtime_content.hpp>

namespace lmdj::facade {

struct RuntimeFacade::Impl {
  explicit Impl(RuntimeConfig supplied) : config(supplied) {}
  struct Pending {
    std::uint32_t sequence{};
    RuntimeCommandOutcome outcome{RuntimeCommandOutcome::applied};
  };
  RuntimeConfig config;
  RuntimePhase phase{RuntimePhase::empty};
  RuntimeBudget budget;
  std::optional<RuntimeContentIdentity> identity;
  std::unique_ptr<audio::RealtimeEngine> engine;
  std::shared_ptr<const cooker::RuntimeSnapshot> snapshot;
  RuntimeEpoch epoch;
  std::uint32_t epoch_count{};
  std::uint32_t accepted{};
  std::uint32_t pending_begin{};
  std::uint32_t pending_count{};
  std::array<Pending, audio::kRealtimeQueueCapacity> pending{};
  // OPEN and BUSY share one atomic so close cannot miss a callback between
  // its admission check and its active-count increment. CAS rejects reentry.
  static constexpr std::uint32_t open = 1;
  static constexpr std::uint32_t busy = 2;
  std::atomic<std::uint32_t> gate{};
  std::atomic<std::uint32_t> consumed{};
  static_assert(std::atomic<std::uint32_t>::is_always_lock_free);

  bool valid_config() const noexcept {
    const auto& limits = config.content_limits;
    return config.maximum_pending_commands > 0 &&
           config.maximum_pending_commands <= pending.size() &&
           config.maximum_epoch > 0 && config.maximum_sequence > 0 &&
           config.maximum_admitted_bytes > 0 &&
           config.platform_reserve_bytes > 0 &&
           limits.maximum_encoded_bytes > 0 && limits.maximum_pcm_bytes > 0 &&
           limits.maximum_sample_frames > 0 && limits.maximum_pads > 0 &&
           limits.maximum_pads <= 64 && limits.maximum_events > 0;
  }

  void drain_events() noexcept {
    if (!engine) return;
    std::array<audio::RuntimeTriggerOutcomeEvent, 64> outcomes{};
    std::size_t count;
    do {
      count = engine->drain_trigger_outcomes(outcomes);
      for (std::size_t index = 0; index < count; ++index) {
        const auto& event = outcomes[index];
        for (std::uint32_t offset = 0; offset < pending_count; ++offset) {
          auto& item = pending[(pending_begin + offset) % pending.size()];
          if (item.sequence == event.sequence) {
            item.outcome = event.outcome == audio::RuntimeTriggerOutcome::voice_started
                               ? RuntimeCommandOutcome::voice_started
                               : RuntimeCommandOutcome::voice_capacity;
            break;
          }
        }
      }
    } while (count == outcomes.size());
    std::array<audio::RuntimeVoiceStateEvent, 64> voices{};
    while (engine->drain_voice_states(voices) == voices.size()) {}
  }
};

RuntimeFacade::RuntimeFacade(RuntimeConfig config)
    : impl_(std::make_unique<Impl>(config)) {}
RuntimeFacade::~RuntimeFacade() { stop(); }

RuntimeResult RuntimeFacade::load(std::span<const std::byte> bytes,
                                 const RuntimeContentIdentity& identity) noexcept {
  auto& self = *impl_;
  if (self.phase != RuntimePhase::empty) return RuntimeResult::wrong_state;
  if (!self.valid_config()) return RuntimeResult::invalid_config;
  self.budget = {};
  try {
    const auto inspected = cooker::inspect_runtime_content(
        bytes, identity, self.config.content_limits);
    if (!inspected.has_value()) {
      return inspected.error().code == foundation::ErrorCode::internal_error
                 ? RuntimeResult::allocation_failed : RuntimeResult::invalid_content;
    }
    const auto& footprint = inspected.value();
    RuntimeBudget budget;
    budget.fixed_bytes = sizeof(RuntimeFacade) + sizeof(Impl) +
                         sizeof(audio::RealtimeEngine) +
                         audio::RealtimeEngine::receipt_bounded_voice_state_storage_bytes();
    budget.encoded_bytes = footprint.encoded_bytes;
    budget.pcm_bytes = footprint.pcm_bytes;
    budget.prepared_float_bytes = footprint.prepared_float_bytes;
    // Payload accounting; allocator/control-block overhead and capacity
    // rounding belong to the explicit platform reserve, not hidden constants.
    budget.metadata_bytes = sizeof(cooker::RuntimeSnapshot) +
        static_cast<std::uint64_t>(footprint.samples) * sizeof(cooker::PcmSample) +
        static_cast<std::uint64_t>(footprint.pads) *
            (sizeof(cooker::ResolvedPad) + sizeof(std::shared_ptr<const cooker::PcmSample>) +
             65 + cooker::kRuntimePcmMediaType.size() + 1) +
        static_cast<std::uint64_t>(footprint.events) *
            (sizeof(cooker::ResolvedEvent) + sizeof(audio::PreparedPatternEvent)) +
        6 * 37 + 65 + sizeof(std::uint32_t);
    budget.preparation_workspace_bytes = footprint.largest_float_sample_bytes +
        static_cast<std::uint64_t>(footprint.events) * sizeof(domain::PatternEvent) +
        sizeof(audio::PreparedSampleBank) + sizeof(audio::PreparedPatternView);
    budget.platform_reserve_bytes = self.config.platform_reserve_bytes;
    for (const auto item : {budget.fixed_bytes, budget.encoded_bytes,
                           budget.pcm_bytes, budget.prepared_float_bytes,
                           budget.metadata_bytes, budget.preparation_workspace_bytes,
                           budget.platform_reserve_bytes}) {
      const auto sum = audio::checked_runtime_byte_sum(budget.admitted_bytes, item);
      if (!sum) return RuntimeResult::budget_exceeded;
      budget.admitted_bytes = *sum;
    }
    self.budget = budget;
    if (budget.admitted_bytes > self.config.maximum_admitted_bytes) {
      return RuntimeResult::budget_exceeded;
    }
    // Reserve large fixed blocks before variable decoded/prepared storage can
    // fragment a bounded platform heap. Keep the candidate local: any later
    // failure still destroys it and leaves the Facade empty and retryable.
    auto engine = std::make_unique<audio::RealtimeEngine>(
        audio::RealtimeEngine::ReceiptBoundedVoiceStates{});
    auto decoded = cooker::decode_runtime_content(bytes, identity, self.config.content_limits);
    if (!decoded.has_value()) {
      return decoded.error().code == foundation::ErrorCode::internal_error
                 ? RuntimeResult::allocation_failed : RuntimeResult::invalid_content;
    }
    auto snapshot = std::move(decoded.value());
    auto bank = audio::PreparedSampleBank::empty(snapshot->project_id,
                                                snapshot->project_revision);
    // The complete decoder already validated Pad order, PCM, playback and
    // identity. Avoid the desktop quota-diagnostic JSON workspace here.
    for (const auto& pad : snapshot->pads) {
      const auto& sample = *pad.sample;
      const auto frames = sample.interleaved.size() / sample.channels;
      std::vector<float> mono(frames);
      const audio::PreparedSampleMaterialView material{
          sample.interleaved.data(), static_cast<std::uint32_t>(frames), sample.channels};
      for (std::uint32_t frame = 0; frame < frames; ++frame) {
        mono[frame] = audio::prepared_material_sample(material, frame);
      }
      if (!bank.set_sample(static_cast<std::uint8_t>(pad.slot.bank * 16 + pad.slot.pad),
                           mono, pad.playback).has_value()) {
        return RuntimeResult::preparation_failed;
      }
    }
    auto pattern = audio::PreparedPatternView::from_canonical_snapshot(*snapshot);
    if (!pattern.has_value()) return RuntimeResult::preparation_failed;
    if (engine->publish_sample_bank(std::move(bank)) != audio::PublishResult::accepted ||
        engine->publish_pattern_view(std::move(pattern.value())).result !=
            audio::PatternPublishResult::accepted) {
      return RuntimeResult::preparation_failed;
    }
    // Copy before committing any candidate ownership: even identity storage
    // failure must leave the Facade empty rather than partly ready.
    auto confirmed_identity = identity;
    self.identity = std::move(confirmed_identity);
    self.snapshot = std::move(snapshot);
    self.engine = std::move(engine);
    self.phase = RuntimePhase::ready;
    return RuntimeResult::ok;
  } catch (const std::bad_alloc&) {
    return RuntimeResult::allocation_failed;
  } catch (...) {
    return RuntimeResult::preparation_failed;
  }
}

RuntimeResult RuntimeFacade::start(RuntimeEpoch& epoch) noexcept {
  auto& self = *impl_;
  if ((self.phase != RuntimePhase::ready && self.phase != RuntimePhase::stopped) ||
      self.pending_count != 0) return RuntimeResult::wrong_state;
  if (self.epoch_count == self.config.maximum_epoch) return RuntimeResult::epoch_exhausted;
  try {
    RuntimeEpoch next;
    next.token_ = std::make_shared<const std::uint32_t>(self.epoch_count + 1);
    if (!self.engine->start().has_value()) return RuntimeResult::preparation_failed;
    ++self.epoch_count;
    self.epoch = next;
    epoch = next;
    self.accepted = 0;
    self.pending_begin = 0;
    self.consumed.store(0, std::memory_order_relaxed);
    self.phase = RuntimePhase::running;
    self.gate.store(Impl::open, std::memory_order_release);
    return RuntimeResult::ok;
  } catch (...) {
    return RuntimeResult::allocation_failed;
  }
}

RuntimeResult RuntimeFacade::submit(const RuntimeCommand& command) noexcept {
  auto& self = *impl_;
  if (self.phase != RuntimePhase::running) return RuntimeResult::wrong_state;
  if (command.epoch != self.epoch) return RuntimeResult::stale_epoch;
  if (self.accepted == self.config.maximum_sequence) return RuntimeResult::sequence_exhausted;
  if (command.sequence <= self.accepted) return RuntimeResult::duplicate_sequence;
  if (command.sequence != self.accepted + 1) return RuntimeResult::out_of_order;
  audio::PadControlKind kind;
  switch (command.kind) {
    case RuntimeCommandKind::press: kind = audio::PadControlKind::press; break;
    case RuntimeCommandKind::release: kind = audio::PadControlKind::release; break;
    case RuntimeCommandKind::stop_slot: kind = audio::PadControlKind::stop_slot; break;
    case RuntimeCommandKind::stop_all: kind = audio::PadControlKind::stop_all; break;
    default: return RuntimeResult::invalid_command;
  }
  if (self.pending_count == self.config.maximum_pending_commands) return RuntimeResult::queue_full;
  const auto result = self.engine->enqueue_control({
      command.sequence, command.slot, command.velocity, kind, {}});
  if (result != audio::EnqueueResult::accepted) {
    return result == audio::EnqueueResult::queue_full
               ? RuntimeResult::queue_full : RuntimeResult::invalid_command;
  }
  self.pending[(self.pending_begin + self.pending_count) % self.pending.size()] =
      {command.sequence, RuntimeCommandOutcome::applied};
  ++self.pending_count;
  self.accepted = command.sequence;
  return RuntimeResult::accepted;
}

std::size_t RuntimeFacade::poll(std::span<RuntimeReceipt> receipts) noexcept {
  auto& self = *impl_;
  // Capacity proof: acquire completed render before draining its state edges;
  // retire pending slots only afterward. Moving this load after drain could
  // acknowledge a start whose edge is still queued and invalidate 2*N + Voices.
  const auto consumed = self.consumed.load(std::memory_order_acquire);
  self.drain_events();
  std::size_t count = 0;
  while (count < receipts.size() && self.pending_count != 0) {
    const auto& item = self.pending[self.pending_begin];
    if (item.sequence > consumed && item.outcome != RuntimeCommandOutcome::cancelled) break;
    receipts[count++] = {self.epoch, item.sequence, item.outcome};
    self.pending_begin = (self.pending_begin + 1) % self.pending.size();
    --self.pending_count;
  }
  return count;
}

void RuntimeFacade::request_stop() noexcept {
  auto& self = *impl_;
  if (self.phase != RuntimePhase::running) return;
  self.gate.fetch_and(~Impl::open, std::memory_order_acq_rel);
  self.phase = RuntimePhase::draining;
}

RuntimeResult RuntimeFacade::finish_stop() noexcept {
  auto& self = *impl_;
  if (self.phase != RuntimePhase::draining) return RuntimeResult::wrong_state;
  if (self.gate.load(std::memory_order_acquire) != 0) return RuntimeResult::draining;
  self.drain_events();
  const auto consumed = self.consumed.load(std::memory_order_acquire);
  for (std::uint32_t offset = 0; offset < self.pending_count; ++offset) {
    auto& item = self.pending[(self.pending_begin + offset) % self.pending.size()];
    if (item.sequence > consumed) item.outcome = RuntimeCommandOutcome::cancelled;
  }
  self.engine->stop();
  self.phase = RuntimePhase::stopped;
  return RuntimeResult::ok;
}

void RuntimeFacade::stop() noexcept {
  request_stop();
  while (finish_stop() == RuntimeResult::draining) std::this_thread::yield();
}

RuntimeResult RuntimeFacade::unload() noexcept {
  auto& self = *impl_;
  if (self.phase == RuntimePhase::running || self.phase == RuntimePhase::draining) {
    return RuntimeResult::wrong_state;
  }
  self.engine.reset();
  self.snapshot.reset();
  self.identity.reset();
  self.budget = {};
  self.phase = RuntimePhase::empty;
  return RuntimeResult::ok;
}

void RuntimeFacade::reset() noexcept { stop(); (void)unload(); }
RuntimePhase RuntimeFacade::phase() const noexcept { return impl_->phase; }
RuntimeBudget RuntimeFacade::budget() const noexcept { return impl_->budget; }
std::optional<RuntimeContentIdentity> RuntimeFacade::content_identity() const {
  return impl_->identity;
}

void RuntimeFacade::render(float* left, float* right, std::uint32_t frames) noexcept {
  if (left == nullptr || right == nullptr) return;
  auto& self = *impl_;
  auto expected = Impl::open;
  if (!self.gate.compare_exchange_strong(expected, Impl::open | Impl::busy,
                                         std::memory_order_acquire,
                                         std::memory_order_relaxed)) {
    std::fill_n(left, frames, 0.0F);
    std::fill_n(right, frames, 0.0F);
    return;
  }
  self.engine->render(left, right, frames);
  self.consumed.store(static_cast<std::uint32_t>(self.engine->consumed_controls_audio()),
                      std::memory_order_release);
  self.gate.fetch_and(~Impl::busy, std::memory_order_release);
}

}  // namespace lmdj::facade
