#include <lmdj/audio/offline_renderer.hpp>

#include <lmdj/audio/mix_math.hpp>
#include <lmdj/audio/wav_writer.hpp>

#include <cstddef>
#include <cstdint>
#include <limits>
#include <utility>
#include <vector>

namespace lmdj::audio {
namespace {

constexpr std::uint32_t kSampleRate = 48'000;
constexpr std::uint16_t kOutputChannels = 2;
constexpr std::uint8_t kMaximumVelocity = 127;
constexpr std::uint16_t kMinimumBpm = 40;
constexpr std::uint16_t kMaximumBpm = 240;
constexpr std::uint32_t kStepsPerBar = 16;
constexpr std::uint64_t kRiffPcmOverhead = 36;

constexpr bool has_supported_bar_count(std::uint8_t bars) {
  return bars == 1 || bars == 2 || bars == 4 || bars == 8;
}

constexpr bool checked_multiply(
    std::uint64_t left,
    std::uint64_t right,
    std::uint64_t& result) {
  if (right != 0 &&
      left > std::numeric_limits<std::uint64_t>::max() / right) {
    return false;
  }
  result = left * right;
  return true;
}

constexpr bool checked_add(
    std::uint64_t left,
    std::uint64_t right,
    std::uint64_t& result) {
  if (left >
      std::numeric_limits<std::uint64_t>::max() - right) {
    return false;
  }
  result = left + right;
  return true;
}

foundation::Result<OfflineRenderResult> invalid_request(
    std::string message) {
  return foundation::Result<OfflineRenderResult>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::move(message),
      });
}

}  // namespace

foundation::Result<OfflineRenderResult> render_offline(
    const OfflineRenderRequest& request) {
  if (!request.snapshot) {
    return invalid_request("offline render requires a Runtime Snapshot");
  }
  const auto& snapshot = *request.snapshot;
  if (snapshot.bpm < kMinimumBpm ||
      snapshot.bpm > kMaximumBpm) {
    return invalid_request(
        "offline render BPM is outside the Snapshot range");
  }
  if (!has_supported_bar_count(snapshot.bars)) {
    return invalid_request(
        "offline render bar count is outside the Snapshot set");
  }
  const auto step_limit =
      static_cast<std::uint32_t>(snapshot.bars) * kStepsPerBar;
  for (const auto& event : snapshot.events) {
    if (event.step >= step_limit) {
      return invalid_request(
          "offline render event step is outside the Snapshot");
    }
  }

  std::uint64_t bar_frame_numerator = 0;
  std::uint64_t frame_count = 0;
  std::uint64_t interleaved_samples = 0;
  std::uint64_t pcm_bytes = 0;
  std::uint64_t riff_size = 0;
  if (!checked_multiply(4, 60, bar_frame_numerator) ||
      !checked_multiply(
          bar_frame_numerator,
          kSampleRate,
          bar_frame_numerator)) {
    return invalid_request("offline render frame count is invalid");
  }
  const auto bar_frames = bar_frame_numerator / snapshot.bpm;
  if (bar_frames == 0 ||
      !checked_multiply(
          bar_frames,
          snapshot.bars,
          frame_count) ||
      !checked_multiply(
          frame_count,
          kOutputChannels,
          interleaved_samples) ||
      !checked_multiply(
          interleaved_samples,
          sizeof(std::int16_t),
          pcm_bytes) ||
      !checked_add(
          kRiffPcmOverhead,
          pcm_bytes,
          riff_size)) {
    return invalid_request("offline render output size overflowed");
  }
  if (riff_size > std::numeric_limits<std::uint32_t>::max() ||
      pcm_bytes > std::numeric_limits<std::size_t>::max() ||
      interleaved_samples >
          static_cast<std::uint64_t>(
              std::numeric_limits<std::ptrdiff_t>::max()) /
              sizeof(std::int16_t)) {
    return invalid_request("offline render buffer is too large");
  }

  std::vector<std::int16_t> output(
      static_cast<std::size_t>(interleaved_samples),
      0);

  for (const auto& event : snapshot.events) {
    if (!event.sample) {
      return invalid_request("offline render event has no PCM sample");
    }
    const auto& source = *event.sample;
    if (source.sample_rate != kSampleRate ||
        (source.channels != 1 && source.channels != 2) ||
        source.interleaved.size() % source.channels != 0) {
      return invalid_request(
          "offline render event has invalid PCM format");
    }
    if (event.velocity == 0 || event.velocity > kMaximumVelocity) {
      return invalid_request(
          "offline render event has invalid velocity");
    }

    const auto step_frame =
        (static_cast<std::uint64_t>(event.step) * kSampleRate * 60U) /
        (static_cast<std::uint64_t>(snapshot.bpm) * 4U);

    const auto source_frames =
        source.interleaved.size() / source.channels;
    for (std::size_t source_frame = 0;
         source_frame < source_frames &&
         step_frame + source_frame < frame_count;
         ++source_frame) {
      const auto output_offset =
          static_cast<std::size_t>(step_frame + source_frame) *
          kOutputChannels;
      const auto source_offset = source_frame * source.channels;
      if (source.channels == 1) {
        const auto scaled =
            detail::scale_velocity(
                source.interleaved[source_offset],
                event.velocity);
        output[output_offset] =
            detail::saturating_add(output[output_offset], scaled);
        output[output_offset + 1] =
            detail::saturating_add(output[output_offset + 1], scaled);
      } else {
        const auto scaled_left =
            detail::scale_velocity(
                source.interleaved[source_offset],
                event.velocity);
        const auto scaled_right =
            detail::scale_velocity(
                source.interleaved[source_offset + 1],
                event.velocity);
        output[output_offset] =
            detail::saturating_add(
                output[output_offset],
                scaled_left);
        output[output_offset + 1] =
            detail::saturating_add(
                output[output_offset + 1],
                scaled_right);
      }
    }
  }

  const auto written =
      detail::write_pcm16_stereo_wav(
          request.output_path,
          kSampleRate,
          output);
  if (!written.has_value()) {
    return foundation::Result<OfflineRenderResult>::failure(
        written.error());
  }

  auto artifact =
      foundation::describe_artifact(
          request.output_path,
          "audio/wav");
  if (!artifact.has_value()) {
    return foundation::Result<OfflineRenderResult>::failure(
        artifact.error());
  }

  return foundation::Result<OfflineRenderResult>::success(
      OfflineRenderResult{
          std::move(artifact.value()),
          frame_count,
          kSampleRate,
          kOutputChannels,
      });
}

}  // namespace lmdj::audio
