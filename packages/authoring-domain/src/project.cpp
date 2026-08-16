#include <lmdj/domain/project.hpp>

#include <utility>

namespace lmdj::domain {
namespace {

bool is_lower_hex(char value) noexcept {
  return (value >= '0' && value <= '9') ||
         (value >= 'a' && value <= 'f');
}

}  // namespace

foundation::Result<ProjectState> create_project(
    foundation::ProjectId id,
    std::uint16_t bpm) {
  if (!is_valid_uuid(id.value())) {
    return foundation::Result<ProjectState>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "project id must be a lowercase UUID",
        });
  }
  if (bpm < 40 || bpm > 240) {
    return foundation::Result<ProjectState>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "project BPM must be between 40 and 240",
            {{"bpm", bpm}},
        });
  }

  ProjectState state{
      ProjectContract::v1,
      std::move(id),
      0,
      bpm,
      {},
      {},
      {},
      {},
  };
  for (std::uint8_t bank = 0; bank < state.banks.size(); ++bank) {
    for (std::uint8_t pad = 0; pad < state.banks.at(bank).size(); ++pad) {
      state.banks.at(bank).at(pad) =
          PadSlot{PadSlotId{bank, pad}, std::nullopt, PadPlayback{}};
    }
  }
  return foundation::Result<ProjectState>::success(std::move(state));
}

bool is_valid_uuid(std::string_view value) noexcept {
  if (value.size() != 36 || value[8] != '-' || value[13] != '-' ||
      value[18] != '-' || value[23] != '-') {
    return false;
  }
  for (std::size_t index = 0; index < value.size(); ++index) {
    if (index == 8 || index == 13 || index == 18 || index == 23) {
      continue;
    }
    if (!is_lower_hex(value[index])) {
      return false;
    }
  }
  return value[14] >= '1' && value[14] <= '5' &&
         (value[19] == '8' || value[19] == '9' ||
          value[19] == 'a' || value[19] == 'b');
}

bool is_valid_slot(PadSlotId slot) noexcept {
  return slot.bank < 4 && slot.pad < 16;
}

std::optional<Asset> resolve_slot_asset(
    const ProjectState& state,
    PadSlotId slot) {
  if (!is_valid_slot(slot)) {
    return std::nullopt;
  }
  const auto& asset_id = state.banks.at(slot.bank).at(slot.pad).asset_id;
  if (!asset_id.has_value()) {
    return std::nullopt;
  }
  const auto asset = state.assets.find(*asset_id);
  if (asset == state.assets.end()) {
    return std::nullopt;
  }
  return asset->second;
}

}  // namespace lmdj::domain
