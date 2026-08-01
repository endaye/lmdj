#pragma once

#include <cstddef>
#include <functional>
#include <span>
#include <string>
#include <vector>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>
#include <lmdj/provider/capability.hpp>

namespace lmdj::provider {

using ArtifactSink =
    std::function<foundation::Result<foundation::ArtifactRef>(
        std::string port,
        std::span<const std::byte> bytes,
        std::string media_type)>;

class Provider {
 public:
  virtual ~Provider() = default;
  virtual std::string id() const = 0;
  virtual std::vector<std::string> capabilities() const = 0;
  virtual AttemptResult run(
      foundation::AttemptId attempt_id,
      const CapabilityRequest& request,
      ArtifactSink output) = 0;
};

}  // namespace lmdj::provider
