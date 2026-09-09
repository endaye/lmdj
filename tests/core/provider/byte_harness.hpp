#pragma once
#include "byte_fixture.hpp"
#include <lmdj/providers/local_proof_success/factory.hpp>
#include "tests/core/support/test.hpp"
namespace byte_fixture {
using namespace lmdj::provider;
using namespace lmdj::foundation;
using Run = std::function<AttemptResult(ProviderRunContext)>;
class FunctionProvider final : public Provider {
 public:
  explicit FunctionProvider(Run run) : run_(std::move(run)) {}
  std::string id() const override { return "test.bytes"; }
  std::vector<std::string> capabilities() const override { return {"proof.candidate.v2"}; }
  AttemptResult run(ProviderRunContext context) override { return run_(std::move(context)); }
 private: Run run_;
};
inline AttemptResult success(ProviderRunContext context) {
  auto output = context.output("candidate", {}, "application/x-lmdj-proof");
  if (!output.has_value()) return {context.attempt_id, std::nullopt,
                                  Error{ErrorCode::provider_failed, "sink failed"}};
  return {context.attempt_id,
          Candidate{CandidateId{context.attempt_id.value()},
                    {{"candidate", output.value()}}, nlohmann::json::object()}, std::nullopt};
}
inline CapabilityRequest request() {
  return {"proof.candidate.v2",
          {{"inputs", {"ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb", "audio/wav", 1}}},
          nlohmann::json::object(), "public", "test", "local", {"proof.execute"}};
}
class Fixture {
 public:
  Fixture() : path(std::filesystem::temp_directory_path() /
      ("lmdj-byte-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()))),
      store(path, {{"local"}, {"public"}, {"proof.execute"}},
            [] { return std::string("2026-09-09T00:00:00.000Z"); }) {}
  ~Fixture() { std::error_code ec; std::filesystem::remove_all(path, ec); }
  ProviderRegistration registration(Run run) {
    auto value = lmdj::providers::local_proof_success_registration();
    value.implementation = std::make_shared<FunctionProvider>(std::move(run));
    return value;
  }
  void install(ProviderRegistration registration) {
    LMDJ_CHECK(registry.add(std::move(registration)).has_value());
    LMDJ_CHECK(store.set_provider_selection("proof.candidate.v2", "test.bytes", registry).has_value());
  }
  AttemptResult execute(const CapabilityRequest& input, const ExecutionOptions& config,
                        std::string id = "attempt-bytes") {
    auto result = store.execute(AttemptId{id}, input, registry, config);
    LMDJ_CHECK(result.has_value());
    return result.value();
  }
  void reason(const AttemptResult& result, ErrorCode code, std::string_view reason) {
    LMDJ_CHECK(result.error.has_value());
    LMDJ_CHECK(result.error->code == code);
    LMDJ_CHECK(result.error->details.at("reason") == reason);
    auto terminal = store.inspect(result.attempt_id);
    LMDJ_CHECK(terminal.has_value());
    LMDJ_CHECK(terminal.value().error->code == code);
    LMDJ_CHECK(terminal.value().error->details.at("reason") == reason);
  }
  std::filesystem::path path;
  AttemptStore store;
  Registry registry;
};
} // namespace byte_fixture
