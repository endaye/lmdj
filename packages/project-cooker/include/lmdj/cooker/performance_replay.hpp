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
  domain::PerformanceId performance_id;
  std::uint64_t resolved_revision{};
  std::uint16_t bpm{};
  bool quantize_enabled{};
  std::uint8_t swing_percent{};
  std::array<std::optional<ResolvedPad>, 64> pads;
  std::array<std::shared_ptr<const RuntimeSnapshot>, 16> patterns;
  std::vector<PerformanceReplayBoundary> boundaries;
  std::uint64_t event_count{};
};

foundation::Result<std::shared_ptr<const PerformanceReplayProjection>>
cook_performance_replay(
    const domain::ProjectState& project,
    const domain::PerformanceId& performance_id,
    ArtifactResolver resolve);

}  // namespace lmdj::cooker
