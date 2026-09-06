#pragma once

#include <array>
#include <compare>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::domain {

enum class ProjectContract : std::uint8_t {
  v1,
  v2,
  v3,
  v4,
};

inline constexpr std::uint32_t kPpq = 960;
inline constexpr std::uint32_t kSixteenthTicks = 240;
inline constexpr std::uint32_t kBarTicks4x4 = 3840;
inline constexpr std::uint8_t kSwingPercentMin = 50;
inline constexpr std::uint8_t kSwingPercentMax = 75;
inline constexpr std::size_t kPerformanceNameMax = 64;
inline constexpr std::uint8_t kPerformancePadSlotMax = 63;
inline constexpr std::size_t kBankPadCount = 16;
inline constexpr std::size_t kPatternSlotCount = 16;
inline constexpr std::uint8_t kPatternSlotMin = 0;
inline constexpr std::uint8_t kPatternSlotMax = 15;
inline constexpr std::uint16_t kFxValueMin = 0;
inline constexpr std::uint16_t kFxValueMax = 1000;
inline constexpr std::uint8_t kFxCount = 8;

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

struct PerformanceIdTag;
using PerformanceId = foundation::StrongId<PerformanceIdTag>;

struct AssetArtifactLineageSource {
  std::string artifact_sha256;
  std::uint64_t project_revision{};

  bool operator==(const AssetArtifactLineageSource&) const = default;
};

struct ResampleFrameRange {
  std::uint64_t start_frame{};
  std::uint64_t end_frame{};

  bool operator==(const ResampleFrameRange&) const = default;
};

struct ResampleLineageDerivation {
  ResampleFrameRange range;
  PerformanceId performance_id;

  bool operator==(const ResampleLineageDerivation&) const = default;
};

// S11-D9: an installed Sound Set slot records the Set it came from on the
// existing Asset Lineage carrier. The Set Store bytes stay unchanged and the
// slot index is the Set slot, never the target Pad Slot of a later edit.
struct SoundSetLineageSource {
  std::string set_id;
  std::string set_version;
  std::string manifest_sha256;
  std::uint8_t slot_index{};
  std::string artifact_sha256;

  bool operator==(const SoundSetLineageSource&) const = default;
};

struct SoundSetInstallLineageDerivation {
  bool operator==(const SoundSetInstallLineageDerivation&) const = default;
};

enum class AssetLineageSourceKind : std::uint8_t {
  asset_artifact,
  soundset,
};

enum class AssetLineageDerivationKind : std::uint8_t {
  resample,
  soundset_install,
};

using AssetLineageSource =
    std::variant<AssetArtifactLineageSource, SoundSetLineageSource>;

using AssetLineageDerivation =
    std::variant<ResampleLineageDerivation, SoundSetInstallLineageDerivation>;

struct AssetLineage {
  AssetLineageSource source;
  AssetLineageDerivation derivation;

  bool operator==(const AssetLineage&) const = default;
};

struct Asset {
  foundation::AssetId id;
  foundation::ArtifactRef artifact;
  std::optional<AssetLineage> lineage;

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

enum class PerformanceEventKind : std::uint8_t {
  pad_hit,
  pattern_launch,
  fx_engage,
  fx_move,
  fx_release,
  hold_on,
  hold_off,
};

enum class PerformanceFx : std::uint8_t {
  filter,
  delay,
  reverb,
  stutter,
  gate,
  reverse,
  crush,
  cutter,
};

struct PadHitPerformanceEvent {
  std::uint8_t slot;
  std::uint64_t onset_tick;
  std::uint64_t duration_tick;
  std::uint8_t velocity;

  bool operator==(const PadHitPerformanceEvent&) const = default;
};

struct PatternLaunchPerformanceEvent {
  std::uint8_t pattern_slot;
  std::uint64_t effective_tick;

  bool operator==(const PatternLaunchPerformanceEvent&) const = default;
};

struct FxEngagePerformanceEvent {
  PerformanceFx fx;
  std::uint16_t value;
  std::uint64_t tick;

  bool operator==(const FxEngagePerformanceEvent&) const = default;
};

struct FxMovePerformanceEvent {
  PerformanceFx fx;
  std::uint16_t value;
  std::uint64_t tick;

  bool operator==(const FxMovePerformanceEvent&) const = default;
};

struct FxReleasePerformanceEvent {
  PerformanceFx fx;
  std::uint64_t tick;

  bool operator==(const FxReleasePerformanceEvent&) const = default;
};

struct HoldOnPerformanceEvent {
  std::uint64_t tick;

  bool operator==(const HoldOnPerformanceEvent&) const = default;
};

struct HoldOffPerformanceEvent {
  std::uint64_t tick;

  bool operator==(const HoldOffPerformanceEvent&) const = default;
};

using PerformanceEventPayload = std::variant<
    PadHitPerformanceEvent,
    PatternLaunchPerformanceEvent,
    FxEngagePerformanceEvent,
    FxMovePerformanceEvent,
    FxReleasePerformanceEvent,
    HoldOnPerformanceEvent,
    HoldOffPerformanceEvent>;

struct PerformanceEvent {
  PerformanceEventPayload payload;

  bool operator==(const PerformanceEvent&) const = default;
};

struct Performance {
  PerformanceId id;
  std::string name;
  std::uint16_t created_bpm;
  std::uint64_t recording_revision{};
  std::optional<foundation::ArtifactRef> recording_artifact;
  std::vector<PerformanceEvent> events;

  bool operator==(const Performance&) const = default;
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
  std::map<PerformanceId, Performance> performances;
  std::array<std::optional<foundation::PatternId>, kPatternSlotCount>
      pattern_slots{};

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

PerformanceEventKind performance_event_kind(
    const PerformanceEvent& event) noexcept;
std::uint64_t performance_event_tick(
    const PerformanceEvent& event) noexcept;
std::uint8_t performance_event_fx_or_slot(
    const PerformanceEvent& event) noexcept;
std::vector<PerformanceEvent> canonical_performance_events(
    const std::vector<PerformanceEvent>& events);
foundation::Result<void> validate_performance_events(
    const std::vector<PerformanceEvent>& events);
foundation::Result<void> validate_performance(
    const Performance& performance);
AssetLineageSourceKind asset_lineage_source_kind(
    const AssetLineage& lineage) noexcept;
AssetLineageDerivationKind asset_lineage_derivation_kind(
    const AssetLineage& lineage) noexcept;
foundation::Result<void> validate_asset_lineage(
    const AssetLineage& lineage);
foundation::Result<AssetLineage> asset_lineage_from_json(
    const nlohmann::json& input);
nlohmann::json asset_lineage_json(const AssetLineage& lineage);
foundation::Result<void> validate_pattern_slots(
    const ProjectState& state);
foundation::Result<PerformanceEvent> performance_event_from_json(
    const nlohmann::json& input);
nlohmann::json performance_event_json(const PerformanceEvent& event);

foundation::Result<nlohmann::json> migrate_project_v3_to_v4(
    const nlohmann::json& project_v3);

}  // namespace lmdj::domain
