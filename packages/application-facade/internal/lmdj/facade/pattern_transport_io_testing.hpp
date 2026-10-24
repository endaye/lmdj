#pragma once

#if defined(LMDJ_PATTERN_TRANSPORT_TESTING) && LMDJ_PATTERN_TRANSPORT_TESTING
#include <lmdj/facade/pattern_transport_ports.hpp>

namespace lmdj::audio { struct PatternTransportReceipt; }

namespace lmdj::facade::testing {
// Conformance-only observation on the actual I/O owner and serialized control.
// A hook and its context must outlive every owner that could have acquired it;
// install/remove only while the test's work gate is idle or fully settled.
struct PatternTransportIoWorkHook {
  void* context;
  void (*before_execute)(void*, const PatternTransportWorkRequest&) noexcept;
  void (*after_execute)(void*, const PatternTransportWorkRequest&,
                        const PatternTransportWorkCompletion*) noexcept;
  void (*closing_receipt)(void*, const audio::PatternTransportReceipt&) noexcept{};
};
void install_pattern_transport_io_work_hook_for_testing(
    const PatternTransportIoWorkHook*) noexcept;
void observe_pattern_transport_closing_receipt_for_testing(
    const audio::PatternTransportReceipt&) noexcept;
}  // namespace lmdj::facade::testing
#endif
