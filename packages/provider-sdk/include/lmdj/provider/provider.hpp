#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <span>
#include <string>
#include <vector>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>
#include <lmdj/provider/capability.hpp>

namespace lmdj::provider {

// Shared across executions by the ingress owner. Reservations, including those
// retained by input handles, outlive an execute call and remain charged.
class StagingBudget {
 public:
  explicit StagingBudget(std::uint64_t maximum_bytes);
  foundation::Result<std::shared_ptr<void>> reserve(std::uint64_t bytes) const;
  std::uint64_t used_bytes() const;
 private:
  struct State;
  std::shared_ptr<State> state_;
};

class ArtifactBytes {
 public:
  ArtifactBytes(foundation::ArtifactRef reference, std::vector<std::byte> bytes,
                std::shared_ptr<void> lease);
  ArtifactBytes(const ArtifactBytes&) = delete;
  ArtifactBytes& operator=(const ArtifactBytes&) = delete;
  const foundation::ArtifactRef& reference() const { return reference_; }
  std::span<const std::byte> bytes() const { return bytes_; }
 private:
  foundation::ArtifactRef reference_;
  std::shared_ptr<void> lease_;
  std::vector<std::byte> bytes_;
};

using ArtifactHandle = std::shared_ptr<const ArtifactBytes>;
using ArtifactSource = std::function<foundation::Result<ArtifactHandle>(
    std::string port, std::size_t occurrence)>;

using ArtifactSink =
    std::function<foundation::Result<foundation::ArtifactRef>(
        std::string port,
        std::span<const std::byte> bytes,
        std::string media_type)>;

struct ProviderRunContext {
  foundation::AttemptId attempt_id;
  std::shared_ptr<const CapabilityRequest> request;
  ArtifactSource source;
  ArtifactSink output;
};

class Provider {
 public:
  virtual ~Provider() = default;
  virtual std::string id() const = 0;
  virtual std::vector<std::string> capabilities() const = 0;
  virtual AttemptResult run(ProviderRunContext context) = 0;
};

}  // namespace lmdj::provider
