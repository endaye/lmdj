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

struct ProviderRegistration {
  std::shared_ptr<Provider> implementation;
  std::string version;
  // In this Proof, this identifies the reproducible Provider source-package
  // manifest compiled into its factory. It is not a binary hash.
  std::string artifact_sha256;
  std::optional<ModelIdentity> model_identity;
  std::vector<CapabilityDescriptor> capabilities;
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
