#include <lmdj/facade/application.hpp>
#include <lmdj/facade/candidate_store.hpp>
#include <lmdj/facade/pattern_transport_controller_factory.hpp>

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <filesystem>
#include <limits>
#include <map>
#include <mutex>
#include <numeric>
#include <optional>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <picosha2.h>

#include <lmdj/audio/offline_renderer.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/cooker/project_cooker.hpp>
#include <lmdj/cooker/performance_replay.hpp>
#include <lmdj/cooker/sample_analysis.hpp>
#include <lmdj/cooker/wav_selection.hpp>
#include <lmdj/cooker/wav_reader.hpp>
#include <lmdj/domain/commands.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_bundle_transfer.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/workspace_cache.hpp>
#include <lmdj/provider/capability.hpp>

#include "pattern_admission_controller.hpp"
#include "testing_hooks.hpp"

namespace lmdj::facade {
namespace testing {
namespace {

std::atomic<SampleProjectionHook*> sample_projection_hook{nullptr};
std::atomic<SequenceAuthoringAdmissionHook*>
    sequence_authoring_admission_hook{nullptr};
std::atomic<ApiEntryHook*> api_entry_hook{nullptr};

}  // namespace

void set_sample_projection_hook(SampleProjectionHook* hook) noexcept {
  sample_projection_hook.store(hook, std::memory_order_release);
}

void invoke_sample_projection_hook() noexcept {
  auto* hook =
      sample_projection_hook.exchange(nullptr, std::memory_order_acq_rel);
  if (hook != nullptr && hook->invoke != nullptr) {
    hook->invoke(hook->context);
  }
}

void set_sequence_authoring_admission_hook(
    SequenceAuthoringAdmissionHook* hook) noexcept {
  sequence_authoring_admission_hook.store(hook, std::memory_order_release);
}

void invoke_sequence_authoring_admission_hook() noexcept {
  auto* hook = sequence_authoring_admission_hook.exchange(
      nullptr, std::memory_order_acq_rel);
  if (hook != nullptr && hook->invoke != nullptr) {
    hook->invoke(hook->context);
  }
}

void set_api_entry_hook(ApiEntryHook* hook) noexcept {
  api_entry_hook.store(hook, std::memory_order_release);
}

void invoke_api_entry_hook() {
  auto* hook = api_entry_hook.exchange(nullptr, std::memory_order_acq_rel);
  if (hook != nullptr && hook->invoke != nullptr) {
    hook->invoke(hook->context);
  }
}

}  // namespace testing
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint64_t kMaximumProjectBundleIndexBytes =
    4U * 1024U * 1024U;
constexpr std::size_t kMaximumProjectBundleChunkBytes = 1024U * 1024U;
constexpr std::uint32_t kMaximumProjectBundleEntries = 4096U;
constexpr std::size_t kMaximumSampleImportChunkBytes = 1024U * 1024U;
constexpr std::size_t kMaximumSampleImportSessions = 16U;
constexpr std::size_t kMaximumRememberedSampleImportTokens = 256U;
constexpr std::size_t kMaximumSampleScavengeFiles = 64U;
constexpr std::uint64_t kMaximumSampleStagingMarkerBytes = 4U * 1024U;
constexpr std::uint64_t kMinimumSampleStagingAgeSeconds = 24U * 60U * 60U;
constexpr audio::RuntimePreparationLimits kDefaultSampleLimits{
    1'048'576,
    67'108'864,
    134'217'728,
    268'435'456,
};
// The native Hosts' Sound Set limits. Unlike the Web Host, `core-cli`,
// `core-mcp` and `native-host` carry no distribution manifest, so this shared
// default is their injection site and these four numbers are their declared
// capacity, not a placeholder. They are the same four the Web Host's manifest
// declares (tools/web-runtime/runtime-identity.json): a Set that installs on
// one Host installs on every other, which cross-Host Sound Set acceptance
// requires. One manifest object, one blob bounded by the same 65 MiB a Host
// already accepts for an imported WAV, one Set's deduplicated total, and the
// whole staging area.
constexpr project_io::SoundSetStoreLimits kDefaultSoundSetStoreLimits{
    1'048'576,
    68'157'440,
    268'435'456,
    536'870'912,
};
constexpr std::string_view kSoundSetReasonAudioUnsupported =
    "soundset_audio_unsupported";
constexpr std::string_view kSampleStagingContract =
    "lmdj.sample-import-staging.v1";
constexpr std::string_view kWaveformCacheContract =
    "lmdj.sample-waveform-cache.v1";
constexpr std::string_view kWaveformCacheFold = "max-abs-mirror";

class InvalidRequest final : public std::runtime_error {
 public:
  explicit InvalidRequest(std::string message)
      : std::runtime_error(std::move(message)) {}
};

enum class OperationKind {
  command,
  query,
};

const std::map<std::string, OperationKind>& operations() {
  static const std::map<std::string, OperationKind> value{
      {"asset.import", OperationKind::command},
      {"attempt.inspect", OperationKind::query},
      {"candidate.job.run", OperationKind::command},
      {"candidate.adopt", OperationKind::command},
      {"candidate.audition", OperationKind::query},
      {"candidate.job.cancel", OperationKind::command},
      {"candidate.set.discard", OperationKind::command},
      {"candidate.job.inspect", OperationKind::query},
      {"pad.assign", OperationKind::command},
      {"pattern.slot.assign", OperationKind::command},
      {"pattern.slot.clear", OperationKind::command},
      {"pattern.slot.move", OperationKind::command},
      {"pattern.create", OperationKind::command},
      {"performance.delete", OperationKind::command},
      {"performance.discard", OperationKind::command},
      {"performance.inspect", OperationKind::query},
      {"performance.list", OperationKind::query},
      {"performance.record.begin", OperationKind::command},
      {"performance.record.event", OperationKind::command},
      {"performance.record.flush", OperationKind::command},
      {"performance.record.launch-request", OperationKind::command},
      {"performance.record.status", OperationKind::query},
      {"performance.record.stop", OperationKind::command},
      {"performance.recording.bind", OperationKind::command},
      {"performance.replay.begin", OperationKind::command},
      {"performance.replay.status", OperationKind::query},
      {"performance.replay.stop", OperationKind::command},
      {"performance.resample.commit", OperationKind::command},
      {"performance.recovery.apply", OperationKind::command},
      {"performance.recovery.discard", OperationKind::command},
      {"performance.recovery.list", OperationKind::query},
      {"performance.rename", OperationKind::command},
      {"performance.save", OperationKind::command},
      {"project.create", OperationKind::command},
      {"project.inspect", OperationKind::query},
      {"provider.list", OperationKind::query},
      {"provider.permissions.configure", OperationKind::command},
      {"provider.run", OperationKind::command},
      {"provider.select", OperationKind::command},
      {"provider.selected", OperationKind::query},
      {"render.offline", OperationKind::command},
      {"sample.import.abort", OperationKind::command},
      {"sample.import.begin", OperationKind::command},
      {"sample.import.chunk", OperationKind::command},
      {"sample.import.commit", OperationKind::command},
      {"sample.inspect", OperationKind::query},
      {"sample.quota", OperationKind::query},
      {"sample.reset_pad", OperationKind::command},
      {"sample.update_pad", OperationKind::command},
      {"sample.waveform", OperationKind::query},
      {"snapshot.cook", OperationKind::query},
      {"sequence.record.begin", OperationKind::command},
      {"sequence.record.event", OperationKind::command},
      {"sequence.record.flush", OperationKind::command},
      {"sequence.record.stop", OperationKind::command},
      {"sequence.record.switch-request", OperationKind::command},
      {"sequence.record.status", OperationKind::query},
      {"sequence.settings.update", OperationKind::command},
      {"sequence.recovery.list", OperationKind::query},
      {"sequence.recovery.apply", OperationKind::command},
      {"sequence.recovery.discard", OperationKind::command},
      {"soundset.audition", OperationKind::query},
      {"soundset.catalog.list", OperationKind::query},
      {"soundset.inspect", OperationKind::query},
      {"soundset.install", OperationKind::command},
      {"soundset.map.preview", OperationKind::query},
  };
  return value;
}

bool valid_utf8(std::string_view value) {
  std::size_t offset = 0;
  while (offset < value.size()) {
    const auto first = static_cast<unsigned char>(value[offset]);
    if (first == 0) {
      return false;
    }
    if (first <= 0x7fU) {
      ++offset;
      continue;
    }
    std::size_t length = 0;
    std::uint32_t code_point = 0;
    if (first >= 0xc2U && first <= 0xdfU) {
      length = 2;
      code_point = first & 0x1fU;
    } else if (first >= 0xe0U && first <= 0xefU) {
      length = 3;
      code_point = first & 0x0fU;
    } else if (first >= 0xf0U && first <= 0xf4U) {
      length = 4;
      code_point = first & 0x07U;
    } else {
      return false;
    }
    if (offset + length > value.size()) {
      return false;
    }
    for (std::size_t index = 1; index < length; ++index) {
      const auto byte =
          static_cast<unsigned char>(value[offset + index]);
      if ((byte & 0xc0U) != 0x80U) {
        return false;
      }
      code_point = (code_point << 6U) | (byte & 0x3fU);
    }
    if ((length == 3 && code_point < 0x800U) ||
        (length == 4 && code_point < 0x10000U) ||
        code_point > 0x10ffffU ||
        (code_point >= 0xd800U && code_point <= 0xdfffU)) {
      return false;
    }
    offset += length;
  }
  return true;
}

bool lowercase_sha256(std::string_view value) {
  return value.size() == 64U &&
         std::all_of(
             value.begin(),
             value.end(),
             [](unsigned char character) {
               return (character >= '0' && character <= '9') ||
                      (character >= 'a' && character <= 'f');
             });
}

Error invalid_bundle_import_request(std::string message) {
  return Error{ErrorCode::invalid_argument, std::move(message)};
}

bool all_strings_valid(const nlohmann::json& value) {
  if (value.is_string()) {
    return valid_utf8(value.get_ref<const std::string&>());
  }
  if (value.is_array()) {
    return std::all_of(
        value.begin(), value.end(), all_strings_valid);
  }
  if (value.is_object()) {
    for (auto iterator = value.begin(); iterator != value.end(); ++iterator) {
      if (!valid_utf8(iterator.key()) || !all_strings_valid(iterator.value())) {
        return false;
      }
    }
  }
  return true;
}

[[noreturn]] void invalid(std::string message) {
  throw InvalidRequest(std::move(message));
}

void require(bool condition, std::string message) {
  if (!condition) {
    invalid(std::move(message));
  }
}

bool exact_keys(
    const nlohmann::json& value,
    std::initializer_list<std::string_view> keys) {
  if (!value.is_object() || value.size() != keys.size()) {
    return false;
  }
  return std::all_of(
      keys.begin(), keys.end(), [&value](const auto key) {
        return value.contains(std::string(key));
      });
}

const std::string& string_field(
    const nlohmann::json& request,
    std::string_view key) {
  const auto& value = request.at(std::string(key));
  require(value.is_string(), std::string(key) + " must be a string");
  const auto& result = value.get_ref<const std::string&>();
  require(valid_utf8(result), std::string(key) + " is not valid UTF-8");
  return result;
}

std::uint64_t unsigned_field(
    const nlohmann::json& request,
    std::string_view key,
    std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max()) {
  const auto& value = request.at(std::string(key));
  std::uint64_t parsed = 0;
  if (value.is_number_unsigned()) {
    parsed = value.get<std::uint64_t>();
  } else if (value.is_number_integer()) {
    const auto signed_value = value.get<std::int64_t>();
    require(signed_value >= 0, std::string(key) + " must be nonnegative");
    parsed = static_cast<std::uint64_t>(signed_value);
  } else {
    invalid(std::string(key) + " must be an integer");
  }
  require(parsed <= maximum, std::string(key) + " is out of range");
  return parsed;
}

std::int64_t signed_field(
    const nlohmann::json& request,
    std::string_view key,
    std::int64_t minimum,
    std::int64_t maximum) {
  const auto& value = request.at(std::string(key));
  require(value.is_number_integer(), std::string(key) + " must be an integer");
  std::int64_t parsed = 0;
  if (value.is_number_unsigned()) {
    const auto unsigned_value = value.get<std::uint64_t>();
    require(
        unsigned_value <= static_cast<std::uint64_t>(maximum),
        std::string(key) + " is out of range");
    parsed = static_cast<std::int64_t>(unsigned_value);
  } else {
    parsed = value.get<std::int64_t>();
  }
  require(
      parsed >= minimum && parsed <= maximum,
      std::string(key) + " is out of range");
  return parsed;
}

std::filesystem::path absolute_path_field(
    const nlohmann::json& request,
    std::string_view key) {
  const auto path = std::filesystem::path(string_field(request, key));
  require(path.is_absolute(), std::string(key) + " must be absolute");
  require(
      path.lexically_normal() == path,
      std::string(key) + " must be normalized");
  return path;
}

std::string uuid_field(
    const nlohmann::json& request,
    std::string_view key) {
  const auto value = string_field(request, key);
  require(
      domain::is_valid_uuid(value),
      std::string(key) + " must be a lowercase UUID");
  return value;
}

bool windows_reserved_name(std::string_view value) {
  auto normalized = std::string(value);
  std::transform(
      normalized.begin(),
      normalized.end(),
      normalized.begin(),
      [](unsigned char character) {
        return static_cast<char>(std::toupper(character));
      });
  const auto dot = normalized.find('.');
  const auto base = normalized.substr(0, dot);
  if (base == "CON" || base == "PRN" || base == "AUX" ||
      base == "NUL") {
    return true;
  }
  return base.size() == 4 &&
         (base.starts_with("COM") || base.starts_with("LPT")) &&
         base.at(3) >= '1' && base.at(3) <= '9';
}

bool safe_file_id(std::string_view value) {
  if (value.empty() || value.size() > 128 || value == "." ||
      value == ".." || windows_reserved_name(value) ||
      value.back() == '.' || value.back() == ' ') {
    return false;
  }
  return std::all_of(
      value.begin(), value.end(), [](unsigned char character) {
        return std::isalnum(character) != 0 ||
               character == '.' || character == '_' ||
               character == '-';
      });
}

std::string file_id_field(
    const nlohmann::json& request,
    std::string_view key) {
  const auto value = string_field(request, key);
  require(safe_file_id(value), std::string(key) + " is unsafe");
  return value;
}

domain::PadSlotId slot_value(const nlohmann::json& encoded) {
  require(
      exact_keys(encoded, {"bank", "pad"}),
      "slot shape is invalid");
  const auto bank = unsigned_field(encoded, "bank", 3);
  const auto pad = unsigned_field(encoded, "pad", 15);
  return domain::PadSlotId{
      static_cast<std::uint8_t>(bank),
      static_cast<std::uint8_t>(pad),
  };
}

domain::TriggerMode trigger_mode_value(const nlohmann::json& encoded) {
  require(encoded.is_string(), "trigger_mode must be a string");
  const auto& value = encoded.get_ref<const std::string&>();
  require(valid_utf8(value), "trigger_mode is not valid UTF-8");
  if (value == "one_shot") {
    return domain::TriggerMode::one_shot;
  }
  if (value == "gate") {
    return domain::TriggerMode::gate;
  }
  if (value == "loop_gate") {
    return domain::TriggerMode::loop_gate;
  }
  if (value == "loop_toggle") {
    return domain::TriggerMode::loop_toggle;
  }
  invalid("trigger_mode is invalid");
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
  return "one_shot";
}

domain::PadPlayback playback_value(const nlohmann::json& encoded) {
  require(
      exact_keys(
          encoded,
          {"trim_start_frame",
           "trim_end_frame",
           "trigger_mode",
           "gain_millidb",
           "muted"}),
      "playback shape is invalid");
  const auto start = unsigned_field(encoded, "trim_start_frame");
  std::optional<std::uint64_t> end;
  if (!encoded.at("trim_end_frame").is_null()) {
    end = unsigned_field(encoded, "trim_end_frame");
  }
  require(encoded.at("muted").is_boolean(), "muted must be a boolean");
  return domain::PadPlayback{
      start,
      end,
      trigger_mode_value(encoded.at("trigger_mode")),
      static_cast<std::int32_t>(signed_field(
          encoded, "gain_millidb", -60'000, 6'000)),
      encoded.at("muted").get<bool>(),
  };
}

cooker::WaveformRequest waveform_request_value(
    const nlohmann::json& encoded) {
  require(
      exact_keys(encoded, {"start_frame", "end_frame", "bucket_count"}),
      "waveform window shape is invalid");
  return cooker::WaveformRequest{
      unsigned_field(encoded, "start_frame"),
      unsigned_field(encoded, "end_frame"),
      static_cast<std::uint32_t>(unsigned_field(encoded, "bucket_count", 512)),
  };
}

domain::Pattern pattern_value(const nlohmann::json& encoded) {
  require(
      exact_keys(encoded, {"pattern_id", "bars", "events"}),
      "pattern shape is invalid");
  const auto pattern_id = uuid_field(encoded, "pattern_id");
  const auto bars = unsigned_field(encoded, "bars", 8);
  require(
      bars == 1 || bars == 2 || bars == 4 || bars == 8,
      "pattern bars are unsupported");
  const auto& events = encoded.at("events");
  require(events.is_array(), "pattern events must be an array");
  std::vector<domain::PatternEvent> parsed;
  parsed.reserve(events.size());
  const auto loop_length = static_cast<std::uint32_t>(bars) *
                           domain::kBarTicks4x4;
  for (const auto& event : events) {
    require(
        exact_keys(
            event,
            {"slot", "onset_tick", "duration_tick", "velocity"}),
        "pattern event shape is invalid");
    const auto onset =
        unsigned_field(event, "onset_tick", loop_length - 1U);
    const auto duration =
        unsigned_field(event, "duration_tick", loop_length);
    const auto velocity = unsigned_field(event, "velocity", 127);
    require(
        velocity > 0 && duration > 0 &&
            duration <= loop_length - onset,
        "pattern event is outside tick bounds");
    parsed.push_back(
        domain::PatternEvent{
            slot_value(event.at("slot")),
            static_cast<std::uint32_t>(onset),
            static_cast<std::uint32_t>(duration),
            static_cast<std::uint8_t>(velocity),
        });
  }
  return domain::Pattern{
      foundation::PatternId{pattern_id},
      static_cast<std::uint8_t>(bars),
      std::move(parsed),
  };
}

nlohmann::json slot_json(domain::PadSlotId slot) {
  return {{"bank", slot.bank}, {"pad", slot.pad}};
}

nlohmann::json playback_json(const domain::PadPlayback& playback) {
  return {
      {"trim_start_frame", playback.trim_start_frame},
      {"trim_end_frame",
       playback.trim_end_frame.has_value()
           ? nlohmann::json(*playback.trim_end_frame)
           : nlohmann::json(nullptr)},
      {"trigger_mode", trigger_mode_name(playback.trigger_mode)},
      {"gain_millidb", playback.gain_millidb},
      {"muted", playback.muted},
  };
}

nlohmann::json pattern_event_json(const domain::PatternEvent& event) {
  return {
      {"slot", slot_json(event.slot)},
      {"onset_tick", event.onset_tick},
      {"duration_tick", event.duration_tick},
      {"velocity", event.velocity},
  };
}

nlohmann::json
artifact_json(const std::optional<foundation::ArtifactRef> &artifact) {
  if (!artifact.has_value()) {
    return nullptr;
  }
  return {
      {"sha256", artifact->sha256},
      {"media_type", artifact->media_type},
      {"byte_length", artifact->byte_length},
  };
}

nlohmann::json performance_json(const domain::Performance &performance) {
  auto events = nlohmann::json::array();
  for (const auto &event : performance.events) {
    events.push_back(domain::performance_event_json(event));
  }
  return {
      {"id", performance.id.value()},
      {"name", performance.name},
      {"created_bpm", performance.created_bpm},
      {"recording_artifact", artifact_json(performance.recording_artifact)},
      {"events", std::move(events)},
  };
}

nlohmann::json project_json(const domain::ProjectState& state) {
  auto banks = nlohmann::json::array();
  for (std::size_t bank = 0; bank < state.banks.size(); ++bank) {
    auto pads = nlohmann::json::array();
    for (const auto& pad : state.banks.at(bank)) {
      pads.push_back(
          {
              {"pad", pad.id.pad},
              {"asset_id",
               pad.asset_id.has_value()
                   ? nlohmann::json(pad.asset_id->value())
                   : nlohmann::json(nullptr)},
          });
    }
    banks.push_back({{"bank", bank}, {"pads", std::move(pads)}});
  }
  auto assets = nlohmann::json::object();
  for (const auto& [id, asset] : state.assets) {
    auto encoded_asset = nlohmann::json{{"artifact", asset.artifact}};
    if (state.contract >= domain::ProjectContract::v4) {
      encoded_asset["lineage"] =
          asset.lineage.has_value()
              ? domain::asset_lineage_json(*asset.lineage)
              : nlohmann::json(nullptr);
    }
    assets[id.value()] = std::move(encoded_asset);
  }
  auto patterns = nlohmann::json::object();
  for (const auto& [id, pattern] : state.patterns) {
    auto events = nlohmann::json::array();
    for (const auto& event : pattern.events) {
      events.push_back(pattern_event_json(event));
    }
    patterns[id.value()] = {
        {"bars", pattern.bars},
        {"events", std::move(events)},
    };
  }
  nlohmann::json encoded{
      {"contract",
       state.contract == domain::ProjectContract::v5
           ? std::string_view{"lmdj.project.v5"}
           : state.contract == domain::ProjectContract::v4
           ? "lmdj.project.v4"
           : "lmdj.project.v3"},
      {"project_id", state.id.value()},
      {"revision", state.revision},
      {"bpm", state.bpm},
      {"sequence_settings",
       {{"quantize_enabled", state.quantize_enabled},
        {"swing_percent", state.swing_percent}}},
      {"banks", std::move(banks)},
      {"assets", std::move(assets)},
      {"patterns", std::move(patterns)},
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
    auto performances = nlohmann::json::object();
    for (const auto& [id, performance] : state.performances) {
      auto value = performance_json(performance);
      value["recording_revision"] = performance.recording_revision;
      performances[id.value()] = std::move(value);
    }
    encoded["performances"] = std::move(performances);
  }
  return encoded;
}

nlohmann::json error_envelope(const Error& error) {
  const auto message =
      valid_utf8(error.message)
          ? error.message
          : std::string("module returned invalid UTF-8");
  auto details =
      all_strings_valid(error.details)
          ? error.details
          : nlohmann::json::object();
  return {
      {"ok", false},
      {"error",
       {
           {"code", foundation::error_code_name(error.code)},
           {"message", message},
           {"details", std::move(details)},
       }},
  };
}

std::string_view sample_public_message(ErrorCode code) {
  switch (code) {
    case ErrorCode::invalid_argument:
      return "Sample request is invalid";
    case ErrorCode::not_found:
      return "Sample resource was not found";
    case ErrorCode::revision_conflict:
      return "Project revision changed";
    case ErrorCode::duplicate_id:
      return "Sample identity already exists";
    case ErrorCode::unsupported_audio:
      return "Sample audio is unsupported";
    case ErrorCode::missing_asset:
      return "Sample Artifact is unavailable";
    case ErrorCode::invalid_project:
      return "Project could not be validated";
    case ErrorCode::cook_failed:
      return "Sample runtime preparation failed";
    case ErrorCode::bank_quota_exhausted:
      return "why: the selection exceeds the Sample Bank quota; remedy: "
             "shorten it, free another Pad, or target another Bank";
    case ErrorCode::project_quota_exhausted:
      return "why: the selection exceeds the Sample Project quota; remedy: "
             "shorten it or free a Pad in any Bank, then retry";
    case ErrorCode::io_error:
      return "Sample storage operation failed";
    case ErrorCode::permission_denied:
      return "Sample operation is not permitted";
    case ErrorCode::provider_not_found:
    case ErrorCode::provider_failed:
    case ErrorCode::internal_error:
      return "Sample operation failed";
  }
  return "Sample operation failed";
}

nlohmann::json sample_public_details(const Error& error) {
  auto details = nlohmann::json::object();
  if (!error.details.is_object()) {
    return details;
  }
  for (const auto* key : {"actual_revision", "expected_revision"}) {
    const auto found = error.details.find(key);
    if (found != error.details.end() &&
        (found->is_number_unsigned() ||
         (found->is_number_integer() && found->get<std::int64_t>() >= 0))) {
      details[key] = *found;
    }
  }
  const auto resource = error.details.find("resource");
  const auto observed = error.details.find("observed");
  const auto limit = error.details.find("limit");
  if (resource != error.details.end() && resource->is_string() &&
      resource->get_ref<const std::string&>().size() <= 64U &&
      observed != error.details.end() && limit != error.details.end() &&
      (observed->is_number_unsigned() || observed->is_number_integer()) &&
      (limit->is_number_unsigned() || limit->is_number_integer())) {
    details["resource"] = *resource;
    details["observed"] = *observed;
    details["limit"] = *limit;
  }
  const auto storage = error.details.find("storage_condition");
  if (storage != error.details.end() && storage->is_string()) {
    const auto& value = storage->get_ref<const std::string&>();
    if (value == project_io::kStorageConditionProjectBusy ||
        value == project_io::kStorageConditionAlreadyExists ||
        value == project_io::kStorageConditionAtomicPublishUnsupported) {
      details["storage_condition"] = value;
    }
  }
  if (error.code == ErrorCode::bank_quota_exhausted) {
    for (const auto* key : {
             "bank",
             "requested_bytes",
             "requested_frames",
             "remaining_bytes",
             "remaining_frames",
             "quota_bytes",
         }) {
      const auto found = error.details.find(key);
      if (found != error.details.end() &&
          (found->is_number_unsigned() || found->is_number_integer())) {
        details[key] = *found;
      }
    }
    const auto consumed = error.details.find("consumed");
    if (consumed != error.details.end() && consumed->is_array() &&
        all_strings_valid(*consumed)) {
      details["consumed"] = *consumed;
    }
  }
  if (error.code == ErrorCode::project_quota_exhausted) {
    for (const auto* key : {
             "requested_bytes",
             "requested_frames",
             "project_used_bytes",
             "project_remaining_bytes",
             "project_quota_bytes",
         }) {
      const auto found = error.details.find(key);
      if (found != error.details.end() &&
          (found->is_number_unsigned() || found->is_number_integer())) {
        details[key] = *found;
      }
    }
    const auto banks = error.details.find("banks");
    if (banks != error.details.end() && banks->is_array() &&
        all_strings_valid(*banks)) {
      details["banks"] = *banks;
    }
  }
  return details;
}

nlohmann::json sample_error_envelope(const Error& error) {
  return {
      {"ok", false},
      {"error",
       {{"code", foundation::error_code_name(error.code)},
        {"message", sample_public_message(error.code)},
        {"details", sample_public_details(error)}}},
  };
}

bool sample_operation_request(const nlohmann::json& request) {
  return request.is_object() && request.contains("operation") &&
         request.at("operation").is_string() &&
         request.at("operation").get_ref<const std::string&>().starts_with(
             "sample.");
}

nlohmann::json success_envelope(
    nlohmann::json result,
    std::optional<std::uint64_t> revision) {
  return {
      {"ok", true},
      {"result", std::move(result)},
      {"project_revision",
       revision.has_value()
           ? nlohmann::json(*revision)
           : nlohmann::json(nullptr)},
  };
}

nlohmann::json internal_error() {
  return error_envelope(
      Error{
          ErrorCode::internal_error,
          "unexpected application failure",
      });
}

nlohmann::json model_identity_json(
    const std::optional<provider::ModelIdentity>& identity) {
  if (!identity.has_value()) {
    return nullptr;
  }
  return {
      {"id", identity->id},
      {"version", identity->version},
      {"artifact_sha256", identity->artifact_sha256},
  };
}

nlohmann::json provider_descriptor_json(
    const provider::ProviderDescriptor& descriptor) {
  auto capabilities = nlohmann::json::array();
  for (const auto& capability : descriptor.capabilities) {
    capabilities.push_back(provider::capability_contract_json(capability));
  }
  return {
      {"id", descriptor.id},
      {"version", descriptor.version},
      {"artifact_sha256", descriptor.artifact_sha256},
      {"model_identity", model_identity_json(descriptor.model_identity)},
      {"capabilities", std::move(capabilities)},
  };
}

nlohmann::json terminal_attempt_json(
    const provider::TerminalAttempt& attempt) {
  auto candidate_ids = nlohmann::json::array();
  for (const auto& id : attempt.candidate_ids) {
    candidate_ids.push_back(id.value());
  }
  auto artifacts = nlohmann::json::array();
  for (const auto& artifact : attempt.artifacts) {
    artifacts.push_back(artifact);
  }
  auto inputs = nlohmann::json::array();
  for (const auto& input : attempt.request.inputs) {
    inputs.push_back(input);
  }
  auto minted_outputs = nlohmann::json::array();
  for (const auto& output : attempt.minted_outputs) {
    minted_outputs.push_back(output);
  }
  auto candidate_outputs = nlohmann::json::array();
  for (const auto& output : attempt.candidate_outputs) {
    candidate_outputs.push_back(output);
  }
  auto error = nlohmann::json(nullptr);
  if (attempt.error.has_value()) {
    error = {
        {"code", foundation::error_code_name(attempt.error->code)},
        {"message", attempt.error->message},
        {"details", attempt.error->details},
    };
  }
  return {
      {"attempt_id", attempt.attempt_id.value()},
      {"status",
       attempt.status == provider::AttemptStatus::succeeded
           ? "succeeded"
           : "failed"},
      {"started_at", attempt.started_at},
      {"ended_at", attempt.ended_at},
      {"provider",
       {
           {"id", attempt.provider.id},
           {"version", attempt.provider.version},
           {"artifact_sha256", attempt.provider.artifact_sha256},
           {"model_identity",
            model_identity_json(attempt.provider.model_identity)},
       }},
      {"capability",
       {
           {"id", attempt.capability.id},
           {"contract", attempt.capability.contract},
           {"version", attempt.capability.version},
       }},
      {"request",
       {
           {"capability", attempt.request.capability},
           {"inputs", std::move(inputs)},
           {"parameters_sha256", attempt.request.parameters_sha256},
           {"data_classification", attempt.request.data_classification},
           {"platform", attempt.request.platform},
           {"region", attempt.request.region},
           {"required_permissions", attempt.request.required_permissions},
       }},
      {"candidate_ids", std::move(candidate_ids)},
      {"candidate_outputs", std::move(candidate_outputs)},
      {"minted_outputs", std::move(minted_outputs)},
      {"artifacts", std::move(artifacts)},
      {"error", std::move(error)},
  };
}

bool path_is_inside_bundle(const std::filesystem::path& path) {
  for (const auto& component : path) {
    if (component.extension() == ".lmdj") {
      return true;
    }
  }
  return false;
}

class OwnedDescriptor {
 public:
  explicit OwnedDescriptor(int descriptor) : descriptor_(descriptor) {}
  OwnedDescriptor(const OwnedDescriptor&) = delete;
  OwnedDescriptor& operator=(const OwnedDescriptor&) = delete;
  OwnedDescriptor(OwnedDescriptor&& other) noexcept
      : descriptor_(std::exchange(other.descriptor_, -1)) {}
  OwnedDescriptor& operator=(OwnedDescriptor&& other) noexcept {
    if (this != &other) {
      close();
      descriptor_ = std::exchange(other.descriptor_, -1);
    }
    return *this;
  }
  ~OwnedDescriptor() { close(); }

  int get() const noexcept { return descriptor_; }

 private:
  void close() noexcept {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }

  int descriptor_;
};

struct RenderDestination {
  OwnedDescriptor parent;
  std::string filename;
};

RenderDestination open_render_destination(
    const std::filesystem::path& output) {
  auto parent = output.parent_path();
#if defined(__APPLE__)
  const auto relative = parent.relative_path();
  if (parent.is_absolute() && !relative.empty()) {
    const auto first = *relative.begin();
    if (first == "var" || first == "tmp") {
      parent = std::filesystem::path("/private") / relative;
    }
  }
#endif
  const int root = ::open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  require(root >= 0, "render output root could not be opened");
  OwnedDescriptor current(root);
  for (const auto& component : parent.relative_path()) {
    if (component.empty() || component == ".") {
      continue;
    }
    const int next = ::openat(
        current.get(),
        component.c_str(),
        O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    require(
        next >= 0, "render output parent contains a symbolic, missing, or "
                       "invalid directory");
    current = OwnedDescriptor(next);
  }

  const auto filename = output.filename().string();
  require(!filename.empty(), "render output filename must not be empty");
  struct stat output_metadata {};
  if (::fstatat(
          current.get(),
          filename.c_str(),
          &output_metadata,
          AT_SYMLINK_NOFOLLOW) == 0) {
    invalid("render output already exists");
  }
  require(
      errno == ENOENT,
      "render output cannot be safely inspected through its parent");
  return RenderDestination{
      std::move(current),
      filename,
  };
}

std::string descriptor_path(int descriptor) {
#if defined(__linux__)
  return "/proc/self/fd/" + std::to_string(descriptor);
#else
  return "/dev/fd/" + std::to_string(descriptor);
#endif
}

class TempRender {
 public:
  TempRender(
      int parent_descriptor,
      int descriptor,
      std::string name)
      : parent_descriptor_(parent_descriptor),
        descriptor_(descriptor),
        name_(std::move(name)) {}
  TempRender(const TempRender&) = delete;
  TempRender& operator=(const TempRender&) = delete;
  TempRender(TempRender&& other) noexcept
      : parent_descriptor_(other.parent_descriptor_),
        descriptor_(std::move(other.descriptor_)),
        name_(std::move(other.name_)),
        linked_(other.linked_) {
    other.linked_ = true;
  }
  ~TempRender() {
    if (!linked_) {
      ::unlinkat(parent_descriptor_, name_.c_str(), 0);
    }
  }

  int descriptor() const noexcept { return descriptor_.get(); }
  std::filesystem::path path() const {
    return descriptor_path(descriptor_.get());
  }
  const std::string& name() const noexcept { return name_; }
  void published() noexcept {
    if (::unlinkat(parent_descriptor_, name_.c_str(), 0) == 0 ||
        errno == ENOENT) {
      linked_ = true;
    }
  }

 private:
  int parent_descriptor_;
  OwnedDescriptor descriptor_;
  std::string name_;
  bool linked_{false};
};

foundation::Result<TempRender> create_temp_render(
    int parent_descriptor) {
  std::random_device random;
  for (std::uint32_t attempt = 0; attempt < 128; ++attempt) {
    const auto name =
        std::string(".lmdj-render-") +
        std::to_string(static_cast<unsigned long long>(::getpid())) +
        "-" +
        std::to_string(
            static_cast<unsigned long long>(random())) +
        "-" + std::to_string(attempt) + ".tmp";
    const int descriptor = ::openat(
        parent_descriptor,
        name.c_str(),
        O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
        0600);
    if (descriptor >= 0) {
      return foundation::Result<TempRender>::success(
          TempRender{parent_descriptor, descriptor, name});
    }
    if (errno != EEXIST && errno != EINTR) {
      return foundation::Result<TempRender>::failure(
          Error{
              ErrorCode::io_error,
              "exclusive render temporary file could not be created",
              {{"system_error", std::strerror(errno)}},
          });
    }
  }
  return foundation::Result<TempRender>::failure(
      Error{
          ErrorCode::io_error,
          "exclusive render temporary name attempts were exhausted",
      });
}

class ScratchRender {
 public:
  explicit ScratchRender(std::filesystem::path directory)
      : directory_(std::move(directory)),
        path_(directory_ / "render.wav") {}
  ScratchRender(const ScratchRender&) = delete;
  ScratchRender& operator=(const ScratchRender&) = delete;
  ScratchRender(ScratchRender&& other) noexcept
      : directory_(std::move(other.directory_)),
        path_(std::move(other.path_)) {
    other.path_.clear();
    other.directory_.clear();
  }
  ~ScratchRender() {
    if (!path_.empty()) {
      ::unlink(path_.c_str());
    }
    if (!directory_.empty()) {
      ::rmdir(directory_.c_str());
    }
  }

  const std::filesystem::path& path() const noexcept { return path_; }

 private:
  std::filesystem::path directory_;
  std::filesystem::path path_;
};

foundation::Result<ScratchRender> create_scratch_render(
    const std::filesystem::path& workspace_root) {
  auto scratch_template =
      (workspace_root / ".core-render-XXXXXX").string();
  std::vector<char> writable(
      scratch_template.begin(), scratch_template.end());
  writable.push_back('\0');
  const char* directory = ::mkdtemp(writable.data());
  if (directory == nullptr) {
    return foundation::Result<ScratchRender>::failure(
        Error{
            ErrorCode::io_error,
            "private render scratch directory could not be created",
            {{"system_error", std::strerror(errno)}},
        });
  }
  ScratchRender scratch{std::filesystem::path(directory)};
  const int descriptor = ::open(
      scratch.path().c_str(),
      O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
      0600);
  if (descriptor < 0) {
    return foundation::Result<ScratchRender>::failure(
        Error{
            ErrorCode::io_error,
            "private render scratch file could not be created",
            {{"system_error", std::strerror(errno)}},
        });
  }
  ::close(descriptor);
  return foundation::Result<ScratchRender>::success(
      std::move(scratch));
}

struct VerifiedScratch {
  foundation::ArtifactRef artifact;
  std::vector<std::byte> bytes;
};

foundation::Result<VerifiedScratch> read_verified_scratch(
    const ScratchRender& scratch,
    const foundation::ArtifactRef& expected) {
  const int value =
      ::open(scratch.path().c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (value < 0) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch file could not be reopened safely",
            {{"system_error", std::strerror(errno)}},
        });
  }
  OwnedDescriptor descriptor(value);
  struct stat before {};
  if (::fstat(descriptor.get(), &before) != 0 ||
      !S_ISREG(before.st_mode) || before.st_size < 0 ||
      static_cast<std::uint64_t>(before.st_size) != expected.byte_length ||
      static_cast<std::uint64_t>(before.st_size) >
          std::numeric_limits<std::size_t>::max()) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch metadata does not match its Artifact",
        });
  }
  const auto stable_artifact = foundation::describe_artifact(
      descriptor_path(descriptor.get()), expected.media_type);
  if (!stable_artifact.has_value()) {
    return foundation::Result<VerifiedScratch>::failure(
        stable_artifact.error());
  }
  if (stable_artifact.value() != expected) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch bytes do not match its Artifact",
        });
  }
  if (::lseek(descriptor.get(), 0, SEEK_SET) < 0) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch descriptor could not be rewound",
        });
  }
  std::vector<std::byte> bytes(
      static_cast<std::size_t>(before.st_size));
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto count = ::read(
        descriptor.get(),
        bytes.data() + offset,
        bytes.size() - offset);
    if (count < 0 && errno == EINTR) {
      continue;
    }
    if (count <= 0) {
      return foundation::Result<VerifiedScratch>::failure(
          Error{
              ErrorCode::io_error,
              "render scratch could not be read completely",
          });
    }
    offset += static_cast<std::size_t>(count);
  }
  struct stat after {};
  if (::fstat(descriptor.get(), &after) != 0 ||
      !S_ISREG(after.st_mode) || after.st_dev != before.st_dev ||
      after.st_ino != before.st_ino || after.st_size != before.st_size) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch changed while it was being read",
        });
  }
  return foundation::Result<VerifiedScratch>::success(
      VerifiedScratch{
          stable_artifact.value(),
          std::move(bytes),
      });
}

foundation::Result<void> write_verified_staging(
    TempRender& staging,
    const VerifiedScratch& scratch) {
  std::size_t offset = 0;
  while (offset < scratch.bytes.size()) {
    const auto count = ::write(
        staging.descriptor(),
        scratch.bytes.data() + offset,
        scratch.bytes.size() - offset);
    if (count < 0 && errno == EINTR) {
      continue;
    }
    if (count <= 0) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::io_error,
              "render staging file could not be written completely",
          });
    }
    offset += static_cast<std::size_t>(count);
  }
  if (::fsync(staging.descriptor()) != 0 ||
      ::lseek(staging.descriptor(), 0, SEEK_SET) < 0) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::io_error,
            "render staging file could not be durably verified",
            {{"system_error", std::strerror(errno)}},
        });
  }
  const auto staged = foundation::describe_artifact(
      staging.path(), scratch.artifact.media_type);
  if (!staged.has_value()) {
    return foundation::Result<void>::failure(staged.error());
  }
  if (staged.value() != scratch.artifact) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::io_error,
            "render staging bytes do not match the verified scratch Artifact",
        });
  }
  return foundation::Result<void>::success();
}

provider::TimestampSource default_timestamp_source() {
  return [] {
    const auto ticks =
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count();
    return std::string("unix-ms:") + std::to_string(ticks);
  };
}

Error runtime_preparation_limit_error(
    std::string resource,
    std::uint64_t observed,
    std::uint64_t limit) {
  return Error{
      ErrorCode::cook_failed,
      "runtime preparation limit exceeded",
      {
          {"resource", std::move(resource)},
          {"observed", observed},
          {"limit", limit},
      },
  };
}

Error runtime_bank_quota_error(
    domain::PadSlotId slot,
    std::uint64_t requested_bytes,
    std::uint64_t requested_frames,
    std::uint64_t remaining_bytes,
    std::uint64_t quota_bytes,
    const std::vector<nlohmann::json>& consumed) {
  return Error{
      ErrorCode::bank_quota_exhausted,
      "Bank prepared-PCM quota exhausted; why: the committed selection "
      "does not fit in this Bank; remedy: shorten the selection, free a Pad "
      "in this Bank, or target another Bank, then retry",
      {
          {"bank", slot.bank},
          {"requested_bytes", requested_bytes},
          {"requested_frames", requested_frames},
          {"remaining_bytes", remaining_bytes},
          {"remaining_frames", remaining_bytes / sizeof(float)},
          {"quota_bytes", quota_bytes},
          {"consumed", consumed},
      },
  };
}

Error runtime_project_quota_error(
    std::uint64_t requested_bytes,
    std::uint64_t requested_frames,
    std::uint64_t project_used_bytes,
    std::uint64_t project_remaining_bytes,
    std::uint64_t project_quota_bytes,
    const std::array<std::uint64_t, 4>& bank_bytes) {
  auto banks = nlohmann::json::array();
  for (std::uint8_t bank = 0; bank < bank_bytes.size(); ++bank) {
    banks.push_back({
        {"bank", bank},
        {"prepared_bytes", bank_bytes.at(bank)},
    });
  }
  return Error{
      ErrorCode::project_quota_exhausted,
      "Project prepared-PCM quota exhausted; why: the committed selection "
      "does not fit in the current generation; remedy: shorten or remove "
      "samples in the Project, then retry",
      {
          {"requested_bytes", requested_bytes},
          {"requested_frames", requested_frames},
          {"project_used_bytes", project_used_bytes},
          {"project_remaining_bytes", project_remaining_bytes},
          {"project_quota_bytes", project_quota_bytes},
          {"banks", std::move(banks)},
      },
  };
}

// Why one Catalog entry did not become available, in public vocabulary only:
// the `lmdj.error.v1` code and, when the failing module attached one, the
// locked `details.reason` token. A Catalog that cannot be reached and a
// Catalog that answers with something that is not
// `lmdj.soundset-catalog.v1` are the same fact to every caller — no usable
// index — and neither is fatal.
nlohmann::json soundset_refusal_json(
    const project_io::SoundSetCatalogEntry& entry,
    const Error& error) {
  nlohmann::json refusal{
      {"set_id", entry.set_id},
      {"version", entry.version},
      {"manifest_sha256", entry.manifest_sha256},
      {"code", foundation::error_code_name(error.code)},
  };
  const auto reason = error.details.is_object()
                          ? error.details.value("reason", std::string{})
                          : std::string{};
  refusal["reason"] =
      reason.empty() ? nlohmann::json(nullptr) : nlohmann::json(reason);
  return refusal;
}

// A published Set that cannot produce a declared Artifact's bytes is a
// corrupted Set Store copy, whether the blob is absent or its bytes changed.
// The locked table has exactly one reason for that: soundset_content_mismatch.
Error soundset_artifact_error(const Error& error) {
  if (error.details.is_object() &&
      error.details.value("reason", std::string{}) ==
          std::string(project_io::kSoundSetReasonContentMismatch)) {
    return error;
  }
  return Error{
      ErrorCode::io_error,
      "Sound Set Artifact bytes do not match the published manifest",
      {{"reason", project_io::kSoundSetReasonContentMismatch}},
  };
}

// S11-D3: Sound Set audio is ordinary S8-D6 audio, so the project-cooker WAV
// reader decides it. The reader raises UNSUPPORTED_AUDIO with no reason token,
// and the Sound Set path is where that reason exists; attaching it here keeps
// the shared reader free of a Sound Set concept.
Error soundset_audio_error(const Error& error, std::uint8_t slot_index) {
  if (error.code != ErrorCode::unsupported_audio) {
    return error;
  }
  return Error{
      ErrorCode::unsupported_audio,
      error.message,
      {
          {"reason", kSoundSetReasonAudioUnsupported},
          {"slot_index", slot_index},
      },
  };
}

bool semver_string(std::string_view value) {
  std::size_t offset = 0;
  for (int component = 0; component < 3; ++component) {
    if (component > 0) {
      if (offset >= value.size() || value[offset] != '.') {
        return false;
      }
      ++offset;
    }
    const auto begin = offset;
    while (offset < value.size() && value[offset] >= '0' &&
           value[offset] <= '9') {
      ++offset;
    }
    const auto digits = offset - begin;
    if (digits == 0 || (digits > 1 && value[begin] == '0')) {
      return false;
    }
  }
  return offset == value.size();
}

// The C++ mirror of `lmdj.soundset-catalog.v1`, written the way
// `packages/authoring-domain/src/project.cpp` mirrors the Project Schema:
// exact keys, checked types, no JSON Schema validator in Core.
std::optional<std::vector<project_io::SoundSetCatalogEntry>>
parse_soundset_catalog_index(std::string_view bytes) {
  if (!valid_utf8(bytes)) {
    return std::nullopt;
  }
  const auto parsed = foundation::parse_bounded_json(bytes);
  if (!parsed.has_value() || !parsed->is_object() ||
      !exact_keys(*parsed, {"contract", "entries"}) ||
      !parsed->at("contract").is_string() ||
      parsed->at("contract").get<std::string>() !=
          "lmdj.soundset-catalog.v1" ||
      !parsed->at("entries").is_array()) {
    return std::nullopt;
  }
  std::vector<project_io::SoundSetCatalogEntry> entries;
  std::set<std::string> seen_entries;
  for (const auto& item : parsed->at("entries")) {
    if (!item.is_object() ||
        !seen_entries.insert(foundation::canonical_json(item)).second) {
      return std::nullopt;
    }
    for (const auto& required : {
             "set_id",
             "version",
             "manifest_sha256",
             "total_bytes",
             "name",
             "publisher",
             "roles_summary",
             "license_summary",
         }) {
      if (!item.contains(required)) {
        return std::nullopt;
      }
    }
    for (auto field = item.begin(); field != item.end(); ++field) {
      const auto& key = field.key();
      if (key != "set_id" && key != "version" && key != "manifest_sha256" &&
          key != "total_bytes" && key != "name" && key != "publisher" &&
          key != "roles_summary" && key != "license_summary" &&
          key != "bpm" && key != "key") {
        return std::nullopt;
      }
    }
    const auto& summary = item.at("license_summary");
    if (!item.at("set_id").is_string() ||
        !domain::is_valid_uuid(item.at("set_id").get_ref<const std::string&>()) ||
        !item.at("version").is_string() ||
        !semver_string(item.at("version").get_ref<const std::string&>()) ||
        !item.at("manifest_sha256").is_string() ||
        !lowercase_sha256(
            item.at("manifest_sha256").get_ref<const std::string&>()) ||
        !item.at("total_bytes").is_number_unsigned() ||
        item.at("total_bytes").get<std::uint64_t>() == 0U ||
        !item.at("name").is_string() ||
        item.at("name").get_ref<const std::string&>().empty() ||
        !item.at("publisher").is_string() ||
        item.at("publisher").get_ref<const std::string&>().empty() ||
        !item.at("roles_summary").is_array() ||
        !exact_keys(summary, {"spdx_id", "rights_holder"}) ||
        !summary.at("spdx_id").is_string() ||
        summary.at("spdx_id").get_ref<const std::string&>().empty() ||
        !summary.at("rights_holder").is_string() ||
        summary.at("rights_holder").get_ref<const std::string&>().empty()) {
      return std::nullopt;
    }
    // `roles_summary` is a closed enum with uniqueItems, and the two optional
    // keys are typed and ranged exactly as the Contract declares them.
    std::set<std::string> roles;
    for (const auto& role : item.at("roles_summary")) {
      if (!role.is_string() ||
          std::ranges::find(
              foundation::kSoundSetRoles,
              role.get_ref<const std::string&>()) ==
              foundation::kSoundSetRoles.end() ||
          !roles.insert(role.get<std::string>()).second) {
        return std::nullopt;
      }
    }
    if (item.contains("bpm")) {
      const auto& bpm = item.at("bpm");
      if (!bpm.is_number_integer() || bpm.is_number_float()) {
        return std::nullopt;
      }
      const auto value = bpm.is_number_unsigned()
                             ? static_cast<std::int64_t>(
                                   std::min<std::uint64_t>(
                                       bpm.get<std::uint64_t>(),
                                       static_cast<std::uint64_t>(
                                           std::numeric_limits<
                                               std::int64_t>::max())))
                             : bpm.get<std::int64_t>();
      if (value < 40 || value > 240) {
        return std::nullopt;
      }
    }
    if (item.contains("key") &&
        (!item.at("key").is_string() ||
         item.at("key").get_ref<const std::string&>().empty())) {
      return std::nullopt;
    }
    entries.push_back(
        project_io::SoundSetCatalogEntry{
            item.at("set_id").get<std::string>(),
            item.at("version").get<std::string>(),
            item.at("manifest_sha256").get<std::string>(),
            item.at("total_bytes").get<std::uint64_t>(),
            foundation::CatalogLicenseSummary{
                summary.at("spdx_id").get<std::string>(),
                summary.at("rights_holder").get<std::string>(),
            },
        });
  }
  return entries;
}

// The Set Store names each published Set by its canonical manifest digest,
// and `StoredSoundSet` carries the canonical bytes rather than the name, so a
// listing recomputes it over exactly the bytes S11-D1 defines the identity as.
std::string canonical_manifest_digest(std::string_view canonical_bytes) {
  picosha2::hash256_one_by_one hasher;
  const auto* begin =
      reinterpret_cast<const unsigned char*>(canonical_bytes.data());
  hasher.process(begin, begin + canonical_bytes.size());
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

// An install's Asset identities have to be a function of the request, not of
// a random source. Task 3's commit path serves a replayed `command_id` only
// when the whole persisted command matches byte for byte, so a Host retrying
// after a lost response must present the same Asset ids it presented the first
// time. Deriving them from the command id, the Set's manifest digest and the
// target Pad makes the retry identical by construction, and makes two Pads of
// one install two distinct Assets even when they share an Artifact.
std::string derived_asset_id(
    std::string_view command_id,
    std::string_view manifest_sha256,
    std::uint8_t bank,
    std::uint8_t pad) {
  const auto seed = std::string("lmdj.soundset.install.asset\n") +
                    std::string(command_id) + "\n" +
                    std::string(manifest_sha256) + "\n" +
                    std::to_string(static_cast<unsigned>(bank)) + "\n" +
                    std::to_string(static_cast<unsigned>(pad));
  const auto digest = canonical_manifest_digest(seed);
  auto value = digest.substr(0, 32);
  // A lowercase canonical UUID with the version-4 nibble and the RFC variant
  // bits, so `domain::is_valid_uuid` accepts it like any other Asset id.
  value.at(12) = '4';
  constexpr std::string_view variants = "89ab";
  value.at(16) = variants.at(
      static_cast<std::size_t>(
          std::string_view("0123456789abcdef").find(value.at(16))) %
      variants.size());
  return value.substr(0, 8) + "-" + value.substr(8, 4) + "-" +
         value.substr(12, 4) + "-" + value.substr(16, 4) + "-" +
         value.substr(20, 12);
}

std::string candidate_asset_id(
    std::string_view command_id,
    std::string_view candidate_id,
    std::uint8_t bank,
    std::uint8_t pad) {
  const auto seed = std::string("lmdj.candidate.adopt.asset\n") +
                    std::string(command_id) + "\n" +
                    std::string(candidate_id) + "\n" +
                    std::to_string(static_cast<unsigned>(bank)) + "\n" +
                    std::to_string(static_cast<unsigned>(pad));
  const auto digest = canonical_manifest_digest(seed);
  auto value = digest.substr(0, 32);
  // A lowercase canonical UUID with the version-4 nibble and the RFC variant
  // bits, so `domain::is_valid_uuid` accepts it like any other Asset id.
  value.at(12) = '4';
  constexpr std::string_view variants = "89ab";
  value.at(16) = variants.at(
      static_cast<std::size_t>(
          std::string_view("0123456789abcdef").find(value.at(16))) %
      variants.size());
  return value.substr(0, 8) + "-" + value.substr(8, 4) + "-" +
         value.substr(12, 4) + "-" + value.substr(16, 4) + "-" +
         value.substr(20, 12);
}

nlohmann::json soundset_artifact_json(const foundation::ArtifactRef& artifact) {
  return {
      {"sha256", artifact.sha256},
      {"media_type", artifact.media_type},
      {"byte_length", artifact.byte_length},
  };
}

nlohmann::json soundset_license_json(const foundation::SoundSetLicense& license) {
  return {
      {"spdx_id", license.spdx_id},
      {"rights_holder", license.rights_holder},
      {"copyright", license.copyright},
      {"attribution", license.attribution},
  };
}

// Identity plus everything a Host needs to list a Set. The occupied slot roles
// are read from the verified manifest, never from the Catalog summary.
nlohmann::json soundset_summary_json(
    const project_io::StoredSoundSet& stored,
    std::string_view manifest_sha256) {
  const auto& manifest = stored.manifest;
  auto slots = nlohmann::json::array();
  for (const auto& slot : manifest.slots) {
    if (!slot.occupied.has_value()) {
      continue;
    }
    slots.push_back({
        {"slot", slot.index},
        {"role", slot.occupied->role},
        {"name", slot.occupied->name},
    });
  }
  nlohmann::json summary{
      {"set_id", manifest.set_id},
      {"version", manifest.version},
      {"manifest_sha256", std::string{manifest_sha256}},
      {"name", manifest.name},
      {"publisher", manifest.publisher},
      {"total_bytes", stored.total_bytes},
      {"license", soundset_license_json(manifest.license)},
      {"occupied_slots", std::move(slots)},
      {"has_demo", manifest.demo.has_value()},
  };
  summary["description"] = manifest.description.has_value()
                               ? nlohmann::json(*manifest.description)
                               : nlohmann::json(nullptr);
  summary["bpm"] = manifest.bpm.has_value() ? nlohmann::json(*manifest.bpm)
                                            : nlohmann::json(nullptr);
  summary["key"] = manifest.key.has_value() ? nlohmann::json(*manifest.key)
                                            : nlohmann::json(nullptr);
  return summary;
}

bool valid_host_project_path(const std::filesystem::path& path) {
  const auto encoded = path.generic_string();
  return valid_utf8(encoded) && path.is_absolute() &&
         path.lexically_normal() == path;
}

Error invalid_sample_request(std::string message) {
  return Error{ErrorCode::invalid_argument, std::move(message)};
}

Error unavailable_sample() {
  return Error{
      ErrorCode::missing_asset,
      "Sample Artifact is unavailable",
  };
}

Error sample_project_load_error(const Error& error) {
  if (error.code == ErrorCode::invalid_project &&
      error.message == "project asset blob is missing or corrupt") {
    return unavailable_sample();
  }
  if (error.code == ErrorCode::invalid_project &&
      error.message == "project managed directory is missing or invalid") {
    return Error{
        ErrorCode::io_error,
        "Sample Project is unavailable",
    };
  }
  return error;
}

Error sample_artifact_read_error(const Error& error) {
  if (error.code == ErrorCode::not_found ||
      error.code == ErrorCode::cook_failed) {
    return unavailable_sample();
  }
  auto details = nlohmann::json::object();
  if (error.details.is_object()) {
    const auto storage = error.details.find("storage_condition");
    if (storage != error.details.end() && storage->is_string()) {
      const auto& value = storage->get_ref<const std::string&>();
      if (value == project_io::kStorageConditionProjectBusy ||
          value == project_io::kStorageConditionAlreadyExists ||
          value == project_io::kStorageConditionAtomicPublishUnsupported) {
        details["storage_condition"] = value;
      }
    }
  }
  return Error{
      error.code,
      "Sample Artifact could not be read",
      std::move(details),
  };
}

Error sample_storage_error(const Error& error, std::string message) {
  auto details = nlohmann::json::object();
  if (error.details.is_object() &&
      error.details.contains("storage_condition") &&
      error.details.at("storage_condition").is_string()) {
    details["storage_condition"] =
        error.details.at("storage_condition");
  }
  return Error{ErrorCode::io_error, std::move(message), std::move(details)};
}

std::uint64_t ceiling_divide(
    std::uint64_t numerator,
    std::uint64_t denominator) {
  return numerator / denominator +
         (numerator % denominator == 0 ? 0U : 1U);
}

std::uint64_t canonical_waveform_frames_per_bucket(
    std::uint64_t source_frames) {
  const auto bucket_count =
      std::min<std::uint64_t>(source_frames, 512U);
  return ceiling_divide(source_frames, bucket_count);
}

std::string waveform_cache_key(
    const foundation::ArtifactRef& artifact,
    std::uint64_t frames_per_bucket) {
  return artifact.sha256 + "/" +
         std::to_string(cooker::kWaveformAlgorithmVersion) + "/" +
         std::string{kWaveformCacheFold} + "/" +
         std::to_string(frames_per_bucket);
}

nlohmann::json wav_metadata_json(const cooker::WavMetadata& metadata) {
  return {
      {"sample_rate", metadata.sample_rate},
      {"channels", metadata.channels},
      {"source_frames", metadata.source_frames},
  };
}

nlohmann::json peak_bucket_json(const cooker::PeakBucket& bucket) {
  return {
      {"start_frame", bucket.start_frame},
      {"end_frame", bucket.end_frame},
      {"peak_magnitude", bucket.peak_magnitude},
  };
}

std::vector<std::byte> encode_waveform_cache(
    const cooker::WaveformEnvelope& envelope,
    std::uint64_t frames_per_bucket) {
  auto buckets = nlohmann::json::array();
  for (const auto& bucket : envelope.buckets) {
    buckets.push_back(peak_bucket_json(bucket));
  }
  const auto encoded = nlohmann::json{
      {"contract", kWaveformCacheContract},
      {"metadata", wav_metadata_json(envelope.metadata)},
      {"algorithm_version", envelope.algorithm_version},
      {"fold", kWaveformCacheFold},
      {"frames_per_bucket", frames_per_bucket},
      {"bucket_count", envelope.buckets.size()},
      {"buckets", std::move(buckets)},
  }.dump();
  const auto* begin = reinterpret_cast<const std::byte*>(encoded.data());
  return {begin, begin + encoded.size()};
}

std::optional<std::uint64_t> cache_unsigned(
    const nlohmann::json& value,
    std::string_view key,
    std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max()) {
  const auto found = value.find(std::string{key});
  if (found == value.end()) {
    return std::nullopt;
  }
  std::uint64_t parsed = 0;
  if (found->is_number_unsigned()) {
    parsed = found->get<std::uint64_t>();
  } else if (found->is_number_integer()) {
    const auto signed_value = found->get<std::int64_t>();
    if (signed_value < 0) {
      return std::nullopt;
    }
    parsed = static_cast<std::uint64_t>(signed_value);
  } else {
    return std::nullopt;
  }
  return parsed <= maximum ? std::optional<std::uint64_t>{parsed}
                           : std::nullopt;
}

std::optional<cooker::WaveformEnvelope> decode_waveform_cache(
    std::span<const std::byte> bytes,
    const cooker::WavMetadata& expected_metadata,
    std::uint64_t expected_frames_per_bucket) {
  if (bytes.size() > 128U * 1024U) {
    return std::nullopt;
  }
  const auto text = std::string_view{
      reinterpret_cast<const char*>(bytes.data()), bytes.size()};
  const auto encoded = nlohmann::json::parse(text, nullptr, false);
  if (encoded.is_discarded() ||
      !exact_keys(
          encoded,
          {"contract",
           "metadata",
           "algorithm_version",
           "fold",
           "frames_per_bucket",
           "bucket_count",
           "buckets"}) ||
      !encoded.at("contract").is_string() ||
      encoded.at("contract") != kWaveformCacheContract ||
      !encoded.at("fold").is_string() ||
      encoded.at("fold") != kWaveformCacheFold ||
      !exact_keys(
          encoded.at("metadata"),
          {"sample_rate", "channels", "source_frames"}) ||
      !encoded.at("buckets").is_array()) {
    return std::nullopt;
  }
  const auto algorithm = cache_unsigned(
      encoded,
      "algorithm_version",
      std::numeric_limits<std::uint32_t>::max());
  const auto frames_per_bucket =
      cache_unsigned(encoded, "frames_per_bucket");
  const auto bucket_count = cache_unsigned(encoded, "bucket_count", 512U);
  const auto sample_rate = cache_unsigned(
      encoded.at("metadata"),
      "sample_rate",
      std::numeric_limits<std::uint32_t>::max());
  const auto channels = cache_unsigned(
      encoded.at("metadata"),
      "channels",
      std::numeric_limits<std::uint16_t>::max());
  const auto source_frames =
      cache_unsigned(encoded.at("metadata"), "source_frames");
  const auto expected_bucket_count =
      ceiling_divide(expected_metadata.source_frames,
                     expected_frames_per_bucket);
  if (!algorithm.has_value() ||
      *algorithm != cooker::kWaveformAlgorithmVersion ||
      !frames_per_bucket.has_value() ||
      *frames_per_bucket != expected_frames_per_bucket ||
      !bucket_count.has_value() ||
      *bucket_count != expected_bucket_count ||
      encoded.at("buckets").size() != *bucket_count ||
      !sample_rate.has_value() ||
      *sample_rate != expected_metadata.sample_rate ||
      !channels.has_value() || *channels != expected_metadata.channels ||
      !source_frames.has_value() ||
      *source_frames != expected_metadata.source_frames) {
    return std::nullopt;
  }
  std::vector<cooker::PeakBucket> buckets;
  buckets.reserve(static_cast<std::size_t>(*bucket_count));
  std::uint64_t expected_start = 0;
  for (const auto& bucket : encoded.at("buckets")) {
    if (!exact_keys(
            bucket,
            {"start_frame", "end_frame", "peak_magnitude"})) {
      return std::nullopt;
    }
    const auto start = cache_unsigned(bucket, "start_frame");
    const auto end = cache_unsigned(bucket, "end_frame");
    const auto peak = cache_unsigned(bucket, "peak_magnitude", 32'768U);
    const auto expected_end = expected_start + std::min(
        expected_frames_per_bucket,
        expected_metadata.source_frames - expected_start);
    if (!start.has_value() || !end.has_value() || !peak.has_value() ||
        *start != expected_start || *end != expected_end) {
      return std::nullopt;
    }
    buckets.push_back(cooker::PeakBucket{
        *start,
        *end,
        static_cast<std::uint16_t>(*peak),
    });
    expected_start = *end;
  }
  if (expected_start != expected_metadata.source_frames) {
    return std::nullopt;
  }
  return cooker::WaveformEnvelope{
      expected_metadata,
      cooker::kWaveformAlgorithmVersion,
      std::move(buckets),
  };
}

std::optional<cooker::WaveformEnvelope> cached_waveform_window(
    const cooker::WaveformEnvelope& cached,
    const cooker::WaveformRequest& request,
    std::uint64_t frames_per_bucket) {
  if (ceiling_divide(
          request.end_frame - request.start_frame,
          request.bucket_count) != frames_per_bucket ||
      request.start_frame % frames_per_bucket != 0 ||
      (request.end_frame != cached.metadata.source_frames &&
       request.end_frame % frames_per_bucket != 0)) {
    return std::nullopt;
  }
  const auto begin = request.start_frame / frames_per_bucket;
  const auto count = ceiling_divide(
      request.end_frame - request.start_frame, frames_per_bucket);
  if (begin > cached.buckets.size() ||
      count > cached.buckets.size() - begin || count > request.bucket_count) {
    return std::nullopt;
  }
  std::vector<cooker::PeakBucket> buckets(
      cached.buckets.begin() + static_cast<std::ptrdiff_t>(begin),
      cached.buckets.begin() +
          static_cast<std::ptrdiff_t>(begin + count));
  if (buckets.empty() || buckets.front().start_frame != request.start_frame ||
      buckets.back().end_frame != request.end_frame) {
    return std::nullopt;
  }
  return cooker::WaveformEnvelope{
      cached.metadata,
      cached.algorithm_version,
      std::move(buckets),
  };
}

bool valid_trigger_mode(domain::TriggerMode mode) {
  switch (mode) {
    case domain::TriggerMode::one_shot:
    case domain::TriggerMode::gate:
    case domain::TriggerMode::loop_gate:
    case domain::TriggerMode::loop_toggle:
      return true;
  }
  return false;
}

foundation::Result<void> remove_sample_staging(
    const std::shared_ptr<project_io::ProjectStoragePlatform>& platform,
    const std::filesystem::path& directory) {
  return platform->remove_tree(directory);
}

struct SampleStagingCleanup {
  ~SampleStagingCleanup() {
    lease.reset();
    if (platform != nullptr && !directory.empty()) {
      (void)remove_sample_staging(platform, directory);
    }
  }

  std::shared_ptr<project_io::ProjectStoragePlatform> platform;
  std::filesystem::path directory;
  std::unique_ptr<project_io::ProjectWriterLease> lease;
};

foundation::Result<void> validate_initial_pattern(
    const domain::Pattern& pattern) {
  if (!domain::is_valid_uuid(pattern.id.value())) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "pattern id must be a lowercase UUID",
        });
  }
  if (pattern.bars != 1 && pattern.bars != 2 &&
      pattern.bars != 4 && pattern.bars != 8) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "pattern bars must be one of 1, 2, 4, or 8",
        });
  }
  const auto loop_length = domain::pattern_length_ticks(pattern.bars);
  for (const auto& event : pattern.events) {
    if (!domain::is_valid_slot(event.slot) || event.velocity < 1 ||
        event.velocity > 127 || event.onset_tick >= loop_length ||
        event.duration_tick < 1 ||
        event.duration_tick > loop_length - event.onset_tick) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_argument,
              "pattern event is invalid",
          });
    }
  }
  return foundation::Result<void>::success();
}

std::vector<domain::PatternEvent> canonical_recovery_events(
    const project_io::ActiveSequenceJournal& journal) {
  std::vector<domain::PatternEvent> recovered;
  for (const auto& flush : journal.flushes) {
    if (!flush.completed) {
      recovered = domain::merge_pattern_events(
          recovered, flush.recovery_events);
    }
  }
  return domain::merge_pattern_events(recovered, journal.pending_events);
}

}  // namespace

struct RuntimeProjectWriterLease::Impl {
  explicit Impl(std::unique_ptr<project_io::ProjectWriterLease> owned)
      : owned(std::move(owned)) {}

  std::unique_ptr<project_io::ProjectWriterLease> owned;
};

struct Application::Impl {
  struct PreparedQuotaUsage {
    std::uint64_t bytes;
    std::uint64_t frames;
  };

  struct SampleQuotaComputation {
    SampleQuotaResult result;
    std::array<std::uint64_t, 4> bank_used_bytes;
  };

  struct SampleImportState {
    SampleImportBeginRequest request;
    std::filesystem::path directory;
    std::filesystem::path payload_path;
    std::uint64_t received_bytes;
    bool finalized;
    std::unique_ptr<project_io::ProjectWriterLease> lease;
  };

  struct ReplayIdentity {
    std::filesystem::path project_path;
    domain::PerformanceId performance_id;
  };

  struct ReplayStopReceipt {
    std::filesystem::path project_path;
    ReplayId replay_id;
    ReplayRuntimeStatus status;
  };

  using PressedSequencePad = detail::PatternOwnedPress;

  struct SequenceRuntime {
    foundation::SequenceSessionId session_id;
    foundation::PatternId pattern_id;
    std::uint8_t bars{};
    std::uint64_t expected_revision{};
    std::uint64_t next_flush_seq{};
    audio::TransportAnchor anchor;
    std::uint64_t last_runtime_frame{};
    std::optional<std::uint64_t> last_input_sequence;
    bool quantize_enabled{};
    std::uint8_t swing_percent{};
    std::uint64_t available_slots{};
    std::uint64_t overlay_generation{};
    std::vector<domain::PatternEvent> pending_events;
    std::map<domain::PadSlotId, PressedSequencePad> pressed;
    std::optional<foundation::PatternId> pending_pattern_id;
    std::optional<std::uint64_t> effective_runtime_frame;
    std::optional<project_io::SequenceFlushRecord> in_flight_flush;
    std::optional<project_io::SequenceFlushIdentity> last_flush_identity;
    std::optional<std::uint64_t> last_committed_revision;
    std::unique_ptr<project_io::ProjectWriterLease> lease;
    std::optional<domain::PadSlotId> armed_capture_slot;
  };

  struct OpenPerformancePad {
    std::uint8_t slot{};
    std::uint64_t onset_tick{};
    std::uint8_t velocity{};
  };

  struct OpenPerformanceFx {
    std::string gesture_id;
    std::uint16_t effective_value{};
    std::optional<std::uint64_t> pending_window;
    std::optional<std::size_t> pending_event_index;
  };

  struct PerformanceEventReceipt {
    std::string payload;
    std::uint64_t accepted_tick{};
    std::uint64_t input_sequence{};
    bool coalesced{};
  };

  struct PendingPerformanceLaunch {
    foundation::CommandId request_id;
    std::uint8_t pattern_slot{};
    std::uint64_t target_tick{};
    bool claimed{};
  };

  struct PerformanceRuntime {
    foundation::SequenceSessionId session_id;
    domain::PerformanceId performance_id;
    std::uint64_t expected_revision{};
    std::uint64_t next_flush_seq{};
    std::vector<domain::PerformanceEvent> pending_events;
    std::map<std::string, OpenPerformancePad> open_pads;
    std::map<domain::PerformanceFx, OpenPerformanceFx> open_fx;
    bool hold{};
    std::map<std::string, PerformanceEventReceipt> event_receipts;
    std::map<std::string, std::pair<std::string, PendingPerformanceLaunch>>
        launch_receipts;
    std::optional<PendingPerformanceLaunch> pending_launch;
    std::optional<PatternLaunchOutcome> last_launch_ack;
    std::uint64_t last_accepted_tick{};
    bool recovery_required{};
  };

  explicit Impl(ApplicationConfig config)
      : workspace_root(std::move(config.workspace_root)),
        registry(
            config.providers
                ? std::move(config.providers)
                : std::make_shared<provider::Registry>()),
        storage_platform(
            config.storage_platform
                ? std::move(config.storage_platform)
                : project_io::make_default_project_storage_platform()),
        performance_clock(std::move(config.performance_clock)),
        performance_input_sequencer(
            std::move(config.performance_input_sequencer)),
        pattern_launch_acknowledger(
            std::move(config.pattern_launch_acknowledger)),
        performance_replay_controller(
            std::move(config.performance_replay_controller)),
        performance_gesture_sink(std::move(config.performance_gesture_sink)),
        sample_limits(
            config.runtime_preparation_limits.value_or(kDefaultSampleLimits)),
        soundset_transport(std::move(config.soundset_catalog_transport)),
        soundset_source(std::move(config.soundset_catalog_source)),
        soundset_limits(
            config.soundset_store_limits.value_or(
                kDefaultSoundSetStoreLimits)),
        soundset_sets(workspace_root, soundset_limits, storage_platform),
        candidates(workspace_root, storage_platform),
        projects(storage_platform),
        sequence_journals(storage_platform),
        bundle_transfers(storage_platform),
        waveform_cache(
            workspace_root / ".lmdj-host/workspace-cache",
            storage_platform),
        provider_policy(std::move(config.provider_policy)),
        provider_timestamp_source(
            config.timestamp_source
                ? std::move(config.timestamp_source)
                : default_timestamp_source()),
        attempts(workspace_root, provider_policy,
                 [this] { return provider_timestamp_source(); }) {
    if (!workspace_root.is_absolute()) {
      throw std::invalid_argument("workspace_root must be absolute");
    }
    if (!performance_replay_controller) {
      throw std::invalid_argument(
          "performance_replay_controller is required");
    }
    const auto cleaned = bundle_transfers.cleanup_incomplete(workspace_root);
    if (!cleaned.has_value()) {
      throw std::runtime_error(
          "incomplete Project Bundle staging cleanup failed");
    }
    const auto sample_cleaned = cleanup_sample_import_staging();
    if (!sample_cleaned.has_value()) {
      throw std::runtime_error("incomplete Sample staging cleanup failed");
    }
  }

  ~Impl() { abandon_sequence_sessions();
    abandon_performance_sessions(); }

  foundation::Result<void> cleanup_sample_import_staging() {
    std::lock_guard lock(sample_mutex);
    const auto root = workspace_root / ".lmdj-host/sample-import-staging";
    const auto present = storage_platform->directory_exists(root);
    if (!present.has_value()) {
      return foundation::Result<void>::failure(sample_storage_error(
          present.error(), "Sample staging root could not be inspected"));
    }
    if (!present.value()) {
      return foundation::Result<void>::success();
    }
    const auto names = storage_platform->list_directories(root);
    if (!names.has_value()) {
      return foundation::Result<void>::failure(sample_storage_error(
          names.error(), "Sample staging root could not be listed"));
    }
    const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                         std::chrono::system_clock::now().time_since_epoch())
                         .count();
    std::size_t scanned = 0;
    for (const auto& name : names.value()) {
      const std::filesystem::path relative{name};
      const auto token = relative.string();
      if (relative.filename() != relative || !domain::is_valid_uuid(token)) {
        continue;
      }
      if (scanned++ >= kMaximumSampleScavengeFiles) {
        break;
      }
      if (sample_imports.contains(token)) {
        continue;
      }
      const auto directory = root / relative;
      auto lease = storage_platform->acquire_writer(directory);
      if (!lease.has_value()) {
        if (lease.error().details.is_object() &&
            lease.error().details.value(
                "storage_condition", std::string{}) ==
                project_io::kStorageConditionProjectBusy) {
          continue;
        }
        return foundation::Result<void>::failure(sample_storage_error(
            lease.error(), "Sample staging cleanup could not acquire writer"));
      }

      const auto validated =
          storage_platform->validate_managed_tree(directory);
      if (!validated.has_value()) {
        return foundation::Result<void>::failure(sample_storage_error(
            validated.error(), "Sample staging candidate is invalid"));
      }
      const auto files = storage_platform->list_names(directory);
      if (!files.has_value()) {
        return foundation::Result<void>::failure(sample_storage_error(
            files.error(), "Sample staging candidate could not be listed"));
      }
      const auto directories =
          storage_platform->list_directories(directory);
      if (!directories.has_value()) {
        return foundation::Result<void>::failure(sample_storage_error(
            directories.error(),
            "Sample staging candidate could not be listed"));
      }
      const auto has_file = [&files](std::string_view name) {
        return std::find(
                   files.value().begin(),
                   files.value().end(),
                   name) != files.value().end();
      };
      const auto has_strict_storage_shape =
          directories.value().empty() && files.value().size() == 2U &&
          has_file("state.json") && has_file("payload.wav");
      const auto marker_path = directory / "state.json";
      bool retain_candidate = false;
      if (has_strict_storage_shape) {
        const auto marker_length =
            storage_platform->byte_length(marker_path);
        if (!marker_length.has_value()) {
          return foundation::Result<void>::failure(sample_storage_error(
              marker_length.error(),
              "Sample staging marker could not be inspected"));
        }
        if (marker_length.value() <= kMaximumSampleStagingMarkerBytes) {
          const auto marker_bytes =
              storage_platform->read_complete(marker_path);
          if (!marker_bytes.has_value()) {
            return foundation::Result<void>::failure(sample_storage_error(
                marker_bytes.error(),
                "Sample staging marker could not be read"));
          }
          const auto marker_text = std::string_view{
              reinterpret_cast<const char*>(marker_bytes.value().data()),
              marker_bytes.value().size()};
          const auto marker =
              nlohmann::json::parse(marker_text, nullptr, false);
          if (!marker.is_discarded() &&
              exact_keys(
                  marker,
                  {"contract", "created_unix_seconds", "state", "token"}) &&
              marker.at("contract").is_string() &&
              marker.at("contract") == kSampleStagingContract &&
              marker.at("state").is_string() &&
              marker.at("state") == "incomplete" &&
              marker.at("token").is_string() &&
              marker.at("token") == token) {
            const auto created =
                cache_unsigned(marker, "created_unix_seconds");
            if (created.has_value() && now >= 0 &&
                *created <= static_cast<std::uint64_t>(now) &&
                static_cast<std::uint64_t>(now) - *created <
                    kMinimumSampleStagingAgeSeconds) {
              retain_candidate = true;
            }
          }
        }
      }
      if (retain_candidate) {
        lease.value().reset();
        continue;
      }
      const auto removed = remove_sample_staging(storage_platform, directory);
      lease.value().reset();
      if (!removed.has_value()) {
        return foundation::Result<void>::failure(sample_storage_error(
            removed.error(), "Sample staging cleanup failed"));
      }
    }
    return foundation::Result<void>::success();
  }

  static Error sequence_error(
      ErrorCode code,
      std::string message,
      nlohmann::json details = nlohmann::json::object()) {
    return Error{code, std::move(message), std::move(details)};
  }

  static std::string sequence_key(const std::filesystem::path& path) {
    return path.generic_string();
  }

  struct SequenceAuthoringAdmission {
    std::unique_lock<std::mutex> lock;
  };

  foundation::Result<SequenceAuthoringAdmission>
  admit_non_sequence_authoring(const std::filesystem::path& path) {
    std::unique_lock lock(sequence_mutex);
    const auto found = sequence_sessions.find(sequence_key(path));
    if (found != sequence_sessions.end()) {
      return foundation::Result<SequenceAuthoringAdmission>::failure(
          sequence_error(
              ErrorCode::invalid_argument,
              "Project mutation is blocked by an active Sequence session",
              {{"reason", "sequence_session_active"},
               {"session_id", found->second.session_id.value()},
               {"remedy", "stop the active Sequence session before retrying"}}));
    }
    // A Facade-vended transport controller's journal is Facade-owned and
    // live; without this registration the reconciliation below would
    // misclassify it as owner loss and seal it out from under the recording.
    // Sample-class mutations keep their legacy busy guard instead: rejected
    // while the transport journal is open, admitted once it settles.
    // Lock order is sequence_mutex before the registry mutex; the registry
    // lock never spans journal IO, and the controller-destruction callback
    // takes only the registry mutex.
    std::set<foundation::SequenceSessionId> transport_owners;
    {
      std::lock_guard registry_lock(transport_sessions->mutex);
      const auto registered =
          transport_sessions->sessions.find(sequence_key(path));
      if (registered != transport_sessions->sessions.end()) {
        transport_owners = registered->second;
      }
    }
    if (!transport_owners.empty()) {
      auto active = sequence_journals.read_active(path);
      if (!active.has_value() &&
          active.error().code != ErrorCode::not_found) {
        return foundation::Result<SequenceAuthoringAdmission>::failure(
            active.error());
      }
      if (active.has_value() &&
          transport_owners.contains(active.value().session_id)) {
        return foundation::Result<SequenceAuthoringAdmission>::failure(
            sequence_error(
                ErrorCode::invalid_argument,
                "Project mutation is blocked by the active Pattern transport "
                "session",
                {{"reason", "sequence_session_active"},
                 {"session_id", active.value().session_id.value()},
                 {"remedy",
                  "stop the Pattern transport recording before retrying"}}));
      }
    }
    const auto performance = performance_sessions.find(sequence_key(path));
    if (performance != performance_sessions.end()) {
      return foundation::Result<SequenceAuthoringAdmission>::failure(
          sequence_error(
              ErrorCode::invalid_argument,
              "Project mutation is blocked by an active Performance session",
              {{"reason", "performance_session_active"},
               {"session_id", performance->second.session_id.value()},
               {"remedy",
                "stop the active Performance session before retrying"}}));
    }
    auto reconciled = projects.reconcile_sequence_recovery(path);
    if (!reconciled.has_value()) {
      return foundation::Result<SequenceAuthoringAdmission>::failure(
          reconciled.error());
    }
    testing::invoke_sequence_authoring_admission_hook();
    return foundation::Result<SequenceAuthoringAdmission>::success(
        SequenceAuthoringAdmission{std::move(lock)});
  }

  static std::string state_name(SequenceRecordState state) {
    switch (state) {
      case SequenceRecordState::inactive:
        return "inactive";
      case SequenceRecordState::active:
        return "active";
      case SequenceRecordState::switching:
        return "switching";
      case SequenceRecordState::recoverable:
        return "recoverable";
    }
    return "inactive";
  }

  static SequenceStatus runtime_status(const SequenceRuntime& runtime) {
    return SequenceStatus{
        runtime.pending_pattern_id.has_value()
            ? SequenceRecordState::switching
            : SequenceRecordState::active,
        runtime.session_id,
        runtime.pattern_id,
        runtime.pending_pattern_id,
        runtime.expected_revision,
        runtime.next_flush_seq,
        runtime.pending_events.size(),
        runtime.effective_runtime_frame,
    };
  }

  static std::uint64_t available_slot_mask(
      const domain::ProjectState& project) {
    std::uint64_t mask = 0;
    for (std::size_t bank = 0; bank < project.banks.size(); ++bank) {
      for (std::size_t pad = 0; pad < project.banks.at(bank).size(); ++pad) {
        if (project.banks.at(bank).at(pad).asset_id.has_value()) {
          mask |= std::uint64_t{1} << (bank * 16U + pad);
        }
      }
    }
    return mask;
  }

  static std::uint8_t slot_index(domain::PadSlotId slot) {
    return static_cast<std::uint8_t>(slot.bank * 16U + slot.pad);
  }

  static detail::PatternEventReducer event_reducer(SequenceRuntime& runtime) {
    return {runtime.bars, runtime.quantize_enabled, runtime.swing_percent,
            runtime.overlay_generation, runtime.pending_events, runtime.pressed};
  }

  static foundation::Result<void> validate_sequence_path_and_session(
      const std::filesystem::path& path,
      const foundation::SequenceSessionId& session_id) {
    if (!valid_host_project_path(path) ||
        !domain::is_valid_uuid(session_id.value())) {
      return foundation::Result<void>::failure(sequence_error(
          ErrorCode::invalid_argument,
          "Sequence request is invalid"));
    }
    return foundation::Result<void>::success();
  }

  static std::string generated_uuid() {
    std::array<std::uint8_t, 16> bytes{};
    std::random_device source;
    for (auto& byte : bytes) {
      byte = static_cast<std::uint8_t>(source());
    }
    bytes[6] = static_cast<std::uint8_t>((bytes[6] & 0x0fU) | 0x40U);
    bytes[8] = static_cast<std::uint8_t>((bytes[8] & 0x3fU) | 0x80U);
    constexpr char digits[] = "0123456789abcdef";
    std::string value;
    value.reserve(36);
    for (std::size_t index = 0; index < bytes.size(); ++index) {
      if (index == 4 || index == 6 || index == 8 || index == 10) {
        value.push_back('-');
      }
      value.push_back(digits[bytes[index] >> 4U]);
      value.push_back(digits[bytes[index] & 0x0fU]);
    }
    return value;
  }

  foundation::Result<SequenceMutationResult> begin_sequence(
      const SequenceBeginRequest& request) {
    auto valid = validate_sequence_path_and_session(
        request.project_path, request.session_id);
    if (!valid.has_value() ||
        !domain::is_valid_uuid(request.pattern_id.value()) ||
        (request.armed_capture_slot.has_value() &&
         !domain::is_valid_slot(*request.armed_capture_slot))) {
      return foundation::Result<SequenceMutationResult>::failure(
          valid.has_value()
              ? sequence_error(
                    ErrorCode::invalid_argument,
                    "Sequence Pattern id is invalid")
              : valid.error());
    }
    std::lock_guard lock(sequence_mutex);
    const auto key = sequence_key(request.project_path);
    const auto existing = sequence_sessions.find(key);
    if (existing != sequence_sessions.end()) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(
              ErrorCode::invalid_argument,
              "a Sequence session is already active for this Project",
              {{"reason", "sequence_session_active"},
               {"session_id", existing->second.session_id.value()}}));
    }
    // A Facade-vended transport engagement with an open journal owns Sequence
    // authoring for the Project; a direct legacy begin would create a second
    // journal owner. Registration alone (an idle or settled controller) does
    // not block: with no open transport journal there is one owner at a time.
    std::set<foundation::SequenceSessionId> transport_owners;
    {
      std::lock_guard registry_lock(transport_sessions->mutex);
      const auto registered = transport_sessions->sessions.find(key);
      if (registered != transport_sessions->sessions.end()) {
        transport_owners = registered->second;
      }
    }
    if (!transport_owners.empty()) {
      auto active = sequence_journals.read_active(request.project_path);
      if (!active.has_value() &&
          active.error().code != ErrorCode::not_found) {
        return foundation::Result<SequenceMutationResult>::failure(
            active.error());
      }
      if (active.has_value() &&
          transport_owners.contains(active.value().session_id)) {
        return foundation::Result<SequenceMutationResult>::failure(
            sequence_error(
                ErrorCode::invalid_argument,
                "Pattern transport session owns Sequence authoring for this "
                "Project",
                {{"reason", "sequence_session_active"},
                 {"session_id", active.value().session_id.value()},
                 {"remedy",
                  "destroy the transport controller (Project replacement or "
                  "Host close) before legacy Sequence authoring"}}));
      }
    }
    auto lease = acquire_project_writer(request.project_path);
    if (!lease.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          lease.error());
    }
    auto reconciled = projects.reconcile_sequence_recovery(
        request.project_path);
    if (!reconciled.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          reconciled.error());
    }
    auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          loaded.error());
    }
    if (loaded.value().revision != request.expected_revision) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(
              ErrorCode::revision_conflict,
              "Sequence begin expected a different Project revision",
              {{"actual_revision", loaded.value().revision},
               {"expected_revision", request.expected_revision}}));
    }
    const auto pattern = loaded.value().patterns.find(request.pattern_id);
    if (pattern == loaded.value().patterns.end()) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::not_found, "Sequence Pattern was not found"));
    }
    if (request.armed_capture_slot.has_value() &&
        loaded.value()
            .banks.at(request.armed_capture_slot->bank)
            .at(request.armed_capture_slot->pad)
            .asset_id.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(
              ErrorCode::invalid_argument,
              "armed Capture target Pad is not empty",
              {{"reason", "armed_capture_target_assigned"}}));
    }
    auto begun = sequence_journals.begin(
        request.project_path,
        request.session_id,
        request.pattern_id,
        pattern->second.bars,
        project_io::sequence_pattern_fingerprint(pattern->second),
        request.expected_revision,
        request.armed_capture_slot);
    if (!begun.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          begun.error());
    }
    SequenceRuntime runtime{
        request.session_id,
        request.pattern_id,
        pattern->second.bars,
        request.expected_revision,
        0,
        audio::TransportAnchor{request.runtime_frame, 0, loaded.value().bpm},
        request.runtime_frame,
        std::nullopt,
        loaded.value().quantize_enabled,
        loaded.value().swing_percent,
        available_slot_mask(loaded.value()),
        0,
        {},
        {},
        std::nullopt,
        std::nullopt,
        std::nullopt,
        std::nullopt,
        std::nullopt,
        std::move(lease.value()),
        request.armed_capture_slot,
    };
    auto [inserted, ok] = sequence_sessions.emplace(key, std::move(runtime));
    if (!ok) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::internal_error,
                         "Sequence registry insertion failed"));
    }
    return foundation::Result<SequenceMutationResult>::success(
        SequenceMutationResult{runtime_status(inserted->second), std::nullopt,
                               false, std::nullopt});
  }

  foundation::Result<SequenceMutationResult> record_sequence_event(
      const SequenceEventRequest& request) {
    auto valid = validate_sequence_path_and_session(
        request.project_path, request.session_id);
    if (!valid.has_value() || !domain::is_valid_slot(request.event.slot) ||
        (request.event.pressed &&
         (request.event.velocity < 1 || request.event.velocity > 127))) {
      return foundation::Result<SequenceMutationResult>::failure(
          valid.has_value()
              ? sequence_error(ErrorCode::invalid_argument,
                               "Sequence Pad event is invalid")
              : valid.error());
    }
    std::lock_guard lock(sequence_mutex);
    const auto found = sequence_sessions.find(sequence_key(request.project_path));
    if (found == sequence_sessions.end() ||
        found->second.session_id != request.session_id) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence event owner does not match",
                         {{"reason", "sequence_owner_mismatch"}}));
    }
    auto& runtime = found->second;
    if (request.event.runtime_frame < runtime.last_runtime_frame ||
        (runtime.last_input_sequence.has_value() &&
         request.event.input_sequence <= *runtime.last_input_sequence)) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence event ordering is invalid"));
    }
    if (runtime.effective_runtime_frame.has_value() &&
        request.event.runtime_frame >= *runtime.effective_runtime_frame) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(
              ErrorCode::invalid_argument,
              "Sequence switch boundary must be flushed first",
              {{"reason", "switch_boundary_reached"},
               {"effective_runtime_frame", *runtime.effective_runtime_frame}}));
    }
    if (runtime.armed_capture_slot == request.event.slot) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(
              ErrorCode::invalid_argument,
              "armed Capture Pad is not a Sequence event",
              {{"reason", "armed_capture_in_progress"}}));
    }
    const auto ticks = audio::raw_tick_at(
        runtime.anchor, request.event.runtime_frame);
    if (!ticks.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(ticks.error());
    }
    if (request.event.pressed &&
        (runtime.available_slots &
         (std::uint64_t{1} << slot_index(request.event.slot))) == 0) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence Pad has no assigned Sample",
                         {{"reason", "sample_unavailable"}}));
    }
    const auto previous_pending = runtime.pending_events;
    const auto previous_pressed = runtime.pressed;
    auto reducer = event_reducer(runtime);
    if (request.event.pressed) {
      reducer.press(request.event.slot, ticks.value(), request.event.velocity);
    } else if (!reducer.release(request.event.slot, ticks.value())) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence release has no matching press"));
    }
    const auto durable = sequence_journals.append_tail(
        request.project_path,
        runtime.session_id,
        runtime.pattern_id,
        runtime.expected_revision,
        request.event.input_sequence,
        reducer.recoverable_tail());
    if (!durable.has_value()) {
      runtime.pending_events = previous_pending;
      runtime.pressed = previous_pressed;
      return foundation::Result<SequenceMutationResult>::failure(durable.error());
    }
    runtime.last_runtime_frame = request.event.runtime_frame;
    runtime.last_input_sequence = request.event.input_sequence;
    return foundation::Result<SequenceMutationResult>::success(
        SequenceMutationResult{
            runtime_status(runtime), std::nullopt, false, std::nullopt});
  }

  static void finalize_unreleased(SequenceRuntime& runtime, bool clear) {
    event_reducer(runtime).finalize_unreleased(clear);
  }

  foundation::Result<void> activate_switched_pattern(
      const std::filesystem::path& path,
      SequenceRuntime& runtime,
      const domain::ProjectState& project) {
    if (!runtime.pending_pattern_id.has_value()) {
      return foundation::Result<void>::success();
    }
    const auto next = project.patterns.find(*runtime.pending_pattern_id);
    if (next == project.patterns.end()) {
      return foundation::Result<void>::failure(sequence_error(
          ErrorCode::not_found, "next Sequence Pattern was not found"));
    }
    auto switched = sequence_journals.switch_pattern(
        path,
        runtime.session_id,
        next->second.id,
        next->second.bars,
        project_io::sequence_pattern_fingerprint(next->second),
        project.revision);
    if (!switched.has_value()) {
      return switched;
    }
    runtime.pattern_id = next->second.id;
    runtime.bars = next->second.bars;
    runtime.expected_revision = project.revision;
    runtime.pending_pattern_id.reset();
    runtime.effective_runtime_frame.reset();
    if (!runtime.pending_events.empty()) {
      runtime.pending_events.clear();
      ++runtime.overlay_generation;
    }
    runtime.pressed.clear();
    return foundation::Result<void>::success();
  }

  foundation::Result<SequenceMutationResult> flush_sequence_locked(
      const SequenceFlushRequest& request,
      bool stop) {
    const auto key = sequence_key(request.project_path);
    auto found = sequence_sessions.find(key);
    if (found == sequence_sessions.end() ||
        found->second.session_id != request.session_id) {
      auto replayed = projects.replay_sequence_flush(
          request.project_path, request.session_id, request.command_id);
      if (!replayed.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            replayed.error());
      }
      if (replayed.value().has_value()) {
        SequenceStatus status;
        status.expected_revision =
            replayed.value()->outcome.state.revision;
        return foundation::Result<SequenceMutationResult>::success(
            SequenceMutationResult{
                status,
                replayed.value()->committed_revision,
                true,
                replayed.value()->identity.pattern_id,
            });
      }
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence flush owner does not match",
                         {{"reason", "sequence_owner_mismatch"}}));
    }
    auto& runtime = found->second;
    if (runtime.last_flush_identity.has_value() &&
        runtime.last_flush_identity->command_id == request.command_id) {
      return foundation::Result<SequenceMutationResult>::success(
          SequenceMutationResult{
              runtime_status(runtime),
              runtime.last_committed_revision,
              true,
              runtime.last_flush_identity->pattern_id,
          });
    }
    const bool replaying_in_flight_command =
        runtime.in_flight_flush.has_value() &&
        runtime.in_flight_flush->command_id == request.command_id;
    auto replay_persisted_command = [&]() -> foundation::Result<
        std::optional<SequenceMutationResult>> {
      auto replayed = projects.replay_sequence_flush(
          request.project_path, runtime.session_id, request.command_id);
      if (!replayed.has_value()) {
        return foundation::Result<
            std::optional<SequenceMutationResult>>::failure(
            replayed.error());
      }
      if (!replayed.value().has_value()) {
        return foundation::Result<
            std::optional<SequenceMutationResult>>::success(std::nullopt);
      }
      return foundation::Result<
          std::optional<SequenceMutationResult>>::success(
          SequenceMutationResult{
              runtime_status(runtime),
              replayed.value()->committed_revision,
              true,
              replayed.value()->identity.pattern_id,
          });
    };
    if (!replaying_in_flight_command) {
      auto replayed = replay_persisted_command();
      if (!replayed.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            replayed.error());
      }
      if (replayed.value().has_value()) {
        return foundation::Result<SequenceMutationResult>::success(
            std::move(*replayed.value()));
      }
    }
    if (!replaying_in_flight_command &&
        request.runtime_frame < runtime.last_runtime_frame) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence flush frame moved backwards"));
    }
    const bool switch_due = runtime.effective_runtime_frame.has_value() &&
                            request.runtime_frame >=
                                *runtime.effective_runtime_frame;

    if (!replaying_in_flight_command) {
      finalize_unreleased(runtime, stop || switch_due);
      runtime.last_runtime_frame = request.runtime_frame;
    }
    std::optional<project_io::SequenceFlushExecution> execution;
    const bool was_switching = runtime.pending_pattern_id.has_value();
    bool replayed_in_flight_command = false;
    if (runtime.in_flight_flush.has_value()) {
      const auto& flush = *runtime.in_flight_flush;
      project_io::SequenceFlushIdentity identity{
          runtime.session_id,
          flush.flush_seq,
          flush.command_id,
          flush.pattern_id,
      };
      auto committed = projects.execute_sequence_flush(
          request.project_path, identity);
      if (!committed.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            committed.error());
      }
      execution.emplace(std::move(committed.value()));
      runtime.expected_revision = execution->outcome.state.revision;
      std::erase_if(
          runtime.pending_events,
          [&flush](const auto& pending) {
            return std::ranges::find(flush.canonical_events, pending) !=
                   flush.canonical_events.end();
          });
      runtime.last_flush_identity = identity;
      runtime.last_committed_revision = runtime.expected_revision;
      ++runtime.next_flush_seq;
      replayed_in_flight_command = flush.command_id == request.command_id;
      runtime.in_flight_flush.reset();
    }
    if (!replayed_in_flight_command && !runtime.pending_events.empty()) {
      if (was_switching) {
        auto active = sequence_journals.set_state(
            request.project_path,
            runtime.session_id,
            project_io::SequenceSessionState::active);
        if (!active.has_value()) {
          return foundation::Result<SequenceMutationResult>::failure(
              active.error());
        }
      }
      auto appended = sequence_journals.append_flush(
          request.project_path,
          runtime.session_id,
          request.command_id,
          runtime.pattern_id,
          runtime.expected_revision,
          runtime.pending_events);
      if (!appended.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            appended.error());
      }
      runtime.in_flight_flush = appended.value();
      project_io::SequenceFlushIdentity identity{
          runtime.session_id,
          appended.value().flush_seq,
          request.command_id,
          runtime.pattern_id,
      };
      auto committed = projects.execute_sequence_flush(
          request.project_path, identity);
      if (!committed.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            committed.error());
      }
      execution.emplace(std::move(committed.value()));
      runtime.expected_revision = execution->outcome.state.revision;
      runtime.pending_events.clear();
      ++runtime.overlay_generation;
      runtime.last_flush_identity = identity;
      runtime.last_committed_revision = runtime.expected_revision;
      ++runtime.next_flush_seq;
      runtime.in_flight_flush.reset();
    }

    if (replayed_in_flight_command &&
        (!runtime.pending_events.empty() || !runtime.pressed.empty())) {
      return foundation::Result<SequenceMutationResult>::success(
          SequenceMutationResult{
              runtime_status(runtime),
              runtime.last_committed_revision,
              true,
              runtime.last_flush_identity->pattern_id,
          });
    }

    if (stop) {
      auto stopped = sequence_journals.set_state(
          request.project_path,
          runtime.session_id,
          project_io::SequenceSessionState::stopped);
      if (!stopped.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            stopped.error());
      }
      auto removed = sequence_journals.remove_active_if_complete(
          request.project_path, runtime.session_id);
      if (!removed.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            removed.error());
      }
      const auto revision = runtime.expected_revision;
      const auto committed_pattern_id = runtime.pattern_id;
      const auto replayed = execution.has_value() &&
                            execution->outcome.replayed;
      sequence_sessions.erase(found);
      SequenceStatus status;
      status.expected_revision = revision;
      return foundation::Result<SequenceMutationResult>::success(
          SequenceMutationResult{
              status, revision, replayed, committed_pattern_id});
    }

    if (switch_due) {
      std::optional<domain::ProjectState> project;
      if (execution.has_value()) {
        project = execution->outcome.state;
      }
      if (!execution.has_value()) {
        auto loaded = projects.load(request.project_path);
        if (!loaded.has_value()) {
          return foundation::Result<SequenceMutationResult>::failure(
              loaded.error());
        }
        project = std::move(loaded.value());
      }
      auto switched = activate_switched_pattern(
          request.project_path, runtime, *project);
      if (!switched.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            switched.error());
      }
    } else if (was_switching) {
      auto switching = sequence_journals.set_state(
          request.project_path,
          runtime.session_id,
          project_io::SequenceSessionState::switching);
      if (!switching.has_value()) {
        return foundation::Result<SequenceMutationResult>::failure(
            switching.error());
      }
    }
    return foundation::Result<SequenceMutationResult>::success(
        SequenceMutationResult{
            runtime_status(runtime),
            execution.has_value()
                ? std::optional<std::uint64_t>{runtime.expected_revision}
                : std::nullopt,
            execution.has_value() && execution->outcome.replayed,
            execution.has_value()
                ? std::optional<foundation::PatternId>{runtime.pattern_id}
                : std::nullopt,
        });
  }

  foundation::Result<SequenceMutationResult> flush_sequence(
      const SequenceFlushRequest& request,
      bool stop) {
    auto valid = validate_sequence_path_and_session(
        request.project_path, request.session_id);
    if (!valid.has_value() ||
        !domain::is_valid_uuid(request.command_id.value())) {
      return foundation::Result<SequenceMutationResult>::failure(
          valid.has_value()
              ? sequence_error(ErrorCode::invalid_argument,
                               "Sequence flush command id is invalid")
              : valid.error());
    }
    std::lock_guard lock(sequence_mutex);
    return flush_sequence_locked(request, stop);
  }

  foundation::Result<SequenceMutationResult> request_sequence_switch(
      const SequenceSwitchRequest& request) {
    auto valid = validate_sequence_path_and_session(
        request.project_path, request.session_id);
    if (!valid.has_value() ||
        !domain::is_valid_uuid(request.next_pattern_id.value())) {
      return foundation::Result<SequenceMutationResult>::failure(
          valid.has_value()
              ? sequence_error(ErrorCode::invalid_argument,
                               "next Sequence Pattern id is invalid")
              : valid.error());
    }
    std::lock_guard lock(sequence_mutex);
    auto found = sequence_sessions.find(sequence_key(request.project_path));
    if (found == sequence_sessions.end() ||
        found->second.session_id != request.session_id) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence switch owner does not match",
                         {{"reason", "sequence_owner_mismatch"}}));
    }
    auto& runtime = found->second;
    const auto switch_runtime_frame =
        request.runtime_frame.value_or(runtime.last_runtime_frame);
    if (switch_runtime_frame < runtime.last_runtime_frame) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence switch runtime frame moved backwards"));
    }
    auto current_numerator = audio::tick_numerator_at(
        runtime.anchor, switch_runtime_frame);
    if (!current_numerator.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          current_numerator.error());
    }
    const auto raw_tick = audio::whole_tick(current_numerator.value());
    const auto next_bar_tick =
        (raw_tick / domain::kBarTicks4x4 + 1U) * domain::kBarTicks4x4;
    if (next_bar_tick >
        std::numeric_limits<std::uint64_t>::max() /
            audio::kTickDenominator) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence switch boundary overflowed"));
    }
    const auto target_numerator = next_bar_tick * audio::kTickDenominator;
    const auto rate = static_cast<std::uint64_t>(runtime.anchor.bpm) *
                      audio::kTransportPpq;
    const auto delta_numerator = target_numerator - runtime.anchor.tick_numerator;
    const auto frame_delta = delta_numerator / rate +
                             (delta_numerator % rate == 0 ? 0U : 1U);
    if (frame_delta >
        std::numeric_limits<std::uint64_t>::max() -
            runtime.anchor.runtime_frame) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence switch frame overflowed"));
    }
    const auto effective_runtime_frame =
        runtime.anchor.runtime_frame + frame_delta;
    if (runtime.pending_pattern_id.has_value()) {
      const auto can_rebase_missed_boundary =
          runtime.pending_pattern_id == request.next_pattern_id &&
          request.runtime_frame.has_value() &&
          runtime.effective_runtime_frame.has_value() &&
          switch_runtime_frame >= *runtime.effective_runtime_frame;
      if (!can_rebase_missed_boundary) {
        return foundation::Result<SequenceMutationResult>::failure(
            sequence_error(ErrorCode::invalid_argument,
                           "a Sequence switch is already pending",
                           {{"reason", "switch_pending"}}));
      }
      runtime.effective_runtime_frame = effective_runtime_frame;
      runtime.last_runtime_frame = switch_runtime_frame;
      return foundation::Result<SequenceMutationResult>::success(
          SequenceMutationResult{
              runtime_status(runtime), std::nullopt, false, std::nullopt});
    }
    if (runtime.pattern_id == request.next_pattern_id) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "next Sequence Pattern is already active"));
    }
    auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          loaded.error());
    }
    if (!loaded.value().patterns.contains(request.next_pattern_id)) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::not_found,
                         "next Sequence Pattern was not found"));
    }
    runtime.pending_pattern_id = request.next_pattern_id;
    runtime.effective_runtime_frame = effective_runtime_frame;
    runtime.last_runtime_frame = switch_runtime_frame;
    auto switching = sequence_journals.set_state(
        request.project_path,
        runtime.session_id,
        project_io::SequenceSessionState::switching);
    if (!switching.has_value()) {
      runtime.pending_pattern_id.reset();
      runtime.effective_runtime_frame.reset();
      return foundation::Result<SequenceMutationResult>::failure(
          switching.error());
    }
    return foundation::Result<SequenceMutationResult>::success(
        SequenceMutationResult{
            runtime_status(runtime), std::nullopt, false, std::nullopt});
  }

  foundation::Result<SequenceStatus> query_sequence_status(
      const SequenceStatusRequest& request) const {
    if (!valid_host_project_path(request.project_path)) {
      return foundation::Result<SequenceStatus>::failure(sequence_error(
          ErrorCode::invalid_argument, "Sequence status path is invalid"));
    }
    std::lock_guard lock(sequence_mutex);
    const auto runtime = sequence_sessions.find(
        sequence_key(request.project_path));
    if (runtime != sequence_sessions.end()) {
      return foundation::Result<SequenceStatus>::success(
          runtime_status(runtime->second));
    }
    const auto active = sequence_journals.read_active(request.project_path);
    if (active.has_value()) {
      const auto pending = canonical_recovery_events(active.value()).size();
      return foundation::Result<SequenceStatus>::success(SequenceStatus{
          active.value().state == project_io::SequenceSessionState::switching
              ? SequenceRecordState::switching
              : SequenceRecordState::active,
          active.value().session_id,
          active.value().pattern_id,
          std::nullopt,
          active.value().expected_revision,
          active.value().next_flush_seq,
          pending,
          std::nullopt,
      });
    }
    if (active.error().code != ErrorCode::not_found) {
      return foundation::Result<SequenceStatus>::failure(active.error());
    }
    const auto recovery = sequence_journals.list_recoverable(
        request.project_path);
    if (!recovery.has_value()) {
      return foundation::Result<SequenceStatus>::failure(recovery.error());
    }
    if (recovery.value().empty()) {
      return foundation::Result<SequenceStatus>::success(SequenceStatus{});
    }
    const auto& candidate = recovery.value().front().journal;
    const auto pending = canonical_recovery_events(candidate).size();
    return foundation::Result<SequenceStatus>::success(SequenceStatus{
        SequenceRecordState::recoverable,
        candidate.session_id,
        candidate.pattern_id,
        std::nullopt,
        candidate.expected_revision,
        candidate.next_flush_seq,
        pending,
        std::nullopt,
    });
  }

  foundation::Result<SequenceOverlayProjection> query_sequence_overlay(
      const SequenceOverlayRequest& request) const {
    auto valid = validate_sequence_path_and_session(
        request.project_path, request.session_id);
    if (!valid.has_value()) {
      return foundation::Result<SequenceOverlayProjection>::failure(
          valid.error());
    }
    std::lock_guard lock(sequence_mutex);
    const auto runtime = sequence_sessions.find(
        sequence_key(request.project_path));
    if (runtime == sequence_sessions.end() ||
        runtime->second.session_id != request.session_id) {
      return foundation::Result<SequenceOverlayProjection>::failure(
          sequence_error(
              ErrorCode::invalid_argument,
              "Sequence overlay owner does not match",
              {{"reason", "sequence_owner_mismatch"}}));
    }
    return foundation::Result<SequenceOverlayProjection>::success(
        SequenceOverlayProjection{
            runtime->second.session_id,
            runtime->second.pattern_id,
            runtime->second.overlay_generation,
            runtime->second.pending_events,
        });
  }

  foundation::Result<std::vector<SequenceRecoveryInfo>>
  list_sequence_recovery(const SequenceStatusRequest& request) {
    if (!valid_host_project_path(request.project_path)) {
      return foundation::Result<std::vector<SequenceRecoveryInfo>>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Sequence recovery path is invalid"));
    }
    std::lock_guard lock(sequence_mutex);
    // Reopen surface: an unresolved transport admission whose owner is gone
    // (controller destroyed without settlement, Host crash) is sealed as
    // owner loss here so the recovery listing can offer it. A journal with a
    // live legacy session or live vended controller is never sealed by a
    // listing. Legacy journals carry no admission and keep their existing
    // reconcile timing. A completed-but-not-removed admission journal (owner
    // died between completion and removal) is reconciled to removal the same
    // way. Sealing requires the bundle writer lease, so a journal owned by a
    // live other process fails the seal with project_busy instead of being
    // misclassified.
    const auto active = sequence_journals.read_active(request.project_path);
    if (!active.has_value() && active.error().code != ErrorCode::not_found) {
      return foundation::Result<std::vector<SequenceRecoveryInfo>>::failure(
          active.error());
    }
    if (active.has_value() && active.value().admission.has_value()) {
      const auto key = sequence_key(request.project_path);
      bool live = sequence_sessions.contains(key);
      if (!live) {
        std::lock_guard registry_lock(transport_sessions->mutex);
        const auto registered = transport_sessions->sessions.find(key);
        live = registered != transport_sessions->sessions.end() &&
               registered->second.contains(active.value().session_id);
      }
      if (!live) {
        // A reconcile failure (for example the bundle writer lease is held by
        // a live external owner) means only "not sealable now": the listing
        // still returns the sealed candidates it already had, and the next
        // listing retries the seal.
        static_cast<void>(
            projects.reconcile_sequence_recovery(request.project_path));
      }
    }
    const auto listed = sequence_journals.list_recoverable(
        request.project_path);
    if (!listed.has_value()) {
      return foundation::Result<std::vector<SequenceRecoveryInfo>>::failure(
          listed.error());
    }
    std::vector<SequenceRecoveryInfo> result;
    result.reserve(listed.value().size());
    for (const auto& candidate : listed.value()) {
      const auto event_count =
          canonical_recovery_events(candidate.journal).size();
      result.push_back(SequenceRecoveryInfo{
          candidate.journal.session_id,
          candidate.journal.pattern_id,
          candidate.journal.bars,
          candidate.reason,
          event_count,
      });
    }
    return foundation::Result<std::vector<SequenceRecoveryInfo>>::success(
        std::move(result));
  }

  foundation::Result<SequenceMutationResult> apply_sequence_recovery(
      const SequenceRecoveryRequest& request) {
    auto valid = validate_sequence_path_and_session(
        request.project_path, request.session_id);
    if (!valid.has_value() ||
        (request.destination_pattern_id.has_value() &&
         !domain::is_valid_uuid(request.destination_pattern_id->value()))) {
      return foundation::Result<SequenceMutationResult>::failure(
          valid.has_value()
              ? sequence_error(ErrorCode::invalid_argument,
                               "Sequence recovery destination is invalid")
              : valid.error());
    }
    std::lock_guard lock(sequence_mutex);
    if (sequence_sessions.contains(sequence_key(request.project_path))) {
      return foundation::Result<SequenceMutationResult>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "a Sequence session is already active",
                         {{"reason", "sequence_session_active"}}));
    }
    auto lease = acquire_project_writer(request.project_path);
    if (!lease.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(lease.error());
    }
    const auto listed = sequence_journals.list_recoverable(
        request.project_path);
    if (!listed.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(listed.error());
    }
    const auto candidate = std::find_if(
        listed.value().begin(), listed.value().end(), [&request](const auto& item) {
          return item.journal.session_id == request.session_id;
        });
    if (candidate == listed.value().end()) {
      return foundation::Result<SequenceMutationResult>::failure(sequence_error(
          ErrorCode::not_found, "Sequence recovery candidate was not found"));
    }
    // Event-only recovery cannot consume raw candidates or an owned-press
    // checkpoint. A terminal transfer proves all admission input was resolved;
    // admission.completed would be too strict because its flush may be pending.
    const auto& admission = candidate->journal.admission;
    if (admission.has_value() &&
        (admission->transfers.empty() || !admission->transfers.back().terminal)) {
      return foundation::Result<SequenceMutationResult>::failure(sequence_error(
          ErrorCode::invalid_argument,
          "Sequence admission is unresolved; retain the recording until its "
          "input conversion is finalized, or explicitly discard it",
          {{"reason", "sequence_admission_unresolved"},
           {"journal_retained", true}}));
    }
    auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(loaded.error());
    }
    const auto destination = request.destination_pattern_id.value_or(
        candidate->journal.pattern_id);
    const auto pattern = loaded.value().patterns.find(destination);
    if (pattern == loaded.value().patterns.end()) {
      return foundation::Result<SequenceMutationResult>::failure(sequence_error(
          ErrorCode::not_found, "Sequence recovery Pattern was not found"));
    }
    if (!request.destination_pattern_id.has_value() &&
        project_io::sequence_pattern_fingerprint(pattern->second) !=
            candidate->journal.pattern_fingerprint) {
      return foundation::Result<SequenceMutationResult>::failure(sequence_error(
          ErrorCode::revision_conflict,
          "Sequence recovery source Pattern changed",
          {{"reason", "pattern_changed"},
           {"pattern_id", destination.value()}}));
    }
    auto recovered_events = canonical_recovery_events(candidate->journal);
    auto begun = sequence_journals.begin(
        request.project_path,
        request.session_id,
        destination,
        pattern->second.bars,
        project_io::sequence_pattern_fingerprint(pattern->second),
        loaded.value().revision);
    if (!begun.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(begun.error());
    }
    std::uint64_t committed_revision = loaded.value().revision;
    bool replayed = false;
    if (!recovered_events.empty()) {
      const foundation::CommandId command_id{generated_uuid()};
      auto appended = sequence_journals.append_flush(
          request.project_path,
          request.session_id,
          command_id,
          destination,
          loaded.value().revision,
          recovered_events);
      if (!appended.has_value()) {
        (void)sequence_journals.seal(
            request.project_path, request.session_id, "recovery_failed");
        return foundation::Result<SequenceMutationResult>::failure(
            appended.error());
      }
      auto executed = projects.execute_sequence_flush(
          request.project_path,
          project_io::SequenceFlushIdentity{
              request.session_id, appended.value().flush_seq, command_id,
              destination});
      if (!executed.has_value()) {
        (void)sequence_journals.seal(
            request.project_path, request.session_id, "recovery_failed");
        return foundation::Result<SequenceMutationResult>::failure(
            executed.error());
      }
      committed_revision = executed.value().outcome.state.revision;
      replayed = executed.value().outcome.replayed;
    }
    auto stopped = sequence_journals.set_state(
        request.project_path, request.session_id,
        project_io::SequenceSessionState::stopped);
    if (!stopped.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(stopped.error());
    }
    auto removed_active = sequence_journals.remove_active_if_complete(
        request.project_path, request.session_id);
    if (!removed_active.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          removed_active.error());
    }
    auto removed_candidate = storage_platform->remove(candidate->path);
    if (!removed_candidate.has_value()) {
      return foundation::Result<SequenceMutationResult>::failure(
          removed_candidate.error());
    }
    SequenceStatus status;
    status.expected_revision = committed_revision;
    return foundation::Result<SequenceMutationResult>::success(
        SequenceMutationResult{
            status, committed_revision, replayed, std::nullopt});
  }

  foundation::Result<void> discard_sequence_recovery(
      const SequenceRecoveryRequest& request) {
    auto valid = validate_sequence_path_and_session(
        request.project_path, request.session_id);
    if (!valid.has_value() || request.destination_pattern_id.has_value()) {
      return foundation::Result<void>::failure(
          valid.has_value()
              ? sequence_error(ErrorCode::invalid_argument,
                               "Sequence discard request is invalid")
              : valid.error());
    }
    std::lock_guard lock(sequence_mutex);
    auto lease = acquire_project_writer(request.project_path);
    if (!lease.has_value()) {
      return foundation::Result<void>::failure(lease.error());
    }
    const auto listed = sequence_journals.list_recoverable(request.project_path);
    if (!listed.has_value()) {
      return foundation::Result<void>::failure(listed.error());
    }
    const auto candidate = std::find_if(
        listed.value().begin(), listed.value().end(), [&request](const auto& item) {
          return item.journal.session_id == request.session_id;
        });
    if (candidate == listed.value().end()) {
      return foundation::Result<void>::failure(sequence_error(
          ErrorCode::not_found, "Sequence recovery candidate was not found"));
    }
    return storage_platform->remove(candidate->path);
  }

  foundation::Result<void> disarm_sequence_capture(
      const SequenceCaptureDisarmRequest& request) {
    auto valid = validate_sequence_path_and_session(
        request.project_path, request.session_id);
    if (!valid.has_value() || !domain::is_valid_slot(request.slot)) {
      return foundation::Result<void>::failure(
          valid.has_value()
              ? sequence_error(
                    ErrorCode::invalid_argument,
                    "armed Capture disarm target is invalid")
              : valid.error());
    }
    std::lock_guard lock(sequence_mutex);
    const auto found = sequence_sessions.find(sequence_key(request.project_path));
    if (found == sequence_sessions.end() ||
        found->second.session_id != request.session_id) {
      return foundation::Result<void>::failure(sequence_error(
          ErrorCode::invalid_argument,
          "armed Capture disarm owner does not match",
          {{"reason", "sequence_owner_mismatch"}}));
    }
    auto& runtime = found->second;
    if (!runtime.armed_capture_slot.has_value()) {
      return foundation::Result<void>::success();
    }
    if (*runtime.armed_capture_slot != request.slot) {
      return foundation::Result<void>::failure(sequence_error(
          ErrorCode::invalid_argument,
          "armed Capture disarm target does not match",
          {{"reason", "armed_capture_target_mismatch"}}));
    }
    auto disarmed = projects.disarm_sequence_capture(
        request.project_path, request.session_id, request.slot);
    if (!disarmed.has_value()) {
      return foundation::Result<void>::failure(disarmed.error());
    }
    if (disarmed.value().reconciled_commit) {
      runtime.expected_revision = disarmed.value().expected_revision;
      runtime.available_slots |=
          std::uint64_t{1} << slot_index(request.slot);
    }
    runtime.armed_capture_slot.reset();
    return foundation::Result<void>::success();
  }

  void abandon_sequence_sessions() noexcept {
    try {
      std::lock_guard lock(sequence_mutex);
      for (auto& [path_text, runtime] : sequence_sessions) {
        const std::filesystem::path path{path_text};
        finalize_unreleased(runtime, true);
        if (!runtime.pending_events.empty()) {
          const foundation::CommandId command_id{generated_uuid()};
          auto appended = sequence_journals.append_flush(
              path, runtime.session_id, command_id, runtime.pattern_id,
              runtime.expected_revision, runtime.pending_events);
          if (appended.has_value()) {
            (void)sequence_journals.seal(
                path, runtime.session_id, "owner_lost");
          }
        } else {
          (void)sequence_journals.set_state(
              path, runtime.session_id,
              project_io::SequenceSessionState::stopped);
          (void)sequence_journals.remove_active_if_complete(
              path, runtime.session_id);
        }
      }
      sequence_sessions.clear();
    } catch (...) {
    }
  }

  void abandon_performance_sessions() noexcept {
    try {
      std::lock_guard lock(sequence_mutex);
      for (auto &[path_text, runtime] : performance_sessions) {
        const std::filesystem::path path{path_text};
        const auto closed = close_performance_transients(path, runtime);
        if (pattern_launch_acknowledger) {
          pattern_launch_acknowledger->cancel(runtime.session_id);
        }
        if (!closed.has_value()) {
          continue;
        }
        (void)sequence_journals.seal_performance(path, runtime.session_id,
                                                 "owner_lost");
      }
      performance_sessions.clear();
    } catch (...) {
    }
  }

  static nlohmann::json sequence_status_json(const SequenceStatus& status) {
    return {
        {"state", state_name(status.state)},
        {"session_id",
         status.session_id.has_value()
             ? nlohmann::json(status.session_id->value())
             : nlohmann::json(nullptr)},
        {"pattern_id",
         status.pattern_id.has_value()
             ? nlohmann::json(status.pattern_id->value())
             : nlohmann::json(nullptr)},
        {"pending_pattern_id",
         status.pending_pattern_id.has_value()
             ? nlohmann::json(status.pending_pattern_id->value())
             : nlohmann::json(nullptr)},
        {"expected_revision", status.expected_revision},
        {"next_flush_seq", status.next_flush_seq},
        {"pending_event_count", status.pending_event_count},
        {"effective_runtime_frame",
         status.effective_runtime_frame.has_value()
             ? nlohmann::json(*status.effective_runtime_frame)
             : nlohmann::json(nullptr)},
    };
  }

  static nlohmann::json sequence_mutation_json(
      const SequenceMutationResult& result) {
    auto encoded = sequence_status_json(result.status);
    encoded["committed_revision"] = result.committed_revision.has_value()
                                         ? nlohmann::json(*result.committed_revision)
                                         : nlohmann::json(nullptr);
    encoded["replayed"] = result.replayed;
    if (result.committed_pattern_id.has_value()) {
      encoded["committed_pattern_id"] = result.committed_pattern_id->value();
    }
    return encoded;
  }

  nlohmann::json sequence_begin(const nlohmann::json& request) {
    require(
        exact_keys(request,
                   {"operation", "project_path", "session_id", "pattern_id",
                    "expected_revision", "runtime_frame"}) ||
            exact_keys(request,
                       {"operation", "project_path", "session_id", "pattern_id",
                        "expected_revision", "runtime_frame",
                        "armed_capture_slot"}),
        "sequence.record.begin request shape is invalid");
    const auto armed_capture_slot =
        !request.contains("armed_capture_slot") ||
                request.at("armed_capture_slot").is_null()
            ? std::optional<domain::PadSlotId>{}
            : std::optional<domain::PadSlotId>{
                  slot_value(request.at("armed_capture_slot"))};
    const auto result = begin_sequence(SequenceBeginRequest{
        absolute_path_field(request, "project_path"),
        foundation::SequenceSessionId{uuid_field(request, "session_id")},
        foundation::PatternId{uuid_field(request, "pattern_id")},
        unsigned_field(request, "expected_revision"),
        unsigned_field(request, "runtime_frame"),
        armed_capture_slot,
    });
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    return success_envelope(
        sequence_mutation_json(result.value()),
        result.value().status.expected_revision);
  }

  nlohmann::json sequence_event(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "project_path", "session_id", "event"}) &&
            request.at("event").is_object() &&
            exact_keys(request.at("event"),
                       {"slot", "velocity", "runtime_frame",
                        "input_sequence", "pressed"}),
        "sequence.record.event request shape is invalid");
    const auto& event = request.at("event");
    require(event.at("pressed").is_boolean(), "pressed must be a boolean");
    const auto velocity = unsigned_field(event, "velocity", 127);
    require(velocity <= 127, "velocity is out of range");
    const auto result = record_sequence_event(SequenceEventRequest{
        absolute_path_field(request, "project_path"),
        foundation::SequenceSessionId{uuid_field(request, "session_id")},
        SequencePadEvent{
            slot_value(event.at("slot")),
            static_cast<std::uint8_t>(velocity),
            unsigned_field(event, "runtime_frame"),
            unsigned_field(event, "input_sequence"),
            event.at("pressed").get<bool>(),
        },
    });
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    return success_envelope(
        sequence_mutation_json(result.value()),
        result.value().status.expected_revision);
  }

  nlohmann::json sequence_flush(
      const nlohmann::json& request,
      bool stop) {
    require(
        exact_keys(request,
                   {"operation", "project_path", "session_id", "command_id",
                    "runtime_frame"}),
        stop ? "sequence.record.stop request shape is invalid"
             : "sequence.record.flush request shape is invalid");
    const SequenceFlushRequest typed{
        absolute_path_field(request, "project_path"),
        foundation::SequenceSessionId{uuid_field(request, "session_id")},
        foundation::CommandId{uuid_field(request, "command_id")},
        unsigned_field(request, "runtime_frame"),
    };
    const auto result = flush_sequence(typed, stop);
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    return success_envelope(
        sequence_mutation_json(result.value()),
        result.value().committed_revision);
  }

  nlohmann::json sequence_switch(const nlohmann::json& request) {
    require(
        exact_keys(request,
                   {"operation", "project_path", "session_id",
                    "next_pattern_id"}) ||
            exact_keys(request,
                       {"operation", "project_path", "session_id",
                        "next_pattern_id", "runtime_frame"}),
        "sequence.record.switch-request request shape is invalid");
    const auto result = request_sequence_switch(SequenceSwitchRequest{
        absolute_path_field(request, "project_path"),
        foundation::SequenceSessionId{uuid_field(request, "session_id")},
        foundation::PatternId{uuid_field(request, "next_pattern_id")},
        request.contains("runtime_frame")
            ? std::optional<std::uint64_t>{
                  unsigned_field(request, "runtime_frame")}
            : std::nullopt,
    });
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    return success_envelope(
        sequence_mutation_json(result.value()),
        result.value().status.expected_revision);
  }

  nlohmann::json sequence_status(const nlohmann::json& request) const {
    require(exact_keys(request, {"operation", "project_path"}),
            "sequence.record.status request shape is invalid");
    const auto result = query_sequence_status(SequenceStatusRequest{
        absolute_path_field(request, "project_path")});
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    return success_envelope(sequence_status_json(result.value()), std::nullopt);
  }

  nlohmann::json sequence_recovery_list(
      const nlohmann::json& request) {
    require(exact_keys(request, {"operation", "project_path"}),
            "sequence.recovery.list request shape is invalid");
    const auto result = list_sequence_recovery(SequenceStatusRequest{
        absolute_path_field(request, "project_path")});
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    auto candidates = nlohmann::json::array();
    for (const auto& candidate : result.value()) {
      candidates.push_back({
          {"session_id", candidate.session_id.value()},
          {"pattern_id", candidate.pattern_id.value()},
          {"bars", candidate.bars},
          {"reason", candidate.reason},
          {"event_count", candidate.event_count},
      });
    }
    return success_envelope(
        {{"candidates", std::move(candidates)}}, std::nullopt);
  }

  nlohmann::json sequence_recovery_apply(
      const nlohmann::json& request) {
    require(
        exact_keys(request,
                   {"operation", "project_path", "session_id",
                    "destination_pattern_id"}),
        "sequence.recovery.apply request shape is invalid");
    std::optional<foundation::PatternId> destination;
    if (!request.at("destination_pattern_id").is_null()) {
      destination = foundation::PatternId{
          uuid_field(request, "destination_pattern_id")};
    }
    const auto result = apply_sequence_recovery(SequenceRecoveryRequest{
        absolute_path_field(request, "project_path"),
        foundation::SequenceSessionId{uuid_field(request, "session_id")},
        destination,
    });
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    return success_envelope(
        sequence_mutation_json(result.value()),
        result.value().committed_revision);
  }

  nlohmann::json sequence_recovery_discard(
      const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "project_path", "session_id"}),
        "sequence.recovery.discard request shape is invalid");
    const auto session_id = foundation::SequenceSessionId{
        uuid_field(request, "session_id")};
    const auto result = discard_sequence_recovery(SequenceRecoveryRequest{
        absolute_path_field(request, "project_path"), session_id, std::nullopt});
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    return success_envelope(
        {{"session_id", session_id.value()}, {"discarded", true}},
        std::nullopt);
  }

  nlohmann::json dispatch(
      const nlohmann::json& request,
      OperationKind requested_kind) {
    require(request.is_object(), "request must be an object");
    require(all_strings_valid(request), "request contains invalid UTF-8");
    require(request.contains("operation"), "operation is required");
    const auto operation = string_field(request, "operation");
    const auto registered = operations().find(operation);
    require(registered != operations().end(), "operation is unknown");
    require(
        registered->second == requested_kind,
        "operation was sent to the wrong Application method");

    if (operation == "project.create") {
      return project_create(request);
    }
    if (operation == "pattern.create") {
      return pattern_create(request);
    }
    if (operation == "pattern.slot.assign") {
      return pattern_slot_assign(request);
    }
    if (operation == "pattern.slot.clear") {
      return pattern_slot_clear(request);
    }
    if (operation == "pattern.slot.move") {
      return pattern_slot_move(request);
    }
    if (operation == "performance.record.begin") {
      return performance_begin(request);
    }
    if (operation == "performance.record.event") {
      return performance_event(request);
    }
    if (operation == "performance.record.launch-request") {
      return performance_launch_request(request);
    }
    if (operation == "performance.record.flush") {
      return performance_flush(request);
    }
    if (operation == "performance.record.stop") {
      return performance_stop(request);
    }
    if (operation == "performance.save") {
      return performance_save(request);
    }
    if (operation == "performance.discard") {
      return performance_discard(request);
    }
    if (operation == "performance.recovery.apply") {
      return performance_recovery_apply(request);
    }
    if (operation == "performance.recovery.discard") {
      return performance_recovery_discard(request);
    }
    if (operation == "performance.rename") {
      return performance_rename(request);
    }
    if (operation == "performance.delete") {
      return performance_delete(request);
    }
    if (operation == "performance.recording.bind") {
      return performance_recording_bind(request);
    }
    if (operation == "performance.replay.begin") {
      return performance_replay_begin(request);
    }
    if (operation == "performance.replay.stop") {
      return performance_replay_stop(request);
    }
    if (operation == "performance.resample.commit") {
      return performance_resample_commit(request);
    }
    if (operation == "sample.inspect") {
      return sample_inspect(request);
    }
    if (operation == "sample.quota") {
      return sample_quota(request);
    }
    if (operation == "sample.waveform") {
      return sample_waveform(request);
    }
    if (operation == "sample.import.begin") {
      return sample_import_begin(request);
    }
    if (operation == "sample.import.chunk") {
      return sample_import_chunk(request);
    }
    if (operation == "sample.import.commit") {
      return sample_import_commit(request);
    }
    if (operation == "sample.import.abort") {
      return sample_import_abort(request);
    }
    if (operation == "sample.update_pad") {
      return sample_update_pad(request);
    }
    if (operation == "sample.reset_pad") {
      return sample_reset_pad(request);
    }
    if (operation == "asset.import") {
      return asset_import(request);
    }
    if (operation == "pad.assign") {
      return pad_assign(request);
    }
    if (operation == "sequence.record.begin") {
      return sequence_begin(request);
    }
    if (operation == "sequence.record.event") {
      return sequence_event(request);
    }
    if (operation == "sequence.record.flush") {
      return sequence_flush(request, false);
    }
    if (operation == "sequence.record.stop") {
      return sequence_flush(request, true);
    }
    if (operation == "sequence.record.switch-request") {
      return sequence_switch(request);
    }
    if (operation == "sequence.settings.update") {
      return sequence_settings_update(request);
    }
    if (operation == "sequence.recovery.apply") {
      return sequence_recovery_apply(request);
    }
    if (operation == "sequence.recovery.discard") {
      return sequence_recovery_discard(request);
    }
    if (operation == "render.offline") {
      return render_offline(request);
    }
    if (operation == "provider.permissions.configure") {
      return provider_permissions_configure(request);
    }
    if (operation == "provider.select") {
      return provider_select(request);
    }
    if (operation == "candidate.adopt") return candidate_adopt(request);
    if (operation == "candidate.audition") return candidate_audition(request);
    if (operation == "candidate.job.cancel") return candidate_job_cancel(request);
    if (operation == "candidate.set.discard") return candidate_set_discard(request);
    if (operation == "candidate.job.run") return candidate_job_run(request);
    if (operation == "candidate.job.inspect") return candidate_job_inspect(request);
    if (operation == "provider.run") {
      return provider_run(request);
    }
    if (operation == "project.inspect") {
      return project_inspect(request);
    }
    if (operation == "performance.list") {
      return performance_list(request);
    }
    if (operation == "performance.inspect") {
      return performance_inspect(request);
    }
    if (operation == "performance.record.status") {
      return performance_status(request);
    }
    if (operation == "performance.replay.status") {
      return performance_replay_status(request);
    }
    if (operation == "performance.recovery.list") {
      return performance_recovery_list(request);
    }
    if (operation == "sequence.record.status") {
      return sequence_status(request);
    }
    if (operation == "sequence.recovery.list") {
      return sequence_recovery_list(request);
    }
    if (operation == "snapshot.cook") {
      return snapshot_cook(request);
    }
    if (operation == "provider.list") {
      return provider_list(request);
    }
    if (operation == "provider.selected") {
      return provider_selected(request);
    }
    if (operation == "soundset.audition") {
      return soundset_audition(request);
    }
    if (operation == "soundset.catalog.list") {
      return soundset_catalog_list(request);
    }
    if (operation == "soundset.inspect") {
      return soundset_inspect(request);
    }
    if (operation == "soundset.map.preview") {
      return soundset_map_preview(request);
    }
    if (operation == "soundset.install") {
      return soundset_install(request);
    }
    return attempt_inspect(request);
  }

  foundation::Result<std::vector<LocalProjectSummary>>
  list_local_projects() {
    const auto listed =
        bundle_transfers.list_local_projects(workspace_root);
    if (!listed.has_value()) {
      return foundation::Result<std::vector<LocalProjectSummary>>::failure(
          listed.error());
    }
    std::vector<LocalProjectSummary> summaries;
    summaries.reserve(listed.value().size());
    for (const auto& item : listed.value()) {
      summaries.push_back(
          LocalProjectSummary{
              item.project_id,
              item.pattern_id,
              item.revision,
              item.bpm,
              item.asset_count,
              item.assigned_pad_count,
              item.bundle_digest,
          });
    }
    return foundation::Result<std::vector<LocalProjectSummary>>::success(
        std::move(summaries));
  }

  foundation::Result<ProjectBundleImportSession>
  begin_project_bundle_import(
      const ProjectBundleImportBeginRequest& request) {
    if (!domain::is_valid_uuid(request.import_token) ||
        request.index_bytes == 0 ||
        request.index_bytes > kMaximumProjectBundleIndexBytes ||
        !lowercase_sha256(request.index_sha256)) {
      return foundation::Result<ProjectBundleImportSession>::failure(
          invalid_bundle_import_request(
              "Project Bundle import begin request is invalid"));
    }
    const auto begun = bundle_transfers.begin(
        workspace_root,
        request.import_token,
        request.index_bytes,
        request.index_sha256);
    if (!begun.has_value()) {
      return foundation::Result<ProjectBundleImportSession>::failure(
          begun.error());
    }
    return foundation::Result<ProjectBundleImportSession>::success(
        ProjectBundleImportSession{
            begun.value().token,
            begun.value().expected_index_bytes,
        });
  }

  foundation::Result<std::optional<ProjectBundleImportIdentity>>
  append_project_bundle_index(
      std::string_view token,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final) {
    if (!domain::is_valid_uuid(token) || bytes.empty() ||
        bytes.size() > kMaximumProjectBundleChunkBytes) {
      return foundation::Result<
          std::optional<ProjectBundleImportIdentity>>::failure(
          invalid_bundle_import_request(
              "Project Bundle index chunk request is invalid"));
    }
    const auto appended =
        bundle_transfers.append_index(token, offset, bytes, final);
    if (!appended.has_value()) {
      return foundation::Result<
          std::optional<ProjectBundleImportIdentity>>::failure(
          appended.error());
    }
    if (!appended.value().has_value()) {
      return foundation::Result<
          std::optional<ProjectBundleImportIdentity>>::success(
          std::nullopt);
    }
    const auto& identity = *appended.value();
    return foundation::Result<
        std::optional<ProjectBundleImportIdentity>>::success(
        ProjectBundleImportIdentity{
            identity.project_id,
            identity.bundle_digest,
            identity.entry_count,
        });
  }

  foundation::Result<void> append_project_bundle_entry(
      std::string_view token,
      std::uint32_t entry_index,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final) {
    if (!domain::is_valid_uuid(token) ||
        entry_index >= kMaximumProjectBundleEntries ||
        bytes.size() > kMaximumProjectBundleChunkBytes ||
        (bytes.empty() && !final)) {
      return foundation::Result<void>::failure(
          invalid_bundle_import_request(
              "Project Bundle entry chunk request is invalid"));
    }
    return bundle_transfers.append_entry(
        token, entry_index, offset, bytes, final);
  }

  foundation::Result<LocalProjectSummary> commit_project_bundle_import(
      std::string_view token) {
    if (!domain::is_valid_uuid(token)) {
      return foundation::Result<LocalProjectSummary>::failure(
          invalid_bundle_import_request(
              "Project Bundle commit token is invalid"));
    }
    const auto committed = bundle_transfers.commit(token);
    if (!committed.has_value()) {
      return foundation::Result<LocalProjectSummary>::failure(
          committed.error());
    }
    const auto& item = committed.value();
    return foundation::Result<LocalProjectSummary>::success(
        LocalProjectSummary{
            item.project_id,
            item.pattern_id,
            item.revision,
            item.bpm,
            item.asset_count,
            item.assigned_pad_count,
            item.bundle_digest,
        });
  }

  foundation::Result<void> abort_project_bundle_import(
      std::string_view token) {
    if (!domain::is_valid_uuid(token)) {
      return foundation::Result<void>::failure(
          invalid_bundle_import_request(
              "Project Bundle abort token is invalid"));
    }
    return bundle_transfers.abort(token);
  }

  foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
  prepare_runtime_snapshot(const RuntimeSnapshotRequest& request) {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.pattern_id.value())) {
      return foundation::Result<
          std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
          Error{
              ErrorCode::invalid_argument,
              "runtime snapshot request is invalid",
          });
    }
    const auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<
          std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
          loaded.error());
    }
    return cook_project(
        request.project_path,
        loaded.value(),
        request.pattern_id,
        request.limits);
  }

  foundation::Result<cooker::EncodedRuntimeContent> export_runtime_content(
      const RuntimeContentExportRequest& request) {
    using ExportResult = foundation::Result<cooker::EncodedRuntimeContent>;
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.project_id.value()) ||
        !domain::is_valid_uuid(request.pattern_id.value()) ||
        request.live_pad_slots.size() > 64) {
      return ExportResult::failure(
          {ErrorCode::invalid_argument, "runtime content export request is invalid"});
    }
    std::array<std::array<bool, 16>, 4> selected{};
    for (const auto slot : request.live_pad_slots) {
      if (!domain::is_valid_slot(slot) || selected[slot.bank][slot.pad]) {
        return ExportResult::failure(
            {ErrorCode::invalid_argument, "live Pad selection is invalid or duplicated"});
      }
      selected[slot.bank][slot.pad] = true;
    }
    auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) return ExportResult::failure(loaded.error());
    // Freeze one loaded value. Later authoring writes cannot retarget this
    // export; artifact identity verification still guards every source read.
    auto project = std::move(loaded.value());
    if (project.id != request.project_id) {
      return ExportResult::failure(
          {ErrorCode::invalid_argument, "runtime content source Project ID differs"});
    }
    if (project.revision != request.expected_revision) {
      return ExportResult::failure(
          {ErrorCode::revision_conflict, "runtime content source revision differs"});
    }
    const auto pattern = project.patterns.find(request.pattern_id);
    if (pattern == project.patterns.end()) {
      return ExportResult::failure(
          {ErrorCode::not_found, "runtime content source Pattern was not found"});
    }
    for (const auto slot : request.live_pad_slots) {
      if (!project.banks[slot.bank][slot.pad].asset_id.has_value()) {
        return ExportResult::failure(
            {ErrorCode::missing_asset, "selected live Pad has no assigned material"});
      }
    }
    for (const auto& event : pattern->second.events) {
      if (!domain::is_valid_slot(event.slot)) {
        return ExportResult::failure(
            {ErrorCode::invalid_project, "runtime content Pattern Slot is invalid"});
      }
      selected[event.slot.bank][event.slot.pad] = true;
    }
    // Only this detached value is narrowed. Do not save it or mutate Truth.
    for (std::size_t bank = 0; bank < project.banks.size(); ++bank) {
      for (std::size_t pad = 0; pad < project.banks[bank].size(); ++pad) {
        if (!selected[bank][pad]) project.banks[bank][pad].asset_id.reset();
      }
    }
    const auto cooked = cook_project(request.project_path, project, request.pattern_id);
    if (!cooked.has_value()) return ExportResult::failure(cooked.error());
    return cooker::encode_runtime_content(*cooked.value(), request.limits);
  }

  foundation::Result<std::unique_ptr<project_io::ProjectWriterLease>>
  acquire_project_writer(const std::filesystem::path& project_path) {
    if (!valid_host_project_path(project_path)) {
      return foundation::Result<
          std::unique_ptr<project_io::ProjectWriterLease>>::failure(
          Error{
              ErrorCode::invalid_argument,
              "project writer request is invalid",
          });
    }
    auto acquired = storage_platform->acquire_writer(project_path);
    if (acquired.has_value()) {
      return acquired;
    }
    const auto& error = acquired.error();
    if (error.details.is_object() &&
        error.details.value("storage_condition", std::string{}) ==
            project_io::kStorageConditionProjectBusy) {
      return foundation::Result<
          std::unique_ptr<project_io::ProjectWriterLease>>::failure(
          Error{
              ErrorCode::io_error,
              "project writer is already acquired",
              {{"storage_condition", "project_busy"}},
          });
    }
    return foundation::Result<
        std::unique_ptr<project_io::ProjectWriterLease>>::failure(
        Error{
            error.code,
            "project writer could not be acquired",
        });
  }

  foundation::Result<domain::ProjectState> create_initial_project(
      const InitialProjectRequest& request) {
    if (!valid_host_project_path(request.project_path)) {
      return foundation::Result<domain::ProjectState>::failure(
          Error{
              ErrorCode::invalid_argument,
              "initial project request is invalid",
          });
    }
    auto initial = domain::create_project(request.project_id, request.bpm);
    if (!initial.has_value()) {
      return initial;
    }
    const auto pattern_validation =
        validate_initial_pattern(request.initial_pattern);
    if (!pattern_validation.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(
          pattern_validation.error());
    }
    initial.value().patterns.emplace(
        request.initial_pattern.id, request.initial_pattern);
    const auto created = projects.create(request.project_path, initial.value());
    if (!created.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(
          created.error());
    }
    return initial;
  }

  foundation::Result<domain::AppliedCommand> import_artifact_bytes(
      const ArtifactBytesImportRequest& request) {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.meta.command_id.value()) ||
        !domain::is_valid_uuid(request.asset_id.value()) ||
        request.media_type.empty() || !valid_utf8(request.media_type)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "byte-backed artifact import request is invalid",
          });
    }
    auto admitted = admit_non_sequence_authoring(request.project_path);
    if (!admitted.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          admitted.error());
    }
    return projects.import_artifact_bytes(
        request.project_path,
        project_io::ProjectStore::ImportArtifactBytesRequest{
            request.meta,
            request.asset_id,
            request.media_type,
            request.bytes,
        });
  }

  foundation::Result<SampleInspectResult> inspect_sample(
      const SampleInspectRequest& request) const {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_slot(request.slot)) {
      return foundation::Result<SampleInspectResult>::failure(
          invalid_sample_request("Sample inspect request is invalid"));
    }
    const auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<SampleInspectResult>::failure(
          sample_project_load_error(loaded.error()));
    }
    testing::invoke_sample_projection_hook();
    const auto& pad = loaded.value()
                          .banks.at(request.slot.bank)
                          .at(request.slot.pad);
    SampleInspectResult result{
        loaded.value().revision,
        request.slot,
        pad.asset_id,
        pad.playback,
        std::nullopt,
        std::nullopt,
    };
    if (!pad.asset_id.has_value()) {
      return foundation::Result<SampleInspectResult>::success(
          std::move(result));
    }
    const auto asset = loaded.value().assets.find(*pad.asset_id);
    if (asset == loaded.value().assets.end()) {
      return foundation::Result<SampleInspectResult>::failure(
          unavailable_sample());
    }
    const auto bytes =
        projects.read_artifact(request.project_path, asset->second.artifact);
    if (!bytes.has_value()) {
      return foundation::Result<SampleInspectResult>::failure(
          sample_artifact_read_error(bytes.error()));
    }
    const auto metadata = cooker::inspect_wav(bytes.value());
    if (!metadata.has_value()) {
      return foundation::Result<SampleInspectResult>::failure(
          metadata.error());
    }
    result.metadata = metadata.value();
    result.waveform_cache_identity = waveform_cache_key(
        asset->second.artifact,
        canonical_waveform_frames_per_bucket(metadata.value().source_frames));
    return foundation::Result<SampleInspectResult>::success(
        std::move(result));
  }

  foundation::Result<cooker::WaveformEnvelope> query_sample_waveform(
      const SampleWaveformRequest& request,
      std::uint64_t* project_revision = nullptr) {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_slot(request.slot) ||
        request.window.bucket_count == 0 ||
        request.window.bucket_count > 512 ||
        request.window.start_frame >= request.window.end_frame) {
      return foundation::Result<cooker::WaveformEnvelope>::failure(
          invalid_sample_request("Sample waveform request is invalid"));
    }
    const auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<cooker::WaveformEnvelope>::failure(
          sample_project_load_error(loaded.error()));
    }
    if (project_revision != nullptr) {
      *project_revision = loaded.value().revision;
    }
    testing::invoke_sample_projection_hook();
    const auto& pad = loaded.value()
                          .banks.at(request.slot.bank)
                          .at(request.slot.pad);
    if (!pad.asset_id.has_value()) {
      return foundation::Result<cooker::WaveformEnvelope>::failure(
          unavailable_sample());
    }
    const auto asset = loaded.value().assets.find(*pad.asset_id);
    if (asset == loaded.value().assets.end()) {
      return foundation::Result<cooker::WaveformEnvelope>::failure(
          unavailable_sample());
    }
    const auto bytes =
        projects.read_artifact(request.project_path, asset->second.artifact);
    if (!bytes.has_value()) {
      return foundation::Result<cooker::WaveformEnvelope>::failure(
          sample_artifact_read_error(bytes.error()));
    }
    const auto decoded = cooker::decode_wav(bytes.value());
    if (!decoded.has_value()) {
      return foundation::Result<cooker::WaveformEnvelope>::failure(
          decoded.error());
    }
    const auto source_frames = static_cast<std::uint64_t>(
        decoded.value()->interleaved.size() / decoded.value()->channels);
    if (request.window.end_frame > source_frames) {
      return foundation::Result<cooker::WaveformEnvelope>::failure(
          invalid_sample_request(
              "Sample waveform request is outside source bounds"));
    }
    const cooker::WavMetadata metadata{
        decoded.value()->sample_rate,
        decoded.value()->channels,
        source_frames,
    };
    const auto requested_frames_per_bucket = ceiling_divide(
        request.window.end_frame - request.window.start_frame,
        request.window.bucket_count);
    const auto full_bucket_count =
        ceiling_divide(source_frames, requested_frames_per_bucket);
    const auto cache_frames_per_bucket =
        ceiling_divide(source_frames, full_bucket_count);
    const auto key = waveform_cache_key(
        asset->second.artifact, cache_frames_per_bucket);
    bool rebuild_cache = false;
    if (full_bucket_count <= 512U) {
      const auto cached = waveform_cache.read(key);
      if (cached.has_value() && cached.value().has_value()) {
        const auto decoded_cache = decode_waveform_cache(
            *cached.value(), metadata, cache_frames_per_bucket);
        if (decoded_cache.has_value()) {
          const auto window = cached_waveform_window(
              *decoded_cache, request.window, cache_frames_per_bucket);
          if (window.has_value()) {
            return foundation::Result<cooker::WaveformEnvelope>::success(
                *window);
          }
        } else {
          (void)waveform_cache.remove(key);
          rebuild_cache = true;
        }
      } else if (cached.has_value()) {
        rebuild_cache = true;
      }
    }
    const auto computed =
        cooker::waveform_envelope(*decoded.value(), request.window);
    if (!computed.has_value()) {
      return computed;
    }
    if (full_bucket_count <= 512U && rebuild_cache) {
      const auto full = cooker::waveform_envelope(
          *decoded.value(),
          cooker::WaveformRequest{
              0,
              source_frames,
              static_cast<std::uint32_t>(full_bucket_count),
          });
      if (full.has_value()) {
        const auto encoded =
            encode_waveform_cache(full.value(), cache_frames_per_bucket);
        (void)waveform_cache.write(key, encoded);
      }
    }
    return computed;
  }

  struct DecodedAudio {
    std::uint32_t sample_rate;
    std::uint16_t channels;
    std::uint64_t source_frames;
    PreparedQuotaUsage prepared;
  };

  // One decode answers both questions the Sound Set path asks: is this S8-D6
  // audio at all, and how much prepared PCM would it cost. The refusal is the
  // project-cooker WAV reader's own UNSUPPORTED_AUDIO; nothing here re-decides
  // the format.
  foundation::Result<DecodedAudio> measure_decoded_audio(
      std::span<const std::byte> bytes) const {
    const auto decoded = cooker::decode_wav(bytes);
    if (!decoded.has_value()) {
      return foundation::Result<DecodedAudio>::failure(decoded.error());
    }
    const auto source_frames = static_cast<std::uint64_t>(
        decoded.value()->interleaved.size() / decoded.value()->channels);
    auto frames = source_frames;
    if (decoded.value()->sample_rate != 48'000) {
      const auto prepared = cooker::prepare_runtime_pcm(*decoded.value());
      if (!prepared.has_value() || prepared.value()->channels == 0 ||
          prepared.value()->interleaved.size() %
                  prepared.value()->channels !=
              0) {
        return foundation::Result<DecodedAudio>::failure(
            prepared.has_value()
                ? Error{
                      ErrorCode::cook_failed,
                      "prepared Sample PCM shape is invalid",
                  }
                : prepared.error());
      }
      frames = static_cast<std::uint64_t>(
          prepared.value()->interleaved.size() /
          prepared.value()->channels);
    }
    const auto prepared_bytes = audio::checked_mono_float_bytes(frames);
    if (!prepared_bytes.has_value()) {
      return foundation::Result<DecodedAudio>::failure(Error{
          ErrorCode::invalid_argument,
          "prepared Sample PCM byte length overflowed",
      });
    }
    return foundation::Result<DecodedAudio>::success(
        DecodedAudio{
            decoded.value()->sample_rate,
            decoded.value()->channels,
            source_frames,
            PreparedQuotaUsage{*prepared_bytes, frames},
        });
  }

  foundation::Result<PreparedQuotaUsage> measure_prepared_quota(
      std::span<const std::byte> bytes) const {
    const auto measured = measure_decoded_audio(bytes);
    if (!measured.has_value()) {
      return foundation::Result<PreparedQuotaUsage>::failure(
          measured.error());
    }
    return foundation::Result<PreparedQuotaUsage>::success(
        measured.value().prepared);
  }

  struct BankQuotaLedger {
    std::array<std::uint64_t, 4> bank_used_bytes{};
    std::uint64_t project_used_bytes = 0;
    std::vector<SampleQuotaConsumed> consumed;
  };

  // The prepared-PCM ledger of the whole Project with a set of target Pads
  // removed. `excluded_pads` is a bitmask over `target_bank`: those are the
  // Pads a caller is about to write, so whatever they hold now is not part of
  // what the write has to fit into. Every other assigned Pad counts once per
  // Pad, so one Artifact on two Pads is two residencies — the 2026-08-28
  // accounting amendment, and the rule S11-D8 reuses for an install.
  foundation::Result<BankQuotaLedger> compute_bank_ledger(
      const std::filesystem::path& project_path,
      const domain::ProjectState& project,
      std::uint8_t target_bank,
      std::uint16_t excluded_pads) const {
    BankQuotaLedger ledger;
    std::map<std::string, PreparedQuotaUsage> cached_usage;

    for (std::uint8_t bank = 0; bank < project.banks.size(); ++bank) {
      for (std::uint8_t pad = 0;
           pad < project.banks.at(bank).size();
           ++pad) {
        const domain::PadSlotId slot{bank, pad};
        const auto& assignment = project.banks.at(bank).at(pad);
        if (!assignment.asset_id.has_value()) {
          continue;
        }
        const auto asset = domain::resolve_slot_asset(project, slot);
        if (!asset.has_value()) {
          return foundation::Result<BankQuotaLedger>::failure(
              unavailable_sample());
        }
        auto usage = cached_usage.find(asset->artifact.sha256);
        if (usage == cached_usage.end()) {
          const auto artifact_bytes =
              projects.read_artifact(project_path, asset->artifact);
          if (!artifact_bytes.has_value()) {
            return foundation::Result<BankQuotaLedger>::failure(
                sample_artifact_read_error(artifact_bytes.error()));
          }
          const auto measured = measure_prepared_quota(artifact_bytes.value());
          if (!measured.has_value()) {
            return foundation::Result<BankQuotaLedger>::failure(
                measured.error());
          }
          usage = cached_usage.emplace(
              asset->artifact.sha256, measured.value()).first;
        }
        if (bank == target_bank) {
          ledger.consumed.push_back(SampleQuotaConsumed{
              slot,
              usage->second.bytes,
              usage->second.frames,
          });
          if ((excluded_pads & (std::uint16_t{1} << pad)) != 0U) {
            continue;
          }
        }
        const auto next_bank = audio::checked_runtime_byte_sum(
            ledger.bank_used_bytes.at(bank), usage->second.bytes);
        const auto next_project = audio::checked_runtime_byte_sum(
            ledger.project_used_bytes, usage->second.bytes);
        if (!next_bank.has_value() || !next_project.has_value()) {
          return foundation::Result<BankQuotaLedger>::failure(Error{
              ErrorCode::invalid_project,
              "Sample quota ledger overflowed",
          });
        }
        ledger.bank_used_bytes.at(bank) = *next_bank;
        ledger.project_used_bytes = *next_project;
      }
    }
    return foundation::Result<BankQuotaLedger>::success(std::move(ledger));
  }

  foundation::Result<SampleQuotaComputation> compute_sample_quota(
      const std::filesystem::path& project_path,
      const domain::ProjectState& project,
      domain::PadSlotId target) const {
    if (!sample_limits.has_value()) {
      return foundation::Result<SampleQuotaComputation>::failure(
          invalid_sample_request("Sample quota is unavailable"));
    }
    auto computed = compute_bank_ledger(
        project_path,
        project,
        target.bank,
        static_cast<std::uint16_t>(std::uint16_t{1} << target.pad));
    if (!computed.has_value()) {
      return foundation::Result<SampleQuotaComputation>::failure(
          computed.error());
    }
    const auto bank_used_bytes = computed.value().bank_used_bytes;
    const auto project_used_bytes = computed.value().project_used_bytes;
    auto consumed = std::move(computed.value().consumed);

    const auto assessment = audio::assess_runtime_quota(
        bank_used_bytes.at(target.bank),
        project_used_bytes,
        0,
        *sample_limits);
    if (!assessment.has_value()) {
      return foundation::Result<SampleQuotaComputation>::failure(Error{
          ErrorCode::invalid_project,
          "Project prepared-PCM quota ledger exceeds configured limits",
      });
    }
    const auto effective_remaining_bytes = std::min(
        assessment->user_bank_remaining_bytes,
        assessment->generation_remaining_bytes);
    return foundation::Result<SampleQuotaComputation>::success(
        SampleQuotaComputation{
            SampleQuotaResult{
                project.revision,
                target,
                sample_limits->maximum_user_bank_bytes,
                bank_used_bytes.at(target.bank),
                assessment->user_bank_remaining_bytes,
                sample_limits->maximum_generation_bytes,
                project_used_bytes,
                assessment->generation_remaining_bytes,
                effective_remaining_bytes,
                effective_remaining_bytes / sizeof(float),
                std::move(consumed),
            },
            bank_used_bytes,
        });
  }

  foundation::Result<SampleQuotaResult> query_sample_quota(
      const SampleQuotaRequest& request) const {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_slot(request.slot)) {
      return foundation::Result<SampleQuotaResult>::failure(
          invalid_sample_request("Sample quota request is invalid"));
    }
    const auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<SampleQuotaResult>::failure(
          sample_project_load_error(loaded.error()));
    }
    testing::invoke_sample_projection_hook();
    auto computed = compute_sample_quota(
        request.project_path, loaded.value(), request.slot);
    if (!computed.has_value()) {
      return foundation::Result<SampleQuotaResult>::failure(
          computed.error());
    }
    return foundation::Result<SampleQuotaResult>::success(
        std::move(computed.value().result));
  }

  foundation::Result<SampleImportSession> begin_sample_import(
      const SampleImportBeginRequest& request) {
    if (!sample_limits.has_value() ||
        !domain::is_valid_uuid(request.import_token) ||
        !valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.meta.command_id.value()) ||
        !domain::is_valid_slot(request.slot) ||
        !domain::is_valid_uuid(request.asset_id.value()) ||
        (request.sequence_session_id.has_value() &&
         !domain::is_valid_uuid(request.sequence_session_id->value())) ||
        request.byte_length == 0 ||
        !sample_limits->allows_artifact_bytes(request.byte_length)) {
      return foundation::Result<SampleImportSession>::failure(
          invalid_sample_request("Sample import begin request is invalid"));
    }
    if (request.sequence_session_id.has_value()) {
      std::lock_guard sequence_lock(sequence_mutex);
      const auto found = sequence_sessions.find(sequence_key(request.project_path));
      if (found == sequence_sessions.end() ||
          found->second.session_id != *request.sequence_session_id) {
        return foundation::Result<SampleImportSession>::failure(
            sequence_error(
                ErrorCode::invalid_argument,
                "armed Capture commit owner does not match",
                {{"reason", "sequence_owner_mismatch"}}));
      }
      if (!found->second.armed_capture_slot.has_value()) {
        return foundation::Result<SampleImportSession>::failure(
            sequence_error(
                ErrorCode::invalid_argument,
                "armed Capture commit has no active target",
                {{"reason", "armed_capture_not_armed"}}));
      }
      if (*found->second.armed_capture_slot != request.slot ||
          found->second.expected_revision != request.meta.expected_revision) {
        return foundation::Result<SampleImportSession>::failure(
            sequence_error(
                ErrorCode::invalid_argument,
                "armed Capture commit target does not match",
                {{"reason", "armed_capture_target_mismatch"}}));
      }
    }
    std::lock_guard lock(sample_mutex);
    if (sample_imports.size() >= kMaximumSampleImportSessions) {
      return foundation::Result<SampleImportSession>::failure(Error{
          ErrorCode::invalid_argument,
          "Sample import session limit reached",
          {{"resource", "sample_import_sessions"},
           {"observed", sample_imports.size() + 1U},
           {"limit", kMaximumSampleImportSessions}},
      });
    }
    if (used_sample_import_tokens.contains(request.import_token)) {
      return foundation::Result<SampleImportSession>::failure(
          invalid_sample_request("Sample import token was already used"));
    }
    const auto root = workspace_root / ".lmdj-host/sample-import-staging";
    const auto ensured = storage_platform->ensure_directory(root);
    if (!ensured.has_value()) {
      return foundation::Result<SampleImportSession>::failure(
          sample_storage_error(
              ensured.error(), "Sample staging could not be created"));
    }
    const auto validated = storage_platform->validate_managed_tree(root);
    if (!validated.has_value()) {
      return foundation::Result<SampleImportSession>::failure(
          sample_storage_error(
              validated.error(), "Sample staging tree is invalid"));
    }
    const auto directory = root / request.import_token;
    const auto marker_path = directory / "state.json";
    const auto payload_path = directory / "payload.wav";
    auto lease = storage_platform->acquire_writer(directory);
    if (!lease.has_value()) {
      return foundation::Result<SampleImportSession>::failure(
          sample_storage_error(
              lease.error(), "Sample staging writer could not be acquired"));
    }
    const auto present = storage_platform->exists(directory);
    if (!present.has_value()) {
      return foundation::Result<SampleImportSession>::failure(
          sample_storage_error(
              present.error(),
              "Sample staging could not be inspected"));
    }
    if (present.value()) {
      return foundation::Result<SampleImportSession>::failure(
          invalid_sample_request("Sample import token was already used"));
    }
    const auto directory_created =
        storage_platform->ensure_directory(directory);
    if (!directory_created.has_value()) {
      return foundation::Result<SampleImportSession>::failure(
          sample_storage_error(
              directory_created.error(),
              "Sample staging could not be created"));
    }
    const auto created_at = std::chrono::duration_cast<std::chrono::seconds>(
                                std::chrono::system_clock::now()
                                    .time_since_epoch())
                                .count();
    const auto marker_text = nlohmann::json{
        {"contract", kSampleStagingContract},
        {"created_unix_seconds", created_at},
        {"state", "incomplete"},
        {"token", request.import_token},
    }.dump();
    auto created = storage_platform->create_immutable(
        marker_path,
        std::as_bytes(std::span<const char>{
            marker_text.data(), marker_text.size()}));
    if (created.has_value()) {
      created = storage_platform->create_immutable(payload_path, {});
    }
    if (!created.has_value()) {
      lease.value().reset();
      (void)remove_sample_staging(storage_platform, directory);
      return foundation::Result<SampleImportSession>::failure(
          sample_storage_error(
              created.error(), "Sample staging could not be created"));
    }
    if (used_sample_import_tokens.size() >=
        kMaximumRememberedSampleImportTokens) {
      used_sample_import_tokens.erase(
          remembered_sample_import_tokens.front());
      remembered_sample_import_tokens.pop_front();
    }
    used_sample_import_tokens.insert(request.import_token);
    remembered_sample_import_tokens.push_back(request.import_token);
    sample_imports.emplace(
        request.import_token,
        SampleImportState{
            request,
            directory,
            payload_path,
            0,
            false,
            std::move(lease.value()),
        });
    return foundation::Result<SampleImportSession>::success(
        SampleImportSession{request.import_token, request.byte_length});
  }

  foundation::Result<void> append_sample_import(
      std::string_view token,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final) {
    if (!domain::is_valid_uuid(token)) {
      return foundation::Result<void>::failure(
          invalid_sample_request("Sample import chunk request is invalid"));
    }
    std::lock_guard lock(sample_mutex);
    const auto found = sample_imports.find(std::string{token});
    if (found == sample_imports.end()) {
      return foundation::Result<void>::failure(
          invalid_sample_request("Sample import chunk request is invalid"));
    }
    if (bytes.size() > kMaximumSampleImportChunkBytes ||
        (bytes.empty() && !final) || found->second.finalized ||
        offset != found->second.received_bytes ||
        bytes.size() > found->second.request.byte_length -
                           found->second.received_bytes ||
        (final && found->second.received_bytes + bytes.size() !=
                      found->second.request.byte_length)) {
      found->second.lease.reset();
      const auto removed = remove_sample_staging(
          storage_platform, found->second.directory);
      sample_imports.erase(found);
      if (!removed.has_value()) {
        return foundation::Result<void>::failure(sample_storage_error(
            removed.error(), "Sample staging could not be removed"));
      }
      return foundation::Result<void>::failure(
          invalid_sample_request("Sample import chunk request is invalid"));
    }
    const auto appended = storage_platform->append_durable(
        found->second.payload_path, offset, bytes);
    if (!appended.has_value()) {
      found->second.lease.reset();
      (void)remove_sample_staging(storage_platform, found->second.directory);
      sample_imports.erase(found);
      return foundation::Result<void>::failure(sample_storage_error(
          appended.error(), "Sample staging append failed"));
    }
    found->second.received_bytes += bytes.size();
    found->second.finalized = final;
    return foundation::Result<void>::success();
  }

  foundation::Result<SampleMutationResult> commit_sample_import(
      std::string_view token,
      std::uint64_t* project_revision = nullptr) {
    if (!domain::is_valid_uuid(token)) {
      return foundation::Result<SampleMutationResult>::failure(
          invalid_sample_request("Sample import commit token is invalid"));
    }
    std::optional<SampleImportState> owned;
    {
      std::lock_guard lock(sample_mutex);
      const auto found = sample_imports.find(std::string{token});
      if (found == sample_imports.end()) {
        return foundation::Result<SampleMutationResult>::failure(
            invalid_sample_request("Sample import session does not exist"));
      }
      owned.emplace(std::move(found->second));
      sample_imports.erase(found);
    }
    auto state = std::move(*owned);
    std::optional<SequenceAuthoringAdmission> ordinary_admission;
    std::unique_lock<std::mutex> capture_admission;
    SequenceRuntime* active_sequence = nullptr;
    if (state.request.sequence_session_id.has_value()) {
      capture_admission = std::unique_lock(sequence_mutex);
      const auto found = sequence_sessions.find(
          sequence_key(state.request.project_path));
      if (found == sequence_sessions.end() ||
          found->second.session_id != *state.request.sequence_session_id) {
        return foundation::Result<SampleMutationResult>::failure(
            sequence_error(
                ErrorCode::invalid_argument,
                "armed Capture commit owner does not match",
                {{"reason", "sequence_owner_mismatch"}}));
      }
      if (!found->second.armed_capture_slot.has_value()) {
        return foundation::Result<SampleMutationResult>::failure(
            sequence_error(
                ErrorCode::invalid_argument,
                "armed Capture commit has no active target",
                {{"reason", "armed_capture_not_armed"}}));
      }
      if (*found->second.armed_capture_slot != state.request.slot ||
          found->second.expected_revision !=
              state.request.meta.expected_revision) {
        return foundation::Result<SampleMutationResult>::failure(
            sequence_error(
                ErrorCode::invalid_argument,
                "armed Capture commit target does not match",
                {{"reason", "armed_capture_target_mismatch"}}));
      }
      active_sequence = &found->second;
    } else {
      auto admitted = admit_non_sequence_authoring(state.request.project_path);
      if (!admitted.has_value()) {
        return foundation::Result<SampleMutationResult>::failure(
            admitted.error());
      }
      ordinary_admission.emplace(std::move(admitted.value()));
    }
    SampleStagingCleanup cleanup{
        storage_platform,
        state.directory,
        std::move(state.lease),
    };
    if (!state.finalized || state.received_bytes != state.request.byte_length) {
      return foundation::Result<SampleMutationResult>::failure(
          invalid_sample_request("Sample import is incomplete"));
    }
    const auto bytes = storage_platform->read_complete(state.payload_path);
    if (!bytes.has_value() || bytes.value().size() != state.request.byte_length) {
      return foundation::Result<SampleMutationResult>::failure(
          sample_storage_error(
              bytes.has_value()
                  ? invalid_sample_request("Sample staging length changed")
                  : bytes.error(),
              "Sample staging could not be read"));
    }
    const auto loaded = projects.load(state.request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(
          sample_project_load_error(loaded.error()));
    }
    if (loaded.value().revision == state.request.meta.expected_revision) {
      const auto candidate = measure_prepared_quota(bytes.value());
      if (!candidate.has_value()) {
        return foundation::Result<SampleMutationResult>::failure(
            candidate.error());
      }
      const auto quota = compute_sample_quota(
          state.request.project_path,
          loaded.value(),
          state.request.slot);
      if (!quota.has_value()) {
        return foundation::Result<SampleMutationResult>::failure(
            quota.error());
      }
      const auto assessment = audio::assess_runtime_quota(
          quota.value().result.bank_used_bytes,
          quota.value().result.project_used_bytes,
          candidate.value().bytes,
          *sample_limits);
      if (!assessment.has_value()) {
        return foundation::Result<SampleMutationResult>::failure(Error{
            ErrorCode::invalid_project,
            "Sample quota ledger exceeds configured limits",
        });
      }
      if (assessment->constraint ==
          audio::RuntimeQuotaConstraint::user_bank) {
        std::vector<nlohmann::json> consumed;
        consumed.reserve(quota.value().result.consumed.size());
        for (const auto& entry : quota.value().result.consumed) {
          consumed.push_back({
              {"pad", entry.slot.pad},
              {"prepared_bytes", entry.prepared_bytes},
              {"prepared_frames", entry.prepared_frames},
          });
        }
        return foundation::Result<SampleMutationResult>::failure(
            runtime_bank_quota_error(
                state.request.slot,
                candidate.value().bytes,
                candidate.value().frames,
                assessment->user_bank_remaining_bytes,
                sample_limits->maximum_user_bank_bytes,
                consumed));
      }
      if (assessment->constraint ==
          audio::RuntimeQuotaConstraint::generation) {
        return foundation::Result<SampleMutationResult>::failure(
            runtime_project_quota_error(
                candidate.value().bytes,
                candidate.value().frames,
                quota.value().result.project_used_bytes,
                assessment->generation_remaining_bytes,
                sample_limits->maximum_generation_bytes,
                quota.value().bank_used_bytes));
      }
    }
    const auto committed = projects.import_assign_sample_bytes(
        state.request.project_path,
        project_io::ProjectStore::ImportAssignSampleBytesRequest{
            state.request.meta,
            state.request.slot,
            state.request.asset_id,
            "audio/wav",
            bytes.value(),
            state.request.sequence_session_id,
        });
    if (!committed.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(
          committed.error());
    }
    if (project_revision != nullptr) {
      *project_revision = committed.value().state.revision;
    }
    if (active_sequence != nullptr) {
      active_sequence->expected_revision = committed.value().state.revision;
      active_sequence->available_slots |=
          std::uint64_t{1} << slot_index(state.request.slot);
      active_sequence->armed_capture_slot.reset();
    }
    return foundation::Result<SampleMutationResult>::success(
        SampleMutationResult{
            committed.value().event.at("revision").get<std::uint64_t>(),
            true,
        });
  }

  foundation::Result<void> abort_sample_import(std::string_view token) {
    if (!domain::is_valid_uuid(token)) {
      return foundation::Result<void>::failure(
          invalid_sample_request("Sample import abort token is invalid"));
    }
    std::lock_guard lock(sample_mutex);
    const auto found = sample_imports.find(std::string{token});
    if (found == sample_imports.end()) {
      return foundation::Result<void>::failure(
          invalid_sample_request("Sample import session does not exist"));
    }
    found->second.lease.reset();
    const auto removed =
        remove_sample_staging(storage_platform, found->second.directory);
    sample_imports.erase(found);
    if (!removed.has_value()) {
      return foundation::Result<void>::failure(sample_storage_error(
          removed.error(), "Sample staging could not be removed"));
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<SampleMutationResult> update_sample_pad(
      const SampleUpdateRequest& request,
      std::uint64_t* project_revision = nullptr) {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.meta.command_id.value()) ||
        !domain::is_valid_slot(request.slot)) {
      return foundation::Result<SampleMutationResult>::failure(
          invalid_sample_request("Sample update request is invalid"));
    }
    auto admitted = admit_non_sequence_authoring(request.project_path);
    if (!admitted.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(
          admitted.error());
    }
    const auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(
          sample_project_load_error(loaded.error()));
    }
    testing::invoke_sample_projection_hook();
    if (loaded.value().revision == request.meta.expected_revision) {
      const auto& pad = loaded.value()
                            .banks.at(request.slot.bank)
                            .at(request.slot.pad);
      if (!pad.asset_id.has_value()) {
        return foundation::Result<SampleMutationResult>::failure(
            unavailable_sample());
      }
      const auto asset = loaded.value().assets.find(*pad.asset_id);
      if (asset == loaded.value().assets.end()) {
        return foundation::Result<SampleMutationResult>::failure(
            unavailable_sample());
      }
      const auto bytes =
          projects.read_artifact(request.project_path, asset->second.artifact);
      if (!bytes.has_value()) {
        return foundation::Result<SampleMutationResult>::failure(
            sample_artifact_read_error(bytes.error()));
      }
      const auto metadata = cooker::inspect_wav(bytes.value());
      if (!metadata.has_value()) {
        return foundation::Result<SampleMutationResult>::failure(
            metadata.error());
      }
      const auto& playback = request.playback;
      if (!valid_trigger_mode(playback.trigger_mode) ||
          playback.gain_millidb < -60'000 ||
          playback.gain_millidb > 6'000 ||
          playback.trim_start_frame >= metadata.value().source_frames ||
          (playback.trim_end_frame.has_value() &&
           (*playback.trim_end_frame <= playback.trim_start_frame ||
            *playback.trim_end_frame > metadata.value().source_frames))) {
        return foundation::Result<SampleMutationResult>::failure(
            invalid_sample_request("Sample playback selection is invalid"));
      }
    }
    const auto updated = projects.execute(
        request.project_path,
        domain::UpdatePadPlayback{
            request.meta,
            request.slot,
            request.playback,
        });
    if (!updated.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(updated.error());
    }
    if (project_revision != nullptr) {
      *project_revision = updated.value().state.revision;
    }
    const bool runtime_required = updated.value()
                                      .state.banks.at(request.slot.bank)
                                      .at(request.slot.pad)
                                      .asset_id.has_value();
    return foundation::Result<SampleMutationResult>::success(
        SampleMutationResult{
            updated.value().event.at("revision").get<std::uint64_t>(),
            runtime_required,
        });
  }

  foundation::Result<SampleMutationResult> reset_sample_pad(
      const SampleResetRequest& request,
      std::uint64_t* project_revision = nullptr) {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.meta.command_id.value()) ||
        !domain::is_valid_slot(request.slot)) {
      return foundation::Result<SampleMutationResult>::failure(
          invalid_sample_request("Sample reset request is invalid"));
    }
    auto admitted = admit_non_sequence_authoring(request.project_path);
    if (!admitted.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(
          admitted.error());
    }
    const auto reset = projects.execute(
        request.project_path,
        domain::ResetPadPlayback{request.meta, request.slot});
    if (!reset.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(reset.error());
    }
    if (project_revision != nullptr) {
      *project_revision = reset.value().state.revision;
    }
    const bool runtime_required = reset.value()
                                      .state.banks.at(request.slot.bank)
                                      .at(request.slot.pad)
                                      .asset_id.has_value();
    return foundation::Result<SampleMutationResult>::success(
        SampleMutationResult{
            reset.value().event.at("revision").get<std::uint64_t>(),
            runtime_required,
        });
  }

  nlohmann::json sample_inspect(const nlohmann::json& request) const {
    require(
        exact_keys(request, {"operation", "project_path", "slot"}),
        "sample.inspect request shape is invalid");
    const auto inspected = inspect_sample(SampleInspectRequest{
        absolute_path_field(request, "project_path"),
        slot_value(request.at("slot")),
    });
    if (!inspected.has_value()) {
      return sample_error_envelope(inspected.error());
    }
    const auto& result = inspected.value();
    return success_envelope(
        {
            {"project_revision", result.project_revision},
            {"slot", slot_json(result.slot)},
            {"asset_id",
             result.asset_id.has_value()
                 ? nlohmann::json(result.asset_id->value())
                 : nlohmann::json(nullptr)},
            {"playback", playback_json(result.playback)},
            {"metadata",
             result.metadata.has_value()
                 ? wav_metadata_json(*result.metadata)
                 : nlohmann::json(nullptr)},
            {"waveform_cache_identity",
             result.waveform_cache_identity.has_value()
                 ? nlohmann::json(*result.waveform_cache_identity)
                 : nlohmann::json(nullptr)},
        },
        result.project_revision);
  }

  nlohmann::json sample_quota(const nlohmann::json& request) const {
    require(
        exact_keys(request, {"operation", "project_path", "slot"}),
        "sample.quota request shape is invalid");
    const auto quota = query_sample_quota(SampleQuotaRequest{
        absolute_path_field(request, "project_path"),
        slot_value(request.at("slot")),
    });
    if (!quota.has_value()) {
      return sample_error_envelope(quota.error());
    }
    auto consumed = nlohmann::json::array();
    for (const auto& entry : quota.value().consumed) {
      consumed.push_back({
          {"slot", slot_json(entry.slot)},
          {"prepared_bytes", entry.prepared_bytes},
          {"prepared_frames", entry.prepared_frames},
      });
    }
    const auto& result = quota.value();
    return success_envelope(
        {
            {"project_revision", result.project_revision},
            {"slot", slot_json(result.slot)},
            {"bank_quota_bytes", result.bank_quota_bytes},
            {"bank_used_bytes", result.bank_used_bytes},
            {"bank_remaining_bytes", result.bank_remaining_bytes},
            {"project_quota_bytes", result.project_quota_bytes},
            {"project_used_bytes", result.project_used_bytes},
            {"project_remaining_bytes", result.project_remaining_bytes},
            {"effective_remaining_bytes",
             result.effective_remaining_bytes},
            {"effective_remaining_frames",
             result.effective_remaining_frames},
            {"consumed", std::move(consumed)},
        },
        result.project_revision);
  }

  nlohmann::json sample_waveform(const nlohmann::json& request) {
    require(
        exact_keys(
            request, {"operation", "project_path", "slot", "window"}),
        "sample.waveform request shape is invalid");
    const SampleWaveformRequest parsed{
        absolute_path_field(request, "project_path"),
        slot_value(request.at("slot")),
        waveform_request_value(request.at("window")),
    };
    std::uint64_t project_revision = 0;
    const auto waveform = query_sample_waveform(parsed, &project_revision);
    if (!waveform.has_value()) {
      return sample_error_envelope(waveform.error());
    }
    auto buckets = nlohmann::json::array();
    for (const auto& bucket : waveform.value().buckets) {
      buckets.push_back(peak_bucket_json(bucket));
    }
    return success_envelope(
        {
            {"metadata", wav_metadata_json(waveform.value().metadata)},
            {"algorithm_version", waveform.value().algorithm_version},
            {"buckets", std::move(buckets)},
        },
        project_revision);
  }

  nlohmann::json sample_import_begin(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation",
             "import_token",
             "project_path",
             "command_id",
             "expected_revision",
             "slot",
             "asset_id",
             "byte_length"}),
        "sample.import.begin request shape is invalid");
    const auto begun = begin_sample_import(SampleImportBeginRequest{
        uuid_field(request, "import_token"),
        absolute_path_field(request, "project_path"),
        domain::CommandMeta{
            foundation::CommandId{uuid_field(request, "command_id")},
            unsigned_field(request, "expected_revision"),
        },
        slot_value(request.at("slot")),
        foundation::AssetId{uuid_field(request, "asset_id")},
        unsigned_field(request, "byte_length", 1'048'576U),
        std::nullopt,
    });
    if (!begun.has_value()) {
      return sample_error_envelope(begun.error());
    }
    return success_envelope(
        {{"token", begun.value().token},
         {"expected_bytes", begun.value().expected_bytes}},
        std::nullopt);
  }

  nlohmann::json sample_import_chunk(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "import_token", "offset", "final", "sidecar"}),
        "sample.import.chunk request shape is invalid");
    (void)uuid_field(request, "import_token");
    (void)unsigned_field(request, "offset");
    require(request.at("final").is_boolean(), "final must be a boolean");
    const auto& sidecar = request.at("sidecar");
    require(
        exact_keys(sidecar, {"sidecar_bytes", "sidecar_sha256"}),
        "sample.import.chunk sidecar shape is invalid");
    (void)unsigned_field(sidecar, "sidecar_bytes", 1'048'576U);
    const auto& hash = string_field(sidecar, "sidecar_sha256");
    require(lowercase_sha256(hash), "sidecar_sha256 is invalid");
    return sample_error_envelope(invalid_sample_request(
        "Sample import binary sidecar is unavailable on this bridge"));
  }

  nlohmann::json sample_import_commit(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "import_token"}),
        "sample.import.commit request shape is invalid");
    std::uint64_t project_revision = 0;
    const auto committed = commit_sample_import(
        uuid_field(request, "import_token"), &project_revision);
    if (!committed.has_value()) {
      return sample_error_envelope(committed.error());
    }
    return success_envelope(
        {{"committed_revision", committed.value().committed_revision},
         {"runtime_prepare_required",
          committed.value().runtime_prepare_required}},
        project_revision);
  }

  nlohmann::json sample_import_abort(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "import_token"}),
        "sample.import.abort request shape is invalid");
    const auto aborted =
        abort_sample_import(uuid_field(request, "import_token"));
    if (!aborted.has_value()) {
      return sample_error_envelope(aborted.error());
    }
    return success_envelope({{"aborted", true}}, std::nullopt);
  }

  nlohmann::json sample_update_pad(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation",
             "project_path",
             "command_id",
             "expected_revision",
             "slot",
             "playback"}),
        "sample.update_pad request shape is invalid");
    std::uint64_t project_revision = 0;
    const auto updated = update_sample_pad(
        SampleUpdateRequest{
            absolute_path_field(request, "project_path"),
            domain::CommandMeta{
                foundation::CommandId{uuid_field(request, "command_id")},
                unsigned_field(request, "expected_revision"),
            },
            slot_value(request.at("slot")),
            playback_value(request.at("playback")),
        },
        &project_revision);
    if (!updated.has_value()) {
      return sample_error_envelope(updated.error());
    }
    return success_envelope(
        {{"committed_revision", updated.value().committed_revision},
         {"runtime_prepare_required", updated.value().runtime_prepare_required}},
        project_revision);
  }

  nlohmann::json sample_reset_pad(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation",
             "project_path",
             "command_id",
             "expected_revision",
             "slot"}),
        "sample.reset_pad request shape is invalid");
    std::uint64_t project_revision = 0;
    const auto reset = reset_sample_pad(
        SampleResetRequest{
            absolute_path_field(request, "project_path"),
            domain::CommandMeta{
                foundation::CommandId{uuid_field(request, "command_id")},
                unsigned_field(request, "expected_revision"),
            },
            slot_value(request.at("slot")),
        },
        &project_revision);
    if (!reset.has_value()) {
      return sample_error_envelope(reset.error());
    }
    return success_envelope(
        {{"committed_revision", reset.value().committed_revision},
         {"runtime_prepare_required", reset.value().runtime_prepare_required}},
        project_revision);
  }

  nlohmann::json project_create(const nlohmann::json& request) {
    require(
        exact_keys(request,
                   {"operation", "project_path", "project_id", "bpm"}) ||
            exact_keys(request,
                       {"operation", "project_path", "project_id", "bpm",
                        "initial_pattern"}),
        "project.create request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto id = uuid_field(request, "project_id");
    const auto bpm = unsigned_field(request, "bpm", 240);
    require(bpm >= 40, "bpm is out of range");
    auto project = domain::create_project(
        foundation::ProjectId{id},
        static_cast<std::uint16_t>(bpm));
    if (!project.has_value()) {
      return error_envelope(project.error());
    }
    std::optional<foundation::PatternId> pattern_id;
    if (request.contains("initial_pattern")) {
      auto pattern = pattern_value(request.at("initial_pattern"));
      auto valid = validate_initial_pattern(pattern);
      if (!valid.has_value()) {
        return error_envelope(valid.error());
      }
      pattern_id = pattern.id;
      project.value().patterns.emplace(pattern.id, std::move(pattern));
    }
    const auto created = projects.create(path, project.value());
    if (!created.has_value()) {
      return error_envelope(created.error());
    }
    auto result = nlohmann::json{{"project_id", id}};
    if (pattern_id.has_value()) {
      result["pattern_id"] = pattern_id->value();
    }
    return success_envelope(std::move(result), 0);
  }

  nlohmann::json pattern_create(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "command_id", "expected_revision",
             "pattern_id", "bars"}),
        "pattern.create request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto pattern_id = uuid_field(request, "pattern_id");
    const auto bars = unsigned_field(request, "bars", 8);
    require(bars == 1 || bars == 2 || bars == 4 || bars == 8,
            "Pattern bars are invalid");
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    const auto created = projects.execute_with_identity(
        path,
        domain::Command{domain::CreatePattern{
            domain::CommandMeta{
                foundation::CommandId{command_id}, revision},
            domain::Pattern{
                foundation::PatternId{pattern_id},
                static_cast<std::uint8_t>(bars),
                {}},
        }});
    if (!created.has_value()) {
      return error_envelope(created.error());
    }
    return success_envelope(
        {{"committed_revision", created.value().outcome.state.revision},
         {"pattern_id", pattern_id},
         {"bars", bars},
         {"replayed", created.value().outcome.replayed}},
        created.value().outcome.state.revision);
  }

  nlohmann::json pattern_slot_assign(const nlohmann::json &request) {
    require(exact_keys(request,
                       {"operation", "project_path", "command_id",
                        "expected_revision", "pattern_slot", "pattern_id"}),
            "pattern.slot.assign request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto slot =
        unsigned_field(request, "pattern_slot", domain::kPatternSlotCount - 1U);
    const auto pattern_id = uuid_field(request, "pattern_id");
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    auto result = projects.execute_with_identity(
        path, domain::Command{domain::AssignPatternSlot{
                  {foundation::CommandId{uuid_field(request, "command_id")},
                   unsigned_field(request, "expected_revision")},
                  static_cast<std::uint8_t>(slot),
                  foundation::PatternId{pattern_id}}});
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    const auto &outcome = result.value().outcome;
    return success_envelope({{"pattern_slot", slot},
                             {"pattern_id", pattern_id},
                             {"committed_revision", outcome.state.revision},
                             {"replayed", outcome.replayed}},
                            outcome.state.revision);
  }

  nlohmann::json pattern_slot_clear(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "command_id",
                                 "expected_revision", "pattern_slot"}),
            "pattern.slot.clear request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto slot =
        unsigned_field(request, "pattern_slot", domain::kPatternSlotCount - 1U);
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    auto result = projects.execute_with_identity(
        path, domain::Command{domain::ClearPatternSlot{
                  {foundation::CommandId{uuid_field(request, "command_id")},
                   unsigned_field(request, "expected_revision")},
                  static_cast<std::uint8_t>(slot)}});
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    const auto &outcome = result.value().outcome;
    return success_envelope({{"pattern_slot", slot},
                             {"pattern_id", nullptr},
                             {"committed_revision", outcome.state.revision},
                             {"replayed", outcome.replayed}},
                            outcome.state.revision);
  }

  nlohmann::json pattern_slot_move(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "command_id",
                                 "expected_revision", "from_slot", "to_slot"}),
            "pattern.slot.move request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto from =
        unsigned_field(request, "from_slot", domain::kPatternSlotCount - 1U);
    const auto to =
        unsigned_field(request, "to_slot", domain::kPatternSlotCount - 1U);
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    auto result = projects.execute_with_identity(
        path, domain::Command{domain::MovePatternSlot{
                  {foundation::CommandId{uuid_field(request, "command_id")},
                   unsigned_field(request, "expected_revision")},
                  static_cast<std::uint8_t>(from),
                  static_cast<std::uint8_t>(to)}});
    if (!result.has_value()) {
      return error_envelope(result.error());
    }
    const auto &outcome = result.value().outcome;
    const auto &moved = outcome.state.pattern_slots.at(to);
    require(moved.has_value(), "moved Pattern slot is empty");
    return success_envelope({{"from_slot", from},
                             {"to_slot", to},
                             {"pattern_id", moved->value()},
                             {"committed_revision", outcome.state.revision},
                             {"replayed", outcome.replayed}},
                            outcome.state.revision);
  }

  static nlohmann::json performance_lifecycle_json(
      const project_io::PerformanceLifecycleReceipt &receipt) {
    return {
        {"performance_id", receipt.performance_id.value()},
        {"committed_revision", receipt.committed_revision},
        {"replayed", receipt.replayed},
    };
  }

  static nlohmann::json
  performance_stop_json(const project_io::PerformanceStopReceipt &receipt) {
    return {
        {"request_id", receipt.request_id.value()},
        {"session_id", receipt.session_id.value()},
        {"performance_id", receipt.performance_id.value()},
        {"state", "stopped"},
        {"pending_event_count", receipt.pending_event_count},
        {"replayed", receipt.replayed},
    };
  }

  static std::string_view replay_state_name(ReplayState state) {
    switch (state) {
      case ReplayState::playing:
        return "playing";
      case ReplayState::stopped:
        return "stopped";
      case ReplayState::complete:
        return "complete";
    }
    return "playing";
  }

  static nlohmann::json replay_status_json(
      const ReplayId& replay_id,
      const ReplayRuntimeStatus& status) {
    return {
        {"replay_id", replay_id.value()},
        {"state", replay_state_name(status.state)},
        {"resolved_revision", status.resolved_revision},
        {"event_cursor", status.event_cursor},
        {"event_count", status.event_count},
    };
  }

  static foundation::ArtifactRef
  performance_artifact(const nlohmann::json &encoded) {
    require(exact_keys(encoded, {"sha256", "media_type", "byte_length"}),
            "recording_artifact shape is invalid");
    const auto sha256 = string_field(encoded, "sha256");
    require(sha256.size() == 64U &&
                std::ranges::all_of(
                    sha256,
                    [](unsigned char character) {
                      return (character >= '0' && character <= '9') ||
                             (character >= 'a' && character <= 'f');
                    }),
            "recording_artifact sha256 is invalid");
    require(string_field(encoded, "media_type") == "audio/wav",
            "recording_artifact media_type is invalid");
    return {
        sha256,
        "audio/wav",
        unsigned_field(encoded, "byte_length"),
    };
  }

  nlohmann::json performance_list(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path"}),
            "performance.list request shape is invalid");
    const auto loaded =
        projects.load(absolute_path_field(request, "project_path"));
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    auto values = nlohmann::json::array();
    for (const auto &[id, performance] : loaded.value().performances) {
      values.push_back({
          {"performance_id", id.value()},
          {"name", performance.name},
          {"created_bpm", performance.created_bpm},
          {"recording_artifact", artifact_json(performance.recording_artifact)},
          {"event_count", performance.events.size()},
      });
    }
    return success_envelope({{"performances", std::move(values)}},
                            loaded.value().revision);
  }

  nlohmann::json performance_inspect(const nlohmann::json &request) {
    require(
        exact_keys(request, {"operation", "project_path", "performance_id"}),
        "performance.inspect request shape is invalid");
    const auto loaded =
        projects.load(absolute_path_field(request, "project_path"));
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto id =
        domain::PerformanceId{uuid_field(request, "performance_id")};
    const auto found = loaded.value().performances.find(id);
    if (found == loaded.value().performances.end()) {
      return error_envelope(
          sequence_error(ErrorCode::not_found, "Performance does not exist"));
    }
    return success_envelope({{"performance", performance_json(found->second)}},
                            loaded.value().revision);
  }

  nlohmann::json performance_begin(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "command_id", "expected_revision",
             "session_id", "performance_id"}),
            "performance.record.begin request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto session_id =
        foundation::SequenceSessionId{uuid_field(request, "session_id")};
    const auto performance_id =
        domain::PerformanceId{uuid_field(request, "performance_id")};
    std::lock_guard lock(sequence_mutex);
    const auto key = sequence_key(path);
    if (sequence_sessions.contains(key)) {
      return error_envelope(sequence_error(
          ErrorCode::invalid_argument,
          "Performance recording conflicts with an active Sequence session",
          {{"reason", "sequence_session_active"}}));
    }
    const auto existing = performance_sessions.find(key);
    if (existing != performance_sessions.end() &&
        (existing->second.session_id != session_id ||
         existing->second.performance_id != performance_id)) {
      return error_envelope(
          sequence_error(ErrorCode::invalid_argument,
                         "Performance recording session is already active",
                         {{"reason", "performance_session_active"}}));
    }
    std::optional<std::uint64_t> fresh_anchor_tick;
    if (existing == performance_sessions.end() && performance_clock) {
      auto active_before = sequence_journals.read_active_performance(path);
      if (!active_before.has_value() &&
          active_before.error().code == ErrorCode::not_found) {
        auto tick = performance_clock->read_tick();
        if (!tick.has_value()) {
          return error_envelope(tick.error());
        }
        fresh_anchor_tick = tick.value();
      }
    }
    auto begun = projects.begin_performance_draft(
        path, {{foundation::CommandId{uuid_field(request, "command_id")},
                unsigned_field(request, "expected_revision")},
               session_id,
               performance_id});
    if (!begun.has_value()) {
      return error_envelope(begun.error());
    }
    auto journal = sequence_journals.read_active_performance(path);
    if (!journal.has_value()) {
      return error_envelope(journal.error());
    }
    if (existing == performance_sessions.end()) {
      auto loaded = projects.load(path);
      if (!loaded.has_value()) {
        return error_envelope(loaded.error());
      }
      const auto draft = loaded.value().performances.find(performance_id);
      if (draft == loaded.value().performances.end()) {
        return error_envelope(sequence_error(
            ErrorCode::invalid_project,
            "Performance draft is missing after begin"));
      }
      if (performance_clock) {
        if (fresh_anchor_tick.has_value()) {
          performance_clock->anchor(
              draft->second.created_bpm, *fresh_anchor_tick);
        } else {
          std::uint64_t maximum_tick = 0;
          const auto include_event = [&maximum_tick](
                                         const domain::PerformanceEvent &event) {
            auto tick = domain::performance_event_tick(event);
            if (const auto *pad =
                    std::get_if<domain::PadHitPerformanceEvent>(
                        &event.payload)) {
              tick = pad->onset_tick + pad->duration_tick;
            }
            maximum_tick = std::max(maximum_tick, tick);
          };
          for (const auto& event : journal.value().pending_events) {
            include_event(event);
          }
          for (const auto& flush : journal.value().flushes) {
            for (const auto& event : flush.canonical_events) {
              include_event(event);
            }
          }
          if (journal.value().transient_checkpoint.has_value()) {
            maximum_tick = std::max(
                maximum_tick,
                journal.value().transient_checkpoint->last_accepted_tick);
          }
          performance_clock->anchor(
              draft->second.created_bpm, maximum_tick);
        }
      }
      if (performance_input_sequencer &&
          journal.value().last_input_sequence.has_value()) {
        performance_input_sequencer->seed(
            *journal.value().last_input_sequence);
      }
      PerformanceRuntime runtime{
          session_id,
          performance_id,
          journal.value().expected_revision,
          journal.value().next_flush_seq,
          journal.value().pending_events,
          {},
          {},
          false,
          {},
          {},
          std::nullopt,
          journal.value().last_launch_ack.has_value()
              ? std::optional<PatternLaunchOutcome>{PatternLaunchOutcome{
                    session_id,
                    journal.value().last_launch_ack->request_id,
                    journal.value().last_launch_ack->pattern_slot,
                    journal.value().last_launch_ack->effective_tick,
                    PatternLaunchOutcomeKind::applied}}
              : std::nullopt,
          journal.value().transient_checkpoint.has_value()
              ? journal.value().transient_checkpoint->last_accepted_tick
              : 0,
          false,
      };
      performance_sessions.emplace(key, std::move(runtime));
    }
    return success_envelope(performance_lifecycle_json(begun.value()),
                            begun.value().committed_revision);
  }

  nlohmann::json performance_flush(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "session_id",
                                 "command_id"}),
            "performance.record.flush request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto session_id =
        foundation::SequenceSessionId{uuid_field(request, "session_id")};
    const auto command_id =
        foundation::CommandId{uuid_field(request, "command_id")};
    std::lock_guard lock(sequence_mutex);
    auto found = performance_sessions.find(sequence_key(path));
    if (found == performance_sessions.end() ||
        found->second.session_id != session_id) {
      auto replayed =
          projects.replay_performance_flush(path, session_id, command_id);
      if (!replayed.has_value()) {
        return error_envelope(replayed.error());
      }
      if (replayed.value().has_value()) {
        return success_envelope(
            {{"performance_id",
              replayed.value()->identity.performance_id.value()},
             {"committed_revision",
              replayed.value()->receipt.committed_revision},
             {"replayed", true}},
            replayed.value()->receipt.committed_revision);
      }
      return error_envelope(
          sequence_error(ErrorCode::invalid_argument,
                         "Performance flush owner does not match"));
    }
    if (found->second.recovery_required) {
      return error_envelope(sequence_error(
          ErrorCode::invalid_argument,
          "Performance session requires recovery",
          {{"reason", "performance_tail_outcome_unknown"}}));
    }
    if (found->second.pending_events.empty()) {
      return error_envelope(
          sequence_error(ErrorCode::invalid_argument,
                         "Performance flush has no pending events",
                         {{"reason", "performance_flush_empty"}}));
    }
    auto appended = sequence_journals.append_performance_flush(
        path, session_id, command_id, found->second.performance_id,
        found->second.expected_revision, found->second.pending_events);
    if (!appended.has_value()) {
      return error_envelope(appended.error());
    }
    auto executed = projects.execute_performance_flush(
        path, {session_id, appended.value().flush_seq, command_id,
               found->second.performance_id});
    if (!executed.has_value()) {
      return error_envelope(executed.error());
    }
    found->second.expected_revision =
        executed.value().receipt.committed_revision;
    found->second.next_flush_seq = appended.value().flush_seq + 1U;
    for (auto &[fx, state] : found->second.open_fx) {
      (void)fx;
      if (state.pending_event_index.has_value() &&
          *state.pending_event_index < found->second.pending_events.size()) {
        const auto *move = std::get_if<domain::FxMovePerformanceEvent>(
            &found->second.pending_events
                 .at(*state.pending_event_index)
                 .payload);
        if (move != nullptr) {
          state.effective_value = move->value;
        }
      }
      state.pending_window.reset();
      state.pending_event_index.reset();
    }
    found->second.pending_events.clear();
    return success_envelope(
        {{"performance_id", found->second.performance_id.value()},
         {"committed_revision", executed.value().receipt.committed_revision},
         {"replayed", executed.value().replayed}},
        executed.value().receipt.committed_revision);
  }

  nlohmann::json performance_stop(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "session_id",
                                 "request_id"}),
            "performance.record.stop request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto session_id =
        foundation::SequenceSessionId{uuid_field(request, "session_id")};
    const auto request_id =
        foundation::CommandId{uuid_field(request, "request_id")};
    std::lock_guard lock(sequence_mutex);
    auto found = performance_sessions.find(sequence_key(path));
    if (found != performance_sessions.end()) {
      if (found->second.session_id != session_id) {
        return error_envelope(
            sequence_error(ErrorCode::invalid_argument,
                           "Performance stop owner does not match"));
      }
      if (found->second.recovery_required) {
        return error_envelope(sequence_error(
            ErrorCode::invalid_argument,
            "Performance session requires recovery",
            {{"reason", "performance_tail_outcome_unknown"}}));
      }
      auto closed = close_performance_transients(path, found->second);
      if (!closed.has_value()) {
        return error_envelope(closed.error());
      }
      if (pattern_launch_acknowledger) {
        pattern_launch_acknowledger->cancel(session_id);
      }
    }
    auto stopped =
        projects.stop_performance_session(path, session_id, request_id);
    if (!stopped.has_value()) {
      return error_envelope(stopped.error());
    }
    performance_sessions.erase(sequence_key(path));
    return success_envelope(performance_stop_json(stopped.value()),
                            std::nullopt);
  }

  nlohmann::json performance_save(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "command_id",
                                 "expected_revision", "performance_id", "name",
                                 "recording_artifact"}),
            "performance.save request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto id =
        domain::PerformanceId{uuid_field(request, "performance_id")};
    std::optional<foundation::ArtifactRef> artifact;
    if (!request.at("recording_artifact").is_null()) {
      artifact = performance_artifact(request.at("recording_artifact"));
    }
    auto saved = projects.save_performance_draft(
        path,
        {foundation::CommandId{uuid_field(request, "command_id")},
         unsigned_field(request, "expected_revision")},
        id, string_field(request, "name"), std::move(artifact));
    if (!saved.has_value()) {
      return error_envelope(saved.error());
    }
    return success_envelope(performance_lifecycle_json(saved.value()),
                            saved.value().committed_revision);
  }

  nlohmann::json performance_discard(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "command_id",
                                 "expected_revision", "performance_id"}),
            "performance.discard request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    auto discarded = projects.discard_performance_draft(
        path,
        {foundation::CommandId{uuid_field(request, "command_id")},
         unsigned_field(request, "expected_revision")},
        domain::PerformanceId{uuid_field(request, "performance_id")});
    if (!discarded.has_value()) {
      return error_envelope(discarded.error());
    }
    return success_envelope(performance_lifecycle_json(discarded.value()),
                            discarded.value().committed_revision);
  }

  nlohmann::json performance_recovery_list(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path"}),
            "performance.recovery.list request shape is invalid");
    auto candidates = projects.list_performance_recovery(
        absolute_path_field(request, "project_path"));
    if (!candidates.has_value()) {
      return error_envelope(candidates.error());
    }
    auto encoded = nlohmann::json::array();
    for (const auto &candidate : candidates.value()) {
      std::size_t durable = 0;
      for (const auto &flush : candidate.journal.flushes) {
        if (flush.completed) {
          durable += flush.canonical_events.size();
        }
      }
      encoded.push_back({
          {"session_id", candidate.journal.session_id.value()},
          {"performance_id", candidate.journal.performance_id.value()},
          {"reason", candidate.reason},
          {"durable_event_count", durable},
          {"pending_event_count", candidate.journal.pending_events.size()},
          {"fingerprint", candidate.journal.performance_fingerprint},
      });
    }
    return success_envelope({{"candidates", std::move(encoded)}}, std::nullopt);
  }

  nlohmann::json performance_recovery_apply(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "command_id",
                                 "expected_revision", "session_id"}),
            "performance.recovery.apply request shape is invalid");
    auto applied = projects.apply_performance_recovery(
        absolute_path_field(request, "project_path"),
        {foundation::CommandId{uuid_field(request, "command_id")},
         unsigned_field(request, "expected_revision")},
        foundation::SequenceSessionId{uuid_field(request, "session_id")});
    if (!applied.has_value()) {
      return error_envelope(applied.error());
    }
    return success_envelope(performance_lifecycle_json(applied.value()),
                            applied.value().committed_revision);
  }

  nlohmann::json performance_recovery_discard(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "session_id",
                                 "request_id"}),
            "performance.recovery.discard request shape is invalid");
    auto discarded = projects.discard_performance_recovery(
        absolute_path_field(request, "project_path"),
        foundation::SequenceSessionId{uuid_field(request, "session_id")},
        foundation::CommandId{uuid_field(request, "request_id")});
    if (!discarded.has_value()) {
      return error_envelope(discarded.error());
    }
    return success_envelope(performance_stop_json(discarded.value()),
                            std::nullopt);
  }

  nlohmann::json performance_rename(const nlohmann::json &request) {
    require(
        exact_keys(request, {"operation", "project_path", "command_id",
                             "expected_revision", "performance_id", "name"}),
        "performance.rename request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    const auto id =
        domain::PerformanceId{uuid_field(request, "performance_id")};
    auto renamed = projects.rename_performance(
        path, {{foundation::CommandId{uuid_field(request, "command_id")},
                unsigned_field(request, "expected_revision")},
               id,
               string_field(request, "name")});
    if (!renamed.has_value()) {
      return error_envelope(renamed.error());
    }
    project_io::PerformanceLifecycleReceipt receipt{
        id, renamed.value().state.revision, renamed.value().replayed};
    return success_envelope(performance_lifecycle_json(receipt),
                            receipt.committed_revision);
  }

  nlohmann::json performance_delete(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "command_id",
                                 "expected_revision", "performance_id"}),
            "performance.delete request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    const auto id =
        domain::PerformanceId{uuid_field(request, "performance_id")};
    auto deleted = projects.delete_performance(
        path, {{foundation::CommandId{uuid_field(request, "command_id")},
                unsigned_field(request, "expected_revision")},
               id});
    if (!deleted.has_value()) {
      return error_envelope(deleted.error());
    }
    project_io::PerformanceLifecycleReceipt receipt{
        id, deleted.value().state.revision, deleted.value().replayed};
    return success_envelope(performance_lifecycle_json(receipt),
                            receipt.committed_revision);
  }

  nlohmann::json performance_recording_bind(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "command_id",
                                 "expected_revision", "performance_id",
                                 "recording_artifact"}),
            "performance.recording.bind request shape is invalid");
    require(!request.at("recording_artifact").is_null(),
            "performance.recording.bind requires an Artifact");
    auto bound = projects.bind_performance_recording(
        absolute_path_field(request, "project_path"),
        {foundation::CommandId{uuid_field(request, "command_id")},
         unsigned_field(request, "expected_revision")},
        domain::PerformanceId{uuid_field(request, "performance_id")},
        performance_artifact(request.at("recording_artifact")));
    if (!bound.has_value()) {
      return error_envelope(bound.error());
    }
    return success_envelope(performance_lifecycle_json(bound.value()),
                            bound.value().committed_revision);
  }

  nlohmann::json performance_replay_begin(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "replay_id", "performance_id"}),
        "performance.replay.begin request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const ReplayId replay_id{uuid_field(request, "replay_id")};
    const domain::PerformanceId performance_id{
        uuid_field(request, "performance_id")};

    std::lock_guard lock(replay_mutex);
    const auto existing = replay_identities.find(replay_id.value());
    if (existing != replay_identities.end()) {
      if (existing->second.project_path != path ||
          existing->second.performance_id != performance_id) {
        return error_envelope(Error{
            ErrorCode::duplicate_id,
            "Performance replay id already exists with different payload",
            {{"replay_id", replay_id.value()}},
        });
      }
      const auto current = performance_replay_controller->status(replay_id);
      if (!current.has_value()) {
        return error_envelope(current.error());
      }
      if (current.value().state != ReplayState::playing &&
          active_replay_id == replay_id.value()) {
        active_replay_id.clear();
      }
      return success_envelope(
          replay_status_json(replay_id, current.value()), std::nullopt);
    }
    if (!active_replay_id.empty()) {
      const ReplayId active_id{active_replay_id};
      const auto active_status =
          performance_replay_controller->status(active_id);
      if (!active_status.has_value()) {
        return error_envelope(active_status.error());
      }
      if (active_status.value().state == ReplayState::playing) {
        return error_envelope(Error{
            ErrorCode::invalid_argument,
            "a Performance replay is already playing",
            {{"active_replay_id", active_replay_id}},
        });
      }
      active_replay_id.clear();
    }

    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto projection = cooker::cook_performance_replay(
        loaded.value(), performance_id,
        [this, path](const foundation::ArtifactRef& artifact) {
          return projects.read_artifact(path, artifact);
        });
    if (!projection.has_value()) {
      return error_envelope(projection.error());
    }
    const auto begun =
        performance_replay_controller->begin(replay_id, projection.value());
    if (!begun.has_value()) {
      const auto retained =
          performance_replay_controller->status(replay_id);
      if (retained.has_value() &&
          retained.value().state == ReplayState::playing) {
        replay_identities.emplace(
            replay_id.value(), ReplayIdentity{path, performance_id});
        active_replay_id = replay_id.value();
      }
      return error_envelope(begun.error());
    }
    replay_identities.emplace(
        replay_id.value(), ReplayIdentity{path, performance_id});
    if (begun.value().state == ReplayState::playing) {
      active_replay_id = replay_id.value();
    }
    return success_envelope(
        replay_status_json(replay_id, begun.value()), std::nullopt);
  }

  foundation::Result<ReplayRuntimeStatus> checked_replay_status(
      const std::filesystem::path& path,
      const ReplayId& replay_id) {
    const auto identity = replay_identities.find(replay_id.value());
    if (identity == replay_identities.end()) {
      return foundation::Result<ReplayRuntimeStatus>::failure(Error{
          ErrorCode::not_found,
          "Performance replay does not exist",
      });
    }
    if (identity->second.project_path != path) {
      return foundation::Result<ReplayRuntimeStatus>::failure(Error{
          ErrorCode::duplicate_id,
          "Performance replay id already exists for another Project",
          {{"replay_id", replay_id.value()}},
      });
    }
    auto status = performance_replay_controller->status(replay_id);
    if (status.has_value() && status.value().state != ReplayState::playing &&
        active_replay_id == replay_id.value()) {
      active_replay_id.clear();
    }
    return status;
  }

  nlohmann::json performance_replay_status(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "project_path", "replay_id"}),
        "performance.replay.status request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const ReplayId replay_id{uuid_field(request, "replay_id")};
    std::lock_guard lock(replay_mutex);
    const auto status = checked_replay_status(path, replay_id);
    if (!status.has_value()) {
      return error_envelope(status.error());
    }
    return success_envelope(
        replay_status_json(replay_id, status.value()), std::nullopt);
  }

  nlohmann::json performance_replay_stop(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "replay_id", "request_id"}),
        "performance.replay.stop request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const ReplayId replay_id{uuid_field(request, "replay_id")};
    const auto request_id = uuid_field(request, "request_id");
    std::lock_guard lock(replay_mutex);

    const auto receipt = replay_stop_receipts.find(request_id);
    if (receipt != replay_stop_receipts.end()) {
      if (receipt->second.project_path != path ||
          receipt->second.replay_id != replay_id) {
        return error_envelope(Error{
            ErrorCode::duplicate_id,
            "Performance replay stop request id already exists",
            {{"request_id", request_id}},
        });
      }
      auto result = replay_status_json(replay_id, receipt->second.status);
      result["request_id"] = request_id;
      result["replayed"] = true;
      return success_envelope(std::move(result), std::nullopt);
    }

    auto status = checked_replay_status(path, replay_id);
    if (!status.has_value()) {
      return error_envelope(status.error());
    }
    if (status.value().state == ReplayState::playing) {
      status = performance_replay_controller->stop(replay_id);
      if (!status.has_value()) {
        return error_envelope(status.error());
      }
      if (status.value().state != ReplayState::playing &&
          active_replay_id == replay_id.value()) {
        active_replay_id.clear();
      }
    }
    if (status.value().state != ReplayState::playing) {
      replay_stop_receipts.emplace(
          request_id, ReplayStopReceipt{path, replay_id, status.value()});
    }
    auto result = replay_status_json(replay_id, status.value());
    result["request_id"] = request_id;
    result["replayed"] = false;
    return success_envelope(std::move(result), std::nullopt);
  }

  nlohmann::json performance_resample_commit(
      const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "command_id",
             "expected_revision", "performance_id", "source_start_frame",
             "source_end_frame", "target_slot"}),
        "performance.resample.commit request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto command_id = uuid_field(request, "command_id");
    const domain::CommandMeta meta{
        foundation::CommandId{command_id},
        unsigned_field(request, "expected_revision")};
    const domain::PerformanceId performance_id{
        uuid_field(request, "performance_id")};
    const auto start_frame = unsigned_field(request, "source_start_frame");
    const auto end_frame = unsigned_field(request, "source_end_frame");
    const auto target = slot_value(request.at("target_slot"));

    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto found = loaded.value().performances.find(performance_id);
    if (found == loaded.value().performances.end()) {
      return error_envelope(Error{
          ErrorCode::not_found,
          "Performance does not exist",
      });
    }
    const auto& performance = found->second;
    if (!performance.recording_artifact.has_value() ||
        performance.recording_artifact->media_type != "audio/wav") {
      return error_envelope(Error{
          ErrorCode::invalid_argument,
          "Performance does not have a verified audio/wav recording Artifact",
      });
    }
    const auto bytes = projects.read_artifact(
        path, *performance.recording_artifact);
    if (!bytes.has_value()) {
      return error_envelope(bytes.error());
    }
    const auto selected = cooker::select_pcm16_stereo_wav(
        bytes.value(), start_frame, end_frame);
    if (!selected.has_value()) {
      return error_envelope(selected.error());
    }
    if (loaded.value().revision == meta.expected_revision) {
      const auto candidate = measure_prepared_quota(selected.value());
      if (!candidate.has_value()) {
        return error_envelope(candidate.error());
      }
      const auto quota = compute_sample_quota(path, loaded.value(), target);
      if (!quota.has_value()) {
        return error_envelope(quota.error());
      }
      const auto assessment = audio::assess_runtime_quota(
          quota.value().result.bank_used_bytes,
          quota.value().result.project_used_bytes,
          candidate.value().bytes,
          *sample_limits);
      if (!assessment.has_value()) {
        return error_envelope(Error{
            ErrorCode::invalid_project,
            "Sample quota ledger exceeds configured limits",
        });
      }
      if (assessment->constraint ==
          audio::RuntimeQuotaConstraint::user_bank) {
        std::vector<nlohmann::json> consumed;
        consumed.reserve(quota.value().result.consumed.size());
        for (const auto& entry : quota.value().result.consumed) {
          consumed.push_back({
              {"pad", entry.slot.pad},
              {"prepared_bytes", entry.prepared_bytes},
              {"prepared_frames", entry.prepared_frames},
          });
        }
        return sample_error_envelope(runtime_bank_quota_error(
            target,
            candidate.value().bytes,
            candidate.value().frames,
            assessment->user_bank_remaining_bytes,
            sample_limits->maximum_user_bank_bytes,
            consumed));
      }
      if (assessment->constraint ==
          audio::RuntimeQuotaConstraint::generation) {
        return sample_error_envelope(runtime_project_quota_error(
            candidate.value().bytes,
            candidate.value().frames,
            quota.value().result.project_used_bytes,
            assessment->generation_remaining_bytes,
            sample_limits->maximum_generation_bytes,
            quota.value().bank_used_bytes));
      }
    }
    const domain::AssetLineage lineage{
        domain::AssetArtifactLineageSource{
            performance.recording_artifact->sha256,
            performance.recording_revision},
        domain::ResampleLineageDerivation{
            {start_frame, end_frame},
            performance.id},
    };
    const auto committed = projects.import_assign_sample_bytes(
        path,
        {meta,
         target,
         foundation::AssetId{command_id},
         "audio/wav",
         selected.value(),
         std::nullopt,
         lineage});
    if (!committed.has_value()) {
      return error_envelope(committed.error());
    }
    const auto revision =
        committed.value().event.at("revision").get<std::uint64_t>();
    return success_envelope(
        {{"performance_id", performance_id.value()},
         {"committed_revision", revision},
         {"runtime_prepare_required", true}},
        committed.value().state.revision);
  }

  static domain::PerformanceFx performance_fx(std::string_view value) {
    static constexpr std::array<std::string_view, 8> names{
        "filter", "delay",   "reverb", "stutter",
        "gate",   "reverse", "crush",  "cutter"};
    const auto found = std::ranges::find(names, value);
    require(found != names.end(), "Performance FX is invalid");
    return static_cast<domain::PerformanceFx>(
        std::distance(names.begin(), found));
  }

  foundation::Result<void>
  performance_transient_checkpoint(
      const PerformanceRuntime &runtime,
      project_io::PerformanceTransientCheckpoint &checkpoint) const {
    checkpoint = project_io::PerformanceTransientCheckpoint{
        {}, {}, runtime.hold, runtime.last_accepted_tick};
    checkpoint.open_pads.reserve(runtime.open_pads.size());
    for (const auto &[gesture_id, pad] : runtime.open_pads) {
      checkpoint.open_pads.push_back(project_io::PerformanceOpenPadTransient{
          gesture_id, pad.slot, pad.onset_tick, pad.velocity});
    }
    std::ranges::sort(
        checkpoint.open_pads,
        {},
        [](const auto &pad) {
          return std::pair{pad.slot, pad.gesture_id};
        });
    checkpoint.open_fx.reserve(runtime.open_fx.size());
    for (const auto &[fx, state] : runtime.open_fx) {
      std::optional<std::uint16_t> pending_value;
      if (state.pending_event_index.has_value()) {
        if (*state.pending_event_index >= runtime.pending_events.size()) {
          return foundation::Result<void>::failure(sequence_error(
              ErrorCode::internal_error,
              "Performance FX checkpoint index is invalid"));
        }
        const auto *pending = std::get_if<domain::FxMovePerformanceEvent>(
            &runtime.pending_events.at(*state.pending_event_index).payload);
        if (pending == nullptr || pending->fx != fx) {
          return foundation::Result<void>::failure(sequence_error(
              ErrorCode::internal_error,
              "Performance FX checkpoint state is invalid"));
        }
        pending_value = pending->value;
      }
      checkpoint.open_fx.push_back(project_io::PerformanceOpenFxTransient{
          fx, state.gesture_id, state.effective_value, pending_value});
    }
    return foundation::Result<void>::success();
  }

  static bool performance_tail_outcome_unknown(
      const foundation::Error &error) {
    return error.details.is_object() && error.details.contains("reason") &&
           error.details.at("reason") ==
               "performance_tail_outcome_unknown";
  }

  foundation::Result<void>
  append_performance_runtime_tail(const std::filesystem::path &path,
                                  PerformanceRuntime &runtime,
                                  std::uint64_t input_sequence) {
    if (runtime.recovery_required) {
      return foundation::Result<void>::failure(sequence_error(
          ErrorCode::invalid_argument,
          "Performance session requires recovery",
          {{"reason", "performance_tail_outcome_unknown"}}));
    }
    project_io::PerformanceTransientCheckpoint checkpoint;
    auto built = performance_transient_checkpoint(runtime, checkpoint);
    if (!built.has_value()) {
      return built;
    }
    return sequence_journals.append_performance_tail(
        path, runtime.session_id, runtime.performance_id,
        runtime.expected_revision, input_sequence, runtime.pending_events,
        std::move(checkpoint),
        runtime.last_launch_ack.has_value()
            ? std::optional<project_io::PerformanceLaunchAck>{
                  project_io::PerformanceLaunchAck{
                      runtime.last_launch_ack->request_id,
                      runtime.last_launch_ack->pattern_slot,
                      runtime.last_launch_ack->effective_tick}}
            : std::nullopt);
  }

  static void canonicalize_performance_pending(PerformanceRuntime &runtime) {
    runtime.pending_events =
        domain::canonical_performance_events(std::move(runtime.pending_events));
    for (auto &[fx, state] : runtime.open_fx) {
      (void)fx;
      state.pending_event_index.reset();
    }
    for (std::size_t index = 0; index < runtime.pending_events.size();
         ++index) {
      const auto *move = std::get_if<domain::FxMovePerformanceEvent>(
          &runtime.pending_events[index].payload);
      if (move == nullptr) {
        continue;
      }
      auto found = runtime.open_fx.find(move->fx);
      if (found != runtime.open_fx.end() &&
          found->second.pending_window.has_value() &&
          *found->second.pending_window == move->tick / 128U) {
        found->second.pending_event_index = index;
      }
    }
  }

  static bool same_launch_ack(const PatternLaunchOutcome &left,
                              const PatternLaunchOutcome &right) {
    return left.session_id == right.session_id &&
           left.request_id == right.request_id &&
           left.pattern_slot == right.pattern_slot &&
           left.effective_tick == right.effective_tick &&
           left.kind == right.kind;
  }

  foundation::Result<void>
  service_performance_launch(const std::filesystem::path &path,
                             PerformanceRuntime &runtime) {
    if (runtime.recovery_required) {
      return foundation::Result<void>::failure(sequence_error(
          ErrorCode::invalid_argument,
          "Performance session requires recovery",
          {{"reason", "performance_tail_outcome_unknown"}}));
    }
    if (!pattern_launch_acknowledger) {
      return foundation::Result<void>::success();
    }
    while (true) {
      const auto outcomes =
          pattern_launch_acknowledger->peek(runtime.session_id);
      if (outcomes.empty()) {
        return foundation::Result<void>::success();
      }
      const auto &outcome = outcomes.front();
      if (outcome.session_id != runtime.session_id) {
        return foundation::Result<void>::failure(sequence_error(
            ErrorCode::invalid_argument,
            "Performance launch outcome belongs to another session",
            {{"reason", "performance_launch_outcome_session_mismatch"},
             {"remedy",
              "retain the outcome and repair the acknowledger session queue before retrying service"}}));
      }

      if (outcome.kind != PatternLaunchOutcomeKind::applied) {
        auto committed = pattern_launch_acknowledger->commit(
            runtime.session_id, outcome.request_id);
        if (!committed.has_value()) {
          return committed;
        }
        if (runtime.pending_launch.has_value() &&
            runtime.pending_launch->request_id == outcome.request_id) {
          runtime.pending_launch.reset();
        }
        continue;
      }

      if (runtime.last_launch_ack.has_value() &&
          runtime.last_launch_ack->request_id == outcome.request_id) {
        if (!same_launch_ack(*runtime.last_launch_ack, outcome)) {
          return foundation::Result<void>::failure(sequence_error(
              ErrorCode::invalid_argument,
              "Performance launch acknowledgement conflicts with durable identity",
              {{"reason", "performance_launch_ack_conflict"},
               {"remedy",
                "retain the journal and outcome; reconcile the exact request, slot and effective tick before retrying service"}}));
        }
        auto committed = pattern_launch_acknowledger->commit(
            runtime.session_id, outcome.request_id);
        if (!committed.has_value()) {
          return committed;
        }
        if (runtime.pending_launch.has_value() &&
            runtime.pending_launch->request_id == outcome.request_id) {
          runtime.pending_launch.reset();
        }
        continue;
      }

      if (!performance_input_sequencer) {
        return foundation::Result<void>::failure(sequence_error(
            ErrorCode::invalid_argument,
            "Performance input sequencer is unavailable",
            {{"reason", "performance_input_authority_unavailable"}}));
      }
      auto sequence = performance_input_sequencer->next();
      if (!sequence.has_value()) {
        return foundation::Result<void>::failure(sequence.error());
      }
      auto before = runtime;
      runtime.pending_events.push_back(
          domain::PerformanceEvent{domain::PatternLaunchPerformanceEvent{
              outcome.pattern_slot, outcome.effective_tick}});
      runtime.last_launch_ack = outcome;
      if (runtime.pending_launch.has_value() &&
          runtime.pending_launch->request_id == outcome.request_id) {
        runtime.pending_launch.reset();
      }
      canonicalize_performance_pending(runtime);
      auto durable =
          append_performance_runtime_tail(path, runtime, sequence.value());
      if (!durable.has_value()) {
        const auto outcome_unknown =
            performance_tail_outcome_unknown(durable.error());
        runtime = std::move(before);
        runtime.recovery_required = outcome_unknown;
        return durable;
      }
      auto committed = pattern_launch_acknowledger->commit(
          runtime.session_id, outcome.request_id);
      if (!committed.has_value()) {
        return committed;
      }
    }
  }

  foundation::Result<void> service_performance() {
    std::lock_guard lock(sequence_mutex);
    for (auto &[path, runtime] : performance_sessions) {
      auto serviced = service_performance_launch(
          std::filesystem::path{path}, runtime);
      if (!serviced.has_value()) {
        return serviced;
      }
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void>
  close_performance_transients(const std::filesystem::path &path,
                               PerformanceRuntime &runtime) {
    if (runtime.open_pads.empty() && runtime.open_fx.empty() && !runtime.hold) {
      return foundation::Result<void>::success();
    }
    if (!performance_clock || !performance_input_sequencer) {
      return foundation::Result<void>::failure(
          sequence_error(ErrorCode::invalid_argument,
                         "Performance Core authorities are unavailable",
                         {{"reason", "performance_authority_unavailable"}}));
    }
    auto tick = performance_clock->read_tick();
    if (!tick.has_value()) {
      return foundation::Result<void>::failure(tick.error());
    }
    auto sequence = performance_input_sequencer->next();
    if (!sequence.has_value()) {
      return foundation::Result<void>::failure(sequence.error());
    }
    auto before = runtime;
    for (const auto &[gesture_id, pad] : runtime.open_pads) {
      (void)gesture_id;
      runtime.pending_events.push_back(
          domain::PerformanceEvent{domain::PadHitPerformanceEvent{
              pad.slot, pad.onset_tick,
              tick.value() > pad.onset_tick
                  ? tick.value() - pad.onset_tick
                  : std::uint64_t{1},
              pad.velocity}});
    }
    for (const auto &[fx, state] : runtime.open_fx) {
      (void)state;
      runtime.pending_events.push_back(domain::PerformanceEvent{
          domain::FxReleasePerformanceEvent{fx, tick.value()}});
    }
    if (runtime.hold) {
      runtime.pending_events.push_back(domain::PerformanceEvent{
          domain::HoldOffPerformanceEvent{tick.value()}});
    }
    runtime.open_pads.clear();
    runtime.open_fx.clear();
    runtime.hold = false;
    runtime.last_accepted_tick = tick.value();
    canonicalize_performance_pending(runtime);
    auto durable =
        append_performance_runtime_tail(path, runtime, sequence.value());
    if (!durable.has_value()) {
      if (performance_tail_outcome_unknown(durable.error())) {
        runtime.recovery_required = true;
      } else {
        runtime = std::move(before);
      }
      return durable;
    }
    return foundation::Result<void>::success();
  }

  nlohmann::json performance_event(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "session_id",
                                 "event_id", "event"}),
            "performance.record.event request shape is invalid");
    require(request.at("event").is_object(), "Performance event is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto session_id =
        foundation::SequenceSessionId{uuid_field(request, "session_id")};
    const auto event_id = uuid_field(request, "event_id");
    const auto payload = request.at("event").dump();
    std::lock_guard lock(sequence_mutex);
    auto found = performance_sessions.find(sequence_key(path));
    if (found == performance_sessions.end() ||
        found->second.session_id != session_id) {
      return error_envelope(
          sequence_error(ErrorCode::invalid_argument,
                         "Performance event owner does not match"));
    }
    auto &runtime = found->second;
    const auto replay = runtime.event_receipts.find(event_id);
    if (replay != runtime.event_receipts.end()) {
      if (replay->second.payload != payload) {
        return error_envelope(
            sequence_error(ErrorCode::invalid_argument,
                           "Performance event id is bound to another payload",
                           {{"reason", "performance_event_id_collision"}}));
      }
      return success_envelope(
          {{"event_id", event_id},
           {"accepted_tick", replay->second.accepted_tick},
           {"input_sequence", replay->second.input_sequence},
           {"coalesced", replay->second.coalesced},
           {"replayed", true}},
          std::nullopt);
    }
    if (runtime.recovery_required) {
      return error_envelope(sequence_error(
          ErrorCode::invalid_argument,
          "Performance session requires recovery",
          {{"reason", "performance_tail_outcome_unknown"}}));
    }
    if (!performance_clock || !performance_input_sequencer) {
      return error_envelope(
          sequence_error(ErrorCode::invalid_argument,
                         "Performance Core authorities are unavailable",
                         {{"reason", "performance_authority_unavailable"}}));
    }
    auto tick = performance_clock->read_tick();
    if (!tick.has_value()) {
      return error_envelope(tick.error());
    }
    auto input_sequence = performance_input_sequencer->next();
    if (!input_sequence.has_value()) {
      return error_envelope(input_sequence.error());
    }
    const auto &event = request.at("event");
    require(event.contains("kind"), "Performance event kind is required");
    const auto kind = string_field(event, "kind");
    auto before = runtime;
    bool coalesced = false;
    // Live master-bus application mirrors the Replay translation exactly
    // (P10-D7). Journal coalescing is a recording-density rule (P10-D15) and
    // never silences an admitted gesture.
    std::optional<audio::FxGesture> live_gesture;
    if (kind == "pad_press") {
      require(exact_keys(event, {"kind", "gesture_id", "slot", "velocity"}),
              "pad_press event shape is invalid");
      const auto gesture = uuid_field(event, "gesture_id");
      require(!runtime.open_pads.contains(gesture),
              "Pad gesture is already open");
      const auto velocity = unsigned_field(event, "velocity", 127U);
      require(velocity >= 1U, "velocity is out of range");
      runtime.open_pads.emplace(
          gesture,
          OpenPerformancePad{
              static_cast<std::uint8_t>(unsigned_field(event, "slot", 63U)),
              tick.value(), static_cast<std::uint8_t>(velocity)});
    } else if (kind == "pad_release") {
      require(exact_keys(event, {"kind", "gesture_id", "slot"}),
              "pad_release event shape is invalid");
      const auto gesture = uuid_field(event, "gesture_id");
      const auto pad = runtime.open_pads.find(gesture);
      const auto slot = unsigned_field(event, "slot", 63U);
      require(pad != runtime.open_pads.end() && pad->second.slot == slot,
              "Pad release does not match an open gesture");
      runtime.pending_events.push_back(
          domain::PerformanceEvent{domain::PadHitPerformanceEvent{
              pad->second.slot, pad->second.onset_tick,
              tick.value() > pad->second.onset_tick
                  ? tick.value() - pad->second.onset_tick
                  : std::uint64_t{1},
              pad->second.velocity}});
      runtime.open_pads.erase(pad);
    } else if (kind == "fx_engage") {
      require(exact_keys(event, {"kind", "gesture_id", "fx", "value"}),
              "fx_engage event shape is invalid");
      const auto fx = performance_fx(string_field(event, "fx"));
      require(!runtime.open_fx.contains(fx),
              "Performance FX is already engaged");
      const auto gesture = uuid_field(event, "gesture_id");
      const auto value = unsigned_field(event, "value", 1000U);
      runtime.pending_events.push_back(
          domain::PerformanceEvent{domain::FxEngagePerformanceEvent{
              fx, static_cast<std::uint16_t>(value), tick.value()}});
      runtime.open_fx.emplace(
          fx, OpenPerformanceFx{gesture, static_cast<std::uint16_t>(value),
                                std::nullopt, std::nullopt});
      live_gesture = audio::FxGesture{audio::FxGestureKind::engage, fx,
                                      static_cast<std::uint16_t>(value)};
    } else if (kind == "fx_move") {
      require(exact_keys(event, {"kind", "gesture_id", "fx", "value"}),
              "fx_move event shape is invalid");
      const auto fx = performance_fx(string_field(event, "fx"));
      const auto gesture = uuid_field(event, "gesture_id");
      auto state = runtime.open_fx.find(fx);
      require(state != runtime.open_fx.end() &&
                  state->second.gesture_id == gesture,
              "FX move does not match an engaged gesture");
      const auto value =
          static_cast<std::uint16_t>(unsigned_field(event, "value", 1000U));
      live_gesture = audio::FxGesture{audio::FxGestureKind::move, fx, value};
      const auto window = tick.value() / 128U;
      if (state->second.pending_window == window &&
          state->second.pending_event_index.has_value()) {
        auto index = *state->second.pending_event_index;
        auto *pending = std::get_if<domain::FxMovePerformanceEvent>(
            &runtime.pending_events.at(index).payload);
        require(pending != nullptr, "FX pending state is invalid");
        if (value == state->second.effective_value) {
          runtime.pending_events.erase(runtime.pending_events.begin() +
                                       static_cast<std::ptrdiff_t>(index));
          state->second.pending_window.reset();
          state->second.pending_event_index.reset();
        } else {
          pending->value = value;
          pending->tick = tick.value();
        }
        coalesced = true;
      } else {
        if (state->second.pending_event_index.has_value()) {
          const auto *previous = std::get_if<domain::FxMovePerformanceEvent>(
              &runtime.pending_events.at(*state->second.pending_event_index)
                   .payload);
          if (previous != nullptr) {
            state->second.effective_value = previous->value;
          }
        }
        state->second.pending_window.reset();
        state->second.pending_event_index.reset();
        if (value != state->second.effective_value) {
          runtime.pending_events.push_back(domain::PerformanceEvent{
              domain::FxMovePerformanceEvent{fx, value, tick.value()}});
          state->second.pending_window = window;
        } else {
          coalesced = true;
        }
      }
    } else if (kind == "fx_release") {
      require(exact_keys(event, {"kind", "gesture_id", "fx"}),
              "fx_release event shape is invalid");
      const auto fx = performance_fx(string_field(event, "fx"));
      const auto gesture = uuid_field(event, "gesture_id");
      const auto state = runtime.open_fx.find(fx);
      require(state != runtime.open_fx.end() &&
                  state->second.gesture_id == gesture,
              "FX release does not match an engaged gesture");
      runtime.pending_events.push_back(domain::PerformanceEvent{
          domain::FxReleasePerformanceEvent{fx, tick.value()}});
      runtime.open_fx.erase(state);
      live_gesture =
          audio::FxGesture{audio::FxGestureKind::release, fx, 0};
    } else if (kind == "hold_on") {
      require(exact_keys(event, {"kind"}), "hold_on event shape is invalid");
      require(!runtime.hold, "Performance HOLD is already on");
      runtime.hold = true;
      runtime.pending_events.push_back(domain::PerformanceEvent{
          domain::HoldOnPerformanceEvent{tick.value()}});
      live_gesture = audio::FxGesture{audio::FxGestureKind::hold_on,
                                      domain::PerformanceFx::filter, 0};
    } else if (kind == "hold_off") {
      require(exact_keys(event, {"kind"}), "hold_off event shape is invalid");
      require(runtime.hold, "Performance HOLD is already off");
      runtime.hold = false;
      runtime.pending_events.push_back(domain::PerformanceEvent{
          domain::HoldOffPerformanceEvent{tick.value()}});
      live_gesture = audio::FxGesture{audio::FxGestureKind::hold_off,
                                      domain::PerformanceFx::filter, 0};
    } else {
      require(false, "Performance event kind is invalid");
    }
    if (live_gesture.has_value() && performance_gesture_sink) {
      // Fail closed before the durable append: a gesture the master bus
      // refused is not admitted, so the journal never claims audio that was
      // never produced. The Host may retry the same event id.
      const auto applied =
          performance_gesture_sink->apply_gesture(*live_gesture);
      if (!applied.has_value()) {
        runtime = std::move(before);
        return error_envelope(applied.error());
      }
    }
    runtime.last_accepted_tick = tick.value();
    canonicalize_performance_pending(runtime);
    auto durable =
        append_performance_runtime_tail(path, runtime, input_sequence.value());
    if (!durable.has_value()) {
      if (performance_tail_outcome_unknown(durable.error())) {
        runtime.recovery_required = true;
      } else {
        runtime = std::move(before);
      }
      return error_envelope(durable.error());
    }
    runtime.event_receipts.emplace(
        event_id, PerformanceEventReceipt{payload, tick.value(),
                                          input_sequence.value(), coalesced});
    return success_envelope({{"event_id", event_id},
                             {"accepted_tick", tick.value()},
                             {"input_sequence", input_sequence.value()},
                             {"coalesced", coalesced},
                             {"replayed", false}},
                            std::nullopt);
  }

  nlohmann::json performance_launch_request(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path", "session_id",
                                 "request_id", "pattern_slot"}),
            "performance.record.launch-request request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto session_id =
        foundation::SequenceSessionId{uuid_field(request, "session_id")};
    const auto request_id =
        foundation::CommandId{uuid_field(request, "request_id")};
    const auto slot =
        unsigned_field(request, "pattern_slot", domain::kPatternSlotCount - 1U);
    std::lock_guard lock(sequence_mutex);
    auto found = performance_sessions.find(sequence_key(path));
    if (found == performance_sessions.end() ||
        found->second.session_id != session_id) {
      return error_envelope(
          sequence_error(ErrorCode::invalid_argument,
                         "Performance launch owner does not match"));
    }
    auto &runtime = found->second;
    const auto payload = std::to_string(slot);
    const auto replay = runtime.launch_receipts.find(request_id.value());
    if (replay != runtime.launch_receipts.end()) {
      if (replay->second.first != payload) {
        return error_envelope(sequence_error(
            ErrorCode::invalid_argument,
            "Performance launch request id is bound to another payload",
            {{"reason", "performance_launch_request_collision"}}));
      }
      const auto &receipt = replay->second.second;
      return success_envelope({{"request_id", request_id.value()},
                               {"state", "pending"},
                               {"target_tick", receipt.target_tick}},
                              std::nullopt);
    }
    if (runtime.recovery_required) {
      return error_envelope(sequence_error(
          ErrorCode::invalid_argument,
          "Performance session requires recovery",
          {{"reason", "performance_tail_outcome_unknown"}}));
    }
    if (!performance_clock || !pattern_launch_acknowledger) {
      return error_envelope(sequence_error(
          ErrorCode::invalid_argument,
          "Performance launch authorities are unavailable",
          {{"reason", "performance_launch_authority_unavailable"}}));
    }
    auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    if (loaded.value().revision != runtime.expected_revision) {
      return error_envelope(sequence_error(
          ErrorCode::revision_conflict,
          "Performance launch Project revision does not match the active session"));
    }
    std::shared_ptr<const cooker::RuntimeSnapshot> resolved_pattern;
    const auto& occupying_pattern = loaded.value().pattern_slots.at(slot);
    if (occupying_pattern.has_value()) {
      auto cooked = cook_project(
          path, loaded.value(), *occupying_pattern, sample_limits);
      if (!cooked.has_value()) {
        return error_envelope(cooked.error());
      }
      resolved_pattern = std::move(cooked.value());
    }
    auto tick = performance_clock->read_tick();
    if (!tick.has_value()) {
      return error_envelope(tick.error());
    }
    const auto earliest =
        ((tick.value() / domain::kBarTicks4x4) + 1U) * domain::kBarTicks4x4;
    auto reservation = pattern_launch_acknowledger->reserve(
        session_id, request_id, static_cast<std::uint8_t>(slot), earliest,
        std::move(resolved_pattern));
    if (!reservation.has_value()) {
      return error_envelope(reservation.error());
    }
    PendingPerformanceLaunch pending{
        request_id, static_cast<std::uint8_t>(slot),
        reservation.value().target_tick, reservation.value().claimed};
    runtime.pending_launch = pending;
    runtime.launch_receipts.emplace(request_id.value(),
                                    std::pair{payload, pending});
    return success_envelope({{"request_id", request_id.value()},
                             {"state", "pending"},
                             {"target_tick", pending.target_tick}},
                            std::nullopt);
  }

  static nlohmann::json
  pending_launch_json(const std::optional<PendingPerformanceLaunch> &pending) {
    if (!pending.has_value()) {
      return nullptr;
    }
    return {
        {"request_id", pending->request_id.value()},
        {"pattern_slot", pending->pattern_slot},
        {"target_tick", pending->target_tick},
        {"claimed", pending->claimed},
    };
  }

  static nlohmann::json
  launch_ack_json(const std::optional<PatternLaunchOutcome> &outcome) {
    if (!outcome.has_value()) {
      return nullptr;
    }
    return {
        {"request_id", outcome->request_id.value()},
        {"pattern_slot", outcome->pattern_slot},
        {"effective_tick", outcome->effective_tick},
    };
  }

  static std::optional<PatternLaunchOutcome> launch_ack_outcome(
      const foundation::SequenceSessionId &session_id,
      const std::optional<project_io::PerformanceLaunchAck> &ack) {
    if (!ack.has_value()) {
      return std::nullopt;
    }
    return PatternLaunchOutcome{
        session_id, ack->request_id, ack->pattern_slot, ack->effective_tick,
        PatternLaunchOutcomeKind::applied};
  }

  static nlohmann::json performance_status_json(
      std::string_view state,
      const std::optional<foundation::SequenceSessionId> &session_id,
      const std::optional<domain::PerformanceId> &performance_id,
      std::uint64_t journal_revision, std::uint64_t next_flush_seq,
      std::size_t pending_event_count, std::size_t open_pad_gestures,
      std::size_t open_fx_gestures, bool hold,
      const std::optional<PendingPerformanceLaunch> &pending_launch,
      const std::optional<PatternLaunchOutcome> &last_launch_ack) {
    return {
        {"state", state},
        {"session_id", session_id.has_value()
                           ? nlohmann::json(session_id->value())
                           : nlohmann::json(nullptr)},
        {"performance_id", performance_id.has_value()
                               ? nlohmann::json(performance_id->value())
                               : nlohmann::json(nullptr)},
        {"journal_revision", journal_revision},
        {"next_flush_seq", next_flush_seq},
        {"pending_event_count", pending_event_count},
        {"open_pad_gestures", open_pad_gestures},
        {"open_fx_gestures", open_fx_gestures},
        {"hold", hold},
        {"pending_launch", pending_launch_json(pending_launch)},
        {"last_launch_ack", launch_ack_json(last_launch_ack)},
    };
  }

  nlohmann::json performance_status(const nlohmann::json &request) {
    require(exact_keys(request, {"operation", "project_path"}),
            "performance.record.status request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    std::lock_guard lock(sequence_mutex);
    auto found = performance_sessions.find(sequence_key(path));
    if (found != performance_sessions.end()) {
      const auto &runtime = found->second;
      return success_envelope(
          performance_status_json(
              runtime.recovery_required ? "recovery_required" : "active",
              runtime.session_id, runtime.performance_id,
              runtime.expected_revision, runtime.next_flush_seq,
              runtime.pending_events.size(), runtime.open_pads.size(),
              runtime.open_fx.size(), runtime.hold, runtime.pending_launch,
              runtime.last_launch_ack),
          std::nullopt);
    }
    auto journal = sequence_journals.read_active_performance(path);
    if (journal.has_value()) {
      const auto &checkpoint = journal.value().transient_checkpoint;
      const auto state =
          journal.value().state == project_io::SequenceSessionState::stopped
              ? "stopped"
          : journal.value().state ==
                  project_io::SequenceSessionState::recovery_required
              ? "recovery_required"
              : "active";
      return success_envelope(
          performance_status_json(
              state, journal.value().session_id, journal.value().performance_id,
              journal.value().expected_revision, journal.value().next_flush_seq,
              journal.value().pending_events.size(),
              checkpoint.has_value() ? checkpoint->open_pads.size() : 0,
              checkpoint.has_value() ? checkpoint->open_fx.size() : 0,
              checkpoint.has_value() && checkpoint->hold, std::nullopt,
              launch_ack_outcome(journal.value().session_id,
                                 journal.value().last_launch_ack)),
          std::nullopt);
    }
    if (journal.error().code != ErrorCode::not_found) {
      return error_envelope(journal.error());
    }
    auto recovery = projects.list_performance_recovery(path);
    if (!recovery.has_value()) {
      return error_envelope(recovery.error());
    }
    if (!recovery.value().empty()) {
      const auto &candidate = recovery.value().front().journal;
      return success_envelope(
          performance_status_json(
              "recovery_required", candidate.session_id,
              candidate.performance_id, candidate.expected_revision,
              candidate.next_flush_seq, candidate.pending_events.size(), 0, 0,
              false, std::nullopt,
              launch_ack_outcome(candidate.session_id,
                                 candidate.last_launch_ack)),
          std::nullopt);
    }
    return success_envelope(
        performance_status_json("idle", std::nullopt, std::nullopt, 0, 0, 0, 0,
                                0, false, std::nullopt, std::nullopt),
        std::nullopt);
  }

  nlohmann::json sequence_settings_update(const nlohmann::json &request) {
    const bool has_runtime_frame = request.contains( "runtime_frame");
    require(
        exact_keys(request, {"operation", "project_path", "command_id",
                             "expected_revision", "session_id", "runtime_frame",
                             "bpm", "quantize_enabled", "swing_percent"}) ||
            exact_keys(request, {"operation", "project_path", "command_id",
                                 "expected_revision", "session_id", "bpm", "quantize_enabled",
             "swing_percent"}),
        "sequence.settings.update request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto runtime_frame = has_runtime_frame
                                   ? unsigned_field(request, "runtime_frame")
                                   : std::uint64_t{0};
    std::optional<foundation::SequenceSessionId> session_id;
    if (!request.at("session_id").is_null()) {
      session_id = foundation::SequenceSessionId{
          uuid_field(request, "session_id")};
    }
    std::optional<std::uint16_t> bpm;
    if (!request.at("bpm").is_null()) {
      const auto value = unsigned_field(request, "bpm", 240);
      require(value >= 40, "Sequence BPM is invalid");
      bpm = static_cast<std::uint16_t>(value);
    }
    std::optional<bool> quantize_enabled;
    if (!request.at("quantize_enabled").is_null()) {
      require(request.at("quantize_enabled").is_boolean(),
              "Sequence Quantize is invalid");
      quantize_enabled = request.at("quantize_enabled").get<bool>();
    }
    std::optional<std::uint8_t> swing_percent;
    if (!request.at("swing_percent").is_null()) {
      const auto value = unsigned_field(request, "swing_percent", 75);
      require(value >= 50, "Sequence Swing is invalid");
      swing_percent = static_cast<std::uint8_t>(value);
    }
    require(bpm.has_value() || quantize_enabled.has_value() ||
                swing_percent.has_value(),
            "Sequence settings update is empty");

    std::lock_guard lock(sequence_mutex);
    auto performance = performance_sessions.find(sequence_key(path));
    if (performance != performance_sessions.end()) {
      require(!has_runtime_frame && session_id.has_value() &&
                  performance->second.session_id == *session_id &&
                  performance->second.expected_revision == revision,
              "Performance settings owner does not match");
      auto updated = projects.execute_performance_rebase(
          path, *session_id,
          domain::UpdateSequenceSettings{
              {foundation::CommandId{command_id}, revision},
              bpm,
              quantize_enabled,
              swing_percent});
      if (!updated.has_value()) {
        return error_envelope(updated.error());
      }
      const auto &outcome = updated.value().outcome;
      if (bpm.has_value() && !outcome.replayed && performance_clock) {
        auto tick = performance_clock->read_tick();
        if (!tick.has_value()) {
          return error_envelope(tick.error());
        }
        performance_clock->anchor(outcome.state.bpm, tick.value());
      }
      performance->second.expected_revision = outcome.state.revision;
      return success_envelope(
          {{"committed_revision", outcome.state.revision},
           {"bpm", outcome.state.bpm},
           {"quantize_enabled", outcome.state.quantize_enabled},
           {"swing_percent", outcome.state.swing_percent},
           {"replayed", outcome.replayed}},
          outcome.state.revision);
    }
    require(has_runtime_frame, "runtime_frame is required outside Performance");
    const auto found = sequence_sessions.find(sequence_key(path));
    if (found == sequence_sessions.end()) {
      require(!session_id.has_value(),
              "Sequence settings owner does not match");
    } else {
      require(session_id.has_value() &&
                  found->second.session_id == *session_id &&
                  found->second.expected_revision == revision &&
                  runtime_frame >= found->second.last_runtime_frame,
              "Sequence settings owner does not match");
      if (bpm.has_value() && found->second.pending_pattern_id.has_value()) {
        return error_envelope(sequence_error(
            ErrorCode::invalid_argument,
            "Sequence BPM cannot change while a Pattern switch is pending",
            {{"reason", "switch_pending"}}));
      }
    }
    const auto updated = projects.execute_with_identity(
        path,
        domain::Command{domain::UpdateSequenceSettings{
            domain::CommandMeta{
                foundation::CommandId{command_id}, revision},
            bpm,
            quantize_enabled,
            swing_percent,
        }});
    if (!updated.has_value()) {
      return error_envelope(updated.error());
    }
    const auto& outcome = updated.value().outcome;
    if (found != sequence_sessions.end()) {
      auto& runtime = found->second;
      if (bpm.has_value()) {
        auto anchor = audio::freeze_transport_bpm(
            runtime.anchor, runtime_frame, outcome.state.bpm);
        if (!anchor.has_value()) {
          return error_envelope(anchor.error());
        }
        runtime.anchor = anchor.value();
      }
      runtime.expected_revision = outcome.state.revision;
      runtime.quantize_enabled = outcome.state.quantize_enabled;
      runtime.swing_percent = outcome.state.swing_percent;
      runtime.last_runtime_frame = runtime_frame;
    }
    return success_envelope(
        {{"committed_revision", outcome.state.revision},
         {"bpm", outcome.state.bpm},
         {"quantize_enabled", outcome.state.quantize_enabled},
         {"swing_percent", outcome.state.swing_percent},
         {"replayed", outcome.replayed}},
        outcome.state.revision);
  }

  nlohmann::json asset_import(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "project_path",
                "command_id",
                "expected_revision",
                "asset_id",
                "source_path",
                "media_type",
            }),
        "asset.import request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto source = absolute_path_field(request, "source_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto asset_id = uuid_field(request, "asset_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto media_type = string_field(request, "media_type");
    require(!media_type.empty(), "media_type must not be empty");
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    const auto imported = projects.import_artifact_with_identity(
        path,
        project_io::ProjectStore::ImportArtifactRequest{
            domain::CommandMeta{
                foundation::CommandId{command_id},
                revision,
            },
            foundation::AssetId{asset_id},
            source,
            media_type,
        });
    if (!imported.has_value()) {
      return error_envelope(imported.error());
    }
    const auto& persisted = imported.value().command;
    const auto& applied = imported.value().outcome;
    return success_envelope(
        {
            {"asset_id", persisted.asset.id.value()},
            {"artifact", persisted.asset.artifact},
            {"committed_revision",
             applied.event.at("revision").get<std::uint64_t>()},
            {"replayed", applied.replayed},
        },
        applied.state.revision);
  }

  nlohmann::json pad_assign(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "project_path",
                "command_id",
                "expected_revision",
                "slot",
                "asset_id",
            }),
        "pad.assign request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto pad_slot = slot_value(request.at("slot"));
    std::optional<foundation::AssetId> asset_id;
    if (!request.at("asset_id").is_null()) {
      asset_id = foundation::AssetId{uuid_field(request, "asset_id")};
    }
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) {
      return error_envelope(admitted.error());
    }
    const auto assigned = projects.execute_with_identity(
        path,
        domain::Command{
            domain::AssignPad{
                {
                    foundation::CommandId{command_id},
                    revision,
                },
                pad_slot,
                asset_id,
            },
        });
    if (!assigned.has_value()) {
      return error_envelope(assigned.error());
    }
    const auto* persisted =
        std::get_if<domain::AssignPad>(&assigned.value().command);
    if (persisted == nullptr) {
      return error_envelope(
          Error{
              ErrorCode::invalid_project,
              "persisted pad assignment has the wrong command type",
          });
    }
    const auto& applied = assigned.value().outcome;
    return success_envelope(
        {
            {"slot", slot_json(persisted->slot)},
            {"asset_id",
             persisted->asset_id.has_value()
                 ? nlohmann::json(persisted->asset_id->value())
                 : nlohmann::json(nullptr)},
            {"committed_revision",
             applied.event.at("revision").get<std::uint64_t>()},
            {"replayed", applied.replayed},
        },
        applied.state.revision);
  }

  foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
  cook_project(
      const std::filesystem::path& path,
      const domain::ProjectState& project,
      const foundation::PatternId& pattern_id,
      std::optional<audio::RuntimePreparationLimits> limits = std::nullopt) {
    auto cooked = cooker::cook(
        project,
        pattern_id,
        [this, path, limits](const foundation::ArtifactRef& artifact) {
          if (limits.has_value() &&
              !limits->allows_artifact_bytes(artifact.byte_length)) {
            return foundation::Result<std::vector<std::byte>>::failure(
                runtime_preparation_limit_error(
                    "artifact_bytes",
                    artifact.byte_length,
                    limits->maximum_artifact_bytes));
          }
          auto bytes = projects.read_artifact(path, artifact);
          return bytes;
        });
    if (!cooked.has_value() || !limits.has_value()) {
      return cooked;
    }

    std::array<std::uint64_t, 4> prospective_bank_bytes{};
    std::array<std::vector<nlohmann::json>, 4> consumed{};
    std::uint64_t prospective_generation_bytes = 0;
    for (const auto& pad : cooked.value()->pads) {
      if (pad.sample == nullptr || pad.sample->channels == 0 ||
          pad.sample->interleaved.size() % pad.sample->channels != 0) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            Error{
                ErrorCode::cook_failed,
                "cooked runtime Snapshot PCM shape is invalid",
            });
      }
      const auto frames = static_cast<std::uint64_t>(
          pad.sample->interleaved.size() / pad.sample->channels);
      const auto sample_bytes = audio::checked_mono_float_bytes(frames);
      if (!sample_bytes.has_value()) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            Error{
                ErrorCode::invalid_argument,
                "runtime preparation PCM byte length overflowed",
            });
      }
      const auto assessment = audio::assess_runtime_quota(
          prospective_bank_bytes.at(pad.slot.bank),
          prospective_generation_bytes,
          sample_bytes.value(),
          *limits);
      if (!assessment.has_value()) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            Error{
                ErrorCode::invalid_argument,
                "runtime preparation quota ledger is invalid",
            });
      }
      if (assessment->constraint ==
          audio::RuntimeQuotaConstraint::user_bank) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            runtime_bank_quota_error(
                pad.slot,
                sample_bytes.value(),
                frames,
                assessment->user_bank_remaining_bytes,
                limits->maximum_user_bank_bytes,
                consumed.at(pad.slot.bank)));
      }
      if (assessment->constraint ==
          audio::RuntimeQuotaConstraint::generation) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            runtime_project_quota_error(
                sample_bytes.value(),
                frames,
                prospective_generation_bytes,
                assessment->generation_remaining_bytes,
                limits->maximum_generation_bytes,
                prospective_bank_bytes));
      }
      prospective_bank_bytes.at(pad.slot.bank) += sample_bytes.value();
      prospective_generation_bytes += sample_bytes.value();
      consumed.at(pad.slot.bank).push_back({
          {"pad", pad.slot.pad},
          {"prepared_bytes", sample_bytes.value()},
          {"prepared_frames", frames},
      });
    }
    return cooked;
  }

  nlohmann::json render_offline(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "pattern_id", "output_path"}),
        "render.offline request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto pattern_id = uuid_field(request, "pattern_id");
    const auto output = absolute_path_field(request, "output_path");
    require(
        !path_is_inside_bundle(output),
        "render output must be outside every .lmdj bundle");
    auto destination = open_render_destination(output);

    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto cooked = cook_project(
        path,
        loaded.value(),
        foundation::PatternId{pattern_id});
    if (!cooked.has_value()) {
      return error_envelope(cooked.error());
    }
    auto scratch_result = create_scratch_render(workspace_root);
    if (!scratch_result.has_value()) {
      return error_envelope(scratch_result.error());
    }
    auto scratch = std::move(scratch_result.value());
    const auto rendered = audio::render_offline(
        audio::OfflineRenderRequest{
            cooked.value(),
            scratch.path(),
        });
    if (!rendered.has_value()) {
      return error_envelope(rendered.error());
    }
    const auto verified =
        read_verified_scratch(scratch, rendered.value().artifact);
    if (!verified.has_value()) {
      return error_envelope(verified.error());
    }
    auto staging_result =
        create_temp_render(destination.parent.get());
    if (!staging_result.has_value()) {
      return error_envelope(staging_result.error());
    }
    auto staging = std::move(staging_result.value());
    const auto staged = write_verified_staging(
        staging, verified.value());
    if (!staged.has_value()) {
      return error_envelope(staged.error());
    }
    if (::linkat(
            destination.parent.get(),
            staging.name().c_str(),
            destination.parent.get(),
            destination.filename.c_str(),
            0) != 0) {
      return error_envelope(
          Error{
              ErrorCode::io_error,
              "render output could not be atomically published",
              {
                  {"path", output.generic_string()},
                  {"system_error", std::strerror(errno)},
              },
          });
    }
    staging.published();
    return success_envelope(
        {
            {"artifact", verified.value().artifact},
            {"output_path", output.generic_string()},
            {"frame_count", rendered.value().frame_count},
            {"sample_rate", rendered.value().sample_rate},
            {"channels", rendered.value().channels},
        },
        loaded.value().revision);
  }

  nlohmann::json provider_permissions_configure(const nlohmann::json& request) {
    require(exact_keys(request, {"operation", "granted_permissions"}),
            "provider.permissions.configure request shape is invalid");
    const auto& encoded = request.at("granted_permissions");
    require(encoded.is_array(), "granted_permissions must be an array");
    std::set<std::string> known;
    for (const auto& descriptor : registry->list()) {
      for (const auto& capability : descriptor.capabilities) {
        known.insert(capability.policy.required_permissions.begin(),
                     capability.policy.required_permissions.end());
      }
    }
    std::set<std::string> unique;
    std::vector<std::string> permissions;
    for (const auto& value : encoded) {
      require(value.is_string(), "permission must be a string");
      const auto permission = value.get<std::string>();
      require(known.contains(permission), "permission is not registered");
      require(unique.insert(permission).second, "permissions must be unique");
      permissions.push_back(permission);
    }
    auto policy = provider_policy;
    policy.granted_permissions = permissions;
    // Policy is session-local; selections and terminal Attempts remain in the
    // existing Workspace store. Preserve the timestamp callable's state too.
    attempts = provider::AttemptStore{
        workspace_root, policy, [this] { return provider_timestamp_source(); }};
    provider_policy = std::move(policy);
    return success_envelope({{"granted_permissions", permissions}}, std::nullopt);
  }

  nlohmann::json provider_select(const nlohmann::json& request) {
    require(
        exact_keys(
            request, {"operation", "capability", "provider_id"}),
        "provider.select request shape is invalid");
    const auto capability = file_id_field(request, "capability");
    const auto provider_id = file_id_field(request, "provider_id");
    const auto selected = attempts.set_provider_selection(
        capability, provider_id, *registry);
    if (!selected.has_value()) {
      return error_envelope(selected.error());
    }
    return success_envelope(
        {
            {"capability", capability},
            {"provider_id", provider_id},
        },
        std::nullopt);
  }

  foundation::Result<CandidateAuditionAudio> audition_candidate(
      const CandidateAuditionRequest& request) {
    using Result = foundation::Result<CandidateAuditionAudio>;
    // Apply the same selector validation to typed and JSON callers.
    const nlohmann::json selector{
        {"project_path", request.project_path.generic_string()},
        {"project_id", request.project_id.value()},
        {"expected_revision", request.expected_revision},
        {"job_id", request.job_id}, {"set_id", request.set_id},
        {"candidate_id", request.candidate_id}};
    const auto path = absolute_path_field(selector, "project_path");
    (void)uuid_field(selector, "project_id");
    (void)unsigned_field(selector, "expected_revision");
    (void)file_id_field(selector, "job_id");
    (void)file_id_field(selector, "set_id");
    (void)file_id_field(selector, "candidate_id");
    // Retain the existing Workspace eligibility ownership until preparation
    // and the final owner/byte checks finish. lease_active never recovers.
    auto eligible = candidates.lease_active(request.job_id, request.set_id, attempts);
    if (!eligible.has_value()) return Result::failure(eligible.error());
    const auto& set = eligible.value().candidate_set;
    const auto& source = set.at("source");
    if (source.at("project_id") != request.project_id.value())
      return Result::failure(Error{ErrorCode::revision_conflict, "Candidate belongs to another Project"});
    const auto source_id = foundation::AssetId{source.at("asset_id").get<std::string>()};
    const auto artifact = source.at("artifact").get<foundation::ArtifactRef>();
    const auto validate_current = [&]() -> foundation::Result<void> {
      const auto current = projects.inspect_committed(path);
      if (!current.has_value()) return foundation::Result<void>::failure(current.error());
      return domain::validate_candidate_source(current.value(), request.project_id,
          request.expected_revision, source_id, artifact);
    };
    const auto fresh = validate_current();
    if (!fresh.has_value()) return Result::failure(fresh.error());
    const auto& recipes = set.at("recipes");
    const auto recipe = std::find_if(recipes.begin(), recipes.end(), [&](const auto& value) {
      return value.at("candidate_id") == request.candidate_id;
    });
    if (recipe == recipes.end()) return Result::failure(Error{ErrorCode::not_found,
        "Candidate recipe is unavailable", {{"reason", "candidate_unavailable"}}});
    if (!sample_limits || artifact.byte_length > 16777216U)
      return Result::failure(invalid_sample_request("Candidate source exceeds preparation byte limit"));
    const auto bytes = projects.read_asset_artifact(path, request.project_id, source_id, artifact);
    if (!bytes.has_value()) return Result::failure(bytes.error());
    const auto metadata = cooker::inspect_wav(bytes.value());
    if (!metadata.has_value()) return Result::failure(metadata.error());
    if (metadata.value().sample_rate != source.at("frame_rate") ||
        metadata.value().source_frames != source.at("frame_count"))
      return Result::failure(Error{ErrorCode::revision_conflict, "Candidate source metadata changed",
          {{"reason", "candidate_source_changed"}}});
    const auto interval = cooker::select_pcm16_wav(bytes.value(),
        recipe->at("start_frame").get<std::uint64_t>(),
        recipe->at("end_frame").get<std::uint64_t>());
    if (!interval.has_value()) return Result::failure(interval.error());
    if (!sample_limits->allows_artifact_bytes(interval.value().size()))
      return Result::failure(invalid_sample_request("Candidate Artifact exceeds preparation byte limit"));
    const auto decoded = cooker::decode_wav(interval.value());
    if (!decoded.has_value()) return Result::failure(decoded.error());
    auto prepared = decoded.value();
    if (prepared->sample_rate != 48'000) {
      auto resampled = cooker::prepare_runtime_pcm(*prepared);
      if (!resampled.has_value()) return Result::failure(resampled.error());
      prepared = std::move(resampled.value());
    }
    // Re-read verified source bytes after preparation, then validate the
    // current expected revision. Neither Project read performs load recovery.
    const auto final_bytes = projects.read_asset_artifact(path, request.project_id, source_id, artifact);
    if (!final_bytes.has_value()) return Result::failure(final_bytes.error());
    const auto final_current = validate_current();
    if (!final_current.has_value()) return Result::failure(final_current.error());
    const auto& selected = interval.value();
    return Result::success(CandidateAuditionAudio{
        {canonical_manifest_digest(std::string_view{
             reinterpret_cast<const char*>(selected.data()), selected.size()}),
         "audio/wav", static_cast<std::uint64_t>(selected.size())},
        decoded.value()->sample_rate, decoded.value()->channels,
        static_cast<std::uint64_t>(decoded.value()->interleaved.size() / decoded.value()->channels),
        std::move(prepared)});
  }

  nlohmann::json candidate_audition(const nlohmann::json& request) {
    require(exact_keys(request, {"operation", "project_path", "project_id",
        "expected_revision", "job_id", "set_id", "candidate_id"}),
        "candidate.audition request shape is invalid");
    const auto revision = unsigned_field(request, "expected_revision");
    const CandidateAuditionRequest typed{absolute_path_field(request, "project_path"),
        foundation::ProjectId{uuid_field(request, "project_id")}, revision,
        file_id_field(request, "job_id"), file_id_field(request, "set_id"),
        file_id_field(request, "candidate_id")};
    const auto audio = audition_candidate(typed);
    if (!audio.has_value()) return error_envelope(audio.error());
    return success_envelope({{"job_id", typed.job_id}, {"set_id", typed.set_id},
        {"candidate_id", typed.candidate_id}, {"artifact", audio.value().artifact},
        {"sample_rate", audio.value().sample_rate}, {"channels", audio.value().channels},
        {"source_frames", audio.value().source_frames}}, revision);
  }

  nlohmann::json candidate_adopt(const nlohmann::json& request) {
    require(exact_keys(request, {"operation", "project_path", "project_id",
        "expected_revision", "command_id", "job_id", "set_id", "selections"}),
        "candidate.adopt request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto project_id = foundation::ProjectId{uuid_field(request, "project_id")};
    const auto revision = unsigned_field(request, "expected_revision");
    const auto command_id = uuid_field(request, "command_id");
    const auto job_id = file_id_field(request, "job_id");
    const auto set_id = file_id_field(request, "set_id");
    const auto& selections = request.at("selections");
    require(selections.is_array() && !selections.empty() && selections.size() <= 64,
        "adoption requires a nonempty explicit Pad list");
    std::map<std::pair<std::uint8_t, std::uint8_t>, std::string> targets;
    for (const auto& selection : selections) {
      require(exact_keys(selection, {"candidate_id", "bank", "pad"}), "adoption selection shape is invalid");
      const auto bank = static_cast<std::uint8_t>(unsigned_field(selection, "bank", 3));
      const auto pad = static_cast<std::uint8_t>(unsigned_field(selection, "pad", 15));
      require(targets.emplace(std::make_pair(bank, pad), file_id_field(selection, "candidate_id")).second,
          "adoption targets must be unique");
    }
    auto admitted = admit_non_sequence_authoring(path);
    if (!admitted.has_value()) return error_envelope(admitted.error());
    auto eligible = candidates.lease_active(job_id, set_id, attempts);
    if (!eligible.has_value()) return error_envelope(eligible.error());
    const auto& set = eligible.value().candidate_set;
    const auto& source = set.at("source");
    if (source.at("project_id") != project_id.value())
      return error_envelope(Error{ErrorCode::revision_conflict, "Candidate belongs to another Project"});
    const auto source_id = foundation::AssetId{source.at("asset_id").get<std::string>()};
    const auto artifact = source.at("artifact").get<foundation::ArtifactRef>();
    const auto loaded = projects.inspect_committed(path);
    if (!loaded.has_value()) return error_envelope(loaded.error());
    const auto fresh = domain::validate_candidate_source(loaded.value(), project_id,
        revision, source_id, artifact);
    if (!fresh.has_value()) return error_envelope(fresh.error());
    std::map<std::string, nlohmann::json> recipes;
    for (const auto& recipe : set.at("recipes"))
      recipes.emplace(recipe.at("candidate_id").get<std::string>(), recipe);
    for (const auto& [target, id] : targets) {
      (void)target;
      if (!recipes.contains(id)) return error_envelope(Error{ErrorCode::not_found,
          "Candidate recipe is unavailable", {{"reason", "candidate_unavailable"}}});
    }
    // All identities and targets were checked before source read/materialization.
    const auto bytes = projects.read_asset_artifact(path, project_id, source_id, artifact);
    if (!bytes.has_value()) return error_envelope(bytes.error());
    const auto metadata = cooker::inspect_wav(bytes.value());
    if (!metadata.has_value()) return error_envelope(metadata.error());
    if (metadata.value().sample_rate != source.at("frame_rate") ||
        metadata.value().source_frames != source.at("frame_count"))
      return error_envelope(Error{ErrorCode::revision_conflict, "Candidate source metadata changed",
          {{"reason", "candidate_source_changed"}}});
    if (!sample_limits) return error_envelope(invalid_sample_request("Sample quota is unavailable"));
    auto final_baseline = loaded.value();
    for (const auto& [target, id] : targets) {
      (void)id;
      final_baseline.banks.at(target.first).at(target.second).asset_id.reset();
    }
    auto ledger = compute_bank_ledger(path, final_baseline, 0, 0);
    if (!ledger.has_value()) return error_envelope(ledger.error());
    // Recipes partition the bounded source. Own one buffer per selected
    // recipe, while every target still receives its own identity and charge.
    std::map<std::string, std::vector<std::byte>> materialized;
    std::vector<project_io::ProjectStore::CandidateAdoptionSlotRequest> slots;
    auto adopted = nlohmann::json::array();
    for (const auto& [target, id] : targets) {
      const auto& recipe = recipes.at(id);
      auto selected = materialized.find(id);
      if (selected == materialized.end()) {
        auto interval = cooker::select_pcm16_wav(bytes.value(),
            recipe.at("start_frame").get<std::uint64_t>(), recipe.at("end_frame").get<std::uint64_t>());
        if (!interval.has_value()) return error_envelope(interval.error());
        selected = materialized.emplace(id, std::move(interval.value())).first;
      }
      if (!sample_limits->allows_artifact_bytes(selected->second.size()))
        return error_envelope(invalid_sample_request("Candidate Artifact exceeds preparation byte limit"));
      const auto measured = measure_prepared_quota(selected->second);
      if (!measured.has_value()) return error_envelope(measured.error());
      const auto& usage = measured.value();
      const auto assessment = audio::assess_runtime_quota(
          ledger.value().bank_used_bytes.at(target.first), ledger.value().project_used_bytes,
          usage.bytes, *sample_limits);
      if (!assessment) return error_envelope(Error{ErrorCode::invalid_project, "Candidate quota ledger is invalid"});
      if (assessment->constraint == audio::RuntimeQuotaConstraint::user_bank)
        return error_envelope(runtime_bank_quota_error({target.first, target.second},
            usage.bytes, usage.frames, assessment->user_bank_remaining_bytes,
            sample_limits->maximum_user_bank_bytes, {}));
      if (assessment->constraint == audio::RuntimeQuotaConstraint::generation)
        return error_envelope(runtime_project_quota_error(usage.bytes, usage.frames,
            ledger.value().project_used_bytes, assessment->generation_remaining_bytes,
            sample_limits->maximum_generation_bytes, ledger.value().bank_used_bytes));
      ledger.value().bank_used_bytes.at(target.first) += usage.bytes;
      ledger.value().project_used_bytes += usage.bytes;
      auto lineage_recipe = recipe;
      lineage_recipe.erase("candidate_id");
      auto lineage = domain::asset_lineage_from_json({
          {"source", {{"kind", "asset_artifact"}, {"artifact_sha256", artifact.sha256},
                      {"project_revision", source.at("project_revision")}}},
          {"derivation", {{"kind", "capability_adoption"}, {"capability", set.at("capability")},
              {"provider", set.at("provider")}, {"model_identity", set.at("model_identity")},
              {"parameters_sha256", set.at("parameters_sha256")}, {"attempt_id", set.at("attempt_id")},
              {"source_asset_id", source_id.value()}, {"output_artifact", set.at("output_artifact")},
              {"recipe", std::move(lineage_recipe)}}}});
      if (!lineage.has_value()) return error_envelope(lineage.error());
      const auto asset_id = candidate_asset_id(command_id, id, target.first, target.second);
      slots.push_back({{target.first, target.second}, foundation::AssetId{asset_id}, "audio/wav",
          selected->second, std::move(lineage.value())});
      adopted.push_back({{"candidate_id", id}, {"bank", target.first}, {"pad", target.second}, {"asset_id", asset_id}});
    }
    const auto committed = projects.adopt_candidates(path, {{foundation::CommandId{command_id}, revision},
        project_id, source_id, artifact, std::move(slots)});
    if (!committed.has_value()) return error_envelope(committed.error());
    return success_envelope({{"set_id", set_id}, {"adopted", std::move(adopted)}}, committed.value().state.revision);
  }

  nlohmann::json candidate_job_cancel(const nlohmann::json& request) {
    require(exact_keys(request, {"operation", "job_id", "attempt_id"}),
            "candidate.job.cancel request shape is invalid");
    const auto result = candidates.cancel(file_id_field(request, "job_id"),
                                           file_id_field(request, "attempt_id"));
    if (!result.has_value()) return error_envelope(result.error());
    return success_envelope(result.value(), std::nullopt);
  }

  nlohmann::json candidate_set_discard(const nlohmann::json& request) {
    require(exact_keys(request, {"operation", "job_id", "set_id"}),
            "candidate.set.discard request shape is invalid");
    const auto result = candidates.discard(file_id_field(request, "job_id"),
                                            file_id_field(request, "set_id"));
    if (!result.has_value()) return error_envelope(result.error());
    return success_envelope(result.value(), std::nullopt);
  }

  nlohmann::json candidate_job_inspect(const nlohmann::json& request) {
    require(exact_keys(request, {"operation", "job_id"}),
            "candidate.job.inspect request shape is invalid");
    const auto result = candidates.inspect(file_id_field(request, "job_id"), attempts);
    if (!result.has_value()) return error_envelope(result.error());
    return success_envelope(result.value(), std::nullopt);
  }

  nlohmann::json candidate_job_run(const nlohmann::json& request) {
    require(exact_keys(request, {"operation", "job_id", "attempt_id", "project_path",
        "project_id", "asset_id", "expected_revision", "parameters", "data_classification",
        "platform", "region", "required_permissions"}),
        "candidate.job.run request shape is invalid");
    const auto job_id = file_id_field(request, "job_id");
    const auto attempt_id = file_id_field(request, "attempt_id");
    const auto path = absolute_path_field(request, "project_path");
    const auto project_id = foundation::ProjectId{uuid_field(request, "project_id")};
    const auto asset_id = foundation::AssetId{uuid_field(request, "asset_id")};
    const auto revision = unsigned_field(request, "expected_revision");
    require(request.at("parameters").is_object(), "parameters must be an object");
    const auto classification = file_id_field(request, "data_classification");
    const auto platform = file_id_field(request, "platform");
    const auto region = file_id_field(request, "region");
    const auto& permissions = request.at("required_permissions");
    require(permissions.is_array(), "required_permissions must be an array");
    std::set<std::string> unique;
    for (const auto& permission : permissions) {
      require(permission.is_string() && safe_file_id(permission.get<std::string>()), "permission is invalid");
      require(unique.insert(permission.get<std::string>()).second, "permissions must be unique");
    }
    const auto admitted = attempts.validate_execution_policy(
        provider::CapabilityRequest{"sample.slice.v1", {}, request.at("parameters"),
            classification, platform, region, permissions.get<std::vector<std::string>>()},
        *registry);
    if (!admitted.has_value()) return error_envelope(admitted.error());
    // Inspect first so an interrupted prior run can be explicitly retried with
    // a fresh Attempt ID; a live executor's Job lease still refuses begin.
    const auto prior = candidates.inspect(job_id, attempts);
    if (!prior.has_value() && prior.error().details.value("reason", "") != "job_not_found")
      return error_envelope(prior.error());
    if (prior.has_value()) {
      for (const auto& entry : prior.value().at("history"))
        if (entry.at("status") == "pending") return error_envelope(Error{
            ErrorCode::invalid_argument, "Candidate Job is already running", {{"reason", "job_busy"}}});
    }
    const auto loaded = projects.inspect_committed(path);
    if (!loaded.has_value()) return error_envelope(loaded.error());
    if (loaded.value().id != project_id || loaded.value().revision != revision)
      return error_envelope(Error{ErrorCode::revision_conflict, "Analysis Project identity or revision changed"});
    const auto found = loaded.value().assets.find(asset_id);
    if (found == loaded.value().assets.end()) return error_envelope(Error{
        ErrorCode::not_found, "Analysis source Asset is missing", {{"reason", "source_asset_missing"}}});
    const auto& artifact = found->second.artifact;
    require(artifact.byte_length <= 16777216, "Slice source exceeds input byte bound");
    const auto bytes = projects.read_asset_artifact(path, project_id, asset_id, artifact);
    if (!bytes.has_value()) return error_envelope(bytes.error());
    const auto metadata = cooker::inspect_wav(bytes.value());
    if (!metadata.has_value()) return error_envelope(metadata.error());
    nlohmann::json intent{{"attempt_id", attempt_id},
      {"source", {{"project_path", path.generic_string()}, {"project_id", project_id.value()},
                   {"asset_id", asset_id.value()}, {"project_revision", revision}, {"artifact", artifact},
                   {"frame_rate", metadata.value().sample_rate}, {"frame_count", metadata.value().source_frames}}},
      {"parameters_sha256", picosha2::hash256_hex_string(foundation::canonical_json(request.at("parameters")))},
      {"data_classification", classification}, {"platform", platform}, {"region", region},
      {"required_permissions", permissions}};
    std::optional<detail::CandidateStore::Run> run;
    const auto reserved = [&]() -> foundation::Result<void> {
      auto begun = candidates.begin(job_id, intent);
      if (!begun.has_value()) return foundation::Result<void>::failure(begun.error());
      run.emplace(std::move(begun.value()));
      return foundation::Result<void>::success();
    };
    const auto executed = provider_run({{"operation", "provider.run"}, {"attempt_id", attempt_id},
        {"capability", "sample.slice.v1"},
        {"inputs", nlohmann::json::array({{{"port", "source_audio"}, {"artifact", artifact}}})},
        {"input_owners", nlohmann::json::array({{{"port", "source_audio"}, {"occurrence", 0},
            {"project_path", path.generic_string()}, {"project_id", project_id.value()}, {"asset_id", asset_id.value()}}})},
        {"parameters", request.at("parameters")}, {"data_classification", classification},
        {"platform", platform}, {"region", region}, {"required_permissions", permissions}}, reserved);
    // No owner intent exists unless this execution won the immutable SDK
    // reservation. In particular, a duplicate raw Provider run cannot donate
    // its terminal to this Job, including after process restart.
    if (!run) return executed;
    const auto finished = candidates.finish(*run, attempts);
    if (!finished.has_value()) return error_envelope(finished.error());
    if (!executed.at("ok").get<bool>()) return executed;
    return success_envelope(finished.value(), std::nullopt);
  }

  nlohmann::json provider_run(const nlohmann::json& request,
      const std::function<foundation::Result<void>()>& after_reservation = {}) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "attempt_id",
                "capability",
                "inputs",
                "parameters",
                "data_classification",
                "platform",
                "region",
                "required_permissions",
            }) ||
        exact_keys(request, {"operation", "attempt_id", "capability", "inputs",
                             "parameters", "data_classification", "platform",
                             "region", "required_permissions", "input_owners"}),
        "provider.run request shape is invalid");
    const auto attempt_id = file_id_field(request, "attempt_id");
    const auto capability = file_id_field(request, "capability");
    const auto classification =
        file_id_field(request, "data_classification");
    const auto platform = file_id_field(request, "platform");
    const auto region = file_id_field(request, "region");
    const auto& encoded_inputs = request.at("inputs");
    require(encoded_inputs.is_array(), "inputs must be an array");
    std::vector<provider::ArtifactBinding> inputs;
    std::set<std::string> input_hashes;
    for (const auto& input : encoded_inputs) {
      require(
          exact_keys(input, {"port", "artifact"}),
          "input Artifact binding shape is invalid");
      require(input.at("port").is_string(), "input port is invalid");
      const auto port = string_field(input, "port");
      require(provider::valid_port_name(port), "input port is invalid");
      const auto& encoded_artifact = input.at("artifact");
      require(
          exact_keys(
              encoded_artifact,
              {"sha256", "media_type", "byte_length"}),
          "input Artifact shape is invalid");
      require(
          encoded_artifact.at("sha256").is_string() &&
              encoded_artifact.at("media_type").is_string(),
          "input Artifact strings are invalid");
      foundation::ArtifactRef artifact{
          string_field(encoded_artifact, "sha256"),
          string_field(encoded_artifact, "media_type"),
          unsigned_field(encoded_artifact, "byte_length"),
      };
      require(
          artifact.sha256.size() == 64 &&
              std::all_of(
                  artifact.sha256.begin(),
                  artifact.sha256.end(),
                  [](unsigned char character) {
                    return (character >= '0' && character <= '9') ||
                           (character >= 'a' && character <= 'f');
                  }),
          "input Artifact hash is invalid");
      require(
          !artifact.media_type.empty(),
          "input Artifact media type is empty");
      require(
          input_hashes.insert(artifact.sha256).second,
          "input Artifact hashes must be unique");
      inputs.push_back(provider::ArtifactBinding{
          port,
          std::move(artifact),
      });
    }
    provider::ArtifactResolver resolver;
    if (request.contains("input_owners")) {
      const auto& encoded_owners = request.at("input_owners");
      require(encoded_owners.is_array() && encoded_owners.size() == inputs.size(),
              "input_owners must name every input occurrence exactly once");
      struct Owner {
        foundation::ArtifactRef artifact;
        std::filesystem::path path;
        foundation::ProjectId project;
        foundation::AssetId asset;
      };
      std::map<std::string, std::uint64_t> occurrences;
      std::map<std::pair<std::string, std::uint64_t>, foundation::ArtifactRef> bindings;
      for (const auto& input : inputs) {
        bindings.emplace(std::pair{input.port, occurrences[input.port]++}, input.artifact);
      }
      std::map<std::string, Owner> owners;
      for (const auto& encoded : encoded_owners) {
        require(exact_keys(encoded, {"port", "occurrence", "project_path",
                                     "project_id", "asset_id"}),
                "input owner shape is invalid");
        const auto key = std::pair{string_field(encoded, "port"),
                                   unsigned_field(encoded, "occurrence")};
        const auto bound = bindings.find(key);
        require(bound != bindings.end(), "input owner occurrence is unbound or duplicated");
        const auto artifact = bound->second;
        owners.emplace(artifact.sha256,
            Owner{artifact, absolute_path_field(encoded, "project_path"),
                  foundation::ProjectId{uuid_field(encoded, "project_id")},
                  foundation::AssetId{uuid_field(encoded, "asset_id")}});
        bindings.erase(bound);
      }
      resolver = [this, owners = std::move(owners)](const foundation::ArtifactRef& artifact) {
        using OwnedBytes = foundation::Result<std::shared_ptr<const std::vector<std::byte>>>;
        const auto found = owners.find(artifact.sha256);
        if (found == owners.end() || found->second.artifact != artifact) {
          return OwnedBytes::failure(Error{ErrorCode::not_found, "input owner unavailable"});
        }
        const auto& owner = found->second;
        auto bytes = projects.read_asset_artifact(
            owner.path, owner.project, owner.asset, artifact);
        if (!bytes.has_value()) {
          const bool mismatch = bytes.error().details.is_object() &&
              bytes.error().details.value("storage_condition", nlohmann::json{}) ==
                  project_io::kStorageConditionArtifactMismatch;
          return OwnedBytes::failure(Error{
              mismatch ? ErrorCode::io_error : ErrorCode::not_found,
              "input Artifact owner read failed",
              {{"reason", mismatch ? "input_artifact_mismatch" : "input_artifact_unavailable"}},
          });
        }
        return OwnedBytes::success(
            std::make_shared<const std::vector<std::byte>>(std::move(bytes.value())));
      };
    }
    const auto& encoded_permissions = request.at("required_permissions");
    require(
        encoded_permissions.is_array(),
        "required_permissions must be an array");
    std::vector<std::string> permissions;
    std::set<std::string> unique_permissions;
    for (const auto& encoded : encoded_permissions) {
      require(encoded.is_string(), "permission must be a string");
      const auto value = encoded.get<std::string>();
      require(safe_file_id(value), "permission is invalid");
      require(
          unique_permissions.insert(value).second,
          "permissions must be unique");
      permissions.push_back(value);
    }
    const auto& parameters = request.at("parameters");
    require(
        parameters.is_object(),
        "parameters must be an object");
    const auto executed = attempts.execute(
        foundation::AttemptId{attempt_id},
        provider::CapabilityRequest{
            capability,
            std::move(inputs),
            parameters,
            classification,
            platform,
            region,
            std::move(permissions),
        },
        *registry,
        provider::ExecutionOptions{
            std::move(resolver), 16777216, 262144,
            std::make_shared<provider::StagingBudget>(67108864)}, after_reservation);
    if (!executed.has_value()) {
      return error_envelope(executed.error());
    }
    if (executed.value().error.has_value()) {
      auto error = *executed.value().error;
      error.details["attempt_id"] = attempt_id;
      return error_envelope(error);
    }
    require(
        executed.value().candidate.has_value(),
        "Provider result has no Candidate");
    const auto& candidate = *executed.value().candidate;
    return success_envelope(
        {
            {"attempt_id", attempt_id},
            {"candidate_id", candidate.id.value()},
            {"outputs", candidate.outputs},
            {"provenance", candidate.provenance},
        },
        std::nullopt);
  }

  nlohmann::json project_inspect(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "project_path"}),
        "project.inspect request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    return success_envelope(
        {{"project", project_json(loaded.value())}},
        loaded.value().revision);
  }

  nlohmann::json snapshot_cook(const nlohmann::json& request) {
    require(
        exact_keys(
            request, {"operation", "project_path", "pattern_id"}),
        "snapshot.cook request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto pattern_id = uuid_field(request, "pattern_id");
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto cooked = cook_project(
        path,
        loaded.value(),
        foundation::PatternId{pattern_id});
    if (!cooked.has_value()) {
      return error_envelope(cooked.error());
    }
    std::set<std::string> hashes;
    const auto pattern =
        loaded.value().patterns.find(foundation::PatternId{pattern_id});
    if (pattern != loaded.value().patterns.end()) {
      for (const auto& event : pattern->second.events) {
        const auto asset =
            domain::resolve_slot_asset(loaded.value(), event.slot);
        if (asset.has_value()) {
          hashes.insert(asset->artifact.sha256);
        }
      }
    }
    return success_envelope(
        {
            {"pattern_id", pattern_id},
            {"event_count", cooked.value()->events.size()},
            {"artifact_sha256s", hashes},
        },
        loaded.value().revision);
  }

  nlohmann::json provider_list(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation"}),
        "provider.list request shape is invalid");
    auto providers = nlohmann::json::array();
    for (const auto& descriptor : registry->list()) {
      providers.push_back(provider_descriptor_json(descriptor));
    }
    return success_envelope(
        {{"providers", std::move(providers)},
         {"granted_permissions", provider_policy.granted_permissions}},
        std::nullopt);
  }

  nlohmann::json provider_selected(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "capability"}),
        "provider.selected request shape is invalid");
    const auto capability = file_id_field(request, "capability");
    const auto selected = attempts.selected_provider(capability);
    if (!selected.has_value()) {
      return error_envelope(selected.error());
    }
    return success_envelope(
        {
            {"capability", capability},
            {"provider_id", selected.value()},
        },
        std::nullopt);
  }

  // ---------------------------------------------------------------- Sound Set

  // Best effort by design (S11-D7): a Catalog that cannot be read is not an
  // error, it is simply no index this call. Every Set already published in the
  // Workspace Set Store stays usable, and its eligibility is then decided by
  // its own manifest, exactly as #465 Q1 case 5 requires.
  std::optional<std::vector<project_io::SoundSetCatalogEntry>>
  read_catalog_entries() const {
    if (!soundset_source) {
      return std::nullopt;
    }
    const auto bytes = soundset_source->read_index(
        soundset_limits.maximum_soundset_manifest_bytes);
    if (!bytes.has_value()) {
      return std::nullopt;
    }
    return parse_soundset_catalog_index(
        std::string_view(
            reinterpret_cast<const char*>(bytes.value().data()),
            bytes.value().size()));
  }

  static std::optional<foundation::CatalogLicenseSummary>
  catalog_summary_for(
      const std::optional<std::vector<project_io::SoundSetCatalogEntry>>&
          entries,
      std::string_view set_id,
      std::string_view version,
      std::string_view manifest_sha256) {
    if (!entries.has_value()) {
      return std::nullopt;
    }
    for (const auto& entry : entries.value()) {
      if (entry.set_id == set_id && entry.version == version &&
          entry.manifest_sha256 == manifest_sha256) {
        return entry.license_summary;
      }
    }
    return std::nullopt;
  }

  // A Set the Catalog declares becomes available by being acquired; a Set that
  // fails to acquire simply does not appear. One Set's fault never hides the
  // Catalog's other entries, and none of it touches a Project.
  nlohmann::json refresh_soundset_store(
      const std::vector<project_io::SoundSetCatalogEntry>& entries) {
    auto refused = nlohmann::json::array();
    if (!soundset_transport) {
      return refused;
    }
    for (const auto& entry : entries) {
      const auto acquired = soundset_sets.acquire(*soundset_transport, entry);
      if (!acquired.has_value()) {
        refused.push_back(soundset_refusal_json(entry, acquired.error()));
      }
    }
    return refused;
  }

  // S11-D3 on every occupied slot and on the optional set-level demo. The
  // whole Set is decided before anything is reported, so a Set with one bad
  // blob is refused as a whole rather than half-described.
  struct SoundSetSlotAudio {
    std::vector<std::byte> bytes;
    DecodedAudio audio;
  };

  // The whole Set's audio, decoded once: every occupied slot, plus the
  // optional S11-D5 set-level `demo`. The demo's measurement is kept rather
  // than dropped so `soundset.audition` can report the geometry of the exact
  // bytes it resolved without reading the blob a second time.
  struct DecodedSoundSetAudio {
    std::array<std::optional<SoundSetSlotAudio>, 16> slots;
    std::optional<DecodedAudio> demo;
  };

  // Every occupied slot of a Set, read once and decoded once. S11-D3 makes
  // this the whole Set's decision: a Set with one blob that is not S8-D6 is
  // refused wherever it is used, so `install` cannot admit under
  // `occupied_pad_policy: keep` what `inspect` refuses. Install then reuses
  // these bytes for the Pads it writes rather than decoding a second time.
  foundation::Result<DecodedSoundSetAudio>
  decode_soundset_audio(
      const project_io::StoredSoundSet& stored,
      std::string_view manifest_sha256) const {
    using Decoded = DecodedSoundSetAudio;
    Decoded decoded;
    for (const auto& slot : stored.manifest.slots) {
      if (!slot.occupied.has_value()) {
        continue;
      }
      const auto index = static_cast<std::uint8_t>(slot.index);
      auto bytes = soundset_sets.read_artifact(
          manifest_sha256, slot.occupied->artifact.sha256);
      if (!bytes.has_value()) {
        return foundation::Result<Decoded>::failure(
            soundset_artifact_error(bytes.error()));
      }
      const auto measured = measure_decoded_audio(bytes.value());
      if (!measured.has_value()) {
        return foundation::Result<Decoded>::failure(
            soundset_audio_error(measured.error(), index));
      }
      decoded.slots.at(index) =
          SoundSetSlotAudio{std::move(bytes.value()), measured.value()};
    }
    // S11-D5's set-level demo is under the same S8-D6 constraint. It is not a
    // slot, so its refusal carries no slot_index.
    if (stored.manifest.demo.has_value()) {
      const auto bytes = soundset_sets.read_artifact(
          manifest_sha256, stored.manifest.demo->sha256);
      if (!bytes.has_value()) {
        return foundation::Result<Decoded>::failure(
            soundset_artifact_error(bytes.error()));
      }
      const auto measured = measure_decoded_audio(bytes.value());
      if (!measured.has_value()) {
        return foundation::Result<Decoded>::failure(Error{
            ErrorCode::unsupported_audio,
            measured.error().message,
            {{"reason", kSoundSetReasonAudioUnsupported}},
        });
      }
      decoded.demo = measured.value();
    }
    return foundation::Result<Decoded>::success(std::move(decoded));
  }

  static nlohmann::json soundset_slots_json(
      const project_io::StoredSoundSet& stored,
      const std::array<std::optional<SoundSetSlotAudio>, 16>& decoded) {
    auto slots = nlohmann::json::array();
    for (const auto& slot : stored.manifest.slots) {
      const auto index = static_cast<std::size_t>(slot.index);
      nlohmann::json encoded{{"slot", slot.index}};
      if (!slot.occupied.has_value()) {
        encoded["occupied"] = false;
        slots.push_back(std::move(encoded));
        continue;
      }
      const auto& audio = decoded.at(index)->audio;
      encoded["occupied"] = true;
      encoded["role"] = slot.occupied->role;
      encoded["name"] = slot.occupied->name;
      encoded["artifact"] = soundset_artifact_json(slot.occupied->artifact);
      encoded["bpm"] = slot.occupied->bpm.has_value()
                           ? nlohmann::json(*slot.occupied->bpm)
                           : nlohmann::json(nullptr);
      encoded["key"] = slot.occupied->key.has_value()
                           ? nlohmann::json(*slot.occupied->key)
                           : nlohmann::json(nullptr);
      encoded["audio"] = {
          {"sample_rate", audio.sample_rate},
          {"channels", audio.channels},
          {"source_frames", audio.source_frames},
          {"prepared_bytes", audio.prepared.bytes},
          {"prepared_frames", audio.prepared.frames},
      };
      slots.push_back(std::move(encoded));
    }
    return slots;
  }

  struct ResolvedSoundSet {
    project_io::StoredSoundSet stored;
    std::string manifest_sha256;
  };

  // Read a published Set and decide its eligibility against whatever the
  // Catalog currently declares about it. Reachable Catalog plus a
  // `license_summary` that differs from the verified manifest is
  // PERMISSION_DENIED; unreachable Catalog leaves the cached manifest as the
  // sole authority.
  foundation::Result<ResolvedSoundSet> resolve_soundset(
      const nlohmann::json& request) const {
    const auto set_id = uuid_field(request, "set_id");
    const auto version = string_field(request, "version");
    require(semver_string(version), "version must be a SemVer string");
    const auto manifest_sha256 = string_field(request, "manifest_sha256");
    require(
        lowercase_sha256(manifest_sha256),
        "manifest_sha256 must be 64 lowercase hex characters");
    auto stored = soundset_sets.read(set_id, version, manifest_sha256);
    if (!stored.has_value()) {
      return foundation::Result<ResolvedSoundSet>::failure(stored.error());
    }
    const auto eligible = foundation::check_soundset_eligibility(
        stored.value().manifest,
        catalog_summary_for(
            read_catalog_entries(), set_id, version, manifest_sha256));
    if (!eligible.has_value()) {
      return foundation::Result<ResolvedSoundSet>::failure(eligible.error());
    }
    return foundation::Result<ResolvedSoundSet>::success(
        ResolvedSoundSet{std::move(stored.value()), manifest_sha256});
  }

  nlohmann::json soundset_catalog_list(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation"}),
        "soundset.catalog.list request shape is invalid");
    const auto entries = read_catalog_entries();
    auto refused = nlohmann::json::array();
    if (entries.has_value()) {
      refused = refresh_soundset_store(entries.value());
    }
    const auto listed = soundset_sets.list();
    if (!listed.has_value()) {
      return error_envelope(listed.error());
    }
    auto sets = nlohmann::json::array();
    for (const auto& stored : listed.value()) {
      const auto digest =
          canonical_manifest_digest(stored.manifest.canonical_bytes);
      // #465 Q1 case 3: listing, preview, download and install share one
      // eligibility, so an ineligible Set is not offered at all. A cached Set
      // the Catalog now disagrees with is named among the refusals rather
      // than vanishing without a reason.
      const auto eligible = foundation::check_soundset_eligibility(
          stored.manifest,
          catalog_summary_for(
              entries,
              stored.manifest.set_id,
              stored.manifest.version,
              digest));
      if (!eligible.has_value()) {
        refused.push_back(
            soundset_refusal_json(
                project_io::SoundSetCatalogEntry{
                    stored.manifest.set_id,
                    stored.manifest.version,
                    digest,
                    stored.total_bytes,
                    std::nullopt,
                },
                eligible.error()));
        continue;
      }
      sets.push_back(soundset_summary_json(stored, digest));
    }
    return success_envelope(
        {
            {"catalog_available", entries.has_value()},
            {"sets", std::move(sets)},
            {"refused", std::move(refused)},
        },
        std::nullopt);
  }

  nlohmann::json soundset_inspect(const nlohmann::json& request) {
    require(
        exact_keys(
            request, {"operation", "set_id", "version", "manifest_sha256"}),
        "soundset.inspect request shape is invalid");
    auto resolved = resolve_soundset(request);
    if (!resolved.has_value()) {
      return error_envelope(resolved.error());
    }
    const auto decoded = decode_soundset_audio(
        resolved.value().stored, resolved.value().manifest_sha256);
    if (!decoded.has_value()) {
      return error_envelope(decoded.error());
    }
    auto result = soundset_summary_json(
        resolved.value().stored, resolved.value().manifest_sha256);
    result["slots"] =
        soundset_slots_json(resolved.value().stored, decoded.value().slots);
    result["demo"] = resolved.value().stored.manifest.demo.has_value()
                         ? soundset_artifact_json(
                               *resolved.value().stored.manifest.demo)
                         : nlohmann::json(nullptr);
    return success_envelope(std::move(result), std::nullopt);
  }

  // S11-D5's two audition layers, and the only Facade operation that resolves
  // Sound Set audio for playback rather than for a write. It resolves and
  // gates the audition source and reports the geometry of the exact bytes the
  // Runtime would play; carrying those bytes into a Host's audio engine is
  // still outstanding, because the engine's preview control is a Pad-slot
  // override on a bank cooked from a Project and a Set is in neither.
  //
  // It is Set-scoped, not Pad-scoped: a Set sitting in the Workspace Set
  // Store is not a Project Pad, so `sample.preview.set` cannot address it.
  // Omitting `slot_index` resolves the set-level `demo`; supplying one
  // resolves that slot's Artifact. Like `soundset.inspect` it is a query
  // with respect to Project Truth — no Asset, no Pad, no revision — and it
  // resolves the Set Store from the Workspace, so a `workspace_path` fails
  // `exact_keys` like any other extra field.
  // `soundset.audition` (#799), in full. The JSON operation below validates its
  // request shape and then delegates here for everything else, so the bytes a
  // Host is handed and the geometry the envelope reports are measured from the
  // same decode and the refusal order exists once. Keep it that way: two copies
  // of the S11-D12 empty-slot answer would agree only as long as a fixture kept
  // checking that they did.
  foundation::Result<SoundSetAuditionAudio> audition_soundset(
      const SoundSetAuditionRequest& request) {
    using Result = foundation::Result<SoundSetAuditionAudio>;
    nlohmann::json identity{
        {"operation", "soundset.audition"},
        {"set_id", request.set_id},
        {"version", request.version},
        {"manifest_sha256", request.manifest_sha256},
    };
    auto resolved = resolve_soundset(identity);
    if (!resolved.has_value()) {
      return Result::failure(resolved.error());
    }
    // S11-D3 is a property of the Set, so this refuses exactly what `inspect`,
    // `soundset.map.preview` and `install` refuse, in the same order.
    const auto decoded = decode_soundset_audio(
        resolved.value().stored, resolved.value().manifest_sha256);
    if (!decoded.has_value()) {
      return Result::failure(decoded.error());
    }
    const auto& manifest = resolved.value().stored.manifest;
    foundation::ArtifactRef artifact{};
    std::span<const std::byte> bytes;
    if (request.slot_index.has_value()) {
      const auto slot = std::ranges::find_if(
          manifest.slots,
          [index = *request.slot_index](const auto& candidate) {
            return candidate.index == index;
          });
      // S11-D12: an empty slot is the author's silence, keyed off the absence
      // of an `artifact`. The existing MISSING_ASSET with no reason, exactly as
      // the JSON operation answers it -- auditions widen no vocabulary.
      if (slot == manifest.slots.end() || !slot->occupied.has_value()) {
        return Result::failure(Error{
            ErrorCode::missing_asset,
            "Sound Set slot is empty",
        });
      }
      artifact = slot->occupied.value().artifact;
      bytes = decoded.value().slots.at(*request.slot_index).value().bytes;
    } else {
      if (!manifest.demo.has_value()) {
        return Result::failure(Error{
            ErrorCode::missing_asset,
            "Sound Set declares no demo",
        });
      }
      artifact = manifest.demo.value();
      auto demo_bytes = soundset_sets.read_artifact(
          resolved.value().manifest_sha256, manifest.demo->sha256);
      if (!demo_bytes.has_value()) {
        return Result::failure(soundset_artifact_error(demo_bytes.error()));
      }
      return prepared_audition(artifact, demo_bytes.value());
    }
    return prepared_audition(artifact, bytes);
  }

  // `decode_soundset_audio` already proved these bytes are S8-D6 audio; this
  // re-decodes to retain the PCM it measures and discards. The second decode is
  // the cost of keeping that function a measurement, and it is one Artifact
  // rather than the sixteen the gate reads.
  foundation::Result<SoundSetAuditionAudio> prepared_audition(
      const foundation::ArtifactRef& artifact,
      std::span<const std::byte> bytes) const {
    using Result = foundation::Result<SoundSetAuditionAudio>;
    const auto decoded = cooker::decode_wav(bytes);
    if (!decoded.has_value()) {
      return Result::failure(decoded.error());
    }
    auto prepared = decoded.value();
    if (prepared->sample_rate != 48'000) {
      auto resampled = cooker::prepare_runtime_pcm(*decoded.value());
      if (!resampled.has_value()) {
        return Result::failure(resampled.error());
      }
      prepared = resampled.value();
    }
    if (prepared == nullptr || prepared->channels == 0 ||
        prepared->interleaved.empty() ||
        prepared->interleaved.size() % prepared->channels != 0) {
      return Result::failure(Error{
          ErrorCode::cook_failed,
          "prepared Sample PCM shape is invalid",
      });
    }
    return Result::success(SoundSetAuditionAudio{
        artifact,
        decoded.value()->sample_rate,
        decoded.value()->channels,
        static_cast<std::uint64_t>(
            decoded.value()->interleaved.size() / decoded.value()->channels),
        std::move(prepared),
    });
  }

  nlohmann::json soundset_audition(const nlohmann::json& request) {
    require(
        exact_keys(
            request, {"operation", "set_id", "version", "manifest_sha256"}) ||
            exact_keys(
                request,
                {"operation", "set_id", "version", "manifest_sha256",
                 "slot_index"}),
        "soundset.audition request shape is invalid");
    std::optional<std::uint8_t> slot_index;
    if (request.contains("slot_index")) {
      slot_index = static_cast<std::uint8_t>(
          unsigned_field(request, "slot_index", 15));
    }
    // Everything below the request shape is `audition_soundset`'s, so the
    // geometry reported here is measured from the same bytes a Host is handed.
    // This delegation is the invariant: resolution, S11-D3's whole-Set audio
    // decision, the refusal order and the S11-D12 empty-slot answer exist once,
    // and the two surfaces cannot drift because there is only one of each.
    // Re-implementing the lookup and refusals here would leave the agreement
    // pinned by fixtures rather than by structure.
    auto audio = audition_soundset(SoundSetAuditionRequest{
        string_field(request, "set_id"),
        string_field(request, "version"),
        string_field(request, "manifest_sha256"),
        slot_index,
    });
    if (!audio.has_value()) {
      return error_envelope(audio.error());
    }
    const auto prepared_frames = static_cast<std::uint64_t>(
        audio.value().prepared->interleaved.size() /
        audio.value().prepared->channels);
    const auto prepared_bytes = audio::checked_mono_float_bytes(
        prepared_frames);
    if (!prepared_bytes.has_value()) {
      return error_envelope(Error{
          ErrorCode::invalid_argument,
          "prepared Sample PCM byte length overflowed",
      });
    }
    return success_envelope(
        {
            {"set_id", string_field(request, "set_id")},
            {"version", string_field(request, "version")},
            {"manifest_sha256", string_field(request, "manifest_sha256")},
            {"slot_index",
             slot_index.has_value() ? nlohmann::json(*slot_index)
                                    : nlohmann::json(nullptr)},
            {"artifact", soundset_artifact_json(audio.value().artifact)},
            {"audio",
             {
                 {"sample_rate", audio.value().sample_rate},
                 {"channels", audio.value().channels},
                 {"source_frames", audio.value().source_frames},
                 {"prepared_bytes", *prepared_bytes},
                 {"prepared_frames", prepared_frames},
             }},
        },
        std::nullopt);
  }

  nlohmann::json soundset_map_preview(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "bank_id", "set_id", "version",
             "manifest_sha256"}),
        "soundset.map.preview request shape is invalid");
    const auto project_path = absolute_path_field(request, "project_path");
    const auto bank = static_cast<std::uint8_t>(
        unsigned_field(request, "bank_id", 3));
    auto resolved = resolve_soundset(request);
    if (!resolved.has_value()) {
      return error_envelope(resolved.error());
    }
    const auto loaded = projects.load(project_path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    // S11-D3 again: a Set that could never install must not be previewed as
    // installable, so the same whole-Set audio decision runs before the pure
    // map.
    const auto decoded = decode_soundset_audio(
        resolved.value().stored, resolved.value().manifest_sha256);
    if (!decoded.has_value()) {
      return error_envelope(decoded.error());
    }
    const auto mapping = domain::map_soundset(
        resolved.value().stored.manifest, loaded.value().banks.at(bank));
    auto proposed = nlohmann::json::array();
    for (const auto& pad : mapping.proposed) {
      proposed.push_back({
          {"slot_index", pad.slot_index},
          {"pad", pad.pad},
          {"artifact", soundset_artifact_json(pad.artifact)},
      });
    }
    return success_envelope(
        {
            {"bank_id", bank},
            {"set_id", resolved.value().stored.manifest.set_id},
            {"version", resolved.value().stored.manifest.version},
            {"manifest_sha256", resolved.value().manifest_sha256},
            {"proposed", std::move(proposed)},
            {"collisions", mapping.collisions},
            {"kept", mapping.kept},
        },
        loaded.value().revision);
  }

  nlohmann::json soundset_install(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "command_id", "expected_revision",
             "bank_id", "set_id", "version", "manifest_sha256"}) ||
            exact_keys(
                request,
                {"operation", "project_path", "command_id",
                 "expected_revision", "bank_id", "set_id", "version",
                 "manifest_sha256", "occupied_pad_policy"}),
        "soundset.install request shape is invalid");
    const auto project_path = absolute_path_field(request, "project_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto expected_revision = unsigned_field(request, "expected_revision");
    const auto bank = static_cast<std::uint8_t>(
        unsigned_field(request, "bank_id", 3));
    std::optional<domain::OccupiedPadPolicy> policy;
    if (request.contains("occupied_pad_policy")) {
      const auto value = string_field(request, "occupied_pad_policy");
      require(
          value == "keep" || value == "replace",
          "occupied_pad_policy must be keep or replace");
      policy = value == "keep" ? domain::OccupiedPadPolicy::keep
                               : domain::OccupiedPadPolicy::replace;
    }
    auto resolved = resolve_soundset(request);
    if (!resolved.has_value()) {
      return error_envelope(resolved.error());
    }
    // S11-D3 is a property of the Set, not of the write set: the whole Set is
    // read and decoded here, before the target Bank is even consulted, so no
    // `occupied_pad_policy` and no empty write set can admit a Set that
    // `inspect` and `soundset.map.preview` both refuse. These bytes are the
    // ones the commit publishes, so each occupied slot is decoded exactly
    // once. Nothing has been written at this point, or below it until the
    // single commit.
    const auto decoded = decode_soundset_audio(
        resolved.value().stored, resolved.value().manifest_sha256);
    if (!decoded.has_value()) {
      return error_envelope(decoded.error());
    }
    const auto loaded = projects.load(project_path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto mapping = domain::map_soundset(
        resolved.value().stored.manifest, loaded.value().banks.at(bank));
    const auto write_set =
        domain::resolve_soundset_write_set(mapping, policy);
    if (!write_set.has_value()) {
      // Carries the complete collisions list and soundset_occupied_conflict,
      // and nothing has been read, decoded or written at this point.
      return error_envelope(write_set.error());
    }
    // #465 Q2: `keep` on a Bank whose every proposed Pad is occupied writes
    // nothing and succeeds. There is no command to commit, so the revision
    // stands and the Project is untouched.
    if (write_set.value().empty()) {
      return success_envelope(
          {
              {"bank_id", bank},
              {"set_id", resolved.value().stored.manifest.set_id},
              {"version", resolved.value().stored.manifest.version},
              {"manifest_sha256", resolved.value().manifest_sha256},
              {"installed", nlohmann::json::array()},
              {"collisions", mapping.collisions},
              {"kept", mapping.kept},
              {"replayed", false},
          },
          loaded.value().revision);
    }

    // Every quota decision happens before the first Project mutation.
    std::uint64_t requested_bytes = 0;
    std::uint64_t requested_frames = 0;
    std::uint16_t written_pads = 0;
    for (const auto& pad : write_set.value()) {
      const auto& prepared =
          decoded.value().slots.at(pad.slot_index)->audio.prepared;
      // S11-D8: per-Pad residency. One Artifact on two Pads is two charges,
      // so the sum is over the write set and not over unique hashes.
      const auto next_bytes =
          audio::checked_runtime_byte_sum(requested_bytes, prepared.bytes);
      const auto next_frames =
          audio::checked_runtime_byte_sum(requested_frames, prepared.frames);
      if (!next_bytes.has_value() || !next_frames.has_value()) {
        return error_envelope(Error{
            ErrorCode::invalid_argument,
            "installed Sound Set prepared PCM byte length overflowed",
        });
      }
      requested_bytes = *next_bytes;
      requested_frames = *next_frames;
      written_pads =
          static_cast<std::uint16_t>(written_pads | (std::uint16_t{1} << pad.pad));
    }

    if (!sample_limits.has_value()) {
      return error_envelope(
          invalid_sample_request("Sample quota is unavailable"));
    }
    const auto ledger = compute_bank_ledger(
        project_path, loaded.value(), bank, written_pads);
    if (!ledger.has_value()) {
      return error_envelope(ledger.error());
    }
    const auto assessment = audio::assess_runtime_quota(
        ledger.value().bank_used_bytes.at(bank),
        ledger.value().project_used_bytes,
        requested_bytes,
        *sample_limits);
    if (!assessment.has_value()) {
      return error_envelope(Error{
          ErrorCode::invalid_project,
          "Sample quota ledger exceeds configured limits",
      });
    }
    if (assessment->constraint == audio::RuntimeQuotaConstraint::user_bank) {
      std::vector<nlohmann::json> consumed;
      consumed.reserve(ledger.value().consumed.size());
      for (const auto& entry : ledger.value().consumed) {
        consumed.push_back({
            {"pad", entry.slot.pad},
            {"prepared_bytes", entry.prepared_bytes},
            {"prepared_frames", entry.prepared_frames},
        });
      }
      return error_envelope(runtime_bank_quota_error(
          domain::PadSlotId{bank, write_set.value().front().pad},
          requested_bytes,
          requested_frames,
          assessment->user_bank_remaining_bytes,
          sample_limits->maximum_user_bank_bytes,
          consumed));
    }
    if (assessment->constraint == audio::RuntimeQuotaConstraint::generation) {
      return error_envelope(runtime_project_quota_error(
          requested_bytes,
          requested_frames,
          ledger.value().project_used_bytes,
          assessment->generation_remaining_bytes,
          sample_limits->maximum_generation_bytes,
          ledger.value().bank_used_bytes));
    }

    std::vector<project_io::ProjectStore::SoundSetInstallSlotRequest> slots;
    slots.reserve(write_set.value().size());
    for (const auto& pad : write_set.value()) {
      slots.push_back(
          project_io::ProjectStore::SoundSetInstallSlotRequest{
              domain::PadSlotId{bank, pad.pad},
              foundation::AssetId{derived_asset_id(
                  command_id,
                  resolved.value().manifest_sha256,
                  bank,
                  pad.pad)},
              "audio/wav",
              decoded.value().slots.at(pad.slot_index)->bytes,
              domain::AssetLineage{
                  domain::SoundSetLineageSource{
                      resolved.value().stored.manifest.set_id,
                      resolved.value().stored.manifest.version,
                      resolved.value().manifest_sha256,
                      pad.slot_index,
                      pad.artifact.sha256,
                  },
                  domain::SoundSetInstallLineageDerivation{},
              },
          });
    }
    const auto committed = projects.install_soundset(
        project_path,
        project_io::ProjectStore::SoundSetInstallRequest{
            domain::CommandMeta{
                foundation::CommandId{command_id}, expected_revision},
            std::move(slots),
        });
    if (!committed.has_value()) {
      return error_envelope(committed.error());
    }
    auto installed = nlohmann::json::array();
    for (const auto& pad : write_set.value()) {
      installed.push_back({{"slot_index", pad.slot_index}, {"pad", pad.pad}});
    }
    return success_envelope(
        {
            {"bank_id", bank},
            {"set_id", resolved.value().stored.manifest.set_id},
            {"version", resolved.value().stored.manifest.version},
            {"manifest_sha256", resolved.value().manifest_sha256},
            {"installed", std::move(installed)},
            {"collisions", mapping.collisions},
            {"kept", mapping.kept},
            {"replayed", committed.value().replayed},
        },
        committed.value().state.revision);
  }

  nlohmann::json attempt_inspect(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "attempt_id"}),
        "attempt.inspect request shape is invalid");
    const auto attempt_id = file_id_field(request, "attempt_id");
    const auto inspected =
        attempts.inspect(foundation::AttemptId{attempt_id});
    if (!inspected.has_value()) {
      return error_envelope(inspected.error());
    }
    return success_envelope(
        terminal_attempt_json(inspected.value()),
        std::nullopt);
  }

  std::filesystem::path workspace_root;
  std::shared_ptr<provider::Registry> registry;
  std::shared_ptr<project_io::ProjectStoragePlatform> storage_platform;
  std::shared_ptr<PerformanceClock> performance_clock;
  std::shared_ptr<PerformanceInputSequencer> performance_input_sequencer;
  std::shared_ptr<PatternLaunchAcknowledger> pattern_launch_acknowledger;
  std::shared_ptr<PerformanceReplayController> performance_replay_controller;
  std::shared_ptr<PerformanceGestureSink> performance_gesture_sink;
  std::optional<audio::RuntimePreparationLimits> sample_limits;
  std::shared_ptr<project_io::CatalogTransport> soundset_transport;
  std::shared_ptr<SoundSetCatalogSource> soundset_source;
  project_io::SoundSetStoreLimits soundset_limits;
  project_io::SoundSetStore soundset_sets;
  detail::CandidateStore candidates;
  project_io::ProjectStore projects;
  project_io::SequenceJournal sequence_journals;
  project_io::ProjectBundleTransfer bundle_transfers;
  project_io::WorkspaceCacheStore waveform_cache;
  provider::ProviderPolicy provider_policy;
  provider::TimestampSource provider_timestamp_source;
  provider::AttemptStore attempts;
  mutable std::mutex sample_mutex;
  mutable std::mutex replay_mutex;
  mutable std::mutex sequence_mutex;
  std::map<std::string, SequenceRuntime> sequence_sessions;
  // Live Facade-vended Pattern transport controllers by Project path. The
  // registration makes their Facade-owned journals known owners for authoring
  // admission and owner-loss reconciliation; an entry retires only at its
  // controller's destruction, never at journal closure. Shared ownership lets
  // a controller destroyed after its Application stop cleanly, and the
  // per-Project set keeps a second vended controller's registration intact
  // when the first is destroyed.
  struct TransportSessionRegistry {
    std::mutex mutex;
    std::map<std::string, std::set<foundation::SequenceSessionId>> sessions;
  };
  std::shared_ptr<TransportSessionRegistry> transport_sessions =
      std::make_shared<TransportSessionRegistry>();
  std::map<std::string, PerformanceRuntime> performance_sessions;
  std::map<std::string, ReplayIdentity> replay_identities;
  std::map<std::string, ReplayStopReceipt> replay_stop_receipts;
  std::string active_replay_id;
  std::map<std::string, SampleImportState> sample_imports;
  std::set<std::string> used_sample_import_tokens;
  std::deque<std::string> remembered_sample_import_tokens;
};

namespace {

constexpr std::string_view kWorkspaceCatalogDirectory =
    ".lmdj-host/soundset-catalog";

// Reads the Workspace's Catalog index off the Host's own filesystem. It is
// the trivial implementation of the S11-D6 seam: a missing, unreadable or
// oversized index is an unreachable Catalog, never a fatal one.
class LocalFileCatalogSource final : public SoundSetCatalogSource {
 public:
  explicit LocalFileCatalogSource(std::filesystem::path index_path)
      : index_path_(std::move(index_path)) {}

  foundation::Result<std::vector<std::byte>> read_index(
      std::uint64_t maximum_bytes) override {
    using Result = foundation::Result<std::vector<std::byte>>;
    const auto unavailable = [](std::string message) {
      return Error{
          ErrorCode::io_error,
          std::move(message),
          {{"reason", project_io::kSoundSetReasonCatalogUnavailable}},
      };
    };
    std::error_code code;
    const auto size = std::filesystem::file_size(index_path_, code);
    if (code || size > maximum_bytes) {
      return Result::failure(
          unavailable("Workspace Catalog index is not readable"));
    }
    std::ifstream stream(index_path_, std::ios::binary);
    if (!stream) {
      return Result::failure(
          unavailable("Workspace Catalog index could not be opened"));
    }
    std::vector<std::byte> bytes(static_cast<std::size_t>(size));
    if (size != 0 &&
        !stream.read(
            reinterpret_cast<char*>(bytes.data()),
            static_cast<std::streamsize>(size))) {
      return Result::failure(
          unavailable("Workspace Catalog index could not be read"));
    }
    return Result::success(std::move(bytes));
  }

 private:
  std::filesystem::path index_path_;
};

}  // namespace

LocalSoundSetCatalog make_workspace_soundset_catalog(
    const std::filesystem::path& workspace_root) {
  const auto root = workspace_root / kWorkspaceCatalogDirectory;
  return LocalSoundSetCatalog{
      project_io::make_local_directory_catalog_transport(root / "objects"),
      std::make_shared<LocalFileCatalogSource>(root / "index.json"),
  };
}

Application::Application(ApplicationConfig config)
    : impl_(std::make_unique<Impl>(std::move(config))) {}

RuntimeProjectWriterLease::RuntimeProjectWriterLease(
    std::unique_ptr<Impl> impl)
    : impl_(std::move(impl)) {}

RuntimeProjectWriterLease::~RuntimeProjectWriterLease() = default;
RuntimeProjectWriterLease::RuntimeProjectWriterLease(
    RuntimeProjectWriterLease&&) noexcept = default;
RuntimeProjectWriterLease& RuntimeProjectWriterLease::operator=(
    RuntimeProjectWriterLease&&) noexcept = default;

Application::~Application() = default;
Application::Application(Application&&) noexcept = default;
Application& Application::operator=(Application&&) noexcept = default;

foundation::Result<void> Application::service_performance() {
  try {
    return impl_->service_performance();
  } catch (...) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "Performance service failed unexpectedly",
    });
  }
}

nlohmann::json Application::command(const nlohmann::json& request) {
  try {
    testing::invoke_api_entry_hook();
    auto serviced = impl_->service_performance();
    if (!serviced.has_value()) {
      return error_envelope(serviced.error());
    }
    return impl_->dispatch(request, OperationKind::command);
  } catch (const InvalidRequest& error) {
    const Error invalid_request{ErrorCode::invalid_argument, error.what()};
    return sample_operation_request(request)
               ? sample_error_envelope(invalid_request)
               : error_envelope(invalid_request);
  } catch (...) {
    return internal_error();
  }
}

nlohmann::json Application::query(
    const nlohmann::json& request) const {
  try {
    testing::invoke_api_entry_hook();
    return impl_->dispatch(request, OperationKind::query);
  } catch (const InvalidRequest& error) {
    const Error invalid_request{ErrorCode::invalid_argument, error.what()};
    return sample_operation_request(request)
               ? sample_error_envelope(invalid_request)
               : error_envelope(invalid_request);
  } catch (...) {
    return internal_error();
  }
}

foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
Application::prepare_runtime_snapshot(
    const RuntimeSnapshotRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->prepare_runtime_snapshot(request);
  } catch (...) {
    return foundation::Result<
        std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<cooker::EncodedRuntimeContent>
Application::export_runtime_content(const RuntimeContentExportRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->export_runtime_content(request);
  } catch (...) {
    return foundation::Result<cooker::EncodedRuntimeContent>::failure(
        {ErrorCode::internal_error,
         "unexpected Application Facade Host API failure"});
  }
}

foundation::Result<RuntimeProjectWriterLease>
Application::acquire_project_writer(
    const std::filesystem::path& project_path) {
  try {
    testing::invoke_api_entry_hook();
    auto acquired = impl_->acquire_project_writer(project_path);
    if (!acquired.has_value()) {
      return foundation::Result<RuntimeProjectWriterLease>::failure(
          acquired.error());
    }
    return foundation::Result<RuntimeProjectWriterLease>::success(
        RuntimeProjectWriterLease{
            std::make_unique<RuntimeProjectWriterLease::Impl>(
                std::move(acquired.value()))});
  } catch (...) {
    return foundation::Result<RuntimeProjectWriterLease>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

std::unique_ptr<PatternTransportController>
Application::make_pattern_transport_controller(
    PatternTransportAudioPort& audio, PatternTransportControllerConfig config) {
  const auto key = config.bundle.generic_string();
  const auto session = config.session;
  const auto registry = impl_->transport_sessions;
  // Register only after successful construction: a throwing factory leaves no
  // stale owner registration behind.
  auto controller = detail::PatternTransportControllerInternalFactory::make(
      audio,
      std::move(config),
      impl_->storage_platform,
      // The registry is shared state, so a controller destroyed after its
      // Application observes an expired weak reference and stops cleanly
      // instead of dereferencing a freed Impl.
      [weak = std::weak_ptr<Impl::TransportSessionRegistry>(registry),
       key, session]() {
        const auto locked = weak.lock();
        if (!locked) {
          return;
        }
        std::lock_guard guard(locked->mutex);
        const auto found = locked->sessions.find(key);
        if (found != locked->sessions.end() && found->second.erase(session) != 0 &&
            found->second.empty()) {
          locked->sessions.erase(found);
        }
      });
  {
    std::lock_guard lock(registry->mutex);
    registry->sessions[key].insert(session);
  }
  return controller;
}

foundation::Result<domain::ProjectState>
Application::create_initial_project(
    const InitialProjectRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->create_initial_project(request);
  } catch (...) {
    return foundation::Result<domain::ProjectState>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<domain::AppliedCommand>
Application::import_artifact_bytes(
    const ArtifactBytesImportRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->import_artifact_bytes(request);
  } catch (...) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<std::vector<LocalProjectSummary>>
Application::list_local_projects() {
  try {
    testing::invoke_api_entry_hook();
    return impl_->list_local_projects();
  } catch (...) {
    return foundation::Result<std::vector<LocalProjectSummary>>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<ProjectBundleImportSession>
Application::begin_project_bundle_import(
    const ProjectBundleImportBeginRequest& request) {
  try {
    return impl_->begin_project_bundle_import(request);
  } catch (...) {
    return foundation::Result<ProjectBundleImportSession>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<std::optional<ProjectBundleImportIdentity>>
Application::append_project_bundle_index(
    std::string_view token,
    std::uint64_t offset,
    std::span<const std::byte> bytes,
    bool final) {
  try {
    return impl_->append_project_bundle_index(
        token, offset, bytes, final);
  } catch (...) {
    return foundation::Result<
        std::optional<ProjectBundleImportIdentity>>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<void> Application::append_project_bundle_entry(
    std::string_view token,
    std::uint32_t entry_index,
    std::uint64_t offset,
    std::span<const std::byte> bytes,
    bool final) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->append_project_bundle_entry(
        token, entry_index, offset, bytes, final);
  } catch (...) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<LocalProjectSummary>
Application::commit_project_bundle_import(std::string_view token) {
  try {
    return impl_->commit_project_bundle_import(token);
  } catch (...) {
    return foundation::Result<LocalProjectSummary>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<void> Application::abort_project_bundle_import(
    std::string_view token) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->abort_project_bundle_import(token);
  } catch (...) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<CandidateAuditionAudio> Application::audition_candidate(
    const CandidateAuditionRequest& request) const {
  try {
    testing::invoke_api_entry_hook();
    return impl_->audition_candidate(request);
  } catch (const InvalidRequest& error) {
    return foundation::Result<CandidateAuditionAudio>::failure(
        Error{ErrorCode::invalid_argument, error.what()});
  } catch (...) {
    return foundation::Result<CandidateAuditionAudio>::failure(
        Error{ErrorCode::internal_error, "Candidate audition failed"});
  }
}

foundation::Result<SoundSetAuditionAudio> Application::audition_soundset(
    const SoundSetAuditionRequest& request) const {
  try {
    testing::invoke_api_entry_hook();
    return impl_->audition_soundset(request);
  } catch (...) {
    return foundation::Result<SoundSetAuditionAudio>::failure(Error{
        ErrorCode::internal_error,
        "Sound Set audition failed",
    });
  }
}

foundation::Result<SampleInspectResult> Application::inspect_sample(
    const SampleInspectRequest& request) const {
  try {
    testing::invoke_api_entry_hook();
    return impl_->inspect_sample(request);
  } catch (...) {
    return foundation::Result<SampleInspectResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<cooker::WaveformEnvelope>
Application::query_sample_waveform(const SampleWaveformRequest& request) {
  try {
    return impl_->query_sample_waveform(request);
  } catch (...) {
    return foundation::Result<cooker::WaveformEnvelope>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SampleQuotaResult> Application::query_sample_quota(
    const SampleQuotaRequest& request) const {
  try {
    testing::invoke_api_entry_hook();
    return impl_->query_sample_quota(request);
  } catch (...) {
    return foundation::Result<SampleQuotaResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SampleImportSession> Application::begin_sample_import(
    const SampleImportBeginRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->begin_sample_import(request);
  } catch (...) {
    return foundation::Result<SampleImportSession>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<void> Application::append_sample_import(
    std::string_view token,
    std::uint64_t offset,
    std::span<const std::byte> bytes,
    bool final) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->append_sample_import(token, offset, bytes, final);
  } catch (...) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SampleMutationResult> Application::commit_sample_import(
    std::string_view token) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->commit_sample_import(token);
  } catch (...) {
    return foundation::Result<SampleMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<void> Application::abort_sample_import(
    std::string_view token) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->abort_sample_import(token);
  } catch (...) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SampleMutationResult> Application::update_sample_pad(
    const SampleUpdateRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->update_sample_pad(request);
  } catch (...) {
    return foundation::Result<SampleMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SampleMutationResult> Application::reset_sample_pad(
    const SampleResetRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->reset_sample_pad(request);
  } catch (...) {
    return foundation::Result<SampleMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SequenceMutationResult> Application::begin_sequence(
    const SequenceBeginRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->begin_sequence(request);
  } catch (...) {
    return foundation::Result<SequenceMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SequenceMutationResult> Application::record_sequence_event(
    const SequenceEventRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->record_sequence_event(request);
  } catch (...) {
    return foundation::Result<SequenceMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SequenceMutationResult> Application::flush_sequence(
    const SequenceFlushRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->flush_sequence(request, false);
  } catch (...) {
    return foundation::Result<SequenceMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SequenceMutationResult> Application::stop_sequence(
    const SequenceFlushRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->flush_sequence(request, true);
  } catch (...) {
    return foundation::Result<SequenceMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SequenceMutationResult>
Application::request_sequence_switch(const SequenceSwitchRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->request_sequence_switch(request);
  } catch (...) {
    return foundation::Result<SequenceMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<void> Application::disarm_sequence_capture(
    const SequenceCaptureDisarmRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->disarm_sequence_capture(request);
  } catch (...) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

void Application::abandon_sequence_sessions() noexcept {
  impl_->abandon_sequence_sessions();
}

foundation::Result<SequenceStatus> Application::query_sequence_status(
    const SequenceStatusRequest& request) const {
  try {
    testing::invoke_api_entry_hook();
    return impl_->query_sequence_status(request);
  } catch (...) {
    return foundation::Result<SequenceStatus>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<SequenceOverlayProjection>
Application::query_sequence_overlay(
    const SequenceOverlayRequest& request) const {
  try {
    testing::invoke_api_entry_hook();
    return impl_->query_sequence_overlay(request);
  } catch (...) {
    return foundation::Result<SequenceOverlayProjection>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<std::vector<SequenceRecoveryInfo>>
Application::list_sequence_recovery(
    const SequenceStatusRequest& request) const {
  try {
    testing::invoke_api_entry_hook();
    return impl_->list_sequence_recovery(request);
  } catch (...) {
    return foundation::Result<std::vector<SequenceRecoveryInfo>>::failure(
        Error{ErrorCode::internal_error,
              "unexpected Application Facade Host API failure"});
  }
}

foundation::Result<SequenceMutationResult>
Application::apply_sequence_recovery(const SequenceRecoveryRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->apply_sequence_recovery(request);
  } catch (...) {
    return foundation::Result<SequenceMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<void> Application::discard_sequence_recovery(
    const SequenceRecoveryRequest& request) {
  try {
    testing::invoke_api_entry_hook();
    return impl_->discard_sequence_recovery(request);
  } catch (...) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

}  // namespace lmdj::facade
