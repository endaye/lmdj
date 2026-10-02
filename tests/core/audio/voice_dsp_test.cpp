#include <lmdj/audio/detail/voice_dsp.hpp>

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <random>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::detail::VoiceDspState;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::ResolvedVoiceDsp;
using lmdj::domain::TriggerMode;

ResolvedPlayback playback(
    std::uint32_t start,
    std::uint32_t end,
    TriggerMode mode,
    ResolvedVoiceDsp dsp) {
  ResolvedPlayback value{start, end, mode, 1.0F, false};
  value.dsp = dsp;
  return value;
}

// A source whose value at frame i is i, so a read reports the frame it took.
std::vector<float> index_source(std::size_t frames) {
  std::vector<float> source(frames);
  for (std::size_t index = 0; index < frames; ++index) {
    source[index] = static_cast<float>(index);
  }
  return source;
}

VoiceDspState prepared(const ResolvedPlayback& value, std::size_t frames) {
  VoiceDspState state{};
  LMDJ_CHECK(lmdj::audio::detail::prepare_voice_dsp(value, frames, state));
  return state;
}

// Renders up to `limit` output frames; a non-looping voice stops at its end.
std::vector<float> render(
    VoiceDspState state,
    const std::vector<float>& source,
    std::size_t limit) {
  std::vector<float> output;
  const auto fetch = [&source](std::uint32_t frame) { return source[frame]; };
  for (std::size_t frame = 0; frame < limit; ++frame) {
    output.push_back(lmdj::audio::detail::voice_dsp_read(state, fetch));
    if (!lmdj::audio::detail::voice_dsp_advance(state)) {
      break;
    }
  }
  return output;
}

void prepare_refuses_a_block_that_does_not_fit() {
  const auto source = index_source(32);
  VoiceDspState state{};
  for (const auto& dsp : {
           ResolvedVoiceDsp{0, 0, 2401, 0, 0},
           ResolvedVoiceDsp{0, 0, -2401, 0, 0},
           ResolvedVoiceDsp{0, 0, 0, 101, 0},
           ResolvedVoiceDsp{0, 0, 0, 0, 0x04},
           ResolvedVoiceDsp{20, 0, 0, 0, 0},
           ResolvedVoiceDsp{0, 1, 0, 0, ResolvedVoiceDsp::kPingPong},
           ResolvedVoiceDsp{10, 6, 0, 0, 0},
       }) {
    LMDJ_CHECK(!lmdj::audio::detail::prepare_voice_dsp(
        playback(0, 20, TriggerMode::loop_gate, dsp), source.size(), state));
  }
  // A 10-frame loop may blend exactly half of itself.
  LMDJ_CHECK(lmdj::audio::detail::prepare_voice_dsp(
      playback(0, 20, TriggerMode::loop_gate, ResolvedVoiceDsp{10, 5, 0, 0, 0}),
      source.size(), state));
}

ResolvedVoiceDsp envelope(std::uint32_t attack, std::uint32_t release) {
  ResolvedVoiceDsp dsp{};
  dsp.attack_frames = attack;
  dsp.release_frames = release;
  return dsp;
}

// An envelope longer than Project Truth admits (2 s attack, 4 s release at
// 48 kHz) is refused like an out-of-range pitch; the longest admitted fits.
void prepare_refuses_an_over_long_envelope() {
  const auto source = index_source(32);
  VoiceDspState state{};
  for (const auto& dsp : {envelope(96'001, 0), envelope(0, 192'001)}) {
    LMDJ_CHECK(!lmdj::audio::detail::prepare_voice_dsp(
        playback(0, 20, TriggerMode::gate, dsp), source.size(), state));
  }
  LMDJ_CHECK(lmdj::audio::detail::prepare_voice_dsp(
      playback(0, 20, TriggerMode::gate, envelope(96'000, 192'000)),
      source.size(), state));
}

// Envelope ramps last max(user, 96) output frames, and a one-shot keeps the
// 96-frame declick for its release. At the default the scale is exactly the
// declick's 1/96, so a default envelope renders bit-identically.
void envelope_is_never_shorter_than_the_declick() {
  using lmdj::audio::detail::voice_envelope;
  const auto neutral = voice_envelope(playback(0, 20, TriggerMode::gate, {}));
  LMDJ_CHECK(neutral.attack_frames == 96);
  LMDJ_CHECK(neutral.release_frames == 96);
  LMDJ_CHECK(neutral.attack_scale == 1.0F / 96.0F);
  LMDJ_CHECK(neutral.release_scale == 1.0F / 96.0F);
  const auto short_ramps =
      voice_envelope(playback(0, 20, TriggerMode::gate, envelope(50, 95)));
  LMDJ_CHECK(short_ramps.attack_frames == 96);
  LMDJ_CHECK(short_ramps.release_frames == 96);
  const auto long_ramps =
      voice_envelope(playback(0, 20, TriggerMode::loop_gate, envelope(480, 4800)));
  LMDJ_CHECK(long_ramps.attack_frames == 480);
  LMDJ_CHECK(long_ramps.attack_scale == 1.0F / 480.0F);
  LMDJ_CHECK(long_ramps.release_frames == 4800);
  LMDJ_CHECK(long_ramps.release_scale == 1.0F / 4800.0F);
  const auto one_shot =
      voice_envelope(playback(0, 20, TriggerMode::one_shot, envelope(480, 4800)));
  LMDJ_CHECK(one_shot.attack_frames == 480);
  LMDJ_CHECK(one_shot.release_frames == 96);
}

// --- Tone and 3-band EQ (lmdj.project.v5 5.2.0) ---

VoiceDspState filter_state(const ResolvedVoiceDsp& dsp) {
  VoiceDspState state{};
  LMDJ_CHECK(lmdj::audio::detail::prepare_voice_dsp(
      playback(0, 20, TriggerMode::gate, dsp), 32, state));
  return state;
}

// The steady-state gain, in dB, of the voice's filter stages for a sine at
// `hz`: one second of 48 kHz input, measured over its second half.
double gain_db(const VoiceDspState& state, double hz) {
  lmdj::audio::detail::VoiceDspFilterMemory memory{};
  double in = 0.0;
  double out = 0.0;
  for (int frame = 0; frame < 48'000; ++frame) {
    const auto x = static_cast<float>(
        0.25 * std::sin(6.28318530717958647692 * hz * frame / 48'000.0));
    const auto y = lmdj::audio::detail::voice_dsp_filter(state, memory, x);
    if (frame >= 24'000) {
      in += static_cast<double>(x) * x;
      out += static_cast<double>(y) * y;
    }
  }
  return 10.0 * std::log10(out / in);
}

ResolvedVoiceDsp tone(std::int8_t value) {
  ResolvedVoiceDsp dsp{};
  dsp.tone = value;
  return dsp;
}

// Tone -100 is a 12 dB/oct low-pass at 100 Hz: -3 dB there, flat below,
// at least 40 dB down at 10 kHz.
void tone_minus_100_is_a_100_hz_low_pass() {
  const auto state = filter_state(tone(-100));
  LMDJ_CHECK(state.filter_count == 1);
  LMDJ_CHECK(std::abs(gain_db(state, 100.0) + 3.01) <= 0.1);
  LMDJ_CHECK(std::abs(gain_db(state, 50.0)) <= 1.0);
  LMDJ_CHECK(gain_db(state, 10'000.0) <= -40.0);
}

// Tone +100 is the mirror image: a 12 dB/oct high-pass at 8 kHz.
void tone_plus_100_is_an_8_khz_high_pass() {
  const auto state = filter_state(tone(100));
  LMDJ_CHECK(state.filter_count == 1);
  LMDJ_CHECK(std::abs(gain_db(state, 8'000.0) + 3.01) <= 0.1);
  LMDJ_CHECK(std::abs(gain_db(state, 16'000.0)) <= 1.0);
  LMDJ_CHECK(gain_db(state, 100.0) <= -40.0);
}

// |tone| <= 2 is a deadband: no stage at all, so the voice is unfiltered.
void tone_deadband_adds_no_stage() {
  for (const std::int8_t value : {-2, -1, 1, 2}) {
    LMDJ_CHECK(filter_state(tone(value)).filter_count == 0);
  }
  LMDJ_CHECK(filter_state(tone(3)).filter_count == 1);
  LMDJ_CHECK(filter_state(tone(-3)).filter_count == 1);
}

ResolvedVoiceDsp mid_band(std::uint16_t hz, std::int16_t millidb, std::uint16_t q_milli) {
  ResolvedVoiceDsp dsp{};
  dsp.eq_flags = ResolvedVoiceDsp::kEqMid;
  dsp.eq_mid_freq_hz = hz;
  dsp.eq_mid_gain_millidb = millidb;
  dsp.eq_mid_q_milli = q_milli;
  return dsp;
}

// The mid bell: +12 dB at 1 kHz with Q 1 measures 12 dB at its centre, and
// leaves distant frequencies near unity.
void mid_bell_reaches_its_gain_at_its_centre() {
  const auto state = filter_state(mid_band(1'000, 12'000, 1'000));
  LMDJ_CHECK(std::abs(gain_db(state, 1'000.0) - 12.0) <= 0.1);
  LMDJ_CHECK(std::abs(gain_db(state, 50.0)) <= 0.5);
}

// A low cut is a high-pass at its frequency and a high cut a low-pass, both
// -3 dB at the band frequency and blind to the band's gain.
void cut_bands_are_minus_3_db_at_their_frequency() {
  ResolvedVoiceDsp low{};
  low.eq_flags = ResolvedVoiceDsp::kEqLow | ResolvedVoiceDsp::kEqLowCut;
  low.eq_low_freq_hz = 200;
  low.eq_low_gain_millidb = 18'000;
  const auto low_state = filter_state(low);
  LMDJ_CHECK(std::abs(gain_db(low_state, 200.0) + 3.01) <= 0.1);
  LMDJ_CHECK(gain_db(low_state, 20.0) <= -35.0);
  ResolvedVoiceDsp high{};
  high.eq_flags = ResolvedVoiceDsp::kEqHigh | ResolvedVoiceDsp::kEqHighCut;
  high.eq_high_freq_hz = 5'000;
  high.eq_high_gain_millidb = -18'000;
  const auto high_state = filter_state(high);
  LMDJ_CHECK(std::abs(gain_db(high_state, 5'000.0) + 3.01) <= 0.1);
  LMDJ_CHECK(gain_db(high_state, 20'000.0) <= -15.0);
}

// Shelves lift or cut everything beyond their frequency by their gain.
void shelves_reach_their_gain_beyond_their_frequency() {
  ResolvedVoiceDsp low{};
  low.eq_flags = ResolvedVoiceDsp::kEqLow;
  low.eq_low_freq_hz = 200;
  low.eq_low_gain_millidb = 6'000;
  const auto low_state = filter_state(low);
  LMDJ_CHECK(std::abs(gain_db(low_state, 20.0) - 6.0) <= 0.2);
  LMDJ_CHECK(std::abs(gain_db(low_state, 10'000.0)) <= 0.2);
  ResolvedVoiceDsp high{};
  high.eq_flags = ResolvedVoiceDsp::kEqHigh;
  high.eq_high_freq_hz = 2'000;
  high.eq_high_gain_millidb = -6'000;
  const auto high_state = filter_state(high);
  LMDJ_CHECK(std::abs(gain_db(high_state, 20'000.0) + 6.0) <= 0.3);
  LMDJ_CHECK(std::abs(gain_db(high_state, 50.0)) <= 0.2);
}

ResolvedVoiceDsp every_stage() {
  auto dsp = mid_band(10'000, 18'000, 10'000);
  dsp.tone = 100;
  dsp.eq_flags |= ResolvedVoiceDsp::kEqLow | ResolvedVoiceDsp::kEqLowCut |
                  ResolvedVoiceDsp::kEqHigh;
  dsp.eq_low_freq_hz = 2'000;
  dsp.eq_high_freq_hz = 1'000;
  dsp.eq_high_gain_millidb = 18'000;
  return dsp;
}

// Ten seconds of noise through every stage at extreme settings stay finite,
// and after the input stops, per-block flushing reaches exact zero.
void extreme_filters_stay_finite_and_flush_to_zero() {
  const auto state = filter_state(every_stage());
  LMDJ_CHECK(state.filter_count == 4);
  lmdj::audio::detail::VoiceDspFilterMemory memory{};
  std::mt19937 random{1667};
  std::uniform_real_distribution<float> noise{-1.0F, 1.0F};
  for (int frame = 0; frame < 480'000; ++frame) {
    const auto y = lmdj::audio::detail::voice_dsp_filter(state, memory, noise(random));
    LMDJ_CHECK(std::isfinite(y));
  }
  for (int frame = 0; frame < 96'000; ++frame) {
    lmdj::audio::detail::voice_dsp_filter(state, memory, 0.0F);
    if ((frame & 127) == 127) {
      lmdj::audio::detail::voice_dsp_flush_filters(state, memory);
    }
  }
  for (const auto& stage : memory.z) {
    LMDJ_CHECK(stage[0] == 0.0F && stage[1] == 0.0F);
  }
}

// Tone and EQ values outside Project Truth's bounds, unknown EQ flags, and a
// cut flag on an absent band are refused; the boundaries fit.
void prepare_refuses_out_of_range_tone_and_eq() {
  const auto source = index_source(32);
  VoiceDspState state{};
  const auto refused = [&](ResolvedVoiceDsp dsp) {
    return !lmdj::audio::detail::prepare_voice_dsp(
        playback(0, 20, TriggerMode::gate, dsp), source.size(), state);
  };
  ResolvedVoiceDsp bad = tone(101);
  LMDJ_CHECK(refused(bad));
  LMDJ_CHECK(refused(tone(-101)));
  bad = {};
  bad.eq_flags = 0x20;
  LMDJ_CHECK(refused(bad));
  bad.eq_flags = ResolvedVoiceDsp::kEqLowCut;
  LMDJ_CHECK(refused(bad));
  bad.eq_flags = ResolvedVoiceDsp::kEqHighCut;
  LMDJ_CHECK(refused(bad));
  LMDJ_CHECK(refused(mid_band(99, 0, 1'000)));
  LMDJ_CHECK(refused(mid_band(1'000, 18'001, 1'000)));
  LMDJ_CHECK(refused(mid_band(1'000, 0, 10'001)));
  ResolvedVoiceDsp low{};
  low.eq_flags = ResolvedVoiceDsp::kEqLow;
  low.eq_low_freq_hz = 2'001;
  LMDJ_CHECK(refused(low));
  ResolvedVoiceDsp high{};
  high.eq_flags = ResolvedVoiceDsp::kEqHigh;
  high.eq_high_freq_hz = 999;
  LMDJ_CHECK(refused(high));
  LMDJ_CHECK(!refused(every_stage()));
  LMDJ_CHECK(!refused(mid_band(100, -18'000, 100)));
}

void neutral_block_reads_the_source_exactly() {
  const auto source = index_source(16);
  const auto output = render(
      prepared(playback(3, 11, TriggerMode::one_shot, {}), source.size()),
      source, 64);
  LMDJ_CHECK(output.size() == 8);
  for (std::size_t index = 0; index < output.size(); ++index) {
    LMDJ_CHECK(output[index] == source[3 + index]);
  }
}

void reverse_reads_the_mirrored_source_exactly() {
  const auto source = index_source(16);
  const auto output = render(
      prepared(playback(3, 11, TriggerMode::one_shot,
                        {0, 0, 0, 0, ResolvedVoiceDsp::kReverse}),
               source.size()),
      source, 64);
  LMDJ_CHECK(output.size() == 8);
  for (std::size_t index = 0; index < output.size(); ++index) {
    LMDJ_CHECK(output[index] == source[10 - index]);
  }
}

void whole_octaves_halve_and_double_a_one_shot() {
  const auto source = index_source(256);
  const auto up = render(
      prepared(playback(0, 200, TriggerMode::one_shot, {0, 0, 1200, 0, 0}),
               source.size()),
      source, 1000);
  const auto down = render(
      prepared(playback(0, 200, TriggerMode::one_shot, {0, 0, -1200, 0, 0}),
               source.size()),
      source, 1000);
  LMDJ_CHECK(up.size() == 100);
  LMDJ_CHECK(down.size() == 400);
}

void hermite_is_exact_on_frames_and_linear_on_a_ramp() {
  std::vector<float> ramp(64);
  for (std::size_t index = 0; index < ramp.size(); ++index) {
    ramp[index] = 0.25F * static_cast<float>(index);
  }
  auto state = prepared(
      playback(0, 64, TriggerMode::one_shot, {0, 0, 700, 0, 0}), ramp.size());
  const auto fetch = [&ramp](std::uint32_t frame) { return ramp[frame]; };
  for (int frame = 0; frame < 40; ++frame) {
    const double expected =
        0.25 * static_cast<double>(state.position) / 4294967296.0;
    const float actual = lmdj::audio::detail::voice_dsp_read(state, fetch);
    LMDJ_CHECK(std::abs(static_cast<double>(actual) - expected) < 1e-5);
    if (static_cast<std::uint32_t>(state.position) == 0) {
      LMDJ_CHECK(actual == ramp[state.position >> 32]);
    }
    LMDJ_CHECK(lmdj::audio::detail::voice_dsp_advance(state));
  }
}

void ping_pong_reflects_without_repeating_a_boundary_frame() {
  const auto source = index_source(32);
  const auto output = render(
      prepared(playback(0, 8, TriggerMode::loop_gate,
                        {4, 0, 0, 0, ResolvedVoiceDsp::kPingPong}),
               source.size()),
      source, 16);
  const std::vector<float> expected{
      0, 1, 2, 3, 4, 5, 6, 7, 6, 5, 4, 5, 6, 7, 6, 5};
  LMDJ_CHECK(output == expected);
}

void later_loop_passes_resume_at_the_loop_point() {
  const auto source = index_source(32);
  const auto output = render(
      prepared(playback(0, 6, TriggerMode::loop_toggle, {2, 0, 0, 0, 0}),
               source.size()),
      source, 14);
  const std::vector<float> expected{
      0, 1, 2, 3, 4, 5, 2, 3, 4, 5, 2, 3, 4, 5};
  LMDJ_CHECK(output == expected);
}

// Reverse mirrors the whole trimmed region, loop point included: the first
// pass starts at the mirror of the trim start, and later passes wrap to the
// mirror of the loop point, so a null loop point (offset 0) still loops the
// whole region.
void reverse_mirrors_the_loop_point_with_the_region() {
  const auto source = index_source(32);
  const auto output = render(
      prepared(playback(0, 8, TriggerMode::loop_toggle,
                        {2, 0, 0, 0, ResolvedVoiceDsp::kReverse}),
               source.size()),
      source, 20);
  const std::vector<float> expected{
      7, 6, 5, 4, 3, 2, 1, 0, 5, 4, 3, 2, 1, 0, 5, 4, 3, 2, 1, 0};
  LMDJ_CHECK(output == expected);
}

void crossfade_gains_hold_constant_power() {
  for (int step = 0; step <= 1000; ++step) {
    const float t = static_cast<float>(step) / 1000.0F;
    const float in = lmdj::audio::detail::quarter_sine(t);
    const float out = lmdj::audio::detail::quarter_sine(1.0F - t);
    LMDJ_CHECK(std::abs(in * in + out * out - 1.0F) < 1e-4F);
  }
}

void crossfade_overlaps_the_loop_head_and_shortens_the_cycle() {
  std::vector<float> source(16, 0.0F);
  for (std::size_t index = 0; index < 4; ++index) {
    source[index] = 1.0F;
  }
  const auto output = render(
      prepared(playback(0, 16, TriggerMode::loop_gate, {0, 4, 0, 0, 0}),
               source.size()),
      source, 40);
  // Frames 12..15 blend the silent tail with the unit head: the head's gain
  // rises from zero across the window.
  LMDJ_CHECK(output[12] == 0.0F);
  LMDJ_CHECK(output[13] > 0.0F && output[13] < output[14]);
  LMDJ_CHECK(output[14] < output[15] && output[15] < 1.0F);
  // The next pass resumes after the blended head, so the cycle is 12 frames.
  LMDJ_CHECK(output[16] == source[4]);
  LMDJ_CHECK(output[28] == source[4]);
}

// Every frame of the window is tail * sin((1 - t) pi / 2) + head * sin(t pi / 2),
// with distinct non-zero tail and head values so neither gain can hide.
void crossfade_blends_tail_and_head_with_complementary_gains() {
  std::vector<float> source(16);
  for (std::size_t index = 0; index < source.size(); ++index) {
    source[index] = static_cast<float>(index + 1);
  }
  const auto output = render(
      prepared(playback(0, 16, TriggerMode::loop_gate, {0, 4, 0, 0, 0}),
               source.size()),
      source, 16);
  for (std::size_t into = 0; into < 4; ++into) {
    const float t = static_cast<float>(into) / 4.0F;
    const float expected =
        source[12 + into] * lmdj::audio::detail::quarter_sine(1.0F - t) +
        source[into] * lmdj::audio::detail::quarter_sine(t);
    LMDJ_CHECK(std::abs(output[12 + into] - expected) < 1e-5F);
  }
  LMDJ_CHECK(output[12] == source[12]);
}

void hard_pan_silences_the_far_side_exactly() {
  const auto source = index_source(4);
  const auto left = prepared(
      playback(0, 4, TriggerMode::one_shot, {0, 0, 0, -100, 0}), source.size());
  const auto right = prepared(
      playback(0, 4, TriggerMode::one_shot, {0, 0, 0, 100, 0}), source.size());
  const auto centre = prepared(
      playback(0, 4, TriggerMode::one_shot, {0, 0, 0, 0, 0}), source.size());
  LMDJ_CHECK(left.pan_right == 0.0F);
  LMDJ_CHECK(std::abs(left.pan_left - 1.41421356F) < 1e-6F);
  LMDJ_CHECK(right.pan_left == 0.0F);
  LMDJ_CHECK(centre.pan_left == 1.0F && centre.pan_right == 1.0F);
}

void pitched_voice_fades_over_its_last_96_output_frames() {
  const auto source = index_source(512);
  auto state = prepared(
      playback(0, 400, TriggerMode::one_shot, {0, 0, 1200, 0, 0}),
      source.size());
  std::vector<float> fades;
  do {
    fades.push_back(lmdj::audio::detail::voice_dsp_end_fade(state));
  } while (lmdj::audio::detail::voice_dsp_advance(state));
  LMDJ_CHECK(fades.size() == 200);
  for (std::size_t index = 0; index + 96 < fades.size(); ++index) {
    LMDJ_CHECK(fades[index] == 1.0F);
  }
  for (std::size_t index = fades.size() - 96; index < fades.size(); ++index) {
    const float expected =
        static_cast<float>(fades.size() - index) / 96.0F;
    LMDJ_CHECK(std::abs(fades[index] - expected) < 1e-6F);
  }
}

void reversed_voice_publishes_descending_source_frames() {
  auto state = prepared(
      playback(5, 9, TriggerMode::one_shot,
               {0, 0, 0, 0, ResolvedVoiceDsp::kReverse}),
      16);
  std::vector<std::uint32_t> frames;
  do {
    frames.push_back(lmdj::audio::detail::voice_dsp_source_frame(state));
  } while (lmdj::audio::detail::voice_dsp_advance(state));
  LMDJ_CHECK((frames == std::vector<std::uint32_t>{8, 7, 6, 5}));
}

}  // namespace

int main() {
  try {
    prepare_refuses_a_block_that_does_not_fit();
    prepare_refuses_an_over_long_envelope();
    envelope_is_never_shorter_than_the_declick();
    tone_minus_100_is_a_100_hz_low_pass();
    tone_plus_100_is_an_8_khz_high_pass();
    tone_deadband_adds_no_stage();
    mid_bell_reaches_its_gain_at_its_centre();
    cut_bands_are_minus_3_db_at_their_frequency();
    shelves_reach_their_gain_beyond_their_frequency();
    extreme_filters_stay_finite_and_flush_to_zero();
    prepare_refuses_out_of_range_tone_and_eq();
    neutral_block_reads_the_source_exactly();
    reverse_reads_the_mirrored_source_exactly();
    whole_octaves_halve_and_double_a_one_shot();
    hermite_is_exact_on_frames_and_linear_on_a_ramp();
    ping_pong_reflects_without_repeating_a_boundary_frame();
    later_loop_passes_resume_at_the_loop_point();
    reverse_mirrors_the_loop_point_with_the_region();
    crossfade_gains_hold_constant_power();
    crossfade_overlaps_the_loop_head_and_shortens_the_cycle();
    crossfade_blends_tail_and_head_with_complementary_gains();
    hard_pan_silences_the_far_side_exactly();
    pitched_voice_fades_over_its_last_96_output_frames();
    reversed_voice_publishes_descending_source_frames();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "audio voice dsp tests: PASS\n";
  return 0;
}
