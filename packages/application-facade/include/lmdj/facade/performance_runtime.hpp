#pragma once

#include <cstdint>
#include <functional>
#include <memory>

#include <lmdj/facade/application.hpp>

namespace lmdj::facade {

class PerformanceTimeSource {
 public:
  virtual ~PerformanceTimeSource() = default;

  // Monotone non-decreasing nanoseconds since an arbitrary epoch.
  virtual std::uint64_t now_ns() = 0;
};

std::shared_ptr<PerformanceTimeSource> make_steady_performance_time_source();

struct PerformanceRuntimeBridge {
  std::shared_ptr<PerformanceClock> clock;
  std::shared_ptr<PerformanceInputSequencer> input_sequencer;
  std::shared_ptr<PatternLaunchAcknowledger> launch_acknowledger;
  std::shared_ptr<PerformanceReplayController> replay_controller;
  std::function<void()> service;
};

PerformanceRuntimeBridge make_headless_performance_runtime_bridge(
    std::shared_ptr<PerformanceTimeSource> time_source);

}  // namespace lmdj::facade
