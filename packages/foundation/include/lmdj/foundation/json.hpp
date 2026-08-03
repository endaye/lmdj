#pragma once

#include <istream>
#include <optional>
#include <string>
#include <string_view>

#include <nlohmann/json.hpp>

namespace lmdj::foundation {

std::string canonical_json(const nlohmann::json& value);

// The maximum number of nested JSON containers any boundary will construct.
// Deep nesting is a stack-overflow vector: the parser is iterative, but the
// resulting DOM's destructor recurses, and a stack overflow is not a catchable
// C++ exception, so a try/catch around parsing does not defend against it.
inline constexpr int kMaximumJsonContainerDepth = 64;

// Parse JSON, refusing to build any container at or beyond
// kMaximumJsonContainerDepth. Returns nullopt for malformed input and for
// input that exceeds the depth limit; never throws.
//
// Rejection prevents DOM construction, not parsing: the remaining input is
// still scanned, so this is not a defense against oversized input. Bound the
// byte length separately.
std::optional<nlohmann::json> parse_bounded_json(std::string_view bytes);
std::optional<nlohmann::json> parse_bounded_json(std::istream& stream);

// True when the bytes are well-formed UTF-8, rejecting overlong encodings,
// surrogate halves, and values above U+10FFFF.
bool valid_utf8(std::string_view value);

}  // namespace lmdj::foundation
