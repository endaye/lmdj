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

struct ResolvedEvent {
  domain::PadSlotId slot;
  std::uint32_t step;
  std::uint8_t velocity;
  std::shared_ptr<const PcmSample> sample;
};

struct RuntimeSnapshot {
  foundation::ProjectId project_id;
  std::uint64_t project_revision;
  std::uint16_t bpm;
  std::uint8_t bars;
  std::vector<ResolvedEvent> events;
};

}  // namespace lmdj::cooker
