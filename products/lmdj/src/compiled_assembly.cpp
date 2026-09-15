#include <lmdj/facade/assembly_loader.hpp>

#include <utility>

#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>
#include <lmdj/providers/local_sample_slice/factory.hpp>

namespace {

lmdj::facade::CompiledAssemblyCatalog lmdj_catalog() {
  using lmdj::facade::CompiledComponent;
  using lmdj::facade::CompiledProvider;
  return lmdj::facade::CompiledAssemblyCatalog{
      "lmdj",
      "1.0.57.0",
      "17cc4b06a4e074448a6cdfb3177f4564134197a45eb5affc6b8697909b934ae4",
      {
          CompiledComponent{"foundation", "0.4.0"},
          CompiledComponent{"authoring-domain", "4.1.0"},
          CompiledComponent{"project-io", "4.1.0"},
          CompiledComponent{"project-cooker", "1.2.0"},
          CompiledComponent{"audio-runtime", "5.0.0"},
          CompiledComponent{"provider-sdk", "2.2.0"},
          CompiledComponent{"application-facade", "6.0.0"},
          CompiledComponent{"web-runtime-platform", "5.3.0"},
      },
      {
          CompiledComponent{"core-cli", "3.3.5"},
          CompiledComponent{"core-mcp", "3.4.0"},
          CompiledComponent{"native-host", "3.4.0"},
          CompiledComponent{"cardputer-host", "1.0.0"},
          CompiledComponent{"web-runtime-host", "4.3.0"},
          CompiledComponent{"creator-web", "4.3.0"},
      },
      {
          CompiledComponent{"lmdj.project.v5", "5.0.0"},
          CompiledComponent{"lmdj.project-bundle.v1", "2.0.0"},
          CompiledComponent{"lmdj.soundset.v1", "1.1.0"},
          CompiledComponent{"lmdj.soundset-catalog.v1", "1.0.0"},
          CompiledComponent{"lmdj.capability.v2", "2.0.0"},
          CompiledComponent{"lmdj.assembly.v2", "2.0.0"},
          CompiledComponent{"lmdj.error.v1", "1.1.0"},
          CompiledComponent{"lmdj.module.v1", "1.0.0"},
          CompiledComponent{"lmdj.product-version.v1", "1.0.0"},
          CompiledComponent{"lmdj.audio.pcm16-wav.v1", "1.0.0"},
          CompiledComponent{"lmdj.slice-points.v1", "1.0.0"},
          CompiledComponent{"lmdj.cardputer-transfer.v1", "1.0.0"},
      },
      {
          CompiledProvider{
              "local.proof.success",
              "2.0.2",
              lmdj::providers::local_proof_success_registration,
              std::nullopt,
          },
          CompiledProvider{
              "local.proof.failure",
              "2.0.2",
              lmdj::providers::local_proof_failure_registration,
              std::nullopt,
          },
          CompiledProvider{
              "local.sample.slice",
              "1.0.2",
              lmdj::providers::local_sample_slice_registration,
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
