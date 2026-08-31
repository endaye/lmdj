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
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
