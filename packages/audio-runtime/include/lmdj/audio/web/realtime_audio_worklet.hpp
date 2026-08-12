#pragma once

#if defined(__EMSCRIPTEN__)

#include <atomic>
#include <cstdint>
#include <memory>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::audio::web {

enum class RealtimeAudioWorkletState : std::int32_t {
  idle = 0,
  starting = 1,
  node_ready = 2,
  ready = 3,
  fatal = -1,
};

enum class RealtimeAudioWorkletFatal : std::int32_t {
  none = 0,
  wrong_browser_thread = 1,
  invalid_audio_context = 2,
  unsupported_sample_rate = 3,
  unsupported_render_quantum = 4,
  worklet_thread_start_failed = 5,
  processor_create_failed = 6,
  node_create_failed = 7,
  invalid_callback_shape = 8,
  callback_reentry = 9,
  coordinator_install_failed = 10,
  processor_error = 11,
  quiescence_timeout = 12,
  bootstrap_timeout = 13,
};

enum class RealtimeAudioWorkletGate : std::int32_t {
  paused = 0,
  open = 1,
  final_quantum_requested = 2,
  terminal = 3,
};

enum class RealtimeAudioWorkletStart : std::int32_t {
  unpublished = 0,
  accepted = 1,
  already_starting = 2,
  already_ready = 3,
  wrong_browser_thread = -1,
  invalid_handle = -2,
  duplicate_handle = -3,
  unsupported_sample_rate = -4,
  unsupported_render_quantum = -5,
  fatal = -6,
};

struct RealtimeAudioWorkletHooks {
  void* context;
  bool (*schedule_control_install)(void* context) noexcept;
};

class RealtimeAudioWorklet final {
 public:
  RealtimeAudioWorklet(
      RealtimeEngine& engine, RealtimeAudioWorkletHooks hooks);
  ~RealtimeAudioWorklet();

  RealtimeAudioWorklet(const RealtimeAudioWorklet&) = delete;
  RealtimeAudioWorklet& operator=(const RealtimeAudioWorklet&) = delete;

  RealtimeAudioWorkletStart start_on_browser_main(
      std::int32_t audio_context_handle) noexcept;
  void complete_control_install(bool installed) noexcept;
  foundation::Result<void> begin_rendering() noexcept;
  foundation::Result<void> await_quiescent(
      std::uint32_t timeout_ms) noexcept;

  bool ready() const noexcept;
  std::uint64_t acknowledged_generation() const noexcept;
  RealtimeAudioWorkletState state() const noexcept;
  RealtimeAudioWorkletFatal fatal() const noexcept;
  void latch_processor_error() noexcept;
  void latch_bootstrap_timeout() noexcept;
  std::int32_t observed_sample_rate() const noexcept;
  std::int32_t observed_render_quantum() const noexcept;
  RealtimeAudioWorkletGate gate_state() const noexcept;
  bool callback_in_flight() const noexcept;

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  std::uint32_t observed_frames() const noexcept;
  std::uint32_t render_calls() const noexcept;
  std::uint32_t output_energy_microunits() const noexcept;
  bool callback_gate_closed() const noexcept;
  std::uint32_t start_calls() const noexcept;
  RealtimeAudioWorkletStart validate_configuration_for_conformance(
      std::int32_t sample_rate, std::int32_t render_quantum) noexcept;
  bool latch_bootstrap_fatal_for_conformance(
      RealtimeAudioWorkletFatal fatal) noexcept;
  bool invoke_invalid_shape_for_conformance(std::int32_t frames) noexcept;
  bool generation_matches_for_conformance(
      std::uint64_t expected_generation) const noexcept;
  bool mark_callback_in_flight_for_conformance() noexcept;
#endif

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::audio::web

#endif
