#include <fstream>
#include <iostream>
#include "tests/core/provider/byte_harness.hpp"
using namespace byte_fixture;

void empty_output_is_verified() {
  Fixture f; f.install(f.registration(success));
  const auto result = f.execute(request(), options());
  LMDJ_CHECK(result.candidate.has_value());
  const auto artifact = result.candidate->outputs[0].artifact;
  const auto bytes = f.store.read_candidate_artifact(result.attempt_id, artifact, 0);
  LMDJ_CHECK(bytes.has_value() && bytes.value().empty());
  auto unbound = artifact; unbound.media_type = "application/json";
  LMDJ_CHECK(!f.store.read_candidate_artifact(result.attempt_id, unbound, 0).has_value());
}
void damaged_output_is_refused(int damage) {
  Fixture f;
  auto registration = f.registration([](auto context) {
    const std::array payload{std::byte{'a'}};
    const auto output = context.output("candidate", payload, "application/x-lmdj-proof");
    LMDJ_CHECK(output.has_value());
    return AttemptResult{context.attempt_id,
        Candidate{CandidateId{context.attempt_id.value()}, {{"candidate", output.value()}},
                  nlohmann::json::object()}, std::nullopt};
  });
  registration.capabilities[0].max_output_bytes = 1;
  registration.output_validation[0].validate = [](const auto&, auto, const auto&, auto, auto) {
    return Result<void>::success();
  };
  f.install(std::move(registration));
  const auto result = f.execute(request(), options());
  LMDJ_CHECK(result.candidate.has_value());
  const auto artifact = result.candidate->outputs[0].artifact;
  const auto bytes = f.store.read_candidate_artifact(result.attempt_id, artifact, 1);
  LMDJ_CHECK(bytes.has_value() && bytes.value() == std::vector{std::byte{'a'}});
  LMDJ_CHECK(!f.store.read_candidate_artifact(result.attempt_id, artifact, 0).has_value());
  const auto terminal = f.store.inspect(result.attempt_id).value();
  const auto path = f.path / ".lmdj-workspace/attempts/attempt-bytes/artifacts" / artifact.sha256;
  if (damage == 0) { std::ofstream stream(path); stream << 'b'; }
  if (damage == 1) { std::ofstream stream(path); stream << "aa"; }
  if (damage == 2) std::filesystem::remove(path);
  if (damage == 3) {
    const auto target = f.path / "outside";
    { std::ofstream stream(target); stream << 'a'; }
    std::filesystem::remove(path); std::filesystem::create_symlink(target, path);
  }
  LMDJ_CHECK(!f.store.read_candidate_artifact(result.attempt_id, artifact, 1).has_value());
  LMDJ_CHECK(f.store.inspect(result.attempt_id).value().candidate_outputs == terminal.candidate_outputs);
}
void fresh_workspace_has_no_attempts() {
  Fixture f; std::filesystem::create_directories(f.path);
  const auto result = f.store.inspect(AttemptId{"absent"});
  LMDJ_CHECK(!result.has_value() && result.error().code == ErrorCode::not_found);
  LMDJ_CHECK(!std::filesystem::exists(f.path / ".lmdj-workspace"));
}
void reservation_callback_precedes_owner_reads() {
  Fixture f;
  int callbacks = 0, reads = 0, runs = 0;
  f.install(f.registration([&](auto context) {
    LMDJ_CHECK(callbacks == 1 && reads == 1);
    ++runs;
    return success(std::move(context));
  }));
  auto config = options();
  const auto resolve = config.resolve_input;
  config.resolve_input = [&](const auto& artifact) {
    LMDJ_CHECK(callbacks == 1);
    ++reads;
    return resolve(artifact);
  };
  const AttemptId id{"callback-order"};
  const auto result = f.store.execute(id, request(), f.registry, config, [&] {
    ++callbacks;
    LMDJ_CHECK(reads == 0 && runs == 0);
    // Reentrant competition proves reservation ownership before the callback.
    LMDJ_CHECK(!f.store.execute(id, request(), f.registry, config).has_value());
    return Result<void>::success();
  });
  LMDJ_CHECK(result.has_value() && result.value().candidate.has_value());
  LMDJ_CHECK(callbacks == 1 && reads == 1 && runs == 1);
}
void duplicate_attempt_skips_callback() {
  Fixture f; f.install(f.registration(success));
  const auto original = f.execute(request(), options());
  int callbacks = 0;
  const auto duplicate = f.store.execute(original.attempt_id, request(), f.registry,
      options(), [&] { ++callbacks; return Result<void>::success(); });
  LMDJ_CHECK(!duplicate.has_value());
  LMDJ_CHECK(callbacks == 0);
}
void failed_callback_retains_reservation(int failure) {
  Fixture f;
  int callbacks = 0, reads = 0, runs = 0;
  f.install(f.registration([&](auto context) { ++runs; return success(std::move(context)); }));
  auto config = options();
  const auto resolve = config.resolve_input;
  config.resolve_input = [&](const auto& artifact) { ++reads; return resolve(artifact); };
  const AttemptId id{"callback-failure"};
  const auto result = f.store.execute(id, request(), f.registry, config,
      [&]() -> Result<void> {
        ++callbacks;
        if (failure == 1) throw std::runtime_error("intent persistence failed");
        if (failure == 2) throw 7;
        return Result<void>::failure({ErrorCode::permission_denied, "intent denied"});
      });
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code ==
      (failure == 0 ? ErrorCode::permission_denied : ErrorCode::io_error));
  if (failure == 0) LMDJ_CHECK(result.error().message == "intent denied");
  const auto terminal = f.store.inspect(id);
  LMDJ_CHECK(!terminal.has_value() && terminal.error().code == ErrorCode::not_found);
  const auto retry = f.store.execute(id, request(), f.registry, config,
      [&] { ++callbacks; return Result<void>::success(); });
  LMDJ_CHECK(!retry.has_value());
  LMDJ_CHECK(callbacks == 1 && reads == 0 && runs == 0);
}
void policy_preflight_needs_no_inputs_or_resolver() {
  Fixture f; f.install(f.registration(success));
  auto input = request();
  input.inputs.clear();
  LMDJ_CHECK(f.store.validate_execution_policy(input, f.registry).has_value());
  input.inputs = {{"undeclared", {"invalid", "invalid", 999}}};
  LMDJ_CHECK(f.store.validate_execution_policy(input, f.registry).has_value());
  input.region = "denied";
  const auto denied = f.store.validate_execution_policy(input, f.registry);
  LMDJ_CHECK(!denied.has_value() && denied.error().code == ErrorCode::permission_denied);
  input = request(); input.inputs[0].port = "undeclared";
  const auto full = f.execute(input, options());
  f.reason(full, ErrorCode::invalid_argument, "input_binding_invalid");
}
int main() {
  try {
    empty_output_is_verified(); fresh_workspace_has_no_attempts();
    reservation_callback_precedes_owner_reads(); duplicate_attempt_skips_callback();
    for (int failure : {0, 1, 2}) failed_callback_retains_reservation(failure);
    policy_preflight_needs_no_inputs_or_resolver();
    for (int damage : {0, 1, 2, 3}) damaged_output_is_refused(damage);
    std::cout << "verified Attempt output reads: PASS\n";
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
