#include <lmdj/audio/offline_renderer.hpp>

#include <lmdj/audio/mix_math.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/wav_writer.hpp>

#include <algorithm>
#include <cmath>
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

constexpr bool is_looping(domain::TriggerMode mode) noexcept {
  return mode == domain::TriggerMode::loop_gate ||
         mode == domain::TriggerMode::loop_toggle;
}

constexpr bool valid_trigger_mode(domain::TriggerMode mode) noexcept {
  switch (mode) {
    case domain::TriggerMode::one_shot:
    case domain::TriggerMode::gate:
    case domain::TriggerMode::loop_gate:
    case domain::TriggerMode::loop_toggle:
      return true;
  }
  return false;
}

foundation::Result<OfflineRenderResult> invalid_request(
    std::string message) {
  return foundation::Result<OfflineRenderResult>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::move(message),
      });
}

std::int16_t apply_gain(std::int16_t value, float gain) noexcept {
  if (gain == 1.0F) {
    return value;
  }
  const auto scaled = static_cast<double>(value) * gain;
  if (scaled >= std::numeric_limits<std::int16_t>::max()) {
    return std::numeric_limits<std::int16_t>::max();
  }
  if (scaled <= std::numeric_limits<std::int16_t>::min()) {
    return std::numeric_limits<std::int16_t>::min();
  }
  return static_cast<std::int16_t>(std::lround(scaled));
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
  if (!has_supported_bar_count(snapshot.bars) ||
      snapshot.ppq != kTransportPpq ||
      snapshot.loop_length_ticks == 0 ||
      snapshot.loop_length_ticks !=
          domain::pattern_length_ticks(snapshot.bars)) {
    return invalid_request(
        "offline render Pattern timing is outside the Snapshot set");
  }
  for (const auto& event : snapshot.events) {
    if (event.onset_tick >= snapshot.loop_length_ticks ||
        event.duration_tick < 1 ||
        event.duration_tick >
            snapshot.loop_length_ticks - event.onset_tick) {
      return invalid_request(
          "offline render event ticks are outside the Snapshot");
    }
  }

  auto frame_boundary = tick_boundary_frame(
      snapshot.loop_length_ticks, snapshot.bpm, snapshot.ppq);
  if (!frame_boundary.has_value() || frame_boundary.value() == 0) {
    return invalid_request("offline render frame count is invalid");
  }
  const auto frame_count = frame_boundary.value();
  std::uint64_t interleaved_samples = 0;
  std::uint64_t pcm_bytes = 0;
  std::uint64_t riff_size = 0;
  if (!checked_multiply(
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
    const auto pad = std::find_if(
        snapshot.pads.begin(),
        snapshot.pads.end(),
        [&event](const cooker::ResolvedPad& candidate) {
          return candidate.slot == event.slot;
        });
    if (pad == snapshot.pads.end()) {
      return invalid_request("offline render event has no resolved Pad");
    }

    auto start_boundary = tick_boundary_frame(
        event.onset_tick, snapshot.bpm, snapshot.ppq);
    auto release_boundary = tick_boundary_frame(
        static_cast<std::uint64_t>(event.onset_tick) +
            event.duration_tick,
        snapshot.bpm,
        snapshot.ppq);
    if (!start_boundary.has_value() || !release_boundary.has_value() ||
        release_boundary.value() <= start_boundary.value() ||
        release_boundary.value() > frame_count) {
      return invalid_request("offline render event frame is invalid");
    }
    const auto start_frame = start_boundary.value();
    const auto release_frame = release_boundary.value();

    const auto source_frames =
        source.interleaved.size() / source.channels;
    const auto& playback = pad->playback;
    if (playback.start_frame >= playback.end_frame ||
        playback.end_frame > source_frames ||
        !valid_trigger_mode(playback.trigger_mode) ||
        !std::isfinite(playback.linear_gain) ||
        playback.linear_gain < 0.0F) {
      return invalid_request("offline render Pad playback is invalid");
    }
    if (playback.muted) {
      continue;
    }
    const auto playback_frames =
        static_cast<std::uint64_t>(playback.end_frame - playback.start_frame);
    auto audible_frames = playback_frames;
    if (playback.trigger_mode != domain::TriggerMode::one_shot) {
      audible_frames = std::min(
          release_frame - start_frame,
          is_looping(playback.trigger_mode)
              ? release_frame - start_frame
              : playback_frames);
    }
    audible_frames = std::min(audible_frames, frame_count - start_frame);
    for (std::uint64_t relative_frame = 0;
         relative_frame < audible_frames;
         ++relative_frame) {
      const auto source_frame = static_cast<std::size_t>(
          playback.start_frame + relative_frame % playback_frames);
      const auto output_offset =
          static_cast<std::size_t>(
              start_frame + relative_frame) *
          kOutputChannels;
      const auto source_offset = source_frame * source.channels;
      if (source.channels == 1) {
        const auto scaled =
            apply_gain(
                detail::scale_velocity(
                    source.interleaved[source_offset], event.velocity),
                playback.linear_gain);
        output[output_offset] =
            detail::saturating_add(output[output_offset], scaled);
        output[output_offset + 1] =
            detail::saturating_add(output[output_offset + 1], scaled);
      } else {
        const auto scaled_left =
            apply_gain(
                detail::scale_velocity(
                    source.interleaved[source_offset], event.velocity),
                playback.linear_gain);
        const auto scaled_right =
            apply_gain(
                detail::scale_velocity(
                    source.interleaved[source_offset + 1], event.velocity),
                playback.linear_gain);
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
