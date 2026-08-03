#include "coreaudio_services.hpp"

#include <mach/mach_time.h>

#include <cstdint>
#include <memory>
#include <string>
#include <utility>

namespace lmdj::audio::apple::detail {
namespace {

foundation::Result<void> coreaudio_failure(
    std::string operation, OSStatus status) {
  return foundation::Result<void>::failure(foundation::Error{
      foundation::ErrorCode::io_error,
      "CoreAudio operation failed",
      {{"operation", std::move(operation)},
       {"os_status", static_cast<std::int64_t>(status)}},
  });
}

class SystemCoreAudioApi final : public CoreAudioApi {
 public:
  AudioComponent find_next(
      const AudioComponentDescription* description) override {
    return AudioComponentFindNext(nullptr, description);
  }

  OSStatus instance_new(
      AudioComponent component, AudioUnit* unit) override {
    return AudioComponentInstanceNew(component, unit);
  }

  OSStatus instance_dispose(AudioUnit unit) override {
    return AudioComponentInstanceDispose(unit);
  }

  OSStatus unit_set_property(
      AudioUnit unit,
      AudioUnitPropertyID property,
      AudioUnitScope scope,
      AudioUnitElement element,
      const void* data,
      UInt32 data_size) override {
    return AudioUnitSetProperty(
        unit, property, scope, element, data, data_size);
  }

  OSStatus object_get_property_data(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      UInt32 qualifier_size,
      const void* qualifier,
      UInt32* data_size,
      void* data) override {
    return AudioObjectGetPropertyData(
        object,
        address,
        qualifier_size,
        qualifier,
        data_size,
        data);
  }

  OSStatus object_add_property_listener(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      AudioObjectPropertyListenerProc listener,
      void* context) override {
    return AudioObjectAddPropertyListener(
        object, address, listener, context);
  }

  OSStatus object_remove_property_listener(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      AudioObjectPropertyListenerProc listener,
      void* context) override {
    return AudioObjectRemovePropertyListener(
        object, address, listener, context);
  }

  OSStatus unit_initialize(AudioUnit unit) override {
    return AudioUnitInitialize(unit);
  }

  OSStatus output_unit_start(AudioUnit unit) override {
    return AudioOutputUnitStart(unit);
  }

  OSStatus output_unit_stop(AudioUnit unit) override {
    return AudioOutputUnitStop(unit);
  }

  OSStatus unit_uninitialize(AudioUnit unit) override {
    return AudioUnitUninitialize(unit);
  }
};

class DefaultCoreAudioServices final : public CoreAudioServices {
 public:
  explicit DefaultCoreAudioServices(std::unique_ptr<CoreAudioApi> api)
      : api_(std::move(api)) {}

  ~DefaultCoreAudioServices() override {
    if (overload_listener_ != nullptr) {
      const AudioObjectPropertyAddress address{
          kAudioDeviceProcessorOverload,
          kAudioObjectPropertyScopeGlobal,
          kAudioObjectPropertyElementMain,
      };
      (void)api_->object_remove_property_listener(
          output_device_, &address, overload_listener_, overload_context_);
    }
    if (unit_ != nullptr) {
      (void)api_->output_unit_stop(unit_);
      (void)api_->unit_uninitialize(unit_);
      (void)api_->instance_dispose(unit_);
    }
  }

  foundation::Result<void> create(
      AURenderCallback render, void* context) override {
    const AudioComponentDescription description{
        kAudioUnitType_Output,
        kAudioUnitSubType_DefaultOutput,
        kAudioUnitManufacturer_Apple,
        0,
        0,
    };
    const auto component = api_->find_next(&description);
    if (component == nullptr) {
      return coreaudio_failure(
          "AudioComponentFindNext", kAudio_ParamError);
    }

    AudioUnit candidate = nullptr;
    auto status = api_->instance_new(component, &candidate);
    if (status != noErr) {
      return coreaudio_failure("AudioComponentInstanceNew", status);
    }
    unit_ = candidate;

    const AURenderCallbackStruct callback{render, context};
    status = api_->unit_set_property(
        unit_,
        kAudioUnitProperty_SetRenderCallback,
        kAudioUnitScope_Input,
        0,
        &callback,
        sizeof(callback));
    if (status != noErr) {
      if (api_->instance_dispose(unit_) == noErr) {
        unit_ = nullptr;
      }
      return coreaudio_failure(
          "AudioUnitSetProperty.render_callback", status);
    }

    return foundation::Result<void>::success();
  }

  foundation::Result<void> configure(
      std::uint32_t sample_rate, std::uint16_t channels) override {
    AudioStreamBasicDescription format{};
    format.mSampleRate = static_cast<Float64>(sample_rate);
    format.mFormatID = kAudioFormatLinearPCM;
    format.mFormatFlags =
        static_cast<AudioFormatFlags>(kAudioFormatFlagIsFloat) |
        static_cast<AudioFormatFlags>(kAudioFormatFlagsNativeEndian) |
        static_cast<AudioFormatFlags>(kAudioFormatFlagIsPacked) |
        static_cast<AudioFormatFlags>(kAudioFormatFlagIsNonInterleaved);
    format.mBytesPerPacket = sizeof(float);
    format.mFramesPerPacket = 1;
    format.mBytesPerFrame = sizeof(float);
    format.mChannelsPerFrame = channels;
    format.mBitsPerChannel = 32;

    const auto status = api_->unit_set_property(
        unit_,
        kAudioUnitProperty_StreamFormat,
        kAudioUnitScope_Input,
        0,
        &format,
        sizeof(format));
    if (status != noErr) {
      return coreaudio_failure("AudioUnitSetProperty.stream_format", status);
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> add_overload_listener(
      AudioObjectPropertyListenerProc listener, void* context) override {
    const AudioObjectPropertyAddress default_output_address{
        kAudioHardwarePropertyDefaultOutputDevice,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    };
    AudioDeviceID device = kAudioObjectUnknown;
    UInt32 size = sizeof(device);
    auto status = api_->object_get_property_data(
        kAudioObjectSystemObject,
        &default_output_address,
        0,
        nullptr,
        &size,
        &device);
    if (status != noErr) {
      return coreaudio_failure(
          "AudioObjectGetPropertyData.default_output_device", status);
    }

    const AudioObjectPropertyAddress overload_address{
        kAudioDeviceProcessorOverload,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    };
    status = api_->object_add_property_listener(
        device, &overload_address, listener, context);
    if (status != noErr) {
      return coreaudio_failure(
          "AudioObjectAddPropertyListener.processor_overload", status);
    }

    output_device_ = device;
    overload_listener_ = listener;
    overload_context_ = context;
    return foundation::Result<void>::success();
  }

  foundation::Result<void> initialize() override {
    const auto status = api_->unit_initialize(unit_);
    if (status != noErr) {
      return coreaudio_failure("AudioUnitInitialize", status);
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> start() override {
    const auto status = api_->output_unit_start(unit_);
    if (status != noErr) {
      return coreaudio_failure("AudioOutputUnitStart", status);
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> stop() override {
    const auto status = api_->output_unit_stop(unit_);
    if (status != noErr) {
      return coreaudio_failure("AudioOutputUnitStop", status);
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> remove_overload_listener() override {
    const AudioObjectPropertyAddress address{
        kAudioDeviceProcessorOverload,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    };
    const auto status = api_->object_remove_property_listener(
        output_device_, &address, overload_listener_, overload_context_);
    if (status != noErr) {
      return coreaudio_failure(
          "AudioObjectRemovePropertyListener.processor_overload", status);
    }

    output_device_ = kAudioObjectUnknown;
    overload_listener_ = nullptr;
    overload_context_ = nullptr;
    return foundation::Result<void>::success();
  }

  foundation::Result<void> uninitialize() override {
    const auto status = api_->unit_uninitialize(unit_);
    if (status != noErr) {
      return coreaudio_failure("AudioUnitUninitialize", status);
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> dispose() override {
    if (unit_ == nullptr) {
      return foundation::Result<void>::success();
    }
    const auto status = api_->instance_dispose(unit_);
    if (status != noErr) {
      return coreaudio_failure("AudioComponentInstanceDispose", status);
    }
    unit_ = nullptr;
    return foundation::Result<void>::success();
  }

 private:
  std::unique_ptr<CoreAudioApi> api_;
  AudioUnit unit_ = nullptr;
  AudioDeviceID output_device_ = kAudioObjectUnknown;
  AudioObjectPropertyListenerProc overload_listener_ = nullptr;
  void* overload_context_ = nullptr;
};

class MachMonotonicClock final : public MonotonicClock {
 public:
  MachMonotonicClock() {
    if (mach_timebase_info(&timebase_) != KERN_SUCCESS ||
        timebase_.denom == 0) {
      timebase_.numer = 1;
      timebase_.denom = 1;
    }
  }

  std::uint64_t now() noexcept override { return mach_absolute_time(); }

  double seconds_between(
      std::uint64_t begin, std::uint64_t end) noexcept override {
    const auto ticks = end >= begin ? end - begin : 0;
    const auto nanoseconds =
        static_cast<double>(ticks) * static_cast<double>(timebase_.numer) /
        static_cast<double>(timebase_.denom);
    return nanoseconds / 1'000'000'000.0;
  }

 private:
  mach_timebase_info_data_t timebase_{};
};

}  // namespace

std::unique_ptr<CoreAudioServices> make_coreaudio_services(
    std::unique_ptr<CoreAudioApi> api) {
  return std::make_unique<DefaultCoreAudioServices>(std::move(api));
}

std::unique_ptr<CoreAudioServices> make_default_coreaudio_services() {
  return make_coreaudio_services(std::make_unique<SystemCoreAudioApi>());
}

std::unique_ptr<MonotonicClock> make_mach_monotonic_clock() {
  return std::make_unique<MachMonotonicClock>();
}

}  // namespace lmdj::audio::apple::detail
