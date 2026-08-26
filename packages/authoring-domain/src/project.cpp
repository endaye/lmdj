#include <lmdj/domain/project.hpp>

#include <algorithm>
#include <map>
#include <tuple>
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
      ProjectContract::v3,
      std::move(id),
      0,
      bpm,
      true,
      50,
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

std::uint32_t pattern_length_ticks(std::uint8_t bars) noexcept {
  return static_cast<std::uint32_t>(bars) * kBarTicks4x4;
}

std::uint32_t quantize_onset_tick(
    std::uint64_t raw_tick,
    std::uint32_t loop_length_ticks,
    bool quantize_enabled,
    std::uint8_t swing_percent) noexcept {
  if (loop_length_ticks == 0) {
    return 0;
  }
  const auto loop_tick = static_cast<std::uint32_t>(
      raw_tick % loop_length_ticks);
  if (!quantize_enabled) {
    return loop_tick;
  }

  const auto grid_index =
      (loop_tick + (kSixteenthTicks / 2U) - 1U) / kSixteenthTicks;
  auto quantized = (grid_index * kSixteenthTicks) % loop_length_ticks;
  if (quantized == 0 || (grid_index % 2U) == 0U) {
    return quantized;
  }

  const auto bounded_swing = std::clamp(
      swing_percent, kSwingPercentMin, kSwingPercentMax);
  const auto pair_start = (grid_index - 1U) * kSixteenthTicks;
  quantized = pair_start +
              ((2U * kSixteenthTicks * bounded_swing + 50U) / 100U);
  return quantized % loop_length_ticks;
}

std::uint32_t normalize_duration_tick(
    std::uint64_t raw_attack_tick,
    std::uint64_t raw_release_tick,
    std::uint32_t onset_tick,
    std::uint32_t loop_length_ticks) noexcept {
  if (loop_length_ticks == 0 || onset_tick >= loop_length_ticks) {
    return 0;
  }
  const auto remainder = loop_length_ticks - onset_tick;
  const auto raw_duration = raw_release_tick > raw_attack_tick
                                ? raw_release_tick - raw_attack_tick
                                : 1U;
  return static_cast<std::uint32_t>(
      std::clamp<std::uint64_t>(raw_duration, 1U, remainder));
}

std::vector<PatternEvent> merge_pattern_events(
    const std::vector<PatternEvent>& stored,
    const std::vector<PatternEvent>& incoming) {
  using EventKey = std::tuple<std::uint8_t, std::uint8_t, std::uint32_t>;
  std::map<EventKey, PatternEvent> by_key;
  const auto insert_or_replace = [&by_key](const PatternEvent& event) {
    by_key.insert_or_assign(
        EventKey{event.slot.bank, event.slot.pad, event.onset_tick}, event);
  };
  for (const auto& event : stored) {
    insert_or_replace(event);
  }
  for (const auto& event : incoming) {
    insert_or_replace(event);
  }

  std::vector<PatternEvent> merged;
  merged.reserve(by_key.size());
  for (const auto& [key, event] : by_key) {
    (void)key;
    merged.push_back(event);
  }
  std::ranges::sort(
      merged,
      {},
      [](const PatternEvent& event) {
        return std::tuple{
            event.onset_tick,
            event.slot.bank,
            event.slot.pad,
            event.duration_tick,
            event.velocity,
        };
      });
  return merged;
}

}  // namespace lmdj::domain
