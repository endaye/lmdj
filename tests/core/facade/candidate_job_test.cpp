#include "tests/core/facade/candidate_fixture.hpp"

namespace {
void success_recipes_and_restart() {
  Fixture f; f.grant(); const auto before = f.snapshot();
  const auto response = f.app->command(job_request(f)); ok(response);
  const auto result = job(f);
  const auto& set = result.at("sets")[0];
  LMDJ_CHECK(set.at("set_id") == result.at("active_set_id"));
  const auto& recipes = set.at("recipes");
  LMDJ_CHECK(recipes.size() == 3);
  const std::vector<std::uint64_t> boundaries{0, 1, 3, 5};
  for (std::size_t i = 0; i < recipes.size(); ++i) {
    LMDJ_CHECK(recipes[i].at("start_frame") == boundaries[i]);
    LMDJ_CHECK(recipes[i].at("end_frame") == boundaries[i + 1]);
    LMDJ_CHECK(recipes[i].at("frame_rate") == 48000);
    LMDJ_CHECK(recipes[i].at("candidate_id") != set.at("sdk_candidate_id"));
  }
  LMDJ_CHECK(set.at("source").at("artifact") == f.source);
  LMDJ_CHECK(set.at("source").at("project_revision") == 1);
  const auto terminal = f.inspect("first");
  LMDJ_CHECK(set.at("output_artifact") == terminal.at("candidate_outputs")[0].at("artifact"));
  f.restart(); LMDJ_CHECK(job(f) == result);
  LMDJ_CHECK(f.inspect("first") == terminal);
  LMDJ_CHECK(f.snapshot() == before);
}
void failed_retry_retains_active() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto before = job(f); const auto truth = f.snapshot();
  auto failed = job_request(f, "failed"); failed["parameters"]["threshold_pcm16"] = 0;
  error(f.app->command(failed), "INVALID_ARGUMENT");
  const auto after = job(f);
  LMDJ_CHECK(after.at("active_set_id") == before.at("active_set_id"));
  LMDJ_CHECK(after.at("sets") == before.at("sets"));
  LMDJ_CHECK(after.at("history").size() == 2);
  LMDJ_CHECK(after.at("history")[1].at("status") == "failed");
  f.restart(); LMDJ_CHECK(job(f) == after); LMDJ_CHECK(f.snapshot() == truth);
}
void empty_success_supersedes() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  auto empty = job_request(f, "empty"); empty["parameters"]["threshold_pcm16"] = 32000;
  ok(f.app->command(empty));
  const auto after = job(f);
  LMDJ_CHECK(after.at("sets").size() == 2);
  LMDJ_CHECK(after.at("sets")[0].at("status") == "superseded");
  LMDJ_CHECK(after.at("sets")[1].at("status") == "active");
  LMDJ_CHECK(after.at("sets")[1].at("recipes").empty());
  LMDJ_CHECK(after.at("sets")[1].at("set_id") == after.at("active_set_id"));
  f.restart(); LMDJ_CHECK(job(f) == after);
}
void existing_terminal_cannot_be_attached() {
  Fixture f; f.grant(); ok(f.app->command(f.request("first")));
  const auto before = f.snapshot(); const auto terminal = f.inspect("first");
  error(f.app->command(job_request(f)), "DUPLICATE_ID");
  LMDJ_CHECK(!std::filesystem::exists(f.root / ".lmdj-host/candidates/state.json"));
  LMDJ_CHECK(f.inspect("first") == terminal); LMDJ_CHECK(f.snapshot() == before);
}
void corrupt_output_refuses_after_restart() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto terminal = f.inspect("first"); const auto truth = f.snapshot();
  const auto hash = terminal.at("candidate_outputs")[0].at("artifact").at("sha256").get<std::string>();
  const auto path = f.root / ".lmdj-workspace/attempts/first/artifacts" / hash;
  auto bytes = read(path); bytes[0] = 'x';
  { std::ofstream stream(path, std::ios::binary); stream << bytes; }
  f.restart();
  error(f.app->query({{"operation", "candidate.job.inspect"}, {"job_id", "slice"}}), "IO_ERROR");
  LMDJ_CHECK(f.inspect("first") == terminal); LMDJ_CHECK(f.snapshot() == truth);
}
void tampered_recipe_refuses() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto truth = f.snapshot();
  const auto path = f.root / ".lmdj-host/candidates/state.json";
  auto state = Json::parse(read(path));
  state["sets"].begin().value()["recipes"][0]["end_frame"] = 5;
  { std::ofstream stream(path); stream << state.dump(); }
  f.restart();
  error(f.app->query({{"operation", "candidate.job.inspect"}, {"job_id", "slice"}}), "INVALID_ARGUMENT");
  LMDJ_CHECK(f.snapshot() == truth);
}
void duplicate_state_key_refuses() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto truth = f.snapshot();
  const auto path = f.root / ".lmdj-host/candidates/state.json";
  auto bytes = read(path); bytes.insert(1, "\"format\":\"slice-candidate-store-v1\",");
  { std::ofstream stream(path); stream << bytes; }
  f.restart();
  error(f.app->query({{"operation", "candidate.job.inspect"}, {"job_id", "slice"}}), "INVALID_ARGUMENT");
  LMDJ_CHECK(f.snapshot() == truth);
}
void stale_revision_refuses_before_intent() {
  Fixture f; f.grant(); auto request = job_request(f); request["expected_revision"] = 0;
  const auto before = f.snapshot(); error(f.app->command(request), "REVISION_CONFLICT");
  LMDJ_CHECK(!std::filesystem::exists(f.root / ".lmdj-host/candidates/state.json"));
  LMDJ_CHECK(f.snapshot() == before);
}
void policy_refusal_precedes_source_reads() {
  for (const bool missing : {false, true}) for (const bool disallowed_region : {false, true}) {
    Fixture f;
    auto request = job_request(f);
    if (disallowed_region) { f.grant(); request["region"] = "remote"; }
    if (missing) std::filesystem::remove(f.blob());
    const auto before = f.snapshot();
    f.storage->owner_leases = 0; f.storage->owner_reads = 0;
    error(f.app->command(request), "PERMISSION_DENIED");
    LMDJ_CHECK(f.storage->owner_leases == 0);
    LMDJ_CHECK(f.storage->owner_reads == 0);
    LMDJ_CHECK(f.snapshot() == before);
  }
}
void analysis_preserves_interrupted_authoring_files() {
  for (const bool stale : {false, true}) {
    Fixture f; f.grant();
    write(f.project / "history/checkpoints/2.json", "{}\n");
    const auto before = f.snapshot();
    auto request = job_request(f);
    if (stale) request["expected_revision"] = 0;
    const auto response = f.app->command(request);
    if (stale) error(response, "REVISION_CONFLICT"); else ok(response);
    LMDJ_CHECK(f.snapshot() == before);
  }
}
void intent_reservation_excludes_raw_provider_collision() {
  Fixture f; f.grant(); ok(f.app->command(job_request(f)));
  const auto truth = f.snapshot(); const auto prior = job(f);
  bool collided = false;
  f.storage->replace_hook = [&](const auto& path, bool after) {
    if (collided || !after || path != f.root / ".lmdj-host/candidates/state.json") return;
    collided = true;
    error(f.app->command(f.request("second")), "DUPLICATE_ID");
  };
  ok(f.app->command(job_request(f, "second")));
  LMDJ_CHECK(collided);
  f.storage->replace_hook = {};
  const auto result = job(f);
  LMDJ_CHECK(result.at("history").size() == 2);
  LMDJ_CHECK(result.at("sets").size() == 2);
  LMDJ_CHECK(result.at("active_set_id") != prior.at("active_set_id"));
  LMDJ_CHECK(result.at("sets")[1].at("attempt_id") == "second");
  f.restart(); LMDJ_CHECK(job(f) == result);
  LMDJ_CHECK(f.snapshot() == truth);
}
}
int main() {
  try {
    success_recipes_and_restart(); failed_retry_retains_active(); empty_success_supersedes();
    stale_revision_refuses_before_intent();
    existing_terminal_cannot_be_attached();
    corrupt_output_refuses_after_restart(); tampered_recipe_refuses(); duplicate_state_key_refuses();
    policy_refusal_precedes_source_reads();
    analysis_preserves_interrupted_authoring_files();
    intent_reservation_excludes_raw_provider_collision();
    std::cout << "candidate Job integration: PASS\n";
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
