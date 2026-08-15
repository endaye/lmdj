#include <lmdj/analysis/wav_pcm16.hpp>

#include <cstring>
#include <utility>

namespace lmdj::analysis {
namespace {

foundation::Error invalid_wav(const char* message) {
  return foundation::Error{
      foundation::ErrorCode::invalid_argument,
      message,
      {{"media_type", "audio/wav"}},
  };
}

std::uint16_t read_u16le(const std::byte* p) {
  return static_cast<std::uint16_t>(
      static_cast<std::uint16_t>(p[0]) |
      static_cast<std::uint16_t>(static_cast<std::uint16_t>(p[1]) << 8U));
}

std::uint32_t read_u32le(const std::byte* p) {
  return static_cast<std::uint32_t>(p[0]) |
         (static_cast<std::uint32_t>(p[1]) << 8U) |
         (static_cast<std::uint32_t>(p[2]) << 16U) |
         (static_cast<std::uint32_t>(p[3]) << 24U);
}

bool tag_equals(const std::byte* p, const char (&tag)[5]) {
  return std::memcmp(p, tag, 4) == 0;
}

}  // namespace

foundation::Result<WavPcm16> parse_wav_pcm16(
    std::span<const std::byte> bytes) {
  using ParseResult = foundation::Result<WavPcm16>;
  if (bytes.size() < 12 || !tag_equals(bytes.data(), "RIFF") ||
      !tag_equals(bytes.data() + 8, "WAVE")) {
    return ParseResult::failure(invalid_wav("input is not RIFF/WAVE"));
  }
  bool have_fmt = false;
  bool have_data = false;
  std::uint16_t audio_format = 0;
  std::uint16_t channels = 0;
  std::uint32_t sample_rate = 0;
  std::uint16_t bits_per_sample = 0;
  const std::byte* data = nullptr;
  std::uint32_t data_size = 0;
  std::size_t offset = 12;
  while (offset + 8 <= bytes.size()) {
    const std::byte* chunk = bytes.data() + offset;
    const std::uint32_t chunk_size = read_u32le(chunk + 4);
    if (chunk_size > bytes.size() - offset - 8) {
      return ParseResult::failure(invalid_wav("WAVE chunk is truncated"));
    }
    const std::byte* body = chunk + 8;
    if (tag_equals(chunk, "fmt ")) {
      if (chunk_size < 16) {
        return ParseResult::failure(
            invalid_wav("WAVE fmt chunk is too small"));
      }
      audio_format = read_u16le(body);
      channels = read_u16le(body + 2);
      sample_rate = read_u32le(body + 4);
      bits_per_sample = read_u16le(body + 14);
      have_fmt = true;
    } else if (tag_equals(chunk, "data")) {
      data = body;
      data_size = chunk_size;
      have_data = true;
    }
    offset += 8 + chunk_size + (chunk_size & 1U);
  }
  if (!have_fmt || !have_data) {
    return ParseResult::failure(
        invalid_wav("WAVE fmt or data chunk is missing"));
  }
  if (audio_format != 1 || bits_per_sample != 16 ||
      (channels != 1 && channels != 2)) {
    return ParseResult::failure(
        invalid_wav("WAVE must be PCM16 mono or stereo"));
  }
  if (data_size % 2 != 0) {
    return ParseResult::failure(invalid_wav("WAVE data is misaligned"));
  }
  WavPcm16 wav;
  wav.sample_rate = sample_rate;
  wav.channels = channels;
  wav.interleaved.resize(data_size / 2);
  for (std::size_t index = 0; index < wav.interleaved.size(); ++index) {
    wav.interleaved[index] =
        static_cast<std::int16_t>(read_u16le(data + index * 2));
  }
  return ParseResult::success(std::move(wav));
}

std::vector<float> mix_to_mono(const WavPcm16& wav) {
  std::vector<float> mono;
  const auto frames = wav.frame_count();
  mono.reserve(frames);
  for (std::uint64_t frame = 0; frame < frames; ++frame) {
    float sum = 0.0F;
    for (std::uint16_t channel = 0; channel < wav.channels; ++channel) {
      sum += static_cast<float>(
                 wav.interleaved[static_cast<std::size_t>(frame) *
                                     wav.channels +
                                 channel]) /
             32768.0F;
    }
    mono.push_back(sum / static_cast<float>(wav.channels));
  }
  return mono;
}

}  // namespace lmdj::analysis
