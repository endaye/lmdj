#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <string>
#include <vector>

#include <lmdj/cooker/performance_replay.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::cooker::PerformanceReplayProjection;
using lmdj::domain::FxEngagePerformanceEvent;
using lmdj::domain::HoldOnPerformanceEvent;
using lmdj::domain::PadHitPerformanceEvent;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::PatternLaunchPerformanceEvent;
using lmdj::domain::Performance;
using lmdj::domain::PerformanceEvent;
using lmdj::domain::PerformanceFx;
using lmdj::domain::PerformanceId;
using lmdj::domain::ProjectContract;
using lmdj::domain::ProjectState;
using lmdj::domain::Asset;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";
constexpr auto kPerformanceId = "50000000-0000-4000-8000-000000000001";
constexpr auto kPatternA = "30000000-0000-4000-8000-000000000001";
constexpr auto kPatternB = "30000000-0000-4000-8000-000000000002";
constexpr auto kSyntheticCollision =
    "ffffffff-ffff-4fff-bfff-000000000000";
constexpr auto kAsset = "20000000-0000-4000-8000-000000000001";

std::vector<std::byte> fixture_bytes(const std::string& name) {
  const auto path = std::filesystem::path{"tests/fixtures/audio"} / name;
  std::ifstream input(path, std::ios::binary);
  LMDJ_CHECK(static_cast<bool>(input));
  const std::vector<char> characters{
      std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
  std::vector<std::byte> result;
  result.reserve(characters.size());
  for (const auto character : characters) {
    result.push_back(
        static_cast<std::byte>(static_cast<unsigned char>(character)));
  }
  return result;
}

ArtifactRef fixture_artifact(const std::string& name) {
  const auto described = lmdj::foundation::describe_artifact(
      std::filesystem::path{"tests/fixtures/audio"} / name,
      "audio/wav");
  LMDJ_CHECK(described.has_value());
  return described.value();
}

ProjectState replay_project(const ArtifactRef& artifact) {
  auto created = lmdj::domain::create_project(ProjectId{kProjectId}, 123);
  LMDJ_CHECK(created.has_value());
  auto project = created.value();
  project.contract = ProjectContract::v4;
  project.revision = 17;
  project.quantize_enabled = true;
  project.swing_percent = 58;
  project.assets.emplace(
      AssetId{kAsset},
      Asset{AssetId{kAsset}, artifact, std::nullopt});
  project.banks.at(2).at(3).asset_id = AssetId{kAsset};
  project.patterns.emplace(
      PatternId{kPatternA},
      Pattern{PatternId{kPatternA}, 1, {
          PatternEvent{{2, 3}, 0, 240, 100},
      }});
  project.patterns.emplace(
      PatternId{kPatternB},
      Pattern{PatternId{kPatternB}, 1, {
          PatternEvent{{2, 3}, 240, 240, 90},
      }});
  project.patterns.emplace(
      PatternId{kSyntheticCollision},
      Pattern{PatternId{kSyntheticCollision}, 1, {}});
  project.pattern_slots.at(1) = PatternId{kPatternA};
  project.pattern_slots.at(7) = PatternId{kPatternB};
  const std::vector<PerformanceEvent> events{
      PerformanceEvent{HoldOnPerformanceEvent{960}},
      PerformanceEvent{FxEngagePerformanceEvent{
          PerformanceFx::filter, 321, 960}},
      PerformanceEvent{PatternLaunchPerformanceEvent{7, 960}},
      PerformanceEvent{PadHitPerformanceEvent{35, 960, 120, 111}},
      PerformanceEvent{PatternLaunchPerformanceEvent{4, 1'200}},
  };
  project.performances.emplace(
      PerformanceId{kPerformanceId},
      Performance{
          PerformanceId{kPerformanceId},
          "Replay",
          123,
          project.revision,
          std::nullopt,
          lmdj::domain::canonical_performance_events(events),
      });
  return project;
}

void test_projection_is_fixed_to_the_cooked_revision() {
  const auto artifact = fixture_artifact("kick.wav");
  const auto bytes = fixture_bytes("kick.wav");
  auto project = replay_project(artifact);
  const auto resolver = [artifact, bytes](const ArtifactRef& requested) {
    LMDJ_CHECK(requested == artifact);
    return lmdj::foundation::Result<std::vector<std::byte>>::success(bytes);
  };

  const auto cooked = lmdj::cooker::cook_performance_replay(
      project, PerformanceId{kPerformanceId}, resolver);
  LMDJ_CHECK(cooked.has_value());
  const auto projection = cooked.value();
  LMDJ_CHECK(projection->performance_id == PerformanceId{kPerformanceId});
  LMDJ_CHECK(projection->resolved_revision == 17);
  LMDJ_CHECK(projection->bpm == 123);
  LMDJ_CHECK(projection->quantize_enabled);
  LMDJ_CHECK(projection->swing_percent == 58);
  LMDJ_CHECK(projection->pads.at(35).has_value());
  LMDJ_CHECK(projection->pads.at(35)->artifact == artifact);
  LMDJ_CHECK(projection->patterns.at(1) != nullptr);
  LMDJ_CHECK(projection->patterns.at(1)->pattern_id == PatternId{kPatternA});
  LMDJ_CHECK(projection->patterns.at(4) == nullptr);
  LMDJ_CHECK(projection->patterns.at(7) != nullptr);
  LMDJ_CHECK(projection->patterns.at(7)->pattern_id == PatternId{kPatternB});
  LMDJ_CHECK(projection->event_count == 5);
  LMDJ_CHECK(projection->boundaries.size() == 5);
  LMDJ_CHECK(projection->boundaries.front().offset_tick == 0);
  LMDJ_CHECK(projection->boundaries.back().offset_tick == 240);
  LMDJ_CHECK(
      projection->boundaries.front().event ==
      project.performances.at(PerformanceId{kPerformanceId}).events.front());

  project.revision = 18;
  project.bpm = 140;
  project.banks.at(2).at(3).asset_id.reset();
  project.pattern_slots.at(1).reset();
  project.pattern_slots.at(4) = PatternId{kPatternA};
  project.performances.erase(PerformanceId{kPerformanceId});

  LMDJ_CHECK(projection->resolved_revision == 17);
  LMDJ_CHECK(projection->bpm == 123);
  LMDJ_CHECK(projection->pads.at(35).has_value());
  LMDJ_CHECK(projection->patterns.at(1) != nullptr);
  LMDJ_CHECK(projection->patterns.at(4) == nullptr);
  LMDJ_CHECK(projection->boundaries.size() == 5);
}

void test_second_cook_reflects_new_truth_and_empty_performance_is_valid() {
  const auto artifact = fixture_artifact("kick.wav");
  const auto bytes = fixture_bytes("kick.wav");
  auto project = replay_project(artifact);
  project.revision = 18;
  project.pattern_slots.at(1).reset();
  project.pattern_slots.at(4) = PatternId{kPatternA};
  project.performances.at(PerformanceId{kPerformanceId}).events.clear();
  const auto resolver = [bytes](const ArtifactRef&) {
    return lmdj::foundation::Result<std::vector<std::byte>>::success(bytes);
  };

  const auto cooked = lmdj::cooker::cook_performance_replay(
      project, PerformanceId{kPerformanceId}, resolver);
  LMDJ_CHECK(cooked.has_value());
  LMDJ_CHECK(cooked.value()->resolved_revision == 18);
  LMDJ_CHECK(cooked.value()->patterns.at(1) == nullptr);
  LMDJ_CHECK(cooked.value()->patterns.at(4) != nullptr);
  LMDJ_CHECK(cooked.value()->boundaries.empty());
  LMDJ_CHECK(cooked.value()->event_count == 0);

  project.performances.erase(PerformanceId{kPerformanceId});
  const auto missing = lmdj::cooker::cook_performance_replay(
      project, PerformanceId{kPerformanceId}, resolver);
  LMDJ_CHECK(!missing.has_value());
  LMDJ_CHECK(missing.error().code == lmdj::foundation::ErrorCode::not_found);
}

void test_projection_rejects_invalid_identity_and_missing_resolver() {
  const auto artifact = fixture_artifact("kick.wav");
  auto project = replay_project(artifact);
  const auto no_resolver = lmdj::cooker::cook_performance_replay(
      project,
      PerformanceId{kPerformanceId},
      lmdj::cooker::ArtifactResolver{});
  LMDJ_CHECK(!no_resolver.has_value());
  LMDJ_CHECK(no_resolver.error().code ==
             lmdj::foundation::ErrorCode::invalid_argument);

  project.performances.at(PerformanceId{kPerformanceId}).id =
      PerformanceId{"50000000-0000-4000-8000-000000000002"};
  const auto mismatched = lmdj::cooker::cook_performance_replay(
      project,
      PerformanceId{kPerformanceId},
      [](const ArtifactRef&) {
        return lmdj::foundation::Result<std::vector<std::byte>>::failure(
            {lmdj::foundation::ErrorCode::internal_error, "unused"});
      });
  LMDJ_CHECK(!mismatched.has_value());
  LMDJ_CHECK(mismatched.error().code ==
             lmdj::foundation::ErrorCode::invalid_project);
}

}  // namespace

int main() {
  try {
    test_projection_is_fixed_to_the_cooked_revision();
    test_second_cook_reflects_new_truth_and_empty_performance_is_valid();
    test_projection_rejects_invalid_identity_and_missing_resolver();
    std::cout << "performance replay projection tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
