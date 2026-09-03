#include <chrono>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <iostream>
#include <lmdj/facade/application.hpp>
#include <lmdj/facade/performance_replay.hpp>
#include <lmdj/project_io/project_store.hpp>

#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::FxGesture;
using lmdj::cooker::PerformanceReplayBoundary;
using lmdj::cooker::PerformanceReplayProjection;
using lmdj::cooker::ResolvedPad;
using lmdj::domain::FxEngagePerformanceEvent;
using lmdj::domain::FxMovePerformanceEvent;
using lmdj::domain::FxReleasePerformanceEvent;
using lmdj::domain::HoldOffPerformanceEvent;
using lmdj::domain::HoldOnPerformanceEvent;
using lmdj::domain::PadHitPerformanceEvent;
using lmdj::domain::PatternLaunchPerformanceEvent;
using lmdj::domain::PerformanceEvent;
using lmdj::domain::PerformanceFx;
using lmdj::domain::PerformanceId;
using lmdj::facade::NeutralResetProgress;
using lmdj::facade::PerformanceReplayRuntimeSink;
using lmdj::facade::ReplayId;
using lmdj::facade::ReplayState;
using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::Result;

constexpr auto kReplayId = "60000000-0000-4000-8000-000000000001";
constexpr auto kPerformanceId = "50000000-0000-4000-8000-000000000001";
constexpr auto kSecondPerformanceId =
    "50000000-0000-4000-8000-000000000002";
constexpr auto kSecondReplayId = "60000000-0000-4000-8000-000000000002";
constexpr auto kStopRequestId = "70000000-0000-4000-8000-000000000001";

class TempDirectory {
 public:
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-replay-" +
             std::to_string(std::chrono::steady_clock::now()
                                .time_since_epoch()
                                .count()));
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

class CapturingController final
    : public lmdj::facade::PerformanceReplayController {
 public:
  Result<lmdj::facade::ReplayRuntimeStatus> begin(
      const ReplayId& replay_id,
      std::shared_ptr<const PerformanceReplayProjection> value) override {
    ++begin_calls;
    ids.push_back(replay_id);
    projections.push_back(std::move(value));
    status_value = {ReplayState::playing, 0,
                    projections.back()->event_count,
                    projections.back()->resolved_revision};
    if (begin_failures > 0) {
      --begin_failures;
      return Result<lmdj::facade::ReplayRuntimeStatus>::failure(
          Error{ErrorCode::internal_error, "runtime reset failed"});
    }
    return Result<lmdj::facade::ReplayRuntimeStatus>::success(status_value);
  }

  Result<lmdj::facade::ReplayRuntimeStatus> status(
      const ReplayId&) const override {
    ++status_calls;
    return Result<lmdj::facade::ReplayRuntimeStatus>::success(status_value);
  }

  Result<lmdj::facade::ReplayRuntimeStatus> stop(
      const ReplayId&) override {
    ++stop_calls;
    if (stop_failures > 0) {
      --stop_failures;
      return Result<lmdj::facade::ReplayRuntimeStatus>::failure(
          Error{ErrorCode::internal_error, "runtime reset failed"});
    }
    if (stop_pending > 0) {
      --stop_pending;
      return Result<lmdj::facade::ReplayRuntimeStatus>::success(status_value);
    }
    status_value.state = ReplayState::stopped;
    return Result<lmdj::facade::ReplayRuntimeStatus>::success(status_value);
  }

  std::vector<ReplayId> ids;
  std::vector<std::shared_ptr<const PerformanceReplayProjection>> projections;
  mutable std::uint32_t status_calls{};
  std::uint32_t begin_calls{};
  std::uint32_t stop_calls{};
  std::uint32_t begin_failures{};
  std::uint32_t stop_failures{};
  std::uint32_t stop_pending{};
  mutable lmdj::facade::ReplayRuntimeStatus status_value;
};

lmdj::domain::ProjectState replay_facade_project() {
  auto created = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{
          "10000000-0000-4000-8000-000000000001"},
      120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  state.contract = lmdj::domain::ProjectContract::v4;
  for (const auto* id : {kPerformanceId, kSecondPerformanceId}) {
    const PerformanceId performance_id{id};
    state.performances.emplace(
        performance_id,
        lmdj::domain::Performance{
            performance_id, "Replay", 120, 0, std::nullopt, {}});
  }
  return state;
}

lmdj::facade::Application make_replay_application(
    const std::filesystem::path& root,
    std::shared_ptr<CapturingController> controller) {
  return lmdj::facade::Application(lmdj::facade::ApplicationConfig{
      root,
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      std::move(controller),
  });
}

class RecordingSink final : public PerformanceReplayRuntimeSink {
 public:
  Result<void> apply_pad_hit(
      const ResolvedPad&,
      std::uint64_t,
      std::uint8_t) override {
    calls.push_back("pad");
    return apply_result();
  }

  Result<void> apply_pattern_launch(
      std::shared_ptr<const lmdj::cooker::RuntimeSnapshot>) override {
    calls.push_back("pattern");
    return apply_result();
  }

  Result<void> apply_fx_gesture(FxGesture) override {
    calls.push_back("fx");
    return apply_result();
  }

  Result<NeutralResetProgress> reset_neutral() override {
    calls.push_back("reset");
    ++reset_attempts;
    if (reset_failures > 0) {
      --reset_failures;
      return Result<NeutralResetProgress>::failure(
          Error{ErrorCode::internal_error, "runtime reset failed"});
    }
    if (reset_pending > 0) {
      --reset_pending;
      return Result<NeutralResetProgress>::success(
          NeutralResetProgress::pending);
  }
    return Result<NeutralResetProgress>::success(
        NeutralResetProgress::complete);
  }

  Result<void> apply_result() {
    if (apply_failures > 0) {
      --apply_failures;
      return Result<void>::failure(
          Error{ErrorCode::internal_error, "runtime apply failed"});
    }
    return Result<void>::success();
  }

  std::vector<std::string> calls;
  std::uint32_t apply_failures{};
  std::uint32_t reset_failures{};
  std::uint32_t reset_pending{};
  std::uint32_t reset_attempts{};
};

std::shared_ptr<const PerformanceReplayProjection> projection() {
  PerformanceReplayProjection value{
      PerformanceId{kPerformanceId},
      44,
      120,
      true,
      50,
      {},
      {},
      {
          PerformanceReplayBoundary{
              0, PerformanceEvent{PadHitPerformanceEvent{0, 10, 40, 99}}},
          PerformanceReplayBoundary{
              0, PerformanceEvent{PatternLaunchPerformanceEvent{3, 10}}},
          PerformanceReplayBoundary{
              0, PerformanceEvent{FxEngagePerformanceEvent{
                     PerformanceFx::filter, 500, 10}}},
          PerformanceReplayBoundary{
              20, PerformanceEvent{HoldOffPerformanceEvent{30}}},
      },
      4,
  };
  value.pads.at(0) = ResolvedPad{
      {0, 0},
      {std::string(64, 'a'), "audio/wav", 44},
      std::make_shared<const lmdj::cooker::PcmSample>(
          lmdj::cooker::PcmSample{48'000, 2, {0, 0}}),
      {0, 1, lmdj::domain::TriggerMode::one_shot, 1.0F, false},
  };
  return std::make_shared<const PerformanceReplayProjection>(std::move(value));
}

std::shared_ptr<const PerformanceReplayProjection> empty_projection() {
  return std::make_shared<const PerformanceReplayProjection>(
      PerformanceReplayProjection{
          PerformanceId{kPerformanceId}, 45, 120, false, 50, {}, {}, {}, 0});
}

void test_lifecycle_and_silent_pattern_gap() {
  auto sink = std::make_shared<RecordingSink>();
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  const auto begun = controller.begin(ReplayId{kReplayId}, projection());
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().state == ReplayState::playing);
  LMDJ_CHECK(begun.value().event_cursor == 0);
  LMDJ_CHECK(begun.value().event_count == 4);
  LMDJ_CHECK(begun.value().resolved_revision == 44);

  const auto first = controller.advance_to(0);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(first.value().event_cursor == 3);
  LMDJ_CHECK((sink->calls == std::vector<std::string>{"pad", "fx"}));
  const auto before_status = sink->calls;
  LMDJ_CHECK(controller.status(ReplayId{kReplayId}).has_value());
  LMDJ_CHECK(sink->calls == before_status);

  const auto completed = controller.advance_to(20);
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().state == ReplayState::complete);
  LMDJ_CHECK(completed.value().event_cursor == 4);
  LMDJ_CHECK(
      (sink->calls ==
       std::vector<std::string>{"pad", "fx", "fx", "reset"}));
}

void test_stop_is_the_only_reset_retry_driver() {
  auto sink = std::make_shared<RecordingSink>();
  sink->reset_failures = 1;
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  LMDJ_CHECK(controller.begin(ReplayId{kReplayId}, projection()).has_value());
  const auto natural = controller.advance_to(20);
  LMDJ_CHECK(!natural.has_value());
  LMDJ_CHECK(sink->reset_attempts == 1);
  const auto fixed = controller.status(ReplayId{kReplayId});
  LMDJ_CHECK(fixed.has_value());
  LMDJ_CHECK(fixed.value().state == ReplayState::playing);
  LMDJ_CHECK(fixed.value().event_cursor == 4);
  LMDJ_CHECK(sink->reset_attempts == 1);

  const auto retried = controller.stop(ReplayId{kReplayId});
  LMDJ_CHECK(retried.has_value());
  LMDJ_CHECK(retried.value().state == ReplayState::complete);
  LMDJ_CHECK(sink->reset_attempts == 2);
  const auto terminal_stop = controller.stop(ReplayId{kReplayId});
  LMDJ_CHECK(terminal_stop.has_value());
  LMDJ_CHECK(terminal_stop.value().state == ReplayState::complete);
  LMDJ_CHECK(sink->reset_attempts == 2);
}

void test_explicit_stop_resets_and_publishes_stopped() {
  auto sink = std::make_shared<RecordingSink>();
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  LMDJ_CHECK(controller.begin(ReplayId{kReplayId}, projection()).has_value());
  const auto stopped = controller.stop(ReplayId{kReplayId});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().state == ReplayState::stopped);
  LMDJ_CHECK(stopped.value().event_cursor == 0);
  LMDJ_CHECK((sink->calls == std::vector<std::string>{"reset"}));
}

void test_empty_projection_resets_before_complete() {
  auto sink = std::make_shared<RecordingSink>();
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  const auto completed =
      controller.begin(ReplayId{kReplayId}, empty_projection());
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().state == ReplayState::complete);
  LMDJ_CHECK(completed.value().event_cursor == 0);
  LMDJ_CHECK((sink->calls == std::vector<std::string>{"reset"}));
}

void test_pending_reset_keeps_playing_until_progress_is_confirmed() {
  auto sink = std::make_shared<RecordingSink>();
  sink->reset_pending = 1;
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  LMDJ_CHECK(controller.begin(ReplayId{kReplayId}, projection()).has_value());
  const auto pending = controller.advance_to(20);
  LMDJ_CHECK(pending.has_value());
  LMDJ_CHECK(pending.value().state == ReplayState::playing);
  LMDJ_CHECK(pending.value().event_cursor == 4);
  LMDJ_CHECK(sink->reset_attempts == 1);

  const auto observed = controller.status(ReplayId{kReplayId});
  LMDJ_CHECK(observed.has_value());
  LMDJ_CHECK(observed.value().state == ReplayState::playing);
  LMDJ_CHECK(sink->reset_attempts == 1);

  const auto completed = controller.advance_to(20);
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().state == ReplayState::complete);
  LMDJ_CHECK(sink->reset_attempts == 2);
}

void test_pending_explicit_stop_is_polled_by_each_stop_request() {
  auto sink = std::make_shared<RecordingSink>();
  sink->reset_pending = 1;
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  LMDJ_CHECK(controller.begin(ReplayId{kReplayId}, projection()).has_value());
  const auto pending = controller.stop(ReplayId{kReplayId});
  LMDJ_CHECK(pending.has_value());
  LMDJ_CHECK(pending.value().state == ReplayState::playing);
  LMDJ_CHECK(sink->reset_attempts == 1);
  LMDJ_CHECK(controller.status(ReplayId{kReplayId}).value().state ==
             ReplayState::playing);
  LMDJ_CHECK(sink->reset_attempts == 1);
  const auto stopped = controller.stop(ReplayId{kReplayId});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().state == ReplayState::stopped);
  LMDJ_CHECK(sink->reset_attempts == 2);
}

void test_empty_projection_retains_identity_while_pending_or_failed() {
  auto pending_sink = std::make_shared<RecordingSink>();
  pending_sink->reset_pending = 1;
  lmdj::facade::ReferencePerformanceReplayController pending_controller(
      pending_sink);
  const auto pending =
      pending_controller.begin(ReplayId{kReplayId}, empty_projection());
  LMDJ_CHECK(pending.has_value());
  LMDJ_CHECK(pending.value().state == ReplayState::playing);
  LMDJ_CHECK(pending_controller.status(ReplayId{kReplayId}).has_value());
  LMDJ_CHECK(
      !pending_controller.begin(ReplayId{kSecondReplayId}, empty_projection())
           .has_value());
  const auto completed = pending_controller.advance_to(0);
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().state == ReplayState::complete);

  auto failed_sink = std::make_shared<RecordingSink>();
  failed_sink->reset_failures = 1;
  lmdj::facade::ReferencePerformanceReplayController failed_controller(
      failed_sink);
  const auto failed =
      failed_controller.begin(ReplayId{kReplayId}, empty_projection());
  LMDJ_CHECK(!failed.has_value());
  const auto retained = failed_controller.status(ReplayId{kReplayId});
  LMDJ_CHECK(retained.has_value());
  LMDJ_CHECK(retained.value().state == ReplayState::playing);
  LMDJ_CHECK(failed_sink->reset_attempts == 1);
  LMDJ_CHECK(failed_controller.advance_to(0).has_value());
  LMDJ_CHECK(failed_sink->reset_attempts == 1);
  const auto retry = failed_controller.stop(ReplayId{kReplayId});
  LMDJ_CHECK(retry.has_value());
  LMDJ_CHECK(retry.value().state == ReplayState::complete);
  LMDJ_CHECK(failed_sink->reset_attempts == 2);
}

void test_apply_failure_freezes_cursor_and_stop_retries_reset() {
  auto sink = std::make_shared<RecordingSink>();
  sink->apply_failures = 1;
  sink->reset_failures = 1;
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  LMDJ_CHECK(controller.begin(ReplayId{kReplayId}, projection()).has_value());
  const auto failed = controller.advance_to(0);
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(sink->reset_attempts == 1);
  const auto observed = controller.status(ReplayId{kReplayId});
  LMDJ_CHECK(observed.has_value());
  LMDJ_CHECK(observed.value().state == ReplayState::playing);
  LMDJ_CHECK(observed.value().event_cursor == 0);
  LMDJ_CHECK(sink->reset_attempts == 1);
  const auto retried = controller.stop(ReplayId{kReplayId});
  LMDJ_CHECK(retried.has_value());
  LMDJ_CHECK(retried.value().state == ReplayState::stopped);
  LMDJ_CHECK(retried.value().event_cursor == 0);
  LMDJ_CHECK(sink->reset_attempts == 2);
}

void test_application_requires_explicit_replay_controller() {
  TempDirectory temp;
  bool rejected = false;
  try {
    lmdj::facade::Application application(lmdj::facade::ApplicationConfig{
        temp.path(), nullptr, {}, {}, std::nullopt, nullptr,
        nullptr, nullptr, nullptr, nullptr});
    (void)application;
  } catch (const std::invalid_argument& error) {
    rejected = std::string{error.what()} ==
               "performance_replay_controller is required";
  }
  LMDJ_CHECK(rejected);
}

void test_unavailable_controller_contract() {
  const auto controller =
      lmdj::facade::make_unavailable_performance_replay_controller();
  for (const auto& result : {
           controller->begin(ReplayId{kReplayId}, projection()),
           controller->status(ReplayId{kReplayId}),
           controller->stop(ReplayId{kReplayId}),
       }) {
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
    LMDJ_CHECK(result.error().details.at("reason") ==
               "performance_replay_runtime_unavailable");
  }
}

void test_reference_controller_validation_and_missing_identity() {
  bool null_sink_rejected = false;
  try {
    lmdj::facade::ReferencePerformanceReplayController invalid(nullptr);
    (void)invalid;
  } catch (const std::invalid_argument& error) {
    null_sink_rejected = std::string{error.what()} ==
                         "Performance replay Runtime sink is required";
  }
  LMDJ_CHECK(null_sink_rejected);

  auto sink = std::make_shared<RecordingSink>();
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  LMDJ_CHECK(!controller.begin(ReplayId{"invalid"}, projection()).has_value());
  LMDJ_CHECK(!controller.begin(ReplayId{kReplayId}, nullptr).has_value());
  auto count_mismatch = std::make_shared<PerformanceReplayProjection>(*projection());
  ++count_mismatch->event_count;
  LMDJ_CHECK(!controller.begin(ReplayId{kReplayId}, count_mismatch).has_value());
  auto noncanonical = std::make_shared<PerformanceReplayProjection>(*projection());
  noncanonical->boundaries.at(0).offset_tick = 1;
  LMDJ_CHECK(!controller.begin(ReplayId{kReplayId}, noncanonical).has_value());
  LMDJ_CHECK(!controller.status(ReplayId{kReplayId}).has_value());
  LMDJ_CHECK(!controller.stop(ReplayId{kReplayId}).has_value());
  LMDJ_CHECK(!controller.advance_to(0).has_value());

  LMDJ_CHECK(controller.begin(ReplayId{kReplayId}, projection()).has_value());
  LMDJ_CHECK(controller.begin(ReplayId{kReplayId}, projection()).has_value());
  LMDJ_CHECK(
      !controller.begin(ReplayId{kSecondReplayId}, projection()).has_value());

  lmdj::facade::ReferencePerformanceReplayController moved(
      std::move(controller));
  lmdj::facade::ReferencePerformanceReplayController assigned(
      std::make_shared<RecordingSink>());
  assigned = std::move(moved);
  LMDJ_CHECK(assigned.status(ReplayId{kReplayId}).has_value());
}

void test_reference_controller_covers_all_runtime_actions_and_failures() {
  auto all_actions = *projection();
  all_actions.patterns.at(3) =
      std::make_shared<const lmdj::cooker::RuntimeSnapshot>(
          lmdj::cooker::RuntimeSnapshot{
              lmdj::foundation::ProjectId{
                  "90000000-0000-4000-8000-000000000001"},
              lmdj::foundation::PatternId{
                  "90000000-0000-4000-8000-000000000002"},
              44, 120, 1, 960, 3'840, {}, {}});
  all_actions.boundaries = {
      {0, PerformanceEvent{PatternLaunchPerformanceEvent{3, 10}}},
      {0, PerformanceEvent{FxMovePerformanceEvent{
              PerformanceFx::delay, 250, 10}}},
      {0, PerformanceEvent{FxReleasePerformanceEvent{
              PerformanceFx::delay, 10}}},
      {0, PerformanceEvent{HoldOnPerformanceEvent{10}}},
  };
  all_actions.event_count = all_actions.boundaries.size();
  auto sink = std::make_shared<RecordingSink>();
  lmdj::facade::ReferencePerformanceReplayController controller(sink);
  LMDJ_CHECK(controller.begin(
      ReplayId{kReplayId},
      std::make_shared<const PerformanceReplayProjection>(all_actions))
                 .has_value());
  const auto completed = controller.advance_to(0);
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().state == ReplayState::complete);
  LMDJ_CHECK((sink->calls ==
              std::vector<std::string>{"pattern", "fx", "fx", "fx", "reset"}));

  auto unresolved = *projection();
  unresolved.boundaries = {
      {0, PerformanceEvent{PadHitPerformanceEvent{1, 0, 10, 100}}},
  };
  unresolved.event_count = 1;
  auto unresolved_sink = std::make_shared<RecordingSink>();
  lmdj::facade::ReferencePerformanceReplayController unresolved_controller(
      unresolved_sink);
  LMDJ_CHECK(unresolved_controller.begin(
      ReplayId{kSecondReplayId},
      std::make_shared<const PerformanceReplayProjection>(unresolved))
                 .has_value());
  const auto unresolved_result = unresolved_controller.advance_to(0);
  LMDJ_CHECK(!unresolved_result.has_value());
  LMDJ_CHECK(unresolved_result.error().code == ErrorCode::missing_asset);
  LMDJ_CHECK(unresolved_controller.status(ReplayId{kSecondReplayId})
                 .value()
                 .state == ReplayState::stopped);

  auto invalid_pattern = *projection();
  invalid_pattern.boundaries = {
      {0, PerformanceEvent{PatternLaunchPerformanceEvent{16, 0}}},
  };
  invalid_pattern.event_count = 1;
  auto invalid_pattern_sink = std::make_shared<RecordingSink>();
  lmdj::facade::ReferencePerformanceReplayController invalid_pattern_controller(
      invalid_pattern_sink);
  LMDJ_CHECK(invalid_pattern_controller.begin(
      ReplayId{kReplayId},
      std::make_shared<const PerformanceReplayProjection>(invalid_pattern))
                 .has_value());
  LMDJ_CHECK(!invalid_pattern_controller.advance_to(0).has_value());

  auto reset_sink = std::make_shared<RecordingSink>();
  reset_sink->reset_failures = 1;
  lmdj::facade::ReferencePerformanceReplayController reset_controller(
      reset_sink);
  LMDJ_CHECK(reset_controller.begin(ReplayId{kReplayId}, projection())
                 .has_value());
  LMDJ_CHECK(!reset_controller.advance_to(20).has_value());
  const auto pending = reset_controller.advance_to(20);
  LMDJ_CHECK(pending.has_value());
  LMDJ_CHECK(pending.value().state == ReplayState::playing);

  auto empty_reset_sink = std::make_shared<RecordingSink>();
  empty_reset_sink->reset_failures = 1;
  lmdj::facade::ReferencePerformanceReplayController empty_reset_controller(
      empty_reset_sink);
  LMDJ_CHECK(!empty_reset_controller.begin(
      ReplayId{kReplayId}, empty_projection()).has_value());
  LMDJ_CHECK(empty_reset_controller.status(ReplayId{kReplayId}).has_value());
}

void test_facade_identity_exclusion_and_fixed_revision() {
  TempDirectory temp;
  const auto bundle = temp.path() / "project.lmdj";
  lmdj::project_io::ProjectStore writer;
  LMDJ_CHECK(writer.create(bundle, replay_facade_project()).has_value());
  auto controller = std::make_shared<CapturingController>();
  auto application = make_replay_application(temp.path(), controller);

  const auto begin_request = nlohmann::json{
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"performance_id", kPerformanceId},
  };
  const auto begun = application.command(begin_request);
  LMDJ_CHECK(begun.at("ok") == true);
  LMDJ_CHECK(begun.at("result").at("state") == "playing");
  LMDJ_CHECK(begun.at("result").at("resolved_revision") == 0);
  LMDJ_CHECK(controller->begin_calls == 1);

  const auto retry = application.command(begin_request);
  LMDJ_CHECK(retry.at("ok") == true);
  LMDJ_CHECK(controller->begin_calls == 1);

  const auto identity_collision = application.command({
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"performance_id", kSecondPerformanceId},
  });
  LMDJ_CHECK(identity_collision.at("ok") == false);
  LMDJ_CHECK(identity_collision.at("error").at("code") == "DUPLICATE_ID");
  LMDJ_CHECK(controller->begin_calls == 1);

  const auto excluded = application.command({
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kSecondReplayId},
      {"performance_id", kSecondPerformanceId},
  });
  LMDJ_CHECK(excluded.at("ok") == false);
  LMDJ_CHECK(excluded.at("error").at("code") == "INVALID_ARGUMENT");
  LMDJ_CHECK((excluded.at("error").at("details") ==
              nlohmann::json{{"active_replay_id", kReplayId}}));

  const auto deleted = writer.delete_performance(
      bundle,
      lmdj::project_io::DeletePerformance{
          {lmdj::foundation::CommandId{
               "80000000-0000-4000-8000-000000000001"},
           0},
          PerformanceId{kPerformanceId}});
  LMDJ_CHECK(deleted.has_value());
  LMDJ_CHECK(controller->projections.front()->resolved_revision == 0);
  LMDJ_CHECK(controller->projections.front()->performance_id ==
             PerformanceId{kPerformanceId});

  const auto stopped = application.command({
      {"operation", "performance.replay.stop"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"request_id", kStopRequestId},
  });
  LMDJ_CHECK(stopped.at("ok") == true);
  LMDJ_CHECK(stopped.at("result").at("state") == "stopped");
  LMDJ_CHECK(stopped.at("result").at("replayed") == false);
  LMDJ_CHECK(controller->stop_calls == 1);
  const auto stop_retry = application.command({
      {"operation", "performance.replay.stop"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"request_id", kStopRequestId},
  });
  LMDJ_CHECK(stop_retry.at("result").at("replayed") == true);
  LMDJ_CHECK(controller->stop_calls == 1);

  const auto next = application.command({
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kSecondReplayId},
      {"performance_id", kSecondPerformanceId},
  });
  LMDJ_CHECK(next.at("ok") == true);
  LMDJ_CHECK(next.at("result").at("resolved_revision") == 1);
  LMDJ_CHECK(controller->projections.back()->resolved_revision == 1);
}

void test_replay_exclusion_is_per_facade_instance() {
  TempDirectory temp;
  const auto bundle = temp.path() / "project.lmdj";
  lmdj::project_io::ProjectStore writer;
  LMDJ_CHECK(writer.create(bundle, replay_facade_project()).has_value());
  auto first_controller = std::make_shared<CapturingController>();
  auto second_controller = std::make_shared<CapturingController>();
  auto first = make_replay_application(temp.path() / "first", first_controller);
  auto second = make_replay_application(temp.path() / "second", second_controller);
  const auto first_result = first.command({
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"performance_id", kPerformanceId},
  });
  const auto second_result = second.command({
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kSecondReplayId},
      {"performance_id", kSecondPerformanceId},
  });
  LMDJ_CHECK(first_result.at("ok") == true);
  LMDJ_CHECK(second_result.at("ok") == true);

  first_controller->status_value.state = ReplayState::complete;
  const auto next_on_first = first.command({
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kSecondReplayId},
      {"performance_id", kSecondPerformanceId},
  });
  LMDJ_CHECK(next_on_first.at("ok") == true);
}

void test_failed_stop_does_not_consume_request_identity() {
  TempDirectory temp;
  const auto bundle = temp.path() / "project.lmdj";
  lmdj::project_io::ProjectStore writer;
  LMDJ_CHECK(writer.create(bundle, replay_facade_project()).has_value());
  auto controller = std::make_shared<CapturingController>();
  controller->stop_failures = 1;
  auto application = make_replay_application(temp.path(), controller);
  const auto begun = application.command({
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"performance_id", kPerformanceId},
  });
  LMDJ_CHECK(begun.at("ok") == true);
  const auto stop_request = nlohmann::json{
      {"operation", "performance.replay.stop"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"request_id", kStopRequestId},
  };
  LMDJ_CHECK(application.command(stop_request).at("ok") == false);
  const auto retried = application.command(stop_request);
  LMDJ_CHECK(retried.at("ok") == true);
  LMDJ_CHECK(retried.at("result").at("replayed") == false);
  const auto receipt = application.command(stop_request);
  LMDJ_CHECK(receipt.at("ok") == true);
  LMDJ_CHECK(receipt.at("result").at("replayed") == true);
  LMDJ_CHECK(controller->stop_calls == 2);
}

void test_pending_stop_does_not_consume_request_identity() {
  TempDirectory temp;
  const auto bundle = temp.path() / "project.lmdj";
  lmdj::project_io::ProjectStore writer;
  LMDJ_CHECK(writer.create(bundle, replay_facade_project()).has_value());
  auto controller = std::make_shared<CapturingController>();
  controller->stop_pending = 1;
  auto application = make_replay_application(temp.path(), controller);
  LMDJ_CHECK(application
                 .command({
                     {"operation", "performance.replay.begin"},
                     {"project_path", bundle.generic_string()},
                     {"replay_id", kReplayId},
                     {"performance_id", kPerformanceId},
                 })
                 .at("ok") == true);
  const auto stop_request = nlohmann::json{
      {"operation", "performance.replay.stop"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"request_id", kStopRequestId},
  };
  const auto pending = application.command(stop_request);
  LMDJ_CHECK(pending.at("ok") == true);
  LMDJ_CHECK(pending.at("result").at("state") == "playing");
  LMDJ_CHECK(pending.at("result").at("replayed") == false);
  LMDJ_CHECK(controller->stop_calls == 1);
  const auto terminal = application.command(stop_request);
  LMDJ_CHECK(terminal.at("ok") == true);
  LMDJ_CHECK(terminal.at("result").at("state") == "stopped");
  LMDJ_CHECK(terminal.at("result").at("replayed") == false);
  LMDJ_CHECK(controller->stop_calls == 2);
  const auto receipt = application.command(stop_request);
  LMDJ_CHECK(receipt.at("ok") == true);
  LMDJ_CHECK(receipt.at("result").at("replayed") == true);
  LMDJ_CHECK(controller->stop_calls == 2);
}

void test_failed_empty_begin_retains_facade_identity_and_exclusion() {
  TempDirectory temp;
  const auto bundle = temp.path() / "project.lmdj";
  lmdj::project_io::ProjectStore writer;
  LMDJ_CHECK(writer.create(bundle, replay_facade_project()).has_value());
  auto controller = std::make_shared<CapturingController>();
  controller->begin_failures = 1;
  auto application = make_replay_application(temp.path(), controller);
  const auto begin_request = nlohmann::json{
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kReplayId},
      {"performance_id", kPerformanceId},
  };
  const auto failed = application.command(begin_request);
  LMDJ_CHECK(failed.at("ok") == false);
  LMDJ_CHECK(controller->begin_calls == 1);

  const auto retry = application.command(begin_request);
  LMDJ_CHECK(retry.at("ok") == true);
  LMDJ_CHECK(retry.at("result").at("state") == "playing");
  LMDJ_CHECK(controller->begin_calls == 1);
  const auto excluded = application.command({
      {"operation", "performance.replay.begin"},
      {"project_path", bundle.generic_string()},
      {"replay_id", kSecondReplayId},
      {"performance_id", kSecondPerformanceId},
  });
  LMDJ_CHECK(excluded.at("ok") == false);
  LMDJ_CHECK((excluded.at("error").at("details") ==
              nlohmann::json{{"active_replay_id", kReplayId}}));
}

}  // namespace

int main() {
  try {
    test_lifecycle_and_silent_pattern_gap();
    test_stop_is_the_only_reset_retry_driver();
    test_explicit_stop_resets_and_publishes_stopped();
    test_empty_projection_resets_before_complete();
    test_pending_reset_keeps_playing_until_progress_is_confirmed();
    test_pending_explicit_stop_is_polled_by_each_stop_request();
    test_empty_projection_retains_identity_while_pending_or_failed();
    test_apply_failure_freezes_cursor_and_stop_retries_reset();
    test_application_requires_explicit_replay_controller();
    test_unavailable_controller_contract();
    test_reference_controller_validation_and_missing_identity();
    test_reference_controller_covers_all_runtime_actions_and_failures();
    test_facade_identity_exclusion_and_fixed_revision();
    test_replay_exclusion_is_per_facade_instance();
    test_failed_stop_does_not_consume_request_identity();
    test_pending_stop_does_not_consume_request_identity();
    test_failed_empty_begin_retains_facade_identity_and_exclusion();
    std::cout << "performance replay controller tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
