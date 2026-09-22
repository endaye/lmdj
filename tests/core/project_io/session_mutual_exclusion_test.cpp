#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <thread>
#include <vector>
#include <picosha2.h>
#include <lmdj/foundation/json.hpp>

#include <lmdj/domain/project.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "tests/core/support/legacy_project.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::Performance;
using lmdj::domain::PerformanceId;
using lmdj::domain::PadSlotId;
using lmdj::domain::PatternEvent;
using lmdj::domain::ProjectContract;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::SequenceJournal;
using lmdj::project_io::SequenceFlushIdentity;
using lmdj::project_io::SessionKind;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kPatternId =
    "10000000-0000-4000-8000-000000000001";
constexpr std::string_view kPerformanceId =
    "10000000-0000-4000-8000-000000000002";
constexpr std::string_view kSequenceSessionId =
    "20000000-0000-4000-8000-000000000001";
constexpr std::string_view kPerformanceSessionId =
    "20000000-0000-4000-8000-000000000002";
constexpr std::string_view kCommandId =
    "30000000-0000-4000-8000-000000000001";
constexpr std::string_view kSecondPerformanceId =
    "10000000-0000-4000-8000-000000000003";
constexpr std::string_view kSecondPerformanceSessionId =
    "20000000-0000-4000-8000-000000000003";
constexpr std::string_view kSecondCommandId =
    "30000000-0000-4000-8000-000000000002";

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce = std::chrono::steady_clock::now()
                           .time_since_epoch()
                           .count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-session-exclusion-" + std::to_string(nonce));
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

// Yield to a competing begin after the real native writer lease is released.
class ReleaseCallbackPlatform final : public lmdj::project_io::ProjectStoragePlatform {
 public:
  explicit ReleaseCallbackPlatform(
      std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> delegate)
      : delegate_(std::move(delegate)) {}

  lmdj::foundation::Result<std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& path) override {
    auto acquired = delegate_->acquire_writer(path);
    if (!acquired.has_value()) {
      return acquired;
    }
    struct Lease final : lmdj::project_io::ProjectWriterLease {
      Lease(std::unique_ptr<lmdj::project_io::ProjectWriterLease> inner,
            std::function<void()>& callback)
          : inner_(std::move(inner)), callback_(callback) {}
      ~Lease() override {
        inner_.reset();
        if (callback_) {
          callback_();
        }
      }
      std::unique_ptr<lmdj::project_io::ProjectWriterLease> inner_;
      std::function<void()>& callback_;
    };
    return decltype(acquired)::success(
        std::make_unique<Lease>(std::move(acquired.value()), after_release));
  }
  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    return delegate_->ensure_directory(path);
  }
  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    return delegate_->exists(path);
  }
  lmdj::foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const override {
    return delegate_->directory_exists(path);
  }
  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    return delegate_->byte_length(path);
  }
  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    return delegate_->read_complete(path);
  }
  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return delegate_->create_immutable(path, bytes);
  }
  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return delegate_->replace_complete(path, bytes);
  }
  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> bytes) override {
    return delegate_->append_durable(path, valid_prefix_length, bytes);
  }
  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    return delegate_->remove(path);
  }
  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    return delegate_->list_names(path);
  }
  lmdj::foundation::Result<std::vector<std::string>> list_directories(
      const std::filesystem::path& path) const override {
    return delegate_->list_directories(path);
  }
  lmdj::foundation::Result<void> remove_tree(
      const std::filesystem::path& path) override {
    return delegate_->remove_tree(path);
  }
  lmdj::foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path& source,
      const std::filesystem::path& destination) override {
    return delegate_->publish_directory_if_absent(source, destination);
  }
  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& path) const override {
    return delegate_->validate_managed_tree(path);
  }

  std::function<void()> after_release;

 private:
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> delegate_;
};

Performance performance() {
  return {
      PerformanceId{std::string{kPerformanceId}},
      "Live set",
      120,
      0,
      std::nullopt,
      {},
  };
}

lmdj::domain::ProjectState project() {
  auto created = lmdj::domain::create_project(
      ProjectId{std::string{kProjectId}}, 120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  state.contract = ProjectContract::v4;
  lmdj::domain::Pattern pattern{
      PatternId{std::string{kPatternId}}, 1, {}};
  state.patterns.emplace(pattern.id, pattern);
  auto live = performance();
  state.performances.emplace(live.id, live);
  return state;
}

lmdj::domain::ProjectState empty_v4_project() {
  auto state = project();
  state.patterns.clear();
  state.performances.clear();
  return state;
}

std::string read_text(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  return {
      std::istreambuf_iterator<char>{stream},
      std::istreambuf_iterator<char>{},
  };
}

void expect_active_conflict(
    const lmdj::foundation::Result<void>& result,
    std::string_view active_kind) {
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(result.error().details.at("reason") ==
             "recording_session_active");
  LMDJ_CHECK(result.error().details.at("session_kind") == active_kind);
}

void test_sequence_and_performance_are_mutually_exclusive() {
  TempDirectory temp;
  ProjectStore store;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, project()).has_value());
  SequenceJournal journal;
  const lmdj::domain::Pattern pattern{
      PatternId{std::string{kPatternId}}, 1, {}};
  const auto live = performance();

  LMDJ_CHECK(
      journal
          .begin(
              bundle,
              SequenceSessionId{std::string{kSequenceSessionId}},
              pattern.id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              0)
          .has_value());
  expect_active_conflict(
      journal.begin_performance(
          bundle,
          SequenceSessionId{std::string{kPerformanceSessionId}},
          live.id,
          lmdj::project_io::performance_fingerprint(live),
          0),
      "sequence");
  LMDJ_CHECK(
      journal
          .remove_active_if_complete(
              bundle,
              SequenceSessionId{std::string{kSequenceSessionId}})
          .has_value());

  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              SequenceSessionId{std::string{kPerformanceSessionId}},
              live.id,
              lmdj::project_io::performance_fingerprint(live),
              0)
          .has_value());
  expect_active_conflict(
      journal.begin(
          bundle,
          SequenceSessionId{std::string{kSequenceSessionId}},
          pattern.id,
          pattern.bars,
          lmdj::project_io::sequence_pattern_fingerprint(pattern),
          0),
      "performance");
}

void test_begin_validates_revision_under_admission_lease() {
  TempDirectory temp;
  ProjectStore store;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, project()).has_value());
  SequenceJournal journal;
  const auto live = performance();
  const auto rejected = journal.begin_performance(
      bundle,
      SequenceSessionId{std::string{kPerformanceSessionId}},
      live.id,
      lmdj::project_io::performance_fingerprint(live),
      7);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::revision_conflict);
  LMDJ_CHECK(
      !std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
}

void test_v3_project_uses_current_sequence_journal_format() {
  TempDirectory temp;
  ProjectStore store;
  auto state = project();
  state.performances.clear();
  const auto bundle = temp.path() / "legacy.lmdj";
  LMDJ_CHECK(store.create(bundle, state).has_value());
  lmdj::test::make_v3_bundle_on_disk(store, bundle);
  SequenceJournal journal;
  LMDJ_CHECK(
      journal
          .begin(
              bundle,
              SequenceSessionId{std::string{kSequenceSessionId}},
              PatternId{std::string{kPatternId}},
              1,
              std::string(64, '0'),
              0)
          .has_value());
  const nlohmann::json payload{
      {"armed_capture_slot", nullptr}, {"bars", 1},
      {"contract", "lmdj.sequence.journal.v3"}, {"expected_revision", 0},
      {"kind", "begin"}, {"pattern_fingerprint", std::string(64, '0')},
      {"pattern_id", kPatternId}, {"session_id", kSequenceSessionId}};
  const auto checksum = picosha2::hash256_hex_string(
      lmdj::foundation::canonical_json(payload));
  const auto expected = lmdj::foundation::canonical_json(
      nlohmann::json{{"checksum", checksum}, {"payload", payload}}) + "\n";
  LMDJ_CHECK(
      read_text(bundle / "recovery/active/sequence.jsonl") == expected);
  const auto loaded = journal.read_active(bundle);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value().session_id.value() == kSequenceSessionId);
}

void test_performance_recovery_does_not_poison_sequence_listing() {
  TempDirectory temp;
  ProjectStore store;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, project()).has_value());
  SequenceJournal journal;
  const auto live = performance();
  const auto session_id =
      SequenceSessionId{std::string{kPerformanceSessionId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              live.id,
              lmdj::project_io::performance_fingerprint(live),
              0)
          .has_value());
  LMDJ_CHECK(
      journal.seal_performance(bundle, session_id, "owner_lost")
          .has_value());

  const auto sequence_candidates = journal.list_recoverable(bundle);
  LMDJ_CHECK(sequence_candidates.has_value());
  LMDJ_CHECK(sequence_candidates.value().empty());
}

void test_same_kind_second_begin_prioritizes_active_session() {
  TempDirectory temp;
  ProjectStore store;
  auto state = project();
  state.performances.clear();
  const auto bundle = temp.path() / "legacy.lmdj";
  LMDJ_CHECK(store.create(bundle, state).has_value());
  lmdj::test::make_v3_bundle_on_disk(store, bundle);
  SequenceJournal journal;
  const lmdj::domain::Pattern pattern{
      PatternId{std::string{kPatternId}}, 1, {}};
  const auto session_id = SequenceSessionId{std::string{kSequenceSessionId}};
  const auto command_id = CommandId{std::string{kCommandId}};
  LMDJ_CHECK(
      journal
          .begin(
              bundle,
              session_id,
              pattern.id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              0)
          .has_value());
  const std::vector events{
      PatternEvent{PadSlotId{0, 0}, 0, 240, 100}};
  const auto flush = journal.append_flush(
      bundle, session_id, command_id, pattern.id, 0, events);
  LMDJ_CHECK(flush.has_value());
  LMDJ_CHECK(
      store
          .execute_sequence_flush(
              bundle,
              SequenceFlushIdentity{
                  session_id, flush.value().flush_seq, command_id, pattern.id})
          .has_value());

  const auto second = journal.begin(
      bundle,
      SequenceSessionId{std::string{kPerformanceSessionId}},
      pattern.id,
      pattern.bars,
      lmdj::project_io::sequence_pattern_fingerprint(pattern),
      0);
  LMDJ_CHECK(!second.has_value());
  LMDJ_CHECK(second.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(second.error().details.at("reason") ==
             "sequence_session_active");
  LMDJ_CHECK(second.error().details.at("session_kind") == "sequence");
}

void test_concurrent_sequence_begins_admit_only_one_session() {
  TempDirectory temp;
  ProjectStore store;
  auto state = project();
  state.performances.clear();
  const auto bundle = temp.path() / "legacy.lmdj";
  LMDJ_CHECK(store.create(bundle, state).has_value());
  lmdj::test::make_v3_bundle_on_disk(store, bundle);
  const lmdj::domain::Pattern pattern{
      PatternId{std::string{kPatternId}}, 1, {}};
  const auto fingerprint =
      lmdj::project_io::sequence_pattern_fingerprint(pattern);
  std::atomic<int> ready{};
  std::atomic<bool> start{};
  std::optional<lmdj::foundation::Result<void>> first;
  std::optional<lmdj::foundation::Result<void>> second;
  const auto contend = [&](std::string_view id) {
    SequenceJournal journal;
    ready.fetch_add(1, std::memory_order_release);
    while (!start.load(std::memory_order_acquire)) {
      std::this_thread::yield();
    }
    return journal.begin(
        bundle,
        SequenceSessionId{std::string{id}},
        pattern.id,
        pattern.bars,
        fingerprint,
        0);
  };
  std::thread first_thread([&] { first = contend(kSequenceSessionId); });
  std::thread second_thread([&] { second = contend(kPerformanceSessionId); });
  while (ready.load(std::memory_order_acquire) != 2) {
    std::this_thread::yield();
  }
  start.store(true, std::memory_order_release);
  first_thread.join();
  second_thread.join();

  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(first->has_value() != second->has_value());
  const auto& rejected = first->has_value() ? *second : *first;
  LMDJ_CHECK(
      rejected.error().code == ErrorCode::invalid_argument ||
      rejected.error().code == ErrorCode::io_error);
  if (rejected.error().code == ErrorCode::invalid_argument) {
    LMDJ_CHECK(rejected.error().details.at("reason") ==
               "sequence_session_active");
    LMDJ_CHECK(rejected.error().details.at("session_kind") == "sequence");
  } else {
    LMDJ_CHECK(rejected.error().details.at("storage_condition") ==
               "project_busy");
  }
}

void test_concurrent_sequence_and_performance_begins_admit_only_one_kind() {
  TempDirectory temp;
  ProjectStore store;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, project()).has_value());
  const lmdj::domain::Pattern pattern{
      PatternId{std::string{kPatternId}}, 1, {}};
  const auto live = performance();
  std::atomic<int> ready{};
  std::atomic<bool> start{};
  std::optional<lmdj::foundation::Result<void>> sequence_result;
  std::optional<lmdj::foundation::Result<void>> performance_result;

  std::thread sequence_thread([&] {
    SequenceJournal journal;
    ready.fetch_add(1, std::memory_order_release);
    while (!start.load(std::memory_order_acquire)) {
      std::this_thread::yield();
    }
    sequence_result = journal.begin(
        bundle,
        SequenceSessionId{std::string{kSequenceSessionId}},
        pattern.id,
        pattern.bars,
        lmdj::project_io::sequence_pattern_fingerprint(pattern),
        0);
  });
  std::thread performance_thread([&] {
    SequenceJournal journal;
    ready.fetch_add(1, std::memory_order_release);
    while (!start.load(std::memory_order_acquire)) {
      std::this_thread::yield();
    }
    performance_result = journal.begin_performance(
        bundle,
        SequenceSessionId{std::string{kPerformanceSessionId}},
        live.id,
        lmdj::project_io::performance_fingerprint(live),
        0);
  });
  while (ready.load(std::memory_order_acquire) != 2) {
    std::this_thread::yield();
  }
  start.store(true, std::memory_order_release);
  sequence_thread.join();
  performance_thread.join();

  LMDJ_CHECK(sequence_result.has_value());
  LMDJ_CHECK(performance_result.has_value());
  LMDJ_CHECK(
      sequence_result->has_value() != performance_result->has_value());
  const auto& rejected = sequence_result->has_value()
                             ? *performance_result
                             : *sequence_result;
  LMDJ_CHECK(
      rejected.error().code == ErrorCode::invalid_argument ||
      rejected.error().code == ErrorCode::io_error);
  if (rejected.error().code == ErrorCode::invalid_argument) {
    LMDJ_CHECK(rejected.error().details.at("reason") ==
               "recording_session_active");
  } else {
    LMDJ_CHECK(rejected.error().details.at("storage_condition") ==
               "project_busy");
  }
  LMDJ_CHECK(
      std::filesystem::exists(bundle / "recovery/active/sequence.jsonl") !=
      std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
}

void test_legacy_v3_sequence_tail_flush_completion_and_seal_reconcile() {
  TempDirectory temp;
  ProjectStore store;
  auto state = project();
  state.performances.clear();
  const auto bundle = temp.path() / "legacy.lmdj";
  LMDJ_CHECK(store.create(bundle, state).has_value());
  lmdj::test::make_v3_bundle_on_disk(store, bundle);
  SequenceJournal journal;
  const lmdj::domain::Pattern pattern{
      PatternId{std::string{kPatternId}}, 1, {}};
  const auto session_id = SequenceSessionId{std::string{kSequenceSessionId}};
  const auto command_id = CommandId{std::string{kCommandId}};
  const std::vector first_events{
      PatternEvent{PadSlotId{0, 0}, 0, 240, 100}};
  LMDJ_CHECK(
      journal
          .begin(
              bundle,
              session_id,
              pattern.id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              0)
          .has_value());
  LMDJ_CHECK(
      journal
          .append_tail(
              bundle, session_id, pattern.id, 0, 1, first_events)
          .has_value());
  const auto flush = journal.append_flush(
      bundle, session_id, command_id, pattern.id, 0, first_events);
  LMDJ_CHECK(flush.has_value());
  LMDJ_CHECK(
      store
          .execute_sequence_flush(
              bundle,
              SequenceFlushIdentity{
                  session_id, flush.value().flush_seq, command_id, pattern.id})
          .has_value());

  SequenceJournal restarted;
  const auto loaded = restarted.read_active(bundle);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value().kind == SessionKind::sequence);
  LMDJ_CHECK(loaded.value().flushes.size() == 1);
  LMDJ_CHECK(loaded.value().flushes.front().kind == SessionKind::sequence);
  LMDJ_CHECK(loaded.value().flushes.front().completed);
  const auto legacy_bytes =
      read_text(bundle / "recovery/active/sequence.jsonl");
  LMDJ_CHECK(legacy_bytes.find("\"kind\":\"tail\"") != std::string::npos);
  LMDJ_CHECK(legacy_bytes.find("\"kind\":\"flush\"") != std::string::npos);
  LMDJ_CHECK(legacy_bytes.find("\"kind\":\"complete\"") !=
             std::string::npos);
  LMDJ_CHECK(legacy_bytes.find("session_kind") == std::string::npos);

  const std::vector pending{
      PatternEvent{PadSlotId{0, 1}, 480, 240, 90}};
  LMDJ_CHECK(
      restarted
          .append_tail(bundle, session_id, pattern.id, 1, 2, pending)
          .has_value());
  const auto candidates = store.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().journal.kind == SessionKind::sequence);
  LMDJ_CHECK(candidates.value().front().journal.pending_events == pending);
  LMDJ_CHECK(candidates.value().front().journal.flushes.front().completed);
  LMDJ_CHECK(std::filesystem::exists(candidates.value().front().path));
}

void test_performance_begin_keeps_owner_across_writer_release() {
  TempDirectory temp;
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore creator;
  LMDJ_CHECK(creator.create(bundle, empty_v4_project()).has_value());
  auto platform = std::make_shared<ReleaseCallbackPlatform>(
      lmdj::project_io::make_default_project_storage_platform());
  ProjectStore winner{platform};
  ProjectStore contender;
  std::optional<lmdj::foundation::Result<
      lmdj::project_io::PerformanceLifecycleReceipt>> second;
  bool yielded = false;
  platform->after_release = [&] {
    if (yielded) {
      return;
    }
    const auto active = SequenceJournal{}.read_active_performance(bundle);
    if (!active.has_value() || active.value().expected_revision != 1) {
      return;
    }
    yielded = true;
    second = contender.begin_performance_draft(
        bundle,
        {{CommandId{std::string{kSecondCommandId}}, 0},
         SequenceSessionId{std::string{kSecondPerformanceSessionId}},
         PerformanceId{std::string{kSecondPerformanceId}}});
  };
  const auto first = winner.begin_performance_draft(
      bundle,
      {{CommandId{std::string{kCommandId}}, 0},
       SequenceSessionId{std::string{kPerformanceSessionId}},
       PerformanceId{std::string{kPerformanceId}}});
  if (!first.has_value()) {
    std::cerr << "begin lost its owner at writer release: "
              << first.error().message << " " << first.error().details.dump()
              << '\n';
    if (second.has_value()) {
      std::cerr << "competing begin: "
                << (second->has_value() ? "success" : second->error().message)
                << '\n';
    }
  }
  LMDJ_CHECK(yielded);
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(!second->has_value());
  LMDJ_CHECK(second->error().details.at("reason") == "recording_session_active");
  const auto active = SequenceJournal{}.read_active_performance(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().session_id.value() == kPerformanceSessionId);
  const auto truth = creator.load(bundle);
  LMDJ_CHECK(truth.has_value());
  LMDJ_CHECK(truth.value().revision == 1);
  LMDJ_CHECK(truth.value().performances.size() == 1);
  LMDJ_CHECK(truth.value().performances.contains(active.value().performance_id));
}

void test_atomic_performance_draft_begin_serializes_writer_lease(
    int iterations) {
  for (int iteration = 0; iteration < iterations; ++iteration) {
    TempDirectory temp;
    ProjectStore creator;
    const auto bundle = temp.path() / "project.lmdj";
    LMDJ_CHECK(creator.create(bundle, empty_v4_project()).has_value());
    std::atomic<int> ready{0};
    std::atomic<bool> start{false};
    std::optional<lmdj::foundation::Result<
        lmdj::project_io::PerformanceLifecycleReceipt>> first;
    std::optional<lmdj::foundation::Result<
        lmdj::project_io::PerformanceLifecycleReceipt>> second;
    std::thread first_thread([&] {
      ProjectStore store;
      ready.fetch_add(1, std::memory_order_release);
      while (!start.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      first = store.begin_performance_draft(
          bundle,
          {{CommandId{std::string{kCommandId}}, 0},
           SequenceSessionId{std::string{kPerformanceSessionId}},
           PerformanceId{std::string{kPerformanceId}}});
    });
    std::thread second_thread([&] {
      ProjectStore store;
      ready.fetch_add(1, std::memory_order_release);
      while (!start.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      second = store.begin_performance_draft(
          bundle,
          {{CommandId{std::string{kSecondCommandId}}, 0},
           SequenceSessionId{std::string{kSecondPerformanceSessionId}},
           PerformanceId{std::string{kSecondPerformanceId}}});
    });
    while (ready.load(std::memory_order_acquire) != 2) {
      std::this_thread::yield();
    }
    start.store(true, std::memory_order_release);
    first_thread.join();
    second_thread.join();
    LMDJ_CHECK(first.has_value());
    LMDJ_CHECK(second.has_value());
    if (first->has_value() == second->has_value()) {
      const auto describe = [](const auto& result) {
        if (result.has_value()) {
          return std::string{"success"};
        }
        return std::string{"failure: "} + result.error().message +
               " details=" + result.error().details.dump();
      };
      std::cerr << "Performance begin iteration " << iteration
                << ": first=" << describe(*first)
                << "; second=" << describe(*second) << '\n';
    }
    LMDJ_CHECK(first->has_value() != second->has_value());
    const auto truth = creator.load(bundle);
    LMDJ_CHECK(truth.has_value());
    LMDJ_CHECK(truth.value().revision == 1);
    LMDJ_CHECK(truth.value().performances.size() == 1);
    const auto active = SequenceJournal{}.read_active_performance(bundle);
    LMDJ_CHECK(active.has_value());
    LMDJ_CHECK(
        truth.value().performances.contains(active.value().performance_id));
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const bool stress = argc == 2 && std::string_view{argv[1]} == "--stress";
    test_sequence_and_performance_are_mutually_exclusive();
    test_begin_validates_revision_under_admission_lease();
    test_v3_project_uses_current_sequence_journal_format();
    test_performance_recovery_does_not_poison_sequence_listing();
    test_same_kind_second_begin_prioritizes_active_session();
    test_concurrent_sequence_begins_admit_only_one_session();
    test_concurrent_sequence_and_performance_begins_admit_only_one_kind();
    test_legacy_v3_sequence_tail_flush_completion_and_seal_reconcile();
    test_performance_begin_keeps_owner_across_writer_release();
    test_atomic_performance_draft_begin_serializes_writer_lease(
        stress ? 32 : 1);
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
