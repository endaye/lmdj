#include "candidate_fixture.hpp"

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/project_io/project_store.hpp>

namespace {
using namespace lmdj::facade;
constexpr auto pattern_id = "00000000-0000-4000-8000-000000000030";
constexpr auto session_id = "00000000-0000-4000-8000-000000000031";

// Pad colour has no Provider dependency; a neutral Facade keeps the test
// independent of any Product Assembly identity. Pads 0..3 hold one Asset each,
// one per combination of an Asset category and a Pad override; Pad 4 is empty.
struct ColourFixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-pad-colour-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path project = root / "colour.lmdj";
  std::unique_ptr<Application> app;
  unsigned next_command = 0x40;
  ColourFixture() {
    std::filesystem::create_directories(root);
    // The Facade creates a legal v5 Project; Project I/O then writes the
    // categorised and overridden Pads the Facade has no command to author.
    const auto seed = root / "seed.lmdj";
    restart();
    ok(app->command({{"operation", "project.create"}, {"project_path", seed.generic_string()},
        {"project_id", project_id}, {"bpm", 120}}));
    app.reset();
    ProjectStore store;
    auto state = store.load(seed).value();
    const std::array<std::optional<lmdj::domain::AssetCategory>, 4> categories{
        lmdj::domain::AssetCategory::drums, lmdj::domain::AssetCategory::bass,
        std::nullopt, std::nullopt};
    const std::array<std::optional<std::uint8_t>, 4> overrides{
        std::nullopt, std::uint8_t{3}, std::nullopt, std::uint8_t{0}};
    std::vector<std::pair<std::filesystem::path, std::string>> blobs;
    for (std::uint8_t pad = 0; pad < 4; ++pad) {
      char id[40];
      std::snprintf(id, sizeof id, "00000000-0000-4000-8000-0000000001%02x", pad);
      const auto source = root / ("colour-" + std::to_string(pad) + ".wav");
      write(source, "RIFF-pad-colour-" + std::to_string(pad));
      const auto artifact = describe_artifact(source, "audio/wav");
      LMDJ_CHECK(artifact.has_value());
      const AssetId asset{id};
      state.assets.emplace(asset, lmdj::domain::Asset{
          asset, artifact.value(), std::nullopt, categories.at(pad)});
      state.banks.at(0).at(pad).asset_id = asset;
      state.banks.at(0).at(pad).colour = overrides.at(pad);
      blobs.emplace_back(source, artifact.value().sha256);
    }
    LMDJ_CHECK(store.create(project, state).has_value());
    for (const auto& [source, sha256] : blobs) {
      std::filesystem::copy_file(source, project / "assets" / (sha256 + ".wav"),
          std::filesystem::copy_options::overwrite_existing);
    }
    restart();
  }
  ~ColourFixture() { app.reset(); std::error_code error; std::filesystem::remove_all(root, error); }
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
  Json pad(int index) { return project_json().at("banks").at(0).at("pads").at(index); }
  Json set(const std::string& id, std::uint64_t revision, int pad, Json colour) {
    return app->command({{"operation", "pad.colour.set"},
        {"project_path", project.generic_string()}, {"command_id", id},
        {"expected_revision", revision}, {"slot", {{"bank", 0}, {"pad", pad}}},
        {"colour", std::move(colour)}});
  }
};

Json colours(const Json& pad) {
  return {pad.at("category"), pad.at("colour_override"), pad.at("colour")};
}

void inspection_projects_the_core_resolver() {
  ColourFixture f;
  // Category default; override over category; neutral; override without a
  // category; an empty Pad is neutral.
  LMDJ_CHECK(colours(f.pad(0)) == Json::array({"drums", nullptr, 0}));
  LMDJ_CHECK(colours(f.pad(1)) == Json::array({"bass", 3, 3}));
  LMDJ_CHECK(colours(f.pad(2)) == Json::array({nullptr, nullptr, nullptr}));
  LMDJ_CHECK(colours(f.pad(3)) == Json::array({nullptr, 0, 0}));
  LMDJ_CHECK(colours(f.pad(4)) == Json::array({nullptr, nullptr, nullptr}));
  LMDJ_CHECK(f.pad(4).at("asset_id").is_null());
}

void set_change_restore_replay_and_persist() {
  ColourFixture f;
  const auto set = f.set(f.command_id(), 0, 0, 2);
  ok(set);
  // A colour changes no audio: the result asks for no Runtime projection.
  LMDJ_CHECK(set.at("result") == Json({{"committed_revision", 1},
      {"slot", {{"bank", 0}, {"pad", 0}}}, {"replayed", false}}));
  LMDJ_CHECK(set.at("project_revision") == 1);
  LMDJ_CHECK(colours(f.pad(0)) == Json::array({"drums", 2, 2}));

  ok(f.set(f.command_id(), 1, 0, 4));
  LMDJ_CHECK(colours(f.pad(0)) == Json::array({"drums", 4, 4}));

  // Restoring removes the override; the category default shows again.
  const auto restore = f.command_id();
  ok(f.set(restore, 2, 0, nullptr));
  LMDJ_CHECK(colours(f.pad(0)) == Json::array({"drums", nullptr, 0}));
  const auto restored = f.project_json();

  const auto retried = f.set(restore, 2, 0, nullptr);
  ok(retried);
  LMDJ_CHECK(retried.at("result").at("replayed") == true);
  LMDJ_CHECK(retried.at("result").at("committed_revision") == 3);
  LMDJ_CHECK(f.project_json() == restored);

  ok(f.set(f.command_id(), 3, 1, nullptr));
  LMDJ_CHECK(colours(f.pad(1)) == Json::array({"bass", nullptr, 1}));
  f.restart();
  LMDJ_CHECK(f.project_json().at("revision") == 4);
  LMDJ_CHECK(colours(f.pad(0)) == Json::array({"drums", nullptr, 0}));
  LMDJ_CHECK(colours(f.pad(1)) == Json::array({"bass", nullptr, 1}));
}

void refusals_keep_truth() {
  ColourFixture f;
  const auto before = f.project_json();
  const auto reason = [](const Json& response) {
    return response.at("error").at("details").value("reason", "");
  };
  error(f.set(f.command_id(), 1, 0, 2), "REVISION_CONFLICT");
  const auto empty = f.set(f.command_id(), 0, 4, 2);
  error(empty, "INVALID_ARGUMENT");
  LMDJ_CHECK(reason(empty) == "pad_empty");
  const auto range = f.set(f.command_id(), 0, 0, 5);
  error(range, "INVALID_ARGUMENT");
  LMDJ_CHECK(reason(range) == "pad_colour_out_of_range");
  const auto unchanged = f.set(f.command_id(), 0, 1, 3);
  error(unchanged, "INVALID_ARGUMENT");
  LMDJ_CHECK(reason(unchanged) == "pad_colour_unchanged");
  // Shape errors: wider than a palette index, a non-index, a bad slot.
  error(f.set(f.command_id(), 0, 0, 256), "INVALID_ARGUMENT");
  error(f.set(f.command_id(), 0, 0, "red"), "INVALID_ARGUMENT");
  error(f.set(f.command_id(), 0, 16, 1), "INVALID_ARGUMENT");
  error(f.app->command({{"operation", "pad.colour.set"},
      {"project_path", f.project.generic_string()}, {"command_id", f.command_id()},
      {"expected_revision", 0}, {"slot", {{"bank", 0}, {"pad", 0}}}}), "INVALID_ARGUMENT");
  LMDJ_CHECK(f.project_json() == before);
}

void recording_session_refuses_colour() {
  ColourFixture f;
  ok(f.app->command({{"operation", "pattern.create"}, {"project_path", f.project.generic_string()},
      {"command_id", other_id}, {"expected_revision", 0}, {"pattern_id", pattern_id}, {"bars", 1}}));
  ok(f.app->command({{"operation", "sequence.record.begin"},
      {"project_path", f.project.generic_string()}, {"session_id", session_id},
      {"pattern_id", pattern_id}, {"expected_revision", 1}, {"runtime_frame", 0}}));
  const auto before = f.project_json();
  const auto refused = f.set(f.command_id(), 1, 0, 2);
  error(refused, "INVALID_ARGUMENT");
  LMDJ_CHECK(refused.at("error").at("details").at("reason") == "sequence_session_active");
  LMDJ_CHECK(f.project_json() == before);
}
}  // namespace

int main() {
  try {
    inspection_projects_the_core_resolver();
    set_change_restore_replay_and_persist();
    refusals_keep_truth();
    recording_session_refuses_colour();
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
  std::cout << "facade pad colour tests: PASS\n";
  return 0;
}
