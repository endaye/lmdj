#include <array>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>
#include <unistd.h>

#include <nlohmann/json.hpp>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/facade/pattern_transport_controller.hpp>
#include <lmdj/facade/performance_replay.hpp>

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
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::facade::PatternTransportAudioPort;
using lmdj::facade::PatternTransportControllerConfig;
using lmdj::facade::PatternTransportIntent;
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
            ("lmdj-pattern-events-edit-" + std::to_string(::getpid()) + "-" +
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
      return std::nullopt;
    }
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
  Application application;

  Fixture()
      : bundle(directory.path() / "project.lmdj"),
        application(ApplicationConfig{
            directory.path(),
            nullptr,
            {},
            {},
            lmdj::audio::RuntimePreparationLimits{
                1'048'576, 240'000, 67'108'864, 134'217'728},
            nullptr,
            nullptr,
            nullptr,
            nullptr,
            lmdj::facade::make_unavailable_performance_replay_controller(),
        }) {
    const auto created = application.create_initial_project(
        lmdj::facade::InitialProjectRequest{
            bundle,
            ProjectId{kProject},
            120,
            lmdj::domain::Pattern{
                pattern,
                1,
                {
                    {PadSlotId{0, 0}, 0, 240, 100},
                    {PadSlotId{0, 1}, 480, 120, 90},
                }},
        });
    LMDJ_CHECK(created.has_value());
  }

  PatternTransportRequest make(unsigned command, std::uint64_t epoch,
                               PatternTransportIntent intent) const {
    return {session, ProjectId{kProject}, CommandId{uuid(command)}, 7, epoch,
            intent, {}};
  }

  static nlohmann::json event_key(
      unsigned bank, unsigned pad, unsigned onset_tick) {
    return {
        {"slot", {{"bank", bank}, {"pad", pad}}},
        {"onset_tick", onset_tick},
    };
  }

  static nlohmann::json event(
      unsigned bank, unsigned pad, unsigned onset_tick,
      unsigned duration_tick, unsigned velocity) {
    return {
        {"slot", {{"bank", bank}, {"pad", pad}}},
        {"onset_tick", onset_tick},
        {"duration_tick", duration_tick},
        {"velocity", velocity},
    };
  }

  nlohmann::json edit_events(
      unsigned command, std::uint64_t expected_revision,
      nlohmann::json remove, nlohmann::json put) {
    return application.command({
        {"operation", "pattern.events.edit"},
        {"project_path", bundle.generic_string()},
        {"command_id", uuid(command)},
        {"expected_revision", expected_revision},
        {"pattern_id", kPattern},
        {"remove", std::move(remove)},
        {"put", std::move(put)},
    });
  }

  nlohmann::json pattern_events() {
    const auto inspected = application.query({
        {"operation", "project.inspect"},
        {"project_path", bundle.generic_string()},
    });
    LMDJ_CHECK(inspected.at("ok").get<bool>());
    return inspected.at("result")
        .at("project")
        .at("patterns")
        .at(kPattern)
        .at("events");
  }
};

void edit_is_refused_while_the_transport_records() {
  Fixture f;
  const auto before = f.pattern_events();
  auto lease = f.application.acquire_project_writer(f.bundle);
  LMDJ_CHECK(lease.has_value());
  auto controller = f.application.make_pattern_transport_controller(
      f.audio,
      PatternTransportControllerConfig{
          f.bundle, f.session, ProjectId{kProject}, f.pattern, 7});
  LMDJ_CHECK(controller != nullptr);
  LMDJ_CHECK(controller->request(f.make(6, 1, PatternTransportIntent::record)) ==
             PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(controller->continue_operation().has_value());
  LMDJ_CHECK(controller->inspect().recording);

  const auto refused = f.edit_events(
      7, 0,
      nlohmann::json::array(),
      nlohmann::json::array({Fixture::event(0, 2, 960, 240, 80)}));
  LMDJ_CHECK(!refused.at("ok").get<bool>());
  LMDJ_CHECK(refused.at("error").at("details").at("reason") ==
             "sequence_session_active");
  LMDJ_CHECK(f.pattern_events() == before);
}

void edit_is_admitted_while_the_transport_plays() {
  Fixture f;
  auto lease = f.application.acquire_project_writer(f.bundle);
  LMDJ_CHECK(lease.has_value());
  auto controller = f.application.make_pattern_transport_controller(
      f.audio,
      PatternTransportControllerConfig{
          f.bundle, f.session, ProjectId{kProject}, f.pattern, 7});
  LMDJ_CHECK(controller != nullptr);
  LMDJ_CHECK(
      controller->request(f.make(6, 1, PatternTransportIntent::play_stop)) ==
      PatternTransportSubmit::accepted);
  f.audio.render(1);
  LMDJ_CHECK(controller->continue_operation().has_value());
  const auto status = controller->inspect();
  LMDJ_CHECK(status.playing);
  LMDJ_CHECK(!status.recording);

  const auto edited = f.edit_events(
      7, 0,
      nlohmann::json::array({Fixture::event_key(0, 1, 480)}),
      nlohmann::json::array({Fixture::event(0, 1, 480, 240, 127)}));
  LMDJ_CHECK(edited.at("ok").get<bool>());
  const auto& result = edited.at("result");
  LMDJ_CHECK(result.at("pattern_id") == kPattern);
  LMDJ_CHECK(result.at("committed_revision") == 1);
  LMDJ_CHECK(result.at("replayed") == false);
  LMDJ_CHECK(controller->inspect().playing);
  const auto events = f.pattern_events();
  LMDJ_CHECK(events.size() == 2);
  LMDJ_CHECK(events.at(1).at("duration_tick") == 240);
  LMDJ_CHECK(events.at(1).at("velocity") == 127);
}

}  // namespace

int main() {
  try {
    edit_is_refused_while_the_transport_records();
    edit_is_admitted_while_the_transport_plays();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "facade pattern events edit tests: PASS\n";
  return 0;
}
