#include <chrono>
#include <filesystem>
#include <iostream>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>

#include "tests/core/support/test.hpp"

namespace {

constexpr std::string_view kProject = "20000000-0000-4000-8000-000000000001";
constexpr std::string_view kSession = "20000000-0000-4000-8000-000000000002";
constexpr std::string_view kPerformance =
    "20000000-0000-4000-8000-000000000003";

class TempDirectory {
public:
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-rebase-" +
             std::to_string(
                 std::chrono::steady_clock::now().time_since_epoch().count()));
    std::filesystem::create_directories(path_);
  }
  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }
  const std::filesystem::path &path() const { return path_; }

private:
  std::filesystem::path path_;
};

void check_ok(const nlohmann::json &response) {
  if (!response.at("ok").get<bool>()) {
    throw std::runtime_error(response.dump());
  }
}

void test_active_performance_settings_use_durable_rebase() {
  TempDirectory temp;
  lmdj::facade::Application application(
      {temp.path(), nullptr, {}, {}, std::nullopt, nullptr});
  const auto bundle = temp.path() / "project.lmdj";
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", kProject},
                                {"bpm", 120}}));
  check_ok(application.command(
      {{"operation", "performance.record.begin"},
       {"project_path", bundle.generic_string()},
       {"command_id", "20000000-0000-4000-8000-000000000004"},
       {"expected_revision", 0},
       {"session_id", kSession},
       {"performance_id", kPerformance}}));

  auto revision = std::uint64_t{1};
  const auto update = [&](std::string_view command_id, nlohmann::json bpm,
                          nlohmann::json quantize, nlohmann::json swing) {
    auto response = application.command({
        {"operation", "sequence.settings.update"},
        {"project_path", bundle.generic_string()},
        {"command_id", command_id},
        {"expected_revision", revision},
        {"session_id", kSession},
        {"bpm", std::move(bpm)},
        {"quantize_enabled", std::move(quantize)},
        {"swing_percent", std::move(swing)},
    });
    check_ok(response);
    ++revision;
    LMDJ_CHECK(response.at("result").at("committed_revision") == revision);
  };
  update("20000000-0000-4000-8000-000000000005", 132, nullptr, nullptr);
  update("20000000-0000-4000-8000-000000000006", nullptr, false, nullptr);
  update("20000000-0000-4000-8000-000000000007", nullptr, nullptr, 63);

  const auto status =
      application.query({{"operation", "performance.record.status"},
                         {"project_path", bundle.generic_string()}});
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("journal_revision") == 4);

  const auto sample_mutation = application.command({
      {"operation", "sample.reset_pad"},
      {"project_path", bundle.generic_string()},
      {"command_id", "20000000-0000-4000-8000-000000000008"},
      {"expected_revision", 4},
      {"slot", {{"bank", 0}, {"pad", 0}}},
  });
  LMDJ_CHECK(!sample_mutation.at("ok").get<bool>());
  LMDJ_CHECK(sample_mutation.at("error").at("code") == "INVALID_ARGUMENT");

  check_ok(application.command(
      {{"operation", "performance.record.stop"},
       {"project_path", bundle.generic_string()},
       {"session_id", kSession},
       {"request_id", "20000000-0000-4000-8000-000000000009"}}));
  check_ok(application.command(
      {{"operation", "performance.discard"},
       {"project_path", bundle.generic_string()},
       {"command_id", "20000000-0000-4000-8000-000000000010"},
       {"expected_revision", 4},
       {"performance_id", kPerformance}}));
}

} // namespace

int main() {
  try {
    test_active_performance_settings_use_durable_rebase();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
