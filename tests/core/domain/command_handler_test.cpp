#include <array>
#include <exception>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>

#include <lmdj/domain/command_handler.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::AppliedCommand;
using lmdj::domain::AssignPad;
using lmdj::domain::AssignPatternSlot;
using lmdj::domain::ClearPatternSlot;
using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CommandReceipt;
using lmdj::domain::CreatePattern;
using lmdj::domain::ImportAsset;
using lmdj::domain::ImportAssignSample;
using lmdj::domain::LoopMode;
using lmdj::domain::EditPatternEvents;
using lmdj::domain::MergePatternEvents;
using lmdj::domain::MovePatternSlot;
using lmdj::domain::PadPlayback;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::PatternEventKey;
using lmdj::domain::ResetPadPlayback;
using lmdj::domain::TriggerMode;
using lmdj::domain::UpdatePadPlayback;
using lmdj::domain::UpdateSequenceSettings;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";
constexpr auto kImportCommand1 = "10000000-0000-4000-8000-000000000001";
constexpr auto kImportCommand2 = "10000000-0000-4000-8000-000000000002";
constexpr auto kAssignCommand1 = "10000000-0000-4000-8000-000000000003";
constexpr auto kPatternCommand = "10000000-0000-4000-8000-000000000004";
constexpr auto kAssignCommand2 = "10000000-0000-4000-8000-000000000005";
constexpr auto kMergeCommand = "10000000-0000-4000-8000-000000000006";
constexpr auto kPlaybackCommand = "10000000-0000-4000-8000-000000000007";
constexpr auto kResetCommand = "10000000-0000-4000-8000-000000000008";
constexpr auto kImportAssignCommand = "10000000-0000-4000-8000-000000000009";
constexpr auto kSequenceSettingsCommand1 =
    "10000000-0000-4000-8000-00000000000a";
constexpr auto kSequenceSettingsCommand2 =
    "10000000-0000-4000-8000-00000000000b";
constexpr auto kAssignPatternSlotCommand =
    "10000000-0000-4000-8000-00000000000c";
constexpr auto kAssignSecondPatternSlotCommand =
    "10000000-0000-4000-8000-00000000000d";
constexpr auto kMovePatternSlotCommand =
    "10000000-0000-4000-8000-00000000000e";
constexpr auto kClearPatternSlotCommand =
    "10000000-0000-4000-8000-00000000000f";
constexpr auto kEditCommand1 = "10000000-0000-4000-8000-000000000010";
constexpr auto kEditCommand2 = "10000000-0000-4000-8000-000000000011";
constexpr auto kAsset1 = "20000000-0000-4000-8000-000000000001";
constexpr auto kAsset2 = "20000000-0000-4000-8000-000000000002";
constexpr auto kPattern1 = "30000000-0000-4000-8000-000000000001";
constexpr auto kPattern2 = "30000000-0000-4000-8000-000000000002";
constexpr auto kValidSha256 =
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

CommandMeta meta(std::string id, std::uint64_t revision) {
  return CommandMeta{CommandId{std::move(id)}, revision};
}

lmdj::domain::ProjectState new_project() {
  const auto result = lmdj::domain::create_project(ProjectId{kProjectId}, 120);
  LMDJ_CHECK(result.has_value());
  return result.value();
}

ImportAsset import_asset(std::string command_id, std::uint64_t revision,
                         std::string asset_id,
                         ArtifactRef artifact =
                             ArtifactRef{kValidSha256, "audio/wav", 1}) {
  return ImportAsset{
      meta(std::move(command_id), revision),
      {AssetId{std::move(asset_id)}, std::move(artifact), std::nullopt},
  };
}

AssignPad assign_pad(std::string command_id, std::uint64_t revision,
                     PadSlotId slot, AssetId asset_id) {
  return AssignPad{
      meta(std::move(command_id), revision), slot, std::move(asset_id)};
}

ImportAssignSample import_assign_sample(
    std::string command_id,
    std::uint64_t revision,
    PadSlotId slot,
    std::string asset_id) {
  return ImportAssignSample{
      meta(std::move(command_id), revision),
      {AssetId{std::move(asset_id)},
       ArtifactRef{kValidSha256, "audio/wav", 1},
       std::nullopt},
      slot,
  };
}

UpdatePadPlayback update_playback(
    std::string command_id,
    std::uint64_t revision,
    PadSlotId slot,
    PadPlayback playback) {
  return UpdatePadPlayback{
      meta(std::move(command_id), revision), slot, playback};
}

template <typename CommandType>
AppliedCommand apply_or_throw(const lmdj::domain::ProjectState& state,
                              const CommandType& command) {
  const auto result = lmdj::domain::apply(state, command, {});
  LMDJ_CHECK(result.has_value());
  return result.value();
}

template <typename CommandType>
void check_invalid_without_state_change(
    const lmdj::domain::ProjectState& state,
    const CommandType& command,
    const std::map<CommandId, CommandReceipt>& receipts = {}) {
  const auto before = state;
  const auto result = lmdj::domain::apply(state, command, receipts);
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(state == before);
}

void test_valid_command_increments_revision_once() {
  const auto initial = new_project();
  const auto applied = apply_or_throw(
      initial, Command{import_asset(kImportCommand1, 0, kAsset1)});

  LMDJ_CHECK(applied.state.revision == 1);
  LMDJ_CHECK(applied.state.contract == lmdj::domain::ProjectContract::v5);
  LMDJ_CHECK(applied.state.assets.size() == 1);
  LMDJ_CHECK(!applied.replayed);
  LMDJ_CHECK(applied.event.at("command_id") == kImportCommand1);
}

void test_ordinary_command_does_not_promote_a_loaded_v3_project() {
  // A v3 Project opened from disk keeps its declared Contract level while it
  // is being edited: promotion to v4 belongs to the persist boundary, not to
  // command application, so opening a v3 Project never migrates it.
  auto initial = new_project();
  initial.contract = lmdj::domain::ProjectContract::v3;
  const auto applied = apply_or_throw(
      initial, Command{import_asset(kImportCommand1, 0, kAsset1)});

  LMDJ_CHECK(applied.state.contract == lmdj::domain::ProjectContract::v3);
  LMDJ_CHECK(applied.state.revision == 1);
}

void test_wrong_revision_returns_conflict_without_changing_state() {
  const auto initial = new_project();
  const auto command =
      Command{import_asset(kImportCommand1, 1, kAsset1)};
  const auto result = lmdj::domain::apply(initial, command, {});

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::revision_conflict);
  LMDJ_CHECK(initial.revision == 0);
  LMDJ_CHECK(initial.assets.empty());
  LMDJ_CHECK(initial.patterns.empty());
}

void test_duplicate_command_id_replays_original_successful_outcome() {
  const auto initial = new_project();
  const auto command =
      Command{import_asset(kImportCommand1, 0, kAsset1)};
  const auto first = apply_or_throw(initial, command);
  const std::map<CommandId, CommandReceipt> receipts{
      {CommandId{kImportCommand1}, {first.state.revision, first.event}},
  };

  const auto replay = lmdj::domain::apply(first.state, command, receipts);
  LMDJ_CHECK(replay.has_value());
  LMDJ_CHECK(replay.value().replayed);
  LMDJ_CHECK(replay.value().state == first.state);
  LMDJ_CHECK(replay.value().event == first.event);
}

void test_import_assign_sample_is_one_revision_and_resets_playback() {
  auto initial = new_project();
  initial.banks[0][0].playback =
      PadPlayback{20, 40, TriggerMode::loop_toggle, -1200, true};

  const auto result = lmdj::domain::apply(
      initial,
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1),
      {});

  LMDJ_CHECK(result.has_value());
  const auto& state = result.value().state;
  LMDJ_CHECK(state.contract == lmdj::domain::ProjectContract::v5);
  LMDJ_CHECK(state.revision == 1);
  LMDJ_CHECK(state.assets.size() == 1);
  LMDJ_CHECK(state.banks[0][0].asset_id == AssetId{kAsset1});
  LMDJ_CHECK(state.banks[0][0].playback == PadPlayback{});
}

void test_update_pad_playback_migrates_an_unassigned_v1_project() {
  const auto initial = new_project();
  const auto updated = lmdj::domain::apply(
      initial,
      UpdatePadPlayback{
          meta(kPlaybackCommand, 0),
          PadSlotId{0, 0},
          PadPlayback{10, 90, TriggerMode::loop_gate, -1200, false}},
      {});

  LMDJ_CHECK(updated.has_value());
  LMDJ_CHECK(updated.value().state.contract ==
             lmdj::domain::ProjectContract::v5);
  LMDJ_CHECK(updated.value().state.revision == 1);
  LMDJ_CHECK(
      updated.value().state.banks[0][0].playback.trim_start_frame == 10);
  LMDJ_CHECK(!updated.value().state.banks[0][0].asset_id.has_value());
}

void test_update_pad_playback_accepts_all_modes_bounds_and_nullable_end() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;
  const std::array cases{
      PadPlayback{0, std::nullopt, TriggerMode::one_shot, -60000, false},
      PadPlayback{10, 90, TriggerMode::gate, -1200, true},
      PadPlayback{20, 100, TriggerMode::loop_gate, 0, false},
      PadPlayback{30, 110, TriggerMode::loop_toggle, 6000, true},
  };

  for (std::size_t index = 0; index < cases.size(); ++index) {
    const auto applied = lmdj::domain::apply(
        state,
        update_playback(
            kPlaybackCommand,
            state.revision,
            PadSlotId{0, 0},
            cases[index]),
        {});
    LMDJ_CHECK(applied.has_value());
    LMDJ_CHECK(applied.value().state.revision == state.revision + 1);
    LMDJ_CHECK(applied.value().state.contract ==
               lmdj::domain::ProjectContract::v5);
    LMDJ_CHECK(applied.value().state.banks[0][0].playback == cases[index]);
    state = applied.value().state;
  }
}

void test_pads_sharing_an_asset_keep_independent_playback() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;
  state = apply_or_throw(
              state,
              Command{assign_pad(
                  kAssignCommand1, 1, PadSlotId{0, 1}, AssetId{kAsset1})})
              .state;
  const PadPlayback first{10, 90, TriggerMode::loop_gate, -1200, false};
  const PadPlayback second{30, std::nullopt, TriggerMode::gate, 6000, true};
  state = apply_or_throw(
              state,
              update_playback(
                  kPlaybackCommand, 2, PadSlotId{0, 0}, first))
              .state;
  state = apply_or_throw(
              state,
              update_playback(
                  kResetCommand, 3, PadSlotId{0, 1}, second))
              .state;

  LMDJ_CHECK(state.banks[0][0].asset_id == state.banks[0][1].asset_id);
  LMDJ_CHECK(state.banks[0][0].playback == first);
  LMDJ_CHECK(state.banks[0][1].playback == second);
}

void test_same_asset_assignment_preserves_playback() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;
  state = apply_or_throw(
              state,
              update_playback(
                  kPlaybackCommand,
                  1,
                  PadSlotId{0, 0},
                  PadPlayback{10, 90, TriggerMode::loop_gate, -1200, true}))
              .state;
  state = apply_or_throw(
              state,
              Command{assign_pad(
                  kAssignCommand1, 2, PadSlotId{0, 0}, AssetId{kAsset1})})
              .state;

  LMDJ_CHECK(
      state.banks[0][0].playback ==
      (PadPlayback{10, 90, TriggerMode::loop_gate, -1200, true}));
}

void test_unassign_resets_playback() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;
  state = apply_or_throw(
              state,
              update_playback(
                  kPlaybackCommand,
                  1,
                  PadSlotId{0, 0},
                  PadPlayback{10, 90, TriggerMode::loop_gate, -1200, true}))
              .state;
  state = apply_or_throw(
              state,
              Command{AssignPad{
                  meta(kAssignCommand1, 2), PadSlotId{0, 0}, std::nullopt}})
              .state;

  LMDJ_CHECK(!state.banks[0][0].asset_id.has_value());
  LMDJ_CHECK(state.banks[0][0].playback == PadPlayback{});
}

void test_delete_pad_is_canonical_and_checked() {
  auto before = apply_or_throw(new_project(),
      import_assign_sample(kImportAssignCommand, 0, {0, 0}, kAsset1)).state;
  before.banks[0][0].playback.gain_millidb = -400;
  before.patterns.emplace(PatternId{kPattern1},
      Pattern{PatternId{kPattern1}, 1, {{{0, 0}, 0, 120, 100}}});
  const lmdj::domain::DeletePad command{meta(kResetCommand, 1), {0, 0}};
  const auto deleted = apply_or_throw(before, command);
  const auto canonical = apply_or_throw(before, Command{command.assignment()});
  LMDJ_CHECK(deleted.state == canonical.state);
  LMDJ_CHECK(deleted.event == canonical.event);
  LMDJ_CHECK(!deleted.state.banks[0][0].asset_id);
  LMDJ_CHECK(deleted.state.banks[0][0].playback == PadPlayback{});
  LMDJ_CHECK(deleted.state.assets == before.assets);
  LMDJ_CHECK(deleted.state.patterns == before.patterns);
  const auto stale = lmdj::domain::apply(before,
      lmdj::domain::DeletePad{meta(kResetCommand, 0), {0, 0}}, {});
  LMDJ_CHECK(!stale.has_value() && stale.error().code == ErrorCode::revision_conflict);
  check_invalid_without_state_change(before,
      lmdj::domain::DeletePad{meta(kResetCommand, 1), {4, 0}});
}

void test_different_asset_assignment_resets_playback() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;
  state = apply_or_throw(
              state, Command{import_asset(kImportCommand2, 1, kAsset2)})
              .state;
  state = apply_or_throw(
              state,
              update_playback(
                  kPlaybackCommand,
                  2,
                  PadSlotId{0, 0},
                  PadPlayback{10, 90, TriggerMode::loop_gate, -1200, true}))
              .state;
  state = apply_or_throw(
              state,
              Command{assign_pad(
                  kAssignCommand1, 3, PadSlotId{0, 0}, AssetId{kAsset2})})
              .state;

  LMDJ_CHECK(state.banks[0][0].asset_id == AssetId{kAsset2});
  LMDJ_CHECK(state.banks[0][0].playback == PadPlayback{});
}

void test_explicit_reset_restores_default_playback() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;

  state = apply_or_throw(
              state,
              update_playback(
                  kPlaybackCommand,
                  1,
                  PadSlotId{0, 0},
                  PadPlayback{5, 15, TriggerMode::gate, 500, false}))
              .state;
  const auto reset = lmdj::domain::apply(
      state,
      ResetPadPlayback{meta(kResetCommand, 2), PadSlotId{0, 0}},
      {});
  LMDJ_CHECK(reset.has_value());
  LMDJ_CHECK(reset.value().state.revision == 3);
  LMDJ_CHECK(reset.value().state.banks[0][0].playback == PadPlayback{});
}

void test_duplicate_playback_update_replays_without_another_revision() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;
  const auto command = update_playback(
      kPlaybackCommand,
      1,
      PadSlotId{0, 0},
      PadPlayback{10, 90, TriggerMode::loop_gate, -1200, false});
  const auto first = apply_or_throw(state, command);
  const std::map<CommandId, CommandReceipt> receipts{
      {CommandId{kPlaybackCommand}, {first.state.revision, first.event}},
  };

  const auto replay = lmdj::domain::apply(first.state, command, receipts);
  LMDJ_CHECK(replay.has_value());
  LMDJ_CHECK(replay.value().replayed);
  LMDJ_CHECK(replay.value().state == first.state);
  LMDJ_CHECK(replay.value().state.revision == 2);
  LMDJ_CHECK(replay.value().event == first.event);
}

void test_update_pad_playback_rejects_invalid_values() {
  const auto initial = new_project();
  for (const PadPlayback& invalid_playback : {
           PadPlayback{0, std::nullopt, TriggerMode::one_shot, -60001, false},
           PadPlayback{0, std::nullopt, TriggerMode::one_shot, 6001, false},
           PadPlayback{10, 10, TriggerMode::gate, 0, false},
           PadPlayback{
               0,
               std::nullopt,
               static_cast<TriggerMode>(255),
               0,
               false},
       }) {
    check_invalid_without_state_change(
        initial,
        update_playback(
            kPlaybackCommand, 0, PadSlotId{0, 0}, invalid_playback));
  }

}

PadPlayback with_parity(
    PadPlayback playback,
    bool reverse,
    std::int32_t pitch_cents,
    std::int32_t pan,
    LoopMode loop_mode,
    std::optional<std::uint64_t> loop_start_frame,
    std::uint64_t loop_crossfade_frames) {
  playback.reverse = reverse;
  playback.pitch_cents = pitch_cents;
  playback.pan = pan;
  playback.loop_mode = loop_mode;
  playback.loop_start_frame = loop_start_frame;
  playback.loop_crossfade_frames = loop_crossfade_frames;
  return playback;
}

void test_update_pad_playback_accepts_parity_bounds() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;
  const PadPlayback loop{10, 30, TriggerMode::loop_gate, 0, false};
  const std::array cases{
      with_parity(loop, true, -2400, -100, LoopMode::forward, std::nullopt, 0),
      with_parity(loop, false, 2400, 100, LoopMode::ping_pong, 10, 0),
      with_parity(loop, false, 0, 0, LoopMode::forward, 29, 0),
      // A 20-frame loop may blend exactly half of itself.
      with_parity(loop, false, 0, 0, LoopMode::forward, 10, 10),
      // An open trim end is bounded by the source length, not the domain.
      with_parity(
          PadPlayback{0, std::nullopt, TriggerMode::loop_toggle, 0, false},
          false, 0, 0, LoopMode::forward, 4, 1000),
  };

  for (const auto& playback : cases) {
    const auto applied = lmdj::domain::apply(
        state,
        update_playback(
            kPlaybackCommand, state.revision, PadSlotId{0, 0}, playback),
        {});
    LMDJ_CHECK(applied.has_value());
    LMDJ_CHECK(applied.value().state.banks[0][0].playback == playback);
    state = applied.value().state;
  }
}

void test_update_pad_playback_rejects_invalid_parity_values() {
  const auto initial = new_project();
  const PadPlayback loop{10, 30, TriggerMode::loop_gate, 0, false};
  for (const PadPlayback& invalid_playback : {
           with_parity(loop, false, 2401, 0, LoopMode::forward, std::nullopt, 0),
           with_parity(loop, false, -2401, 0, LoopMode::forward, std::nullopt, 0),
           with_parity(loop, false, 0, 101, LoopMode::forward, std::nullopt, 0),
           with_parity(loop, false, 0, -101, LoopMode::forward, std::nullopt, 0),
           with_parity(
               loop, false, 0, 0, static_cast<LoopMode>(255), std::nullopt, 0),
           with_parity(loop, false, 0, 0, LoopMode::forward, 9, 0),
           with_parity(loop, false, 0, 0, LoopMode::forward, 30, 0),
           with_parity(loop, false, 0, 0, LoopMode::ping_pong, std::nullopt, 1),
           with_parity(loop, false, 0, 0, LoopMode::forward, 10, 11),
       }) {
    check_invalid_without_state_change(
        initial,
        update_playback(
            kPlaybackCommand, 0, PadSlotId{0, 0}, invalid_playback));
  }
}

void test_explicit_reset_clears_parity_playback() {
  auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                   .state;
  state = apply_or_throw(
              state,
              update_playback(
                  kPlaybackCommand,
                  1,
                  PadSlotId{0, 0},
                  with_parity(
                      PadPlayback{5, 25, TriggerMode::loop_toggle, 0, false},
                      true, 700, -40, LoopMode::forward, 9, 3)))
              .state;
  const auto reset = lmdj::domain::apply(
      state,
      ResetPadPlayback{meta(kResetCommand, 2), PadSlotId{0, 0}},
      {});
  LMDJ_CHECK(reset.has_value());
  LMDJ_CHECK(reset.value().state.banks[0][0].playback == PadPlayback{});
}

void test_assign_pad_rejects_missing_asset() {
  const auto initial = new_project();
  const auto missing_asset = lmdj::domain::apply(
      initial,
      Command{assign_pad(
          kAssignCommand1, 0, PadSlotId{0, 0}, AssetId{kAsset1})},
      {});

  LMDJ_CHECK(!missing_asset.has_value());
  LMDJ_CHECK(missing_asset.error().code == ErrorCode::missing_asset);
  LMDJ_CHECK(initial.banks[0][0].playback == PadPlayback{});
  LMDJ_CHECK(!initial.banks[0][0].asset_id.has_value());
}

void test_update_pad_playback_rejects_stale_revision() {
  const auto state = apply_or_throw(
      new_project(),
      import_assign_sample(
          kImportAssignCommand, 0, PadSlotId{0, 0}, kAsset1))
                         .state;
  const auto result = lmdj::domain::apply(
      state,
      update_playback(
          kPlaybackCommand,
          0,
          PadSlotId{0, 0},
          PadPlayback{10, 90, TriggerMode::loop_gate, -1200, false}),
      {});

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::revision_conflict);
  LMDJ_CHECK(state.revision == 1);
  LMDJ_CHECK(state.banks[0][0].playback == PadPlayback{});
}

void test_invalid_command_leaves_state_unchanged() {
  const auto initial = new_project();
  const auto invalid = Command{assign_pad(
      kAssignCommand1, 0, PadSlotId{4, 0}, AssetId{kAsset1})};
  const auto result = lmdj::domain::apply(initial, invalid, {});

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(initial == new_project());
}

void test_invalid_command_id_is_rejected_before_receipt_lookup() {
  const auto initial = new_project();
  for (const std::string_view invalid : {
           "10000000.0000.4000.8000.000000000001",
           "10000000-0000-4000-8000-00000000000A",
           "10000000-0000-4000-8000-00000000001",
           "10000000-0000-6000-8000-000000000001",
       }) {
    const Command command{
        import_asset(std::string(invalid), 0, kAsset1)};
    const std::map<CommandId, CommandReceipt> receipts{
        {CommandId{std::string(invalid)},
         {1, {{"command_id", invalid}, {"type", "asset.imported"}}}},
    };
    check_invalid_without_state_change(initial, command, receipts);
  }
}

void test_import_asset_validates_id_and_complete_artifact_reference() {
  const auto initial = new_project();
  for (const std::string_view invalid : {
           "20000000.0000.4000.8000.000000000001",
           "20000000-0000-4000-8000-00000000000A",
           "20000000-0000-4000-8000-00000000001",
           "20000000-0000-6000-8000-000000000001",
       }) {
    check_invalid_without_state_change(
        initial,
        Command{import_asset(kImportCommand1, 0, std::string(invalid))});
  }

  std::string uppercase_sha(64, 'A');
  std::string non_hex_sha(64, 'a');
  non_hex_sha.back() = 'g';
  for (ArtifactRef invalid : {
           ArtifactRef{"a", "audio/wav", 1},
           ArtifactRef{uppercase_sha, "audio/wav", 1},
           ArtifactRef{non_hex_sha, "audio/wav", 1},
           ArtifactRef{kValidSha256, "", 1},
       }) {
    check_invalid_without_state_change(
        initial,
        Command{import_asset(
            kImportCommand1, 0, kAsset1, std::move(invalid))});
  }

  const auto zero_length = lmdj::domain::apply(
      initial,
      Command{import_asset(
          kImportCommand1,
          0,
          kAsset1,
          ArtifactRef{kValidSha256, "audio/wav", 0})},
      {});
  LMDJ_CHECK(zero_length.has_value());
  LMDJ_CHECK(zero_length.value().state.assets.at(AssetId{kAsset1})
                 .artifact.byte_length == 0);
}

void test_assign_pad_rejects_invalid_asset_id_before_lookup() {
  const auto initial = new_project();
  for (const std::string_view invalid : {
           "20000000.0000.4000.8000.000000000001",
           "20000000-0000-4000-8000-00000000000A",
           "20000000-0000-4000-8000-00000000001",
           "20000000-0000-6000-8000-000000000001",
       }) {
    check_invalid_without_state_change(
        initial,
        Command{assign_pad(
            kAssignCommand1,
            0,
            PadSlotId{0, 0},
            AssetId{std::string(invalid)})});
  }
}

void test_pattern_events_keep_slot_reference_through_pad_reassignment() {
  auto state = new_project();
  state = apply_or_throw(
      state, Command{import_asset(kImportCommand1, 0, kAsset1)}).state;
  state = apply_or_throw(
      state, Command{import_asset(kImportCommand2, 1, kAsset2)}).state;
  state = apply_or_throw(
      state,
      Command{assign_pad(
          kAssignCommand1, 2, PadSlotId{0, 0}, AssetId{kAsset1})})
              .state;
  state = apply_or_throw(
      state,
      Command{CreatePattern{
          meta(kPatternCommand, 3),
          {PatternId{kPattern1}, 1, {{PadSlotId{0, 0}, 0, 240, 100}}},
      }})
              .state;
  state = apply_or_throw(
      state,
      Command{assign_pad(
          kAssignCommand2, 4, PadSlotId{0, 0}, AssetId{kAsset2})})
              .state;

  const auto& event = state.patterns.at(PatternId{kPattern1}).events.at(0);
  LMDJ_CHECK((event.slot == PadSlotId{0, 0}));
  const auto resolved = lmdj::domain::resolve_slot_asset(state, event.slot);
  LMDJ_CHECK(resolved.has_value());
  LMDJ_CHECK(resolved->id == AssetId{kAsset2});
}

void test_pattern_validation_enforces_velocity_bars_and_tick_bounds() {
  const auto state = new_project();
  const auto invalid_velocity = Command{CreatePattern{
      meta(kPatternCommand, 0),
      {PatternId{kPattern1}, 1, {{PadSlotId{0, 0}, 0, 240, 0}}},
  }};
  const auto invalid_bars = Command{CreatePattern{
      meta(kPatternCommand, 0),
      {PatternId{kPattern1}, 3, {{PadSlotId{0, 0}, 0, 240, 100}}},
  }};
  const auto invalid_onset = Command{CreatePattern{
      meta(kPatternCommand, 0),
      {PatternId{kPattern1}, 1, {{PadSlotId{0, 0}, 3'840, 1, 100}}},
  }};

  for (const auto& command :
       {invalid_velocity, invalid_bars, invalid_onset}) {
    const auto result = lmdj::domain::apply(state, command, {});
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
    LMDJ_CHECK(result.error().code != ErrorCode::revision_conflict);
  }
}

void test_create_pattern_rejects_invalid_pattern_id() {
  const auto initial = new_project();
  for (const std::string_view invalid : {
           "30000000.0000.4000.8000.000000000001",
           "30000000-0000-4000-8000-00000000000A",
           "30000000-0000-4000-8000-00000000001",
           "30000000-0000-6000-8000-000000000001",
       }) {
    check_invalid_without_state_change(
        initial,
        Command{CreatePattern{
            meta(kPatternCommand, 0),
            {PatternId{std::string(invalid)}, 1, {}},
        }});
  }
}

void test_merge_pattern_events_replaces_duplicates_and_orders_canonically() {
  auto state = apply_or_throw(
                   new_project(),
                   Command{CreatePattern{
                       meta(kPatternCommand, 0),
                       {PatternId{kPattern1},
                        1,
                        {
                            {PadSlotId{1, 0}, 480, 120, 80},
                            {PadSlotId{0, 2}, 0, 240, 90},
                        }},
                   }})
                   .state;
  const auto merged = lmdj::domain::apply(
      state,
      Command{MergePatternEvents{
          meta(kMergeCommand, 1),
          PatternId{kPattern1},
          {
              {PadSlotId{1, 0}, 480, 300, 127},
              {PadSlotId{0, 1}, 0, 120, 100},
              {PadSlotId{0, 1}, 0, 60, 110},
          },
      }},
      {});

  LMDJ_CHECK(merged.has_value());
  const auto& events =
      merged.value().state.patterns.at(PatternId{kPattern1}).events;
  LMDJ_CHECK(events.size() == 3);
  LMDJ_CHECK((events[0].slot == PadSlotId{0, 1}));
  LMDJ_CHECK(events[0].duration_tick == 60);
  LMDJ_CHECK(events[0].velocity == 110);
  LMDJ_CHECK((events[1].slot == PadSlotId{0, 2}));
  LMDJ_CHECK((events[2].slot == PadSlotId{1, 0}));
  LMDJ_CHECK(events[2].duration_tick == 300);
  LMDJ_CHECK(events[2].velocity == 127);
}

// A one-bar Pattern with A1 at 0 and A2 at 240, at revision 1.
lmdj::domain::ProjectState project_with_grid_pattern() {
  return apply_or_throw(
             new_project(),
             Command{CreatePattern{
                 meta(kPatternCommand, 0),
                 {PatternId{kPattern1},
                  1,
                  {
                      {PadSlotId{0, 0}, 0, 240, 100},
                      {PadSlotId{0, 1}, 240, 240, 100},
                  }},
             }})
      .state;
}

EditPatternEvents edit_pattern(
    std::string command_id, std::uint64_t revision,
    std::vector<PatternEventKey> remove, std::vector<PatternEvent> put,
    std::string pattern_id = kPattern1) {
  return EditPatternEvents{meta(std::move(command_id), revision),
                           PatternId{std::move(pattern_id)},
                           std::move(remove), std::move(put)};
}

// The refusal's exact code and reason, so each caller fails at its own line.
std::optional<std::pair<ErrorCode, std::string>> edit_refusal(
    const lmdj::domain::ProjectState& state, const EditPatternEvents& command) {
  const auto before = state;
  const auto result = lmdj::domain::apply(state, command, {});
  if (!(state == before)) {
    throw std::runtime_error("a refused edit changed the state");
  }
  if (result.has_value()) {
    return std::nullopt;
  }
  return std::pair{result.error().code,
                   result.error().details.value("reason", std::string{})};
}

std::optional<std::pair<ErrorCode, std::string>> refused(
    ErrorCode code, std::string reason) {
  return std::pair{code, std::move(reason)};
}

void test_edit_pattern_events_moves_resizes_and_adds_in_one_revision() {
  const auto state = project_with_grid_pattern();
  const auto edited = apply_or_throw(
      state,
      edit_pattern(kEditCommand1, 1,
                   {{PadSlotId{0, 0}, 0}},
                   {{PadSlotId{0, 0}, 480, 240, 100},
                    {PadSlotId{0, 1}, 240, 720, 64},
                    {PadSlotId{0, 2}, 0, 120, 100}}));
  LMDJ_CHECK(edited.state.revision == state.revision + 1);
  LMDJ_CHECK(!edited.replayed);
  LMDJ_CHECK(edited.event.at("type") == "pattern.events_edited");
  const auto& events = edited.state.patterns.at(PatternId{kPattern1}).events;
  LMDJ_CHECK((events == std::vector<PatternEvent>{
      {PadSlotId{0, 2}, 0, 120, 100},
      {PadSlotId{0, 1}, 240, 720, 64},
      {PadSlotId{0, 0}, 480, 240, 100}}));
}

void test_edit_pattern_events_put_replaces_by_key_and_keeps_overlap() {
  const auto edited = apply_or_throw(
      project_with_grid_pattern(),
      edit_pattern(kEditCommand1, 1, {},
                   {{PadSlotId{0, 1}, 240, 60, 30},
                    {PadSlotId{0, 1}, 120, 480, 90}}));
  const auto& events = edited.state.patterns.at(PatternId{kPattern1}).events;
  // The put at A2/240 replaced the stored note; the new A2/120 note overlaps
  // it, which is allowed at a different onset.
  LMDJ_CHECK((events == std::vector<PatternEvent>{
      {PadSlotId{0, 0}, 0, 240, 100},
      {PadSlotId{0, 1}, 120, 480, 90},
      {PadSlotId{0, 1}, 240, 60, 30}}));
}

void test_edit_pattern_events_refuses_a_missing_removal() {
  LMDJ_CHECK(edit_refusal(project_with_grid_pattern(),
                          edit_pattern(kEditCommand1, 1,
                                       {{PadSlotId{0, 0}, 0}, {PadSlotId{0, 3}, 0}},
                                       {})) ==
             refused(ErrorCode::not_found, "pattern_event_missing"));
}

void test_edit_pattern_events_refuses_repeated_keys() {
  const auto state = project_with_grid_pattern();
  LMDJ_CHECK(edit_refusal(state,
                          edit_pattern(kEditCommand1, 1,
                                       {{PadSlotId{0, 0}, 0}, {PadSlotId{0, 0}, 0}},
                                       {})) ==
             refused(ErrorCode::invalid_argument, "pattern_edit_duplicate_key"));
  LMDJ_CHECK(edit_refusal(state,
                          edit_pattern(kEditCommand1, 1, {},
                                       {{PadSlotId{0, 2}, 0, 120, 100},
                                        {PadSlotId{0, 2}, 0, 240, 90}})) ==
             refused(ErrorCode::invalid_argument, "pattern_edit_duplicate_key"));
}

void test_edit_pattern_events_refuses_an_empty_or_unchanging_edit() {
  const auto state = project_with_grid_pattern();
  LMDJ_CHECK(edit_refusal(state, edit_pattern(kEditCommand1, 1, {}, {})) ==
             refused(ErrorCode::invalid_argument, "pattern_edit_empty"));
  // Removing a note and putting it back unchanged is a no-op, so it must not
  // become a revision or an Undo entry.
  LMDJ_CHECK(edit_refusal(state,
                          edit_pattern(kEditCommand1, 1, {{PadSlotId{0, 0}, 0}},
                                       {{PadSlotId{0, 0}, 0, 240, 100}})) ==
             refused(ErrorCode::invalid_argument, "pattern_edit_unchanged"));
}

void test_edit_pattern_events_refuses_a_note_across_the_loop_seam() {
  // One bar is 3840 ticks: a 480-tick note at 3600 would cross the seam.
  check_invalid_without_state_change(
      project_with_grid_pattern(),
      edit_pattern(kEditCommand1, 1, {}, {{PadSlotId{0, 2}, 3600, 480, 100}}));
}

void test_edit_pattern_events_refuses_an_unknown_pattern() {
  LMDJ_CHECK(edit_refusal(project_with_grid_pattern(),
                          edit_pattern(kEditCommand1, 1, {},
                                       {{PadSlotId{0, 2}, 0, 120, 100}},
                                       kPattern2)) ==
             refused(ErrorCode::not_found, "pattern_not_found"));
}

void test_edit_pattern_events_is_revision_checked_and_replays() {
  const auto state = project_with_grid_pattern();
  const auto stale = lmdj::domain::apply(
      state,
      edit_pattern(kEditCommand1, 0, {}, {{PadSlotId{0, 2}, 0, 120, 100}}),
      {});
  LMDJ_CHECK(!stale.has_value());
  LMDJ_CHECK(stale.error().code == ErrorCode::revision_conflict);

  const auto command =
      edit_pattern(kEditCommand2, 1, {}, {{PadSlotId{0, 2}, 0, 120, 100}});
  const auto first = apply_or_throw(state, command);
  const std::map<CommandId, CommandReceipt> receipts{
      {CommandId{kEditCommand2}, {first.state.revision, first.event}}};
  const auto replayed = lmdj::domain::apply(first.state, command, receipts);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state == first.state);
  LMDJ_CHECK(replayed.value().event == first.event);
}

void test_tick_pattern_validation_enforces_loop_remainder() {
  const auto initial = new_project();
  for (const PatternEvent invalid : {
           PatternEvent{PadSlotId{4, 0}, 0, 240, 100},
           PatternEvent{PadSlotId{0, 0}, 0, 240, 0},
           PatternEvent{PadSlotId{0, 0}, 3840, 1, 100},
           PatternEvent{PadSlotId{0, 0}, 3839, 2, 100},
           PatternEvent{PadSlotId{0, 0}, 0, 0, 100},
       }) {
    check_invalid_without_state_change(
        initial,
        Command{CreatePattern{
            meta(kPatternCommand, 0),
            {PatternId{kPattern2}, 1, {invalid}},
        }});
  }
}

void test_sequence_settings_update_enforces_locked_ranges() {
  auto state = new_project();
  const auto updated = lmdj::domain::apply(
      state,
      Command{UpdateSequenceSettings{
          meta(kMergeCommand, 0), 240, false, 75}},
      {});
  LMDJ_CHECK(updated.has_value());
  LMDJ_CHECK(updated.value().state.bpm == 240);
  LMDJ_CHECK(!updated.value().state.quantize_enabled);
  LMDJ_CHECK(updated.value().state.swing_percent == 75);

  const auto quantize_only = apply_or_throw(
      updated.value().state,
      Command{UpdateSequenceSettings{
          meta(kSequenceSettingsCommand1, 1), {}, true, {}}});
  LMDJ_CHECK(quantize_only.state.bpm == 240);
  LMDJ_CHECK(quantize_only.state.quantize_enabled);
  LMDJ_CHECK(quantize_only.state.swing_percent == 75);

  const auto bpm_only = apply_or_throw(
      quantize_only.state,
      Command{UpdateSequenceSettings{
          meta(kSequenceSettingsCommand2, 2), 40, {}, {}}});
  LMDJ_CHECK(bpm_only.state.bpm == 40);
  LMDJ_CHECK(bpm_only.state.quantize_enabled);
  LMDJ_CHECK(bpm_only.state.swing_percent == 75);

  for (const auto& command : {
           UpdateSequenceSettings{meta(kMergeCommand, 0), 39, {}, {}},
           UpdateSequenceSettings{meta(kMergeCommand, 0), 241, {}, {}},
           UpdateSequenceSettings{meta(kMergeCommand, 0), {}, {}, 49},
           UpdateSequenceSettings{meta(kMergeCommand, 0), {}, {}, 76},
           UpdateSequenceSettings{meta(kMergeCommand, 0), {}, {}, {}},
       }) {
    check_invalid_without_state_change(state, Command{command});
  }
}

void test_pattern_slot_commands_enforce_ownership_and_receipts() {
  auto initial = new_project();
  initial.contract = lmdj::domain::ProjectContract::v4;
  const PatternId pattern1{kPattern1};
  const PatternId pattern2{kPattern2};
  initial.patterns.emplace(pattern1, Pattern{pattern1, 1, {}});
  initial.patterns.emplace(pattern2, Pattern{pattern2, 1, {}});

  const Command assign_first{AssignPatternSlot{
      meta(kAssignPatternSlotCommand, 0), 0, pattern1}};
  const auto assigned = apply_or_throw(initial, assign_first);
  LMDJ_CHECK(assigned.state.contract == lmdj::domain::ProjectContract::v4);
  LMDJ_CHECK(assigned.state.revision == 1);
  LMDJ_CHECK(assigned.state.pattern_slots.at(0) == pattern1);
  LMDJ_CHECK(!assigned.replayed);

  const std::map<CommandId, CommandReceipt> receipts{
      {CommandId{kAssignPatternSlotCommand},
       {assigned.state.revision, assigned.event}},
  };
  const auto replay = lmdj::domain::apply(
      assigned.state, assign_first, receipts);
  LMDJ_CHECK(replay.has_value());
  LMDJ_CHECK(replay.value().replayed);
  LMDJ_CHECK(replay.value().state == assigned.state);
  LMDJ_CHECK(replay.value().event == assigned.event);

  for (const Command& rejected : {
           Command{AssignPatternSlot{
               meta(kAssignSecondPatternSlotCommand, 1), 0, pattern2}},
           Command{AssignPatternSlot{
               meta(kAssignSecondPatternSlotCommand, 1), 1, pattern1}},
           Command{AssignPatternSlot{
               meta(kAssignSecondPatternSlotCommand, 1),
               1,
               PatternId{"30000000-0000-4000-8000-000000000099"}}},
           Command{AssignPatternSlot{
               meta(kAssignSecondPatternSlotCommand, 1), 16, pattern2}},
       }) {
    check_invalid_without_state_change(assigned.state, rejected);
  }

  const auto assigned_second = apply_or_throw(
      assigned.state,
      Command{AssignPatternSlot{
          meta(kAssignSecondPatternSlotCommand, 1), 1, pattern2}});
  LMDJ_CHECK(assigned_second.state.revision == 2);

  for (const Command& rejected : {
           Command{MovePatternSlot{
               meta(kMovePatternSlotCommand, 2), 0, 1}},
           Command{MovePatternSlot{
               meta(kMovePatternSlotCommand, 2), 0, 0}},
           Command{MovePatternSlot{
               meta(kMovePatternSlotCommand, 2), 2, 3}},
           Command{MovePatternSlot{
               meta(kMovePatternSlotCommand, 2), 0, 16}},
       }) {
    check_invalid_without_state_change(assigned_second.state, rejected);
  }

  const auto moved = apply_or_throw(
      assigned_second.state,
      Command{MovePatternSlot{
          meta(kMovePatternSlotCommand, 2), 0, 2}});
  LMDJ_CHECK(moved.state.revision == 3);
  LMDJ_CHECK(!moved.state.pattern_slots.at(0).has_value());
  LMDJ_CHECK(moved.state.pattern_slots.at(2) == pattern1);
  LMDJ_CHECK(moved.state.pattern_slots.at(1) == pattern2);

  check_invalid_without_state_change(
      moved.state,
      Command{ClearPatternSlot{
          meta(kClearPatternSlotCommand, 3), 0}});
  check_invalid_without_state_change(
      moved.state,
      Command{ClearPatternSlot{
          meta(kClearPatternSlotCommand, 3), 16}});

  const auto cleared = apply_or_throw(
      moved.state,
      Command{ClearPatternSlot{
          meta(kClearPatternSlotCommand, 3), 2}});
  LMDJ_CHECK(cleared.state.revision == 4);
  LMDJ_CHECK(!cleared.state.pattern_slots.at(2).has_value());
  LMDJ_CHECK(cleared.state.pattern_slots.at(1) == pattern2);
}

void test_v4_authoring_commands_preserve_pattern_slot_truth() {
  auto initial = new_project();
  initial.contract = lmdj::domain::ProjectContract::v4;
  const PatternId pattern1{kPattern1};
  initial.patterns.emplace(pattern1, Pattern{pattern1, 1, {}});

  const auto assigned = apply_or_throw(
      initial,
      Command{AssignPatternSlot{
          meta(kAssignPatternSlotCommand, 0), 0, pattern1}});
  const auto updated = apply_or_throw(
      assigned.state,
      Command{UpdateSequenceSettings{
          meta(kSequenceSettingsCommand1, 1), 121, {}, {}}});

  LMDJ_CHECK(updated.state.contract == lmdj::domain::ProjectContract::v4);
  LMDJ_CHECK(updated.state.revision == 2);
  LMDJ_CHECK(updated.state.pattern_slots == assigned.state.pattern_slots);
  LMDJ_CHECK(updated.state.pattern_slots.at(0) == pattern1);
}

}  // namespace

int main() {
  try {
    test_valid_command_increments_revision_once();
    test_ordinary_command_does_not_promote_a_loaded_v3_project();
    test_wrong_revision_returns_conflict_without_changing_state();
    test_duplicate_command_id_replays_original_successful_outcome();
    test_import_assign_sample_is_one_revision_and_resets_playback();
    test_update_pad_playback_migrates_an_unassigned_v1_project();
    test_update_pad_playback_accepts_all_modes_bounds_and_nullable_end();
    test_pads_sharing_an_asset_keep_independent_playback();
    test_same_asset_assignment_preserves_playback();
    test_unassign_resets_playback();
    test_delete_pad_is_canonical_and_checked();
    test_different_asset_assignment_resets_playback();
    test_explicit_reset_restores_default_playback();
    test_duplicate_playback_update_replays_without_another_revision();
    test_update_pad_playback_rejects_invalid_values();
    test_update_pad_playback_accepts_parity_bounds();
    test_update_pad_playback_rejects_invalid_parity_values();
    test_explicit_reset_clears_parity_playback();
    test_assign_pad_rejects_missing_asset();
    test_update_pad_playback_rejects_stale_revision();
    test_invalid_command_leaves_state_unchanged();
    test_invalid_command_id_is_rejected_before_receipt_lookup();
    test_import_asset_validates_id_and_complete_artifact_reference();
    test_assign_pad_rejects_invalid_asset_id_before_lookup();
    test_pattern_events_keep_slot_reference_through_pad_reassignment();
    test_pattern_validation_enforces_velocity_bars_and_tick_bounds();
    test_create_pattern_rejects_invalid_pattern_id();
    test_merge_pattern_events_replaces_duplicates_and_orders_canonically();
    test_edit_pattern_events_moves_resizes_and_adds_in_one_revision();
    test_edit_pattern_events_put_replaces_by_key_and_keeps_overlap();
    test_edit_pattern_events_refuses_a_missing_removal();
    test_edit_pattern_events_refuses_repeated_keys();
    test_edit_pattern_events_refuses_an_empty_or_unchanging_edit();
    test_edit_pattern_events_refuses_a_note_across_the_loop_seam();
    test_edit_pattern_events_refuses_an_unknown_pattern();
    test_edit_pattern_events_is_revision_checked_and_replays();
    test_tick_pattern_validation_enforces_loop_remainder();
    test_sequence_settings_update_enforces_locked_ranges();
    test_pattern_slot_commands_enforce_ownership_and_receipts();
    test_v4_authoring_commands_preserve_pattern_slot_truth();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "domain command handler tests: PASS\n";
  return 0;
}
