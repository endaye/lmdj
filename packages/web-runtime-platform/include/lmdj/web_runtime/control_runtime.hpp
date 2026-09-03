#pragma once

#include <cstddef>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::web_runtime {

namespace detail {
class ControlRuntimeAudioAccess;
class ControlRuntimeClockAccess;
class ControlRuntimeSnapshotAccess;
}

struct SequenceBarBoundaryEvent {
  std::string session_id;
  std::string pattern_id;
  std::uint64_t runtime_frame;
  std::uint64_t generation;
};

class ControlRuntime final {
 public:
  struct AbsoluteRequestDeadline final {
    std::chrono::steady_clock::time_point value;
    void* publication_context = nullptr;
    bool (*publication_settlement_owned)(void* context) noexcept = nullptr;
  };

  static foundation::Result<std::unique_ptr<ControlRuntime>> create(
      std::filesystem::path workspace_root,
      facade::ApplicationConfig application_config,
      audio::RuntimePreparationLimits limits);

  nlohmann::json dispatch(
      std::string_view operation,
      const nlohmann::json& payload,
      std::span<const std::byte> sidecar);
  nlohmann::json dispatch(
      std::string_view operation,
      const nlohmann::json& payload,
      std::span<const std::byte> sidecar,
      std::chrono::steady_clock::time_point submitted_at);
  nlohmann::json dispatch(
      std::string_view operation,
      const nlohmann::json& payload,
      std::span<const std::byte> sidecar,
      AbsoluteRequestDeadline deadline);
  std::vector<audio::RuntimeTriggerOutcomeEvent> drain_outcomes();
  std::vector<audio::RuntimeVoiceStateEvent> drain_voice_states();
  foundation::Result<void> drain_capture();
  foundation::Result<void> service_performance();
  std::optional<SequenceBarBoundaryEvent> drain_sequence_bar_boundary();
  bool validate_realtime_health() noexcept;
  void fail_and_seal(std::string_view cause) noexcept;
  bool failed() const noexcept;
  audio::RealtimeEngine& engine() noexcept;

 private:
  struct Impl;
  explicit ControlRuntime(std::shared_ptr<Impl> impl) noexcept;

  std::shared_ptr<Impl> impl_;
  friend class detail::ControlRuntimeAudioAccess;
  friend class detail::ControlRuntimeClockAccess;
  friend class detail::ControlRuntimeSnapshotAccess;
};

namespace detail {

struct AudioQuiescenceCoordinator {
  void* context;
  foundation::Result<void> (*await_quiescent)(
      void* context, std::uint32_t timeout_ms) noexcept;
  foundation::Result<void> (*begin_rendering)(void* context) noexcept;
  bool (*ready)(void* context) noexcept;
  std::uint64_t (*acknowledged_generation)(void* context) noexcept;
};

struct ControlRuntimeClock {
  void* context;
  std::chrono::steady_clock::time_point (*now)(void* context) noexcept;
};

struct ControlRuntimeSnapshotTruth {
  std::optional<std::uint64_t> project_revision;
  std::optional<std::uint64_t> runtime_revision;
};

class ControlRuntimeAudioAccess final {
 public:
  static foundation::Result<void> install(
      ControlRuntime& runtime,
      AudioQuiescenceCoordinator coordinator) noexcept;
};

class ControlRuntimeClockAccess final {
 public:
  static foundation::Result<void> install(
      ControlRuntime& runtime,
      ControlRuntimeClock clock) noexcept;
};

class ControlRuntimeSnapshotAccess final {
 public:
  static ControlRuntimeSnapshotTruth read(
      const ControlRuntime& runtime) noexcept;
};

inline constexpr std::size_t kBridgeMaximumEnvelopeBytes = 65'536;
inline constexpr std::size_t kBridgeMaximumSidecarBytes = 1'048'576;
inline constexpr std::size_t kBridgeMessageSlotCount = 8;

enum class BridgeSubmitStatus : std::uint8_t {
  accepted,
  envelope_too_large,
  sidecar_too_large,
  queue_full,
  proxy_failed,
};

enum class BridgePollStatus : std::uint8_t {
  empty,
  message,
  output_too_small,
  failed,
};

enum class BridgeCancelStatus : std::int8_t {
  not_found = -1,
  publish_claimed = 0,
  cancelled = 1,
};

struct BridgeHooks {
  void* context;
  bool (*schedule)(
      void* context,
      void (*function)(void*) noexcept,
      void* argument) noexcept;
  bool (*on_control)(void* context) noexcept;
#if !defined(__EMSCRIPTEN__)
  void (*before_response_serialization)(void* context);
  void (*after_capture_drain)(void* context);
  void (*after_outcome_drain)(void* context);
#endif
};

class ControlBridge final {
 public:
  ControlBridge(ControlRuntime& runtime, BridgeHooks hooks);

  BridgeSubmitStatus submit(
      std::span<const std::byte> envelope,
      std::span<const std::byte> sidecar,
      std::optional<std::chrono::steady_clock::time_point> caller_deadline =
          std::nullopt) noexcept;
  BridgePollStatus poll(
      std::span<std::byte> output,
      std::size_t& required) noexcept;
  BridgeCancelStatus cancel(std::string_view request_id) noexcept;
  BridgeCancelStatus cancel_query(std::string_view request_id) noexcept;
  bool configure_deadline_proof(
      std::string_view request_id,
      std::uint8_t gate,
      bool force_publication_error) noexcept;
  bool release_deadline_proof() noexcept;
  int deadline_proof_state(std::string_view request_id) const noexcept;
  // Park a control-thread task while a request dispatch is in progress (it
  // may be suspended in Asyncify); the bridge re-proxies it once that dispatch
  // has returned. Returns false when the caller should run the task itself.
  bool defer_while_dispatching(
      void (*function)(void*) noexcept, void* argument) noexcept;
  bool terminal_release_ready() const noexcept;
  bool failed() const noexcept;

 private:
  struct Impl;
  std::shared_ptr<Impl> impl_;
};

}  // namespace detail
}  // namespace lmdj::web_runtime
