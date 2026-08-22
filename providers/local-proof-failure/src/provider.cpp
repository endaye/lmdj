#include <lmdj/providers/local_proof_failure/factory.hpp>

#include <memory>
#include <string>
#include <utility>
#include <vector>

#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>

namespace lmdj::providers {
namespace {

#ifndef LMDJ_LOCAL_PROOF_FAILURE_SOURCE_PACKAGE_SHA256
#error "failure Provider source-package identity is required"
#endif

class LocalProofFailureProvider final : public provider::Provider {
 public:
  std::string id() const override { return "local.proof.failure"; }

  std::vector<std::string> capabilities() const override {
    return {"proof.candidate.v2"};
  }

  provider::AttemptResult run(
      foundation::AttemptId attempt_id,
      const provider::CapabilityRequest&,
      provider::ArtifactSink) override {
    return provider::AttemptResult{
        std::move(attempt_id),
        std::nullopt,
        foundation::Error{
            foundation::ErrorCode::provider_failed,
            "intentional proof failure",
        },
    };
  }
};

provider::CapabilityDescriptor proof_capability() {
  return provider::CapabilityDescriptor{
      "proof.candidate.v2",
      "2.0.0",
      {{
          "inputs",
          {"*/*"},
          "lmdj.artifact.input.v1",
          "1.0.0",
          false,
          64,
      }},
      {{
          "candidate",
          {"application/x-lmdj-proof"},
          "lmdj.artifact.proof.v1",
          "1.0.0",
          true,
          1,
      }},
      provider::Determinism::deterministic,
      {},
      {"PROVIDER_FAILED"},
      provider::ResourceRequirements{
          provider::ResourceClass::light,
          16,
      },
      provider::ExecutionPolicy{1000, 1},
      provider::CapabilityPolicy{
          {"public"},
          {"local"},
          {"proof.execute"},
      },
      {"test"},
      0,
  };
}

}  // namespace

provider::ProviderRegistration local_proof_failure_registration() {
  return provider::ProviderRegistration{
      std::make_shared<LocalProofFailureProvider>(),
      "1.0.5",
      LMDJ_LOCAL_PROOF_FAILURE_SOURCE_PACKAGE_SHA256,
      std::nullopt,
      {proof_capability()},
  };
}

}  // namespace lmdj::providers
