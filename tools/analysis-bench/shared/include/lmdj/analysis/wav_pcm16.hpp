#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

#include <lmdj/foundation/error.hpp>

namespace lmdj::analysis {

struct WavPcm16 {
  std::uint32_t sample_rate = 0;
  std::uint16_t channels = 0;
  std::vector<std::int16_t> interleaved;

  std::uint64_t frame_count() const {
    return channels == 0 ? 0
                         : interleaved.size() /
                               static_cast<std::size_t>(channels);
  }
};

// Strict RIFF/WAVE PCM16 parser. Any sample rate, mono or stereo.
foundation::Result<WavPcm16> parse_wav_pcm16(
    std::span<const std::byte> bytes);

// Mono mixdown to float samples in [-1, 1].
std::vector<float> mix_to_mono(const WavPcm16& wav);

}  // namespace lmdj::analysis
