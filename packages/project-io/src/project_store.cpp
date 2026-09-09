#include <lmdj/project_io/project_store.hpp>

#include <algorithm>
#include <array>
#include <charconv>
#include <cerrno>
#include <cctype>
#include <chrono>
#include <initializer_list>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
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

#include <fcntl.h>
#include <nlohmann/json.hpp>
#include <picosha2.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

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

std::filesystem::path performance_owner_lock_path(
    const std::filesystem::path& bundle) {
  return bundle / "recovery/active/performance.lock";
}

Error recording_session_active_error(
    const foundation::SequenceSessionId& session_id) {
  return Error{
      ErrorCode::invalid_argument,
      "active Performance recording owner is still alive",
      {{"reason", "recording_session_active"},
       {"session_id", session_id.value()},
       {"remedy",
        "stop the active Performance owner or retry after its process exits"}},
  };
}

struct FinalizePerformanceDraft {
  domain::CommandMeta meta;
  domain::PerformanceId performance_id;
  std::string name;
  std::optional<foundation::ArtifactRef> artifact;
  std::vector<domain::PerformanceEvent> events;
};

struct BindPerformanceRecording {
  domain::CommandMeta meta;
  domain::PerformanceId performance_id;
  foundation::ArtifactRef artifact;
};

using PersistedCommand = std::variant<
    domain::ImportAsset,
    domain::AssignPad,
    domain::CreatePattern,
    domain::AssignPatternSlot,
    domain::ClearPatternSlot,
    domain::MovePatternSlot,
    domain::MergePatternEvents,
    domain::UpdateSequenceSettings,
    domain::ImportAssignSample,
    domain::InstallSoundSet,
    domain::AdoptCandidates,
    domain::UpdatePadPlayback,
    domain::ResetPadPlayback,
    PerformanceMutation,
    CreatePerformance,
    RenamePerformance,
    DeletePerformance,
    FinalizePerformanceDraft,
    BindPerformanceRecording>;

struct LoadedProject {
  domain::ProjectState state;
  std::map<foundation::CommandId, PersistedCommand> commands;
  std::map<foundation::CommandId, domain::CommandReceipt> receipts;
  std::map<foundation::CommandId, SequenceFlushIdentity>
      sequence_flush_identities;
  std::map<foundation::CommandId, PerformanceFlushIdentity>
      performance_flush_identities;
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

bool valid_candidate_source_profile(
    std::string_view media_type, std::uint64_t byte_length) {
  return media_type == "audio/wav" && byte_length <= 16777216U;
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

foundation::Result<void> verify_managed_wav_artifact(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    const foundation::ArtifactRef& artifact) {
  if (artifact.media_type != "audio/wav" ||
      !valid_sha256(artifact.sha256)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance recording must be a verified audio/wav ArtifactRef",
        {{"reason", "performance_recording_artifact_invalid"},
         {"remedy",
          "provide an audio/wav ArtifactRef with the lowercase SHA-256 of its managed bytes"}},
    });
  }
  const auto path = bundle / "assets" / (artifact.sha256 + ".wav");
  auto described = describe_artifact(platform, path, artifact.media_type);
  if (!described.has_value() || described.value() != artifact) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::missing_asset,
        "Performance recording ArtifactRef does not match managed storage",
        {{"path", path.generic_string()},
         {"reason", "performance_recording_artifact_unverified"},
         {"remedy",
          "install the exact WAV bytes at assets/<sha256>.wav before saving or binding the recording"}},
    });
  }
  return foundation::Result<void>::success();
}

std::string canonical_fingerprint(const nlohmann::json& value) {
  const auto encoded = foundation::canonical_json(value);
  picosha2::hash256_one_by_one hasher;
  hasher.process(encoded.begin(), encoded.end());
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

std::string_view performance_state_string(SequenceSessionState state) {
  switch (state) {
    case SequenceSessionState::active:
      return "active";
    case SequenceSessionState::switching:
      return "switching";
    case SequenceSessionState::stopped:
      return "stopped";
    case SequenceSessionState::recovery_required:
      return "recovery_required";
    case SequenceSessionState::owner_lost:
      return "owner_lost";
    case SequenceSessionState::abandoned:
      return "abandoned";
  }
  return "unknown";
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

// The canonical persisted shape of a state, leaving its Contract level alone.
// The load path compares a replayed state against the head checkpoint at
// whatever level that checkpoint declares, including a level an older Build
// wrote, so the Contract decision does not belong here.
domain::ProjectState canonical_projection(
    const domain::ProjectState& state) {
  auto projected = state;
  if (projected.contract == domain::ProjectContract::v1 ||
      projected.contract == domain::ProjectContract::v2) {
    projected.quantize_enabled = true;
    projected.swing_percent = 50;
  }
  for (auto& [id, pattern] : projected.patterns) {
    (void)id;
    pattern.events = domain::merge_pattern_events({}, pattern.events);
  }
  for (auto& [id, performance] : projected.performances) {
    (void)id;
    performance.events =
        domain::canonical_performance_events(performance.events);
  }
  return projected;
}

// Every Project this Build persists is written as lmdj.project.v5, so a
// Project's Contract level never has to be inferred from its command history.
// An existing v3/v4 Project retains its Contract on load and is promoted to v5 the
// first time it is persisted; nothing is rewritten merely by opening it.
domain::ProjectState persisted_projection(
    const domain::ProjectState& state) {
  auto projected = canonical_projection(state);
  projected.contract = domain::ProjectContract::v5;
  return projected;
}

nlohmann::json performance_value_json(
    const domain::Performance& performance) {
  auto events = nlohmann::json::array();
  for (const auto& event : performance.events) {
    events.push_back(domain::performance_event_json(event));
  }
  return {
      {"created_bpm", performance.created_bpm},
      {"events", std::move(events)},
      {"name", performance.name},
      {"recording_revision", performance.recording_revision},
      {"recording_artifact",
       performance.recording_artifact.has_value()
           ? nlohmann::json(*performance.recording_artifact)
           : nlohmann::json(nullptr)},
  };
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
    nlohmann::json encoded_asset{
        {"artifact", asset.artifact}, {"asset_id", id.value()}};
    if (state.contract >= domain::ProjectContract::v4) {
      encoded_asset["lineage"] =
          asset.lineage.has_value()
              ? domain::asset_lineage_json(*asset.lineage)
              : nlohmann::json(nullptr);
    }
    assets.push_back(std::move(encoded_asset));
  }
  auto patterns = nlohmann::json::array();
  for (const auto& [id, pattern] : state.patterns) {
    auto encoded = pattern_value_json(pattern);
    encoded["pattern_id"] = id.value();
    patterns.push_back(std::move(encoded));
  }
  nlohmann::json encoded = {
      {"assets", std::move(assets)},
      {"banks", std::move(banks)},
      {"bpm", state.bpm},
      {"contract",
       state.contract == domain::ProjectContract::v5
           ? std::string_view{"lmdj.project.v5"}
           : state.contract == domain::ProjectContract::v4
           ? std::string_view{"lmdj.project.v4"}
           : std::string_view{"lmdj.project.v3"}},
      {"patterns", std::move(patterns)},
      {"project_id", state.id.value()},
      {"revision", state.revision},
      {"sequence_settings",
       {
           {"quantize_enabled", state.quantize_enabled},
           {"swing_percent", state.swing_percent},
       }},
  };
  if (state.contract >= domain::ProjectContract::v4) {
    auto pattern_slots = nlohmann::json::array();
    for (const auto& pattern_id : state.pattern_slots) {
      pattern_slots.push_back(
          pattern_id.has_value()
              ? nlohmann::json(pattern_id->value())
              : nlohmann::json(nullptr));
    }
    encoded["pattern_slots"] = std::move(pattern_slots);
    auto performances = nlohmann::json::array();
    for (const auto& [id, performance] : state.performances) {
      auto value = performance_value_json(performance);
      value["performance_id"] = id.value();
      performances.push_back(std::move(value));
    }
    encoded["performances"] = std::move(performances);
  }
  return encoded;
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

foundation::Result<domain::Performance> parse_performance(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(
            input,
            {"created_bpm",
             "events",
             "name",
             "performance_id",
             "recording_revision",
             "recording_artifact"}) ||
        !input.at("performance_id").is_string() ||
        !input.at("name").is_string() ||
        !nonnegative_integer(input.at("created_bpm")) ||
        !nonnegative_integer(input.at("recording_revision")) ||
        !input.at("events").is_array()) {
      return foundation::Result<domain::Performance>::failure(
          invalid_project("project Performance shape is invalid", path));
    }
    const auto created_bpm = unsigned_integer_value(input.at("created_bpm"));
    const auto recording_revision =
        unsigned_integer_value(input.at("recording_revision"));
    if (!created_bpm.has_value() || !recording_revision.has_value() ||
        *created_bpm > std::numeric_limits<std::uint16_t>::max()) {
      return foundation::Result<domain::Performance>::failure(
          invalid_project("project Performance BPM is invalid", path));
    }
    std::optional<foundation::ArtifactRef> recording_artifact;
    if (!input.at("recording_artifact").is_null()) {
      recording_artifact =
          input.at("recording_artifact").get<foundation::ArtifactRef>();
    }
    domain::Performance performance{
        domain::PerformanceId{
            input.at("performance_id").get<std::string>()},
        input.at("name").get<std::string>(),
        static_cast<std::uint16_t>(*created_bpm),
        *recording_revision,
        std::move(recording_artifact),
        {},
    };
    for (const auto& encoded : input.at("events")) {
      auto event = domain::performance_event_from_json(encoded);
      if (!event.has_value()) {
        return foundation::Result<domain::Performance>::failure(
            invalid_project(
                "project Performance event is invalid",
                path,
                event.error().message));
      }
      performance.events.push_back(std::move(event.value()));
    }
    if (performance.events !=
        domain::canonical_performance_events(performance.events)) {
      return foundation::Result<domain::Performance>::failure(
          invalid_project(
              "project Performance events are not canonical", path));
    }
    auto validated = domain::validate_performance(performance);
    if (!validated.has_value()) {
      return foundation::Result<domain::Performance>::failure(
          invalid_project(
              "project Performance is invalid",
              path,
              validated.error().message));
    }
    return foundation::Result<domain::Performance>::success(
        std::move(performance));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::Performance>::failure(
        invalid_project(
            "project Performance could not be parsed",
            path,
            exception.what()));
  }
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
    const bool is_v5 = contract == "lmdj.project.v5";
    const bool is_v4 = contract == "lmdj.project.v4" || is_v5;
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
    const bool v4_shape =
        is_v4 &&
        exact_object_keys(
            input,
            {
                "assets",
                "banks",
                "bpm",
                "contract",
                "patterns",
                "pattern_slots",
                "performances",
                "project_id",
                "revision",
                "sequence_settings",
            }) &&
        input.at("assets").is_array() &&
        input.at("patterns").is_array() &&
        input.at("pattern_slots").is_array() &&
        input.at("performances").is_array() &&
        exact_object_keys(
            input.at("sequence_settings"),
            {"quantize_enabled", "swing_percent"});
    if ((!legacy_shape && !v3_shape && !v4_shape) ||
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
    state.contract = is_v5 ? domain::ProjectContract::v5
                           : is_v4 ? domain::ProjectContract::v4
                           : domain::ProjectContract::v3;
    state.revision = *revision;
    if (is_v3 || is_v4) {
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
                                       const nlohmann::json& encoded,
                                       std::optional<domain::AssetLineage>
                                           lineage = std::nullopt)
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
          std::move(lineage),
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
    if (is_v3 || is_v4) {
      for (const auto& encoded : input.at("assets")) {
        const bool valid_asset_shape =
            is_v4
                ? exact_object_keys(
                      encoded, {"artifact", "asset_id", "lineage"})
                : exact_object_keys(encoded, {"artifact", "asset_id"});
        if (!valid_asset_shape ||
            !encoded.at("asset_id").is_string()) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project("project asset entry is invalid", path));
        }
        std::optional<domain::AssetLineage> lineage;
        if (is_v4 && !encoded.at("lineage").is_null()) {
          auto parsed_lineage =
              domain::asset_lineage_from_json(encoded.at("lineage"));
          if (!parsed_lineage.has_value()) {
            return foundation::Result<domain::ProjectState>::failure(
                invalid_project(
                    "project Asset Lineage is invalid",
                    path,
                    parsed_lineage.error().message));
          }
          if (!is_v5 && domain::asset_lineage_derivation_kind(parsed_lineage.value()) ==
                            domain::AssetLineageDerivationKind::capability_adoption) {
            return foundation::Result<domain::ProjectState>::failure(
                invalid_project("capability adoption requires Project v5", path));
          }
          lineage = std::move(parsed_lineage.value());
        }
        auto value = nlohmann::json{{"artifact", encoded.at("artifact")}};
        auto parsed = parse_asset_entry(
            encoded.at("asset_id").get<std::string>(),
            value,
            std::move(lineage));
        if (!parsed.has_value()) {
          return foundation::Result<domain::ProjectState>::failure(
              parsed.error());
        }
      }
    } else {
      for (auto iterator = input.at("assets").begin();
           iterator != input.at("assets").end(); ++iterator) {
        auto parsed = parse_asset_entry(
            iterator.key(), iterator.value(), std::nullopt);
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

    if (is_v3 || is_v4) {
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
    if (is_v4) {
      const auto& encoded_slots = input.at("pattern_slots");
      if (encoded_slots.size() != domain::kPatternSlotCount) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project Pattern slot count is invalid", path));
      }
      for (std::size_t slot = 0; slot < encoded_slots.size(); ++slot) {
        const auto& encoded = encoded_slots.at(slot);
        if (encoded.is_null()) {
          continue;
        }
        if (!encoded.is_string()) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project("project Pattern slot is invalid", path));
        }
        state.pattern_slots.at(slot) = foundation::PatternId{
            encoded.get<std::string>()};
      }
      const auto slots_valid = domain::validate_pattern_slots(state);
      if (!slots_valid.has_value()) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project(
                "project Pattern slots are invalid",
                path,
                slots_valid.error().message));
      }
      for (const auto& encoded : input.at("performances")) {
        auto performance = parse_performance(encoded, path);
        if (!performance.has_value() ||
            !state.performances
                 .emplace(performance.value().id, performance.value())
                 .second) {
          return foundation::Result<domain::ProjectState>::failure(
              performance.has_value()
                  ? invalid_project(
                        "project Performance id is duplicated", path)
                  : performance.error());
        }
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
                   {"lineage",
                    value.asset.lineage.has_value()
                        ? domain::asset_lineage_json(*value.asset.lineage)
                        : nlohmann::json(nullptr)},
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
            std::is_same_v<Type, domain::AssignPatternSlot>) {
          return {
              {"meta", meta_json(value.meta)},
              {"pattern_id", value.pattern_id.value()},
              {"slot", value.slot},
              {"type", "AssignPatternSlot"},
          };
        } else if constexpr (
            std::is_same_v<Type, domain::ClearPatternSlot>) {
          return {
              {"meta", meta_json(value.meta)},
              {"slot", value.slot},
              {"type", "ClearPatternSlot"},
          };
        } else if constexpr (
            std::is_same_v<Type, domain::MovePatternSlot>) {
          return {
              {"from_slot", value.from_slot},
              {"meta", meta_json(value.meta)},
              {"to_slot", value.to_slot},
              {"type", "MovePatternSlot"},
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
                   {"lineage",
                    value.asset.lineage.has_value()
                        ? domain::asset_lineage_json(*value.asset.lineage)
                        : nlohmann::json(nullptr)},
               }},
              {"meta", meta_json(value.meta)},
              {"slot", slot_json(value.slot)},
              {"type", "ImportAssignSample"},
          };
        } else if constexpr (
            std::is_same_v<Type, domain::InstallSoundSet> ||
            std::is_same_v<Type, domain::AdoptCandidates>) {
          auto assignments = nlohmann::json::array();
          for (const auto& assignment : value.assignments) {
            assignments.push_back({
                {"asset",
                 {
                     {"artifact", assignment.asset.artifact},
                     {"id", assignment.asset.id.value()},
                     {"lineage",
                      assignment.asset.lineage.has_value()
                          ? domain::asset_lineage_json(
                                *assignment.asset.lineage)
                          : nlohmann::json(nullptr)},
                 }},
                {"slot", slot_json(assignment.slot)},
            });
          }
          nlohmann::json encoded{
              {"assignments", std::move(assignments)},
              {"meta", meta_json(value.meta)},
              {"type", "InstallSoundSet"},
          };
          if constexpr (std::is_same_v<Type, domain::AdoptCandidates>) {
            encoded["type"] = "AdoptCandidates";
            encoded["project_id"] = value.project_id.value();
            encoded["source_asset_id"] = value.source_asset_id.value();
            encoded["source_artifact"] = value.source_artifact;
          }
          return encoded;
        } else if constexpr (
            std::is_same_v<Type, domain::UpdatePadPlayback>) {
          return {
              {"meta", meta_json(value.meta)},
              {"playback", playback_json(value.playback)},
              {"slot", slot_json(value.slot)},
              {"type", "UpdatePadPlayback"},
          };
        } else if constexpr (std::is_same_v<Type, PerformanceMutation>) {
          auto events = nlohmann::json::array();
          for (const auto& event : value.events) {
            events.push_back(domain::performance_event_json(event));
          }
          return {
              {"events", std::move(events)},
              {"meta", meta_json(value.meta)},
              {"performance_id", value.performance_id.value()},
              {"type", "AppendPerformanceEvents"},
          };
        } else if constexpr (std::is_same_v<Type, CreatePerformance>) {
          return {
              {"meta", meta_json(value.meta)},
              {"name", value.name},
              {"performance_id", value.performance_id.value()},
              {"type", "CreatePerformance"},
          };
        } else if constexpr (std::is_same_v<Type, RenamePerformance>) {
          return {
              {"meta", meta_json(value.meta)},
              {"name", value.name},
              {"performance_id", value.performance_id.value()},
              {"type", "RenamePerformance"},
          };
        } else if constexpr (std::is_same_v<Type, DeletePerformance>) {
          return {
              {"meta", meta_json(value.meta)},
              {"performance_id", value.performance_id.value()},
              {"type", "DeletePerformance"},
          };
        } else if constexpr (
            std::is_same_v<Type, FinalizePerformanceDraft>) {
          auto events = nlohmann::json::array();
          for (const auto& event : value.events) {
            events.push_back(domain::performance_event_json(event));
          }
          return {
              {"artifact",
               value.artifact.has_value()
                   ? nlohmann::json(*value.artifact)
                   : nlohmann::json(nullptr)},
              {"events", std::move(events)},
              {"meta", meta_json(value.meta)},
              {"name", value.name},
              {"performance_id", value.performance_id.value()},
              {"type", "FinalizePerformanceDraft"},
          };
        } else if constexpr (
            std::is_same_v<Type, BindPerformanceRecording>) {
          return {
              {"artifact", value.artifact},
              {"meta", meta_json(value.meta)},
              {"performance_id", value.performance_id.value()},
              {"type", "BindPerformanceRecording"},
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
    const auto parse_transaction_asset = [&path](
                                             const nlohmann::json& encoded)
        -> foundation::Result<domain::Asset> {
      const bool legacy_shape =
          exact_object_keys(encoded, {"artifact", "id"});
      const bool current_shape =
          exact_object_keys(encoded, {"artifact", "id", "lineage"});
      if ((!legacy_shape && !current_shape) ||
          !encoded.at("id").is_string()) {
        return foundation::Result<domain::Asset>::failure(
            invalid_project("transaction Asset shape is invalid", path));
      }
      std::optional<domain::AssetLineage> lineage;
      if (current_shape && !encoded.at("lineage").is_null()) {
        auto parsed = domain::asset_lineage_from_json(encoded.at("lineage"));
        if (!parsed.has_value()) {
          return foundation::Result<domain::Asset>::failure(
              invalid_project(
                  "transaction Asset Lineage is invalid",
                  path,
                  parsed.error().message));
        }
        lineage = std::move(parsed.value());
      }
      return foundation::Result<domain::Asset>::success(domain::Asset{
          foundation::AssetId{encoded.at("id").get<std::string>()},
          encoded.at("artifact").get<foundation::ArtifactRef>(),
          std::move(lineage),
      });
    };
    if (type == "ImportAsset") {
      const auto& encoded = input.at("asset");
      if (!exact_object_keys(input, {"asset", "meta", "type"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project("ImportAsset transaction shape is invalid", path));
      }
      auto asset = parse_transaction_asset(encoded);
      if (!asset.has_value()) {
        return foundation::Result<PersistedCommand>::failure(asset.error());
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::ImportAsset{
              std::move(meta.value()),
              std::move(asset.value()),
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
    if (type == "AssignPatternSlot") {
      if (!exact_object_keys(
              input, {"meta", "pattern_id", "slot", "type"}) ||
          !input.at("pattern_id").is_string() ||
          !nonnegative_integer(input.at("slot"))) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "AssignPatternSlot transaction shape is invalid", path));
      }
      const auto slot = unsigned_integer_value(input.at("slot"));
      if (!slot.has_value() ||
          *slot > std::numeric_limits<std::uint8_t>::max()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "AssignPatternSlot index is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::AssignPatternSlot{
              std::move(meta.value()),
              static_cast<std::uint8_t>(*slot),
              foundation::PatternId{
                  input.at("pattern_id").get<std::string>()},
          }});
    }
    if (type == "ClearPatternSlot") {
      if (!exact_object_keys(input, {"meta", "slot", "type"}) ||
          !nonnegative_integer(input.at("slot"))) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "ClearPatternSlot transaction shape is invalid", path));
      }
      const auto slot = unsigned_integer_value(input.at("slot"));
      if (!slot.has_value() ||
          *slot > std::numeric_limits<std::uint8_t>::max()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "ClearPatternSlot index is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::ClearPatternSlot{
              std::move(meta.value()),
              static_cast<std::uint8_t>(*slot),
          }});
    }
    if (type == "MovePatternSlot") {
      if (!exact_object_keys(
              input, {"from_slot", "meta", "to_slot", "type"}) ||
          !nonnegative_integer(input.at("from_slot")) ||
          !nonnegative_integer(input.at("to_slot"))) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "MovePatternSlot transaction shape is invalid", path));
      }
      const auto from_slot = unsigned_integer_value(input.at("from_slot"));
      const auto to_slot = unsigned_integer_value(input.at("to_slot"));
      if (!from_slot.has_value() || !to_slot.has_value() ||
          *from_slot > std::numeric_limits<std::uint8_t>::max() ||
          *to_slot > std::numeric_limits<std::uint8_t>::max()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "MovePatternSlot index is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::MovePatternSlot{
              std::move(meta.value()),
              static_cast<std::uint8_t>(*from_slot),
              static_cast<std::uint8_t>(*to_slot),
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
      if (!exact_object_keys(input, {"asset", "meta", "slot", "type"})) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "ImportAssignSample transaction shape is invalid", path));
      }
      auto slot = parse_slot(input.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<PersistedCommand>::failure(slot.error());
      }
      const auto& encoded = input.at("asset");
      auto asset = parse_transaction_asset(encoded);
      if (!asset.has_value()) {
        return foundation::Result<PersistedCommand>::failure(asset.error());
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::ImportAssignSample{
              std::move(meta.value()),
              std::move(asset.value()),
              slot.value(),
          }});
    }
    if (type == "InstallSoundSet") {
      if (!exact_object_keys(input, {"assignments", "meta", "type"}) ||
          !input.at("assignments").is_array() ||
          input.at("assignments").empty()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "InstallSoundSet transaction shape is invalid", path));
      }
      std::vector<domain::SoundSetInstallAssignment> assignments;
      for (const auto& encoded : input.at("assignments")) {
        if (!exact_object_keys(encoded, {"asset", "slot"})) {
          return foundation::Result<PersistedCommand>::failure(
              invalid_project(
                  "InstallSoundSet assignment shape is invalid", path));
        }
        auto slot = parse_slot(encoded.at("slot"), path);
        if (!slot.has_value()) {
          return foundation::Result<PersistedCommand>::failure(slot.error());
        }
        auto asset = parse_transaction_asset(encoded.at("asset"));
        if (!asset.has_value()) {
          return foundation::Result<PersistedCommand>::failure(asset.error());
        }
        assignments.push_back(
            domain::SoundSetInstallAssignment{
                slot.value(),
                std::move(asset.value()),
            });
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::InstallSoundSet{
              std::move(meta.value()),
              std::move(assignments),
          }});
    }
    if (type == "AdoptCandidates") {
      if (!exact_object_keys(input, {"assignments", "meta", "type", "project_id", "source_asset_id", "source_artifact"}) ||
          !input.at("assignments").is_array() ||
          input.at("assignments").empty()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "AdoptCandidates transaction shape is invalid", path));
      }
      const auto& source = input.at("source_artifact");
      if (!input.at("project_id").is_string() ||
          !domain::is_valid_uuid(input.at("project_id").get<std::string>()) ||
          !input.at("source_asset_id").is_string() ||
          !domain::is_valid_uuid(input.at("source_asset_id").get<std::string>()) ||
          !exact_object_keys(source, {"sha256", "media_type", "byte_length"}) ||
          !source.at("sha256").is_string() ||
          !valid_sha256(source.at("sha256").get<std::string>()) ||
          !source.at("media_type").is_string() ||
          !nonnegative_integer(source.at("byte_length")) ||
          !valid_candidate_source_profile(
              source.at("media_type").get_ref<const std::string&>(),
              source.at("byte_length").get<std::uint64_t>()) ||
          input.at("assignments").size() > 64)
        return foundation::Result<PersistedCommand>::failure(
            invalid_project("AdoptCandidates source identity is invalid", path));
      std::vector<domain::CandidateAdoptionAssignment> assignments;
      for (const auto& encoded : input.at("assignments")) {
        if (!exact_object_keys(encoded, {"asset", "slot"})) {
          return foundation::Result<PersistedCommand>::failure(
              invalid_project(
                  "AdoptCandidates assignment shape is invalid", path));
        }
        auto slot = parse_slot(encoded.at("slot"), path);
        if (!slot.has_value()) {
          return foundation::Result<PersistedCommand>::failure(slot.error());
        }
        auto asset = parse_transaction_asset(encoded.at("asset"));
        if (!asset.has_value()) {
          return foundation::Result<PersistedCommand>::failure(asset.error());
        }
        assignments.push_back(
            domain::CandidateAdoptionAssignment{
                slot.value(),
                std::move(asset.value()),
            });
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{domain::AdoptCandidates{
              std::move(meta.value()),
              foundation::ProjectId{input.at("project_id").get<std::string>()},
              foundation::AssetId{input.at("source_asset_id").get<std::string>()},
              input.at("source_artifact").get<foundation::ArtifactRef>(),
              std::move(assignments),
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
    if (type == "CreatePerformance" || type == "RenamePerformance") {
      if (!exact_object_keys(
              input, {"meta", "name", "performance_id", "type"}) ||
          !input.at("name").is_string() ||
          !input.at("performance_id").is_string()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                type + " transaction shape is invalid", path));
      }
      const auto performance_id =
          input.at("performance_id").get<std::string>();
      if (!domain::is_valid_uuid(performance_id)) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                type + " Performance id is invalid", path));
      }
      if (type == "CreatePerformance") {
        return foundation::Result<PersistedCommand>::success(
            PersistedCommand{CreatePerformance{
                std::move(meta.value()),
                domain::PerformanceId{performance_id},
                input.at("name").get<std::string>(),
            }});
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{RenamePerformance{
              std::move(meta.value()),
              domain::PerformanceId{performance_id},
              input.at("name").get<std::string>(),
          }});
    }
    if (type == "DeletePerformance") {
      if (!exact_object_keys(
              input, {"meta", "performance_id", "type"}) ||
          !input.at("performance_id").is_string()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "DeletePerformance transaction shape is invalid", path));
      }
      const auto performance_id =
          input.at("performance_id").get<std::string>();
      if (!domain::is_valid_uuid(performance_id)) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "DeletePerformance Performance id is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{DeletePerformance{
              std::move(meta.value()),
              domain::PerformanceId{performance_id},
          }});
    }
    if (type == "FinalizePerformanceDraft") {
      if (!exact_object_keys(
              input,
              {"artifact", "events", "meta", "name", "performance_id",
               "type"}) ||
          !input.at("events").is_array() || !input.at("name").is_string() ||
          !input.at("performance_id").is_string()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "FinalizePerformanceDraft transaction shape is invalid",
                path));
      }
      std::vector<domain::PerformanceEvent> events;
      for (const auto& encoded : input.at("events")) {
        auto parsed = domain::performance_event_from_json(encoded);
        if (!parsed.has_value()) {
          return foundation::Result<PersistedCommand>::failure(
              invalid_project(
                  "FinalizePerformanceDraft event is invalid", path,
                  parsed.error().message));
        }
        events.push_back(std::move(parsed.value()));
      }
      if (events != domain::canonical_performance_events(events)) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "FinalizePerformanceDraft events are not canonical", path));
      }
      std::optional<foundation::ArtifactRef> artifact;
      if (!input.at("artifact").is_null()) {
        artifact = input.at("artifact").get<foundation::ArtifactRef>();
      }
      const auto performance_id =
          input.at("performance_id").get<std::string>();
      if (!domain::is_valid_uuid(performance_id)) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "FinalizePerformanceDraft Performance id is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{FinalizePerformanceDraft{
              std::move(meta.value()),
              domain::PerformanceId{performance_id},
              input.at("name").get<std::string>(),
              std::move(artifact),
              std::move(events),
          }});
    }
    if (type == "BindPerformanceRecording") {
      if (!exact_object_keys(
              input, {"artifact", "meta", "performance_id", "type"}) ||
          !input.at("performance_id").is_string()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "BindPerformanceRecording transaction shape is invalid",
                path));
      }
      const auto performance_id =
          input.at("performance_id").get<std::string>();
      if (!domain::is_valid_uuid(performance_id)) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "BindPerformanceRecording Performance id is invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{BindPerformanceRecording{
              std::move(meta.value()),
              domain::PerformanceId{performance_id},
              input.at("artifact").get<foundation::ArtifactRef>(),
          }});
    }
    if (type == "AppendPerformanceEvents") {
      if (!exact_object_keys(
              input, {"events", "meta", "performance_id", "type"}) ||
          !input.at("events").is_array() ||
          !input.at("performance_id").is_string()) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "AppendPerformanceEvents transaction shape is invalid",
                path));
      }
      const auto performance_id =
          input.at("performance_id").get<std::string>();
      if (!domain::is_valid_uuid(performance_id)) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "AppendPerformanceEvents Performance id is invalid",
                path));
      }
      std::vector<domain::PerformanceEvent> events;
      for (const auto& encoded : input.at("events")) {
        auto parsed = domain::performance_event_from_json(encoded);
        if (!parsed.has_value()) {
          return foundation::Result<PersistedCommand>::failure(
              invalid_project(
                  "AppendPerformanceEvents event is invalid",
                  path,
                  parsed.error().message));
        }
        events.push_back(std::move(parsed.value()));
      }
      if (events.empty() ||
          events != domain::canonical_performance_events(events)) {
        return foundation::Result<PersistedCommand>::failure(
            invalid_project(
                "AppendPerformanceEvents events are invalid", path));
      }
      return foundation::Result<PersistedCommand>::success(
          PersistedCommand{PerformanceMutation{
              std::move(meta.value()),
              domain::PerformanceId{performance_id},
              std::move(events),
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
            std::is_same_v<Type, PerformanceMutation> ||
            std::is_same_v<Type, CreatePerformance> ||
            std::is_same_v<Type, RenamePerformance> ||
            std::is_same_v<Type, DeletePerformance> ||
            std::is_same_v<Type, FinalizePerformanceDraft> ||
            std::is_same_v<Type, BindPerformanceRecording>) {
          const auto receipt = receipts.find(value.meta.command_id);
          if (receipt != receipts.end()) {
            return foundation::Result<domain::AppliedCommand>::success(
                domain::AppliedCommand{
                    state, receipt->second.event, true});
          }
          if (state.revision != value.meta.expected_revision) {
            return foundation::Result<domain::AppliedCommand>::failure(Error{
                ErrorCode::revision_conflict,
                "Performance command expected revision does not match",
                {{"actual_revision", state.revision},
                 {"expected_revision", value.meta.expected_revision}},
            });
          }
          if (!domain::is_valid_uuid(value.performance_id.value())) {
            return foundation::Result<domain::AppliedCommand>::failure(Error{
                ErrorCode::invalid_argument,
                "Performance id is invalid",
            });
          }
          auto next = state;
          std::string_view event_type;
          if constexpr (std::is_same_v<Type, CreatePerformance>) {
            domain::Performance performance{
                value.performance_id,
                value.name,
                state.bpm,
                value.meta.expected_revision,
                std::nullopt,
                {},
            };
            auto validated = domain::validate_performance(performance);
            if (!validated.has_value()) {
              return foundation::Result<domain::AppliedCommand>::failure(
                  validated.error());
            }
            if (!next.performances
                     .emplace(performance.id, std::move(performance))
                     .second) {
              return foundation::Result<domain::AppliedCommand>::failure(
                  Error{
                      ErrorCode::duplicate_id,
                      "Performance id already exists",
                      {{"performance_id", value.performance_id.value()}},
                  });
            }
            event_type = "performance.created";
          } else {
            const auto found =
                next.performances.find(value.performance_id);
            if (found == next.performances.end()) {
              return foundation::Result<domain::AppliedCommand>::failure(
                  Error{
                      ErrorCode::not_found,
                      "Performance mutation target does not exist",
                      {{"performance_id", value.performance_id.value()}},
                  });
            }
            if constexpr (std::is_same_v<Type, PerformanceMutation>) {
              auto& target = found->second;
              target.events.insert(
                  target.events.end(),
                  value.events.begin(),
                  value.events.end());
              target.events =
                  domain::canonical_performance_events(target.events);
              auto validated = domain::validate_performance(target);
              if (!validated.has_value()) {
                return foundation::Result<domain::AppliedCommand>::failure(
                    validated.error());
              }
              event_type = "performance.events_appended";
            } else if constexpr (std::is_same_v<Type, RenamePerformance>) {
              found->second.name = value.name;
              auto validated = domain::validate_performance(found->second);
              if (!validated.has_value()) {
                return foundation::Result<domain::AppliedCommand>::failure(
                    validated.error());
              }
              event_type = "performance.renamed";
            } else if constexpr (
                std::is_same_v<Type, FinalizePerformanceDraft>) {
              auto& target = found->second;
              target.events.insert(
                  target.events.end(), value.events.begin(), value.events.end());
              target.events =
                  domain::canonical_performance_events(target.events);
              target.name = value.name;
              if (value.artifact.has_value()) {
                if (target.recording_artifact.has_value() &&
                    target.recording_artifact != value.artifact) {
                  return foundation::Result<domain::AppliedCommand>::failure(
                      Error{
                          ErrorCode::invalid_argument,
                          "Performance recording ArtifactRef is already bound",
                          {{"reason", "performance_recording_conflict"},
                           {"remedy",
                            "keep the existing recording ArtifactRef or create a new Performance; replacement is not permitted"}},
                      });
                }
                target.recording_artifact = value.artifact;
              }
              auto validated = domain::validate_performance(target);
              if (!validated.has_value()) {
                return foundation::Result<domain::AppliedCommand>::failure(
                    validated.error());
              }
              event_type = "performance.saved";
            } else if constexpr (
                std::is_same_v<Type, BindPerformanceRecording>) {
              auto& target = found->second;
              if (target.recording_artifact.has_value()) {
                if (*target.recording_artifact == value.artifact) {
                  return foundation::Result<domain::AppliedCommand>::failure(
                      Error{
                          ErrorCode::invalid_argument,
                          "same ArtifactRef must replay through its original command id",
                          {{"reason", "performance_recording_already_bound"},
                           {"remedy",
                            "replay the original bind command id or treat the identical ArtifactRef as already bound"}},
                      });
                }
                return foundation::Result<domain::AppliedCommand>::failure(
                    Error{
                        ErrorCode::invalid_argument,
                        "Performance recording ArtifactRef is already bound",
                        {{"reason", "performance_recording_conflict"},
                         {"remedy",
                          "keep the existing recording ArtifactRef or create a new Performance; replacement is not permitted"}},
                    });
              }
              target.recording_artifact = value.artifact;
              auto validated = domain::validate_performance(target);
              if (!validated.has_value()) {
                return foundation::Result<domain::AppliedCommand>::failure(
                    validated.error());
              }
              event_type = "performance.recording_bound";
            } else {
              next.performances.erase(found);
              event_type = "performance.deleted";
            }
          }
          next.contract = std::max(next.contract, domain::ProjectContract::v4);
          ++next.revision;
          nlohmann::json event = {
              {"command_id", value.meta.command_id.value()},
              {"performance_id", value.performance_id.value()},
              {"revision", next.revision},
              {"type", event_type},
          };
          if constexpr (
              std::is_same_v<Type, CreatePerformance> ||
              std::is_same_v<Type, RenamePerformance> ||
              std::is_same_v<Type, FinalizePerformanceDraft>) {
            event["name"] = value.name;
          }
          return foundation::Result<domain::AppliedCommand>::success(
              domain::AppliedCommand{
                  std::move(next), std::move(event), false});
        } else if constexpr (
            std::is_same_v<Type, domain::ImportAssignSample> ||
            std::is_same_v<Type, domain::InstallSoundSet> ||
            std::is_same_v<Type, domain::AdoptCandidates> ||
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
            std::is_same_v<Type, domain::InstallSoundSet> ||
            std::is_same_v<Type, domain::AdoptCandidates> ||
            std::is_same_v<Type, domain::UpdatePadPlayback> ||
            std::is_same_v<Type, domain::ResetPadPlayback> ||
            std::is_same_v<Type, PerformanceMutation> ||
            std::is_same_v<Type, CreatePerformance> ||
            std::is_same_v<Type, RenamePerformance> ||
            std::is_same_v<Type, DeletePerformance> ||
            std::is_same_v<Type, FinalizePerformanceDraft> ||
            std::is_same_v<Type, BindPerformanceRecording>) {
          return foundation::Result<domain::Command>::failure(
              Error{
                  ErrorCode::internal_error,
                  "persisted internal mutation is not a legacy command",
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
    const std::filesystem::path& bundle,
    bool verify_asset_bytes = true) {
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
    const bool checkpoint_is_current =
        checkpoint_json.value().at("contract") == "lmdj.project.v3" ||
        checkpoint_json.value().at("contract") == "lmdj.project.v4" ||
        checkpoint_json.value().at("contract") == "lmdj.project.v5";

    LoadedProject loaded{
        std::move(initial.value()),
        {},
        {},
        {},
        {},
        {},
    };
    // The head checkpoint, not the replayed command history, states a
    // Project's Contract level: a Project promoted to v4 by an earlier persist
    // still replays from a v3 checkpoint zero, and a v4-only command in that
    // history has to replay against v4 Project Truth.
    loaded.state.contract = checkpoint.value().contract;
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
      if (transaction.value().contains("performance_flush")) {
        try {
          const auto& encoded = transaction.value().at("performance_flush");
          PerformanceFlushIdentity identity{
              foundation::SequenceSessionId{
                  encoded.at("session_id").get<std::string>()},
              encoded.at("flush_seq").get<std::uint64_t>(),
              foundation::CommandId{
                  encoded.at("command_id").get<std::string>()},
              domain::PerformanceId{
                  encoded.at("performance_id").get<std::string>()},
          };
          const auto* mutation =
              std::get_if<PerformanceMutation>(&command.value());
          if (mutation == nullptr ||
              !domain::is_valid_uuid(identity.session_id.value()) ||
              identity.command_id != meta.command_id ||
              identity.performance_id != mutation->performance_id) {
            return foundation::Result<LoadedProject>::failure(
                invalid_project(
                    "project transaction Performance flush identity is "
                    "invalid",
                    bundle / relative));
          }
          loaded.performance_flush_identities.emplace(
              meta.command_id, std::move(identity));
        } catch (const std::exception& exception) {
          return foundation::Result<LoadedProject>::failure(
              invalid_project(
                  "project transaction Performance flush identity is invalid",
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

    if (checkpoint.value() != canonical_projection(loaded.state) ||
        (checkpoint_is_current &&
         foundation::canonical_json(checkpoint_json.value()) !=
             foundation::canonical_json(project_json(loaded.state)))) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project(
              "project checkpoint does not match transaction replay",
              bundle / head_checkpoint));
    }

    // Owner resolution verifies only its selected Artifact after checking
    // ownership. Every authoring load keeps the complete asset verification.
    if (!verify_asset_bytes) {
      return foundation::Result<LoadedProject>::success(std::move(loaded));
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
    const LoadedProject& loaded,
    std::optional<std::string_view> retained_artifact_sha = std::nullopt) {
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
  for (const auto& [performance_id, performance] :
       loaded.state.performances) {
    (void)performance_id;
    if (performance.recording_artifact.has_value()) {
      referenced_assets.insert(performance.recording_artifact->sha256);
    }
  }
  if (retained_artifact_sha.has_value()) {
    referenced_assets.insert(std::string{*retained_artifact_sha});
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
        std::nullopt,
    const std::optional<PerformanceFlushIdentity>&
        performance_flush_identity = std::nullopt,
    // A Sound Set install publishes N content-addressed blobs under one
    // revision, so the rollback ledger below is a vector: a partial multi-blob
    // publish must be undone completely or the commit is not atomic.
    const std::vector<ArtifactStage>& artifact_stages = {}) {
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
  const bool soundset_install =
      std::holds_alternative<domain::InstallSoundSet>(command);
  // Both families stage bytes and publish blobs before the manifest settles,
  // so they share the same injected fault points; without this a Sound Set
  // install would have no atomicity coverage at all.
  const bool candidate_adoption = std::holds_alternative<domain::AdoptCandidates>(command);
  const bool staged_artifact_commit = sample_import || soundset_install || candidate_adoption;
  if (staged_artifact_commit) {
    const auto fault = sample_after_event_preparation_fault(bundle);
    if (!fault.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }

  // Every Project this Build persists is written as lmdj.project.v5, so an
  // existing v3 Project is promoted on its first persist. Promote the state
  // being committed, not just the bytes, so the checkpoint on disk, the state
  // returned to the caller, and the next load all agree on the Contract level.
  auto committed = applied.value();
  committed.state = persisted_projection(committed.state);
  const auto encoded_state = project_json(committed.state);
  const auto validated_state =
      parse_project(encoded_state, bundle / "manifest.json");
  if (!validated_state.has_value() ||
      validated_state.value() != committed.state) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command result cannot be persisted as valid Project Truth",
        });
  }

  std::vector<ArtifactStage> stages;
  if (artifact_stage.has_value()) {
    stages.push_back(*artifact_stage);
  }
  stages.insert(
      stages.end(), artifact_stages.begin(), artifact_stages.end());
  std::vector<std::filesystem::path> newly_published_artifacts;
  // Every blob this command published must be attempted, so one stubborn
  // removal cannot strand the rest; the first error is still what surfaces.
  const auto remove_newly_published = [&]() -> foundation::Result<void> {
    auto outcome = foundation::Result<void>::success();
    for (const auto& path : newly_published_artifacts) {
      const auto removed = platform->remove(path);
      if (!removed.has_value() && outcome.has_value()) {
        outcome = foundation::Result<void>::failure(removed.error());
      }
    }
    return outcome;
  };
  if (!stages.empty()) {
    for (const auto& stage : stages) {
      const auto published = publish_artifact(*platform, bundle, stage);
      if (!published.has_value()) {
        (void)remove_newly_published();
        return foundation::Result<domain::AppliedCommand>::failure(
            published.error());
      }
      if (published.value()) {
        newly_published_artifacts.push_back(
            bundle / "assets" / (stage.artifact.sha256 + ".wav"));
      }
    }
  } else if (
      std::holds_alternative<domain::ImportAsset>(command) ||
      sample_import || soundset_install || candidate_adoption) {
    std::vector<const domain::Asset*> assets;
    if (const auto* import = std::get_if<domain::ImportAsset>(&command)) {
      assets.push_back(&import->asset);
    } else if (
        const auto* sample =
            std::get_if<domain::ImportAssignSample>(&command)) {
      assets.push_back(&sample->asset);
    } else if (candidate_adoption) {
      for (const auto& assignment : std::get<domain::AdoptCandidates>(command).assignments)
        assets.push_back(&assignment.asset);
    } else {
      for (const auto& assignment :
           std::get<domain::InstallSoundSet>(command).assignments) {
        assets.push_back(&assignment.asset);
      }
    }
    for (const auto* asset : assets) {
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
  }
  if (staged_artifact_commit) {
    const auto fault = sample_after_artifact_creation_fault(
        stages.empty()
            ? bundle / "assets"
            : bundle / "assets" / (stages.front().artifact.sha256 + ".wav"));
    if (!fault.has_value()) {
      const auto removed = remove_newly_published();
      if (!removed.has_value()) {
        return foundation::Result<domain::AppliedCommand>::failure(
            removed.error());
      }
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }

  const auto revision = committed.state.revision;
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
      {"event", committed.event},
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
  if (performance_flush_identity.has_value()) {
    transaction["performance_flush"] = {
        {"command_id", performance_flush_identity->command_id.value()},
        {"flush_seq", performance_flush_identity->flush_seq},
        {"performance_id",
         performance_flush_identity->performance_id.value()},
        {"session_id", performance_flush_identity->session_id.value()},
    };
  }
  const auto transaction_bytes =
      foundation::canonical_json(transaction) + "\n";
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const bool performance_truth_command =
      std::holds_alternative<CreatePerformance>(command) ||
      std::holds_alternative<RenamePerformance>(command) ||
      std::holds_alternative<DeletePerformance>(command) ||
      std::holds_alternative<FinalizePerformanceDraft>(command) ||
      std::holds_alternative<BindPerformanceRecording>(command);
  if (sequence_flush_identity.has_value() ||
      performance_flush_identity.has_value() || performance_truth_command) {
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
    (void)remove_newly_published();
    return foundation::Result<domain::AppliedCommand>::failure(
        written.error());
  }

  const auto checkpoint_bytes =
      foundation::canonical_json(project_json(committed.state)) + "\n";
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  if (sequence_flush_identity.has_value() ||
      performance_flush_identity.has_value() || performance_truth_command) {
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
    (void)remove_newly_published();
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
    return remove_newly_published();
  };
  if (staged_artifact_commit) {
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
  if (sequence_flush_identity.has_value() ||
      performance_flush_identity.has_value() || performance_truth_command) {
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

  if (staged_artifact_commit) {
    const auto fault = sample_after_manifest_publication_fault(
        bundle / "manifest.json");
    if (!fault.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          fault.error());
    }
  }

  return foundation::Result<domain::AppliedCommand>::success(
      std::move(committed));
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

foundation::Result<std::optional<ActiveSequenceJournal>>
admit_sequence_authoring(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    const PersistedCommand* command = nullptr,
    const std::optional<foundation::SequenceSessionId>&
        sequence_session_id = std::nullopt) {
  SequenceJournal journal{platform};
  auto active = journal.read_active(bundle);
  if (!active.has_value()) {
    if (active.error().code == ErrorCode::not_found) {
      if (sequence_session_id.has_value()) {
        return foundation::Result<
            std::optional<ActiveSequenceJournal>>::failure(Error{
            ErrorCode::invalid_argument,
            "armed Capture commit has no active Sequence arm",
            {{"reason", "armed_capture_not_armed"}},
        });
      }
      return foundation::Result<
          std::optional<ActiveSequenceJournal>>::success(std::nullopt);
    }
    return foundation::Result<
        std::optional<ActiveSequenceJournal>>::failure(active.error());
  }
  const auto* settings =
      command != nullptr
          ? std::get_if<domain::UpdateSequenceSettings>(command)
          : nullptr;
  const auto* sample =
      command != nullptr
          ? std::get_if<domain::ImportAssignSample>(command)
          : nullptr;
  if (settings != nullptr &&
      (active.value().state == SequenceSessionState::active ||
       active.value().state == SequenceSessionState::switching)) {
    if (active.value().capture_commit.has_value()) {
      return foundation::Result<
          std::optional<ActiveSequenceJournal>>::failure(Error{
          ErrorCode::invalid_argument,
          "Sequence settings cannot commit while armed Capture recovery is "
          "pending",
          {{"reason", "armed_capture_recovery_pending"},
           {"remedy",
            "retry, reconcile, or discard the armed Capture first"}},
      });
    }
    return foundation::Result<
        std::optional<ActiveSequenceJournal>>::success(
            std::optional<ActiveSequenceJournal>{std::move(active.value())});
  }
  if (sequence_session_id.has_value() && sample != nullptr &&
      (active.value().state == SequenceSessionState::active ||
       active.value().state == SequenceSessionState::switching)) {
    if (active.value().session_id != *sequence_session_id) {
      return foundation::Result<
          std::optional<ActiveSequenceJournal>>::failure(Error{
          ErrorCode::invalid_argument,
          "armed Capture commit owner does not match",
          {{"reason", "sequence_owner_mismatch"},
           {"session_id", active.value().session_id.value()}},
      });
    }
    if (!active.value().armed_capture_slot.has_value()) {
      return foundation::Result<
          std::optional<ActiveSequenceJournal>>::failure(Error{
          ErrorCode::invalid_argument,
          "armed Capture commit has no active target",
          {{"reason", "armed_capture_not_armed"},
           {"session_id", active.value().session_id.value()}},
      });
    }
    if (*active.value().armed_capture_slot != sample->slot ||
        active.value().expected_revision != sample->meta.expected_revision) {
      return foundation::Result<
          std::optional<ActiveSequenceJournal>>::failure(Error{
          ErrorCode::invalid_argument,
          "armed Capture commit target does not match",
          {{"reason", "armed_capture_target_mismatch"},
           {"session_id", active.value().session_id.value()}},
      });
    }
    return foundation::Result<
        std::optional<ActiveSequenceJournal>>::success(
        std::optional<ActiveSequenceJournal>{std::move(active.value())});
  }
  return foundation::Result<std::optional<ActiveSequenceJournal>>::failure(
      Error{
          ErrorCode::invalid_argument,
          "Project mutation is blocked by the active Sequence Journal",
          {{"reason", "sequence_session_active"},
           {"session_id", active.value().session_id.value()},
           {"remedy",
            "stop the active Sequence session or reconcile owner loss before retrying"}},
      });
}

foundation::Result<void> admit_performance_sample_class(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle) {
  SequenceJournal journal{platform};
  auto active = journal.read_active_performance(bundle);
  if (!active.has_value()) {
    return active.error().code == ErrorCode::not_found
               ? foundation::Result<void>::success()
               : foundation::Result<void>::failure(active.error());
  }
  if (active.value().state == SequenceSessionState::recovery_required) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Sample-class mutation is blocked until durable Performance rebase reconciliation completes",
        {{"reason", "performance_rebase_recovery_required"},
         {"session_id", active.value().session_id.value()},
         {"remedy",
          "reopen the Project and retry the exact prepared command; no other Authoring Command is admissible"}},
    });
  }
  return foundation::Result<void>::failure(Error{
      ErrorCode::invalid_argument,
      "Sample-class mutation is blocked while Performance recording remains active",
      {{"reason", "performance_sample_command_blocked"},
       {"session_id", active.value().session_id.value()},
       {"recording_sealed", false},
       {"remedy",
        "stop and save or discard the Performance draft before retrying the Sample-class command"}},
  });
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
  SequenceJournal recording{platform};
  auto performance = recording.read_active_performance(bundle);
  if (performance.has_value()) {
    if (performance.value().state ==
        SequenceSessionState::recovery_required) {
      return foundation::Result<domain::AppliedCommand>::failure(Error{
          ErrorCode::invalid_argument,
          "Project mutation is blocked until durable Performance rebase reconciliation completes",
          {{"reason", "performance_rebase_recovery_required"},
           {"session_id", performance.value().session_id.value()},
           {"remedy",
            "reopen the Project and retry the exact prepared command; no other Authoring Command is admissible"}},
      });
    }
    return foundation::Result<domain::AppliedCommand>::failure(Error{
        ErrorCode::invalid_argument,
        "Project mutation is blocked by the active Performance Journal",
        {{"reason", "performance_session_active"},
         {"session_id", performance.value().session_id.value()},
         {"session_state",
          performance_state_string(performance.value().state)},
         {"remedy",
          "stop, save, discard, or exactly reconcile the Performance session before retrying"}},
    });
  }
  if (performance.error().code != ErrorCode::not_found) {
    return foundation::Result<domain::AppliedCommand>::failure(
        performance.error());
  }
  std::optional<domain::PerformanceId> managed_performance_id;
  if (const auto* rename = std::get_if<RenamePerformance>(&command)) {
    managed_performance_id = rename->performance_id;
  } else if (const auto* remove =
                 std::get_if<DeletePerformance>(&command)) {
    managed_performance_id = remove->performance_id;
  }
  if (managed_performance_id.has_value()) {
    auto candidates = recording.list_performance_recoverable(bundle);
    if (!candidates.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          candidates.error());
    }
    if (std::ranges::any_of(
            candidates.value(),
            [&managed_performance_id](const auto& candidate) {
              return candidate.journal.performance_id ==
                     *managed_performance_id;
            })) {
      return foundation::Result<domain::AppliedCommand>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance management mutation is blocked by recovery",
          {{"reason", "performance_recovery_pending"},
           {"remedy",
            "apply or discard the recoverable Performance tail before renaming or deleting the draft"}},
      });
    }
  }
  auto admitted = admit_sequence_authoring(platform, bundle);
  if (!admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        admitted.error());
  }
  return commit_loaded(
      platform,
      bundle,
      std::move(loaded.value()),
      command,
      std::nullopt,
      nullptr);
}

foundation::Result<std::vector<std::byte>> read_verified_artifact(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    const foundation::ArtifactRef& artifact) {
  const auto path =
      bundle / "assets" / (artifact.sha256 + ".wav");
  auto existing = platform.exists(path);
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
  auto length = platform.byte_length(path);
  if (!length.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(length.error());
  }
  if (length.value() != artifact.byte_length) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::cook_failed,
            "project artifact byte length does not match its reference",
            {{"path", path.generic_string()},
             {"storage_condition", std::string{kStorageConditionArtifactMismatch}}},
        });
  }
  auto read = platform.read_complete(path);
  if (!read.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(read.error());
  }
  auto bytes = std::move(read.value());
  if (bytes.size() != artifact.byte_length) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::cook_failed,
            "project artifact byte length changed while it was being read",
            {{"path", path.generic_string()},
             {"storage_condition", std::string{kStorageConditionArtifactMismatch}}},
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
            {{"path", path.generic_string()},
             {"storage_condition", std::string{kStorageConditionArtifactMismatch}}},
        });
  }
  return foundation::Result<std::vector<std::byte>>::success(
      std::move(bytes));
}

}  // namespace

struct PerformanceOwnerLock::Impl {
  explicit Impl(int descriptor_value) : descriptor(descriptor_value) {}
  ~Impl() {
    if (descriptor >= 0) {
      (void)::flock(descriptor, LOCK_UN);
      (void)::close(descriptor);
    }
  }

  int descriptor{-1};
};

PerformanceOwnerLock::PerformanceOwnerLock(std::unique_ptr<Impl> impl)
    : impl_(std::move(impl)) {}
PerformanceOwnerLock::~PerformanceOwnerLock() = default;
PerformanceOwnerLock::PerformanceOwnerLock(PerformanceOwnerLock&&) noexcept =
    default;
PerformanceOwnerLock& PerformanceOwnerLock::operator=(
    PerformanceOwnerLock&&) noexcept = default;

struct ProjectStore::PerformanceOwnerLocks {
  struct Entry {
    foundation::SequenceSessionId session_id;
    std::unique_ptr<PerformanceOwnerLock> lock;
  };

  std::mutex mutex;
  std::map<std::string, Entry> entries;
};

ProjectStore::ProjectStore()
    : ProjectStore(make_default_project_storage_platform()) {}

ProjectStore::ProjectStore(std::shared_ptr<ProjectStoragePlatform> platform)
    : platform_(platform != nullptr
                    ? std::move(platform)
                    : make_default_project_storage_platform()),
      performance_owner_locks_(
          std::make_shared<PerformanceOwnerLocks>()) {}

foundation::Result<void> ProjectStore::hold_performance_owner_lock(
    const std::filesystem::path& bundle,
    const foundation::SequenceSessionId& session_id) {
  const auto key = bundle.lexically_normal().generic_string();
  std::lock_guard lock(performance_owner_locks_->mutex);
  const auto existing = performance_owner_locks_->entries.find(key);
  if (existing != performance_owner_locks_->entries.end()) {
    return existing->second.session_id == session_id
               ? foundation::Result<void>::success()
               : foundation::Result<void>::failure(
                     recording_session_active_error(
                         existing->second.session_id));
  }
  auto acquired = acquire_performance_owner_lock(bundle, session_id);
  if (!acquired.has_value()) {
    return foundation::Result<void>::failure(acquired.error());
  }
  performance_owner_locks_->entries.emplace(
      key,
      PerformanceOwnerLocks::Entry{
          session_id, std::move(acquired.value())});
  return foundation::Result<void>::success();
}

void ProjectStore::release_performance_owner_lock(
    const std::filesystem::path& bundle) noexcept {
  try {
    const auto key = bundle.lexically_normal().generic_string();
    std::lock_guard lock(performance_owner_locks_->mutex);
    performance_owner_locks_->entries.erase(key);
  } catch (...) {
  }
}

foundation::Result<std::unique_ptr<PerformanceOwnerLock>>
ProjectStore::acquire_performance_owner_lock(
    const std::filesystem::path& bundle,
    const foundation::SequenceSessionId& session_id) {
  if (!domain::is_valid_uuid(session_id.value())) {
    return foundation::Result<
        std::unique_ptr<PerformanceOwnerLock>>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance owner lock session id is invalid",
    });
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<
        std::unique_ptr<PerformanceOwnerLock>>::failure(tree.error());
  }
  int flags = O_CREAT | O_RDWR | O_CLOEXEC;
#if defined(O_NOFOLLOW)
  flags |= O_NOFOLLOW;
#endif
  const auto path = performance_owner_lock_path(bundle);
  const int descriptor = ::open(path.c_str(), flags, 0600);
  if (descriptor < 0) {
    return foundation::Result<
        std::unique_ptr<PerformanceOwnerLock>>::failure(Error{
        ErrorCode::io_error,
        "Performance owner lock file could not be opened",
        {{"path", path.generic_string()}, {"errno", errno}},
    });
  }
  struct stat metadata {};
  if (::fstat(descriptor, &metadata) != 0 ||
      !S_ISREG(metadata.st_mode) || metadata.st_uid != ::geteuid()) {
    const auto failure = errno;
    (void)::close(descriptor);
    return foundation::Result<
        std::unique_ptr<PerformanceOwnerLock>>::failure(Error{
        ErrorCode::io_error,
        "Performance owner lock file is not a private regular file",
        {{"path", path.generic_string()}, {"errno", failure}},
    });
  }
  if (::flock(descriptor, LOCK_EX | LOCK_NB) != 0) {
    const auto failure = errno;
    (void)::close(descriptor);
    if (failure == EWOULDBLOCK || failure == EAGAIN) {
      return foundation::Result<
          std::unique_ptr<PerformanceOwnerLock>>::failure(
          recording_session_active_error(session_id));
    }
    return foundation::Result<
        std::unique_ptr<PerformanceOwnerLock>>::failure(Error{
        ErrorCode::io_error,
        "Performance owner lock could not be acquired",
        {{"path", path.generic_string()}, {"errno", failure}},
    });
  }
  auto owner_lock = std::unique_ptr<PerformanceOwnerLock>{
      new PerformanceOwnerLock(
          std::make_unique<PerformanceOwnerLock::Impl>(descriptor))};
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<
        std::unique_ptr<PerformanceOwnerLock>>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  if (!active.has_value()) {
    return foundation::Result<
        std::unique_ptr<PerformanceOwnerLock>>::failure(active.error());
  }
  if (active.value().session_id != session_id) {
    return foundation::Result<
        std::unique_ptr<PerformanceOwnerLock>>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance owner lock session does not match the active Journal",
    });
  }
  return foundation::Result<std::unique_ptr<PerformanceOwnerLock>>::success(
      std::move(owner_lock));
}

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
  // The Contract level of `initial` does not survive: every Project this Build
  // persists is written as lmdj.project.v5. A caller that wants a v3 Project on
  // disk has to write one, which is what tests/core/support/legacy_project.hpp
  // is for.
  const auto persisted_initial = persisted_projection(initial);
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
  SequenceJournal performance_journal{platform_};
  auto performance = performance_journal.read_active_performance(bundle);
  if (performance.has_value()) {
    if (performance.value().state ==
        SequenceSessionState::recovery_required) {
      return foundation::Result<CommandExecution>::failure(Error{
          ErrorCode::invalid_argument,
          "Project mutation is blocked until durable Performance rebase reconciliation completes",
          {{"reason", "performance_rebase_recovery_required"},
           {"session_id", performance.value().session_id.value()},
           {"remedy",
            "reopen the Project and retry the exact prepared command; no other Authoring Command is admissible"}},
      });
    }
    const bool sample_class = std::visit(
        [](const auto& value) {
          using Type = std::decay_t<decltype(value)>;
          return std::is_same_v<Type, domain::ImportAsset> ||
                 std::is_same_v<Type, domain::AssignPad>;
        },
        command);
    const bool settings =
        std::holds_alternative<domain::UpdateSequenceSettings>(command);
    return foundation::Result<CommandExecution>::failure(Error{
        ErrorCode::invalid_argument,
        settings
            ? "Performance settings mutation requires the session-owned durable rebase path"
            : sample_class
                  ? "Sample-class mutation is blocked while Performance recording remains active"
                  : "unknown Authoring Command fails closed during Performance recording",
        {{"reason",
          settings
              ? "performance_rebase_owner_required"
              : sample_class ? "performance_sample_command_blocked"
                             : "performance_unknown_command_blocked"},
         {"session_id", performance.value().session_id.value()},
         {"recording_sealed", false},
         {"remedy",
          settings
              ? "call execute_performance_rebase with the active session id"
              : sample_class
                    ? "stop and save or discard the Performance draft before retrying the Sample-class command"
                    : "stop, save, discard, or exactly reconcile the Performance session before retrying"}},
    });
  }
  if (performance.error().code != ErrorCode::not_found) {
    return foundation::Result<CommandExecution>::failure(
        performance.error());
  }
  auto persisted_identity = persisted_command(command);
  auto admitted =
      admit_sequence_authoring(platform_, bundle, &persisted_identity);
  if (!admitted.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        admitted.error());
  }
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
  if (admitted.value().has_value() &&
      outcome.value().state.revision >
          admitted.value()->expected_revision) {
    SequenceJournal journal{platform_};
    auto rebased = journal.rebase(
        bundle,
        admitted.value()->session_id,
        outcome.value().state.revision);
    if (!rebased.has_value()) {
      return foundation::Result<CommandExecution>::failure(
          rebased.error());
    }
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

foundation::Result<domain::AppliedCommand> ProjectStore::create_performance(
    const std::filesystem::path& bundle,
    const CreatePerformance& command) {
  return execute_persisted(platform_, bundle, PersistedCommand{command});
}

foundation::Result<domain::AppliedCommand> ProjectStore::rename_performance(
    const std::filesystem::path& bundle,
    const RenamePerformance& command) {
  return execute_persisted(platform_, bundle, PersistedCommand{command});
}

foundation::Result<domain::AppliedCommand> ProjectStore::delete_performance(
    const std::filesystem::path& bundle,
    const DeletePerformance& command) {
  return execute_persisted(platform_, bundle, PersistedCommand{command});
}

foundation::Result<PerformanceLifecycleReceipt>
ProjectStore::begin_performance_draft(
    const std::filesystem::path& bundle,
    const domain::CommandMeta& meta,
    const foundation::SequenceSessionId& session_id,
    const domain::PerformanceId& performance_id) {
  return begin_performance_draft(
      bundle, BeginPerformanceDraftRequest{meta, session_id, performance_id});
}

foundation::Result<PerformanceLifecycleReceipt>
ProjectStore::begin_performance_draft(
    const std::filesystem::path& bundle,
    const BeginPerformanceDraftRequest& request) {
  if (!domain::is_valid_uuid(request.meta.command_id.value()) ||
      !domain::is_valid_uuid(request.session_id.value()) ||
      !domain::is_valid_uuid(request.performance_id.value())) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance draft begin identity is invalid",
    });
  }
  std::unique_ptr<PerformanceOwnerLock> reattach_owner_lock;
  bool already_attached = false;
  {
    SequenceJournal journal{platform_};
    auto active = journal.read_active_performance(bundle);
    if (active.has_value()) {
      const bool exact_reattach =
          active.value().begin_command_id.has_value() &&
          *active.value().begin_command_id == request.meta.command_id &&
          active.value().session_id == request.session_id &&
          active.value().performance_id == request.performance_id;
      if (exact_reattach) {
        const auto key = bundle.lexically_normal().generic_string();
        {
          std::lock_guard lock(performance_owner_locks_->mutex);
          const auto existing = performance_owner_locks_->entries.find(key);
          if (existing != performance_owner_locks_->entries.end()) {
            if (existing->second.session_id != request.session_id) {
              return foundation::Result<PerformanceLifecycleReceipt>::failure(
                  recording_session_active_error(
                      existing->second.session_id));
            }
            already_attached = true;
          }
        }
        if (!already_attached) {
          auto acquired = acquire_performance_owner_lock(
              bundle, request.session_id);
          if (!acquired.has_value()) {
            return foundation::Result<PerformanceLifecycleReceipt>::failure(
                acquired.error());
          }
          reattach_owner_lock = std::move(acquired.value());
          auto closed = journal.close_performance_transients_for_owner_loss(
              bundle, request.session_id);
          if (!closed.has_value()) {
            return foundation::Result<PerformanceLifecycleReceipt>::failure(
                closed.error());
          }
        }
      } else {
        auto reconciled = reconcile_performance_recovery(bundle);
        if (!reconciled.has_value()) {
          return foundation::Result<PerformanceLifecycleReceipt>::failure(
              reconciled.error());
        }
      }
    } else if (active.error().code != ErrorCode::not_found) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          active.error());
    }
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        loaded.error());
  }
  auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        recovered.error());
  }
  const CreatePerformance command{
      request.meta,
      request.performance_id,
      "Untitled Performance",
  };
  const domain::Performance intended{
      request.performance_id,
      command.name,
      loaded.value().state.bpm,
      request.meta.expected_revision,
      std::nullopt,
      {},
  };
  auto valid = domain::validate_performance(intended);
  if (!valid.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        valid.error());
  }
  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  if (active.has_value()) {
    if (!active.value().begin_command_id.has_value() ||
        *active.value().begin_command_id != request.meta.command_id ||
        active.value().session_id != request.session_id ||
        active.value().performance_id != request.performance_id) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance begin collides with the active recording session",
          {{"reason", "performance_begin_command_conflict"},
           {"remedy",
            "retry the exact original begin identity or finish the active Performance session before starting another draft"}},
      });
    }
  } else if (active.error().code == ErrorCode::not_found) {
    auto begun = journal.begin_performance_draft_locked(
        bundle,
        request.meta.command_id,
        request.session_id,
        request.performance_id,
        performance_fingerprint(intended),
        request.meta.expected_revision);
    if (!begun.has_value()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          begun.error());
    }
  } else {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        active.error());
  }

  auto outcome = commit_loaded(
      platform_, bundle, std::move(loaded.value()),
      PersistedCommand{command}, std::nullopt, nullptr);
  if (!outcome.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        outcome.error());
  }
  auto refreshed = journal.read_active_performance(bundle);
  if (!refreshed.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        refreshed.error());
  }
  if (refreshed.value().state ==
          SequenceSessionState::recovery_required &&
      refreshed.value().expected_revision == request.meta.expected_revision) {
    const auto target =
        outcome.value().state.performances.find(request.performance_id);
    if (target == outcome.value().state.performances.end()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          invalid_project(
              "Performance draft begin receipt target is missing",
              bundle / "manifest.json"));
    }
    auto completed = journal.complete_performance_begin_locked(
        bundle,
        request.session_id,
        outcome.value().state.revision,
        performance_fingerprint(target->second));
    if (!completed.has_value()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          completed.error());
    }
  }
  const PerformanceLifecycleReceipt receipt{
      request.performance_id,
      outcome.value().state.revision,
      outcome.value().replayed,
  };
  operation.reset();
  if (reattach_owner_lock != nullptr) {
    const auto key = bundle.lexically_normal().generic_string();
    std::lock_guard lock(performance_owner_locks_->mutex);
    const auto [existing, inserted] =
        performance_owner_locks_->entries.emplace(
            key,
            PerformanceOwnerLocks::Entry{
                request.session_id, std::move(reattach_owner_lock)});
    if (!inserted && existing->second.session_id != request.session_id) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          recording_session_active_error(existing->second.session_id));
    }
  } else if (!already_attached) {
    auto held = hold_performance_owner_lock(bundle, request.session_id);
    if (!held.has_value()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          held.error());
    }
  }
  return foundation::Result<PerformanceLifecycleReceipt>::success(receipt);
}

foundation::Result<PerformanceStopReceipt>
ProjectStore::stop_performance_session(
    const std::filesystem::path& bundle,
    const foundation::SequenceSessionId& session_id,
    const foundation::CommandId& request_id) {
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  SequenceJournal journal{platform_};
  auto before = journal.read_active_performance(bundle);
  if (!before.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(before.error());
  }
  const bool replayed =
      before.value().stop_request_id.has_value() &&
      *before.value().stop_request_id == request_id;
  auto stopped =
      journal.stop_performance_locked(bundle, session_id, request_id);
  if (!stopped.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(
        stopped.error());
  }
  auto after = journal.read_active_performance(bundle);
  if (!after.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(after.error());
  }
  return foundation::Result<PerformanceStopReceipt>::success(
      {request_id,
       session_id,
       after.value().performance_id,
       after.value().state,
       after.value().pending_events.size(),
       replayed});
}

foundation::Result<PerformanceLifecycleReceipt>
ProjectStore::save_performance_draft(
    const std::filesystem::path& bundle,
    const domain::CommandMeta& meta,
    const domain::PerformanceId& performance_id,
    std::string name,
    std::optional<foundation::ArtifactRef> artifact) {
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        loaded.error());
  }
  auto recovered = recover_uncommitted(
      *platform_,
      bundle,
      loaded.value(),
      artifact.has_value()
          ? std::optional<std::string_view>{artifact->sha256}
          : std::nullopt);
  if (!recovered.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        recovered.error());
  }
  if (artifact.has_value()) {
    auto verified = verify_managed_wav_artifact(*platform_, bundle, *artifact);
    if (!verified.has_value()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          verified.error());
    }
  }
  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  std::vector<domain::PerformanceEvent> tail;
  foundation::SequenceSessionId session_id{""};
  if (active.has_value()) {
    if (active.value().performance_id != performance_id ||
        active.value().state != SequenceSessionState::stopped ||
        std::ranges::any_of(
            active.value().flushes,
            [](const auto& flush) { return !flush.completed; })) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance save requires the matching stopped draft",
          {{"reason", "performance_draft_not_stopped"},
           {"remedy",
            "stop the matching Performance session and complete every pending flush before saving"}},
      });
    }
    tail = active.value().pending_events;
    session_id = active.value().session_id;
  } else if (active.error().code != ErrorCode::not_found) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        active.error());
  }

  const auto existing = loaded.value().commands.find(meta.command_id);
  if (existing != loaded.value().commands.end()) {
    const auto* saved = std::get_if<FinalizePerformanceDraft>(&existing->second);
    if (saved == nullptr || saved->performance_id != performance_id ||
        saved->name != name || saved->artifact != artifact ||
        (active.has_value() && saved->events != tail)) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance save command id is bound to another command",
          {{"reason", "performance_save_command_conflict"},
           {"remedy",
            "retry the exact original save payload or issue a new command id for a different save"}},
      });
    }
  } else if (!active.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::not_found,
        "stopped Performance draft Journal does not exist",
    });
  }

  const FinalizePerformanceDraft command{
      meta,
      performance_id,
      std::move(name),
      std::move(artifact),
      existing != loaded.value().commands.end()
          ? std::get<FinalizePerformanceDraft>(existing->second).events
          : std::move(tail),
  };
  auto outcome = commit_loaded(
      platform_, bundle, std::move(loaded.value()),
      PersistedCommand{command}, std::nullopt, nullptr);
  if (!outcome.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        outcome.error());
  }
  if (active.has_value()) {
    auto removed = journal.remove_active_performance_locked(
        bundle, session_id, true);
    if (!removed.has_value()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          removed.error());
    }
  }
  release_performance_owner_lock(bundle);
  return foundation::Result<PerformanceLifecycleReceipt>::success(
      {performance_id,
       outcome.value().state.revision,
       outcome.value().replayed});
}

foundation::Result<PerformanceLifecycleReceipt>
ProjectStore::discard_performance_draft(
    const std::filesystem::path& bundle,
    const domain::CommandMeta& meta,
    const domain::PerformanceId& performance_id) {
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        loaded.error());
  }
  auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        recovered.error());
  }
  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  foundation::SequenceSessionId session_id{""};
  if (active.has_value()) {
    if (active.value().performance_id != performance_id ||
        active.value().state != SequenceSessionState::stopped) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance discard requires the matching stopped draft",
          {{"reason", "performance_draft_not_stopped"},
           {"remedy",
            "stop the matching Performance session before discarding its draft"}},
      });
    }
    session_id = active.value().session_id;
  } else if (active.error().code != ErrorCode::not_found) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        active.error());
  }
  const DeletePerformance command{meta, performance_id};
  const auto existing = loaded.value().commands.find(meta.command_id);
  if (existing != loaded.value().commands.end() &&
      command_json(existing->second) !=
          command_json(PersistedCommand{command})) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance discard command id is bound to another command",
        {{"reason", "performance_discard_command_conflict"},
         {"remedy",
          "retry the exact original discard identity or issue a new command id"}},
    });
  }
  if (!active.has_value() && existing == loaded.value().commands.end()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::not_found,
        "stopped Performance draft Journal does not exist",
    });
  }
  auto outcome = commit_loaded(
      platform_, bundle, std::move(loaded.value()),
      PersistedCommand{command}, std::nullopt, nullptr);
  if (!outcome.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        outcome.error());
  }
  if (active.has_value()) {
    auto removed = journal.remove_active_performance_locked(
        bundle, session_id, true);
    if (!removed.has_value()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          removed.error());
    }
  }
  release_performance_owner_lock(bundle);
  return foundation::Result<PerformanceLifecycleReceipt>::success(
      {performance_id,
       outcome.value().state.revision,
       outcome.value().replayed});
}

foundation::Result<PerformanceLifecycleReceipt>
ProjectStore::apply_performance_recovery(
    const std::filesystem::path& bundle,
    const domain::CommandMeta& meta,
    const foundation::SequenceSessionId& session_id) {
  auto reconciled = reconcile_performance_recovery(bundle);
  if (!reconciled.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        reconciled.error());
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        loaded.error());
  }
  auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        recovered.error());
  }
  SequenceJournal journal{platform_};
  auto candidates = journal.list_performance_recoverable(bundle);
  if (!candidates.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        candidates.error());
  }
  auto active = journal.read_active_performance(bundle);
  if (active.has_value() && active.value().session_id == session_id &&
      active.value().state == SequenceSessionState::stopped) {
    const auto command = loaded.value().commands.find(meta.command_id);
    const auto* mutation =
        command != loaded.value().commands.end()
            ? std::get_if<PerformanceMutation>(&command->second)
            : nullptr;
    const auto receipt = loaded.value().receipts.find(meta.command_id);
    if (mutation != nullptr && receipt != loaded.value().receipts.end() &&
        mutation->performance_id == active.value().performance_id) {
      const auto candidate = std::find_if(
          candidates.value().begin(), candidates.value().end(),
          [&session_id](const auto& value) {
            return value.journal.session_id == session_id;
          });
      if (candidate != candidates.value().end()) {
        const auto target = loaded.value().state.performances.find(
            active.value().performance_id);
        if (target == loaded.value().state.performances.end()) {
          return foundation::Result<PerformanceLifecycleReceipt>::failure(
              invalid_project(
                  "recovered Performance draft is missing",
                  bundle / "manifest.json"));
        }
        auto cleaned = journal.restore_stopped_performance_locked(
            bundle,
            *candidate,
            loaded.value().state.revision,
            performance_fingerprint(target->second),
            meta.command_id);
        if (!cleaned.has_value()) {
          return foundation::Result<PerformanceLifecycleReceipt>::failure(
              cleaned.error());
        }
      }
      return foundation::Result<PerformanceLifecycleReceipt>::success(
          {active.value().performance_id,
           receipt->second.committed_revision,
           true});
    }
  }
  if (active.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "active Performance session blocks recovery apply",
        {{"reason", "recording_session_active"},
         {"remedy",
          "stop or reconcile the active Performance session before applying a sealed recovery candidate"}},
    });
  }
  if (active.error().code != ErrorCode::not_found) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        active.error());
  }
  const auto candidate = std::find_if(
      candidates.value().begin(), candidates.value().end(),
      [&session_id](const auto& value) {
        return value.journal.session_id == session_id;
      });
  if (candidate == candidates.value().end()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::not_found,
        "Performance recovery candidate does not exist",
    });
  }
  if (candidate->journal.pending_events.empty() ||
      std::ranges::any_of(
          candidate->journal.flushes,
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance recovery apply requires a durable stopped tail",
        {{"reason", "performance_recovery_tail_incomplete"},
         {"recovery_retained", true},
         {"remedy",
          "retain the candidate and retry after its durable tail and flush completions are available"}},
    });
  }
  const PerformanceMutation mutation{
      meta,
      candidate->journal.performance_id,
      candidate->journal.pending_events,
  };
  const auto existing_command =
      loaded.value().commands.find(meta.command_id);
  if (existing_command != loaded.value().commands.end() &&
      command_json(existing_command->second) !=
          command_json(PersistedCommand{mutation})) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance recovery command id is bound to another command",
        {{"reason", "performance_recovery_command_conflict"},
         {"recovery_retained", true},
         {"remedy",
          "retry the exact original recovery payload or use a new command id"}},
    });
  }
  const auto existing_receipt = loaded.value().receipts.find(meta.command_id);
  if (existing_receipt != loaded.value().receipts.end()) {
    const auto updated = loaded.value().state.performances.find(
        candidate->journal.performance_id);
    if (updated == loaded.value().state.performances.end()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          invalid_project(
              "committed Performance recovery target is missing",
              bundle / "manifest.json"));
    }
    auto restored = journal.restore_stopped_performance_locked(
        bundle,
        *candidate,
        loaded.value().state.revision,
        performance_fingerprint(updated->second),
        meta.command_id);
    if (!restored.has_value()) {
      return foundation::Result<PerformanceLifecycleReceipt>::failure(
          restored.error());
    }
    return foundation::Result<PerformanceLifecycleReceipt>::success(
        {candidate->journal.performance_id,
         existing_receipt->second.committed_revision,
         true});
  }
  const auto target = loaded.value().state.performances.find(
      candidate->journal.performance_id);
  if (target == loaded.value().state.performances.end() ||
      performance_fingerprint(target->second) !=
          candidate->journal.performance_fingerprint ||
      loaded.value().state.revision != candidate->journal.expected_revision) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_project,
        "Performance recovery draft fingerprint does not match Project Truth",
        {{"reason", "performance_recovery_target_incompatible"},
         {"recovery_retained", true},
         {"remedy",
          "retain the candidate and recover it only against the matching Performance draft revision and fingerprint"}},
    });
  }
  auto outcome = commit_loaded(
      platform_, bundle, std::move(loaded.value()),
      PersistedCommand{mutation}, std::nullopt, nullptr);
  if (!outcome.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        outcome.error());
  }
  const auto updated = outcome.value().state.performances.find(
      candidate->journal.performance_id);
  if (updated == outcome.value().state.performances.end()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        invalid_project(
            "Performance recovery target disappeared after publication",
            bundle / "manifest.json"));
  }
  auto restored = journal.restore_stopped_performance_locked(
      bundle,
      *candidate,
      outcome.value().state.revision,
      performance_fingerprint(updated->second),
      meta.command_id);
  if (!restored.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        restored.error());
  }
  return foundation::Result<PerformanceLifecycleReceipt>::success(
      {candidate->journal.performance_id,
       outcome.value().state.revision,
       outcome.value().replayed});
}

foundation::Result<PerformanceStopReceipt>
ProjectStore::discard_performance_recovery(
    const std::filesystem::path& bundle,
    const foundation::SequenceSessionId& session_id,
    const foundation::CommandId& request_id) {
  auto reconciled = reconcile_performance_recovery(bundle);
  if (!reconciled.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(
        reconciled.error());
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(loaded.error());
  }
  SequenceJournal journal{platform_};
  auto candidates = journal.list_performance_recoverable(bundle);
  if (!candidates.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(
        candidates.error());
  }
  auto active = journal.read_active_performance(bundle);
  if (active.has_value()) {
    if (active.value().session_id == session_id &&
        active.value().state == SequenceSessionState::stopped &&
        active.value().stop_request_id == request_id) {
      const auto candidate = std::find_if(
          candidates.value().begin(), candidates.value().end(),
          [&session_id](const auto& value) {
            return value.journal.session_id == session_id;
          });
      if (candidate != candidates.value().end()) {
        const auto target = loaded.value().state.performances.find(
            active.value().performance_id);
        if (target == loaded.value().state.performances.end()) {
          return foundation::Result<PerformanceStopReceipt>::failure(
              invalid_project(
                  "recovered Performance draft is missing",
                  bundle / "manifest.json"));
        }
        auto cleaned = journal.restore_stopped_performance_locked(
            bundle,
            *candidate,
            loaded.value().state.revision,
            performance_fingerprint(target->second),
            request_id);
        if (!cleaned.has_value()) {
          return foundation::Result<PerformanceStopReceipt>::failure(
              cleaned.error());
        }
      }
      return foundation::Result<PerformanceStopReceipt>::success(
          {request_id,
           session_id,
           active.value().performance_id,
           SequenceSessionState::stopped,
           0,
           true});
    }
    return foundation::Result<PerformanceStopReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "active Performance session blocks recovery discard",
        {{"reason", "recording_session_active"},
         {"remedy",
          "stop or reconcile the active Performance session before discarding a sealed recovery candidate"}},
    });
  }
  if (active.error().code != ErrorCode::not_found) {
    return foundation::Result<PerformanceStopReceipt>::failure(active.error());
  }
  const auto candidate = std::find_if(
      candidates.value().begin(), candidates.value().end(),
      [&session_id](const auto& value) {
        return value.journal.session_id == session_id;
      });
  if (candidate == candidates.value().end()) {
    return foundation::Result<PerformanceStopReceipt>::failure(Error{
        ErrorCode::not_found,
        "Performance recovery candidate does not exist",
    });
  }
  const auto target = loaded.value().state.performances.find(
      candidate->journal.performance_id);
  if (target == loaded.value().state.performances.end()) {
    return foundation::Result<PerformanceStopReceipt>::failure(Error{
        ErrorCode::invalid_project,
        "Performance recovery draft no longer exists",
        {{"reason", "performance_recovery_target_missing"},
         {"recovery_retained", true},
         {"remedy",
          "retain the candidate and restore the matching Performance draft before retrying recovery discard"}},
    });
  }
  auto restored = journal.restore_stopped_performance_locked(
      bundle,
      *candidate,
      loaded.value().state.revision,
      performance_fingerprint(target->second),
      request_id);
  if (!restored.has_value()) {
    return foundation::Result<PerformanceStopReceipt>::failure(
        restored.error());
  }
  return foundation::Result<PerformanceStopReceipt>::success(
      {request_id,
       session_id,
       candidate->journal.performance_id,
       SequenceSessionState::stopped,
       0,
       false});
}

foundation::Result<PerformanceLifecycleReceipt>
ProjectStore::bind_performance_recording(
    const std::filesystem::path& bundle,
    const domain::CommandMeta& meta,
    const domain::PerformanceId& performance_id,
    const foundation::ArtifactRef& artifact) {
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        loaded.error());
  }
  auto recovered = recover_uncommitted(
      *platform_, bundle, loaded.value(), artifact.sha256);
  if (!recovered.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        recovered.error());
  }
  auto verified = verify_managed_wav_artifact(*platform_, bundle, artifact);
  if (!verified.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        verified.error());
  }
  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  if (active.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance recording bind is blocked by an active draft",
        {{"reason", "performance_session_active"},
         {"remedy",
          "stop and save or discard the active Performance draft before binding a recording"}},
    });
  }
  if (active.error().code != ErrorCode::not_found) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        active.error());
  }
  auto candidates = journal.list_performance_recoverable(bundle);
  if (!candidates.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        candidates.error());
  }
  if (std::ranges::any_of(
          candidates.value(),
          [&performance_id](const auto& candidate) {
            return candidate.journal.performance_id == performance_id;
          })) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance recording bind is blocked by recovery",
        {{"reason", "performance_recovery_pending"},
         {"remedy",
          "apply or discard the recoverable Performance tail before binding a recording"}},
    });
  }
  const auto target = loaded.value().state.performances.find(performance_id);
  if (target == loaded.value().state.performances.end()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::not_found,
        "Performance recording bind target does not exist",
    });
  }
  if (target->second.recording_artifact.has_value()) {
    if (*target->second.recording_artifact == artifact) {
      return foundation::Result<PerformanceLifecycleReceipt>::success(
          {performance_id, loaded.value().state.revision, true});
    }
    return foundation::Result<PerformanceLifecycleReceipt>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance recording ArtifactRef is already bound",
        {{"reason", "performance_recording_conflict"},
         {"remedy",
          "keep the existing recording ArtifactRef or create a new Performance; replacement is not permitted"}},
    });
  }
  const BindPerformanceRecording command{meta, performance_id, artifact};
  auto outcome = commit_loaded(
      platform_, bundle, std::move(loaded.value()),
      PersistedCommand{command}, std::nullopt, nullptr);
  if (!outcome.has_value()) {
    return foundation::Result<PerformanceLifecycleReceipt>::failure(
        outcome.error());
  }
  return foundation::Result<PerformanceLifecycleReceipt>::success(
      {performance_id,
       outcome.value().state.revision,
       outcome.value().replayed});
}

foundation::Result<CommandExecution>
ProjectStore::execute_performance_rebase(
    const std::filesystem::path& bundle,
    const foundation::SequenceSessionId& session_id,
    const domain::UpdateSequenceSettings& command) {
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<CommandExecution>::failure(tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<CommandExecution>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<CommandExecution>::failure(loaded.error());
  }
  auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<CommandExecution>::failure(recovered.error());
  }
  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  if (!active.has_value() || active.value().session_id != session_id) {
    return foundation::Result<CommandExecution>::failure(
        active.has_value()
            ? Error{ErrorCode::invalid_argument,
                    "Performance rebase owner does not match",
                    {{"reason", "performance_rebase_owner_mismatch"},
                     {"remedy",
                      "retry with the active Performance session id"}}}
            : active.error());
  }
  const auto persisted = PersistedCommand{command};
  const auto fingerprint = canonical_fingerprint(command_json(persisted));
  const auto existing = std::find_if(
      active.value().rebases.begin(), active.value().rebases.end(),
      [&command](const auto& rebase) {
        return rebase.command_id == command.meta.command_id;
      });
  if (active.value().state == SequenceSessionState::recovery_required &&
      existing == active.value().rebases.end()) {
    return foundation::Result<CommandExecution>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance rebase recovery requires the exact prepared command",
        {{"reason", "performance_rebase_recovery_required"},
         {"remedy",
          "reopen the Project and retry the exact command_id and immutable command payload already recorded by rebase_prepare"}},
    });
  }
  if (existing != active.value().rebases.end() &&
      (existing->command_fingerprint != fingerprint ||
       existing->from_revision != command.meta.expected_revision ||
       existing->to_revision != command.meta.expected_revision + 1)) {
    return foundation::Result<CommandExecution>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance rebase command id is bound to another command",
        {{"reason", "performance_rebase_command_conflict"},
         {"remedy",
          "retry the exact prepared command payload or issue a new command id before preparation"}},
    });
  }
  if (existing == active.value().rebases.end()) {
    auto prepared = journal.prepare_performance_rebase_locked(
        bundle,
        session_id,
        {command.meta.command_id,
         fingerprint,
         command.meta.expected_revision,
         command.meta.expected_revision + 1,
         std::nullopt,
         false});
    if (!prepared.has_value()) {
      return foundation::Result<CommandExecution>::failure(prepared.error());
    }
  } else if (existing->completed) {
    auto outcome = commit_loaded(
        platform_, bundle, std::move(loaded.value()), persisted,
        std::nullopt, nullptr);
    if (!outcome.has_value()) {
      return foundation::Result<CommandExecution>::failure(outcome.error());
    }
    return foundation::Result<CommandExecution>::success(
        {domain::Command{command}, std::move(outcome.value())});
  }

  auto outcome = commit_loaded(
      platform_, bundle, std::move(loaded.value()), persisted,
      std::nullopt, nullptr);
  if (!outcome.has_value()) {
    return foundation::Result<CommandExecution>::failure(outcome.error());
  }
  const auto target = outcome.value().state.performances.find(
      active.value().performance_id);
  if (target == outcome.value().state.performances.end()) {
    return foundation::Result<CommandExecution>::failure(
        invalid_project(
            "Performance rebase target disappeared after publication",
            bundle / "manifest.json"));
  }
  auto completed = journal.complete_performance_rebase_locked(
      bundle,
      session_id,
      command.meta.command_id,
      outcome.value().state.revision,
      command.bpm.has_value()
          ? std::optional<std::uint16_t>{outcome.value().state.bpm}
          : std::nullopt,
      performance_fingerprint(target->second));
  if (!completed.has_value()) {
    return foundation::Result<CommandExecution>::failure(completed.error());
  }
  return foundation::Result<CommandExecution>::success(
      {domain::Command{command}, std::move(outcome.value())});
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
          receipt->second.committed_revision,
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

foundation::Result<std::optional<PerformanceFlushExecution>>
ProjectStore::replay_performance_flush(
    const std::filesystem::path& bundle,
    const PerformanceFlushIdentity& identity) {
  if (!domain::is_valid_uuid(identity.session_id.value()) ||
      !domain::is_valid_uuid(identity.command_id.value()) ||
      !domain::is_valid_uuid(identity.performance_id.value())) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance flush identity is invalid",
    });
  }
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto loaded = load_project(*platform_, bundle);
  if (!loaded.has_value()) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(loaded.error());
  }
  auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(
        recovered.error());
  }
  const auto command = loaded.value().commands.find(identity.command_id);
  if (command == loaded.value().commands.end()) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::success(std::nullopt);
  }
  const auto stored =
      loaded.value().performance_flush_identities.find(identity.command_id);
  const auto* mutation =
      std::get_if<PerformanceMutation>(&command->second);
  if (stored == loaded.value().performance_flush_identities.end() ||
      stored->second != identity || mutation == nullptr ||
      mutation->performance_id != identity.performance_id) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance flush identity does not match the persisted mutation",
    });
  }
  const auto receipt = loaded.value().receipts.find(identity.command_id);
  if (receipt == loaded.value().receipts.end()) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(
        invalid_project(
            "persisted Performance flush receipt is missing",
            bundle / "manifest.json"));
  }
  return foundation::Result<
      std::optional<PerformanceFlushExecution>>::success(
      PerformanceFlushExecution{
          identity,
          *mutation,
          PerformanceMutationReceipt{receipt->second.committed_revision},
          std::move(loaded.value().state),
          true,
      });
}

foundation::Result<std::optional<PerformanceFlushExecution>>
ProjectStore::replay_performance_flush(
    const std::filesystem::path& bundle,
    const foundation::SequenceSessionId& session_id,
    const foundation::CommandId& command_id) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(command_id.value())) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance flush identity is invalid",
    });
  }

  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  if (active.has_value()) {
    const auto flush = std::find_if(
        active.value().flushes.begin(), active.value().flushes.end(),
        [&command_id](const auto& candidate) {
          return candidate.command_id == command_id;
        });
    if (flush != active.value().flushes.end()) {
      if (active.value().session_id != session_id) {
        return foundation::Result<
            std::optional<PerformanceFlushExecution>>::failure(Error{
            ErrorCode::invalid_argument,
            "Performance flush identity does not match the persisted mutation",
            {{"reason", "performance_command_conflict"}},
        });
      }
      return replay_performance_flush(
          bundle,
          PerformanceFlushIdentity{
              session_id,
              flush->flush_seq,
              command_id,
              flush->performance_id,
          });
    }
  } else if (active.error().code != ErrorCode::not_found) {
    return foundation::Result<
        std::optional<PerformanceFlushExecution>>::failure(active.error());
  }

  std::optional<PerformanceFlushIdentity> identity;
  {
    auto tree = validate_managed_bundle_tree(*platform_, bundle);
    if (!tree.has_value()) {
      return foundation::Result<
          std::optional<PerformanceFlushExecution>>::failure(tree.error());
    }
    auto lease = platform_->acquire_writer(bundle);
    if (!lease.has_value()) {
      return foundation::Result<
          std::optional<PerformanceFlushExecution>>::failure(lease.error());
    }
    auto operation = std::move(lease.value());
    (void)operation;
    auto loaded = load_project(*platform_, bundle);
    if (!loaded.has_value()) {
      return foundation::Result<
          std::optional<PerformanceFlushExecution>>::failure(loaded.error());
    }
    auto recovered = recover_uncommitted(*platform_, bundle, loaded.value());
    if (!recovered.has_value()) {
      return foundation::Result<
          std::optional<PerformanceFlushExecution>>::failure(
          recovered.error());
    }
    const auto stored =
        loaded.value().performance_flush_identities.find(command_id);
    if (stored == loaded.value().performance_flush_identities.end()) {
      if (loaded.value().commands.contains(command_id)) {
        return foundation::Result<
            std::optional<PerformanceFlushExecution>>::failure(Error{
            ErrorCode::invalid_argument,
            "Performance flush command id is bound to a different mutation",
            {{"reason", "performance_command_conflict"}},
        });
      }
      return foundation::Result<
          std::optional<PerformanceFlushExecution>>::success(std::nullopt);
    }
    if (stored->second.session_id != session_id) {
      return foundation::Result<
          std::optional<PerformanceFlushExecution>>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance flush identity does not match the persisted mutation",
          {{"reason", "performance_command_conflict"}},
      });
    }
    identity = stored->second;
  }
  return replay_performance_flush(bundle, *identity);
}

foundation::Result<PerformanceFlushExecution>
ProjectStore::execute_performance_flush(
    const std::filesystem::path& bundle,
    const PerformanceFlushIdentity& identity) {
  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  if (!active.has_value()) {
    return foundation::Result<PerformanceFlushExecution>::failure(
        active.error());
  }
  if (active.value().session_id != identity.session_id ||
      active.value().performance_id != identity.performance_id) {
    return foundation::Result<PerformanceFlushExecution>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance flush session does not match the active Journal",
    });
  }
  const auto flush = std::find_if(
      active.value().flushes.begin(), active.value().flushes.end(),
      [&identity](const auto& candidate) {
        return candidate.flush_seq == identity.flush_seq;
      });
  if (flush == active.value().flushes.end() ||
      flush->command_id != identity.command_id ||
      flush->performance_id != identity.performance_id) {
    return foundation::Result<PerformanceFlushExecution>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance flush identity is not durably journaled",
        {{"reason", "performance_command_conflict"}},
    });
  }
  if (flush->completed) {
    auto replayed = replay_performance_flush(bundle, identity);
    if (!replayed.has_value()) {
      return foundation::Result<PerformanceFlushExecution>::failure(
          replayed.error());
    }
    if (!replayed.value().has_value()) {
      return foundation::Result<PerformanceFlushExecution>::failure(
          invalid_project(
              "completed Performance flush receipt is missing",
              bundle / "manifest.json"));
    }
    return foundation::Result<PerformanceFlushExecution>::success(
        std::move(*replayed.value()));
  }

  const PerformanceMutation mutation{
      {identity.command_id, flush->expected_revision},
      identity.performance_id,
      flush->canonical_events,
  };
  auto committed = [&]() -> foundation::Result<domain::AppliedCommand> {
    auto tree = validate_managed_bundle_tree(*platform_, bundle);
    if (!tree.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(tree.error());
    }
    auto lease = platform_->acquire_writer(bundle);
    if (!lease.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          lease.error());
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
    auto locked_active = journal.read_active_performance(bundle);
    if (!locked_active.has_value() ||
        locked_active.value().session_id != identity.session_id) {
      return foundation::Result<domain::AppliedCommand>::failure(
          locked_active.has_value()
              ? Error{
                    ErrorCode::invalid_argument,
                    "Performance Journal changed before flush admission",
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
        locked_flush->completed ||
        locked_flush->command_id != identity.command_id ||
        locked_flush->performance_id != identity.performance_id ||
        locked_flush->expected_revision != flush->expected_revision ||
        locked_flush->canonical_events != flush->canonical_events) {
      return foundation::Result<domain::AppliedCommand>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance Journal changed before flush admission",
      });
    }
    const auto existing =
        loaded.value().performance_flush_identities.find(identity.command_id);
    const bool has_receipt =
        loaded.value().receipts.contains(identity.command_id);
    if (has_receipt &&
        (existing == loaded.value().performance_flush_identities.end() ||
         existing->second != identity)) {
      return foundation::Result<domain::AppliedCommand>::failure(Error{
          ErrorCode::invalid_argument,
          "command id is bound to a different Performance flush identity",
      });
    }
    if (!has_receipt) {
      const auto target =
          loaded.value().state.performances.find(identity.performance_id);
      if (target == loaded.value().state.performances.end() ||
          performance_fingerprint(target->second) !=
              locked_active.value().performance_fingerprint) {
        return foundation::Result<domain::AppliedCommand>::failure(Error{
            ErrorCode::invalid_project,
            "Performance recovery target was deleted or changed",
            {{"reason", "performance_recovery_target_incompatible"},
             {"recovery_retained", true},
             {"remedy",
              "retain the recovery journal and choose an explicitly "
              "compatible Performance before retrying"}},
        });
      }
    }
    return commit_loaded(
        platform_,
        bundle,
        std::move(loaded.value()),
        PersistedCommand{mutation},
        std::nullopt,
        nullptr,
        std::nullopt,
        identity);
  }();
  if (!committed.has_value()) {
    return foundation::Result<PerformanceFlushExecution>::failure(
        committed.error());
  }
  auto visible = replay_performance_flush(bundle, identity);
  if (!visible.has_value()) {
    return foundation::Result<PerformanceFlushExecution>::failure(
        visible.error());
  }
  if (!visible.value().has_value()) {
    return foundation::Result<PerformanceFlushExecution>::failure(Error{
        ErrorCode::io_error,
        "Performance flush receipt is not visible from the manifest head",
    });
  }
  const auto target =
      visible.value()->state.performances.find(identity.performance_id);
  if (target == visible.value()->state.performances.end()) {
    return foundation::Result<PerformanceFlushExecution>::failure(
        invalid_project(
            "Performance flush target disappeared after publication",
            bundle / "manifest.json"));
  }
  auto completed = journal.complete_performance_flush(
      bundle,
      identity.session_id,
      identity.flush_seq,
      visible.value()->state.revision,
      performance_fingerprint(target->second));
  if (!completed.has_value()) {
    return foundation::Result<PerformanceFlushExecution>::failure(
        completed.error());
  }
  auto result = std::move(*visible.value());
  result.replayed = committed.value().replayed;
  return foundation::Result<PerformanceFlushExecution>::success(
      std::move(result));
}

foundation::Result<std::vector<PerformanceRecoveryCandidate>>
ProjectStore::list_performance_recovery(
    const std::filesystem::path& bundle) const {
  SequenceJournal journal{platform_};
  auto candidates = journal.list_performance_recoverable(bundle);
  if (!candidates.has_value()) {
    return candidates;
  }
  auto active = journal.read_active_performance(bundle);
  if (active.has_value()) {
    auto preview = preview_performance_owner_loss(active.value());
    if (!preview.has_value()) {
      return foundation::Result<
          std::vector<PerformanceRecoveryCandidate>>::failure(
          preview.error());
    }
    active.value().pending_events =
        std::move(preview.value().canonical_events);
    std::string reason;
    switch (active.value().state) {
      case SequenceSessionState::active:
        reason = "active";
        break;
      case SequenceSessionState::switching:
        reason = "switching";
        break;
      case SequenceSessionState::stopped:
        reason = "stopped";
        break;
      case SequenceSessionState::recovery_required:
        reason = "recovery_required";
        break;
      case SequenceSessionState::owner_lost:
        reason = "owner_lost";
        break;
      case SequenceSessionState::abandoned:
        reason = "abandoned";
        break;
    }
    candidates.value().push_back(PerformanceRecoveryCandidate{
        std::move(active.value()),
        std::move(reason),
        bundle / "recovery/active/performance.jsonl",
    });
  } else if (active.error().code != ErrorCode::not_found) {
    return foundation::Result<
        std::vector<PerformanceRecoveryCandidate>>::failure(active.error());
  }
  return candidates;
}

foundation::Result<std::vector<PerformanceRecoveryCandidate>>
ProjectStore::reconcile_performance_recovery(
    const std::filesystem::path& bundle) {
  SequenceJournal journal{platform_};
  auto active = journal.read_active_performance(bundle);
  if (!active.has_value()) {
    if (active.error().code == ErrorCode::not_found) {
      return journal.list_performance_recoverable(bundle);
    }
    return foundation::Result<
        std::vector<PerformanceRecoveryCandidate>>::failure(active.error());
  }
  if (active.value().state == SequenceSessionState::stopped) {
    return journal.list_performance_recoverable(bundle);
  }
  auto owner_lock = acquire_performance_owner_lock(
      bundle, active.value().session_id);
  if (!owner_lock.has_value()) {
    return foundation::Result<
        std::vector<PerformanceRecoveryCandidate>>::failure(
        owner_lock.error());
  }
  active = journal.read_active_performance(bundle);
  if (!active.has_value()) {
    return foundation::Result<
        std::vector<PerformanceRecoveryCandidate>>::failure(active.error());
  }
  for (const auto& flush : active.value().flushes) {
    if (flush.completed) {
      continue;
    }
    const PerformanceFlushIdentity identity{
        active.value().session_id,
        flush.flush_seq,
        flush.command_id,
        flush.performance_id,
    };
    auto visible = replay_performance_flush(bundle, identity);
    if (!visible.has_value()) {
      return foundation::Result<
          std::vector<PerformanceRecoveryCandidate>>::failure(
          visible.error());
    }
    if (!visible.value().has_value()) {
      continue;
    }
    const auto target =
        visible.value()->state.performances.find(identity.performance_id);
    if (target == visible.value()->state.performances.end()) {
      return foundation::Result<
          std::vector<PerformanceRecoveryCandidate>>::failure(Error{
          ErrorCode::invalid_project,
          "committed Performance flush target is missing",
          {{"recovery_retained", true}},
      });
    }
    auto completed = journal.complete_performance_flush(
        bundle,
        identity.session_id,
        identity.flush_seq,
        visible.value()->state.revision,
        performance_fingerprint(target->second));
    if (!completed.has_value()) {
      return foundation::Result<
          std::vector<PerformanceRecoveryCandidate>>::failure(
          completed.error());
    }
  }
  active = journal.read_active_performance(bundle);
  if (!active.has_value()) {
    return foundation::Result<
        std::vector<PerformanceRecoveryCandidate>>::failure(active.error());
  }
  auto closed = journal.close_performance_transients_for_owner_loss(
      bundle, active.value().session_id);
  if (!closed.has_value()) {
    return foundation::Result<
        std::vector<PerformanceRecoveryCandidate>>::failure(closed.error());
  }
  active = journal.read_active_performance(bundle);
  if (!active.has_value()) {
    return foundation::Result<
        std::vector<PerformanceRecoveryCandidate>>::failure(active.error());
  }
  const bool has_pending =
      !active.value().pending_events.empty() ||
      std::ranges::any_of(
          active.value().flushes,
          [](const auto& flush) { return !flush.completed; });
  if (has_pending || active.value().flushes.empty()) {
    auto sealed = journal.seal_performance(
        bundle, active.value().session_id, "owner_lost");
    if (!sealed.has_value()) {
      return foundation::Result<
          std::vector<PerformanceRecoveryCandidate>>::failure(
          sealed.error());
    }
  } else {
    auto removed = journal.remove_active_performance_if_complete(
        bundle, active.value().session_id);
    if (!removed.has_value()) {
      return foundation::Result<
          std::vector<PerformanceRecoveryCandidate>>::failure(
          removed.error());
    }
  }
  return journal.list_performance_recoverable(bundle);
}

foundation::Result<SequenceCaptureDisarmResult>
ProjectStore::disarm_sequence_capture(
    const std::filesystem::path& bundle,
    const foundation::SequenceSessionId& session_id,
    domain::PadSlotId slot) {
  SequenceJournal journal{platform_};
  return journal.resolve_capture_disarm(
      bundle, session_id, slot,
      [this, &bundle](const SequenceCaptureCommit& capture)
          -> foundation::Result<std::optional<std::uint64_t>> {
        const auto conflict = [](std::string message) {
          return foundation::Result<std::optional<std::uint64_t>>::failure(
              Error{
                  ErrorCode::invalid_project,
                  std::move(message),
                  {{"reason", "armed_capture_recovery_conflict"},
                   {"remedy",
                    "inspect the durable Capture receipt and Project Truth"}},
              });
        };
        auto loaded = load_project(*platform_, bundle);
        if (!loaded.has_value()) {
          return foundation::Result<std::optional<std::uint64_t>>::failure(
              loaded.error());
        }
        const auto recovered =
            recover_uncommitted(*platform_, bundle, loaded.value());
        if (!recovered.has_value()) {
          return foundation::Result<std::optional<std::uint64_t>>::failure(
              recovered.error());
        }
        const auto receipt = loaded.value().receipts.find(capture.command_id);
        if (receipt == loaded.value().receipts.end()) {
          if (loaded.value().state.revision != capture.expected_revision ||
              loaded.value().commands.contains(capture.command_id) ||
              loaded.value().state.assets.contains(capture.asset_id) ||
              loaded.value()
                  .state.banks.at(capture.slot.bank)
                  .at(capture.slot.pad)
                  .asset_id.has_value()) {
            return conflict(
                "durable armed Capture abort does not match Project Truth");
          }
          return foundation::Result<std::optional<std::uint64_t>>::success(
              std::nullopt);
        }

        const auto recorded = loaded.value().commands.find(capture.command_id);
        const auto* sample =
            recorded != loaded.value().commands.end()
                ? std::get_if<domain::ImportAssignSample>(&recorded->second)
                : nullptr;
        const auto asset = loaded.value().state.assets.find(capture.asset_id);
        const auto expected_event = nlohmann::json{
            {"command_id", capture.command_id.value()},
            {"revision", capture.expected_revision + 1},
            {"type", "sample.imported_assigned"},
        };
        if (sample == nullptr ||
            sample->meta.command_id != capture.command_id ||
            sample->meta.expected_revision != capture.expected_revision ||
            sample->asset.id != capture.asset_id ||
            sample->asset.artifact != capture.artifact ||
            sample->slot != capture.slot ||
            receipt->second.committed_revision !=
                capture.expected_revision + 1 ||
            receipt->second.event != expected_event ||
            loaded.value().state.revision != capture.expected_revision + 1 ||
            asset == loaded.value().state.assets.end() ||
            asset->second != sample->asset ||
            loaded.value()
                    .state.banks.at(capture.slot.bank)
                    .at(capture.slot.pad)
                    .asset_id != capture.asset_id) {
          return conflict(
              "durable armed Capture receipt does not match Project Truth");
        }
        return foundation::Result<std::optional<std::uint64_t>>::success(
            receipt->second.committed_revision);
      });
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
  if (active.value().capture_commit.has_value()) {
    const auto resolved = disarm_sequence_capture(
        bundle, active.value().session_id,
        active.value().capture_commit->slot);
    if (!resolved.has_value()) {
      return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
          resolved.error());
    }
    active = journal.read_active(bundle);
    if (!active.has_value()) {
      return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
          active.error());
    }
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
  const bool has_pending =
      !active.value().pending_events.empty() ||
      std::any_of(
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
  auto performance_admitted =
      admit_performance_sample_class(platform_, bundle);
  if (!performance_admitted.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        performance_admitted.error());
  }
  auto admitted = admit_sequence_authoring(platform_, bundle);
  if (!admitted.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        admitted.error());
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
      domain::Asset{request.asset_id, described.value(), std::nullopt},
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
  auto performance_admitted =
      admit_performance_sample_class(platform_, bundle);
  if (!performance_admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        performance_admitted.error());
  }
  auto admitted = admit_sequence_authoring(platform_, bundle);
  if (!admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        admitted.error());
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
      domain::Asset{request.asset_id, artifact, std::nullopt},
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

foundation::Result<domain::AppliedCommand> ProjectStore::install_soundset(
    const std::filesystem::path& bundle,
    const SoundSetInstallRequest& request) {
  if (!domain::is_valid_uuid(request.meta.command_id.value())) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id must be a lowercase UUID",
        });
  }
  if (request.slots.empty()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "installing a Sound Set needs at least one assignment",
        });
  }
  for (const auto& slot : request.slots) {
    if (!domain::is_valid_slot(slot.slot)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "pad slot is invalid",
          });
    }
    if (!domain::is_valid_uuid(slot.asset_id.value())) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "asset id must be a lowercase UUID",
          });
    }
    if (slot.media_type.empty()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "artifact media type must not be empty",
          });
    }
    // The generic artifact safety boundary is checked before the writer lease
    // so an oversized install never contends for it.
    if (slot.bytes.size() > kMaximumArtifactBytes) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "artifact exceeds the Project import limit",
              {{"maximum_byte_length", kMaximumArtifactBytes}},
          });
    }
    const auto valid_lineage = domain::validate_asset_lineage(slot.lineage);
    if (!valid_lineage.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          valid_lineage.error());
    }
  }
  // Same ordering point as the byte imports: the cheap bundle check precedes
  // the full-artifact hashes, so a missing bundle costs no hashing at all.
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
  std::vector<domain::SoundSetInstallAssignment> assignments;
  std::vector<ArtifactStage> stages;
  assignments.reserve(request.slots.size());
  stages.reserve(request.slots.size());
  for (const auto& slot : request.slots) {
    const auto artifact = describe_bytes(slot.bytes, slot.media_type);
    assignments.push_back(
        domain::SoundSetInstallAssignment{
            slot.slot,
            domain::Asset{slot.asset_id, artifact, slot.lineage},
        });
    stages.push_back(ArtifactStage{{}, artifact, slot.bytes, true});
  }
  const PersistedCommand command = domain::InstallSoundSet{
      request.meta,
      std::move(assignments),
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
  if (loaded.value().state.contract < domain::ProjectContract::v4) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "installing a Sound Set requires lmdj.project.v4 Project Truth",
        });
  }
  const auto recovered = recover_uncommitted(
      *platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        recovered.error());
  }
  auto performance_admitted =
      admit_performance_sample_class(platform_, bundle);
  if (!performance_admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        performance_admitted.error());
  }
  auto admitted = admit_sequence_authoring(platform_, bundle);
  if (!admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        admitted.error());
  }
  auto scavenged = scavenge_sample_staging(*platform_, bundle);
  if (!scavenged.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        scavenged.error());
  }
  // A replayed command id publishes nothing: commit_loaded serves the stored
  // receipt after the identity cross-check.
  const bool replayed =
      loaded.value().receipts.contains(request.meta.command_id);
  return commit_loaded(
      platform_,
      bundle,
      std::move(loaded.value()),
      command,
      std::nullopt,
      nullptr,
      std::nullopt,
      std::nullopt,
      replayed ? std::vector<ArtifactStage>{} : std::move(stages));
}

foundation::Result<domain::AppliedCommand> ProjectStore::adopt_candidates(
    const std::filesystem::path& bundle,
    const CandidateAdoptionRequest& request) {
  if (!domain::is_valid_uuid(request.meta.command_id.value())) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id must be a lowercase UUID",
        });
  }
  if (request.slots.empty() || request.slots.size() > 64) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "adopting Candidates requires 1 to 64 assignments",
        });
  }
  for (const auto& slot : request.slots) {
    if (!domain::is_valid_slot(slot.slot)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "pad slot is invalid",
          });
    }
    if (!domain::is_valid_uuid(slot.asset_id.value())) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "asset id must be a lowercase UUID",
          });
    }
    if (slot.media_type != "audio/wav") {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "adopted artifacts must use audio/wav",
          });
    }
    // Refuse oversized materialized intervals before writer contention.
    if (slot.bytes.size() > 16777216U) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "candidate artifact exceeds the Slice byte limit",
              {{"maximum_byte_length", 16777216U}},
          });
    }
    const auto valid_lineage = domain::validate_asset_lineage(slot.lineage);
    if (!valid_lineage.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          valid_lineage.error());
    }
  }
  // Same ordering point as the byte imports: the cheap bundle check precedes
  // the full-artifact hashes, so a missing bundle costs no hashing at all.
  auto tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(tree.error());
  }
  std::vector<domain::CandidateAdoptionAssignment> assignments;
  std::vector<ArtifactStage> stages;
  assignments.reserve(request.slots.size());
  stages.reserve(request.slots.size());
  for (const auto& slot : request.slots) {
    const auto artifact = describe_bytes(slot.bytes, slot.media_type);
    assignments.push_back(
        domain::CandidateAdoptionAssignment{
            slot.slot,
            domain::Asset{slot.asset_id, artifact, slot.lineage},
        });
    stages.push_back(ArtifactStage{{}, artifact, slot.bytes, true});
  }
  const PersistedCommand command = domain::AdoptCandidates{
      request.meta,
      request.project_id,
      request.source_asset_id,
      request.source_artifact,
      std::move(assignments),
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
  const auto fresh = domain::validate_candidate_source(loaded.value().state,
      request.project_id, request.meta.expected_revision,
      request.source_asset_id, request.source_artifact);
  if (!fresh.has_value())
    return foundation::Result<domain::AppliedCommand>::failure(fresh.error());
  // Revalidate actual bytes while the Project writer excludes source mutation.
  if (!valid_candidate_source_profile(
          request.source_artifact.media_type, request.source_artifact.byte_length)) {
    return foundation::Result<domain::AppliedCommand>::failure(Error{
        ErrorCode::invalid_argument,
        "Candidate source must be audio/wav and at most 16 MiB",
    });
  }
  const auto source_bytes = describe_artifact(*platform_,
      bundle / "assets" / (request.source_artifact.sha256 + ".wav"),
      request.source_artifact.media_type);
  if (!source_bytes.has_value())
    return foundation::Result<domain::AppliedCommand>::failure(source_bytes.error());
  if (source_bytes.value() != request.source_artifact)
    return foundation::Result<domain::AppliedCommand>::failure(Error{
        ErrorCode::revision_conflict, "Candidate source bytes changed",
        {{"reason", "candidate_source_changed"}}});
  const auto recovered = recover_uncommitted(
      *platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        recovered.error());
  }
  auto performance_admitted =
      admit_performance_sample_class(platform_, bundle);
  if (!performance_admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        performance_admitted.error());
  }
  auto admitted = admit_sequence_authoring(platform_, bundle);
  if (!admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        admitted.error());
  }
  auto scavenged = scavenge_sample_staging(*platform_, bundle);
  if (!scavenged.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        scavenged.error());
  }
  // Freshness was checked before the shared full-command identity check.
  // Adoption never serves an old-revision receipt at this public boundary.
  return commit_loaded(
      platform_,
      bundle,
      std::move(loaded.value()),
      command,
      std::nullopt,
      nullptr,
      std::nullopt,
      std::nullopt,
      std::move(stages));
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
  if (request.lineage.has_value()) {
    const auto valid_lineage =
        domain::validate_asset_lineage(*request.lineage);
    if (!valid_lineage.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          valid_lineage.error());
    }
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
      domain::Asset{request.asset_id, artifact, request.lineage},
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
  if (request.lineage.has_value() &&
      loaded.value().state.contract < domain::ProjectContract::v4) {
    return foundation::Result<domain::AppliedCommand>::failure(Error{
        ErrorCode::invalid_argument,
        "Asset Lineage requires lmdj.project.v4 Project Truth",
    });
  }
  const auto recovered = recover_uncommitted(
      *platform_, bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        recovered.error());
  }
  auto performance_admitted =
      admit_performance_sample_class(platform_, bundle);
  if (!performance_admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        performance_admitted.error());
  }
  auto admitted = admit_sequence_authoring(
      platform_, bundle, &command, request.sequence_session_id);
  if (!admitted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        admitted.error());
  }
  const auto scavenged = scavenge_sample_staging(*platform_, bundle);
  if (!scavenged.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        scavenged.error());
  }

  if (admitted.value().has_value() &&
      admitted.value()->capture_commit.has_value()) {
    const auto& capture = *admitted.value()->capture_commit;
    const auto recovery_conflict = [](std::string message) {
      return foundation::Result<domain::AppliedCommand>::failure(Error{
          ErrorCode::invalid_argument,
          std::move(message),
          {{"reason", "armed_capture_recovery_conflict"},
           {"remedy",
            "retry the original captured bytes for the armed Pad"}},
      });
    };
    if (!request.sequence_session_id.has_value() ||
        request.lineage.has_value() ||
        admitted.value()->session_id != *request.sequence_session_id ||
        capture.slot != request.slot ||
        capture.expected_revision != request.meta.expected_revision ||
        capture.artifact != artifact) {
      return recovery_conflict(
          "armed Capture retry does not match the durable commit identity");
    }
    const domain::ImportAssignSample durable_command{
        domain::CommandMeta{capture.command_id, capture.expected_revision},
        domain::Asset{capture.asset_id, capture.artifact, std::nullopt},
        capture.slot,
    };
    const PersistedCommand persisted = durable_command;
    const auto receipt = loaded.value().receipts.find(capture.command_id);
    if (receipt != loaded.value().receipts.end()) {
      const auto recorded = loaded.value().commands.find(capture.command_id);
      const auto* recorded_sample =
          recorded != loaded.value().commands.end()
              ? std::get_if<domain::ImportAssignSample>(&recorded->second)
              : nullptr;
      const auto expected_event = nlohmann::json{
          {"command_id", capture.command_id.value()},
          {"revision", capture.expected_revision + 1},
          {"type", "sample.imported_assigned"},
      };
      const auto asset = loaded.value().state.assets.find(capture.asset_id);
      if (recorded_sample == nullptr ||
          recorded_sample->meta.command_id != capture.command_id ||
          recorded_sample->meta.expected_revision !=
              capture.expected_revision ||
          recorded_sample->asset.id != capture.asset_id ||
          recorded_sample->asset.artifact != capture.artifact ||
          recorded_sample->slot != capture.slot ||
          receipt->second.committed_revision != capture.expected_revision + 1 ||
          receipt->second.event != expected_event ||
          loaded.value().state.revision != capture.expected_revision + 1 ||
          asset == loaded.value().state.assets.end() ||
          asset->second != durable_command.asset ||
          loaded.value()
                  .state.banks.at(capture.slot.bank)
                  .at(capture.slot.pad)
                  .asset_id != capture.asset_id) {
        return recovery_conflict(
            "durable armed Capture receipt does not match Project Truth");
      }
    } else if (loaded.value().state.revision != capture.expected_revision ||
               loaded.value().commands.contains(capture.command_id)) {
      return recovery_conflict(
          "durable armed Capture precommit does not match Project Truth");
    }

    std::optional<ArtifactStage> stage;
    std::optional<StagedSample> resumed_staging;
    if (receipt == loaded.value().receipts.end()) {
      auto staged = stage_sample(
          *platform_, bundle, capture.command_id.value(), request.bytes);
      if (!staged.has_value()) {
        return foundation::Result<domain::AppliedCommand>::failure(
            staged.error());
      }
      resumed_staging = std::move(staged.value());
      stage = ArtifactStage{
          resumed_staging->payload, capture.artifact, {}, false};
    }
    auto reconciled = commit_loaded(
        platform_, bundle, std::move(loaded.value()), persisted,
        std::move(stage), nullptr);
    if (resumed_staging.has_value()) {
      const auto cleanup = platform_->remove_tree(resumed_staging->directory);
      if (!reconciled.has_value()) {
        return reconciled;
      }
      if (!cleanup.has_value()) {
        return foundation::Result<domain::AppliedCommand>::failure(
            cleanup.error());
      }
    }
    if (!reconciled.has_value()) {
      return reconciled;
    }
    SequenceJournal journal{platform_};
    auto completed = journal.complete_armed_capture(
        bundle, *request.sequence_session_id, capture.command_id, capture.slot,
        reconciled.value().state.revision);
    if (!completed.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          completed.error());
    }
    return reconciled;
  }

  if (loaded.value().receipts.contains(request.meta.command_id)) {
    auto replayed = commit_loaded(
        platform_,
        bundle,
        std::move(loaded.value()),
        command,
        std::nullopt,
        nullptr);
    if (!replayed.has_value()) {
      return replayed;
    }
    return replayed;
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

  if (request.sequence_session_id.has_value() && admitted.value().has_value()) {
    SequenceJournal journal{platform_};
    auto prepared = journal.prepare_armed_capture(
        bundle, *request.sequence_session_id, request.meta.command_id,
        request.asset_id, request.slot, artifact,
        request.meta.expected_revision);
    if (!prepared.has_value()) {
      const auto cleanup = cleanup_staging();
      return foundation::Result<domain::AppliedCommand>::failure(
          cleanup.has_value() ? prepared.error() : cleanup.error());
    }
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
  if (request.sequence_session_id.has_value() && admitted.value().has_value() &&
      outcome.value().state.revision > admitted.value()->expected_revision) {
    SequenceJournal journal{platform_};
    auto completed = journal.complete_armed_capture(
        bundle, *request.sequence_session_id, request.meta.command_id,
        request.slot,
        outcome.value().state.revision);
    if (!completed.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          completed.error());
    }
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

  return read_verified_artifact(*platform_, bundle, artifact);
}

foundation::Result<std::vector<std::byte>> ProjectStore::read_asset_artifact(
    const std::filesystem::path& bundle,
    const foundation::ProjectId& project_id,
    const foundation::AssetId& asset_id,
    const foundation::ArtifactRef& artifact) const {
  using BytesResult = foundation::Result<std::vector<std::byte>>;
  if (bundle.extension() != ".lmdj" ||
      !domain::is_valid_uuid(project_id.value()) ||
      !domain::is_valid_uuid(asset_id.value()) ||
      !valid_sha256(artifact.sha256) || artifact.media_type.empty() ||
      artifact.byte_length > kMaximumArtifactBytes) {
    return BytesResult::failure(
        Error{ErrorCode::invalid_argument, "Artifact owner selector is invalid"});
  }
  auto tree = platform_->validate_managed_tree(bundle);
  if (!tree.has_value()) return BytesResult::failure(tree.error());
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) return BytesResult::failure(lease.error());
  tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) return BytesResult::failure(tree.error());
  // The internal reader replays committed metadata only. Public load also
  // recovers/scavenges authoring state, which owner resolution must not do.
  const auto loaded = load_project(*platform_, bundle, false);
  if (!loaded.has_value()) return BytesResult::failure(loaded.error());
  const auto& state = loaded.value().state;
  const auto owner = state.assets.find(asset_id);
  if (state.id != project_id || owner == state.assets.end() ||
      owner->second.artifact != artifact) {
    return BytesResult::failure(
        Error{ErrorCode::not_found, "Project Asset does not own Artifact"});
  }
  return read_verified_artifact(*platform_, bundle, artifact);
}

foundation::Result<domain::ProjectState> ProjectStore::inspect_committed(
    const std::filesystem::path& bundle) const {
  using Result = foundation::Result<domain::ProjectState>;
  if (bundle.extension() != ".lmdj")
    return Result::failure(invalid_project("project bundle extension is invalid", bundle));
  auto tree = platform_->validate_managed_tree(bundle);
  if (!tree.has_value()) return Result::failure(tree.error());
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) return Result::failure(lease.error());
  tree = validate_managed_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) return Result::failure(tree.error());
  auto loaded = load_project(*platform_, bundle, false);
  if (!loaded.has_value()) return Result::failure(loaded.error());
  return Result::success(std::move(loaded.value().state));
}

}  // namespace lmdj::project_io
