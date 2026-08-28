#include <atomic>
#include <array>
#include <chrono>
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include <lmdj/facade/application.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "packages/application-facade/src/testing_hooks.hpp"

#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::CommandMeta;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::facade::ArtifactBytesImportRequest;
using lmdj::facade::InitialProjectRequest;
using lmdj::facade::SampleImportBeginRequest;
using lmdj::facade::SequenceRecordState;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-sequence-surface-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') +
         tail;
}

std::vector<std::byte> read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary | std::ios::ate);
  LMDJ_CHECK(static_cast<bool>(stream));
  const auto size = stream.tellg();
  LMDJ_CHECK(size >= 0);
  std::vector<std::byte> result(static_cast<std::size_t>(size));
  stream.seekg(0);
  stream.read(reinterpret_cast<char*>(result.data()), size);
  LMDJ_CHECK(static_cast<bool>(stream));
  return result;
}

ApplicationConfig config(const std::filesystem::path& root) {
  return ApplicationConfig{
      root,
      nullptr,
      {},
      {},
      lmdj::audio::RuntimePreparationLimits{
          1'048'576, 240'000, 67'108'864, 134'217'728},
      nullptr,
  };
}

void create_recordable_project(
    Application& application,
    const std::filesystem::path& project,
    const PatternId& pattern_id) {
  const auto created = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{uuid(1)},
          120,
          Pattern{pattern_id, 1, {}},
      });
  LMDJ_CHECK(created.has_value());
  const auto imported = application.import_artifact_bytes(
      ArtifactBytesImportRequest{
          project,
          CommandMeta{CommandId{uuid(10)}, 0},
          AssetId{uuid(11)},
          "audio/wav",
          read_bytes("tests/fixtures/audio/kick.wav"),
      });
  LMDJ_CHECK(imported.has_value());
  const auto assigned = application.command({
      {"operation", "pad.assign"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(12)},
      {"expected_revision", 1},
      {"slot", {{"bank", 0}, {"pad", 0}}},
      {"asset_id", uuid(11)},
  });
  LMDJ_CHECK(assigned.value("ok", false));
  LMDJ_CHECK(assigned.at("project_revision") == 2);
}

class SequenceAdmissionHookGuard {
 public:
  explicit SequenceAdmissionHookGuard(
      lmdj::facade::testing::SequenceAuthoringAdmissionHook* hook) {
    lmdj::facade::testing::set_sequence_authoring_admission_hook(hook);
  }

  ~SequenceAdmissionHookGuard() {
    lmdj::facade::testing::set_sequence_authoring_admission_hook(nullptr);
  }

  SequenceAdmissionHookGuard(const SequenceAdmissionHookGuard&) = delete;
  SequenceAdmissionHookGuard& operator=(
      const SequenceAdmissionHookGuard&) = delete;
};

struct SequenceAdmissionGate {
  std::atomic<bool> entered{false};
  std::atomic<bool> release{false};
};

void hold_sequence_admission(void* opaque) noexcept {
  auto& gate = *static_cast<SequenceAdmissionGate*>(opaque);
  gate.entered.store(true, std::memory_order_release);
  while (!gate.release.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }
}

void test_sequence_lifecycle_idempotence_and_mutation_exclusion() {
  TempDirectory temp;
  const auto project = temp.path() / "lifecycle.lmdj";
  const PatternId pattern_id{uuid(20)};
  const SequenceSessionId session_id{uuid(21)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);

  const auto begun = application.begin_sequence(
      {project, session_id, pattern_id, 2, 0});
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().status.state == SequenceRecordState::active);
  LMDJ_CHECK(application.query_sequence_status({project}).value() ==
             begun.value().status);

  const auto blocked = application.command({
      {"operation", "pad.assign"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(22)},
      {"expected_revision", 2},
      {"slot", {{"bank", 0}, {"pad", 0}}},
      {"asset_id", nullptr},
  });
  LMDJ_CHECK(!blocked.at("ok").get<bool>());
  LMDJ_CHECK(
      blocked.at("error").at("details").at("reason") ==
      "sequence_session_active");

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
                 .has_value());
  const lmdj::facade::SequenceFlushRequest flush{
      project, session_id, CommandId{uuid(23)}, 12'000};
  const auto committed = application.flush_sequence(flush);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().committed_revision == 3);
  const auto replayed = application.flush_sequence(flush);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);

  const auto stopped = application.stop_sequence(
      {project, session_id, CommandId{uuid(24)}, 12'001});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().status.state == SequenceRecordState::inactive);
  LMDJ_CHECK(!std::filesystem::exists(
      project / "recovery/active/sequence.jsonl"));

  Application restarted(config(temp.path()));
  const auto cross_host_replay = restarted.flush_sequence(flush);
  LMDJ_CHECK(cross_host_replay.has_value());
  LMDJ_CHECK(cross_host_replay.value().replayed);
  LMDJ_CHECK(cross_host_replay.value().committed_revision == 3);
  LMDJ_CHECK(
      cross_host_replay.value().status.state == SequenceRecordState::inactive);
}

void test_owner_loss_apply_and_discard_are_explicit() {
  TempDirectory temp;
  const auto project = temp.path() / "recovery.lmdj";
  const PatternId pattern_id{uuid(30)};
  const SequenceSessionId first{uuid(31)};
  {
    Application owner(config(temp.path()));
    create_recordable_project(owner, project, pattern_id);
    LMDJ_CHECK(owner.begin_sequence({project, first, pattern_id, 2, 0})
                   .has_value());
    LMDJ_CHECK(owner.record_sequence_event(
        {project, first, {PadSlotId{0, 0}, 90, 0, 1, true}})
                   .has_value());
  }

  Application recovery(config(temp.path()));
  const auto candidates = recovery.list_sequence_recovery({project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().event_count == 1);
  const auto applied = recovery.apply_sequence_recovery(
      {project, first, std::nullopt});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(applied.value().committed_revision == 3);
  LMDJ_CHECK(recovery.list_sequence_recovery({project}).value().empty());

  const SequenceSessionId second{uuid(32)};
  {
    Application owner(config(temp.path()));
    LMDJ_CHECK(owner.begin_sequence({project, second, pattern_id, 3, 0})
                   .has_value());
    LMDJ_CHECK(owner.record_sequence_event(
        {project, second, {PadSlotId{0, 0}, 70, 0, 1, true}})
                   .has_value());
  }
  LMDJ_CHECK(recovery.discard_sequence_recovery(
      {project, second, std::nullopt}).has_value());
  LMDJ_CHECK(recovery.list_sequence_recovery({project}).value().empty());
}

void test_writer_lease_blocks_competing_sequence_owner() {
  TempDirectory temp;
  const auto project = temp.path() / "lease.lmdj";
  const PatternId pattern_id{uuid(40)};
  Application owner(config(temp.path()));
  Application competitor(config(temp.path()));
  create_recordable_project(owner, project, pattern_id);
  LMDJ_CHECK(owner.begin_sequence(
      {project, SequenceSessionId{uuid(41)}, pattern_id, 2, 0}).has_value());
  const auto observed = competitor.query_sequence_status({project});
  LMDJ_CHECK(observed.has_value());
  LMDJ_CHECK(observed.value().state == SequenceRecordState::active);
  LMDJ_CHECK(observed.value().session_id == SequenceSessionId{uuid(41)});
  const auto rejected = competitor.begin_sequence(
      {project, SequenceSessionId{uuid(42)}, pattern_id, 2, 0});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      rejected.error().details.at("storage_condition") == "project_busy");
}

void test_begin_cannot_cross_an_authoring_admission() {
  TempDirectory temp;
  const auto project = temp.path() / "admission-race.lmdj";
  const PatternId pattern_id{uuid(60)};
  const SequenceSessionId session_id{uuid(61)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);

  SequenceAdmissionGate gate;
  lmdj::facade::testing::SequenceAuthoringAdmissionHook hook{
      &gate, hold_sequence_admission};
  SequenceAdmissionHookGuard guard(&hook);
  bool assigned = false;
  std::uint64_t assigned_revision = 0;
  std::thread authoring([&]() {
    const auto result = application.command({
        {"operation", "pad.assign"},
        {"project_path", project.generic_string()},
        {"command_id", uuid(62)},
        {"expected_revision", 2},
        {"slot", {{"bank", 0}, {"pad", 0}}},
        {"asset_id", nullptr},
    });
    assigned = result.value("ok", false);
    if (assigned) {
      assigned_revision = result.at("project_revision").get<std::uint64_t>();
    }
  });
  while (!gate.entered.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }

  bool begin_succeeded = false;
  ErrorCode begin_error = ErrorCode::internal_error;
  std::atomic<bool> begin_entered{false};
  std::atomic<bool> begin_returned{false};
  std::thread begin([&]() {
    begin_entered.store(true, std::memory_order_release);
    auto result = application.begin_sequence(
        {project, session_id, pattern_id, 2, 0});
    begin_succeeded = result.has_value();
    if (!result.has_value()) {
      begin_error = result.error().code;
    }
    begin_returned.store(true, std::memory_order_release);
  });
  while (!begin_entered.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }
  const auto begin_deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(250);
  while (!begin_returned.load(std::memory_order_acquire) &&
         std::chrono::steady_clock::now() < begin_deadline) {
    std::this_thread::yield();
  }
  const bool crossed_admission =
      begin_returned.load(std::memory_order_acquire);
  gate.release.store(true, std::memory_order_release);
  authoring.join();
  begin.join();

  LMDJ_CHECK(!crossed_admission);
  LMDJ_CHECK(assigned);
  LMDJ_CHECK(assigned_revision == 3);
  LMDJ_CHECK(!begin_succeeded);
  LMDJ_CHECK(begin_error == ErrorCode::revision_conflict);
  LMDJ_CHECK(!std::filesystem::exists(
      project / "recovery/active/sequence.jsonl"));
}

void test_orphan_journal_is_sealed_before_authoring() {
  TempDirectory temp;
  const auto project = temp.path() / "orphan-admission.lmdj";
  const PatternId pattern_id{uuid(70)};
  const SequenceSessionId session_id{uuid(71)};
  Application creator(config(temp.path()));
  create_recordable_project(creator, project, pattern_id);

  lmdj::project_io::ProjectStore store;
  const auto state = store.load(project);
  LMDJ_CHECK(state.has_value());
  const auto& pattern = state.value().patterns.at(pattern_id);
  lmdj::project_io::SequenceJournal journal;
  LMDJ_CHECK(
      journal
          .begin(
              project,
              session_id,
              pattern_id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              state.value().revision)
          .has_value());

  Application restarted(config(temp.path()));
  const auto created = restarted.command({
      {"operation", "pattern.create"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(72)},
      {"expected_revision", 2},
      {"pattern_id", uuid(73)},
      {"bars", 1},
  });
  LMDJ_CHECK(created.value("ok", false));
  LMDJ_CHECK(created.at("project_revision") == 3);
  LMDJ_CHECK(!std::filesystem::exists(
      project / "recovery/active/sequence.jsonl"));
  const auto candidates = restarted.list_sequence_recovery({project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().reason == "owner_lost");
  LMDJ_CHECK(candidates.value().front().session_id == session_id);
}

void test_settings_rebase_and_pattern_creation_are_authoritative() {
  TempDirectory temp;
  const auto project = temp.path() / "authoring.lmdj";
  const PatternId pattern_id{uuid(50)};
  const SequenceSessionId session_id{uuid(51)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);
  LMDJ_CHECK(application.begin_sequence(
      {project, session_id, pattern_id, 2, 0}).has_value());

  const auto updated = application.command({
      {"operation", "sequence.settings.update"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(52)},
      {"expected_revision", 2},
      {"session_id", session_id.value()},
      {"runtime_frame", 6'000},
      {"bpm", 140},
      {"quantize_enabled", false},
      {"swing_percent", 60},
  });
  LMDJ_CHECK(updated.value("ok", false));
  LMDJ_CHECK(updated.at("project_revision") == 3);
  LMDJ_CHECK(updated.at("result").at("bpm") == 140);
  LMDJ_CHECK(!updated.at("result").at("quantize_enabled").get<bool>());
  LMDJ_CHECK(application.query_sequence_status({project})
                 .value().expected_revision == 3);

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 6'001, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
                 .has_value());
  const auto stopped = application.stop_sequence(
      {project, session_id, CommandId{uuid(53)}, 12'001});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().committed_revision == 4);

  const auto created = application.command({
      {"operation", "pattern.create"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(54)},
      {"expected_revision", 4},
      {"pattern_id", uuid(55)},
      {"bars", 4},
  });
  LMDJ_CHECK(created.value("ok", false));
  LMDJ_CHECK(created.at("project_revision") == 5);
  LMDJ_CHECK(created.at("result").at("bars") == 4);
}

void test_armed_capture_commit_rebases_without_losing_pending_events() {
  TempDirectory temp;
  const auto project = temp.path() / "armed-capture.lmdj";
  const PatternId pattern_id{uuid(80)};
  const SequenceSessionId session_id{uuid(81)};
  const PadSlotId armed_slot{0, 1};
  const auto wav = read_bytes("tests/fixtures/audio/kick.wav");
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);

  const auto begun = application.begin_sequence(
      {project, session_id, pattern_id, 2, 0, armed_slot});
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
                 .has_value());
  const auto armed_event = application.record_sequence_event(
      {project, session_id, {armed_slot, 100, 12'001, 3, true}});
  LMDJ_CHECK(!armed_event.has_value());
  LMDJ_CHECK(armed_event.error().details.contains("reason"));
  LMDJ_CHECK(
      armed_event.error().details.at("reason") == "armed_capture_in_progress");

  const auto unarmed_begin = application.begin_sample_import(
      SampleImportBeginRequest{
          uuid(82),
          project,
          CommandMeta{CommandId{uuid(83)}, 2},
          PadSlotId{0, 2},
          AssetId{uuid(84)},
          wav.size(),
          session_id,
      });
  LMDJ_CHECK(!unarmed_begin.has_value());
  LMDJ_CHECK(unarmed_begin.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(unarmed_begin.error().details.contains("reason"));
  LMDJ_CHECK(
      unarmed_begin.error().details.at("reason") ==
      "armed_capture_target_mismatch");
  auto active = application.query_sequence_status({project});
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().state == SequenceRecordState::active);
  LMDJ_CHECK(active.value().pending_event_count == 1);
  LMDJ_CHECK(active.value().expected_revision == 2);

  const auto invalid_token = uuid(85);
  LMDJ_CHECK(application.begin_sample_import(
      SampleImportBeginRequest{
          invalid_token,
          project,
          CommandMeta{CommandId{uuid(86)}, 2},
          armed_slot,
          AssetId{uuid(87)},
          wav.size(),
          session_id,
      }).has_value());
  const std::vector<std::byte> invalid_wav(wav.size(), std::byte{0});
  LMDJ_CHECK(application.append_sample_import(
      invalid_token, 0, invalid_wav, true).has_value());
  const auto invalid_commit = application.commit_sample_import(invalid_token);
  LMDJ_CHECK(!invalid_commit.has_value());
  active = application.query_sequence_status({project});
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().state == SequenceRecordState::active);
  LMDJ_CHECK(active.value().pending_event_count == 1);
  LMDJ_CHECK(active.value().expected_revision == 2);

  const auto token = uuid(88);
  LMDJ_CHECK(application.begin_sample_import(
      SampleImportBeginRequest{
          token,
          project,
          CommandMeta{CommandId{uuid(89)}, 2},
          armed_slot,
          AssetId{uuid(90)},
          wav.size(),
          session_id,
      }).has_value());
  LMDJ_CHECK(application.append_sample_import(token, 0, wav, true).has_value());
  const auto committed = application.commit_sample_import(token);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().committed_revision == 3);
  active = application.query_sequence_status({project});
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().state == SequenceRecordState::active);
  LMDJ_CHECK(active.value().pending_event_count == 1);
  LMDJ_CHECK(active.value().expected_revision == 3);

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {armed_slot, 110, 12'002, 4, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {armed_slot, 0, 24'000, 5, false}})
                 .has_value());
  const auto stopped = application.stop_sequence(
      {project, session_id, CommandId{uuid(91)}, 24'001});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().committed_revision == 4);

  lmdj::project_io::ProjectStore reopened;
  const auto reloaded = reopened.load(project);
  LMDJ_CHECK(reloaded.has_value());
  LMDJ_CHECK(reloaded.value().banks.at(0).at(1).asset_id == AssetId{uuid(90)});
  const auto& events = reloaded.value().patterns.at(pattern_id).events;
  LMDJ_CHECK(events.size() == 2);
  LMDJ_CHECK(events.at(0).slot == PadSlotId(0, 0));
  LMDJ_CHECK(events.at(1).slot == armed_slot);
}

void test_cancelled_armed_capture_keeps_sequence_active_and_disarms_commit() {
  TempDirectory temp;
  const auto project = temp.path() / "cancelled-capture.lmdj";
  const PatternId pattern_id{uuid(92)};
  const SequenceSessionId session_id{uuid(93)};
  const PadSlotId armed_slot{0, 1};
  const auto wav = read_bytes("tests/fixtures/audio/kick.wav");
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);
  LMDJ_CHECK(application.begin_sequence(
      {project, session_id, pattern_id, 2, 0, armed_slot}).has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 1, 2, false}})
                 .has_value());
  LMDJ_CHECK(application.disarm_sequence_capture(
      {project, session_id, armed_slot}).has_value());
  const auto status = application.query_sequence_status({project});
  LMDJ_CHECK(status.has_value());
  LMDJ_CHECK(status.value().state == SequenceRecordState::active);
  LMDJ_CHECK(status.value().pending_event_count == 1);

  const auto rejected = application.begin_sample_import(
      SampleImportBeginRequest{
          uuid(94),
          project,
          CommandMeta{CommandId{uuid(95)}, 2},
          armed_slot,
          AssetId{uuid(96)},
          wav.size(),
          session_id,
      });
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().details.contains("reason"));
  LMDJ_CHECK(
      rejected.error().details.at("reason") == "armed_capture_not_armed");
  LMDJ_CHECK(application.stop_sequence(
      {project, session_id, CommandId{uuid(97)}, 1}).has_value());
}

void test_prepublication_capture_marker_can_disarm_and_preserve_pending_events() {
  TempDirectory temp;
  const auto project = temp.path() / "prepared-capture-discard.lmdj";
  const PatternId pattern_id{uuid(98)};
  const SequenceSessionId session_id{uuid(99)};
  const PadSlotId armed_slot{0, 1};
  auto platform = lmdj::project_io::make_default_project_storage_platform();
  auto application_config = config(temp.path());
  application_config.storage_platform = platform;
  Application application(std::move(application_config));
  create_recordable_project(application, project, pattern_id);
  LMDJ_CHECK(application.begin_sequence(
      {project, session_id, pattern_id, 2, 0, armed_slot}).has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 1, 2, false}})
                 .has_value());

  const auto artifact = lmdj::foundation::describe_artifact(
      "tests/fixtures/audio/kick.wav", "audio/wav");
  LMDJ_CHECK(artifact.has_value());
  lmdj::project_io::SequenceJournal journal{platform};
  const auto prepared = journal.prepare_armed_capture(
      project, session_id, CommandId{uuid(100)}, AssetId{uuid(101)},
      armed_slot, artifact.value(), 2);
  LMDJ_CHECK(prepared.has_value());

  LMDJ_CHECK(application.disarm_sequence_capture(
      {project, session_id, armed_slot}).has_value());
  const auto status = application.query_sequence_status({project});
  LMDJ_CHECK(status.has_value());
  LMDJ_CHECK(status.value().state == SequenceRecordState::active);
  LMDJ_CHECK(status.value().expected_revision == 2);
  LMDJ_CHECK(status.value().pending_event_count == 1);
  const auto disarmed = journal.read_active(project);
  LMDJ_CHECK(disarmed.has_value());
  LMDJ_CHECK(!disarmed.value().armed_capture_slot.has_value());
  LMDJ_CHECK(!disarmed.value().capture_commit.has_value());

  const auto stopped = application.stop_sequence(
      {project, session_id, CommandId{uuid(102)}, 1});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().committed_revision == 3);
  lmdj::project_io::ProjectStore reopened{platform};
  const auto truth = reopened.load(project);
  LMDJ_CHECK(truth.has_value());
  LMDJ_CHECK(truth.value().revision == 3);
  LMDJ_CHECK(truth.value().assets.size() == 1);
  LMDJ_CHECK(!truth.value().assets.contains(AssetId{uuid(101)}));
  LMDJ_CHECK(
      !truth.value().banks.at(armed_slot.bank).at(armed_slot.pad).asset_id
           .has_value());
  LMDJ_CHECK(truth.value().patterns.at(pattern_id).events.size() == 1);
}

}  // namespace

int main() {
  try {
    test_sequence_lifecycle_idempotence_and_mutation_exclusion();
    test_owner_loss_apply_and_discard_are_explicit();
    test_writer_lease_blocks_competing_sequence_owner();
    test_begin_cannot_cross_an_authoring_admission();
    test_orphan_journal_is_sealed_before_authoring();
    test_settings_rebase_and_pattern_creation_are_authoritative();
    test_armed_capture_commit_rebases_without_losing_pending_events();
    test_cancelled_armed_capture_keeps_sequence_active_and_disarms_commit();
    test_prepublication_capture_marker_can_disarm_and_preserve_pending_events();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "sequence facade surface tests: PASS\n";
  return 0;
}
