#include <lmdj/facade/assembly_loader.hpp>

#include <utility>

#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>

namespace {

lmdj::facade::CompiledAssemblyCatalog lmdj_catalog() {
  using lmdj::facade::CompiledComponent;
  using lmdj::facade::CompiledProvider;
  return lmdj::facade::CompiledAssemblyCatalog{
      "lmdj",
      "1.0.13.0",
      "17cc4b06a4e074448a6cdfb3177f4564134197a45eb5affc6b8697909b934ae4",
      {
          CompiledComponent{"foundation", "0.2.0"},
          CompiledComponent{"authoring-domain", "0.1.1"},
          CompiledComponent{"project-io", "0.3.1"},
          CompiledComponent{"project-cooker", "0.2.1"},
          CompiledComponent{"audio-runtime", "0.3.1"},
          CompiledComponent{"provider-sdk", "1.1.1"},
          CompiledComponent{"application-facade", "1.1.2"},
      },
      {
          CompiledComponent{"core-cli", "1.0.4"},
          CompiledComponent{"core-mcp", "1.1.1"},
          CompiledComponent{"native-test-host", "1.0.2"},
      },
      {
          CompiledComponent{"lmdj.project.v1", "1.0.0"},
          CompiledComponent{"lmdj.capability.v2", "2.0.0"},
          CompiledComponent{"lmdj.assembly.v2", "2.0.0"},
          CompiledComponent{"lmdj.error.v1", "1.0.0"},
          CompiledComponent{"lmdj.module.v1", "1.0.0"},
          CompiledComponent{"lmdj.product-version.v1", "1.0.0"},
      },
      {
          CompiledProvider{
              "local.proof.success",
              "1.0.2",
              lmdj::providers::local_proof_success_registration,
              std::nullopt,
          },
          CompiledProvider{
              "local.proof.failure",
              "1.0.2",
              lmdj::providers::local_proof_failure_registration,
              std::nullopt,
          },
      },
  };
}

struct ProductAssemblyInstaller {
  ProductAssemblyInstaller() {
    lmdj::facade::install_compiled_assembly_catalog(lmdj_catalog());
  }
};

ProductAssemblyInstaller installer;

}  // namespace
