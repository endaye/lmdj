#include "tests/core/facade/candidate_fixture.hpp"

#include <sys/wait.h>
#include <unistd.h>

namespace {
void crash_recovery(int boundary, bool has_prior) {
  Fixture f; f.grant(); const auto truth = f.snapshot();
  Json prior = nullptr;
  if (has_prior) { ok(f.app->command(job_request(f, "baseline"))); prior = job(f); }
  f.app.reset();
  const auto child = fork();
  LMDJ_CHECK(child >= 0);
  if (child == 0) {
    f.restart(); f.grant();
    unsigned replacements = 0;
    f.storage->replace_hook = [&](const auto& path, bool after) {
      if (path != f.root / ".lmdj-host/candidates/state.json") return;
      if (!after) ++replacements;
      if ((boundary == 1 && replacements == 1 && after) ||
          (boundary == 2 && replacements == 2 && !after) ||
          (boundary == 3 && replacements == 2 && after)) _exit(70 + boundary);
    };
    f.app->command(job_request(f));
    _exit(99);
  }
  int status = 0;
  LMDJ_CHECK(waitpid(child, &status, 0) == child);
  LMDJ_CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 70 + boundary);
  const auto raw = Json::parse(read(f.root / ".lmdj-host/candidates/state.json"));
  const auto index = has_prior ? 1 : 0;
  const auto set_id = raw.at("jobs").at("slice").at("history")[index].at("set_id");
  f.restart();
  const auto recovered = job(f);
  LMDJ_CHECK(recovered.at("history").size() == (has_prior ? 2 : 1));
  if (boundary == 1) {
    LMDJ_CHECK(recovered.at("history")[index].at("status") == "interrupted");
    if (has_prior) {
      LMDJ_CHECK(recovered.at("sets") == prior.at("sets"));
      LMDJ_CHECK(recovered.at("active_set_id") == prior.at("active_set_id"));
    } else {
      LMDJ_CHECK(recovered.at("sets").empty());
      LMDJ_CHECK(recovered.at("active_set_id").is_null());
    }
    LMDJ_CHECK(!std::filesystem::exists(f.root / ".lmdj-workspace/attempts/first.json"));
  } else {
    if (recovered.at("history")[index].at("status") != "succeeded")
      throw std::runtime_error("boundary " + std::to_string(boundary) + ": " + recovered.dump() + " terminal: " +
          f.app->query({{"operation", "attempt.inspect"}, {"attempt_id", "first"}}).dump());
    LMDJ_CHECK(recovered.at("history")[index].at("status") == "succeeded");
    LMDJ_CHECK(recovered.at("sets").size() == (has_prior ? 2 : 1));
    if (has_prior) LMDJ_CHECK(recovered.at("sets")[0].at("status") == "superseded");
    LMDJ_CHECK(recovered.at("active_set_id") == set_id);
    LMDJ_CHECK(recovered.at("sets")[index].at("recipes").size() == 3);
  }
  f.restart(); LMDJ_CHECK(job(f) == recovered);
  LMDJ_CHECK(f.snapshot() == truth);
}
void live_job_is_not_recovered_or_reentered() {
  Fixture f; f.app.reset(); const auto truth = f.snapshot();
  int ready[2], resume[2];
  LMDJ_CHECK(pipe(ready) == 0 && pipe(resume) == 0);
  const auto child = fork(); LMDJ_CHECK(child >= 0);
  if (child == 0) {
    close(ready[0]); close(resume[1]);
    f.restart(); f.grant();
    bool paused = false;
    f.storage->read_hook = [&](const auto& path) {
      if (paused || path != f.blob() ||
          !std::filesystem::exists(f.root / ".lmdj-host/candidates/state.json")) return;
      paused = true; char signal = 'r';
      if (::write(ready[1], &signal, 1) != 1 || ::read(resume[0], &signal, 1) != 1) _exit(98);
    };
    const auto response = f.app->command(job_request(f));
    _exit(response.at("ok").get<bool>() ? 0 : 99);
  }
  close(ready[1]); close(resume[0]);
  char signal = 0; LMDJ_CHECK(::read(ready[0], &signal, 1) == 1);
  f.restart(); f.grant();
  const auto pending = job(f);
  const auto refused = f.app->command(job_request(f, "racing"));
  // Release the child before assertions, so a failed assertion cannot strand it.
  LMDJ_CHECK(::write(resume[1], "r", 1) == 1);
  close(ready[0]); close(resume[1]);
  int status = 0; LMDJ_CHECK(waitpid(child, &status, 0) == child);
  LMDJ_CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
  LMDJ_CHECK(pending.at("history")[0].at("status") == "pending");
  LMDJ_CHECK(pending.at("sets").empty());
  error(refused, "INVALID_ARGUMENT");
  LMDJ_CHECK(refused.at("error").at("details").at("reason") == "job_busy");
  const auto completed = job(f);
  LMDJ_CHECK(completed.at("history").size() == 1);
  LMDJ_CHECK(completed.at("history")[0].at("status") == "succeeded");
  LMDJ_CHECK(completed.at("sets").size() == 1);
  LMDJ_CHECK(!std::filesystem::exists(f.root / ".lmdj-workspace/attempts/racing.json"));
  LMDJ_CHECK(f.snapshot() == truth);
}

}
int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string_view(argv[1]) == "--stress") {
      for (int iteration = 0; iteration < 100; ++iteration) live_job_is_not_recovered_or_reentered();
      std::cout << "candidate process stress: PASS\n"; return 0;
    }
    LMDJ_CHECK(argc == 1);
    for (int boundary : {1, 2, 3}) for (bool prior : {false, true}) crash_recovery(boundary, prior);
    live_job_is_not_recovered_or_reentered();
    std::cout << "candidate process recovery: PASS\n";
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
