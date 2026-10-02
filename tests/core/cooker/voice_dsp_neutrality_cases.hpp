#pragma once

#include <cstdint>
#include <vector>

#include <lmdj/domain/project.hpp>

// Pad playbacks that are valid for an eight-frame source, each with whether it
// resolves to the neutral voice DSP block. project_cooker_test requires a build
// with the voice DSP to resolve exactly these to neutral, and
// voice_dsp_disabled_test requires a build without it (the Cardputer's) to
// accept exactly these, so the two builds cannot disagree about which Pads
// play. The neutral cases other than the defaults differ in Project Truth but
// resolve to nothing at 48 kHz.
struct VoiceDspNeutralityCase {
  const char* name;
  lmdj::domain::PadPlayback playback;
  std::uint32_t source_rate;
  bool neutral;
};

inline constexpr std::uint64_t kVoiceDspNeutralitySourceFrames = 8;

inline std::vector<VoiceDspNeutralityCase> voice_dsp_neutrality_cases() {
  using lmdj::domain::EqBandKind;
  using lmdj::domain::LoopMode;
  using lmdj::domain::PadEqBell;
  using lmdj::domain::PadEqShelf;
  using lmdj::domain::PadPlayback;
  using lmdj::domain::TriggerMode;
  const auto with = [](auto edit) {
    PadPlayback playback{1, 7, TriggerMode::loop_gate, 0, false};
    edit(playback);
    return playback;
  };
  return {
      {"defaults", with([](PadPlayback&) {}), 44'100, true},
      {"loop start at the trim start",
       with([](PadPlayback& p) { p.loop_start_frame = 1; }), 44'100, true},
      {"loop start inside the trim start's output frame",
       with([](PadPlayback& p) {
         p.trim_start_frame = 2;
         p.loop_start_frame = 3;
       }),
       96'000, true},
      {"crossfade shorter than one output frame",
       with([](PadPlayback& p) { p.loop_crossfade_frames = 1; }), 96'000, true},
      {"tone at the deadband's lower edge",
       with([](PadPlayback& p) { p.tone = -2; }), 44'100, true},
      {"tone at the deadband's upper edge",
       with([](PadPlayback& p) { p.tone = 2; }), 44'100, true},
      {"reverse", with([](PadPlayback& p) { p.reverse = true; }), 44'100, false},
      {"pitch", with([](PadPlayback& p) { p.pitch_cents = 1; }), 44'100, false},
      {"pan", with([](PadPlayback& p) { p.pan = 1; }), 44'100, false},
      {"ping-pong", with([](PadPlayback& p) { p.loop_mode = LoopMode::ping_pong; }),
       44'100, false},
      {"loop start", with([](PadPlayback& p) { p.loop_start_frame = 4; }), 44'100,
       false},
      {"crossfade", with([](PadPlayback& p) { p.loop_crossfade_frames = 1; }),
       44'100, false},
      {"attack", with([](PadPlayback& p) { p.attack_ms = 1; }), 44'100, false},
      {"release", with([](PadPlayback& p) { p.release_ms = 1; }), 44'100, false},
      {"tone below the deadband", with([](PadPlayback& p) { p.tone = -3; }), 44'100,
       false},
      {"tone above the deadband", with([](PadPlayback& p) { p.tone = 3; }), 44'100,
       false},
      {"flat low shelf",
       with([](PadPlayback& p) { p.eq.low = PadEqShelf{EqBandKind::shelf, 100, 0}; }),
       44'100, false},
      {"flat mid bell",
       with([](PadPlayback& p) { p.eq.mid = PadEqBell{1'000, 0, 700}; }), 44'100,
       false},
      {"high cut",
       with([](PadPlayback& p) { p.eq.high = PadEqShelf{EqBandKind::cut, 8'000, 0}; }),
       44'100, false},
  };
}
