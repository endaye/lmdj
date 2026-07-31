#include <algorithm>
#include <array>
#include <atomic>
#include <barrier>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <string>
#include <thread>
#include <unordered_set>
#include <utility>
#include <vector>

#include <fcntl.h>
#include <nlohmann/json.hpp>
#include <sys/file.h>
#include <unistd.h>

#include <lmdj/facade/c_api.h>

#include "tests/core/support/test.hpp"

namespace {

using namespace std::chrono_literals;

class TempDirectory {
 public:
  TempDirectory() {
    static std::atomic<std::uint64_t> sequence{0};
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-c-api-stress-" + std::to_string(nonce) + "-" +
             std::to_string(sequence.fetch_add(1)));
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

struct CallResult {
  int status = LMDJ_STATUS_INVALID_ARGUMENT;
  bool response_present = false;
};

std::string config_json(const std::filesystem::path& root) {
  return nlohmann::json{{"workspace_root", root.generic_string()}}.dump();
}

lmdj_engine* create_engine(const std::string& config) {
  lmdj_engine* engine = nullptr;
  char* error = nullptr;
  const auto status =
      lmdj_engine_create(config.c_str(), &engine, &error);
  const bool error_absent = error == nullptr;
  lmdj_string_free(error);
  LMDJ_CHECK(status == LMDJ_STATUS_OK);
  LMDJ_CHECK(engine != nullptr);
  LMDJ_CHECK(error_absent);
  return engine;
}

nlohmann::json command(
    lmdj_engine* engine,
    const nlohmann::json& request) {
  const auto encoded = request.dump();
  char* response = nullptr;
  const auto status =
      lmdj_engine_command(engine, encoded.c_str(), &response);
  LMDJ_CHECK(status == LMDJ_STATUS_OK);
  LMDJ_CHECK(response != nullptr);
  const auto parsed = nlohmann::json::parse(response);
  lmdj_string_free(response);
  return parsed;
}

bool wait_until_true(
    const std::atomic<bool>& value,
    std::chrono::steady_clock::duration timeout) {
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (!value.load(std::memory_order_acquire) &&
         std::chrono::steady_clock::now() < deadline) {
    std::this_thread::yield();
  }
  return value.load(std::memory_order_acquire);
}

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" +
         std::string(12 - tail.size(), '0') + tail;
}

void test_32_independent_engines_make_progress_concurrently() {
  constexpr std::size_t kEngineCount = 32;
  constexpr std::size_t kQueriesPerEngine = 128;

  TempDirectory temp;
  const auto config = config_json(temp.path());
  const auto request =
      nlohmann::json{{"operation", "provider.list"}}.dump();
  std::array<lmdj_engine*, kEngineCount> engines{};
  for (auto& engine : engines) {
    engine = create_engine(config);
  }

  std::array<CallResult, kEngineCount> results{};
  std::array<std::size_t, kEngineCount> completed{};
  std::barrier<> start(static_cast<std::ptrdiff_t>(kEngineCount + 1));
  std::vector<std::jthread> workers;
  workers.reserve(kEngineCount);
  for (std::size_t index = 0; index < kEngineCount; ++index) {
    workers.emplace_back([&, index]() noexcept {
      start.arrive_and_wait();
      auto result = CallResult{LMDJ_STATUS_OK, true};
      std::size_t progress = 0;
      for (; progress < kQueriesPerEngine; ++progress) {
        char* response = nullptr;
        const auto status = lmdj_engine_query(
            engines[index], request.c_str(), &response);
        const bool response_present = response != nullptr;
        lmdj_string_free(response);
        if (status != LMDJ_STATUS_OK || !response_present) {
          result = CallResult{status, response_present};
          break;
        }
      }
      results[index] = result;
      completed[index] = progress;
    });
  }
  start.arrive_and_wait();
  workers.clear();

  for (std::size_t index = 0; index < kEngineCount; ++index) {
    LMDJ_CHECK(results.at(index).status == LMDJ_STATUS_OK);
    LMDJ_CHECK(results.at(index).response_present);
    LMDJ_CHECK(completed.at(index) == kQueriesPerEngine);
    lmdj_engine_free(engines.at(index));
  }
}

void test_query_and_free_race_never_reuses_stale_handle() {
  constexpr std::size_t kIterations = 256;

  TempDirectory temp;
  const auto config = config_json(temp.path());
  const auto request =
      nlohmann::json{{"operation", "provider.list"}}.dump();
  std::vector<lmdj_engine*> stale;
  stale.reserve(kIterations * 2);

  for (std::size_t iteration = 0; iteration < kIterations; ++iteration) {
    auto* raced = create_engine(config);
    std::barrier<> start(3);
    CallResult query_result;
    std::atomic<bool> free_completed{false};
    std::jthread query_worker([&]() noexcept {
      start.arrive_and_wait();
      char* response = nullptr;
      const auto status =
          lmdj_engine_query(raced, request.c_str(), &response);
      query_result = CallResult{status, response != nullptr};
      lmdj_string_free(response);
    });
    std::jthread free_worker([&]() noexcept {
      start.arrive_and_wait();
      lmdj_engine_free(raced);
      free_completed.store(true, std::memory_order_release);
    });
    start.arrive_and_wait();
    query_worker.join();
    free_worker.join();

    LMDJ_CHECK(free_completed.load(std::memory_order_acquire));
    LMDJ_CHECK(
        query_result.status == LMDJ_STATUS_OK ||
        query_result.status == LMDJ_STATUS_INVALID_HANDLE);
    LMDJ_CHECK(
        query_result.response_present ==
        (query_result.status == LMDJ_STATUS_OK));
    stale.push_back(raced);

    auto* replacement = create_engine(config);
    LMDJ_CHECK(
        std::find(stale.begin(), stale.end(), replacement) ==
        stale.end());
    lmdj_engine_free(replacement);
    stale.push_back(replacement);

    char* response = reinterpret_cast<char*>(0x1);
    LMDJ_CHECK(
        lmdj_engine_query(raced, request.c_str(), &response) ==
        LMDJ_STATUS_INVALID_HANDLE);
    LMDJ_CHECK(response == nullptr);
  }
}

void test_10000_create_free_cycles_keep_all_stale_handles_invalid() {
  constexpr std::size_t kCycles = 10'000;

  TempDirectory temp;
  const auto config = config_json(temp.path());
  const auto request =
      nlohmann::json{{"operation", "provider.list"}}.dump();
  std::vector<lmdj_engine*> stale;
  stale.reserve(kCycles);
  std::unordered_set<lmdj_engine*> identities;
  identities.reserve(kCycles);

  for (std::size_t iteration = 0; iteration < kCycles; ++iteration) {
    auto* engine = create_engine(config);
    LMDJ_CHECK(identities.insert(engine).second);
    lmdj_engine_free(engine);
    stale.push_back(engine);
  }

  for (auto* engine : stale) {
    char* response = reinterpret_cast<char*>(0x1);
    LMDJ_CHECK(
        lmdj_engine_query(engine, request.c_str(), &response) ==
        LMDJ_STATUS_INVALID_HANDLE);
    LMDJ_CHECK(response == nullptr);
  }
}

void test_blocked_engine_does_not_block_unrelated_engine_lifetimes() {
  TempDirectory temp;
  const auto config = config_json(temp.path());
  auto* blocked_engine = create_engine(config);
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

  const auto blocked_request =
      nlohmann::json{
          {"operation", "pad.assign"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(91)},
          {"expected_revision", 0},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"asset_id", nullptr},
      }
          .dump();
  const auto query_request =
      nlohmann::json{{"operation", "provider.list"}}.dump();

  CallResult blocked_result;
  std::atomic<bool> blocked_entered{false};
  std::atomic<bool> blocked_completed{false};
  std::barrier<> blocked_start(2);
  std::jthread blocked_worker([&]() noexcept {
    blocked_start.arrive_and_wait();
    blocked_entered.store(true, std::memory_order_release);
    char* response = nullptr;
    const auto status = lmdj_engine_command(
        blocked_engine, blocked_request.c_str(), &response);
    blocked_result = CallResult{status, response != nullptr};
    lmdj_string_free(response);
    blocked_completed.store(true, std::memory_order_release);
  });
  blocked_start.arrive_and_wait();
  const bool observed_entry = wait_until_true(blocked_entered, 2s);
  const bool observed_block =
      observed_entry && !wait_until_true(blocked_completed, 100ms);

  CallResult unrelated_create;
  CallResult unrelated_query;
  std::atomic<bool> unrelated_completed{false};
  std::barrier<> unrelated_start(2);
  std::jthread unrelated_worker([&]() noexcept {
    unrelated_start.arrive_and_wait();
    lmdj_engine* engine = nullptr;
    char* error = nullptr;
    const auto create_status =
        lmdj_engine_create(config.c_str(), &engine, &error);
    unrelated_create =
        CallResult{create_status, error != nullptr};
    lmdj_string_free(error);
    if (create_status == LMDJ_STATUS_OK && engine != nullptr) {
      char* response = nullptr;
      const auto query_status = lmdj_engine_query(
          engine, query_request.c_str(), &response);
      unrelated_query =
          CallResult{query_status, response != nullptr};
      lmdj_string_free(response);
      lmdj_engine_free(engine);
    }
    unrelated_completed.store(true, std::memory_order_release);
  });
  unrelated_start.arrive_and_wait();
  const bool unrelated_made_progress =
      wait_until_true(unrelated_completed, 5s);
  const bool blocked_while_lock_held =
      !blocked_completed.load(std::memory_order_acquire);

  const bool unlock_succeeded = ::flock(lock_fd, LOCK_UN) == 0;
  const bool close_succeeded = ::close(lock_fd) == 0;
  blocked_worker.join();
  unrelated_worker.join();
  lmdj_engine_free(blocked_engine);

  LMDJ_CHECK(observed_entry);
  LMDJ_CHECK(observed_block);
  LMDJ_CHECK(unrelated_made_progress);
  LMDJ_CHECK(blocked_while_lock_held);
  LMDJ_CHECK(unlock_succeeded);
  LMDJ_CHECK(close_succeeded);
  LMDJ_CHECK(blocked_result.status == LMDJ_STATUS_OK);
  LMDJ_CHECK(blocked_result.response_present);
  LMDJ_CHECK(unrelated_create.status == LMDJ_STATUS_OK);
  LMDJ_CHECK(!unrelated_create.response_present);
  LMDJ_CHECK(unrelated_query.status == LMDJ_STATUS_OK);
  LMDJ_CHECK(unrelated_query.response_present);
}

}  // namespace

int main() {
  try {
    test_32_independent_engines_make_progress_concurrently();
    test_query_and_free_race_never_reuses_stale_handle();
    test_10000_create_free_cycles_keep_all_stale_handles_invalid();
    test_blocked_engine_does_not_block_unrelated_engine_lifetimes();
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
  std::cout << "facade C ABI stress tests: PASS\n";
  return 0;
}
