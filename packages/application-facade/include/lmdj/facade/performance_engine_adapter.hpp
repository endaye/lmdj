#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/facade/performance_ports.hpp>
#include <lmdj/facade/performance_replay.hpp>

namespace lmdj::facade {

// The gateway is the adapter's sole Pattern publication boundary. It accepts
// immutable material already resolved by Core; neither it nor the Host maps a
// Pattern Slot or reads Project Truth.
struct PatternPublicationGateway {
  using Publish = std::function<foundation::Result<audio::PatternPublication>(
      std::shared_ptr<const cooker::RuntimeSnapshot>,
      std::optional<std::uint64_t>,
      std::optional<audio::PatternReplacementAuthority>)>;
  using PublishImmediate =
      std::function<foundation::Result<audio::PatternPublication>(
          std::shared_ptr<const cooker::RuntimeSnapshot>)>;
  using Cancel = std::function<bool(const audio::PatternReplacementAuthority&)>;

  Publish publish;
  PublishImmediate publish_immediate;
  Cancel cancel;
};

PatternPublicationGateway make_engine_pattern_publication_gateway(
    audio::RealtimeEngine& engine);

// Core adapter over a RealtimeEngine (HRS-D9). The engine must outlive the
// adapter, and must be stopped and callback-drained (queue/voices quiescent)
// before adapter destruction. All members are control-thread surfaces; render
// gains no entry point.
struct EnginePerformanceAdapter {
  std::shared_ptr<PerformanceClock> clock;
  std::shared_ptr<PerformanceInputSequencer> input_sequencer;
  std::shared_ptr<PatternLaunchAcknowledger> launch_acknowledger;
  std::shared_ptr<PerformanceReplayController> replay_controller;
  std::shared_ptr<PerformanceGestureSink> gesture_sink;
  std::function<void()> service;
};

EnginePerformanceAdapter make_engine_performance_adapter(
    audio::RealtimeEngine& engine, PatternPublicationGateway gateway);

}  // namespace lmdj::facade
