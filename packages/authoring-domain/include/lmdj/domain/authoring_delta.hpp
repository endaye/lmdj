#pragma once

#include <map>
#include <optional>
#include <vector>

#include <lmdj/domain/command_handler.hpp>

namespace lmdj::domain {

template <class T>
struct AuthoringChange {
  T before;
  T after;
  bool operator==(const AuthoringChange&) const = default;
};

// An edit contains only the values its user action changed. Neither revision,
// Contract, receipts, Runtime state nor the session history is authoring data.
struct AuthoringDelta {
  foundation::ProjectId project_id;
  std::optional<AuthoringChange<std::uint16_t>> bpm;
  std::optional<AuthoringChange<bool>> quantize_enabled;
  std::optional<AuthoringChange<std::uint8_t>> swing_percent;
  std::vector<AuthoringChange<PadSlot>> pads;
  std::map<foundation::AssetId, AuthoringChange<std::optional<Asset>>> assets;
  std::map<foundation::PatternId, AuthoringChange<std::optional<Pattern>>> patterns;
  std::map<PerformanceId, AuthoringChange<std::optional<Performance>>> performances;
  std::map<std::uint8_t,
           AuthoringChange<std::optional<foundation::PatternId>>> pattern_slots;

  bool empty() const noexcept;
  bool operator==(const AuthoringDelta&) const = default;
};

struct ApplyAuthoringDelta {
  CommandMeta meta;
  AuthoringDelta delta;
};

foundation::Result<AuthoringDelta> authoring_difference(
    const ProjectState& before, const ProjectState& after);
AuthoringDelta reverse_authoring_delta(AuthoringDelta delta);
foundation::Result<AuthoringDelta> compose_authoring_deltas(
    const AuthoringDelta& first, const AuthoringDelta& second);
foundation::Result<AppliedCommand> apply(
    const ProjectState& state, const ApplyAuthoringDelta& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

}  // namespace lmdj::domain
