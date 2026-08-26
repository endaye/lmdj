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

enum class ProjectContract : std::uint8_t {
  v1,
  v2,
  v3,
};

inline constexpr std::uint32_t kPpq = 960;
inline constexpr std::uint32_t kSixteenthTicks = 240;
inline constexpr std::uint32_t kBarTicks4x4 = 3840;
inline constexpr std::uint8_t kSwingPercentMin = 50;
inline constexpr std::uint8_t kSwingPercentMax = 75;

enum class TriggerMode : std::uint8_t {
  one_shot,
  gate,
  loop_gate,
  loop_toggle,
};

struct PadPlayback {
  std::uint64_t trim_start_frame{0};
  std::optional<std::uint64_t> trim_end_frame;
  TriggerMode trigger_mode{TriggerMode::one_shot};
  std::int32_t gain_millidb{0};
  bool muted{false};

  bool operator==(const PadPlayback&) const = default;
};

struct PadSlotId {
  std::uint8_t bank;
  std::uint8_t pad;

  auto operator<=>(const PadSlotId&) const = default;
};

struct PadSlot {
  PadSlotId id;
  std::optional<foundation::AssetId> asset_id;
  PadPlayback playback;

  bool operator==(const PadSlot&) const = default;
};

struct Asset {
  foundation::AssetId id;
  foundation::ArtifactRef artifact;

  bool operator==(const Asset&) const = default;
};

struct PatternEvent {
  PadSlotId slot;
  std::uint32_t onset_tick;
  std::uint32_t duration_tick;
  std::uint8_t velocity;

  PatternEvent(
      PadSlotId slot_value,
      std::uint32_t onset_tick_value,
      std::uint32_t duration_tick_value,
      std::uint8_t velocity_value) noexcept
      : slot(slot_value),
        onset_tick(onset_tick_value),
        duration_tick(duration_tick_value),
        velocity(velocity_value) {}

  bool operator==(const PatternEvent& other) const noexcept {
    return slot == other.slot && onset_tick == other.onset_tick &&
           duration_tick == other.duration_tick && velocity == other.velocity;
  }
};

struct Pattern {
  foundation::PatternId id;
  std::uint8_t bars;
  std::vector<PatternEvent> events;

  bool operator==(const Pattern&) const = default;
};

struct ProjectState {
  ProjectContract contract;
  foundation::ProjectId id;
  std::uint64_t revision;
  std::uint16_t bpm;
  bool quantize_enabled;
  std::uint8_t swing_percent;
  std::array<std::array<PadSlot, 16>, 4> banks;
  std::map<foundation::AssetId, Asset> assets;
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

std::uint32_t pattern_length_ticks(std::uint8_t bars) noexcept;
std::uint32_t quantize_onset_tick(
    std::uint64_t raw_tick,
    std::uint32_t loop_length_ticks,
    bool quantize_enabled,
    std::uint8_t swing_percent) noexcept;
std::uint32_t normalize_duration_tick(
    std::uint64_t raw_attack_tick,
    std::uint64_t raw_release_tick,
    std::uint32_t onset_tick,
    std::uint32_t loop_length_ticks) noexcept;
std::vector<PatternEvent> merge_pattern_events(
    const std::vector<PatternEvent>& stored,
    const std::vector<PatternEvent>& incoming);

}  // namespace lmdj::domain
