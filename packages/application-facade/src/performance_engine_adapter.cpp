#include <algorithm>
#include <cmath>
#include <deque>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/detail/voice_dsp.hpp>
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

// The exact Bar length the Engine's PreparedPatternView derives for the same
// snapshot (prepared_sample_bank.cpp computes bar_frames with this public
// tick_boundary_frame call), so a deferred launch stays on the Engine's grid.
foundation::Result<std::uint64_t> pattern_bar_frames(
    const cooker::RuntimeSnapshot& pattern) {
  return audio::tick_boundary_frame(
      domain::kBarTicks4x4, pattern.bpm, pattern.ppq);
}

bool valid_playback(const cooker::ResolvedPlayback& playback,
                    std::uint32_t frame_count) noexcept {
  return playback.start_frame < playback.end_frame &&
         playback.end_frame <= frame_count &&
         valid_trigger_mode(playback.trigger_mode) &&
         std::isfinite(playback.linear_gain) && playback.linear_gain >= 0.0F &&
         audio::detail::voice_dsp_fits(playback, frame_count);
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

  // Inverse of frame_at_tick: labels a reserved Runtime frame with the
  // Performance clock's journal tick (#1974). The launch boundary comes from
  // the Engine's transport grid; the journal still records Performance ticks.
  foundation::Result<std::uint64_t> tick_at_frame(std::uint64_t frame) {
    std::lock_guard lock(mutex_);
    if (!anchored_ || !anchor_valid_ || anchor_.bpm < 40 ||
        anchor_.bpm > 240) {
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
    // Like frame_at_tick, only the observed playhead advances last_tick_;
    // a reserved future boundary must not pull read_tick ahead of the
    // performance it labels, or later admissions would land early.
    return audio::raw_tick_at(anchor_, frame);
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
    // An audio-claimed publication still ahead of the playhead keeps its
    // boundary; the successor reserves one full Bar behind it (P10-D22).
    bool claimed_boundary_ahead = false;
    std::uint64_t claimed_activation_frame = 0;
    std::uint64_t claimed_bar_frames = 0;
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
        claimed_boundary_ahead = previous.authority.has_value() &&
            telemetry.rendered_frames < previous.activation_frame;
        claimed_activation_frame = previous.activation_frame;
        claimed_bar_frames = previous.bar_frames;
      }
    }

    // Boundary authority (#1974): while the global Pattern transport plays,
    // a launch reserves the Engine's own next Bar from the transport origin —
    // the same boundary derivation pattern.transport.switch uses — and the
    // journal tick reports that boundary back through the Performance clock.
    // The Performance-clock Bar remains the boundary only where no transport
    // Bar exists: a journal-only empty-slot launch, or a launch with no
    // playing Pattern to derive from.
    const bool transport_boundary = resolved_pattern != nullptr &&
        telemetry.state == audio::RealtimeState::running &&
        engine_.current_pattern_id().has_value();

    if (!transport_boundary) {
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
          0,
      };
      if (resolved_pattern) {
        const auto pattern_id = resolved_pattern->pattern_id;
        const auto bar_frames = pattern_bar_frames(*resolved_pattern);
        if (!bar_frames.has_value()) {
          outcomes_[key].push_back(PatternLaunchOutcome{
              session_id,
              request_id,
              pattern_slot,
              earliest_target_tick,
              PatternLaunchOutcomeKind::failed,
          });
          return foundation::Result<PatternLaunchReservation>::failure(
              bar_frames.error());
        }
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
        next_pending.bar_frames = bar_frames.value();
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

    // Transport-owned boundary. Without an audio-claimed publication ahead,
    // no frame is requested and the Engine derives the next Bar from the
    // transport origin itself, exactly as the playing-state transport switch
    // does; a claimed predecessor pins the successor one full Bar behind the
    // boundary the Engine already holds, on the same grid.
    const auto pattern_id = resolved_pattern->pattern_id;
    const auto bar_frames = pattern_bar_frames(*resolved_pattern);
    if (!bar_frames.has_value()) {
      outcomes_[key].push_back(PatternLaunchOutcome{
          session_id,
          request_id,
          pattern_slot,
          earliest_target_tick,
          PatternLaunchOutcomeKind::failed,
      });
      return foundation::Result<PatternLaunchReservation>::failure(
          bar_frames.error());
    }
    std::optional<std::uint64_t> requested_activation;
    if (claimed_boundary_ahead) {
      if (claimed_activation_frame >
          std::numeric_limits<std::uint64_t>::max() - claimed_bar_frames) {
        outcomes_[key].push_back(PatternLaunchOutcome{
            session_id,
            request_id,
            pattern_slot,
            earliest_target_tick,
            PatternLaunchOutcomeKind::failed,
        });
        return foundation::Result<PatternLaunchReservation>::failure(
            adapter_error(foundation::ErrorCode::invalid_argument,
                          "Performance launch boundary overflowed"));
      }
      requested_activation = claimed_activation_frame + claimed_bar_frames;
    }
    const auto publication = gateway_->publish(
        std::move(resolved_pattern), requested_activation, replacement);
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
    const auto boundary_tick =
        clock_->tick_at_frame(publication.value().activation_frame);
    // The Engine boundary is already reserved; a clock that cannot label
    // the frame keeps the Performance-clock lower bound as the journal
    // tick rather than abandoning a publication the audio thread holds.
    const auto target_tick =
        boundary_tick.has_value() ? boundary_tick.value() : earliest_target_tick;
    pending_queue.push_back(Pending{
        session_id,
        request_id,
        pattern_slot,
        target_tick,
        publication.value().activation_frame,
        audio::PatternReplacementAuthority{
            publication.value().generation,
            pattern_id,
            publication.value().activation_frame,
        },
        false,
        telemetry.start_epoch,
        bar_frames.value(),
    });
    return foundation::Result<PatternLaunchReservation>::success(
        {target_tick, claimed});
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
    // Bar length of the reserved publication's Pattern, on the Engine's
    // grid; a successor deferred behind this launch waits one Bar of it.
    std::uint64_t bar_frames{};
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

// D0/P1 typed live-control admission core. Sole producer of the engine's
// bounded master-control queue: every sibling adapter surface (legacy gesture
// sink, replay sink, reset) routes through this object, so its accepted
// shadow and per-position history are the complete control-thread truth.
// ---------------------------------------------------------------------------


constexpr std::size_t fx_index(domain::PerformanceFx fx) noexcept {
  return static_cast<std::size_t>(fx);
}

audio::FilterType to_engine_filter_type(domain::PerformanceFilterType type) {
  switch (type) {
    case domain::PerformanceFilterType::lp:
      return audio::FilterType::low_pass;
    case domain::PerformanceFilterType::hp:
      return audio::FilterType::high_pass;
    case domain::PerformanceFilterType::bp:
      return audio::FilterType::band_pass;
  }
  return audio::FilterType::low_pass;
}

domain::PerformanceFilterType to_domain_filter_type(audio::FilterType type) {
  switch (type) {
    case audio::FilterType::low_pass:
      return domain::PerformanceFilterType::lp;
    case audio::FilterType::high_pass:
      return domain::PerformanceFilterType::hp;
    case audio::FilterType::band_pass:
      return domain::PerformanceFilterType::bp;
  }
  return domain::PerformanceFilterType::lp;
}

std::string make_runtime_generation() {
  std::random_device random;
  std::string hex;
  hex.reserve(32);
  for (int index = 0; index < 32; ++index) {
    const auto nibble = static_cast<unsigned>(random()) & 0xFU;
    hex.push_back("0123456789abcdef"[nibble]);
  }
  hex.at(12) = '4';
  constexpr std::string_view variants = "89ab";
  hex.at(16) = variants.at(
      std::string_view("0123456789abcdef").find(hex.at(16)) %
      variants.size());
  return hex.substr(0, 8) + "-" + hex.substr(8, 4) + "-" + hex.substr(12, 4) +
         "-" + hex.substr(16, 4) + "-" + hex.substr(20, 12);
}

struct LiveControlShadow {
  audio::FilterLiveState filter{};  // hold + legacy/independent branches
  std::array<domain::PerformanceFxGateState, 7> fx{};  // delay..cutter
  std::uint64_t muted_mask{};
  std::uint64_t solo_mask{};
  std::array<std::optional<std::string>, 8> generations{};
  // No operator==: audio::FilterLiveState is a plain POD. Comparisons go
  // through to_public_state.
};

PerformanceLiveControlState to_public_state(const LiveControlShadow& shadow) {
  PerformanceLiveControlState out;
  out.state.hold = shadow.filter.hold;
  if (shadow.filter.mode == audio::FilterMode::legacy) {
    out.state.filter = domain::LegacyFilterLiveState{
        shadow.filter.engaged, shadow.filter.frozen, shadow.filter.legacy_value};
  } else {
    out.state.filter = domain::IndependentFilterLiveState{
        shadow.filter.engaged,
        shadow.filter.frozen,
        to_domain_filter_type(shadow.filter.parameters.type),
        static_cast<std::uint16_t>(shadow.filter.parameters.cutoff_hz),
        shadow.filter.parameters.resonance_milli};
  }
  out.state.other_fx = shadow.fx;
  out.state.muted_mask = shadow.muted_mask;
  out.state.solo_mask = shadow.solo_mask;
  out.runtime_generations = shadow.generations;
  return out;
}

class EngineLiveControlCore final : public PerformanceLiveControlSink {
 public:
  explicit EngineLiveControlCore(audio::RealtimeEngine& engine)
      : engine_(engine) {
    last_seen_start_epoch_ = engine_.telemetry().start_epoch;
    reset_shadow_locked();
  }

  std::optional<std::string> current_control_epoch() override {
    std::lock_guard lock(mutex_);
    observe_engine_epoch_locked();
    return epoch_;
  }

  std::optional<std::string> bound_control_project() override {
    std::lock_guard lock(mutex_);
    observe_engine_epoch_locked();
    return bound_project_;
  }

  foundation::Result<std::string> bind_control_target(
      std::string project_uuid) override {
    if (!domain::is_valid_uuid(project_uuid)) {
      return foundation::Result<std::string>::failure(adapter_error(
          foundation::ErrorCode::invalid_argument,
          "Live control target is not a verified Project UUID"));
    }
    std::lock_guard lock(mutex_);
    observe_engine_epoch_locked();
    const auto start_epoch = engine_.telemetry().start_epoch;
    if (epoch_.has_value() && bound_project_ == project_uuid &&
        bound_start_epoch_ == start_epoch) {
      return foundation::Result<std::string>::success(*epoch_);
    }
    epoch_ = make_runtime_generation();
    bound_project_ = std::move(project_uuid);
    bound_start_epoch_ = start_epoch;
    return foundation::Result<std::string>::success(*epoch_);
  }

  void invalidate_control_target() override {
    std::lock_guard lock(mutex_);
    epoch_.reset();
    bound_project_.reset();
  }

  PerformanceLiveControlSnapshot live_control_snapshot() override {
    std::lock_guard lock(mutex_);
    observe_engine_epoch_locked();
    const auto applied = applied_position_locked();
    PerformanceLiveControlSnapshot snapshot;
    snapshot.accepted = to_public_state(shadow_);
    snapshot.applied = to_public_state(state_at_locked(applied));
    snapshot.accepted_control_sequence = accepted_control_sequence_;
    snapshot.applied_control_sequence =
        history_front_sequence_advanced_to(applied);
    snapshot.engine_start_epoch = engine_.telemetry().start_epoch;
    return snapshot;
  }

  foundation::Result<PerformanceLiveControlReservation> reserve_live_control(
      const std::string& control_epoch,
      const PerformanceLiveControlIntent& intent) override {
    std::lock_guard lock(mutex_);
    observe_engine_epoch_locked();
    if (const auto stale = require_epoch_locked(control_epoch); !stale.empty()) {
      return foundation::Result<PerformanceLiveControlReservation>::failure(
          adapter_error(foundation::ErrorCode::invalid_argument, stale));
    }
    auto derived = derive_locked(intent);
    if (!derived.has_value()) {
      return foundation::Result<PerformanceLiveControlReservation>::failure(
          derived.error());
    }
    if (occupied_cells_locked() >= audio::kRealtimeQueueCapacity) {
      return foundation::Result<PerformanceLiveControlReservation>::failure(
          adapter_error(foundation::ErrorCode::internal_error,
                        "the master FX gesture queue is full"));
    }
    ++held_cells_;
    const auto& outcome = derived.value();
    PerformanceLiveControlReservation reservation;
    reservation.fx_gesture = outcome.fx_gesture;
    reservation.filter_gesture = outcome.filter_gesture;
    reservation.pad_gates = outcome.pad_gates;
    reservation.resulting_state = to_public_state(outcome.shadow);
    reservation.assigned_generation = outcome.assigned_generation;
    reservation.control_sequence = accepted_control_sequence_ + 1;
    reservation.hold = std::shared_ptr<void>(
        this, [](void* core) {
          static_cast<EngineLiveControlCore*>(core)->release_cell();
        });
    return foundation::Result<PerformanceLiveControlReservation>::success(
        std::move(reservation));
  }

  foundation::Result<PerformanceLiveControlReservation>
  reserve_live_control_republish(
      const std::string& control_epoch,
      std::optional<audio::FxGesture> fx_gesture,
      std::optional<audio::FilterGesture> filter_gesture,
      std::optional<audio::PadGatesState> pad_gates,
      PerformanceLiveControlState resulting_state,
      std::optional<std::string> assigned_generation) override {
    std::lock_guard lock(mutex_);
    observe_engine_epoch_locked();
    if (const auto stale = require_epoch_locked(control_epoch); !stale.empty()) {
      return foundation::Result<PerformanceLiveControlReservation>::failure(
          adapter_error(foundation::ErrorCode::invalid_argument, stale));
    }
    if (occupied_cells_locked() >= audio::kRealtimeQueueCapacity) {
      return foundation::Result<PerformanceLiveControlReservation>::failure(
          adapter_error(foundation::ErrorCode::internal_error,
                        "the master FX gesture queue is full"));
    }
    ++held_cells_;
    PerformanceLiveControlReservation reservation;
    reservation.fx_gesture = std::move(fx_gesture);
    reservation.filter_gesture = std::move(filter_gesture);
    reservation.pad_gates = pad_gates;
    reservation.resulting_state = std::move(resulting_state);
    reservation.assigned_generation = std::move(assigned_generation);
    reservation.control_sequence = accepted_control_sequence_ + 1;
    reservation.hold = std::shared_ptr<void>(
        this, [](void* core) {
          static_cast<EngineLiveControlCore*>(core)->release_cell();
        });
    return foundation::Result<PerformanceLiveControlReservation>::success(
        std::move(reservation));
  }

  foundation::Result<void> publish_live_control(
      PerformanceLiveControlReservation reservation) override {
    std::unique_lock lock(mutex_);
    if (!reservation.hold) {
      return foundation::Result<void>::failure(adapter_error(
          foundation::ErrorCode::invalid_argument,
          "Live control reservation is not held"));
    }
    const auto result = enqueue_locked(reservation);
    if (result != audio::FxEnqueueResult::accepted) {
      lock.unlock();
      reservation.hold.reset();  // known refusal: release the cell, no change
      return foundation::Result<void>::failure(enqueue_error(
          std::string("Live control admission was refused by the master bus: ") +
          std::string(fx_enqueue_reason(result))));
    }
    LiveControlShadow next = shadow_;
    apply_reservation_to_shadow(next, reservation);
    commit_shadow_locked(std::move(next), true);
    lock.unlock();
    reservation.hold.reset();  // deleter takes the mutex
    return foundation::Result<void>::success();
  }

  void cancel_live_control(
      PerformanceLiveControlReservation reservation) noexcept override {
    reservation.hold.reset();
  }

  foundation::Result<PerformanceControlFence> begin_fence(
      const std::string& control_epoch) override {
    std::lock_guard lock(mutex_);
    observe_engine_epoch_locked();
    if (const auto stale = require_epoch_locked(control_epoch); !stale.empty()) {
      return foundation::Result<PerformanceControlFence>::failure(
          adapter_error(foundation::ErrorCode::invalid_argument, stale));
    }
    if (occupied_cells_locked() >= audio::kRealtimeQueueCapacity) {
      return foundation::Result<PerformanceControlFence>::failure(
          adapter_error(foundation::ErrorCode::internal_error,
                        "the master FX gesture queue is full"));
    }
    return foundation::Result<PerformanceControlFence>::success(
        PerformanceControlFence{
            enqueued_position_locked(),
            engine_.telemetry().start_epoch,
            to_public_state(shadow_),
        });
  }

  PerformanceFenceReadiness fence_readiness(
      const PerformanceControlFence& fence) override {
    std::lock_guard lock(mutex_);
    observe_engine_epoch_locked();
    if (!epoch_.has_value() ||
        engine_.telemetry().start_epoch != fence.engine_start_epoch) {
      return PerformanceFenceReadiness::diverged;
    }
    const auto applied = applied_position_locked();
    if (applied < fence.position) {
      return PerformanceFenceReadiness::pending;
    }
    return to_public_state(state_at_locked(fence.position)) == fence.header
               ? PerformanceFenceReadiness::ready
               : PerformanceFenceReadiness::diverged;
  }

  // ---- sibling-surface admissions (legacy gesture sink, replay sink, reset)
  // Every one enqueues through here so the shadow and history stay complete.

  foundation::Result<void> publish_legacy_gesture(
      audio::FxGesture gesture, bool live_admission = true) {
    std::lock_guard lock(mutex_);
    const auto result = engine_.enqueue_fx_gesture(gesture);
    if (result != audio::FxEnqueueResult::accepted) {
      return foundation::Result<void>::failure(enqueue_error(
          std::string(
              "Live Performance FX gesture was refused by the master bus: ") +
          std::string(fx_enqueue_reason(result)) +
          "; prepare the master FX chain for the current Project tempo and "
          "start the engine before admitting the gesture"));
    }
    LiveControlShadow next = shadow_;
    apply_fx_gesture_to_shadow(next, gesture);
    commit_shadow_locked(std::move(next), live_admission);
    return foundation::Result<void>::success();
  }

  foundation::Result<void> publish_filter_change(
      domain::PerformanceFilterPhase phase,
      domain::PerformanceFilterType type,
      std::uint16_t cutoff_hz,
      std::uint16_t resonance_milli) {
    const audio::FilterGesture gesture{
        phase == domain::PerformanceFilterPhase::engage
            ? audio::FilterPhase::engage
        : phase == domain::PerformanceFilterPhase::move
            ? audio::FilterPhase::move
            : audio::FilterPhase::release,
        audio::FilterParameters{
            to_engine_filter_type(type), cutoff_hz, resonance_milli}};
    std::lock_guard lock(mutex_);
    const auto result = engine_.enqueue_filter_gesture(gesture);
    if (result != audio::FxEnqueueResult::accepted) {
      return foundation::Result<void>::failure(enqueue_error(
          std::string("Performance replay Filter change was rejected: ") +
          std::string(fx_enqueue_reason(result))));
    }
    LiveControlShadow next = shadow_;
    next.filter = audio::MasterFxChain::filter_live_state_after(
        next.filter, gesture);
    if (gesture.phase == audio::FilterPhase::engage) {
      next.generations[fx_index(domain::PerformanceFx::filter)] =
          make_runtime_generation();
    } else if (gesture.phase == audio::FilterPhase::release) {
      next.generations[fx_index(domain::PerformanceFx::filter)].reset();
    }
    commit_shadow_locked(std::move(next), false);
    return foundation::Result<void>::success();
  }

  foundation::Result<void> publish_pad_gates(
      std::uint64_t muted_mask, std::uint64_t solo_mask) {
    std::lock_guard lock(mutex_);
    const auto result = engine_.enqueue_pad_gates(muted_mask, solo_mask);
    if (result != audio::FxEnqueueResult::accepted) {
      return foundation::Result<void>::failure(enqueue_error(
          std::string("Performance replay Pad gates were rejected: ") +
          std::string(fx_enqueue_reason(result))));
    }
    LiveControlShadow next = shadow_;
    next.muted_mask = muted_mask;
    next.solo_mask = solo_mask;
    commit_shadow_locked(std::move(next), false);
    return foundation::Result<void>::success();
  }

  // Queue-position accessors for sibling sinks (replay header/reset ACKs).
  std::uint64_t enqueued_position() {
    std::lock_guard lock(mutex_);
    return enqueued_position_raw();
  }

  std::uint64_t applied_position() {
    std::lock_guard lock(mutex_);
    return applied_position_locked();
  }

 private:
  struct DerivedAdmission {
    std::optional<audio::FxGesture> fx_gesture;
    std::optional<audio::FilterGesture> filter_gesture;
    std::optional<audio::PadGatesState> pad_gates;
    LiveControlShadow shadow;
    std::optional<std::string> assigned_generation;
  };

  std::string require_epoch_locked(const std::string& control_epoch) const {
    if (!epoch_.has_value() || *epoch_ != control_epoch) {
      return "Live control epoch is stale or unbound";
    }
    return {};
  }

  void release_cell() noexcept {
    std::lock_guard lock(mutex_);
    if (held_cells_ != 0) {
      --held_cells_;
    }
  }

  void observe_engine_epoch_locked() {
    const auto start_epoch = engine_.telemetry().start_epoch;
    if (start_epoch == last_seen_start_epoch_) {
      return;
    }
    // Engine restart (project change, close, stop/start): the M1/F1 engine
    // lifecycle already reset masks, FX and Filter to neutral; the old
    // epoch, callbacks and receipts must not reach the new state.
    last_seen_start_epoch_ = start_epoch;
    epoch_.reset();
    bound_project_.reset();
    accepted_control_sequence_ = 0;
    reset_shadow_locked();
  }

  void reset_shadow_locked() {
    shadow_ = LiveControlShadow{};
    history_.clear();
    history_.push_back(HistoryEntry{enqueued_position_raw(), shadow_, 0});
  }

  std::uint64_t enqueued_position_raw() const {
    const auto fx = engine_.master_fx_telemetry();
    return fx.enqueued_gestures + fx.enqueued_filter_controls +
           fx.enqueued_tempo_updates +
           engine_.pad_gates_status().accepted_sequence;
  }

  std::uint64_t enqueued_position_locked() const {
    return enqueued_position_raw();
  }

  std::uint64_t applied_position_locked() const {
    const auto fx = engine_.master_fx_telemetry();
    return fx.dequeued_gestures + fx.dequeued_filter_controls +
           fx.applied_tempo_updates +
           engine_.pad_gates_status().applied.sequence;
  }

  std::uint64_t occupied_cells_locked() const {
    const auto fx = engine_.master_fx_telemetry();
    const auto queued = fx.queued_gestures +
                        (fx.enqueued_filter_controls -
                         fx.dequeued_filter_controls) +
                        (fx.enqueued_tempo_updates - fx.applied_tempo_updates);
    const auto gates = engine_.pad_gates_status();
    return queued + (gates.accepted_sequence - gates.applied.sequence) +
           held_cells_;
  }

  const LiveControlShadow& state_at_locked(std::uint64_t position) const {
    const HistoryEntry* found = &history_.front();
    for (const auto& entry : history_) {
      if (entry.position > position) {
        break;
      }
      found = &entry;
    }
    return found->shadow;
  }

  std::uint64_t history_front_sequence_advanced_to(
      std::uint64_t applied) const {
    std::uint64_t sequence = 0;
    for (const auto& entry : history_) {
      if (entry.position > applied) {
        break;
      }
      sequence = entry.control_sequence;
    }
    return sequence;
  }

  static LiveControlShadow shadow_from_public(
      const PerformanceLiveControlState& state) {
    LiveControlShadow shadow;
    shadow.filter.hold = state.state.hold;
    if (const auto* legacy =
            std::get_if<domain::LegacyFilterLiveState>(&state.state.filter)) {
      shadow.filter.mode = audio::FilterMode::legacy;
      shadow.filter.engaged = legacy->engaged;
      shadow.filter.frozen = legacy->frozen;
      shadow.filter.legacy_value = legacy->value;
    } else {
      const auto& independent =
          std::get<domain::IndependentFilterLiveState>(state.state.filter);
      shadow.filter.mode = audio::FilterMode::independent;
      shadow.filter.engaged = independent.engaged;
      shadow.filter.frozen = independent.frozen;
      shadow.filter.parameters = audio::FilterParameters{
          to_engine_filter_type(independent.type),
          independent.cutoff_hz,
          independent.resonance_milli};
    }
    shadow.fx = state.state.other_fx;
    shadow.muted_mask = state.state.muted_mask;
    shadow.solo_mask = state.state.solo_mask;
    shadow.generations = state.runtime_generations;
    return shadow;
  }

  void commit_shadow_locked(LiveControlShadow next, bool live_admission) {
    if (live_admission) {
      ++accepted_control_sequence_;
    }
    shadow_ = std::move(next);
    history_.push_back(HistoryEntry{
        enqueued_position_raw(), shadow_,
        live_admission ? accepted_control_sequence_
                       : (history_.empty() ? 0 : history_.back().control_sequence)});
    const auto applied = applied_position_locked();
    while (history_.size() > 1 && history_.at(1).position <= applied) {
      history_.pop_front();
    }
  }

  void apply_fx_gesture_to_shadow(
      LiveControlShadow& shadow, audio::FxGesture gesture) {
    // Mirrors MasterFxChain::apply_gesture exactly; the pure Filter helpers
    // cover the Filter stage.
    shadow.filter = audio::MasterFxChain::filter_live_state_after(
        shadow.filter, gesture);
    const auto index = fx_index(gesture.fx);
    switch (gesture.kind) {
      case audio::FxGestureKind::hold_on:
      case audio::FxGestureKind::hold_off:
        // hold_off also clears every frozen flag; the Filter helper above
        // covers hold and the Filter branches, the FX stages follow here.
        if (gesture.kind == audio::FxGestureKind::hold_off) {
          for (auto& stage : shadow.fx) {
            stage.frozen = false;
          }
        }
        return;
      case audio::FxGestureKind::engage:
        if (gesture.fx != domain::PerformanceFx::filter) {
          auto& stage = shadow.fx.at(index - 1);
          stage.engaged = true;
          stage.frozen = false;
          stage.value = gesture.value;
        }
        shadow.generations[index] = make_runtime_generation();
        return;
      case audio::FxGestureKind::move:
        if (gesture.fx == domain::PerformanceFx::filter) {
          const auto independent_was_active =
              shadow.filter.mode == audio::FilterMode::independent &&
              (shadow.filter.engaged || shadow.filter.frozen);
          if (independent_was_active) {
            // Legacy move takeover: a new legacy binding is born.
            shadow.generations[index] = make_runtime_generation();
          }
        } else {
          shadow.fx.at(index - 1).value = gesture.value;
        }
        return;
      case audio::FxGestureKind::release:
        shadow.generations[index].reset();
        if (gesture.fx != domain::PerformanceFx::filter) {
          auto& stage = shadow.fx.at(index - 1);
          const auto was_active = stage.engaged || stage.frozen;
          stage.engaged = false;
          stage.frozen = shadow.filter.hold && was_active;
          if (!stage.frozen) {
            stage.value = 0;
          }
        }
        return;
    }
  }

  void apply_reservation_to_shadow(
      LiveControlShadow& shadow,
      const PerformanceLiveControlReservation& reservation) {
    shadow = shadow_from_public(reservation.resulting_state);
  }

  audio::FxEnqueueResult enqueue_locked(
      const PerformanceLiveControlReservation& reservation) {
    if (reservation.fx_gesture.has_value()) {
      return engine_.enqueue_fx_gesture(*reservation.fx_gesture);
    }
    if (reservation.filter_gesture.has_value()) {
      return engine_.enqueue_filter_gesture(*reservation.filter_gesture);
    }
    if (reservation.pad_gates.has_value()) {
      return engine_.enqueue_pad_gates(reservation.pad_gates->muted_mask,
                                       reservation.pad_gates->solo_mask);
    }
    return audio::FxEnqueueResult::accepted;  // hold_on/off map to fx_gesture
  }

  foundation::Result<DerivedAdmission> derive_locked(
      const PerformanceLiveControlIntent& intent) {
    using Intent = PerformanceLiveControlIntent;
    DerivedAdmission derived;
    derived.shadow = shadow_;
    const auto filter_index = fx_index(domain::PerformanceFx::filter);
    const auto binding_mismatch = adapter_error(
        foundation::ErrorCode::invalid_argument,
        "Live control gesture generation does not match the engaged binding");
    switch (intent.kind) {
      case Intent::Kind::filter_parameter: {
        audio::FilterParameters tuple;
        const auto base =
            shadow_.filter.mode == audio::FilterMode::independent
                ? shadow_.filter.parameters
                : audio::kFilterDefaultParameters;
        tuple = base;
        switch (intent.parameter) {
          case Intent::FilterParameter::type:
            if (intent.value > 2) {
              return foundation::Result<DerivedAdmission>::failure(
                  adapter_error(foundation::ErrorCode::invalid_argument,
                                "Filter type is invalid"));
            }
            tuple.type = static_cast<audio::FilterType>(intent.value);
            break;
          case Intent::FilterParameter::cutoff_hz:
            if (intent.value < audio::kFilterCutoffMinimumHz ||
                intent.value > audio::kFilterCutoffMaximumHz) {
              return foundation::Result<DerivedAdmission>::failure(
                  adapter_error(foundation::ErrorCode::invalid_argument,
                                "Filter cutoff is outside 20-20000 Hz"));
            }
            tuple.cutoff_hz = intent.value;
            break;
          case Intent::FilterParameter::resonance_milli:
            if (intent.value > audio::kFilterResonanceMaximumMilli) {
              return foundation::Result<DerivedAdmission>::failure(
                  adapter_error(foundation::ErrorCode::invalid_argument,
                                "Filter resonance is outside 0-1000"));
            }
            tuple.resonance_milli =
                static_cast<std::uint16_t>(intent.value);
            break;
        }
        if (intent.phase == domain::PerformanceFilterPhase::engage) {
          derived.filter_gesture =
              audio::FilterGesture{audio::FilterPhase::engage, tuple};
          derived.assigned_generation = make_runtime_generation();
          derived.shadow.filter =
              audio::MasterFxChain::filter_live_state_after(
                  derived.shadow.filter, *derived.filter_gesture);
          derived.shadow.generations[filter_index] =
              derived.assigned_generation;
        } else if (intent.phase == domain::PerformanceFilterPhase::move) {
          if (shadow_.filter.mode != audio::FilterMode::independent ||
              !shadow_.filter.engaged ||
              !intent.gesture_generation.has_value() ||
              shadow_.generations[filter_index] !=
                  *intent.gesture_generation) {
            return foundation::Result<DerivedAdmission>::failure(
                binding_mismatch);
          }
          derived.filter_gesture =
              audio::FilterGesture{audio::FilterPhase::move, tuple};
          derived.shadow.filter =
              audio::MasterFxChain::filter_live_state_after(
                  derived.shadow.filter, *derived.filter_gesture);
        } else {
          return foundation::Result<DerivedAdmission>::failure(adapter_error(
              foundation::ErrorCode::invalid_argument,
              "filter_parameter requires phase engage or move; use "
              "filter_release to release"));
        }
        return foundation::Result<DerivedAdmission>::success(
            std::move(derived));
      }
      case Intent::Kind::filter_release: {
        if (shadow_.filter.mode != audio::FilterMode::independent ||
            !shadow_.filter.engaged ||
            !intent.gesture_generation.has_value() ||
            shadow_.generations[filter_index] != *intent.gesture_generation) {
          return foundation::Result<DerivedAdmission>::failure(
              binding_mismatch);
        }
        derived.filter_gesture = audio::FilterGesture{
            audio::FilterPhase::release, shadow_.filter.parameters};
        derived.shadow.filter =
            audio::MasterFxChain::filter_live_state_after(
                derived.shadow.filter, *derived.filter_gesture);
        derived.shadow.generations[filter_index].reset();
        return foundation::Result<DerivedAdmission>::success(
            std::move(derived));
      }
      case Intent::Kind::fx_parameter: {
        if (intent.value > audio::kMasterFxValueMaximum) {
          return foundation::Result<DerivedAdmission>::failure(adapter_error(
              foundation::ErrorCode::invalid_argument,
              "the value is outside the 0-1000 scale"));
        }
        const auto index = fx_index(intent.fx);
        if (intent.phase == domain::PerformanceFilterPhase::engage) {
          derived.fx_gesture = audio::FxGesture{
              audio::FxGestureKind::engage, intent.fx,
              static_cast<std::uint16_t>(intent.value)};
          derived.assigned_generation = make_runtime_generation();
          apply_fx_gesture_to_shadow(derived.shadow, *derived.fx_gesture);
          derived.shadow.generations[index] = derived.assigned_generation;
        } else if (intent.phase == domain::PerformanceFilterPhase::move) {
          if (!intent.gesture_generation.has_value() ||
              shadow_.generations[index] != *intent.gesture_generation) {
            return foundation::Result<DerivedAdmission>::failure(
                binding_mismatch);
          }
          derived.fx_gesture = audio::FxGesture{
              audio::FxGestureKind::move, intent.fx,
              static_cast<std::uint16_t>(intent.value)};
          apply_fx_gesture_to_shadow(derived.shadow, *derived.fx_gesture);
        } else {
          return foundation::Result<DerivedAdmission>::failure(adapter_error(
              foundation::ErrorCode::invalid_argument,
              "fx_parameter requires phase engage or move; use fx_release to "
              "release"));
        }
        return foundation::Result<DerivedAdmission>::success(
            std::move(derived));
      }
      case Intent::Kind::fx_release: {
        const auto index = fx_index(intent.fx);
        if (!intent.gesture_generation.has_value() ||
            shadow_.generations[index] != *intent.gesture_generation) {
          return foundation::Result<DerivedAdmission>::failure(
              binding_mismatch);
        }
        derived.fx_gesture = audio::FxGesture{
            audio::FxGestureKind::release, intent.fx, 0};
        apply_fx_gesture_to_shadow(derived.shadow, *derived.fx_gesture);
        return foundation::Result<DerivedAdmission>::success(
            std::move(derived));
      }
      case Intent::Kind::pad_mute:
      case Intent::Kind::pad_solo: {
        if (intent.slot > 63) {
          return foundation::Result<DerivedAdmission>::failure(adapter_error(
              foundation::ErrorCode::invalid_argument,
              "Pad gate slot is outside 0-63"));
        }
        auto muted = shadow_.muted_mask;
        auto solo = shadow_.solo_mask;
        const auto bit = std::uint64_t{1} << intent.slot;
        if (intent.kind == Intent::Kind::pad_mute) {
          muted = intent.enabled ? (muted | bit) : (muted & ~bit);
        } else {
          solo = intent.enabled ? (solo | bit) : (solo & ~bit);
        }
        derived.pad_gates = audio::PadGatesState{muted, solo};
        derived.shadow.muted_mask = muted;
        derived.shadow.solo_mask = solo;
        return foundation::Result<DerivedAdmission>::success(
            std::move(derived));
      }
      case Intent::Kind::clear_pad_gates: {
        derived.pad_gates = audio::PadGatesState{0, 0};
        derived.shadow.muted_mask = 0;
        derived.shadow.solo_mask = 0;
        return foundation::Result<DerivedAdmission>::success(
            std::move(derived));
      }
      case Intent::Kind::hold_on:
      case Intent::Kind::hold_off: {
        const auto on = intent.kind == Intent::Kind::hold_on;
        if (on == shadow_.filter.hold) {
          return foundation::Result<DerivedAdmission>::failure(adapter_error(
              foundation::ErrorCode::invalid_argument,
              on ? "Performance HOLD is already on"
                 : "Performance HOLD is already off"));
        }
        derived.fx_gesture = audio::FxGesture{
            on ? audio::FxGestureKind::hold_on
               : audio::FxGestureKind::hold_off,
            domain::PerformanceFx::filter, 0};
        apply_fx_gesture_to_shadow(derived.shadow, *derived.fx_gesture);
        return foundation::Result<DerivedAdmission>::success(
            std::move(derived));
      }
    }
    return foundation::Result<DerivedAdmission>::failure(adapter_error(
        foundation::ErrorCode::invalid_argument,
        "Live control intent is invalid"));
  }

  struct HistoryEntry {
    std::uint64_t position;
    LiveControlShadow shadow;
    std::uint64_t control_sequence;
  };

  audio::RealtimeEngine& engine_;
  std::mutex mutex_;
  std::optional<std::string> epoch_;
  std::optional<std::string> bound_project_;
  std::uint64_t bound_start_epoch_{};
  std::uint64_t last_seen_start_epoch_{};
  LiveControlShadow shadow_;
  std::deque<HistoryEntry> history_;
  std::uint64_t accepted_control_sequence_{};
  std::uint64_t held_cells_{};
};

// Live counterpart of EnginePerformanceReplaySink::apply_fx_gesture: the same
// gesture reaches the same DSP whether Core admits it live or replays it
// (P10-D7). Routes through the shared admission core so the accepted shadow
// also tracks legacy sessionless gestures.
class EnginePerformanceGestureSink final : public PerformanceGestureSink {
 public:
  explicit EnginePerformanceGestureSink(
      std::shared_ptr<EngineLiveControlCore> core)
      : core_(std::move(core)) {}

  foundation::Result<void> apply_gesture(audio::FxGesture gesture) override {
    return core_->publish_legacy_gesture(gesture);
  }

 private:
  std::shared_ptr<EngineLiveControlCore> core_;
};

class EnginePerformanceReplaySink final : public PerformanceReplayRuntimeSink {
 public:
  EnginePerformanceReplaySink(
      audio::RealtimeEngine& engine,
      std::shared_ptr<PatternPublicationGateway> gateway,
      std::shared_ptr<EngineLiveControlCore> live_core)
      : engine_(engine),
        gateway_(std::move(gateway)),
        live_core_(std::move(live_core)) {}

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
    const auto published = live_core_->publish_legacy_gesture(gesture, false);
    if (!published.has_value()) {
      return foundation::Result<void>::failure(
          enqueue_error("Performance replay FX gesture was rejected"));
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> apply_filter_change(
      domain::PerformanceFilterPhase phase,
      domain::PerformanceFilterType type,
      std::uint16_t cutoff_hz,
      std::uint16_t resonance_milli) override {
    return live_core_->publish_filter_change(phase, type, cutoff_hz,
                                             resonance_milli);
  }

  foundation::Result<void> apply_pad_gates(
      std::uint64_t muted_mask, std::uint64_t solo_mask) override {
    return live_core_->publish_pad_gates(muted_mask, solo_mask);
  }

  foundation::Result<void> apply_initial_live_state(
      const domain::PerformanceInitialLiveState& state) override {
    // HOLD first so a frozen-only stage freezes on its release below; then
    // each active stage, then the gate masks. Engage does reset the stage's
    // DSP buffers, which is correct at replay start: no recorded tail lives
    // in a fresh engine, and the original capture Wav remains the audio
    // authority regardless.
    if (state.hold) {
      const auto hold = live_core_->publish_legacy_gesture(
          audio::FxGesture{audio::FxGestureKind::hold_on,
                           domain::PerformanceFx::filter, 0},
          false);
      if (!hold.has_value()) {
        return hold;
      }
    }
    for (std::size_t index = 0; index < state.other_fx.size(); ++index) {
      const auto& stage = state.other_fx.at(index);
      if (!stage.engaged && !stage.frozen) {
        continue;
      }
      const auto fx = static_cast<domain::PerformanceFx>(index + 1);
      const auto engaged = live_core_->publish_legacy_gesture(
          audio::FxGesture{audio::FxGestureKind::engage, fx, stage.value},
          false);
      if (!engaged.has_value()) {
        return engaged;
      }
      if (stage.frozen && !stage.engaged) {
        const auto released = live_core_->publish_legacy_gesture(
            audio::FxGesture{audio::FxGestureKind::release, fx, 0}, false);
        if (!released.has_value()) {
          return released;
        }
      }
    }
    if (const auto* legacy =
            std::get_if<domain::LegacyFilterLiveState>(&state.filter)) {
      if (legacy->engaged || legacy->frozen) {
        const auto engaged = live_core_->publish_legacy_gesture(
            audio::FxGesture{audio::FxGestureKind::engage,
                             domain::PerformanceFx::filter, legacy->value},
            false);
        if (!engaged.has_value()) {
          return engaged;
        }
        if (legacy->frozen && !legacy->engaged) {
          const auto released = live_core_->publish_legacy_gesture(
              audio::FxGesture{audio::FxGestureKind::release,
                               domain::PerformanceFx::filter, 0},
              false);
          if (!released.has_value()) {
            return released;
          }
        }
      }
    } else {
      const auto& independent =
          std::get<domain::IndependentFilterLiveState>(state.filter);
      if (independent.engaged || independent.frozen) {
        const auto engaged = live_core_->publish_filter_change(
            domain::PerformanceFilterPhase::engage, independent.type,
            independent.cutoff_hz, independent.resonance_milli);
        if (!engaged.has_value()) {
          return engaged;
        }
        if (independent.frozen && !independent.engaged) {
          const auto released = live_core_->publish_filter_change(
              domain::PerformanceFilterPhase::release, independent.type,
              independent.cutoff_hz, independent.resonance_milli);
          if (!released.has_value()) {
            return released;
          }
        }
      }
    }
    if (state.muted_mask != 0 || state.solo_mask != 0) {
      const auto gates =
          live_core_->publish_pad_gates(state.muted_mask, state.solo_mask);
      if (!gates.has_value()) {
        return gates;
      }
    }
    header_target_ = live_core_->enqueued_position();
    return foundation::Result<void>::success();
  }

  foundation::Result<NeutralResetProgress>
  initial_live_state_applied() override {
    if (!header_target_.has_value()) {
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::complete);
    }
    if (live_core_->applied_position() >= *header_target_) {
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::complete);
    }
    return foundation::Result<NeutralResetProgress>::success(
        NeutralResetProgress::pending);
  }

  foundation::Result<NeutralResetProgress> reset_neutral() override {
    // Quiescent Engine Stop clears the FX queue and resets the master bus.
    // Project replacement stops a replay with audio already suspended; no
    // callback can acknowledge newly enqueued gestures in that state.
    if (engine_.telemetry().state == audio::RealtimeState::stopped) {
      clear_reset_state();
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::complete);
    }
    const auto start_epoch = engine_.telemetry().start_epoch;
    if (reset_epoch_.has_value() && *reset_epoch_ != start_epoch) {
      clear_reset_state();
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::complete);
    }
    if (!reset_epoch_.has_value()) {
      reset_epoch_ = start_epoch;
    }
    if (reset_targets_.has_value()) {
      if (reset_reached()) {
        clear_reset_state();
        return foundation::Result<NeutralResetProgress>::success(
            NeutralResetProgress::complete);
      }
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::pending);
    }

    // Neutral covers every live channel: HOLD off, the seven non-Filter FX
    // and the legacy Filter released, the independent Filter released when
    // it is active, and both Pad gate masks cleared. Queue pressure keeps
    // the reset pending; the cursor resumes without duplicating gestures.
    constexpr auto legacy_gesture_count = audio::kFxChainOrder.size() + 1;
    while (reset_cursor_ < legacy_gesture_count) {
      const auto gesture =
          reset_cursor_ == 0
              ? audio::FxGesture{audio::FxGestureKind::hold_off,
                                 domain::PerformanceFx::filter, 0}
              : audio::FxGesture{audio::FxGestureKind::release,
                                 audio::kFxChainOrder.at(reset_cursor_ - 1), 0};
      const auto published = live_core_->publish_legacy_gesture(gesture, false);
      if (!published.has_value()) {
        if (reset_queue_full(published.error())) {
          return foundation::Result<NeutralResetProgress>::success(
              NeutralResetProgress::pending);
        }
        return foundation::Result<NeutralResetProgress>::failure(
            published.error());
      }
      ++reset_cursor_;
    }
    if (reset_cursor_ == legacy_gesture_count) {
      const auto snapshot = live_core_->live_control_snapshot();
      if (const auto* independent =
              std::get_if<domain::IndependentFilterLiveState>(
                  &snapshot.accepted.state.filter);
          independent != nullptr &&
          (independent->engaged || independent->frozen)) {
        const auto released = live_core_->publish_filter_change(
            domain::PerformanceFilterPhase::release, independent->type,
            independent->cutoff_hz, independent->resonance_milli);
        if (!released.has_value()) {
          if (reset_queue_full(released.error())) {
            return foundation::Result<NeutralResetProgress>::success(
                NeutralResetProgress::pending);
          }
          return foundation::Result<NeutralResetProgress>::failure(
              released.error());
        }
      }
      ++reset_cursor_;
    }
    if (reset_cursor_ == legacy_gesture_count + 1) {
      const auto gates = live_core_->publish_pad_gates(0, 0);
      if (!gates.has_value()) {
        if (reset_queue_full(gates.error())) {
          return foundation::Result<NeutralResetProgress>::success(
              NeutralResetProgress::pending);
        }
        return foundation::Result<NeutralResetProgress>::failure(
            gates.error());
      }
      ++reset_cursor_;
    }
    reset_targets_ = ResetTargets{
        engine_.master_fx_telemetry().enqueued_gestures,
        engine_.master_fx_telemetry().enqueued_filter_controls,
        engine_.pad_gates_status().accepted_sequence,
    };
    if (reset_reached()) {
      clear_reset_state();
      return foundation::Result<NeutralResetProgress>::success(
          NeutralResetProgress::complete);
    }
    return foundation::Result<NeutralResetProgress>::success(
        NeutralResetProgress::pending);
  }

 private:
  struct ResetTargets {
    std::uint64_t gestures;
    std::uint64_t filter_controls;
    std::uint64_t pad_gates;
  };

  bool reset_reached() const {
    const auto fx = engine_.master_fx_telemetry();
    return fx.dequeued_gestures >= reset_targets_->gestures &&
           fx.dequeued_filter_controls >= reset_targets_->filter_controls &&
           engine_.pad_gates_status().applied.sequence >=
               reset_targets_->pad_gates;
  }

  static bool reset_queue_full(const foundation::Error& error) {
    return error.message.find(
               fx_enqueue_reason(audio::FxEnqueueResult::queue_full)) !=
           std::string::npos;
  }

  void clear_reset_state() noexcept {
    reset_targets_.reset();
    reset_epoch_.reset();
    reset_cursor_ = 0;
  }

  audio::RealtimeEngine& engine_;
  std::shared_ptr<PatternPublicationGateway> gateway_;
  std::shared_ptr<EngineLiveControlCore> live_core_;
  std::vector<std::shared_ptr<const cooker::PcmSample>> material_owners_;
  std::optional<ResetTargets> reset_targets_;
  std::optional<std::uint64_t> reset_epoch_;
  std::optional<std::uint64_t> header_target_;
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

// ---------------------------------------------------------------------------

EnginePerformanceAdapter make_engine_performance_adapter(
    audio::RealtimeEngine& engine, PatternPublicationGateway gateway) {
  if (!gateway.publish || !gateway.publish_immediate || !gateway.cancel) {
    throw std::invalid_argument("Pattern publication gateway is incomplete");
  }
  auto shared_gateway =
      std::make_shared<PatternPublicationGateway>(std::move(gateway));
  auto live_core = std::make_shared<EngineLiveControlCore>(engine);
  auto clock = std::make_shared<EnginePerformanceClock>(engine);
  auto launches = std::make_shared<EnginePatternLaunchAcknowledger>(
      engine, clock, shared_gateway);
  auto replay_sink = std::make_shared<EnginePerformanceReplaySink>(
      engine, shared_gateway, live_core);
  auto replay = std::make_shared<EnginePerformanceReplayController>(
      engine, std::move(replay_sink));
  return EnginePerformanceAdapter{
      clock,
      std::make_shared<EnginePerformanceInputSequencer>(),
      launches,
      replay,
      std::make_shared<EnginePerformanceGestureSink>(live_core),
      [clock, launches = std::move(launches), replay = std::move(replay)]() {
        clock->service();
        launches->service();
        replay->service();
      },
      std::move(live_core),
  };
}

}  // namespace lmdj::facade
