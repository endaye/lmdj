#pragma once

#include <string>

#include <nlohmann/json.hpp>

namespace lmdj::foundation {

std::string canonical_json(const nlohmann::json& value);

}  // namespace lmdj::foundation
