#pragma once

#include "coreaudio_services.hpp"

namespace lmdj::audio::apple::detail {

class CoreAudioOutputStateMachine final {
 public:
  CoreAudioOutputStateMachine(
      RealtimeEngine& engine,
      std::unique_ptr<CoreAudioServices> services,
      std::unique_ptr<MonotonicClock> clock);
  foundation::Result<void> start();
  foundation::Result<void> stop();
  CoreAudioState state() const noexcept;
  CoreAudioTelemetry telemetry() const noexcept;

 private:
  static OSStatus render_callback(
      void* context,
      AudioUnitRenderActionFlags* flags,
      const AudioTimeStamp* timestamp,
      UInt32 bus,
      UInt32 frames,
      AudioBufferList* buffers) noexcept;
  static OSStatus overload_callback(
      AudioObjectID object,
      UInt32 address_count,
      const AudioObjectPropertyAddress* addresses,
      void* context) noexcept;

  RealtimeEngine& engine_;
  std::unique_ptr<CoreAudioServices> services_;
  std::unique_ptr<MonotonicClock> clock_;
  CoreAudioState state_{CoreAudioState::stopped};
  bool created_ = false;
  bool listener_added_ = false;
  bool initialized_ = false;
  bool unit_started_ = false;
  std::atomic<std::uint64_t> device_overloads_{0};
  std::atomic<std::uint64_t> callback_failures_{0};
  std::atomic<std::uint64_t> deadline_overruns_{0};
};

}  // namespace lmdj::audio::apple::detail
