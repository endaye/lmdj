#include <atomic>
#include <csignal>
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

#include <sys/wait.h>
#include <unistd.h>

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

void remove_last_journal_record(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  LMDJ_CHECK(static_cast<bool>(input));
  std::string contents{
      std::istreambuf_iterator<char>{input},
      std::istreambuf_iterator<char>{}};
  LMDJ_CHECK(contents.ends_with('\n'));
  const auto previous = contents.rfind('\n', contents.size() - 2);
  LMDJ_CHECK(previous != std::string::npos);
  contents.resize(previous + 1);
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  LMDJ_CHECK(static_cast<bool>(output));
  output.write(contents.data(), static_cast<std::streamsize>(contents.size()));
  LMDJ_CHECK(static_cast<bool>(output));
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

ApplicationConfig sample_config(const std::filesystem::path& root) {
  auto result = config(root);
  result.runtime_preparation_limits = lmdj::audio::RuntimePreparationLimits{
      1'048'576,
      67'108'864,
      134'217'728,
      134'217'728,
  };
  return result;
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

void test_post_commit_stop_retry_preserves_later_unreleased_press() {
  TempDirectory temp;
  const auto project = temp.path() / "post-commit-stop-retry.lmdj";
  const PatternId pattern_id{uuid(70)};
  const SequenceSessionId session_id{uuid(71)};
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
  const lmdj::facade::SequenceFlushRequest first_stop{
      project, session_id, CommandId{uuid(72)}, 12'000};
  platform->arm();
  const auto failed = application.stop_sequence(first_stop);
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(platform->triggered());

  lmdj::project_io::ProjectStore store{platform};
  LMDJ_CHECK(store.load(project).value().revision == 3);
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 90, 24'000, 2, true}})
                 .has_value());

  const auto replayed = application.stop_sequence(first_stop);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().committed_revision == 3);
  LMDJ_CHECK(replayed.value().status.state == SequenceRecordState::active);
  LMDJ_CHECK(replayed.value().status.session_id == session_id);
  LMDJ_CHECK(std::filesystem::exists(
      project / "recovery/active/sequence.jsonl"));

  const auto stopped = application.stop_sequence(
      {project, session_id, CommandId{uuid(73)}, 36'000});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(!stopped.value().replayed);
  LMDJ_CHECK(stopped.value().committed_revision == 4);
  LMDJ_CHECK(stopped.value().status.state == SequenceRecordState::inactive);
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

void test_sigkill_owner_recovers_acknowledged_unflushed_events() {
  TempDirectory temp;
  const auto project = temp.path() / "hard-owner-loss.lmdj";
  const PatternId pattern_id{uuid(33)};
  const SequenceSessionId session_id{uuid(34)};
  {
    Application creator(config(temp.path()));
    create_recordable_project(creator, project, pattern_id);
  }

  const auto child = ::fork();
  LMDJ_CHECK(child >= 0);
  if (child == 0) {
    Application owner(config(temp.path()));
    const bool accepted =
        owner.begin_sequence({project, session_id, pattern_id, 2, 0})
            .has_value() &&
        owner.record_sequence_event(
                 {project, session_id, {PadSlotId{0, 0}, 101, 0, 1, true}})
            .has_value() &&
        owner.record_sequence_event(
                 {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}})
            .has_value() &&
        owner.record_sequence_event(
                 {project, session_id,
                  {PadSlotId{0, 0}, 77, 12'000, 3, true}})
            .has_value();
    if (!accepted) {
      ::_exit(20);
    }
    ::raise(SIGSTOP);
    ::_exit(21);
  }

  int stopped_status = 0;
  LMDJ_CHECK(::waitpid(child, &stopped_status, WUNTRACED) == child);
  LMDJ_CHECK(WIFSTOPPED(stopped_status));
  LMDJ_CHECK(WSTOPSIG(stopped_status) == SIGSTOP);
  LMDJ_CHECK(::kill(child, SIGKILL) == 0);
  int killed_status = 0;
  LMDJ_CHECK(::waitpid(child, &killed_status, 0) == child);
  LMDJ_CHECK(WIFSIGNALED(killed_status));
  LMDJ_CHECK(WTERMSIG(killed_status) == SIGKILL);

  Application restarted(config(temp.path()));
  const auto reconciliation = restarted.begin_sequence(
      {project, SequenceSessionId{uuid(35)}, pattern_id, 999, 18'001});
  LMDJ_CHECK(!reconciliation.has_value());
  LMDJ_CHECK(reconciliation.error().code == ErrorCode::revision_conflict);

  const auto candidates = restarted.list_sequence_recovery({project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().session_id == session_id);
  LMDJ_CHECK(candidates.value().front().reason == "owner_lost");
  LMDJ_CHECK(candidates.value().front().event_count == 2);

  const auto applied = restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(applied.value().committed_revision == 3);
  lmdj::project_io::ProjectStore store;
  const auto recovered = store.load(project);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().revision == 3);
  const auto& events = recovered.value().patterns.at(pattern_id).events;
  LMDJ_CHECK(events.size() == 2);
  LMDJ_CHECK(events.at(0).slot.bank == 0);
  LMDJ_CHECK(events.at(0).slot.pad == 0);
  LMDJ_CHECK(events.at(0).onset_tick == 0);
  LMDJ_CHECK(events.at(0).duration_tick == 480);
  LMDJ_CHECK(events.at(0).velocity == 101);
  LMDJ_CHECK(events.at(1).slot.bank == 0);
  LMDJ_CHECK(events.at(1).slot.pad == 0);
  LMDJ_CHECK(events.at(1).onset_tick == 480);
  LMDJ_CHECK(events.at(1).duration_tick == 240);
  LMDJ_CHECK(events.at(1).velocity == 77);
}

void test_later_flush_supersedes_failed_flush_before_recovery_apply() {
  TempDirectory temp;
  const auto project = temp.path() / "superseded-flush.lmdj";
  const PatternId pattern_id{uuid(36)};
  const SequenceSessionId session_id{uuid(37)};
  {
    Application creator(config(temp.path()));
    create_recordable_project(creator, project, pattern_id);
  }

  lmdj::project_io::ProjectStore store;
  lmdj::project_io::SequenceJournal journal;
  const auto loaded = store.load(project);
  LMDJ_CHECK(loaded.has_value());
  const auto& pattern = loaded.value().patterns.at(pattern_id);
  LMDJ_CHECK(
      journal
          .begin(
              project,
              session_id,
              pattern_id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              loaded.value().revision)
          .has_value());

  const lmdj::domain::PatternEvent old_event{
      PadSlotId{0, 0}, 0, 120, 40};
  const lmdj::domain::PatternEvent replacement{
      PadSlotId{0, 0}, 0, 240, 90};
  const lmdj::domain::PatternEvent uncommitted{
      PadSlotId{0, 0}, 480, 120, 70};
  LMDJ_CHECK(
      journal.append_tail(project, session_id, pattern_id, 2, 1,
                          std::vector{old_event}).has_value());
  const auto first = journal.append_flush(
      project, session_id, CommandId{uuid(38)}, pattern_id, 2,
      std::vector{old_event});
  LMDJ_CHECK(first.has_value());
  const auto failed = store.execute_sequence_flush(
      project,
      {session_id, first.value().flush_seq, CommandId{uuid(39)}, pattern_id});
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(store.load(project).value().revision == 2);

  LMDJ_CHECK(
      journal.append_tail(project, session_id, pattern_id, 2, 2,
                          std::vector{replacement}).has_value());
  const auto second = journal.append_flush(
      project, session_id, CommandId{uuid(40)}, pattern_id, 2,
      std::vector{replacement});
  LMDJ_CHECK(second.has_value());
  const auto committed = store.execute_sequence_flush(
      project,
      {session_id, second.value().flush_seq, CommandId{uuid(40)}, pattern_id});
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().outcome.state.revision == 3);
  LMDJ_CHECK(
      committed.value().outcome.state.patterns.at(pattern_id).events ==
      std::vector{replacement});

  LMDJ_CHECK(
      journal.append_tail(project, session_id, pattern_id, 3, 3,
                          std::vector{uncommitted}).has_value());
  Application restarted(config(temp.path()));
  const auto reconciliation = restarted.begin_sequence(
      {project, SequenceSessionId{uuid(41)}, pattern_id, 999, 0});
  LMDJ_CHECK(!reconciliation.has_value());
  LMDJ_CHECK(reconciliation.error().code == ErrorCode::revision_conflict);

  const auto candidates = restarted.list_sequence_recovery({project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().event_count == 1);
  const auto applied = restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(applied.value().committed_revision == 4);

  const auto recovered = store.load(project);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().revision == 4);
  const auto& events = recovered.value().patterns.at(pattern_id).events;
  LMDJ_CHECK(events.size() == 2);
  LMDJ_CHECK(events.at(0) == replacement);
  LMDJ_CHECK(events.at(1) == uncommitted);
  LMDJ_CHECK(!restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt}).has_value());
  LMDJ_CHECK(!restarted.discard_sequence_recovery(
      {project, session_id, std::nullopt}).has_value());
  LMDJ_CHECK(store.load(project).value().revision == 4);
}

void test_replayed_completion_applies_only_durable_tail_residual_once() {
  TempDirectory temp;
  const auto project = temp.path() / "completion-tail-residual.lmdj";
  const PatternId pattern_id{uuid(42)};
  const SequenceSessionId session_id{uuid(43)};
  {
    Application creator(config(temp.path()));
    create_recordable_project(creator, project, pattern_id);
  }

  lmdj::project_io::ProjectStore store;
  lmdj::project_io::SequenceJournal journal;
  const auto initial = store.load(project);
  LMDJ_CHECK(initial.has_value());
  const auto& pattern = initial.value().patterns.at(pattern_id);
  LMDJ_CHECK(
      journal
          .begin(
              project,
              session_id,
              pattern_id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              initial.value().revision)
          .has_value());

  const lmdj::domain::PatternEvent exact{
      PadSlotId{0, 0}, 0, 120, 90};
  const lmdj::domain::PatternEvent committed_same_key{
      PadSlotId{0, 0}, 240, 120, 50};
  const lmdj::domain::PatternEvent replacement{
      PadSlotId{0, 0}, 240, 240, 110};
  const lmdj::domain::PatternEvent additional{
      PadSlotId{0, 0}, 480, 120, 70};
  const std::vector committed_batch{exact, committed_same_key};
  const std::vector durable_tail{exact, replacement, additional};
  const auto command_id = CommandId{uuid(44)};
  const auto flush = journal.append_flush(
      project,
      session_id,
      command_id,
      pattern_id,
      initial.value().revision,
      committed_batch);
  LMDJ_CHECK(flush.has_value());
  const auto committed = store.execute_sequence_flush(
      project,
      {session_id, flush.value().flush_seq, command_id, pattern_id});
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().outcome.state.revision == 3);

  remove_last_journal_record(
      project / "recovery/active/sequence.jsonl");
  const auto incomplete = journal.read_active(project);
  LMDJ_CHECK(incomplete.has_value());
  LMDJ_CHECK(!incomplete.value().flushes.at(0).completed);
  LMDJ_CHECK(
      journal.append_tail(
          project,
          session_id,
          pattern_id,
          initial.value().revision,
          1,
          durable_tail)
          .has_value());

  Application restarted(config(temp.path()));
  const auto reconciliation = restarted.begin_sequence(
      {project, SequenceSessionId{uuid(45)}, pattern_id, 999, 0});
  LMDJ_CHECK(!reconciliation.has_value());
  LMDJ_CHECK(reconciliation.error().code == ErrorCode::revision_conflict);
  const auto candidates = restarted.list_sequence_recovery({project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().event_count == 2);

  const auto applied = restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(applied.value().committed_revision == 4);
  const auto recovered = store.load(project);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().revision == 4);
  const std::vector expected_recovered{exact, replacement, additional};
  LMDJ_CHECK(
      recovered.value().patterns.at(pattern_id).events ==
      expected_recovered);
  LMDJ_CHECK(!restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt}).has_value());
  LMDJ_CHECK(!restarted.discard_sequence_recovery(
      {project, session_id, std::nullopt}).has_value());
  LMDJ_CHECK(store.load(project).value().revision == 4);
}

void test_inverse_completion_recovery_applies_only_effective_residual_once() {
  TempDirectory temp;
  const auto project = temp.path() / "inverse-flush-residual.lmdj";
  const PatternId pattern_id{uuid(46)};
  const SequenceSessionId session_id{uuid(47)};
  {
    Application creator(config(temp.path()));
    create_recordable_project(creator, project, pattern_id);
  }

  lmdj::project_io::ProjectStore store;
  lmdj::project_io::SequenceJournal journal;
  const auto initial = store.load(project);
  LMDJ_CHECK(initial.has_value());
  const auto& pattern = initial.value().patterns.at(pattern_id);
  LMDJ_CHECK(
      journal
          .begin(
              project,
              session_id,
              pattern_id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              initial.value().revision)
          .has_value());

  const lmdj::domain::PatternEvent committed{
      PadSlotId{0, 0}, 0, 120, 90};
  const lmdj::domain::PatternEvent residual{
      PadSlotId{0, 0}, 240, 120, 70};
  const std::vector first_batch{committed};
  const std::vector second_batch{committed, residual};
  const auto first_command = CommandId{uuid(48)};
  const auto second_command = CommandId{uuid(49)};
  const auto first = journal.append_flush(
      project,
      session_id,
      first_command,
      pattern_id,
      initial.value().revision,
      first_batch);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(
      journal.append_tail(
          project,
          session_id,
          pattern_id,
          initial.value().revision,
          1,
          second_batch)
          .has_value());
  const auto second = journal.append_flush(
      project,
      session_id,
      second_command,
      pattern_id,
      initial.value().revision,
      second_batch);
  LMDJ_CHECK(second.has_value());
  const auto executed = store.execute_sequence_flush(
      project,
      {session_id, first.value().flush_seq, first_command, pattern_id});
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().outcome.state.revision == 3);
  const auto exact_retry = journal.append_flush(
      project,
      session_id,
      second_command,
      pattern_id,
      initial.value().revision,
      second_batch);
  LMDJ_CHECK(exact_retry.has_value());
  LMDJ_CHECK(exact_retry.value().flush_seq == second.value().flush_seq);

  Application restarted(config(temp.path()));
  const auto reconciliation = restarted.begin_sequence(
      {project, SequenceSessionId{uuid(50)}, pattern_id, 999, 0});
  LMDJ_CHECK(!reconciliation.has_value());
  LMDJ_CHECK(reconciliation.error().code == ErrorCode::revision_conflict);
  const auto candidates = restarted.list_sequence_recovery({project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().event_count == 1);

  const auto applied = restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(applied.value().committed_revision == 4);
  const auto recovered = store.load(project);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().revision == 4);
  LMDJ_CHECK(
      recovered.value().patterns.at(pattern_id).events == second_batch);
  LMDJ_CHECK(!restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt}).has_value());
  LMDJ_CHECK(!restarted.discard_sequence_recovery(
      {project, session_id, std::nullopt}).has_value());
  LMDJ_CHECK(store.load(project).value().revision == 4);
}

void test_durable_tail_overrides_older_flush_residual_in_recovery() {
  TempDirectory temp;
  const auto project = temp.path() / "tail-precedence-recovery.lmdj";
  const PatternId pattern_id{uuid(109)};
  const SequenceSessionId session_id{uuid(110)};
  {
    Application creator(config(temp.path()));
    create_recordable_project(creator, project, pattern_id);
  }

  lmdj::project_io::ProjectStore store;
  lmdj::project_io::SequenceJournal journal;
  const auto initial = store.load(project);
  LMDJ_CHECK(initial.has_value());
  const auto& pattern = initial.value().patterns.at(pattern_id);
  LMDJ_CHECK(
      journal
          .begin(
              project,
              session_id,
              pattern_id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              initial.value().revision)
          .has_value());

  const lmdj::domain::PatternEvent old_value{
      PadSlotId{0, 0}, 0, 120, 50};
  const lmdj::domain::PatternEvent new_value{
      PadSlotId{0, 0}, 0, 240, 110};
  const lmdj::domain::PatternEvent additional{
      PadSlotId{0, 1}, 240, 120, 70};
  const auto first_command = CommandId{uuid(111)};
  const auto first = journal.append_flush(
      project,
      session_id,
      first_command,
      pattern_id,
      initial.value().revision,
      std::vector{old_value});
  LMDJ_CHECK(first.has_value());
  const auto failed = store.execute_sequence_flush(
      project,
      {session_id,
       first.value().flush_seq,
       CommandId{uuid(112)},
       pattern_id});
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(store.load(project).value().revision == initial.value().revision);
  LMDJ_CHECK(
      journal
          .append_tail(
              project,
              session_id,
              pattern_id,
              initial.value().revision,
              1,
              std::vector{new_value, additional})
          .has_value());
  const auto reconciled = store.reconcile_sequence_recovery(project);
  LMDJ_CHECK(reconciled.has_value());
  LMDJ_CHECK(reconciled.value().size() == 1);

  Application restarted(config(temp.path()));
  const auto status = restarted.query_sequence_status({project});
  LMDJ_CHECK(status.has_value());
  LMDJ_CHECK(status.value().state == SequenceRecordState::recoverable);
  LMDJ_CHECK(status.value().pending_event_count == 2);
  const auto candidates = restarted.list_sequence_recovery({project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().event_count == 2);

  const auto applied = restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(
      applied.value().committed_revision == initial.value().revision + 1);
  const auto recovered = store.load(project);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(
      recovered.value().revision == initial.value().revision + 1);
  const std::vector expected_recovery{new_value, additional};
  LMDJ_CHECK(
      recovered.value().patterns.at(pattern_id).events ==
      expected_recovery);
  LMDJ_CHECK(!restarted.apply_sequence_recovery(
      {project, session_id, std::nullopt}).has_value());
  LMDJ_CHECK(!restarted.discard_sequence_recovery(
      {project, session_id, std::nullopt}).has_value());
  LMDJ_CHECK(
      store.load(project).value().revision == initial.value().revision + 1);
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

void test_pending_overlay_projection_is_owner_scoped_and_replaceable() {
  TempDirectory temp;
  const auto project = temp.path() / "pending-overlay.lmdj";
  const PatternId pattern_id{uuid(80)};
  const SequenceSessionId session_id{uuid(81)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);
  LMDJ_CHECK(application.begin_sequence(
      {project, session_id, pattern_id, 2, 0}).has_value());

  const auto initial = application.query_sequence_overlay(
      {project, session_id});
  LMDJ_CHECK(initial.has_value());
  LMDJ_CHECK(initial.value().session_id == session_id);
  LMDJ_CHECK(initial.value().pattern_id == pattern_id);
  LMDJ_CHECK(initial.value().generation == 0);
  LMDJ_CHECK(initial.value().events.empty());

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 80, 0, 1, true}})
                 .has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 110, 3'000, 2, true}})
                 .has_value());
  const auto first = application.query_sequence_overlay(
      {project, session_id});
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(first.value().generation == 1);
  LMDJ_CHECK(first.value().events.size() == 1);
  LMDJ_CHECK((first.value().events.front().slot == PadSlotId{0, 0}));
  LMDJ_CHECK(first.value().events.front().onset_tick == 0);
  LMDJ_CHECK(first.value().events.front().velocity == 80);

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 5'000, 3, false}})
                 .has_value());
  const auto replaced = application.query_sequence_overlay(
      {project, session_id});
  LMDJ_CHECK(replaced.has_value());
  LMDJ_CHECK(replaced.value().generation == 2);
  LMDJ_CHECK(replaced.value().events.size() == 1);
  LMDJ_CHECK(replaced.value().events.front().velocity == 110);

  const auto rejected = application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 5'001, 4, false}});
  LMDJ_CHECK(!rejected.has_value());
  const auto after_rejection = application.query_sequence_overlay(
      {project, session_id});
  LMDJ_CHECK(after_rejection.has_value());
  LMDJ_CHECK(after_rejection.value().generation == 2);
  LMDJ_CHECK(after_rejection.value().events == replaced.value().events);

  const auto wrong_owner = application.query_sequence_overlay(
      {project, SequenceSessionId{uuid(82)}});
  LMDJ_CHECK(!wrong_owner.has_value());
  LMDJ_CHECK(wrong_owner.error().code == ErrorCode::invalid_argument);

  const auto flushed = application.flush_sequence(
      {project, session_id, CommandId{uuid(83)}, 6'000});
  LMDJ_CHECK(flushed.has_value());
  const auto empty = application.query_sequence_overlay(
      {project, session_id});
  LMDJ_CHECK(empty.has_value());
  LMDJ_CHECK(empty.value().generation == 3);
  LMDJ_CHECK(empty.value().events.empty());
}

void test_switch_pending_bpm_rejects_before_project_mutation() {
  TempDirectory temp;
  const auto project = temp.path() / "switch-settings.lmdj";
  const PatternId pattern_id{uuid(90)};
  const PatternId target_pattern_id{uuid(91)};
  const SequenceSessionId session_id{uuid(92)};
  Application application(config(temp.path()));
  create_recordable_project(application, project, pattern_id);
  const auto created = application.command({
      {"operation", "pattern.create"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(93)},
      {"expected_revision", 2},
      {"pattern_id", target_pattern_id.value()},
      {"bars", 1},
  });
  LMDJ_CHECK(created.value("ok", false));
  LMDJ_CHECK(application.begin_sequence(
      {project, session_id, pattern_id, 3, 0}).has_value());
  LMDJ_CHECK(application.request_sequence_switch(
      {project, session_id, target_pattern_id, 1}).has_value());

  const auto rejected = application.command({
      {"operation", "sequence.settings.update"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(94)},
      {"expected_revision", 3},
      {"session_id", session_id.value()},
      {"runtime_frame", 2},
      {"bpm", 90},
      {"quantize_enabled", nullptr},
      {"swing_percent", nullptr},
  });
  LMDJ_CHECK(!rejected.value("ok", false));
  LMDJ_CHECK(rejected.at("error").at("code") == "INVALID_ARGUMENT");
  lmdj::project_io::ProjectStore store;
  const auto inspected = store.load(project);
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().revision == 3);
  LMDJ_CHECK(inspected.value().bpm == 120);
}

void test_armed_capture_commit_rebases_without_stopping_sequence() {
  TempDirectory temp;
  const auto project = temp.path() / "armed-capture.lmdj";
  const PatternId pattern_id{uuid(100)};
  const SequenceSessionId session_id{uuid(101)};
  const PadSlotId armed_slot{0, 1};
  const auto bytes = read_bytes("tests/fixtures/audio/mono-44100.wav");
  Application application(sample_config(temp.path()));
  create_recordable_project(application, project, pattern_id);

  const auto begun = application.begin_sequence(
      {project, session_id, pattern_id, 2, 0, armed_slot});
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 100, 0, 1, true}}).has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {PadSlotId{0, 0}, 0, 12'000, 2, false}}).has_value());
  const auto before = application.query_sequence_status({project});
  LMDJ_CHECK(before.has_value());
  LMDJ_CHECK(before.value().pending_event_count == 1);

  const auto cancelled_token = uuid(109);
  LMDJ_CHECK(application.begin_sample_import(SampleImportBeginRequest{
      cancelled_token,
      project,
      {CommandId{uuid(110)}, 2},
      armed_slot,
      AssetId{uuid(111)},
      bytes.size(),
      session_id,
  }).has_value());
  LMDJ_CHECK(application.append_sample_import(
      cancelled_token,
      0,
      std::span<const std::byte>{bytes}.first(bytes.size() / 2),
      false).has_value());
  LMDJ_CHECK(application.abort_sample_import(cancelled_token).has_value());
  const auto after_cancel = application.query_sequence_status({project});
  LMDJ_CHECK(after_cancel.has_value());
  LMDJ_CHECK(after_cancel.value() == before.value());

  const auto wrong_token = uuid(102);
  LMDJ_CHECK(application.begin_sample_import(SampleImportBeginRequest{
      wrong_token,
      project,
      {CommandId{uuid(103)}, 2},
      PadSlotId{0, 2},
      AssetId{uuid(104)},
      bytes.size(),
      session_id,
  }).has_value());
  LMDJ_CHECK(application.append_sample_import(
      wrong_token, 0, bytes, true).has_value());
  const auto wrong = application.commit_sample_import(wrong_token);
  LMDJ_CHECK(!wrong.has_value());
  LMDJ_CHECK(wrong.error().details.at("reason") ==
             "armed_capture_target_mismatch");
  const auto after_wrong = application.query_sequence_status({project});
  LMDJ_CHECK(after_wrong.has_value());
  LMDJ_CHECK(after_wrong.value() == before.value());

  const auto token = uuid(105);
  LMDJ_CHECK(application.begin_sample_import(SampleImportBeginRequest{
      token,
      project,
      {CommandId{uuid(106)}, 2},
      armed_slot,
      AssetId{uuid(107)},
      bytes.size(),
      session_id,
  }).has_value());
  LMDJ_CHECK(application.append_sample_import(token, 0, bytes, true).has_value());
  const auto committed = application.commit_sample_import(token);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().committed_revision == 3);
  const auto active = application.query_sequence_status({project});
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().state == SequenceRecordState::active);
  LMDJ_CHECK(active.value().session_id == session_id);
  LMDJ_CHECK(active.value().expected_revision == 3);
  LMDJ_CHECK(active.value().pending_event_count == 1);

  const auto reused_token = uuid(112);
  LMDJ_CHECK(application.begin_sample_import(SampleImportBeginRequest{
      reused_token,
      project,
      {CommandId{uuid(113)}, 3},
      armed_slot,
      AssetId{uuid(114)},
      bytes.size(),
      session_id,
  }).has_value());
  LMDJ_CHECK(application.append_sample_import(
      reused_token, 0, bytes, true).has_value());
  const auto reused = application.commit_sample_import(reused_token);
  LMDJ_CHECK(!reused.has_value());
  LMDJ_CHECK(reused.error().details.at("reason") ==
             "armed_capture_target_mismatch");
  const auto after_reuse = application.query_sequence_status({project});
  LMDJ_CHECK(after_reuse.has_value());
  LMDJ_CHECK(after_reuse.value() == active.value());

  const auto flushed = application.flush_sequence(
      {project, session_id, CommandId{uuid(115)}, 24'000});
  LMDJ_CHECK(flushed.has_value());
  LMDJ_CHECK(flushed.value().committed_revision == 4);
  LMDJ_CHECK(flushed.value().status.state == SequenceRecordState::active);
  LMDJ_CHECK(flushed.value().status.pending_event_count == 0);

  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {armed_slot, 96, 24'000, 3, true}}).has_value());
  LMDJ_CHECK(application.record_sequence_event(
      {project, session_id, {armed_slot, 0, 36'000, 4, false}}).has_value());
  const auto stopped = application.stop_sequence(
      {project, session_id, CommandId{uuid(108)}, 48'000});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(stopped.value().committed_revision == 5);

  lmdj::project_io::ProjectStore store;
  const auto loaded = store.load(project);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value().revision == 5);
  LMDJ_CHECK(loaded.value().banks.at(0).at(1).asset_id == AssetId{uuid(107)});
  LMDJ_CHECK(loaded.value().patterns.at(pattern_id).events.size() == 2);
}

}  // namespace

int main() {
  try {
    test_sequence_lifecycle_idempotence_and_mutation_exclusion();
    test_post_commit_retry_preserves_later_events_for_a_new_command();
    test_post_commit_stop_retry_preserves_later_unreleased_press();
    test_older_flush_replay_preserves_pending_events();
    test_project_command_collision_does_not_poison_sequence_journal();
    test_prior_sequence_collision_does_not_poison_new_session();
    test_owner_loss_apply_and_discard_are_explicit();
    test_sigkill_owner_recovers_acknowledged_unflushed_events();
    test_later_flush_supersedes_failed_flush_before_recovery_apply();
    test_replayed_completion_applies_only_durable_tail_residual_once();
    test_inverse_completion_recovery_applies_only_effective_residual_once();
    test_durable_tail_overrides_older_flush_residual_in_recovery();
    test_writer_lease_blocks_competing_sequence_owner();
    test_begin_cannot_cross_an_authoring_admission();
    test_orphan_journal_is_sealed_before_authoring();
    test_settings_rebase_and_pattern_creation_are_authoritative();
    test_pending_overlay_projection_is_owner_scoped_and_replaceable();
    test_switch_pending_bpm_rejects_before_project_mutation();
    test_armed_capture_commit_rebases_without_stopping_sequence();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "sequence facade surface tests: PASS\n";
  return 0;
}
