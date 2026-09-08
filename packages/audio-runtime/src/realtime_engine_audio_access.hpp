#pragma once

#include <lmdj/audio/realtime_engine.hpp>

namespace lmdj::audio::detail {

// Internal adapter-only view. Call on the same audio thread immediately after
// render, or after callback quiescence. Never use this from a concurrent control
// or observer thread: Bank generation is audio-owned, not an atomic observation.
// This is not a new public telemetry API and transfers no slot/resource lifetime.
struct RealtimeEngineAudioAccess {
  struct Status {
    std::uint64_t bank_generation;
    RuntimeVoiceStateStreamState voice_state;
  };
  static Status status(const RealtimeEngine& engine) noexcept {
    return {
        engine.current_bank_generation_,
        engine.voice_state_stream_state_.load(std::memory_order_acquire),
    };
  }
};

}  // namespace lmdj::audio::detail
