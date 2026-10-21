#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <lmdj/facade/application.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "packages/application-facade/internal/lmdj/facade/mutation_publish_scope.hpp"
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using facade::PatternTempoPreviewPhase;
using facade::PatternTempoPreviewStatus;
using foundation::Result;

std::string uuid(unsigned suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') + tail;
}

template <typename T> T take(Result<T> value) {
  if (!value.has_value()) throw std::runtime_error(value.error().message + " " + value.error().details.dump());
  return std::move(value.value());
}

void success(const Result<void>& result) {
  if (!result.has_value()) throw std::runtime_error(result.error().message);
}

std::vector<std::byte> wav() {
  std::vector<std::byte> bytes;
  const auto text = [&](std::string_view s) { for (auto c : s) bytes.push_back(static_cast<std::byte>(c)); };
  const auto u16 = [&](std::uint16_t n) {
    bytes.push_back(static_cast<std::byte>(n & 255));
    bytes.push_back(static_cast<std::byte>(n >> 8));
  };
  const auto u32 = [&](std::uint32_t n) { u16(static_cast<std::uint16_t>(n)); u16(static_cast<std::uint16_t>(n >> 16)); };
  text("RIFF"); u32(24'036); text("WAVEfmt "); u32(16); u16(1); u16(1);
  u32(48'000); u32(96'000); u16(2); u16(16); text("data"); u32(24'000);
  for (unsigned frame = 0; frame < 12'000; ++frame) u16(10'000);
  return bytes;
}

class Platform final : public project_io::ProjectStoragePlatform {
 public:
  std::shared_ptr<project_io::ProjectStoragePlatform> inner = project_io::make_default_project_storage_platform();
  std::atomic<std::uint64_t> writes{};
  std::atomic<bool> fail_after_manifest{};
  std::atomic<bool> fail_writer{};
  std::atomic<bool> failed{};
  Result<std::unique_ptr<project_io::ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override {
    if (fail_writer.exchange(false))
      return Result<std::unique_ptr<project_io::ProjectWriterLease>>::failure(
          {foundation::ErrorCode::io_error, "writer unavailable during exact reconciliation"});
    return inner->acquire_writer(p);
  }
  Result<void> ensure_directory(const std::filesystem::path& p) override { return inner->ensure_directory(p); }
  Result<bool> exists(const std::filesystem::path& p) const override { return inner->exists(p); }
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override { return inner->byte_length(p); }
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override { return inner->read_complete(p); }
  Result<void> create_immutable(const std::filesystem::path& p, std::span<const std::byte> b) override { ++writes; return inner->create_immutable(p, b); }
  Result<void> replace_complete(const std::filesystem::path& p, std::span<const std::byte> b) override {
    ++writes;
    auto result = inner->replace_complete(p, b);
    if (result.has_value() && p.filename() == "manifest.json" && fail_after_manifest.exchange(false)) {
      failed = true;
      return Result<void>::failure({foundation::ErrorCode::io_error, "lost response after actual manifest publication"});
    }
    return result;
  }
  Result<void> append_durable(const std::filesystem::path& p, std::uint64_t n, std::span<const std::byte> b) override { ++writes; return inner->append_durable(p, n, b); }
  Result<void> remove(const std::filesystem::path& p) override { return inner->remove(p); }
  Result<std::vector<std::string>> list_names(const std::filesystem::path& p) const override { return inner->list_names(p); }
  Result<std::vector<std::string>> list_directories(const std::filesystem::path& p) const override { return inner->list_directories(p); }
  Result<bool> directory_exists(const std::filesystem::path& p) const override { return inner->directory_exists(p); }
  Result<void> remove_tree(const std::filesystem::path& p) override { return inner->remove_tree(p); }
  Result<void> publish_directory_if_absent(const std::filesystem::path& a, const std::filesystem::path& b) override { return inner->publish_directory_if_absent(a, b); }
  Result<void> validate_managed_tree(const std::filesystem::path& p) const override { return inner->validate_managed_tree(p); }
};

facade::ApplicationConfig config(const std::filesystem::path& root, const std::shared_ptr<Platform>& platform) {
  facade::ApplicationConfig c{};
  c.workspace_root = root;
  c.storage_platform = platform;
  c.performance_replay_controller = facade::make_unavailable_performance_replay_controller();
  return c;
}

void render(audio::RealtimeEngine& engine, std::uint64_t frames) {
  std::array<float, 128> left{}, right{};
  while (frames) {
    const auto count = static_cast<std::uint32_t>(std::min<std::uint64_t>(128, frames));
    engine.render(left.data(), right.data(), count);
    frames -= count;
  }
}

void until(audio::RealtimeEngine& engine, std::uint64_t frame) {
  LMDJ_CHECK(engine.telemetry().rendered_frames <= frame);
  render(engine, frame - engine.telemetry().rendered_frames);
}

void onset(audio::RealtimeEngine& engine, std::uint64_t frame, std::uint64_t previous) {
  until(engine, frame);
  LMDJ_CHECK(engine.telemetry().started_voices == previous);
  float left{}, right{};
  engine.render(&left, &right, 1);
  LMDJ_CHECK(engine.telemetry().started_voices == previous + 1 && left == 0 && right == 0);
  engine.render(&left, &right, 1);
  LMDJ_CHECK(left > 0 && left == right);
}

struct Fixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-tempo-preview-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path bundle = root / "project.lmdj";
  std::shared_ptr<Platform> platform = std::make_shared<Platform>();
  audio::RealtimeEngine engine;
  std::unique_ptr<facade::Application> app;
  std::unique_ptr<domain::ProjectState> baseline;
  std::optional<audio::PreparedPatternView> source;
  PatternTempoPreviewStatus state;

  explicit Fixture(bool playing = true) {
    std::filesystem::create_directories(root);
    app = std::make_unique<facade::Application>(config(root, platform));
    domain::Pattern pattern{foundation::PatternId{uuid(2)}, 1, {}};
    for (std::uint32_t tick = 0; tick < 3840; tick += 960)
      pattern.events.push_back({{0, 0}, tick, 1, 127});
    take(app->create_initial_project({bundle, foundation::ProjectId{uuid(1)}, 120, pattern}));
    const auto bytes = wav();
    take(app->import_artifact_bytes({bundle, {foundation::CommandId{uuid(10)}, 0}, foundation::AssetId{uuid(11)}, "audio/wav", bytes}));
    const auto assigned = app->command({{"operation", "pad.assign"}, {"project_path", bundle.generic_string()},
        {"command_id", uuid(12)}, {"expected_revision", 1}, {"slot", {{"bank", 0}, {"pad", 0}}}, {"asset_id", uuid(11)}});
    LMDJ_CHECK(assigned.value("ok", false));
    baseline = std::make_unique<domain::ProjectState>(truth());
    LMDJ_CHECK(baseline->revision == 2);
    artifact();
    auto snapshot = take(app->prepare_runtime_snapshot({bundle, foundation::PatternId{uuid(2)}}));
    source = take(audio::PreparedPatternView::from_snapshot(*snapshot));
    success(engine.enable_pattern_transport(7));
    LMDJ_CHECK(engine.publish_sample_bank(audio::PreparedSampleBank::empty(foundation::ProjectId{uuid(1)}, 2)) == audio::PublishResult::accepted);
    auto native = take(source->with_tempo(120));
    const auto published = engine.publish_pattern_view(std::move(native));
    LMDJ_CHECK(published.result == audio::PatternPublishResult::accepted);
    success(engine.start());
    if (playing)
      LMDJ_CHECK(engine.submit_pattern_transport({7, 1, published.generation, audio::PatternTransportAction::start, {}}) == audio::PatternTransportSubmit::accepted);
    render(engine, 1);
    if (playing) {
      LMDJ_CHECK(engine.inspect_pattern_transport_receipt(7, 1).has_value());
      LMDJ_CHECK(engine.acknowledge_pattern_transport_receipt(7, 1));
    }
    state = take(app->bind_pattern_tempo_source({bundle, foundation::ProjectId{uuid(1)},
        foundation::PatternId{uuid(2)}, 2, {1, published.generation}}, *source, engine));
    LMDJ_CHECK(state.phase == PatternTempoPreviewPhase::ready && state.identity.source_id != 0);
    LMDJ_CHECK(app->command({{"operation", "history.open"}, {"project_path", bundle.generic_string()}, {"session_id", uuid(100)}}).value("ok", false));
  }
  ~Fixture() {
    app.reset();
    engine.stop();
    std::error_code ignored;
    std::filesystem::remove_all(root, ignored);
  }
  domain::ProjectState truth() const { return take(project_io::ProjectStore(platform).inspect_committed(bundle)); }
  nlohmann::json history() const {
    const auto reply = app->query({{"operation", "history.inspect"}, {"project_path", bundle.generic_string()}});
    LMDJ_CHECK(reply.value("ok", false));
    return reply.at("result");
  }
  void artifact() const {
    const auto value = truth();
    const auto& ref = value.assets.at(foundation::AssetId{uuid(11)}).artifact;
    LMDJ_CHECK(ref.byte_length == 24'044 && ref.sha256 == "d9116fe7b5537009d51623ec622a866c6a94be1f4a1d6c761078f2b6e16f6eba");
    LMDJ_CHECK(take(project_io::ProjectStore(platform).read_artifact(bundle, ref)) == wav());
  }
  PatternTempoPreviewStatus preview(std::uint16_t bpm, bool start = true) {
    state = take(app->preview_pattern_tempo({{state.identity.source_id, start ? 0 : state.identity.preview_id}, bpm}));
    return state;
  }
  PatternTempoPreviewStatus service() { state = take(app->service_pattern_tempo_preview(state.identity.source_id)); return state; }
  PatternTempoPreviewStatus settle() {
    for (unsigned i = 0; i < 8; ++i) {
      render(engine, 128);
      service();
      if (state.phase == PatternTempoPreviewPhase::cancelled || state.phase == PatternTempoPreviewPhase::committed) return state;
    }
    throw std::runtime_error("tempo did not settle: " + (state.failure ? state.failure->message : "no failure"));
  }
};

void complete_audio_cancel_commit_undo_reopen() {
  Fixture f;
  const auto writes = f.platform->writes.load();
  LMDJ_CHECK(f.history().at("undo_count") == 0);
  until(f.engine, 12'001);
  const auto first = f.preview(240);
  LMDJ_CHECK(first.phase == PatternTempoPreviewPhase::preview_pending);
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == 0);
  onset(f.engine, 18'001, 1);
  LMDJ_CHECK(f.service().applied->anchor == (audio::TransportAnchor{12'001, 1'382'515'200, 240}));
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == 0);
  until(f.engine, 20'000);
  f.state = take(f.app->cancel_pattern_tempo_preview(first.identity));
  LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::cancelling);
  LMDJ_CHECK(f.truth() == *f.baseline);
  onset(f.engine, 40'001, 2);
  LMDJ_CHECK(f.service().phase == PatternTempoPreviewPhase::cancelled);
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == 0 && f.platform->writes == writes);
  until(f.engine, 50'000);
  f.preview(240);
  onset(f.engine, 57'001, 3);
  f.service();
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == 0);
  until(f.engine, 60'000);
  const facade::PatternTempoPreviewCommit command{f.state.identity, {foundation::CommandId{uuid(200)}, 2}};
  f.state = take(f.app->commit_pattern_tempo_preview(command));
  LMDJ_CHECK(f.state.committed_revision == 3 && f.state.phase == PatternTempoPreviewPhase::committed_pending);
  LMDJ_CHECK(f.state.project_revision == 3 && f.state.source_revision == 2);
  auto expected = *f.baseline;
  expected.bpm = 240; expected.revision = 3;
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == 1);
  onset(f.engine, 69'001, 4);
  LMDJ_CHECK(f.service().phase == PatternTempoPreviewPhase::committed);
  LMDJ_CHECK(f.state.project_revision == 3 && f.state.source_revision == 3);
  onset(f.engine, 81'001, 5);
  const auto accepted = f.engine.pattern_telemetry().accepted_publications;
  LMDJ_CHECK(take(f.app->commit_pattern_tempo_preview(command)).committed_revision == 3);
  LMDJ_CHECK(take(f.app->cancel_pattern_tempo_preview(command.identity)).phase == PatternTempoPreviewPhase::committed);
  LMDJ_CHECK(f.engine.pattern_telemetry().accepted_publications == accepted);
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == 1);
  take(f.app->release_pattern_tempo_source(f.state.identity.source_id));
  const auto undone = f.app->command({{"operation", "history.undo"}, {"project_path", f.bundle.generic_string()},
      {"session_id", uuid(100)}, {"command_id", uuid(201)}, {"expected_revision", 3}});
  LMDJ_CHECK(undone.value("ok", false));
  expected.bpm = 120; expected.revision = 4;
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == 0 && f.history().at("redo_count") == 1);
  f.artifact();
  f.app.reset();
  f.app = std::make_unique<facade::Application>(config(f.root, f.platform));
  LMDJ_CHECK(f.truth() == expected);
  f.artifact();
  LMDJ_CHECK(take(f.app->prepare_runtime_snapshot({f.bundle, foundation::PatternId{uuid(2)}}))->bpm == 120);
}

void pending_and_stale_clear_cannot_consume_a_new_turn() {
  Fixture f;
  const auto writes = f.platform->writes.load();
  const auto first = f.preview(240);
  const auto pending = f.app->preview_pattern_tempo({first.identity, 180});
  LMDJ_CHECK(!pending.has_value() && pending.error().details.at("reason") == "tempo_preview_pending");
  auto wrong = first.identity; ++wrong.preview_id;
  LMDJ_CHECK(!f.app->cancel_pattern_tempo_preview(wrong).has_value());
  f.state = take(f.app->cancel_pattern_tempo_preview(first.identity));
  LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::cancelling);
  LMDJ_CHECK(!f.app->commit_pattern_tempo_preview(
      {first.identity, {foundation::CommandId{uuid(250)}, 2}}).has_value());
  f.settle();
  const auto second = f.preview(180);
  LMDJ_CHECK(second.identity.preview_id > first.identity.preview_id);
  const auto before = f.engine.pattern_telemetry().accepted_publications;
  LMDJ_CHECK(!f.app->cancel_pattern_tempo_preview(first.identity).has_value());
  LMDJ_CHECK(f.engine.pattern_telemetry().accepted_publications == before);
  f.state = take(f.app->cancel_pattern_tempo_preview(second.identity));
  f.settle();
  LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes && f.history().at("undo_count") == 0);
  const auto id = f.state.identity.source_id;
  take(f.app->release_pattern_tempo_source(id));
  LMDJ_CHECK(!f.app->service_pattern_tempo_preview(id).has_value());
}

void return_to_base_has_no_publication_or_history() {
  Fixture f;
  const auto writes = f.platform->writes.load();
  const auto publications = f.engine.pattern_telemetry().accepted_publications;
  LMDJ_CHECK(f.preview(120).phase == PatternTempoPreviewPhase::cancelled);
  LMDJ_CHECK(!f.app->preview_pattern_tempo({{f.state.identity.source_id, 0}, 39}).has_value());
  LMDJ_CHECK(f.platform->writes == writes && f.engine.pattern_telemetry().accepted_publications == publications);
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == 0);
}

void cancel_observes_latest_committed_truth_without_writing() {
  Fixture f;
  until(f.engine, 12'001); f.preview(240);
  onset(f.engine, 18'001, 1); f.service();
  const auto changed = take(project_io::ProjectStore(f.platform).execute(f.bundle,
      domain::Command{domain::UpdateSequenceSettings{{foundation::CommandId{uuid(300)}, 2}, 160, {}, {}}}));
  const auto writes = f.platform->writes.load();
  const auto rejected = f.app->commit_pattern_tempo_preview(
      {f.state.identity, {foundation::CommandId{uuid(301)}, 2}});
  LMDJ_CHECK(!rejected.has_value() && rejected.error().details.at("reason") == "tempo_truth_changed");
  LMDJ_CHECK(!f.service().command_id && f.platform->writes == writes && f.truth() == changed.state);
  until(f.engine, 20'000);
  f.state = take(f.app->cancel_pattern_tempo_preview(f.state.identity));
  render(f.engine, 128); f.service(); // actual restore, then same-BPM revision adoption
  render(f.engine, 128); f.service();
  LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::cancelled && f.state.project_revision == 3 && f.state.committed_bpm == 160);
  onset(f.engine, 35'001, 2);
  LMDJ_CHECK(f.truth() == changed.state && f.platform->writes == writes);
}

void actual_published_commit_response_loss_is_retained_and_reconciled() {
  Fixture f;
  f.preview(240); render(f.engine, 128); f.service();
  f.platform->fail_after_manifest = true;
  const facade::PatternTempoPreviewCommit command{f.state.identity, {foundation::CommandId{uuid(400)}, 2}};
  f.state = take(f.app->commit_pattern_tempo_preview(command));
  LMDJ_CHECK(f.platform->failed && f.state.phase == PatternTempoPreviewPhase::commit_unknown && !f.state.committed_revision);
  auto expected = *f.baseline; expected.bpm = 240; expected.revision = 3;
  LMDJ_CHECK(f.truth() == expected); // actual durable far-side fact, despite response failure
  LMDJ_CHECK(!f.app->cancel_pattern_tempo_preview(command.identity).has_value());
  auto changed = command; changed.meta.command_id = foundation::CommandId{uuid(401)};
  LMDJ_CHECK(!f.app->commit_pattern_tempo_preview(changed).has_value());
  LMDJ_CHECK(take(f.app->release_pattern_tempo_source(command.identity.source_id)).phase == PatternTempoPreviewPhase::commit_unknown);
  const auto writes = f.platform->writes.load();
  f.platform->fail_writer = true;
  f.state = take(f.app->commit_pattern_tempo_preview(command));
  LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::commit_unknown &&
      f.state.command_id == command.meta.command_id && !f.state.committed_revision);
  LMDJ_CHECK(!f.app->cancel_pattern_tempo_preview(command.identity).has_value());
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes);
  f.state = take(f.app->commit_pattern_tempo_preview(command));
  LMDJ_CHECK(f.state.committed_revision == 3);
  f.settle();
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == 1 && f.platform->writes == writes);
  f.artifact();
}

void command_collision_is_a_known_refusal_that_can_still_cancel() {
  Fixture f;
  f.preview(240); render(f.engine, 128); f.service();
  const auto writes = f.platform->writes.load();
  const auto rejected = f.app->commit_pattern_tempo_preview(
      {f.state.identity, {foundation::CommandId{uuid(12)}, 2}});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(!f.service().command_id && f.state.phase == PatternTempoPreviewPhase::previewing);
  f.state = take(f.app->cancel_pattern_tempo_preview(f.state.identity));
  f.settle();
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == 0 && f.platform->writes == writes);
  f.artifact();
}

void publication_observation_preserves_the_outer_host_gate() {
  Fixture f;
  f.preview(240); render(f.engine, 128); f.service();
  struct Gate {
    bool allow{}, fail{};
    unsigned claims{}, commits{}, aborts{}, checks{};
  } gate;
  facade::detail::MutationPublishScope outer({&gate,
      [](void* p) noexcept { auto& g = *static_cast<Gate*>(p); ++g.claims; return g.allow; },
      [](void* p) noexcept { ++static_cast<Gate*>(p)->commits; },
      [](void* p) noexcept { ++static_cast<Gate*>(p)->aborts; },
      [](void* p) noexcept { auto& g = *static_cast<Gate*>(p); ++g.checks; return g.fail; }});
  const facade::PatternTempoPreviewCommit command{f.state.identity, {foundation::CommandId{uuid(420)}, 2}};
  LMDJ_CHECK(!f.app->commit_pattern_tempo_preview(command).has_value());
  LMDJ_CHECK(gate.claims == 1 && gate.commits == 0 && gate.aborts == 0 && gate.checks == 0);
  LMDJ_CHECK(!f.service().command_id && f.truth() == *f.baseline && f.history().at("undo_count") == 0);
  gate.allow = true; gate.fail = true;
  f.state = take(f.app->commit_pattern_tempo_preview(command));
  LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::commit_unknown && !f.state.committed_revision);
  LMDJ_CHECK(gate.claims == 2 && gate.commits == 0 && gate.aborts == 1 && gate.checks == 1);
  LMDJ_CHECK(!f.app->cancel_pattern_tempo_preview(command.identity).has_value());
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == 0);
  gate.fail = false;
  f.state = take(f.app->commit_pattern_tempo_preview(command));
  f.settle();
  auto expected = *f.baseline; expected.bpm = 240; expected.revision = 3;
  LMDJ_CHECK(gate.claims == 3 && gate.commits == 1 && gate.aborts == 1 && gate.checks == 2);
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == 1);
}

void same_revision_foreign_project_is_refused_before_a_write() {
  Fixture f;
  f.preview(240); render(f.engine, 128); f.service();
  const auto replacement = f.root / "replacement.lmdj";
  const auto retained = f.root / "retained.lmdj";
  facade::Application foreign(config(f.root, f.platform));
  take(foreign.create_initial_project({replacement, foundation::ProjectId{uuid(900)}, 120,
      f.baseline->patterns.at(foundation::PatternId{uuid(2)})}));
  project_io::ProjectStore store(f.platform);
  take(store.execute(replacement, domain::Command{domain::UpdateSequenceSettings{
      {foundation::CommandId{uuid(901)}, 0}, 160, {}, {}}}));
  const auto expected = take(store.execute(replacement, domain::Command{domain::UpdateSequenceSettings{
      {foundation::CommandId{uuid(902)}, 1}, 120, {}, {}}})).state;
  std::filesystem::rename(f.bundle, retained);
  std::filesystem::rename(replacement, f.bundle);
  const auto writes = f.platform->writes.load();
  const auto rejected = f.app->commit_pattern_tempo_preview(
      {f.state.identity, {foundation::CommandId{uuid(903)}, 2}});
  LMDJ_CHECK(!rejected.has_value() && rejected.error().details.at("reason") == "tempo_source_stale");
  LMDJ_CHECK(!f.service().command_id && f.truth() == expected && f.platform->writes == writes);
  LMDJ_CHECK(take(store.inspect_committed(retained)) == *f.baseline);
  const auto& artifact = f.baseline->assets.at(foundation::AssetId{uuid(11)}).artifact;
  LMDJ_CHECK(take(store.read_artifact(retained, artifact)) == wav());
}

void save_before_preview_apply_stays_committed_through_cancel() {
  Fixture f;
  until(f.engine, 12'001);
  f.preview(240);
  const facade::PatternTempoPreviewCommit command{f.state.identity, {foundation::CommandId{uuid(450)}, 2}};
  f.state = take(f.app->commit_pattern_tempo_preview(command));
  LMDJ_CHECK(f.state.committed_revision == 3 && f.state.phase == PatternTempoPreviewPhase::committed_pending);
  LMDJ_CHECK(take(f.app->cancel_pattern_tempo_preview(command.identity)).committed_revision == 3);
  auto expected = *f.baseline; expected.bpm = 240; expected.revision = 3;
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == 1);
  onset(f.engine, 18'001, 1);
  f.service(); f.settle();
  LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::committed);
  onset(f.engine, 30'001, 2);
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == 1);
}

void recooked_material_refuses_before_a_preview_or_commit_exists() {
  Fixture f;
  take(f.app->release_pattern_tempo_source(f.state.identity.source_id));
  auto snapshot = take(f.app->prepare_runtime_snapshot({f.bundle, foundation::PatternId{uuid(2)}}));
  auto recooked = take(audio::PreparedPatternView::from_snapshot(*snapshot));
  f.state = take(f.app->bind_pattern_tempo_source({f.bundle, foundation::ProjectId{uuid(1)},
      foundation::PatternId{uuid(2)}, 2, {1, f.engine.pattern_telemetry().current_generation}}, recooked, f.engine));
  const auto writes = f.platform->writes.load();
  const auto publications = f.engine.pattern_telemetry().accepted_publications;
  const auto refused = f.app->preview_pattern_tempo({{f.state.identity.source_id, 0}, 240});
  LMDJ_CHECK(!refused.has_value() && refused.error().details.at("reason") == "tempo_publication_phase_mismatch");
  LMDJ_CHECK(!f.app->commit_pattern_tempo_preview({f.state.identity, {foundation::CommandId{uuid(451)}, 2}}).has_value());
  LMDJ_CHECK(f.platform->writes == writes && f.engine.pattern_telemetry().accepted_publications == publications);
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == 0);
}

void withdrawn_publication_has_an_honest_refusal_and_explicit_resolution() {
  Fixture f;
  const auto withdraw = [&] {
    const auto observed = f.engine.pattern_transport_observation();
    LMDJ_CHECK(observed.has_value());
    const auto authority = observed->pending_switches[1] ? observed->pending_switches[1] : observed->pending_switches[0];
    LMDJ_CHECK(authority.has_value() && f.engine.cancel_unclaimed_pattern_publication(*authority));
    render(f.engine, 128);
    f.service();
    LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::preview_refused && f.state.failure &&
        f.state.failure->details.at("reason") == "tempo_publication_unapplied");
    const auto before = f.engine.pattern_telemetry().accepted_publications;
    f.service();
    LMDJ_CHECK(f.engine.pattern_telemetry().accepted_publications == before);
  };
  f.preview(240); withdraw();
  LMDJ_CHECK(f.state.applied && f.state.applied->anchor.bpm == 120 && f.truth() == *f.baseline);
  f.state = take(f.app->cancel_pattern_tempo_preview(f.state.identity));
  LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::cancelled && f.history().at("undo_count") == 0);
  f.preview(240); withdraw();
  f.state = take(f.app->commit_pattern_tempo_preview({f.state.identity, {foundation::CommandId{uuid(452)}, 2}}));
  LMDJ_CHECK(f.state.committed_revision == 3);
  f.settle();
  auto expected = *f.baseline; expected.bpm = 240; expected.revision = 3;
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == 1);
}

void recording_and_history_are_fenced_before_side_effects() {
  Fixture f;
  f.preview(240);
  const auto writes = f.platform->writes.load();
  const auto begun = f.app->begin_sequence({f.bundle, foundation::SequenceSessionId{uuid(500)},
      foundation::PatternId{uuid(2)}, 2, 1});
  LMDJ_CHECK(!begun.has_value() && begun.error().details.at("reason") == "tempo_preview_active");
  const auto record = f.app->command({{"operation", "performance.record.begin"},
      {"project_path", f.bundle.generic_string()}, {"command_id", uuid(501)}, {"expected_revision", 2},
      {"session_id", uuid(502)}, {"performance_id", uuid(503)}});
  LMDJ_CHECK(!record.at("ok").get<bool>() && record.at("error").at("details").at("reason") == "tempo_preview_active");
  const auto close = f.app->command({{"operation", "history.close"}});
  LMDJ_CHECK(!close.at("ok").get<bool>());
  LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes);
  LMDJ_CHECK(f.history().at("disabled_reason") == "tempo_preview_active");
  f.state = take(f.app->cancel_pattern_tempo_preview(f.state.identity));
  f.settle();
  take(f.app->begin_sequence({f.bundle, foundation::SequenceSessionId{uuid(500)}, foundation::PatternId{uuid(2)}, 2, 1}));
  const auto refused = f.app->preview_pattern_tempo({{f.state.identity.source_id, 0}, 180});
  LMDJ_CHECK(!refused.has_value() && refused.error().details.at("reason") == "tempo_recording_active");
  take(f.app->stop_sequence({f.bundle, foundation::SequenceSessionId{uuid(500)}, foundation::CommandId{uuid(504)}, 2}));
  LMDJ_CHECK(f.truth() == *f.baseline);
}

class TransportPort final : public facade::PatternTransportAudioPort {
 public:
  explicit TransportPort(Fixture& fixture) : f(fixture) {}
  audio::PatternTransportSubmit submit(const audio::PatternTransportCommand& r) override { return f.engine.submit_pattern_transport(r); }
  std::optional<audio::PatternTransportReceipt> inspect(std::uint64_t g, std::uint64_t e) const override { return f.engine.inspect_pattern_transport_receipt(g, e); }
  bool acknowledge(std::uint64_t g, std::uint64_t e) override { return f.engine.acknowledge_pattern_transport_receipt(g, e); }
  std::uint64_t pattern_generation() const override { return f.engine.pattern_telemetry().current_generation; }
  std::optional<audio::PatternReplacementAuthority> pending_switch() const override {
    const auto observation = f.engine.pattern_transport_observation();
    return observation ? (observation->pending_switches[1] ? observation->pending_switches[1]
        : observation->pending_switches[0]) : std::nullopt;
  }
  bool supports_receipt_bound_opening() const override { return true; }
  std::optional<audio::PatternTransportObservation> observe_transport() const override { return f.engine.pattern_transport_observation(); }
  std::optional<foundation::PatternId> current_pattern() const override { return f.engine.current_pattern_id(); }
  Result<audio::PatternPublication> publish_overlay(const foundation::PatternId& id,
      std::span<const domain::PatternEvent> events) override {
    auto snapshot = take(f.app->prepare_runtime_snapshot({f.bundle, id}));
    auto view = take(audio::PreparedPatternView::from_snapshot_with_overlay(*snapshot, events));
    const auto published = f.engine.publish_pattern_view_preserving_phase(std::move(view), pattern_generation());
    if (published.result != audio::PatternPublishResult::accepted)
      return Result<audio::PatternPublication>::failure({foundation::ErrorCode::invalid_argument, "test overlay refused"});
    return Result<audio::PatternPublication>::success(published);
  }
  bool cancel_overlay(const audio::PatternReplacementAuthority& r) override { return f.engine.cancel_pattern_publication(r); }
 private:
  Fixture& f;
};

template <typename Call> void wait_for(Call&& call) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
  while (!call()) {
    LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    std::this_thread::yield();
  }
}

void moved_vended_transport_keeps_both_directions_of_the_interlock() {
  Fixture f(false);
  TransportPort port(f);
  auto original = f.app->make_pattern_transport_controller(port,
      {f.bundle, foundation::SequenceSessionId{uuid(600)}, foundation::ProjectId{uuid(1)}, foundation::PatternId{uuid(2)}, 7});
  auto controller = std::make_unique<facade::PatternTransportController>(std::move(*original));
  original.reset(); // Registry observation must follow the stable pimpl.
  wait_for([&] { return controller->inspect_io().ready; });
  f.preview(240);
  const auto request = [&](facade::PatternTransportIntent intent, unsigned command) {
    return facade::PatternTransportRequest{foundation::SequenceSessionId{uuid(600)},
        foundation::ProjectId{uuid(1)}, foundation::CommandId{uuid(command)}, 7,
        controller->inspect().transport_epoch + 1, intent, 2};
  };
  LMDJ_CHECK(controller->request(request(facade::PatternTransportIntent::record, 601)) == facade::PatternTransportSubmit::busy);
  f.state = take(f.app->cancel_pattern_tempo_preview(f.state.identity)); f.settle();
  LMDJ_CHECK(controller->request(request(facade::PatternTransportIntent::play_stop, 602)) == facade::PatternTransportSubmit::accepted);
  const auto tick = [&] { render(f.engine, 128); success(controller->continue_operation()); };
  wait_for([&] { tick(); return controller->inspect().playing && controller->inspect().phase == facade::PatternTransportPhase::idle; });
  f.preview(180); // Merely owning a playing transport is not a recording lock.
  f.state = take(f.app->cancel_pattern_tempo_preview(f.state.identity)); f.settle();
  LMDJ_CHECK(controller->request(request(facade::PatternTransportIntent::record, 603)) == facade::PatternTransportSubmit::accepted);
  const auto refused = f.app->preview_pattern_tempo({{f.state.identity.source_id, 0}, 200});
  LMDJ_CHECK(!refused.has_value() && refused.error().details.at("reason") == "tempo_recording_active");
  wait_for([&] { tick(); return controller->inspect().recording && controller->inspect().phase == facade::PatternTransportPhase::idle; });
  controller->request_shutdown();
  wait_for([&] { tick(); return controller->shutdown_complete(); });
  controller.reset();
  LMDJ_CHECK(f.truth() == *f.baseline);
}

void retiring_one_controller_does_not_remove_another_same_session_guard() {
  Fixture f(false);
  TransportPort port(f);
  const facade::PatternTransportControllerConfig c{f.bundle, foundation::SequenceSessionId{uuid(610)},
      foundation::ProjectId{uuid(1)}, foundation::PatternId{uuid(2)}, 7};
  auto retired = f.app->make_pattern_transport_controller(port, c);
  auto current = f.app->make_pattern_transport_controller(port, c);
  wait_for([&] { return retired->inspect_io().ready && current->inspect_io().ready; });
  retired.reset();
  LMDJ_CHECK(current->request({c.session, c.project, foundation::CommandId{uuid(611)}, 7, 1,
      facade::PatternTransportIntent::record, 2}) == facade::PatternTransportSubmit::accepted);
  const auto tick = [&] { render(f.engine, 128); success(current->continue_operation()); };
  wait_for([&] { tick(); return current->inspect().recording && current->inspect().phase == facade::PatternTransportPhase::idle; });
  const auto refused = f.app->preview_pattern_tempo({{f.state.identity.source_id, 0}, 180});
  LMDJ_CHECK(!refused.has_value() && refused.error().details.at("reason") == "tempo_recording_active");
  current->request_shutdown();
  wait_for([&] { tick(); return current->shutdown_complete(); });
  current.reset();
  LMDJ_CHECK(f.truth() == *f.baseline);
}

void stopped_owner_cannot_resurrect_its_preview_after_restart() {
  Fixture f;
  f.preview(240); render(f.engine, 128); f.service();
  f.engine.stop();
  LMDJ_CHECK(f.service().phase == PatternTempoPreviewPhase::source_lost);
  LMDJ_CHECK(!f.engine.current_pattern_id());
  take(f.app->release_pattern_tempo_source(f.state.identity.source_id));
  success(f.engine.start()); render(f.engine, 128);
  LMDJ_CHECK(!f.engine.current_pattern_id());
  LMDJ_CHECK(!f.app->preview_pattern_tempo({f.state.identity, 180}).has_value());
  LMDJ_CHECK(f.truth() == *f.baseline);
}

void foreign_publication_is_not_cancelled_or_stopped_by_old_owner() {
  Fixture f;
  f.preview(240); render(f.engine, 128); f.service();
  auto snapshot = take(f.app->prepare_runtime_snapshot({f.bundle, foundation::PatternId{uuid(2)}}));
  auto foreign = *snapshot; foreign.pattern_id = foundation::PatternId{uuid(700)};
  auto prepared = take(audio::PreparedPatternView::from_snapshot(foreign));
  const auto published = f.engine.publish_pattern_view_immediate(std::move(prepared));
  LMDJ_CHECK(published.result == audio::PatternPublishResult::accepted);
  render(f.engine, 128);
  LMDJ_CHECK(f.service().phase == PatternTempoPreviewPhase::source_lost);
  LMDJ_CHECK(!f.app->cancel_pattern_tempo_preview(f.state.identity).has_value());
  f.app.reset();
  LMDJ_CHECK(f.engine.telemetry().state == audio::RealtimeState::running);
  LMDJ_CHECK(f.engine.current_pattern_id() == foundation::PatternId{uuid(700)});
  LMDJ_CHECK(f.engine.pattern_telemetry().current_generation == published.generation);
  LMDJ_CHECK(f.truth() == *f.baseline);
}

void terminal_application_destruction_clears_unapplied_preview() {
  Fixture f;
  f.preview(240);
  LMDJ_CHECK(f.engine.pattern_telemetry().pending_publications == 1);
  f.app.reset();
  LMDJ_CHECK(f.engine.telemetry().state == audio::RealtimeState::stopped);
  LMDJ_CHECK(!f.engine.current_pattern_id() && f.engine.pattern_telemetry().pending_publications == 0);
  success(f.engine.start()); render(f.engine, 128);
  LMDJ_CHECK(!f.engine.current_pattern_id() && f.truth() == *f.baseline);
}

class Replay final : public facade::PerformanceReplayController {
 public:
  facade::ReplayState state{facade::ReplayState::stopped};
  unsigned begins{};
  Result<facade::ReplayRuntimeStatus> begin(const facade::ReplayId&,
      std::shared_ptr<const cooker::PerformanceReplayProjection>) override {
    ++begins;
    state = facade::ReplayState::playing;
    return Result<facade::ReplayRuntimeStatus>::success({state, 0, 0, 3});
  }
  Result<facade::ReplayRuntimeStatus> status(const facade::ReplayId&) const override {
    return Result<facade::ReplayRuntimeStatus>::success({state, 0, 0, 3});
  }
  Result<facade::ReplayRuntimeStatus> stop(const facade::ReplayId&) override {
    state = facade::ReplayState::stopped;
    return Result<facade::ReplayRuntimeStatus>::success({state, 0, 0, 3});
  }
};

void valid_replay_and_preview_cannot_open_over_each_other() {
  Fixture f;
  take(f.app->release_pattern_tempo_source(f.state.identity.source_id));
  f.app.reset();
  take(project_io::ProjectStore(f.platform).create_performance(f.bundle,
      {{foundation::CommandId{uuid(800)}, 2}, domain::PerformanceId{uuid(801)}, "Replay fixture"}));
  auto replay = std::make_shared<Replay>();
  auto c = config(f.root, f.platform);
  c.performance_replay_controller = replay;
  f.app = std::make_unique<facade::Application>(std::move(c));
  auto snapshot = take(f.app->prepare_runtime_snapshot({f.bundle, foundation::PatternId{uuid(2)}}));
  f.source = take(audio::PreparedPatternView::from_snapshot(*snapshot));
  const auto published = f.engine.publish_pattern_view_immediate(take(f.source->with_tempo(120)));
  LMDJ_CHECK(published.result == audio::PatternPublishResult::accepted);
  render(f.engine, 128);
  f.state = take(f.app->bind_pattern_tempo_source({f.bundle, foundation::ProjectId{uuid(1)},
      foundation::PatternId{uuid(2)}, 3, {1, published.generation}}, *f.source, f.engine));
  f.baseline = std::make_unique<domain::ProjectState>(f.truth());
  const auto begin = nlohmann::json{{"operation", "performance.replay.begin"},
      {"project_path", f.bundle.generic_string()}, {"replay_id", uuid(802)}, {"performance_id", uuid(801)}};
  LMDJ_CHECK(f.app->command(begin).value("ok", false));
  const auto before = f.engine.pattern_telemetry().accepted_publications;
  const auto refused = f.app->preview_pattern_tempo({{f.state.identity.source_id, 0}, 240});
  LMDJ_CHECK(!refused.has_value() && refused.error().details.at("reason") == "tempo_replay_active");
  LMDJ_CHECK(f.engine.pattern_telemetry().accepted_publications == before && f.truth() == *f.baseline);
  LMDJ_CHECK(f.app->command({{"operation", "performance.replay.stop"}, {"project_path", f.bundle.generic_string()},
      {"replay_id", uuid(802)}, {"request_id", uuid(803)}}).value("ok", false));
  f.preview(240);
  const auto blocked = f.app->command(begin);
  LMDJ_CHECK(!blocked.at("ok").get<bool>() && blocked.at("error").at("details").at("reason") == "tempo_preview_active");
  LMDJ_CHECK(replay->begins == 1 && f.truth() == *f.baseline);
  f.state = take(f.app->cancel_pattern_tempo_preview(f.state.identity));
  f.settle();
}

void concurrent_render_and_facade_preview_settlement() {
  Fixture f;
  std::atomic<std::uint64_t> callbacks{};
  std::jthread audio([&](std::stop_token stop) {
    while (!stop.stop_requested()) { render(f.engine, 128); ++callbacks; }
  });
  std::uint64_t accepted{}, refused{};
  for (unsigned round = 0; round < 16; ++round) {
    f.preview(round % 2 == 0 ? 240 : 180); ++accepted;
    const auto pending = f.app->preview_pattern_tempo({f.state.identity, 200});
    LMDJ_CHECK(!pending.has_value()); ++refused;
    f.state = take(f.app->cancel_pattern_tempo_preview(f.state.identity));
    for (unsigned probe = 0; probe < 100'000 && f.state.phase != PatternTempoPreviewPhase::cancelled; ++probe) {
      f.service(); std::this_thread::yield();
    }
    LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::cancelled);
  }
  // Normal owner disposal completes while callbacks still run. The Session
  // must be gone before Application destruction; Native stop is not a gate.
  f.preview(240); ++accepted;
  const auto source_id = f.state.identity.source_id;
  f.state = take(f.app->release_pattern_tempo_source(source_id));
  for (unsigned probe = 0; probe < 100'000 && f.state.phase != PatternTempoPreviewPhase::cancelled; ++probe) {
    f.state = take(f.app->release_pattern_tempo_source(source_id));
    std::this_thread::yield();
  }
  LMDJ_CHECK(f.state.phase == PatternTempoPreviewPhase::cancelled);
  LMDJ_CHECK(!f.app->service_pattern_tempo_preview(source_id).has_value());
  LMDJ_CHECK(f.history().at("undo_count") == 0);
  const auto before_destroy = callbacks.load();
  f.app.reset();
  for (unsigned probe = 0; probe < 100'000 && callbacks.load() == before_destroy; ++probe)
    std::this_thread::yield();
  LMDJ_CHECK(callbacks.load() > before_destroy && f.engine.telemetry().state == audio::RealtimeState::running);
  audio.request_stop(); audio.join();
  LMDJ_CHECK(accepted == 17 && refused == 16 && callbacks > 0);
  LMDJ_CHECK(f.truth() == *f.baseline);
  std::cout << "Facade tempo concurrent: accepted=" << accepted << " refused=" << refused
            << " callbacks=" << callbacks.load() << '\n';
}
}  // namespace

int main(int argc, char** argv) {
  try {
    const std::string_view group = argc == 2 ? argv[1] : "all";
    LMDJ_CHECK(argc <= 2);
    if (group == "journey" || group == "all") complete_audio_cancel_commit_undo_reopen();
    if (group == "identity" || group == "all") {
      pending_and_stale_clear_cannot_consume_a_new_turn();
      return_to_base_has_no_publication_or_history();
      cancel_observes_latest_committed_truth_without_writing();
      same_revision_foreign_project_is_refused_before_a_write();
      recooked_material_refuses_before_a_preview_or_commit_exists();
      withdrawn_publication_has_an_honest_refusal_and_explicit_resolution();
    }
    if (group == "uncertain" || group == "all") {
      actual_published_commit_response_loss_is_retained_and_reconciled();
      command_collision_is_a_known_refusal_that_can_still_cancel();
      publication_observation_preserves_the_outer_host_gate();
      save_before_preview_apply_stays_committed_through_cancel();
    }
    if (group == "ownership" || group == "all") {
      recording_and_history_are_fenced_before_side_effects();
      moved_vended_transport_keeps_both_directions_of_the_interlock();
      retiring_one_controller_does_not_remove_another_same_session_guard();
      stopped_owner_cannot_resurrect_its_preview_after_restart();
      foreign_publication_is_not_cancelled_or_stopped_by_old_owner();
      terminal_application_destruction_clears_unapplied_preview();
      valid_replay_and_preview_cannot_open_over_each_other();
    }
    if (group == "stress") concurrent_render_and_facade_preview_settlement();
    LMDJ_CHECK(group == "journey" || group == "identity" || group == "uncertain" || group == "ownership" || group == "stress" || group == "all");
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
