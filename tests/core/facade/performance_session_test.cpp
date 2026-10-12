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

// D0/P1 owner-loss fixture: a minimal but honest live-control stub — neutral
// accepted state, immediately-ready fences, and a publish counter proving the
// sealed retry never enqueues.
class StubLiveControl final
    : public lmdj::facade::PerformanceLiveControlSink {
public:
  static constexpr std::string_view kEpoch =
      "11111111-1111-4111-8111-111111111111";

  std::optional<std::string> current_control_epoch() override {
    return epoch_;
  }
  std::optional<std::string> bound_control_project() override {
    return bound_;
  }
  lmdj::foundation::Result<std::string> bind_control_target(
      std::string project_uuid) override {
    if (!epoch_.has_value() || bound_ != project_uuid) {
      epoch_ = std::string{kEpoch};
      bound_ = project_uuid;
    }
    return lmdj::foundation::Result<std::string>::success(*epoch_);
  }
  void invalidate_control_target() override {
    epoch_.reset();
    bound_.reset();
  }
  lmdj::facade::PerformanceLiveControlSnapshot live_control_snapshot()
      override {
    return {state_, state_, sequence_, sequence_, 1};
  }
  lmdj::foundation::Result<lmdj::facade::PerformanceLiveControlReservation>
  reserve_live_control(
      const std::string& control_epoch,
      const lmdj::facade::PerformanceLiveControlIntent& intent) override {
    if (!epoch_.has_value() || *epoch_ != control_epoch) {
      return lmdj::foundation::Result<
          lmdj::facade::PerformanceLiveControlReservation>::failure(
          {lmdj::foundation::ErrorCode::invalid_argument, "stale epoch"});
    }
    lmdj::facade::PerformanceLiveControlReservation reservation;
    auto next = state_;
    using Kind = lmdj::facade::PerformanceLiveControlIntent::Kind;
    if (intent.kind == Kind::fx_parameter &&
        intent.phase == lmdj::domain::PerformanceFilterPhase::engage) {
      reservation.assigned_generation =
          "20000000-0000-4000-8000-000000000001";
      next.state.other_fx
          .at(static_cast<std::size_t>(intent.fx) - 1)
          .engaged = true;
      next.state.other_fx
          .at(static_cast<std::size_t>(intent.fx) - 1)
          .value = static_cast<std::uint16_t>(intent.value);
      reservation.fx_gesture = lmdj::audio::FxGesture{};
    } else if (intent.kind == Kind::hold_on || intent.kind == Kind::hold_off) {
      next.state.hold = intent.kind == Kind::hold_on;
      reservation.fx_gesture = lmdj::audio::FxGesture{};
    }
    reservation.resulting_state = next;
    reservation.control_sequence = sequence_ + 1;
    return lmdj::foundation::Result<
        lmdj::facade::PerformanceLiveControlReservation>::success(
        std::move(reservation));
  }
  lmdj::foundation::Result<lmdj::facade::PerformanceLiveControlReservation>
  reserve_live_control_republish(
      const std::string&,
      std::optional<lmdj::audio::FxGesture> fx_gesture,
      std::optional<lmdj::audio::FilterGesture> filter_gesture,
      std::optional<lmdj::audio::PadGatesState> pad_gates,
      lmdj::facade::PerformanceLiveControlState resulting_state,
      std::optional<std::string> assigned_generation) override {
    lmdj::facade::PerformanceLiveControlReservation reservation;
    reservation.fx_gesture = fx_gesture;
    reservation.filter_gesture = filter_gesture;
    reservation.pad_gates = pad_gates;
    reservation.resulting_state = std::move(resulting_state);
    reservation.assigned_generation = std::move(assigned_generation);
    reservation.control_sequence = sequence_ + 1;
    return lmdj::foundation::Result<
        lmdj::facade::PerformanceLiveControlReservation>::success(
        std::move(reservation));
  }
  lmdj::foundation::Result<void> publish_live_control(
      lmdj::facade::PerformanceLiveControlReservation reservation) override {
    ++publish_calls_;
    state_ = reservation.resulting_state;
    ++sequence_;
    return lmdj::foundation::Result<void>::success();
  }
  void cancel_live_control(
      lmdj::facade::PerformanceLiveControlReservation) noexcept override {
  }
  lmdj::foundation::Result<lmdj::facade::PerformanceControlFence> begin_fence(
      const std::string&) override {
    return lmdj::foundation::Result<
        lmdj::facade::PerformanceControlFence>::success(
        lmdj::facade::PerformanceControlFence{sequence_, 1, state_});
  }
  lmdj::facade::PerformanceFenceReadiness fence_readiness(
      const lmdj::facade::PerformanceControlFence&) override {
    return lmdj::facade::PerformanceFenceReadiness::ready;
  }

  std::size_t publish_calls() const { return publish_calls_; }

private:
  std::optional<std::string> epoch_;
  std::optional<std::string> bound_;
  lmdj::facade::PerformanceLiveControlState state_{};
  std::uint64_t sequence_{};
  std::size_t publish_calls_{};
};

// Injects one genuinely-unknown tail outcome: the append reports failure
// after writing, then the read-back also fails once.
class UnknownTailStorage final
    : public lmdj::project_io::ProjectStoragePlatform {
public:
  UnknownTailStorage()
      : delegate_(lmdj::project_io::make_default_project_storage_platform()) {}

  void fail_next_performance_tail() { armed_count_ = 2; }

  lmdj::foundation::Result<std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path &path) override {
    return delegate_->acquire_writer(path);
  }
  lmdj::foundation::Result<void>
  ensure_directory(const std::filesystem::path &path) override {
    return delegate_->ensure_directory(path);
  }
  lmdj::foundation::Result<bool>
  exists(const std::filesystem::path &path) const override {
    return delegate_->exists(path);
  }
  lmdj::foundation::Result<std::uint64_t>
  byte_length(const std::filesystem::path &path) const override {
    return delegate_->byte_length(path);
  }
  lmdj::foundation::Result<std::vector<std::byte>>
  read_complete(const std::filesystem::path &path) const override {
    if (read_armed_ &&
        path.generic_string().find("performance.jsonl") !=
            std::string::npos) {
      read_armed_ = false;
      return lmdj::foundation::Result<std::vector<std::byte>>::failure({
          lmdj::foundation::ErrorCode::io_error,
          "injected journal read failure",
      });
    }
    return delegate_->read_complete(path);
  }
  lmdj::foundation::Result<void>
  create_immutable(const std::filesystem::path &path,
                   std::span<const std::byte> bytes) override {
    return delegate_->create_immutable(path, bytes);
  }
  lmdj::foundation::Result<void>
  replace_complete(const std::filesystem::path &path,
                   std::span<const std::byte> bytes) override {
    return delegate_->replace_complete(path, bytes);
  }
  lmdj::foundation::Result<void>
  append_durable(const std::filesystem::path &path,
                 std::uint64_t valid_prefix_length,
                 std::span<const std::byte> bytes) override {
    if (armed_count_ != 0 &&
        path.generic_string().find("performance.jsonl") !=
            std::string::npos) {
      --armed_count_;
      auto appended =
          delegate_->append_durable(path, valid_prefix_length, bytes);
      if (appended.has_value()) {
        return lmdj::foundation::Result<void>::failure({
            lmdj::foundation::ErrorCode::io_error,
            "injected post-write tail failure",
        });
      }
      return appended;
    }
    return delegate_->append_durable(path, valid_prefix_length, bytes);
  }
  lmdj::foundation::Result<void>
  remove(const std::filesystem::path &path) override {
    return delegate_->remove(path);
  }
  lmdj::foundation::Result<std::vector<std::string>>
  list_names(const std::filesystem::path &path) const override {
    return delegate_->list_names(path);
  }
  lmdj::foundation::Result<std::vector<std::string>>
  list_directories(const std::filesystem::path &path) const override {
    return delegate_->list_directories(path);
  }
  lmdj::foundation::Result<void>
  remove_tree(const std::filesystem::path &path) override {
    return delegate_->remove_tree(path);
  }
  lmdj::foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path &staging,
      const std::filesystem::path &destination) override {
    return delegate_->publish_directory_if_absent(staging, destination);
  }
  lmdj::foundation::Result<bool>
  directory_exists(const std::filesystem::path &path) const override {
    return delegate_->directory_exists(path);
  }
  lmdj::foundation::Result<void>
  validate_managed_tree(const std::filesystem::path &path) const override {
    return delegate_->validate_managed_tree(path);
  }

private:
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> delegate_;
  std::size_t armed_count_{};
  mutable bool read_armed_{};
};

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

// D0/P1 R5 oracle: a prepared admission whose producer is truly lost reaches
// terminal only through the recovery-only closure/seal; the sealed old retry
// queries the explicit unknown with zero enqueue; the next Performance starts
// with its own empty ledger.
void test_headered_owner_loss_closure_terminal_and_sealed_retry_unknown() {
  TempDirectory temp;
  const auto bundle = temp.path() / "headered-owner-loss.lmdj";
  constexpr std::string_view project = "80000000-0000-4000-8000-000000000001";
  constexpr std::string_view session = "80000000-0000-4000-8000-000000000002";
  constexpr std::string_view performance =
      "80000000-0000-4000-8000-000000000003";
  constexpr std::string_view begin = "80000000-0000-4000-8000-000000000004";
  constexpr std::string_view event = "80000000-0000-4000-8000-000000000005";
  auto storage = std::make_shared<UnknownTailStorage>();
  {
    lmdj::facade::ApplicationConfig config{
        temp.path(),
        nullptr,
        {},
        {},
        std::nullopt,
        storage,
        std::make_shared<Clock>(),
        std::make_shared<Sequencer>(),
        nullptr,
        lmdj::facade::make_unavailable_performance_replay_controller(),
    };
    config.performance_live_control = std::make_shared<StubLiveControl>();
    lmdj::facade::Application owner(std::move(config));
    check_ok(owner.command({{"operation", "project.create"},
                            {"project_path", bundle.generic_string()},
                            {"project_id", project},
                            {"bpm", 120}}));
    check_ok(owner.command({{"operation", "performance.record.begin"},
                            {"project_path", bundle.generic_string()},
                            {"command_id", begin},
                            {"expected_revision", 0},
                            {"session_id", session},
                            {"performance_id", performance},
                            {"control_epoch",
                             std::string{StubLiveControl::kEpoch}}}));
    // One completed admission, then a prepared tail whose durable outcome is
    // unknown when the owner dies.
    check_ok(owner.command({
        {"operation", "performance.record.event"},
        {"project_path", bundle.generic_string()},
        {"session_id", session},
        {"event_id", event},
        {"event", {{"kind", "hold_on"}}},
        {"control_epoch", std::string{StubLiveControl::kEpoch}},
        {"expected_recording_sequence", "0"},
    }));
    storage->fail_next_performance_tail();
    const auto ambiguous = owner.command({
        {"operation", "performance.record.event"},
        {"project_path", bundle.generic_string()},
        {"session_id", session},
        {"event_id", "80000000-0000-4000-8000-000000000006"},
        {"event", {{"kind", "hold_off"}}},
        {"control_epoch", std::string{StubLiveControl::kEpoch}},
        {"expected_recording_sequence", "1"},
    });
    LMDJ_CHECK(!ambiguous.at("ok").get<bool>());
    LMDJ_CHECK(ambiguous.at("error").at("details").at("reason") ==
               "performance_tail_outcome_unknown");
    // The owner dies with the admission frozen and unknown.
  }

  // The reattach reader only queries: the old retry answers the durable
  // pending receipt as an explicit unknown and enqueues nothing.
  auto reader_live = std::make_shared<StubLiveControl>();
  lmdj::facade::ApplicationConfig reader_config{
      temp.path(),
      nullptr,
      {},
      {},
      std::nullopt,
      nullptr,
      std::make_shared<Clock>(),
      std::make_shared<Sequencer>(),
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
  };
  reader_config.performance_live_control = reader_live;
  lmdj::facade::Application reader(std::move(reader_config));
  const auto candidates = reader.query({
      {"operation", "performance.recovery.list"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(candidates);
  LMDJ_CHECK(candidates.at("result").at("candidates").size() == 1U);
  LMDJ_CHECK(candidates.at("result").at("candidates").at(0).at("reason") ==
             "owner_lost");

  const auto retry_request = nlohmann::json{
      {"operation", "performance.record.event"},
      {"project_path", bundle.generic_string()},
      {"session_id", session},
      {"event_id", "80000000-0000-4000-8000-000000000006"},
      {"event", {{"kind", "hold_off"}}},
      {"control_epoch", std::string{StubLiveControl::kEpoch}},
      {"expected_recording_sequence", "1"},
  };
  const auto retry = reader.command(retry_request);
  check_ok(retry);
  LMDJ_CHECK(retry.at("result").at("replayed") == true);
  LMDJ_CHECK(retry.at("result").at("admission").at("phase") == "prepared");
  LMDJ_CHECK(retry.at("result").at("admission").at("result") ==
             "not_published");
  LMDJ_CHECK(reader_live->publish_calls() == 0);

  // The recovery-only closure/seal brings the lost session to terminal.
  const auto applied = reader.command({
      {"operation", "performance.recovery.apply"},
      {"project_path", bundle.generic_string()},
      {"command_id", "80000000-0000-4000-8000-000000000007"},
      {"expected_revision", 1},
      {"session_id", session},
  });
  check_ok(applied);

  // After the seal the old identity still only reports its durable unknown.
  const auto sealed_retry = reader.command(retry_request);
  check_ok(sealed_retry);
  LMDJ_CHECK(sealed_retry.at("result").at("replayed") == true);
  LMDJ_CHECK(sealed_retry.at("result").at("admission").at("phase") ==
             "prepared");
  LMDJ_CHECK(reader_live->publish_calls() == 0);

  // The explicit finalize (the ordinary save path) retires the stopped
  // journal; only then does the next Performance begin with its own empty
  // ledger, unblocked by the old terminal pending admission.
  check_ok(reader.command({
      {"operation", "performance.save"},
      {"project_path", bundle.generic_string()},
      {"command_id", "80000000-0000-4000-8000-000000000010"},
      {"expected_revision",
       applied.at("result").at("committed_revision")},
      {"performance_id", performance},
      {"name", "Recovered Take"},
      {"recording_artifact", nullptr},
  }));
  check_ok(reader.command({
      {"operation", "performance.record.begin"},
      {"project_path", bundle.generic_string()},
      {"command_id", "80000000-0000-4000-8000-000000000008"},
      {"expected_revision",
       applied.at("result").at("committed_revision").get<std::uint64_t>() + 1},
      {"session_id", "80000000-0000-4000-8000-000000000009"},
      {"performance_id", "80000000-0000-4000-8000-00000000000a"},
      {"control_epoch", std::string{StubLiveControl::kEpoch}},
  }));
  const auto status = reader.query({
      {"operation", "performance.record.status"},
      {"project_path", bundle.generic_string()},
  });
  check_ok(status);
  LMDJ_CHECK(status.at("result").at("next_recording_sequence") == "0");
  LMDJ_CHECK(status.at("result").at("core_control_ready") == true);
}

} // namespace

int main() {
  try {
    test_begin_flush_stop_save_and_inspect();
    test_authorities_attach_once_and_resume_from_durable_journal();
    test_owner_loss_recovery_is_publicly_observable_and_applicable();
    test_flush_replay_crosses_application_process_identity_boundary();
    test_recovery_queries_are_read_only_while_owner_is_alive();
    test_headered_owner_loss_closure_terminal_and_sealed_retry_unknown();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
