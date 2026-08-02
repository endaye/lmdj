#include "packages/audio-runtime/src/apple/coreaudio_output_state.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <map>
#include <set>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::EnqueueResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RealtimeState;
using lmdj::audio::TriggerEvent;
using lmdj::audio::apple::CoreAudioState;
using lmdj::audio::apple::CoreAudioOutput;
using lmdj::audio::apple::detail::CoreAudioApi;
using lmdj::audio::apple::detail::CoreAudioOutputStateMachine;
using lmdj::audio::apple::detail::CoreAudioServices;
using lmdj::audio::apple::detail::MonotonicClock;
using lmdj::audio::apple::detail::make_coreaudio_services;
using lmdj::audio::apple::detail::make_mach_monotonic_clock;
using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::Result;

Result<void> fake_failure(const std::string& operation) {
  return Result<void>::failure(Error{
      ErrorCode::io_error,
      "injected CoreAudio failure",
      {{"operation", operation}, {"source", "test"}},
  });
}

class FakeCoreAudioServices final : public CoreAudioServices {
 public:
  Result<void> create(AURenderCallback render, void* context) override {
    calls.emplace_back("create");
    if (should_fail("create")) {
      return fake_failure("create");
    }
    render_ = render;
    render_context_ = context;
    return Result<void>::success();
  }

  Result<void> configure(
      std::uint32_t sample_rate, std::uint16_t channels) override {
    calls.emplace_back("configure");
    configured_sample_rate = sample_rate;
    configured_channels = channels;
    if (should_fail("configure")) {
      return fake_failure("configure");
    }
    return Result<void>::success();
  }

  Result<void> add_overload_listener(
      AudioObjectPropertyListenerProc listener, void* context) override {
    calls.emplace_back("add_overload_listener");
    if (should_fail("add_overload_listener")) {
      return fake_failure("add_overload_listener");
    }
    overload_listener_ = listener;
    overload_context_ = context;
    return Result<void>::success();
  }

  Result<void> initialize() override {
    return record("initialize");
  }

  Result<void> start() override { return record("start"); }

  Result<void> stop() override { return record("stop"); }

  Result<void> remove_overload_listener() override {
    const auto result = record("remove_overload_listener");
    if (result.has_value()) {
      overload_listener_ = nullptr;
      overload_context_ = nullptr;
    }
    return result;
  }

  Result<void> uninitialize() override { return record("uninitialize"); }

  Result<void> dispose() override {
    const auto result = record("dispose");
    if (result.has_value()) {
      render_ = nullptr;
      render_context_ = nullptr;
    }
    return result;
  }

  void fail_once(std::string operation) {
    failures.insert(std::move(operation));
  }

  OSStatus render(UInt32 frames, AudioBufferList* buffers) {
    LMDJ_CHECK(render_ != nullptr);
    AudioUnitRenderActionFlags flags = 0;
    AudioTimeStamp timestamp{};
    return render_(
        render_context_, &flags, &timestamp, 0, frames, buffers);
  }

  void notify_overload() {
    LMDJ_CHECK(overload_listener_ != nullptr);
    const AudioObjectPropertyAddress address{
        kAudioDeviceProcessorOverload,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    };
    LMDJ_CHECK(
        overload_listener_(0, 1, &address, overload_context_) == noErr);
  }

  std::vector<std::string> calls;
  std::uint32_t configured_sample_rate = 0;
  std::uint16_t configured_channels = 0;

 private:
  bool should_fail(const std::string& operation) {
    return failures.erase(operation) != 0;
  }

  Result<void> record(const std::string& operation) {
    calls.push_back(operation);
    if (should_fail(operation)) {
      return fake_failure(operation);
    }
    return Result<void>::success();
  }

  std::set<std::string> failures;
  AURenderCallback render_ = nullptr;
  void* render_context_ = nullptr;
  AudioObjectPropertyListenerProc overload_listener_ = nullptr;
  void* overload_context_ = nullptr;
};

class FakeClock final : public MonotonicClock {
 public:
  std::uint64_t now() noexcept override { return ++ticks; }

  double seconds_between(
      std::uint64_t begin, std::uint64_t end) noexcept override {
    observed_begin = begin;
    observed_end = end;
    return elapsed_seconds;
  }

  std::uint64_t ticks = 0;
  std::uint64_t observed_begin = 0;
  std::uint64_t observed_end = 0;
  double elapsed_seconds = 0.0;
};

OSStatus raw_test_render(
    void*,
    AudioUnitRenderActionFlags*,
    const AudioTimeStamp*,
    UInt32,
    UInt32,
    AudioBufferList*) {
  return noErr;
}

OSStatus raw_test_overload(
    AudioObjectID,
    UInt32,
    const AudioObjectPropertyAddress*,
    void*) {
  return noErr;
}

struct RawCoreAudioTrace {
  std::vector<std::string> calls;
  std::map<std::string, OSStatus> failures;
  AudioComponentDescription component_description{};
  AudioUnit callback_unit = nullptr;
  AudioUnitScope callback_scope = 0;
  AudioUnitElement callback_element = 0;
  AURenderCallbackStruct render_callback{};
  AudioUnit format_unit = nullptr;
  AudioUnitScope format_scope = 0;
  AudioUnitElement format_element = 0;
  AudioStreamBasicDescription format{};
  AudioObjectID get_object = kAudioObjectUnknown;
  AudioObjectPropertyAddress get_address{};
  UInt32 get_qualifier_size = 0;
  const void* get_qualifier = nullptr;
  UInt32 get_data_size = 0;
  AudioObjectID add_object = kAudioObjectUnknown;
  AudioObjectPropertyAddress add_address{};
  AudioObjectPropertyListenerProc add_listener = nullptr;
  void* add_context = nullptr;
  AudioObjectID remove_object = kAudioObjectUnknown;
  AudioObjectPropertyAddress remove_address{};
  AudioObjectPropertyListenerProc remove_listener = nullptr;
  void* remove_context = nullptr;
  AudioUnit last_unit = nullptr;
  bool component_available = true;
  AudioDeviceID output_device = 41;
};

class FakeRawCoreAudioApi final : public CoreAudioApi {
 public:
  explicit FakeRawCoreAudioApi(std::shared_ptr<RawCoreAudioTrace> trace)
      : trace_(std::move(trace)) {}

  AudioComponent find_next(
      const AudioComponentDescription* description) override {
    trace_->calls.emplace_back("find_next");
    trace_->component_description = *description;
    return trace_->component_available ? component() : nullptr;
  }

  OSStatus instance_new(AudioComponent candidate, AudioUnit* unit) override {
    trace_->calls.emplace_back("instance_new");
    LMDJ_CHECK(candidate == component());
    const auto status = failure("instance_new");
    if (status == noErr) {
      *unit = audio_unit();
    }
    return status;
  }

  OSStatus instance_dispose(AudioUnit unit) override {
    trace_->calls.emplace_back("instance_dispose");
    LMDJ_CHECK(unit == audio_unit());
    trace_->last_unit = unit;
    return failure("instance_dispose");
  }

  OSStatus unit_set_property(
      AudioUnit unit,
      AudioUnitPropertyID property,
      AudioUnitScope scope,
      AudioUnitElement element,
      const void* data,
      UInt32 data_size) override {
    if (property == kAudioUnitProperty_SetRenderCallback) {
      trace_->calls.emplace_back("set_render_callback");
      LMDJ_CHECK(data_size == sizeof(AURenderCallbackStruct));
      trace_->callback_unit = unit;
      trace_->callback_scope = scope;
      trace_->callback_element = element;
      trace_->render_callback =
          *static_cast<const AURenderCallbackStruct*>(data);
      return failure("set_render_callback");
    }
    LMDJ_CHECK(property == kAudioUnitProperty_StreamFormat);
    trace_->calls.emplace_back("set_stream_format");
    LMDJ_CHECK(data_size == sizeof(AudioStreamBasicDescription));
    trace_->format_unit = unit;
    trace_->format_scope = scope;
    trace_->format_element = element;
    trace_->format = *static_cast<const AudioStreamBasicDescription*>(data);
    return failure("set_stream_format");
  }

  OSStatus object_get_property_data(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      UInt32 qualifier_size,
      const void* qualifier,
      UInt32* data_size,
      void* data) override {
    trace_->calls.emplace_back("get_default_output");
    trace_->get_object = object;
    trace_->get_address = *address;
    trace_->get_qualifier_size = qualifier_size;
    trace_->get_qualifier = qualifier;
    trace_->get_data_size = *data_size;
    const auto status = failure("get_default_output");
    if (status == noErr) {
      LMDJ_CHECK(*data_size == sizeof(AudioDeviceID));
      *static_cast<AudioDeviceID*>(data) = trace_->output_device;
    }
    return status;
  }

  OSStatus object_add_property_listener(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      AudioObjectPropertyListenerProc listener,
      void* context) override {
    trace_->calls.emplace_back("add_listener");
    trace_->add_object = object;
    trace_->add_address = *address;
    trace_->add_listener = listener;
    trace_->add_context = context;
    return failure("add_listener");
  }

  OSStatus object_remove_property_listener(
      AudioObjectID object,
      const AudioObjectPropertyAddress* address,
      AudioObjectPropertyListenerProc listener,
      void* context) override {
    trace_->calls.emplace_back("remove_listener");
    trace_->remove_object = object;
    trace_->remove_address = *address;
    trace_->remove_listener = listener;
    trace_->remove_context = context;
    return failure("remove_listener");
  }

  OSStatus unit_initialize(AudioUnit unit) override {
    return unit_operation("unit_initialize", unit);
  }

  OSStatus output_unit_start(AudioUnit unit) override {
    return unit_operation("output_start", unit);
  }

  OSStatus output_unit_stop(AudioUnit unit) override {
    return unit_operation("output_stop", unit);
  }

  OSStatus unit_uninitialize(AudioUnit unit) override {
    return unit_operation("unit_uninitialize", unit);
  }

  static AudioComponent component() {
    return reinterpret_cast<AudioComponent>(static_cast<std::uintptr_t>(0x10));
  }

  static AudioUnit audio_unit() {
    return reinterpret_cast<AudioUnit>(static_cast<std::uintptr_t>(0x20));
  }

 private:
  OSStatus failure(const std::string& operation) const {
    const auto found = trace_->failures.find(operation);
    return found == trace_->failures.end() ? noErr : found->second;
  }

  OSStatus unit_operation(const std::string& operation, AudioUnit unit) {
    trace_->calls.push_back(operation);
    LMDJ_CHECK(unit == audio_unit());
    trace_->last_unit = unit;
    return failure(operation);
  }

  std::shared_ptr<RawCoreAudioTrace> trace_;
};

struct RawServiceHarness {
  std::shared_ptr<RawCoreAudioTrace> trace =
      std::make_shared<RawCoreAudioTrace>();
  std::unique_ptr<CoreAudioServices> services = make_coreaudio_services(
      std::make_unique<FakeRawCoreAudioApi>(trace));
};

struct StereoBufferList {
  UInt32 count;
  AudioBuffer buffers[2];
};

struct Harness {
  RealtimeEngine engine;
  FakeCoreAudioServices* services = nullptr;
  FakeClock* clock = nullptr;
  std::unique_ptr<CoreAudioOutputStateMachine> output;

  Harness() {
    auto owned_services = std::make_unique<FakeCoreAudioServices>();
    auto owned_clock = std::make_unique<FakeClock>();
    services = owned_services.get();
    clock = owned_clock.get();
    output = std::make_unique<CoreAudioOutputStateMachine>(
        engine, std::move(owned_services), std::move(owned_clock));
  }
};

void check_calls(
    const FakeCoreAudioServices& services,
    std::span<const std::string> expected) {
  LMDJ_CHECK(services.calls.size() == expected.size());
  for (std::size_t index = 0; index < expected.size(); ++index) {
    LMDJ_CHECK(services.calls[index] == expected[index]);
  }
}

void check_address(
    const AudioObjectPropertyAddress& address,
    AudioObjectPropertySelector selector) {
  LMDJ_CHECK(address.mSelector == selector);
  LMDJ_CHECK(address.mScope == kAudioObjectPropertyScopeGlobal);
  LMDJ_CHECK(address.mElement == kAudioObjectPropertyElementMain);
}

void check_framework_error(
    const Result<void>& result,
    const std::string& operation,
    OSStatus status) {
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::io_error);
  LMDJ_CHECK(result.error().details.at("operation") == operation);
  LMDJ_CHECK(result.error().details.at("os_status") ==
             static_cast<std::int64_t>(status));
}

void concrete_services_forward_exact_coreaudio_arguments() {
  RawServiceHarness harness;
  auto* context = harness.trace.get();
  const AURenderCallback render = &raw_test_render;
  LMDJ_CHECK(
      harness.services->create(render, context).has_value());
  LMDJ_CHECK(harness.services->configure(48'000, 2).has_value());
  LMDJ_CHECK(
      harness.services->add_overload_listener(&raw_test_overload, context)
          .has_value());
  LMDJ_CHECK(harness.services->initialize().has_value());
  LMDJ_CHECK(harness.services->start().has_value());
  LMDJ_CHECK(harness.services->stop().has_value());
  LMDJ_CHECK(harness.services->remove_overload_listener().has_value());
  LMDJ_CHECK(harness.services->uninitialize().has_value());
  LMDJ_CHECK(harness.services->dispose().has_value());

  const std::array<std::string, 12> expected{
      "find_next",
      "instance_new",
      "set_render_callback",
      "set_stream_format",
      "get_default_output",
      "add_listener",
      "unit_initialize",
      "output_start",
      "output_stop",
      "remove_listener",
      "unit_uninitialize",
      "instance_dispose",
  };
  LMDJ_CHECK(harness.trace->calls.size() == expected.size());
  for (std::size_t index = 0; index < expected.size(); ++index) {
    LMDJ_CHECK(harness.trace->calls[index] == expected[index]);
  }

  const auto& description = harness.trace->component_description;
  LMDJ_CHECK(description.componentType == kAudioUnitType_Output);
  LMDJ_CHECK(description.componentSubType ==
             kAudioUnitSubType_DefaultOutput);
  LMDJ_CHECK(description.componentManufacturer ==
             kAudioUnitManufacturer_Apple);
  LMDJ_CHECK(description.componentFlags == 0);
  LMDJ_CHECK(description.componentFlagsMask == 0);
  LMDJ_CHECK(harness.trace->callback_unit ==
             FakeRawCoreAudioApi::audio_unit());
  LMDJ_CHECK(harness.trace->callback_scope == kAudioUnitScope_Input);
  LMDJ_CHECK(harness.trace->callback_element == 0);
  LMDJ_CHECK(harness.trace->render_callback.inputProc == render);
  LMDJ_CHECK(harness.trace->render_callback.inputProcRefCon == context);

  const auto& format = harness.trace->format;
  const auto exact_flags =
      static_cast<AudioFormatFlags>(kAudioFormatFlagIsFloat) |
      static_cast<AudioFormatFlags>(kAudioFormatFlagsNativeEndian) |
      static_cast<AudioFormatFlags>(kAudioFormatFlagIsPacked) |
      static_cast<AudioFormatFlags>(kAudioFormatFlagIsNonInterleaved);
  LMDJ_CHECK(harness.trace->format_unit ==
             FakeRawCoreAudioApi::audio_unit());
  LMDJ_CHECK(harness.trace->format_scope == kAudioUnitScope_Input);
  LMDJ_CHECK(harness.trace->format_element == 0);
  LMDJ_CHECK(format.mSampleRate == 48'000.0);
  LMDJ_CHECK(format.mFormatID == kAudioFormatLinearPCM);
  LMDJ_CHECK(format.mFormatFlags == exact_flags);
  LMDJ_CHECK(format.mBytesPerPacket == sizeof(float));
  LMDJ_CHECK(format.mFramesPerPacket == 1);
  LMDJ_CHECK(format.mBytesPerFrame == sizeof(float));
  LMDJ_CHECK(format.mChannelsPerFrame == 2);
  LMDJ_CHECK(format.mBitsPerChannel == 32);

  LMDJ_CHECK(harness.trace->get_object == kAudioObjectSystemObject);
  check_address(
      harness.trace->get_address,
      kAudioHardwarePropertyDefaultOutputDevice);
  LMDJ_CHECK(harness.trace->get_qualifier_size == 0);
  LMDJ_CHECK(harness.trace->get_qualifier == nullptr);
  LMDJ_CHECK(harness.trace->get_data_size == sizeof(AudioDeviceID));
  LMDJ_CHECK(harness.trace->add_object == harness.trace->output_device);
  check_address(
      harness.trace->add_address, kAudioDeviceProcessorOverload);
  LMDJ_CHECK(harness.trace->add_listener == &raw_test_overload);
  LMDJ_CHECK(harness.trace->add_context == context);
  LMDJ_CHECK(harness.trace->remove_object == harness.trace->output_device);
  check_address(
      harness.trace->remove_address, kAudioDeviceProcessorOverload);
  LMDJ_CHECK(harness.trace->remove_listener == &raw_test_overload);
  LMDJ_CHECK(harness.trace->remove_context == context);

  const auto calls_before_destruction = harness.trace->calls.size();
  harness.services.reset();
  LMDJ_CHECK(harness.trace->calls.size() == calls_before_destruction);
}

void concrete_services_map_signed_framework_errors() {
  constexpr OSStatus kStatus = -12'345;
  {
    RawServiceHarness harness;
    harness.trace->component_available = false;
    check_framework_error(
        harness.services->create(&raw_test_render, nullptr),
        "AudioComponentFindNext",
        kAudio_ParamError);
  }
  {
    RawServiceHarness harness;
    harness.trace->failures["instance_new"] = kStatus;
    check_framework_error(
        harness.services->create(&raw_test_render, nullptr),
        "AudioComponentInstanceNew",
        kStatus);
  }
  {
    RawServiceHarness harness;
    harness.trace->failures["set_render_callback"] = kStatus;
    check_framework_error(
        harness.services->create(&raw_test_render, nullptr),
        "AudioUnitSetProperty.render_callback",
        kStatus);
    LMDJ_CHECK(harness.trace->calls.back() == "instance_dispose");
  }
  {
    RawServiceHarness harness;
    LMDJ_CHECK(
        harness.services->create(&raw_test_render, nullptr).has_value());
    harness.trace->failures["set_stream_format"] = kStatus;
    check_framework_error(
        harness.services->configure(48'000, 2),
        "AudioUnitSetProperty.stream_format",
        kStatus);
  }
  {
    RawServiceHarness harness;
    harness.trace->failures["get_default_output"] = kStatus;
    check_framework_error(
        harness.services->add_overload_listener(
            &raw_test_overload, nullptr),
        "AudioObjectGetPropertyData.default_output_device",
        kStatus);
  }
  {
    RawServiceHarness harness;
    harness.trace->failures["add_listener"] = kStatus;
    check_framework_error(
        harness.services->add_overload_listener(
            &raw_test_overload, nullptr),
        "AudioObjectAddPropertyListener.processor_overload",
        kStatus);
  }

  struct UnitFailureCase {
    std::string raw_operation;
    std::string framework_operation;
    Result<void> (CoreAudioServices::*invoke)();
  };
  const std::array<UnitFailureCase, 5> unit_failures{
      UnitFailureCase{
          "unit_initialize",
          "AudioUnitInitialize",
          &CoreAudioServices::initialize},
      UnitFailureCase{
          "output_start", "AudioOutputUnitStart", &CoreAudioServices::start},
      UnitFailureCase{
          "output_stop", "AudioOutputUnitStop", &CoreAudioServices::stop},
      UnitFailureCase{
          "unit_uninitialize",
          "AudioUnitUninitialize",
          &CoreAudioServices::uninitialize},
      UnitFailureCase{
          "instance_dispose",
          "AudioComponentInstanceDispose",
          &CoreAudioServices::dispose},
  };
  for (const auto& failure : unit_failures) {
    RawServiceHarness harness;
    LMDJ_CHECK(
        harness.services->create(&raw_test_render, nullptr).has_value());
    harness.trace->failures[failure.raw_operation] = kStatus;
    check_framework_error(
        ((*harness.services).*(failure.invoke))(),
        failure.framework_operation,
        kStatus);
  }

  {
    RawServiceHarness harness;
    LMDJ_CHECK(
        harness.services->add_overload_listener(
            &raw_test_overload, nullptr)
            .has_value());
    harness.trace->failures["remove_listener"] = kStatus;
    check_framework_error(
        harness.services->remove_overload_listener(),
        "AudioObjectRemovePropertyListener.processor_overload",
        kStatus);
  }
}

void concrete_services_retain_owned_resources_for_destructor_cleanup() {
  constexpr OSStatus kFailure = -7'777;
  {
    RawServiceHarness harness;
    LMDJ_CHECK(
        harness.services->create(&raw_test_render, nullptr).has_value());
    LMDJ_CHECK(
        harness.services->add_overload_listener(
            &raw_test_overload, nullptr)
            .has_value());
    harness.services.reset();
    const std::array<std::string, 4> expected_tail{
        "remove_listener",
        "output_stop",
        "unit_uninitialize",
        "instance_dispose",
    };
    LMDJ_CHECK(harness.trace->calls.size() >= expected_tail.size());
    const auto begin = harness.trace->calls.size() - expected_tail.size();
    for (std::size_t index = 0; index < expected_tail.size(); ++index) {
      LMDJ_CHECK(harness.trace->calls[begin + index] == expected_tail[index]);
    }
  }
  {
    RawServiceHarness harness;
    LMDJ_CHECK(
        harness.services->create(&raw_test_render, nullptr).has_value());
    harness.trace->failures["instance_dispose"] = kFailure;
    check_framework_error(
        harness.services->dispose(),
        "AudioComponentInstanceDispose",
        kFailure);
    const auto dispose_calls_before = static_cast<std::size_t>(std::count(
        harness.trace->calls.begin(),
        harness.trace->calls.end(),
        "instance_dispose"));
    harness.services.reset();
    const auto dispose_calls_after = static_cast<std::size_t>(std::count(
        harness.trace->calls.begin(),
        harness.trace->calls.end(),
        "instance_dispose"));
    LMDJ_CHECK(dispose_calls_after == dispose_calls_before + 1);
  }
  {
    RawServiceHarness harness;
    harness.trace->failures["set_render_callback"] = kFailure;
    harness.trace->failures["instance_dispose"] = kFailure - 1;
    check_framework_error(
        harness.services->create(&raw_test_render, nullptr),
        "AudioUnitSetProperty.render_callback",
        kFailure);
    const auto dispose_calls_before = static_cast<std::size_t>(std::count(
        harness.trace->calls.begin(),
        harness.trace->calls.end(),
        "instance_dispose"));
    harness.services.reset();
    const auto dispose_calls_after = static_cast<std::size_t>(std::count(
        harness.trace->calls.begin(),
        harness.trace->calls.end(),
        "instance_dispose"));
    LMDJ_CHECK(dispose_calls_after == dispose_calls_before + 1);
  }
  {
    RawServiceHarness harness;
    LMDJ_CHECK(
        harness.services->add_overload_listener(
            &raw_test_overload, nullptr)
            .has_value());
    harness.trace->failures["remove_listener"] = kFailure;
    check_framework_error(
        harness.services->remove_overload_listener(),
        "AudioObjectRemovePropertyListener.processor_overload",
        kFailure);
    const auto remove_calls_before = static_cast<std::size_t>(std::count(
        harness.trace->calls.begin(),
        harness.trace->calls.end(),
        "remove_listener"));
    harness.services.reset();
    const auto remove_calls_after = static_cast<std::size_t>(std::count(
        harness.trace->calls.begin(),
        harness.trace->calls.end(),
        "remove_listener"));
    LMDJ_CHECK(remove_calls_after == remove_calls_before + 1);
  }
}

void default_factories_are_passive_until_start() {
  RealtimeEngine engine;
  CoreAudioOutput output(engine);
  LMDJ_CHECK(output.state() == CoreAudioState::stopped);
  LMDJ_CHECK(output.telemetry().device_overloads == 0);
  LMDJ_CHECK(output.stop().has_value());

  auto clock = make_mach_monotonic_clock();
  const auto begin = clock->now();
  const auto end = clock->now();
  LMDJ_CHECK(clock->seconds_between(begin, end) >= 0.0);
  LMDJ_CHECK(clock->seconds_between(2, 1) == 0.0);
}

void starts_and_stops_in_the_approved_order() {
  Harness harness;

  LMDJ_CHECK(harness.output->state() == CoreAudioState::stopped);
  LMDJ_CHECK(harness.output->start().has_value());
  LMDJ_CHECK(harness.output->state() == CoreAudioState::running);
  LMDJ_CHECK(harness.engine.telemetry().state == RealtimeState::running);
  LMDJ_CHECK(harness.services->configured_sample_rate == 48'000);
  LMDJ_CHECK(harness.services->configured_channels == 2);
  LMDJ_CHECK(harness.output->stop().has_value());
  LMDJ_CHECK(harness.output->state() == CoreAudioState::stopped);
  LMDJ_CHECK(harness.engine.telemetry().state == RealtimeState::stopped);

  const std::array<std::string, 9> expected{
      "create",
      "configure",
      "add_overload_listener",
      "initialize",
      "start",
      "stop",
      "remove_overload_listener",
      "uninitialize",
      "dispose",
  };
  check_calls(*harness.services, expected);
}

void start_failures_unwind_and_allow_restart() {
  struct FailureCase {
    std::string operation;
    std::vector<std::string> expected;
  };
  const std::array<FailureCase, 5> cases{
      FailureCase{"create", {"create"}},
      FailureCase{"configure", {"create", "configure", "dispose"}},
      FailureCase{
          "add_overload_listener",
          {"create", "configure", "add_overload_listener", "dispose"}},
      FailureCase{
          "initialize",
          {"create",
           "configure",
           "add_overload_listener",
           "initialize",
           "remove_overload_listener",
           "dispose"}},
      FailureCase{
          "start",
          {"create",
           "configure",
           "add_overload_listener",
           "initialize",
           "start",
           "uninitialize",
           "remove_overload_listener",
           "dispose"}},
  };

  for (const auto& failure : cases) {
    Harness harness;
    harness.services->fail_once(failure.operation);
    const auto failed = harness.output->start();
    LMDJ_CHECK(!failed.has_value());
    LMDJ_CHECK(failed.error().details.at("operation") == failure.operation);
    LMDJ_CHECK(harness.output->state() == CoreAudioState::stopped);
    LMDJ_CHECK(harness.engine.telemetry().state == RealtimeState::stopped);
    check_calls(*harness.services, failure.expected);

    LMDJ_CHECK(harness.output->start().has_value());
    LMDJ_CHECK(harness.output->state() == CoreAudioState::running);
    LMDJ_CHECK(harness.output->stop().has_value());
  }
}

void a_prestarted_engine_is_stopped_after_safe_unwind() {
  Harness harness;
  LMDJ_CHECK(harness.engine.start().has_value());

  const auto failed = harness.output->start();
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(harness.output->state() == CoreAudioState::stopped);
  LMDJ_CHECK(harness.engine.telemetry().state == RealtimeState::stopped);

  const std::array<std::string, 7> expected{
      "create",
      "configure",
      "add_overload_listener",
      "initialize",
      "uninitialize",
      "remove_overload_listener",
      "dispose",
  };
  check_calls(*harness.services, expected);
  LMDJ_CHECK(harness.output->start().has_value());
  LMDJ_CHECK(harness.output->stop().has_value());
}

void start_unwind_is_terminal_when_listener_removal_fails() {
  Harness harness;
  harness.services->fail_once("initialize");
  harness.services->fail_once("remove_overload_listener");

  const auto failed = harness.output->start();
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().details.at("operation") == "initialize");
  LMDJ_CHECK(harness.output->state() == CoreAudioState::failed);
  harness.services->notify_overload();
  LMDJ_CHECK(harness.output->telemetry().device_overloads == 1);
  LMDJ_CHECK(!harness.output->start().has_value());
  LMDJ_CHECK(!harness.output->stop().has_value());
}

void duplicate_start_reports_already_running() {
  Harness harness;
  LMDJ_CHECK(harness.output->start().has_value());
  const auto duplicate = harness.output->start();
  LMDJ_CHECK(!duplicate.has_value());
  LMDJ_CHECK(duplicate.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(duplicate.error().details.at("reason") == "already_running");
  LMDJ_CHECK(harness.output->state() == CoreAudioState::running);
  LMDJ_CHECK(harness.services->calls.size() == 5);
  LMDJ_CHECK(harness.output->stop().has_value());
}

void stop_is_idempotent_without_extra_framework_calls() {
  Harness harness;
  LMDJ_CHECK(harness.output->stop().has_value());
  LMDJ_CHECK(harness.services->calls.empty());
  LMDJ_CHECK(harness.output->start().has_value());
  LMDJ_CHECK(harness.output->stop().has_value());
  const auto calls_after_first_stop = harness.services->calls.size();
  LMDJ_CHECK(harness.output->stop().has_value());
  LMDJ_CHECK(harness.services->calls.size() == calls_after_first_stop);
}

void stop_retains_the_first_error_and_restarts_after_safe_disposal() {
  const std::array<std::string, 2> recoverable_failures{
      "stop", "uninitialize"};
  for (const auto& operation : recoverable_failures) {
    Harness harness;
    LMDJ_CHECK(harness.output->start().has_value());
    harness.services->fail_once(operation);

    const auto stopped = harness.output->stop();
    LMDJ_CHECK(!stopped.has_value());
    LMDJ_CHECK(stopped.error().details.at("operation") == operation);
    LMDJ_CHECK(harness.output->state() == CoreAudioState::stopped);
    LMDJ_CHECK(harness.engine.telemetry().state == RealtimeState::stopped);
    LMDJ_CHECK(harness.output->start().has_value());
    LMDJ_CHECK(harness.output->stop().has_value());
  }

  Harness multiple;
  LMDJ_CHECK(multiple.output->start().has_value());
  multiple.services->fail_once("stop");
  multiple.services->fail_once("uninitialize");
  const auto stopped = multiple.output->stop();
  LMDJ_CHECK(!stopped.has_value());
  LMDJ_CHECK(stopped.error().details.at("operation") == "stop");
  LMDJ_CHECK(multiple.output->state() == CoreAudioState::stopped);
}

void failed_listener_removal_is_terminal() {
  Harness harness;
  LMDJ_CHECK(harness.output->start().has_value());
  harness.services->fail_once("remove_overload_listener");

  const auto stopped = harness.output->stop();
  LMDJ_CHECK(!stopped.has_value());
  LMDJ_CHECK(stopped.error().details.at("operation") ==
             "remove_overload_listener");
  LMDJ_CHECK(harness.output->state() == CoreAudioState::failed);
  LMDJ_CHECK(harness.engine.telemetry().state == RealtimeState::running);
  harness.services->notify_overload();
  LMDJ_CHECK(harness.output->telemetry().device_overloads == 1);
}

void failed_disposal_is_terminal_and_preserves_engine_samples() {
  Harness harness;
  const std::array<float, 1> sample{0.375F};
  LMDJ_CHECK(harness.engine.load_sample(0, sample).has_value());
  harness.services->fail_once("start");
  harness.services->fail_once("dispose");

  const auto failed_start = harness.output->start();
  LMDJ_CHECK(!failed_start.has_value());
  LMDJ_CHECK(failed_start.error().details.at("operation") == "start");
  LMDJ_CHECK(harness.output->state() == CoreAudioState::failed);
  LMDJ_CHECK(harness.engine.telemetry().state == RealtimeState::running);
  LMDJ_CHECK(harness.engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  harness.engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == sample[0] && right[0] == sample[0]);

  const auto terminal_start = harness.output->start();
  const auto terminal_stop = harness.output->stop();
  LMDJ_CHECK(!terminal_start.has_value());
  LMDJ_CHECK(!terminal_stop.has_value());
  LMDJ_CHECK(terminal_start.error().code == terminal_stop.error().code);
  LMDJ_CHECK(terminal_start.error().message == terminal_stop.error().message);
  LMDJ_CHECK(terminal_start.error().details == terminal_stop.error().details);
  LMDJ_CHECK(terminal_start.error().details.at("reason") ==
             "callback_termination_unproven");
}

void failed_stop_disposal_is_terminal_and_preserves_engine_samples() {
  Harness harness;
  const std::array<float, 1> sample{-0.625F};
  LMDJ_CHECK(harness.engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(harness.output->start().has_value());
  harness.services->fail_once("dispose");

  const auto failed_stop = harness.output->stop();
  LMDJ_CHECK(!failed_stop.has_value());
  LMDJ_CHECK(failed_stop.error().details.at("operation") == "dispose");
  LMDJ_CHECK(harness.output->state() == CoreAudioState::failed);
  LMDJ_CHECK(harness.engine.telemetry().state == RealtimeState::running);
  LMDJ_CHECK(harness.engine.enqueue(TriggerEvent{2, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  harness.engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(left[0] == sample[0] && right[0] == sample[0]);
}

void renders_engine_output_and_reports_callback_telemetry() {
  Harness harness;
  const std::array<float, 2> sample{0.25F, -0.5F};
  LMDJ_CHECK(harness.engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(harness.output->start().has_value());
  LMDJ_CHECK(harness.engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);

  std::array<float, 2> left{};
  std::array<float, 2> right{};
  StereoBufferList storage{
      2,
      {{1, static_cast<UInt32>(sizeof(left)), left.data()},
       {1, static_cast<UInt32>(sizeof(right)), right.data()}},
  };
  auto* buffers = reinterpret_cast<AudioBufferList*>(&storage);
  LMDJ_CHECK(harness.services->render(2, buffers) == noErr);
  LMDJ_CHECK(left == sample && right == sample);
  LMDJ_CHECK(harness.clock->observed_begin == 1);
  LMDJ_CHECK(harness.clock->observed_end == 2);

  harness.services->notify_overload();
  harness.clock->elapsed_seconds = 2.0 / 48'000.0;
  LMDJ_CHECK(harness.services->render(2, buffers) == noErr);
  LMDJ_CHECK(harness.output->telemetry().deadline_overruns == 0);
  harness.clock->elapsed_seconds = 3.0 / 48'000.0;
  LMDJ_CHECK(harness.services->render(2, buffers) == noErr);
  const auto telemetry = harness.output->telemetry();
  LMDJ_CHECK(telemetry.device_overloads == 1);
  LMDJ_CHECK(telemetry.callback_failures == 0);
  LMDJ_CHECK(telemetry.deadline_overruns == 1);
  LMDJ_CHECK(harness.output->stop().has_value());
}

void rejects_invalid_audio_buffer_lists() {
  Harness harness;
  LMDJ_CHECK(harness.output->start().has_value());

  std::array<float, 2> left{};
  std::array<float, 2> right{};
  StereoBufferList storage{
      2,
      {{1, static_cast<UInt32>(sizeof(left)), left.data()},
       {1, static_cast<UInt32>(sizeof(right)), right.data()}},
  };
  auto* buffers = reinterpret_cast<AudioBufferList*>(&storage);

  LMDJ_CHECK(harness.services->render(2, nullptr) == kAudio_ParamError);
  storage.count = 1;
  LMDJ_CHECK(harness.services->render(2, buffers) == kAudio_ParamError);
  storage.count = 2;
  storage.buffers[0].mNumberChannels = 2;
  LMDJ_CHECK(harness.services->render(2, buffers) == kAudio_ParamError);
  storage.buffers[0].mNumberChannels = 1;
  storage.buffers[1].mDataByteSize = sizeof(float);
  LMDJ_CHECK(harness.services->render(2, buffers) == kAudio_ParamError);
  storage.buffers[1].mDataByteSize = sizeof(right);
  storage.buffers[0].mData = nullptr;
  LMDJ_CHECK(harness.services->render(2, buffers) == kAudio_ParamError);
  LMDJ_CHECK(harness.output->telemetry().callback_failures == 5);
  LMDJ_CHECK(harness.engine.telemetry().callback_count == 0);
  LMDJ_CHECK(harness.output->stop().has_value());
}

void successful_restart_resets_adapter_telemetry() {
  Harness harness;
  LMDJ_CHECK(harness.output->start().has_value());
  LMDJ_CHECK(harness.services->render(1, nullptr) == kAudio_ParamError);
  harness.services->notify_overload();
  LMDJ_CHECK(harness.output->stop().has_value());
  LMDJ_CHECK(harness.output->telemetry().callback_failures == 1);
  LMDJ_CHECK(harness.output->telemetry().device_overloads == 1);

  LMDJ_CHECK(harness.output->start().has_value());
  const auto reset = harness.output->telemetry();
  LMDJ_CHECK(reset.device_overloads == 0);
  LMDJ_CHECK(reset.callback_failures == 0);
  LMDJ_CHECK(reset.deadline_overruns == 0);
  LMDJ_CHECK(harness.output->stop().has_value());
}

}  // namespace

int main() {
  concrete_services_forward_exact_coreaudio_arguments();
  concrete_services_map_signed_framework_errors();
  concrete_services_retain_owned_resources_for_destructor_cleanup();
  default_factories_are_passive_until_start();
  starts_and_stops_in_the_approved_order();
  start_failures_unwind_and_allow_restart();
  a_prestarted_engine_is_stopped_after_safe_unwind();
  start_unwind_is_terminal_when_listener_removal_fails();
  duplicate_start_reports_already_running();
  stop_is_idempotent_without_extra_framework_calls();
  stop_retains_the_first_error_and_restarts_after_safe_disposal();
  failed_listener_removal_is_terminal();
  failed_disposal_is_terminal_and_preserves_engine_samples();
  failed_stop_disposal_is_terminal_and_preserves_engine_samples();
  renders_engine_output_and_reports_callback_telemetry();
  rejects_invalid_audio_buffer_lists();
  successful_restart_resets_adapter_telemetry();
}
