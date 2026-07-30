#include <lmdj/cooker/wav_reader.hpp>

#include <array>
#include <bit>
#include <cstdint>
#include <limits>
#include <string_view>
#include <utility>
#include <vector>

namespace lmdj::cooker {
namespace {

foundation::Result<std::shared_ptr<const PcmSample>> unsupported(
    std::string_view message) {
  return foundation::Result<std::shared_ptr<const PcmSample>>::failure(
      foundation::Error{
          foundation::ErrorCode::unsupported_audio,
          std::string(message),
      });
}

bool has_fourcc(
    std::span<const std::byte> bytes,
    std::size_t offset,
    const std::array<char, 4>& expected) {
  if (offset > bytes.size() || bytes.size() - offset < expected.size()) {
    return false;
  }
  for (std::size_t index = 0; index < expected.size(); ++index) {
    if (std::to_integer<char>(bytes[offset + index]) != expected.at(index)) {
      return false;
    }
  }
  return true;
}

std::uint16_t read_u16(std::span<const std::byte> bytes, std::size_t offset) {
  return static_cast<std::uint16_t>(
      std::to_integer<unsigned char>(bytes[offset]) |
      (static_cast<std::uint16_t>(
           std::to_integer<unsigned char>(bytes[offset + 1]))
       << 8));
}

std::uint32_t read_u32(std::span<const std::byte> bytes, std::size_t offset) {
  return static_cast<std::uint32_t>(
      std::to_integer<unsigned char>(bytes[offset]) |
      (static_cast<std::uint32_t>(
           std::to_integer<unsigned char>(bytes[offset + 1]))
       << 8) |
      (static_cast<std::uint32_t>(
           std::to_integer<unsigned char>(bytes[offset + 2]))
       << 16) |
      (static_cast<std::uint32_t>(
           std::to_integer<unsigned char>(bytes[offset + 3]))
       << 24));
}

}  // namespace

foundation::Result<std::shared_ptr<const PcmSample>> decode_wav(
    std::span<const std::byte> bytes) {
  constexpr std::array<char, 4> kRiff{'R', 'I', 'F', 'F'};
  constexpr std::array<char, 4> kWave{'W', 'A', 'V', 'E'};
  constexpr std::array<char, 4> kFmt{'f', 'm', 't', ' '};
  constexpr std::array<char, 4> kData{'d', 'a', 't', 'a'};

  if (bytes.size() < 12 || !has_fourcc(bytes, 0, kRiff) ||
      !has_fourcc(bytes, 8, kWave)) {
    return unsupported("audio is not a RIFF/WAVE file");
  }
  const auto declared_riff_size = static_cast<std::uint64_t>(read_u32(bytes, 4));
  if (declared_riff_size + 8U != bytes.size()) {
    return unsupported("RIFF chunk size does not match file length");
  }

  bool have_fmt = false;
  bool have_data = false;
  std::uint16_t audio_format = 0;
  std::uint16_t channels = 0;
  std::uint32_t sample_rate = 0;
  std::uint32_t byte_rate = 0;
  std::uint16_t block_align = 0;
  std::uint16_t bits_per_sample = 0;
  std::span<const std::byte> audio_bytes;
  std::size_t offset = 12;

  while (offset < bytes.size()) {
    if (bytes.size() - offset < 8) {
      return unsupported("WAV chunk header exceeds file length");
    }
    const auto chunk_size = static_cast<std::size_t>(read_u32(bytes, offset + 4));
    const auto data_offset = offset + 8;
    if (chunk_size > bytes.size() - data_offset) {
      return unsupported("WAV chunk exceeds file length");
    }

    if (has_fourcc(bytes, offset, kFmt)) {
      if (have_fmt || chunk_size != 16) {
        return unsupported("WAV must contain one PCM fmt chunk");
      }
      have_fmt = true;
      audio_format = read_u16(bytes, data_offset);
      channels = read_u16(bytes, data_offset + 2);
      sample_rate = read_u32(bytes, data_offset + 4);
      byte_rate = read_u32(bytes, data_offset + 8);
      block_align = read_u16(bytes, data_offset + 12);
      bits_per_sample = read_u16(bytes, data_offset + 14);
    } else if (has_fourcc(bytes, offset, kData)) {
      if (have_data) {
        return unsupported("WAV must contain one data chunk");
      }
      have_data = true;
      audio_bytes = bytes.subspan(data_offset, chunk_size);
    }

    offset = data_offset + chunk_size;
    if ((chunk_size & 1U) != 0U) {
      if (offset == bytes.size()) {
        return unsupported("WAV odd-sized chunk is missing padding");
      }
      ++offset;
    }
  }

  if (offset != bytes.size() || !have_fmt || !have_data) {
    return unsupported("WAV must contain one fmt and one data chunk");
  }
  if (audio_format != 1 || (channels != 1 && channels != 2) ||
      sample_rate != 48'000 || bits_per_sample != 16 ||
      block_align != channels * 2U ||
      byte_rate != sample_rate * static_cast<std::uint32_t>(block_align)) {
    return unsupported("WAV encoding must be 48 kHz PCM16 mono or stereo");
  }
  if (audio_bytes.size() % block_align != 0) {
    return unsupported("WAV data is not aligned to complete frames");
  }
  if (audio_bytes.size() / 2 >
      static_cast<std::size_t>(std::numeric_limits<std::uint32_t>::max())) {
    return unsupported("WAV sample count exceeds supported range");
  }

  std::vector<std::int16_t> samples;
  samples.reserve(audio_bytes.size() / 2);
  for (std::size_t index = 0; index < audio_bytes.size(); index += 2) {
    const auto bits = read_u16(audio_bytes, index);
    samples.push_back(std::bit_cast<std::int16_t>(bits));
  }
  return foundation::Result<std::shared_ptr<const PcmSample>>::success(
      std::make_shared<const PcmSample>(
          PcmSample{sample_rate, channels, std::move(samples)}));
}

}  // namespace lmdj::cooker
