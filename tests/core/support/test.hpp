#pragma once

#include <source_location>
#include <stdexcept>
#include <string>
#include <string_view>

namespace lmdj::test {

inline void check(
    bool condition,
    std::string_view expression,
    const std::source_location location = std::source_location::current()) {
  if (condition) {
    return;
  }
  throw std::runtime_error(
      std::string(location.file_name()) + ":" +
      std::to_string(location.line()) + ": check failed: " +
      std::string(expression));
}

}  // namespace lmdj::test

#define LMDJ_CHECK(expression) \
  ::lmdj::test::check(static_cast<bool>(expression), #expression)
