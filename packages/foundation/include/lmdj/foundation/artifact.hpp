#pragma once

#include <compare>
#include <cstdint>
#include <filesystem>
#include <string>

#include <lmdj/foundation/error.hpp>

namespace lmdj::foundation {

struct ArtifactRef {
  std::string sha256;
  std::string media_type;
  std::uint64_t byte_length;

  auto operator<=>(const ArtifactRef&) const = default;
};

void to_json(nlohmann::json& output, const ArtifactRef& artifact);
void from_json(const nlohmann::json& input, ArtifactRef& artifact);

Result<ArtifactRef> describe_artifact(
    const std::filesystem::path& path,
    std::string media_type);

}  // namespace lmdj::foundation
