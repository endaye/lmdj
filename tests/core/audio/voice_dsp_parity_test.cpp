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

std::vector<std::int16_t> sine_source() {
  std::vector<std::int16_t> pcm(kSourceFrames);
  for (std::size_t frame = 0; frame < pcm.size(); ++frame) {
    pcm[frame] = static_cast<std::int16_t>(
        12'000.0 * std::sin(static_cast<double>(frame) * 0.031));
  }
  return pcm;
}

// One mono non-neutral voice rendered live and offline agrees within one
// PCM16 step on every frame of both channels: both run the shared kernel.
// The offline event and the replay press both last one beat, 24 000 frames,
// so a looping voice also crosses its gate release at the same frame.
// Returns the live left channel.
std::vector<float> expect_kernel_voice_matches_between_realtime_and_offline(
    const ResolvedPlayback& playback,
    std::size_t rendered_frames,
    const std::vector<std::int16_t>& pcm = sine_source()) {

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
                 PreparedSampleMaterialView{
                     pcm.data(), static_cast<std::uint32_t>(pcm.size()), 1}}) ==
             EnqueueResult::accepted);
  // 100-frame blocks: the engine flushes filter memory once per block, so it
  // flushes at different voice offsets from the offline renderer's 128-frame
  // cadence.
  std::vector<float> left(rendered_frames);
  std::vector<float> right(rendered_frames);
  for (std::size_t done = 0; done < left.size(); done += 100) {
    const auto frames =
        static_cast<std::uint32_t>(std::min<std::size_t>(100, left.size() - done));
    engine.render(left.data() + done, right.data() + done, frames);
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
  return left;
}

ResolvedPlayback kernel_playback(TriggerMode mode, ResolvedVoiceDsp dsp) {
  ResolvedPlayback playback{0, kSourceFrames, mode, 0.8F, false};
  playback.dsp = dsp;
  return playback;
}

void reversed_pitched_one_shot_matches_between_realtime_and_offline() {
  expect_kernel_voice_matches_between_realtime_and_offline(
      kernel_playback(TriggerMode::one_shot,
                      ResolvedVoiceDsp{0, 0, 300, 40, ResolvedVoiceDsp::kReverse}),
      kSourceFrames + 512);
}

// Many passes of a crossfaded forward loop, then the gate release tail.
void crossfaded_loop_and_release_match_between_realtime_and_offline() {
  expect_kernel_voice_matches_between_realtime_and_offline(
      kernel_playback(TriggerMode::loop_gate,
                      ResolvedVoiceDsp{500, 200, -700, -30, 0}),
      24'000 + 512);
}

void reversed_ping_pong_loop_matches_between_realtime_and_offline() {
  expect_kernel_voice_matches_between_realtime_and_offline(
      kernel_playback(
          TriggerMode::loop_gate,
          ResolvedVoiceDsp{300, 0, 500, 0,
                           ResolvedVoiceDsp::kReverse | ResolvedVoiceDsp::kPingPong}),
      24'000 + 512);
}

// A 100 ms user attack and a 200 ms user release on a gated loop: the same
// envelope in realtime and offline, through the release tail's end.
void user_envelope_matches_between_realtime_and_offline() {
  ResolvedVoiceDsp dsp{};
  dsp.attack_frames = 4'800;
  dsp.release_frames = 9'600;
  expect_kernel_voice_matches_between_realtime_and_offline(
      kernel_playback(TriggerMode::loop_gate, dsp), 24'000 + 9'600 + 512);
}

// Tone and every EQ band on a gated loop, with a release: the same filter
// stages in realtime and offline, through the release tail's end.
void tone_and_eq_match_between_realtime_and_offline() {
  ResolvedVoiceDsp dsp{};
  dsp.release_frames = 4'800;
  dsp.tone = -40;
  dsp.eq_flags = ResolvedVoiceDsp::kEqLow | ResolvedVoiceDsp::kEqMid |
                 ResolvedVoiceDsp::kEqHigh | ResolvedVoiceDsp::kEqHighCut;
  dsp.eq_low_freq_hz = 150;
  dsp.eq_low_gain_millidb = 6'000;
  dsp.eq_mid_freq_hz = 1'200;
  dsp.eq_mid_gain_millidb = -9'000;
  dsp.eq_mid_q_milli = 2'000;
  dsp.eq_high_freq_hz = 6'000;
  expect_kernel_voice_matches_between_realtime_and_offline(
      kernel_playback(TriggerMode::loop_gate, dsp), 24'000 + 4'800 + 512);
}

// The gate releases at frame 24 000, halfway through a 1 s user attack: both
// renders fade from the attack's level over the release.
void release_during_a_user_attack_matches_between_realtime_and_offline() {
  ResolvedVoiceDsp dsp{};
  dsp.attack_frames = 48'000;
  dsp.release_frames = 9'600;
  expect_kernel_voice_matches_between_realtime_and_offline(
      kernel_playback(TriggerMode::loop_gate, dsp), 24'000 + 9'600 + 512);
}

// A filtered one-shot reaching its sample's end: both renders take the ending
// declick on the filtered output at the same frames.
void filtered_one_shot_end_matches_between_realtime_and_offline() {
  ResolvedVoiceDsp dsp{};
  dsp.tone = -100;
  dsp.eq_flags = ResolvedVoiceDsp::kEqMid;
  dsp.eq_mid_freq_hz = 200;
  dsp.eq_mid_gain_millidb = 12'000;
  dsp.eq_mid_q_milli = 4'000;
  expect_kernel_voice_matches_between_realtime_and_offline(
      kernel_playback(TriggerMode::one_shot, dsp), kSourceFrames + 512);
}

// A burst and then silence: every filter stage rings down through the flush
// floor while the voice still plays, so the two renders zero their filter
// memory at different offsets. They still agree within one step, and the
// live tail reaches exact zero.
void filter_flushes_at_different_offsets_keep_the_renders_together() {
  constexpr std::uint32_t kFrames = 90'000;
  auto pcm = sine_source();
  pcm.resize(kFrames, 0);
  ResolvedVoiceDsp dsp{};
  dsp.tone = -100;
  dsp.eq_flags = ResolvedVoiceDsp::kEqLow | ResolvedVoiceDsp::kEqMid;
  dsp.eq_low_freq_hz = 80;
  dsp.eq_low_gain_millidb = 6'000;
  dsp.eq_mid_freq_hz = 100;
  dsp.eq_mid_gain_millidb = 6'000;
  dsp.eq_mid_q_milli = 5'000;
  ResolvedPlayback playback{0, kFrames, TriggerMode::one_shot, 0.8F, false};
  playback.dsp = dsp;
  const auto live =
      expect_kernel_voice_matches_between_realtime_and_offline(playback, kFrames, pcm);
  // Flushed, the live tail is exact zero from about frame 45 000; unflushed it
  // would still hold denormal residue at the voice's last frame.
  for (std::size_t frame = 60'000; frame < live.size(); ++frame) {
    LMDJ_CHECK(live[frame] == 0.0F);
  }
}

}  // namespace

int main() {
  try {
    reversed_pitched_one_shot_matches_between_realtime_and_offline();
    crossfaded_loop_and_release_match_between_realtime_and_offline();
    reversed_ping_pong_loop_matches_between_realtime_and_offline();
    user_envelope_matches_between_realtime_and_offline();
    tone_and_eq_match_between_realtime_and_offline();
    release_during_a_user_attack_matches_between_realtime_and_offline();
    filtered_one_shot_end_matches_between_realtime_and_offline();
    filter_flushes_at_different_offsets_keep_the_renders_together();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "audio voice dsp parity tests: PASS\n";
  return 0;
}
