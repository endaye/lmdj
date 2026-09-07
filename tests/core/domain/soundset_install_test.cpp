// S11-D8 / S11-D9 / S11-D12 and #465 Q2: installing a Sound Set writes the
// mapped slots as ordinary Assets with soundset Lineage in one revision. The
// three write-sets on an occupied target Bank are the acceptance witness:
// an omitted policy refuses, `keep` writes only the non-colliding proposals,
// and `replace` writes every proposal. Replaced Assets are never deleted.
#include <algorithm>
#include <array>
#include <cstdint>
#include <exception>
#include <iostream>
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/domain/commands.hpp>
#include <lmdj/foundation/soundset_manifest.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::Asset;
using lmdj::domain::AssetLineage;
using lmdj::domain::CommandMeta;
using lmdj::domain::CommandReceipt;
using lmdj::domain::InstallSoundSet;
using lmdj::domain::OccupiedPadPolicy;
using lmdj::domain::PadSlotId;
using lmdj::domain::ProjectContract;
using lmdj::domain::ProjectState;
using lmdj::domain::SoundSetInstallAssignment;
using lmdj::domain::SoundSetInstallLineageDerivation;
using lmdj::domain::SoundSetLineageSource;
using lmdj::domain::SoundSetProposedPad;
using lmdj::domain::map_soundset;
using lmdj::domain::resolve_soundset_write_set;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SoundSetManifest;
using lmdj::foundation::SoundSetOccupiedSlot;

constexpr std::uint8_t kTargetBank = 2;
constexpr const char* kSetId = "30000000-0000-4000-8000-000000000009";
constexpr const char* kSetVersion = "1.2.0";

std::string digest(char fill) { return std::string(64, fill); }

std::string uuid(unsigned value) {
  std::string suffix = std::to_string(value);
  return "20000000-0000-4000-8000-" + std::string(12 - suffix.size(), '0') +
         suffix;
}

// Slots 0, 1, 2 and 5 are occupied; every other slot is empty.
SoundSetManifest test_manifest() {
  SoundSetManifest manifest;
  manifest.set_id = kSetId;
  manifest.version = kSetVersion;
  manifest.name = "Install Fixture";
  manifest.publisher = "Test Publisher";
  manifest.license = {"CC0-1.0", "Holder", "Copyright 2026 Holder", ""};
  for (int index = 0; index < lmdj::foundation::kSoundSetSlotCount; ++index) {
    manifest.slots.at(static_cast<std::size_t>(index)).index = index;
  }
  const std::array<std::pair<int, char>, 4> occupied{
      {{0, 'a'}, {1, 'b'}, {2, 'c'}, {5, 'd'}}};
  for (const auto& [index, fill] : occupied) {
    manifest.slots.at(static_cast<std::size_t>(index)).occupied =
        SoundSetOccupiedSlot{
            "kick",
            std::string{"slot-"} + std::to_string(index),
            ArtifactRef{digest(fill), "audio/wav", 44},
            std::nullopt,
            std::nullopt,
        };
  }
  return manifest;
}

ProjectState project_with_occupied_pads(
    const std::vector<std::uint8_t>& occupied_pads) {
  auto created = lmdj::domain::create_project(ProjectId{uuid(1)}, 120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  state.contract = ProjectContract::v4;
  for (const auto pad : occupied_pads) {
    const auto asset_id = AssetId{uuid(100U + pad)};
    state.assets.emplace(
        asset_id,
        Asset{asset_id, ArtifactRef{digest('f'), "audio/wav", 44}, std::nullopt});
    state.banks.at(kTargetBank).at(pad).asset_id = asset_id;
  }
  return state;
}

AssetLineage soundset_lineage(std::uint8_t slot_index, char artifact_fill) {
  return AssetLineage{
      SoundSetLineageSource{
          kSetId,
          kSetVersion,
          digest('e'),
          slot_index,
          digest(artifact_fill),
      },
      SoundSetInstallLineageDerivation{},
  };
}

// The Facade allocates Asset ids; this mirrors that step deterministically.
InstallSoundSet install_command(
    const std::vector<SoundSetProposedPad>& write_set,
    std::uint64_t expected_revision) {
  InstallSoundSet command{
      CommandMeta{CommandId{uuid(7)}, expected_revision}, {}};
  for (const auto& proposed : write_set) {
    const auto asset_id = AssetId{uuid(200U + proposed.pad)};
    command.assignments.push_back(SoundSetInstallAssignment{
        PadSlotId{kTargetBank, proposed.pad},
        Asset{
            asset_id,
            proposed.artifact,
            soundset_lineage(proposed.slot_index, proposed.artifact.sha256.at(0)),
        },
    });
  }
  return command;
}

std::vector<std::uint8_t> written_pads(
    const std::vector<SoundSetProposedPad>& write_set) {
  std::vector<std::uint8_t> pads;
  for (const auto& proposed : write_set) {
    pads.push_back(proposed.pad);
  }
  return pads;
}

void test_omitted_policy_refuses_with_the_full_collisions_list() {
  const auto state = project_with_occupied_pads({1, 5});
  const auto mapping = map_soundset(test_manifest(), state.banks.at(kTargetBank));
  LMDJ_CHECK(mapping.collisions == std::vector<std::uint8_t>({1, 5}));
  const auto refused = resolve_soundset_write_set(mapping, std::nullopt);
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      refused.error().details.at("reason") == "soundset_occupied_conflict");
  LMDJ_CHECK(
      refused.error().details.at("collisions") ==
      nlohmann::json::array({1, 5}));
  // Zero Project change: the refusal never reached a command.
  LMDJ_CHECK(state.revision == 0);
  LMDJ_CHECK(state.assets.size() == 2);
}

void test_omitted_policy_is_accepted_when_nothing_collides() {
  const auto state = project_with_occupied_pads({3, 7});
  const auto mapping = map_soundset(test_manifest(), state.banks.at(kTargetBank));
  LMDJ_CHECK(mapping.collisions.empty());
  const auto resolved = resolve_soundset_write_set(mapping, std::nullopt);
  LMDJ_CHECK(resolved.has_value());
  LMDJ_CHECK(
      written_pads(resolved.value()) ==
      std::vector<std::uint8_t>({0, 1, 2, 5}));
}

void test_keep_writes_only_the_non_colliding_proposed_pads() {
  const auto state = project_with_occupied_pads({1, 5});
  const auto mapping = map_soundset(test_manifest(), state.banks.at(kTargetBank));
  const auto resolved =
      resolve_soundset_write_set(mapping, OccupiedPadPolicy::keep);
  LMDJ_CHECK(resolved.has_value());
  LMDJ_CHECK(
      written_pads(resolved.value()) == std::vector<std::uint8_t>({0, 2}));

  const auto applied = lmdj::domain::apply(
      state, install_command(resolved.value(), state.revision), {});
  LMDJ_CHECK(applied.has_value());
  const auto& next = applied.value().state;
  LMDJ_CHECK(next.revision == state.revision + 1);
  LMDJ_CHECK(next.banks.at(kTargetBank).at(0).asset_id == AssetId{uuid(200)});
  LMDJ_CHECK(next.banks.at(kTargetBank).at(2).asset_id == AssetId{uuid(202)});
  // The colliding Pads keep their original Assets.
  LMDJ_CHECK(
      next.banks.at(kTargetBank).at(1).asset_id == AssetId{uuid(101)});
  LMDJ_CHECK(
      next.banks.at(kTargetBank).at(5).asset_id == AssetId{uuid(105)});
  LMDJ_CHECK(next.assets.size() == state.assets.size() + 2);
}

void test_replace_writes_every_proposed_pad_and_keeps_replaced_assets() {
  const auto state = project_with_occupied_pads({1, 5});
  const auto mapping = map_soundset(test_manifest(), state.banks.at(kTargetBank));
  const auto resolved =
      resolve_soundset_write_set(mapping, OccupiedPadPolicy::replace);
  LMDJ_CHECK(resolved.has_value());
  LMDJ_CHECK(
      written_pads(resolved.value()) ==
      std::vector<std::uint8_t>({0, 1, 2, 5}));

  const auto applied = lmdj::domain::apply(
      state, install_command(resolved.value(), state.revision), {});
  LMDJ_CHECK(applied.has_value());
  const auto& next = applied.value().state;
  LMDJ_CHECK(next.revision == state.revision + 1);
  for (const std::uint8_t pad : {0, 1, 2, 5}) {
    LMDJ_CHECK(
        next.banks.at(kTargetBank).at(pad).asset_id ==
        AssetId{uuid(200U + pad)});
  }
  // S8-D5: the Assets the install replaced are still Project Truth.
  LMDJ_CHECK(next.assets.contains(AssetId{uuid(101)}));
  LMDJ_CHECK(next.assets.contains(AssetId{uuid(105)}));
  LMDJ_CHECK(next.assets.size() == state.assets.size() + 4);
}

void test_empty_set_slots_never_clear_an_occupied_pad() {
  const auto state = project_with_occupied_pads({3, 7, 15});
  const auto mapping = map_soundset(test_manifest(), state.banks.at(kTargetBank));
  const auto resolved =
      resolve_soundset_write_set(mapping, OccupiedPadPolicy::replace);
  LMDJ_CHECK(resolved.has_value());
  const auto applied = lmdj::domain::apply(
      state, install_command(resolved.value(), state.revision), {});
  LMDJ_CHECK(applied.has_value());
  const auto& next = applied.value().state;
  for (const std::uint8_t pad : {3, 7, 15}) {
    LMDJ_CHECK(
        next.banks.at(kTargetBank).at(pad).asset_id ==
        AssetId{uuid(100U + pad)});
  }
  // Empty Set slots over empty Pads stay empty rather than being written.
  LMDJ_CHECK(!next.banks.at(kTargetBank).at(4).asset_id.has_value());
}

void test_install_lands_every_asset_and_pad_in_exactly_one_revision() {
  const auto state = project_with_occupied_pads({});
  const auto mapping = map_soundset(test_manifest(), state.banks.at(kTargetBank));
  const auto resolved = resolve_soundset_write_set(mapping, std::nullopt);
  LMDJ_CHECK(resolved.has_value());
  const auto command = install_command(resolved.value(), state.revision);
  const auto applied = lmdj::domain::apply(state, command, {});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(!applied.value().replayed);
  const auto& next = applied.value().state;
  LMDJ_CHECK(next.revision == 1);
  LMDJ_CHECK(next.assets.size() == 4);
  LMDJ_CHECK(applied.value().event.at("revision") == 1);
  LMDJ_CHECK(applied.value().event.at("type") == "soundset.installed");
  LMDJ_CHECK(applied.value().event.at("command_id") == uuid(7));
  LMDJ_CHECK(next.contract == ProjectContract::v4);
  for (const auto& assignment : command.assignments) {
    const auto& asset = next.assets.at(assignment.asset.id);
    LMDJ_CHECK(asset.lineage.has_value());
    const auto& source =
        std::get<SoundSetLineageSource>(asset.lineage->source);
    LMDJ_CHECK(source.set_id == kSetId);
    LMDJ_CHECK(source.set_version == kSetVersion);
    LMDJ_CHECK(source.manifest_sha256 == digest('e'));
    LMDJ_CHECK(source.slot_index == assignment.slot.pad);
    LMDJ_CHECK(source.artifact_sha256 == asset.artifact.sha256);
    LMDJ_CHECK(std::holds_alternative<SoundSetInstallLineageDerivation>(
        asset.lineage->derivation));
  }
}

void test_replayed_command_id_returns_the_stored_receipt() {
  const auto state = project_with_occupied_pads({});
  const auto mapping = map_soundset(test_manifest(), state.banks.at(kTargetBank));
  const auto resolved = resolve_soundset_write_set(mapping, std::nullopt);
  LMDJ_CHECK(resolved.has_value());
  const auto command = install_command(resolved.value(), state.revision);
  const nlohmann::json stored_event{
      {"command_id", uuid(7)}, {"revision", 1}, {"type", "soundset.installed"}};
  const std::map<CommandId, CommandReceipt> receipts{
      {command.meta.command_id, CommandReceipt{1, stored_event}}};
  const auto replayed = lmdj::domain::apply(state, command, receipts);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().event == stored_event);
  LMDJ_CHECK(replayed.value().state == state);
}

void test_install_fails_closed_on_a_lineage_that_contradicts_its_slot() {
  const auto state = project_with_occupied_pads({});
  const auto mapping = map_soundset(test_manifest(), state.banks.at(kTargetBank));
  const auto resolved = resolve_soundset_write_set(mapping, std::nullopt);
  LMDJ_CHECK(resolved.has_value());

  auto wrong_slot = install_command(resolved.value(), state.revision);
  std::get<SoundSetLineageSource>(
      wrong_slot.assignments.at(1).asset.lineage->source)
      .slot_index = 9;
  LMDJ_CHECK(!lmdj::domain::apply(state, wrong_slot, {}).has_value());

  auto wrong_artifact = install_command(resolved.value(), state.revision);
  std::get<SoundSetLineageSource>(
      wrong_artifact.assignments.at(1).asset.lineage->source)
      .artifact_sha256 = digest('9');
  LMDJ_CHECK(!lmdj::domain::apply(state, wrong_artifact, {}).has_value());

  auto resample_derivation = install_command(resolved.value(), state.revision);
  resample_derivation.assignments.at(0).asset.lineage->derivation =
      lmdj::domain::ResampleLineageDerivation{
          {1, 2}, lmdj::domain::PerformanceId{uuid(3)}};
  LMDJ_CHECK(!lmdj::domain::apply(state, resample_derivation, {}).has_value());

  auto missing_lineage = install_command(resolved.value(), state.revision);
  missing_lineage.assignments.at(0).asset.lineage.reset();
  LMDJ_CHECK(!lmdj::domain::apply(state, missing_lineage, {}).has_value());

  auto two_banks = install_command(resolved.value(), state.revision);
  two_banks.assignments.at(1).slot.bank = kTargetBank + 1;
  LMDJ_CHECK(!lmdj::domain::apply(state, two_banks, {}).has_value());

  auto duplicate_pad = install_command(resolved.value(), state.revision);
  duplicate_pad.assignments.at(1).slot.pad =
      duplicate_pad.assignments.at(0).slot.pad;
  LMDJ_CHECK(!lmdj::domain::apply(state, duplicate_pad, {}).has_value());

  auto empty = install_command({}, state.revision);
  LMDJ_CHECK(!lmdj::domain::apply(state, empty, {}).has_value());

  auto legacy = state;
  legacy.contract = ProjectContract::v3;
  LMDJ_CHECK(
      !lmdj::domain::apply(
           legacy, install_command(resolved.value(), legacy.revision), {})
           .has_value());

  auto stale = install_command(resolved.value(), state.revision + 3);
  const auto conflicted = lmdj::domain::apply(state, stale, {});
  LMDJ_CHECK(!conflicted.has_value());
  LMDJ_CHECK(conflicted.error().code == ErrorCode::revision_conflict);
}

}  // namespace

int main() {
  try {
    test_omitted_policy_refuses_with_the_full_collisions_list();
    test_omitted_policy_is_accepted_when_nothing_collides();
    test_keep_writes_only_the_non_colliding_proposed_pads();
    test_replace_writes_every_proposed_pad_and_keeps_replaced_assets();
    test_empty_set_slots_never_clear_an_occupied_pad();
    test_install_lands_every_asset_and_pad_in_exactly_one_revision();
    test_replayed_command_id_returns_the_stored_receipt();
    test_install_fails_closed_on_a_lineage_that_contradicts_its_slot();
  } catch (const std::exception& error) {
    std::cerr << "soundset install test failed: " << error.what() << "\n";
    return 1;
  }
  std::cout << "soundset install tests passed\n";
  return 0;
}
