#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include <picosha2.h>

#include <fcntl.h>
#include <nlohmann/json.hpp>
#include <sys/file.h>
#include <sys/wait.h>
#include <unistd.h>

#include <lmdj/facade/c_api.h>

#include "tests/core/support/test.hpp"

namespace {

// High-volume repetition belongs to facade.c_api_stress. Keep this component
// proof bounded so its sanitizer build retains headroom under the tier timeout.
constexpr std::size_t kComponentRepetitions = 128;
static_assert(kComponentRepetitions <= 256);

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-c-api-test-" + std::to_string(nonce));
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

class ScopedRegularFile {
 public:
  explicit ScopedRegularFile(std::filesystem::path path)
      : path_(std::move(path)) {
    std::filesystem::create_directories(path_.parent_path());
    std::ofstream stream(path_, std::ios::binary | std::ios::trunc);
    LMDJ_CHECK(static_cast<bool>(stream));
  }

  ~ScopedRegularFile() {
    std::error_code error;
    std::filesystem::remove(path_, error);
  }

  ScopedRegularFile(const ScopedRegularFile&) = delete;
  ScopedRegularFile& operator=(const ScopedRegularFile&) = delete;

 private:
  std::filesystem::path path_;
};

std::filesystem::path default_project_writer_lease_root() {
#if defined(__APPLE__)
  if (const char* home = std::getenv("HOME");
      home != nullptr && home[0] != '\0') {
    const std::filesystem::path home_path{home};
    if (home_path.is_absolute()) {
      return home_path / "Library/Application Support/LMDJ" /
             "project-writer-leases";
    }
  }
#else
  if (const char* state = std::getenv("XDG_STATE_HOME");
      state != nullptr && state[0] != '\0') {
    const std::filesystem::path state_path{state};
    if (state_path.is_absolute()) {
      return state_path / "lmdj/project-writer-leases";
    }
  }
  if (const char* home = std::getenv("HOME");
      home != nullptr && home[0] != '\0') {
    const std::filesystem::path home_path{home};
    if (home_path.is_absolute()) {
      return home_path / ".local/state/lmdj/project-writer-leases";
    }
  }
#endif
  std::error_code error;
  auto temporary = std::filesystem::temp_directory_path(error);
  if (error || !temporary.is_absolute()) {
    temporary = "/tmp";
  }
  return temporary /
         ("lmdj-" + std::to_string(static_cast<unsigned long>(::geteuid()))) /
         "project-writer-leases";
}

std::filesystem::path normalized_project_path(
    const std::filesystem::path& path) {
  auto normalized = std::filesystem::absolute(path).lexically_normal();
#if defined(__APPLE__)
  const auto relative = normalized.relative_path();
  if (!relative.empty()) {
    const auto first = *relative.begin();
    if (first == "var" || first == "tmp") {
      normalized = std::filesystem::path{"/private"} / relative;
    }
  }
#endif
  return normalized;
}

std::string config_json(const std::filesystem::path& root) {
  return nlohmann::json{{"workspace_root", root.generic_string()}}.dump();
}

std::string assembly_config_json(
    const std::filesystem::path& root,
    const std::filesystem::path& assembly) {
  return nlohmann::json{
      {"workspace_root", root.generic_string()},
      {"assembly_path", assembly.generic_string()},
  }.dump();
}

nlohmann::json command(
    lmdj_engine* engine,
    const nlohmann::json& request) {
  char* response = nullptr;
  const auto encoded = request.dump();
  LMDJ_CHECK(
      lmdj_engine_command(engine, encoded.c_str(), &response) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(response != nullptr);
  auto parsed = nlohmann::json::parse(response);
  lmdj_string_free(response);
  return parsed;
}

nlohmann::json query(
    lmdj_engine* engine,
    const nlohmann::json& request) {
  char* response = nullptr;
  const auto encoded = request.dump();
  LMDJ_CHECK(
      lmdj_engine_query(engine, encoded.c_str(), &response) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(response != nullptr);
  auto parsed = nlohmann::json::parse(response);
  lmdj_string_free(response);
  return parsed;
}

void check_facade_error(
    const nlohmann::json& response,
    std::string_view code) {
  LMDJ_CHECK(response.at("ok") == false);
  LMDJ_CHECK(response.at("error").at("code") == code);
}

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" +
         std::string(12 - tail.size(), '0') + tail;
}

nlohmann::json sample_playback(
    std::uint64_t start = 0,
    nlohmann::json end = nullptr,
    std::string_view mode = "one_shot",
    std::int32_t gain = 0,
    bool muted = false) {
  return {
      {"trim_start_frame", start},
      {"trim_end_frame", std::move(end)},
      {"trigger_mode", mode},
      {"gain_millidb", gain},
      {"muted", muted},
  };
}

void write_bytes(
    const std::filesystem::path& path,
    std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  if (!stream) {
    throw std::runtime_error("C ABI fixture could not be written");
  }
}

void test_create_command_query_and_owned_strings() {
  TempDirectory temp;
  lmdj_engine* engine = nullptr;
  char* error = reinterpret_cast<char*>(0x1);
  const auto config = config_json(temp.path());
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &engine, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(engine != nullptr);
  LMDJ_CHECK(error == nullptr);

  const auto project = temp.path() / "abi.lmdj";
  const auto create = nlohmann::json{
      {"operation", "project.create"},
      {"project_path", project.generic_string()},
      {"project_id", "00000000-0000-4000-8000-000000000001"},
      {"bpm", 120},
  }.dump();
  char* response = reinterpret_cast<char*>(0x1);
  LMDJ_CHECK(
      lmdj_engine_command(engine, create.c_str(), &response) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(response != nullptr);
  LMDJ_CHECK(nlohmann::json::parse(response).at("ok") == true);
  lmdj_string_free(response);

  const auto inspect = nlohmann::json{
      {"operation", "project.inspect"},
      {"project_path", project.generic_string()},
  }.dump();
  for (std::size_t index = 0; index < kComponentRepetitions; ++index) {
    response = reinterpret_cast<char*>(0x1);
    LMDJ_CHECK(
        lmdj_engine_query(engine, inspect.c_str(), &response) ==
        LMDJ_STATUS_OK);
    LMDJ_CHECK(response != nullptr);
    LMDJ_CHECK(nlohmann::json::parse(response).at("ok") == true);
    lmdj_string_free(response);
  }

  const std::string non_ascii_path =
      (temp.path() / "音乐.lmdj").generic_string();
  const auto non_ascii = nlohmann::json{
      {"operation", "project.inspect"},
      {"project_path", non_ascii_path},
  }.dump();
  response = nullptr;
  LMDJ_CHECK(
      lmdj_engine_query(engine, non_ascii.c_str(), &response) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(response != nullptr);
  const std::string round_trip(response);
  LMDJ_CHECK(round_trip.find(non_ascii_path) != std::string::npos);
  lmdj_string_free(response);

  lmdj_string_free(nullptr);
  lmdj_engine_free(engine);
  lmdj_engine_free(engine);
}

void test_assembly_composition_through_c_abi() {
  TempDirectory temp;
  const auto assembly =
      std::filesystem::absolute("products/lmdj/assembly.json");
  const auto config = assembly_config_json(temp.path(), assembly);
  lmdj_engine* engine = nullptr;
  char* error = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &engine, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(engine != nullptr);
  LMDJ_CHECK(error == nullptr);

  const auto provider_list =
      nlohmann::json{{"operation", "provider.list"}}.dump();
  char* response = nullptr;
  LMDJ_CHECK(
      lmdj_engine_query(engine, provider_list.c_str(), &response) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(response != nullptr);
  const auto parsed = nlohmann::json::parse(response);
  lmdj_string_free(response);
  const auto& providers = parsed.at("result").at("providers");
  LMDJ_CHECK(providers.size() == 2);
  LMDJ_CHECK(providers.at(0).at("id") == "local.proof.failure");
  LMDJ_CHECK(providers.at(1).at("id") == "local.proof.success");
  lmdj_engine_free(engine);

  const auto invalid = assembly_config_json(
      temp.path(), temp.path() / "missing-assembly.json");
  engine = reinterpret_cast<lmdj_engine*>(0x1);
  error = reinterpret_cast<char*>(0x1);
  LMDJ_CHECK(
      lmdj_engine_create(invalid.c_str(), &engine, &error) ==
      LMDJ_STATUS_INVALID_ARGUMENT);
  LMDJ_CHECK(engine == nullptr);
  LMDJ_CHECK(error == nullptr);
}

void test_sequence_surface_is_routed_through_c_abi() {
  {
    TempDirectory temp;
    const auto config = config_json(temp.path());
    lmdj_engine* engine = nullptr;
    char* error = nullptr;
    LMDJ_CHECK(
        lmdj_engine_create(config.c_str(), &engine, &error) == LMDJ_STATUS_OK);
    LMDJ_CHECK(error == nullptr);
    const auto project = temp.path() / "sequence-surface.lmdj";
    LMDJ_CHECK(command(engine,
                       {{"operation", "project.create"},
                        {"project_path", project.generic_string()},
                        {"project_id", uuid(1)},
                        {"bpm", 120}})
                   .at("ok") == true);
    check_facade_error(
        command(engine,
                {{"operation", "sequence.record.begin"},
                 {"project_path", project.generic_string()},
                 {"session_id", uuid(201)},
                 {"pattern_id", uuid(10)},
                 {"expected_revision", 0},
                 {"runtime_frame", 0}}),
        "NOT_FOUND");
    const auto status = query(
        engine,
        {{"operation", "sequence.record.status"},
         {"project_path", project.generic_string()}});
    LMDJ_CHECK(status.at("ok") == true);
    LMDJ_CHECK(status.at("result").at("state") == "inactive");
    const auto recovery = query(
        engine,
        {{"operation", "sequence.recovery.list"},
         {"project_path", project.generic_string()}});
    LMDJ_CHECK(recovery.at("ok") == true);
    LMDJ_CHECK(recovery.at("result").at("candidates").empty());
    lmdj_engine_free(engine);
    return;
  }
  TempDirectory temp;
  const auto config = config_json(temp.path());
  lmdj_engine* engine = nullptr;
  char* error = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &engine, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(error == nullptr);

  const auto project = temp.path() / "replay-identity.lmdj";
  auto response = command(
      engine,
      {
          {"operation", "project.create"},
          {"project_path", project.generic_string()},
          {"project_id", uuid(1)},
          {"bpm", 120},
      });
  LMDJ_CHECK(response.at("ok") == true);
  response = command(
      engine,
      {
          {"operation", "pad.assign"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(51)},
          {"expected_revision", 0},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"asset_id", nullptr},
      });
  LMDJ_CHECK(response.at("ok") == true);
  response = command(
      engine,
      {
          {"operation", "take.begin"},
          {"project_path", project.generic_string()},
          {"take_id", uuid(201)},
          {"expected_revision", 1},
          {"sample_rate", 48000},
      });
  LMDJ_CHECK(response.at("ok") == true);

  const auto replay_request = nlohmann::json{
      {"operation", "take.commit"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(52)},
      {"expected_revision", 1},
      {"take_id", uuid(201)},
      {"pattern",
       {
           {"pattern_id", uuid(10)},
           {"bars", 1},
           {"events", nlohmann::json::array()},
       }},
  };
  response = command(engine, replay_request);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("result").at("replayed") == false);
  response = command(engine, replay_request);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  auto cross_operation = replay_request;
  cross_operation["command_id"] = uuid(51);
  cross_operation["expected_revision"] = 0;
  check_facade_error(
      command(engine, cross_operation), "INVALID_ARGUMENT");

  std::vector<nlohmann::json> changed_requests;
  auto changed_revision = replay_request;
  changed_revision["expected_revision"] = 2;
  changed_requests.push_back(std::move(changed_revision));
  auto changed_take = replay_request;
  changed_take["take_id"] = uuid(299);
  changed_requests.push_back(std::move(changed_take));
  auto changed_pattern_id = replay_request;
  changed_pattern_id["pattern"]["pattern_id"] = uuid(99);
  changed_requests.push_back(std::move(changed_pattern_id));
  auto changed_pattern_bars = replay_request;
  changed_pattern_bars["pattern"]["bars"] = 2;
  changed_requests.push_back(std::move(changed_pattern_bars));
  auto changed_pattern_event = replay_request;
  changed_pattern_event["pattern"]["events"].push_back(
      {
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"step", 0},
          {"velocity", 127},
      });
  changed_requests.push_back(std::move(changed_pattern_event));
  for (const auto& changed : changed_requests) {
    check_facade_error(
        command(engine, changed), "INVALID_ARGUMENT");
  }

  lmdj_engine* fresh = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &fresh, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(error == nullptr);
  response = command(fresh, replay_request);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("project_revision") == 2);
  LMDJ_CHECK(response.at("result").at("take_id") == uuid(201));
  LMDJ_CHECK(response.at("result").at("pattern_id") == uuid(10));
  LMDJ_CHECK(response.at("result").at("committed_revision") == 2);
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  lmdj_engine_free(fresh);
  lmdj_engine_free(engine);
}

void test_asset_and_pad_replay_identity_through_c_abi() {
  TempDirectory temp;
  const auto config = config_json(temp.path());
  const auto source = temp.path() / "source-a.wav";
  const auto changed_source = temp.path() / "source-b.wav";
  write_bytes(source, "source-a");
  write_bytes(changed_source, "source-b");
  lmdj_engine* engine = nullptr;
  char* error = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &engine, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(error == nullptr);

  const auto project = temp.path() / "asset-pad-identity.lmdj";
  LMDJ_CHECK(
      command(
          engine,
          {
              {"operation", "project.create"},
              {"project_path", project.generic_string()},
              {"project_id", uuid(1)},
              {"bpm", 120},
          })
          .at("ok") == true);
  const auto import = nlohmann::json{
      {"operation", "asset.import"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(81)},
      {"expected_revision", 0},
      {"asset_id", uuid(101)},
      {"source_path", source.generic_string()},
      {"media_type", "audio/wav"},
  };
  auto response = command(engine, import);
  LMDJ_CHECK(response.at("ok") == true);
  response = command(engine, import);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("result").at("asset_id") == uuid(101));
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  std::vector<nlohmann::json> changed_imports;
  auto changed_revision = import;
  changed_revision["expected_revision"] = 1;
  changed_imports.push_back(std::move(changed_revision));
  auto changed_asset = import;
  changed_asset["asset_id"] = uuid(199);
  changed_imports.push_back(std::move(changed_asset));
  auto changed_bytes = import;
  changed_bytes["source_path"] = changed_source.generic_string();
  changed_imports.push_back(std::move(changed_bytes));
  auto changed_media = import;
  changed_media["media_type"] = "application/octet-stream";
  changed_imports.push_back(std::move(changed_media));
  for (const auto& changed : changed_imports) {
    check_facade_error(
        command(engine, changed), "INVALID_ARGUMENT");
  }

  auto import_id_as_pad = nlohmann::json{
      {"operation", "pad.assign"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(81)},
      {"expected_revision", 0},
      {"slot", {{"bank", 0}, {"pad", 0}}},
      {"asset_id", uuid(101)},
  };
  check_facade_error(
      command(engine, import_id_as_pad), "INVALID_ARGUMENT");

  const auto assignment = nlohmann::json{
      {"operation", "pad.assign"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(82)},
      {"expected_revision", 1},
      {"slot", {{"bank", 0}, {"pad", 0}}},
      {"asset_id", uuid(101)},
  };
  response = command(engine, assignment);
  LMDJ_CHECK(response.at("ok") == true);
  response = command(engine, assignment);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(
      (response.at("result").at("slot") ==
       nlohmann::json{{"bank", 0}, {"pad", 0}}));
  LMDJ_CHECK(response.at("result").at("asset_id") == uuid(101));
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  std::vector<nlohmann::json> changed_assignments;
  auto changed_pad_revision = assignment;
  changed_pad_revision["expected_revision"] = 2;
  changed_assignments.push_back(std::move(changed_pad_revision));
  auto changed_slot = assignment;
  changed_slot["slot"]["pad"] = 1;
  changed_assignments.push_back(std::move(changed_slot));
  auto changed_assignment = assignment;
  changed_assignment["asset_id"] = nullptr;
  changed_assignments.push_back(std::move(changed_assignment));
  for (const auto& changed : changed_assignments) {
    check_facade_error(
        command(engine, changed), "INVALID_ARGUMENT");
  }

  auto pad_id_as_import = import;
  pad_id_as_import["command_id"] = uuid(82);
  pad_id_as_import["expected_revision"] = 1;
  check_facade_error(
      command(engine, pad_id_as_import), "INVALID_ARGUMENT");

  lmdj_engine* fresh = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &fresh, &error) ==
      LMDJ_STATUS_OK);
  response = command(fresh, import);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("project_revision") == 2);
  LMDJ_CHECK(response.at("result").at("asset_id") == uuid(101));
  LMDJ_CHECK(response.at("result").at("committed_revision") == 1);
  LMDJ_CHECK(response.at("result").at("replayed") == true);
  response = command(fresh, assignment);
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("project_revision") == 2);
  LMDJ_CHECK(response.at("result").at("asset_id") == uuid(101));
  LMDJ_CHECK(response.at("result").at("committed_revision") == 2);
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  lmdj_engine_free(fresh);
  lmdj_engine_free(engine);
}

void test_sample_operations_have_exact_shapes_and_private_errors() {
  TempDirectory temp;
  const auto config = config_json(temp.path());
  lmdj_engine* engine = nullptr;
  char* error = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &engine, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(error == nullptr);

  const auto project = temp.path() / "sample-c-api.lmdj";
  auto response = command(
      engine,
      {
          {"operation", "project.create"},
          {"project_path", project.generic_string()},
          {"project_id", uuid(701)},
          {"bpm", 120},
      });
  LMDJ_CHECK(response.at("ok") == true);
  response = command(
      engine,
      {
          {"operation", "asset.import"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(702)},
          {"expected_revision", 0},
          {"asset_id", uuid(703)},
          {"source_path",
           std::filesystem::absolute(
               "tests/fixtures/audio/mono-44100.wav")
               .generic_string()},
          {"media_type", "audio/wav"},
      });
  LMDJ_CHECK(response.at("ok") == true);
  response = command(
      engine,
      {
          {"operation", "pad.assign"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(704)},
          {"expected_revision", 1},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"asset_id", uuid(703)},
      });
  LMDJ_CHECK(response.at("ok") == true);

  response = query(
      engine,
      {
          {"operation", "sample.inspect"},
          {"project_path", project.generic_string()},
          {"slot", {{"bank", 0}, {"pad", 0}}},
      });
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("project_revision") == 2);
  const auto& inspected = response.at("result");
  LMDJ_CHECK(inspected.size() == 6);
  for (const auto* key : {
           "project_revision",
           "slot",
           "asset_id",
           "playback",
           "metadata",
           "waveform_cache_identity",
       }) {
    LMDJ_CHECK(inspected.contains(key));
  }
  LMDJ_CHECK(inspected.at("metadata").at("sample_rate") == 44'100);
  LMDJ_CHECK(inspected.at("metadata").at("source_frames") == 8);
  LMDJ_CHECK(inspected.at("playback") == sample_playback());

  response = query(
      engine,
      {
          {"operation", "sample.waveform"},
          {"project_path", project.generic_string()},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"window",
           {{"start_frame", 0},
            {"end_frame", 8},
            {"bucket_count", 4}}},
      });
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("project_revision") == 2);
  LMDJ_CHECK(response.at("result").size() == 3);
  LMDJ_CHECK(response.at("result").at("algorithm_version") == 1);
  LMDJ_CHECK(response.at("result").at("buckets").size() == 4);
  LMDJ_CHECK((
      response.at("result").at("buckets").at(0) ==
      nlohmann::json{
          {"start_frame", 0},
          {"end_frame", 2},
          {"peak_magnitude", 32'768},
      }));

  response = command(
      engine,
      {
          {"operation", "sample.update_pad"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(705)},
          {"expected_revision", 2},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"playback", sample_playback(1, 7, "loop_toggle", -1'200, true)},
      });
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("project_revision") == 3);
  LMDJ_CHECK((
      response.at("result") ==
      nlohmann::json{
          {"committed_revision", 3},
          {"runtime_prepare_required", true},
      }));
  response = command(
      engine,
      {
          {"operation", "sample.reset_pad"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(706)},
          {"expected_revision", 3},
          {"slot", {{"bank", 0}, {"pad", 0}}},
      });
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("project_revision") == 4);

  const auto conflicted = command(
      engine,
      {
          {"operation", "sample.update_pad"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(711)},
          {"expected_revision", 3},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"playback", sample_playback()},
      });
  check_facade_error(conflicted, "REVISION_CONFLICT");
  LMDJ_CHECK((
      conflicted.at("error").at("details") ==
      nlohmann::json{
          {"actual_revision", 4},
          {"expected_revision", 3},
      }));
  LMDJ_CHECK(
      conflicted.at("error").at("message") ==
      "Project revision changed");

  const auto valid_token = uuid(707);
  check_facade_error(
      command(
          engine,
          {
              {"operation", "sample.import.begin"},
              {"import_token", valid_token},
              {"project_path", project.generic_string()},
              {"command_id", uuid(708)},
              {"expected_revision", 4},
              {"slot", {{"bank", 0}, {"pad", 0}}},
              {"asset_id", uuid(709)},
              {"byte_length", 60},
          }),
      "INVALID_ARGUMENT");
  check_facade_error(
      command(
          engine,
          {
              {"operation", "sample.import.chunk"},
              {"import_token", valid_token},
              {"offset", 0},
              {"final", true},
              {"sidecar",
               {{"sidecar_bytes", 60},
                {"sidecar_sha256", std::string(64, '0')}}},
          }),
      "INVALID_ARGUMENT");

  std::vector<nlohmann::json> rejected_requests{
      {{"operation", "sample.inspect"},
       {"project_path", project.generic_string()},
       {"slot", {{"bank", 0}, {"pad", 0}}},
       {"filename", "private.wav"}},
      {{"operation", "sample.waveform"},
       {"project_path", project.generic_string()},
       {"slot", {{"bank", 0}, {"pad", 0}}},
       {"window",
        {{"start_frame", 0}, {"end_frame", 8}, {"bucket_count", 513}}}},
      {{"operation", "sample.waveform"},
       {"project_path", project.generic_string()},
       {"slot", {{"bank", 4}, {"pad", 0}}},
       {"window",
        {{"start_frame", 0}, {"end_frame", 8}, {"bucket_count", 4}}}},
      {{"operation", "sample.update_pad"},
       {"project_path", project.generic_string()},
       {"command_id", "not-a-uuid"},
       {"expected_revision", 4},
       {"slot", {{"bank", 0}, {"pad", 0}}},
       {"playback", sample_playback()}},
      {{"operation", "sample.reset_pad"},
       {"project_path", project.generic_string()},
       {"command_id", uuid(710)},
       {"expected_revision", -1},
       {"slot", {{"bank", 0}, {"pad", 0}}}},
      {{"operation", "sample.import.chunk"},
       {"import_token", valid_token},
       {"offset", 0},
       {"final", true},
       {"sidecar",
        {{"sidecar_bytes", 3}, {"sidecar_sha256", std::string(64, '0')}}},
       {"bytes", nlohmann::json::array({1, 2, 3})}},
      {{"operation", "sample.import.chunk"},
       {"import_token", valid_token},
       {"offset", 0},
       {"final", true},
       {"sidecar",
        {{"sidecar_bytes", 3}, {"sidecar_sha256", std::string(64, '0')}}},
       {"path", "/private/audio.wav"}},
      {{"operation", "sample.import.commit"},
       {"import_token", "not-a-uuid"}},
      {{"operation", "sample.import.abort"},
       {"import_token", valid_token},
       {"filename", "private.wav"}},
  };
  for (const auto& request : rejected_requests) {
    const auto surface = request.at("operation").get<std::string>() ==
                                 "sample.inspect" ||
                             request.at("operation").get<std::string>() ==
                                 "sample.waveform"
                         ? query(engine, request)
                         : command(engine, request);
    check_facade_error(surface, "INVALID_ARGUMENT");
    LMDJ_CHECK(surface.at("error").at("details").empty());
    LMDJ_CHECK(
        surface.at("error").at("message") == "Sample request is invalid");
    const auto encoded = surface.dump();
    LMDJ_CHECK(encoded.find("private.wav") == std::string::npos);
    LMDJ_CHECK(encoded.find("/private/audio.wav") == std::string::npos);
  }

  const auto missing_project = temp.path() / "private-missing.lmdj";
  const auto private_error = query(
      engine,
      {
          {"operation", "sample.inspect"},
          {"project_path", missing_project.generic_string()},
          {"slot", {{"bank", 0}, {"pad", 0}}},
      });
  check_facade_error(private_error, "IO_ERROR");
  LMDJ_CHECK(private_error.at("error").at("details").empty());
  LMDJ_CHECK(
      private_error.at("error").at("message") ==
      "Sample storage operation failed");
  const auto encoded_error = private_error.dump();
  LMDJ_CHECK(
      encoded_error.find(missing_project.generic_string()) ==
      std::string::npos);
  LMDJ_CHECK(encoded_error.size() < 512);

  const auto replayed_update = command(
      engine,
      {
          {"operation", "sample.update_pad"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(705)},
          {"expected_revision", 2},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"playback", sample_playback(1, 7, "loop_toggle", -1'200, true)},
      });
  LMDJ_CHECK(replayed_update.at("ok") == true);
  LMDJ_CHECK(
      replayed_update.at("result").at("committed_revision") == 3);
  const auto advanced = command(
      engine,
      {
          {"operation", "sample.update_pad"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(712)},
          {"expected_revision", 4},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"playback", sample_playback(1, 7, "loop_gate", -600, false)},
      });
  LMDJ_CHECK(advanced.at("ok") == true);
  LMDJ_CHECK(advanced.at("project_revision") == 5);
  const auto replayed_reset = command(
      engine,
      {
          {"operation", "sample.reset_pad"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(706)},
          {"expected_revision", 3},
          {"slot", {{"bank", 0}, {"pad", 0}}},
      });
  LMDJ_CHECK(replayed_reset.at("ok") == true);
  LMDJ_CHECK(
      replayed_reset.at("result").at("committed_revision") == 4);
  const auto update_revision =
      replayed_update.at("project_revision").get<std::uint64_t>();
  const auto reset_revision =
      replayed_reset.at("project_revision").get<std::uint64_t>();
  if (update_revision != 4 || reset_revision != 5) {
    throw std::runtime_error(
        "Sample C ABI replay revisions are stale: update=" +
        std::to_string(update_revision) +
        " reset=" + std::to_string(reset_revision));
  }

  lmdj_engine_free(engine);
}

void test_transport_failures_null_outputs_and_valid_facade_errors() {
  TempDirectory temp;
  const auto config = config_json(temp.path());
  lmdj_engine* engine = reinterpret_cast<lmdj_engine*>(0x1);
  char* error = reinterpret_cast<char*>(0x1);

  LMDJ_CHECK(
      lmdj_engine_create(nullptr, &engine, &error) != LMDJ_STATUS_OK);
  LMDJ_CHECK(engine == nullptr);
  LMDJ_CHECK(error == nullptr);
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), nullptr, &error) !=
      LMDJ_STATUS_OK);
  LMDJ_CHECK(error == nullptr);
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &engine, nullptr) !=
      LMDJ_STATUS_OK);
  LMDJ_CHECK(engine == nullptr);

  const auto nul_config =
      nlohmann::json{
          {"workspace_root",
           temp.path().generic_string() + std::string("\0tail", 5)},
      }
          .dump();
  LMDJ_CHECK(
      lmdj_engine_create(nul_config.c_str(), &engine, &error) !=
      LMDJ_STATUS_OK);
  LMDJ_CHECK(engine == nullptr);
  LMDJ_CHECK(error == nullptr);

  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &engine, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(error == nullptr);
  char* response = reinterpret_cast<char*>(0x1);
  LMDJ_CHECK(
      lmdj_engine_command(nullptr, "{}", &response) != LMDJ_STATUS_OK);
  LMDJ_CHECK(response == nullptr);
  LMDJ_CHECK(
      lmdj_engine_command(engine, nullptr, &response) != LMDJ_STATUS_OK);
  LMDJ_CHECK(response == nullptr);
  LMDJ_CHECK(
      lmdj_engine_query(engine, "{}", nullptr) != LMDJ_STATUS_OK);

  for (const auto malformed : {
           "",
           " ",
           "[]",
           "42",
           "{} trailing",
           "{\"operation\":",
       }) {
    response = reinterpret_cast<char*>(0x1);
    LMDJ_CHECK(
        lmdj_engine_query(engine, malformed, &response) !=
        LMDJ_STATUS_OK);
    LMDJ_CHECK(response == nullptr);
  }
  const std::string invalid_utf8("\xc3\x28", 2);
  response = reinterpret_cast<char*>(0x1);
  LMDJ_CHECK(
      lmdj_engine_query(engine, invalid_utf8.c_str(), &response) !=
      LMDJ_STATUS_OK);
  LMDJ_CHECK(response == nullptr);

  for (const auto operation : {
           "unknown",
           "project.bundle.list",
           "project.bundle.import.begin",
           "project.bundle.import.commit",
       }) {
    response = nullptr;
    const auto request =
        nlohmann::json{{"operation", operation}}.dump();
    LMDJ_CHECK(
        lmdj_engine_query(engine, request.c_str(), &response) ==
        LMDJ_STATUS_OK);
    LMDJ_CHECK(response != nullptr);
    check_facade_error(
        nlohmann::json::parse(response), "INVALID_ARGUMENT");
    lmdj_string_free(response);
  }
  lmdj_engine_free(engine);
}

void test_stale_unknown_aba_and_racing_free_are_safe() {
  TempDirectory temp;
  const auto config = config_json(temp.path());
  char* error = nullptr;
  lmdj_engine* first = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &first, &error) ==
      LMDJ_STATUS_OK);
  lmdj_engine_free(first);

  lmdj_engine* second = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &second, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(second != first);
  char* response = reinterpret_cast<char*>(0x1);
  LMDJ_CHECK(
      lmdj_engine_query(first, "{}", &response) != LMDJ_STATUS_OK);
  LMDJ_CHECK(response == nullptr);
  LMDJ_CHECK(
      lmdj_engine_query(
          reinterpret_cast<lmdj_engine*>(
              static_cast<std::uintptr_t>(0x1)),
          "{}",
          &response) != LMDJ_STATUS_OK);
  LMDJ_CHECK(response == nullptr);

  const auto unknown =
      std::string("{\"operation\":\"unknown\"}");
  std::atomic<bool> started{false};
  std::thread worker([&] {
    started.store(true);
    for (std::size_t index = 0; index < kComponentRepetitions; ++index) {
      char* local = nullptr;
      const auto status =
          lmdj_engine_query(second, unknown.c_str(), &local);
      LMDJ_CHECK(
          status == LMDJ_STATUS_OK ||
          status == LMDJ_STATUS_INVALID_HANDLE);
      if (local != nullptr) {
        lmdj_string_free(local);
      }
    }
  });
  while (!started.load()) {
    std::this_thread::yield();
  }
  lmdj_engine_free(second);
  worker.join();
  lmdj_engine_free(second);
}

void test_busy_project_fails_fast_without_serializing_engines() {
  using namespace std::chrono_literals;
  TempDirectory temp;
  const auto config = config_json(temp.path());
  char* error = nullptr;
  lmdj_engine* blocked_engine = nullptr;
  lmdj_engine* independent_engine = nullptr;
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &blocked_engine, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(error == nullptr);
  LMDJ_CHECK(
      lmdj_engine_create(config.c_str(), &independent_engine, &error) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(error == nullptr);

  const auto project = temp.path() / "blocked-engine.lmdj";
  const auto lease_root = default_project_writer_lease_root();
  const ScopedRegularFile unrelated_lease{
      lease_root /
      (temp.path().filename().string() + ".unrelated-project.lock")};
  LMDJ_CHECK(
      command(
          blocked_engine,
          {
              {"operation", "project.create"},
              {"project_path", project.generic_string()},
              {"project_id", uuid(1)},
              {"bpm", 120},
          })
          .at("ok") == true);
  const auto lease_path =
      lease_root /
      (picosha2::hash256_hex_string(
           normalized_project_path(project).generic_string()) +
       ".lock");
  LMDJ_CHECK(std::filesystem::is_regular_file(lease_path));
  const int lease_fd = ::open(lease_path.c_str(), O_RDWR | O_CLOEXEC);
  LMDJ_CHECK(lease_fd >= 0);
  LMDJ_CHECK(::flock(lease_fd, LOCK_EX) == 0);

  auto busy_mutation = std::async(
      std::launch::async,
      [&]() {
        return command(
            blocked_engine,
            {
                {"operation", "pad.assign"},
                {"project_path", project.generic_string()},
                {"command_id", uuid(91)},
                {"expected_revision", 0},
                {"slot", {{"bank", 0}, {"pad", 0}}},
                {"asset_id", nullptr},
            });
      });
  const bool busy_completed =
      busy_mutation.wait_for(250ms) == std::future_status::ready;

  const auto provider_list =
      nlohmann::json{{"operation", "provider.list"}}.dump();
  auto same_engine = std::async(
      std::launch::async,
      [&]() {
        char* response = nullptr;
        const auto status = lmdj_engine_query(
            blocked_engine, provider_list.c_str(), &response);
        std::string value = response == nullptr ? "" : response;
        lmdj_string_free(response);
        return std::pair{status, std::move(value)};
      });
  auto independent = std::async(
      std::launch::async,
      [&]() {
        char* response = nullptr;
        const auto status = lmdj_engine_query(
            independent_engine, provider_list.c_str(), &response);
        std::string value = response == nullptr ? "" : response;
        lmdj_string_free(response);
        return std::pair{status, std::move(value)};
      });
  const bool same_engine_completed =
      same_engine.wait_for(250ms) == std::future_status::ready;
  const bool independent_completed =
      independent.wait_for(250ms) == std::future_status::ready;

  LMDJ_CHECK(::flock(lease_fd, LOCK_UN) == 0);
  LMDJ_CHECK(::close(lease_fd) == 0);
  const auto busy_response = busy_mutation.get();
  const auto same_engine_response = same_engine.get();
  const auto independent_response = independent.get();
  lmdj_engine_free(independent_engine);
  lmdj_engine_free(blocked_engine);

  LMDJ_CHECK(busy_completed);
  LMDJ_CHECK(same_engine_completed);
  LMDJ_CHECK(independent_completed);
  LMDJ_CHECK(busy_response.at("ok") == false);
  LMDJ_CHECK(busy_response.at("error").at("code") == "IO_ERROR");
  LMDJ_CHECK(
      busy_response.at("error")
          .at("details")
          .at("storage_condition") == "project_busy");
  LMDJ_CHECK(same_engine_response.first == LMDJ_STATUS_OK);
  LMDJ_CHECK(
      nlohmann::json::parse(same_engine_response.second).at("ok") == true);
  LMDJ_CHECK(independent_response.first == LMDJ_STATUS_OK);
  LMDJ_CHECK(
      nlohmann::json::parse(independent_response.second).at("ok") == true);
}

void test_repeated_create_free_keeps_stale_handles_dead() {
  TempDirectory temp;
  const auto config = config_json(temp.path());
  std::vector<lmdj_engine*> stale;
  stale.reserve(kComponentRepetitions);
  for (std::size_t index = 0; index < kComponentRepetitions; ++index) {
    lmdj_engine* engine = nullptr;
    char* error = nullptr;
    LMDJ_CHECK(
        lmdj_engine_create(config.c_str(), &engine, &error) ==
        LMDJ_STATUS_OK);
    LMDJ_CHECK(error == nullptr);
    LMDJ_CHECK(
        std::find(stale.begin(), stale.end(), engine) == stale.end());
    lmdj_engine_free(engine);
    stale.push_back(engine);
  }
  for (auto* engine : stale) {
    char* response = nullptr;
    LMDJ_CHECK(
        lmdj_engine_command(engine, "{}", &response) ==
        LMDJ_STATUS_INVALID_HANDLE);
    LMDJ_CHECK(response == nullptr);
  }
}

std::string deeply_nested_request(std::size_t depth) {
  constexpr std::string_view prefix =
      R"({"operation":"provider.list","nested":)";
  std::string request;
  request.reserve(prefix.size() + depth * 2U + 2U);
  request += prefix;
  request.append(depth, '[');
  request.push_back('0');
  request.append(depth, ']');
  request.push_back('}');
  return request;
}

void test_excessive_json_depth_is_rejected_without_crashing() {
  TempDirectory temp;
  const auto config = config_json(temp.path());
  lmdj_engine* engine = nullptr;
  char* error = nullptr;
  LMDJ_CHECK(lmdj_engine_create(config.c_str(), &engine, &error) == 0);
  LMDJ_CHECK(error == nullptr);
  char* accepted_response = nullptr;
  const auto accepted_request = deeply_nested_request(63U);
  LMDJ_CHECK(
      lmdj_engine_query(engine, accepted_request.c_str(), &accepted_response) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(accepted_response != nullptr);
  lmdj_string_free(accepted_response);
  lmdj_engine_free(engine);

  bool all_children_rejected = true;
  for (const std::size_t depth : {64U, 200000U}) {
    const auto child = ::fork();
    LMDJ_CHECK(child >= 0);
    if (child == 0) {
      lmdj_engine* child_engine = nullptr;
      char* child_error = nullptr;
      const auto created =
          lmdj_engine_create(config.c_str(), &child_engine, &child_error);
      if (child_error != nullptr) {
        lmdj_string_free(child_error);
      }
      if (created != LMDJ_STATUS_OK || child_engine == nullptr) {
        ::_exit(1);
      }
      char* response = reinterpret_cast<char*>(0x1);
      const auto request = deeply_nested_request(depth);
      const auto status =
          lmdj_engine_query(child_engine, request.c_str(), &response);
      const bool rejected =
          status == LMDJ_STATUS_INVALID_ARGUMENT && response == nullptr;
      if (response != nullptr) {
        lmdj_string_free(response);
      }
      lmdj_engine_free(child_engine);
      ::_exit(rejected ? 0 : 1);
    }

    int child_status = 0;
    LMDJ_CHECK(::waitpid(child, &child_status, 0) == child);
    all_children_rejected =
        all_children_rejected && WIFEXITED(child_status) &&
        WEXITSTATUS(child_status) == 0;
  }
  LMDJ_CHECK(all_children_rejected);
}

}  // namespace

int main() {
  try {
    LMDJ_CHECK(LMDJ_CORE_C_API_VERSION == 1);
    test_create_command_query_and_owned_strings();
    test_assembly_composition_through_c_abi();
    test_sequence_surface_is_routed_through_c_abi();
    test_asset_and_pad_replay_identity_through_c_abi();
    test_sample_operations_have_exact_shapes_and_private_errors();
    test_transport_failures_null_outputs_and_valid_facade_errors();
    test_stale_unknown_aba_and_racing_free_are_safe();
    test_busy_project_fails_fast_without_serializing_engines();
    test_repeated_create_free_keeps_stale_handles_dead();
    test_excessive_json_depth_is_rejected_without_crashing();
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
  std::cout << "facade C ABI tests: PASS\n";
  return 0;
}
