#pragma once

#include <filesystem>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::facade {

struct CompiledComponent {
  std::string id;
  std::string version;
};

struct CompiledProvider {
  std::string id;
  std::string version;
  std::function<provider::ProviderRegistration()> factory;
  std::optional<provider::ModelIdentity> model_identity;
};

struct CompiledAssemblyCatalog {
  std::string product_id;
  std::string product_version;
  std::string assembly_schema_sha256;
  std::vector<CompiledComponent> modules;
  std::vector<CompiledComponent> hosts;
  std::vector<CompiledComponent> contracts;
  std::vector<CompiledProvider> providers;
};

struct LoadedAssembly {
  std::shared_ptr<provider::Registry> providers;
  provider::ProviderPolicy provider_policy;
};

foundation::Result<LoadedAssembly> load_assembly(
    const std::filesystem::path& assembly_path,
    const std::filesystem::path& schema_path,
    const CompiledAssemblyCatalog& catalog);

void install_compiled_assembly_catalog(CompiledAssemblyCatalog catalog);

foundation::Result<LoadedAssembly> load_installed_assembly(
    const std::filesystem::path& assembly_path);

}  // namespace lmdj::facade
