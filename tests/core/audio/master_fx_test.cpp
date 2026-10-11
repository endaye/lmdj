#include <lmdj/audio/master_fx.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <exception>
#include <iostream>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::FxGesture;
using lmdj::audio::FxGestureKind;
using lmdj::audio::MasterFxChain;
using lmdj::audio::MasterFxPreparation;
using lmdj::domain::PerformanceFx;

constexpr std::uint32_t kSampleRate = 48'000;
constexpr std::uint16_t kBpm = 240;

std::vector<float> signal(std::size_t frames, std::uint32_t seed) {
  std::vector<float> output(frames);
  for (std::size_t frame = 0; frame < frames; ++frame) {
    const auto integer = static_cast<std::int32_t>(
        (frame * (seed * 2U + 1U) + seed * 17U) % 101U) - 50;
    output[frame] = static_cast<float>(integer) / 64.0F;
  }
  return output;
}

bool differs(
    const std::vector<float>& left,
    const std::vector<float>& right,
    const std::vector<float>& original_left,
    const std::vector<float>& original_right) {
  return left != original_left || right != original_right;
}

double energy(const std::vector<float>& signal) {
  double total = 0.0;
  for (const auto sample : signal) {
    total += static_cast<double>(sample) * sample;
  }
  return total;
}

std::vector<float> filtered_signal(
    std::uint16_t value, std::vector<float> input) {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(chain.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::filter, value}));
  auto right = input;
  chain.process(input.data(), right.data(), input.size());
  return input;
}

void fixed_order_and_integer_ladders_are_exact() {
  constexpr std::array expected{
      PerformanceFx::filter,
      PerformanceFx::delay,
      PerformanceFx::reverb,
      PerformanceFx::stutter,
      PerformanceFx::gate,
      PerformanceFx::reverse,
      PerformanceFx::crush,
      PerformanceFx::cutter,
  };
  static_assert(lmdj::audio::kFxChainOrder == expected);

  constexpr std::array<std::uint16_t, 6> stutter_values{
      0, 200, 400, 600, 800, 1'000};
  constexpr std::array<std::uint32_t, 6> stutter_divisors{
      2, 4, 8, 16, 32, 64};
  for (std::size_t index = 0; index < stutter_values.size(); ++index) {
    LMDJ_CHECK(
        lmdj::audio::master_fx_stutter_divisor(stutter_values[index]) ==
        stutter_divisors[index]);
  }

  constexpr std::array<std::uint16_t, 7> cutter_values{
      0, 167, 334, 500, 667, 834, 1'000};
  constexpr std::array<std::uint32_t, 7> cutter_divisors{
      1, 2, 4, 8, 16, 32, 64};
  for (std::size_t index = 0; index < cutter_values.size(); ++index) {
    LMDJ_CHECK(
        lmdj::audio::master_fx_cutter_divisor(cutter_values[index]) ==
        cutter_divisors[index]);
  }

  constexpr auto bar_frames =
      lmdj::audio::master_fx_bar_frames(kSampleRate, 123);
  static_assert(bar_frames == 93'658);
  static_assert(
      lmdj::audio::master_fx_stutter_frames(kSampleRate, 123, 1'000) ==
      bar_frames / 64U);
  static_assert(
      lmdj::audio::master_fx_cutter_frames(kSampleRate, 123, 1'000) ==
      bar_frames / 64U);
  static_assert(
      lmdj::audio::master_fx_delay_frames(kSampleRate, 123, 1'000) ==
      bar_frames / 16U);

  lmdj::audio::detail::MasterFxPeriodAccumulator rational_period;
  rational_period.configure(kSampleRate, 123, 64);
  constexpr std::uint64_t kPeriods = 10'000;
  std::uint64_t accumulated = 0;
  auto saw_floor = false;
  auto saw_ceil = false;
  for (std::uint64_t period = 0; period < kPeriods; ++period) {
    const auto frames = rational_period.next_frames();
    LMDJ_CHECK(frames == bar_frames / 64U ||
               frames == bar_frames / 64U + 1U);
    saw_floor = saw_floor || frames == bar_frames / 64U;
    saw_ceil = saw_ceil || frames == bar_frames / 64U + 1U;
    if (period == 0) {
      LMDJ_CHECK(frames == bar_frames / 64U + 1U);
    }
    accumulated += frames;
  }
  LMDJ_CHECK(saw_floor);
  LMDJ_CHECK(saw_ceil);
  LMDJ_CHECK(
      accumulated ==
      (static_cast<std::uint64_t>(kSampleRate) * 240U * kPeriods +
       123U * 64U - 1U) /
          (123U * 64U));
}

void filter_direction_and_resonance_match_the_locked_mapping() {
  std::vector<float> alternating(4'096);
  for (std::size_t frame = 0; frame < alternating.size(); ++frame) {
    alternating[frame] = frame % 2 == 0 ? 0.5F : -0.5F;
  }
  std::vector<float> constant(4'096, 0.5F);

  const auto low_pass_high_frequency = filtered_signal(0, alternating);
  const auto high_pass_high_frequency = filtered_signal(1'000, alternating);
  LMDJ_CHECK(
      energy(low_pass_high_frequency) < energy(high_pass_high_frequency));

  const auto low_pass_dc = filtered_signal(0, constant);
  const auto high_pass_dc = filtered_signal(1'000, constant);
  LMDJ_CHECK(energy(high_pass_dc) < energy(low_pass_dc));

  std::vector<float> impulse(2'048, 0.0F);
  impulse[0] = 1.0F;
  const auto resonance_sign_changes = [](const std::vector<float>& output) {
    auto sign_changes = 0U;
    auto previous_sign = 0;
    for (const auto sample : output) {
      const auto sign =
          sample > 0.00001F ? 1 : sample < -0.00001F ? -1 : 0;
      if (sign != 0 && previous_sign != 0 && sign != previous_sign) {
        ++sign_changes;
      }
      if (sign != 0) {
        previous_sign = sign;
      }
    }
    return sign_changes;
  };
  LMDJ_CHECK(resonance_sign_changes(filtered_signal(0, impulse)) >= 2);
  LMDJ_CHECK(
      resonance_sign_changes(filtered_signal(1'000, impulse)) >= 2);
}

void repeated_same_value_moves_preserve_dsp_continuity() {
  for (const auto fx : lmdj::audio::kFxChainOrder) {
    MasterFxChain stable;
    MasterFxChain moved;
    LMDJ_CHECK(
        stable.prepare(MasterFxPreparation{kSampleRate, kBpm}).has_value());
    LMDJ_CHECK(
        moved.prepare(MasterFxPreparation{kSampleRate, kBpm}).has_value());
    LMDJ_CHECK(stable.apply_gesture(
        FxGesture{FxGestureKind::engage, fx, 1'000}));
    LMDJ_CHECK(moved.apply_gesture(
        FxGesture{FxGestureKind::engage, fx, 1'000}));

    auto stable_left = signal(8'192, 53);
    auto stable_right = signal(8'192, 59);
    auto moved_left = stable_left;
    auto moved_right = stable_right;
    for (std::size_t offset = 0; offset < stable_left.size(); offset += 128) {
      stable.process(stable_left.data() + offset,
                     stable_right.data() + offset, 128);
      LMDJ_CHECK(moved.apply_gesture(
          FxGesture{FxGestureKind::move, fx, 1'000}));
      moved.process(
          moved_left.data() + offset, moved_right.data() + offset, 128);
    }
    LMDJ_CHECK(moved_left == stable_left);
    LMDJ_CHECK(moved_right == stable_right);
  }
}

bool reengaged_effect_keeps_silence(PerformanceFx fx) {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, kBpm}).has_value());
  LMDJ_CHECK(chain.apply_gesture(
      FxGesture{FxGestureKind::engage, fx, 1'000}));

  std::vector<float> impulse_left(8'192, 0.0F);
  std::vector<float> impulse_right(8'192, 0.0F);
  impulse_left[0] = 1.0F;
  chain.process(
      impulse_left.data(), impulse_right.data(), impulse_left.size());
  LMDJ_CHECK(chain.apply_gesture(
      FxGesture{FxGestureKind::release, fx, 0}));

  std::array<float, 257> released_left{};
  std::array<float, 257> released_right{};
  chain.process(
      released_left.data(), released_right.data(), released_left.size());
  LMDJ_CHECK(std::all_of(
      released_left.begin(), released_left.end(), [](float sample) {
        return sample == 0.0F;
      }));
  LMDJ_CHECK(std::all_of(
      released_right.begin(), released_right.end(), [](float sample) {
        return sample == 0.0F;
      }));

  LMDJ_CHECK(chain.apply_gesture(
      FxGesture{FxGestureKind::engage, fx, 1'000}));
  std::array<float, 4'096> restarted_left{};
  std::array<float, 4'096> restarted_right{};
  chain.process(
      restarted_left.data(), restarted_right.data(), restarted_left.size());
  return std::all_of(
             restarted_left.begin(), restarted_left.end(), [](float sample) {
               return sample == 0.0F;
             }) &&
         std::all_of(
             restarted_right.begin(),
             restarted_right.end(),
             [](float sample) { return sample == 0.0F; });
}

void reverb_reengage_cannot_resurrect_released_audio() {
  LMDJ_CHECK(reengaged_effect_keeps_silence(PerformanceFx::reverb));
}

void delay_reengage_cannot_resurrect_released_audio() {
  LMDJ_CHECK(reengaged_effect_keeps_silence(PerformanceFx::delay));
}

void rational_phase_survives_multiple_quantum_boundary_tempo_changes() {
  lmdj::audio::detail::MasterFxPeriodAccumulator phase;
  phase.configure(kSampleRate, 123, 64);
  constexpr auto denominator =
      static_cast<std::uint64_t>(kSampleRate) * 240U;
  std::uint64_t expected_phase = 0;
  std::uint64_t expected_boundaries = 0;
  std::uint64_t observed_boundaries = 0;
  const auto advance = [&](std::uint16_t bpm, std::uint32_t quanta) {
    phase.set_rate(bpm, 64);
    for (std::uint32_t frame = 0; frame < quanta * 128U; ++frame) {
      expected_phase += static_cast<std::uint64_t>(bpm) * 64U;
      if (expected_phase >= denominator) {
        expected_phase -= denominator;
        ++expected_boundaries;
      }
      if (phase.advance_frame()) {
        ++observed_boundaries;
      }
    }
  };
  advance(123, 17);
  advance(97, 31);
  advance(211, 43);
  advance(123, 1'000);
  LMDJ_CHECK(observed_boundaries == expected_boundaries);
  LMDJ_CHECK(phase.phase_numerator() == expected_phase);
}

void tempo_and_division_transitions_have_golden_boundaries() {
  MasterFxChain delay;
  LMDJ_CHECK(
      delay.prepare(MasterFxPreparation{kSampleRate, 240}).has_value());
  LMDJ_CHECK(delay.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::delay, 0}));
  std::vector<float> delay_left(3'095, 0.0F);
  std::vector<float> delay_right(3'095, 0.0F);
  delay_left[0] = 1.0F;
  delay.process(delay_left.data(), delay_right.data(), 100);
  LMDJ_CHECK(delay.apply_gesture(FxGesture{
      FxGestureKind::move, PerformanceFx::delay, 1'000}));
  delay.process(
      delay_left.data() + 100, delay_right.data() + 100, 2'995);
  LMDJ_CHECK(delay_left[0] == 1.0F);
  LMDJ_CHECK(std::all_of(
      delay_left.begin() + 1, delay_left.begin() + 3'094, [](float sample) {
        return sample == 0.0F;
      }));
  LMDJ_CHECK(delay_left[3'094] == 1.0F);

  MasterFxChain cutter;
  LMDJ_CHECK(
      cutter.prepare(MasterFxPreparation{kSampleRate, 123}).has_value());
  LMDJ_CHECK(cutter.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::cutter, 1'000}));
  std::vector<float> cutter_left(128U * 91U, 1.0F);
  std::vector<float> cutter_right = cutter_left;
  constexpr std::array<std::pair<std::uint32_t, std::uint16_t>, 3>
      transitions{{{17, 97}, {48, 211}, {72, 123}}};
  std::uint64_t expected_phase = 0;
  std::size_t transition_index = 0;
  auto bpm = std::uint16_t{123};
  constexpr auto denominator =
      static_cast<std::uint64_t>(kSampleRate) * 240U;
  for (std::uint32_t quantum = 0; quantum < 91; ++quantum) {
    if (transition_index < transitions.size() &&
        quantum == transitions[transition_index].first) {
      bpm = transitions[transition_index].second;
      LMDJ_CHECK(cutter.set_bpm(bpm));
      ++transition_index;
    }
    cutter.process(
        cutter_left.data() + quantum * 128U,
        cutter_right.data() + quantum * 128U,
        128);
    for (std::uint32_t frame = 0; frame < 128; ++frame) {
      const auto index = quantum * 128U + frame;
      const auto expected = expected_phase >= denominator / 2U ? 0.0F : 1.0F;
      LMDJ_CHECK(cutter_left[index] == expected);
      expected_phase += static_cast<std::uint64_t>(bpm) * 64U;
      if (expected_phase >= denominator) {
        expected_phase -= denominator;
      }
    }
  }
}

void rational_delay_feedback_tracks_each_floor_ceil_period_boundary() {
  MasterFxChain delay;
  LMDJ_CHECK(
      delay.prepare(MasterFxPreparation{kSampleRate, 123}).has_value());
  LMDJ_CHECK(delay.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::delay, 1'000}));

  // Division 16 at 123 BPM advances through 5,854, 5,854, 5,853 and
  // 5,854-frame periods. Put the impulse at the final frame of period one so
  // every floor/ceil transition must keep the feedback aligned to the same
  // musical boundary instead of reviving a skipped tail slot later.
  std::vector<float> left(23'415, 0.0F);
  std::vector<float> right(left.size(), 0.0F);
  left[5'853] = 1.0F;
  delay.process(left.data(), right.data(), left.size());

  for (std::size_t frame = 0; frame < left.size(); ++frame) {
    const auto expected_left = frame == 11'707
                                   ? 1.0F
                               : frame == 23'414 ? 0.1225F
                                                  : 0.0F;
    const auto expected_right = frame == 17'560 ? 0.35F : 0.0F;
    LMDJ_CHECK(std::abs(left[frame] - expected_left) < 0.000001F);
    LMDJ_CHECK(std::abs(right[frame] - expected_right) < 0.000001F);
  }
}

void reference_dsp_golden_vectors_are_exact() {
  MasterFxChain delay;
  LMDJ_CHECK(
      delay.prepare(MasterFxPreparation{kSampleRate, 240}).has_value());
  LMDJ_CHECK(delay.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::delay, 1'000}));
  std::vector<float> delay_left(6'001, 0.0F);
  std::vector<float> delay_right(6'001, 0.0F);
  delay_left[0] = 1.0F;
  delay.process(delay_left.data(), delay_right.data(), delay_left.size());
  LMDJ_CHECK(delay_left[0] == 0.0F);
  LMDJ_CHECK(delay_left[3'000] == 1.0F);
  LMDJ_CHECK(delay_right[6'000] == 0.35F);

  MasterFxChain reverb;
  LMDJ_CHECK(
      reverb.prepare(MasterFxPreparation{kSampleRate, 240}).has_value());
  LMDJ_CHECK(reverb.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::reverb, 1'000}));
  std::vector<float> reverb_left(4'801, 0.0F);
  std::vector<float> reverb_right(4'801, 0.0F);
  reverb_left[0] = 1.0F;
  reverb.process(
      reverb_left.data(), reverb_right.data(), reverb_left.size());
  LMDJ_CHECK(std::abs(reverb_left[0] - 0.35F) < 0.000001F);
  LMDJ_CHECK(reverb_left[2'400] == 1.0F);
  LMDJ_CHECK(reverb_right[4'800] == 0.62F);

  MasterFxChain gate;
  LMDJ_CHECK(
      gate.prepare(MasterFxPreparation{kSampleRate, 240}).has_value());
  LMDJ_CHECK(gate.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::gate, 1'000}));
  std::array<float, 5> gate_left{-0.8F, -0.69F, 0.0F, 0.69F, 0.8F};
  auto gate_right = gate_left;
  gate.process(gate_left.data(), gate_right.data(), gate_left.size());
  constexpr std::array<float, 5> gated{-0.8F, 0.0F, 0.0F, 0.0F, 0.8F};
  LMDJ_CHECK(gate_left == gated);
  LMDJ_CHECK(gate_right == gated);

  MasterFxChain reverse;
  LMDJ_CHECK(
      reverse.prepare(MasterFxPreparation{kSampleRate, 240}).has_value());
  LMDJ_CHECK(reverse.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::reverse, 1'000}));
  constexpr auto segment = 750U;
  std::vector<float> reverse_left(segment * 3U, 0.0F);
  std::vector<float> reverse_right(segment * 3U, 0.0F);
  std::fill(reverse_left.begin(), reverse_left.begin() + segment, 0.1F);
  std::fill(
      reverse_left.begin() + segment,
      reverse_left.begin() + segment * 2U,
      0.2F);
  std::fill(reverse_left.begin() + segment * 2U, reverse_left.end(), 0.3F);
  reverse_right = reverse_left;
  reverse.process(
      reverse_left.data(), reverse_right.data(), reverse_left.size());
  LMDJ_CHECK(reverse_left[0] == 0.1F);
  LMDJ_CHECK(reverse_left[segment] == 0.1F);
  LMDJ_CHECK(reverse_left[segment * 2U] == 0.2F);

  MasterFxChain crush;
  LMDJ_CHECK(
      crush.prepare(MasterFxPreparation{kSampleRate, 240}).has_value());
  LMDJ_CHECK(crush.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::crush, 1'000}));
  std::array<float, 64> crush_left{};
  crush_left.fill(-0.5F);
  std::fill(crush_left.begin(), crush_left.begin() + 32, 0.5F);
  auto crush_right = crush_left;
  crush.process(crush_left.data(), crush_right.data(), crush_left.size());
  for (std::size_t frame = 0; frame < 32; ++frame) {
    LMDJ_CHECK(std::abs(crush_left[frame] - 4.0F / 7.0F) < 0.000001F);
  }
  for (std::size_t frame = 32; frame < 64; ++frame) {
    LMDJ_CHECK(std::abs(crush_left[frame] + 4.0F / 7.0F) < 0.000001F);
  }
}

void every_effect_changes_signal_and_release_is_exact_passthrough() {
  constexpr std::array<std::uint16_t, 8> values{
      1'000, 1'000, 1'000, 1'000, 1'000, 1'000, 1'000, 1'000};
  for (std::size_t index = 0; index < lmdj::audio::kFxChainOrder.size();
       ++index) {
    MasterFxChain chain;
    LMDJ_CHECK(chain.prepare(MasterFxPreparation{kSampleRate, kBpm})
                   .has_value());
    const auto fx = lmdj::audio::kFxChainOrder[index];
    LMDJ_CHECK(chain.apply_gesture(
        FxGesture{FxGestureKind::engage, fx, values[index]}));

    auto left = signal(8'192, 3);
    auto right = signal(8'192, 11);
    const auto original_left = left;
    const auto original_right = right;
    chain.process(left.data(), right.data(), left.size());
    LMDJ_CHECK(differs(left, right, original_left, original_right));

    LMDJ_CHECK(chain.apply_gesture(
        FxGesture{FxGestureKind::release, fx, 0}));
    left = signal(257, 17);
    right = signal(257, 23);
    const auto released_left = left;
    const auto released_right = right;
    chain.process(left.data(), right.data(), left.size());
    LMDJ_CHECK(left == released_left);
    LMDJ_CHECK(right == released_right);
  }
}

void filter_midpoint_is_bit_identical_bypass() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(chain.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::filter, 500}));
  auto left = signal(1'024, 7);
  auto right = signal(1'024, 13);
  const auto original_left = left;
  const auto original_right = right;
  chain.process(left.data(), right.data(), left.size());
  LMDJ_CHECK(left == original_left);
  LMDJ_CHECK(right == original_right);

  std::array<float, 2> overrange_left{-1.25F, 1.25F};
  std::array<float, 2> overrange_right{1.5F, -1.5F};
  const auto exact_overrange_left = overrange_left;
  const auto exact_overrange_right = overrange_right;
  chain.process(
      overrange_left.data(), overrange_right.data(), overrange_left.size());
  LMDJ_CHECK(overrange_left == exact_overrange_left);
  LMDJ_CHECK(overrange_right == exact_overrange_right);
}

void global_hold_freezes_releases_and_hold_off_releases_every_effect() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  for (const auto fx : lmdj::audio::kFxChainOrder) {
    LMDJ_CHECK(chain.apply_gesture(
        FxGesture{FxGestureKind::engage, fx, 1'000}));
  }
  LMDJ_CHECK(chain.apply_gesture(
      FxGesture{FxGestureKind::hold_on, PerformanceFx::filter, 0}));
  for (const auto fx : lmdj::audio::kFxChainOrder) {
    LMDJ_CHECK(chain.apply_gesture(
        FxGesture{FxGestureKind::release, fx, 0}));
  }

  auto held_left = signal(8'192, 29);
  auto held_right = signal(8'192, 31);
  const auto dry_left = held_left;
  const auto dry_right = held_right;
  chain.process(held_left.data(), held_right.data(), held_left.size());
  LMDJ_CHECK(differs(held_left, held_right, dry_left, dry_right));

  LMDJ_CHECK(chain.apply_gesture(
      FxGesture{FxGestureKind::hold_off, PerformanceFx::filter, 0}));
  auto released_left = signal(513, 37);
  auto released_right = signal(513, 41);
  const auto exact_left = released_left;
  const auto exact_right = released_right;
  chain.process(
      released_left.data(), released_right.data(), released_left.size());
  LMDJ_CHECK(released_left == exact_left);
  LMDJ_CHECK(released_right == exact_right);
}

void global_hold_freezes_an_engaged_zero_value() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(chain.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::filter, 0}));
  LMDJ_CHECK(chain.apply_gesture(
      FxGesture{FxGestureKind::hold_on, PerformanceFx::filter, 0}));
  LMDJ_CHECK(chain.apply_gesture(FxGesture{
      FxGestureKind::release, PerformanceFx::filter, 0}));

  auto left = signal(1'024, 43);
  auto right = signal(1'024, 47);
  const auto dry_left = left;
  const auto dry_right = right;
  chain.process(left.data(), right.data(), left.size());
  LMDJ_CHECK(differs(left, right, dry_left, dry_right));
}

using lmdj::audio::FilterMode;
using lmdj::audio::FilterParameters;
using lmdj::audio::FilterPhase;
using lmdj::audio::FilterType;
using lmdj::audio::FilterGesture;

// Independent oracle: the analog SVF prototype's magnitude under the bilinear
// frequency warp, derived from the transfer functions, not from the chain's
// per-sample recurrence. Named blind spot: both sides share the specified
// resonance-to-Q mapping (that mapping is the product specification), so a
// defect in that formula itself is out of this test's reach; every topology,
// state-update, output-selection and scaling defect is caught.
double analytic_prototype_gain(
    FilterType type,
    double frequency_hz,
    double cutoff_hz,
    std::uint16_t resonance_milli) {
  const auto warp = [](double hz) {
    return std::tan(3.14159265358979323846 * hz / 48'000.0);
  };
  const auto u = warp(frequency_hz) / warp(cutoff_hz);
  const auto log_q =
      -0.34657359027997265 +
      2.6491586533460524 * (static_cast<double>(resonance_milli) / 1'000.0);
  const auto k = std::exp(-log_q);
  const auto denominator = std::hypot(1.0 - u * u, u * k);
  switch (type) {
    case FilterType::low_pass:
      return 1.0 / denominator;
    case FilterType::high_pass:
      return u * u / denominator;
    case FilterType::band_pass:
      return u * k / denominator;
  }
  return 0.0;
}

double measured_steady_gain(FilterParameters parameters, double frequency_hz) {
  constexpr double amplitude = 0.05;
  constexpr std::size_t frames = 48'000;
  constexpr std::size_t warmup = 24'000;
  constexpr auto pi = 3.14159265358979323846;
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(chain.apply_filter_gesture(
      FilterGesture{FilterPhase::engage, parameters}));
  std::vector<float> left(frames);
  for (std::size_t frame = 0; frame < frames; ++frame) {
    left[frame] = static_cast<float>(
        amplitude *
        std::sin(2.0 * pi * frequency_hz *
                 static_cast<double>(frame) / 48'000.0));
  }
  auto right = left;
  chain.process(left.data(), right.data(), frames);
  auto sine = 0.0;
  auto cosine = 0.0;
  for (std::size_t frame = warmup; frame < frames; ++frame) {
    const auto phase = 2.0 * pi * frequency_hz *
                       static_cast<double>(frame) / 48'000.0;
    sine += static_cast<double>(left[frame]) * std::sin(phase);
    cosine += static_cast<double>(left[frame]) * std::cos(phase);
  }
  return 2.0 * std::hypot(sine, cosine) /
         (static_cast<double>(frames - warmup) * amplitude);
}

void expect_prototype_gain(
    FilterType type,
    double cutoff_hz,
    std::uint16_t resonance_milli,
    double frequency_hz) {
  const auto expected = analytic_prototype_gain(
      type, frequency_hz, cutoff_hz, resonance_milli);
  const auto measured = measured_steady_gain(
      FilterParameters{type, static_cast<std::uint32_t>(cutoff_hz),
                       resonance_milli},
      frequency_hz);
  const auto tolerance = 0.01 * expected + 0.002;
  if (std::abs(measured - expected) > tolerance) {
    std::cerr << "independent filter gain mismatch: type "
              << static_cast<int>(type) << " cutoff " << cutoff_hz
              << " resonance " << resonance_milli << " frequency "
              << frequency_hz << " expected " << expected << " measured "
              << measured << '\n';
    LMDJ_CHECK(false);
  }
}

void independent_filter_response_matches_the_analytic_prototype() {
  for (const auto type :
       {FilterType::low_pass, FilterType::high_pass, FilterType::band_pass}) {
    for (const double frequency : {100.0, 1'000.0, 10'000.0}) {
      expect_prototype_gain(type, 1'000.0, 0, frequency);
    }
  }
  // Resonance peak: LP/HP reach Q at the cutoff, BP stays unity at center.
  expect_prototype_gain(FilterType::low_pass, 1'000.0, 1'000, 1'000.0);
  expect_prototype_gain(FilterType::low_pass, 1'000.0, 1'000, 100.0);
  expect_prototype_gain(FilterType::high_pass, 1'000.0, 500, 1'000.0);
  expect_prototype_gain(FilterType::band_pass, 4'000.0, 500, 400.0);
  expect_prototype_gain(FilterType::band_pass, 4'000.0, 500, 4'000.0);
  expect_prototype_gain(FilterType::band_pass, 4'000.0, 500, 16'000.0);
  // Range edges keep the analytic shape; 20 kHz is not lowered.
  expect_prototype_gain(FilterType::high_pass, 20.0, 0, 20.0);
  expect_prototype_gain(FilterType::high_pass, 20.0, 0, 1'000.0);
  expect_prototype_gain(FilterType::low_pass, 20'000.0, 1'000, 20'000.0);
  expect_prototype_gain(FilterType::low_pass, 20'000.0, 0, 100.0);
}

void independent_filter_off_is_bit_identical_bypass() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  const auto initial = chain.filter_state();
  LMDJ_CHECK(initial.mode == FilterMode::independent);
  LMDJ_CHECK(!initial.engaged && !initial.frozen && !initial.hold);
  LMDJ_CHECK(initial.parameters.type == FilterType::low_pass);
  LMDJ_CHECK(initial.parameters.cutoff_hz == 20'000);
  LMDJ_CHECK(initial.parameters.resonance_milli == 0);

  auto left = signal(1'024, 7);
  auto right = signal(1'024, 13);
  const auto original_left = left;
  const auto original_right = right;
  chain.process(left.data(), right.data(), left.size());
  LMDJ_CHECK(left == original_left);
  LMDJ_CHECK(right == original_right);

  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 800, 250}}));
  chain.process(left.data(), right.data(), left.size());
  LMDJ_CHECK(differs(left, right, original_left, original_right));

  LMDJ_CHECK(chain.apply_filter_gesture(
      FilterGesture{FilterPhase::release, {}}));
  const auto released = chain.filter_state();
  LMDJ_CHECK(!released.engaged && !released.frozen);
  // The tuple is retained for readback after release.
  LMDJ_CHECK(released.parameters.type == FilterType::low_pass);
  LMDJ_CHECK(released.parameters.cutoff_hz == 800);
  LMDJ_CHECK(released.parameters.resonance_milli == 250);

  // After the 96-frame wet ramp the bypass is bit-identical again.
  left = signal(1'024, 71);
  right = signal(1'024, 73);
  chain.process(left.data(), right.data(), left.size());
  left = signal(1'024, 79);
  right = signal(1'024, 83);
  const auto exact_left = left;
  const auto exact_right = right;
  chain.process(left.data(), right.data(), left.size());
  LMDJ_CHECK(left == exact_left);
  LMDJ_CHECK(right == exact_right);
}

void independent_filter_single_parameter_moves_preserve_the_other_two() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::high_pass, 800, 250}}));

  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::move, {FilterType::high_pass, 1'200, 250}}));
  auto state = chain.filter_state();
  LMDJ_CHECK(state.parameters.cutoff_hz == 1'200);
  LMDJ_CHECK(state.parameters.type == FilterType::high_pass);
  LMDJ_CHECK(state.parameters.resonance_milli == 250);

  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::move, {FilterType::band_pass, 1'200, 250}}));
  state = chain.filter_state();
  LMDJ_CHECK(state.parameters.type == FilterType::band_pass);
  LMDJ_CHECK(state.parameters.cutoff_hz == 1'200);
  LMDJ_CHECK(state.parameters.resonance_milli == 250);

  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::move, {FilterType::band_pass, 1'200, 900}}));
  state = chain.filter_state();
  LMDJ_CHECK(state.parameters.resonance_milli == 900);
  LMDJ_CHECK(state.parameters.type == FilterType::band_pass);
  LMDJ_CHECK(state.parameters.cutoff_hz == 1'200);

  // A move without an engaged independent gesture is refused, not applied.
  MasterFxChain idle;
  LMDJ_CHECK(
      idle.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(!idle.apply_filter_gesture(FilterGesture{
      FilterPhase::move, {FilterType::low_pass, 100, 0}}));
  LMDJ_CHECK(idle.filter_state().parameters.cutoff_hz == 20'000);

  // Same-tuple moves preserve DSP continuity, as with the legacy branch.
  MasterFxChain stable;
  MasterFxChain moved;
  LMDJ_CHECK(
      stable.prepare(MasterFxPreparation{kSampleRate, kBpm}).has_value());
  LMDJ_CHECK(
      moved.prepare(MasterFxPreparation{kSampleRate, kBpm}).has_value());
  const FilterParameters tuple{FilterType::low_pass, 700, 400};
  LMDJ_CHECK(stable.apply_filter_gesture(
      FilterGesture{FilterPhase::engage, tuple}));
  LMDJ_CHECK(moved.apply_filter_gesture(
      FilterGesture{FilterPhase::engage, tuple}));
  auto stable_left = signal(8'192, 53);
  auto stable_right = signal(8'192, 59);
  auto moved_left = stable_left;
  auto moved_right = stable_right;
  for (std::size_t offset = 0; offset < stable_left.size(); offset += 128) {
    stable.process(stable_left.data() + offset,
                   stable_right.data() + offset, 128);
    LMDJ_CHECK(moved.apply_filter_gesture(
        FilterGesture{FilterPhase::move, tuple}));
    moved.process(
        moved_left.data() + offset, moved_right.data() + offset, 128);
  }
  LMDJ_CHECK(moved_left == stable_left);
  LMDJ_CHECK(moved_right == stable_right);
}

void independent_filter_extremes_stay_finite_and_stable() {
  for (const auto type :
       {FilterType::low_pass, FilterType::high_pass, FilterType::band_pass}) {
    for (const std::uint32_t cutoff : {20U, 20'000U}) {
      for (const std::uint16_t resonance : {0, 1'000}) {
        MasterFxChain chain;
        LMDJ_CHECK(chain.prepare(MasterFxPreparation{kSampleRate, 120})
                       .has_value());
        LMDJ_CHECK(chain.apply_filter_gesture(
            FilterGesture{FilterPhase::engage, {type, cutoff, resonance}}));
        auto left = signal(48'000, 101);
        auto right = signal(48'000, 103);
        for (auto& sample : left) {
          sample *= 1.2F;
        }
        chain.process(left.data(), right.data(), left.size());
        auto finite = true;
        for (std::size_t frame = 0; frame < left.size(); ++frame) {
          finite = finite && std::isfinite(left[frame]) &&
                   std::isfinite(right[frame]);
        }
        LMDJ_CHECK(finite);
        // Two seconds of silence decay any resonance tail toward zero.
        std::vector<float> silence_left(96'000, 0.0F);
        std::vector<float> silence_right(96'000, 0.0F);
        chain.process(
            silence_left.data(), silence_right.data(), silence_left.size());
        auto tail = 0.0F;
        for (std::size_t frame = silence_left.size() - 96;
             frame < silence_left.size();
             ++frame) {
          tail = std::max(
              tail, std::max(std::abs(silence_left[frame]),
                             std::abs(silence_right[frame])));
        }
        LMDJ_CHECK(tail < 0.01F);
      }
    }
  }
}

void legacy_gestures_take_over_and_legacy_release_owns_only_legacy() {
  // Legacy engage takes over the single stage with legacy semantics.
  MasterFxChain takeover;
  MasterFxChain legacy_only;
  LMDJ_CHECK(
      takeover.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(
      legacy_only.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(takeover.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 800, 250}}));
  {
    auto warmup_left = signal(2'048, 3);
    auto warmup_right = signal(2'048, 5);
    takeover.process(
        warmup_left.data(), warmup_right.data(), warmup_left.size());
  }
  LMDJ_CHECK(takeover.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::filter, 250}));
  LMDJ_CHECK(legacy_only.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::filter, 250}));
  const auto state = takeover.filter_state();
  LMDJ_CHECK(state.mode == FilterMode::legacy);
  LMDJ_CHECK(state.engaged && state.legacy_value == 250);
  auto takeover_left = signal(8'192, 11);
  auto takeover_right = signal(8'192, 17);
  auto legacy_left = takeover_left;
  auto legacy_right = takeover_right;
  takeover.process(
      takeover_left.data(), takeover_right.data(), takeover_left.size());
  legacy_only.process(
      legacy_left.data(), legacy_right.data(), legacy_left.size());
  LMDJ_CHECK(takeover_left == legacy_left);
  LMDJ_CHECK(takeover_right == legacy_right);

  // A legacy move during independent activity takes over as legacy too.
  MasterFxChain move_takeover;
  LMDJ_CHECK(
      move_takeover.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(move_takeover.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::high_pass, 2'000, 100}}));
  LMDJ_CHECK(move_takeover.apply_gesture(FxGesture{
      FxGestureKind::move, PerformanceFx::filter, 700}));
  const auto moved_state = move_takeover.filter_state();
  LMDJ_CHECK(moved_state.mode == FilterMode::legacy);
  LMDJ_CHECK(moved_state.engaged && moved_state.legacy_value == 700);

  // A delayed legacy release must not kill the independent gesture.
  MasterFxChain released;
  MasterFxChain untouched;
  LMDJ_CHECK(
      released.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(
      untouched.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  const FilterParameters tuple{FilterType::low_pass, 500, 600};
  LMDJ_CHECK(released.apply_filter_gesture(
      FilterGesture{FilterPhase::engage, tuple}));
  LMDJ_CHECK(untouched.apply_filter_gesture(
      FilterGesture{FilterPhase::engage, tuple}));
  LMDJ_CHECK(released.apply_gesture(FxGesture{
      FxGestureKind::release, PerformanceFx::filter, 0}));
  const auto released_state = released.filter_state();
  LMDJ_CHECK(released_state.mode == FilterMode::independent);
  LMDJ_CHECK(released_state.engaged);
  auto released_left = signal(4'096, 23);
  auto released_right = signal(4'096, 29);
  auto untouched_left = released_left;
  auto untouched_right = released_right;
  released.process(
      released_left.data(), released_right.data(), released_left.size());
  untouched.process(
      untouched_left.data(), untouched_right.data(), untouched_left.size());
  LMDJ_CHECK(released_left == untouched_left);
  LMDJ_CHECK(released_right == untouched_right);
}

void independent_release_freezes_under_hold_and_hold_off_bypasses() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 300, 800}}));
  LMDJ_CHECK(chain.apply_gesture(
      FxGesture{FxGestureKind::hold_on, PerformanceFx::filter, 0}));
  LMDJ_CHECK(chain.apply_filter_gesture(
      FilterGesture{FilterPhase::release, {}}));
  const auto frozen = chain.filter_state();
  LMDJ_CHECK(frozen.mode == FilterMode::independent);
  LMDJ_CHECK(!frozen.engaged && frozen.frozen && frozen.hold);

  auto left = signal(8'192, 31);
  auto right = signal(8'192, 37);
  const auto dry_left = left;
  const auto dry_right = right;
  chain.process(left.data(), right.data(), left.size());
  LMDJ_CHECK(differs(left, right, dry_left, dry_right));

  LMDJ_CHECK(chain.apply_gesture(
      FxGesture{FxGestureKind::hold_off, PerformanceFx::filter, 0}));
  const auto cleared = chain.filter_state();
  LMDJ_CHECK(!cleared.frozen && !cleared.engaged && !cleared.hold);
  left = signal(1'024, 41);
  right = signal(1'024, 43);
  chain.process(left.data(), right.data(), left.size());
  left = signal(1'024, 47);
  right = signal(1'024, 53);
  const auto exact_left = left;
  const auto exact_right = right;
  chain.process(left.data(), right.data(), left.size());
  LMDJ_CHECK(left == exact_left);
  LMDJ_CHECK(right == exact_right);
}

void invalid_independent_filter_parameters_are_refused() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(!chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage,
      {static_cast<FilterType>(7), 800, 0}}));
  LMDJ_CHECK(!chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 19, 0}}));
  LMDJ_CHECK(!chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 20'001, 0}}));
  LMDJ_CHECK(!chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 800, 1'001}}));
  const auto state = chain.filter_state();
  LMDJ_CHECK(state.mode == FilterMode::independent && !state.engaged);
  LMDJ_CHECK(state.parameters.cutoff_hz == 20'000);
}

MasterFxChain make_settling_chain() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 800, 250}}));
  std::array<float, 128> warm_left{};
  std::array<float, 128> warm_right{};
  warm_left.fill(0.5F);
  warm_right.fill(0.5F);
  chain.process(warm_left.data(), warm_right.data(), warm_left.size());
  LMDJ_CHECK(chain.apply_filter_gesture(
      FilterGesture{FilterPhase::release, {}}));
  return chain;
}

void independent_release_settling_never_clamps_settled_dry_frames() {
  // A release whose 96-frame wet ramp completes mid-block: frames past the
  // settled point are dry and must stay bit-identical to the input — the
  // filter writes nothing there and no clamp may touch them — and the output
  // must not depend on how the render is split into blocks.
  auto chain = make_settling_chain();
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  left.fill(1.5F);
  right.fill(-1.5F);
  chain.process(left.data(), right.data(), left.size());
  // The wet ramp decrements 96 → 0 across the block; the settled frames are
  // bit-identical dry, never clamped to ±1.
  for (std::size_t frame = 95; frame < left.size(); ++frame) {
    LMDJ_CHECK(left[frame] == 1.5F);
    LMDJ_CHECK(right[frame] == -1.5F);
  }
  // Frames the filter did process stay clamped exactly as before.
  for (std::size_t frame = 0; frame < 95; ++frame) {
    LMDJ_CHECK(std::abs(left[frame]) <= 1.0F);
    LMDJ_CHECK(std::abs(right[frame]) <= 1.0F);
  }
  std::array<float, 128> next_left{};
  std::array<float, 128> next_right{};
  next_left.fill(1.5F);
  next_right.fill(-1.5F);
  chain.process(next_left.data(), next_right.data(), next_left.size());
  for (std::size_t frame = 0; frame < next_left.size(); ++frame) {
    LMDJ_CHECK(next_left[frame] == 1.5F);
    LMDJ_CHECK(next_right[frame] == -1.5F);
  }

  // 96 + 32 must produce exactly the same output as one 128-frame render.
  auto split = make_settling_chain();
  std::array<float, 128> split_left{};
  std::array<float, 128> split_right{};
  split_left.fill(1.5F);
  split_right.fill(-1.5F);
  split.process(split_left.data(), split_right.data(), 96);
  split.process(split_left.data() + 96, split_right.data() + 96, 32);
  auto whole = make_settling_chain();
  std::array<float, 128> whole_left{};
  std::array<float, 128> whole_right{};
  whole_left.fill(1.5F);
  whole_right.fill(-1.5F);
  whole.process(whole_left.data(), whole_right.data(), whole_left.size());
  LMDJ_CHECK(split_left == whole_left);
  LMDJ_CHECK(split_right == whole_right);
}

void typed_engage_after_legacy_takeover_restarts_the_wet_gate() {
  MasterFxChain chain;
  LMDJ_CHECK(
      chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 1'000, 0}}));
  std::array<float, 128> warm_left{};
  std::array<float, 128> warm_right{};
  warm_left.fill(0.25F);
  warm_right.fill(0.25F);
  chain.process(warm_left.data(), warm_right.data(), warm_left.size());
  // Legacy neutral takeover of the single stage.
  LMDJ_CHECK(chain.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::filter, 500}));
  LMDJ_CHECK(chain.filter_state().mode == FilterMode::legacy);
  // Typed re-engage with the same tuple must restart the wet gate from zero.
  LMDJ_CHECK(chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 1'000, 0}}));
  std::array<float, 1> left{0.25F};
  std::array<float, 1> right{0.25F};
  chain.process(left.data(), right.data(), 1);

  // Independent closed-form expectation for a fresh gate: wet = 1/96,
  // registers reset, LP selects v2 = a3 * x with a-coefficients from
  // g = tan(pi * 1000 / 48000) and k = sqrt(2) (0% resonance). Named blind
  // spot: the coefficient formulas are shared with the implementation (they
  // are the specification); the wet-gate restart this test pins is not — a
  // stale gate gives 0.000979 instead of 0.247406.
  const auto g = std::tan(3.14159265358979323846 * 1000.0 / 48'000.0);
  const auto k = std::sqrt(2.0);
  const auto a1 = 1.0 / (1.0 + g * (g + k));
  const auto a3 = g * g * a1;
  const auto expected = 0.25 + (a3 * 0.25 - 0.25) / 96.0;
  LMDJ_CHECK(std::abs(static_cast<double>(left[0]) - expected) < 0.000001);
  LMDJ_CHECK(std::abs(static_cast<double>(right[0]) - expected) < 0.000001);

  // Equivalence with the equivalent fresh-gate baseline: engage, release,
  // re-engage with the same tuple and coefficient state, no legacy interlude.
  MasterFxChain baseline;
  LMDJ_CHECK(
      baseline.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
  LMDJ_CHECK(baseline.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 1'000, 0}}));
  auto base_left = warm_left;
  auto base_right = warm_right;
  baseline.process(base_left.data(), base_right.data(), base_left.size());
  LMDJ_CHECK(baseline.apply_filter_gesture(
      FilterGesture{FilterPhase::release, {}}));
  baseline.process(base_left.data(), base_right.data(), base_left.size());
  LMDJ_CHECK(baseline.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 1'000, 0}}));
  std::array<float, 1> base_frame_left{0.25F};
  std::array<float, 1> base_frame_right{0.25F};
  baseline.process(
      base_frame_left.data(), base_frame_right.data(), 1);
  LMDJ_CHECK(left[0] == base_frame_left[0]);
  LMDJ_CHECK(right[0] == base_frame_right[0]);
}

void typed_admission_refuses_non_realtime_sample_rates_without_state_change() {
  MasterFxChain chain;
  // Legacy preparation at other rates remains valid by design.
  LMDJ_CHECK(chain.prepare(MasterFxPreparation{32'000, 120}).has_value());
  const auto before = chain.filter_state();
  LMDJ_CHECK(!chain.apply_filter_gesture(FilterGesture{
      FilterPhase::engage, {FilterType::low_pass, 20'000, 0}}));
  LMDJ_CHECK(!chain.apply_filter_gesture(FilterGesture{
      FilterPhase::move, {FilterType::low_pass, 1'000, 500}}));
  const auto after = chain.filter_state();
  LMDJ_CHECK(after.mode == before.mode && after.engaged == before.engaged &&
             after.frozen == before.frozen && after.hold == before.hold &&
             after.legacy_value == before.legacy_value &&
             after.parameters.type == before.parameters.type &&
             after.parameters.cutoff_hz == before.parameters.cutoff_hz &&
             after.parameters.resonance_milli ==
                 before.parameters.resonance_milli);

  // Release after the rejections is still accepted; nothing is stuck.
  LMDJ_CHECK(chain.apply_filter_gesture(
      FilterGesture{FilterPhase::release, {}}));
  const auto released = chain.filter_state();
  LMDJ_CHECK(!released.engaged && !released.frozen);
  auto left = signal(1'024, 7);
  auto right = signal(1'024, 13);
  const auto dry_left = left;
  const auto dry_right = right;
  chain.process(left.data(), right.data(), left.size());
  LMDJ_CHECK(left == dry_left);
  LMDJ_CHECK(right == dry_right);

  // The legacy branch at the same non-48k preparation still processes.
  LMDJ_CHECK(chain.apply_gesture(FxGesture{
      FxGestureKind::engage, PerformanceFx::filter, 300}));
  auto legacy_left = signal(2'048, 3);
  auto legacy_right = signal(2'048, 11);
  const auto original_left = legacy_left;
  const auto original_right = legacy_right;
  chain.process(
      legacy_left.data(), legacy_right.data(), legacy_left.size());
  LMDJ_CHECK(differs(legacy_left, legacy_right, original_left,
                     original_right));
}

void typed_filter_at_48k_stays_finite_at_the_documented_corners() {
  // The P2-A probe shape: constant 0.25 input through typed engagements at
  // the documented corners — 20 kHz / 0% (the 32 kHz NaN repro's intended
  // 48 kHz behavior), 20 Hz / 0%, and 20 kHz / 100%.
  for (const auto parameters : {
           FilterParameters{FilterType::low_pass, 20'000, 0},
           FilterParameters{FilterType::low_pass, 20, 0},
           FilterParameters{FilterType::low_pass, 20'000, 1'000},
       }) {
    MasterFxChain chain;
    LMDJ_CHECK(
        chain.prepare(MasterFxPreparation{kSampleRate, 120}).has_value());
    LMDJ_CHECK(chain.apply_filter_gesture(
        FilterGesture{FilterPhase::engage, parameters}));
    std::array<float, 2'048> left{};
    std::array<float, 2'048> right{};
    left.fill(0.25F);
    right.fill(0.25F);
    chain.process(left.data(), right.data(), left.size());
    for (std::size_t frame = 0; frame < left.size(); ++frame) {
      LMDJ_CHECK(std::isfinite(left[frame]));
      LMDJ_CHECK(std::isfinite(right[frame]));
    }
  }
}

}  // namespace

int main() {
  try {
    fixed_order_and_integer_ladders_are_exact();
    filter_direction_and_resonance_match_the_locked_mapping();
    repeated_same_value_moves_preserve_dsp_continuity();
    delay_reengage_cannot_resurrect_released_audio();
    reverb_reengage_cannot_resurrect_released_audio();
    rational_phase_survives_multiple_quantum_boundary_tempo_changes();
    tempo_and_division_transitions_have_golden_boundaries();
    rational_delay_feedback_tracks_each_floor_ceil_period_boundary();
    reference_dsp_golden_vectors_are_exact();
    every_effect_changes_signal_and_release_is_exact_passthrough();
    filter_midpoint_is_bit_identical_bypass();
    global_hold_freezes_releases_and_hold_off_releases_every_effect();
    global_hold_freezes_an_engaged_zero_value();
    independent_filter_response_matches_the_analytic_prototype();
    independent_filter_off_is_bit_identical_bypass();
    independent_filter_single_parameter_moves_preserve_the_other_two();
    independent_filter_extremes_stay_finite_and_stable();
    legacy_gestures_take_over_and_legacy_release_owns_only_legacy();
    independent_release_freezes_under_hold_and_hold_off_bypasses();
    invalid_independent_filter_parameters_are_refused();
    independent_release_settling_never_clamps_settled_dry_frames();
    typed_engage_after_legacy_takeover_restarts_the_wet_gate();
    typed_admission_refuses_non_realtime_sample_rates_without_state_change();
    typed_filter_at_48k_stays_finite_at_the_documented_corners();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
