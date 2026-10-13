#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <span>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/facade/performance_engine_adapter.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "tests/core/support/test.hpp"

namespace {

constexpr std::string_view kProject = "10000000-0000-4000-8000-000000000001";
constexpr std::string_view kSession = "10000000-0000-4000-8000-000000000002";
constexpr std::string_view kPerformance =
    "10000000-0000-4000-8000-000000000003";
constexpr std::string_view kBegin = "10000000-0000-4000-8000-000000000004";
constexpr std::string_view kGesture = "10000000-0000-4000-8000-000000000005";
constexpr std::string_view kFxGesture = "10000000-0000-4000-8000-000000000006";
constexpr std::string_view kLaunch = "10000000-0000-4000-8000-000000000007";
constexpr std::string_view kStop = "10000000-0000-4000-8000-000000000008";
constexpr std::string_view kSave = "10000000-0000-4000-8000-000000000009";

class TempDirectory {
public:
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-gesture-" +
             std::to_string(
                 std::chrono::steady_clock::now().time_since_epoch().count()));
    std::filesystem::create_directories(path_);
  }
  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }
  const std::filesystem::path &path() const { return path_; }

private:
  std::filesystem::path path_;
};

class Clock final : public lmdj::facade::PerformanceClock {
public:
  void anchor(std::uint16_t, std::uint64_t) override {}

  lmdj::foundation::Result<std::uint64_t> read_tick() override {
    const auto value = ticks_.at(cursor_++);
    return lmdj::foundation::Result<std::uint64_t>::success(value);
  }

private:
  std::vector<std::uint64_t> ticks_{0,   10,  30,  40,  100, 110, 120, 200,
                                    210, 220, 230, 240, 245, 250};
  std::size_t cursor_{};
};

class GestureSink final : public lmdj::facade::PerformanceGestureSink {
public:
  lmdj::foundation::Result<void>
  apply_gesture(lmdj::audio::FxGesture gesture) override {
    if (refusals_ != 0) {
      --refusals_;
      return lmdj::foundation::Result<void>::failure({
          lmdj::foundation::ErrorCode::internal_error,
          "test master bus refused the gesture",
      });
    }
    applied_.push_back(gesture);
    return lmdj::foundation::Result<void>::success();
  }

  void refuse_next(std::size_t count) { refusals_ = count; }

  const std::vector<lmdj::audio::FxGesture> &applied() const {
    return applied_;
  }

private:
  std::vector<lmdj::audio::FxGesture> applied_;
  std::size_t refusals_{};
};

class Sequencer final : public lmdj::facade::PerformanceInputSequencer {
public:
  void seed(std::uint64_t last_input_sequence) override {
    next_ = std::max(next_, last_input_sequence);
  }

  lmdj::foundation::Result<std::uint64_t> next() override {
    return lmdj::foundation::Result<std::uint64_t>::success(++next_);
  }

private:
  std::uint64_t next_{};
};

class LaunchAcknowledger final
    : public lmdj::facade::PatternLaunchAcknowledger {
public:
  lmdj::foundation::Result<lmdj::facade::PatternLaunchReservation>
  reserve(const lmdj::foundation::SequenceSessionId &session_id,
          const lmdj::foundation::CommandId &request_id,
          std::uint8_t pattern_slot,
          std::uint64_t earliest_target_tick,
          std::shared_ptr<const lmdj::cooker::RuntimeSnapshot>
              resolved_pattern) override {
    session_id_ = session_id;
    request_id_ = request_id;
    pattern_slot_ = pattern_slot;
    target_tick_ = earliest_target_tick;
    resolved_pattern_ = std::move(resolved_pattern);
    return lmdj::foundation::Result<
        lmdj::facade::PatternLaunchReservation>::success({earliest_target_tick,
                                                          false});
  }

  std::vector<lmdj::facade::PatternLaunchOutcome> peek(
      const lmdj::foundation::SequenceSessionId &session_id) override {
    const auto found = outcomes_.find(session_id.value());
    return found == outcomes_.end()
               ? std::vector<lmdj::facade::PatternLaunchOutcome>{}
               : found->second;
  }

  lmdj::foundation::Result<void> commit(
      const lmdj::foundation::SequenceSessionId &session_id,
      const lmdj::foundation::CommandId &request_id) override {
    const auto found = outcomes_.find(session_id.value());
    if (found == outcomes_.end() || found->second.empty() ||
        found->second.front().request_id != request_id) {
      return lmdj::foundation::Result<void>::failure({
          lmdj::foundation::ErrorCode::invalid_argument,
          "test acknowledger commit is not the ordered front",
      });
    }
    if (commit_failures_ != 0) {
      --commit_failures_;
      return lmdj::foundation::Result<void>::failure({
          lmdj::foundation::ErrorCode::io_error,
          "injected acknowledgement commit failure",
      });
    }
    found->second.erase(found->second.begin());
    if (found->second.empty()) {
      outcomes_.erase(found);
    }
    return lmdj::foundation::Result<void>::success();
  }

  void cancel(const lmdj::foundation::SequenceSessionId &) noexcept override {}

  void acknowledge() {
    enqueue(session_id_, request_id_, pattern_slot_, target_tick_,
            lmdj::facade::PatternLaunchOutcomeKind::applied);
  }

  void enqueue(
      const lmdj::foundation::SequenceSessionId &session_id,
      const lmdj::foundation::CommandId &request_id,
      std::uint8_t pattern_slot, std::uint64_t effective_tick,
      lmdj::facade::PatternLaunchOutcomeKind kind) {
    outcomes_[session_id.value()].push_back(
        {session_id, request_id, pattern_slot, effective_tick, kind});
  }

  void fail_next_commit() { commit_failures_ = 1; }

  std::size_t pending_count(
      const lmdj::foundation::SequenceSessionId &session_id) const {
    const auto found = outcomes_.find(session_id.value());
    return found == outcomes_.end() ? 0 : found->second.size();
  }

  const std::shared_ptr<const lmdj::cooker::RuntimeSnapshot>&
  resolved_pattern() const {
    return resolved_pattern_;
  }

private:
  lmdj::foundation::SequenceSessionId session_id_{""};
  lmdj::foundation::CommandId request_id_{""};
  std::uint8_t pattern_slot_{};
  std::uint64_t target_tick_{};
  std::shared_ptr<const lmdj::cooker::RuntimeSnapshot> resolved_pattern_;
  std::map<std::string, std::vector<lmdj::facade::PatternLaunchOutcome>>
      outcomes_;
  std::size_t commit_failures_{};
};

class PostWriteFailingStorage final
    : public lmdj::project_io::ProjectStoragePlatform {
public:
  PostWriteFailingStorage()
      : delegate_(lmdj::project_io::make_default_project_storage_platform()) {}

  void fail_next_tail_retry_pair() { post_write_failures_ = 2; }
  void fail_next_tail_pre_write_pair() { pre_write_failures_ = 2; }
  // The next admission_complete metadata append fails before writing, and the
  // journal's read-back fails once, so the outcome is genuinely unknown.
  void fail_next_complete_pair() {
    complete_pre_write_failures_ = 1;
  }

  lmdj::foundation::Result<std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path &path) override {
    return delegate_->acquire_writer(path);
  }
  lmdj::foundation::Result<void>
  ensure_directory(const std::filesystem::path &path) override {
    return delegate_->ensure_directory(path);
  }
  lmdj::foundation::Result<bool>
  exists(const std::filesystem::path &path) const override {
    return delegate_->exists(path);
  }
  lmdj::foundation::Result<std::uint64_t>
  byte_length(const std::filesystem::path &path) const override {
    return delegate_->byte_length(path);
  }
  lmdj::foundation::Result<std::vector<std::byte>>
  read_complete(const std::filesystem::path &path) const override {
    if (journal_read_armed_ &&
        path.generic_string().find("performance.jsonl") !=
            std::string::npos) {
      journal_read_armed_ = false;
      return lmdj::foundation::Result<std::vector<std::byte>>::failure({
          lmdj::foundation::ErrorCode::io_error,
          "injected journal read failure",
      });
    }
    return delegate_->read_complete(path);
  }
  lmdj::foundation::Result<void>
  create_immutable(const std::filesystem::path &path,
                   std::span<const std::byte> bytes) override {
    return delegate_->create_immutable(path, bytes);
  }
  lmdj::foundation::Result<void>
  replace_complete(const std::filesystem::path &path,
                   std::span<const std::byte> bytes) override {
    return delegate_->replace_complete(path, bytes);
  }
  lmdj::foundation::Result<void>
  append_durable(const std::filesystem::path &path,
                 std::uint64_t valid_prefix_length,
                 std::span<const std::byte> bytes) override {
    if (pre_write_failures_ != 0) {
      --pre_write_failures_;
      return lmdj::foundation::Result<void>::failure({
          lmdj::foundation::ErrorCode::io_error,
          "injected pre-write append failure",
      });
    }
    const auto is_complete_record =
        std::search(bytes.begin(), bytes.end(),
                    kCompleteMarker, kCompleteMarker + 18) != bytes.end();
    if (is_complete_record && complete_pre_write_failures_ != 0) {
      --complete_pre_write_failures_;
      journal_read_armed_ = true;
      return lmdj::foundation::Result<void>::failure({
          lmdj::foundation::ErrorCode::io_error,
          "injected pre-write admission_complete failure",
      });
    }
    auto appended =
        delegate_->append_durable(path, valid_prefix_length, bytes);
    if (appended.has_value() && post_write_failures_ != 0) {
      --post_write_failures_;
      return lmdj::foundation::Result<void>::failure({
          lmdj::foundation::ErrorCode::io_error,
          "injected post-write append failure",
      });
    }
    return appended;
  }
  lmdj::foundation::Result<void>
  remove(const std::filesystem::path &path) override {
    return delegate_->remove(path);
  }
  lmdj::foundation::Result<std::vector<std::string>>
  list_names(const std::filesystem::path &path) const override {
    return delegate_->list_names(path);
  }
  lmdj::foundation::Result<std::vector<std::string>>
  list_directories(const std::filesystem::path &path) const override {
    return delegate_->list_directories(path);
  }
  lmdj::foundation::Result<void>
  remove_tree(const std::filesystem::path &path) override {
    return delegate_->remove_tree(path);
  }
  lmdj::foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path &staging,
      const std::filesystem::path &destination) override {
    return delegate_->publish_directory_if_absent(staging, destination);
  }
  lmdj::foundation::Result<bool>
  directory_exists(const std::filesystem::path &path) const override {
    return delegate_->directory_exists(path);
  }
  lmdj::foundation::Result<void>
  validate_managed_tree(const std::filesystem::path &path) const override {
    return delegate_->validate_managed_tree(path);
  }

private:
  static constexpr std::byte kCompleteMarker[18] = {
      std::byte{'a'}, std::byte{'d'}, std::byte{'m'}, std::byte{'i'},
      std::byte{'s'}, std::byte{'s'}, std::byte{'i'}, std::byte{'o'},
      std::byte{'n'}, std::byte{'_'}, std::byte{'c'}, std::byte{'o'},
      std::byte{'m'}, std::byte{'p'}, std::byte{'l'}, std::byte{'e'},
      std::byte{'t'}, std::byte{'e'},
  };
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> delegate_;
  std::size_t pre_write_failures_{};
  std::size_t post_write_failures_{};
  std::size_t complete_pre_write_failures_{};
  mutable bool journal_read_armed_{};
};

void check_ok(const nlohmann::json &response) {
  if (!response.at("ok").get<bool>()) {
    throw std::runtime_error(response.dump());
  }
}


std::map<std::string, std::string> bundle_bytes(
    const std::filesystem::path &bundle) {
  std::map<std::string, std::string> result;
  for (const auto &entry : std::filesystem::recursive_directory_iterator(
           bundle)) {
    if (!entry.is_regular_file()) {
      continue;
    }
    std::ifstream stream(entry.path(), std::ios::binary);
    result.emplace(
        entry.path().lexically_relative(bundle).generic_string(),
        std::string{std::istreambuf_iterator<char>{stream},
                    std::istreambuf_iterator<char>{}});
  }
  return result;
}

void test_status_is_read_only_and_explicit_service_is_exactly_once() {
  TempDirectory temp;
  auto acknowledger = std::make_shared<LaunchAcknowledger>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      acknowledger,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "read-only-status.lmdj";
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", "61000000-0000-4000-8000-000000000001"},
                                {"bpm", 120}}));
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", "61000000-0000-4000-8000-000000000002"},
                                {"expected_revision", 0},
                                {"session_id", "61000000-0000-4000-8000-000000000003"},
                                {"performance_id", "61000000-0000-4000-8000-000000000004"}}));
  check_ok(application.command({
      {"operation", "performance.record.launch-request"},
      {"project_path", bundle.generic_string()},
      {"session_id", "61000000-0000-4000-8000-000000000003"},
      {"request_id", "61000000-0000-4000-8000-000000000005"},
      {"pattern_slot", 3},
  }));
  acknowledger->acknowledge();
  const lmdj::foundation::SequenceSessionId session{
      "61000000-0000-4000-8000-000000000003"};
  const auto before_status = bundle_bytes(bundle);
  const auto first_status = application.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  const auto second_status = application.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(first_status);
  LMDJ_CHECK(first_status == second_status);
  LMDJ_CHECK(first_status.at("result").at("last_launch_ack").is_null());
  LMDJ_CHECK(bundle_bytes(bundle) == before_status);
  LMDJ_CHECK(acknowledger->pending_count(session) == 1);

  LMDJ_CHECK(application.service_performance().has_value());
  const auto after_service = bundle_bytes(bundle);
  LMDJ_CHECK(after_service != before_status);
  LMDJ_CHECK(acknowledger->pending_count(session) == 0);
  const auto serviced_status = application.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(serviced_status);
  LMDJ_CHECK(serviced_status.at("result").at("last_launch_ack").at(
                 "request_id") ==
             "61000000-0000-4000-8000-000000000005");

  lmdj::facade::Application observer({
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  });
  const auto cross_process_status = observer.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(cross_process_status);
  LMDJ_CHECK(cross_process_status.at("result").at("last_launch_ack") ==
             serviced_status.at("result").at("last_launch_ack"));

  LMDJ_CHECK(application.service_performance().has_value());
  LMDJ_CHECK(bundle_bytes(bundle) == after_service);
  LMDJ_CHECK(application.query({
                 {"operation", "performance.record.status"},
                 {"project_path", bundle.generic_string()},
             }) == serviced_status);
  LMDJ_CHECK(bundle_bytes(bundle) == after_service);
}

void test_launch_service_retries_without_loss_or_duplicate_events() {
  TempDirectory temp;
  auto storage = std::make_shared<PostWriteFailingStorage>();
  auto acknowledger = std::make_shared<LaunchAcknowledger>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      storage,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      acknowledger,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "launch-service-retry.lmdj";
  const lmdj::foundation::SequenceSessionId session{
      "62000000-0000-4000-8000-000000000003"};
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", "62000000-0000-4000-8000-000000000001"},
                                {"bpm", 120}}));
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", "62000000-0000-4000-8000-000000000002"},
                                {"expected_revision", 0},
                                {"session_id", session.value()},
                                {"performance_id", "62000000-0000-4000-8000-000000000004"}}));
  check_ok(application.command({
      {"operation", "performance.record.launch-request"},
      {"project_path", bundle.generic_string()},
      {"session_id", session.value()},
      {"request_id", "62000000-0000-4000-8000-000000000005"},
      {"pattern_slot", 3},
  }));
  acknowledger->acknowledge();

  storage->fail_next_tail_pre_write_pair();
  const auto before_failure = bundle_bytes(bundle);
  const auto definitive = application.service_performance();
  LMDJ_CHECK(!definitive.has_value());
  LMDJ_CHECK(definitive.error().code == lmdj::foundation::ErrorCode::io_error);
  LMDJ_CHECK(bundle_bytes(bundle) == before_failure);
  LMDJ_CHECK(acknowledger->pending_count(session) == 1);
  const auto rolled_back = application.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(rolled_back);
  LMDJ_CHECK(rolled_back.at("result").at("last_launch_ack").is_null());

  acknowledger->fail_next_commit();
  const auto commit_gap = application.service_performance();
  LMDJ_CHECK(!commit_gap.has_value());
  LMDJ_CHECK(commit_gap.error().code == lmdj::foundation::ErrorCode::io_error);
  LMDJ_CHECK(acknowledger->pending_count(session) == 1);
  lmdj::project_io::SequenceJournal journal{storage};
  const auto durable_gap = journal.read_active_performance(bundle);
  LMDJ_CHECK(durable_gap.has_value());
  LMDJ_CHECK(durable_gap.value().pending_events.size() == 1);
  LMDJ_CHECK(durable_gap.value().last_launch_ack.has_value());
  LMDJ_CHECK(durable_gap.value().last_launch_ack->request_id.value() ==
             "62000000-0000-4000-8000-000000000005");
  const auto gap_bytes = bundle_bytes(bundle);
  const auto gap_sequence = durable_gap.value().last_input_sequence;

  LMDJ_CHECK(application.service_performance().has_value());
  LMDJ_CHECK(acknowledger->pending_count(session) == 0);
  LMDJ_CHECK(bundle_bytes(bundle) == gap_bytes);
  LMDJ_CHECK(journal.read_active_performance(bundle).value().last_input_sequence ==
             gap_sequence);

  acknowledger->enqueue(
      session,
      lmdj::foundation::CommandId{
          "62000000-0000-4000-8000-000000000006"},
      4, 7'680, lmdj::facade::PatternLaunchOutcomeKind::applied);
  acknowledger->enqueue(
      session,
      lmdj::foundation::CommandId{
          "62000000-0000-4000-8000-000000000007"},
      5, 11'520, lmdj::facade::PatternLaunchOutcomeKind::applied);
  acknowledger->fail_next_commit();
  const auto second_gap = application.service_performance();
  LMDJ_CHECK(!second_gap.has_value());
  LMDJ_CHECK(acknowledger->pending_count(session) == 2);
  const auto second_durable = journal.read_active_performance(bundle);
  LMDJ_CHECK(second_durable.has_value());
  LMDJ_CHECK(second_durable.value().pending_events.size() == 2);
  LMDJ_CHECK(second_durable.value().last_launch_ack->request_id.value() ==
             "62000000-0000-4000-8000-000000000006");
  const auto second_gap_bytes = bundle_bytes(bundle);

  LMDJ_CHECK(application.service_performance().has_value());
  LMDJ_CHECK(acknowledger->pending_count(session) == 0);
  LMDJ_CHECK(bundle_bytes(bundle) != second_gap_bytes);
  const auto all_durable = journal.read_active_performance(bundle);
  LMDJ_CHECK(all_durable.has_value());
  LMDJ_CHECK(all_durable.value().pending_events.size() == 3);
  LMDJ_CHECK(all_durable.value().last_launch_ack->request_id.value() ==
             "62000000-0000-4000-8000-000000000007");

  const auto before_no_event = bundle_bytes(bundle);
  acknowledger->enqueue(
      session,
      lmdj::foundation::CommandId{
          "62000000-0000-4000-8000-000000000008"},
      6, 15'360, lmdj::facade::PatternLaunchOutcomeKind::cancelled);
  acknowledger->enqueue(
      session,
      lmdj::foundation::CommandId{
          "62000000-0000-4000-8000-000000000009"},
      7, 19'200, lmdj::facade::PatternLaunchOutcomeKind::failed);
  LMDJ_CHECK(application.service_performance().has_value());
  LMDJ_CHECK(acknowledger->pending_count(session) == 0);
  LMDJ_CHECK(bundle_bytes(bundle) == before_no_event);

  acknowledger->enqueue(
      session,
      lmdj::foundation::CommandId{
          "62000000-0000-4000-8000-000000000010"},
      8, 23'040, lmdj::facade::PatternLaunchOutcomeKind::applied);
  acknowledger->enqueue(
      session,
      lmdj::foundation::CommandId{
          "62000000-0000-4000-8000-000000000011"},
      9, 26'880, lmdj::facade::PatternLaunchOutcomeKind::applied);
  check_ok(application.command({
      {"operation", "performance.record.stop"},
      {"project_path", bundle.generic_string()},
      {"session_id", session.value()},
      {"request_id", "62000000-0000-4000-8000-000000000012"},
  }));
  check_ok(application.command({
      {"operation", "performance.save"},
      {"project_path", bundle.generic_string()},
      {"command_id", "62000000-0000-4000-8000-000000000013"},
      {"expected_revision", 1},
      {"performance_id", "62000000-0000-4000-8000-000000000004"},
      {"name", "Ordered Launches"},
      {"recording_artifact", nullptr},
  }));
  const auto inspected = application.query({
      {"operation", "performance.inspect"},
      {"project_path", bundle.generic_string()},
      {"performance_id", "62000000-0000-4000-8000-000000000004"},
  });
  check_ok(inspected);
  std::size_t launch_count = 0;
  for (const auto &event :
       inspected.at("result").at("performance").at("events")) {
    launch_count += event.at("kind") == "pattern_launch" ? 1U : 0U;
  }
  LMDJ_CHECK(launch_count == 5);
}

void test_ambiguous_launch_service_freezes_without_consuming_outcome() {
  TempDirectory temp;
  auto storage = std::make_shared<PostWriteFailingStorage>();
  auto acknowledger = std::make_shared<LaunchAcknowledger>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      storage,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      acknowledger,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "ambiguous-launch-service.lmdj";
  const lmdj::foundation::SequenceSessionId session{
      "63000000-0000-4000-8000-000000000003"};
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", "63000000-0000-4000-8000-000000000001"},
                                {"bpm", 120}}));
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", "63000000-0000-4000-8000-000000000002"},
                                {"expected_revision", 0},
                                {"session_id", session.value()},
                                {"performance_id", "63000000-0000-4000-8000-000000000004"}}));
  check_ok(application.command({
      {"operation", "performance.record.launch-request"},
      {"project_path", bundle.generic_string()},
      {"session_id", session.value()},
      {"request_id", "63000000-0000-4000-8000-000000000005"},
      {"pattern_slot", 3},
  }));
  acknowledger->acknowledge();
  storage->fail_next_tail_retry_pair();
  const auto ambiguous = application.service_performance();
  LMDJ_CHECK(!ambiguous.has_value());
  LMDJ_CHECK(ambiguous.error().details.at("reason") ==
             "performance_tail_outcome_unknown");
  LMDJ_CHECK(acknowledger->pending_count(session) == 1);
  const auto retained = bundle_bytes(bundle);
  const auto status = application.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("state") == "recovery_required");
  LMDJ_CHECK(status.at("result").at("pending_event_count") == 0);
  LMDJ_CHECK(status.at("result").at("last_launch_ack").is_null());
  LMDJ_CHECK(status.at("result").at("pending_launch").at("request_id") ==
             "63000000-0000-4000-8000-000000000005");
  LMDJ_CHECK(bundle_bytes(bundle) == retained);
  const auto frozen = application.service_performance();
  LMDJ_CHECK(!frozen.has_value());
  LMDJ_CHECK(frozen.error().details.at("reason") ==
             "performance_tail_outcome_unknown");
  LMDJ_CHECK(acknowledger->pending_count(session) == 1);
  LMDJ_CHECK(bundle_bytes(bundle) == retained);
}

void test_raw_gesture_admission_and_launch_ack() {
  TempDirectory temp;
  auto acknowledger = std::make_shared<LaunchAcknowledger>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
  config.performance_clock = std::make_shared<Clock>();
  config.performance_input_sequencer = std::make_shared<Sequencer>();
  config.pattern_launch_acknowledger = acknowledger;
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "project.lmdj";

  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", kProject},
                                {"bpm", 120}}));
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", kBegin},
                                {"expected_revision", 0},
                                {"session_id", kSession},
                                {"performance_id", kPerformance}}));

  const auto press_id = "10000000-0000-4000-8000-000000000010";
  const auto press = nlohmann::json{{"operation", "performance.record.event"},
                                    {"project_path", bundle.generic_string()},
                                    {"session_id", kSession},
                                    {"event_id", press_id},
                                    {"event",
                                     {{"kind", "pad_press"},
                                      {"gesture_id", kGesture},
                                      {"slot", 5},
                                      {"velocity", 100}}}};
  const auto accepted = application.command(press);
  check_ok(accepted);
  lmdj::project_io::SequenceJournal journal;
  const auto pressed = journal.read_active_performance(bundle);
  LMDJ_CHECK(pressed.has_value());
  LMDJ_CHECK(pressed.value().pending_events.empty());
  LMDJ_CHECK(pressed.value().last_input_sequence == 1);
  LMDJ_CHECK(pressed.value().transient_checkpoint.has_value());
  LMDJ_CHECK(
      pressed.value().transient_checkpoint->open_pads.size() == 1);
  LMDJ_CHECK(
      pressed.value().transient_checkpoint->open_pads.front().gesture_id ==
      kGesture);
  LMDJ_CHECK(
      pressed.value().transient_checkpoint->last_accepted_tick == 10);
  const auto replayed = application.command(press);
  check_ok(replayed);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);
  auto collision = press;
  collision["event"]["slot"] = 6;
  LMDJ_CHECK(!application.command(collision).at("ok").get<bool>());

  check_ok(application.command(
      {{"operation", "performance.record.event"},
       {"project_path", bundle.generic_string()},
       {"session_id", kSession},
       {"event_id", "10000000-0000-4000-8000-000000000011"},
       {"event",
        {{"kind", "pad_release"}, {"gesture_id", kGesture}, {"slot", 5}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000012"},
                           {"event",
                            {{"kind", "fx_engage"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"},
                             {"value", 500}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000013"},
                           {"event",
                            {{"kind", "fx_move"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"},
                             {"value", 600}}}}));
  const auto coalesced =
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000014"},
                           {"event",
                            {{"kind", "fx_move"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"},
                             {"value", 700}}}});
  check_ok(coalesced);
  LMDJ_CHECK(coalesced.at("result").at("coalesced") == true);
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000015"},
                           {"event",
                            {{"kind", "fx_release"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"}}}}));

  const auto launch =
      application.command({{"operation", "performance.record.launch-request"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"request_id", kLaunch},
                           {"pattern_slot", 3}});
  check_ok(launch);
  LMDJ_CHECK(launch.at("result").at("target_tick") == 3840);
  const auto pending_status =
      application.query({{"operation", "performance.record.status"},
                         {"project_path", bundle.generic_string()}});
  check_ok(pending_status);
  LMDJ_CHECK(pending_status.at("result").at("pending_launch").at("claimed") ==
             false);
  check_ok(
      application.command({{"operation", "performance.record.launch-request"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"request_id", kLaunch},
                           {"pattern_slot", 3}}));
  const auto launch_collision =
      application.command({{"operation", "performance.record.launch-request"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"request_id", kLaunch},
                           {"pattern_slot", 4}});
  LMDJ_CHECK(!launch_collision.at("ok").get<bool>());
  acknowledger->acknowledge();
  const auto unserviced_status =
      application.query({{"operation", "performance.record.status"},
                         {"project_path", bundle.generic_string()}});
  check_ok(unserviced_status);
  LMDJ_CHECK(unserviced_status.at("result").at("last_launch_ack").is_null());
  LMDJ_CHECK(acknowledger->pending_count(
                 lmdj::foundation::SequenceSessionId{std::string{kSession}}) ==
             1);
  LMDJ_CHECK(application.service_performance().has_value());
  const auto status =
      application.query({{"operation", "performance.record.status"},
                         {"project_path", bundle.generic_string()}});
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("last_launch_ack").at("pattern_slot") == 3);

  check_ok(application.command(
      {{"operation", "performance.record.event"},
       {"project_path", bundle.generic_string()},
       {"session_id", kSession},
       {"event_id", "10000000-0000-4000-8000-000000000016"},
       {"event",
        {{"kind", "pad_press"},
         {"gesture_id", "10000000-0000-4000-8000-000000000017"},
         {"slot", 7},
         {"velocity", 90}}}}));
  check_ok(application.command(
      {{"operation", "performance.record.event"},
       {"project_path", bundle.generic_string()},
       {"session_id", kSession},
       {"event_id", "10000000-0000-4000-8000-000000000018"},
       {"event",
        {{"kind", "fx_engage"},
         {"gesture_id", "10000000-0000-4000-8000-000000000019"},
         {"fx", "reverse"},
         {"value", 800}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000020"},
                           {"event", {{"kind", "hold_on"}}}}));

  const auto open = journal.read_active_performance(bundle);
  LMDJ_CHECK(open.has_value());
  LMDJ_CHECK(open.value().last_input_sequence == 10);
  LMDJ_CHECK(open.value().transient_checkpoint.has_value());
  LMDJ_CHECK(open.value().transient_checkpoint->open_pads.size() == 1);
  LMDJ_CHECK(open.value().transient_checkpoint->open_fx.size() == 1);
  LMDJ_CHECK(open.value().transient_checkpoint->hold);
  LMDJ_CHECK(open.value().transient_checkpoint->last_accepted_tick == 230);
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000021"},
                           {"event", {{"kind", "hold_off"}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000022"},
                           {"event", {{"kind", "hold_on"}}}}));

  check_ok(application.command({{"operation", "performance.record.stop"},
                                {"project_path", bundle.generic_string()},
                                {"session_id", kSession},
                                {"request_id", kStop}}));
  check_ok(application.command({{"operation", "performance.save"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", kSave},
                                {"expected_revision", 1},
                                {"performance_id", kPerformance},
                                {"name", "Gesture Take"},
                                {"recording_artifact", nullptr}}));
  const auto inspected =
      application.query({{"operation", "performance.inspect"},
                         {"project_path", bundle.generic_string()},
                         {"performance_id", kPerformance}});
  check_ok(inspected);
  const auto encoded = inspected.dump();
  LMDJ_CHECK(encoded.find(std::string(kGesture)) == std::string::npos);
  LMDJ_CHECK(encoded.find(std::string(kFxGesture)) == std::string::npos);
  const auto &events = inspected.at("result").at("performance").at("events");
  LMDJ_CHECK(events.size() == 12U);
  LMDJ_CHECK(events.at(0).at("kind") == "pad_hit");
  LMDJ_CHECK(events.at(0).at("duration_tick") == 20);
  const auto encoded_events = events.dump();
  LMDJ_CHECK(encoded_events.find("pattern_launch") != std::string::npos);
  LMDJ_CHECK(encoded_events.find("hold_off") != std::string::npos);
}

void test_launch_receives_core_resolved_immutable_pattern_material() {
  TempDirectory temp;
  auto acknowledger = std::make_shared<LaunchAcknowledger>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      acknowledger,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "resolved-pattern-project.lmdj";
  constexpr auto pattern = "10000000-0000-4000-8000-000000000030";
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", "10000000-0000-4000-8000-000000000031"},
                                {"bpm", 120}}));
  check_ok(application.command({
      {"operation", "pattern.create"},
      {"project_path", bundle.generic_string()},
      {"command_id", "10000000-0000-4000-8000-000000000032"},
      {"expected_revision", 0},
      {"pattern_id", pattern},
      {"bars", 1},
  }));
  check_ok(application.command({
      {"operation", "pattern.slot.assign"},
      {"project_path", bundle.generic_string()},
      {"command_id", "10000000-0000-4000-8000-000000000033"},
      {"expected_revision", 1},
      {"pattern_slot", 3},
      {"pattern_id", pattern},
  }));
  check_ok(application.command({
      {"operation", "performance.record.begin"},
      {"project_path", bundle.generic_string()},
      {"command_id", "10000000-0000-4000-8000-000000000034"},
      {"expected_revision", 2},
      {"session_id", "10000000-0000-4000-8000-000000000035"},
      {"performance_id", "10000000-0000-4000-8000-000000000036"},
  }));
  check_ok(application.command({
      {"operation", "performance.record.launch-request"},
      {"project_path", bundle.generic_string()},
      {"session_id", "10000000-0000-4000-8000-000000000035"},
      {"request_id", "10000000-0000-4000-8000-000000000037"},
      {"pattern_slot", 3},
  }));
  LMDJ_CHECK(acknowledger->resolved_pattern() != nullptr);
  LMDJ_CHECK(acknowledger->resolved_pattern()->pattern_id.value() == pattern);
  LMDJ_CHECK(acknowledger->resolved_pattern()->project_revision == 3);
}

void test_ambiguous_tail_append_freezes_runtime_without_overwrite() {
  TempDirectory temp;
  auto storage = std::make_shared<PostWriteFailingStorage>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      storage,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "ambiguous-project.lmdj";
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", "70000000-0000-4000-8000-000000000001"},
                                {"bpm", 120}}));
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", "70000000-0000-4000-8000-000000000002"},
                                {"expected_revision", 0},
                                {"session_id", "70000000-0000-4000-8000-000000000003"},
                                {"performance_id", "70000000-0000-4000-8000-000000000004"}}));

  storage->fail_next_tail_retry_pair();
  const auto ambiguous = application.command({
      {"operation", "performance.record.event"},
      {"project_path", bundle.generic_string()},
      {"session_id", "70000000-0000-4000-8000-000000000003"},
      {"event_id", "70000000-0000-4000-8000-000000000005"},
      {"event",
       {{"kind", "pad_press"},
        {"gesture_id", "70000000-0000-4000-8000-000000000006"},
        {"slot", 4},
        {"velocity", 91}}},
  });
  LMDJ_CHECK(!ambiguous.at("ok").get<bool>());
  LMDJ_CHECK(
      ambiguous.at("error").at("details").at("reason") ==
      "performance_tail_outcome_unknown");

  const auto journal_path = bundle / "recovery/active/performance.jsonl";
  const auto retained_before = storage->read_complete(journal_path);
  LMDJ_CHECK(retained_before.has_value());
  const auto durable =
      lmdj::project_io::SequenceJournal{storage}.read_active_performance(bundle);
  LMDJ_CHECK(durable.has_value());
  LMDJ_CHECK(durable.value().last_input_sequence == 1);
  LMDJ_CHECK(durable.value().transient_checkpoint.has_value());
  LMDJ_CHECK(durable.value().transient_checkpoint->open_pads.size() == 1);

  const auto status = application.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("state") == "recovery_required");
  LMDJ_CHECK(status.at("result").at("open_pad_gestures") == 1);

  const auto rejected = application.command({
      {"operation", "performance.record.event"},
      {"project_path", bundle.generic_string()},
      {"session_id", "70000000-0000-4000-8000-000000000003"},
      {"event_id", "70000000-0000-4000-8000-000000000007"},
      {"event", {{"kind", "hold_on"}}},
  });
  LMDJ_CHECK(!rejected.at("ok").get<bool>());
  LMDJ_CHECK(
      rejected.at("error").at("details").at("reason") ==
      "performance_tail_outcome_unknown");
  const auto stopped = application.command({
      {"operation", "performance.record.stop"},
      {"project_path", bundle.generic_string()},
      {"session_id", "70000000-0000-4000-8000-000000000003"},
      {"request_id", "70000000-0000-4000-8000-000000000008"},
  });
  LMDJ_CHECK(!stopped.at("ok").get<bool>());
  const auto retained_after = storage->read_complete(journal_path);
  LMDJ_CHECK(retained_after.has_value());
  LMDJ_CHECK(retained_after.value() == retained_before.value());
}


// P10-D7 and Stage 10 acceptance item 8: every admitted FX and HOLD gesture is
// audible live through the same DSP Replay drives. Before this witness the
// Facade journalled gestures and applied none, so a live Performance recorded
// a master bus that never changed.
void test_admitted_fx_and_hold_gestures_reach_the_master_bus() {
  TempDirectory temp;
  auto sink = std::make_shared<GestureSink>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      std::make_shared<LaunchAcknowledger>(),
      lmdj::facade::make_unavailable_performance_replay_controller(),
      sink,
  };
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "project.lmdj";
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", kProject},
                                {"bpm", 120}}));
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", kBegin},
                                {"expected_revision", 0},
                                {"session_id", kSession},
                                {"performance_id", kPerformance}}));

  const auto event = [&bundle](std::string_view event_id,
                               nlohmann::json payload) {
    return nlohmann::json{{"operation", "performance.record.event"},
                          {"project_path", bundle.generic_string()},
                          {"session_id", kSession},
                          {"event_id", event_id},
                          {"event", std::move(payload)}};
  };

  // A Pad gesture is audible through the existing trigger path and must not
  // reach the master bus as an FX gesture.
  check_ok(application.command(
      event("10000000-0000-4000-8000-000000000020",
            {{"kind", "pad_press"},
             {"gesture_id", kGesture},
             {"slot", 5},
             {"velocity", 100}})));
  LMDJ_CHECK(sink->applied().empty());
  check_ok(application.command(
      event("10000000-0000-4000-8000-000000000021",
            {{"kind", "pad_release"}, {"gesture_id", kGesture}, {"slot", 5}})));
  LMDJ_CHECK(sink->applied().empty());

  check_ok(application.command(
      event("10000000-0000-4000-8000-000000000022",
            {{"kind", "fx_engage"},
             {"gesture_id", kFxGesture},
             {"fx", "filter"},
             {"value", 500}})));
  check_ok(application.command(
      event("10000000-0000-4000-8000-000000000023",
            {{"kind", "fx_move"},
             {"gesture_id", kFxGesture},
             {"fx", "filter"},
             {"value", 630}})));
  check_ok(application.command(
      event("10000000-0000-4000-8000-000000000024", {{"kind", "hold_on"}})));
  check_ok(application.command(
      event("10000000-0000-4000-8000-000000000025", {{"kind", "hold_off"}})));
  check_ok(application.command(
      event("10000000-0000-4000-8000-000000000026",
            {{"kind", "fx_release"},
             {"gesture_id", kFxGesture},
             {"fx", "filter"}})));

  const auto &applied = sink->applied();
  LMDJ_CHECK(applied.size() == 5);
  LMDJ_CHECK(applied.at(0).kind == lmdj::audio::FxGestureKind::engage);
  LMDJ_CHECK(applied.at(0).fx == lmdj::domain::PerformanceFx::filter);
  LMDJ_CHECK(applied.at(0).value == 500);
  LMDJ_CHECK(applied.at(1).kind == lmdj::audio::FxGestureKind::move);
  LMDJ_CHECK(applied.at(1).value == 630);
  LMDJ_CHECK(applied.at(2).kind == lmdj::audio::FxGestureKind::hold_on);
  LMDJ_CHECK(applied.at(3).kind == lmdj::audio::FxGestureKind::hold_off);
  LMDJ_CHECK(applied.at(4).kind == lmdj::audio::FxGestureKind::release);
  LMDJ_CHECK(applied.at(4).fx == lmdj::domain::PerformanceFx::filter);

  // A replayed receipt is not a second audible gesture.
  check_ok(application.command(
      event("10000000-0000-4000-8000-000000000022",
            {{"kind", "fx_engage"},
             {"gesture_id", kFxGesture},
             {"fx", "filter"},
             {"value", 500}})));
  LMDJ_CHECK(sink->applied().size() == 5);
}

// A refused gesture is not admitted: the master bus and the journal never
// disagree about what the Performance sounded like.
void test_refused_live_gesture_leaves_no_journalled_event() {
  TempDirectory temp;
  auto sink = std::make_shared<GestureSink>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      std::make_shared<LaunchAcknowledger>(),
      lmdj::facade::make_unavailable_performance_replay_controller(),
      sink,
  };
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "project.lmdj";
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", kProject},
                                {"bpm", 120}}));
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", kBegin},
                                {"expected_revision", 0},
                                {"session_id", kSession},
                                {"performance_id", kPerformance}}));

  sink->refuse_next(1);
  const auto refused =
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000030"},
                           {"event",
                            {{"kind", "fx_engage"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"},
                             {"value", 500}}}});
  LMDJ_CHECK(!refused.at("ok").get<bool>());
  lmdj::project_io::SequenceJournal journal;
  const auto after = journal.read_active_performance(bundle);
  LMDJ_CHECK(after.has_value());
  LMDJ_CHECK(after.value().pending_events.empty());

  // The same event id is still admissible once the master bus accepts it.
  check_ok(application.command(
      {{"operation", "performance.record.event"},
       {"project_path", bundle.generic_string()},
       {"session_id", kSession},
       {"event_id", "10000000-0000-4000-8000-000000000030"},
       {"event",
        {{"kind", "fx_engage"},
         {"gesture_id", kFxGesture},
         {"fx", "filter"},
         {"value", 500}}}}));
  LMDJ_CHECK(sink->applied().size() == 1);
}

// Session-free FX admission (#1674): performance.fx.gesture applies a gesture
// live to the master bus with no recording session, no project and no journal,
// so FX are audible whenever audio runs.
void test_session_free_fx_gesture_reaches_the_master_bus() {
  TempDirectory temp;
  auto sink = std::make_shared<GestureSink>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      std::make_shared<LaunchAcknowledger>(),
      lmdj::facade::make_unavailable_performance_replay_controller(),
      sink,
  };
  lmdj::facade::Application application(std::move(config));

  const auto gesture = [](nlohmann::json payload) {
    return nlohmann::json{{"operation", "performance.fx.gesture"},
                          {"event", std::move(payload)}};
  };
  check_ok(application.command(
      gesture({{"kind", "fx_engage"}, {"fx", "filter"}, {"value", 500}})));
  check_ok(application.command(
      gesture({{"kind", "fx_move"}, {"fx", "filter"}, {"value", 630}})));
  check_ok(application.command(gesture({{"kind", "hold_on"}})));
  check_ok(application.command(gesture({{"kind", "hold_off"}})));
  check_ok(application.command(
      gesture({{"kind", "fx_release"}, {"fx", "filter"}})));

  const auto &applied = sink->applied();
  LMDJ_CHECK(applied.size() == 5);
  LMDJ_CHECK(applied.at(0).kind == lmdj::audio::FxGestureKind::engage);
  LMDJ_CHECK(applied.at(0).fx == lmdj::domain::PerformanceFx::filter);
  LMDJ_CHECK(applied.at(0).value == 500);
  LMDJ_CHECK(applied.at(1).kind == lmdj::audio::FxGestureKind::move);
  LMDJ_CHECK(applied.at(1).value == 630);
  LMDJ_CHECK(applied.at(2).kind == lmdj::audio::FxGestureKind::hold_on);
  LMDJ_CHECK(applied.at(3).kind == lmdj::audio::FxGestureKind::hold_off);
  LMDJ_CHECK(applied.at(4).kind == lmdj::audio::FxGestureKind::release);
  LMDJ_CHECK(applied.at(4).fx == lmdj::domain::PerformanceFx::filter);

  // Nothing is journaled: no project exists and none is created.
  LMDJ_CHECK(std::filesystem::is_empty(temp.path()));
}

void test_session_free_fx_gesture_refusals_fail_closed() {
  TempDirectory temp;
  auto sink = std::make_shared<GestureSink>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      std::make_shared<LaunchAcknowledger>(),
      lmdj::facade::make_unavailable_performance_replay_controller(),
      sink,
  };
  lmdj::facade::Application application(std::move(config));
  const auto gesture = [](nlohmann::json payload) {
    return nlohmann::json{{"operation", "performance.fx.gesture"},
                          {"event", std::move(payload)}};
  };

  LMDJ_CHECK(!application
                  .command(gesture({{"kind", "fx_engage"},
                                    {"fx", "flanger"},
                                    {"value", 500}}))
                  .at("ok")
                  .get<bool>());
  LMDJ_CHECK(!application
                  .command(gesture({{"kind", "fx_engage"},
                                    {"fx", "filter"},
                                    {"value", 1001}}))
                  .at("ok")
                  .get<bool>());
  LMDJ_CHECK(!application
                  .command(gesture({{"kind", "fx_engage"}, {"fx", "filter"}}))
                  .at("ok")
                  .get<bool>());
  LMDJ_CHECK(
      !application.command(gesture({{"kind", "pad_press"}})).at("ok").get<bool>());
  LMDJ_CHECK(sink->applied().empty());

  sink->refuse_next(1);
  const auto refused = application.command(
      gesture({{"kind", "fx_engage"}, {"fx", "filter"}, {"value", 500}}));
  LMDJ_CHECK(!refused.at("ok").get<bool>());
  LMDJ_CHECK(refused.at("error").at("code") == "INTERNAL_ERROR");
  LMDJ_CHECK(sink->applied().empty());

  lmdj::facade::Application engineless({
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  });
  const auto unavailable = engineless.command(
      gesture({{"kind", "fx_engage"}, {"fx", "filter"}, {"value", 500}}));
  LMDJ_CHECK(!unavailable.at("ok").get<bool>());
  LMDJ_CHECK(unavailable.at("error").at("details").at("reason") ==
             "performance_fx_authority_unavailable");
}

// ---------------------------------------------------------------------------
// D0/P1 headered-profile fixtures: an honest in-memory LiveControlSink (no
// engine) implementing the same accepted-state derivation the adapter owns,
// plus a settable clock.
// ---------------------------------------------------------------------------

class SettableClock final : public lmdj::facade::PerformanceClock {
public:
  void anchor(std::uint16_t, std::uint64_t at_tick) override {
    current_ = std::max(current_, at_tick);
  }
  lmdj::foundation::Result<std::uint64_t> read_tick() override {
    return lmdj::foundation::Result<std::uint64_t>::success(current_);
  }
  void set(std::uint64_t tick) { current_ = tick; }

private:
  std::uint64_t current_{};
};

class FakeLiveControl final
    : public lmdj::facade::PerformanceLiveControlSink {
public:
  static constexpr std::string_view kEpoch =
      "11111111-1111-4111-8111-111111111111";

  std::optional<std::string> current_control_epoch() override {
    return epoch_;
  }
  std::optional<std::string> bound_control_project() override {
    return bound_;
  }
  lmdj::foundation::Result<std::string> bind_control_target(
      std::string project_uuid) override {
    if (!epoch_.has_value() || bound_ != project_uuid) {
      epoch_ = std::string{kEpoch};
      bound_ = project_uuid;
    }
    return lmdj::foundation::Result<std::string>::success(*epoch_);
  }
  void invalidate_control_target() override {
    epoch_.reset();
    bound_.reset();
  }

  lmdj::facade::PerformanceLiveControlSnapshot live_control_snapshot()
      override {
    return {state_, applied_state_, accepted_sequence_, applied_sequence_, 1};
  }

  lmdj::foundation::Result<lmdj::facade::PerformanceLiveControlReservation>
  reserve_live_control(
      const std::string& control_epoch,
      const lmdj::facade::PerformanceLiveControlIntent& intent) override {
    if (!epoch_.has_value() || *epoch_ != control_epoch) {
      return failure("stale epoch");
    }
    if (reserve_failures_ != 0) {
      --reserve_failures_;
      return failure("injected reserve failure");
    }
    ++reserve_calls_;
    lmdj::facade::PerformanceLiveControlReservation reservation;
    auto next = state_;
    const auto filter_index =
        static_cast<std::size_t>(lmdj::domain::PerformanceFx::filter);
    switch (intent.kind) {
      case lmdj::facade::PerformanceLiveControlIntent::Kind::
          filter_parameter: {
        auto independent =
            next.state.filter.index() == 1
                ? std::get<lmdj::domain::IndependentFilterLiveState>(
                      next.state.filter)
                : lmdj::domain::IndependentFilterLiveState{};
        switch (intent.parameter) {
          case lmdj::facade::PerformanceLiveControlIntent::FilterParameter::
              type:
            independent.type =
                static_cast<lmdj::domain::PerformanceFilterType>(
                    intent.value);
            break;
          case lmdj::facade::PerformanceLiveControlIntent::FilterParameter::
              cutoff_hz:
            if (intent.value < 20 || intent.value > 20'000) {
              return failure("cutoff out of range");
            }
            independent.cutoff_hz =
                static_cast<std::uint16_t>(intent.value);
            break;
          case lmdj::facade::PerformanceLiveControlIntent::FilterParameter::
              resonance_milli:
            if (intent.value > 1'000) {
              return failure("resonance out of range");
            }
            independent.resonance_milli =
                static_cast<std::uint16_t>(intent.value);
            break;
        }
        if (intent.phase == lmdj::domain::PerformanceFilterPhase::engage) {
          independent.engaged = true;
          independent.frozen = false;
          reservation.assigned_generation = next_generation();
          next.runtime_generations.at(filter_index) =
              reservation.assigned_generation;
        } else {
          if (!intent.gesture_generation.has_value() ||
              state_.runtime_generations.at(filter_index) !=
                  *intent.gesture_generation) {
            return failure("binding mismatch");
          }
        }
        next.state.filter = independent;
        reservation.filter_gesture = lmdj::audio::FilterGesture{};
        break;
      }
      case lmdj::facade::PerformanceLiveControlIntent::Kind::
          filter_release: {
        if (!intent.gesture_generation.has_value() ||
            state_.runtime_generations.at(filter_index) !=
                *intent.gesture_generation) {
          return failure("binding mismatch");
        }
        auto &independent =
            std::get<lmdj::domain::IndependentFilterLiveState>(
                next.state.filter);
        independent.engaged = false;
        independent.frozen = next.state.hold;
        next.runtime_generations.at(filter_index).reset();
        reservation.filter_gesture = lmdj::audio::FilterGesture{};
        break;
      }
      case lmdj::facade::PerformanceLiveControlIntent::Kind::fx_parameter: {
        const auto index = static_cast<std::size_t>(intent.fx);
        if (intent.phase == lmdj::domain::PerformanceFilterPhase::engage) {
          reservation.assigned_generation = next_generation();
          next.runtime_generations.at(index) =
              reservation.assigned_generation;
          set_fx(next, intent.fx, true, false,
                 static_cast<std::uint16_t>(intent.value));
        } else {
          if (!intent.gesture_generation.has_value() ||
              state_.runtime_generations.at(index) !=
                  *intent.gesture_generation) {
            return failure("binding mismatch");
          }
          set_fx(next, intent.fx, std::nullopt, std::nullopt,
                 static_cast<std::uint16_t>(intent.value));
        }
        reservation.fx_gesture = lmdj::audio::FxGesture{};
        break;
      }
      case lmdj::facade::PerformanceLiveControlIntent::Kind::fx_release: {
        const auto index = static_cast<std::size_t>(intent.fx);
        if (!intent.gesture_generation.has_value() ||
            state_.runtime_generations.at(index) !=
                *intent.gesture_generation) {
          return failure("binding mismatch");
        }
        set_fx(next, intent.fx, false, next.state.hold, std::nullopt);
        next.runtime_generations.at(index).reset();
        reservation.fx_gesture = lmdj::audio::FxGesture{};
        break;
      }
      case lmdj::facade::PerformanceLiveControlIntent::Kind::pad_mute:
      case lmdj::facade::PerformanceLiveControlIntent::Kind::pad_solo: {
        const auto bit = std::uint64_t{1} << intent.slot;
        auto &mask = intent.kind ==
                             lmdj::facade::PerformanceLiveControlIntent::
                                 Kind::pad_mute
                         ? next.state.muted_mask
                         : next.state.solo_mask;
        mask = intent.enabled ? (mask | bit) : (mask & ~bit);
        reservation.pad_gates =
            lmdj::audio::PadGatesState{next.state.muted_mask,
                                       next.state.solo_mask};
        break;
      }
      case lmdj::facade::PerformanceLiveControlIntent::Kind::
          clear_pad_gates:
        next.state.muted_mask = 0;
        next.state.solo_mask = 0;
        reservation.pad_gates = lmdj::audio::PadGatesState{0, 0};
        break;
      case lmdj::facade::PerformanceLiveControlIntent::Kind::hold_on:
      case lmdj::facade::PerformanceLiveControlIntent::Kind::hold_off:
        next.state.hold = intent.kind ==
                          lmdj::facade::PerformanceLiveControlIntent::Kind::
                              hold_on;
        reservation.fx_gesture = lmdj::audio::FxGesture{};
        break;
    }
    reservation.resulting_state = next;
    reservation.control_sequence = accepted_sequence_ + 1;
    return lmdj::foundation::Result<
        lmdj::facade::PerformanceLiveControlReservation>::success(
        std::move(reservation));
  }

  lmdj::foundation::Result<lmdj::facade::PerformanceLiveControlReservation>
  reserve_live_control_republish(
      const std::string& control_epoch,
      std::optional<lmdj::audio::FxGesture> fx_gesture,
      std::optional<lmdj::audio::FilterGesture> filter_gesture,
      std::optional<lmdj::audio::PadGatesState> pad_gates,
      lmdj::facade::PerformanceLiveControlState resulting_state,
      std::optional<std::string> assigned_generation) override {
    if (!epoch_.has_value() || *epoch_ != control_epoch) {
      return failure("stale epoch");
    }
    ++republish_calls_;
    lmdj::facade::PerformanceLiveControlReservation reservation;
    reservation.fx_gesture = fx_gesture;
    reservation.filter_gesture = filter_gesture;
    reservation.pad_gates = pad_gates;
    reservation.resulting_state = std::move(resulting_state);
    reservation.assigned_generation = std::move(assigned_generation);
    reservation.control_sequence = accepted_sequence_ + 1;
    return lmdj::foundation::Result<
        lmdj::facade::PerformanceLiveControlReservation>::success(
        std::move(reservation));
  }

  lmdj::foundation::Result<void> publish_live_control(
      lmdj::facade::PerformanceLiveControlReservation reservation) override {
    if (publish_failures_ != 0) {
      --publish_failures_;
      return lmdj::foundation::Result<void>::failure(
          {lmdj::foundation::ErrorCode::internal_error,
           "injected publish failure"});
    }
    ++publish_calls_;
    state_ = reservation.resulting_state;
    ++accepted_sequence_;
    return lmdj::foundation::Result<void>::success();
  }

  void cancel_live_control(
      lmdj::facade::PerformanceLiveControlReservation) noexcept override {
    ++cancel_calls_;
  }

  lmdj::foundation::Result<lmdj::facade::PerformanceControlFence> begin_fence(
      const std::string& control_epoch) override {
    if (!epoch_.has_value() || *epoch_ != control_epoch) {
      return lmdj::foundation::Result<
          lmdj::facade::PerformanceControlFence>::failure(
          {lmdj::foundation::ErrorCode::invalid_argument, "stale epoch"});
    }
    if (fence_failures_ != 0) {
      --fence_failures_;
      return lmdj::foundation::Result<
          lmdj::facade::PerformanceControlFence>::failure(
          {lmdj::foundation::ErrorCode::internal_error,
           "the master FX gesture queue is full"});
    }
    fence_ = lmdj::facade::PerformanceControlFence{
        accepted_sequence_, 1, state_};
    return lmdj::foundation::Result<
        lmdj::facade::PerformanceControlFence>::success(*fence_);
  }

  lmdj::facade::PerformanceFenceReadiness fence_readiness(
      const lmdj::facade::PerformanceControlFence&) override {
    return readiness_;
  }

  // Test controls.
  void set_accepted(lmdj::facade::PerformanceLiveControlState state) {
    state_ = std::move(state);
  }
  void set_readiness(lmdj::facade::PerformanceFenceReadiness readiness) {
    readiness_ = readiness;
  }
  void fail_reserves(std::size_t count) { reserve_failures_ = count; }
  void fail_publishes(std::size_t count) { publish_failures_ = count; }
  void fail_fences(std::size_t count) { fence_failures_ = count; }
  std::size_t publish_calls() const { return publish_calls_; }
  std::size_t reserve_calls() const { return reserve_calls_; }
  std::size_t republish_calls() const { return republish_calls_; }
  std::size_t cancel_calls() const { return cancel_calls_; }
  const lmdj::facade::PerformanceLiveControlState& accepted() const {
    return state_;
  }

private:
  static lmdj::foundation::Result<
      lmdj::facade::PerformanceLiveControlReservation>
  failure(const char* message) {
    return lmdj::foundation::Result<
        lmdj::facade::PerformanceLiveControlReservation>::failure(
        {lmdj::foundation::ErrorCode::invalid_argument, message});
  }

  std::string next_generation() {
    char buffer[37];
    std::snprintf(buffer, sizeof buffer,
                  "20000000-0000-4000-8000-%012zu", ++generation_counter_);
    return buffer;
  }

  static void set_fx(lmdj::facade::PerformanceLiveControlState& state,
                     lmdj::domain::PerformanceFx fx,
                     std::optional<bool> engaged, std::optional<bool> frozen,
                     std::optional<std::uint16_t> value) {
    if (fx == lmdj::domain::PerformanceFx::filter) {
      if (state.state.filter.index() != 0) {
        return;
      }
      auto& legacy =
          std::get<lmdj::domain::LegacyFilterLiveState>(state.state.filter);
      if (engaged.has_value()) legacy.engaged = *engaged;
      if (frozen.has_value()) legacy.frozen = *frozen;
      if (value.has_value()) legacy.value = *value;
      return;
    }
    auto& stage =
        state.state.other_fx.at(static_cast<std::size_t>(fx) - 1);
    if (engaged.has_value()) stage.engaged = *engaged;
    if (frozen.has_value()) stage.frozen = *frozen;
    if (value.has_value()) stage.value = *value;
  }

  std::optional<std::string> epoch_;
  std::optional<std::string> bound_;
  lmdj::facade::PerformanceLiveControlState state_{};
  lmdj::facade::PerformanceLiveControlState applied_state_{};
  std::uint64_t accepted_sequence_{};
  std::uint64_t applied_sequence_{};
  std::optional<lmdj::facade::PerformanceControlFence> fence_;
  lmdj::facade::PerformanceFenceReadiness readiness_{
      lmdj::facade::PerformanceFenceReadiness::pending};
  std::size_t reserve_failures_{};
  std::size_t publish_failures_{};
  std::size_t fence_failures_{};
  std::size_t reserve_calls_{};
  std::size_t publish_calls_{};
  std::size_t republish_calls_{};
  std::size_t cancel_calls_{};
  std::size_t generation_counter_{};
};

// A headered-profile Application wired with the fake live-control port.
struct HeaderedFixture {  explicit HeaderedFixture(
      std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> storage =
          nullptr) {
    live = std::make_shared<FakeLiveControl>();
    clock = std::make_shared<SettableClock>();
    sequencer = std::make_shared<Sequencer>();
    acknowledger = std::make_shared<LaunchAcknowledger>();
    config = lmdj::facade::ApplicationConfig{
        temp.path(),
        nullptr,
        {},
        {},
        std::nullopt,
        storage,
        clock,
        sequencer,
        acknowledger,
        lmdj::facade::make_unavailable_performance_replay_controller(),
    };
    config.performance_live_control = live;
    application.emplace(std::move(config));
  }

  void create_project(std::string_view project_id = kProject) {
    check_ok(application->command({{"operation", "project.create"},
                                   {"project_path", bundle().generic_string()},
                                   {"project_id", std::string(project_id)},
                                   {"bpm", 120}}));
  }

  const std::filesystem::path& bundle() const { return bundle_; }

  nlohmann::json begin_headered(
      std::string_view session = kSession,
      std::string_view performance = kPerformance,
      std::string_view command = kBegin) {
    return application->command(
        {{"operation", "performance.record.begin"},
         {"project_path", bundle().generic_string()},
         {"command_id", std::string(command)},
         {"expected_revision", 0},
         {"session_id", std::string(session)},
         {"performance_id", std::string(performance)},
         {"control_epoch", std::string(FakeLiveControl::kEpoch)}});
  }

  nlohmann::json record_event(
      std::string_view event_id, nlohmann::json event,
      std::string_view expected, std::string_view session = kSession) {
    return application->command(
        {{"operation", "performance.record.event"},
         {"project_path", bundle().generic_string()},
         {"session_id", std::string(session)},
         {"event_id", std::string(event_id)},
         {"event", std::move(event)},
         {"control_epoch", std::string(FakeLiveControl::kEpoch)},
         {"expected_recording_sequence", std::string(expected)}});
  }

  nlohmann::json record_status() {
    return application->query({{"operation", "performance.record.status"},
                               {"project_path", bundle().generic_string()}});
  }

  void mark_ready() {
    live->set_readiness(lmdj::facade::PerformanceFenceReadiness::ready);
    check_ok(record_status());  // latches core_control_ready
  }

  TempDirectory temp;
  std::filesystem::path bundle_ =
      temp.path() / "headered.lmdj";
  std::shared_ptr<FakeLiveControl> live;
  std::shared_ptr<SettableClock> clock;
  std::shared_ptr<Sequencer> sequencer;
  std::shared_ptr<LaunchAcknowledger> acknowledger;
  lmdj::facade::ApplicationConfig config;
  std::optional<lmdj::facade::Application> application;
};

// Status counts open recording gestures in both profiles, not merely sounding
// effects. Frozen-only Reverb is deliberately audible without an open binding.
void test_headered_status_counts_fx_and_filter_across_reopen_and_stop() {
  HeaderedFixture fixture;
  fixture.create_project();
  auto initial = lmdj::facade::PerformanceLiveControlState{};
  initial.state.hold = true;
  initial.state.other_fx.at(0) = {true, false, 500};
  initial.state.other_fx.at(1) = {false, true, 700};
  initial.state.filter = lmdj::domain::IndependentFilterLiveState{
      true, false, lmdj::domain::PerformanceFilterType::lp, 1'000, 100};
  initial.runtime_generations.at(0) =
      "20000000-0000-4000-8000-000000000001";
  initial.runtime_generations.at(1) =
      "20000000-0000-4000-8000-000000000002";
  fixture.live->set_accepted(initial);
  const auto begun = fixture.begin_headered();
  check_ok(begun);
  fixture.mark_ready();
  const auto count = [&] {
    const auto status = fixture.record_status();
    check_ok(status);
    return status.at("result").at("open_fx_gestures").get<std::size_t>();
  };
  const auto durable_count = [&] {
    // This Application has no in-memory Performance session: query must use
    // the durable checkpoint, without attaching or replaying any gesture.
    lmdj::facade::Application reader{
        lmdj::facade::ApplicationConfig{
            fixture.temp.path(), nullptr, {}, {}, std::nullopt, nullptr,
            nullptr, nullptr, nullptr,
            lmdj::facade::make_unavailable_performance_replay_controller()}};
    const auto status = reader.query({
        {"operation", "performance.record.status"},
        {"project_path", fixture.bundle().generic_string()}});
    check_ok(status);
    return status.at("result").at("open_fx_gestures").get<std::size_t>();
  };
  LMDJ_CHECK(count() == 2U); // Delay + independent Filter; excludes frozen Reverb.
  LMDJ_CHECK(durable_count() == 2U);
  LMDJ_CHECK(fixture.live->publish_calls() == 0U); // queries are read-only

  nlohmann::json delay_binding;
  nlohmann::json filter_binding;
  for (const auto& binding : begun.at("result").at("fx_bindings")) {
    if (binding.at("fx") == "delay") delay_binding = binding;
    if (binding.at("fx") == "filter") filter_binding = binding;
  }
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000601",
      {{"kind", "fx_release"}, {"fx", "delay"},
       {"gesture_id", delay_binding.at("recording_gesture_id")},
       {"gesture_generation", delay_binding.at("gesture_generation")}}, "0"));
  LMDJ_CHECK(count() == 1U);
  LMDJ_CHECK(durable_count() == 1U);
  LMDJ_CHECK(fixture.live->accepted().state.other_fx.at(0).frozen);
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000602",
      {{"kind", "filter_release"},
       {"gesture_id", filter_binding.at("recording_gesture_id")},
       {"gesture_generation", filter_binding.at("gesture_generation")}}, "1"));
  LMDJ_CHECK(count() == 0U);
  LMDJ_CHECK(durable_count() == 0U);

  const auto engaged = fixture.record_event(
      "10000000-0000-4000-8000-000000000603",
      {{"kind", "fx_engage"}, {"fx", "delay"}, {"value", 620}}, "2");
  check_ok(engaged);
  LMDJ_CHECK(count() == 1U);
  LMDJ_CHECK(durable_count() == 1U);
  const auto& binding = engaged.at("result");
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000604",
      {{"kind", "fx_move"}, {"fx", "delay"}, {"value", 650},
       {"gesture_id", binding.at("recording_gesture_id")},
       {"gesture_generation", binding.at("gesture_generation")}}, "3"));
  LMDJ_CHECK(count() == 1U);
  check_ok(fixture.application->command({
      {"operation", "performance.record.stop"},
      {"project_path", fixture.bundle().generic_string()},
      {"session_id", std::string(kSession)},
      {"request_id", "10000000-0000-4000-8000-000000000605"}}));
  LMDJ_CHECK(count() == 0U);
  LMDJ_CHECK(durable_count() == 0U);
}

// P1 oracle: begin fence mapping — pre-begin engaged Delay 500 + HOLD frozen
// Reverb 700. The mapping contains only Delay; the begin publishes nothing
// (no fake engage, no DSP reset); the first Pad waits for the applied proof.
void test_headered_begin_fence_mapping_and_first_pad_gate() {
  HeaderedFixture fixture;
  fixture.create_project();
  auto initial = lmdj::facade::PerformanceLiveControlState{};
  initial.state.hold = true;
  initial.state.other_fx.at(0) = {true, false, 500};   // delay engaged
  initial.state.other_fx.at(1) = {false, true, 700};   // reverb frozen-only
  initial.runtime_generations.at(1) =
      "20000000-0000-4000-8000-000000000001";
  fixture.live->set_accepted(initial);

  const auto begun = fixture.begin_headered();
  check_ok(begun);
  const auto &result = begun.at("result");
  LMDJ_CHECK(result.at("profile") == "header_input_sequence");
  LMDJ_CHECK(result.at("core_control_ready") == false);
  LMDJ_CHECK(result.at("next_recording_sequence") == "0");
  LMDJ_CHECK(result.at("fx_bindings").size() == 1U);
  LMDJ_CHECK(result.at("fx_bindings").at(0).at("fx") == "delay");
  LMDJ_CHECK(result.at("fx_bindings").at(0).at("gesture_generation") ==
             "20000000-0000-4000-8000-000000000001");
  // The fence publishes nothing: no engage/move reached the bus.
  LMDJ_CHECK(fixture.live->publish_calls() == 0);

  // The durable header holds both sounding states; only the engaged Delay is
  // an open checkpoint gesture (frozen-only Reverb has none).
  lmdj::project_io::SequenceJournal journal;
  const auto durable = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(durable.has_value());
  LMDJ_CHECK(durable.value().initial_live_state.has_value());
  LMDJ_CHECK(durable.value().initial_live_state->hold);
  LMDJ_CHECK(
      durable.value().initial_live_state->other_fx.at(0).engaged);
  LMDJ_CHECK(
      durable.value().initial_live_state->other_fx.at(0).value == 500);
  LMDJ_CHECK(
      durable.value().initial_live_state->other_fx.at(1).frozen);
  LMDJ_CHECK(durable.value().transient_checkpoint.has_value());
  LMDJ_CHECK(durable.value().transient_checkpoint->open_fx.size() == 1U);
  LMDJ_CHECK(durable.value()
                 .transient_checkpoint->open_fx.front()
                 .fx == lmdj::domain::PerformanceFx::delay);
  LMDJ_CHECK(!durable.value().transient_checkpoint->open_filter.has_value());
  LMDJ_CHECK(durable.value().admission_ledger.has_value());
  LMDJ_CHECK(
      durable.value().admission_ledger->next_recording_sequence == 0);

  // The first Pad admission is refused before the fence's applied proof.
  const auto early_pad = fixture.record_event(
      "10000000-0000-4000-8000-000000000100",
      {{"kind", "pad_press"},
       {"gesture_id", "10000000-0000-4000-8000-000000000101"},
       {"slot", 5},
       {"velocity", 100}},
      "0");
  LMDJ_CHECK(!early_pad.at("ok").get<bool>());
  LMDJ_CHECK(early_pad.at("error").at("details").at("reason") ==
             "performance_control_not_ready");
  LMDJ_CHECK(journal.read_active_performance(fixture.bundle())
                 .value()
                 .pending_events.empty());

  // The durable header does not move when a control changes mid-fence.
  fixture.clock->set(4);
  const auto move_during_fence = fixture.record_event(
      "10000000-0000-4000-8000-000000000102",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 600},
       {"gesture_id",
        result.at("fx_bindings").at(0).at("recording_gesture_id")},
       {"gesture_generation", "20000000-0000-4000-8000-000000000001"}},
      "0");
  check_ok(move_during_fence);
  LMDJ_CHECK(fixture.live->publish_calls() == 1);
  LMDJ_CHECK(journal.read_active_performance(fixture.bundle())
                 .value()
                 .initial_live_state->other_fx.at(0)
                 .value == 500);

  // A stale generation cannot impersonate the binding.
  const auto stale = fixture.record_event(
      "10000000-0000-4000-8000-000000000103",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 610},
       {"gesture_id",
        result.at("fx_bindings").at(0).at("recording_gesture_id")},
       {"gesture_generation", "20000000-0000-4000-8000-999999999999"}},
      "1");
  LMDJ_CHECK(!stale.at("ok").get<bool>());
  LMDJ_CHECK(fixture.live->publish_calls() == 1);

  fixture.mark_ready();
  const auto status = fixture.record_status();
  LMDJ_CHECK(status.at("result").at("core_control_ready") == true);
  LMDJ_CHECK(status.at("result").at("profile") == "header_input_sequence");

  fixture.clock->set(10);
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000104",
      {{"kind", "pad_press"},
       {"gesture_id", "10000000-0000-4000-8000-000000000101"},
       {"slot", 5},
       {"velocity", 100}},
      "1"));
  fixture.clock->set(20);
  const auto released = fixture.record_event(
      "10000000-0000-4000-8000-000000000105",
      {{"kind", "pad_release"},
       {"gesture_id", "10000000-0000-4000-8000-000000000101"},
       {"slot", 5}},
      "2");
  check_ok(released);
  // The PadHit carries its press's durable input sequence, not the release's.
  const auto after = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(after.has_value());
  LMDJ_CHECK(after.value().pending_events.size() == 2U);
  const auto &hit = after.value().pending_events.at(1);
  LMDJ_CHECK(std::get<lmdj::domain::PadHitPerformanceEvent>(hit.payload)
                 .duration_tick == 10);
  LMDJ_CHECK(hit.input_sequence == 2);
  LMDJ_CHECK(after.value().last_input_sequence == 3);

  // The first move600/release pair with the mapping, then HOLD lifecycle.
  const auto move = fixture.record_event(
      "10000000-0000-4000-8000-000000000106",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 600},
       {"gesture_id",
        result.at("fx_bindings").at(0).at("recording_gesture_id")},
       {"gesture_generation", "20000000-0000-4000-8000-000000000001"}},
      "3");
  check_ok(move);
  LMDJ_CHECK(move.at("result").at("coalesced") == false);
  const auto release = fixture.record_event(
      "10000000-0000-4000-8000-000000000107",
      {{"kind", "fx_release"},
       {"fx", "delay"},
       {"gesture_id",
        result.at("fx_bindings").at(0).at("recording_gesture_id")},
       {"gesture_generation", "20000000-0000-4000-8000-000000000001"}},
      "4");
  check_ok(release);
}

// P1 oracle: the no-coalescing counterexample. Move500@(16) → Pad@(32) →
// Move900@(64) all survive with their own tick and sequence; the PadHit at 32
// reads the 500 state; same-tick control/Pad order follows receive order.
void test_headered_profile_preserves_every_move_and_same_tick_order() {
  HeaderedFixture fixture;
  fixture.create_project();
  check_ok(fixture.begin_headered());
  fixture.mark_ready();

  const auto engage = fixture.record_event(
      "10000000-0000-4000-8000-000000000200",
      {{"kind", "fx_engage"}, {"fx", "delay"}, {"value", 0}}, "0");
  check_ok(engage);
  const auto gesture_id =
      engage.at("result").at("recording_gesture_id").get<std::string>();
  const auto generation =
      engage.at("result").at("gesture_generation").get<std::string>();

  fixture.clock->set(16);
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000201",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id", gesture_id},
       {"gesture_generation", generation}},
      "1"));
  fixture.clock->set(32);
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000202",
      {{"kind", "pad_press"},
       {"gesture_id", "10000000-0000-4000-8000-000000000203"},
       {"slot", 0},
       {"velocity", 127}},
      "2"));
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000204",
      {{"kind", "pad_release"},
       {"gesture_id", "10000000-0000-4000-8000-000000000203"},
       {"slot", 0}},
      "3"));
  fixture.clock->set(64);
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000205",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 900},
       {"gesture_id", gesture_id},
       {"gesture_generation", generation}},
      "4"));

  lmdj::project_io::SequenceJournal journal;
  const auto durable = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(durable.has_value());
  const auto &events = durable.value().pending_events;
  LMDJ_CHECK(events.size() == 4U);
  const auto move_at = [](const lmdj::domain::PerformanceEvent &event) {
    return std::get<lmdj::domain::FxMovePerformanceEvent>(event.payload);
  };
  LMDJ_CHECK(move_at(events.at(1)).value == 500);
  LMDJ_CHECK(move_at(events.at(1)).tick == 16);
  LMDJ_CHECK(events.at(1).input_sequence == 2);
  const auto &hit =
      std::get<lmdj::domain::PadHitPerformanceEvent>(events.at(2).payload);
  LMDJ_CHECK(hit.onset_tick == 32);
  LMDJ_CHECK(events.at(2).input_sequence == 3);
  LMDJ_CHECK(move_at(events.at(3)).value == 900);
  LMDJ_CHECK(move_at(events.at(3)).tick == 64);
  LMDJ_CHECK(events.at(3).input_sequence == 5);

  // Same tick, control → Pad: the control keeps its earlier sequence.
  fixture.clock->set(100);
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000206",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 700},
       {"gesture_id", gesture_id},
       {"gesture_generation", generation}},
      "5"));
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000207",
      {{"kind", "pad_press"},
       {"gesture_id", "10000000-0000-4000-8000-000000000208"},
       {"slot", 1},
       {"velocity", 100}},
      "6"));
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000209",
      {{"kind", "pad_release"},
       {"gesture_id", "10000000-0000-4000-8000-000000000208"},
       {"slot", 1}},
      "7"));
  // Same tick, Pad → control: the Pad keeps its earlier sequence.
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000210",
      {{"kind", "pad_press"},
       {"gesture_id", "10000000-0000-4000-8000-000000000211"},
       {"slot", 2},
       {"velocity", 90}},
      "8"));
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000212",
      {{"kind", "pad_release"},
       {"gesture_id", "10000000-0000-4000-8000-000000000211"},
       {"slot", 2}},
      "9"));
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000213",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 450},
       {"gesture_id", gesture_id},
       {"gesture_generation", generation}},
      "10"));

  const auto after = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(after.has_value());
  const auto &ordered = after.value().pending_events;
  // Canonical order is (tick, input_sequence): same-tick pairs stay in
  // receive order in both directions.
  std::optional<std::uint64_t> previous_sequence;
  for (const auto &event : ordered) {
    const auto tick = lmdj::domain::performance_event_tick(event);
    if (tick == 100 && event.input_sequence.has_value()) {
      if (previous_sequence.has_value()) {
        LMDJ_CHECK(*event.input_sequence > *previous_sequence);
      }
      previous_sequence = *event.input_sequence;
    }
  }
  LMDJ_CHECK(previous_sequence.has_value());
}

// P1 oracle: exact retry / collision / retry-expired / out-of-order / stale
// epoch — every refusal leaves the far side untouched (zero publish).
void test_headered_exact_retry_collision_expired_and_stale_epoch() {
  HeaderedFixture fixture;
  fixture.create_project();
  const auto begun = fixture.begin_headered();
  check_ok(begun);
  fixture.mark_ready();
  const auto generation =
      begun.at("result").at("fx_bindings").empty()
          ? std::string{}
          : std::string{};
  (void)generation;
  // Engage Delay first so moves have a binding.
  const auto engage = fixture.record_event(
      "10000000-0000-4000-8000-000000000300",
      {{"kind", "fx_engage"}, {"fx", "delay"}, {"value", 100}}, "0");
  check_ok(engage);
  const auto gesture_id =
      engage.at("result").at("recording_gesture_id").get<std::string>();
  const auto gen =
      engage.at("result").at("gesture_generation").get<std::string>();

  const auto c1 = fixture.record_event(
      "10000000-0000-4000-8000-000000000301",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  check_ok(c1);
  LMDJ_CHECK(c1.at("result").at("input_sequence") == "2");
  LMDJ_CHECK(c1.at("result").at("next_recording_sequence") == "2");
  const auto publishes_after_c1 = fixture.live->publish_calls();

  // Exact retry: the original receipt, zero new publish.
  const auto retry = fixture.record_event(
      "10000000-0000-4000-8000-000000000301",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  check_ok(retry);
  LMDJ_CHECK(retry.at("result").at("replayed") == true);
  LMDJ_CHECK(fixture.live->publish_calls() == publishes_after_c1);

  // Same identity, changed payload: collision, zero publish.
  const auto collision = fixture.record_event(
      "10000000-0000-4000-8000-000000000301",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 900},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  LMDJ_CHECK(!collision.at("ok").get<bool>());
  LMDJ_CHECK(collision.at("error").at("details").at("reason") ==
             "performance_admission_collision");
  LMDJ_CHECK(fixture.live->publish_calls() == publishes_after_c1);

  // C2 completes the window.
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000302",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 900},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "2"));

  // C1's original wire is expired: zero enqueue, unknown by design.
  const auto expired = fixture.record_event(
      "10000000-0000-4000-8000-000000000301",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  LMDJ_CHECK(!expired.at("ok").get<bool>());
  LMDJ_CHECK(expired.at("error").at("details").at("reason") ==
             "performance_recording_retry_expired");
  const auto out_of_order = fixture.record_event(
      "10000000-0000-4000-8000-000000000303",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 200},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "7");
  LMDJ_CHECK(!out_of_order.at("ok").get<bool>());
  LMDJ_CHECK(out_of_order.at("error").at("details").at("reason") ==
             "performance_admission_out_of_order");
  LMDJ_CHECK(fixture.live->publish_calls() == publishes_after_c1 + 1);

  // A stale epoch refuses before any allocation.
  fixture.live->invalidate_control_target();
  const auto stale = fixture.record_event(
      "10000000-0000-4000-8000-000000000304",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 300},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "3");
  LMDJ_CHECK(!stale.at("ok").get<bool>());
  LMDJ_CHECK(stale.at("error").at("details").at("reason") ==
             "performance_control_epoch_stale");
  LMDJ_CHECK(fixture.live->publish_calls() == publishes_after_c1 + 1);

  // The durable window holds C2 as the completed admission.
  lmdj::project_io::SequenceJournal journal;
  const auto durable = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(durable.has_value());
  const auto &ledger = *durable.value().admission_ledger;
  LMDJ_CHECK(ledger.next_recording_sequence == 3);
  LMDJ_CHECK(ledger.completed.has_value());
  LMDJ_CHECK(ledger.completed->request_id.value() ==
             "10000000-0000-4000-8000-000000000302");
}

// P1 journal fault oracle: a known pre-write failure keeps the frozen tuple
// retryable without a second tick/sequence; an unknown post-write freezes the
// session with the irreversible audio fact retained.
void test_headered_journal_faults_freeze_and_retry_exactly() {
  auto storage = std::make_shared<PostWriteFailingStorage>();
  HeaderedFixture fixture(storage);
  fixture.create_project();
  check_ok(fixture.begin_headered());
  fixture.mark_ready();
  const auto engage = fixture.record_event(
      "10000000-0000-4000-8000-000000000400",
      {{"kind", "fx_engage"}, {"fx", "delay"}, {"value", 100}}, "0");
  check_ok(engage);
  const auto gesture_id =
      engage.at("result").at("recording_gesture_id").get<std::string>();
  const auto gen =
      engage.at("result").at("gesture_generation").get<std::string>();

  // Known pre-write failure: no durable record, cell released, tuple frozen.
  storage->fail_next_tail_pre_write_pair();
  const auto failed = fixture.record_event(
      "10000000-0000-4000-8000-000000000401",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  LMDJ_CHECK(!failed.at("ok").get<bool>());
  LMDJ_CHECK(failed.at("error").at("code") == "IO_ERROR");
  lmdj::project_io::SequenceJournal journal;
  LMDJ_CHECK(journal.read_active_performance(fixture.bundle())
                 .value()
                 .last_input_sequence == 1);
  LMDJ_CHECK(fixture.live->publish_calls() == 1);  // only the engage

  // A different payload on the same identity is a collision while frozen.
  const auto collision = fixture.record_event(
      "10000000-0000-4000-8000-000000000401",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 900},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  LMDJ_CHECK(!collision.at("ok").get<bool>());
  LMDJ_CHECK(collision.at("error").at("details").at("reason") ==
             "performance_admission_collision");

  // The identical retry re-reserves the frozen translation and reuses the
  // frozen tick/sequence: the durable high-water is 2, not 3.
  const auto retried = fixture.record_event(
      "10000000-0000-4000-8000-000000000401",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  check_ok(retried);
  LMDJ_CHECK(retried.at("result").at("replayed") == true);
  LMDJ_CHECK(fixture.live->republish_calls() == 1);
  LMDJ_CHECK(fixture.live->publish_calls() == 2);
  const auto durable = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(durable.value().last_input_sequence == 2);
  LMDJ_CHECK(durable.value().pending_events.size() == 2U);
}

// P1 journal fault oracle: an unknown post-write preserves the (possibly
// durable) admission, freezes the session, and the exact retry completes the
// identical tuple — never a second publish.
void test_headered_unknown_write_freezes_and_retry_never_republishes() {
  auto storage = std::make_shared<PostWriteFailingStorage>();
  HeaderedFixture fixture(storage);
  fixture.create_project();
  check_ok(fixture.begin_headered());
  fixture.mark_ready();
  const auto engage = fixture.record_event(
      "10000000-0000-4000-8000-000000000500",
      {{"kind", "fx_engage"}, {"fx", "delay"}, {"value", 100}}, "0");
  check_ok(engage);
  const auto gesture_id =
      engage.at("result").at("recording_gesture_id").get<std::string>();
  const auto gen =
      engage.at("result").at("gesture_generation").get<std::string>();

  storage->fail_next_tail_retry_pair();
  const auto ambiguous = fixture.record_event(
      "10000000-0000-4000-8000-000000000501",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  LMDJ_CHECK(!ambiguous.at("ok").get<bool>());
  LMDJ_CHECK(ambiguous.at("error").at("details").at("reason") ==
             "performance_tail_outcome_unknown");
  // The audio never published: the cell stayed held and unpublished.
  LMDJ_CHECK(fixture.live->publish_calls() == 1);
  const auto status = fixture.record_status();
  LMDJ_CHECK(status.at("result").at("state") == "recovery_required");
  LMDJ_CHECK(!status.at("result").at("pending_admission").is_null());

  // Another identity is blocked by the frozen admission.
  const auto blocked = fixture.record_event(
      "10000000-0000-4000-8000-000000000502",
      {{"kind", "hold_on"}}, "2");
  LMDJ_CHECK(!blocked.at("ok").get<bool>());
  LMDJ_CHECK(blocked.at("error").at("details").at("reason") ==
             "performance_admission_pending");

  // The identical retry completes the original tuple exactly once.
  const auto retried = fixture.record_event(
      "10000000-0000-4000-8000-000000000501",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id", gesture_id},
       {"gesture_generation", gen}},
      "1");
  check_ok(retried);
  LMDJ_CHECK(retried.at("result").at("replayed") == true);
  LMDJ_CHECK(fixture.live->publish_calls() == 2);  // the frozen move, once
  lmdj::project_io::SequenceJournal journal;
  const auto durable = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(durable.value().last_input_sequence == 2);
  LMDJ_CHECK(durable.value().admission_ledger->next_recording_sequence == 2);
  LMDJ_CHECK(!durable.value().admission_ledger->pending.has_value());
  LMDJ_CHECK(fixture.record_status().at("result").at("state") == "active");
}

// P1: a complete-metadata unknown freezes after publish; the retry completes
// the identical metadata with zero re-enqueue.
void test_headered_complete_unknown_retries_metadata_only() {
  auto storage = std::make_shared<PostWriteFailingStorage>();
  HeaderedFixture fixture(storage);
  fixture.create_project();
  check_ok(fixture.begin_headered());
  fixture.mark_ready();
  const auto engage = fixture.record_event(
      "10000000-0000-4000-8000-000000000600",
      {{"kind", "fx_engage"}, {"fx", "delay"}, {"value", 100}}, "0");
  check_ok(engage);
  const auto publishes = fixture.live->publish_calls();
  LMDJ_CHECK(publishes == 1);

  storage->fail_next_complete_pair();
  const auto ambiguous = fixture.record_event(
      "10000000-0000-4000-8000-000000000601",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id",
        engage.at("result").at("recording_gesture_id")},
       {"gesture_generation",
        engage.at("result").at("gesture_generation")}},
      "1");
  LMDJ_CHECK(!ambiguous.at("ok").get<bool>());
  if (ambiguous.at("ok").get<bool>() ||
      !ambiguous.at("error").at("details").contains("reason") ||
      ambiguous.at("error").at("details").at("reason") !=
          "performance_admission_complete_outcome_unknown") {
    throw std::runtime_error(ambiguous.dump());
  }
  // The audio DID publish; the session freezes instead of rolling back.
  LMDJ_CHECK(fixture.live->publish_calls() == 2);
  LMDJ_CHECK(fixture.record_status().at("result").at("state") ==
             "recovery_required");

  const auto retried = fixture.record_event(
      "10000000-0000-4000-8000-000000000601",
      {{"kind", "fx_move"},
       {"fx", "delay"},
       {"value", 500},
       {"gesture_id",
        engage.at("result").at("recording_gesture_id")},
       {"gesture_generation",
        engage.at("result").at("gesture_generation")}},
      "1");
  check_ok(retried);
  LMDJ_CHECK(retried.at("result").at("replayed") == true);
  // Zero re-enqueue on the metadata retry.
  LMDJ_CHECK(fixture.live->publish_calls() == 2);
  lmdj::project_io::SequenceJournal journal;
  const auto durable = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(
      durable.value().admission_ledger->completed.has_value());
  LMDJ_CHECK(durable.value()
                 .admission_ledger->completed->request_id.value() ==
             "10000000-0000-4000-8000-000000000601");
}

// P1: a full queue refuses the begin before any draft or admission exists.
void test_headered_begin_queue_full_creates_no_draft() {
  HeaderedFixture fixture;
  fixture.create_project();
  fixture.live->fail_fences(1);
  const auto refused = fixture.begin_headered();
  LMDJ_CHECK(!refused.at("ok").get<bool>());
  LMDJ_CHECK(refused.at("error").at("message") ==
             "the master FX gesture queue is full");
  const auto listed = fixture.application->query(
      {{"operation", "performance.list"},
       {"project_path", fixture.bundle().generic_string()}});
  check_ok(listed);
  LMDJ_CHECK(listed.at("result").at("performances").empty());
  LMDJ_CHECK(fixture.live->publish_calls() == 0);
  // The refusal consumed nothing: the same begin identity succeeds after.
  check_ok(fixture.begin_headered());
}

// P1 lifecycle oracle: recording stop closes the journal gestures with one
// Core sequence per synthetic event and retains the live performance state.
void test_headered_stop_closure_allocates_per_event_and_retains_live_state() {
  HeaderedFixture fixture;
  fixture.create_project();
  check_ok(fixture.begin_headered());
  fixture.mark_ready();
  const auto engage = fixture.record_event(
      "10000000-0000-4000-8000-000000000700",
      {{"kind", "fx_engage"}, {"fx", "delay"}, {"value", 100}}, "0");
  check_ok(engage);
  const auto gesture_id =
      engage.at("result").at("recording_gesture_id").get<std::string>();
  const auto gen =
      engage.at("result").at("gesture_generation").get<std::string>();
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000701", {{"kind", "hold_on"}}, "1"));
  fixture.clock->set(10);
  check_ok(fixture.record_event(
      "10000000-0000-4000-8000-000000000702",
      {{"kind", "pad_press"},
       {"gesture_id", "10000000-0000-4000-8000-000000000703"},
       {"slot", 4},
       {"velocity", 90}},
      "2"));

  const auto publishes_before_stop = fixture.live->publish_calls();
  check_ok(fixture.application->command(
      {{"operation", "performance.record.stop"},
       {"project_path", fixture.bundle().generic_string()},
       {"session_id", std::string{kSession}},
       {"request_id", "10000000-0000-4000-8000-000000000704"}}));
  // Recording stop is journal-side: the live bus is untouched.
  LMDJ_CHECK(fixture.live->publish_calls() == publishes_before_stop);
  LMDJ_CHECK(fixture.live->accepted().state.hold);
  LMDJ_CHECK(fixture.live->accepted().state.other_fx.at(0).engaged);

  lmdj::project_io::SequenceJournal journal;
  const auto durable = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(durable.has_value());
  // Closure: PadHit (press sequence) + FxRelease + HoldOff, each synthetic
  // control with its own Core sequence.
  std::optional<std::uint64_t> release_sequence;
  std::optional<std::uint64_t> hold_off_sequence;
  for (const auto &event : durable.value().pending_events) {
    if (std::holds_alternative<lmdj::domain::FxReleasePerformanceEvent>(
            event.payload)) {
      release_sequence = event.input_sequence;
    }
    if (std::holds_alternative<lmdj::domain::HoldOffPerformanceEvent>(
            event.payload)) {
      hold_off_sequence = event.input_sequence;
    }
  }
  LMDJ_CHECK(release_sequence.has_value());
  LMDJ_CHECK(hold_off_sequence.has_value());
  LMDJ_CHECK(*release_sequence != *hold_off_sequence);
  (void)gen;
  (void)gesture_id;
}

// D0/P1: without an attached engine (no live-control port), the new-profile
// begin fails explicitly as audio-producer unavailable instead of faking an
// applied live state; the legacy profile begin is unchanged.
void test_headless_new_profile_begin_fails_explicitly() {
  TempDirectory temp;
  lmdj::facade::Application application{
      {temp.path(),
       nullptr,
       {},
       {},
       std::nullopt,
       nullptr,
       std::make_shared<Clock>(),
       std::make_shared<Sequencer>(),
       nullptr,
       lmdj::facade::make_unavailable_performance_replay_controller(),
       nullptr,
       nullptr,
       nullptr,
       std::nullopt,
       nullptr}};
  const auto bundle = temp.path() / "headless.lmdj";
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", kProject},
                                {"bpm", 120}}));
  const auto refused = application.command({
      {"operation", "performance.record.begin"},
      {"project_path", bundle.generic_string()},
      {"command_id", kBegin},
      {"expected_revision", 0},
      {"session_id", kSession},
      {"performance_id", kPerformance},
      {"control_epoch", "11111111-1111-4111-8111-111111111111"},
  });
  LMDJ_CHECK(!refused.at("ok").get<bool>());
  LMDJ_CHECK(refused.at("error").at("details").at("reason") ==
             "performance_live_control_unavailable");
  // No draft was created; the legacy begin still works on the same project.
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", kBegin},
                                {"expected_revision", 0},
                                {"session_id", kSession},
                                {"performance_id", kPerformance}}));
}

// P1 oracle: a headered launch-request freezes its input sequence at
// reservation and the ACK reuses it; the internal ACK admission advances the
// ledger without a second musical sequence.
void test_headered_launch_freezes_sequence_at_reservation_and_ack_reuses() {
  HeaderedFixture fixture;
  fixture.create_project();
  check_ok(fixture.begin_headered());
  fixture.mark_ready();

  const auto launch = fixture.application->command({
      {"operation", "performance.record.launch-request"},
      {"project_path", fixture.bundle().generic_string()},
      {"session_id", std::string{kSession}},
      {"request_id", "10000000-0000-4000-8000-000000000800"},
      {"pattern_slot", 3},
      {"control_epoch", std::string{FakeLiveControl::kEpoch}},
      {"expected_recording_sequence", "0"},
  });
  check_ok(launch);
  const auto frozen_sequence =
      launch.at("result").at("input_sequence").get<std::string>();
  LMDJ_CHECK(frozen_sequence == "1");
  LMDJ_CHECK(launch.at("result").at("next_recording_sequence") == "1");

  // The reservation is durable before any ACK, with no Pattern event yet.
  lmdj::project_io::SequenceJournal journal;
  const auto before_ack =
      journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(before_ack.has_value());
  LMDJ_CHECK(before_ack.value().pending_events.empty());
  LMDJ_CHECK(before_ack.value().admission_ledger->completed.has_value());
  LMDJ_CHECK(before_ack.value()
                 .admission_ledger->completed->request_id.value() ==
             "10000000-0000-4000-8000-000000000800");
  LMDJ_CHECK(before_ack.value()
                 .admission_ledger->completed->event_input_sequences.empty());

  fixture.acknowledger->acknowledge();
  LMDJ_CHECK(fixture.application->service_performance().has_value());
  const auto after = journal.read_active_performance(fixture.bundle());
  LMDJ_CHECK(after.has_value());
  LMDJ_CHECK(after.value().pending_events.size() == 1U);
  const auto &event = after.value().pending_events.front();
  LMDJ_CHECK(std::holds_alternative<
             lmdj::domain::PatternLaunchPerformanceEvent>(event.payload));
  // The ACK reused the frozen sequence; the internal admission advanced the
  // ledger but allocated no second musical sequence for the event.
  LMDJ_CHECK(*event.input_sequence == 1);
  LMDJ_CHECK(after.value().admission_ledger->next_recording_sequence == 2);
}

// P1: sessionless live.control — the Core-issued epoch/CAS window over the
// same admission kernel, and the recording route's exclusivity.
void test_live_control_sessionless_window_and_recording_route_exclusion() {
  HeaderedFixture fixture;
  fixture.create_project();
  const auto status = fixture.application->query(
      {{"operation", "performance.live.status"},
       {"project_path", fixture.bundle().generic_string()}});
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("available") == true);
  LMDJ_CHECK(status.at("result").at("control_epoch") ==
             std::string{FakeLiveControl::kEpoch});
  LMDJ_CHECK(status.at("result").at("accepted_control_sequence") == "0");

  const auto control = [&](std::string_view command_id,
                           std::string_view expected, nlohmann::json intent) {
    return fixture.application->command(
        {{"operation", "performance.live.control"},
         {"project_path", fixture.bundle().generic_string()},
         {"control_epoch", std::string{FakeLiveControl::kEpoch}},
         {"command_id", std::string(command_id)},
         {"expected_control_sequence", std::string(expected)},
         {"intent", std::move(intent)}});
  };
  const auto first = control("10000000-0000-4000-8000-000000000900", "0",
                             {{"kind", "pad_mute"},
                              {"slot", 7},
                              {"enabled", true}});
  check_ok(first);
  LMDJ_CHECK(first.at("result").at("accepted") == true);
  LMDJ_CHECK(first.at("result").at("control_sequence") == "1");
  LMDJ_CHECK(fixture.live->accepted().state.muted_mask ==
             (std::uint64_t{1} << 7));

  // Exact replay of the completed admission: zero new publish.
  const auto replay = control("10000000-0000-4000-8000-000000000900", "0",
                              {{"kind", "pad_mute"},
                               {"slot", 7},
                               {"enabled", true}});
  check_ok(replay);
  LMDJ_CHECK(replay.at("result").at("replayed") == true);
  LMDJ_CHECK(fixture.live->publish_calls() == 1);
  // An expired unknown identity and a future sequence both refuse.
  LMDJ_CHECK(!control("10000000-0000-4000-8000-000000000901", "0",
                      {{"kind", "hold_on"}})
                  .at("ok")
                  .get<bool>());
  LMDJ_CHECK(!control("10000000-0000-4000-8000-000000000902", "5",
                      {{"kind", "hold_on"}})
                  .at("ok")
                  .get<bool>());

  // While a headered recording is begin-pending/active on the epoch, the
  // sessionless route refuses; the recording route owns the epoch's control.
  check_ok(fixture.begin_headered());
  const auto blocked = control("10000000-0000-4000-8000-000000000903", "1",
                               {{"kind", "hold_on"}});
  LMDJ_CHECK(!blocked.at("ok").get<bool>());
  LMDJ_CHECK(blocked.at("error").at("details").at("reason") ==
             "performance_recording_route_required");
  LMDJ_CHECK(fixture.live->publish_calls() == 1);
}

void test_live_control_exact_retry_observes_real_render_application() {
  TempDirectory temp;
  const auto bundle = temp.path() / "live-retry.lmdj";
  lmdj::audio::RealtimeEngine engine;
  LMDJ_CHECK(engine.prepare_master_fx(120).has_value());
  LMDJ_CHECK(engine.start().has_value());
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  auto config = lmdj::facade::ApplicationConfig{
      temp.path(), nullptr, {}, {}, std::nullopt, nullptr,
      adapter.clock, adapter.input_sequencer, adapter.launch_acknowledger,
      adapter.replay_controller, adapter.gesture_sink};
  config.performance_live_control = adapter.live_control;
  lmdj::facade::Application application(std::move(config));
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", std::string{kProject}},
                                {"bpm", 120}}));
  const auto status = application.query(
      {{"operation", "performance.live.status"},
       {"project_path", bundle.generic_string()}});
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("available") == true);
  LMDJ_CHECK(status.at("result").at("accepted_control_sequence") == "0");
  LMDJ_CHECK(status.at("result").at("applied_control_sequence") == "0");
  const auto epoch = status.at("result").at("control_epoch").get<std::string>();
  const nlohmann::json request = {
      {"operation", "performance.live.control"},
      {"project_path", bundle.generic_string()}, {"control_epoch", epoch},
      {"command_id", "10000000-0000-4000-8000-000000000910"},
      {"expected_control_sequence", "0"},
      {"intent", {{"kind", "pad_mute"}, {"slot", 7}, {"enabled", true}}}};
  const auto first = application.command(request);
  check_ok(first);
  const auto &receipt = first.at("result");
  LMDJ_CHECK(receipt.size() == 7U);
  LMDJ_CHECK(receipt.at("command_id") == request.at("command_id"));
  LMDJ_CHECK(receipt.at("control_epoch") == epoch);
  LMDJ_CHECK(receipt.at("control_sequence") == "1");
  LMDJ_CHECK(receipt.at("gesture_generation").is_null());
  LMDJ_CHECK(receipt.at("accepted") == true);
  LMDJ_CHECK(receipt.at("applied") == false);
  LMDJ_CHECK(receipt.at("replayed") == false);
  LMDJ_CHECK(first.at("project_revision").is_null());
  const auto accepted = adapter.live_control->live_control_snapshot();
  LMDJ_CHECK(accepted.accepted_control_sequence == 1);
  LMDJ_CHECK(accepted.applied_control_sequence == 0);
  LMDJ_CHECK(accepted.accepted.state.muted_mask == (std::uint64_t{1} << 7));
  LMDJ_CHECK(accepted.applied.state.muted_mask == 0);
  LMDJ_CHECK(engine.pad_gates_status().accepted_sequence == 1);
  const auto start_epoch = engine.telemetry().start_epoch;

  const auto check_retry = [&](const nlohmann::json &response, bool applied) {
    check_ok(response);
    const auto &retry = response.at("result");
    LMDJ_CHECK(retry.contains("applied"));
    LMDJ_CHECK(retry.size() == 7U);
    LMDJ_CHECK(retry.at("accepted") == true);
    LMDJ_CHECK(retry.at("applied").is_boolean());
    LMDJ_CHECK(retry.at("applied") == applied);
    LMDJ_CHECK(retry.at("replayed") == true);
    LMDJ_CHECK(response.at("project_revision").is_null());
    auto retained_identity = receipt;
    auto retry_identity = retry;
    retained_identity.erase("applied");
    retained_identity.erase("replayed");
    retry_identity.erase("applied");
    retry_identity.erase("replayed");
    LMDJ_CHECK(retry_identity == retained_identity);
    const auto snapshot = adapter.live_control->live_control_snapshot();
    LMDJ_CHECK(snapshot.accepted_control_sequence == 1);
    LMDJ_CHECK(snapshot.accepted.state.muted_mask == (std::uint64_t{1} << 7));
    LMDJ_CHECK(engine.pad_gates_status().accepted_sequence == 1);
    LMDJ_CHECK(engine.telemetry().start_epoch == start_epoch);
  };
  check_retry(application.command(request), false);
  LMDJ_CHECK(
      adapter.live_control->live_control_snapshot().applied_control_sequence == 0);
  LMDJ_CHECK(engine.pad_gates_status().applied.sequence == 0);

  std::array<float, 128> left{};
  std::array<float, 128> right{};
  engine.render(left.data(), right.data(), 128);
  const auto actually_applied = adapter.live_control->live_control_snapshot();
  LMDJ_CHECK(actually_applied.applied_control_sequence == 1);
  LMDJ_CHECK(actually_applied.applied.state.muted_mask ==
             (std::uint64_t{1} << 7));
  LMDJ_CHECK(engine.pad_gates_status().applied.sequence == 1);
  LMDJ_CHECK(engine.pad_gates_status().applied.state.muted_mask ==
             (std::uint64_t{1} << 7));
  check_retry(application.command(request), true);
  check_retry(application.command(request), true);
  engine.stop();
}

} // namespace

int main() {
  try {
    test_status_is_read_only_and_explicit_service_is_exactly_once();
    test_launch_service_retries_without_loss_or_duplicate_events();
    test_ambiguous_launch_service_freezes_without_consuming_outcome();
    test_raw_gesture_admission_and_launch_ack();
    test_launch_receives_core_resolved_immutable_pattern_material();
    test_ambiguous_tail_append_freezes_runtime_without_overwrite();
    test_admitted_fx_and_hold_gestures_reach_the_master_bus();
    test_refused_live_gesture_leaves_no_journalled_event();
    test_session_free_fx_gesture_reaches_the_master_bus();
    test_session_free_fx_gesture_refusals_fail_closed();
    test_headered_status_counts_fx_and_filter_across_reopen_and_stop();
    test_headered_begin_fence_mapping_and_first_pad_gate();
    test_headered_profile_preserves_every_move_and_same_tick_order();
    test_headered_exact_retry_collision_expired_and_stale_epoch();
    test_headered_journal_faults_freeze_and_retry_exactly();
    test_headered_unknown_write_freezes_and_retry_never_republishes();
    test_headered_complete_unknown_retries_metadata_only();
    test_headered_begin_queue_full_creates_no_draft();
    test_headered_stop_closure_allocates_per_event_and_retains_live_state();
    test_headless_new_profile_begin_fails_explicitly();
    test_headered_launch_freezes_sequence_at_reservation_and_ack_reuses();
    test_live_control_sessionless_window_and_recording_route_exclusion();
    test_live_control_exact_retry_observes_real_render_application();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
