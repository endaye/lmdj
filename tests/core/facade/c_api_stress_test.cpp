#include <algorithm>
#include <array>
#include <atomic>
#include <barrier>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <span>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_set>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/c_api.h>

#include "packages/application-facade/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

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

class InvokeGateRegistration {
 public:
  explicit InvokeGateRegistration(
      lmdj::facade::testing::InvokeGate& gate) noexcept {
    lmdj::facade::testing::set_invoke_gate(&gate);
  }

  ~InvokeGateRegistration() {
    lmdj::facade::testing::set_invoke_gate(nullptr);
  }

  InvokeGateRegistration(const InvokeGateRegistration&) = delete;
  InvokeGateRegistration& operator=(const InvokeGateRegistration&) = delete;
};

class InvokeGateRelease {
 public:
  explicit InvokeGateRelease(
      lmdj::facade::testing::InvokeGate& gate) noexcept
      : gate_(gate) {}

  ~InvokeGateRelease() { release(); }

  InvokeGateRelease(const InvokeGateRelease&) = delete;
  InvokeGateRelease& operator=(const InvokeGateRelease&) = delete;

  void release() noexcept {
    gate_.release.store(true, std::memory_order_release);
    gate_.release.notify_all();
  }

 private:
  lmdj::facade::testing::InvokeGate& gate_;
};

constexpr std::size_t kIndependentEngineCount = 32;
constexpr std::size_t kIndependentEngineQueriesPerEngine = 128;
struct IndependentEngineQueryRange {
  std::size_t begin;
  std::size_t end;
};
constexpr std::array<IndependentEngineQueryRange, 2>
    kIndependentEngineQueryRanges{
        IndependentEngineQueryRange{0, 64},
        IndependentEngineQueryRange{64, 128},
    };
static_assert(
    kIndependentEngineQueryRanges.front().begin == 0 &&
    kIndependentEngineQueryRanges.front().end ==
        kIndependentEngineQueryRanges.back().begin &&
    kIndependentEngineQueryRanges.back().end ==
        kIndependentEngineQueriesPerEngine);

void test_independent_engines_inspect_samples_concurrently(
    IndependentEngineQueryRange query_range) {
  constexpr std::size_t kEngineCount = kIndependentEngineCount;

  TempDirectory temp;
  const auto config = config_json(temp.path());
  std::array<lmdj_engine*, kEngineCount> engines{};
  std::array<std::string, kEngineCount> requests{};
  for (std::size_t index = 0; index < kEngineCount; ++index) {
    engines.at(index) = create_engine(config);
    const auto project =
        temp.path() / ("sample-" + std::to_string(index) + ".lmdj");
    const auto project_suffix = std::to_string(index + 1U);
    const auto created = nlohmann::json{
        {"operation", "project.create"},
        {"project_path", project.generic_string()},
        {"project_id",
         "00000000-0000-4000-8000-" +
             std::string(12U - project_suffix.size(), '0') +
             project_suffix},
        {"bpm", 120},
    }.dump();
    char* response = nullptr;
    LMDJ_CHECK(
        lmdj_engine_command(
            engines.at(index), created.c_str(), &response) ==
        LMDJ_STATUS_OK);
    LMDJ_CHECK(response != nullptr);
    LMDJ_CHECK(nlohmann::json::parse(response).at("ok") == true);
    lmdj_string_free(response);
    requests.at(index) = nlohmann::json{
        {"operation", "sample.inspect"},
        {"project_path", project.generic_string()},
        {"slot", {{"bank", 0}, {"pad", 0}}},
    }.dump();
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
      for (auto query_index = query_range.begin;
           query_index < query_range.end;
           ++query_index) {
        char* response = nullptr;
        const auto status = lmdj_engine_query(
            engines[index], requests[index].c_str(), &response);
        const bool response_present = response != nullptr;
        const bool successful =
            response_present &&
            nlohmann::json::parse(response).value("ok", false);
        lmdj_string_free(response);
        if (status != LMDJ_STATUS_OK || !successful) {
          result = CallResult{status, response_present};
          break;
        }
        ++progress;
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
    LMDJ_CHECK(
        completed.at(index) == query_range.end - query_range.begin);
    lmdj_engine_free(engines.at(index));
  }
}

void test_independent_engines_queries_0_63() {
  test_independent_engines_inspect_samples_concurrently(
      kIndependentEngineQueryRanges.at(0));
}

void test_independent_engines_queries_64_127() {
  test_independent_engines_inspect_samples_concurrently(
      kIndependentEngineQueryRanges.at(1));
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
  const auto request =
      nlohmann::json{{"operation", "provider.list"}}.dump();

  lmdj::facade::testing::InvokeGate gate{blocked_engine};
  InvokeGateRegistration registration(gate);
  CallResult blocked_result;
  std::atomic<bool> blocked_completed{false};
  std::jthread blocked_worker([&]() noexcept {
    char* response = nullptr;
    const auto status = lmdj_engine_query(
        blocked_engine, request.c_str(), &response);
    blocked_result = CallResult{status, response != nullptr};
    lmdj_string_free(response);
    blocked_completed.store(true, std::memory_order_release);
    blocked_completed.notify_all();
  });
  InvokeGateRelease release_guard(gate);
  gate.entered.wait(false, std::memory_order_acquire);
  const bool observed_entry = gate.entered.load(std::memory_order_acquire);

  lmdj_engine* unrelated_engine = nullptr;
  char* error = nullptr;
  const auto unrelated_create_status =
      lmdj_engine_create(config.c_str(), &unrelated_engine, &error);
  const bool unrelated_error_present = error != nullptr;
  lmdj_string_free(error);
  CallResult unrelated_query;
  if (unrelated_create_status == LMDJ_STATUS_OK &&
      unrelated_engine != nullptr) {
    char* response = nullptr;
    const auto status = lmdj_engine_query(
        unrelated_engine, request.c_str(), &response);
    unrelated_query = CallResult{status, response != nullptr};
    lmdj_string_free(response);
    lmdj_engine_free(unrelated_engine);
  }
  const bool blocked_while_gate_held =
      !blocked_completed.load(std::memory_order_acquire);

  release_guard.release();
  blocked_worker.join();
  lmdj_engine_free(blocked_engine);

  LMDJ_CHECK(observed_entry);
  LMDJ_CHECK(blocked_while_gate_held);
  LMDJ_CHECK(blocked_result.status == LMDJ_STATUS_OK);
  LMDJ_CHECK(blocked_result.response_present);
  LMDJ_CHECK(unrelated_create_status == LMDJ_STATUS_OK);
  LMDJ_CHECK(unrelated_engine != nullptr);
  LMDJ_CHECK(!unrelated_error_present);
  LMDJ_CHECK(unrelated_query.status == LMDJ_STATUS_OK);
  LMDJ_CHECK(unrelated_query.response_present);
}

using Scenario = void (*)();

constexpr std::array<Scenario, 1> kIndependentEngineQueries0To63Scenarios{
    test_independent_engines_queries_0_63,
};

constexpr std::array<Scenario, 1> kIndependentEngineQueries64To127Scenarios{
    test_independent_engines_queries_64_127,
};

constexpr std::array<Scenario, 1> kQueryFreeRaceScenarios{
    test_query_and_free_race_never_reuses_stale_handle,
};

constexpr std::array<Scenario, 1> kStaleHandleScenarios{
    test_10000_create_free_cycles_keep_all_stale_handles_invalid,
};

constexpr std::array<Scenario, 1> kLifetimeIsolationScenarios{
    test_blocked_engine_does_not_block_unrelated_engine_lifetimes,
};

struct Shard {
  std::string_view name;
  std::span<const Scenario> scenarios;
};

constexpr std::array<Shard, 5> kShards{
    Shard{
        "independent-engines-0-63",
        kIndependentEngineQueries0To63Scenarios},
    Shard{
        "independent-engines-64-127",
        kIndependentEngineQueries64To127Scenarios},
    Shard{"query-free-race", kQueryFreeRaceScenarios},
    Shard{"stale-handles", kStaleHandleScenarios},
    Shard{"lifetime-isolation", kLifetimeIsolationScenarios},
};

void run(std::span<const Scenario> scenarios) {
  for (const auto scenario : scenarios) {
    scenario();
  }
}

}  // namespace

int main(int argc, char** argv) {
  if (argc == 2 && std::string_view(argv[1]) == "--list-shards") {
    std::size_t total{};
    for (const auto& shard : kShards) {
      std::cout << shard.name << ' ' << shard.scenarios.size() << '\n';
      total += shard.scenarios.size();
    }
    std::cout << "all " << total << '\n';
    return 0;
  }
  const std::string_view prefix{"--shard="};
  const auto selected =
      argc == 2 ? std::string_view(argv[1]) : std::string_view{};
  if (argc > 2 || (argc == 2 && !selected.starts_with(prefix))) {
    std::cerr << "usage: lmdj_application_c_api_stress_tests "
                 "[--list-shards|--shard=<name>]\n";
    return 2;
  }
  try {
    std::size_t executed{};
    for (const auto& shard : kShards) {
      if (argc == 1 || selected.substr(prefix.size()) == shard.name) {
        run(shard.scenarios);
        executed += shard.scenarios.size();
      }
    }
    if (executed == 0) {
      std::cerr << "unknown C API stress shard\n";
      return 2;
    }
    std::cout << "facade C ABI stress tests: PASS (" << executed
              << " scenarios)\n";
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
  }
  return 0;
}
