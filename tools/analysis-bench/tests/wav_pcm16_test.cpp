#include <cassert>
#include <cstdint>
#include <iostream>
#include <span>

#include <lmdj/analysis/wav_pcm16.hpp>

#include "support.hpp"

int main() {
  const auto kick = analysis_bench_test::read_bytes(
      "tests/fixtures/audio/kick.wav");
  assert(!kick.empty());
  const auto parsed =
      lmdj::analysis::parse_wav_pcm16(std::span<const std::byte>(kick));
  assert(parsed.has_value());
  assert(parsed.value().sample_rate == 48000);
  assert(parsed.value().channels == 1);
  assert(parsed.value().frame_count() > 0);
  assert(parsed.value().frame_count() == parsed.value().interleaved.size());

  const auto stereo = analysis_bench_test::read_bytes(
      "tests/fixtures/audio/stereo.wav");
  const auto parsed_stereo =
      lmdj::analysis::parse_wav_pcm16(std::span<const std::byte>(stereo));
  assert(parsed_stereo.has_value());
  assert(parsed_stereo.value().channels == 2);
  assert(
      parsed_stereo.value().frame_count() * 2 ==
      parsed_stereo.value().interleaved.size());
  const auto mono = lmdj::analysis::mix_to_mono(parsed_stereo.value());
  assert(mono.size() == parsed_stereo.value().frame_count());
  for (const float sample : mono) {
    assert(sample >= -1.0F && sample <= 1.0F);
  }

  const std::byte garbage[16] = {};
  const auto rejected = lmdj::analysis::parse_wav_pcm16(
      std::span<const std::byte>(garbage, sizeof(garbage)));
  assert(!rejected.has_value());
  assert(
      rejected.error().code == lmdj::foundation::ErrorCode::invalid_argument);

  std::cout << "wav_pcm16_test passed\n";
  return 0;
}
