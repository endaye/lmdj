#pragma once

#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING

#include <span>

#include <lmdj/web_runtime/control_runtime.hpp>

namespace lmdj::web_runtime::testing {

inline nlohmann::json fail_next_pattern_publication(
    ControlRuntime& runtime) {
  return runtime.dispatch(
      "__testing.fail-next-pattern-publication",
      nlohmann::json::object(),
      std::span<const std::byte>{});
}

}  // namespace lmdj::web_runtime::testing

#endif
