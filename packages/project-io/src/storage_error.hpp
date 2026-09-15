#pragma once

#include <string>
#include <utility>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/error.hpp>

namespace lmdj::project_io::detail {

// A storage refusal keeps its code and its storage_condition, and gains a
// message naming the step that refused: quota exhaustion, a torn publication,
// a lease collision and a mount failure must not reach a log as one shapeless
// IO_ERROR. No new details vocabulary is minted; the Facade forwards only the
// Contract-locked code and reason.
inline foundation::Error sanitized_storage_error(
    const foundation::Error& source,
    std::string message) {
  auto details = nlohmann::json::object();
  if (source.details.is_object() &&
      source.details.contains("storage_condition")) {
    details["storage_condition"] = source.details.at("storage_condition");
  }
  return foundation::Error{source.code, std::move(message), std::move(details)};
}

}  // namespace lmdj::project_io::detail
