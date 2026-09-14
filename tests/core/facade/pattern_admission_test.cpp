#include <lmdj/audio/prepared_sample_bank.hpp>

#include <iostream>

#include "packages/application-facade/src/pattern_admission_controller.hpp"
#include "tests/core/support/test.hpp"

namespace {
using lmdj::domain::PadSlotId;
using lmdj::domain::PatternEvent;
using lmdj::facade::detail::PatternEventReducer;
using lmdj::facade::detail::PatternOwnedPress;

std::string uuid(unsigned suffix) {
  const auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') + tail;
}

lmdj::project_io::ActiveSequenceJournal retained_fixture() {
  using namespace lmdj;
  using namespace project_io;
  ActiveSequenceJournal journal{
      foundation::SequenceSessionId{uuid(1)}, foundation::PatternId{uuid(2)},
      1, "", 0, 0, SequenceSessionState::active, {}, {}, {}, 0, {}, {},
      SessionKind::sequence, {}};
  SequenceAdmissionPreparation preparation{
      {foundation::CommandId{uuid(3)}, 7, 11}, foundation::ProjectId{uuid(4)},
      journal.pattern_id, 21, 10};
  journal.admission = SequenceAdmissionState{
      preparation, {}, {}, {}, {}, {}, {}, 21, false};
  journal.admission->admission_fence = SequenceAdmissionFence{
      SequenceFenceKind::admission, foundation::CommandId{uuid(5)}, 11,
      13000, 1000, journal.pattern_id, 21, 120, true, {},
      SequenceSwitchOutcome::none, {}};
  journal.admission->candidates = {
      {10, 25000, {0, 1}, SequenceCandidateKind::press, 90, 72},
      {11, 31000, {0, 1}, SequenceCandidateKind::release, 0, 72}};
  return journal;
}

void durable_candidates_use_the_retained_origin() {
  using namespace lmdj;
  const auto journal = retained_fixture();
  const auto transfer = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 11, false);
  LMDJ_CHECK(transfer.has_value());
  LMDJ_CHECK(transfer.value().recoverable_tail ==
      std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));
  LMDJ_CHECK(transfer.value().checkpoint.owned_presses.empty());
  LMDJ_CHECK(transfer.value().journal_input_sequence == 1);
}

void preparation_preserves_nondefault_quantization_without_a_profile() {
  using namespace lmdj;
  auto journal = retained_fixture();
  journal.admission->preparation.quantize_enabled = true;
  journal.admission->preparation.swing_percent = 60;
  journal.admission->candidates[0].runtime_frame = 31000;
  journal.admission->candidates[1].runtime_frame = 37000;
  LMDJ_CHECK(journal.admission->timing_profiles.empty());
  const auto transfer = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 11, false);
  LMDJ_CHECK(transfer.has_value());
  LMDJ_CHECK(transfer.value().recoverable_tail ==
      std::vector<PatternEvent>({{{0, 1}, 1248, 240, 90}}));
}

void retained_profiles_preserve_clock_and_quantization_history() {
  using namespace lmdj;
  using namespace project_io;
  auto journal = retained_fixture();
  journal.admission->timing_profiles.push_back({foundation::CommandId{uuid(8)},
      12, journal.pattern_id, 21, 0, 37000, 4'147'200'000, 60, true, 60});
  journal.admission->candidates.push_back(
      {12, 49000, {0, 2}, SequenceCandidateKind::press, 95, 80});
  journal.admission->candidates.push_back(
      {13, 61000, {0, 2}, SequenceCandidateKind::release, 0, 80});
  const auto transfer = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 13, false);
  LMDJ_CHECK(transfer.has_value());
  LMDJ_CHECK(transfer.value().recoverable_tail == std::vector<PatternEvent>({
      {{0, 1}, 960, 240, 90}, {{0, 2}, 1728, 240, 95}}));
}

void cutoff_excludes_orphans_and_uses_ordinary_terminal_completion() {
  using namespace lmdj;
  using namespace project_io;
  auto journal = retained_fixture();
  journal.admission->candidates = {
      {10, 12000, {0, 1}, SequenceCandidateKind::press, 90, 60},
      {11, 14000, {0, 1}, SequenceCandidateKind::release, 0, 60},
      {12, 25000, {0, 1}, SequenceCandidateKind::press, 95, 72},
      {13, 31000, {0, 1}, SequenceCandidateKind::release, 0, 72}};
  journal.admission->closure = SequenceAdmissionClosure{13, SequenceAdmissionCloseReason::capacity};
  LMDJ_CHECK(!facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 13, false).has_value());
  auto cutoff = *journal.admission->admission_fence;
  cutoff.kind = SequenceFenceKind::cutoff;
  cutoff.command_id = foundation::CommandId{uuid(7)};
  cutoff.transport_epoch = 12;
  cutoff.effective_frame = 30000;
  journal.admission->cutoff_fence = cutoff;
  const auto transfer = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 13, false);
  LMDJ_CHECK(transfer.has_value());
  LMDJ_CHECK(transfer.value().recoverable_tail ==
      std::vector<PatternEvent>({{{0, 1}, 960, 240, 95}}));
  LMDJ_CHECK(transfer.value().checkpoint.owned_presses.size() == 1);
  journal.admission->transfers.push_back(transfer.value());
  journal.admission->candidates.clear();
  journal.pending_events = transfer.value().recoverable_tail;
  journal.last_input_sequence = transfer.value().journal_input_sequence;
  const auto terminal = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(9)}, 0, true);
  LMDJ_CHECK(terminal.has_value());
  LMDJ_CHECK(terminal.value().recoverable_tail == transfer.value().recoverable_tail);
  LMDJ_CHECK(terminal.value().checkpoint.owned_presses.empty());
  LMDJ_CHECK(!terminal.value().journal_input_sequence);
  LMDJ_CHECK(terminal.value().checkpoint.last_runtime_frame == 30000);
}

void conversion_retry_returns_the_retained_identity_without_new_input() {
  using namespace lmdj;
  auto journal = retained_fixture();
  const foundation::CommandId id{uuid(6)};
  const auto first = facade::detail::build_admission_transfer(journal, id, 11, false);
  LMDJ_CHECK(first.has_value());
  journal.admission->transfers.push_back(first.value());
  journal.admission->candidates.clear();
  const auto retry = facade::detail::build_admission_transfer(journal, id, 11, false);
  LMDJ_CHECK(retry.has_value() && retry.value() == first.value());
  LMDJ_CHECK(!facade::detail::build_admission_transfer(journal, id, 10, false).has_value());
  LMDJ_CHECK(!facade::detail::build_admission_transfer(journal, id, 0, true).has_value());
}

void excluded_prefix_preserves_the_checkpoint_and_input_sequence() {
  using namespace lmdj;
  auto journal = retained_fixture();
  const auto press = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 10, false);
  LMDJ_CHECK(press.has_value());
  journal.admission->transfers.push_back(press.value());
  journal.admission->candidates.erase(journal.admission->candidates.begin());
  journal.admission->candidates.front().press_sequence = 71; // stale release
  journal.pending_events = press.value().recoverable_tail;
  journal.last_input_sequence = 1;
  const auto release = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(7)}, 11, false);
  LMDJ_CHECK(release.has_value());
  LMDJ_CHECK(release.value().recoverable_tail == press.value().recoverable_tail);
  LMDJ_CHECK(release.value().checkpoint == press.value().checkpoint);
  LMDJ_CHECK(!release.value().journal_input_sequence);
  LMDJ_CHECK(release.value().candidate_receipts.size() == 1);
}

void switch_target_input_requires_reconciliation_and_its_own_clock() {
  using namespace lmdj;
  using namespace project_io;
  for (const bool same_pattern : {false, true}) {
    auto journal = retained_fixture();
    const auto target = same_pattern ? journal.pattern_id : foundation::PatternId{uuid(9)};
    journal.admission->applied_switches.push_back({target, 22, 28000});
    LMDJ_CHECK(!facade::detail::build_admission_transfer(
        journal, foundation::CommandId{uuid(6)}, 11, false).has_value());
    const auto source = facade::detail::build_admission_transfer(
        journal, foundation::CommandId{uuid(6)}, 10, false);
    LMDJ_CHECK(source.has_value());
    LMDJ_CHECK(source.value().recoverable_tail ==
        std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));
    // Model the far side of journal switch; this is not the switch owner test.
    journal.pattern_id = target;
    journal.expected_revision = 1;
    journal.admission->segment_generation = 22;
    journal.admission->transfers.push_back(source.value());
    journal.last_input_sequence = 1;
    journal.admission->candidates = {
        {11, 31000, {0, 1}, SequenceCandidateKind::release, 0, 72},
        {12, 34000, {0, 2}, SequenceCandidateKind::press, 95, 80},
        {13, 40000, {0, 2}, SequenceCandidateKind::release, 0, 80}};
    LMDJ_CHECK(!facade::detail::build_admission_transfer(
        journal, foundation::CommandId{uuid(7)}, 13, false).has_value());
    journal.admission->timing_profiles.push_back({foundation::CommandId{uuid(8)},
        11, target, 22, 1, 28000, 0, 120, false, 50});
    const auto transferred = facade::detail::build_admission_transfer(
        journal, foundation::CommandId{uuid(7)}, 13, false);
    LMDJ_CHECK(transferred.has_value());
    LMDJ_CHECK(transferred.value().pattern_id == target);
    LMDJ_CHECK(transferred.value().recoverable_tail ==
        std::vector<PatternEvent>({{{0, 2}, 240, 240, 95}}));
    LMDJ_CHECK(transferred.value().checkpoint.owned_presses.empty());
    LMDJ_CHECK(transferred.value().checkpoint.publication_generation == 22);
    LMDJ_CHECK(transferred.value().journal_input_sequence == 2);
  }
}

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
    durable_candidates_use_the_retained_origin();
    preparation_preserves_nondefault_quantization_without_a_profile();
    retained_profiles_preserve_clock_and_quantization_history();
    cutoff_excludes_orphans_and_uses_ordinary_terminal_completion();
    conversion_retry_returns_the_retained_identity_without_new_input();
    excluded_prefix_preserves_the_checkpoint_and_input_sequence();
    switch_target_input_requires_reconciliation_and_its_own_clock();
    acknowledged_origin_preserves_mid_loop_phase();
    release_requires_the_owned_correlation();
    retrigger_and_terminal_completion_keep_existing_rules();
    legacy_release_and_quantization_share_the_same_reducer();
    swing_uses_the_existing_odd_sixteenth_grid();
    release_duration_stops_at_the_pattern_end();
    multi_bar_onset_does_not_wrap_at_one_bar();
    std::cout << "pattern admission tests: PASS (14 scenarios)\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
