#include <lmdj/audio/offline_renderer.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <string>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::EnqueueResult;
using lmdj::audio::PadControlEvent;
using lmdj::audio::PadControlKind;
using lmdj::audio::PadControlOrigin;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PreparedSampleMaterialView;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::cooker::PcmSample;
using lmdj::cooker::ResolvedEvent;
using lmdj::cooker::ResolvedPad;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::ResolvedVoiceDsp;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::PadSlotId;
using lmdj::domain::TriggerMode;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";
constexpr std::uint32_t kSourceFrames = 2'000;

std::int16_t quantize(float value) {
  const float scaled = value < 0.0F ? value * 32768.0F : value * 32767.0F;
  return static_cast<std::int16_t>(
      std::clamp<long>(std::lround(scaled), -32768, 32767));
}

std::vector<std::byte> read_bytes(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  LMDJ_CHECK(static_cast<bool>(input));
  const std::vector<char> characters{
      std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
  std::vector<std::byte> bytes;
  bytes.reserve(characters.size());
  for (const char character : characters) {
    bytes.push_back(static_cast<std::byte>(character));
  }
  return bytes;
}

std::int16_t wav_sample(const std::vector<std::byte>& bytes, std::size_t index) {
  const auto offset = 44 + index * 2;
  return static_cast<std::int16_t>(
      std::to_integer<std::uint16_t>(bytes.at(offset)) |
      (std::to_integer<std::uint16_t>(bytes.at(offset + 1)) << 8U));
}

// One mono non-neutral voice rendered live and offline agrees within one
// PCM16 step on every frame of both channels: both run the shared kernel.
void mono_kernel_voice_matches_between_realtime_and_offline() {
  std::vector<std::int16_t> pcm(kSourceFrames);
  for (std::size_t frame = 0; frame < pcm.size(); ++frame) {
    pcm[frame] = static_cast<std::int16_t>(
        12'000.0 * std::sin(static_cast<double>(frame) * 0.031));
  }
  ResolvedPlayback playback{0, kSourceFrames, TriggerMode::one_shot, 0.8F, false};
  playback.dsp = ResolvedVoiceDsp{
      0, 0, 300, 40, ResolvedVoiceDsp::kReverse};

  // Offline: one event at tick 0 of a one-bar pattern.
  const auto sample = std::make_shared<const PcmSample>(PcmSample{48'000, 1, pcm});
  const auto snapshot = std::make_shared<const RuntimeSnapshot>(RuntimeSnapshot{
      lmdj::foundation::ProjectId{kProjectId},
      lmdj::foundation::PatternId{"30000000-0000-4000-8000-000000000001"},
      1, 120, 1, lmdj::domain::kPpq, lmdj::domain::kBarTicks4x4,
      {ResolvedPad{
          PadSlotId{0, 0},
          lmdj::foundation::ArtifactRef{std::string(64, 'a'), "audio/wav",
                                        pcm.size() * 2},
          sample, playback}},
      {ResolvedEvent{PadSlotId{0, 0}, 0, 960, 127, sample}},
  });
  const auto path = std::filesystem::temp_directory_path() /
      ("lmdj-voice-parity-" +
       std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) +
       ".wav");
  const auto rendered = lmdj::audio::render_offline(
      lmdj::audio::OfflineRenderRequest{snapshot, path});
  LMDJ_CHECK(rendered.has_value());
  const auto offline = read_bytes(path);
  std::filesystem::remove(path);

  // Realtime: the same voice as a Performance Replay press on the same PCM.
  RealtimeEngine engine;
  LMDJ_CHECK(engine.publish_sample_bank(
                 PreparedSampleBank::empty(lmdj::foundation::ProjectId{kProjectId}, 1)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  std::array<float, 1> warm_left{};
  std::array<float, 1> warm_right{};
  engine.render(warm_left.data(), warm_right.data(), 1);
  LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                 1, 0, 127, PadControlKind::press, playback,
                 PadControlOrigin::performance_replay, 24'000,
                 PreparedSampleMaterialView{pcm.data(), kSourceFrames, 1}}) ==
             EnqueueResult::accepted);
  std::vector<float> left(kSourceFrames + 512);
  std::vector<float> right(kSourceFrames + 512);
  for (std::size_t done = 0; done < left.size(); done += 128) {
    engine.render(left.data() + done, right.data() + done, 128);
  }

  std::size_t compared = 0;
  for (std::size_t frame = 0; frame < left.size(); ++frame) {
    const auto offline_left = wav_sample(offline, frame * 2);
    const auto offline_right = wav_sample(offline, frame * 2 + 1);
    LMDJ_CHECK(std::abs(offline_left - quantize(left[frame])) <= 1);
    LMDJ_CHECK(std::abs(offline_right - quantize(right[frame])) <= 1);
    compared += offline_left != 0 ? 1 : 0;
  }
  // The comparison covered audible frames, not only silence.
  LMDJ_CHECK(compared > 1'000);
}

}  // namespace

int main() {
  try {
    mono_kernel_voice_matches_between_realtime_and_offline();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "audio voice dsp parity tests: PASS\n";
  return 0;
}
