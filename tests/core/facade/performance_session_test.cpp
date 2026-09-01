#include <chrono>
#include <filesystem>
#include <iostream>
#include <memory>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>

#include "tests/core/support/test.hpp"

namespace {

constexpr std::string_view kProject = "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kSession = "00000000-0000-4000-8000-000000000002";
constexpr std::string_view kPerformance =
    "00000000-0000-4000-8000-000000000003";
constexpr std::string_view kBegin = "00000000-0000-4000-8000-000000000004";
constexpr std::string_view kEvent = "00000000-0000-4000-8000-000000000005";
constexpr std::string_view kFlush = "00000000-0000-4000-8000-000000000006";
constexpr std::string_view kStop = "00000000-0000-4000-8000-000000000007";
constexpr std::string_view kSave = "00000000-0000-4000-8000-000000000008";
constexpr std::string_view kPattern = "00000000-0000-4000-8000-000000000009";

class TempDirectory {
public:
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-session-" +
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

class Clock final : public lmdj::facade::PerformanceClock {
public:
  lmdj::foundation::Result<std::uint64_t> read_tick() override {
    return lmdj::foundation::Result<std::uint64_t>::success(next_ += 10U);
  }

private:
  std::uint64_t next_{};
};

class Sequencer final : public lmdj::facade::PerformanceInputSequencer {
public:
  lmdj::foundation::Result<std::uint64_t> next() override {
    return lmdj::foundation::Result<std::uint64_t>::success(++next_);
  }

private:
  std::uint64_t next_{};
};

lmdj::facade::Application make_application(const std::filesystem::path &root) {
  lmdj::facade::ApplicationConfig config{root, nullptr,      {},
                                         {},   std::nullopt, nullptr};
  config.performance_clock = std::make_shared<Clock>();
  config.performance_input_sequencer = std::make_shared<Sequencer>();
  return lmdj::facade::Application(std::move(config));
}

void check_ok(const nlohmann::json &response) {
  if (!response.at("ok").get<bool>()) {
    throw std::runtime_error(response.dump());
  }
}

void test_begin_flush_stop_save_and_inspect() {
  TempDirectory temp;
  auto application = make_application(temp.path());
  const auto bundle = temp.path() / "project.lmdj";
  check_ok(application.command({
      {"operation", "project.create"},
      {"project_path", bundle.generic_string()},
      {"project_id", kProject},
      {"bpm", 120},
  }));

  const auto begun = application.command({
      {"operation", "performance.record.begin"},
      {"project_path", bundle.generic_string()},
      {"command_id", kBegin},
      {"expected_revision", 0},
      {"session_id", kSession},
      {"performance_id", kPerformance},
  });
  check_ok(begun);
  LMDJ_CHECK(begun.at("result").at("committed_revision") == 1);

  check_ok(application.command({
      {"operation", "performance.record.event"},
      {"project_path", bundle.generic_string()},
      {"session_id", kSession},
      {"event_id", kEvent},
      {"event", {{"kind", "hold_on"}}},
  }));
  const auto flushed = application.command({
      {"operation", "performance.record.flush"},
      {"project_path", bundle.generic_string()},
      {"session_id", kSession},
      {"command_id", kFlush},
  });
  check_ok(flushed);
  LMDJ_CHECK(flushed.at("result").at("committed_revision") == 2);

  const auto stopped = application.command({
      {"operation", "performance.record.stop"},
      {"project_path", bundle.generic_string()},
      {"session_id", kSession},
      {"request_id", kStop},
  });
  check_ok(stopped);
  LMDJ_CHECK(stopped.at("result").at("state") == "stopped");

  const auto saved = application.command({
      {"operation", "performance.save"},
      {"project_path", bundle.generic_string()},
      {"command_id", kSave},
      {"expected_revision", 2},
      {"performance_id", kPerformance},
      {"name", "First Take"},
      {"recording_artifact", nullptr},
  });
  check_ok(saved);
  LMDJ_CHECK(saved.at("result").at("committed_revision") == 3);

  const auto inspected = application.query({
      {"operation", "performance.inspect"},
      {"project_path", bundle.generic_string()},
      {"performance_id", kPerformance},
  });
  check_ok(inspected);
  const auto &performance = inspected.at("result").at("performance");
  LMDJ_CHECK(performance.at("name") == "First Take");
  LMDJ_CHECK(performance.at("events").size() == 2U);
  LMDJ_CHECK(performance.at("events").at(0).at("kind") == "hold_on");
  LMDJ_CHECK(performance.at("events").at(1).at("kind") == "hold_off");

  const auto listed = application.query({
      {"operation", "performance.list"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(listed);
  LMDJ_CHECK(listed.at("result").at("performances").size() == 1U);
  LMDJ_CHECK(listed.at("result").at("performances").at(0).at("event_count") ==
             2);

  const auto renamed = application.command({
      {"operation", "performance.rename"},
      {"project_path", bundle.generic_string()},
      {"command_id", "00000000-0000-4000-8000-000000000010"},
      {"expected_revision", 3},
      {"performance_id", kPerformance},
      {"name", "Renamed Take"},
  });
  check_ok(renamed);
  LMDJ_CHECK(renamed.at("result").at("committed_revision") == 4);

  check_ok(application.command({
      {"operation", "pattern.create"},
      {"project_path", bundle.generic_string()},
      {"command_id", "00000000-0000-4000-8000-000000000011"},
      {"expected_revision", 4},
      {"pattern_id", kPattern},
      {"bars", 1},
  }));
  const auto assigned = application.command({
      {"operation", "pattern.slot.assign"},
      {"project_path", bundle.generic_string()},
      {"command_id", "00000000-0000-4000-8000-000000000012"},
      {"expected_revision", 5},
      {"pattern_slot", 0},
      {"pattern_id", kPattern},
  });
  check_ok(assigned);
  LMDJ_CHECK(assigned.at("result").at("pattern_id") == kPattern);
  const auto moved = application.command({
      {"operation", "pattern.slot.move"},
      {"project_path", bundle.generic_string()},
      {"command_id", "00000000-0000-4000-8000-000000000013"},
      {"expected_revision", 6},
      {"from_slot", 0},
      {"to_slot", 15},
  });
  check_ok(moved);
  LMDJ_CHECK(moved.at("result").at("pattern_id") == kPattern);
  const auto cleared = application.command({
      {"operation", "pattern.slot.clear"},
      {"project_path", bundle.generic_string()},
      {"command_id", "00000000-0000-4000-8000-000000000014"},
      {"expected_revision", 7},
      {"pattern_slot", 15},
  });
  check_ok(cleared);
  LMDJ_CHECK(cleared.at("result").at("pattern_id").is_null());

  const auto invalid_binding = application.command({
      {"operation", "performance.recording.bind"},
      {"project_path", bundle.generic_string()},
      {"command_id", "00000000-0000-4000-8000-000000000015"},
      {"expected_revision", 8},
      {"performance_id", kPerformance},
      {"recording_artifact",
       {{"sha256", std::string(64U, 'a')},
        {"media_type", "audio/wav"},
        {"byte_length", 44}}},
  });
  LMDJ_CHECK(!invalid_binding.at("ok").get<bool>());

  const auto deleted = application.command({
      {"operation", "performance.delete"},
      {"project_path", bundle.generic_string()},
      {"command_id", "00000000-0000-4000-8000-000000000016"},
      {"expected_revision", 8},
      {"performance_id", kPerformance},
  });
  check_ok(deleted);
  LMDJ_CHECK(deleted.at("result").at("committed_revision") == 9);
}

void test_owner_loss_recovery_is_publicly_observable_and_applicable() {
  TempDirectory temp;
  const auto bundle = temp.path() / "recovery-project.lmdj";
  constexpr std::string_view project = "30000000-0000-4000-8000-000000000001";
  constexpr std::string_view session = "30000000-0000-4000-8000-000000000002";
  constexpr std::string_view performance =
      "30000000-0000-4000-8000-000000000003";
  {
    auto application = make_application(temp.path());
    check_ok(application.command({
        {"operation", "project.create"},
        {"project_path", bundle.generic_string()},
        {"project_id", project},
        {"bpm", 120},
    }));
    check_ok(application.command({
        {"operation", "performance.record.begin"},
        {"project_path", bundle.generic_string()},
        {"command_id", "30000000-0000-4000-8000-000000000004"},
        {"expected_revision", 0},
        {"session_id", session},
        {"performance_id", performance},
    }));
    check_ok(application.command({
        {"operation", "performance.record.event"},
        {"project_path", bundle.generic_string()},
        {"session_id", session},
        {"event_id", "30000000-0000-4000-8000-000000000005"},
        {"event", {{"kind", "hold_on"}}},
    }));
  }

  auto reopened = make_application(temp.path());
  const auto candidates = reopened.query({
      {"operation", "performance.recovery.list"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(candidates);
  LMDJ_CHECK(candidates.at("result").at("candidates").size() == 1U);
  LMDJ_CHECK(candidates.at("result").at("candidates").at(0).at("reason") ==
             "owner_lost");

  const auto status = reopened.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("state") == "recovery_required");

  const auto applied = reopened.command({
      {"operation", "performance.recovery.apply"},
      {"project_path", bundle.generic_string()},
      {"command_id", "30000000-0000-4000-8000-000000000006"},
      {"expected_revision", 1},
      {"session_id", session},
  });
  check_ok(applied);
  LMDJ_CHECK(applied.at("result").at("committed_revision") == 2);
  const auto inspected = reopened.query({
      {"operation", "performance.inspect"},
      {"project_path", bundle.generic_string()},
      {"performance_id", performance},
  });
  check_ok(inspected);
  LMDJ_CHECK(inspected.at("result").at("performance").at("events").size() ==
             2U);
}

} // namespace

int main() {
  try {
    test_begin_flush_stop_save_and_inspect();
    test_owner_loss_recovery_is_publicly_observable_and_applicable();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
