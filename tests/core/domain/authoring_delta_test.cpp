#include <iostream>
#include <limits>

#include <lmdj/domain/authoring_delta.hpp>
#include "tests/core/support/candidate_adoption.hpp"

namespace {
using namespace lmdj::test::candidate;
void round_trip() {
  const auto before = project();
  auto edited = apply(before, command(), {}).value().state;
  edited.bpm = 99;
  edited.quantize_enabled = !before.quantize_enabled;
  edited.swing_percent = 64;
  edited.banks[0][2].playback.gain_millidb = -6000;
  const auto delta = authoring_difference(before, edited).value();
  const auto reversed = reverse_authoring_delta(delta);
  const auto undone = apply(edited, ApplyAuthoringDelta{{CommandId{uuid(80)}, edited.revision}, reversed}, {});
  LMDJ_CHECK(undone.has_value());
  auto expected = before;
  expected.contract = edited.contract;
  expected.revision = edited.revision + 1;
  LMDJ_CHECK(undone.value().state == expected);
  const auto redone = apply(expected, ApplyAuthoringDelta{{CommandId{uuid(81)}, expected.revision}, delta}, {});
  LMDJ_CHECK(redone.has_value());
  edited.revision = expected.revision + 1;
  LMDJ_CHECK(redone.value().state == edited);
  LMDJ_CHECK(reverse_authoring_delta(reversed) == delta);
}
void changes_only_owned_values() {
  auto before = project();
  auto after = before;
  after.banks[0][0].playback.muted = true;
  auto current = before;
  current.bpm = 140;
  current.revision = 10;
  const auto delta = authoring_difference(before, after).value();
  const auto result = apply(current, ApplyAuthoringDelta{{CommandId{uuid(82)}, 10}, delta}, {});
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value().state.bpm == 140);
  LMDJ_CHECK(result.value().state.banks[0][0].playback.muted);
  LMDJ_CHECK(result.value().state.revision == 11);
  LMDJ_CHECK(current.banks[0][0].playback.muted == false);
}
void atomic_conflict() {
  const auto before = project();
  auto after = before;
  after.bpm = 150;
  after.banks[0][0].playback.muted = true;
  const auto delta = authoring_difference(before, after).value();
  auto changed = before;
  changed.banks[0][0].playback.gain_millidb = -3000;
  const auto original = changed;
  const auto result = apply(changed, ApplyAuthoringDelta{{CommandId{uuid(83)}, changed.revision}, delta}, {});
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::revision_conflict);
  LMDJ_CHECK(changed == original);
}
void compose_actions() {
  auto first = project();
  auto second = first;
  second.bpm = 130;
  second.banks[0][1].playback.muted = true;
  auto third = second;
  third.bpm = first.bpm;
  third.banks[0][2].playback.gain_millidb = -9000;
  const auto a = authoring_difference(first, second).value();
  const auto b = authoring_difference(second, third).value();
  const auto composed = compose_authoring_deltas(a, b);
  LMDJ_CHECK(composed.has_value());
  LMDJ_CHECK(composed.value() == authoring_difference(first, third).value());
  LMDJ_CHECK(compose_authoring_deltas(a, reverse_authoring_delta(a)).value().empty());
  LMDJ_CHECK(!compose_authoring_deltas(a, a).has_value());
}
void object_and_slot_changes() {
  auto first = project();
  auto second = first;
  const PatternId pattern_id{uuid(90)};
  second.patterns.emplace(pattern_id, Pattern{pattern_id, 1, {}});
  second.pattern_slots[0] = pattern_id;
  const PerformanceId performance_id{uuid(91)};
  second.performances.emplace(performance_id, Performance{performance_id, "Take", first.bpm, first.revision, std::nullopt, {}});
  const auto delta = authoring_difference(first, second).value();
  auto forward = apply(first, ApplyAuthoringDelta{{CommandId{uuid(92)}, first.revision}, delta}, {});
  LMDJ_CHECK(forward.has_value());
  auto reverse = apply(forward.value().state, ApplyAuthoringDelta{{CommandId{uuid(93)}, forward.value().state.revision}, reverse_authoring_delta(delta)}, {});
  LMDJ_CHECK(reverse.has_value());
  first.revision += 2;
  LMDJ_CHECK(reverse.value().state == first);
}
void invalid_content() {
  const auto before = project();
  auto after = before;
  after.bpm = 1;
  LMDJ_CHECK(!apply(before, ApplyAuthoringDelta{{CommandId{uuid(94)}, before.revision}, authoring_difference(before, after).value()}, {}).has_value());
  after = before;
  after.pattern_slots[0] = PatternId{uuid(95)};
  LMDJ_CHECK(!apply(before, ApplyAuthoringDelta{{CommandId{uuid(96)}, before.revision}, authoring_difference(before, after).value()}, {}).has_value());
  after = before;
  after.id = ProjectId{uuid(97)};
  LMDJ_CHECK(!authoring_difference(before, after).has_value());
  after = before;
  ++after.revision;
  LMDJ_CHECK(authoring_difference(before, after).value().empty());
}
}
int main() {
  try {
    round_trip(); changes_only_owned_values(); atomic_conflict();
    compose_actions(); object_and_slot_changes(); invalid_content();
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
  std::cout << "authoring delta: PASS\n";
}
