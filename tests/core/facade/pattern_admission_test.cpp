#include <lmdj/audio/prepared_sample_bank.hpp>

#include <iostream>

#include "packages/application-facade/src/pattern_admission_controller.hpp"
#include "tests/core/support/test.hpp"

namespace {
using lmdj::domain::PadSlotId;
using lmdj::domain::PatternEvent;
using lmdj::facade::detail::PatternEventReducer;
using lmdj::facade::detail::PatternOwnedPress;

struct State {
  std::uint64_t generation{};
  std::vector<PatternEvent> events;
  std::map<PadSlotId, PatternOwnedPress> pressed;
  PatternEventReducer reducer(bool quantize = false, std::uint8_t swing = 50) {
    return {1, quantize, swing, generation, events, pressed};
  }
};

void acknowledged_origin_preserves_mid_loop_phase() {
  State state;
  const lmdj::audio::TransportAnchor anchor{1000, 0, 120};
  constexpr std::uint64_t admission_frame = 13000;
  const auto attack = lmdj::audio::raw_tick_at(anchor, 25000);
  const auto release = lmdj::audio::raw_tick_at(anchor, 31000);
  const auto reset_attack = lmdj::audio::raw_tick_at(
      {admission_frame, 0, 120}, 25000);
  LMDJ_CHECK(admission_frame > anchor.runtime_frame);
  LMDJ_CHECK(attack.has_value() && release.has_value());
  LMDJ_CHECK(reset_attack.has_value() && reset_attack.value() == 480);
  // Reducer math only: the production prepared-admission caller is still T1b.
  auto reducer = state.reducer();
  reducer.press({0, 1}, attack.value(), 90, 72);
  LMDJ_CHECK(reducer.release({0, 1}, release.value(), 72));
  LMDJ_CHECK(state.events == std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));
  LMDJ_CHECK(state.pressed.empty());
}

void release_requires_the_owned_correlation() {
  State state;
  auto reducer = state.reducer();
  LMDJ_CHECK(!reducer.release({0, 1}, 120, 40));
  reducer.press({0, 1}, 960, 91, 72);
  const auto retained = reducer.recoverable_tail();
  const auto generation = state.generation;
  LMDJ_CHECK(!reducer.release({0, 1}, 1200, 71));
  LMDJ_CHECK(reducer.recoverable_tail() == retained);
  LMDJ_CHECK(state.generation == generation);
  LMDJ_CHECK(state.pressed.size() == 1);
  LMDJ_CHECK(reducer.release({0, 1}, 1200, 72));
  LMDJ_CHECK(state.events == std::vector<PatternEvent>({{{0, 1}, 960, 240, 91}}));
}

void retrigger_and_terminal_completion_keep_existing_rules() {
  State state;
  auto reducer = state.reducer();
  reducer.press({0, 1}, 960, 90, 10);
  reducer.press({0, 1}, 1080, 100, 11);
  LMDJ_CHECK(state.events == std::vector<PatternEvent>({{{0, 1}, 960, 120, 90}}));
  LMDJ_CHECK(!reducer.release({0, 1}, 1140, 10));
  const auto tail = reducer.recoverable_tail();
  LMDJ_CHECK(state.events.size() == 1 && state.pressed.size() == 1);
  LMDJ_CHECK(tail == std::vector<PatternEvent>({
      {{0, 1}, 960, 120, 90}, {{0, 1}, 1080, 240, 100}}));
  reducer.finalize_unreleased(false);
  LMDJ_CHECK(state.events == tail && state.pressed.size() == 1);
  reducer.finalize_unreleased(true);
  LMDJ_CHECK(state.events == tail && state.pressed.empty());
}

void legacy_release_and_quantization_share_the_same_reducer() {
  State state;
  auto reducer = state.reducer(true, 50);
  reducer.press({0, 2}, 1000, 87);
  LMDJ_CHECK(reducer.release({0, 2}, 1240));
  LMDJ_CHECK(state.events == std::vector<PatternEvent>({{{0, 2}, 960, 240, 87}}));
  const auto generation = state.generation;
  reducer.press({0, 2}, 1000, 87);
  LMDJ_CHECK(reducer.release({0, 2}, 1240));
  LMDJ_CHECK(state.events.size() == 1);
  LMDJ_CHECK(state.generation == generation);
}

void swing_uses_the_existing_odd_sixteenth_grid() {
  State state;
  auto reducer = state.reducer(true, 60);
  reducer.press({0, 3}, 4080, 95);
  LMDJ_CHECK(reducer.release({0, 3}, 4320));
  LMDJ_CHECK(state.events == std::vector<PatternEvent>({{{0, 3}, 288, 240, 95}}));
}

void release_duration_stops_at_the_pattern_end() {
  State state;
  auto reducer = state.reducer();
  reducer.press({0, 3}, 3800, 95);
  LMDJ_CHECK(reducer.release({0, 3}, 4200));
  LMDJ_CHECK(state.events == std::vector<PatternEvent>({{{0, 3}, 3800, 40, 95}}));
}

void multi_bar_onset_does_not_wrap_at_one_bar() {
  State state;
  PatternEventReducer reducer{
      2, false, 50, state.generation, state.events, state.pressed};
  reducer.press({1, 3}, 4000, 95);
  LMDJ_CHECK(reducer.release({1, 3}, 4240));
  LMDJ_CHECK(state.events == std::vector<PatternEvent>({{{1, 3}, 4000, 240, 95}}));
}
}  // namespace

int main() {
  try {
    acknowledged_origin_preserves_mid_loop_phase();
    release_requires_the_owned_correlation();
    retrigger_and_terminal_completion_keep_existing_rules();
    legacy_release_and_quantization_share_the_same_reducer();
    swing_uses_the_existing_odd_sixteenth_grid();
    release_duration_stops_at_the_pattern_end();
    multi_bar_onset_does_not_wrap_at_one_bar();
    std::cout << "pattern event reducer tests: PASS (7 scenarios)\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
