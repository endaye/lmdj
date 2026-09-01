#include <lmdj/web_runtime/control_runtime.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <source_location>
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
#include <lmdj/facade/mutation_publish_scope.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>

#include "tests/core/support/test.hpp"
#include "testing_hooks.hpp"

namespace lmdj::web_runtime::detail {
nlohmann::json normalize_error_for_testing(
    const foundation::Error& error);
}

namespace {

using Json = nlohmann::json;
using lmdj::audio::BankTelemetry;
using lmdj::audio::CaptureState;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RuntimePreparationLimits;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;
using lmdj::web_runtime::ControlRuntime;
using lmdj::web_runtime::detail::AudioQuiescenceCoordinator;
using lmdj::web_runtime::detail::BridgeCancelStatus;
using lmdj::web_runtime::detail::BridgeHooks;
using lmdj::web_runtime::detail::BridgePollStatus;
using lmdj::web_runtime::detail::BridgeSubmitStatus;
using lmdj::web_runtime::detail::ControlBridge;
using lmdj::web_runtime::detail::ControlRuntimeAudioAccess;
using lmdj::web_runtime::detail::ControlRuntimeClock;
using lmdj::web_runtime::detail::ControlRuntimeClockAccess;
using lmdj::web_runtime::detail::kBridgeMaximumEnvelopeBytes;
using lmdj::web_runtime::detail::kBridgeMaximumSidecarBytes;
using lmdj::web_runtime::detail::kBridgeMessageSlotCount;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kPatternId =
    "00000000-0000-4000-8000-000000000010";
constexpr std::string_view kNextPatternId =
    "00000000-0000-4000-8000-000000000011";
constexpr std::string_view kAssetId =
    "00000000-0000-4000-8000-000000000101";
constexpr std::string_view kSequenceSessionId =
    "00000000-0000-4000-8000-000000000201";
constexpr std::string_view kProtocolShapeRequestId =
    "01234567-89ab-cdef-0123-456789abcdef";

constexpr RuntimePreparationLimits kWebLimits{
    68'157'440,
    67'108'864,
    134'217'728,
    268'435'456,
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

Application make_application(
    const std::filesystem::path& root,
    RuntimePreparationLimits limits = kWebLimits) {
  return Application(ApplicationConfig{
      root,
      std::make_shared<Registry>(),
      ProviderPolicy{},
      [] { return std::string("2026-08-04T00:00:00.000Z"); },
      limits,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  });
}

std::unique_ptr<ControlRuntime> make_runtime(
    const std::filesystem::path& root,
    RuntimePreparationLimits limits = kWebLimits) {
  auto created = ControlRuntime::create(
      root, make_application(root, limits), limits);
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

std::vector<std::byte> mono_pcm16_wav(
    std::uint32_t frames,
    std::uint32_t sample_rate = 48'000) {
  const auto data_bytes = frames * 2U;
  std::vector<std::byte> bytes(44U + data_bytes);
  write_tag(bytes, 0, "RIFF");
  write_u32(bytes, 4, 36U + data_bytes);
  write_tag(bytes, 8, "WAVE");
  write_tag(bytes, 12, "fmt ");
  write_u32(bytes, 16, 16);
  write_u16(bytes, 20, 1);
  write_u16(bytes, 22, 1);
  write_u32(bytes, 24, sample_rate);
  write_u32(bytes, 28, sample_rate * 2U);
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

std::string sha256(std::string_view text) {
  return sha256(std::span<const std::byte>{
      reinterpret_cast<const std::byte*>(text.data()), text.size()});
}

std::vector<std::byte> read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  LMDJ_CHECK(stream.good());
  const std::string text{
      std::istreambuf_iterator<char>{stream},
      std::istreambuf_iterator<char>{}};
  return {
      reinterpret_cast<const std::byte*>(text.data()),
      reinterpret_cast<const std::byte*>(text.data() + text.size()),
  };
}

struct ProjectBundleFixture {
  std::string index;
  std::vector<std::vector<std::byte>> entries;
  std::string digest;
};

ProjectBundleFixture build_project_bundle_fixture(
    const std::filesystem::path& source,
    std::string_view project_id) {
  struct SourceEntry {
    std::string path;
    std::vector<std::byte> bytes;
  };
  std::vector<SourceEntry> source_entries;
  for (const auto& entry :
       std::filesystem::recursive_directory_iterator(source)) {
    LMDJ_CHECK(!entry.is_symlink());
    if (!entry.is_regular_file()) {
      continue;
    }
    source_entries.push_back({
        std::filesystem::relative(entry.path(), source).generic_string(),
        read_bytes(entry.path()),
    });
  }
  std::sort(
      source_entries.begin(),
      source_entries.end(),
      [](const auto& left, const auto& right) {
        return std::lexicographical_compare(
            left.path.begin(),
            left.path.end(),
            right.path.begin(),
            right.path.end(),
            [](char left_byte, char right_byte) {
              return static_cast<unsigned char>(left_byte) <
                     static_cast<unsigned char>(right_byte);
            });
      });

  auto encoded_entries = Json::array();
  std::uint64_t offset = 0;
  std::vector<std::vector<std::byte>> payloads;
  for (auto& entry : source_entries) {
    encoded_entries.push_back({
        {"bytes", entry.bytes.size()},
        {"offset", offset},
        {"path", entry.path},
        {"sha256", sha256(entry.bytes)},
    });
    offset += entry.bytes.size();
    payloads.push_back(std::move(entry.bytes));
  }
  Json index{
      {"bundle_digest", std::string(64, '0')},
      {"compression", "none"},
      {"contract", "lmdj.project-bundle.v1"},
      {"contract_version", "1.1.0"},
      {"entries", std::move(encoded_entries)},
      {"project_contract", "lmdj.project.v3"},
      {"project_id", project_id},
      {"uncompressed_bytes", offset},
  };
  auto digest_source = index;
  digest_source.erase("bundle_digest");
  const auto digest = sha256(
      lmdj::foundation::canonical_json(digest_source));
  index["bundle_digest"] = digest;
  return {
      lmdj::foundation::canonical_json(index),
      std::move(payloads),
      digest,
  };
}

Json sidecar_declaration(std::span<const std::byte> bytes) {
  return {
      {"sidecar_bytes", bytes.size()},
      {"sidecar_sha256", sha256(bytes)},
  };
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

Json playback_payload(
    std::uint64_t start,
    std::optional<std::uint64_t> end,
    std::string_view mode = "one_shot",
    std::int32_t gain_millidb = 0,
    bool muted = false) {
  return {
      {"trim_start_frame", start},
      {"trim_end_frame", end.has_value() ? Json(*end) : Json(nullptr)},
      {"trigger_mode", mode},
      {"gain_millidb", gain_millidb},
      {"muted", muted},
  };
}

Json sample_begin_payload(
    std::uint32_t token_suffix,
    std::uint32_t command_suffix,
    std::uint64_t expected_revision,
    std::string_view asset_id,
    std::size_t byte_length,
    std::uint8_t pad = 0) {
  return {
      {"import_token", uuid(token_suffix)},
      {"command_id", uuid(command_suffix)},
      {"expected_revision", expected_revision},
      {"slot", slot(0, pad)},
      {"asset_id", asset_id},
      {"byte_length", byte_length},
  };
}

Json sample_chunk_payload(
    std::uint32_t token_suffix,
    std::uint64_t offset,
    bool final,
    std::span<const std::byte> bytes) {
  return {
      {"import_token", uuid(token_suffix)},
      {"offset", offset},
      {"final", final},
      {"sidecar", sidecar_declaration(bytes)},
  };
}

void check_success(
    const Json& response,
    const std::source_location& location = std::source_location::current()) {
  LMDJ_CHECK(response.is_object());
  LMDJ_CHECK(response.size() == 2);
  if (response.at("ok") != true) {
    throw std::runtime_error(
        std::string(location.file_name()) + ":" +
        std::to_string(location.line()) +
        ": unexpected control response: " + response.dump());
  }
  LMDJ_CHECK(response.contains("result"));
}

Json check_locked_success_result(
    const Json& response,
    const std::source_location& location = std::source_location::current()) {
  check_success(response, location);
  LMDJ_CHECK(response.at("result").is_object());
  return response.at("result");
}

Json check_error(const Json& response, std::string_view code) {
  LMDJ_CHECK(response.is_object());
  LMDJ_CHECK(response.size() == 2);
  LMDJ_CHECK(response.at("ok") == false);
  if (response.at("error").at("code") != code) {
    throw std::runtime_error(
        "unexpected response error, wanted " + std::string(code) + ": " +
        response.dump());
  }
  LMDJ_CHECK(response.at("error").at("message").is_string());
  LMDJ_CHECK(response.at("error").at("details").is_object());
  return response.at("error");
}

void check_exact_keys(
    const Json& value,
    std::initializer_list<std::string_view> keys) {
  LMDJ_CHECK(value.is_object());
  if (value.size() != keys.size()) {
    throw std::runtime_error(
        "exact response key count mismatch: " + value.dump());
  }
  for (const auto key : keys) {
    LMDJ_CHECK(value.contains(std::string(key)));
  }
}

Json check_exact_success(
    const Json& response,
    std::initializer_list<std::string_view> keys,
    const std::source_location& location = std::source_location::current()) {
  const auto& result = check_locked_success_result(response, location);
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

  bool stopped() const noexcept {
    return !running_.load(std::memory_order_acquire);
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

struct FakeRuntimeClock final {
  static std::chrono::steady_clock::time_point now(void* context) noexcept {
    auto& self = *static_cast<FakeRuntimeClock*>(context);
    ++self.reads;
    if (self.cross_deadline_on_read.has_value() &&
        self.reads == *self.cross_deadline_on_read) {
      self.current += std::chrono::seconds(31);
    }
    return self.current;
  }

  ControlRuntimeClock seam() noexcept {
    return ControlRuntimeClock{this, &FakeRuntimeClock::now};
  }

  std::chrono::steady_clock::time_point current{
      std::chrono::seconds(100)};
  std::uint64_t reads = 0;
  std::optional<std::uint64_t> cross_deadline_on_read;
};

struct CommitDeadlineCrossing final {
  static bool claim(void*) noexcept { return true; }

  static void commit(void* context) noexcept {
    auto& self = *static_cast<CommitDeadlineCrossing*>(context);
    self.clock.current += std::chrono::seconds(31);
  }

  static void abort(void*) noexcept {}

  static bool force_failure(void*) noexcept { return false; }

  lmdj::facade::detail::MutationPublishToken token() noexcept {
    return {
        this,
        &CommitDeadlineCrossing::claim,
        &CommitDeadlineCrossing::commit,
        &CommitDeadlineCrossing::abort,
        &CommitDeadlineCrossing::force_failure,
    };
  }

  FakeRuntimeClock& clock;
};

struct FakeCoordinator final {
  static lmdj::foundation::Result<void> begin(void* context) noexcept {
    auto& self = *static_cast<FakeCoordinator*>(context);
    ++self.begin_calls;
    if (self.begin_delay_ms != 0) {
      std::this_thread::sleep_for(
          std::chrono::milliseconds(self.begin_delay_ms));
    }
    self.acknowledged_before_begin = self.acknowledged;
    self.acknowledged = self.begin_stale_acknowledgement;
    if (!self.begin_succeed) {
      return lmdj::foundation::Result<void>::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::internal_error,
              "fake begin failure",
          });
    }
    if (self.acknowledgement_delay_polls == 0) {
      self.acknowledged = self.begin_acknowledgement;
    }
    return lmdj::foundation::Result<void>::success();
  }

  static lmdj::foundation::Result<void> await(
      void* context, std::uint32_t timeout_ms) noexcept {
    auto& self = *static_cast<FakeCoordinator*>(context);
    self.called = true;
    ++self.await_calls;
    self.timeout_ms = timeout_ms;
    if (self.await_delay_ms != 0) {
      std::this_thread::sleep_for(
          std::chrono::milliseconds(self.await_delay_ms));
    }
    if (self.render_during_await && self.engine != nullptr) {
      std::array<float, 128> left{};
      std::array<float, 128> right{};
      self.engine->render(left.data(), right.data(), 128);
    }
    if (self.driver != nullptr && self.engine != nullptr) {
      const auto deadline = std::chrono::steady_clock::now() +
                            std::chrono::seconds(1);
      auto capture = self.engine->capture_telemetry().state;
      while (capture != CaptureState::idle &&
             capture != CaptureState::corrupted &&
             std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
        capture = self.engine->capture_telemetry().state;
      }
    }
    if (self.driver != nullptr) {
      self.driver->stop();
    }
    if (self.engine != nullptr) {
      self.observed_capture_idle =
          self.engine->capture_telemetry().state == CaptureState::idle;
      self.observed_engine_running =
          self.engine->telemetry().state ==
          lmdj::audio::RealtimeState::running;
    }
    self.quiescence_established =
        self.driver == nullptr || self.driver->stopped();
    if (self.engine != nullptr) {
      self.callback_count_at_quiescence =
          self.engine->telemetry().callback_count;
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

  static bool ready(void* context) noexcept {
    return static_cast<FakeCoordinator*>(context)->is_ready;
  }

  static std::uint64_t acknowledged_generation(void* context) noexcept {
    auto& self = *static_cast<FakeCoordinator*>(context);
    ++self.acknowledgement_calls;
    if (self.acknowledgement_poll_delay_ms != 0) {
      std::this_thread::sleep_for(
          std::chrono::milliseconds(self.acknowledgement_poll_delay_ms));
    }
    if (self.acknowledgement_delay_polls != 0 &&
        ++self.acknowledgement_polls >= self.acknowledgement_delay_polls) {
      self.acknowledged = self.begin_acknowledgement;
    }
    if (self.observe_engine_generation && self.engine != nullptr) {
      self.acknowledged =
          self.engine->bank_telemetry().current_generation;
    }
    return self.acknowledged;
  }

  AudioQuiescenceCoordinator seam() noexcept {
    return AudioQuiescenceCoordinator{
        this,
        &FakeCoordinator::await,
        &FakeCoordinator::begin,
        &FakeCoordinator::ready,
        &FakeCoordinator::acknowledged_generation,
    };
  }

  ContinuousAudioDriver* driver = nullptr;
  RealtimeEngine* engine = nullptr;
  bool succeed = true;
  bool begin_succeed = true;
  bool is_ready = true;
  bool timeout = false;
  bool called = false;
  bool render_during_await = false;
  bool observe_engine_generation = false;
  bool observed_capture_idle = false;
  bool observed_engine_running = false;
  bool quiescence_established = false;
  std::uint64_t callback_count_at_quiescence = 0;
  std::uint32_t timeout_ms = 0;
  std::uint32_t await_delay_ms = 0;
  std::uint32_t begin_delay_ms = 0;
  std::uint64_t acknowledged = 0;
  std::uint64_t acknowledged_before_begin = 0;
  std::uint64_t begin_stale_acknowledgement = 0;
  std::uint64_t begin_acknowledgement = 1;
  std::uint32_t begin_calls = 0;
  std::uint32_t await_calls = 0;
  std::uint32_t acknowledgement_calls = 0;
  std::uint32_t acknowledgement_delay_polls = 0;
  std::uint32_t acknowledgement_polls = 0;
  std::uint32_t acknowledgement_poll_delay_ms = 0;
};

struct OneShotAudioBackend final {
  void* context;
  BankTelemetry (*bank_telemetry)(void* context) noexcept;
  void (*render)(
      void* context,
      float* left,
      float* right,
      std::uint32_t frames) noexcept;
};

class OneShotAudioDriver final {
 public:
  explicit OneShotAudioDriver(RealtimeEngine& engine)
      : OneShotAudioDriver(OneShotAudioBackend{
            &engine,
            [](void* context) noexcept {
              return static_cast<RealtimeEngine*>(context)->bank_telemetry();
            },
            [](void* context,
               float* left,
               float* right,
               std::uint32_t frames) noexcept {
              static_cast<RealtimeEngine*>(context)->render(
                  left, right, frames);
            },
        }) {}

  explicit OneShotAudioDriver(OneShotAudioBackend backend)
      : backend_(backend) {
    LMDJ_CHECK(backend_.context != nullptr);
    LMDJ_CHECK(backend_.bank_telemetry != nullptr);
    LMDJ_CHECK(backend_.render != nullptr);
    thread_ = std::thread([this] { run(); });
  }

  ~OneShotAudioDriver() {
    stop_requested_.store(true, std::memory_order_release);
    {
      std::lock_guard lock(mutex_);
      stopped_ = true;
    }
    changed_.notify_all();
    if (thread_.joinable()) {
      thread_.join();
    }
  }

  void render_one() { render_frames(128); }

  void render_frames(std::uint32_t frame_count) {
    LMDJ_CHECK(frame_count > 0 && frame_count <= 128);
    std::unique_lock lock(mutex_);
    const auto target = completed_ + 1;
    frame_count_ = frame_count;
    ++permits_;
    changed_.notify_all();
    changed_.wait(lock, [this, target] { return completed_ >= target; });
  }

  void schedule_one() {
    std::lock_guard lock(mutex_);
    ++permits_;
    changed_.notify_all();
  }

  void schedule_bank_transition() {
    const auto target_generation =
        backend_.bank_telemetry(backend_.context).accepted_publications + 1;
    LMDJ_CHECK(target_generation != 0);
    std::lock_guard lock(mutex_);
    if (bank_transition_target_generation_ != 0) {
      throw std::runtime_error(
          "one-shot bank transition already in flight");
    }
    ++permits_;
    ++bank_transition_permits_;
    bank_transition_target_generation_ = target_generation;
    changed_.notify_all();
  }

 private:
  void run() noexcept {
    std::array<float, 128> left{};
    std::array<float, 128> right{};
    while (true) {
      bool wait_for_bank_transition = false;
      std::uint64_t bank_transition_target_generation = 0;
      std::uint32_t frame_count = 128;
      {
        std::unique_lock lock(mutex_);
        changed_.wait(lock, [this] { return stopped_ || permits_ != 0; });
        if (stopped_) {
          return;
        }
        --permits_;
        frame_count = frame_count_;
        frame_count_ = 128;
        if (bank_transition_permits_ != 0) {
          --bank_transition_permits_;
          wait_for_bank_transition = true;
          bank_transition_target_generation =
              bank_transition_target_generation_;
        }
      }
      while (wait_for_bank_transition &&
             backend_.bank_telemetry(backend_.context)
                     .accepted_publications <
                 bank_transition_target_generation &&
             !stop_requested_.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      if (stop_requested_.load(std::memory_order_acquire)) {
        return;
      }
      do {
        backend_.render(
            backend_.context, left.data(), right.data(), frame_count);
        if (!wait_for_bank_transition ||
            backend_.bank_telemetry(backend_.context)
                    .applied_publications >=
                bank_transition_target_generation) {
          break;
        }
        std::this_thread::yield();
      } while (!stop_requested_.load(std::memory_order_acquire));
      if (stop_requested_.load(std::memory_order_acquire)) {
        return;
      }
      {
        std::lock_guard lock(mutex_);
        if (wait_for_bank_transition) {
          bank_transition_target_generation_ = 0;
        }
        ++completed_;
      }
      changed_.notify_all();
    }
  }

  OneShotAudioBackend backend_;
  std::mutex mutex_;
  std::condition_variable changed_;
  std::size_t permits_ = 0;
  std::size_t bank_transition_permits_ = 0;
  std::uint64_t bank_transition_target_generation_ = 0;
  std::size_t completed_ = 0;
  std::uint32_t frame_count_ = 128;
  std::atomic<bool> stop_requested_{false};
  bool stopped_ = false;
  std::thread thread_;
};

struct DeterministicBankTransitionBackend final {
  static BankTelemetry bank_telemetry(void* context) noexcept {
    auto& self = *static_cast<DeterministicBankTransitionBackend*>(context);
    self.telemetry_reads.fetch_add(1, std::memory_order_release);
    return BankTelemetry{
        1,
        self.pending_publications.load(std::memory_order_acquire),
        self.accepted_publications.load(std::memory_order_acquire),
        self.applied_publications.load(std::memory_order_acquire),
        0,
        0,
        0,
    };
  }

  static void render(
      void* context,
      float*,
      float*,
      std::uint32_t) noexcept {
    auto& self = *static_cast<DeterministicBankTransitionBackend*>(context);
    const auto render_call =
        self.render_calls.fetch_add(1, std::memory_order_acq_rel) + 1;
    if (render_call == self.apply_on_render_call) {
      self.applied_publications.store(
          self.accepted_publications.load(std::memory_order_acquire),
          std::memory_order_release);
    }
  }

  OneShotAudioBackend backend() noexcept {
    return OneShotAudioBackend{
        this,
        &DeterministicBankTransitionBackend::bank_telemetry,
        &DeterministicBankTransitionBackend::render,
    };
  }

  std::atomic<std::uint64_t> pending_publications{1};
  std::atomic<std::uint64_t> accepted_publications{1};
  std::atomic<std::uint64_t> applied_publications{1};
  std::atomic<std::uint64_t> telemetry_reads{0};
  std::atomic<std::uint64_t> render_calls{0};
  std::uint64_t apply_on_render_call = 1;
};

void test_one_shot_bank_transition_waits_for_accepted_queue_commit() {
  DeterministicBankTransitionBackend backend;
  {
    OneShotAudioDriver audio(backend.backend());
    audio.schedule_bank_transition();
    wait_until([&] {
      return backend.telemetry_reads.load(std::memory_order_acquire) >= 2;
    });
    LMDJ_CHECK(backend.render_calls.load(std::memory_order_acquire) == 0);

    backend.accepted_publications.store(2, std::memory_order_release);
    wait_until([&] {
      return backend.applied_publications.load(std::memory_order_acquire) == 2;
    });
  }
  LMDJ_CHECK(backend.render_calls.load(std::memory_order_acquire) == 1);
}

void test_one_shot_bank_transition_renders_until_target_is_applied() {
  DeterministicBankTransitionBackend backend;
  backend.apply_on_render_call = 2;
  {
    OneShotAudioDriver audio(backend.backend());
    audio.schedule_bank_transition();
    wait_until([&] {
      return backend.telemetry_reads.load(std::memory_order_acquire) >= 2;
    });
    backend.accepted_publications.store(2, std::memory_order_release);
    wait_until([&] {
      return backend.applied_publications.load(std::memory_order_acquire) == 2;
    });
  }
  LMDJ_CHECK(backend.render_calls.load(std::memory_order_acquire) == 2);
}

void test_one_shot_bank_transition_rejects_overlap_until_completion() {
  DeterministicBankTransitionBackend backend;
  {
    OneShotAudioDriver audio(backend.backend());
    audio.schedule_bank_transition();
    wait_until([&] {
      return backend.telemetry_reads.load(std::memory_order_acquire) >= 2;
    });

    bool rejected = false;
    try {
      audio.schedule_bank_transition();
    } catch (const std::runtime_error& error) {
      rejected = std::string_view(error.what()) ==
          "one-shot bank transition already in flight";
    }
    LMDJ_CHECK(rejected);
  }
  LMDJ_CHECK(backend.render_calls.load(std::memory_order_acquire) == 0);
}

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
      lmdj::web_runtime::detail::normalize_error_for_testing(
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

  check_error(
      lmdj::web_runtime::detail::normalize_error_for_testing(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::invalid_project,
              "Project Bundle entry exceeds 64 MiB",
              {{"transfer_condition", "resource_limit"}},
          }),
      "WEB_RUNTIME_RESOURCE_LIMIT");
  check_error(
      lmdj::web_runtime::detail::normalize_error_for_testing(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::io_error,
              "atomic publish failed",
              {{"storage_condition", "atomic_publish_unsupported"}},
          }),
      "UNSUPPORTED_WEB_RUNTIME");
  check_error(
      lmdj::web_runtime::detail::normalize_error_for_testing(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::io_error,
              "destination appeared",
              {{"storage_condition", "already_exists"}},
          }),
      "DUPLICATE_ID");
}

void test_project_bundle_stream_delegates_to_facade_and_lists_summary() {
  TempDirectory temp;
  const auto source_root = temp.path() / "source";
  const auto target_root = temp.path() / "target";
  std::filesystem::create_directories(source_root);
  std::filesystem::create_directories(target_root);
  {
    auto builder = make_runtime(source_root);
    check_success(builder->dispatch(
        "project.create", create_payload(), {}));
  }
  const auto fixture = build_project_bundle_fixture(
      source_root / "projects" /
          (std::string(kProjectId) + ".lmdj"),
      kProjectId);
  const auto index_bytes = std::span<const std::byte>{
      reinterpret_cast<const std::byte*>(fixture.index.data()),
      fixture.index.size(),
  };
  auto runtime = make_runtime(target_root);

  auto listed = check_locked_success_result(
      runtime->dispatch("project.list", Json::object(), {}));
  check_exact_keys(listed, {"projects"});
  LMDJ_CHECK(listed.at("projects") == Json::array());

  const auto token = uuid(601);
  auto begun = check_locked_success_result(runtime->dispatch(
      "project.import.begin",
      {
          {"import_token", token},
          {"index_bytes", fixture.index.size()},
          {"index_sha256", sha256(fixture.index)},
      },
      {}));
  check_exact_keys(begun, {"import_token", "expected_index_bytes"});
  LMDJ_CHECK(begun.at("import_token") == token);
  LMDJ_CHECK(begun.at("expected_index_bytes") == fixture.index.size());

  const auto identity = check_locked_success_result(runtime->dispatch(
      "project.import.index",
      {
          {"import_token", token},
          {"offset", 0},
          {"final", true},
          {"sidecar", sidecar_declaration(index_bytes)},
      },
      index_bytes));
  check_exact_keys(identity, {"project_id", "bundle_digest", "entry_count"});
  LMDJ_CHECK(identity.at("project_id") == kProjectId);
  LMDJ_CHECK(identity.at("bundle_digest") == fixture.digest);
  LMDJ_CHECK(identity.at("entry_count") == fixture.entries.size());

  for (std::size_t entry_index = 0;
       entry_index < fixture.entries.size();
       ++entry_index) {
    const auto& entry = fixture.entries.at(entry_index);
    const auto result = check_locked_success_result(runtime->dispatch(
        "project.import.entry",
        {
            {"import_token", token},
            {"entry_index", entry_index},
            {"offset", 0},
            {"final", true},
            {"sidecar", sidecar_declaration(entry)},
        },
        entry));
    check_exact_keys(
        result, {"entry_index", "received_entry_bytes", "final"});
    LMDJ_CHECK(result.at("entry_index") == entry_index);
    LMDJ_CHECK(result.at("received_entry_bytes") == entry.size());
    LMDJ_CHECK(result.at("final") == true);
  }

  const auto committed = check_locked_success_result(runtime->dispatch(
      "project.import.commit", {{"import_token", token}}, {}));
  check_exact_keys(
      committed,
      {"project_id", "pattern_id", "revision", "bpm", "asset_count",
       "assigned_pad_count", "bundle_digest"});
  LMDJ_CHECK(committed.at("project_id") == kProjectId);
  LMDJ_CHECK(committed.at("pattern_id") == kPatternId);
  LMDJ_CHECK(committed.at("revision") == 0);
  LMDJ_CHECK(committed.at("bundle_digest") == fixture.digest);

  listed = check_locked_success_result(
      runtime->dispatch("project.list", Json::object(), {}));
  LMDJ_CHECK(listed.at("projects").size() == 1);
  LMDJ_CHECK(listed.at("projects").front() == committed);

  const auto mismatch_token = uuid(602);
  check_success(runtime->dispatch(
      "project.import.begin",
      {
          {"import_token", mismatch_token},
          {"index_bytes", fixture.index.size()},
          {"index_sha256", sha256(fixture.index)},
      },
      {}));
  check_error(runtime->dispatch(
      "project.import.index",
      {
          {"import_token", mismatch_token},
          {"offset", 1},
          {"final", true},
          {"sidecar", sidecar_declaration(index_bytes)},
      },
      index_bytes),
      "INVALID_PROJECT");
  const auto aborted = check_locked_success_result(runtime->dispatch(
      "project.import.abort", {{"import_token", mismatch_token}}, {}));
  LMDJ_CHECK((aborted == Json{{"aborted", true}}));
}

void test_host_close_aborts_active_project_bundle_import() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  const auto token = uuid(603);
  check_success(runtime->dispatch(
      "project.import.begin",
      {
          {"import_token", token},
          {"index_bytes", 1},
          {"index_sha256", sha256("x")},
      },
      {}));
  const auto staging = temp.path() / ".lmdj-host" / "import-staging" /
                       token;
  LMDJ_CHECK(std::filesystem::exists(staging));

  const auto& closed = check_exact_success(
      runtime->dispatch("host.close", Json::object(), {}),
      {"state", "stopped_sequence_id"});
  LMDJ_CHECK((closed == Json{{"state", "closed"}, {"stopped_sequence_id", nullptr}}));
  LMDJ_CHECK(!std::filesystem::exists(staging));
}

void test_runtime_cancellation_precedes_project_mutation() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  const auto expired = std::chrono::steady_clock::now() -
                       std::chrono::seconds(31);
  check_error(
      runtime->dispatch(
          "project.create", create_payload(), {}, expired),
      "HOST_TIMEOUT");
  LMDJ_CHECK(!std::filesystem::exists(
      temp.path() / "projects" /
      (std::string(kProjectId) + ".lmdj")));
  check_error(
      runtime->dispatch("host.status", Json::object(), {}),
      "HOST_STATE_INVALID");
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
          {"maximum_user_bank_bytes", kWebLimits.maximum_user_bank_bytes},
          {"maximum_generation_bytes", kWebLimits.maximum_generation_bytes},
          {"maximum_resident_bytes", kWebLimits.maximum_resident_bytes},
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

  FakeCoordinator activation_coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(
          *runtime, activation_coordinator.seam())
          .has_value());
  const auto& activated = check_exact_success(
      runtime->dispatch("audio.activate", Json::object(), {}),
      {"state", "changed", "generation"});
  LMDJ_CHECK((
      activated ==
      Json{{"state", "running"}, {"changed", true}, {"generation", 1}}));
  const auto& begun = check_exact_success(
      runtime->dispatch(
          "sequence.record.begin",
          {{"session_id", kSequenceSessionId},
           {"pattern_id", kPatternId},
           {"expected_revision", 2},
           {"armed_capture_slot", slot(0, 1)}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "transport_anchor"});
  LMDJ_CHECK(begun.at("state") == "active");
  LMDJ_CHECK(begun.at("session_id") == kSequenceSessionId);
  LMDJ_CHECK(begun.at("pattern_id") == kPatternId);
  LMDJ_CHECK(begun.at("project_revision") == 2);
  LMDJ_CHECK(begun.at("transport_anchor").at("bpm") == 120);
  const auto& trigger = check_exact_success(
      runtime->dispatch(
          "trigger", {{"slot", 0}, {"velocity", 100}}, {}),
      {"sequence", "status"});
  LMDJ_CHECK(trigger.at("sequence") == 1);
  LMDJ_CHECK(trigger.at("status") == "enqueued");
  check_exact_success(
      runtime->dispatch(
          "trigger", {{"slot", 0}, {"kind", "release"}}, {}),
      {"accepted"});
  const auto captured_asset_id = uuid(304);
  const auto capture_token = uuid(305);
  auto capture_begin = sample_begin_payload(
      305, 306, 2, captured_asset_id, wav.size(), 1);
  capture_begin["sequence_session_id"] = kSequenceSessionId;
  check_exact_success(
      runtime->dispatch("sample.import.begin", capture_begin, {}),
      {"token", "expected_bytes"});
  check_exact_success(
      runtime->dispatch(
          "sample.import.chunk", sample_chunk_payload(305, 0, true, wav), wav),
      {"received_bytes", "final"});
  const auto& capture_committed = check_exact_success(
      runtime->dispatch(
          "sample.import.commit", {{"import_token", capture_token}}, {}),
      {"committed_revision", "runtime_revision", "runtime_published",
       "snapshot_error"});
  LMDJ_CHECK(capture_committed.at("committed_revision") == 3);
  LMDJ_CHECK(capture_committed.at("runtime_revision") == 2);
  LMDJ_CHECK(capture_committed.at("runtime_published") == false);
  const auto& rebased = check_exact_success(
      runtime->dispatch("sequence.record.status", Json::object(), {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "project_revision"});
  LMDJ_CHECK(rebased.at("state") == "active");
  LMDJ_CHECK(rebased.at("expected_revision") == 3);
  LMDJ_CHECK(rebased.at("pending_event_count") == 1);
  const auto stop_command = uuid(303);
  const auto& stopped = check_exact_success(
      runtime->dispatch(
          "sequence.record.stop",
          {{"session_id", kSequenceSessionId}, {"command_id", stop_command}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "runtime_frame", "pattern_publication"});
  LMDJ_CHECK(stopped.at("state") == "inactive");
  LMDJ_CHECK(stopped.at("committed_revision") == 4);
  LMDJ_CHECK(stopped.at("replayed") == false);
  const auto& recoverable = check_exact_success(
      runtime->dispatch("sequence.recovery.list", Json::object(), {}),
      {"candidates", "project_revision"});
  LMDJ_CHECK(recoverable.at("candidates").empty());
  LMDJ_CHECK(recoverable.at("project_revision").is_null());
  const auto saved = inspect_project(temp.path(), kProjectId);
  const auto& events = saved.at("result")
                           .at("project")
                           .at("patterns")
                           .at(kPatternId)
                           .at("events");
  LMDJ_CHECK(events.size() == 1);
  LMDJ_CHECK(events.at(0).at("onset_tick") == 0);
  LMDJ_CHECK(events.at(0).at("duration_tick") >= 1);
  const auto& captured = check_exact_success(
      runtime->dispatch("sample.inspect", {{"slot", slot(0, 1)}}, {}),
      {"project_revision", "slot", "asset_id", "playback", "metadata",
       "waveform_cache_identity"});
  LMDJ_CHECK(captured.at("asset_id") == captured_asset_id);
  const auto inspected = inspect_project(temp.path(), kProjectId);
  LMDJ_CHECK(inspected.at("ok") == true);
  LMDJ_CHECK(
      inspected.at("result").at("project").at("project_id") == kProjectId);
  LMDJ_CHECK(
      inspected.at("result")
          .at("project")
          .at("patterns")
          .contains(kPatternId));

  FakeCoordinator close_coordinator;
  const auto installed = ControlRuntimeAudioAccess::install(
      *runtime, close_coordinator.seam());
  LMDJ_CHECK(installed.has_value());
  const auto& suspended = check_exact_success(
      runtime->dispatch("audio.suspend", Json::object(), {}),
      {"state", "changed", "stopped_sequence_id"});
  LMDJ_CHECK((
      suspended ==
      Json{{"state", "audio-suspended"},
           {"changed", true},
           {"stopped_sequence_id", nullptr}}));
  LMDJ_CHECK(close_coordinator.called);
  const auto& closed = check_exact_success(
      runtime->dispatch("host.close", Json::object(), {}),
      {"state", "stopped_sequence_id"});
  LMDJ_CHECK((
      closed == Json{{"state", "closed"}, {"stopped_sequence_id", nullptr}}));
  runtime.reset();

  auto reopened = make_runtime(temp.path());
  check_success(reopened->dispatch(
      "project.open",
      {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
      {}));
}

void test_sequence_observer_busy_and_owner_loss_recovery() {
  TempDirectory temp;
  {
    auto owner = make_runtime(temp.path());
    check_success(owner->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(32);
    import_and_assign(*owner, wav, kAssetId, 701, 702, 0);
    check_success(owner->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    FakeCoordinator coordinator;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*owner, coordinator.seam())
            .has_value());
    check_success(owner->dispatch("audio.activate", Json::object(), {}));
    check_success(owner->dispatch(
        "sequence.record.begin",
        {{"session_id", kSequenceSessionId},
         {"pattern_id", kPatternId},
         {"expected_revision", 2}},
        {}));
    check_success(owner->dispatch(
        "sequence.record.event",
        {{"session_id", kSequenceSessionId},
         {"event",
          {{"slot", slot(0, 0)}, {"velocity", 100}, {"pressed", true}}}},
        {}));
    OneShotAudioDriver audio(owner->engine());
    audio.render_one();
    check_success(owner->dispatch(
        "sequence.record.event",
        {{"session_id", kSequenceSessionId},
         {"event",
          {{"slot", slot(0, 0)}, {"velocity", 0}, {"pressed", false}}}},
        {}));
    for (std::size_t callback = 0; callback < 750; ++callback) {
      audio.render_one();
    }
    LMDJ_CHECK(owner->engine().current_pattern_has_overlay() == true);

    auto observer = make_runtime(temp.path());
    const auto& status = check_exact_success(
        observer->dispatch(
            "sequence.record.status", {{"project_id", kProjectId}}, {}),
        {"state", "session_id", "pattern_id", "pending_pattern_id",
         "expected_revision", "next_flush_seq", "pending_event_count",
         "effective_runtime_frame", "project_revision"});
    LMDJ_CHECK(status.at("state") == "active");
    LMDJ_CHECK(status.at("session_id") == kSequenceSessionId);
    check_error(
        observer->dispatch(
            "project.open",
            {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
            {}),
        "PROJECT_BUSY");
    owner->fail_and_seal("test_owner_loss");
    LMDJ_CHECK(owner->engine().pattern_telemetry().pending_activation_frame ==
               192'000);
    for (std::size_t callback = 0; callback < 750; ++callback) {
      audio.render_one();
    }
    LMDJ_CHECK(owner->engine().current_pattern_has_overlay() == false);
    LMDJ_CHECK(owner->engine().telemetry().started_voices == 1);
    const auto& recovery = check_exact_success(
        observer->dispatch(
            "sequence.recovery.list", {{"project_id", kProjectId}}, {}),
        {"candidates", "project_revision"});
    LMDJ_CHECK(recovery.at("candidates").size() == 1);
    LMDJ_CHECK(
        recovery.at("candidates").at(0).at("session_id") ==
        kSequenceSessionId);
    LMDJ_CHECK(
        recovery.at("candidates").at(0).at("reason") == "owner_lost");
  }

  auto restarted = make_runtime(temp.path());
  const auto& recovery = check_exact_success(
      restarted->dispatch(
          "sequence.recovery.list", {{"project_id", kProjectId}}, {}),
      {"candidates", "project_revision"});
  LMDJ_CHECK(recovery.at("candidates").size() == 1);
  LMDJ_CHECK(recovery.at("candidates").at(0).at("session_id") == kSequenceSessionId);
  LMDJ_CHECK(recovery.at("candidates").at(0).at("reason") == "owner_lost");
}

void test_owner_loss_cleanup_failure_stops_and_clears_the_overlay() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(32);
  import_and_assign(*runtime, wav, kAssetId, 738, 739, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  coordinator.engine = &runtime->engine();
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  check_success(runtime->dispatch(
      "sequence.record.begin",
      {{"session_id", kSequenceSessionId},
       {"pattern_id", kPatternId},
       {"expected_revision", 2}},
      {}));

  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  audio.render_one();
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"kind", "release"}}, {}));
  for (std::size_t callback = 0; callback < 750; ++callback) {
    audio.render_one();
  }
  LMDJ_CHECK(runtime->engine().current_pattern_has_overlay() == true);

  check_exact_success(
      lmdj::web_runtime::testing::fail_next_pattern_publication(*runtime),
      {"armed"});
  runtime->fail_and_seal("test_owner_loss_cleanup_failure");

  LMDJ_CHECK(runtime->failed());
  LMDJ_CHECK(coordinator.called);
  LMDJ_CHECK(runtime->engine().telemetry().state ==
             lmdj::audio::RealtimeState::stopped);
  LMDJ_CHECK(!runtime->engine().current_pattern_id().has_value());
  LMDJ_CHECK(!runtime->engine().pending_pattern_id().has_value());
}

void test_pending_sequence_overlay_repeats_and_commits_without_duplicate() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 731, 732, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  check_success(runtime->dispatch(
      "sequence.record.begin",
      {{"session_id", kSequenceSessionId},
       {"pattern_id", kPatternId},
       {"expected_revision", 2}},
      {}));

  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  audio.render_one();
  LMDJ_CHECK(runtime->engine().telemetry().started_voices == 1);
  LMDJ_CHECK(runtime->engine().pattern_telemetry().pending_generation == 0);
  LMDJ_CHECK(runtime->engine().current_pattern_has_overlay() == false);
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"kind", "release"}}, {}));

  const auto overlay_publication = runtime->engine().pattern_telemetry();
  LMDJ_CHECK(overlay_publication.pending_generation != 0);
  LMDJ_CHECK(overlay_publication.pending_activation_frame == 96'000);
  const auto& settings = check_exact_success(
      runtime->dispatch(
          "sequence.settings.update",
          {{"command_id", uuid(734)},
           {"expected_revision", 2},
           {"session_id", kSequenceSessionId},
           {"bpm", 90},
           {"quantize_enabled", nullptr},
           {"swing_percent", nullptr}},
          {}),
      {"bpm", "quantize_enabled", "swing_percent", "committed_revision",
       "replayed", "project_revision", "pattern_publication"});
  LMDJ_CHECK(settings.at("committed_revision") == 3);
  LMDJ_CHECK(settings.at("pattern_publication").is_object());
  LMDJ_CHECK(runtime->engine().pattern_telemetry().pending_activation_frame ==
             96'000);
  for (std::size_t callback = 0; callback < 750; ++callback) {
    audio.render_one();
  }
  LMDJ_CHECK(runtime->engine().telemetry().started_voices == 2);
  LMDJ_CHECK(runtime->engine().current_pattern_has_overlay() == true);

  check_error(
      runtime->dispatch(
          "sequence.record.event",
          {{"session_id", kSequenceSessionId},
           {"event",
            {{"slot", slot(0, 0)}, {"velocity", 0}, {"pressed", false}}}},
          {}),
      "INVALID_ARGUMENT");
  LMDJ_CHECK(runtime->engine().pattern_telemetry().pending_generation == 0);
  LMDJ_CHECK(runtime->engine().current_pattern_has_overlay() == true);

  const auto& stopped = check_exact_success(
      runtime->dispatch(
          "sequence.record.stop",
          {{"session_id", kSequenceSessionId}, {"command_id", uuid(733)}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "runtime_frame", "pattern_publication"});
  LMDJ_CHECK(stopped.at("committed_revision") == 4);
  LMDJ_CHECK(stopped.at("pattern_publication").is_object());
  LMDJ_CHECK(runtime->engine().pattern_telemetry().pending_activation_frame ==
             224'000);

  for (std::size_t callback = 0; callback < 1'000; ++callback) {
    audio.render_one();
  }
  LMDJ_CHECK(runtime->engine().telemetry().started_voices == 3);
  LMDJ_CHECK(runtime->engine().current_pattern_has_overlay() == false);
  const auto final_pattern = runtime->engine().pattern_telemetry();
  LMDJ_CHECK(final_pattern.applied_publications == 3);
  LMDJ_CHECK(final_pattern.superseded_publications == 1);
}

void test_stop_replay_recovers_a_committed_clean_publication_failure() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 735, 736, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  check_success(runtime->dispatch(
      "sequence.record.begin",
      {{"session_id", kSequenceSessionId},
       {"pattern_id", kPatternId},
       {"expected_revision", 2}},
      {}));

  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  audio.render_one();
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"kind", "release"}}, {}));
  for (std::size_t callback = 0; callback < 750; ++callback) {
    audio.render_one();
  }
  LMDJ_CHECK(runtime->engine().current_pattern_has_overlay() == true);

  const auto command_id = uuid(737);
  check_exact_success(
      lmdj::web_runtime::testing::fail_next_pattern_publication(*runtime),
      {"armed"});
  check_error(
      runtime->dispatch(
          "sequence.record.stop",
          {{"session_id", kSequenceSessionId}, {"command_id", command_id}},
          {}),
      "INVALID_ARGUMENT");

  const auto& replayed = check_exact_success(
      runtime->dispatch(
          "sequence.record.stop",
          {{"session_id", kSequenceSessionId}, {"command_id", command_id}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "runtime_frame", "pattern_publication"});
  LMDJ_CHECK(replayed.at("committed_revision") == 3);
  LMDJ_CHECK(replayed.at("replayed") == true);
  LMDJ_CHECK(replayed.at("pattern_publication").is_object());
  LMDJ_CHECK(runtime->engine().pattern_telemetry().pending_activation_frame ==
             192'000);
  for (std::size_t callback = 0; callback < 750; ++callback) {
    audio.render_one();
  }
  LMDJ_CHECK(runtime->engine().current_pattern_has_overlay() == false);
  LMDJ_CHECK(runtime->engine().telemetry().started_voices == 3);
}

void test_authoritative_switch_supersedes_overlay_and_stop_cancels_target() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 740, 741, 0);
  const auto target_pattern = uuid(11);
  const auto& created = check_exact_success(
      runtime->dispatch(
          "pattern.create",
          {{"command_id", uuid(742)},
           {"expected_revision", 2},
           {"pattern_id", target_pattern},
           {"bars", 1}},
          {}),
      {"committed_revision", "pattern_id", "bars", "replayed",
       "project_revision"});
  LMDJ_CHECK(created.at("committed_revision") == 3);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  check_success(runtime->dispatch(
      "sequence.record.begin",
      {{"session_id", kSequenceSessionId},
       {"pattern_id", kPatternId},
       {"expected_revision", 3}},
      {}));

  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"kind", "release"}}, {}));
  const auto overlay = runtime->engine().pattern_telemetry();
  LMDJ_CHECK(overlay.pending_generation != 0);
  LMDJ_CHECK(runtime->engine().pending_pattern_id() ==
             lmdj::foundation::PatternId{std::string(kPatternId)});

  const auto& switching = check_exact_success(
      runtime->dispatch(
          "sequence.record.switch-request",
          {{"session_id", kSequenceSessionId},
           {"next_pattern_id", target_pattern}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "pattern_publication"});
  LMDJ_CHECK(switching.at("state") == "switching");
  LMDJ_CHECK(switching.at("pending_pattern_id") == target_pattern);
  LMDJ_CHECK(runtime->engine().pending_pattern_id() ==
             lmdj::foundation::PatternId{target_pattern});
  LMDJ_CHECK(runtime->engine().pattern_telemetry().superseded_publications >= 1);
  OneShotAudioDriver audio(runtime->engine());
  audio.render_one();

  const auto revision_before_settings = switching.at("project_revision");
  check_error(
      runtime->dispatch(
          "sequence.settings.update",
          {{"command_id", uuid(743)},
           {"expected_revision", revision_before_settings},
           {"session_id", kSequenceSessionId},
           {"bpm", 90},
           {"quantize_enabled", nullptr},
           {"swing_percent", nullptr}},
          {}),
      "INVALID_ARGUMENT");
  const auto unchanged = inspect_project(temp.path(), kProjectId);
  LMDJ_CHECK(unchanged.at("project_revision") == revision_before_settings);
  LMDJ_CHECK(unchanged.at("result").at("project").at("bpm") == 120);

  const auto stop_command = uuid(744);
  check_exact_success(
      lmdj::web_runtime::testing::fail_next_pattern_publication(*runtime),
      {"armed"});
  check_error(
      runtime->dispatch(
          "sequence.record.stop",
          {{"session_id", kSequenceSessionId}, {"command_id", stop_command}},
          {}),
      "INVALID_ARGUMENT");
  LMDJ_CHECK(!runtime->engine().pending_pattern_id().has_value());
  const auto committed_revision =
      inspect_project(temp.path(), kProjectId).at("project_revision");
  const auto canceled_boundary =
      switching.at("effective_runtime_frame").get<std::uint64_t>();
  while (runtime->engine().telemetry().rendered_frames <= canceled_boundary) {
    audio.render_one();
  }
  LMDJ_CHECK(runtime->engine().current_pattern_id() ==
             lmdj::foundation::PatternId{std::string(kPatternId)});
  const auto& replayed = check_exact_success(
      runtime->dispatch(
          "sequence.record.stop",
          {{"session_id", kSequenceSessionId}, {"command_id", stop_command}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "runtime_frame", "pattern_publication"});
  LMDJ_CHECK(replayed.at("state") == "inactive");
  LMDJ_CHECK(replayed.at("replayed") == true);
  LMDJ_CHECK(replayed.at("pattern_publication").is_object());
  LMDJ_CHECK(
      replayed.at("pattern_publication").at("activation_frame") >
      canceled_boundary);
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") ==
      committed_revision);
  for (std::size_t callback = 0; callback < 1'100; ++callback) {
    audio.render_one();
  }
  LMDJ_CHECK(runtime->engine().current_pattern_id() ==
             lmdj::foundation::PatternId{std::string(kPatternId)});
  LMDJ_CHECK(runtime->engine().current_pattern_has_overlay() == false);
  const auto saved = inspect_project(temp.path(), kProjectId);
  LMDJ_CHECK(saved.at("result")
                 .at("project")
                 .at("patterns")
                 .at(kPatternId)
                 .at("events")
                 .size() == 1);
}

void test_stop_fails_closed_if_target_applies_between_cancel_queries() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto target_pattern = uuid(13);
  const auto& created = check_exact_success(
      runtime->dispatch(
          "pattern.create",
          {{"command_id", uuid(750)},
           {"expected_revision", 0},
           {"pattern_id", target_pattern},
           {"bars", 1}},
          {}),
      {"committed_revision", "pattern_id", "bars", "replayed",
       "project_revision"});
  LMDJ_CHECK(created.at("committed_revision") == 1);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  check_success(runtime->dispatch(
      "sequence.record.begin",
      {{"session_id", kSequenceSessionId},
       {"pattern_id", kPatternId},
       {"expected_revision", 1}},
      {}));
  const auto& switching = check_exact_success(
      runtime->dispatch(
          "sequence.record.switch-request",
          {{"session_id", kSequenceSessionId},
           {"next_pattern_id", target_pattern}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "pattern_publication"});
  const auto boundary =
      switching.at("effective_runtime_frame").get<std::uint64_t>();

  OneShotAudioDriver audio(runtime->engine());
  while (runtime->engine().telemetry().rendered_frames < boundary) {
    audio.render_one();
  }
  LMDJ_CHECK(runtime->engine().telemetry().rendered_frames == boundary);
  LMDJ_CHECK(runtime->engine().current_pattern_id() ==
             lmdj::foundation::PatternId{std::string(kPatternId)});

  struct CancelGate final {
    std::atomic<bool> first_query_complete{false};
    std::atomic<bool> release{false};
  } gate;
  lmdj::web_runtime::testing::CancelPendingSwitchHook hook{
      &gate,
      [](void* context) noexcept {
        auto& cancel_gate = *static_cast<CancelGate*>(context);
        cancel_gate.first_query_complete.store(true, std::memory_order_release);
        while (!cancel_gate.release.load(std::memory_order_acquire)) {
          std::this_thread::yield();
        }
      }};
  lmdj::web_runtime::testing::set_cancel_pending_switch_hook(&hook);

  Json stop_response;
  std::thread stop_thread([&] {
    stop_response = runtime->dispatch(
        "sequence.record.stop",
        {{"session_id", kSequenceSessionId}, {"command_id", uuid(751)}},
        {});
  });
  while (!gate.first_query_complete.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }
  audio.render_one();
  LMDJ_CHECK(runtime->engine().current_pattern_id() ==
             lmdj::foundation::PatternId{target_pattern});
  LMDJ_CHECK(!runtime->engine().pending_pattern_id().has_value());
  gate.release.store(true, std::memory_order_release);
  stop_thread.join();

  check_error(stop_response, "INVALID_ARGUMENT");
  LMDJ_CHECK(runtime->engine().telemetry().state ==
             lmdj::audio::RealtimeState::stopped);
  LMDJ_CHECK(!runtime->engine().current_pattern_id().has_value());
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId).at("project_revision") ==
             1);
}

void test_bpm_publication_then_switch_flushes_old_events_at_exact_boundary() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 745, 746, 0);
  const auto target_pattern = uuid(12);
  check_success(runtime->dispatch(
      "pattern.create",
      {{"command_id", uuid(747)},
       {"expected_revision", 2},
       {"pattern_id", target_pattern},
       {"bars", 1}},
      {}));
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  check_success(runtime->dispatch(
      "sequence.record.begin",
      {{"session_id", kSequenceSessionId},
       {"pattern_id", kPatternId},
       {"expected_revision", 3}},
      {}));
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"kind", "release"}}, {}));
  const auto& settings = check_exact_success(
      runtime->dispatch(
          "sequence.settings.update",
          {{"command_id", uuid(748)},
           {"expected_revision", 3},
           {"session_id", kSequenceSessionId},
           {"bpm", 90},
           {"quantize_enabled", nullptr},
           {"swing_percent", nullptr}},
          {}),
      {"bpm", "quantize_enabled", "swing_percent", "committed_revision",
       "replayed", "project_revision", "pattern_publication"});
  LMDJ_CHECK(settings.at("pattern_publication").is_object());

  const auto& switching = check_exact_success(
      runtime->dispatch(
          "sequence.record.switch-request",
          {{"session_id", kSequenceSessionId},
           {"next_pattern_id", target_pattern}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "pattern_publication"});
  const auto boundary =
      switching.at("effective_runtime_frame").get<std::uint64_t>();
  LMDJ_CHECK(switching.at("pattern_publication").at("activation_frame") ==
             boundary);
  OneShotAudioDriver audio(runtime->engine());
  while (runtime->engine().telemetry().rendered_frames <= boundary) {
    audio.render_one();
  }
  const auto notification = runtime->drain_sequence_bar_boundary();
  LMDJ_CHECK(notification.has_value());
  LMDJ_CHECK(notification->pattern_id == target_pattern);
  LMDJ_CHECK(!runtime->drain_sequence_bar_boundary().has_value());
  const auto& flushed = check_exact_success(
      runtime->dispatch(
          "sequence.record.flush",
          {{"session_id", kSequenceSessionId}, {"command_id", uuid(749)}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "runtime_frame", "pattern_publication"});
  LMDJ_CHECK(flushed.at("state") == "active");
  LMDJ_CHECK(flushed.at("pattern_id") == target_pattern);
  LMDJ_CHECK(flushed.at("pattern_publication").is_null());
  LMDJ_CHECK(runtime->engine().current_pattern_id() ==
             lmdj::foundation::PatternId{target_pattern});
  const auto saved = inspect_project(temp.path(), kProjectId);
  LMDJ_CHECK(saved.at("result")
                 .at("project")
                 .at("patterns")
                 .at(kPatternId)
                 .at("events")
                 .size() == 1);
}

void test_sequence_switch_prepares_before_selecting_bar_boundary() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto& created = check_exact_success(
      runtime->dispatch(
          "pattern.create",
          {{"command_id", uuid(1'201)},
           {"expected_revision", 0},
           {"pattern_id", kNextPatternId},
           {"bars", 1}},
          {}),
      {"committed_revision", "pattern_id", "bars", "replayed",
       "project_revision"});
  LMDJ_CHECK(created.at("committed_revision") == 1);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));

  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "sequence.settings.update",
      {{"command_id", "00000000-0000-4000-8000-000000000099"},
       {"expected_revision", 1},
       {"session_id", nullptr},
       {"bpm", 132},
       {"quantize_enabled", nullptr},
       {"swing_percent", nullptr}},
      {}));
  while (runtime->engine().pattern_telemetry().pending_generation != 0) {
    audio.render_one();
  }
  const auto& begun = check_exact_success(
      runtime->dispatch(
          "sequence.record.begin",
          {{"session_id", kSequenceSessionId},
           {"pattern_id", kPatternId},
           {"expected_revision", 2}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "transport_anchor"});
  const auto bar_frames = lmdj::audio::tick_boundary_frame(
      lmdj::domain::kBarTicks4x4, 132, lmdj::audio::kTransportPpq);
  LMDJ_CHECK(bar_frames.has_value());
  const auto anchor_frame =
      begun.at("transport_anchor").at("runtime_frame").get<std::uint64_t>();
  const auto request_frame = anchor_frame + bar_frames.value() - 128;
  while (runtime->engine().telemetry().rendered_frames < request_frame) {
    const auto remaining =
        request_frame - runtime->engine().telemetry().rendered_frames;
    audio.render_frames(static_cast<std::uint32_t>(
        remaining < 128 ? remaining : 128));
  }
  LMDJ_CHECK(runtime->engine().telemetry().rendered_frames == request_frame);
  const auto& switched = check_exact_success(
      runtime->dispatch(
          "sequence.record.switch-request",
          {{"session_id", kSequenceSessionId},
           {"next_pattern_id", kNextPatternId}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "pattern_publication"});
  LMDJ_CHECK(switched.at("state") == "switching");
  LMDJ_CHECK(switched.at("pending_pattern_id") == kNextPatternId);
  LMDJ_CHECK(
      switched.at("effective_runtime_frame") ==
      switched.at("pattern_publication").at("activation_frame"));
}

void test_sequence_switch_supersedes_a_near_boundary_recording_overlay() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 1'211, 1'212, 0);
  check_exact_success(
      runtime->dispatch(
          "pattern.create",
          {{"command_id", uuid(1'213)},
           {"expected_revision", 2},
           {"pattern_id", kNextPatternId},
           {"bars", 1}},
          {}),
      {"committed_revision", "pattern_id", "bars", "replayed",
       "project_revision"});
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));

  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  check_exact_success(
      runtime->dispatch(
          "sequence.record.begin",
          {{"session_id", kSequenceSessionId},
           {"pattern_id", kPatternId},
           {"expected_revision", 3}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "transport_anchor"});

  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"kind", "release"}}, {}));
  const auto overlay = runtime->engine().pattern_telemetry();
  LMDJ_CHECK(overlay.pending_generation != 0);
  OneShotAudioDriver audio(runtime->engine());
  struct PublicationGate final {
    OneShotAudioDriver& audio;
    RealtimeEngine& engine;
    std::uint64_t boundary;
  } gate{audio, runtime->engine(), overlay.pending_activation_frame};
  lmdj::web_runtime::testing::SequenceSwitchPublicationHook hook{
      &gate,
      [](void* context) noexcept {
        auto& publication = *static_cast<PublicationGate*>(context);
        while (publication.engine.telemetry().rendered_frames <=
               publication.boundary) {
          publication.audio.render_one();
        }
      }};
  lmdj::web_runtime::testing::set_sequence_switch_publication_hook(&hook);

  const auto& switched = check_exact_success(
      runtime->dispatch(
          "sequence.record.switch-request",
          {{"session_id", kSequenceSessionId},
           {"next_pattern_id", kNextPatternId}},
          {}),
      {"state", "session_id", "pattern_id", "pending_pattern_id",
       "expected_revision", "next_flush_seq", "pending_event_count",
       "effective_runtime_frame", "committed_revision", "replayed",
       "project_revision", "pattern_publication"});
  LMDJ_CHECK(switched.at("state") == "switching");
  LMDJ_CHECK(switched.at("pending_pattern_id") == kNextPatternId);
  LMDJ_CHECK(
      switched.at("effective_runtime_frame") ==
      switched.at("pattern_publication").at("activation_frame"));
  LMDJ_CHECK(!runtime->failed());
}

void test_sample_editing_binds_current_project_and_drives_fixed_controls() {
  TempDirectory temp;
  {
    auto fixture_builder = make_runtime(temp.path());
    check_success(fixture_builder->dispatch(
        "project.create", create_payload(), {}));
  }
  const auto manifest_path = temp.path() / "projects" /
                             (std::string(kProjectId) + ".lmdj") /
                             "manifest.json";
  const auto original_manifest = read_bytes(manifest_path);
  auto runtime = make_runtime(temp.path());
  check_exact_success(
      runtime->dispatch(
          "project.open",
          {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
          {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  const auto current = check_exact_success(
      runtime->dispatch("project.inspect", Json::object(), {}),
      {"project", "project_revision"});
  LMDJ_CHECK(current.at("project").at("contract") == "lmdj.project.v3");
  LMDJ_CHECK(read_bytes(manifest_path) == original_manifest);

  auto forbidden_inspect = Json{{"slot", slot(0, 0)}};
  forbidden_inspect["project_path"] = "/browser-supplied/project.lmdj";
  check_error(
      runtime->dispatch("sample.inspect", forbidden_inspect, {}),
      "HOST_PROTOCOL_MISMATCH");
  const auto empty = check_exact_success(
      runtime->dispatch("sample.inspect", {{"slot", slot(0, 0)}}, {}),
      {"project_revision", "slot", "asset_id", "playback", "metadata",
       "waveform_cache_identity"});
  LMDJ_CHECK(empty.at("project_revision") == 0);
  LMDJ_CHECK(empty.at("asset_id").is_null());
  LMDJ_CHECK(empty.at("metadata").is_null());
  LMDJ_CHECK(read_bytes(manifest_path) == original_manifest);
  const auto empty_quota = check_exact_success(
      runtime->dispatch("sample.quota", {{"slot", slot(0, 0)}}, {}),
      {"project_revision", "slot", "bank_quota_bytes", "bank_used_bytes",
       "bank_remaining_bytes", "project_quota_bytes", "project_used_bytes",
       "project_remaining_bytes", "effective_remaining_bytes",
       "effective_remaining_frames", "consumed"});
  LMDJ_CHECK(empty_quota.at("project_revision") == 0);
  LMDJ_CHECK(empty_quota.at("slot") == slot(0, 0));
  LMDJ_CHECK(empty_quota.at("effective_remaining_frames") == 16'777'216);
  LMDJ_CHECK(empty_quota.at("consumed").empty());

  const auto wav = mono_pcm16_wav(2'400);
  const auto token = uuid(401);
  const auto begun = check_exact_success(
      runtime->dispatch(
          "sample.import.begin",
          sample_begin_payload(401, 402, 0, kAssetId, wav.size()),
          {}),
      {"token", "expected_bytes"});
  LMDJ_CHECK(begun.at("token") == token);
  LMDJ_CHECK(begun.at("expected_bytes") == wav.size());

  const auto midpoint = wav.size() / 2U;
  const auto first = std::span<const std::byte>(wav).first(midpoint);
  const auto second = std::span<const std::byte>(wav).subspan(midpoint);
  const auto first_chunk = check_exact_success(
      runtime->dispatch(
          "sample.import.chunk",
          sample_chunk_payload(401, 0, false, first),
          first),
      {"received_bytes", "final"});
  LMDJ_CHECK(first_chunk.at("received_bytes") == midpoint);
  LMDJ_CHECK(first_chunk.at("final") == false);
  const auto final_chunk = check_exact_success(
      runtime->dispatch(
          "sample.import.chunk",
          sample_chunk_payload(401, midpoint, true, second),
          second),
      {"received_bytes", "final"});
  LMDJ_CHECK(final_chunk.at("received_bytes") == wav.size());
  LMDJ_CHECK(final_chunk.at("final") == true);

  const auto committed = check_exact_success(
      runtime->dispatch(
          "sample.import.commit", {{"import_token", token}}, {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(committed.at("committed_revision") == 1);
  LMDJ_CHECK(committed.at("runtime_revision") == 1);
  LMDJ_CHECK(committed.at("runtime_published") == true);
  LMDJ_CHECK(runtime->engine().bank_telemetry().accepted_publications == 2);
  const auto migrated = check_exact_success(
      runtime->dispatch("project.inspect", Json::object(), {}),
      {"project", "project_revision"});
  LMDJ_CHECK(migrated.at("project_revision") == 1);
  const auto checkpoint_bytes = read_bytes(
      manifest_path.parent_path() / "history/checkpoints/1.json");
  const auto checkpoint_text = std::string_view(
      reinterpret_cast<const char*>(checkpoint_bytes.data()),
      checkpoint_bytes.size());
  LMDJ_CHECK(
      Json::parse(checkpoint_text).at("contract") == "lmdj.project.v3");

  const auto inspected = check_exact_success(
      runtime->dispatch("sample.inspect", {{"slot", slot(0, 0)}}, {}),
      {"project_revision", "slot", "asset_id", "playback", "metadata",
       "waveform_cache_identity"});
  LMDJ_CHECK(inspected.at("project_revision") == 1);
  LMDJ_CHECK(inspected.at("asset_id") == kAssetId);
  LMDJ_CHECK(inspected.at("metadata").at("source_frames") == 2'400);
  const auto replacement_quota = check_exact_success(
      runtime->dispatch("sample.quota", {{"slot", slot(0, 0)}}, {}),
      {"project_revision", "slot", "bank_quota_bytes", "bank_used_bytes",
       "bank_remaining_bytes", "project_quota_bytes", "project_used_bytes",
       "project_remaining_bytes", "effective_remaining_bytes",
       "effective_remaining_frames", "consumed"});
  LMDJ_CHECK(replacement_quota.at("project_revision") == 1);
  LMDJ_CHECK(replacement_quota.at("bank_used_bytes") == 0);
  LMDJ_CHECK(replacement_quota.at("consumed").size() == 1);
  LMDJ_CHECK(replacement_quota.at("consumed").at(0).at("slot") == slot(0, 0));
  const auto waveform = check_exact_success(
      runtime->dispatch(
          "sample.waveform",
          {{"slot", slot(0, 0)},
           {"window",
            {{"start_frame", 0},
             {"end_frame", 2'400},
             {"bucket_count", 32}}}},
          {}),
      {"metadata", "algorithm_version", "buckets", "project_revision"});
  LMDJ_CHECK(waveform.at("algorithm_version") == 1);
  LMDJ_CHECK(waveform.at("buckets").size() == 32);

  const auto loop_toggle = playback_payload(
      10, 2'000, "loop_toggle", -600, false);
  const auto updated = check_exact_success(
      runtime->dispatch(
          "sample.update_pad",
          {{"command_id", uuid(403)},
           {"expected_revision", 1},
           {"slot", slot(0, 0)},
           {"playback", loop_toggle}},
          {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(updated.at("committed_revision") == 2);
  LMDJ_CHECK(updated.at("runtime_revision") == 2);
  LMDJ_CHECK(updated.at("runtime_published") == true);

  const auto conflict = check_error(
      runtime->dispatch(
          "sample.update_pad",
          {{"command_id", uuid(404)},
           {"expected_revision", 1},
           {"slot", slot(0, 0)},
           {"playback", loop_toggle}},
          {}),
      "REVISION_CONFLICT");
  LMDJ_CHECK(conflict.at("details").at("actual_revision") == 2);
  LMDJ_CHECK(conflict.at("details").at("expected_revision") == 1);

  FakeCoordinator coordinator;
  coordinator.begin_acknowledgement = 3;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  coordinator.engine = &runtime->engine();
  coordinator.observe_engine_generation = true;
  std::array<float, 1> left{};
  std::array<float, 1> right{};

  check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 127}}, {}),
      {"sequence", "status"});
  runtime->engine().render(left.data(), right.data(), 1);
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 1);
  check_exact_success(
      runtime->dispatch("sample.stop", {{"slot", slot(0, 0)}}, {}),
      {"accepted", "scope"});
  runtime->engine().render(left.data(), right.data(), 1);
  // F6 ramp: the stop starts a kRealtimeRampFrames release tail instead of
  // silencing the voice at once, so it is still active after one frame.
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 1);
  std::array<float, 96> tail_left{};
  std::array<float, 96> tail_right{};
  runtime->engine().render(tail_left.data(), tail_right.data(), 96);
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 0);

  const auto preview = playback_payload(100, 200, "gate", -1'200, false);
  check_exact_success(
      runtime->dispatch(
          "sample.preview.set",
          {{"slot", slot(0, 0)}, {"playback", preview}},
          {}),
      {"accepted"});
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 127}}, {}));
  runtime->engine().render(left.data(), right.data(), 1);
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 1);
  check_exact_success(
      runtime->dispatch(
          "trigger", {{"slot", 0}, {"kind", "release"}}, {}),
      {"accepted"});
  runtime->engine().render(left.data(), right.data(), 1);
  // F6 ramp: the gate release renders its 96-frame tail before the voice
  // deactivates (the tail ends well before end_frame 200).
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 1);
  runtime->engine().render(tail_left.data(), tail_right.data(), 96);
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 0);

  // A real Worklet continues draining fixed controls while the control thread
  // prepares and publishes the replacement Bank.
  ContinuousAudioDriver audio(runtime->engine());
  const auto release_update = check_exact_success(
      runtime->dispatch(
          "sample.update_pad",
          {{"command_id", uuid(405)},
           {"expected_revision", 2},
           {"slot", slot(0, 0)},
           {"playback", preview}},
          {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(release_update.at("committed_revision") == 3);

  check_success(runtime->dispatch(
      "sample.preview.clear", {{"slot", slot(0, 0)}}, {}));
  check_success(runtime->dispatch(
      "sample.preview.set",
      {{"slot", slot(0, 0)},
       {"playback", playback_payload(0, 2'400, "loop_toggle")}},
      {}));
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 127}}, {}));
  wait_until([&] {
    return runtime->engine().telemetry().active_voices == 1;
  });
  const auto reset = check_exact_success(
      runtime->dispatch(
          "sample.reset_pad",
          {{"command_id", uuid(406)},
           {"expected_revision", 3},
           {"slot", slot(0, 0)}},
          {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(reset.at("committed_revision") == 4);
  wait_until([&] {
    return runtime->engine().telemetry().active_voices == 0;
  });
  audio.stop();

  std::array<lmdj::audio::RuntimeVoiceStateEvent, 16> voice_states{};
  const auto voice_count = runtime->engine().drain_voice_states(voice_states);
  LMDJ_CHECK(voice_count >= 6);
  LMDJ_CHECK(voice_states[0].state == lmdj::audio::RuntimeVoiceState::started);
  LMDJ_CHECK(std::any_of(
      voice_states.begin(),
      voice_states.begin() + static_cast<std::ptrdiff_t>(voice_count),
      [](const auto& event) {
        return event.state == lmdj::audio::RuntimeVoiceState::stopped;
      }));
}

void test_sample_import_prevents_current_project_switch_until_terminal() {
  TempDirectory temp;
  constexpr std::string_view other_project_id =
      "00000000-0000-4000-8000-000000000002";
  constexpr std::string_view other_pattern_id =
      "00000000-0000-4000-8000-000000000020";
  {
    auto fixture_builder = make_runtime(temp.path());
    check_success(fixture_builder->dispatch(
        "project.create", create_payload(), {}));
  }
  {
    auto fixture_builder = make_runtime(temp.path());
    check_success(fixture_builder->dispatch(
        "project.create",
        create_payload(other_project_id, other_pattern_id),
        {}));
  }

  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch(
      "project.open",
      {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
      {}));
  const auto wav = mono_pcm16_wav(32);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(411, 412, 0, kAssetId, wav.size()),
      {}));
  const auto staging = temp.path() / ".lmdj-host/sample-import-staging" /
                       uuid(411);
  LMDJ_CHECK(std::filesystem::exists(staging));

  check_error(
      runtime->dispatch(
          "project.open",
          {{"project_id", other_project_id},
           {"pattern_id", other_pattern_id}},
          {}),
      "HOST_STATE_INVALID");
  LMDJ_CHECK(std::filesystem::exists(staging));

  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(411, 0, true, wav),
      wav));
  const auto committed = check_exact_success(
      runtime->dispatch(
          "sample.import.commit", {{"import_token", uuid(411)}}, {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(committed.at("committed_revision") == 1);
  LMDJ_CHECK(committed.at("runtime_revision") == 1);
  LMDJ_CHECK(committed.at("runtime_published") == true);
  LMDJ_CHECK(!std::filesystem::exists(staging));
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 1);
  LMDJ_CHECK(
      inspect_project(temp.path(), other_project_id)
          .at("project_revision") == 0);

  const auto opened_other = check_exact_success(
      runtime->dispatch(
          "project.open",
          {{"project_id", other_project_id},
           {"pattern_id", other_pattern_id}},
          {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(opened_other.at("project_id") == other_project_id);
  LMDJ_CHECK(opened_other.at("project_revision") == 0);
}

void test_sample_import_protocol_failure_aborts_staging() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(32);
  const auto staging_root =
      temp.path() / ".lmdj-host/sample-import-staging";
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(421, 422, 0, kAssetId, wav.size()),
      {}));
  auto malformed = sample_chunk_payload(421, 0, true, wav);
  malformed["sidecar"]["sidecar_sha256"] = std::string(64, '0');
  check_error(
      runtime->dispatch("sample.import.chunk", malformed, wav),
      "HOST_PROTOCOL_MISMATCH");
  check_error(
      runtime->dispatch(
          "sample.import.commit", {{"import_token", uuid(421)}}, {}),
      "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(421)));

  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(423, 424, 0, kAssetId, wav.size()),
      {}));
  check_error(
      runtime->dispatch(
          "sample.import.chunk",
          sample_chunk_payload(423, 1, true, wav),
          wav),
      "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(423)));

  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(425, 426, 0, kAssetId, wav.size()),
      {}));
  const auto first_half = std::span<const std::byte>(wav).first(wav.size() / 2);
  check_error(
      runtime->dispatch(
          "sample.import.chunk",
          sample_chunk_payload(425, 0, true, first_half),
          first_half),
      "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(425)));

  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(427, 428, 0, kAssetId, wav.size()),
      {}));
  const auto overflow_payload = sample_chunk_payload(
      427,
      std::numeric_limits<std::uint64_t>::max(),
      false,
      first_half);
  check_error(
      runtime->dispatch(
          "sample.import.chunk", overflow_payload, first_half),
      "HOST_PROTOCOL_MISMATCH");
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(427)));

  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(429, 430, 0, kAssetId, wav.size()),
      {}));
  check_exact_success(
      runtime->dispatch(
          "sample.import.abort", {{"import_token", uuid(429)}}, {}),
      {"aborted"});
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(429)));

  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(461, 462, 0, kAssetId, wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(461, 0, true, wav),
      wav));
  const auto malformed_commit = check_error(
      runtime->dispatch(
          "sample.import.commit",
          {{"import_token", uuid(461)}, {"unexpected", true}},
          {}),
      "HOST_PROTOCOL_MISMATCH");
  LMDJ_CHECK(malformed_commit.at("details").empty());
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(461)));
  check_error(
      runtime->dispatch(
          "sample.import.commit", {{"import_token", uuid(461)}}, {}),
      "INVALID_ARGUMENT");

  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(463, 464, 0, kAssetId, wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(463, 0, false, first_half),
      first_half));
  const auto malformed_abort = check_error(
      runtime->dispatch(
          "sample.import.abort",
          {{"import_token", uuid(463)}, {"unexpected", true}},
          {}),
      "HOST_PROTOCOL_MISMATCH");
  LMDJ_CHECK(malformed_abort.at("details").empty());
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(463)));
  check_error(
      runtime->dispatch(
          "sample.import.abort", {{"import_token", uuid(463)}}, {}),
      "INVALID_ARGUMENT");

  const auto unowned_abort = check_error(
      runtime->dispatch(
          "sample.import.abort",
          {{"import_token", uuid(465)}, {"unexpected", true}},
          {}),
      "HOST_PROTOCOL_MISMATCH");
  LMDJ_CHECK(unowned_abort.at("details").empty());

  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(466, 467, 0, kAssetId, wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(466, 0, true, wav),
      wav));
  check_error(
      runtime->dispatch(
          "sample.import.commit",
          {{"import_token", uuid(466)}},
          first_half),
      "HOST_PROTOCOL_MISMATCH");
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(466)));

  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(468, 469, 0, kAssetId, wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(468, 0, false, first_half),
      first_half));
  check_error(
      runtime->dispatch(
          "sample.import.abort",
          {{"import_token", uuid(468)}},
          first_half),
      "HOST_PROTOCOL_MISMATCH");
  LMDJ_CHECK(!std::filesystem::exists(staging_root / uuid(468)));
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 0);
}

void test_sample_import_timeout_aborts_staging_and_fails_closed() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(32);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(451, 452, 0, kAssetId, wav.size()),
      {}));
  const auto staging = temp.path() / ".lmdj-host/sample-import-staging" /
                       uuid(451);
  LMDJ_CHECK(std::filesystem::exists(staging));

  check_error(
      runtime->dispatch(
          "sample.inspect",
          {{"slot", slot(0, 0)}},
          {},
          std::chrono::steady_clock::now() - std::chrono::seconds(31)),
      "HOST_TIMEOUT");
  LMDJ_CHECK(!std::filesystem::exists(staging));
  LMDJ_CHECK(runtime->failed());
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 0);
}

void test_sample_commit_quota_failure_keeps_truth_and_runtime_unchanged() {
  TempDirectory temp;
  constexpr RuntimePreparationLimits limits{
      1'048'576,
      16,
      134'217'728,
      268'435'456,
  };
  auto runtime = make_runtime(temp.path(), limits);
  check_success(runtime->dispatch("project.create", create_payload(), {}));

  const auto first_wav = mono_pcm16_wav(2);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(431, 432, 0, kAssetId, first_wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(431, 0, true, first_wav),
      first_wav));
  const auto first = check_exact_success(
      runtime->dispatch(
          "sample.import.commit", {{"import_token", uuid(431)}}, {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(first.at("runtime_revision") == 1);
  const auto generation =
      runtime->engine().bank_telemetry().accepted_publications;
  FakeCoordinator coordinator;
  coordinator.begin_acknowledgement = generation;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));

  const auto larger_wav = mono_pcm16_wav(8);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(433, 434, 1, uuid(435), larger_wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(433, 0, true, larger_wav),
      larger_wav));
  const auto rejected = runtime->dispatch(
      "sample.import.commit", {{"import_token", uuid(433)}}, {});
  check_error(rejected, "BANK_QUOTA_EXHAUSTED");
  LMDJ_CHECK(
      runtime->engine().bank_telemetry().accepted_publications == generation);
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 1);
  const auto retained = check_exact_success(
      runtime->dispatch("sample.inspect", {{"slot", slot(0, 0)}}, {}),
      {"project_revision", "slot", "asset_id", "playback", "metadata",
       "waveform_cache_identity"});
  LMDJ_CHECK(retained.at("project_revision") == 1);
  LMDJ_CHECK(retained.at("metadata").at("source_frames") == 2);
  LMDJ_CHECK(
      !std::filesystem::exists(
          temp.path() / ".lmdj-host/sample-import-staging" / uuid(433)));
  LMDJ_CHECK(
      runtime->engine().bank_telemetry().accepted_publications == generation);
}

void test_sample_post_claim_deadline_preserves_saved_truth() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeRuntimeClock clock;
  LMDJ_CHECK(
      ControlRuntimeClockAccess::install(*runtime, clock.seam()).has_value());
  check_success(runtime->dispatch(
      "project.create", create_payload(), {}, clock.current));

  const auto wav = mono_pcm16_wav(32);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(471, 472, 0, kAssetId, wav.size()),
      {},
      clock.current));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(471, 0, true, wav),
      wav,
      clock.current));
  const auto first = check_exact_success(
      runtime->dispatch(
          "sample.import.commit",
          {{"import_token", uuid(471)}},
          {},
          clock.current),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(first.at("runtime_revision") == 1);
  const auto generation =
      runtime->engine().bank_telemetry().accepted_publications;

  const auto submitted_at = clock.current;
  CommitDeadlineCrossing crossing{clock};
  Json response;
  {
    const lmdj::facade::detail::MutationPublishScope publish_scope(
        crossing.token());
    response = runtime->dispatch(
        "sample.update_pad",
        {{"command_id", uuid(473)},
         {"expected_revision", 1},
         {"slot", slot(0, 0)},
         {"playback", playback_payload(0, 16, "gate", -600)}},
        {},
        submitted_at);
  }
  LMDJ_CHECK(response.at("ok") == true);
  const auto saved = check_exact_success(
      response,
      {"committed_revision", "runtime_revision", "runtime_published",
       "snapshot_error"});
  LMDJ_CHECK(saved.at("committed_revision") == 2);
  LMDJ_CHECK(saved.at("runtime_revision") == 1);
  LMDJ_CHECK(saved.at("runtime_published") == false);
  LMDJ_CHECK(saved.at("snapshot_error").at("code") == "HOST_TIMEOUT");
  LMDJ_CHECK(!runtime->failed());
  LMDJ_CHECK(
      runtime->engine().bank_telemetry().accepted_publications == generation);
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 2);

  const auto second_wav = mono_pcm16_wav(16);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(474, 475, 2, uuid(476), second_wav.size()),
      {},
      clock.current));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(474, 0, true, second_wav),
      second_wav,
      clock.current));
  const auto staging = temp.path() / ".lmdj-host/sample-import-staging" /
                       uuid(474);
  LMDJ_CHECK(std::filesystem::exists(staging));
  const auto preclaim_submitted_at = clock.current;
  clock.current += std::chrono::seconds(31);
  check_error(
      runtime->dispatch(
          "sample.import.commit",
          {{"import_token", uuid(474)}},
          {},
          preclaim_submitted_at),
      "HOST_TIMEOUT");
  LMDJ_CHECK(runtime->failed());
  LMDJ_CHECK(!std::filesystem::exists(staging));
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 2);
}

void test_source_frames_are_admitted_by_prepared_pcm_quota() {
  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(220'501, 44'100);
    check_success(runtime->dispatch(
        "sample.import.begin",
        sample_begin_payload(441, 442, 0, kAssetId, wav.size()),
        {}));
    check_success(runtime->dispatch(
        "sample.import.chunk",
        sample_chunk_payload(441, 0, true, wav),
        wav));
    const auto published = check_exact_success(
        runtime->dispatch(
            "sample.import.commit", {{"import_token", uuid(441)}}, {}),
        {"committed_revision", "runtime_revision", "runtime_published"});
    LMDJ_CHECK(published.at("committed_revision") == 1);
    LMDJ_CHECK(published.at("runtime_revision") == 1);
    LMDJ_CHECK(published.at("runtime_published") == true);
    LMDJ_CHECK(
        runtime->engine().bank_telemetry().accepted_publications == 1);
  }

  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(240'001, 48'000);
    check_success(runtime->dispatch(
        "sample.import.begin",
        sample_begin_payload(443, 444, 0, kAssetId, wav.size()),
        {}));
    check_success(runtime->dispatch(
        "sample.import.chunk",
        sample_chunk_payload(443, 0, true, wav),
        wav));
    const auto published = check_exact_success(
        runtime->dispatch(
            "sample.import.commit", {{"import_token", uuid(443)}}, {}),
        {"committed_revision", "runtime_revision", "runtime_published"});
    LMDJ_CHECK(published.at("committed_revision") == 1);
    LMDJ_CHECK(published.at("runtime_revision") == 1);
    LMDJ_CHECK(published.at("runtime_published") == true);
    LMDJ_CHECK(
        inspect_project(temp.path(), kProjectId).at("project_revision") == 1);
  }
}

void test_trigger_queue_full_is_admission_failure() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(256);
  import_and_assign(*runtime, wav, kAssetId, 761, 762, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));

  for (std::uint64_t sequence = 1;
       sequence <= lmdj::audio::kRealtimeQueueCapacity;
       ++sequence) {
    const auto admitted = check_exact_success(
        runtime->dispatch(
            "trigger", {{"slot", 0}, {"velocity", 127}}, {}),
        {"sequence", "status"});
    LMDJ_CHECK(admitted.at("sequence") == sequence);
  }
  const auto rejected = check_error(
      runtime->dispatch(
          "trigger", {{"slot", 0}, {"velocity", 127}}, {}),
      "HOST_STATE_INVALID");
  LMDJ_CHECK(rejected.at("message") == "trigger queue is full");
  LMDJ_CHECK(runtime->engine().telemetry().queue_drops == 1);
  LMDJ_CHECK(
      runtime->engine().trigger_outcome_telemetry().published_outcomes == 0);

  const auto preview_rejected = check_error(
      runtime->dispatch(
          "sample.preview.set",
          {{"slot", slot(0, 0)},
           {"playback", playback_payload(0, 256, "one_shot")}},
          {}),
      "HOST_STATE_INVALID");
  LMDJ_CHECK(preview_rejected.at("message") == "trigger queue is full");
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 2);

  const auto mutation_rejected = check_error(
      runtime->dispatch(
          "sample.update_pad",
          {{"command_id", uuid(763)},
           {"expected_revision", 2},
           {"slot", slot(0, 0)},
           {"playback", playback_payload(0, 256, "one_shot")}},
          {}),
      "HOST_STATE_INVALID");
  LMDJ_CHECK(mutation_rejected.at("message") == "trigger queue is full");
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 2);
  LMDJ_CHECK(
      runtime->engine().trigger_outcome_telemetry().published_outcomes == 0);
}

void test_voice_capacity_is_sequence_addressed_execution_outcome() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(48'000);
  import_and_assign(*runtime, wav, kAssetId, 771, 772, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));

  for (std::uint64_t sequence = 1; sequence <= 129; ++sequence) {
    const auto admitted = check_exact_success(
        runtime->dispatch(
            "trigger", {{"slot", 0}, {"velocity", 127}}, {}),
        {"sequence", "status"});
    LMDJ_CHECK(admitted.at("sequence") == sequence);
  }
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  runtime->engine().render(left.data(), right.data(), 128);

  const auto first = runtime->drain_outcomes();
  const auto second = runtime->drain_outcomes();
  const auto third = runtime->drain_outcomes();
  LMDJ_CHECK(first.size() == 64);
  LMDJ_CHECK(second.size() == 64);
  LMDJ_CHECK(third.size() == 1);
  for (const auto& outcome : first) {
    LMDJ_CHECK(
        outcome.outcome == lmdj::audio::RuntimeTriggerOutcome::voice_started);
  }
  for (const auto& outcome : second) {
    LMDJ_CHECK(
        outcome.outcome == lmdj::audio::RuntimeTriggerOutcome::voice_started);
  }
  LMDJ_CHECK(third.front().sequence == 129);
  LMDJ_CHECK(
      third.front().outcome ==
      lmdj::audio::RuntimeTriggerOutcome::voice_capacity);
  LMDJ_CHECK(runtime->engine().telemetry().voice_drops == 1);
  LMDJ_CHECK(runtime->engine().telemetry().queue_drops == 0);
}

void test_audio_activation_requires_ready_and_reports_explicit_ack() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 791, 792, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));

  const auto missing_ready = AudioQuiescenceCoordinator{
      nullptr,
      &FakeCoordinator::await,
      &FakeCoordinator::begin,
      &FakeCoordinator::ready,
      &FakeCoordinator::acknowledged_generation,
  };
  LMDJ_CHECK(
      !ControlRuntimeAudioAccess::install(*runtime, missing_ready).has_value());

  FakeCoordinator coordinator;
  coordinator.is_ready = false;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  const auto& not_ready = check_error(
      runtime->dispatch("audio.activate", Json::object(), {}),
      "HOST_STATE_INVALID");
  LMDJ_CHECK(not_ready.at("message") == "audio output is not ready");

  const auto& before = check_exact_success(
      runtime->dispatch("host.status", Json::object(), {}),
      {"state", "project_id", "project_revision", "pattern_id",
       "runtime_ready", "control_generation", "acknowledged_generation",
       "limits", "audio_state", "capture_state"});
  LMDJ_CHECK(before.at("acknowledged_generation").is_null());

  coordinator.is_ready = true;
  coordinator.acknowledged = 77;
  coordinator.acknowledgement_delay_polls = 3;
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  LMDJ_CHECK(coordinator.begin_calls == 1);
  LMDJ_CHECK(coordinator.acknowledged_before_begin == 77);
  LMDJ_CHECK(coordinator.acknowledged == 1);
  LMDJ_CHECK(coordinator.acknowledgement_polls >= 3);
  const auto& after = check_exact_success(
      runtime->dispatch("host.status", Json::object(), {}),
      {"state", "project_id", "project_revision", "pattern_id",
       "runtime_ready", "control_generation", "acknowledged_generation",
       "limits", "audio_state", "capture_state"});
  LMDJ_CHECK(after.at("acknowledged_generation") == 1);
}

void test_live_bank_publication_waits_for_the_exact_acknowledgement() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 7911, 7912, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));

  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  LMDJ_CHECK(coordinator.acknowledged == 1);

  const auto calls_before_publication = coordinator.acknowledgement_calls;
  coordinator.begin_acknowledgement = 2;
  coordinator.acknowledgement_delay_polls = 3;
  coordinator.acknowledgement_polls = 0;
  const auto& reloaded = check_exact_success(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(reloaded.at("generation") == 2);
  LMDJ_CHECK(coordinator.acknowledged == 2);
  LMDJ_CHECK(
      coordinator.acknowledgement_calls >= calls_before_publication + 3);
}

void test_live_bank_publication_ack_timeout_fails_closed() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 7915, 7916, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));

  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  LMDJ_CHECK(coordinator.acknowledged == 1);

  coordinator.acknowledgement_delay_polls =
      std::numeric_limits<std::uint32_t>::max();
  coordinator.acknowledgement_poll_delay_ms = 10;
  const auto started_at = std::chrono::steady_clock::now();
  check_error(
      runtime->dispatch(
          "snapshot.reload",
          {{"pattern_id", kPatternId}},
          {},
          started_at - std::chrono::milliseconds(29'900)),
      "HOST_TIMEOUT");
  LMDJ_CHECK(
      std::chrono::steady_clock::now() - started_at <
      std::chrono::milliseconds(500));
  check_error(
      runtime->dispatch("host.status", Json::object(), {}),
      "HOST_STATE_INVALID");
}

void test_live_sample_mutations_wait_for_the_exact_bank_acknowledgement() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto initial_wav = mono_pcm16_wav(32);
  import_and_assign(*runtime, initial_wav, kAssetId, 7917, 7918, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));

  FakeCoordinator coordinator;
  coordinator.engine = &runtime->engine();
  coordinator.observe_engine_generation = true;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  LMDJ_CHECK(coordinator.acknowledged == 1);
  ContinuousAudioDriver audio(runtime->engine());

  const auto imported_asset = uuid(7919);
  const auto imported_wav = mono_pcm16_wav(64);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(
          7920, 7921, 2, imported_asset, imported_wav.size(), 1),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(7920, 0, true, imported_wav),
      imported_wav));
  const auto& committed = check_exact_success(
      runtime->dispatch(
          "sample.import.commit", {{"import_token", uuid(7920)}}, {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(committed.at("runtime_published") == true);
  LMDJ_CHECK(coordinator.acknowledged == 2);

  const auto& updated = check_exact_success(
      runtime->dispatch(
          "sample.update_pad",
          {{"command_id", uuid(7922)},
           {"expected_revision", 3},
           {"slot", slot(0, 1)},
           {"playback", playback_payload(0, 32, "gate", -600)}},
          {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(updated.at("runtime_published") == true);
  LMDJ_CHECK(coordinator.acknowledged == 3);

  const auto& reset = check_exact_success(
      runtime->dispatch(
          "sample.reset_pad",
          {{"command_id", uuid(7923)},
           {"expected_revision", 4},
           {"slot", slot(0, 1)}},
          {}),
      {"committed_revision", "runtime_revision", "runtime_published"});
  LMDJ_CHECK(reset.at("runtime_published") == true);
  LMDJ_CHECK(coordinator.acknowledged == 4);
  audio.stop();
}

void check_running_sample_mutation_post_commit_deadline_fails_closed(
    std::string_view operation,
    std::uint32_t suffix,
    bool cross_during_runtime_preparation = false) {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeRuntimeClock clock;
  LMDJ_CHECK(
      ControlRuntimeClockAccess::install(*runtime, clock.seam()).has_value());
  check_success(runtime->dispatch(
      "project.create", create_payload(), {}, clock.current));
  const auto initial_wav = mono_pcm16_wav(32);
  import_and_assign(*runtime, initial_wav, kAssetId, suffix, suffix + 1, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}, clock.current));

  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch(
      "audio.activate", Json::object(), {}, clock.current));
  LMDJ_CHECK(coordinator.acknowledged == 1);
  const auto generation =
      runtime->engine().bank_telemetry().accepted_publications;

  const auto submitted_at = clock.current;
  const auto dispatch_mutation = [&]() {
    if (operation == "sample.import.commit") {
      return runtime->dispatch(
          operation,
          {{"import_token", uuid(suffix + 2)}},
          {},
          submitted_at);
    }
    if (operation == "sample.update_pad") {
      return runtime->dispatch(
          operation,
          {{"command_id", uuid(suffix + 2)},
           {"expected_revision", 2},
           {"slot", slot(0, 0)},
           {"playback", playback_payload(0, 16, "gate", -900)}},
          {},
          submitted_at);
    }
    LMDJ_CHECK(operation == "sample.reset_pad");
    return runtime->dispatch(
        operation,
        {{"command_id", uuid(suffix + 2)},
         {"expected_revision", 2},
         {"slot", slot(0, 0)}},
        {},
        submitted_at);
  };
  if (operation == "sample.import.commit") {
    const auto imported_wav = mono_pcm16_wav(64);
    check_success(runtime->dispatch(
        "sample.import.begin",
        sample_begin_payload(
            suffix + 2,
            suffix + 3,
            2,
            uuid(suffix + 4),
            imported_wav.size(),
            1),
        {},
        clock.current));
    check_success(runtime->dispatch(
        "sample.import.chunk",
        sample_chunk_payload(suffix + 2, 0, true, imported_wav),
        imported_wav,
        clock.current));
  }

  Json response;
  if (cross_during_runtime_preparation) {
    clock.reads = 0;
    // dispatch admission, mutation admission, and the outer post-commit check
    // must all observe time remaining; preparation's publication check is the
    // first read that crosses the deadline.
    clock.cross_deadline_on_read = 4;
    response = dispatch_mutation();
  } else {
    CommitDeadlineCrossing crossing{clock};
    const lmdj::facade::detail::MutationPublishScope publish_scope(
        crossing.token());
    response = dispatch_mutation();
  }

  const auto& timed_out = check_exact_success(
      response,
      {"committed_revision", "runtime_revision", "runtime_published",
       "snapshot_error"});
  LMDJ_CHECK(timed_out.at("committed_revision") == 3);
  LMDJ_CHECK(timed_out.at("runtime_revision") == 2);
  LMDJ_CHECK(timed_out.at("runtime_published") == false);
  LMDJ_CHECK(timed_out.at("snapshot_error").at("code") == "HOST_TIMEOUT");
  LMDJ_CHECK(runtime->failed());
  LMDJ_CHECK(
      runtime->engine().bank_telemetry().accepted_publications == generation);
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 3);
  check_error(
      runtime->dispatch(
          "trigger", {{"slot", 0}, {"velocity", 100}}, {}, clock.current),
      "HOST_STATE_INVALID");
  check_error(
      runtime->dispatch("host.status", Json::object(), {}, clock.current),
      "HOST_STATE_INVALID");
}

void test_running_sample_mutation_post_commit_deadline_fails_closed() {
  check_running_sample_mutation_post_commit_deadline_fails_closed(
      "sample.import.commit", 7'930);
  check_running_sample_mutation_post_commit_deadline_fails_closed(
      "sample.update_pad", 7'940);
  check_running_sample_mutation_post_commit_deadline_fails_closed(
      "sample.reset_pad", 7'950);
}

void test_running_sample_mutation_preparation_deadline_fails_closed() {
  check_running_sample_mutation_post_commit_deadline_fails_closed(
      "sample.import.commit", 7'960, true);
  check_running_sample_mutation_post_commit_deadline_fails_closed(
      "sample.update_pad", 7'970, true);
  check_running_sample_mutation_post_commit_deadline_fails_closed(
      "sample.reset_pad", 7'980, true);
}

void test_audio_reactivation_waits_past_a_stale_bank_acknowledgement() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 7913, 7914, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));

  FakeCoordinator coordinator;
  coordinator.begin_acknowledgement = 2;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  check_success(runtime->dispatch("audio.suspend", Json::object(), {}));

  const auto calls_before_reactivation = coordinator.acknowledgement_calls;
  coordinator.begin_stale_acknowledgement = 1;
  coordinator.acknowledgement_delay_polls = 3;
  coordinator.acknowledgement_polls = 0;
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  LMDJ_CHECK(coordinator.acknowledged_before_begin == 2);
  LMDJ_CHECK(coordinator.acknowledged == 2);
  LMDJ_CHECK(
      coordinator.acknowledgement_calls >= calls_before_reactivation + 3);
}

void test_audio_activation_rolls_back_begin_and_ack_failures() {
  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(8);
    import_and_assign(*runtime, wav, kAssetId, 793, 794, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    FakeCoordinator coordinator;
    coordinator.begin_succeed = false;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
            .has_value());
    check_error(
        runtime->dispatch("audio.activate", Json::object(), {}),
        "INTERNAL_ERROR");
    LMDJ_CHECK(coordinator.called);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::stopped);
    check_error(
        runtime->dispatch("host.status", Json::object(), {}),
        "HOST_STATE_INVALID");
  }

  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(8);
    import_and_assign(*runtime, wav, kAssetId, 795, 796, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    FakeCoordinator coordinator;
    coordinator.begin_acknowledgement = 2;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
            .has_value());
    check_error(
        runtime->dispatch("audio.activate", Json::object(), {}),
        "INTERNAL_ERROR");
    LMDJ_CHECK(coordinator.called);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::stopped);
    check_error(
        runtime->dispatch("host.status", Json::object(), {}),
        "HOST_STATE_INVALID");
  }

  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(8);
    import_and_assign(*runtime, wav, kAssetId, 797, 798, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    FakeCoordinator coordinator;
    coordinator.begin_acknowledgement = 0;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
            .has_value());
    check_error(
        runtime->dispatch("audio.activate", Json::object(), {}),
        "HOST_TIMEOUT");
    LMDJ_CHECK(!coordinator.called);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::running);
    check_error(
        runtime->dispatch("host.status", Json::object(), {}),
        "HOST_STATE_INVALID");
  }
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
    const auto& missing = check_error(
        runtime->dispatch("audio.activate", Json::object(), {}),
        "HOST_STATE_INVALID");
    LMDJ_CHECK(missing.at("message") == "audio output is not ready");
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::stopped);
    check_success(runtime->dispatch("host.status", Json::object(), {}));
  }

  {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(8);
    import_and_assign(*runtime, wav, kAssetId, 811, 812, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    FakeCoordinator failure;
    failure.succeed = false;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, failure.seam())
            .has_value());
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    ContinuousAudioDriver driver(runtime->engine());
    failure.driver = &driver;
    failure.engine = &runtime->engine();
    check_error(
        runtime->dispatch("audio.suspend", Json::object(), {}),
        "INTERNAL_ERROR");
    LMDJ_CHECK(failure.called);
    LMDJ_CHECK(failure.quiescence_established);
    LMDJ_CHECK(driver.stopped());
    LMDJ_CHECK(failure.observed_engine_running);
    LMDJ_CHECK(
        runtime->engine().telemetry().callback_count ==
        failure.callback_count_at_quiescence);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::stopped);
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
    FakeCoordinator success;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, success.seam())
            .has_value());
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    ContinuousAudioDriver driver(runtime->engine());
    success.driver = &driver;
    success.engine = &runtime->engine();
    check_success(runtime->dispatch(
        "sequence.record.begin",
        {{"session_id", kSequenceSessionId},
         {"pattern_id", kPatternId},
         {"expected_revision", 2}},
        {}));
    check_success(runtime->dispatch(
        "trigger", {{"slot", 0}, {"velocity", 100}}, {}));
    check_success(runtime->dispatch(
        "trigger", {{"slot", 0}, {"kind", "release"}}, {}));
    FakeRuntimeClock clock;
    LMDJ_CHECK(
        ControlRuntimeClockAccess::install(*runtime, clock.seam()).has_value());
    const auto& suspended = check_exact_success(
        runtime->dispatch(
            "audio.suspend", Json::object(), {}, clock.current),
        {"state", "changed", "stopped_sequence_id"});
    LMDJ_CHECK((
        suspended ==
        Json{{"state", "audio-suspended"},
             {"changed", true},
             {"stopped_sequence_id", kSequenceSessionId}}));
    LMDJ_CHECK(success.called);
    LMDJ_CHECK(success.timeout_ms >= 1);
    LMDJ_CHECK(success.timeout_ms <= 1'000);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        lmdj::audio::RealtimeState::stopped);
    success.begin_acknowledgement =
        runtime->engine().bank_telemetry().accepted_publications;
    check_success(runtime->dispatch(
        "audio.activate", Json::object(), {}, clock.current));
    LMDJ_CHECK(success.begin_calls == 2);
    const auto& candidates = check_exact_success(
        runtime->dispatch(
            "sequence.recovery.list", Json::object(), {}, clock.current),
        {"candidates", "project_revision"});
    LMDJ_CHECK(candidates.at("candidates").empty());
    LMDJ_CHECK(candidates.at("project_revision").is_null());
  }
}

void test_audio_activation_rechecks_deadline_after_generation_ack() {
  for (const auto begin_succeeds : {true, false}) {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(8);
    import_and_assign(*runtime, wav, kAssetId, 885, 886, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    FakeCoordinator coordinator;
    coordinator.begin_delay_ms = 100;
    coordinator.begin_succeed = begin_succeeds;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
            .has_value());

    check_error(
        runtime->dispatch(
            "audio.activate",
            Json::object(),
            {},
            std::chrono::steady_clock::now() -
                std::chrono::milliseconds(950)),
        "HOST_TIMEOUT");
    LMDJ_CHECK(coordinator.begin_calls == 1);
    LMDJ_CHECK(coordinator.acknowledgement_calls == 0);
    LMDJ_CHECK(!coordinator.called);
    LMDJ_CHECK(
        runtime->engine().telemetry().state ==
        (begin_succeeds ? lmdj::audio::RealtimeState::running
                        : lmdj::audio::RealtimeState::stopped));
    check_error(
        runtime->dispatch("host.status", Json::object(), {}),
        "HOST_STATE_INVALID");
  }
}

void test_audio_activation_ack_wait_uses_original_request_budget() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 887, 888, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  coordinator.begin_acknowledgement = 0;
  coordinator.acknowledgement_delay_polls =
      std::numeric_limits<std::uint32_t>::max();
  coordinator.acknowledgement_poll_delay_ms = 10;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());

  const auto started_at = std::chrono::steady_clock::now();
  check_error(
      runtime->dispatch(
          "audio.activate",
          Json::object(),
          {},
          started_at - std::chrono::milliseconds(900)),
      "HOST_TIMEOUT");
  const auto elapsed = std::chrono::steady_clock::now() - started_at;
  LMDJ_CHECK(elapsed < std::chrono::milliseconds(500));
  LMDJ_CHECK(coordinator.acknowledgement_calls < 20);
  LMDJ_CHECK(!coordinator.called);
  LMDJ_CHECK(
      runtime->engine().telemetry().state ==
      lmdj::audio::RealtimeState::running);
}

void test_audio_activation_rollback_rechecks_the_original_deadline() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 889, 890, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  coordinator.begin_succeed = false;
  coordinator.await_delay_ms = 100;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());

  check_error(
      runtime->dispatch(
          "audio.activate",
          Json::object(),
          {},
          std::chrono::steady_clock::now() -
              std::chrono::milliseconds(950)),
      "HOST_TIMEOUT");
  LMDJ_CHECK(coordinator.called);
  LMDJ_CHECK(coordinator.timeout_ms >= 1);
  LMDJ_CHECK(coordinator.timeout_ms <= 100);
  LMDJ_CHECK(coordinator.acknowledgement_calls == 0);
  LMDJ_CHECK(
      runtime->engine().telemetry().state ==
      lmdj::audio::RealtimeState::stopped);
}

void test_suspend_and_close_pass_only_the_original_remaining_budget() {
  for (const auto operation : {"audio.suspend", "host.close"}) {
    TempDirectory temp;
    auto runtime = make_runtime(temp.path());
    check_success(runtime->dispatch("project.create", create_payload(), {}));
    const auto wav = mono_pcm16_wav(8);
    import_and_assign(*runtime, wav, kAssetId, 895, 896, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    FakeCoordinator coordinator;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
            .has_value());
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    const auto elapsed_budget =
        operation == std::string_view("audio.suspend") ? 750 : 9'750;

    check_success(runtime->dispatch(
        operation,
        Json::object(),
        {},
        std::chrono::steady_clock::now() -
            std::chrono::milliseconds(elapsed_budget)));
    LMDJ_CHECK(coordinator.called);
    LMDJ_CHECK(coordinator.timeout_ms >= 1);
    LMDJ_CHECK(coordinator.timeout_ms <= 300);
  }
}

void test_exact_non_fifo_aggregate_accounting_and_prior_bank_retention() {
  TempDirectory temp;
  constexpr RuntimePreparationLimits limits{
      1'048'576,
      4'096,
      2'052,
      4'104,
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
  FakeCoordinator coordinator;
  coordinator.engine = &runtime->engine();
  coordinator.observe_engine_generation = true;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 127}}, {}));
  audio.render_one();
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 1);

  const auto newer_small = mono_pcm16_wav(1);
  import_and_assign(*runtime, newer_small, uuid(402), 413, 414, 2);
  audio.schedule_bank_transition();
  const auto& second = check_exact_success(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(second.at("generation") == 2);

  const auto current = mono_pcm16_wav(2);
  import_and_assign(*runtime, current, uuid(403), 415, 416, 4);
  audio.schedule_bank_transition();
  const auto& third = check_exact_success(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(third.at("generation") == 3);

  const auto rejected_candidate = mono_pcm16_wav(3);
  import_and_assign(
      *runtime, rejected_candidate, uuid(404), 417, 418, 6);
  const auto& rejected = check_error(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      "WEB_RUNTIME_RESOURCE_LIMIT");
  LMDJ_CHECK(
      rejected.at("message").get<std::string>().find("why:") !=
      std::string::npos);
  LMDJ_CHECK(
      rejected.at("message").get<std::string>().find("remedy:") !=
      std::string::npos);
  const Json expected_residency_details{
      {"resource", "resident_pcm_bytes"},
      {"observed", 4'108},
      {"limit", 4'104},
  };
  if (rejected.at("details") != expected_residency_details) {
    throw std::runtime_error(
        "unexpected residency details: " + rejected.at("details").dump());
  }
  LMDJ_CHECK(runtime->engine().bank_telemetry().current_generation == 3);

  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 127}}, {}));
  audio.render_one();
  LMDJ_CHECK(!runtime->drain_outcomes().empty());
  audio.schedule_bank_transition();
  const auto& after_reclaim = check_exact_success(
      runtime->dispatch(
          "snapshot.reload", {{"pattern_id", kPatternId}}, {}),
      {"project_id", "project_revision", "pattern_id", "runtime_ready",
       "generation", "snapshot_error"});
  LMDJ_CHECK(after_reclaim.at("generation") == 4);
}

void test_host_close_releases_current_and_retired_runtime_banks() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(512);
  import_and_assign(*runtime, wav, kAssetId, 491, 492, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  const auto before = runtime->engine().bank_telemetry();
  LMDJ_CHECK(before.current_generation == 1);

  const auto& closed = check_exact_success(
      runtime->dispatch("host.close", Json::object(), {}),
      {"state", "stopped_sequence_id"});
  LMDJ_CHECK((
      closed == Json{{"state", "closed"}, {"stopped_sequence_id", nullptr}}));
  const auto after = runtime->engine().bank_telemetry();
  LMDJ_CHECK(after.current_generation == 0);
  LMDJ_CHECK(after.accepted_publications == before.accepted_publications);
  LMDJ_CHECK(after.applied_publications == before.applied_publications);
  LMDJ_CHECK(after.reclaimed_banks == before.reclaimed_banks + 1);
  const auto reclaimed =
      runtime->engine().reclaim_retired_bank_telemetry();
  LMDJ_CHECK(reclaimed.count == 0);
  LMDJ_CHECK(reclaimed.decoded_pcm_bytes == 0);

  LMDJ_CHECK(runtime->engine().start().has_value());
  LMDJ_CHECK(
      runtime->engine().enqueue(
          lmdj::audio::TriggerEvent{1, 0, 127}) ==
      lmdj::audio::EnqueueResult::sample_unavailable);
  LMDJ_CHECK(runtime->engine().telemetry().started_voices == 0);
  LMDJ_CHECK(runtime->engine().telemetry().invalid_events == 1);
  runtime->engine().stop();
}

void test_oversized_project_switch_is_inspectable_but_not_runnable() {
  TempDirectory temp;
  constexpr RuntimePreparationLimits limits{
      1'048'576,
      4,
      8,
      16,
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
      "BANK_QUOTA_EXHAUSTED");
  LMDJ_CHECK(opened.at("snapshot_error").at("details").at("bank") == 0);
  LMDJ_CHECK(
      opened.at("snapshot_error").at("details").at("requested_bytes") ==
      8);
  LMDJ_CHECK(
      opened.at("snapshot_error").at("details").at("remaining_bytes") ==
      4);
  LMDJ_CHECK(
      opened.at("snapshot_error").at("message").get<std::string>().find(
          "why:") != std::string::npos);
  LMDJ_CHECK(
      opened.at("snapshot_error").at("message").get<std::string>().find(
          "remedy:") != std::string::npos);
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
    if (self.response_delay_ms != 0) {
      std::this_thread::sleep_for(
          std::chrono::milliseconds(self.response_delay_ms));
    }
    if (std::exchange(self.throw_before_response_serialization, false)) {
      throw std::runtime_error("injected response serialization failure");
    }
  }

  static void after_capture_drain(void* context) {
    auto& self = *static_cast<FakeProxy*>(context);
    if (!std::exchange(self.inject_capture_drop, false)) {
      return;
    }
    LMDJ_CHECK(self.capture_engine != nullptr);
    std::array<float, 1> left{};
    std::array<float, 1> right{};
    self.capture_engine->render(left.data(), right.data(), 1);
  }

  static void after_outcome_drain(void*) {}

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
  bool inject_capture_drop = false;
  std::uint32_t response_delay_ms = 0;
  RealtimeEngine* capture_engine = nullptr;
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
          FakeProxy::before_response_serialization,
          FakeProxy::after_capture_drain,
          FakeProxy::after_outcome_drain});
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

void check_snapshot_published_notification(
    const Json& notification,
    std::uint64_t generation,
    std::uint64_t project_revision) {
  check_exact_keys(notification, {"protocol_version", "event", "payload"});
  LMDJ_CHECK(notification.at("protocol_version") == 1);
  LMDJ_CHECK(notification.at("event") == "snapshot.published");
  LMDJ_CHECK(!notification.contains("request_id"));
  LMDJ_CHECK((
      notification.at("payload") ==
      Json{{"generation", generation},
           {"project_revision", project_revision}}));
}

void test_bridge_routes_sample_operations_without_a_project_path() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(989);
  const auto envelope = encode(request(
      request_id, "sample.inspect", {{"slot", slot(0, 0)}}));

  LMDJ_CHECK(
      bridge->submit(envelope, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto response = poll_message(*bridge);
  check_exact_keys(
      response,
      {"protocol_version", "request_id", "ok", "result"});
  LMDJ_CHECK(response.at("request_id") == request_id);
  const auto& result = response.at("result");
  check_exact_keys(
      result,
      {"project_revision", "slot", "asset_id", "playback", "metadata",
       "waveform_cache_identity"});
  LMDJ_CHECK(result.at("project_revision") == 0);
  const auto encoded_request = std::string(
      reinterpret_cast<const char*>(envelope.data()), envelope.size());
  LMDJ_CHECK(encoded_request.find("project_path") == std::string::npos);
  proxy.pump_one();

  const auto quota_request_id = uuid(990);
  const auto quota_envelope = encode(request(
      quota_request_id, "sample.quota", {{"slot", slot(0, 0)}}));
  LMDJ_CHECK(
      bridge->submit(quota_envelope, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto quota_response = poll_message(*bridge);
  check_exact_keys(
      quota_response,
      {"protocol_version", "request_id", "ok", "result"});
  LMDJ_CHECK(quota_response.at("request_id") == quota_request_id);
  check_exact_keys(
      quota_response.at("result"),
      {"project_revision", "slot", "bank_quota_bytes", "bank_used_bytes",
       "bank_remaining_bytes", "project_quota_bytes", "project_used_bytes",
       "project_remaining_bytes", "effective_remaining_bytes",
       "effective_remaining_frames", "consumed"});
  LMDJ_CHECK(quota_response.at("result").at("project_revision") == 0);
  const auto encoded_quota_request = std::string(
      reinterpret_cast<const char*>(quota_envelope.data()),
      quota_envelope.size());
  LMDJ_CHECK(encoded_quota_request.find("project_path") == std::string::npos);
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

void
test_bridge_reserves_response_capacity_under_realtime_notification_pressure() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(256);
  import_and_assign(*runtime, wav, kAssetId, 721, 722, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());

  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto activate_id = uuid(723);
  const auto activate = encode(request(
      activate_id, "audio.activate", Json::object()));
  LMDJ_CHECK(
      bridge->submit(activate, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  LMDJ_CHECK(poll_message(*bridge).at("request_id") == activate_id);
  proxy.pump_one();

  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "trigger", {{"slot", 0}, {"velocity", 127}}, {}));
  audio.render_one();
  proxy.pump_one();

  // Each poll frees one notification slot and schedules another realtime
  // drain. Each drain has both an outcome and a Voice-state batch available,
  // so without a reserved response slot the notification stream can occupy
  // every fixed message slot before the next control request is processed.
  for (std::size_t index = 0; index + 2 < kBridgeMessageSlotCount; ++index) {
    const auto notification = poll_message(*bridge);
    LMDJ_CHECK(!notification.contains("request_id"));
    check_success(runtime->dispatch(
        "trigger", {{"slot", 0}, {"velocity", 127}}, {}));
    audio.render_one();
    proxy.pump_one();
  }

  const auto status_id = uuid(724);
  const auto status = encode(request(
      status_id, "host.status", Json::object()));
  LMDJ_CHECK(
      bridge->submit(status, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();

  bool found_response = false;
  for (std::size_t index = 0; index < kBridgeMessageSlotCount; ++index) {
    const auto message = poll_message(*bridge);
    if (message.value("request_id", "") == status_id) {
      LMDJ_CHECK(message.at("ok") == true);
      found_response = true;
      break;
    }
  }
  LMDJ_CHECK(found_response);
  LMDJ_CHECK(!bridge->failed());
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
    {
      auto builder = make_runtime(temp.path());
      check_success(builder->dispatch(
          "project.create", create_payload(), {}));
    }
    auto runtime = make_runtime(temp.path());
    FakeProxy proxy;
    auto bridge = make_bridge(*runtime, proxy);
    const auto open = encode(request(
        uuid(900),
        "project.open",
        {{"project_id", kProjectId}, {"pattern_id", kPatternId}}));
    LMDJ_CHECK(
        bridge->submit(open, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();
    LMDJ_CHECK(poll_message(*bridge).at("ok") == true);
    const auto notification = poll_message(*bridge);
    LMDJ_CHECK(notification.at("event") == "snapshot.published");
    LMDJ_CHECK((
        notification.at("payload") == Json{{"generation", 1}}));
  }

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
        4,
        8,
        16,
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
        "BANK_QUOTA_EXHAUSTED");

    const auto notification = poll_message(*bridge);
    check_exact_keys(
        notification, {"protocol_version", "event", "payload"});
    LMDJ_CHECK(notification.at("event") == "snapshot.rejected");
    LMDJ_CHECK(!notification.contains("request_id"));
    check_exact_keys(notification.at("payload"), {"error"});
    LMDJ_CHECK(
        notification.at("payload").at("error").at("code") ==
        "BANK_QUOTA_EXHAUSTED");
    check_no_bridge_message(*bridge);
  }
}

void test_bridge_emits_sample_publication_notifications_after_response() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(32);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(481, 482, 0, kAssetId, wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(481, 0, true, wav),
      wav));

  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto commit = encode(request(
      uuid(921),
      "sample.import.commit",
      {{"import_token", uuid(481)}}));
  LMDJ_CHECK(
      bridge->submit(commit, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto commit_response = poll_message(*bridge);
  LMDJ_CHECK(commit_response.at("request_id") == uuid(921));
  LMDJ_CHECK(commit_response.at("ok") == true);
  LMDJ_CHECK(commit_response.at("result").at("committed_revision") == 1);
  check_snapshot_published_notification(poll_message(*bridge), 1, 1);
  proxy.pump_one();
  const auto status_after_commit = check_locked_success_result(
      runtime->dispatch("host.status", Json::object(), {}));
  LMDJ_CHECK(status_after_commit.at("control_generation") == 1);

  const Json update_payload{
      {"command_id", uuid(483)},
      {"expected_revision", 1},
      {"slot", slot(0, 0)},
      {"playback", playback_payload(0, 16, "gate", -600)}};
  const auto update = encode(request(
      uuid(922), "sample.update_pad", update_payload));
  LMDJ_CHECK(
      bridge->submit(update, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto update_response = poll_message(*bridge);
  LMDJ_CHECK(update_response.at("request_id") == uuid(922));
  LMDJ_CHECK(update_response.at("ok") == true);
  LMDJ_CHECK(update_response.at("result").at("committed_revision") == 2);
  check_snapshot_published_notification(poll_message(*bridge), 2, 2);
  proxy.pump_one();

  const auto reset = encode(request(
      uuid(923),
      "sample.reset_pad",
      {{"command_id", uuid(484)},
       {"expected_revision", 2},
       {"slot", slot(0, 0)}}));
  LMDJ_CHECK(
      bridge->submit(reset, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto reset_response = poll_message(*bridge);
  LMDJ_CHECK(reset_response.at("request_id") == uuid(923));
  LMDJ_CHECK(reset_response.at("ok") == true);
  LMDJ_CHECK(reset_response.at("result").at("committed_revision") == 3);
  check_snapshot_published_notification(poll_message(*bridge), 3, 3);
  proxy.pump_one();
  const auto status_after_reset = check_locked_success_result(
      runtime->dispatch("host.status", Json::object(), {}));
  LMDJ_CHECK(status_after_reset.at("control_generation") == 3);

  const auto replay = encode(request(
      uuid(929), "sample.update_pad", update_payload));
  LMDJ_CHECK(
      bridge->submit(replay, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto replay_response = poll_message(*bridge);
  LMDJ_CHECK(replay_response.at("request_id") == uuid(929));
  LMDJ_CHECK(replay_response.at("ok") == true);
  LMDJ_CHECK(replay_response.at("result").at("committed_revision") == 2);
  LMDJ_CHECK(replay_response.at("result").at("runtime_revision") == 3);
  LMDJ_CHECK(replay_response.at("result").at("runtime_published") == true);
  check_snapshot_published_notification(poll_message(*bridge), 4, 3);
  check_no_bridge_message(*bridge);
  proxy.pump_one();
  const auto status_after_replay = check_locked_success_result(
      runtime->dispatch("host.status", Json::object(), {}));
  LMDJ_CHECK(status_after_replay.at("project_revision") == 3);
  LMDJ_CHECK(status_after_replay.at("control_generation") == 4);

  const auto malformed = encode(request(
      uuid(924),
      "sample.update_pad",
      {{"command_id", uuid(485)},
       {"expected_revision", 3},
       {"slot", slot(0, 0)}}));
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

  const auto conflict = encode(request(
      uuid(925),
      "sample.reset_pad",
      {{"command_id", uuid(486)},
       {"expected_revision", 2},
       {"slot", slot(0, 0)}}));
  LMDJ_CHECK(
      bridge->submit(conflict, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto conflict_response = poll_message(*bridge);
  LMDJ_CHECK(conflict_response.at("ok") == false);
  LMDJ_CHECK(
      conflict_response.at("error").at("code") == "REVISION_CONFLICT");
  check_no_bridge_message(*bridge);
}

void test_bridge_emits_commit_quota_rejection_without_snapshot_notification() {
  TempDirectory temp;
  constexpr RuntimePreparationLimits limits{
      1'048'576,
      16,
      134'217'728,
      268'435'456,
  };
  auto runtime = make_runtime(temp.path(), limits);
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto first_wav = mono_pcm16_wav(2);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(487, 488, 0, kAssetId, first_wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(487, 0, true, first_wav),
      first_wav));
  check_success(runtime->dispatch(
      "sample.import.commit", {{"import_token", uuid(487)}}, {}));

  const Json replayed_update_payload{
      {"command_id", uuid(493)},
      {"expected_revision", 1},
      {"slot", slot(0, 0)},
      {"playback", playback_payload(0, 1, "gate", -300)}};
  const auto updated = check_locked_success_result(runtime->dispatch(
      "sample.update_pad", replayed_update_payload, {}));
  LMDJ_CHECK(updated.at("committed_revision") == 2);
  LMDJ_CHECK(updated.at("runtime_revision") == 2);
  LMDJ_CHECK(updated.at("runtime_published") == true);

  const auto larger_wav = mono_pcm16_wav(8);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(489, 490, 2, uuid(491), larger_wav.size()),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(489, 0, true, larger_wav),
      larger_wav));

  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto commit = encode(request(
      uuid(926),
      "sample.import.commit",
      {{"import_token", uuid(489)}}));
  LMDJ_CHECK(
      bridge->submit(commit, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == uuid(926));
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(
      response.at("error").at("code") == "BANK_QUOTA_EXHAUSTED");
  LMDJ_CHECK(response.at("error").at("details").at("bank") == 0);
  LMDJ_CHECK(
      response.at("error").at("details").at("remaining_frames") == 4);
  LMDJ_CHECK(
      response.at("error").at("details").at("consumed").size() == 1);
  check_no_bridge_message(*bridge);
  proxy.pump_one();
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") == 2);

  const auto unknown = encode(request(
      uuid(928),
      "sample.import.commit",
      {{"import_token", uuid(492)}}));
  LMDJ_CHECK(
      bridge->submit(unknown, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto unknown_response = poll_message(*bridge);
  LMDJ_CHECK(unknown_response.at("ok") == false);
  LMDJ_CHECK(
      unknown_response.at("error").at("code") == "INVALID_ARGUMENT");
  check_no_bridge_message(*bridge);
  LMDJ_CHECK(
      runtime->engine().bank_telemetry().accepted_publications == 2);
}

void test_bridge_rejects_an_expired_control_request_without_late_success() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(990);
  const auto status = encode(request(
      request_id, "host.status", Json::object()));

  LMDJ_CHECK(
      bridge->submit(status, {}) == BridgeSubmitStatus::accepted);
  std::this_thread::sleep_for(std::chrono::milliseconds(1'050));
  proxy.pump_one();
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == "HOST_TIMEOUT");
  proxy.pump_one();
  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(
      bridge->poll(output, required) == BridgePollStatus::failed);
  check_error(
      runtime->dispatch("host.status", Json::object(), {}),
      "HOST_STATE_INVALID");
}

void test_bridge_cancelled_before_dispatch_skips_facade_work() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch(
      "project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(989);
  const auto import = encode(request(
      request_id,
      "asset.import",
      import_payload(989, 0, kAssetId, wav)));

  LMDJ_CHECK(bridge->configure_deadline_proof(request_id, 1, false));
  LMDJ_CHECK(
      bridge->submit(import, wav) == BridgeSubmitStatus::accepted);
  std::jthread control([&] { proxy.pump_one(); });
  wait_until([&] {
    return (bridge->deadline_proof_state(request_id) & (1 << 8)) != 0;
  });
  LMDJ_CHECK(
      bridge->cancel(request_id) == BridgeCancelStatus::cancelled);
  control.join();

  const auto proof = bridge->deadline_proof_state(request_id);
  LMDJ_CHECK((proof & (1 << 9)) == 0);
  LMDJ_CHECK(bridge->terminal_release_ready());
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == "HOST_TIMEOUT");
  proxy.pump_one();
  LMDJ_CHECK(std::filesystem::is_empty(
      temp.path() / "projects" /
      (std::string(kProjectId) + ".lmdj") / "assets"));
  LMDJ_CHECK(std::filesystem::is_empty(
      temp.path() / "projects" /
      (std::string(kProjectId) + ".lmdj") / "history/transactions"));
}

void test_bridge_benign_query_cancel_does_not_fail_the_runtime() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const std::array<std::pair<std::string_view, Json>, 5> queries{{
      {"sample.inspect", {{"slot", slot(0, 0)}}},
      {"sample.quota", {{"slot", slot(0, 0)}}},
      {"sample.waveform",
       {{"slot", slot(0, 0)},
        {"window",
         {{"start_frame", 0}, {"end_frame", 1}, {"bucket_count", 1}}}}},
      {"project.inspect", Json::object()},
      {"project.list", Json::object()},
  }};

  for (std::size_t index = 0; index < queries.size(); ++index) {
    const auto request_id = uuid(1'100 + index);
    const auto query = encode(request(
        request_id, queries[index].first, queries[index].second));
    LMDJ_CHECK(
        bridge->submit(query, {}) == BridgeSubmitStatus::accepted);
    LMDJ_CHECK(
        bridge->cancel_query(request_id) == BridgeCancelStatus::cancelled);
    proxy.pump_one();
    const auto response = poll_message(*bridge);
    LMDJ_CHECK(response.at("request_id") == request_id);
    LMDJ_CHECK(response.at("ok") == false);
    LMDJ_CHECK(response.at("error").at("code") == "HOST_STATE_INVALID");
    proxy.pump_one();
    check_no_bridge_message(*bridge);
  }
  check_success(runtime->dispatch("host.status", Json::object(), {}));
}

void test_bridge_rechecks_deadline_before_success_publication() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  proxy.response_delay_ms = 1'050;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(991);
  const auto status = encode(request(
      request_id, "host.status", Json::object()));

  LMDJ_CHECK(
      bridge->submit(status, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == "HOST_TIMEOUT");
  proxy.pump_one();
  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(
      bridge->poll(output, required) == BridgePollStatus::failed);
}

void test_bridge_uses_the_caller_deadline_as_the_authoritative_upper_bound() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(994);
  const auto status = encode(request(
      request_id, "host.status", Json::object()));

  LMDJ_CHECK(
      bridge->submit(status, {}, std::chrono::steady_clock::now()) ==
      BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == "HOST_TIMEOUT");
  proxy.pump_one();
  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(
      bridge->poll(output, required) == BridgePollStatus::failed);
}

void test_bridge_preserves_a_pre_deadline_publication_claim_to_settlement() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(998);
  const auto import = encode(request(
      request_id,
      "asset.import",
      import_payload(998, 0, kAssetId, wav)));

  LMDJ_CHECK(bridge->configure_deadline_proof(request_id, 2, false));
  const auto caller_deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(2);
  LMDJ_CHECK(
      bridge->submit(
          import,
          wav,
          caller_deadline) ==
      BridgeSubmitStatus::accepted);
  std::jthread control([&] { proxy.pump_one(); });
  wait_until([&] {
    const auto state = bridge->deadline_proof_state(request_id);
    return (state & 0xff) == 2 &&
           (state & (1 << 9)) != 0 &&
           (state & (1 << 10)) != 0;
  });
  std::this_thread::sleep_until(
      caller_deadline + std::chrono::milliseconds(50));
  LMDJ_CHECK(bridge->release_deadline_proof());
  control.join();

  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == true);
  const auto& result = response.at("result");
  check_exact_keys(
      result,
      {"asset_id", "artifact", "committed_revision", "replayed",
       "project_revision"});
  LMDJ_CHECK(result.at("project_revision") == 1);
  LMDJ_CHECK(!runtime->failed());
  LMDJ_CHECK(!bridge->failed());
  proxy.pump_one();
  check_no_bridge_message(*bridge);
}

void test_bridge_passes_the_absolute_caller_deadline_into_audio_activation() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 995, 996, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));

  FakeCoordinator coordinator;
  coordinator.begin_stale_acknowledgement = 0;
  coordinator.acknowledgement_delay_polls =
      std::numeric_limits<std::uint32_t>::max();
  coordinator.acknowledgement_poll_delay_ms = 10;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());

  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(997);
  const auto activation = encode(request(
      request_id, "audio.activate", Json::object()));
  const auto started_at = std::chrono::steady_clock::now();
  LMDJ_CHECK(
      bridge->submit(
          activation,
          {},
          started_at + std::chrono::milliseconds(100)) ==
      BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto elapsed = std::chrono::steady_clock::now() - started_at;

  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == "HOST_TIMEOUT");
  LMDJ_CHECK(elapsed >= std::chrono::milliseconds(80));
  LMDJ_CHECK(elapsed < std::chrono::milliseconds(400));
  // The elapsed deadline is authoritative. Sanitizer scheduling may reduce
  // the number of 10 ms polling sleeps that fit in that interval, so require
  // proof that acknowledgement was observed without coupling the contract to
  // a wall-clock polling count.
  LMDJ_CHECK(coordinator.acknowledgement_calls != 0);
  LMDJ_CHECK(runtime->failed());
  LMDJ_CHECK(bridge->failed());
  const auto terminal_acknowledgement_calls =
      coordinator.acknowledgement_calls;
  std::this_thread::sleep_for(std::chrono::milliseconds(50));
  LMDJ_CHECK(
      coordinator.acknowledgement_calls == terminal_acknowledgement_calls);
  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(
      bridge->poll(output, required) == BridgePollStatus::failed);
}

void test_bridge_rechecks_deadline_before_error_publication() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  proxy.response_delay_ms = 1'050;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(993);
  const auto malformed = encode(request(
      request_id, "host.status", {{"unexpected", true}}));

  LMDJ_CHECK(
      bridge->submit(malformed, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == "HOST_TIMEOUT");
  proxy.pump_one();
  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(
      bridge->poll(output, required) == BridgePollStatus::failed);
}

void test_internal_audio_activation_timeout_is_terminal_after_response() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(8);
  import_and_assign(*runtime, wav, kAssetId, 981, 982, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  coordinator.acknowledgement_delay_polls =
      std::numeric_limits<std::uint32_t>::max();
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(992);
  const auto activation = encode(request(
      request_id, "audio.activate", Json::object()));

  LMDJ_CHECK(
      bridge->submit(activation, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == "HOST_TIMEOUT");
  proxy.pump_one();
  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(
      bridge->poll(output, required) == BridgePollStatus::failed);
}

void test_bridge_preserves_error_responses_for_an_externally_failed_runtime() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  runtime->fail_and_seal("external_audio_failure");
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);

  for (const auto suffix : {994U, 995U}) {
    const auto request_id = uuid(suffix);
    const auto status = encode(request(
        request_id, "host.status", Json::object()));
    LMDJ_CHECK(
        bridge->submit(status, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();
    const auto response = poll_message(*bridge);
    LMDJ_CHECK(response.at("request_id") == request_id);
    LMDJ_CHECK(response.at("ok") == false);
    LMDJ_CHECK(
        response.at("error").at("code") == "HOST_STATE_INVALID");
    proxy.pump_one();
    LMDJ_CHECK(!bridge->failed());
  }
}

}  // namespace

int main() {
  try {
    test_one_shot_bank_transition_waits_for_accepted_queue_commit();
    test_one_shot_bank_transition_renders_until_target_is_applied();
    test_one_shot_bank_transition_rejects_overlap_until_completion();
    test_facade_error_details_follow_an_explicit_safe_schema();
    test_project_bundle_stream_delegates_to_facade_and_lists_summary();
    test_host_close_aborts_active_project_bundle_import();
    test_runtime_cancellation_precedes_project_mutation();
    test_exact_payloads_and_facade_owned_project_journey();
    test_sequence_observer_busy_and_owner_loss_recovery();
    test_owner_loss_cleanup_failure_stops_and_clears_the_overlay();
    test_pending_sequence_overlay_repeats_and_commits_without_duplicate();
    test_stop_replay_recovers_a_committed_clean_publication_failure();
    test_authoritative_switch_supersedes_overlay_and_stop_cancels_target();
    test_stop_fails_closed_if_target_applies_between_cancel_queries();
    test_bpm_publication_then_switch_flushes_old_events_at_exact_boundary();
    test_sequence_switch_prepares_before_selecting_bar_boundary();
    test_sequence_switch_supersedes_a_near_boundary_recording_overlay();
    test_sample_editing_binds_current_project_and_drives_fixed_controls();
    test_sample_import_prevents_current_project_switch_until_terminal();
    test_sample_import_protocol_failure_aborts_staging();
    test_sample_import_timeout_aborts_staging_and_fails_closed();
    test_sample_commit_quota_failure_keeps_truth_and_runtime_unchanged();
    test_sample_post_claim_deadline_preserves_saved_truth();
    test_source_frames_are_admitted_by_prepared_pcm_quota();
    test_trigger_queue_full_is_admission_failure();
    test_voice_capacity_is_sequence_addressed_execution_outcome();
    test_audio_activation_requires_ready_and_reports_explicit_ack();
    test_audio_reactivation_waits_past_a_stale_bank_acknowledgement();
    test_live_bank_publication_waits_for_the_exact_acknowledgement();
    test_live_bank_publication_ack_timeout_fails_closed();
    test_live_sample_mutations_wait_for_the_exact_bank_acknowledgement();
    test_running_sample_mutation_post_commit_deadline_fails_closed();
    test_running_sample_mutation_preparation_deadline_fails_closed();
    test_audio_activation_rolls_back_begin_and_ack_failures();
    test_audio_suspend_requires_and_honors_quiescence_coordinator();
    test_audio_activation_rechecks_deadline_after_generation_ack();
    test_audio_activation_ack_wait_uses_original_request_budget();
    test_audio_activation_rollback_rechecks_the_original_deadline();
    test_suspend_and_close_pass_only_the_original_remaining_budget();
    test_exact_non_fifo_aggregate_accounting_and_prior_bank_retention();
    test_host_close_releases_current_and_retired_runtime_banks();
    test_oversized_project_switch_is_inspectable_but_not_runnable();
    test_bridge_routes_sample_operations_without_a_project_path();
    test_bridge_defers_parse_dispatch_and_copies_fixed_slots();
    test_bridge_rejects_duplicates_until_response_consumption();
    test_bridge_response_backpressure_fails_before_mutation();
    test_bridge_reserves_response_capacity_under_realtime_notification_pressure();
    test_bridge_exception_reuses_the_reserved_response_slot();
    test_bridge_release_proxy_failure_is_a_terminal_transport_signal();
    test_bridge_emits_only_real_snapshot_notifications_after_response();
    test_bridge_emits_sample_publication_notifications_after_response();
    test_bridge_emits_commit_quota_rejection_without_snapshot_notification();
    test_bridge_rejects_an_expired_control_request_without_late_success();
    test_bridge_cancelled_before_dispatch_skips_facade_work();
    test_bridge_benign_query_cancel_does_not_fail_the_runtime();
    test_bridge_rechecks_deadline_before_success_publication();
    test_bridge_uses_the_caller_deadline_as_the_authoritative_upper_bound();
    test_bridge_preserves_a_pre_deadline_publication_claim_to_settlement();
    test_bridge_passes_the_absolute_caller_deadline_into_audio_activation();
    test_bridge_rechecks_deadline_before_error_publication();
    test_internal_audio_activation_timeout_is_terminal_after_response();
    test_bridge_preserves_error_responses_for_an_externally_failed_runtime();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "web control runtime tests: PASS\n";
  return 0;
}
