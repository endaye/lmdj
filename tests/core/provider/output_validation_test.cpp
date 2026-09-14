#include <iostream>
#include "tests/core/provider/byte_harness.hpp"
using namespace byte_fixture;

void missing_validator() {
  Fixture f;
  auto registration = f.registration(success);
  registration.output_validation.clear();
  LMDJ_CHECK(!f.registry.add(std::move(registration)).has_value());
}
void validator_rejects(bool optional) {
  Fixture f;
  auto registration = f.registration(success);
  registration.capabilities[0].output_artifacts[0].required = !optional;
  registration.output_validation[0].validate =
      [](const auto&, auto inputs, const auto& binding, auto bytes, auto) {
        LMDJ_CHECK(inputs.size() == 1);
        LMDJ_CHECK(binding.artifact.byte_length == bytes.size());
        return Result<void>::failure({ErrorCode::invalid_argument, "invalid schema"});
      };
  f.install(std::move(registration));
  f.reason(f.execute(request(), options()), ErrorCode::provider_failed, "output_schema_invalid");
  auto terminal = f.store.inspect(AttemptId{"attempt-bytes"}).value();
  LMDJ_CHECK(terminal.candidate_ids.empty());
  LMDJ_CHECK(terminal.minted_outputs.empty());
  LMDJ_CHECK(!std::filesystem::exists(f.path / ".lmdj-workspace/attempts/attempt-bytes"));
}
void scratch_budget() {
  Fixture f;
  auto registration = f.registration(success);
  registration.output_validation[0].scratch_bytes = 1;
  bool called = false;
  registration.output_validation[0].validate = [&](const auto&, auto, const auto&, auto, auto) {
    called = true; return Result<void>::success();
  };
  f.install(std::move(registration));
  auto config = options();
  config.staging_budget = std::make_shared<StagingBudget>(1);
  f.reason(f.execute(request(), config), ErrorCode::provider_failed, "output_contract_invalid");
  LMDJ_CHECK(!called);
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
}
void ignored_sink_failure(int mode) {
  Fixture f;
  f.install(f.registration([mode](auto context) {
    if (mode == 0) {
      const std::array payload{std::byte{'x'}};
      LMDJ_CHECK(!context.output("candidate", payload, "application/x-lmdj-proof").has_value());
    } else if (mode == 1) {
      LMDJ_CHECK(!context.output("wrong-port", {}, "application/x-lmdj-proof").has_value());
    } else {
      LMDJ_CHECK(context.output("candidate", {}, "application/x-lmdj-proof").has_value());
    }
    return success(context);
  }));
  f.reason(f.execute(request(), options()), ErrorCode::provider_failed, "output_contract_invalid");
}
void domain_error(bool approved) {
  Fixture f;
  auto registration = f.registration([approved](auto context) {
    return AttemptResult{context.attempt_id, std::nullopt,
        Error{ErrorCode::provider_failed, "private provider message",
              {{"reason", approved ? "analysis_failed" : "input_artifact_unavailable"},
               {"secret", "do not persist"}}}};
  });
  registration.domain_errors.push_back({"proof.candidate.v2", ErrorCode::provider_failed, "analysis_failed"});
  f.install(std::move(registration));
  auto result = f.execute(request(), options());
  f.reason(result, ErrorCode::provider_failed, approved ? "analysis_failed" : "output_contract_invalid");
  auto terminal = f.store.inspect(result.attempt_id).value();
  LMDJ_CHECK(!terminal.error->details.contains("secret"));
  LMDJ_CHECK(terminal.error->message != "private provider message");
}
void provider_cannot_spoof_owner_mismatch() {
  Fixture f;
  f.install(f.registration([](auto context) {
    return AttemptResult{context.attempt_id, std::nullopt,
        Error{ErrorCode::io_error, "owner mismatch impersonation",
              {{"reason", "input_artifact_mismatch"}, {"path", "/private/owner"}}}};
  }));
  const auto result = f.execute(request(), options());
  f.reason(result, ErrorCode::provider_failed, "output_contract_invalid");
  LMDJ_CHECK(!f.store.inspect(result.attempt_id).value().error->details.contains("path"));
}
void aggregate_output(bool exact) {
  Fixture f;
  auto registration = f.registration([](auto context) {
    const std::array a{std::byte{'a'}}, b{std::byte{'b'}};
    const auto first = context.output("candidate", a, "application/x-lmdj-proof");
    LMDJ_CHECK(first.has_value());
    const auto second = context.output("candidate", b, "application/x-lmdj-proof");
    if (!second.has_value()) return AttemptResult{context.attempt_id, std::nullopt,
        Error{ErrorCode::provider_failed, "second refused"}};
    return AttemptResult{context.attempt_id,
        Candidate{CandidateId{context.attempt_id.value()},
            {{"candidate", first.value()}, {"candidate", second.value()}},
            nlohmann::json::object()}, std::nullopt};
  });
  registration.capabilities[0].max_output_bytes = 2;
  registration.capabilities[0].output_artifacts[0].max_count = 2;
  registration.output_validation[0].validate = [](const auto&, auto, const auto&, auto bytes, auto) {
    LMDJ_CHECK(bytes.size() == 1); return Result<void>::success();
  };
  f.install(std::move(registration));
  auto config = options(); config.maximum_output_bytes = exact ? 2 : 1;
  auto result = f.execute(request(), config);
  if (exact) LMDJ_CHECK(result.candidate->outputs.size() == 2);
  else f.reason(result, ErrorCode::provider_failed, "output_contract_invalid");
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
}
int main() {
  try {
    missing_validator(); validator_rejects(false); validator_rejects(true);
    scratch_budget();
    for (int mode = 0; mode < 3; ++mode) ignored_sink_failure(mode);
    domain_error(false); domain_error(true);
    provider_cannot_spoof_owner_mismatch();
    aggregate_output(false); aggregate_output(true);
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
