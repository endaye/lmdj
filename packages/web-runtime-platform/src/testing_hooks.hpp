#pragma once

#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING

#include <atomic>
#include <span>

#include <lmdj/web_runtime/control_runtime.hpp>

namespace lmdj::web_runtime::testing {

struct CancelPendingSwitchHook {
  void* context;
  void (*invoke)(void*) noexcept;
};
static_assert(std::atomic<CancelPendingSwitchHook*>::is_always_lock_free);

void set_cancel_pending_switch_hook(CancelPendingSwitchHook* hook) noexcept;
void invoke_cancel_pending_switch_hook() noexcept;

inline nlohmann::json fail_next_pattern_publication(
    ControlRuntime& runtime) {
  return runtime.dispatch(
      "__testing.fail-next-pattern-publication",
      nlohmann::json::object(),
      std::span<const std::byte>{});
}

}  // namespace lmdj::web_runtime::testing

#endif
