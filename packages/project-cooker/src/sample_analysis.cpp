#include <lmdj/cooker/sample_analysis.hpp>

#include <algorithm>
#include <cstdint>
#include <limits>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include <lmdj/cooker/wav_reader.hpp>

namespace lmdj::cooker {
namespace {

constexpr std::uint64_t kRuntimeSampleRate = 48'000;

foundation::Result<void> validate_sample(const PcmSample& sample) {
  if ((sample.sample_rate != 44'100 && sample.sample_rate != 48'000) ||
      (sample.channels != 1 && sample.channels != 2) ||
      sample.interleaved.empty() ||
      sample.interleaved.size() % sample.channels != 0) {
    return foundation::Result<void>::failure(foundation::Error{
        foundation::ErrorCode::unsupported_audio,
        "decoded PCM shape is unsupported",
    });
  }
  return foundation::Result<void>::success();
}

foundation::Result<WaveformEnvelope> invalid_waveform_request(
    std::string message) {
  return foundation::Result<WaveformEnvelope>::failure(foundation::Error{
      foundation::ErrorCode::invalid_argument,
      std::move(message),
  });
}

std::uint16_t magnitude(std::int16_t sample) noexcept {
  if (sample == std::numeric_limits<std::int16_t>::min()) {
    return 32'768;
  }
  const auto value = static_cast<std::int32_t>(sample);
  return static_cast<std::uint16_t>(value < 0 ? -value : value);
}

std::int16_t symmetric_round(
    std::int64_t numerator,
    std::int64_t denominator) noexcept {
  const auto half = denominator / 2;
  const auto rounded = numerator >= 0
                           ? (numerator + half) / denominator
                           : -((-numerator + half) / denominator);
  return static_cast<std::int16_t>(rounded);
}

}  // namespace

foundation::Result<WavMetadata> inspect_wav(
    std::span<const std::byte> bytes) {
  const auto decoded = decode_wav(bytes);
  if (!decoded.has_value()) {
    return foundation::Result<WavMetadata>::failure(decoded.error());
  }
  return foundation::Result<WavMetadata>::success(WavMetadata{
      decoded.value()->sample_rate,
      decoded.value()->channels,
      static_cast<std::uint64_t>(
          decoded.value()->interleaved.size() / decoded.value()->channels),
  });
}

foundation::Result<WaveformEnvelope> waveform_envelope(
    const PcmSample& sample,
    const WaveformRequest& request) {
  const auto valid = validate_sample(sample);
  if (!valid.has_value()) {
    return foundation::Result<WaveformEnvelope>::failure(valid.error());
  }
  const auto source_frames = static_cast<std::uint64_t>(
      sample.interleaved.size() / sample.channels);
  if (request.bucket_count == 0 || request.bucket_count > 512 ||
      request.start_frame >= request.end_frame ||
      request.end_frame > source_frames) {
    return invalid_waveform_request("waveform request is outside source bounds");
  }

  const auto window_frames = request.end_frame - request.start_frame;
  const auto frames_per_bucket =
      window_frames / request.bucket_count +
      (window_frames % request.bucket_count == 0 ? 0U : 1U);
  std::vector<PeakBucket> buckets;
  buckets.reserve(static_cast<std::size_t>(std::min<std::uint64_t>(
      request.bucket_count, window_frames)));
  auto bucket_start = request.start_frame;
  while (bucket_start < request.end_frame) {
    const auto bucket_frames = std::min(
        frames_per_bucket, request.end_frame - bucket_start);
    const auto bucket_end = bucket_start + bucket_frames;
    std::uint16_t peak = 0;
    for (auto frame = bucket_start; frame < bucket_end; ++frame) {
      const auto base = frame * sample.channels;
      for (std::uint16_t channel = 0; channel < sample.channels; ++channel) {
        peak = std::max(
            peak,
            magnitude(sample.interleaved.at(
                static_cast<std::size_t>(base + channel))));
      }
    }
    buckets.push_back(PeakBucket{bucket_start, bucket_end, peak});
    bucket_start = bucket_end;
  }

  return foundation::Result<WaveformEnvelope>::success(WaveformEnvelope{
      WavMetadata{sample.sample_rate, sample.channels, source_frames},
      kWaveformAlgorithmVersion,
      std::move(buckets),
  });
}

foundation::Result<std::shared_ptr<const PcmSample>> prepare_runtime_pcm(
    const PcmSample& source) {
  const auto valid = validate_sample(source);
  if (!valid.has_value()) {
    return foundation::Result<std::shared_ptr<const PcmSample>>::failure(
        valid.error());
  }
  if (source.sample_rate == kRuntimeSampleRate) {
    return foundation::Result<std::shared_ptr<const PcmSample>>::success(
        std::make_shared<const PcmSample>(source));
  }

  const auto source_frames = static_cast<std::uint64_t>(
      source.interleaved.size() / source.channels);
  if (source_frames >
      std::numeric_limits<std::uint64_t>::max() / kRuntimeSampleRate) {
    return foundation::Result<std::shared_ptr<const PcmSample>>::failure(
        foundation::Error{
            foundation::ErrorCode::unsupported_audio,
            "prepared PCM frame count overflowed",
        });
  }
  const auto scaled_frames = source_frames * kRuntimeSampleRate;
  const auto prepared_frames =
      scaled_frames / source.sample_rate +
      (scaled_frames % source.sample_rate == 0 ? 0U : 1U);
  if (prepared_frames >
      std::numeric_limits<std::uint64_t>::max() / source.channels) {
    return foundation::Result<std::shared_ptr<const PcmSample>>::failure(
        foundation::Error{
            foundation::ErrorCode::unsupported_audio,
            "prepared PCM sample count overflowed",
        });
  }
  const auto prepared_samples = prepared_frames * source.channels;
  if (prepared_samples >
      static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
    return foundation::Result<std::shared_ptr<const PcmSample>>::failure(
        foundation::Error{
            foundation::ErrorCode::unsupported_audio,
            "prepared PCM allocation exceeds supported range",
        });
  }

  std::vector<std::int16_t> interleaved;
  interleaved.reserve(static_cast<std::size_t>(prepared_samples));
  for (std::uint64_t output_frame = 0;
       output_frame < prepared_frames;
       ++output_frame) {
    if (output_frame >
        std::numeric_limits<std::uint64_t>::max() / source.sample_rate) {
      return foundation::Result<std::shared_ptr<const PcmSample>>::failure(
          foundation::Error{
              foundation::ErrorCode::unsupported_audio,
              "prepared PCM source position overflowed",
          });
    }
    const auto source_position = output_frame * source.sample_rate;
    const auto source_frame = source_position / kRuntimeSampleRate;
    const auto remainder = source_position % kRuntimeSampleRate;
    for (std::uint16_t channel = 0; channel < source.channels; ++channel) {
      const auto left_index = source_frame * source.channels + channel;
      if (source_frame >= source_frames - 1U) {
        interleaved.push_back(source.interleaved.at(
            static_cast<std::size_t>(
                (source_frames - 1U) * source.channels + channel)));
        continue;
      }
      const auto right_index = left_index + source.channels;
      const auto weighted =
          static_cast<std::int64_t>(source.interleaved.at(
              static_cast<std::size_t>(left_index))) *
              static_cast<std::int64_t>(kRuntimeSampleRate - remainder) +
          static_cast<std::int64_t>(source.interleaved.at(
              static_cast<std::size_t>(right_index))) *
              static_cast<std::int64_t>(remainder);
      interleaved.push_back(symmetric_round(weighted, kRuntimeSampleRate));
    }
  }

  return foundation::Result<std::shared_ptr<const PcmSample>>::success(
      std::make_shared<const PcmSample>(PcmSample{
          static_cast<std::uint32_t>(kRuntimeSampleRate),
          source.channels,
          std::move(interleaved),
      }));
}

}  // namespace lmdj::cooker
