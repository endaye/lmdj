#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <type_traits>

#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::audio {

inline constexpr std::uint64_t kScheduledPatternSerialMaximum =
    (std::uint64_t{1} << 60U) - 1;
inline constexpr std::size_t kCountInForcedCueCapacity = 8;
inline constexpr std::size_t kCountInCueSpanCapacity = 9;
inline constexpr std::uint64_t kCountInCueEnvelopeFrames = 1'920;

enum class ScheduledPatternPhase : std::uint8_t {
  empty, submitted, preparing, cancel_preparing, armed, starting, applied,
  cancelled, failing, refused,
};
enum class ScheduledPatternSubmit : std::uint8_t {
  accepted, busy, disabled, not_running, stale_generation, stale_frame_epoch,
  stale_epoch, stale_serial, identity_mismatch, invalid_bars, not_stopped,
  exhausted, start_won,
};
enum class ScheduledPatternResult : std::uint8_t { applied, cancelled, refused };

struct ScheduledPatternRecordRequest {
  std::uint64_t runtime_generation{};
  std::uint64_t frame_epoch{};
  std::uint64_t epoch{};
  std::uint64_t serial{};
  std::uint64_t expected_pattern_generation{};
  foundation::PatternId pattern_id;
  std::uint8_t bars{};
};
struct ScheduledPatternCancelRequest {
  std::uint64_t runtime_generation{};
  std::uint64_t frame_epoch{};
  std::uint64_t serial{};
  std::uint64_t epoch{};
};
struct ScheduledPatternRecordReceipt {
  std::uint64_t runtime_generation{};
  std::uint64_t frame_epoch{};
  std::uint64_t serial{};
  std::uint64_t epoch{};
  std::uint64_t pattern_generation{};
  foundation::PatternId pattern_id;
  ScheduledPatternResult result{};
  std::optional<std::uint64_t> effective_frame;
  std::optional<std::uint64_t> origin_frame;
  bool playing{};
};
struct ScheduledPatternRecordStatus {
  std::uint64_t runtime_generation{};
  std::uint64_t frame_epoch{};
  std::uint64_t serial{};
  ScheduledPatternPhase phase{};
  std::uint8_t bars{};
  std::uint16_t bpm{};
  std::uint64_t bar_frames{};
  std::optional<std::uint64_t> count_in_frame;
  std::optional<std::uint64_t> start_frame;
  std::optional<ScheduledPatternRecordReceipt> start_receipt;
  std::optional<ScheduledPatternRecordReceipt> cancel_receipt;
};

// Pointer-free callback ownership. marker_frame is the mathematical phase
// origin; [begin_frame,end_frame) is irrevocably committed to this batch.
// A carried span has marker=false and does not count as another forced cue.
struct CountInCueSpan {
  std::uint64_t marker_frame{};
  std::uint64_t begin_frame{};
  std::uint64_t end_frame{};
  bool accent{};
  bool forced{};
  bool marker{};
};
struct CountInCueBatch {
  std::uint64_t batch_id{};
  std::uint64_t runtime_generation{};
  std::uint64_t frame_epoch{};
  std::uint64_t serial{};
  std::uint64_t begin_frame{};
  std::uint64_t end_frame{};
  std::optional<std::uint64_t> cancellation_frame;
  std::array<CountInCueSpan, kCountInCueSpanCapacity> spans{};
  std::size_t span_count{};
};
static_assert(std::is_trivially_copyable_v<CountInCueBatch>);

enum class PatternInputSubmit : std::uint8_t {
  accepted, disabled, not_running, stale_generation, stale_frame_epoch,
  invalid_input, sample_unavailable, bank_transition, queue_full,
  completion_full, release_full, stale_hold, exhausted,
};
enum class PatternInputDisposition : std::uint8_t {
  voice_started, voice_capacity, toggle_stopped, muted_no_voice,
  release_applied, release_no_voice, invalidated_before_consume,
};
struct PatternInputAuthority {
  std::uint64_t schedule_serial{};
  std::uint64_t transport_epoch{};
  bool recording{};
  bool operator==(const PatternInputAuthority&) const = default;
};
struct PatternInputCommand {
  std::uint64_t runtime_generation{};
  std::uint64_t frame_epoch{};
  std::uint8_t slot{};
  std::uint8_t velocity{};
  bool release{};
  // Nonzero for a physical release; never the legacy release sequence zero.
  std::uint64_t held_press_sequence{};
  // Every held press (including a silent/toggle/one-shot press) reserves its
  // future release. A nonphysical trigger may explicitly select held=false.
  bool held{true};
  cooker::ResolvedPlayback playback{};
};
struct PatternInputAdmission {
  PatternInputSubmit result{};
  std::uint64_t sequence{};
  std::uint64_t acceptance_ordinal{};
  PatternInputAuthority authority{};
};
struct PatternInputCompletion {
  std::uint64_t runtime_generation{};
  std::uint64_t frame_epoch{};
  std::uint64_t sequence{};
  std::uint64_t held_press_sequence{};
  std::uint64_t acceptance_ordinal{};
  std::uint64_t runtime_frame{};
  std::uint8_t slot{};
  PatternInputAuthority authority{};
  PatternInputDisposition disposition{};
};
struct PatternInputProfileStatus {
  bool enabled{};
  std::uint64_t runtime_generation{};
  std::size_t capacity{};
  std::size_t physical_capacity{};
  std::size_t ordinary_pending{};
  std::size_t held_release_reservations{};
  std::size_t retained_completions{};
};
static_assert(std::is_trivially_copyable_v<PatternInputCompletion>);

}  // namespace lmdj::audio
