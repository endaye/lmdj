#include "control_runtime.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <memory>
#include <mutex>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>

#include "tests/core/support/test.hpp"

namespace lmdj::web_host::detail {
nlohmann::json normalize_error_for_testing(
    const foundation::Error& error);
}

namespace {

using Json = nlohmann::json;
using lmdj::audio::CaptureState;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RuntimePreparationLimits;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;
using lmdj::web_host::ControlRuntime;
using lmdj::web_host::detail::AudioQuiescenceCoordinator;
using lmdj::web_host::detail::BridgeHooks;
using lmdj::web_host::detail::BridgePollStatus;
using lmdj::web_host::detail::BridgeSubmitStatus;
using lmdj::web_host::detail::ControlBridge;
using lmdj::web_host::detail::ControlRuntimeAudioAccess;
using lmdj::web_host::detail::kBridgeMaximumEnvelopeBytes;
using lmdj::web_host::detail::kBridgeMaximumSidecarBytes;
using lmdj::web_host::detail::kBridgeMessageSlotCount;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kPatternId =
    "00000000-0000-4000-8000-000000000010";
constexpr std::string_view kCommittedPatternId =
    "00000000-0000-4000-8000-000000000011";
constexpr std::string_view kAssetId =
    "00000000-0000-4000-8000-000000000101";
constexpr std::string_view kTakeId =
    "00000000-0000-4000-8000-000000000201";
constexpr std::string_view kProtocolShapeRequestId =
    "01234567-89ab-cdef-0123-456789abcdef";

constexpr RuntimePreparationLimits kWebLimits{
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
            ("lmdj-web-control-test-" + std::to_string(nonce) + "-" +
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

Application make_application(const std::filesystem::path& root) {
  return Application(ApplicationConfig{
      root,
      std::make_shared<Registry>(),
      ProviderPolicy{},
      [] { return std::string("2026-08-04T00:00:00.000Z"); },
  });
}

std::unique_ptr<ControlRuntime> make_runtime(
    const std::filesystem::path& root,
    RuntimePreparationLimits limits = kWebLimits) {
  auto created = ControlRuntime::create(
      root, make_application(root), limits);
  LMDJ_CHECK(created.has_value());
  return std::move(created.value());
}

Json slot(std::uint32_t bank, std::uint32_t pad) {
  return {{"bank", bank}, {"pad", pad}};
}

Json empty_pattern(std::string_view pattern_id = kPatternId) {
  return {
      {"pattern_id", pattern_id},
      {"bars", 1},
      {"events", Json::array()},
  };
}

Json create_payload(
    std::string_view project_id = kProjectId,
    std::string_view pattern_id = kPatternId) {
  return {
      {"project_id", project_id},
      {"bpm", 120},
      {"initial_pattern", empty_pattern(pattern_id)},
  };
}

void write_u16(
    std::vector<std::byte>& bytes,
    std::size_t offset,
    std::uint16_t value) {
  bytes.at(offset) = static_cast<std::byte>(value & 0xffU);
  bytes.at(offset + 1) = static_cast<std::byte>(value >> 8U);
}

void write_u32(
    std::vector<std::byte>& bytes,
    std::size_t offset,
    std::uint32_t value) {
  for (std::size_t index = 0; index < 4; ++index) {
    bytes.at(offset + index) =
        static_cast<std::byte>(value >> (index * 8U));
  }
}

void write_tag(
    std::vector<std::byte>& bytes,
    std::size_t offset,
    std::string_view tag) {
  LMDJ_CHECK(tag.size() == 4);
  for (std::size_t index = 0; index < tag.size(); ++index) {
    bytes.at(offset + index) =
        static_cast<std::byte>(static_cast<unsigned char>(tag.at(index)));
  }
}

std::vector<std::byte> mono_pcm16_wav(std::uint32_t frames) {
  const auto data_bytes = frames * 2U;
  std::vector<std::byte> bytes(44U + data_bytes);
  write_tag(bytes, 0, "RIFF");
  write_u32(bytes, 4, 36U + data_bytes);
  write_tag(bytes, 8, "WAVE");
  write_tag(bytes, 12, "fmt ");
  write_u32(bytes, 16, 16);
  write_u16(bytes, 20, 1);
  write_u16(bytes, 22, 1);
  write_u32(bytes, 24, 48'000);
  write_u32(bytes, 28, 96'000);
  write_u16(bytes, 32, 2);
  write_u16(bytes, 34, 16);
  write_tag(bytes, 36, "data");
  write_u32(bytes, 40, data_bytes);
  return bytes;
}

std::string sha256(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  const auto* first = reinterpret_cast<const unsigned char*>(bytes.data());
  hasher.process(first, first + bytes.size());
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

Json import_payload(
    std::uint32_t command_suffix,
    std::uint64_t expected_revision,
    std::string_view asset_id,
    std::span<const std::byte> bytes) {
  return {
      {"command_id", uuid(command_suffix)},
      {"expected_revision", expected_revision},
      {"asset_id", asset_id},
      {"media_type", "audio/wav"},
      {"sidecar",
       {
           {"sidecar_bytes", bytes.size()},
           {"sidecar_sha256", sha256(bytes)},
       }},
  };
}

Json assign_payload(
    std::uint32_t command_suffix,
    std::uint64_t expected_revision,
    std::string_view asset_id,
    std::uint8_t pad = 0) {
  return {
      {"command_id", uuid(command_suffix)},
      {"expected_revision", expected_revision},
      {"slot", slot(0, pad)},
      {"asset_id", asset_id},
  };
}

void check_success(const Json& response) {
  LMDJ_CHECK(response.is_object());
  LMDJ_CHECK(response.size() == 2);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.contains("result"));
}

Json check_locked_success_result(const Json& response) {
  check_success(response);
  LMDJ_CHECK(response.at("result").is_object());
  return response.at("result");
}

Json check_error(const Json& response, std::string_view code) {
  LMDJ_CHECK(response.is_object());
  LMDJ_CHECK(response.size() == 2);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == code);
  LMDJ_CHECK(response.at("error").at("message").is_string());
  LMDJ_CHECK(response.at("error").at("details").is_object());
  return response.at("error");
}

void check_exact_keys(
    const Json& value,
    std::initializer_list<std::string_view> keys) {
  LMDJ_CHECK(value.is_object());
  LMDJ_CHECK(value.size() == keys.size());
  for (const auto key : keys) {
    LMDJ_CHECK(value.contains(std::string(key)));
  }
}

Json check_exact_success(
    const Json& response,
    std::initializer_list<std::string_view> keys) {
  const auto& result = check_locked_success_result(response);
  check_exact_keys(result, keys);
  return result;
}

void wait_until(auto predicate) {
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!predicate()) {
    if (std::chrono::steady_clock::now() >= deadline) {
      throw std::runtime_error("timed out waiting for Audio test state");
    }
    std::this_thread::yield();
  }
}

class ContinuousAudioDriver final {
 public:
  explicit ContinuousAudioDriver(RealtimeEngine& engine)
      : engine_(engine), thread_([this] { run(); }) {}

  ~ContinuousAudioDriver() { stop(); }

  ContinuousAudioDriver(const ContinuousAudioDriver&) = delete;
  ContinuousAudioDriver& operator=(const ContinuousAudioDriver&) = delete;

  void stop() noexcept {
    running_.store(false, std::memory_order_release);
    if (thread_.joinable()) {
      thread_.join();
    }
  }

 private:
  void run() noexcept {
    std::array<float, 128> left{};
    std::array<float, 128> right{};
    while (running_.load(std::memory_order_acquire)) {
      engine_.render(left.data(), right.data(), 128);
      std::this_thread::sleep_for(std::chrono::microseconds(100));
    }
  }

  RealtimeEngine& engine_;
  std::atomic<bool> running_{true};
  std::thread thread_;
};

struct FakeCoordinator final {
  static lmdj::foundation::Result<void> await(
      void* context, std::uint32_t timeout_ms) noexcept {
    auto& self = *static_cast<FakeCoordinator*>(context);
    self.called = true;
    self.timeout_ms = timeout_ms;
    if (self.engine != nullptr) {
      self.observed_capture_idle =
          self.engine->capture_telemetry().state == CaptureState::idle;
      self.observed_engine_running =
          self.engine->telemetry().state ==
          lmdj::audio::RealtimeState::running;
    }
    if (!self.workspace_root.empty() && !self.expected_take_id.empty()) {
      try {
        const auto sealed_directory =
            self.workspace_root / "projects" /
            (std::string(kProjectId) + ".lmdj") / "recovery/sealed";
        const auto prefix = self.expected_take_id + "-capture_incomplete";
        for (const auto& entry :
             std::filesystem::directory_iterator(sealed_directory)) {
          if (entry.is_regular_file() &&
              entry.path().filename().string().starts_with(prefix)) {
            self.observed_take_sealed = true;
            break;
          }
        }
      } catch (...) {
        self.observed_take_sealed = false;
      }
    }
    if (self.succeed && self.driver != nullptr) {
      self.driver->stop();
    }
    if (!self.succeed) {
      return lmdj::foundation::Result<void>::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::internal_error,
              self.timeout
                  ? "native coordinator timeout must not escape"
                  : "native coordinator failure must not escape",
          });
    }
    return lmdj::foundation::Result<void>::success();
  }

  AudioQuiescenceCoordinator seam() noexcept {
    return AudioQuiescenceCoordinator{this, &FakeCoordinator::await};
  }

  ContinuousAudioDriver* driver = nullptr;
  RealtimeEngine* engine = nullptr;
  std::filesystem::path workspace_root;
  std::string expected_take_id;
  bool succeed = true;
  bool timeout = false;
  bool called = false;
  bool observed_capture_idle = false;
  bool observed_engine_running = false;
  bool observed_take_sealed = false;
  std::uint32_t timeout_ms = 0;
};

class OneShotAudioDriver final {
 public:
  explicit OneShotAudioDriver(RealtimeEngine& engine)
      : engine_(engine), thread_([this] { run(); }) {}

  ~OneShotAudioDriver() {
    {
      std::lock_guard lock(mutex_);
      stopped_ = true;
    }
    changed_.notify_all();
    thread_.join();
  }

  void render_one() {
    std::unique_lock lock(mutex_);
    const auto target = completed_ + 1;
    ++permits_;
    changed_.notify_all();
    changed_.wait(lock, [this, target] { return completed_ >= target; });
  }

 private:
  void run() noexcept {
    std::array<float, 128> left{};
    std::array<float, 128> right{};
    while (true) {
      {
        std::unique_lock lock(mutex_);
        changed_.wait(lock, [this] { return stopped_ || permits_ != 0; });
        if (stopped_) {
          return;
        }
        --permits_;
      }
      engine_.render(left.data(), right.data(), 128);
      {
        std::lock_guard lock(mutex_);
        ++completed_;
      }
      changed_.notify_all();
    }
  }

  RealtimeEngine& engine_;
  std::mutex mutex_;
  std::condition_variable changed_;
  std::size_t permits_ = 0;
  std::size_t completed_ = 0;
  bool stopped_ = false;
  std::thread thread_;
};

void import_and_assign(
    ControlRuntime& runtime,
    std::span<const std::byte> wav,
    std::string_view asset_id,
    std::uint32_t import_command,
    std::uint32_t assign_command,
    std::uint64_t starting_revision) {
  check_success(runtime.dispatch(
      "asset.import",
      import_payload(import_command, starting_revision, asset_id, wav),
      wav));
  check_success(runtime.dispatch(
      "pad.assign",
      assign_payload(
          assign_command, starting_revision + 1, asset_id),
      {}));
}

Json inspect_project(
    const std::filesystem::path& root,
    std::string_view project_id) {
  auto observer = make_application(root);
  return observer.query(
      {
          {"operation", "project.inspect"},
          {"project_path",
           (root / "projects" /
            (std::string(project_id) + ".lmdj"))
               .generic_string()},
      });
}

void test_facade_error_details_follow_an_explicit_safe_schema() {
  static constexpr std::string_view kDetailMarker =
      "detail leaked /private/project-storage";
  static constexpr std::string_view kPathMarker =
      "/private/project-storage/manifest.json";
  static constexpr std::string_view kSystemMarker =
      "system error 13 from native storage";
  static constexpr std::string_view kStorageMarker =
      "backend_volume_offline";
  const auto normalized =
      lmdj::web_host::detail::normalize_error_for_testing(
      lmdj::foundation::Error{
          lmdj::foundation::ErrorCode::revision_conflict,
          "source message must not escape",
          {
              {"actual_revision", std::uint64_t{9}},
              {"expected_revision", std::uint64_t{8}},
              {"detail", kDetailMarker},
              {"path", kPathMarker},
              {"system_error", kSystemMarker},
              {"storage_condition", kStorageMarker},
              {"nested",
               {
                   {"captured_revision", std::uint64_t{7}},
                   {"detail", kDetailMarker},
               }},
              {"history",
               Json::array(
                   {{{"expected_revision", std::uint64_t{6}},
                     {"path", kPathMarker}},
                    kSystemMarker})},
          },
      });
  const auto& error = check_error(normalized, "REVISION_CONFLICT");
  LMDJ_CHECK(error.at("message") == "project revision conflict");
  LMDJ_CHECK((
      error.at("details") ==
      Json{
          {"actual_revision", 9},
          {"expected_revision", 8},
          {"nested", {{"captured_revision", 7}}},
          {"history", Json::array({{{"expected_revision", 6}}})},
      }));
  const auto encoded = normalized.dump();
  for (const auto marker :
       {kDetailMarker, kPathMarker, kSystemMarker, kStorageMarker}) {
    LMDJ_CHECK(encoded.find(marker) == std::string::npos);
  }
}

void test_exact_payloads_and_facade_owned_project_journey() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());

  const auto& initial_status = check_exact_success(
      runtime->dispatch("host.status", Json::object(), {}),
      {"state", "project_id", "project_revision", "pattern_id",
       "runtime_ready", "control_generation", "acknowledged_generation",
       "limits", "audio_state", "capture_state"});
  LMDJ_CHECK(initial_status.at("project_id").is_null());
  LMDJ_CHECK(initial_status.at("project_revision").is_null());
  LMDJ_CHECK(initial_status.at("pattern_id").is_null());
  LMDJ_CHECK(initial_status.at("runtime_ready") == false);
  LMDJ_CHECK(initial_status.at("control_generation").is_null());
  LMDJ_CHECK(initial_status.at("acknowledged_generation").is_null());
  LMDJ_CHECK((
      initial_status.at("limits") ==
      Json{
          {"maximum_artifact_bytes", kWebLimits.maximum_artifact_bytes},
          {"maximum_decoded_frames_per_pad",
           kWebLimits.maximum_decoded_frames_per_pad},
          {"maximum_prepared_bank_bytes",
           kWebLimits.maximum_prepared_bank_bytes},
          {"maximum_live_bank_bytes", kWebLimits.maximum_live_bank_bytes},
      }));

  auto extra_create = create_payload();
  extra_create["project_path"] = "/forbidden/path.lmdj";
  check_error(
      runtime->dispatch("project.create", extra_create, {}),
      "HOST_PROTOCOL_MISMATCH");
  LMDJ_CHECK(!std::filesystem::exists(
      temp.path() / "projects" /
      (std::string(kProjectId) + ".lmdj")));

  const auto& created = check_exact_success(
      runtime->dispatch("project.create", create_payload(), {}),
      {"project_id", "project_revision", "initial_pattern_id",
       "runtime_ready"});
  LMDJ_CHECK(created.at("project_id") == kProjectId);
  LMDJ_CHECK(created.at("project_revision") == 0);
  LMDJ_CHECK(created.at("initial_pattern_id") == kPatternId);
  LMDJ_CHECK(created.at("runtime_ready") == false);
  LMDJ_CHECK(std::filesystem::exists(
      temp.path() / "projects" /
      (std::string(kProjectId) + ".lmdj") / "manifest.json"));

  auto competitor = make_runtime(temp.path());
  const auto& busy = check_error(
      competitor->dispatch(
          "project.open",
          {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
          {}),
      "PROJECT_BUSY");
  LMDJ_CHECK((
      busy == Json{
                  {"code", "PROJECT_BUSY"},
                  {"message", "project is already open for writing"},
                  {"details", Json::object()},
              }));
  competitor.reset();

  const auto wav = mono_pcm16_wav(2'400);
  auto bad_import = import_payload(301, 0, kAssetId, wav);
  bad_import["sidecar"]["sidecar_sha256"] = std::string(64, '0');
  check_error(
      runtime->dispatch("asset.import", bad_import, wav),
      "HOST_PROTOCOL_MISMATCH");
  const auto& imported = check_exact_success(
      runtime->dispatch(
          "asset.import", import_payload(301, 0, kAssetId, wav), wav),
      {"asset_id", "artifact", "committed_revision", "replayed",
       "project_revision"});
  LMDJ_CHECK(imported.at("asset_id") == kAssetId);
  LMDJ_CHECK(imported.at("committed_revision") == 1);
  LMDJ_CHECK(imported.at("replayed") == false);
  LMDJ_CHECK(imported.at("project_revision") == 1);
  const auto& assigned = check_exact_success(
      runtime->dispatch("pad.assign", assign_payload(302, 1, kAssetId), {}),
      {"slot", "asset_id", "committed_revision", "replayed",
       "project_revision"});
  LMDJ_CHECK(assigned.at("slot") == slot(0, 0));
  LMDJ_CHECK(assigned.at("asset_id") == kAssetId);
  LMDJ_CHECK(assigned.at("committed_revision") == 2);
  LMDJ_CHECK(assigned.at("replayed") == false);
  LMDJ_CHECK(assigned.at("project_revision") == 2);

  const auto& opened = check_exact_success(
      runtime->dispatch(
          "project.open",
          {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
          {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(opened.at("project_id") == kProjectId);
  LMDJ_CHECK(opened.at("project_revision") == 2);
  LMDJ_CHECK(opened.at("pattern_id") == kPatternId);
  LMDJ_CHECK(opened.at("runtime_ready") == true);
  LMDJ_CHECK(opened.at("generation") == 1);
  LMDJ_CHECK(opened.at("snapshot_error").is_null());
  const auto& inspected_result = check_exact_success(
      runtime->dispatch("project.inspect", Json::object(), {}),
      {"project", "project_revision"});
  LMDJ_CHECK(inspected_result.at("project_revision") == 2);
  LMDJ_CHECK(inspected_result.at("project").at("project_id") == kProjectId);

  const auto& activated = check_exact_success(
      runtime->dispatch("audio.activate", Json::object(), {}),
      {"state", "changed", "generation"});
  LMDJ_CHECK((
      activated ==
      Json{{"state", "running"}, {"changed", true}, {"generation", 1}}));
  ContinuousAudioDriver audio(runtime->engine());

  const auto& begun = check_exact_success(
      runtime->dispatch(
          "take.begin",
          {{"take_id", kTakeId}, {"expected_revision", 2}},
          {}),
      {"take_id", "project_revision", "capture_state"});
  LMDJ_CHECK(begun.at("take_id") == kTakeId);
  LMDJ_CHECK(begun.at("project_revision") == 2);
  LMDJ_CHECK(begun.at("capture_state") == "arm_pending");
  wait_until([&] {
    return runtime->engine().capture_telemetry().state ==
           CaptureState::active;
  });
  const auto& trigger = check_exact_success(
      runtime->dispatch(
          "trigger", {{"slot", 0}, {"velocity", 100}}, {}),
      {"sequence", "status"});
  LMDJ_CHECK(trigger.at("sequence") == 1);
  LMDJ_CHECK(trigger.at("status") == "enqueued");
  wait_until([&] {
    return runtime->engine().capture_telemetry().captured_events == 1;
  });
  const auto& stopped = check_exact_success(
      runtime->dispatch("take.stop", Json::object(), {}),
      {"take_id", "project_revision", "status"});
  LMDJ_CHECK((
      stopped ==
      Json{{"take_id", kTakeId},
           {"project_revision", 2},
           {"status", "committable"}}));
  audio.stop();

  const auto committed_pattern = Json{
      {"pattern_id", kCommittedPatternId},
      {"bars", 1},
      {"events",
       Json::array(
           {{{"slot", slot(0, 0)}, {"step", 0}, {"velocity", 100}}})},
  };
  const auto& committed = check_exact_success(
      runtime->dispatch(
          "take.commit",
          {
              {"command_id", uuid(303)},
              {"expected_revision", 2},
              {"pattern", committed_pattern},
          },
          {}),
      {"take_id", "pattern_id", "committed_revision", "replayed",
       "project_revision"});
  LMDJ_CHECK((
      committed ==
      Json{{"take_id", kTakeId},
           {"pattern_id", kCommittedPatternId},
           {"committed_revision", 3},
           {"replayed", false},
           {"project_revision", 3}}));
  const auto& recoverable = check_exact_success(
      runtime->dispatch("take.recoverable.list", Json::object(), {}),
      {"candidates", "project_revision"});
  LMDJ_CHECK(recoverable.at("candidates").empty());
  LMDJ_CHECK(recoverable.at("project_revision") == 3);
  const auto inspected = inspect_project(temp.path(), kProjectId);
  LMDJ_CHECK(inspected.at("ok") == true);
  LMDJ_CHECK(
      inspected.at("result").at("project").at("project_id") == kProjectId);
  LMDJ_CHECK(
      inspected.at("result")
              .at("project")
              .at("takes")
              .at(kTakeId)
              .at("events")
              .size() ==
      1);
  LMDJ_CHECK(
      inspected.at("result")
          .at("project")
          .at("patterns")
          .contains(kPatternId));
  LMDJ_CHECK(
      inspected.at("result")
          .at("project")
          .at("patterns")
          .contains(kCommittedPatternId));

  FakeCoordinator close_coordinator;
  const auto installed = ControlRuntimeAudioAccess::install(
      *runtime, close_coordinator.seam());
  LMDJ_CHECK(installed.has_value());
  const auto& suspended = check_exact_success(
      runtime->dispatch("audio.suspend", Json::object(), {}),
      {"state", "changed", "sealed_take_id"});
  LMDJ_CHECK((
      suspended ==
      Json{{"state", "audio-suspended"},
           {"changed", true},
           {"sealed_take_id", nullptr}}));
  LMDJ_CHECK(close_coordinator.called);
  const auto& closed = check_exact_success(
      runtime->dispatch("host.close", Json::object(), {}),
      {"state", "sealed_take_id"});
  LMDJ_CHECK((
      closed == Json{{"state", "closed"}, {"sealed_take_id", nullptr}}));
  runtime.reset();

  auto reopened = make_runtime(temp.path());
  check_success(reopened->dispatch(
      "project.open",
      {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
      {}));
}

void test_take_stop_drains_the_final_disarm_quantum() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 751, 752, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "take.begin",
      {{"take_id", kTakeId}, {"expected_revision", 2}},
      {}));
  audio.render_one();
  LMDJ_CHECK(
      runtime->engine().capture_telemetry().state == CaptureState::active);

  // This event is admitted before the stop boundary but is not rendered until
  // capture has entered disarm_pending.
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 101}}, {}));
  LMDJ_CHECK(
      runtime->engine().capture_telemetry().captured_events == 0);
  Json stopped;
  std::thread stop_thread([&] {
    stopped = runtime->dispatch("take.stop", Json::object(), {});
  });
  wait_until([&] {
    return runtime->engine().capture_telemetry().state ==
           CaptureState::disarm_pending;
  });
  audio.render_one();
  stop_thread.join();
  LMDJ_CHECK((
      check_exact_success(
          stopped, {"take_id", "project_revision", "status"}) ==
      Json{{"take_id", kTakeId},
           {"project_revision", 2},
           {"status", "committable"}}));

  // Events admitted after take.stop returns still play, but capture is idle
  // and they must not enter the committable Take.
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 102}}, {}));
  audio.render_one();
  check_success(runtime->dispatch(
      "take.commit",
      {
          {"command_id", uuid(753)},
          {"expected_revision", 2},
          {"pattern", empty_pattern(kCommittedPatternId)},
      },
      {}));

  const auto inspected = inspect_project(temp.path(), kProjectId);
  const auto& events = inspected.at("result")
                           .at("project")
                           .at("takes")
                           .at(kTakeId)
                           .at("events");
  LMDJ_CHECK(events.size() == 1);
  LMDJ_CHECK(events.at(0).at("velocity") == 101);
}

void test_audio_suspend_requires_and_honors_quiescence_coordinator() {
  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(8);
    import_and_assign(*runtime, wav, kAssetId, 801, 802, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    const auto& missing = check_error(
        runtime->dispatch("audio.suspend", Json::object(), {}),
        "HOST_STATE_INVALID");
    LMDJ_CHECK(missing.at("message") == "audio quiescence is unavailable");
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::running);
    check_error(
        runtime->dispatch("host.status", Json::object(), {}),
        "HOST_STATE_INVALID");
  }

  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(8);
    import_and_assign(*runtime, wav, kAssetId, 811, 812, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    FakeCoordinator failure;
    failure.succeed = false;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, failure.seam())
            .has_value());
    check_error(
        runtime->dispatch("audio.suspend", Json::object(), {}),
        "INTERNAL_ERROR");
    LMDJ_CHECK(failure.called);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::running);
    check_error(
        runtime->dispatch("host.status", Json::object(), {}),
        "HOST_STATE_INVALID");
  }

  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(2'400);
    import_and_assign(*runtime, wav, kAssetId, 821, 822, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    ContinuousAudioDriver driver(runtime->engine());
    FakeCoordinator success;
    success.driver = &driver;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, success.seam())
            .has_value());
    check_success(runtime->dispatch(
        "take.begin",
        {{"take_id", kTakeId}, {"expected_revision", 2}},
        {}));
    wait_until([&] {
      return runtime->engine().capture_telemetry().state ==
             CaptureState::active;
    });
    check_success(runtime->dispatch(
        "trigger", {{"slot", 0}, {"velocity", 100}}, {}));
    wait_until([&] {
      return runtime->engine().capture_telemetry().captured_events == 1;
    });
    const auto& suspended = check_exact_success(
        runtime->dispatch("audio.suspend", Json::object(), {}),
        {"state", "changed", "sealed_take_id"});
    LMDJ_CHECK((
        suspended ==
        Json{{"state", "audio-suspended"},
             {"changed", true},
             {"sealed_take_id", kTakeId}}));
    LMDJ_CHECK(success.called);
    LMDJ_CHECK(success.timeout_ms == 30'000);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::stopped);
    const auto& candidates = check_exact_success(
        runtime->dispatch("take.recoverable.list", Json::object(), {}),
        {"candidates", "project_revision"});
    LMDJ_CHECK(candidates.at("candidates").size() == 1);
    LMDJ_CHECK(
        candidates.at("candidates").at(0).at("reason") ==
        "capture_incomplete");
  }
}

void test_host_close_orders_capture_seal_quiescence_and_engine_stop() {
  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(2'400);
    import_and_assign(*runtime, wav, kAssetId, 831, 832, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    ContinuousAudioDriver driver(runtime->engine());
    FakeCoordinator coordinator;
    coordinator.driver = &driver;
    coordinator.engine = &runtime->engine();
    coordinator.workspace_root = temp.path();
    coordinator.expected_take_id = kTakeId;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
            .has_value());
    check_success(runtime->dispatch(
        "take.begin",
        {{"take_id", kTakeId}, {"expected_revision", 2}},
        {}));
    wait_until([&] {
      return runtime->engine().capture_telemetry().state ==
             CaptureState::active;
    });
    check_success(runtime->dispatch(
        "trigger", {{"slot", 0}, {"velocity", 103}}, {}));
    wait_until([&] {
      return runtime->engine().capture_telemetry().captured_events == 1;
    });

    const auto& closed = check_exact_success(
        runtime->dispatch("host.close", Json::object(), {}),
        {"state", "sealed_take_id"});
    LMDJ_CHECK((
        closed ==
        Json{{"state", "closed"}, {"sealed_take_id", kTakeId}}));
    LMDJ_CHECK(coordinator.called);
    LMDJ_CHECK(coordinator.timeout_ms == 10'000);
    LMDJ_CHECK(coordinator.observed_capture_idle);
    LMDJ_CHECK(coordinator.observed_take_sealed);
    LMDJ_CHECK(coordinator.observed_engine_running);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::stopped);
    check_error(
        runtime->dispatch("host.status", Json::object(), {}),
        "HOST_STATE_INVALID");

    runtime.reset();
    auto reopened = make_runtime(temp.path());
    check_success(reopened->dispatch(
        "project.open",
        {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
        {}));
    const auto& recoverable = check_exact_success(
        reopened->dispatch("take.recoverable.list", Json::object(), {}),
        {"candidates", "project_revision"});
    LMDJ_CHECK(recoverable.at("candidates").size() == 1);
    LMDJ_CHECK(
        recoverable.at("candidates").at(0).at("take_id") == kTakeId);
  }

  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(2'400);
    import_and_assign(*runtime, wav, kAssetId, 841, 842, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    ContinuousAudioDriver driver(runtime->engine());
    FakeCoordinator timeout;
    timeout.succeed = false;
    timeout.timeout = true;
    timeout.engine = &runtime->engine();
    timeout.workspace_root = temp.path();
    timeout.expected_take_id = kTakeId;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, timeout.seam())
            .has_value());
    check_success(runtime->dispatch(
        "take.begin",
        {{"take_id", kTakeId}, {"expected_revision", 2}},
        {}));
    wait_until([&] {
      return runtime->engine().capture_telemetry().state ==
             CaptureState::active;
    });

    check_error(
        runtime->dispatch("host.close", Json::object(), {}),
        "INTERNAL_ERROR");
    LMDJ_CHECK(timeout.called);
    LMDJ_CHECK(timeout.timeout_ms == 10'000);
    LMDJ_CHECK(timeout.observed_capture_idle);
    LMDJ_CHECK(timeout.observed_take_sealed);
    LMDJ_CHECK(timeout.observed_engine_running);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::running);
    check_error(
        runtime->dispatch("host.status", Json::object(), {}),
        "HOST_STATE_INVALID");
    check_error(
        runtime->dispatch("audio.activate", Json::object(), {}),
        "HOST_STATE_INVALID");
  }
}

void test_exact_non_fifo_aggregate_accounting_and_prior_bank_retention() {
  TempDirectory temp;
  constexpr RuntimePreparationLimits limits{
      1'048'576,
      512,
      4'096,
      2'060,
  };
  auto runtime = make_runtime(temp.path(), limits);
  check_success(runtime->dispatch(
      "project.create", create_payload(), {}));

  const auto large = mono_pcm16_wav(512);
  import_and_assign(*runtime, large, uuid(401), 411, 412, 0);
  const auto& first = check_exact_success(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(first.at("generation") == 1);
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 127}}, {}));
  audio.render_one();
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 1);

  const auto newer_small = mono_pcm16_wav(1);
  import_and_assign(*runtime, newer_small, uuid(402), 413, 414, 2);
  const auto& second = check_exact_success(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(second.at("generation") == 2);
  audio.render_one();

  const auto current = mono_pcm16_wav(2);
  import_and_assign(*runtime, current, uuid(403), 415, 416, 4);
  const auto& third = check_exact_success(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(third.at("generation") == 3);
  audio.render_one();

  const auto rejected_candidate = mono_pcm16_wav(3);
  import_and_assign(
      *runtime, rejected_candidate, uuid(404), 417, 418, 6);
  const auto& rejected = check_error(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      "WEB_RUNTIME_RESOURCE_LIMIT");
  LMDJ_CHECK((
      rejected.at("details") ==
      Json{
          {"resource", "live_bank_bytes"},
          {"observed", 2'068},
          {"limit", 2'060},
      }));
  LMDJ_CHECK(runtime->engine().bank_telemetry().current_generation == 3);

  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 127}}, {}));
  audio.render_one();
  LMDJ_CHECK(!runtime->drain_outcomes().empty());
  const auto& after_reclaim = check_exact_success(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(after_reclaim.at("generation") == 4);
}

void test_oversized_project_switch_is_inspectable_but_not_runnable() {
  TempDirectory temp;
  constexpr RuntimePreparationLimits limits{
      1'048'576,
      1,
      4,
      8,
  };
  auto runtime = make_runtime(temp.path(), limits);
  check_success(runtime->dispatch(
      "project.create", create_payload(kProjectId, kPatternId), {}));
  const auto small = mono_pcm16_wav(1);
  import_and_assign(*runtime, small, kAssetId, 501, 502, 0);
  check_success(runtime->dispatch(
      "project.open",
      {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
      {}));

  const auto large_project = uuid(2);
  const auto large_pattern = uuid(20);
  const auto large_asset = uuid(102);
  {
    // Author the oversized Project through a separate Facade/Runtime. The
    // Runtime under test must switch directly from the live small Project via
    // project.open; no same-Runtime project.create may pre-disable its Bank.
    auto builder = make_runtime(temp.path());
    check_success(builder->dispatch(
        "project.create",
        create_payload(large_project, large_pattern),
        {}));
    const auto large = mono_pcm16_wav(2);
    import_and_assign(*builder, large, large_asset, 503, 504, 0);
    check_success(builder->dispatch("host.close", Json::object(), {}));
  }
  LMDJ_CHECK(runtime->engine().bank_telemetry().current_generation == 1);
  const auto& opened = check_exact_success(
      runtime->dispatch(
          "project.open",
          {{"project_id", large_project}, {"pattern_id", large_pattern}},
          {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(opened.at("project_id") == large_project);
  LMDJ_CHECK(opened.at("project_revision") == 2);
  LMDJ_CHECK(opened.at("pattern_id") == large_pattern);
  LMDJ_CHECK(opened.at("runtime_ready") == false);
  LMDJ_CHECK(opened.at("generation").is_null());
  LMDJ_CHECK(
      opened.at("snapshot_error").at("code") ==
      "WEB_RUNTIME_RESOURCE_LIMIT");
  LMDJ_CHECK((
      opened.at("snapshot_error").at("details") ==
      Json{
          {"resource", "decoded_frames_per_pad"},
          {"observed", 2},
          {"limit", 1},
      }));
  const auto& inspected = check_exact_success(
      runtime->dispatch("project.inspect", Json::object(), {}),
      {"project", "project_revision"});
  LMDJ_CHECK(
      inspected.at("project").at("project_id") == large_project);
  const auto& status = check_exact_success(
      runtime->dispatch("host.status", Json::object(), {}),
      {"state", "project_id", "project_revision", "pattern_id",
       "runtime_ready", "control_generation", "acknowledged_generation",
       "limits", "audio_state", "capture_state"});
  LMDJ_CHECK(status.at("project_id") == large_project);
  LMDJ_CHECK(status.at("runtime_ready") == false);
  check_error(
      runtime->dispatch("audio.activate", Json::object(), {}),
      "HOST_STATE_INVALID");
  check_error(
      runtime->dispatch(
          "trigger", {{"slot", 0}, {"velocity", 127}}, {}),
      "HOST_STATE_INVALID");
  LMDJ_CHECK(runtime->engine().bank_telemetry().current_generation == 1);
}

struct FakeProxy final {
  struct Task {
    void (*function)(void*) noexcept;
    void* argument;
  };

  static bool schedule(
      void* context,
      void (*function)(void*) noexcept,
      void* argument) noexcept {
    auto& self = *static_cast<FakeProxy*>(context);
    if (!self.accept) {
      return false;
    }
    self.tasks.push_back(Task{function, argument});
    return true;
  }

  static bool on_control(void* context) noexcept {
    return static_cast<FakeProxy*>(context)->is_control;
  }

  static void before_response_serialization(void* context) {
    auto& self = *static_cast<FakeProxy*>(context);
    if (std::exchange(self.throw_before_response_serialization, false)) {
      throw std::runtime_error("injected response serialization failure");
    }
  }

  void pump_one() {
    LMDJ_CHECK(!tasks.empty());
    auto task = tasks.front();
    tasks.erase(tasks.begin());
    is_control = true;
    task.function(task.argument);
    is_control = false;
  }

  bool accept = true;
  bool is_control = false;
  bool throw_before_response_serialization = false;
  std::vector<Task> tasks;
};

std::vector<std::byte> encode(const Json& value) {
  const auto encoded = value.dump();
  const auto* first = reinterpret_cast<const std::byte*>(encoded.data());
  return {first, first + encoded.size()};
}

Json request(
    std::string_view request_id,
    std::string_view operation,
    Json payload) {
  return {
      {"protocol_version", 1},
      {"request_id", request_id},
      {"operation", operation},
      {"payload", std::move(payload)},
  };
}

std::unique_ptr<ControlBridge> make_bridge(
    ControlRuntime& runtime,
    FakeProxy& proxy) {
  return std::make_unique<ControlBridge>(
      runtime,
      BridgeHooks{
          &proxy,
          FakeProxy::schedule,
          FakeProxy::on_control,
          FakeProxy::before_response_serialization});
}

Json poll_message(ControlBridge& bridge) {
  std::array<std::byte, kBridgeMaximumEnvelopeBytes> output{};
  std::size_t required = 0;
  LMDJ_CHECK(
      bridge.poll(output, required) == BridgePollStatus::message);
  LMDJ_CHECK(required <= output.size());
  const auto* first = reinterpret_cast<const char*>(output.data());
  return Json::parse(first, first + required);
}

void check_no_bridge_message(ControlBridge& bridge) {
  std::array<std::byte, kBridgeMaximumEnvelopeBytes> output{};
  std::size_t required = 1;
  LMDJ_CHECK(
      bridge.poll(output, required) == BridgePollStatus::empty);
  LMDJ_CHECK(required == 0);
}

void test_bridge_defers_parse_dispatch_and_copies_fixed_slots() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = std::string(kProtocolShapeRequestId);
  auto bytes = encode(request(request_id, "project.create", create_payload()));

  LMDJ_CHECK(
      bridge->submit(bytes, {}) == BridgeSubmitStatus::accepted);
  LMDJ_CHECK(proxy.tasks.size() == 1);
  LMDJ_CHECK(!std::filesystem::exists(
      temp.path() / "projects" /
      (std::string(kProjectId) + ".lmdj")));
  std::fill(bytes.begin(), bytes.end(), std::byte{'x'});
  proxy.pump_one();
  LMDJ_CHECK(std::filesystem::exists(
      temp.path() / "projects" /
      (std::string(kProjectId) + ".lmdj") / "manifest.json"));
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("protocol_version") == 1);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.contains("result"));
  LMDJ_CHECK(!response.contains("project_revision"));

  std::vector<std::byte> at_limit(kBridgeMaximumEnvelopeBytes, std::byte{'x'});
  std::vector<std::byte> over_limit(
      kBridgeMaximumEnvelopeBytes + 1, std::byte{'x'});
  LMDJ_CHECK(
      bridge->submit(over_limit, {}) ==
      BridgeSubmitStatus::envelope_too_large);
  std::vector<std::byte> sidecar(kBridgeMaximumSidecarBytes + 1);
  LMDJ_CHECK(
      bridge->submit(at_limit, sidecar) ==
      BridgeSubmitStatus::sidecar_too_large);
}

void test_bridge_rejects_duplicates_until_response_consumption() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(701);
  const auto bytes = encode(
      request(request_id, "host.status", Json::object()));

  LMDJ_CHECK(
      bridge->submit(bytes, {}) == BridgeSubmitStatus::accepted);
  LMDJ_CHECK(
      bridge->submit(bytes, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  LMDJ_CHECK(poll_message(*bridge).at("ok") == true);

  // B was admitted before A completed. Consuming A's response must enqueue
  // A's ID release behind B on the same Control FIFO, so B still observes the
  // duplicate even though the browser-main thread has already polled A.
  proxy.pump_one();
  const auto duplicate = poll_message(*bridge);
  LMDJ_CHECK(duplicate.at("ok") == false);
  LMDJ_CHECK(
      duplicate.at("error").at("code") == "HOST_PROTOCOL_MISMATCH");

  // Once the FIFO reaches both completed-request release tasks, the same ID
  // can be admitted again without an unbounded tombstone set.
  proxy.pump_one();
  proxy.pump_one();
  LMDJ_CHECK(
      bridge->submit(bytes, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  LMDJ_CHECK(poll_message(*bridge).at("ok") == true);
}

void test_bridge_response_backpressure_fails_before_mutation() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);

  for (std::size_t index = 0; index < kBridgeMessageSlotCount; ++index) {
    const auto bytes = encode(request(
        uuid(static_cast<std::uint32_t>(710 + index)),
        "host.status",
        Json::object()));
    LMDJ_CHECK(
        bridge->submit(bytes, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();
  }

  const auto create = encode(request(
      uuid(720), "project.create", create_payload()));
  LMDJ_CHECK(
      bridge->submit(create, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  LMDJ_CHECK(bridge->failed());
  LMDJ_CHECK(!std::filesystem::exists(
      temp.path() / "projects" /
      (std::string(kProjectId) + ".lmdj")));
}

void test_bridge_exception_reuses_the_reserved_response_slot() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);

  // Leave exactly one message slot free. The injected exception occurs only
  // after that final response slot has been reserved.
  for (std::size_t index = 0; index + 1 < kBridgeMessageSlotCount; ++index) {
    const auto bytes = encode(request(
        uuid(static_cast<std::uint32_t>(730 + index)),
        "host.status",
        Json::object()));
    LMDJ_CHECK(
        bridge->submit(bytes, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();
  }

  const auto failed_request_id = uuid(740);
  const auto failed_request = encode(request(
      failed_request_id, "host.status", Json::object()));
  proxy.throw_before_response_serialization = true;
  LMDJ_CHECK(
      bridge->submit(failed_request, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();

  for (std::size_t index = 0; index + 1 < kBridgeMessageSlotCount; ++index) {
    LMDJ_CHECK(poll_message(*bridge).at("ok") == true);
  }
  const auto fallback = poll_message(*bridge);
  LMDJ_CHECK(fallback.at("request_id") == failed_request_id);
  LMDJ_CHECK(fallback.at("ok") == false);
  LMDJ_CHECK(fallback.at("error").at("code") == "INTERNAL_ERROR");
  LMDJ_CHECK(bridge->failed());
}

void test_bridge_release_proxy_failure_is_a_terminal_transport_signal() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto bytes = encode(request(
      uuid(741), "host.status", Json::object()));

  LMDJ_CHECK(
      bridge->submit(bytes, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  proxy.accept = false;
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(bridge->failed());
  LMDJ_CHECK(proxy.tasks.empty());
  LMDJ_CHECK(
      bridge->submit(bytes, {}) == BridgeSubmitStatus::queue_full);

  std::array<std::byte, kBridgeMaximumEnvelopeBytes> output{};
  std::size_t required = 1;
  LMDJ_CHECK(
      bridge->poll(output, required) == BridgePollStatus::failed);
  LMDJ_CHECK(required == 0);
  // Control is unreachable, so Task 8 must terminate the Worker; this
  // browser-main failure path deliberately performs no Facade cleanup here.
}

void test_bridge_emits_only_real_snapshot_notifications_after_response() {
  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    FakeProxy proxy;
    auto bridge = make_bridge(*runtime, proxy);

    const auto malformed = encode(request(
        uuid(901),
        "project.open",
        {{"project_id", kProjectId}}));
    LMDJ_CHECK(
        bridge->submit(malformed, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();
    const auto malformed_response = poll_message(*bridge);
    LMDJ_CHECK(malformed_response.at("ok") == false);
    LMDJ_CHECK(
        malformed_response.at("error").at("code") ==
        "HOST_PROTOCOL_MISMATCH");
    check_no_bridge_message(*bridge);
    proxy.pump_one();

    const auto wrong_state = encode(request(
        uuid(902),
        "snapshot.reload",
        {{"pattern_id", kPatternId}}));
    LMDJ_CHECK(
        bridge->submit(wrong_state, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();
    const auto state_response = poll_message(*bridge);
    LMDJ_CHECK(state_response.at("ok") == false);
    LMDJ_CHECK(
        state_response.at("error").at("code") == "HOST_STATE_INVALID");
    check_no_bridge_message(*bridge);
  }

  {
    TempDirectory temp;
    auto owner = make_runtime(temp.path());
    check_success(owner->dispatch(
        "project.create", create_payload(), {}));
    auto contender = make_runtime(temp.path());
    FakeProxy proxy;
    auto bridge = make_bridge(*contender, proxy);
    const auto open = encode(request(
        uuid(903),
        "project.open",
        {{"project_id", kProjectId}, {"pattern_id", kPatternId}}));
    LMDJ_CHECK(
        bridge->submit(open, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();
    const auto busy = poll_message(*bridge);
    LMDJ_CHECK(busy.at("ok") == false);
    LMDJ_CHECK(busy.at("error").at("code") == "PROJECT_BUSY");
    check_no_bridge_message(*bridge);
  }

  {
    TempDirectory temp;
    constexpr RuntimePreparationLimits limits{
        1'048'576,
        1,
        4,
        8,
    };
    auto runtime = make_runtime(temp.path(), limits);
    check_success(runtime->dispatch(
        "project.create", create_payload(), {}));
    const auto oversized = mono_pcm16_wav(2);
    import_and_assign(*runtime, oversized, kAssetId, 911, 912, 0);
    FakeProxy proxy;
    auto bridge = make_bridge(*runtime, proxy);
    const auto request_id = uuid(904);
    const auto open = encode(request(
        request_id,
        "project.open",
        {{"project_id", kProjectId}, {"pattern_id", kPatternId}}));
    LMDJ_CHECK(
        bridge->submit(open, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();

    const auto response = poll_message(*bridge);
    LMDJ_CHECK(response.at("request_id") == request_id);
    LMDJ_CHECK(response.at("ok") == true);
    LMDJ_CHECK(response.at("result").at("runtime_ready") == false);
    LMDJ_CHECK(
        response.at("result").at("snapshot_error").at("code") ==
        "WEB_RUNTIME_RESOURCE_LIMIT");

    const auto notification = poll_message(*bridge);
    check_exact_keys(
        notification, {"protocol_version", "event", "payload"});
    LMDJ_CHECK(notification.at("event") == "snapshot.rejected");
    LMDJ_CHECK(!notification.contains("request_id"));
    LMDJ_CHECK(
        notification.at("payload").at("error").at("code") ==
        "WEB_RUNTIME_RESOURCE_LIMIT");
    check_no_bridge_message(*bridge);
  }
}

}  // namespace

int main() {
  try {
    test_facade_error_details_follow_an_explicit_safe_schema();
    test_exact_payloads_and_facade_owned_project_journey();
    test_take_stop_drains_the_final_disarm_quantum();
    test_audio_suspend_requires_and_honors_quiescence_coordinator();
    test_host_close_orders_capture_seal_quiescence_and_engine_stop();
    test_exact_non_fifo_aggregate_accounting_and_prior_bank_retention();
    test_oversized_project_switch_is_inspectable_but_not_runnable();
    test_bridge_defers_parse_dispatch_and_copies_fixed_slots();
    test_bridge_rejects_duplicates_until_response_consumption();
    test_bridge_response_backpressure_fails_before_mutation();
    test_bridge_exception_reuses_the_reserved_response_slot();
    test_bridge_release_proxy_failure_is_a_terminal_transport_signal();
    test_bridge_emits_only_real_snapshot_notifications_after_response();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "web control runtime tests: PASS\n";
  return 0;
}
