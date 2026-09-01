#include <chrono>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/cooker/wav_selection.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/project_io/project_store.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::Performance;
using lmdj::domain::PerformanceId;
using lmdj::domain::ProjectContract;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ProjectId;
using lmdj::project_io::ProjectStore;

constexpr auto kProjectId = "10000000-0000-4000-8000-000000000001";
constexpr auto kPerformanceId = "20000000-0000-4000-8000-000000000001";
constexpr auto kSecondPerformanceId =
    "20000000-0000-4000-8000-000000000002";
constexpr auto kCommandId = "30000000-0000-4000-8000-000000000001";
constexpr auto kBindCommandId = "40000000-0000-4000-8000-000000000001";
constexpr auto kSecondBindCommandId =
    "40000000-0000-4000-8000-000000000002";

class TempDirectory {
 public:
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-resample-performance-" +
             std::to_string(std::chrono::steady_clock::now()
                                .time_since_epoch()
                                .count()));
    std::filesystem::create_directories(path_);
  }
  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }
  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::vector<std::byte> read_bytes(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  LMDJ_CHECK(static_cast<bool>(input));
  const std::vector<char> chars{
      std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
  std::vector<std::byte> bytes;
  bytes.reserve(chars.size());
  for (const auto value : chars) {
    bytes.push_back(static_cast<std::byte>(static_cast<unsigned char>(value)));
  }
  return bytes;
}

using Inventory = std::map<std::string, std::vector<std::byte>>;

Inventory inventory(const std::filesystem::path& bundle) {
  Inventory result;
  for (const auto& item :
       std::filesystem::recursive_directory_iterator(bundle)) {
    if (item.is_regular_file()) {
      result.emplace(
          std::filesystem::relative(item.path(), bundle).generic_string(),
          read_bytes(item.path()));
    }
  }
  return result;
}

lmdj::domain::ProjectState project() {
  auto created = lmdj::domain::create_project(ProjectId{kProjectId}, 120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  state.contract = ProjectContract::v4;
  const PerformanceId id{kPerformanceId};
  state.performances.emplace(
      id, Performance{id, "Recorded", 120, 42, std::nullopt, {}});
  const PerformanceId second_id{kSecondPerformanceId};
  state.performances.emplace(
      second_id,
      Performance{second_id, "Recorded second", 120, 43, std::nullopt, {}});
  return state;
}

struct Fixture {
  std::filesystem::path bundle;
  ArtifactRef recording;
  std::vector<std::byte> source;
};

Fixture create_fixture(TempDirectory& temp, std::string_view name) {
  const auto bundle = temp.path() / (std::string{name} + ".lmdj");
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, project()).has_value());
  const auto source_path =
      std::filesystem::path{"tests/fixtures/audio/stereo.wav"};
  const auto source = read_bytes(source_path);
  const auto described =
      lmdj::foundation::describe_artifact(source_path, "audio/wav");
  LMDJ_CHECK(described.has_value());
  std::filesystem::copy_file(
      source_path,
      bundle / "assets" / (described.value().sha256 + ".wav"));
  const auto bound = store.bind_performance_recording(
      bundle,
      {CommandId{kBindCommandId}, 0},
      PerformanceId{kPerformanceId},
      described.value());
  LMDJ_CHECK(bound.has_value());
  LMDJ_CHECK(bound.value().committed_revision == 1);
  const auto second_bound = store.bind_performance_recording(
      bundle,
      {CommandId{kSecondBindCommandId}, 1},
      PerformanceId{kSecondPerformanceId},
      described.value());
  LMDJ_CHECK(second_bound.has_value());
  LMDJ_CHECK(second_bound.value().committed_revision == 2);
  return {bundle, described.value(), source};
}

Application make_application(
    const std::filesystem::path& root,
    lmdj::audio::RuntimePreparationLimits limits =
        {1'048'576, 240'000, 67'108'864, 134'217'728}) {
  return Application(ApplicationConfig{
      root,
      nullptr,
      {},
      {},
      limits,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  });
}

nlohmann::json request(
    const std::filesystem::path& bundle,
    std::uint64_t start = 1,
    std::uint64_t end = 3,
    std::uint32_t pad = 2) {
  return {
      {"operation", "performance.resample.commit"},
      {"project_path", bundle.generic_string()},
      {"command_id", kCommandId},
      {"expected_revision", 2},
      {"performance_id", kPerformanceId},
      {"source_start_frame", start},
      {"source_end_frame", end},
      {"target_slot", {{"bank", 1}, {"pad", pad}}},
  };
}

void check_result_shape(const nlohmann::json& response) {
  LMDJ_CHECK(response.at("ok") == true);
  const auto& result = response.at("result");
  LMDJ_CHECK(result.size() == 3);
  LMDJ_CHECK(result.contains("performance_id"));
  LMDJ_CHECK(result.contains("committed_revision"));
  LMDJ_CHECK(result.contains("runtime_prepare_required"));
}

void test_commit_persists_exact_selection_lineage_and_receipt() {
  TempDirectory temp;
  const auto fixture = create_fixture(temp, "commit");
  auto application = make_application(temp.path());
  const auto committed = application.command(request(fixture.bundle));
  check_result_shape(committed);
  LMDJ_CHECK(committed.at("project_revision") == 3);
  LMDJ_CHECK(committed.at("result").at("performance_id") == kPerformanceId);
  LMDJ_CHECK(committed.at("result").at("committed_revision") == 3);
  LMDJ_CHECK(committed.at("result").at("runtime_prepare_required") == true);

  ProjectStore store;
  const auto loaded = store.load(fixture.bundle);
  LMDJ_CHECK(loaded.has_value());
  const AssetId asset_id{kCommandId};
  const auto& assigned = loaded.value().banks.at(1).at(2);
  LMDJ_CHECK(assigned.asset_id == asset_id);
  const auto& asset = loaded.value().assets.at(asset_id);
  LMDJ_CHECK(asset.lineage.has_value());
  LMDJ_CHECK(asset.lineage->source.artifact_sha256 ==
             fixture.recording.sha256);
  LMDJ_CHECK(asset.lineage->source.project_revision == 42);
  LMDJ_CHECK(asset.lineage->derivation.performance_id ==
             PerformanceId{kPerformanceId});
  LMDJ_CHECK(asset.lineage->derivation.range.start_frame == 1);
  LMDJ_CHECK(asset.lineage->derivation.range.end_frame == 3);
  const auto stored = store.read_artifact(fixture.bundle, asset.artifact);
  const auto expected =
      lmdj::cooker::select_pcm16_stereo_wav(fixture.source, 1, 3);
  LMDJ_CHECK(stored.has_value());
  LMDJ_CHECK(expected.has_value());
  LMDJ_CHECK(stored.value() == expected.value());

  const auto before_retry = inventory(fixture.bundle);
  const auto replayed = application.command(request(fixture.bundle));
  check_result_shape(replayed);
  LMDJ_CHECK(replayed.at("result").at("committed_revision") == 3);
  LMDJ_CHECK(inventory(fixture.bundle) == before_retry);

  auto collision_request = request(fixture.bundle);
  collision_request["target_slot"] = {{"bank", 1}, {"pad", 3}};
  const auto collision = application.command(collision_request);
  LMDJ_CHECK(collision.at("ok") == false);
  LMDJ_CHECK(inventory(fixture.bundle) == before_retry);

  collision_request = request(fixture.bundle, 0, 2);
  const auto range_collision = application.command(collision_request);
  LMDJ_CHECK(range_collision.at("ok") == false);
  LMDJ_CHECK(inventory(fixture.bundle) == before_retry);

  collision_request = request(fixture.bundle);
  collision_request["performance_id"] = kSecondPerformanceId;
  const auto performance_and_lineage_collision =
      application.command(collision_request);
  LMDJ_CHECK(performance_and_lineage_collision.at("ok") == false);
  LMDJ_CHECK(inventory(fixture.bundle) == before_retry);
}

void test_rejections_leave_the_complete_far_side_unchanged() {
  TempDirectory temp;
  const auto fixture = create_fixture(temp, "rejections");
  auto application = make_application(temp.path());
  const auto before = inventory(fixture.bundle);

  const auto invalid_range = application.command(request(fixture.bundle, 3, 3));
  LMDJ_CHECK(invalid_range.at("ok") == false);
  LMDJ_CHECK(inventory(fixture.bundle) == before);

  const auto cancelled = application.command({
      {"operation", "performance.resample.cancel"},
      {"project_path", fixture.bundle.generic_string()},
  });
  LMDJ_CHECK(cancelled.at("ok") == false);
  LMDJ_CHECK(cancelled.at("error").at("message") == "operation is unknown");
  LMDJ_CHECK(inventory(fixture.bundle) == before);

  auto quota_application = make_application(
      temp.path() / "quota",
      {1'048'576, 4, 67'108'864, 134'217'728});
  const auto quota = quota_application.command(request(fixture.bundle));
  LMDJ_CHECK(quota.at("ok") == false);
  LMDJ_CHECK(quota.at("error").at("code") == "BANK_QUOTA_EXHAUSTED");
  const auto& details = quota.at("error").at("details");
  LMDJ_CHECK(details.at("bank") == 1);
  LMDJ_CHECK(details.at("requested_bytes") == 8);
  LMDJ_CHECK(details.at("requested_frames") == 2);
  LMDJ_CHECK(details.at("remaining_bytes") == 4);
  LMDJ_CHECK(details.at("remaining_frames") == 1);
  LMDJ_CHECK(details.at("quota_bytes") == 4);
  LMDJ_CHECK(details.at("consumed") == nlohmann::json::array());
  LMDJ_CHECK(inventory(fixture.bundle) == before);
}

void test_missing_and_mismatched_recording_are_non_destructive() {
  TempDirectory temp;
  const auto missing_bundle = temp.path() / "missing.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(missing_bundle, project()).has_value());
  auto missing_request = request(missing_bundle);
  missing_request["expected_revision"] = 0;
  auto application = make_application(temp.path());
  const auto before_missing = inventory(missing_bundle);
  const auto missing = application.command(missing_request);
  LMDJ_CHECK(missing.at("ok") == false);
  LMDJ_CHECK(missing.at("error").at("code") == "INVALID_ARGUMENT");
  LMDJ_CHECK(inventory(missing_bundle) == before_missing);

  const auto fixture = create_fixture(temp, "mismatched");
  const auto recording_path =
      fixture.bundle / "assets" / (fixture.recording.sha256 + ".wav");
  std::filesystem::resize_file(recording_path, 1);
  const auto before_mismatch = inventory(fixture.bundle);
  const auto mismatched = application.command(request(fixture.bundle));
  LMDJ_CHECK(mismatched.at("ok") == false);
  LMDJ_CHECK(mismatched.at("error").at("code") == "COOK_FAILED");
  LMDJ_CHECK(inventory(fixture.bundle) == before_mismatch);
}

}  // namespace

int main() {
  try {
    test_commit_persists_exact_selection_lineage_and_receipt();
    test_rejections_leave_the_complete_far_side_unchanged();
    test_missing_and_mismatched_recording_are_non_destructive();
    std::cout << "resample Performance tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
