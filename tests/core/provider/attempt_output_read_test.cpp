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
int main() {
  try {
    empty_output_is_verified(); fresh_workspace_has_no_attempts();
    for (int damage : {0, 1, 2, 3}) damaged_output_is_refused(damage);
    std::cout << "verified Attempt output reads: PASS\n";
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
