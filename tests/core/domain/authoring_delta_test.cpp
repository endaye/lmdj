#include <iostream>
#include <limits>
#include <functional>

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
void rejects_invalid_result_content() {
  // Each mutation violates one independent authoring invariant.
  const std::vector<std::function<void(ProjectState&)>> cases{
    [](auto& s) { s.bpm = 241; },
    [](auto& s) { s.swing_percent = 101; },
    [](auto& s) { s.assets.begin()->second.id = AssetId{uuid(99)}; },
    [](auto& s) { s.assets.begin()->second.artifact.sha256 = "short"; },
    [](auto& s) { s.assets.begin()->second.artifact.sha256 = std::string(64, 'g'); },
    [](auto& s) { s.assets.begin()->second.artifact.media_type.clear(); },
    [](auto& s) { s.assets.begin()->second.lineage = lineage(); std::get<CapabilityAdoptionLineageDerivation>(s.assets.begin()->second.lineage->derivation).parameters_sha256 = "bad"; },
    [](auto& s) { s.banks[0][0].asset_id = AssetId{uuid(99)}; },
    [](auto& s) { s.banks[0][0].playback.gain_millidb = -60001; },
    [](auto& s) { s.banks[0][0].playback.gain_millidb = 6001; },
    [](auto& s) { s.banks[0][0].playback.trim_end_frame = 0; },
    [](auto& s) { s.banks[0][0].playback.trigger_mode = static_cast<TriggerMode>(99); },
    [](auto& s) { s.banks[0][0].playback.pitch_cents = 2401; },
    [](auto& s) { auto& p = s.patterns.begin()->second; p.id = PatternId{uuid(99)}; },
    [](auto& s) { s.patterns.begin()->second.bars = 3; },
    [](auto& s) { s.patterns.begin()->second.events.front().slot = {4,0}; },
    [](auto& s) { s.patterns.begin()->second.events.front().velocity = 0; },
    [](auto& s) { s.patterns.begin()->second.events.front().velocity = 128; },
    [](auto& s) { s.patterns.begin()->second.events.front().onset_tick = pattern_length_ticks(1); },
    [](auto& s) { s.patterns.begin()->second.events.front().duration_tick = 0; },
    [](auto& s) { s.patterns.begin()->second.events.front().duration_tick = pattern_length_ticks(1) + 1; },
    [](auto& s) { s.performances.begin()->second.id = PerformanceId{uuid(99)}; },
    [](auto& s) { s.performances.begin()->second.created_bpm = 1; },
  };
  auto before = project();
  const PatternId pattern{uuid(90)};
  before.patterns.emplace(pattern, Pattern{pattern,1,{{{0,0},0,120,100}}});
  const PerformanceId performance{uuid(91)};
  before.performances.emplace(performance, Performance{performance,"Take",120,1,std::nullopt,{}});
  for (const auto& mutate : cases) {
    auto after = before;
    mutate(after);
    const auto result = apply(before, ApplyAuthoringDelta{{CommandId{uuid(100)},before.revision}, authoring_difference(before,after).value()}, {});
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
  }
}
void rejects_malformed_delta_and_stale_identity() {
  const auto before = project();
  auto after = before; after.banks[0][0].playback.muted = true;
  const auto delta = authoring_difference(before,after).value();
  const std::vector<std::function<void(ApplyAuthoringDelta&)>> malformed{
    [](auto& c) { c.meta.command_id = CommandId{"invalid"}; },
    [](auto& c) { c.delta.pads.clear(); },
    [](auto& c) { c.delta.pads.front().before.id = {4,0}; },
    [](auto& c) { c.delta.pads.front().after.id = {0,1}; },
    [](auto& c) { c.delta.pads.push_back(c.delta.pads.front()); },
    [](auto& c) { c.delta.pads.front().after = c.delta.pads.front().before; },
    [](auto& c) { c.delta.pattern_slots.emplace(16,AuthoringChange<std::optional<PatternId>>{std::nullopt,PatternId{uuid(90)}}); },
    [](auto& c) { c.delta.pattern_slots.emplace(0,AuthoringChange<std::optional<PatternId>>{std::nullopt,std::nullopt}); },
  };
  for (const auto& mutate : malformed) {
    ApplyAuthoringDelta command{{CommandId{uuid(101)},before.revision},delta}; mutate(command);
    const auto result = apply(before,command,{});
    LMDJ_CHECK(!result.has_value() && result.error().code == ErrorCode::invalid_argument);
  }
  auto exhausted = before; exhausted.revision = std::numeric_limits<std::uint64_t>::max();
  LMDJ_CHECK(!apply(exhausted,ApplyAuthoringDelta{{CommandId{uuid(102)},exhausted.revision},delta},{}).has_value());
  auto stale = ApplyAuthoringDelta{{CommandId{uuid(103)},before.revision+1},delta};
  LMDJ_CHECK(apply(before,stale,{}).error().code == ErrorCode::revision_conflict);
  stale.meta.expected_revision = before.revision; stale.delta.project_id = ProjectId{uuid(99)};
  LMDJ_CHECK(apply(before,stale,{}).error().code == ErrorCode::revision_conflict);
}
void conflicting_fields_and_composition() {
  auto before = project();
  const PatternId pattern{uuid(90)};
  before.patterns.emplace(pattern,Pattern{pattern,1,{{{0,0},0,120,100}}});
  const PerformanceId performance{uuid(91)};
  before.performances.emplace(performance,Performance{performance,"Take",120,1,std::nullopt,{}});
  const std::vector<std::function<void(ProjectState&)>> edits{
    [](auto& s) { s.bpm = 130; },
    [](auto& s) { s.quantize_enabled = !s.quantize_enabled; },
    [](auto& s) { s.swing_percent = 60; },
    [](auto& s) { s.assets.begin()->second.artifact.byte_length++; },
    [](auto& s) { s.patterns.begin()->second.bars = 2; },
    [](auto& s) { s.performances.begin()->second.name = "Changed"; },
    [pattern](auto& s) { s.pattern_slots[0] = pattern; },
    [](auto& s) { s.banks[0][0].playback.muted = true; },
  };
  AuthoringDelta empty{before.id,{},{},{},{},{},{},{},{}};
  for (const auto& edit : edits) {
    auto after = before; edit(after);
    const auto delta = authoring_difference(before,after).value();
    const auto result = apply(after,ApplyAuthoringDelta{{CommandId{uuid(104)},after.revision},delta},{});
    LMDJ_CHECK(!result.has_value() && result.error().code == ErrorCode::revision_conflict);
    LMDJ_CHECK(!compose_authoring_deltas(delta,delta).has_value());
    LMDJ_CHECK(compose_authoring_deltas(empty,delta).value() == delta);
    LMDJ_CHECK(compose_authoring_deltas(delta,empty).value() == delta);
    LMDJ_CHECK(compose_authoring_deltas(delta,reverse_authoring_delta(delta)).value().empty());
  }
  auto other = empty; other.project_id = ProjectId{uuid(99)};
  LMDJ_CHECK(!compose_authoring_deltas(empty,other).has_value());
}

}
int main() {
  try {
    round_trip(); changes_only_owned_values(); atomic_conflict();
    compose_actions(); object_and_slot_changes(); invalid_content();
    rejects_invalid_result_content(); rejects_malformed_delta_and_stale_identity();
    conflicting_fields_and_composition();
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
  std::cout << "authoring delta: PASS\n";
}
