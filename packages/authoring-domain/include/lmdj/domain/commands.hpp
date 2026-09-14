#pragma once

#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <variant>
#include <vector>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/soundset_manifest.hpp>

namespace lmdj::domain {

struct CommandMeta {
  foundation::CommandId command_id;
  std::uint64_t expected_revision;
};

struct ImportAsset {
  CommandMeta meta;
  Asset asset;
};

struct AssignPad {
  CommandMeta meta;
  PadSlotId slot;
  std::optional<foundation::AssetId> asset_id;
};

struct ImportAssignSample {
  CommandMeta meta;
  Asset asset;
  PadSlotId slot;
};

struct UpdatePadPlayback {
  CommandMeta meta;
  PadSlotId slot;
  PadPlayback playback;
};

struct ResetPadPlayback {
  CommandMeta meta;
  PadSlotId slot;
};

struct CreatePattern {
  CommandMeta meta;
  Pattern pattern;
};

struct AssignPatternSlot {
  CommandMeta meta;
  std::uint8_t slot;
  foundation::PatternId pattern_id;
};

struct ClearPatternSlot {
  CommandMeta meta;
  std::uint8_t slot;
};

struct MovePatternSlot {
  CommandMeta meta;
  std::uint8_t from_slot;
  std::uint8_t to_slot;
};

struct MergePatternEvents {
  CommandMeta meta;
  foundation::PatternId pattern_id;
  std::vector<PatternEvent> events;
};

struct UpdateSequenceSettings {
  CommandMeta meta;
  std::optional<std::uint16_t> bpm;
  std::optional<bool> quantize_enabled;
  std::optional<std::uint8_t> swing_percent;
};

// S11-D11: the v1 Sound Set map is slot-index identity. Role, BPM and Key are
// preview metadata; they never permute a slot and there is no DSP.
using BankPadSlots = std::array<PadSlot, kBankPadCount>;

// #465 Q2: the only two answers to an occupied target Pad.
enum class OccupiedPadPolicy : std::uint8_t {
  keep,
  replace,
};

struct SoundSetProposedPad {
  std::uint8_t slot_index{};
  std::uint8_t pad{};
  foundation::ArtifactRef artifact;

  bool operator==(const SoundSetProposedPad&) const = default;
};

// `proposed` is every occupied Set slot in slot order, `collisions` the subset
// whose target Pad already holds an Asset, and `kept` every target Pad the map
// leaves alone — S11-D12: an empty Set slot is not a wipe instruction.
struct SoundSetMapping {
  std::vector<SoundSetProposedPad> proposed;
  std::vector<std::uint8_t> collisions;
  std::vector<std::uint8_t> kept;

  bool operator==(const SoundSetMapping&) const = default;
};

SoundSetMapping map_soundset(
    const foundation::SoundSetManifest& manifest,
    const BankPadSlots& pads);

// Omitting the policy while `collisions` is non-empty is
// `soundset_occupied_conflict` and zero Project change.
foundation::Result<std::vector<SoundSetProposedPad>>
resolve_soundset_write_set(
    const SoundSetMapping& mapping,
    const std::optional<OccupiedPadPolicy>& policy);

struct SoundSetInstallAssignment {
  PadSlotId slot;
  Asset asset;

  bool operator==(const SoundSetInstallAssignment&) const = default;
};

// One command, one CommandMeta, one revision: every Asset and Pad assignment
// of an install lands together or not at all.
struct InstallSoundSet {
  CommandMeta meta;
  std::vector<SoundSetInstallAssignment> assignments;
};

// Explicit atomic adoption, independent of Sound Set mapping semantics.
struct CandidateAdoptionAssignment {
  PadSlotId slot;
  Asset asset;
  bool operator==(const CandidateAdoptionAssignment&) const = default;
};
struct AdoptCandidates {
  CommandMeta meta;
  foundation::ProjectId project_id;
  foundation::AssetId source_asset_id;
  foundation::ArtifactRef source_artifact;
  std::vector<CandidateAdoptionAssignment> assignments;
};
foundation::Result<void> validate_candidate_source(
    const ProjectState& state, const foundation::ProjectId& project_id,
    std::uint64_t expected_revision, const foundation::AssetId& source_asset_id,
    const foundation::ArtifactRef& source_artifact);

using Command = std::variant<
    ImportAsset,
    AssignPad,
    CreatePattern,
    AssignPatternSlot,
    ClearPatternSlot,
    MovePatternSlot,
    MergePatternEvents,
    UpdateSequenceSettings>;

struct AppliedCommand;
struct CommandReceipt;

foundation::Result<AppliedCommand> apply(
    const ProjectState& state, const AdoptCandidates& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const ImportAssignSample& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const InstallSoundSet& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const UpdatePadPlayback& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const ResetPadPlayback& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);

}  // namespace lmdj::domain
