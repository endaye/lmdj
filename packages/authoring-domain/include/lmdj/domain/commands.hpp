#pragma once

#include <cstdint>
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

}  // namespace lmdj::domain
