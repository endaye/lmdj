#include <array>
#include <cerrno>
#include <chrono>
#include <csignal>
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

#include "packages/application-facade/src/pattern_transport_io_owner.hpp"
#include "tests/core/support/test.hpp"
#include "tests/core/support/child_process.hpp"

namespace {
using namespace lmdj;
using Json = nlohmann::json;
using facade::PatternTransportWorkOutcome;
using facade::PatternTransportWorkRequest;
using facade::detail::PatternTransportIoOwner;
using domain::PatternEvent;

std::string uuid(unsigned suffix) {
  const auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') + tail;
}
class FaultStorage final : public lmdj::project_io::ProjectStoragePlatform {
 public:
  static lmdj::foundation::Result<void> fault() {
    return lmdj::foundation::Result<void>::failure(
        {lmdj::foundation::ErrorCode::io_error, "injected segment durability failure"});
  }
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner =
      lmdj::project_io::make_default_project_storage_platform();
  std::string fault_kind;
  bool after_write = false;
  bool fault_hit = false;
  bool fail_sync = false;
  std::filesystem::path crash_marker;
  std::string crash_label;

  lmdj::foundation::Result<void> selected_fault() {
    if (!crash_marker.empty()) {
      { std::ofstream marker(crash_marker); marker << crash_label; marker.flush();
        LMDJ_CHECK(static_cast<bool>(marker)); }
      std::raise(SIGSTOP);
    }
    return fault();
  }

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
    const bool hit = fault_kind == "manifest" && path.filename() == "manifest.json";
    if (hit) { fault_kind.clear(); fault_hit = true; }
    if (hit && !after_write) return selected_fault();
    const auto result = inner->replace_complete(path, bytes);
    return hit && result.has_value() ? selected_fault() : result;
  }
  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path, std::uint64_t prefix,
      std::span<const std::byte> bytes) override {
    const auto text = bytes.empty() ? std::string{} :
        std::string(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    const bool hit = !fault_kind.empty() && fault_kind != "manifest" &&
        text.find("\"kind\":\"" + fault_kind + "\"") != std::string::npos;
    if (hit) { fault_kind.clear(); fault_hit = true; }
    if (hit && !after_write) return selected_fault();
    if (fail_sync && bytes.empty()) return fault();
    const auto result = inner->append_durable(path, prefix, bytes);
    return hit && result.has_value() ? selected_fault() : result;
  }
  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    const bool hit = fault_kind == "remove" && path.filename() == "sequence.jsonl";
    if (hit) { fault_kind.clear(); fault_hit = true; }
    if (hit && !after_write) return selected_fault();
    const auto result = inner->remove(path);
    return hit && result.has_value() ? selected_fault() : result;
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
  std::shared_ptr<FaultStorage> platform = std::make_shared<FaultStorage>();
  std::filesystem::path root;
  std::filesystem::path bundle = root / "project.lmdj";
  project_io::ProjectStore store{platform};
  project_io::SequenceJournal journals{platform};
  foundation::ProjectId project{uuid(4)};
  foundation::PatternId a{uuid(2)}, b{uuid(9)};
  foundation::SequenceSessionId session{uuid(1)};
  facade::PatternTransportControllerConfig config{bundle, session, project, a, 7};
  std::unique_ptr<PatternTransportIoOwner> io;
  std::uint64_t step = 1;
  explicit Fixture(std::filesystem::path owned_root =
      std::filesystem::temp_directory_path() / ("lmdj-recording-segments-" +
          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count())))
      : root(std::move(owned_root)) {
    auto created = domain::create_project(project, 120);
    LMDJ_CHECK(created.has_value());
    auto state = std::move(created.value());
    state.patterns.emplace(a, domain::Pattern{a, 1, {}});
    state.patterns.emplace(b, domain::Pattern{b, 1, {}});
    LMDJ_CHECK(store.create(bundle, state).has_value());
    reopen_owner();
    const project_io::SequenceAdmissionFence fence{
        project_io::SequenceFenceKind::admission, foundation::CommandId{uuid(5)},
        11, 13000, 1000, a, 21, 120, true, {}, project_io::SequenceSwitchOutcome::none, {}};
    run(work(3, {{"op", "open"}, {"pattern", a.value()}, {"revision", 0},
        {"generation", 21}, {"started", facade::detail::transport_clock_stamp(std::chrono::steady_clock::now())},
        {"fence", facade::detail::encode_transport_fence(fence)}}));
  }
  ~Fixture() {
    io.reset();
    std::error_code ignored;
    std::filesystem::remove_all(root, ignored);
  }
  void reopen_owner() { io = std::make_unique<PatternTransportIoOwner>(config, platform, nullptr); }
  PatternTransportWorkRequest work(unsigned command, Json payload, std::uint64_t epoch = 11) {
    return {{7, epoch, foundation::CommandId{uuid(command)}, step++}, payload.dump()};
  }
  void run(const PatternTransportWorkRequest& request) {
    const auto result = io->execute(request);
    if (result.outcome != PatternTransportWorkOutcome::success && result.error)
      std::cerr << result.error->message << ' ' << result.error->details.dump() << '\n';
    LMDJ_CHECK(result.outcome == PatternTransportWorkOutcome::success);
  }
  void input(std::uint64_t watermark, std::uint64_t frame, std::uint8_t pad,
             bool pressed, std::uint64_t correlation, std::uint8_t velocity = 90) {
    const auto result = io->execute(work(static_cast<unsigned>(1000 + watermark), {{"op", "admit"}, {"candidate", {
        {"watermark", watermark}, {"frame", frame}, {"bank", 0}, {"pad", pad},
        {"pressed", pressed}, {"velocity", pressed ? velocity : 0}, {"correlation", correlation}}}}));
    LMDJ_CHECK(result.outcome == PatternTransportWorkOutcome::success);
    LMDJ_CHECK(Json::parse(result.payload).at("retained").get<bool>());
  }
  PatternTransportWorkRequest segment(unsigned command, foundation::PatternId target,
                                      std::uint64_t generation, std::uint64_t frame) {
    return work(command, {{"op", "segment"}, {"recording", uuid(3)},
        {"pattern", target.value()}, {"generation", generation}, {"frame", frame}, {"bpm", 120}});
  }
  project_io::ActiveSequenceJournal active() {
    const auto result = journals.read_active(bundle);
    LMDJ_CHECK(result.has_value());
    return result.value();
  }
  domain::ProjectState truth() {
    const auto result = store.load(bundle);
    LMDJ_CHECK(result.has_value());
    return result.value();
  }
  void source() { input(10, 25000, 1, true, 72); }
  void target() {
    input(11, 41000, 1, false, 72); // Old held release cannot create a B press.
    input(12, 46000, 2, true, 80, 95);
    input(13, 58000, 2, false, 80);
  }
  void finish(foundation::PatternId pattern, std::uint64_t generation,
              std::uint64_t origin, std::uint64_t frame) {
    const project_io::SequenceAdmissionFence fence{
        project_io::SequenceFenceKind::cutoff, foundation::CommandId{uuid(500)},
        12, frame, origin, pattern, generation, 120, false, {},
        project_io::SequenceSwitchOutcome::none, {}};
    run(work(501, {{"op", "cutoff"}, {"fence", facade::detail::encode_transport_fence(fence)}}, 12));
    run(work(502, {{"op", "close"}, {"switched", false}}, 12));
    LMDJ_CHECK(!journals.read_active(bundle).has_value());
  }
  void reopened_truth(const std::vector<PatternEvent>& expected_a,
                      const std::vector<PatternEvent>& expected_b, std::uint64_t revision) {
    io.reset();
    const auto loaded = project_io::ProjectStore{platform}.load(bundle);
    if (loaded.has_value() && loaded.value().revision != revision)
      std::cerr << "reopened revision " << loaded.value().revision << " expected " << revision << '\n';
    LMDJ_CHECK(loaded.has_value() && loaded.value().id == project && loaded.value().revision == revision);
    LMDJ_CHECK(loaded.value().patterns.at(a).events == expected_a);
    LMDJ_CHECK(loaded.value().patterns.at(b).events == expected_b);
  }
};

const std::vector<PatternEvent> source_notes{{{0, 1}, 960, 240, 90}};
const std::vector<PatternEvent> target_notes{{{0, 2}, 240, 480, 95}};

void continuous_a_b_a_keeps_full_truth_and_new_generation_clock() {
  Fixture f;
  f.source();
  const auto to_b = f.segment(100, f.b, 22, 40000);
  f.run(to_b);
  LMDJ_CHECK(f.truth().patterns.at(f.a).events == source_notes);
  LMDJ_CHECK(f.truth().patterns.at(f.b).events.empty());
  LMDJ_CHECK(f.active().pattern_id == f.b && f.active().admission->segment_generation == 22);
  const auto segment = f.active();
  const auto& profile = segment.admission->timing_profiles;
  LMDJ_CHECK(profile.size() == 1);
  LMDJ_CHECK(profile[0].pattern_id == f.b && profile[0].publication_generation == 22);
  LMDJ_CHECK(profile[0].runtime_frame == 40000 && profile[0].tick_numerator == 0);
  LMDJ_CHECK(profile[0].first_watermark == 11 && profile[0].expected_revision == 1);
  LMDJ_CHECK(profile[0].bpm == 120 && !profile[0].quantize_enabled && profile[0].swing_percent == 50);
  f.target();
  // Active target is not prematurely flushed: a later release still owns its
  // complete 480-tick duration, rather than an already committed fallback.
  LMDJ_CHECK(f.truth().patterns.at(f.b).events.empty());
  f.run(f.segment(101, f.a, 23, 70000));
  LMDJ_CHECK(f.truth().patterns.at(f.b).events == target_notes);
  auto before = f.active();
  LMDJ_CHECK(before.pattern_id == f.a && before.admission->timing_profiles.back().runtime_frame == 70000);
  auto live_owner = std::move(f.io);
  f.reopen_owner();
  f.run(to_b); // Historical retry does not rewind A to B or alter either Truth.
  LMDJ_CHECK(f.active() == before);
  f.io = std::move(live_owner);
  f.input(14, 76000, 1, true, 90, 100);
  f.input(15, 82000, 1, false, 90);
  f.finish(f.a, 23, 70000, 90000);
  f.reopened_truth({{{0, 1}, 240, 240, 100}, {{0, 1}, 960, 240, 90}}, target_notes, 3);
}

void empty_segments_keep_equal_frontiers_and_no_empty_flushes() {
  Fixture f;
  f.run(f.segment(100, f.b, 22, 40000));
  f.run(f.segment(101, f.a, 23, 70000));
  auto active = f.active();
  LMDJ_CHECK(active.flushes.empty() && active.expected_revision == 0);
  LMDJ_CHECK(active.admission->timing_profiles.size() == 2);
  LMDJ_CHECK(active.admission->timing_profiles[0].first_watermark == 10);
  LMDJ_CHECK(active.admission->timing_profiles[1].first_watermark == 10);
  f.input(10, 76000, 1, true, 90);
  f.input(11, 82000, 1, false, 90);
  f.finish(f.a, 23, 70000, 90000);
  f.reopened_truth({{{0, 1}, 240, 240, 90}}, {}, 1);
}

void durable_partial_steps_replay_original_work_after_owner_reconstruction() {
  for (const auto* kind : {"admission-switch", "admission-transfer", "flush", "manifest", "complete", "switch", "admission-profile"}) {
    for (bool after : {false, true}) {
      Fixture f;
      f.source();
      f.run(f.segment(100, f.b, 22, 40000));
      f.target();
      const auto request = f.segment(101, f.a, 23, 70000);
      f.platform->fault_kind = kind;
      f.platform->after_write = after;
      const auto failed = f.io->execute(request);
      LMDJ_CHECK(f.platform->fault_hit);
      LMDJ_CHECK(failed.outcome == PatternTransportWorkOutcome::unknown);
      f.reopen_owner();
      // Even a readable profile after a lost response cannot ACK while its
      // exact durable replay is still failing to sync.
      if (after && std::string(kind) == "admission-profile") {
        LMDJ_CHECK(f.active().admission->timing_profiles.size() == 2);
        f.platform->fail_sync = true;
        LMDJ_CHECK(f.io->reconcile(request).outcome == PatternTransportWorkOutcome::unknown);
        f.platform->fail_sync = false;
      }
      const auto reconciled = f.io->reconcile(request);
      if (reconciled.error) std::cerr << kind << ' ' << after << ' ' << reconciled.error->message << ' ' << reconciled.error->details.dump() << '\n';
      LMDJ_CHECK(reconciled.outcome == PatternTransportWorkOutcome::success);
      const auto exact = f.active();
      f.run(request);
      LMDJ_CHECK(f.active() == exact);
      LMDJ_CHECK(f.truth().patterns.at(f.a).events == source_notes);
      LMDJ_CHECK(f.truth().patterns.at(f.b).events == target_notes);
      // Reconstructed owner can settle retained operations, but readable
      // opening bytes cannot authorize new live input after producer loss.
      const auto live = f.io->execute(f.work(2000, {{"op", "admit"}, {"candidate", {
          {"watermark", 14}, {"frame", 76000}, {"bank", 0}, {"pad", 1},
          {"pressed", true}, {"velocity", 100}, {"correlation", 90}}}}));
      LMDJ_CHECK(live.outcome == PatternTransportWorkOutcome::success);
      LMDJ_CHECK(!Json::parse(live.payload).at("retained").get<bool>());
      LMDJ_CHECK(f.active() == exact);
      f.finish(f.a, 23, 70000, 90000);
      f.reopened_truth(source_notes, target_notes, 2);
    }
  }
}

void stale_work_or_retroactive_input_cannot_change_segment() {
  for (unsigned mutation = 0; mutation != 6; ++mutation) {
    Fixture f;
    f.source();
    auto request = f.segment(100, f.b, 22, 40000);
    auto payload = Json::parse(request.payload);
    if (mutation == 0) payload["recording"] = uuid(600);
    if (mutation == 1) ++request.identity.runtime_generation;
    if (mutation == 2) ++request.identity.transport_epoch;
    if (mutation == 3) payload["bpm"] = 0;
    if (mutation == 4) f.input(11, 40000, 2, true, 73);
    if (mutation == 5) payload["pattern"] = uuid(999);
    request.payload = payload.dump();
    const auto before = f.active();
    const auto truth = f.truth();
    LMDJ_CHECK(f.io->execute(request).outcome == PatternTransportWorkOutcome::refused);
    LMDJ_CHECK(f.active() == before);
    LMDJ_CHECK(f.truth().revision == truth.revision);
    LMDJ_CHECK(f.truth().patterns == truth.patterns);
  }
  Fixture f;
  f.source();
  const auto original = f.segment(100, f.b, 22, 40000);
  f.run(original);
  const auto before = f.active();
  for (const auto* key : {"frame", "bpm", "generation"}) {
    auto changed = original;
    auto payload = Json::parse(changed.payload);
    payload[key] = payload[key].get<unsigned>() + 1;
    changed.payload = payload.dump();
    LMDJ_CHECK(f.io->execute(changed).outcome == PatternTransportWorkOutcome::refused);
    LMDJ_CHECK(f.active() == before);
  }
}
void changed_project_revision_cannot_become_segment_authority() {
  for (bool unrelated_pending_flush : {false, true}) {
    Fixture f;
    f.source();
    if (unrelated_pending_flush) {
      facade::detail::PatternAdmissionOwner checkpoint{f.journals, f.bundle, f.session};
      LMDJ_CHECK(checkpoint.prepare(f.active().admission->preparation).has_value());
      LMDJ_CHECK(checkpoint.checkpoint_prefix(foundation::CommandId{uuid(700)}).has_value());
    }
    // Settings normally rebase the Journal legitimately. Interrupt precisely
    // that rebase after the real Project commit to create an actual conflict.
    f.platform->fault_kind = "rebase";
    const auto updated = f.store.execute(f.bundle, domain::Command{domain::UpdateSequenceSettings{
        {foundation::CommandId{uuid(600)}, 0}, 130, {}, {}}});
    LMDJ_CHECK(!updated.has_value() && f.platform->fault_hit);
    if (unrelated_pending_flush) {
      const auto stale = f.active();
      // A canonical but uncommitted stale flush is not the receipt responsible
      // for advancing Truth. It must not exempt that unrelated new revision.
      LMDJ_CHECK(f.journals.append_flush(f.bundle, f.session, foundation::CommandId{uuid(701)},
          f.a, stale.expected_revision, stale.pending_events).has_value());
    }
    const auto before = f.active();
    const auto truth = f.truth();
    LMDJ_CHECK(truth.revision == 1);
    const auto denied = f.io->execute(f.segment(100, f.b, 22, 40000));
    LMDJ_CHECK(denied.outcome == PatternTransportWorkOutcome::refused);
    LMDJ_CHECK(f.active() == before);
    LMDJ_CHECK(f.truth().patterns == truth.patterns && f.truth().revision == truth.revision);
  }
}

void legitimate_settings_rebase_preserves_terminal_switch_close() {
  Fixture f;
  f.source();
  LMDJ_CHECK(f.store.execute(f.bundle, domain::Command{domain::UpdateSequenceSettings{
      {foundation::CommandId{uuid(600)}, 0}, 130, {}, {}}}).has_value());
  LMDJ_CHECK(f.truth().revision == 1 && f.active().expected_revision == 1);
  f.target();
  const project_io::SequenceAdmissionFence fence{
      project_io::SequenceFenceKind::cutoff, foundation::CommandId{uuid(500)},
      12, 70000, 40000, f.b, 22, 120, false,
      project_io::SequencePublicationAuthority{f.b, 22, 40000},
      project_io::SequenceSwitchOutcome::applied_before_cutoff, 40000};
  f.run(f.work(501, {{"op", "cutoff"}, {"fence", facade::detail::encode_transport_fence(fence)}}, 12));
  f.run(f.work(502, {{"op", "close"}, {"switched", true}}, 12));
  const auto closed = f.active();
  LMDJ_CHECK(closed.pattern_id == f.b && closed.expected_revision == 3);
  LMDJ_CHECK(closed.admission->closure && !closed.admission->completed);
  // The existing switched-close profile intentionally retains its closed
  // Journal without a terminal transfer. Preserve that separate known debt.
  f.reopened_truth(source_notes, target_notes, 3);
  std::cout << "legitimate settings rebase and terminal switch close: PASS\n";
}

void retained_segment_cell_prevents_close_from_removing_its_journal() {
  Fixture f;
  f.source();
  f.io.reset();
  const auto segment = f.segment(100, f.b, 22, 40000);
  const project_io::SequenceAdmissionFence fence{
      project_io::SequenceFenceKind::cutoff, foundation::CommandId{uuid(500)},
      12, 70000, 40000, f.b, 22, 120, false, {},
      project_io::SequenceSwitchOutcome::none, {}};
  const auto cutoff = f.work(501, {{"op", "cutoff"},
      {"fence", facade::detail::encode_transport_fence(fence)}}, 12);
  const auto close = f.work(502, {{"op", "close"}, {"switched", false}}, 12);
  f.platform->fault_kind = "admission-profile";
  f.platform->after_write = true;
  facade::PatternTransportExecutor executor{7, [config = f.config, platform = f.platform] {
    return std::make_unique<PatternTransportIoOwner>(config, platform, nullptr);
  }};
  const auto wait = [](auto predicate) {
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (!predicate() && std::chrono::steady_clock::now() < until)
      std::this_thread::sleep_for(std::chrono::milliseconds{1});
    LMDJ_CHECK(predicate());
  };
  wait([&] { return executor.inspect().ready; });
  LMDJ_CHECK(executor.submit(segment) == facade::PatternTransportWorkSubmit::accepted);
  wait([&] { return executor.inspect().completion != nullptr; });
  LMDJ_CHECK(executor.inspect().completion->outcome == PatternTransportWorkOutcome::unknown);
  LMDJ_CHECK(executor.inspect().ticket == segment.identity);
  LMDJ_CHECK(executor.submit(close) == facade::PatternTransportWorkSubmit::busy);
  LMDJ_CHECK(f.active().admission->timing_profiles.size() == 1);
  LMDJ_CHECK(executor.reconcile(segment.identity));
  wait([&] { return executor.inspect().completion != nullptr; });
  LMDJ_CHECK(executor.inspect().completion->outcome == PatternTransportWorkOutcome::success);
  LMDJ_CHECK(executor.submit(close) == facade::PatternTransportWorkSubmit::busy);
  LMDJ_CHECK(executor.consume(segment.identity));
  LMDJ_CHECK(!executor.reconcile(segment.identity));
  for (const auto& request : {cutoff, close}) {
    LMDJ_CHECK(executor.submit(request) == facade::PatternTransportWorkSubmit::accepted);
    wait([&] { return executor.inspect().completion != nullptr; });
    LMDJ_CHECK(executor.inspect().completion->outcome == PatternTransportWorkOutcome::success);
    LMDJ_CHECK(executor.consume(request.identity));
  }
  LMDJ_CHECK(!f.journals.read_active(f.bundle).has_value());
  LMDJ_CHECK(!executor.reconcile(segment.identity));
  LMDJ_CHECK(executor.submit(segment) == facade::PatternTransportWorkSubmit::stale);
  executor.request_shutdown();
  wait([&] { return executor.inspect().stopped; });
  f.reopened_truth(source_notes, {}, 1);
}

struct CrashCase { const char* operation; const char* kind; };
constexpr std::array<CrashCase, 16> crash_cases{{
    {"segment", "admission-switch"}, {"segment", "admission-transfer"},
    {"segment", "flush"}, {"segment", "manifest"}, {"segment", "complete"},
    {"segment", "switch"}, {"segment", "admission-profile"},
    {"admit", "admission-candidate"}, {"cutoff", "admission-fence"},
    {"close", "admission-close"}, {"close", "admission-transfer"},
    {"close", "flush"}, {"close", "manifest"}, {"close", "complete"},
    {"close", "admission-complete"}, {"close", "remove"},
}};

PatternTransportWorkRequest cutoff_work(Fixture& f) {
  const project_io::SequenceAdmissionFence fence{
      project_io::SequenceFenceKind::cutoff, foundation::CommandId{uuid(500)},
      12, 100000, 70000, f.a, 23, 120, false, {},
      project_io::SequenceSwitchOutcome::none, {}};
  return f.work(501, {{"op", "cutoff"},
      {"fence", facade::detail::encode_transport_fence(fence)}}, 12);
}

void crash_child(const std::filesystem::path& root, const std::string& operation,
                 const std::string& kind, bool after) {
  LMDJ_CHECK(root.filename().string().starts_with("lmdj-segment-crash-") &&
      std::filesystem::canonical(root.parent_path()) ==
          std::filesystem::canonical(std::filesystem::temp_directory_path()) &&
      std::filesystem::is_directory(root) && !std::filesystem::is_symlink(root));
  Fixture f{root};
  f.source();
  f.run(f.segment(100, f.b, 22, 40000));
  f.target();
  auto request = f.segment(101, f.a, 23, 70000);
  if (operation != "segment") {
    f.run(request);
    if (operation == "admit") {
      request = f.work(2000, {{"op", "admit"}, {"candidate", {
          {"watermark", 14}, {"frame", 76000}, {"bank", 0}, {"pad", 3},
          {"pressed", true}, {"velocity", 100}, {"correlation", 90}}}});
    } else {
      f.input(14, 76000, 3, true, 90, 100);
      f.input(15, 88000, 3, false, 90);
      request = cutoff_work(f);
      if (operation == "close") {
        f.run(request);
        request = f.work(502, {{"op", "close"}, {"switched", false}}, 12);
      } else LMDJ_CHECK(operation == "cutoff");
    }
  }
  f.platform->fault_kind = kind;
  f.platform->after_write = after;
  f.platform->crash_marker = root / "crash-barrier";
  f.platform->crash_label = operation + ":" + kind + (after ? ":after" : ":before");
  (void)f.io->execute(request);
  // Returning normally, an exception, or missing the requested storage call
  // cannot stand in for a process stopped at that exact durable boundary.
  LMDJ_CHECK(false);
}

void cold_recovery_after_real_process_death() {
  std::size_t completed = 0;
  for (const auto& c : crash_cases) for (bool after : {false, true}) {
    struct OwnedDirectory {
      std::filesystem::path path = std::filesystem::temp_directory_path() /
          ("lmdj-segment-crash-" + std::to_string(
              std::chrono::steady_clock::now().time_since_epoch().count()));
      ~OwnedDirectory() { std::error_code ignored; std::filesystem::remove_all(path, ignored); }
    } owned;
    LMDJ_CHECK(std::filesystem::create_directory(owned.path));
    const auto child = test::process::spawn({"--crash-step", owned.path.string(),
        c.operation, c.kind, after ? "after" : "before"});
    int status = 0;
    pid_t observed = 0;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (observed == 0 && std::chrono::steady_clock::now() < deadline) {
      observed = ::waitpid(child, &status, WUNTRACED | WNOHANG);
      if (observed < 0 && errno == EINTR) observed = 0;
      if (observed == 0) std::this_thread::sleep_for(std::chrono::milliseconds{1});
    }
    const bool stopped = observed == child && WIFSTOPPED(status) && WSTOPSIG(status) == SIGSTOP;
    // Reap before asserting so a failed precondition cannot strand a child.
    if (observed == 0 || stopped) {
      LMDJ_CHECK(::kill(child, SIGKILL) == 0);
      pid_t reaped;
      do { reaped = ::waitpid(child, &status, 0); } while (reaped < 0 && errno == EINTR);
      LMDJ_CHECK(reaped == child);
    }
    LMDJ_CHECK(stopped && WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL);
    const std::string label = std::string(c.operation) + ":" + c.kind + (after ? ":after" : ":before");
    std::ifstream marker(owned.path / "crash-barrier");
    LMDJ_CHECK(std::string(std::istreambuf_iterator<char>{marker}, {}) == label);

    const auto bundle = owned.path / "project.lmdj";
    const foundation::PatternId a{uuid(2)}, b{uuid(9)};
    const foundation::SequenceSessionId session{uuid(1)};
    auto expected = domain::create_project(foundation::ProjectId{uuid(4)}, 120).value();
    auto a_events = source_notes;
    const bool terminal = std::string_view(c.operation) == "cutoff" || std::string_view(c.operation) == "close";
    if (terminal || (std::string_view(c.operation) == "admit" && after))
      a_events.insert(a_events.begin(), {{0, 3}, 240, terminal ? 480U : 240U, 100});
    expected.patterns.emplace(a, domain::Pattern{a, 1, a_events});
    expected.patterns.emplace(b, domain::Pattern{b, 1, target_notes});
    expected.revision = a_events.size() == 1 ? 2 : 3;
    const facade::ApplicationConfig config{owned.path, nullptr, {}, {},
        audio::RuntimePreparationLimits{1'048'576, 240'000, 67'108'864, 134'217'728},
        nullptr, nullptr, nullptr, nullptr, facade::make_unavailable_performance_replay_controller()};
    {
      facade::Application recovery{config};
      const auto active_before_listing = project_io::SequenceJournal{}.read_active(bundle);
      const auto listed = recovery.list_sequence_recovery({bundle});
      LMDJ_CHECK(listed.has_value());
      if (listed.value().empty()) {
        LMDJ_CHECK(std::string_view(c.operation) == "close" &&
            ((after && std::string_view(c.kind) == "admission-complete") ||
             std::string_view(c.kind) == "remove"));
        if (std::string_view(c.kind) == "remove" && after) {
          LMDJ_CHECK(!active_before_listing.has_value() &&
              active_before_listing.error().code == foundation::ErrorCode::not_found);
        } else {
          LMDJ_CHECK(active_before_listing.has_value() && active_before_listing.value().admission &&
              active_before_listing.value().admission->completed);
        }
      } else {
        LMDJ_CHECK(listed.value().size() == 1 && listed.value().front().session_id == session);
        LMDJ_CHECK(active_before_listing.has_value() &&
            listed.value().front().pattern_id == active_before_listing.value().pattern_id &&
            listed.value().front().reason == "owner_lost");
        const auto applied = recovery.apply_sequence_recovery({bundle, session, {}});
        if (!applied.has_value()) std::cerr << label << ' ' << applied.error().message << ' '
            << applied.error().details.dump() << '\n';
        LMDJ_CHECK(applied.has_value());
      }
      LMDJ_CHECK(project_io::ProjectStore{}.load(bundle).value() == expected);
      LMDJ_CHECK(recovery.list_sequence_recovery({bundle}).value().empty());
      const auto absent = project_io::SequenceJournal{}.read_active(bundle);
      LMDJ_CHECK(!absent.has_value() && absent.error().code == foundation::ErrorCode::not_found);
    }
    {
      facade::Application reopened{config};
      LMDJ_CHECK(project_io::ProjectStore{}.load(bundle).value() == expected);
      LMDJ_CHECK(reopened.list_sequence_recovery({bundle}).value().empty());
      LMDJ_CHECK(!reopened.apply_sequence_recovery({bundle, session, {}}).has_value());
      LMDJ_CHECK(project_io::ProjectStore{}.load(bundle).value() == expected);
    }
    ++completed;
    std::cout << "cold segment recovery " << label << ": PASS\n";
  }
  LMDJ_CHECK(completed == 32);
  std::cout << "cold segment recovery matrix: PASS (32 actual SIGKILL boundaries)\n";
}

}  // namespace

int main(int argc, char** argv) {
  try {
    lmdj::test::process::initialize(argv[0]);
    if (argc == 6 && std::string_view(argv[1]) == "--crash-step") {
      crash_child(argv[2], argv[3], argv[4], std::string_view(argv[5]) == "after");
      return 1;
    }
    if (argc == 2 && std::string_view(argv[1]) == "--restart") {
      cold_recovery_after_real_process_death();
      return 0;
    }
    LMDJ_CHECK(argc == 1 || (argc == 2 && std::string_view(argv[1]) == "--component"));
    continuous_a_b_a_keeps_full_truth_and_new_generation_clock();
    empty_segments_keep_equal_frontiers_and_no_empty_flushes();
    durable_partial_steps_replay_original_work_after_owner_reconstruction();
    stale_work_or_retroactive_input_cannot_change_segment();
    legitimate_settings_rebase_preserves_terminal_switch_close();
    changed_project_revision_cannot_become_segment_authority();
    retained_segment_cell_prevents_close_from_removing_its_journal();
    if (argc == 1) cold_recovery_after_real_process_death();
    std::cout << "pattern transport segment tests: PASS\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
