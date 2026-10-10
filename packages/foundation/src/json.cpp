#include <lmdj/foundation/json.hpp>

#include <cstddef>
#include <cstdint>
#include <functional>

namespace lmdj::foundation {
namespace {

struct JsonDepthLimitExceeded {};

// Stops parsing at any container opened at or beyond the depth limit. nlohmann
// reports the depth as the container stack size before the push, so the
// outermost container is depth 0 and the limit admits exactly
// kMaximumJsonContainerDepth nested containers.
class DepthGuard {
 public:
  bool operator()(
      int depth,
      nlohmann::json::parse_event_t event,
      nlohmann::json&) {
    const bool container_start =
        event == nlohmann::json::parse_event_t::object_start ||
        event == nlohmann::json::parse_event_t::array_start;
    if (container_start && depth >= kMaximumJsonContainerDepth) {
      // Returning false only discards the container; it still scans the rest.
      // Both public overloads contain this private refusal signal.
      throw JsonDepthLimitExceeded{};
    }
    return true;
  }
};

nlohmann::json canonicalize(const nlohmann::json& value) {
  if (value.is_object()) {
    auto object = nlohmann::json::object();
    for (auto iterator = value.cbegin(); iterator != value.cend(); ++iterator) {
      object[iterator.key()] = canonicalize(iterator.value());
    }
    return object;
  }
  if (value.is_array()) {
    auto array = nlohmann::json::array();
    for (const auto& item : value) {
      array.push_back(canonicalize(item));
    }
    return array;
  }
  return value;
}

}  // namespace

std::string canonical_json(const nlohmann::json& value) {
  return canonicalize(value).dump();
}

std::optional<nlohmann::json> parse_bounded_json(std::string_view bytes) {
  try {
    DepthGuard guard;
    auto value = nlohmann::json::parse(
        bytes.begin(), bytes.end(), std::ref(guard), false);
    if (value.is_discarded()) {
      return std::nullopt;
    }
    return value;
  } catch (const JsonDepthLimitExceeded&) {
    return std::nullopt;
  }
}

std::optional<nlohmann::json> parse_bounded_json(std::istream& stream) {
  try {
    DepthGuard guard;
    auto value = nlohmann::json::parse(stream, std::ref(guard), false);
    if (value.is_discarded()) {
      return std::nullopt;
    }
    return value;
  } catch (const JsonDepthLimitExceeded&) {
    return std::nullopt;
  }
}

bool valid_utf8(std::string_view value) {
  std::size_t offset = 0;
  while (offset < value.size()) {
    const auto first = static_cast<unsigned char>(value[offset]);
    if (first <= 0x7fU) {
      ++offset;
      continue;
    }
    std::size_t length = 0;
    std::uint32_t code_point = 0;
    if (first >= 0xc2U && first <= 0xdfU) {
      length = 2;
      code_point = first & 0x1fU;
    } else if (first >= 0xe0U && first <= 0xefU) {
      length = 3;
      code_point = first & 0x0fU;
    } else if (first >= 0xf0U && first <= 0xf4U) {
      length = 4;
      code_point = first & 0x07U;
    } else {
      return false;
    }
    if (offset + length > value.size()) {
      return false;
    }
    for (std::size_t index = 1; index < length; ++index) {
      const auto byte =
          static_cast<unsigned char>(value[offset + index]);
      if ((byte & 0xc0U) != 0x80U) {
        return false;
      }
      code_point = (code_point << 6U) | (byte & 0x3fU);
    }
    if ((length == 3 && code_point < 0x800U) ||
        (length == 4 && code_point < 0x10000U) ||
        code_point > 0x10ffffU ||
        (code_point >= 0xd800U && code_point <= 0xdfffU)) {
      return false;
    }
    offset += length;
  }
  return true;
}

}  // namespace lmdj::foundation
