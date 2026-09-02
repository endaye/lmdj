#pragma once

#include <cstdint>
#include <memory>

#include <lmdj/audio/master_fx.hpp>
#include <lmdj/cooker/performance_replay.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::facade {

struct ReplayIdTag;
using ReplayId = foundation::StrongId<ReplayIdTag>;

enum class ReplayState : std::uint8_t {
  playing,
  stopped,
  complete,
};

struct ReplayRuntimeStatus {
  ReplayState state{ReplayState::playing};
  std::uint64_t event_cursor{};
  std::uint64_t event_count{};
  std::uint64_t resolved_revision{};

  bool operator==(const ReplayRuntimeStatus&) const = default;
};

enum class NeutralResetProgress : std::uint8_t {
  pending,
  complete,
};

class PerformanceReplayController {
 public:
  virtual ~PerformanceReplayController() = default;
  virtual foundation::Result<ReplayRuntimeStatus> begin(
      const ReplayId& replay_id,
      std::shared_ptr<const cooker::PerformanceReplayProjection> projection) =
      0;
  virtual foundation::Result<ReplayRuntimeStatus> status(
      const ReplayId& replay_id) const = 0;
  virtual foundation::Result<ReplayRuntimeStatus> stop(
      const ReplayId& replay_id) = 0;
};

class PerformanceReplayRuntimeSink {
 public:
  virtual ~PerformanceReplayRuntimeSink() = default;
  virtual foundation::Result<void> apply_pad_hit(
      const cooker::ResolvedPad& pad,
      std::uint64_t duration_tick,
      std::uint8_t velocity) = 0;
  virtual foundation::Result<void> apply_pattern_launch(
      std::shared_ptr<const cooker::RuntimeSnapshot> pattern) = 0;
  virtual foundation::Result<void> apply_fx_gesture(
      audio::FxGesture gesture) = 0;
  virtual foundation::Result<NeutralResetProgress> reset_neutral() = 0;
};

class ReferencePerformanceReplayController final
    : public PerformanceReplayController {
 public:
  explicit ReferencePerformanceReplayController(
      std::shared_ptr<PerformanceReplayRuntimeSink> sink);
  ~ReferencePerformanceReplayController() override;

  ReferencePerformanceReplayController(
      const ReferencePerformanceReplayController&) = delete;
  ReferencePerformanceReplayController& operator=(
      const ReferencePerformanceReplayController&) = delete;
  ReferencePerformanceReplayController(
      ReferencePerformanceReplayController&&) noexcept;
  ReferencePerformanceReplayController& operator=(
      ReferencePerformanceReplayController&&) noexcept;

  foundation::Result<ReplayRuntimeStatus> begin(
      const ReplayId& replay_id,
      std::shared_ptr<const cooker::PerformanceReplayProjection> projection)
      override;
  foundation::Result<ReplayRuntimeStatus> status(
      const ReplayId& replay_id) const override;
  foundation::Result<ReplayRuntimeStatus> stop(
      const ReplayId& replay_id) override;

  foundation::Result<ReplayRuntimeStatus> advance_to(
      std::uint64_t elapsed_tick);

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

std::shared_ptr<PerformanceReplayController>
make_unavailable_performance_replay_controller();

}  // namespace lmdj::facade
