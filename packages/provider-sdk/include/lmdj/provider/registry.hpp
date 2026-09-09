#pragma once

#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>

namespace lmdj::provider {

struct ModelIdentity {
  std::string id;
  std::string version;
  std::string artifact_sha256;

  bool operator==(const ModelIdentity&) const = default;
};

struct ValidatedInput {
  ArtifactBinding binding;
  ArtifactHandle handle;
};

using OutputValidator = std::function<foundation::Result<void>(
    const CapabilityRequest&, std::span<const ValidatedInput>,
    const ArtifactBinding&, std::span<const std::byte>, std::span<std::byte>)>;

// Every output port, including opaque Proof ports, declares a validation policy.
// Scratch is reserved by execution before invoking consumer code.
struct OutputValidation {
  std::string capability;
  std::string port;
  OutputValidator validate;
  std::uint64_t scratch_bytes;
};

struct DomainErrorValidation {
  std::string capability;
  foundation::ErrorCode code;
  std::string reason;
};

struct ProviderRegistration {
  std::shared_ptr<Provider> implementation;
  std::string version;
  // In this Proof, this identifies the reproducible Provider source-package
  // manifest compiled into its factory. It is not a binary hash.
  std::string artifact_sha256;
  std::optional<ModelIdentity> model_identity;
  std::vector<CapabilityDescriptor> capabilities;
  std::vector<OutputValidation> output_validation;
  std::vector<DomainErrorValidation> domain_errors;
};

struct ProviderDescriptor {
  std::string id;
  std::string version;
  // Same source-package identity supplied by ProviderRegistration.
  std::string artifact_sha256;
  std::optional<ModelIdentity> model_identity;
  std::vector<CapabilityDescriptor> capabilities;
};

struct ProviderEntry {
  ProviderDescriptor descriptor;
  std::shared_ptr<Provider> implementation;
  std::vector<OutputValidation> output_validation;
  std::vector<DomainErrorValidation> domain_errors;
};

class Registry {
 public:
  foundation::Result<void> add(ProviderRegistration registration);
  std::vector<ProviderDescriptor> list() const;
  foundation::Result<ProviderEntry> select(
      const std::string& provider_id,
      const std::string& capability) const;

 private:
  std::map<std::string, ProviderEntry> providers_;
};

}  // namespace lmdj::provider
