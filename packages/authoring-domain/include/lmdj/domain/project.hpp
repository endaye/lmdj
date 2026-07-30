#pragma once

#include <array>
#include <compare>
#include <cstdint>
#include <map>
#include <optional>
#include <string_view>
#include <vector>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::domain {

struct PadSlotId {
  std::uint8_t bank;
  std::uint8_t pad;

  auto operator<=>(const PadSlotId&) const = default;
};

struct PadSlot {
  PadSlotId id;
  std::optional<foundation::AssetId> asset_id;

  bool operator==(const PadSlot&) const = default;
};

struct Asset {
  foundation::AssetId id;
  foundation::ArtifactRef artifact;

  bool operator==(const Asset&) const = default;
};

struct PatternEvent {
  PadSlotId slot;
  std::uint32_t step;
  std::uint8_t velocity;

  bool operator==(const PatternEvent&) const = default;
};

struct Pattern {
  foundation::PatternId id;
  std::uint8_t bars;
  std::vector<PatternEvent> events;

  bool operator==(const Pattern&) const = default;
};

struct RawTakeEvent {
  PadSlotId slot;
  std::uint32_t frame_offset;
  std::uint8_t velocity;

  bool operator==(const RawTakeEvent&) const = default;
};

struct RawTake {
  foundation::TakeId id;
  std::uint32_t sample_rate;
  std::vector<RawTakeEvent> events;

  bool operator==(const RawTake&) const = default;
};

struct ProjectState {
  foundation::ProjectId id;
  std::uint64_t revision;
  std::uint16_t bpm;
  std::array<std::array<PadSlot, 16>, 4> banks;
  std::map<foundation::AssetId, Asset> assets;
  std::map<foundation::TakeId, RawTake> takes;
  std::map<foundation::PatternId, Pattern> patterns;

  bool operator==(const ProjectState&) const = default;
};

foundation::Result<ProjectState> create_project(
    foundation::ProjectId id,
    std::uint16_t bpm);

bool is_valid_uuid(std::string_view value) noexcept;
bool is_valid_slot(PadSlotId slot) noexcept;
std::optional<Asset> resolve_slot_asset(
    const ProjectState& state,
    PadSlotId slot);

}  // namespace lmdj::domain
