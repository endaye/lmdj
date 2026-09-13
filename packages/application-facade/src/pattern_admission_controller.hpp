#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <vector>

#include <lmdj/domain/project.hpp>

namespace lmdj::facade::detail {

struct PatternOwnedPress {
  std::uint64_t raw_attack_tick{};
  std::uint32_t onset_tick{};
  std::uint8_t velocity{};
  std::optional<std::uint64_t> correlation;
};

// Synchronous, non-owning view of a caller-serialized event overlay. Callers
// supply ticks from their transport anchor; admission and durability stay with
// the journal owner. Legacy Sequence releases omit correlation intentionally.
class PatternEventReducer {
 public:
  PatternEventReducer(
      std::uint8_t bars, bool quantize_enabled, std::uint8_t swing_percent,
      std::uint64_t& generation, std::vector<domain::PatternEvent>& events,
      std::map<domain::PadSlotId, PatternOwnedPress>& pressed);

  void press(domain::PadSlotId slot, std::uint64_t raw_attack_tick,
             std::uint8_t velocity,
             std::optional<std::uint64_t> correlation = std::nullopt);
  bool release(domain::PadSlotId slot, std::uint64_t raw_release_tick,
               std::optional<std::uint64_t> correlation = std::nullopt);
  std::vector<domain::PatternEvent> recoverable_tail() const;
  void finalize_unreleased(bool clear);

 private:
  void merge_pending(domain::PatternEvent event);
  void finalize_pressed(domain::PadSlotId slot, std::uint64_t raw_release_tick,
                        bool remove_press);

  std::uint8_t bars_;
  bool quantize_enabled_;
  std::uint8_t swing_percent_;
  std::uint64_t& generation_;
  std::vector<domain::PatternEvent>& events_;
  std::map<domain::PadSlotId, PatternOwnedPress>& pressed_;
};

}  // namespace lmdj::facade::detail
