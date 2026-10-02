// audio.voice_dsp_disabled: the cooker and the Audio Runtime built as the
// Cardputer builds them, without the voice DSP (LMDJ_VOICE_DSP=0; decision
// 2026-09-30 point 9). CI never builds that firmware, so this is where its
// configuration compiles and runs.

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/cooker/project_cooker.hpp>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <type_traits>
#include <utility>
#include <vector>

#include "tests/core/cooker/voice_dsp_neutrality_cases.hpp"
#include "tests/core/support/test.hpp"

#if LMDJ_VOICE_DSP
#error "audio.voice_dsp_disabled must build without the voice DSP"
#endif

namespace {

using lmdj::audio::EnqueueResult;
using lmdj::audio::PadControlEvent;
using lmdj::audio::PadControlKind;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::ResolvedVoiceDsp;
using lmdj::domain::TriggerMode;

// The block occupies no bytes, so every playback in a control message, a Bank
// slot and a Pattern event is as small as before the voice DSP existed.
struct PlaybackWithoutDsp {
  std::uint32_t start_frame;
  std::uint32_t end_frame;
  TriggerMode trigger_mode;
  float linear_gain;
  bool muted;
};

static_assert(std::is_empty_v<ResolvedVoiceDsp>);
static_assert(sizeof(ResolvedPlayback) == sizeof(PlaybackWithoutDsp));

// The cooker accepts exactly the cases a build with the voice DSP resolves to
// neutral (project_cooker_test checks that half) and refuses the rest.
void cooker_accepts_exactly_the_shared_neutral_cases() {
  for (const auto& entry : voice_dsp_neutrality_cases()) {
    const auto resolved = lmdj::cooker::resolve_pad_playback(
        entry.playback, entry.source_rate, kVoiceDspNeutralitySourceFrames);
    if (resolved.has_value() != entry.neutral) {
      std::cerr << "neutrality case: " << entry.name << '\n';
    }
    LMDJ_CHECK(resolved.has_value() == entry.neutral);
    if (!entry.neutral) {
      LMDJ_CHECK(resolved.error().code ==
                 lmdj::foundation::ErrorCode::invalid_argument);
      LMDJ_CHECK(resolved.error().message ==
                 "Pad playback voice settings are not supported by this build");
    }
  }
}

// Invalid settings are still reported as invalid, ahead of this build's
// refusal.
void cooker_reports_invalid_settings_as_invalid() {
  lmdj::domain::PadPlayback playback{1, 7, TriggerMode::loop_gate, 0, false};
  playback.loop_start_frame = 7;
  const auto resolved = lmdj::cooker::resolve_pad_playback(
      playback, 44'100, kVoiceDspNeutralitySourceFrames);
  LMDJ_CHECK(!resolved.has_value());
  LMDJ_CHECK(resolved.error().message ==
             "Pad playback voice settings are invalid");
}

struct Channels {
  std::vector<float> left;
  std::vector<float> right;
};

Channels render(RealtimeEngine& engine, std::uint32_t frames) {
  Channels out{std::vector<float>(frames), std::vector<float>(frames)};
  std::uint32_t done = 0;
  while (done < frames) {
    const auto block = std::min<std::uint32_t>(frames - done, 128);
    engine.render(out.left.data() + done, out.right.data() + done, block);
    done += block;
  }
  return out;
}

void start_gate_voice(RealtimeEngine& engine, const std::vector<float>& sample) {
  auto bank = PreparedSampleBank::empty(
      lmdj::foundation::ProjectId{"00000000-0000-4000-8000-000000000001"}, 1);
  LMDJ_CHECK(bank.set_sample(
                     0, sample,
                     ResolvedPlayback{0, static_cast<std::uint32_t>(sample.size()),
                                      TriggerMode::gate, 1.0F, false})
                 .has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                 1, 0, 127, PadControlKind::press, ResolvedPlayback{}}) ==
             EnqueueResult::accepted);
}

// Every voice attacks and releases over the 96-frame declick at exactly the
// scale a build with the voice DSP uses for a default envelope.
void a_voice_attacks_and_releases_over_the_declick() {
  RealtimeEngine engine;
  const std::vector<float> sample(1'000, 0.5F);
  start_gate_voice(engine, sample);
  const auto attack = render(engine, 200);
  for (std::size_t frame = 0; frame < 96; ++frame) {
    LMDJ_CHECK(attack.left[frame] ==
               0.5F * (static_cast<float>(frame) * (1.0F / 96.0F)));
  }
  LMDJ_CHECK(attack.left[96] == 0.5F);
  LMDJ_CHECK(attack.right == attack.left);
  LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                 2, 0, 0, PadControlKind::release, ResolvedPlayback{}}) ==
             EnqueueResult::accepted);
  const auto tail = render(engine, 97);
  LMDJ_CHECK(tail.left[0] == 0.5F);
  for (std::size_t frame = 1; frame < 96; ++frame) {
    LMDJ_CHECK(tail.left[frame] ==
               0.5F * (static_cast<float>(96 - frame) * (1.0F / 96.0F)));
  }
  LMDJ_CHECK(tail.left[96] == 0.0F);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
}

// A second stop during the declick tail ends the voice at once.
void a_second_stop_ends_the_tail() {
  RealtimeEngine engine;
  const std::vector<float> sample(1'000, 0.5F);
  start_gate_voice(engine, sample);
  render(engine, 200);
  LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                 2, 0, 0, PadControlKind::release, ResolvedPlayback{}}) ==
             EnqueueResult::accepted);
  render(engine, 10);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
  LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                 3, 0, 0, PadControlKind::stop_all, ResolvedPlayback{}}) ==
             EnqueueResult::accepted);
  const auto after = render(engine, 1);
  LMDJ_CHECK(after.left[0] == 0.0F);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
}

}  // namespace

int main() {
  try {
    cooker_accepts_exactly_the_shared_neutral_cases();
    cooker_reports_invalid_settings_as_invalid();
    a_voice_attacks_and_releases_over_the_declick();
    a_second_stop_ends_the_tail();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
