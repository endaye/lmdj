#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <variant>

#include <lmdj/domain/project.hpp>

namespace lmdj::domain {

struct CommandMeta {
  foundation::CommandId command_id;
  std::uint64_t expected_revision;
};

struct ImportAsset {
  CommandMeta meta;
  Asset asset;
};

struct AssignPad {
  CommandMeta meta;
  PadSlotId slot;
  std::optional<foundation::AssetId> asset_id;
};

struct ImportAssignSample {
  CommandMeta meta;
  PadSlotId slot;
  Asset asset;
};

struct UpdatePadPlayback {
  CommandMeta meta;
  PadSlotId slot;
  PadPlayback playback;
};

struct ResetPadPlayback {
  CommandMeta meta;
  PadSlotId slot;
};

struct RecordTake {
  CommandMeta meta;
  RawTake take;
  Pattern pattern;
};

struct CreatePattern {
  CommandMeta meta;
  Pattern pattern;
};

using Command = std::variant<ImportAsset, AssignPad, RecordTake, CreatePattern>;

struct AppliedCommand;
struct CommandReceipt;

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const ImportAssignSample& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const UpdatePadPlayback& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const ResetPadPlayback& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

}  // namespace lmdj::domain
