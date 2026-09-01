#include <array>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/domain/commands.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::PerformanceId;
using lmdj::domain::PadHitPerformanceEvent;
using lmdj::domain::PerformanceEvent;
using lmdj::domain::ProjectContract;
using lmdj::domain::UpdateSequenceSettings;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::SequenceJournal;
using lmdj::project_io::SequenceSessionState;
using lmdj::project_io::testing::FaultPoint;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kPerformanceId =
    "10000000-0000-4000-8000-000000000001";
constexpr std::string_view kSessionId =
    "20000000-0000-4000-8000-000000000001";
constexpr std::string_view kBeginCommandId =
    "30000000-0000-4000-8000-000000000001";
constexpr std::string_view kRebaseCommandId =
    "30000000-0000-4000-8000-000000000002";
constexpr std::string_view kOtherCommandId =
    "30000000-0000-4000-8000-000000000003";
constexpr std::string_view kPatternId =
    "50000000-0000-4000-8000-000000000001";

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce = std::chrono::steady_clock::now()
                           .time_since_epoch()
                           .count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-rebase-" + std::to_string(nonce));
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

int journal_writes = 0;

lmdj::foundation::Result<void> fail_second_journal_write(
    FaultPoint point,
    const std::filesystem::path& path) {
  if (point == FaultPoint::sequence_journal_write && ++journal_writes == 2) {
    return lmdj::foundation::Result<void>::failure({
        ErrorCode::io_error,
        "injected rebase completion failure",
        {{"path", path.generic_string()}},
    });
  }
  return lmdj::foundation::Result<void>::success();
}

class FaultGuard {
 public:
  FaultGuard() {
    journal_writes = 0;
    lmdj::project_io::testing::set_fault_hook(fail_second_journal_write);
  }
  ~FaultGuard() { lmdj::project_io::testing::set_fault_hook(nullptr); }
};

lmdj::domain::ProjectState empty_project() {
  auto created = lmdj::domain::create_project(
      ProjectId{std::string{kProjectId}}, 120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  state.contract = ProjectContract::v4;
  return state;
}

void test_visible_rebase_receipt_requires_exact_completion_retry() {
  TempDirectory temp;
  ProjectStore store;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, empty_project()).has_value());
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto performance_id = PerformanceId{std::string{kPerformanceId}};
  LMDJ_CHECK(
      store
          .begin_performance_draft(
              bundle,
              {{CommandId{std::string{kBeginCommandId}}, 0},
               session_id,
               performance_id})
          .has_value());

  const UpdateSequenceSettings command{
      {CommandId{std::string{kRebaseCommandId}}, 1},
      130,
      std::nullopt,
      std::nullopt,
  };
  {
    FaultGuard fault;
    const auto interrupted =
        store.execute_performance_rebase(bundle, session_id, command);
    LMDJ_CHECK(!interrupted.has_value());
    LMDJ_CHECK(interrupted.error().code == ErrorCode::io_error);
  }
  LMDJ_CHECK(store.load(bundle).value().revision == 2);
  LMDJ_CHECK(store.load(bundle).value().bpm == 130);
  const auto blocked = SequenceJournal{}.read_active_performance(bundle);
  LMDJ_CHECK(blocked.has_value());
  LMDJ_CHECK(blocked.value().state ==
             SequenceSessionState::recovery_required);
  const auto blocked_event = SequenceJournal{}.append_performance_tail(
      bundle,
      session_id,
      performance_id,
      1,
      1,
      std::vector{PerformanceEvent{
          PadHitPerformanceEvent{0, 0, 120, 100}}});
  LMDJ_CHECK(!blocked_event.has_value());
  LMDJ_CHECK(blocked_event.error().details.at("reason") ==
             "performance_rebase_recovery_required");
  LMDJ_CHECK(blocked_event.error().details.contains("remedy"));

  const auto blocked_stop = store.stop_performance_session(
      bundle,
      session_id,
      CommandId{"40000000-0000-4000-8000-000000000001"});
  LMDJ_CHECK(!blocked_stop.has_value());
  LMDJ_CHECK(blocked_stop.error().details.at("reason") ==
             "performance_rebase_recovery_required");

  const UpdateSequenceSettings different_rebase{
      {CommandId{std::string{kOtherCommandId}}, 2},
      140,
      std::nullopt,
      std::nullopt,
  };
  const auto blocked_rebase = store.execute_performance_rebase(
      bundle, session_id, different_rebase);
  LMDJ_CHECK(!blocked_rebase.has_value());
  LMDJ_CHECK(blocked_rebase.error().details.at("reason") ==
             "performance_rebase_recovery_required");

  const lmdj::domain::Command blocked_mutation = lmdj::domain::CreatePattern{
      {CommandId{"30000000-0000-4000-8000-000000000006"}, 2},
      {lmdj::foundation::PatternId{std::string{kPatternId}}, 1, {}},
  };
  const auto rejected_mutation = store.execute(bundle, blocked_mutation);
  LMDJ_CHECK(!rejected_mutation.has_value());
  LMDJ_CHECK(rejected_mutation.error().details.at("reason") ==
             "performance_rebase_recovery_required");

  const std::array recovery_sample_bytes{
      std::byte{0x52}, std::byte{0x49}, std::byte{0x46}, std::byte{0x46}};
  const auto rejected_sample = store.import_artifact_bytes(
      bundle,
      {{CommandId{"30000000-0000-4000-8000-000000000007"}, 2},
       lmdj::foundation::AssetId{
           "60000000-0000-4000-8000-000000000002"},
       "audio/wav",
       recovery_sample_bytes});
  LMDJ_CHECK(!rejected_sample.has_value());
  LMDJ_CHECK(rejected_sample.error().details.at("reason") ==
             "performance_rebase_recovery_required");

  const auto retry =
      store.execute_performance_rebase(bundle, session_id, command);
  LMDJ_CHECK(retry.has_value());
  LMDJ_CHECK(retry.value().outcome.replayed);
  LMDJ_CHECK(retry.value().outcome.state.revision == 2);
  const auto active = SequenceJournal{}.read_active_performance(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().state == SequenceSessionState::active);
  LMDJ_CHECK(active.value().expected_revision == 2);

  const UpdateSequenceSettings collision{
      {CommandId{std::string{kRebaseCommandId}}, 1},
      140,
      std::nullopt,
      std::nullopt,
  };
  const auto rejected =
      store.execute_performance_rebase(bundle, session_id, collision);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);

  const lmdj::domain::Command sample_command = lmdj::domain::AssignPad{
      {CommandId{std::string{kOtherCommandId}}, 2},
      {0, 0},
      std::nullopt,
  };
  const auto sample = store.execute(bundle, sample_command);
  LMDJ_CHECK(!sample.has_value());
  LMDJ_CHECK(sample.error().details.at("reason") ==
             "performance_sample_command_blocked");
  LMDJ_CHECK(sample.error().details.at("recording_sealed") == false);
  const std::array sample_bytes{
      std::byte{0x52}, std::byte{0x49}, std::byte{0x46}, std::byte{0x46}};
  const auto imported = store.import_artifact_bytes(
      bundle,
      {{CommandId{"30000000-0000-4000-8000-000000000005"}, 2},
       lmdj::foundation::AssetId{
           "60000000-0000-4000-8000-000000000001"},
       "audio/wav",
       sample_bytes});
  LMDJ_CHECK(!imported.has_value());
  LMDJ_CHECK(imported.error().details.at("reason") ==
             "performance_sample_command_blocked");
  LMDJ_CHECK(imported.error().details.at("recording_sealed") == false);

  const lmdj::domain::Command unknown_command = lmdj::domain::CreatePattern{
      {CommandId{"30000000-0000-4000-8000-000000000004"}, 2},
      {lmdj::foundation::PatternId{std::string{kPatternId}}, 1, {}},
  };
  const auto unknown = store.execute(bundle, unknown_command);
  LMDJ_CHECK(!unknown.has_value());
  LMDJ_CHECK(unknown.error().details.at("reason") ==
             "performance_unknown_command_blocked");
  LMDJ_CHECK(SequenceJournal{}
                 .read_active_performance(bundle)
                 .value()
                 .state == SequenceSessionState::active);
}

}  // namespace

int main() {
  try {
    test_visible_rebase_receipt_requires_exact_completion_retry();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
