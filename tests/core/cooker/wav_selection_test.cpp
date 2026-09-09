#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <vector>

#include <lmdj/cooker/wav_selection.hpp>
#include <lmdj/cooker/wav_reader.hpp>

#include "tests/core/support/test.hpp"

namespace {

void append_u16(std::vector<std::byte>& bytes, std::uint16_t value) {
  bytes.push_back(static_cast<std::byte>(value));
  bytes.push_back(static_cast<std::byte>(value >> 8));
}

void append_u32(std::vector<std::byte>& bytes, std::uint32_t value) {
  for (std::uint32_t shift = 0; shift < 32; shift += 8) {
    bytes.push_back(static_cast<std::byte>(value >> shift));
  }
}

void append_fourcc(std::vector<std::byte>& bytes, const char* value) {
  for (std::size_t index = 0; index < 4; ++index) {
    bytes.push_back(
        static_cast<std::byte>(static_cast<unsigned char>(value[index])));
  }
}

std::vector<std::byte> wav(
    std::uint16_t format = 1,
    std::uint16_t channels = 2,
    std::uint32_t sample_rate = 48'000,
    std::uint16_t bits = 16) {
  const std::vector<std::int16_t> samples{
      100, -100, 200, -200, 300, -300, 400, -400,
  };
  const auto block_align = static_cast<std::uint16_t>(channels * bits / 8U);
  const auto data_size = static_cast<std::uint32_t>(samples.size() * 2U);
  std::vector<std::byte> bytes;
  append_fourcc(bytes, "RIFF");
  append_u32(bytes, 36U + data_size);
  append_fourcc(bytes, "WAVE");
  append_fourcc(bytes, "fmt ");
  append_u32(bytes, 16);
  append_u16(bytes, format);
  append_u16(bytes, channels);
  append_u32(bytes, sample_rate);
  append_u32(bytes, sample_rate * block_align);
  append_u16(bytes, block_align);
  append_u16(bytes, bits);
  append_fourcc(bytes, "data");
  append_u32(bytes, data_size);
  for (const auto sample : samples) {
    append_u16(bytes, static_cast<std::uint16_t>(sample));
  }
  return bytes;
}

std::uint32_t read_u32(const std::vector<std::byte>& bytes, std::size_t offset) {
  return static_cast<std::uint32_t>(
      std::to_integer<unsigned char>(bytes.at(offset)) |
      (std::to_integer<unsigned char>(bytes.at(offset + 1)) << 8U) |
      (std::to_integer<unsigned char>(bytes.at(offset + 2)) << 16U) |
      (std::to_integer<unsigned char>(bytes.at(offset + 3)) << 24U));
}

void test_selects_exact_half_open_frame_range() {
  const auto source = wav();
  const auto original = source;
  const auto selected =
      lmdj::cooker::select_pcm16_stereo_wav(source, 1, 3);
  LMDJ_CHECK(selected.has_value());
  LMDJ_CHECK(source == original);
  LMDJ_CHECK(selected.value().size() == 52);
  LMDJ_CHECK(read_u32(selected.value(), 4) == 44);
  LMDJ_CHECK(read_u32(selected.value(), 24) == 48'000);
  LMDJ_CHECK(read_u32(selected.value(), 40) == 8);
  LMDJ_CHECK(
      std::to_integer<unsigned char>(selected.value().at(44)) == 200U);
  LMDJ_CHECK(
      std::to_integer<unsigned char>(selected.value().at(48)) == 44U);
}

void check_rejected(
    const std::vector<std::byte>& bytes,
    std::uint64_t start,
    std::uint64_t end) {
  const auto selected =
      lmdj::cooker::select_pcm16_stereo_wav(bytes, start, end);
  LMDJ_CHECK(!selected.has_value());
  LMDJ_CHECK(
      selected.error().code == lmdj::foundation::ErrorCode::unsupported_audio ||
      selected.error().code == lmdj::foundation::ErrorCode::invalid_argument);
}

void test_rejects_invalid_ranges_and_encodings() {
  const auto valid = wav();
  check_rejected(valid, 0, 0);
  check_rejected(valid, 3, 2);
  check_rejected(valid, 0, 5);
  check_rejected(wav(1, 1), 0, 1);
  check_rejected(wav(1, 2, 44'100), 0, 1);
  check_rejected(wav(3), 0, 1);
  check_rejected(wav(1, 2, 48'000, 24), 0, 1);

  auto malformed = valid;
  malformed.at(0) = std::byte{'X'};
  check_rejected(malformed, 0, 1);
  auto trailing = valid;
  trailing.push_back(std::byte{0});
  check_rejected(trailing, 0, 1);
}

void test_slice_profile_preserves_exact_pcm_and_rate() {
  for (const std::uint16_t channels : {std::uint16_t{1}, std::uint16_t{2}}) {
    for (const std::uint32_t rate : {44100U, 48000U}) {
      const auto source = wav(1, channels, rate);
      const auto selected = lmdj::cooker::select_pcm16_wav(source, 1, 3);
      LMDJ_CHECK(selected.has_value());
      const auto pcm = lmdj::cooker::decode_wav(selected.value());
      LMDJ_CHECK(pcm.has_value());
      LMDJ_CHECK(pcm.value()->channels == channels && pcm.value()->sample_rate == rate);
      LMDJ_CHECK(pcm.value()->interleaved == (channels == 1
          ? std::vector<std::int16_t>{-100, 200}
          : std::vector<std::int16_t>{200, -200, 300, -300}));
      LMDJ_CHECK(source == wav(1, channels, rate));
    }
  }
}
void test_slice_profile_bound_and_materialization_refusals() {
  const auto source = wav();
  LMDJ_CHECK(!lmdj::cooker::select_pcm16_wav(source, 0, 5).has_value());
  LMDJ_CHECK(!lmdj::cooker::select_pcm16_wav(source, 1, 1).has_value());
  LMDJ_CHECK(!lmdj::cooker::select_pcm16_wav(wav(3), 0, 1).has_value());
  auto maximum = source;
  maximum.resize(16777216, std::byte{0});
  const auto put_u32 = [&](std::size_t offset, std::uint32_t value) {
    for (unsigned byte = 0; byte < 4; ++byte)
      maximum.at(offset + byte) = static_cast<std::byte>(value >> (8 * byte));
  };
  put_u32(4, 16777216U - 8U); put_u32(40, 16777216U - 44U);
  LMDJ_CHECK(lmdj::cooker::select_pcm16_wav(maximum, 0, 1).has_value());
  maximum.push_back(std::byte{0});
  const auto refused = lmdj::cooker::select_pcm16_wav(maximum, 0, 1);
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().code == lmdj::foundation::ErrorCode::invalid_argument);
}

}  // namespace

int main() {
  try {
    test_slice_profile_preserves_exact_pcm_and_rate();
    test_slice_profile_bound_and_materialization_refusals();
    test_selects_exact_half_open_frame_range();
    test_rejects_invalid_ranges_and_encodings();
    std::cout << "wav selection tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
