#include <lmdj/facade/performance_ports.hpp>
#include <lmdj/facade/performance_runtime.hpp>
#include <lmdj/facade/performance_engine_adapter.hpp>
#include <lmdj/facade/performance_replay.hpp>

// These headers are real positive controls in the full Facade's include
// closure. A transitive full-target dependency must not hide a broken split.
#if __has_include(<lmdj/project_io/project_store.hpp>) || \
    __has_include(<lmdj/provider/registry.hpp>)
#error "why: runtime consumer sees Project IO or Provider SDK; remedy: link only the isolated Performance runtime and remove full Facade dependencies"
#endif

#include "tests/core/support/test.hpp"

int main() {
  auto bridge = lmdj::facade::make_headless_performance_runtime_bridge(
      lmdj::facade::make_steady_performance_time_source());
  LMDJ_CHECK(bridge.clock && bridge.input_sequencer &&
             bridge.launch_acknowledger && bridge.replay_controller &&
             bridge.service);

  auto unavailable =
      lmdj::facade::make_unavailable_performance_replay_controller();
  LMDJ_CHECK(unavailable);

  // Never start a callback: the adapter is destroyed before its stopped engine.
  lmdj::audio::RealtimeEngine engine;
  auto adapter = lmdj::facade::make_engine_performance_adapter(
      engine, lmdj::facade::make_engine_pattern_publication_gateway(engine));
  LMDJ_CHECK(adapter.clock && adapter.input_sequencer &&
             adapter.launch_acknowledger && adapter.replay_controller &&
             adapter.gesture_sink && adapter.service);
  return 0;
}
