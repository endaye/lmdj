#include <cstdint>
#include <exception>
#include <iostream>
#include <limits>
#include <string>
#include <type_traits>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/domain/project.hpp>

#include "tests/core/support/test.hpp"

namespace {

using Json = nlohmann::json;
using lmdj::domain::AssetLineage;
using lmdj::domain::Performance;
using lmdj::domain::PerformanceEvent;
using lmdj::domain::PerformanceEventKind;
using lmdj::domain::PerformanceFx;

constexpr auto kPerformanceId = "00000000-0000-4000-8000-000000000010";

Performance valid_performance() {
  return Performance{
      lmdj::domain::PerformanceId{kPerformanceId},
      "Performance",
      120,
      0,
      std::nullopt,
      {},
  };
}

AssetLineage valid_lineage() {
  return AssetLineage{
      {std::string(64, 'a'), 7},
      {{10, 20}, lmdj::domain::PerformanceId{kPerformanceId}},
  };
}

PerformanceEvent parse_event(const Json& input) {
  const auto result = lmdj::domain::performance_event_from_json(input);
  LMDJ_CHECK(result.has_value());
  return result.value();
}

void check_rejected(const Json& input) {
  const auto result = lmdj::domain::performance_event_from_json(input);
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(
      result.error().code ==
      lmdj::foundation::ErrorCode::invalid_argument);
}

void check_performance_rejected(const Performance& performance) {
  const auto result = lmdj::domain::validate_performance(performance);
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(
      result.error().code ==
      lmdj::foundation::ErrorCode::invalid_argument);
}

void test_locked_event_and_fx_vocabularies_have_stable_ordinals() {
  static_assert(std::is_same_v<
                std::underlying_type_t<PerformanceEventKind>,
                std::uint8_t>);
  static_assert(std::is_same_v<
                std::underlying_type_t<PerformanceFx>,
                std::uint8_t>);

  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceEventKind::pad_hit) == 0);
  LMDJ_CHECK(
      static_cast<std::uint8_t>(PerformanceEventKind::pattern_launch) == 1);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceEventKind::fx_engage) == 2);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceEventKind::fx_move) == 3);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceEventKind::fx_release) == 4);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceEventKind::hold_on) == 5);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceEventKind::hold_off) == 6);

  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceFx::filter) == 0);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceFx::delay) == 1);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceFx::reverb) == 2);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceFx::stutter) == 3);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceFx::gate) == 4);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceFx::reverse) == 5);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceFx::crush) == 6);
  LMDJ_CHECK(static_cast<std::uint8_t>(PerformanceFx::cutter) == 7);
}

void test_each_locked_event_shape_round_trips_exactly() {
  const std::vector<Json> encoded{
      {{"kind", "pad_hit"},
       {"slot", 63},
       {"onset_tick", 10},
       {"duration_tick", 20},
       {"velocity", 127}},
      {{"kind", "pattern_launch"},
       {"pattern_slot", 15},
       {"effective_tick", 3'840}},
      {{"kind", "fx_engage"}, {"fx", 0}, {"value", 500}, {"tick", 11}},
      {{"kind", "fx_move"}, {"fx", 7}, {"value", 1'000}, {"tick", 12}},
      {{"kind", "fx_release"}, {"fx", 7}, {"tick", 13}},
      {{"kind", "hold_on"}, {"tick", 14}},
      {{"kind", "hold_off"}, {"tick", 15}},
  };

  for (const auto& event : encoded) {
    const auto parsed = parse_event(event);
    LMDJ_CHECK(lmdj::domain::performance_event_json(parsed) == event);
  }
}

void test_events_are_canonically_ordered_by_tick_kind_and_fx_or_slot() {
  std::vector<PerformanceEvent> events{
      parse_event({{"kind", "hold_off"}, {"tick", 100}}),
      parse_event(
          {{"kind", "pad_hit"},
           {"slot", 7},
           {"onset_tick", 100},
           {"duration_tick", 1},
           {"velocity", 100}}),
      parse_event({{"kind", "fx_move"}, {"fx", 6}, {"value", 100}, {"tick", 100}}),
      parse_event({{"kind", "pattern_launch"}, {"pattern_slot", 4}, {"effective_tick", 100}}),
      parse_event({{"kind", "fx_engage"}, {"fx", 3}, {"value", 500}, {"tick", 100}}),
      parse_event({{"kind", "hold_on"}, {"tick", 100}}),
      parse_event({{"kind", "fx_release"}, {"fx", 3}, {"tick", 100}}),
      parse_event(
          {{"kind", "pad_hit"},
           {"slot", 2},
           {"onset_tick", 100},
           {"duration_tick", 1},
           {"velocity", 100}}),
      parse_event({{"kind", "fx_move"}, {"fx", 1}, {"value", 200}, {"tick", 100}}),
      parse_event({{"kind", "hold_on"}, {"tick", 99}}),
  };

  const auto ordered = lmdj::domain::canonical_performance_events(events);
  LMDJ_CHECK(ordered.size() == events.size());
  LMDJ_CHECK(lmdj::domain::performance_event_tick(ordered[0]) == 99);
  LMDJ_CHECK(
      lmdj::domain::performance_event_kind(ordered[1]) ==
      PerformanceEventKind::pad_hit);
  LMDJ_CHECK(lmdj::domain::performance_event_fx_or_slot(ordered[1]) == 2);
  LMDJ_CHECK(lmdj::domain::performance_event_fx_or_slot(ordered[2]) == 7);
  LMDJ_CHECK(
      lmdj::domain::performance_event_kind(ordered[3]) ==
      PerformanceEventKind::pattern_launch);
  LMDJ_CHECK(
      lmdj::domain::performance_event_kind(ordered[4]) ==
      PerformanceEventKind::fx_engage);
  LMDJ_CHECK(
      lmdj::domain::performance_event_kind(ordered[5]) ==
      PerformanceEventKind::fx_move);
  LMDJ_CHECK(lmdj::domain::performance_event_fx_or_slot(ordered[5]) == 1);
  LMDJ_CHECK(lmdj::domain::performance_event_fx_or_slot(ordered[6]) == 6);
  LMDJ_CHECK(
      lmdj::domain::performance_event_kind(ordered[7]) ==
      PerformanceEventKind::fx_release);
  LMDJ_CHECK(
      lmdj::domain::performance_event_kind(ordered[8]) ==
      PerformanceEventKind::hold_on);
  LMDJ_CHECK(
      lmdj::domain::performance_event_kind(ordered[9]) ==
      PerformanceEventKind::hold_off);
}

void test_valid_stream_and_performance_are_accepted() {
  std::vector<PerformanceEvent> events{
      parse_event({{"kind", "fx_engage"}, {"fx", 0}, {"value", 500}, {"tick", 10}}),
      parse_event({{"kind", "fx_move"}, {"fx", 0}, {"value", 700}, {"tick", 11}}),
      parse_event({{"kind", "hold_on"}, {"tick", 12}}),
      parse_event({{"kind", "fx_release"}, {"fx", 0}, {"tick", 13}}),
      parse_event({{"kind", "hold_off"}, {"tick", 14}}),
  };
  LMDJ_CHECK(lmdj::domain::validate_performance_events(events).has_value());

  Performance performance{
      lmdj::domain::PerformanceId{kPerformanceId},
      std::string(64, 'x'),
      120,
      42,
      std::nullopt,
      std::move(events),
  };
  LMDJ_CHECK(lmdj::domain::validate_performance(performance).has_value());
  performance.name.push_back('x');
  LMDJ_CHECK(!lmdj::domain::validate_performance(performance).has_value());

  std::string unicode_name;
  for (std::size_t index = 0; index < 64; ++index) {
    unicode_name += "\xe6\xbc\x94";
  }
  performance.name = unicode_name;
  LMDJ_CHECK(lmdj::domain::validate_performance(performance).has_value());
  performance.name += "\xe5\x87\xba";
  LMDJ_CHECK(!lmdj::domain::validate_performance(performance).has_value());
}

void test_asset_lineage_round_trips_exactly() {
  const auto lineage = valid_lineage();
  const Json expected{
      {"source",
       {{"kind", "asset_artifact"},
        {"artifact_sha256", std::string(64, 'a')},
        {"project_revision", 7}}},
      {"derivation",
       {{"kind", "resample"},
        {"range", {{"start_frame", 10}, {"end_frame", 20}}},
        {"performance_id", kPerformanceId}}},
  };
  LMDJ_CHECK(lmdj::domain::validate_asset_lineage(lineage).has_value());
  LMDJ_CHECK(lmdj::domain::asset_lineage_json(lineage) == expected);
  const auto decoded = lmdj::domain::asset_lineage_from_json(expected);
  LMDJ_CHECK(decoded.has_value());
  LMDJ_CHECK(decoded.value() == lineage);
}

void test_asset_lineage_rejects_invalid_values_and_shapes() {
  auto lineage = valid_lineage();
  lineage.source.artifact_sha256 = std::string(64, 'A');
  LMDJ_CHECK(!lmdj::domain::validate_asset_lineage(lineage).has_value());
  lineage = valid_lineage();
  lineage.source.artifact_sha256 = std::string(63, 'a');
  LMDJ_CHECK(!lmdj::domain::validate_asset_lineage(lineage).has_value());
  lineage = valid_lineage();
  lineage.derivation.performance_id =
      lmdj::domain::PerformanceId{"not-a-uuid"};
  LMDJ_CHECK(!lmdj::domain::validate_asset_lineage(lineage).has_value());
  lineage = valid_lineage();
  lineage.derivation.range.end_frame = lineage.derivation.range.start_frame;
  LMDJ_CHECK(!lmdj::domain::validate_asset_lineage(lineage).has_value());
  lineage = valid_lineage();
  lineage.derivation.range.end_frame = lineage.derivation.range.start_frame - 1;
  LMDJ_CHECK(!lmdj::domain::validate_asset_lineage(lineage).has_value());

  const std::vector<Json> malformed{
      nullptr,
      Json::object(),
      {{"source", Json::object()}, {"derivation", Json::object()}},
      {{"source",
        {{"kind", "asset_artifact"},
         {"artifact_sha256", std::string(64, 'a')},
         {"project_revision", 7},
         {"extra", true}}},
       {"derivation",
        {{"kind", "resample"},
         {"range", {{"start_frame", 10}, {"end_frame", 20}}},
         {"performance_id", kPerformanceId}}}},
      {{"source",
        {{"kind", "asset_artifact"},
         {"artifact_sha256", std::string(64, 'a')},
         {"project_revision", 7}}},
       {"derivation",
        {{"kind", "resample"},
         {"range",
          {{"start_frame", 10}, {"end_frame", 20}, {"extra", true}}},
         {"performance_id", kPerformanceId}}}},
  };
  for (const auto& value : malformed) {
    LMDJ_CHECK(!lmdj::domain::asset_lineage_from_json(value).has_value());
  }
}

void test_recording_revision_accepts_any_unsigned_64_bit_value() {
  auto performance = valid_performance();
  performance.recording_revision = std::numeric_limits<std::uint64_t>::max();
  LMDJ_CHECK(lmdj::domain::validate_performance(performance).has_value());
}

void test_unmatched_release_and_move_are_rejected() {
  const std::vector<PerformanceEvent> release{
      parse_event({{"kind", "fx_release"}, {"fx", 2}, {"tick", 1}}),
  };
  const std::vector<PerformanceEvent> move{
      parse_event({{"kind", "fx_move"}, {"fx", 2}, {"value", 1}, {"tick", 1}}),
  };
  LMDJ_CHECK(!lmdj::domain::validate_performance_events(release).has_value());
  LMDJ_CHECK(!lmdj::domain::validate_performance_events(move).has_value());
}

void test_double_engage_is_rejected() {
  const std::vector<PerformanceEvent> events{
      parse_event({{"kind", "fx_engage"}, {"fx", 5}, {"value", 1}, {"tick", 1}}),
      parse_event({{"kind", "fx_engage"}, {"fx", 5}, {"value", 2}, {"tick", 2}}),
  };
  LMDJ_CHECK(!lmdj::domain::validate_performance_events(events).has_value());
}

void test_double_hold_transitions_are_rejected() {
  const std::vector<PerformanceEvent> double_on{
      parse_event({{"kind", "hold_on"}, {"tick", 1}}),
      parse_event({{"kind", "hold_on"}, {"tick", 2}}),
  };
  const std::vector<PerformanceEvent> off_while_off{
      parse_event({{"kind", "hold_off"}, {"tick", 1}}),
  };
  LMDJ_CHECK(!lmdj::domain::validate_performance_events(double_on).has_value());
  LMDJ_CHECK(!lmdj::domain::validate_performance_events(off_while_off).has_value());
}

void test_contract_bounds_are_rejected() {
  check_rejected(
      {{"kind", "pad_hit"},
       {"slot", 64},
       {"onset_tick", 0},
       {"duration_tick", 1},
       {"velocity", 127}});
  check_rejected(
      {{"kind", "pad_hit"},
       {"slot", 0},
       {"onset_tick", 0},
       {"duration_tick", 0},
       {"velocity", 127}});
  check_rejected(
      {{"kind", "pattern_launch"},
       {"pattern_slot", 16},
       {"effective_tick", 0}});
  check_rejected(
      {{"kind", "fx_engage"}, {"fx", 8}, {"value", 500}, {"tick", 0}});
  check_rejected(
      {{"kind", "fx_move"}, {"fx", 0}, {"value", 1'001}, {"tick", 0}});
}

void test_typed_event_validation_rejects_every_bound() {
  const auto rejects = [](PerformanceEvent event) {
    LMDJ_CHECK(
        !lmdj::domain::validate_performance_events({std::move(event)})
             .has_value());
  };

  rejects(PerformanceEvent{lmdj::domain::PadHitPerformanceEvent{64, 0, 1, 1}});
  rejects(PerformanceEvent{lmdj::domain::PadHitPerformanceEvent{0, 0, 0, 1}});
  rejects(PerformanceEvent{lmdj::domain::PadHitPerformanceEvent{0, 0, 1, 0}});
  rejects(PerformanceEvent{lmdj::domain::PadHitPerformanceEvent{0, 0, 1, 128}});
  rejects(PerformanceEvent{
      lmdj::domain::PatternLaunchPerformanceEvent{16, 0}});
  rejects(PerformanceEvent{lmdj::domain::FxEngagePerformanceEvent{
      static_cast<PerformanceFx>(8), 0, 0}});
  rejects(PerformanceEvent{
      lmdj::domain::FxEngagePerformanceEvent{PerformanceFx::filter, 1'001, 0}});
  rejects(PerformanceEvent{lmdj::domain::FxMovePerformanceEvent{
      static_cast<PerformanceFx>(8), 0, 0}});
  rejects(PerformanceEvent{
      lmdj::domain::FxMovePerformanceEvent{PerformanceFx::filter, 1'001, 0}});
  rejects(PerformanceEvent{lmdj::domain::FxReleasePerformanceEvent{
      static_cast<PerformanceFx>(8), 0}});
}

void test_performance_metadata_artifact_and_ordering_are_validated() {
  auto performance = valid_performance();
  performance.id = lmdj::domain::PerformanceId{"not-a-uuid"};
  check_performance_rejected(performance);

  performance = valid_performance();
  performance.name.clear();
  check_performance_rejected(performance);

  const std::vector<std::string> malformed_utf8{
      std::string("\x80", 1),
      std::string("\xc2", 1),
      std::string("\xc2x", 2),
      std::string("\xc0\x80", 2),
      std::string("\xed\xa0\x80", 3),
      std::string("\xf4\x90\x80\x80", 4),
  };
  for (const auto& name : malformed_utf8) {
    performance = valid_performance();
    performance.name = name;
    check_performance_rejected(performance);
  }

  performance = valid_performance();
  performance.name = std::string("\xc2\xa2", 2) +
                     std::string("\xf0\x9f\x8e\xb5", 4);
  LMDJ_CHECK(lmdj::domain::validate_performance(performance).has_value());

  performance = valid_performance();
  performance.created_bpm = 39;
  check_performance_rejected(performance);
  performance.created_bpm = 241;
  check_performance_rejected(performance);

  performance = valid_performance();
  performance.recording_artifact =
      lmdj::foundation::ArtifactRef{"abc", "audio/wav", 3};
  check_performance_rejected(performance);
  performance.recording_artifact =
      lmdj::foundation::ArtifactRef{std::string(64, 'g'), "audio/wav", 3};
  check_performance_rejected(performance);
  performance.recording_artifact =
      lmdj::foundation::ArtifactRef{std::string(64, 'a'), "", 3};
  check_performance_rejected(performance);
  performance.recording_artifact = lmdj::foundation::ArtifactRef{
      std::string(64, 'a'), "audio/wav", 3};
  LMDJ_CHECK(lmdj::domain::validate_performance(performance).has_value());

  performance = valid_performance();
  performance.events = {
      PerformanceEvent{lmdj::domain::PadHitPerformanceEvent{0, 2, 1, 1}},
      PerformanceEvent{lmdj::domain::PadHitPerformanceEvent{0, 1, 1, 1}},
  };
  check_performance_rejected(performance);
}

void test_event_json_rejects_malformed_shapes_and_values() {
  const std::vector<Json> malformed{
      nullptr,
      Json::array(),
      Json::object(),
      {{"kind", 1}},
      {{"kind", "unknown"}},
      {{"kind", "pad_hit"},
       {"slot", 0},
       {"onset_tick", 0},
       {"duration_tick", 1}},
      {{"kind", "pad_hit"},
       {"slot", 0},
       {"onset_tick", 0},
       {"duration_tick", 1},
       {"wrong", 1}},
      {{"kind", "pad_hit"},
       {"slot", -1},
       {"onset_tick", 0},
       {"duration_tick", 1},
       {"velocity", 1}},
      {{"kind", "pad_hit"},
       {"slot", 0},
       {"onset_tick", -1},
       {"duration_tick", 1},
       {"velocity", 1}},
      {{"kind", "pad_hit"},
       {"slot", 0},
       {"onset_tick", 0},
       {"duration_tick", "one"},
       {"velocity", 1}},
      {{"kind", "pad_hit"},
       {"slot", 0},
       {"onset_tick", 0},
       {"duration_tick", 1},
       {"velocity", 0}},
      {{"kind", "pattern_launch"},
       {"pattern_slot", -1},
       {"effective_tick", 0}},
      {{"kind", "pattern_launch"},
       {"pattern_slot", 0},
       {"effective_tick", -1}},
      {{"kind", "fx_engage"}, {"fx", -1}, {"value", 0}, {"tick", 0}},
      {{"kind", "fx_engage"}, {"fx", 0}, {"value", -1}, {"tick", 0}},
      {{"kind", "fx_engage"}, {"fx", 0}, {"value", 0}, {"tick", -1}},
      {{"kind", "fx_move"}, {"fx", 8}, {"value", 0}, {"tick", 0}},
      {{"kind", "fx_move"}, {"fx", 0}, {"value", 1'001}, {"tick", 0}},
      {{"kind", "fx_release"}, {"fx", -1}, {"tick", 0}},
      {{"kind", "fx_release"}, {"fx", 0}, {"tick", -1}},
      {{"kind", "hold_on"}, {"tick", -1}},
      {{"kind", "hold_on"}, {"tick", 0}, {"extra", true}},
      {{"kind", "hold_off"}, {"tick", "zero"}},
      {{"kind", "hold_off"}, {"wrong", 0}},
  };
  for (const auto& input : malformed) {
    check_rejected(input);
  }

  const Json unsigned_event{
      {"kind", "pad_hit"},
      {"slot", Json(std::uint64_t{63})},
      {"onset_tick", Json(std::uint64_t{1})},
      {"duration_tick", Json(std::uint64_t{2})},
      {"velocity", Json(std::uint64_t{127})},
  };
  LMDJ_CHECK(lmdj::domain::performance_event_from_json(unsigned_event).has_value());
}

void test_asset_pattern_id_and_bank_references_are_rejected() {
  auto asset_reference = Json{
      {"kind", "pad_hit"},
      {"slot", 0},
      {"onset_tick", 0},
      {"duration_tick", 1},
      {"velocity", 127},
  };
  asset_reference["asset_id"] = "00000000-0000-4000-8000-000000000001";
  check_rejected(asset_reference);

  auto pattern_reference = Json{
      {"kind", "pattern_launch"},
      {"pattern_slot", 0},
      {"effective_tick", 0},
  };
  pattern_reference["pattern_id"] =
      "00000000-0000-4000-8000-000000000002";
  check_rejected(pattern_reference);

  auto bank_reference = Json{
      {"kind", "pad_hit"},
      {"slot", 0},
      {"onset_tick", 0},
      {"duration_tick", 1},
      {"velocity", 127},
  };
  bank_reference["bank"] = 0;
  check_rejected(bank_reference);
}

}  // namespace

int main() {
  try {
    test_locked_event_and_fx_vocabularies_have_stable_ordinals();
    test_each_locked_event_shape_round_trips_exactly();
    test_events_are_canonically_ordered_by_tick_kind_and_fx_or_slot();
    test_valid_stream_and_performance_are_accepted();
    test_asset_lineage_round_trips_exactly();
    test_asset_lineage_rejects_invalid_values_and_shapes();
    test_recording_revision_accepts_any_unsigned_64_bit_value();
    test_unmatched_release_and_move_are_rejected();
    test_double_engage_is_rejected();
    test_double_hold_transitions_are_rejected();
    test_contract_bounds_are_rejected();
    test_typed_event_validation_rejects_every_bound();
    test_performance_metadata_artifact_and_ordering_are_validated();
    test_event_json_rejects_malformed_shapes_and_values();
    test_asset_pattern_id_and_bank_references_are_rejected();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "domain performance tests: PASS\n";
  return 0;
}
