#include <cstddef>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/json.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::kMaximumJsonContainerDepth;
using lmdj::foundation::parse_bounded_json;
using lmdj::foundation::valid_utf8;

// One object wrapping `depth` nested arrays. nlohmann reports the depth as the
// container stack size before the push, so the outer object is depth 0 and
// `depth` nested arrays reach depth `depth`.
std::string nested(std::size_t depth) {
  std::string value = R"({"nested":)";
  value.reserve(value.size() + depth * 2U + 2U);
  value.append(depth, '[');
  value.append(depth, ']');
  value.push_back('}');
  return value;
}

void test_depth_boundary_is_exact() {
  const auto limit = static_cast<std::size_t>(kMaximumJsonContainerDepth);
  const auto accepted = parse_bounded_json(nested(limit - 1U));
  LMDJ_CHECK(accepted.has_value());
  LMDJ_CHECK(accepted->is_object());

  LMDJ_CHECK(!parse_bounded_json(nested(limit)).has_value());
  LMDJ_CHECK(!parse_bounded_json(nested(limit + 1U)).has_value());
}

void test_excessive_depth_is_rejected_without_crashing() {
  // The failure this guards is a stack overflow in the DOM destructor, which
  // no try/catch can contain. Reaching the assertion at all is the assertion.
  for (const std::size_t depth : {std::size_t{1'000}, std::size_t{200'000}}) {
    LMDJ_CHECK(!parse_bounded_json(nested(depth)).has_value());
    std::istringstream stream(nested(depth));
    LMDJ_CHECK(!parse_bounded_json(stream).has_value());
  }
}

void test_stream_and_bytes_overloads_agree() {
  const std::string document = R"({"a":[1,2,{"b":null}]})";
  const auto from_bytes = parse_bounded_json(document);
  std::istringstream stream(document);
  const auto from_stream = parse_bounded_json(stream);
  LMDJ_CHECK(from_bytes.has_value());
  LMDJ_CHECK(from_stream.has_value());
  LMDJ_CHECK(*from_bytes == *from_stream);
}

void test_malformed_input_is_rejected_without_throwing() {
  for (const auto* document : {"", "{", "{\"a\":}", "nope", "[1,]"}) {
    LMDJ_CHECK(!parse_bounded_json(std::string_view(document)).has_value());
  }
}

void test_valid_utf8_accepts_and_rejects() {
  LMDJ_CHECK(valid_utf8(""));
  LMDJ_CHECK(valid_utf8("ascii"));
  LMDJ_CHECK(valid_utf8("\xc2\xa9"));          // U+00A9
  LMDJ_CHECK(valid_utf8("\xe4\xb8\xad"));      // U+4E2D
  LMDJ_CHECK(valid_utf8("\xf0\x9f\x8e\xb9"));  // U+1F3B9

  LMDJ_CHECK(!valid_utf8("\xff"));              // invalid lead
  LMDJ_CHECK(!valid_utf8("\x80"));              // orphan continuation
  LMDJ_CHECK(!valid_utf8("\xc2"));              // truncated
  LMDJ_CHECK(!valid_utf8("\xc0\xaf"));          // overlong solidus
  LMDJ_CHECK(!valid_utf8("\xe0\x80\xaf"));      // overlong
  LMDJ_CHECK(!valid_utf8("\xed\xa0\x80"));      // surrogate half
  LMDJ_CHECK(!valid_utf8("\xf5\x80\x80\x80"));  // above U+10FFFF
}

}  // namespace

int main() {
  try {
    test_depth_boundary_is_exact();
    test_excessive_depth_is_rejected_without_crashing();
    test_stream_and_bytes_overloads_agree();
    test_malformed_input_is_rejected_without_throwing();
    test_valid_utf8_accepts_and_rejects();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "foundation json tests: PASS\n";
  return 0;
}
