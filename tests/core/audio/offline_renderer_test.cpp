#include <lmdj/audio/mix_math.hpp>
#include <lmdj/audio/offline_renderer.hpp>

#include <lmdj/cooker/project_cooker.hpp>
#include <lmdj/cooker/wav_reader.hpp>
#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/artifact.hpp>

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::OfflineRenderRequest;
using lmdj::audio::render_offline;
using lmdj::cooker::PcmSample;
using lmdj::cooker::ResolvedEvent;
using lmdj::cooker::ResolvedPad;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::AssignPad;
using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CreatePattern;
using lmdj::domain::ImportAsset;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::ProjectState;
using lmdj::domain::TriggerMode;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;

constexpr std::uint32_t kSampleRate = 48'000;
constexpr std::uint16_t kChannels = 2;
constexpr std::uint64_t kOneBarFrames = 96'000;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-audio-runtime-test-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::vector<std::byte> read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary | std::ios::ate);
  if (!stream) {
    throw std::runtime_error("failed to open test file: " + path.string());
  }
  const auto size = stream.tellg();
  if (size < 0) {
    throw std::runtime_error("failed to size test file: " + path.string());
  }
  std::vector<std::byte> bytes(static_cast<std::size_t>(size));
  stream.seekg(0);
  if (!bytes.empty()) {
    stream.read(
        reinterpret_cast<char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
  }
  if (!stream) {
    throw std::runtime_error("failed to read test file: " + path.string());
  }
  return bytes;
}

std::uint16_t read_u16(
    const std::vector<std::byte>& bytes,
    std::size_t offset) {
  return static_cast<std::uint16_t>(
      std::to_integer<std::uint8_t>(bytes.at(offset)) |
      (static_cast<std::uint16_t>(
           std::to_integer<std::uint8_t>(bytes.at(offset + 1)))
       << 8U));
}

std::uint32_t read_u32(
    const std::vector<std::byte>& bytes,
    std::size_t offset) {
  return static_cast<std::uint32_t>(
      std::to_integer<std::uint8_t>(bytes.at(offset)) |
      (static_cast<std::uint32_t>(
           std::to_integer<std::uint8_t>(bytes.at(offset + 1)))
       << 8U) |
      (static_cast<std::uint32_t>(
           std::to_integer<std::uint8_t>(bytes.at(offset + 2)))
       << 16U) |
      (static_cast<std::uint32_t>(
           std::to_integer<std::uint8_t>(bytes.at(offset + 3)))
       << 24U));
}

std::int16_t read_pcm16(
    const std::vector<std::byte>& bytes,
    std::uint64_t frame,
    std::uint16_t channel) {
  const auto offset =
      44U + static_cast<std::size_t>((frame * kChannels + channel) * 2U);
  return static_cast<std::int16_t>(read_u16(bytes, offset));
}

bool has_tag(
    const std::vector<std::byte>& bytes,
    std::size_t offset,
    const char* tag) {
  for (std::size_t index = 0; index < 4; ++index) {
    if (std::to_integer<char>(bytes.at(offset + index)) != tag[index]) {
      return false;
    }
  }
  return true;
}

std::shared_ptr<const PcmSample> sample(
    std::uint16_t channels,
    std::vector<std::int16_t> interleaved) {
  return std::make_shared<const PcmSample>(
      PcmSample{kSampleRate, channels, std::move(interleaved)});
}

std::shared_ptr<const RuntimeSnapshot> snapshot(
    std::vector<ResolvedEvent> events,
    std::uint16_t bpm = 120,
    std::uint8_t bars = 1) {
  std::vector<ResolvedPad> pads;
  for (const auto& event : events) {
    bool already_present = false;
    for (const auto& pad : pads) {
      already_present = already_present || pad.slot == event.slot;
    }
    if (already_present || event.sample == nullptr) {
      continue;
    }
    const auto frames = event.sample->interleaved.size() /
                        event.sample->channels;
    pads.push_back(ResolvedPad{
        event.slot,
        ArtifactRef{
            std::string(64, 'a'),
            "audio/wav",
            event.sample->interleaved.size() * sizeof(std::int16_t),
        },
        event.sample,
        ResolvedPlayback{
            0,
            static_cast<std::uint32_t>(frames),
            TriggerMode::one_shot,
            1.0F,
            false,
        },
    });
  }
  return std::make_shared<const RuntimeSnapshot>(
      RuntimeSnapshot{
          ProjectId{"00000000-0000-4000-8000-000000000001"},
          17,
          bpm,
          bars,
          std::move(pads),
          std::move(events),
      });
}

std::shared_ptr<const RuntimeSnapshot> snapshot_with_playback(
    ResolvedEvent event,
    ResolvedPlayback playback) {
  return std::make_shared<const RuntimeSnapshot>(RuntimeSnapshot{
      ProjectId{"00000000-0000-4000-8000-000000000001"},
      17,
      120,
      1,
      {
          ResolvedPad{
              event.slot,
              ArtifactRef{std::string(64, 'b'), "audio/wav", 16},
              event.sample,
              playback,
          },
      },
      {std::move(event)},
  });
}

std::shared_ptr<const PcmSample> fixture_sample(std::string_view filename) {
  const auto bytes =
      read_bytes(std::filesystem::path("tests/fixtures/audio") / filename);
  const auto decoded = lmdj::cooker::decode_wav(bytes);
  if (!decoded.has_value()) {
    throw std::runtime_error("failed to decode source fixture");
  }
  return decoded.value();
}

std::string expected_golden_sha() {
  std::ifstream stream(
      "tests/fixtures/golden/one_bar_120bpm.sha256",
      std::ios::binary);
  std::string digest;
  stream >> digest;
  if (digest.size() != 64) {
    throw std::runtime_error("invalid Golden Audio SHA fixture");
  }
  return digest;
}

void test_mix_math_uses_mathematical_floor_and_saturation() {
  using lmdj::audio::detail::floor_div;
  using lmdj::audio::detail::saturating_add;
  using lmdj::audio::detail::scale_velocity;

  static_assert(floor_div(-64, 127) == -1);
  static_assert(scale_velocity(-1, 127) == -1);
  static_assert(scale_velocity(1, 127) == 1);
  static_assert(scale_velocity(-2, 64) == -1);
  static_assert(saturating_add(32'760, 100) == 32'767);
  static_assert(saturating_add(-32'760, -100) == -32'768);

  LMDJ_CHECK(scale_velocity(1'000, 64) == 504);
  LMDJ_CHECK(saturating_add(32'760, 100) == 32'767);
  LMDJ_CHECK(saturating_add(-32'760, -100) == -32'768);
}

void test_render_writes_exact_header_frame_count_and_step_positions() {
  TempDirectory temp;
  const auto impulse = sample(1, {1'200});
  const auto input = snapshot({
      {PadSlotId{0, 0}, 0, 127, impulse},
      {PadSlotId{0, 0}, 4, 127, impulse},
      {PadSlotId{0, 0}, 8, 127, impulse},
      {PadSlotId{0, 0}, 12, 127, impulse},
  });
  const auto output_path = temp.path() / "positions.wav";

  const auto rendered =
      render_offline(OfflineRenderRequest{input, output_path});

  LMDJ_CHECK(rendered.has_value());
  LMDJ_CHECK(rendered.value().frame_count == kOneBarFrames);
  LMDJ_CHECK(rendered.value().sample_rate == kSampleRate);
  LMDJ_CHECK(rendered.value().channels == kChannels);
  LMDJ_CHECK(rendered.value().artifact.media_type == "audio/wav");

  const auto wav = read_bytes(output_path);
  LMDJ_CHECK(wav.size() == 44U + kOneBarFrames * kChannels * 2U);
  LMDJ_CHECK(has_tag(wav, 0, "RIFF"));
  LMDJ_CHECK(read_u32(wav, 4) == wav.size() - 8U);
  LMDJ_CHECK(has_tag(wav, 8, "WAVE"));
  LMDJ_CHECK(has_tag(wav, 12, "fmt "));
  LMDJ_CHECK(read_u32(wav, 16) == 16);
  LMDJ_CHECK(read_u16(wav, 20) == 1);
  LMDJ_CHECK(read_u16(wav, 22) == kChannels);
  LMDJ_CHECK(read_u32(wav, 24) == kSampleRate);
  LMDJ_CHECK(read_u32(wav, 28) == 192'000);
  LMDJ_CHECK(read_u16(wav, 32) == 4);
  LMDJ_CHECK(read_u16(wav, 34) == 16);
  LMDJ_CHECK(has_tag(wav, 36, "data"));
  LMDJ_CHECK(read_u32(wav, 40) == kOneBarFrames * kChannels * 2U);

  for (const auto frame :
       {std::uint64_t{0}, std::uint64_t{24'000},
        std::uint64_t{48'000}, std::uint64_t{72'000}}) {
    LMDJ_CHECK(read_pcm16(wav, frame, 0) == 1'200);
    LMDJ_CHECK(read_pcm16(wav, frame, 1) == 1'200);
    LMDJ_CHECK(read_pcm16(wav, frame + 1, 0) == 0);
    LMDJ_CHECK(read_pcm16(wav, frame + 1, 1) == 0);
  }
}

void test_render_preserves_stereo_and_scales_velocity() {
  TempDirectory temp;
  const auto stereo = sample(2, {-2, 1'000});
  const auto input =
      snapshot({{PadSlotId{0, 1}, 0, 64, stereo}});
  const auto output_path = temp.path() / "stereo-velocity.wav";

  const auto rendered =
      render_offline(OfflineRenderRequest{input, output_path});

  LMDJ_CHECK(rendered.has_value());
  const auto wav = read_bytes(output_path);
  LMDJ_CHECK(read_pcm16(wav, 0, 0) == -1);
  LMDJ_CHECK(read_pcm16(wav, 0, 1) == 504);
}

void test_pattern_events_apply_trim_gain_and_mute_as_one_shot_starts() {
  TempDirectory temp;
  const auto stereo = sample(
      2,
      {100, -100, 2'000, -2'000, 3'000, -3'000, 4'000, -4'000});
  const auto trimmed = snapshot_with_playback(
      ResolvedEvent{PadSlotId{0, 0}, 0, 127, stereo},
      ResolvedPlayback{
          1, 3, TriggerMode::loop_toggle, 0.5F, false});
  const auto trimmed_path = temp.path() / "trimmed.wav";

  const auto rendered =
      render_offline(OfflineRenderRequest{trimmed, trimmed_path});

  LMDJ_CHECK(rendered.has_value());
  const auto wav = read_bytes(trimmed_path);
  LMDJ_CHECK(read_pcm16(wav, 0, 0) == 1'000);
  LMDJ_CHECK(read_pcm16(wav, 0, 1) == -1'000);
  LMDJ_CHECK(read_pcm16(wav, 1, 0) == 1'500);
  LMDJ_CHECK(read_pcm16(wav, 1, 1) == -1'500);
  LMDJ_CHECK(read_pcm16(wav, 2, 0) == 0);
  LMDJ_CHECK(read_pcm16(wav, 2, 1) == 0);

  const auto muted = snapshot_with_playback(
      ResolvedEvent{PadSlotId{0, 0}, 0, 127, stereo},
      ResolvedPlayback{0, 4, TriggerMode::gate, 1.0F, true});
  const auto muted_path = temp.path() / "muted.wav";
  LMDJ_CHECK(render_offline(OfflineRenderRequest{muted, muted_path})
                 .has_value());
  const auto muted_wav = read_bytes(muted_path);
  for (std::uint64_t frame = 0; frame < 4; ++frame) {
    LMDJ_CHECK(read_pcm16(muted_wav, frame, 0) == 0);
    LMDJ_CHECK(read_pcm16(muted_wav, frame, 1) == 0);
  }
}

void test_render_saturates_overlapping_events_without_wrap() {
  TempDirectory temp;
  const auto loud = sample(2, {30'000, -30'000});
  const auto input = snapshot({
      {PadSlotId{0, 0}, 0, 127, loud},
      {PadSlotId{0, 1}, 0, 127, loud},
  });
  const auto output_path = temp.path() / "saturation.wav";

  const auto rendered =
      render_offline(OfflineRenderRequest{input, output_path});

  LMDJ_CHECK(rendered.has_value());
  const auto wav = read_bytes(output_path);
  LMDJ_CHECK(read_pcm16(wav, 0, 0) == 32'767);
  LMDJ_CHECK(read_pcm16(wav, 0, 1) == -32'768);
}

void test_render_saturates_each_event_in_snapshot_order() {
  TempDirectory temp;
  const auto positive = sample(1, {30'000});
  const auto negative = sample(1, {-30'000});
  const auto forward_path = temp.path() / "mixed-forward.wav";
  const auto reverse_path = temp.path() / "mixed-reverse.wav";

  const auto forward =
      render_offline(
          OfflineRenderRequest{
              snapshot({
                  {PadSlotId{0, 0}, 0, 127, positive},
                  {PadSlotId{0, 1}, 0, 127, positive},
                  {PadSlotId{0, 2}, 0, 127, negative},
              }),
              forward_path,
          });
  const auto reverse =
      render_offline(
          OfflineRenderRequest{
              snapshot({
                  {PadSlotId{0, 2}, 0, 127, negative},
                  {PadSlotId{0, 0}, 0, 127, positive},
                  {PadSlotId{0, 1}, 0, 127, positive},
              }),
              reverse_path,
          });

  LMDJ_CHECK(forward.has_value());
  LMDJ_CHECK(reverse.has_value());
  const auto forward_wav = read_bytes(forward_path);
  const auto reverse_wav = read_bytes(reverse_path);
  LMDJ_CHECK(read_pcm16(forward_wav, 0, 0) == 2'767);
  LMDJ_CHECK(read_pcm16(forward_wav, 0, 1) == 2'767);
  LMDJ_CHECK(read_pcm16(reverse_wav, 0, 0) == 30'000);
  LMDJ_CHECK(read_pcm16(reverse_wav, 0, 1) == 30'000);
}

void test_render_does_not_mutate_the_input_snapshot() {
  TempDirectory temp;
  const auto source = sample(1, {-1, 2, -3});
  const auto input =
      snapshot({{PadSlotId{0, 2}, 8, 96, source}});
  static_assert(
      std::is_const_v<std::remove_reference_t<decltype(*input)>>);
  const auto source_before = source->interleaved;
  const auto event_before = input->events.front();

  const auto rendered =
      render_offline(
          OfflineRenderRequest{input, temp.path() / "immutable.wav"});

  LMDJ_CHECK(rendered.has_value());
  LMDJ_CHECK(input->project_revision == 17);
  LMDJ_CHECK(input->bpm == 120);
  LMDJ_CHECK(input->bars == 1);
  LMDJ_CHECK(input->events.size() == 1);
  LMDJ_CHECK(input->events.front().slot == event_before.slot);
  LMDJ_CHECK(input->events.front().step == event_before.step);
  LMDJ_CHECK(input->events.front().velocity == event_before.velocity);
  LMDJ_CHECK(input->events.front().sample == event_before.sample);
  LMDJ_CHECK(source->interleaved == source_before);
}

void test_render_matches_independent_golden_audio_sha() {
  TempDirectory temp;
  const auto kick = fixture_sample("kick.wav");
  const auto snare = fixture_sample("snare.wav");
  const auto input = snapshot({
      {PadSlotId{0, 0}, 0, 127, kick},
      {PadSlotId{0, 1}, 4, 127, snare},
      {PadSlotId{0, 0}, 8, 127, kick},
      {PadSlotId{0, 1}, 12, 127, snare},
  });
  const auto output_path = temp.path() / "one_bar_120bpm.wav";

  const auto rendered =
      render_offline(OfflineRenderRequest{input, output_path});

  LMDJ_CHECK(rendered.has_value());
  LMDJ_CHECK(rendered.value().artifact.sha256 == expected_golden_sha());
  LMDJ_CHECK(
      read_bytes(output_path) ==
      read_bytes("tests/fixtures/golden/one_bar_120bpm.wav"));
  const auto independently_described =
      lmdj::foundation::describe_artifact(output_path, "audio/wav");
  LMDJ_CHECK(independently_described.has_value());
  LMDJ_CHECK(
      rendered.value().artifact == independently_described.value());
}

void test_authoring_project_cooks_directly_into_golden_render() {
  constexpr auto kProjectIdValue =
      "00000000-0000-4000-8000-000000000011";
  constexpr auto kKickAssetId =
      "20000000-0000-4000-8000-000000000011";
  constexpr auto kSnareAssetId =
      "20000000-0000-4000-8000-000000000012";
  constexpr auto kPatternId =
      "30000000-0000-4000-8000-000000000011";
  constexpr auto kImportKickCommand =
      "10000000-0000-4000-8000-000000000011";
  constexpr auto kImportSnareCommand =
      "10000000-0000-4000-8000-000000000012";
  constexpr auto kAssignKickCommand =
      "10000000-0000-4000-8000-000000000013";
  constexpr auto kAssignSnareCommand =
      "10000000-0000-4000-8000-000000000014";
  constexpr auto kCreatePatternCommand =
      "10000000-0000-4000-8000-000000000015";

  const auto apply_command =
      [](const ProjectState& state, const Command& command) {
        const auto applied = lmdj::domain::apply(state, command, {});
        LMDJ_CHECK(applied.has_value());
        return applied.value().state;
      };
  const auto kick_path =
      std::filesystem::path{"tests/fixtures/audio/kick.wav"};
  const auto snare_path =
      std::filesystem::path{"tests/fixtures/audio/snare.wav"};
  const auto kick_artifact =
      lmdj::foundation::describe_artifact(kick_path, "audio/wav");
  const auto snare_artifact =
      lmdj::foundation::describe_artifact(snare_path, "audio/wav");
  LMDJ_CHECK(kick_artifact.has_value());
  LMDJ_CHECK(snare_artifact.has_value());
  const auto kick_bytes = read_bytes(kick_path);
  const auto snare_bytes = read_bytes(snare_path);

  auto created =
      lmdj::domain::create_project(ProjectId{kProjectIdValue}, 120);
  LMDJ_CHECK(created.has_value());
  auto project = created.value();
  project = apply_command(
      project,
      Command{ImportAsset{
          CommandMeta{
              CommandId{kImportKickCommand},
              project.revision,
          },
          {
              AssetId{kKickAssetId},
              kick_artifact.value(),
          },
      }});
  project = apply_command(
      project,
      Command{ImportAsset{
          CommandMeta{
              CommandId{kImportSnareCommand},
              project.revision,
          },
          {
              AssetId{kSnareAssetId},
              snare_artifact.value(),
          },
      }});
  project = apply_command(
      project,
      Command{AssignPad{
          CommandMeta{
              CommandId{kAssignKickCommand},
              project.revision,
          },
          PadSlotId{0, 0},
          AssetId{kKickAssetId},
      }});
  project = apply_command(
      project,
      Command{AssignPad{
          CommandMeta{
              CommandId{kAssignSnareCommand},
              project.revision,
          },
          PadSlotId{0, 1},
          AssetId{kSnareAssetId},
      }});
  project = apply_command(
      project,
      Command{CreatePattern{
          CommandMeta{
              CommandId{kCreatePatternCommand},
              project.revision,
          },
          Pattern{
              PatternId{kPatternId},
              1,
              {
                  {PadSlotId{0, 0}, 0, 127},
                  {PadSlotId{0, 1}, 4, 127},
                  {PadSlotId{0, 0}, 8, 127},
                  {PadSlotId{0, 1}, 12, 127},
              },
          },
      }});

  const auto cooked =
      lmdj::cooker::cook(
          project,
          PatternId{kPatternId},
          [
              kick_artifact = kick_artifact.value(),
              snare_artifact = snare_artifact.value(),
              kick_bytes,
              snare_bytes
          ](const ArtifactRef& artifact)
              -> lmdj::foundation::Result<std::vector<std::byte>> {
            if (artifact == kick_artifact) {
              return lmdj::foundation::Result<
                  std::vector<std::byte>>::success(kick_bytes);
            }
            if (artifact == snare_artifact) {
              return lmdj::foundation::Result<
                  std::vector<std::byte>>::success(snare_bytes);
            }
            return lmdj::foundation::Result<
                std::vector<std::byte>>::failure(
                lmdj::foundation::Error{
                    ErrorCode::not_found,
                    "Derived Runtime fixture is unavailable",
                });
          });
  LMDJ_CHECK(cooked.has_value());
  LMDJ_CHECK(cooked.value()->events.size() == 4);

  TempDirectory temp;
  const auto output_path = temp.path() / "derived-runtime.wav";
  const auto rendered =
      render_offline(
          OfflineRenderRequest{cooked.value(), output_path});

  LMDJ_CHECK(rendered.has_value());
  LMDJ_CHECK(rendered.value().artifact.sha256 == expected_golden_sha());
  LMDJ_CHECK(
      read_bytes(output_path) ==
      read_bytes("tests/fixtures/golden/one_bar_120bpm.wav"));
}

void test_render_rejects_a_missing_snapshot() {
  TempDirectory temp;
  const auto rendered =
      render_offline(
          OfflineRenderRequest{nullptr, temp.path() / "missing.wav"});

  LMDJ_CHECK(!rendered.has_value());
  LMDJ_CHECK(rendered.error().code == ErrorCode::invalid_argument);
}

void expect_invalid_snapshot(
    std::shared_ptr<const RuntimeSnapshot> input,
    const std::filesystem::path& output_path) {
  const auto rendered =
      render_offline(OfflineRenderRequest{input, output_path});

  LMDJ_CHECK(!rendered.has_value());
  LMDJ_CHECK(rendered.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!std::filesystem::exists(output_path));
}

void test_render_rejects_snapshot_invariants_before_allocating() {
  TempDirectory temp;
  expect_invalid_snapshot(
      snapshot({}, 1, 255),
      temp.path() / "oversized-invalid.wav");
  expect_invalid_snapshot(
      snapshot({}, 39, 1),
      temp.path() / "bpm-low.wav");
  expect_invalid_snapshot(
      snapshot({}, 241, 1),
      temp.path() / "bpm-high.wav");
  expect_invalid_snapshot(
      snapshot({}, 120, 3),
      temp.path() / "bars-invalid.wav");

  const auto impulse = sample(1, {1});
  expect_invalid_snapshot(
      snapshot(
          {{PadSlotId{0, 0}, 128, 127, impulse}},
          40,
          8),
      temp.path() / "step-invalid.wav");
}

void test_render_accepts_the_largest_task5_snapshot_shape() {
  TempDirectory temp;
  const auto rendered =
      render_offline(
          OfflineRenderRequest{
              snapshot({}, 40, 8),
              temp.path() / "task5-maximum.wav",
          });

  LMDJ_CHECK(rendered.has_value());
  LMDJ_CHECK(rendered.value().frame_count == 2'304'000);
  LMDJ_CHECK(
      rendered.value().artifact.byte_length ==
      44U + 2'304'000U * kChannels * 2U);
}

}  // namespace

int main() {
  try {
    test_mix_math_uses_mathematical_floor_and_saturation();
    test_render_writes_exact_header_frame_count_and_step_positions();
    test_render_preserves_stereo_and_scales_velocity();
    test_pattern_events_apply_trim_gain_and_mute_as_one_shot_starts();
    test_render_saturates_overlapping_events_without_wrap();
    test_render_saturates_each_event_in_snapshot_order();
    test_render_does_not_mutate_the_input_snapshot();
    test_render_matches_independent_golden_audio_sha();
    test_authoring_project_cooks_directly_into_golden_render();
    test_render_rejects_a_missing_snapshot();
    test_render_rejects_snapshot_invariants_before_allocating();
    test_render_accepts_the_largest_task5_snapshot_shape();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "audio offline renderer tests: PASS\n";
  return 0;
}
