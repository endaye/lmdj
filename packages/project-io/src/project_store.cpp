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
#include <lmdj/project_io/take_journal.hpp>

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
    domain::RecordTake,
    domain::CreatePattern,
    domain::ImportAssignSample,
    domain::UpdatePadPlayback,
    domain::ResetPadPlayback>;

struct LoadedProject {
  domain::ProjectState state;
  std::map<foundation::CommandId, PersistedCommand> commands;
  std::map<foundation::CommandId, domain::CommandReceipt> receipts;
  std::map<foundation::CommandId, foundation::TakeId> cleanup_obligations;
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
      {"slot", slot_json(event.slot)},
      {"step", event.step},
      {"velocity", event.velocity},
  };
}

nlohmann::json raw_take_event_json(const domain::RawTakeEvent& event) {
  return {
      {"frame_offset", event.frame_offset},
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

nlohmann::json take_value_json(const domain::RawTake& take) {
  auto events = nlohmann::json::array();
  for (const auto& event : take.events) {
    events.push_back(raw_take_event_json(event));
  }
  return {
      {"events", std::move(events)},
      {"sample_rate", take.sample_rate},
  };
}

nlohmann::json take_json(const domain::RawTake& take) {
  auto encoded = take_value_json(take);
  encoded["id"] = take.id.value();
  return encoded;
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
      if (state.contract == domain::ProjectContract::v2) {
        encoded_pad["playback"] = playback_json(slot.playback);
      }
      pads.push_back(std::move(encoded_pad));
    }
    banks.push_back(
        {
            {"bank", bank},
            {"pads", std::move(pads)},
        });
  }

  auto assets = nlohmann::json::object();
  for (const auto& [id, asset] : state.assets) {
    assets[id.value()] = {{"artifact", asset.artifact}};
  }
  auto takes = nlohmann::json::object();
  for (const auto& [id, take] : state.takes) {
    takes[id.value()] = take_value_json(take);
  }
  auto patterns = nlohmann::json::object();
  for (const auto& [id, pattern] : state.patterns) {
    patterns[id.value()] = pattern_value_json(pattern);
  }
  return {
      {"assets", std::move(assets)},
      {"banks", std::move(banks)},
      {"bpm", state.bpm},
      {"contract",
       state.contract == domain::ProjectContract::v1 ? "lmdj.project.v1"
                                                     : "lmdj.project.v2"},
      {"patterns", std::move(patterns)},
      {"project_id", state.id.value()},
      {"revision", state.revision},
      {"takes", std::move(takes)},
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
    const std::filesystem::path& path) {
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
    const auto step_limit =
        static_cast<std::uint32_t>(pattern.bars) * 16;
    for (const auto& encoded : input.at("events")) {
      if (!exact_object_keys(
              encoded, {"slot", "step", "velocity"})) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event shape is invalid", path));
      }
      const auto step = unsigned_integer_value(encoded.at("step"));
      const auto velocity =
          unsigned_integer_value(encoded.at("velocity"));
      if (!step.has_value() || !velocity.has_value() ||
          *step > std::numeric_limits<std::uint32_t>::max() ||
          *velocity > std::numeric_limits<std::uint8_t>::max()) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event is invalid", path));
      }
      auto slot = parse_slot(encoded.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<domain::Pattern>::failure(slot.error());
      }
      domain::PatternEvent event{
          slot.value(),
          static_cast<std::uint32_t>(*step),
          static_cast<std::uint8_t>(*velocity),
      };
      if (event.velocity < 1 || event.velocity > 127 ||
          event.step >= step_limit) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event is invalid", path));
      }
      pattern.events.push_back(event);
    }
    return foundation::Result<domain::Pattern>::success(std::move(pattern));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::Pattern>::failure(
        invalid_project(
            "project pattern could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<domain::RawTake> parse_take(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(
            input, {"events", "id", "sample_rate"}) ||
        !input.at("events").is_array()) {
      return foundation::Result<domain::RawTake>::failure(
          invalid_project("project raw take shape is invalid", path));
    }
    const auto sample_rate =
        unsigned_integer_value(input.at("sample_rate"));
    if (!sample_rate.has_value() || *sample_rate != 48000) {
      return foundation::Result<domain::RawTake>::failure(
          invalid_project("project raw take metadata is invalid", path));
    }
    domain::RawTake take{
        foundation::TakeId{input.at("id").get<std::string>()},
        static_cast<std::uint32_t>(*sample_rate),
        {},
    };
    if (!domain::is_valid_uuid(take.id.value()) ||
        take.sample_rate != 48000) {
      return foundation::Result<domain::RawTake>::failure(
          invalid_project("project raw take metadata is invalid", path));
    }
    for (const auto& encoded : input.at("events")) {
      if (!exact_object_keys(
              encoded, {"frame_offset", "slot", "velocity"})) {
        return foundation::Result<domain::RawTake>::failure(
            invalid_project("project raw take event shape is invalid", path));
      }
      const auto frame_offset =
          unsigned_integer_value(encoded.at("frame_offset"));
      const auto velocity =
          unsigned_integer_value(encoded.at("velocity"));
      if (!frame_offset.has_value() || !velocity.has_value() ||
          *frame_offset >
              std::numeric_limits<std::uint32_t>::max() ||
          *velocity > std::numeric_limits<std::uint8_t>::max()) {
        return foundation::Result<domain::RawTake>::failure(
            invalid_project("project raw take event is invalid", path));
      }
      auto slot = parse_slot(encoded.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<domain::RawTake>::failure(slot.error());
      }
      domain::RawTakeEvent event{
          slot.value(),
          static_cast<std::uint32_t>(*frame_offset),
          static_cast<std::uint8_t>(*velocity),
      };
      if (event.velocity < 1 || event.velocity > 127) {
        return foundation::Result<domain::RawTake>::failure(
            invalid_project("project raw take event is invalid", path));
      }
      take.events.push_back(event);
    }
    return foundation::Result<domain::RawTake>::success(std::move(take));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::RawTake>::failure(
        invalid_project(
            "project raw take could not be parsed",
            path,
            exception.what()));
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
  return parse_pattern(encoded, path);
}

foundation::Result<domain::RawTake> parse_project_take(
    std::string_view id,
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  if (!domain::is_valid_uuid(id) ||
      !exact_object_keys(input, {"events", "sample_rate"})) {
    return foundation::Result<domain::RawTake>::failure(
        invalid_project("project raw take entry is invalid", path));
  }
  auto encoded = input;
  encoded["id"] = id;
  return parse_take(encoded, path);
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
    if (!exact_object_keys(
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
            }) ||
        (!is_v1 && !is_v2) ||
        !nonnegative_integer(input.at("revision")) ||
        !nonnegative_integer(input.at("bpm")) ||
        !input.at("banks").is_array() ||
        !input.at("assets").is_object() ||
        !input.at("takes").is_object() ||
        !input.at("patterns").is_object()) {
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
    state.contract = is_v1 ? domain::ProjectContract::v1
                           : domain::ProjectContract::v2;
    state.revision = *revision;

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
        if (is_v2) {
          auto playback = parse_playback(encoded_pad.at("playback"), path);
          if (!playback.has_value()) {
            return foundation::Result<domain::ProjectState>::failure(
                playback.error());
          }
          state.banks.at(*bank).at(*pad).playback = playback.value();
        }
      }
    }

    for (auto iterator = input.at("assets").begin();
         iterator != input.at("assets").end();
         ++iterator) {
      const auto& encoded = iterator.value();
      if (!domain::is_valid_uuid(iterator.key()) ||
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
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project asset entry is invalid", path));
      }
      domain::Asset asset{
          foundation::AssetId{iterator.key()},
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
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project artifact reference is invalid", path));
      }
      state.assets.emplace(asset.id, asset);
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

    for (auto iterator = input.at("takes").begin();
         iterator != input.at("takes").end();
         ++iterator) {
      auto take =
          parse_project_take(iterator.key(), iterator.value(), path);
      if (!take.has_value()) {
        return foundation::Result<domain::ProjectState>::failure(take.error());
      }
      state.takes.emplace(take.value().id, take.value());
    }
    for (auto iterator = input.at("patterns").begin();
         iterator != input.at("patterns").end();
         ++iterator) {
      auto pattern = parse_project_pattern(
          iterator.key(), iterator.value(), path);
      if (!pattern.has_value()) {
        return foundation::Result<domain::ProjectState>::failure(
            pattern.error());
      }
      state.patterns.emplace(pattern.value().id, pattern.value());
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
        } else if constexpr (std::is_same_v<Type, domain::RecordTake>) {
          return {
              {"meta", meta_json(value.meta)},
              {"pattern", pattern_json(value.pattern)},
              {"take", take_json(value.take)},
              {"type", "RecordTake"},
          };
        } else if constexpr (std::is_same_v<Type, domain::CreatePattern>) {
          return {
              {"meta", meta_json(value.meta)},
              {"pattern", pattern_json(value.pattern)},
              {"type", "CreatePattern"},
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
    if (type == "RecordTake") {
      auto take = parse_take(input.at("take"), path);
      auto pattern = parse_pattern(input.at("pattern"), path);
      if (!take.has_value()) {
        return foundation::Result<PersistedCommand>::failure(take.error());
      }
      if (!pattern.has_value()) {
        return foundation::Result<PersistedCommand>::failure(pattern.error());
      }
      if (!exact_object_keys(input, {"meta", "pattern", "take", "type"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project("RecordTake transaction shape is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::RecordTake{
              std::move(meta.value()),
              std::move(take.value()),
              std::move(pattern.value()),
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
      [](const auto& value) -> PersistedCommand { return value; }, command);
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
      const auto applied =
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
      if (transaction.value().contains("cleanup_take_id")) {
        const auto cleanup_take_id =
            foundation::TakeId{
                transaction.value()
                    .at("cleanup_take_id")
                    .get<std::string>()};
        const auto* record =
            std::get_if<domain::RecordTake>(&command.value());
        if (record == nullptr ||
            !domain::is_valid_uuid(cleanup_take_id.value()) ||
            cleanup_take_id != record->take.id) {
          return foundation::Result<LoadedProject>::failure(
              invalid_project(
                  "project transaction cleanup obligation is invalid",
                  bundle / relative));
        }
        loaded.cleanup_obligations.emplace(
            meta.command_id, cleanup_take_id);
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
    if (checkpoint.value() != loaded.state ||
        foundation::canonical_json(checkpoint_json.value()) !=
            foundation::canonical_json(project_json(loaded.state))) {
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
  if (reused.value()) {
    return foundation::Result<StagedSample>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sample staging token was already used",
        });
  }
  auto lease = platform.acquire_writer(directory);
  if (!lease.has_value()) {
    return foundation::Result<StagedSample>::failure(lease.error());
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

foundation::Result<bool> matching_active_journal(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    const domain::RecordTake& record) {
  const auto path =
      bundle / "recovery/active" /
      (record.take.id.value() + ".jsonl");
  auto exists = platform->exists(path);
  if (!exists.has_value()) {
    return foundation::Result<bool>::failure(exists.error());
  }
  if (!exists.value()) {
    return foundation::Result<bool>::success(false);
  }
  if (!domain::is_valid_uuid(record.take.id.value())) {
    return foundation::Result<bool>::failure(
        Error{ErrorCode::invalid_argument, "take id is not a safe file name"});
  }
  auto bytes = read_file_bytes(*platform, path);
  if (!bytes.has_value()) {
    return foundation::Result<bool>::failure(bytes.error());
  }
  const auto line_end = bytes.value().find('\n');
  if (line_end == std::string::npos) {
    return foundation::Result<bool>::failure(
        invalid_project("active take journal could not be read", path));
  }
  try {
    const auto header = parse_bounded_or_throw(
        bytes.value().substr(0, line_end));
    TakeJournal journal{platform};
    const auto take =
        journal.read_active(bundle, record.take.id);
    if (!take.has_value()) {
      return foundation::Result<bool>::failure(take.error());
    }
    return foundation::Result<bool>::success(
        header.at("expected_revision").get<std::uint64_t>() ==
            record.meta.expected_revision &&
        take.value() == record.take);
  } catch (const std::exception& exception) {
    return foundation::Result<bool>::failure(
        invalid_project(
            "active take journal metadata could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<void> complete_journal_cleanup(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    const std::optional<foundation::TakeId>& cleanup_take_id) {
  if (!cleanup_take_id.has_value()) {
    return foundation::Result<void>::success();
  }
  const auto path =
      bundle / "recovery/active" /
      (cleanup_take_id->value() + ".jsonl");
  const auto removed = platform.remove(path);
  if (!removed.has_value()) {
    return removed;
  }
  return foundation::Result<void>::success();
}

foundation::Result<domain::AppliedCommand> commit_loaded(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    LoadedProject loaded,
    const PersistedCommand& command,
    const std::optional<ArtifactStage>& artifact_stage,
    PersistedCommand* persisted_identity) {
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
  bool journal_matches = false;
  std::optional<foundation::TakeId> cleanup_take_id;
  if (!replay_candidate) {
    const auto* record = std::get_if<domain::RecordTake>(&command);
    if (record != nullptr) {
      const auto matching = matching_active_journal(platform, bundle, *record);
      if (!matching.has_value()) {
        return foundation::Result<domain::AppliedCommand>::failure(
            matching.error());
      }
      journal_matches = matching.value();
      if (journal_matches) {
        cleanup_take_id = record->take.id;
      }
    }
  }

  const auto applied =
      apply_command(loaded.state, command, loaded.receipts);
  if (!applied.has_value()) {
    if (applied.error().code == ErrorCode::revision_conflict &&
        journal_matches) {
      const auto& record = std::get<domain::RecordTake>(command);
      TakeJournal journal{platform};
      const auto sealed =
          journal.seal(bundle, record.take.id, "revision_conflict");
      if (!sealed.has_value()) {
        return foundation::Result<domain::AppliedCommand>::failure(
            sealed.error());
      }
    }
    return foundation::Result<domain::AppliedCommand>::failure(
        applied.error());
  }
  if (applied.value().replayed) {
    const auto obligation =
        loaded.cleanup_obligations.find(meta.command_id);
    if (obligation != loaded.cleanup_obligations.end()) {
      cleanup_take_id = obligation->second;
    }
    const auto cleanup =
        complete_journal_cleanup(*platform, bundle, cleanup_take_id);
    if (!cleanup.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          cleanup.error());
    }
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
      validated_state.value() != applied.value().state) {
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
  if (cleanup_take_id.has_value()) {
    transaction["cleanup_take_id"] = cleanup_take_id->value();
  }
  const auto transaction_bytes =
      foundation::canonical_json(transaction) + "\n";
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

  const auto cleanup =
      complete_journal_cleanup(*platform, bundle, cleanup_take_id);
  if (!cleanup.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        cleanup.error());
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
  const auto encoded = project_json(initial);
  const auto validated = parse_project(encoded, bundle);
  if (!validated.has_value() || validated.value() != initial) {
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
        existing_state.value() != initial ||
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

foundation::Result<std::optional<RecordTakeReplay>>
ProjectStore::replay_record_take(
    const std::filesystem::path& bundle,
    const RecordTakeReplayIdentity& identity) {
  if (!domain::is_valid_uuid(identity.meta.command_id.value())) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id is not a safe file name",
        });
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        tree.error());
  }
  auto lock_result = platform_->acquire_writer(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        tree.error());
  }
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        recovered.error());
  }
  const auto original =
      loaded.value().commands.find(identity.meta.command_id);
  if (original == loaded.value().commands.end()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::success(
        std::nullopt);
  }
  const auto* record =
      std::get_if<domain::RecordTake>(&original->second);
  if (record == nullptr) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id belongs to a different command type",
        });
  }
  if (record->meta.expected_revision != identity.meta.expected_revision ||
      record->take.id != identity.take_id ||
      record->pattern != identity.pattern) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "take commit replay identity does not match persisted RecordTake",
        });
  }
  const auto receipt =
      loaded.value().receipts.find(identity.meta.command_id);
  if (receipt == loaded.value().receipts.end()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        invalid_project(
            "persisted RecordTake receipt is missing",
            bundle / "manifest.json"));
  }
  const auto cleanup =
      loaded.value().cleanup_obligations.find(identity.meta.command_id);
  if (cleanup != loaded.value().cleanup_obligations.end()) {
    const auto completed =
        complete_journal_cleanup(*platform_, bundle, cleanup->second);
    if (!completed.has_value()) {
      return foundation::Result<std::optional<RecordTakeReplay>>::failure(
          completed.error());
    }
  }
  return foundation::Result<std::optional<RecordTakeReplay>>::success(
      RecordTakeReplay{
          *record,
          domain::AppliedCommand{
              std::move(loaded.value().state),
              receipt->second.event,
              true,
          },
      });
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
  const auto artifact = describe_bytes(request.bytes, request.media_type);

  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
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
  const auto artifact = describe_bytes(request.bytes, request.media_type);
  const PersistedCommand command = domain::ImportAssignSample{
      request.meta,
      domain::Asset{request.asset_id, artifact},
      request.slot,
  };

  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
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
