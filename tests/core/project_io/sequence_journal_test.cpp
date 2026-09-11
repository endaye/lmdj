#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
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

void admission_candidate_reopens() {
  using namespace lmdj::project_io;
  TempDirectory directory("admission-reopen");
  ProjectStore store;
  const auto bundle = create_bundle(directory, store);
  const SequenceAdmissionPreparation preparation{
      {CommandId{std::string{kCommandId}}, 1, 1},
      ProjectId{std::string{kProjectId}}, PatternId{std::string{kPatternId}},
      1, 10};
  const SequenceAdmissionCandidate candidate{
      10, 1000, {0, 0}, SequenceCandidateKind::press, 100, 7};
  {
    SequenceJournal journal;
    begin(journal, bundle);
    const SequenceSessionId session{std::string{kSessionId}};
    LMDJ_CHECK(journal.prepare_admission(bundle, session, preparation).has_value());
    LMDJ_CHECK(journal.append_admission_candidate(
        bundle, session, preparation.identity, candidate).has_value());
  }
  const auto reopened = SequenceJournal{}.read_active(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value().admission.has_value());
  LMDJ_CHECK(reopened.value().admission->preparation == preparation);
  LMDJ_CHECK(reopened.value().admission->candidates ==
             std::vector<SequenceAdmissionCandidate>{candidate});
  LMDJ_CHECK(reopened.value().pending_events.empty());
  LMDJ_CHECK(!reopened.value().last_input_sequence.has_value());
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
             cumulative_batch);
  LMDJ_CHECK(active.value().flushes.at(1).recovery_events ==
             expected_residual);

  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().journal.flushes.at(0).completed);
  LMDJ_CHECK(!candidates.value().front().journal.flushes.at(1).completed);
  LMDJ_CHECK(
      candidates.value().front().journal.flushes.at(1).canonical_events ==
      cumulative_batch);
  LMDJ_CHECK(
      candidates.value().front().journal.flushes.at(1).recovery_events ==
      expected_residual);
  LMDJ_CHECK(store.load(bundle).value().revision == 1);
  LMDJ_CHECK(
      store.load(bundle).value().patterns.at(pattern_id).events ==
      committed_batch);
}

void test_original_flush_payload_survives_inverse_completion_residual() {
  TempDirectory temp("inverse-original-payload");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  begin(journal, bundle);
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto pattern_id = PatternId{std::string{kPatternId}};
  const auto first_command = CommandId{uuid_for(170)};
  const auto second_command = CommandId{uuid_for(171)};
  const auto committed = event(0, 0, 120, 90);
  const auto residual = event(1, 240, 120, 70);
  const auto conflicting = event(2, 480, 120, 60);
  const std::vector first_batch{committed};
  const std::vector second_batch{committed, residual};

  const auto first = journal.append_flush(
      bundle, session_id, first_command, pattern_id, 0, first_batch);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(
      journal.append_tail(bundle, session_id, pattern_id, 0, 1, second_batch)
          .has_value());
  const auto second = journal.append_flush(
      bundle, session_id, second_command, pattern_id, 0, second_batch);
  LMDJ_CHECK(second.has_value());
  const auto executed = store.execute_sequence_flush(
      bundle,
      {session_id, first.value().flush_seq, first_command, pattern_id});
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().outcome.state.revision == 1);

  const auto before_retry = read_text(
      bundle / "recovery/active/sequence.jsonl");
  const auto exact_retry = journal.append_flush(
      bundle, session_id, second_command, pattern_id, 0, second_batch);
  LMDJ_CHECK(exact_retry.has_value());
  LMDJ_CHECK(exact_retry.value().flush_seq == second.value().flush_seq);
  LMDJ_CHECK(exact_retry.value().command_id == second_command);
  LMDJ_CHECK(exact_retry.value().pattern_id == pattern_id);
  LMDJ_CHECK(exact_retry.value().expected_revision == 0);
  LMDJ_CHECK(exact_retry.value().canonical_events == second_batch);
  LMDJ_CHECK(exact_retry.value().recovery_events == std::vector{residual});
  LMDJ_CHECK(
      read_text(bundle / "recovery/active/sequence.jsonl") == before_retry);

  const auto residual_only = journal.append_flush(
      bundle,
      session_id,
      second_command,
      pattern_id,
      0,
      std::vector{residual});
  LMDJ_CHECK(!residual_only.has_value());
  LMDJ_CHECK(
      residual_only.error().details.at("reason") ==
      "sequence_command_conflict");
  const auto different = journal.append_flush(
      bundle,
      session_id,
      second_command,
      pattern_id,
      0,
      std::vector{committed, conflicting});
  LMDJ_CHECK(!different.has_value());
  LMDJ_CHECK(
      different.error().details.at("reason") ==
      "sequence_command_conflict");
  LMDJ_CHECK(
      read_text(bundle / "recovery/active/sequence.jsonl") == before_retry);

  SequenceJournal reloaded;
  const auto active = reloaded.read_active(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().flushes.size() == 2);
  LMDJ_CHECK(!active.value().flushes.at(1).completed);
  LMDJ_CHECK(active.value().flushes.at(1).canonical_events == second_batch);
  LMDJ_CHECK(
      active.value().flushes.at(1).recovery_events ==
      std::vector{residual});
  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(
      candidates.value().front().journal.flushes.at(1).canonical_events ==
      second_batch);
  LMDJ_CHECK(
      candidates.value().front().journal.flushes.at(1).recovery_events ==
      std::vector{residual});
  LMDJ_CHECK(store.load(bundle).value().revision == 1);

  const auto sealed_path = candidates.value().front().path;
  const auto original_snapshot = read_text(sealed_path);
  auto versioned = nlohmann::json::parse(original_snapshot);
  auto& encoded_flush = versioned["payload"]["journal"]["flushes"][1];
  LMDJ_CHECK(encoded_flush.at("payload_version") == 2);
  LMDJ_CHECK(encoded_flush.at("events").size() == 2);
  LMDJ_CHECK(encoded_flush.at("recovery_events").size() == 1);

  encoded_flush.erase("recovery_events");
  versioned["checksum"] = sha256(lmdj::foundation::canonical_json(
      versioned.at("payload")));
  write_text(
      sealed_path,
      lmdj::foundation::canonical_json(versioned) + "\n");
  const auto missing_v2_residual = journal.list_recoverable(bundle);
  LMDJ_CHECK(!missing_v2_residual.has_value());
  LMDJ_CHECK(missing_v2_residual.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(
      missing_v2_residual.error().details.at("reason") ==
      "sequence_recovery_payload_invalid");
  LMDJ_CHECK(
      missing_v2_residual.error().details.at("recovery_retained") == true);
  LMDJ_CHECK(
      missing_v2_residual.error().details.at("remedy").get<std::string>().find(
          "repair") !=
      std::string::npos);
  LMDJ_CHECK(
      missing_v2_residual.error().details.at("remedy").get<std::string>().find(
          "discard") !=
      std::string::npos);

  // Unsupported legacy payloads are rejected without changing retained bytes.
  auto legacy = nlohmann::json::parse(original_snapshot);
  auto& legacy_flush = legacy["payload"]["journal"]["flushes"][1];
  legacy_flush["events"] = legacy_flush.at("recovery_events");
  legacy_flush.erase("recovery_events");
  legacy_flush.erase("payload_version");
  legacy["checksum"] = sha256(lmdj::foundation::canonical_json(
      legacy.at("payload")));
  write_text(
      sealed_path,
      lmdj::foundation::canonical_json(legacy) + "\n");
  const auto legacy_candidates = journal.list_recoverable(bundle);
  LMDJ_CHECK(!legacy_candidates.has_value());
  LMDJ_CHECK(read_text(sealed_path) ==
      lmdj::foundation::canonical_json(legacy) + "\n");
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
    LMDJ_CHECK(
        active.value().flushes[index].canonical_events ==
        std::vector{event()});
    LMDJ_CHECK(
        active.value().flushes[index].recovery_events ==
        std::vector{event()});
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
  LMDJ_CHECK(std::ranges::all_of(
      resolved.value().flushes,
      [](const auto& flush) {
        return flush.canonical_events == std::vector{event()} &&
               flush.recovery_events.empty();
      }));
  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().empty());
}

// Admission fixtures use the public API and independently encode receipt preimages.
using namespace lmdj::project_io;

nlohmann::json admission_candidate_json(const SequenceAdmissionCandidate& c) {
  return {{"watermark", c.watermark}, {"runtime_frame", c.runtime_frame},
          {"slot", {{"bank", c.slot.bank}, {"pad", c.slot.pad}}},
          {"kind", static_cast<unsigned>(c.kind)}, {"velocity", c.velocity},
          {"press_sequence", c.press_sequence}};
}

struct AdmissionFixture {
  TempDirectory temp{"admission"};
  ProjectStore store;
  std::filesystem::path bundle{temp.path() / "project.lmdj"};
  SequenceJournal journal;
  SequenceSessionId session{std::string{kSessionId}};
  SequenceAdmissionPreparation preparation{
      {CommandId{std::string{kCommandId}}, 1, 1},
      ProjectId{std::string{kProjectId}}, PatternId{std::string{kPatternId}}, 1, 10};
  SequenceAdmissionCandidate press{10, 1000, {0, 0}, SequenceCandidateKind::press, 100, 7};
  explicit AdmissionFixture(bool target_pattern = false) {
    auto state = project_with_pattern();
    if (target_pattern) {
      const PatternId target{uuid_for(90)};
      state.patterns.emplace(target, Pattern{target, 1, {}});
    }
    LMDJ_CHECK(store.create(bundle, state).has_value());
    begin(journal, bundle);
  }
  auto path() const { return bundle / "recovery/active/sequence.jsonl"; }
  auto state() const { return SequenceJournal{}.read_active(bundle).value(); }
  void prepare() {
    LMDJ_CHECK(journal.prepare_admission(bundle, session, preparation).has_value());
  }
  auto candidate(const SequenceAdmissionCandidate& c) {
    return journal.append_admission_candidate(bundle, session, preparation.identity, c);
  }
  SequenceAdmissionFence fence(bool cutoff = false) const {
    return {cutoff ? SequenceFenceKind::cutoff : SequenceFenceKind::admission,
            CommandId{uuid_for(cutoff ? 92 : 91)}, cutoff ? 2U : 1U,
            cutoff ? 2000U : 900U, 0, preparation.pattern_id, 1, 120, true,
            std::nullopt, SequenceSwitchOutcome::none, std::nullopt};
  }
  void retain(bool cutoff = false) {
    LMDJ_CHECK(journal.retain_admission_fence(
        bundle, session, preparation.identity, fence(cutoff)).has_value());
  }
  void close() {
    LMDJ_CHECK(journal.close_admission(bundle, session, preparation.identity,
        {press.watermark, SequenceAdmissionCloseReason::requested}).has_value());
  }
  SequenceAdmissionTransfer transfer(bool held = true) const {
    auto array = nlohmann::json::array({admission_candidate_json(press)});
    SequenceAdmissionTransfer t{
        CommandId{uuid_for(93)}, false, press.watermark, press.watermark,
        sha256(lmdj::foundation::canonical_json(array)),
        {{press.watermark, sha256(lmdj::foundation::canonical_json(array.at(0)))}},
        preparation.pattern_id, 0, std::nullopt, {},
        {preparation.pattern_id, 900, {}}};
    if (held) {
      t.journal_input_sequence = 1;
      t.recoverable_tail = {event()};
      t.checkpoint = {preparation.pattern_id, 1000, {{{0, 0}, 7, 0, 0, 100}}};
    }
    return t;
  }
  auto transfer(const SequenceAdmissionTransfer& t) {
    return journal.transfer_admission_prefix(bundle, session, preparation.identity, t);
  }
  template <typename Operation> void rejected_unchanged(Operation operation) {
    const auto bytes = read_text(path());
    const auto before = state();
    LMDJ_CHECK(!operation().has_value());
    LMDJ_CHECK(read_text(path()) == bytes);
    LMDJ_CHECK(state() == before);
  }
  template <typename Operation> void retry_unchanged(Operation operation) {
    const auto bytes = read_text(path());
    const auto before = state();
    LMDJ_CHECK(operation().has_value());
    LMDJ_CHECK(read_text(path()) == bytes);
    LMDJ_CHECK(state() == before);
  }
};

void admission_exact_retry_and_collisions() {
  AdmissionFixture f;
  f.prepare();
  f.retry_unchanged([&] { return f.journal.prepare_admission(f.bundle, f.session, f.preparation); });
  auto changed = f.preparation;
  changed.first_watermark++;
  f.rejected_unchanged([&] { return f.journal.prepare_admission(f.bundle, f.session, changed); });
  LMDJ_CHECK(f.candidate(f.press).has_value());
  f.retry_unchanged([&] { return f.candidate(f.press); });
  auto c = f.press;
  c.velocity++;
  f.rejected_unchanged([&] { return f.candidate(c); });
  auto identity = f.preparation.identity;
  identity.runtime_generation++;
  f.rejected_unchanged([&] { return f.journal.append_admission_candidate(f.bundle, f.session, identity, f.press); });
  identity = f.preparation.identity;
  identity.transport_epoch++;
  f.rejected_unchanged([&] { return f.journal.append_admission_candidate(f.bundle, f.session, identity, f.press); });
  f.rejected_unchanged([&] { return f.journal.append_admission_candidate(f.bundle, SequenceSessionId{uuid_for(99)}, f.preparation.identity, f.press); });
}

void admission_bounds_and_integer_extremes() {
  for (unsigned which = 0; which < 8; ++which) {
    AdmissionFixture f;
    auto p = f.preparation;
    if (which == 0) p.candidate_limit = 0;
    if (which == 1) p.candidate_limit = 1025;
    if (which == 2) p.candidate_byte_limit = 0;
    if (which == 3) p.candidate_byte_limit = 1048577;
    if (which == 4) p.fence_timeout_ms = 5001;
    if (which == 5) p.identity.runtime_generation = 0;
    if (which == 6) p.project_id = ProjectId{uuid_for(99)};
    if (which == 7) p.pattern_id = PatternId{uuid_for(99)};
    f.rejected_unchanged([&] { return f.journal.prepare_admission(f.bundle, f.session, p); });
  }
  AdmissionFixture f;
  f.prepare();
  for (unsigned which = 0; which < 6; ++which) {
    auto c = f.press;
    if (which == 0) c.watermark = 9;
    if (which == 1) c.slot.bank = 4;
    if (which == 2) c.slot.pad = 16;
    if (which == 3) c.velocity = 0;
    if (which == 4) c.velocity = 128;
    if (which == 5) c.kind = SequenceCandidateKind::release;
    f.rejected_unchanged([&] { return f.candidate(c); });
  }
  LMDJ_CHECK(f.candidate(f.press).has_value());
  auto c = f.press;
  c.watermark = std::numeric_limits<std::uint64_t>::max();
  c.runtime_frame = std::numeric_limits<std::uint64_t>::max();
  LMDJ_CHECK(f.candidate(c).has_value());
  f.retry_unchanged([&] { return f.candidate(c); });
  c.watermark = 11;
  f.rejected_unchanged([&] { return f.candidate(c); });
}

void admission_final_slot_closes_atomically() {
  for (bool byte_limit : {false, true}) {
    AdmissionFixture f;
    if (byte_limit) {
      f.preparation.candidate_byte_limit = static_cast<std::uint32_t>(
          lmdj::foundation::canonical_json(admission_candidate_json(f.press)).size());
    } else {
      f.preparation.candidate_limit = 1;
    }
    f.prepare();
    const auto before = read_text(f.path());
    LMDJ_CHECK(f.candidate(f.press).has_value());
    const auto added = read_text(f.path()).substr(before.size());
    LMDJ_CHECK(std::count(added.begin(), added.end(), '\n') == 1);
    LMDJ_CHECK(f.state().admission->closure ==
        (SequenceAdmissionClosure{10, SequenceAdmissionCloseReason::capacity}));
    f.retry_unchanged([&] { return f.candidate(f.press); });
    auto next = f.press;
    next.watermark++;
    f.rejected_unchanged([&] { return f.candidate(next); });
    f.retain();
    f.retain(true);
    LMDJ_CHECK(f.transfer(f.transfer()).has_value());
  }
  AdmissionFixture f;
  f.preparation.candidate_byte_limit = 1;
  f.prepare();
  f.rejected_unchanged([&] { return f.candidate(f.press); });
  LMDJ_CHECK(f.journal.close_admission(f.bundle, f.session, f.preparation.identity,
      {std::nullopt, SequenceAdmissionCloseReason::capacity}).has_value());
  f.retain();
  f.retain(true);
}

void admission_fences_are_independent_immutable_decisions() {
  AdmissionFixture f;
  f.prepare();
  auto wrong = f.fence();
  wrong.origin_frame = wrong.effective_frame + 1;
  f.rejected_unchanged([&] { return f.journal.retain_admission_fence(f.bundle, f.session, f.preparation.identity, wrong); });
  f.retain(true);
  f.retain();
  f.retry_unchanged([&] { return f.journal.retain_admission_fence(f.bundle, f.session, f.preparation.identity, f.fence()); });
  wrong = f.fence();
  wrong.playing = false;
  f.rejected_unchanged([&] { return f.journal.retain_admission_fence(f.bundle, f.session, f.preparation.identity, wrong); });
  for (auto outcome : {SequenceSwitchOutcome::applied_before_cutoff, SequenceSwitchOutcome::canceled_at_cutoff}) {
    AdmissionFixture g;
    g.prepare();
    auto decision = g.fence(true);
    decision.switch_outcome = outcome;
    decision.switch_authority = SequencePublicationAuthority{g.preparation.pattern_id, 1, 1500};
    if (outcome == SequenceSwitchOutcome::applied_before_cutoff) decision.switch_applied_frame = 2000;
    else decision.switch_applied_frame = 1500;
    g.rejected_unchanged([&] { return g.journal.retain_admission_fence(g.bundle, g.session, g.preparation.identity, decision); });
    if (outcome == SequenceSwitchOutcome::applied_before_cutoff) decision.switch_applied_frame = 1500;
    else decision.switch_applied_frame.reset();
    LMDJ_CHECK(g.journal.retain_admission_fence(g.bundle, g.session, g.preparation.identity, decision).has_value());
    LMDJ_CHECK(g.state().admission->cutoff_fence == decision);
  }
}

void admission_transfer_requires_authority_and_replaces_once() {
  AdmissionFixture f;
  f.prepare();
  LMDJ_CHECK(f.candidate(f.press).has_value());
  auto t = f.transfer();
  f.rejected_unchanged([&] { return f.transfer(t); });
  f.retain();
  f.rejected_unchanged([&] { return f.journal.append_tail(f.bundle, f.session, f.preparation.pattern_id, 0, 1, std::vector{event()}); });
  f.rejected_unchanged([&] { return f.journal.append_flush(f.bundle, f.session, CommandId{uuid_for(98)}, f.preparation.pattern_id, 0, std::vector{event()}); });
  for (unsigned which = 0; which < 5; ++which) {
    auto bad = t;
    if (which == 0) bad.candidates_sha256[0] = 'x';
    if (which == 1) bad.candidate_receipts[0].payload_sha256[0] = 'x';
    if (which == 2) bad.expected_revision++;
    if (which == 3) bad.checkpoint.owned_presses.push_back(bad.checkpoint.owned_presses.front());
    if (which == 4) bad.recoverable_tail.front().duration_tick = 0;
    f.rejected_unchanged([&] { return f.transfer(bad); });
  }
  LMDJ_CHECK(f.transfer(t).has_value());
  LMDJ_CHECK(f.state().pending_events == std::vector{event()});
  LMDJ_CHECK(f.state().admission->candidates.empty());
  LMDJ_CHECK(f.state().admission->transfers.back() == t);
  f.retry_unchanged([&] { return f.transfer(t); });
  f.retry_unchanged([&] { return f.candidate(f.press); });
  auto collision = f.press;
  collision.press_sequence++;
  f.rejected_unchanged([&] { return f.candidate(collision); });
  t.checkpoint.last_runtime_frame++;
  f.rejected_unchanged([&] { return f.transfer(t); });
}

void admission_excluded_prefix_preserves_sequence_and_checkpoint() {
  AdmissionFixture f;
  f.press.runtime_frame = 800; // Before the admission fence at frame 900.
  f.prepare();
  f.retain();
  LMDJ_CHECK(f.candidate(f.press).has_value());
  auto t = f.transfer(false);
  auto changed = t;
  changed.checkpoint.last_runtime_frame++;
  f.rejected_unchanged([&] { return f.transfer(changed); });
  LMDJ_CHECK(f.transfer(t).has_value());
  LMDJ_CHECK(!f.state().last_input_sequence.has_value());
  LMDJ_CHECK(f.state().pending_events.empty());
  LMDJ_CHECK(f.state().admission->candidates.empty());
  f.retry_unchanged([&] { return f.transfer(t); });
}

void admission_held_press_terminal_reopens_flushes_and_completes() {
  AdmissionFixture f;
  f.prepare();
  f.retain();
  LMDJ_CHECK(f.candidate(f.press).has_value());
  const auto held = f.transfer();
  LMDJ_CHECK(f.transfer(held).has_value());
  auto terminal = held;
  terminal.transfer_id = CommandId{uuid_for(94)};
  terminal.terminal = true;
  terminal.first_watermark = terminal.last_watermark = 0;
  terminal.candidate_receipts.clear();
  terminal.candidates_sha256 = sha256("[]");
  terminal.journal_input_sequence.reset();
  terminal.checkpoint.owned_presses.clear();
  terminal.checkpoint.last_runtime_frame = 2000;
  f.rejected_unchanged([&] { return f.transfer(terminal); });
  f.retain(true);
  f.close();
  f.rejected_unchanged([&] { return f.journal.complete_admission(f.bundle, f.session, f.preparation.identity); });
  LMDJ_CHECK(f.transfer(terminal).has_value());
  const auto reopened = SequenceJournal{}.read_active(f.bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value().admission->transfers.back() == terminal);
  LMDJ_CHECK(reopened.value().pending_events == std::vector{event()});
  LMDJ_CHECK(reopened.value().last_input_sequence == 1);
  f.retry_unchanged([&] { return f.transfer(terminal); });
  auto new_terminal = terminal;
  new_terminal.transfer_id = CommandId{uuid_for(95)};
  f.rejected_unchanged([&] { return f.transfer(new_terminal); });
  f.rejected_unchanged([&] { return f.journal.complete_admission(f.bundle, f.session, f.preparation.identity); });
  const CommandId command{uuid_for(96)};
  const auto flush = f.journal.append_flush(f.bundle, f.session, command,
      f.preparation.pattern_id, 0, terminal.recoverable_tail);
  LMDJ_CHECK(flush.has_value());
  LMDJ_CHECK(f.store.execute_sequence_flush(f.bundle,
      {f.session, flush.value().flush_seq, command, f.preparation.pattern_id}).has_value());
  f.retry_unchanged([&] { return f.transfer(terminal); });
  f.retry_unchanged([&] { return f.transfer(held); });
  LMDJ_CHECK(f.journal.complete_admission(f.bundle, f.session, f.preparation.identity).has_value());
  f.retry_unchanged([&] { return f.journal.complete_admission(f.bundle, f.session, f.preparation.identity); });
  LMDJ_CHECK(f.state().admission->completed);
  LMDJ_CHECK(f.state().last_input_sequence == 1);
  LMDJ_CHECK(f.store.load(f.bundle).value().patterns.at(f.preparation.pattern_id).events == std::vector{event()});
  auto expected = f.state();
  expected.state = SequenceSessionState::owner_lost;
  LMDJ_CHECK(f.journal.seal(f.bundle, f.session, "owner_lost").has_value());
  const auto sealed = f.journal.list_recoverable(f.bundle);
  LMDJ_CHECK(sealed.has_value());
  LMDJ_CHECK(sealed.value().size() == 1);
  LMDJ_CHECK(sealed.value().front().journal == expected);
}

void admission_torn_records_and_write_failures_preserve_bytes() {
  for (unsigned which = 0; which < 3; ++which) {
    AdmissionFixture f;
    f.prepare();
    if (which == 2) { LMDJ_CHECK(f.candidate(f.press).has_value()); f.retain(); }
    auto operation = [&]() {
      if (which == 0) return f.candidate(f.press);
      if (which == 1) return f.journal.retain_admission_fence(f.bundle, f.session, f.preparation.identity, f.fence());
      return f.transfer(f.transfer());
    };
    { FaultGuard fault(FaultPoint::sequence_journal_write); f.rejected_unchanged(operation); }
    const auto prefix = read_text(f.path());
    LMDJ_CHECK(operation().has_value());
    const auto full = read_text(f.path());
    f.retry_unchanged(operation); // Durable append, lost response, new reader.
    const auto torn = full.substr(0, full.size() - 3);
    write_text(f.path(), torn);
    const auto read = SequenceJournal{}.read_active(f.bundle);
    LMDJ_CHECK(!read.has_value());
    LMDJ_CHECK(read.error().details.at("durable_prefix_length") == prefix.size());
    LMDJ_CHECK(!operation().has_value());
    LMDJ_CHECK(read_text(f.path()) == torn);
  }
}

void admission_empty_pending_owner_loss_is_not_removed() {
  AdmissionFixture f;
  const CommandId command{uuid_for(97)};
  const auto flush = f.journal.append_flush(f.bundle, f.session, command,
      f.preparation.pattern_id, 0, std::vector{event()});
  LMDJ_CHECK(flush.has_value());
  LMDJ_CHECK(f.store.execute_sequence_flush(f.bundle,
      {f.session, flush.value().flush_seq, command, f.preparation.pattern_id}).has_value());
  f.prepare();
  LMDJ_CHECK(f.state().pending_events.empty());
  f.rejected_unchanged([&] { return f.journal.remove_active_if_complete(f.bundle, f.session); });
  const auto recovery = f.store.reconcile_sequence_recovery(f.bundle);
  LMDJ_CHECK(recovery.has_value());
  LMDJ_CHECK(recovery.value().size() == 1);
  LMDJ_CHECK(recovery.value().front().journal.admission->preparation == f.preparation);
  LMDJ_CHECK(!recovery.value().front().journal.admission->completed);
  LMDJ_CHECK(!recovery.value().front().journal.admission->admission_fence.has_value());
}

void admission_unsupported_formats_are_retained() {
  for (bool sealed : {false, true}) {
    for (std::string_view contract : {"v1", "v99"}) {
      AdmissionFixture f;
      f.prepare();
      LMDJ_CHECK(f.candidate(f.press).has_value());
      auto path = f.path();
      if (sealed) {
        const auto result = f.journal.seal(f.bundle, f.session, "owner_lost");
        LMDJ_CHECK(result.has_value());
        path = result.value();
      }
      const auto original = read_text(path);
      const auto end = original.find('\n');
      auto envelope = nlohmann::json::parse(original.substr(0, end));
      envelope["payload"]["contract"] =
          std::string{sealed ? "lmdj.sequence.recovery." : "lmdj.sequence.journal."} + std::string{contract};
      envelope["checksum"] = sha256(lmdj::foundation::canonical_json(envelope.at("payload")));
      const auto changed = lmdj::foundation::canonical_json(envelope) + original.substr(end);
      write_text(path, changed);
      if (sealed) LMDJ_CHECK(!f.journal.list_recoverable(f.bundle).has_value());
      else {
        LMDJ_CHECK(!f.journal.read_active(f.bundle).has_value());
        LMDJ_CHECK(!f.candidate(f.press).has_value());
        LMDJ_CHECK(!f.store.reconcile_sequence_recovery(f.bundle).has_value());
      }
      LMDJ_CHECK(read_text(path) == changed);
    }
  }
}

void admission_unknown_sync_requires_durable_retry() {
  for (unsigned which = 0; which < 3; ++which) {
    AdmissionFixture f;
    f.prepare();
    if (which == 2) { LMDJ_CHECK(f.candidate(f.press).has_value()); f.retain(); }
    auto operation = [&]() {
      if (which == 0) return f.candidate(f.press);
      if (which == 1) return f.journal.retain_admission_fence(f.bundle, f.session, f.preparation.identity, f.fence());
      return f.transfer(f.transfer());
    };
    const auto prefix = read_text(f.path());
    {
      FaultGuard fault(FaultPoint::active_journal_sync);
      LMDJ_CHECK(!operation().has_value());
      LMDJ_CHECK(read_text(f.path()).size() > prefix.size());
      // Readable bytes after write-before-fsync do not establish durability.
      // Retry must finish the sync, and remain unknown while that still fails.
      f.rejected_unchanged(operation);
    }
    f.retry_unchanged(operation);
    if (which == 2) {
      LMDJ_CHECK(f.state().pending_events == std::vector{event()});
      LMDJ_CHECK(f.state().admission->transfers.size() == 1);
    }
  }
}

void admission_hard_count_and_transfer_byte_bounds() {
  AdmissionFixture f;
  f.prepare();
  // A checksummed durable prefix avoids 1023 unrelated filesystem syncs while
  // exercising the real replay and final-slot append against the hard cap.
  auto bytes = read_text(f.path());
  for (std::uint64_t i = 0; i < 1023; ++i) {
    auto c = f.press;
    c.watermark += i;
    const nlohmann::json payload{
        {"kind", "admission-candidate"}, {"session_id", kSessionId},
        {"identity", {{"operation_id", kCommandId}, {"runtime_generation", 1}, {"transport_epoch", 1}}},
        {"data", admission_candidate_json(c)}};
    bytes += lmdj::foundation::canonical_json(nlohmann::json{
        {"payload", payload}, {"checksum", sha256(lmdj::foundation::canonical_json(payload))}}) + "\n";
  }
  write_text(f.path(), bytes);
  auto last = f.press;
  last.watermark += 1023;
  LMDJ_CHECK(f.candidate(last).has_value());
  LMDJ_CHECK(f.state().admission->candidates.size() == 1024);
  LMDJ_CHECK(f.state().admission->closure ==
      (SequenceAdmissionClosure{1033, SequenceAdmissionCloseReason::capacity}));
  ++last.watermark;
  f.rejected_unchanged([&] { return f.candidate(last); });

  AdmissionFixture g;
  g.prepare();
  g.retain();
  LMDJ_CHECK(g.candidate(g.press).has_value());
  auto oversized = g.transfer();
  oversized.recoverable_tail.clear();
  for (std::uint32_t tick = 0; tick < 300; ++tick) {
    for (std::uint8_t slot = 0; slot < 64; ++slot) {
      oversized.recoverable_tail.push_back({{static_cast<std::uint8_t>(slot / 16),
          static_cast<std::uint8_t>(slot % 16)}, tick, 1, 100});
    }
  }
  oversized.recoverable_tail = lmdj::domain::merge_pattern_events({}, oversized.recoverable_tail);
  g.rejected_unchanged([&] { return g.transfer(oversized); });
}

void admission_corrupt_integer_and_snapshot_fields_fail_closed() {
  for (const auto& invalid : {nlohmann::json(-1), nlohmann::json(256), nlohmann::json(1.5)}) {
    AdmissionFixture f;
    f.prepare();
    LMDJ_CHECK(f.candidate(f.press).has_value());
    rewrite_last_record(f.path(), [&](auto& envelope) {
      envelope["payload"]["data"]["velocity"] = invalid;
      envelope["checksum"] = sha256(lmdj::foundation::canonical_json(envelope.at("payload")));
    });
    const auto bytes = read_text(f.path());
    LMDJ_CHECK(!f.journal.read_active(f.bundle).has_value());
    LMDJ_CHECK(!f.candidate(f.press).has_value());
    LMDJ_CHECK(read_text(f.path()) == bytes);
  }
  for (const auto* field : {"admission", "next_tail_seq", "pending_events", "capture_commit", "armed_capture_slot"}) {
    AdmissionFixture f;
    f.prepare();
    const auto sealed = f.journal.seal(f.bundle, f.session, "owner_lost");
    LMDJ_CHECK(sealed.has_value());
    rewrite_last_record(sealed.value(), [&](auto& envelope) {
      envelope["payload"]["journal"].erase(field);
      envelope["checksum"] = sha256(lmdj::foundation::canonical_json(envelope.at("payload")));
    });
    const auto bytes = read_text(sealed.value());
    LMDJ_CHECK(!f.journal.list_recoverable(f.bundle).has_value());
    LMDJ_CHECK(read_text(sealed.value()) == bytes);
  }
}

void sequence_new_snapshot_rejects_wrong_field_types() {
  for (bool bad_bars : {false, true}) {
    AdmissionFixture f;
    f.prepare();
    const auto sealed = f.journal.seal(f.bundle, f.session, "owner_lost");
    LMDJ_CHECK(sealed.has_value());
    rewrite_last_record(sealed.value(), [&](auto& envelope) {
      if (bad_bars) envelope["payload"]["journal"]["bars"] = 257;
      else envelope["payload"]["journal"]["pending_events"] = nullptr;
      envelope["checksum"] = sha256(lmdj::foundation::canonical_json(envelope.at("payload")));
    });
    const auto bytes = read_text(sealed.value());
    LMDJ_CHECK(!f.journal.list_recoverable(f.bundle).has_value());
    LMDJ_CHECK(read_text(sealed.value()) == bytes);
  }
}

void admission_switch_drains_source_before_target_exclusion() {
  AdmissionFixture f(true);
  f.prepare();
  f.retain();
  LMDJ_CHECK(f.candidate(f.press).has_value());
  const auto held = f.transfer();
  auto excluded = f.press;
  excluded.watermark = 11;
  excluded.runtime_frame = 1600;
  excluded.kind = SequenceCandidateKind::release;
  excluded.velocity = 0;
  excluded.press_sequence = 0;
  LMDJ_CHECK(f.candidate(excluded).has_value());
  const PatternId target{uuid_for(90)};
  auto cutoff = f.fence(true);
  cutoff.pattern_id = target;
  cutoff.publication_generation = 2;
  cutoff.origin_frame = 1500;
  cutoff.switch_authority = SequencePublicationAuthority{target, 2, 1500};
  cutoff.switch_outcome = SequenceSwitchOutcome::applied_before_cutoff;
  cutoff.switch_applied_frame = 1500;
  LMDJ_CHECK(f.journal.retain_admission_fence(f.bundle, f.session, f.preparation.identity, cutoff).has_value());
  LMDJ_CHECK(f.journal.close_admission(f.bundle, f.session, f.preparation.identity,
      {11, SequenceAdmissionCloseReason::requested}).has_value());
  const Pattern target_value{target, 1, {}};
  const auto target_fingerprint = sequence_pattern_fingerprint(target_value);
  f.rejected_unchanged([&] { return f.journal.switch_pattern(f.bundle, f.session, target, 1, target_fingerprint, 0); });
  LMDJ_CHECK(f.transfer(held).has_value());
  const CommandId command{uuid_for(96)};
  const auto flush = f.journal.append_flush(f.bundle, f.session, command,
      f.preparation.pattern_id, 0, held.recoverable_tail);
  LMDJ_CHECK(flush.has_value());
  LMDJ_CHECK(f.store.execute_sequence_flush(f.bundle,
      {f.session, flush.value().flush_seq, command, f.preparation.pattern_id}).has_value());
  LMDJ_CHECK(f.state().admission->candidates == std::vector{excluded});
  LMDJ_CHECK(f.journal.switch_pattern(f.bundle, f.session, target, 1, target_fingerprint, 1).has_value());
  f.press = excluded;
  auto transfer = f.transfer(false);
  transfer.transfer_id = CommandId{uuid_for(97)};
  transfer.pattern_id = target;
  transfer.expected_revision = 1;
  transfer.checkpoint = {target, 1500, {}};
  LMDJ_CHECK(f.transfer(transfer).has_value());
  LMDJ_CHECK(f.state().pending_events.empty());
  LMDJ_CHECK(f.state().last_input_sequence == 1);
  LMDJ_CHECK(f.state().admission->candidates.empty());
  LMDJ_CHECK(f.state().admission->transfers.back() == transfer);
  const auto truth = f.store.load(f.bundle);
  LMDJ_CHECK(truth.has_value());
  LMDJ_CHECK(truth.value().patterns.at(f.preparation.pattern_id).events == held.recoverable_tail);
  LMDJ_CHECK(truth.value().patterns.at(target).events.empty());
}

void sequence_snapshot_requires_flush_record_grammar() {
  for (const auto* field : {"kind", "events", "recovery_events"}) {
    AdmissionFixture f;
    const auto flush = f.journal.append_flush(f.bundle, f.session, CommandId{uuid_for(99)},
        f.preparation.pattern_id, 0, std::vector{event()});
    LMDJ_CHECK(flush.has_value());
    const auto sealed = f.journal.seal(f.bundle, f.session, "owner_lost");
    LMDJ_CHECK(sealed.has_value());
    rewrite_last_record(sealed.value(), [&](auto& envelope) {
      auto& record = envelope["payload"]["journal"]["flushes"][0];
      if (std::string_view{field} == "kind") record.erase(field);
      else record[field] = nlohmann::json{{"event", record.at(field).at(0)}};
      envelope["checksum"] = sha256(lmdj::foundation::canonical_json(envelope.at("payload")));
    });
    const auto bytes = read_text(sealed.value());
    LMDJ_CHECK(!f.journal.list_recoverable(f.bundle).has_value());
    LMDJ_CHECK(read_text(sealed.value()) == bytes);
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
    admission_candidate_reopens();
    admission_exact_retry_and_collisions();
    admission_bounds_and_integer_extremes();
    admission_final_slot_closes_atomically();
    admission_fences_are_independent_immutable_decisions();
    admission_transfer_requires_authority_and_replaces_once();
    admission_excluded_prefix_preserves_sequence_and_checkpoint();
    admission_held_press_terminal_reopens_flushes_and_completes();
    admission_torn_records_and_write_failures_preserve_bytes();
    admission_empty_pending_owner_loss_is_not_removed();
    admission_unsupported_formats_are_retained();
    admission_unknown_sync_requires_durable_retry();
    admission_hard_count_and_transfer_byte_bounds();
    admission_corrupt_integer_and_snapshot_fields_fail_closed();
    sequence_new_snapshot_rejects_wrong_field_types();
    admission_switch_drains_source_before_target_exclusion();
    sequence_snapshot_requires_flush_record_grammar();
    test_durable_tail_snapshots_survive_reload_and_are_consumed_by_flush();
    test_torn_tail_fails_closed_with_actionable_recovery_evidence();
    test_later_cumulative_flush_resolves_failed_earlier_flush_exactly_once();
    test_earlier_completion_resolves_all_durable_equivalent_retries();
    test_ambiguous_committed_flush_resolves_later_equivalent_retry();
    test_earlier_completion_preserves_only_later_uncommitted_residual();
    test_original_flush_payload_survives_inverse_completion_residual();
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
