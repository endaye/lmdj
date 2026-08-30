#include <lmdj/audio/master_fx.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <array>
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


int main() {
  try {
    identical_preparation_and_gesture_stream_is_sample_identical();
    quantum_coalesced_gesture_orderings_with_same_values_are_identical();
    repeated_live_streams_use_the_same_chain_code_sample_identically();
    realtime_engine_processes_the_mixed_voice_through_master_fx();
    running_tempo_update_matches_fresh_preparation_at_quantum_boundary();
    midstream_tempo_update_changes_future_boundaries_deterministically();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
