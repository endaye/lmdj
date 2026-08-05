#include "control_runtime.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <limits>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

#include <picosha2.h>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/domain/commands.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>

namespace lmdj::web_host {
namespace {

using Json = nlohmann::json;
using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint32_t kSampleRate = 48'000;

std::chrono::milliseconds operation_deadline(std::string_view operation) {
  if (operation == "host.close") {
    return std::chrono::seconds(10);
  }
  if (operation == "host.status" || operation == "audio.activate" ||
      operation == "audio.suspend" || operation == "trigger") {
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
    require(exact_keys(event, {"slot", "step", "velocity"}));
    const auto step = unsigned_field(event, "step", bars * 16U - 1U);
    const auto velocity = unsigned_field(event, "velocity", 127);
    require(velocity != 0);
    parsed.push_back(domain::PatternEvent{
        slot_value(event.at("slot")),
        static_cast<std::uint32_t>(step),
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
  if (code == "IO_ERROR" && details.is_object() &&
      storage_condition != details.end() &&
      storage_condition->is_string() &&
      *storage_condition == "project_busy") {
    return host_error(
        "PROJECT_BUSY",
        "project is already open for writing");
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

  struct TakeSession {
    std::string id;
    std::uint64_t project_revision;
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

  bool request_cancelled() const noexcept {
    return request_deadline.has_value() &&
           std::chrono::steady_clock::now() >= *request_deadline;
  }

  std::uint32_t remaining_request_budget_ms() const noexcept {
    if (!request_deadline.has_value()) {
      return 0;
    }
    const auto now = std::chrono::steady_clock::now();
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
    return foundation::Result<void>::success();
  }

  SnapshotResult prepare_and_publish(std::string_view selected_pattern) {
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

    auto bank = audio::PreparedSampleBank::from_snapshot(snapshot, limits);
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
    if (cancel_if_expired()) {
      auto error = timeout_error();
      return SnapshotResult{false, false, std::nullopt, error.at("error")};
    }
    const auto publication = engine.publish_sample_bank(std::move(bank.value()));
    if (publication != audio::PublishResult::accepted) {
      auto error = state_error("runtime Bank publication is unavailable");
      return SnapshotResult{false, false, std::nullopt, error.at("error")};
    }
    reserved_live_bytes = *aggregate;
    runtime_ready = true;
    runtime_bank_project_id = project_id;
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

  foundation::Result<void> drain_capture_events() {
    if (!active_take.has_value() || !retained_project_path.has_value()) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "no active realtime Take",
      });
    }
    if (request_cancelled()) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::internal_error,
          "request deadline expired before Capture persistence",
      });
    }
    std::array<audio::CapturedTriggerEvent, 64> captured{};
    const auto count = engine.drain_capture(captured);
    if (count == 0) {
      return foundation::Result<void>::success();
    }
    std::array<domain::RawTakeEvent, 64> events{};
    for (std::size_t index = 0; index < count; ++index) {
      events[index] = domain::RawTakeEvent{
          domain::PadSlotId{
              static_cast<std::uint8_t>(captured[index].slot / 16U),
              static_cast<std::uint8_t>(captured[index].slot % 16U),
          },
          captured[index].frame_offset,
          captured[index].velocity,
      };
    }
    auto appended = application.append_realtime_take_events(
        *retained_project_path,
        foundation::TakeId{active_take->id},
        std::span<const domain::RawTakeEvent>(events.data(), count));
    if (request_cancelled()) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::internal_error,
          "request deadline expired after Capture persistence",
      });
    }
    return appended;
  }

  foundation::Result<void> drain_all_capture_events() {
    while (engine.capture_telemetry().drained_events <
           engine.capture_telemetry().captured_events) {
      const auto drained = drain_capture_events();
      if (!drained.has_value()) {
        return drained;
      }
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> seal_take(const TakeSession& take) {
    auto sealed = application.seal_realtime_take(
        *retained_project_path,
        foundation::TakeId{take.id},
        "capture_incomplete");
    if (!sealed.has_value()) {
      return foundation::Result<void>::failure(sealed.error());
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> seal_active_after_failure(Error failure) {
    const auto sealed = seal_take(*active_take);
    if (!sealed.has_value()) {
      return sealed;
    }
    active_take.reset();
    return foundation::Result<void>::failure(std::move(failure));
  }

  foundation::Result<void> finish_capture(bool make_committable) {
    if (!active_take.has_value()) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "no active realtime Take",
      });
    }
    trigger_admission = false;
    if (!coordinator.has_value() ||
        coordinator->await_quiescent == nullptr ||
        coordinator->begin_rendering == nullptr) {
      return seal_active_after_failure(Error{
          ErrorCode::internal_error,
          "audio capture acknowledgement is unavailable",
      });
    }
    bool worklet_paused = false;
    auto capture = engine.capture_telemetry().state;
    while (capture != audio::CaptureState::idle &&
           capture != audio::CaptureState::corrupted) {
      if (capture == audio::CaptureState::active) {
        const auto disarmed = engine.disarm_capture();
        if (!disarmed.has_value()) {
          return seal_active_after_failure(disarmed.error());
        }
      }
      if (worklet_paused) {
        const auto begun = coordinator->begin_rendering(
            coordinator->context);
        if (!begun.has_value()) {
          return seal_active_after_failure(begun.error());
        }
        worklet_paused = false;
      }
      const auto timeout_ms = remaining_request_budget_ms();
      if (timeout_ms == 0) {
        return seal_active_after_failure(Error{
            ErrorCode::internal_error,
            "capture barrier timed out",
        });
      }
      const auto quiescent = coordinator->await_quiescent(
          coordinator->context, timeout_ms);
      worklet_paused = true;
      if (!quiescent.has_value()) {
        return seal_active_after_failure(quiescent.error());
      }
      capture = engine.capture_telemetry().state;
    }
    if (capture == audio::CaptureState::corrupted) {
      return seal_active_after_failure(Error{
          ErrorCode::internal_error,
          "realtime capture was corrupted",
      });
    }
    const auto drained = drain_all_capture_events();
    if (!drained.has_value()) {
      return seal_active_after_failure(drained.error());
    }
    const auto take = *active_take;
    if (make_committable) {
      if (request_cancelled()) {
        return foundation::Result<void>::failure(Error{
            ErrorCode::internal_error,
            "request deadline expired before audio rendering resumed",
        });
      }
      const auto begun = coordinator->begin_rendering(
          coordinator->context);
      if (!begun.has_value()) {
        return seal_active_after_failure(begun.error());
      }
      if (request_cancelled()) {
        return foundation::Result<void>::failure(Error{
            ErrorCode::internal_error,
            "request deadline expired after audio rendering resumed",
        });
      }
      committable_take = take;
      active_take.reset();
      trigger_admission = true;
      return foundation::Result<void>::success();
    }
    const auto sealed = seal_take(take);
    if (sealed.has_value()) {
      active_take.reset();
    }
    return sealed;
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

  void seal_all_noexcept() noexcept {
    try {
      if (!retained_project_path.has_value()) {
        active_take.reset();
        committable_take.reset();
        return;
      }
      if (active_take.has_value()) {
        if (seal_take(*active_take).has_value()) {
          active_take.reset();
        }
      }
      if (committable_take.has_value()) {
        if (seal_take(*committable_take).has_value()) {
          committable_take.reset();
        }
      }
    } catch (...) {
    }
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
  std::optional<std::string> runtime_bank_project_id;
  std::optional<TakeSession> active_take;
  std::optional<TakeSession> committable_take;
  std::optional<detail::AudioQuiescenceCoordinator> coordinator;
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
      operation, payload, sidecar, std::chrono::steady_clock::now());
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
    if (operation == "project.create") {
      require(exact_keys(
          payload, {"project_id", "bpm", "initial_pattern"}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::running ||
          impl_->active_take.has_value() ||
          impl_->committable_take.has_value()) {
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
      impl_->runtime_ready = false;
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
          impl_->active_take.has_value() ||
          impl_->committable_take.has_value()) {
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
      if (switched) {
        impl_->runtime_ready = false;
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
             std::chrono::steady_clock::now() < deadline) {
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
      require(exact_keys(payload, {"slot", "velocity"}));
      require(sidecar.empty());
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
      const auto enqueued = impl_->engine.enqueue(audio::TriggerEvent{
          sequence,
          static_cast<std::uint8_t>(selected_slot),
          static_cast<std::uint8_t>(velocity),
      });
      if (enqueued != audio::EnqueueResult::accepted) {
        return state_error(enqueue_failure_message(enqueued));
      }
      ++impl_->next_trigger_sequence;
      return success(
          {{"sequence", sequence}, {"status", "enqueued"}});
    }
    if (operation == "take.begin") {
      require(exact_keys(payload, {"take_id", "expected_revision"}));
      require(sidecar.empty());
      if (impl_->state != Impl::State::running ||
          !impl_->session_available() || impl_->active_take.has_value() ||
          impl_->committable_take.has_value()) {
        return state_error();
      }
      const auto take_id = uuid_field(payload, "take_id");
      const auto revision = unsigned_field(payload, "expected_revision");
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto begun = impl_->application.command(
          {
              {"operation", "take.begin"},
              {"project_path",
               impl_->retained_project_path->generic_string()},
              {"take_id", take_id},
              {"expected_revision", revision},
              {"sample_rate", kSampleRate},
          });
      if (!begun.value("ok", false)) {
        return normalized_facade_error(begun);
      }
      if (impl_->cancel_if_expired()) {
        static_cast<void>(impl_->application.seal_realtime_take(
            *impl_->retained_project_path,
            foundation::TakeId{take_id},
            "capture_incomplete"));
        return timeout_error();
      }
      const auto armed = impl_->engine.arm_capture();
      if (!armed.has_value()) {
        impl_->application.seal_realtime_take(
            *impl_->retained_project_path,
            foundation::TakeId{take_id},
            "capture_incomplete");
        return normalized_error(armed.error());
      }
      const auto current_revision =
          begun.at("project_revision").get<std::uint64_t>();
      impl_->active_take = Impl::TakeSession{take_id, current_revision};
      impl_->trigger_admission = true;
      return success({
          {"take_id", take_id},
          {"project_revision", current_revision},
          {"capture_state", "arm_pending"},
      });
    }
    if (operation == "take.stop") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (impl_->state != Impl::State::running ||
          !impl_->active_take.has_value()) {
        return state_error();
      }
      const auto take = *impl_->active_take;
      const auto finished = impl_->finish_capture(true);
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (!finished.has_value()) {
        impl_->state = Impl::State::failed;
        impl_->trigger_admission = false;
        impl_->seal_all_noexcept();
        return normalized_error(finished.error());
      }
      return success({
          {"take_id", take.id},
          {"project_revision", take.project_revision},
          {"status", "committable"},
      });
    }
    if (operation == "take.commit") {
      require(exact_keys(
          payload, {"command_id", "expected_revision", "pattern"}));
      require(sidecar.empty());
      if (!impl_->session_available() ||
          !impl_->committable_take.has_value()) {
        return state_error();
      }
      uuid_field(payload, "command_id");
      unsigned_field(payload, "expected_revision");
      pattern_value(payload.at("pattern"));
      auto request = payload;
      request["operation"] = "take.commit";
      request["project_path"] =
          impl_->retained_project_path->generic_string();
      request["take_id"] = impl_->committable_take->id;
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
        impl_->committable_take.reset();
      }
      return response;
    }
    if (operation == "take.recoverable.list") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      return impl_->facade_query(
          {{"operation", "take.recoverable.list"},
           {"project_path", impl_->retained_project_path->generic_string()}});
    }
    if (operation == "audio.suspend") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::audio_suspended) {
        return success({
            {"state", "audio-suspended"},
            {"changed", false},
            {"sealed_take_id", nullptr},
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
      std::optional<std::string> sealed_take;
      std::optional<Error> capture_failure;
      if (impl_->active_take.has_value()) {
        sealed_take = impl_->active_take->id;
        const auto finished = impl_->finish_capture(false);
        if (!finished.has_value()) {
          capture_failure = finished.error();
        }
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto cleanup = impl_->quiesce_and_stop_audio();
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (capture_failure.has_value() || !cleanup.has_value()) {
        const auto failure = capture_failure.has_value()
                                 ? *capture_failure
                                 : cleanup.error();
        fail_and_seal("audio_suspend_failed");
        return normalized_error(failure);
      }
      impl_->state = Impl::State::audio_suspended;
      return success({
          {"state", "audio-suspended"},
          {"changed", true},
          {"sealed_take_id",
           sealed_take.has_value() ? Json(*sealed_take) : Json(nullptr)},
      });
    }
    if (operation == "host.close") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      std::optional<std::string> sealed_take;
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
        std::optional<Error> capture_failure;
        if (impl_->active_take.has_value()) {
          sealed_take = impl_->active_take->id;
          const auto finished = impl_->finish_capture(false);
          if (!finished.has_value()) {
            capture_failure = finished.error();
          }
        }
        observe_timeout();
        if (close_timed_out) {
          return timeout_error();
        }
        const auto cleanup = impl_->quiesce_and_stop_audio();
        if (capture_failure.has_value() || !cleanup.has_value()) {
          close_failure = capture_failure.has_value()
                              ? *capture_failure
                              : cleanup.error();
        }
      }
      if (impl_->committable_take.has_value()) {
        sealed_take = impl_->committable_take->id;
        const auto take = *impl_->committable_take;
        const auto sealed = impl_->seal_take(take);
        if (!sealed.has_value()) {
          impl_->state = Impl::State::failed;
          close_failure = sealed.error();
        } else {
          impl_->committable_take.reset();
        }
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
          {"sealed_take_id",
           sealed_take.has_value() ? Json(*sealed_take) : Json(nullptr)},
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

foundation::Result<void> ControlRuntime::drain_capture() {
  const auto capture = impl_->engine.capture_telemetry();
  if (capture.capture_drops != 0 ||
      capture.state == audio::CaptureState::corrupted) {
    fail_and_seal("capture_drop");
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "realtime capture was corrupted",
    });
  }
  auto drained = impl_->drain_capture_events();
  if (!drained.has_value() &&
      drained.error().code != ErrorCode::invalid_argument) {
    const auto failure = drained.error();
    fail_and_seal("capture_persistence_failure");
    return foundation::Result<void>::failure(failure);
  }
  if (!validate_realtime_health()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "realtime drain failed",
    });
  }
  return drained;
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

}  // namespace lmdj::web_host
