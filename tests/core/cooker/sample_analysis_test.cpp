#include <array>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <string>
#include <utility>
#include <vector>

#include <lmdj/cooker/sample_analysis.hpp>
#include <lmdj/cooker/wav_reader.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::cooker::PeakBucket;
using lmdj::cooker::PcmSample;
using lmdj::foundation::ErrorCode;

std::vector<std::byte> fixture_bytes(const std::string& name) {
  const auto path = std::filesystem::path{"tests/fixtures/audio"} / name;
  std::ifstream input(path, std::ios::binary);
  LMDJ_CHECK(static_cast<bool>(input));
  const std::vector<char> characters{
      std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
  std::vector<std::byte> bytes;
  bytes.reserve(characters.size());
  for (const char character : characters) {
    bytes.push_back(static_cast<std::byte>(
        static_cast<unsigned char>(character)));
  }
  return bytes;
}

void write_u16(std::vector<std::byte>& bytes,
               std::size_t offset,
               std::uint16_t value) {
  bytes.at(offset) = static_cast<std::byte>(value & 0xffU);
  bytes.at(offset + 1) = static_cast<std::byte>(value >> 8U);
}

void write_u32(std::vector<std::byte>& bytes,
               std::size_t offset,
               std::uint32_t value) {
  for (std::uint32_t shift = 0; shift < 32U; shift += 8U) {
    bytes.at(offset + shift / 8U) = static_cast<std::byte>(value >> shift);
  }
}

void update_riff_size(std::vector<std::byte>& bytes) {
  LMDJ_CHECK(bytes.size() >= 8U);
  write_u32(bytes, 4, static_cast<std::uint32_t>(bytes.size() - 8U));
}

void append_chunk(std::vector<std::byte>& bytes,
                  const std::array<char, 4>& type,
                  const std::vector<std::byte>& payload) {
  for (const char character : type) {
    bytes.push_back(static_cast<std::byte>(
        static_cast<unsigned char>(character)));
  }
  const auto payload_size = static_cast<std::uint32_t>(payload.size());
  for (std::uint32_t shift = 0; shift < 32U; shift += 8U) {
    bytes.push_back(static_cast<std::byte>(payload_size >> shift));
  }
  bytes.insert(bytes.end(), payload.begin(), payload.end());
  if ((payload.size() & 1U) != 0U) {
    bytes.push_back(std::byte{0});
  }
}

void check_bucket(const PeakBucket& bucket,
                  std::uint64_t start,
                  std::uint64_t end,
                  std::uint16_t peak) {
  LMDJ_CHECK(bucket.start_frame == start);
  LMDJ_CHECK(bucket.end_frame == end);
  LMDJ_CHECK(bucket.peak_magnitude == peak);
}

void check_unsupported(const std::vector<std::byte>& bytes) {
  const auto decoded = lmdj::cooker::decode_wav(bytes);
  const auto inspected = lmdj::cooker::inspect_wav(bytes);
  LMDJ_CHECK(!decoded.has_value());
  LMDJ_CHECK(decoded.error().code == ErrorCode::unsupported_audio);
  LMDJ_CHECK(!inspected.has_value());
  LMDJ_CHECK(inspected.error().code == ErrorCode::unsupported_audio);
}

void test_inspection_accepts_locked_pcm16_rates_and_reports_source_metadata() {
  const auto mono = lmdj::cooker::inspect_wav(
      fixture_bytes("mono-44100.wav"));
  const auto stereo = lmdj::cooker::inspect_wav(
      fixture_bytes("stereo.wav"));
  auto stereo_44100_bytes = fixture_bytes("stereo.wav");
  write_u32(stereo_44100_bytes, 24, 44'100);
  write_u32(stereo_44100_bytes, 28, 176'400);
  const auto stereo_44100 = lmdj::cooker::inspect_wav(stereo_44100_bytes);

  LMDJ_CHECK(mono.has_value());
  LMDJ_CHECK(mono.value().sample_rate == 44'100);
  LMDJ_CHECK(mono.value().channels == 1);
  LMDJ_CHECK(mono.value().source_frames == 8);
  LMDJ_CHECK(stereo.has_value());
  LMDJ_CHECK(stereo.value().sample_rate == 48'000);
  LMDJ_CHECK(stereo.value().channels == 2);
  LMDJ_CHECK(stereo.value().source_frames == 4);
  LMDJ_CHECK(stereo_44100.has_value());
  LMDJ_CHECK(stereo_44100.value().sample_rate == 44'100);
  LMDJ_CHECK(stereo_44100.value().channels == 2);
  LMDJ_CHECK(stereo_44100.value().source_frames == 4);
}

void test_strict_wav_rejects_format_field_and_duplicate_chunk_breaks() {
  const auto valid = fixture_bytes("mono-44100.wav");

  auto float_encoding = valid;
  write_u16(float_encoding, 20, 3);

  auto wrong_rate = valid;
  write_u32(wrong_rate, 24, 32'000);
  write_u32(wrong_rate, 28, 64'000);

  auto wrong_bits = valid;
  write_u16(wrong_bits, 34, 24);
  write_u16(wrong_bits, 32, 3);
  write_u32(wrong_bits, 28, 132'300);

  auto wrong_byte_rate = valid;
  write_u32(wrong_byte_rate, 28, 88'199);

  auto wrong_block_align = valid;
  write_u16(wrong_block_align, 32, 4);

  auto duplicate_fmt = valid;
  duplicate_fmt.insert(
      duplicate_fmt.begin() + 36,
      valid.begin() + 12,
      valid.begin() + 36);
  update_riff_size(duplicate_fmt);

  auto duplicate_data = valid;
  append_chunk(
      duplicate_data,
      {'d', 'a', 't', 'a'},
      {std::byte{0}, std::byte{0}});
  update_riff_size(duplicate_data);

  auto empty_data = valid;
  empty_data.resize(44);
  write_u32(empty_data, 40, 0);
  update_riff_size(empty_data);

  for (const auto& malformed : {
           float_encoding,
           wrong_rate,
           wrong_bits,
           wrong_byte_rate,
           wrong_block_align,
           duplicate_fmt,
           duplicate_data,
           empty_data,
       }) {
    check_unsupported(malformed);
  }
}

void test_strict_wav_rejects_source_frame_declaration_above_active_limit() {
  constexpr std::uint32_t boundary_frame_count = 240'000;
  constexpr std::uint32_t frame_count = 240'001;
  auto boundary = fixture_bytes("mono-44100.wav");
  boundary.resize(
      44U + boundary_frame_count * sizeof(std::int16_t), std::byte{0});
  write_u32(boundary, 40, boundary_frame_count * sizeof(std::int16_t));
  update_riff_size(boundary);
  auto oversized = fixture_bytes("mono-44100.wav");
  oversized.resize(44U + frame_count * sizeof(std::int16_t), std::byte{0});
  write_u32(oversized, 40, frame_count * sizeof(std::int16_t));
  update_riff_size(oversized);

  const auto accepted = lmdj::cooker::decode_wav(boundary);
  LMDJ_CHECK(accepted.has_value());
  LMDJ_CHECK(accepted.value()->interleaved.size() == boundary_frame_count);
  check_unsupported(oversized);
}

void test_waveform_uses_exact_nonempty_buckets_and_int16_min_magnitude() {
  const auto decoded = lmdj::cooker::decode_wav(
      fixture_bytes("mono-44100.wav"));
  LMDJ_CHECK(decoded.has_value());

  const auto envelope = lmdj::cooker::waveform_envelope(
      *decoded.value(), {0, 8, 4});

  LMDJ_CHECK(envelope.has_value());
  LMDJ_CHECK(envelope.value().algorithm_version == 1);
  LMDJ_CHECK(envelope.value().metadata.sample_rate == 44'100);
  LMDJ_CHECK(envelope.value().metadata.channels == 1);
  LMDJ_CHECK(envelope.value().metadata.source_frames == 8);
  LMDJ_CHECK(envelope.value().buckets.size() == 4);
  check_bucket(envelope.value().buckets.at(0), 0, 2, 32'768);
  check_bucket(envelope.value().buckets.at(1), 2, 4, 8'192);
  check_bucket(envelope.value().buckets.at(2), 4, 6, 4'096);
  check_bucket(envelope.value().buckets.at(3), 6, 8, 0);
}

void test_waveform_folds_all_stereo_channels_by_max_absolute_peak() {
  const auto decoded = lmdj::cooker::decode_wav(
      fixture_bytes("stereo.wav"));
  LMDJ_CHECK(decoded.has_value());

  const auto envelope = lmdj::cooker::waveform_envelope(
      *decoded.value(), {0, 4, 2});

  LMDJ_CHECK(envelope.has_value());
  LMDJ_CHECK(envelope.value().buckets.size() == 2);
  check_bucket(envelope.value().buckets.at(0), 0, 2, 32'768);
  check_bucket(envelope.value().buckets.at(1), 2, 4, 1'011);
}

void test_waveform_partial_window_never_reuses_an_overwide_peak() {
  const PcmSample sample{
      48'000,
      1,
      {30'000, 1, -2, 3, -4},
  };

  const auto envelope = lmdj::cooker::waveform_envelope(
      sample, {1, 5, 3});
  const auto narrow = lmdj::cooker::waveform_envelope(
      sample, {1, 3, 512});

  LMDJ_CHECK(envelope.has_value());
  LMDJ_CHECK(envelope.value().buckets.size() == 2);
  check_bucket(envelope.value().buckets.at(0), 1, 3, 2);
  check_bucket(envelope.value().buckets.at(1), 3, 5, 4);
  LMDJ_CHECK(narrow.has_value());
  LMDJ_CHECK(narrow.value().buckets.size() == 2);
  check_bucket(narrow.value().buckets.at(0), 1, 2, 1);
  check_bucket(narrow.value().buckets.at(1), 2, 3, 2);
}

void test_waveform_rejects_empty_out_of_range_and_unbounded_requests() {
  const PcmSample sample{48'000, 1, {1, 2, 3}};
  const std::array requests{
      lmdj::cooker::WaveformRequest{0, 0, 1},
      lmdj::cooker::WaveformRequest{2, 1, 1},
      lmdj::cooker::WaveformRequest{0, 4, 1},
      lmdj::cooker::WaveformRequest{0, 3, 0},
      lmdj::cooker::WaveformRequest{0, 3, 513},
      lmdj::cooker::WaveformRequest{
          std::numeric_limits<std::uint64_t>::max() - 1U,
          std::numeric_limits<std::uint64_t>::max(),
          2},
  };

  for (const auto& request : requests) {
    const auto result = lmdj::cooker::waveform_envelope(sample, request);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
  }
}

void test_integer_rational_preparation_matches_locked_44100_golden_vector() {
  const auto decoded = lmdj::cooker::decode_wav(
      fixture_bytes("mono-44100.wav"));
  LMDJ_CHECK(decoded.has_value());

  const auto first = lmdj::cooker::prepare_runtime_pcm(*decoded.value());
  const auto second = lmdj::cooker::prepare_runtime_pcm(*decoded.value());
  const std::vector<std::int16_t> expected{
      -32'768, 12'390, -4'198, 1'101, -1'434,
      -448, 998, 0, 0,
  };

  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(first.value()->sample_rate == 48'000);
  LMDJ_CHECK(first.value()->channels == 1);
  LMDJ_CHECK(first.value()->interleaved == expected);
  LMDJ_CHECK(second.value()->interleaved == expected);
}

void test_integer_rational_preparation_clamps_the_last_source_frame() {
  const PcmSample source{44'100, 1, {0, 1'000}};
  const auto prepared = lmdj::cooker::prepare_runtime_pcm(source);

  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK((prepared.value()->interleaved ==
              std::vector<std::int16_t>{0, 919, 1'000}));
}

void test_integer_rational_preparation_preserves_stereo_channel_order() {
  const PcmSample source{44'100, 2, {0, 1'000, -1'000, 0}};
  const auto prepared = lmdj::cooker::prepare_runtime_pcm(source);

  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value()->channels == 2);
  LMDJ_CHECK((prepared.value()->interleaved ==
              std::vector<std::int16_t>{
                  0, 1'000, -919, 81, -1'000, 0,
              }));
}

void test_48000_preparation_is_byte_equivalent_for_stereo_pcm() {
  const PcmSample source{
      48'000,
      2,
      {32'767, -32'768, -12'345, 23'456},
  };
  const auto prepared = lmdj::cooker::prepare_runtime_pcm(source);

  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value()->sample_rate == source.sample_rate);
  LMDJ_CHECK(prepared.value()->channels == source.channels);
  LMDJ_CHECK(prepared.value()->interleaved == source.interleaved);
}

void test_analysis_rejects_invalid_decoded_pcm_shapes() {
  const std::array invalid{
      PcmSample{44'100, 1, {}},
      PcmSample{32'000, 1, {1}},
      PcmSample{48'000, 0, {1}},
      PcmSample{48'000, 3, {1, 2, 3}},
      PcmSample{48'000, 2, {1, 2, 3}},
  };

  for (const auto& sample : invalid) {
    const auto envelope = lmdj::cooker::waveform_envelope(
        sample, {0, 1, 1});
    const auto prepared = lmdj::cooker::prepare_runtime_pcm(sample);
    LMDJ_CHECK(!envelope.has_value());
    LMDJ_CHECK(envelope.error().code == ErrorCode::unsupported_audio);
    LMDJ_CHECK(!prepared.has_value());
    LMDJ_CHECK(prepared.error().code == ErrorCode::unsupported_audio);
  }
}

}  // namespace

int main() {
  try {
    test_inspection_accepts_locked_pcm16_rates_and_reports_source_metadata();
    test_strict_wav_rejects_format_field_and_duplicate_chunk_breaks();
    test_strict_wav_rejects_source_frame_declaration_above_active_limit();
    test_waveform_uses_exact_nonempty_buckets_and_int16_min_magnitude();
    test_waveform_folds_all_stereo_channels_by_max_absolute_peak();
    test_waveform_partial_window_never_reuses_an_overwide_peak();
    test_waveform_rejects_empty_out_of_range_and_unbounded_requests();
    test_integer_rational_preparation_matches_locked_44100_golden_vector();
    test_integer_rational_preparation_clamps_the_last_source_frame();
    test_integer_rational_preparation_preserves_stereo_channel_order();
    test_48000_preparation_is_byte_equivalent_for_stereo_pcm();
    test_analysis_rejects_invalid_decoded_pcm_shapes();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "sample analysis tests: PASS\n";
  return 0;
}
