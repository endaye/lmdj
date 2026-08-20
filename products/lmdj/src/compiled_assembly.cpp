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
      "1.0.24.0",
      "17cc4b06a4e074448a6cdfb3177f4564134197a45eb5affc6b8697909b934ae4",
      {
          CompiledComponent{"foundation", "0.2.0"},
          CompiledComponent{"authoring-domain", "0.2.0"},
          CompiledComponent{"project-io", "0.6.0"},
          CompiledComponent{"project-cooker", "0.3.0"},
          CompiledComponent{"audio-runtime", "0.5.0"},
          CompiledComponent{"provider-sdk", "1.1.2"},
          CompiledComponent{"application-facade", "1.4.1"},
          CompiledComponent{"web-runtime-platform", "0.3.1"},
      },
      {
          CompiledComponent{"core-cli", "1.0.13"},
          CompiledComponent{"core-mcp", "1.1.10"},
          CompiledComponent{"native-test-host", "1.0.11"},
          CompiledComponent{"web-runtime-host", "1.2.10"},
          CompiledComponent{"creator-web", "1.3.1"},
      },
      {
          CompiledComponent{"lmdj.project.v1", "1.0.0"},
          CompiledComponent{"lmdj.project.v2", "2.0.0"},
          CompiledComponent{"lmdj.project-bundle.v1", "1.0.0"},
          CompiledComponent{"lmdj.capability.v2", "2.0.0"},
          CompiledComponent{"lmdj.assembly.v2", "2.0.0"},
          CompiledComponent{"lmdj.error.v1", "1.0.0"},
          CompiledComponent{"lmdj.module.v1", "1.0.0"},
          CompiledComponent{"lmdj.product-version.v1", "1.0.0"},
      },
      {
          CompiledProvider{
              "local.proof.success",
              "1.0.3",
              lmdj::providers::local_proof_success_registration,
              std::nullopt,
          },
          CompiledProvider{
              "local.proof.failure",
              "1.0.3",
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
