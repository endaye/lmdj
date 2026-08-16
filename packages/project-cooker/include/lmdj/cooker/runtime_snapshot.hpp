#pragma once

#include <cstdint>
#include <memory>
#include <vector>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::cooker {

struct PcmSample {
  std::uint32_t sample_rate;
  std::uint16_t channels;
  std::vector<std::int16_t> interleaved;
};

struct ResolvedPlayback {
  std::uint32_t start_frame;
  std::uint32_t end_frame;
  domain::TriggerMode trigger_mode;
  float linear_gain;
  bool muted;
};

struct ResolvedEvent {
  domain::PadSlotId slot;
  std::uint32_t step;
  std::uint8_t velocity;
  std::shared_ptr<const PcmSample> sample;
};

struct ResolvedPad {
  domain::PadSlotId slot;
  foundation::ArtifactRef artifact;
  std::shared_ptr<const PcmSample> sample;
  ResolvedPlayback playback{};
};

struct RuntimeSnapshot {
  foundation::ProjectId project_id;
  std::uint64_t project_revision;
  std::uint16_t bpm;
  std::uint8_t bars;
  std::vector<ResolvedPad> pads;
  std::vector<ResolvedEvent> events;
};

}  // namespace lmdj::cooker
