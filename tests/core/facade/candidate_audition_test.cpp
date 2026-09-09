#include <algorithm>
#include "tests/core/facade/candidate_fixture.hpp"
#include <lmdj/project_io/project_store.hpp>

namespace {
using namespace lmdj;

Json analyze(Fixture& f) {
  f.grant();
  const auto response = f.app->command(job_request(f));
  ok(response);
  return response.at("result").at("sets").at(0);
}
Json request(const Fixture& f, const Json& set, std::uint64_t revision = 1) {
  return {{"operation", "candidate.audition"}, {"project_path", f.project.generic_string()},
      {"project_id", project_id}, {"expected_revision", revision}, {"job_id", "slice"},
      {"set_id", set.at("set_id")}, {"candidate_id", set.at("recipes").at(1).at("candidate_id")}};
}
facade::CandidateAuditionRequest typed(const Json& value) {
  return {value.at("project_path").get<std::string>(),
      ProjectId{value.at("project_id").get<std::string>()},
      value.at("expected_revision").get<std::uint64_t>(), value.at("job_id").get<std::string>(),
      value.at("set_id").get<std::string>(), value.at("candidate_id").get<std::string>()};
}
auto files(const Fixture& f) {
  std::map<std::string, std::string> result;
  for (const auto& entry : std::filesystem::recursive_directory_iterator(f.root)) {
    const auto key = entry.path().lexically_relative(f.root).generic_string();
    if (entry.is_regular_file()) result.emplace(key, read(entry.path()));
    else if (entry.is_directory()) result.emplace(key + "/", "");
  }
  return result;
}
domain::ProjectState state(const Fixture& f) {
  ProjectStore store;
  const auto inspected = store.inspect_committed(f.project);
  LMDJ_CHECK(inspected.has_value());
  return inspected.value();
}
// Include the entire Workspace (terminal, index, blobs and directories), not
// just a projected revision. These reads deliberately do not recover a bundle.
void readonly(Fixture& f, const std::function<void()>& action) {
  const auto truth = state(f);
  const auto before = files(f);
  const auto writes = f.storage->writes;
  action();
  LMDJ_CHECK(f.storage->writes == writes);
  LMDJ_CHECK(state(f) == truth);
  LMDJ_CHECK(files(f) == before);
}
void refusal(Fixture& f, const Json& value, std::string_view code,
             std::string_view reason = {}) {
  for (bool reopen : {false, true}) {
    if (reopen) f.restart();
    readonly(f, [&] {
      const auto response = f.app->query(value);
      error(response, code);
      if (!reason.empty()) LMDJ_CHECK(response.at("error").at("details").at("reason") == reason);
    });
  }
}
std::string profile(std::uint32_t rate, std::uint16_t channels) {
  std::string bytes = "RIFF";
  little(bytes, 36U + 10U * channels, 4); bytes += "WAVEfmt ";
  little(bytes, 16, 4); little(bytes, 1, 2); little(bytes, channels, 2);
  little(bytes, rate, 4); little(bytes, rate * channels * 2U, 4);
  little(bytes, channels * 2U, 2); little(bytes, 16, 2);
  bytes += "data"; little(bytes, 10U * channels, 4);
  for (int sample : {0, 5000, 0, 8000, 0}) {
    for (std::uint16_t channel = 0; channel < channels; ++channel)
      little(bytes, static_cast<std::uint16_t>(channel == 0 ? sample : -sample), 2);
  }
  return bytes;
}
void exact_pcm_and_resampling() {
  for (const auto rate : {44100U, 48000U}) {
    for (const auto channels : {std::uint16_t{1}, std::uint16_t{2}}) {
      Fixture f(profile(rate, channels));
      const auto set = analyze(f);
      const auto value = request(f, set);
      for (bool reopen : {false, true}) {
        if (reopen) f.restart();
        readonly(f, [&] {
          const auto audio = f.app->audition_candidate(typed(value));
          LMDJ_CHECK(audio.has_value());
          LMDJ_CHECK(audio.value().sample_rate == rate);
          LMDJ_CHECK(audio.value().channels == channels && audio.value().source_frames == 2);
          LMDJ_CHECK(audio.value().prepared && audio.value().prepared->sample_rate == 48000);
          LMDJ_CHECK(audio.value().prepared->channels == channels);
          // Linear 44.1 -> 48 kHz: frame 1 is 5000 * 3900 / 48000,
          // symmetrically rounded to 406; the final source frame is held.
          const std::vector<std::int16_t> mono = rate == 44100
              ? std::vector<std::int16_t>{5000, 406, 0}
              : std::vector<std::int16_t>{5000, 0};
          std::vector<std::int16_t> expected;
          for (const auto sample : mono) {
            expected.push_back(sample);
            if (channels == 2) expected.push_back(static_cast<std::int16_t>(-sample));
          }
          LMDJ_CHECK(audio.value().prepared->interleaved == expected);
          LMDJ_CHECK(audio.value().artifact.media_type == "audio/wav");
          LMDJ_CHECK(audio.value().artifact.byte_length == 44U + 4U * channels);
          const auto digest = rate == 44100
              ? (channels == 1 ? "13618b6a06c7d761a592d0c46525a3a63e3907028148860554b2c1fc800cb1c1"
                               : "d1b9a8a62c7ca3530716cfe9561494906d7d246160cd3dcb01f7e525f359a98f")
              : (channels == 1 ? "4b5ce0312aae827d22af4f7866d1bd1f0972f7feca0feb0c3deeaa1b43f3246f"
                               : "6e106c46ee731d12427def214ef2019ce5bc48d0bbeca1a4bd65320e21cf95a1");
          LMDJ_CHECK(audio.value().artifact.sha256 == digest);
          const auto metadata = f.app->query(value); ok(metadata);
          LMDJ_CHECK(metadata.at("project_revision") == 1);
          LMDJ_CHECK(metadata.at("result") == Json({{"job_id", "slice"}, {"set_id", set.at("set_id")},
              {"candidate_id", value.at("candidate_id")}, {"artifact", audio.value().artifact},
              {"sample_rate", rate}, {"channels", channels}, {"source_frames", 2}}));
          const auto repeated = f.app->audition_candidate(typed(value));
          LMDJ_CHECK(repeated.has_value());
          LMDJ_CHECK(repeated.value().artifact == audio.value().artifact);
          LMDJ_CHECK(repeated.value().prepared->interleaved == expected);
        });
      }
    }
  }
}
void pattern_and_unrelated_revision() {
  Fixture f;
  const auto set = analyze(f);
  ProjectStore store;
  LMDJ_CHECK(store.execute(f.project, domain::Command{domain::AssignPad{
      {CommandId{other_id}, 1}, {2, 3}, AssetId{asset_id}}}).has_value());
  LMDJ_CHECK(store.execute(f.project, domain::Command{domain::CreatePattern{
      {CommandId{"00000000-0000-4000-8000-000000000098"}, 2},
      {PatternId{other_id}, 1, {{{2, 3}, 0, 120, 100}, {{0, 4}, 240, 120, 80}}}}}).has_value());
  const auto truth = state(f);
  LMDJ_CHECK(!truth.patterns.at(PatternId{other_id}).events.empty());
  const auto before = files(f);
  refusal(f, request(f, set), "REVISION_CONFLICT");
  for (bool reopen : {false, true}) {
    if (reopen) f.restart();
    readonly(f, [&] { ok(f.app->query(request(f, set, 3))); });
    LMDJ_CHECK(state(f) == truth && files(f) == before);
  }
}
void strict_query() {
  Fixture f;
  const auto set = analyze(f);
  const auto valid = request(f, set);
  for (const auto& [key, value] : valid.items()) {
    (void)value;
    auto missing = valid; missing.erase(key);
    refusal(f, missing, "INVALID_ARGUMENT");
  }
  auto extra = valid; extra["played"] = true;
  refusal(f, extra, "INVALID_ARGUMENT");
  for (const auto& invalid : {Json(-1), Json(true), Json(1.5), Json("1")}) {
    auto changed = valid; changed["expected_revision"] = invalid;
    refusal(f, changed, "INVALID_ARGUMENT");
  }
  for (const auto* key : {"job_id", "set_id", "candidate_id", "project_id", "project_path"}) {
    auto changed = valid; changed[key] = "../invalid";
    refusal(f, changed, "INVALID_ARGUMENT");
  }
  readonly(f, [&] {
    error(f.app->command(valid), "INVALID_ARGUMENT");
    auto invalid = typed(valid); invalid.job_id = "../invalid";
    const auto result = f.app->audition_candidate(invalid);
    LMDJ_CHECK(!result.has_value() && result.error().code == ErrorCode::invalid_argument);
  });
}
void unknown_and_lifecycle() {
  for (const auto* key : {"job_id", "set_id", "candidate_id"}) {
    Fixture f;
    auto value = request(f, analyze(f)); value[key] = "unknown";
    refusal(f, value, "NOT_FOUND", "candidate_unavailable");
  }
  for (bool supersede : {false, true}) {
    Fixture f;
    const auto set = analyze(f);
    const auto value = request(f, set);
    if (supersede) ok(f.app->command(job_request(f, "second")));
    else ok(f.app->command({{"operation", "candidate.set.discard"}, {"job_id", "slice"},
                           {"set_id", set.at("set_id")}}));
    refusal(f, value, "NOT_FOUND", "candidate_unavailable");
  }
}
void source_identity_refusals() {
  Fixture f;
  auto value = request(f, analyze(f)); value["project_id"] = other_id;
  refusal(f, value, "REVISION_CONFLICT");
  for (bool missing : {false, true}) {
    Fixture changed;
    const auto selected = request(changed, analyze(changed));
    std::filesystem::remove_all(changed.project);
    ProjectStore store;
    LMDJ_CHECK(store.create(changed.project,
        domain::create_project(ProjectId{project_id}, 120).value()).has_value());
    auto bytes = wav(); bytes.back() = 1;
    LMDJ_CHECK(store.import_artifact_bytes(changed.project, {{CommandId{other_id}, 0},
        AssetId{missing ? other_id : asset_id}, "audio/wav",
        std::as_bytes(std::span{bytes.data(), bytes.size()})}).has_value());
    refusal(changed, selected, missing ? "NOT_FOUND" : "REVISION_CONFLICT",
        missing ? "source_asset_missing" : "candidate_source_changed");
  }
}
void unavailable_bytes() {
  for (int target = 0; target != 3; ++target) {
    for (bool corrupt : {false, true}) {
      Fixture f;
      const auto set = analyze(f);
      const auto value = request(f, set);
      const auto attempts = f.root / ".lmdj-workspace/attempts";
      const auto path = target == 0 ? f.blob() : target == 1
          ? attempts / "first" / "artifacts" / set.at("output_artifact").at("sha256").get<std::string>()
          : attempts / "first.json";
      if (corrupt) write(path, "corrupt"); else std::filesystem::remove(path);
      for (bool reopen : {false, true}) {
        if (reopen) f.restart();
        readonly(f, [&] {
          const auto response = f.app->query(value);
          LMDJ_CHECK(response.at("ok") == false);
          LMDJ_CHECK(response.at("error").at("code") != "INTERNAL_ERROR");
        });
      }
    }
  }
}
void tampered_recipe() {
  Fixture f;
  const auto value = request(f, analyze(f));
  const auto path = f.root / ".lmdj-host/candidates/state.json";
  auto index = Json::parse(read(path));
  index["sets"][value.at("set_id").get<std::string>()]["recipes"][1]["end_frame"] = 5;
  write(path, index.dump());
  refusal(f, value, "INVALID_ARGUMENT", "candidate_state_invalid");
}
void preparation_limit() {
  Fixture f;
  const auto value = request(f, analyze(f));
  f.limits = audio::RuntimePreparationLimits{47, 100, 100, 100}; f.restart();
  refusal(f, value, "INVALID_ARGUMENT");
}
void empty_result_and_invalid_profile() {
  auto silence = wav();
  std::fill(silence.begin() + 44, silence.end(), '\0');
  Fixture empty(silence);
  const auto set = analyze(empty);
  LMDJ_CHECK(set.at("recipes").empty());
  const Json empty_request{{"operation", "candidate.audition"},
      {"project_path", empty.project.generic_string()}, {"project_id", project_id},
      {"expected_revision", 1}, {"job_id", "slice"}, {"set_id", set.at("set_id")},
      {"candidate_id", "unknown"}};
  refusal(empty, empty_request, "NOT_FOUND", "candidate_unavailable");

  auto unsupported = wav(); unsupported[20] = 3; // IEEE float is outside PCM16.
  Fixture invalid(unsupported); invalid.grant();
  error(invalid.app->command(job_request(invalid)), "UNSUPPORTED_AUDIO");
  auto missing = empty_request; missing["project_path"] = invalid.project.generic_string();
  // The real analysis path cannot publish an auditionable recipe for this profile.
  refusal(invalid, missing, "NOT_FOUND", "candidate_unavailable");
}
void interval_boundaries() {
  Fixture f;
  const auto set = analyze(f);
  const std::vector<std::vector<std::int16_t>> expected{{0}, {5000, 0}, {8000, 0}};
  LMDJ_CHECK(set.at("recipes").size() == expected.size());
  for (std::size_t index = 0; index < expected.size(); ++index) {
    auto value = request(f, set);
    value["candidate_id"] = set.at("recipes").at(index).at("candidate_id");
    readonly(f, [&] {
      const auto result = f.app->audition_candidate(typed(value));
      LMDJ_CHECK(result.has_value());
      LMDJ_CHECK(result.value().prepared->interleaved == expected[index]);
      LMDJ_CHECK(result.value().source_frames == expected[index].size());
    });
  }
}
void eligibility_held_through_preparation() {
  Fixture f;
  const auto set = analyze(f);
  std::size_t reads = 0;
  f.storage->read_hook = [&](const auto& path) {
    if (path != f.blob()) return;
    ++reads;
    const auto discarded = f.app->command({{"operation", "candidate.set.discard"},
        {"job_id", "slice"}, {"set_id", set.at("set_id")}});
    error(discarded, "INVALID_ARGUMENT");
    LMDJ_CHECK(discarded.at("error").at("details").at("reason") == "job_busy");
  };
  readonly(f, [&] { ok(f.app->query(request(f, set))); });
  f.storage->read_hook = {};
  LMDJ_CHECK(reads >= 2);
}
void preparation_rechecks_source() {
  for (bool corrupt : {false, true}) {
    Fixture f;
    const auto value = request(f, analyze(f));
    bool read_source = false;
    bool changed = false;
    auto expected = state(f);
    std::map<std::string, std::string> after_external_change;
    f.storage->read_hook = [&](const auto& path) { if (path == f.blob()) read_source = true; };
    f.storage->acquire_hook = [&](const auto& path) {
      if (path != f.project || !read_source || changed) return;
      changed = true;
      if (corrupt) write(f.blob(), "corrupt");
      else {
        ProjectStore other;
        const auto edited = other.execute(f.project, domain::Command{domain::UpdateSequenceSettings{
            {CommandId{other_id}, 1}, 130, std::nullopt, std::nullopt}});
        LMDJ_CHECK(edited.has_value()); expected = edited.value().state;
      }
      after_external_change = files(f);
    };
    const auto writes = f.storage->writes;
    const auto result = f.app->query(value);
    LMDJ_CHECK(changed && result.at("ok") == false);
    if (!corrupt) error(result, "REVISION_CONFLICT");
    f.storage->read_hook = {}; f.storage->acquire_hook = {};
    LMDJ_CHECK(f.storage->writes == writes);
    LMDJ_CHECK(state(f) == expected && files(f) == after_external_change);
    f.restart();
    LMDJ_CHECK(state(f) == expected && files(f) == after_external_change);
  }
}
void permission_readback_preserves_explicit_grants() {
  Fixture f;
  const auto before = f.app->query({{"operation", "provider.list"}});
  ok(before);
  auto grants = before.at("result").at("granted_permissions");
  LMDJ_CHECK(grants.is_array());
  grants.push_back("sample.slice.execute");
  ok(f.app->command({{"operation", "provider.permissions.configure"}, {"granted_permissions", grants}}));
  const auto after = f.app->query({{"operation", "provider.list"}});
  ok(after);
  LMDJ_CHECK(after.at("result").at("granted_permissions") == grants);
  LMDJ_CHECK(after.at("result").at("providers") == before.at("result").at("providers"));
  f.restart();
  const auto reopened = f.app->query({{"operation", "provider.list"}});
  ok(reopened);
  LMDJ_CHECK(reopened == before);
}
} // namespace

int main() {
  try {
    permission_readback_preserves_explicit_grants();
    exact_pcm_and_resampling(); pattern_and_unrelated_revision(); strict_query();
    unknown_and_lifecycle(); source_identity_refusals(); unavailable_bytes();
    preparation_limit(); preparation_rechecks_source(); interval_boundaries(); tampered_recipe();
    empty_result_and_invalid_profile(); eligibility_held_through_preparation();
    std::cout << "candidate audition Facade: PASS\n";
    return 0;
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
}
