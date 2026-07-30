#include <dlfcn.h>

#include <array>
#include <cstdio>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "tests/core/support/test.hpp"

#ifndef LMDJ_CORE_C_LIBRARY_PATH
#error "dynamic C ABI library path is required"
#endif

namespace {

std::set<std::string> exported_symbols() {
#if defined(__APPLE__)
  const auto command =
      std::string("nm -gU \"") + LMDJ_CORE_C_LIBRARY_PATH + "\"";
#else
  const auto command =
      std::string("nm -D --defined-only \"") +
      LMDJ_CORE_C_LIBRARY_PATH + "\"";
#endif
  FILE* pipe = ::popen(command.c_str(), "r");
  if (pipe == nullptr) {
    throw std::runtime_error("nm could not inspect the C ABI library");
  }
  std::set<std::string> result;
  std::array<char, 16U * 1024U> buffer{};
  while (::fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) !=
         nullptr) {
    std::istringstream line(buffer.data());
    std::vector<std::string> tokens;
    for (std::string token; line >> token;) {
      tokens.push_back(std::move(token));
    }
    if (tokens.size() < 2) {
      continue;
    }
    auto symbol = tokens.back();
#if defined(__APPLE__)
    if (!symbol.empty() && symbol.front() == '_') {
      symbol.erase(symbol.begin());
    }
#else
    if (const auto version = symbol.find('@');
        version != std::string::npos) {
      symbol.erase(version);
    }
    if (tokens.at(tokens.size() - 2) == "A") {
      continue;
    }
#endif
    result.insert(std::move(symbol));
  }
  if (::pclose(pipe) != 0) {
    throw std::runtime_error("nm failed to inspect the C ABI library");
  }
  return result;
}

}  // namespace

int main() {
  try {
    void* library = ::dlopen(LMDJ_CORE_C_LIBRARY_PATH, RTLD_NOW | RTLD_LOCAL);
    if (library == nullptr) {
      throw std::runtime_error(::dlerror());
    }
    constexpr std::array<std::string_view, 5> symbols{
        "lmdj_engine_create",
        "lmdj_engine_command",
        "lmdj_engine_query",
        "lmdj_string_free",
        "lmdj_engine_free",
    };
    for (const auto symbol : symbols) {
      LMDJ_CHECK(::dlsym(library, symbol.data()) != nullptr);
    }
    const std::set<std::string> expected(
        symbols.begin(), symbols.end());
    LMDJ_CHECK(exported_symbols() == expected);
    LMDJ_CHECK(::dlsym(library, "lmdj_application_internal") == nullptr);
    LMDJ_CHECK(::dlclose(library) == 0);
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
  std::cout << "facade dynamic-load tests: PASS\n";
  return 0;
}
