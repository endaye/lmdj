#include <lmdj/facade/candidate_store.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/foundation/artifact.hpp>
#include "tests/core/facade/candidate_fixture.hpp"

#include <sys/wait.h>
#include <unistd.h>

namespace {
Json adopt_request(const Fixture& f, const Json& set) {
  return {{"operation", "candidate.adopt"}, {"project_path", f.project.generic_string()},
      {"project_id", project_id}, {"expected_revision", 1}, {"command_id", other_id},
      {"job_id", "slice"}, {"set_id", set.at("set_id")},
      {"selections", Json::array({{{"candidate_id", set.at("recipes")[1].at("candidate_id")},
                                  {"bank", 0}, {"pad", 3}}})}};
}
lmdj::domain::ProjectState verify_adoption(Fixture& f, const Json& set, const Json& result) {
  ProjectStore store;
  const auto loaded = store.load(f.project); LMDJ_CHECK(loaded.has_value());
  const auto committed = loaded.value();
  LMDJ_CHECK(committed.revision == 2 && committed.assets.size() == 2);
  const auto id = AssetId{result.at("result").at("adopted")[0].at("asset_id").get<std::string>()};
  LMDJ_CHECK(committed.banks[0][3].asset_id == id);
  const auto& asset = committed.assets.at(id);
  const auto actual = describe_artifact(f.project / "assets" / (asset.artifact.sha256 + ".wav"), "audio/wav");
  LMDJ_CHECK(actual.has_value() && actual.value() == asset.artifact);
  LMDJ_CHECK(asset.artifact.byte_length == 48);
  LMDJ_CHECK(asset.lineage.has_value());
  auto recipe = set.at("recipes")[1]; recipe.erase("candidate_id");
  LMDJ_CHECK(lmdj::domain::asset_lineage_json(*asset.lineage) == (Json{
      {"source", {{"kind", "asset_artifact"}, {"artifact_sha256", f.source.at("sha256")}, {"project_revision", 1}}},
      {"derivation", {{"kind", "capability_adoption"}, {"capability", set.at("capability")},
        {"provider", set.at("provider")}, {"model_identity", set.at("model_identity")},
        {"parameters_sha256", set.at("parameters_sha256")}, {"attempt_id", set.at("attempt_id")},
        {"source_asset_id", asset_id}, {"output_artifact", set.at("output_artifact")}, {"recipe", recipe}}}}));
  LMDJ_CHECK(read(f.blob()) == wav());
  return committed;
}
void adoption_excludes_discard_until_commit() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto before = job(f); const auto set = before.at("sets")[0];
  const auto terminal_path = f.root / ".lmdj-workspace/attempts/first.json";
  const auto terminal = read(terminal_path);
  const auto discard = Json{{"operation", "candidate.set.discard"},
      {"job_id", "slice"}, {"set_id", set.at("set_id")}};
  int ready[2], resume[2]; LMDJ_CHECK(pipe(ready) == 0 && pipe(resume) == 0);
  const auto child = fork(); LMDJ_CHECK(child >= 0);
  if (child == 0) {
    close(ready[0]); close(resume[1]);
    try {
      f.restart();
      LMDJ_CHECK(::write(ready[1], "r", 1) == 1);
      char signal; LMDJ_CHECK(::read(resume[0], &signal, 1) == 1);
      const auto refused = f.app->command(discard);
      error(refused, "INVALID_ARGUMENT");
      LMDJ_CHECK(refused.at("error").at("details").at("reason") == "job_busy");
      _exit(0);
    } catch (...) { _exit(98); }
  }
  close(ready[1]); close(resume[0]);
  char signal; LMDJ_CHECK(::read(ready[0], &signal, 1) == 1);
  bool fenced = false;
  f.storage->replace_hook = [&](const auto& path, bool after) {
    if (fenced || after || path != f.project / "manifest.json") return;
    fenced = true;
    LMDJ_CHECK(::write(resume[1], "g", 1) == 1);
    int status = 0; LMDJ_CHECK(waitpid(child, &status, 0) == child);
    LMDJ_CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
  };
  const auto result = f.app->command(adopt_request(f, set));
  f.storage->replace_hook = {};
  close(ready[0]); close(resume[1]);
  // If adoption refused before reaching the fence, release/reap the child
  // through pipe EOF before asserting the response.
  if (!fenced) { int status = 0; LMDJ_CHECK(waitpid(child, &status, 0) == child); }
  ok(result); LMDJ_CHECK(fenced && result.at("project_revision") == 2);
  const auto committed = verify_adoption(f, set, result);
  ProjectStore store;
  LMDJ_CHECK(job(f) == before && read(terminal_path) == terminal);
  const auto truth = f.snapshot();
  ok(f.app->command(discard));
  const auto discarded = job(f);
  LMDJ_CHECK(discarded.at("active_set_id").is_null());
  LMDJ_CHECK(discarded.at("sets")[0].at("status") == "discarded");
  LMDJ_CHECK(discarded.at("history") == before.at("history"));
  f.restart(); LMDJ_CHECK(job(f) == discarded);
  LMDJ_CHECK(store.load(f.project).value() == committed && f.snapshot() == truth);
  LMDJ_CHECK(read(terminal_path) == terminal);
}
void wait_exit(pid_t child, int expected) {
  int status = 0; LMDJ_CHECK(waitpid(child, &status, 0) == child);
  LMDJ_CHECK(WIFEXITED(status) && WEXITSTATUS(status) == expected);
}
void retry_finishes_during_adoption(bool cancelled) {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto before = job(f); const auto set = before.at("sets")[0];
  const auto first_path = f.root / ".lmdj-workspace/attempts/first.json";
  const auto first_terminal = read(first_path);
  const auto owner_path = f.root / ".lmdj-host/candidates/state.json";
  int ready[2], resume[2]; LMDJ_CHECK(pipe(ready) == 0 && pipe(resume) == 0);
  const auto child = fork(); LMDJ_CHECK(child >= 0);
  if (child == 0) {
    close(ready[0]); close(resume[1]);
    try {
      f.restart(); f.grant(); bool paused = false, input_read = false;
      f.storage->read_hook = [&](const auto& path) {
        if (paused || path != f.blob()) return;
        const auto raw = Json::parse(read(owner_path));
        if (raw.at("jobs").at("slice").at("history").size() != 2) return;
        input_read = true;
      };
      // Owned input reads hold the Project writer. Pause only after that
      // real lease releases so adoption can acquire its own writer.
      f.storage->release_hook = [&](const auto& path) {
        if (paused || !input_read || path != f.project) return;
        paused = true;
        LMDJ_CHECK(::write(ready[1], "r", 1) == 1);
        char signal; LMDJ_CHECK(::read(resume[0], &signal, 1) == 1);
      };
      const auto finished = f.app->command(job_request(f, "second"));
      // Immutable SDK completion succeeds, but owner publication is fenced.
      error(finished, "INVALID_ARGUMENT");
      LMDJ_CHECK(finished.at("error").at("details").at("reason") == "job_busy");
      _exit(0);
    } catch (...) { _exit(98); }
  }
  close(ready[1]); close(resume[0]);
  char signal; LMDJ_CHECK(::read(ready[0], &signal, 1) == 1);
  if (cancelled) ok(f.app->command({{"operation", "candidate.job.cancel"},
      {"job_id", "slice"}, {"attempt_id", "second"}}));
  bool fenced = false;
  std::string second_terminal;
  f.storage->replace_hook = [&](const auto& path, bool after) {
    if (fenced || after || path != f.project / "manifest.json") return;
    fenced = true;
    LMDJ_CHECK(::write(resume[1], "g", 1) == 1);
    wait_exit(child, 0);
    second_terminal = read(f.root / ".lmdj-workspace/attempts/second.json");
    LMDJ_CHECK(Json::parse(second_terminal).at("status") == "succeeded");
    const auto raw = Json::parse(read(owner_path));
    LMDJ_CHECK(raw.at("jobs").at("slice").at("history")[1].at("status") ==
        (cancelled ? "cancelled" : "pending"));
    LMDJ_CHECK(raw.at("jobs").at("slice").at("active_set_id") == before.at("active_set_id"));
  };
  const auto result = f.app->command(adopt_request(f, set));
  f.storage->replace_hook = {};
  close(ready[0]); close(resume[1]);
  if (!fenced) { int status = 0; LMDJ_CHECK(waitpid(child, &status, 0) == child); }
  ok(result); LMDJ_CHECK(fenced);
  const auto committed = verify_adoption(f, set, result);
  const auto truth = f.snapshot();
  f.restart(); const auto recovered = job(f);
  LMDJ_CHECK(recovered.at("history").size() == 2);
  LMDJ_CHECK(recovered.at("history")[0] == before.at("history")[0]);
  if (cancelled) {
    LMDJ_CHECK(recovered.at("history")[1].at("status") == "cancelled");
    LMDJ_CHECK(recovered.at("sets") == before.at("sets"));
    LMDJ_CHECK(recovered.at("active_set_id") == before.at("active_set_id"));
  } else {
    LMDJ_CHECK(recovered.at("history")[1].at("status") == "succeeded");
    LMDJ_CHECK(recovered.at("sets").size() == 2);
    LMDJ_CHECK(recovered.at("sets")[0].at("status") == "superseded");
    LMDJ_CHECK(recovered.at("sets")[1].at("attempt_id") == "second");
    LMDJ_CHECK(recovered.at("active_set_id") == recovered.at("sets")[1].at("set_id"));
  }
  ProjectStore store;
  LMDJ_CHECK(store.load(f.project).value() == committed && f.snapshot() == truth);
  f.restart(); LMDJ_CHECK(job(f) == recovered);
  LMDJ_CHECK(store.load(f.project).value() == committed && f.snapshot() == truth);
  LMDJ_CHECK(read(first_path) == first_terminal);
  LMDJ_CHECK(read(f.root / ".lmdj-workspace/attempts/second.json") == second_terminal);
}
void failed_retry_allows_prior_adoption() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto before = job(f); const auto set = before.at("sets")[0];
  const auto first_path = f.root / ".lmdj-workspace/attempts/first.json";
  const auto first_terminal = read(first_path);
  auto retry = job_request(f, "failed"); retry["parameters"]["threshold_pcm16"] = 0;
  error(f.app->command(retry), "INVALID_ARGUMENT");
  const auto failed = job(f);
  LMDJ_CHECK(failed.at("active_set_id") == before.at("active_set_id"));
  LMDJ_CHECK(failed.at("sets") == before.at("sets"));
  LMDJ_CHECK(failed.at("history")[1].at("status") == "failed");
  const auto failed_path = f.root / ".lmdj-workspace/attempts/failed.json";
  const auto failed_terminal = read(failed_path);
  const auto result = f.app->command(adopt_request(f, set)); ok(result);
  const auto committed = verify_adoption(f, set, result);
  const auto truth = f.snapshot();
  f.restart(); LMDJ_CHECK(job(f) == failed);
  ProjectStore store;
  LMDJ_CHECK(store.load(f.project).value() == committed && f.snapshot() == truth);
  LMDJ_CHECK(read(first_path) == first_terminal && read(failed_path) == failed_terminal);
}
void adoption_failure_releases_discard() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto before = job(f); const auto set = before.at("sets")[0];
  ProjectStore store;
  const auto original = store.load(f.project); LMDJ_CHECK(original.has_value());
  const auto terminal_path = f.root / ".lmdj-workspace/attempts/first.json";
  const auto terminal = read(terminal_path);
  bool failed = false;
  f.storage->fail_replace = [&](const auto& path) {
    if (failed || path != f.project / "manifest.json") return false;
    failed = true; return true;
  };
  const auto refused = f.app->command(adopt_request(f, set));
  f.storage->fail_replace = {};
  error(refused, "IO_ERROR"); LMDJ_CHECK(failed);
  LMDJ_CHECK(store.load(f.project).value() == original.value());
  LMDJ_CHECK(std::distance(std::filesystem::directory_iterator(f.project / "assets"), {}) == 1);
  LMDJ_CHECK(read(f.blob()) == wav() && job(f) == before);
  ok(f.app->command({{"operation", "candidate.set.discard"},
      {"job_id", "slice"}, {"set_id", set.at("set_id")}}));
  const auto discarded = job(f);
  LMDJ_CHECK(discarded.at("sets")[0].at("status") == "discarded");
  LMDJ_CHECK(discarded.at("active_set_id").is_null());
  LMDJ_CHECK(discarded.at("history") == before.at("history"));
  f.restart(); LMDJ_CHECK(job(f) == discarded);
  LMDJ_CHECK(store.load(f.project).value() == original.value());
  LMDJ_CHECK(read(f.blob()) == wav() && read(terminal_path) == terminal);
}
void interrupted_recovery_crash() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f, "baseline")));
  const auto before = job(f); const auto truth = f.snapshot(); f.app.reset();
  const auto runner = fork(); LMDJ_CHECK(runner >= 0);
  if (runner == 0) {
    f.restart(); f.grant();
    f.storage->replace_hook = [&](const auto& path, bool after) {
      if (after && path == f.root / ".lmdj-host/candidates/state.json") _exit(64);
    };
    f.app->command(job_request(f)); _exit(99);
  }
  wait_exit(runner, 64);
  const auto recovery = fork(); LMDJ_CHECK(recovery >= 0);
  if (recovery == 0) {
    f.restart();
    f.storage->replace_hook = [&](const auto& path, bool after) {
      if (after && path == f.root / ".lmdj-host/candidates/state.json") _exit(65);
    };
    job(f); _exit(99);
  }
  wait_exit(recovery, 65); f.restart(); const auto after = job(f);
  LMDJ_CHECK(after.at("history")[1].at("status") == "interrupted");
  LMDJ_CHECK(after.at("active_set_id") == before.at("active_set_id"));
  LMDJ_CHECK(after.at("sets") == before.at("sets"));
  LMDJ_CHECK(!std::filesystem::exists(f.root / ".lmdj-workspace/attempts/first.json"));
  f.restart(); LMDJ_CHECK(job(f) == after); LMDJ_CHECK(f.snapshot() == truth);
}
void lifecycle_crash(bool discard, bool after) {
  Fixture f; f.grant(); ok(f.app->command(job_request(f, "baseline")));
  const auto before = job(f); const auto truth = f.snapshot();
  const auto baseline_terminal = read(f.root / ".lmdj-workspace/attempts/baseline.json");
  if (!discard) {
    // Leave a successful immutable terminal and pending owner intent. Cancel
    // must win even though recovery could otherwise publish the terminal.
    f.app.reset(); const auto runner = fork(); LMDJ_CHECK(runner >= 0);
    if (runner == 0) {
      f.restart(); f.grant(); int replacements = 0;
      f.storage->replace_hook = [&](const auto& path, bool completed) {
        if (path == f.root / ".lmdj-host/candidates/state.json" && !completed && ++replacements == 2) _exit(61);
      };
      f.app->command(job_request(f)); _exit(99);
    }
    wait_exit(runner, 61);
  }
  const auto terminal = discard ? baseline_terminal : read(f.root / ".lmdj-workspace/attempts/first.json");
  f.app.reset(); const auto child = fork(); LMDJ_CHECK(child >= 0);
  if (child == 0) {
    f.restart();
    f.storage->replace_hook = [&](const auto& path, bool completed) {
      if (path == f.root / ".lmdj-host/candidates/state.json" && completed == after) _exit(62);
    };
    const auto request = discard
        ? Json{{"operation", "candidate.set.discard"}, {"job_id", "slice"}, {"set_id", before.at("active_set_id")}}
        : Json{{"operation", "candidate.job.cancel"}, {"job_id", "slice"}, {"attempt_id", "first"}};
    f.app->command(request); _exit(99);
  }
  wait_exit(child, 62); f.restart(); const auto recovered = job(f);
  if (discard) {
    LMDJ_CHECK(recovered.at("history") == before.at("history"));
    if (after) {
      LMDJ_CHECK(recovered.at("active_set_id").is_null());
      LMDJ_CHECK(recovered.at("sets")[0].at("status") == "discarded");
    } else LMDJ_CHECK(recovered == before);
  } else if (after) {
    LMDJ_CHECK(recovered.at("history")[1].at("status") == "cancelled");
    LMDJ_CHECK(recovered.at("sets") == before.at("sets"));
    LMDJ_CHECK(recovered.at("active_set_id") == before.at("active_set_id"));
  } else {
    LMDJ_CHECK(recovered.at("history")[1].at("status") == "succeeded");
    LMDJ_CHECK(recovered.at("sets")[0].at("status") == "superseded");
    LMDJ_CHECK(recovered.at("active_set_id") == recovered.at("sets")[1].at("set_id"));
  }
  f.restart(); LMDJ_CHECK(job(f) == recovered); LMDJ_CHECK(f.snapshot() == truth);
  LMDJ_CHECK(read(f.root / ".lmdj-workspace/attempts/baseline.json") == baseline_terminal);
  LMDJ_CHECK(read(f.root / (discard ? ".lmdj-workspace/attempts/baseline.json" : ".lmdj-workspace/attempts/first.json")) == terminal);
  // Discard retains all real output bytes; no tombstone-driven collection.
  const auto output = Json::parse(baseline_terminal).at("candidate_outputs")[0].at("artifact");
  LMDJ_CHECK(std::filesystem::exists(f.root / ".lmdj-workspace/attempts/baseline/artifacts" / output.at("sha256").get<std::string>()));
}
void cancellation_wins_over_live_success() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f, "baseline")));
  const auto before = job(f); const auto truth = f.snapshot(); f.app.reset();
  int ready[2], resume[2]; LMDJ_CHECK(pipe(ready) == 0 && pipe(resume) == 0);
  const auto child = fork(); LMDJ_CHECK(child >= 0);
  if (child == 0) {
    close(ready[0]); close(resume[1]); f.restart(); f.grant(); bool paused = false;
    f.storage->read_hook = [&](const auto& path) {
      if (paused || path != f.blob()) return;
      const auto raw = Json::parse(read(f.root / ".lmdj-host/candidates/state.json"));
      if (raw.at("jobs").at("slice").at("history").size() != 2) return;
      paused = true; char signal = 'r';
      if (::write(ready[1], &signal, 1) != 1 || ::read(resume[0], &signal, 1) != 1) _exit(98);
    };
    const auto result = f.app->command(job_request(f));
    _exit(result.at("ok") == true ? 63 : 99);
  }
  close(ready[1]); close(resume[0]); char signal = 0;
  LMDJ_CHECK(::read(ready[0], &signal, 1) == 1); f.restart();
  const auto cancelled = f.app->command({{"operation", "candidate.job.cancel"}, {"job_id", "slice"}, {"attempt_id", "first"}});
  LMDJ_CHECK(::write(resume[1], "r", 1) == 1); close(ready[0]); close(resume[1]); wait_exit(child, 63);
  ok(cancelled); const auto terminal = read(f.root / ".lmdj-workspace/attempts/first.json");
  f.restart(); const auto recovered = job(f);
  LMDJ_CHECK(recovered.at("sets") == before.at("sets"));
  LMDJ_CHECK(recovered.at("active_set_id") == before.at("active_set_id"));
  LMDJ_CHECK(recovered.at("history")[1].at("status") == "cancelled");
  LMDJ_CHECK(f.inspect("first").at("status") == "succeeded");
  LMDJ_CHECK(read(f.root / ".lmdj-workspace/attempts/first.json") == terminal);
  LMDJ_CHECK(f.snapshot() == truth);
}
void cross_process_eligibility_exclusion() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto before = job(f); const auto set = before.at("active_set_id").get<std::string>();
  f.app.reset(); int ready[2], resume[2]; LMDJ_CHECK(pipe(ready) == 0 && pipe(resume) == 0);
  const auto child = fork(); LMDJ_CHECK(child >= 0);
  if (child == 0) {
    close(ready[0]); close(resume[1]);
    lmdj::facade::detail::CandidateStore store(f.root, f.storage);
    lmdj::provider::AttemptStore attempts(f.root, {}, [] { return std::string{"test"}; });
    auto held = store.lease_active("slice", set, attempts);
    char signal = held.has_value() ? 'r' : 'f';
    if (::write(ready[1], &signal, 1) != 1 || ::read(resume[0], &signal, 1) != 1) _exit(98);
    _exit(0);
  }
  close(ready[1]); close(resume[0]); char signal = 0; LMDJ_CHECK(::read(ready[0], &signal, 1) == 1);
  lmdj::facade::detail::CandidateStore store(f.root, f.storage);
  const auto refused = store.discard("slice", set);
  LMDJ_CHECK(::write(resume[1], "r", 1) == 1); close(ready[0]); close(resume[1]); wait_exit(child, 0);
  LMDJ_CHECK(signal == 'r'); LMDJ_CHECK(!refused.has_value() && refused.error().details.at("reason") == "job_busy");
  LMDJ_CHECK(store.discard("slice", set).has_value());
  // Reverse order: a fresh process cannot acquire eligibility after tombstone.
  const auto reader = fork(); LMDJ_CHECK(reader >= 0);
  if (reader == 0) {
    lmdj::facade::detail::CandidateStore fresh(f.root, f.storage);
    lmdj::provider::AttemptStore attempts(f.root, {}, [] { return std::string{"test"}; });
    const auto denied = fresh.lease_active("slice", set, attempts);
    _exit(!denied.has_value() && denied.error().details.at("reason") == "candidate_unavailable" ? 0 : 99);
  }
  wait_exit(reader, 0); f.restart();
  LMDJ_CHECK(job(f).at("sets")[0].at("status") == "discarded");
}

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
  f.restart(); f.grant();
  if (boundary == 1) {
    // The child persisted its intent only after owning the SDK reservation.
    // A raw execution after its death cannot donate a new terminal to recovery.
    error(f.app->command(f.request("first")), "DUPLICATE_ID");
  }
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
  const auto raw_refused = f.app->command(f.request("first"));
  // Release the child before assertions, so a failed assertion cannot strand it.
  LMDJ_CHECK(::write(resume[1], "r", 1) == 1);
  close(ready[0]); close(resume[1]);
  int status = 0; LMDJ_CHECK(waitpid(child, &status, 0) == child);
  LMDJ_CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
  LMDJ_CHECK(pending.at("history")[0].at("status") == "pending");
  LMDJ_CHECK(pending.at("sets").empty());
  error(refused, "INVALID_ARGUMENT");
  error(raw_refused, "DUPLICATE_ID");
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
      for (int iteration = 0; iteration < 100; ++iteration) {
        live_job_is_not_recovered_or_reentered();
        cancellation_wins_over_live_success(); cross_process_eligibility_exclusion();
        adoption_excludes_discard_until_commit();
        retry_finishes_during_adoption(false); retry_finishes_during_adoption(true);
      }
      std::cout << "candidate process stress: PASS\n"; return 0;
    }
    LMDJ_CHECK(argc == 1);
    adoption_excludes_discard_until_commit();
    retry_finishes_during_adoption(false); retry_finishes_during_adoption(true);
    failed_retry_allows_prior_adoption();
    adoption_failure_releases_discard();
    for (int boundary : {1, 2, 3}) for (bool prior : {false, true}) crash_recovery(boundary, prior);
    interrupted_recovery_crash();
    for (bool discard : {false, true}) for (bool after : {false, true}) lifecycle_crash(discard, after);
    cancellation_wins_over_live_success(); cross_process_eligibility_exclusion();
    live_job_is_not_recovered_or_reentered();
    std::cout << "candidate process recovery: PASS\n";
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
