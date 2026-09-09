#pragma once

#include <filesystem>
#include <functional>
#include <optional>
#include <string>
#include <vector>

#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::provider {

struct ProviderPolicy {
  std::vector<std::string> allowed_regions;
  std::vector<std::string> allowed_data_classifications;
  std::vector<std::string> granted_permissions;
};

using TimestampSource = std::function<std::string()>;

// The owner keeps its buffer stable throughout ingress. The SDK copies it;
// ownership of a const shared_ptr alone is not an immutability guarantee.
using ArtifactResolver = std::function<foundation::Result<
    std::shared_ptr<const std::vector<std::byte>>>(const foundation::ArtifactRef&)>;

struct ExecutionOptions {
  ArtifactResolver resolve_input;
  std::uint64_t maximum_input_bytes;
  std::uint64_t maximum_output_bytes;
  std::shared_ptr<StagingBudget> staging_budget;
};

// These typed values expose SDK-owned Workspace state to Hosts. Their
// persisted JSON is an implementation-private format, not a versioned
// cross-language Contract.
enum class AttemptStatus {
  succeeded,
  failed,
};

struct AttemptProviderIdentity {
  std::string id;
  std::string version;
  std::string artifact_sha256;
  std::optional<ModelIdentity> model_identity;
};

struct AttemptCapabilityIdentity {
  std::string id;
  std::string contract;
  std::string version;
};

struct AttemptRequestMetadata {
  std::string capability;
  std::vector<ArtifactBinding> inputs;
  std::string parameters_sha256;
  std::string data_classification;
  std::string platform;
  std::string region;
  std::vector<std::string> required_permissions;
};

struct TerminalAttempt {
  foundation::AttemptId attempt_id;
  AttemptStatus status;
  std::string started_at;
  std::string ended_at;
  AttemptProviderIdentity provider;
  AttemptCapabilityIdentity capability;
  AttemptRequestMetadata request;
  std::vector<foundation::CandidateId> candidate_ids;
  std::vector<ArtifactBinding> minted_outputs;
  std::vector<ArtifactBinding> candidate_outputs;
  std::vector<foundation::ArtifactRef> artifacts;
  std::optional<foundation::Error> error;
};

class AttemptStore {
 public:
  AttemptStore(
      std::filesystem::path workspace_root,
      ProviderPolicy policy,
      TimestampSource timestamp_source);

  foundation::Result<void> set_provider_selection(
      std::string capability,
      std::string provider_id,
      const Registry& registry);

  foundation::Result<std::string> selected_provider(
      const std::string& capability) const;

  foundation::Result<TerminalAttempt> inspect(
      foundation::AttemptId attempt_id) const;

  foundation::Result<AttemptResult> execute(
      foundation::AttemptId attempt_id,
      const CapabilityRequest& request,
      const Registry& registry,
      const ExecutionOptions& options);

 private:
  std::filesystem::path workspace_root_;
  ProviderPolicy policy_;
  TimestampSource timestamp_source_;
};

}  // namespace lmdj::provider
