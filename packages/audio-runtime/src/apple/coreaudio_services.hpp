#pragma once

#include <AudioUnit/AudioUnit.h>
#include <CoreAudio/CoreAudio.h>

#include <atomic>
#include <cstdint>
#include <memory>

#include <lmdj/audio/apple/coreaudio_output.hpp>

namespace lmdj::audio::apple::detail {

class CoreAudioServices {
 public:
  virtual ~CoreAudioServices() = default;
  virtual foundation::Result<void> create(
      AURenderCallback render, void* context) = 0;
  virtual foundation::Result<void> configure(
      std::uint32_t sample_rate, std::uint16_t channels) = 0;
  virtual foundation::Result<void> add_overload_listener(
      AudioObjectPropertyListenerProc listener, void* context) = 0;
  virtual foundation::Result<void> initialize() = 0;
  virtual foundation::Result<void> start() = 0;
  virtual foundation::Result<void> stop() = 0;
  virtual foundation::Result<void> remove_overload_listener() = 0;
  virtual foundation::Result<void> uninitialize() = 0;
  virtual foundation::Result<void> dispose() = 0;
};

class MonotonicClock {
 public:
  virtual ~MonotonicClock() = default;
  virtual std::uint64_t now() noexcept = 0;
  virtual double seconds_between(
      std::uint64_t begin, std::uint64_t end) noexcept = 0;
};

class CoreAudioApi {
 public:
  virtual ~CoreAudioApi() = default;
  virtual AudioComponent find_next(
      const AudioComponentDescription* description) = 0;
  virtual OSStatus instance_new(
      AudioComponent component, AudioUnit* unit) = 0;
  virtual OSStatus instance_dispose(AudioUnit unit) = 0;
  virtual OSStatus unit_set_property(
      AudioUnit unit,
      AudioUnitPropertyID property,
      AudioUnitScope scope,
      AudioUnitElement element,
      const void* data,
      UInt32 data_size) = 0;
  virtual OSStatus object_get_property_data(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      UInt32 qualifier_size,
      const void* qualifier,
      UInt32* data_size,
      void* data) = 0;
  virtual OSStatus object_add_property_listener(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      AudioObjectPropertyListenerProc listener,
      void* context) = 0;
  virtual OSStatus object_remove_property_listener(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      AudioObjectPropertyListenerProc listener,
      void* context) = 0;
  virtual OSStatus unit_initialize(AudioUnit unit) = 0;
  virtual OSStatus output_unit_start(AudioUnit unit) = 0;
  virtual OSStatus output_unit_stop(AudioUnit unit) = 0;
  virtual OSStatus unit_uninitialize(AudioUnit unit) = 0;
};

std::unique_ptr<CoreAudioServices> make_coreaudio_services(
    std::unique_ptr<CoreAudioApi> api);
std::unique_ptr<CoreAudioServices> make_default_coreaudio_services();
std::unique_ptr<MonotonicClock> make_mach_monotonic_clock();

}  // namespace lmdj::audio::apple::detail
