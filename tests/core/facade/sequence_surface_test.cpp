#include <chrono>
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include <lmdj/facade/application.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::CommandMeta;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::facade::ArtifactBytesImportRequest;
using lmdj::facade::InitialProjectRequest;
using lmdj::facade::SequenceRecordState;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-sequence-surface-" + std::to_string(nonce));
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

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') +
         tail;
}

std::vector<std::byte> read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary | std::ios::ate);
  LMDJ_CHECK(static_cast<bool>(stream));
  const auto size = stream.tellg();
  LMDJ_CHECK(size >= 0);
  std::vector<std::byte> result(static_cast<std::size_t>(size));
  stream.seekg(0);
  stream.read(reinterpret_cast<char*>(result.data()), size);
  LMDJ_CHECK(static_cast<bool>(stream));
  return result;
}

ApplicationConfig config(const std::filesystem::path& root) {
  return ApplicationConfig{
      root,
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
  };
}

void create_recordable_project(
    Application& application,
    const std::filesystem::path& project,
    const PatternId& pattern_id) {
  const auto created = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{uuid(1)},
          120,
          Pattern{pattern_id, 1, {}},
      });
  LMDJ_CHECK(created.has_value());
  const auto imported = application.import_artifact_bytes(
      ArtifactBytesImportRequest{
          project,
          CommandMeta{CommandId{uuid(10)}, 0},
          AssetId{uuid(11)},
          "audio/wav",
          read_bytes("tests/fixtures/audio/kick.wav"),
      });
  LMDJ_CHECK(imported.has_value());
  const auto assigned = application.command({
      {"operation", "pad.assign"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(12)},
      {"expected_revision", 1},
      {"slot", {{"bank", 0}, {"pad", 0}}},
      {"asset_id", uuid(11)},
  });
  LMDJ_CHECK(assigned.value("ok", false));
  LMDJ_CHECK(assigned.at("project_revision") == 2);
}

void test_sequence_lifecycle_idempotence_and_mutation_exclusion() {
  TempDirectory temp;
  const auto project = temp.path() / "lifecycle.lmdj";
  const PatternId pattern_id{uuid(20)};
  const SequenceSessionId session_id{uuid(21)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);

  const auto begun = application.begin_sequence(
      {project, session_id, pattern_id, 2, 0});
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().status.state == SequenceRecordState::active);
  LMDJ_CHECK(application.query_sequence_status({project}).value() ==
             begun.value().status);

  const auto blocked = application.command({
      {"operation", "pad.assign"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(22)},
      {"expected_revision", 2},
      {"slot", {{"bank", 0}, {"pad", 0}}},
      {"asset_id", nullptr},
  });
  LMDJ_CHECK(!blocked.at("ok").get<bool>());
  LMDJ_CHECK(
      blocked.at("error").at("details").at("reason") ==
      "sequence_session_active");

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
                 .has_value());
  const lmdj::facade::SequenceFlushRequest flush{
      project, session_id, CommandId{uuid(23)}, 12'000};
  const auto committed = application.flush_sequence(flush);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().committed_revision == 3);
  const auto replayed = application.flush_sequence(flush);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);

  const auto stopped = application.stop_sequence(
      {project, session_id, CommandId{uuid(24)}, 12'001});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().status.state == SequenceRecordState::inactive);
  LMDJ_CHECK(!std::filesystem::exists(
      project / "recovery/active/sequence.jsonl"));

  Application restarted(config(temp.path()));
  const auto cross_host_replay = restarted.flush_sequence(flush);
  LMDJ_CHECK(cross_host_replay.has_value());
  LMDJ_CHECK(cross_host_replay.value().replayed);
  LMDJ_CHECK(cross_host_replay.value().committed_revision == 3);
  LMDJ_CHECK(
      cross_host_replay.value().status.state == SequenceRecordState::inactive);
}

void test_owner_loss_apply_and_discard_are_explicit() {
  TempDirectory temp;
  const auto project = temp.path() / "recovery.lmdj";
  const PatternId pattern_id{uuid(30)};
  const SequenceSessionId first{uuid(31)};
  {
    Application owner(config(temp.path()));
    create_recordable_project(owner, project, pattern_id);
    LMDJ_CHECK(owner.begin_sequence({project, first, pattern_id, 2, 0})
                   .has_value());
    LMDJ_CHECK(owner.record_sequence_event(
        {project, first, {PadSlotId{0, 0}, 90, 0, 1, true}})
                   .has_value());
  }

  Application recovery(config(temp.path()));
  const auto candidates = recovery.list_sequence_recovery({project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().event_count == 1);
  const auto applied = recovery.apply_sequence_recovery(
      {project, first, std::nullopt});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(applied.value().committed_revision == 3);
  LMDJ_CHECK(recovery.list_sequence_recovery({project}).value().empty());

  const SequenceSessionId second{uuid(32)};
  {
    Application owner(config(temp.path()));
    LMDJ_CHECK(owner.begin_sequence({project, second, pattern_id, 3, 0})
                   .has_value());
    LMDJ_CHECK(owner.record_sequence_event(
        {project, second, {PadSlotId{0, 0}, 70, 0, 1, true}})
                   .has_value());
  }
  LMDJ_CHECK(recovery.discard_sequence_recovery(
      {project, second, std::nullopt}).has_value());
  LMDJ_CHECK(recovery.list_sequence_recovery({project}).value().empty());
}

void test_writer_lease_blocks_competing_sequence_owner() {
  TempDirectory temp;
  const auto project = temp.path() / "lease.lmdj";
  const PatternId pattern_id{uuid(40)};
  Application owner(config(temp.path()));
  Application competitor(config(temp.path()));
  create_recordable_project(owner, project, pattern_id);
  LMDJ_CHECK(owner.begin_sequence(
      {project, SequenceSessionId{uuid(41)}, pattern_id, 2, 0}).has_value());
  const auto observed = competitor.query_sequence_status({project});
  LMDJ_CHECK(observed.has_value());
  LMDJ_CHECK(observed.value().state == SequenceRecordState::active);
  LMDJ_CHECK(observed.value().session_id == SequenceSessionId{uuid(41)});
  const auto rejected = competitor.begin_sequence(
      {project, SequenceSessionId{uuid(42)}, pattern_id, 2, 0});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      rejected.error().details.at("storage_condition") == "project_busy");
}

}  // namespace

int main() {
  try {
    test_sequence_lifecycle_idempotence_and_mutation_exclusion();
    test_owner_loss_apply_and_discard_are_explicit();
    test_writer_lease_blocks_competing_sequence_owner();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "sequence facade surface tests: PASS\n";
  return 0;
}
