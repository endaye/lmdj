#include <lmdj/cooker/performance_replay.hpp>

#include <iomanip>
#include <map>
#include <sstream>
#include <string>
#include <utility>

namespace lmdj::cooker {
namespace {

using ReplayResult = foundation::Result<
    std::shared_ptr<const PerformanceReplayProjection>>;

ReplayResult replay_failure(
    foundation::ErrorCode code,
    std::string message) {
  return ReplayResult::failure(foundation::Error{code, std::move(message)});
}

std::optional<foundation::PatternId> projection_pattern_id(
    const domain::ProjectState& project) {
  constexpr std::uint64_t kMaximumSuffix = 0xffffffffffffULL;
  for (std::uint64_t suffix = 0;
       suffix <= project.patterns.size() && suffix <= kMaximumSuffix;
       ++suffix) {
    std::ostringstream encoded;
    encoded << "ffffffff-ffff-4fff-bfff-" << std::hex << std::nouppercase
            << std::setw(12) << std::setfill('0') << suffix;
    foundation::PatternId candidate{encoded.str()};
    if (!project.patterns.contains(candidate)) {
      return candidate;
    }
  }
  return std::nullopt;
}

}  // namespace

foundation::Result<std::shared_ptr<const PerformanceReplayProjection>>
cook_performance_replay(
    const domain::ProjectState& project,
    const domain::PerformanceId& performance_id,
    ArtifactResolver resolve) {
  const auto performance = project.performances.find(performance_id);
  if (performance == project.performances.end()) {
    return replay_failure(
        foundation::ErrorCode::not_found,
        "Performance does not exist");
  }
  if (performance->second.id != performance_id) {
    return replay_failure(
        foundation::ErrorCode::invalid_project,
        "Performance identity does not match its map key");
  }
  const auto valid_performance =
      domain::validate_performance(performance->second);
  if (!valid_performance.has_value()) {
    return ReplayResult::failure(valid_performance.error());
  }
  if (!resolve) {
    return replay_failure(
        foundation::ErrorCode::invalid_argument,
        "Performance replay requires an Artifact resolver");
  }

  struct CachedArtifact {
    foundation::ArtifactRef artifact;
    std::vector<std::byte> bytes;
  };
  std::map<std::string, CachedArtifact> cache;
  const auto cached_resolver = [&](const foundation::ArtifactRef& artifact)
      -> foundation::Result<std::vector<std::byte>> {
    const auto cached = cache.find(artifact.sha256);
    if (cached != cache.end()) {
      if (cached->second.artifact != artifact) {
        return foundation::Result<std::vector<std::byte>>::failure(
            foundation::Error{
                foundation::ErrorCode::cook_failed,
                "reused artifact digest has conflicting metadata",
            });
      }
      return foundation::Result<std::vector<std::byte>>::success(
          cached->second.bytes);
    }
    const auto resolved = resolve(artifact);
    if (!resolved.has_value()) {
      return foundation::Result<std::vector<std::byte>>::failure(
          resolved.error());
    }
    cache.emplace(
        artifact.sha256,
        CachedArtifact{artifact, resolved.value()});
    return foundation::Result<std::vector<std::byte>>::success(
        resolved.value());
  };

  auto projection_source = project;
  const auto pad_projection_id = projection_pattern_id(project);
  if (!pad_projection_id.has_value()) {
    return replay_failure(
        foundation::ErrorCode::invalid_project,
        "Project has no available replay projection Pattern identity");
  }
  projection_source.patterns.emplace(
      *pad_projection_id,
      domain::Pattern{*pad_projection_id, 1, {}});
  const auto pad_snapshot =
      cook(projection_source, *pad_projection_id, cached_resolver);
  if (!pad_snapshot.has_value()) {
    return ReplayResult::failure(pad_snapshot.error());
  }

  PerformanceReplayProjection projection{
      performance_id,
      project.revision,
      project.bpm,
      project.quantize_enabled,
      project.swing_percent,
      {},
      {},
      {},
      0,
  };
  for (const auto& pad : pad_snapshot.value()->pads) {
    const auto index = static_cast<std::size_t>(pad.slot.bank) * 16U +
                       static_cast<std::size_t>(pad.slot.pad);
    if (index >= projection.pads.size() ||
        projection.pads.at(index).has_value()) {
      return replay_failure(
          foundation::ErrorCode::invalid_project,
          "Project contains an invalid replay Pad slot");
    }
    projection.pads.at(index) = pad;
  }

  for (std::size_t slot = 0; slot < project.pattern_slots.size(); ++slot) {
    const auto& pattern_id = project.pattern_slots.at(slot);
    if (!pattern_id.has_value()) {
      continue;
    }
    const auto snapshot = cook(project, *pattern_id, cached_resolver);
    if (!snapshot.has_value()) {
      return ReplayResult::failure(snapshot.error());
    }
    projection.patterns.at(slot) = snapshot.value();
  }

  const auto canonical =
      domain::canonical_performance_events(performance->second.events);
  projection.event_count = static_cast<std::uint64_t>(canonical.size());
  projection.boundaries.reserve(canonical.size());
  const auto first_tick = canonical.empty()
                              ? 0U
                              : domain::performance_event_tick(canonical.front());
  for (const auto& event : canonical) {
    projection.boundaries.push_back(PerformanceReplayBoundary{
        domain::performance_event_tick(event) - first_tick,
        event,
    });
  }
  return ReplayResult::success(
      std::make_shared<const PerformanceReplayProjection>(
          std::move(projection)));
}

}  // namespace lmdj::cooker
