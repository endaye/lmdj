#include <lmdj/cooker/wav_selection.hpp>

#include <array>
#include <cstdint>
#include <limits>
#include <string>

#include <lmdj/cooker/wav_reader.hpp>

namespace lmdj::cooker {
namespace {

using SelectionResult = foundation::Result<std::vector<std::byte>>;

SelectionResult invalid_range(std::string message) {
  return SelectionResult::failure(foundation::Error{
      foundation::ErrorCode::invalid_argument,
      std::move(message),
  });
}

SelectionResult unsupported(std::string message) {
  return SelectionResult::failure(foundation::Error{
      foundation::ErrorCode::unsupported_audio,
      std::move(message),
  });
}

void append_fourcc(
    std::vector<std::byte>& output,
    const std::array<char, 4>& value) {
  for (const auto character : value) {
    output.push_back(
        static_cast<std::byte>(static_cast<unsigned char>(character)));
  }
}

void append_u16(std::vector<std::byte>& output, std::uint16_t value) {
  output.push_back(static_cast<std::byte>(value & 0xffU));
  output.push_back(static_cast<std::byte>((value >> 8U) & 0xffU));
}

void append_u32(std::vector<std::byte>& output, std::uint32_t value) {
  for (std::uint32_t shift = 0; shift < 32U; shift += 8U) {
    output.push_back(static_cast<std::byte>((value >> shift) & 0xffU));
  }
}

foundation::Result<std::vector<std::byte>> select_wav(
    std::span<const std::byte> source,
    std::uint64_t start_frame,
    std::uint64_t end_frame,
    bool stereo_only) {
  if (start_frame >= end_frame) {
    return invalid_range(
        "WAV selection must be a non-empty half-open frame range");
  }
  if (!stereo_only && source.size() > 16777216U) return invalid_range("Slice source exceeds byte bound");
  const auto decoded = decode_wav(source);
  if (!decoded.has_value()) {
    return SelectionResult::failure(decoded.error());
  }
  const auto& pcm = *decoded.value();
  if (stereo_only && (pcm.sample_rate != 48000U || pcm.channels != 2U))
    return unsupported("WAV selection requires PCM16 48 kHz stereo input");
  if ((pcm.sample_rate != 48'000U && pcm.sample_rate != 44'100U) ||
      (pcm.channels != 1U && pcm.channels != 2U)) {
    return unsupported("WAV selection requires PCM16 44.1/48 kHz mono/stereo input");
  }
  if (pcm.interleaved.size() % pcm.channels != 0U) {
    return unsupported("WAV selection source has incomplete frames");
  }
  const auto frame_count =
      static_cast<std::uint64_t>(pcm.interleaved.size() / pcm.channels);
  if (end_frame > frame_count) {
    return invalid_range("WAV selection exceeds the source frame count");
  }
  const auto selected_frames = end_frame - start_frame;
  if (selected_frames > std::numeric_limits<std::uint64_t>::max() / 4U) {
    return invalid_range("WAV selection byte length overflowed");
  }
  const auto data_bytes = selected_frames * pcm.channels * 2U;
  if (data_bytes > std::numeric_limits<std::uint32_t>::max() ||
      data_bytes > std::numeric_limits<std::size_t>::max() - 44U ||
      data_bytes > std::numeric_limits<std::uint32_t>::max() - 36U) {
    return invalid_range("WAV selection exceeds RIFF size limits");
  }
  if (start_frame > std::numeric_limits<std::uint64_t>::max() / 2U ||
      end_frame > std::numeric_limits<std::uint64_t>::max() / 2U) {
    return invalid_range("WAV selection sample index overflowed");
  }
  const auto first_sample = start_frame * pcm.channels;
  const auto last_sample = end_frame * pcm.channels;
  if (last_sample > pcm.interleaved.size() ||
      first_sample > std::numeric_limits<std::size_t>::max()) {
    return invalid_range("WAV selection sample range is unsupported");
  }

  std::vector<std::byte> output;
  output.reserve(44U + static_cast<std::size_t>(data_bytes));
  append_fourcc(output, {'R', 'I', 'F', 'F'});
  append_u32(output, static_cast<std::uint32_t>(36U + data_bytes));
  append_fourcc(output, {'W', 'A', 'V', 'E'});
  append_fourcc(output, {'f', 'm', 't', ' '});
  append_u32(output, 16U);
  append_u16(output, 1U);
  append_u16(output, pcm.channels);
  append_u32(output, pcm.sample_rate);
  append_u32(output, pcm.sample_rate * pcm.channels * 2U);
  append_u16(output, static_cast<std::uint16_t>(pcm.channels * 2U));
  append_u16(output, 16U);
  append_fourcc(output, {'d', 'a', 't', 'a'});
  append_u32(output, static_cast<std::uint32_t>(data_bytes));
  for (std::uint64_t index = first_sample; index < last_sample; ++index) {
    append_u16(
        output,
        static_cast<std::uint16_t>(
            pcm.interleaved.at(static_cast<std::size_t>(index))));
  }
  return SelectionResult::success(std::move(output));
}

} // namespace

foundation::Result<std::vector<std::byte>> select_pcm16_wav(
    std::span<const std::byte> source, std::uint64_t start_frame,
    std::uint64_t end_frame) {
  return select_wav(source, start_frame, end_frame, false);
}

foundation::Result<std::vector<std::byte>> select_pcm16_stereo_wav(
    std::span<const std::byte> source, std::uint64_t start_frame,
    std::uint64_t end_frame) {
  return select_wav(source, start_frame, end_frame, true);
}

}  // namespace lmdj::cooker
