#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

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
  void anchor(std::uint16_t bpm, std::uint64_t at_tick) override {
    anchors.emplace_back(bpm, at_tick);
    next_ = std::max(next_, at_tick);
  }

  lmdj::foundation::Result<std::uint64_t> read_tick() override {
    ++read_count;
    return lmdj::foundation::Result<std::uint64_t>::success(next_ += 10U);
  }

  std::vector<std::pair<std::uint16_t, std::uint64_t>> anchors;
  std::uint64_t read_count{};

private:
  std::uint64_t next_{};
};

class Sequencer final : public lmdj::facade::PerformanceInputSequencer {
public:
  void seed(std::uint64_t last_input_sequence) override {
    seeded_after = last_input_sequence;
    next_ = std::max(next_, last_input_sequence);
  }

  lmdj::foundation::Result<std::uint64_t> next() override {
    return lmdj::foundation::Result<std::uint64_t>::success(++next_);
  }

  std::optional<std::uint64_t> seeded_after;

private:
  std::uint64_t next_{};
};

lmdj::facade::Application make_application(
    const std::filesystem::path &root,
    std::shared_ptr<Clock> clock = std::make_shared<Clock>(),
    std::shared_ptr<Sequencer> sequencer = std::make_shared<Sequencer>()) {
  lmdj::facade::ApplicationConfig config{
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
  config.performance_clock = std::move(clock);
  config.performance_input_sequencer = std::move(sequencer);
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

void test_authorities_attach_once_and_resume_from_durable_journal() {
  TempDirectory temp;
  const auto fresh_bundle = temp.path() / "fresh-project.lmdj";
  auto fresh_clock = std::make_shared<Clock>();
  auto fresh_sequencer = std::make_shared<Sequencer>();
  auto fresh = make_application(temp.path(), fresh_clock, fresh_sequencer);
  check_ok(fresh.command({
      {"operation", "project.create"},
      {"project_path", fresh_bundle.generic_string()},
      {"project_id", "40000000-0000-4000-8000-000000000001"},
      {"bpm", 120},
  }));
  const nlohmann::json begin = {
      {"operation", "performance.record.begin"},
      {"project_path", fresh_bundle.generic_string()},
      {"command_id", "40000000-0000-4000-8000-000000000002"},
      {"expected_revision", 0},
      {"session_id", "40000000-0000-4000-8000-000000000003"},
      {"performance_id", "40000000-0000-4000-8000-000000000004"},
  };
  check_ok(fresh.command(begin));
  LMDJ_CHECK((fresh_clock->anchors ==
              std::vector<std::pair<std::uint16_t, std::uint64_t>>{
                  {120, 10}}));
  LMDJ_CHECK(fresh_clock->read_count == 1);
  check_ok(fresh.command(begin));
  LMDJ_CHECK(fresh_clock->anchors.size() == 1);
  LMDJ_CHECK(fresh_clock->read_count == 1);
  LMDJ_CHECK(!fresh_sequencer->seeded_after.has_value());

  check_ok(fresh.command({
      {"operation", "sequence.settings.update"},
      {"project_path", fresh_bundle.generic_string()},
      {"command_id", "40000000-0000-4000-8000-000000000005"},
      {"expected_revision", 1},
      {"session_id", "40000000-0000-4000-8000-000000000003"},
      {"bpm", 90},
      {"quantize_enabled", true},
      {"swing_percent", 50},
  }));
  LMDJ_CHECK(fresh_clock->anchors.size() == 2);
  LMDJ_CHECK((fresh_clock->anchors.back() ==
              std::pair<std::uint16_t, std::uint64_t>{90, 20}));

  const auto reattach_bundle = temp.path() / "reattach-project.lmdj";
  {
    auto setup = make_application(temp.path());
    check_ok(setup.command({
        {"operation", "project.create"},
        {"project_path", reattach_bundle.generic_string()},
        {"project_id", "40000000-0000-4000-8000-000000000011"},
        {"bpm", 130},
    }));
  }
  const lmdj::foundation::CommandId begin_id{
      "40000000-0000-4000-8000-000000000012"};
  const lmdj::foundation::SequenceSessionId session_id{
      "40000000-0000-4000-8000-000000000013"};
  const lmdj::domain::PerformanceId performance_id{
      "40000000-0000-4000-8000-000000000014"};
  {
    const auto storage =
        lmdj::project_io::make_default_project_storage_platform();
    lmdj::project_io::ProjectStore projects{storage};
    lmdj::project_io::SequenceJournal journal{storage};
    LMDJ_CHECK(projects
                   .begin_performance_draft(
                       reattach_bundle,
                       {{begin_id, 0}, session_id, performance_id})
                   .has_value());
    const std::vector<lmdj::domain::PerformanceEvent> durable_events{
        lmdj::domain::PerformanceEvent{
            lmdj::domain::PadHitPerformanceEvent{1, 600, 100, 80}}};
    const lmdj::project_io::PerformanceTransientCheckpoint checkpoint{
        {lmdj::project_io::PerformanceOpenPadTransient{
            "40000000-0000-4000-8000-000000000017", 0, 500, 100}},
        {},
        false,
        500,
    };
    LMDJ_CHECK(journal
                   .append_performance_tail(
                       reattach_bundle,
                       session_id,
                       performance_id,
                       1,
                       7,
                       durable_events,
                       checkpoint)
                   .has_value());
  }

  auto reattach_clock = std::make_shared<Clock>();
  auto reattach_sequencer = std::make_shared<Sequencer>();
  auto reattached =
      make_application(temp.path(), reattach_clock, reattach_sequencer);
  check_ok(reattached.command({
      {"operation", "performance.record.begin"},
      {"project_path", reattach_bundle.generic_string()},
      {"command_id", begin_id.value()},
      {"expected_revision", 0},
      {"session_id", session_id.value()},
      {"performance_id", performance_id.value()},
  }));
  LMDJ_CHECK((reattach_clock->anchors ==
              std::vector<std::pair<std::uint16_t, std::uint64_t>>{
                  {130, 701}}));
  LMDJ_CHECK(reattach_clock->read_count == 0);
  LMDJ_CHECK(reattach_sequencer->seeded_after == 8);
  const auto closed = lmdj::project_io::SequenceJournal{}
                          .read_active_performance(reattach_bundle);
  LMDJ_CHECK(closed.has_value());
  LMDJ_CHECK(closed.value().pending_events.size() == 2);
  LMDJ_CHECK(closed.value().transient_checkpoint.has_value());
  LMDJ_CHECK(closed.value().transient_checkpoint->open_pads.empty());
  LMDJ_CHECK(closed.value().transient_checkpoint->last_accepted_tick == 701);

  const auto admitted = reattached.command({
      {"operation", "performance.record.event"},
      {"project_path", reattach_bundle.generic_string()},
      {"session_id", session_id.value()},
      {"event_id", "40000000-0000-4000-8000-000000000015"},
      {"event",
       {{"kind", "pad_press"},
        {"gesture_id", "40000000-0000-4000-8000-000000000016"},
        {"slot", 0},
        {"velocity", 100}}},
  });
  check_ok(admitted);
  LMDJ_CHECK(admitted.at("result").at("accepted_tick") >= 701);
  LMDJ_CHECK(admitted.at("result").at("input_sequence") == 9);
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

void test_flush_replay_crosses_application_process_identity_boundary() {
  TempDirectory temp;
  const auto bundle = temp.path() / "flush-replay-project.lmdj";
  constexpr std::string_view project = "50000000-0000-4000-8000-000000000001";
  constexpr std::string_view session = "50000000-0000-4000-8000-000000000002";
  constexpr std::string_view performance =
      "50000000-0000-4000-8000-000000000003";
  constexpr std::string_view begin = "50000000-0000-4000-8000-000000000004";
  constexpr std::string_view event = "50000000-0000-4000-8000-000000000005";
  constexpr std::string_view flush = "50000000-0000-4000-8000-000000000006";
  {
    auto owner = make_application(temp.path());
    check_ok(owner.command({{"operation", "project.create"},
                            {"project_path", bundle.generic_string()},
                            {"project_id", project},
                            {"bpm", 120}}));
    check_ok(owner.command({{"operation", "performance.record.begin"},
                            {"project_path", bundle.generic_string()},
                            {"command_id", begin},
                            {"expected_revision", 0},
                            {"session_id", session},
                            {"performance_id", performance}}));
    check_ok(owner.command({
        {"operation", "performance.record.event"},
        {"project_path", bundle.generic_string()},
        {"session_id", session},
        {"event_id", event},
        {"event", {{"kind", "hold_on"}}},
    }));
    check_ok(owner.command({{"operation", "performance.record.flush"},
                            {"project_path", bundle.generic_string()},
                            {"session_id", session},
                            {"command_id", flush}}));
  }

  auto observer = make_application(temp.path());
  const auto inspect_request = nlohmann::json{
      {"operation", "project.inspect"},
      {"project_path", bundle.generic_string()},
  };
  const auto before = observer.query(inspect_request);
  check_ok(before);
  const auto replayed = observer.command({
      {"operation", "performance.record.flush"},
      {"project_path", bundle.generic_string()},
      {"session_id", session},
      {"command_id", flush},
  });
  check_ok(replayed);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);
  LMDJ_CHECK(replayed.at("result").at("committed_revision") == 2);
  LMDJ_CHECK(observer.query(inspect_request) == before);

  const auto collision = observer.command({
      {"operation", "performance.record.flush"},
      {"project_path", bundle.generic_string()},
      {"session_id", "50000000-0000-4000-8000-000000000099"},
      {"command_id", flush},
  });
  LMDJ_CHECK(!collision.at("ok").get<bool>());
  LMDJ_CHECK(observer.query(inspect_request) == before);

  const auto unknown = observer.command({
      {"operation", "performance.record.flush"},
      {"project_path", bundle.generic_string()},
      {"session_id", session},
      {"command_id", "50000000-0000-4000-8000-000000000098"},
  });
  LMDJ_CHECK(!unknown.at("ok").get<bool>());
  LMDJ_CHECK(unknown.at("error").at("message") ==
             "Performance flush owner does not match");
  LMDJ_CHECK(observer.query(inspect_request) == before);

  const auto raw_event_replay = observer.command({
      {"operation", "performance.record.event"},
      {"project_path", bundle.generic_string()},
      {"session_id", session},
      {"event_id", event},
      {"event", {{"kind", "hold_on"}}},
  });
  LMDJ_CHECK(!raw_event_replay.at("ok").get<bool>());
  LMDJ_CHECK(observer.query(inspect_request) == before);
}

void test_recovery_queries_are_read_only_while_owner_is_alive() {
  TempDirectory temp;
  const auto bundle = temp.path() / "live-owner-project.lmdj";
  auto owner = make_application(temp.path());
  check_ok(owner.command({
      {"operation", "project.create"},
      {"project_path", bundle.generic_string()},
      {"project_id", "60000000-0000-4000-8000-000000000001"},
      {"bpm", 120},
  }));
  check_ok(owner.command({
      {"operation", "performance.record.begin"},
      {"project_path", bundle.generic_string()},
      {"command_id", "60000000-0000-4000-8000-000000000002"},
      {"expected_revision", 0},
      {"session_id", "60000000-0000-4000-8000-000000000003"},
      {"performance_id", "60000000-0000-4000-8000-000000000004"},
  }));
  check_ok(owner.command({
      {"operation", "performance.record.event"},
      {"project_path", bundle.generic_string()},
      {"session_id", "60000000-0000-4000-8000-000000000003"},
      {"event_id", "60000000-0000-4000-8000-000000000005"},
      {"event", {{"kind", "hold_on"}}},
  }));
  const auto active_path = bundle / "recovery/active/performance.jsonl";
  std::ifstream before_stream(active_path, std::ios::binary);
  const std::string before(
      std::istreambuf_iterator<char>{before_stream},
      std::istreambuf_iterator<char>{});

  auto observer = make_application(temp.path());
  const auto listed = observer.query({
      {"operation", "performance.recovery.list"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(listed);
  LMDJ_CHECK(listed.at("result").at("candidates").size() == 1);
  LMDJ_CHECK(listed.at("result").at("candidates").at(0).at("reason") ==
             "active");
  LMDJ_CHECK(
      listed.at("result").at("candidates").at(0).at("pending_event_count") ==
      2);
  const auto status = observer.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("state") == "active");
  LMDJ_CHECK(status.at("result").at("open_pad_gestures") == 0);
  LMDJ_CHECK(status.at("result").at("open_fx_gestures") == 0);
  LMDJ_CHECK(status.at("result").at("hold") == true);
  std::ifstream after_stream(active_path, std::ios::binary);
  const std::string after(
      std::istreambuf_iterator<char>{after_stream},
      std::istreambuf_iterator<char>{});
  LMDJ_CHECK(after == before);
  LMDJ_CHECK(std::filesystem::is_empty(bundle / "recovery/sealed"));
}

} // namespace

int main() {
  try {
    test_begin_flush_stop_save_and_inspect();
    test_authorities_attach_once_and_resume_from_durable_journal();
    test_owner_loss_recovery_is_publicly_observable_and_applicable();
    test_flush_replay_crosses_application_process_identity_boundary();
    test_recovery_queries_are_read_only_while_owner_is_alive();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
