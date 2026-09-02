#include <chrono>
#include <filesystem>
#include <iostream>
#include <memory>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>

#include "tests/core/support/test.hpp"

namespace {

constexpr std::string_view kProject = "10000000-0000-4000-8000-000000000001";
constexpr std::string_view kSession = "10000000-0000-4000-8000-000000000002";
constexpr std::string_view kPerformance =
    "10000000-0000-4000-8000-000000000003";
constexpr std::string_view kBegin = "10000000-0000-4000-8000-000000000004";
constexpr std::string_view kGesture = "10000000-0000-4000-8000-000000000005";
constexpr std::string_view kFxGesture = "10000000-0000-4000-8000-000000000006";
constexpr std::string_view kLaunch = "10000000-0000-4000-8000-000000000007";
constexpr std::string_view kStop = "10000000-0000-4000-8000-000000000008";
constexpr std::string_view kSave = "10000000-0000-4000-8000-000000000009";

class TempDirectory {
public:
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-gesture-" +
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
  void anchor(std::uint16_t, std::uint64_t) override {}

  lmdj::foundation::Result<std::uint64_t> read_tick() override {
    const auto value = ticks_.at(cursor_++);
    return lmdj::foundation::Result<std::uint64_t>::success(value);
  }

private:
  std::vector<std::uint64_t> ticks_{0,   10,  30,  40,  100, 110, 120, 200,
                                    210, 220, 230, 240, 245, 250};
  std::size_t cursor_{};
};

class Sequencer final : public lmdj::facade::PerformanceInputSequencer {
public:
  void seed(std::uint64_t last_input_sequence) override {
    next_ = std::max(next_, last_input_sequence);
  }

  lmdj::foundation::Result<std::uint64_t> next() override {
    return lmdj::foundation::Result<std::uint64_t>::success(++next_);
  }

private:
  std::uint64_t next_{};
};

class LaunchAcknowledger final
    : public lmdj::facade::PatternLaunchAcknowledger {
public:
  lmdj::foundation::Result<lmdj::facade::PatternLaunchReservation>
  reserve(const lmdj::foundation::SequenceSessionId &session_id,
          const lmdj::foundation::CommandId &request_id,
          std::uint8_t pattern_slot,
          std::uint64_t earliest_target_tick,
          std::shared_ptr<const lmdj::cooker::RuntimeSnapshot>
              resolved_pattern) override {
    session_id_ = session_id;
    request_id_ = request_id;
    pattern_slot_ = pattern_slot;
    target_tick_ = earliest_target_tick;
    resolved_pattern_ = std::move(resolved_pattern);
    return lmdj::foundation::Result<
        lmdj::facade::PatternLaunchReservation>::success({earliest_target_tick,
                                                          false});
  }

  std::vector<lmdj::facade::PatternLaunchOutcome>
  drain(const lmdj::foundation::SequenceSessionId &) override {
    return std::exchange(outcomes_, {});
  }

  void cancel(const lmdj::foundation::SequenceSessionId &) noexcept override {}

  void acknowledge() {
    outcomes_.push_back({session_id_, request_id_, pattern_slot_, target_tick_,
                         lmdj::facade::PatternLaunchOutcomeKind::applied});
  }

  const std::shared_ptr<const lmdj::cooker::RuntimeSnapshot>&
  resolved_pattern() const {
    return resolved_pattern_;
  }

private:
  lmdj::foundation::SequenceSessionId session_id_{""};
  lmdj::foundation::CommandId request_id_{""};
  std::uint8_t pattern_slot_{};
  std::uint64_t target_tick_{};
  std::shared_ptr<const lmdj::cooker::RuntimeSnapshot> resolved_pattern_;
  std::vector<lmdj::facade::PatternLaunchOutcome> outcomes_;
};

void check_ok(const nlohmann::json &response) {
  if (!response.at("ok").get<bool>()) {
    throw std::runtime_error(response.dump());
  }
}

void test_raw_gesture_admission_and_launch_ack() {
  TempDirectory temp;
  auto acknowledger = std::make_shared<LaunchAcknowledger>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
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
  config.performance_clock = std::make_shared<Clock>();
  config.performance_input_sequencer = std::make_shared<Sequencer>();
  config.pattern_launch_acknowledger = acknowledger;
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "project.lmdj";

  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", kProject},
                                {"bpm", 120}}));
  check_ok(application.command({{"operation", "performance.record.begin"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", kBegin},
                                {"expected_revision", 0},
                                {"session_id", kSession},
                                {"performance_id", kPerformance}}));

  const auto press_id = "10000000-0000-4000-8000-000000000010";
  const auto press = nlohmann::json{{"operation", "performance.record.event"},
                                    {"project_path", bundle.generic_string()},
                                    {"session_id", kSession},
                                    {"event_id", press_id},
                                    {"event",
                                     {{"kind", "pad_press"},
                                      {"gesture_id", kGesture},
                                      {"slot", 5},
                                      {"velocity", 100}}}};
  const auto accepted = application.command(press);
  check_ok(accepted);
  const auto replayed = application.command(press);
  check_ok(replayed);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);
  auto collision = press;
  collision["event"]["slot"] = 6;
  LMDJ_CHECK(!application.command(collision).at("ok").get<bool>());

  check_ok(application.command(
      {{"operation", "performance.record.event"},
       {"project_path", bundle.generic_string()},
       {"session_id", kSession},
       {"event_id", "10000000-0000-4000-8000-000000000011"},
       {"event",
        {{"kind", "pad_release"}, {"gesture_id", kGesture}, {"slot", 5}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000012"},
                           {"event",
                            {{"kind", "fx_engage"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"},
                             {"value", 500}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000013"},
                           {"event",
                            {{"kind", "fx_move"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"},
                             {"value", 600}}}}));
  const auto coalesced =
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000014"},
                           {"event",
                            {{"kind", "fx_move"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"},
                             {"value", 700}}}});
  check_ok(coalesced);
  LMDJ_CHECK(coalesced.at("result").at("coalesced") == true);
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000015"},
                           {"event",
                            {{"kind", "fx_release"},
                             {"gesture_id", kFxGesture},
                             {"fx", "filter"}}}}));

  const auto launch =
      application.command({{"operation", "performance.record.launch-request"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"request_id", kLaunch},
                           {"pattern_slot", 3}});
  check_ok(launch);
  LMDJ_CHECK(launch.at("result").at("target_tick") == 3840);
  const auto pending_status =
      application.query({{"operation", "performance.record.status"},
                         {"project_path", bundle.generic_string()}});
  check_ok(pending_status);
  LMDJ_CHECK(pending_status.at("result").at("pending_launch").at("claimed") ==
             false);
  check_ok(
      application.command({{"operation", "performance.record.launch-request"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"request_id", kLaunch},
                           {"pattern_slot", 3}}));
  const auto launch_collision =
      application.command({{"operation", "performance.record.launch-request"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"request_id", kLaunch},
                           {"pattern_slot", 4}});
  LMDJ_CHECK(!launch_collision.at("ok").get<bool>());
  acknowledger->acknowledge();
  const auto status =
      application.query({{"operation", "performance.record.status"},
                         {"project_path", bundle.generic_string()}});
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("last_launch_ack").at("pattern_slot") == 3);

  check_ok(application.command(
      {{"operation", "performance.record.event"},
       {"project_path", bundle.generic_string()},
       {"session_id", kSession},
       {"event_id", "10000000-0000-4000-8000-000000000016"},
       {"event",
        {{"kind", "pad_press"},
         {"gesture_id", "10000000-0000-4000-8000-000000000017"},
         {"slot", 7},
         {"velocity", 90}}}}));
  check_ok(application.command(
      {{"operation", "performance.record.event"},
       {"project_path", bundle.generic_string()},
       {"session_id", kSession},
       {"event_id", "10000000-0000-4000-8000-000000000018"},
       {"event",
        {{"kind", "fx_engage"},
         {"gesture_id", "10000000-0000-4000-8000-000000000019"},
         {"fx", "reverse"},
         {"value", 800}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000020"},
                           {"event", {{"kind", "hold_on"}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000021"},
                           {"event", {{"kind", "hold_off"}}}}));
  check_ok(
      application.command({{"operation", "performance.record.event"},
                           {"project_path", bundle.generic_string()},
                           {"session_id", kSession},
                           {"event_id", "10000000-0000-4000-8000-000000000022"},
                           {"event", {{"kind", "hold_on"}}}}));

  check_ok(application.command({{"operation", "performance.record.stop"},
                                {"project_path", bundle.generic_string()},
                                {"session_id", kSession},
                                {"request_id", kStop}}));
  check_ok(application.command({{"operation", "performance.save"},
                                {"project_path", bundle.generic_string()},
                                {"command_id", kSave},
                                {"expected_revision", 1},
                                {"performance_id", kPerformance},
                                {"name", "Gesture Take"},
                                {"recording_artifact", nullptr}}));
  const auto inspected =
      application.query({{"operation", "performance.inspect"},
                         {"project_path", bundle.generic_string()},
                         {"performance_id", kPerformance}});
  check_ok(inspected);
  const auto encoded = inspected.dump();
  LMDJ_CHECK(encoded.find(std::string(kGesture)) == std::string::npos);
  LMDJ_CHECK(encoded.find(std::string(kFxGesture)) == std::string::npos);
  const auto &events = inspected.at("result").at("performance").at("events");
  LMDJ_CHECK(events.size() == 12U);
  LMDJ_CHECK(events.at(0).at("kind") == "pad_hit");
  LMDJ_CHECK(events.at(0).at("duration_tick") == 20);
  const auto encoded_events = events.dump();
  LMDJ_CHECK(encoded_events.find("pattern_launch") != std::string::npos);
  LMDJ_CHECK(encoded_events.find("hold_off") != std::string::npos);
}

void test_launch_receives_core_resolved_immutable_pattern_material() {
  TempDirectory temp;
  auto acknowledger = std::make_shared<LaunchAcknowledger>();
  lmdj::facade::ApplicationConfig config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      acknowledger,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
  lmdj::facade::Application application(std::move(config));
  const auto bundle = temp.path() / "resolved-pattern-project.lmdj";
  constexpr auto pattern = "10000000-0000-4000-8000-000000000030";
  check_ok(application.command({{"operation", "project.create"},
                                {"project_path", bundle.generic_string()},
                                {"project_id", "10000000-0000-4000-8000-000000000031"},
                                {"bpm", 120}}));
  check_ok(application.command({
      {"operation", "pattern.create"},
      {"project_path", bundle.generic_string()},
      {"command_id", "10000000-0000-4000-8000-000000000032"},
      {"expected_revision", 0},
      {"pattern_id", pattern},
      {"bars", 1},
  }));
  check_ok(application.command({
      {"operation", "pattern.slot.assign"},
      {"project_path", bundle.generic_string()},
      {"command_id", "10000000-0000-4000-8000-000000000033"},
      {"expected_revision", 1},
      {"pattern_slot", 3},
      {"pattern_id", pattern},
  }));
  check_ok(application.command({
      {"operation", "performance.record.begin"},
      {"project_path", bundle.generic_string()},
      {"command_id", "10000000-0000-4000-8000-000000000034"},
      {"expected_revision", 2},
      {"session_id", "10000000-0000-4000-8000-000000000035"},
      {"performance_id", "10000000-0000-4000-8000-000000000036"},
  }));
  check_ok(application.command({
      {"operation", "performance.record.launch-request"},
      {"project_path", bundle.generic_string()},
      {"session_id", "10000000-0000-4000-8000-000000000035"},
      {"request_id", "10000000-0000-4000-8000-000000000037"},
      {"pattern_slot", 3},
  }));
  LMDJ_CHECK(acknowledger->resolved_pattern() != nullptr);
  LMDJ_CHECK(acknowledger->resolved_pattern()->pattern_id.value() == pattern);
  LMDJ_CHECK(acknowledger->resolved_pattern()->project_revision == 3);
}

} // namespace

int main() {
  try {
    test_raw_gesture_admission_and_launch_ack();
    test_launch_receives_core_resolved_immutable_pattern_material();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
