#include <lmdj/domain/command_handler.hpp>

#include <algorithm>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <variant>

namespace lmdj::domain {
namespace {

foundation::Result<AppliedCommand> invalid(std::string_view message) {
  return foundation::Result<AppliedCommand>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

bool valid_velocity(std::uint8_t velocity) {
  return velocity >= 1 && velocity <= 127;
}

bool valid_bars(std::uint8_t bars) {
  return bars == 1 || bars == 2 || bars == 4 || bars == 8;
}

bool valid_sha256(std::string_view value) {
  if (value.size() != 64) {
    return false;
  }
  for (const char character : value) {
    if (!((character >= '0' && character <= '9') ||
          (character >= 'a' && character <= 'f'))) {
      return false;
    }
  }
  return true;
}

bool valid_artifact(const foundation::ArtifactRef& artifact) {
  return valid_sha256(artifact.sha256) && !artifact.media_type.empty();
}

bool valid_trigger_mode(TriggerMode trigger_mode) {
  switch (trigger_mode) {
    case TriggerMode::one_shot:
    case TriggerMode::gate:
    case TriggerMode::loop_gate:
    case TriggerMode::loop_toggle:
      return true;
  }
  return false;
}

bool valid_playback(const PadPlayback& playback) {
  return playback.gain_millidb >= -60000 &&
         playback.gain_millidb <= 6000 &&
         valid_trigger_mode(playback.trigger_mode) &&
         (!playback.trim_end_frame.has_value() ||
          *playback.trim_end_frame > playback.trim_start_frame);
}

foundation::Result<void> validate_pattern(const Pattern& pattern) {
  if (!is_valid_uuid(pattern.id.value())) {
    return foundation::Result<void>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "pattern id must be a lowercase UUID",
        });
  }
  if (!valid_bars(pattern.bars)) {
    return foundation::Result<void>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "pattern bars must be one of 1, 2, 4, or 8",
        });
  }
  const auto tick_limit = pattern_length_ticks(pattern.bars);
  for (const auto& event : pattern.events) {
    if (!is_valid_slot(event.slot) || !valid_velocity(event.velocity) ||
        event.onset_tick >= tick_limit || event.duration_tick == 0 ||
        event.duration_tick > tick_limit - event.onset_tick) {
      return foundation::Result<void>::failure(
          foundation::Error{
              foundation::ErrorCode::invalid_argument,
              "pattern event is invalid",
          });
    }
  }
  return foundation::Result<void>::success();
}

nlohmann::json command_event(
    std::string_view type,
    const CommandMeta& meta,
    std::uint64_t revision) {
  return {
      {"command_id", meta.command_id.value()},
      {"revision", revision},
      {"type", type},
  };
}

AppliedCommand applied(
    ProjectState state,
    std::string_view type,
    const CommandMeta& meta,
    ProjectContract contract = ProjectContract::v3) {
  state.contract = std::max(state.contract, contract);
  ++state.revision;
  const auto committed_revision = state.revision;
  return AppliedCommand{
      std::move(state),
      command_event(type, meta, committed_revision),
      false,
  };
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const AssignPatternSlot& command) {
  const auto current = validate_pattern_slots(state);
  if (!current.has_value()) {
    return invalid(current.error().message);
  }
  if (command.slot >= kPatternSlotCount) {
    return invalid("Pattern slot is out of range");
  }
  if (!is_valid_uuid(command.pattern_id.value()) ||
      !state.patterns.contains(command.pattern_id)) {
    return invalid("assigned Pattern does not exist");
  }
  if (state.pattern_slots.at(command.slot).has_value()) {
    return invalid("Pattern slot is already occupied");
  }
  if (std::ranges::find(
          state.pattern_slots,
          std::optional<foundation::PatternId>{command.pattern_id}) !=
      state.pattern_slots.end()) {
    return invalid("Pattern is already assigned to a slot");
  }
  auto copy = state;
  copy.pattern_slots.at(command.slot) = command.pattern_id;
  auto result = applied(
      std::move(copy),
      "pattern.slot_assigned",
      command.meta,
      ProjectContract::v4);
  result.event["pattern_id"] = command.pattern_id.value();
  result.event["pattern_slot"] = command.slot;
  return foundation::Result<AppliedCommand>::success(std::move(result));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const ClearPatternSlot& command) {
  const auto current = validate_pattern_slots(state);
  if (!current.has_value()) {
    return invalid(current.error().message);
  }
  if (command.slot >= kPatternSlotCount) {
    return invalid("Pattern slot is out of range");
  }
  if (!state.pattern_slots.at(command.slot).has_value()) {
    return invalid("Pattern slot is empty");
  }
  const auto pattern_id = *state.pattern_slots.at(command.slot);
  auto copy = state;
  copy.pattern_slots.at(command.slot) = std::nullopt;
  auto result = applied(
      std::move(copy),
      "pattern.slot_cleared",
      command.meta,
      ProjectContract::v4);
  result.event["pattern_id"] = pattern_id.value();
  result.event["pattern_slot"] = command.slot;
  return foundation::Result<AppliedCommand>::success(std::move(result));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const MovePatternSlot& command) {
  const auto current = validate_pattern_slots(state);
  if (!current.has_value()) {
    return invalid(current.error().message);
  }
  if (command.from_slot >= kPatternSlotCount ||
      command.to_slot >= kPatternSlotCount) {
    return invalid("Pattern slot is out of range");
  }
  if (command.from_slot == command.to_slot) {
    return invalid("Pattern slot move requires different slots");
  }
  if (!state.pattern_slots.at(command.from_slot).has_value()) {
    return invalid("Pattern slot move source is empty");
  }
  if (state.pattern_slots.at(command.to_slot).has_value()) {
    return invalid("Pattern slot move target is occupied");
  }
  const auto pattern_id = *state.pattern_slots.at(command.from_slot);
  auto copy = state;
  copy.pattern_slots.at(command.from_slot) = std::nullopt;
  copy.pattern_slots.at(command.to_slot) = pattern_id;
  auto result = applied(
      std::move(copy),
      "pattern.slot_moved",
      command.meta,
      ProjectContract::v4);
  result.event["from_slot"] = command.from_slot;
  result.event["pattern_id"] = pattern_id.value();
  result.event["to_slot"] = command.to_slot;
  return foundation::Result<AppliedCommand>::success(std::move(result));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const ImportAsset& command) {
  if (!is_valid_uuid(command.asset.id.value())) {
    return invalid("asset id must be a lowercase UUID");
  }
  if (!valid_artifact(command.asset.artifact)) {
    return invalid("artifact reference is invalid");
  }
  if (command.asset.lineage) {
    const auto valid = validate_asset_lineage(*command.asset.lineage);
    if (!valid.has_value()) {
      return foundation::Result<AppliedCommand>::failure(valid.error());
    }
    if (state.contract < ProjectContract::v4 ||
        (asset_lineage_derivation_kind(*command.asset.lineage) ==
             AssetLineageDerivationKind::capability_adoption &&
         state.contract < ProjectContract::v5)) {
      return invalid("Asset Lineage is not supported by this Project Contract");
    }
  }
  if (state.assets.contains(command.asset.id)) {
    return foundation::Result<AppliedCommand>::failure(
        foundation::Error{
            foundation::ErrorCode::duplicate_id,
            "asset id already exists",
        });
  }
  auto copy = state;
  copy.assets.emplace(command.asset.id, command.asset);
  return foundation::Result<AppliedCommand>::success(
      applied(std::move(copy), "asset.imported", command.meta));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const AssignPad& command) {
  if (!is_valid_slot(command.slot)) {
    return invalid("pad slot is invalid");
  }
  if (command.asset_id.has_value() &&
      !is_valid_uuid(command.asset_id->value())) {
    return invalid("asset id must be a lowercase UUID");
  }
  if (command.asset_id.has_value() &&
      !state.assets.contains(*command.asset_id)) {
    return foundation::Result<AppliedCommand>::failure(
        foundation::Error{
            foundation::ErrorCode::missing_asset,
            "assigned asset does not exist",
        });
  }
  auto copy = state;
  auto& pad = copy.banks.at(command.slot.bank).at(command.slot.pad);
  const bool resets_playback =
      !command.asset_id.has_value() || pad.asset_id != command.asset_id;
  pad.asset_id = command.asset_id;
  if (resets_playback) {
    pad.playback = PadPlayback{};
  }
  return foundation::Result<AppliedCommand>::success(
      applied(std::move(copy), "pad.assigned", command.meta));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const ImportAssignSample& command) {
  if (!is_valid_slot(command.slot)) {
    return invalid("pad slot is invalid");
  }
  if (!is_valid_uuid(command.asset.id.value())) {
    return invalid("asset id must be a lowercase UUID");
  }
  if (!valid_artifact(command.asset.artifact)) {
    return invalid("artifact reference is invalid");
  }
  if (command.asset.lineage) {
    const auto valid = validate_asset_lineage(*command.asset.lineage);
    if (!valid.has_value()) {
      return foundation::Result<AppliedCommand>::failure(valid.error());
    }
    if (state.contract < ProjectContract::v4 ||
        (asset_lineage_derivation_kind(*command.asset.lineage) ==
             AssetLineageDerivationKind::capability_adoption &&
         state.contract < ProjectContract::v5)) {
      return invalid("Asset Lineage is not supported by this Project Contract");
    }
  }
  if (state.assets.contains(command.asset.id)) {
    return foundation::Result<AppliedCommand>::failure(
        foundation::Error{
            foundation::ErrorCode::duplicate_id,
            "asset id already exists",
        });
  }
  auto copy = state;
  copy.assets.emplace(command.asset.id, command.asset);
  auto& pad = copy.banks.at(command.slot.bank).at(command.slot.pad);
  pad.asset_id = command.asset.id;
  pad.playback = PadPlayback{};
  return foundation::Result<AppliedCommand>::success(
      applied(std::move(copy), "sample.imported_assigned", command.meta));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const InstallSoundSet& command) {
  if (state.contract < ProjectContract::v4) {
    return invalid(
        "installing a Sound Set requires lmdj.project.v4 Project Truth");
  }
  if (command.assignments.empty()) {
    return invalid("installing a Sound Set needs at least one assignment");
  }
  const auto bank = command.assignments.front().slot.bank;
  std::set<std::uint8_t> pads;
  std::set<foundation::AssetId> asset_ids;
  std::optional<SoundSetLineageSource> set_identity;
  for (const auto& assignment : command.assignments) {
    if (!is_valid_slot(assignment.slot)) {
      return invalid("pad slot is invalid");
    }
    if (assignment.slot.bank != bank) {
      return invalid("a Sound Set install targets exactly one Bank");
    }
    if (!pads.insert(assignment.slot.pad).second) {
      return invalid("a Sound Set install assigns each Pad at most once");
    }
    if (!is_valid_uuid(assignment.asset.id.value())) {
      return invalid("asset id must be a lowercase UUID");
    }
    if (!asset_ids.insert(assignment.asset.id).second) {
      return invalid("a Sound Set install introduces each asset id once");
    }
    if (!valid_artifact(assignment.asset.artifact)) {
      return invalid("artifact reference is invalid");
    }
    if (state.assets.contains(assignment.asset.id)) {
      return foundation::Result<AppliedCommand>::failure(
          foundation::Error{
              foundation::ErrorCode::duplicate_id,
              "asset id already exists",
          });
    }
    if (!assignment.asset.lineage.has_value()) {
      return invalid("an installed Sound Set slot must carry soundset Lineage");
    }
    const auto& lineage = *assignment.asset.lineage;
    const auto* source = std::get_if<SoundSetLineageSource>(&lineage.source);
    if (source == nullptr ||
        !std::holds_alternative<SoundSetInstallLineageDerivation>(
            lineage.derivation)) {
      return invalid("an installed Sound Set slot must carry soundset Lineage");
    }
    const auto valid_lineage = validate_asset_lineage(lineage);
    if (!valid_lineage.has_value()) {
      return invalid(valid_lineage.error().message);
    }
    // S11-D11: the map is slot-index identity, so the recorded Set slot is the
    // target Pad, and S11-D9 pins the Lineage digest to the Asset it describes.
    if (source->slot_index != assignment.slot.pad) {
      return invalid(
          "soundset Lineage slot index must match the installed Pad Slot");
    }
    if (source->artifact_sha256 != assignment.asset.artifact.sha256) {
      return invalid(
          "soundset Lineage artifact digest must match the installed Asset");
    }
    if (!set_identity.has_value()) {
      set_identity = *source;
    } else if (
        set_identity->set_id != source->set_id ||
        set_identity->set_version != source->set_version ||
        set_identity->manifest_sha256 != source->manifest_sha256) {
      return invalid("a Sound Set install carries exactly one Set identity");
    }
  }
  auto copy = state;
  for (const auto& assignment : command.assignments) {
    copy.assets.emplace(assignment.asset.id, assignment.asset);
    auto& pad = copy.banks.at(assignment.slot.bank).at(assignment.slot.pad);
    pad.asset_id = assignment.asset.id;
    pad.playback = PadPlayback{};
  }
  return foundation::Result<AppliedCommand>::success(
      applied(
          std::move(copy),
          "soundset.installed",
          command.meta,
          ProjectContract::v4));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const UpdatePadPlayback& command) {
  if (!is_valid_slot(command.slot)) {
    return invalid("pad slot is invalid");
  }
  if (!valid_playback(command.playback)) {
    return invalid("pad playback is invalid");
  }
  auto copy = state;
  copy.banks.at(command.slot.bank).at(command.slot.pad).playback =
      command.playback;
  return foundation::Result<AppliedCommand>::success(
      applied(std::move(copy), "pad.playback_updated", command.meta));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const ResetPadPlayback& command) {
  if (!is_valid_slot(command.slot)) {
    return invalid("pad slot is invalid");
  }
  auto copy = state;
  copy.banks.at(command.slot.bank).at(command.slot.pad).playback = PadPlayback{};
  return foundation::Result<AppliedCommand>::success(
      applied(std::move(copy), "pad.playback_reset", command.meta));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const CreatePattern& command) {
  const auto validation = validate_pattern(command.pattern);
  if (!validation.has_value()) {
    return foundation::Result<AppliedCommand>::failure(validation.error());
  }
  if (state.patterns.contains(command.pattern.id)) {
    return foundation::Result<AppliedCommand>::failure(
        foundation::Error{
            foundation::ErrorCode::duplicate_id,
            "pattern id already exists",
        });
  }
  auto copy = state;
  auto pattern = command.pattern;
  pattern.events = merge_pattern_events({}, pattern.events);
  copy.patterns.emplace(pattern.id, std::move(pattern));
  return foundation::Result<AppliedCommand>::success(
      applied(std::move(copy), "pattern.created", command.meta));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const MergePatternEvents& command) {
  if (!is_valid_uuid(command.pattern_id.value())) {
    return invalid("pattern id must be a lowercase UUID");
  }
  const auto found = state.patterns.find(command.pattern_id);
  if (found == state.patterns.end()) {
    return foundation::Result<AppliedCommand>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "pattern does not exist",
        });
  }
  Pattern incoming{command.pattern_id, found->second.bars, command.events};
  const auto validation = validate_pattern(incoming);
  if (!validation.has_value()) {
    return foundation::Result<AppliedCommand>::failure(validation.error());
  }
  auto copy = state;
  copy.patterns.at(command.pattern_id).events = merge_pattern_events(
      found->second.events, command.events);
  return foundation::Result<AppliedCommand>::success(
      applied(std::move(copy), "pattern.events_merged", command.meta));
}

foundation::Result<AppliedCommand> apply_new_command(
    const ProjectState& state,
    const UpdateSequenceSettings& command) {
  if (!command.bpm.has_value() && !command.quantize_enabled.has_value() &&
      !command.swing_percent.has_value()) {
    return invalid("sequence settings update is empty");
  }
  if (command.bpm.has_value() &&
      (*command.bpm < 40 || *command.bpm > 240)) {
    return invalid("project BPM must be between 40 and 240");
  }
  if (command.swing_percent.has_value() &&
      (*command.swing_percent < kSwingPercentMin ||
       *command.swing_percent > kSwingPercentMax)) {
    return invalid("swing percent must be between 50 and 75");
  }
  auto copy = state;
  if (command.bpm.has_value()) {
    copy.bpm = *command.bpm;
  }
  if (command.quantize_enabled.has_value()) {
    copy.quantize_enabled = *command.quantize_enabled;
  }
  if (command.swing_percent.has_value()) {
    copy.swing_percent = *command.swing_percent;
  }
  return foundation::Result<AppliedCommand>::success(
      applied(std::move(copy), "sequence.settings_updated", command.meta));
}

template <typename CommandType>
foundation::Result<AppliedCommand> apply_checked(
    const ProjectState& state,
    const CommandType& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts) {
  const auto& meta = command.meta;
  if (!is_valid_uuid(meta.command_id.value())) {
    return invalid("command id must be a lowercase UUID");
  }
  const auto receipt = receipts.find(meta.command_id);
  if (receipt != receipts.end()) {
    return foundation::Result<AppliedCommand>::success(
        AppliedCommand{state, receipt->second.event, true});
  }
  if (meta.expected_revision != state.revision) {
    return foundation::Result<AppliedCommand>::failure(
        foundation::Error{
            foundation::ErrorCode::revision_conflict,
            "command expected a different project revision",
            {
                {"actual_revision", state.revision},
                {"expected_revision", meta.expected_revision},
            },
        });
  }
  return apply_new_command(state, command);
}

}  // namespace

SoundSetMapping map_soundset(
    const foundation::SoundSetManifest& manifest,
    const BankPadSlots& pads) {
  SoundSetMapping mapping;
  for (std::size_t index = 0; index < pads.size(); ++index) {
    const auto pad = static_cast<std::uint8_t>(index);
    const auto& slot = manifest.slots.at(index);
    if (!slot.occupied.has_value()) {
      // S11-D12: an empty Set slot proposes nothing and clears nothing.
      mapping.kept.push_back(pad);
      continue;
    }
    mapping.proposed.push_back(
        SoundSetProposedPad{pad, pad, slot.occupied->artifact});
    if (pads.at(index).asset_id.has_value()) {
      mapping.collisions.push_back(pad);
    }
  }
  return mapping;
}

foundation::Result<std::vector<SoundSetProposedPad>>
resolve_soundset_write_set(
    const SoundSetMapping& mapping,
    const std::optional<OccupiedPadPolicy>& policy) {
  using WriteSet = std::vector<SoundSetProposedPad>;
  if (!mapping.collisions.empty() && !policy.has_value()) {
    return foundation::Result<WriteSet>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "installing this Sound Set needs an occupied Pad policy",
            {
                {"collisions", mapping.collisions},
                {"reason", "soundset_occupied_conflict"},
            },
        });
  }
  if (policy.value_or(OccupiedPadPolicy::replace) ==
      OccupiedPadPolicy::replace) {
    return foundation::Result<WriteSet>::success(mapping.proposed);
  }
  WriteSet kept;
  for (const auto& proposed : mapping.proposed) {
    if (std::ranges::find(mapping.collisions, proposed.pad) ==
        mapping.collisions.end()) {
      kept.push_back(proposed);
    }
  }
  return foundation::Result<WriteSet>::success(std::move(kept));
}

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const Command& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts) {
  return std::visit(
      [&state, &receipts](const auto& value) {
        return apply_checked(state, value, receipts);
      },
      command);
}

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const ImportAssignSample& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts) {
  return apply_checked(state, command, receipts);
}

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const InstallSoundSet& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts) {
  return apply_checked(state, command, receipts);
}

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const UpdatePadPlayback& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts) {
  return apply_checked(state, command, receipts);
}

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const ResetPadPlayback& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts) {
  return apply_checked(state, command, receipts);
}

}  // namespace lmdj::domain
