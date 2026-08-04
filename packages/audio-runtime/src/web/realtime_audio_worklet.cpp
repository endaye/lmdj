#include <lmdj/audio/web/realtime_audio_worklet.hpp>

#if defined(__EMSCRIPTEN__)

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <thread>

#include <emscripten/threading.h>
#include <emscripten/webaudio.h>

namespace lmdj::audio::web {
namespace {

constexpr std::int32_t kRequiredSampleRate = 48'000;
constexpr std::int32_t kRequiredFrames = 128;
constexpr std::size_t kWorkletStackBytes = 64U * 1024U;

enum class CallbackGate : std::uint32_t {
  open,
  final_quantum_requested,
  closed,
};

static_assert(std::atomic<std::uint32_t>::is_always_lock_free);
static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
static_assert(std::atomic<bool>::is_always_lock_free);
static_assert(std::atomic<CallbackGate>::is_always_lock_free);
static_assert(std::atomic<RealtimeAudioWorkletState>::is_always_lock_free);
static_assert(std::atomic<RealtimeAudioWorkletFatal>::is_always_lock_free);

foundation::Error worklet_error(const char* message) noexcept {
  return foundation::Error{
      foundation::ErrorCode::internal_error,
      message,
  };
}

}  // namespace

struct RealtimeAudioWorklet::Impl {
  Impl(RealtimeEngine& owned_engine, RealtimeAudioWorkletHooks owned_hooks)
      : engine(owned_engine), hooks(owned_hooks) {}

  static bool process(
      int num_inputs,
      const AudioSampleFrame* inputs,
      int num_outputs,
      AudioSampleFrame* outputs,
      int num_params,
      const AudioParamFrame* params,
      void* user_data) noexcept {
    auto& self = *static_cast<Impl*>(user_data);
    if (self.fatal_code.load(std::memory_order_acquire) !=
            RealtimeAudioWorkletFatal::none ||
        self.gate.load(std::memory_order_acquire) == CallbackGate::closed) {
      return false;
    }
    bool expected = false;
    if (!self.in_flight.compare_exchange_strong(
            expected,
            true,
            std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      self.latch_fatal(RealtimeAudioWorkletFatal::callback_reentry);
      return false;
    }

    const bool valid =
        num_inputs == 0 && num_outputs == 1 &&
        outputs != nullptr && outputs[0].numberOfChannels == 2 &&
        outputs[0].samplesPerChannel == kRequiredFrames &&
        outputs[0].data != nullptr && num_params == 0;
    static_cast<void>(inputs);
    static_cast<void>(params);
    if (!valid) {
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
      if (outputs != nullptr && num_outputs > 0) {
        self.observed_quantum.store(
            static_cast<std::uint32_t>(
                std::max(outputs[0].samplesPerChannel, 0)),
            std::memory_order_relaxed);
      }
#endif
      self.in_flight.store(false, std::memory_order_release);
      self.latch_fatal(RealtimeAudioWorkletFatal::invalid_callback_shape);
      return false;
    }

    auto* left = outputs[0].data;
    auto* right = outputs[0].data + outputs[0].samplesPerChannel;
    self.engine.render(left, right, kRequiredFrames);
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
    self.observed_quantum.store(kRequiredFrames, std::memory_order_relaxed);
    self.render_count.fetch_add(1, std::memory_order_relaxed);

    float energy = 0.0F;
    for (std::int32_t frame = 0; frame < kRequiredFrames; ++frame) {
      energy += std::abs(left[frame]) + std::abs(right[frame]);
    }
    const auto scaled = static_cast<std::uint32_t>(
        std::min(energy * 1'000'000.0F,
                 static_cast<float>(UINT32_MAX)));
    auto previous = self.energy_microunits.load(std::memory_order_relaxed);
    while (previous < scaled &&
           !self.energy_microunits.compare_exchange_weak(
               previous,
               scaled,
               std::memory_order_relaxed,
               std::memory_order_relaxed)) {
    }
#endif
    self.acknowledged.store(
        self.engine.bank_telemetry().current_generation,
        std::memory_order_release);
    self.in_flight.store(false, std::memory_order_release);

    auto requested = CallbackGate::final_quantum_requested;
    if (self.gate.compare_exchange_strong(
            requested,
            CallbackGate::closed,
            std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      return false;
    }
    return self.gate.load(std::memory_order_acquire) == CallbackGate::open;
  }

  static void processor_created(
      EMSCRIPTEN_WEBAUDIO_T context,
      bool success,
      void* user_data) {
    auto& self = *static_cast<Impl*>(user_data);
    if (!emscripten_is_main_browser_thread()) {
      self.latch_fatal(RealtimeAudioWorkletFatal::wrong_browser_thread);
      return;
    }
    if (!success) {
      self.latch_fatal(RealtimeAudioWorkletFatal::processor_create_failed);
      return;
    }
    int output_channel_counts[1] = {2};
    EmscriptenAudioWorkletNodeCreateOptions options = {
        .numberOfInputs = 0,
        .numberOfOutputs = 1,
        .outputChannelCounts = output_channel_counts,
        .channelCount = 2,
        .channelCountMode = WEBAUDIO_CHANNEL_COUNT_MODE_EXPLICIT,
        .channelInterpretation = WEBAUDIO_CHANNEL_INTERPRETATION_DISCRETE,
    };
    const auto node = emscripten_create_wasm_audio_worklet_node(
        context,
        "lmdj-realtime-engine",
        &options,
        &Impl::process,
        &self);
    if (node == 0) {
      self.latch_fatal(RealtimeAudioWorkletFatal::node_create_failed);
      return;
    }
    emscripten_audio_node_connect(node, context, 0, 0);
    self.node.store(node, std::memory_order_release);
    self.worklet_state.store(
        RealtimeAudioWorkletState::node_ready,
        std::memory_order_release);
    if (self.hooks.context == nullptr ||
        self.hooks.schedule_control_install == nullptr ||
        !self.hooks.schedule_control_install(self.hooks.context)) {
      self.latch_fatal(
          RealtimeAudioWorkletFatal::coordinator_install_failed);
    }
  }

  static void worklet_started(
      EMSCRIPTEN_WEBAUDIO_T context,
      bool success,
      void* user_data) {
    auto& self = *static_cast<Impl*>(user_data);
    if (!emscripten_is_main_browser_thread()) {
      self.latch_fatal(RealtimeAudioWorkletFatal::wrong_browser_thread);
      return;
    }
    if (!success) {
      self.latch_fatal(
          RealtimeAudioWorkletFatal::worklet_thread_start_failed);
      return;
    }
    const WebAudioWorkletProcessorCreateOptions options = {
        .name = "lmdj-realtime-engine",
        .numAudioParams = 0,
        .audioParamDescriptors = nullptr,
    };
    emscripten_create_wasm_audio_worklet_processor_async(
        context, &options, &Impl::processor_created, &self);
  }

  void latch_fatal(RealtimeAudioWorkletFatal code) noexcept {
    auto expected = RealtimeAudioWorkletFatal::none;
    fatal_code.compare_exchange_strong(
        expected,
        code,
        std::memory_order_acq_rel,
        std::memory_order_acquire);
    gate.store(CallbackGate::closed, std::memory_order_release);
    worklet_state.store(
        RealtimeAudioWorkletState::fatal,
        std::memory_order_release);
  }

  RealtimeEngine& engine;
  RealtimeAudioWorkletHooks hooks;
  alignas(16) std::array<std::byte, kWorkletStackBytes> stack{};
  std::atomic<RealtimeAudioWorkletState> worklet_state{
      RealtimeAudioWorkletState::idle};
  std::atomic<RealtimeAudioWorkletFatal> fatal_code{
      RealtimeAudioWorkletFatal::none};
  std::atomic<CallbackGate> gate{CallbackGate::open};
  std::atomic<bool> in_flight{false};
  std::atomic<std::uint64_t> acknowledged{0};
  std::atomic<std::int32_t> node{0};
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  std::atomic<std::uint32_t> observed_quantum{0};
  std::atomic<std::uint32_t> render_count{0};
  std::atomic<std::uint32_t> energy_microunits{0};
#endif
};

RealtimeAudioWorklet::RealtimeAudioWorklet(
    RealtimeEngine& engine, RealtimeAudioWorkletHooks hooks)
    : impl_(std::make_unique<Impl>(engine, hooks)) {}

RealtimeAudioWorklet::~RealtimeAudioWorklet() = default;

int RealtimeAudioWorklet::start_on_browser_main(
    std::int32_t audio_context_handle) noexcept {
  if (!emscripten_is_main_browser_thread()) {
    impl_->latch_fatal(RealtimeAudioWorkletFatal::wrong_browser_thread);
    return -1;
  }
  if (audio_context_handle <= 0 ||
      impl_->worklet_state.load(std::memory_order_acquire) !=
          RealtimeAudioWorkletState::idle) {
    impl_->latch_fatal(RealtimeAudioWorkletFatal::invalid_audio_context);
    return -2;
  }
  if (emscripten_audio_context_sample_rate(audio_context_handle) !=
      kRequiredSampleRate) {
    impl_->latch_fatal(RealtimeAudioWorkletFatal::unsupported_sample_rate);
    return -3;
  }
  if (emscripten_audio_context_quantum_size(audio_context_handle) !=
      kRequiredFrames) {
    impl_->latch_fatal(
        RealtimeAudioWorkletFatal::unsupported_render_quantum);
    return -4;
  }
  impl_->worklet_state.store(
      RealtimeAudioWorkletState::starting,
      std::memory_order_release);
  emscripten_start_wasm_audio_worklet_thread_async(
      audio_context_handle,
      impl_->stack.data(),
      impl_->stack.size(),
      &Impl::worklet_started,
      impl_.get());
  return 1;
}

void RealtimeAudioWorklet::complete_control_install(bool installed) noexcept {
  if (!installed) {
    impl_->latch_fatal(
        RealtimeAudioWorkletFatal::coordinator_install_failed);
    return;
  }
  auto expected = RealtimeAudioWorkletState::node_ready;
  if (!impl_->worklet_state.compare_exchange_strong(
          expected,
          RealtimeAudioWorkletState::ready,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    impl_->latch_fatal(
        RealtimeAudioWorkletFatal::coordinator_install_failed);
  }
}

foundation::Result<void> RealtimeAudioWorklet::await_quiescent(
    std::uint32_t timeout_ms) noexcept {
  auto expected = CallbackGate::open;
  impl_->gate.compare_exchange_strong(
      expected,
      CallbackGate::final_quantum_requested,
      std::memory_order_acq_rel,
      std::memory_order_acquire);
  const auto deadline = std::chrono::steady_clock::now() +
                        std::chrono::milliseconds(timeout_ms);
  while (impl_->gate.load(std::memory_order_acquire) !=
             CallbackGate::closed ||
         impl_->in_flight.load(std::memory_order_acquire)) {
    if (std::chrono::steady_clock::now() >= deadline) {
      return foundation::Result<void>::failure(
          worklet_error("Wasm AudioWorklet quiescence timed out"));
    }
    std::this_thread::yield();
  }
  return foundation::Result<void>::success();
}

bool RealtimeAudioWorklet::ready() const noexcept {
  return impl_->worklet_state.load(std::memory_order_acquire) ==
             RealtimeAudioWorkletState::ready &&
         impl_->gate.load(std::memory_order_acquire) == CallbackGate::open;
}

std::uint64_t RealtimeAudioWorklet::acknowledged_generation() const noexcept {
  return impl_->acknowledged.load(std::memory_order_acquire);
}

RealtimeAudioWorkletState RealtimeAudioWorklet::state() const noexcept {
  return impl_->worklet_state.load(std::memory_order_acquire);
}

RealtimeAudioWorkletFatal RealtimeAudioWorklet::fatal() const noexcept {
  return impl_->fatal_code.load(std::memory_order_acquire);
}

std::int32_t RealtimeAudioWorklet::node_handle() const noexcept {
  return impl_->node.load(std::memory_order_acquire);
}

void RealtimeAudioWorklet::latch_processor_error() noexcept {
  impl_->latch_fatal(RealtimeAudioWorkletFatal::processor_error);
}

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
std::uint32_t RealtimeAudioWorklet::observed_frames() const noexcept {
  return impl_->observed_quantum.load(std::memory_order_acquire);
}

std::uint32_t RealtimeAudioWorklet::render_calls() const noexcept {
  return impl_->render_count.load(std::memory_order_acquire);
}

std::uint32_t RealtimeAudioWorklet::output_energy_microunits() const noexcept {
  return impl_->energy_microunits.load(std::memory_order_acquire);
}

bool RealtimeAudioWorklet::callback_gate_closed() const noexcept {
  return impl_->gate.load(std::memory_order_acquire) == CallbackGate::closed;
}

bool RealtimeAudioWorklet::callback_in_flight() const noexcept {
  return impl_->in_flight.load(std::memory_order_acquire);
}

bool RealtimeAudioWorklet::invoke_invalid_shape_for_conformance(
    std::int32_t frames) noexcept {
  std::array<float, 512> output{};
  AudioSampleFrame frame = {
      .numberOfChannels = 2,
      .samplesPerChannel = frames,
      .data = output.data(),
  };
  return Impl::process(
      0, nullptr, 1, &frame, 0, nullptr, impl_.get());
}

bool RealtimeAudioWorklet::generation_matches_for_conformance(
    std::uint64_t expected_generation) const noexcept {
  return acknowledged_generation() == expected_generation;
}
#endif

}  // namespace lmdj::audio::web

#endif
