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
  const auto stereo_44100 = lmdj::cooker::inspect_wav(
      fixture_bytes("stereo-44100.wav"));

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
  LMDJ_CHECK(stereo_44100.value().source_frames == 2);
}

void test_strict_wav_rejects_duplicate_required_chunks() {
  for (const auto* name : {
           "duplicate-fmt-chunk.wav",
           "duplicate-data-chunk.wav",
       }) {
    check_unsupported(fixture_bytes(name));
  }
}

void test_strict_wav_rejects_inconsistent_pcm_shape_fields() {
  for (const auto* name : {
           "invalid-byte-rate.wav",
           "invalid-block-align.wav",
       }) {
    check_unsupported(fixture_bytes(name));
  }
}

void test_strict_wav_rejects_unsupported_encodings() {
  for (const auto* name : {
           "unsupported-float.wav",
           "unsupported-sample-rate.wav",
           "unsupported-bit-depth.wav",
       }) {
    check_unsupported(fixture_bytes(name));
  }
}

void test_strict_wav_rejects_truncated_data_declaration() {
  check_unsupported(fixture_bytes("truncated-data-declaration.wav"));
}

void test_strict_wav_rejects_empty_data() {
  auto empty_data = fixture_bytes("mono-44100.wav");
  empty_data.resize(44);
  write_u32(empty_data, 40, 0);
  update_riff_size(empty_data);
  check_unsupported(empty_data);
}

void test_cooker_does_not_apply_web_product_frame_admission_policy() {
  constexpr std::uint32_t frame_count_beyond_web_product_limit = 240'001;
  const auto structurally_valid =
      fixture_bytes("mono-44100-over-web-frame-limit.wav");

  const auto decoded = lmdj::cooker::decode_wav(structurally_valid);
  const auto inspected = lmdj::cooker::inspect_wav(structurally_valid);

  LMDJ_CHECK(decoded.has_value());
  LMDJ_CHECK(
      decoded.value()->interleaved.size() ==
      frame_count_beyond_web_product_limit);
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(
      inspected.value().source_frames ==
      frame_count_beyond_web_product_limit);

  const auto envelope = lmdj::cooker::waveform_envelope(
      *decoded.value(), {0, 1, 1});
  const auto prepared = lmdj::cooker::prepare_runtime_pcm(*decoded.value());

  LMDJ_CHECK(envelope.has_value());
  LMDJ_CHECK(envelope.value().metadata.source_frames ==
             frame_count_beyond_web_product_limit);
  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value()->interleaved.size() == 261'226);
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
  const auto decoded = lmdj::cooker::decode_wav(
      fixture_bytes("stereo-44100.wav"));
  LMDJ_CHECK(decoded.has_value());
  const auto prepared = lmdj::cooker::prepare_runtime_pcm(*decoded.value());

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
    test_strict_wav_rejects_duplicate_required_chunks();
    test_strict_wav_rejects_inconsistent_pcm_shape_fields();
    test_strict_wav_rejects_unsupported_encodings();
    test_strict_wav_rejects_truncated_data_declaration();
    test_strict_wav_rejects_empty_data();
    test_cooker_does_not_apply_web_product_frame_admission_policy();
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
