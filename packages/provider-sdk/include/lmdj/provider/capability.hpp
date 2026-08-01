#pragma once

#include <compare>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::provider {

enum class Determinism {
  deterministic,
  seeded,
  nondeterministic,
};

enum class ResourceClass {
  light,
  cpu,
  gpu,
  remote,
};

struct ArtifactPortDescriptor {
  std::string name;
  std::vector<std::string> media_types;
  std::string schema_id;
  std::string schema_version;
  bool required;
  std::uint32_t max_count;

  auto operator<=>(const ArtifactPortDescriptor&) const = default;
};

struct ResourceRequirements {
  ResourceClass resource_class;
  std::optional<std::uint64_t> memory_mib;

  auto operator<=>(const ResourceRequirements&) const = default;
};

struct ExecutionPolicy {
  std::uint32_t timeout_ms;
  std::uint32_t max_attempts;

  auto operator<=>(const ExecutionPolicy&) const = default;
};

struct CapabilityPolicy {
  std::vector<std::string> data_classifications;
  std::vector<std::string> regions;
  std::vector<std::string> required_permissions;

  auto operator<=>(const CapabilityPolicy&) const = default;
};

struct CapabilityDescriptor {
  std::string id;
  std::string contract_version;
  std::vector<ArtifactPortDescriptor> input_artifacts;
  std::vector<ArtifactPortDescriptor> output_artifacts;
  Determinism determinism;
  std::vector<std::string> progress_events;
  std::vector<std::string> error_codes;
  ResourceRequirements resources;
  ExecutionPolicy execution;
  CapabilityPolicy policy;
  std::vector<std::string> platforms;
  std::uint64_t max_output_bytes;

  auto operator<=>(const CapabilityDescriptor&) const = default;
};

nlohmann::json capability_contract_json(
    const CapabilityDescriptor& capability);
std::string canonical_capability_json(
    const CapabilityDescriptor& capability);

struct ArtifactBinding {
  std::string port;
  foundation::ArtifactRef artifact;

  auto operator<=>(const ArtifactBinding&) const = default;
};

void to_json(nlohmann::json& output, const ArtifactBinding& binding);
void from_json(const nlohmann::json& input, ArtifactBinding& binding);

struct CapabilityRequest {
  std::string capability;
  std::vector<ArtifactBinding> inputs;
  nlohmann::json parameters;
  std::string data_classification;
  std::string platform;
  std::string region;
  std::vector<std::string> required_permissions;
};

struct Candidate {
  foundation::CandidateId id;
  std::vector<ArtifactBinding> outputs;
  nlohmann::json provenance;
};

struct AttemptResult {
  foundation::AttemptId attempt_id;
  std::optional<Candidate> candidate;
  std::optional<foundation::Error> error;
};

}  // namespace lmdj::provider
