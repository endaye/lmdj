#include <array>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <limits>
#include <string>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>

#include <lmdj/cooker/project_cooker.hpp>
#include <lmdj/cooker/wav_reader.hpp>
#include <lmdj/domain/command_handler.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::cooker::ArtifactResolver;
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
using lmdj::domain::TriggerMode;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::ProjectState;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::Result;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";
constexpr auto kAssetKick = "20000000-0000-4000-8000-000000000001";
constexpr auto kAssetSnare = "20000000-0000-4000-8000-000000000002";
constexpr auto kPatternId = "30000000-0000-4000-8000-000000000001";
constexpr auto kMissingPatternId = "30000000-0000-4000-8000-000000000002";
constexpr auto kUnsupportedSha =
    "e1bfa728d85c1034701e9bf80c6bc99aa40dd8eb713c576b53ea4fd6aa5d9635";
constexpr auto kImportKick = "10000000-0000-4000-8000-000000000001";
constexpr auto kImportSnare = "10000000-0000-4000-8000-000000000002";
constexpr auto kAssignKick = "10000000-0000-4000-8000-000000000003";
constexpr auto kPatternCommand = "10000000-0000-4000-8000-000000000004";
constexpr auto kAssignSnare = "10000000-0000-4000-8000-000000000005";
constexpr auto kAssignKickDuplicate =
    "10000000-0000-4000-8000-000000000006";

using CookResult = decltype(lmdj::cooker::cook(
    std::declval<const ProjectState&>(),
    std::declval<PatternId>(),
    std::declval<ArtifactResolver>()));

using RuntimeSnapshotMemberTypes = decltype([] {
  auto [project_id, pattern_id, project_revision, bpm, bars, ppq,
        loop_length_ticks, pads,
        events] = RuntimeSnapshot{
      ProjectId{kProjectId}, PatternId{kPatternId}, 0, 0, 0, 0, 0, {}, {}};
  return std::tuple{
      std::type_identity<decltype(project_id)>{},
      std::type_identity<decltype(pattern_id)>{},
      std::type_identity<decltype(project_revision)>{},
      std::type_identity<decltype(bpm)>{},
      std::type_identity<decltype(bars)>{},
      std::type_identity<decltype(ppq)>{},
      std::type_identity<decltype(loop_length_ticks)>{},
      std::type_identity<decltype(pads)>{},
      std::type_identity<decltype(events)>{},
  };
}());

using ResolvedPlaybackMemberTypes = decltype([] {
  [[maybe_unused]] auto [start_frame, end_frame, trigger_mode, linear_gain, muted] =
      ResolvedPlayback{0, 1, TriggerMode::one_shot, 1.0F, false};
  return std::tuple{
      std::type_identity<decltype(start_frame)>{},
      std::type_identity<decltype(end_frame)>{},
      std::type_identity<decltype(trigger_mode)>{},
      std::type_identity<decltype(linear_gain)>{},
      std::type_identity<decltype(muted)>{},
  };
}());

static_assert(std::is_aggregate_v<RuntimeSnapshot>);
static_assert(std::is_aggregate_v<ResolvedPlayback>);
static_assert(std::is_same_v<
              CookResult,
              Result<std::shared_ptr<const RuntimeSnapshot>>>);
static_assert(std::is_same_v<
              decltype(ResolvedEvent::sample),
              std::shared_ptr<const PcmSample>>);
static_assert(std::is_same_v<
              decltype(ResolvedPad::sample),
              std::shared_ptr<const PcmSample>>);
static_assert(std::is_same_v<
              RuntimeSnapshotMemberTypes,
              std::tuple<
                  std::type_identity<ProjectId>,
                  std::type_identity<PatternId>,
                  std::type_identity<std::uint64_t>,
                  std::type_identity<std::uint16_t>,
                  std::type_identity<std::uint8_t>,
                  std::type_identity<std::uint32_t>,
                  std::type_identity<std::uint32_t>,
                  std::type_identity<std::vector<ResolvedPad>>,
                  std::type_identity<std::vector<ResolvedEvent>>>>);
static_assert(std::is_same_v<
              ResolvedPlaybackMemberTypes,
              std::tuple<
                  std::type_identity<std::uint32_t>,
                  std::type_identity<std::uint32_t>,
                  std::type_identity<TriggerMode>,
                  std::type_identity<float>,
                  std::type_identity<bool>>>);

std::vector<std::byte> fixture_bytes(const std::string& name) {
  const auto path = std::filesystem::path{"tests/fixtures/audio"} / name;
  std::ifstream input(path, std::ios::binary);
  LMDJ_CHECK(static_cast<bool>(input));
  const std::vector<char> characters{
      std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
  std::vector<std::byte> bytes;
  bytes.reserve(characters.size());
  for (const char character : characters) {
    bytes.push_back(static_cast<std::byte>(static_cast<unsigned char>(character)));
  }
  return bytes;
}

ArtifactRef fixture_artifact(const std::string& name) {
  const auto path = std::filesystem::path{"tests/fixtures/audio"} / name;
  const auto artifact = lmdj::foundation::describe_artifact(path, "audio/wav");
  LMDJ_CHECK(artifact.has_value());
  return artifact.value();
}

void write_little_endian_u32(
    std::vector<std::byte>& bytes,
    std::size_t offset,
    std::uint32_t value) {
  for (std::size_t index = 0; index < 4; ++index) {
    bytes.at(offset + index) = static_cast<std::byte>(value >> (index * 8));
  }
}

void update_riff_size(std::vector<std::byte>& bytes) {
  LMDJ_CHECK(bytes.size() >= 8);
  write_little_endian_u32(
      bytes, 4, static_cast<std::uint32_t>(bytes.size() - 8));
}

std::vector<std::byte> truncated_riff(
    const std::vector<std::byte>& valid,
    std::size_t size) {
  auto result = valid;
  result.resize(size);
  if (result.size() >= 8) {
    update_riff_size(result);
  }
  return result;
}

void append_chunk(
    std::vector<std::byte>& bytes,
    const std::array<char, 4>& type,
    const std::vector<std::byte>& payload,
    bool add_padding) {
  for (const char character : type) {
    bytes.push_back(static_cast<std::byte>(static_cast<unsigned char>(character)));
  }
  const auto payload_size = static_cast<std::uint32_t>(payload.size());
  for (std::size_t index = 0; index < 4; ++index) {
    bytes.push_back(static_cast<std::byte>(payload_size >> (index * 8)));
  }
  bytes.insert(bytes.end(), payload.begin(), payload.end());
  if (add_padding && (payload.size() & 1U) != 0U) {
    bytes.push_back(std::byte{0});
  }
}

ProjectState new_project() {
  const auto project = lmdj::domain::create_project(ProjectId{kProjectId}, 120);
  LMDJ_CHECK(project.has_value());
  return project.value();
}

CommandMeta meta(const char* id, std::uint64_t revision) {
  return CommandMeta{CommandId{id}, revision};
}

ProjectState apply_or_throw(const ProjectState& project, const Command& command) {
  const auto applied = lmdj::domain::apply(project, command, {});
  LMDJ_CHECK(applied.has_value());
  return applied.value().state;
}

ProjectState project_with_pattern(
    const ArtifactRef& artifact,
    std::vector<PatternEvent> events = {
        {PadSlotId{0, 0}, 0, 240, 100}}) {
  auto project = new_project();
  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(kImportKick, project.revision),
          {AssetId{kAssetKick}, artifact},
      }});
  project = apply_or_throw(
      project,
      Command{AssignPad{
          meta(kAssignKick, project.revision), PadSlotId{0, 0}, AssetId{kAssetKick},
      }});
  project = apply_or_throw(
      project,
      Command{CreatePattern{
          meta(kPatternCommand, project.revision),
          {PatternId{kPatternId}, 1, std::move(events)},
      }});
  return project;
}

ArtifactResolver resolver_for(
    std::map<std::string, std::vector<std::byte>> bytes_by_sha,
    std::uint32_t* resolve_count = nullptr) {
  return [bytes_by_sha = std::move(bytes_by_sha), resolve_count](
             const ArtifactRef& artifact) -> Result<std::vector<std::byte>> {
    if (resolve_count != nullptr) {
      ++*resolve_count;
    }
    const auto bytes = bytes_by_sha.find(artifact.sha256);
    if (bytes == bytes_by_sha.end()) {
      return Result<std::vector<std::byte>>::failure(
          Error{ErrorCode::not_found, "fixture artifact is unavailable"});
    }
    return Result<std::vector<std::byte>>::success(bytes->second);
  };
}

void test_mono_pcm16_fixtures_decode_correctly() {
  const auto kick = lmdj::cooker::decode_wav(fixture_bytes("kick.wav"));
  const auto snare = lmdj::cooker::decode_wav(fixture_bytes("snare.wav"));

  LMDJ_CHECK(kick.has_value());
  LMDJ_CHECK(snare.has_value());
  LMDJ_CHECK(kick.value()->sample_rate == 48'000);
  LMDJ_CHECK(kick.value()->channels == 1);
  LMDJ_CHECK(kick.value()->interleaved.size() == 4'800);
  LMDJ_CHECK(kick.value()->interleaved.at(0) == 0);
  LMDJ_CHECK(kick.value()->interleaved.at(1) == 236);
  LMDJ_CHECK(snare.value()->sample_rate == 48'000);
  LMDJ_CHECK(snare.value()->channels == 1);
  LMDJ_CHECK(snare.value()->interleaved.size() == 2'400);
  LMDJ_CHECK(snare.value()->interleaved.at(0) == 18'207);
  LMDJ_CHECK(snare.value()->interleaved.at(1) == -29'659);
}

void test_stereo_pcm16_fixture_preserves_interleave() {
  const auto decoded = lmdj::cooker::decode_wav(fixture_bytes("stereo.wav"));

  LMDJ_CHECK(decoded.has_value());
  LMDJ_CHECK(decoded.value()->sample_rate == 48'000);
  LMDJ_CHECK(decoded.value()->channels == 2);
  LMDJ_CHECK((decoded.value()->interleaved ==
             std::vector<std::int16_t>{
                 32'767, -32'768, -32'768, 32'767,
                 123, -789, -456, 1'011,
             }));
}

void test_unsupported_sample_rate_and_bit_depth_return_unsupported_audio() {
  auto wrong_rate = fixture_bytes("kick.wav");
  wrong_rate.at(24) = std::byte{0x44};
  wrong_rate.at(25) = std::byte{0xac};
  wrong_rate.at(26) = std::byte{0x00};
  wrong_rate.at(27) = std::byte{0x00};
  const auto rate_result = lmdj::cooker::decode_wav(wrong_rate);

  auto wrong_depth = fixture_bytes("kick.wav");
  wrong_depth.at(34) = std::byte{0x08};
  wrong_depth.at(35) = std::byte{0x00};
  const auto depth_result = lmdj::cooker::decode_wav(wrong_depth);

  LMDJ_CHECK(!rate_result.has_value());
  LMDJ_CHECK(rate_result.error().code == ErrorCode::unsupported_audio);
  LMDJ_CHECK(!depth_result.has_value());
  LMDJ_CHECK(depth_result.error().code == ErrorCode::unsupported_audio);
}

void test_malformed_wav_layouts_return_unsupported_audio() {
  const auto valid = fixture_bytes("kick.wav");

  auto chunk_size_exceeds_body = valid;
  write_little_endian_u32(
      chunk_size_exceeds_body,
      40,
      static_cast<std::uint32_t>(chunk_size_exceeds_body.size() - 43));

  auto trailing_partial_header = valid;
  trailing_partial_header.push_back(std::byte{0});
  update_riff_size(trailing_partial_header);

  auto odd_chunk_without_padding = valid;
  append_chunk(
      odd_chunk_without_padding,
      {'J', 'U', 'N', 'K'},
      {std::byte{0}},
      false);
  update_riff_size(odd_chunk_without_padding);

  auto duplicate_fmt = valid;
  duplicate_fmt.insert(
      duplicate_fmt.begin() + 36,
      valid.begin() + 12,
      valid.begin() + 36);
  update_riff_size(duplicate_fmt);

  auto duplicate_data = valid;
  append_chunk(
      duplicate_data,
      {'d', 'a', 't', 'a'},
      {std::byte{0}, std::byte{0}},
      true);
  update_riff_size(duplicate_data);

  const std::vector<std::pair<std::string, std::vector<std::byte>>> cases{
      {"truncated RIFF header", truncated_riff(valid, 11)},
      {"truncated chunk header", truncated_riff(valid, 19)},
      {"truncated chunk body", truncated_riff(valid, 35)},
      {"chunk size exceeds body", std::move(chunk_size_exceeds_body)},
      {"trailing partial chunk header", std::move(trailing_partial_header)},
      {"odd chunk without padding", std::move(odd_chunk_without_padding)},
      {"duplicate fmt chunk", std::move(duplicate_fmt)},
      {"duplicate data chunk", std::move(duplicate_data)},
  };

  for (const auto& malformed : cases) {
    const auto result = lmdj::cooker::decode_wav(malformed.second);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::unsupported_audio);
  }
}

void test_cooker_resolves_events_through_current_pad_slot() {
  const auto kick = fixture_artifact("kick.wav");
  const auto snare = fixture_artifact("snare.wav");
  auto project = project_with_pattern(kick);
  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(kImportSnare, project.revision),
          {AssetId{kAssetSnare}, snare},
      }});
  project = apply_or_throw(
      project,
      Command{AssignPad{
          meta(kAssignSnare, project.revision), PadSlotId{0, 0}, AssetId{kAssetSnare},
      }});

  const auto result = lmdj::cooker::cook(
      project,
      PatternId{kPatternId},
      resolver_for({
          {kick.sha256, fixture_bytes("kick.wav")},
          {snare.sha256, fixture_bytes("snare.wav")},
      }));

  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value()->project_id == ProjectId{kProjectId});
  LMDJ_CHECK(result.value()->project_revision == project.revision);
  LMDJ_CHECK(result.value()->bpm == 120);
  LMDJ_CHECK(result.value()->bars == 1);
  LMDJ_CHECK(result.value()->events.size() == 1);
  LMDJ_CHECK((result.value()->events.at(0).slot == PadSlotId{0, 0}));
  LMDJ_CHECK(result.value()->events.at(0).onset_tick == 0);
  LMDJ_CHECK(result.value()->events.at(0).duration_tick == 240);
  LMDJ_CHECK(result.value()->events.at(0).velocity == 100);
  LMDJ_CHECK(result.value()->events.at(0).sample->interleaved.size() == 2'400);
}

void test_cooker_resolves_every_assigned_pad_in_global_slot_order() {
  const auto kick = fixture_artifact("kick.wav");
  const auto stereo = fixture_artifact("stereo.wav");
  auto project = project_with_pattern(kick);
  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(kImportSnare, project.revision),
          {AssetId{kAssetSnare}, stereo},
      }});
  project = apply_or_throw(
      project,
      Command{AssignPad{
          meta(kAssignSnare, project.revision),
          PadSlotId{1, 2},
          AssetId{kAssetSnare},
      }});
  project = apply_or_throw(
      project,
      Command{AssignPad{
          meta(kAssignKickDuplicate, project.revision),
          PadSlotId{3, 15},
          AssetId{kAssetKick},
      }});
  std::uint32_t resolve_count = 0;

  const auto result = lmdj::cooker::cook(
      project,
      PatternId{kPatternId},
      resolver_for(
          {
              {kick.sha256, fixture_bytes("kick.wav")},
              {stereo.sha256, fixture_bytes("stereo.wav")},
          },
          &resolve_count));

  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value()->pads.size() == 3);
  LMDJ_CHECK((result.value()->pads.at(0).slot == PadSlotId{0, 0}));
  LMDJ_CHECK((result.value()->pads.at(1).slot == PadSlotId{1, 2}));
  LMDJ_CHECK((result.value()->pads.at(2).slot == PadSlotId{3, 15}));
  LMDJ_CHECK(result.value()->pads.at(0).artifact.sha256 == kick.sha256);
  LMDJ_CHECK(result.value()->pads.at(1).artifact.sha256 == stereo.sha256);
  LMDJ_CHECK(
      result.value()->pads.at(0).sample ==
      result.value()->pads.at(2).sample);
  LMDJ_CHECK(
      result.value()->events.at(0).sample ==
      result.value()->pads.at(0).sample);
  LMDJ_CHECK(resolve_count == 2);
}

void test_cooker_rejects_invalid_unused_assigned_pad_artifacts() {
  const auto kick = fixture_artifact("kick.wav");
  const auto stereo = fixture_artifact("stereo.wav");
  auto project = project_with_pattern(kick);
  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(kImportSnare, project.revision),
          {AssetId{kAssetSnare}, stereo},
      }});
  project = apply_or_throw(
      project,
      Command{AssignPad{
          meta(kAssignSnare, project.revision),
          PadSlotId{3, 15},
          AssetId{kAssetSnare},
      }});

  const auto missing = lmdj::cooker::cook(
      project,
      PatternId{kPatternId},
      resolver_for({{kick.sha256, fixture_bytes("kick.wav")}}));

  auto corrupt_project = project;
  corrupt_project.assets.at(AssetId{kAssetSnare}).artifact.byte_length += 1;
  const auto corrupt = lmdj::cooker::cook(
      corrupt_project,
      PatternId{kPatternId},
      resolver_for({
          {kick.sha256, fixture_bytes("kick.wav")},
          {stereo.sha256, fixture_bytes("stereo.wav")},
      }));

  auto unsupported_project = project;
  unsupported_project.assets.at(AssetId{kAssetSnare}).artifact = ArtifactRef{
      kUnsupportedSha, "audio/wav", 4};
  const auto unsupported = lmdj::cooker::cook(
      unsupported_project,
      PatternId{kPatternId},
      resolver_for({
          {kick.sha256, fixture_bytes("kick.wav")},
          {kUnsupportedSha,
           {std::byte{'B'}, std::byte{'A'}, std::byte{'D'}, std::byte{'!'}}},
      }));

  LMDJ_CHECK(!missing.has_value());
  LMDJ_CHECK(missing.error().code == ErrorCode::not_found);
  LMDJ_CHECK(!corrupt.has_value());
  LMDJ_CHECK(corrupt.error().code == ErrorCode::cook_failed);
  LMDJ_CHECK(!unsupported.has_value());
  LMDJ_CHECK(unsupported.error().code == ErrorCode::unsupported_audio);
}

void test_cooker_rejects_unassigned_slot() {
  auto project = new_project();
  project = apply_or_throw(
      project,
      Command{CreatePattern{
          meta(kPatternCommand, project.revision),
          {PatternId{kPatternId}, 1, {{PadSlotId{0, 1}, 0, 240, 100}}},
      }});
  const auto result = lmdj::cooker::cook(
      project, PatternId{kPatternId}, resolver_for({}));

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::missing_asset);
}

void test_cooker_rejects_missing_pattern() {
  const auto project = new_project();
  const auto result = lmdj::cooker::cook(
      project, PatternId{kMissingPatternId}, resolver_for({}));

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::not_found);
}

void test_cooker_rejects_artifact_byte_length_or_hash_mismatch() {
  auto artifact = fixture_artifact("kick.wav");
  artifact.byte_length += 1;
  const auto length_result = lmdj::cooker::cook(
      project_with_pattern(artifact),
      PatternId{kPatternId},
      resolver_for({{artifact.sha256, fixture_bytes("kick.wav")}}));

  artifact = fixture_artifact("kick.wav");
  artifact.sha256 = std::string(64, 'a');
  const auto hash_result = lmdj::cooker::cook(
      project_with_pattern(artifact),
      PatternId{kPatternId},
      resolver_for({{artifact.sha256, fixture_bytes("kick.wav")}}));

  LMDJ_CHECK(!length_result.has_value());
  LMDJ_CHECK(length_result.error().code == ErrorCode::cook_failed);
  LMDJ_CHECK(!hash_result.has_value());
  LMDJ_CHECK(hash_result.error().code == ErrorCode::cook_failed);
}

void test_cooker_rejects_cached_artifact_with_later_wrong_length() {
  const auto correct_artifact = fixture_artifact("kick.wav");
  auto wrong_length_artifact = correct_artifact;
  ++wrong_length_artifact.byte_length;
  auto project = new_project();
  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(kImportKick, project.revision),
          {AssetId{kAssetKick}, correct_artifact},
      }});
  project = apply_or_throw(
      project,
      Command{ImportAsset{
          meta(kImportSnare, project.revision),
          {AssetId{kAssetSnare}, wrong_length_artifact},
      }});
  project = apply_or_throw(
      project,
      Command{AssignPad{
          meta(kAssignKick, project.revision), PadSlotId{0, 0}, AssetId{kAssetKick},
      }});
  project = apply_or_throw(
      project,
      Command{AssignPad{
          meta(kAssignSnare, project.revision), PadSlotId{0, 1}, AssetId{kAssetSnare},
      }});
  project = apply_or_throw(
      project,
      Command{CreatePattern{
          meta(kPatternCommand, project.revision),
          {
              PatternId{kPatternId},
              1,
              {
                  {PadSlotId{0, 0}, 0, 240, 100},
                  {PadSlotId{0, 1}, 960, 240, 96},
              },
          },
      }});
  std::uint32_t resolve_count = 0;
  const auto result = lmdj::cooker::cook(
      project,
      PatternId{kPatternId},
      resolver_for(
          {{correct_artifact.sha256, fixture_bytes("kick.wav")}},
          &resolve_count));

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::cook_failed);
  LMDJ_CHECK(resolve_count == 1);
}

void test_cooker_decodes_each_unique_artifact_once() {
  const auto artifact = fixture_artifact("kick.wav");
  const auto project = project_with_pattern(
      artifact,
      {
          {PadSlotId{0, 0}, 0, 240, 100},
          {PadSlotId{0, 0}, 960, 240, 96},
      });
  std::uint32_t resolve_count = 0;
  const auto result = lmdj::cooker::cook(
      project,
      PatternId{kPatternId},
      resolver_for(
          {{artifact.sha256, fixture_bytes("kick.wav")}}, &resolve_count));

  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(resolve_count == 1);
  LMDJ_CHECK(result.value()->events.size() == 2);
  LMDJ_CHECK(result.value()->events.at(0).sample == result.value()->events.at(1).sample);
}

void test_cooker_prepares_44100_pcm_and_resolves_complete_playback() {
  const auto artifact = fixture_artifact("mono-44100.wav");
  auto project = project_with_pattern(artifact);
  project.banks.at(0).at(0).playback = {
      1,
      7,
      TriggerMode::loop_gate,
      -6'000,
      true,
  };

  const auto result = lmdj::cooker::cook(
      project,
      PatternId{kPatternId},
      resolver_for({
          {artifact.sha256, fixture_bytes("mono-44100.wav")},
      }));

  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value()->pads.size() == 1);
  const auto& pad = result.value()->pads.at(0);
  LMDJ_CHECK(pad.sample->sample_rate == 48'000);
  LMDJ_CHECK(pad.sample->channels == 1);
  LMDJ_CHECK(pad.sample->interleaved.size() == 9);
  LMDJ_CHECK(pad.playback.start_frame == 1);
  LMDJ_CHECK(pad.playback.end_frame == 8);
  LMDJ_CHECK(pad.playback.trigger_mode == TriggerMode::loop_gate);
  constexpr auto expected_gain = 0x1.009b9cp-1F;
  LMDJ_CHECK(std::abs(pad.playback.linear_gain - expected_gain) < 0.000'001F);
  LMDJ_CHECK(pad.playback.muted);
  LMDJ_CHECK(result.value()->events.at(0).sample == pad.sample);
}

void test_cooker_resolves_default_playback_over_the_full_prepared_source() {
  const auto artifact = fixture_artifact("mono-44100.wav");
  const auto result = lmdj::cooker::cook(
      project_with_pattern(artifact),
      PatternId{kPatternId},
      resolver_for({
          {artifact.sha256, fixture_bytes("mono-44100.wav")},
      }));

  LMDJ_CHECK(result.has_value());
  const auto& playback = result.value()->pads.at(0).playback;
  LMDJ_CHECK(playback.start_frame == 0);
  LMDJ_CHECK(playback.end_frame == 9);
  LMDJ_CHECK(playback.trigger_mode == TriggerMode::one_shot);
  LMDJ_CHECK(playback.linear_gain == 1.0F);
  LMDJ_CHECK(!playback.muted);
}

void test_cooker_rejects_invalid_trim_gain_and_trigger_values() {
  const auto artifact = fixture_artifact("mono-44100.wav");
  const auto bytes = fixture_bytes("mono-44100.wav");
  auto empty_trim = project_with_pattern(artifact);
  empty_trim.banks.at(0).at(0).playback.trim_start_frame = 4;
  empty_trim.banks.at(0).at(0).playback.trim_end_frame = 4;
  auto oversized_trim = project_with_pattern(artifact);
  oversized_trim.banks.at(0).at(0).playback.trim_end_frame = 9;
  auto non_finite_gain = project_with_pattern(artifact);
  non_finite_gain.banks.at(0).at(0).playback.gain_millidb =
      std::numeric_limits<std::int32_t>::max();
  auto gain_below_domain = project_with_pattern(artifact);
  gain_below_domain.banks.at(0).at(0).playback.gain_millidb = -60'001;
  auto gain_above_domain = project_with_pattern(artifact);
  gain_above_domain.banks.at(0).at(0).playback.gain_millidb = 6'001;
  auto invalid_mode = project_with_pattern(artifact);
  invalid_mode.banks.at(0).at(0).playback.trigger_mode =
      static_cast<TriggerMode>(255);

  for (const auto* project : {
           &empty_trim,
           &oversized_trim,
           &non_finite_gain,
           &gain_below_domain,
           &gain_above_domain,
           &invalid_mode,
       }) {
    const auto result = lmdj::cooker::cook(
        *project,
        PatternId{kPatternId},
        resolver_for({{artifact.sha256, bytes}}));
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
  }
}

void test_cooker_rejects_invalid_tick_and_duration_bounds() {
  const auto artifact = fixture_artifact("stereo.wav");
  auto onset_at_loop_end = project_with_pattern(artifact);
  onset_at_loop_end.patterns.at(PatternId{kPatternId})
      .events.front().onset_tick = lmdj::domain::kBarTicks4x4;
  auto zero_duration = project_with_pattern(artifact);
  zero_duration.patterns.at(PatternId{kPatternId})
      .events.front().duration_tick = 0;
  auto duration_past_loop = project_with_pattern(artifact);
  auto& past_loop = duration_past_loop.patterns.at(PatternId{kPatternId})
                        .events.front();
  past_loop.onset_tick = lmdj::domain::kBarTicks4x4 - 1;
  past_loop.duration_tick = 2;

  for (const auto* project : {
           &onset_at_loop_end,
           &zero_duration,
           &duration_past_loop,
       }) {
    const auto result = lmdj::cooker::cook(
        *project,
        PatternId{kPatternId},
        resolver_for({{artifact.sha256, fixture_bytes("stereo.wav")}}));
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_project);
  }
}

void test_cooker_returns_immutable_deterministic_snapshot_values() {
  const auto artifact = fixture_artifact("stereo.wav");
  const auto project = project_with_pattern(artifact);
  const auto first = lmdj::cooker::cook(
      project,
      PatternId{kPatternId},
      resolver_for({{artifact.sha256, fixture_bytes("stereo.wav")}}));
  const auto second = lmdj::cooker::cook(
      project,
      PatternId{kPatternId},
      resolver_for({{artifact.sha256, fixture_bytes("stereo.wav")}}));

  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(second.has_value());
  static_assert(std::is_const_v<std::remove_reference_t<decltype(*first.value())>>);
  LMDJ_CHECK(first.value()->project_id == second.value()->project_id);
  LMDJ_CHECK(first.value()->pattern_id == second.value()->pattern_id);
  LMDJ_CHECK(first.value()->project_revision == second.value()->project_revision);
  LMDJ_CHECK(first.value()->bpm == second.value()->bpm);
  LMDJ_CHECK(first.value()->bars == second.value()->bars);
  LMDJ_CHECK(first.value()->ppq == lmdj::domain::kPpq);
  LMDJ_CHECK(first.value()->loop_length_ticks ==
             lmdj::domain::kBarTicks4x4);
  LMDJ_CHECK(first.value()->pads.size() == second.value()->pads.size());
  LMDJ_CHECK(first.value()->pads.at(0).slot == second.value()->pads.at(0).slot);
  LMDJ_CHECK(
      first.value()->pads.at(0).artifact ==
      second.value()->pads.at(0).artifact);
  LMDJ_CHECK(
      first.value()->pads.at(0).sample->interleaved ==
      second.value()->pads.at(0).sample->interleaved);
  LMDJ_CHECK(first.value()->events.size() == second.value()->events.size());
  LMDJ_CHECK(first.value()->events.at(0).slot == second.value()->events.at(0).slot);
  LMDJ_CHECK(first.value()->events.at(0).onset_tick ==
             second.value()->events.at(0).onset_tick);
  LMDJ_CHECK(first.value()->events.at(0).duration_tick ==
             second.value()->events.at(0).duration_tick);
  LMDJ_CHECK(first.value()->events.at(0).velocity == second.value()->events.at(0).velocity);
  LMDJ_CHECK(first.value()->events.at(0).sample->interleaved ==
             second.value()->events.at(0).sample->interleaved);
}

}  // namespace

int main() {
  try {
    test_mono_pcm16_fixtures_decode_correctly();
    test_stereo_pcm16_fixture_preserves_interleave();
    test_unsupported_sample_rate_and_bit_depth_return_unsupported_audio();
    test_malformed_wav_layouts_return_unsupported_audio();
    test_cooker_resolves_events_through_current_pad_slot();
    test_cooker_resolves_every_assigned_pad_in_global_slot_order();
    test_cooker_rejects_invalid_unused_assigned_pad_artifacts();
    test_cooker_rejects_unassigned_slot();
    test_cooker_rejects_missing_pattern();
    test_cooker_rejects_artifact_byte_length_or_hash_mismatch();
    test_cooker_rejects_cached_artifact_with_later_wrong_length();
    test_cooker_decodes_each_unique_artifact_once();
    test_cooker_prepares_44100_pcm_and_resolves_complete_playback();
    test_cooker_resolves_default_playback_over_the_full_prepared_source();
    test_cooker_rejects_invalid_trim_gain_and_trigger_values();
    test_cooker_rejects_invalid_tick_and_duration_bounds();
    test_cooker_returns_immutable_deterministic_snapshot_values();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project cooker tests: PASS\n";
  return 0;
}
