#pragma once

#include <cstdint>
#include <map>

#include <nlohmann/json.hpp>

#include <lmdj/domain/commands.hpp>

namespace lmdj::domain {

struct AppliedCommand {
  ProjectState state;
  nlohmann::json event;
  bool replayed;
};

struct CommandReceipt {
  std::uint64_t committed_revision;
  nlohmann::json event;
};

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const Command& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

}  // namespace lmdj::domain
