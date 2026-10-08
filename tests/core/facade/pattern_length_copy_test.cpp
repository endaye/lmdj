#include "candidate_fixture.hpp"

namespace {
using namespace lmdj::facade;
constexpr auto pattern_id = "00000000-0000-4000-8000-000000000030";
constexpr auto session_id = "00000000-0000-4000-8000-000000000031";
constexpr auto copy_id = "00000000-0000-4000-8000-000000000032";
// Pattern length and copy (#1823) have no Provider dependency; a neutral
// Facade keeps the test independent of any Product Assembly identity.
struct LengthFixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-pattern-length-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path project = root / "source.lmdj";
  std::unique_ptr<Application> app;
  unsigned next_command = 0x40;
  LengthFixture() {
    std::filesystem::create_directories(root);
    restart();
    ok(app->command({{"operation", "project.create"}, {"project_path", project.generic_string()},
        {"project_id", project_id}, {"bpm", 120}}));
    ok(app->command({{"operation", "pattern.create"}, {"project_path", project.generic_string()},
        {"command_id", other_id}, {"expected_revision", 0}, {"pattern_id", pattern_id}, {"bars", 1}}));
  }
  ~LengthFixture() { app.reset(); std::error_code error; std::filesystem::remove_all(root, error); }
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
  Json resize(const std::string& id, std::uint64_t revision, int bars) {
    return app->command({{"operation", "pattern.resize"},
        {"project_path", project.generic_string()}, {"command_id", id},
        {"expected_revision", revision}, {"pattern_id", pattern_id}, {"bars", bars}});
  }
  Json double_up(const std::string& id, std::uint64_t revision) {
    return app->command({{"operation", "pattern.double"},
        {"project_path", project.generic_string()}, {"command_id", id},
        {"expected_revision", revision}, {"pattern_id", pattern_id}});
  }
  Json copy(const std::string& id, std::uint64_t revision) {
    return app->command({{"operation", "pattern.copy"},
        {"project_path", project.generic_string()}, {"command_id", id},
        {"expected_revision", revision}, {"source_pattern_id", pattern_id},
        {"pattern_id", copy_id}});
  }
};

void length_changes_and_a_slotted_copy_commit_replay_and_persist() {
  LengthFixture f;
  const auto resized = f.resize(f.command_id(), 1, 2);
  ok(resized);
  LMDJ_CHECK(resized.at("result").at("committed_revision") == 2);
  LMDJ_CHECK(resized.at("result").at("bars") == 2);
  LMDJ_CHECK(resized.at("result").at("replayed") == false);

  const auto doubled = f.double_up(f.command_id(), 2);
  ok(doubled);
  LMDJ_CHECK(doubled.at("result").at("bars") == 4);
  ok(f.app->command({{"operation", "pattern.slot.assign"},
      {"project_path", f.project.generic_string()}, {"command_id", f.command_id()},
      {"expected_revision", 3}, {"pattern_slot", 7}, {"pattern_id", pattern_id}}));

  const auto copy = f.command_id();
  const auto copied = f.copy(copy, 4);
  ok(copied);
  LMDJ_CHECK(copied.at("result").at("committed_revision") == 5);
  LMDJ_CHECK(copied.at("result").at("source_pattern_id") == pattern_id);
  LMDJ_CHECK(copied.at("result").at("pattern_id") == copy_id);
  LMDJ_CHECK(copied.at("result").at("pattern_slot") == 8);
  const auto retried = f.copy(copy, 4);
  ok(retried);
  LMDJ_CHECK(retried.at("result").at("replayed") == true);
  LMDJ_CHECK(retried.at("result").at("pattern_slot") == 8);

  f.restart();
  const auto project = f.project_json();
  LMDJ_CHECK(project.at("revision") == 5);
  LMDJ_CHECK(project.at("patterns").at(pattern_id).at("bars") == 4);
  LMDJ_CHECK(project.at("patterns").at(copy_id).at("bars") == 4);
  LMDJ_CHECK(project.at("pattern_slots").at(8) == copy_id);
}

void refused_length_changes_keep_truth() {
  LengthFixture f;
  const auto before = f.project_json();
  const auto unchanged = f.resize(f.command_id(), 1, 1);
  error(unchanged, "INVALID_ARGUMENT");
  LMDJ_CHECK(unchanged.at("error").at("details").at("reason") == "pattern_length_unchanged");
  error(f.resize(f.command_id(), 1, 3), "INVALID_ARGUMENT");
  error(f.resize(f.command_id(), 0, 2), "REVISION_CONFLICT");
  LMDJ_CHECK(f.project_json() == before);
  ok(f.resize(f.command_id(), 1, 8));
  const auto at_eight = f.project_json();
  const auto longest = f.double_up(f.command_id(), 2);
  error(longest, "INVALID_ARGUMENT");
  LMDJ_CHECK(longest.at("error").at("details").at("reason") == "pattern_length_maximum");
  LMDJ_CHECK(f.project_json() == at_eight);
  ok(f.copy(f.command_id(), 2));
  const auto copied = f.project_json();
  error(f.copy(f.command_id(), 3), "DUPLICATE_ID");
  LMDJ_CHECK(f.project_json() == copied);
}

void recording_session_refuses_each_operation() {
  LengthFixture f;
  ok(f.app->command({{"operation", "sequence.record.begin"},
      {"project_path", f.project.generic_string()}, {"session_id", session_id},
      {"pattern_id", pattern_id}, {"expected_revision", 1}, {"runtime_frame", 0}}));
  const auto before = f.project_json();
  for (const auto& refused : {f.resize(f.command_id(), 1, 2),
                              f.double_up(f.command_id(), 1),
                              f.copy(f.command_id(), 1)}) {
    error(refused, "INVALID_ARGUMENT");
    LMDJ_CHECK(refused.at("error").at("details").at("reason") == "sequence_session_active");
  }
  LMDJ_CHECK(f.project_json() == before);
}
}  // namespace

int main() {
  try {
    length_changes_and_a_slotted_copy_commit_replay_and_persist();
    refused_length_changes_keep_truth();
    recording_session_refuses_each_operation();
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
  std::cout << "facade pattern length and copy tests: PASS\n";
  return 0;
}
