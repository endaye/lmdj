#pragma once

#include <cstddef>
#include <cstdint>
#include <type_traits>

#include <lmdj/cooker/runtime_snapshot.hpp>

// The shared per-voice DSP kernel (decision 2026-09-30, lmdj.project.v5 5.1.0).
// The realtime engine and the offline renderer run every non-neutral voice
// through these functions, so live playback and an export of the same voice
// execute the same code. A neutral voice never enters the kernel: it keeps the
// renderer's original path, which is why default output is unchanged.
//
// Everything here is noexcept, allocation-free and lock-free. Positions are
// Q32.32 frames and the per-frame functions use no double; prepare_voice_dsp
// derives the pitch step in double once per trigger, on the audio thread.
namespace lmdj::audio::detail {

inline constexpr std::uint32_t kVoiceDspRampFrames = 96;

struct VoiceDspState {
  // Logical read position from the voice's start frame, and its per-output-
  // frame step (1 << 32 is the source rate).
  std::uint64_t position;
  std::uint64_t step;
  // 96 output frames expressed in logical Q32.32 frames, for the end fade.
  std::uint64_t fade_span;
  std::uint32_t start;
  std::uint32_t length;
  // Logical frame where later loop passes begin.
  std::uint32_t loop_begin;
  // Frames of a forward loop's tail blended with the loop's head.
  std::uint32_t crossfade;
  float pan_left;
  float pan_right;
  float inverse_fade_span;
  bool reverse;
  bool looping;
  bool ping_pong;
  bool backwards;
};

static_assert(std::is_trivially_copyable_v<VoiceDspState>);

// Builds the kernel state for one trigger. Returns false when the block does
// not fit the playback or the material; the caller then refuses the event.
bool prepare_voice_dsp(
    const cooker::ResolvedPlayback& playback,
    std::size_t material_frames,
    VoiceDspState& state) noexcept;

// True when a playback's DSP block fits its playback and material. A neutral
// block always fits: it never enters the kernel.
inline bool voice_dsp_fits(
    const cooker::ResolvedPlayback& playback,
    std::size_t material_frames) noexcept {
  if (cooker::is_neutral(playback.dsp)) {
    return true;
  }
  VoiceDspState state{};
  return prepare_voice_dsp(playback, material_frames, state);
}

// Equal-power crossfade gain for t in [0, 1]: sin(t * pi / 2).
float quarter_sine(float t) noexcept;

inline std::uint32_t voice_dsp_physical_frame(
    const VoiceDspState& state,
    std::uint32_t logical) noexcept {
  return state.reverse ? state.start + (state.length - 1 - logical)
                       : state.start + logical;
}

// The physical source frame under the read head, for Host publication: a
// reversed voice's playhead therefore moves backwards.
inline std::uint32_t voice_dsp_source_frame(const VoiceDspState& state) noexcept {
  return voice_dsp_physical_frame(
      state, static_cast<std::uint32_t>(state.position >> 32));
}

template <typename Fetch>
float voice_dsp_sample_at(
    const VoiceDspState& state,
    std::uint64_t position,
    Fetch&& fetch) noexcept {
  const auto whole = static_cast<std::uint32_t>(position >> 32);
  const auto fraction = static_cast<std::uint32_t>(position);
  if (fraction == 0) {
    return fetch(voice_dsp_physical_frame(state, whole));
  }
  // 4-point Catmull-Rom Hermite. Neighbours outside the region clamp to its
  // edge frames, so no read leaves the trimmed material.
  const auto last = state.length - 1;
  const auto previous = whole == 0 ? 0 : whole - 1;
  const auto next = whole >= last ? last : whole + 1;
  const auto after = whole + 2 > last ? last : whole + 2;
  const float xm1 = fetch(voice_dsp_physical_frame(state, previous));
  const float x0 = fetch(voice_dsp_physical_frame(state, whole));
  const float x1 = fetch(voice_dsp_physical_frame(state, next));
  const float x2 = fetch(voice_dsp_physical_frame(state, after));
  const float t = static_cast<float>(fraction) * 0x1p-32F;
  const float c1 = 0.5F * (x1 - xm1);
  const float c2 = xm1 - 2.5F * x0 + 2.0F * x1 - 0.5F * x2;
  const float c3 = 0.5F * (x2 - xm1) + 1.5F * (x0 - x1);
  return ((c3 * t + c2) * t + c1) * t + x0;
}

// The voice's sample under the read head, before gain, ramps and pan. Inside
// a forward loop's crossfade window the tail is blended equal-power with the
// matching frame of the loop head; the next pass resumes after that head.
template <typename Fetch>
float voice_dsp_read(const VoiceDspState& state, Fetch&& fetch) noexcept {
  const float tail = voice_dsp_sample_at(state, state.position, fetch);
  if (state.crossfade == 0) {
    return tail;
  }
  const auto window_start =
      static_cast<std::uint64_t>(state.length - state.crossfade) << 32;
  if (state.position < window_start) {
    return tail;
  }
  const auto into = state.position - window_start;
  const auto head_position =
      (static_cast<std::uint64_t>(state.loop_begin) << 32) + into;
  const float head = voice_dsp_sample_at(state, head_position, fetch);
  const float t = static_cast<float>(into) /
                  static_cast<float>(
                      static_cast<std::uint64_t>(state.crossfade) << 32);
  return tail * quarter_sine(1.0F - t) + head * quarter_sine(t);
}

// The non-looping end fade: 1 until the last 96 output frames, then the
// remaining output distance over 96, as the renderer's original fade.
inline float voice_dsp_end_fade(const VoiceDspState& state) noexcept {
  if (state.looping) {
    return 1.0F;
  }
  const auto end = static_cast<std::uint64_t>(state.length) << 32;
  const auto remaining = end - state.position;
  if (remaining >= state.fade_span) {
    return 1.0F;
  }
  return static_cast<float>(remaining) * state.inverse_fade_span;
}

// Advances one output frame. Returns false once a non-looping voice has
// passed its last frame.
inline bool voice_dsp_advance(VoiceDspState& state) noexcept {
  const auto end = static_cast<std::uint64_t>(state.length) << 32;
  if (!state.ping_pong) {
    state.position += state.step;
    if (state.position < end) {
      return true;
    }
    if (!state.looping) {
      return false;
    }
    const auto resume =
        static_cast<std::uint64_t>(state.loop_begin + state.crossfade) << 32;
    const auto cycle = end - resume;
    state.position = resume + (state.position - end) % cycle;
    return true;
  }
  // Ping-pong reflects at the last frame and at the loop point, so neither
  // boundary frame plays twice in a row.
  const auto top = end - (std::uint64_t{1} << 32);
  const auto bottom = static_cast<std::uint64_t>(state.loop_begin) << 32;
  if (top <= bottom) {
    state.position = bottom;
    return true;
  }
  if (!state.backwards) {
    state.position += state.step;
    if (state.position > top) {
      const auto over = state.position - top;
      state.position = over >= top - bottom ? bottom : top - over;
      state.backwards = true;
    }
    return true;
  }
  if (state.position - bottom >= state.step) {
    state.position -= state.step;
    return true;
  }
  const auto under = state.step - (state.position - bottom);
  state.position = under >= top - bottom ? top : bottom + under;
  state.backwards = false;
  return true;
}

}  // namespace lmdj::audio::detail
