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

// Biquad design for the 48 kHz engine rate, after the RBJ Audio EQ Cookbook.
// Coefficients are derived in double once per trigger and stored as float.
constexpr double kSampleRate = 48'000.0;
constexpr double kTwoPi = 6.28318530717958647692;
constexpr double kButterworthQ = 0.70710678118654752440;

VoiceDspBiquad normalized(
    double b0, double b1, double b2, double a0, double a1, double a2) noexcept {
  return VoiceDspBiquad{
      static_cast<float>(b0 / a0), static_cast<float>(b1 / a0),
      static_cast<float>(b2 / a0), static_cast<float>(a1 / a0),
      static_cast<float>(a2 / a0)};
}

struct Angle {
  double cosine;
  double alpha;
};

Angle angle(double hz, double q) noexcept {
  const double w0 = kTwoPi * hz / kSampleRate;
  return Angle{std::cos(w0), std::sin(w0) / (2.0 * q)};
}

// A 12 dB/oct Butterworth low-pass or high-pass.
VoiceDspBiquad pass(double hz, bool high) noexcept {
  const auto [c, alpha] = angle(hz, kButterworthQ);
  const double side = high ? (1.0 + c) / 2.0 : (1.0 - c) / 2.0;
  return normalized(
      side, high ? -(1.0 + c) : 1.0 - c, side, 1.0 + alpha, -2.0 * c,
      1.0 - alpha);
}

VoiceDspBiquad bell(double hz, double gain_db, double q) noexcept {
  const double a = std::pow(10.0, gain_db / 40.0);
  const auto [c, alpha] = angle(hz, q);
  return normalized(
      1.0 + alpha * a, -2.0 * c, 1.0 - alpha * a, 1.0 + alpha / a, -2.0 * c,
      1.0 - alpha / a);
}

// A shelf with slope S = 1.
VoiceDspBiquad shelf(double hz, double gain_db, bool high) noexcept {
  const double a = std::pow(10.0, gain_db / 40.0);
  const auto [c, alpha_q] = angle(hz, kButterworthQ);
  const double root = 2.0 * std::sqrt(a) * alpha_q;
  const double sign = high ? -1.0 : 1.0;
  const double b0 = a * ((a + 1.0) - sign * (a - 1.0) * c + root);
  const double b1 = sign * 2.0 * a * ((a - 1.0) - sign * (a + 1.0) * c);
  const double b2 = a * ((a + 1.0) - sign * (a - 1.0) * c - root);
  const double a0 = (a + 1.0) + sign * (a - 1.0) * c + root;
  const double a1 = -sign * 2.0 * ((a - 1.0) + sign * (a + 1.0) * c);
  const double a2 = (a + 1.0) + sign * (a - 1.0) * c - root;
  return normalized(b0, b1, b2, a0, a1, a2);
}

// The tone stage, when |tone| is outside the +/-2 deadband. A negative tone is
// a low-pass whose cutoff sweeps logarithmically from 20 kHz to 100 Hz at
// -100; a positive one a high-pass from 20 Hz to 8 kHz at +100.
VoiceDspBiquad tone_stage(std::int8_t tone) noexcept {
  if (tone < 0) {
    return pass(
        20'000.0 * std::pow(100.0 / 20'000.0, -static_cast<double>(tone) / 100.0),
        false);
  }
  return pass(
      20.0 * std::pow(8'000.0 / 20.0, static_cast<double>(tone) / 100.0), true);
}

bool in_range(std::int32_t value, std::int32_t low, std::int32_t high) noexcept {
  return value >= low && value <= high;
}

// The tone and EQ bounds Project Truth admits; anything else is refused.
bool tone_fits(const cooker::ResolvedVoiceDsp& dsp) noexcept {
  using Dsp = cooker::ResolvedVoiceDsp;
  constexpr std::uint8_t kKnownEq =
      Dsp::kEqLow | Dsp::kEqLowCut | Dsp::kEqMid | Dsp::kEqHigh | Dsp::kEqHighCut;
  const auto flags = dsp.eq_flags;
  const auto gain = [](std::int16_t value) {
    return in_range(value, domain::kPadEqGainMillidbMin, domain::kPadEqGainMillidbMax);
  };
  if ((flags & static_cast<std::uint8_t>(~kKnownEq)) != 0 ||
      ((flags & Dsp::kEqLowCut) != 0 && (flags & Dsp::kEqLow) == 0) ||
      ((flags & Dsp::kEqHighCut) != 0 && (flags & Dsp::kEqHigh) == 0) ||
      !in_range(dsp.tone, domain::kPadToneMin, domain::kPadToneMax)) {
    return false;
  }
  if ((flags & Dsp::kEqLow) != 0 &&
      (!in_range(dsp.eq_low_freq_hz, domain::kPadEqLowFreqHzMin,
                 domain::kPadEqLowFreqHzMax) ||
       !gain(dsp.eq_low_gain_millidb))) {
    return false;
  }
  if ((flags & Dsp::kEqMid) != 0 &&
      (!in_range(dsp.eq_mid_freq_hz, domain::kPadEqMidFreqHzMin,
                 domain::kPadEqMidFreqHzMax) ||
       !gain(dsp.eq_mid_gain_millidb) ||
       !in_range(dsp.eq_mid_q_milli, domain::kPadEqMidQMilliMin,
                 domain::kPadEqMidQMilliMax))) {
    return false;
  }
  return (flags & Dsp::kEqHigh) == 0 ||
         (in_range(dsp.eq_high_freq_hz, domain::kPadEqHighFreqHzMin,
                   domain::kPadEqHighFreqHzMax) &&
          gain(dsp.eq_high_gain_millidb));
}

// Fills the enabled stages in order: tone, low, mid, high.
void prepare_filters(
    const cooker::ResolvedVoiceDsp& dsp, VoiceDspState& state) noexcept {
  using Dsp = cooker::ResolvedVoiceDsp;
  const auto add = [&state](VoiceDspBiquad stage) {
    state.filters[state.filter_count++] = stage;
  };
  if (dsp.tone < -2 || dsp.tone > 2) {
    add(tone_stage(dsp.tone));
  }
  const auto db = [](std::int16_t millidb) {
    return static_cast<double>(millidb) / 1'000.0;
  };
  if ((dsp.eq_flags & Dsp::kEqLow) != 0) {
    add((dsp.eq_flags & Dsp::kEqLowCut) != 0
            ? pass(dsp.eq_low_freq_hz, true)
            : shelf(dsp.eq_low_freq_hz, db(dsp.eq_low_gain_millidb), false));
  }
  if ((dsp.eq_flags & Dsp::kEqMid) != 0) {
    add(bell(dsp.eq_mid_freq_hz, db(dsp.eq_mid_gain_millidb),
             static_cast<double>(dsp.eq_mid_q_milli) / 1'000.0));
  }
  if ((dsp.eq_flags & Dsp::kEqHigh) != 0) {
    add((dsp.eq_flags & Dsp::kEqHighCut) != 0
            ? pass(dsp.eq_high_freq_hz, false)
            : shelf(dsp.eq_high_freq_hz, db(dsp.eq_high_gain_millidb), true));
  }
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
      dsp.pan < domain::kPadPanMin || dsp.pan > domain::kPadPanMax ||
      dsp.attack_frames > kVoiceDspMaxAttackFrames ||
      dsp.release_frames > kVoiceDspMaxReleaseFrames || !tone_fits(dsp)) {
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

  prepare_filters(dsp, state);

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
