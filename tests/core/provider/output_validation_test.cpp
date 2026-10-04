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

void shared_roles_validate_independently(bool reject_secondary) {
  Fixture f;
  auto registration = shared_registration(f);
  std::vector<std::string> validated;
  for (auto& validator : registration.output_validation) {
    validator.validate = [&](const auto&, auto, const auto& binding, auto bytes, auto) {
      validated.push_back(binding.port);
      LMDJ_CHECK(bytes.size() == 1 && bytes[0] == std::byte{'a'});
      if (reject_secondary && binding.port == "secondary")
        return Result<void>::failure({ErrorCode::invalid_argument, "secondary schema"});
      return Result<void>::success();
    };
  }
  f.install(std::move(registration));
  const auto config = options();
  const bool reject_requested = reject_secondary;
  reject_secondary = false;
  const auto prior = f.execute(request(), config, "immutable");
  LMDJ_CHECK(prior.candidate.has_value());
  validated.clear();
  reject_secondary = reject_requested;
  const auto result = f.execute(request(), config);
  LMDJ_CHECK(validated == (std::vector<std::string>{"primary", "secondary"}));
  if (reject_secondary) {
    f.reason(result, ErrorCode::provider_failed, "output_schema_invalid");
    LMDJ_CHECK(f.store.inspect(result.attempt_id).value().minted_outputs.empty());
    LMDJ_CHECK(!std::filesystem::exists(f.path / ".lmdj-workspace/attempts/attempt-bytes"));
  } else LMDJ_CHECK(result.candidate.has_value());
  LMDJ_CHECK(f.store.inspect(prior.attempt_id).value().candidate_outputs == prior.candidate->outputs);
  for (const auto& binding : prior.candidate->outputs) {
    const auto bytes = f.store.read_candidate_artifact(prior.attempt_id, binding.artifact, 1);
    LMDJ_CHECK(bytes.has_value() && bytes.value() == std::vector{std::byte{'a'}});
  }
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
}
void repeated_output_is_refused(bool same_port) {
  Fixture f;
  bool refused = false;
  auto registration = shared_registration(f, [&](auto context) {
    const std::array payload{std::byte{'a'}};
    const auto first = context.output("primary", payload, "application/x-lmdj-proof");
    LMDJ_CHECK(first.has_value());
    const auto repeated = context.output(same_port ? "primary" : "secondary", payload,
        same_port ? "application/x-lmdj-proof" : "application/octet-stream");
    refused = !repeated.has_value();
    // Ignoring the refusal must still fail the whole Attempt.
    return AttemptResult{context.attempt_id, Candidate{CandidateId{context.attempt_id.value()},
        {{"primary", first.value()}}, nlohmann::json::object()}, std::nullopt};
  });
  // Avoid testing only the per-port max_count or media-type allowlist.
  registration.capabilities[0].output_artifacts[0].max_count = 2;
  registration.capabilities[0].output_artifacts[1].media_types.push_back("application/octet-stream");
  f.install(std::move(registration));
  const auto config = options();
  const auto result = f.execute(request(), config);
  LMDJ_CHECK(refused);
  f.reason(result, ErrorCode::provider_failed, "output_contract_invalid");
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
  LMDJ_CHECK(!std::filesystem::exists(f.path / ".lmdj-workspace/attempts/attempt-bytes"));
}
void shared_candidate_binding_is_exact(int damage) {
  Fixture f;
  auto registration = shared_registration(f, [damage](auto context) {
    auto result = shared_outputs(context);
    auto& outputs = result.candidate->outputs;
    if (damage == 0) outputs.pop_back();
    if (damage == 1) outputs.push_back(outputs[0]);
    if (damage == 2) ++outputs[1].artifact.byte_length;
    if (damage == 3) outputs[1].artifact.media_type = "audio/wav";
    if (damage == 4) outputs[1].port = "primary";
    return result;
  });
  for (auto& port : registration.capabilities[0].output_artifacts) {
    port.max_count = 2;
    port.media_types.push_back("audio/wav");
  }
  f.install(std::move(registration));
  const auto config = options();
  const auto result = f.execute(request(), config);
  f.reason(result, ErrorCode::provider_failed, "output_contract_invalid");
  LMDJ_CHECK(f.store.inspect(result.attempt_id).value().candidate_outputs.empty());
  LMDJ_CHECK(!std::filesystem::exists(f.path / ".lmdj-workspace/attempts/attempt-bytes"));
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
}
void shared_output_budget(bool staging, bool exact) {
  Fixture f;
  f.install(shared_registration(f));
  auto config = options();
  // One input byte plus two retained logical output buffers.
  if (staging) config.staging_budget = std::make_shared<StagingBudget>(exact ? 3 : 2);
  else config.maximum_output_bytes = exact ? 2 : 1;
  const auto result = f.execute(request(), config);
  if (exact) LMDJ_CHECK(result.candidate.has_value());
  else {
    f.reason(result, ErrorCode::provider_failed, "output_contract_invalid");
    LMDJ_CHECK(!std::filesystem::exists(f.path / ".lmdj-workspace/attempts/attempt-bytes"));
  }
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
}
int main() {
  try {
    shared_roles_validate_independently(false); shared_roles_validate_independently(true);
    repeated_output_is_refused(false); repeated_output_is_refused(true);
    for (int damage = 0; damage < 5; ++damage) shared_candidate_binding_is_exact(damage);
    for (bool staging : {false, true})
      for (bool exact : {false, true}) shared_output_budget(staging, exact);
    missing_validator(); validator_rejects(false); validator_rejects(true);
    scratch_budget();
    for (int mode = 0; mode < 3; ++mode) ignored_sink_failure(mode);
    domain_error(false); domain_error(true);
    provider_cannot_spoof_owner_mismatch();
    aggregate_output(false); aggregate_output(true);
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
