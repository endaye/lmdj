#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include <fcntl.h>
#include <nlohmann/json.hpp>
#include <sys/file.h>
#include <unistd.h>

#include <lmdj/facade/c_api.h>

#include "tests/core/support/test.hpp"

namespace {

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

std::string config_json(const std::filesystem::path& root) {
  return nlohmann::json{{"workspace_root", root.generic_string()}}.dump();
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
  for (std::size_t index = 0; index < 1000; ++index) {
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

void test_take_replay_identity_is_enforced_through_c_abi() {
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

  response = nullptr;
  LMDJ_CHECK(
      lmdj_engine_query(
          engine, "{\"operation\":\"unknown\"}", &response) ==
      LMDJ_STATUS_OK);
  LMDJ_CHECK(response != nullptr);
  LMDJ_CHECK(nlohmann::json::parse(response).at("ok") == false);
  lmdj_string_free(response);
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
    for (std::size_t index = 0; index < 1000; ++index) {
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

void test_blocked_engine_does_not_serialize_other_engines() {
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

  const int lock_fd =
      ::open((project / ".lock").c_str(), O_RDWR | O_CLOEXEC);
  LMDJ_CHECK(lock_fd >= 0);
  LMDJ_CHECK(::flock(lock_fd, LOCK_EX) == 0);

  auto mutation = std::async(
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
  LMDJ_CHECK(mutation.wait_for(150ms) == std::future_status::timeout);

  const auto provider_list =
      nlohmann::json{{"operation", "provider.list"}}.dump();
  std::atomic<bool> queued_started{false};
  auto queued_same_engine = std::async(
      std::launch::async,
      [&]() {
        queued_started.store(true);
        char* response = nullptr;
        const auto status = lmdj_engine_query(
            blocked_engine, provider_list.c_str(), &response);
        std::string value = response == nullptr ? "" : response;
        lmdj_string_free(response);
        return std::pair{status, std::move(value)};
      });
  while (!queued_started.load()) {
    std::this_thread::yield();
  }
  LMDJ_CHECK(
      queued_same_engine.wait_for(150ms) == std::future_status::timeout);

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
  const bool independent_completed =
      independent.wait_for(250ms) == std::future_status::ready;

  LMDJ_CHECK(::flock(lock_fd, LOCK_UN) == 0);
  LMDJ_CHECK(::close(lock_fd) == 0);
  const auto mutation_response = mutation.get();
  const auto queued_response = queued_same_engine.get();
  const auto independent_response = independent.get();
  lmdj_engine_free(independent_engine);
  lmdj_engine_free(blocked_engine);

  LMDJ_CHECK(independent_completed);
  LMDJ_CHECK(mutation_response.at("ok") == true);
  LMDJ_CHECK(queued_response.first == LMDJ_STATUS_OK);
  LMDJ_CHECK(
      nlohmann::json::parse(queued_response.second).at("ok") == true);
  LMDJ_CHECK(independent_response.first == LMDJ_STATUS_OK);
  LMDJ_CHECK(
      nlohmann::json::parse(independent_response.second).at("ok") == true);
}

void test_repeated_create_free_keeps_stale_handles_dead() {
  TempDirectory temp;
  const auto config = config_json(temp.path());
  std::vector<lmdj_engine*> stale;
  stale.reserve(1000);
  for (std::size_t index = 0; index < 1000; ++index) {
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

}  // namespace

int main() {
  try {
    LMDJ_CHECK(LMDJ_CORE_C_API_VERSION == 1);
    test_create_command_query_and_owned_strings();
    test_take_replay_identity_is_enforced_through_c_abi();
    test_asset_and_pad_replay_identity_through_c_abi();
    test_transport_failures_null_outputs_and_valid_facade_errors();
    test_stale_unknown_aba_and_racing_free_are_safe();
    test_blocked_engine_does_not_serialize_other_engines();
    test_repeated_create_free_keeps_stale_handles_dead();
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
  std::cout << "facade C ABI tests: PASS\n";
  return 0;
}
