#include <lmdj/audio/web/realtime_audio_worklet.hpp>

#if defined(__EMSCRIPTEN__)

#include <algorithm>
#include <array>
#include <atomic>
#include <climits>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

#include <emscripten/threading.h>
#include <emscripten/webaudio.h>

namespace lmdj::audio::web {
namespace {

constexpr std::int32_t kRequiredSampleRate = 48'000;
constexpr std::int32_t kRequiredFrames = 128;
constexpr std::size_t kWorkletStackBytes = 64U * 1024U;
constexpr auto kQuiescenceRecheckInterval = std::chrono::milliseconds{10};

static_assert(std::atomic<std::uint32_t>::is_always_lock_free);
static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
static_assert(std::atomic<bool>::is_always_lock_free);
static_assert(std::atomic<RealtimeAudioWorkletGate>::is_always_lock_free);
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
        self.gate.load(std::memory_order_acquire) ==
            RealtimeAudioWorkletGate::terminal) {
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
      self.latch_fatal(RealtimeAudioWorkletFatal::invalid_callback_shape);
      return false;
    }

    auto gate = self.gate.load(std::memory_order_acquire);
    if (gate == RealtimeAudioWorkletGate::paused) {
      std::fill_n(
          outputs[0].data,
          outputs[0].numberOfChannels * outputs[0].samplesPerChannel,
          0.0F);
      return true;
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
    gate = self.gate.load(std::memory_order_acquire);
    if (gate == RealtimeAudioWorkletGate::paused) {
      std::fill_n(
          outputs[0].data,
          outputs[0].numberOfChannels * outputs[0].samplesPerChannel,
          0.0F);
      self.in_flight.store(false, std::memory_order_release);
      self.signal_quiescence_waiters();
      return true;
    }
    if (gate == RealtimeAudioWorkletGate::terminal) {
      self.in_flight.store(false, std::memory_order_release);
      self.signal_quiescence_waiters();
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
    auto requested = RealtimeAudioWorkletGate::final_quantum_requested;
    const auto paused = self.gate.compare_exchange_strong(
        requested,
        RealtimeAudioWorkletGate::paused,
        std::memory_order_acq_rel,
        std::memory_order_acquire);
    self.in_flight.store(false, std::memory_order_release);
    if (paused || requested == RealtimeAudioWorkletGate::terminal) {
      self.signal_quiescence_waiters();
    }
    return self.gate.load(std::memory_order_acquire) !=
           RealtimeAudioWorkletGate::terminal;
  }

  void signal_quiescence_waiters() noexcept {
    quiescence_signal.fetch_add(1, std::memory_order_release);
    static_cast<void>(emscripten_futex_wake(&quiescence_signal, INT_MAX));
  }

  static void processor_created(
      EMSCRIPTEN_WEBAUDIO_T context,
      bool success,
      void* user_data) {
    auto& self = *static_cast<Impl*>(user_data);
    if (!emscripten_is_main_browser_thread()) {
      self.latch_bootstrap_fatal(
          RealtimeAudioWorkletFatal::wrong_browser_thread);
      return;
    }
    if (!success) {
      self.latch_bootstrap_fatal(
          RealtimeAudioWorkletFatal::processor_create_failed);
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
      self.latch_bootstrap_fatal(
          RealtimeAudioWorkletFatal::node_create_failed);
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
      self.latch_bootstrap_fatal(
          RealtimeAudioWorkletFatal::coordinator_install_failed);
    }
  }

  static void worklet_started(
      EMSCRIPTEN_WEBAUDIO_T context,
      bool success,
      void* user_data) {
    auto& self = *static_cast<Impl*>(user_data);
    if (!emscripten_is_main_browser_thread()) {
      self.latch_bootstrap_fatal(
          RealtimeAudioWorkletFatal::wrong_browser_thread);
      return;
    }
    if (!success) {
      self.latch_bootstrap_fatal(
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
    gate.store(RealtimeAudioWorkletGate::terminal, std::memory_order_release);
    worklet_state.store(
        RealtimeAudioWorkletState::fatal,
        std::memory_order_release);
    signal_quiescence_waiters();
  }

  void latch_bootstrap_fatal(RealtimeAudioWorkletFatal code) noexcept {
    // Bootstrap callbacks only publish atomics. Control proxying is initiated
    // later by the browser-main start Promise, never by the render callback.
    latch_fatal(code);
  }

  RealtimeAudioWorkletStart validate_configuration(
      std::int32_t realized_sample_rate,
      std::int32_t realized_render_quantum) noexcept {
    sample_rate.store(realized_sample_rate, std::memory_order_release);
    render_quantum.store(realized_render_quantum, std::memory_order_release);
    if (realized_sample_rate != kRequiredSampleRate) {
      latch_fatal(RealtimeAudioWorkletFatal::unsupported_sample_rate);
      return RealtimeAudioWorkletStart::unsupported_sample_rate;
    }
    if (realized_render_quantum != kRequiredFrames) {
      latch_fatal(RealtimeAudioWorkletFatal::unsupported_render_quantum);
      return RealtimeAudioWorkletStart::unsupported_render_quantum;
    }
    return RealtimeAudioWorkletStart::accepted;
  }

  RealtimeEngine& engine;
  RealtimeAudioWorkletHooks hooks;
  alignas(16) std::array<std::byte, kWorkletStackBytes> stack{};
  std::atomic<RealtimeAudioWorkletState> worklet_state{
      RealtimeAudioWorkletState::idle};
  std::atomic<RealtimeAudioWorkletFatal> fatal_code{
      RealtimeAudioWorkletFatal::none};
  std::atomic<RealtimeAudioWorkletGate> gate{
      RealtimeAudioWorkletGate::paused};
  std::atomic<bool> in_flight{false};
  std::atomic<std::uint32_t> quiescence_signal{0};
  std::atomic<std::uint64_t> acknowledged{0};
  std::atomic<std::int32_t> node{0};
  std::atomic<std::int32_t> sample_rate{0};
  std::atomic<std::int32_t> render_quantum{0};
  std::int32_t audio_context_handle = 0;
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  std::atomic<std::uint32_t> observed_quantum{0};
  std::atomic<std::uint32_t> render_count{0};
  std::atomic<std::uint32_t> energy_microunits{0};
  std::atomic<std::uint32_t> accepted_start_calls{0};
#endif
};

RealtimeAudioWorklet::RealtimeAudioWorklet(
    RealtimeEngine& engine, RealtimeAudioWorkletHooks hooks)
    : impl_(std::make_unique<Impl>(engine, hooks)) {}

RealtimeAudioWorklet::~RealtimeAudioWorklet() = default;

RealtimeAudioWorkletStart RealtimeAudioWorklet::start_on_browser_main(
    std::int32_t audio_context_handle) noexcept {
  if (!emscripten_is_main_browser_thread()) {
    impl_->latch_bootstrap_fatal(
        RealtimeAudioWorkletFatal::wrong_browser_thread);
    return RealtimeAudioWorkletStart::wrong_browser_thread;
  }
  if (audio_context_handle <= 0) {
    return RealtimeAudioWorkletStart::invalid_handle;
  }
  const auto state = impl_->worklet_state.load(std::memory_order_acquire);
  if (state == RealtimeAudioWorkletState::starting ||
      state == RealtimeAudioWorkletState::node_ready) {
    return impl_->audio_context_handle == audio_context_handle
               ? RealtimeAudioWorkletStart::already_starting
               : RealtimeAudioWorkletStart::duplicate_handle;
  }
  if (state == RealtimeAudioWorkletState::ready) {
    return impl_->audio_context_handle == audio_context_handle
               ? RealtimeAudioWorkletStart::already_ready
               : RealtimeAudioWorkletStart::duplicate_handle;
  }
  if (state == RealtimeAudioWorkletState::fatal) {
    return RealtimeAudioWorkletStart::fatal;
  }
  impl_->audio_context_handle = audio_context_handle;
  const auto sample_rate =
      emscripten_audio_context_sample_rate(audio_context_handle);
  const auto quantum =
      emscripten_audio_context_quantum_size(audio_context_handle);
  const auto validation = impl_->validate_configuration(sample_rate, quantum);
  if (validation != RealtimeAudioWorkletStart::accepted) {
    return validation;
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
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  impl_->accepted_start_calls.fetch_add(1, std::memory_order_relaxed);
#endif
  return RealtimeAudioWorkletStart::accepted;
}

void RealtimeAudioWorklet::complete_control_install(bool installed) noexcept {
  if (!installed) {
    impl_->latch_bootstrap_fatal(
        RealtimeAudioWorkletFatal::coordinator_install_failed);
    return;
  }
  auto expected = RealtimeAudioWorkletState::node_ready;
  if (!impl_->worklet_state.compare_exchange_strong(
          expected,
          RealtimeAudioWorkletState::ready,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    impl_->latch_bootstrap_fatal(
        RealtimeAudioWorkletFatal::coordinator_install_failed);
  }
}

foundation::Result<void> RealtimeAudioWorklet::begin_rendering() noexcept {
  if (impl_->worklet_state.load(std::memory_order_acquire) !=
          RealtimeAudioWorkletState::ready ||
      impl_->fatal_code.load(std::memory_order_acquire) !=
          RealtimeAudioWorkletFatal::none ||
      impl_->in_flight.load(std::memory_order_acquire)) {
    return foundation::Result<void>::failure(
        worklet_error("Wasm AudioWorklet is not ready to render"));
  }
  auto expected = RealtimeAudioWorkletGate::paused;
  impl_->acknowledged.store(0, std::memory_order_release);
  if (!impl_->gate.compare_exchange_strong(
          expected,
          RealtimeAudioWorkletGate::open,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    return foundation::Result<void>::failure(
        worklet_error("Wasm AudioWorklet gate is not paused"));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> RealtimeAudioWorklet::await_quiescent(
    std::uint32_t timeout_ms) noexcept {
  auto gate = impl_->gate.load(std::memory_order_acquire);
  if (gate == RealtimeAudioWorkletGate::paused &&
      !impl_->in_flight.load(std::memory_order_acquire)) {
    return foundation::Result<void>::success();
  }
  auto expected = RealtimeAudioWorkletGate::open;
  impl_->gate.compare_exchange_strong(
      expected,
      RealtimeAudioWorkletGate::final_quantum_requested,
      std::memory_order_acq_rel,
      std::memory_order_acquire);
  const auto deadline = std::chrono::steady_clock::now() +
                        std::chrono::milliseconds(timeout_ms);
  while (true) {
    const auto observed_signal =
        impl_->quiescence_signal.load(std::memory_order_acquire);
    gate = impl_->gate.load(std::memory_order_acquire);
    const auto in_flight = impl_->in_flight.load(std::memory_order_acquire);
    if (gate == RealtimeAudioWorkletGate::paused && !in_flight) {
      return foundation::Result<void>::success();
    }
    if (gate == RealtimeAudioWorkletGate::terminal && !in_flight) {
      return foundation::Result<void>::failure(
          worklet_error("Wasm AudioWorklet is terminal"));
    }
    const auto now = std::chrono::steady_clock::now();
    if (now >= deadline) {
      impl_->latch_fatal(RealtimeAudioWorkletFatal::quiescence_timeout);
      while (impl_->in_flight.load(std::memory_order_acquire)) {
        const auto terminal_signal =
            impl_->quiescence_signal.load(std::memory_order_acquire);
        if (!impl_->in_flight.load(std::memory_order_acquire)) {
          break;
        }
        static_cast<void>(emscripten_futex_wait(
            &impl_->quiescence_signal,
            terminal_signal,
            std::numeric_limits<double>::infinity()));
      }
      return foundation::Result<void>::failure(
          worklet_error("Wasm AudioWorklet quiescence timed out"));
    }
    const auto remaining =
        std::chrono::duration<double, std::milli>(deadline - now).count();
    const auto wait_ms = std::min(
        remaining,
        std::chrono::duration<double, std::milli>(
            kQuiescenceRecheckInterval).count());
    static_cast<void>(emscripten_futex_wait(
        &impl_->quiescence_signal, observed_signal, wait_ms));
  }
}

bool RealtimeAudioWorklet::ready() const noexcept {
  return impl_->worklet_state.load(std::memory_order_acquire) ==
             RealtimeAudioWorkletState::ready &&
         impl_->gate.load(std::memory_order_acquire) ==
             RealtimeAudioWorkletGate::paused &&
         !impl_->in_flight.load(std::memory_order_acquire);
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

void RealtimeAudioWorklet::latch_processor_error() noexcept {
  impl_->latch_fatal(RealtimeAudioWorkletFatal::processor_error);
}

void RealtimeAudioWorklet::latch_bootstrap_timeout() noexcept {
  impl_->latch_bootstrap_fatal(
      RealtimeAudioWorkletFatal::bootstrap_timeout);
}

std::int32_t RealtimeAudioWorklet::observed_sample_rate() const noexcept {
  return impl_->sample_rate.load(std::memory_order_acquire);
}

std::int32_t RealtimeAudioWorklet::observed_render_quantum() const noexcept {
  return impl_->render_quantum.load(std::memory_order_acquire);
}

RealtimeAudioWorkletGate RealtimeAudioWorklet::gate_state() const noexcept {
  return impl_->gate.load(std::memory_order_acquire);
}

bool RealtimeAudioWorklet::callback_in_flight() const noexcept {
  return impl_->in_flight.load(std::memory_order_acquire);
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
  return impl_->gate.load(std::memory_order_acquire) ==
         RealtimeAudioWorkletGate::terminal;
}

std::uint32_t RealtimeAudioWorklet::start_calls() const noexcept {
  return impl_->accepted_start_calls.load(std::memory_order_acquire);
}

RealtimeAudioWorkletStart
RealtimeAudioWorklet::validate_configuration_for_conformance(
    std::int32_t sample_rate, std::int32_t render_quantum) noexcept {
  if (impl_->worklet_state.load(std::memory_order_acquire) !=
      RealtimeAudioWorkletState::idle) {
    return RealtimeAudioWorkletStart::fatal;
  }
  return impl_->validate_configuration(sample_rate, render_quantum);
}

bool RealtimeAudioWorklet::latch_bootstrap_fatal_for_conformance(
    RealtimeAudioWorkletFatal fatal) noexcept {
  switch (fatal) {
    case RealtimeAudioWorkletFatal::worklet_thread_start_failed:
    case RealtimeAudioWorkletFatal::processor_create_failed:
    case RealtimeAudioWorkletFatal::node_create_failed:
    case RealtimeAudioWorkletFatal::coordinator_install_failed:
      impl_->latch_bootstrap_fatal(fatal);
      return true;
    default:
      return false;
  }
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
