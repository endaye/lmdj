#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>
#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::facade::RuntimeSnapshotRequest;
using lmdj::domain::PadSlotId;
using lmdj::domain::RawTakeEvent;
using lmdj::foundation::PatternId;
using lmdj::foundation::TakeId;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kKickAssetId =
    "00000000-0000-4000-8000-000000000101";
constexpr std::string_view kSnareAssetId =
    "00000000-0000-4000-8000-000000000102";
constexpr std::string_view kTakeId =
    "00000000-0000-4000-8000-000000000201";
constexpr std::string_view kPatternId =
    "00000000-0000-4000-8000-000000000010";
constexpr std::string_view kCapability = "proof.candidate.v2";
constexpr std::string_view kGoldenSha =
    "d276060107ab2479126c4f66919b799593a852fe624720f03e7be3b70bcfe867";

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-facade-test-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" +
         std::string(12 - tail.size(), '0') + tail;
}

std::shared_ptr<Registry> proof_registry() {
  auto registry = std::make_shared<Registry>();
  LMDJ_CHECK(
      registry->add(
          lmdj::providers::local_proof_success_registration()).has_value());
  LMDJ_CHECK(
      registry->add(
          lmdj::providers::local_proof_failure_registration()).has_value());
  return registry;
}

ApplicationConfig config(
    const std::filesystem::path& root,
    std::shared_ptr<Registry> registry = proof_registry()) {
  return ApplicationConfig{
      root,
      std::move(registry),
      ProviderPolicy{
          {"local"},
          {"public"},
          {"proof.execute"},
      },
      [] {
        return std::string("2026-07-31T00:00:00.000Z");
      },
  };
}

nlohmann::json slot(std::uint32_t bank, std::uint32_t pad) {
  return {{"bank", bank}, {"pad", pad}};
}

void check_exact_keys(
    const nlohmann::json& object,
    std::initializer_list<std::string_view> keys) {
  LMDJ_CHECK(object.is_object());
  LMDJ_CHECK(object.size() == keys.size());
  for (const auto key : keys) {
    LMDJ_CHECK(object.contains(std::string(key)));
  }
}

void check_success(
    const nlohmann::json& response,
    const nlohmann::json& revision) {
  check_exact_keys(response, {"ok", "result", "project_revision"});
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("result").is_object());
  LMDJ_CHECK(response.at("project_revision") == revision);
}

void check_error(
    const nlohmann::json& response,
    std::string_view code) {
  check_exact_keys(response, {"ok", "error"});
  LMDJ_CHECK(response.at("ok") == false);
  check_exact_keys(
      response.at("error"), {"code", "message", "details"});
  LMDJ_CHECK(response.at("error").at("code") == code);
}

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("test file could not be opened");
  }
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

void write_bytes(
    const std::filesystem::path& path,
    std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  if (!stream) {
    throw std::runtime_error("test file could not be written");
  }
}

nlohmann::json create_request(const std::filesystem::path& project) {
  return {
      {"operation", "project.create"},
      {"project_path", project.generic_string()},
      {"project_id", kProjectId},
      {"bpm", 120},
  };
}

void test_module_versions_and_dependencies_are_exact() {
  const auto application = nlohmann::json::parse(
      read_bytes("packages/application-facade/module.json"));
  const auto project_io = nlohmann::json::parse(
      read_bytes("packages/project-io/module.json"));
  LMDJ_CHECK(
      (application ==
       nlohmann::json{
           {"contract", "lmdj.module.v1"},
           {"module", "application-facade"},
           {"version", "1.0.1"},
           {"api_version", 2},
           {"dependencies",
            {
                {"foundation", "0.1.0"},
                {"authoring-domain", "0.1.0"},
                {"project-io", "0.2.0"},
                {"project-cooker", "0.1.0"},
                {"audio-runtime", "0.2.0"},
                {"provider-sdk", "1.0.0"},
            }},
       }));
  LMDJ_CHECK(project_io.at("module") == "project-io");
  LMDJ_CHECK(project_io.at("version") == "0.2.0");
}

nlohmann::json import_request(
    const std::filesystem::path& project,
    std::uint32_t command_suffix,
    std::string_view asset_id,
    const std::filesystem::path& source,
    std::uint64_t revision) {
  return {
      {"operation", "asset.import"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(command_suffix)},
      {"expected_revision", revision},
      {"asset_id", asset_id},
      {"source_path", source.generic_string()},
      {"media_type", "audio/wav"},
  };
}

nlohmann::json assign_request(
    const std::filesystem::path& project,
    std::uint32_t command_suffix,
    std::uint32_t pad,
    std::string_view asset_id,
    std::uint64_t revision) {
  return {
      {"operation", "pad.assign"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(command_suffix)},
      {"expected_revision", revision},
      {"slot", slot(0, pad)},
      {"asset_id", asset_id},
  };
}

nlohmann::json pattern_json() {
  return {
      {"pattern_id", kPatternId},
      {"bars", 1},
      {"events",
       nlohmann::json::array(
           {
               {{"slot", slot(0, 0)}, {"step", 0}, {"velocity", 127}},
               {{"slot", slot(0, 1)}, {"step", 4}, {"velocity", 127}},
               {{"slot", slot(0, 0)}, {"step", 8}, {"velocity", 127}},
               {{"slot", slot(0, 1)}, {"step", 12}, {"velocity", 127}},
           })},
  };
}

void create_golden_project(
    Application& application,
    const std::filesystem::path& project) {
  auto response = application.command(create_request(project));
  check_success(response, 0);

  response = application.command(import_request(
      project,
      1,
      kKickAssetId,
      std::filesystem::absolute("tests/fixtures/audio/kick.wav"),
      0));
  check_success(response, 1);

  response = application.command(import_request(
      project,
      2,
      kSnareAssetId,
      std::filesystem::absolute("tests/fixtures/audio/snare.wav"),
      1));
  check_success(response, 2);

  response = application.command(
      assign_request(project, 3, 0, kKickAssetId, 2));
  check_success(response, 3);
  response = application.command(
      assign_request(project, 4, 1, kSnareAssetId, 3));
  check_success(response, 4);

  response = application.command(
      {
          {"operation", "take.begin"},
          {"project_path", project.generic_string()},
          {"take_id", kTakeId},
          {"expected_revision", 4},
          {"sample_rate", 48000},
      });
  check_success(response, 4);
  for (const auto& [pad, frame] :
       std::vector<std::pair<std::uint32_t, std::uint64_t>>{
           {0, 0},
           {1, 24'000},
           {0, 48'000},
           {1, 72'000},
       }) {
    response = application.command(
        {
            {"operation", "take.append"},
            {"project_path", project.generic_string()},
            {"take_id", kTakeId},
            {"event",
             {
                 {"slot", slot(0, pad)},
                 {"frame_offset", frame},
                 {"velocity", 127},
             }},
        });
    check_success(response, 4);
  }

  response = application.command(
      {
          {"operation", "take.commit"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(5)},
          {"expected_revision", 4},
          {"take_id", kTakeId},
          {"pattern", pattern_json()},
      });
  check_success(response, 5);
}

void test_all_operations_share_one_facade_and_revision_contract() {
  TempDirectory temp;
  const auto project = temp.path() / "proof-beat.lmdj";
  auto registry = proof_registry();
  Application application(config(temp.path(), registry));
  create_golden_project(application, project);

  auto response = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(response, 5);
  const auto& projected = response.at("result").at("project");
  check_exact_keys(
      projected,
      {
          "contract",
          "project_id",
          "revision",
          "bpm",
          "banks",
          "assets",
          "takes",
          "patterns",
      });
  LMDJ_CHECK(projected.at("contract") == "lmdj.project.v1");
  LMDJ_CHECK(projected.at("revision") == 5);
  LMDJ_CHECK(
      projected.at("takes").at(kTakeId).at("events").size() == 4);

  response = application.query(
      {
          {"operation", "take.recoverable.list"},
          {"project_path", project.generic_string()},
      });
  check_success(response, 5);
  LMDJ_CHECK(response.at("result").at("candidates").empty());

  response = application.query(
      {
          {"operation", "snapshot.cook"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
      });
  check_success(response, 5);
  check_exact_keys(
      response.at("result"),
      {"pattern_id", "event_count", "artifact_sha256s"});
  LMDJ_CHECK(response.at("result").at("event_count") == 4);
  LMDJ_CHECK(response.dump().find("snapshot_id") == std::string::npos);
  LMDJ_CHECK(
      response.at("result").at("artifact_sha256s").size() == 2);

  response = application.query({{"operation", "provider.list"}});
  check_success(response, nullptr);
  LMDJ_CHECK(response.at("result").at("providers").size() == 2);

  response = application.command(
      {
          {"operation", "provider.select"},
          {"capability", kCapability},
          {"provider_id", "local.proof.success"},
      });
  check_success(response, nullptr);
  response = application.query(
      {
          {"operation", "provider.selected"},
          {"capability", kCapability},
      });
  check_success(response, nullptr);
  LMDJ_CHECK(
      response.at("result").at("provider_id") ==
      "local.proof.success");

  response = application.command(
      {
          {"operation", "provider.run"},
          {"attempt_id", "attempt-facade-success"},
          {"capability", kCapability},
          {"inputs",
           nlohmann::json::array({
               {
                   {"port", "inputs"},
                   {"artifact",
                    {
                        {"sha256", std::string(64, 'a')},
                        {"media_type", "application/octet-stream"},
                        {"byte_length", 1},
                    }},
               },
           })},
          {"parameters", nlohmann::json::object()},
          {"data_classification", "public"},
          {"platform", "test"},
          {"region", "local"},
          {"required_permissions",
           nlohmann::json::array({"proof.execute"})},
      });
  check_success(response, nullptr);
  check_exact_keys(
      response.at("result"),
      {
          "attempt_id",
          "candidate_id",
          "outputs",
          "provenance",
      });
  const auto expected_outputs = nlohmann::json::array({
      {
          {"port", "candidate"},
          {"artifact",
           {
               {"sha256",
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
               {"media_type", "application/x-lmdj-proof"},
               {"byte_length", 0},
           }},
      },
  });
  LMDJ_CHECK(response.at("result").at("outputs") == expected_outputs);

  response = application.query(
      {
          {"operation", "attempt.inspect"},
          {"attempt_id", "attempt-facade-success"},
      });
  check_success(response, nullptr);
  LMDJ_CHECK(response.at("result").at("attempt_id") ==
             "attempt-facade-success");
  LMDJ_CHECK(response.at("result").at("status") == "succeeded");
  LMDJ_CHECK(
      response.at("result").at("request").at("inputs").at(0).at("port") ==
      "inputs");
  LMDJ_CHECK(
      response.at("result").at("minted_outputs") == expected_outputs);
  LMDJ_CHECK(
      response.at("result").at("candidate_outputs") == expected_outputs);
}

void test_render_recooks_after_restart_and_publishes_golden_atomically() {
  TempDirectory temp;
  const auto project = temp.path() / "proof-beat.lmdj";
  {
    Application application(config(temp.path()));
    create_golden_project(application, project);
    const auto cooked = application.query(
        {
            {"operation", "snapshot.cook"},
            {"project_path", project.generic_string()},
            {"pattern_id", kPatternId},
        });
    check_success(cooked, 5);
  }

  const auto project_before = read_bytes(project / "manifest.json");
  const auto output = temp.path() / "beat.wav";
  Application fresh(config(temp.path()));
  auto rendered = fresh.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", output.generic_string()},
      });
  check_success(rendered, 5);
  LMDJ_CHECK(rendered.dump().find("snapshot_id") == std::string::npos);
  LMDJ_CHECK(rendered.at("result").at("artifact").at("sha256") == kGoldenSha);
  LMDJ_CHECK(rendered.at("result").at("output_path") ==
             output.generic_string());
  LMDJ_CHECK(std::filesystem::is_regular_file(output));
  LMDJ_CHECK(read_bytes(project / "manifest.json") == project_before);

  const auto output_before = read_bytes(output);
  const auto existing = fresh.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", output.generic_string()},
      });
  check_error(existing, "INVALID_ARGUMENT");
  LMDJ_CHECK(read_bytes(output) == output_before);

  const auto inside = project / "beat.wav";
  const auto rejected = fresh.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", inside.generic_string()},
      });
  check_error(rejected, "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(inside));
  for (const auto& entry :
       std::filesystem::directory_iterator(temp.path())) {
    const auto name = entry.path().filename().string();
    LMDJ_CHECK(
        name.find(".lmdj-render-") == std::string::npos);
    LMDJ_CHECK(
        name.find(".core-render-") == std::string::npos);
  }
}

void test_typed_realtime_host_api_prepares_and_persists_take_batches() {
  TempDirectory temp;
  const auto project = temp.path() / "typed-snapshot.lmdj";
  Application application(config(temp.path()));
  create_golden_project(application, project);
  const auto manifest_before = read_bytes(project / "manifest.json");

  const auto prepared = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{project, PatternId{std::string(kPatternId)}});

  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value()->project_revision == 5);
  LMDJ_CHECK(prepared.value()->pads.size() == 2);
  LMDJ_CHECK(prepared.value()->events.size() == 4);
  LMDJ_CHECK(read_bytes(project / "manifest.json") == manifest_before);
  const auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(inspected, 5);

  const auto invalid_path = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{
          std::filesystem::path{"relative.lmdj"},
          PatternId{std::string(kPatternId)},
      });
  LMDJ_CHECK(!invalid_path.has_value());
  LMDJ_CHECK(
      invalid_path.error().code ==
      lmdj::foundation::ErrorCode::invalid_argument);

  const auto capture_project = temp.path() / "typed-capture.lmdj";
  check_success(
      application.command(create_request(capture_project)), 0);
  const TakeId capture_take{uuid(202)};
  check_success(
      application.command(
          {
              {"operation", "take.begin"},
              {"project_path", capture_project.generic_string()},
              {"take_id", capture_take.value()},
              {"expected_revision", 0},
              {"sample_rate", 48000},
          }),
      0);
  const std::vector<RawTakeEvent> events{
      RawTakeEvent{PadSlotId{0, 0}, 0, 127},
      RawTakeEvent{PadSlotId{1, 2}, 128, 96},
      RawTakeEvent{PadSlotId{3, 15}, 256, 64},
  };

  const auto appended = application.append_realtime_take_events(
      capture_project, capture_take, events);

  LMDJ_CHECK(appended.has_value());
  const auto committed = application.command(
      {
          {"operation", "take.commit"},
          {"project_path", capture_project.generic_string()},
          {"command_id", uuid(203)},
          {"expected_revision", 0},
          {"take_id", capture_take.value()},
          {"pattern",
           {
               {"pattern_id", uuid(204)},
               {"bars", 1},
               {"events",
                nlohmann::json::array(
                    {
                        {{"slot", slot(0, 0)},
                         {"step", 0},
                         {"velocity", 127}},
                        {{"slot", slot(1, 2)},
                         {"step", 1},
                         {"velocity", 96}},
                        {{"slot", slot(3, 15)},
                         {"step", 2},
                         {"velocity", 64}},
                    })},
           }},
      });
  check_success(committed, 1);
  const auto captured = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", capture_project.generic_string()},
      });
  check_success(captured, 1);
  const auto& persisted = captured.at("result")
                              .at("project")
                              .at("takes")
                              .at(capture_take.value())
                              .at("events");
  LMDJ_CHECK(persisted.size() == events.size());
  LMDJ_CHECK(persisted.at(0).at("frame_offset") == 0);
  LMDJ_CHECK(persisted.at(1).at("frame_offset") == 128);
  LMDJ_CHECK(persisted.at(2).at("frame_offset") == 256);

  const auto recovery_project = temp.path() / "typed-recovery.lmdj";
  check_success(application.command(create_request(recovery_project)), 0);
  const TakeId recovery_take{uuid(205)};
  check_success(
      application.command(
          {
              {"operation", "take.begin"},
              {"project_path", recovery_project.generic_string()},
              {"take_id", recovery_take.value()},
              {"expected_revision", 0},
              {"sample_rate", 48000},
          }),
      0);
  LMDJ_CHECK(
      application.append_realtime_take_events(
                     recovery_project,
                     recovery_take,
                     std::span<const RawTakeEvent>{events}.first(1))
          .has_value());
  const auto invalid_reason = application.seal_realtime_take(
      recovery_project, recovery_take, "revision_conflict");
  LMDJ_CHECK(!invalid_reason.has_value());
  LMDJ_CHECK(
      invalid_reason.error().code ==
      lmdj::foundation::ErrorCode::invalid_argument);
  const auto sealed = application.seal_realtime_take(
      recovery_project, recovery_take, "capture_incomplete");
  LMDJ_CHECK(sealed.has_value());
  const auto candidates = application.query(
      {
          {"operation", "take.recoverable.list"},
          {"project_path", recovery_project.generic_string()},
      });
  check_success(candidates, 0);
  LMDJ_CHECK(candidates.at("result").at("candidates").size() == 1);
  LMDJ_CHECK(
      candidates.at("result")
              .at("candidates")
              .at(0)
              .at("reason") == "capture_incomplete");
  LMDJ_CHECK(
      candidates.at("result")
              .at("candidates")
              .at(0)
              .at("events")
              .size() == 1);
}

void test_render_rejects_symlinked_parent_and_never_reuses_crash_residue() {
  TempDirectory temp;
  const auto project = temp.path() / "proof-beat.lmdj";
  Application application(config(temp.path()));
  create_golden_project(application, project);

  const auto output = temp.path() / "residue.wav";
  const auto residue =
      temp.path() / "residue.wav.lmdj-render-0.tmp";
  {
    std::ofstream stream(residue, std::ios::binary);
    stream << "crash-residue-must-survive";
  }
  const auto rendered = application.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", output.generic_string()},
      });
  check_success(rendered, 5);
  LMDJ_CHECK(read_bytes(residue) == "crash-residue-must-survive");
  for (const auto& entry :
       std::filesystem::directory_iterator(temp.path())) {
    LMDJ_CHECK(
        entry.path().filename().string().find(".core-render-") ==
        std::string::npos);
  }

  const auto alias = temp.path() / "outside-looking";
  std::filesystem::create_directory_symlink(project, alias);
  const auto injected = alias / "injected.wav";
  const auto rejected = application.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", injected.generic_string()},
      });
  check_error(rejected, "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project / "injected.wav"));
}

void test_take_commit_uses_captured_revision_and_replays_after_cleanup() {
  TempDirectory temp;
  const auto project = temp.path() / "captured-revision.lmdj";
  Application application(config(temp.path()));
  check_success(application.command(create_request(project)), 0);
  check_success(
      application.command(import_request(
          project,
          41,
          kKickAssetId,
          std::filesystem::absolute("tests/fixtures/audio/kick.wav"),
          0)),
      1);
  check_success(
      application.command(
          assign_request(project, 42, 0, kKickAssetId, 1)),
      2);

  check_success(
      application.command(
          {
              {"operation", "take.begin"},
              {"project_path", project.generic_string()},
              {"take_id", kTakeId},
              {"expected_revision", 2},
              {"sample_rate", 48000},
          }),
      2);
  check_success(
      application.command(
          {
              {"operation", "take.append"},
              {"project_path", project.generic_string()},
              {"take_id", kTakeId},
              {"event",
               {
                   {"slot", slot(0, 0)},
                   {"frame_offset", 0},
                   {"velocity", 127},
               }},
          }),
      2);
  check_success(
      application.command(
          assign_request(project, 43, 1, kKickAssetId, 2)),
      3);

  const auto conflicted = application.command(
      {
          {"operation", "take.commit"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(44)},
          {"expected_revision", 3},
          {"take_id", kTakeId},
          {"pattern",
           {
               {"pattern_id", kPatternId},
               {"bars", 1},
               {"events",
                nlohmann::json::array(
                    {{{"slot", slot(0, 0)},
                      {"step", 0},
                      {"velocity", 127}}})},
           }},
      });
  check_error(conflicted, "REVISION_CONFLICT");
  auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(inspected, 3);
  LMDJ_CHECK(inspected.at("result").at("project").at("takes").empty());
  const auto recoverable = application.query(
      {
          {"operation", "take.recoverable.list"},
          {"project_path", project.generic_string()},
      });
  check_success(recoverable, 3);
  LMDJ_CHECK(recoverable.at("result").at("candidates").size() == 1);
  LMDJ_CHECK(
      recoverable.at("result")
          .at("candidates")
          .at(0)
          .at("expected_revision") == 2);

  const auto replay_project = temp.path() / "replay.lmdj";
  create_golden_project(application, replay_project);
  const auto replay_request = nlohmann::json{
      {"operation", "take.commit"},
      {"project_path", replay_project.generic_string()},
      {"command_id", uuid(5)},
      {"expected_revision", 4},
      {"take_id", kTakeId},
      {"pattern", pattern_json()},
  };
  auto replayed = application.command(replay_request);
  check_success(replayed, 5);
  LMDJ_CHECK(replayed.at("result").at("committed_revision") == 5);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);

  check_success(
      application.command(
          assign_request(replay_project, 45, 2, kKickAssetId, 5)),
      6);
  Application fresh(config(temp.path()));
  replayed = fresh.command(replay_request);
  check_success(replayed, 6);
  LMDJ_CHECK(replayed.at("result").at("committed_revision") == 5);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);

  auto cross_operation = replay_request;
  cross_operation["command_id"] = uuid(3);
  cross_operation["expected_revision"] = 2;
  check_error(
      fresh.command(cross_operation), "INVALID_ARGUMENT");

  auto changed_revision = replay_request;
  changed_revision["expected_revision"] = 5;
  check_error(
      fresh.command(changed_revision), "INVALID_ARGUMENT");

  auto changed_take = replay_request;
  changed_take["take_id"] = uuid(299);
  check_error(fresh.command(changed_take), "INVALID_ARGUMENT");

  auto changed_pattern_id = replay_request;
  changed_pattern_id["pattern"]["pattern_id"] = uuid(99);
  check_error(
      fresh.command(changed_pattern_id), "INVALID_ARGUMENT");

  auto changed_pattern_bars = replay_request;
  changed_pattern_bars["pattern"]["bars"] = 2;
  check_error(
      fresh.command(changed_pattern_bars), "INVALID_ARGUMENT");

  auto changed_pattern_event = replay_request;
  changed_pattern_event["pattern"]["events"][0]["velocity"] = 126;
  check_error(
      fresh.command(changed_pattern_event), "INVALID_ARGUMENT");

  replayed = fresh.command(replay_request);
  check_success(replayed, 6);
  LMDJ_CHECK(replayed.at("result").at("take_id") == kTakeId);
  LMDJ_CHECK(replayed.at("result").at("pattern_id") == kPatternId);
  LMDJ_CHECK(replayed.at("result").at("committed_revision") == 5);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);
}

void test_asset_and_pad_replay_identity_is_enforced() {
  TempDirectory temp;
  const auto project = temp.path() / "command-identity.lmdj";
  const auto source = temp.path() / "source-a.wav";
  const auto changed_source = temp.path() / "source-b.wav";
  write_bytes(source, "source-a");
  write_bytes(changed_source, "source-b");
  Application application(config(temp.path()));
  check_success(application.command(create_request(project)), 0);

  const auto import = nlohmann::json{
      {"operation", "asset.import"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(71)},
      {"expected_revision", 0},
      {"asset_id", kKickAssetId},
      {"source_path", source.generic_string()},
      {"media_type", "audio/wav"},
  };
  auto response = application.command(import);
  check_success(response, 1);
  LMDJ_CHECK(response.at("result").at("replayed") == false);
  response = application.command(import);
  check_success(response, 1);
  LMDJ_CHECK(response.at("result").at("asset_id") == kKickAssetId);
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  auto changed_import_revision = import;
  changed_import_revision["expected_revision"] = 1;
  check_error(
      application.command(changed_import_revision), "INVALID_ARGUMENT");
  auto changed_asset = import;
  changed_asset["asset_id"] = uuid(199);
  check_error(application.command(changed_asset), "INVALID_ARGUMENT");
  auto changed_bytes = import;
  changed_bytes["source_path"] = changed_source.generic_string();
  check_error(application.command(changed_bytes), "INVALID_ARGUMENT");
  auto changed_media = import;
  changed_media["media_type"] = "application/octet-stream";
  check_error(application.command(changed_media), "INVALID_ARGUMENT");

  auto import_id_as_pad = assign_request(
      project, 71, 0, kKickAssetId, 0);
  check_error(
      application.command(import_id_as_pad), "INVALID_ARGUMENT");

  const auto assignment =
      assign_request(project, 72, 0, kKickAssetId, 1);
  response = application.command(assignment);
  check_success(response, 2);
  LMDJ_CHECK(response.at("result").at("replayed") == false);
  response = application.command(assignment);
  check_success(response, 2);
  LMDJ_CHECK(response.at("result").at("slot") == slot(0, 0));
  LMDJ_CHECK(response.at("result").at("asset_id") == kKickAssetId);
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  auto changed_pad_revision = assignment;
  changed_pad_revision["expected_revision"] = 2;
  check_error(
      application.command(changed_pad_revision), "INVALID_ARGUMENT");
  auto changed_slot = assignment;
  changed_slot["slot"] = slot(0, 1);
  check_error(application.command(changed_slot), "INVALID_ARGUMENT");
  auto changed_assignment = assignment;
  changed_assignment["asset_id"] = nullptr;
  check_error(
      application.command(changed_assignment), "INVALID_ARGUMENT");

  auto pad_id_as_import = import;
  pad_id_as_import["command_id"] = uuid(72);
  pad_id_as_import["expected_revision"] = 1;
  check_error(
      application.command(pad_id_as_import), "INVALID_ARGUMENT");

  Application fresh(config(temp.path()));
  response = fresh.command(import);
  check_success(response, 2);
  LMDJ_CHECK(response.at("result").at("asset_id") == kKickAssetId);
  LMDJ_CHECK(response.at("result").at("committed_revision") == 1);
  LMDJ_CHECK(response.at("result").at("replayed") == true);
  response = fresh.command(assignment);
  check_success(response, 2);
  LMDJ_CHECK(response.at("result").at("slot") == slot(0, 0));
  LMDJ_CHECK(response.at("result").at("asset_id") == kKickAssetId);
  LMDJ_CHECK(response.at("result").at("committed_revision") == 2);
  LMDJ_CHECK(response.at("result").at("replayed") == true);
}

void test_exact_shapes_routing_and_invalid_scalars_fail_before_mutation() {
  TempDirectory temp;
  const auto project = temp.path() / "shape.lmdj";
  Application application(config(temp.path()));

  const std::vector<std::string> commands{
      "project.create",
      "asset.import",
      "pad.assign",
      "take.begin",
      "take.append",
      "take.commit",
      "render.offline",
      "provider.select",
      "provider.run",
  };
  const std::vector<std::string> queries{
      "project.inspect",
      "take.recoverable.list",
      "snapshot.cook",
      "provider.list",
      "provider.selected",
      "attempt.inspect",
  };
  for (const auto& operation : commands) {
    check_error(
        application.query({{"operation", operation}}),
        "INVALID_ARGUMENT");
    check_error(
        application.command(
            {{"operation", operation}, {"unexpected", true}}),
        "INVALID_ARGUMENT");
  }
  for (const auto& operation : queries) {
    check_error(
        application.command({{"operation", operation}}),
        "INVALID_ARGUMENT");
    check_error(
        application.query(
            {{"operation", operation}, {"unexpected", true}}),
        "INVALID_ARGUMENT");
  }
  check_error(
      application.command({{"operation", "unknown"}}),
      "INVALID_ARGUMENT");
  check_error(application.command(nlohmann::json::object()), "INVALID_ARGUMENT");
  check_error(
      application.command({{"operation", 42}}),
      "INVALID_ARGUMENT");

  auto extra = create_request(project);
  extra["extra"] = true;
  check_error(application.command(extra), "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project));

  auto invalid_uuid = create_request(project);
  invalid_uuid["project_id"] = "00000000-0000-0000-0000-000000000001";
  check_error(application.command(invalid_uuid), "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project));

  auto invalid_utf8 = create_request(project);
  invalid_utf8["operation"] = std::string("\xc3\x28", 2);
  check_error(application.command(invalid_utf8), "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project));

  auto embedded_nul = create_request(project);
  embedded_nul["project_path"] =
      std::string(project.generic_string() + std::string("\0tail", 5));
  check_error(application.command(embedded_nul), "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project));

  check_success(application.command(create_request(project)), 0);
  auto fractional = import_request(
      project,
      31,
      kKickAssetId,
      std::filesystem::absolute("tests/fixtures/audio/kick.wav"),
      0);
  fractional["expected_revision"] = 0.0;
  check_error(application.command(fractional), "INVALID_ARGUMENT");
  for (const auto& invalid_revision :
       std::vector<nlohmann::json>{
           -1,
           "0",
           nlohmann::json::parse("18446744073709551616"),
       }) {
    auto invalid_integer = fractional;
    invalid_integer["expected_revision"] = invalid_revision;
    check_error(application.command(invalid_integer), "INVALID_ARGUMENT");
  }
  auto nested_extra = assign_request(
      project, 32, 0, kKickAssetId, 0);
  nested_extra["slot"]["extra"] = true;
  check_error(application.command(nested_extra), "INVALID_ARGUMENT");

  const auto stale_begin = application.command(
      {
          {"operation", "take.begin"},
          {"project_path", project.generic_string()},
          {"take_id", kTakeId},
          {"expected_revision", 1},
          {"sample_rate", 48000},
      });
  check_error(stale_begin, "REVISION_CONFLICT");
  LMDJ_CHECK(!std::filesystem::exists(
      project / "recovery/active" /
      (std::string(kTakeId) + ".jsonl")));
  auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(inspected, 0);

  auto with_snapshot_id = nlohmann::json{
      {"operation", "snapshot.cook"},
      {"project_path", project.generic_string()},
      {"pattern_id", kPatternId},
      {"snapshot_id", "forbidden"},
  };
  check_error(application.query(with_snapshot_id), "INVALID_ARGUMENT");
}

void test_provider_failures_are_errors_but_attempts_remain_queryable() {
  TempDirectory temp;
  Application application(config(temp.path()));
  auto selected = application.command(
      {
          {"operation", "provider.select"},
          {"capability", kCapability},
          {"provider_id", "local.proof.failure"},
      });
  check_success(selected, nullptr);
  const auto failed = application.command(
      {
          {"operation", "provider.run"},
          {"attempt_id", "attempt-facade-failure"},
          {"capability", kCapability},
          {"inputs", nlohmann::json::array()},
          {"parameters", nlohmann::json::object()},
          {"data_classification", "public"},
          {"platform", "test"},
          {"region", "local"},
          {"required_permissions",
           nlohmann::json::array({"proof.execute"})},
      });
  check_error(failed, "PROVIDER_FAILED");
  LMDJ_CHECK(
      failed.at("error").at("details").at("attempt_id") ==
      "attempt-facade-failure");

  const auto inspected = application.query(
      {
          {"operation", "attempt.inspect"},
          {"attempt_id", "attempt-facade-failure"},
      });
  check_success(inspected, nullptr);
  LMDJ_CHECK(inspected.at("result").at("status") == "failed");
  LMDJ_CHECK(
      inspected.dump().find("intentional proof failure") ==
      std::string::npos);

  Application deny_all(
      ApplicationConfig{
          temp.path() / "deny",
          proof_registry(),
          ProviderPolicy{},
          [] { return std::string("2026-07-31T00:00:00.000Z"); },
      });
  check_success(
      deny_all.command(
          {
              {"operation", "provider.select"},
              {"capability", kCapability},
              {"provider_id", "local.proof.success"},
          }),
      nullptr);
  const auto denied = deny_all.command(
      {
          {"operation", "provider.run"},
          {"attempt_id", "attempt-denied"},
          {"capability", kCapability},
          {"inputs", nlohmann::json::array()},
          {"parameters", nlohmann::json::object()},
          {"data_classification", "public"},
          {"platform", "test"},
          {"region", "local"},
          {"required_permissions",
           nlohmann::json::array({"proof.execute"})},
      });
  check_error(denied, "PERMISSION_DENIED");
}

}  // namespace

int main() {
  try {
    test_module_versions_and_dependencies_are_exact();
    test_all_operations_share_one_facade_and_revision_contract();
    test_render_rejects_symlinked_parent_and_never_reuses_crash_residue();
    test_render_recooks_after_restart_and_publishes_golden_atomically();
    test_typed_realtime_host_api_prepares_and_persists_take_batches();
    test_take_commit_uses_captured_revision_and_replays_after_cleanup();
    test_asset_and_pad_replay_identity_is_enforced();
    test_exact_shapes_routing_and_invalid_scalars_fail_before_mutation();
    test_provider_failures_are_errors_but_attempts_remain_queryable();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "application facade tests: PASS\n";
  return 0;
}
