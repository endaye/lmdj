#include <lmdj/provider/capability.hpp>

#include <algorithm>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <lmdj/foundation/json.hpp>

namespace lmdj::provider {
namespace {

std::string_view determinism_name(Determinism determinism) {
  switch (determinism) {
    case Determinism::deterministic:
      return "deterministic";
    case Determinism::seeded:
      return "seeded";
    case Determinism::nondeterministic:
      return "nondeterministic";
  }
  return "nondeterministic";
}

std::string_view resource_class_name(ResourceClass resource_class) {
  switch (resource_class) {
    case ResourceClass::light:
      return "light";
    case ResourceClass::cpu:
      return "cpu";
    case ResourceClass::gpu:
      return "gpu";
    case ResourceClass::remote:
      return "remote";
  }
  return "remote";
}

std::vector<std::string> sorted_strings(
    std::vector<std::string> values) {
  std::sort(values.begin(), values.end());
  return values;
}

nlohmann::json port_json(ArtifactPortDescriptor port) {
  std::sort(port.media_types.begin(), port.media_types.end());
  return {
      {"media_types", std::move(port.media_types)},
      {"max_count", port.max_count},
      {"name", std::move(port.name)},
      {"required", port.required},
      {"schema_id", std::move(port.schema_id)},
      {"schema_version", std::move(port.schema_version)},
  };
}

nlohmann::json ports_json(
    std::vector<ArtifactPortDescriptor> ports) {
  std::sort(
      ports.begin(), ports.end(), [](const auto& left, const auto& right) {
        return left.name < right.name;
      });
  auto encoded = nlohmann::json::array();
  for (auto& port : ports) {
    encoded.push_back(port_json(std::move(port)));
  }
  return encoded;
}

}  // namespace

nlohmann::json capability_contract_json(
    const CapabilityDescriptor& capability) {
  auto resources = nlohmann::json{
      {"class", resource_class_name(capability.resources.resource_class)},
  };
  if (capability.resources.memory_mib.has_value()) {
    resources["memory_mib"] = *capability.resources.memory_mib;
  }
  return {
      {"capability_id", capability.id},
      {"contract", "lmdj.capability.v2"},
      {"contract_version", capability.contract_version},
      {"determinism", determinism_name(capability.determinism)},
      {"errors", sorted_strings(capability.error_codes)},
      {"execution",
       {
           {"max_attempts", capability.execution.max_attempts},
           {"timeout_ms", capability.execution.timeout_ms},
       }},
      {"input_artifacts", ports_json(capability.input_artifacts)},
      {"output_artifacts", ports_json(capability.output_artifacts)},
      {"policy",
       {
           {"data_classifications",
            sorted_strings(capability.policy.data_classifications)},
           {"regions", sorted_strings(capability.policy.regions)},
           {"required_permissions",
            sorted_strings(capability.policy.required_permissions)},
       }},
      {"progress_events", sorted_strings(capability.progress_events)},
      {"resources", std::move(resources)},
  };
}

bool valid_port_name(std::string_view value) noexcept {
  return !value.empty() &&
         value.front() >= 'a' && value.front() <= 'z' &&
         std::all_of(
             value.begin() + 1,
             value.end(),
             [](unsigned char character) {
               return (character >= 'a' && character <= 'z') ||
                      (character >= '0' && character <= '9') ||
                      character == '_';
             });
}

void to_json(nlohmann::json& output, const ArtifactBinding& binding) {
  output = {
      {"artifact", binding.artifact},
      {"port", binding.port},
  };
}

void from_json(const nlohmann::json& input, ArtifactBinding& binding) {
  input.at("port").get_to(binding.port);
  input.at("artifact").get_to(binding.artifact);
}

std::string canonical_capability_json(
    const CapabilityDescriptor& capability) {
  return foundation::canonical_json(
      capability_contract_json(capability));
}

}  // namespace lmdj::provider
