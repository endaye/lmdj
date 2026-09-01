#include <chrono>
#include <filesystem>
#include <iostream>
#include <string_view>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;

class TempDirectory {
public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-operation-contract-" + std::to_string(nonce));
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

ApplicationConfig config(const std::filesystem::path &root) {
  return ApplicationConfig{root, nullptr, {}, {}, std::nullopt, nullptr};
}

void require_registered(Application &application, std::string_view operation,
                        bool command) {
  const nlohmann::json request{{"operation", operation}};
  const auto accepted =
      command ? application.command(request) : application.query(request);
  LMDJ_CHECK(!accepted.at("ok").get<bool>());
  LMDJ_CHECK(accepted.at("error").at("message") != "operation is unknown");

  const auto wrong_method =
      command ? application.query(request) : application.command(request);
  LMDJ_CHECK(!wrong_method.at("ok").get<bool>());
  LMDJ_CHECK(wrong_method.at("error").at("message") ==
             "operation was sent to the wrong Application method");
}

void test_locked_task4_operations_are_registered_with_exact_kinds() {
  TempDirectory temp;
  Application application(config(temp.path()));

  for (const auto operation : {
           "pattern.slot.assign",
           "pattern.slot.clear",
           "pattern.slot.move",
           "performance.record.begin",
           "performance.record.event",
           "performance.record.launch-request",
           "performance.record.flush",
           "performance.record.stop",
           "performance.save",
           "performance.discard",
           "performance.recovery.apply",
           "performance.recovery.discard",
           "performance.rename",
           "performance.delete",
           "performance.recording.bind",
       }) {
    require_registered(application, operation, true);
  }

  for (const auto operation : {
           "performance.list",
           "performance.inspect",
           "performance.record.status",
           "performance.recovery.list",
       }) {
    require_registered(application, operation, false);
  }

  const auto missing = (temp.path() / "missing.lmdj").generic_string();
  for (const auto& response : {
           application.query({{"operation", "performance.list"},
                              {"project_path", missing}}),
           application.query({{"operation", "performance.inspect"},
                              {"project_path", missing},
                              {"performance_id",
                               "00000000-0000-4000-8000-000000000001"}}),
  }) {
    LMDJ_CHECK(!response.at("ok").get<bool>());
  }
}

} // namespace

int main() {
  try {
    test_locked_task4_operations_are_registered_with_exact_kinds();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
