#include <lmdj/facade/application.hpp>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <filesystem>
#include <limits>
#include <map>
#include <mutex>
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

#include <lmdj/audio/offline_renderer.hpp>
#include <lmdj/cooker/project_cooker.hpp>
#include <lmdj/cooker/sample_analysis.hpp>
#include <lmdj/cooker/wav_reader.hpp>
#include <lmdj/domain/commands.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/project_bundle_transfer.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/take_journal.hpp>
#include <lmdj/project_io/workspace_cache.hpp>
#include <lmdj/provider/capability.hpp>

#include "testing_hooks.hpp"

namespace lmdj::facade {
namespace testing {
namespace {

std::atomic<SampleProjectionHook*> sample_projection_hook{nullptr};

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

}  // namespace testing
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint32_t kSampleRate = 48'000;
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
      {"pad.assign", OperationKind::command},
      {"project.create", OperationKind::command},
      {"project.inspect", OperationKind::query},
      {"provider.list", OperationKind::query},
      {"provider.run", OperationKind::command},
      {"provider.select", OperationKind::command},
      {"provider.selected", OperationKind::query},
      {"render.offline", OperationKind::command},
      {"sample.import.abort", OperationKind::command},
      {"sample.import.begin", OperationKind::command},
      {"sample.import.chunk", OperationKind::command},
      {"sample.import.commit", OperationKind::command},
      {"sample.inspect", OperationKind::query},
      {"sample.reset_pad", OperationKind::command},
      {"sample.update_pad", OperationKind::command},
      {"sample.waveform", OperationKind::query},
      {"snapshot.cook", OperationKind::query},
      {"take.append", OperationKind::command},
      {"take.begin", OperationKind::command},
      {"take.commit", OperationKind::command},
      {"take.recoverable.list", OperationKind::query},
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
  const auto step_limit = bars * 16U;
  for (const auto& event : events) {
    require(
        exact_keys(event, {"slot", "step", "velocity"}),
        "pattern event shape is invalid");
    const auto step = unsigned_field(event, "step", step_limit - 1U);
    const auto velocity = unsigned_field(event, "velocity", 127);
    require(velocity > 0, "pattern velocity must be positive");
    parsed.push_back(
        domain::PatternEvent{
            slot_value(event.at("slot")),
            static_cast<std::uint32_t>(step),
            static_cast<std::uint8_t>(velocity),
        });
  }
  return domain::Pattern{
      foundation::PatternId{pattern_id},
      static_cast<std::uint8_t>(bars),
      std::move(parsed),
  };
}

domain::RawTakeEvent raw_event_value(const nlohmann::json& encoded) {
  require(
      exact_keys(encoded, {"slot", "frame_offset", "velocity"}),
      "raw event shape is invalid");
  const auto frame_offset =
      unsigned_field(
          encoded,
          "frame_offset",
          std::numeric_limits<std::uint32_t>::max());
  const auto velocity = unsigned_field(encoded, "velocity", 127);
  require(velocity > 0, "raw event velocity must be positive");
  return domain::RawTakeEvent{
      slot_value(encoded.at("slot")),
      static_cast<std::uint32_t>(frame_offset),
      static_cast<std::uint8_t>(velocity),
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

nlohmann::json raw_event_json(const domain::RawTakeEvent& event) {
  return {
      {"slot", slot_json(event.slot)},
      {"frame_offset", event.frame_offset},
      {"velocity", event.velocity},
  };
}

nlohmann::json pattern_event_json(const domain::PatternEvent& event) {
  return {
      {"slot", slot_json(event.slot)},
      {"step", event.step},
      {"velocity", event.velocity},
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
    assets[id.value()] = {{"artifact", asset.artifact}};
  }
  auto takes = nlohmann::json::object();
  for (const auto& [id, take] : state.takes) {
    auto events = nlohmann::json::array();
    for (const auto& event : take.events) {
      events.push_back(raw_event_json(event));
    }
    takes[id.value()] = {
        {"sample_rate", take.sample_rate},
        {"events", std::move(events)},
    };
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
  return {
      {"contract", "lmdj.project.v1"},
      {"project_id", state.id.value()},
      {"revision", state.revision},
      {"bpm", state.bpm},
      {"banks", std::move(banks)},
      {"assets", std::move(assets)},
      {"takes", std::move(takes)},
      {"patterns", std::move(patterns)},
  };
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
        next >= 0,
        "render output parent contains a symbolic, missing, or invalid directory");
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
  const auto step_limit =
      static_cast<std::uint32_t>(pattern.bars) * 16U;
  for (const auto& event : pattern.events) {
    if (!domain::is_valid_slot(event.slot) || event.velocity < 1 ||
        event.velocity > 127 || event.step >= step_limit) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_argument,
              "pattern event is invalid",
          });
    }
  }
  return foundation::Result<void>::success();
}

}  // namespace

struct RuntimeProjectWriterLease::Impl {
  explicit Impl(std::unique_ptr<project_io::ProjectWriterLease> owned)
      : owned(std::move(owned)) {}

  std::unique_ptr<project_io::ProjectWriterLease> owned;
};

struct Application::Impl {
  struct SampleImportState {
    SampleImportBeginRequest request;
    std::filesystem::path directory;
    std::filesystem::path payload_path;
    std::uint64_t received_bytes;
    bool finalized;
    std::unique_ptr<project_io::ProjectWriterLease> lease;
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
        sample_limits(config.runtime_preparation_limits),
        projects(storage_platform),
        journals(storage_platform),
        bundle_transfers(storage_platform),
        waveform_cache(
            workspace_root / ".lmdj-host/workspace-cache",
            storage_platform),
        attempts(
            workspace_root,
            std::move(config.provider_policy),
            config.timestamp_source
                ? std::move(config.timestamp_source)
                : default_timestamp_source()) {
    if (!workspace_root.is_absolute()) {
      throw std::invalid_argument("workspace_root must be absolute");
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
    const auto validated = storage_platform->validate_managed_tree(root);
    if (!validated.has_value()) {
      return foundation::Result<void>::failure(sample_storage_error(
          validated.error(), "Sample staging tree is invalid"));
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
      const auto marker_path = directory / "state.json";
      const auto marker_length = storage_platform->byte_length(marker_path);
      if (!marker_length.has_value() ||
          marker_length.value() > kMaximumSampleStagingMarkerBytes) {
        continue;
      }
      const auto marker_bytes = storage_platform->read_complete(marker_path);
      if (!marker_bytes.has_value()) {
        continue;
      }
      const auto marker_text = std::string_view{
          reinterpret_cast<const char*>(marker_bytes.value().data()),
          marker_bytes.value().size()};
      const auto marker = nlohmann::json::parse(marker_text, nullptr, false);
      if (marker.is_discarded() ||
          !exact_keys(
              marker,
              {"contract", "created_unix_seconds", "state", "token"}) ||
          !marker.at("contract").is_string() ||
          marker.at("contract") != kSampleStagingContract ||
          !marker.at("state").is_string() ||
          marker.at("state") != "incomplete" ||
          !marker.at("token").is_string() || marker.at("token") != token) {
        continue;
      }
      const auto created = cache_unsigned(marker, "created_unix_seconds");
      if (!created.has_value() || now < 0 ||
          *created > static_cast<std::uint64_t>(now) ||
          static_cast<std::uint64_t>(now) - *created <
              kMinimumSampleStagingAgeSeconds) {
        continue;
      }
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
      lease.value().reset();
      const auto removed = remove_sample_staging(storage_platform, directory);
      if (!removed.has_value()) {
        return foundation::Result<void>::failure(sample_storage_error(
            removed.error(), "Sample staging cleanup failed"));
      }
    }
    return foundation::Result<void>::success();
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
    if (operation == "sample.inspect") {
      return sample_inspect(request);
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
    if (operation == "take.begin") {
      return take_begin(request);
    }
    if (operation == "take.append") {
      return take_append(request);
    }
    if (operation == "take.commit") {
      return take_commit(request);
    }
    if (operation == "render.offline") {
      return render_offline(request);
    }
    if (operation == "provider.select") {
      return provider_select(request);
    }
    if (operation == "provider.run") {
      return provider_run(request);
    }
    if (operation == "project.inspect") {
      return project_inspect(request);
    }
    if (operation == "take.recoverable.list") {
      return recoverable_list(request);
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
                std::move(*window));
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

  foundation::Result<SampleImportSession> begin_sample_import(
      const SampleImportBeginRequest& request) {
    if (!sample_limits.has_value() ||
        !domain::is_valid_uuid(request.import_token) ||
        !valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.meta.command_id.value()) ||
        !domain::is_valid_slot(request.slot) ||
        !domain::is_valid_uuid(request.asset_id.value()) ||
        request.byte_length == 0 ||
        !sample_limits->allows_artifact_bytes(request.byte_length)) {
      return foundation::Result<SampleImportSession>::failure(
          invalid_sample_request("Sample import begin request is invalid"));
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
    const auto metadata = cooker::inspect_wav(bytes.value());
    if (!metadata.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(
          metadata.error());
    }
    if (!sample_limits.has_value() ||
        !sample_limits->allows_decoded_frames_per_pad(
            metadata.value().source_frames)) {
      return foundation::Result<SampleMutationResult>::failure(Error{
          ErrorCode::unsupported_audio,
          "Sample exceeds the active decoded frame limit",
          {{"resource", "decoded_frames_per_pad"},
           {"observed", metadata.value().source_frames},
           {"limit",
            sample_limits.has_value()
                ? sample_limits->maximum_decoded_frames_per_pad
                : 0U}},
      });
    }
    const auto committed = projects.import_assign_sample_bytes(
        state.request.project_path,
        project_io::ProjectStore::ImportAssignSampleBytesRequest{
            state.request.meta,
            state.request.slot,
            state.request.asset_id,
            "audio/wav",
            bytes.value(),
        });
    if (!committed.has_value()) {
      return foundation::Result<SampleMutationResult>::failure(
          committed.error());
    }
    if (project_revision != nullptr) {
      *project_revision = committed.value().state.revision;
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

  foundation::Result<void> append_realtime_take_events(
      const std::filesystem::path& project_path,
      foundation::TakeId take_id,
      std::span<const domain::RawTakeEvent> events) {
    const auto encoded_path = project_path.generic_string();
    if (!valid_utf8(encoded_path) || !project_path.is_absolute() ||
        project_path.lexically_normal() != project_path ||
        !domain::is_valid_uuid(take_id.value())) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_argument,
              "realtime take append request is invalid",
          });
    }
    return journals.append_batch(project_path, std::move(take_id), events);
  }

  foundation::Result<std::filesystem::path> seal_realtime_take(
      const std::filesystem::path& project_path,
      foundation::TakeId take_id,
      std::string_view reason) {
    const auto encoded_path = project_path.generic_string();
    if (!valid_utf8(encoded_path) || !project_path.is_absolute() ||
        project_path.lexically_normal() != project_path ||
        !domain::is_valid_uuid(take_id.value()) ||
        reason != "capture_incomplete") {
      return foundation::Result<std::filesystem::path>::failure(
          Error{
              ErrorCode::invalid_argument,
              "realtime take seal request is invalid",
          });
    }
    return journals.seal(
        project_path, std::move(take_id), std::string(reason));
  }

  nlohmann::json project_create(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "project_id", "bpm"}),
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
    const auto created = projects.create(path, project.value());
    if (!created.has_value()) {
      return error_envelope(created.error());
    }
    return success_envelope({{"project_id", id}}, 0);
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

  nlohmann::json take_begin(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "project_path",
                "take_id",
                "expected_revision",
                "sample_rate",
            }),
        "take.begin request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto take_id = uuid_field(request, "take_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto sample_rate =
        unsigned_field(request, "sample_rate", kSampleRate);
    require(sample_rate == kSampleRate, "sample_rate must be 48000");
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    if (loaded.value().revision != revision) {
      return error_envelope(
          Error{
              ErrorCode::revision_conflict,
              "take begin expected a different project revision",
              {
                  {"actual_revision", loaded.value().revision},
                  {"expected_revision", revision},
              },
          });
    }
    const auto begun = journals.begin(
        path,
        foundation::TakeId{take_id},
        revision,
        static_cast<std::uint32_t>(sample_rate));
    if (!begun.has_value()) {
      return error_envelope(begun.error());
    }
    return success_envelope({{"take_id", take_id}}, loaded.value().revision);
  }

  nlohmann::json take_append(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "take_id", "event"}),
        "take.append request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto take_id = uuid_field(request, "take_id");
    const auto event = raw_event_value(request.at("event"));
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto appended = journals.append(
        path, foundation::TakeId{take_id}, event);
    if (!appended.has_value()) {
      return error_envelope(appended.error());
    }
    const auto take =
        journals.read_active(path, foundation::TakeId{take_id});
    if (!take.has_value()) {
      return error_envelope(take.error());
    }
    return success_envelope(
        {
            {"take_id", take_id},
            {"event_count", take.value().events.size()},
        },
        loaded.value().revision);
  }

  nlohmann::json take_commit(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "project_path",
                "command_id",
                "expected_revision",
                "take_id",
                "pattern",
            }),
        "take.commit request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto take_id = uuid_field(request, "take_id");
    const auto pattern = pattern_value(request.at("pattern"));
    const project_io::RecordTakeReplayIdentity replay_identity{
        {
            foundation::CommandId{command_id},
            revision,
        },
        foundation::TakeId{take_id},
        pattern,
    };
    const auto replay = projects.replay_record_take(
        path, replay_identity);
    if (!replay.has_value()) {
      return error_envelope(replay.error());
    }
    if (replay.value().has_value()) {
      const auto& persisted = *replay.value();
      return success_envelope(
          {
              {"take_id", persisted.command.take.id.value()},
              {"pattern_id", persisted.command.pattern.id.value()},
              {"committed_revision",
               persisted.outcome.event.at("revision")
                   .get<std::uint64_t>()},
              {"replayed", true},
          },
          persisted.outcome.state.revision);
    }
    const auto active = journals.read_active_journal(
        path, foundation::TakeId{take_id});
    if (!active.has_value()) {
      return error_envelope(active.error());
    }
    if (revision != active.value().expected_revision) {
      const auto sealed = journals.seal(
          path,
          foundation::TakeId{take_id},
          "revision_conflict");
      if (!sealed.has_value()) {
        return error_envelope(sealed.error());
      }
      return error_envelope(
          Error{
              ErrorCode::revision_conflict,
              "take commit revision does not match its captured revision",
              {
                  {"captured_revision",
                   active.value().expected_revision},
                  {"expected_revision", revision},
              },
          });
    }
    const auto committed = projects.execute_with_identity(
        path,
        domain::Command{
            domain::RecordTake{
                {
                    foundation::CommandId{command_id},
                    active.value().expected_revision,
                },
                active.value().take,
                pattern,
            },
        });
    if (!committed.has_value()) {
      return error_envelope(committed.error());
    }
    const auto* persisted =
        std::get_if<domain::RecordTake>(&committed.value().command);
    if (persisted == nullptr) {
      return error_envelope(
          Error{
              ErrorCode::invalid_project,
              "persisted Take commit has the wrong command type",
          });
    }
    const auto& applied = committed.value().outcome;
    return success_envelope(
        {
            {"take_id", persisted->take.id.value()},
            {"pattern_id", persisted->pattern.id.value()},
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
          if (!bytes.has_value() || !limits.has_value()) {
            return bytes;
          }
          const auto metadata = cooker::inspect_wav(bytes.value());
          if (!metadata.has_value()) {
            return foundation::Result<std::vector<std::byte>>::failure(
                metadata.error());
          }
          if (!limits->allows_decoded_frames_per_pad(
                  metadata.value().source_frames)) {
            return foundation::Result<std::vector<std::byte>>::failure(
                runtime_preparation_limit_error(
                    "decoded_frames_per_pad",
                    metadata.value().source_frames,
                    limits->maximum_decoded_frames_per_pad));
          }
          return bytes;
        });
    if (!cooked.has_value() || !limits.has_value()) {
      return cooked;
    }

    std::uint64_t prospective_bank_bytes = 0;
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
      const auto total = audio::checked_runtime_byte_sum(
          prospective_bank_bytes, sample_bytes.value());
      if (!total.has_value()) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            Error{
                ErrorCode::invalid_argument,
                "runtime preparation Bank byte length overflowed",
            });
      }
      prospective_bank_bytes = total.value();
    }
    if (!limits->allows_prepared_bank_bytes(prospective_bank_bytes)) {
      return foundation::Result<
          std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
          runtime_preparation_limit_error(
              "prepared_bank_bytes",
              prospective_bank_bytes,
              limits->maximum_prepared_bank_bytes));
    }
    if (!limits->allows_live_bank_bytes(prospective_bank_bytes)) {
      return foundation::Result<
          std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
          runtime_preparation_limit_error(
              "live_bank_bytes",
              prospective_bank_bytes,
              limits->maximum_live_bank_bytes));
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

  nlohmann::json provider_run(const nlohmann::json& request) {
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
            }),
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
        *registry);
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

  nlohmann::json recoverable_list(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "project_path"}),
        "take.recoverable.list request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto listed = journals.list_recoverable(path);
    if (!listed.has_value()) {
      return error_envelope(listed.error());
    }
    auto candidates = nlohmann::json::array();
    for (const auto& candidate : listed.value()) {
      auto events = nlohmann::json::array();
      for (const auto& event : candidate.take.events) {
        events.push_back(raw_event_json(event));
      }
      candidates.push_back(
          {
              {"take_id", candidate.take.id.value()},
              {"expected_revision", candidate.expected_revision},
              {"reason", candidate.reason},
              {"sample_rate", candidate.take.sample_rate},
              {"events", std::move(events)},
          });
    }
    std::sort(
        candidates.begin(),
        candidates.end(),
        [](const auto& left, const auto& right) {
          return left.at("take_id").template get<std::string>() <
                 right.at("take_id").template get<std::string>();
        });
    return success_envelope(
        {{"candidates", std::move(candidates)}},
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
        {{"providers", std::move(providers)}},
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
  std::optional<audio::RuntimePreparationLimits> sample_limits;
  project_io::ProjectStore projects;
  project_io::TakeJournal journals;
  project_io::ProjectBundleTransfer bundle_transfers;
  project_io::WorkspaceCacheStore waveform_cache;
  provider::AttemptStore attempts;
  mutable std::mutex sample_mutex;
  std::map<std::string, SampleImportState> sample_imports;
  std::set<std::string> used_sample_import_tokens;
  std::deque<std::string> remembered_sample_import_tokens;
};

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

nlohmann::json Application::command(const nlohmann::json& request) {
  try {
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

foundation::Result<RuntimeProjectWriterLease>
Application::acquire_project_writer(
    const std::filesystem::path& project_path) {
  try {
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

foundation::Result<domain::ProjectState>
Application::create_initial_project(
    const InitialProjectRequest& request) {
  try {
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
    return impl_->abort_project_bundle_import(token);
  } catch (...) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<SampleInspectResult> Application::inspect_sample(
    const SampleInspectRequest& request) const {
  try {
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

foundation::Result<SampleImportSession> Application::begin_sample_import(
    const SampleImportBeginRequest& request) {
  try {
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
    return impl_->reset_sample_pad(request);
  } catch (...) {
    return foundation::Result<SampleMutationResult>::failure(Error{
        ErrorCode::internal_error,
        "unexpected Application Facade Host API failure",
    });
  }
}

foundation::Result<void> Application::append_realtime_take_events(
    const std::filesystem::path& project_path,
    foundation::TakeId take_id,
    std::span<const domain::RawTakeEvent> events) {
  try {
    return impl_->append_realtime_take_events(
        project_path, std::move(take_id), events);
  } catch (...) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<std::filesystem::path>
Application::seal_realtime_take(
    const std::filesystem::path& project_path,
    foundation::TakeId take_id,
    std::string_view reason) {
  try {
    return impl_->seal_realtime_take(
        project_path, std::move(take_id), reason);
  } catch (...) {
    return foundation::Result<std::filesystem::path>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

}  // namespace lmdj::facade
