#include <cstdio>
// The public controller header is the boundary that lets a Host drive Pattern
// transport without naming a Project I/O type; keep it the first include so a
// stray project_io dependency in it fails this compile.
#include <lmdj/facade/pattern_transport_controller.hpp>

#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <functional>
#include <initializer_list>
#include <iostream>
#include <iterator>
#include <memory>
#include <optional>
#include <string>
#include <unistd.h>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/facade/performance_replay.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "packages/application-facade/src/pattern_admission_controller.hpp"
#include "packages/application-facade/src/pattern_transport_controller.hpp"
#include "packages/application-facade/internal/lmdj/facade/pattern_transport_controller_factory.hpp"
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
      },
       // The overlay projection's recorded events land on pad 1; a prepared
       // view needs material for every slot an event names (#1513).
       ResolvedPad{
           PadSlotId{0, 1},
           lmdj::foundation::ArtifactRef{std::string(64, 'b'), "audio/wav", 256},
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
    ++submit_calls;
    if (before_submit) before_submit();
    const auto result = engine.submit_pattern_transport(command);
    if (result == lmdj::audio::PatternTransportSubmit::accepted) ++accepted_submits;
    return result;
  }
  std::optional<lmdj::audio::PatternTransportReceipt> inspect(
      std::uint64_t generation, std::uint64_t epoch) const override {
    return engine.inspect_pattern_transport_receipt(generation, epoch);
  }
  bool acknowledge(std::uint64_t generation, std::uint64_t epoch) override {
    ++acknowledge_calls;
    if (refuse_acknowledge) return false;
    return engine.acknowledge_pattern_transport_receipt(generation, epoch);
  }
  std::uint64_t pattern_generation() const override {
    return engine.pattern_telemetry().current_generation;
  }
  std::optional<lmdj::audio::PatternReplacementAuthority> pending_switch()
      const override {
    // Report the exact authority this port published, like queue_switch does:
    // the telemetry snapshot can diverge from the slot's stored triple, and a
    // fence naming the overlay must match the slot exactly.
    if (queued_overlay_ &&
        engine.pattern_telemetry().current_generation <
            queued_overlay_->generation) {
      return queued_overlay_;
    }
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
  bool receipt_bound_capability = false;
  bool unavailable_observation = false;
  bool refuse_acknowledge = false;
  unsigned submit_calls{}, accepted_submits{}, acknowledge_calls{};
  std::function<void()> before_submit;
  bool supports_receipt_bound_opening() const override {
    return receipt_bound_capability;
  }
  std::optional<lmdj::audio::PatternTransportObservation> observe_transport()
      const override {
    return unavailable_observation ? std::nullopt
                                  : engine.pattern_transport_observation();
  }
  // Retarget information for #1403: when false the port reports no current
  // Pattern (the defaulted-port semantics) and the coordinator keeps its
  // vendored binding.
  bool report_current_pattern = true;
  std::optional<PatternId> current_pattern() const override {
    if (!report_current_pattern) return std::nullopt;
    return engine.current_pattern_id();
  }
  // The overlay publication capability (#1513). Records what the coordinator
  // asked to publish so a test can assert on it; refuses when asked to.
  std::vector<std::pair<PatternId, std::vector<lmdj::domain::PatternEvent>>>
      published_overlays;
  bool refuse_overlay_publication = false;
  lmdj::foundation::Result<lmdj::audio::PatternPublication> publish_overlay(
      const PatternId& pattern,
      std::span<const lmdj::domain::PatternEvent> events) override {
    if (refuse_overlay_publication) {
      return lmdj::foundation::Result<lmdj::audio::PatternPublication>::failure(
          {lmdj::foundation::ErrorCode::bank_quota_exhausted,
           "test refusal"});
    }
    auto view = PreparedPatternView::from_snapshot_with_overlay(
        pattern_snapshot(pattern.value().c_str()), events);
    LMDJ_CHECK(view.has_value());
    const auto publication =
        engine.publish_pattern_view(std::move(view.value()));
    LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
    published_overlays.emplace_back(
        pattern, std::vector<lmdj::domain::PatternEvent>{events.begin(), events.end()});
    queued_overlay_ = lmdj::audio::PatternReplacementAuthority{
        publication.generation, pattern, publication.activation_frame};
    return lmdj::foundation::Result<lmdj::audio::PatternPublication>::success(
        publication);
  }
  bool cancel_overlay(
      const lmdj::audio::PatternReplacementAuthority& authority) override {
    if (!queued_overlay_ || queued_overlay_->generation != authority.generation ||
        !engine.cancel_pattern_publication(authority)) {
      return false;
    }
    queued_overlay_.reset();
    return true;
  }
  std::optional<lmdj::audio::PatternReplacementAuthority> queued_overlay_;
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

// Real storage delegation with one bounded failure at a durable Journal step.
// Unknown responses write the real bytes first; retries exercise the codec,
// not an invented success receipt or a fake in-memory Journal.
class JournalFaultStorage final : public lmdj::project_io::ProjectStoragePlatform {
 public:
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner{
      lmdj::project_io::make_default_project_storage_platform()};
  bool fail_begin = false, uncertain_begin = false, uncertain_append = false;
  std::string fail_append_kind;
  unsigned journal_creates{}, journal_appends{};
  std::function<void()> before_create;
  lmdj::foundation::Result<void> failure() const {
    return lmdj::foundation::Result<void>::failure(
        {lmdj::foundation::ErrorCode::io_error, "injected Journal IO failure"});
  }
  lmdj::foundation::Result<std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& p) override { return inner->acquire_writer(p); }
  lmdj::foundation::Result<void> ensure_directory(const std::filesystem::path& p) override {
    return inner->ensure_directory(p);
  }
  lmdj::foundation::Result<bool> exists(const std::filesystem::path& p) const override {
    return inner->exists(p);
  }
  lmdj::foundation::Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override {
    return inner->byte_length(p);
  }
  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& p) const override { return inner->read_complete(p); }
  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& p, std::span<const std::byte> bytes) override {
    if (p.filename() == "sequence.jsonl") {
      ++journal_creates;
      if (before_create) before_create();
      if (fail_begin) { fail_begin = false; return failure(); }
      if (uncertain_begin) {
        uncertain_begin = false;
        const auto written = inner->create_immutable(p, bytes);
        if (!written.has_value()) return written;
        return failure();
      }
    }
    return inner->create_immutable(p, bytes);
  }
  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& p, std::span<const std::byte> bytes) override {
    return inner->replace_complete(p, bytes);
  }
  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& p, std::uint64_t prefix,
      std::span<const std::byte> bytes) override {
    if (p.filename() == "sequence.jsonl") {
      if (!bytes.empty()) ++journal_appends;
      const std::string text(bytes.empty() ? "" : reinterpret_cast<const char*>(bytes.data()), bytes.size());
      if (!fail_append_kind.empty() && text.find(fail_append_kind) != std::string::npos) {
        fail_append_kind.clear();
        if (uncertain_append) {
          const auto written = inner->append_durable(p, prefix, bytes);
          if (!written.has_value()) return written;
        }
        return failure();
      }
    }
    return inner->append_durable(p, prefix, bytes);
  }
  lmdj::foundation::Result<void> remove(const std::filesystem::path& p) override {
    return inner->remove(p);
  }
  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& p) const override { return inner->list_names(p); }
  lmdj::foundation::Result<std::vector<std::string>> list_directories(
      const std::filesystem::path& p) const override { return inner->list_directories(p); }
  lmdj::foundation::Result<void> remove_tree(const std::filesystem::path& p) override {
    return inner->remove_tree(p);
  }
  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& p) const override { return inner->validate_managed_tree(p); }
};

struct Fixture {
  TempDirectory directory;
  std::filesystem::path bundle;
  SequenceSessionId session{uuid(1)};
  PatternId pattern{kPattern};
  EnginePort audio;
  std::unique_ptr<PatternTransportController> controller;

  Fixture(std::initializer_list<PatternId> extra_patterns = {},
          std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> platform = {})
      : bundle(directory.path() / "project.lmdj") {
    auto created = lmdj::domain::create_project(ProjectId{kProject}, 120);
    LMDJ_CHECK(created.has_value());
    auto state = std::move(created.value());
    state.patterns.emplace(pattern, lmdj::domain::Pattern{pattern, 1, {}});
    for (const auto& extra : extra_patterns) {
      state.patterns.emplace(extra, lmdj::domain::Pattern{extra, 1, {}});
    }
    lmdj::project_io::ProjectStore store(platform);
    LMDJ_CHECK(store.create(bundle, state).has_value());
    const PatternTransportControllerConfig config{
        bundle, session, ProjectId{kProject}, pattern, 7};
    controller = platform
        ? lmdj::facade::detail::PatternTransportControllerInternalFactory::make(
              audio, config, std::move(platform))
        : lmdj::facade::make_pattern_transport_controller(audio, config);
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
    // A queued-but-unlanded overlay makes a closing command busy; render past
    // its bar and let the cadence record the landed publication, exactly as a
    // live host's service tick would, before the command is submitted.
    for (unsigned step = 0; step < 100; ++step) {
      if (!audio.pending_switch().has_value() &&
          audio.engine.pattern_telemetry().pending_generation == 0) {
        break;
      }
      audio.render(9'600);
      static_cast<void>(controller->publish_overlay());
    }
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

constexpr auto kPendingPatternB = "00000000-0000-4000-8000-00000000000b";
constexpr auto kPendingPatternC = "00000000-0000-4000-8000-00000000000c";

void queue_claimed_b_and_queued_c(Fixture& f) {
  auto b = PreparedPatternView::from_snapshot(pattern_snapshot(kPendingPatternB));
  const auto pb = f.audio.engine.publish_pattern_view(std::move(b.value()), 96'000);
  LMDJ_CHECK(pb.result == PatternPublishResult::accepted && pb.activation_frame == 96'000);
  f.audio.render(1);
  auto c = PreparedPatternView::from_snapshot(pattern_snapshot(kPendingPatternC));
  const auto pc = f.audio.engine.publish_pattern_view(std::move(c.value()), 192'000,
      lmdj::audio::PatternReplacementAuthority{
          pb.generation, PatternId{kPendingPatternB}, pb.activation_frame});
  LMDJ_CHECK(pc.result == PatternPublishResult::accepted && pc.activation_frame == 192'000);
}

void capable_stop_cancels_both_pending_views_and_does_not_open_a_journal() {
  Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}});
  f.audio.receipt_bound_capability = true;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  queue_claimed_b_and_queued_c(f);
  const auto stop = f.make(7, 2, PatternTransportIntent::play_stop);
  LMDJ_CHECK(f.controller->request(stop) == PatternTransportSubmit::accepted);
  f.audio.render(1);
  const auto receipt = f.audio.engine.inspect_pattern_transport_receipt(7, 2);
  LMDJ_CHECK(receipt && receipt->switch_outcomes[0] && receipt->switch_outcomes[1]);
  LMDJ_CHECK(f.controller->continue_operation().has_value());
  LMDJ_CHECK(!f.controller->inspect().playing && !f.controller->inspect().recording);
  LMDJ_CHECK(!f.journal_exists());
  f.audio.render(192'000);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == f.pattern);
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().canceled_publications == 2);
  LMDJ_CHECK(f.audio.accepted_submits == 2 && f.audio.acknowledge_calls == 2);
  LMDJ_CHECK(f.controller->request(stop) == PatternTransportSubmit::replayed);
  LMDJ_CHECK(f.audio.accepted_submits == 2);
}

void receipt_bound_record_crossing_an_apply_records_and_persists_the_actual_pattern() {
  for (const bool both_applied : {false, true}) {
    Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}});
    f.audio.receipt_bound_capability = true;
    f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
    queue_claimed_b_and_queued_c(f);
    bool crossed = false;
    f.audio.before_submit = [&] {
      if (!crossed) {
        crossed = true;
        f.audio.render(both_applied ? 192'000 : 96'000);
      }
    };
    const auto record = f.make(7, 2, PatternTransportIntent::record);
    LMDJ_CHECK(f.controller->request(record) == PatternTransportSubmit::accepted);
    LMDJ_CHECK(!f.journal_exists() && !f.controller->inspect().recording);
    f.audio.render(1);
    const auto target = PatternId{both_applied ? kPendingPatternC : kPendingPatternB};
    const auto receipt = f.audio.engine.inspect_pattern_transport_receipt(7, 2);
    LMDJ_CHECK(receipt && receipt->pattern_id == target);
    LMDJ_CHECK(f.controller->continue_operation().has_value());
    const auto journal = f.read_journal();
    LMDJ_CHECK(journal.pattern_id == target && journal.admission && journal.admission->admission_fence);
    LMDJ_CHECK(journal.admission->preparation.publication_generation == receipt->pattern_generation);
    LMDJ_CHECK(journal.admission->admission_fence->pattern_id == target);
    LMDJ_CHECK(journal.admission->admission_fence->origin_frame == receipt->origin_frame);
    LMDJ_CHECK(journal.admission->admission_fence->switch_outcome ==
        lmdj::project_io::SequenceSwitchOutcome::none);
    LMDJ_CHECK(journal.admission->preparation.first_watermark == 10);
    LMDJ_CHECK(journal.admission && journal.admission->admission_fence);
    LMDJ_CHECK(journal.admission->preparation.fence_timeout_ms == 5000);
    LMDJ_CHECK(f.controller->inspect().recording && !f.controller->inspect().error);
    LMDJ_CHECK(f.controller->admit({10, receipt->effective_frame, {0, 1}, true, 90, 10})
        .value() == lmdj::facade::PatternAdmissionAdmit::retained);
    LMDJ_CHECK(f.controller->admit({11, receipt->effective_frame + 128, {0, 1}, false, 0, 10})
        .value() == lmdj::facade::PatternAdmissionAdmit::retained);
    f.audio.before_submit = {};
    f.settle(f.make(8, 3, PatternTransportIntent::record));
    LMDJ_CHECK(!f.journal_exists() && !f.controller->inspect().recording);
    lmdj::project_io::ProjectStore store;
    const auto reopened = store.load(f.bundle);
    LMDJ_CHECK(reopened.has_value() && reopened.value().revision == 1);
    LMDJ_CHECK(reopened.value().patterns.at(target).events.size() == 1);
    LMDJ_CHECK(reopened.value().patterns.at(target).events[0].velocity == 90);
    LMDJ_CHECK(reopened.value().patterns.at(f.pattern).events.empty());
    const auto other = PatternId{both_applied ? kPendingPatternB : kPendingPatternC};
    LMDJ_CHECK(reopened.value().patterns.at(other).events.empty());
    LMDJ_CHECK(f.audio.accepted_submits == 3);
  }
}

void capable_record_known_revision_or_foreign_owner_conflict_submits_nothing() {
  for (const bool foreign_owner : {false, true}) {
    auto platform = std::make_shared<JournalFaultStorage>();
    Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}}, platform);
    f.audio.receipt_bound_capability = true;
    f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
    // Both generations keep the current Pattern identity, so an unrelated
    // cross-target guard cannot hide a missing revision or owner preflight.
    auto first_view = PreparedPatternView::from_snapshot(pattern_snapshot());
    const auto first = f.audio.engine.publish_pattern_view(std::move(first_view.value()), 96'000);
    LMDJ_CHECK(first.result == PatternPublishResult::accepted);
    f.audio.render(1);
    auto second_view = PreparedPatternView::from_snapshot(pattern_snapshot());
    LMDJ_CHECK(f.audio.engine.publish_pattern_view(std::move(second_view.value()), 192'000,
        lmdj::audio::PatternReplacementAuthority{first.generation, f.pattern, first.activation_frame}).result ==
        PatternPublishResult::accepted);
    auto request = f.make(7, 2, PatternTransportIntent::record);
    if (foreign_owner) {
      lmdj::project_io::ProjectStore store(platform);
      lmdj::project_io::SequenceJournal journals(platform);
      const auto project = store.load(f.bundle);
      LMDJ_CHECK(journals.begin(f.bundle, SequenceSessionId{uuid(99)}, f.pattern, 1,
          lmdj::project_io::sequence_pattern_fingerprint(project.value().patterns.at(f.pattern)),
          project.value().revision).has_value());
    } else request.expected_revision = 1;
    const auto before_journal = foreign_owner
        ? std::optional{f.read_journal()} : std::nullopt;
    const auto before_creates = platform->journal_creates;
    const auto before_appends = platform->journal_appends;
    const auto before_submits = f.audio.submit_calls;
    LMDJ_CHECK(f.controller->request(request) == PatternTransportSubmit::refused);
    LMDJ_CHECK(f.audio.submit_calls == before_submits);
    LMDJ_CHECK(platform->journal_creates == before_creates && platform->journal_appends == before_appends);
    LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_publications == 2);
    LMDJ_CHECK(!f.controller->inspect().recording);
    if (foreign_owner) LMDJ_CHECK(f.read_journal() == *before_journal);
    else LMDJ_CHECK(!f.journal_exists());
  }
}

void receipt_bound_begin_failure_keeps_the_real_cutoff_until_same_command_retry() {
  auto platform = std::make_shared<JournalFaultStorage>();
  Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}}, platform);
  f.audio.receipt_bound_capability = true;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  queue_claimed_b_and_queued_c(f);
  const auto record = f.make(7, 2, PatternTransportIntent::record);
  LMDJ_CHECK(f.controller->request(record) == PatternTransportSubmit::accepted);
  platform->fail_begin = true;
  f.audio.render(1);
  const auto receipt = f.audio.engine.inspect_pattern_transport_receipt(7, 2);
  LMDJ_CHECK(receipt && receipt->switch_outcomes[0] && receipt->switch_outcomes[1]);
  LMDJ_CHECK(!f.controller->continue_operation().has_value());
  const auto failed = f.controller->inspect();
  LMDJ_CHECK(failed.phase == PatternTransportPhase::awaiting_audio && failed.error);
  LMDJ_CHECK(failed.error->code == lmdj::foundation::ErrorCode::io_error);
  LMDJ_CHECK(!failed.recording && failed.command_id == record.command_id);
  LMDJ_CHECK(f.audio.accepted_submits == 2 && f.audio.acknowledge_calls == 1);
  LMDJ_CHECK(!f.journal_exists());
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().canceled_publications == 2);
  LMDJ_CHECK(f.audio.engine.inspect_pattern_transport_receipt(7, 2)->effective_frame == receipt->effective_frame);
  LMDJ_CHECK(f.controller->request(record) == PatternTransportSubmit::replayed);
  f.audio.render(192'000);
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == f.pattern);
  LMDJ_CHECK(f.controller->continue_operation().has_value());
  LMDJ_CHECK(f.controller->inspect().recording && !f.controller->inspect().error);
  LMDJ_CHECK(f.read_journal().admission->admission_fence->effective_frame == receipt->effective_frame);
  LMDJ_CHECK(f.audio.accepted_submits == 2 && f.audio.acknowledge_calls == 2);
}

void receipt_bound_unknown_durable_writes_replay_without_duplicate_bytes() {
  for (const std::string step : {"begin", "admission-prepare", "admission-fence"}) {
    auto platform = std::make_shared<JournalFaultStorage>();
    Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}}, platform);
    f.audio.receipt_bound_capability = true;
    f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
    queue_claimed_b_and_queued_c(f);
    const auto record = f.make(7, 2, PatternTransportIntent::record);
    LMDJ_CHECK(f.controller->request(record) == PatternTransportSubmit::accepted);
    if (step == "begin") platform->uncertain_begin = true;
    else {
      platform->fail_append_kind = step;
      platform->uncertain_append = true;
    }
    f.audio.render(1);
    LMDJ_CHECK(!f.controller->continue_operation().has_value());
    const auto partial = f.read_journal();
    LMDJ_CHECK(partial.session_id == f.session && partial.pattern_id == f.pattern);
    LMDJ_CHECK(!f.controller->inspect().recording && f.audio.acknowledge_calls == 1);
    LMDJ_CHECK(f.controller->continue_operation().has_value());
    const auto complete = f.read_journal();
    LMDJ_CHECK(complete.admission && complete.admission->admission_fence);
    LMDJ_CHECK(complete.admission->preparation.identity.operation_id == record.command_id);
    LMDJ_CHECK(platform->journal_creates == 1 && platform->journal_appends == 2);
    LMDJ_CHECK(f.audio.accepted_submits == 2 && f.audio.acknowledge_calls == 2);
    LMDJ_CHECK(f.controller->request(record) == PatternTransportSubmit::replayed);
    LMDJ_CHECK(platform->journal_creates == 1 && platform->journal_appends == 2);
  }
}

void capable_record_unavailable_observation_is_busy_without_audio_or_journal_effects() {
  Fixture f;
  f.audio.receipt_bound_capability = true;
  f.audio.unavailable_observation = true;
  LMDJ_CHECK(f.controller->request(f.make(6, 1, PatternTransportIntent::record)) == PatternTransportSubmit::busy);
  LMDJ_CHECK(f.audio.submit_calls == 0 && !f.journal_exists());
  f.audio.unavailable_observation = false;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  LMDJ_CHECK(f.controller->inspect().recording);
}

void receipt_bound_opening_cannot_acknowledge_before_durable_admission() {
  auto platform = std::make_shared<JournalFaultStorage>();
  Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}}, platform);
  f.audio.receipt_bound_capability = true;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  queue_claimed_b_and_queued_c(f);
  const auto record = f.make(7, 2, PatternTransportIntent::record);
  LMDJ_CHECK(f.controller->request(record) == PatternTransportSubmit::accepted);
  platform->before_create = [&] {
    LMDJ_CHECK(f.audio.acknowledge_calls == 1);
    LMDJ_CHECK(!f.controller->inspect().recording);
    LMDJ_CHECK(f.audio.engine.inspect_pattern_transport_receipt(7, 2));
  };
  f.audio.render(1);
  LMDJ_CHECK(f.controller->continue_operation().has_value());
  LMDJ_CHECK(f.read_journal().admission->admission_fence);
  LMDJ_CHECK(f.audio.acknowledge_calls == 2 && f.controller->inspect().recording);
}

void receipt_bound_ack_failure_keeps_recording_false_and_the_durable_journal_receipt() {
  Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}});
  f.audio.receipt_bound_capability = true;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  queue_claimed_b_and_queued_c(f);
  const auto record = f.make(7, 2, PatternTransportIntent::record);
  LMDJ_CHECK(f.controller->request(record) == PatternTransportSubmit::accepted);
  f.audio.render(1);
  f.audio.refuse_acknowledge = true;
  LMDJ_CHECK(!f.controller->continue_operation().has_value());
  LMDJ_CHECK(f.controller->inspect().phase == PatternTransportPhase::error);
  LMDJ_CHECK(!f.controller->inspect().recording && f.controller->inspect().command_id == record.command_id);
  const auto journal = f.read_journal();
  LMDJ_CHECK(journal.admission && journal.admission->admission_fence);
  LMDJ_CHECK(journal.admission->preparation.identity.operation_id == record.command_id);
  LMDJ_CHECK(f.audio.engine.inspect_pattern_transport_receipt(7, 2));
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().canceled_publications == 2);
}

void receipt_bound_owner_retry_preserves_the_original_deadline_and_explicit_override() {
  using namespace lmdj;
  for (const std::uint32_t timeout : {5000U, 23U}) {
    Fixture f;
    project_io::ProjectStore store;
    project_io::SequenceJournal journals;
    const auto state = store.load(f.bundle);
    LMDJ_CHECK(journals.begin(f.bundle, f.session, f.pattern, 1,
        project_io::sequence_pattern_fingerprint(state.value().patterns.at(f.pattern)), 0).has_value());
    std::chrono::steady_clock::time_point now{};
    const auto start = now;
    facade::detail::PatternAdmissionOwner owner(journals, f.bundle, f.session, [&] { return now; });
    project_io::SequenceAdmissionPreparation preparation{
        {CommandId{uuid(7)}, 7, 2}, ProjectId{kProject}, f.pattern, 1, 10};
    LMDJ_CHECK(preparation.fence_timeout_ms == 5000);
    preparation.fence_timeout_ms = timeout;
    LMDJ_CHECK(owner.prepare(preparation, start).has_value());
    now += std::chrono::milliseconds{timeout - 1};
    LMDJ_CHECK(owner.prepare(preparation, start).has_value());
    const project_io::SequenceAdmissionFence fence{
        project_io::SequenceFenceKind::admission, CommandId{uuid(7)}, 2,
        100, 0, f.pattern, 1, 120, true, {}, project_io::SequenceSwitchOutcome::none, {}};
    LMDJ_CHECK(owner.activate(fence).has_value());
    LMDJ_CHECK(owner.admit({10, 100, {0, 1}, project_io::SequenceCandidateKind::press, 90, 10})
        .value() == facade::detail::PatternAdmissionAdmit::retained);
    now += std::chrono::milliseconds{1};
    LMDJ_CHECK(owner.admit({11, 101, {0, 1}, project_io::SequenceCandidateKind::release, 0, 10})
        .value() == facade::detail::PatternAdmissionAdmit::live_only);
    const auto expired = journals.read_active(f.bundle);
    LMDJ_CHECK(expired.value().admission->closure->reason == project_io::SequenceAdmissionCloseReason::deadline);
    LMDJ_CHECK(expired.value().admission->candidates.size() == 1);
  }
}

void receipt_bound_late_revision_or_foreign_journal_conflict_retains_receipt_and_owner() {
  for (const unsigned conflict : {0U, 1U, 2U}) {
    auto platform = std::make_shared<JournalFaultStorage>();
    Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}}, platform);
    f.audio.receipt_bound_capability = true;
    f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
    queue_claimed_b_and_queued_c(f);
    auto record = f.make(7, 2, PatternTransportIntent::record);
    record.expected_revision = 0;
    LMDJ_CHECK(f.controller->request(record) == PatternTransportSubmit::accepted);
    f.audio.render(1);
    const auto receipt = f.audio.engine.inspect_pattern_transport_receipt(7, 2);
    lmdj::project_io::ProjectStore store(platform);
    if (conflict == 0) {
      // A real unrelated authoring commit occurs after read-only preflight.
      LMDJ_CHECK(store.execute(f.bundle, lmdj::domain::EditPatternEvents{
          {CommandId{uuid(90)}, 0}, PatternId{kPendingPatternB}, {},
          {{{0, 1}, 0, 120, 80}}}).has_value());
    } else {
      lmdj::project_io::SequenceJournal journals(platform);
      const auto project = store.load(f.bundle);
      const auto target = conflict == 1 ? f.pattern : PatternId{kPendingPatternB};
      const auto owner = conflict == 1 ? SequenceSessionId{uuid(99)} : f.session;
      LMDJ_CHECK(journals.begin(f.bundle, owner, target, 1,
          lmdj::project_io::sequence_pattern_fingerprint(project.value().patterns.at(target)), 0).has_value());
    }
    const auto before_creates = platform->journal_creates;
    const auto before_appends = platform->journal_appends;
    LMDJ_CHECK(!f.controller->continue_operation().has_value());
    const auto status = f.controller->inspect();
    LMDJ_CHECK(status.phase == PatternTransportPhase::error && !status.recording && status.error);
    LMDJ_CHECK(status.command_id == record.command_id);
    LMDJ_CHECK(f.audio.acknowledge_calls == 1 && f.audio.accepted_submits == 2);
    LMDJ_CHECK(platform->journal_creates == before_creates && platform->journal_appends == before_appends);
    LMDJ_CHECK(f.audio.engine.inspect_pattern_transport_receipt(7, 2)->effective_frame == receipt->effective_frame);
    LMDJ_CHECK(f.audio.engine.pattern_telemetry().canceled_publications == 2);
    if (conflict == 0) {
      LMDJ_CHECK(status.error->code == lmdj::foundation::ErrorCode::revision_conflict);
      LMDJ_CHECK(!f.journal_exists() && store.load(f.bundle).value().revision == 1);
    } else {
      const auto journal = f.read_journal();
      LMDJ_CHECK(!journal.admission);
      LMDJ_CHECK(journal.session_id == (conflict == 1 ? SequenceSessionId{uuid(99)} : f.session));
      LMDJ_CHECK(journal.pattern_id == (conflict == 1 ? f.pattern : PatternId{kPendingPatternB}));
    }
  }
}

void preexisting_same_owner_journal_with_wrong_bars_or_fingerprint_refuses_before_cutoff() {
  for (const bool wrong_bars : {false, true}) {
    auto platform = std::make_shared<JournalFaultStorage>();
    Fixture f({}, platform);
    f.audio.receipt_bound_capability = true;
    f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
    auto view = PreparedPatternView::from_snapshot(pattern_snapshot());
    LMDJ_CHECK(f.audio.engine.publish_pattern_switch_view(std::move(view.value())).result == PatternPublishResult::accepted);
    f.audio.render(1);
    lmdj::project_io::ProjectStore store(platform);
    lmdj::project_io::SequenceJournal journals(platform);
    const auto project = store.load(f.bundle);
    const auto fingerprint = wrong_bars
        ? lmdj::project_io::sequence_pattern_fingerprint(project.value().patterns.at(f.pattern))
        : std::string(64, '0');
    LMDJ_CHECK(journals.begin(f.bundle, f.session, f.pattern, wrong_bars ? 2 : 1, fingerprint, 0).has_value());
    const auto submits = f.audio.submit_calls;
    const auto creates = platform->journal_creates;
    LMDJ_CHECK(f.controller->request(f.make(7, 2, PatternTransportIntent::record)) == PatternTransportSubmit::refused);
    LMDJ_CHECK(f.audio.submit_calls == submits && f.audio.acknowledge_calls == 1);
    LMDJ_CHECK(platform->journal_creates == creates && platform->journal_appends == 0);
    LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_publications == 1);
    LMDJ_CHECK(!f.read_journal().admission);
  }
}

void receipt_bound_preflight_preserves_existing_prefix_and_accepts_only_a_matching_empty_header() {
  for (const unsigned prefix : {0U, 1U, 2U}) {
    auto platform = std::make_shared<JournalFaultStorage>();
    Fixture f({}, platform);
    f.audio.receipt_bound_capability = true;
    f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
    auto view = PreparedPatternView::from_snapshot(pattern_snapshot());
    LMDJ_CHECK(f.audio.engine.publish_pattern_view(std::move(view.value()), 96'000).result == PatternPublishResult::accepted);
    f.audio.render(1);
    lmdj::project_io::ProjectStore store(platform);
    lmdj::project_io::SequenceJournal journals(platform);
    const auto state = store.load(f.bundle);
    LMDJ_CHECK(journals.begin(f.bundle, f.session, f.pattern, 1,
        lmdj::project_io::sequence_pattern_fingerprint(state.value().patterns.at(f.pattern)), 0,
        prefix == 2 ? std::optional{PadSlotId{0, 1}} : std::nullopt).has_value());
    if (prefix == 1) {
      const std::array events{lmdj::domain::PatternEvent{{0, 1}, 0, 120, 90}};
      LMDJ_CHECK(journals.append_tail(f.bundle, f.session, f.pattern, 0, 1, events).has_value());
    }
    const auto before = journals.read_active(f.bundle).value();
    const auto creates = platform->journal_creates;
    const auto appends = platform->journal_appends;
    const auto submits = f.audio.submit_calls;
    const auto request = f.make(7, 2, PatternTransportIntent::record);
    if (prefix == 0) {
      LMDJ_CHECK(f.controller->request(request) == PatternTransportSubmit::accepted);
      LMDJ_CHECK(journals.read_active(f.bundle).value() == before);
      f.audio.render(1);
      LMDJ_CHECK(f.controller->continue_operation().has_value());
      LMDJ_CHECK(f.controller->inspect().recording);
      LMDJ_CHECK(platform->journal_creates == creates && platform->journal_appends == appends + 2);
    } else {
      LMDJ_CHECK(f.controller->request(request) == PatternTransportSubmit::refused);
      LMDJ_CHECK(f.audio.submit_calls == submits && f.audio.acknowledge_calls == 1);
      LMDJ_CHECK(platform->journal_creates == creates && platform->journal_appends == appends);
      LMDJ_CHECK(journals.read_active(f.bundle).value() == before);
      LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_publications == 1);
      LMDJ_CHECK(!f.controller->inspect().recording);
    }
  }
}

struct InternalEnginePort final : lmdj::facade::detail::PatternTransportAudioPort {
  EnginePort& port;
  explicit InternalEnginePort(EnginePort& value) : port(value) {}
  lmdj::audio::PatternTransportSubmit submit(const lmdj::audio::PatternTransportCommand& c) override {
    return port.submit(c);
  }
  std::optional<lmdj::audio::PatternTransportReceipt> inspect(std::uint64_t g, std::uint64_t e) const override {
    return port.inspect(g, e);
  }
  bool acknowledge(std::uint64_t g, std::uint64_t e) override { return port.acknowledge(g, e); }
  std::uint64_t pattern_generation() const override { return port.pattern_generation(); }
  std::optional<lmdj::audio::PatternReplacementAuthority> pending_switch() const override { return port.pending_switch(); }
  bool supports_receipt_bound_opening() const override { return port.supports_receipt_bound_opening(); }
  std::optional<lmdj::audio::PatternTransportObservation> observe_transport() const override { return port.observe_transport(); }
};

void actual_request_receipt_delay_and_unknown_prepare_retry_share_one_deadline_clock() {
  using namespace lmdj;
  for (const bool already_expired : {false, true}) {
    auto platform = std::make_shared<JournalFaultStorage>();
    Fixture f({PatternId{kPendingPatternB}, PatternId{kPendingPatternC}}, platform);
    f.audio.receipt_bound_capability = true;
    InternalEnginePort audio(f.audio);
    project_io::ProjectStore store(platform);
    project_io::SequenceJournal journals(platform);
    std::chrono::steady_clock::time_point now{};
    facade::detail::PatternTransportCoordinator coordinator(audio, journals, store,
        f.bundle, f.session, ProjectId{kProject}, f.pattern, 7, [&] { return now; });
    LMDJ_CHECK(coordinator.request(f.make(6, 1, PatternTransportIntent::play_stop)) == PatternTransportSubmit::accepted);
    f.audio.render(1);
    LMDJ_CHECK(coordinator.continue_operation().has_value());
    queue_claimed_b_and_queued_c(f);
    const auto record = f.make(7, 2, PatternTransportIntent::record);
    LMDJ_CHECK(coordinator.request(record) == PatternTransportSubmit::accepted);
    f.audio.render(1);
    now += std::chrono::milliseconds{4998};
    platform->fail_append_kind = "admission-prepare";
    platform->uncertain_append = true;
    LMDJ_CHECK(!coordinator.continue_operation().has_value());
    LMDJ_CHECK(!coordinator.inspect().recording && f.audio.acknowledge_calls == 1);
    now += std::chrono::milliseconds{already_expired ? 1002 : 1};
    LMDJ_CHECK(coordinator.continue_operation().has_value());
    const auto journal = f.read_journal();
    LMDJ_CHECK(journal.admission->preparation.fence_timeout_ms == 5000);
    const auto frame = journal.admission->admission_fence->effective_frame;
    const auto press = coordinator.admit({10, frame, {0, 1}, project_io::SequenceCandidateKind::press, 90, 10});
    LMDJ_CHECK(press.has_value());
    LMDJ_CHECK(press.value() == (already_expired ? facade::detail::PatternAdmissionAdmit::live_only
                                             : facade::detail::PatternAdmissionAdmit::retained));
    if (!already_expired) {
      now += std::chrono::milliseconds{1};
      LMDJ_CHECK(coordinator.admit({11, frame + 1, {0, 1}, project_io::SequenceCandidateKind::release, 0, 10})
          .value() == facade::detail::PatternAdmissionAdmit::live_only);
    }
    LMDJ_CHECK(f.read_journal().admission->closure->reason == project_io::SequenceAdmissionCloseReason::deadline);
    LMDJ_CHECK(platform->journal_creates == 1 && platform->journal_appends == 3 + (already_expired ? 0 : 1));
    LMDJ_CHECK(f.audio.accepted_submits == 2 && f.audio.acknowledge_calls == 2);
  }
}

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
// #1958: a Host republication outside this coordinator (a Record-off
// completion) advances the engine's current Pattern generation past the last
// transport receipt. A Stop that names a switch queued after it must fence
// against the Pattern that plays now, or the engine refuses it every time.
void stop_names_a_switch_queued_after_an_outside_republication(
    bool receipt_bound_capability) {
  constexpr auto kPatternB = "00000000-0000-4000-8000-00000000000b";
  Fixture f({PatternId{kPatternB}});
  f.audio.receipt_bound_capability = receipt_bound_capability;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  LMDJ_CHECK(f.controller->inspect().playing);
  const auto acknowledged =
      f.audio.engine.pattern_telemetry().current_generation;

  // The Host republishes the playing Pattern; it lands at its Bar.
  auto again = PreparedPatternView::from_snapshot(pattern_snapshot());
  LMDJ_CHECK(again.has_value());
  LMDJ_CHECK(f.audio.engine.publish_pattern_view(std::move(again.value()))
                 .result == PatternPublishResult::accepted);
  for (unsigned step = 0;
       step < 100 && f.audio.engine.pattern_telemetry().pending_generation != 0;
       ++step) {
    f.audio.render(9'600);
  }
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_generation == 0);
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().current_generation !=
             acknowledged);

  // A switch to B is queued and claimed, its boundary still ahead.
  auto view = PreparedPatternView::from_snapshot(pattern_snapshot(kPatternB));
  LMDJ_CHECK(view.has_value());
  const auto switched =
      f.audio.engine.publish_pattern_view(std::move(view.value()));
  LMDJ_CHECK(switched.result == PatternPublishResult::accepted);
  f.audio.render(512);
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_generation ==
             switched.generation);

  // Stop names the switch against the current generation and is accepted;
  // the switch is voided at the cutoff and A stays current.
  LMDJ_CHECK(f.controller->request(f.make(7, 2,
                 PatternTransportIntent::play_stop)) ==
             PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(f.controller->continue_operation().has_value());
  const auto status = f.controller->inspect();
  LMDJ_CHECK(!status.playing);
  LMDJ_CHECK(!status.error.has_value());
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == f.pattern);
}

void stop_names_a_switch_queued_after_an_outside_republication() {
  // The stale last-receipt generation must not refuse Stop through either
  // the default legacy port or the coherent native observation capability.
  stop_names_a_switch_queued_after_an_outside_republication(false);
  stop_names_a_switch_queued_after_an_outside_republication(true);
}

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

// #1513: the Host publishes this projection so the pass just played is audible
// on the next one. Outside an open recording there is nothing to publish.
void overlay_projection_is_empty_outside_an_open_recording() {
  Fixture f;
  const auto before = f.controller->project_overlay();
  LMDJ_CHECK(before.has_value());
  LMDJ_CHECK(!before.value().has_value());
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const lmdj::facade::PatternTransportCandidate press{
      10, admission_frame(f.bundle), {0, 1}, true, 90, 10};
  LMDJ_CHECK(f.controller->admit(press).has_value());
  LMDJ_CHECK(f.controller->project_overlay().value().has_value());
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  const auto after = f.controller->project_overlay();
  LMDJ_CHECK(after.has_value());
  LMDJ_CHECK(!after.value().has_value());
}

// The load-bearing fact: what the Host hears mid-recording is what Record-off
// writes to Project Truth.
void overlay_projection_carries_the_events_the_close_will_commit() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
  f.audio.render(6'000);
  LMDJ_CHECK(f.controller->admit({11, frame + 6'000, {0, 1}, false, 0, 10})
                 .has_value());
  const auto projected = f.controller->project_overlay();
  LMDJ_CHECK(projected.has_value() && projected.value().has_value());
  LMDJ_CHECK(projected.value()->pattern_id == f.pattern);
  const auto heard = projected.value()->events;
  LMDJ_CHECK(heard.size() == 1);
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  lmdj::project_io::ProjectStore store;
  const auto project = store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  LMDJ_CHECK(project.value().patterns.at(f.pattern).events == heard);
}

void overlay_generation_advances_only_when_the_projection_changes() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  // A recording that has contributed nothing publishes nothing: generation
  // stays zero rather than costing the Host one empty publication.
  const auto empty = f.controller->project_overlay();
  LMDJ_CHECK(empty.has_value() && empty.value().has_value());
  LMDJ_CHECK(empty.value()->events.empty());
  LMDJ_CHECK(empty.value()->generation == 0);
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
  const auto pressed = f.controller->project_overlay();
  LMDJ_CHECK(pressed.has_value() && pressed.value().has_value());
  LMDJ_CHECK(pressed.value()->generation == 1);
  LMDJ_CHECK(pressed.value()->events.size() == 1);
  // Repeating the call changes nothing, so the Host does not republish.
  const auto repeated = f.controller->project_overlay();
  LMDJ_CHECK(repeated.has_value() && repeated.value().has_value());
  LMDJ_CHECK(repeated.value()->generation == 1);
  LMDJ_CHECK(repeated.value()->events == pressed.value()->events);
  // The release corrects the held press's duration, which is new content. The
  // frame delta must exceed one sixteenth, or the correction would land on the
  // same 240-tick default the held press already projects and nothing changes.
  f.audio.render(18'000);
  LMDJ_CHECK(f.controller->admit({11, frame + 18'000, {0, 1}, false, 0, 10})
                 .has_value());
  const auto released = f.controller->project_overlay();
  LMDJ_CHECK(released.has_value() && released.value().has_value());
  LMDJ_CHECK(released.value()->generation == 2);
  LMDJ_CHECK(released.value()->events != pressed.value()->events);
}

// The exactly-once guard: projecting is a read, so a Host that publishes an
// overlay on every input commits exactly what a Host that never projects does.
void overlay_projection_does_not_disturb_the_commit() {
  std::vector<lmdj::domain::PatternEvent> committed[2];
  for (int projecting = 0; projecting < 2; ++projecting) {
    Fixture f;
    f.settle(f.make(6, 1, PatternTransportIntent::record));
    const auto frame = admission_frame(f.bundle);
    LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
    if (projecting != 0) {
      for (int repeat = 0; repeat < 3; ++repeat) {
        LMDJ_CHECK(f.controller->project_overlay().has_value());
      }
    }
    f.audio.render(6'000);
    LMDJ_CHECK(f.controller->admit({11, frame + 6'000, {0, 1}, false, 0, 10})
                   .has_value());
    if (projecting != 0) {
      LMDJ_CHECK(f.controller->project_overlay().has_value());
    }
    f.settle(f.make(7, 2, PatternTransportIntent::record));
    lmdj::project_io::ProjectStore store;
    const auto project = store.load(f.bundle);
    LMDJ_CHECK(project.has_value());
    committed[projecting] = project.value().patterns.at(f.pattern).events;
    LMDJ_CHECK(!f.journal_exists());
  }
  LMDJ_CHECK(committed[0] == committed[1]);
  LMDJ_CHECK(committed[0].size() == 1);
}

// A reconciled switch can carry identical events onto a different Pattern. The
// generation names the overlay, so the Pattern identity must advance it too, or
// a Host that de-duplicates on generation keeps publishing the old Pattern's
// overlay onto the new one.
void overlay_generation_advances_when_the_projected_pattern_changes() {
  constexpr auto kPatternB = "00000000-0000-4000-8000-00000000000b";
  // One Bar of 4/4 at 120 BPM and 48 kHz. A candidate a whole number of Bars
  // after the transport origin lands on onset tick zero whichever Bar it is,
  // so both recordings below project the same event.
  constexpr std::uint64_t kBarFrames = 96'000;
  Fixture f({PatternId{kPatternB}});
  // The first Bar boundary at or after both the admission fence and the frames
  // already rendered. Taking the maximum keeps the render delta non-negative:
  // an unsigned subtraction the other way round renders for hours.
  const auto next_bar = [&](std::uint64_t origin, std::uint64_t fence) {
    const auto rendered = f.audio.engine.telemetry().rendered_frames;
    const auto floor = fence > rendered ? fence : rendered;
    return origin +
           ((floor - origin + kBarFrames - 1) / kBarFrames) * kBarFrames;
  };

  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto origin = f.controller->inspect().origin_frame;
  const auto fence_a =
      f.read_journal().admission->admission_fence->effective_frame;
  const auto bar_a = next_bar(origin, fence_a);
  f.audio.render(bar_a - f.audio.engine.telemetry().rendered_frames);
  LMDJ_CHECK(f.controller->admit({10, bar_a, {0, 1}, true, 90, 10}).has_value());
  const auto on_a = f.controller->project_overlay();
  LMDJ_CHECK(on_a.has_value() && on_a.value().has_value());
  LMDJ_CHECK(on_a.value()->pattern_id == f.pattern);
  const auto events = on_a.value()->events;
  const auto generation = on_a.value()->generation;
  f.settle(f.make(7, 2, PatternTransportIntent::record));

  auto view = PreparedPatternView::from_snapshot(pattern_snapshot(kPatternB));
  LMDJ_CHECK(view.has_value());
  LMDJ_CHECK(f.audio.engine.publish_pattern_view(std::move(view.value()))
                 .result == PatternPublishResult::accepted);
  for (unsigned step = 0;
       step < 100 &&
       f.audio.engine.pattern_telemetry().pending_generation != 0;
       ++step) {
    f.audio.render(9'600);
  }
  LMDJ_CHECK(f.audio.engine.current_pattern_id() == PatternId{kPatternB});

  f.settle(f.make(8, 3, PatternTransportIntent::record));
  const auto journal_b = f.read_journal();
  LMDJ_CHECK(journal_b.pattern_id == PatternId{kPatternB});
  const auto fence_b = journal_b.admission->admission_fence->effective_frame;
  const auto bar_b = next_bar(origin, fence_b);
  f.audio.render(bar_b - f.audio.engine.telemetry().rendered_frames);
  LMDJ_CHECK(f.controller->admit({12, bar_b, {0, 1}, true, 90, 12}).has_value());
  const auto on_b = f.controller->project_overlay();
  LMDJ_CHECK(on_b.has_value() && on_b.value().has_value());
  LMDJ_CHECK(on_b.value()->pattern_id == PatternId{kPatternB});
  // The point of the Bar alignment: identical content on a different Pattern.
  LMDJ_CHECK(on_b.value()->events == events);
  LMDJ_CHECK(on_b.value()->generation != generation);
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
  // The owner is gone: no terminal transfer will ever arrive. Recovery
  // finalizes the retained held press after its attack tail and replays it
  // into the Pattern instead of refusing forever (#1515).
  const auto applied = f.application.apply_sequence_recovery(
      {f.bundle, f.session, std::nullopt});
  LMDJ_CHECK(applied.has_value());
  lmdj::project_io::ProjectStore after(f.platform);
  const auto settled = after.load(f.bundle);
  LMDJ_CHECK(settled.has_value());
  LMDJ_CHECK(settled.value().patterns.at(f.pattern).events ==
      std::vector<lmdj::domain::PatternEvent>({{{0, 1}, 0, 240, 90}}));
  const auto listed_again = f.application.list_sequence_recovery({f.bundle});
  LMDJ_CHECK(listed_again.has_value());
  LMDJ_CHECK(listed_again.value().empty());
  // The journal was consumed by the recovery itself; an explicit discard has
  // nothing left to remove.
  LMDJ_CHECK(!f.application.discard_sequence_recovery(
                 {f.bundle, f.session, std::nullopt}).has_value());
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

// L2 (#1513): the coordinator publishes the open recording's overlay through
// the Host capability on the control cadence, records the publication
// generation in the journal, and the Record-off cutoff still validates — the
// exact refusal that motivated the coordinator-owned design.
void overlay_publication_records_and_the_cutoff_matches() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.audio.published_overlays.size() == 1);
  LMDJ_CHECK(f.audio.published_overlays[0].first == f.pattern);
  LMDJ_CHECK(f.audio.published_overlays[0].second.size() == 1);
  // The journal records the publication only after it lands at its Bar: the
  // cadence tick past the boundary writes the applied authority.
  for (unsigned step = 0;
       step < 100 && f.audio.engine.pattern_telemetry().pending_generation != 0;
       ++step) {
    f.audio.render(9'600);
  }
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  const auto journal_after = f.read_journal();
  const auto& admission = *journal_after.admission;
  LMDJ_CHECK(admission.published_generation > admission.segment_generation);
  // Repeated cadence ticks with no new content publish nothing more.
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.audio.published_overlays.size() == 1);
  // The release corrects the held press's duration, which is new content; the
  // second overlay publishes on the next tick and lands at the next Bar.
  f.audio.render(18'000);
  LMDJ_CHECK(f.controller->admit({11, frame + 18'000, {0, 1}, false, 0, 10})
                 .has_value());
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.audio.published_overlays.size() == 2);
  for (unsigned step = 0;
       step < 100 && f.audio.engine.pattern_telemetry().pending_generation != 0;
       ++step) {
    f.audio.render(9'600);
  }
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  // Record-off after the last overlay landed: the cutoff names the recorded
  // applied authority — the exact check that refused before the coordinator
  // owned the publication.
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  LMDJ_CHECK(!f.journal_exists());
  lmdj::project_io::ProjectStore store;
  const auto project = store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  LMDJ_CHECK(project.value().patterns.at(f.pattern).events.size() == 1);
}

// Closing can win the control cadence immediately after an overlay lands.
// The receipt must carry that applied authority through the durable cutoff
// even though no idle publish_overlay call recorded it first.
void closing_retains_an_overlay_that_landed_before_the_control_tick() {
  for (const auto intent : {PatternTransportIntent::record,
                            PatternTransportIntent::play_stop}) {
    Fixture f;
    f.settle(f.make(6, 1, PatternTransportIntent::record));
    const auto frame = admission_frame(f.bundle);
    LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
    LMDJ_CHECK(f.controller->publish_overlay().has_value());
    LMDJ_CHECK(f.audio.published_overlays.size() == 1);
    for (unsigned step = 0;
         step < 100 && f.audio.engine.pattern_telemetry().pending_generation != 0;
         ++step) {
      f.audio.render(9'600);
    }
    LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_generation == 0);
    LMDJ_CHECK(f.read_journal().admission->published_generation == 0);
    lmdj::project_io::ProjectStore store;
    const auto before = store.load(f.bundle);
    LMDJ_CHECK(before.has_value());
    // Deliberately no idle control tick between audio landing and close.
    LMDJ_CHECK(f.controller->request(f.make(7, 2, intent)) ==
               PatternTransportSubmit::accepted);
    f.audio.render(1);
    if (intent == PatternTransportIntent::record) {
      // Refuse the durable overlay append with a real foreign writer lease.
      // Repeated continuation must keep the applied marker and the receipt
      // until the same close can retry, rather than poison the engagement.
      const auto foreign = lmdj::project_io::make_default_project_storage_platform();
      auto lease = foreign->acquire_writer(f.bundle);
      LMDJ_CHECK(lease.has_value());
      for (unsigned attempt = 0; attempt < 2; ++attempt) {
        const auto refused = f.controller->continue_operation();
        LMDJ_CHECK(!refused.has_value());
        LMDJ_CHECK(refused.error().code == lmdj::foundation::ErrorCode::io_error);
        LMDJ_CHECK(f.controller->inspect().phase == PatternTransportPhase::awaiting_audio);
        LMDJ_CHECK(f.controller->inspect().recording);
      }
      lease.value().reset();
    }
    const auto closed = f.controller->continue_operation();
    if (!closed.has_value()) std::cerr << closed.error().message << '\n';
    LMDJ_CHECK(closed.has_value());
    LMDJ_CHECK(!f.journal_exists());
    LMDJ_CHECK(f.controller->inspect().playing ==
               (intent == PatternTransportIntent::record));
    LMDJ_CHECK(!f.controller->inspect().recording);
    const auto reopened = store.load(f.bundle);
    LMDJ_CHECK(reopened.has_value());
    LMDJ_CHECK(reopened.value().revision == before.value().revision + 1);
    const auto& events = reopened.value().patterns.at(f.pattern).events;
    LMDJ_CHECK(events.size() == 1);
    LMDJ_CHECK(events.front().slot.bank == 0 && events.front().slot.pad == 1);
    LMDJ_CHECK(events.front().velocity == 90);
  }
}

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  LMDJ_CHECK(input.good());
  return {std::istreambuf_iterator<char>(input), {}};
}

void write_bytes(const std::filesystem::path& path, const std::string& bytes) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  LMDJ_CHECK(output.good());
  output << bytes;
  LMDJ_CHECK(output.good());
}

// L2 (#1513): Record-off right after live input, while the overlay that input
// produced is still queued for its Bar, is accepted: the coordinator withdraws
// its own unlanded overlay instead of refusing the close, and the close
// commits the retained input exactly once.
void record_off_withdraws_an_unlanded_overlay_and_commits_once() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
  f.audio.render(18'000);
  LMDJ_CHECK(f.controller->admit({11, frame + 18'000, {0, 1}, false, 0, 10})
                 .has_value());
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.audio.published_overlays.size() == 1);
  // A render block lets the audio thread claim the queued publication, as a
  // live AudioWorklet does within one quantum; the Bar is still ahead.
  f.audio.render(256);
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_generation != 0);
  LMDJ_CHECK(f.controller->request(f.make(7, 2, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  LMDJ_CHECK(!f.controller->inspect().error.has_value());
  for (unsigned step = 0; step < 100 && f.journal_exists(); ++step) {
    f.audio.render(1);
    LMDJ_CHECK(f.controller->continue_operation().has_value());
  }
  LMDJ_CHECK(!f.journal_exists());
  LMDJ_CHECK(f.controller->inspect().phase == PatternTransportPhase::idle);
  lmdj::project_io::ProjectStore store;
  const auto project = store.load(f.bundle);
  LMDJ_CHECK(project.has_value());
  LMDJ_CHECK(project.value().patterns.at(f.pattern).events.size() == 1);
}

// L2 (#1513): a deferred command whose submission meets a real unnamed
// successor (not the withdrawn slot retiring) is refused after a bounded
// number of cadence ticks instead of waiting forever, and leaves nothing
// withdrawn behind for a later command's receipt.
void deferred_command_meeting_an_unnamed_successor_is_refused() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  f.audio.render(256);
  LMDJ_CHECK(f.controller->request(f.make(7, 2, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  auto view = PreparedPatternView::from_snapshot(pattern_snapshot());
  LMDJ_CHECK(view.has_value());
  LMDJ_CHECK(f.audio.engine.publish_pattern_view(std::move(view.value())).result ==
             PatternPublishResult::accepted);
  bool refused = false;
  for (unsigned step = 0; step < 200 && !refused; ++step) {
    refused = !f.controller->continue_operation().has_value();
  }
  LMDJ_CHECK(refused);
  LMDJ_CHECK(f.controller->inspect().phase == PatternTransportPhase::idle);
  LMDJ_CHECK(f.controller->inspect().error.has_value());
  LMDJ_CHECK(f.journal_exists());
}

// L2 (#1513): the cadence runs on every realtime service tick, so while the
// coordinator's own overlay is queued for its Bar a tick answers from the port
// alone. An unreadable journal proves no journal read happens in that window.
void queued_overlay_tick_reads_no_journal() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.audio.engine.pattern_telemetry().pending_generation != 0);
  const auto journal = f.bundle / "recovery/active/sequence.jsonl";
  const auto bytes = read_bytes(journal);
  write_bytes(journal, "not a journal\n");
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  write_bytes(journal, bytes);
  LMDJ_CHECK(f.audio.published_overlays.size() == 1);
}

// L2 (#1513): a Host refusal (pool full, seam unwired) is a capability fact,
// not an error: no error phase is entered, the input stays durable, and the
// SAME content is attempted only once. New retained input re-arms the
// publication and gets its own attempt once the capability recovers.
void refused_overlay_publication_settles_and_new_content_retries() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
  f.audio.refuse_overlay_publication = true;
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.controller->inspect().phase == PatternTransportPhase::idle);
  LMDJ_CHECK(f.controller->inspect().error == std::nullopt);
  LMDJ_CHECK(f.audio.published_overlays.empty());
  // Same content: settled by the refusal, no per-tick retry loop.
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.audio.published_overlays.empty());
  // New content re-arms the request; the capability has recovered.
  f.audio.refuse_overlay_publication = false;
  f.audio.render(18'000);
  LMDJ_CHECK(f.controller->admit({11, frame + 18'000, {0, 1}, false, 0, 10})
                 .has_value());
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.audio.published_overlays.size() == 1);
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  LMDJ_CHECK(!f.journal_exists());
}

// L2 (#1513): an overlay superseded by a different Pattern's publication
// before it lands never becomes current; the coordinator drops the marker
// without recording it, and the switch machinery owns the reconciliation the
// close then settles through.
void superseded_overlay_is_dropped_and_the_close_settles() {
  constexpr auto kPatternB = "00000000-0000-4000-8000-00000000000b";
  Fixture f({PatternId{kPatternB}});
  f.settle(f.make(6, 1, PatternTransportIntent::record));
  const auto frame = admission_frame(f.bundle);
  LMDJ_CHECK(f.controller->admit({10, frame, {0, 1}, true, 90, 10}).has_value());
  LMDJ_CHECK(f.controller->publish_overlay().has_value());
  LMDJ_CHECK(f.audio.published_overlays.size() == 1);
  // While the transport holds the engine, an outside publication of a
  // different Pattern is refused by the engine itself — the superseded-by-
  // switch window cannot be entered from the control lane, which is the
  // protection the busy guard and the exact-equality landing check rely on.
  auto view = PreparedPatternView::from_snapshot(pattern_snapshot(kPatternB));
  LMDJ_CHECK(view.has_value());
  LMDJ_CHECK(f.audio.engine.publish_pattern_view(std::move(view.value()))
                 .result == PatternPublishResult::publication_pending);
  f.settle(f.make(7, 2, PatternTransportIntent::record));
  LMDJ_CHECK(!f.journal_exists());
}

}  // namespace

int main() {
  try {
    capable_stop_cancels_both_pending_views_and_does_not_open_a_journal();
    receipt_bound_record_crossing_an_apply_records_and_persists_the_actual_pattern();
    capable_record_known_revision_or_foreign_owner_conflict_submits_nothing();
    receipt_bound_begin_failure_keeps_the_real_cutoff_until_same_command_retry();
    receipt_bound_unknown_durable_writes_replay_without_duplicate_bytes();
    capable_record_unavailable_observation_is_busy_without_audio_or_journal_effects();
    receipt_bound_opening_cannot_acknowledge_before_durable_admission();
    receipt_bound_ack_failure_keeps_recording_false_and_the_durable_journal_receipt();
    receipt_bound_late_revision_or_foreign_journal_conflict_retains_receipt_and_owner();
    preexisting_same_owner_journal_with_wrong_bars_or_fingerprint_refuses_before_cutoff();
    receipt_bound_preflight_preserves_existing_prefix_and_accepts_only_a_matching_empty_header();
    actual_request_receipt_delay_and_unknown_prepare_retry_share_one_deadline_clock();
    receipt_bound_owner_retry_preserves_the_original_deadline_and_explicit_override();
    stopped_record_plays_and_opens_admission();
    recording_record_off_closes_and_keeps_playing();
    playing_play_stops_without_a_journal();
    pending_operation_reports_busy_then_replays();
    stale_generation_is_rejected();
    deterministic_fence_mismatch_parks_the_engagement_in_error();
    record_after_an_applied_switch_retargets_the_bound_pattern();
    stop_names_a_switch_queued_after_an_outside_republication();
    applied_switch_mid_recording_settles_through_the_close_path();
    recording_press_and_release_are_retained();
    overlay_projection_is_empty_outside_an_open_recording();
    overlay_projection_carries_the_events_the_close_will_commit();
    overlay_generation_advances_only_when_the_projection_changes();
    overlay_projection_does_not_disturb_the_commit();
    overlay_generation_advances_when_the_projected_pattern_changes();
    overlay_publication_records_and_the_cutoff_matches();
    closing_retains_an_overlay_that_landed_before_the_control_tick();
    record_off_withdraws_an_unlanded_overlay_and_commits_once();
    deferred_command_meeting_an_unnamed_successor_is_refused();
    queued_overlay_tick_reads_no_journal();
    superseded_overlay_is_dropped_and_the_close_settles();
    refused_overlay_publication_settles_and_new_content_retries();
    pre_fence_candidate_is_live_only();
    admission_before_recording_fails();
    release_with_unknown_correlation_fabricates_no_press();
    application_built_controller_runs_under_the_held_writer_lease();
    controller_on_a_fresh_platform_reports_busy_then_recovers();
    known_owner_registration_protects_only_the_open_transport_journal();
    controller_destroyed_after_application_is_safe();
    owner_lost_transport_admission_is_sealed_and_listed();
    std::cout << "pattern transport controller tests: PASS (41 scenarios)\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
