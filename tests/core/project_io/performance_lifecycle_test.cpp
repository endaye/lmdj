#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::PadHitPerformanceEvent;
using lmdj::domain::PerformanceEvent;
using lmdj::domain::PerformanceId;
using lmdj::domain::ProjectContract;
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
constexpr std::string_view kSecondPerformanceId =
    "10000000-0000-4000-8000-000000000002";
constexpr std::string_view kSessionId =
    "20000000-0000-4000-8000-000000000001";
constexpr std::string_view kBeginCommandId =
    "30000000-0000-4000-8000-000000000001";
constexpr std::string_view kSaveCommandId =
    "30000000-0000-4000-8000-000000000002";
constexpr std::string_view kDiscardCommandId =
    "30000000-0000-4000-8000-000000000003";
constexpr std::string_view kStopRequestId =
    "40000000-0000-4000-8000-000000000001";
constexpr std::string_view kRecoveryRequestId =
    "40000000-0000-4000-8000-000000000002";

class TempDirectory {
 public:
  explicit TempDirectory(std::string_view label) {
    const auto nonce = std::chrono::steady_clock::now()
                           .time_since_epoch()
                           .count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-lifecycle-" + std::string(label) + "-" +
             std::to_string(nonce));
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

lmdj::domain::ProjectState empty_project() {
  auto created = lmdj::domain::create_project(
      ProjectId{std::string{kProjectId}}, 120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  state.contract = ProjectContract::v4;
  return state;
}

PerformanceEvent pad_hit() {
  return PerformanceEvent{PadHitPerformanceEvent{0, 0, 120, 100}};
}

lmdj::foundation::ArtifactRef install_managed_wav(
    const std::filesystem::path& bundle,
    const std::filesystem::path& source,
    std::string_view bytes) {
  {
    std::ofstream stream(source, std::ios::binary | std::ios::trunc);
    stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  }
  const auto artifact =
      lmdj::foundation::describe_artifact(source, "audio/wav");
  LMDJ_CHECK(artifact.has_value());
  std::filesystem::copy_file(
      source,
      bundle / "assets" / (artifact.value().sha256 + ".wav"));
  return artifact.value();
}

FaultPoint selected_fault = FaultPoint::sequence_journal_write;
int selected_fault_occurrence = 1;
int observed_fault_occurrences = 0;

lmdj::foundation::Result<void> fail_selected(
    FaultPoint point,
    const std::filesystem::path& path) {
  if (point == selected_fault &&
      ++observed_fault_occurrences == selected_fault_occurrence) {
    return lmdj::foundation::Result<void>::failure({
        ErrorCode::io_error,
        "injected Performance lifecycle fault",
        {{"path", path.generic_string()}},
    });
  }
  return lmdj::foundation::Result<void>::success();
}

class FaultGuard {
 public:
  explicit FaultGuard(FaultPoint point, int occurrence = 1) {
    selected_fault = point;
    selected_fault_occurrence = occurrence;
    observed_fault_occurrences = 0;
    lmdj::project_io::testing::set_fault_hook(fail_selected);
  }
  ~FaultGuard() { lmdj::project_io::testing::set_fault_hook(nullptr); }
};

void test_begin_stop_save_is_one_durable_draft_lifecycle() {
  TempDirectory temp("save");
  ProjectStore store;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, empty_project()).has_value());
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto performance_id = PerformanceId{std::string{kPerformanceId}};

  const auto begun = store.begin_performance_draft(
      bundle,
      {{CommandId{std::string{kBeginCommandId}}, 0},
       session_id,
       performance_id});
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(!begun.value().replayed);
  LMDJ_CHECK(begun.value().committed_revision == 1);
  const auto draft = store.load(bundle).value().performances.at(performance_id);
  LMDJ_CHECK(draft.name == "Untitled Performance");
  LMDJ_CHECK(draft.created_bpm == 120);
  LMDJ_CHECK(draft.recording_revision == 0);
  LMDJ_CHECK(!draft.recording_artifact.has_value());
  LMDJ_CHECK(draft.events.empty());

  const auto replayed = store.begin_performance_draft(
      bundle,
      {{CommandId{std::string{kBeginCommandId}}, 0},
       session_id,
       performance_id});
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().committed_revision == 1);

  const auto collision = store.begin_performance_draft(
      bundle,
      {{CommandId{std::string{kBeginCommandId}}, 0},
       session_id,
       PerformanceId{std::string{kSecondPerformanceId}}});
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::invalid_argument);

  SequenceJournal journal;
  LMDJ_CHECK(
      journal
          .append_performance_tail(
              bundle, session_id, performance_id, 1, 1,
              std::vector{pad_hit()})
          .has_value());
  const auto stopped = store.stop_performance_session(
      bundle, session_id, CommandId{std::string{kStopRequestId}});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().state == SequenceSessionState::stopped);
  LMDJ_CHECK(stopped.value().pending_event_count == 1);
  LMDJ_CHECK(store.load(bundle).value().revision == 1);

  const auto saved = store.save_performance_draft(
      bundle,
      {CommandId{std::string{kSaveCommandId}}, 1},
      performance_id,
      "First Set",
      std::nullopt);
  LMDJ_CHECK(saved.has_value());
  LMDJ_CHECK(saved.value().committed_revision == 2);
  const auto truth = store.load(bundle).value();
  LMDJ_CHECK(truth.performances.at(performance_id).name == "First Set");
  LMDJ_CHECK(truth.performances.at(performance_id).events ==
             std::vector{pad_hit()});
  LMDJ_CHECK(!journal.read_active_performance(bundle).has_value());
}

void test_recording_revision_is_fixed_at_nonzero_begin_revision() {
  TempDirectory temp("recording-revision");
  ProjectStore store;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, empty_project()).has_value());
  LMDJ_CHECK(
      store
          .create_performance(
              bundle,
              {{CommandId{"30000000-0000-4000-8000-000000000010"}, 0},
               PerformanceId{std::string{kSecondPerformanceId}},
               "Existing"})
          .has_value());
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto performance_id = PerformanceId{std::string{kPerformanceId}};
  const auto request = lmdj::project_io::BeginPerformanceDraftRequest{
      {CommandId{std::string{kBeginCommandId}}, 1},
      session_id,
      performance_id,
  };

  const auto begun = store.begin_performance_draft(bundle, request);
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().committed_revision == 2);
  LMDJ_CHECK(
      store.load(bundle)
          .value()
          .performances.at(performance_id)
          .recording_revision == 1);
  const auto replayed = store.begin_performance_draft(bundle, request);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(
      store.load(bundle)
          .value()
          .performances.at(performance_id)
          .recording_revision == 1);

  SequenceJournal journal;
  LMDJ_CHECK(
      journal
          .append_performance_tail(
              bundle, session_id, performance_id, 2, 1,
              std::vector{pad_hit()})
          .has_value());
  LMDJ_CHECK(
      store
          .stop_performance_session(
              bundle, session_id,
              CommandId{std::string{kStopRequestId}})
          .has_value());
  LMDJ_CHECK(
      store
          .save_performance_draft(
              bundle,
              {CommandId{std::string{kSaveCommandId}}, 2},
              performance_id,
              "Saved",
              std::nullopt)
          .has_value());
  LMDJ_CHECK(
      store.load(bundle)
          .value()
          .performances.at(performance_id)
          .recording_revision == 1);

  const auto artifact = install_managed_wav(
      bundle, temp.path() / "recording.wav", "RIFF-recording-revision");
  LMDJ_CHECK(
      store
          .bind_performance_recording(
              bundle,
              {CommandId{"30000000-0000-4000-8000-000000000011"}, 3},
              performance_id,
              artifact)
          .has_value());
  LMDJ_CHECK(
      store.load(bundle)
          .value()
          .performances.at(performance_id)
          .recording_revision == 1);
}

void test_stopped_draft_can_be_discarded() {
  TempDirectory temp("discard");
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
  LMDJ_CHECK(
      store
          .stop_performance_session(
              bundle, session_id,
              CommandId{std::string{kStopRequestId}})
          .has_value());
  const auto discarded = store.discard_performance_draft(
      bundle,
      {CommandId{std::string{kDiscardCommandId}}, 1},
      performance_id);
  LMDJ_CHECK(discarded.has_value());
  LMDJ_CHECK(discarded.value().committed_revision == 2);
  LMDJ_CHECK(store.load(bundle).value().performances.empty());
  LMDJ_CHECK(!SequenceJournal{}.read_active_performance(bundle).has_value());
}

void test_recovery_apply_and_discard_return_stopped_drafts() {
  {
    TempDirectory temp("recovery-apply");
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
    SequenceJournal journal;
    LMDJ_CHECK(
        journal
            .append_performance_tail(
                bundle, session_id, performance_id, 1, 1,
                std::vector{pad_hit()})
            .has_value());
    LMDJ_CHECK(
        journal.seal_performance(bundle, session_id, "owner_lost")
            .has_value());
    const auto applied = store.apply_performance_recovery(
        bundle,
        {CommandId{std::string{kSaveCommandId}}, 1},
        session_id);
    LMDJ_CHECK(applied.has_value());
    LMDJ_CHECK(applied.value().committed_revision == 2);
    LMDJ_CHECK(store.load(bundle).value().performances.at(performance_id).events ==
               std::vector{pad_hit()});
    LMDJ_CHECK(
        store.load(bundle)
            .value()
            .performances.at(performance_id)
            .recording_revision == 0);
    const auto stopped = journal.read_active_performance(bundle);
    LMDJ_CHECK(stopped.has_value());
    LMDJ_CHECK(stopped.value().state == SequenceSessionState::stopped);
    LMDJ_CHECK(stopped.value().pending_events.empty());
    LMDJ_CHECK(journal.list_performance_recoverable(bundle).value().empty());
  }

  {
    TempDirectory temp("recovery-discard");
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
    SequenceJournal journal;
    LMDJ_CHECK(
        journal
            .append_performance_tail(
                bundle, session_id, performance_id, 1, 1,
                std::vector{pad_hit()})
            .has_value());
    LMDJ_CHECK(
        journal.seal_performance(bundle, session_id, "owner_lost")
            .has_value());
    const auto rename_blocked = store.rename_performance(
        bundle,
        {{CommandId{std::string{kSaveCommandId}}, 1},
         performance_id,
         "Must not rename"});
    LMDJ_CHECK(!rename_blocked.has_value());
    LMDJ_CHECK(rename_blocked.error().details.at("reason") ==
               "performance_recovery_pending");
    const auto delete_blocked = store.delete_performance(
        bundle,
        {{CommandId{std::string{kDiscardCommandId}}, 1}, performance_id});
    LMDJ_CHECK(!delete_blocked.has_value());
    LMDJ_CHECK(delete_blocked.error().details.at("reason") ==
               "performance_recovery_pending");
    const auto discarded = store.discard_performance_recovery(
        bundle,
        session_id,
        CommandId{std::string{kRecoveryRequestId}});
    LMDJ_CHECK(discarded.has_value());
    LMDJ_CHECK(store.load(bundle).value().revision == 1);
    LMDJ_CHECK(store.load(bundle)
                   .value()
                   .performances.at(performance_id)
                   .events.empty());
    const auto stopped = journal.read_active_performance(bundle);
    LMDJ_CHECK(stopped.has_value());
    LMDJ_CHECK(stopped.value().state == SequenceSessionState::stopped);
    LMDJ_CHECK(stopped.value().pending_events.empty());
  }
}

void test_recording_bind_verifies_managed_wav_and_is_null_only() {
  TempDirectory temp("bind");
  ProjectStore store;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, empty_project()).has_value());
  const auto performance_id = PerformanceId{std::string{kPerformanceId}};
  LMDJ_CHECK(
      store
          .create_performance(
              bundle,
              {{CommandId{std::string{kBeginCommandId}}, 0},
               performance_id,
               "Saved"})
          .has_value());
  const auto first = install_managed_wav(
      bundle, temp.path() / "first.wav", "RIFF-first");
  auto invalid = first;
  ++invalid.byte_length;
  LMDJ_CHECK(
      !store
           .bind_performance_recording(
               bundle,
               {CommandId{std::string{kSaveCommandId}}, 1},
               performance_id,
               invalid)
           .has_value());
  const auto bound = store.bind_performance_recording(
      bundle,
      {CommandId{std::string{kSaveCommandId}}, 1},
      performance_id,
      first);
  LMDJ_CHECK(bound.has_value());
  LMDJ_CHECK(bound.value().committed_revision == 2);
  const auto same = store.bind_performance_recording(
      bundle,
      {CommandId{std::string{kDiscardCommandId}}, 2},
      performance_id,
      first);
  LMDJ_CHECK(same.has_value());
  LMDJ_CHECK(same.value().replayed);
  LMDJ_CHECK(same.value().committed_revision == 2);
  const auto second = install_managed_wav(
      bundle, temp.path() / "second.wav", "RIFF-second");
  const auto conflict = store.bind_performance_recording(
      bundle,
      {CommandId{std::string{kDiscardCommandId}}, 2},
      performance_id,
      second);
  LMDJ_CHECK(!conflict.has_value());
  LMDJ_CHECK(conflict.error().details.at("reason") ==
             "performance_recording_conflict");
}

void test_begin_stop_and_save_faults_are_retryable_without_orphans() {
  for (const auto fault : {
           FaultPoint::sequence_transaction_write,
           FaultPoint::sequence_checkpoint_write,
           FaultPoint::sequence_manifest_publish,
       }) {
    TempDirectory temp("begin-fault");
    ProjectStore store;
    const auto bundle = temp.path() / "project.lmdj";
    LMDJ_CHECK(store.create(bundle, empty_project()).has_value());
    const auto request = lmdj::project_io::BeginPerformanceDraftRequest{
        {CommandId{std::string{kBeginCommandId}}, 0},
        SequenceSessionId{std::string{kSessionId}},
        PerformanceId{std::string{kPerformanceId}},
    };
    {
      FaultGuard guard(fault);
      LMDJ_CHECK(!store.begin_performance_draft(bundle, request).has_value());
    }
    LMDJ_CHECK(store.load(bundle).value().revision == 0);
    const auto retained = SequenceJournal{}.read_active_performance(bundle);
    LMDJ_CHECK(retained.has_value());
    LMDJ_CHECK(retained.value().state ==
               SequenceSessionState::recovery_required);
    const auto retried = store.begin_performance_draft(bundle, request);
    LMDJ_CHECK(retried.has_value());
    LMDJ_CHECK(retried.value().committed_revision == 1);
    LMDJ_CHECK(store.load(bundle).value().performances.size() == 1);
  }

  {
    TempDirectory temp("begin-completion-fault");
    ProjectStore store;
    const auto bundle = temp.path() / "project.lmdj";
    LMDJ_CHECK(store.create(bundle, empty_project()).has_value());
    const auto request = lmdj::project_io::BeginPerformanceDraftRequest{
        {CommandId{std::string{kBeginCommandId}}, 0},
        SequenceSessionId{std::string{kSessionId}},
        PerformanceId{std::string{kPerformanceId}},
    };
    {
      FaultGuard guard(FaultPoint::sequence_journal_write, 2);
      LMDJ_CHECK(!store.begin_performance_draft(bundle, request).has_value());
    }
    LMDJ_CHECK(store.load(bundle).value().revision == 1);
    LMDJ_CHECK(SequenceJournal{}
                   .read_active_performance(bundle)
                   .value()
                   .state == SequenceSessionState::recovery_required);
    const auto retried = store.begin_performance_draft(bundle, request);
    LMDJ_CHECK(retried.has_value());
    LMDJ_CHECK(retried.value().replayed);
    LMDJ_CHECK(SequenceJournal{}
                   .read_active_performance(bundle)
                   .value()
                   .state == SequenceSessionState::active);
  }

  {
    TempDirectory temp("stop-save-fault");
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
    {
      FaultGuard guard(FaultPoint::sequence_journal_write);
      LMDJ_CHECK(
          !store
               .stop_performance_session(
                   bundle,
                   session_id,
                   CommandId{std::string{kStopRequestId}})
               .has_value());
    }
    LMDJ_CHECK(SequenceJournal{}
                   .read_active_performance(bundle)
                   .value()
                   .state == SequenceSessionState::active);
    LMDJ_CHECK(
        store
            .stop_performance_session(
                bundle,
                session_id,
                CommandId{std::string{kStopRequestId}})
            .has_value());
    {
      FaultGuard guard(FaultPoint::sequence_journal_deletion);
      LMDJ_CHECK(
          !store
               .save_performance_draft(
                   bundle,
                   {CommandId{std::string{kSaveCommandId}}, 1},
                   performance_id,
                   "Recovered Save",
                   std::nullopt)
               .has_value());
    }
    LMDJ_CHECK(store.load(bundle).value().revision == 2);
    LMDJ_CHECK(SequenceJournal{}.read_active_performance(bundle).has_value());
    const auto retried = store.save_performance_draft(
        bundle,
        {CommandId{std::string{kSaveCommandId}}, 1},
        performance_id,
        "Recovered Save",
        std::nullopt);
    LMDJ_CHECK(retried.has_value());
    LMDJ_CHECK(retried.value().replayed);
    LMDJ_CHECK(!SequenceJournal{}.read_active_performance(bundle).has_value());
  }
}

void test_recovery_cleanup_faults_reconcile_exactly_once() {
  {
    TempDirectory temp("recovery-apply-cleanup-fault");
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
    SequenceJournal journal;
    LMDJ_CHECK(
        journal
            .append_performance_tail(
                bundle, session_id, performance_id, 1, 1,
                std::vector{pad_hit()})
            .has_value());
    LMDJ_CHECK(
        journal.seal_performance(bundle, session_id, "owner_lost")
            .has_value());
    {
      FaultGuard guard(FaultPoint::sequence_journal_deletion);
      LMDJ_CHECK(
          !store
               .apply_performance_recovery(
                   bundle,
                   {CommandId{std::string{kSaveCommandId}}, 1},
                   session_id)
               .has_value());
    }
    LMDJ_CHECK(store.load(bundle).value().revision == 2);
    LMDJ_CHECK(journal.read_active_performance(bundle).has_value());
    LMDJ_CHECK(journal.list_performance_recoverable(bundle).value().size() == 1);
    const auto retried = store.apply_performance_recovery(
        bundle,
        {CommandId{std::string{kSaveCommandId}}, 1},
        session_id);
    LMDJ_CHECK(retried.has_value());
    LMDJ_CHECK(retried.value().replayed);
    LMDJ_CHECK(store.load(bundle).value().revision == 2);
    LMDJ_CHECK(journal.list_performance_recoverable(bundle).value().empty());
  }

  {
    TempDirectory temp("recovery-discard-cleanup-fault");
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
    SequenceJournal journal;
    LMDJ_CHECK(
        journal
            .append_performance_tail(
                bundle, session_id, performance_id, 1, 1,
                std::vector{pad_hit()})
            .has_value());
    LMDJ_CHECK(
        journal.seal_performance(bundle, session_id, "owner_lost")
            .has_value());
    const auto request_id = CommandId{std::string{kRecoveryRequestId}};
    {
      FaultGuard guard(FaultPoint::sequence_journal_deletion);
      LMDJ_CHECK(
          !store
               .discard_performance_recovery(
                   bundle, session_id, request_id)
               .has_value());
    }
    LMDJ_CHECK(store.load(bundle).value().revision == 1);
    LMDJ_CHECK(journal.read_active_performance(bundle).has_value());
    LMDJ_CHECK(journal.list_performance_recoverable(bundle).value().size() == 1);
    const auto retried = store.discard_performance_recovery(
        bundle, session_id, request_id);
    LMDJ_CHECK(retried.has_value());
    LMDJ_CHECK(retried.value().replayed);
    LMDJ_CHECK(journal.list_performance_recoverable(bundle).value().empty());
  }
}

}  // namespace

int main() {
  try {
    test_begin_stop_save_is_one_durable_draft_lifecycle();
    test_recording_revision_is_fixed_at_nonzero_begin_revision();
    test_stopped_draft_can_be_discarded();
    test_recovery_apply_and_discard_return_stopped_drafts();
    test_recording_bind_verifies_managed_wav_and_is_null_only();
    test_begin_stop_and_save_faults_are_retryable_without_orphans();
    test_recovery_cleanup_faults_reconcile_exactly_once();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
