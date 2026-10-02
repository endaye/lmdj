#include <cstdint>
#include <exception>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

#include <lmdj/domain/project.hpp>

#include "tests/core/support/test.hpp"

namespace {

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";

static_assert(std::is_same_v<
    std::underlying_type_t<lmdj::domain::ProjectContract>,
    std::uint8_t>);
static_assert(std::is_same_v<
    std::underlying_type_t<lmdj::domain::TriggerMode>,
    std::uint8_t>);

void test_uuid_validation_matches_project_contract_grammar() {
  for (const std::string_view valid : {
           "01234567-89ab-1cde-8f01-23456789abcd",
           "01234567-89ab-2cde-9f01-23456789abcd",
           "01234567-89ab-3cde-af01-23456789abcd",
           "01234567-89ab-4cde-bf01-23456789abcd",
           "01234567-89ab-5cde-8f01-23456789abcd",
       }) {
    LMDJ_CHECK(lmdj::domain::is_valid_uuid(valid));
  }

  for (const std::string_view invalid : {
           "01234567.89ab.4cde.8f01.23456789abcd",
           "01234567-89AB-4cde-8f01-23456789abcd",
           "01234567-89ab-4cde-8f01-23456789abc",
           "01234567-89ab-6cde-8f01-23456789abcd",
           "01234567-89ab-4cde-7f01-23456789abcd",
           "01234567-89ab-4cde-cf01-23456789abcd",
       }) {
    LMDJ_CHECK(!lmdj::domain::is_valid_uuid(invalid));
  }
}

void test_every_new_project_declares_lmdj_project_v5() {
  // The Contract level of a Project is not emergent from its command history:
  // every Project this Build creates declares lmdj.project.v5 before any
  // command is applied, so a v5-only command never has to promote it first.
  const auto result = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{kProjectId}, 120);

  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value().contract == lmdj::domain::ProjectContract::v5);
  LMDJ_CHECK(result.value().revision == 0);
  LMDJ_CHECK(
      result.value().pattern_slots.size() ==
      lmdj::domain::kPatternSlotCount);
  for (const auto& slot : result.value().pattern_slots) {
    LMDJ_CHECK(!slot.has_value());
  }
  LMDJ_CHECK(result.value().performances.empty());
}

void test_new_project_creates_all_64_addressable_pad_slots() {
  const auto result = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{kProjectId}, 120);

  LMDJ_CHECK(result.has_value());
  const auto& project = result.value();
  LMDJ_CHECK(project.contract == lmdj::domain::ProjectContract::v5);
  LMDJ_CHECK(project.revision == 0);
  LMDJ_CHECK(project.quantize_enabled);
  LMDJ_CHECK(project.swing_percent == 50);
  LMDJ_CHECK(project.banks.size() == 4);

  std::uint32_t slot_count = 0;
  for (std::uint8_t bank = 0; bank < 4; ++bank) {
    LMDJ_CHECK(project.banks.at(bank).size() == 16);
    for (std::uint8_t pad = 0; pad < 16; ++pad) {
      const auto& slot = project.banks.at(bank).at(pad);
      LMDJ_CHECK((slot.id == lmdj::domain::PadSlotId{bank, pad}));
      LMDJ_CHECK(!slot.asset_id.has_value());
      LMDJ_CHECK(slot.playback == lmdj::domain::PadPlayback{});
      ++slot_count;
    }
  }
  LMDJ_CHECK(slot_count == 64);
}

void test_tick_helpers_follow_locked_quantize_swing_and_duration_rules() {
  using lmdj::domain::kBarTicks4x4;
  using lmdj::domain::normalize_duration_tick;
  using lmdj::domain::quantize_onset_tick;

  LMDJ_CHECK(quantize_onset_tick(119, kBarTicks4x4, true, 50) == 0);
  LMDJ_CHECK(quantize_onset_tick(120, kBarTicks4x4, true, 50) == 0);
  LMDJ_CHECK(quantize_onset_tick(121, kBarTicks4x4, true, 50) == 240);
  LMDJ_CHECK(
      quantize_onset_tick(kBarTicks4x4 - 1, kBarTicks4x4, true, 50) == 0);
  LMDJ_CHECK(quantize_onset_tick(240, kBarTicks4x4, true, 75) == 360);
  LMDJ_CHECK(quantize_onset_tick(241, kBarTicks4x4, false, 75) == 241);
  LMDJ_CHECK(
      normalize_duration_tick(1'000, 1'300, 960, kBarTicks4x4) == 300);
  LMDJ_CHECK(
      normalize_duration_tick(1'000, 900, 960, kBarTicks4x4) == 1);
  LMDJ_CHECK(
      normalize_duration_tick(0, 9'000, 3'800, kBarTicks4x4) == 40);
}

void test_pattern_merge_is_last_write_wins_and_canonically_ordered() {
  using lmdj::domain::PadSlotId;
  using lmdj::domain::PatternEvent;
  const std::vector<PatternEvent> stored{
      {PadSlotId{1, 0}, 480, 120, 90},
      {PadSlotId{0, 2}, 0, 240, 80},
  };
  const std::vector<PatternEvent> incoming{
      {PadSlotId{1, 0}, 480, 300, 127},
      {PadSlotId{0, 1}, 0, 120, 100},
      {PadSlotId{0, 1}, 0, 60, 110},
  };
  const auto merged = lmdj::domain::merge_pattern_events(stored, incoming);

  LMDJ_CHECK(merged.size() == 3);
  LMDJ_CHECK((merged[0].slot == PadSlotId{0, 1}));
  LMDJ_CHECK(merged[0].duration_tick == 60);
  LMDJ_CHECK(merged[0].velocity == 110);
  LMDJ_CHECK((merged[1].slot == PadSlotId{0, 2}));
  LMDJ_CHECK((merged[2].slot == PadSlotId{1, 0}));
  LMDJ_CHECK(merged[2].duration_tick == 300);
  LMDJ_CHECK(merged[2].velocity == 127);
}

void test_pad_playback_defaults_are_project_v2_contract_values() {
  const lmdj::domain::PadPlayback playback{};

  LMDJ_CHECK(playback.trim_start_frame == 0);
  LMDJ_CHECK(!playback.trim_end_frame.has_value());
  LMDJ_CHECK(playback.trigger_mode == lmdj::domain::TriggerMode::one_shot);
  LMDJ_CHECK(playback.gain_millidb == 0);
  LMDJ_CHECK(!playback.muted);
}

// The 5.1.0 parity fields default to the playback that predates them, both
// for a default value and for the five-value form every older caller uses.
void test_pad_playback_parity_fields_default_to_prior_behaviour() {
  for (const lmdj::domain::PadPlayback& playback :
       {lmdj::domain::PadPlayback{},
        lmdj::domain::PadPlayback{
            7, 90, lmdj::domain::TriggerMode::loop_gate, -1200, true}}) {
    LMDJ_CHECK(!playback.reverse);
    LMDJ_CHECK(playback.pitch_cents == 0);
    LMDJ_CHECK(playback.pan == 0);
    LMDJ_CHECK(playback.loop_mode == lmdj::domain::LoopMode::forward);
    LMDJ_CHECK(!playback.loop_start_frame.has_value());
    LMDJ_CHECK(playback.loop_crossfade_frames == 0);
  }
}

// The 5.2.0 tone fields default to the bypassed playback that predates them.
void test_pad_playback_tone_fields_default_to_bypass() {
  for (const lmdj::domain::PadPlayback& playback :
       {lmdj::domain::PadPlayback{},
        lmdj::domain::PadPlayback{
            7, 90, lmdj::domain::TriggerMode::loop_gate, -1200, true}}) {
    LMDJ_CHECK(playback.attack_ms == 0);
    LMDJ_CHECK(playback.release_ms == 0);
    LMDJ_CHECK(playback.tone == 0);
    LMDJ_CHECK(playback.eq == lmdj::domain::PadEq{});
    LMDJ_CHECK(!playback.eq.low && !playback.eq.mid && !playback.eq.high);
  }
}

// Against an 8-frame source, the loop point must lie before the resolved end:
// an open trim end resolves to the source length.
void test_playback_for_source_bounds_the_loop_point_by_the_resolved_end() {
  lmdj::domain::PadPlayback playback{
      0, std::nullopt, lmdj::domain::TriggerMode::loop_gate, 0, false};
  playback.loop_start_frame = 7;
  LMDJ_CHECK(lmdj::domain::is_valid_playback_for_source(playback, 8));
  playback.loop_start_frame = 8;
  LMDJ_CHECK(!lmdj::domain::is_valid_playback_for_source(playback, 8));
  playback.trim_end_frame = 7;
  playback.loop_start_frame = 7;
  LMDJ_CHECK(!lmdj::domain::is_valid_playback_for_source(playback, 8));
  playback.trim_end_frame = 9;
  playback.loop_start_frame = std::nullopt;
  LMDJ_CHECK(!lmdj::domain::is_valid_playback_for_source(playback, 8));
}

// The crossfade may cover at most half of the loop the source leaves.
void test_playback_for_source_bounds_the_crossfade_by_half_the_loop() {
  lmdj::domain::PadPlayback playback{
      0, std::nullopt, lmdj::domain::TriggerMode::loop_gate, 0, false};
  playback.loop_start_frame = 2;
  playback.loop_crossfade_frames = 3;
  LMDJ_CHECK(lmdj::domain::is_valid_playback_for_source(playback, 8));
  playback.loop_crossfade_frames = 4;
  LMDJ_CHECK(!lmdj::domain::is_valid_playback_for_source(playback, 8));
}

void test_project_factory_accepts_only_supported_bpm_range() {
  LMDJ_CHECK(
      lmdj::domain::create_project(
          lmdj::foundation::ProjectId{kProjectId}, 40)
          .has_value());
  LMDJ_CHECK(
      lmdj::domain::create_project(
          lmdj::foundation::ProjectId{kProjectId}, 240)
          .has_value());

  const auto too_slow = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{kProjectId}, 39);
  const auto too_fast = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{kProjectId}, 241);

  LMDJ_CHECK(!too_slow.has_value());
  LMDJ_CHECK(
      too_slow.error().code == lmdj::foundation::ErrorCode::invalid_argument);
  LMDJ_CHECK(!too_fast.has_value());
  LMDJ_CHECK(
      too_fast.error().code == lmdj::foundation::ErrorCode::invalid_argument);
}

void test_project_factory_rejects_non_contract_project_ids() {
  for (const std::string_view invalid : {
           "00000000.0000.4000.8000.000000000001",
           "00000000-0000-4000-8000-00000000000A",
           "00000000-0000-4000-8000-00000000001",
           "00000000-0000-6000-8000-000000000001",
       }) {
    const auto result = lmdj::domain::create_project(
        lmdj::foundation::ProjectId{std::string(invalid)}, 120);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(
        result.error().code ==
        lmdj::foundation::ErrorCode::invalid_argument);
  }
}

void test_sequence_session_id_is_a_distinct_strong_identity() {
  const lmdj::foundation::SequenceSessionId first{kProjectId};
  const lmdj::foundation::SequenceSessionId same{kProjectId};
  const lmdj::foundation::SequenceSessionId different{
      "00000000-0000-4000-8000-000000000002"};
  LMDJ_CHECK(first == same);
  LMDJ_CHECK(first != different);
}

}  // namespace

int main() {
  try {
    test_uuid_validation_matches_project_contract_grammar();
    test_new_project_creates_all_64_addressable_pad_slots();
    test_every_new_project_declares_lmdj_project_v5();
    test_tick_helpers_follow_locked_quantize_swing_and_duration_rules();
    test_pattern_merge_is_last_write_wins_and_canonically_ordered();
    test_pad_playback_defaults_are_project_v2_contract_values();
    test_pad_playback_parity_fields_default_to_prior_behaviour();
    test_pad_playback_tone_fields_default_to_bypass();
    test_playback_for_source_bounds_the_loop_point_by_the_resolved_end();
    test_playback_for_source_bounds_the_crossfade_by_half_the_loop();
    test_project_factory_accepts_only_supported_bpm_range();
    test_project_factory_rejects_non_contract_project_ids();
    test_sequence_session_id_is_a_distinct_strong_identity();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "domain project tests: PASS\n";
  return 0;
}
