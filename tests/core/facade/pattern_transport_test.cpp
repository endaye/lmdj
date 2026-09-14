#include <array>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <memory>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/pattern_transport_ports.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

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
using lmdj::facade::detail::PatternTransportAudioPort;
using lmdj::facade::detail::PatternTransportCoordinator;
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
  explicit TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-transport-" +
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
    return engine.acknowledge_pattern_transport_receipt(
        runtime_generation, epoch);
  }
  std::uint64_t pattern_generation() const override { return generation; }
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

struct Fixture {
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
        coordinator(audio, journals, bundle, session, ProjectId{kProject},
                    pattern, 7) {
    auto created = lmdj::domain::create_project(ProjectId{kProject}, 120);
    LMDJ_CHECK(created.has_value());
    auto state = std::move(created.value());
    state.patterns.emplace(pattern, lmdj::domain::Pattern{pattern, 1, {}});
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
    std::cout << "pattern transport tests: PASS (8 scenarios)\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
