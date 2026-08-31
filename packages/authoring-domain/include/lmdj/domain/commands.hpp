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
  Asset asset;
  PadSlotId slot;
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

struct CreatePattern {
  CommandMeta meta;
  Pattern pattern;
};

struct AssignPatternSlot {
  CommandMeta meta;
  std::uint8_t slot;
  foundation::PatternId pattern_id;
};

struct ClearPatternSlot {
  CommandMeta meta;
  std::uint8_t slot;
};

struct MovePatternSlot {
  CommandMeta meta;
  std::uint8_t from_slot;
  std::uint8_t to_slot;
};

struct MergePatternEvents {
  CommandMeta meta;
  foundation::PatternId pattern_id;
  std::vector<PatternEvent> events;
};

struct UpdateSequenceSettings {
  CommandMeta meta;
  std::optional<std::uint16_t> bpm;
  std::optional<bool> quantize_enabled;
  std::optional<std::uint8_t> swing_percent;
};

using Command = std::variant<
    ImportAsset,
    AssignPad,
    CreatePattern,
    AssignPatternSlot,
    ClearPatternSlot,
    MovePatternSlot,
    MergePatternEvents,
    UpdateSequenceSettings>;

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
