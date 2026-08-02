#pragma once

#include "coreaudio_services.hpp"

namespace lmdj::audio::apple::detail {

class CoreAudioCallbackContext final {
 public:
  CoreAudioCallbackContext(RealtimeEngine& engine, MonotonicClock& clock);
  void reset_telemetry() noexcept;
  void enable() noexcept;
  bool enter() noexcept;
  void leave() noexcept;
  void disable_and_drain() noexcept;
  void quarantine() noexcept;
  RealtimeEngine& engine() noexcept;
  MonotonicClock& clock() noexcept;
  void record_device_overload() noexcept;
  void record_callback_failure() noexcept;
  void record_deadline_overrun() noexcept;
  CoreAudioTelemetry telemetry() const noexcept;

 private:
  RealtimeEngine* engine_;
  MonotonicClock* clock_;
  std::atomic<bool> enabled_{false};
  std::atomic<std::uint64_t> in_flight_{0};
  std::atomic<std::uint64_t> device_overloads_{0};
  std::atomic<std::uint64_t> callback_failures_{0};
  std::atomic<std::uint64_t> deadline_overruns_{0};
  CoreAudioCallbackContext* quarantine_next_ = nullptr;
};

class CoreAudioOutputStateMachine final {
 public:
  CoreAudioOutputStateMachine(
      RealtimeEngine& engine,
      std::unique_ptr<CoreAudioServices> services,
      std::unique_ptr<MonotonicClock> clock);
  ~CoreAudioOutputStateMachine();
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
  std::unique_ptr<CoreAudioCallbackContext> callback_context_;
  CoreAudioState state_{CoreAudioState::stopped};
  bool created_ = false;
  bool listener_added_ = false;
  bool initialized_ = false;
  bool unit_started_ = false;
};

}  // namespace lmdj::audio::apple::detail
