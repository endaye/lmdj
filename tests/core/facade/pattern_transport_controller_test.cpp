// The public controller header is the boundary that lets a Host drive Pattern
// transport without naming a Project I/O type; keep it the first include so a
// stray project_io dependency in it fails this compile.
#include <lmdj/facade/pattern_transport_controller.hpp>

#include <array>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <memory>
#include <optional>
#include <unistd.h>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

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

RuntimeSnapshot pattern_snapshot() {
  auto sample = std::make_shared<const lmdj::cooker::PcmSample>(
      lmdj::cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(128, 1)});
  return RuntimeSnapshot{
      ProjectId{kProject}, PatternId{kPattern}, 1, 120, 1,
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
  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }
  const std::filesystem::path& path() const { return path_; }
 private:
  std::filesystem::path path_;
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
    if (!pending) return std::nullopt;
    const auto telemetry = engine.pattern_telemetry();
    return lmdj::audio::PatternReplacementAuthority{
        telemetry.pending_generation, *pending,
        telemetry.pending_activation_frame};
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

  Fixture() : bundle(directory.path() / "project.lmdj") {
    auto created = lmdj::domain::create_project(ProjectId{kProject}, 120);
    LMDJ_CHECK(created.has_value());
    auto state = std::move(created.value());
    state.patterns.emplace(pattern, lmdj::domain::Pattern{pattern, 1, {}});
    lmdj::project_io::ProjectStore store;
    LMDJ_CHECK(store.create(bundle, state).has_value());
    // The journal lifecycle stays with the existing Sequence surface; the
    // controller rides on the already-open journal, as in the coordinator.
    lmdj::project_io::SequenceJournal journals;
    LMDJ_CHECK(journals
                   .begin(bundle, session, pattern, 1,
                          lmdj::project_io::sequence_pattern_fingerprint(
                              state.patterns.at(pattern)),
                          0)
                   .has_value());
    controller = lmdj::facade::make_pattern_transport_controller(
        audio,
        PatternTransportControllerConfig{
            bundle, session, ProjectId{kProject}, pattern, 7});
    LMDJ_CHECK(controller != nullptr);
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
  const auto journal = f.read_journal();
  LMDJ_CHECK(journal.admission->closure.has_value());
}

void playing_play_stops_without_a_journal() {
  Fixture f;
  f.settle(f.make(6, 1, PatternTransportIntent::play_stop));
  LMDJ_CHECK(f.controller->inspect().playing);
  f.settle(f.make(7, 2, PatternTransportIntent::play_stop));
  const auto status = f.controller->inspect();
  LMDJ_CHECK(!status.playing);
  LMDJ_CHECK(!status.recording);
  const auto journal = f.read_journal();
  LMDJ_CHECK(!journal.admission);
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

void stale_generation_is_rejected() {
  Fixture f;
  auto stale = f.make(6, 1, PatternTransportIntent::play_stop);
  stale.runtime_generation = 8;
  LMDJ_CHECK(f.controller->request(stale) == PatternTransportSubmit::stale);
  LMDJ_CHECK(!f.controller->inspect().playing);
}

}  // namespace

int main() {
  try {
    stopped_record_plays_and_opens_admission();
    recording_record_off_closes_and_keeps_playing();
    playing_play_stops_without_a_journal();
    pending_operation_reports_busy_then_replays();
    stale_generation_is_rejected();
    std::cout << "pattern transport controller tests: PASS (5 scenarios)\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
