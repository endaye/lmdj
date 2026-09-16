// The public controller header is the boundary that lets a Host drive Pattern
// transport without naming a Project I/O type; keep it the first include so a
// stray project_io dependency in it fails this compile.
#include <lmdj/facade/pattern_transport_controller.hpp>

#include <array>
#include <chrono>
#include <filesystem>
#include <initializer_list>
#include <iostream>
#include <memory>
#include <optional>
#include <unistd.h>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/facade/performance_replay.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>

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
using lmdj::facade::PatternTransportAudioPort;
using lmdj::facade::PatternTransportController;
using lmdj::facade::PatternTransportControllerConfig;
using lmdj::facade::PatternTransportIntent;
using lmdj::facade::PatternTransportPhase;
using lmdj::facade::PatternTransportRequest;
using lmdj::facade::PatternTransportSubmit;
using lmdj::foundation::CommandId;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;

constexpr auto kProject = "00000000-0000-4000-8000-000000000004";
constexpr auto kPattern = "00000000-0000-4000-8000-000000000002";

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
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-transport-controller-" + std::to_string(::getpid()) + "-" +
             std::to_string(std::chrono::steady_clock::now()
                                .time_since_epoch()
                                .count()));
    std::filesystem::create_directories(path_);
  }
  // An explicit root reuses an existing directory and leaves it in place, so
  // a second fixture can reopen the same workspace after the first is gone.
  explicit TempDirectory(std::filesystem::path existing)
      : path_(std::move(existing)), reusable_(true) {
    std::filesystem::create_directories(path_);
  }
  ~TempDirectory() {
    if (reusable_) {
      return;
    }
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }
  const std::filesystem::path& path() const { return path_; }
  TempDirectory(TempDirectory&&) = default;
  TempDirectory& operator=(TempDirectory&&) = default;
  TempDirectory(const TempDirectory&) = delete;
  TempDirectory& operator=(const TempDirectory&) = delete;
 private:
  std::filesystem::path path_;
  bool reusable_ = false;
};

// The Host-side port a Runtime Host implements over its own engine; this test
// double proves the public surface needs nothing beyond the engine.
struct EnginePort final : PatternTransportAudioPort {
  RealtimeEngine engine;
  EnginePort() {
    LMDJ_CHECK(engine.enable_pattern_transport(7).has_value());
    LMDJ_CHECK(engine.publish_sample_bank(
        PreparedSampleBank::empty(ProjectId{kProject}, 1)) ==
               PublishResult::accepted);
    auto view = PreparedPatternView::from_snapshot(pattern_snapshot());
    LMDJ_CHECK(view.has_value());
    const auto published = engine.publish_pattern_view(std::move(view.value()));
    LMDJ_CHECK(published.result == PatternPublishResult::accepted);
    LMDJ_CHECK(engine.start().has_value());
  }
  lmdj::audio::PatternTransportSubmit submit(
      const lmdj::audio::PatternTransportCommand& command) override {
    return engine.submit_pattern_transport(command);
  }
  std::optional<lmdj::audio::PatternTransportReceipt> inspect(
      std::uint64_t generation, std::uint64_t epoch) const override {
    return engine.inspect_pattern_transport_receipt(generation, epoch);
  }
  bool acknowledge(std::uint64_t generation, std::uint64_t epoch) override {
    return engine.acknowledge_pattern_transport_receipt(generation, epoch);
  }
  std::uint64_t pattern_generation() const override {
    return engine.pattern_telemetry().current_generation;
  }
  std::optional<lmdj::audio::PatternReplacementAuthority> pending_switch()
      const override {
    const auto pending = engine.pending_pattern_id();
    if (!pending) {
      // Once the queued switch is current the engine no longer reports it as
      // pending; re-report it so a fence crossing the application still names
      // the switch (same fallback as the internal-tier port).
      if (queued_switch_ &&
          engine.current_pattern_id() == queued_switch_->pattern_id &&
          engine.pattern_telemetry().current_generation ==
              queued_switch_->generation) {
        return queued_switch_;
      }
      return std::nullopt;
    }
    const auto telemetry = engine.pattern_telemetry();
    return lmdj::audio::PatternReplacementAuthority{
        telemetry.pending_generation, *pending,
        telemetry.pending_activation_frame};
  }
  // Retarget information for #1403: when false the port reports no current
  // Pattern (the defaulted-port semantics) and the coordinator keeps its
  // vendored binding.
  bool report_current_pattern = true;
  std::optional<PatternId> current_pattern() const override {
    if (!report_current_pattern) return std::nullopt;
    return engine.current_pattern_id();
  }
  std::optional<lmdj::audio::PatternReplacementAuthority> queued_switch_;
  void queue_switch(const char* pattern_id, std::uint64_t activation_frame) {
    auto view = PreparedPatternView::from_snapshot(pattern_snapshot(pattern_id));
    LMDJ_CHECK(view.has_value());
    const auto publication = engine.publish_pattern_view(
        std::move(view.value()), activation_frame);
    LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
    queued_switch_ = lmdj::audio::PatternReplacementAuthority{
        publication.generation, PatternId{pattern_id},
        publication.activation_frame};
  }
  void render(std::uint64_t frames) {
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

struct Fixture {
  TempDirectory directory;
  std::filesystem::path bundle;
  SequenceSessionId session{uuid(1)};
  PatternId pattern{kPattern};
  EnginePort audio;
  std::unique_ptr<PatternTransportController> controller;

  Fixture(std::initializer_list<PatternId> extra_patterns = {})
      : bundle(directory.path() / "project.lmdj") {
    auto created = lmdj::domain::create_project(ProjectId{kProject}, 120);
    LMDJ_CHECK(created.has_value());
    auto state = std::move(created.value());
    state.patterns.emplace(pattern, lmdj::domain::Pattern{pattern, 1, {}});
    for (const auto& extra : extra_patterns) {
      state.patterns.emplace(extra, lmdj::domain::Pattern{extra, 1, {}});
    }
    lmdj::project_io::ProjectStore store;
    LMDJ_CHECK(store.create(bundle, state).has_value());
    controller = lmdj::facade::make_pattern_transport_controller(
        audio,
        PatternTransportControllerConfig{
            bundle, session, ProjectId{kProject}, pattern, 7});
    LMDJ_CHECK(controller != nullptr);
  }

  bool journal_exists() const {
    lmdj::project_io::SequenceJournal reader;
    const auto journal = reader.read_active(bundle);
    if (journal.has_value()) return true;
    LMDJ_CHECK(journal.error().code == lmdj::foundation::ErrorCode::not_found);
    return false;
  }

  PatternTransportRequest make(unsigned command, std::uint64_t epoch,
                               PatternTransportIntent intent) const {
    return {session, ProjectId{kProject}, CommandId{uuid(command)}, 7, epoch,
            intent, {}};
  }

  void settle(const PatternTransportRequest& request) {
    LMDJ_CHECK(controller->request(request) == PatternTransportSubmit::accepted);
    audio.render(1);
    LMDJ_CHECK(controller->continue_operation().has_value());
  }

  lmdj::project_io::ActiveSequenceJournal read_journal() const {
    lmdj::project_io::SequenceJournal reader;
    const auto journal = reader.read_active(bundle);
    LMDJ_CHECK(journal.has_value());
    return journal.value();
  }
};

void stopped_record_plays_and_opens_admission() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto status = f.controller->inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(status.recording);
  LMDJ_CHECK(status.phase == PatternTransportPhase::idle);
  const auto journal = f.read_journal();
  LMDJ_CHECK(journal.admission.has_value());
  LMDJ_CHECK(journal.admission->admission_fence.has_value());
  LMDJ_CHECK(journal.admission->admission_fence->origin_frame ==
             status.origin_frame);
}

void recording_record_off_closes_and_keeps_playing() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto origin = f.controller->inspect().origin_frame;
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto status = f.controller->inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(!status.recording);
  LMDJ_CHECK(status.origin_frame == origin);
  // Record-off settles the admission completely; the journal is removed.
  LMDJ_CHECK(!f.journal_exists());
}

void playing_play_stops_without_a_journal() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  LMDJ_CHECK(f.controller->inspect().playing);
  f.settle(f.make(7, 2, PatternTransportIntent::play_stop));
  const auto status = f.controller->inspect();
  LMDJ_CHECK(!status.playing);
  LMDJ_CHECK(!status.recording);
  LMDJ_CHECK(!f.journal_exists());
}

void pending_operation_reports_busy_then_replays() {
  Fixture f;
  const auto first = f.make(6, 1, PatternTransportIntent::play_stop);
  LMDJ_CHECK(f.controller->request(first) == PatternTransportSubmit::accepted);
  LMDJ_CHECK(f.controller->inspect().phase ==
             PatternTransportPhase::awaiting_audio);
  // A conflicting mutation is busy while the receipt is unpublished; the same
  // command replays.
  LMDJ_CHECK(f.controller->request(f.make(7, 2, PatternTransportIntent::record)) ==
             PatternTransportSubmit::busy);
  LMDJ_CHECK(f.controller->request(first) == PatternTransportSubmit::replayed);
  // A continuation without a receipt is a short no-op, not a wait.
  LMDJ_CHECK(f.controller->continue_operation().has_value());
  LMDJ_CHECK(f.controller->inspect().phase ==
             PatternTransportPhase::awaiting_audio);
  f.audio.render(1);
  LMDJ_CHECK(f.controller->continue_operation().has_value());
  LMDJ_CHECK(f.controller->inspect().phase == PatternTransportPhase::idle);
  LMDJ_CHECK(f.controller->inspect().playing);
  LMDJ_CHECK(f.controller->request(first) == PatternTransportSubmit::replayed);
}

void deterministic_fence_mismatch_parks_the_engagement_in_error() {
  constexpr auto kPatternB = "00000000-0000-4000-8000-00000000000b";
  Fixture f;
  // A port without retarget information (the defaulted `current_pattern`)
  // keeps the pre-#1403 behavior: the coordinator cannot re-anchor, so the
  // deterministic fence mismatch still parks the engagement honestly.
  f.audio.report_current_pattern = false;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  f.settle(f.make(8, 3, PatternTransportIntent::play_stop));
  LMDJ_CHECK(!f.controller->inspect().playing);

  // A cross-identity republication behind the coordinator: the Engine applies
  // pattern B while the coordinator stays bound to pattern A.
  auto view = PreparedPatternView::from_snapshot(pattern_snapshot(kPatternB));
  LMDJ_CHECK(view.has_value());
  const auto published =
      f.audio.engine.publish_pattern_view(std::move(view.value()));
  LMDJ_CHECK(published.result == PatternPublishResult::accepted);
  for (unsigned step = 0;
       step < 100 &&
       f.audio.engine.pattern_telemetry().pending_generation != 0;
       ++step) {
    f.audio.render(9'600);
  }
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_generation == 0);

  // The Engine accepts the start against the generation that is current, but
  // the receipt names pattern B while the admission preparation named A: the
  // fence authority validation fails deterministically.
  LMDJ_CHECK(f.controller->request(f.make(9, 4, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  f.audio.render(1);
  const auto applied = f.controller->continue_operation();
  LMDJ_CHECK(!applied.has_value());
  const auto failed = f.controller->inspect();
  LMDJ_CHECK(failed.phase == PatternTransportPhase::error);
  LMDJ_CHECK(failed.error.has_value());

  // The same retained receipt is never retried: continuations are no-ops, the
  // parked error is stable, and new commands are refused, never busy.
  LMDJ_CHECK(f.controller->continue_operation().has_value());
  const auto parked = f.controller->inspect();
  LMDJ_CHECK(parked.phase == PatternTransportPhase::error);
  LMDJ_CHECK(parked.error.has_value());
  LMDJ_CHECK(parked.error->message == failed.error->message);
  LMDJ_CHECK(f.controller->request(f.make(10, 5, PatternTransportIntent::record)) ==
             PatternTransportSubmit::refused);
  LMDJ_CHECK(
      f.controller->request(f.make(11, 5, PatternTransportIntent::play_stop)) ==
      PatternTransportSubmit::refused);
}

void stale_generation_is_rejected() {
  Fixture f;
  auto stale = f.make(6, 1, PatternTransportIntent::play_stop);
  stale.runtime_generation = 8;
  LMDJ_CHECK(f.controller->request(stale) == PatternTransportSubmit::stale);
  LMDJ_CHECK(!f.controller->inspect().playing);
}

std::uint64_t admission_frame(const std::filesystem::path& bundle) {
  lmdj::project_io::SequenceJournal reader;
  const auto journal = reader.read_active(bundle);
  LMDJ_CHECK(journal.has_value());
  LMDJ_CHECK(journal.value().admission && journal.value().admission->admission_fence);
  return journal.value().admission->admission_fence->effective_frame;
}

// #1403: after a playing-state applied switch the engine's current Pattern is
// B while the coordinator's vendored binding is still A. The next Record
// retargets the binding before any journal or admission work, so the journal,
// the admission fence and the committed events all name B.
void record_after_an_applied_switch_retargets_the_bound_pattern() {
  constexpr auto kPatternB = "00000000-0000-4000-8000-00000000000b";
  Fixture f({PatternId{kPatternB}});
  // Record on A and settle the close; the transport keeps playing.
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  LMDJ_CHECK(f.controller->inspect().playing);
  LMDJ_CHECK(!f.controller->inspect().recording);

  // The switch publication applies at the Bar boundary while playing.
  auto view = PreparedPatternView::from_snapshot(pattern_snapshot(kPatternB));
  LMDJ_CHECK(view.has_value());
  const auto published =
      f.audio.engine.publish_pattern_view(std::move(view.value()));
  LMDJ_CHECK(published.result == PatternPublishResult::accepted);
  for (unsigned step = 0;
       step < 100 &&
       f.audio.engine.pattern_telemetry().pending_generation != 0;
       ++step) {
    f.audio.render(9'600);
  }
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_generation == 0);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternB});

  // Record retargets: the journal begins for B and the admission activates
  // against B instead of failing the fence authority deterministically.
  f.settle(f.make(8, 3, PatternTransportIntent::record));
  const auto recording = f.controller->inspect();
  LMDJ_CHECK(recording.playing);
  LMDJ_CHECK(recording.recording);
  LMDJ_CHECK(recording.phase == PatternTransportPhase::idle);
  LMDJ_CHECK(!recording.error.has_value());
  const auto journal = f.read_journal();
  LMDJ_CHECK(journal.pattern_id == PatternId{kPatternB});
  LMDJ_CHECK(journal.admission.has_value() &&
             journal.admission->admission_fence.has_value());
  LMDJ_CHECK(journal.admission->admission_fence->pattern_id ==
             PatternId{kPatternB});
  const auto frame = journal.admission->admission_fence->effective_frame;
  LMDJ_CHECK(f.controller
                 ->admit(lmdj::facade::PatternTransportCandidate{
                     10, frame, {0, 1}, true, 90, 10})
                 .value() == lmdj::facade::PatternAdmissionAdmit::retained);
  LMDJ_CHECK(f.controller
                 ->admit(lmdj::facade::PatternTransportCandidate{
                     11, frame, {0, 1}, false, 0, 10})
                 .value() == lmdj::facade::PatternAdmissionAdmit::retained);

  // Record-off commits the events to B in Project Truth; the engagement never
  // enters the error phase.
  f.settle(f.make(9, 4, PatternTransportIntent::record));
  const auto settled = f.controller->inspect();
  LMDJ_CHECK(settled.playing);
  LMDJ_CHECK(!settled.recording);
  LMDJ_CHECK(!settled.error.has_value());
  lmdj::project_io::ProjectStore store;
  const auto project = store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  const auto& events = project.value().patterns.at(PatternId{kPatternB}).events;
  LMDJ_CHECK(events.size() == 1);
  LMDJ_CHECK((events.front().slot == lmdj::domain::PadSlotId{0, 1}));
  LMDJ_CHECK(events.front().velocity == 90);
  LMDJ_CHECK(project.value().patterns.at(f.pattern).events.empty());
  LMDJ_CHECK(!f.journal_exists());
}

// The negative half of #1403: a switch that applies while a journal is active
// never retargets the binding mid-recording — the switch-spanning close
// machinery (retain_switch, reconcile, drains) settles it, exactly as the
// internal-tier switch scenarios pin.
void applied_switch_mid_recording_settles_through_the_close_path() {
  constexpr auto kPatternB = "00000000-0000-4000-8000-00000000000b";
  Fixture f({PatternId{kPatternB}});
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(frame < 2);
  LMDJ_CHECK(f.controller
                 ->admit(lmdj::facade::PatternTransportCandidate{
                     10, frame, {0, 1}, true, 90, 10})
                 .value() == lmdj::facade::PatternAdmissionAdmit::retained);
  LMDJ_CHECK(f.controller
                 ->admit(lmdj::facade::PatternTransportCandidate{
                     11, frame, {0, 1}, false, 0, 10})
                 .value() == lmdj::facade::PatternAdmissionAdmit::retained);

  // The switch applies while the journal is active; Record-off then fences
  // with the switch named and settles through the close path.
  f.audio.queue_switch(kPatternB, 2);
  f.audio.render(10);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternB});
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto settled = f.controller->inspect();
  LMDJ_CHECK(settled.playing);
  LMDJ_CHECK(!settled.recording);
  LMDJ_CHECK(settled.phase == PatternTransportPhase::idle);
  LMDJ_CHECK(!settled.error.has_value());
  // The retained journal is reconciled to the applied switch's Pattern; the
  // pre-switch prefix drained to A and no target-segment input existed.
  const auto journal = f.read_journal();
  LMDJ_CHECK(journal.pattern_id == PatternId{kPatternB});
  LMDJ_CHECK(journal.admission.has_value() &&
             journal.admission->applied_switches.size() == 1);
  LMDJ_CHECK(journal.admission->applied_switches.front().pattern_id ==
             PatternId{kPatternB});
  lmdj::project_io::ProjectStore store;
  const auto project = store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  const auto& source_events = project.value().patterns.at(f.pattern).events;
  LMDJ_CHECK(source_events.size() == 1);
  LMDJ_CHECK(source_events.front().velocity == 90);
  LMDJ_CHECK(project.value().patterns.at(PatternId{kPatternB}).events.empty());
}

void recording_press_and_release_are_retained() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  // Press carries its own watermark as correlation; the release repeats it to
  // close that exact owned press.
  const lmdj::facade::PatternTransportCandidate press{
      10, frame, {0, 1}, true, 90, 10};
  const lmdj::facade::PatternTransportCandidate release{
      11, frame, {0, 1}, false, 0, 10};
  const auto admitted_press = f.controller->admit(press);
  LMDJ_CHECK(admitted_press.has_value());
  LMDJ_CHECK(admitted_press.value() == lmdj::facade::PatternAdmissionAdmit::retained);
  const auto admitted_release = f.controller->admit(release);
  LMDJ_CHECK(admitted_release.has_value());
  LMDJ_CHECK(admitted_release.value() == lmdj::facade::PatternAdmissionAdmit::retained);
  const auto journal = f.read_journal();
  LMDJ_CHECK(journal.admission->candidates.size() == 2);
  const auto& stored_press = journal.admission->candidates.front();
  LMDJ_CHECK(stored_press.watermark == 10);
  LMDJ_CHECK(stored_press.runtime_frame == frame);
  LMDJ_CHECK((stored_press.slot == lmdj::domain::PadSlotId{0, 1}));
  LMDJ_CHECK(stored_press.kind ==
             lmdj::project_io::SequenceCandidateKind::press);
  LMDJ_CHECK(stored_press.velocity == 90);
  LMDJ_CHECK(stored_press.press_sequence == 10);
  const auto& stored_release = journal.admission->candidates.back();
  LMDJ_CHECK(stored_release.kind ==
             lmdj::project_io::SequenceCandidateKind::release);
  LMDJ_CHECK(stored_release.press_sequence == 10);
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  // Record-off settles: the retained prefix is drained and committed to Project
  // Truth exactly once, the admission completes, and the settled journal is
  // removed.
  lmdj::project_io::ProjectStore store;
  const auto project = store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  const auto& events = project.value().patterns.at(f.pattern).events;
  LMDJ_CHECK(events.size() == 1);
  LMDJ_CHECK((events.front().slot == lmdj::domain::PadSlotId{0, 1}));
  LMDJ_CHECK(events.front().velocity == 90);
  LMDJ_CHECK(!f.journal_exists());
}

void pre_fence_candidate_is_live_only() {
  Fixture f;
  // A playing Record fences at the current frame, so a candidate stamped
  // before it is observable as pre-fence input.
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  f.audio.render(64);
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(frame > 0);
  const lmdj::facade::PatternTransportCandidate early{
      10, frame - 1, {0, 1}, true, 90, 10};
  const auto admitted = f.controller->admit(early);
  LMDJ_CHECK(admitted.has_value());
  LMDJ_CHECK(admitted.value() == lmdj::facade::PatternAdmissionAdmit::live_only);
  const auto journal = f.read_journal();
  LMDJ_CHECK(journal.admission->candidates.empty());
}

void admission_before_recording_fails() {
  Fixture f;
  const lmdj::facade::PatternTransportCandidate press{10, 0, {0, 1}, true, 90, 10};
  LMDJ_CHECK(!f.controller->admit(press).has_value());
  LMDJ_CHECK(!f.journal_exists());
}

void release_with_unknown_correlation_fabricates_no_press() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  const lmdj::facade::PatternTransportCandidate press{
      10, frame, {0, 1}, true, 90, 10};
  // A release naming a correlation this session never pressed. Admission
  // retains it as a candidate; correlation matching belongs to conversion,
  // which must never invent the missing press's release.
  const lmdj::facade::PatternTransportCandidate orphan_release{
      11, frame, {0, 1}, false, 0, 77};
  LMDJ_CHECK(f.controller->admit(press).has_value());
  const auto admitted = f.controller->admit(orphan_release);
  LMDJ_CHECK(admitted.has_value());
  LMDJ_CHECK(admitted.value() == lmdj::facade::PatternAdmissionAdmit::retained);
  const auto journal = f.read_journal();
  LMDJ_CHECK(journal.admission->candidates.size() == 2);
  LMDJ_CHECK(journal.admission->candidates.back().press_sequence == 77);
  // Closing drains and converts the frozen prefix: the orphan release matches
  // no owned press, so exactly the press is committed to Project Truth, and the
  // settled journal is removed. Correlation matching is pinned by the T1 suite.
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  lmdj::project_io::ProjectStore store;
  const auto project = store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  const auto& events = project.value().patterns.at(f.pattern).events;
  LMDJ_CHECK(events.size() == 1);
  LMDJ_CHECK((events.front().slot == lmdj::domain::PadSlotId{0, 1}));
  LMDJ_CHECK(events.front().velocity == 90);
  LMDJ_CHECK(!f.journal_exists());
}

// The real Host shape: one Application, one storage platform instance, and a
// Host-held Project writer lease beside the transport controller.
struct ApplicationFixture {
  explicit ApplicationFixture(
      std::filesystem::path root = std::filesystem::path{})
      : directory(root.empty() ? TempDirectory()
                               : TempDirectory(std::move(root))),
        bundle(directory.path() / "project.lmdj"),
        application(app_config(directory.path(), platform)) {
    auto created = lmdj::domain::create_project(ProjectId{kProject}, 120);
    LMDJ_CHECK(created.has_value());
    auto state = std::move(created.value());
    state.patterns.emplace(pattern, lmdj::domain::Pattern{pattern, 1, {}});
    lmdj::project_io::ProjectStore store(platform);
    LMDJ_CHECK(store.create(bundle, state).has_value());
  }

  TempDirectory directory;
  std::filesystem::path bundle;
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> platform{
      lmdj::project_io::make_default_project_storage_platform()};
  SequenceSessionId session{uuid(1)};
  PatternId pattern{kPattern};
  EnginePort audio;
  lmdj::facade::Application application;

  static lmdj::facade::ApplicationConfig app_config(
      const std::filesystem::path& root,
      std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> storage) {
    return lmdj::facade::ApplicationConfig{
        root,
        nullptr,
        {},
        {},
        lmdj::audio::RuntimePreparationLimits{
            1'048'576, 240'000, 67'108'864, 134'217'728},
        std::move(storage),
        nullptr,
        nullptr,
        nullptr,
        lmdj::facade::make_unavailable_performance_replay_controller(),
    };
  }

  PatternTransportRequest make(unsigned command, std::uint64_t epoch,
                               PatternTransportIntent intent) const {
    return {session, ProjectId{kProject}, CommandId{uuid(command)}, 7, epoch,
            intent, {}};
  }

  bool journal_exists() const {
    lmdj::project_io::SequenceJournal reader;
    const auto journal = reader.read_active(bundle);
    if (journal.has_value()) return true;
    LMDJ_CHECK(journal.error().code == lmdj::foundation::ErrorCode::not_found);
    return false;
  }
};

void application_built_controller_runs_under_the_held_writer_lease() {
  ApplicationFixture f;
  auto lease = f.application.acquire_project_writer(f.bundle);
  LMDJ_CHECK(lease.has_value());
  auto controller = f.application.make_pattern_transport_controller(
      f.audio,
      PatternTransportControllerConfig{
          f.bundle, f.session, ProjectId{kProject}, f.pattern, 7});
  LMDJ_CHECK(controller != nullptr);
  // Record, admit and close while the Host keeps its writer lease: the
  // controller's journal writes share the Application's platform instance, so
  // the lease never reports the bundle busy.
  LMDJ_CHECK(controller->request(f.make(6, 1, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(controller->continue_operation().has_value());
  const auto status = controller->inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(status.recording);
  const auto frame = admission_frame(f.bundle);
  const auto admitted = controller->admit(
      lmdj::facade::PatternTransportCandidate{10, frame, {0, 1}, true, 90, 10});
  LMDJ_CHECK(admitted.has_value());
  LMDJ_CHECK(admitted.value() == lmdj::facade::PatternAdmissionAdmit::retained);
  LMDJ_CHECK(controller->request(f.make(7, 2, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(controller->continue_operation().has_value());
  LMDJ_CHECK(!controller->inspect().recording);
  // The lazy begin, admission, settlement flush and journal removal all ran
  // under the Host-held lease through the shared platform instance.
  lmdj::project_io::ProjectStore store(f.platform);
  const auto project = store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  const auto& events = project.value().patterns.at(f.pattern).events;
  LMDJ_CHECK(events.size() == 1);
  LMDJ_CHECK(events.front().velocity == 90);
  lmdj::project_io::SequenceJournal reader;
  const auto journal = reader.read_active(f.bundle);
  LMDJ_CHECK(!journal.has_value());
  LMDJ_CHECK(journal.error().code == lmdj::foundation::ErrorCode::not_found);
}

void controller_on_a_fresh_platform_reports_busy_then_recovers() {
  Fixture f;
  // An independent platform instance holding the writer lease locks the
  // bundle's flock against the controller's own fresh default instance.
  const auto foreign = lmdj::project_io::make_default_project_storage_platform();
  auto lease = foreign->acquire_writer(f.bundle);
  LMDJ_CHECK(lease.has_value());
  const auto request = f.make(6, 1, PatternTransportIntent::record);
  LMDJ_CHECK(f.controller->request(request) == PatternTransportSubmit::refused);
  const auto failed = f.controller->inspect();
  LMDJ_CHECK(failed.error.has_value());
  LMDJ_CHECK(failed.error->code == lmdj::foundation::ErrorCode::io_error);
  LMDJ_CHECK(failed.error->details.at("storage_condition") ==
             lmdj::project_io::kStorageConditionProjectBusy);
  LMDJ_CHECK(!failed.playing);
  LMDJ_CHECK(!failed.recording);
  // Releasing the foreign lease unblocks the exact same command identity.
  lease.value().reset();
  f.settle(request);
  const auto status = f.controller->inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(status.recording);
}

void known_owner_registration_protects_only_the_open_transport_journal() {
  ApplicationFixture f;
  auto lease = f.application.acquire_project_writer(f.bundle);
  LMDJ_CHECK(lease.has_value());
  const SequenceSessionId second_session{uuid(9)};
  auto first = f.application.make_pattern_transport_controller(
      f.audio,
      PatternTransportControllerConfig{
          f.bundle, f.session, ProjectId{kProject}, f.pattern, 7});
  auto second = f.application.make_pattern_transport_controller(
      f.audio,
      PatternTransportControllerConfig{
          f.bundle, second_session, ProjectId{kProject}, f.pattern, 8});
  const lmdj::facade::SequenceBeginRequest legacy_begin{
      f.bundle, SequenceSessionId{uuid(10)}, f.pattern, 0, 0};
  const auto assign = [&f] {
    return f.application.command({
        {"operation", "pad.assign"},
        {"project_path", f.bundle.generic_string()},
        {"command_id", uuid(30)},
        {"expected_revision", 0},
        {"slot", {{"bank", 0}, {"pad", 1}}},
        {"asset_id", nullptr},
    });
  };
  // Registration alone does not block authoring: no transport journal is open.
  LMDJ_CHECK(assign().at("ok").get<bool>());

  LMDJ_CHECK(first->request(f.make(6, 1, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(first->continue_operation().has_value());
  LMDJ_CHECK(first->inspect().recording);
  // With the transport journal open, legacy begin and Sample-class authoring
  // keep their busy guard and the journal is never sealed as owner loss.
  const auto blocked_begin = f.application.begin_sequence(legacy_begin);
  LMDJ_CHECK(!blocked_begin.has_value());
  LMDJ_CHECK(blocked_begin.error().details.at("reason") ==
             "sequence_session_active");
  // Destroying the second registration keeps the first journal protected.
  second.reset();
  const auto blocked_assign = f.application.command({
      {"operation", "pad.assign"},
      {"project_path", f.bundle.generic_string()},
      {"command_id", uuid(31)},
      {"expected_revision", 1},
      {"slot", {{"bank", 0}, {"pad", 1}}},
      {"asset_id", nullptr},
  });
  LMDJ_CHECK(!blocked_assign.at("ok").get<bool>());
  LMDJ_CHECK(blocked_assign.at("error").at("details").at("reason") ==
             "sequence_session_active");
  LMDJ_CHECK(first->request(f.make(7, 2, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(first->continue_operation().has_value());
  LMDJ_CHECK(!first->inspect().recording);
  // After settlement removes the journal, authoring is admitted again even
  // while the controller is still vended.
  lmdj::project_io::ProjectStore store(f.platform);
  const auto current = store.load(f.bundle);
  LMDJ_CHECK(current.has_value());
  LMDJ_CHECK(f.application
                 .begin_sequence({f.bundle, SequenceSessionId{uuid(10)},
                                  f.pattern, current.value().revision, 0})
                 .has_value());
}

void owner_lost_transport_admission_is_sealed_and_listed() {
  ApplicationFixture f;
  auto lease = f.application.acquire_project_writer(f.bundle);
  LMDJ_CHECK(lease.has_value());
  auto controller = f.application.make_pattern_transport_controller(
      f.audio,
      PatternTransportControllerConfig{
          f.bundle, f.session, ProjectId{kProject}, f.pattern, 7});
  LMDJ_CHECK(controller->request(f.make(6, 1, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(controller->continue_operation().has_value());
  LMDJ_CHECK(controller->inspect().recording);
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(controller->admit(
      lmdj::facade::PatternTransportCandidate{10, frame, {0, 1}, true, 90, 10})
                 .has_value());

  // A listing while the owner is live never seals its journal.
  const auto live = f.application.list_sequence_recovery({f.bundle});
  LMDJ_CHECK(live.has_value());
  LMDJ_CHECK(live.value().empty());
  LMDJ_CHECK(f.journal_exists());

  controller.reset();
  const auto listed = f.application.list_sequence_recovery({f.bundle});
  LMDJ_CHECK(listed.has_value());
  LMDJ_CHECK(listed.value().size() == 1);
  LMDJ_CHECK(listed.value().front().session_id == f.session);
  LMDJ_CHECK(listed.value().front().reason == "owner_lost");
  // The retained candidate survives the seal; the unresolved admission is a
  // recoverable refusal, not a guess.
  const auto applied = f.application.apply_sequence_recovery(
      {f.bundle, f.session, std::nullopt});
  LMDJ_CHECK(!applied.has_value());
  LMDJ_CHECK(applied.error().details.at("reason") ==
             "sequence_admission_unresolved");
  const auto listed_again = f.application.list_sequence_recovery({f.bundle});
  LMDJ_CHECK(listed_again.has_value());
  LMDJ_CHECK(listed_again.value().size() == 1);
  LMDJ_CHECK(f.application.discard_sequence_recovery({f.bundle, f.session, std::nullopt})
                 .has_value());
  const auto empty = f.application.list_sequence_recovery({f.bundle});
  LMDJ_CHECK(empty.has_value());
  LMDJ_CHECK(empty.value().empty());
}

void controller_destroyed_after_application_is_safe() {
  const auto directory =
      std::filesystem::temp_directory_path() /
      ("lmdj-transport-lifetime-" +
       std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::create_directories(directory);
  std::unique_ptr<lmdj::facade::PatternTransportController> controller;
  {
    ApplicationFixture f;
    controller = f.application.make_pattern_transport_controller(
        f.audio,
        PatternTransportControllerConfig{
            f.bundle, f.session, ProjectId{kProject}, f.pattern, 7});
    LMDJ_CHECK(controller != nullptr);
  }
  // Far side: the retired owner leaves no registration behind, so a fresh
  // Application over the same workspace admits legacy authoring; the later
  // controller destruction observes the expired owner and stops cleanly.
  {
    ApplicationFixture reopened(directory);
    LMDJ_CHECK(reopened.application
                   .begin_sequence({reopened.bundle,
                                    SequenceSessionId{uuid(11)}, reopened.pattern,
                                    0, 0})
                   .has_value());
  }
  controller.reset();
  std::error_code ignored;
  std::filesystem::remove_all(directory, ignored);
}

}  // namespace

int main() {
  try {
    stopped_record_plays_and_opens_admission();
    recording_record_off_closes_and_keeps_playing();
    playing_play_stops_without_a_journal();
    pending_operation_reports_busy_then_replays();
    stale_generation_is_rejected();
    deterministic_fence_mismatch_parks_the_engagement_in_error();
    record_after_an_applied_switch_retargets_the_bound_pattern();
    applied_switch_mid_recording_settles_through_the_close_path();
    recording_press_and_release_are_retained();
    pre_fence_candidate_is_live_only();
    admission_before_recording_fails();
    release_with_unknown_correlation_fabricates_no_press();
    application_built_controller_runs_under_the_held_writer_lease();
    controller_on_a_fresh_platform_reports_busy_then_recovers();
    known_owner_registration_protects_only_the_open_transport_journal();
    controller_destroyed_after_application_is_safe();
    owner_lost_transport_admission_is_sealed_and_listed();
    std::cout << "pattern transport controller tests: PASS (17 scenarios)\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
