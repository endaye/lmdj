#include <lmdj/web_runtime/control_runtime.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/provider/registry.hpp>

#include "tests/core/support/test.hpp"

namespace {

using Json = nlohmann::json;
using lmdj::audio::RuntimePreparationLimits;
using lmdj::facade::ApplicationConfig;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;
using lmdj::project_io::SequenceJournal;
using lmdj::web_runtime::ControlRuntime;
using lmdj::web_runtime::detail::BridgeHooks;
using lmdj::web_runtime::detail::BridgePollStatus;
using lmdj::web_runtime::detail::BridgeSubmitStatus;
using lmdj::web_runtime::detail::ControlBridge;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kPatternId =
    "00000000-0000-4000-8000-000000000010";
constexpr std::string_view kSessionId =
    "00000000-0000-4000-8000-000000000020";
constexpr std::string_view kPerformanceId =
    "00000000-0000-4000-8000-000000000030";
constexpr std::string_view kReplayId =
    "00000000-0000-4000-8000-000000000031";

constexpr RuntimePreparationLimits kLimits{
    1'048'576,
    240'000,
    67'108'864,
    134'217'728,
};

class TempDirectory final {
 public:
  TempDirectory() {
    static std::atomic<std::uint64_t> sequence{0};
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
        ("lmdj-web-performance-bridge-" + std::to_string(nonce) + "-" +
         std::to_string(sequence.fetch_add(1)));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  const std::filesystem::path& path() const noexcept { return path_; }

 private:
  std::filesystem::path path_;
};

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" +
      std::string(12 - tail.size(), '0') + tail;
}

ApplicationConfig config(const std::filesystem::path& root) {
  return ApplicationConfig{
      root,
      std::make_shared<Registry>(),
      ProviderPolicy{},
      [] { return std::string("2026-09-03T00:00:00.000Z"); },
      kLimits,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
}

Json require_success(
    Json response, std::string_view context = "unspecified operation") {
  LMDJ_CHECK(response.is_object());
  if (!response.value("ok", false)) {
    throw std::runtime_error(
        "unexpected Host failure in " + std::string(context) + ": " +
        response.dump());
  }
  LMDJ_CHECK(response.contains("result"));
  return response.at("result");
}

std::string source_file(std::string_view relative_path) {
  std::ifstream input(
      std::filesystem::path{LMDJ_SOURCE_DIR} / relative_path,
      std::ios::binary);
  LMDJ_CHECK(input.good());
  return {std::istreambuf_iterator<char>(input),
          std::istreambuf_iterator<char>()};
}

void test_web_audio_bridge_carries_one_opaque_destination_and_direct_fallback() {
  const auto header = source_file(
      "packages/audio-runtime/include/lmdj/audio/web/"
      "realtime_audio_worklet.hpp");
  const auto implementation = source_file(
      "packages/audio-runtime/src/web/realtime_audio_worklet.cpp");
  const auto bridge = source_file(
      "packages/web-runtime-platform/src/bridge.cpp");
  const auto pre_js = source_file(
      "packages/web-runtime-platform/src/web-runtime-pre.js");

  const auto has = [](const std::string& source, std::string_view token) {
    return source.find(token) != std::string::npos;
  };
  LMDJ_CHECK(has(header, "std::int32_t output_destination_handle"));
  LMDJ_CHECK(has(header, "connect_direct_output_on_browser_main"));
  LMDJ_CHECK(has(
      implementation,
      "node, self.output_destination_handle, 0, 0"));
  LMDJ_CHECK(has(bridge, "lmdj_web_audio_connect_direct"));
  LMDJ_CHECK(has(pre_js, "function registerAudioNode(node)"));
  LMDJ_CHECK(has(pre_js, "function startAudioWorklet("));
  LMDJ_CHECK(has(pre_js, "outputDestinationHandle"));
  LMDJ_CHECK(has(pre_js, "function connectAudioWorkletDirect("));
}

void render_frames(ControlRuntime& runtime, std::uint64_t frames) {
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  while (frames != 0) {
    const auto count = static_cast<std::uint32_t>(
        std::min<std::uint64_t>(frames, left.size()));
    runtime.engine().render(left.data(), right.data(), count);
    frames -= count;
  }
}

void render_through_tick(ControlRuntime& runtime, std::uint64_t tick) {
  constexpr std::uint64_t kFramesPerTickAt120Bpm = 25;
  const auto target_frame = tick * kFramesPerTickAt120Bpm;
  const auto rendered = runtime.engine().telemetry().rendered_frames;
  render_frames(
      runtime,
      target_frame > rendered ? target_frame - rendered + 128 : 128);
}

void service_periodic(ControlBridge& bridge) {
  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(bridge.poll(output, required) == BridgePollStatus::empty);
}

struct ImmediateControl final {
  static bool schedule(
      void*, void (*function)(void*) noexcept, void* argument) noexcept {
    function(argument);
    return true;
  }

  static bool on_control(void*) noexcept { return true; }
};

Json bridge_request(
    ControlBridge& bridge,
    std::string_view operation,
    const Json& payload,
    std::uint32_t request_suffix) {
  const auto encoded = Json{
      {"protocol_version", 1},
      {"request_id", uuid(request_suffix)},
      {"operation", operation},
      {"payload", payload},
  }.dump();
  const auto bytes = std::span<const std::byte>(
      reinterpret_cast<const std::byte*>(encoded.data()), encoded.size());
  LMDJ_CHECK(bridge.submit(bytes, {}) == BridgeSubmitStatus::accepted);
  std::array<std::byte, 65'536> output{};
  std::size_t required = 0;
  LMDJ_CHECK(bridge.poll(output, required) == BridgePollStatus::message);
  return Json::parse(
      reinterpret_cast<const char*>(output.data()),
      reinterpret_cast<const char*>(output.data() + required));
}

void test_constructs_application_with_engine_authorities_and_services_launches() {
  TempDirectory temporary;
  auto created = ControlRuntime::create(
      temporary.path(), config(temporary.path()), kLimits);
  LMDJ_CHECK(created.has_value());
  auto runtime = std::move(created.value());

  require_success(runtime->dispatch(
      "project.create",
      {
          {"project_id", kProjectId},
          {"bpm", 120},
          {"initial_pattern",
           {{"pattern_id", kPatternId}, {"bars", 1}, {"events", Json::array()}}},
      },
      {}));
  require_success(runtime->dispatch(
      "pattern.slot.assign",
      {
          {"command_id", uuid(1)},
          {"expected_revision", 0},
          {"pattern_slot", 1},
          {"pattern_id", kPatternId},
      },
      {}));
  require_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  LMDJ_CHECK(runtime->engine().start().has_value());
  ControlBridge bridge(
      *runtime,
      BridgeHooks{
          nullptr,
          &ImmediateControl::schedule,
          &ImmediateControl::on_control,
          nullptr,
          nullptr,
          nullptr});
  LMDJ_CHECK(bridge_request(bridge, "host.status", Json::object(), 90)
                 .value("ok", false));

  require_success(runtime->dispatch(
      "performance.record.begin",
      {
          {"command_id", uuid(2)},
          {"expected_revision", 1},
          {"session_id", kSessionId},
          {"performance_id", kPerformanceId},
      },
      {}));
  const auto before = require_success(runtime->dispatch(
      "performance.record.status", Json::object(), {}));
  const auto repeated = require_success(runtime->dispatch(
      "performance.record.status", Json::object(), {}));
  LMDJ_CHECK(before == repeated);
  LMDJ_CHECK(before.at("last_launch_ack").is_null());

  const auto invalid_raw = runtime->dispatch(
      "performance.record.event",
      {
          {"session_id", kSessionId},
          {"event_id", uuid(40)},
          {"event", {{"kind", "hold_on"}}},
          {"runtime_frame", 1},
      },
      {});
  LMDJ_CHECK(!invalid_raw.value("ok", true));
  LMDJ_CHECK(
      invalid_raw.at("error").at("code") == "HOST_PROTOCOL_MISMATCH");
  const auto requested = require_success(runtime->dispatch(
      "performance.record.launch-request",
      {
          {"session_id", kSessionId},
          {"request_id", uuid(3)},
          {"pattern_slot", 1},
      },
      {}));
  const auto target_tick = requested.at("target_tick").get<std::uint64_t>();
  LMDJ_CHECK(target_tick != 0);
  render_through_tick(*runtime, target_tick);
  service_periodic(bridge);
  const auto durable_ack = SequenceJournal{}
      .read_active_performance(
          temporary.path() / "projects" /
          (std::string(kProjectId) + ".lmdj"));
  LMDJ_CHECK(durable_ack.has_value());
  LMDJ_CHECK(durable_ack.value().last_launch_ack.has_value());
  LMDJ_CHECK(
      durable_ack.value().last_launch_ack->request_id.value() == uuid(3));

  const auto acknowledged = require_success(runtime->dispatch(
      "performance.record.status", Json::object(), {}));
  LMDJ_CHECK(acknowledged.at("last_launch_ack").at("request_id") == uuid(3));
  LMDJ_CHECK(
      acknowledged.at("last_launch_ack").at("effective_tick") == target_tick);

  const auto replaced = require_success(runtime->dispatch(
      "performance.record.launch-request",
      {
          {"session_id", kSessionId},
          {"request_id", uuid(4)},
          {"pattern_slot", 1},
      },
      {}));
  const auto replacement = require_success(runtime->dispatch(
      "performance.record.launch-request",
      {
          {"session_id", kSessionId},
          {"request_id", uuid(5)},
          {"pattern_slot", 15},
      },
      {}));
  LMDJ_CHECK(replaced.at("target_tick") == replacement.at("target_tick"));
  render_through_tick(
      *runtime, replacement.at("target_tick").get<std::uint64_t>());
  service_periodic(bridge);
  const auto empty_ack = require_success(runtime->dispatch(
      "performance.record.status", Json::object(), {}));
  LMDJ_CHECK(empty_ack.at("last_launch_ack").at("request_id") == uuid(5));

  require_success(runtime->dispatch(
      "performance.record.flush",
      {{"session_id", kSessionId}, {"command_id", uuid(50)}},
      {}));
  auto inspected = require_success(runtime->dispatch(
      "performance.inspect", {{"performance_id", kPerformanceId}}, {}));
  auto launched_slots = std::vector<std::uint8_t>{};
  for (const auto& event : inspected.at("performance").at("events")) {
    if (event.at("kind") == "pattern_launch") {
      launched_slots.push_back(event.at("pattern_slot").get<std::uint8_t>());
    }
  }
  LMDJ_CHECK(launched_slots == std::vector<std::uint8_t>({1, 15}));

  const auto claimed = require_success(runtime->dispatch(
      "performance.record.launch-request",
      {
          {"session_id", kSessionId},
          {"request_id", uuid(6)},
          {"pattern_slot", 1},
      },
      {}));
  const auto claimed_tick = claimed.at("target_tick").get<std::uint64_t>();
  render_through_tick(*runtime, claimed_tick);
  const auto generation_after_claim =
      runtime->engine().pattern_telemetry().current_generation;
  const auto deferred = require_success(runtime->dispatch(
      "performance.record.launch-request",
      {
          {"session_id", kSessionId},
          {"request_id", uuid(7)},
          {"pattern_slot", 15},
      },
      {}));
  const auto deferred_tick = deferred.at("target_tick").get<std::uint64_t>();
  LMDJ_CHECK(deferred_tick > claimed_tick);
  const auto deferred_status = require_success(runtime->dispatch(
      "performance.record.status", Json::object(), {}));
  LMDJ_CHECK(deferred_status.at("last_launch_ack").at("request_id") == uuid(6));
  LMDJ_CHECK(deferred_status.at("pending_launch").at("request_id") == uuid(7));
  render_through_tick(*runtime, deferred_tick);
  service_periodic(bridge);
  LMDJ_CHECK(
      runtime->engine().pattern_telemetry().current_generation ==
      generation_after_claim);

  require_success(runtime->dispatch(
      "performance.record.flush",
      {{"session_id", kSessionId}, {"command_id", uuid(51)}},
      {}));
  inspected = require_success(runtime->dispatch(
      "performance.inspect", {{"performance_id", kPerformanceId}}, {}));
  launched_slots.clear();
  for (const auto& event : inspected.at("performance").at("events")) {
    if (event.at("kind") == "pattern_launch") {
      launched_slots.push_back(event.at("pattern_slot").get<std::uint8_t>());
    }
  }
  LMDJ_CHECK(
      launched_slots == std::vector<std::uint8_t>({1, 15, 1, 15}));

  require_success(runtime->dispatch(
      "__testing.fail-next-pattern-publication", Json::object(), {}));
  const auto failed_launch = runtime->dispatch(
      "performance.record.launch-request",
      {
          {"session_id", kSessionId},
          {"request_id", uuid(8)},
          {"pattern_slot", 1},
      },
      {});
  LMDJ_CHECK(!failed_launch.value("ok", true));
  service_periodic(bridge);
  inspected = require_success(runtime->dispatch(
      "performance.inspect", {{"performance_id", kPerformanceId}}, {}));
  launched_slots.clear();
  for (const auto& event : inspected.at("performance").at("events")) {
    if (event.at("kind") == "pattern_launch") {
      launched_slots.push_back(event.at("pattern_slot").get<std::uint8_t>());
    }
  }
  LMDJ_CHECK(
      launched_slots == std::vector<std::uint8_t>({1, 15, 1, 15}));

  const auto replay_publications_before =
      runtime->engine().pattern_telemetry().accepted_publications;
  const auto replay_begin = require_success(runtime->dispatch(
      "performance.replay.begin",
      {{"replay_id", kReplayId}, {"performance_id", kPerformanceId}},
      {}), "performance.replay.begin");
  LMDJ_CHECK(replay_begin.at("event_cursor") == 0);
  render_frames(*runtime, 128);
  service_periodic(bridge);
  LMDJ_CHECK(
      runtime->engine().pattern_telemetry().accepted_publications >
      replay_publications_before);
  const auto replay_progress = require_success(runtime->dispatch(
      "performance.replay.status", {{"replay_id", kReplayId}}, {}),
      "performance.replay.status after periodic service");
  LMDJ_CHECK(replay_progress.at("event_cursor").get<std::uint64_t>() > 0);
  const auto replay_repeated = require_success(runtime->dispatch(
      "performance.replay.status", {{"replay_id", kReplayId}}, {}),
      "performance.replay.status repeated without render");
  LMDJ_CHECK(replay_repeated == replay_progress);
  runtime->engine().stop();
}

void test_rejects_invalid_values_at_the_cpp_host_boundary() {
  TempDirectory temporary;
  auto created = ControlRuntime::create(
      temporary.path(), config(temporary.path()), kLimits);
  LMDJ_CHECK(created.has_value());
  auto runtime = std::move(created.value());

  const auto artifact = Json{
      {"sha256", std::string(64, 'a')},
      {"media_type", "audio/wav"},
      {"byte_length", 1},
  };
  const auto command = uuid(100);
  const auto request = uuid(101);
  const auto invalid_requests = std::vector<std::pair<std::string, Json>>{
      {"pattern.slot.assign",
       {{"command_id", command},
        {"expected_revision", 0},
        {"pattern_slot", 1},
        {"pattern_id", "not-a-uuid"}}},
      {"pattern.slot.clear",
       {{"command_id", command},
        {"expected_revision", 0},
        {"pattern_slot", 16}}},
      {"pattern.slot.move",
       {{"command_id", command},
        {"expected_revision", 0},
        {"from_slot", -1},
        {"to_slot", 2}}},
      {"performance.list", {{"unexpected", true}}},
      {"performance.inspect", {{"performance_id", "not-a-uuid"}}},
      {"performance.record.begin",
       {{"command_id", command},
        {"expected_revision", 0},
        {"session_id", "not-a-uuid"},
        {"performance_id", kPerformanceId}}},
      {"performance.record.event",
       {{"session_id", kSessionId},
        {"event_id", request},
        {"event",
         {{"kind", "pad_press"},
          {"gesture_id", uuid(102)},
          {"slot", 1},
          {"velocity", 0},
          {"unexpected", true}}}}},
      {"performance.record.launch-request",
       {{"session_id", kSessionId},
        {"request_id", request},
        {"pattern_slot", 16}}},
      {"performance.record.flush",
       {{"session_id", kSessionId}, {"command_id", "not-a-uuid"}}},
      {"performance.record.stop",
       {{"session_id", kSessionId}, {"request_id", "not-a-uuid"}}},
      {"performance.record.status", {{"unexpected", true}}},
      {"performance.save",
       {{"command_id", command},
        {"expected_revision", 0},
        {"performance_id", kPerformanceId},
        {"name", "Performance"},
        {"recording_artifact",
         {{"sha256", std::string(64, 'a')},
          {"media_type", "audio/wav"},
          {"byte_length", 1},
          {"unexpected", true}}}}},
      {"performance.discard",
       {{"command_id", command},
        {"expected_revision", -1},
        {"performance_id", kPerformanceId}}},
      {"performance.recovery.list", {{"unexpected", true}}},
      {"performance.recovery.apply",
       {{"command_id", command},
        {"expected_revision", 0},
        {"session_id", "not-a-uuid"}}},
      {"performance.recovery.discard",
       {{"session_id", kSessionId}, {"request_id", "not-a-uuid"}}},
      {"performance.rename",
       {{"command_id", command},
        {"expected_revision", 0},
        {"performance_id", kPerformanceId},
        {"name", ""}}},
      {"performance.delete",
       {{"command_id", command},
        {"expected_revision", 0},
        {"performance_id", "not-a-uuid"}}},
      {"performance.recording.bind",
       {{"command_id", command},
        {"expected_revision", 0},
        {"performance_id", kPerformanceId},
        {"recording_artifact",
         {{"sha256", std::string(64, 'a')},
          {"media_type", "audio/mpeg"},
          {"byte_length", 1}}}}},
      {"performance.replay.begin",
       {{"replay_id", "not-a-uuid"},
        {"performance_id", kPerformanceId}}},
      {"performance.replay.stop",
       {{"replay_id", kReplayId}, {"request_id", "not-a-uuid"}}},
      {"performance.replay.status", {{"replay_id", "not-a-uuid"}}},
      {"performance.resample.commit",
       {{"command_id", command},
        {"expected_revision", 0},
        {"performance_id", kPerformanceId},
        {"source_start_frame", 20},
        {"source_end_frame", 20},
        {"target_slot", {{"bank", 0}, {"pad", 1}, {"unexpected", true}}}}},
  };
  LMDJ_CHECK(invalid_requests.size() == 23U);
  std::set<std::string> operations;
  for (const auto& [operation, payload] : invalid_requests) {
    LMDJ_CHECK(operations.insert(operation).second);
    const auto response = runtime->dispatch(operation, payload, {});
    LMDJ_CHECK(!response.value("ok", true));
    LMDJ_CHECK(
        response.at("error").at("code") == "HOST_PROTOCOL_MISMATCH");
  }

  const auto invalid_gestures = std::vector<Json>{
      {{"kind", "pad_press"},
       {"gesture_id", uuid(110)},
       {"slot", 64},
       {"velocity", 127}},
      {{"kind", "pad_release"},
       {"gesture_id", uuid(111)},
       {"slot", -1}},
      {{"kind", "fx_engage"},
       {"gesture_id", uuid(112)},
       {"fx", "chorus"},
       {"value", 500}},
      {{"kind", "fx_move"},
       {"gesture_id", uuid(113)},
       {"fx", "filter"},
       {"value", 1'001}},
      {{"kind", "fx_release"},
       {"gesture_id", "not-a-uuid"},
       {"fx", "filter"}},
      {{"kind", "hold_on"}, {"unexpected", true}},
      {{"kind", "hold_off"}, {"unexpected", true}},
      {{"kind", "unknown"}},
  };
  std::uint32_t suffix = 120;
  for (const auto& event : invalid_gestures) {
    const auto response = runtime->dispatch(
        "performance.record.event",
        {
            {"session_id", kSessionId},
            {"event_id", uuid(suffix++)},
            {"event", event},
        },
        {});
    LMDJ_CHECK(!response.value("ok", true));
    LMDJ_CHECK(
        response.at("error").at("code") == "HOST_PROTOCOL_MISMATCH");
  }

  const auto unsafe_integer = runtime->dispatch(
      "performance.save",
      {
          {"command_id", command},
          {"expected_revision", 9'007'199'254'740'992ULL},
          {"performance_id", kPerformanceId},
          {"name", "Performance"},
          {"recording_artifact", artifact},
      },
      {});
  LMDJ_CHECK(!unsafe_integer.value("ok", true));
  LMDJ_CHECK(
      unsafe_integer.at("error").at("code") == "HOST_PROTOCOL_MISMATCH");

  const auto repeated = [](std::string_view value, std::size_t count) {
    std::string result;
    for (std::size_t index = 0; index < count; ++index) {
      result += value;
    }
    return result;
  };
  const auto boundary_name = [&runtime, &command](
                                 std::string_view operation,
                                 const std::string& name) {
    auto payload = Json{
        {"command_id", command},
        {"expected_revision", 0},
        {"performance_id", kPerformanceId},
        {"name", name},
    };
    if (operation == "performance.save") {
      payload["recording_artifact"] = nullptr;
    }
    return runtime->dispatch(operation, payload, {});
  };
  for (const auto& [operation, unit] :
       std::array<std::pair<std::string_view, std::string_view>, 2>{
           std::pair{"performance.save", "演"},
           std::pair{"performance.rename", "😀"},
       }) {
    const auto accepted = boundary_name(operation, repeated(unit, 64));
    LMDJ_CHECK(!accepted.value("ok", true));
    LMDJ_CHECK(accepted.at("error").at("code") == "HOST_STATE_INVALID");
    const auto rejected = boundary_name(operation, repeated(unit, 65));
    LMDJ_CHECK(!rejected.value("ok", true));
    LMDJ_CHECK(
        rejected.at("error").at("code") == "HOST_PROTOCOL_MISMATCH");
  }
}

void test_owner_loss_never_materializes_an_unacknowledged_launch() {
  TempDirectory temporary;
  {
    auto created = ControlRuntime::create(
        temporary.path(), config(temporary.path()), kLimits);
    LMDJ_CHECK(created.has_value());
    auto runtime = std::move(created.value());
    require_success(runtime->dispatch(
        "project.create",
        {
            {"project_id", kProjectId},
            {"bpm", 120},
            {"initial_pattern",
             {{"pattern_id", kPatternId},
              {"bars", 1},
              {"events", Json::array()}}},
        },
        {}), "owner-loss project.create");
    require_success(runtime->dispatch(
        "pattern.slot.assign",
        {
            {"command_id", uuid(60)},
            {"expected_revision", 0},
            {"pattern_slot", 1},
            {"pattern_id", kPatternId},
        },
        {}), "owner-loss pattern.slot.assign");
    require_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    LMDJ_CHECK(runtime->engine().start().has_value());
    require_success(runtime->dispatch(
        "performance.record.begin",
        {
            {"command_id", uuid(61)},
            {"expected_revision", 1},
            {"session_id", kSessionId},
            {"performance_id", kPerformanceId},
        },
        {}), "owner-loss performance.record.begin");
    require_success(runtime->dispatch(
        "performance.record.launch-request",
        {
            {"session_id", kSessionId},
            {"request_id", uuid(62)},
            {"pattern_slot", 1},
        },
        {}), "owner-loss performance.record.launch-request");
    runtime->engine().stop();
  }

  auto reopened = ControlRuntime::create(
      temporary.path(), config(temporary.path()), kLimits);
  LMDJ_CHECK(reopened.has_value());
  auto runtime = std::move(reopened.value());
  require_success(runtime->dispatch(
      "project.open",
      {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
      {}), "owner-loss project.open");
  const auto candidates = require_success(runtime->dispatch(
      "performance.recovery.list", Json::object(), {}),
      "owner-loss performance.recovery.list");
  LMDJ_CHECK(candidates.at("candidates").size() == 1);
  LMDJ_CHECK(
      candidates.at("candidates").at(0).at("pending_event_count") == 0);
  const auto inspected = require_success(runtime->dispatch(
      "performance.inspect", {{"performance_id", kPerformanceId}}, {}),
      "owner-loss performance.inspect");
  LMDJ_CHECK(std::none_of(
      inspected.at("performance").at("events").begin(),
      inspected.at("performance").at("events").end(),
      [](const Json& event) { return event.at("kind") == "pattern_launch"; }));
  require_success(runtime->dispatch(
      "performance.recovery.discard",
      {
          {"session_id", kSessionId},
          {"request_id", uuid(63)},
      },
      {}), "owner-loss performance.recovery.discard");
  const auto after_discard = require_success(runtime->dispatch(
      "performance.recovery.list", Json::object(), {}),
      "owner-loss performance.recovery.list after discard");
  LMDJ_CHECK(after_discard.at("candidates").size() == 1);
  LMDJ_CHECK(after_discard.at("candidates").at(0).at("reason") == "stopped");
  require_success(runtime->dispatch(
      "performance.discard",
      {
          {"command_id", uuid(64)},
          {"expected_revision", 2},
          {"performance_id", kPerformanceId},
      },
      {}), "owner-loss performance.discard stopped draft");
  const auto after_draft_discard = require_success(runtime->dispatch(
      "performance.recovery.list", Json::object(), {}),
      "owner-loss performance.recovery.list after draft discard");
  LMDJ_CHECK(after_draft_discard.at("candidates").empty());
}

}  // namespace

int main() {
  try {
    test_web_audio_bridge_carries_one_opaque_destination_and_direct_fallback();
    test_constructs_application_with_engine_authorities_and_services_launches();
    test_rejects_invalid_values_at_the_cpp_host_boundary();
    test_owner_loss_never_materializes_an_unacknowledged_launch();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
