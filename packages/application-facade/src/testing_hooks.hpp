#pragma once

#if !defined(LMDJ_C_API_TESTING)
#error "C API testing hooks require LMDJ_C_API_TESTING"
#endif

#include <atomic>

#include <lmdj/facade/c_api.h>

namespace lmdj::facade::testing {

struct InvokeGate {
  lmdj_engine* engine;
  std::atomic<bool> entered{false};
  std::atomic<bool> release{false};
};

void set_invoke_gate(InvokeGate* gate) noexcept;
void block_invoke_if_selected(lmdj_engine* engine) noexcept;

}  // namespace lmdj::facade::testing
