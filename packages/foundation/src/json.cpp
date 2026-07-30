#include <lmdj/foundation/json.hpp>

namespace lmdj::foundation {
namespace {

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

}  // namespace lmdj::foundation
