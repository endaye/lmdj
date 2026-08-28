#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <span>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/domain/project.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::SequenceFlushIdentity;
using lmdj::project_io::SequenceJournal;
using lmdj::project_io::SequenceSessionState;
using lmdj::project_io::testing::FaultPoint;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kPatternId =
    "10000000-0000-4000-8000-000000000001";
constexpr std::string_view kSessionId =
    "20000000-0000-4000-8000-000000000001";
constexpr std::string_view kCommandId =
    "30000000-0000-4000-8000-000000000001";

class TempDirectory {
 public:
  explicit TempDirectory(std::string_view label) {
    const auto nonce = std::chrono::steady_clock::now()
                           .time_since_epoch()
                           .count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-sequence-journal-" + std::string(label) + "-" +
             std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }

  const std::filesystem::path& path() const { return path_; }

  TempDirectory(const TempDirectory&) = delete;
  TempDirectory& operator=(const TempDirectory&) = delete;

 private:
  std::filesystem::path path_;
};

std::string read_text(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  return {
      std::istreambuf_iterator<char>{stream},
      std::istreambuf_iterator<char>{},
  };
}

std::string uuid_for(std::uint64_t value) {
  constexpr char digits[] = "0123456789abcdef";
  std::string uuid = "40000000-0000-4000-8000-000000000000";
  for (std::size_t index = 0; index < 12; ++index) {
    uuid[uuid.size() - 1 - index] = digits[value & 0xfU];
    value >>= 4U;
  }
  return uuid;
}

Pattern empty_pattern() {
  return {PatternId{std::string{kPatternId}}, 1, {}};
}

lmdj::domain::ProjectState project_with_pattern() {
  auto created = lmdj::domain::create_project(
      ProjectId{std::string{kProjectId}}, 120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  auto pattern = empty_pattern();
  state.patterns.emplace(pattern.id, pattern);
  return state;
}

PatternEvent event(
    std::uint8_t pad = 0,
    std::uint32_t onset = 0,
    std::uint32_t duration = 240,
    std::uint8_t velocity = 100) {
  return {PadSlotId{0, pad}, onset, duration, velocity};
}

std::filesystem::path create_bundle(
    TempDirectory& temp,
    ProjectStore& store) {
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, project_with_pattern()).has_value());
  return bundle;
}

void begin(SequenceJournal& journal, const std::filesystem::path& bundle) {
  const auto pattern = empty_pattern();
  LMDJ_CHECK(
      journal
          .begin(
              bundle,
              SequenceSessionId{std::string{kSessionId}},
              pattern.id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              0)
          .has_value());
}

std::string sha256(std::string_view bytes) {
  picosha2::hash256_one_by_one hasher;
  hasher.process(bytes.begin(), bytes.end());
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

void test_shared_fingerprint_vectors_are_exact_bytes() {
  const auto path = std::filesystem::path{LMDJ_SOURCE_DIR} /
                    "tests/fixtures/golden/sequence-pattern-fingerprint-v1.json";
  const auto document = nlohmann::json::parse(read_text(path));
  LMDJ_CHECK(
      document.at("contract") ==
      "lmdj.sequence-pattern-fingerprint-v1");
  for (const auto& vector : document.at("vectors")) {
    const auto canonical = vector.at("canonical_json").get<std::string>();
    LMDJ_CHECK(!canonical.ends_with('\n'));
    LMDJ_CHECK(!canonical.starts_with("\xef\xbb\xbf"));
    LMDJ_CHECK(
        sha256(canonical) == vector.at("sha256").get<std::string>());
  }
  const auto empty = empty_pattern();
  LMDJ_CHECK(
      lmdj::project_io::sequence_pattern_fingerprint(empty) ==
      document.at("vectors").at(0).at("sha256").get<std::string>());
  auto populated = empty;
  populated.events.push_back(event());
  LMDJ_CHECK(
      lmdj::project_io::sequence_pattern_fingerprint(populated) ==
      document.at("vectors").at(1).at("sha256").get<std::string>());
}

void test_durable_tail_snapshots_survive_reload_and_are_consumed_by_flush() {
  TempDirectory temp("tail");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto pattern_id = PatternId{std::string{kPatternId}};

  LMDJ_CHECK(
      journal
          .append_tail(bundle, session_id, pattern_id, 0, 1,
                       std::vector{event(1, 480, 240, 80)})
          .has_value());
  const std::vector second_tail{
      event(1, 480, 240, 80),
      event(0, 0, 120, 100),
  };
  LMDJ_CHECK(
      journal.append_tail(bundle, session_id, pattern_id, 0, 2, second_tail)
          .has_value());

  const auto reloaded = journal.read_active(bundle);
  LMDJ_CHECK(reloaded.has_value());
  LMDJ_CHECK(reloaded.value().next_tail_seq == 2);
  LMDJ_CHECK(reloaded.value().last_input_sequence == 2);
  LMDJ_CHECK(reloaded.value().pending_events.size() == 2);
  LMDJ_CHECK(reloaded.value().pending_events.at(0) == event(0, 0, 120, 100));
  LMDJ_CHECK(reloaded.value().pending_events.at(1) == event(1, 480, 240, 80));

  const auto flushed = journal.append_flush(
      bundle,
      session_id,
      CommandId{std::string{kCommandId}},
      pattern_id,
      0,
      second_tail);
  LMDJ_CHECK(flushed.has_value());
  const auto consumed = journal.read_active(bundle);
  LMDJ_CHECK(consumed.has_value());
  LMDJ_CHECK(consumed.value().pending_events.empty());
  LMDJ_CHECK(consumed.value().flushes.size() == 1);
  LMDJ_CHECK(consumed.value().flushes.front().canonical_events ==
             reloaded.value().pending_events);
}

void test_torn_tail_fails_closed_with_actionable_recovery_evidence() {
  TempDirectory temp("torn-tail");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto path = bundle / "recovery/active/sequence.jsonl";
  const auto durable_prefix = std::filesystem::file_size(path);
  constexpr std::string_view torn = "{\"checksum\":\"partial";
  {
    std::ofstream stream(path, std::ios::binary | std::ios::app);
    LMDJ_CHECK(static_cast<bool>(stream));
    stream.write(torn.data(), static_cast<std::streamsize>(torn.size()));
    LMDJ_CHECK(static_cast<bool>(stream));
  }

  const auto rejected = journal.read_active(bundle);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(
      rejected.error().details.at("reason") == "sequence_journal_torn_tail");
  LMDJ_CHECK(
      rejected.error().details.at("durable_prefix_length") == durable_prefix);
  LMDJ_CHECK(rejected.error().details.at("observed_length") ==
             durable_prefix + torn.size());
  LMDJ_CHECK(rejected.error().details.at("path") == path.generic_string());
  LMDJ_CHECK(
      rejected.error().details.at("remedy") ==
      "retain the journal and repair or discard the torn tail explicitly");
  LMDJ_CHECK(std::filesystem::file_size(path) == durable_prefix + torn.size());
}

void test_one_project_session_and_monotonic_durable_flush_identity() {
  TempDirectory temp("identity");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);

  const auto duplicate = journal.begin(
      bundle,
      SequenceSessionId{uuid_for(2)},
      PatternId{std::string{kPatternId}},
      1,
      std::string(64, '0'),
      0);
  LMDJ_CHECK(!duplicate.has_value());
  LMDJ_CHECK(duplicate.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      duplicate.error().details.at("reason") == "sequence_session_active");
  LMDJ_CHECK(
      duplicate.error().details.at("session_id") == kSessionId);

  const std::vector first_events{
      event(1, 240, 120, 80),
      event(0, 0, 240, 90),
      event(1, 240, 300, 127),
  };
  auto first = journal.append_flush(
      bundle,
      SequenceSessionId{std::string{kSessionId}},
      CommandId{std::string{kCommandId}},
      PatternId{std::string{kPatternId}},
      0,
      first_events);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(first.value().flush_seq == 0);
  LMDJ_CHECK(first.value().canonical_events.size() == 2);
  LMDJ_CHECK(first.value().canonical_events[0].slot.pad == 0);
  LMDJ_CHECK(first.value().canonical_events[1].duration_tick == 300);
  LMDJ_CHECK(first.value().canonical_events[1].velocity == 127);

  const auto bytes = read_text(bundle / "recovery/active/sequence.jsonl");
  LMDJ_CHECK(bytes.find(kSessionId) != std::string::npos);
  LMDJ_CHECK(bytes.find(kCommandId) != std::string::npos);
  LMDJ_CHECK(bytes.find("\"flush_seq\":0") != std::string::npos);
  const auto unchanged = store.load(bundle);
  LMDJ_CHECK(unchanged.has_value());
  LMDJ_CHECK(unchanged.value().revision == 0);

  LMDJ_CHECK(
      journal
          .complete_flush(
              bundle,
              SequenceSessionId{std::string{kSessionId}},
              0,
              1,
              std::string(64, '1'))
          .has_value());
  const std::vector second_events{event(2, 480)};
  auto second = journal.append_flush(
      bundle,
      SequenceSessionId{std::string{kSessionId}},
      CommandId{uuid_for(3)},
      PatternId{std::string{kPatternId}},
      1,
      second_events);
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(second.value().flush_seq == 1);
}

void test_writer_lease_contention_fails_before_begin() {
  TempDirectory temp("lease");
  auto platform = lmdj::project_io::make_default_project_storage_platform();
  ProjectStore store{platform};
  const auto bundle = create_bundle(temp, store);
  auto held = platform->acquire_writer(bundle);
  LMDJ_CHECK(held.has_value());
  SequenceJournal contender{
      lmdj::project_io::make_default_project_storage_platform()};
  const auto result = contender.begin(
      bundle,
      SequenceSessionId{std::string{kSessionId}},
      PatternId{std::string{kPatternId}},
      1,
      std::string(64, '0'),
      0);
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      result.error().details.at("storage_condition") == "project_busy");
}

void test_sequence_flush_commits_once_and_replays_receipt() {
  TempDirectory temp("replay");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const std::vector events{event()};
  auto flush = journal.append_flush(
      bundle,
      SequenceSessionId{std::string{kSessionId}},
      CommandId{std::string{kCommandId}},
      PatternId{std::string{kPatternId}},
      0,
      events);
  LMDJ_CHECK(flush.has_value());
  const SequenceFlushIdentity identity{
      SequenceSessionId{std::string{kSessionId}},
      flush.value().flush_seq,
      CommandId{std::string{kCommandId}},
      PatternId{std::string{kPatternId}},
  };

  const auto first = store.execute_sequence_flush(bundle, identity);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(!first.value().outcome.replayed);
  LMDJ_CHECK(first.value().outcome.state.revision == 1);
  LMDJ_CHECK(
      first.value().outcome.state.patterns.at(identity.pattern_id).events.size() ==
      1);
  const auto active = journal.read_active(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().flushes.at(0).completed);

  const auto replayed = store.execute_sequence_flush(bundle, identity);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().outcome.replayed);
  LMDJ_CHECK(replayed.value().outcome.state.revision == 1);
  LMDJ_CHECK(
      replayed.value()
          .outcome.state.patterns.at(identity.pattern_id)
          .events.size() == 1);
}

void test_pattern_switch_preserves_session_flush_sequence() {
  TempDirectory temp("switch");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto first = journal.append_flush(
      bundle,
      session_id,
      CommandId{std::string{kCommandId}},
      PatternId{std::string{kPatternId}},
      0,
      std::vector{event()});
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(
      store
          .execute_sequence_flush(
              bundle,
              {session_id,
               first.value().flush_seq,
               CommandId{std::string{kCommandId}},
               PatternId{std::string{kPatternId}}})
          .has_value());

  const Pattern next{PatternId{uuid_for(9)}, 2, {}};
  LMDJ_CHECK(
      journal
          .switch_pattern(
              bundle,
              session_id,
              next.id,
              next.bars,
              lmdj::project_io::sequence_pattern_fingerprint(next),
              1)
          .has_value());
  const auto switched = journal.read_active(bundle);
  LMDJ_CHECK(switched.has_value());
  LMDJ_CHECK(switched.value().session_id == session_id);
  LMDJ_CHECK(switched.value().pattern_id == next.id);
  LMDJ_CHECK(switched.value().bars == 2);
  LMDJ_CHECK(switched.value().expected_revision == 1);
  LMDJ_CHECK(switched.value().next_flush_seq == 1);
  LMDJ_CHECK(switched.value().flushes.size() == 1);

  const auto second = journal.append_flush(
      bundle,
      session_id,
      CommandId{uuid_for(10)},
      next.id,
      1,
      std::vector{event(1)});
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(second.value().flush_seq == 1);
}

FaultPoint selected_fault = FaultPoint::sequence_receipt_reload;

lmdj::foundation::Result<void> fail_selected(
    FaultPoint point,
    const std::filesystem::path& path) {
  if (point != selected_fault) {
    return lmdj::foundation::Result<void>::success();
  }
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected Sequence fault",
          {{"path", path.generic_string()}},
      });
}

class FaultGuard {
 public:
  explicit FaultGuard(FaultPoint point) {
    selected_fault = point;
    lmdj::project_io::testing::set_fault_hook(fail_selected);
  }
  ~FaultGuard() { lmdj::project_io::testing::set_fault_hook(nullptr); }

  FaultGuard(const FaultGuard&) = delete;
  FaultGuard& operator=(const FaultGuard&) = delete;
};

void test_restart_reconciles_reload_visible_receipt_without_overdub() {
  TempDirectory temp("reconcile");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const std::vector events{event()};
  auto flush = journal.append_flush(
      bundle,
      SequenceSessionId{std::string{kSessionId}},
      CommandId{std::string{kCommandId}},
      PatternId{std::string{kPatternId}},
      0,
      events);
  LMDJ_CHECK(flush.has_value());
  const SequenceFlushIdentity identity{
      SequenceSessionId{std::string{kSessionId}},
      0,
      CommandId{std::string{kCommandId}},
      PatternId{std::string{kPatternId}},
  };
  lmdj::foundation::Result<lmdj::project_io::SequenceFlushExecution> result =
      lmdj::foundation::Result<
          lmdj::project_io::SequenceFlushExecution>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error, "fault was not run"});
  {
    FaultGuard fault(FaultPoint::sequence_receipt_reload);
    result = store.execute_sequence_flush(bundle, identity);
  }
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::io_error);
  const auto committed = store.load(bundle);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().revision == 1);
  LMDJ_CHECK(committed.value().patterns.at(identity.pattern_id).events.size() == 1);
  LMDJ_CHECK(!journal.read_active(bundle).value().flushes.at(0).completed);

  ProjectStore restarted;
  const auto candidates = restarted.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().empty());
  const auto no_active = journal.read_active(bundle);
  LMDJ_CHECK(!no_active.has_value());
  LMDJ_CHECK(no_active.error().code == ErrorCode::not_found);
  const auto reopened = restarted.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value().revision == 1);
  LMDJ_CHECK(reopened.value().patterns.at(identity.pattern_id).events.size() == 1);
}

void test_flush_fault_matrix_has_only_recoverable_or_single_commit_outcomes() {
  constexpr std::array fault_points{
      FaultPoint::sequence_journal_write,
      FaultPoint::sequence_transaction_write,
      FaultPoint::sequence_checkpoint_write,
      FaultPoint::sequence_manifest_publish,
      FaultPoint::sequence_receipt_reload,
      FaultPoint::sequence_journal_completion,
  };
  for (std::size_t index = 0; index < fault_points.size(); ++index) {
    TempDirectory temp("matrix-" + std::to_string(index));
    ProjectStore store;
    const auto bundle = create_bundle(temp, store);
    SequenceJournal journal;
    begin(journal, bundle);
    const std::vector events{event()};
    const SequenceFlushIdentity identity{
        SequenceSessionId{std::string{kSessionId}},
        0,
        CommandId{std::string{kCommandId}},
        PatternId{std::string{kPatternId}},
    };

    if (fault_points[index] == FaultPoint::sequence_journal_write) {
      FaultGuard fault(fault_points[index]);
      const auto appended = journal.append_flush(
          bundle,
          identity.session_id,
          identity.command_id,
          identity.pattern_id,
          0,
          events);
      LMDJ_CHECK(!appended.has_value());
      LMDJ_CHECK(appended.error().code == ErrorCode::io_error);
    } else {
      LMDJ_CHECK(
          journal
              .append_flush(
                  bundle,
                  identity.session_id,
                  identity.command_id,
                  identity.pattern_id,
                  0,
                  events)
              .has_value());
      FaultGuard fault(fault_points[index]);
      const auto executed = store.execute_sequence_flush(bundle, identity);
      LMDJ_CHECK(!executed.has_value());
      LMDJ_CHECK(executed.error().code == ErrorCode::io_error);
    }

    const bool committed =
        fault_points[index] == FaultPoint::sequence_receipt_reload ||
        fault_points[index] == FaultPoint::sequence_journal_completion;
    const auto visible = store.load(bundle);
    LMDJ_CHECK(visible.has_value());
    LMDJ_CHECK(visible.value().revision == (committed ? 1 : 0));
    LMDJ_CHECK(
        visible.value().patterns.at(identity.pattern_id).events.size() ==
        (committed ? 1 : 0));

    const auto reconciled = store.reconcile_sequence_recovery(bundle);
    LMDJ_CHECK(reconciled.has_value());
    if (committed) {
      LMDJ_CHECK(reconciled.value().empty());
      const auto replayed = store.replay_sequence_flush(bundle, identity);
      LMDJ_CHECK(replayed.has_value());
      LMDJ_CHECK(replayed.value().has_value());
      LMDJ_CHECK(replayed.value()->outcome.state.revision == 1);
      LMDJ_CHECK(
          replayed.value()
              ->outcome.state.patterns.at(identity.pattern_id)
              .events.size() == 1);
    } else {
      LMDJ_CHECK(reconciled.value().size() == 1);
      LMDJ_CHECK(reconciled.value().front().reason == "owner_lost");
      LMDJ_CHECK(store.load(bundle).value().revision == 0);
    }
  }

  TempDirectory temp("matrix-deletion");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const std::vector events{event()};
  const SequenceFlushIdentity identity{
      SequenceSessionId{std::string{kSessionId}},
      0,
      CommandId{std::string{kCommandId}},
      PatternId{std::string{kPatternId}},
  };
  LMDJ_CHECK(
      journal
          .append_flush(
              bundle,
              identity.session_id,
              identity.command_id,
              identity.pattern_id,
              0,
              events)
          .has_value());
  LMDJ_CHECK(store.execute_sequence_flush(bundle, identity).has_value());
  {
    FaultGuard fault(FaultPoint::sequence_journal_deletion);
    const auto removed =
        journal.remove_active_if_complete(bundle, identity.session_id);
    LMDJ_CHECK(!removed.has_value());
    LMDJ_CHECK(removed.error().code == ErrorCode::io_error);
  }
  LMDJ_CHECK(store.load(bundle).value().revision == 1);
  const auto reconciled = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(reconciled.has_value());
  LMDJ_CHECK(reconciled.value().empty());
  LMDJ_CHECK(store.load(bundle).value().revision == 1);
}

void test_uncommitted_flush_seals_owner_lost_recovery() {
  TempDirectory temp("owner-lost");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const std::vector events{event()};
  LMDJ_CHECK(
      journal
          .append_flush(
              bundle,
              SequenceSessionId{std::string{kSessionId}},
              CommandId{std::string{kCommandId}},
              PatternId{std::string{kPatternId}},
              0,
              events)
          .has_value());
  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().reason == "owner_lost");
  LMDJ_CHECK(
      candidates.value().front().journal.state ==
      SequenceSessionState::owner_lost);
  LMDJ_CHECK(!candidates.value().front().journal.flushes.at(0).completed);
  LMDJ_CHECK(store.load(bundle).value().revision == 0);
}

void test_concurrent_flush_allocation_is_gap_free() {
  TempDirectory temp("stress");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  constexpr std::size_t kWorkers = 32;
  std::atomic<bool> failed{false};
  std::vector<std::thread> workers;
  workers.reserve(kWorkers);
  for (std::size_t index = 0; index < kWorkers; ++index) {
    workers.emplace_back([&, index] {
      const std::vector events{event(
          static_cast<std::uint8_t>(index % 16),
          static_cast<std::uint32_t>((index % 16) * 240))};
      auto appended = journal.append_flush(
          bundle,
          SequenceSessionId{std::string{kSessionId}},
          CommandId{uuid_for(index + 1)},
          PatternId{std::string{kPatternId}},
          0,
          events);
      if (!appended.has_value()) {
        failed.store(true, std::memory_order_release);
      }
    });
  }
  for (auto& worker : workers) {
    worker.join();
  }
  LMDJ_CHECK(!failed.load(std::memory_order_acquire));
  const auto active = journal.read_active(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().flushes.size() == kWorkers);
  LMDJ_CHECK(active.value().next_flush_seq == kWorkers);
  for (std::size_t index = 0; index < kWorkers; ++index) {
    LMDJ_CHECK(active.value().flushes[index].flush_seq == index);
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string_view{argv[1]} == "--stress") {
      test_concurrent_flush_allocation_is_gap_free();
      return 0;
    }
    test_shared_fingerprint_vectors_are_exact_bytes();
    test_durable_tail_snapshots_survive_reload_and_are_consumed_by_flush();
    test_torn_tail_fails_closed_with_actionable_recovery_evidence();
    test_one_project_session_and_monotonic_durable_flush_identity();
    test_writer_lease_contention_fails_before_begin();
    test_sequence_flush_commits_once_and_replays_receipt();
    test_pattern_switch_preserves_session_flush_sequence();
    test_restart_reconciles_reload_visible_receipt_without_overdub();
    test_flush_fault_matrix_has_only_recoverable_or_single_commit_outcomes();
    test_uncommitted_flush_seals_owner_lost_recovery();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
