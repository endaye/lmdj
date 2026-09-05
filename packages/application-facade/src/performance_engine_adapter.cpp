#include <algorithm>
#include <cmath>
#include <deque>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/performance_engine_adapter.hpp>

namespace lmdj::facade {
namespace {

constexpr std::uint64_t kBarTicks = domain::kBarTicks4x4;

foundation::Error adapter_error(foundation::ErrorCode code,
                                std::string message) {
  return foundation::Error{code, std::move(message)};
}

foundation::Error enqueue_error(std::string message) {
  return adapter_error(foundation::ErrorCode::internal_error,
                       std::move(message));
}

std::string_view fx_enqueue_reason(audio::FxEnqueueResult result) noexcept {
  switch (result) {
    case audio::FxEnqueueResult::accepted:
      return "accepted";
    case audio::FxEnqueueResult::invalid_fx:
      return "the effect is outside the Contract chain";
    case audio::FxEnqueueResult::invalid_value:
      return "the value is outside the 0-1000 scale";
    case audio::FxEnqueueResult::invalid_bpm:
      return "the prepared tempo is invalid";
    case audio::FxEnqueueResult::not_prepared:
      return "the master FX chain is not prepared for the current tempo";
    case audio::FxEnqueueResult::not_running:
      return "the engine is not running";
    case audio::FxEnqueueResult::queue_full:
      return "the master FX gesture queue is full";
  }
  return "the master bus refused the gesture";
}

bool valid_trigger_mode(domain::TriggerMode mode) noexcept {
  switch (mode) {
    case domain::TriggerMode::one_shot:
    case domain::TriggerMode::gate:
    case domain::TriggerMode::loop_gate:
    case domain::TriggerMode::loop_toggle:
      return true;
  }
  return false;
}

bool valid_playback(const cooker::ResolvedPlayback& playback,
                    std::uint32_t frame_count) noexcept {
  return playback.start_frame < playback.end_frame &&
         playback.end_frame <= frame_count &&
         valid_trigger_mode(playback.trigger_mode) &&
         std::isfinite(playback.linear_gain) && playback.linear_gain >= 0.0F;
}

class EnginePerformanceClock final : public PerformanceClock {
 public:
  explicit EnginePerformanceClock(audio::RealtimeEngine& engine)
      : engine_(engine) {}

  void anchor(std::uint16_t bpm, std::uint64_t at_tick) override {
    std::lock_guard lock(mutex_);
    const auto telemetry = engine_.telemetry();
    const auto current_numerator =
        anchored_ ? observe_numerator_locked(
                        telemetry.start_epoch, telemetry.rendered_frames)
                  : foundation::Result<std::uint64_t>::success(0);
    if (!current_numerator.has_value() || bpm < 40 || bpm > 240) {
      anchor_valid_ = false;
      anchored_ = true;
      return;
    }
    const auto monotone_tick = std::max(at_tick, last_tick_);
    if (monotone_tick > std::numeric_limits<std::uint64_t>::max() /
                            audio::kTickDenominator) {
      anchor_valid_ = false;
      last_tick_ = monotone_tick;
      anchored_ = true;
      return;
    }
    const auto monotone_numerator =
        monotone_tick * audio::kTickDenominator;
    const auto anchor_numerator =
        std::max(monotone_numerator, current_numerator.value());
    anchor_ = audio::TransportAnchor{
        telemetry.rendered_frames, anchor_numerator, bpm};
    last_observed_epoch_ = telemetry.start_epoch;
    last_numerator_ = anchor_numerator;
    last_tick_ = std::max(last_tick_, audio::whole_tick(anchor_numerator));
    anchor_valid_ = true;
    anchored_ = true;
  }

  foundation::Result<std::uint64_t> read_tick() override {
    std::lock_guard lock(mutex_);
    if (!anchored_) {
      return foundation::Result<std::uint64_t>::success(last_tick_);
    }
    const auto telemetry = engine_.telemetry();
    const auto numerator = observe_numerator_locked(
        telemetry.start_epoch, telemetry.rendered_frames);
    if (!numerator.has_value()) {
      return foundation::Result<std::uint64_t>::failure(numerator.error());
    }
    last_tick_ = std::max(last_tick_, audio::whole_tick(numerator.value()));
    return foundation::Result<std::uint64_t>::success(last_tick_);
  }

  foundation::Result<std::uint64_t> frame_at_tick(std::uint64_t tick) {
    std::lock_guard lock(mutex_);
    if (!anchored_ || !anchor_valid_ || anchor_.bpm < 40 ||
        anchor_.bpm > 240 ||
        tick > std::numeric_limits<std::uint64_t>::max() /
                   audio::kTickDenominator) {
      return foundation::Result<std::uint64_t>::failure(
          adapter_error(foundation::ErrorCode::invalid_argument,
                        "Performance engine clock is not anchored"));
    }
    const auto telemetry = engine_.telemetry();
    const auto observed = observe_numerator_locked(
        telemetry.start_epoch, telemetry.rendered_frames);
    if (!observed.has_value()) {
      return foundation::Result<std::uint64_t>::failure(observed.error());
    }
    last_tick_ = std::max(last_tick_, audio::whole_tick(observed.value()));
    const auto target_numerator = tick * audio::kTickDenominator;
    if (target_numerator <= anchor_.tick_numerator) {
      return foundation::Result<std::uint64_t>::success(
          anchor_.runtime_frame);
    }
    const auto delta_numerator = target_numerator - anchor_.tick_numerator;
    const auto rate = static_cast<std::uint64_t>(anchor_.bpm) *
                      audio::kTransportPpq;
    const auto delta_frame =
        delta_numerator / rate + (delta_numerator % rate == 0 ? 0U : 1U);
    if (delta_frame > std::numeric_limits<std::uint64_t>::max() -
                          anchor_.runtime_frame) {
      return foundation::Result<std::uint64_t>::failure(
          adapter_error(foundation::ErrorCode::invalid_argument,
                        "Performance launch frame overflowed"));
    }
    return foundation::Result<std::uint64_t>::success(
        anchor_.runtime_frame + delta_frame);
  }

  void service() {
    std::lock_guard lock(mutex_);
    if (!anchored_) {
      return;
    }
    const auto telemetry = engine_.telemetry();
    const auto observed = observe_numerator_locked(
        telemetry.start_epoch, telemetry.rendered_frames);
    if (observed.has_value()) {
      last_tick_ =
          std::max(last_tick_, audio::whole_tick(observed.value()));
    }
  }

 private:
  foundation::Result<std::uint64_t> observe_numerator_locked(
      std::uint64_t start_epoch,
      std::uint64_t frame) {
    if (!anchored_ || !anchor_valid_) {
      return foundation::Result<std::uint64_t>::failure(
          adapter_error(foundation::ErrorCode::invalid_argument,
                        "Performance engine clock anchor is invalid"));
    }
    if (start_epoch != last_observed_epoch_) {
      anchor_ = audio::TransportAnchor{0, last_numerator_, anchor_.bpm};
    }
    auto numerator = audio::tick_numerator_at(anchor_, frame);
    if (!numerator.has_value()) {
      anchor_valid_ = false;
      return numerator;
    }
    last_observed_epoch_ = start_epoch;
    last_numerator_ = numerator.value();
    return numerator;
  }

  audio::RealtimeEngine& engine_;
  mutable std::mutex mutex_;
  audio::TransportAnchor anchor_{};
  std::uint64_t last_observed_epoch_{};
  std::uint64_t last_numerator_{};
  std::uint64_t last_tick_{};
  bool anchor_valid_{};
  bool anchored_{};
};

class EnginePerformanceInputSequencer final : public PerformanceInputSequencer {
 public:
  void seed(std::uint64_t last_input_sequence) override {
    std::lock_guard lock(mutex_);
    next_ = std::max(next_, last_input_sequence);
  }

  foundation::Result<std::uint64_t> next() override {
    std::lock_guard lock(mutex_);
    if (next_ == std::numeric_limits<std::uint64_t>::max()) {
      return foundation::Result<std::uint64_t>::failure(
          adapter_error(foundation::ErrorCode::internal_error,
                        "Performance input sequence is exhausted"));
    }
    return foundation::Result<std::uint64_t>::success(++next_);
  }

 private:
  std::mutex mutex_;
  std::uint64_t next_{};
};

class EnginePatternLaunchAcknowledger final : public PatternLaunchAcknowledger {
 public:
  EnginePatternLaunchAcknowledger(
      audio::RealtimeEngine& engine,
      std::shared_ptr<EnginePerformanceClock> clock,
      std::shared_ptr<PatternPublicationGateway> gateway)
      : engine_(engine),
        clock_(std::move(clock)),
        gateway_(std::move(gateway)) {}

  foundation::Result<PatternLaunchReservation> reserve(
      const foundation::SequenceSessionId& session_id,
      const foundation::CommandId& request_id, std::uint8_t pattern_slot,
      std::uint64_t earliest_target_tick,
      std::shared_ptr<const cooker::RuntimeSnapshot> resolved_pattern)
      override {
    std::lock_guard lock(mutex_);
    const auto telemetry = engine_.telemetry();
    cancel_stale_epochs(telemetry.start_epoch);
    const auto key = session_id.value();
    bool claimed = false;
    std::optional<audio::PatternReplacementAuthority> replacement;
    auto& pending_queue = pending_[key];
    if (!pending_queue.empty()) {
      auto& previous = pending_queue.back();
      if (previous.claimed) {
        claimed = true;
        replacement = previous.authority;
      } else if (previous.authority.has_value()) {
        replacement = previous.authority;
        if (gateway_->cancel(*previous.authority)) {
          outcomes_[key].push_back(PatternLaunchOutcome{
              previous.session_id,
              previous.request_id,
              previous.pattern_slot,
              previous.target_tick,
              PatternLaunchOutcomeKind::cancelled,
          });
          pending_queue.pop_back();
          replacement.reset();
        } else {
          previous.claimed = true;
          claimed = true;
        }
      } else if (telemetry.rendered_frames >= previous.activation_frame) {
        previous.claimed = true;
        claimed = true;
      } else {
        outcomes_[key].push_back(PatternLaunchOutcome{
            previous.session_id,
            previous.request_id,
            previous.pattern_slot,
            previous.target_tick,
            PatternLaunchOutcomeKind::cancelled,
        });
        pending_queue.pop_back();
      }
      if (claimed) {
        const auto next_bar =
            previous.target_tick >
                    std::numeric_limits<std::uint64_t>::max() - kBarTicks
                ? std::numeric_limits<std::uint64_t>::max()
                : previous.target_tick + kBarTicks;
        earliest_target_tick = std::max(earliest_target_tick, next_bar);
      }
    }

    const auto activation = clock_->frame_at_tick(earliest_target_tick);
    if (!activation.has_value()) {
      outcomes_[key].push_back(PatternLaunchOutcome{
          session_id,
          request_id,
          pattern_slot,
          earliest_target_tick,
          PatternLaunchOutcomeKind::failed,
      });
      return foundation::Result<PatternLaunchReservation>::failure(
          activation.error());
    }

    Pending next_pending{
        session_id,         request_id,   pattern_slot, earliest_target_tick,
        activation.value(), std::nullopt, false,        telemetry.start_epoch,
    };
    if (resolved_pattern) {
      const auto pattern_id = resolved_pattern->pattern_id;
      const auto publication = gateway_->publish(
          std::move(resolved_pattern), activation.value(), replacement);
      if (!publication.has_value()) {
        outcomes_[key].push_back(PatternLaunchOutcome{
            session_id,
            request_id,
            pattern_slot,
            earliest_target_tick,
            PatternLaunchOutcomeKind::failed,
        });
        return foundation::Result<PatternLaunchReservation>::failure(
            publication.error());
      }
      next_pending.activation_frame = publication.value().activation_frame;
      next_pending.authority = audio::PatternReplacementAuthority{
          publication.value().generation,
          pattern_id,
          publication.value().activation_frame,
      };
    }
    pending_queue.push_back(std::move(next_pending));
    return foundation::Result<PatternLaunchReservation>::success(
        {earliest_target_tick, claimed});
  }

  std::vector<PatternLaunchOutcome> peek(
      const foundation::SequenceSessionId& session_id) override {
    std::lock_guard lock(mutex_);
    const auto found = outcomes_.find(session_id.value());
    if (found == outcomes_.end()) {
      return {};
    }
    return found->second;
  }

  foundation::Result<void> commit(
      const foundation::SequenceSessionId& session_id,
      const foundation::CommandId& request_id) override {
    std::lock_guard lock(mutex_);
    const auto found = outcomes_.find(session_id.value());
    if (found == outcomes_.end() || found->second.empty() ||
        found->second.front().request_id != request_id) {
      return foundation::Result<void>::failure(adapter_error(
          foundation::ErrorCode::invalid_argument,
          "Pattern launch outcome commit rejected: request is not the "
          "ordered session front; peek and commit the front request"));
    }
    found->second.erase(found->second.begin());
    if (found->second.empty()) {
      outcomes_.erase(found);
    }
    return foundation::Result<void>::success();
  }

  void cancel(
      const foundation::SequenceSessionId& session_id) noexcept override {
    std::lock_guard lock(mutex_);
    const auto telemetry = engine_.telemetry();
    cancel_stale_epochs(telemetry.start_epoch);
    const auto key = session_id.value();
    auto found = pending_.find(key);
    if (found == pending_.end()) {
      return;
    }
    auto& queue = found->second;
    const auto rendered_frames = telemetry.rendered_frames;
    for (auto iterator = queue.begin(); iterator != queue.end();) {
      const auto cancelled =
          !iterator->claimed &&
          (iterator->authority.has_value()
               ? gateway_->cancel(*iterator->authority)
               : rendered_frames < iterator->activation_frame);
      if (!cancelled) {
        iterator->claimed = true;
        ++iterator;
        continue;
      }
      outcomes_[key].push_back(PatternLaunchOutcome{
          iterator->session_id,
          iterator->request_id,
          iterator->pattern_slot,
          iterator->target_tick,
          PatternLaunchOutcomeKind::cancelled,
      });
      iterator = queue.erase(iterator);
    }
    if (queue.empty()) {
      pending_.erase(found);
    }
  }

  void service() {
    std::lock_guard lock(mutex_);
    static_cast<void>(engine_.reclaim_retired_patterns());
    const auto telemetry = engine_.telemetry();
    cancel_stale_epochs(telemetry.start_epoch);
    const auto pattern = engine_.pattern_telemetry();
    const auto rendered_frames = telemetry.rendered_frames;
    for (auto iterator = pending_.begin(); iterator != pending_.end();) {
      auto& queue = iterator->second;
      const auto current_belongs_to_queue =
          std::any_of(queue.begin(), queue.end(), [&pattern](const auto& entry) {
            return entry.authority.has_value() &&
                   entry.authority->generation == pattern.current_generation;
          });
      bool reached_current = false;
      for (auto pending = queue.begin(); pending != queue.end();) {
        const auto crossed = rendered_frames >= pending->activation_frame;
        const auto is_current =
            pending->authority.has_value() &&
            pending->authority->generation == pattern.current_generation;
        const auto applied =
            !pending->authority.has_value()
                ? crossed
                : crossed &&
                      (is_current ||
                       (current_belongs_to_queue && !reached_current &&
                        pending->claimed));
        reached_current = reached_current || is_current;
        if (applied) {
          outcomes_[iterator->first].push_back(PatternLaunchOutcome{
              pending->session_id,
              pending->request_id,
              pending->pattern_slot,
              pending->target_tick,
              PatternLaunchOutcomeKind::applied,
          });
          pending = queue.erase(pending);
          continue;
        }
        const auto no_longer_pending =
            !pending->claimed && pending->authority.has_value() && crossed &&
            pattern.pending_generation != pending->authority->generation;
        if (no_longer_pending) {
          outcomes_[iterator->first].push_back(PatternLaunchOutcome{
              pending->session_id,
              pending->request_id,
              pending->pattern_slot,
              pending->target_tick,
              PatternLaunchOutcomeKind::cancelled,
          });
          pending = queue.erase(pending);
          continue;
        }
        ++pending;
      }
      if (queue.empty()) {
        iterator = pending_.erase(iterator);
      } else {
        ++iterator;
      }
    }
  }

 private:
  struct Pending {
    foundation::SequenceSessionId session_id;
    foundation::CommandId request_id;
    std::uint8_t pattern_slot{};
    std::uint64_t target_tick{};
    std::uint64_t activation_frame{};
    std::optional<audio::PatternReplacementAuthority> authority;
    bool claimed{};
    std::uint64_t start_epoch{};
  };

  void cancel_stale_epochs(std::uint64_t current_epoch) {
    for (auto pending_session = pending_.begin();
         pending_session != pending_.end();) {
      auto& queue = pending_session->second;
      for (auto pending = queue.begin(); pending != queue.end();) {
        if (pending->start_epoch == current_epoch) {
          ++pending;
          continue;
        }
        outcomes_[pending_session->first].push_back(PatternLaunchOutcome{
            pending->session_id,
            pending->request_id,
            pending->pattern_slot,
            pending->target_tick,
            PatternLaunchOutcomeKind::cancelled,
        });
        pending = queue.erase(pending);
      }
      if (queue.empty()) {
        pending_session = pending_.erase(pending_session);
      } else {
        ++pending_session;
      }
    }
  }

  audio::RealtimeEngine& engine_;
  std::shared_ptr<EnginePerformanceClock> clock_;
  std::shared_ptr<PatternPublicationGateway> gateway_;
  std::mutex mutex_;
  std::map<std::string, std::deque<Pending>> pending_;
  std::map<std::string, std::vector<PatternLaunchOutcome>> outcomes_;
};

class EnginePerformanceReplaySink final : public PerformanceReplayRuntimeSink {
 public:
  EnginePerformanceReplaySink(
      audio::RealtimeEngine& engine,
      std::shared_ptr<PatternPublicationGateway> gateway)
      : engine_(engine), gateway_(std::move(gateway)) {}

  void set_bpm(std::uint16_t bpm) noexcept { bpm_ = bpm; }

  foundation::Result<void> apply_pad_hit(const cooker::ResolvedPad& pad,
                                         std::uint64_t duration_tick,
                                         std::uint8_t velocity) override {
    if (!domain::is_valid_slot(pad.slot) || !pad.sample ||
        pad.sample->sample_rate != audio::kRealtimeSampleRate ||
        (pad.sample->channels != 1 && pad.sample->channels != 2) ||
        pad.sample->interleaved.empty() ||
        pad.sample->interleaved.size() % pad.sample->channels != 0) {
      return foundation::Result<void>::failure(
          enqueue_error("Performance replay Pad material is invalid"));
    }
    const auto frame_count =
        pad.sample->interleaved.size() / pad.sample->channels;
    if (frame_count > std::numeric_limits<std::uint32_t>::max() ||
        !valid_playback(pad.playback,
                        static_cast<std::uint32_t>(frame_count))) {
      return foundation::Result<void>::failure(
          enqueue_error("Performance replay Pad playback is invalid"));
    }
    const auto duration_frames =
        audio::tick_boundary_frame(duration_tick, bpm_);
    if (!duration_frames.has_value() || duration_frames.value() == 0) {
      return foundation::Result<void>::failure(
          enqueue_error("Performance replay Pad duration is invalid"));
    }
    if (std::none_of(material_owners_.begin(), material_owners_.end(),
                     [&pad](const auto& owner) {
                       return owner.get() == pad.sample.get();
                     })) {
      material_owners_.push_back(pad.sample);
    }
    const auto slot =
        static_cast<std::uint8_t>(pad.slot.bank * 16U + pad.slot.pad);
    const auto enqueued = engine_.enqueue_control(audio::PadControlEvent{
        0,
        slot,
        velocity,
        audio::PadControlKind::press,
        pad.playback,
        audio::PadControlOrigin::performance_replay,
        duration_frames.value(),
        audio::PreparedSampleMaterialView{
            pad.sample->interleaved.data(),
            static_cast<std::uint32_t>(frame_count),
            pad.sample->channels,
        },
    });
    if (enqueued != audio::EnqueueResult::accepted) {
      return foundation::Result<void>::failure(
          enqueue_error("Performance replay Pad hit was rejected"));
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> apply_pattern_launch(
      std::shared_ptr<const cooker::RuntimeSnapshot> pattern) override {
    const auto publication = gateway_->publish_immediate(std::move(pattern));
    if (!publication.has_value()) {
      return foundation::Result<void>::failure(publication.error());
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> apply_fx_gesture(audio::FxGesture gesture) override {
    if (engine_.enqueue_fx_gesture(gesture) !=
        audio::FxEnqueueResult::accepted) {
      return foundation::Result<void>::failure(
          enqueue_error("Performance replay FX gesture was rejected"));
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<NeutralResetProgress> reset_neutral() override {
    const auto start_epoch = engine_.telemetry().start_epoch;
    if (reset_epoch_.has_value() && *reset_epoch_ != start_epoch) {
      clear_reset_state();
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::complete);
    }
    if (!reset_epoch_.has_value()) {
      reset_epoch_ = start_epoch;
    }
    if (reset_target_.has_value()) {
      if (engine_.master_fx_telemetry().dequeued_gestures >= *reset_target_) {
        clear_reset_state();
        return foundation::Result<NeutralResetProgress>::success(
            NeutralResetProgress::complete);
      }
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::pending);
    }

    constexpr auto gesture_count = audio::kFxChainOrder.size() + 1;
    while (reset_cursor_ < gesture_count) {
      const auto gesture =
          reset_cursor_ == 0
              ? audio::FxGesture{audio::FxGestureKind::hold_off,
                                 domain::PerformanceFx::filter, 0}
              : audio::FxGesture{audio::FxGestureKind::release,
                                 audio::kFxChainOrder.at(reset_cursor_ - 1), 0};
      const auto enqueued = engine_.enqueue_fx_gesture(gesture);
      if (enqueued == audio::FxEnqueueResult::queue_full) {
        return foundation::Result<NeutralResetProgress>::success(
            NeutralResetProgress::pending);
      }
      if (enqueued != audio::FxEnqueueResult::accepted) {
        return foundation::Result<NeutralResetProgress>::failure(
            enqueue_error("Performance replay neutral reset was rejected"));
      }
      ++reset_cursor_;
    }
    reset_target_ = engine_.master_fx_telemetry().enqueued_gestures;
    if (engine_.master_fx_telemetry().dequeued_gestures >= *reset_target_) {
      clear_reset_state();
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::complete);
    }
    return foundation::Result<NeutralResetProgress>::success(
        NeutralResetProgress::pending);
  }

 private:
  void clear_reset_state() noexcept {
    reset_target_.reset();
    reset_epoch_.reset();
    reset_cursor_ = 0;
  }

  audio::RealtimeEngine& engine_;
  std::shared_ptr<PatternPublicationGateway> gateway_;
  std::vector<std::shared_ptr<const cooker::PcmSample>> material_owners_;
  std::optional<std::uint64_t> reset_target_;
  std::optional<std::uint64_t> reset_epoch_;
  std::size_t reset_cursor_{};
  std::uint16_t bpm_{};
};

class EnginePerformanceReplayController final
    : public PerformanceReplayController {
 public:
  EnginePerformanceReplayController(
      audio::RealtimeEngine& engine,
      std::shared_ptr<EnginePerformanceReplaySink> sink)
      : engine_(engine), sink_(std::move(sink)), controller_(sink_) {}

  foundation::Result<ReplayRuntimeStatus> begin(
      const ReplayId& replay_id,
      std::shared_ptr<const cooker::PerformanceReplayProjection> projection)
      override {
    std::lock_guard lock(mutex_);
    const auto already_active =
        active_replay_id_.has_value() && *active_replay_id_ == replay_id;
    const auto bpm = projection ? projection->bpm : 0;
    auto begun = controller_.begin(replay_id, std::move(projection));
    if (!begun.has_value()) {
      const auto retained = controller_.status(replay_id);
      if (!already_active && retained.has_value() &&
          retained.value().state == ReplayState::playing) {
        sink_->set_bpm(bpm);
        active_replay_id_ = replay_id;
        start_transport(bpm);
      }
      return begun;
    }
    if (!already_active && begun.value().state == ReplayState::playing) {
      sink_->set_bpm(bpm);
      active_replay_id_ = replay_id;
      start_transport(bpm);
    }
    return begun;
  }

  foundation::Result<ReplayRuntimeStatus> status(
      const ReplayId& replay_id) const override {
    return controller_.status(replay_id);
  }

  foundation::Result<ReplayRuntimeStatus> stop(
      const ReplayId& replay_id) override {
    std::lock_guard lock(mutex_);
    auto stopped = controller_.stop(replay_id);
    if (stopped.has_value() && stopped.value().state != ReplayState::playing &&
        active_replay_id_.has_value() && *active_replay_id_ == replay_id) {
      active_replay_id_.reset();
    }
    return stopped;
  }

  void service() {
    std::lock_guard lock(mutex_);
    if (!active_replay_id_.has_value()) {
      return;
    }
    const auto telemetry = engine_.telemetry();
    if (!transport_valid_ || bpm_ < 40 || bpm_ > 240) {
      return;
    }
    if (telemetry.start_epoch != last_observed_epoch_) {
      anchor_ = audio::TransportAnchor{0, last_numerator_, bpm_};
    }
    const auto numerator =
        audio::tick_numerator_at(anchor_, telemetry.rendered_frames);
    if (!numerator.has_value()) {
      transport_valid_ = false;
      return;
    }
    last_observed_epoch_ = telemetry.start_epoch;
    last_numerator_ = numerator.value();
    auto advanced = controller_.advance_to(audio::whole_tick(last_numerator_));
    if (advanced.has_value() &&
        advanced.value().state != ReplayState::playing) {
      active_replay_id_.reset();
    }
  }

 private:
  void start_transport(std::uint16_t bpm) {
    const auto telemetry = engine_.telemetry();
    anchor_ = audio::TransportAnchor{telemetry.rendered_frames, 0, bpm};
    last_observed_epoch_ = telemetry.start_epoch;
    last_numerator_ = 0;
    bpm_ = bpm;
    transport_valid_ = bpm >= 40 && bpm <= 240;
  }

  audio::RealtimeEngine& engine_;
  mutable std::mutex mutex_;
  std::shared_ptr<EnginePerformanceReplaySink> sink_;
  ReferencePerformanceReplayController controller_;
  std::optional<ReplayId> active_replay_id_;
  audio::TransportAnchor anchor_{};
  std::uint64_t last_observed_epoch_{};
  std::uint64_t last_numerator_{};
  std::uint16_t bpm_{};
  bool transport_valid_{};
};

}  // namespace

PatternPublicationGateway make_engine_pattern_publication_gateway(
    audio::RealtimeEngine& engine) {
  const auto prepare =
      [](std::shared_ptr<const cooker::RuntimeSnapshot> snapshot)
      -> foundation::Result<audio::PreparedPatternView> {
    if (!snapshot) {
      return foundation::Result<audio::PreparedPatternView>::failure(
          adapter_error(foundation::ErrorCode::invalid_argument,
                        "Runtime Pattern material is required"));
    }
    return audio::PreparedPatternView::from_snapshot(*snapshot);
  };
  return PatternPublicationGateway{
      [&engine, prepare](
          std::shared_ptr<const cooker::RuntimeSnapshot> snapshot,
          std::optional<std::uint64_t> activation_frame,
          std::optional<audio::PatternReplacementAuthority>
              replacement_authority) {
        auto prepared = prepare(std::move(snapshot));
        if (!prepared.has_value()) {
          return foundation::Result<audio::PatternPublication>::failure(
              prepared.error());
        }
        static_cast<void>(engine.reclaim_retired_patterns());
        const auto publication = engine.publish_pattern_view(
            std::move(prepared.value()), activation_frame,
            std::move(replacement_authority));
        if (publication.result != audio::PatternPublishResult::accepted) {
          return foundation::Result<audio::PatternPublication>::failure(
              adapter_error(foundation::ErrorCode::invalid_argument,
                            "Realtime Pattern publication was rejected"));
        }
        return foundation::Result<audio::PatternPublication>::success(
            publication);
      },
      [&engine, prepare](
          std::shared_ptr<const cooker::RuntimeSnapshot> snapshot) {
        auto prepared = prepare(std::move(snapshot));
        if (!prepared.has_value()) {
          return foundation::Result<audio::PatternPublication>::failure(
              prepared.error());
        }
        static_cast<void>(engine.reclaim_retired_patterns());
        const auto publication = engine.publish_pattern_view_immediate(
            std::move(prepared.value()));
        if (publication.result != audio::PatternPublishResult::accepted) {
          return foundation::Result<audio::PatternPublication>::failure(
              adapter_error(foundation::ErrorCode::invalid_argument,
                            "Realtime Pattern publication was rejected"));
        }
        return foundation::Result<audio::PatternPublication>::success(
            publication);
      },
      [&engine](const audio::PatternReplacementAuthority& authority) {
        return engine.cancel_unclaimed_pattern_publication(authority);
      },
  };
}

// Live counterpart of EnginePerformanceReplaySink::apply_fx_gesture: the same
// gesture reaches the same DSP whether Core admits it live or replays it
// (P10-D7).
class EnginePerformanceGestureSink final : public PerformanceGestureSink {
 public:
  explicit EnginePerformanceGestureSink(audio::RealtimeEngine& engine)
      : engine_(engine) {}

  foundation::Result<void> apply_gesture(audio::FxGesture gesture) override {
    const auto enqueued = engine_.enqueue_fx_gesture(gesture);
    if (enqueued != audio::FxEnqueueResult::accepted) {
      return foundation::Result<void>::failure(enqueue_error(
          std::string(
              "Live Performance FX gesture was refused by the master bus: ") +
          std::string(fx_enqueue_reason(enqueued)) +
          "; prepare the master FX chain for the current Project tempo and "
          "start the engine before admitting the gesture"));
    }
    return foundation::Result<void>::success();
  }

 private:
  audio::RealtimeEngine& engine_;
};

EnginePerformanceAdapter make_engine_performance_adapter(
    audio::RealtimeEngine& engine, PatternPublicationGateway gateway) {
  if (!gateway.publish || !gateway.publish_immediate || !gateway.cancel) {
    throw std::invalid_argument("Pattern publication gateway is incomplete");
  }
  auto shared_gateway =
      std::make_shared<PatternPublicationGateway>(std::move(gateway));
  auto clock = std::make_shared<EnginePerformanceClock>(engine);
  auto launches = std::make_shared<EnginePatternLaunchAcknowledger>(
      engine, clock, shared_gateway);
  auto replay_sink = std::make_shared<EnginePerformanceReplaySink>(
      engine, shared_gateway);
  auto replay = std::make_shared<EnginePerformanceReplayController>(
      engine, std::move(replay_sink));
  return EnginePerformanceAdapter{
      clock,
      std::make_shared<EnginePerformanceInputSequencer>(),
      launches,
      replay,
      std::make_shared<EnginePerformanceGestureSink>(engine),
      [clock, launches = std::move(launches), replay = std::move(replay)]() {
        clock->service();
        launches->service();
        replay->service();
      },
  };
}

}  // namespace lmdj::facade
