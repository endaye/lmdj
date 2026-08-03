#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::web_host {

namespace detail {
class ControlRuntimeAudioAccess;
}

class ControlRuntime final {
 public:
  static foundation::Result<std::unique_ptr<ControlRuntime>> create(
      std::filesystem::path workspace_root,
      facade::Application application,
      audio::RuntimePreparationLimits limits);

  nlohmann::json dispatch(
      std::string_view operation,
      const nlohmann::json& payload,
      std::span<const std::byte> sidecar);
  std::vector<audio::RuntimeTriggerOutcomeEvent> drain_outcomes();
  foundation::Result<void> drain_capture();
  void fail_and_seal(std::string_view cause) noexcept;
  audio::RealtimeEngine& engine() noexcept;

 private:
  struct Impl;
  explicit ControlRuntime(std::shared_ptr<Impl> impl) noexcept;

  std::shared_ptr<Impl> impl_;
  friend class detail::ControlRuntimeAudioAccess;
};

namespace detail {

struct AudioQuiescenceCoordinator {
  void* context;
  foundation::Result<void> (*await_quiescent)(
      void* context, std::uint32_t timeout_ms) noexcept;
};

class ControlRuntimeAudioAccess final {
 public:
  static foundation::Result<void> install(
      ControlRuntime& runtime,
      AudioQuiescenceCoordinator coordinator) noexcept;
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

struct BridgeHooks {
  void* context;
  bool (*schedule)(
      void* context,
      void (*function)(void*) noexcept,
      void* argument) noexcept;
  bool (*on_control)(void* context) noexcept;
#if !defined(__EMSCRIPTEN__)
  void (*before_response_serialization)(void* context);
#endif
};

class ControlBridge final {
 public:
  ControlBridge(ControlRuntime& runtime, BridgeHooks hooks);

  BridgeSubmitStatus submit(
      std::span<const std::byte> envelope,
      std::span<const std::byte> sidecar) noexcept;
  BridgePollStatus poll(
      std::span<std::byte> output,
      std::size_t& required) noexcept;
  bool failed() const noexcept;

 private:
  struct Impl;
  std::shared_ptr<Impl> impl_;
};

}  // namespace detail
}  // namespace lmdj::web_host
