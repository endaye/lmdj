#pragma once

#include <cstdint>
#include <memory>
#include <type_traits>
#include <vector>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::cooker {

struct PcmSample {
  std::uint32_t sample_rate;
  std::uint16_t channels;
  std::vector<std::int16_t> interleaved;
};

// The resolved per-voice DSP settings of a Pad (lmdj.project.v5 5.1.0 and
// 5.2.0). It is
// integer-only and trivially copyable so it rides every realtime control
// message, and all-zero is neutral: a neutral block renders exactly as the
// playback that predates it. Frame values are 48 kHz output frames.
struct ResolvedVoiceDsp {
  static constexpr std::uint8_t kReverse = 0x01;
  static constexpr std::uint8_t kPingPong = 0x02;

  // Frames from start_frame to where later loop passes resume.
  std::uint32_t loop_start_offset;
  std::uint32_t loop_crossfade_frames;
  std::int16_t pitch_cents;
  std::int8_t pan;
  std::uint8_t flags;
  // Envelope ramp lengths (lmdj.project.v5 5.2.0). Zero, or anything shorter
  // than the 96-frame declick, renders as the declick. The default member
  // initializers keep the 5.1.0 positional form compiling unchanged.
  std::uint32_t attack_frames = 0;
  std::uint32_t release_frames = 0;

  bool operator==(const ResolvedVoiceDsp&) const = default;
};

constexpr bool is_neutral(const ResolvedVoiceDsp& dsp) noexcept {
  return dsp == ResolvedVoiceDsp{};
}

struct ResolvedPlayback {
  // Value-initialization keeps every member zero, which the realtime engine
  // reads as "use the published playback"; the five-value constructor keeps
  // the form every existing caller uses and leaves the DSP block neutral.
  ResolvedPlayback() = default;
  ResolvedPlayback(
      std::uint32_t start_frame_value,
      std::uint32_t end_frame_value,
      domain::TriggerMode trigger_mode_value,
      float linear_gain_value,
      bool muted_value) noexcept
      : start_frame(start_frame_value),
        end_frame(end_frame_value),
        trigger_mode(trigger_mode_value),
        linear_gain(linear_gain_value),
        muted(muted_value),
        dsp{} {}

  std::uint32_t start_frame;
  std::uint32_t end_frame;
  domain::TriggerMode trigger_mode;
  float linear_gain;
  bool muted;
  ResolvedVoiceDsp dsp;
};

static_assert(sizeof(ResolvedVoiceDsp) == 20);
static_assert(std::is_trivially_copyable_v<ResolvedVoiceDsp>);
static_assert(std::is_trivially_copyable_v<ResolvedPlayback>);

struct ResolvedEvent {
  domain::PadSlotId slot;
  std::uint32_t onset_tick;
  std::uint32_t duration_tick;
  std::uint8_t velocity;
  std::shared_ptr<const PcmSample> sample;

  bool operator==(const ResolvedEvent&) const = default;
};

struct ResolvedPad {
  domain::PadSlotId slot;
  foundation::ArtifactRef artifact;
  std::shared_ptr<const PcmSample> sample;
  ResolvedPlayback playback{};
};

struct RuntimeSnapshot {
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t project_revision;
  std::uint16_t bpm;
  std::uint8_t bars;
  std::uint32_t ppq;
  std::uint32_t loop_length_ticks;
  std::vector<ResolvedPad> pads;
  std::vector<ResolvedEvent> events;
};

}  // namespace lmdj::cooker
