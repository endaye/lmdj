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

// Arms one throw at the next public Application entry, so the catch-all every
// entry installs can be proven to convert an unexpected exception into the
// documented failure envelope instead of letting it escape across the Host
// boundary. Deliberately *not* noexcept: throwing is the whole point. One-shot
// like the projection hook above — it disarms itself when it fires, so an
// armed hook cannot leak into an unrelated call.
struct ApiEntryHook {
  void* context;
  void (*invoke)(void*);
};

void set_api_entry_hook(ApiEntryHook* hook) noexcept;
void invoke_api_entry_hook();

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
