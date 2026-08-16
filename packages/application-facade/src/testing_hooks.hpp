#pragma once

#include <atomic>

#if defined(LMDJ_C_API_TESTING)
#include <lmdj/facade/c_api.h>
#endif

namespace lmdj::facade::testing {

struct SampleProjectionHook {
  void* context;
  void (*invoke)(void*) noexcept;
};

void set_sample_projection_hook(SampleProjectionHook* hook) noexcept;
void invoke_sample_projection_hook() noexcept;

#if defined(LMDJ_C_API_TESTING)
struct InvokeGate {
  lmdj_engine* engine;
  std::atomic<bool> entered{false};
  std::atomic<bool> release{false};
};

void set_invoke_gate(InvokeGate* gate) noexcept;
void block_invoke_if_selected(lmdj_engine* engine) noexcept;
#endif

}  // namespace lmdj::facade::testing
