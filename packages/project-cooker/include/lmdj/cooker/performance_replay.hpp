#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

#include <lmdj/cooker/project_cooker.hpp>

namespace lmdj::cooker {

struct PerformanceReplayBoundary {
  std::uint64_t offset_tick{};
  domain::PerformanceEvent event;

  bool operator==(const PerformanceReplayBoundary&) const = default;
};

struct PerformanceReplayProjection {
  // The constructor keeps the positional form every existing caller uses, so
  // no caller relies on partially initializing an aggregate.
  PerformanceReplayProjection(
      domain::PerformanceId performance_id_value,
      std::uint64_t resolved_revision_value,
      std::uint16_t bpm_value,
      bool quantize_enabled_value,
      std::uint8_t swing_percent_value,
      std::array<std::optional<ResolvedPad>, 64> pads_value,
      std::array<std::shared_ptr<const RuntimeSnapshot>, 16> patterns_value,
      std::vector<PerformanceReplayBoundary> boundaries_value,
      std::uint64_t event_count_value,
      std::optional<domain::PerformanceInitialLiveState>
          initial_live_state_value = std::nullopt)
      : performance_id(std::move(performance_id_value)),
        resolved_revision(resolved_revision_value),
        bpm(bpm_value),
        quantize_enabled(quantize_enabled_value),
        swing_percent(swing_percent_value),
        pads(std::move(pads_value)),
        patterns(std::move(patterns_value)),
        boundaries(std::move(boundaries_value)),
        event_count(event_count_value),
        initial_live_state(std::move(initial_live_state_value)) {}

  domain::PerformanceId performance_id;
  std::uint64_t resolved_revision{};
  std::uint16_t bpm{};
  bool quantize_enabled{};
  std::uint8_t swing_percent{};
  std::array<std::optional<ResolvedPad>, 64> pads;
  std::array<std::shared_ptr<const RuntimeSnapshot>, 16> patterns;
  std::vector<PerformanceReplayBoundary> boundaries;
  std::uint64_t event_count{};
  // The recorded live-control header (lmdj.project.v5 5.4.1), restored before
  // the first event — including for a zero-event Performance. It is fixed
  // state, independent of the first event's tick normalization.
  std::optional<domain::PerformanceInitialLiveState> initial_live_state;
};

foundation::Result<std::shared_ptr<const PerformanceReplayProjection>>
cook_performance_replay(
    const domain::ProjectState& project,
    const domain::PerformanceId& performance_id,
    ArtifactResolver resolve);

}  // namespace lmdj::cooker
