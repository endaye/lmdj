#include <chrono>
#include <filesystem>
#include <iostream>
#include <fstream>
#include <functional>
#include <lmdj/project_io/project_store.hpp>
#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/candidate_adoption.hpp"

namespace {
using namespace lmdj::test::candidate;
using namespace lmdj::project_io;
using namespace lmdj::project_io::testing;
// Simulates the storage boundary where replace completed durably but its
// acknowledgement was lost. Core must read the manifest before moving again.
class UnknownManifestPlatform final : public ProjectStoragePlatform {
 public:
  std::shared_ptr<ProjectStoragePlatform> delegate = make_default_project_storage_platform();
  bool fail_after_manifest{};
  Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override { return delegate->acquire_writer(p); }
  Result<void> ensure_directory(const std::filesystem::path& p) override { return delegate->ensure_directory(p); }
  Result<bool> exists(const std::filesystem::path& p) const override { return delegate->exists(p); }
  Result<bool> directory_exists(const std::filesystem::path& p) const override { return delegate->directory_exists(p); }
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override { return delegate->byte_length(p); }
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override { return delegate->read_complete(p); }
  Result<void> create_immutable(const std::filesystem::path& p, std::span<const std::byte> b) override { return delegate->create_immutable(p,b); }
  Result<void> replace_complete(const std::filesystem::path& p, std::span<const std::byte> b) override {
    auto result = delegate->replace_complete(p,b);
    if (result.has_value() && p.filename() == "manifest.json" && fail_after_manifest) {
      fail_after_manifest = false;
      return Result<void>::failure(Error{ErrorCode::io_error, "manifest acknowledgement lost"});
    }
    return result;
  }
  Result<void> append_durable(const std::filesystem::path& p, std::uint64_t n, std::span<const std::byte> b) override { return delegate->append_durable(p,n,b); }
  Result<void> remove(const std::filesystem::path& p) override { return delegate->remove(p); }
  Result<std::vector<std::string>> list_names(const std::filesystem::path& p) const override { return delegate->list_names(p); }
  Result<std::vector<std::string>> list_directories(const std::filesystem::path& p) const override { return delegate->list_directories(p); }
  Result<void> validate_managed_tree(const std::filesystem::path& p) const override { return delegate->validate_managed_tree(p); }
};
struct Fixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-history-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".lmdj");
  ProjectStore store;
  std::string session = uuid(900);
  unsigned id = 100;
  explicit Fixture(std::shared_ptr<ProjectStoragePlatform> platform = {}) : store(std::move(platform)) {
    LMDJ_CHECK(store.create(root, create_project(ProjectId{uuid(1)}, 120).value()).has_value());
    const auto opened = store.open_authoring_history(root, session);
    if (!opened.has_value()) throw std::runtime_error(opened.error().message);
    LMDJ_CHECK(opened.value().disabled_reason.empty());
  }
  ~Fixture() { set_fault_hook(nullptr); std::error_code ec; std::filesystem::remove_all(root, ec); }
  ProjectState state() {
    auto loaded = store.load(root);
    if (!loaded.has_value()) throw std::runtime_error(loaded.error().message);
    return loaded.value();
  }
  CommandMeta meta() { return {CommandId{uuid(id++)}, state().revision}; }
  AuthoringHistoryStatus status() {
    const auto result = store.inspect_authoring_history(root);
    if (!result.has_value()) throw std::runtime_error(result.error().message);
    return result.value();
  }
  AppliedCommand restore(bool redo = false) {
    const auto result = store.restore_authoring_history(root, meta(), session, redo);
    if (!result.has_value()) throw std::runtime_error(result.error().message + result.error().details.dump());
    return result.value();
  }
  void edit(int gain) {
    auto playback = state().banks[0][0].playback;
    playback.gain_millidb = gain;
    const auto result = store.execute(root, UpdatePadPlayback{meta(), {0,0}, playback});
    if (!result.has_value()) throw std::runtime_error(result.error().message);
  }
};
// Undo and redo carry every 5.1.0 parity field through the persisted history.
void parity_edit_undoes_and_redoes() {
  Fixture f;
  const auto before = f.state();
  auto playback = before.banks[0][0].playback;
  playback.trim_end_frame = 30;
  playback.trigger_mode = TriggerMode::loop_gate;
  playback.reverse = true;
  playback.pitch_cents = -350;
  playback.pan = 60;
  playback.loop_mode = LoopMode::ping_pong;
  playback.loop_start_frame = 12;
  LMDJ_CHECK(f.store.execute(f.root, UpdatePadPlayback{f.meta(), {0,0}, playback}).has_value());
  const auto edited = f.state();
  LMDJ_CHECK(edited.banks[0][0].playback == playback);
  LMDJ_CHECK(f.restore().state.banks == before.banks);
  LMDJ_CHECK(f.restore(true).state.banks == edited.banks);
}
void tone_edit_undoes_and_redoes() {
  Fixture f;
  const auto before = f.state();
  auto playback = before.banks[0][0].playback;
  playback.trigger_mode = TriggerMode::gate;
  playback.attack_ms = 250;
  playback.release_ms = 1200;
  playback.tone = 35;
  playback.eq.mid = lmdj::domain::PadEqBell{2500, -600, 1400};
  playback.eq.high = lmdj::domain::PadEqShelf{lmdj::domain::EqBandKind::cut, 9000, -1800};
  LMDJ_CHECK(f.store.execute(f.root, UpdatePadPlayback{f.meta(), {0,0}, playback}).has_value());
  const auto edited = f.state();
  LMDJ_CHECK(edited.banks[0][0].playback == playback);
  LMDJ_CHECK(f.restore().state.banks == before.banks);
  LMDJ_CHECK(f.restore(true).state.banks == edited.banks);
}
void edit_restore_and_persist() {
  Fixture f;
  const auto before = f.state();
  f.edit(-200);
  LMDJ_CHECK(f.status().undo_count == 1);
  LMDJ_CHECK(f.status().undo_label == "Edit Pad");
  const auto edited = f.state();
  const auto undone = f.restore();
  LMDJ_CHECK(undone.state.banks == before.banks);
  LMDJ_CHECK(undone.state.revision == 2);
  LMDJ_CHECK(f.status().undo_count == 0 && f.status().redo_count == 1);
  const auto redone = f.restore(true);
  LMDJ_CHECK(redone.state.banks == edited.banks);
  LMDJ_CHECK(redone.state.revision == 3);
  ProjectStore reopened;
  const auto persisted = reopened.load(f.root);
  LMDJ_CHECK(persisted.has_value() && persisted.value() == redone.state);
  LMDJ_CHECK(reopened.open_authoring_history(f.root, uuid(901)).value().undo_count == 0);
}
void retry_noop_and_fork() {
  Fixture f;
  f.edit(-100);
  const auto command = f.meta();
  LMDJ_CHECK(f.store.restore_authoring_history(f.root, command, f.session, false).has_value());
  const auto retry = f.store.restore_authoring_history(f.root, command, f.session, false);
  LMDJ_CHECK(retry.has_value() && retry.value().replayed);
  LMDJ_CHECK(f.status().redo_count == 1 && f.status().undo_count == 0);
  f.edit(0);
  LMDJ_CHECK(f.status().redo_count == 1 && f.status().undo_count == 0);
  auto invalid = f.meta(); invalid.expected_revision += 7;
  LMDJ_CHECK(!f.store.restore_authoring_history(f.root, invalid, f.session, true).has_value());
  LMDJ_CHECK(f.status().redo_count == 1);
  f.edit(-300);
  LMDJ_CHECK(f.status().redo_count == 0 && f.status().undo_count == 1);
}
void import_retains_original_bytes() {
  Fixture f;
  const std::vector<std::byte> bytes{std::byte{1}, std::byte{2}, std::byte{3}};
  const auto imported = f.store.import_artifact_bytes(f.root,
      {f.meta(), AssetId{uuid(2)}, "audio/wav", bytes});
  LMDJ_CHECK(imported.has_value());
  const auto artifact = imported.value().state.assets.at(AssetId{uuid(2)}).artifact;
  f.restore();
  LMDJ_CHECK(f.state().assets.empty()); // also exercises orphan scavenging
  const auto retained = f.store.read_artifact(f.root, artifact);
  LMDJ_CHECK(retained.has_value() && retained.value() == bytes);
  const auto redone = f.restore(true);
  LMDJ_CHECK(redone.state.assets.at(AssetId{uuid(2)}).artifact == artifact);
  LMDJ_CHECK(f.store.read_artifact(f.root, artifact).value() == bytes);
}
void adoption_is_one_action_and_reuses_every_original_artifact() {
  Fixture f;
  const std::vector<std::byte> source{std::byte{1}, std::byte{2}, std::byte{3}};
  const auto imported = f.store.import_artifact_bytes(f.root,
      {f.meta(), AssetId{uuid(2)}, "audio/wav", source});
  LMDJ_CHECK(imported.has_value());
  const auto before = f.state();
  const auto source_ref = before.assets.at(AssetId{uuid(2)}).artifact;
  const std::vector<std::vector<std::byte>> outputs{{std::byte{4}}, {std::byte{5}, std::byte{6}}};
  ProjectStore::CandidateAdoptionRequest request{f.meta(), before.id, AssetId{uuid(2)}, source_ref, {}};
  for (unsigned i = 0; i < outputs.size(); ++i)
    request.slots.push_back({{0, static_cast<std::uint8_t>(i)}, AssetId{uuid(4+i)},
        "audio/wav", outputs[i], lineage(source_ref)});
  const auto adopted = f.store.adopt_candidates(f.root, request);
  LMDJ_CHECK(adopted.has_value());
  LMDJ_CHECK(f.status().undo_count == 2);
  const auto undone = f.restore();
  LMDJ_CHECK(undone.state.assets == before.assets && undone.state.banks == before.banks);
  LMDJ_CHECK(f.state().revision == 3); // load also scavenges unreferenced assets
  for (unsigned i = 0; i < outputs.size(); ++i) {
    const auto& ref = adopted.value().state.assets.at(AssetId{uuid(4+i)}).artifact;
    LMDJ_CHECK(f.store.read_artifact(f.root, ref).value() == outputs[i]);
  }
  const auto redone = f.restore(true);
  LMDJ_CHECK(redone.state.revision == 4);
  LMDJ_CHECK(redone.state.assets == adopted.value().state.assets);
  LMDJ_CHECK(redone.state.banks == adopted.value().state.banks);
  LMDJ_CHECK(f.status().undo_count == 2 && f.status().redo_count == 0);
  ProjectStore reopened;
  LMDJ_CHECK(reopened.load(f.root).value() == redone.state);
}
Result<void> fail_publish(FaultPoint point, const std::filesystem::path&) {
  return point == FaultPoint::manifest_publish
      ? Result<void>::failure(Error{ErrorCode::io_error, "injected history publication failure"})
      : Result<void>::success();
}
void failed_publication_keeps_stack() {
  Fixture f;
  f.edit(-100);
  const auto command = f.meta();
  set_fault_hook(fail_publish);
  LMDJ_CHECK(!f.store.restore_authoring_history(f.root, command, f.session, false).has_value());
  set_fault_hook(nullptr);
  LMDJ_CHECK(f.status().undo_count == 1 && f.status().redo_count == 0);
  LMDJ_CHECK(f.state().banks[0][0].playback.gain_millidb == -100);
  LMDJ_CHECK(f.store.restore_authoring_history(f.root, command, f.session, false).has_value());
  LMDJ_CHECK(f.status().undo_count == 0 && f.status().redo_count == 1);
}
void external_changes_and_sessions_invalidate() {
  Fixture f;
  f.edit(-100);
  LMDJ_CHECK(!f.store.restore_authoring_history(f.root, f.meta(), uuid(999), false).has_value());
  LMDJ_CHECK(f.status().undo_count == 1);
  ProjectStore other;
  auto playback = f.state().banks[0][0].playback; playback.gain_millidb = -400;
  LMDJ_CHECK(other.execute(f.root, UpdatePadPlayback{f.meta(), {0,0}, playback}).has_value());
  LMDJ_CHECK(f.status().disabled_reason == "authoring_history_invalidated");
  LMDJ_CHECK(f.status().undo_count == 0);
  LMDJ_CHECK(f.store.open_authoring_history(f.root, uuid(901)).value().disabled_reason.empty());
  f.store.close_authoring_history();
  LMDJ_CHECK(f.status().disabled_reason == "authoring_history_not_open");
}
void unknown_commit_reconciles_exactly_once() {
  auto platform = std::make_shared<UnknownManifestPlatform>();
  Fixture f(platform);
  f.edit(-200);
  const auto command = f.meta();
  platform->fail_after_manifest = true;
  LMDJ_CHECK(!f.store.restore_authoring_history(f.root, command, f.session, false).has_value());
  LMDJ_CHECK(f.status().redo_count == 1 && f.status().undo_count == 0);
  LMDJ_CHECK(f.state().revision == 2 && f.state().banks[0][0].playback.gain_millidb == 0);
  const auto reconciled = f.store.restore_authoring_history(f.root, command, f.session, false);
  LMDJ_CHECK(reconciled.has_value() && reconciled.value().replayed);
  LMDJ_CHECK(f.status().redo_count == 1);
  const auto redone = f.restore(true);
  LMDJ_CHECK(redone.state.revision == 3 && redone.state.banks[0][0].playback.gain_millidb == -200);
}
void missing_redo_bytes_refuses_without_moving_history() {
  Fixture f;
  const std::vector<std::byte> bytes{std::byte{1}};
  const auto imported = f.store.import_artifact_bytes(f.root,
      {f.meta(), AssetId{uuid(2)}, "audio/wav", bytes});
  LMDJ_CHECK(imported.has_value());
  const auto artifact = imported.value().state.assets.at(AssetId{uuid(2)}).artifact;
  f.restore();
  std::filesystem::remove(f.root / "assets" / (artifact.sha256 + ".wav"));
  const auto result = f.store.restore_authoring_history(f.root, f.meta(), f.session, true);
  LMDJ_CHECK(!result.has_value() && result.error().code == ErrorCode::missing_asset);
  LMDJ_CHECK(f.state().assets.empty() && f.state().revision == 2);
  LMDJ_CHECK(f.status().redo_count == 1 && f.status().undo_count == 0);
}
void clear_pad_preserves_pattern_events_and_restores_binding() {
  Fixture f;
  const std::vector<std::byte> bytes{std::byte{1}};
  const auto imported = f.store.import_artifact_bytes(f.root,
      {f.meta(), AssetId{uuid(2)}, "audio/wav", bytes});
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(f.store.execute(f.root, AssignPad{f.meta(), {0,0}, AssetId{uuid(2)}}).has_value());
  const auto pattern_id = PatternId{uuid(3)};
  LMDJ_CHECK(f.store.execute(f.root, CreatePattern{f.meta(), Pattern{pattern_id,1,{{{0,0},0,120,100}}}}).has_value());
  f.edit(-400);
  const auto before = f.state();
  const auto command = DeletePad{f.meta(), {0,0}};
  const auto count = f.status().undo_count;
  LMDJ_CHECK(f.store.execute(f.root, command).has_value());
  LMDJ_CHECK(f.status().undo_count == count + 1);
  LMDJ_CHECK(f.store.execute(f.root, command).value().replayed);
  LMDJ_CHECK(f.status().undo_count == count + 1);
  LMDJ_CHECK(f.state().banks[0][0].playback == PadPlayback{});
  LMDJ_CHECK(f.state().assets == before.assets);
  LMDJ_CHECK(f.store.execute(f.root, DeletePad{f.meta(), {0,0}}).has_value());
  LMDJ_CHECK(f.status().undo_count == count + 1);
  LMDJ_CHECK(!f.state().banks[0][0].asset_id && f.state().patterns == before.patterns);
  const auto undone = f.restore().state;
  LMDJ_CHECK(undone.banks == before.banks && undone.patterns == before.patterns);
  LMDJ_CHECK(!f.restore(true).state.banks[0][0].asset_id);
  LMDJ_CHECK(f.state().patterns == before.patterns);
}
void performance_draft_save_and_cancel_are_single_actions() {
  Fixture f;
  f.edit(-100); f.restore();
  const auto session = SequenceSessionId{uuid(910)};
  const auto id = PerformanceId{uuid(911)};
  LMDJ_CHECK(f.store.begin_performance_draft(f.root, {f.meta(),session,id}).has_value());
  LMDJ_CHECK(!f.status().disabled_reason.empty());
  LMDJ_CHECK(!f.store.restore_authoring_history(f.root,f.meta(),f.session,false).has_value());
  LMDJ_CHECK(f.store.stop_performance_session(f.root,session,CommandId{uuid(912)}).has_value());
  LMDJ_CHECK(f.store.discard_performance_draft(f.root,f.meta(),id).has_value());
  LMDJ_CHECK(f.state().performances.empty());
  LMDJ_CHECK(f.status().undo_count == 0 && f.status().redo_count == 1);
  const auto session2 = SequenceSessionId{uuid(913)};
  LMDJ_CHECK(f.store.begin_performance_draft(f.root, {f.meta(),session2,id}).has_value());
  LMDJ_CHECK(f.store.stop_performance_session(f.root,session2,CommandId{uuid(914)}).has_value());
  LMDJ_CHECK(f.store.save_performance_draft(f.root,f.meta(),id,"Take",std::nullopt).has_value());
  const auto saved = f.state();
  LMDJ_CHECK(saved.performances.at(id).name == "Take");
  LMDJ_CHECK(f.status().undo_count == 1 && f.status().redo_count == 0);
  LMDJ_CHECK(f.restore().state.performances.empty());
  LMDJ_CHECK(f.restore(true).state.performances == saved.performances);
  LMDJ_CHECK(f.store.delete_performance(f.root,{f.meta(),id}).has_value());
  LMDJ_CHECK(f.status().undo_count == 2);
  LMDJ_CHECK(f.restore().state.performances == saved.performances);
}
void grouped_cancel_restores_redo_and_capacity() {
  AuthoringHistory history;
  auto a = create_project(ProjectId{uuid(1)},120).value();
  history.start("project.lmdj", uuid(900), a, "a");
  auto b = a; b.revision = 1; b.bpm = 121;
  auto publication = history.prepare("project.lmdj", a,b,"a","b","Edit","",{}).value();
  publication.begin(); publication.confirm();
  auto c = a; c.revision = 2;
  publication = history.prepare("project.lmdj",b,c,"b","c","Undo","",false).value();
  publication.begin(); publication.confirm();
  auto d = c; d.revision = 3; d.bpm = 130;
  publication = history.prepare("project.lmdj",c,d,"c","d","Record","draft",{}).value();
  publication.begin(); publication.confirm();
  auto e = c; e.revision = 4;
  publication = history.prepare("project.lmdj",d,e,"d","e","Cancel","draft",{}).value();
  publication.begin(); publication.confirm();
  LMDJ_CHECK(history.status("project.lmdj").undo_count == 0);
  LMDJ_CHECK(history.status("project.lmdj").redo_count == 1);
  auto previous = e;
  std::string fingerprint = "e";
  for (unsigned i = 0; i < 105; ++i) {
    auto next = previous; ++next.revision; next.bpm = 120 + i % 2;
    const auto next_fingerprint = std::to_string(i);
    publication = history.prepare("project.lmdj",previous,next,fingerprint,next_fingerprint,"Edit","",{}).value();
    publication.begin(); publication.confirm();
    previous = next; fingerprint = next_fingerprint;
  }
  LMDJ_CHECK(history.status("project.lmdj").undo_count == AuthoringHistory::kMaximumActions);
  auto draft = previous; ++draft.revision; draft.swing_percent = 60;
  publication = history.prepare("project.lmdj",previous,draft,fingerprint,"draft","Record","new draft",{}).value();
  publication.begin(); publication.confirm();
  auto cancelled = previous; cancelled.revision = draft.revision + 1;
  publication = history.prepare("project.lmdj",draft,cancelled,"draft","cancelled","Cancel","new draft",{}).value();
  publication.begin(); publication.confirm();
  LMDJ_CHECK(history.status("project.lmdj").undo_count == AuthoringHistory::kMaximumActions);

}
std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}
void persisted_history_rejects_malformed_commands_atomically() {
  using Json = nlohmann::json;
  const std::vector<std::function<void(Json&)>> cases{
    [](auto& c) { c["redo"] = 1; },
    [](auto& c) { c["history_session_id"] = "invalid"; },
    [](auto& c) { c["unexpected"] = true; },
    [](auto& c) { c["delta"]["unexpected"] = true; },
    [](auto& c) { c["delta"]["bpm"] = {{"before",120},{"after",120.5}}; },
    [](auto& c) { c["delta"]["swing_percent"] = {{"before",50},{"after",256}}; },
    [](auto& c) { c["delta"]["quantize_enabled"] = {{"before",true},{"after",0}}; },
    [](auto& c) { c["delta"]["pads"][0]["before"]["asset_id"] = "invalid"; },
    [](auto& c) { c["delta"]["pads"].push_back(c["delta"]["pads"][0]); },
    [](auto& c) { c["delta"]["assets"][uuid(2)] = {{"before",nullptr},{"after",{{"id",uuid(3)},{"artifact",source_artifact()},{"lineage",nullptr}}}}; },
    [](auto& c) { c["delta"]["pattern_slots"] = Json::array({{{"slot",0},{"before",nullptr},{"after",uuid(90)}},{{"slot",0},{"before",nullptr},{"after",uuid(90)}}}); },
    [](auto& c) { c["delta"]["pattern_slots"] = Json::array({{{"slot",16},{"before",nullptr},{"after",uuid(90)}}}); },
  };
  for (const auto& mutate : cases) {
    Fixture f; f.edit(-200); f.restore();
    const auto committed = f.state();
    const auto manifest = read_bytes(f.root / "manifest.json");
    std::filesystem::path transaction;
    Json encoded;
    for (const auto& entry : std::filesystem::directory_iterator(f.root / "history/transactions")) {
      auto candidate = Json::parse(read_bytes(entry.path()));
      if (candidate.at("command").at("type") == "ApplyAuthoringDelta") {
        transaction = entry.path(); encoded = std::move(candidate); break;
      }
    }
    LMDJ_CHECK(!transaction.empty());
    const auto pristine = read_bytes(transaction);
    mutate(encoded["command"]);
    { std::ofstream output(transaction); output << encoded.dump(); }
    ProjectStore reader;
    const auto result = reader.load(f.root);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_project);
    LMDJ_CHECK(read_bytes(f.root / "manifest.json") == manifest);
    { std::ofstream output(transaction); output << pristine; }
    LMDJ_CHECK(reader.load(f.root).value() == committed);
  }
}

// #1671: one grid edit is one action, Undo and Redo restore it exactly, and
// its persisted identity survives a reload so a retry still replays.
void pattern_event_edit_is_one_action_and_replays_after_reload() {
  Fixture f;
  const auto pattern_id = PatternId{uuid(3)};
  LMDJ_CHECK(f.store.execute(f.root, CreatePattern{f.meta(), Pattern{pattern_id, 1,
      {{{0,0},0,240,100}, {{0,1},240,240,100}}}}).has_value());
  const auto before = f.state();
  const auto count = f.status().undo_count;
  // Put is deliberately not in canonical order.
  const EditPatternEvents command{f.meta(), pattern_id, {{{0,0}, 0}},
      {{{0,2},0,120,90}, {{0,0},480,240,100}, {{0,1},240,720,64}}};
  const auto edited = f.store.execute(f.root, command);
  LMDJ_CHECK(edited.has_value() && !edited.value().replayed);
  LMDJ_CHECK(f.status().undo_count == count + 1);
  LMDJ_CHECK(f.status().undo_label == "Edit Pattern");
  const auto after = f.state();
  LMDJ_CHECK((after.patterns.at(pattern_id).events == std::vector<PatternEvent>{
      {{0,2},0,120,90}, {{0,1},240,720,64}, {{0,0},480,240,100}}));

  ProjectStore reopened;
  const auto retry = reopened.execute(f.root, command);
  LMDJ_CHECK(retry.has_value() && retry.value().replayed);
  LMDJ_CHECK(reopened.load(f.root).value() == after);

  const auto undone = f.restore().state;
  LMDJ_CHECK(undone.patterns == before.patterns);
  LMDJ_CHECK(f.restore(true).state.patterns == after.patterns);
}

}

int main() {
  try {
    persisted_history_rejects_malformed_commands_atomically();
    edit_restore_and_persist(); parity_edit_undoes_and_redoes(); tone_edit_undoes_and_redoes(); retry_noop_and_fork(); import_retains_original_bytes();
    failed_publication_keeps_stack(); external_changes_and_sessions_invalidate();
    adoption_is_one_action_and_reuses_every_original_artifact();
    grouped_cancel_restores_redo_and_capacity();
    unknown_commit_reconciles_exactly_once(); missing_redo_bytes_refuses_without_moving_history();
    clear_pad_preserves_pattern_events_and_restores_binding(); performance_draft_save_and_cancel_are_single_actions();
    pattern_event_edit_is_one_action_and_replays_after_reload();
    return 0;
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
