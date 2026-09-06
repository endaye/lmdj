#include <lmdj/domain/project.hpp>

#include <algorithm>
#include <array>
#include <map>
#include <set>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>
#include <variant>

#include <lmdj/foundation/soundset_manifest.hpp>

namespace lmdj::domain {
namespace {

bool is_lower_hex(char value) noexcept {
  return (value >= '0' && value <= '9') ||
         (value >= 'a' && value <= 'f');
}

foundation::Result<PerformanceEvent> invalid_performance_event(
    std::string_view message) {
  return foundation::Result<PerformanceEvent>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

foundation::Result<void> invalid_performance(std::string_view message) {
  return foundation::Result<void>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

foundation::Result<void> invalid_asset_lineage(std::string_view message) {
  return foundation::Result<void>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

foundation::Result<AssetLineage> invalid_asset_lineage_value(
    std::string_view message) {
  return foundation::Result<AssetLineage>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

bool exact_object_keys(
    const nlohmann::json& input,
    std::initializer_list<std::string_view> keys) {
  if (!input.is_object() || input.size() != keys.size()) {
    return false;
  }
  return std::ranges::all_of(
      keys,
      [&input](std::string_view key) {
        return input.contains(key);
      });
}

std::optional<std::uint64_t> unsigned_value(
    const nlohmann::json& input) noexcept {
  try {
    if (input.is_number_unsigned()) {
      return input.get<std::uint64_t>();
    }
    if (input.is_number_integer()) {
      const auto value = input.get<std::int64_t>();
      if (value >= 0) {
        return static_cast<std::uint64_t>(value);
      }
    }
  } catch (const std::exception&) {
  }
  return std::nullopt;
}

std::optional<std::uint64_t> bounded_unsigned(
    const nlohmann::json& input,
    std::uint64_t maximum) noexcept {
  const auto value = unsigned_value(input);
  if (!value.has_value() || *value > maximum) {
    return std::nullopt;
  }
  return value;
}

bool valid_fx(PerformanceFx fx) noexcept {
  return static_cast<std::uint8_t>(fx) < kFxCount;
}

bool valid_sha256(std::string_view value) noexcept {
  if (value.size() != 64) {
    return false;
  }
  return std::ranges::all_of(value, is_lower_hex);
}

// The Sound Set Contract pins `set_version` to the same three-part SemVer
// pattern the Project Schema uses, so a Lineage that survives the Schema also
// survives the domain and vice versa.
bool valid_soundset_semver(std::string_view value) noexcept {
  std::size_t index = 0;
  for (int part = 0; part < 3; ++part) {
    if (part > 0) {
      if (index >= value.size() || value[index] != '.') {
        return false;
      }
      ++index;
    }
    const std::size_t start = index;
    while (index < value.size() && value[index] >= '0' && value[index] <= '9') {
      ++index;
    }
    const std::size_t digits = index - start;
    if (digits == 0 || (digits > 1 && value[start] == '0')) {
      return false;
    }
  }
  return index == value.size();
}

std::optional<std::size_t> utf8_code_point_count(
    std::string_view value) noexcept {
  std::size_t count = 0;
  for (std::size_t index = 0; index < value.size();) {
    const auto first = static_cast<unsigned char>(value[index]);
    std::size_t length = 0;
    std::uint32_t code_point = 0;
    if (first <= 0x7fU) {
      length = 1;
      code_point = first;
    } else if ((first & 0xe0U) == 0xc0U) {
      length = 2;
      code_point = first & 0x1fU;
    } else if ((first & 0xf0U) == 0xe0U) {
      length = 3;
      code_point = first & 0x0fU;
    } else if ((first & 0xf8U) == 0xf0U) {
      length = 4;
      code_point = first & 0x07U;
    } else {
      return std::nullopt;
    }
    if (index + length > value.size()) {
      return std::nullopt;
    }
    for (std::size_t offset = 1; offset < length; ++offset) {
      const auto continuation =
          static_cast<unsigned char>(value[index + offset]);
      if ((continuation & 0xc0U) != 0x80U) {
        return std::nullopt;
      }
      code_point = (code_point << 6U) | (continuation & 0x3fU);
    }
    const bool overlong =
        (length == 2 && code_point < 0x80U) ||
        (length == 3 && code_point < 0x800U) ||
        (length == 4 && code_point < 0x10000U);
    if (overlong || code_point > 0x10ffffU ||
        (code_point >= 0xd800U && code_point <= 0xdfffU)) {
      return std::nullopt;
    }
    index += length;
    ++count;
  }
  return count;
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

foundation::Result<void> validate_pattern_slots(
    const ProjectState& state) {
  std::set<foundation::PatternId> occupied;
  for (const auto& pattern_id : state.pattern_slots) {
    if (!pattern_id.has_value()) {
      continue;
    }
    if (!is_valid_uuid(pattern_id->value()) ||
        !state.patterns.contains(*pattern_id)) {
      return foundation::Result<void>::failure(
          foundation::Error{
              foundation::ErrorCode::invalid_argument,
              "Pattern slot references an invalid or missing Pattern",
          });
    }
    if (!occupied.insert(*pattern_id).second) {
      return foundation::Result<void>::failure(
          foundation::Error{
              foundation::ErrorCode::invalid_argument,
              "Pattern occupies more than one Pattern slot",
          });
    }
  }
  return foundation::Result<void>::success();
}

PerformanceEventKind performance_event_kind(
    const PerformanceEvent& event) noexcept {
  return static_cast<PerformanceEventKind>(event.payload.index());
}

std::uint64_t performance_event_tick(
    const PerformanceEvent& event) noexcept {
  return std::visit(
      [](const auto& payload) -> std::uint64_t {
        using Event = std::decay_t<decltype(payload)>;
        if constexpr (std::is_same_v<Event, PadHitPerformanceEvent>) {
          return payload.onset_tick;
        } else if constexpr (
            std::is_same_v<Event, PatternLaunchPerformanceEvent>) {
          return payload.effective_tick;
        } else {
          return payload.tick;
        }
      },
      event.payload);
}

std::uint8_t performance_event_fx_or_slot(
    const PerformanceEvent& event) noexcept {
  return std::visit(
      [](const auto& payload) -> std::uint8_t {
        using Event = std::decay_t<decltype(payload)>;
        if constexpr (std::is_same_v<Event, PadHitPerformanceEvent>) {
          return payload.slot;
        } else if constexpr (
            std::is_same_v<Event, PatternLaunchPerformanceEvent>) {
          return payload.pattern_slot;
        } else if constexpr (
            std::is_same_v<Event, FxEngagePerformanceEvent> ||
            std::is_same_v<Event, FxMovePerformanceEvent> ||
            std::is_same_v<Event, FxReleasePerformanceEvent>) {
          return static_cast<std::uint8_t>(payload.fx);
        } else {
          return 0;
        }
      },
      event.payload);
}

std::vector<PerformanceEvent> canonical_performance_events(
    const std::vector<PerformanceEvent>& events) {
  auto ordered = events;
  std::ranges::stable_sort(
      ordered,
      {},
      [](const PerformanceEvent& event) {
        return std::tuple{
            performance_event_tick(event),
            static_cast<std::uint8_t>(performance_event_kind(event)),
            performance_event_fx_or_slot(event),
        };
      });
  return ordered;
}

foundation::Result<void> validate_performance_events(
    const std::vector<PerformanceEvent>& events) {
  std::array<bool, kFxCount> engaged{};
  bool hold_enabled = false;
  for (const auto& event : canonical_performance_events(events)) {
    const auto valid = std::visit(
        [&engaged, &hold_enabled](const auto& payload)
            -> foundation::Result<void> {
          using Event = std::decay_t<decltype(payload)>;
          if constexpr (std::is_same_v<Event, PadHitPerformanceEvent>) {
            if (payload.slot > kPerformancePadSlotMax ||
                payload.duration_tick == 0 || payload.velocity == 0 ||
                payload.velocity > 127) {
              return invalid_performance("pad_hit event is invalid");
            }
          } else if constexpr (
              std::is_same_v<Event, PatternLaunchPerformanceEvent>) {
            if (payload.pattern_slot < kPatternSlotMin ||
                payload.pattern_slot > kPatternSlotMax) {
              return invalid_performance(
                  "pattern_launch event is invalid");
            }
          } else if constexpr (
              std::is_same_v<Event, FxEngagePerformanceEvent>) {
            if (!valid_fx(payload.fx) || payload.value < kFxValueMin ||
                payload.value > kFxValueMax) {
              return invalid_performance("fx_engage event is invalid");
            }
            auto& active = engaged.at(static_cast<std::uint8_t>(payload.fx));
            if (active) {
              return invalid_performance(
                  "fx_engage requires a disengaged effect");
            }
            active = true;
          } else if constexpr (
              std::is_same_v<Event, FxMovePerformanceEvent>) {
            if (!valid_fx(payload.fx) || payload.value < kFxValueMin ||
                payload.value > kFxValueMax) {
              return invalid_performance("fx_move event is invalid");
            }
            if (!engaged.at(static_cast<std::uint8_t>(payload.fx))) {
              return invalid_performance(
                  "fx_move requires a matching open fx_engage");
            }
          } else if constexpr (
              std::is_same_v<Event, FxReleasePerformanceEvent>) {
            if (!valid_fx(payload.fx)) {
              return invalid_performance("fx_release event is invalid");
            }
            auto& active = engaged.at(static_cast<std::uint8_t>(payload.fx));
            if (!active) {
              return invalid_performance(
                  "fx_release requires a matching open fx_engage");
            }
            active = false;
          } else if constexpr (
              std::is_same_v<Event, HoldOnPerformanceEvent>) {
            if (hold_enabled) {
              return invalid_performance(
                  "hold_on requires HOLD to be off");
            }
            hold_enabled = true;
          } else {
            if (!hold_enabled) {
              return invalid_performance(
                  "hold_off requires HOLD to be on");
            }
            hold_enabled = false;
          }
          return foundation::Result<void>::success();
        },
        event.payload);
    if (!valid.has_value()) {
      return valid;
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> validate_performance(
    const Performance& performance) {
  if (!is_valid_uuid(performance.id.value())) {
    return invalid_performance(
        "performance id must be a lowercase UUID");
  }
  const auto name_length = utf8_code_point_count(performance.name);
  if (!name_length.has_value() || *name_length == 0 ||
      *name_length > kPerformanceNameMax) {
    return invalid_performance(
        "performance name must contain 1 to 64 UTF-8 code points");
  }
  if (performance.created_bpm < 40 || performance.created_bpm > 240) {
    return invalid_performance(
        "performance created BPM must be between 40 and 240");
  }
  if (performance.recording_artifact.has_value() &&
      (!valid_sha256(performance.recording_artifact->sha256) ||
       performance.recording_artifact->media_type.empty())) {
    return invalid_performance(
        "performance recording artifact is invalid");
  }
  if (performance.events != canonical_performance_events(performance.events)) {
    return invalid_performance(
        "performance events must use canonical ordering");
  }
  return validate_performance_events(performance.events);
}

AssetLineageSourceKind asset_lineage_source_kind(
    const AssetLineage& lineage) noexcept {
  return std::holds_alternative<SoundSetLineageSource>(lineage.source)
             ? AssetLineageSourceKind::soundset
             : AssetLineageSourceKind::asset_artifact;
}

AssetLineageDerivationKind asset_lineage_derivation_kind(
    const AssetLineage& lineage) noexcept {
  return std::holds_alternative<SoundSetInstallLineageDerivation>(
             lineage.derivation)
             ? AssetLineageDerivationKind::soundset_install
             : AssetLineageDerivationKind::resample;
}

foundation::Result<void> validate_asset_lineage(
    const AssetLineage& lineage) {
  if (const auto* artifact_source =
          std::get_if<AssetArtifactLineageSource>(&lineage.source);
      artifact_source != nullptr) {
    if (!valid_sha256(artifact_source->artifact_sha256)) {
      return invalid_asset_lineage(
          "asset Lineage source digest must be lowercase SHA-256");
    }
  } else {
    const auto& soundset = std::get<SoundSetLineageSource>(lineage.source);
    if (!is_valid_uuid(soundset.set_id)) {
      return invalid_asset_lineage(
          "asset Lineage Sound Set id must be a lowercase UUID");
    }
    if (!valid_soundset_semver(soundset.set_version)) {
      return invalid_asset_lineage(
          "asset Lineage Sound Set version must be SemVer");
    }
    if (!valid_sha256(soundset.manifest_sha256) ||
        !valid_sha256(soundset.artifact_sha256)) {
      return invalid_asset_lineage(
          "asset Lineage source digest must be lowercase SHA-256");
    }
    if (soundset.slot_index >= foundation::kSoundSetSlotCount) {
      return invalid_asset_lineage(
          "asset Lineage Sound Set slot index is out of range");
    }
  }
  if (const auto* resample =
          std::get_if<ResampleLineageDerivation>(&lineage.derivation);
      resample != nullptr) {
    if (!is_valid_uuid(resample->performance_id.value())) {
      return invalid_asset_lineage(
          "asset Lineage Performance id must be a lowercase UUID");
    }
    if (resample->range.start_frame >= resample->range.end_frame) {
      return invalid_asset_lineage(
          "asset Lineage frame range must be non-empty and increasing");
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<AssetLineage> asset_lineage_from_json(
    const nlohmann::json& input) {
  try {
    if (!exact_object_keys(input, {"source", "derivation"})) {
      return invalid_asset_lineage_value(
          "asset Lineage must contain exact source and derivation objects");
    }
    const auto& source = input.at("source");
    const auto& derivation = input.at("derivation");
    if (!source.is_object() || !source.contains("kind") ||
        !source.at("kind").is_string() || !derivation.is_object() ||
        !derivation.contains("kind") || !derivation.at("kind").is_string()) {
      return invalid_asset_lineage_value(
          "asset Lineage must declare a supported source and derivation kind");
    }
    const auto source_kind = source.at("kind").get<std::string>();
    const auto derivation_kind = derivation.at("kind").get<std::string>();
    AssetLineageSource parsed_source;
    if (source_kind == "asset_artifact") {
      if (!exact_object_keys(
              source,
              {"kind", "artifact_sha256", "project_revision"}) ||
          !source.at("artifact_sha256").is_string()) {
        return invalid_asset_lineage_value(
            "asset Lineage source shape or value is invalid");
      }
      const auto project_revision =
          unsigned_value(source.at("project_revision"));
      if (!project_revision.has_value()) {
        return invalid_asset_lineage_value(
            "asset Lineage integer value is invalid");
      }
      parsed_source = AssetArtifactLineageSource{
          source.at("artifact_sha256").get<std::string>(),
          *project_revision,
      };
    } else if (source_kind == "soundset") {
      if (!exact_object_keys(
              source,
              {"kind",
               "set_id",
               "set_version",
               "manifest_sha256",
               "slot_index",
               "artifact_sha256"}) ||
          !source.at("set_id").is_string() ||
          !source.at("set_version").is_string() ||
          !source.at("manifest_sha256").is_string() ||
          !source.at("artifact_sha256").is_string()) {
        return invalid_asset_lineage_value(
            "asset Lineage source shape or value is invalid");
      }
      const auto slot_index = bounded_unsigned(
          source.at("slot_index"),
          static_cast<std::uint64_t>(foundation::kSoundSetSlotCount) - 1);
      if (!slot_index.has_value()) {
        return invalid_asset_lineage_value(
            "asset Lineage integer value is invalid");
      }
      parsed_source = SoundSetLineageSource{
          source.at("set_id").get<std::string>(),
          source.at("set_version").get<std::string>(),
          source.at("manifest_sha256").get<std::string>(),
          static_cast<std::uint8_t>(*slot_index),
          source.at("artifact_sha256").get<std::string>(),
      };
    } else {
      return invalid_asset_lineage_value(
          "asset Lineage source shape or value is invalid");
    }
    AssetLineageDerivation parsed_derivation{
        SoundSetInstallLineageDerivation{}};
    if (derivation_kind == "resample") {
      if (!exact_object_keys(
              derivation,
              {"kind", "range", "performance_id"}) ||
          !derivation.at("performance_id").is_string()) {
        return invalid_asset_lineage_value(
            "asset Lineage derivation shape or value is invalid");
      }
      const auto& range = derivation.at("range");
      if (!exact_object_keys(range, {"start_frame", "end_frame"})) {
        return invalid_asset_lineage_value(
            "asset Lineage range shape is invalid");
      }
      const auto start_frame = unsigned_value(range.at("start_frame"));
      const auto end_frame = unsigned_value(range.at("end_frame"));
      if (!start_frame.has_value() || !end_frame.has_value()) {
        return invalid_asset_lineage_value(
            "asset Lineage integer value is invalid");
      }
      parsed_derivation = ResampleLineageDerivation{
          {*start_frame, *end_frame},
          PerformanceId{derivation.at("performance_id").get<std::string>()},
      };
    } else if (derivation_kind == "soundset_install") {
      if (!exact_object_keys(derivation, {"kind"})) {
        return invalid_asset_lineage_value(
            "asset Lineage derivation shape or value is invalid");
      }
      parsed_derivation = SoundSetInstallLineageDerivation{};
    } else {
      return invalid_asset_lineage_value(
          "asset Lineage derivation shape or value is invalid");
    }
    AssetLineage lineage{
        std::move(parsed_source),
        std::move(parsed_derivation),
    };
    const auto valid = validate_asset_lineage(lineage);
    if (!valid.has_value()) {
      return foundation::Result<AssetLineage>::failure(valid.error());
    }
    return foundation::Result<AssetLineage>::success(std::move(lineage));
  } catch (const std::exception&) {
    return invalid_asset_lineage_value(
        "asset Lineage shape or value is invalid");
  }
}

nlohmann::json asset_lineage_json(const AssetLineage& lineage) {
  nlohmann::json source;
  if (const auto* artifact_source =
          std::get_if<AssetArtifactLineageSource>(&lineage.source);
      artifact_source != nullptr) {
    source = {
        {"kind", "asset_artifact"},
        {"artifact_sha256", artifact_source->artifact_sha256},
        {"project_revision", artifact_source->project_revision},
    };
  } else {
    const auto& soundset = std::get<SoundSetLineageSource>(lineage.source);
    source = {
        {"kind", "soundset"},
        {"set_id", soundset.set_id},
        {"set_version", soundset.set_version},
        {"manifest_sha256", soundset.manifest_sha256},
        {"slot_index", soundset.slot_index},
        {"artifact_sha256", soundset.artifact_sha256},
    };
  }
  nlohmann::json derivation;
  if (const auto* resample =
          std::get_if<ResampleLineageDerivation>(&lineage.derivation);
      resample != nullptr) {
    derivation = {
        {"kind", "resample"},
        {"range",
         {{"start_frame", resample->range.start_frame},
          {"end_frame", resample->range.end_frame}}},
        {"performance_id", resample->performance_id.value()},
    };
  } else {
    derivation = nlohmann::json::object({{"kind", "soundset_install"}});
  }
  return {
      {"source", std::move(source)},
      {"derivation", std::move(derivation)},
  };
}

foundation::Result<PerformanceEvent> performance_event_from_json(
    const nlohmann::json& input) {
  try {
    if (!input.is_object() || !input.contains("kind") ||
        !input.at("kind").is_string()) {
      return invalid_performance_event(
          "performance event must declare a supported kind");
    }
    const auto kind = input.at("kind").get<std::string>();
    if (kind == "pad_hit" &&
        exact_object_keys(
            input,
            {"kind", "slot", "onset_tick", "duration_tick", "velocity"})) {
      const auto slot = bounded_unsigned(
          input.at("slot"), kPerformancePadSlotMax);
      const auto onset_tick = unsigned_value(input.at("onset_tick"));
      const auto duration_tick = unsigned_value(input.at("duration_tick"));
      const auto velocity = bounded_unsigned(input.at("velocity"), 127);
      if (slot.has_value() && onset_tick.has_value() &&
          duration_tick.has_value() && *duration_tick > 0 &&
          velocity.has_value() && *velocity > 0) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{PadHitPerformanceEvent{
                static_cast<std::uint8_t>(*slot),
                *onset_tick,
                *duration_tick,
                static_cast<std::uint8_t>(*velocity),
            }});
      }
    } else if (
        kind == "pattern_launch" &&
        exact_object_keys(
            input, {"kind", "pattern_slot", "effective_tick"})) {
      const auto slot = bounded_unsigned(
          input.at("pattern_slot"), kPatternSlotMax);
      const auto tick = unsigned_value(input.at("effective_tick"));
      if (slot.has_value() && tick.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{PatternLaunchPerformanceEvent{
                static_cast<std::uint8_t>(*slot), *tick}});
      }
    } else if (
        (kind == "fx_engage" || kind == "fx_move") &&
        exact_object_keys(input, {"kind", "fx", "value", "tick"})) {
      const auto fx = bounded_unsigned(input.at("fx"), kFxCount - 1);
      const auto value = bounded_unsigned(input.at("value"), kFxValueMax);
      const auto tick = unsigned_value(input.at("tick"));
      if (fx.has_value() && value.has_value() && tick.has_value()) {
        const auto typed_fx = static_cast<PerformanceFx>(*fx);
        if (kind == "fx_engage") {
          return foundation::Result<PerformanceEvent>::success(
              PerformanceEvent{FxEngagePerformanceEvent{
                  typed_fx, static_cast<std::uint16_t>(*value), *tick}});
        }
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{FxMovePerformanceEvent{
                typed_fx, static_cast<std::uint16_t>(*value), *tick}});
      }
    } else if (
        kind == "fx_release" &&
        exact_object_keys(input, {"kind", "fx", "tick"})) {
      const auto fx = bounded_unsigned(input.at("fx"), kFxCount - 1);
      const auto tick = unsigned_value(input.at("tick"));
      if (fx.has_value() && tick.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{FxReleasePerformanceEvent{
                static_cast<PerformanceFx>(*fx), *tick}});
      }
    } else if (
        kind == "hold_on" &&
        exact_object_keys(input, {"kind", "tick"})) {
      const auto tick = unsigned_value(input.at("tick"));
      if (tick.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{HoldOnPerformanceEvent{*tick}});
      }
    } else if (
        kind == "hold_off" &&
        exact_object_keys(input, {"kind", "tick"})) {
      const auto tick = unsigned_value(input.at("tick"));
      if (tick.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{HoldOffPerformanceEvent{*tick}});
      }
    }
  } catch (const std::exception&) {
  }
  return invalid_performance_event(
      "performance event shape or value is invalid");
}

nlohmann::json performance_event_json(const PerformanceEvent& event) {
  return std::visit(
      [](const auto& payload) -> nlohmann::json {
        using Event = std::decay_t<decltype(payload)>;
        if constexpr (std::is_same_v<Event, PadHitPerformanceEvent>) {
          return {
              {"duration_tick", payload.duration_tick},
              {"kind", "pad_hit"},
              {"onset_tick", payload.onset_tick},
              {"slot", payload.slot},
              {"velocity", payload.velocity},
          };
        } else if constexpr (
            std::is_same_v<Event, PatternLaunchPerformanceEvent>) {
          return {
              {"effective_tick", payload.effective_tick},
              {"kind", "pattern_launch"},
              {"pattern_slot", payload.pattern_slot},
          };
        } else if constexpr (
            std::is_same_v<Event, FxEngagePerformanceEvent>) {
          return {
              {"fx", static_cast<std::uint8_t>(payload.fx)},
              {"kind", "fx_engage"},
              {"tick", payload.tick},
              {"value", payload.value},
          };
        } else if constexpr (
            std::is_same_v<Event, FxMovePerformanceEvent>) {
          return {
              {"fx", static_cast<std::uint8_t>(payload.fx)},
              {"kind", "fx_move"},
              {"tick", payload.tick},
              {"value", payload.value},
          };
        } else if constexpr (
            std::is_same_v<Event, FxReleasePerformanceEvent>) {
          return {
              {"fx", static_cast<std::uint8_t>(payload.fx)},
              {"kind", "fx_release"},
              {"tick", payload.tick},
          };
        } else if constexpr (
            std::is_same_v<Event, HoldOnPerformanceEvent>) {
          return {{"kind", "hold_on"}, {"tick", payload.tick}};
        } else {
          return {{"kind", "hold_off"}, {"tick", payload.tick}};
        }
      },
      event.payload);
}

}  // namespace lmdj::domain
