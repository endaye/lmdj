#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <span>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>
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
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> delegate_;
  std::size_t pre_write_failures_{};
  std::size_t post_write_failures_{};
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
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
