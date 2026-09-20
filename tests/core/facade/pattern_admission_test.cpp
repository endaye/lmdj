#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/facade/pattern_transport_ports.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include <chrono>
#include <filesystem>
#include <functional>
#include <iostream>
#include <memory>
#include <optional>
#include <span>
#include <thread>
#include <vector>

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
  // The last converted candidate is followed by one the cutoff excludes, so
  // the checkpoint must carry the converted frame and not the excluded one.
  LMDJ_CHECK(transfer.value().checkpoint.last_runtime_frame == 25000);
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

void projection_equals_the_tail_the_transfer_would_commit() {
  using namespace lmdj;
  using namespace project_io;
  const auto journal = retained_fixture();
  const auto transfer = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 11, false);
  LMDJ_CHECK(transfer.has_value());
  const auto projection = facade::detail::project_admission_overlay(journal, false);
  LMDJ_CHECK(projection.has_value() && projection.value().has_value());
  LMDJ_CHECK(*projection.value() == transfer.value().recoverable_tail);
}

void projection_preserves_the_retained_clock_and_quantization() {
  using namespace lmdj;
  using namespace project_io;
  auto journal = retained_fixture();
  journal.admission->timing_profiles.push_back({foundation::CommandId{uuid(8)},
      12, journal.pattern_id, 21, 0, 37000, 4'147'200'000, 60, true, 60});
  journal.admission->candidates.push_back(
      {12, 43000, {0, 3}, SequenceCandidateKind::press, 99, 88});
  journal.admission->candidates.push_back(
      {13, 49000, {0, 3}, SequenceCandidateKind::release, 0, 88});
  const auto transfer = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 13, false);
  LMDJ_CHECK(transfer.has_value());
  const auto projection = facade::detail::project_admission_overlay(journal, false);
  LMDJ_CHECK(projection.has_value() && projection.value().has_value());
  LMDJ_CHECK(*projection.value() == transfer.value().recoverable_tail);
}

void projection_holds_a_press_at_a_sixteenth_until_its_release_lands() {
  using namespace lmdj;
  using namespace project_io;
  auto journal = retained_fixture();
  journal.admission->candidates.pop_back();  // press retained, release not yet
  const auto held = facade::detail::project_admission_overlay(journal, false);
  LMDJ_CHECK(held.has_value() && held.value().has_value());
  LMDJ_CHECK(*held.value() == std::vector<PatternEvent>(
      {{{0, 1}, 960, domain::kSixteenthTicks, 90}}));
  journal.admission->candidates.push_back(
      {11, 37000, {0, 1}, SequenceCandidateKind::release, 0, 72});
  const auto released = facade::detail::project_admission_overlay(journal, false);
  LMDJ_CHECK(released.has_value() && released.value().has_value());
  LMDJ_CHECK(*released.value() == std::vector<PatternEvent>({{{0, 1}, 960, 480, 90}}));
}

void projection_excludes_pre_fence_and_post_cutoff_candidates() {
  using namespace lmdj;
  using namespace project_io;
  auto journal = retained_fixture();
  journal.admission->candidates = {
      {10, 12000, {0, 1}, SequenceCandidateKind::press, 90, 60},
      {11, 14000, {0, 1}, SequenceCandidateKind::release, 0, 60},
      {12, 25000, {0, 1}, SequenceCandidateKind::press, 95, 72},
      {13, 31000, {0, 1}, SequenceCandidateKind::release, 0, 72}};
  journal.admission->closure = SequenceAdmissionClosure{13, SequenceAdmissionCloseReason::capacity};
  auto cutoff = *journal.admission->admission_fence;
  cutoff.kind = SequenceFenceKind::cutoff;
  cutoff.command_id = foundation::CommandId{uuid(7)};
  cutoff.transport_epoch = 12;
  cutoff.effective_frame = 30000;
  journal.admission->cutoff_fence = cutoff;
  const auto transfer = facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 13, false);
  LMDJ_CHECK(transfer.has_value());
  const auto projection = facade::detail::project_admission_overlay(journal, false);
  LMDJ_CHECK(projection.has_value() && projection.value().has_value());
  // The pre-fence press at 12000 and the post-cutoff release at 31000 are
  // absent from both, so the surviving press is still held at a sixteenth.
  LMDJ_CHECK(*projection.value() == transfer.value().recoverable_tail);
  LMDJ_CHECK(*projection.value() == std::vector<PatternEvent>(
      {{{0, 1}, 960, domain::kSixteenthTicks, 95}}));
}

void projection_shows_nothing_while_a_switch_awaits_reconciliation() {
  using namespace lmdj;
  using namespace project_io;
  auto journal = retained_fixture();
  journal.admission->applied_switches.push_back(
      {foundation::PatternId{uuid(9)}, 22, 28000});
  // The transfer builder refuses the same durable shape; the projection
  // reports an ordinary live state instead of poisoning its caller.
  LMDJ_CHECK(!facade::detail::build_admission_transfer(
      journal, foundation::CommandId{uuid(6)}, 11, false).has_value());
  const auto projection = facade::detail::project_admission_overlay(journal, false);
  LMDJ_CHECK(projection.has_value() && !projection.value().has_value());
}

// A pending applied switch with a candidate at/after its frame makes the
// finalized overlay unconvertible. The recovery projection must surface that
// failure, not swallow it — the journal is the only durable copy (#1515).
void owner_lost_overlay_failure_propagates_from_the_projection() {
  using namespace lmdj;
  using namespace project_io;
  auto journal = retained_fixture();
  journal.state = SequenceSessionState::owner_lost;
  journal.admission->applied_switches.push_back(
      {foundation::PatternId{uuid(9)}, 22, 5000});
  // The fixture's candidates (frames 25000/31000) sit at/after the pending
  // switch frame: conversion must fail, never silently drop the take.
  const auto projection = facade::detail::project_admission_overlay(journal, true);
  LMDJ_CHECK(!projection.has_value());
  LMDJ_CHECK(projection.error().details.at("reason") ==
             "switch_prefix_requires_reconciliation");
}

void projection_shows_nothing_before_activation_or_after_sealing() {
  using namespace lmdj;
  using namespace project_io;
  auto unactivated = retained_fixture();
  unactivated.admission->admission_fence.reset();
  const auto before = facade::detail::project_admission_overlay(unactivated, false);
  LMDJ_CHECK(before.has_value() && !before.value().has_value());

  auto lost = retained_fixture();
  lost.state = SequenceSessionState::owner_lost;
  const auto gone = facade::detail::project_admission_overlay(lost, false);
  LMDJ_CHECK(gone.has_value() && !gone.value().has_value());

  // The recovery surface reads the same durable input terminally: the take
  // the performer heard survives owner loss (#1515). A held press has no
  // future release, so it ends after its attack tail exactly like a terminal
  // transfer.
  auto held = retained_fixture();
  held.state = SequenceSessionState::owner_lost;
  held.admission->candidates = {
      {10, 25000, {0, 1}, SequenceCandidateKind::press, 90, 72}};
  const auto finalized = facade::detail::project_admission_overlay(held, true);
  LMDJ_CHECK(finalized.has_value() && finalized.value().has_value());
  LMDJ_CHECK(*finalized.value() ==
      std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));

  auto completed = retained_fixture();
  completed.admission->completed = true;
  const auto sealed = facade::detail::project_admission_overlay(completed, false);
  LMDJ_CHECK(sealed.has_value() && !sealed.value().has_value());

  ActiveSequenceJournal absent = retained_fixture();
  absent.admission.reset();
  const auto none = facade::detail::project_admission_overlay(absent, false);
  LMDJ_CHECK(none.has_value() && !none.value().has_value());
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

class TempDirectory {
 public:
  explicit TempDirectory(std::string_view label) {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-admission-owner-" + std::string(label) + "-" +
             std::to_string(std::chrono::steady_clock::now()
                                .time_since_epoch()
                                .count()));
    std::filesystem::create_directories(path_);
  }
  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }
  const std::filesystem::path& path() const { return path_; }
  TempDirectory(const TempDirectory&) = delete;
  TempDirectory& operator=(const TempDirectory&) = delete;
 private:
  std::filesystem::path path_;
};

class FailingAppendStorage final : public lmdj::project_io::ProjectStoragePlatform {
 public:
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner =
      lmdj::project_io::make_default_project_storage_platform();
  int fail_appends = 0;

  lmdj::foundation::Result<std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& path) override {
    return inner->acquire_writer(path);
  }
  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    return inner->ensure_directory(path);
  }
  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    return inner->exists(path);
  }
  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    return inner->byte_length(path);
  }
  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    return inner->read_complete(path);
  }
  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner->create_immutable(path, bytes);
  }
  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner->replace_complete(path, bytes);
  }
  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path, std::uint64_t prefix,
      std::span<const std::byte> bytes) override {
    if (fail_appends > 0) {
      --fail_appends;
      return lmdj::foundation::Result<void>::failure(
          {lmdj::foundation::ErrorCode::io_error,
           "injected admission append failure",
           {{"journal_retained", true}}});
    }
    return inner->append_durable(path, prefix, bytes);
  }
  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    return inner->remove(path);
  }
  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    return inner->list_names(path);
  }
  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& path) const override {
    return inner->validate_managed_tree(path);
  }
};

struct OwnerFixture {
  std::shared_ptr<FailingAppendStorage> platform{
      std::make_shared<FailingAppendStorage>()};
  TempDirectory directory;
  lmdj::project_io::ProjectStore store;
  std::filesystem::path bundle;
  lmdj::project_io::SequenceJournal journals;
  lmdj::foundation::SequenceSessionId session{uuid(1)};
  lmdj::foundation::PatternId pattern{uuid(2)};
  lmdj::project_io::SequenceAdmissionPreparation preparation{
      {lmdj::foundation::CommandId{uuid(3)}, 7, 11},
      lmdj::foundation::ProjectId{uuid(4)}, pattern, 21, 10};
  std::chrono::steady_clock::time_point now{
      std::chrono::steady_clock::now()};
  lmdj::facade::detail::PatternAdmissionOwner owner;

  OwnerFixture()
      : directory("owner"),
        bundle(directory.path() / "project.lmdj"),
        journals(platform),
        owner(journals, bundle, session, [this] { return now; }) {
    auto created = lmdj::domain::create_project(preparation.project_id, 120);
    LMDJ_CHECK(created.has_value());
    auto state = std::move(created.value());
    state.patterns.emplace(pattern, lmdj::domain::Pattern{pattern, 1, {}});
    LMDJ_CHECK(store.create(bundle, state).has_value());
    LMDJ_CHECK(journals
                   .begin(bundle, session, pattern, 1,
                          lmdj::project_io::sequence_pattern_fingerprint(
                              state.patterns.at(pattern)),
                          0)
                   .has_value());
  }

  lmdj::project_io::SequenceAdmissionFence fence() const {
    return {lmdj::project_io::SequenceFenceKind::admission,
            lmdj::foundation::CommandId{uuid(5)}, 11, 13000, 1000, pattern, 21,
            120, true, {}, lmdj::project_io::SequenceSwitchOutcome::none, {}};
  }

  lmdj::project_io::SequenceAdmissionFence cutoff_fence() const {
    return {lmdj::project_io::SequenceFenceKind::cutoff,
            lmdj::foundation::CommandId{uuid(7)}, 12, 40000, 1000, pattern, 21,
            120, true, {}, lmdj::project_io::SequenceSwitchOutcome::none, {}};
  }
};

void prepared_owner_uses_origin_not_the_admission_frame() {
  using namespace lmdj;
  using namespace facade::detail;
  OwnerFixture f;
  LMDJ_CHECK(f.owner.prepare(f.preparation).has_value());
  LMDJ_CHECK(f.owner.activate(f.fence()).has_value());
  const auto live = f.owner.admit(
      {9, 12000, {0, 1}, project_io::SequenceCandidateKind::press, 80, 60});
  LMDJ_CHECK(live.has_value() && live.value() == PatternAdmissionAdmit::live_only);
  LMDJ_CHECK(f.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .value() == PatternAdmissionAdmit::retained);
  LMDJ_CHECK(f.owner.admit(
      {11, 31000, {0, 1}, project_io::SequenceCandidateKind::release, 0, 72})
                 .value() == PatternAdmissionAdmit::retained);
  const auto transfer = f.owner.drain(foundation::CommandId{uuid(6)}, 11, false);
  LMDJ_CHECK(transfer.has_value());
  LMDJ_CHECK(transfer.value().recoverable_tail ==
             std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().admission->candidates.empty());
  LMDJ_CHECK(journal.value().admission->transfers.size() == 1);
  LMDJ_CHECK(journal.value().admission->admission_fence->origin_frame == 1000);
}

void prepared_owner_keeps_post_close_input_live_only() {
  using namespace lmdj;
  using namespace facade::detail;
  OwnerFixture f;
  LMDJ_CHECK(f.owner.prepare(f.preparation).has_value());
  LMDJ_CHECK(f.owner.activate(f.fence()).has_value());
  LMDJ_CHECK(f.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .value() == PatternAdmissionAdmit::retained);
  LMDJ_CHECK(f.owner
                 .close({10, project_io::SequenceAdmissionCloseReason::capacity})
                 .has_value());
  LMDJ_CHECK(f.owner.admit(
      {11, 31000, {0, 1}, project_io::SequenceCandidateKind::release, 0, 72})
                 .value() == PatternAdmissionAdmit::live_only);
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.value().admission->candidates.size() == 1);
  LMDJ_CHECK(journal.value().admission->closure.has_value());
}

void prepared_owner_leaves_unresolved_fence_after_owner_loss() {
  using namespace lmdj;
  using namespace facade::detail;
  OwnerFixture f;
  LMDJ_CHECK(f.owner.prepare(f.preparation).has_value());
  LMDJ_CHECK(f.owner.activate(f.fence()).has_value());
  LMDJ_CHECK(f.journals.set_state(
      f.bundle, f.session, project_io::SequenceSessionState::owner_lost)
                 .has_value());
  LMDJ_CHECK(f.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .value() == PatternAdmissionAdmit::live_only);
  LMDJ_CHECK(!f.owner.drain(foundation::CommandId{uuid(6)}, 10, false).has_value());
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.value().state == project_io::SequenceSessionState::owner_lost);
  LMDJ_CHECK(journal.value().admission->admission_fence.has_value());
  LMDJ_CHECK(journal.value().admission->candidates.empty());
}

void prepared_owner_drains_through_the_execution_port() {
  using namespace lmdj;
  using namespace facade;
  OwnerFixture prepared;
  LMDJ_CHECK(prepared.owner.prepare(prepared.preparation).has_value());
  LMDJ_CHECK(prepared.owner.activate(prepared.fence()).has_value());
  LMDJ_CHECK(prepared.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .has_value());
  LMDJ_CHECK(prepared.owner.admit(
      {11, 31000, {0, 1}, project_io::SequenceCandidateKind::release, 0, 72})
                 .has_value());
  class Worker final : public PatternTransportWorkOwner {
   public:
    Worker(std::filesystem::path bundle, foundation::SequenceSessionId session,
           project_io::SequenceAdmissionIdentity identity)
        : bundle_(std::move(bundle)), session_(session), identity_(identity) {}
    PatternTransportWorkCompletion execute(
        const PatternTransportWorkRequest&) override {
      const auto transfer = detail::commit_admission_transfer(
          journals_, bundle_, session_, identity_,
          foundation::CommandId{uuid(6)}, 11, false);
      if (!transfer.has_value()) {
        return {PatternTransportWorkOutcome::refused, {}, transfer.error()};
      }
      return {PatternTransportWorkOutcome::success,
              transfer.value().candidates_sha256, {}};
    }
   private:
    project_io::SequenceJournal journals_;
    std::filesystem::path bundle_;
    foundation::SequenceSessionId session_;
    project_io::SequenceAdmissionIdentity identity_;
  };
  PatternTransportExecutor executor(7, [&] {
    return std::make_unique<Worker>(
        prepared.bundle, prepared.session, prepared.preparation.identity);
  });
  const auto end = std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (!executor.inspect().ready) {
    LMDJ_CHECK(std::chrono::steady_clock::now() < end);
    std::this_thread::yield();
  }
  const PatternTransportWorkRequest request{
      {7, 11, foundation::CommandId{uuid(6)}, 1}, "drain"};
  LMDJ_CHECK(executor.submit(request) == PatternTransportWorkSubmit::accepted);
  while (executor.inspect().completion == nullptr) {
    LMDJ_CHECK(std::chrono::steady_clock::now() < end);
    std::this_thread::yield();
  }
  LMDJ_CHECK(executor.inspect().completion->outcome ==
             PatternTransportWorkOutcome::success);
  LMDJ_CHECK(executor.consume(request.identity));
  const auto journal = prepared.journals.read_active(prepared.bundle);
  LMDJ_CHECK(journal.value().admission->transfers.size() == 1);
  LMDJ_CHECK(journal.value().admission->transfers.front().recoverable_tail ==
             std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));
}

void prepared_owner_closes_at_capacity_and_drains_after_delayed_cutoff() {
  using namespace lmdj;
  using namespace facade::detail;
  OwnerFixture f;
  f.preparation.candidate_limit = 1;
  LMDJ_CHECK(f.owner.prepare(f.preparation).has_value());
  LMDJ_CHECK(f.owner.activate(f.fence()).has_value());
  LMDJ_CHECK(f.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .value() == PatternAdmissionAdmit::retained);
  const auto closed = f.journals.read_active(f.bundle);
  LMDJ_CHECK(closed.value().admission->closure ==
             (project_io::SequenceAdmissionClosure{
                 10, project_io::SequenceAdmissionCloseReason::capacity}));
  LMDJ_CHECK(f.owner.admit(
      {11, 31000, {0, 1}, project_io::SequenceCandidateKind::release, 0, 72})
                 .value() == PatternAdmissionAdmit::live_only);
  const auto still_closed = f.journals.read_active(f.bundle);
  LMDJ_CHECK(still_closed.value().admission->candidates.size() == 1);
  LMDJ_CHECK(!f.owner.drain(foundation::CommandId{uuid(6)}, 10, false).has_value());
  LMDJ_CHECK(f.owner.cutoff(f.cutoff_fence()).has_value());
  const auto transfer = f.owner.drain(foundation::CommandId{uuid(6)}, 10, false);
  LMDJ_CHECK(transfer.has_value());
  LMDJ_CHECK(transfer.value().recoverable_tail ==
             std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));
  const auto retry = f.owner.drain(foundation::CommandId{uuid(6)}, 10, false);
  LMDJ_CHECK(retry.has_value());
  LMDJ_CHECK(retry.value() == transfer.value());
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.value().admission->candidates.empty());
  LMDJ_CHECK(journal.value().admission->transfers.size() == 1);
  LMDJ_CHECK(f.owner.admit(
      {12, 37000, {0, 1}, project_io::SequenceCandidateKind::press, 80, 80})
                 .value() == PatternAdmissionAdmit::live_only);
}

void prepared_owner_closes_an_empty_prefix_at_deadline() {
  using namespace lmdj;
  using namespace facade::detail;
  OwnerFixture f;
  f.preparation.fence_timeout_ms = 1;
  LMDJ_CHECK(f.owner.prepare(f.preparation).has_value());
  LMDJ_CHECK(f.owner.activate(f.fence()).has_value());
  f.now += std::chrono::milliseconds{2};
  LMDJ_CHECK(f.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .value() == PatternAdmissionAdmit::live_only);
  const auto closed = f.journals.read_active(f.bundle);
  LMDJ_CHECK(closed.value().admission->candidates.empty());
  LMDJ_CHECK(closed.value().admission->closure ==
             (project_io::SequenceAdmissionClosure{
                 std::nullopt, project_io::SequenceAdmissionCloseReason::deadline}));
  LMDJ_CHECK(!f.owner.drain(foundation::CommandId{uuid(6)}, 0, false).has_value());
}

void prepared_owner_closes_at_deadline_before_the_next_candidate() {
  using namespace lmdj;
  using namespace facade::detail;
  OwnerFixture f;
  f.preparation.fence_timeout_ms = 1;
  LMDJ_CHECK(f.owner.prepare(f.preparation).has_value());
  LMDJ_CHECK(f.owner.activate(f.fence()).has_value());
  LMDJ_CHECK(f.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .value() == PatternAdmissionAdmit::retained);
  f.now += std::chrono::milliseconds{2};
  LMDJ_CHECK(f.owner.admit(
      {11, 31000, {0, 1}, project_io::SequenceCandidateKind::release, 0, 72})
                 .value() == PatternAdmissionAdmit::live_only);
  const auto closed = f.journals.read_active(f.bundle);
  LMDJ_CHECK(closed.value().admission->candidates.size() == 1);
  LMDJ_CHECK(closed.value().admission->closure ==
             (project_io::SequenceAdmissionClosure{
                 10, project_io::SequenceAdmissionCloseReason::deadline}));
  LMDJ_CHECK(f.owner.cutoff(f.cutoff_fence()).has_value());
  const auto transfer = f.owner.drain(foundation::CommandId{uuid(6)}, 10, false);
  LMDJ_CHECK(transfer.has_value());
  LMDJ_CHECK(transfer.value().recoverable_tail ==
             std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));
}

void prepared_owner_reports_an_uncertain_suffix_on_storage_failure() {
  using namespace lmdj;
  using namespace facade::detail;
  OwnerFixture f;
  LMDJ_CHECK(f.owner.prepare(f.preparation).has_value());
  LMDJ_CHECK(f.owner.activate(f.fence()).has_value());
  LMDJ_CHECK(f.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .value() == PatternAdmissionAdmit::retained);
  f.platform->fail_appends = 1;
  const auto failed = f.owner.admit(
      {11, 31000, {0, 1}, project_io::SequenceCandidateKind::release, 0, 72});
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().details.at("uncertain_suffix_watermark") == 11);
  LMDJ_CHECK(failed.error().details.at("last_retained_watermark") == 10);
  const auto closed = f.journals.read_active(f.bundle);
  LMDJ_CHECK(closed.value().admission->candidates.size() == 1);
  LMDJ_CHECK(closed.value().admission->closure ==
             (project_io::SequenceAdmissionClosure{
                 10, project_io::SequenceAdmissionCloseReason::storage_failure}));
  LMDJ_CHECK(f.owner.admit(
      {12, 37000, {0, 1}, project_io::SequenceCandidateKind::press, 80, 80})
                 .value() == PatternAdmissionAdmit::live_only);
  LMDJ_CHECK(f.owner.cutoff(f.cutoff_fence()).has_value());
  const auto transfer = f.owner.drain(foundation::CommandId{uuid(6)}, 10, false);
  LMDJ_CHECK(transfer.has_value());
  LMDJ_CHECK(transfer.value().recoverable_tail ==
             std::vector<PatternEvent>({{{0, 1}, 960, 240, 90}}));
}

void prepared_owner_surfaces_a_failed_storage_failure_close() {
  using namespace lmdj;
  using namespace facade::detail;
  OwnerFixture f;
  LMDJ_CHECK(f.owner.prepare(f.preparation).has_value());
  LMDJ_CHECK(f.owner.activate(f.fence()).has_value());
  LMDJ_CHECK(f.owner.admit(
      {10, 25000, {0, 1}, project_io::SequenceCandidateKind::press, 90, 72})
                 .value() == PatternAdmissionAdmit::retained);
  f.platform->fail_appends = 2;
  const auto failed = f.owner.admit(
      {11, 31000, {0, 1}, project_io::SequenceCandidateKind::release, 0, 72});
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().details.at("uncertain_suffix_watermark") == 11);
  LMDJ_CHECK(failed.error().details.at("last_retained_watermark") == 10);
  LMDJ_CHECK(failed.error().details.at("closure_unresolved") == true);
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(!journal.value().admission->closure.has_value());
  LMDJ_CHECK(journal.value().admission->candidates.size() == 1);
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
    owner_lost_overlay_failure_propagates_from_the_projection();
    projection_equals_the_tail_the_transfer_would_commit();
    projection_preserves_the_retained_clock_and_quantization();
    projection_holds_a_press_at_a_sixteenth_until_its_release_lands();
    projection_excludes_pre_fence_and_post_cutoff_candidates();
    projection_shows_nothing_while_a_switch_awaits_reconciliation();
    projection_shows_nothing_before_activation_or_after_sealing();
    acknowledged_origin_preserves_mid_loop_phase();
    release_requires_the_owned_correlation();
    retrigger_and_terminal_completion_keep_existing_rules();
    legacy_release_and_quantization_share_the_same_reducer();
    swing_uses_the_existing_odd_sixteenth_grid();
    release_duration_stops_at_the_pattern_end();
    multi_bar_onset_does_not_wrap_at_one_bar();
    prepared_owner_uses_origin_not_the_admission_frame();
    prepared_owner_keeps_post_close_input_live_only();
    prepared_owner_leaves_unresolved_fence_after_owner_loss();
    prepared_owner_drains_through_the_execution_port();
    prepared_owner_closes_at_capacity_and_drains_after_delayed_cutoff();
    prepared_owner_closes_an_empty_prefix_at_deadline();
    prepared_owner_closes_at_deadline_before_the_next_candidate();
    prepared_owner_reports_an_uncertain_suffix_on_storage_failure();
    prepared_owner_surfaces_a_failed_storage_failure_close();
    std::cout << "pattern admission tests: PASS (29 scenarios)\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
