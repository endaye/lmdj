#include <lmdj/provider/registry.hpp>

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <set>
#include <string_view>
#include <utility>

namespace lmdj::provider {
namespace {

using foundation::Error;
using foundation::ErrorCode;

Error invalid_registration(std::string message) {
  return Error{
      ErrorCode::invalid_argument,
      std::move(message),
  };
}

bool valid_token(std::string_view value) {
  return !value.empty() &&
         std::all_of(
             value.begin(), value.end(), [](unsigned char character) {
               return std::isalnum(character) != 0 ||
                      character == '.' || character == '_' ||
                      character == '-';
             });
}

bool valid_contract_id(std::string_view value) {
  if (value.find('.') == std::string_view::npos) {
    return false;
  }
  std::size_t start = 0;
  while (start < value.size()) {
    const auto separator = value.find('.', start);
    const auto end =
        separator == std::string_view::npos ? value.size() : separator;
    const auto segment = value.substr(start, end - start);
    if (segment.empty() ||
        segment.front() < 'a' || segment.front() > 'z' ||
        !std::all_of(
            segment.begin() + 1,
            segment.end(),
            [](unsigned char character) {
              return (character >= 'a' && character <= 'z') ||
                     (character >= '0' && character <= '9') ||
                     character == '-';
            })) {
      return false;
    }
    if (separator == std::string_view::npos) {
      return true;
    }
    start = separator + 1;
  }
  return false;
}

bool valid_port_name(std::string_view value) {
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

bool valid_sha256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(
             value.begin(), value.end(), [](unsigned char character) {
               return (character >= '0' && character <= '9') ||
                      (character >= 'a' && character <= 'f');
             });
}

bool valid_semver(std::string_view value) {
  std::size_t component_start = 0;
  int components = 0;
  while (component_start <= value.size()) {
    const auto separator = value.find('.', component_start);
    const auto component_end =
        separator == std::string_view::npos ? value.size() : separator;
    if (component_end == component_start ||
        (component_end - component_start > 1 &&
         value.at(component_start) == '0') ||
        !std::all_of(
            value.begin() + static_cast<std::ptrdiff_t>(component_start),
            value.begin() + static_cast<std::ptrdiff_t>(component_end),
            [](unsigned char character) {
              return std::isdigit(character) != 0;
            })) {
      return false;
    }
    ++components;
    if (separator == std::string_view::npos) {
      break;
    }
    component_start = separator + 1;
  }
  return components == 3;
}

bool unique_nonempty(std::vector<std::string> values) {
  if (std::any_of(values.begin(), values.end(), [](const auto& value) {
        return value.empty();
      })) {
    return false;
  }
  std::sort(values.begin(), values.end());
  return std::adjacent_find(values.begin(), values.end()) == values.end();
}

void normalize_strings(std::vector<std::string>& values) {
  std::sort(values.begin(), values.end());
}

void normalize_ports(std::vector<ArtifactPortDescriptor>& ports) {
  for (auto& port : ports) {
    normalize_strings(port.media_types);
  }
  std::sort(
      ports.begin(), ports.end(), [](const auto& left, const auto& right) {
        return left.name < right.name;
      });
}

bool valid_ports(
    const std::vector<ArtifactPortDescriptor>& ports) {
  std::set<std::string> names;
  for (const auto& port : ports) {
    if (!valid_port_name(port.name) || port.media_types.empty() ||
        !unique_nonempty(port.media_types) ||
        !valid_contract_id(port.schema_id) ||
        !valid_semver(port.schema_version) ||
        port.max_count == 0 ||
        !names.insert(port.name).second) {
      return false;
    }
  }
  return true;
}

void normalize_capability(CapabilityDescriptor& capability) {
  normalize_ports(capability.input_artifacts);
  normalize_ports(capability.output_artifacts);
  normalize_strings(capability.progress_events);
  normalize_strings(capability.error_codes);
  normalize_strings(capability.policy.data_classifications);
  normalize_strings(capability.platforms);
  normalize_strings(capability.policy.regions);
  normalize_strings(capability.policy.required_permissions);
}

bool valid_capability(const CapabilityDescriptor& capability) {
  static const std::set<std::string> error_codes{
      "INVALID_ARGUMENT",
      "NOT_FOUND",
      "REVISION_CONFLICT",
      "DUPLICATE_ID",
      "UNSUPPORTED_AUDIO",
      "MISSING_ASSET",
      "INVALID_PROJECT",
      "COOK_FAILED",
      "PROVIDER_NOT_FOUND",
      "PROVIDER_FAILED",
      "PERMISSION_DENIED",
      "IO_ERROR",
      "INTERNAL_ERROR",
  };
  return valid_contract_id(capability.id) &&
         valid_semver(capability.contract_version) &&
         valid_ports(capability.input_artifacts) &&
         !capability.output_artifacts.empty() &&
         valid_ports(capability.output_artifacts) &&
         unique_nonempty(capability.progress_events) &&
         unique_nonempty(capability.error_codes) &&
         std::all_of(
             capability.error_codes.begin(),
             capability.error_codes.end(),
             [](const auto& code) {
               return error_codes.contains(code);
             }) &&
         capability.execution.timeout_ms > 0 &&
         capability.execution.max_attempts > 0 &&
         unique_nonempty(capability.policy.data_classifications) &&
         !capability.platforms.empty() &&
         unique_nonempty(capability.platforms) &&
         unique_nonempty(capability.policy.regions) &&
         unique_nonempty(capability.policy.required_permissions);
}

}  // namespace

foundation::Result<void> Registry::add(
    ProviderRegistration registration) {
  if (!registration.implementation) {
    return foundation::Result<void>::failure(
        invalid_registration("provider implementation is required"));
  }
  const auto provider_id = registration.implementation->id();
  if (!valid_token(provider_id) || !valid_semver(registration.version) ||
      !valid_sha256(registration.artifact_sha256) ||
      (registration.model_identity.has_value() &&
       (!valid_token(registration.model_identity->id) ||
        registration.model_identity->version.empty() ||
        !valid_sha256(
            registration.model_identity->artifact_sha256))) ||
      registration.capabilities.empty()) {
    return foundation::Result<void>::failure(
        invalid_registration("provider registration metadata is invalid"));
  }
  if (providers_.contains(provider_id)) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::duplicate_id,
            "provider id is already registered",
            {{"provider_id", provider_id}},
        });
  }

  std::set<std::string> descriptor_ids;
  for (auto& capability : registration.capabilities) {
    normalize_capability(capability);
    if (!valid_capability(capability) ||
        !descriptor_ids.insert(capability.id).second) {
      return foundation::Result<void>::failure(
          invalid_registration("provider capability descriptor is invalid"));
    }
  }
  std::sort(
      registration.capabilities.begin(),
      registration.capabilities.end(),
      [](const auto& left, const auto& right) {
        return left.id < right.id;
      });

  auto implementation_capabilities =
      registration.implementation->capabilities();
  if (!unique_nonempty(implementation_capabilities)) {
    return foundation::Result<void>::failure(
        invalid_registration("provider capabilities are invalid"));
  }
  normalize_strings(implementation_capabilities);
  std::vector<std::string> registered_capabilities;
  registered_capabilities.reserve(registration.capabilities.size());
  for (const auto& capability : registration.capabilities) {
    registered_capabilities.push_back(capability.id);
  }
  if (implementation_capabilities != registered_capabilities) {
    return foundation::Result<void>::failure(
        invalid_registration(
            "provider implementation and descriptors disagree"));
  }

  auto descriptor = ProviderDescriptor{
      provider_id,
      std::move(registration.version),
      std::move(registration.artifact_sha256),
      std::move(registration.model_identity),
      std::move(registration.capabilities),
  };
  providers_.emplace(
      provider_id,
      ProviderEntry{
          std::move(descriptor),
          std::move(registration.implementation),
      });
  return foundation::Result<void>::success();
}

std::vector<ProviderDescriptor> Registry::list() const {
  std::vector<ProviderDescriptor> result;
  result.reserve(providers_.size());
  for (const auto& [provider_id, entry] : providers_) {
    static_cast<void>(provider_id);
    result.push_back(entry.descriptor);
  }
  return result;
}

foundation::Result<ProviderEntry> Registry::select(
    const std::string& provider_id,
    const std::string& capability) const {
  const auto provider = providers_.find(provider_id);
  if (provider == providers_.end()) {
    return foundation::Result<ProviderEntry>::failure(
        Error{
            ErrorCode::provider_not_found,
            "provider is not registered",
            {{"provider_id", provider_id}},
        });
  }
  const auto supported = std::find_if(
      provider->second.descriptor.capabilities.begin(),
      provider->second.descriptor.capabilities.end(),
      [&capability](const auto& descriptor) {
        return descriptor.id == capability;
      });
  if (supported == provider->second.descriptor.capabilities.end()) {
    return foundation::Result<ProviderEntry>::failure(
        Error{
            ErrorCode::invalid_argument,
            "provider does not implement requested capability",
            {
                {"provider_id", provider_id},
                {"capability", capability},
            },
        });
  }
  return foundation::Result<ProviderEntry>::success(provider->second);
}

}  // namespace lmdj::provider
