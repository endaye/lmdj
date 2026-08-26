#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <lmdj/cooker/project_cooker.hpp>
#include <lmdj/domain/command_handler.hpp>

#include "tests/core/support/deterministic_rng.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::cooker::ArtifactResolver;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::AssignPad;
using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CreatePattern;
using lmdj::domain::ImportAsset;
using lmdj::domain::PadSlotId;
using lmdj::domain::PadPlayback;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::ProjectState;
using lmdj::domain::TriggerMode;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::Result;
using lmdj::test::DeterministicRng;

constexpr std::string_view kMonoSha =
    "b921463fe1cb521fa6734fe8f04a002bd4b99faf44c811d2b833b21ee7e7a5e9";
constexpr std::string_view kStereoSha =
    "8ed906292be8d7ecd66263e66187af80719a79e6b2934759c3d0f06b4c02421b";
constexpr std::string_view kUnsupportedSha =
    "e1bfa728d85c1034701e9bf80c6bc99aa40dd8eb713c576b53ea4fd6aa5d9635";
constexpr std::array<std::int16_t, 4> kMonoSamples{
    32767, -32768, 123, -456};
constexpr std::array<std::int16_t, 8> kStereoSamples{
    32767, -32768, -32768, 32767, 123, -789, -456, 1011};

float expected_linear_gain(std::int32_t gain_millidb) {
  switch (gain_millidb) {
    case -60'000:
      return 0x1.0624dep-10F;
    case -6'000:
      return 0x1.009b9cp-1F;
    case -3'000:
      return 0x1.6a77dep-1F;
    case 0:
      return 1.0F;
    case 6'000:
      return 0x1.fec982p+0F;
  }
  throw std::runtime_error("unexpected gain golden input");
}

std::string generated_uuid(char family, std::uint64_t seed,
                           std::uint64_t ordinal) {
  std::ostringstream value;
  value << family << "0000000-0000-4000-8000-"
        << std::hex << std::nouppercase << std::setfill('0')
        << std::setw(4) << seed
        << std::setw(8) << ordinal;
  return value.str();
}

void append_u16(std::vector<std::byte>& bytes, std::uint16_t value) {
  bytes.push_back(static_cast<std::byte>(value & 0xffU));
  bytes.push_back(static_cast<std::byte>(value >> 8U));
}

void append_u32(std::vector<std::byte>& bytes, std::uint32_t value) {
  for (std::uint32_t shift = 0; shift < 32U; shift += 8U) {
    bytes.push_back(static_cast<std::byte>(value >> shift));
  }
}

void append_ascii(std::vector<std::byte>& bytes, std::string_view value) {
  for (const char character : value) {
    bytes.push_back(
        static_cast<std::byte>(static_cast<unsigned char>(character)));
  }
}

template <std::size_t SampleCount>
std::vector<std::byte> pcm16_wav(
    std::uint16_t channels,
    const std::array<std::int16_t, SampleCount>& samples) {
  const auto data_size =
      static_cast<std::uint32_t>(samples.size() * sizeof(std::int16_t));
  std::vector<std::byte> bytes;
  bytes.reserve(44U + data_size);
  append_ascii(bytes, "RIFF");
  append_u32(bytes, 36U + data_size);
  append_ascii(bytes, "WAVEfmt ");
  append_u32(bytes, 16);
  append_u16(bytes, 1);
  append_u16(bytes, channels);
  append_u32(bytes, 48000);
  append_u32(bytes, 48000U * channels * sizeof(std::int16_t));
  append_u16(
      bytes,
      static_cast<std::uint16_t>(channels * sizeof(std::int16_t)));
  append_u16(bytes, 16);
  append_ascii(bytes, "data");
  append_u32(bytes, data_size);
  for (const auto sample : samples) {
    append_u16(bytes, static_cast<std::uint16_t>(sample));
  }
  return bytes;
}

struct Fixtures {
  std::vector<std::byte> mono = pcm16_wav(1, kMonoSamples);
  std::vector<std::byte> stereo = pcm16_wav(2, kStereoSamples);

  ArtifactRef mono_artifact() const {
    return ArtifactRef{
        std::string(kMonoSha), "audio/wav", mono.size()};
  }

  ArtifactRef stereo_artifact() const {
    return ArtifactRef{
        std::string(kStereoSha), "audio/wav", stereo.size()};
  }
};

struct ResolverTrace {
  std::uint32_t calls{};
  std::map<std::string, std::uint32_t> calls_by_sha;
};

enum class InvalidArtifactMode {
  none,
  corrupt_bytes,
  unavailable,
  unsupported_bytes,
};

ArtifactResolver resolver_for(
    const Fixtures& fixtures,
    ResolverTrace& trace,
    InvalidArtifactMode invalid_mode = InvalidArtifactMode::none) {
  const std::map<std::string, std::vector<std::byte>> bytes_by_sha{
      {std::string(kMonoSha), fixtures.mono},
      {std::string(kStereoSha), fixtures.stereo},
      {
          std::string(kUnsupportedSha),
          {
              std::byte{'B'},
              std::byte{'A'},
              std::byte{'D'},
              std::byte{'!'},
          },
      },
  };
  return [
      bytes_by_sha,
      &trace,
      invalid_mode
  ](const ArtifactRef& artifact) -> Result<std::vector<std::byte>> {
    ++trace.calls;
    ++trace.calls_by_sha[artifact.sha256];
    if (
        invalid_mode == InvalidArtifactMode::unavailable &&
        artifact.sha256 == kStereoSha) {
      return Result<std::vector<std::byte>>::failure(
          Error{ErrorCode::not_found, "in-memory PCM fixture is unavailable"});
    }
    const auto found = bytes_by_sha.find(artifact.sha256);
    if (found == bytes_by_sha.end()) {
      return Result<std::vector<std::byte>>::failure(
          Error{ErrorCode::not_found, "in-memory PCM fixture is unavailable"});
    }
    auto bytes = found->second;
    if (
        invalid_mode == InvalidArtifactMode::corrupt_bytes &&
        artifact.sha256 == kStereoSha) {
      bytes.back() ^= std::byte{0x01};
    }
    return Result<std::vector<std::byte>>::success(std::move(bytes));
  };
}

ProjectState apply_or_throw(
    const ProjectState& project,
    const Command& command) {
  const auto applied = lmdj::domain::apply(project, command, {});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(applied.value().state.revision == project.revision + 1U);
  return applied.value().state;
}

struct GeneratedProject {
  ProjectState state;
  PatternId pattern_id;
  AssetId stereo_asset;
  PadSlotId reassigned_slot;
  PadSlotId mono_slot;
  PadSlotId stereo_slot;
};

GeneratedProject generated_project(
    std::uint64_t seed,
    DeterministicRng& rng,
    const Fixtures& fixtures) {
  const auto created = lmdj::domain::create_project(
      ProjectId{generated_uuid('0', seed, 1)},
      static_cast<std::uint16_t>(40U + rng.bounded(201)));
  LMDJ_CHECK(created.has_value());
  auto project = created.value();

  const AssetId mono_first{generated_uuid('2', seed, 1)};
  const AssetId mono_second{generated_uuid('2', seed, 2)};
  const AssetId stereo{generated_uuid('2', seed, 3)};
  const PadSlotId reassigned_slot{
      static_cast<std::uint8_t>(seed % 4U),
      static_cast<std::uint8_t>(seed % 16U),
  };
  const PadSlotId mono_slot{
      static_cast<std::uint8_t>((seed + 1U) % 4U),
      static_cast<std::uint8_t>((seed + 5U) % 16U),
  };
  const PadSlotId stereo_slot{
      static_cast<std::uint8_t>((seed + 2U) % 4U),
      static_cast<std::uint8_t>((seed + 9U) % 16U),
  };
  const PadSlotId duplicate_mono_slot{
      static_cast<std::uint8_t>((seed + 3U) % 4U),
      static_cast<std::uint8_t>((seed + 13U) % 16U),
  };
  const PatternId pattern_id{generated_uuid('3', seed, 1)};
  std::uint64_t command = 1;
  const auto meta = [&]() {
    return CommandMeta{
        CommandId{generated_uuid('1', seed, command++)},
        project.revision,
    };
  };

  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(), {mono_first, fixtures.mono_artifact()}}});
  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(), {mono_second, fixtures.mono_artifact()}}});
  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(), {stereo, fixtures.stereo_artifact()}}});
  project = apply_or_throw(
      project,
      Command{AssignPad{meta(), reassigned_slot, mono_first}});
  project = apply_or_throw(
      project,
      Command{AssignPad{meta(), mono_slot, mono_second}});
  project = apply_or_throw(
      project,
      Command{AssignPad{meta(), stereo_slot, stereo}});
  project = apply_or_throw(
      project,
      Command{AssignPad{meta(), duplicate_mono_slot, mono_first}});

  std::vector<PatternEvent> events{
      {mono_slot, 0, lmdj::domain::kSixteenthTicks, 127},
      {reassigned_slot,
       lmdj::domain::kSixteenthTicks,
       lmdj::domain::kSixteenthTicks,
       126},
      {stereo_slot,
       2 * lmdj::domain::kSixteenthTicks,
       lmdj::domain::kSixteenthTicks,
       125},
      {duplicate_mono_slot,
       3 * lmdj::domain::kSixteenthTicks,
       lmdj::domain::kSixteenthTicks,
       124},
  };
  for (std::uint32_t step = 4; step < 16; ++step) {
    const std::array slots{reassigned_slot, mono_slot, stereo_slot};
    events.push_back(PatternEvent{
        slots.at(rng.bounded(slots.size())),
        step * lmdj::domain::kSixteenthTicks,
        lmdj::domain::kSixteenthTicks,
        static_cast<std::uint8_t>(1U + rng.bounded(127)),
    });
  }
  project = apply_or_throw(
      project,
      Command{CreatePattern{
          meta(), Pattern{pattern_id, 1, std::move(events)}}});
  project = apply_or_throw(
      project,
      Command{AssignPad{meta(), reassigned_slot, stereo}});

  project.banks.at(reassigned_slot.bank).at(reassigned_slot.pad).playback =
      PadPlayback{
          seed % 3U,
          4,
          static_cast<TriggerMode>(seed % 4U),
          std::array<std::int32_t, 4>{-60'000, -6'000, 0, 6'000}.at(
              seed % 4U),
          (seed & 1U) != 0U,
      };
  project.banks.at(mono_slot.bank).at(mono_slot.pad).playback = PadPlayback{
      1, 3, TriggerMode::gate, -3'000, false};
  project.banks.at(stereo_slot.bank).at(stereo_slot.pad).playback = PadPlayback{
      0, std::nullopt, TriggerMode::loop_gate, 0, false};
  project.banks.at(duplicate_mono_slot.bank)
      .at(duplicate_mono_slot.pad)
      .playback = PadPlayback{
      0, 1, TriggerMode::loop_toggle, 6'000, true};

  return GeneratedProject{
      std::move(project),
      pattern_id,
      stereo,
      reassigned_slot,
      mono_slot,
      stereo_slot,
  };
}

void check_snapshots_equal(
    const RuntimeSnapshot& first,
    const RuntimeSnapshot& second) {
  LMDJ_CHECK(first.project_id == second.project_id);
  LMDJ_CHECK(first.pattern_id == second.pattern_id);
  LMDJ_CHECK(first.project_revision == second.project_revision);
  LMDJ_CHECK(first.bpm == second.bpm);
  LMDJ_CHECK(first.bars == second.bars);
  LMDJ_CHECK(first.ppq == second.ppq);
  LMDJ_CHECK(first.loop_length_ticks == second.loop_length_ticks);
  LMDJ_CHECK(first.pads.size() == second.pads.size());
  for (std::size_t index = 0; index < first.pads.size(); ++index) {
    const auto& left = first.pads.at(index);
    const auto& right = second.pads.at(index);
    LMDJ_CHECK(left.slot == right.slot);
    LMDJ_CHECK(left.artifact == right.artifact);
    LMDJ_CHECK(left.sample != nullptr);
    LMDJ_CHECK(right.sample != nullptr);
    LMDJ_CHECK(left.sample->sample_rate == right.sample->sample_rate);
    LMDJ_CHECK(left.sample->channels == right.sample->channels);
    LMDJ_CHECK(left.sample->interleaved == right.sample->interleaved);
    LMDJ_CHECK(left.playback.start_frame == right.playback.start_frame);
    LMDJ_CHECK(left.playback.end_frame == right.playback.end_frame);
    LMDJ_CHECK(left.playback.trigger_mode == right.playback.trigger_mode);
    LMDJ_CHECK(left.playback.linear_gain == right.playback.linear_gain);
    LMDJ_CHECK(left.playback.muted == right.playback.muted);
  }
  LMDJ_CHECK(first.events.size() == second.events.size());
  for (std::size_t index = 0; index < first.events.size(); ++index) {
    const auto& left = first.events.at(index);
    const auto& right = second.events.at(index);
    LMDJ_CHECK(left.slot == right.slot);
    LMDJ_CHECK(left.onset_tick == right.onset_tick);
    LMDJ_CHECK(left.duration_tick == right.duration_tick);
    LMDJ_CHECK(left.velocity == right.velocity);
    LMDJ_CHECK(left.sample != nullptr);
    LMDJ_CHECK(right.sample != nullptr);
    LMDJ_CHECK(left.sample->sample_rate == right.sample->sample_rate);
    LMDJ_CHECK(left.sample->channels == right.sample->channels);
    LMDJ_CHECK(
        left.sample->interleaved.size() ==
        right.sample->interleaved.size());
    for (std::size_t sample = 0;
         sample < left.sample->interleaved.size();
         ++sample) {
      LMDJ_CHECK(
          left.sample->interleaved.at(sample) ==
          right.sample->interleaved.at(sample));
    }
  }
}

template <typename Scenario>
void for_each_seed(Scenario&& scenario) {
  for (std::uint64_t seed = 0; seed <= 255; ++seed) {
    try {
      scenario(seed);
    } catch (const std::exception& error) {
      throw std::runtime_error(
          "seed " + std::to_string(seed) + ": " + error.what());
    }
  }
}

struct MatrixEvidence {
  std::uint64_t deterministic_cooks{};
  std::uint64_t deduplicated_resolutions{};
  std::uint64_t rejected_partial_snapshots{};
  std::uint64_t current_slot_resolutions{};
  std::uint64_t resolved_playback_values{};
};

MatrixEvidence run_determinism_matrix() {
  MatrixEvidence evidence;
  const Fixtures fixtures;
  LMDJ_CHECK(fixtures.mono.size() == 52);
  LMDJ_CHECK(fixtures.stereo.size() == 60);

  for_each_seed([&](std::uint64_t seed) {
    DeterministicRng rng(seed);
    const auto generated = generated_project(seed, rng, fixtures);
    const auto immutable_project = generated.state;

    ResolverTrace first_trace;
    ResolverTrace second_trace;
    const auto first = lmdj::cooker::cook(
        generated.state,
        generated.pattern_id,
        resolver_for(fixtures, first_trace));
    const auto second = lmdj::cooker::cook(
        generated.state,
        generated.pattern_id,
        resolver_for(fixtures, second_trace));
    LMDJ_CHECK(first.has_value());
    LMDJ_CHECK(second.has_value());
    LMDJ_CHECK(generated.state == immutable_project);
    check_snapshots_equal(*first.value(), *second.value());
    ++evidence.deterministic_cooks;

    for (const auto* trace : {&first_trace, &second_trace}) {
      LMDJ_CHECK(trace->calls == 2);
      LMDJ_CHECK(trace->calls_by_sha.at(std::string(kMonoSha)) == 1);
      LMDJ_CHECK(trace->calls_by_sha.at(std::string(kStereoSha)) == 1);
    }
    const auto& pads = first.value()->pads;
    LMDJ_CHECK(pads.size() == 4);
    for (std::size_t index = 1; index < pads.size(); ++index) {
      const auto left = static_cast<std::uint16_t>(
                            pads.at(index - 1).slot.bank) *
                            16U +
                        pads.at(index - 1).slot.pad;
      const auto right = static_cast<std::uint16_t>(
                             pads.at(index).slot.bank) *
                             16U +
                         pads.at(index).slot.pad;
      LMDJ_CHECK(left < right);
    }
    for (const auto& pad : pads) {
      const auto& playback = generated.state.banks.at(pad.slot.bank)
                                 .at(pad.slot.pad)
                                 .playback;
      LMDJ_CHECK(pad.playback.start_frame == playback.trim_start_frame);
      LMDJ_CHECK(
          pad.playback.end_frame == playback.trim_end_frame.value_or(4));
      LMDJ_CHECK(pad.playback.trigger_mode == playback.trigger_mode);
      LMDJ_CHECK(
          pad.playback.linear_gain ==
          expected_linear_gain(playback.gain_millidb));
      LMDJ_CHECK(pad.playback.muted == playback.muted);
    }
    ++evidence.resolved_playback_values;
    const auto& events = first.value()->events;
    LMDJ_CHECK(events.at(0).sample != events.at(1).sample);
    LMDJ_CHECK(events.at(1).sample == events.at(2).sample);
    LMDJ_CHECK(events.at(0).sample == events.at(3).sample);
    for (const auto& event : events) {
      const auto pad = std::find_if(
          pads.begin(), pads.end(), [&](const auto& candidate) {
            return candidate.slot == event.slot;
          });
      LMDJ_CHECK(pad != pads.end());
      LMDJ_CHECK(pad->sample == event.sample);
    }
    ++evidence.deduplicated_resolutions;

    LMDJ_CHECK(events.at(1).slot == generated.reassigned_slot);
    LMDJ_CHECK(events.at(1).sample->channels == 2);
    LMDJ_CHECK(events.at(1).sample->interleaved.size() == kStereoSamples.size());
    for (std::size_t index = 0; index < kStereoSamples.size(); ++index) {
      LMDJ_CHECK(
          events.at(1).sample->interleaved.at(index) ==
          kStereoSamples.at(index));
    }
    ++evidence.current_slot_resolutions;

    auto invalid_project = generated.state;
    const auto invalid_mode = seed % 5U;
    auto resolver_mode = InvalidArtifactMode::none;
    auto expected_error = ErrorCode::invalid_project;
    if (invalid_mode == 0U) {
      resolver_mode = InvalidArtifactMode::corrupt_bytes;
      expected_error = ErrorCode::cook_failed;
    } else if (invalid_mode == 1U) {
      resolver_mode = InvalidArtifactMode::unavailable;
      expected_error = ErrorCode::not_found;
    } else if (invalid_mode == 2U) {
      resolver_mode = InvalidArtifactMode::unsupported_bytes;
      expected_error = ErrorCode::unsupported_audio;
      invalid_project.assets.at(generated.stereo_asset).artifact =
          ArtifactRef{
              std::string(kUnsupportedSha),
              "audio/wav",
              4,
          };
    } else if (invalid_mode == 3U) {
      invalid_project.assets.at(generated.stereo_asset).artifact.sha256 =
          "invalid";
    } else {
      invalid_project.assets.at(generated.stereo_asset).artifact.sha256 =
          std::string(64, 'g');
    }

    std::set<std::string> resolver_hashes_before_failure;
    for (const auto& bank : invalid_project.banks) {
      bool reached_invalid_asset = false;
      for (const auto& pad : bank) {
        if (!pad.asset_id.has_value()) {
          continue;
        }
        if (*pad.asset_id == generated.stereo_asset) {
          if (invalid_mode <= 2U) {
            resolver_hashes_before_failure.insert(
                invalid_project.assets.at(*pad.asset_id).artifact.sha256);
          }
          reached_invalid_asset = true;
          break;
        }
        resolver_hashes_before_failure.insert(
            invalid_project.assets.at(*pad.asset_id).artifact.sha256);
      }
      if (reached_invalid_asset) {
        break;
      }
    }
    const auto expected_calls = static_cast<std::uint32_t>(
        resolver_hashes_before_failure.size());

    ResolverTrace invalid_trace;
    const auto invalid = lmdj::cooker::cook(
        invalid_project,
        generated.pattern_id,
        resolver_for(fixtures, invalid_trace, resolver_mode));
    LMDJ_CHECK(!invalid.has_value());
    LMDJ_CHECK(invalid.error().code == expected_error);
    LMDJ_CHECK(invalid_trace.calls == expected_calls);
    LMDJ_CHECK(generated.state == immutable_project);
    ++evidence.rejected_partial_snapshots;
  });

  return evidence;
}

const MatrixEvidence& determinism_matrix_evidence() {
  static const MatrixEvidence evidence = run_determinism_matrix();
  return evidence;
}

void test_generated_projects_cook_to_identical_snapshots() {
  LMDJ_CHECK(
      determinism_matrix_evidence().deterministic_cooks == 256);
}

void test_generated_artifact_resolution_is_content_deduplicated() {
  LMDJ_CHECK(
      determinism_matrix_evidence().deduplicated_resolutions == 256);
}

void test_generated_invalid_artifacts_never_publish_partial_snapshot() {
  LMDJ_CHECK(
      determinism_matrix_evidence().rejected_partial_snapshots == 256);
}

void test_generated_slot_reassignment_resolves_current_asset() {
  LMDJ_CHECK(
      determinism_matrix_evidence().current_slot_resolutions == 256);
}

void test_generated_pad_playback_resolves_deterministically() {
  LMDJ_CHECK(
      determinism_matrix_evidence().resolved_playback_values == 256);
}

}  // namespace

int main() {
  try {
    test_generated_projects_cook_to_identical_snapshots();
    test_generated_artifact_resolution_is_content_deduplicated();
    test_generated_invalid_artifacts_never_publish_partial_snapshot();
    test_generated_slot_reassignment_resolves_current_asset();
    test_generated_pad_playback_resolves_deterministically();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "cooker determinism matrix tests: PASS\n";
  return 0;
}
