#include <csignal>
#include <sys/wait.h>
#include <unistd.h>
#include <iostream>
#include <fstream>
#include "tests/core/provider/byte_harness.hpp"
using namespace byte_fixture;
std::string crash_at;
std::string fail_at;
std::filesystem::path obstruction;
namespace lmdj::provider::test {
void checkpoint(std::string_view name) {
  if (name == crash_at) ::raise(SIGKILL);
  if (name == fail_at) std::filesystem::create_directory(obstruction);
}
}
void persistence_failure(bool publication) {
  Fixture f;
  f.install(f.registration(success));
  auto baseline = f.execute(request(), options(), "immutable");
  LMDJ_CHECK(baseline.candidate.has_value());
  obstruction = f.path / (publication
      ? ".lmdj-workspace/attempts/interrupted/artifacts"
      : ".lmdj-workspace/attempts/interrupted.json");
  fail_at = publication ? "validated" : "published";
  const auto failed = f.store.execute(AttemptId{"interrupted"}, request(), f.registry, options());
  fail_at.clear();
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == (publication ? ErrorCode::io_error : ErrorCode::duplicate_id));
  LMDJ_CHECK(std::filesystem::exists(f.path / ".lmdj-workspace/attempts/interrupted"));
  // Remove only the injected obstruction, then reopen the interrupted store.
  std::filesystem::remove(obstruction);
  AttemptStore restarted(f.path, {{"local"}, {"public"}, {"proof.execute"}},
                         [] { return std::string("2026-09-09T00:00:01.000Z"); });
  LMDJ_CHECK(!restarted.inspect(AttemptId{"interrupted"}).has_value());
  const auto reused = restarted.execute(AttemptId{"interrupted"}, request(), f.registry, options());
  LMDJ_CHECK(!reused.has_value() && reused.error().code == ErrorCode::duplicate_id);
  LMDJ_CHECK(restarted.inspect(AttemptId{"immutable"}).value().candidate_outputs == baseline.candidate->outputs);
}
void journey(std::string boundary) {
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
  registration.output_validation[0].validate = [](const auto&, auto, const auto&, auto bytes, auto) {
    LMDJ_CHECK(bytes.size() == 1 && bytes[0] == std::byte{'a'});
    return Result<void>::success();
  };
  f.install(std::move(registration));
  auto baseline = f.execute(request(), options(), "immutable");
  LMDJ_CHECK(baseline.candidate.has_value());
  LMDJ_CHECK(baseline.candidate->outputs[0].artifact.sha256 == request().inputs[0].artifact.sha256);
  LMDJ_CHECK(baseline.candidate->outputs[0].artifact.byte_length == 1);
  crash_at = boundary;
  auto child = ::fork();
  LMDJ_CHECK(child >= 0);
  if (child == 0) {
    (void) f.execute(request(), options(), "interrupted");
    ::_exit(99);
  }
  int status = 0;
  LMDJ_CHECK(::waitpid(child, &status, 0) == child);
  LMDJ_CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL);
  crash_at.clear();
  // Restart in a separate process and inspect only persisted state.
  child = ::fork();
  LMDJ_CHECK(child >= 0);
  if (child == 0) {
    try {
      AttemptStore restarted(f.path, {{"local"}, {"public"}, {"proof.execute"}},
                             [] { return std::string("2026-09-09T00:00:01.000Z"); });
      const auto prior = restarted.inspect(AttemptId{"immutable"});
      LMDJ_CHECK(prior.has_value());
      LMDJ_CHECK(prior.value().candidate_outputs == baseline.candidate->outputs);
      const auto recovered = restarted.inspect(AttemptId{"interrupted"});
      if (boundary == "terminal") {
        LMDJ_CHECK(recovered.has_value());
        LMDJ_CHECK(recovered.value().status == AttemptStatus::succeeded);
        LMDJ_CHECK(recovered.value().candidate_outputs == baseline.candidate->outputs);
        for (const auto& output : recovered.value().candidate_outputs) {
          auto path = f.path / ".lmdj-workspace/attempts/interrupted/artifacts" / output.artifact.sha256;
          auto actual = describe_artifact(path, output.artifact.media_type);
          LMDJ_CHECK(actual.has_value());
          LMDJ_CHECK(actual.value() == output.artifact);
        }
      } else {
        LMDJ_CHECK(!recovered.has_value());
        LMDJ_CHECK(recovered.error().code == ErrorCode::not_found);
      }
      LMDJ_CHECK(std::filesystem::exists(f.path / ".lmdj-workspace/attempts/interrupted"));
      const auto reuse = restarted.execute(AttemptId{"interrupted"}, request(), f.registry, options());
      LMDJ_CHECK(!reuse.has_value());
      LMDJ_CHECK(reuse.error().code == ErrorCode::duplicate_id);
      LMDJ_CHECK(restarted.inspect(AttemptId{"immutable"}).value().candidate_outputs ==
                 baseline.candidate->outputs);
      ::_exit(0);
    } catch (const std::exception& error) {
      std::cerr << boundary << ": " << error.what() << std::endl; ::_exit(1);
    }
  }
  LMDJ_CHECK(::waitpid(child, &status, 0) == child);
  LMDJ_CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
}
int main() {
  try {
    for (const auto* boundary : {"reserved", "inputs", "staged", "validated", "published", "terminal"})
      journey(boundary);
    persistence_failure(true); persistence_failure(false);
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
