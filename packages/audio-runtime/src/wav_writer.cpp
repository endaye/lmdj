#include <lmdj/audio/wav_writer.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <limits>
#include <string>
#include <utility>

namespace lmdj::audio::detail {
namespace {

foundation::Result<void> failure(
    foundation::ErrorCode code,
    std::string message,
    const std::filesystem::path& path) {
  return foundation::Result<void>::failure(
      foundation::Error{
          code,
          std::move(message),
          {{"path", path.generic_string()}},
      });
}

void write_tag(std::ofstream& stream, const char* tag) {
  stream.write(tag, 4);
}

void write_u16_le(std::ofstream& stream, std::uint16_t value) {
  const std::array<char, 2> bytes{
      static_cast<char>(value & 0xffU),
      static_cast<char>((value >> 8U) & 0xffU),
  };
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

void write_u32_le(std::ofstream& stream, std::uint32_t value) {
  const std::array<char, 4> bytes{
      static_cast<char>(value & 0xffU),
      static_cast<char>((value >> 8U) & 0xffU),
      static_cast<char>((value >> 16U) & 0xffU),
      static_cast<char>((value >> 24U) & 0xffU),
  };
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

}  // namespace

foundation::Result<void> write_pcm16_stereo_wav(
    const std::filesystem::path& path,
    std::uint32_t sample_rate,
    std::span<const std::int16_t> interleaved) {
  constexpr std::uint16_t kChannels = 2;
  constexpr std::uint16_t kBitsPerSample = 16;
  constexpr std::uint16_t kBlockAlign =
      kChannels * (kBitsPerSample / 8U);

  if (interleaved.size() % kChannels != 0) {
    return failure(
        foundation::ErrorCode::invalid_argument,
        "stereo PCM must have an even sample count",
        path);
  }
  if (interleaved.size() >
      (std::numeric_limits<std::uint32_t>::max() - 36U) / 2U) {
    return failure(
        foundation::ErrorCode::invalid_argument,
        "WAV payload exceeds the RIFF size limit",
        path);
  }
  if (sample_rate >
      std::numeric_limits<std::uint32_t>::max() / kBlockAlign) {
    return failure(
        foundation::ErrorCode::invalid_argument,
        "WAV byte rate exceeds the format limit",
        path);
  }

  const auto data_bytes =
      static_cast<std::uint32_t>(interleaved.size() * 2U);
  const auto riff_bytes = 36U + data_bytes;
  const auto byte_rate = sample_rate * kBlockAlign;

  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  if (!stream) {
    return failure(
        foundation::ErrorCode::io_error,
        "WAV output could not be opened",
        path);
  }

  write_tag(stream, "RIFF");
  write_u32_le(stream, riff_bytes);
  write_tag(stream, "WAVE");
  write_tag(stream, "fmt ");
  write_u32_le(stream, 16);
  write_u16_le(stream, 1);
  write_u16_le(stream, kChannels);
  write_u32_le(stream, sample_rate);
  write_u32_le(stream, byte_rate);
  write_u16_le(stream, kBlockAlign);
  write_u16_le(stream, kBitsPerSample);
  write_tag(stream, "data");
  write_u32_le(stream, data_bytes);
  for (const auto sample : interleaved) {
    write_u16_le(stream, static_cast<std::uint16_t>(sample));
  }

  stream.close();
  if (!stream) {
    return failure(
        foundation::ErrorCode::io_error,
        "WAV output could not be written completely",
        path);
  }
  return foundation::Result<void>::success();
}

}  // namespace lmdj::audio::detail
