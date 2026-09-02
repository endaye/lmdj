#include <lmdj/facade/performance_runtime.hpp>

#include <algorithm>
#include <chrono>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <utility>

namespace lmdj::facade {
namespace {

constexpr std::uint64_t kNanosecondsPerSecond = 1'000'000'000ULL;
constexpr std::uint64_t kTicksPerBeat = 960ULL;
constexpr std::uint64_t kSecondsPerMinute = 60ULL;

std::uint64_t elapsed_ticks(
    std::uint64_t elapsed_ns,
    std::uint16_t bpm) noexcept {
  const auto ticks_per_second =
      static_cast<std::uint64_t>(bpm) * kTicksPerBeat / kSecondsPerMinute;
  const auto whole_seconds = elapsed_ns / kNanosecondsPerSecond;
  const auto remainder_ns = elapsed_ns % kNanosecondsPerSecond;
  if (ticks_per_second != 0 &&
      whole_seconds >
          std::numeric_limits<std::uint64_t>::max() / ticks_per_second) {
    return std::numeric_limits<std::uint64_t>::max();
  }
  const auto whole_ticks = whole_seconds * ticks_per_second;
  const auto partial_ticks =
      remainder_ns * ticks_per_second / kNanosecondsPerSecond;
  if (whole_ticks >
      std::numeric_limits<std::uint64_t>::max() - partial_ticks) {
    return std::numeric_limits<std::uint64_t>::max();
  }
  return whole_ticks + partial_ticks;
}

std::uint64_t saturating_add(
    std::uint64_t left,
    std::uint64_t right) noexcept {
  if (left > std::numeric_limits<std::uint64_t>::max() - right) {
    return std::numeric_limits<std::uint64_t>::max();
  }
  return left + right;
}

class SteadyPerformanceTimeSource final : public PerformanceTimeSource {
 public:
  std::uint64_t now_ns() override {
    const auto elapsed = std::chrono::steady_clock::now().time_since_epoch();
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed).count());
  }
};

class HeadlessPerformanceClock final : public PerformanceClock {
 public:
  explicit HeadlessPerformanceClock(
      std::shared_ptr<PerformanceTimeSource> time_source)
      : time_source_(std::move(time_source)) {}

  void anchor(std::uint16_t bpm, std::uint64_t at_tick) override {
    std::lock_guard lock(mutex_);
    const auto now = time_source_->now_ns();
    bpm_ = bpm;
    anchor_ns_ = std::max(anchor_ns_, now);
    anchor_tick_ = std::max(at_tick, last_tick_);
    last_tick_ = anchor_tick_;
    anchored_ = true;
  }

  foundation::Result<std::uint64_t> read_tick() override {
    std::lock_guard lock(mutex_);
    if (!anchored_) {
      return foundation::Result<std::uint64_t>::success(last_tick_);
    }
    const auto now = time_source_->now_ns();
    const auto elapsed = now > anchor_ns_ ? now - anchor_ns_ : 0;
    const auto tick = saturating_add(
        anchor_tick_, elapsed_ticks(elapsed, bpm_));
    last_tick_ = std::max(last_tick_, tick);
    return foundation::Result<std::uint64_t>::success(last_tick_);
  }

 private:
  std::shared_ptr<PerformanceTimeSource> time_source_;
  std::mutex mutex_;
  std::uint64_t anchor_ns_{};
  std::uint64_t anchor_tick_{};
  std::uint64_t last_tick_{};
  std::uint16_t bpm_{};
  bool anchored_{};
};

class HeadlessPerformanceInputSequencer final
    : public PerformanceInputSequencer {
 public:
  void seed(std::uint64_t last_input_sequence) override {
    std::lock_guard lock(mutex_);
    next_ = std::max(next_, last_input_sequence);
  }

  foundation::Result<std::uint64_t> next() override {
    std::lock_guard lock(mutex_);
    if (next_ == std::numeric_limits<std::uint64_t>::max()) {
      return foundation::Result<std::uint64_t>::failure(foundation::Error{
          foundation::ErrorCode::internal_error,
          "Performance input sequence is exhausted",
      });
    }
    return foundation::Result<std::uint64_t>::success(++next_);
  }

 private:
  std::mutex mutex_;
  std::uint64_t next_{};
};

class HeadlessPatternLaunchTransport final
    : public PatternLaunchAcknowledger {
 public:
  explicit HeadlessPatternLaunchTransport(
      std::shared_ptr<PerformanceClock> clock)
      : clock_(std::move(clock)) {}

  foundation::Result<PatternLaunchReservation> reserve(
      const foundation::SequenceSessionId& session_id,
      const foundation::CommandId& request_id,
      std::uint8_t pattern_slot,
      std::uint64_t earliest_target_tick,
      std::shared_ptr<const cooker::RuntimeSnapshot>) override {
    std::lock_guard lock(mutex_);
    pending_.insert_or_assign(
        session_id.value(),
        Pending{
            session_id,
            request_id,
            pattern_slot,
            earliest_target_tick,
        });
    return foundation::Result<PatternLaunchReservation>::success(
        {earliest_target_tick, false});
  }

  std::vector<PatternLaunchOutcome> drain(
      const foundation::SequenceSessionId& session_id) override {
    std::lock_guard lock(mutex_);
    auto found = outcomes_.find(session_id.value());
    if (found == outcomes_.end()) {
      return {};
    }
    auto drained = std::move(found->second);
    outcomes_.erase(found);
    return drained;
  }

  void cancel(
      const foundation::SequenceSessionId& session_id) noexcept override {
    std::lock_guard lock(mutex_);
    pending_.erase(session_id.value());
  }

  void service() {
    auto tick = clock_->read_tick();
    if (!tick.has_value()) {
      return;
    }
    std::lock_guard lock(mutex_);
    for (auto iterator = pending_.begin(); iterator != pending_.end();) {
      if (iterator->second.target_tick > tick.value()) {
        ++iterator;
        continue;
      }
      const auto pending = iterator->second;
      outcomes_[pending.session_id.value()].push_back(PatternLaunchOutcome{
          pending.session_id,
          pending.request_id,
          pending.pattern_slot,
          pending.target_tick,
          PatternLaunchOutcomeKind::applied,
      });
      iterator = pending_.erase(iterator);
    }
  }

 private:
  struct Pending {
    foundation::SequenceSessionId session_id;
    foundation::CommandId request_id;
    std::uint8_t pattern_slot{};
    std::uint64_t target_tick{};
  };

  std::shared_ptr<PerformanceClock> clock_;
  std::mutex mutex_;
  std::map<std::string, Pending> pending_;
  std::map<std::string, std::vector<PatternLaunchOutcome>> outcomes_;
};

class SilentPerformanceReplayRuntimeSink final
    : public PerformanceReplayRuntimeSink {
 public:
  foundation::Result<void> apply_pad_hit(
      const cooker::ResolvedPad&,
      std::uint64_t,
      std::uint8_t) override {
    return foundation::Result<void>::success();
  }

  foundation::Result<void> apply_pattern_launch(
      std::shared_ptr<const cooker::RuntimeSnapshot>) override {
    return foundation::Result<void>::success();
  }

  foundation::Result<void> apply_fx_gesture(audio::FxGesture) override {
    return foundation::Result<void>::success();
  }

  foundation::Result<NeutralResetProgress> reset_neutral() override {
    return foundation::Result<NeutralResetProgress>::success(
        NeutralResetProgress::complete);
  }
};

class HeadlessPerformanceReplayController final
    : public PerformanceReplayController {
 public:
  explicit HeadlessPerformanceReplayController(
      std::shared_ptr<PerformanceTimeSource> time_source)
      : time_source_(std::move(time_source)),
        controller_(std::make_shared<SilentPerformanceReplayRuntimeSink>()) {}

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
        active_replay_id_ = replay_id;
        started_ns_ = time_source_->now_ns();
        bpm_ = bpm;
      }
      return begun;
    }
    if (!already_active && begun.value().state == ReplayState::playing) {
      active_replay_id_ = replay_id;
      started_ns_ = time_source_->now_ns();
      bpm_ = bpm;
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
        active_replay_id_.has_value() &&
        *active_replay_id_ == replay_id) {
      active_replay_id_.reset();
    }
    return stopped;
  }

  void service() {
    std::lock_guard lock(mutex_);
    if (!active_replay_id_.has_value()) {
      return;
    }
    const auto now = time_source_->now_ns();
    const auto elapsed = now > started_ns_ ? now - started_ns_ : 0;
    auto advanced = controller_.advance_to(elapsed_ticks(elapsed, bpm_));
    if (advanced.has_value() &&
        advanced.value().state != ReplayState::playing) {
      active_replay_id_.reset();
    }
  }

 private:
  std::shared_ptr<PerformanceTimeSource> time_source_;
  mutable std::mutex mutex_;
  ReferencePerformanceReplayController controller_;
  std::optional<ReplayId> active_replay_id_;
  std::uint64_t started_ns_{};
  std::uint16_t bpm_{};
};

}  // namespace

std::shared_ptr<PerformanceTimeSource> make_steady_performance_time_source() {
  return std::make_shared<SteadyPerformanceTimeSource>();
}

PerformanceRuntimeBridge make_headless_performance_runtime_bridge(
    std::shared_ptr<PerformanceTimeSource> time_source) {
  if (!time_source) {
    throw std::invalid_argument("Performance time source is required");
  }
  auto clock = std::make_shared<HeadlessPerformanceClock>(time_source);
  auto launches = std::make_shared<HeadlessPatternLaunchTransport>(clock);
  auto replay =
      std::make_shared<HeadlessPerformanceReplayController>(time_source);
  return PerformanceRuntimeBridge{
      clock,
      std::make_shared<HeadlessPerformanceInputSequencer>(),
      launches,
      replay,
      [launches = std::move(launches), replay = std::move(replay)]() {
        launches->service();
        replay->service();
      },
  };
}

}  // namespace lmdj::facade
