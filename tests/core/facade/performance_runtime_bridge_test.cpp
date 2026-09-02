#include <cstdint>
#include <iostream>
#include <lmdj/facade/performance_runtime.hpp>
#include <memory>

#include <utility>

#include "tests/core/support/test.hpp"

namespace {

constexpr auto kSession = "71000000-0000-4000-8000-000000000001";
constexpr auto kFirstLaunch = "71000000-0000-4000-8000-000000000002";
constexpr auto kSecondLaunch = "71000000-0000-4000-8000-000000000003";
constexpr auto kReplay = "71000000-0000-4000-8000-000000000004";
constexpr auto kPerformance = "71000000-0000-4000-8000-000000000005";

class ScriptedTimeSource final
    : public lmdj::facade::PerformanceTimeSource {
 public:
  std::uint64_t now_ns() override { return now_; }

  void set(std::uint64_t now) { now_ = now; }

 private:
  std::uint64_t now_{};
};

std::shared_ptr<const lmdj::cooker::PerformanceReplayProjection>
replay_projection() {
  using lmdj::cooker::PerformanceReplayBoundary;
  using lmdj::cooker::PerformanceReplayProjection;
  using lmdj::domain::HoldOffPerformanceEvent;
  using lmdj::domain::HoldOnPerformanceEvent;
  using lmdj::domain::PerformanceEvent;
  using lmdj::domain::PerformanceId;

  return std::make_shared<const PerformanceReplayProjection>(
      PerformanceReplayProjection{
          PerformanceId{kPerformance},
          9,
          120,
          false,
          50,
          {},
          {},
          {
              PerformanceReplayBoundary{
                  0, PerformanceEvent{HoldOnPerformanceEvent{0}}},
              PerformanceReplayBoundary{
                  960, PerformanceEvent{HoldOffPerformanceEvent{960}}},
          },
          2,
      });
}

std::shared_ptr<const lmdj::cooker::PerformanceReplayProjection>
empty_replay_projection() {
  return std::make_shared<const lmdj::cooker::PerformanceReplayProjection>(
      lmdj::cooker::PerformanceReplayProjection{
          lmdj::domain::PerformanceId{kPerformance},
          10,
          120,
          false,
          50,
          {},
          {},
          {},
          0,
      });
}

void test_clock_anchoring_and_monotonicity() {
  auto time = std::make_shared<ScriptedTimeSource>();
  time->set(1'000'000'000ULL);
  auto bridge =
      lmdj::facade::make_headless_performance_runtime_bridge(time);

  bridge.clock->anchor(120, 100);
  LMDJ_CHECK(bridge.clock->read_tick().value() == 100);
  time->set(1'500'000'000ULL);
  LMDJ_CHECK(bridge.clock->read_tick().value() == 1060);

  bridge.clock->anchor(60, 1060);
  time->set(2'500'000'000ULL);
  LMDJ_CHECK(bridge.clock->read_tick().value() == 2020);
  time->set(2'000'000'000ULL);
  LMDJ_CHECK(bridge.clock->read_tick().value() == 2020);
}

void test_sequencer_is_strictly_increasing() {
  auto bridge = lmdj::facade::make_headless_performance_runtime_bridge(
      std::make_shared<ScriptedTimeSource>());
  LMDJ_CHECK(bridge.input_sequencer->next().value() == 1);
  LMDJ_CHECK(bridge.input_sequencer->next().value() == 2);
  LMDJ_CHECK(bridge.input_sequencer->next().value() == 3);
}

void test_transport_latest_wins_exactly_once_and_cancel() {
  auto time = std::make_shared<ScriptedTimeSource>();
  auto bridge =
      lmdj::facade::make_headless_performance_runtime_bridge(time);
  bridge.clock->anchor(120, 0);
  const lmdj::foundation::SequenceSessionId session{kSession};

  const auto first = bridge.launch_acknowledger->reserve(
      session,
      lmdj::foundation::CommandId{kFirstLaunch},
      1,
      3840,
      nullptr);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(first.value().target_tick == 3840);
  LMDJ_CHECK(!first.value().claimed);

  const auto second = bridge.launch_acknowledger->reserve(
      session,
      lmdj::foundation::CommandId{kSecondLaunch},
      2,
      3840,
      nullptr);
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(!second.value().claimed);

  time->set(1'999'000'000ULL);
  bridge.service();
  LMDJ_CHECK(bridge.launch_acknowledger->drain(session).empty());
  time->set(2'000'000'000ULL);
  bridge.service();
  const auto outcomes = bridge.launch_acknowledger->drain(session);
  LMDJ_CHECK(outcomes.size() == 1);
  LMDJ_CHECK(outcomes.front().request_id.value() == kSecondLaunch);
  LMDJ_CHECK(outcomes.front().pattern_slot == 2);
  LMDJ_CHECK(outcomes.front().effective_tick == 3840);
  LMDJ_CHECK(
      outcomes.front().kind ==
      lmdj::facade::PatternLaunchOutcomeKind::applied);
  bridge.service();
  LMDJ_CHECK(bridge.launch_acknowledger->drain(session).empty());

  LMDJ_CHECK(
      bridge.launch_acknowledger
          ->reserve(
              session,
              lmdj::foundation::CommandId{kFirstLaunch},
              3,
              7680,
              nullptr)
          .has_value());
  bridge.launch_acknowledger->cancel(session);
  time->set(5'000'000'000ULL);
  bridge.service();
  LMDJ_CHECK(bridge.launch_acknowledger->drain(session).empty());
}

void test_replay_progression_depends_on_elapsed_time_only() {
  auto time = std::make_shared<ScriptedTimeSource>();
  time->set(5'000'000'000ULL);
  auto bridge =
      lmdj::facade::make_headless_performance_runtime_bridge(time);
  const lmdj::facade::ReplayId replay_id{kReplay};
  const auto begun =
      bridge.replay_controller->begin(replay_id, replay_projection());
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().event_cursor == 0);

  time->set(5'500'000'000ULL);
  const auto observed = bridge.replay_controller->status(replay_id);
  LMDJ_CHECK(observed.has_value());
  LMDJ_CHECK(observed.value().event_cursor == 0);

  time->set(5'000'000'000ULL);
  bridge.service();
  LMDJ_CHECK(bridge.replay_controller->status(replay_id).value().event_cursor ==
             1);
  bridge.service();
  LMDJ_CHECK(bridge.replay_controller->status(replay_id).value().event_cursor ==
             1);

  time->set(5'500'000'000ULL);
  bridge.service();
  const auto completed = bridge.replay_controller->status(replay_id);
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().event_cursor == 2);
  LMDJ_CHECK(completed.value().state == lmdj::facade::ReplayState::complete);
}

void test_silent_headless_reset_completes_without_pending_cycle() {
  auto bridge = lmdj::facade::make_headless_performance_runtime_bridge(
      std::make_shared<ScriptedTimeSource>());
  const auto completed = bridge.replay_controller->begin(
      lmdj::facade::ReplayId{kReplay}, empty_replay_projection());
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().state == lmdj::facade::ReplayState::complete);
  LMDJ_CHECK(completed.value().event_cursor == 0);
}

}  // namespace

int main() {
  try {
    test_clock_anchoring_and_monotonicity();
    test_sequencer_is_strictly_increasing();
    test_transport_latest_wins_exactly_once_and_cancel();
    test_replay_progression_depends_on_elapsed_time_only();
    test_silent_headless_reset_completes_without_pending_cycle();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
