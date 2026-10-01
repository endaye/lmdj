#include "candidate_fixture.hpp"

namespace {
using namespace lmdj::facade;
// This command has no Provider dependency; construct a neutral Facade rather
// than binding the test to a Product Assembly identity.
struct DeleteFixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-pad-delete-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path project = root / "source.lmdj";
  std::shared_ptr<ObservedStorage> storage = std::make_shared<ObservedStorage>();
  std::unique_ptr<Application> app;
  std::string digest;
  DeleteFixture() {
    std::filesystem::create_directories(root);
    storage->owner = project;
    restart();
    ok(app->command({{"operation", "project.create"}, {"project_path", project.generic_string()},
        {"project_id", project_id}, {"bpm", 120}}));
    const auto bytes = wav();
    LMDJ_CHECK(app->import_artifact_bytes({project,
        {CommandId{"00000000-0000-4000-8000-000000000003"}, 0}, AssetId{asset_id}, "audio/wav",
        std::as_bytes(std::span{bytes.data(),bytes.size()})}).has_value());
    const auto inspected = app->query({{"operation", "project.inspect"}, {"project_path",project.generic_string()}});
    ok(inspected);
    digest = inspected.at("result").at("project").at("assets").at(asset_id).at("artifact").at("sha256");
  }
  ~DeleteFixture() { app.reset(); std::error_code error; std::filesystem::remove_all(root,error); }
  void restart() {
    app.reset();
    ApplicationConfig config{};
    config.workspace_root = root;
    config.storage_platform = storage;
    config.performance_replay_controller = make_unavailable_performance_replay_controller();
    app = std::make_unique<Application>(std::move(config));
  }
  auto blob() const { return project / "assets" / (digest + ".wav"); }
};
Json project(DeleteFixture& f) {
  const auto result = f.app->query({{"operation", "project.inspect"},
      {"project_path", f.project.generic_string()}});
  ok(result);
  return result.at("result").at("project");
}
void bind(DeleteFixture& f) {
  ok(f.app->command({{"operation", "pad.assign"},
      {"project_path", f.project.generic_string()}, {"command_id", other_id},
      {"expected_revision", 1}, {"slot", {{"bank", 0}, {"pad", 0}}},
      {"asset_id", asset_id}}));
}
void delete_persists_and_replays() {
  DeleteFixture f;
  bind(f);
  const auto original_bytes = read(f.blob());
  const auto before = project(f);
  const SampleDeleteRequest request{f.project,
      {CommandId{"00000000-0000-4000-8000-000000000010"}, 2}, {0, 0}};
  const auto deleted = f.app->delete_sample_pad(request);
  LMDJ_CHECK(deleted.has_value());
  LMDJ_CHECK(deleted.value().committed_revision == 3);
  LMDJ_CHECK(deleted.value().runtime_prepare_required);
  const auto inspected = f.app->inspect_sample({f.project, {0, 0}});
  LMDJ_CHECK(inspected.has_value() && !inspected.value().asset_id);
  LMDJ_CHECK(inspected.value().playback == lmdj::domain::PadPlayback{});
  LMDJ_CHECK(project(f).at("assets") == before.at("assets"));
  LMDJ_CHECK(read(f.blob()) == original_bytes);
  LMDJ_CHECK(f.app->delete_sample_pad(request).value().committed_revision == 3);
  f.restart();
  LMDJ_CHECK(!f.app->inspect_sample({f.project, {0, 0}}).value().asset_id);
  LMDJ_CHECK(project(f).at("revision") == 3);
}
void refused_delete_preserves_truth() {
  DeleteFixture f;
  bind(f);
  const auto before = project(f);
  const auto stale = f.app->delete_sample_pad({f.project,
      {CommandId{"00000000-0000-4000-8000-000000000011"}, 1}, {0, 0}});
  LMDJ_CHECK(!stale.has_value() && stale.error().code == ErrorCode::revision_conflict);
  LMDJ_CHECK(project(f) == before);
  const auto invalid = f.app->delete_sample_pad({f.project,
      {CommandId{"invalid"}, 2}, {0, 0}});
  LMDJ_CHECK(!invalid.has_value() && project(f) == before);
  f.storage->fail_create = [](const auto&) { return true; };
  const auto failed = f.app->delete_sample_pad({f.project,
      {CommandId{"00000000-0000-4000-8000-000000000012"}, 2}, {0, 0}});
  LMDJ_CHECK(!failed.has_value());
  f.storage->fail_create = {};
  LMDJ_CHECK(project(f) == before);
}
void deletion_cancels_staged_import_and_rejects_late_commit() {
  DeleteFixture f;
  bind(f);
  const auto token = "00000000-0000-4000-8000-000000000020";
  LMDJ_CHECK(f.app->begin_sample_import({token, f.project,
      {CommandId{"00000000-0000-4000-8000-000000000021"}, 2},
      {0, 0}, AssetId{"00000000-0000-4000-8000-000000000022"}, wav().size()}).has_value());
  const auto result = f.app->command({{"operation", "pad.delete"},
      {"project_path", f.project.generic_string()},
      {"command_id", "00000000-0000-4000-8000-000000000023"},
      {"expected_revision", 2}, {"slot", {{"bank", 0}, {"pad", 0}}}});
  ok(result);
  LMDJ_CHECK(result.at("result").at("committed_revision") == 3);
  LMDJ_CHECK(!f.app->commit_sample_import(token).has_value());
  LMDJ_CHECK(!f.app->inspect_sample({f.project, {0, 0}}).value().asset_id);
  LMDJ_CHECK(project(f).at("revision") == 3);
}
void deletion_does_not_cancel_another_pads_import() {
  DeleteFixture f;
  bind(f);
  const auto token = "00000000-0000-4000-8000-000000000030";
  const auto bytes = wav();
  LMDJ_CHECK(f.app->begin_sample_import({token, f.project,
      {CommandId{"00000000-0000-4000-8000-000000000031"}, 2},
      {0, 1}, AssetId{"00000000-0000-4000-8000-000000000032"}, bytes.size()}).has_value());
  const auto deletion = f.app->delete_sample_pad({f.project,
      {CommandId{"00000000-0000-4000-8000-000000000033"}, 2}, {0, 0}});
  LMDJ_CHECK(deletion.has_value());
  LMDJ_CHECK(f.app->append_sample_import(token, 0,
      std::as_bytes(std::span{bytes.data(),bytes.size()}), true).has_value());
  const auto conflict = f.app->commit_sample_import(token);
  LMDJ_CHECK(!conflict.has_value() && conflict.error().code == ErrorCode::revision_conflict);
  LMDJ_CHECK(!f.app->inspect_sample({f.project,{0,0}}).value().asset_id);
  LMDJ_CHECK(!f.app->inspect_sample({f.project,{0,1}}).value().asset_id);
  LMDJ_CHECK(project(f).at("revision") == 3);
}

void deletion_refuses_unsettled_recording(bool performance) {
  DeleteFixture f;
  bind(f);
  if (performance) {
    ok(f.app->command({{"operation","performance.record.begin"},
        {"project_path",f.project.generic_string()},
        {"command_id","00000000-0000-4000-8000-000000000040"},
        {"expected_revision",2}, {"session_id","00000000-0000-4000-8000-000000000041"},
        {"performance_id","00000000-0000-4000-8000-000000000042"}}));
  } else {
    ok(f.app->command({{"operation","pattern.create"},
        {"project_path",f.project.generic_string()},
        {"command_id","00000000-0000-4000-8000-000000000040"},
        {"expected_revision",2},{"pattern_id","00000000-0000-4000-8000-000000000042"},
        {"bars",1}}));
    LMDJ_CHECK(f.app->begin_sequence({f.project,
        SequenceSessionId{"00000000-0000-4000-8000-000000000041"},
        PatternId{"00000000-0000-4000-8000-000000000042"},3,0}).has_value());
  }
  const auto before = project(f);
  const auto deletion = f.app->delete_sample_pad({f.project,
      {CommandId{"00000000-0000-4000-8000-000000000043"},3},{0,0}});
  LMDJ_CHECK(!deletion.has_value() && deletion.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(project(f) == before);
}

void refused_or_replayed_delete_keeps_new_import_ownership() {
  DeleteFixture f;
  bind(f);
  const SampleDeleteRequest deletion{f.project,
      {CommandId{"00000000-0000-4000-8000-000000000050"},2},{0,0}};
  LMDJ_CHECK(f.app->delete_sample_pad(deletion).has_value());
  const auto token = "00000000-0000-4000-8000-000000000051";
  const auto bytes = wav();
  LMDJ_CHECK(f.app->begin_sample_import({token,f.project,
      {CommandId{"00000000-0000-4000-8000-000000000052"},3},{0,0},
      AssetId{"00000000-0000-4000-8000-000000000053"},bytes.size()}).has_value());
  const auto replay = f.app->delete_sample_pad(deletion);
  LMDJ_CHECK(replay.has_value() && replay.value().cancelled_import_tokens.empty());
  LMDJ_CHECK(!f.app->delete_sample_pad({f.project,
      {CommandId{"00000000-0000-4000-8000-000000000054"},2},{0,0}}).has_value());
  LMDJ_CHECK(f.app->append_sample_import(token,0,
      std::as_bytes(std::span{bytes.data(),bytes.size()}),true).has_value());
  LMDJ_CHECK(f.app->commit_sample_import(token).has_value());
  LMDJ_CHECK(f.app->inspect_sample({f.project,{0,0}}).value().asset_id.has_value());
}

}
int main() {
  try {
    delete_persists_and_replays();
    refused_delete_preserves_truth();
    deletion_cancels_staged_import_and_rejects_late_commit();
    deletion_does_not_cancel_another_pads_import();
    deletion_refuses_unsettled_recording(false);
    deletion_refuses_unsettled_recording(true);
    refused_or_replayed_delete_keeps_new_import_ownership();
  } catch (const std::exception& failure) {
    std::cerr << failure.what() << '\n'; return 1;
  }
  std::cout << "facade pad deletion: PASS\n";
}
