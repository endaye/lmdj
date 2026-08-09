#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <vector>

#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::cooker {

inline constexpr std::uint32_t kWaveformAlgorithmVersion = 1;

struct WavMetadata {
  std::uint32_t sample_rate;
  std::uint16_t channels;
  std::uint64_t source_frames;
};

struct WaveformRequest {
  std::uint64_t start_frame;
  std::uint64_t end_frame;
  std::uint32_t bucket_count;
};

struct PeakBucket {
  std::uint64_t start_frame;
  std::uint64_t end_frame;
  std::uint16_t peak_magnitude;
};

struct WaveformEnvelope {
  WavMetadata metadata;
  std::uint32_t algorithm_version;
  std::vector<PeakBucket> buckets;
};

foundation::Result<WavMetadata> inspect_wav(
    std::span<const std::byte> bytes);
foundation::Result<WaveformEnvelope> waveform_envelope(
    const PcmSample& sample,
    const WaveformRequest& request);
foundation::Result<std::shared_ptr<const PcmSample>> prepare_runtime_pcm(
    const PcmSample& source);

}  // namespace lmdj::cooker
