#pragma once

#if defined(LMDJ_PATTERN_TRANSPORT_TESTING) && LMDJ_PATTERN_TRANSPORT_TESTING
#include <lmdj/facade/pattern_transport_ports.hpp>

namespace lmdj::facade::testing {
// Conformance-only observation on the actual production I/O owner thread.
// A hook and its context must outlive every owner that could have acquired it;
// install/remove only while the test's work gate is idle or fully settled.
struct PatternTransportIoWorkHook {
  void* context;
  void (*before_execute)(void*, const PatternTransportWorkRequest&) noexcept;
  void (*after_execute)(void*, const PatternTransportWorkRequest&,
                        const PatternTransportWorkCompletion*) noexcept;
};
void install_pattern_transport_io_work_hook_for_testing(
    const PatternTransportIoWorkHook*) noexcept;
}  // namespace lmdj::facade::testing
#endif
