#include <lmdj/domain/command_handler.hpp>

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
    const CommandMeta& meta) {
  state.contract = ProjectContract::v3;
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
    const ImportAsset& command) {
  if (!is_valid_uuid(command.asset.id.value())) {
    return invalid("asset id must be a lowercase UUID");
  }
  if (!valid_artifact(command.asset.artifact)) {
    return invalid("artifact reference is invalid");
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
