#include <lmdj/facade/assembly_loader.hpp>

#include <algorithm>
#include <fstream>
#include <initializer_list>
#include <map>
#include <mutex>
#include <optional>
#include <regex>
#include <set>
#include <string>
#include <string_view>
#include <utility>

#include <nlohmann/json.hpp>

namespace lmdj::facade {
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::uintmax_t kMaximumAssemblyBytes = 4U * 1024U * 1024U;

std::mutex installed_catalog_mutex;
std::optional<CompiledAssemblyCatalog> installed_catalog;

foundation::Result<LoadedAssembly> failure(std::string message) {
  return foundation::Result<LoadedAssembly>::failure(
      Error{ErrorCode::invalid_argument, std::move(message)});
}

bool normalized_absolute(const std::filesystem::path& path) {
  return path.is_absolute() && path.lexically_normal() == path;
}

std::optional<nlohmann::json> read_object(
    const std::filesystem::path& path) {
  std::error_code error;
  if (!normalized_absolute(path) || !std::filesystem::is_regular_file(path, error) ||
      error || std::filesystem::is_symlink(path, error) || error) {
    return std::nullopt;
  }
  const auto size = std::filesystem::file_size(path, error);
  if (error || size > kMaximumAssemblyBytes) {
    return std::nullopt;
  }
  std::ifstream input(path, std::ios::binary);
  if (!input.good()) {
    return std::nullopt;
  }
  auto value = nlohmann::json::parse(input, nullptr, false);
  if (value.is_discarded() || !value.is_object()) {
    return std::nullopt;
  }
  return value;
}

bool exact_keys(
    const nlohmann::json& value,
    std::initializer_list<std::string_view> expected) {
  if (!value.is_object() || value.size() != expected.size()) {
    return false;
  }
  return std::all_of(expected.begin(), expected.end(), [&](auto key) {
    return value.contains(std::string(key));
  });
}

bool valid_id(const std::string& value) {
  static const std::regex pattern(
      R"(^[a-z][a-z0-9]*(\.[a-z0-9-]+|-[a-z0-9-]+)*$)");
  return std::regex_match(value, pattern);
}

bool valid_semver(const std::string& value) {
  static const std::regex pattern(
      R"(^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$)");
  return std::regex_match(value, pattern);
}

bool valid_product_version(const std::string& value) {
  static const std::regex pattern(
      R"(^[1-9][0-9]*\.[0-9]+\.[0-9]+\.[0-9]+$)");
  return std::regex_match(value, pattern);
}

bool valid_sha256(const std::string& value) {
  static const std::regex pattern(R"(^[0-9a-f]{64}$)");
  return std::regex_match(value, pattern);
}

bool valid_versioned_component(const nlohmann::json& value) {
  return exact_keys(value, {"id", "version"}) &&
         value.at("id").is_string() && value.at("version").is_string() &&
         valid_id(value.at("id").get<std::string>()) &&
         valid_semver(value.at("version").get<std::string>());
}

bool valid_model_identity(const nlohmann::json& value) {
  if (value.is_null()) {
    return true;
  }
  if (!exact_keys(value, {"id", "version", "artifact_sha256"}) ||
      !value.at("id").is_string() || !value.at("version").is_string() ||
      !value.at("artifact_sha256").is_string()) {
    return false;
  }
  return valid_id(value.at("id").get<std::string>()) &&
         !value.at("version").get_ref<const std::string&>().empty() &&
         valid_sha256(
             value.at("artifact_sha256").get<std::string>());
}

bool valid_provider(const nlohmann::json& value) {
  if (!exact_keys(
          value,
          {"id", "version", "capabilities", "model_identity"}) ||
      !value.at("id").is_string() || !value.at("version").is_string() ||
      !value.at("capabilities").is_array() ||
      !valid_model_identity(value.at("model_identity")) ||
      !valid_id(value.at("id").get<std::string>()) ||
      !valid_semver(value.at("version").get<std::string>())) {
    return false;
  }
  std::set<std::pair<std::string, std::string>> capabilities;
  for (const auto& capability : value.at("capabilities")) {
    if (!valid_versioned_component(capability) ||
        !capabilities
             .emplace(
                 capability.at("id").get<std::string>(),
                 capability.at("version").get<std::string>())
             .second) {
      return false;
    }
  }
  return true;
}

bool schema_identity(const nlohmann::json& schema) {
  if (!schema.contains("$id") || !schema.at("$id").is_string() ||
      !schema.contains("x-lmdj-contract-version") ||
      schema.at("x-lmdj-contract-version") != "2.0.0" ||
      schema.value("type", "") != "object" ||
      schema.value("additionalProperties", true) ||
      !schema.contains("properties") ||
      !schema.at("properties").is_object() ||
      !schema.at("properties").contains("contract")) {
    return false;
  }
  const auto& contract = schema.at("properties").at("contract");
  return contract.is_object() &&
         contract.value("const", "") == "lmdj.assembly.v2" &&
         schema.at("$id")
             .get_ref<const std::string&>()
             .ends_with("lmdj.assembly.v2.schema.json");
}

std::optional<std::vector<std::string>> policy_values(
    const nlohmann::json& value) {
  if (!value.is_array()) {
    return std::nullopt;
  }
  std::vector<std::string> values;
  std::set<std::string> unique;
  for (const auto& member : value) {
    if (!member.is_string()) {
      return std::nullopt;
    }
    auto decoded = member.get<std::string>();
    if (decoded.empty() || !unique.insert(decoded).second) {
      return std::nullopt;
    }
    values.push_back(std::move(decoded));
  }
  return values;
}

std::optional<provider::ProviderPolicy> provider_policy(
    const nlohmann::json& value) {
  if (!exact_keys(
          value,
          {"allowed_regions",
           "allowed_data_classifications",
           "granted_permissions"})) {
    return std::nullopt;
  }
  auto regions = policy_values(value.at("allowed_regions"));
  auto classifications =
      policy_values(value.at("allowed_data_classifications"));
  auto permissions = policy_values(value.at("granted_permissions"));
  if (!regions.has_value() || !classifications.has_value() ||
      !permissions.has_value()) {
    return std::nullopt;
  }
  return provider::ProviderPolicy{
      std::move(*regions),
      std::move(*classifications),
      std::move(*permissions),
  };
}

std::optional<std::map<std::string, std::string>> component_inventory(
    const nlohmann::json& value) {
  if (!value.is_array()) {
    return std::nullopt;
  }
  std::map<std::string, std::string> inventory;
  for (const auto& component : value) {
    if (!valid_versioned_component(component)) {
      return std::nullopt;
    }
    const auto inserted = inventory.emplace(
        component.at("id").get<std::string>(),
        component.at("version").get<std::string>());
    if (!inserted.second) {
      return std::nullopt;
    }
  }
  return inventory;
}

std::optional<std::map<std::string, std::string>> compiled_inventory(
    const std::vector<CompiledComponent>& components) {
  std::map<std::string, std::string> inventory;
  for (const auto& component : components) {
    if (!valid_id(component.id) || !valid_semver(component.version) ||
        !inventory.emplace(component.id, component.version).second) {
      return std::nullopt;
    }
  }
  return inventory;
}

std::optional<std::filesystem::path> locate_schema(
    const std::filesystem::path& assembly_path) {
  auto current = assembly_path.parent_path();
  for (int depth = 0; depth < 8 && !current.empty(); ++depth) {
    const auto candidate = current / "contracts" / "assembly" /
                           "lmdj.assembly.v2.schema.json";
    std::error_code error;
    if (std::filesystem::is_regular_file(candidate, error) && !error) {
      return candidate.lexically_normal();
    }
    const auto parent = current.parent_path();
    if (parent == current) {
      break;
    }
    current = parent;
  }
  return std::nullopt;
}

std::optional<std::map<std::string, CompiledProvider>> provider_catalog(
    const std::vector<CompiledProvider>& providers) {
  std::map<std::string, CompiledProvider> catalog;
  for (const auto& provider : providers) {
    if (!valid_id(provider.id) || !valid_semver(provider.version) ||
        !provider.factory ||
        (provider.model_identity.has_value() &&
         (!valid_id(provider.model_identity->id) ||
          provider.model_identity->version.empty() ||
          !valid_sha256(
              provider.model_identity->artifact_sha256))) ||
        !catalog.emplace(provider.id, provider).second) {
      return std::nullopt;
    }
  }
  return catalog;
}

bool provider_matches(
    const nlohmann::json& declared,
    const CompiledProvider& compiled,
    const provider::ProviderRegistration& registration) {
  if (!registration.implementation ||
      registration.implementation->id() != compiled.id ||
      registration.version != compiled.version ||
      declared.at("version") != compiled.version) {
    return false;
  }
  std::map<std::string, std::string> declared_capabilities;
  for (const auto& capability : declared.at("capabilities")) {
    declared_capabilities.emplace(
        capability.at("id").get<std::string>(),
        capability.at("version").get<std::string>());
  }
  std::map<std::string, std::string> compiled_capabilities;
  for (const auto& capability : registration.capabilities) {
    if (!compiled_capabilities
             .emplace(capability.id, capability.contract_version)
             .second) {
      return false;
    }
  }
  if (declared_capabilities != compiled_capabilities) {
    return false;
  }
  const auto& model = declared.at("model_identity");
  if (model.is_null()) {
    return !registration.model_identity.has_value() &&
           !compiled.model_identity.has_value();
  }
  if (!registration.model_identity.has_value() ||
      !compiled.model_identity.has_value()) {
    return false;
  }
  return model.at("id") == compiled.model_identity->id &&
         model.at("version") == compiled.model_identity->version &&
         model.at("artifact_sha256") ==
             compiled.model_identity->artifact_sha256 &&
         *registration.model_identity == *compiled.model_identity;
}

}  // namespace

foundation::Result<LoadedAssembly> load_assembly(
    const std::filesystem::path& assembly_path,
    const std::filesystem::path& schema_path,
    const CompiledAssemblyCatalog& catalog) {
  try {
    const auto schema = read_object(schema_path);
    const auto assembly = read_object(assembly_path);
    const auto described_schema = foundation::describe_artifact(
        schema_path, "application/schema+json");
    if (!schema.has_value() || !schema_identity(*schema) ||
        !described_schema.has_value() ||
        described_schema.value().sha256 != catalog.assembly_schema_sha256 ||
        !assembly.has_value() ||
        !exact_keys(
            *assembly,
            {"contract",
             "product",
             "modules",
             "hosts",
             "providers",
             "contracts",
             "provider_policy"}) ||
        assembly->at("contract") != "lmdj.assembly.v2") {
      return failure("assembly or schema is invalid");
    }
    const auto& product = assembly->at("product");
    if (!exact_keys(product, {"id", "version"}) ||
        !product.at("id").is_string() ||
        !product.at("version").is_string() ||
        !valid_id(product.at("id").get<std::string>()) ||
        !valid_product_version(product.at("version").get<std::string>()) ||
        product.at("id") != catalog.product_id ||
        product.at("version") != catalog.product_version) {
      return failure("assembly product identity is invalid");
    }

    const auto declared_modules =
        component_inventory(assembly->at("modules"));
    const auto declared_hosts = component_inventory(assembly->at("hosts"));
    const auto declared_contracts =
        component_inventory(assembly->at("contracts"));
    const auto available_modules = compiled_inventory(catalog.modules);
    const auto available_hosts = compiled_inventory(catalog.hosts);
    const auto available_contracts = compiled_inventory(catalog.contracts);
    if (!declared_modules.has_value() || !declared_hosts.has_value() ||
        !declared_contracts.has_value() ||
        !available_modules.has_value() || !available_hosts.has_value() ||
        !available_contracts.has_value() ||
        *declared_modules != *available_modules ||
        *declared_hosts != *available_hosts ||
        *declared_contracts != *available_contracts) {
      return failure("assembly component inventory is unavailable");
    }

    if (!assembly->at("providers").is_array()) {
      return failure("assembly providers must be an array");
    }
    auto effective_policy =
        provider_policy(assembly->at("provider_policy"));
    if (!effective_policy.has_value()) {
      return failure("assembly Provider policy is invalid");
    }
    const auto available_providers = provider_catalog(catalog.providers);
    if (!available_providers.has_value()) {
      return failure("compiled Provider catalog is invalid");
    }
    auto registry = std::make_shared<provider::Registry>();
    std::set<std::string> declared_provider_ids;
    for (const auto& declared : assembly->at("providers")) {
      if (!valid_provider(declared)) {
        return failure("assembly Provider declaration is invalid");
      }
      const auto provider_id = declared.at("id").get<std::string>();
      if (!declared_provider_ids.insert(provider_id).second) {
        return failure("assembly Provider IDs must be unique");
      }
      const auto found = available_providers->find(provider_id);
      if (found == available_providers->end()) {
        return failure("assembly Provider is not compiled");
      }
      auto registration = found->second.factory();
      if (!provider_matches(declared, found->second, registration)) {
        return failure("assembly Provider metadata does not match");
      }
      const auto added = registry->add(std::move(registration));
      if (!added.has_value()) {
        return failure("assembly Provider registration failed");
      }
    }
    return foundation::Result<LoadedAssembly>::success(
        LoadedAssembly{std::move(registry), std::move(*effective_policy)});
  } catch (...) {
    return failure("assembly loading failed");
  }
}

void install_compiled_assembly_catalog(CompiledAssemblyCatalog catalog) {
  std::lock_guard lock(installed_catalog_mutex);
  if (installed_catalog.has_value()) {
    throw std::logic_error("compiled Assembly catalog already installed");
  }
  installed_catalog.emplace(std::move(catalog));
}

foundation::Result<LoadedAssembly> load_installed_assembly(
    const std::filesystem::path& assembly_path) {
  const auto schema_path = locate_schema(assembly_path);
  if (!schema_path.has_value()) {
    return failure("Assembly schema could not be located");
  }
  std::lock_guard lock(installed_catalog_mutex);
  if (!installed_catalog.has_value()) {
    return failure("compiled Assembly catalog is not installed");
  }
  return load_assembly(assembly_path, *schema_path, *installed_catalog);
}

}  // namespace lmdj::facade
