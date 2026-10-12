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
  return ApplicationConfig{
      root,
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
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
           "performance.fx.gesture",
           "performance.live.control",
           "performance.record.launch-request",
           "performance.record.flush",
           "performance.record.stop",
           "performance.replay.begin",
           "performance.replay.stop",
           "performance.resample.commit",
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
           "performance.live.status",
           "performance.record.status",
           "performance.replay.status",
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

  const auto malformed_replay = application.command(
      {{"operation", "performance.replay.begin"},
       {"project_path", missing},
       {"replay_id", "not-a-uuid"},
       {"performance_id", "00000000-0000-4000-8000-000000000001"}});
  LMDJ_CHECK(!malformed_replay.at("ok").get<bool>());
  LMDJ_CHECK(malformed_replay.at("error").at("code") == "INVALID_ARGUMENT");

  const auto extra_key = application.query(
      {{"operation", "performance.replay.status"},
       {"project_path", missing},
       {"replay_id", "00000000-0000-4000-8000-000000000001"},
       {"extra", true}});
  LMDJ_CHECK(!extra_key.at("ok").get<bool>());
  LMDJ_CHECK(extra_key.at("error").at("message") ==
             "performance.replay.status request shape is invalid");
}

// D0/P1: the typed live-control wire carries only Core-issued identities —
// any Host-supplied tick/frame/sequence key breaks the exact-key shape.
void test_live_control_wire_accepts_only_core_issued_identities() {
  TempDirectory temp;
  Application application(config(temp.path()));
  const auto base = nlohmann::json{
      {"operation", "performance.live.control"},
      {"project_path", (temp.path() / "missing.lmdj").generic_string()},
      {"control_epoch", "00000000-0000-4000-8000-000000000001"},
      {"command_id", "00000000-0000-4000-8000-000000000002"},
      {"expected_control_sequence", "0"},
      {"intent", {{"kind", "hold_on"}}},
  };
  for (const auto *host_key : {"tick", "frame", "input_sequence"}) {
    auto forged = base;
    forged[host_key] = 42;
    const auto response = application.command(forged);
    LMDJ_CHECK(!response.at("ok").get<bool>());
    LMDJ_CHECK(response.at("error").at("message") ==
               "performance.live.control request shape is invalid");
  }
  // The exact shape reaches the handler (the missing Project is the domain
  // failure, not a shape rejection).
  const auto shaped = application.command(base);
  LMDJ_CHECK(!shaped.at("ok").get<bool>());
  LMDJ_CHECK(shaped.at("error").at("message") !=
             "performance.live.control request shape is invalid");
  // A malformed sequence string is not a Core identity.
  auto bad_sequence = base;
  bad_sequence["expected_control_sequence"] = "007";
  const auto response = application.command(bad_sequence);
  LMDJ_CHECK(!response.at("ok").get<bool>());
}

} // namespace

int main() {
  try {
    test_locked_task4_operations_are_registered_with_exact_kinds();
    test_live_control_wire_accepts_only_core_issued_identities();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
