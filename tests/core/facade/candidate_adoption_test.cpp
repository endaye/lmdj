#include "tests/core/facade/candidate_fixture.hpp"
#include <lmdj/facade/candidate_store.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/cooker/wav_reader.hpp>
#include <lmdj/provider/attempt_store.hpp>

namespace {
using namespace lmdj;
constexpr auto adoption_id = "00000000-0000-4000-8000-000000000010";
Json analyze(Fixture& f) {
  f.grant();
  const auto result = f.app->command(job_request(f));
  ok(result);
  return result.at("result").at("sets").at(0);
}
Json request(const Fixture& f, const Json& set, std::uint64_t rev = 1) {
  return {{"operation", "candidate.adopt"}, {"project_path", f.project.generic_string()},
      {"project_id", project_id}, {"expected_revision", rev}, {"command_id", adoption_id},
      {"job_id", "slice"}, {"set_id", set.at("set_id")},
      {"selections", Json::array({{{"candidate_id", set.at("recipes").at(1).at("candidate_id")}, {"bank", 2}, {"pad", 4}},
          {{"candidate_id", set.at("recipes").at(1).at("candidate_id")}, {"bank", 0}, {"pad", 3}}})}};
}
domain::ProjectState state(Fixture& f) {
  ProjectStore store;
  const auto result = store.load(f.project);
  if (!result.has_value()) throw std::runtime_error(result.error().message);
  return result.value();
}
void unchanged(Fixture& f, const domain::ProjectState& before) {
  LMDJ_CHECK(state(f) == before);
  f.restart();
  LMDJ_CHECK(state(f) == before);
}
void success_and_reopen() {
  Fixture f;
  const auto set = analyze(f);
  const auto index = read(f.root / ".lmdj-host/candidates/state.json");
  const auto before = state(f);
  const auto result = f.app->command(request(f, set));
  ok(result);
  LMDJ_CHECK(result.at("project_revision") == 2);
  const auto adopted = result.at("result").at("adopted");
  LMDJ_CHECK(adopted.size() == 2);
  LMDJ_CHECK(adopted.at(0).at("bank") == 0 && adopted.at(1).at("bank") == 2);
  LMDJ_CHECK(adopted.at(0).at("asset_id") != adopted.at(1).at("asset_id"));
  const auto committed = state(f);
  LMDJ_CHECK(committed.revision == before.revision + 1);
  LMDJ_CHECK(committed.assets.size() == before.assets.size() + 2);
  LMDJ_CHECK(committed.assets.at(AssetId{asset_id}) == before.assets.at(AssetId{asset_id}));
  LMDJ_CHECK(read(f.blob()) == wav());
  ProjectStore store;
  for (const auto& target : adopted) {
    const auto id = AssetId{target.at("asset_id").get<std::string>()};
    LMDJ_CHECK(committed.banks.at(target.at("bank").get<std::size_t>()).at(target.at("pad").get<std::size_t>()).asset_id == id);
    const auto& asset = committed.assets.at(id);
    const auto artifact = store.read_artifact(f.project, asset.artifact);
    LMDJ_CHECK(artifact.has_value());
    LMDJ_CHECK(asset.artifact.byte_length == 48);
    LMDJ_CHECK(asset.artifact.media_type == "audio/wav");
    const auto described = foundation::describe_artifact(f.project / "assets" / (asset.artifact.sha256 + ".wav"), "audio/wav");
    LMDJ_CHECK(described.has_value() && described.value() == asset.artifact);
    const auto decoded = cooker::decode_wav(artifact.value());
    LMDJ_CHECK(decoded.has_value());
    LMDJ_CHECK(decoded.value()->sample_rate == 48000 && decoded.value()->channels == 1);
    LMDJ_CHECK(decoded.value()->interleaved == (std::vector<std::int16_t>{5000, 0}));
    const auto lineage = domain::asset_lineage_json(*asset.lineage);
    LMDJ_CHECK(lineage.at("source") == (Json{{"kind", "asset_artifact"},
        {"artifact_sha256", f.source.at("sha256")}, {"project_revision", 1}}));
    auto recipe = set.at("recipes").at(1); recipe.erase("candidate_id");
    LMDJ_CHECK(lineage.at("derivation") == (Json{{"kind", "capability_adoption"},
        {"capability", set.at("capability")}, {"provider", set.at("provider")},
        {"model_identity", nullptr}, {"parameters_sha256", set.at("parameters_sha256")},
        {"attempt_id", set.at("attempt_id")}, {"source_asset_id", asset_id},
        {"output_artifact", set.at("output_artifact")}, {"recipe", recipe}}));
  }
  f.restart();
  LMDJ_CHECK(state(f) == committed);
  LMDJ_CHECK(read(f.root / ".lmdj-host/candidates/state.json") == index);
  error(f.app->command(request(f, set)), "REVISION_CONFLICT");
  LMDJ_CHECK(state(f) == committed);
  auto again = request(f, set, 2); again["command_id"] = other_id;
  ok(f.app->command(again));
  const auto repeated = state(f);
  LMDJ_CHECK(repeated.revision == 3 && repeated.assets.size() == 5);
  f.restart(); LMDJ_CHECK(state(f) == repeated);
}
void strict_selections() {
  Fixture f;
  const auto set = analyze(f);
  const auto before = state(f);
  auto good = request(f, set);
  for (int shape = 0; shape < 8; ++shape) {
    auto bad = good;
    if (shape == 0) bad["selections"] = Json::array();
    if (shape == 1) bad["selections"][1] = bad["selections"][0];
    if (shape == 2) bad["selections"][1].erase("pad");
    if (shape == 3) bad["selections"][1]["bank"] = 4;
    if (shape == 4) bad["selections"][1]["pad"] = 16;
    if (shape == 5) bad["selections"][1]["set_id"] = set.at("set_id");
    if (shape == 6) bad.erase("expected_revision");
    if (shape == 7) bad["automatic_fill"] = true;
    error(f.app->command(bad), "INVALID_ARGUMENT");
    LMDJ_CHECK(state(f) == before);
  }
  for (const auto* unknown : {"unknown", "other-set.0"}) {
    auto bad = good; bad["selections"][1]["candidate_id"] = unknown;
    const auto result = f.app->command(bad);
    error(result, "NOT_FOUND");
    LMDJ_CHECK(result.at("error").at("details").at("reason") == "candidate_unavailable");
    LMDJ_CHECK(state(f) == before);
  }
  auto wrong_set = good; wrong_set["set_id"] = "missing";
  error(f.app->command(wrong_set), "NOT_FOUND");
  unchanged(f, before);
}
void early_freshness_and_unrelated_edit() {
  Fixture f;
  const auto set = analyze(f);
  const auto before = state(f);
  std::size_t reads = 0;
  f.storage->read_hook = [&](const auto& p) { if (p == f.blob()) ++reads; };
  auto stale = request(f, set); stale["expected_revision"] = 0;
  error(f.app->command(stale), "REVISION_CONFLICT");
  auto wrong = request(f, set); wrong["project_id"] = other_id;
  error(f.app->command(wrong), "REVISION_CONFLICT");
  LMDJ_CHECK(reads == 0);
  f.storage->read_hook = {};
  LMDJ_CHECK(state(f) == before);
  ProjectStore store;
  const auto edited = store.execute(f.project, domain::Command{domain::UpdateSequenceSettings{
      {CommandId{other_id}, 1}, 125, std::nullopt, std::nullopt}});
  LMDJ_CHECK(edited.has_value());
  ok(f.app->command(request(f, set, 2)));
  const auto after = state(f);
  LMDJ_CHECK(after.revision == 3 && after.bpm == 125);
  for (const auto& [id, asset] : after.assets) {
    if (id == AssetId{asset_id}) continue;
    LMDJ_CHECK(std::get<domain::AssetArtifactLineageSource>(asset.lineage->source).project_revision == 1);
  }
  f.restart(); LMDJ_CHECK(state(f) == after);
}
void quota(bool bank) {
  Fixture f;
  const auto set = analyze(f);
  f.limits = audio::RuntimePreparationLimits{16777216, bank ? 12U : 100U, bank ? 100U : 12U, 100};
  f.restart();
  auto cmd = request(f, set);
  if (bank) cmd["selections"][0]["bank"] = 0;
  const auto before = state(f);
  const auto result = f.app->command(cmd);
  error(result, bank ? "BANK_QUOTA_EXHAUSTED" : "PROJECT_QUOTA_EXHAUSTED");
  unchanged(f, before);
  // Each interval costs 8 bytes. One fits; two copies must cost 16, not 8.
  cmd["selections"].erase(cmd["selections"].begin());
  ok(f.app->command(cmd));
  LMDJ_CHECK(state(f).revision == 2);
}
void replacement_charges() {
  Fixture f;
  const auto set = analyze(f);
  ProjectStore store;
  LMDJ_CHECK(store.execute(f.project, domain::Command{domain::AssignPad{
      {CommandId{other_id}, 1}, {0, 3}, AssetId{asset_id}}}).has_value());
  LMDJ_CHECK(store.execute(f.project, domain::Command{domain::AssignPad{
      {CommandId{"00000000-0000-4000-8000-000000000098"}, 2}, {2, 4}, AssetId{asset_id}}}).has_value());
  // Old targets cost 40 together; final two selected targets cost only 16.
  f.limits = audio::RuntimePreparationLimits{16777216, 8, 16, 100}; f.restart();
  ok(f.app->command(request(f, set, 3)));
  const auto committed = state(f);
  LMDJ_CHECK(committed.revision == 4);
  f.restart(); LMDJ_CHECK(state(f) == committed);
}
void preparation_failure() {
  Fixture f;
  const auto set = analyze(f);
  f.limits = audio::RuntimePreparationLimits{47, 100, 100, 100}; f.restart();
  const auto before = state(f);
  error(f.app->command(request(f, set)), "INVALID_ARGUMENT");
  unchanged(f, before);
}
void unavailable_bytes() {
  for (bool corrupt : {false, true}) {
    Fixture f;
    const auto set = analyze(f);
    const auto before = state(f);
    if (corrupt) write(f.blob(), "corrupt"); else std::filesystem::remove(f.blob());
    const auto result = f.app->command(request(f, set));
    LMDJ_CHECK(result.at("ok") == false);
    ProjectStore store;
    const auto inspected = store.inspect_committed(f.project);
    LMDJ_CHECK(inspected.has_value() && inspected.value() == before);
    f.restart();
    const auto reopened = store.inspect_committed(f.project);
    LMDJ_CHECK(reopened.has_value() && reopened.value() == before);
    // Restoring unavailable media proves the retained Truth still reopens.
    write(f.blob(), wav());
    LMDJ_CHECK(state(f) == before);
  }
}
void source_binding_replaced() {
  for (bool missing : {false, true}) {
    Fixture f;
    const auto set = analyze(f);
    std::filesystem::remove_all(f.project);
    ProjectStore store;
    LMDJ_CHECK(store.create(f.project, domain::create_project(ProjectId{project_id}, 120).value()).has_value());
    auto bytes = wav(); bytes.back() = 1;
    LMDJ_CHECK(store.import_artifact_bytes(f.project, {{CommandId{other_id}, 0},
        AssetId{missing ? other_id : asset_id}, "audio/wav", std::as_bytes(std::span{bytes.data(), bytes.size()})}).has_value());
    const auto before = state(f);
    const auto result = f.app->command(request(f, set));
    error(result, missing ? "NOT_FOUND" : "REVISION_CONFLICT");
    LMDJ_CHECK(result.at("error").at("details").at("reason") ==
        (missing ? "source_asset_missing" : "candidate_source_changed"));
    unchanged(f, before);
  }
}
void save_failure_and_lease_unwind() {
  Fixture f;
  const auto set = analyze(f);
  const auto before = state(f);
  bool failed = false;
  f.storage->fail_replace = [&](const auto& p) {
    if (p == f.project / "manifest.json") { failed = true; return true; } return false;
  };
  error(f.app->command(request(f, set)), "IO_ERROR");
  LMDJ_CHECK(failed); f.storage->fail_replace = {};
  unchanged(f, before);
  ok(f.app->command(request(f, set)));
  LMDJ_CHECK(state(f).revision == 2);
}
void eligibility_and_project_writer_race() {
  Fixture f;
  const auto set = analyze(f);
  const auto before = state(f);
  facade::detail::CandidateStore owner(f.root, f.storage);
  provider::AttemptStore attempts(f.root, {}, [] { return "2026-09-10T00:00:00Z"; });
  bool owner_held_at_materialization = false;
  bool owner_held_at_commit = false;
  f.storage->read_hook = [&](const auto& p) {
    if (p == f.blob()) {
      const auto lease = owner.lease_active("slice", set.at("set_id").get<std::string>(), attempts);
      LMDJ_CHECK(!lease.has_value()); owner_held_at_materialization = true;
    }
  };
  f.storage->replace_hook = [&](const auto& p, bool after) {
    if (p == f.project / "manifest.json" && !after) {
      const auto lease = owner.lease_active("slice", set.at("set_id").get<std::string>(), attempts);
      LMDJ_CHECK(!lease.has_value()); owner_held_at_commit = true;
    }
  };
  ok(f.app->command(request(f, set)));
  LMDJ_CHECK(owner_held_at_materialization && owner_held_at_commit);
  f.storage->read_hook = {}; f.storage->replace_hook = {};
  LMDJ_CHECK(owner.lease_active("slice", set.at("set_id").get<std::string>(), attempts).has_value());
  LMDJ_CHECK(state(f).revision == before.revision + 1);
}
void eligibility_is_pure_and_exclusive() {
  Fixture f;
  const auto set = analyze(f);
  facade::detail::CandidateStore owner(f.root, f.storage);
  provider::AttemptStore attempts(f.root, {}, [] { return "2026-09-10T00:00:00Z"; });
  auto intent = job(f).at("history").at(0).at("intent");
  intent["attempt_id"] = "pending";
  auto run = owner.begin("slice", intent);
  LMDJ_CHECK(run.has_value());
  const auto owner_file = f.root / ".lmdj-host/candidates/state.json";
  const auto pending = read(owner_file);
  {
    auto leased = owner.lease_active("slice", set.at("set_id").get<std::string>(), attempts);
    LMDJ_CHECK(leased.has_value());
    LMDJ_CHECK(leased.value().candidate_set == set);
    LMDJ_CHECK(read(owner_file) == pending);
    const auto competing = owner.lease_active("slice", set.at("set_id").get<std::string>(), attempts);
    LMDJ_CHECK(!competing.has_value());
    LMDJ_CHECK(competing.error().details.at("reason") == "job_busy");
  }
  LMDJ_CHECK(owner.lease_active("slice", set.at("set_id").get<std::string>(), attempts).has_value());
  LMDJ_CHECK(read(owner_file) == pending);
}
void empty_and_superseded_sets() {
  auto silent = wav();
  for (std::size_t i = 44; i < silent.size(); ++i) silent[i] = 0;
  Fixture empty(silent);
  const auto empty_set = analyze(empty);
  LMDJ_CHECK(empty_set.at("recipes").empty());
  Json unavailable{{"operation", "candidate.adopt"}, {"project_path", empty.project.generic_string()},
      {"project_id", project_id}, {"expected_revision", 1}, {"command_id", adoption_id},
      {"job_id", "slice"}, {"set_id", empty_set.at("set_id")},
      {"selections", Json::array({{{"candidate_id", "missing"}, {"bank", 0}, {"pad", 0}}})}};
  const auto original = state(empty);
  error(empty.app->command(unavailable), "NOT_FOUND");
  unchanged(empty, original);
  Fixture f;
  const auto old = analyze(f);
  ok(f.app->command(job_request(f, "second")));
  const auto before = state(f);
  error(f.app->command(request(f, old)), "NOT_FOUND");
  unchanged(f, before);
  const auto current = job(f).at("sets").at(1);
  ok(f.app->command(request(f, current)));
  LMDJ_CHECK(state(f).revision == 2);
}
void relocated_project() {
  Fixture f;
  const auto set = analyze(f);
  const auto relocated = f.root / "relocated.lmdj";
  std::filesystem::rename(f.project, relocated);
  f.project = relocated; f.storage->owner = relocated;
  ok(f.app->command(request(f, set)));
  const auto after = state(f);
  f.restart(); LMDJ_CHECK(state(f) == after && after.revision == 2);
}
void commit_rechecks_freshness() {
  for (bool corrupt_bytes : {false, true}) {
    Fixture f;
    const auto set = analyze(f);
    bool read_source = false;
    bool raced = false;
    auto expected = state(f);
    f.storage->read_hook = [&](const auto& p) { if (p == f.blob()) read_source = true; };
    f.storage->acquire_hook = [&](const auto& p) {
      if (p != f.project || !read_source || raced) return;
      raced = true;
      if (corrupt_bytes) { write(f.blob(), "corrupt"); return; }
      ProjectStore rival;
      const auto edited = rival.execute(f.project, domain::Command{domain::UpdateSequenceSettings{
          {CommandId{other_id}, 1}, 130, std::nullopt, std::nullopt}});
      LMDJ_CHECK(edited.has_value()); expected = edited.value().state;
    };
    const auto result = f.app->command(request(f, set));
    LMDJ_CHECK(raced);
    LMDJ_CHECK(result.at("ok") == false);
    if (!corrupt_bytes) error(result, "REVISION_CONFLICT");
    f.storage->read_hook = {}; f.storage->acquire_hook = {};
    if (corrupt_bytes) write(f.blob(), wav());
    unchanged(f, expected);
  }
}
void second_artifact_failure_is_atomic() {
  Fixture f;
  const auto set = analyze(f);
  auto cmd = request(f, set);
  cmd["selections"][0]["candidate_id"] = set.at("recipes").at(2).at("candidate_id");
  const auto before = state(f);
  std::size_t artifacts = 0;
  f.storage->fail_create = [&](const auto& p) {
    return p.parent_path() == f.project / "assets" && ++artifacts == 2;
  };
  error(f.app->command(cmd), "IO_ERROR");
  LMDJ_CHECK(artifacts == 2);
  f.storage->fail_create = {};
  unchanged(f, before);
  LMDJ_CHECK(std::distance(std::filesystem::directory_iterator(f.project / "assets"), {}) == 1);
  ok(f.app->command(cmd));
  LMDJ_CHECK(state(f).revision == 2);
}

void ordering_is_deterministic() {
  Fixture f;
  const auto set = analyze(f);
  const auto clone = f.root / "clone.lmdj";
  std::filesystem::copy(f.project, clone, std::filesystem::copy_options::recursive);
  auto normal = request(f, set);
  auto reversed = normal;
  reversed["project_path"] = clone.generic_string();
  std::reverse(reversed["selections"].begin(), reversed["selections"].end());
  const auto first = f.app->command(normal); ok(first);
  const auto second = f.app->command(reversed); ok(second);
  LMDJ_CHECK(first == second);
  ProjectStore store;
  const auto cloned = store.load(clone);
  LMDJ_CHECK(cloned.has_value() && cloned.value() == state(f));
}
void unavailable_terminal_and_output() {
  for (int unavailable = 0; unavailable != 3; ++unavailable) {
    Fixture f;
    const auto set = analyze(f);
    const auto before = state(f);
    const auto attempt = f.root / ".lmdj-workspace/attempts/first";
    const auto artifact = attempt / "artifacts" / set.at("output_artifact").at("sha256").get<std::string>();
    if (unavailable == 0) std::filesystem::remove(artifact);
    if (unavailable == 1) write(artifact, "corrupt");
    if (unavailable == 2) {
      // Remove the recorded Attempt evidence, never discover a substitute blob.
      std::filesystem::remove_all(attempt);
    }
    const auto result = f.app->command(request(f, set));
    LMDJ_CHECK(result.at("ok") == false);
    unchanged(f, before);
  }
}

void preparation_uses_profile_frames() {
  for (const std::uint32_t rate : {44100U, 48000U}) {
    for (const std::uint16_t channels : {std::uint16_t{1}, std::uint16_t{2}}) {
      std::string audio = "RIFF";
      little(audio, 36U + 10U * channels, 4); audio += "WAVEfmt ";
      little(audio, 16, 4); little(audio, 1, 2); little(audio, channels, 2);
      little(audio, rate, 4); little(audio, rate * channels * 2U, 4);
      little(audio, channels * 2U, 2); little(audio, 16, 2);
      audio += "data"; little(audio, 10U * channels, 4);
      for (int sample : {0, 5000, 0, 8000, 0})
        for (std::uint16_t channel = 0; channel < channels; ++channel)
          little(audio, static_cast<std::uint16_t>(sample), 2);
      Fixture f(audio);
      const auto set = analyze(f);
      const std::uint64_t per_pad = rate == 44100 ? 12 : 8;
      f.limits = audio::RuntimePreparationLimits{16777216, per_pad, per_pad * 2, 100};
      f.restart();
      const auto result = f.app->command(request(f, set)); ok(result);
      const auto after = state(f);
      for (const auto& target : result.at("result").at("adopted")) {
        const auto& asset = after.assets.at(AssetId{target.at("asset_id").get<std::string>()});
        LMDJ_CHECK(asset.artifact.byte_length == 44U + 4U * channels);
        ProjectStore store;
        const auto bytes = store.read_artifact(f.project, asset.artifact);
        LMDJ_CHECK(bytes.has_value());
        const auto pcm = cooker::decode_wav(bytes.value());
        LMDJ_CHECK(pcm.has_value());
        LMDJ_CHECK(pcm.value()->sample_rate == rate && pcm.value()->channels == channels);
        LMDJ_CHECK(pcm.value()->interleaved == (channels == 1
            ? std::vector<std::int16_t>{5000, 0}
            : std::vector<std::int16_t>{5000, 5000, 0, 0}));
        LMDJ_CHECK(std::get<domain::CapabilityAdoptionLineageDerivation>(asset.lineage->derivation).recipe.frame_rate == rate);
      }
      f.restart(); LMDJ_CHECK(state(f) == after);
      // Replacement must charge the resampled 48 kHz frame count, not raw frames.
      f.limits->maximum_generation_bytes = per_pad * 2 - 1; f.restart();
      auto next = request(f, set, 2); next["command_id"] = other_id;
      error(f.app->command(next), "PROJECT_QUOTA_EXHAUSTED");
      LMDJ_CHECK(state(f) == after);
    }
  }
}

void active_session_refuses_adoption() {
  Fixture f;
  const auto set = analyze(f);
  ok(f.app->command({{"operation", "pattern.create"}, {"project_path", f.project.generic_string()},
      {"command_id", other_id}, {"expected_revision", 1}, {"pattern_id", other_id}, {"bars", 1}}));
  ok(f.app->command({{"operation", "sequence.record.begin"}, {"project_path", f.project.generic_string()},
      {"session_id", adoption_id}, {"pattern_id", other_id}, {"expected_revision", 2}, {"runtime_frame", 0}}));
  const auto before = state(f);
  const auto result = f.app->command(request(f, set, 2));
  error(result, "INVALID_ARGUMENT");
  LMDJ_CHECK(result.at("error").at("details").at("reason") == "sequence_session_active");
  LMDJ_CHECK(state(f) == before);
}

}
int main() {
  try {
    success_and_reopen(); strict_selections(); early_freshness_and_unrelated_edit();
    quota(true); quota(false); replacement_charges(); preparation_failure();
    unavailable_bytes(); source_binding_replaced(); save_failure_and_lease_unwind();
    eligibility_and_project_writer_race(); eligibility_is_pure_and_exclusive();
    empty_and_superseded_sets(); relocated_project(); commit_rechecks_freshness();
    second_artifact_failure_is_atomic(); ordering_is_deterministic();
    unavailable_terminal_and_output(); preparation_uses_profile_frames();
    active_session_refuses_adoption();
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
  std::cout << "candidate adoption Facade: PASS\n";
}
