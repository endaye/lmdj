#include <lmdj/web_runtime/control_runtime.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
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
#include <lmdj/facade/assembly_loader.hpp>
#include <lmdj/facade/mutation_publish_scope.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
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

ApplicationConfig make_application_config(
    const std::filesystem::path& root,
    RuntimePreparationLimits limits = kWebLimits) {
  return ApplicationConfig{
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
  };
}

Application make_application(
    const std::filesystem::path& root,
    RuntimePreparationLimits limits = kWebLimits) {
  return Application(make_application_config(root, limits));
}

std::unique_ptr<ControlRuntime> make_runtime(
    const std::filesystem::path& root,
    RuntimePreparationLimits limits = kWebLimits) {
  auto created = ControlRuntime::create(
      root, make_application_config(root, limits), limits);
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

  // Read the Contract level the Store persisted instead of naming one here;
  // a hardcoded level stops describing the Project when the writer moves.
  const auto entry_text = [&](std::string_view relative) {
    const auto found = std::find_if(
        source_entries.begin(),
        source_entries.end(),
        [&](const auto& item) { return item.path == relative; });
    LMDJ_CHECK(found != source_entries.end());
    return std::string{
        reinterpret_cast<const char*>(found->bytes.data()),
        found->bytes.size()};
  };
  const auto manifest = Json::parse(entry_text("manifest.json"));
  const auto head = Json::parse(
      entry_text(manifest.at("head_checkpoint").get<std::string>()));
  const auto project_contract = head.at("contract").get<std::string>();

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
      {"contract_version", "1.3.0"},
      {"entries", std::move(encoded_entries)},
      {"project_contract", project_contract},
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
    self.current += self.advance_per_read;
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
  std::chrono::steady_clock::duration advance_per_read{0};
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
       "limits", "audio_state", "capture_state", "pattern_transport"});
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
  LMDJ_CHECK(current.at("project").at("contract") == "lmdj.project.v5");
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
      Json::parse(checkpoint_text).at("contract") == "lmdj.project.v5");

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

void test_audio_activation_prepares_master_fx_for_perform() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));

  LMDJ_CHECK(runtime->engine().master_fx_telemetry().current_bpm == 120);
  LMDJ_CHECK(
      runtime->engine().enqueue_fx_gesture(lmdj::audio::FxGesture{
          lmdj::audio::FxGestureKind::hold_off,
          lmdj::domain::PerformanceFx::filter,
          0}) == lmdj::audio::FxEnqueueResult::accepted);
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
       "limits", "audio_state", "capture_state", "pattern_transport"});
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
       "limits", "audio_state", "capture_state", "pattern_transport"});
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
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  // The fake clock keeps 250ms of the original 1000ms request budget through
  // instrumented master FX preparation, so rollback always reaches
  // quiescence; the fifth clock read is the post-rollback recheck of the
  // original deadline, which then crosses it deterministically.
  FakeRuntimeClock clock;
  clock.cross_deadline_on_read = 5;
  LMDJ_CHECK(
      ControlRuntimeClockAccess::install(*runtime, clock.seam()).has_value());

  check_error(
      runtime->dispatch(
          "audio.activate",
          Json::object(),
          {},
          clock.current - std::chrono::milliseconds(750)),
      "HOST_TIMEOUT");
  LMDJ_CHECK(coordinator.called);
  LMDJ_CHECK(coordinator.timeout_ms >= 1);
  LMDJ_CHECK(coordinator.timeout_ms <= 250);
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
       "limits", "audio_state", "capture_state", "pattern_transport"});
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
    // Runs while a dispatch is in progress and before its response exists:
    // the point at which, in the browser, Asyncify has suspended the dispatch
    // and the proxying mailbox may run the next task.
    if (self.during_dispatch) {
      auto during = std::exchange(self.during_dispatch, nullptr);
      during();
    }
  }

  static void after_capture_drain(void* context) {
    auto& self = *static_cast<FakeProxy*>(context);
    ++self.capture_drains;
    // Runs inside the realtime service: the point at which, in the browser,
    // service_performance() may have suspended in OPFS and the mailbox may run
    // the next task.
    if (self.during_realtime_service) {
      auto during = std::exchange(self.during_realtime_service, nullptr);
      during();
    }
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
    run_as_control(task);
  }

  void pump_last() {
    LMDJ_CHECK(!tasks.empty());
    auto task = tasks.back();
    tasks.pop_back();
    run_as_control(task);
  }

  void run_as_control(const Task& task) {
    // Nested pumps model the mailbox running inside a suspended dispatch, so
    // they must leave the outer task's control-thread identity intact.
    const auto previous = std::exchange(is_control, true);
    task.function(task.argument);
    is_control = previous;
  }

  bool accept = true;
  bool is_control = false;
  bool throw_before_response_serialization = false;
  bool inject_capture_drop = false;
  std::uint32_t response_delay_ms = 0;
  RealtimeEngine* capture_engine = nullptr;
  std::function<void()> during_dispatch;
  std::function<void()> during_realtime_service;
  std::size_t capture_drains = 0;
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

// Stage 11's Sound Set operations reach the Facade through the Web Host with
// the exact locked field sets, and only the two Project-scoped ones learn a
// Project. Browsing, inspecting and auditioning the Workspace Set Store
// follows the `provider.list` precedent: it needs no open Project, and it
// never carries a Workspace field.
void test_soundset_operations_route_at_the_workspace_and_the_project() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());

  // No Project is open yet, and the Workspace-level query still answers.
  const auto listed = check_locked_success_result(
      runtime->dispatch("soundset.catalog.list", Json::object(), {}));
  check_exact_keys(
      listed,
      {"project_revision", "catalog_available", "sets", "refused"});
  LMDJ_CHECK(listed.at("catalog_available") == false);
  LMDJ_CHECK(listed.at("sets").empty());

  const Json identity{
      {"set_id", "11111111-1111-4111-8111-111111111111"},
      {"version", "1.0.0"},
      {"manifest_sha256", std::string(64, 'a')},
  };
  // Not in the Set Store, but refused by the Facade rather than by the Host's
  // session gate: the operation reached Core.
  check_error(
      runtime->dispatch("soundset.inspect", identity, {}), "NOT_FOUND");

  // Every locked shape is exact, and a stray Workspace field is refused by
  // the Host before the Facade ever sees it.
  auto stray = identity;
  stray["workspace_path"] = temp.path().generic_string();
  check_error(
      runtime->dispatch("soundset.inspect", stray, {}),
      "HOST_PROTOCOL_MISMATCH");
  check_error(
      runtime->dispatch(
          "soundset.catalog.list",
          {{"workspace_path", temp.path().generic_string()}},
          {}),
      "HOST_PROTOCOL_MISMATCH");
  auto preview = identity;
  preview["bank_id"] = 1;
  // The two Project-scoped operations never carry a project_path of their
  // own; the Host injects the retained Project.
  auto preview_with_project = preview;
  preview_with_project["project_path"] = temp.path().generic_string();
  check_error(
      runtime->dispatch("soundset.map.preview", preview_with_project, {}),
      "HOST_PROTOCOL_MISMATCH");
  check_error(
      runtime->dispatch("soundset.map.preview", identity, {}),
      "HOST_PROTOCOL_MISMATCH");
  auto out_of_range = preview;
  out_of_range["bank_id"] = 4;
  check_error(
      runtime->dispatch("soundset.map.preview", out_of_range, {}),
      "HOST_PROTOCOL_MISMATCH");

  // S11-D5's audition is Workspace-level like `inspect`: no open Project, no
  // Project field, and the optional `slot_index` is bounded by SLOT_MAX.
  check_error(
      runtime->dispatch("soundset.audition", identity, {}), "NOT_FOUND");
  auto audition_slot = identity;
  audition_slot["slot_index"] = 15;
  check_error(
      runtime->dispatch("soundset.audition", audition_slot, {}), "NOT_FOUND");
  auto audition_out_of_range = identity;
  audition_out_of_range["slot_index"] = 16;
  check_error(
      runtime->dispatch("soundset.audition", audition_out_of_range, {}),
      "HOST_PROTOCOL_MISMATCH");
  auto audition_with_project = identity;
  audition_with_project["project_path"] = temp.path().generic_string();
  check_error(
      runtime->dispatch("soundset.audition", audition_with_project, {}),
      "HOST_PROTOCOL_MISMATCH");

  // #799. Stopping is a Host operation: it addresses this Host's engine, not a
  // Set, so it takes an empty payload and never reaches the Facade -- which has
  // no such operation and would answer it through `attempt_inspect`.
  //
  // Idempotent by design. Stopping with nothing auditioning succeeds, which is
  // what keeps it inside the frozen error vocabulary: there is no "nothing to
  // stop" condition, so no reason token is needed for one.
  const auto stopped = runtime->dispatch("soundset.audition.stop", Json::object(), {});
  LMDJ_CHECK(stopped.at("ok").get<bool>());
  LMDJ_CHECK(stopped.at("result").at("accepted").get<bool>());
  const auto stopped_again = runtime->dispatch("soundset.audition.stop", Json::object(), {});
  LMDJ_CHECK(stopped_again.at("ok").get<bool>());

  // It addresses no Set, so any identity field is a protocol error rather than
  // an ignored extra -- the same exact-keys discipline as its siblings.
  check_error(
      runtime->dispatch("soundset.audition.stop", identity, {}),
      "HOST_PROTOCOL_MISMATCH");

  auto install = preview;
  install["command_id"] = uuid(4101);
  install["expected_revision"] = 0;
  auto bad_policy = install;
  bad_policy["occupied_pad_policy"] = "overwrite";
  check_error(
      runtime->dispatch("soundset.install", bad_policy, {}),
      "HOST_PROTOCOL_MISMATCH");

  // Without an open Project the two Project-scoped operations are the ones
  // the Host state gate refuses.
  check_error(
      runtime->dispatch("soundset.map.preview", preview, {}),
      "HOST_STATE_INVALID");
  check_error(
      runtime->dispatch("soundset.install", install, {}),
      "HOST_STATE_INVALID");

  // With a Project open they reach the Facade, which refuses on the Set
  // rather than on the Host state.
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  check_error(
      runtime->dispatch("soundset.map.preview", preview, {}), "NOT_FOUND");
  auto second_install = install;
  second_install["occupied_pad_policy"] = "keep";
  check_error(
      runtime->dispatch("soundset.install", second_install, {}),
      "NOT_FOUND");
}

// The transport itself, without a Facade in front of it. Everything the
// browser side can reach is checked here, because the Set Store's own
// independent verification would otherwise mask a transport that verified
// nothing: both refuse a tampered Set, so only a direct read distinguishes
// them.
void test_host_supplied_catalog_verifies_what_it_serves() {
  using lmdj::project_io::CatalogObjectKind;
  using lmdj::project_io::CatalogObjectRef;

  const auto handle = lmdj::facade::make_supplied_soundset_catalog(64, 2);
  auto& control = *handle.control;
  auto& transport = *handle.transport;
  auto& source = *handle.source;
  const std::string payload = "sound-set-object";
  std::vector<std::byte> bytes(payload.size());
  std::transform(
      payload.begin(), payload.end(), bytes.begin(), [](char value) {
        return static_cast<std::byte>(static_cast<unsigned char>(value));
      });
  const auto digest = picosha2::hash256_hex_string(payload);

  // A miss is an unreachable Catalog and records the address exactly once,
  // however many times Core asks.
  const auto missed = transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, digest}, 1024);
  LMDJ_CHECK(!missed.has_value());
  LMDJ_CHECK(missed.error().code == lmdj::foundation::ErrorCode::io_error);
  LMDJ_CHECK(missed.error().details.at("reason") == "catalog_unavailable");
  LMDJ_CHECK(!transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, digest}, 1024).has_value());
  // The same digest under the other kind is a different address.
  LMDJ_CHECK(!transport.read_object(
      CatalogObjectRef{CatalogObjectKind::manifest, digest}, 1024).has_value());
  auto pending = control.drain_pending();
  LMDJ_CHECK(!pending.index);
  LMDJ_CHECK(pending.objects.size() == 2);
  LMDJ_CHECK(pending.objects.at(0).object_kind == "blob");
  LMDJ_CHECK(pending.objects.at(0).sha256 == digest);
  LMDJ_CHECK(pending.objects.at(1).object_kind == "manifest");
  LMDJ_CHECK(control.drain_pending().objects.empty());

  // An address that is not a lowercase sha256 is not an address at all, and
  // is never recorded as something the Host could go and fetch.
  LMDJ_CHECK(!transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, "../secret"}, 1024).has_value());
  LMDJ_CHECK(control.drain_pending().objects.empty());

  // Bytes that do not hash to the address they were staged under never reach
  // Core, and re-asking cannot help, so the address stays off the pending set.
  LMDJ_CHECK(control.supply("blob", std::string(64, 'b'), 0, bytes.size(), bytes).has_value());
  const auto mismatched = transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, std::string(64, 'b')}, 1024);
  LMDJ_CHECK(!mismatched.has_value());
  LMDJ_CHECK(mismatched.error().details.at("reason") == "soundset_content_mismatch");
  LMDJ_CHECK(control.drain_pending().objects.empty());

  // A staged address serves its own bytes, and supplying it clears it from the
  // pending set.
  LMDJ_CHECK(!transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, digest}, 1024).has_value());
  LMDJ_CHECK(control.supply("blob", digest, 0, bytes.size(), bytes).has_value());
  LMDJ_CHECK(control.drain_pending().objects.empty());
  const auto served = transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, digest}, 1024);
  LMDJ_CHECK(served.has_value());
  LMDJ_CHECK(served.value() == bytes);
  // The caller's own bound still decides, and being over it is not a fault in
  // the Set.
  const auto bounded = transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, digest}, 4);
  LMDJ_CHECK(!bounded.has_value());
  LMDJ_CHECK(bounded.error().details.at("reason") == "catalog_unavailable");

  // Host staging capacity is decided before an allocation: 64 bytes and two
  // objects are already spent by the two staged above.
  LMDJ_CHECK(!control.supply("manifest", std::string(64, 'c'), 0, bytes.size(), bytes).has_value());
  control.clear_staged();
  LMDJ_CHECK(control.supply("manifest", std::string(64, 'c'), 0, bytes.size(), bytes).has_value());
  std::vector<std::byte> oversized(65, std::byte{0});
  LMDJ_CHECK(!control.supply("blob", std::string(64, 'd'), 0, oversized.size(), oversized).has_value());

  // Only the two locked kinds and only a lowercase sha256 name an object.
  LMDJ_CHECK(!control.supply("index", digest, 0, bytes.size(), bytes).has_value());
  LMDJ_CHECK(!control.supply("archive", digest, 0, bytes.size(), bytes).has_value());
  LMDJ_CHECK(!control.supply("blob", "manifest/" + digest, 0, bytes.size(), bytes).has_value());
  LMDJ_CHECK(!control.supply("blob", std::string(64, 'B'), 0, bytes.size(), bytes).has_value());

  // A chunked object is readable only when the whole of it has arrived, and a
  // run that does not continue the one in flight is refused rather than
  // stitched into a Set nobody sent.
  control.clear_staged();
  const std::span<const std::byte> whole(bytes);
  LMDJ_CHECK(
      control.supply("blob", digest, 0, bytes.size(), whole.first(4)).value() ==
      false);
  LMDJ_CHECK(!transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, digest}, 1024).has_value());
  // Wrong offset, wrong declared length, and a different address mid-run.
  LMDJ_CHECK(!control.supply("blob", digest, 5, bytes.size(), whole.subspan(5))
                  .has_value());
  LMDJ_CHECK(!control.supply("blob", digest, 4, bytes.size() + 1,
                             whole.subspan(4)).has_value());
  LMDJ_CHECK(!control.supply("manifest", digest, 4, bytes.size(),
                             whole.subspan(4)).has_value());
  // A chunk that runs past the declared length is refused whole.
  LMDJ_CHECK(!control.supply("blob", digest, 0, 2, whole).has_value());
  LMDJ_CHECK(
      control.supply("blob", digest, 0, bytes.size(), whole.first(4)).value() ==
      false);
  LMDJ_CHECK(
      control.supply("blob", digest, 4, bytes.size(), whole.subspan(4))
          .value() == true);
  LMDJ_CHECK(transport.read_object(
      CatalogObjectRef{CatalogObjectKind::blob, digest}, 1024).has_value());
  control.clear_staged();

  // The index is the second, separate read: absent, present, and withdrawn.
  const auto no_index = source.read_index(1024);
  LMDJ_CHECK(!no_index.has_value());
  LMDJ_CHECK(no_index.error().details.at("reason") == "catalog_unavailable");
  LMDJ_CHECK(control.drain_pending().index);
  LMDJ_CHECK(!control.drain_pending().index);
  LMDJ_CHECK(control.supply_index(bytes).has_value());
  LMDJ_CHECK(source.read_index(1024).has_value());
  control.forget_index();
  LMDJ_CHECK(!source.read_index(1024).has_value());
}

// The Web Host's own half of the Sound Set Catalog. S11-D6 gives a Catalog
// adapter exactly one power, and these three Host-local operations are the
// whole of the browser side's access to it: stage the Catalog index, stage one
// object addressed by `{object_kind, sha256}`, and read back the addresses
// Core asked for and could not be served. There is no path, URL, archive
// member or third object kind anywhere in that surface, and a request that is
// not one of those shapes is refused rather than repaired.
void test_host_supplied_catalog_resolves_only_addressed_objects() {
  TempDirectory temp;
  const std::filesystem::path corpus =
      std::filesystem::path(LMDJ_SOURCE_DIR) / "tests/fixtures/soundset";
  LMDJ_CHECK(std::filesystem::is_directory(corpus));

  auto catalog = lmdj::facade::make_supplied_soundset_catalog(
      4ULL * 1024ULL * 1024ULL, 256);
  auto config = make_application_config(temp.path());
  config.soundset_catalog_transport = catalog.transport;
  config.soundset_catalog_source = catalog.source;
  auto created = ControlRuntime::create(temp.path(), std::move(config), kWebLimits);
  LMDJ_CHECK(created.has_value());
  auto runtime = std::move(created.value());

  const auto read_fixture = [&corpus](const std::filesystem::path& relative) {
    std::ifstream stream(corpus / relative, std::ios::binary);
    LMDJ_CHECK(stream.good());
    const std::string text(
        (std::istreambuf_iterator<char>(stream)),
        std::istreambuf_iterator<char>());
    std::vector<std::byte> bytes(text.size());
    std::transform(
        text.begin(), text.end(), bytes.begin(), [](char value) {
          return static_cast<std::byte>(static_cast<unsigned char>(value));
        });
    return bytes;
  };

  // Nothing has been asked for yet.
  const auto empty = check_exact_success(
      runtime->dispatch("soundset.catalog.pending", Json::object(), {}),
      {"index", "objects"});
  LMDJ_CHECK(empty.at("index") == false);
  LMDJ_CHECK(empty.at("objects").empty());

  // An unreachable Catalog is not fatal, and the Host learns that the index is
  // the read that failed.
  const auto cold = check_locked_success_result(
      runtime->dispatch("soundset.catalog.list", Json::object(), {}));
  LMDJ_CHECK(cold.at("catalog_available") == false);
  LMDJ_CHECK(cold.at("sets").empty());
  const auto wanted_index = check_locked_success_result(
      runtime->dispatch("soundset.catalog.pending", Json::object(), {}));
  LMDJ_CHECK(wanted_index.at("index") == true);
  LMDJ_CHECK(wanted_index.at("objects").empty());

  // Only the two locked kinds, only a lowercase sha256, and only those two
  // fields. Every other spelling is refused before a byte is staged.
  const auto index_bytes = read_fixture("catalog/index.json");
  check_error(
      runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", "manifest"}, {"sha256", std::string(64, 'a')},
           {"offset", 0}, {"byte_length", index_bytes.size()},
           {"url", "https://example.invalid/object"}},
          index_bytes),
      "HOST_PROTOCOL_MISMATCH");
  check_error(
      runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", "manifest"}, {"offset", 0}},
          index_bytes),
      "HOST_PROTOCOL_MISMATCH");
  check_error(
      runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", "archive"}, {"sha256", std::string(64, 'a')},
           {"offset", 0}, {"byte_length", index_bytes.size()}},
          index_bytes),
      "INVALID_ARGUMENT");
  check_error(
      runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", "index"}, {"sha256", std::string(64, 'a')},
           {"offset", 0}, {"byte_length", index_bytes.size()}},
          index_bytes),
      "INVALID_ARGUMENT");
  check_error(
      runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", "blob"}, {"sha256", "../../../etc/passwd"},
           {"offset", 0}, {"byte_length", index_bytes.size()}},
          index_bytes),
      "INVALID_ARGUMENT");
  check_error(
      runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", "blob"}, {"sha256", std::string(64, 'A')},
           {"offset", 0}, {"byte_length", index_bytes.size()}},
          index_bytes),
      "INVALID_ARGUMENT");
  // The index is not an object of either locked kind, so it never travels on
  // the object surface, and an absent index carries no bytes.
  check_error(
      runtime->dispatch(
          "soundset.catalog.index", {{"available", false}}, index_bytes),
      "HOST_PROTOCOL_MISMATCH");
  check_error(
      runtime->dispatch(
          "soundset.catalog.index",
          {{"available", true}, {"sha256", std::string(64, 'a')}},
          index_bytes),
      "HOST_PROTOCOL_MISMATCH");

  check_exact_success(
      runtime->dispatch(
          "soundset.catalog.index", {{"available", true}}, index_bytes),
      {"staged"});

  // Every address Core asks for is one basename under one object kind, and
  // one pass of the loop below stages exactly the addresses of the last pass.
  Json listed;
  std::vector<std::string> addresses;
  for (int round = 0; round < 32; ++round) {
    listed = check_locked_success_result(
        runtime->dispatch("soundset.catalog.list", Json::object(), {}));
    const auto pending = check_locked_success_result(
        runtime->dispatch("soundset.catalog.pending", Json::object(), {}));
    LMDJ_CHECK(pending.at("index") == false);
    if (pending.at("objects").empty()) {
      break;
    }
    for (const auto& object : pending.at("objects")) {
      check_exact_keys(object, {"object_kind", "sha256"});
      const auto kind = object.at("object_kind").get<std::string>();
      const auto sha256 = object.at("sha256").get<std::string>();
      LMDJ_CHECK(kind == "manifest" || kind == "blob");
      LMDJ_CHECK(sha256.size() == 64);
      addresses.push_back(kind + "/" + sha256);
      // An object crosses the bridge in as many messages as it needs, and is
      // readable only once the last one has arrived.
      const auto bytes = read_fixture(std::filesystem::path(kind) / sha256);
      const auto half = bytes.size() / 2;
      const auto first = check_locked_success_result(runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", kind}, {"sha256", sha256}, {"offset", 0},
           {"byte_length", bytes.size()}},
          std::span<const std::byte>(bytes).first(half)));
      LMDJ_CHECK(first.at("staged") == false);
      const auto last = check_locked_success_result(runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", kind}, {"sha256", sha256}, {"offset", half},
           {"byte_length", bytes.size()}},
          std::span<const std::byte>(bytes).subspan(half)));
      LMDJ_CHECK(last.at("staged") == true);
    }
  }
  LMDJ_CHECK(!addresses.empty());
  // One address is one download: the Attribution Kit's demo declares its own
  // slot 0 hash, and the Foundry CC0 Set reuses slot 0's Artifact on slot 12.
  auto unique = addresses;
  std::sort(unique.begin(), unique.end());
  LMDJ_CHECK(std::unique(unique.begin(), unique.end()) == unique.end());

  LMDJ_CHECK(listed.at("catalog_available") == true);
  const auto set_named = [&listed](std::string_view name) {
    for (const auto& entry : listed.at("sets")) {
      if (entry.at("name") == name) {
        return entry;
      }
    }
    throw std::runtime_error("Set is not listed: " + std::string(name));
  };
  // The CC-BY-4.0 attribution string reaches listing through the Web Host.
  const auto attribution_kit = set_named("Fixture Attribution Kit");
  LMDJ_CHECK(attribution_kit.at("license").at("spdx_id") == "CC-BY-4.0");
  LMDJ_CHECK(
      !attribution_kit.at("license").at("attribution").get<std::string>().empty());
  const auto foundry = set_named("Fixture Foundry CC0");
  LMDJ_CHECK(foundry.at("has_demo") == true);

  // An ineligible or corrupted Set is named among the refusals with its own
  // public reason rather than vanishing, and the eligible Sets beside it still
  // list. Which layer refused the tampered bytes is not asserted here: the Set
  // Store verifies independently of the transport, and
  // `test_host_supplied_catalog_verifies_what_it_serves` is what pins the
  // transport's own check.
  const auto refused_reason = [&listed](std::string_view manifest_sha256) {
    for (const auto& entry : listed.at("refused")) {
      if (entry.at("manifest_sha256") == manifest_sha256) {
        return entry.at("reason").get<std::string>();
      }
    }
    throw std::runtime_error("Set is not refused: " + std::string(manifest_sha256));
  };
  LMDJ_CHECK(
      refused_reason(
          "00a4700e06a3006d23b7e1b70a09295076c1009c119bd6d3950361ff9892df8e") ==
      "soundset_content_mismatch");
  LMDJ_CHECK(
      refused_reason(
          "9bdf31630ae7edb863a6520d0b6bebabf45d4b63416b75f1e4ab5086e3ba9592") ==
      "soundset_license_ineligible");

  // Supplied objects live for one listing pass. Core has published what it
  // accepted into the Workspace Set Store, so opening the next pass frees the
  // crossing buffer -- otherwise the two Host bounds would be lifetime totals
  // and a long session would quietly stop being able to acquire anything.
  check_exact_success(
      runtime->dispatch(
          "soundset.catalog.index", {{"available", true}}, index_bytes),
      {"staged"});
  check_locked_success_result(
      runtime->dispatch("soundset.catalog.list", Json::object(), {}));
  const auto reasked = check_locked_success_result(
      runtime->dispatch("soundset.catalog.pending", Json::object(), {}));
  // Every published Set is idempotent and asks for nothing; only the Sets the
  // Set Store never accepted come back, and they come back from an empty
  // staging area rather than being served a second time from it.
  LMDJ_CHECK(!reasked.at("objects").empty());

  // S11-D7: the Catalog going away leaves every published Set listable.
  check_exact_success(
      runtime->dispatch("soundset.catalog.index", {{"available", false}}, {}),
      {"staged"});
  const auto offline = check_locked_success_result(
      runtime->dispatch("soundset.catalog.list", Json::object(), {}));
  LMDJ_CHECK(offline.at("catalog_available") == false);
  LMDJ_CHECK(offline.at("sets").size() == listed.at("sets").size());
  LMDJ_CHECK(!offline.at("sets").empty());
}

// A Host that wired no Catalog transport has no browser side to stage into,
// and says so rather than pretending to accept bytes.
void test_host_catalog_operations_need_a_wired_transport() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_error(
      runtime->dispatch("soundset.catalog.pending", Json::object(), {}),
      "HOST_STATE_INVALID");
  check_error(
      runtime->dispatch("soundset.catalog.index", {{"available", true}}, {}),
      "HOST_STATE_INVALID");
  check_error(
      runtime->dispatch(
          "soundset.catalog.supply",
          {{"object_kind", "blob"}, {"sha256", std::string(64, 'a')},
           {"offset", 0}, {"byte_length", 0}},
          {}),
      "HOST_STATE_INVALID");
}

// #799, review finding. A Sound Set audition answered `ok` whether or not any
// sound came out of it. `played` is that missing fact: it sits beside the
// geometry on the successful result and says whether a voice actually started.
// It is not a refusal and adds no `lmdj.error.v1` code and no `details.reason`
// token -- reporting *which* branch produced a silence would need exactly the
// vocabulary the Stage froze, so only the fact is carried.
//
// The defect this catches: a Host that publishes a snapshot, never activates
// audio, auditions a Set, and is told the audition succeeded. That is not a
// hypothetical -- `enqueue_control` refuses every event while the engine is
// stopped, so it is the answer every headless Host gets.
std::vector<std::byte> read_soundset_fixture(
    const std::filesystem::path& relative) {
  const std::filesystem::path corpus =
      std::filesystem::path(LMDJ_SOURCE_DIR) / "tests/fixtures/soundset";
  std::ifstream stream(corpus / relative, std::ios::binary);
  LMDJ_CHECK(stream.good());
  const std::string text(
      (std::istreambuf_iterator<char>(stream)),
      std::istreambuf_iterator<char>());
  std::vector<std::byte> bytes(text.size());
  std::transform(
      text.begin(), text.end(), bytes.begin(), [](char value) {
        return static_cast<std::byte>(static_cast<unsigned char>(value));
      });
  return bytes;
}

// Drive the Host's own Catalog surface until the Workspace Set Store holds
// every eligible fixture Set, and answer with the last listing. Auditioning
// needs a real published Set: the geometry, the decode and the PCM all come
// from the Set Store, so a synthetic identity would only ever reach NOT_FOUND.
Json publish_fixture_soundsets(ControlRuntime& runtime) {
  const auto index_bytes = read_soundset_fixture("catalog/index.json");
  check_locked_success_result(runtime.dispatch(
      "soundset.catalog.index", {{"available", true}}, index_bytes));
  Json listed;
  for (int round = 0; round < 32; ++round) {
    listed = check_locked_success_result(
        runtime.dispatch("soundset.catalog.list", Json::object(), {}));
    const auto pending = check_locked_success_result(
        runtime.dispatch("soundset.catalog.pending", Json::object(), {}));
    if (pending.at("objects").empty()) {
      break;
    }
    for (const auto& object : pending.at("objects")) {
      const auto kind = object.at("object_kind").get<std::string>();
      const auto sha256 = object.at("sha256").get<std::string>();
      const auto bytes =
          read_soundset_fixture(std::filesystem::path(kind) / sha256);
      check_locked_success_result(runtime.dispatch(
          "soundset.catalog.supply",
          {{"object_kind", kind}, {"sha256", sha256}, {"offset", 0},
           {"byte_length", bytes.size()}},
          bytes));
    }
  }
  LMDJ_CHECK(listed.at("catalog_available") == true);
  return listed;
}

// Every outcome a caller can actually reach, in the order a Host passes
// through them. Reachability is not uniform and the legs say which is which:
// three of `play_audition`'s four early returns cannot be reached through the
// Facade at all, because `prepared_audition` refuses their exact conditions
// with `cook_failed` before `play_audition` is entered and the dispatch only
// calls it after the same `audition_soundset` already answered `ok`. Those
// three stay as contract checks and are deliberately not claimed as covered.
// What is covered is the pool refusal, the discarded enqueue result, the
// dispatch's own `runtime_ready` guard, and the success.
void test_soundset_audition_reports_whether_a_voice_started() {
  TempDirectory temp;
  auto catalog = lmdj::facade::make_supplied_soundset_catalog(
      4ULL * 1024ULL * 1024ULL, 256);
  auto config = make_application_config(temp.path());
  config.soundset_catalog_transport = catalog.transport;
  config.soundset_catalog_source = catalog.source;
  auto created =
      ControlRuntime::create(temp.path(), std::move(config), kWebLimits);
  LMDJ_CHECK(created.has_value());
  auto runtime = std::move(created.value());

  const auto listed = publish_fixture_soundsets(*runtime);
  Json foundry;
  for (const auto& entry : listed.at("sets")) {
    if (entry.at("name") == "Fixture Foundry CC0") {
      foundry = entry;
    }
  }
  LMDJ_CHECK(foundry.is_object());
  // The set-level demo, so every leg auditions the same bytes and the only
  // variable across them is the state of this Host's engine.
  LMDJ_CHECK(foundry.at("has_demo") == true);
  const Json identity{
      {"set_id", foundry.at("set_id")},
      {"version", foundry.at("version")},
      {"manifest_sha256", foundry.at("manifest_sha256")},
  };

  // Leg 1 -- no Project, so no runtime. The dispatch's `runtime_ready` guard
  // is the outermost of the silent paths and the only one that never touches
  // the engine at all.
  const auto cold = check_locked_success_result(
      runtime->dispatch("soundset.audition", identity, {}));
  // The metadata answer is correct and useful, which is why this is a success
  // and not a refusal: the Facade really did resolve, gate and decode bytes.
  LMDJ_CHECK(cold.at("audio").at("prepared_frames").get<std::uint64_t>() > 0);
  LMDJ_CHECK(cold.at("played") == false);

  // Leg 2 -- a published snapshot with a stopped engine. This is the defect in
  // its most ordinary form: `runtime_ready` is true, the audition Bank really
  // is published, and `enqueue_control` still refuses because nothing is
  // rendering. Before `played`, this answered exactly like leg 4 below and
  // exactly like an audition that made a sound.
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(32);
  import_and_assign(*runtime, wav, kAssetId, 7991, 7992, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  const auto ready = check_locked_success_result(
      runtime->dispatch("host.status", Json::object(), {}));
  LMDJ_CHECK(ready.at("runtime_ready") == true);
  LMDJ_CHECK(
      runtime->engine().telemetry().state ==
      lmdj::audio::RealtimeState::stopped);
  const auto committed =
      inspect_project(temp.path(), kProjectId).at("project_revision");
  const auto silent = check_locked_success_result(
      runtime->dispatch("soundset.audition", identity, {}));
  LMDJ_CHECK(silent.at("played") == false);

  // Leg 3 -- a running engine. Far side: a voice really is rendering, so
  // `played == true` is a statement about the audio thread and not about how
  // far down `play_audition` got.
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  LMDJ_CHECK(
      runtime->engine().telemetry().state ==
      lmdj::audio::RealtimeState::running);
  OneShotAudioDriver audio(runtime->engine());
  const auto audible = check_locked_success_result(
      runtime->dispatch("soundset.audition", identity, {}));
  LMDJ_CHECK(audible.at("played") == true);
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 0);
  audio.render_one();
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 1);

  // Leg 4 -- the audition pool. Two Banks, and nothing in this Host reclaims
  // them, so leg 2's Bank is still held and leg 3's is current: the next
  // audition is refused by `publish_audition_bank`. That refusal used to be
  // invisible.
  const auto exhausted = check_locked_success_result(
      runtime->dispatch("soundset.audition", identity, {}));
  LMDJ_CHECK(exhausted.at("played") == false);
  // and it is the audition pool that refused, not the Project's.
  LMDJ_CHECK(runtime->engine().bank_telemetry().bank_slot_rejections == 0);

  // Auditioning is a query with respect to Project Truth in every one of those
  // states. The far side has to be read from the Project itself rather than
  // from the reply: `soundset.audition` is Workspace-scoped, so the Facade
  // never learns a Project and the envelope's `project_revision` is `null`
  // even with one open -- comparing those nulls would assert nothing.
  LMDJ_CHECK(silent.at("project_revision").is_null());
  LMDJ_CHECK(audible.at("project_revision").is_null());
  LMDJ_CHECK(exhausted.at("project_revision").is_null());
  LMDJ_CHECK(
      inspect_project(temp.path(), kProjectId).at("project_revision") ==
      committed);
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

// Under Asyncify the control thread returns to its event loop while
// runtime.dispatch() waits on OPFS, and the mailbox then runs the next proxied
// request. Asyncify cannot be re-entered on one thread, so that second request
// must wait for the first dispatch to return and be re-proxied afterwards.
// before_response_serialization is the harness's window into "dispatch in
// progress": request B's thunk is pumped from inside request A's dispatch.
void test_bridge_defers_a_request_whose_thunk_runs_during_a_dispatch() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto first_id = uuid(760);
  const auto second_id = uuid(761);
  LMDJ_CHECK(
      bridge->submit(encode(request(first_id, "host.status", Json::object())), {}) ==
      BridgeSubmitStatus::accepted);
  LMDJ_CHECK(
      bridge->submit(encode(request(second_id, "host.status", Json::object())), {}) ==
      BridgeSubmitStatus::accepted);
  LMDJ_CHECK(proxy.tasks.size() == 2);

  bool second_ran_during_first = false;
  proxy.during_dispatch = [&] {
    // The mailbox delivers B while A is suspended. B's thunk is still at the
    // front: it was proxied before anything A's own dispatch may have queued.
    const auto queued_before = proxy.tasks.size();
    proxy.pump_one();
    second_ran_during_first = true;
    // B must not have been dispatched: no response exists for either request
    // yet, the bridge is healthy, and B was parked rather than re-proxied
    // while A still owns the control thread.
    check_no_bridge_message(*bridge);
    LMDJ_CHECK(!bridge->failed());
    LMDJ_CHECK(proxy.tasks.size() == queued_before - 1);
  };
  proxy.pump_one();
  LMDJ_CHECK(second_ran_during_first);

  // A completed and published first; B was re-proxied after A returned and
  // answers only once its own thunk runs again.
  const auto first = poll_message(*bridge);
  LMDJ_CHECK(first.at("request_id") == first_id);
  LMDJ_CHECK(first.at("ok") == true);
  check_no_bridge_message(*bridge);
  LMDJ_CHECK(!proxy.tasks.empty());

  std::optional<Json> second;
  for (std::size_t budget = proxy.tasks.size(); budget > 0 && !second; --budget) {
    proxy.pump_one();
    std::array<std::byte, kBridgeMaximumEnvelopeBytes> output{};
    std::size_t required = 0;
    if (bridge->poll(output, required) == BridgePollStatus::message) {
      const auto* text = reinterpret_cast<const char*>(output.data());
      second = Json::parse(text, text + required);
    }
  }
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(second->at("request_id") == second_id);
  LMDJ_CHECK(second->at("ok") == true);
  LMDJ_CHECK(!bridge->failed());
  LMDJ_CHECK(!runtime->failed());
}

// The realtime service reaches OPFS through Asyncify when a launch
// acknowledgement applies (service_performance appends the durable tail). A
// request the mailbox delivers while that service is suspended must park
// behind it exactly as it parks behind a suspended dispatch; dispatching it
// inline would suspend Asyncify a second time and the worker would never
// answer again (#656).
void test_bridge_parks_requests_during_the_realtime_service() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  LMDJ_CHECK(runtime->engine().start().has_value());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);

  // Realtime service arms only after a dispatch observes the running engine.
  LMDJ_CHECK(
      bridge->submit(encode(request(uuid(809), "host.status", Json::object())), {}) ==
      BridgeSubmitStatus::accepted);
  proxy.pump_one();
  LMDJ_CHECK(poll_message(*bridge).at("ok") == true);
  while (!proxy.tasks.empty()) proxy.pump_one();

  // An empty poll asks for realtime service; the proxy now holds its thunk.
  check_no_bridge_message(*bridge);
  LMDJ_CHECK(proxy.tasks.size() == 1);

  const auto request_id = uuid(810);
  bool parked_during_service = false;
  proxy.during_realtime_service = [&] {
    LMDJ_CHECK(
        bridge->submit(encode(request(request_id, "host.status", Json::object())), {}) ==
        BridgeSubmitStatus::accepted);
    const auto queued_before = proxy.tasks.size();
    // The mailbox runs the request thunk while the service owns the thread.
    proxy.pump_last();
    parked_during_service = true;
    // Parked, not dispatched: no response exists, nothing failed, and the
    // request was not re-proxied while the service still owns the thread.
    check_no_bridge_message(*bridge);
    LMDJ_CHECK(!bridge->failed());
    LMDJ_CHECK(proxy.tasks.size() == queued_before - 1);
  };
  proxy.pump_one();
  LMDJ_CHECK(parked_during_service);
  LMDJ_CHECK(!bridge->failed());
  LMDJ_CHECK(!runtime->failed());

  // The service returned and handed the parked request back to the mailbox;
  // it answers only once its own thunk runs again.
  LMDJ_CHECK(!proxy.tasks.empty());
  std::optional<Json> response;
  for (std::size_t budget = proxy.tasks.size() + 2; budget > 0 && !response; --budget) {
    if (proxy.tasks.empty()) break;
    proxy.pump_one();
    std::array<std::byte, kBridgeMaximumEnvelopeBytes> output{};
    std::size_t required = 0;
    if (bridge->poll(output, required) == BridgePollStatus::message) {
      const auto* text = reinterpret_cast<const char*>(output.data());
      response = Json::parse(text, text + required);
    }
  }
  LMDJ_CHECK(response.has_value());
  LMDJ_CHECK(response->at("request_id") == request_id);
  LMDJ_CHECK(response->at("ok") == true);
  LMDJ_CHECK(!bridge->failed());
  LMDJ_CHECK(!runtime->failed());
}

// Sealing the runtime aborts imports and so reaches OPFS through Asyncify. A
// failure observed by a foreign mailbox task while a dispatch is suspended must
// set the failure flags at once but seal only after that dispatch returns.
void test_bridge_defers_the_seal_when_a_failure_lands_during_a_dispatch() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto first_id = uuid(770);
  LMDJ_CHECK(
      bridge->submit(encode(request(first_id, "host.status", Json::object())), {}) ==
      BridgeSubmitStatus::accepted);

  bool failure_deferred_seal = false;
  proxy.during_dispatch = [&] {
    // Exhaust the request slots while A is suspended: the overflow submit
    // schedules fail_thunk, which the mailbox then runs during A.
    for (std::uint32_t index = 0; index < 15; ++index) {
      LMDJ_CHECK(
          bridge->submit(
              encode(request(uuid(780 + index), "host.status", Json::object())),
              {}) == BridgeSubmitStatus::accepted);
    }
    LMDJ_CHECK(
        bridge->submit(
            encode(request(uuid(799), "host.status", Json::object())), {}) ==
        BridgeSubmitStatus::queue_full);
    LMDJ_CHECK(bridge->failed());
    proxy.pump_last();
    // The bridge is failed, but the runtime is not yet sealed: that would
    // re-enter Asyncify while A is suspended.
    LMDJ_CHECK(bridge->failed());
    LMDJ_CHECK(!runtime->failed());
    failure_deferred_seal = true;
  };
  proxy.pump_one();
  LMDJ_CHECK(failure_deferred_seal);
  // A has returned; the deferred seal ran from resume_deferred().
  LMDJ_CHECK(runtime->failed());
  LMDJ_CHECK(bridge->failed());
}

namespace {
struct ForeignTaskCounter {
  int runs = 0;
};

void bump_foreign_task(void* context) noexcept {
  ++static_cast<ForeignTaskCounter*>(context)->runs;
}
}  // namespace

// Control-thread tasks proxied from outside the bridge (audio failure,
// manifest failure, coordinator install) ask the same gate. While a dispatch
// is in progress they are parked and re-proxied afterwards; terminal release is
// not ready while the control thread is owned that way.
void test_bridge_parks_foreign_control_tasks_during_a_dispatch() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  ForeignTaskCounter counter;

  // Idle: the caller runs its task itself, and release is ready.
  LMDJ_CHECK(!bridge->defer_while_dispatching(&bump_foreign_task, &counter));
  LMDJ_CHECK(bridge->terminal_release_ready());

  const auto request_id = uuid(800);
  LMDJ_CHECK(
      bridge->submit(encode(request(request_id, "host.status", Json::object())), {}) ==
      BridgeSubmitStatus::accepted);
  bool parked_during_dispatch = false;
  proxy.during_dispatch = [&] {
    LMDJ_CHECK(!bridge->terminal_release_ready());
    const auto queued_before = proxy.tasks.size();
    LMDJ_CHECK(bridge->defer_while_dispatching(&bump_foreign_task, &counter));
    LMDJ_CHECK(counter.runs == 0);
    // Parked, not proxied, while the dispatch owns the control thread.
    LMDJ_CHECK(proxy.tasks.size() == queued_before);
    parked_during_dispatch = true;
  };
  proxy.pump_one();
  LMDJ_CHECK(parked_during_dispatch);
  LMDJ_CHECK(counter.runs == 0);
  LMDJ_CHECK(bridge->terminal_release_ready());
  LMDJ_CHECK(poll_message(*bridge).at("request_id") == request_id);

  // Re-proxied after the dispatch returned; it runs on its own mailbox turn.
  for (std::size_t budget = proxy.tasks.size(); budget > 0 && counter.runs == 0; --budget) {
    proxy.pump_one();
  }
  LMDJ_CHECK(counter.runs == 1);
  LMDJ_CHECK(!bridge->failed());
}

// The realtime service drains Runtime state that dispatch also writes, and its
// health checks seal the Runtime directly, so the whole service -- not only its
// seal -- waits for a suspended dispatch and runs once it has returned.
void test_bridge_parks_the_realtime_service_during_a_dispatch() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(256);
  import_and_assign(*runtime, wav, kAssetId, 811, 812, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());

  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto activate_id = uuid(813);
  LMDJ_CHECK(
      bridge->submit(
          encode(request(activate_id, "audio.activate", Json::object())), {}) ==
      BridgeSubmitStatus::accepted);
  proxy.pump_one();
  LMDJ_CHECK(poll_message(*bridge).at("request_id") == activate_id);
  // Settle: run whatever the activation and its poll scheduled, so no realtime
  // service is pending when the probe request starts.
  while (!proxy.tasks.empty()) {
    proxy.pump_one();
  }

  const auto probe_id = uuid(814);
  LMDJ_CHECK(
      bridge->submit(encode(request(probe_id, "host.status", Json::object())), {}) ==
      BridgeSubmitStatus::accepted);
  bool service_parked = false;
  proxy.during_dispatch = [&] {
    // A poll from the browser main thread while the dispatch is suspended
    // requests realtime service, which proxies the service thunk; the mailbox
    // then delivers it during the dispatch.
    std::array<std::byte, kBridgeMaximumEnvelopeBytes> output{};
    std::size_t required = 0;
    static_cast<void>(bridge->poll(output, required));
    LMDJ_CHECK(!proxy.tasks.empty());
    const auto drains_before = proxy.capture_drains;
    proxy.pump_last();
    LMDJ_CHECK(proxy.capture_drains == drains_before);
    service_parked = true;
  };
  const auto drains_before_probe = proxy.capture_drains;
  proxy.pump_one();
  LMDJ_CHECK(service_parked);
  LMDJ_CHECK(proxy.capture_drains == drains_before_probe);

  // The service was re-proxied after the dispatch returned and runs now.
  for (std::size_t budget = proxy.tasks.size();
       budget > 0 && proxy.capture_drains == drains_before_probe; --budget) {
    proxy.pump_one();
  }
  LMDJ_CHECK(proxy.capture_drains == drains_before_probe + 1);
  LMDJ_CHECK(!bridge->failed());
  LMDJ_CHECK(!runtime->failed());
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
  FakeRuntimeClock clock;
  clock.advance_per_read = std::chrono::milliseconds(10);
  LMDJ_CHECK(
      ControlRuntimeClockAccess::install(*runtime, clock.seam()).has_value());

  FakeProxy proxy;
  auto bridge = make_bridge(*runtime, proxy);
  const auto request_id = uuid(997);
  const auto activation = encode(request(
      request_id, "audio.activate", Json::object()));
  const auto started_at = std::chrono::steady_clock::now();
  clock.current = started_at;
  LMDJ_CHECK(
      bridge->submit(
          activation,
          {},
          started_at + std::chrono::milliseconds(100)) ==
      BridgeSubmitStatus::accepted);
  proxy.pump_one();

  const auto response = poll_message(*bridge);
  LMDJ_CHECK(response.at("request_id") == request_id);
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == "HOST_TIMEOUT");
  // Runtime-side deadline accounting runs on the fake clock anchored at the
  // caller deadline, so acknowledgement polling is bounded by the 100ms
  // caller budget instead of wall-clock scheduling: six 10ms advances reach
  // the deadline, while falling through to the 1s operation default would
  // poll an order of magnitude longer.
  LMDJ_CHECK(coordinator.acknowledgement_calls != 0);
  LMDJ_CHECK(coordinator.acknowledgement_calls <= 10);
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

std::unique_ptr<ControlRuntime> make_provider_runtime(const std::filesystem::path& root) {
  auto assembly = lmdj::facade::load_installed_assembly(
      std::filesystem::path{LMDJ_TEST_ASSEMBLY_PATH});
  LMDJ_CHECK(assembly.has_value());
  auto config = make_application_config(root);
  config.providers = assembly.value().providers;
  config.provider_policy = assembly.value().provider_policy;
  auto created = ControlRuntime::create(root, std::move(config), kWebLimits);
  LMDJ_CHECK(created.has_value());
  return std::move(created.value());
}

void test_candidate_host_owns_paths_pcm_stop_and_atomic_adoption() {
  TempDirectory temp;
  auto runtime = make_provider_runtime(temp.path());
  check_success(runtime->dispatch("provider.permissions.configure",
    {{"granted_permissions", Json::array({"sample.slice.execute"})}}, {}));
  check_success(runtime->dispatch("provider.select",
    {{"capability", "sample.slice.v1"}, {"provider_id", "local.sample.slice"}}, {}));
  Json run{{"job_id", "web-candidate"}, {"attempt_id", "web-candidate-attempt"},
    {"project_id", kProjectId}, {"asset_id", kAssetId}, {"expected_revision", 1},
    {"parameters", {{"refractory_frames", 1}}}, {"data_classification", "public"},
    {"platform", "test"}, {"region", "local"}, {"required_permissions", Json::array({"sample.slice.execute"})}};
  check_error(runtime->dispatch("candidate.job.run", run, {}), "HOST_STATE_INVALID");
  check_success(runtime->dispatch("candidate.audition.stop", Json::object(), {}));
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  auto wav = mono_pcm16_wav(4096);
  for (std::size_t offset = 44; offset < wav.size(); offset += 2) write_u16(wav, offset, 12000);
  check_success(runtime->dispatch("asset.import", import_payload(820, 0, kAssetId, wav), wav));
  const auto before = inspect_project(temp.path(), kProjectId);
  auto injected = run; injected["project_path"] = "/forbidden/project.lmdj";
  check_error(runtime->dispatch("candidate.job.run", injected, {}), "HOST_PROTOCOL_MISMATCH");
  check_error(runtime->dispatch("candidate.job.run", run, wav), "HOST_PROTOCOL_MISMATCH");
  auto wrong = run; wrong["project_id"] = uuid(821);
  check_error(runtime->dispatch("candidate.job.run", wrong, {}), "REVISION_CONFLICT");
  auto competing = make_provider_runtime(temp.path());
  check_error(competing->dispatch("project.open",
    {{"project_id", kProjectId}, {"pattern_id", kPatternId}}, {}), "PROJECT_BUSY");
  check_error(competing->dispatch("candidate.job.run", run, {}), "HOST_STATE_INVALID");
  check_success(competing->dispatch("host.close", Json::object(), {}));
  const auto result = check_locked_success_result(runtime->dispatch("candidate.job.run", run, {}));
  LMDJ_CHECK(result.at("project_revision").is_null());
  LMDJ_CHECK(result.dump().find("project_path") == std::string::npos);
  LMDJ_CHECK(result.dump().find(temp.path().generic_string()) == std::string::npos);
  LMDJ_CHECK(result.at("sets").size() == 1);
  const auto& set = result.at("sets").at(0);
  LMDJ_CHECK(set.at("recipes").size() == 1);
  const auto set_id = set.at("set_id");
  const auto candidate_id = set.at("recipes").at(0).at("candidate_id");
  Json preview{{"project_id", kProjectId}, {"expected_revision", 1},
    {"job_id", "web-candidate"}, {"set_id", set_id}, {"candidate_id", candidate_id}};
  const auto cold = check_locked_success_result(runtime->dispatch("candidate.audition", preview, {}));
  LMDJ_CHECK(cold.at("played") == false && cold.at("source_frames") == 4096);
  LMDJ_CHECK(cold.at("project_revision") == 1);
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId) == before);
  check_success(runtime->dispatch("snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  // A prepared but stopped Host can publish an audition Bank without admitting
  // a voice. Replacing it below must not refund Project Bank reservations.
  const auto prepared_cold = check_locked_success_result(runtime->dispatch("candidate.audition", preview, {}));
  LMDJ_CHECK(prepared_cold.at("played") == false);
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId) == before);
  FakeCoordinator coordinator;
  LMDJ_CHECK(ControlRuntimeAudioAccess::install(*runtime, coordinator.seam()).has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  struct ObservedPcm { RealtimeEngine* engine; float peak = 0; } observed{&runtime->engine()};
  OneShotAudioDriver driver(OneShotAudioBackend{&observed,
    [](void* context) noexcept {return static_cast<ObservedPcm*>(context)->engine->bank_telemetry();},
    [](void* context, float* left, float* right, std::uint32_t frames) noexcept {
      auto& state = *static_cast<ObservedPcm*>(context);
      state.engine->render(left, right, frames);
      state.peak = 0;
      for (std::uint32_t frame = 0; frame < frames; ++frame)
        state.peak = std::max(state.peak, std::abs(left[frame]));
    }});
  const auto audible = check_locked_success_result(runtime->dispatch("candidate.audition", preview, {}));
  LMDJ_CHECK(audible.at("played") == true);
  driver.render_one();
  LMDJ_CHECK(observed.peak > 0.0F);
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 1);
  check_error(runtime->dispatch("candidate.audition.stop", {{"set_id", set_id}}, {}), "HOST_PROTOCOL_MISMATCH");
  check_success(runtime->dispatch("candidate.audition.stop", Json::object(), {}));
  // Drain the fixed engine release ramp, then assert the far-side block is silent.
  for (std::uint32_t frames = 0; frames < lmdj::audio::kRealtimeRampFrames; frames += 128) driver.render_one();
  driver.render_one();
  LMDJ_CHECK(observed.peak == 0.0F);
  LMDJ_CHECK(runtime->engine().telemetry().active_voices == 0);
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId) == before);
  auto stale = preview; stale["expected_revision"] = 0;
  check_error(runtime->dispatch("candidate.audition", stale, {}), "REVISION_CONFLICT");
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId) == before);
  Json adopt{{"project_id", kProjectId}, {"expected_revision", 1}, {"command_id", uuid(822)},
    {"job_id", "web-candidate"}, {"set_id", set_id},
    {"selections", Json::array({{{"candidate_id", candidate_id}, {"bank", 0}, {"pad", 1}},
      {{"candidate_id", candidate_id}, {"bank", 0}, {"pad", 2}}})}};
  auto duplicate = adopt; duplicate["selections"][1]["pad"] = 1;
  check_error(runtime->dispatch("candidate.adopt", duplicate, {}), "HOST_PROTOCOL_MISMATCH");
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId) == before);
  const auto adopted = check_locked_success_result(runtime->dispatch("candidate.adopt", adopt, {}));
  LMDJ_CHECK(adopted.at("project_revision") == 2 && adopted.at("adopted").size() == 2);
  LMDJ_CHECK(adopted.at("adopted")[0].at("asset_id") != adopted.at("adopted")[1].at("asset_id"));
  const auto after = inspect_project(temp.path(), kProjectId);
  check_error(runtime->dispatch("candidate.adopt", adopt, {}), "REVISION_CONFLICT");
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId) == after);
  const auto discarded = check_locked_success_result(runtime->dispatch("candidate.set.discard",
    {{"job_id", "web-candidate"}, {"set_id", set_id}}, {}));
  LMDJ_CHECK(discarded.at("active_set_id").is_null());
  preview["expected_revision"] = 2;
  check_error(runtime->dispatch("candidate.audition", preview, {}), "NOT_FOUND");
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId) == after);
  check_error(runtime->dispatch("candidate.job.cancel",
    {{"job_id", "web-candidate"}, {"attempt_id", "web-candidate-attempt"}}, {}), "INVALID_ARGUMENT");
  check_success(runtime->dispatch("host.close", Json::object(), {}));
  check_error(runtime->dispatch("candidate.audition.stop", Json::object(), {}), "HOST_STATE_INVALID");
  check_error(runtime->dispatch("candidate.job.inspect", {{"job_id", "web-candidate"}}, {}), "HOST_STATE_INVALID");
  auto reopened = make_provider_runtime(temp.path());
  const auto restored = check_locked_success_result(reopened->dispatch("candidate.job.inspect", {{"job_id", "web-candidate"}}, {}));
  LMDJ_CHECK(restored == discarded);
  LMDJ_CHECK(restored.dump().find("project_path") == std::string::npos);
  check_success(reopened->dispatch("project.open", {{"project_id", kProjectId}, {"pattern_id", kPatternId}}, {}));
  LMDJ_CHECK(inspect_project(temp.path(), kProjectId) == after);
  check_success(reopened->dispatch("host.close", Json::object(), {}));
}

void test_provider_owner_uses_retained_project_and_survives_restart() {
  TempDirectory temp;
  auto runtime = make_provider_runtime(temp.path());
  const auto listed = check_locked_success_result(runtime->dispatch("provider.list", Json::object(), {}));
  LMDJ_CHECK(listed.at("providers").size() == 3);
  check_success(runtime->dispatch("provider.permissions.configure",
      {{"granted_permissions", Json::array({"sample.slice.execute"})}}, {}));
  check_success(runtime->dispatch("provider.select",
      {{"capability", "sample.slice.v1"}, {"provider_id", "local.sample.slice"}}, {}));
  Json input{{"attempt_id", "web-owner"}, {"capability", "sample.slice.v1"},
      {"inputs", Json::array({{{"port", "source_audio"}, {"artifact", {
          {"sha256", std::string(64, 'a')}, {"media_type", "audio/wav"}, {"byte_length", 54}}}}})},
      {"input_owners", Json::array({{{"port", "source_audio"}, {"occurrence", 0},
          {"project_id", kProjectId}, {"asset_id", kAssetId}}})},
      {"parameters", {{"refractory_frames", 1}}}, {"data_classification", "public"},
      {"platform", "test"}, {"region", "local"}, {"required_permissions", Json::array({"sample.slice.execute"})}};
  check_error(runtime->dispatch("provider.run", input, {}), "HOST_STATE_INVALID");
  check_error(runtime->dispatch("attempt.inspect", {{"attempt_id", "web-owner"}}, {}), "NOT_FOUND");
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  auto wav = mono_pcm16_wav(5); write_u16(wav, 46, 5000); write_u16(wav, 50, 8000);
  const auto imported = check_locked_success_result(runtime->dispatch(
      "asset.import", import_payload(810, 0, kAssetId, wav), wav));
  input["inputs"][0]["artifact"] = imported.at("artifact");
  const auto before = runtime->dispatch("project.inspect", Json::object(), {});
  auto competing = make_provider_runtime(temp.path());
  check_error(competing->dispatch("project.open",
      {{"project_id", kProjectId}, {"pattern_id", kPatternId}}, {}), "PROJECT_BUSY");
  check_error(competing->dispatch("provider.run", input, {}), "HOST_STATE_INVALID");
  check_error(competing->dispatch("attempt.inspect", {{"attempt_id", "web-owner"}}, {}), "NOT_FOUND");
  check_success(competing->dispatch("host.close", Json::object(), {}));
  competing.reset();
  auto injected_path = input;
  injected_path["input_owners"][0]["project_path"] = "/forbidden/project.lmdj";
  check_error(runtime->dispatch("provider.run", injected_path, {}), "HOST_PROTOCOL_MISMATCH");
  check_error(runtime->dispatch("provider.run", input, wav), "HOST_PROTOCOL_MISMATCH");
  const auto run = check_locked_success_result(runtime->dispatch("provider.run", input, {}));
  LMDJ_CHECK(run.at("outputs").size() == 1);
  const auto terminal = runtime->dispatch("attempt.inspect", {{"attempt_id", "web-owner"}}, {});
  const auto inspected = check_locked_success_result(terminal);
  LMDJ_CHECK(inspected.at("request").at("inputs") == input.at("inputs"));
  LMDJ_CHECK(inspected.at("candidate_outputs") == run.at("outputs"));
  LMDJ_CHECK(inspected.at("status") == "succeeded");
  LMDJ_CHECK(terminal.dump().find("project_path") == std::string::npos);
  LMDJ_CHECK(runtime->dispatch("project.inspect", Json::object(), {}) == before);
  check_success(runtime->dispatch("host.close", Json::object(), {})); runtime.reset();
  runtime = make_provider_runtime(temp.path());
  LMDJ_CHECK(runtime->dispatch("attempt.inspect", {{"attempt_id", "web-owner"}}, {}) == terminal);
  check_success(runtime->dispatch("project.open", {{"project_id", kProjectId}, {"pattern_id", kPatternId}}, {}));
  input["attempt_id"] = "web-no-regrant";
  check_error(runtime->dispatch("provider.run", input, {}), "PERMISSION_DENIED");
  LMDJ_CHECK(runtime->dispatch("project.inspect", Json::object(), {}) == before);
  check_success(runtime->dispatch("host.close", Json::object(), {}));
}

void test_web_provider_owner_refusals_are_persistent(unsigned mode) {
  TempDirectory temp;
  auto runtime = make_provider_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  auto wav = mono_pcm16_wav(5);
  const auto imported = check_locked_success_result(runtime->dispatch(
      "asset.import", import_payload(811, 0, kAssetId, wav), wav));
  const auto before = runtime->dispatch("project.inspect", Json::object(), {});
  check_success(runtime->dispatch("provider.permissions.configure",
      {{"granted_permissions", Json::array({"sample.slice.execute"})}}, {}));
  check_success(runtime->dispatch("provider.select",
      {{"capability", "sample.slice.v1"}, {"provider_id", "local.sample.slice"}}, {}));
  Json input{{"attempt_id", "web-refusal"}, {"capability", "sample.slice.v1"},
      {"inputs", Json::array({{{"port", "source_audio"}, {"artifact", imported.at("artifact")}}})},
      {"input_owners", Json::array({{{"port", "source_audio"}, {"occurrence", 0},
          {"project_id", kProjectId}, {"asset_id", kAssetId}}})},
      {"parameters", Json::object()}, {"data_classification", "public"},
      {"platform", "test"}, {"region", "local"}, {"required_permissions", Json::array({"sample.slice.execute"})}};
  auto code = "NOT_FOUND"; auto reason = "input_artifact_unavailable";
  if (mode == 0) input.erase("input_owners");
  if (mode == 1) input["input_owners"][0]["project_id"] = uuid(999);
  if (mode == 2) input["input_owners"][0]["asset_id"] = uuid(999);
  if (mode == 3) input["inputs"][0]["artifact"]["sha256"] = std::string(64, 'b');
  const auto blob = temp.path() / "projects" / (std::string(kProjectId) + ".lmdj") /
      "assets" / (imported.at("artifact").at("sha256").get<std::string>() + ".wav");
  if (mode == 4 || mode == 5) {
    auto corrupt = wav;
    if (mode == 4) corrupt.back() = std::byte{1}; else corrupt.push_back(std::byte{1});
    std::ofstream file(blob, std::ios::binary);
    file.write(reinterpret_cast<const char*>(corrupt.data()), static_cast<std::streamsize>(corrupt.size()));
    LMDJ_CHECK(file.good());
    code = "IO_ERROR"; reason = "input_artifact_mismatch";
  }
  if (mode == 6) std::filesystem::remove(blob);
  const auto refused = check_error(runtime->dispatch("provider.run", input, {}), code);
  LMDJ_CHECK(refused.at("details").at("reason") == reason);
  LMDJ_CHECK(refused.at("details").at("attempt_id") == "web-refusal");
  const auto terminal = runtime->dispatch("attempt.inspect", {{"attempt_id", "web-refusal"}}, {});
  LMDJ_CHECK(terminal.at("result").at("status") == "failed");
  LMDJ_CHECK(terminal.at("result").at("minted_outputs").empty());
  LMDJ_CHECK(terminal.at("result").at("candidate_outputs").empty());
  check_success(runtime->dispatch("host.close", Json::object(), {})); runtime.reset();
  runtime = make_provider_runtime(temp.path());
  LMDJ_CHECK(runtime->dispatch("attempt.inspect", {{"attempt_id", "web-refusal"}}, {}) == terminal);
  // Inspect works before any Project is reopened, including with corrupt input.
  if (mode < 4) {
    check_success(runtime->dispatch("project.open", {{"project_id", kProjectId}, {"pattern_id", kPatternId}}, {}));
    LMDJ_CHECK(runtime->dispatch("project.inspect", Json::object(), {}) == before);
  }
  check_success(runtime->dispatch("host.close", Json::object(), {}));
}

Json pattern_transport_request_payload(
    std::string_view session_id,
    std::uint32_t command_suffix,
    std::uint64_t epoch,
    std::string_view intent) {
  return {
      {"session_id", session_id},
      {"project_id", kProjectId},
      {"command_id", uuid(command_suffix)},
      {"expected_epoch", epoch},
      {"intent", intent},
      {"expected_revision", nullptr},
  };
}

Json pattern_transport_inspect(
    ControlRuntime& runtime,
    std::string_view session_id) {
  return check_exact_success(
      runtime.dispatch(
          "pattern.transport.inspect", {{"session_id", session_id}}, {}),
      {"engaged", "playing", "recording", "phase", "runtime_generation",
       "transport_epoch", "origin_frame", "command_id", "publication_pending",
       "error"});
}

// Each inspection turn drives one bounded continuation step; a render between
// turns lets the Engine publish the transport receipt. Returns the settled
// status or fails the test.
Json settle_pattern_transport(
    ControlRuntime& runtime,
    OneShotAudioDriver& audio,
    std::string_view session_id) {
  for (unsigned step = 0; step < 8; ++step) {
    audio.render_one();
    auto status = pattern_transport_inspect(runtime, session_id);
    if (status.at("phase") == "idle" &&
        status.at("publication_pending") == false) {
      return status;
    }
  }
  throw std::runtime_error("Pattern transport operation did not settle");
}

Json create_opted_in_project() {
  auto payload = create_payload();
  payload["pattern_transport"] = true;
  return payload;
}

void test_pattern_transport_requires_opt_in_and_preserves_legacy() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(runtime->dispatch("project.create", create_payload(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 770, 771, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));

  // Without the Project-open negotiation marker the transport operations are
  // refused and legacy Sequence recording keeps its journal meaning.
  check_error(
      runtime->dispatch(
          "pattern.transport.request",
          pattern_transport_request_payload(kSequenceSessionId, 772, 1,
                                            "record"),
          {}),
      "HOST_STATE_INVALID");
  check_success(runtime->dispatch(
      "sequence.record.begin",
      {{"session_id", kSequenceSessionId},
       {"pattern_id", kPatternId},
       {"expected_revision", 2}},
      {}));
}

void test_pattern_transport_records_live_input_and_rejects_legacy_writes() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(
      runtime->dispatch("project.create", create_opted_in_project(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 773, 774, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  OneShotAudioDriver audio(runtime->engine());

  const auto disengaged =
      pattern_transport_inspect(*runtime, kSequenceSessionId);
  LMDJ_CHECK(disengaged.at("engaged") == false);
  LMDJ_CHECK(disengaged.at("playing") == false);

  const auto& ticket = check_exact_success(
      runtime->dispatch(
          "pattern.transport.request",
          pattern_transport_request_payload(kSequenceSessionId, 775, 1,
                                            "record"),
          {}),
      {"session_id", "command_id", "submit", "status"});
  LMDJ_CHECK(ticket.at("session_id") == kSequenceSessionId);
  LMDJ_CHECK(ticket.at("command_id") == uuid(775));
  LMDJ_CHECK(ticket.at("submit") == "accepted");
  // The pending ticket is returned through the ordinary serializer while the
  // audio receipt is still outstanding; the tail does not await it.
  LMDJ_CHECK(ticket.at("status").at("phase") == "awaiting_audio");
  LMDJ_CHECK(ticket.at("status").at("engaged") == true);

  // A new mutation while the operation is unresolved is busy; an exact replay
  // returns the retained operation.
  check_error(
      runtime->dispatch(
          "pattern.transport.request",
          pattern_transport_request_payload(kSequenceSessionId, 776, 2,
                                            "play_stop"),
          {}),
      "HOST_STATE_INVALID");
  LMDJ_CHECK(
      check_exact_success(
          runtime->dispatch(
              "pattern.transport.request",
              pattern_transport_request_payload(kSequenceSessionId, 775, 1,
                                                "record"),
              {}),
          {"session_id", "command_id", "submit", "status"})
          .at("submit") == "replayed");

  // Live input stays serviceable while the admission completion is held: the
  // pre-fence press/release are live-only and journaled nowhere.
  check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 96}}, {}),
      {"sequence", "status"});
  check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}),
      {"accepted"});

  const auto recording =
      settle_pattern_transport(*runtime, audio, kSequenceSessionId);
  LMDJ_CHECK(recording.at("playing") == true);
  LMDJ_CHECK(recording.at("recording") == true);
  LMDJ_CHECK(recording.at("command_id") == uuid(775));

  // A global-enabled session rejects conflicting direct legacy writes; the
  // coordinator is the single journal owner.
  check_error(
      runtime->dispatch(
          "sequence.record.begin",
          {{"session_id", kSequenceSessionId},
           {"pattern_id", kPatternId},
           {"expected_revision", 2}},
          {}),
      "HOST_STATE_INVALID");
  check_error(
      runtime->dispatch(
          "sequence.settings.update",
          {{"command_id", uuid(777)},
           {"expected_revision", 2},
           {"session_id", kSequenceSessionId},
           {"bpm", 100},
           {"quantize_enabled", nullptr},
           {"swing_percent", nullptr}},
          {}),
      "HOST_STATE_INVALID");

  // Post-enqueue press/release are admitted with their original outcomes; the
  // journaling response is not reported before durability, so the durable
  // candidates must already exist when the trigger responses return.
  const auto& press = check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}),
      {"sequence", "status"});
  LMDJ_CHECK(press.at("status") == "enqueued");
  audio.render_one();
  check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}),
      {"accepted"});
  const auto bundle =
      temp.path() / "projects" / (std::string(kProjectId) + ".lmdj");
  const auto journal = lmdj::project_io::SequenceJournal{}.read_active(bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().admission.has_value());
  const auto& candidates = journal.value().admission->candidates;
  LMDJ_CHECK(candidates.size() == 2);
  LMDJ_CHECK(
      candidates.at(0).kind == lmdj::project_io::SequenceCandidateKind::press);
  // Watermarks start at the admission window floor the Facade coordinator
  // opens (10); this assertion pins that contract.
  LMDJ_CHECK(candidates.at(0).watermark == 10);
  LMDJ_CHECK(candidates.at(0).press_sequence == 10);
  LMDJ_CHECK(candidates.at(0).velocity == 100);
  LMDJ_CHECK(
      candidates.at(1).kind == lmdj::project_io::SequenceCandidateKind::release);
  LMDJ_CHECK(candidates.at(1).watermark == 11);
  // The release repeats its owning press's identity as correlation.
  LMDJ_CHECK(candidates.at(1).press_sequence == 10);

  // Record-off: storage settlement and the committed-Pattern publication are
  // held as separate completions.
  check_exact_success(
      runtime->dispatch(
          "pattern.transport.request",
          pattern_transport_request_payload(kSequenceSessionId, 778, 2,
                                            "record"),
          {}),
      {"session_id", "command_id", "submit", "status"});
  audio.render_one();
  const auto settled = pattern_transport_inspect(*runtime, kSequenceSessionId);
  LMDJ_CHECK(settled.at("phase") == "idle");
  LMDJ_CHECK(settled.at("recording") == false);
  LMDJ_CHECK(settled.at("playing") == true);
  LMDJ_CHECK(settled.at("publication_pending") == true);
  const auto published = pattern_transport_inspect(*runtime, kSequenceSessionId);
  LMDJ_CHECK(published.at("publication_pending") == false);

  // A retained completed command replays; the same identity with a changed
  // payload is invalid rather than a second toggle.
  LMDJ_CHECK(
      check_exact_success(
          runtime->dispatch(
              "pattern.transport.request",
              pattern_transport_request_payload(kSequenceSessionId, 778, 2,
                                                "record"),
              {}),
          {"session_id", "command_id", "submit", "status"})
          .at("submit") == "replayed");
  check_error(
      runtime->dispatch(
          "pattern.transport.request",
          pattern_transport_request_payload(kSequenceSessionId, 778, 2,
                                            "play_stop"),
          {}),
      "INVALID_ARGUMENT");

  const auto truth = inspect_project(temp.path(), kProjectId);
  const auto& events = truth.at("result")
                           .at("project")
                           .at("patterns")
                           .at(kPatternId)
                           .at("events");
  LMDJ_CHECK(events.size() == 1);
  LMDJ_CHECK(events.at(0).at("slot") == slot(0, 0));
  LMDJ_CHECK(events.at(0).at("velocity") == 100);
  LMDJ_CHECK(
      truth.at("project_revision").get<std::uint64_t>() > 2);

  // A live Pad survives Record-off and Pattern Stop: scheduling state never
  // gates the live trigger path.
  auto voices = runtime->engine().telemetry().started_voices;
  check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}),
      {"sequence", "status"});
  audio.render_one();
  LMDJ_CHECK(runtime->engine().telemetry().started_voices > voices);
  check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}),
      {"accepted"});

  check_exact_success(
      runtime->dispatch(
          "pattern.transport.request",
          pattern_transport_request_payload(kSequenceSessionId, 779, 3,
                                            "play_stop"),
          {}),
      {"session_id", "command_id", "submit", "status"});
  const auto stopped =
      settle_pattern_transport(*runtime, audio, kSequenceSessionId);
  LMDJ_CHECK(stopped.at("playing") == false);
  LMDJ_CHECK(stopped.at("recording") == false);

  voices = runtime->engine().telemetry().started_voices;
  check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}),
      {"sequence", "status"});
  audio.render_one();
  LMDJ_CHECK(runtime->engine().telemetry().started_voices > voices);
  check_exact_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}),
      {"accepted"});
}

void test_pattern_transport_suspend_barrier_settles_recording() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(
      runtime->dispatch("project.create", create_opted_in_project(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 780, 781, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  ContinuousAudioDriver driver(runtime->engine());
  coordinator.engine = &runtime->engine();
  coordinator.driver = &driver;

  check_success(runtime->dispatch(
      "pattern.transport.request",
      pattern_transport_request_payload(kSequenceSessionId, 782, 1, "record"),
      {}));
  wait_until([&] {
    const auto status = pattern_transport_inspect(*runtime, kSequenceSessionId);
    return status.at("recording") == true && status.at("phase") == "idle";
  });
  check_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  check_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}));

  // Explicit Suspend enters the shutdown barrier: acknowledged Pattern Stop,
  // admission closure and journal settlement complete before audio stops.
  // That settlement is real render-thread work whose duration sanitizer
  // instrumentation stretches past the 1s request budget even though every
  // settlement leg completes; pin the runtime clock so expiry cannot
  // interrupt the barrier this test verifies.
  FakeRuntimeClock clock;
  clock.current = std::chrono::steady_clock::now();
  LMDJ_CHECK(
      ControlRuntimeClockAccess::install(*runtime, clock.seam()).has_value());
  const auto& suspended = check_exact_success(
      runtime->dispatch("audio.suspend", Json::object(), {}),
      {"state", "changed", "stopped_sequence_id"});
  LMDJ_CHECK(suspended.at("state") == "audio-suspended");
  LMDJ_CHECK(suspended.at("changed") == true);

  const auto bundle =
      temp.path() / "projects" / (std::string(kProjectId) + ".lmdj");
  // Full settlement (drain → terminal → flush → complete → remove) leaves no
  // active journal and no recovery candidate; the recorded events are
  // committed Project Truth.
  const auto journal = lmdj::project_io::SequenceJournal{}.read_active(bundle);
  LMDJ_CHECK(!journal.has_value());
  const auto truth = inspect_project(temp.path(), kProjectId);
  LMDJ_CHECK(
      truth.at("result")
          .at("project")
          .at("patterns")
          .at(kPatternId)
          .at("events")
          .size() == 1);
  const auto& recovery = check_exact_success(
      runtime->dispatch(
          "sequence.recovery.list", {{"project_id", kProjectId}}, {}),
      {"candidates", "project_revision"});
  LMDJ_CHECK(recovery.at("candidates").empty());

  const auto settled = pattern_transport_inspect(*runtime, kSequenceSessionId);
  LMDJ_CHECK(settled.at("playing") == false);
  LMDJ_CHECK(settled.at("recording") == false);
  LMDJ_CHECK(settled.at("phase") == "idle");
  LMDJ_CHECK(settled.at("error").is_null());

  // Disposal re-enters the same barrier (already settled) and closes cleanly;
  // a fresh runtime then reopens the Project with the committed events.
  check_success(runtime->dispatch("host.close", Json::object(), {}));
  LMDJ_CHECK(runtime->pattern_transport_pending() == false);
  driver.stop();
  runtime.reset();
  auto reopened = make_runtime(temp.path());
  check_success(reopened->dispatch(
      "project.open",
      {{"project_id", kProjectId}, {"pattern_id", kPatternId}},
      {}));
  const auto reopened_truth = check_exact_success(
      reopened->dispatch("project.inspect", Json::object(), {}),
      {"project", "project_revision"});
  LMDJ_CHECK(
      reopened_truth.at("project")
          .at("patterns")
          .at(kPatternId)
          .at("events")
          .size() == 1);
}

void test_pattern_transport_unknown_closure_blocks_clean_suspend() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(
      runtime->dispatch("project.create", create_opted_in_project(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 783, 784, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  OneShotAudioDriver audio(runtime->engine());

  // Record live input durably first, then stop rendering so the barrier's
  // Pattern Stop receipt never arrives: the closure is unknown and Suspend
  // must fail instead of claiming a clean barrier.
  check_success(runtime->dispatch(
      "pattern.transport.request",
      pattern_transport_request_payload(kSequenceSessionId, 785, 1, "record"),
      {}));
  const auto recording =
      settle_pattern_transport(*runtime, audio, kSequenceSessionId);
  LMDJ_CHECK(recording.at("recording") == true);
  check_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  check_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}));

  const auto suspended = runtime->dispatch("audio.suspend", Json::object(), {});
  LMDJ_CHECK(suspended.value("ok", true) == false);
  LMDJ_CHECK(runtime->failed());

  // The unknown closure stays unresolved rather than being finalized from a
  // guessed state: the active journal persists with its admission open and
  // the durably retained candidates intact.
  const auto bundle =
      temp.path() / "projects" / (std::string(kProjectId) + ".lmdj");
  const auto journal = lmdj::project_io::SequenceJournal{}.read_active(bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().admission.has_value());
  LMDJ_CHECK(!journal.value().admission->closure.has_value());
  LMDJ_CHECK(!journal.value().admission->cutoff_fence.has_value());
  LMDJ_CHECK(journal.value().admission->candidates.size() == 2);
}

void test_transport_recording_rejects_sample_commit_and_keeps_journal() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  check_success(
      runtime->dispatch("project.create", create_opted_in_project(), {}));
  const auto wav = mono_pcm16_wav(2'400);
  import_and_assign(*runtime, wav, kAssetId, 790, 791, 0);
  check_success(runtime->dispatch(
      "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
          .has_value());
  check_success(runtime->dispatch("audio.activate", Json::object(), {}));
  OneShotAudioDriver audio(runtime->engine());
  check_success(runtime->dispatch(
      "pattern.transport.request",
      pattern_transport_request_payload(kSequenceSessionId, 792, 1, "record"),
      {}));
  const auto recording =
      settle_pattern_transport(*runtime, audio, kSequenceSessionId);
  LMDJ_CHECK(recording.at("recording") == true);
  check_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  audio.render_one();
  check_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}));

  // The capture-style Sample commit keeps its legacy busy guard: honestly
  // rejected while the transport journal is open, and the journal — owned by
  // the Facade-vended controller — must not be sealed as owner loss.
  const auto capture_wav = mono_pcm16_wav(480);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(
          793, 794, 2, "00000000-0000-4000-8000-000000000099",
          capture_wav.size(), 1),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(793, 0, true, capture_wav),
      capture_wav));
  check_error(
      runtime->dispatch(
          "sample.import.commit", {{"import_token", uuid(793)}}, {}),
      "INVALID_ARGUMENT");

  const auto bundle =
      temp.path() / "projects" / (std::string(kProjectId) + ".lmdj");
  const auto journal = lmdj::project_io::SequenceJournal{}.read_active(bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().admission.has_value());
  LMDJ_CHECK(journal.value().admission->candidates.size() == 2);
  check_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}));
  audio.render_one();
  check_success(
      runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}));

  // Once the recording settles (journal completed and removed), the same
  // Sample commit is admitted again.
  {
    const auto pending_journal =
        lmdj::project_io::SequenceJournal{}.read_active(bundle);
    LMDJ_CHECK(pending_journal.has_value());
    LMDJ_CHECK(pending_journal.value().admission->candidates.size() == 4);
  }
  check_success(runtime->dispatch(
      "pattern.transport.request",
      pattern_transport_request_payload(kSequenceSessionId, 795, 2, "record"),
      {}));
  const auto settled =
      settle_pattern_transport(*runtime, audio, kSequenceSessionId);
  LMDJ_CHECK(settled.at("recording") == false);
  LMDJ_CHECK(
      !lmdj::project_io::SequenceJournal{}.read_active(bundle).has_value());
  const auto after_settle = check_exact_success(
      runtime->dispatch("project.inspect", Json::object(), {}),
      {"project", "project_revision"});
  // The record-off committed both retained gestures as Project Truth.
  LMDJ_CHECK(
      after_settle.at("project_revision").get<std::uint64_t>() > 2);
  LMDJ_CHECK(
      after_settle.at("project")
          .at("patterns")
          .at(kPatternId)
          .at("events")
          .size() == 2);
  check_success(runtime->dispatch(
      "sample.import.begin",
      sample_begin_payload(
          796, 797,
          after_settle.at("project_revision").get<std::uint64_t>(),
          "00000000-0000-4000-8000-000000000098",
          capture_wav.size(), 1),
      {}));
  check_success(runtime->dispatch(
      "sample.import.chunk",
      sample_chunk_payload(796, 0, true, capture_wav),
      capture_wav));
  check_success(runtime->dispatch(
      "sample.import.commit", {{"import_token", uuid(796)}}, {}));
}

void test_pattern_transport_owner_loss_lists_recovery_on_reopen() {
  TempDirectory temp;
  {
    auto runtime = make_runtime(temp.path());
    check_success(
        runtime->dispatch("project.create", create_opted_in_project(), {}));
    const auto wav = mono_pcm16_wav(2'400);
    import_and_assign(*runtime, wav, kAssetId, 800, 801, 0);
    check_success(runtime->dispatch(
        "snapshot.reload", {{"pattern_id", kPatternId}}, {}));
    FakeCoordinator coordinator;
    LMDJ_CHECK(
        ControlRuntimeAudioAccess::install(*runtime, coordinator.seam())
            .has_value());
    check_success(runtime->dispatch("audio.activate", Json::object(), {}));
    OneShotAudioDriver audio(runtime->engine());
    check_success(runtime->dispatch(
        "pattern.transport.request",
        pattern_transport_request_payload(kSequenceSessionId, 802, 1, "record"),
        {}));
    const auto recording =
        settle_pattern_transport(*runtime, audio, kSequenceSessionId);
    LMDJ_CHECK(recording.at("recording") == true);
    check_success(
        runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}));
    audio.render_one();
    check_success(
        runtime->dispatch("trigger", {{"slot", 0}, {"kind", "release"}}, {}));

    // Listing while the owner is live never seals its journal.
    const auto& live = check_exact_success(
        runtime->dispatch(
            "sequence.recovery.list", {{"project_id", kProjectId}}, {}),
        {"candidates", "project_revision"});
    LMDJ_CHECK(live.at("candidates").empty());
    check_success(
        runtime->dispatch("trigger", {{"slot", 0}, {"velocity", 100}}, {}));

    // Owner loss without a Close: destruction settles nothing transport-owned.
  }

  // The destroyed runtime leaves the active journal on disk with its admission
  // open and every durable candidate intact; nothing is removed or settled.
  const auto bundle =
      temp.path() / "projects" / (std::string(kProjectId) + ".lmdj");
  const auto orphaned =
      lmdj::project_io::SequenceJournal{}.read_active(bundle);
  LMDJ_CHECK(orphaned.has_value());
  LMDJ_CHECK(orphaned.value().admission.has_value());
  LMDJ_CHECK(!orphaned.value().admission->closure.has_value());
  LMDJ_CHECK(orphaned.value().admission->candidates.size() == 3);

  auto reopened = make_runtime(temp.path());
  check_success(reopened->dispatch(
      "project.open",
      {{"project_id", kProjectId},
       {"pattern_id", kPatternId},
       {"pattern_transport", true}},
      {}));
  const auto& recovery = check_exact_success(
      reopened->dispatch(
          "sequence.recovery.list", {{"project_id", kProjectId}}, {}),
      {"candidates", "project_revision"});
  LMDJ_CHECK(recovery.at("candidates").size() == 1);
  LMDJ_CHECK(
      recovery.at("candidates").at(0).at("session_id") == kSequenceSessionId);
  LMDJ_CHECK(
      recovery.at("candidates").at(0).at("reason") == "owner_lost");

  // The unresolved admission is a recoverable refusal, never a guess; discard
  // releases it and a fresh transport recording can open a new journal.
  const auto applied = reopened->dispatch(
      "sequence.recovery.apply",
      {{"session_id", kSequenceSessionId}, {"destination_pattern_id", nullptr}},
      {});
  LMDJ_CHECK(!applied.value("ok", true));
  check_success(reopened->dispatch(
      "sequence.recovery.discard", {{"session_id", kSequenceSessionId}}, {}));
  const auto& cleared = check_exact_success(
      reopened->dispatch(
          "sequence.recovery.list", {{"project_id", kProjectId}}, {}),
      {"candidates", "project_revision"});
  LMDJ_CHECK(cleared.at("candidates").empty());

  FakeCoordinator coordinator;
  LMDJ_CHECK(
      ControlRuntimeAudioAccess::install(*reopened, coordinator.seam())
          .has_value());
  check_success(reopened->dispatch("audio.activate", Json::object(), {}));
  OneShotAudioDriver audio(reopened->engine());
  check_success(reopened->dispatch(
      "pattern.transport.request",
      pattern_transport_request_payload(kSequenceSessionId, 803, 1, "record"),
      {}));
  const auto recording =
      settle_pattern_transport(*reopened, audio, kSequenceSessionId);
  LMDJ_CHECK(recording.at("recording") == true);
}

}  // namespace

int main() {
  try {
    test_candidate_host_owns_paths_pcm_stop_and_atomic_adoption();
    test_provider_owner_uses_retained_project_and_survives_restart();
    for (unsigned mode = 0; mode < 7; ++mode) test_web_provider_owner_refusals_are_persistent(mode);
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
    test_audio_activation_prepares_master_fx_for_perform();
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
    test_soundset_operations_route_at_the_workspace_and_the_project();
    test_host_supplied_catalog_verifies_what_it_serves();
    test_host_supplied_catalog_resolves_only_addressed_objects();
    test_host_catalog_operations_need_a_wired_transport();
    test_soundset_audition_reports_whether_a_voice_started();
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
    test_bridge_defers_a_request_whose_thunk_runs_during_a_dispatch();
    test_bridge_defers_the_seal_when_a_failure_lands_during_a_dispatch();
    test_bridge_parks_foreign_control_tasks_during_a_dispatch();
    test_bridge_parks_requests_during_the_realtime_service();
    test_bridge_parks_the_realtime_service_during_a_dispatch();
    test_bridge_benign_query_cancel_does_not_fail_the_runtime();
    test_bridge_rechecks_deadline_before_success_publication();
    test_bridge_uses_the_caller_deadline_as_the_authoritative_upper_bound();
    test_bridge_preserves_a_pre_deadline_publication_claim_to_settlement();
    test_bridge_passes_the_absolute_caller_deadline_into_audio_activation();
    test_bridge_rechecks_deadline_before_error_publication();
    test_internal_audio_activation_timeout_is_terminal_after_response();
    test_bridge_preserves_error_responses_for_an_externally_failed_runtime();
    test_pattern_transport_requires_opt_in_and_preserves_legacy();
    test_pattern_transport_records_live_input_and_rejects_legacy_writes();
    test_pattern_transport_suspend_barrier_settles_recording();
    test_pattern_transport_unknown_closure_blocks_clean_suspend();
    test_transport_recording_rejects_sample_commit_and_keeps_journal();
    test_pattern_transport_owner_loss_lists_recovery_on_reopen();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "web control runtime tests: PASS\n";
  return 0;
}
