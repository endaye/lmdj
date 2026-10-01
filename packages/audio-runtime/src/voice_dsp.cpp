#include <lmdj/audio/detail/voice_dsp.hpp>

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace lmdj::audio::detail {
namespace {

constexpr std::size_t kQuarterSineSegments = 256;
constexpr float kPi = 3.14159265358979323846F;

std::array<float, kQuarterSineSegments + 1> make_quarter_sine() noexcept {
  std::array<float, kQuarterSineSegments + 1> table{};
  for (std::size_t index = 0; index <= kQuarterSineSegments; ++index) {
    table[index] = std::sin(
        static_cast<float>(index) * (kPi * 0.5F) /
        static_cast<float>(kQuarterSineSegments));
  }
  // The end points are exact so a full-scale blend reaches unity and zero.
  table.front() = 0.0F;
  table.back() = 1.0F;
  return table;
}

// Built during static initialisation, before any render callback runs.
const std::array<float, kQuarterSineSegments + 1> kQuarterSine =
    make_quarter_sine();

bool is_looping(domain::TriggerMode mode) noexcept {
  return mode == domain::TriggerMode::loop_gate ||
         mode == domain::TriggerMode::loop_toggle;
}

}  // namespace

float quarter_sine(float t) noexcept {
  if (!(t > 0.0F)) {
    return 0.0F;
  }
  if (t >= 1.0F) {
    return 1.0F;
  }
  const float scaled = t * static_cast<float>(kQuarterSineSegments);
  const auto index = static_cast<std::size_t>(scaled);
  const float fraction = scaled - static_cast<float>(index);
  return kQuarterSine[index] +
         (kQuarterSine[index + 1] - kQuarterSine[index]) * fraction;
}

bool prepare_voice_dsp(
    const cooker::ResolvedPlayback& playback,
    std::size_t material_frames,
    VoiceDspState& state) noexcept {
  using Dsp = cooker::ResolvedVoiceDsp;
  const auto& dsp = playback.dsp;
  constexpr std::uint8_t kKnownFlags = Dsp::kReverse | Dsp::kPingPong;
  if (playback.start_frame >= playback.end_frame ||
      playback.end_frame > material_frames ||
      (dsp.flags & static_cast<std::uint8_t>(~kKnownFlags)) != 0 ||
      dsp.pitch_cents < domain::kPadPitchCentsMin ||
      dsp.pitch_cents > domain::kPadPitchCentsMax ||
      dsp.pan < domain::kPadPanMin || dsp.pan > domain::kPadPanMax) {
    return false;
  }
  const auto length = playback.end_frame - playback.start_frame;
  if (dsp.loop_start_offset >= length) {
    return false;
  }
  const bool ping_pong_requested = (dsp.flags & Dsp::kPingPong) != 0;
  if ((ping_pong_requested && dsp.loop_crossfade_frames != 0) ||
      dsp.loop_crossfade_frames > (length - dsp.loop_start_offset) / 2) {
    return false;
  }

  const bool looping = is_looping(playback.trigger_mode);
  state = VoiceDspState{};
  state.start = playback.start_frame;
  state.length = length;
  state.looping = looping;
  state.ping_pong = looping && ping_pong_requested;
  state.loop_begin = looping ? dsp.loop_start_offset : 0;
  state.crossfade =
      looping && !state.ping_pong ? dsp.loop_crossfade_frames : 0;
  state.reverse = (dsp.flags & Dsp::kReverse) != 0;

  // The rate is computed once per trigger; whole octaves are exact powers of
  // two, so +/-1200 cents halves or doubles a voice exactly.
  state.step = dsp.pitch_cents == 0
                   ? std::uint64_t{1} << 32
                   : static_cast<std::uint64_t>(std::llround(
                         std::exp2(static_cast<double>(dsp.pitch_cents) /
                                   1200.0) *
                         4294967296.0));
  state.fade_span = state.step * kVoiceDspRampFrames;
  state.inverse_fade_span = 1.0F / static_cast<float>(state.fade_span);

  // Equal-power pan with unity at the centre; a hard pan is exact silence on
  // the far side because sin(0) is exactly zero.
  if (dsp.pan == 0) {
    state.pan_left = 1.0F;
    state.pan_right = 1.0F;
  } else {
    constexpr float kSqrt2 = 1.41421356237309504880F;
    const float unit = kPi / 400.0F;
    state.pan_left =
        kSqrt2 * std::sin(static_cast<float>(100 - dsp.pan) * unit);
    state.pan_right =
        kSqrt2 * std::sin(static_cast<float>(100 + dsp.pan) * unit);
  }
  return true;
}

}  // namespace lmdj::audio::detail
