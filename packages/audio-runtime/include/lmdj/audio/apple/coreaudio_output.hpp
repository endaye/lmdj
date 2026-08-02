#pragma once

#include <cstdint>
#include <memory>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::audio::apple {

enum class CoreAudioState : std::uint8_t {
  stopped,
  running,
  failed,
};

struct CoreAudioTelemetry {
  std::uint64_t device_overloads;
  std::uint64_t callback_failures;
  std::uint64_t deadline_overruns;
};

class CoreAudioOutput final {
 public:
  explicit CoreAudioOutput(RealtimeEngine& engine);
  ~CoreAudioOutput();
  CoreAudioOutput(const CoreAudioOutput&) = delete;
  CoreAudioOutput& operator=(const CoreAudioOutput&) = delete;
  foundation::Result<void> start();
  foundation::Result<void> stop();
  CoreAudioState state() const noexcept;
  CoreAudioTelemetry telemetry() const noexcept;

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::audio::apple
