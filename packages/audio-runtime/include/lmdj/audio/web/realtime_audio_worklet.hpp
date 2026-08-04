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

  int start_on_browser_main(std::int32_t audio_context_handle) noexcept;
  void complete_control_install(bool installed) noexcept;
  foundation::Result<void> await_quiescent(
      std::uint32_t timeout_ms) noexcept;

  bool ready() const noexcept;
  std::uint64_t acknowledged_generation() const noexcept;
  RealtimeAudioWorkletState state() const noexcept;
  RealtimeAudioWorkletFatal fatal() const noexcept;
  std::int32_t node_handle() const noexcept;
  void latch_processor_error() noexcept;

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
  std::uint32_t observed_frames() const noexcept;
  std::uint32_t render_calls() const noexcept;
  std::uint32_t output_energy_microunits() const noexcept;
  bool callback_gate_closed() const noexcept;
  bool callback_in_flight() const noexcept;
  bool invoke_invalid_shape_for_conformance(std::int32_t frames) noexcept;
  bool generation_matches_for_conformance(
      std::uint64_t expected_generation) const noexcept;
#endif

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::audio::web

#endif
