#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::audio {

class RealtimeEngine;

inline constexpr std::uint32_t kTransportPpq = 960;
inline constexpr std::uint32_t kTransportSampleRate = 48'000;
inline constexpr std::uint64_t kTickDenominator = 2'880'000;
static_assert(
    kTickDenominator ==
    static_cast<std::uint64_t>(kTransportSampleRate) * 60U);

constexpr std::optional<std::uint64_t> integrate_tick_numerator(
    std::uint64_t anchor_numerator,
    std::uint64_t frame_delta,
    std::uint16_t bpm,
    std::uint32_t ppq = kTransportPpq) noexcept {
  const auto rate = static_cast<std::uint64_t>(bpm) * ppq;
  if (rate == 0 ||
      frame_delta >
          (std::numeric_limits<std::uint64_t>::max() - anchor_numerator) /
              rate) {
    return std::nullopt;
  }
  return anchor_numerator + frame_delta * rate;
}

constexpr std::uint64_t whole_tick(
    std::uint64_t tick_numerator) noexcept {
  return tick_numerator / kTickDenominator;
}

struct TransportAnchor {
  std::uint64_t runtime_frame{};
  std::uint64_t tick_numerator{};
  std::uint16_t bpm{};

  bool operator==(const TransportAnchor&) const = default;
};

foundation::Result<std::uint64_t> tick_numerator_at(
    const TransportAnchor& anchor,
    std::uint64_t runtime_frame) noexcept;
foundation::Result<std::uint64_t> raw_tick_at(
    const TransportAnchor& anchor,
    std::uint64_t runtime_frame) noexcept;
foundation::Result<TransportAnchor> freeze_transport_bpm(
    const TransportAnchor& anchor,
    std::uint64_t runtime_frame,
    std::uint16_t new_bpm) noexcept;
foundation::Result<std::uint64_t> tick_boundary_frame(
    std::uint64_t tick,
    std::uint16_t bpm,
    std::uint32_t ppq = kTransportPpq) noexcept;

struct PreparedSampleMaterialView {
  const std::int16_t* interleaved{};
  std::uint32_t frame_count{};
  std::uint16_t channels{};

  bool operator==(const PreparedSampleMaterialView&) const = default;
};

static_assert(std::is_trivially_copyable_v<PreparedSampleMaterialView>);

constexpr float prepared_pcm16_to_float(std::int16_t value) noexcept {
  return value < 0 ? static_cast<float>(value) / 32768.0F
                   : static_cast<float>(value) / 32767.0F;
}

inline float prepared_material_sample(PreparedSampleMaterialView material,
                                      std::uint32_t frame) noexcept {
  const auto index = static_cast<std::size_t>(frame) * material.channels;
  const auto first = prepared_pcm16_to_float(material.interleaved[index]);
  return material.channels == 1
             ? first
             : (first +
                prepared_pcm16_to_float(material.interleaved[index + 1])) *
                   0.5F;
}

struct PreparedPatternEvent {
  domain::PadSlotId slot;
  std::uint32_t onset_tick{};
  std::uint32_t duration_tick{};
  std::uint8_t velocity{};
  std::uint64_t start_frame{};
  std::uint64_t release_frame{};
  PreparedSampleMaterialView material{};
  cooker::ResolvedPlayback playback{};

  // Material equality is view identity plus bounds; it never scans PCM.
  bool operator==(const PreparedPatternEvent& other) const noexcept {
    return slot == other.slot && onset_tick == other.onset_tick &&
           duration_tick == other.duration_tick && velocity == other.velocity &&
           start_frame == other.start_frame &&
           release_frame == other.release_frame && material == other.material &&
           playback.start_frame == other.playback.start_frame &&
           playback.end_frame == other.playback.end_frame &&
           playback.trigger_mode == other.playback.trigger_mode &&
           playback.linear_gain == other.playback.linear_gain &&
           playback.muted == other.playback.muted;
  }
};

class PreparedPatternView final {
 public:
  PreparedPatternView(PreparedPatternView&&) noexcept = default;
  PreparedPatternView& operator=(PreparedPatternView&&) noexcept = default;
  PreparedPatternView(const PreparedPatternView&) = delete;
  PreparedPatternView& operator=(const PreparedPatternView&) = delete;

  static foundation::Result<PreparedPatternView> from_snapshot(
      const cooker::RuntimeSnapshot& snapshot);
  // Strict canonical event order, no overlay/map merge workspace. Invalid or
  // duplicate keys are rejected rather than normalized.
  static foundation::Result<PreparedPatternView> from_canonical_snapshot(
      const cooker::RuntimeSnapshot& snapshot);
  static foundation::Result<PreparedPatternView> from_snapshot_with_overlay(
      const cooker::RuntimeSnapshot& snapshot,
      std::span<const domain::PatternEvent> journal_overlay);

  const foundation::ProjectId& project_id() const noexcept;
  const foundation::PatternId& pattern_id() const noexcept;
  std::uint64_t project_revision() const noexcept;
  std::uint16_t bpm() const noexcept;
  std::uint32_t ppq() const noexcept;
  std::uint32_t loop_length_ticks() const noexcept;
  std::uint64_t loop_frames() const noexcept;
  std::uint64_t bar_frames() const noexcept;
  const std::vector<PreparedPatternEvent>& events() const noexcept;
  bool has_overlay() const noexcept;

 private:
  static foundation::Result<PreparedPatternView> prepare(
      const cooker::RuntimeSnapshot& snapshot,
      std::span<const domain::PatternEvent> journal_overlay,
      bool canonical = false);
  PreparedPatternView(
      foundation::ProjectId project_id,
      foundation::PatternId pattern_id,
      std::uint64_t project_revision,
      std::uint16_t bpm,
      std::uint32_t ppq,
      std::uint32_t loop_length_ticks,
      std::uint64_t loop_frames,
      std::uint64_t bar_frames,
      std::vector<PreparedPatternEvent> events,
      std::vector<std::shared_ptr<const cooker::PcmSample>> material_owners,
      bool has_overlay);

  foundation::ProjectId project_id_;
  foundation::PatternId pattern_id_;
  std::uint64_t project_revision_{};
  std::uint16_t bpm_{};
  std::uint32_t ppq_{};
  std::uint32_t loop_length_ticks_{};
  std::uint64_t loop_frames_{};
  std::uint64_t bar_frames_{};
  std::vector<PreparedPatternEvent> events_;
  std::vector<std::shared_ptr<const cooker::PcmSample>> material_owners_;
  bool has_overlay_{};
};

// Identity carried by a Sound Set audition Bank (#799). A nil UUID and
// revision 0, named rather than written at the call site, so a reader who
// finds it in a debugger can tell at once that it is not a Project, and a
// future consumer collides with a name instead of a plausible-looking UUID.
inline constexpr std::string_view kAuditionBankProjectIdValue =
    "00000000-0000-0000-0000-000000000000";
inline constexpr std::uint64_t kAuditionBankProjectRevision = 0;

inline foundation::ProjectId kAuditionBankProjectId() {
  return foundation::ProjectId(std::string{kAuditionBankProjectIdValue});
}

class PreparedSampleBank final {
 public:
  PreparedSampleBank(PreparedSampleBank&&) noexcept = default;
  PreparedSampleBank& operator=(PreparedSampleBank&&) noexcept = default;
  PreparedSampleBank(const PreparedSampleBank&) = delete;
  PreparedSampleBank& operator=(const PreparedSampleBank&) = delete;

  static foundation::Result<PreparedSampleBank> from_snapshot(
      const cooker::RuntimeSnapshot& snapshot);
  static foundation::Result<PreparedSampleBank> from_snapshot(
      const cooker::RuntimeSnapshot& snapshot,
      const RuntimePreparationLimits& limits);
  static PreparedSampleBank empty(foundation::ProjectId project_id,
                                  std::uint64_t project_revision);

  foundation::Result<void> set_sample(std::uint8_t slot,
                                      std::span<const float> mono_pcm);
  foundation::Result<void> set_sample(
      std::uint8_t slot,
      std::span<const float> mono_pcm,
      cooker::ResolvedPlayback playback);

  // Diagnostic only. Nothing in the engine reads this to make a decision; it
  // exists so a Bank in a debugger can be traced back to what produced it.
  //
  // A Sound Set audition Bank (#799) is not produced by a Project and carries
  // `kAuditionBankProjectId` with revision `kAuditionBankProjectRevision`. If
  // you are about to key a decision off this accessor, that sentinel is why
  // you must not: an audition Bank would answer with a Project identity that
  // names no Project.
  const foundation::ProjectId& project_id() const noexcept;
  std::uint64_t project_revision() const noexcept;
  std::uint64_t availability_mask() const noexcept;
  std::size_t sample_count() const noexcept;
  std::uint64_t decoded_pcm_bytes() const noexcept;

 private:
  PreparedSampleBank(foundation::ProjectId project_id,
                     std::uint64_t project_revision);

  friend class RealtimeEngine;
  const std::vector<float>& sample(std::uint8_t slot) const noexcept;
  const cooker::ResolvedPlayback& playback(std::uint8_t slot) const noexcept;

  foundation::ProjectId project_id_;
  std::uint64_t project_revision_;
  std::uint64_t availability_mask_ = 0;
  std::uint64_t decoded_pcm_bytes_ = 0;
  std::array<std::vector<float>, 64> samples_;
  std::array<cooker::ResolvedPlayback, 64> playbacks_{};
};

}  // namespace lmdj::audio
