#include <lmdj/facade/performance_replay.hpp>

#include <map>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <variant>

namespace lmdj::facade {
namespace {

foundation::Error replay_error(
    foundation::ErrorCode code,
    std::string message) {
  return foundation::Error{code, std::move(message)};
}

foundation::Error unavailable_error() {
  return foundation::Error{
      foundation::ErrorCode::invalid_argument,
      "Performance replay Runtime is unavailable",
      {{"reason", "performance_replay_runtime_unavailable"}},
  };
}

class UnavailablePerformanceReplayController final
    : public PerformanceReplayController {
 public:
  foundation::Result<ReplayRuntimeStatus> begin(
      const ReplayId&,
      std::shared_ptr<const cooker::PerformanceReplayProjection>) override {
    return foundation::Result<ReplayRuntimeStatus>::failure(
        unavailable_error());
  }

  foundation::Result<ReplayRuntimeStatus> status(
      const ReplayId&) const override {
    return foundation::Result<ReplayRuntimeStatus>::failure(
        unavailable_error());
  }

  foundation::Result<ReplayRuntimeStatus> stop(
      const ReplayId&) override {
    return foundation::Result<ReplayRuntimeStatus>::failure(
        unavailable_error());
  }
};

}  // namespace

struct ReferencePerformanceReplayController::Impl {
  struct ReplayEntry {
    std::shared_ptr<const cooker::PerformanceReplayProjection> projection;
    ReplayRuntimeStatus status;
    std::optional<ReplayState> reset_target;
  };

  explicit Impl(std::shared_ptr<PerformanceReplayRuntimeSink> sink_value)
      : sink(std::move(sink_value)) {
    if (!sink) {
      throw std::invalid_argument(
          "Performance replay Runtime sink is required");
    }
  }

  foundation::Result<void> apply(
      const ReplayEntry& entry,
      const domain::PerformanceEvent& event) {
    return std::visit(
        [&](const auto& payload) -> foundation::Result<void> {
          using Payload = std::decay_t<decltype(payload)>;
          if constexpr (std::is_same_v<
                            Payload,
                            domain::PadHitPerformanceEvent>) {
            if (payload.slot >= entry.projection->pads.size() ||
                !entry.projection->pads.at(payload.slot).has_value()) {
              return foundation::Result<void>::failure(replay_error(
                  foundation::ErrorCode::missing_asset,
                  "Performance replay Pad is unresolved"));
            }
            return sink->apply_pad_hit(
                *entry.projection->pads.at(payload.slot),
                payload.duration_tick,
                payload.velocity);
          } else if constexpr (std::is_same_v<
                                   Payload,
                                   domain::PatternLaunchPerformanceEvent>) {
            if (payload.pattern_slot >= entry.projection->patterns.size()) {
              return foundation::Result<void>::failure(replay_error(
                  foundation::ErrorCode::invalid_project,
                  "Performance replay Pattern slot is invalid"));
            }
            const auto& pattern =
                entry.projection->patterns.at(payload.pattern_slot);
            return pattern
                       ? sink->apply_pattern_launch(pattern)
                       : foundation::Result<void>::success();
          } else if constexpr (std::is_same_v<
                                   Payload,
                                   domain::FxEngagePerformanceEvent>) {
            return sink->apply_fx_gesture(audio::FxGesture{
                audio::FxGestureKind::engage, payload.fx, payload.value});
          } else if constexpr (std::is_same_v<
                                   Payload,
                                   domain::FxMovePerformanceEvent>) {
            return sink->apply_fx_gesture(audio::FxGesture{
                audio::FxGestureKind::move, payload.fx, payload.value});
          } else if constexpr (std::is_same_v<
                                   Payload,
                                   domain::FxReleasePerformanceEvent>) {
            return sink->apply_fx_gesture(audio::FxGesture{
                audio::FxGestureKind::release, payload.fx, 0});
          } else if constexpr (std::is_same_v<
                                   Payload,
                                   domain::HoldOnPerformanceEvent>) {
            return sink->apply_fx_gesture(audio::FxGesture{
                audio::FxGestureKind::hold_on,
                domain::PerformanceFx::filter,
                0});
          } else {
            return sink->apply_fx_gesture(audio::FxGesture{
                audio::FxGestureKind::hold_off,
                domain::PerformanceFx::filter,
                0});
          }
        },
        event.payload);
  }

  foundation::Result<ReplayRuntimeStatus> finish_reset(
      const std::string& replay_key,
      ReplayEntry& entry) {
    const auto reset = sink->reset_neutral();
    if (!reset.has_value()) {
      return foundation::Result<ReplayRuntimeStatus>::failure(reset.error());
    }
    entry.status.state = *entry.reset_target;
    entry.reset_target.reset();
    if (active_replay_id == replay_key) {
      active_replay_id.clear();
    }
    return foundation::Result<ReplayRuntimeStatus>::success(entry.status);
  }

  std::shared_ptr<PerformanceReplayRuntimeSink> sink;
  mutable std::mutex mutex;
  std::map<std::string, ReplayEntry> replays;
  std::string active_replay_id;
};

ReferencePerformanceReplayController::ReferencePerformanceReplayController(
    std::shared_ptr<PerformanceReplayRuntimeSink> sink)
    : impl_(std::make_unique<Impl>(std::move(sink))) {}

ReferencePerformanceReplayController::~ReferencePerformanceReplayController() =
    default;
ReferencePerformanceReplayController::ReferencePerformanceReplayController(
    ReferencePerformanceReplayController&&) noexcept = default;
ReferencePerformanceReplayController&
ReferencePerformanceReplayController::operator=(
    ReferencePerformanceReplayController&&) noexcept = default;

foundation::Result<ReplayRuntimeStatus>
ReferencePerformanceReplayController::begin(
    const ReplayId& replay_id,
    std::shared_ptr<const cooker::PerformanceReplayProjection> projection) {
  if (!domain::is_valid_uuid(replay_id.value()) || !projection ||
      projection->event_count != projection->boundaries.size()) {
    return foundation::Result<ReplayRuntimeStatus>::failure(replay_error(
        foundation::ErrorCode::invalid_argument,
        "Performance replay begin request is invalid"));
  }
  for (std::size_t index = 1; index < projection->boundaries.size(); ++index) {
    if (projection->boundaries.at(index - 1).offset_tick >
        projection->boundaries.at(index).offset_tick) {
      return foundation::Result<ReplayRuntimeStatus>::failure(replay_error(
          foundation::ErrorCode::invalid_argument,
          "Performance replay boundaries are not canonical"));
    }
  }
  std::lock_guard lock(impl_->mutex);
  const auto key = replay_id.value();
  const auto existing = impl_->replays.find(key);
  if (existing != impl_->replays.end()) {
    return foundation::Result<ReplayRuntimeStatus>::success(
        existing->second.status);
  }
  if (!impl_->active_replay_id.empty()) {
    return foundation::Result<ReplayRuntimeStatus>::failure(replay_error(
        foundation::ErrorCode::invalid_argument,
        "a Performance replay is already playing"));
  }
  const ReplayRuntimeStatus initial_status{
      ReplayState::playing,
      0,
      projection->event_count,
      projection->resolved_revision,
  };
  auto [inserted, created] = impl_->replays.emplace(
      key,
      Impl::ReplayEntry{
          std::move(projection),
          initial_status,
          std::nullopt,
      });
  if (!created) {
    return foundation::Result<ReplayRuntimeStatus>::failure(replay_error(
        foundation::ErrorCode::duplicate_id,
        "Performance replay identity already exists"));
  }
  auto& entry = inserted->second;
  impl_->active_replay_id = key;
  if (entry.status.event_count == 0) {
    entry.reset_target = ReplayState::complete;
    const auto completed = impl_->finish_reset(key, entry);
    if (!completed.has_value()) {
      impl_->active_replay_id.clear();
      impl_->replays.erase(inserted);
    }
    return completed;
  }
  return foundation::Result<ReplayRuntimeStatus>::success(entry.status);
}

foundation::Result<ReplayRuntimeStatus>
ReferencePerformanceReplayController::status(
    const ReplayId& replay_id) const {
  std::lock_guard lock(impl_->mutex);
  const auto found = impl_->replays.find(replay_id.value());
  if (found == impl_->replays.end()) {
    return foundation::Result<ReplayRuntimeStatus>::failure(replay_error(
        foundation::ErrorCode::not_found,
        "Performance replay does not exist"));
  }
  return foundation::Result<ReplayRuntimeStatus>::success(found->second.status);
}

foundation::Result<ReplayRuntimeStatus>
ReferencePerformanceReplayController::stop(const ReplayId& replay_id) {
  std::lock_guard lock(impl_->mutex);
  const auto key = replay_id.value();
  const auto found = impl_->replays.find(key);
  if (found == impl_->replays.end()) {
    return foundation::Result<ReplayRuntimeStatus>::failure(replay_error(
        foundation::ErrorCode::not_found,
        "Performance replay does not exist"));
  }
  auto& entry = found->second;
  if (entry.status.state != ReplayState::playing) {
    return foundation::Result<ReplayRuntimeStatus>::success(entry.status);
  }
  if (!entry.reset_target.has_value()) {
    entry.reset_target = ReplayState::stopped;
  }
  return impl_->finish_reset(key, entry);
}

foundation::Result<ReplayRuntimeStatus>
ReferencePerformanceReplayController::advance_to(
    std::uint64_t elapsed_tick) {
  std::lock_guard lock(impl_->mutex);
  if (impl_->active_replay_id.empty()) {
    return foundation::Result<ReplayRuntimeStatus>::failure(replay_error(
        foundation::ErrorCode::not_found,
        "no Performance replay is playing"));
  }
  const auto key = impl_->active_replay_id;
  auto& entry = impl_->replays.at(key);
  if (entry.reset_target.has_value()) {
    return foundation::Result<ReplayRuntimeStatus>::success(entry.status);
  }
  while (entry.status.event_cursor < entry.status.event_count) {
    const auto cursor = static_cast<std::size_t>(entry.status.event_cursor);
    const auto& boundary = entry.projection->boundaries.at(cursor);
    if (boundary.offset_tick > elapsed_tick) {
      break;
    }
    const auto applied = impl_->apply(entry, boundary.event);
    if (!applied.has_value()) {
      entry.reset_target = ReplayState::stopped;
      const auto reset = impl_->finish_reset(key, entry);
      if (!reset.has_value()) {
        return reset;
      }
      return foundation::Result<ReplayRuntimeStatus>::failure(applied.error());
    }
    ++entry.status.event_cursor;
  }
  if (entry.status.event_cursor == entry.status.event_count) {
    entry.reset_target = ReplayState::complete;
    return impl_->finish_reset(key, entry);
  }
  return foundation::Result<ReplayRuntimeStatus>::success(entry.status);
}

std::shared_ptr<PerformanceReplayController>
make_unavailable_performance_replay_controller() {
  return std::make_shared<UnavailablePerformanceReplayController>();
}

}  // namespace lmdj::facade
