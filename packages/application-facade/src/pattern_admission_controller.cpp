#include "pattern_admission_controller.hpp"

#include <utility>

namespace lmdj::facade::detail {

PatternEventReducer::PatternEventReducer(
    std::uint8_t bars, bool quantize_enabled, std::uint8_t swing_percent,
    std::uint64_t& generation, std::vector<domain::PatternEvent>& events,
    std::map<domain::PadSlotId, PatternOwnedPress>& pressed)
    : bars_(bars), quantize_enabled_(quantize_enabled),
      swing_percent_(swing_percent), generation_(generation), events_(events),
      pressed_(pressed) {}

void PatternEventReducer::merge_pending(domain::PatternEvent event) {
  auto merged = domain::merge_pattern_events(events_, {std::move(event)});
  if (merged != events_) {
    events_ = std::move(merged);
    ++generation_;
  }
}

void PatternEventReducer::finalize_pressed(
    domain::PadSlotId slot, std::uint64_t raw_release_tick, bool remove_press) {
  const auto found = pressed_.find(slot);
  if (found == pressed_.end()) {
    return;
  }
  merge_pending(domain::PatternEvent{
      slot, found->second.onset_tick,
      domain::normalize_duration_tick(
          found->second.raw_attack_tick, raw_release_tick,
          found->second.onset_tick, domain::pattern_length_ticks(bars_)),
      found->second.velocity});
  if (remove_press) {
    pressed_.erase(found);
  }
}

void PatternEventReducer::press(
    domain::PadSlotId slot, std::uint64_t raw_attack_tick, std::uint8_t velocity,
    std::optional<std::uint64_t> correlation) {
  finalize_pressed(slot, raw_attack_tick, true);
  pressed_.insert_or_assign(slot, PatternOwnedPress{
      raw_attack_tick,
      domain::quantize_onset_tick(raw_attack_tick,
          domain::pattern_length_ticks(bars_), quantize_enabled_, swing_percent_),
      velocity, correlation});
}

bool PatternEventReducer::release(
    domain::PadSlotId slot, std::uint64_t raw_release_tick,
    std::optional<std::uint64_t> correlation) {
  const auto found = pressed_.find(slot);
  if (found == pressed_.end() ||
      (correlation.has_value() && found->second.correlation != correlation)) {
    return false;
  }
  finalize_pressed(slot, raw_release_tick, true);
  return true;
}

std::vector<domain::PatternEvent> PatternEventReducer::recoverable_tail() const {
  auto result = events_;
  const auto loop_length = domain::pattern_length_ticks(bars_);
  for (const auto& [slot, press] : pressed_) {
    result = domain::merge_pattern_events(result, {domain::PatternEvent{
        slot, press.onset_tick,
        domain::normalize_duration_tick(
            press.raw_attack_tick, press.raw_attack_tick + domain::kSixteenthTicks,
            press.onset_tick, loop_length),
        press.velocity}});
  }
  return result;
}

void PatternEventReducer::finalize_unreleased(bool clear) {
  std::vector<domain::PadSlotId> slots;
  slots.reserve(pressed_.size());
  for (const auto& [slot, press] : pressed_) {
    (void)press;
    slots.push_back(slot);
  }
  for (const auto slot : slots) {
    const auto attack = pressed_.at(slot).raw_attack_tick;
    finalize_pressed(slot, attack + domain::kSixteenthTicks, clear);
  }
}

}  // namespace lmdj::facade::detail
