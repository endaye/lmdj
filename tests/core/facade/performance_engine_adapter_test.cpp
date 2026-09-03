#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/facade/performance_engine_adapter.hpp>

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::RealtimeEngine;
using lmdj::cooker::PcmSample;
using lmdj::cooker::PerformanceReplayBoundary;
using lmdj::cooker::PerformanceReplayProjection;
using lmdj::cooker::ResolvedEvent;
using lmdj::cooker::ResolvedPad;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::FxEngagePerformanceEvent;
using lmdj::domain::HoldOnPerformanceEvent;
using lmdj::domain::PadHitPerformanceEvent;
using lmdj::domain::PadSlotId;
using lmdj::domain::PatternLaunchPerformanceEvent;
using lmdj::domain::PerformanceEvent;
using lmdj::domain::PerformanceFx;
using lmdj::domain::PerformanceId;
using lmdj::domain::TriggerMode;
using lmdj::facade::PatternLaunchOutcome;
using lmdj::facade::PatternLaunchOutcomeKind;
using lmdj::facade::ReplayId;
using lmdj::facade::ReplayState;
using lmdj::foundation::CommandId;
using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::Result;
using lmdj::foundation::SequenceSessionId;

constexpr auto kProject = "72000000-0000-4000-8000-000000000001";
constexpr auto kPatternA = "72000000-0000-4000-8000-000000000002";
constexpr auto kPatternB = "72000000-0000-4000-8000-000000000003";
constexpr auto kPatternC = "72000000-0000-4000-8000-000000000004";
constexpr auto kSession = "72000000-0000-4000-8000-000000000005";
constexpr auto kFailedSession = "72000000-0000-4000-8000-000000000012";
constexpr auto kAppliedSession = "72000000-0000-4000-8000-000000000013";
constexpr auto kFirstRequest = "72000000-0000-4000-8000-000000000006";
constexpr auto kSecondRequest = "72000000-0000-4000-8000-000000000007";
constexpr auto kThirdRequest = "72000000-0000-4000-8000-000000000008";
constexpr auto kFourthRequest = "72000000-0000-4000-8000-000000000011";
constexpr auto kReplay = "72000000-0000-4000-8000-000000000009";
constexpr auto kPerformance = "72000000-0000-4000-8000-000000000010";
constexpr std::uint64_t kBarTick = 3'840;
constexpr std::uint64_t kBarFramesAt120Bpm = 96'000;

std::shared_ptr<const PcmSample> sample(std::int16_t value = 2'000) {
  return std::make_shared<const PcmSample>(
      PcmSample{48'000, 1, std::vector<std::int16_t>(4'096, value)});
}

std::shared_ptr<const RuntimeSnapshot> snapshot(const char* pattern,
                                                std::uint64_t revision = 1,
    std::int16_t sample_value = 2'000) {
  const auto pcm = sample(sample_value);
  const ResolvedPlayback playback{0, 4'096, TriggerMode::one_shot, 1.0F, false};
  const ResolvedPad pad{
      PadSlotId{0, 0},
      {std::string(64, 'a'), "audio/wav", revision},
      pcm,
      playback,
  };
  return std::make_shared<const RuntimeSnapshot>(RuntimeSnapshot{
      ProjectId{kProject},
      PatternId{pattern},
      revision,
      120,
      1,
      960,
      static_cast<std::uint32_t>(kBarTick),
      {pad},
      {ResolvedEvent{PadSlotId{0, 0}, 0, 240, 100, pcm}},
  });
}

void render(RealtimeEngine& engine, std::uint64_t frames) {
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  while (frames != 0) {
    const auto block = static_cast<std::uint32_t>(
        std::min<std::uint64_t>(frames, left.size()));
    engine.render(left.data(), right.data(), block);
    frames -= block;
  }
}

std::vector<PatternLaunchOutcome> outcomes_for(
    lmdj::facade::EnginePerformanceAdapter& adapter) {
  const SequenceSessionId session{kSession};
  const auto outcomes = adapter.launch_acknowledger->peek(session);
  for (const auto& outcome : outcomes) {
    LMDJ_CHECK(
        adapter.launch_acknowledger->commit(session, outcome.request_id)
            .has_value());
  }
  return outcomes;
}

void prepare_running_engine(RealtimeEngine& engine);

void test_launch_outcomes_are_two_phase_ordered_and_session_isolated() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);
  const SequenceSessionId cancelled_session{kSession};
  const SequenceSessionId failed_session{kFailedSession};
  const SequenceSessionId applied_session{kAppliedSession};

  LMDJ_CHECK(adapter.launch_acknowledger
                 ->reserve(cancelled_session, CommandId{kFirstRequest}, 1,
                           kBarTick, snapshot(kPatternA))
                 .has_value());
  LMDJ_CHECK(adapter.launch_acknowledger
                 ->reserve(cancelled_session, CommandId{kSecondRequest}, 2,
                           kBarTick, snapshot(kPatternB))
                 .has_value());
  const auto failed = adapter.launch_acknowledger->reserve(
      failed_session, CommandId{kThirdRequest}, 3,
      std::numeric_limits<std::uint64_t>::max(), snapshot(kPatternC));
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(adapter.launch_acknowledger
                 ->reserve(applied_session, CommandId{kFourthRequest}, 4, 0,
                           nullptr)
                 .has_value());

  render(engine, kBarFramesAt120Bpm + 1);
  adapter.service();

  const auto ordered = adapter.launch_acknowledger->peek(cancelled_session);
  const auto repeated = adapter.launch_acknowledger->peek(cancelled_session);
  LMDJ_CHECK(ordered.size() == 2);
  LMDJ_CHECK(repeated.size() == ordered.size());
  LMDJ_CHECK(ordered.at(0).request_id == CommandId{kFirstRequest});
  LMDJ_CHECK(ordered.at(0).kind == PatternLaunchOutcomeKind::cancelled);
  LMDJ_CHECK(ordered.at(1).request_id == CommandId{kSecondRequest});
  LMDJ_CHECK(ordered.at(1).kind == PatternLaunchOutcomeKind::applied);
  LMDJ_CHECK(repeated.at(0).request_id == ordered.at(0).request_id);
  LMDJ_CHECK(repeated.at(1).request_id == ordered.at(1).request_id);

  const auto failed_only = adapter.launch_acknowledger->peek(failed_session);
  LMDJ_CHECK(failed_only.size() == 1);
  LMDJ_CHECK(failed_only.front().request_id == CommandId{kThirdRequest});
  LMDJ_CHECK(failed_only.front().kind == PatternLaunchOutcomeKind::failed);
  const auto applied_only = adapter.launch_acknowledger->peek(applied_session);
  LMDJ_CHECK(applied_only.size() == 1);
  LMDJ_CHECK(applied_only.front().request_id == CommandId{kFourthRequest});
  LMDJ_CHECK(applied_only.front().kind == PatternLaunchOutcomeKind::applied);

  const auto out_of_order = adapter.launch_acknowledger->commit(
      cancelled_session, CommandId{kSecondRequest});
  LMDJ_CHECK(!out_of_order.has_value());
  LMDJ_CHECK(out_of_order.error().code == ErrorCode::invalid_argument);
  const auto cross_session = adapter.launch_acknowledger->commit(
      failed_session, CommandId{kFourthRequest});
  LMDJ_CHECK(!cross_session.has_value());
  LMDJ_CHECK(adapter.launch_acknowledger->peek(cancelled_session).size() == 2);
  LMDJ_CHECK(adapter.launch_acknowledger->peek(failed_session).size() == 1);
  LMDJ_CHECK(adapter.launch_acknowledger->peek(applied_session).size() == 1);

  LMDJ_CHECK(adapter.launch_acknowledger
                 ->commit(cancelled_session, CommandId{kFirstRequest})
                 .has_value());
  LMDJ_CHECK(adapter.launch_acknowledger
                 ->commit(cancelled_session, CommandId{kSecondRequest})
                 .has_value());
  LMDJ_CHECK(adapter.launch_acknowledger
                 ->commit(failed_session, CommandId{kThirdRequest})
                 .has_value());
  LMDJ_CHECK(adapter.launch_acknowledger
                 ->commit(applied_session, CommandId{kFourthRequest})
                 .has_value());
  LMDJ_CHECK(adapter.launch_acknowledger->peek(cancelled_session).empty());
  LMDJ_CHECK(adapter.launch_acknowledger->peek(failed_session).empty());
  LMDJ_CHECK(adapter.launch_acknowledger->peek(applied_session).empty());
  LMDJ_CHECK(!adapter.launch_acknowledger
                  ->commit(applied_session, CommandId{kFourthRequest})
                  .has_value());
}

void prepare_running_engine(RealtimeEngine& engine) {
  auto bank =
      lmdj::audio::PreparedSampleBank::from_snapshot(*snapshot(kPatternA));
  LMDJ_CHECK(bank.has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank.value())) ==
             lmdj::audio::PublishResult::accepted);
  LMDJ_CHECK(engine.prepare_master_fx(120).has_value());
  LMDJ_CHECK(engine.start().has_value());
}

void test_applied_boundary_and_clock_reanchor_are_exact() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);

  const auto reservation = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kFirstRequest}, 1, kBarTick,
      snapshot(kPatternA));
  LMDJ_CHECK(reservation.has_value());
  LMDJ_CHECK(reservation.value().target_tick == kBarTick);
  LMDJ_CHECK(!reservation.value().claimed);
  render(engine, kBarFramesAt120Bpm - 1);
  adapter.service();
  LMDJ_CHECK(outcomes_for(adapter).empty());
  // A boundary at frame N is rendered by the callback whose first frame is N;
  // rendered_frames reaches N before that callback and N + 1 afterwards.
  render(engine, 2);
  adapter.service();
  const auto applied = outcomes_for(adapter);
  LMDJ_CHECK(applied.size() == 1);
  LMDJ_CHECK(applied.front().request_id == CommandId{kFirstRequest});
  LMDJ_CHECK(applied.front().effective_tick == kBarTick);
  LMDJ_CHECK(applied.front().kind == PatternLaunchOutcomeKind::applied);
  adapter.service();
  LMDJ_CHECK(outcomes_for(adapter).empty());

  LMDJ_CHECK(adapter.clock->read_tick().value() == kBarTick);
  adapter.clock->anchor(60, kBarTick);
  render(engine, 48'000);
  LMDJ_CHECK(adapter.clock->read_tick().value() == kBarTick + 960);
  adapter.clock->anchor(240, kBarTick - 100);
  LMDJ_CHECK(adapter.clock->read_tick().value() >= kBarTick + 960);
}

void test_clock_reanchor_preserves_fractional_tick_progress() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);

  render(engine, 1);
  LMDJ_CHECK(adapter.clock->read_tick().value() == 0);
  adapter.clock->anchor(60, 0);
  render(engine, 48);
  LMDJ_CHECK(adapter.clock->read_tick().value() == 1);
}

void test_clock_reanchor_keeps_failed_fractional_state_invalid() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
  constexpr auto last_representable_tick =
      maximum / lmdj::audio::kTickDenominator;
  constexpr auto last_tick_numerator =
      last_representable_tick * lmdj::audio::kTickDenominator;
  constexpr auto frames_until_overflow =
      (maximum - last_tick_numerator) /
          (240U * lmdj::audio::kTransportPpq) +
      1U;
  adapter.clock->anchor(240, last_representable_tick);

  render(engine, frames_until_overflow);
  LMDJ_CHECK(!adapter.clock->read_tick().has_value());
  adapter.clock->anchor(120, last_representable_tick);
  LMDJ_CHECK(!adapter.clock->read_tick().has_value());
}

void test_clock_preserves_fractional_progress_across_engine_restart() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);

  render(engine, 48);
  LMDJ_CHECK(adapter.clock->read_tick().value() == 1);
  adapter.service();
  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  render(engine, 49);
  LMDJ_CHECK(adapter.clock->read_tick().value() == 3);

  adapter.clock->anchor(60, 3);
  render(engine, 50);
  LMDJ_CHECK(adapter.clock->read_tick().value() == 4);
  const auto reservation = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kFirstRequest}, 1, kBarTick,
      snapshot(kPatternA));
  LMDJ_CHECK(reservation.has_value());
  LMDJ_CHECK(reservation.value().target_tick == kBarTick);
}

void test_input_sequence_continues_after_the_seed() {
  RealtimeEngine engine;
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));

  LMDJ_CHECK(adapter.clock->read_tick().value() == 0);
  adapter.input_sequencer->seed(41);
  LMDJ_CHECK(adapter.input_sequencer->next().value() == 42);
  adapter.input_sequencer->seed(20);
  LMDJ_CHECK(adapter.input_sequencer->next().value() == 43);
}

void test_incomplete_pattern_gateway_is_rejected() {
  RealtimeEngine engine;
  auto gateway =
      lmdj::facade::make_engine_pattern_publication_gateway(engine);
  const auto missing_material = gateway.publish(nullptr, std::nullopt,
                                                std::nullopt);
  LMDJ_CHECK(!missing_material.has_value());
  LMDJ_CHECK(missing_material.error().code == ErrorCode::invalid_argument);

  bool rejected = false;
  try {
    static_cast<void>(lmdj::facade::make_engine_performance_adapter(
        engine, lmdj::facade::PatternPublicationGateway{}));
  } catch (const std::invalid_argument&) {
    rejected = true;
  }
  LMDJ_CHECK(rejected);
}

void test_latest_wins_and_claimed_boundary_defers() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);

  LMDJ_CHECK(adapter.launch_acknowledger
                 ->reserve(SequenceSessionId{kSession},
                           CommandId{kFirstRequest}, 1, kBarTick,
                           snapshot(kPatternA))
                 .has_value());
  const auto replacement = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kSecondRequest}, 2, kBarTick,
      snapshot(kPatternB));
  LMDJ_CHECK(replacement.has_value());
  LMDJ_CHECK(!replacement.value().claimed);
  const auto replaced = outcomes_for(adapter);
  LMDJ_CHECK(replaced.size() == 1);
  LMDJ_CHECK(replaced.front().request_id == CommandId{kFirstRequest});
  LMDJ_CHECK(replaced.front().kind == PatternLaunchOutcomeKind::cancelled);
  render(engine, kBarFramesAt120Bpm + 1);
  adapter.service();
  const auto applied = outcomes_for(adapter);
  LMDJ_CHECK(applied.size() == 1);
  LMDJ_CHECK(applied.front().request_id == CommandId{kSecondRequest});
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternB});

  const auto already_claimed = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kThirdRequest}, 3, kBarTick * 2,
      snapshot(kPatternC));
  LMDJ_CHECK(already_claimed.has_value());
  render(engine, kBarFramesAt120Bpm);
  const auto deferred = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kFirstRequest}, 4, kBarTick * 2,
      snapshot(kPatternA));
  LMDJ_CHECK(deferred.has_value());
  LMDJ_CHECK(deferred.value().claimed);
  LMDJ_CHECK(deferred.value().target_tick == kBarTick * 3);
  LMDJ_CHECK(outcomes_for(adapter).empty());

  const auto successor = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kFourthRequest}, 5, kBarTick * 3,
      snapshot(kPatternB));
  LMDJ_CHECK(successor.has_value());
  LMDJ_CHECK(!successor.value().claimed);
  LMDJ_CHECK(successor.value().target_tick == kBarTick * 3);
  const auto replaced_successor = outcomes_for(adapter);
  LMDJ_CHECK(replaced_successor.size() == 1);
  LMDJ_CHECK(replaced_successor.front().request_id == CommandId{kFirstRequest});
  LMDJ_CHECK(replaced_successor.front().kind ==
             PatternLaunchOutcomeKind::cancelled);

  adapter.service();
  const auto predecessor_applied = outcomes_for(adapter);
  LMDJ_CHECK(predecessor_applied.size() == 1);
  LMDJ_CHECK(predecessor_applied.front().request_id ==
             CommandId{kThirdRequest});
  LMDJ_CHECK(predecessor_applied.front().kind ==
             PatternLaunchOutcomeKind::applied);
  LMDJ_CHECK(predecessor_applied.front().effective_tick == kBarTick * 2);
  render(engine, kBarFramesAt120Bpm);
  adapter.service();
  const auto deferred_applied = outcomes_for(adapter);
  LMDJ_CHECK(deferred_applied.size() == 1);
  LMDJ_CHECK(deferred_applied.front().request_id == CommandId{kFourthRequest});
  LMDJ_CHECK(deferred_applied.front().effective_tick == kBarTick * 3);
}

void test_service_recovers_claimed_predecessor_after_crossing_successor() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);

  LMDJ_CHECK(adapter.launch_acknowledger
                 ->reserve(SequenceSessionId{kSession},
                           CommandId{kFirstRequest}, 1, kBarTick,
                           snapshot(kPatternA))
                 .has_value());
  render(engine, kBarFramesAt120Bpm + 1);
  const auto successor = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kSecondRequest}, 2, kBarTick,
      snapshot(kPatternB));
  LMDJ_CHECK(successor.has_value());
  LMDJ_CHECK(successor.value().claimed);
  LMDJ_CHECK(successor.value().target_tick == kBarTick * 2);

  render(engine, kBarFramesAt120Bpm);
  adapter.service();
  const auto applied = outcomes_for(adapter);
  LMDJ_CHECK(applied.size() == 2);
  LMDJ_CHECK(applied.at(0).request_id == CommandId{kFirstRequest});
  LMDJ_CHECK(applied.at(0).effective_tick == kBarTick);
  LMDJ_CHECK(applied.at(0).kind == PatternLaunchOutcomeKind::applied);
  LMDJ_CHECK(applied.at(1).request_id == CommandId{kSecondRequest});
  LMDJ_CHECK(applied.at(1).effective_tick == kBarTick * 2);
  LMDJ_CHECK(applied.at(1).kind == PatternLaunchOutcomeKind::applied);
}

void test_restart_cancels_unclaimed_pattern_before_new_reservation() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);

  const auto predecessor = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kFirstRequest}, 1, kBarTick,
      snapshot(kPatternA));
  LMDJ_CHECK(predecessor.has_value());
  LMDJ_CHECK(!predecessor.value().claimed);
  LMDJ_CHECK(predecessor.value().target_tick == kBarTick);

  engine.stop();
  LMDJ_CHECK(engine.pattern_telemetry().pending_generation == 0);
  LMDJ_CHECK(engine.start().has_value());

  const auto successor = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kSecondRequest}, 2, kBarTick,
      snapshot(kPatternB));
  LMDJ_CHECK(successor.has_value());
  LMDJ_CHECK(!successor.value().claimed);
  LMDJ_CHECK(successor.value().target_tick == kBarTick);

  const auto cancelled = outcomes_for(adapter);
  LMDJ_CHECK(cancelled.size() == 1);
  LMDJ_CHECK(cancelled.front().request_id == CommandId{kFirstRequest});
  LMDJ_CHECK(cancelled.front().effective_tick == kBarTick);
  LMDJ_CHECK(cancelled.front().kind == PatternLaunchOutcomeKind::cancelled);

  render(engine, kBarFramesAt120Bpm + 1);
  adapter.service();
  const auto applied = outcomes_for(adapter);
  LMDJ_CHECK(applied.size() == 1);
  LMDJ_CHECK(applied.front().request_id == CommandId{kSecondRequest});
  LMDJ_CHECK(applied.front().effective_tick == kBarTick);
  LMDJ_CHECK(applied.front().kind == PatternLaunchOutcomeKind::applied);
}

void test_service_cancels_prior_epoch_pattern_exactly_once() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);

  const auto reservation = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kFirstRequest}, 1, kBarTick,
      snapshot(kPatternA));
  LMDJ_CHECK(reservation.has_value());
  LMDJ_CHECK(!reservation.value().claimed);

  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  adapter.service();

  const auto cancelled = outcomes_for(adapter);
  LMDJ_CHECK(cancelled.size() == 1);
  LMDJ_CHECK(cancelled.front().request_id == CommandId{kFirstRequest});
  LMDJ_CHECK(cancelled.front().effective_tick == kBarTick);
  LMDJ_CHECK(cancelled.front().kind == PatternLaunchOutcomeKind::cancelled);
  adapter.service();
  LMDJ_CHECK(outcomes_for(adapter).empty());
}

void test_claimed_pattern_is_not_superseded_before_its_boundary() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  adapter.clock->anchor(120, 0);

  LMDJ_CHECK(adapter.launch_acknowledger
                 ->reserve(SequenceSessionId{kSession},
                           CommandId{kFirstRequest}, 1, kBarTick,
                           snapshot(kPatternA))
                 .has_value());
  render(engine, 1);
  const auto successor = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kSecondRequest}, 2, kBarTick,
      snapshot(kPatternB));
  LMDJ_CHECK(successor.has_value());
  LMDJ_CHECK(successor.value().claimed);
  LMDJ_CHECK(successor.value().target_tick == kBarTick * 2);

  render(engine, kBarFramesAt120Bpm);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternA});
  render(engine, kBarFramesAt120Bpm);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternB});
  adapter.service();
  const auto applied = outcomes_for(adapter);
  LMDJ_CHECK(applied.size() == 2);
  LMDJ_CHECK(applied.at(0).request_id == CommandId{kFirstRequest});
  LMDJ_CHECK(applied.at(0).effective_tick == kBarTick);
  LMDJ_CHECK(applied.at(0).kind == PatternLaunchOutcomeKind::applied);
  LMDJ_CHECK(applied.at(1).request_id == CommandId{kSecondRequest});
  LMDJ_CHECK(applied.at(1).effective_tick == kBarTick * 2);
  LMDJ_CHECK(applied.at(1).kind == PatternLaunchOutcomeKind::applied);
}

void test_empty_cancel_and_failure_never_create_ghost_applied() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto gateway = lmdj::facade::make_engine_pattern_publication_gateway(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(engine, gateway);
  adapter.clock->anchor(120, 0);

  const auto initial = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kFirstRequest}, 1, kBarTick,
      snapshot(kPatternA));
  LMDJ_CHECK(initial.has_value());
  adapter.launch_acknowledger->cancel(SequenceSessionId{kSession});
  const auto cancelled = outcomes_for(adapter);
  LMDJ_CHECK(cancelled.size() == 1);
  LMDJ_CHECK(cancelled.front().kind == PatternLaunchOutcomeKind::cancelled);
  render(engine, kBarFramesAt120Bpm + 1);
  adapter.service();
  LMDJ_CHECK(outcomes_for(adapter).empty());

  const auto playing = engine.current_pattern_id();
  const auto empty = adapter.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kSecondRequest}, 2, kBarTick * 2,
      nullptr);
  LMDJ_CHECK(empty.has_value());
  LMDJ_CHECK(engine.pattern_telemetry().pending_publications == 0);
  render(engine, kBarFramesAt120Bpm);
  adapter.service();
  const auto empty_applied = outcomes_for(adapter);
  LMDJ_CHECK(empty_applied.size() == 1);
  LMDJ_CHECK(empty_applied.front().kind == PatternLaunchOutcomeKind::applied);
  LMDJ_CHECK(empty_applied.front().effective_tick == kBarTick * 2);
  LMDJ_CHECK(engine.current_pattern_id() == playing);

  gateway.publish =
      [](std::shared_ptr<const RuntimeSnapshot>, std::optional<std::uint64_t>,
         std::optional<lmdj::audio::PatternReplacementAuthority>) {
        return Result<lmdj::audio::PatternPublication>::failure(Error{
            ErrorCode::internal_error, "injected Pattern publication failure"});
      };
  auto failing =
      lmdj::facade::make_engine_performance_adapter(engine, std::move(gateway));
  failing.clock->anchor(120, kBarTick * 2);
  const auto rejected = failing.launch_acknowledger->reserve(
      SequenceSessionId{kSession}, CommandId{kThirdRequest}, 3, kBarTick * 3,
      snapshot(kPatternC));
  LMDJ_CHECK(!rejected.has_value());
  const auto failed = outcomes_for(failing);
  LMDJ_CHECK(failed.size() == 1);
  LMDJ_CHECK(failed.front().kind == PatternLaunchOutcomeKind::failed);
  render(engine, kBarFramesAt120Bpm);
  failing.service();
  LMDJ_CHECK(outcomes_for(failing).empty());
}

std::shared_ptr<const PerformanceReplayProjection> replay_projection() {
  auto value = PerformanceReplayProjection{
      PerformanceId{kPerformance},
      1,
      120,
      false,
      50,
      {},
      {},
      {
          PerformanceReplayBoundary{
              0, PerformanceEvent{PadHitPerformanceEvent{0, 240, 240, 100}}},
          PerformanceReplayBoundary{
              0, PerformanceEvent{PatternLaunchPerformanceEvent{1, 240}}},
          PerformanceReplayBoundary{0,
                                    PerformanceEvent{FxEngagePerformanceEvent{
                                        PerformanceFx::filter, 500, 240}}},
          PerformanceReplayBoundary{
              960, PerformanceEvent{HoldOnPerformanceEvent{960}}},
      },
      4,
  };
  const auto material = snapshot(kPatternA);
  auto replay_pad = material->pads.front();
  replay_pad.playback.trigger_mode = TriggerMode::loop_gate;
  value.pads.at(0) = std::move(replay_pad);
  auto silent_pattern = *material;
  silent_pattern.events.clear();
  value.patterns.at(1) =
      std::make_shared<const RuntimeSnapshot>(std::move(silent_pattern));
  return std::make_shared<const PerformanceReplayProjection>(std::move(value));
}

std::shared_ptr<const PerformanceReplayProjection> pad_only_replay_projection(
    std::uint16_t bpm) {
  auto value = *replay_projection();
  value.bpm = bpm;
  value.boundaries = {PerformanceReplayBoundary{
      0, PerformanceEvent{PadHitPerformanceEvent{0, 240, 240, 100}}}};
  value.event_count = 1;
  return std::make_shared<const PerformanceReplayProjection>(std::move(value));
}

std::shared_ptr<const PerformanceReplayProjection>
pattern_only_replay_projection() {
  auto value = *replay_projection();
  value.boundaries = {PerformanceReplayBoundary{
      0, PerformanceEvent{PatternLaunchPerformanceEvent{1, 240}}}};
  value.event_count = 1;
  return std::make_shared<const PerformanceReplayProjection>(std::move(value));
}

std::shared_ptr<const PerformanceReplayProjection>
positive_pattern_replay_projection() {
  auto value = *pattern_only_replay_projection();
  value.patterns.at(1) = snapshot(kPatternB, 7, 20'000);
  return std::make_shared<const PerformanceReplayProjection>(std::move(value));
}

std::shared_ptr<const PerformanceReplayProjection>
delayed_pad_replay_projection() {
  auto value = *pad_only_replay_projection(120);
  value.boundaries = {PerformanceReplayBoundary{
      2, PerformanceEvent{PadHitPerformanceEvent{0, 240, 240, 100}}}};
  return std::make_shared<const PerformanceReplayProjection>(std::move(value));
}

void test_replay_pattern_launch_survives_service_frame_race() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto initial = lmdj::audio::PreparedPatternView::from_snapshot(
      *snapshot(kPatternB));
  LMDJ_CHECK(initial.has_value());
  LMDJ_CHECK(engine.publish_pattern_view(std::move(initial.value()), 0).result ==
             lmdj::audio::PatternPublishResult::accepted);
  render(engine, 1);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternB});
  auto stale_exact = lmdj::audio::PreparedPatternView::from_snapshot(
      *snapshot(kPatternC));
  LMDJ_CHECK(stale_exact.has_value());
  LMDJ_CHECK(
      engine.publish_pattern_view(std::move(stale_exact.value()), 0).result ==
      lmdj::audio::PatternPublishResult::publish_queue_full);

  auto gateway = lmdj::facade::make_engine_pattern_publication_gateway(engine);
  auto publish_immediate = std::move(gateway.publish_immediate);
  bool raced = false;
  gateway.publish_immediate =
      [&engine, &publish_immediate, &raced](
          std::shared_ptr<const RuntimeSnapshot> pattern) {
        render(engine, 1);
        raced = true;
        return publish_immediate(std::move(pattern));
      };
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, std::move(gateway));
  LMDJ_CHECK(adapter.replay_controller
                 ->begin(ReplayId{kReplay}, pattern_only_replay_projection())
                 .has_value());
  adapter.service();
  LMDJ_CHECK(raced);
  render(engine, 1);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternA});
}

void test_replay_pattern_uses_projection_material_and_retains_release_tail() {
  RealtimeEngine engine;
  const auto live_material = snapshot(kPatternA, 1, -20'000);
  auto live_bank = lmdj::audio::PreparedSampleBank::from_snapshot(*live_material);
  LMDJ_CHECK(live_bank.has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(live_bank.value())) ==
             lmdj::audio::PublishResult::accepted);
  LMDJ_CHECK(engine.prepare_master_fx(120).has_value());
  auto silent = *snapshot(kPatternA, 2, 0);
  auto silent_view = lmdj::audio::PreparedPatternView::from_snapshot(silent);
  LMDJ_CHECK(silent_view.has_value());
  LMDJ_CHECK(engine.publish_pattern_view(std::move(silent_view.value())).result ==
             lmdj::audio::PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  auto gateway = lmdj::facade::make_engine_pattern_publication_gateway(engine);
  auto adapter =
      lmdj::facade::make_engine_performance_adapter(engine, gateway);
  LMDJ_CHECK(
      adapter.replay_controller
          ->begin(ReplayId{kReplay}, positive_pattern_replay_projection())
          .has_value());
  adapter.service();
  std::array<float, 2> left{};
  std::array<float, 2> right{};
  engine.render(left.data(), right.data(), 2);
  LMDJ_CHECK(left.at(1) > 0.0F);
  LMDJ_CHECK(right == left);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternB});
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);

  auto replacement = *snapshot(kPatternC, 8, -20'000);
  replacement.events.clear();
  const auto replaced = gateway.publish(
      std::make_shared<const RuntimeSnapshot>(std::move(replacement)),
      engine.telemetry().rendered_frames, std::nullopt);
  LMDJ_CHECK(replaced.has_value());
  render(engine, 1);
  LMDJ_CHECK(engine.current_pattern_id() == PatternId{kPatternC});
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 0);
  render(engine, lmdj::audio::kRealtimeRampFrames);
  LMDJ_CHECK(engine.reclaim_retired_patterns() == 1);
}

void test_idempotent_begin_does_not_retime_the_fixed_replay() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  LMDJ_CHECK(adapter.replay_controller
                 ->begin(ReplayId{kReplay}, pad_only_replay_projection(120))
                 .has_value());
  LMDJ_CHECK(adapter.replay_controller
                 ->begin(ReplayId{kReplay}, pad_only_replay_projection(60))
                 .has_value());
  adapter.service();
  render(engine, 6'000);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
  render(engine, 1 + lmdj::audio::kRealtimeRampFrames);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
}

void test_active_replay_preserves_fractional_progress_across_engine_restart() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  const auto begun = adapter.replay_controller->begin(
      ReplayId{kReplay}, delayed_pad_replay_projection());
  LMDJ_CHECK(begun.has_value());

  render(engine, 48);
  adapter.service();
  LMDJ_CHECK(adapter.replay_controller->status(ReplayId{kReplay})
                 .value()
                 .event_cursor == 0);
  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  render(engine, 49);
  adapter.service();
  LMDJ_CHECK(adapter.replay_controller->status(ReplayId{kReplay})
                 .value()
                 .event_cursor == 1);
  LMDJ_CHECK(engine.telemetry().enqueued_events == 1);
  adapter.service();
  LMDJ_CHECK(engine.telemetry().enqueued_events == 1);
}

void test_replay_progresses_from_rendering_and_periodic_service_only() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  LMDJ_CHECK(engine.arm_capture().has_value());
  render(engine, 1);
  const auto begun =
      adapter.replay_controller->begin(ReplayId{kReplay}, replay_projection());
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().state == ReplayState::playing);
  LMDJ_CHECK(begun.value().event_cursor == 0);

  adapter.service();
  auto progressed = adapter.replay_controller->status(ReplayId{kReplay});
  LMDJ_CHECK(progressed.has_value());
  LMDJ_CHECK(progressed.value().event_cursor == 3);
  auto changed_live_bank = lmdj::audio::PreparedSampleBank::from_snapshot(
      *snapshot(kPatternC, 9, -20'000));
  LMDJ_CHECK(changed_live_bank.has_value());
  LMDJ_CHECK(engine.publish_sample_bank(std::move(changed_live_bank.value())) ==
             lmdj::audio::PublishResult::accepted);
  std::array<float, 2> left{};
  std::array<float, 2> right{};
  engine.render(left.data(), right.data(), 2);
  LMDJ_CHECK(left.at(1) > 0.0F);
  std::array<lmdj::audio::RuntimeTriggerOutcomeEvent, 1> live_outcomes{};
  std::array<lmdj::audio::RuntimeVoiceStateEvent, 1> live_voice_states{};
  std::array<lmdj::audio::CapturedTriggerEvent, 1> captured{};
  LMDJ_CHECK(engine.drain_trigger_outcomes(live_outcomes) == 0);
  LMDJ_CHECK(engine.drain_voice_states(live_voice_states) == 0);
  LMDJ_CHECK(engine.drain_capture(captured) == 0);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);

  constexpr std::uint64_t kReplayDurationFrames = 6'000;
  render(engine, kReplayDurationFrames - 2);
  LMDJ_CHECK(engine.telemetry().active_voices == 1);
  render(engine, 1 + lmdj::audio::kRealtimeRampFrames);
  LMDJ_CHECK(engine.telemetry().active_voices == 0);
  LMDJ_CHECK(engine.drain_trigger_outcomes(live_outcomes) == 0);
  LMDJ_CHECK(engine.drain_voice_states(live_voice_states) == 0);
  LMDJ_CHECK(engine.drain_capture(captured) == 0);

  const auto elapsed = engine.telemetry().rendered_frames - 1;
  render(engine, 24'000 - elapsed);
  LMDJ_CHECK(adapter.replay_controller->status(ReplayId{kReplay})
                 .value()
                 .event_cursor == 3);
  adapter.service();
  const auto pending = adapter.replay_controller->status(ReplayId{kReplay});
  LMDJ_CHECK(pending.has_value());
  LMDJ_CHECK(pending.value().state == ReplayState::playing);
  LMDJ_CHECK(pending.value().event_cursor == 4);
  const auto reset_target = engine.master_fx_telemetry().enqueued_gestures;
  adapter.service();
  LMDJ_CHECK(engine.master_fx_telemetry().enqueued_gestures == reset_target);
  render(engine, 128);
  adapter.service();
  const auto completed = adapter.replay_controller->status(ReplayId{kReplay});
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().state == ReplayState::complete);
  const auto realtime = engine.telemetry();
  const auto fx = engine.master_fx_telemetry();
  const auto pattern = engine.pattern_telemetry();
  LMDJ_CHECK(realtime.enqueued_events >= 1);
  LMDJ_CHECK(fx.enqueued_gestures >= 3);
  LMDJ_CHECK(fx.queue_drops == 0);
  LMDJ_CHECK(pattern.accepted_publications >= 1);
}

std::shared_ptr<const PerformanceReplayProjection> empty_replay_projection() {
  return std::make_shared<const PerformanceReplayProjection>(
      PerformanceReplayProjection{
          PerformanceId{kPerformance}, 2, 120, false, 50, {}, {}, {}, 0});
}

void test_pending_empty_replay_reset_completes_after_engine_restart() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  const auto begun = adapter.replay_controller->begin(
      ReplayId{kReplay}, empty_replay_projection());
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().state == ReplayState::playing);
  LMDJ_CHECK(engine.master_fx_telemetry().enqueued_gestures == 9);

  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  adapter.service();
  const auto completed =
      adapter.replay_controller->status(ReplayId{kReplay});
  LMDJ_CHECK(completed.has_value());
  LMDJ_CHECK(completed.value().state == ReplayState::complete);
  LMDJ_CHECK(engine.master_fx_telemetry().enqueued_gestures == 0);
}

void test_reset_queue_pressure_continues_without_duplicate_gestures() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  for (std::size_t index = 0; index < lmdj::audio::kRealtimeQueueCapacity - 4;
       ++index) {
    LMDJ_CHECK(engine.enqueue_fx_gesture(lmdj::audio::FxGesture{
                   lmdj::audio::FxGestureKind::move, PerformanceFx::filter,
                   static_cast<std::uint16_t>(index % 1'001)}) ==
               lmdj::audio::FxEnqueueResult::accepted);
  }
  const auto before = engine.master_fx_telemetry().enqueued_gestures;
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  const auto begun = adapter.replay_controller->begin(
      ReplayId{kReplay}, empty_replay_projection());
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().state == ReplayState::playing);
  LMDJ_CHECK(engine.master_fx_telemetry().enqueued_gestures == before + 4);

  render(engine, 128);
  adapter.service();
  LMDJ_CHECK(
      adapter.replay_controller->status(ReplayId{kReplay}).value().state ==
      ReplayState::playing);
  LMDJ_CHECK(engine.master_fx_telemetry().enqueued_gestures == before + 9);
  adapter.service();
  LMDJ_CHECK(engine.master_fx_telemetry().enqueued_gestures == before + 9);

  render(engine, 128);
  adapter.service();
  LMDJ_CHECK(
      adapter.replay_controller->status(ReplayId{kReplay}).value().state ==
      ReplayState::complete);
  LMDJ_CHECK(engine.master_fx_telemetry().dequeued_gestures == before + 9);
}

void test_explicit_stop_waits_for_neutral_reset_confirmation() {
  RealtimeEngine engine;
  prepare_running_engine(engine);
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  LMDJ_CHECK(adapter.replay_controller
                 ->begin(ReplayId{kReplay}, pad_only_replay_projection(120))
                 .has_value());

  const auto pending = adapter.replay_controller->stop(ReplayId{kReplay});
  LMDJ_CHECK(pending.has_value());
  LMDJ_CHECK(pending.value().state == ReplayState::playing);
  render(engine, 128);
  const auto stopped = adapter.replay_controller->stop(ReplayId{kReplay});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().state == ReplayState::stopped);
  adapter.service();
  LMDJ_CHECK(adapter.replay_controller->status(ReplayId{kReplay})
                 .value()
                 .state == ReplayState::stopped);
}

}  // namespace

int main() {
  try {
    test_launch_outcomes_are_two_phase_ordered_and_session_isolated();
    test_applied_boundary_and_clock_reanchor_are_exact();
    test_input_sequence_continues_after_the_seed();
    test_incomplete_pattern_gateway_is_rejected();
    test_latest_wins_and_claimed_boundary_defers();
    test_clock_reanchor_preserves_fractional_tick_progress();
    test_clock_reanchor_keeps_failed_fractional_state_invalid();
    test_active_replay_preserves_fractional_progress_across_engine_restart();
    test_clock_preserves_fractional_progress_across_engine_restart();
    test_pending_empty_replay_reset_completes_after_engine_restart();
    test_replay_pattern_launch_survives_service_frame_race();
    test_service_recovers_claimed_predecessor_after_crossing_successor();
    test_restart_cancels_unclaimed_pattern_before_new_reservation();
    test_service_cancels_prior_epoch_pattern_exactly_once();
    test_claimed_pattern_is_not_superseded_before_its_boundary();
    test_empty_cancel_and_failure_never_create_ghost_applied();
    test_replay_pattern_uses_projection_material_and_retains_release_tail();
    test_idempotent_begin_does_not_retime_the_fixed_replay();
    test_replay_progresses_from_rendering_and_periodic_service_only();
    test_reset_queue_pressure_continues_without_duplicate_gestures();
    test_explicit_stop_waits_for_neutral_reset_confirmation();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
