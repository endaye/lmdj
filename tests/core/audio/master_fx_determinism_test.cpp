#include <lmdj/audio/master_fx.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <array>
#include <cmath>
#include <cstdint>
#include <exception>
#include <iostream>
#include <optional>
#include <utility>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::EnqueueResult;
using lmdj::audio::FxEnqueueResult;
using lmdj::audio::FxGesture;
using lmdj::audio::FxGestureKind;
using lmdj::audio::MasterFxChain;
using lmdj::audio::MasterFxPreparation;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::TriggerEvent;
using lmdj::domain::PerformanceFx;

std::vector<float> signal(std::size_t frames, std::uint32_t seed) {
  std::vector<float> output(frames);
  for (std::size_t frame = 0; frame < frames; ++frame) {
    const auto integer = static_cast<std::int32_t>(
        (frame * (seed * 2U + 1U) + seed * 13U) % 113U) - 56;
    output[frame] = static_cast<float>(integer) / 80.0F;
  }
  return output;
}

std::pair<std::vector<float>, std::vector<float>> process_chain(
    const std::vector<FxGesture>& gestures) {
  MasterFxChain chain;
  LMDJ_CHECK(chain.prepare(MasterFxPreparation{48'000, 137}).has_value());
  for (const auto gesture : gestures) {
    LMDJ_CHECK(chain.apply_gesture(gesture));
  }
  auto left = signal(12'288, 5);
  auto right = signal(12'288, 19);
  for (std::size_t offset = 0; offset < left.size(); offset += 128) {
    chain.process(left.data() + offset, right.data() + offset, 128);
  }
  return {std::move(left), std::move(right)};
}

std::vector<FxGesture> fully_engaged(std::uint16_t value) {
  std::vector<FxGesture> gestures;
  for (const auto fx : lmdj::audio::kFxChainOrder) {
    gestures.push_back(FxGesture{FxGestureKind::engage, fx, value});
  }
  return gestures;
}

void identical_preparation_and_gesture_stream_is_sample_identical() {
  const auto gestures = fully_engaged(731);
  const auto first = process_chain(gestures);
  const auto second = process_chain(gestures);
  LMDJ_CHECK(first == second);
}

void quantum_coalesced_gesture_orderings_with_same_values_are_identical() {
  std::vector<FxGesture> moved;
  std::vector<FxGesture> direct;
  for (const auto fx : lmdj::audio::kFxChainOrder) {
    moved.push_back(FxGesture{FxGestureKind::engage, fx, 101});
    moved.push_back(FxGesture{FxGestureKind::move, fx, 777});
    moved.push_back(FxGesture{FxGestureKind::move, fx, 777});
    direct.push_back(FxGesture{FxGestureKind::engage, fx, 777});
  }
  LMDJ_CHECK(process_chain(moved) == process_chain(direct));

  std::vector<FxGesture> engaged_then_released;
  for (const auto fx : lmdj::audio::kFxChainOrder) {
    engaged_then_released.push_back(
        FxGesture{FxGestureKind::engage, fx, 900});
    engaged_then_released.push_back(
        FxGesture{FxGestureKind::release, fx, 0});
  }
  LMDJ_CHECK(process_chain(engaged_then_released) == process_chain({}));
}

std::pair<std::array<float, 4'096>, std::array<float, 4'096>> render_live(
    const std::vector<FxGesture>& gestures,
    std::uint16_t prepared_bpm = 137,
    std::optional<std::uint16_t> running_bpm = std::nullopt) {
  RealtimeEngine engine;
  const auto sample = [] {
    std::array<float, 4'096> result{};
    for (std::size_t frame = 0; frame < result.size(); ++frame) {
      result[frame] = static_cast<float>(frame % 97U) / 128.0F;
    }
    return result;
  }();
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(prepared_bpm).has_value());
  LMDJ_CHECK(engine.start().has_value());
  if (running_bpm.has_value()) {
    LMDJ_CHECK(
        engine.enqueue_master_fx_tempo(*running_bpm) ==
        FxEnqueueResult::accepted);
  }
  for (const auto gesture : gestures) {
    LMDJ_CHECK(engine.enqueue_fx_gesture(gesture) == FxEnqueueResult::accepted);
  }
  LMDJ_CHECK(
      engine.enqueue(TriggerEvent{1, 0, 127}) == EnqueueResult::accepted);
  std::array<float, 4'096> left{};
  std::array<float, 4'096> right{};
  for (std::size_t offset = 0; offset < left.size(); offset += 128) {
    engine.render(left.data() + offset, right.data() + offset, 128);
  }
  if (running_bpm.has_value()) {
    LMDJ_CHECK(engine.master_fx_telemetry().current_bpm == *running_bpm);
  }
  return {left, right};
}

void repeated_live_streams_use_the_same_chain_code_sample_identically() {
  const auto gestures = fully_engaged(863);
  LMDJ_CHECK(render_live(gestures) == render_live(gestures));
}

void realtime_engine_processes_the_mixed_voice_through_master_fx() {
  const auto dry = render_live({});
  const auto wet = render_live(fully_engaged(863));
  LMDJ_CHECK(wet != dry);
}

void running_tempo_update_matches_fresh_preparation_at_quantum_boundary() {
  const auto gestures = fully_engaged(1'000);
  const auto updated = render_live(gestures, 120, 123);
  const auto prepared = render_live(gestures, 123);
  LMDJ_CHECK(updated == prepared);
}

std::array<float, 8'192> render_fx_with_midstream_tempo(
    PerformanceFx fx,
    std::optional<std::uint16_t> running_bpm) {
  RealtimeEngine engine;
  std::array<float, 8'192> sample{};
  for (std::size_t frame = 0; frame < sample.size(); ++frame) {
    sample[frame] =
        static_cast<float>(static_cast<std::int32_t>(frame % 83U) - 41) /
        64.0F;
  }
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(120).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue_fx_gesture(FxGesture{
                 FxGestureKind::engage, fx, 1'000}) ==
             FxEnqueueResult::accepted);
  LMDJ_CHECK(
      engine.enqueue(TriggerEvent{1, 0, 127}) == EnqueueResult::accepted);
  std::array<float, 8'192> left{};
  std::array<float, 8'192> right{};
  for (std::size_t offset = 0; offset < left.size(); offset += 128) {
    if (offset == 1'024 && running_bpm.has_value()) {
      LMDJ_CHECK(
          engine.enqueue_master_fx_tempo(*running_bpm) ==
          FxEnqueueResult::accepted);
    }
    engine.render(left.data() + offset, right.data() + offset, 128);
  }
  return left;
}

void midstream_tempo_update_changes_future_boundaries_deterministically() {
  constexpr std::array tempo_locked{
      PerformanceFx::delay,
      PerformanceFx::stutter,
      PerformanceFx::cutter,
  };
  for (const auto fx : tempo_locked) {
    const auto first = render_fx_with_midstream_tempo(fx, 123);
    const auto second = render_fx_with_midstream_tempo(fx, 123);
    const auto unchanged =
        render_fx_with_midstream_tempo(fx, std::nullopt);
    LMDJ_CHECK(first == second);
    LMDJ_CHECK(first != unchanged);
  }
}

}  // namespace

namespace {

using lmdj::audio::FilterGesture;
using lmdj::audio::FilterPhase;
using lmdj::audio::FilterType;

// One explicit integer control stream mixing typed Filter controls with the
// legacy gestures that share the stage (HOLD and legacy Filter ownership).
struct MixedControl {
  bool is_filter;
  FxGesture gesture;
  FilterGesture filter;
};

MixedControl typed(FilterPhase phase, FilterType type, std::uint32_t cutoff_hz,
                   std::uint16_t resonance_milli) {
  return MixedControl{
      true, {}, FilterGesture{phase, {type, cutoff_hz, resonance_milli}}};
}

MixedControl legacy(FxGestureKind kind, std::uint16_t value) {
  return MixedControl{
      false, FxGesture{kind, PerformanceFx::filter, value}, {}};
}

const std::vector<MixedControl>& mixed_stream() {
  static const std::vector<MixedControl> stream{
      typed(FilterPhase::engage, FilterType::low_pass, 800, 250),
      legacy(FxGestureKind::hold_on, 0),
      typed(FilterPhase::release, FilterType::low_pass, 0, 0),
      typed(FilterPhase::move, FilterType::low_pass, 100, 0),
      legacy(FxGestureKind::hold_off, 0),
      typed(FilterPhase::engage, FilterType::band_pass, 1'200, 900),
      typed(FilterPhase::move, FilterType::band_pass, 20'000, 1'000),
      legacy(FxGestureKind::engage, 300),
      typed(FilterPhase::move, FilterType::low_pass, 500, 0),
      legacy(FxGestureKind::release, 0),
      typed(FilterPhase::engage, FilterType::high_pass, 63, 17),
      typed(FilterPhase::release, FilterType::low_pass, 0, 0),
  };
  return stream;
}

std::pair<std::vector<float>, std::vector<float>> process_chain_mixed() {
  MasterFxChain chain;
  LMDJ_CHECK(chain.prepare(MasterFxPreparation{48'000, 137}).has_value());
  auto left = signal(12'288, 5);
  auto right = signal(12'288, 19);
  const auto& stream = mixed_stream();
  std::size_t applied = 0;
  for (std::size_t offset = 0; offset < left.size(); offset += 128) {
    // Two quanta of audio between controls, mirroring the engine pacing.
    if (offset % 256 == 0 && applied < stream.size()) {
      const auto& control = stream[applied];
      if (control.is_filter) {
        static_cast<void>(chain.apply_filter_gesture(control.filter));
      } else {
        static_cast<void>(chain.apply_gesture(control.gesture));
      }
      ++applied;
    }
    chain.process(left.data() + offset, right.data() + offset, 128);
  }
  return {std::move(left), std::move(right)};
}

std::pair<std::array<float, 12'288>, std::array<float, 12'288>>
render_live_mixed() {
  RealtimeEngine engine;
  const auto sample = [] {
    std::array<float, 12'288> result{};
    for (std::size_t frame = 0; frame < result.size(); ++frame) {
      result[frame] = static_cast<float>(frame % 97U) / 128.0F;
    }
    return result;
  }();
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(137).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue(TriggerEvent{1, 0, 127}) == EnqueueResult::accepted);
  std::array<float, 12'288> left{};
  std::array<float, 12'288> right{};
  const auto& stream = mixed_stream();
  std::size_t sent = 0;
  for (std::size_t offset = 0; offset < left.size(); offset += 128) {
    if (offset % 256 == 0 && sent < stream.size()) {
      const auto& control = stream[sent];
      if (control.is_filter) {
        LMDJ_CHECK(engine.enqueue_filter_gesture(control.filter) ==
                   FxEnqueueResult::accepted);
      } else {
        LMDJ_CHECK(engine.enqueue_fx_gesture(control.gesture) ==
                   FxEnqueueResult::accepted);
      }
      ++sent;
    }
    engine.render(left.data() + offset, right.data() + offset, 128);
  }
  return {left, right};
}

// Engine and chain share MasterFxChain code, so two copies agreeing cannot by
// itself prove the DSP correct — that is this parity test's named blind spot.
// The independent anchors are master_fx_test's analytic prototype oracles
// (topology correctness) and the exact golden samples locked here (regression
// identity); the engine/chain agreement below then proves only that the queue
// path applies the same stream the same way.
void mixed_typed_control_stream_is_deterministic_across_engine_and_dsp() {
  const auto first = process_chain_mixed();
  const auto second = process_chain_mixed();
  LMDJ_CHECK(first == second);

  const auto live_first = render_live_mixed();
  const auto live_second = render_live_mixed();
  LMDJ_CHECK(live_first == live_second);

  // The coherent state reached through the real engine equals the shared
  // DSP's state after the same stream: two typed controls are no-ops (a move
  // while frozen, a move while legacy owns the stage) but still consume
  // accepted sequence, exactly like any other accepted control.
  RealtimeEngine engine;
  const auto sample = [] {
    std::array<float, 64> result{};
    result.fill(0.25F);
    return result;
  }();
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(137).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (const auto& control : mixed_stream()) {
    if (control.is_filter) {
      LMDJ_CHECK(engine.enqueue_filter_gesture(control.filter) ==
                 FxEnqueueResult::accepted);
    } else {
      LMDJ_CHECK(engine.enqueue_fx_gesture(control.gesture) ==
                 FxEnqueueResult::accepted);
    }
  }
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  engine.render(left.data(), right.data(), left.size());
  const auto status = engine.filter_control_status();
  LMDJ_CHECK(status.accepted_sequence == 8);
  LMDJ_CHECK(status.applied.sequence == 8);
  LMDJ_CHECK(status.applied.epoch == engine.telemetry().start_epoch);

  MasterFxChain chain;
  LMDJ_CHECK(chain.prepare(MasterFxPreparation{48'000, 137}).has_value());
  for (const auto& control : mixed_stream()) {
    if (control.is_filter) {
      static_cast<void>(chain.apply_filter_gesture(control.filter));
    } else {
      static_cast<void>(chain.apply_gesture(control.gesture));
    }
  }
  const auto chain_state = chain.filter_state();
  const auto& applied = status.applied.state;
  LMDJ_CHECK(applied.mode == chain_state.mode);
  LMDJ_CHECK(applied.engaged == chain_state.engaged);
  LMDJ_CHECK(applied.frozen == chain_state.frozen);
  LMDJ_CHECK(applied.hold == chain_state.hold);
  LMDJ_CHECK(applied.legacy_value == chain_state.legacy_value);
  LMDJ_CHECK(applied.parameters.type == chain_state.parameters.type);
  LMDJ_CHECK(
      applied.parameters.cutoff_hz == chain_state.parameters.cutoff_hz);
  LMDJ_CHECK(applied.parameters.resonance_milli ==
             chain_state.parameters.resonance_milli);
  // Locked end state: independent HP 63 Hz / 1.7% released, legacy scalar
  // back to zero after its release, HOLD off.
  LMDJ_CHECK(chain_state.mode == lmdj::audio::FilterMode::independent);
  LMDJ_CHECK(!chain_state.engaged && !chain_state.frozen &&
             !chain_state.hold);
  LMDJ_CHECK(chain_state.parameters.type == FilterType::high_pass);
  LMDJ_CHECK(chain_state.parameters.cutoff_hz == 63);
  LMDJ_CHECK(chain_state.parameters.resonance_milli == 17);
  LMDJ_CHECK(chain_state.legacy_value == 0);

  // Locked reference samples of the typed stream's chain output. The bypass
  // frame is exactly the raw input (bit-identical bypass); the engaged frames
  // carry a 1e-5 tolerance because the coefficients pass through libm tan/exp,
  // whose last double ulp may differ across platforms — any algorithmic
  // regression moves these samples by orders of magnitude more.
  constexpr std::array<std::pair<std::size_t, float>, 6> golden{{
      {0, 0.112133957F},
      {256, -0.0279778652F},
      {512, 0.0211538225F},
      {1'024, 0.0455697998F},
      {1'408, -0.0162643939F},
      {2'048, 0.374967873F},
  }};
  for (const auto& [frame, expected] : golden) {
    LMDJ_CHECK(std::abs(first.first[frame] - expected) < 0.00001F);
  }
  constexpr auto bypass_frame = std::size_t{4'096};
  LMDJ_CHECK(first.first[bypass_frame] == -0.275000006F);
}

}  // namespace


int main() {
  try {
    identical_preparation_and_gesture_stream_is_sample_identical();
    quantum_coalesced_gesture_orderings_with_same_values_are_identical();
    repeated_live_streams_use_the_same_chain_code_sample_identically();
    realtime_engine_processes_the_mixed_voice_through_master_fx();
    running_tempo_update_matches_fresh_preparation_at_quantum_boundary();
    midstream_tempo_update_changes_future_boundaries_deterministically();
    mixed_typed_control_stream_is_deterministic_across_engine_and_dsp();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
