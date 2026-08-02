#include <lmdj/audio/apple/coreaudio_output.hpp>

#include "coreaudio_output_state.hpp"

#include <cstdint>
#include <memory>
#include <utility>

namespace lmdj::audio::apple {
namespace detail {
namespace {

static_assert(std::atomic<std::uint64_t>::is_always_lock_free);

foundation::Result<void> already_running_error() {
  return foundation::Result<void>::failure(foundation::Error{
      foundation::ErrorCode::invalid_argument,
      "CoreAudio output is already running",
      {{"reason", "already_running"}},
  });
}

foundation::Result<void> terminal_state_error() {
  return foundation::Result<void>::failure(foundation::Error{
      foundation::ErrorCode::io_error,
      "CoreAudio output callback termination could not be proven",
      {{"reason", "callback_termination_unproven"}},
  });
}

}  // namespace

CoreAudioOutputStateMachine::CoreAudioOutputStateMachine(
    RealtimeEngine& engine,
    std::unique_ptr<CoreAudioServices> services,
    std::unique_ptr<MonotonicClock> clock)
    : engine_(engine),
      services_(std::move(services)),
      clock_(std::move(clock)) {}

foundation::Result<void> CoreAudioOutputStateMachine::start() {
  if (state_ == CoreAudioState::failed) {
    return terminal_state_error();
  }
  if (state_ == CoreAudioState::running) {
    return already_running_error();
  }

  device_overloads_.store(0, std::memory_order_relaxed);
  callback_failures_.store(0, std::memory_order_relaxed);
  deadline_overruns_.store(0, std::memory_order_relaxed);

  auto result = services_->create(&render_callback, this);
  if (!result.has_value()) {
    engine_.stop();
    return result;
  }
  created_ = true;

  result = services_->configure(kRealtimeSampleRate, kRealtimeChannels);
  if (result.has_value()) {
    result = services_->add_overload_listener(&overload_callback, this);
    if (result.has_value()) {
      listener_added_ = true;
      result = services_->initialize();
      if (result.has_value()) {
        initialized_ = true;
        result = engine_.start();
        if (result.has_value()) {
          result = services_->start();
          if (result.has_value()) {
            unit_started_ = true;
            state_ = CoreAudioState::running;
            return result;
          }
        }
      }
    }
  }

  const auto first_error = result.error();
  if (initialized_) {
    const auto cleanup = services_->uninitialize();
    if (cleanup.has_value()) {
      initialized_ = false;
    }
  }
  if (listener_added_) {
    const auto cleanup = services_->remove_overload_listener();
    if (cleanup.has_value()) {
      listener_added_ = false;
    }
  }

  bool disposed = false;
  if (created_) {
    const auto cleanup = services_->dispose();
    if (cleanup.has_value()) {
      created_ = false;
      initialized_ = false;
      unit_started_ = false;
      disposed = true;
    }
  }

  if (disposed && !listener_added_) {
    engine_.stop();
    state_ = CoreAudioState::stopped;
  } else {
    state_ = CoreAudioState::failed;
  }
  return foundation::Result<void>::failure(first_error);
}

foundation::Result<void> CoreAudioOutputStateMachine::stop() {
  if (state_ == CoreAudioState::failed) {
    return terminal_state_error();
  }
  if (state_ == CoreAudioState::stopped) {
    return foundation::Result<void>::success();
  }

  bool has_error = false;
  foundation::Error first_error{
      foundation::ErrorCode::internal_error, "unreachable CoreAudio error"};
  const auto retain_first_error = [&](const foundation::Result<void>& result) {
    if (!result.has_value() && !has_error) {
      first_error = result.error();
      has_error = true;
    }
  };

  auto cleanup = services_->stop();
  retain_first_error(cleanup);
  if (cleanup.has_value()) {
    unit_started_ = false;
  }

  cleanup = services_->remove_overload_listener();
  retain_first_error(cleanup);
  if (cleanup.has_value()) {
    listener_added_ = false;
  }

  cleanup = services_->uninitialize();
  retain_first_error(cleanup);
  if (cleanup.has_value()) {
    initialized_ = false;
  }

  cleanup = services_->dispose();
  retain_first_error(cleanup);
  const bool disposed = cleanup.has_value();
  if (disposed) {
    created_ = false;
    initialized_ = false;
    unit_started_ = false;
  }

  if (disposed && !listener_added_) {
    engine_.stop();
    state_ = CoreAudioState::stopped;
  } else {
    state_ = CoreAudioState::failed;
  }

  if (has_error) {
    return foundation::Result<void>::failure(std::move(first_error));
  }
  return foundation::Result<void>::success();
}

CoreAudioState CoreAudioOutputStateMachine::state() const noexcept {
  return state_;
}

CoreAudioTelemetry CoreAudioOutputStateMachine::telemetry() const noexcept {
  return CoreAudioTelemetry{
      device_overloads_.load(std::memory_order_relaxed),
      callback_failures_.load(std::memory_order_relaxed),
      deadline_overruns_.load(std::memory_order_relaxed),
  };
}

OSStatus CoreAudioOutputStateMachine::render_callback(
    void* context,
    AudioUnitRenderActionFlags*,
    const AudioTimeStamp*,
    UInt32,
    UInt32 frames,
    AudioBufferList* buffers) noexcept {
  auto* output = static_cast<CoreAudioOutputStateMachine*>(context);
  const auto required_bytes =
      static_cast<std::uint64_t>(frames) * sizeof(float);
  if (output == nullptr || buffers == nullptr ||
      buffers->mNumberBuffers != 2 ||
      buffers->mBuffers[0].mNumberChannels != 1 ||
      buffers->mBuffers[1].mNumberChannels != 1 ||
      buffers->mBuffers[0].mData == nullptr ||
      buffers->mBuffers[1].mData == nullptr ||
      buffers->mBuffers[0].mDataByteSize < required_bytes ||
      buffers->mBuffers[1].mDataByteSize < required_bytes) {
    if (output != nullptr) {
      output->callback_failures_.fetch_add(1, std::memory_order_relaxed);
    }
    return kAudio_ParamError;
  }

  const auto begin = output->clock_->now();
  output->engine_.render(
      static_cast<float*>(buffers->mBuffers[0].mData),
      static_cast<float*>(buffers->mBuffers[1].mData),
      frames);
  const auto end = output->clock_->now();
  const auto elapsed = output->clock_->seconds_between(begin, end);
  const auto deadline =
      static_cast<double>(frames) / static_cast<double>(kRealtimeSampleRate);
  if (elapsed > deadline) {
    output->deadline_overruns_.fetch_add(1, std::memory_order_relaxed);
  }
  return noErr;
}

OSStatus CoreAudioOutputStateMachine::overload_callback(
    AudioObjectID,
    UInt32,
    const AudioObjectPropertyAddress*,
    void* context) noexcept {
  static_cast<CoreAudioOutputStateMachine*>(context)
      ->device_overloads_.fetch_add(1, std::memory_order_relaxed);
  return noErr;
}

}  // namespace detail

class CoreAudioOutput::Impl final {
 public:
  explicit Impl(RealtimeEngine& engine)
      : state_machine_(
            engine,
            detail::make_default_coreaudio_services(),
            detail::make_mach_monotonic_clock()) {}

  ~Impl() { (void)state_machine_.stop(); }

  detail::CoreAudioOutputStateMachine state_machine_;
};

CoreAudioOutput::CoreAudioOutput(RealtimeEngine& engine)
    : impl_(std::make_unique<Impl>(engine)) {}

CoreAudioOutput::~CoreAudioOutput() = default;

foundation::Result<void> CoreAudioOutput::start() {
  return impl_->state_machine_.start();
}

foundation::Result<void> CoreAudioOutput::stop() {
  return impl_->state_machine_.stop();
}

CoreAudioState CoreAudioOutput::state() const noexcept {
  return impl_->state_machine_.state();
}

CoreAudioTelemetry CoreAudioOutput::telemetry() const noexcept {
  return impl_->state_machine_.telemetry();
}

}  // namespace lmdj::audio::apple
