#include <lmdj/project_io/project_store.hpp>

#include <algorithm>
#include <array>
#include <charconv>
#include <cctype>
#include <chrono>
#include <initializer_list>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <span>
#include <stdexcept>
#include <string_view>
#include <system_error>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "publish_token.hpp"
#include "testing_hooks.hpp"

namespace lmdj::project_io {
namespace {
// Every JSON document below arrives from disk and is therefore external input.
// Deep nesting is a stack-overflow vector that a try/catch cannot contain, so
// parse through the depth-bounded Foundation entry point. These paths already
// convert exceptions into typed failures, so signalling by exception keeps the
// existing error contract intact.
template <typename Source>
nlohmann::json parse_bounded_or_throw(Source&& source) {
  auto parsed = foundation::parse_bounded_json(std::forward<Source>(source));
  if (!parsed.has_value()) {
    throw std::runtime_error(
        "JSON is malformed or exceeds the maximum container depth");
  }
  return std::move(*parsed);
}

using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint64_t kMaximumArtifactBytes = 64U * 1024U * 1024U;

using PersistedCommand = std::variant<
    domain::ImportAsset,
    domain::AssignPad,
    domain::CreatePattern,
    domain::MergePatternEvents,
    domain::UpdateSequenceSettings,
    domain::ImportAssignSample,
    domain::UpdatePadPlayback,
    domain::ResetPadPlayback>;

struct LoadedProject {
  domain::ProjectState state;
  std::map<foundation::CommandId, PersistedCommand> commands;
  std::map<foundation::CommandId, domain::CommandReceipt> receipts;
  std::map<foundation::CommandId, SequenceFlushIdentity>
      sequence_flush_identities;
  std::vector<std::string> transactions;
};

struct ArtifactStage {
  std::filesystem::path source;
  foundation::ArtifactRef artifact;
  std::span<const std::byte> bytes;
  bool byte_backed = false;
};

bool valid_sha256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(
             value.begin(),
             value.end(),
             [](unsigned char character) {
               return (character >= '0' && character <= '9') ||
                      (character >= 'a' && character <= 'f');
             });
}

Error invalid_project(
    std::string message,
    const std::filesystem::path& path,
    std::string detail = {}) {
  auto details = nlohmann::json{{"path", path.generic_string()}};
  if (!detail.empty()) {
    details["detail"] = std::move(detail);
  }
  return Error{
      ErrorCode::invalid_project,
      std::move(message),
      std::move(details),
  };
}

foundation::Result<void> validate_managed_bundle_tree(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  const auto no_symlinks = platform.validate_managed_tree(bundle);
  if (!no_symlinks.has_value()) {
    return no_symlinks;
  }
  const std::array managed_directories{
      bundle,
      bundle / "assets",
      bundle / "history",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
      bundle / "recovery",
      bundle / "recovery/active",
      bundle / "recovery/sealed",
  };
  for (const auto& directory : managed_directories) {
    const auto present = platform.directory_exists(directory);
    if (!present.has_value() || !present.value()) {
      return foundation::Result<void>::failure(
          invalid_project(
              "project managed directory is missing or invalid",
              directory,
              present.has_value()
                  ? "path is not an existing directory"
                  : present.error().message));
    }
  }
  const auto manifest = platform.byte_length(bundle / "manifest.json");
  if (!manifest.has_value()) {
    return foundation::Result<void>::failure(
        invalid_project(
            "project manifest is missing or invalid",
            bundle / "manifest.json",
            manifest.error().message));
  }
  return foundation::Result<void>::success();
}

std::span<const std::byte> byte_span(std::string_view bytes) {
  return {
      reinterpret_cast<const std::byte*>(bytes.data()),
      bytes.size(),
  };
}

std::string byte_string(std::span<const std::byte> bytes) {
  if (bytes.empty()) {
    return {};
  }
  return {
      reinterpret_cast<const char*>(bytes.data()),
      bytes.size(),
  };
}

foundation::Result<std::string> read_file_bytes(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& path) {
  auto bytes = platform.read_complete(path);
  if (!bytes.has_value()) {
    return foundation::Result<std::string>::failure(bytes.error());
  }
  return foundation::Result<std::string>::success(
      byte_string(bytes.value()));
}

foundation::Result<nlohmann::json> read_json(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& path) {
  auto bytes = read_file_bytes(platform, path);
  if (!bytes.has_value()) {
    auto existing = platform.exists(path);
    if (existing.has_value() && !existing.value()) {
      return foundation::Result<nlohmann::json>::failure(
          Error{
              ErrorCode::not_found,
              "project JSON file could not be opened",
              {{"path", path.generic_string()}},
          });
    }
    return foundation::Result<nlohmann::json>::failure(bytes.error());
  }
  try {
    return foundation::Result<nlohmann::json>::success(
        parse_bounded_or_throw(std::string_view(bytes.value())));
  } catch (const std::exception& exception) {
    return foundation::Result<nlohmann::json>::failure(
        invalid_project(
            "project JSON file could not be parsed",
            path,
            exception.what()));
  }
}

foundation::ArtifactRef describe_bytes(
    std::span<const std::byte> bytes,
    std::string media_type) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* begin =
        reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(begin, begin + bytes.size());
  }
  hasher.finish();
  return foundation::ArtifactRef{
      picosha2::get_hash_hex_string(hasher),
      std::move(media_type),
      bytes.size(),
  };
}

foundation::Result<foundation::ArtifactRef> describe_artifact(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& path,
    std::string media_type) {
  auto bytes = platform.read_complete(path);
  if (!bytes.has_value()) {
    auto existing = platform.exists(path);
    if (existing.has_value() && !existing.value()) {
      return foundation::Result<foundation::ArtifactRef>::failure(
          Error{
              ErrorCode::not_found,
              "artifact path does not exist",
              {{"path", path.generic_string()}},
          });
    }
    return foundation::Result<foundation::ArtifactRef>::failure(bytes.error());
  }
  return foundation::Result<foundation::ArtifactRef>::success(
      describe_bytes(bytes.value(), std::move(media_type)));
}

nlohmann::json slot_json(domain::PadSlotId slot) {
  return {{"bank", slot.bank}, {"pad", slot.pad}};
}

std::string_view trigger_mode_name(domain::TriggerMode mode) {
  switch (mode) {
    case domain::TriggerMode::one_shot:
      return "one_shot";
    case domain::TriggerMode::gate:
      return "gate";
    case domain::TriggerMode::loop_gate:
      return "loop_gate";
    case domain::TriggerMode::loop_toggle:
      return "loop_toggle";
  }
  return {};
}

std::optional<domain::TriggerMode> parse_trigger_mode(std::string_view mode) {
  if (mode == "one_shot") {
    return domain::TriggerMode::one_shot;
  }
  if (mode == "gate") {
    return domain::TriggerMode::gate;
  }
  if (mode == "loop_gate") {
    return domain::TriggerMode::loop_gate;
  }
  if (mode == "loop_toggle") {
    return domain::TriggerMode::loop_toggle;
  }
  return std::nullopt;
}

nlohmann::json playback_json(const domain::PadPlayback& playback) {
  return {
      {"gain_millidb", playback.gain_millidb},
      {"muted", playback.muted},
      {"trigger_mode", trigger_mode_name(playback.trigger_mode)},
      {"trim_end_frame",
       playback.trim_end_frame.has_value()
           ? nlohmann::json(*playback.trim_end_frame)
           : nlohmann::json(nullptr)},
      {"trim_start_frame", playback.trim_start_frame},
  };
}

nlohmann::json pattern_event_json(const domain::PatternEvent& event) {
  return {
      {"duration_tick", event.duration_tick},
      {"onset_tick", event.onset_tick},
      {"slot", slot_json(event.slot)},
      {"velocity", event.velocity},
  };
}

nlohmann::json pattern_value_json(const domain::Pattern& pattern) {
  auto events = nlohmann::json::array();
  for (const auto& event : pattern.events) {
    events.push_back(pattern_event_json(event));
  }
  return {
      {"bars", pattern.bars},
      {"events", std::move(events)},
  };
}

nlohmann::json pattern_json(const domain::Pattern& pattern) {
  auto encoded = pattern_value_json(pattern);
  encoded["id"] = pattern.id.value();
  return encoded;
}

domain::ProjectState persisted_v3_projection(
    const domain::ProjectState& state) {
  auto projected = state;
  if (projected.contract != domain::ProjectContract::v3) {
    projected.quantize_enabled = true;
    projected.swing_percent = 50;
  }
  projected.contract = domain::ProjectContract::v3;
  for (auto& [id, pattern] : projected.patterns) {
    (void)id;
    pattern.events = domain::merge_pattern_events({}, pattern.events);
  }
  return projected;
}

nlohmann::json project_json(const domain::ProjectState& state) {
  auto banks = nlohmann::json::array();
  for (std::size_t bank = 0; bank < state.banks.size(); ++bank) {
    auto pads = nlohmann::json::array();
    for (const auto& slot : state.banks.at(bank)) {
      nlohmann::json encoded_pad = {
          {"asset_id",
           slot.asset_id.has_value()
               ? nlohmann::json(slot.asset_id->value())
               : nlohmann::json(nullptr)},
          {"pad", slot.id.pad},
      };
      encoded_pad["playback"] = playback_json(slot.playback);
      pads.push_back(std::move(encoded_pad));
    }
    banks.push_back(
        {
            {"bank", bank},
            {"pads", std::move(pads)},
        });
  }

  auto assets = nlohmann::json::array();
  for (const auto& [id, asset] : state.assets) {
    assets.push_back(
        {{"artifact", asset.artifact}, {"asset_id", id.value()}});
  }
  auto patterns = nlohmann::json::array();
  for (const auto& [id, pattern] : state.patterns) {
    auto encoded = pattern_value_json(pattern);
    encoded["pattern_id"] = id.value();
    patterns.push_back(std::move(encoded));
  }
  return {
      {"assets", std::move(assets)},
      {"banks", std::move(banks)},
      {"bpm", state.bpm},
      {"contract", kProjectWriterContract},
      {"patterns", std::move(patterns)},
      {"project_id", state.id.value()},
      {"revision", state.revision},
      {"sequence_settings",
       {
           {"quantize_enabled", state.quantize_enabled},
           {"swing_percent", state.swing_percent},
       }},
  };
}

bool exact_object_keys(
    const nlohmann::json& input,
    std::initializer_list<std::string_view> keys) {
  if (!input.is_object() || input.size() != keys.size()) {
    return false;
  }
  return std::all_of(
      keys.begin(),
      keys.end(),
      [&input](std::string_view key) {
        return input.contains(std::string(key));
      });
}

std::optional<std::uint64_t> unsigned_integer_value(
    const nlohmann::json& input) {
  if (input.is_number_unsigned()) {
    return input.get<std::uint64_t>();
  }
  if (!input.is_number_integer()) {
    return std::nullopt;
  }
  const auto value = input.get<std::int64_t>();
  if (value < 0) {
    return std::nullopt;
  }
  return static_cast<std::uint64_t>(value);
}

bool nonnegative_integer(const nlohmann::json& input) {
  return unsigned_integer_value(input).has_value();
}

foundation::Result<domain::PadPlayback> parse_playback(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(
            input,
            {"gain_millidb",
             "muted",
             "trigger_mode",
             "trim_end_frame",
             "trim_start_frame"}) ||
        !input.at("gain_millidb").is_number_integer() ||
        !input.at("muted").is_boolean() ||
        !input.at("trigger_mode").is_string() ||
        !nonnegative_integer(input.at("trim_start_frame")) ||
        !(input.at("trim_end_frame").is_null() ||
          nonnegative_integer(input.at("trim_end_frame")))) {
      return foundation::Result<domain::PadPlayback>::failure(
          invalid_project("project Pad playback shape is invalid", path));
    }
    const auto trigger_mode = parse_trigger_mode(
        input.at("trigger_mode").get<std::string>());
    const auto gain = input.at("gain_millidb").get<std::int64_t>();
    const auto trim_start =
        unsigned_integer_value(input.at("trim_start_frame"));
    std::optional<std::uint64_t> trim_end;
    if (!input.at("trim_end_frame").is_null()) {
      trim_end = unsigned_integer_value(input.at("trim_end_frame"));
    }
    if (!trigger_mode.has_value() || !trim_start.has_value() ||
        gain < -60'000 || gain > 6'000 ||
        (trim_end.has_value() &&
         (*trim_end == 0 || *trim_end <= *trim_start))) {
      return foundation::Result<domain::PadPlayback>::failure(
          invalid_project("project Pad playback is invalid", path));
    }
    return foundation::Result<domain::PadPlayback>::success(
        domain::PadPlayback{
            *trim_start,
            trim_end,
            *trigger_mode,
            static_cast<std::int32_t>(gain),
            input.at("muted").get<bool>(),
        });
  } catch (const std::exception& exception) {
    return foundation::Result<domain::PadPlayback>::failure(
        invalid_project(
            "project Pad playback could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<domain::PadSlotId> parse_slot(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(input, {"bank", "pad"})) {
      return foundation::Result<domain::PadSlotId>::failure(
          invalid_project("project pad slot shape is invalid", path));
    }
    const auto bank = unsigned_integer_value(input.at("bank"));
    const auto pad = unsigned_integer_value(input.at("pad"));
    if (!bank.has_value() || !pad.has_value() ||
        *bank > 3 || *pad > 15) {
      return foundation::Result<domain::PadSlotId>::failure(
          invalid_project("project contains an invalid pad slot", path));
    }
    domain::PadSlotId slot{
        static_cast<std::uint8_t>(*bank),
        static_cast<std::uint8_t>(*pad),
    };
    if (!domain::is_valid_slot(slot)) {
      return foundation::Result<domain::PadSlotId>::failure(
          invalid_project("project contains an invalid pad slot", path));
    }
    return foundation::Result<domain::PadSlotId>::success(slot);
  } catch (const std::exception& exception) {
    return foundation::Result<domain::PadSlotId>::failure(
        invalid_project(
            "project pad slot could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<domain::Pattern> parse_pattern(
    const nlohmann::json& input,
    const std::filesystem::path& path,
    bool allow_legacy_events = false) {
  try {
    if (!exact_object_keys(input, {"bars", "events", "id"}) ||
        !input.at("events").is_array()) {
      return foundation::Result<domain::Pattern>::failure(
          invalid_project("project pattern shape is invalid", path));
    }
    const auto bars = unsigned_integer_value(input.at("bars"));
    if (!bars.has_value() ||
        (*bars != 1 && *bars != 2 && *bars != 4 && *bars != 8)) {
      return foundation::Result<domain::Pattern>::failure(
          invalid_project("project pattern metadata is invalid", path));
    }
    domain::Pattern pattern{
        foundation::PatternId{input.at("id").get<std::string>()},
        static_cast<std::uint8_t>(*bars),
        {},
    };
    if (!domain::is_valid_uuid(pattern.id.value()) ||
        (pattern.bars != 1 && pattern.bars != 2 &&
         pattern.bars != 4 && pattern.bars != 8)) {
      return foundation::Result<domain::Pattern>::failure(
          invalid_project("project pattern metadata is invalid", path));
    }
    const auto tick_limit = domain::pattern_length_ticks(pattern.bars);
    for (const auto& encoded : input.at("events")) {
      const bool legacy_event = exact_object_keys(
          encoded, {"slot", "step", "velocity"});
      const bool tick_event = exact_object_keys(
          encoded,
          {"duration_tick", "onset_tick", "slot", "velocity"});
      if ((!allow_legacy_events && legacy_event) ||
          (!legacy_event && !tick_event)) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event shape is invalid", path));
      }
      const auto onset_tick = unsigned_integer_value(
          encoded.at(legacy_event ? "step" : "onset_tick"));
      const auto duration_tick = legacy_event
                                     ? std::optional<std::uint64_t>{
                                           domain::kSixteenthTicks}
                                     : unsigned_integer_value(
                                           encoded.at("duration_tick"));
      const auto velocity =
          unsigned_integer_value(encoded.at("velocity"));
      if (!onset_tick.has_value() || !duration_tick.has_value() ||
          !velocity.has_value() ||
          *onset_tick > std::numeric_limits<std::uint32_t>::max() ||
          *duration_tick > std::numeric_limits<std::uint32_t>::max() ||
          *velocity > std::numeric_limits<std::uint8_t>::max() ||
          (legacy_event &&
           *onset_tick >= static_cast<std::uint64_t>(pattern.bars) * 16U)) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event is invalid", path));
      }
      auto slot = parse_slot(encoded.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<domain::Pattern>::failure(slot.error());
      }
      domain::PatternEvent event{
          slot.value(),
          static_cast<std::uint32_t>(
              legacy_event ? *onset_tick * domain::kSixteenthTicks
                           : *onset_tick),
          static_cast<std::uint32_t>(*duration_tick),
          static_cast<std::uint8_t>(*velocity),
      };
      if (event.velocity < 1 || event.velocity > 127 ||
          event.onset_tick >= tick_limit || event.duration_tick == 0 ||
          event.duration_tick > tick_limit - event.onset_tick) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event is invalid", path));
      }
      pattern.events.push_back(event);
    }
    pattern.events = domain::merge_pattern_events({}, pattern.events);
    return foundation::Result<domain::Pattern>::success(std::move(pattern));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::Pattern>::failure(
        invalid_project(
            "project pattern could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<void> validate_retired_capture(
    std::string_view id,
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!domain::is_valid_uuid(id) ||
        !exact_object_keys(input, {"events", "sample_rate"}) ||
        !input.at("events").is_array()) {
      return foundation::Result<void>::failure(
          invalid_project("retired capture entry is invalid", path));
    }
    const auto sample_rate = unsigned_integer_value(input.at("sample_rate"));
    if (!sample_rate.has_value() || *sample_rate != 48000) {
      return foundation::Result<void>::failure(
          invalid_project("retired capture metadata is invalid", path));
    }
    for (const auto& encoded : input.at("events")) {
      if (!exact_object_keys(encoded, {"frame_offset", "slot", "velocity"})) {
        return foundation::Result<void>::failure(
            invalid_project("retired capture event shape is invalid", path));
      }
      const auto frame_offset = unsigned_integer_value(encoded.at("frame_offset"));
      const auto velocity = unsigned_integer_value(encoded.at("velocity"));
      const auto slot = parse_slot(encoded.at("slot"), path);
      if (!frame_offset.has_value() || !velocity.has_value() ||
          *frame_offset > std::numeric_limits<std::uint32_t>::max() ||
          *velocity < 1 || *velocity > 127 || !slot.has_value()) {
        return foundation::Result<void>::failure(
            slot.has_value()
                ? invalid_project("retired capture event is invalid", path)
                : slot.error());
      }
    }
    return foundation::Result<void>::success();
  } catch (const std::exception& exception) {
    return foundation::Result<void>::failure(
        invalid_project(
            "retired capture could not be parsed", path, exception.what()));
  }
}

foundation::Result<domain::Pattern> parse_project_pattern(
    std::string_view id,
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  if (!domain::is_valid_uuid(id) ||
      !exact_object_keys(input, {"bars", "events"})) {
    return foundation::Result<domain::Pattern>::failure(
        invalid_project("project pattern entry is invalid", path));
  }
  auto encoded = input;
  encoded["id"] = id;
  return parse_pattern(encoded, path, true);
}

foundation::Result<domain::ProjectState> parse_project(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    const auto contract = input.contains("contract") &&
                                  input.at("contract").is_string()
                              ? input.at("contract").get<std::string>()
                              : std::string{};
    const bool is_v1 = contract == "lmdj.project.v1";
    const bool is_v2 = contract == "lmdj.project.v2";
    const bool is_v3 = contract == "lmdj.project.v3";
    const bool legacy_shape =
        (is_v1 || is_v2) &&
        exact_object_keys(
            input,
            {
                "assets",
                "banks",
                "bpm",
                "contract",
                "patterns",
                "project_id",
                "revision",
                "takes",
            }) &&
        input.at("assets").is_object() &&
        input.at("takes").is_object() &&
        input.at("patterns").is_object();
    const bool v3_shape =
        is_v3 &&
        exact_object_keys(
            input,
            {
                "assets",
                "banks",
                "bpm",
                "contract",
                "patterns",
                "project_id",
                "revision",
                "sequence_settings",
            }) &&
        input.at("assets").is_array() &&
        input.at("patterns").is_array() &&
        exact_object_keys(
            input.at("sequence_settings"),
            {"quantize_enabled", "swing_percent"});
    if ((!legacy_shape && !v3_shape) ||
        !nonnegative_integer(input.at("revision")) ||
        !nonnegative_integer(input.at("bpm")) ||
        !input.at("banks").is_array()) {
      return foundation::Result<domain::ProjectState>::failure(
          invalid_project("project checkpoint contract is invalid", path));
    }
    const auto bpm = unsigned_integer_value(input.at("bpm"));
    const auto revision =
        unsigned_integer_value(input.at("revision"));
    if (!bpm.has_value() || *bpm > 240 ||
        !revision.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(
          invalid_project("project metadata is invalid", path));
    }
    auto created = domain::create_project(
        foundation::ProjectId{
            input.at("project_id").get<std::string>()},
        static_cast<std::uint16_t>(*bpm));
    if (!created.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(
          invalid_project("project metadata is invalid", path));
    }
    auto state = std::move(created.value());
    state.contract = domain::ProjectContract::v3;
    state.revision = *revision;
    if (is_v3) {
      const auto swing = unsigned_integer_value(
          input.at("sequence_settings").at("swing_percent"));
      if (!input.at("sequence_settings")
               .at("quantize_enabled")
               .is_boolean() ||
          !swing.has_value() ||
          *swing < domain::kSwingPercentMin ||
          *swing > domain::kSwingPercentMax) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project sequence settings are invalid", path));
      }
      state.quantize_enabled = input.at("sequence_settings")
                                   .at("quantize_enabled")
                                   .get<bool>();
      state.swing_percent = static_cast<std::uint8_t>(*swing);
    }

    const auto& banks = input.at("banks");
    if (banks.size() != state.banks.size()) {
      return foundation::Result<domain::ProjectState>::failure(
          invalid_project("project bank count is invalid", path));
    }
    std::array<bool, 4> seen_banks{};
    for (const auto& encoded_bank : banks) {
      if (!exact_object_keys(encoded_bank, {"bank", "pads"}) ||
          !nonnegative_integer(encoded_bank.at("bank")) ||
          !encoded_bank.at("pads").is_array()) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project bank shape is invalid", path));
      }
      const auto bank =
          unsigned_integer_value(encoded_bank.at("bank"));
      if (!bank.has_value() ||
          *bank >= state.banks.size() || seen_banks.at(*bank) ||
          encoded_bank.at("pads").size() !=
              state.banks.at(*bank).size()) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project bank layout is invalid", path));
      }
      seen_banks.at(*bank) = true;
      std::array<bool, 16> seen_pads{};
      for (const auto& encoded_pad : encoded_bank.at("pads")) {
        const bool valid_pad_shape =
            is_v1
                ? exact_object_keys(encoded_pad, {"asset_id", "pad"})
                : exact_object_keys(
                      encoded_pad, {"asset_id", "pad", "playback"});
        if (!valid_pad_shape ||
            !nonnegative_integer(encoded_pad.at("pad"))) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project("project pad shape is invalid", path));
        }
        const auto pad =
            unsigned_integer_value(encoded_pad.at("pad"));
        if (!pad.has_value() ||
            *pad >= state.banks.at(*bank).size() ||
            seen_pads.at(*pad)) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project("project pad layout is invalid", path));
        }
        seen_pads.at(*pad) = true;
        if (encoded_pad.at("asset_id").is_null()) {
          state.banks.at(*bank).at(*pad).asset_id =
              std::nullopt;
        } else {
          const auto asset_id =
              encoded_pad.at("asset_id").get<std::string>();
          if (!domain::is_valid_uuid(asset_id)) {
            return foundation::Result<domain::ProjectState>::failure(
                invalid_project(
                    "project pad asset reference is invalid",
                    path));
          }
          state.banks.at(*bank).at(*pad).asset_id =
              foundation::AssetId{asset_id};
        }
        if (!is_v1) {
          auto playback = parse_playback(encoded_pad.at("playback"), path);
          if (!playback.has_value()) {
            return foundation::Result<domain::ProjectState>::failure(
                playback.error());
          }
          state.banks.at(*bank).at(*pad).playback = playback.value();
        }
      }
    }

    const auto parse_asset_entry = [&state, &path](
                                       std::string_view id,
                                       const nlohmann::json& encoded)
        -> foundation::Result<void> {
      if (!domain::is_valid_uuid(id) ||
          !exact_object_keys(encoded, {"artifact"}) ||
          !exact_object_keys(
              encoded.at("artifact"),
              {"byte_length", "media_type", "sha256"}) ||
          !nonnegative_integer(
              encoded.at("artifact").at("byte_length")) ||
          !encoded.at("artifact").at("media_type").is_string() ||
          encoded.at("artifact").at("media_type")
              .get<std::string>()
              .empty() ||
          !encoded.at("artifact").at("sha256").is_string()) {
        return foundation::Result<void>::failure(
            invalid_project("project asset entry is invalid", path));
      }
      domain::Asset asset{
          foundation::AssetId{std::string{id}},
          foundation::ArtifactRef{
              encoded.at("artifact")
                  .at("sha256")
                  .get<std::string>(),
              encoded.at("artifact")
                  .at("media_type")
                  .get<std::string>(),
              encoded.at("artifact")
                  .at("byte_length")
                  .get<std::uint64_t>(),
          },
      };
      if (!valid_sha256(asset.artifact.sha256)) {
        return foundation::Result<void>::failure(
            invalid_project("project artifact reference is invalid", path));
      }
      if (!state.assets.emplace(asset.id, asset).second) {
        return foundation::Result<void>::failure(
            invalid_project("project asset id is duplicated", path));
      }
      return foundation::Result<void>::success();
    };
    if (is_v3) {
      for (const auto& encoded : input.at("assets")) {
        if (!exact_object_keys(encoded, {"artifact", "asset_id"}) ||
            !encoded.at("asset_id").is_string()) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project("project asset entry is invalid", path));
        }
        auto value = nlohmann::json{{"artifact", encoded.at("artifact")}};
        auto parsed = parse_asset_entry(
            encoded.at("asset_id").get<std::string>(), value);
        if (!parsed.has_value()) {
          return foundation::Result<domain::ProjectState>::failure(
              parsed.error());
        }
      }
    } else {
      for (auto iterator = input.at("assets").begin();
           iterator != input.at("assets").end(); ++iterator) {
        auto parsed = parse_asset_entry(iterator.key(), iterator.value());
        if (!parsed.has_value()) {
          return foundation::Result<domain::ProjectState>::failure(
              parsed.error());
        }
      }
    }
    for (const auto& bank : state.banks) {
      for (const auto& slot : bank) {
        if (slot.asset_id.has_value() &&
            !state.assets.contains(*slot.asset_id)) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project(
                  "project pad references a missing asset",
                  path));
        }
      }
    }

    if (is_v3) {
      for (const auto& encoded : input.at("patterns")) {
        if (!exact_object_keys(
                encoded, {"bars", "events", "pattern_id"}) ||
            !encoded.at("pattern_id").is_string()) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project("project pattern entry is invalid", path));
        }
        auto value = encoded;
        value["id"] = value.at("pattern_id");
        value.erase("pattern_id");
        auto pattern = parse_pattern(value, path);
        if (!pattern.has_value() ||
            !state.patterns.emplace(pattern.value().id, pattern.value()).second) {
          return foundation::Result<domain::ProjectState>::failure(
              pattern.has_value()
                  ? invalid_project("project pattern id is duplicated", path)
                  : pattern.error());
        }
      }
    } else {
      // Retired v1/v2 capture data is validated and discarded by migration.
      for (auto iterator = input.at("takes").begin();
           iterator != input.at("takes").end(); ++iterator) {
        auto capture = validate_retired_capture(
            iterator.key(), iterator.value(), path);
        if (!capture.has_value()) {
          return foundation::Result<domain::ProjectState>::failure(
              capture.error());
        }
      }
      for (auto iterator = input.at("patterns").begin();
           iterator != input.at("patterns").end(); ++iterator) {
        auto pattern = parse_project_pattern(
            iterator.key(), iterator.value(), path);
        if (!pattern.has_value()) {
          return foundation::Result<domain::ProjectState>::failure(
              pattern.error());
        }
        state.patterns.emplace(pattern.value().id, pattern.value());
      }
    }
    return foundation::Result<domain::ProjectState>::success(std::move(state));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::ProjectState>::failure(
        invalid_project(
            "project checkpoint could not be parsed",
            path,
            exception.what()));
  }
}

nlohmann::json meta_json(const domain::CommandMeta& meta) {
  return {
      {"command_id", meta.command_id.value()},
      {"expected_revision", meta.expected_revision},
  };
}

const domain::CommandMeta& command_meta(const PersistedCommand& command) {
  return std::visit(
      [](const auto& value) -> const domain::CommandMeta& {
        return value.meta;
      },
      command);
}

nlohmann::json command_json(const PersistedCommand& command) {
  return std::visit(
      [](const auto& value) -> nlohmann::json {
        using Type = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<Type, domain::ImportAsset>) {
          return {
              {"asset",
               {
                   {"artifact", value.asset.artifact},
                   {"id", value.asset.id.value()},
               }},
              {"meta", meta_json(value.meta)},
              {"type", "ImportAsset"},
          };
        } else if constexpr (std::is_same_v<Type, domain::AssignPad>) {
          return {
              {"asset_id",
               value.asset_id.has_value()
                   ? nlohmann::json(value.asset_id->value())
                   : nlohmann::json(nullptr)},
              {"meta", meta_json(value.meta)},
              {"slot", slot_json(value.slot)},
              {"type", "AssignPad"},
          };
        } else if constexpr (std::is_same_v<Type, domain::CreatePattern>) {
          return {
              {"meta", meta_json(value.meta)},
              {"pattern", pattern_json(value.pattern)},
              {"type", "CreatePattern"},
          };
        } else if constexpr (
            std::is_same_v<Type, domain::MergePatternEvents>) {
          auto events = nlohmann::json::array();
          for (const auto& event : value.events) {
            events.push_back(pattern_event_json(event));
          }
          return {
              {"events", std::move(events)},
              {"meta", meta_json(value.meta)},
              {"pattern_id", value.pattern_id.value()},
              {"type", "MergePatternEvents"},
          };
        } else if constexpr (
            std::is_same_v<Type, domain::UpdateSequenceSettings>) {
          return {
              {"bpm",
               value.bpm.has_value() ? nlohmann::json(*value.bpm)
                                     : nlohmann::json(nullptr)},
              {"meta", meta_json(value.meta)},
              {"quantize_enabled",
               value.quantize_enabled.has_value()
                   ? nlohmann::json(*value.quantize_enabled)
                   : nlohmann::json(nullptr)},
              {"swing_percent",
               value.swing_percent.has_value()
                   ? nlohmann::json(*value.swing_percent)
                   : nlohmann::json(nullptr)},
              {"type", "UpdateSequenceSettings"},
          };
        } else if constexpr (
            std::is_same_v<Type, domain::ImportAssignSample>) {
          return {
              {"asset",
               {
                   {"artifact", value.asset.artifact},
                   {"id", value.asset.id.value()},
               }},
              {"meta", meta_json(value.meta)},
              {"slot", slot_json(value.slot)},
              {"type", "ImportAssignSample"},
          };
        } else if constexpr (
            std::is_same_v<Type, domain::UpdatePadPlayback>) {
          return {
              {"meta", meta_json(value.meta)},
              {"playback", playback_json(value.playback)},
              {"slot", slot_json(value.slot)},
              {"type", "UpdatePadPlayback"},
          };
        } else {
          return {
              {"meta", meta_json(value.meta)},
              {"slot", slot_json(value.slot)},
              {"type", "ResetPadPlayback"},
          };
        }
      },
      command);
}

foundation::Result<domain::CommandMeta> parse_meta(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(input, {"command_id", "expected_revision"}) ||
        !nonnegative_integer(input.at("expected_revision"))) {
      return foundation::Result<domain::CommandMeta>::failure(
          invalid_project("transaction command metadata shape is invalid", path));
    }
    domain::CommandMeta meta{
        foundation::CommandId{input.at("command_id").get<std::string>()},
        input.at("expected_revision").get<std::uint64_t>(),
    };
    if (!domain::is_valid_uuid(meta.command_id.value())) {
      return foundation::Result<domain::CommandMeta>::failure(
          invalid_project("transaction command id is invalid", path));
    }
    return foundation::Result<domain::CommandMeta>::success(std::move(meta));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::CommandMeta>::failure(
        invalid_project(
            "transaction command metadata could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<PersistedCommand> parse_command(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    auto meta = parse_meta(input.at("meta"), path);
    if (!meta.has_value()) {
      return foundation::Result<PersistedCommand>::failure(meta.error());
    }
    const auto type = input.at("type").get<std::string>();
    if (type == "ImportAsset") {
      const auto& encoded = input.at("asset");
      if (!exact_object_keys(input, {"asset", "meta", "type"}) ||
          !exact_object_keys(input.at("asset"), {"artifact", "id"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project("ImportAsset transaction shape is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::ImportAsset{
              std::move(meta.value()),
              domain::Asset{
                  foundation::AssetId{
                      encoded.at("id").get<std::string>()},
                  encoded.at("artifact")
                      .get<foundation::ArtifactRef>(),
              },
          }});
    }
    if (type == "AssignPad") {
      auto slot = parse_slot(input.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<PersistedCommand>::failure(slot.error());
      }
      std::optional<foundation::AssetId> asset_id;
      if (!input.at("asset_id").is_null()) {
        asset_id = foundation::AssetId{
            input.at("asset_id").get<std::string>()};
      }
      if (!exact_object_keys(input, {"asset_id", "meta", "slot", "type"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project("AssignPad transaction shape is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::AssignPad{
              std::move(meta.value()),
              slot.value(),
              std::move(asset_id),
          }});
    }
    if (type == "CreatePattern") {
      auto pattern = parse_pattern(input.at("pattern"), path);
      if (!pattern.has_value()) {
        return foundation::Result<PersistedCommand>::failure(pattern.error());
      }
      if (!exact_object_keys(input, {"meta", "pattern", "type"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project("CreatePattern transaction shape is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::CreatePattern{
              std::move(meta.value()),
              std::move(pattern.value()),
          }});
    }
    if (type == "MergePatternEvents") {
      if (!exact_object_keys(
              input, {"events", "meta", "pattern_id", "type"}) ||
          !input.at("events").is_array() ||
          !input.at("pattern_id").is_string()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "MergePatternEvents transaction shape is invalid", path));
      }
      const auto pattern_id =
          input.at("pattern_id").get<std::string>();
      if (!domain::is_valid_uuid(pattern_id)) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "MergePatternEvents pattern id is invalid", path));
      }
      auto encoded_pattern = nlohmann::json{
          {"bars", 8},
          {"events", input.at("events")},
          {"id", pattern_id},
      };
      auto parsed = parse_pattern(encoded_pattern, path);
      if (!parsed.has_value()) {
        return foundation::Result<PersistedCommand>::failure(parsed.error());
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::MergePatternEvents{
              std::move(meta.value()),
              foundation::PatternId{pattern_id},
              std::move(parsed.value().events),
          }});
    }
    if (type == "UpdateSequenceSettings") {
      if (!exact_object_keys(
              input,
              {"bpm",
               "meta",
               "quantize_enabled",
               "swing_percent",
               "type"}) ||
          !(input.at("bpm").is_null() ||
            nonnegative_integer(input.at("bpm"))) ||
          !(input.at("quantize_enabled").is_null() ||
            input.at("quantize_enabled").is_boolean()) ||
          !(input.at("swing_percent").is_null() ||
            nonnegative_integer(input.at("swing_percent")))) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "UpdateSequenceSettings transaction shape is invalid", path));
      }
      std::optional<std::uint16_t> bpm;
      std::optional<bool> quantize_enabled;
      std::optional<std::uint8_t> swing_percent;
      if (!input.at("bpm").is_null()) {
        const auto value = unsigned_integer_value(input.at("bpm"));
        if (!value.has_value() ||
            *value > std::numeric_limits<std::uint16_t>::max()) {
          return foundation::Result<PersistedCommand>::failure(
              invalid_project("UpdateSequenceSettings BPM is invalid", path));
        }
        bpm = static_cast<std::uint16_t>(*value);
      }
      if (!input.at("quantize_enabled").is_null()) {
        quantize_enabled = input.at("quantize_enabled").get<bool>();
      }
      if (!input.at("swing_percent").is_null()) {
        const auto value = unsigned_integer_value(input.at("swing_percent"));
        if (!value.has_value() ||
            *value > std::numeric_limits<std::uint8_t>::max()) {
          return foundation::Result<PersistedCommand>::failure(
              invalid_project(
                  "UpdateSequenceSettings Swing is invalid", path));
        }
        swing_percent = static_cast<std::uint8_t>(*value);
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::UpdateSequenceSettings{
              std::move(meta.value()), bpm, quantize_enabled, swing_percent}});
    }
    if (type == "ImportAssignSample") {
      if (!exact_object_keys(input, {"asset", "meta", "slot", "type"}) ||
          !exact_object_keys(input.at("asset"), {"artifact", "id"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "ImportAssignSample transaction shape is invalid", path));
      }
      auto slot = parse_slot(input.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<PersistedCommand>::failure(slot.error());
      }
      const auto& encoded = input.at("asset");
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::ImportAssignSample{
              std::move(meta.value()),
              domain::Asset{
                  foundation::AssetId{encoded.at("id").get<std::string>()},
                  encoded.at("artifact").get<foundation::ArtifactRef>(),
              },
              slot.value(),
          }});
    }
    if (type == "UpdatePadPlayback") {
      if (!exact_object_keys(
              input, {"meta", "playback", "slot", "type"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "UpdatePadPlayback transaction shape is invalid", path));
      }
      auto slot = parse_slot(input.at("slot"), path);
      auto playback = parse_playback(input.at("playback"), path);
      if (!slot.has_value()) {
        return foundation::Result<PersistedCommand>::failure(slot.error());
      }
      if (!playback.has_value()) {
        return foundation::Result<PersistedCommand>::failure(playback.error());
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::UpdatePadPlayback{
              std::move(meta.value()),
              slot.value(),
              playback.value(),
          }});
    }
    if (type == "ResetPadPlayback") {
      if (!exact_object_keys(input, {"meta", "slot", "type"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "ResetPadPlayback transaction shape is invalid", path));
      }
      auto slot = parse_slot(input.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<PersistedCommand>::failure(slot.error());
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::ResetPadPlayback{
              std::move(meta.value()),
              slot.value(),
          }});
    }
    return foundation::Result<PersistedCommand>::failure(
        invalid_project("transaction command type is unknown", path));
  } catch (const std::exception& exception) {
    return foundation::Result<PersistedCommand>::failure(
        invalid_project(
            "transaction command could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<domain::AppliedCommand> apply_command(
    const domain::ProjectState& state,
    const PersistedCommand& command,
    const std::map<foundation::CommandId, domain::CommandReceipt>& receipts) {
  return std::visit(
      [&state, &receipts](const auto& value) {
        using Type = std::decay_t<decltype(value)>;
        if constexpr (
            std::is_same_v<Type, domain::ImportAssignSample> ||
            std::is_same_v<Type, domain::UpdatePadPlayback> ||
            std::is_same_v<Type, domain::ResetPadPlayback>) {
          return domain::apply(state, value, receipts);
        } else {
          return domain::apply(state, domain::Command{value}, receipts);
        }
      },
      command);
}

PersistedCommand persisted_command(const domain::Command& command) {
  return std::visit(
      [](const auto& value) -> PersistedCommand {
        auto normalized = value;
        using Type = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<Type, domain::CreatePattern>) {
          normalized.pattern.events = domain::merge_pattern_events(
              {}, normalized.pattern.events);
        } else if constexpr (
            std::is_same_v<Type, domain::MergePatternEvents>) {
          normalized.events = domain::merge_pattern_events(
              {}, normalized.events);
        }
        return PersistedCommand{std::move(normalized)};
      },
      command);
}

foundation::Result<domain::Command> legacy_command(
    const PersistedCommand& command) {
  return std::visit(
      [](const auto& value) -> foundation::Result<domain::Command> {
        using Type = std::decay_t<decltype(value)>;
        if constexpr (
            std::is_same_v<Type, domain::ImportAssignSample> ||
            std::is_same_v<Type, domain::UpdatePadPlayback> ||
            std::is_same_v<Type, domain::ResetPadPlayback>) {
          return foundation::Result<domain::Command>::failure(
              Error{
                  ErrorCode::internal_error,
                  "persisted Sample command is not a legacy command",
              });
        } else {
          return foundation::Result<domain::Command>::success(
              domain::Command{value});
        }
      },
      command);
}

bool safe_relative_path(
    const std::filesystem::path& relative,
    const std::filesystem::path& required_parent) {
  if (relative.empty() || relative.is_absolute() ||
      relative.lexically_normal() != relative) {
    return false;
  }
  auto iterator = relative.begin();
  auto parent_iterator = required_parent.begin();
  for (; parent_iterator != required_parent.end(); ++parent_iterator) {
    if (iterator == relative.end() || *iterator != *parent_iterator) {
      return false;
    }
    ++iterator;
  }
  return iterator != relative.end();
}

foundation::Result<LoadedProject> load_project(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  const auto manifest_path = bundle / "manifest.json";
  auto manifest_result = read_json(platform, manifest_path);
  if (!manifest_result.has_value()) {
    return foundation::Result<LoadedProject>::failure(
        manifest_result.error());
  }

  try {
    const auto& manifest = manifest_result.value();
    if (manifest.at("contract") != "lmdj.project.manifest.v1") {
      return foundation::Result<LoadedProject>::failure(
          invalid_project("project manifest contract is invalid", manifest_path));
    }
    const auto head_revision =
        manifest.at("head_revision").get<std::uint64_t>();
    const auto head_checkpoint =
        std::filesystem::path{
            manifest.at("head_checkpoint").get<std::string>()};
    const auto expected_head =
        std::filesystem::path{"history/checkpoints"} /
        (std::to_string(head_revision) + ".json");
    if (head_checkpoint != expected_head ||
        !safe_relative_path(
            head_checkpoint, "history/checkpoints")) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project("project manifest checkpoint path is invalid", manifest_path));
    }

    auto initial_json =
        read_json(platform, bundle / "history/checkpoints/0.json");
    if (!initial_json.has_value()) {
      return foundation::Result<LoadedProject>::failure(initial_json.error());
    }
    auto initial = parse_project(
        initial_json.value(), bundle / "history/checkpoints/0.json");
    if (!initial.has_value()) {
      return foundation::Result<LoadedProject>::failure(initial.error());
    }
    if (initial.value().revision != 0) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project(
              "initial checkpoint revision is not zero",
              bundle / "history/checkpoints/0.json"));
    }
    auto checkpoint_json = read_json(platform, bundle / head_checkpoint);
    if (!checkpoint_json.has_value()) {
      return foundation::Result<LoadedProject>::failure(
          checkpoint_json.error());
    }
    auto checkpoint =
        parse_project(checkpoint_json.value(), bundle / head_checkpoint);
    if (!checkpoint.has_value()) {
      return foundation::Result<LoadedProject>::failure(checkpoint.error());
    }
    const bool checkpoint_is_v3 =
        checkpoint_json.value().at("contract") == "lmdj.project.v3";

    LoadedProject loaded{
        std::move(initial.value()),
        {},
        {},
        {},
        {},
    };
    for (const auto& encoded_path : manifest.at("transactions")) {
      const auto relative =
          std::filesystem::path{encoded_path.get<std::string>()};
      if (!safe_relative_path(relative, "history/transactions")) {
        return foundation::Result<LoadedProject>::failure(
            invalid_project("project transaction path is invalid", manifest_path));
      }
      auto transaction = read_json(platform, bundle / relative);
      if (!transaction.has_value()) {
        return foundation::Result<LoadedProject>::failure(
            transaction.error());
      }
      auto command =
          parse_command(transaction.value().at("command"), bundle / relative);
      if (!command.has_value()) {
        return foundation::Result<LoadedProject>::failure(command.error());
      }
      auto applied =
          apply_command(loaded.state, command.value(), loaded.receipts);
      if (!applied.has_value() || applied.value().replayed) {
        return foundation::Result<LoadedProject>::failure(
            invalid_project(
                "project transaction could not be replayed",
                bundle / relative));
      }
      const auto revision =
          transaction.value().at("revision").get<std::uint64_t>();
      if (revision != applied.value().state.revision ||
          transaction.value().at("event") != applied.value().event) {
        return foundation::Result<LoadedProject>::failure(
            invalid_project(
                "project transaction receipt does not match replay",
                bundle / relative));
      }
      const auto& meta = command_meta(command.value());
      loaded.commands.emplace(meta.command_id, command.value());
      loaded.receipts.emplace(
          meta.command_id,
          domain::CommandReceipt{revision, applied.value().event});
      if (transaction.value().contains("sequence_flush")) {
        try {
          const auto& encoded = transaction.value().at("sequence_flush");
          SequenceFlushIdentity identity{
              foundation::SequenceSessionId{
                  encoded.at("session_id").get<std::string>()},
              encoded.at("flush_seq").get<std::uint64_t>(),
              foundation::CommandId{
                  encoded.at("command_id").get<std::string>()},
              foundation::PatternId{
                  encoded.at("pattern_id").get<std::string>()},
          };
          const auto* merge =
              std::get_if<domain::MergePatternEvents>(&command.value());
          if (merge == nullptr ||
              !domain::is_valid_uuid(identity.session_id.value()) ||
              identity.command_id != meta.command_id ||
              identity.pattern_id != merge->pattern_id) {
            return foundation::Result<LoadedProject>::failure(
                invalid_project(
                    "project transaction Sequence flush identity is invalid",
                    bundle / relative));
          }
          loaded.sequence_flush_identities.emplace(
              meta.command_id, std::move(identity));
        } catch (const std::exception& exception) {
          return foundation::Result<LoadedProject>::failure(
              invalid_project(
                  "project transaction Sequence flush identity is invalid",
                  bundle / relative,
                  exception.what()));
        }
      }
      loaded.state = applied.value().state;
      loaded.transactions.push_back(relative.generic_string());
    }
    if (loaded.state.revision != head_revision) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project(
              "project manifest head does not match transaction replay",
              manifest_path));
    }

    if (checkpoint.value() != persisted_v3_projection(loaded.state) ||
        (checkpoint_is_v3 &&
         foundation::canonical_json(checkpoint_json.value()) !=
             foundation::canonical_json(project_json(loaded.state)))) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project(
              "project checkpoint does not match transaction replay",
              bundle / head_checkpoint));
    }

    for (const auto& [asset_id, asset] : loaded.state.assets) {
      (void)asset_id;
      const auto blob =
          bundle / "assets" / (asset.artifact.sha256 + ".wav");
      const auto described =
          describe_artifact(platform, blob, asset.artifact.media_type);
      if (!described.has_value() ||
          described.value() != asset.artifact) {
        return foundation::Result<LoadedProject>::failure(
            invalid_project(
                "project asset blob is missing or corrupt",
                blob));
      }
    }
    return foundation::Result<LoadedProject>::success(std::move(loaded));
  } catch (const std::exception& exception) {
    return foundation::Result<LoadedProject>::failure(
        invalid_project(
            "project manifest could not be validated",
            manifest_path,
            exception.what()));
  }
}

std::optional<std::uint64_t> leading_revision(std::string_view name) {
  const auto end = name.find_first_of("-.");
  if (end == std::string_view::npos || end == 0) {
    return std::nullopt;
  }
  std::uint64_t value = 0;
  const auto parsed =
      std::from_chars(name.data(), name.data() + end, value);
  if (parsed.ec != std::errc{} ||
      parsed.ptr != name.data() + end) {
    return std::nullopt;
  }
  return value;
}

std::optional<std::string_view> opaque_temp_destination(
    std::string_view name) {
  constexpr std::string_view marker = ".tmp.";
  const auto marker_position = name.rfind(marker);
  if (marker_position == std::string_view::npos) {
    return std::nullopt;
  }
  const auto token = name.substr(marker_position + marker.size());
  if (token.size() != 32 ||
      !std::all_of(
          token.begin(),
          token.end(),
          [](unsigned char character) {
            return (character >= '0' && character <= '9') ||
                   (character >= 'a' && character <= 'f');
          })) {
    return std::nullopt;
  }
  return name.substr(0, marker_position);
}

bool checkpoint_temp_name(std::string_view name) {
  const auto destination = opaque_temp_destination(name);
  constexpr std::string_view suffix = ".json";
  if (!destination.has_value() || !destination->ends_with(suffix)) {
    return false;
  }
  const auto revision =
      destination->substr(0, destination->size() - suffix.size());
  std::uint64_t parsed_revision = 0;
  const auto parsed = std::from_chars(
      revision.data(), revision.data() + revision.size(), parsed_revision);
  return parsed.ec == std::errc{} &&
         parsed.ptr == revision.data() + revision.size();
}

bool transaction_temp_name(std::string_view name) {
  const auto destination = opaque_temp_destination(name);
  constexpr std::string_view suffix = ".json";
  if (!destination.has_value() || !destination->ends_with(suffix)) {
    return false;
  }
  const auto stem =
      destination->substr(0, destination->size() - suffix.size());
  const auto separator = stem.find('-');
  if (separator == std::string_view::npos || separator == 0) {
    return false;
  }
  std::uint64_t revision = 0;
  const auto parsed = std::from_chars(
      stem.data(), stem.data() + separator, revision);
  return parsed.ec == std::errc{} &&
         parsed.ptr == stem.data() + separator &&
         domain::is_valid_uuid(stem.substr(separator + 1));
}

bool asset_temp_name(std::string_view name) {
  const auto destination = opaque_temp_destination(name);
  constexpr std::string_view suffix = ".wav";
  return destination.has_value() &&
         destination->size() == 64 + suffix.size() &&
         destination->ends_with(suffix) &&
         valid_sha256(destination->substr(0, 64));
}

bool manifest_temp_name(std::string_view name) {
  const auto destination = opaque_temp_destination(name);
  return destination.has_value() && *destination == "manifest.json";
}

std::filesystem::path sample_staging_root(
    const std::filesystem::path& bundle) {
  auto workspace = bundle.parent_path();
  if (workspace.filename() == "projects") {
    workspace = workspace.parent_path();
  }
  return workspace / ".lmdj-host/sample-staging";
}

foundation::Result<void> sample_after_staging_fault(
    const std::filesystem::path& path) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  return testing::detail::invoke_fault(
      testing::FaultPoint::sample_after_staging, path);
#else
  (void)path;
  return foundation::Result<void>::success();
#endif
}

foundation::Result<void> sample_after_event_preparation_fault(
    const std::filesystem::path& path) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  return testing::detail::invoke_fault(
      testing::FaultPoint::sample_after_event_preparation, path);
#else
  (void)path;
  return foundation::Result<void>::success();
#endif
}

foundation::Result<void> sample_after_artifact_creation_fault(
    const std::filesystem::path& path) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  return testing::detail::invoke_fault(
      testing::FaultPoint::sample_after_artifact_creation, path);
#else
  (void)path;
  return foundation::Result<void>::success();
#endif
}

foundation::Result<void> sample_after_manifest_preparation_fault(
    const std::filesystem::path& path) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  return testing::detail::invoke_fault(
      testing::FaultPoint::sample_after_manifest_preparation, path);
#else
  (void)path;
  return foundation::Result<void>::success();
#endif
}

foundation::Result<void> sample_after_manifest_publication_fault(
    const std::filesystem::path& path) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  return testing::detail::invoke_fault(
      testing::FaultPoint::sample_after_manifest_publication, path);
#else
  (void)path;
  return foundation::Result<void>::success();
#endif
}

foundation::Result<void> scavenge_sample_staging(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  constexpr std::size_t kMaximumScavengedEntries = 64;
  constexpr std::uint64_t kMaximumStagingMarkerBytes = 4U * 1024U;
  constexpr std::int64_t kMinimumIncompleteAgeSeconds = 24 * 60 * 60;
  const auto root = sample_staging_root(bundle);
  const auto present = platform.exists(root);
  if (!present.has_value()) {
    return foundation::Result<void>::failure(present.error());
  }
  if (!present.value()) {
    return foundation::Result<void>::success();
  }
  const auto valid_tree = platform.validate_managed_tree(root);
  if (!valid_tree.has_value()) {
    return valid_tree;
  }
  const auto is_directory = platform.directory_exists(root);
  if (!is_directory.has_value() || !is_directory.value()) {
    return foundation::Result<void>::failure(
        invalid_project("Sample staging root is not a directory", root));
  }
  const auto names = platform.list_directories(root);
  if (!names.has_value()) {
    return foundation::Result<void>::failure(names.error());
  }
  const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                       std::chrono::system_clock::now().time_since_epoch())
                       .count();
  std::size_t inspected = 0;
  for (const auto& name : names.value()) {
    if (inspected == kMaximumScavengedEntries) {
      break;
    }
    ++inspected;
    if (!domain::is_valid_uuid(name)) {
      continue;
    }
    const auto directory = root / name;
    const auto marker_length = platform.byte_length(directory / "state.json");
    if (!marker_length.has_value() ||
        marker_length.value() > kMaximumStagingMarkerBytes) {
      continue;
    }
    const auto marker = read_json(platform, directory / "state.json");
    if (!marker.has_value() ||
        !exact_object_keys(
            marker.value(),
            {"contract", "created_unix_seconds", "state", "token"}) ||
        marker.value().at("contract") != "lmdj.sample-staging.v1" ||
        marker.value().at("token") != name ||
        !nonnegative_integer(marker.value().at("created_unix_seconds")) ||
        !marker.value().at("state").is_string()) {
      continue;
    }
    const auto created =
        unsigned_integer_value(marker.value().at("created_unix_seconds"));
    const auto state = marker.value().at("state").get<std::string>();
    const bool old_incomplete =
        state == "incomplete" && created.has_value() &&
        *created <= static_cast<std::uint64_t>(now) &&
        static_cast<std::uint64_t>(now) - *created >=
            static_cast<std::uint64_t>(kMinimumIncompleteAgeSeconds);
    if (!old_incomplete) {
      continue;
    }
    auto lease = platform.acquire_writer(directory);
    if (!lease.has_value()) {
      const auto busy =
          lease.error().details.is_object() &&
          lease.error().details.value("storage_condition", std::string{}) ==
              kStorageConditionProjectBusy;
      if (busy) {
        continue;
      }
      return foundation::Result<void>::failure(lease.error());
    }
    lease.value().reset();
    const auto removed = platform.remove_tree(directory);
    if (!removed.has_value()) {
      return removed;
    }
  }
  return foundation::Result<void>::success();
}

struct StagedSample {
  std::filesystem::path directory;
  std::filesystem::path payload;
};

foundation::Result<StagedSample> stage_sample(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    std::string_view token,
    std::span<const std::byte> bytes) {
  const auto root = sample_staging_root(bundle);
  auto valid_tree = platform.validate_managed_tree(root);
  if (!valid_tree.has_value()) {
    return foundation::Result<StagedSample>::failure(valid_tree.error());
  }
  auto ensured = platform.ensure_directory(root);
  if (!ensured.has_value()) {
    return foundation::Result<StagedSample>::failure(ensured.error());
  }
  valid_tree = platform.validate_managed_tree(root);
  if (!valid_tree.has_value()) {
    return foundation::Result<StagedSample>::failure(valid_tree.error());
  }
  const auto directory = root / std::string{token};
  const auto reused = platform.exists(directory);
  if (!reused.has_value()) {
    return foundation::Result<StagedSample>::failure(reused.error());
  }
  auto lease = platform.acquire_writer(directory);
  if (!lease.has_value()) {
    return foundation::Result<StagedSample>::failure(lease.error());
  }
  if (reused.value()) {
    const auto valid_directory = platform.validate_managed_tree(directory);
    if (!valid_directory.has_value()) {
      return foundation::Result<StagedSample>::failure(
          valid_directory.error());
    }
    const auto files = platform.list_names(directory);
    if (!files.has_value()) {
      return foundation::Result<StagedSample>::failure(files.error());
    }
    const auto directories = platform.list_directories(directory);
    if (!directories.has_value()) {
      return foundation::Result<StagedSample>::failure(directories.error());
    }
    const auto marker = read_json(platform, directory / "state.json");
    const bool reusable_incomplete =
        files.value() ==
            std::vector<std::string>{"payload.wav", "state.json"} &&
        directories.value().empty() && marker.has_value() &&
        exact_object_keys(
            marker.value(),
            {"contract", "created_unix_seconds", "state", "token"}) &&
        marker.value().at("contract") == "lmdj.sample-staging.v1" &&
        marker.value().at("state") == "incomplete" &&
        marker.value().at("token") == token &&
        nonnegative_integer(marker.value().at("created_unix_seconds"));
    if (!reusable_incomplete) {
      return foundation::Result<StagedSample>::failure(
          Error{
              ErrorCode::invalid_argument,
              "Sample staging token was already used",
          });
    }
    const auto removed = platform.remove_tree(directory);
    if (!removed.has_value()) {
      return foundation::Result<StagedSample>::failure(removed.error());
    }
  }
  ensured = platform.ensure_directory(directory);
  if (!ensured.has_value()) {
    lease.value().reset();
    (void)platform.remove_tree(directory);
    return foundation::Result<StagedSample>::failure(ensured.error());
  }
  const auto created = std::chrono::duration_cast<std::chrono::seconds>(
                           std::chrono::system_clock::now().time_since_epoch())
                           .count();
  const auto marker_bytes = foundation::canonical_json(
                                nlohmann::json{
                                    {"contract", "lmdj.sample-staging.v1"},
                                    {"created_unix_seconds", created},
                                    {"state", "incomplete"},
                                    {"token", token},
                                }) +
                            "\n";
  auto written = platform.create_immutable(
      directory / "state.json", byte_span(marker_bytes));
  if (written.has_value()) {
    written = platform.create_immutable(directory / "payload.wav", bytes);
  }
  lease.value().reset();
  if (!written.has_value()) {
    (void)platform.remove_tree(directory);
    return foundation::Result<StagedSample>::failure(written.error());
  }
  return foundation::Result<StagedSample>::success(
      StagedSample{directory, directory / "payload.wav"});
}

foundation::Result<void> recover_initial_create_residue(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  const auto checkpoints = bundle / "history/checkpoints";
  auto checkpoint_names = platform.list_names(checkpoints);
  if (!checkpoint_names.has_value()) {
    return foundation::Result<void>::failure(checkpoint_names.error());
  }
  for (const auto& name : checkpoint_names.value()) {
    if (!checkpoint_temp_name(name) || leading_revision(name) != 0) {
      continue;
    }
    const auto removed = platform.remove(checkpoints / name);
    if (!removed.has_value()) {
      return removed;
    }
  }
  auto bundle_names = platform.list_names(bundle);
  if (!bundle_names.has_value()) {
    return foundation::Result<void>::failure(bundle_names.error());
  }
  for (const auto& name : bundle_names.value()) {
    if (!manifest_temp_name(name)) {
      continue;
    }
    const auto removed = platform.remove(bundle / name);
    if (!removed.has_value()) {
      return removed;
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> recover_uncommitted(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    const LoadedProject& loaded) {
  const auto checkpoints = bundle / "history/checkpoints";
  const auto transactions = bundle / "history/transactions";
  const auto assets = bundle / "assets";
  const std::set<std::string> committed_transactions(
      loaded.transactions.begin(), loaded.transactions.end());

  auto checkpoint_names = platform.list_names(checkpoints);
  if (!checkpoint_names.has_value()) {
    return foundation::Result<void>::failure(checkpoint_names.error());
  }
  for (const auto& name : checkpoint_names.value()) {
    const auto revision = leading_revision(name);
    if (checkpoint_temp_name(name) ||
        (revision.has_value() && *revision > loaded.state.revision)) {
      const auto removed = platform.remove(checkpoints / name);
      if (!removed.has_value()) {
        return removed;
      }
    }
  }
  auto transaction_names = platform.list_names(transactions);
  if (!transaction_names.has_value()) {
    return foundation::Result<void>::failure(transaction_names.error());
  }
  for (const auto& name : transaction_names.value()) {
    const auto relative =
        (std::filesystem::path{"history/transactions"} / name)
            .generic_string();
    if (committed_transactions.contains(relative)) {
      continue;
    }
    const auto revision = leading_revision(name);
    if (transaction_temp_name(name) ||
        (revision.has_value() && *revision > loaded.state.revision)) {
      const auto removed = platform.remove(transactions / name);
      if (!removed.has_value()) {
        return removed;
      }
    }
  }

  std::set<std::string> referenced_assets;
  for (const auto& [asset_id, asset] : loaded.state.assets) {
    (void)asset_id;
    referenced_assets.insert(asset.artifact.sha256);
  }
  auto asset_names = platform.list_names(assets);
  if (!asset_names.has_value()) {
    return foundation::Result<void>::failure(asset_names.error());
  }
  for (const auto& name : asset_names.value()) {
    const auto path = assets / name;
    const auto stem = path.stem().string();
    if (asset_temp_name(name) ||
        (path.extension() == ".wav" &&
         valid_sha256(stem) &&
         !referenced_assets.contains(stem))) {
      const auto removed = platform.remove(path);
      if (!removed.has_value()) {
        return removed;
      }
    }
  }
  auto bundle_names = platform.list_names(bundle);
  if (!bundle_names.has_value()) {
    return foundation::Result<void>::failure(bundle_names.error());
  }
  for (const auto& name : bundle_names.value()) {
    if (manifest_temp_name(name)) {
      const auto removed = platform.remove(bundle / name);
      if (!removed.has_value()) {
        return removed;
      }
    }
  }
  return foundation::Result<void>::success();
}

nlohmann::json manifest_json(
    std::uint64_t revision,
    const std::vector<std::string>& transactions) {
  return {
      {"contract", "lmdj.project.manifest.v1"},
      {"head_checkpoint",
       "history/checkpoints/" + std::to_string(revision) + ".json"},
      {"head_revision", revision},
      {"transactions", transactions},
  };
}

foundation::Result<bool> publish_artifact(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    const ArtifactStage& stage) {
  const auto directory = bundle / "assets";
  const auto final_path =
      directory / (stage.artifact.sha256 + ".wav");
  auto final_exists = platform.exists(final_path);
  if (!final_exists.has_value()) {
    return foundation::Result<bool>::failure(final_exists.error());
  }
  if (final_exists.value()) {
    const auto described = describe_artifact(
        platform, final_path, stage.artifact.media_type);
    if (!described.has_value() ||
        described.value() != stage.artifact) {
      return foundation::Result<bool>::failure(
          invalid_project(
              "content-addressed asset path contains different bytes",
              final_path));
    }
    return foundation::Result<bool>::success(false);
  }

  if (stage.byte_backed) {
    const auto described = describe_bytes(
        stage.bytes, stage.artifact.media_type);
    if (described != stage.artifact) {
      return foundation::Result<bool>::failure(
          Error{
              ErrorCode::invalid_argument,
              "byte-backed artifact changed while it was imported",
          });
    }
    auto created = platform.create_immutable(final_path, stage.bytes);
    return created.has_value()
               ? foundation::Result<bool>::success(true)
               : foundation::Result<bool>::failure(created.error());
  }

  auto source_bytes = platform.read_complete(stage.source);
  if (!source_bytes.has_value()) {
    return foundation::Result<bool>::failure(source_bytes.error());
  }
  const auto described = describe_bytes(
      source_bytes.value(), stage.artifact.media_type);
  if (described != stage.artifact) {
    return foundation::Result<bool>::failure(
        Error{
            ErrorCode::io_error,
            "source artifact changed while it was imported",
            {{"path", stage.source.generic_string()}},
        });
  }
  auto created = platform.create_immutable(final_path, source_bytes.value());
  return created.has_value()
             ? foundation::Result<bool>::success(true)
             : foundation::Result<bool>::failure(created.error());
}

foundation::Result<domain::AppliedCommand> commit_loaded(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    LoadedProject loaded,
    const PersistedCommand& command,
    const std::optional<ArtifactStage>& artifact_stage,
    PersistedCommand* persisted_identity,
    const std::optional<SequenceFlushIdentity>& sequence_flush_identity =
        std::nullopt) {
  const auto& meta = command_meta(command);
  if (!domain::is_valid_uuid(meta.command_id.value())) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id is not a safe file name",
        });
  }

  const bool replay_candidate =
      loaded.receipts.contains(meta.command_id);
  if (replay_candidate) {
    const auto original = loaded.commands.find(meta.command_id);
    if (original == loaded.commands.end()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          invalid_project(
              "persisted command identity is missing",
              bundle / "manifest.json"));
    }
    if (command_json(original->second) != command_json(command)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "command id is already bound to a different command identity",
          });
    }
    if (persisted_identity != nullptr) {
      *persisted_identity = original->second;
    }
  } else if (persisted_identity != nullptr) {
    *persisted_identity = command;
  }
  const auto applied =
      apply_command(loaded.state, command, loaded.receipts);
  if (!applied.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        applied.error());
  }
  if (applied.value().replayed) {
    return applied;
  }

  const bool sample_import =
      std::holds_alternative<domain::ImportAssignSample>(command);
  if (sample_import) {
    const auto fault = sample_after_event_preparation_fault(bundle);
    if (!fault.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }

  const auto encoded_state = project_json(applied.value().state);
  const auto validated_state =
      parse_project(encoded_state, bundle / "manifest.json");
  if (!validated_state.has_value() ||
      validated_state.value() !=
          persisted_v3_projection(applied.value().state)) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command result cannot be persisted as valid Project Truth",
        });
  }

  std::optional<std::filesystem::path> newly_published_artifact;
  if (artifact_stage.has_value()) {
    const auto published = publish_artifact(*platform, bundle, *artifact_stage);
    if (!published.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          published.error());
    }
    if (published.value()) {
      newly_published_artifact =
          bundle / "assets" / (artifact_stage->artifact.sha256 + ".wav");
    }
  } else if (
      std::holds_alternative<domain::ImportAsset>(command) ||
      sample_import) {
    const domain::Asset* asset = nullptr;
    if (const auto* import = std::get_if<domain::ImportAsset>(&command)) {
      asset = &import->asset;
    } else {
      asset = &std::get<domain::ImportAssignSample>(command).asset;
    }
    if (!valid_sha256(asset->artifact.sha256)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "imported Asset SHA-256 is invalid",
          });
    }
    const auto blob =
        bundle / "assets" /
        (asset->artifact.sha256 + ".wav");
    const auto described = describe_artifact(
        *platform, blob, asset->artifact.media_type);
    if (!described.has_value() ||
        described.value() != asset->artifact) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::missing_asset,
              "import command must reference an existing bundle artifact",
              {{"path", blob.generic_string()}},
          });
    }
  }
  if (sample_import) {
    const auto fault = sample_after_artifact_creation_fault(
        artifact_stage.has_value()
            ? bundle / "assets" /
                  (artifact_stage->artifact.sha256 + ".wav")
            : bundle / "assets");
    if (!fault.has_value()) {
      if (newly_published_artifact.has_value()) {
        const auto removed = platform->remove(*newly_published_artifact);
        if (!removed.has_value()) {
          return foundation::Result<domain::AppliedCommand>::failure(
              removed.error());
        }
      }
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }

  const auto revision = applied.value().state.revision;
  const auto transaction_relative =
      std::filesystem::path{"history/transactions"} /
      (std::to_string(revision) + "-" +
       meta.command_id.value() + ".json");
  const auto checkpoint_relative =
      std::filesystem::path{"history/checkpoints"} /
      (std::to_string(revision) + ".json");
  const auto transaction_final = bundle / transaction_relative;
  const auto checkpoint_final = bundle / checkpoint_relative;

  nlohmann::json transaction = {
      {"command", command_json(command)},
      {"event", applied.value().event},
      {"revision", revision},
  };
  if (sequence_flush_identity.has_value()) {
    transaction["sequence_flush"] = {
        {"command_id", sequence_flush_identity->command_id.value()},
        {"flush_seq", sequence_flush_identity->flush_seq},
        {"pattern_id", sequence_flush_identity->pattern_id.value()},
        {"session_id", sequence_flush_identity->session_id.value()},
    };
  }
  const auto transaction_bytes =
      foundation::canonical_json(transaction) + "\n";
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  if (sequence_flush_identity.has_value()) {
    const auto fault = testing::detail::invoke_fault(
        testing::FaultPoint::sequence_transaction_write, transaction_final);
    if (!fault.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }
#endif
  auto written = platform->create_immutable(
      transaction_final, byte_span(transaction_bytes));
  if (!written.has_value()) {
    if (newly_published_artifact.has_value()) {
      (void)platform->remove(*newly_published_artifact);
    }
    return foundation::Result<domain::AppliedCommand>::failure(
        written.error());
  }

  const auto checkpoint_bytes =
      foundation::canonical_json(project_json(applied.value().state)) + "\n";
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  if (sequence_flush_identity.has_value()) {
    const auto fault = testing::detail::invoke_fault(
        testing::FaultPoint::sequence_checkpoint_write, checkpoint_final);
    if (!fault.has_value()) {
      (void)platform->remove(transaction_final);
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }
#endif
  written = platform->create_immutable(
      checkpoint_final, byte_span(checkpoint_bytes));
  if (!written.has_value()) {
    (void)platform->remove(transaction_final);
    if (newly_published_artifact.has_value()) {
      (void)platform->remove(*newly_published_artifact);
    }
    return foundation::Result<domain::AppliedCommand>::failure(
        written.error());
  }

  loaded.transactions.push_back(transaction_relative.generic_string());
  const auto manifest_bytes = foundation::canonical_json(
                                  manifest_json(revision, loaded.transactions)) +
                              "\n";
  const auto cleanup_unpublished = [&]() -> foundation::Result<void> {
    for (const auto& path : {transaction_final, checkpoint_final}) {
      const auto removed = platform->remove(path);
      if (!removed.has_value()) {
        return removed;
      }
    }
    if (newly_published_artifact.has_value()) {
      const auto removed = platform->remove(*newly_published_artifact);
      if (!removed.has_value()) {
        return removed;
      }
    }
    return foundation::Result<void>::success();
  };
  if (sample_import) {
    const auto fault = sample_after_manifest_preparation_fault(
        bundle / "manifest.json");
    if (!fault.has_value()) {
      const auto cleanup = cleanup_unpublished();
      if (!cleanup.has_value()) {
        return foundation::Result<domain::AppliedCommand>::failure(
            cleanup.error());
      }
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }
  if (!detail::claim_publish()) {
    const auto cleanup = cleanup_unpublished();
    if (!cleanup.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          cleanup.error());
    }
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::internal_error,
            "Project mutation was cancelled before publication",
        });
  }
  if (detail::force_publish_failure()) {
    detail::abort_publish();
    const auto cleanup = cleanup_unpublished();
    if (!cleanup.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          cleanup.error());
    }
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::io_error,
            "Project manifest publication failed",
            {{"stage", "manifest_settlement"}},
        });
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  if (sequence_flush_identity.has_value()) {
    const auto fault = testing::detail::invoke_fault(
        testing::FaultPoint::sequence_manifest_publish,
        bundle / "manifest.json");
    if (!fault.has_value()) {
      detail::abort_publish();
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }
#endif
  written = platform->replace_complete(
      bundle / "manifest.json", byte_span(manifest_bytes));
  if (!written.has_value()) {
    detail::abort_publish();
    return foundation::Result<domain::AppliedCommand>::failure(
        written.error());
  }
  detail::commit_publish();

  if (sample_import) {
    const auto fault = sample_after_manifest_publication_fault(
        bundle / "manifest.json");
    if (!fault.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }

  return applied;
}

foundation::Result<void> create_bundle_directories(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  const std::array paths{
      bundle,
      bundle / "assets",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
      bundle / "recovery/active",
      bundle / "recovery/sealed",
  };
  for (const auto& path : paths) {
    const auto ensured = platform.ensure_directory(path);
    if (!ensured.has_value()) {
      return ensured;
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<domain::AppliedCommand> execute_persisted(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    const PersistedCommand& command) {
  auto tree = validate_managed_bundle_tree(*platform, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
  auto lock_result = platform->acquire_writer(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(*platform, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
  auto loaded = load_project(*platform, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(*platform, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        recovered.error());
  }
  return commit_loaded(
      platform,
      bundle,
      std::move(loaded.value()),
      command,
      std::nullopt,
      nullptr);
}

}  // namespace

ProjectStore::ProjectStore()
    : ProjectStore(make_default_project_storage_platform()) {}

ProjectStore::ProjectStore(std::shared_ptr<ProjectStoragePlatform> platform)
    : platform_(platform != nullptr
                    ? std::move(platform)
                    : make_default_project_storage_platform()) {}

foundation::Result<void> ProjectStore::create(
    const std::filesystem::path& bundle,
    const domain::ProjectState& initial) {
  if (bundle.extension() != ".lmdj" || initial.revision != 0) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "project bundle must end in .lmdj and start at revision zero",
        });
  }
  const auto persisted_initial = persisted_v3_projection(initial);
  const auto encoded = project_json(persisted_initial);
  const auto validated = parse_project(encoded, bundle);
  if (!validated.has_value() || validated.value() != persisted_initial) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "initial project state is invalid",
        });
  }
  const auto existing_tree = platform_->validate_managed_tree(bundle);
  if (!existing_tree.has_value()) {
    return existing_tree;
  }
  auto directories = create_bundle_directories(*platform_, bundle);
  if (!directories.has_value()) {
    return directories;
  }
  auto lock_result = platform_->acquire_writer(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<void>::failure(lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  const auto locked_tree = platform_->validate_managed_tree(bundle);
  if (!locked_tree.has_value()) {
    return locked_tree;
  }
  auto manifest_exists = platform_->exists(bundle / "manifest.json");
  if (!manifest_exists.has_value()) {
    return foundation::Result<void>::failure(manifest_exists.error());
  }
  if (manifest_exists.value()) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::duplicate_id,
            "project bundle already has a manifest",
            {{"path", bundle.generic_string()}},
        });
  }

  const auto checkpoint_final =
      bundle / "history/checkpoints/0.json";
  const auto recovered = recover_initial_create_residue(*platform_, bundle);
  if (!recovered.has_value()) {
    return recovered;
  }

  const auto checkpoint_bytes =
      foundation::canonical_json(encoded) + "\n";
  auto checkpoint_exists = platform_->exists(checkpoint_final);
  if (!checkpoint_exists.has_value()) {
    return foundation::Result<void>::failure(checkpoint_exists.error());
  }
  if (checkpoint_exists.value()) {
    auto existing_json = read_json(*platform_, checkpoint_final);
    auto existing_bytes = read_file_bytes(*platform_, checkpoint_final);
    if (!existing_json.has_value() || !existing_bytes.has_value()) {
      return foundation::Result<void>::failure(
          invalid_project(
              "existing initial checkpoint could not be validated",
              checkpoint_final));
    }
    auto existing_state =
        parse_project(existing_json.value(), checkpoint_final);
    if (!existing_state.has_value() ||
        existing_state.value() != persisted_initial ||
        existing_bytes.value() != checkpoint_bytes) {
      return foundation::Result<void>::failure(
          invalid_project(
              "existing initial checkpoint does not match requested Project",
              checkpoint_final));
    }
  } else {
    auto written = platform_->create_immutable(
        checkpoint_final, byte_span(checkpoint_bytes));
    if (!written.has_value()) {
      return written;
    }
  }

  const auto manifest_bytes =
      foundation::canonical_json(manifest_json(0, {})) + "\n";
  if (!detail::claim_publish()) {
    const auto cleanup = platform_->remove(checkpoint_final);
    return cleanup.has_value()
               ? foundation::Result<void>::failure(
                     Error{
                         ErrorCode::internal_error,
                         "Project creation was cancelled before publication",
                     })
               : cleanup;
  }
  if (detail::force_publish_failure()) {
    detail::abort_publish();
    const auto cleanup = platform_->remove(checkpoint_final);
    return cleanup.has_value()
               ? foundation::Result<void>::failure(
                     Error{
                         ErrorCode::io_error,
                         "Project manifest publication failed",
                         {{"stage", "manifest_settlement"}},
                     })
               : cleanup;
  }
  auto written = platform_->replace_complete(
      bundle / "manifest.json", byte_span(manifest_bytes));
  if (!written.has_value()) {
    detail::abort_publish();
    return written;
  }
  detail::commit_publish();
  return foundation::Result<void>::success();
}

foundation::Result<domain::ProjectState> ProjectStore::load(
    const std::filesystem::path& bundle) const {
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::ProjectState>::failure(tree.error());
  }
  auto lock_result = platform_->acquire_writer(bundle);
  const auto writer_busy =
      !lock_result.has_value() && lock_result.error().details.is_object() &&
      lock_result.error().details.value("storage_condition", std::string{}) ==
          kStorageConditionProjectBusy;
  if (!lock_result.has_value() && !writer_busy) {
    return foundation::Result<domain::ProjectState>::failure(
        lock_result.error());
  }
  std::unique_ptr<ProjectWriterLease> lock;
  if (lock_result.has_value()) {
    lock = std::move(lock_result.value());
    tree = validate_managed_bundle_tree(*platform_, bundle);
    if (!tree.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(tree.error());
    }
  }
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<domain::ProjectState>::failure(
        loaded.error());
  }
  if (lock != nullptr) {
    const auto recovered =
        recover_uncommitted(*platform_, bundle, loaded.value());
    if (!recovered.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(
          recovered.error());
    }
    const auto scavenged = scavenge_sample_staging(*platform_, bundle);
    if (!scavenged.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(
          scavenged.error());
    }
  }
  return foundation::Result<domain::ProjectState>::success(
      std::move(loaded.value().state));
}

foundation::Result<CommandExecution> ProjectStore::execute_with_identity(
    const std::filesystem::path& bundle,
    const domain::Command& command) {
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<CommandExecution>::failure(tree.error());
  }
  auto lock_result = platform_->acquire_writer(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<CommandExecution>::failure(tree.error());
  }
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        recovered.error());
  }
  auto persisted_identity = persisted_command(command);
  auto outcome = commit_loaded(
      platform_,
      bundle,
      std::move(loaded.value()),
      persisted_identity,
      std::nullopt,
      &persisted_identity);
  if (!outcome.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        outcome.error());
  }
  auto returned_identity = legacy_command(persisted_identity);
  if (!returned_identity.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        returned_identity.error());
  }
  return foundation::Result<CommandExecution>::success(
      CommandExecution{
          std::move(returned_identity.value()),
          std::move(outcome.value()),
      });
}

foundation::Result<domain::AppliedCommand> ProjectStore::execute(
    const std::filesystem::path& bundle,
    const domain::Command& command) {
  auto executed = execute_with_identity(bundle, command);
  if (!executed.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        executed.error());
  }
  return foundation::Result<domain::AppliedCommand>::success(
      std::move(executed.value().outcome));
}

foundation::Result<domain::AppliedCommand> ProjectStore::execute(
    const std::filesystem::path& bundle,
    const domain::UpdatePadPlayback& command) {
  return execute_persisted(platform_, bundle, PersistedCommand{command});
}

foundation::Result<domain::AppliedCommand> ProjectStore::execute(
    const std::filesystem::path& bundle,
    const domain::ResetPadPlayback& command) {
  return execute_persisted(platform_, bundle, PersistedCommand{command});
}

foundation::Result<std::optional<SequenceFlushExecution>>
ProjectStore::replay_sequence_flush(
    const std::filesystem::path& bundle,
    const SequenceFlushIdentity& identity) {
  if (!domain::is_valid_uuid(identity.session_id.value()) ||
      !domain::is_valid_uuid(identity.command_id.value()) ||
      !domain::is_valid_uuid(identity.pattern_id.value())) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence flush identity is invalid",
        });
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::failure(tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::failure(loaded.error());
  }
  const auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::failure(recovered.error());
  }
  const auto original = loaded.value().commands.find(identity.command_id);
  if (original == loaded.value().commands.end()) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::success(std::nullopt);
  }
  const auto stored_identity =
      loaded.value().sequence_flush_identities.find(identity.command_id);
  const auto* merge =
      std::get_if<domain::MergePatternEvents>(&original->second);
  if (stored_identity == loaded.value().sequence_flush_identities.end() ||
      stored_identity->second != identity || merge == nullptr ||
      merge->pattern_id != identity.pattern_id) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence flush identity does not match the persisted command",
        });
  }
  const auto receipt = loaded.value().receipts.find(identity.command_id);
  if (receipt == loaded.value().receipts.end()) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::failure(
        invalid_project(
            "persisted Sequence flush receipt is missing",
            bundle / "manifest.json"));
  }
  return foundation::Result<
      std::optional<SequenceFlushExecution>>::success(
      SequenceFlushExecution{
          identity,
          *merge,
          domain::AppliedCommand{
              std::move(loaded.value().state),
              receipt->second.event,
              true,
          },
      });
}

foundation::Result<std::optional<SequenceFlushExecution>>
ProjectStore::replay_sequence_flush(
    const std::filesystem::path& bundle,
    const foundation::SequenceSessionId& session_id,
    const foundation::CommandId& command_id) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(command_id.value())) {
    return foundation::Result<
        std::optional<SequenceFlushExecution>>::failure(
        Error{ErrorCode::invalid_argument,
              "Sequence flush replay identity is invalid"});
  }
  std::optional<SequenceFlushIdentity> identity;
  {
    auto tree = validate_managed_bundle_tree(*platform_, bundle);
    if (!tree.has_value()) {
      return foundation::Result<
          std::optional<SequenceFlushExecution>>::failure(tree.error());
    }
    auto lease = platform_->acquire_writer(bundle);
    if (!lease.has_value()) {
      return foundation::Result<
          std::optional<SequenceFlushExecution>>::failure(lease.error());
    }
    auto operation = std::move(lease.value());
    (void)operation;
    auto loaded = load_project(*platform_, bundle);
    if (!loaded.has_value()) {
      return foundation::Result<
          std::optional<SequenceFlushExecution>>::failure(loaded.error());
    }
    const auto recovered =
        recover_uncommitted(*platform_, bundle, loaded.value());
    if (!recovered.has_value()) {
      return foundation::Result<
          std::optional<SequenceFlushExecution>>::failure(recovered.error());
    }
    if (!loaded.value().commands.contains(command_id)) {
      return foundation::Result<
          std::optional<SequenceFlushExecution>>::success(std::nullopt);
    }
    const auto stored =
        loaded.value().sequence_flush_identities.find(command_id);
    if (stored == loaded.value().sequence_flush_identities.end() ||
        stored->second.session_id != session_id) {
      return foundation::Result<
          std::optional<SequenceFlushExecution>>::failure(Error{
          ErrorCode::invalid_argument,
          "Sequence flush identity does not match the persisted command",
      });
    }
    identity = stored->second;
  }
  return replay_sequence_flush(bundle, *identity);
}

foundation::Result<SequenceFlushExecution>
ProjectStore::execute_sequence_flush(
    const std::filesystem::path& bundle,
    const SequenceFlushIdentity& identity) {
  SequenceJournal journal{platform_};
  auto active = journal.read_active(bundle);
  if (!active.has_value()) {
    return foundation::Result<SequenceFlushExecution>::failure(active.error());
  }
  if (active.value().session_id != identity.session_id) {
    return foundation::Result<SequenceFlushExecution>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence flush session does not match the active Journal",
        });
  }
  const auto flush = std::find_if(
      active.value().flushes.begin(), active.value().flushes.end(),
      [&identity](const auto& candidate) {
        return candidate.flush_seq == identity.flush_seq;
      });
  if (flush == active.value().flushes.end() ||
      flush->command_id != identity.command_id ||
      flush->pattern_id != identity.pattern_id) {
    return foundation::Result<SequenceFlushExecution>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence flush identity is not durably journaled",
        });
  }
  const domain::MergePatternEvents command{
      {identity.command_id, flush->expected_revision},
      identity.pattern_id,
      flush->canonical_events,
  };

  auto committed = [&]() -> foundation::Result<domain::AppliedCommand> {
    auto tree = validate_managed_bundle_tree(*platform_, bundle);
    if (!tree.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(tree.error());
    }
    auto lease = platform_->acquire_writer(bundle);
    if (!lease.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(lease.error());
    }
    auto operation = std::move(lease.value());
    (void)operation;
    auto loaded = load_project(*platform_, bundle);
    if (!loaded.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          loaded.error());
    }
    auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
    if (!recovered.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          recovered.error());
    }
    auto locked_active = journal.read_active(bundle);
    if (!locked_active.has_value() ||
        locked_active.value().session_id != identity.session_id) {
      return foundation::Result<domain::AppliedCommand>::failure(
          locked_active.has_value()
              ? Error{
                    ErrorCode::invalid_argument,
                    "Sequence Journal changed before flush admission",
                }
              : locked_active.error());
    }
    const auto locked_flush = std::find_if(
        locked_active.value().flushes.begin(),
        locked_active.value().flushes.end(),
        [&identity](const auto& candidate) {
          return candidate.flush_seq == identity.flush_seq;
        });
    if (locked_flush == locked_active.value().flushes.end() ||
        locked_flush->command_id != identity.command_id ||
        locked_flush->pattern_id != identity.pattern_id ||
        locked_flush->expected_revision != flush->expected_revision ||
        locked_flush->canonical_events != flush->canonical_events) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "Sequence Journal changed before flush admission",
          });
    }
    const auto existing =
        loaded.value().sequence_flush_identities.find(identity.command_id);
    if (loaded.value().receipts.contains(identity.command_id) &&
        (existing == loaded.value().sequence_flush_identities.end() ||
         existing->second != identity)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "command id is bound to a different Sequence flush identity",
          });
    }
    auto persisted = PersistedCommand{command};
    return commit_loaded(
        platform_, bundle, std::move(loaded.value()), persisted,
        std::nullopt, nullptr, identity);
  }();
  if (!committed.has_value()) {
    return foundation::Result<SequenceFlushExecution>::failure(
        committed.error());
  }

#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto visibility_fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_receipt_reload,
      bundle / "manifest.json");
  if (!visibility_fault.has_value()) {
    return foundation::Result<SequenceFlushExecution>::failure(
        visibility_fault.error());
  }
#endif
  auto visible = replay_sequence_flush(bundle, identity);
  if (!visible.has_value()) {
    return foundation::Result<SequenceFlushExecution>::failure(
        visible.error());
  }
  if (!visible.value().has_value()) {
    return foundation::Result<SequenceFlushExecution>::failure(
        Error{
            ErrorCode::io_error,
            "Sequence flush receipt is not visible from the manifest head",
        });
  }
  const auto pattern =
      visible.value()->outcome.state.patterns.find(identity.pattern_id);
  if (pattern == visible.value()->outcome.state.patterns.end()) {
    return foundation::Result<SequenceFlushExecution>::failure(
        Error{
            ErrorCode::invalid_project,
            "Sequence flush target disappeared after manifest publication",
        });
  }
  auto completed = journal.complete_flush(
      bundle, identity.session_id, identity.flush_seq,
      visible.value()->outcome.state.revision,
      sequence_pattern_fingerprint(pattern->second));
  if (!completed.has_value()) {
    return foundation::Result<SequenceFlushExecution>::failure(
        completed.error());
  }
  auto result = std::move(*visible.value());
  result.outcome.replayed = committed.value().replayed;
  return foundation::Result<SequenceFlushExecution>::success(
      std::move(result));
}

foundation::Result<std::vector<SequenceRecoveryCandidate>>
ProjectStore::reconcile_sequence_recovery(
    const std::filesystem::path& bundle) {
  SequenceJournal journal{platform_};
  auto active = journal.read_active(bundle);
  if (!active.has_value()) {
    if (active.error().code == ErrorCode::not_found) {
      return journal.list_recoverable(bundle);
    }
    return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
        active.error());
  }
  for (const auto& flush : active.value().flushes) {
    if (flush.completed) {
      continue;
    }
    const SequenceFlushIdentity identity{
        active.value().session_id,
        flush.flush_seq,
        flush.command_id,
        flush.pattern_id,
    };
    auto visible = replay_sequence_flush(bundle, identity);
    if (!visible.has_value()) {
      return foundation::Result<
          std::vector<SequenceRecoveryCandidate>>::failure(visible.error());
    }
    if (!visible.value().has_value()) {
      continue;
    }
    const auto pattern =
        visible.value()->outcome.state.patterns.find(identity.pattern_id);
    if (pattern == visible.value()->outcome.state.patterns.end()) {
      return foundation::Result<
          std::vector<SequenceRecoveryCandidate>>::failure(
          Error{
              ErrorCode::invalid_project,
              "committed Sequence flush target is missing",
          });
    }
    auto completed = journal.complete_flush(
        bundle, identity.session_id, identity.flush_seq,
        visible.value()->outcome.state.revision,
        sequence_pattern_fingerprint(pattern->second));
    if (!completed.has_value()) {
      return foundation::Result<
          std::vector<SequenceRecoveryCandidate>>::failure(completed.error());
    }
  }
  active = journal.read_active(bundle);
  if (!active.has_value()) {
    return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
        active.error());
  }
  const bool has_pending = std::any_of(
      active.value().flushes.begin(), active.value().flushes.end(),
      [](const auto& flush) { return !flush.completed; });
  if (has_pending || active.value().flushes.empty()) {
    auto sealed = journal.seal(
        bundle, active.value().session_id, "owner_lost");
    if (!sealed.has_value()) {
      return foundation::Result<
          std::vector<SequenceRecoveryCandidate>>::failure(sealed.error());
    }
  } else {
    auto removed = journal.remove_active_if_complete(
        bundle, active.value().session_id);
    if (!removed.has_value()) {
      return foundation::Result<
          std::vector<SequenceRecoveryCandidate>>::failure(removed.error());
    }
  }
  return journal.list_recoverable(bundle);
}

foundation::Result<ImportArtifactExecution>
ProjectStore::import_artifact_with_identity(
    const std::filesystem::path& bundle,
    const ImportArtifactRequest& request) {
  if (!domain::is_valid_uuid(request.meta.command_id.value())) {
    return foundation::Result<ImportArtifactExecution>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id must be a lowercase UUID",
        });
  }
  if (!domain::is_valid_uuid(request.asset_id.value())) {
    return foundation::Result<ImportArtifactExecution>::failure(
        Error{
            ErrorCode::invalid_argument,
            "asset id must be a lowercase UUID",
        });
  }
  if (request.media_type.empty()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact media type must not be empty",
        });
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        tree.error());
  }
  auto lock_result = platform_->acquire_writer(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        tree.error());
  }
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        recovered.error());
  }

  const auto original =
      loaded.value().commands.find(request.meta.command_id);
  if (original != loaded.value().commands.end()) {
    const auto* import =
        std::get_if<domain::ImportAsset>(&original->second);
    if (import == nullptr) {
      return foundation::Result<ImportArtifactExecution>::failure(
          Error{
              ErrorCode::invalid_argument,
              "command id belongs to a different command type",
          });
    }
    if (import->meta.expected_revision !=
            request.meta.expected_revision ||
        import->asset.id != request.asset_id ||
        import->asset.artifact.media_type != request.media_type) {
      return foundation::Result<ImportArtifactExecution>::failure(
          Error{
              ErrorCode::invalid_argument,
              "asset import replay identity does not match persisted ImportAsset",
          });
    }
    const auto described = describe_artifact(
        *platform_, request.source, request.media_type);
    if (described.has_value() &&
        described.value() != import->asset.artifact) {
      return foundation::Result<ImportArtifactExecution>::failure(
          Error{
              ErrorCode::invalid_argument,
              "asset import source bytes do not match persisted ImportAsset",
          });
    }
    const auto receipt =
        loaded.value().receipts.find(request.meta.command_id);
    if (receipt == loaded.value().receipts.end()) {
      return foundation::Result<ImportArtifactExecution>::failure(
          invalid_project(
              "persisted ImportAsset receipt is missing",
              bundle / "manifest.json"));
    }
    return foundation::Result<ImportArtifactExecution>::success(
        ImportArtifactExecution{
            *import,
            domain::AppliedCommand{
                std::move(loaded.value().state),
                receipt->second.event,
                true,
            },
        });
  }
  const auto described =
      describe_artifact(*platform_, request.source, request.media_type);
  if (!described.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        described.error());
  }
  const PersistedCommand command = domain::ImportAsset{
      request.meta,
      domain::Asset{request.asset_id, described.value()},
  };
  auto persisted_identity = command;
  auto outcome = commit_loaded(
      platform_,
      bundle,
      std::move(loaded.value()),
      command,
      ArtifactStage{
          request.source,
          described.value(),
          {},
          false,
      },
      &persisted_identity);
  if (!outcome.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        outcome.error());
  }
  const auto* import =
      std::get_if<domain::ImportAsset>(&persisted_identity);
  if (import == nullptr) {
    return foundation::Result<ImportArtifactExecution>::failure(
        invalid_project(
            "persisted import outcome has the wrong command type",
            bundle / "manifest.json"));
  }
  return foundation::Result<ImportArtifactExecution>::success(
      ImportArtifactExecution{
          *import,
          std::move(outcome.value()),
      });
}

foundation::Result<domain::AppliedCommand> ProjectStore::import_artifact(
    const std::filesystem::path& bundle,
    const ImportArtifactRequest& request) {
  auto imported = import_artifact_with_identity(bundle, request);
  if (!imported.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        imported.error());
  }
  return foundation::Result<domain::AppliedCommand>::success(
      std::move(imported.value().outcome));
}

foundation::Result<domain::AppliedCommand> ProjectStore::import_artifact_bytes(
    const std::filesystem::path& bundle,
    const ImportArtifactBytesRequest& request) {
  if (!domain::is_valid_uuid(request.meta.command_id.value())) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id must be a lowercase UUID",
        });
  }
  if (!domain::is_valid_uuid(request.asset_id.value())) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "asset id must be a lowercase UUID",
        });
  }
  if (request.media_type.empty()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact media type must not be empty",
        });
  }
  if (request.bytes.size() > kMaximumArtifactBytes) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact exceeds the Project import limit",
            {{"maximum_byte_length", kMaximumArtifactBytes}},
        });
  }
  // Validate the bundle before hashing: describe_bytes runs SHA-256 over the
  // whole artifact, and doing that before a cheap existence check means a
  // missing or malformed bundle costs a full hash of bytes that are then
  // thrown away. The refusal is identical either way - the bundle error wins
  // in both orders - so this only removes wasted work.
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
  const auto artifact = describe_bytes(request.bytes, request.media_type);

  auto lock_result = platform_->acquire_writer(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(
      *platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        recovered.error());
  }

  const auto original =
      loaded.value().commands.find(request.meta.command_id);
  if (original != loaded.value().commands.end()) {
    const auto* import =
        std::get_if<domain::ImportAsset>(&original->second);
    if (import == nullptr) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "command id belongs to a different command type",
          });
    }
    if (import->meta.expected_revision != request.meta.expected_revision ||
        import->asset.id != request.asset_id ||
        import->asset.artifact != artifact) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "asset import replay identity does not match persisted ImportAsset",
          });
    }
    const auto receipt =
        loaded.value().receipts.find(request.meta.command_id);
    if (receipt == loaded.value().receipts.end()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          invalid_project(
              "persisted ImportAsset receipt is missing",
              bundle / "manifest.json"));
    }
    return foundation::Result<domain::AppliedCommand>::success(
        domain::AppliedCommand{
            std::move(loaded.value().state),
            receipt->second.event,
            true,
        });
  }

  const PersistedCommand command = domain::ImportAsset{
      request.meta,
      domain::Asset{request.asset_id, artifact},
  };
  auto outcome = commit_loaded(
      platform_,
      bundle,
      std::move(loaded.value()),
      command,
      ArtifactStage{
          {},
          artifact,
          request.bytes,
          true,
      },
      nullptr);
  if (!outcome.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        outcome.error());
  }
  return outcome;
}

foundation::Result<domain::AppliedCommand>
ProjectStore::import_assign_sample_bytes(
    const std::filesystem::path& bundle,
    const ImportAssignSampleBytesRequest& request) {
  if (!domain::is_valid_uuid(request.meta.command_id.value())) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id must be a lowercase UUID",
        });
  }
  if (!domain::is_valid_slot(request.slot)) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "pad slot is invalid",
        });
  }
  if (!domain::is_valid_uuid(request.asset_id.value())) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "asset id must be a lowercase UUID",
        });
  }
  if (request.media_type.empty()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact media type must not be empty",
        });
  }
  if (request.bytes.size() > kMaximumArtifactBytes) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact exceeds the Project import limit",
            {{"maximum_byte_length", kMaximumArtifactBytes}},
        });
  }
  // Same ordering point as the byte import above: the cheap bundle check
  // precedes the full-artifact hash, so a missing bundle no longer costs one.
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
  const auto artifact = describe_bytes(request.bytes, request.media_type);
  const PersistedCommand command = domain::ImportAssignSample{
      request.meta,
      domain::Asset{request.asset_id, artifact},
      request.slot,
  };
  auto lock_result = platform_->acquire_writer(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(
      *platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        recovered.error());
  }
  const auto scavenged = scavenge_sample_staging(*platform_, bundle);
  if (!scavenged.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        scavenged.error());
  }

  if (loaded.value().receipts.contains(request.meta.command_id)) {
    return commit_loaded(
        platform_,
        bundle,
        std::move(loaded.value()),
        command,
        std::nullopt,
        nullptr);
  }

  auto staged = stage_sample(
      *platform_,
      bundle,
      request.meta.command_id.value(),
      request.bytes);
  if (!staged.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        staged.error());
  }
  const auto cleanup_staging = [&]() {
    return platform_->remove_tree(staged.value().directory);
  };
  const auto staged_fault =
      sample_after_staging_fault(staged.value().directory);
  if (!staged_fault.has_value()) {
    const auto cleanup = cleanup_staging();
    return foundation::Result<domain::AppliedCommand>::failure(
        cleanup.has_value() ? staged_fault.error() : cleanup.error());
  }

  auto outcome = commit_loaded(
      platform_,
      bundle,
      std::move(loaded.value()),
      command,
      ArtifactStage{
          staged.value().payload,
          artifact,
          {},
          false,
      },
      nullptr);
  const auto cleanup = cleanup_staging();
  if (!outcome.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        outcome.error());
  }
  if (!cleanup.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        cleanup.error());
  }
  return outcome;
}

foundation::Result<std::vector<std::byte>> ProjectStore::read_artifact(
    const std::filesystem::path& bundle,
    const foundation::ArtifactRef& artifact) const {
  if (!valid_sha256(artifact.sha256) || artifact.media_type.empty()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact reference is invalid",
        });
  }
  if (artifact.byte_length > kMaximumArtifactBytes) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact exceeds the Project read limit",
            {{"maximum_byte_length", kMaximumArtifactBytes}},
        });
  }

  if (bundle.extension() != ".lmdj") {
    return foundation::Result<std::vector<std::byte>>::failure(
        invalid_project("project bundle extension is invalid", bundle));
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        tree.error());
  }
  auto lock_result = platform_->acquire_writer(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        tree.error());
  }

  const auto path =
      bundle / "assets" / (artifact.sha256 + ".wav");
  auto existing = platform_->exists(path);
  if (!existing.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        existing.error());
  }
  if (!existing.value()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::not_found,
            "project artifact does not exist",
            {{"path", path.generic_string()}},
        });
  }
  auto length = platform_->byte_length(path);
  if (!length.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(length.error());
  }
  if (length.value() != artifact.byte_length) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::cook_failed,
            "project artifact byte length does not match its reference",
            {{"path", path.generic_string()}},
        });
  }
  auto read = platform_->read_complete(path);
  if (!read.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(read.error());
  }
  auto bytes = std::move(read.value());
  if (bytes.size() != artifact.byte_length) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::cook_failed,
            "project artifact byte length changed while it was being read",
            {{"path", path.generic_string()}},
        });
  }

  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* hash_begin =
        reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(hash_begin, hash_begin + bytes.size());
  }
  hasher.finish();
  if (picosha2::get_hash_hex_string(hasher) != artifact.sha256) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::cook_failed,
            "project artifact hash does not match its reference",
            {{"path", path.generic_string()}},
        });
  }
  return foundation::Result<std::vector<std::byte>>::success(
      std::move(bytes));
}

}  // namespace lmdj::project_io
