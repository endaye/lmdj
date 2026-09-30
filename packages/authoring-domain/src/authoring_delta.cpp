#include <lmdj/domain/authoring_delta.hpp>

#include <algorithm>
#include <limits>
#include <set>
#include <utility>

namespace lmdj::domain {
namespace {
foundation::Error conflict() {
  return {foundation::ErrorCode::revision_conflict,
          "Authoring history no longer matches the current Project content",
          {{"reason", "authoring_history_conflict"},
           {"remedy", "reopen the Project to start a new authoring session"}}};
}
foundation::Error invalid() {
  return {foundation::ErrorCode::invalid_argument,
          "Authoring change must preserve valid Project content and identity"};
}
template <class T>
std::optional<AuthoringChange<T>> difference(const T& before, const T& after) {
  if (before == after) return std::nullopt;
  return AuthoringChange<T>{before, after};
}
template <class K, class V>
std::optional<V> lookup(const std::map<K, V>& values, const K& key) {
  const auto found = values.find(key);
  return found == values.end() ? std::nullopt : std::optional<V>{found->second};
}
template <class K, class V>
auto map_difference(const std::map<K, V>& before, const std::map<K, V>& after) {
  std::map<K, AuthoringChange<std::optional<V>>> result;
  for (const auto& [key, value] : before) {
    const auto next = lookup(after, key);
    if (next != std::optional<V>{value}) result.emplace(key, AuthoringChange<std::optional<V>>{value, next});
  }
  for (const auto& [key, value] : after) {
    if (!before.contains(key)) result.emplace(key, AuthoringChange<std::optional<V>>{std::nullopt, value});
  }
  return result;
}
template <class T>
bool change_value(T& value, const std::optional<AuthoringChange<T>>& change) {
  if (!change) return true;
  if (value != change->before || change->before == change->after) return false;
  value = change->after;
  return true;
}
template <class K, class V>
bool change_map(std::map<K, V>& values,
                const std::map<K, AuthoringChange<std::optional<V>>>& changes) {
  for (const auto& [key, change] : changes) {
    if (lookup(values, key) != change.before || change.before == change.after) return false;
    if (change.after) values.insert_or_assign(key, *change.after);
    else values.erase(key);
  }
  return true;
}
template <class T>
bool compose_value(std::optional<AuthoringChange<T>>& first,
                   const std::optional<AuthoringChange<T>>& second) {
  if (!second) return true;
  if (!first) { first = second; return true; }
  if (first->after != second->before) return false;
  first->after = second->after;
  if (first->before == first->after) first.reset();
  return true;
}
template <class K, class V>
bool compose_map(std::map<K, AuthoringChange<V>>& first,
                 const std::map<K, AuthoringChange<V>>& second) {
  for (const auto& [key, change] : second) {
    const auto found = first.find(key);
    if (found == first.end()) { first.emplace(key, change); continue; }
    if (found->second.after != change.before) return false;
    found->second.after = change.after;
    if (found->second.before == found->second.after) first.erase(found);
  }
  return true;
}
template <class Values> void reverse_map(Values& values) {
  for (auto& [key, value] : values) {
    (void)key;
    std::swap(value.before, value.after);
  }
}
template <class T> void reverse_optional(std::optional<AuthoringChange<T>>& change) {
  if (change) std::swap(change->before, change->after);
}

bool valid_content(const ProjectState& state) {
  if (state.bpm < 40 || state.bpm > 240 ||
      state.swing_percent < kSwingPercentMin || state.swing_percent > kSwingPercentMax ||
      !validate_pattern_slots(state).has_value()) return false;
  for (const auto& [id, asset] : state.assets) {
    if (id != asset.id || !is_valid_uuid(id.value()) ||
        asset.artifact.sha256.size() != 64 || asset.artifact.media_type.empty() ||
        !std::ranges::all_of(asset.artifact.sha256, [](char c) {
          return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        }) || (asset.lineage && !validate_asset_lineage(*asset.lineage).has_value())) return false;
  }
  for (std::size_t b = 0; b < state.banks.size(); ++b) {
    for (std::size_t p = 0; p < state.banks[b].size(); ++p) {
      const auto& pad = state.banks[b][p];
      const auto& playback = pad.playback;
      if (pad.id.bank != b || pad.id.pad != p ||
          (pad.asset_id && !state.assets.contains(*pad.asset_id)) ||
          playback.gain_millidb < -60000 || playback.gain_millidb > 6000 ||
          (playback.trim_end_frame && *playback.trim_end_frame <= playback.trim_start_frame)) return false;
      switch (playback.trigger_mode) {
        case TriggerMode::one_shot: case TriggerMode::gate:
        case TriggerMode::loop_gate: case TriggerMode::loop_toggle: break;
        default: return false;
      }
    }
  }
  for (const auto& [id, pattern] : state.patterns) {
    if (id != pattern.id || !is_valid_uuid(id.value()) ||
        (pattern.bars != 1 && pattern.bars != 2 && pattern.bars != 4 && pattern.bars != 8)) return false;
    const auto limit = pattern_length_ticks(pattern.bars);
    for (const auto& event : pattern.events) {
      if (!is_valid_slot(event.slot) || event.velocity < 1 || event.velocity > 127 ||
          event.onset_tick >= limit || event.duration_tick == 0 ||
          event.duration_tick > limit - event.onset_tick) return false;
    }
  }
  for (const auto& [id, performance] : state.performances) {
    if (id != performance.id || !validate_performance(performance).has_value()) return false;
  }
  return true;
}
}  // namespace

bool AuthoringDelta::empty() const noexcept {
  return !bpm && !quantize_enabled && !swing_percent && pads.empty() &&
      assets.empty() && patterns.empty() && performances.empty() && pattern_slots.empty();
}

foundation::Result<AuthoringDelta> authoring_difference(
    const ProjectState& before, const ProjectState& after) {
  if (before.id != after.id) return foundation::Result<AuthoringDelta>::failure(conflict());
  AuthoringDelta delta{before.id, difference(before.bpm, after.bpm),
                      difference(before.quantize_enabled, after.quantize_enabled),
                      difference(before.swing_percent, after.swing_percent), {},
                      map_difference(before.assets, after.assets),
                      map_difference(before.patterns, after.patterns),
                      map_difference(before.performances, after.performances), {}};
  for (std::size_t b = 0; b < before.banks.size(); ++b) {
    for (std::size_t p = 0; p < before.banks[b].size(); ++p) {
      if (before.banks[b][p] != after.banks[b][p])
        delta.pads.push_back({before.banks[b][p], after.banks[b][p]});
    }
  }
  for (std::size_t i = 0; i < before.pattern_slots.size(); ++i) {
    if (before.pattern_slots[i] != after.pattern_slots[i])
      delta.pattern_slots.emplace(static_cast<std::uint8_t>(i),
          AuthoringChange<std::optional<foundation::PatternId>>{before.pattern_slots[i], after.pattern_slots[i]});
  }
  return foundation::Result<AuthoringDelta>::success(std::move(delta));
}

AuthoringDelta reverse_authoring_delta(AuthoringDelta delta) {
  reverse_optional(delta.bpm); reverse_optional(delta.quantize_enabled);
  reverse_optional(delta.swing_percent);
  for (auto& change : delta.pads) std::swap(change.before, change.after);
  reverse_map(delta.assets); reverse_map(delta.patterns);
  reverse_map(delta.performances); reverse_map(delta.pattern_slots);
  return delta;
}

foundation::Result<AuthoringDelta> compose_authoring_deltas(
    const AuthoringDelta& first, const AuthoringDelta& second) {
  auto result = first;
  if (first.project_id != second.project_id ||
      !compose_value(result.bpm, second.bpm) ||
      !compose_value(result.quantize_enabled, second.quantize_enabled) ||
      !compose_value(result.swing_percent, second.swing_percent) ||
      !compose_map(result.assets, second.assets) ||
      !compose_map(result.patterns, second.patterns) ||
      !compose_map(result.performances, second.performances) ||
      !compose_map(result.pattern_slots, second.pattern_slots))
    return foundation::Result<AuthoringDelta>::failure(conflict());
  for (const auto& next : second.pads) {
    const auto found = std::ranges::find_if(result.pads, [&](const auto& old) {
      return old.before.id == next.before.id;
    });
    if (found == result.pads.end()) { result.pads.push_back(next); continue; }
    if (found->after != next.before) return foundation::Result<AuthoringDelta>::failure(conflict());
    found->after = next.after;
    if (found->before == found->after) result.pads.erase(found);
  }
  std::ranges::sort(result.pads, {}, [](const auto& change) {
    return change.before.id.bank * 16 + change.before.id.pad;
  });
  return foundation::Result<AuthoringDelta>::success(std::move(result));
}

foundation::Result<AppliedCommand> apply(
    const ProjectState& state, const ApplyAuthoringDelta& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts) {
  using Result = foundation::Result<AppliedCommand>;
  if (!is_valid_uuid(command.meta.command_id.value()) || command.delta.empty()) return Result::failure(invalid());
  const auto receipt = receipts.find(command.meta.command_id);
  if (receipt != receipts.end()) return Result::success({state, receipt->second.event, true});
  if (state.id != command.delta.project_id || state.revision != command.meta.expected_revision)
    return Result::failure(conflict());
  if (state.revision == std::numeric_limits<std::uint64_t>::max()) return Result::failure(invalid());
  auto next = state;
  const auto& delta = command.delta;
  if (!change_value(next.bpm, delta.bpm) ||
      !change_value(next.quantize_enabled, delta.quantize_enabled) ||
      !change_value(next.swing_percent, delta.swing_percent) ||
      !change_map(next.assets, delta.assets) || !change_map(next.patterns, delta.patterns) ||
      !change_map(next.performances, delta.performances)) return Result::failure(conflict());
  std::set<unsigned> seen;
  for (const auto& change : delta.pads) {
    const auto slot = change.before.id;
    if (!is_valid_slot(slot) || slot != change.after.id ||
        !seen.insert(slot.bank * 16U + slot.pad).second || change.before == change.after) return Result::failure(invalid());
    auto& pad = next.banks[slot.bank][slot.pad];
    if (pad != change.before) return Result::failure(conflict());
    pad = change.after;
  }
  for (const auto& [slot, change] : delta.pattern_slots) {
    if (slot >= kPatternSlotCount || change.before == change.after) return Result::failure(invalid());
    if (next.pattern_slots[slot] != change.before) return Result::failure(conflict());
    next.pattern_slots[slot] = change.after;
  }
  if (!valid_content(next)) return Result::failure(invalid());
  ++next.revision;
  const auto revision = next.revision;
  return Result::success({std::move(next),
      {{"type", "project.history_applied"}, {"command_id", command.meta.command_id.value()},
       {"revision", revision}}, false});
}
}  // namespace lmdj::domain
