#include <lmdj/audio/apple/coreaudio_output.hpp>

#include "coreaudio_output_state.hpp"

#include <algorithm>
#include <cstdint>
#include <memory>
#include <thread>
#include <utility>

namespace lmdj::audio::apple {
namespace detail {

class CoreAudioOutputStateMachine::CallbackContext final {
 public:
  CallbackContext(RealtimeEngine& engine, MonotonicClock& clock)
      : engine_(&engine), clock_(&clock) {}

  void reset_telemetry() noexcept {
    device_overloads_.store(0, std::memory_order_relaxed);
    callback_failures_.store(0, std::memory_order_relaxed);
    deadline_overruns_.store(0, std::memory_order_relaxed);
  }

  void enable() noexcept {
    enabled_.store(true, std::memory_order_seq_cst);
  }

  bool enter() noexcept {
    in_flight_.fetch_add(1, std::memory_order_seq_cst);
    return enabled_.load(std::memory_order_seq_cst);
  }

  void leave() noexcept {
    in_flight_.fetch_sub(1, std::memory_order_seq_cst);
  }

  void disable_and_drain() noexcept {
    enabled_.store(false, std::memory_order_seq_cst);
    while (in_flight_.load(std::memory_order_seq_cst) != 0) {
      std::this_thread::yield();
    }
  }

  void quarantine() noexcept {
    static std::atomic<CallbackContext*> quarantine_head{nullptr};
    auto* observed = quarantine_head.load(std::memory_order_relaxed);
    do {
      quarantine_next_ = observed;
    } while (!quarantine_head.compare_exchange_weak(
        observed,
        this,
        std::memory_order_release,
        std::memory_order_relaxed));
  }

  RealtimeEngine& engine() noexcept { return *engine_; }
  MonotonicClock& clock() noexcept { return *clock_; }

  void record_device_overload() noexcept {
    device_overloads_.fetch_add(1, std::memory_order_relaxed);
  }

  void record_callback_failure() noexcept {
    callback_failures_.fetch_add(1, std::memory_order_relaxed);
  }

  void record_deadline_overrun() noexcept {
    deadline_overruns_.fetch_add(1, std::memory_order_relaxed);
  }

  CoreAudioTelemetry telemetry() const noexcept {
    return CoreAudioTelemetry{
        device_overloads_.load(std::memory_order_relaxed),
        callback_failures_.load(std::memory_order_relaxed),
        deadline_overruns_.load(std::memory_order_relaxed),
    };
  }

 private:
  RealtimeEngine* engine_;
  MonotonicClock* clock_;
  std::atomic<bool> enabled_{false};
  std::atomic<std::uint64_t> in_flight_{0};
  std::atomic<std::uint64_t> device_overloads_{0};
  std::atomic<std::uint64_t> callback_failures_{0};
  std::atomic<std::uint64_t> deadline_overruns_{0};
  CallbackContext* quarantine_next_ = nullptr;
};

namespace {

static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
static_assert(std::atomic<bool>::is_always_lock_free);

bool valid_render_buffers(
    AudioBufferList* buffers, std::uint64_t required_bytes) noexcept {
  return buffers != nullptr && buffers->mNumberBuffers == 2 &&
         buffers->mBuffers[0].mNumberChannels == 1 &&
         buffers->mBuffers[1].mNumberChannels == 1 &&
         buffers->mBuffers[0].mData != nullptr &&
         buffers->mBuffers[1].mData != nullptr &&
         buffers->mBuffers[0].mDataByteSize >= required_bytes &&
         buffers->mBuffers[1].mDataByteSize >= required_bytes;
}

OSStatus silence_render_buffers(
    AudioBufferList* buffers, UInt32 frames) noexcept {
  const auto required_bytes =
      static_cast<std::uint64_t>(frames) * sizeof(float);
  if (!valid_render_buffers(buffers, required_bytes)) {
    return kAudio_ParamError;
  }
  std::fill_n(
      static_cast<float*>(buffers->mBuffers[0].mData), frames, 0.0F);
  std::fill_n(
      static_cast<float*>(buffers->mBuffers[1].mData), frames, 0.0F);
  return noErr;
}

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
      clock_(std::move(clock)),
      callback_context_(
          std::make_unique<CallbackContext>(engine_, *clock_)) {}

CoreAudioOutputStateMachine::~CoreAudioOutputStateMachine() {
  if (state_ == CoreAudioState::running) {
    (void)stop();
  }
  if (state_ == CoreAudioState::failed) {
    callback_context_->disable_and_drain();
    auto* context = callback_context_.release();
    context->quarantine();
  }
}

foundation::Result<void> CoreAudioOutputStateMachine::start() {
  if (state_ == CoreAudioState::failed) {
    return terminal_state_error();
  }
  if (state_ == CoreAudioState::running) {
    return already_running_error();
  }

  callback_context_->reset_telemetry();

  auto result =
      services_->create(&render_callback, callback_context_.get());
  if (!result.has_value()) {
    const auto first_error = result.error();
    callback_context_->disable_and_drain();
    const auto cleanup = services_->dispose();
    if (cleanup.has_value()) {
      engine_.stop();
      state_ = CoreAudioState::stopped;
    } else {
      state_ = CoreAudioState::failed;
    }
    return foundation::Result<void>::failure(first_error);
  }
  created_ = true;

  result = services_->configure(kRealtimeSampleRate, kRealtimeChannels);
  if (result.has_value()) {
    result = services_->add_overload_listener(
        &overload_callback, callback_context_.get());
    if (result.has_value()) {
      listener_added_ = true;
      result = services_->initialize();
      if (result.has_value()) {
        initialized_ = true;
        result = engine_.start();
        if (result.has_value()) {
          callback_context_->enable();
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
  callback_context_->disable_and_drain();
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

  callback_context_->disable_and_drain();

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
  return callback_context_->telemetry();
}

OSStatus CoreAudioOutputStateMachine::render_callback(
    void* context,
    AudioUnitRenderActionFlags*,
    const AudioTimeStamp*,
    UInt32,
    UInt32 frames,
    AudioBufferList* buffers) noexcept {
  auto* callback_context = static_cast<CallbackContext*>(context);
  if (callback_context == nullptr) {
    return kAudio_ParamError;
  }
  const bool enabled = callback_context->enter();
  struct CallbackExit final {
    CallbackContext& context;
    ~CallbackExit() { context.leave(); }
  } callback_exit{*callback_context};
  if (!enabled) {
    return silence_render_buffers(buffers, frames);
  }

  const auto required_bytes =
      static_cast<std::uint64_t>(frames) * sizeof(float);
  if (!valid_render_buffers(buffers, required_bytes)) {
    callback_context->record_callback_failure();
    return kAudio_ParamError;
  }

  const auto begin = callback_context->clock().now();
  callback_context->engine().render(
      static_cast<float*>(buffers->mBuffers[0].mData),
      static_cast<float*>(buffers->mBuffers[1].mData),
      frames);
  const auto end = callback_context->clock().now();
  const auto elapsed =
      callback_context->clock().seconds_between(begin, end);
  const auto deadline =
      static_cast<double>(frames) / static_cast<double>(kRealtimeSampleRate);
  if (elapsed > deadline) {
    callback_context->record_deadline_overrun();
  }
  return noErr;
}

OSStatus CoreAudioOutputStateMachine::overload_callback(
    AudioObjectID,
    UInt32,
    const AudioObjectPropertyAddress*,
    void* context) noexcept {
  auto* callback_context = static_cast<CallbackContext*>(context);
  if (callback_context == nullptr) {
    return noErr;
  }
  const bool enabled = callback_context->enter();
  if (enabled) {
    callback_context->record_device_overload();
  }
  callback_context->leave();
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
