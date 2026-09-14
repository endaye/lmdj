#include <array>
#include <chrono>
#include <filesystem>
#include <functional>
#include <iostream>
#include <memory>
#include <span>
#include <unistd.h>
#include <vector>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/pattern_transport_ports.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "packages/application-facade/src/pattern_transport_controller.hpp"
#include "tests/core/support/test.hpp"

namespace {
using lmdj::audio::PatternPublishResult;
using lmdj::audio::PreparedPatternView;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::cooker::ResolvedEvent;
using lmdj::cooker::ResolvedPad;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::PadSlotId;
using lmdj::domain::TriggerMode;
using lmdj::facade::PatternTransportIntent;
using lmdj::facade::PatternTransportPhase;
using lmdj::facade::PatternTransportRequest;
using lmdj::facade::PatternTransportSubmit;
using lmdj::project_io::SequenceSwitchOutcome;
using lmdj::facade::detail::PatternAdmissionAdmit;
using lmdj::facade::detail::PatternTransportAudioPort;
using lmdj::facade::detail::PatternTransportCoordinator;
using lmdj::project_io::SequenceCandidateKind;
using lmdj::foundation::CommandId;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;

constexpr auto kProject = "00000000-0000-4000-8000-000000000004";
constexpr auto kPattern = "00000000-0000-4000-8000-000000000002";
constexpr auto kPatternB = "00000000-0000-4000-8000-00000000000b";
constexpr auto kPatternC = "00000000-0000-4000-8000-00000000000c";

std::string uuid(unsigned suffix) {
  const auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') + tail;
}

RuntimeSnapshot pattern_snapshot(const char* pattern_id = kPattern) {
  auto sample = std::make_shared<const lmdj::cooker::PcmSample>(
      lmdj::cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(128, 1)});
  return RuntimeSnapshot{
      ProjectId{kProject}, PatternId{pattern_id}, 1, 120, 1,
      lmdj::domain::kPpq, lmdj::domain::kBarTicks4x4,
      {ResolvedPad{
          PadSlotId{0, 0},
          lmdj::foundation::ArtifactRef{std::string(64, 'a'), "audio/wav", 256},
          sample,
          ResolvedPlayback{0, 128, TriggerMode::loop_gate, 1.0F, false},
      }},
      {ResolvedEvent{
          PadSlotId{0, 0}, 0, lmdj::domain::kBarTicks4x4, 127, sample,
      }},
  };
}

class TempDirectory {
 public:
  explicit TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-transport-" + std::to_string(::getpid()) + "-" +
             std::to_string(std::chrono::steady_clock::now()
                                .time_since_epoch()
                                .count()));
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

struct EnginePort final : PatternTransportAudioPort {
  RealtimeEngine engine;
  std::uint64_t generation{};
  std::function<void()> before_ack;
  std::optional<lmdj::audio::PatternReplacementAuthority> queued_switch_;
  EnginePort() {
    LMDJ_CHECK(engine.enable_pattern_transport(7).has_value());
    LMDJ_CHECK(engine.publish_sample_bank(
        PreparedSampleBank::empty(ProjectId{kProject}, 1)) ==
               PublishResult::accepted);
    auto view = PreparedPatternView::from_snapshot(pattern_snapshot());
    LMDJ_CHECK(view.has_value());
    const auto published = engine.publish_pattern_view(std::move(view.value()));
    LMDJ_CHECK(published.result == PatternPublishResult::accepted);
    generation = published.generation;
    LMDJ_CHECK(engine.start().has_value());
  }
  lmdj::audio::PatternTransportSubmit submit(
      const lmdj::audio::PatternTransportCommand& command) override {
    return engine.submit_pattern_transport(command);
  }
  std::optional<lmdj::audio::PatternTransportReceipt> inspect(
      std::uint64_t runtime_generation, std::uint64_t epoch) const override {
    return engine.inspect_pattern_transport_receipt(runtime_generation, epoch);
  }
  bool acknowledge(std::uint64_t runtime_generation, std::uint64_t epoch) override {
    if (before_ack) before_ack();
    return engine.acknowledge_pattern_transport_receipt(
        runtime_generation, epoch);
  }
  std::uint64_t pattern_generation() const override {
    return engine.pattern_telemetry().current_generation;
  }
  std::optional<lmdj::audio::PatternReplacementAuthority> pending_switch()
      const override {
    const auto pending = engine.pending_pattern_id();
    if (pending) {
      const auto telemetry = engine.pattern_telemetry();
      return lmdj::audio::PatternReplacementAuthority{
          telemetry.pending_generation, *pending,
          telemetry.pending_activation_frame};
    }
    if (queued_switch_ &&
        engine.current_pattern_id() == queued_switch_->pattern_id &&
        engine.pattern_telemetry().current_generation ==
            queued_switch_->generation) {
      return queued_switch_;
    }
    return std::nullopt;
  }
  lmdj::audio::PatternPublication try_switch(
      const char* pattern_id, std::uint64_t activation_frame,
      std::optional<lmdj::audio::PatternReplacementAuthority> authority =
          std::nullopt) {
    auto view = PreparedPatternView::from_snapshot(pattern_snapshot(pattern_id));
    LMDJ_CHECK(view.has_value());
    const auto publication = engine.publish_pattern_view(
        std::move(view.value()), activation_frame, authority);
    if (publication.result == PatternPublishResult::accepted) {
      queued_switch_ = lmdj::audio::PatternReplacementAuthority{
          publication.generation, PatternId{pattern_id},
          publication.activation_frame};
    }
    return publication;
  }
  void queue_switch(std::uint64_t activation_frame) {
    LMDJ_CHECK(try_switch(kPatternB, activation_frame).result ==
               PatternPublishResult::accepted);
  }
  void render(std::uint64_t frames = 1) {
    std::array<float, 256> left{};
    std::array<float, 256> right{};
    while (frames != 0) {
      const auto block = static_cast<std::uint32_t>(
          std::min<std::uint64_t>(frames, left.size()));
      engine.render(left.data(), right.data(), block);
      frames -= block;
    }
  }
};

class FailingAppendStorage final : public lmdj::project_io::ProjectStoragePlatform {
 public:
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner =
      lmdj::project_io::make_default_project_storage_platform();
  int fail_appends = 0;

  lmdj::foundation::Result<std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& path) override {
    return inner->acquire_writer(path);
  }
  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    return inner->ensure_directory(path);
  }
  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    return inner->exists(path);
  }
  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    return inner->byte_length(path);
  }
  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    return inner->read_complete(path);
  }
  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner->create_immutable(path, bytes);
  }
  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner->replace_complete(path, bytes);
  }
  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path, std::uint64_t prefix,
      std::span<const std::byte> bytes) override {
    if (fail_appends > 0) {
      --fail_appends;
      return lmdj::foundation::Result<void>::failure(
          {lmdj::foundation::ErrorCode::io_error,
           "injected admission append failure",
           {{"journal_retained", true}}});
    }
    return inner->append_durable(path, prefix, bytes);
  }
  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    return inner->remove(path);
  }
  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    return inner->list_names(path);
  }
  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& path) const override {
    return inner->validate_managed_tree(path);
  }
};

struct Fixture {
  std::shared_ptr<FailingAppendStorage> platform{
      std::make_shared<FailingAppendStorage>()};
  TempDirectory directory;
  lmdj::project_io::ProjectStore store;
  std::filesystem::path bundle;
  lmdj::project_io::SequenceJournal journals;
  SequenceSessionId session{uuid(1)};
  PatternId pattern{kPattern};
  EnginePort audio;
  PatternTransportCoordinator coordinator;

  Fixture()
      : bundle(directory.path() / "project.lmdj"),
        journals(platform),
        coordinator(audio, journals, store, bundle, session, ProjectId{kProject},
                    pattern, 7) {
    auto created = lmdj::domain::create_project(ProjectId{kProject}, 120);
    LMDJ_CHECK(created.has_value());
    auto state = std::move(created.value());
    state.patterns.emplace(pattern, lmdj::domain::Pattern{pattern, 1, {}});
    state.patterns.emplace(PatternId{kPatternB},
                           lmdj::domain::Pattern{PatternId{kPatternB}, 1, {}});
    state.patterns.emplace(PatternId{kPatternC},
                           lmdj::domain::Pattern{PatternId{kPatternC}, 1, {}});
    LMDJ_CHECK(store.create(bundle, state).has_value());
    LMDJ_CHECK(journals
                   .begin(bundle, session, pattern, 1,
                          lmdj::project_io::sequence_pattern_fingerprint(
                              state.patterns.at(pattern)),
                          0)
                   .has_value());
  }

  PatternTransportRequest make(unsigned command, std::uint64_t epoch,
                               PatternTransportIntent intent) const {
    return {session, ProjectId{kProject}, CommandId{uuid(command)}, 7, epoch,
            intent, {}};
  }

  void settle(const PatternTransportRequest& request) {
    LMDJ_CHECK(coordinator.request(request) == PatternTransportSubmit::accepted);
    audio.render(1);
    LMDJ_CHECK(coordinator.continue_operation().has_value());
  }
};

void stopped_play_starts_without_a_journal() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  const auto status = f.coordinator.inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(!status.recording);
  LMDJ_CHECK(status.phase == PatternTransportPhase::idle);
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(!journal.value().admission);
}

void stopped_record_starts_playing_and_opens_admission() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto status = f.coordinator.inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(status.recording);
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.value().admission.has_value());
  LMDJ_CHECK(journal.value().admission->admission_fence.has_value());
  LMDJ_CHECK(journal.value().admission->admission_fence->origin_frame ==
             status.origin_frame);
}

void playing_play_stops_without_a_journal() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  f.settle(f.make(7, 2, PatternTransportIntent::play_stop));
  const auto status = f.coordinator.inspect();
  LMDJ_CHECK(!status.playing);
  LMDJ_CHECK(!status.recording);
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(!journal.value().admission);
}

void playing_record_keeps_origin_and_opens_admission() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  const auto origin = f.coordinator.inspect().origin_frame;
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto status = f.coordinator.inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(status.recording);
  LMDJ_CHECK(status.origin_frame == origin);
}

void recording_play_stops_scheduling_and_closes_admission() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  f.settle(f.make(7, 2, PatternTransportIntent::play_stop));
  const auto status = f.coordinator.inspect();
  LMDJ_CHECK(!status.playing);
  LMDJ_CHECK(!status.recording);
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.value().admission->closure.has_value());
  LMDJ_CHECK(journal.value().admission->cutoff_fence.has_value());
}

void recording_record_commits_and_keeps_playing() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto origin = f.coordinator.inspect().origin_frame;
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto status = f.coordinator.inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(!status.recording);
  LMDJ_CHECK(status.origin_frame == origin);
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.value().admission->closure.has_value());
}

void duplicate_command_does_not_toggle_twice() {
  Fixture f;
  const auto first = f.make(6, 1, PatternTransportIntent::play_stop);
  f.settle(first);
  LMDJ_CHECK(f.coordinator.request(first) == PatternTransportSubmit::replayed);
  LMDJ_CHECK(f.coordinator.inspect().playing);
  auto changed = first;
  changed.intent = PatternTransportIntent::record;
  LMDJ_CHECK(f.coordinator.request(changed) == PatternTransportSubmit::invalid);
  LMDJ_CHECK(f.coordinator.inspect().playing);
  LMDJ_CHECK(!f.coordinator.inspect().recording);
}

void earlier_command_does_not_toggle_after_a_later_one() {
  Fixture f;
  const auto play = f.make(6, 1, PatternTransportIntent::play_stop);
  f.settle(play);
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  LMDJ_CHECK(f.coordinator.inspect().playing);
  LMDJ_CHECK(f.coordinator.inspect().recording);
  LMDJ_CHECK(f.coordinator.request(play) == PatternTransportSubmit::replayed);
  LMDJ_CHECK(f.coordinator.inspect().playing);
  LMDJ_CHECK(f.coordinator.inspect().recording);
}

void wrong_session_or_project_is_invalid() {
  Fixture f;
  auto session = f.make(6, 1, PatternTransportIntent::play_stop);
  session.session = SequenceSessionId{uuid(99)};
  LMDJ_CHECK(f.coordinator.request(session) == PatternTransportSubmit::invalid);
  auto project = f.make(7, 1, PatternTransportIntent::play_stop);
  project.project_id = ProjectId{uuid(98)};
  LMDJ_CHECK(f.coordinator.request(project) == PatternTransportSubmit::invalid);
}

void recording_stop_retains_cutoff_before_ack() {
  Fixture f;
  bool cutoff_before_ack = false;
  f.audio.before_ack = [&] {
    const auto journal = f.journals.read_active(f.bundle);
    cutoff_before_ack = journal.has_value() && journal.value().admission &&
        journal.value().admission->cutoff_fence.has_value();
  };
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  cutoff_before_ack = false;
  f.settle(f.make(7, 2, PatternTransportIntent::play_stop));
  LMDJ_CHECK(cutoff_before_ack);
  LMDJ_CHECK(!f.coordinator.inspect().playing);
  LMDJ_CHECK(!f.coordinator.inspect().recording);
}

void close_failure_after_ack_keeps_audio_and_retries() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  f.audio.before_ack = [&] { f.platform->fail_appends = 1; };
  const auto stop = f.make(7, 2, PatternTransportIntent::play_stop);
  LMDJ_CHECK(f.coordinator.request(stop) == PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(!f.coordinator.continue_operation().has_value());
  const auto failed = f.coordinator.inspect();
  LMDJ_CHECK(!failed.playing);
  LMDJ_CHECK(failed.recording);
  LMDJ_CHECK(failed.phase == PatternTransportPhase::flushing);
  LMDJ_CHECK(f.coordinator.request(stop) == PatternTransportSubmit::replayed);
  LMDJ_CHECK(f.coordinator.continue_operation().has_value());
  const auto recovered = f.coordinator.inspect();
  LMDJ_CHECK(!recovered.playing);
  LMDJ_CHECK(!recovered.recording);
  LMDJ_CHECK(recovered.phase == PatternTransportPhase::idle);
}

lmdj::project_io::SequenceAdmissionFence cutoff_of(Fixture& f) {
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().admission && journal.value().admission->cutoff_fence);
  return *journal.value().admission->cutoff_fence;
}

void switch_at_or_after_cutoff_is_canceled() {
  for (const auto activation : {std::uint64_t{2}, std::uint64_t{200}}) {
    Fixture f;
    f.settle(f.make(6, 1, PatternTransportIntent::record));
    f.audio.queue_switch(activation);
    LMDJ_CHECK(f.audio.pending_switch().has_value());
    f.settle(f.make(7, 2, PatternTransportIntent::record));
    f.audio.render(300);
    const auto cutoff = cutoff_of(f);
    LMDJ_CHECK(cutoff.switch_outcome == SequenceSwitchOutcome::canceled_at_cutoff);
    LMDJ_CHECK(!cutoff.switch_applied_frame);
    LMDJ_CHECK(cutoff.switch_authority &&
               cutoff.switch_authority->pattern_id == PatternId{kPatternB});
    LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPattern});
    LMDJ_CHECK(f.coordinator.inspect().playing);
  }
}

void switch_applied_before_cutoff_is_retained() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  f.audio.queue_switch(2);
  f.audio.render(10);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternB});
  LMDJ_CHECK(!f.audio.engine.pending_pattern_id());
  LMDJ_CHECK(f.audio.pending_switch().has_value());
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto cutoff = cutoff_of(f);
  LMDJ_CHECK(cutoff.switch_outcome == SequenceSwitchOutcome::applied_before_cutoff);
  LMDJ_CHECK(cutoff.switch_applied_frame && *cutoff.switch_applied_frame == 2);
  LMDJ_CHECK(cutoff.switch_authority &&
             cutoff.switch_authority->pattern_id == PatternId{kPatternB});
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternB});
  LMDJ_CHECK(f.coordinator.inspect().playing);
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().admission &&
             journal.value().admission->applied_switches.size() == 1);
  LMDJ_CHECK(journal.value().admission->applied_switches.front().pattern_id ==
             PatternId{kPatternB});
  LMDJ_CHECK(journal.value().admission->applied_switches.front().frame == 2);
  LMDJ_CHECK(journal.value().pattern_id == PatternId{kPatternB});
  LMDJ_CHECK(journal.value().admission->segment_generation ==
             journal.value().admission->applied_switches.front().generation);
}

void switch_applied_before_cutoff_drains_source_prefix() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto opened = f.journals.read_active(f.bundle);
  LMDJ_CHECK(opened.has_value() && opened.value().admission &&
             opened.value().admission->admission_fence);
  const auto press_frame =
      opened.value().admission->admission_fence->effective_frame;
  LMDJ_CHECK(press_frame < 2);
  LMDJ_CHECK(f.coordinator
                 .admit({10, press_frame, {0, 1}, SequenceCandidateKind::press,
                         90, 1})
                 .value() == PatternAdmissionAdmit::retained);
  LMDJ_CHECK(f.coordinator
                 .admit({11, press_frame, {0, 1}, SequenceCandidateKind::release,
                         0, 1})
                 .value() == PatternAdmissionAdmit::retained);
  f.audio.queue_switch(2);
  f.audio.render(10);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternB});
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().pattern_id == PatternId{kPatternB});
  LMDJ_CHECK(journal.value().admission &&
             journal.value().admission->candidates.empty());
  const auto project = f.store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  LMDJ_CHECK(!project.value().patterns.at(PatternId{kPattern}).events.empty());
  LMDJ_CHECK(project.value().patterns.at(PatternId{kPatternB}).events.empty());
}

void switch_applied_before_cutoff_drains_target_segment() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto opened = f.journals.read_active(f.bundle);
  LMDJ_CHECK(opened.has_value() && opened.value().admission &&
             opened.value().admission->admission_fence);
  const auto press_frame =
      opened.value().admission->admission_fence->effective_frame;
  LMDJ_CHECK(press_frame < 2);
  LMDJ_CHECK(f.coordinator
                 .admit({10, press_frame, {0, 1}, SequenceCandidateKind::press,
                         90, 1})
                 .value() == PatternAdmissionAdmit::retained);
  LMDJ_CHECK(f.coordinator
                 .admit({11, press_frame, {0, 1}, SequenceCandidateKind::release,
                         0, 1})
                 .value() == PatternAdmissionAdmit::retained);
  f.audio.queue_switch(2);
  f.audio.render(10);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternB});
  LMDJ_CHECK(f.coordinator
                 .admit({12, 3, {0, 2}, SequenceCandidateKind::press, 95, 2})
                 .value() == PatternAdmissionAdmit::retained);
  LMDJ_CHECK(f.coordinator
                 .admit({13, 3, {0, 2}, SequenceCandidateKind::release, 0, 2})
                 .value() == PatternAdmissionAdmit::retained);
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().pattern_id == PatternId{kPatternB});
  LMDJ_CHECK(journal.value().admission &&
             journal.value().admission->candidates.empty());
  const auto project = f.store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  LMDJ_CHECK(!project.value().patterns.at(PatternId{kPattern}).events.empty());
  LMDJ_CHECK(!project.value().patterns.at(PatternId{kPatternB}).events.empty());
}

void refused_switch_publication_retries_without_a_ghost_applied() {
  Fixture f;
  const auto before = f.store.load(f.bundle);
  LMDJ_CHECK(before.has_value());
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  f.audio.queue_switch(100);
  const auto pending = f.audio.pending_switch();
  LMDJ_CHECK(pending.has_value());
  LMDJ_CHECK(pending->pattern_id == PatternId{kPatternB});
  // Real engine refusal: an ordinary publication cannot supersede a pending
  // publication for a different Pattern.
  const auto refused = f.audio.try_switch(kPatternC, 2);
  LMDJ_CHECK(refused.result == PatternPublishResult::publication_pending);
  // No ghost: the refused publication never became pending authority.
  const auto retained = f.audio.pending_switch();
  LMDJ_CHECK(retained.has_value());
  LMDJ_CHECK(retained->pattern_id == PatternId{kPatternB});
  LMDJ_CHECK(retained->generation == pending->generation);
  LMDJ_CHECK(retained->activation_frame == pending->activation_frame);
  // Retry with the exact pending authority replaces the pending switch once.
  const auto retried = f.audio.try_switch(kPatternC, 2, pending);
  LMDJ_CHECK(retried.result == PatternPublishResult::accepted);
  f.audio.render(10);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternC});
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto cutoff = cutoff_of(f);
  LMDJ_CHECK(cutoff.switch_outcome == SequenceSwitchOutcome::applied_before_cutoff);
  LMDJ_CHECK(cutoff.switch_applied_frame && *cutoff.switch_applied_frame == 2);
  LMDJ_CHECK(cutoff.switch_authority &&
             cutoff.switch_authority->pattern_id == PatternId{kPatternC});
  const auto journal = f.journals.read_active(f.bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().pattern_id == PatternId{kPatternC});
  // Exactly one applied switch is retained despite the refused first attempt.
  LMDJ_CHECK(journal.value().admission &&
             journal.value().admission->applied_switches.size() == 1);
  LMDJ_CHECK(journal.value().admission->applied_switches.front().pattern_id ==
             PatternId{kPatternC});
  LMDJ_CHECK(journal.value().admission->applied_switches.front().frame == 2);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternC});
  LMDJ_CHECK(f.coordinator.inspect().playing);
  const auto project = f.store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  LMDJ_CHECK(project.value().patterns.at(PatternId{kPatternC}).events.empty());
  LMDJ_CHECK(project.value().revision == before.value().revision);
}
}  // namespace

int main() {
  try {
    stopped_play_starts_without_a_journal();
    stopped_record_starts_playing_and_opens_admission();
    playing_play_stops_without_a_journal();
    playing_record_keeps_origin_and_opens_admission();
    recording_play_stops_scheduling_and_closes_admission();
    recording_record_commits_and_keeps_playing();
    duplicate_command_does_not_toggle_twice();
    earlier_command_does_not_toggle_after_a_later_one();
    wrong_session_or_project_is_invalid();
    recording_stop_retains_cutoff_before_ack();
    close_failure_after_ack_keeps_audio_and_retries();
    switch_at_or_after_cutoff_is_canceled();
    switch_applied_before_cutoff_is_retained();
    switch_applied_before_cutoff_drains_source_prefix();
    switch_applied_before_cutoff_drains_target_segment();
    refused_switch_publication_retries_without_a_ghost_applied();
    std::cout << "pattern transport tests: PASS (16 scenarios)\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
