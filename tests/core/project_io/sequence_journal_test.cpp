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
#include <lmdj/foundation/json.hpp>
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

void write_text(const std::filesystem::path& path, std::string_view text) {
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  LMDJ_CHECK(static_cast<bool>(stream));
  stream.write(text.data(), static_cast<std::streamsize>(text.size()));
  LMDJ_CHECK(static_cast<bool>(stream));
}

template <typename Mutator>
std::pair<std::size_t, std::size_t> rewrite_last_record(
    const std::filesystem::path& path,
    Mutator&& mutate) {
  const auto original = read_text(path);
  LMDJ_CHECK(original.ends_with('\n'));
  const auto previous = original.rfind('\n', original.size() - 2);
  const auto offset = previous == std::string::npos ? 0 : previous + 1;
  auto envelope = nlohmann::json::parse(
      original.substr(offset, original.size() - offset - 1));
  mutate(envelope);
  const auto replacement = lmdj::foundation::canonical_json(envelope) + "\n";
  const auto changed = original.substr(0, offset) + replacement;
  write_text(path, changed);
  return {offset, changed.size()};
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
  LMDJ_CHECK(rejected.error().details.at("record_offset") == durable_prefix);
  LMDJ_CHECK(rejected.error().details.at("observed_length") ==
             durable_prefix + torn.size());
  LMDJ_CHECK(rejected.error().details.at("path") == path.generic_string());
  LMDJ_CHECK(rejected.error().details.at("journal_retained") == true);
  LMDJ_CHECK(
      rejected.error().details.at("remedy") ==
      "retain the journal; repair the invalid suffix or discard the recovery "
      "journal explicitly");
  LMDJ_CHECK(std::filesystem::file_size(path) == durable_prefix + torn.size());
}

void expect_corrupt_record_evidence(
    const lmdj::foundation::Error& error,
    const std::filesystem::path& path,
    std::size_t offset,
    std::size_t observed_length,
    std::string_view expected_reason) {
  LMDJ_CHECK(error.code == ErrorCode::invalid_project);
  LMDJ_CHECK(error.details.at("reason") == expected_reason);
  LMDJ_CHECK(error.details.at("durable_prefix_length") == offset);
  LMDJ_CHECK(error.details.at("record_offset") == offset);
  LMDJ_CHECK(error.details.at("observed_length") == observed_length);
  LMDJ_CHECK(error.details.at("path") == path.generic_string());
  LMDJ_CHECK(error.details.at("journal_retained") == true);
  LMDJ_CHECK(
      error.details.at("remedy").get<std::string>().find("discard") !=
      std::string::npos);
  LMDJ_CHECK(std::filesystem::file_size(path) == observed_length);
}

void test_complete_line_tail_corruption_fails_closed_with_uniform_evidence() {
  const auto run = [](
                       std::string_view label,
                       std::string_view expected_reason,
                       const auto& corrupt) {
    TempDirectory temp(label);
    ProjectStore store;
    const auto bundle = create_bundle(temp, store);
    SequenceJournal journal;
    begin(journal, bundle);
    const auto path = bundle / "recovery/active/sequence.jsonl";
    LMDJ_CHECK(
        journal
            .append_tail(
                bundle,
                SequenceSessionId{std::string{kSessionId}},
                PatternId{std::string{kPatternId}},
                0,
                1,
                std::vector{
                    event(0, 0, 120, 100),
                    event(1, 480, 240, 80),
                })
            .has_value());
    const auto [offset, observed_length] = rewrite_last_record(path, corrupt);
    const auto rejected = journal.read_active(bundle);
    LMDJ_CHECK(!rejected.has_value());
    expect_corrupt_record_evidence(
        rejected.error(), path, offset, observed_length, expected_reason);
  };

  run(
      "checksum-corrupt",
      "sequence_journal_checksum_mismatch",
      [](nlohmann::json& envelope) {
        envelope["checksum"] = std::string(64, '0');
      });
  run(
      "tail-sequence-corrupt",
      "sequence_journal_tail_identity_invalid",
      [](nlohmann::json& envelope) {
        envelope["payload"]["tail_seq"] = 9;
        envelope["checksum"] = sha256(
            lmdj::foundation::canonical_json(envelope.at("payload")));
      });
  run(
      "tail-canonical-corrupt",
      "sequence_journal_tail_not_canonical",
      [](nlohmann::json& envelope) {
        auto& events = envelope["payload"]["events"];
        const auto first = events.at(0);
        events[0] = events.at(1);
        events[1] = first;
        envelope["checksum"] = sha256(
            lmdj::foundation::canonical_json(envelope.at("payload")));
      });
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

void test_repeated_command_id_is_idempotent_or_rejected_before_append() {
  TempDirectory temp("command-idempotency");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto command_id = CommandId{std::string{kCommandId}};
  const auto pattern_id = PatternId{std::string{kPatternId}};
  const std::vector events{event()};

  const auto first = journal.append_flush(
      bundle, session_id, command_id, pattern_id, 0, events);
  LMDJ_CHECK(first.has_value());
  const auto journal_bytes = read_text(
      bundle / "recovery/active/sequence.jsonl");

  const auto replayed = journal.append_flush(
      bundle, session_id, command_id, pattern_id, 0, events);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value() == first.value());
  LMDJ_CHECK(
      read_text(bundle / "recovery/active/sequence.jsonl") == journal_bytes);

  LMDJ_CHECK(
      journal
          .complete_flush(
              bundle,
              session_id,
              first.value().flush_seq,
              1,
              std::string(64, '1'))
          .has_value());
  const auto completed_bytes = read_text(
      bundle / "recovery/active/sequence.jsonl");
  const auto completed_replay = journal.append_flush(
      bundle, session_id, command_id, pattern_id, 0, events);
  LMDJ_CHECK(completed_replay.has_value());
  LMDJ_CHECK(completed_replay.value().flush_seq == first.value().flush_seq);
  LMDJ_CHECK(completed_replay.value().completed);
  LMDJ_CHECK(
      read_text(bundle / "recovery/active/sequence.jsonl") == completed_bytes);

  const auto conflicting = journal.append_flush(
      bundle,
      session_id,
      command_id,
      pattern_id,
      0,
      std::vector{event(1, 240)});
  LMDJ_CHECK(!conflicting.has_value());
  LMDJ_CHECK(conflicting.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      conflicting.error().details.at("reason") ==
      "sequence_command_conflict");
  const auto active = journal.read_active(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().flushes.size() == 1);
  LMDJ_CHECK(active.value().next_flush_seq == 1);
  LMDJ_CHECK(
      read_text(bundle / "recovery/active/sequence.jsonl") == completed_bytes);
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
  LMDJ_CHECK(first.value().committed_revision == 1);
  LMDJ_CHECK(first.value().outcome.state.revision == 1);
  LMDJ_CHECK(
      first.value().outcome.state.patterns.at(identity.pattern_id).events.size() ==
      1);
  const auto active = journal.read_active(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().flushes.at(0).completed);
  LMDJ_CHECK(
      journal.remove_active_if_complete(bundle, identity.session_id)
          .has_value());
  const auto advanced = store.execute(
      bundle,
      lmdj::domain::Command{lmdj::domain::UpdateSequenceSettings{
          {CommandId{uuid_for(99)}, 1},
          121,
          std::nullopt,
          std::nullopt,
      }});
  LMDJ_CHECK(advanced.has_value());
  LMDJ_CHECK(advanced.value().state.revision == 2);

  const auto replayed = store.replay_sequence_flush(bundle, identity);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().has_value());
  LMDJ_CHECK(replayed.value()->committed_revision == 1);
  LMDJ_CHECK(replayed.value()->outcome.replayed);
  LMDJ_CHECK(replayed.value()->outcome.state.revision == 2);
  LMDJ_CHECK(
      replayed.value()
          ->outcome
          .state
          .patterns.at(identity.pattern_id)
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

void test_later_cumulative_flush_resolves_failed_earlier_flush_exactly_once() {
  TempDirectory temp("cumulative-flush");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto pattern_id = PatternId{std::string{kPatternId}};
  const auto old_event = event(0, 0, 120, 40);
  const auto replacement = event(0, 0, 240, 90);
  const auto uncommitted = event(1, 480, 120, 70);

  LMDJ_CHECK(
      journal.append_tail(bundle, session_id, pattern_id, 0, 1,
                          std::vector{old_event}).has_value());
  const auto first = journal.append_flush(
      bundle, session_id, CommandId{uuid_for(20)}, pattern_id, 0,
      std::vector{old_event});
  LMDJ_CHECK(first.has_value());
  const SequenceFlushIdentity first_identity{
      session_id, first.value().flush_seq, CommandId{uuid_for(20)}, pattern_id};
  lmdj::foundation::Result<lmdj::project_io::SequenceFlushExecution>
      first_execution =
          lmdj::foundation::Result<
              lmdj::project_io::SequenceFlushExecution>::failure(
              lmdj::foundation::Error{
                  ErrorCode::internal_error, "fault was not run"});
  {
    FaultGuard fault(FaultPoint::sequence_transaction_write);
    first_execution = store.execute_sequence_flush(bundle, first_identity);
  }
  LMDJ_CHECK(!first_execution.has_value());
  LMDJ_CHECK(store.load(bundle).value().revision == 0);

  const auto omitted = journal.append_flush(
      bundle, session_id, CommandId{uuid_for(22)}, pattern_id, 0,
      std::vector{uncommitted});
  LMDJ_CHECK(!omitted.has_value());
  LMDJ_CHECK(omitted.error().code == ErrorCode::invalid_argument);

  LMDJ_CHECK(
      journal.append_tail(bundle, session_id, pattern_id, 0, 2,
                          std::vector{replacement}).has_value());
  const auto second = journal.append_flush(
      bundle, session_id, CommandId{uuid_for(21)}, pattern_id, 0,
      std::vector{replacement});
  LMDJ_CHECK(second.has_value());
  const SequenceFlushIdentity second_identity{
      session_id, second.value().flush_seq, CommandId{uuid_for(21)}, pattern_id};
  const auto committed = store.execute_sequence_flush(bundle, second_identity);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().outcome.state.revision == 1);
  LMDJ_CHECK(
      committed.value().outcome.state.patterns.at(pattern_id).events ==
      std::vector{replacement});

  const auto resolved = journal.read_active(bundle);
  LMDJ_CHECK(resolved.has_value());
  LMDJ_CHECK(resolved.value().flushes.size() == 2);
  LMDJ_CHECK(resolved.value().flushes.at(0).completed);
  LMDJ_CHECK(resolved.value().flushes.at(1).completed);

  LMDJ_CHECK(
      journal.append_tail(bundle, session_id, pattern_id, 1, 3,
                          std::vector{uncommitted}).has_value());
  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().journal.pending_events ==
             std::vector{uncommitted});
  LMDJ_CHECK(std::ranges::all_of(
      candidates.value().front().journal.flushes,
      [](const auto& flush) { return flush.completed; }));
}

void test_earlier_completion_resolves_all_durable_equivalent_retries() {
  TempDirectory temp("inverse-completion");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto pattern_id = PatternId{std::string{kPatternId}};
  const std::vector events{event(0, 0, 120, 90)};
  constexpr std::size_t kRetries = 32;

  for (std::size_t index = 0; index < kRetries; ++index) {
    const auto appended = journal.append_flush(
        bundle, session_id, CommandId{uuid_for(100 + index)}, pattern_id, 0,
        events);
    LMDJ_CHECK(appended.has_value());
    LMDJ_CHECK(appended.value().flush_seq == index);
  }
  const auto committed = store.execute_sequence_flush(
      bundle,
      {session_id, 0, CommandId{uuid_for(100)}, pattern_id});
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().outcome.state.revision == 1);

  const auto resolved = journal.read_active(bundle);
  LMDJ_CHECK(resolved.has_value());
  LMDJ_CHECK(resolved.value().flushes.size() == kRetries);
  LMDJ_CHECK(std::ranges::all_of(
      resolved.value().flushes,
      [](const auto& flush) { return flush.completed; }));
  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().empty());
  LMDJ_CHECK(store.load(bundle).value().revision == 1);
  LMDJ_CHECK(
      store.load(bundle).value().patterns.at(pattern_id).events == events);
}

void test_ambiguous_committed_flush_resolves_later_equivalent_retry() {
  TempDirectory temp("ambiguous-inverse-completion");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto pattern_id = PatternId{std::string{kPatternId}};
  const std::vector events{event(0, 0, 120, 90)};

  LMDJ_CHECK(
      journal.append_flush(
          bundle, session_id, CommandId{uuid_for(140)}, pattern_id, 0, events)
          .has_value());
  lmdj::foundation::Result<lmdj::project_io::SequenceFlushExecution> ambiguous =
      lmdj::foundation::Result<
          lmdj::project_io::SequenceFlushExecution>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error, "fault was not run"});
  {
    FaultGuard fault(FaultPoint::sequence_journal_completion);
    ambiguous = store.execute_sequence_flush(
        bundle,
        {session_id, 0, CommandId{uuid_for(140)}, pattern_id});
  }
  LMDJ_CHECK(!ambiguous.has_value());
  LMDJ_CHECK(store.load(bundle).value().revision == 1);
  LMDJ_CHECK(!journal.read_active(bundle).value().flushes.at(0).completed);

  const auto retry = journal.append_flush(
      bundle, session_id, CommandId{uuid_for(141)}, pattern_id, 0, events);
  LMDJ_CHECK(retry.has_value());
  LMDJ_CHECK(retry.value().flush_seq == 1);

  ProjectStore restarted;
  const auto candidates = restarted.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().empty());
  const auto no_active = journal.read_active(bundle);
  LMDJ_CHECK(!no_active.has_value());
  LMDJ_CHECK(no_active.error().code == ErrorCode::not_found);
  LMDJ_CHECK(restarted.load(bundle).value().revision == 1);
  LMDJ_CHECK(
      restarted.load(bundle).value().patterns.at(pattern_id).events == events);
}

void test_earlier_completion_preserves_only_later_uncommitted_residual() {
  TempDirectory temp("inverse-residual");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto pattern_id = PatternId{std::string{kPatternId}};
  const auto committed_event = event(0, 0, 120, 90);
  const auto superseded_event = event(1, 240, 120, 50);
  const auto later_replacement = event(1, 240, 240, 110);
  const auto additional_event = event(2, 480, 120, 70);
  const std::vector committed_batch{committed_event, superseded_event};
  const std::vector cumulative_batch{
      committed_event, later_replacement, additional_event};
  const std::vector expected_residual{later_replacement, additional_event};

  LMDJ_CHECK(
      journal
          .append_flush(
              bundle,
              session_id,
              CommandId{uuid_for(150)},
              pattern_id,
              0,
              committed_batch)
          .has_value());
  LMDJ_CHECK(
      journal.append_tail(bundle, session_id, pattern_id, 0, 1,
                          cumulative_batch).has_value());
  LMDJ_CHECK(
      journal
          .append_flush(
              bundle,
              session_id,
              CommandId{uuid_for(151)},
              pattern_id,
              0,
              cumulative_batch)
          .has_value());

  const auto committed = store.execute_sequence_flush(
      bundle,
      {session_id, 0, CommandId{uuid_for(150)}, pattern_id});
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().outcome.state.revision == 1);
  LMDJ_CHECK(
      committed.value().outcome.state.patterns.at(pattern_id).events ==
      committed_batch);

  const auto active = journal.read_active(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().flushes.at(0).completed);
  LMDJ_CHECK(!active.value().flushes.at(1).completed);
  LMDJ_CHECK(active.value().flushes.at(1).canonical_events ==
             expected_residual);

  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().journal.flushes.at(0).completed);
  LMDJ_CHECK(!candidates.value().front().journal.flushes.at(1).completed);
  LMDJ_CHECK(
      candidates.value().front().journal.flushes.at(1).canonical_events ==
      expected_residual);
  LMDJ_CHECK(store.load(bundle).value().revision == 1);
  LMDJ_CHECK(
      store.load(bundle).value().patterns.at(pattern_id).events ==
      committed_batch);
}

void test_replayed_completion_subtracts_committed_events_from_durable_tail() {
  const auto run_case = [](
                            std::string_view label,
                            const std::vector<PatternEvent>& committed_batch,
                            const std::vector<PatternEvent>& durable_tail,
                            const std::vector<PatternEvent>& expected_residual) {
    TempDirectory temp(label);
    ProjectStore store;
    const auto bundle = create_bundle(temp, store);
    SequenceJournal journal;
    begin(journal, bundle);
    const auto session_id = SequenceSessionId{std::string{kSessionId}};
    const auto pattern_id = PatternId{std::string{kPatternId}};
    const auto command_id = CommandId{uuid_for(160)};

    const auto flush = journal.append_flush(
        bundle, session_id, command_id, pattern_id, 0, committed_batch);
    LMDJ_CHECK(flush.has_value());
    {
      FaultGuard fault(FaultPoint::sequence_journal_completion);
      const auto ambiguous = store.execute_sequence_flush(
          bundle,
          {session_id, flush.value().flush_seq, command_id, pattern_id});
      LMDJ_CHECK(!ambiguous.has_value());
    }
    LMDJ_CHECK(store.load(bundle).value().revision == 1);
    LMDJ_CHECK(!journal.read_active(bundle).value().flushes.at(0).completed);
    LMDJ_CHECK(
        journal.append_tail(bundle, session_id, pattern_id, 0, 1, durable_tail)
            .has_value());

    ProjectStore restarted;
    const auto candidates = restarted.reconcile_sequence_recovery(bundle);
    LMDJ_CHECK(candidates.has_value());
    if (expected_residual.empty()) {
      LMDJ_CHECK(candidates.value().empty());
      const auto no_active = journal.read_active(bundle);
      LMDJ_CHECK(!no_active.has_value());
      LMDJ_CHECK(no_active.error().code == ErrorCode::not_found);
    } else {
      LMDJ_CHECK(candidates.value().size() == 1);
      const auto& recovered = candidates.value().front().journal;
      LMDJ_CHECK(recovered.pending_events == expected_residual);
      LMDJ_CHECK(recovered.next_tail_seq == 1);
      LMDJ_CHECK(recovered.last_input_sequence == 1);
      LMDJ_CHECK(std::ranges::all_of(
          recovered.flushes,
          [](const auto& candidate) { return candidate.completed; }));
    }
    const auto loaded = restarted.load(bundle);
    LMDJ_CHECK(loaded.has_value());
    LMDJ_CHECK(loaded.value().revision == 1);
    LMDJ_CHECK(
        loaded.value().patterns.at(pattern_id).events == committed_batch);
  };

  const auto exact = event(0, 0, 120, 90);
  const auto committed_same_key = event(1, 240, 120, 50);
  const auto replacement = event(1, 240, 240, 110);
  const auto additional = event(2, 480, 120, 70);

  run_case(
      "tail-residual-new-key",
      std::vector{exact},
      std::vector{exact, additional},
      std::vector{additional});
  run_case(
      "tail-residual-replacement",
      std::vector{exact, committed_same_key},
      std::vector{exact, replacement, additional},
      std::vector{replacement, additional});
  run_case(
      "tail-residual-equivalent",
      std::vector{exact, committed_same_key},
      std::vector{exact, committed_same_key},
      {});
}

void test_restart_reconciles_each_post_commit_fault_without_overdub() {
  constexpr std::array post_commit_faults{
      FaultPoint::sequence_receipt_reload,
      FaultPoint::sequence_journal_completion,
  };
  for (std::size_t index = 0; index < post_commit_faults.size(); ++index) {
    TempDirectory temp("reconcile-" + std::to_string(index));
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
      FaultGuard fault(post_commit_faults[index]);
      result = store.execute_sequence_flush(bundle, identity);
    }
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::io_error);
    const auto committed = store.load(bundle);
    LMDJ_CHECK(committed.has_value());
    LMDJ_CHECK(committed.value().revision == 1);
    LMDJ_CHECK(
        committed.value().patterns.at(identity.pattern_id).events.size() == 1);
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
    LMDJ_CHECK(
        reopened.value().patterns.at(identity.pattern_id).events.size() == 1);
  }
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

    if (committed) {
      const auto retried_append = journal.append_flush(
          bundle,
          identity.session_id,
          identity.command_id,
          identity.pattern_id,
          0,
          events);
      LMDJ_CHECK(retried_append.has_value());
      LMDJ_CHECK(retried_append.value().flush_seq == identity.flush_seq);
      LMDJ_CHECK(journal.read_active(bundle).value().flushes.size() == 1);
      const auto retried_execution =
          store.execute_sequence_flush(bundle, identity);
      LMDJ_CHECK(retried_execution.has_value());
      LMDJ_CHECK(retried_execution.value().outcome.replayed);
      LMDJ_CHECK(
          retried_execution.value().outcome.state.revision == 1);
    }

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
      const std::vector events{event()};
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
  const auto& first = active.value().flushes.front();
  const auto committed = store.execute_sequence_flush(
      bundle,
      {SequenceSessionId{std::string{kSessionId}},
       first.flush_seq,
       first.command_id,
       PatternId{std::string{kPatternId}}});
  LMDJ_CHECK(committed.has_value());
  const auto resolved = journal.read_active(bundle);
  LMDJ_CHECK(resolved.has_value());
  LMDJ_CHECK(std::ranges::all_of(
      resolved.value().flushes,
      [](const auto& flush) { return flush.completed; }));
  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().empty());
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
    test_later_cumulative_flush_resolves_failed_earlier_flush_exactly_once();
    test_earlier_completion_resolves_all_durable_equivalent_retries();
    test_ambiguous_committed_flush_resolves_later_equivalent_retry();
    test_earlier_completion_preserves_only_later_uncommitted_residual();
    test_replayed_completion_subtracts_committed_events_from_durable_tail();
    test_complete_line_tail_corruption_fails_closed_with_uniform_evidence();
    test_one_project_session_and_monotonic_durable_flush_identity();
    test_repeated_command_id_is_idempotent_or_rejected_before_append();
    test_writer_lease_contention_fails_before_begin();
    test_sequence_flush_commits_once_and_replays_receipt();
    test_pattern_switch_preserves_session_flush_sequence();
    test_restart_reconciles_each_post_commit_fault_without_overdub();
    test_flush_fault_matrix_has_only_recoverable_or_single_commit_outcomes();
    test_uncommitted_flush_seals_owner_lost_recovery();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
