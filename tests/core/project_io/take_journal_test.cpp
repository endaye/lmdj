#include <algorithm>
#include <array>
#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <string>
#include <string_view>
#include <utility>

#include <nlohmann/json.hpp>

#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/take_journal.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CreatePattern;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::RawTake;
using lmdj::domain::RawTakeEvent;
using lmdj::domain::RecordTake;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::TakeId;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::TakeJournal;

int active_directory_sync_calls = 0;
int active_journal_remove_calls = 0;
int active_journal_sync_calls = 0;

lmdj::foundation::Result<void> fail_active_journal_remove(
    lmdj::project_io::testing::FaultPoint point,
    const std::filesystem::path& path) {
  if (point !=
      lmdj::project_io::testing::FaultPoint::active_journal_remove) {
    return lmdj::foundation::Result<void>::success();
  }
  ++active_journal_remove_calls;
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected active-journal removal failure",
          {{"path", path.generic_string()}},
      });
}

lmdj::foundation::Result<void> fail_active_journal_sync(
    lmdj::project_io::testing::FaultPoint point,
    const std::filesystem::path& path) {
  if (point !=
      lmdj::project_io::testing::FaultPoint::active_journal_sync) {
    return lmdj::foundation::Result<void>::success();
  }
  ++active_journal_sync_calls;
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected active-journal sync failure",
          {{"path", path.generic_string()}},
      });
}

lmdj::foundation::Result<void> count_active_journal_sync(
    lmdj::project_io::testing::FaultPoint point,
    const std::filesystem::path&) {
  if (point ==
      lmdj::project_io::testing::FaultPoint::active_journal_sync) {
    ++active_journal_sync_calls;
  }
  return lmdj::foundation::Result<void>::success();
}

lmdj::foundation::Result<void> fail_active_directory_sync(
    lmdj::project_io::testing::FaultPoint point,
    const std::filesystem::path& path) {
  if (point !=
      lmdj::project_io::testing::FaultPoint::active_directory_sync) {
    return lmdj::foundation::Result<void>::success();
  }
  ++active_directory_sync_calls;
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected active-directory sync failure",
          {{"path", path.generic_string()}},
      });
}

lmdj::foundation::Result<void> count_active_directory_sync(
    lmdj::project_io::testing::FaultPoint point,
    const std::filesystem::path&) {
  if (point !=
      lmdj::project_io::testing::FaultPoint::active_directory_sync) {
    return lmdj::foundation::Result<void>::success();
  }
  ++active_directory_sync_calls;
  return lmdj::foundation::Result<void>::success();
}

class FaultHookGuard {
 public:
  explicit FaultHookGuard(
      lmdj::project_io::testing::FaultHook hook) {
    lmdj::project_io::testing::set_fault_hook(hook);
  }

  ~FaultHookGuard() {
    lmdj::project_io::testing::set_fault_hook(nullptr);
  }

  FaultHookGuard(const FaultHookGuard&) = delete;
  FaultHookGuard& operator=(const FaultHookGuard&) = delete;
};

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-take-journal-test-" + std::to_string(nonce));
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

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("failed to read test file");
  }
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

void write_bytes(
    const std::filesystem::path& path,
    std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  if (!stream) {
    throw std::runtime_error("failed to write test fixture");
  }
}

std::map<std::string, std::string> project_truth_snapshot(
    const std::filesystem::path& bundle) {
  std::map<std::string, std::string> snapshot;
  const std::array roots{
      bundle / "manifest.json",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
  };
  for (const auto& root : roots) {
    if (std::filesystem::is_regular_file(root)) {
      snapshot.emplace(
          std::filesystem::relative(root, bundle).generic_string(),
          read_bytes(root));
      continue;
    }
    for (const auto& entry :
         std::filesystem::recursive_directory_iterator(root)) {
      if (entry.is_regular_file()) {
        snapshot.emplace(
            std::filesystem::relative(entry.path(), bundle).generic_string(),
            read_bytes(entry.path()));
      }
    }
  }
  return snapshot;
}

std::string test_uuid(std::string_view seed) {
  std::uint64_t hash = 1469598103934665603ULL;
  for (const unsigned char character : seed) {
    hash ^= character;
    hash *= 1099511628211ULL;
  }
  constexpr std::string_view digits = "0123456789abcdef";
  std::string suffix(12, '0');
  for (std::size_t index = suffix.size(); index > 0; --index) {
    suffix.at(index - 1) = digits.at(hash & 0x0fU);
    hash >>= 4U;
  }
  return "00000000-0000-4000-8000-" + suffix;
}

lmdj::domain::ProjectState new_project() {
  const auto result =
      lmdj::domain::create_project(ProjectId{test_uuid("project-1")}, 120);
  LMDJ_CHECK(result.has_value());
  return result.value();
}

CommandMeta meta(std::string id, std::uint64_t revision) {
  return CommandMeta{CommandId{test_uuid(id)}, revision};
}

RawTake recorded_take(std::string id) {
  return RawTake{
      TakeId{test_uuid(id)},
      48000,
      {
          RawTakeEvent{PadSlotId{0, 1}, 1234, 96},
          RawTakeEvent{PadSlotId{1, 2}, 5678, 110},
      },
  };
}

Pattern recorded_pattern(std::string id) {
  return Pattern{
      PatternId{test_uuid(id)},
      1,
      {
          PatternEvent{PadSlotId{0, 1}, 1, 96},
          PatternEvent{PadSlotId{1, 2}, 5, 110},
      },
  };
}

void begin_and_append(
    TakeJournal& journal,
    const std::filesystem::path& bundle,
    const RawTake& take,
    std::uint64_t expected_revision) {
  LMDJ_CHECK(
      journal.begin(
                 bundle,
                 take.id,
                 expected_revision,
                 take.sample_rate)
          .has_value());
  for (const auto& event : take.events) {
    LMDJ_CHECK(journal.append(bundle, take.id, event).has_value());
  }
}

void test_typed_active_journal_preserves_captured_revision() {
  TempDirectory temp;
  const auto bundle = temp.path() / "typed-active.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("typed-active-take");
  begin_and_append(journal, bundle, take, 7);

  const auto active =
      journal.read_active_journal(bundle, take.id);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().take == take);
  LMDJ_CHECK(active.value().expected_revision == 7);
}

void test_take_journal_requires_uuid_and_48000_metadata() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const std::array invalid_take_ids{
      std::string{"take-1"},
      std::string{"foo.tmp.bar"},
      std::string{"00000000-0000-4000-8000-00000000000A"},
      std::string{"00000000-0000-6000-8000-000000000001"},
  };
  for (const auto& invalid_take_id : invalid_take_ids) {
    const auto rejected = journal.begin(
        bundle, TakeId{invalid_take_id}, 0, 48000);
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  }

  const auto take_id = TakeId{test_uuid("take-1")};
  const auto wrong_rate = journal.begin(bundle, take_id, 0, 44100);
  LMDJ_CHECK(!wrong_rate.has_value());
  LMDJ_CHECK(wrong_rate.error().code == ErrorCode::invalid_argument);
  const auto active_path =
      bundle / "recovery/active" / (take_id.value() + ".jsonl");
  LMDJ_CHECK(!std::filesystem::exists(active_path));

  const auto invalid_header = nlohmann::json{
      {"contract", "lmdj.take.journal.v1"},
      {"expected_revision", 0},
      {"sample_rate", 44100},
      {"take_id", take_id.value()},
  };
  write_bytes(active_path, invalid_header.dump() + "\n");
  const auto unreadable = journal.read_active(bundle, take_id);
  LMDJ_CHECK(!unreadable.has_value());
  LMDJ_CHECK(unreadable.error().code == ErrorCode::invalid_project);
  const auto unsealable =
      journal.seal(bundle, take_id, "interrupted");
  LMDJ_CHECK(!unsealable.has_value());
  LMDJ_CHECK(unsealable.error().code == ErrorCode::invalid_project);
}

void test_begin_sync_failure_preserves_io_error_and_can_retry() {
  TempDirectory temp;
  const auto bundle = temp.path() / "begin-sync-failure.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("begin-sync-failure");
  const auto active =
      bundle / "recovery/active" / (take.id.value() + ".jsonl");
  active_journal_sync_calls = 0;

  lmdj::foundation::Result<void> failed =
      lmdj::foundation::Result<void>::success();
  {
    FaultHookGuard hook(fail_active_journal_sync);
    failed = journal.begin(bundle, take.id, 0, take.sample_rate);
  }

  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(active_journal_sync_calls == 1);
  LMDJ_CHECK(!std::filesystem::exists(active));

  const auto retried =
      journal.begin(bundle, take.id, 0, take.sample_rate);
  LMDJ_CHECK(retried.has_value());
  const auto recovered = journal.read_active_journal(bundle, take.id);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().take.id == take.id);
  LMDJ_CHECK(recovered.value().take.events.empty());
  LMDJ_CHECK(recovered.value().expected_revision == 0);

  const auto duplicate =
      journal.begin(bundle, take.id, 0, take.sample_rate);
  LMDJ_CHECK(!duplicate.has_value());
  LMDJ_CHECK(duplicate.error().code == ErrorCode::duplicate_id);
  LMDJ_CHECK(std::filesystem::is_regular_file(active));
}

void test_invalid_command_id_is_rejected_before_journal_matching() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");
  begin_and_append(journal, bundle, take, 0);
  const auto active_path =
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl");
  write_bytes(active_path, "not-json\n");
  const auto corrupted_bytes = read_bytes(active_path);
  auto invalid_meta = meta("record-1", 0);
  invalid_meta.command_id = CommandId{"foo.tmp.bar"};

  const auto rejected = store.execute(
      bundle,
      Command{RecordTake{
          invalid_meta,
          take,
          recorded_pattern("pattern-1"),
      }});

  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(active_path) == corrupted_bytes);
  LMDJ_CHECK(store.load(bundle).value().revision == 0);
}

void test_append_flushes_each_event_and_restart_reads_acknowledged_data() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");

  TakeJournal first_process;
  LMDJ_CHECK(
      first_process.begin(bundle, take.id, 0, take.sample_rate).has_value());
  LMDJ_CHECK(
      first_process.append(bundle, take.id, take.events.at(0)).has_value());
  const auto active_path =
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl");
  const auto acknowledged_bytes = read_bytes(active_path);
  LMDJ_CHECK(
      std::count(
          acknowledged_bytes.begin(), acknowledged_bytes.end(), '\n') == 2);

  TakeJournal restarted_process;
  const auto after_restart =
      restarted_process.read_active(bundle, take.id);
  LMDJ_CHECK(after_restart.has_value());
  LMDJ_CHECK(after_restart.value().events.size() == 1);
  LMDJ_CHECK(after_restart.value().events.at(0) == take.events.at(0));
  LMDJ_CHECK(
      restarted_process.append(bundle, take.id, take.events.at(1)).has_value());

  TakeJournal second_restart;
  const auto complete = second_restart.read_active(bundle, take.id);
  LMDJ_CHECK(complete.has_value());
  LMDJ_CHECK(complete.value() == take);
}

void test_append_batch_validates_before_one_durable_append() {
  TempDirectory temp;
  const auto bundle = temp.path() / "batch-append.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  auto take = recorded_take("batch-append-take");
  take.events.push_back(RawTakeEvent{PadSlotId{3, 15}, 9'000, 127});
  LMDJ_CHECK(
      journal.begin(bundle, take.id, 0, take.sample_rate).has_value());
  active_journal_sync_calls = 0;

  lmdj::foundation::Result<void> appended =
      lmdj::foundation::Result<void>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "batch append did not run",
          });
  {
    FaultHookGuard hook(count_active_journal_sync);
    appended = journal.append_batch(bundle, take.id, take.events);
  }

  LMDJ_CHECK(appended.has_value());
  LMDJ_CHECK(active_journal_sync_calls == 1);
  const auto persisted = journal.read_active(bundle, take.id);
  LMDJ_CHECK(persisted.has_value());
  LMDJ_CHECK(persisted.value() == take);
  const auto active_path =
      bundle / "recovery/active" / (take.id.value() + ".jsonl");
  const auto acknowledged = read_bytes(active_path);

  const std::vector<RawTakeEvent> empty;
  const auto rejected_empty =
      journal.append_batch(bundle, take.id, empty);
  auto invalid_events = take.events;
  invalid_events.at(1).velocity = 0;
  const auto rejected_invalid =
      journal.append_batch(bundle, take.id, invalid_events);
  auto descending_events = take.events;
  descending_events.at(1).frame_offset = 1;
  const auto rejected_descending =
      journal.append_batch(bundle, take.id, descending_events);

  LMDJ_CHECK(!rejected_empty.has_value());
  LMDJ_CHECK(rejected_empty.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!rejected_invalid.has_value());
  LMDJ_CHECK(rejected_invalid.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!rejected_descending.has_value());
  LMDJ_CHECK(rejected_descending.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(active_path) == acknowledged);
}

void test_append_batch_sync_failure_preserves_recoverable_events() {
  TempDirectory temp;
  const auto bundle = temp.path() / "batch-sync-failure.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("batch-sync-failure-take");
  LMDJ_CHECK(
      journal.begin(bundle, take.id, 0, take.sample_rate).has_value());
  active_journal_sync_calls = 0;

  lmdj::foundation::Result<void> failed =
      lmdj::foundation::Result<void>::success();
  {
    FaultHookGuard hook(fail_active_journal_sync);
    failed = journal.append_batch(bundle, take.id, take.events);
  }

  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(active_journal_sync_calls == 1);
  const auto recovered = journal.read_active(bundle, take.id);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value() == take);
  const auto sealed =
      journal.seal(bundle, take.id, "capture_incomplete");
  LMDJ_CHECK(sealed.has_value());
  const auto candidates = journal.list_recoverable(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().at(0).take == take);
  LMDJ_CHECK(candidates.value().at(0).reason == "capture_incomplete");
}

void test_torn_final_record_is_ignored_and_repaired_before_append() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");
  LMDJ_CHECK(
      journal.begin(bundle, take.id, 0, take.sample_rate).has_value());
  LMDJ_CHECK(journal.append(bundle, take.id, take.events.at(0)).has_value());
  const auto active_path =
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl");
  {
    std::ofstream torn(
        active_path, std::ios::binary | std::ios::app);
    torn << R"({"frame_offset":999,"slot":{"bank":)";
    LMDJ_CHECK(static_cast<bool>(torn));
  }

  TakeJournal restarted;
  const auto recovered = restarted.read_active(bundle, take.id);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().events.size() == 1);
  LMDJ_CHECK(recovered.value().events.at(0) == take.events.at(0));

  LMDJ_CHECK(
      restarted.append(bundle, take.id, take.events.at(1)).has_value());
  const auto repaired_bytes = read_bytes(active_path);
  LMDJ_CHECK(repaired_bytes.find("\"frame_offset\":999") == std::string::npos);
  TakeJournal second_restart;
  const auto complete = second_restart.read_active(bundle, take.id);
  LMDJ_CHECK(complete.has_value());
  LMDJ_CHECK(complete.value() == take);
}

void test_record_take_keeps_journal_until_manifest_commit_then_cleans_it() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");
  begin_and_append(journal, bundle, take, 0);

  const auto manifest_temp_blocker =
      bundle /
      ("manifest.json.tmp." + test_uuid("record-1"));
  std::filesystem::create_directory(manifest_temp_blocker);
  const auto failed = store.execute(
      bundle,
      Command{RecordTake{
          meta("record-1", 0),
          take,
          recorded_pattern("pattern-1"),
      }});
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(std::filesystem::is_regular_file(
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl")));
  const auto before_commit = store.load(bundle);
  LMDJ_CHECK(before_commit.has_value());
  LMDJ_CHECK(before_commit.value().revision == 0);
  LMDJ_CHECK(before_commit.value().takes.empty());

  std::filesystem::remove(manifest_temp_blocker);
  const auto committed = store.execute(
      bundle,
      Command{RecordTake{
          meta("record-1", 0),
          take,
          recorded_pattern("pattern-1"),
      }});
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().state.revision == 1);
  LMDJ_CHECK(
      committed.value().state.takes.at(
          TakeId{test_uuid("take-1")}) == take);
  LMDJ_CHECK(!std::filesystem::exists(
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl")));
  LMDJ_CHECK(std::filesystem::is_regular_file(
      bundle / "history/checkpoints/1.json"));
  const auto transaction = nlohmann::json::parse(read_bytes(
      bundle / "history/transactions" /
      ("1-" + test_uuid("record-1") + ".json")));
  LMDJ_CHECK(
      transaction.at("cleanup_take_id") == test_uuid("take-1"));
}

void test_direct_record_take_without_matching_journal_remains_valid() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto unrelated = recorded_take("take-active");
  begin_and_append(journal, bundle, unrelated, 0);

  const auto direct_take = recorded_take("take-direct");
  const auto committed = store.execute(
      bundle,
      Command{RecordTake{
          meta("record-direct", 0),
          direct_take,
          recorded_pattern("pattern-direct"),
      }});

  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().state.revision == 1);
  LMDJ_CHECK(std::filesystem::is_regular_file(
      bundle / "recovery/active" /
      (test_uuid("take-active") + ".jsonl")));
  const auto transaction = nlohmann::json::parse(read_bytes(
      bundle / "history/transactions" /
      ("1-" + test_uuid("record-direct") + ".json")));
  LMDJ_CHECK(!transaction.contains("cleanup_take_id"));
}

void test_nonmatching_record_never_runs_active_directory_cleanup() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto unrelated = recorded_take("take-active");
  begin_and_append(journal, bundle, unrelated, 0);
  const auto unrelated_path =
      bundle / "recovery/active" /
      (test_uuid("take-active") + ".jsonl");
  const auto unrelated_bytes = read_bytes(unrelated_path);
  const auto direct_take = recorded_take("take-direct");
  active_directory_sync_calls = 0;

  lmdj::foundation::Result<lmdj::domain::AppliedCommand> committed =
      lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "test did not execute",
          });
  {
    FaultHookGuard hook(fail_active_directory_sync);
    committed = store.execute(
        bundle,
        Command{RecordTake{
            meta("record-direct", 0),
            direct_take,
            recorded_pattern("pattern-direct"),
        }});
  }

  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().state.revision == 1);
  LMDJ_CHECK(active_directory_sync_calls == 0);
  LMDJ_CHECK(std::filesystem::is_regular_file(unrelated_path));
  LMDJ_CHECK(read_bytes(unrelated_path) == unrelated_bytes);
}

void test_cleanup_failure_is_reported_and_replay_finishes_cleanup() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");
  begin_and_append(journal, bundle, take, 0);
  const auto command = Command{RecordTake{
      meta("record-1", 0),
      take,
      recorded_pattern("pattern-1"),
  }};

  active_journal_remove_calls = 0;
  lmdj::foundation::Result<lmdj::domain::AppliedCommand> cleanup_failed =
      lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "test did not execute",
          });
  {
    FaultHookGuard hook(fail_active_journal_remove);
    cleanup_failed = store.execute(bundle, command);
    LMDJ_CHECK(active_journal_remove_calls == 1);
  }

  LMDJ_CHECK(!cleanup_failed.has_value());
  LMDJ_CHECK(cleanup_failed.error().code == ErrorCode::io_error);
  const auto committed = store.load(bundle);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().revision == 1);
  LMDJ_CHECK(
      committed.value().takes.contains(TakeId{test_uuid("take-1")}));
  LMDJ_CHECK(std::filesystem::is_regular_file(
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl")));

  const auto replay = store.execute(bundle, command);
  LMDJ_CHECK(replay.has_value());
  LMDJ_CHECK(replay.value().replayed);
  LMDJ_CHECK(!std::filesystem::exists(
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl")));
}

void test_fsync_failure_after_remove_replays_persisted_cleanup_obligation() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");
  begin_and_append(journal, bundle, take, 0);
  const auto command = Command{RecordTake{
      meta("record-1", 0),
      take,
      recorded_pattern("pattern-1"),
  }};
  const auto active_path =
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl");
  active_directory_sync_calls = 0;

  lmdj::foundation::Result<lmdj::domain::AppliedCommand> cleanup_failed =
      lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "test did not execute",
          });
  {
    FaultHookGuard hook(fail_active_directory_sync);
    cleanup_failed = store.execute(bundle, command);
  }

  LMDJ_CHECK(!cleanup_failed.has_value());
  LMDJ_CHECK(cleanup_failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(active_directory_sync_calls == 1);
  LMDJ_CHECK(!std::filesystem::exists(active_path));
  const auto committed = store.load(bundle);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().revision == 1);
  LMDJ_CHECK(
      committed.value().takes.contains(TakeId{test_uuid("take-1")}));

  active_directory_sync_calls = 0;
  lmdj::foundation::Result<lmdj::domain::AppliedCommand> replayed =
      lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "test did not execute",
          });
  {
    FaultHookGuard hook(count_active_directory_sync);
    replayed = store.execute(bundle, command);
  }

  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(active_directory_sync_calls == 1);
  LMDJ_CHECK(!std::filesystem::exists(active_path));
}

void test_revision_conflict_seals_candidate_without_changing_project_truth() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");
  begin_and_append(journal, bundle, take, 0);

  const auto intervening = store.execute(
      bundle,
      Command{CreatePattern{
          meta("intervening-1", 0),
          recorded_pattern("intervening-pattern"),
      }});
  LMDJ_CHECK(intervening.has_value());
  const auto truth_before = project_truth_snapshot(bundle);

  const auto conflicted = store.execute(
      bundle,
      Command{RecordTake{
          meta("record-1", 0),
          take,
          recorded_pattern("recorded-pattern"),
      }});

  LMDJ_CHECK(!conflicted.has_value());
  LMDJ_CHECK(conflicted.error().code == ErrorCode::revision_conflict);
  LMDJ_CHECK(project_truth_snapshot(bundle) == truth_before);
  LMDJ_CHECK(!std::filesystem::exists(
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl")));
  const auto candidates = journal.list_recoverable(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().at(0).take == take);
  LMDJ_CHECK(candidates.value().at(0).expected_revision == 0);
  LMDJ_CHECK(candidates.value().at(0).reason == "revision_conflict");
  LMDJ_CHECK(std::filesystem::is_regular_file(
      candidates.value().at(0).path));
  const auto loaded = store.load(bundle);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value().revision == 1);
  LMDJ_CHECK(loaded.value().takes.empty());
}

void test_sealed_candidates_survive_workspace_cleanup_and_project_load() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");
  begin_and_append(journal, bundle, take, 0);
  const auto sealed = journal.seal(bundle, take.id, "interrupted");
  LMDJ_CHECK(sealed.has_value());
  const auto sealed_bytes = read_bytes(sealed.value());

  const auto workspace = temp.path() / ".lmdj-workspace";
  std::filesystem::create_directories(workspace / "attempts");
  std::filesystem::remove_all(workspace);
  LMDJ_CHECK(store.load(bundle).has_value());

  LMDJ_CHECK(std::filesystem::is_regular_file(sealed.value()));
  LMDJ_CHECK(read_bytes(sealed.value()) == sealed_bytes);
  const auto candidates = journal.list_recoverable(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().at(0).reason == "interrupted");
}

void test_symlinked_recovery_directory_is_rejected_before_seal() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  const auto external = temp.path() / "external-recovery";
  std::filesystem::create_directory(external);
  const auto sentinel = external / "sentinel.txt";
  {
    std::ofstream stream(sentinel, std::ios::binary);
    stream << "must-survive";
    LMDJ_CHECK(static_cast<bool>(stream));
  }
  ProjectStore store;
  TakeJournal journal;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto take = recorded_take("take-1");
  begin_and_append(journal, bundle, take, 0);
  std::filesystem::remove(bundle / "recovery/sealed");
  std::filesystem::create_directory_symlink(
      external, bundle / "recovery/sealed");

  const auto sealed = journal.seal(bundle, take.id, "interrupted");

  LMDJ_CHECK(!sealed.has_value());
  LMDJ_CHECK(sealed.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(std::filesystem::is_regular_file(sentinel));
  LMDJ_CHECK(read_bytes(sentinel) == "must-survive");
  LMDJ_CHECK(std::filesystem::is_regular_file(
      bundle / "recovery/active" /
      (test_uuid("take-1") + ".jsonl")));
}

}  // namespace

int main() {
  try {
    test_typed_active_journal_preserves_captured_revision();
    test_take_journal_requires_uuid_and_48000_metadata();
    test_begin_sync_failure_preserves_io_error_and_can_retry();
    test_invalid_command_id_is_rejected_before_journal_matching();
    test_append_flushes_each_event_and_restart_reads_acknowledged_data();
    test_append_batch_validates_before_one_durable_append();
    test_append_batch_sync_failure_preserves_recoverable_events();
    test_torn_final_record_is_ignored_and_repaired_before_append();
    test_record_take_keeps_journal_until_manifest_commit_then_cleans_it();
    test_direct_record_take_without_matching_journal_remains_valid();
    test_nonmatching_record_never_runs_active_directory_cleanup();
    test_cleanup_failure_is_reported_and_replay_finishes_cleanup();
    test_fsync_failure_after_remove_replays_persisted_cleanup_obligation();
    test_revision_conflict_seals_candidate_without_changing_project_truth();
    test_sealed_candidates_survive_workspace_cleanup_and_project_load();
    test_symlinked_recovery_directory_is_rejected_before_seal();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "take journal tests: PASS\n";
  return 0;
}
