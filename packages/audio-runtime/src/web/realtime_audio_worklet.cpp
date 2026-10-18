#include <lmdj/audio/web/realtime_audio_worklet.hpp>

#include <lmdj/audio/prepared_sample_bank.hpp>

#include "../realtime_engine_audio_access.hpp"

static_assert(lmdj::audio::kTickDenominator == 2'880'000);
static_assert(lmdj::audio::integrate_tick_numerator(0, 62, 192).value() ==
              11'427'840);
static_assert(lmdj::audio::whole_tick(
                  lmdj::audio::integrate_tick_numerator(0, 62, 192).value()) ==
              3);
static_assert(lmdj::audio::whole_tick(
                  lmdj::audio::integrate_tick_numerator(0, 63, 192).value()) ==
              4);
static_assert(lmdj::audio::integrate_tick_numerator(
                  2'007'360, 31, 97).value() == 4'894'080);

#if defined(__EMSCRIPTEN__)

#include <algorithm>
#include <array>
#include <atomic>
#include <climits>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include <emscripten/emscripten.h>
#include <emscripten/threading.h>
#include <emscripten/webaudio.h>

namespace lmdj::audio::web {
namespace {

constexpr std::int32_t kRequiredSampleRate = 48'000;
constexpr std::int32_t kRequiredFrames = 128;
constexpr std::size_t kWorkletStackBytes = 64U * 1024U;
constexpr auto kQuiescenceRecheckInterval = std::chrono::milliseconds{10};
// A paused-admitted callback only zeroes its outputs, so its borrow lasts
// microseconds and a release gap follows within one render quantum. This bound
// is reached only when the AudioWorklet thread itself has stalled (#2345).
constexpr auto kBeginRenderingGapBound = std::chrono::milliseconds{200};
constexpr auto kBeginRenderingGapRecheck = std::chrono::milliseconds{1};
constexpr std::uint32_t kCallbackGateMask = 3U;
constexpr std::uint32_t kCallbackBorrow = 4U;
constexpr std::uint32_t kCallbackSaturated = 0x8000'0000U;
constexpr std::uint32_t kCallbackBorrowMask =
    ~(kCallbackGateMask | kCallbackSaturated);

static_assert(std::atomic<std::uint32_t>::is_always_lock_free);
static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
static_assert(std::atomic<bool>::is_always_lock_free);
static_assert(std::atomic<RealtimeAudioWorkletGate>::is_always_lock_free);
static_assert(std::atomic<RealtimeAudioWorkletState>::is_always_lock_free);
static_assert(std::atomic<RealtimeAudioWorkletFatal>::is_always_lock_free);

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
constexpr std::uint32_t kPhysicalFenceCueStage = 1U;
constexpr std::uint32_t kPhysicalFenceEpilogueStage = 2U;
// Holds one paused-admitted callback, borrow included, before it zeroes its
// outputs. It proves activation waits for that borrow instead of refusing.
constexpr std::uint32_t kPhysicalFencePausedStage = 4U;
constexpr std::uint32_t kPhysicalFenceStages = kPhysicalFenceCueStage |
    kPhysicalFenceEpilogueStage | kPhysicalFencePausedStage;
constexpr std::uint32_t kPhysicalFenceExpired = 0x8000'0000U;
constexpr std::uint32_t kPhysicalFenceWaitSlices = 1'000U;
constexpr double kPhysicalFenceWaitMilliseconds = 10.0;
std::atomic<RealtimeEngine*> conformance_engine{nullptr};
std::atomic<std::int32_t> conformance_voice_overflow_process_return{-1};
static_assert(std::atomic<RealtimeEngine*>::is_always_lock_free);
#endif

foundation::Error worklet_error(const char* message) noexcept {
  return foundation::Error{
      foundation::ErrorCode::internal_error,
      message,
  };
}

}  // namespace

struct RealtimeAudioWorklet::Impl {
  Impl(RealtimeEngine& owned_engine, RealtimeAudioWorkletHooks owned_hooks)
      : engine(owned_engine), hooks(owned_hooks) {
    // Bootstrap owns the bounded kernels; audio only indexes immutable PCM.
    constexpr auto decay = -7.600902459542082;  // log(0.0001 / 0.2)
    constexpr auto two_pi = 6.28318530717958647692;
    for (std::size_t frame = 0; frame < kCountInCueEnvelopeFrames; ++frame) {
      const auto time = static_cast<double>(frame) / kRequiredSampleRate;
      const auto gain = 0.2 * std::exp(
          decay * static_cast<double>(frame) / kCountInCueEnvelopeFrames);
      cue_normal[frame] = static_cast<float>(
          std::sin(two_pi * 1'200.0 * time) * gain);
      cue_accent[frame] = static_cast<float>(
          std::sin(two_pi * 1'800.0 * time) * gain);
    }
  }

  static RealtimeAudioWorkletGate callback_gate(
      std::uint32_t state) noexcept {
    return static_cast<RealtimeAudioWorkletGate>(state & kCallbackGateMask);
  }

  static std::uint32_t callback_borrows(std::uint32_t state) noexcept {
    return (state & kCallbackBorrowMask) / kCallbackBorrow;
  }

  void seal_terminal() noexcept {
    // terminal == 3: one RMW closes admission without losing any borrow or
    // saturation bit. No audio-side retry is needed, including fatal paths.
    callback_state.fetch_or(kCallbackGateMask, std::memory_order_acq_rel);
  }

  bool callback_resources_quiescent() const noexcept {
    const auto state = callback_state.load(std::memory_order_acquire);
    return state == static_cast<std::uint32_t>(RealtimeAudioWorkletGate::paused) ||
           state == static_cast<std::uint32_t>(RealtimeAudioWorkletGate::terminal);
  }

  bool release_callback_body_last_use(bool keep_alive) noexcept {
    const auto state = callback_state.load(std::memory_order_acquire);
    if (callback_gate(state) != RealtimeAudioWorkletGate::open) {
      // A wake is only a hint. The waiter must observe the final release;
      // a wake before it can defer observation to the existing 10 ms recheck.
      signal_quiescence_waiters();
    }
    keep_alive = keep_alive &&
                 callback_gate(state) != RealtimeAudioWorkletGate::terminal;
    callback_state.fetch_sub(kCallbackBorrow, std::memory_order_release);
    // The release above is this admitted body's LAST Impl access. Only the
    // already-computed local return value may be used from here onward.
    return keep_alive;
  }

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  bool wait_physical_fence_barrier(
      std::uint32_t stage, std::uint32_t claimed_stages) noexcept {
    if ((claimed_stages & stage) == 0) {
      return true;
    }
    physical_fence_entered.fetch_or(stage, std::memory_order_release);
    // Finite conformance-only hold: at most 1000 waits of 10 ms per stage.
    // Caller quiescence budgets and the production callback are unchanged.
    for (std::uint32_t slice = 0; slice < kPhysicalFenceWaitSlices; ++slice) {
      const auto released = physical_fence_released.load(
          std::memory_order_acquire);
      if ((released & stage) != 0) {
        return true;
      }
      static_cast<void>(emscripten_futex_wait(
          &physical_fence_released, released,
          kPhysicalFenceWaitMilliseconds));
    }
    if ((physical_fence_released.load(std::memory_order_acquire) & stage) != 0) {
      return true;
    }
    // Harness expiry INVALIDATES the whole witness. It is not a consumer
    // release, owner ACK, or timeout-based physical receipt. Finish the real
    // cue/body retirement, but never fabricate a processor/Host fatal code.
    physical_fence_entered.fetch_or(
        kPhysicalFenceExpired, std::memory_order_release);
    seal_terminal();
    worklet_state.store(
        RealtimeAudioWorkletState::fatal, std::memory_order_release);
    signal_quiescence_waiters();
    return false;
  }
#endif

  bool render_cue_batch(
      const CountInCueBatch& batch, AudioSampleFrame& output) noexcept {
    if (batch.span_count > batch.spans.size() ||
        batch.end_frame < batch.begin_frame ||
        batch.end_frame - batch.begin_frame > kRequiredFrames) {
      return false;
    }
    auto* left = output.data;
    auto* right = left + kRequiredFrames;
    for (std::size_t index = 0; index < batch.span_count; ++index) {
      const auto& span = batch.spans[index];
      if (span.begin_frame < batch.begin_frame ||
          span.end_frame > batch.end_frame ||
          span.end_frame < span.begin_frame ||
          span.marker_frame > span.begin_frame ||
          span.end_frame - span.marker_frame > kCountInCueEnvelopeFrames) {
        return false;
      }
      const auto& kernel = span.accent ? cue_accent : cue_normal;
      for (auto frame = span.begin_frame; frame < span.end_frame; ++frame) {
        const auto sample = kernel[frame - span.marker_frame];
        const auto offset = frame - batch.begin_frame;
        left[offset] += sample;
        right[offset] += sample;
      }
    }
    return true;
  }

  static void zero_outputs(
      int num_outputs, AudioSampleFrame* outputs) noexcept {
    for (int output = 0; output < num_outputs; ++output) {
      std::fill_n(outputs[output].data,
                  outputs[output].numberOfChannels *
                      outputs[output].samplesPerChannel,
                  0.0F);
    }
  }

  static bool mute_retryable_callback(
      int num_inputs, int num_outputs, AudioSampleFrame* outputs,
      int num_params) noexcept {
    // Failed gate-only admission owns no Impl/Engine borrow. Validate only
    // callback arguments, without reading the adapter's output profile.
    if (num_inputs != 0 || (num_outputs != 1 && num_outputs != 2) ||
        outputs == nullptr || num_params != 0) {
      return false;
    }
    for (int output = 0; output < num_outputs; ++output) {
      if (outputs[output].numberOfChannels != 2 ||
          outputs[output].samplesPerChannel != kRequiredFrames ||
          outputs[output].data == nullptr) {
        return false;
      }
    }
    zero_outputs(num_outputs, outputs);
    return true;
  }

  static bool process(
      int num_inputs,
      const AudioSampleFrame* inputs,
      int num_outputs,
      AudioSampleFrame* outputs,
      int num_params,
      const AudioParamFrame* params,
      void* user_data) noexcept {
    auto& self = *static_cast<Impl*>(user_data);
    auto admission = self.callback_state.load(std::memory_order_acquire);
    if (callback_gate(admission) == RealtimeAudioWorkletGate::terminal) {
      return false;
    }
    if ((admission & kCallbackBorrowMask) == kCallbackBorrowMask) {
      // Never wrap the count into a false zero proof. Saturation permanently
      // disables physical proof even after every existing borrow is released.
      self.callback_state.fetch_or(
          kCallbackSaturated | kCallbackGateMask, std::memory_order_acq_rel);
      self.latch_fatal(RealtimeAudioWorkletFatal::callback_reentry);
      return false;
    }
    const auto admission_gate = callback_gate(admission);
    const auto previous_borrows = callback_borrows(admission);
    if (!self.callback_state.compare_exchange_strong(
            admission, admission + kCallbackBorrow,
            std::memory_order_acq_rel, std::memory_order_acquire)) {
      if (callback_gate(admission) == RealtimeAudioWorkletGate::terminal) {
        return false;
      }
      if (previous_borrows != 0 ||
          callback_borrows(admission) != previous_borrows) {
        // Unadmitted overlap may publish only retained adapter metadata.
        // This is not a body borrow or an Impl destruction receipt; Root
        // retains the callback context through real backend retirement.
        self.latch_fatal(RealtimeAudioWorkletFatal::callback_reentry);
        return false;
      }
      return mute_retryable_callback(
          num_inputs, num_outputs, outputs, num_params);
    }
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
    std::uint32_t physical_fence_stages = 0;
#endif
    const auto finish = [&](bool keep_alive) noexcept {
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
      if (!self.wait_physical_fence_barrier(
              kPhysicalFenceEpilogueStage, physical_fence_stages)) {
        keep_alive = false;
      }
#endif
      return self.release_callback_body_last_use(keep_alive);
    };
    if (self.fatal_code.load(std::memory_order_acquire) !=
        RealtimeAudioWorkletFatal::none) {
      return finish(false);
    }

    const auto expected_outputs =
        self.count_in_output.load(std::memory_order_acquire) ? 2 : 1;
    bool valid = num_inputs == 0 && num_outputs == expected_outputs &&
                 outputs != nullptr && num_params == 0;
    if (valid) {
      for (int output = 0; output < num_outputs; ++output) {
        valid = valid && outputs[output].numberOfChannels == 2 &&
                outputs[output].samplesPerChannel == kRequiredFrames &&
                outputs[output].data != nullptr;
      }
    }
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
      return finish(false);
    }

    const auto heartbeat_before_callback =
        self.callback_heartbeat.fetch_add(1, std::memory_order_release);

    const auto admitted_state =
        self.callback_state.load(std::memory_order_acquire);
    const auto gate = callback_gate(admitted_state);
    if (gate == RealtimeAudioWorkletGate::terminal) {
      return finish(false);
    }
    if (previous_borrows != 0 || callback_borrows(admitted_state) > 1) {
      self.latch_fatal(RealtimeAudioWorkletFatal::callback_reentry);
      return finish(false);
    }
    if (admission_gate == RealtimeAudioWorkletGate::paused ||
        gate == RealtimeAudioWorkletGate::paused) {
      // A paused admission NEVER accesses Engine, even if control eventually
      // opens admission. Future paused Engine work needs a new exclusion proof.
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
      auto paused_only = kPhysicalFencePausedStage;
      if (self.physical_fence_armed.compare_exchange_strong(
              paused_only, 0, std::memory_order_acq_rel,
              std::memory_order_acquire)) {
        physical_fence_stages = kPhysicalFencePausedStage;
      }
      if (!self.wait_physical_fence_barrier(
              kPhysicalFencePausedStage, physical_fence_stages)) {
        zero_outputs(num_outputs, outputs);
        return finish(false);
      }
#endif
      zero_outputs(num_outputs, outputs);
      return finish(true);
    }

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
    // An epilogue-only witness may use a render without a cue. A combined
    // witness claims BOTH bits only at the same actual successful cue take.
    auto epilogue_only = kPhysicalFenceEpilogueStage;
    if (self.physical_fence_armed.compare_exchange_strong(
            epilogue_only, 0, std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      physical_fence_stages = kPhysicalFenceEpilogueStage;
    }
#endif
    auto* left = outputs[0].data;
    auto* right = outputs[0].data + outputs[0].samplesPerChannel;
    if (expected_outputs == 2) {
      std::fill_n(outputs[1].data, 2 * kRequiredFrames, 0.0F);
    }
    self.engine.render(left, right, kRequiredFrames);
    CountInCueBatch cue_batch{};
    if (self.engine.take_count_in_cue_batch_audio(cue_batch)) {
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
      if (physical_fence_stages == 0) {
        physical_fence_stages = self.physical_fence_armed.exchange(
            0, std::memory_order_acq_rel);
      }
      if (physical_fence_stages != 0) {
        self.physical_fence_cue_batch.store(
            cue_batch.batch_id, std::memory_order_release);
      }
      const auto cue_barrier_released = self.wait_physical_fence_barrier(
          kPhysicalFenceCueStage, physical_fence_stages);
#endif
      const auto consumed = cue_batch.span_count == 0 ||
          (expected_outputs == 2 &&
           self.render_cue_batch(cue_batch, outputs[1]));
      if (!consumed) {
        // A terminal adapter explicitly discards this copied output span.
        // Retire its consumer fence before the callback can become quiescent.
        zero_outputs(num_outputs, outputs);
      }
      const auto retired = self.engine.acknowledge_count_in_cue_batch_audio(
          cue_batch.batch_id);
      if (!consumed || !retired) {
        self.latch_fatal(RealtimeAudioWorkletFatal::processor_error);
        return finish(false);
      }
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
      if (!cue_barrier_released) {
        return finish(false);
      }
#endif
    }
    const auto render_status =
        lmdj::audio::detail::RealtimeEngineAudioAccess::status(self.engine);
    if (render_status.voice_state ==
        RuntimeVoiceStateStreamState::corrupted) {
      self.latch_fatal(RealtimeAudioWorkletFatal::processor_error);
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
      conformance_voice_overflow_process_return.store(
          0, std::memory_order_release);
#endif
      return finish(false);
    }
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
    if (previous < scaled) {
      // Only one non-reentrant render body writes this diagnostic. A racing
      // conformance reset may win; never retry on the audio thread.
      self.energy_microunits.compare_exchange_strong(
          previous, scaled, std::memory_order_relaxed,
          std::memory_order_relaxed);
    }
#endif
    auto acknowledged_generation = self.activation_generation.exchange(
        0, std::memory_order_acq_rel);
    if (acknowledged_generation != 0) {
      // Only the actual first open-gate render owns frame zero. Publish its
      // original heartbeat before the positive ACK; neither control/main
      // scheduling nor later callbacks can shift this activation's epoch.
      self.engine_epoch_heartbeat.store(
          heartbeat_before_callback, std::memory_order_release);
    } else {
      acknowledged_generation = render_status.bank_generation;
    }
    self.acknowledged.store(
        acknowledged_generation, std::memory_order_release);
    auto requested = self.callback_state.load(std::memory_order_acquire);
    if (callback_gate(requested) ==
        RealtimeAudioWorkletGate::final_quantum_requested) {
      // Single attempt; terminal sealing or another borrow can win. Keep the
      // request pending instead of retrying or losing the concurrent borrow.
      self.callback_state.compare_exchange_strong(
          requested, requested & ~kCallbackGateMask,
          std::memory_order_acq_rel, std::memory_order_acquire);
    }
    return finish(true);
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
    const auto output_count =
        self.count_in_output.load(std::memory_order_acquire) ? 2 : 1;
    int output_channel_counts[2] = {2, 2};
    EmscriptenAudioWorkletNodeCreateOptions options = {
        .numberOfInputs = 0,
        .numberOfOutputs = output_count,
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
    emscripten_audio_node_connect(
        node, self.output_destination_handle, 0, 0);
    if (output_count == 2) {
      emscripten_audio_node_connect(
          node, self.cue_destination_handle, 1, 0);
    }
    self.direct_output_destination_handle =
        self.output_destination_handle == self.audio_context_handle
            ? self.audio_context_handle
            : 0;
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
    seal_terminal();
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
  // Sole admission/body-last-use authority. Low bits preserve the public gate
  // enum; upper bits count actual admitted bodies, with sticky saturation.
  std::atomic<std::uint32_t> callback_state{
      static_cast<std::uint32_t>(RealtimeAudioWorkletGate::paused)};
  std::atomic<std::uint32_t> quiescence_signal{0};
  std::atomic<std::uint64_t> acknowledged{0};
  std::atomic<std::uint64_t> activation_generation{0};
  std::atomic<std::uint32_t> callback_heartbeat{0};
  std::atomic<std::uint32_t> engine_epoch_heartbeat{0};
  std::atomic<std::int32_t> node{0};
  std::atomic<std::int32_t> sample_rate{0};
  std::atomic<std::int32_t> render_quantum{0};
  std::array<float, kCountInCueEnvelopeFrames> cue_normal{};
  std::array<float, kCountInCueEnvelopeFrames> cue_accent{};
  std::int32_t audio_context_handle = 0;
  std::int32_t output_destination_handle = 0;
  std::int32_t cue_destination_handle = 0;
  // Set before bootstrap publishes the node and immutable thereafter.
  std::atomic<bool> count_in_output{false};
  std::int32_t direct_output_destination_handle = 0;
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  std::atomic<std::uint32_t> physical_fence_armed{0};
  std::atomic<std::uint32_t> physical_fence_released{0};
  std::atomic<std::uint32_t> physical_fence_entered{0};
  std::atomic<std::uint64_t> physical_fence_cue_batch{0};
  // Counts begin_rendering attempts that met an in-flight callback borrow.
  std::atomic<std::uint32_t> begin_rendering_borrow_waits{0};
  std::atomic<std::uint32_t> observed_quantum{0};
  std::atomic<std::uint32_t> render_count{0};
  std::atomic<std::uint32_t> energy_microunits{0};
  std::atomic<std::uint32_t> accepted_start_calls{0};
  std::atomic<std::uint32_t> direct_output_connect_calls{0};
#endif
};

RealtimeAudioWorklet::RealtimeAudioWorklet(
    RealtimeEngine& engine, RealtimeAudioWorkletHooks hooks)
    : impl_(std::make_unique<Impl>(engine, hooks)) {
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  conformance_engine.store(&engine, std::memory_order_release);
  conformance_voice_overflow_process_return.store(
      -1, std::memory_order_release);
#endif
}

RealtimeAudioWorklet::~RealtimeAudioWorklet() {
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  auto* expected = &impl_->engine;
  static_cast<void>(conformance_engine.compare_exchange_strong(
      expected,
      nullptr,
      std::memory_order_acq_rel,
      std::memory_order_acquire));
#endif
}

RealtimeAudioWorkletStart RealtimeAudioWorklet::start_on_browser_main(
    std::int32_t audio_context_handle,
    std::int32_t output_destination_handle) noexcept {
  return start_on_browser_main_impl(
      audio_context_handle, output_destination_handle, 0);
}

RealtimeAudioWorkletStart
RealtimeAudioWorklet::start_with_count_in_on_browser_main(
    std::int32_t audio_context_handle,
    std::int32_t output_destination_handle,
    std::int32_t cue_destination_handle) noexcept {
  if (cue_destination_handle <= 0 ||
      cue_destination_handle == output_destination_handle) {
    return RealtimeAudioWorkletStart::invalid_handle;
  }
  return start_on_browser_main_impl(
      audio_context_handle, output_destination_handle, cue_destination_handle);
}

RealtimeAudioWorkletStart RealtimeAudioWorklet::start_on_browser_main_impl(
    std::int32_t audio_context_handle,
    std::int32_t output_destination_handle,
    std::int32_t cue_destination_handle) noexcept {
  if (!emscripten_is_main_browser_thread()) {
    impl_->latch_bootstrap_fatal(
        RealtimeAudioWorkletFatal::wrong_browser_thread);
    return RealtimeAudioWorkletStart::wrong_browser_thread;
  }
  if (audio_context_handle <= 0 || output_destination_handle <= 0) {
    return RealtimeAudioWorkletStart::invalid_handle;
  }
  const auto state = impl_->worklet_state.load(std::memory_order_acquire);
  if (state == RealtimeAudioWorkletState::starting ||
      state == RealtimeAudioWorkletState::node_ready) {
    return impl_->audio_context_handle == audio_context_handle &&
                   impl_->output_destination_handle == output_destination_handle &&
                   impl_->cue_destination_handle == cue_destination_handle
               ? RealtimeAudioWorkletStart::already_starting
               : RealtimeAudioWorkletStart::duplicate_handle;
  }
  if (state == RealtimeAudioWorkletState::ready) {
    return impl_->audio_context_handle == audio_context_handle &&
                   impl_->output_destination_handle == output_destination_handle &&
                   impl_->cue_destination_handle == cue_destination_handle
               ? RealtimeAudioWorkletStart::already_ready
               : RealtimeAudioWorkletStart::duplicate_handle;
  }
  if (state == RealtimeAudioWorkletState::fatal) {
    return RealtimeAudioWorkletStart::fatal;
  }
  impl_->audio_context_handle = audio_context_handle;
  impl_->output_destination_handle = output_destination_handle;
  impl_->cue_destination_handle = cue_destination_handle;
  impl_->count_in_output.store(
      cue_destination_handle != 0, std::memory_order_release);
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

bool RealtimeAudioWorklet::has_count_in_output() const noexcept {
  return impl_->count_in_output.load(std::memory_order_acquire);
}

bool RealtimeAudioWorklet::set_count_in_metronome_on_browser_main(
    bool enabled) noexcept {
  if (!emscripten_is_main_browser_thread() ||
      state() != RealtimeAudioWorkletState::ready ||
      fatal() != RealtimeAudioWorkletFatal::none || !has_count_in_output()) {
    return false;
  }
  const auto gate = gate_state();
  if (gate != RealtimeAudioWorkletGate::paused &&
      gate != RealtimeAudioWorkletGate::open) {
    return false;
  }
  // The adapter retains its Engine for its complete published lifetime, as
  // for the other browser-main entry points. This is the Engine's existing
  // atomic monitoring flag; no Project/control state or audio payload is read.
  impl_->engine.set_count_in_metronome(enabled);
  return true;
}

bool RealtimeAudioWorklet::connect_direct_output_on_browser_main(
    std::int32_t audio_context_handle,
    std::int32_t output_destination_handle) noexcept {
  if (output_destination_handle == 0) {
    output_destination_handle = audio_context_handle;
  }
  if (!emscripten_is_main_browser_thread() || audio_context_handle <= 0 ||
      output_destination_handle <= 0 ||
      impl_->audio_context_handle != audio_context_handle) {
    return false;
  }
  const auto state = impl_->worklet_state.load(std::memory_order_acquire);
  if (state != RealtimeAudioWorkletState::node_ready &&
      state != RealtimeAudioWorkletState::ready) {
    return false;
  }
  if (impl_->direct_output_destination_handle != 0) {
    return impl_->direct_output_destination_handle == output_destination_handle;
  }
  if (impl_->output_destination_handle == output_destination_handle) {
    impl_->direct_output_destination_handle = output_destination_handle;
    return true;
  }
  const auto node = impl_->node.load(std::memory_order_acquire);
  if (node <= 0) {
    return false;
  }
  emscripten_audio_node_connect(node, output_destination_handle, 0, 0);
  impl_->direct_output_destination_handle = output_destination_handle;
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  impl_->direct_output_connect_calls.fetch_add(1, std::memory_order_relaxed);
#endif
  return true;
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
  // A running context keeps admitting paused callbacks, each holding a borrow
  // while it zeroes its outputs. Such a borrow never touches Engine, so it is
  // not a refusal reason; the gate still opens only from an exact zero-borrow
  // paused state, after waiting for the release gap below (#2345).
  if (impl_->worklet_state.load(std::memory_order_acquire) !=
          RealtimeAudioWorkletState::ready ||
      impl_->fatal_code.load(std::memory_order_acquire) !=
          RealtimeAudioWorkletFatal::none ||
      Impl::callback_gate(impl_->callback_state.load(
          std::memory_order_acquire)) != RealtimeAudioWorkletGate::paused) {
    return foundation::Result<void>::failure(
        worklet_error("Wasm AudioWorklet is not ready to render"));
  }
  const auto bank = impl_->engine.bank_telemetry();
  if (bank.accepted_publications == 0 ||
      bank.current_generation != bank.accepted_publications ||
      bank.pending_publications != 0) {
    return foundation::Result<void>::failure(
        worklet_error("Wasm AudioWorklet Bank is not current"));
  }
  const auto deadline =
      std::chrono::steady_clock::now() + kBeginRenderingGapBound;
  while (true) {
    auto expected =
        static_cast<std::uint32_t>(RealtimeAudioWorkletGate::paused);
    impl_->activation_generation.store(
        bank.current_generation, std::memory_order_release);
    impl_->acknowledged.store(0, std::memory_order_release);
    if (impl_->callback_state.compare_exchange_strong(
            expected,
            static_cast<std::uint32_t>(RealtimeAudioWorkletGate::open),
            std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      return foundation::Result<void>::success();
    }
    impl_->activation_generation.store(0, std::memory_order_release);
    if (Impl::callback_gate(expected) != RealtimeAudioWorkletGate::paused ||
        impl_->fatal_code.load(std::memory_order_acquire) !=
            RealtimeAudioWorkletFatal::none) {
      return foundation::Result<void>::failure(
          worklet_error("Wasm AudioWorklet gate is not paused"));
    }
#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
    impl_->begin_rendering_borrow_waits.fetch_add(
        1, std::memory_order_acq_rel);
#endif
    const auto now = std::chrono::steady_clock::now();
    if (now >= deadline) {
      return foundation::Result<void>::failure(worklet_error(
          "Wasm AudioWorklet paused callback did not release its borrow"));
    }
    // A paused-gate release signals quiescence waiters before it drops its
    // borrow, so a short recheck bounds a wake that lands before the release.
    const auto observed_signal =
        impl_->quiescence_signal.load(std::memory_order_acquire);
    if (impl_->callback_state.load(std::memory_order_acquire) ==
        static_cast<std::uint32_t>(RealtimeAudioWorkletGate::paused)) {
      continue;
    }
    const auto wait_ms = std::min(
        std::chrono::duration<double, std::milli>(deadline - now).count(),
        std::chrono::duration<double, std::milli>(
            kBeginRenderingGapRecheck).count());
    static_cast<void>(emscripten_futex_wait(
        &impl_->quiescence_signal, observed_signal, wait_ms));
  }
}

foundation::Result<void> RealtimeAudioWorklet::await_quiescent(
    std::uint32_t timeout_ms) noexcept {
  auto callback_state = impl_->callback_state.load(std::memory_order_acquire);
  if (callback_state ==
      static_cast<std::uint32_t>(RealtimeAudioWorkletGate::paused)) {
    return foundation::Result<void>::success();
  }
  const auto deadline = std::chrono::steady_clock::now() +
                        std::chrono::milliseconds(timeout_ms);
  while (true) {
    // One attempt per existing bounded control recheck, preserving borrows.
    // A callback's admission/release may win; retry only inside this budget.
    auto expected = impl_->callback_state.load(std::memory_order_acquire);
    if (Impl::callback_gate(expected) == RealtimeAudioWorkletGate::open) {
      impl_->callback_state.compare_exchange_strong(
          expected,
          (expected & ~kCallbackGateMask) |
              static_cast<std::uint32_t>(
                  RealtimeAudioWorkletGate::final_quantum_requested),
          std::memory_order_acq_rel, std::memory_order_acquire);
    }
    const auto observed_signal =
        impl_->quiescence_signal.load(std::memory_order_acquire);
    callback_state = impl_->callback_state.load(std::memory_order_acquire);
    if (callback_state ==
        static_cast<std::uint32_t>(RealtimeAudioWorkletGate::paused)) {
      return foundation::Result<void>::success();
    }
    if (Impl::callback_gate(callback_state) ==
            RealtimeAudioWorkletGate::terminal &&
        Impl::callback_borrows(callback_state) == 0) {
      return foundation::Result<void>::failure(
          worklet_error("Wasm AudioWorklet is terminal"));
    }
    const auto now = std::chrono::steady_clock::now();
    if (now >= deadline) {
      impl_->latch_fatal(RealtimeAudioWorkletFatal::quiescence_timeout);
      const auto terminal_deadline =
          now + std::chrono::milliseconds(timeout_ms);
      while (callback_in_flight()) {
        const auto terminal_signal =
            impl_->quiescence_signal.load(std::memory_order_acquire);
        if (!callback_in_flight()) {
          break;
        }
        const auto terminal_now = std::chrono::steady_clock::now();
        if (terminal_now >= terminal_deadline) {
          return foundation::Result<void>::failure(worklet_error(
              "Wasm AudioWorklet quiescence timed out with callback still in "
              "flight"));
        }
        const auto terminal_remaining =
            std::chrono::duration<double, std::milli>(
                terminal_deadline - terminal_now)
                .count();
        const auto terminal_wait_ms = std::min(
            terminal_remaining,
            std::chrono::duration<double, std::milli>(
                kQuiescenceRecheckInterval)
                .count());
        static_cast<void>(emscripten_futex_wait(
            &impl_->quiescence_signal,
            terminal_signal,
            terminal_wait_ms));
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

void RealtimeAudioWorklet::request_terminal_drain() noexcept {
  // Host/Bridge may own the original failure. Do not synthesize processor_error
  // (or any other fatal code) merely to close the real resource admission gate.
  impl_->seal_terminal();
  impl_->worklet_state.store(
      RealtimeAudioWorkletState::fatal, std::memory_order_release);
  impl_->signal_quiescence_waiters();
}

bool RealtimeAudioWorklet::physically_quiescent() const noexcept {
  return impl_->callback_resources_quiescent();
}

bool RealtimeAudioWorklet::ready() const noexcept {
  // Readiness is the paused gate, not a zero borrow count: a running context
  // keeps admitting paused callbacks that never touch Engine. begin_rendering
  // opens the gate only from the exact zero-borrow paused state (#2345).
  return impl_->worklet_state.load(std::memory_order_acquire) ==
             RealtimeAudioWorkletState::ready &&
         Impl::callback_gate(impl_->callback_state.load(
             std::memory_order_acquire)) == RealtimeAudioWorkletGate::paused;
}

std::uint64_t RealtimeAudioWorklet::acknowledged_generation() const noexcept {
  return impl_->acknowledged.load(std::memory_order_acquire);
}

std::uint32_t RealtimeAudioWorklet::callback_heartbeat() const noexcept {
  return impl_->callback_heartbeat.load(std::memory_order_acquire);
}

std::uint32_t RealtimeAudioWorklet::engine_epoch_heartbeat() const noexcept {
  return impl_->engine_epoch_heartbeat.load(std::memory_order_acquire);
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
  return Impl::callback_gate(
      impl_->callback_state.load(std::memory_order_acquire));
}

bool RealtimeAudioWorklet::callback_in_flight() const noexcept {
  return Impl::callback_borrows(
             impl_->callback_state.load(std::memory_order_acquire)) != 0;
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

void RealtimeAudioWorklet::reset_output_energy_for_conformance() noexcept {
  impl_->energy_microunits.store(0, std::memory_order_release);
}

std::uint32_t
RealtimeAudioWorklet::direct_output_connections_for_conformance()
    const noexcept {
  return impl_->direct_output_connect_calls.load(std::memory_order_acquire);
}

bool RealtimeAudioWorklet::callback_gate_closed() const noexcept {
  return gate_state() == RealtimeAudioWorkletGate::terminal;
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
  std::array<float, 512> cue{};
  AudioSampleFrame outputs[2] = {
      {.numberOfChannels = 2, .samplesPerChannel = frames,
       .data = output.data()},
      {.numberOfChannels = 2, .samplesPerChannel = frames,
       .data = cue.data()},
  };
  const auto output_count = has_count_in_output() ? 2 : 1;
  return Impl::process(
      0, nullptr, output_count, outputs, 0, nullptr, impl_.get());
}

bool RealtimeAudioWorklet::generation_matches_for_conformance(
    std::uint64_t expected_generation) const noexcept {
  return acknowledged_generation() == expected_generation;
}

bool RealtimeAudioWorklet::mark_callback_in_flight_for_conformance() noexcept {
  // Legacy artificial timeout probe only: never use it as actual last-use
  // acceptance. The new barriers hold a real admitted callback/cue borrow.
  auto expected = impl_->callback_state.load(std::memory_order_acquire);
  if (Impl::callback_gate(expected) == RealtimeAudioWorkletGate::terminal ||
      Impl::callback_borrows(expected) != 0) {
    return false;
  }
  return impl_->callback_state.compare_exchange_strong(
      expected, expected + kCallbackBorrow,
      std::memory_order_acq_rel, std::memory_order_acquire);
}

void RealtimeAudioWorklet::arm_physical_fence_barrier_for_conformance(
    std::uint32_t stages) noexcept {
  // Serialized harness control arms only before a callback and never re-arms
  // an outstanding witness; the actual callback claims all requested stages.
  impl_->physical_fence_entered.store(0, std::memory_order_relaxed);
  impl_->physical_fence_released.store(0, std::memory_order_relaxed);
  impl_->physical_fence_cue_batch.store(0, std::memory_order_relaxed);
  impl_->physical_fence_armed.store(
      stages & kPhysicalFenceStages, std::memory_order_release);
}

void RealtimeAudioWorklet::release_physical_fence_barrier_for_conformance(
    std::uint32_t stages) noexcept {
  impl_->physical_fence_released.fetch_or(
      stages & kPhysicalFenceStages, std::memory_order_release);
  static_cast<void>(emscripten_futex_wake(
      &impl_->physical_fence_released, INT_MAX));
}

std::uint32_t
RealtimeAudioWorklet::physical_fence_barrier_stage_for_conformance()
    const noexcept {
  return impl_->physical_fence_entered.load(std::memory_order_acquire);
}

std::uint64_t
RealtimeAudioWorklet::physical_fence_cue_batch_for_conformance() const noexcept {
  return impl_->physical_fence_cue_batch.load(std::memory_order_acquire);
}

std::uint64_t
RealtimeAudioWorklet::physical_fence_pending_cue_batch_for_conformance() const noexcept {
  return lmdj::audio::detail::RealtimeEngineAudioAccess::pending_cue_batch_for_conformance(
      impl_->engine);
}

std::uint32_t
RealtimeAudioWorklet::begin_rendering_borrow_waits_for_conformance()
    const noexcept {
  return impl_->begin_rendering_borrow_waits.load(std::memory_order_acquire);
}

std::uint32_t
RealtimeAudioWorklet::physical_fence_borrow_count_for_conformance()
    const noexcept {
  return Impl::callback_borrows(
      impl_->callback_state.load(std::memory_order_acquire));
}

extern "C" {

EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_web_audio_test_voice_state_capacity() {
  return static_cast<std::uint32_t>(kRealtimeVoiceStateCapacity);
}

EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_web_audio_test_voice_state_active_voices() {
  auto* engine = conformance_engine.load(std::memory_order_acquire);
  return engine == nullptr
             ? 0
             : static_cast<std::uint32_t>(
                   engine->telemetry().active_voices);
}

EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_web_audio_test_voice_state_published() {
  auto* engine = conformance_engine.load(std::memory_order_acquire);
  return engine == nullptr
             ? 0
             : static_cast<std::uint32_t>(
                   engine->voice_state_telemetry().published_voice_states);
}

EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_web_audio_test_voice_state_state() {
  auto* engine = conformance_engine.load(std::memory_order_acquire);
  return engine == nullptr
             ? UINT32_MAX
             : static_cast<std::uint32_t>(
                   engine->voice_state_telemetry().state);
}

EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_web_audio_test_voice_state_drops() {
  auto* engine = conformance_engine.load(std::memory_order_acquire);
  return engine == nullptr
             ? UINT32_MAX
             : static_cast<std::uint32_t>(
                   engine->voice_state_telemetry().voice_state_drops);
}

EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_web_audio_test_voice_state_outcome_drops() {
  auto* engine = conformance_engine.load(std::memory_order_acquire);
  return engine == nullptr
             ? UINT32_MAX
             : static_cast<std::uint32_t>(
                   engine->trigger_outcome_telemetry()
                       .runtime_outcome_drops);
}

EMSCRIPTEN_KEEPALIVE std::int32_t
lmdj_web_audio_test_voice_state_process_return() {
  return conformance_voice_overflow_process_return.load(
      std::memory_order_acquire);
}

EMSCRIPTEN_KEEPALIVE int
lmdj_web_audio_test_enqueue_voice_state_batch(
    std::uint32_t batch,
    std::uint32_t voice_count) {
  auto* engine = conformance_engine.load(std::memory_order_acquire);
  if (engine == nullptr || voice_count == 0 ||
      voice_count > kRealtimeVoiceCapacity ||
      engine->telemetry().state != RealtimeState::running ||
      engine->telemetry().queued_events != 0 ||
      engine->voice_state_telemetry().state !=
          RuntimeVoiceStateStreamState::healthy) {
    return -1;
  }

  std::array<RuntimeTriggerOutcomeEvent, kRealtimeVoiceCapacity> outcomes{};
  for (std::size_t attempt = 0;
       attempt <=
           kRealtimeTriggerOutcomeCapacity / kRealtimeVoiceCapacity;
       ++attempt) {
    if (engine->drain_trigger_outcomes(outcomes) < outcomes.size()) {
      break;
    }
  }
  if (engine->trigger_outcome_telemetry().runtime_outcome_drops != 0) {
    return -2;
  }

  const auto sequence_base =
      std::uint64_t{1'000'000} +
      static_cast<std::uint64_t>(batch) * kRealtimeVoiceCapacity;
  int accepted = 0;
  const auto enqueue = [&](PadControlEvent event) noexcept {
    if (engine->enqueue_control(event) != EnqueueResult::accepted) {
      return false;
    }
    ++accepted;
    return true;
  };
  if (!enqueue(PadControlEvent{
          sequence_base,
          0,
          0,
          PadControlKind::preview_set,
          cooker::ResolvedPlayback{
              0,
              1,
              domain::TriggerMode::gate,
              1.0F,
              false,
          },
      })) {
    return -3;
  }
  for (std::uint32_t index = 0; index < voice_count; ++index) {
    if (!enqueue(PadControlEvent{
            sequence_base + index + 1,
            0,
            127,
            PadControlKind::press,
            {},
        })) {
      return -4;
    }
  }
  if (!enqueue(PadControlEvent{
          sequence_base + voice_count + 1,
          0,
          0,
          PadControlKind::stop_all,
          {},
      })) {
    return -5;
  }
  return accepted;
}

}  // extern "C"
#endif

}  // namespace lmdj::audio::web

#endif
