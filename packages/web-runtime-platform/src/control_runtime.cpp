#include <lmdj/web_runtime/control_runtime.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <cmath>
#include <limits>
#include <map>
#include <optional>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

#include <picosha2.h>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/domain/commands.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>

namespace lmdj::web_runtime {
namespace {

using Json = nlohmann::json;
using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint32_t kSampleRate = 48'000;

std::string generated_uuid() {
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

std::chrono::milliseconds operation_deadline(std::string_view operation) {
  if (operation == "host.close") {
    return std::chrono::seconds(10);
  }
  if (operation == "host.status" || operation == "audio.activate" ||
      operation == "audio.suspend" || operation == "trigger" ||
      operation == "sequence.record.event" ||
      operation == "sequence.record.status" ||
      operation == "sequence.recovery.list" ||
      operation == "sample.preview.set" ||
      operation == "sample.preview.clear" || operation == "sample.stop") {
    return std::chrono::seconds(1);
  }
  return std::chrono::seconds(30);
}

class ProtocolFailure final : public std::runtime_error {
 public:
  ProtocolFailure() : std::runtime_error("invalid Host protocol request") {}
};

[[noreturn]] void protocol_failure() { throw ProtocolFailure{}; }

bool exact_keys(
    const Json& value,
    std::initializer_list<std::string_view> keys) {
  if (!value.is_object() || value.size() != keys.size()) {
    return false;
  }
  return std::all_of(keys.begin(), keys.end(), [&value](const auto key) {
    return value.contains(std::string(key));
  });
}

void require(bool condition) {
  if (!condition) {
    protocol_failure();
  }
}

const std::string& string_field(const Json& value, std::string_view key) {
  const auto& field = value.at(std::string(key));
  require(field.is_string());
  return field.get_ref<const std::string&>();
}

std::uint64_t unsigned_field(
    const Json& value,
    std::string_view key,
    std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max()) {
  const auto& field = value.at(std::string(key));
  std::uint64_t result = 0;
  if (field.is_number_unsigned()) {
    result = field.get<std::uint64_t>();
  } else if (field.is_number_integer()) {
    const auto signed_result = field.get<std::int64_t>();
    require(signed_result >= 0);
    result = static_cast<std::uint64_t>(signed_result);
  } else {
    protocol_failure();
  }
  require(result <= maximum);
  return result;
}

bool bool_field(const Json& value, std::string_view key) {
  const auto& field = value.at(std::string(key));
  require(field.is_boolean());
  return field.get<bool>();
}

std::int32_t signed_field(
    const Json& value,
    std::string_view key,
    std::int32_t minimum,
    std::int32_t maximum) {
  const auto& field = value.at(std::string(key));
  require(field.is_number_integer());
  const auto result = field.get<std::int64_t>();
  require(result >= minimum && result <= maximum);
  return static_cast<std::int32_t>(result);
}

std::string uuid_field(const Json& value, std::string_view key) {
  const auto result = string_field(value, key);
  require(domain::is_valid_uuid(result));
  return result;
}

domain::PadSlotId slot_value(const Json& value) {
  require(exact_keys(value, {"bank", "pad"}));
  return domain::PadSlotId{
      static_cast<std::uint8_t>(unsigned_field(value, "bank", 3)),
      static_cast<std::uint8_t>(unsigned_field(value, "pad", 15)),
  };
}

std::uint8_t flatten_slot(domain::PadSlotId slot) noexcept {
  return static_cast<std::uint8_t>(slot.bank * 16U + slot.pad);
}

domain::TriggerMode trigger_mode_value(const Json& value) {
  require(value.is_string());
  const auto mode = value.get<std::string_view>();
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
  protocol_failure();
}

domain::PadPlayback playback_value(const Json& value) {
  require(exact_keys(
      value,
      {"trim_start_frame", "trim_end_frame", "trigger_mode",
       "gain_millidb", "muted"}));
  const auto start = unsigned_field(value, "trim_start_frame");
  std::optional<std::uint64_t> end;
  if (!value.at("trim_end_frame").is_null()) {
    end = unsigned_field(value, "trim_end_frame");
    require(*end > start);
  }
  return domain::PadPlayback{
      start,
      end,
      trigger_mode_value(value.at("trigger_mode")),
      signed_field(value, "gain_millidb", -60'000, 6'000),
      bool_field(value, "muted"),
  };
}

domain::Pattern pattern_value(const Json& value) {
  require(exact_keys(value, {"pattern_id", "bars", "events"}));
  const auto id = uuid_field(value, "pattern_id");
  const auto bars = unsigned_field(value, "bars", 8);
  require(bars == 1 || bars == 2 || bars == 4 || bars == 8);
  const auto& events = value.at("events");
  require(events.is_array());
  std::vector<domain::PatternEvent> parsed;
  parsed.reserve(events.size());
  for (const auto& event : events) {
    require(exact_keys(
        event, {"slot", "onset_tick", "duration_tick", "velocity"}));
    const auto loop_length = domain::pattern_length_ticks(
        static_cast<std::uint8_t>(bars));
    const auto onset = unsigned_field(event, "onset_tick", loop_length - 1U);
    const auto duration = unsigned_field(event, "duration_tick", loop_length);
    const auto velocity = unsigned_field(event, "velocity", 127);
    require(velocity != 0 && duration != 0 && duration <= loop_length - onset);
    parsed.push_back(domain::PatternEvent{
        slot_value(event.at("slot")),
        static_cast<std::uint32_t>(onset),
        static_cast<std::uint32_t>(duration),
        static_cast<std::uint8_t>(velocity),
    });
  }
  return domain::Pattern{
      foundation::PatternId{id},
      static_cast<std::uint8_t>(bars),
      std::move(parsed),
  };
}

Json success(Json result) {
  return {{"ok", true}, {"result", std::move(result)}};
}

Json host_error(
    std::string code,
    std::string message,
    Json details = Json::object()) {
  return {
      {"ok", false},
      {"error",
       {
           {"code", std::move(code)},
           {"message", std::move(message)},
           {"details", std::move(details)},
       }},
  };
}

Json protocol_error() {
  return host_error(
      "HOST_PROTOCOL_MISMATCH",
      "host protocol request is invalid");
}

Json state_error(std::string message = "operation is unavailable") {
  return host_error("HOST_STATE_INVALID", std::move(message));
}

Json timeout_error() {
  return host_error("HOST_TIMEOUT", "host request timed out");
}

Json internal_error() {
  return host_error("INTERNAL_ERROR", "unexpected Web Host failure");
}

Json sanitize_details(const Json& value) {
  static constexpr std::array<std::string_view, 3> revision_fields{
      "actual_revision",
      "expected_revision",
      "captured_revision",
  };
  const auto sensitive_container_key = [](std::string key) {
    std::transform(
        key.begin(), key.end(), key.begin(), [](unsigned char character) {
          return static_cast<char>(std::tolower(character));
        });
    return key.find("detail") != std::string::npos ||
           key.find("path") != std::string::npos ||
           key.find("system") != std::string::npos ||
           key.find("storage") != std::string::npos ||
           key == "errno";
  };
  const auto sanitize_node = [&](const auto& self, const Json& node)
      -> std::optional<Json> {
    if (node.is_object()) {
      auto result = Json::object();
      for (auto iterator = node.begin(); iterator != node.end(); ++iterator) {
        const auto approved_revision = std::find(
            revision_fields.begin(),
            revision_fields.end(),
            std::string_view(iterator.key()));
        if (approved_revision != revision_fields.end() &&
            iterator.value().is_number_unsigned()) {
          result[iterator.key()] = iterator.value();
          continue;
        }
        if (sensitive_container_key(iterator.key()) ||
            (!iterator.value().is_object() &&
             !iterator.value().is_array())) {
          continue;
        }
        const auto nested = self(self, iterator.value());
        if (nested.has_value()) {
          result[iterator.key()] = *nested;
        }
      }
      if (!result.empty()) {
        return result;
      }
      return std::nullopt;
    }
    if (node.is_array()) {
      auto result = Json::array();
      for (const auto& item : node) {
        if (!item.is_object() && !item.is_array()) {
          continue;
        }
        const auto nested = self(self, item);
        if (nested.has_value()) {
          result.push_back(*nested);
        }
      }
      if (!result.empty()) {
        return result;
      }
      return std::nullopt;
    }
    return std::nullopt;
  };
  const auto sanitized = sanitize_node(sanitize_node, value);
  return sanitized.has_value() && sanitized->is_object()
             ? *sanitized
             : Json::object();
}

std::string safe_message(std::string_view code) {
  static const std::map<std::string_view, std::string_view> messages{
      {"INVALID_ARGUMENT", "request is invalid"},
      {"NOT_FOUND", "requested resource was not found"},
      {"REVISION_CONFLICT", "project revision conflict"},
      {"DUPLICATE_ID", "identifier already exists"},
      {"UNSUPPORTED_AUDIO", "audio input is unsupported"},
      {"MISSING_ASSET", "required asset is missing"},
      {"INVALID_PROJECT", "project data is invalid"},
      {"COOK_FAILED", "runtime snapshot preparation failed"},
      {"PROVIDER_NOT_FOUND", "provider was not found"},
      {"PROVIDER_FAILED", "provider failed"},
      {"PERMISSION_DENIED", "operation is not permitted"},
      {"IO_ERROR", "project storage operation failed"},
      {"INTERNAL_ERROR", "unexpected Web Host failure"},
  };
  const auto found = messages.find(code);
  return std::string(
      found == messages.end() ? messages.at("INTERNAL_ERROR") : found->second);
}

Json normalized_error(
    std::string code,
    const Json& details,
    std::string_view source_message = {}) {
  const auto storage_condition =
      details.is_object() ? details.find("storage_condition") : details.end();
  const auto transfer_condition =
      details.is_object() ? details.find("transfer_condition") : details.end();
  if (code == "INVALID_PROJECT" && details.is_object() &&
      transfer_condition != details.end() &&
      transfer_condition->is_string() &&
      *transfer_condition == "resource_limit") {
    return host_error(
        "WEB_RUNTIME_RESOURCE_LIMIT",
        "Project Bundle exceeds the Web Runtime transfer limit");
  }
  if (code == "IO_ERROR" && details.is_object() &&
      storage_condition != details.end() &&
      storage_condition->is_string() &&
      *storage_condition == "project_busy") {
    return host_error(
        "PROJECT_BUSY",
        "project is already open for writing");
  }
  if (code == "IO_ERROR" && details.is_object() &&
      storage_condition != details.end() &&
      storage_condition->is_string() &&
      *storage_condition == "atomic_publish_unsupported") {
    return host_error(
        "UNSUPPORTED_WEB_RUNTIME",
        "atomic Project directory publication is unavailable");
  }
  if (code == "IO_ERROR" && details.is_object() &&
      storage_condition != details.end() &&
      storage_condition->is_string() &&
      *storage_condition == "already_exists") {
    return host_error(
        "DUPLICATE_ID",
        "a different Project already uses this identity");
  }
  if (code == "INVALID_ARGUMENT" &&
      source_message.starts_with("Project Bundle")) {
    return host_error("INVALID_PROJECT", "Project Bundle transfer is invalid");
  }
  static constexpr std::array<std::string_view, 4> resource_names{
      "artifact_bytes",
      "decoded_frames_per_pad",
      "prepared_bank_bytes",
      "live_bank_bytes",
  };
  const auto resource =
      details.is_object() ? details.find("resource") : details.end();
  const auto observed =
      details.is_object() ? details.find("observed") : details.end();
  const auto limit =
      details.is_object() ? details.find("limit") : details.end();
  const auto valid_resource =
      resource != details.end() && resource->is_string() &&
      std::find(
          resource_names.begin(),
          resource_names.end(),
          resource->get<std::string_view>()) != resource_names.end();
  if (code == "COOK_FAILED" &&
      source_message == "runtime preparation limit exceeded" &&
      valid_resource && observed != details.end() &&
      observed->is_number_unsigned() && limit != details.end() &&
      limit->is_number_unsigned()) {
    return host_error(
        "WEB_RUNTIME_RESOURCE_LIMIT",
        "runtime preparation limit exceeded",
        {
            {"resource", *resource},
            {"observed", *observed},
            {"limit", *limit},
        });
  }
  if (source_message == "capture barrier timed out") {
    return host_error("HOST_TIMEOUT", "capture barrier timed out");
  }
  return host_error(code, safe_message(code), sanitize_details(details));
}

Json normalized_error(const Error& error) {
  return normalized_error(
      std::string(foundation::error_code_name(error.code)),
      error.details,
      error.message);
}

Json normalized_facade_error(const Json& response) {
  if (!response.is_object() || response.value("ok", true) ||
      !response.contains("error") || !response.at("error").is_object()) {
    return internal_error();
  }
  const auto& error = response.at("error");
  if (!error.contains("code") || !error.at("code").is_string() ||
      !error.contains("message") || !error.at("message").is_string() ||
      !error.contains("details")) {
    return internal_error();
  }
  return normalized_error(
      error.at("code").get<std::string>(),
      error.at("details"),
      error.at("message").get<std::string>());
}

Json normalized_facade_success(const Json& response) {
  if (!response.is_object() || response.value("ok", false) != true ||
      !response.contains("result") || !response.at("result").is_object() ||
      !response.contains("project_revision")) {
    return internal_error();
  }
  auto result = response.at("result");
  result["project_revision"] = response.at("project_revision");
  return success(std::move(result));
}

std::string sha256(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* first =
        reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(first, first + bytes.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

void require_sidecar(
    const Json& declaration,
    std::span<const std::byte> sidecar) {
  require(exact_keys(
      declaration, {"sidecar_bytes", "sidecar_sha256"}));
  const auto declared_bytes = unsigned_field(
      declaration, "sidecar_bytes", detail::kBridgeMaximumSidecarBytes);
  const auto declared_sha = string_field(declaration, "sidecar_sha256");
  require(
      declared_sha.size() == 64 &&
      std::all_of(
          declared_sha.begin(), declared_sha.end(), [](char value) {
            return (value >= '0' && value <= '9') ||
                   (value >= 'a' && value <= 'f');
          }));
  require(declared_bytes == sidecar.size());
  require(sha256(sidecar) == declared_sha);
}

Json local_project_summary(const facade::LocalProjectSummary& summary) {
  return {
      {"project_id", summary.project_id.value()},
      {"pattern_id", summary.pattern_id.value()},
      {"revision", summary.revision},
      {"bpm", summary.bpm},
      {"asset_count", summary.asset_count},
      {"assigned_pad_count", summary.assigned_pad_count},
      {"bundle_digest", summary.bundle_digest},
  };
}

std::string capture_state_name(audio::CaptureState state) {
  switch (state) {
    case audio::CaptureState::idle:
      return "idle";
    case audio::CaptureState::arm_pending:
      return "arm_pending";
    case audio::CaptureState::active:
      return "active";
    case audio::CaptureState::disarm_pending:
      return "disarm_pending";
    case audio::CaptureState::corrupted:
      return "corrupted";
  }
  return "corrupted";
}

std::string enqueue_failure_message(audio::EnqueueResult result) {
  switch (result) {
    case audio::EnqueueResult::sample_unavailable:
      return "trigger sample is unavailable";
    case audio::EnqueueResult::bank_transition:
      return "runtime Bank transition is pending";
    case audio::EnqueueResult::queue_full:
      return "trigger queue is full";
    case audio::EnqueueResult::not_running:
      return "audio runtime is not running";
    case audio::EnqueueResult::invalid_slot:
    case audio::EnqueueResult::invalid_velocity:
    case audio::EnqueueResult::accepted:
      return "trigger is invalid";
  }
  return "trigger is invalid";
}

}  // namespace

struct ControlRuntime::Impl {
  enum class State { core_ready, running, audio_suspended, closed, failed };

  struct SequenceSession {
    foundation::SequenceSessionId id;
    foundation::PatternId pattern_id;
    std::uint64_t next_input_sequence{1};
    std::optional<domain::PadSlotId> armed_capture_slot;
  };

  struct PendingSequenceBoundary {
    foundation::SequenceSessionId session_id;
    foundation::PatternId pattern_id;
    std::uint64_t runtime_frame;
    std::uint64_t generation;
  };

  Impl(
      std::filesystem::path root,
      facade::Application owned_application,
      audio::RuntimePreparationLimits owned_limits)
      : workspace_root(std::move(root)),
        application(std::move(owned_application)),
        limits(owned_limits) {}

  std::filesystem::path project_path(std::string_view project_id) const {
    return workspace_root / "projects" /
           (std::string(project_id) + ".lmdj");
  }

  bool session_available() const noexcept {
    return project_id.has_value() && project_revision.has_value() &&
           retained_project_path.has_value() && writer_lease.has_value();
  }

  foundation::Result<facade::SequenceMutationResult> record_sequence_pad(
      domain::PadSlotId slot,
      std::uint8_t velocity,
      bool pressed) {
    if (!active_sequence.has_value() || !retained_project_path.has_value()) {
      return foundation::Result<facade::SequenceMutationResult>::failure(
          Error{ErrorCode::invalid_argument, "no Sequence session is active"});
    }
    const auto runtime_frame = engine.telemetry().rendered_frames;
    const auto input_sequence = active_sequence->next_input_sequence;
    auto recorded = application.record_sequence_event({
        *retained_project_path,
        active_sequence->id,
        facade::SequencePadEvent{
            slot, velocity, runtime_frame, input_sequence, pressed},
    });
    if (recorded.has_value()) {
      ++active_sequence->next_input_sequence;
    }
    return recorded;
  }

  foundation::Result<facade::SequenceMutationResult> stop_active_sequence() {
    if (!active_sequence.has_value() || !retained_project_path.has_value()) {
      return foundation::Result<facade::SequenceMutationResult>::failure(
          Error{ErrorCode::invalid_argument, "no Sequence session is active"});
    }
    const auto session_id = active_sequence->id;
    auto stopped = application.stop_sequence({
        *retained_project_path,
        session_id,
        foundation::CommandId{generated_uuid()},
        engine.telemetry().rendered_frames,
    });
    if (stopped.has_value()) {
      active_sequence.reset();
      if (stopped.value().committed_revision.has_value()) {
        project_revision = *stopped.value().committed_revision;
      }
    }
    return stopped;
  }

  foundation::Result<audio::PatternPublication> publish_project_pattern(
      const foundation::PatternId& selected_pattern,
      std::optional<std::uint64_t> activation_frame = std::nullopt) {
    if (!retained_project_path.has_value()) {
      return foundation::Result<audio::PatternPublication>::failure(
          Error{ErrorCode::invalid_argument, "no Project is open"});
    }
    auto snapshot = application.prepare_runtime_snapshot({
        *retained_project_path,
        selected_pattern,
        limits,
    });
    if (!snapshot.has_value()) {
      return foundation::Result<audio::PatternPublication>::failure(
          snapshot.error());
    }
    auto pattern = audio::PreparedPatternView::from_snapshot(*snapshot.value());
    if (!pattern.has_value()) {
      return foundation::Result<audio::PatternPublication>::failure(
          pattern.error());
    }
    const auto publication =
        engine.publish_pattern_view(std::move(pattern.value()), activation_frame);
    if (publication.result != audio::PatternPublishResult::accepted) {
      return foundation::Result<audio::PatternPublication>::failure(Error{
          ErrorCode::invalid_argument,
          "runtime Pattern publication is unavailable",
      });
    }
    return foundation::Result<audio::PatternPublication>::success(publication);
  }

  std::chrono::steady_clock::time_point clock_now() const noexcept {
    return clock.has_value() ? clock->now(clock->context)
                             : std::chrono::steady_clock::now();
  }

  void abort_tracked_sample_import(const Json& payload) noexcept {
    std::string token;
    try {
      if (!payload.is_object() || !payload.contains("import_token") ||
          !payload.at("import_token").is_string()) {
        return;
      }
      token = payload.at("import_token").get<std::string>();
    } catch (...) {
      return;
    }
    if (!sample_import_tokens.contains(token)) {
      return;
    }
    try {
      static_cast<void>(application.abort_sample_import(token));
    } catch (...) {
    }
    sample_import_tokens.erase(token);
    sample_import_slots.erase(token);
  }

  bool request_cancelled() const noexcept {
    return request_deadline.has_value() &&
           clock_now() >= *request_deadline;
  }

  std::uint32_t remaining_request_budget_ms() const noexcept {
    if (!request_deadline.has_value()) {
      return 0;
    }
    const auto now = clock_now();
    if (now >= *request_deadline) {
      return 0;
    }
    const auto remaining = *request_deadline - now;
    auto rounded = std::chrono::duration_cast<std::chrono::milliseconds>(
        remaining);
    if (rounded < remaining) {
      rounded += std::chrono::milliseconds(1);
    }
    return static_cast<std::uint32_t>(std::min<std::int64_t>(
        rounded.count(),
        std::numeric_limits<std::uint32_t>::max()));
  }

  Json status() const {
    const auto bank = engine.bank_telemetry();
    const auto acknowledged_generation =
        coordinator.has_value() &&
                coordinator->acknowledged_generation != nullptr
            ? coordinator->acknowledged_generation(coordinator->context)
            : 0;
    const auto audio_running =
        engine.telemetry().state == audio::RealtimeState::running;
    const auto generation_visible =
        runtime_ready && project_id.has_value() &&
        runtime_bank_project_id == project_id &&
        bank.accepted_publications != 0;
    return success({
        {"state", state_name()},
        {"project_id",
         project_id.has_value() ? Json(*project_id) : Json(nullptr)},
        {"project_revision",
         project_revision.has_value() ? Json(*project_revision)
                                      : Json(nullptr)},
        {"pattern_id",
         pattern_id.has_value() ? Json(*pattern_id) : Json(nullptr)},
        {"runtime_ready", runtime_ready},
        {"control_generation",
         generation_visible ? Json(bank.accepted_publications)
                            : Json(nullptr)},
        {"acknowledged_generation",
         generation_visible && acknowledged_generation != 0
             ? Json(acknowledged_generation)
             : Json(nullptr)},
        {"limits",
         {
             {"maximum_artifact_bytes", limits.maximum_artifact_bytes},
             {"maximum_decoded_frames_per_pad",
              limits.maximum_decoded_frames_per_pad},
             {"maximum_prepared_bank_bytes",
              limits.maximum_prepared_bank_bytes},
             {"maximum_live_bank_bytes", limits.maximum_live_bank_bytes},
         }},
        {"audio_state", audio_running ? "running" : "stopped"},
        {"capture_state",
         capture_state_name(engine.capture_telemetry().state)},
    });
  }

  std::string state_name() const {
    switch (state) {
      case State::core_ready:
        return "core-ready";
      case State::running:
        return "running";
      case State::audio_suspended:
        return "audio-suspended";
      case State::closed:
        return "closed";
      case State::failed:
        return "failed";
    }
    return "failed";
  }

  Json facade_command(Json request) {
    const auto response = application.command(request);
    if (!response.value("ok", false)) {
      return normalized_facade_error(response);
    }
    return normalized_facade_success(response);
  }

  Json facade_query(Json request) {
    const auto response = application.query(request);
    if (!response.value("ok", false)) {
      return normalized_facade_error(response);
    }
    return normalized_facade_success(response);
  }

  foundation::Result<cooker::ResolvedPlayback> resolve_preview_playback(
      const facade::SampleInspectResult& inspected,
      const domain::PadPlayback& playback) {
    if (!inspected.asset_id.has_value() ||
        !inspected.metadata.has_value()) {
      return foundation::Result<cooker::ResolvedPlayback>::failure(Error{
          ErrorCode::missing_asset,
          "Sample preview Pad is unassigned",
      });
    }
    const auto& metadata = *inspected.metadata;
    const auto source_end =
        playback.trim_end_frame.value_or(metadata.source_frames);
    if (metadata.sample_rate == 0 || playback.trim_start_frame >= source_end ||
        source_end > metadata.source_frames ||
        playback.trim_start_frame >
            std::numeric_limits<std::uint64_t>::max() / kSampleRate ||
        source_end >
            std::numeric_limits<std::uint64_t>::max() / kSampleRate) {
      return foundation::Result<cooker::ResolvedPlayback>::failure(Error{
          ErrorCode::invalid_argument,
          "Sample preview playback is invalid",
      });
    }
    const auto scaled_start = playback.trim_start_frame * kSampleRate;
    const auto scaled_end = source_end * kSampleRate;
    const auto runtime_start = scaled_start / metadata.sample_rate;
    const auto runtime_end =
        scaled_end / metadata.sample_rate +
        (scaled_end % metadata.sample_rate != 0 ? 1U : 0U);
    const auto prepared_frames =
        metadata.source_frames * kSampleRate / metadata.sample_rate +
        (metadata.source_frames * kSampleRate % metadata.sample_rate != 0
             ? 1U
             : 0U);
    const auto gain = static_cast<float>(std::pow(
        10.0, static_cast<double>(playback.gain_millidb) / 20'000.0));
    if (runtime_start >= runtime_end || runtime_end > prepared_frames ||
        runtime_start > std::numeric_limits<std::uint32_t>::max() ||
        runtime_end > std::numeric_limits<std::uint32_t>::max() ||
        !std::isfinite(gain)) {
      return foundation::Result<cooker::ResolvedPlayback>::failure(Error{
          ErrorCode::invalid_argument,
          "Sample preview playback is invalid",
      });
    }
    return foundation::Result<cooker::ResolvedPlayback>::success(
        cooker::ResolvedPlayback{
            static_cast<std::uint32_t>(runtime_start),
            static_cast<std::uint32_t>(runtime_end),
            playback.trigger_mode,
            gain,
            playback.muted,
        });
  }

  std::optional<Json> enqueue_sample_control(
      audio::PadControlKind kind,
      domain::PadSlotId slot,
      cooker::ResolvedPlayback playback = {}) {
    if (state != State::running || !trigger_admission || !runtime_ready ||
        runtime_bank_project_id != project_id) {
      return state_error("runtime control is unavailable");
    }
    const auto enqueued = engine.enqueue_control(audio::PadControlEvent{
        0,
        flatten_slot(slot),
        0,
        kind,
        playback,
    });
    if (enqueued != audio::EnqueueResult::accepted) {
      return state_error(enqueue_failure_message(enqueued));
    }
    return std::nullopt;
  }

  std::optional<Json> prepare_sample_mutation_controls(
      domain::PadSlotId slot,
      bool stop_voice) {
    if (state != State::running) {
      return std::nullopt;
    }
    if (stop_voice) {
      const auto stopped = enqueue_sample_control(
          audio::PadControlKind::stop_slot, slot);
      if (stopped.has_value()) {
        return stopped;
      }
    }
    return enqueue_sample_control(audio::PadControlKind::preview_clear, slot);
  }

  struct SnapshotResult {
    bool published = false;
    bool resource_rejected = false;
    std::optional<std::uint64_t> generation;
    Json error = nullptr;
  };

  foundation::Result<void> release_runtime_banks() {
    for (std::size_t slot = 0; slot < audio::kRealtimeSampleSlots; ++slot) {
      const auto cleared =
          engine.clear_sample(static_cast<std::uint8_t>(slot));
      if (!cleared.has_value()) {
        return cleared;
      }
    }
    const auto reclaimed = engine.reclaim_retired_bank_telemetry();
    if (reclaimed.decoded_pcm_bytes > reserved_live_bytes) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::internal_error,
          "runtime Bank reservation underflow",
      });
    }
    reserved_live_bytes -= reclaimed.decoded_pcm_bytes;
    if (reserved_live_bytes != 0) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::internal_error,
          "runtime Bank resources remain reserved",
      });
    }
    runtime_ready = false;
    runtime_bank_project_id.reset();
    runtime_revision.reset();
    return foundation::Result<void>::success();
  }

  SnapshotResult prepare_and_publish(
      std::string_view selected_pattern,
      bool preserve_saved_truth = false) {
    const auto reclaimed = engine.reclaim_retired_bank_telemetry();
    if (reclaimed.decoded_pcm_bytes > reserved_live_bytes) {
      throw std::logic_error("runtime Bank reservation underflow");
    }
    reserved_live_bytes -= reclaimed.decoded_pcm_bytes;

    auto prepared = application.prepare_runtime_snapshot(
        facade::RuntimeSnapshotRequest{
            *retained_project_path,
            foundation::PatternId{std::string(selected_pattern)},
            limits,
        });
    if (!prepared.has_value()) {
      auto error = normalized_error(prepared.error());
      return SnapshotResult{
          false,
          error.at("error").at("code") ==
              "WEB_RUNTIME_RESOURCE_LIMIT",
          std::nullopt,
          error.at("error"),
      };
    }
    const auto& snapshot = *prepared.value();
    if (!project_id.has_value() ||
        snapshot.project_id.value() != *project_id) {
      auto error = host_error(
          "INVALID_PROJECT", "project identity does not match selector");
      return SnapshotResult{false, false, std::nullopt, error.at("error")};
    }

    std::uint64_t candidate_bytes = 0;
    for (const auto& pad : snapshot.pads) {
      if (pad.sample == nullptr || pad.sample->channels == 0 ||
          pad.sample->interleaved.size() % pad.sample->channels != 0) {
        auto error = host_error(
            "INVALID_PROJECT", "runtime snapshot PCM is invalid");
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
      const auto frames = static_cast<std::uint64_t>(
          pad.sample->interleaved.size() / pad.sample->channels);
      const auto bytes = audio::checked_mono_float_bytes(frames);
      if (!bytes.has_value()) {
        auto error = host_error(
            "INVALID_PROJECT", "runtime snapshot PCM is invalid");
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
      const auto total =
          audio::checked_runtime_byte_sum(candidate_bytes, *bytes);
      if (!total.has_value()) {
        auto error = host_error(
            "INVALID_PROJECT", "runtime snapshot PCM is invalid");
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
      candidate_bytes = *total;
    }
    const auto aggregate =
        audio::checked_runtime_byte_sum(reserved_live_bytes, candidate_bytes);
    if (!aggregate.has_value() ||
        !limits.allows_live_bank_bytes(*aggregate)) {
      const auto observed = aggregate.value_or(
          std::numeric_limits<std::uint64_t>::max());
      auto error = host_error(
          "WEB_RUNTIME_RESOURCE_LIMIT",
          "runtime preparation limit exceeded",
          {
              {"resource", "live_bank_bytes"},
              {"observed", observed},
              {"limit", limits.maximum_live_bank_bytes},
          });
      return SnapshotResult{false, true, std::nullopt, error.at("error")};
    }

    // Application admission already applies the decoded-source frame limit.
    // The immutable Snapshot contains prepared 48 kHz frames, which can be
    // larger after 44.1 kHz resampling and must not be compared to that source
    // limit a second time. Publication retains every byte/live-bank bound.
    const auto publication_limits = audio::RuntimePreparationLimits{
        limits.maximum_artifact_bytes,
        std::numeric_limits<std::uint64_t>::max(),
        limits.maximum_prepared_bank_bytes,
        limits.maximum_live_bank_bytes,
    };
    auto bank = audio::PreparedSampleBank::from_snapshot(
        snapshot, publication_limits);
    if (!bank.has_value()) {
      auto error = normalized_error(bank.error());
      return SnapshotResult{
          false,
          error.at("error").at("code") ==
              "WEB_RUNTIME_RESOURCE_LIMIT",
          std::nullopt,
          error.at("error"),
      };
    }
    const auto current_pattern = engine.current_pattern_id();
    const auto publish_pattern =
        engine.telemetry().state == audio::RealtimeState::stopped ||
        !current_pattern.has_value() ||
        current_pattern->value() != selected_pattern;
    std::optional<audio::PreparedPatternView> pattern;
    if (publish_pattern) {
      auto prepared_pattern =
          audio::PreparedPatternView::from_snapshot(snapshot);
      if (!prepared_pattern.has_value()) {
        auto error = normalized_error(prepared_pattern.error());
        return SnapshotResult{
            false, false, std::nullopt, error.at("error")};
      }
      pattern.emplace(std::move(prepared_pattern.value()));
    }
    if (preserve_saved_truth ? request_cancelled() : cancel_if_expired()) {
      auto error = timeout_error();
      return SnapshotResult{false, false, std::nullopt, error.at("error")};
    }
    if (pattern.has_value() &&
        engine.telemetry().state == audio::RealtimeState::stopped) {
      const auto cleared = engine.clear_pattern_view();
      if (!cleared.has_value()) {
        auto error = normalized_error(cleared.error());
        return SnapshotResult{
            false, false, std::nullopt, error.at("error")};
      }
      static_cast<void>(engine.reclaim_retired_patterns());
    }
    const auto publication = engine.publish_sample_bank(std::move(bank.value()));
    if (publication != audio::PublishResult::accepted) {
      auto error = state_error("runtime Bank publication is unavailable");
      return SnapshotResult{false, false, std::nullopt, error.at("error")};
    }
    if (pattern.has_value()) {
      const auto pattern_publication =
          engine.publish_pattern_view(std::move(*pattern));
      if (pattern_publication.result !=
          audio::PatternPublishResult::accepted) {
        auto error = state_error("runtime Pattern publication is unavailable");
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
    }
    reserved_live_bytes = *aggregate;
    runtime_ready = true;
    runtime_bank_project_id = project_id;
    runtime_revision = snapshot.project_revision;
    pattern_id = std::string(selected_pattern);
    project_revision = snapshot.project_revision;
    const auto generation = engine.bank_telemetry().accepted_publications;
    return SnapshotResult{true, false, generation, nullptr};
  }

  Json open_result(
      std::string_view selected_pattern,
      const SnapshotResult& snapshot) const {
    return success({
        {"project_id", *project_id},
        {"project_revision", *project_revision},
        {"pattern_id", std::string(selected_pattern)},
        {"runtime_ready", snapshot.published},
        {"generation",
         snapshot.generation.has_value() ? Json(*snapshot.generation)
                                         : Json(nullptr)},
        {"snapshot_error", snapshot.error},
    });
  }

  Json retry_result(
      std::string_view selected_pattern,
      const SnapshotResult& snapshot) const {
    return success({
        {"project_id", *project_id},
        {"project_revision", *project_revision},
        {"pattern_id", std::string(selected_pattern)},
        {"runtime_ready", snapshot.published},
        {"generation",
         snapshot.generation.has_value() ? Json(*snapshot.generation)
                                         : Json(nullptr)},
        {"snapshot_error", snapshot.error},
        {"runtime_revision",
         runtime_revision.has_value() ? Json(*runtime_revision)
                                      : Json(nullptr)},
    });
  }

  Json sample_mutation_result(
      const facade::SampleMutationResult& mutation,
      domain::PadSlotId slot) {
    const auto inspected = application.inspect_sample(
        facade::SampleInspectRequest{*retained_project_path, slot});
    if (inspected.has_value()) {
      project_revision = inspected.value().project_revision;
    } else {
      project_revision = mutation.committed_revision;
    }
    SnapshotResult snapshot;
    if (mutation.runtime_prepare_required) {
      if (request_cancelled()) {
        const auto timeout = timeout_error();
        snapshot.error = timeout.at("error");
      } else {
        snapshot = prepare_and_publish(*pattern_id, true);
      }
    }
    Json result{
        {"committed_revision", mutation.committed_revision},
        {"runtime_revision",
         runtime_revision.has_value() ? Json(*runtime_revision)
                                      : Json(nullptr)},
        {"runtime_published", snapshot.published},
    };
    if (!snapshot.error.is_null()) {
      result["snapshot_error"] = snapshot.error;
    }
    return success(std::move(result));
  }

  foundation::Result<void> quiesce_and_stop_audio() noexcept {
    trigger_admission = false;
    if (!coordinator.has_value() ||
        coordinator->await_quiescent == nullptr) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::internal_error,
          "audio quiescence is unavailable",
      });
    }
    const auto timeout_ms = remaining_request_budget_ms();
    if (timeout_ms == 0) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::internal_error,
          "request deadline expired before audio quiescence",
      });
    }
    // The coordinator contract guarantees paused-or-terminal and no callback
    // in flight on every return, including a timeout/failure return.
    const auto quiescent = coordinator->await_quiescent(
        coordinator->context, timeout_ms);
    engine.stop();
    return quiescent;
  }

  foundation::Result<void> abort_imports() {
    std::optional<Error> first_failure;
    for (auto current = import_tokens.begin(); current != import_tokens.end();) {
      const auto aborted = application.abort_project_bundle_import(*current);
      if (aborted.has_value()) {
        current = import_tokens.erase(current);
        continue;
      }
      if (!first_failure.has_value()) {
        first_failure = aborted.error();
      }
      ++current;
    }
    for (auto current = sample_import_tokens.begin();
         current != sample_import_tokens.end();) {
      const auto aborted = application.abort_sample_import(*current);
      sample_import_slots.erase(*current);
      if (aborted.has_value()) {
        current = sample_import_tokens.erase(current);
        continue;
      }
      if (!first_failure.has_value()) {
        first_failure = aborted.error();
      }
      ++current;
    }
    if (first_failure.has_value()) {
      return foundation::Result<void>::failure(*first_failure);
    }
    return foundation::Result<void>::success();
  }

  void seal_all_noexcept() noexcept {
    try {
      static_cast<void>(abort_imports());
    } catch (...) {
    }
    application.abandon_sequence_sessions();
    active_sequence.reset();
    pending_sequence_boundary.reset();
  }

  bool cancel_if_expired() noexcept {
    if (!request_cancelled()) {
      return false;
    }
    trigger_admission = false;
    seal_all_noexcept();
    state = State::failed;
    return true;
  }

  std::filesystem::path workspace_root;
  facade::Application application;
  audio::RuntimePreparationLimits limits;
  audio::RealtimeEngine engine;
  State state = State::core_ready;
  std::optional<facade::RuntimeProjectWriterLease> writer_lease;
  std::optional<std::filesystem::path> retained_project_path;
  std::optional<std::string> project_id;
  std::optional<std::uint64_t> project_revision;
  std::optional<std::string> pattern_id;
  std::optional<std::uint16_t> project_bpm;
  std::optional<std::string> runtime_bank_project_id;
  std::optional<std::uint64_t> runtime_revision;
  std::optional<SequenceSession> active_sequence;
  std::optional<PendingSequenceBoundary> pending_sequence_boundary;
  std::optional<detail::AudioQuiescenceCoordinator> coordinator;
  std::optional<detail::ControlRuntimeClock> clock;
  std::set<std::string> import_tokens;
  std::set<std::string> sample_import_tokens;
  std::map<std::string, domain::PadSlotId> sample_import_slots;
  std::uint64_t reserved_live_bytes = 0;
  std::uint64_t next_trigger_sequence = 1;
  bool runtime_ready = false;
  bool trigger_admission = false;
  std::optional<std::chrono::steady_clock::time_point> request_deadline;
};

ControlRuntime::ControlRuntime(std::shared_ptr<Impl> impl) noexcept
    : impl_(std::move(impl)) {}

foundation::Result<std::unique_ptr<ControlRuntime>> ControlRuntime::create(
    std::filesystem::path workspace_root,
    facade::Application application,
    audio::RuntimePreparationLimits limits) {
  if (!workspace_root.is_absolute() ||
      workspace_root.lexically_normal() != workspace_root) {
    return foundation::Result<std::unique_ptr<ControlRuntime>>::failure(
        Error{ErrorCode::invalid_argument, "workspace root is invalid"});
  }
  try {
    return foundation::Result<std::unique_ptr<ControlRuntime>>::success(
        std::unique_ptr<ControlRuntime>(new ControlRuntime(
            std::make_shared<Impl>(
                std::move(workspace_root),
                std::move(application),
                limits))));
  } catch (...) {
    return foundation::Result<std::unique_ptr<ControlRuntime>>::failure(
        Error{ErrorCode::internal_error, "Web Host allocation failed"});
  }
}

Json ControlRuntime::dispatch(
    std::string_view operation,
    const Json& payload,
    std::span<const std::byte> sidecar) {
  return dispatch(
      operation, payload, sidecar, impl_->clock_now());
}

Json ControlRuntime::dispatch(
    std::string_view operation,
    const Json& payload,
    std::span<const std::byte> sidecar,
    std::chrono::steady_clock::time_point submitted_at) {
  struct DeadlineReset final {
    std::optional<std::chrono::steady_clock::time_point>& value;
    ~DeadlineReset() { value.reset(); }
  } reset{impl_->request_deadline};
  impl_->request_deadline = submitted_at + operation_deadline(operation);
  try {
    if (impl_->state == Impl::State::failed ||
        impl_->state == Impl::State::closed) {
      return state_error();
    }
    if (impl_->cancel_if_expired()) {
      return timeout_error();
    }
    if (operation == "host.status") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      return impl_->status();
    }
    if (operation == "project.list") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      const auto listed = impl_->application.list_local_projects();
      if (!listed.has_value()) {
        return normalized_error(listed.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      auto projects = Json::array();
      for (const auto& summary : listed.value()) {
        projects.push_back(local_project_summary(summary));
      }
      return success({{"projects", std::move(projects)}});
    }
    if (operation == "project.import.begin") {
      require(exact_keys(
          payload, {"import_token", "index_bytes", "index_sha256"}));
      require(sidecar.empty());
      const auto token = uuid_field(payload, "import_token");
      const auto index_bytes = unsigned_field(
          payload, "index_bytes", 4'194'304);
      require(index_bytes != 0);
      const auto index_sha256 = string_field(payload, "index_sha256");
      require(
          index_sha256.size() == 64 &&
          std::all_of(
              index_sha256.begin(), index_sha256.end(), [](char value) {
                return (value >= '0' && value <= '9') ||
                       (value >= 'a' && value <= 'f');
              }));
      const auto begun = impl_->application.begin_project_bundle_import(
          facade::ProjectBundleImportBeginRequest{
              token, index_bytes, index_sha256});
      if (!begun.has_value()) {
        return normalized_error(begun.error());
      }
      impl_->import_tokens.insert(token);
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({
          {"import_token", begun.value().token},
          {"expected_index_bytes", begun.value().expected_index_bytes},
      });
    }
    if (operation == "project.import.index") {
      require(exact_keys(
          payload, {"import_token", "offset", "final", "sidecar"}));
      const auto token = uuid_field(payload, "import_token");
      const auto offset = unsigned_field(payload, "offset");
      const auto final = bool_field(payload, "final");
      require_sidecar(payload.at("sidecar"), sidecar);
      const auto appended = impl_->application.append_project_bundle_index(
          token, offset, sidecar, final);
      if (!appended.has_value()) {
        return normalized_error(appended.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (!appended.value().has_value()) {
        return success({
            {"received_index_bytes", offset + sidecar.size()},
            {"final", false},
        });
      }
      const auto& identity = *appended.value();
      return success({
          {"project_id", identity.project_id.value()},
          {"bundle_digest", identity.bundle_digest},
          {"entry_count", identity.entry_count},
      });
    }
    if (operation == "project.import.entry") {
      require(exact_keys(
          payload,
          {"import_token", "entry_index", "offset", "final", "sidecar"}));
      const auto token = uuid_field(payload, "import_token");
      const auto entry_index = unsigned_field(payload, "entry_index", 4'095);
      const auto offset = unsigned_field(payload, "offset");
      const auto final = bool_field(payload, "final");
      require_sidecar(payload.at("sidecar"), sidecar);
      const auto appended = impl_->application.append_project_bundle_entry(
          token,
          static_cast<std::uint32_t>(entry_index),
          offset,
          sidecar,
          final);
      if (!appended.has_value()) {
        return normalized_error(appended.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({
          {"entry_index", entry_index},
          {"received_entry_bytes", offset + sidecar.size()},
          {"final", final},
      });
    }
    if (operation == "project.import.commit") {
      require(exact_keys(payload, {"import_token"}));
      require(sidecar.empty());
      const auto token = uuid_field(payload, "import_token");
      const auto committed =
          impl_->application.commit_project_bundle_import(token);
      impl_->import_tokens.erase(token);
      if (!committed.has_value()) {
        return normalized_error(committed.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success(local_project_summary(committed.value()));
    }
    if (operation == "project.import.abort") {
      require(exact_keys(payload, {"import_token"}));
      require(sidecar.empty());
      const auto token = uuid_field(payload, "import_token");
      const auto aborted =
          impl_->application.abort_project_bundle_import(token);
      impl_->import_tokens.erase(token);
      if (!aborted.has_value()) {
        return normalized_error(aborted.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({{"aborted", true}});
    }
    if (operation == "project.create") {
      require(exact_keys(
          payload, {"project_id", "bpm", "initial_pattern"}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::running ||
          impl_->active_sequence.has_value() ||
          !impl_->sample_import_tokens.empty()) {
        return state_error();
      }
      const auto project_id = uuid_field(payload, "project_id");
      const auto bpm = unsigned_field(payload, "bpm", 240);
      require(bpm >= 40);
      auto initial_pattern = pattern_value(payload.at("initial_pattern"));
      const auto initial_pattern_id = initial_pattern.id.value();
      const auto path = impl_->project_path(project_id);
      auto lease = impl_->application.acquire_project_writer(path);
      if (!lease.has_value()) {
        return normalized_error(lease.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      auto created = impl_->application.create_initial_project(
          facade::InitialProjectRequest{
              path,
              foundation::ProjectId{project_id},
              static_cast<std::uint16_t>(bpm),
              std::move(initial_pattern),
          });
      if (!created.has_value()) {
        return normalized_error(created.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      impl_->writer_lease.emplace(std::move(lease.value()));
      impl_->retained_project_path = path;
      impl_->project_id = project_id;
      impl_->project_revision = std::uint64_t{0};
      impl_->pattern_id = initial_pattern_id;
      impl_->project_bpm = static_cast<std::uint16_t>(bpm);
      impl_->runtime_ready = false;
      impl_->runtime_revision.reset();
      impl_->trigger_admission = false;
      impl_->state = Impl::State::core_ready;
      return success({
          {"project_id", project_id},
          {"project_revision", std::uint64_t{0}},
          {"initial_pattern_id", initial_pattern_id},
          {"runtime_ready", false},
      });
    }
    if (operation == "project.open") {
      require(exact_keys(payload, {"project_id", "pattern_id"}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::running ||
          impl_->active_sequence.has_value() ||
          !impl_->sample_import_tokens.empty()) {
        return state_error();
      }
      const auto selected_id = uuid_field(payload, "project_id");
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      const auto path = impl_->project_path(selected_id);
      auto lease = impl_->application.acquire_project_writer(path);
      if (!lease.has_value()) {
        return normalized_error(lease.error());
      }
      const auto inspected = impl_->application.query(
          {{"operation", "project.inspect"},
           {"project_path", path.generic_string()}});
      if (!inspected.value("ok", false)) {
        return normalized_facade_error(inspected);
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto& inspected_project =
          inspected.at("result").at("project");
      if (inspected_project.value("project_id", std::string{}) !=
          selected_id) {
        return host_error(
            "INVALID_PROJECT", "project identity does not match selector");
      }
      const auto switched =
          !impl_->runtime_bank_project_id.has_value() ||
          *impl_->runtime_bank_project_id != selected_id;
      impl_->writer_lease.emplace(std::move(lease.value()));
      impl_->retained_project_path = path;
      impl_->project_id = selected_id;
      impl_->project_revision =
          inspected.at("project_revision").get<std::uint64_t>();
      impl_->pattern_id = selected_pattern;
      impl_->project_bpm =
          inspected_project.at("bpm").get<std::uint16_t>();
      if (switched) {
        impl_->runtime_ready = false;
        impl_->runtime_revision.reset();
      }
      impl_->state = Impl::State::core_ready;
      const auto snapshot = impl_->prepare_and_publish(selected_pattern);
      if (!snapshot.published) {
        impl_->runtime_ready = false;
        if (!snapshot.resource_rejected) {
          return {{"ok", false}, {"error", snapshot.error}};
        }
        return impl_->open_result(selected_pattern, snapshot);
      }
      return impl_->open_result(selected_pattern, snapshot);
    }
    if (operation == "pattern.create") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "pattern_id", "bars"}));
      require(sidecar.empty());
      if (!impl_->session_available() || impl_->active_sequence.has_value()) {
        return state_error();
      }
      auto response = impl_->application.command({
          {"operation", "pattern.create"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"command_id", uuid_field(payload, "command_id")},
          {"expected_revision", unsigned_field(payload, "expected_revision")},
          {"pattern_id", uuid_field(payload, "pattern_id")},
          {"bars", unsigned_field(payload, "bars", 8)},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->project_revision =
          response.at("project_revision").get<std::uint64_t>();
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      return success(std::move(result));
    }
    if (operation == "project.inspect") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto response = impl_->facade_query(
          {{"operation", "project.inspect"},
           {"project_path", impl_->retained_project_path->generic_string()}});
      if (response.value("ok", false)) {
        impl_->project_revision =
            response.at("result").at("project_revision")
                .get<std::uint64_t>();
      }
      return response;
    }
    if (operation == "sample.inspect") {
      require(exact_keys(payload, {"slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_slot = slot_value(payload.at("slot"));
      auto response = impl_->facade_query(
          {{"operation", "sample.inspect"},
           {"project_path", impl_->retained_project_path->generic_string()},
           {"slot", payload.at("slot")}});
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (response.value("ok", false)) {
        impl_->project_revision =
            response.at("result").at("project_revision")
                .get<std::uint64_t>();
      }
      static_cast<void>(selected_slot);
      return response;
    }
    if (operation == "sample.waveform") {
      require(exact_keys(payload, {"slot", "window"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      static_cast<void>(slot_value(payload.at("slot")));
      const auto& window = payload.at("window");
      require(exact_keys(
          window, {"start_frame", "end_frame", "bucket_count"}));
      const auto start = unsigned_field(window, "start_frame");
      const auto end = unsigned_field(window, "end_frame");
      const auto buckets = unsigned_field(window, "bucket_count", 512);
      require(start < end && buckets != 0);
      auto response = impl_->facade_query(
          {{"operation", "sample.waveform"},
           {"project_path", impl_->retained_project_path->generic_string()},
           {"slot", payload.at("slot")},
           {"window", window}});
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (response.value("ok", false)) {
        impl_->project_revision =
            response.at("result").at("project_revision")
                .get<std::uint64_t>();
      }
      return response;
    }
    if (operation == "sample.import.begin") {
      require(
          exact_keys(
              payload,
              {"import_token", "command_id", "expected_revision", "slot",
               "asset_id", "byte_length"}) ||
          exact_keys(
              payload,
              {"import_token", "command_id", "expected_revision",
               "sequence_session_id", "slot", "asset_id", "byte_length"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto token = uuid_field(payload, "import_token");
      const auto command_id = uuid_field(payload, "command_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto selected_slot = slot_value(payload.at("slot"));
      const auto asset_id = uuid_field(payload, "asset_id");
      const auto sequence_session_id = payload.contains("sequence_session_id")
          ? std::optional<foundation::SequenceSessionId>{
                foundation::SequenceSessionId{
                    uuid_field(payload, "sequence_session_id")}}
          : std::nullopt;
      const auto byte_length = unsigned_field(
          payload, "byte_length", impl_->limits.maximum_artifact_bytes);
      require(byte_length != 0);
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto begun = impl_->application.begin_sample_import(
          facade::SampleImportBeginRequest{
              token,
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, expected_revision},
              selected_slot,
              foundation::AssetId{asset_id},
              byte_length,
              sequence_session_id,
          });
      if (!begun.has_value()) {
        return normalized_error(begun.error());
      }
      impl_->sample_import_tokens.insert(token);
      impl_->sample_import_slots[token] = selected_slot;
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({
          {"token", begun.value().token},
          {"expected_bytes", begun.value().expected_bytes},
      });
    }
    if (operation == "sample.import.chunk") {
      if (!exact_keys(
              payload,
              {"import_token", "offset", "final", "sidecar"})) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      const auto token = uuid_field(payload, "import_token");
      if (!impl_->session_available() ||
          !impl_->sample_import_tokens.contains(token)) {
        return state_error();
      }
      std::uint64_t offset = 0;
      bool final = false;
      try {
        offset = unsigned_field(payload, "offset");
        final = bool_field(payload, "final");
        require_sidecar(payload.at("sidecar"), sidecar);
        require(
            offset <= std::numeric_limits<std::uint64_t>::max() -
                          sidecar.size());
      } catch (const ProtocolFailure&) {
        impl_->abort_tracked_sample_import(payload);
        throw;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto appended = impl_->application.append_sample_import(
          token, offset, sidecar, final);
      if (!appended.has_value()) {
        impl_->sample_import_tokens.erase(token);
        impl_->sample_import_slots.erase(token);
        return normalized_error(appended.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({
          {"received_bytes", offset + sidecar.size()},
          {"final", final},
      });
    }
    if (operation == "sample.import.commit") {
      if (!exact_keys(payload, {"import_token"})) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      if (!sidecar.empty()) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto token = uuid_field(payload, "import_token");
      const auto found = impl_->sample_import_slots.find(token);
      if (!impl_->sample_import_tokens.contains(token) ||
          found == impl_->sample_import_slots.end()) {
        return normalized_error(Error{
            ErrorCode::invalid_argument,
            "Sample import token is not active",
        });
      }
      const auto selected_slot = found->second;
      if (const auto control =
              impl_->prepare_sample_mutation_controls(selected_slot, true);
          control.has_value()) {
        static_cast<void>(impl_->application.abort_sample_import(token));
        impl_->sample_import_tokens.erase(token);
        impl_->sample_import_slots.erase(token);
        return *control;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto committed = impl_->application.commit_sample_import(token);
      impl_->sample_import_tokens.erase(token);
      impl_->sample_import_slots.erase(token);
      if (!committed.has_value()) {
        return normalized_error(committed.error());
      }
      return impl_->sample_mutation_result(committed.value(), selected_slot);
    }
    if (operation == "sample.import.abort") {
      if (!exact_keys(payload, {"import_token"})) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      if (!sidecar.empty()) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto token = uuid_field(payload, "import_token");
      const auto aborted = impl_->application.abort_sample_import(token);
      impl_->sample_import_tokens.erase(token);
      impl_->sample_import_slots.erase(token);
      if (!aborted.has_value()) {
        return normalized_error(aborted.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({{"aborted", true}});
    }
    if (operation == "sample.update_pad") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "slot", "playback"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto command_id = uuid_field(payload, "command_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto selected_slot = slot_value(payload.at("slot"));
      const auto playback = playback_value(payload.at("playback"));
      if (const auto control = impl_->prepare_sample_mutation_controls(
              selected_slot, playback.muted);
          control.has_value()) {
        return *control;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto updated = impl_->application.update_sample_pad(
          facade::SampleUpdateRequest{
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, expected_revision},
              selected_slot,
              playback,
          });
      if (!updated.has_value()) {
        return normalized_error(updated.error());
      }
      return impl_->sample_mutation_result(updated.value(), selected_slot);
    }
    if (operation == "sample.reset_pad") {
      require(exact_keys(
          payload, {"command_id", "expected_revision", "slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto command_id = uuid_field(payload, "command_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto selected_slot = slot_value(payload.at("slot"));
      if (const auto control =
              impl_->prepare_sample_mutation_controls(selected_slot, true);
          control.has_value()) {
        return *control;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto reset = impl_->application.reset_sample_pad(
          facade::SampleResetRequest{
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, expected_revision},
              selected_slot,
          });
      if (!reset.has_value()) {
        return normalized_error(reset.error());
      }
      return impl_->sample_mutation_result(reset.value(), selected_slot);
    }
    if (operation == "sample.preview.set") {
      require(exact_keys(payload, {"slot", "playback"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_slot = slot_value(payload.at("slot"));
      const auto playback = playback_value(payload.at("playback"));
      const auto inspected = impl_->application.inspect_sample(
          facade::SampleInspectRequest{
              *impl_->retained_project_path, selected_slot});
      if (!inspected.has_value()) {
        return normalized_error(inspected.error());
      }
      if (!impl_->runtime_revision.has_value() ||
          !impl_->runtime_bank_project_id.has_value() ||
          impl_->runtime_bank_project_id != impl_->project_id ||
          inspected.value().project_revision != *impl_->runtime_revision) {
        return state_error("runtime Bank is not current");
      }
      const auto resolved =
          impl_->resolve_preview_playback(inspected.value(), playback);
      if (!resolved.has_value()) {
        return normalized_error(resolved.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (const auto control = impl_->enqueue_sample_control(
              audio::PadControlKind::preview_set,
              selected_slot,
              resolved.value());
          control.has_value()) {
        return *control;
      }
      return success({{"accepted", true}});
    }
    if (operation == "sample.preview.clear") {
      require(exact_keys(payload, {"slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_slot = slot_value(payload.at("slot"));
      if (const auto control = impl_->enqueue_sample_control(
              audio::PadControlKind::preview_clear, selected_slot);
          control.has_value()) {
        return *control;
      }
      return success({{"accepted", true}});
    }
    if (operation == "sample.stop") {
      require(exact_keys(payload, {}) || exact_keys(payload, {"slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto stop_all = payload.empty();
      const auto selected_slot =
          stop_all ? domain::PadSlotId{0, 0}
                   : slot_value(payload.at("slot"));
      if (const auto control = impl_->enqueue_sample_control(
              stop_all ? audio::PadControlKind::stop_all
                       : audio::PadControlKind::stop_slot,
              selected_slot);
          control.has_value()) {
        return *control;
      }
      return success({
          {"accepted", true},
          {"scope", stop_all ? "all" : "slot"},
      });
    }
    if (operation == "asset.import") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "asset_id", "media_type",
           "sidecar"}));
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto command_id = uuid_field(payload, "command_id");
      const auto revision = unsigned_field(payload, "expected_revision");
      const auto asset_id = uuid_field(payload, "asset_id");
      const auto media_type = string_field(payload, "media_type");
      require(!media_type.empty());
      const auto& declaration = payload.at("sidecar");
      require(exact_keys(
          declaration, {"sidecar_bytes", "sidecar_sha256"}));
      const auto declared_bytes =
          unsigned_field(declaration, "sidecar_bytes");
      const auto declared_sha = string_field(declaration, "sidecar_sha256");
      require(declared_sha.size() == 64 &&
              std::all_of(
                  declared_sha.begin(), declared_sha.end(), [](char value) {
                    return (value >= '0' && value <= '9') ||
                           (value >= 'a' && value <= 'f');
                  }));
      require(declared_bytes == sidecar.size());
      require(sha256(sidecar) == declared_sha);
      if (!impl_->limits.allows_artifact_bytes(sidecar.size())) {
        return host_error(
            "WEB_RUNTIME_RESOURCE_LIMIT",
            "runtime preparation limit exceeded",
            {
                {"resource", "artifact_bytes"},
                {"observed", sidecar.size()},
                {"limit", impl_->limits.maximum_artifact_bytes},
            });
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      auto imported = impl_->application.import_artifact_bytes(
          facade::ArtifactBytesImportRequest{
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, revision},
              foundation::AssetId{asset_id},
              media_type,
              sidecar,
          });
      if (!imported.has_value()) {
        return normalized_error(imported.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto& applied = imported.value();
      const auto found =
          applied.state.assets.find(foundation::AssetId{asset_id});
      if (found == applied.state.assets.end()) {
        throw std::logic_error("imported Asset is absent from Project state");
      }
      impl_->project_revision = applied.state.revision;
      return success({
          {"asset_id", asset_id},
          {"artifact", found->second.artifact},
          {"committed_revision",
           applied.event.at("revision").get<std::uint64_t>()},
          {"replayed", applied.replayed},
          {"project_revision", applied.state.revision},
      });
    }
    if (operation == "pad.assign") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "slot", "asset_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      uuid_field(payload, "command_id");
      unsigned_field(payload, "expected_revision");
      slot_value(payload.at("slot"));
      if (!payload.at("asset_id").is_null()) {
        uuid_field(payload, "asset_id");
      }
      auto request = payload;
      request["operation"] = "pad.assign";
      request["project_path"] =
          impl_->retained_project_path->generic_string();
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      auto response = impl_->facade_command(std::move(request));
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (response.value("ok", false)) {
        impl_->project_revision =
            response.at("result").at("project_revision")
                .get<std::uint64_t>();
      }
      return response;
    }
    if (operation == "snapshot.reload") {
      require(exact_keys(payload, {"pattern_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto snapshot = impl_->prepare_and_publish(selected_pattern);
      if (!snapshot.published) {
        return {{"ok", false}, {"error", snapshot.error}};
      }
      return impl_->open_result(selected_pattern, snapshot);
    }
    if (operation == "snapshot.retry") {
      require(exact_keys(payload, {"pattern_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      if (selected_pattern != *impl_->pattern_id) {
        return state_error("retry Pattern is not current");
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto snapshot = impl_->prepare_and_publish(selected_pattern);
      return impl_->retry_result(selected_pattern, snapshot);
    }
    if (operation == "audio.activate") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (!impl_->session_available() || !impl_->runtime_ready ||
          !impl_->runtime_bank_project_id.has_value() ||
          *impl_->runtime_bank_project_id != *impl_->project_id) {
        return state_error();
      }
      if (impl_->state == Impl::State::running) {
        return success({
            {"state", "running"},
            {"changed", false},
            {"generation",
             impl_->engine.bank_telemetry().accepted_publications},
        });
      }
      if (!impl_->coordinator.has_value() ||
          impl_->coordinator->ready == nullptr ||
          !impl_->coordinator->ready(impl_->coordinator->context)) {
        return state_error("audio output is not ready");
      }
      if (impl_->state != Impl::State::core_ready &&
          impl_->state != Impl::State::audio_suspended) {
        return state_error();
      }
      const auto bank = impl_->engine.bank_telemetry();
      const auto expected_generation = bank.accepted_publications;
      if (expected_generation == 0 ||
          bank.current_generation != expected_generation ||
          bank.pending_publications != 0) {
        return state_error("runtime Bank is not current");
      }
      const auto rollback = [this]() {
        impl_->trigger_admission = false;
        static_cast<void>(impl_->quiesce_and_stop_audio());
        fail_and_seal("audio_activation_failed");
        return internal_error();
      };
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto started = impl_->engine.start();
      if (!started.has_value()) {
        return rollback();
      }
      if (impl_->coordinator->begin_rendering == nullptr) {
        return rollback();
      }
      const auto begun = impl_->coordinator->begin_rendering(
          impl_->coordinator->context);
      if (impl_->request_cancelled()) {
        if (!begun.has_value()) {
          impl_->engine.stop();
        }
        fail_and_seal("audio_activation_timeout");
        return timeout_error();
      }
      if (!begun.has_value()) {
        const auto failed = rollback();
        return impl_->request_cancelled() ? timeout_error() : failed;
      }
      const auto deadline = *impl_->request_deadline;
      auto acknowledged = impl_->coordinator->acknowledged_generation(
          impl_->coordinator->context);
      while (acknowledged == 0 &&
             impl_->clock_now() < deadline) {
        std::this_thread::yield();
        acknowledged = impl_->coordinator->acknowledged_generation(
            impl_->coordinator->context);
      }
      if (acknowledged != expected_generation) {
        const auto timed_out = impl_->request_cancelled();
        if (timed_out) {
          fail_and_seal("audio_activation_timeout");
          return timeout_error();
        }
        const auto failed = rollback();
        return impl_->request_cancelled() ? timeout_error() : failed;
      }
      if (impl_->request_cancelled()) {
        fail_and_seal("audio_activation_timeout");
        return timeout_error();
      }
      impl_->state = Impl::State::running;
      impl_->trigger_admission = true;
      return success({
          {"state", "running"},
          {"changed", true},
          {"generation", expected_generation},
      });
    }
    if (operation == "trigger") {
      require(sidecar.empty());
      if (exact_keys(payload, {"slot", "kind"})) {
        const auto selected_slot = unsigned_field(payload, "slot", 63);
        require(string_field(payload, "kind") == "release");
        const auto structured_slot = domain::PadSlotId{
            static_cast<std::uint8_t>(selected_slot / 16U),
            static_cast<std::uint8_t>(selected_slot % 16U),
        };
        if (const auto control = impl_->enqueue_sample_control(
                audio::PadControlKind::release, structured_slot);
            control.has_value()) {
          return *control;
        }
        if (impl_->active_sequence.has_value()) {
          const auto recorded = impl_->record_sequence_pad(
              structured_slot, 0, false);
          if (!recorded.has_value()) {
            return normalized_error(recorded.error());
          }
        }
        return success({{"accepted", true}});
      }
      require(exact_keys(payload, {"slot", "velocity"}));
      const auto selected_slot = unsigned_field(payload, "slot", 63);
      const auto velocity = unsigned_field(payload, "velocity", 127);
      require(velocity != 0);
      if (impl_->state != Impl::State::running ||
          !impl_->trigger_admission || !impl_->runtime_ready ||
          impl_->runtime_bank_project_id != impl_->project_id) {
        return state_error();
      }
      const auto sequence = impl_->next_trigger_sequence;
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto enqueued = impl_->engine.enqueue_control(
          audio::PadControlEvent{
              sequence,
              static_cast<std::uint8_t>(selected_slot),
              static_cast<std::uint8_t>(velocity),
              audio::PadControlKind::press,
              {},
          });
      if (enqueued != audio::EnqueueResult::accepted) {
        return state_error(enqueue_failure_message(enqueued));
      }
      ++impl_->next_trigger_sequence;
      if (impl_->active_sequence.has_value()) {
        const auto recorded = impl_->record_sequence_pad(
            domain::PadSlotId{
                static_cast<std::uint8_t>(selected_slot / 16U),
                static_cast<std::uint8_t>(selected_slot % 16U),
            },
            static_cast<std::uint8_t>(velocity),
            true);
        if (!recorded.has_value()) {
          return normalized_error(recorded.error());
        }
      }
      return success(
          {{"sequence", sequence}, {"status", "enqueued"}});
    }
    if (operation == "sequence.record.begin") {
      require(
          exact_keys(
              payload, {"session_id", "pattern_id", "expected_revision"}) ||
          exact_keys(
              payload,
              {"session_id", "pattern_id", "expected_revision",
               "armed_capture_slot"}));
      require(sidecar.empty());
      if (impl_->state != Impl::State::running ||
          !impl_->session_available() || impl_->active_sequence.has_value() ||
          !impl_->project_bpm.has_value()) {
        return state_error();
      }
      const auto session_id = uuid_field(payload, "session_id");
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto armed_capture_slot =
          !payload.contains("armed_capture_slot") ||
                  payload.at("armed_capture_slot").is_null()
              ? std::optional<domain::PadSlotId>{}
              : std::optional<domain::PadSlotId>{
                    slot_value(payload.at("armed_capture_slot"))};
      const auto runtime_frame =
          impl_->engine.current_pattern_origin_frame();
      if (!runtime_frame.has_value()) {
        return state_error("runtime Pattern clock is unavailable");
      }
      auto response = impl_->application.command({
          {"operation", "sequence.record.begin"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", session_id},
          {"pattern_id", selected_pattern},
          {"expected_revision", expected_revision},
          {"runtime_frame", *runtime_frame},
          {"armed_capture_slot",
           armed_capture_slot.has_value()
               ? nlohmann::json{
                     {"bank", armed_capture_slot->bank},
                     {"pad", armed_capture_slot->pad}}
               : nlohmann::json(nullptr)},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->active_sequence = Impl::SequenceSession{
          foundation::SequenceSessionId{session_id},
          foundation::PatternId{selected_pattern},
          1,
          armed_capture_slot,
      };
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      result["transport_anchor"] = {
          {"runtime_frame", *runtime_frame},
          {"tick_numerator", 0},
          {"bpm", *impl_->project_bpm},
      };
      return success(std::move(result));
    }
    if (operation == "sequence.capture.disarm") {
      require(exact_keys(payload, {"session_id", "slot"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      const auto selected_slot = slot_value(payload.at("slot"));
      require(
          impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() == session_id);
      const auto disarmed = impl_->application.disarm_sequence_capture(
          facade::SequenceCaptureDisarmRequest{
              *impl_->retained_project_path,
              foundation::SequenceSessionId{session_id},
              selected_slot,
          });
      if (!disarmed.has_value()) {
        return normalized_error(disarmed.error());
      }
      impl_->active_sequence->armed_capture_slot.reset();
      return success({{"disarmed", true}});
    }
    if (operation == "sequence.settings.update") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "session_id", "bpm",
           "quantize_enabled", "swing_percent"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto session_id = payload.at("session_id").is_null()
          ? std::optional<std::string>{}
          : std::optional<std::string>{uuid_field(payload, "session_id")};
      if ((impl_->active_sequence.has_value() &&
           (!session_id.has_value() ||
            impl_->active_sequence->id.value() != *session_id)) ||
          (!impl_->active_sequence.has_value() && session_id.has_value())) {
        return state_error();
      }
      const auto runtime_frame = impl_->engine.telemetry().rendered_frames;
      auto response = impl_->application.command({
          {"operation", "sequence.settings.update"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"command_id", uuid_field(payload, "command_id")},
          {"expected_revision", unsigned_field(payload, "expected_revision")},
          {"session_id", session_id.has_value()
                             ? nlohmann::json(*session_id)
                             : nlohmann::json(nullptr)},
          {"runtime_frame", runtime_frame},
          {"bpm", payload.at("bpm")},
          {"quantize_enabled", payload.at("quantize_enabled")},
          {"swing_percent", payload.at("swing_percent")},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->project_revision =
          response.at("project_revision").get<std::uint64_t>();
      impl_->project_bpm =
          response.at("result").at("bpm").get<std::uint16_t>();
      nlohmann::json publication = nullptr;
      if (!payload.at("bpm").is_null()) {
        auto published = impl_->publish_project_pattern(
            foundation::PatternId{*impl_->pattern_id});
        if (!published.has_value()) {
          fail_and_seal("sequence_settings_publication_failed");
          return normalized_error(published.error());
        }
        publication = {
            {"generation", published.value().generation},
            {"activation_frame", published.value().activation_frame},
        };
      }
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      result["pattern_publication"] = std::move(publication);
      return success(std::move(result));
    }
    if (operation == "sequence.record.event") {
      require(exact_keys(payload, {"session_id", "event"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      require(
          impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() == session_id);
      const auto& event = payload.at("event");
      require(exact_keys(event, {"slot", "velocity", "pressed"}));
      const auto selected_slot = slot_value(event.at("slot"));
      const auto velocity = unsigned_field(event, "velocity", 127);
      const auto pressed = bool_field(event, "pressed");
      require((pressed && velocity != 0) || (!pressed && velocity == 0));
      const auto runtime_frame = impl_->engine.telemetry().rendered_frames;
      const auto input_sequence =
          impl_->active_sequence->next_input_sequence;
      auto response = impl_->application.command({
          {"operation", "sequence.record.event"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", session_id},
          {"event",
           {
               {"slot", event.at("slot")},
               {"velocity", velocity},
               {"runtime_frame", runtime_frame},
               {"input_sequence", input_sequence},
               {"pressed", pressed},
           }},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      ++impl_->active_sequence->next_input_sequence;
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      result["runtime_frame"] = runtime_frame;
      result["input_sequence"] = input_sequence;
      static_cast<void>(selected_slot);
      return success(std::move(result));
    }
    if (operation == "sequence.record.flush" ||
        operation == "sequence.record.stop") {
      require(exact_keys(payload, {"session_id", "command_id"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      const auto command_id = uuid_field(payload, "command_id");
      if (impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() != session_id) {
        return state_error();
      }
      const auto runtime_frame = impl_->engine.telemetry().rendered_frames;
      std::optional<foundation::PatternId> recorded_pattern;
      if (impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() == session_id) {
        recorded_pattern = impl_->active_sequence->pattern_id;
      }
      auto response = impl_->application.command({
          {"operation", std::string(operation)},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", session_id},
          {"command_id", command_id},
          {"runtime_frame", runtime_frame},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      if (response.at("project_revision").is_number_unsigned()) {
        impl_->project_revision =
            response.at("project_revision").get<std::uint64_t>();
      }
      Json pattern_publication = nullptr;
      const auto& sequence_result = response.at("result");
      if (recorded_pattern.has_value() &&
          sequence_result.at("committed_revision").is_number_unsigned() &&
          sequence_result.at("replayed") == false &&
          sequence_result.at("pattern_id").is_string() &&
          sequence_result.at("pattern_id").get<std::string>() ==
              recorded_pattern->value()) {
        auto published = impl_->publish_project_pattern(*recorded_pattern);
        if (!published.has_value()) {
          fail_and_seal("sequence_pattern_publication_failed");
          return normalized_error(published.error());
        }
        pattern_publication = {
            {"generation", published.value().generation},
            {"activation_frame", published.value().activation_frame},
        };
      }
      if (operation == "sequence.record.flush" &&
          impl_->active_sequence.has_value() &&
          sequence_result.at("pattern_id").is_string()) {
        impl_->active_sequence->pattern_id = foundation::PatternId{
            sequence_result.at("pattern_id").get<std::string>()};
        impl_->pattern_id = impl_->active_sequence->pattern_id.value();
      }
      if (operation == "sequence.record.stop" &&
          impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() == session_id) {
        impl_->active_sequence.reset();
      }
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      result["runtime_frame"] = runtime_frame;
      result["pattern_publication"] = std::move(pattern_publication);
      return success(std::move(result));
    }
    if (operation == "sequence.record.switch-request") {
      require(exact_keys(payload, {"session_id", "next_pattern_id"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      const auto next_pattern_id = uuid_field(payload, "next_pattern_id");
      if (!impl_->active_sequence.has_value() ||
          impl_->active_sequence->id.value() != session_id) {
        return state_error();
      }
      const auto runtime_frame = impl_->engine.telemetry().rendered_frames;
      auto response = impl_->application.command({
          {"operation", "sequence.record.switch-request"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", session_id},
          {"next_pattern_id", next_pattern_id},
          {"runtime_frame", runtime_frame},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      const auto effective_runtime_frame =
          response.at("result").at("effective_runtime_frame")
              .get<std::uint64_t>();
      auto published = impl_->publish_project_pattern(
          foundation::PatternId{next_pattern_id}, effective_runtime_frame);
      if (!published.has_value()) {
        fail_and_seal("sequence_switch_publication_failed");
        return normalized_error(published.error());
      }
      auto result = response.at("result");
      if (effective_runtime_frame != published.value().activation_frame) {
        fail_and_seal("sequence_switch_clock_mismatch");
        return internal_error();
      }
      impl_->pending_sequence_boundary = Impl::PendingSequenceBoundary{
          foundation::SequenceSessionId{session_id},
          foundation::PatternId{next_pattern_id},
          published.value().activation_frame,
          published.value().generation,
      };
      result["project_revision"] = response.at("project_revision");
      result["pattern_publication"] = {
          {"generation", published.value().generation},
          {"activation_frame", published.value().activation_frame},
      };
      return success(std::move(result));
    }
    if (operation == "sequence.record.status" ||
        operation == "sequence.recovery.list") {
      require(
          exact_keys(payload, {}) || exact_keys(payload, {"project_id"}));
      require(sidecar.empty());
      std::filesystem::path path;
      if (payload.empty()) {
        if (!impl_->retained_project_path.has_value()) {
          return state_error();
        }
        path = *impl_->retained_project_path;
      } else {
        path = impl_->project_path(uuid_field(payload, "project_id"));
      }
      return impl_->facade_query({
          {"operation", std::string(operation)},
          {"project_path", path.generic_string()},
      });
    }
    if (operation == "sequence.recovery.apply") {
      require(exact_keys(
          payload, {"session_id", "destination_pattern_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      uuid_field(payload, "session_id");
      if (!payload.at("destination_pattern_id").is_null()) {
        uuid_field(payload, "destination_pattern_id");
      }
      auto request = payload;
      request["operation"] = "sequence.recovery.apply";
      request["project_path"] =
          impl_->retained_project_path->generic_string();
      auto response = impl_->application.command(request);
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      if (response.at("project_revision").is_number_unsigned()) {
        impl_->project_revision =
            response.at("project_revision").get<std::uint64_t>();
      }
      return normalized_facade_success(response);
    }
    if (operation == "sequence.recovery.discard") {
      require(exact_keys(payload, {"session_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      auto request = payload;
      request["operation"] = "sequence.recovery.discard";
      request["project_path"] =
          impl_->retained_project_path->generic_string();
      return impl_->facade_command(std::move(request));
    }
    if (operation == "audio.suspend") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::audio_suspended) {
        return success({
            {"state", "audio-suspended"},
            {"changed", false},
            {"stopped_sequence_id", nullptr},
        });
      }
      if (impl_->state != Impl::State::running) {
        return state_error();
      }
      if (!impl_->coordinator.has_value() ||
          impl_->coordinator->await_quiescent == nullptr) {
        impl_->seal_all_noexcept();
        impl_->state = Impl::State::failed;
        impl_->trigger_admission = false;
        return state_error("audio quiescence is unavailable");
      }
      std::optional<std::string> stopped_sequence;
      std::optional<Error> sequence_failure;
      if (impl_->active_sequence.has_value()) {
        stopped_sequence = impl_->active_sequence->id.value();
        const auto stopped = impl_->stop_active_sequence();
        if (!stopped.has_value()) {
          sequence_failure = stopped.error();
        }
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto had_pending_pattern =
          impl_->engine.pending_pattern_id().has_value();
      const auto cleanup = impl_->quiesce_and_stop_audio();
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (!sequence_failure.has_value() && cleanup.has_value() &&
          (stopped_sequence.has_value() || had_pending_pattern) &&
          impl_->pattern_id.has_value()) {
        const auto refreshed =
            impl_->prepare_and_publish(*impl_->pattern_id, true);
        if (!refreshed.published) {
          sequence_failure = Error{
              ErrorCode::internal_error,
              "stopped Sequence Pattern could not be published",
          };
        }
      }
      if (sequence_failure.has_value() || !cleanup.has_value()) {
        const auto failure = sequence_failure.has_value()
                                 ? *sequence_failure
                                 : cleanup.error();
        fail_and_seal("audio_suspend_failed");
        return normalized_error(failure);
      }
      impl_->state = Impl::State::audio_suspended;
      return success({
          {"state", "audio-suspended"},
          {"changed", true},
          {"stopped_sequence_id",
           stopped_sequence.has_value() ? Json(*stopped_sequence)
                                        : Json(nullptr)},
      });
    }
    if (operation == "host.close") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      std::optional<std::string> stopped_sequence;
      std::optional<Error> close_failure;
      bool close_timed_out = false;
      const auto observe_timeout = [&] {
        if (!impl_->request_cancelled()) {
          return;
        }
        close_timed_out = true;
        impl_->trigger_admission = false;
        impl_->seal_all_noexcept();
        impl_->state = Impl::State::failed;
      };
      if (impl_->state == Impl::State::running) {
        if (!impl_->coordinator.has_value() ||
            impl_->coordinator->await_quiescent == nullptr) {
          impl_->seal_all_noexcept();
          impl_->state = Impl::State::failed;
          return state_error("audio quiescence is unavailable");
        }
        if (impl_->active_sequence.has_value()) {
          stopped_sequence = impl_->active_sequence->id.value();
          const auto stopped = impl_->stop_active_sequence();
          if (!stopped.has_value()) {
            close_failure = stopped.error();
          }
        }
        observe_timeout();
        if (close_timed_out) {
          return timeout_error();
        }
        const auto cleanup = impl_->quiesce_and_stop_audio();
        if (!cleanup.has_value()) {
          close_failure = cleanup.error();
        }
      }
      const auto imports_released = impl_->abort_imports();
      if (!imports_released.has_value() && !close_failure.has_value()) {
        close_failure = imports_released.error();
      }
      observe_timeout();
      const auto released = impl_->release_runtime_banks();
      observe_timeout();
      if (close_timed_out) {
        return timeout_error();
      }
      if (!released.has_value()) {
        fail_and_seal("host_close_bank_release_failed");
        return normalized_error(released.error());
      }
      if (close_failure.has_value()) {
        fail_and_seal("host_close_failed");
        return normalized_error(*close_failure);
      }
      impl_->trigger_admission = false;
      impl_->state = Impl::State::closed;
      impl_->writer_lease.reset();
      return success({
          {"state", "closed"},
          {"stopped_sequence_id",
           stopped_sequence.has_value() ? Json(*stopped_sequence)
                                        : Json(nullptr)},
      });
    }
    return protocol_error();
  } catch (const ProtocolFailure&) {
    return protocol_error();
  } catch (...) {
    fail_and_seal("unexpected_exception");
    return internal_error();
  }
}

std::vector<audio::RuntimeTriggerOutcomeEvent>
ControlRuntime::drain_outcomes() {
  if (!validate_realtime_health()) {
    return {};
  }
  std::vector<audio::RuntimeTriggerOutcomeEvent> result;
  result.reserve(64);
  std::array<audio::RuntimeTriggerOutcomeEvent, 64> batch{};
  const auto count = impl_->engine.drain_trigger_outcomes(batch);
  if (count > batch.size()) {
    fail_and_seal("trigger_outcome_batch_overflow");
    return {};
  }
  for (std::size_t index = 0; index < count; ++index) {
    result.push_back(batch[index]);
  }
  if (!validate_realtime_health()) {
    return {};
  }
  return result;
}

std::optional<SequenceBarBoundaryEvent>
ControlRuntime::drain_sequence_bar_boundary() {
  if (!impl_->pending_sequence_boundary.has_value()) {
    return std::nullopt;
  }
  const auto telemetry = impl_->engine.pattern_telemetry();
  const auto& pending = *impl_->pending_sequence_boundary;
  if (telemetry.current_generation != pending.generation ||
      impl_->engine.telemetry().rendered_frames < pending.runtime_frame) {
    return std::nullopt;
  }
  SequenceBarBoundaryEvent result{
      pending.session_id.value(),
      pending.pattern_id.value(),
      pending.runtime_frame,
      pending.generation,
  };
  impl_->pending_sequence_boundary.reset();
  return result;
}

std::vector<audio::RuntimeVoiceStateEvent>
ControlRuntime::drain_voice_states() {
  if (!validate_realtime_health()) {
    return {};
  }
  std::vector<audio::RuntimeVoiceStateEvent> result;
  result.reserve(64);
  std::array<audio::RuntimeVoiceStateEvent, 64> batch{};
  const auto count = impl_->engine.drain_voice_states(batch);
  if (count > batch.size()) {
    fail_and_seal("voice_state_batch_overflow");
    return {};
  }
  for (std::size_t index = 0; index < count; ++index) {
    result.push_back(batch[index]);
  }
  if (!validate_realtime_health()) {
    return {};
  }
  return result;
}

foundation::Result<void> ControlRuntime::drain_capture() {
  if (!validate_realtime_health()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "realtime capture health check failed",
    });
  }
  std::array<audio::CapturedTriggerEvent, 64> discarded{};
  while (impl_->engine.drain_capture(discarded) != 0) {
  }
  return foundation::Result<void>::success();
}

bool ControlRuntime::validate_realtime_health() noexcept {
  if (impl_->state == Impl::State::failed) {
    return false;
  }
  const auto capture = impl_->engine.capture_telemetry();
  if (capture.capture_drops != 0 ||
      capture.state == audio::CaptureState::corrupted) {
    fail_and_seal("capture_drop");
    return false;
  }
  if (impl_->engine.trigger_outcome_telemetry().runtime_outcome_drops != 0) {
    fail_and_seal("trigger_outcome_drop");
    return false;
  }
  const auto voice_state = impl_->engine.voice_state_telemetry();
  if (voice_state.voice_state_drops != 0 ||
      voice_state.state == audio::RuntimeVoiceStateStreamState::corrupted) {
    fail_and_seal("voice_state_drop");
    return false;
  }
  return true;
}

void ControlRuntime::fail_and_seal(std::string_view) noexcept {
  impl_->trigger_admission = false;
  impl_->seal_all_noexcept();
  impl_->state = Impl::State::failed;
}

bool ControlRuntime::failed() const noexcept {
  return impl_->state == Impl::State::failed;
}

audio::RealtimeEngine& ControlRuntime::engine() noexcept {
  return impl_->engine;
}

#if !defined(__EMSCRIPTEN__)
namespace detail {
nlohmann::json normalize_error_for_testing(const foundation::Error& error) {
  return normalized_error(error);
}
}  // namespace detail
#endif

foundation::Result<void> detail::ControlRuntimeAudioAccess::install(
    ControlRuntime& runtime,
    AudioQuiescenceCoordinator coordinator) noexcept {
  if (coordinator.context == nullptr ||
      coordinator.await_quiescent == nullptr ||
      coordinator.begin_rendering == nullptr || coordinator.ready == nullptr ||
      coordinator.acknowledged_generation == nullptr) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "audio quiescence coordinator is invalid",
    });
  }
  if (runtime.impl_->state == ControlRuntime::Impl::State::closed ||
      runtime.impl_->state == ControlRuntime::Impl::State::failed) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "audio quiescence coordinator cannot be installed",
    });
  }
  runtime.impl_->coordinator = coordinator;
  return foundation::Result<void>::success();
}

foundation::Result<void> detail::ControlRuntimeClockAccess::install(
    ControlRuntime& runtime,
    ControlRuntimeClock clock) noexcept {
  if (clock.context == nullptr || clock.now == nullptr) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Control Runtime clock is invalid",
    });
  }
  if (runtime.impl_->state == ControlRuntime::Impl::State::closed ||
      runtime.impl_->state == ControlRuntime::Impl::State::failed) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Control Runtime clock cannot be installed",
    });
  }
  runtime.impl_->clock = clock;
  return foundation::Result<void>::success();
}

detail::ControlRuntimeSnapshotTruth
detail::ControlRuntimeSnapshotAccess::read(
    const ControlRuntime& runtime) noexcept {
  return {
      runtime.impl_->project_revision,
      runtime.impl_->runtime_revision,
  };
}

}  // namespace lmdj::web_runtime
