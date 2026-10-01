#include "candidate_fixture.hpp"

namespace {
using namespace lmdj::facade;
constexpr auto pattern_id = "00000000-0000-4000-8000-000000000030";
constexpr auto session_id = "00000000-0000-4000-8000-000000000031";
// Grid editing has no Provider dependency; a neutral Facade keeps the test
// independent of any Product Assembly identity.
struct EditFixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-pattern-edit-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path project = root / "source.lmdj";
  std::unique_ptr<Application> app;
  unsigned next_command = 0x40;
  EditFixture() {
    std::filesystem::create_directories(root);
    restart();
    ok(app->command({{"operation", "project.create"}, {"project_path", project.generic_string()},
        {"project_id", project_id}, {"bpm", 120}}));
    ok(app->command({{"operation", "pattern.create"}, {"project_path", project.generic_string()},
        {"command_id", other_id}, {"expected_revision", 0}, {"pattern_id", pattern_id}, {"bars", 1}}));
  }
  ~EditFixture() { app.reset(); std::error_code error; std::filesystem::remove_all(root, error); }
  void restart() {
    app.reset();
    ApplicationConfig config{};
    config.workspace_root = root;
    config.performance_replay_controller = make_unavailable_performance_replay_controller();
    app = std::make_unique<Application>(std::move(config));
  }
  std::string command_id() {
    char buffer[40];
    std::snprintf(buffer, sizeof buffer, "00000000-0000-4000-8000-%012x", next_command++);
    return buffer;
  }
  Json project_json() {
    const auto result = app->query({{"operation", "project.inspect"},
        {"project_path", project.generic_string()}});
    ok(result);
    return result.at("result").at("project");
  }
  Json edit(const std::string& id, std::uint64_t revision, Json remove, Json put) {
    return app->command({{"operation", "pattern.events.edit"},
        {"project_path", project.generic_string()}, {"command_id", id},
        {"expected_revision", revision}, {"pattern_id", pattern_id},
        {"remove", std::move(remove)}, {"put", std::move(put)}});
  }
};
Json slot(int bank, int pad) { return {{"bank", bank}, {"pad", pad}}; }
Json note(int pad, int onset, int duration, int velocity) {
  return {{"slot", slot(0, pad)}, {"onset_tick", onset},
          {"duration_tick", duration}, {"velocity", velocity}};
}
Json key(int pad, int onset) { return {{"slot", slot(0, pad)}, {"onset_tick", onset}}; }

void edits_commit_replay_and_persist() {
  EditFixture f;
  const auto added = f.edit(f.command_id(), 1, Json::array(),
      Json::array({note(1, 240, 240, 100), note(0, 0, 240, 100)}));
  ok(added);
  LMDJ_CHECK(added.at("result").at("committed_revision") == 2);
  LMDJ_CHECK(added.at("result").at("replayed") == false);

  const auto move = f.command_id();
  const auto moved = f.edit(move, 2, Json::array({key(0, 0)}),
      Json::array({note(0, 480, 120, 64)}));
  ok(moved);
  LMDJ_CHECK(moved.at("result").at("committed_revision") == 3);
  const auto expected = Json::array({note(1, 240, 240, 100), note(0, 480, 120, 64)});
  LMDJ_CHECK(f.project_json().at("patterns").at(pattern_id).at("events") == expected);

  const auto retried = f.edit(move, 2, Json::array({key(0, 0)}),
      Json::array({note(0, 480, 120, 64)}));
  ok(retried);
  LMDJ_CHECK(retried.at("result").at("replayed") == true);
  LMDJ_CHECK(retried.at("result").at("committed_revision") == 3);
  f.restart();
  LMDJ_CHECK(f.project_json().at("revision") == 3);
  LMDJ_CHECK(f.project_json().at("patterns").at(pattern_id).at("events") == expected);
}

void refused_edits_keep_truth() {
  EditFixture f;
  ok(f.edit(f.command_id(), 1, Json::array(), Json::array({note(0, 0, 240, 100)})));
  const auto before = f.project_json();
  const auto missing = f.edit(f.command_id(), 2, Json::array({key(3, 0)}), Json::array());
  error(missing, "NOT_FOUND");
  LMDJ_CHECK(missing.at("error").at("details").at("reason") == "pattern_event_missing");
  error(f.edit(f.command_id(), 1, Json::array(), Json::array({note(2, 0, 240, 100)})),
        "REVISION_CONFLICT");
  // A one-bar Pattern ends at 3840 ticks, so this note would cross the seam.
  error(f.edit(f.command_id(), 2, Json::array(), Json::array({note(2, 3600, 480, 100)})),
        "INVALID_ARGUMENT");
  error(f.edit(f.command_id(), 2, Json::array(), Json::array({{{"slot", slot(0, 2)},
        {"onset_tick", 0}, {"velocity", 100}}})), "INVALID_ARGUMENT");
  LMDJ_CHECK(f.project_json() == before);
}

void recording_session_refuses_edits() {
  EditFixture f;
  ok(f.app->command({{"operation", "sequence.record.begin"},
      {"project_path", f.project.generic_string()}, {"session_id", session_id},
      {"pattern_id", pattern_id}, {"expected_revision", 1}, {"runtime_frame", 0}}));
  const auto before = f.project_json();
  const auto refused = f.edit(f.command_id(), 1, Json::array(), Json::array({note(0, 0, 240, 100)}));
  error(refused, "INVALID_ARGUMENT");
  LMDJ_CHECK(refused.at("error").at("details").at("reason") == "sequence_session_active");
  LMDJ_CHECK(f.project_json() == before);
}
}  // namespace

int main() {
  try {
    edits_commit_replay_and_persist();
    refused_edits_keep_truth();
    recording_session_refuses_edits();
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
  std::cout << "facade pattern events edit tests: PASS\n";
  return 0;
}
