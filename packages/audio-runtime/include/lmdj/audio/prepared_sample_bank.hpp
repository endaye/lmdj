#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::audio {

class RealtimeEngine;

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

  foundation::ProjectId project_id_;
  std::uint64_t project_revision_;
  std::uint64_t availability_mask_ = 0;
  std::uint64_t decoded_pcm_bytes_ = 0;
  std::array<std::vector<float>, 64> samples_;
};

}  // namespace lmdj::audio
