#include <atomic>
#include <chrono>
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <span>
#include <string>
#include <string_view>
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
      std::nullopt,
      nullptr,
  };
}

class JournalCompletionFailurePlatform final
    : public lmdj::project_io::ProjectStoragePlatform {
 public:
  explicit JournalCompletionFailurePlatform(
      std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner)
      : inner_(std::move(inner)) {}

  void arm() noexcept {
    armed_ = true;
    triggered_ = false;
  }

  bool triggered() const noexcept { return triggered_; }

  lmdj::foundation::Result<
      std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& path) override {
    return inner_->acquire_writer(path);
  }

  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    return inner_->ensure_directory(path);
  }

  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    return inner_->exists(path);
  }

  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    return inner_->byte_length(path);
  }

  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    return inner_->read_complete(path);
  }

  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner_->create_immutable(path, bytes);
  }

  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner_->replace_complete(path, bytes);
  }

  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> bytes) override {
    const std::string_view text{
        reinterpret_cast<const char*>(bytes.data()), bytes.size()};
    if (armed_ && path.filename() == "sequence.jsonl" &&
        text.find("\"kind\":\"complete\"") != std::string_view::npos) {
      armed_ = false;
      triggered_ = true;
      return lmdj::foundation::Result<void>::failure(
          lmdj::foundation::Error{
              ErrorCode::io_error,
              "injected Sequence journal completion failure",
          });
    }
    return inner_->append_durable(path, valid_prefix_length, bytes);
  }

  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    return inner_->remove(path);
  }

  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    return inner_->list_names(path);
  }

  lmdj::foundation::Result<std::vector<std::string>> list_directories(
      const std::filesystem::path& path) const override {
    return inner_->list_directories(path);
  }

  lmdj::foundation::Result<void> remove_tree(
      const std::filesystem::path& path) override {
    return inner_->remove_tree(path);
  }

  lmdj::foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path& source,
      const std::filesystem::path& destination) override {
    return inner_->publish_directory_if_absent(source, destination);
  }

  lmdj::foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const override {
    return inner_->directory_exists(path);
  }

  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& root) const override {
    return inner_->validate_managed_tree(root);
  }

 private:
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner_;
  bool armed_{};
  bool triggered_{};
};

ApplicationConfig config(
    const std::filesystem::path& root,
    std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> platform) {
  auto result = config(root);
  result.storage_platform = std::move(platform);
  return result;
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

  const auto advanced = application.command({
      {"operation", "sequence.settings.update"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(25)},
      {"expected_revision", 3},
      {"session_id", nullptr},
      {"runtime_frame", 12'002},
      {"bpm", 121},
      {"quantize_enabled", nullptr},
      {"swing_percent", nullptr},
  });
  LMDJ_CHECK(advanced.value("ok", false));
  LMDJ_CHECK(advanced.at("project_revision") == 4);

  Application restarted(config(temp.path()));
  const auto cross_host_replay = restarted.flush_sequence(flush);
  LMDJ_CHECK(cross_host_replay.has_value());
  LMDJ_CHECK(cross_host_replay.value().replayed);
  LMDJ_CHECK(cross_host_replay.value().committed_revision == 3);
  LMDJ_CHECK(cross_host_replay.value().status.expected_revision == 4);
  LMDJ_CHECK(
      cross_host_replay.value().status.state == SequenceRecordState::inactive);
}

void test_post_commit_retry_preserves_later_events_for_a_new_command() {
  TempDirectory temp;
  const auto project = temp.path() / "post-commit-retry.lmdj";
  const PatternId pattern_id{uuid(60)};
  const SequenceSessionId session_id{uuid(61)};
  auto platform = std::make_shared<JournalCompletionFailurePlatform>(
      lmdj::project_io::make_default_project_storage_platform());
  Application application(config(temp.path(), platform));
  create_recordable_project(application, project, pattern_id);

  LMDJ_CHECK(
      application.begin_sequence({project, session_id, pattern_id, 2, 0})
          .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
                 .has_value());

  const lmdj::facade::SequenceFlushRequest first_flush{
      project, session_id, CommandId{uuid(62)}, 12'000};
  platform->arm();
  const auto failed = application.flush_sequence(first_flush);
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(platform->triggered());
  lmdj::project_io::ProjectStore store{platform};
  LMDJ_CHECK(store.load(project).value().revision == 3);

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 24'000, 3, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 36'000, 4, false}})
                 .has_value());

  const auto retried = application.flush_sequence(first_flush);
  LMDJ_CHECK(retried.has_value());
  LMDJ_CHECK(retried.value().replayed);
  LMDJ_CHECK(retried.value().committed_revision == 3);
  LMDJ_CHECK(retried.value().status.pending_event_count == 1);

  const auto repeated = application.flush_sequence(first_flush);
  LMDJ_CHECK(repeated.has_value());
  LMDJ_CHECK(repeated.value().replayed);
  LMDJ_CHECK(repeated.value().committed_revision == 3);
  LMDJ_CHECK(repeated.value().status.pending_event_count == 1);

  const auto later = application.flush_sequence(
      {project, session_id, CommandId{uuid(63)}, 36'001});
  LMDJ_CHECK(later.has_value());
  LMDJ_CHECK(!later.value().replayed);
  LMDJ_CHECK(later.value().committed_revision == 4);
  LMDJ_CHECK(later.value().status.pending_event_count == 0);

  const auto stopped = application.stop_sequence(
      {project, session_id, CommandId{uuid(64)}, 36'002});
  LMDJ_CHECK(stopped.has_value());
  const auto loaded = store.load(project);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value().revision == 4);
  LMDJ_CHECK(loaded.value().patterns.at(pattern_id).events.size() == 2);
  LMDJ_CHECK(!std::filesystem::exists(
      project / "recovery/active/sequence.jsonl"));
}

void test_older_flush_replay_preserves_pending_events() {
  TempDirectory temp;
  const auto project = temp.path() / "older-flush-replay.lmdj";
  const PatternId pattern_id{uuid(80)};
  const SequenceSessionId session_id{uuid(81)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);

  LMDJ_CHECK(
      application.begin_sequence({project, session_id, pattern_id, 2, 0})
          .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
                 .has_value());
  const lmdj::facade::SequenceFlushRequest first{
      project, session_id, CommandId{uuid(82)}, 12'000};
  const auto first_result = application.flush_sequence(first);
  LMDJ_CHECK(first_result.has_value());
  LMDJ_CHECK(first_result.value().committed_revision == 3);

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 24'000, 3, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 36'000, 4, false}})
                 .has_value());
  const auto second = application.flush_sequence(
      {project, session_id, CommandId{uuid(83)}, 36'000});
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(second.value().committed_revision == 4);

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 48'000, 5, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 60'000, 6, false}})
                 .has_value());
  const auto journal_path = project / "recovery/active/sequence.jsonl";
  const auto journal_before_stale = read_bytes(journal_path);
  const auto stale_unknown = application.flush_sequence(
      {project, session_id, CommandId{uuid(86)}, first.runtime_frame});
  LMDJ_CHECK(!stale_unknown.has_value());
  LMDJ_CHECK(stale_unknown.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(journal_path) == journal_before_stale);
  LMDJ_CHECK(application.query_sequence_status({project})
                 .value()
                 .pending_event_count == 1);

  const auto replayed = application.flush_sequence(first);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().committed_revision == 3);
  LMDJ_CHECK(replayed.value().status.pending_event_count == 1);

  const auto third = application.flush_sequence(
      {project, session_id, CommandId{uuid(84)}, 60'001});
  LMDJ_CHECK(third.has_value());
  LMDJ_CHECK(!third.value().replayed);
  LMDJ_CHECK(third.value().committed_revision == 5);
  LMDJ_CHECK(third.value().status.pending_event_count == 0);
  LMDJ_CHECK(application.stop_sequence(
      {project, session_id, CommandId{uuid(85)}, 60'002}).has_value());
}

void test_project_command_collision_does_not_poison_sequence_journal() {
  TempDirectory temp;
  const auto project = temp.path() / "project-command-collision.lmdj";
  const PatternId pattern_id{uuid(90)};
  const SequenceSessionId session_id{uuid(91)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);

  LMDJ_CHECK(
      application.begin_sequence({project, session_id, pattern_id, 2, 0})
          .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
                 .has_value());
  const auto journal_path = project / "recovery/active/sequence.jsonl";
  const auto journal_before = read_bytes(journal_path);

  const auto collision = application.flush_sequence(
      {project, session_id, CommandId{uuid(12)}, 12'000});
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(journal_path) == journal_before);
  LMDJ_CHECK(application.query_sequence_status({project})
                 .value()
                 .pending_event_count == 1);

  const auto valid = application.flush_sequence(
      {project, session_id, CommandId{uuid(92)}, 12'001});
  LMDJ_CHECK(valid.has_value());
  LMDJ_CHECK(valid.value().committed_revision == 3);
  LMDJ_CHECK(application.stop_sequence(
      {project, session_id, CommandId{uuid(93)}, 12'002}).has_value());

  lmdj::project_io::ProjectStore store;
  const auto reconciled = store.reconcile_sequence_recovery(project);
  LMDJ_CHECK(reconciled.has_value());
  LMDJ_CHECK(reconciled.value().empty());
  const SequenceSessionId next_session{uuid(94)};
  LMDJ_CHECK(application.begin_sequence(
      {project, next_session, pattern_id, 3, 12'003}).has_value());
  LMDJ_CHECK(application.stop_sequence(
      {project, next_session, CommandId{uuid(95)}, 12'004}).has_value());
}

void test_prior_sequence_collision_does_not_poison_new_session() {
  TempDirectory temp;
  const auto project = temp.path() / "prior-sequence-collision.lmdj";
  const PatternId pattern_id{uuid(100)};
  const SequenceSessionId first_session{uuid(101)};
  const CommandId first_command{uuid(102)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);

  LMDJ_CHECK(application.begin_sequence(
      {project, first_session, pattern_id, 2, 0}).has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, first_session, {PadSlotId{0, 0}, 100, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, first_session, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
                 .has_value());
  LMDJ_CHECK(application.flush_sequence(
      {project, first_session, first_command, 12'000}).has_value());
  LMDJ_CHECK(application.stop_sequence(
      {project, first_session, CommandId{uuid(103)}, 12'001}).has_value());

  const SequenceSessionId second_session{uuid(104)};
  LMDJ_CHECK(application.begin_sequence(
      {project, second_session, pattern_id, 3, 24'000}).has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, second_session, {PadSlotId{0, 0}, 100, 24'000, 3, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, second_session, {PadSlotId{0, 0}, 0, 36'000, 4, false}})
                 .has_value());
  const auto journal_path = project / "recovery/active/sequence.jsonl";
  const auto journal_before = read_bytes(journal_path);

  const auto collision = application.flush_sequence(
      {project, second_session, first_command, 36'000});
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(journal_path) == journal_before);
  LMDJ_CHECK(application.query_sequence_status({project})
                 .value()
                 .pending_event_count == 1);

  const auto valid = application.flush_sequence(
      {project, second_session, CommandId{uuid(105)}, 36'001});
  LMDJ_CHECK(valid.has_value());
  LMDJ_CHECK(valid.value().committed_revision == 4);
  LMDJ_CHECK(application.stop_sequence(
      {project, second_session, CommandId{uuid(106)}, 36'002}).has_value());

  lmdj::project_io::ProjectStore store;
  const auto reconciled = store.reconcile_sequence_recovery(project);
  LMDJ_CHECK(reconciled.has_value());
  LMDJ_CHECK(reconciled.value().empty());
  const SequenceSessionId third_session{uuid(107)};
  LMDJ_CHECK(application.begin_sequence(
      {project, third_session, pattern_id, 4, 48'000}).has_value());
  LMDJ_CHECK(application.stop_sequence(
      {project, third_session, CommandId{uuid(108)}, 48'001}).has_value());
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

}  // namespace

int main() {
  try {
    test_sequence_lifecycle_idempotence_and_mutation_exclusion();
    test_post_commit_retry_preserves_later_events_for_a_new_command();
    test_older_flush_replay_preserves_pending_events();
    test_project_command_collision_does_not_poison_sequence_journal();
    test_prior_sequence_collision_does_not_poison_new_session();
    test_owner_loss_apply_and_discard_are_explicit();
    test_writer_lease_blocks_competing_sequence_owner();
    test_begin_cannot_cross_an_authoring_admission();
    test_orphan_journal_is_sealed_before_authoring();
    test_settings_rebase_and_pattern_creation_are_authoritative();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "sequence facade surface tests: PASS\n";
  return 0;
}
