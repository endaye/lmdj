#include "capture_writer.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <functional>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include <poll.h>
#include <unistd.h>

#include <nlohmann/json.hpp>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#if defined(__APPLE__)
#include <lmdj/audio/apple/coreaudio_output.hpp>
#endif
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/facade/assembly_loader.hpp>
#include <lmdj/facade/performance_engine_adapter.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>

namespace {

using Json = nlohmann::json;
using lmdj::audio::CaptureState;
using lmdj::audio::EnqueueResult;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RuntimeTriggerOutcomeEvent;
using lmdj::facade::Application;
using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::CommandId;
using lmdj::foundation::PatternId;
using lmdj::foundation::Result;
using lmdj::foundation::SequenceSessionId;
using lmdj::native_host::CaptureWriter;

constexpr std::size_t kMaximumCommandBytes = 64U * 1024U;
constexpr int kMaximumJsonContainerDepth = 32;
constexpr std::uint32_t kNoDeviceRenderFrames = 128;
constexpr int kControlTickMilliseconds = 2;
constexpr auto kControlDeadline = std::chrono::seconds(2);
constexpr std::string_view kHostVersion = "2.0.0";
#if !defined(LMDJ_NATIVE_PRODUCT_BUILD)
#error "Native Host Product Build identity is required"
#endif
constexpr std::string_view kProductBuild = LMDJ_NATIVE_PRODUCT_BUILD;
constexpr std::string_view kUsage =
    "usage: lmdj-native-host --workspace ABSOLUTE_PATH "
    "--assembly ABSOLUTE_ASSEMBLY_JSON "
    "--project ABSOLUTE_PROJECT_BUNDLE --pattern UUID [--no-device]\n";
constexpr std::string_view kInternalErrorFallback =
    "{\"error\":{\"code\":\"INTERNAL_ERROR\",\"details\":{},"
    "\"message\":\"unexpected Native Host failure\"},\"ok\":false}\n";

struct RawInvocation {
  std::string_view workspace;
  std::string_view assembly;
  std::string_view project;
  std::string_view pattern;
  bool no_device = false;
};

struct Invocation {
  std::filesystem::path workspace;
  std::filesystem::path assembly;
  std::filesystem::path project;
  PatternId pattern_id;
  bool no_device;
};

enum class FacadeSurface {
  command,
  query,
};

constexpr std::array<std::pair<std::string_view, FacadeSurface>, 23>
    kPerformanceOperations{{
        {"pattern.slot.assign", FacadeSurface::command},
        {"pattern.slot.clear", FacadeSurface::command},
        {"pattern.slot.move", FacadeSurface::command},
        {"performance.list", FacadeSurface::query},
        {"performance.inspect", FacadeSurface::query},
        {"performance.record.begin", FacadeSurface::command},
        {"performance.record.event", FacadeSurface::command},
        {"performance.record.launch-request", FacadeSurface::command},
        {"performance.record.flush", FacadeSurface::command},
        {"performance.record.stop", FacadeSurface::command},
        {"performance.record.status", FacadeSurface::query},
        {"performance.save", FacadeSurface::command},
        {"performance.discard", FacadeSurface::command},
        {"performance.recovery.list", FacadeSurface::query},
        {"performance.recovery.apply", FacadeSurface::command},
        {"performance.recovery.discard", FacadeSurface::command},
        {"performance.rename", FacadeSurface::command},
        {"performance.delete", FacadeSurface::command},
        {"performance.recording.bind", FacadeSurface::command},
        {"performance.replay.begin", FacadeSurface::command},
        {"performance.replay.stop", FacadeSurface::command},
        {"performance.replay.status", FacadeSurface::query},
        {"performance.resample.commit", FacadeSurface::command},
    }};

// Stage 11's Sound Set operations are a second Facade surface this Host
// forwards, kept in their own table so the P10-D20 Performance inventory that
// `tests/host/performance_cli_test.py` pins against the Facade stays exactly
// the Performance inventory.
constexpr std::array<std::pair<std::string_view, FacadeSurface>, 5>
    kSoundSetOperations{{
        {"soundset.audition", FacadeSurface::query},
        {"soundset.catalog.list", FacadeSurface::query},
        {"soundset.inspect", FacadeSurface::query},
        {"soundset.map.preview", FacadeSurface::query},
        {"soundset.install", FacadeSurface::command},
    }};

std::optional<FacadeSurface> performance_surface(std::string_view operation) {
  for (const auto& [name, surface] : kPerformanceOperations) {
    if (name == operation) {
      return surface;
    }
  }
  return std::nullopt;
}

std::optional<FacadeSurface> soundset_surface(std::string_view operation) {
  for (const auto& [name, surface] : kSoundSetOperations) {
    if (name == operation) {
      return surface;
    }
  }
  return std::nullopt;
}

enum class LineStatus {
  line,
  end,
  too_large,
};

struct LineRead {
  LineStatus status;
  std::string bytes;
};

bool valid_utf8(std::string_view value) {
  std::size_t offset = 0;
  while (offset < value.size()) {
    const auto first = static_cast<unsigned char>(value[offset]);
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

std::optional<RawInvocation> parse_raw_invocation(
    int argc,
    char** argv) {
  RawInvocation invocation;
  bool has_workspace = false;
  bool has_assembly = false;
  bool has_project = false;
  bool has_pattern = false;
  bool has_no_device = false;
  for (int index = 1; index < argc; ++index) {
    const auto flag = std::string_view(argv[index]);
    if (flag == "--no-device") {
      if (has_no_device) {
        return std::nullopt;
      }
      has_no_device = true;
      invocation.no_device = true;
      continue;
    }
    if (index + 1 >= argc) {
      return std::nullopt;
    }
    const auto value = std::string_view(argv[++index]);
    if (flag == "--workspace" && !has_workspace) {
      invocation.workspace = value;
      has_workspace = true;
    } else if (flag == "--assembly" && !has_assembly) {
      invocation.assembly = value;
      has_assembly = true;
    } else if (flag == "--project" && !has_project) {
      invocation.project = value;
      has_project = true;
    } else if (flag == "--pattern" && !has_pattern) {
      invocation.pattern = value;
      has_pattern = true;
    } else {
      return std::nullopt;
    }
  }
  if (!has_workspace || !has_assembly || !has_project || !has_pattern) {
    return std::nullopt;
  }
  return invocation;
}

bool valid_path(
    std::string_view value,
    std::filesystem::path* output) {
  if (value.empty() || !valid_utf8(value)) {
    return false;
  }
  *output = std::filesystem::path(value);
  return output->is_absolute() && output->lexically_normal() == *output;
}

Result<Invocation> validate_invocation(const RawInvocation& raw) {
  Invocation invocation{
      {},
      {},
      {},
      PatternId{std::string(raw.pattern)},
      raw.no_device,
  };
  if (!valid_path(raw.workspace, &invocation.workspace) ||
      !valid_path(raw.assembly, &invocation.assembly) ||
      !valid_path(raw.project, &invocation.project) ||
      !valid_utf8(raw.pattern) ||
      !lmdj::domain::is_valid_uuid(raw.pattern)) {
    return Result<Invocation>::failure(Error{
        ErrorCode::invalid_argument,
        "workspace, assembly, and project must be absolute normalized UTF-8 "
        "paths and pattern must be a UUID",
    });
  }
  return Result<Invocation>::success(std::move(invocation));
}

Json error_response(
    std::string_view code,
    std::string_view message,
    Json details = Json::object()) {
  return {
      {"ok", false},
      {"error",
       {
           {"code", code},
           {"message", message},
           {"details", std::move(details)},
       }},
  };
}

Json error_response(const Error& error) {
  return error_response(
      lmdj::foundation::error_code_name(error.code),
      error.message,
      error.details);
}

Json invalid_request(std::string_view message) {
  return error_response("INVALID_ARGUMENT", message);
}

Json success_response(std::string_view operation, Json result) {
  return {
      {"ok", true},
      {"operation", operation},
      {"result", std::move(result)},
  };
}

bool response_ok(const Json& response) {
  const auto ok = response.find("ok");
  return ok != response.end() && ok->is_boolean() && ok->get<bool>();
}

bool write_response(const Json& response) {
  const auto encoded = lmdj::foundation::canonical_json(response);
  std::cout.write(
      encoded.data(), static_cast<std::streamsize>(encoded.size()));
  std::cout.put('\n');
  std::cout.flush();
  return static_cast<bool>(std::cout);
}

class ControlTicker final {
 public:
  explicit ControlTicker(std::function<void()> control_tick)
      : control_tick_(std::move(control_tick)),
        next_tick_(std::chrono::steady_clock::now() + kPeriod) {}

  void service_if_due() {
    const auto now = std::chrono::steady_clock::now();
    if (now < next_tick_) {
      return;
    }
    control_tick_();
    const auto completed = std::chrono::steady_clock::now();
    do {
      next_tick_ += kPeriod;
    } while (next_tick_ <= completed);
  }

  int poll_timeout_milliseconds() const {
    const auto remaining = std::chrono::ceil<std::chrono::milliseconds>(
        next_tick_ - std::chrono::steady_clock::now());
    return static_cast<int>(
        std::max<std::int64_t>(0, remaining.count()));
  }

 private:
  static constexpr auto kPeriod =
      std::chrono::milliseconds(kControlTickMilliseconds);
  std::function<void()> control_tick_;
  std::chrono::steady_clock::time_point next_tick_;
};

LineRead read_line(ControlTicker& control_ticker) {
  std::string bytes;
  bytes.reserve(kMaximumCommandBytes);
  bool too_large = false;
  char value = 0;
  while (true) {
    control_ticker.service_if_due();
    pollfd input{STDIN_FILENO, POLLIN, 0};
    const auto ready =
        ::poll(&input, 1, control_ticker.poll_timeout_milliseconds());
    control_ticker.service_if_due();
    if (ready == 0) {
      continue;
    }
    if (ready < 0) {
      if (errno == EINTR) {
        continue;
      }
      break;
    }
    const auto count = ::read(STDIN_FILENO, &value, 1);
    control_ticker.service_if_due();
    if (count == 0) {
      break;
    }
    if (count < 0) {
      if (errno == EINTR) {
        continue;
      }
      break;
    }
    if (value == '\n') {
      return LineRead{
          too_large ? LineStatus::too_large : LineStatus::line,
          std::move(bytes),
      };
    }
    if (bytes.size() < kMaximumCommandBytes) {
      bytes.push_back(value);
    } else {
      too_large = true;
    }
  }
  if (bytes.empty() && !too_large) {
    return LineRead{LineStatus::end, {}};
  }
  return LineRead{
      too_large ? LineStatus::too_large : LineStatus::line,
      std::move(bytes),
  };
}

std::optional<Json> parse_bounded_json(std::string_view bytes) {
  if (bytes.empty() || !valid_utf8(bytes)) {
    return std::nullopt;
  }
  bool depth_exceeded = false;
  const auto callback = [&depth_exceeded](
                            int depth,
                            Json::parse_event_t event,
                            Json&) {
    const bool container_start =
        event == Json::parse_event_t::object_start ||
        event == Json::parse_event_t::array_start;
    if (container_start && depth >= kMaximumJsonContainerDepth) {
      depth_exceeded = true;
      return false;
    }
    return true;
  };
  auto parsed = Json::parse(
      bytes.begin(), bytes.end(), callback, false);
  if (depth_exceeded || parsed.is_discarded() || !parsed.is_object()) {
    return std::nullopt;
  }
  return parsed;
}

bool exact_keys(
    const Json& value,
    std::initializer_list<std::string_view> keys) {
  if (!value.is_object() || value.size() != keys.size()) {
    return false;
  }
  return std::all_of(keys.begin(), keys.end(), [&](std::string_view key) {
    return value.contains(std::string(key));
  });
}

std::optional<std::uint64_t> unsigned_value(
    const Json& request,
    std::string_view key) {
  const auto iterator = request.find(std::string(key));
  if (iterator == request.end() || !iterator->is_number_unsigned()) {
    return std::nullopt;
  }
  return iterator->get<std::uint64_t>();
}

std::optional<std::string> uuid_value(
    const Json& request,
    std::string_view key) {
  const auto iterator = request.find(std::string(key));
  if (iterator == request.end() || !iterator->is_string()) {
    return std::nullopt;
  }
  const auto value = iterator->get<std::string>();
  if (!valid_utf8(value) || !lmdj::domain::is_valid_uuid(value)) {
    return std::nullopt;
  }
  return value;
}

Result<void> host_failure(ErrorCode code, std::string message) {
  return Result<void>::failure(Error{code, std::move(message)});
}

std::string_view capture_state_name(CaptureState state) noexcept {
  switch (state) {
    case CaptureState::idle:
      return "idle";
    case CaptureState::arm_pending:
      return "arm_pending";
    case CaptureState::active:
      return "active";
    case CaptureState::disarm_pending:
      return "disarm_pending";
    case CaptureState::corrupted:
      return "corrupted";
  }
  return "corrupted";
}

class NativeHost final {
 public:
  NativeHost(
      Invocation invocation,
      std::shared_ptr<lmdj::provider::Registry> providers,
      lmdj::provider::ProviderPolicy provider_policy)
      : invocation_(std::move(invocation)),
        performance_adapter_(lmdj::facade::make_engine_performance_adapter(
            engine_,
            lmdj::facade::make_engine_pattern_publication_gateway(engine_))),
        catalog_(lmdj::facade::make_workspace_soundset_catalog(
            invocation_.workspace)),
        application_(lmdj::facade::ApplicationConfig{
            invocation_.workspace,
            std::move(providers),
            std::move(provider_policy),
            {},
            std::nullopt,
            nullptr,
            performance_adapter_.clock,
            performance_adapter_.input_sequencer,
            performance_adapter_.launch_acknowledger,
            performance_adapter_.replay_controller,
            performance_adapter_.gesture_sink,
            catalog_.transport,
            catalog_.source,
        }) {
#if defined(__APPLE__)
    if (!invocation_.no_device) {
      output_ = std::make_unique<lmdj::audio::apple::CoreAudioOutput>(engine_);
    }
#endif
  }

  ~NativeHost() {
    if (writer_ != nullptr) {
      const auto state = engine_.capture_telemetry().state;
      if (state == CaptureState::active) {
        {
          std::lock_guard lock(facade_mutex_);
          (void)engine_.disarm_capture();
        }
        drive_no_device_once();
      }
      writer_->request_stop();
      writer_->join();
      writer_.reset();
    }
    if (running_) {
      (void)stop_backend();
    }
  }

  Result<void> startup() {
    const auto prepared = prepare_snapshot(invocation_.pattern_id);
    if (!prepared.has_value()) {
      return Result<void>::failure(prepared.error());
    }
    auto bank = PreparedSampleBank::from_snapshot(*prepared.value());
    if (!bank.has_value()) {
      return Result<void>::failure(bank.error());
    }
    if (engine_.publish_sample_bank(std::move(bank.value())) !=
        PublishResult::accepted) {
      return host_failure(
          ErrorCode::internal_error,
          "initial Sample Bank publication failed");
    }
    auto prepared_fx = engine_.prepare_master_fx(prepared.value()->bpm);
    if (!prepared_fx.has_value()) {
      return prepared_fx;
    }
    snapshot_ = prepared.value();
    pattern_id_ = invocation_.pattern_id;
    auto started = start_backend();
    if (started.has_value() && trigger_outcome_failed()) {
      (void)stop_backend();
      started = host_failure(
          ErrorCode::internal_error,
          "Realtime Trigger outcome ring dropped events during startup");
    }
    return started;
  }

  Json ready_response() const {
    return success_response(
        "ready",
        {
            {"backend", invocation_.no_device ? "deterministic" : "coreaudio"},
            {"host_version", kHostVersion},
            {"product_build", kProductBuild},
            {"project_id", snapshot_->project_id.value()},
            {"project_revision", snapshot_->project_revision},
            {"resolved_pad_count", snapshot_->pads.size()},
        });
  }

  Json handle(const Json& request) {
    const auto operation = request.find("operation");
    const bool has_operation =
        operation != request.end() && operation->is_string();
    const auto name = has_operation ? operation->get<std::string>() : "";
    const auto performance =
        has_operation ? performance_surface(name) : std::nullopt;
    const auto soundset =
        has_operation ? soundset_surface(name) : std::nullopt;
    const bool query_operation =
        name == "sample.quota" || name == "status" ||
        (performance.has_value() && *performance == FacadeSurface::query) ||
        (soundset.has_value() && *soundset == FacadeSurface::query);
    if (!has_operation || query_operation) {
      service_runtime_once();
    } else {
      auto serviced = service_command_boundary();
      if (!serviced.has_value()) {
        return error_response(serviced.error());
      }
    }
    if (trigger_outcome_failed()) {
      return trigger_outcome_failure_response();
    }
    auto response = [&]() -> Json {
      if (!has_operation) {
        return invalid_request("operation must be a string");
      }
      if (name == "sample.quota") {
        return sample_quota(request);
      }
      if (performance.has_value()) {
        return performance_operation(request, *performance);
      }
      if (soundset.has_value()) {
        return soundset_operation(request, *soundset);
      }
      if (name == "trigger") {
        return trigger(request);
      }
      if (name == "snapshot.reload") {
        return reload_snapshot(request);
      }
      if (name == "record.begin") {
        return record_begin(request);
      }
      if (name == "record.stop") {
        return record_stop(request);
      }
      if (name == "status") {
        return status(request);
      }
      if (name == "stop") {
        return stop(request);
      }
      if (name == "start") {
        return start(request);
      }
      if (name == "quit") {
        return quit(request);
      }
      return invalid_request("unknown Native Host operation");
    }();
    service_runtime_once();
    if (trigger_outcome_failed()) {
      return trigger_outcome_failure_response();
    }
    return response;
  }

  bool quitting() const noexcept { return quitting_; }

  void service_control_tick() {
    drive_no_device_once();
    service_periodic_control_tick();
  }

  bool terminal_audio_failure() const noexcept {
#if defined(__APPLE__)
    return trigger_outcome_failed() ||
           (output_ != nullptr &&
            output_->state() == lmdj::audio::apple::CoreAudioState::failed);
#else
    return trigger_outcome_failed();
#endif
  }

 private:
  Json performance_operation(
      const Json& request,
      FacadeSurface surface) {
    const auto project = request.find("project_path");
    if (project != request.end() &&
        (!project->is_string() ||
         project->get<std::string>() != invocation_.project.generic_string())) {
      return invalid_request(
          "Performance operation must target the Native Host Project");
    }
    std::lock_guard lock(facade_mutex_);
    return surface == FacadeSurface::command
               ? application_.command(request)
               : application_.query(request);
  }

  // Workspace-level Sound Set operations carry no `project_path` at all, and
  // the Project-scoped two must name this Host's Project, so the check is the
  // presence-conditional one rather than a required field.
  Json soundset_operation(const Json& request, FacadeSurface surface) {
    const auto project = request.find("project_path");
    if (project != request.end() &&
        (!project->is_string() ||
         project->get<std::string>() != invocation_.project.generic_string())) {
      return invalid_request(
          "Sound Set operation must target the Native Host Project");
    }
    bool played = false;
    Json response;
    {
      std::lock_guard lock(facade_mutex_);
      response = surface == FacadeSurface::command
                     ? application_.command(request)
                     : application_.query(request);
      // #799. The Facade has answered with the geometry; this Host owns an
      // engine, so it also plays the bytes. A stopped Host is a normal state
      // rather than a refusal, so `running_` gates the playback and never the
      // answer.
      //
      // #1059 established `played` on the other engine-owning Host: without it
      // "it played" and "it silently did not" are the same reply, and the
      // branch a caller actually meets is a Host that has published a snapshot
      // and never started its backend, where `enqueue_control` refuses every
      // audition. This carries that field with the same meaning -- a voice was
      // admitted -- and never a reason for `false`, because a reason
      // vocabulary here is what Stage 11 froze. It is a Host field on the
      // result, not a Facade one: `soundset.audition` through the CLI or
      // core-mcp carries no `played`, because neither owns an engine to answer
      // for.
      //
      // `find` rather than `operator[]`: on a non-const `Json` the subscript
      // inserts a null member for a missing key, so probing `result` that way
      // would edit the envelope it is only supposed to read.
      const auto result = response.find("result");
      if (response.value("ok", false) && result != response.end() &&
          result->is_object() &&
          request.at("operation").get<std::string>() == "soundset.audition") {
        played = running_ && play_audition_locked(request);
        (*result)["played"] = played;
      }
    }
    if (played) {
      // The deterministic backend has no clock of its own: nothing renders
      // until this Host drives it, which is why `trigger` drains here too. In
      // device mode this returns immediately and the audio callback owns the
      // voice.
      drain_no_device_trigger();
    }
    return response;
  }

  // #799. Publish the audition PCM the Facade decoded into the engine's
  // reserved audition pool and start a voice on it.
  //
  // There is deliberately no native `soundset.audition.stop`. The Web Host has
  // one because a browsing user interrupts a preview mid-playback; this Host
  // is driven line by line over stdio, its auditions are `one_shot`, a second
  // audition supersedes the first through the pool's replace semantics, and
  // the deterministic backend has already rendered the preview to completion
  // by the time the response is written. Adding one would mean a Host-owned
  // operation outside `kSoundSetOperations` -- that table maps names to a
  // `FacadeSurface`, and the Facade serves no stop, so an entry there would
  // silently reach `dispatch()`'s `attempt_inspect` fallthrough. That is a new
  // operation on this Host's surface, which the byte-path plan settled the
  // other way for three Host tables and did not anticipate for this one; it
  // belongs to #799 as a follow-up, not to this Task.
  //
  // `audition_soundset` is the typed Facade method the Web Host's
  // `play_audition` also calls: the Facade resolves the Set, applies S11-D3's
  // whole-Set audio decision and the locked refusal order, decodes and
  // resamples, and hands back prepared PCM. This Host never reads the Set
  // Store -- the relationship `sample.preview.set` already has with
  // `inspect_sample` -- which is what keeps audition inside "Hosts use only
  // the Application Facade".
  //
  // Not an error by design, exactly as in `control_runtime.cpp`: the metadata
  // answer the caller is about to receive is already correct, and reporting a
  // playback failure as a refusal would need error vocabulary Stage 11 has
  // frozen. Returns whether a voice was actually admitted, which the caller
  // reports as `played` rather than discarding.
  //
  // Called with `facade_mutex_` held.
  [[nodiscard]] bool play_audition_locked(const Json& request) {
    // The three identity fields are strings whenever the Facade answered `ok`:
    // `soundset_audition` admits only the two exact key sets and type-checks
    // each field before it resolves anything.
    lmdj::facade::SoundSetAuditionRequest audition{
        request.at("set_id").get<std::string>(),
        request.at("version").get<std::string>(),
        request.at("manifest_sha256").get<std::string>(),
        std::nullopt,
    };
    if (request.contains("slot_index")) {
      audition.slot_index = static_cast<std::uint8_t>(
          request.at("slot_index").get<std::uint64_t>());
    }
    const auto audio = application_.audition_soundset(audition);
    if (!audio.has_value()) {
      // The Facade already refused this request through the envelope the
      // caller is about to receive; there is nothing further to report.
      return false;
    }
    const auto& source = *audio.value().prepared;
    if (source.channels == 0 || source.interleaved.empty() ||
        source.interleaved.size() % source.channels != 0) {
      return false;
    }
    const auto frames = source.interleaved.size() / source.channels;
    if (frames > std::numeric_limits<std::uint32_t>::max()) {
      return false;
    }
    // Down-mix to the mono float a Bank stores through the same public helper
    // `PreparedSampleBank::from_snapshot` uses for a Project Pad, so an
    // audition and a Pad cannot disagree about what stereo means.
    const lmdj::audio::PreparedSampleMaterialView material{
        source.interleaved.data(),
        static_cast<std::uint32_t>(frames),
        source.channels,
    };
    std::vector<float> mono;
    mono.reserve(frames);
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      mono.push_back(lmdj::audio::prepared_material_sample(material, frame));
    }
    auto bank = PreparedSampleBank::empty(
        lmdj::audio::kAuditionBankProjectId(),
        lmdj::audio::kAuditionBankProjectRevision);
    if (!bank.set_sample(lmdj::audio::kAuditionSampleSlot, mono).has_value()) {
      return false;
    }
    if (engine_.publish_audition_bank(std::move(bank)) !=
        PublishResult::accepted) {
      // Both reserved audition slots are still draining an earlier preview.
      // Dropping this one is the honest outcome: the alternative is
      // overwriting bytes a voice is still reading, which is the defect the
      // two-slot pool exists to avoid. Retiring from here instead is not an
      // option -- publication primes an `empty` slot and the audio thread
      // applies and retires inside `render`, which is what serialises
      // retirement against voice starts.
      return false;
    }
    return engine_.enqueue_control(lmdj::audio::PadControlEvent{
               0,
               0,
               127,
               lmdj::audio::PadControlKind::audition_start,
               {},
           }) == EnqueueResult::accepted;
  }

  Json sample_quota(const Json& request) {
    if (!exact_keys(request, {"operation", "project_path", "slot"}) ||
        !request.at("project_path").is_string() ||
        request.at("project_path").get<std::string>() !=
            invocation_.project.generic_string()) {
      return invalid_request(
          "sample.quota must target the Native Host Project");
    }
    std::lock_guard lock(facade_mutex_);
    return application_.query(request);
  }

  void service_runtime_locked() {
    performance_adapter_.service();
    std::array<RuntimeTriggerOutcomeEvent, 64> outcomes{};
    (void)engine_.drain_trigger_outcomes(outcomes);
  }

  Result<void> service_application_locked() {
    auto serviced = application_.service_performance();
    if (serviced.has_value()) {
      performance_service_error_.reset();
      return Result<void>::success();
    }
    if (!performance_service_error_.has_value()) {
      performance_service_error_ = serviced.error();
    }
    return Result<void>::failure(*performance_service_error_);
  }

  Result<void> service_command_boundary() {
    std::lock_guard lock(facade_mutex_);
    service_runtime_locked();
    return service_application_locked();
  }

  void service_periodic_control_tick() {
    std::lock_guard lock(facade_mutex_);
    service_runtime_locked();
    static_cast<void>(service_application_locked());
  }

  void service_runtime_once() {
    std::lock_guard lock(facade_mutex_);
    service_runtime_locked();
  }

  bool trigger_outcome_failed() const noexcept {
    return engine_.trigger_outcome_telemetry().runtime_outcome_drops != 0;
  }

  Json trigger_outcome_failure_response() const {
    return error_response(
        "INTERNAL_ERROR", "Realtime Trigger outcome ring dropped events");
  }

  Result<std::shared_ptr<const lmdj::cooker::RuntimeSnapshot>>
  prepare_snapshot(const PatternId& pattern_id) {
    std::lock_guard lock(facade_mutex_);
    return application_.prepare_runtime_snapshot(
        lmdj::facade::RuntimeSnapshotRequest{
            invocation_.project,
            pattern_id,
        });
  }

  Result<void> start_backend() {
    std::lock_guard lock(facade_mutex_);
    if (running_) {
      return host_failure(
          ErrorCode::invalid_argument, "Native Host is already running");
    }
    Result<void> started = host_failure(
        ErrorCode::unsupported_audio,
        "real-time device output is unsupported on this platform");
    if (invocation_.no_device) {
      started = engine_.start();
#if defined(__APPLE__)
    } else {
      started = output_->start();
#endif
    }
    if (started.has_value()) {
      running_ = true;
    }
    return started;
  }

  Result<void> stop_backend() {
    std::lock_guard lock(facade_mutex_);
    if (!running_) {
      return Result<void>::success();
    }
    Result<void> stopped = Result<void>::success();
    if (invocation_.no_device) {
      engine_.stop();
#if defined(__APPLE__)
    } else {
      stopped = output_->stop();
#endif
    }
    if (stopped.has_value()) {
      running_ = false;
    }
    return stopped;
  }

  void drive_no_device_once() {
    if (!invocation_.no_device || !running_) {
      return;
    }
    std::array<float, kNoDeviceRenderFrames> left{};
    std::array<float, kNoDeviceRenderFrames> right{};
    engine_.render(left.data(), right.data(), kNoDeviceRenderFrames);
  }

  void drain_no_device_trigger() {
    if (!invocation_.no_device) {
      return;
    }
    do {
      drive_no_device_once();
      const auto telemetry = engine_.telemetry();
      if (telemetry.queued_events == 0 && telemetry.active_voices == 0) {
        return;
      }
    } while (true);
  }

  bool wait_for_capture(CaptureState first, CaptureState second) {
    const auto deadline = std::chrono::steady_clock::now() + kControlDeadline;
    while (std::chrono::steady_clock::now() < deadline) {
      const auto state = engine_.capture_telemetry().state;
      if (state == first || state == second) {
        return true;
      }
      if (invocation_.no_device) {
        drive_no_device_once();
      } else {
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
      }
    }
    return false;
  }

  Json trigger(const Json& request) {
    if (!exact_keys(request, {"operation", "slot", "velocity"})) {
      return invalid_request("trigger request shape is invalid");
    }
    if (!running_) {
      return invalid_request("Native Host is stopped");
    }
    if (active_session_.has_value() &&
        engine_.capture_telemetry().state != CaptureState::active) {
      return invalid_request("recording Capture is not active");
    }
    const auto slot = request.find("slot");
    const auto velocity = unsigned_value(request, "velocity");
    if (slot == request.end() ||
        !exact_keys(*slot, {"bank", "pad"}) ||
        !velocity.has_value() || *velocity == 0 || *velocity > 127) {
      return invalid_request("trigger slot or velocity is invalid");
    }
    const auto bank = unsigned_value(*slot, "bank");
    const auto pad = unsigned_value(*slot, "pad");
    if (!bank.has_value() || !pad.has_value() || *bank > 3 || *pad > 15) {
      return invalid_request("trigger slot is out of range");
    }
    const auto global_slot =
        static_cast<std::uint8_t>(*bank * 16U + *pad);
    const auto sequence = next_sequence_++;
    const auto result = [&] {
      std::lock_guard lock(facade_mutex_);
      return engine_.enqueue(lmdj::audio::TriggerEvent{
          sequence,
          global_slot,
          static_cast<std::uint8_t>(*velocity),
      });
    }();
    if (result != EnqueueResult::accepted) {
      return error_response(
          result == EnqueueResult::sample_unavailable
              ? "NOT_FOUND"
              : "INVALID_ARGUMENT",
          "realtime Trigger was rejected",
          {{"result", static_cast<std::uint8_t>(result)}});
    }
    drain_no_device_trigger();
    return success_response(
        "trigger",
        {{"sequence", sequence}, {"status", "accepted"}});
  }

  Json reload_snapshot(const Json& request) {
    if (!exact_keys(request, {"operation", "pattern_id"})) {
      return invalid_request("snapshot.reload request shape is invalid");
    }
    const auto pattern = uuid_value(request, "pattern_id");
    if (!pattern.has_value()) {
      return invalid_request("snapshot.reload pattern_id is invalid");
    }
    const PatternId pattern_id{*pattern};
    auto prepared = prepare_snapshot(pattern_id);
    if (!prepared.has_value()) {
      return error_response(prepared.error());
    }
    auto bank = PreparedSampleBank::from_snapshot(*prepared.value());
    if (!bank.has_value()) {
      return error_response(bank.error());
    }

    const auto deadline = std::chrono::steady_clock::now() + kControlDeadline;
    PublishResult published = PublishResult::events_pending;
    while (std::chrono::steady_clock::now() < deadline) {
      {
        std::lock_guard lock(facade_mutex_);
        (void)engine_.reclaim_retired_banks();
        published = engine_.publish_sample_bank(std::move(bank.value()));
      }
      if (published == PublishResult::accepted) {
        break;
      }
      if (published != PublishResult::events_pending &&
          published != PublishResult::bank_slots_full) {
        break;
      }
      if (invocation_.no_device && running_) {
        drive_no_device_once();
      } else {
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
      }
    }
    if (published != PublishResult::accepted) {
      return error_response(
          "IO_ERROR",
          "Sample Bank publication failed; previous Bank remains current");
    }
    while (engine_.bank_telemetry().pending_publications != 0 &&
           std::chrono::steady_clock::now() < deadline) {
      if (invocation_.no_device) {
        drive_no_device_once();
      } else {
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
      }
    }
    if (engine_.bank_telemetry().pending_publications != 0) {
      return error_response(
          "IO_ERROR", "Sample Bank callback publication timed out");
    }
    snapshot_ = prepared.value();
    pattern_id_ = pattern_id;
    return success_response(
        "snapshot.reload",
        {
            {"pattern_id", pattern_id.value()},
            {"project_revision", snapshot_->project_revision},
            {"resolved_pad_count", snapshot_->pads.size()},
        });
  }

  Json record_begin(const Json& request) {
    if (!exact_keys(
            request,
            {"operation", "session_id", "expected_revision"})) {
      return invalid_request("record.begin request shape is invalid");
    }
    if (!running_ || active_session_.has_value() || writer_ != nullptr) {
      return invalid_request("Native Host cannot begin a recording now");
    }
    const auto session = uuid_value(request, "session_id");
    const auto revision = unsigned_value(request, "expected_revision");
    if (!session.has_value() || !revision.has_value()) {
      return invalid_request("record.begin identity is invalid");
    }

    Json begun;
    {
      std::lock_guard lock(facade_mutex_);
      const auto result = application_.begin_sequence({
          invocation_.project,
          SequenceSessionId{*session},
          pattern_id_,
          *revision,
          engine_.telemetry().rendered_frames,
      });
      begun = result.has_value()
                  ? success_response(
                        "sequence.record.begin",
                        {{"session_id", *session},
                         {"expected_revision", *revision}})
                  : error_response(result.error());
    }
    if (!response_ok(begun)) {
      return begun;
    }

    const SequenceSessionId session_id{*session};
    try {
      writer_ = std::make_unique<CaptureWriter>(
          engine_, application_, facade_mutex_, invocation_.project, session_id);
      writer_->start();
    } catch (...) {
      writer_.reset();
      return error_response(
          "INTERNAL_ERROR", "Capture Writer failed to start");
    }
    capture_baseline_ = engine_.capture_telemetry().captured_events;
    const auto armed = [&] {
      std::lock_guard lock(facade_mutex_);
      return engine_.arm_capture();
    }();
    const auto reached_capture_state =
        armed.has_value() &&
        wait_for_capture(CaptureState::active, CaptureState::corrupted);
    const auto capture_state = engine_.capture_telemetry().state;
    if (!reached_capture_state || capture_state != CaptureState::active) {
      if (capture_state == CaptureState::active) {
        std::lock_guard lock(facade_mutex_);
        (void)engine_.disarm_capture();
      }
      const auto pending_state = engine_.capture_telemetry().state;
      if (pending_state != CaptureState::idle &&
          pending_state != CaptureState::corrupted) {
        (void)stop_backend();
      }
      writer_->request_stop();
      writer_->join();
      writer_.reset();
      return error_response("IO_ERROR", "Capture arm timed out");
    }
    active_session_ = session_id;
    return success_response(
        "record.begin",
        {
            {"session_id", *session},
            {"expected_revision", *revision},
        });
  }

  Json finish_recording(std::optional<CommandId> stop_command) {
    if (!active_session_.has_value() || writer_ == nullptr) {
      return invalid_request("no recording is active");
    }
    const auto session_id = *active_session_;
    const auto disarmed = [&] {
      std::lock_guard lock(facade_mutex_);
      return engine_.disarm_capture();
    }();
    const auto reached_terminal =
        disarmed.has_value() &&
        wait_for_capture(CaptureState::idle, CaptureState::corrupted);
    writer_->request_stop();
    if (!reached_terminal) {
      (void)stop_backend();
    }
    writer_->join();

    const auto capture = engine_.capture_telemetry();
    const auto captured = capture.captured_events - capture_baseline_;
    const auto persisted = writer_->persisted_events();
    const auto failures = writer_->failure_count();
    last_persisted_events_ = persisted;
    last_writer_failures_ = failures;

    std::array<lmdj::audio::CapturedTriggerEvent, 64> discarded{};
    while (engine_.drain_capture(discarded) != 0) {
    }
    bool clean =
        stop_command.has_value() && reached_terminal &&
        capture.state == CaptureState::idle && failures == 0 &&
        persisted == captured;
    std::optional<std::uint64_t> committed_revision;
    if (clean) {
      std::lock_guard lock(facade_mutex_);
      const auto stopped = application_.stop_sequence({
          invocation_.project,
          session_id,
          *stop_command,
          engine_.telemetry().rendered_frames,
      });
      if (!stopped.has_value()) {
        active_session_.reset();
        writer_.reset();
        return error_response(stopped.error());
      }
      committed_revision = stopped.value().committed_revision;
    }

    active_session_.reset();
    writer_.reset();
    return success_response(
        "record.stop",
        {
            {"session_id", session_id.value()},
            {"captured_events", captured},
            {"persisted_events", persisted},
            {"writer_failures", failures},
            {"clean", clean},
            {"committed_revision",
             committed_revision.has_value()
                 ? Json(*committed_revision)
                 : Json(nullptr)},
        });
  }

  Json record_stop(const Json& request) {
    if (!exact_keys(request, {"operation", "command_id"})) {
      return invalid_request("record.stop request shape is invalid");
    }
    const auto command = uuid_value(request, "command_id");
    if (!command.has_value()) {
      return invalid_request("record.stop command id is invalid");
    }
    return finish_recording(CommandId{*command});
  }

  Json status(const Json& request) const {
    if (!exact_keys(request, {"operation"})) {
      return invalid_request("status request shape is invalid");
    }
    const auto realtime = engine_.telemetry();
    const auto bank = engine_.bank_telemetry();
    const auto capture = engine_.capture_telemetry();
    const auto writer_persisted =
        writer_ != nullptr ? writer_->persisted_events() : last_persisted_events_;
    const auto writer_failures =
        writer_ != nullptr ? writer_->failure_count() : last_writer_failures_;
    Json coreaudio = {
        {"callback_failures", 0},
        {"deadline_overruns", 0},
        {"device_overloads", 0},
    };
#if defined(__APPLE__)
    if (output_ != nullptr) {
      const auto telemetry = output_->telemetry();
      coreaudio = {
          {"callback_failures", telemetry.callback_failures},
          {"deadline_overruns", telemetry.deadline_overruns},
          {"device_overloads", telemetry.device_overloads},
      };
    }
#endif
    return success_response(
        "status",
        {
            {"host",
             {
                 {"backend",
                  invocation_.no_device ? "deterministic" : "coreaudio"},
                 {"host_version", kHostVersion},
                 {"product_build", kProductBuild},
                 {"state", running_ ? "running" : "stopped"},
             }},
            {"snapshot",
             {
                 {"pattern_id", pattern_id_.value()},
                 {"project_id", snapshot_->project_id.value()},
                 {"project_revision", snapshot_->project_revision},
                 {"resolved_pad_count", snapshot_->pads.size()},
             }},
            {"bank",
             {
                 {"accepted_publications", bank.accepted_publications},
                 {"applied_publications", bank.applied_publications},
                 {"bank_slot_rejections", bank.bank_slot_rejections},
                 {"current_generation", bank.current_generation},
                 {"pending_publications", bank.pending_publications},
                 {"publish_queue_drops", bank.publish_queue_drops},
                 {"reclaimed_banks", bank.reclaimed_banks},
             }},
            {"engine",
             {
                 {"active_voices", realtime.active_voices},
                 {"callback_count", realtime.callback_count},
                 {"cancelled_events", realtime.cancelled_events},
                 {"cancelled_voices", realtime.cancelled_voices},
                 {"completed_voices", realtime.completed_voices},
                 {"dequeued_events", realtime.dequeued_events},
                 {"enqueued_events", realtime.enqueued_events},
                 {"queue_drops", realtime.queue_drops},
                 {"queued_events", realtime.queued_events},
                 {"rendered_frames", realtime.rendered_frames},
                 {"started_voices", realtime.started_voices},
                 {"voice_drops", realtime.voice_drops},
             }},
            {"capture",
             {
                 {"captured_events", capture.captured_events},
                 {"capture_drops", capture.capture_drops},
                 {"capture_origin_frame", capture.capture_origin_frame},
                 {"drained_events", capture.drained_events},
                 {"persisted_events", writer_persisted},
                 {"state", capture_state_name(capture.state)},
                 {"writer_failures", writer_failures},
             }},
            {"coreaudio", std::move(coreaudio)},
            {"active_session_id",
             active_session_.has_value()
                 ? Json(active_session_->value())
                 : Json(nullptr)},
        });
  }

  Json stop(const Json& request) {
    if (!exact_keys(request, {"operation"})) {
      return invalid_request("stop request shape is invalid");
    }
    if (active_session_.has_value()) {
      const auto stopped_recording = finish_recording(std::nullopt);
      if (!response_ok(stopped_recording)) {
        return stopped_recording;
      }
    }
    const auto stopped = stop_backend();
    if (!stopped.has_value()) {
      return error_response(stopped.error());
    }
    return success_response("stop", {{"state", "stopped"}});
  }

  Json start(const Json& request) {
    if (!exact_keys(request, {"operation"})) {
      return invalid_request("start request shape is invalid");
    }
    if (active_session_.has_value()) {
      return invalid_request("cannot start while a recording is active");
    }
    const auto started = start_backend();
    if (!started.has_value()) {
      return error_response(started.error());
    }
    return success_response("start", {{"state", "running"}});
  }

  Json quit(const Json& request) {
    if (!exact_keys(request, {"operation"})) {
      return invalid_request("quit request shape is invalid");
    }
    if (active_session_.has_value()) {
      const auto stopped_recording = finish_recording(std::nullopt);
      if (!response_ok(stopped_recording)) {
        return stopped_recording;
      }
    }
    const auto stopped = stop_backend();
    if (!stopped.has_value()) {
      return error_response(stopped.error());
    }
    quitting_ = true;
    return success_response("quit", {{"state", "stopped"}});
  }

  Invocation invocation_;
  RealtimeEngine engine_;
  lmdj::facade::EnginePerformanceAdapter performance_adapter_;
  lmdj::facade::LocalSoundSetCatalog catalog_;
  Application application_;
  std::mutex facade_mutex_;
  std::optional<Error> performance_service_error_;
  std::shared_ptr<const lmdj::cooker::RuntimeSnapshot> snapshot_;
  PatternId pattern_id_{"00000000-0000-4000-8000-000000000000"};
#if defined(__APPLE__)
  std::unique_ptr<lmdj::audio::apple::CoreAudioOutput> output_;
#endif
  std::unique_ptr<CaptureWriter> writer_;
  std::optional<SequenceSessionId> active_session_;
  std::uint64_t capture_baseline_ = 0;
  std::uint64_t last_persisted_events_ = 0;
  std::uint64_t last_writer_failures_ = 0;
  std::uint64_t next_sequence_ = 1;
  bool running_ = false;
  bool quitting_ = false;
};

int write_fallback() noexcept {
  const auto written = std::fwrite(
      kInternalErrorFallback.data(),
      1,
      kInternalErrorFallback.size(),
      stdout);
  if (written != kInternalErrorFallback.size() ||
      std::fflush(stdout) != 0) {
    return 2;
  }
  return 2;
}

int run(const RawInvocation& raw) {
  auto invocation = validate_invocation(raw);
  if (!invocation.has_value()) {
    (void)write_response(error_response(invocation.error()));
    return 2;
  }
  auto assembly =
      lmdj::facade::load_installed_assembly(invocation.value().assembly);
  if (!assembly.has_value()) {
    (void)write_response(error_response(assembly.error()));
    return 2;
  }
  NativeHost host(
      std::move(invocation.value()),
      std::move(assembly.value().providers),
      std::move(assembly.value().provider_policy));
  const auto started = host.startup();
  if (!started.has_value()) {
    (void)write_response(error_response(started.error()));
    if (host.terminal_audio_failure()) {
      std::_Exit(2);
    }
    return 2;
  }
  if (!write_response(host.ready_response())) {
    return 2;
  }

  ControlTicker control_ticker([&host] { host.service_control_tick(); });
  while (!host.quitting()) {
    const auto line = read_line(control_ticker);
    Json response;
    if (line.status == LineStatus::too_large) {
      response = invalid_request("command exceeds the 65536 byte limit");
    } else if (line.status == LineStatus::end) {
      response = host.handle({{"operation", "quit"}});
    } else {
      const auto request = parse_bounded_json(line.bytes);
      response = request.has_value()
                     ? host.handle(*request)
                     : invalid_request(
                           "command must be a UTF-8 JSON object with depth at most 32");
    }
    if (!write_response(response)) {
      return 2;
    }
    if (host.terminal_audio_failure()) {
      std::_Exit(2);
    }
  }
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
#if defined(SIGPIPE)
  (void)std::signal(SIGPIPE, SIG_IGN);
#endif
  const auto invocation = parse_raw_invocation(argc, argv);
  if (!invocation.has_value()) {
    const auto written =
        std::fwrite(kUsage.data(), 1, kUsage.size(), stderr);
    if (written != kUsage.size()) {
      return 64;
    }
    return 64;
  }
  try {
    return run(*invocation);
  } catch (...) {
    try {
      (void)write_response(
          error_response("INTERNAL_ERROR", "unexpected Native Host failure"));
      return 2;
    } catch (...) {
      return write_fallback();
    }
  }
}
