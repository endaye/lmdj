#include <lmdj/facade/pattern_transport_controller.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <optional>
#include <source_location>
#include <span>
#include <string>
#include <string_view>
#include <sys/wait.h>
#include <thread>
#include <tuple>
#include <unistd.h>
#include <vector>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/facade/performance_replay.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include "packages/application-facade/internal/lmdj/facade/pattern_transport_controller_factory.hpp"
#include "packages/application-facade/src/pattern_transport_controller.hpp"
#include "packages/application-facade/src/pattern_transport_io_owner.hpp"
#include "packages/application-facade/src/pattern_opening_test_seam.hpp"
#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/child_process.hpp"
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
constexpr auto project = "00000000-0000-4000-8000-000000000004";
constexpr auto pattern = "00000000-0000-4000-8000-000000000002";
std::string uuid(std::uint64_t value) {
  const auto tail = std::to_string(value);
  return "00000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') + tail;
}
template<class Predicate> void wait_for(Predicate predicate,
    std::source_location location = std::source_location::current()) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{3};
  while (!predicate()) {
    if (std::chrono::steady_clock::now() >= deadline) {
      throw std::runtime_error(std::string{location.file_name()} + ":" +
          std::to_string(location.line()) + ": wait_for timed out in " + location.function_name());
    }
    std::this_thread::yield();
  }
}
// Delegates every operation to real storage. Only the selected actual begin or
// admission append import is held; no fake Journal or fabricated IO receipt.
struct Storage final : project_io::ProjectStoragePlatform,
                       project_io::ProjectJournalLayoutValidator,
                       project_io::ProjectStorageTextReader {
  std::shared_ptr<project_io::ProjectStoragePlatform> inner{project_io::make_default_project_storage_platform()};
  mutable std::mutex mutex;
  std::condition_variable cv;
  bool hold_begin{}, hold_append{}, entered{}, released{};
  std::atomic<std::size_t> writes{}, writers{}, leases_destroyed{};
  std::thread::id worker;
  bool observe{};
  struct Lease final : project_io::ProjectWriterLease {
    Storage& storage;
    std::unique_ptr<project_io::ProjectWriterLease> owned;
    std::thread::id thread;
    Lease(Storage& owner, std::unique_ptr<project_io::ProjectWriterLease> lease)
        : storage(owner), owned(std::move(lease)), thread(std::this_thread::get_id()) {}
    ~Lease() override {
      LMDJ_CHECK(std::this_thread::get_id() == thread);
      owned.reset();
      ++storage.leases_destroyed;
    }
  };
  void arm(bool begin) {
    std::lock_guard lock(mutex);
    hold_begin = begin; hold_append = !begin; entered = released = false;
  }
  void release() { std::lock_guard lock(mutex); released = true; cv.notify_all(); }
  void gate(bool begin) {
    std::unique_lock lock(mutex);
    if (!(begin ? hold_begin : hold_append)) return;
    entered = true;
    cv.notify_all();
    cv.wait(lock, [&] { return released; });
    hold_begin = hold_append = false;
  }
  bool is_entered() const { std::lock_guard lock(mutex); return entered; }
  foundation::Result<std::unique_ptr<project_io::ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override {
    auto result = inner->acquire_writer(p);
    if (!result.has_value() || !observe) return result;
    if (worker == std::thread::id{}) worker = std::this_thread::get_id();
    LMDJ_CHECK(worker == std::this_thread::get_id());
    ++writers;
    std::unique_ptr<project_io::ProjectWriterLease> lease = std::make_unique<Lease>(*this, std::move(result.value()));
    return foundation::Result<std::unique_ptr<project_io::ProjectWriterLease>>::success(std::move(lease));
  }
  foundation::Result<void> ensure_directory(const std::filesystem::path& p) override { return inner->ensure_directory(p); }
  foundation::Result<bool> exists(const std::filesystem::path& p) const override { return inner->exists(p); }
  foundation::Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override { return inner->byte_length(p); }
  foundation::Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override {
    auto result = inner->read_complete(p);
    return result;
  }
  foundation::Result<std::string> read_complete_text(const std::filesystem::path& p) const override {
    const auto* reader = dynamic_cast<const project_io::ProjectStorageTextReader*>(inner.get());
    LMDJ_CHECK(reader != nullptr);
    auto result = reader->read_complete_text(p);
    return result;
  }
  foundation::Result<void> create_immutable(const std::filesystem::path& p, std::span<const std::byte> bytes) override {
    if (observe) ++writes;
    if (p.filename() == "sequence.jsonl") gate(true);
    return inner->create_immutable(p, bytes);
  }
  foundation::Result<void> replace_complete(const std::filesystem::path& p, std::span<const std::byte> bytes) override {
    if (observe) ++writes;
    return inner->replace_complete(p, bytes);
  }
  foundation::Result<void> append_durable(const std::filesystem::path& p, std::uint64_t prefix,
                                         std::span<const std::byte> bytes) override {
    if (observe) ++writes;
    const auto text = std::string(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    if (p.filename() == "sequence.jsonl" && text.find("admission-candidate") != std::string::npos) gate(false);
    return inner->append_durable(p, prefix, bytes);
  }
  foundation::Result<void> remove(const std::filesystem::path& p) override { if (observe) ++writes; return inner->remove(p); }
  foundation::Result<std::vector<std::string>> list_names(const std::filesystem::path& p) const override { return inner->list_names(p); }
  foundation::Result<std::vector<std::string>> list_directories(const std::filesystem::path& p) const override { return inner->list_directories(p); }
  foundation::Result<void> remove_tree(const std::filesystem::path& p) override { return inner->remove_tree(p); }
  foundation::Result<bool> directory_exists(const std::filesystem::path& p) const override { return inner->directory_exists(p); }
  foundation::Result<void> validate_managed_tree(const std::filesystem::path& p) const override { return inner->validate_managed_tree(p); }
  foundation::Result<void> validate_journal_layout(const std::filesystem::path& p) const override {
    const auto* layout = dynamic_cast<const project_io::ProjectJournalLayoutValidator*>(inner.get());
    LMDJ_CHECK(layout != nullptr);
    return layout->validate_journal_layout(p);
  }
};
struct Port final : facade::PatternTransportAudioPort, facade::ScheduledPatternTransportAudioPort {
  audio::RealtimeEngine engine;
  unsigned ordinary_ack_calls{}, scheduled_ack_calls{}, ordinary_submit_calls{};
  std::optional<audio::PatternTransportSubmit> ordinary_submit_result;
  explicit Port(std::uint16_t bpm = 120) {
    LMDJ_CHECK(engine.enable_pattern_transport(7).has_value());
    LMDJ_CHECK(engine.enable_scheduled_pattern_record(7).has_value());
    LMDJ_CHECK(engine.enable_pattern_input_profile(7).has_value());
    auto sample = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(128, 1000)});
    cooker::RuntimeSnapshot snapshot{foundation::ProjectId{project}, foundation::PatternId{pattern}, 1,
        bpm, 1, domain::kPpq, domain::kBarTicks4x4, {}, {}};
    for (std::uint8_t bank = 0; bank != 4; ++bank) for (std::uint8_t pad = 0; pad != 16; ++pad)
      snapshot.pads.emplace_back(domain::PadSlotId{bank, pad},
          foundation::ArtifactRef{std::string(64, 'a'), "audio/wav", 256}, sample,
          cooker::ResolvedPlayback{0, 128, domain::TriggerMode::loop_gate, 1.0F, false});
    auto prepared = audio::PreparedSampleBank::from_snapshot(snapshot);
    auto view = audio::PreparedPatternView::from_snapshot(snapshot);
    LMDJ_CHECK(prepared.has_value() && view.has_value());
    LMDJ_CHECK(engine.publish_sample_bank(std::move(prepared.value())) == audio::PublishResult::accepted);
    LMDJ_CHECK(engine.publish_pattern_view(std::move(view.value())).result == audio::PatternPublishResult::accepted);
    LMDJ_CHECK(engine.start().has_value());
    render(1);
  }
  audio::PatternTransportSubmit submit(const audio::PatternTransportCommand& c) override {
    ++ordinary_submit_calls;
    ordinary_submit_result = engine.submit_pattern_transport(c);
    return *ordinary_submit_result;
  }
  std::optional<audio::PatternTransportReceipt> inspect(std::uint64_t g, std::uint64_t e) const override { return engine.inspect_pattern_transport_receipt(g, e); }
  bool acknowledge(std::uint64_t g, std::uint64_t e) override { ++ordinary_ack_calls; return engine.acknowledge_pattern_transport_receipt(g, e); }
  std::uint64_t pattern_generation() const override { return engine.pattern_telemetry().current_generation; }
  std::optional<audio::PatternReplacementAuthority> pending_switch() const override { return {}; }
  std::optional<foundation::PatternId> current_pattern() const override { return engine.current_pattern_id(); }
  audio::ScheduledPatternSubmit submit_scheduled(const audio::ScheduledPatternRecordRequest& r) override { return engine.submit_scheduled_pattern_record(r); }
  std::optional<audio::ScheduledPatternRecordStatus> inspect_scheduled(std::uint64_t g, std::uint64_t s) const override { return engine.inspect_scheduled_pattern_record(g, s); }
  audio::ScheduledPatternSubmit cancel_scheduled(const audio::ScheduledPatternCancelRequest& r) override { return engine.cancel_scheduled_pattern_record(r); }
  bool acknowledge_scheduled(std::uint64_t g, std::uint64_t s, std::uint64_t e) override { ++scheduled_ack_calls; return engine.acknowledge_scheduled_pattern_record(g, s, e); }
  bool scheduled_quiescent() const override { return engine.scheduled_pattern_record_quiescent(); }
  void render(std::uint64_t frames) {
    std::array<float, 128> left{}, right{};
    while (frames) {
      const auto block = static_cast<std::uint32_t>(std::min<std::uint64_t>(frames, left.size()));
      engine.render(left.data(), right.data(), block);
      audio::CountInCueBatch cues;
      if (engine.take_count_in_cue_batch_audio(cues)) LMDJ_CHECK(engine.acknowledge_count_in_cue_batch_audio(cues.batch_id));
      frames -= block;
    }
  }
};
struct Fixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-count-in-facade-" + std::to_string(::getpid()) + "-" +
       std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path bundle = root / "project.lmdj";
  std::shared_ptr<Storage> storage = std::make_shared<Storage>();
  Port port;
  std::unique_ptr<facade::PatternTransportController> controller;
  domain::ProjectState initial;
  explicit Fixture(std::uint16_t bpm = 120) : port(bpm),
      initial(std::move(domain::create_project(foundation::ProjectId{project}, bpm).value())) {
    initial.patterns.emplace(foundation::PatternId{pattern}, domain::Pattern{foundation::PatternId{pattern}, 1, {}});
    project_io::ProjectStore store(storage);
    LMDJ_CHECK(store.create(bundle, initial).has_value());
    storage->observe = true;
    controller = facade::detail::PatternTransportControllerInternalFactory::make(port,
        {bundle, foundation::SequenceSessionId{uuid(1)}, foundation::ProjectId{project}, foundation::PatternId{pattern}, 7},
        storage, {}, {}, &port);
    wait_for([&] { return controller->inspect_io().ready; });
  }
  ~Fixture() {
    storage->release();
    controller.reset();
    std::error_code ignored;
    std::filesystem::remove_all(root, ignored);
  }
  facade::PatternTransportRequest request(unsigned id, std::uint64_t epoch, facade::PatternTransportIntent intent) const {
    return {foundation::SequenceSessionId{uuid(1)}, foundation::ProjectId{project}, foundation::CommandId{uuid(id)}, 7, epoch, intent, 0};
  }
  facade::ScheduledPatternTransportRequest schedule(std::uint8_t bars = 1) const {
    return {request(2, 1, facade::PatternTransportIntent::record), port.engine.telemetry().start_epoch, 1, bars};
  }
  void tick() { static_cast<void>(controller->continue_operation()); }
  void settled() { wait_for([&] { tick(); return controller->inspect().phase == facade::PatternTransportPhase::idle; }); }
  void start() {
    LMDJ_CHECK(controller->request_count_in(schedule()) == facade::PatternTransportSubmit::accepted);
    port.render(1);
    tick();
    const auto armed = controller->inspect_count_in();
    LMDJ_CHECK(armed.count_in && armed.count_in->start_frame);
    port.render(*armed.count_in->start_frame - port.engine.telemetry().rendered_frames + 1);
    wait_for([&] { tick(); return controller->inspect_count_in().opening_complete; });
    LMDJ_CHECK(controller->inspect().recording);
  }
  std::pair<facade::PatternTransportInputTicket, audio::PatternInputAdmission> input(
      unsigned id, std::uint8_t slot, bool press, std::uint64_t correlation = 0, bool muted = true,
      domain::TriggerMode mode = domain::TriggerMode::loop_gate) {
    const facade::PatternTransportInputRequest r{foundation::CommandId{uuid(id)}, 7, port.engine.telemetry().start_epoch,
        port.engine.telemetry().rendered_frames, {static_cast<std::uint8_t>(slot / 16), static_cast<std::uint8_t>(slot % 16)},
        press, static_cast<std::uint8_t>(press ? 90 : 0), correlation, true};
    const auto ticket = controller->reserve_input(r);
    LMDJ_CHECK(ticket.has_value());
    audio::PatternInputCommand command{7, r.frame_epoch, slot, r.velocity, !press, correlation, true,
        cooker::ResolvedPlayback{0, 128, mode, 1.0F, muted}};
    const auto accepted = port.engine.enqueue_pattern_input(command);
    LMDJ_CHECK(accepted.result == audio::PatternInputSubmit::accepted);
    LMDJ_CHECK(controller->bind_input(ticket.value(), accepted));
    return {ticket.value(), accepted};
  }
  void native_complete(const facade::PatternTransportInputTicket& ticket, const audio::PatternInputAdmission& a) {
    const auto completion = port.engine.inspect_pattern_input_completion(7, port.engine.telemetry().start_epoch, a.sequence);
    LMDJ_CHECK(completion);
    LMDJ_CHECK(controller->complete_input(*completion));
    LMDJ_CHECK(!controller->consume_input(ticket));
  }
  void input_settled(const facade::PatternTransportInputTicket& ticket, const audio::PatternInputAdmission& a) {
    wait_for([&] { tick(); const auto status = controller->inspect_input(ticket); return status && status->complete; });
    const auto status = controller->inspect_input(ticket);
    LMDJ_CHECK(status->native_result && status->durable_settled && !status->error);
    LMDJ_CHECK(port.engine.consume_pattern_input_completion(7, port.engine.telemetry().start_epoch, a.sequence));
    LMDJ_CHECK(controller->consume_input(ticket));
    LMDJ_CHECK(!controller->consume_input(ticket));
  }
};
void winning_cancel_has_no_storage_or_truth_effect() {
  Fixture f;
  const auto before_writes = f.storage->writes.load();
  const auto before_writers = f.storage->writers.load();
  const auto schedule = f.schedule(2);
  LMDJ_CHECK(f.controller->request_count_in(schedule) == facade::PatternTransportSubmit::accepted);
  LMDJ_CHECK(!f.controller->inspect_count_in().count_in);
  f.port.render(1);
  f.tick();
  LMDJ_CHECK(f.controller->inspect_count_in().count_in->start_frame);
  LMDJ_CHECK(f.storage->writes == before_writes && f.storage->writers == before_writers);
  const facade::ScheduledPatternTransportCancel cancel{f.request(3, 2, facade::PatternTransportIntent::play_stop), schedule.frame_epoch, 1};
  LMDJ_CHECK(f.controller->cancel_count_in(cancel) == facade::PatternTransportSubmit::accepted);
  f.settled();
  const auto status = f.controller->inspect_count_in();
  LMDJ_CHECK(status.start_receipt && status.start_receipt->result == audio::ScheduledPatternResult::cancelled);
  LMDJ_CHECK(!status.opening_complete && !f.controller->inspect().playing);
  LMDJ_CHECK(f.storage->writes == before_writes && f.storage->writers == before_writers);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  project_io::SequenceJournal journals(f.storage->inner);
  LMDJ_CHECK(!journals.read_active(f.bundle).has_value());
}
void refused_before_start_settles_native_without_storage_work() {
  Fixture f;
  const auto writes = f.storage->writes.load();
  const auto writers = f.storage->writers.load();
  LMDJ_CHECK(f.controller->request_count_in(f.schedule()) == facade::PatternTransportSubmit::accepted);
  f.port.engine.stop();
  f.tick();
  const auto refused = f.controller->inspect_count_in();
  LMDJ_CHECK(refused.start_receipt && refused.start_receipt->result == audio::ScheduledPatternResult::refused);
  LMDJ_CHECK(!refused.start_receipt->effective_frame && !refused.start_receipt->origin_frame);
  LMDJ_CHECK(refused.error && !refused.opening_pending && !refused.opening_complete);
  LMDJ_CHECK(f.port.scheduled_quiescent());
  LMDJ_CHECK(f.storage->writes == writes && f.storage->writers == writers);
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  project_io::SequenceJournal journal(f.storage->inner);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
}
void completed_opening_retains_the_count_in_lineage_until_a_later_real_cutoff() {
  Fixture f;
  f.start();
  for (unsigned turn = 0; turn != 16; ++turn) f.tick();
  const auto opened = f.controller->inspect_count_in();
  LMDJ_CHECK(opened.opening_complete && opened.start_receipt && !opened.cancel_receipt);
  LMDJ_CHECK(opened.start_receipt->result == audio::ScheduledPatternResult::applied);
  LMDJ_CHECK(opened.start_receipt->effective_frame == 96'001 && opened.start_receipt->origin_frame == 96'001);
  LMDJ_CHECK(f.controller->inspect().recording && f.controller->inspect().phase == facade::PatternTransportPhase::idle);
  const auto native = f.port.inspect_scheduled(7, 1);
  LMDJ_CHECK(native && native->start_receipt && native->start_receipt->result == audio::ScheduledPatternResult::applied);
  LMDJ_CHECK(!f.port.scheduled_quiescent());
  f.port.render(24'000);
  const facade::ScheduledPatternTransportCancel cancel{
      f.request(3, 2, facade::PatternTransportIntent::play_stop), f.schedule().frame_epoch, 1};
  LMDJ_CHECK(f.controller->cancel_count_in(cancel) == facade::PatternTransportSubmit::accepted);
  f.tick();
  LMDJ_CHECK(!f.controller->inspect_count_in().cancel_receipt);
  f.port.render(1);
  f.settled();
  const auto closed = f.controller->inspect_count_in();
  LMDJ_CHECK(closed.start_receipt && closed.cancel_receipt && !closed.error);
  LMDJ_CHECK(closed.start_receipt->effective_frame == 96'001 && closed.start_receipt->origin_frame == 96'001);
  LMDJ_CHECK(closed.cancel_receipt->result == audio::ScheduledPatternResult::applied);
  LMDJ_CHECK(closed.cancel_receipt->epoch == 2 && closed.cancel_receipt->effective_frame == 120'002);
  LMDJ_CHECK(closed.cancel_receipt->origin_frame == 96'001 && !closed.cancel_receipt->playing);
  LMDJ_CHECK(!f.controller->inspect().recording && !f.controller->inspect().playing);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  LMDJ_CHECK(!project_io::SequenceJournal{f.storage->inner}.read_active(f.bundle).has_value());
  LMDJ_CHECK(f.port.scheduled_quiescent());
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
}

void held_begin_retains_actual_start_and_stop() {
  Fixture f;
  f.storage->arm(true);
  LMDJ_CHECK(f.controller->request_count_in(f.schedule()) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.tick();
  const auto s = *f.controller->inspect_count_in().count_in->start_frame;
  f.port.render(s - f.port.engine.telemetry().rendered_frames + 1);
  wait_for([&] { f.tick(); return f.storage->is_entered(); });
  const auto status = f.controller->inspect_count_in();
  LMDJ_CHECK(status.start_receipt && *status.start_receipt->effective_frame == s && status.opening_pending);
  for (unsigned n = 0; n != 20; ++n) { f.tick(); LMDJ_CHECK(f.controller->inspect_count_in().opening_pending); }
  const auto cancel = facade::ScheduledPatternTransportCancel{f.request(3, 2, facade::PatternTransportIntent::play_stop), f.schedule().frame_epoch, 1};
  LMDJ_CHECK(f.controller->cancel_count_in(cancel) == facade::PatternTransportSubmit::accepted);
  f.tick(); f.port.render(1); f.tick();
  LMDJ_CHECK(!f.controller->inspect().playing);
  LMDJ_CHECK(f.controller->inspect_count_in().start_receipt->result == audio::ScheduledPatternResult::applied);
  f.storage->release(); f.settled();
  LMDJ_CHECK(!f.controller->inspect().recording);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
}
void silent_press_ticket_consumption_preserves_release_and_actual_duration() {
  Fixture f;
  f.start();
  auto press = f.input(10, 1, true);
  f.port.render(1);
  f.native_complete(press.first, press.second);
  f.input_settled(press.first, press.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);
  f.port.render(24'000); // 120 BPM / 48 kHz: 960 ticks, not default 240
  f.storage->arm(false);
  auto release = f.input(11, 1, false, press.second.sequence);
  f.port.render(1);
  f.native_complete(release.first, release.second);
  wait_for([&] { f.tick(); return f.storage->is_entered(); });
  LMDJ_CHECK(!f.controller->inspect_input(release.first)->complete);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
  LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::record)) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.tick();
  LMDJ_CHECK(f.controller->inspect().playing); // Record-off retains playback
  f.storage->release();
  f.input_settled(release.first, release.second);
  f.settled();
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
  LMDJ_CHECK(!f.controller->inspect().recording);
  project_io::ProjectStore reader(f.storage->inner);
  const auto reopened = reader.load(f.bundle);
  LMDJ_CHECK(reopened.has_value() && reopened.value().revision == 1);
  const auto& events = reopened.value().patterns.at(foundation::PatternId{pattern}).events;
  LMDJ_CHECK((events.size() == 1 && events[0].slot == domain::PadSlotId{0, 1}));
  LMDJ_CHECK(events[0].onset_tick == 0 && events[0].duration_tick == 960 && events[0].velocity == 90);
  auto expected = f.initial;
  expected.revision = 1;
  expected.patterns.at(foundation::PatternId{pattern}).events = events;
  LMDJ_CHECK(reopened.value() == expected); // complete Truth, not event-count prefix
  project_io::SequenceJournal journal(f.storage->inner);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
  LMDJ_CHECK(f.controller->request(f.request(4, 3, facade::PatternTransportIntent::play_stop)) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.settled();
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.storage->worker != std::this_thread::get_id());
  LMDJ_CHECK(f.storage->writers == f.storage->leases_destroyed);
}
void independent_metadata_partitions_keep_reserved_release_available() {
  Fixture f;
  f.start();
  auto held = f.input(10, 0, true);
  f.port.render(1); f.native_complete(held.first, held.second); f.input_settled(held.first, held.second);
  f.port.render(24'000); // Keep the saturated hold's real duration distinct from its default.
  f.storage->arm(false);
  std::vector<std::pair<facade::PatternTransportInputTicket, audio::PatternInputAdmission>> pending;
  // Fill ordinary metadata using unheld presses so physical held-release FIFO
  // pressure is a different resource. Hold the first actual durable append.
  for (std::size_t n = 0; n != facade::kPatternTransportIngressCapacity; ++n) {
    facade::PatternTransportInputRequest r{foundation::CommandId{uuid(100 + n)}, 7, f.port.engine.telemetry().start_epoch,
        f.port.engine.telemetry().rendered_frames, {0, 1}, true, 90, 0, false};
    const auto ticket = f.controller->reserve_input(r);
    LMDJ_CHECK(ticket.has_value());
    auto admission = f.port.engine.enqueue_pattern_input({7, r.frame_epoch, 1, 90, false, 0, false,
        cooker::ResolvedPlayback{0, 128, domain::TriggerMode::loop_gate, 1.0F, true}});
    LMDJ_CHECK(admission.result == audio::PatternInputSubmit::accepted);
    LMDJ_CHECK(f.controller->bind_input(ticket.value(), admission));
    f.port.render(1); f.native_complete(ticket.value(), admission);
    pending.emplace_back(ticket.value(), admission);
    f.tick();
    if (n == 0) {
      wait_for([&] { f.tick(); return f.storage->is_entered(); });
    }
  }
  LMDJ_CHECK(f.controller->inspect_ingress().ordinary_pending == facade::kPatternTransportIngressCapacity);
  const auto refused = f.controller->reserve_input({foundation::CommandId{uuid(9999)}, 7, f.port.engine.telemetry().start_epoch,
      f.port.engine.telemetry().rendered_frames, {0, 2}, true, 90, 0, false});
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().details.at("reason") == "pattern_transport_metadata_full");
  const auto release = f.input(11, 0, false, held.second.sequence);
  f.port.render(1); f.native_complete(release.first, release.second);
  LMDJ_CHECK(f.controller->inspect_input(release.first)->admission->acceptance_ordinal > pending.back().second.acceptance_ordinal);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
  f.storage->release();
  for (const auto& input : pending) {
    f.input_settled(input.first, input.second);
  }
  f.input_settled(release.first, release.second);
  LMDJ_CHECK(f.controller->inspect_ingress().ordinary_pending == 0);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::play_stop)) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.settled();
  project_io::ProjectStore reader(f.storage->inner);
  const auto reopened = reader.load(f.bundle);
  LMDJ_CHECK(reopened.has_value() && reopened.value().revision == 1);
  const auto& events = reopened.value().patterns.at(foundation::PatternId{pattern}).events;
  const auto retained_hold = std::find_if(events.begin(), events.end(), [](const auto& e) {
    return e.slot == domain::PadSlotId{0, 0};
  });
  LMDJ_CHECK(retained_hold != events.end());
  LMDJ_CHECK(retained_hold->duration_tick == 960 + (facade::kPatternTransportIngressCapacity + 2) / 25);
  LMDJ_CHECK(retained_hold->duration_tick != domain::kSixteenthTicks);
  auto expected = f.initial;
  expected.revision = 1;
  expected.patterns.at(foundation::PatternId{pattern}).events = events;
  LMDJ_CHECK(reopened.value() == expected);
  project_io::SequenceJournal journal(f.storage->inner);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
}

void toggle_stopped_press_consumption_preserves_both_real_releases() {
  Fixture f;
  f.start();
  const auto first = f.input(10, 2, true, 0, false, domain::TriggerMode::loop_toggle);
  f.port.render(1); f.native_complete(first.first, first.second);
  LMDJ_CHECK(f.controller->inspect_input(first.first)->native_result->disposition == audio::PatternInputDisposition::voice_started);
  f.input_settled(first.first, first.second);
  f.port.render(24'000);
  const auto second = f.input(11, 2, true, 0, false, domain::TriggerMode::loop_toggle);
  f.port.render(1); f.native_complete(second.first, second.second);
  LMDJ_CHECK(f.controller->inspect_input(second.first)->native_result->disposition == audio::PatternInputDisposition::toggle_stopped);
  f.input_settled(second.first, second.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 2);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 2);
  const auto first_release = f.input(12, 2, false, first.second.sequence);
  f.port.render(1); f.native_complete(first_release.first, first_release.second);
  f.input_settled(first_release.first, first_release.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
  f.port.render(24'000);
  const auto second_release = f.input(13, 2, false, second.second.sequence);
  f.port.render(1); f.native_complete(second_release.first, second_release.second);
  f.input_settled(second_release.first, second_release.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
  LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::play_stop)) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.settled();
  project_io::ProjectStore reader(f.storage->inner);
  const auto reopened = reader.load(f.bundle);
  LMDJ_CHECK(reopened.has_value() && reopened.value().revision == 1);
  const auto& events = reopened.value().patterns.at(foundation::PatternId{pattern}).events;
  LMDJ_CHECK(events == std::vector<domain::PatternEvent>({{{0, 2}, 0, 960, 90}, {{0, 2}, 960, 960, 90}}));
  auto expected = f.initial;
  expected.revision = 1;
  expected.patterns.at(foundation::PatternId{pattern}).events = events;
  LMDJ_CHECK(reopened.value() == expected);
  project_io::SequenceJournal journal(f.storage->inner);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
}

void post_open_owner_invalidation_preserves_prefix_until_real_recovery() {
  Fixture f;
  f.start();
  const auto press = f.input(10, 1, true);
  f.port.render(1); f.native_complete(press.first, press.second); f.input_settled(press.first, press.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
  f.port.engine.stop();
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.controller->inspect().error &&
      f.controller->inspect().error->details.at("reason") == "pattern_transport_owner_invalidated");
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  // Authoring disposition cannot spend the independent native physical hold.
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);
  project_io::SequenceJournal journal(f.storage->inner);
  const auto retained = journal.read_active(f.bundle);
  LMDJ_CHECK(retained.has_value() && retained.value().state == project_io::SequenceSessionState::owner_lost);
  LMDJ_CHECK(retained.value().admission && !retained.value().admission->cutoff_fence);
  LMDJ_CHECK(retained.value().admission->candidates.size() == 1);
  LMDJ_CHECK(retained.value().admission->candidates[0].press_sequence == press.second.sequence);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  facade::ApplicationConfig config{};
  config.workspace_root = f.root;
  config.storage_platform = f.storage->inner;
  config.performance_replay_controller = facade::make_unavailable_performance_replay_controller();
  facade::Application application{std::move(config)};
  const auto recovery = application.list_sequence_recovery({f.bundle});
  LMDJ_CHECK(recovery.has_value() && recovery.value().size() == 1 && recovery.value()[0].reason == "owner_lost");
  LMDJ_CHECK(application.apply_sequence_recovery({f.bundle, foundation::SequenceSessionId{uuid(1)}, {}}).has_value());
  auto expected = f.initial;
  expected.revision = 1;
  expected.patterns.at(foundation::PatternId{pattern}).events = {{{0, 1}, 0, 240, 90}};
  LMDJ_CHECK(reader.load(f.bundle).value() == expected);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
  LMDJ_CHECK(f.port.engine.revoke_pattern_input_holds_quiescent(7));
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
}

void shutdown_preserves_only_owned_live_releases_until_acknowledged() {
  Fixture f;
  const auto press = f.input(10, 1, true);
  f.port.render(1);
  f.native_complete(press.first, press.second);
  f.input_settled(press.first, press.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);
  f.controller->request_shutdown();
  for (unsigned n = 0; n != 20; ++n) {
    f.tick();
    LMDJ_CHECK(!f.controller->shutdown_complete());
    LMDJ_CHECK(!f.controller->inspect_io().shutdown_requested);
  }
  facade::PatternTransportInputRequest r{foundation::CommandId{uuid(11)}, 7,
      f.port.engine.telemetry().start_epoch, f.port.engine.telemetry().rendered_frames,
      {0, 1}, false, 0, press.second.sequence, true};
  auto bad = r;
  bad.command_id = foundation::CommandId{uuid(12)};
  bad.pressed = true;
  bad.velocity = 90;
  bad.correlation = 0;
  LMDJ_CHECK(!f.controller->reserve_input(bad).has_value());
  bad = r;
  bad.slot = {0, 2};
  LMDJ_CHECK(!f.controller->reserve_input(bad).has_value());
  bad = r;
  bad.correlation = press.second.sequence + 1;
  LMDJ_CHECK(!f.controller->reserve_input(bad).has_value());
  const auto ticket = f.controller->reserve_input(r);
  LMDJ_CHECK(ticket.has_value());
  LMDJ_CHECK(f.controller->reserve_input(r).value() == ticket.value());
  bad = r;
  ++bad.runtime_frame;
  LMDJ_CHECK(!f.controller->reserve_input(bad).has_value());
  const auto release = f.input(11, 1, false, press.second.sequence);
  LMDJ_CHECK(release.first == ticket.value());
  f.port.render(1);
  f.native_complete(release.first, release.second);
  wait_for([&] { f.tick(); return f.controller->inspect_input(release.first)->complete; });
  LMDJ_CHECK(f.controller->inspect_input(release.first)->durable_settled);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);
  // Completion is not acknowledgment: the exact ticket must remain inspectable.
  for (unsigned n = 0; n != 20; ++n) {
    f.tick();
    LMDJ_CHECK(!f.controller->shutdown_complete());
    LMDJ_CHECK(f.controller->inspect_input(release.first));
  }
  f.input_settled(release.first, release.second);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 0);
  LMDJ_CHECK(!f.controller->reserve_input(r).has_value());
}

void pre_start_press_and_post_start_release_stay_live_only() {
  Fixture f;
  const auto schedule = f.schedule();
  LMDJ_CHECK(f.controller->request_count_in(schedule) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.tick();
  const auto s = *f.controller->inspect_count_in().count_in->start_frame;
  auto press = f.input(10, 1, true);
  LMDJ_CHECK((press.second.authority == audio::PatternInputAuthority{}));
  f.port.render(1); f.native_complete(press.first, press.second);
  f.input_settled(press.first, press.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);
  f.port.render(s - f.port.engine.telemetry().rendered_frames + 1);
  wait_for([&] { f.tick(); return f.controller->inspect_count_in().opening_complete; });
  auto release = f.input(11, 1, false, press.second.sequence);
  f.port.render(1); f.native_complete(release.first, release.second);
  f.input_settled(release.first, release.second);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
  LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::play_stop)) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.settled();
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  project_io::SequenceJournal journal(f.storage->inner);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
}
void two_bars_at_40_bpm_do_not_spend_the_opening_budget_before_s() {
  Fixture f(40);
  const auto writes = f.storage->writes.load();
  LMDJ_CHECK(f.controller->request_count_in(f.schedule(2)) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.tick();
  const auto count = *f.controller->inspect_count_in().count_in;
  LMDJ_CHECK(count.count_in_frame && count.start_frame && count.bar_frames == 288'000);
  LMDJ_CHECK(*count.start_frame == *count.count_in_frame + 576'000); // literal 12-second native span
  f.port.render(*count.start_frame - f.port.engine.telemetry().rendered_frames);
  f.tick();
  LMDJ_CHECK(!f.controller->inspect_count_in().opening_pending);
  LMDJ_CHECK(!f.controller->inspect().recording && f.storage->writes == writes);
  f.port.render(1);
  wait_for([&] { f.tick(); return f.controller->inspect_count_in().opening_complete; });
  LMDJ_CHECK(!f.controller->inspect_count_in().error);
  LMDJ_CHECK(*f.controller->inspect_count_in().start_receipt->effective_frame == *count.start_frame);
  LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::play_stop)) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.settled();
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
}
void expired_press_keeps_its_exact_work_and_future_release() {
  Fixture f;
  f.start();
  f.storage->arm(false);
  auto press = f.input(10, 1, true);
  f.port.render(1); f.native_complete(press.first, press.second);
  wait_for([&] { f.tick(); return f.storage->is_entered(); });
  const auto work = f.controller->inspect_io().ticket;
  LMDJ_CHECK(work);
  std::this_thread::sleep_for(facade::kPatternTransportInputDeadline + std::chrono::milliseconds{1});
  for (unsigned n = 0; n != 20; ++n) {
    f.tick();
    LMDJ_CHECK(f.controller->inspect_io().ticket == work);
    const auto status = f.controller->inspect_input(press.first);
    LMDJ_CHECK(status && status->expired && !status->complete);
    LMDJ_CHECK(!f.controller->consume_input(press.first));
  }
  f.storage->release();
  f.input_settled(press.first, press.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
  auto release = f.input(11, 1, false, press.second.sequence);
  f.port.render(1); f.native_complete(release.first, release.second);
  f.input_settled(release.first, release.second);
  LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::play_stop)) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.settled();
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value().revision == 1);
}

void opening_expiry_retains_e1_and_uses_a_real_stop() {
  Fixture f;
  f.storage->arm(true);
  LMDJ_CHECK(f.controller->request_count_in(f.schedule()) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.tick();
  const auto s = *f.controller->inspect_count_in().count_in->start_frame;
  f.port.render(s - f.port.engine.telemetry().rendered_frames + 1);
  wait_for([&] { f.tick(); return f.storage->is_entered(); });
  const auto work = f.controller->inspect_io().ticket;
  std::this_thread::sleep_for(facade::kScheduledPatternOpeningDeadline + std::chrono::milliseconds{1});
  f.tick();
  LMDJ_CHECK(f.controller->inspect_io().ticket == work);
  const auto expired = f.controller->inspect_count_in();
  LMDJ_CHECK(expired.error && expired.error->details.at("reason") == "pattern_transport_opening_expired");
  LMDJ_CHECK(expired.start_receipt->result == audio::ScheduledPatternResult::applied);
  LMDJ_CHECK(*expired.start_receipt->effective_frame == s);
  f.tick();
  const auto expected_stop_frame = f.port.engine.telemetry().rendered_frames;
  f.port.render(1); f.tick();
  LMDJ_CHECK(!f.controller->inspect().playing);
  LMDJ_CHECK(f.controller->inspect_io().ticket == work);
  f.storage->release();
  wait_for([&] {
    f.tick();
    return f.controller->inspect().phase == facade::PatternTransportPhase::error &&
        !f.controller->inspect_io().ticket && !f.controller->inspect_io().completion;
  });
  const auto refused = f.controller->inspect_count_in();
  LMDJ_CHECK(refused.error && refused.error->details.at("reason") == "admission_opening_deadline_elapsed");
  const auto terminal = f.controller->inspect();
  LMDJ_CHECK(terminal.error && terminal.error->details.at("reason") == "admission_opening_deadline_elapsed");
  LMDJ_CHECK(!f.controller->inspect_io().ticket && !f.controller->inspect_io().completion);
  lmdj::test::check(!refused.opening_pending && !refused.opening_complete, "opening_expiry_retains_e1_and_uses_a_real_stop: final refused opening retires pending without completing");
  LMDJ_CHECK(refused.start_receipt && refused.cancel_receipt);
  LMDJ_CHECK(refused.start_receipt->result == audio::ScheduledPatternResult::applied &&
      refused.start_receipt->effective_frame == s && refused.start_receipt->origin_frame == s);
  LMDJ_CHECK(refused.cancel_receipt->result == audio::ScheduledPatternResult::applied &&
      refused.cancel_receipt->effective_frame == expected_stop_frame &&
      refused.cancel_receipt->origin_frame == s && !refused.cancel_receipt->playing);
  LMDJ_CHECK(!f.controller->inspect().playing && !f.controller->inspect().recording);
  LMDJ_CHECK(f.port.scheduled_quiescent());
  project_io::SequenceJournal journal(f.storage->inner);
  const auto prefix = journal.read_active(f.bundle);
  LMDJ_CHECK(prefix.has_value() && prefix.value().admission &&
      prefix.value().admission->closure && prefix.value().admission->candidates.empty());
  LMDJ_CHECK(prefix.value().admission->closure->reason == project_io::SequenceAdmissionCloseReason::deadline);
  LMDJ_CHECK(!prefix.value().admission->admission_fence && !prefix.value().admission->cutoff_fence);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
}

void known_durable_opening_survives_held_delivery_and_late_exact_reconciliation(
    bool pause_before_publication = false) {
  Fixture f;
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  f.controller.reset();
  struct Bridge final : facade::detail::PatternTransportAudioPort {
    Port& port;
    explicit Bridge(Port& value) : port(value) {}
    audio::PatternTransportSubmit submit(const audio::PatternTransportCommand& c) override { return port.submit(c); }
    std::optional<audio::PatternTransportReceipt> inspect(std::uint64_t g, std::uint64_t e) const override { return port.inspect(g, e); }
    bool acknowledge(std::uint64_t g, std::uint64_t e) override { return port.acknowledge(g, e); }
    std::uint64_t pattern_generation() const override { return port.pattern_generation(); }
    std::optional<audio::PatternReplacementAuthority> pending_switch() const override { return port.pending_switch(); }
    std::optional<foundation::PatternId> current_pattern() const override { return port.current_pattern(); }
    bool supports_receipt_bound_opening() const override { return port.supports_receipt_bound_opening(); }
    std::optional<audio::PatternTransportObservation> observe_transport() const override { return port.observe_transport(); }
    foundation::Result<audio::PatternPublication> publish_overlay(const foundation::PatternId& p,
        std::span<const domain::PatternEvent> e) override { return port.publish_overlay(p, e); }
    bool cancel_overlay(const audio::PatternReplacementAuthority& a) override { return port.cancel_overlay(a); }
  } bridge(f.port);
  struct Gate {
    std::mutex mutex;
    std::condition_variable cv;
    bool entered{}, released{};
    std::optional<facade::PatternTransportWorkRequest> opening_request;
    void release() { std::lock_guard lock(mutex); released = true; cv.notify_all(); }
    bool held() { std::lock_guard lock(mutex); return entered; }
    auto request() { std::lock_guard lock(mutex); return opening_request; }
  };
  struct Owner final : facade::PatternTransportWorkOwner, facade::PatternTransportWorkReconciler {
    facade::detail::PatternTransportIoOwner actual;
    std::shared_ptr<Gate> gate;
    Owner(const facade::PatternTransportControllerConfig& config, std::shared_ptr<Storage> storage,
        std::shared_ptr<facade::detail::PatternTransportOpeningPublication> publication,
        std::shared_ptr<Gate> held)
        : actual(config, std::move(storage), {}, std::move(publication)), gate(std::move(held)) {}
    facade::PatternTransportWorkCompletion execute(const facade::PatternTransportWorkRequest& r) override {
      if (nlohmann::json::parse(r.payload).at("op") == "open") {
        std::lock_guard lock(gate->mutex);
        gate->opening_request = r;
      }
      const auto result = actual.execute(r);
      if (nlohmann::json::parse(r.payload).at("op") == "open" &&
          result.outcome == facade::PatternTransportWorkOutcome::success) {
        std::unique_lock lock(gate->mutex);
        gate->entered = true;
        gate->cv.notify_all();
        gate->cv.wait(lock, [&] { return gate->released; });
        // Only delivery is lost: the actual owner already retained its real
        // durable success. Executor reconciliation must use that same owner.
        throw std::runtime_error("lost actual opening completion delivery");
      }
      return result;
    }
    facade::PatternTransportWorkCompletion reconcile(const facade::PatternTransportWorkRequest& r) override {
      return actual.reconcile(r);
    }
  };
  const facade::PatternTransportControllerConfig config{f.bundle, foundation::SequenceSessionId{uuid(1)},
      foundation::ProjectId{project}, foundation::PatternId{pattern}, 7};
  auto publication = std::make_shared<facade::detail::PatternTransportOpeningPublication>();
  auto gate = std::make_shared<Gate>();
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
  facade::detail::testing::PatternOpeningTestGate opening_gate;
#else
  LMDJ_CHECK(!pause_before_publication);
#endif
  facade::PatternTransportExecutor executor(7, [config, storage = f.storage, publication, gate] {
    return std::make_unique<Owner>(config, storage, publication, gate);
  });
  struct ReleaseOnExit {
    std::shared_ptr<Gate> gate;
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
    facade::detail::testing::PatternOpeningTestGate& opening_gate;
#endif
    ~ReleaseOnExit() {
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
      opening_gate.release();
      facade::detail::testing::install_pattern_opening_test_gate(nullptr);
#endif
      gate->release();
    }
  } release_on_exit{gate
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
      , opening_gate
#endif
  };
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
  if (pause_before_publication)
    facade::detail::testing::install_pattern_opening_test_gate(&opening_gate);
#endif
  facade::detail::PatternTransportCoordinator coordinator(bridge, executor, config, &f.port, publication);
  const auto tick = [&] { static_cast<void>(coordinator.continue_operation()); };
  wait_for([&] { return executor.inspect().ready; });
  const auto schedule = f.schedule();
  LMDJ_CHECK(coordinator.request_count_in(schedule) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); tick();
  const auto s = *coordinator.inspect_count_in().count_in->start_frame;
  f.port.render(s - f.port.engine.telemetry().rendered_frames + 1);
  wait_for([&] {
    tick();
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
    if (pause_before_publication) return opening_gate.entered.load(std::memory_order_acquire);
#endif
    return gate->held();
  });
  const auto work = executor.inspect().ticket;
  const auto original = gate->request();
  LMDJ_CHECK(work && original && original->identity == *work);
  const auto started = std::chrono::steady_clock::time_point{std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::nanoseconds{nlohmann::json::parse(original->payload).at("started").get<std::int64_t>()})};
  const auto known_opening = [&] {
    std::lock_guard lock(publication->guard);
    return publication->successful;
  };
  std::shared_ptr<const facade::detail::PatternTransportOpeningEvidence> known;
  std::chrono::steady_clock::time_point captured;
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
  if (pause_before_publication) {
    captured = std::chrono::steady_clock::time_point{std::chrono::duration_cast<std::chrono::steady_clock::duration>(
        std::chrono::nanoseconds{opening_gate.completed_stamp.load(std::memory_order_acquire)})};
    // The real owner has captured its real durable completion while holding
    // the same guard the control side can only try. No fake clock or result.
    std::unique_lock lock(publication->guard, std::try_to_lock);
    LMDJ_CHECK(!lock.owns_lock() && !gate->held());
  } else
#endif
  {
    known = known_opening();
    LMDJ_CHECK(known && known->request == *original);
    captured = known->completed_at;
  }
  LMDJ_CHECK(captured >= started && captured - started < facade::kScheduledPatternOpeningDeadline);
  project_io::SequenceJournal journals(f.storage->inner);
  project_io::ProjectStore reader(f.storage->inner);
  const auto durable = journals.read_active(f.bundle);
  LMDJ_CHECK(durable.has_value() && durable.value().admission->admission_fence);
  LMDJ_CHECK(durable.value().admission->admission_fence->effective_frame == s);
  LMDJ_CHECK(!durable.value().admission->closure && durable.value().admission->candidates.empty());
  std::this_thread::sleep_for(facade::kScheduledPatternOpeningDeadline + std::chrono::milliseconds{1});
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
  if (pause_before_publication) {
    std::atomic<bool> drove{false};
    std::jthread control_drive([&] { tick(); tick(); drove.store(true, std::memory_order_release); });
    // If a regression blocks Control on the worker's guard, release the real
    // worker before joining on exception, and retain the original 3s bound.
    struct ReleaseBeforeJoin {
      facade::detail::testing::PatternOpeningTestGate& gate;
      bool finished{};
      ~ReleaseBeforeJoin() { if (!finished) gate.release(); }
    } release_before_join{opening_gate};
    wait_for([&] { return drove.load(std::memory_order_acquire); });
    release_before_join.finished = true;
    control_drive.join();
    LMDJ_CHECK(!gate->held());
    std::unique_lock lock(publication->guard, std::try_to_lock);
    LMDJ_CHECK(!lock.owns_lock());
  } else
#endif
  { tick(); tick(); }
  const auto waiting = coordinator.inspect_count_in();
  lmdj::test::check(waiting.opening_pending && !waiting.opening_complete && !waiting.error && !waiting.cancel_receipt, "known_durable_opening_survives_held_delivery_and_late_exact_reconciliation: timely durable opening has no synthetic cancellation");
  LMDJ_CHECK(waiting.start_receipt && waiting.start_receipt->result == audio::ScheduledPatternResult::applied);
  LMDJ_CHECK(waiting.start_receipt->effective_frame == s && waiting.start_receipt->origin_frame == s);
  LMDJ_CHECK(coordinator.inspect().playing && !coordinator.inspect().recording);
  LMDJ_CHECK(executor.inspect().ticket == work && !executor.inspect().completion);
  LMDJ_CHECK(f.port.ordinary_ack_calls == 0 && f.port.scheduled_ack_calls == 0);
  LMDJ_CHECK(journals.read_active(f.bundle).value() == durable.value());
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
  if (pause_before_publication) {
    opening_gate.release();
    wait_for([&] { tick(); return gate->held(); });
    known = known_opening();
    LMDJ_CHECK(known && known->request == *original && known->completed_at == captured);
    // Publication still does not deliver executor success, retire the exact
    // work, ACK the real Native receipt, or announce recording to the UI.
    tick(); tick();
    const auto published = coordinator.inspect_count_in();
    LMDJ_CHECK(published.opening_pending && !published.opening_complete && !published.error);
    LMDJ_CHECK(!published.cancel_receipt && !coordinator.inspect().recording);
    LMDJ_CHECK(executor.inspect().ticket == work && !executor.inspect().completion);
    LMDJ_CHECK(f.port.ordinary_ack_calls == 0 && f.port.scheduled_ack_calls == 0);
    LMDJ_CHECK(journals.read_active(f.bundle).value() == durable.value());
  }
#endif
  gate->release();
  wait_for([&] { tick(); return coordinator.inspect_count_in().opening_complete; });
  LMDJ_CHECK(!coordinator.inspect_count_in().error && coordinator.inspect().recording);
  const auto replayed = known_opening();
  LMDJ_CHECK(replayed && replayed->request == known->request && replayed->completed_at == known->completed_at);
  const auto input = [&](unsigned id, bool pressed, std::uint64_t correlation = 0) {
    const facade::PatternTransportInputRequest r{foundation::CommandId{uuid(id)}, 7,
        f.port.engine.telemetry().start_epoch, f.port.engine.telemetry().rendered_frames,
        {0, 1}, pressed, static_cast<std::uint8_t>(pressed ? 90 : 0), correlation, true};
    const auto ticket = coordinator.reserve_input(r);
    LMDJ_CHECK(ticket.has_value());
    const audio::PatternInputCommand command{7, r.frame_epoch, 1, r.velocity, !pressed, correlation, true,
        cooker::ResolvedPlayback{0, 128, domain::TriggerMode::loop_gate, 1.0F, true}};
    const auto accepted = f.port.engine.enqueue_pattern_input(command);
    LMDJ_CHECK(accepted.result == audio::PatternInputSubmit::accepted);
    LMDJ_CHECK(coordinator.bind_input(ticket.value(), accepted));
    f.port.render(1);
    const auto actual = f.port.engine.inspect_pattern_input_completion(7, r.frame_epoch, accepted.sequence);
    LMDJ_CHECK(actual && coordinator.complete_input(*actual));
    LMDJ_CHECK(!coordinator.consume_input(ticket.value()));
    wait_for([&] { tick(); const auto state = coordinator.inspect_input(ticket.value()); return state && state->complete; });
    const auto state = coordinator.inspect_input(ticket.value());
    LMDJ_CHECK(state->durable_settled && state->native_result && !state->error);
    LMDJ_CHECK(f.port.engine.consume_pattern_input_completion(7, r.frame_epoch, accepted.sequence));
    LMDJ_CHECK(coordinator.consume_input(ticket.value()));
    return accepted;
  };
  const auto press = input(10, true);
  f.port.render(24'000);
  input(11, false, press.sequence);
  LMDJ_CHECK(coordinator.inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
  const auto stop_frame = f.port.engine.telemetry().rendered_frames;
  LMDJ_CHECK(stop_frame == s + 24'003);
  const facade::ScheduledPatternTransportCancel cancel{
      f.request(3, 2, facade::PatternTransportIntent::play_stop), schedule.frame_epoch, schedule.schedule_serial};
  LMDJ_CHECK(coordinator.cancel_count_in(cancel) == facade::PatternTransportSubmit::accepted);
  tick(); f.port.render(1);
  wait_for([&] { tick(); return coordinator.inspect().phase == facade::PatternTransportPhase::idle; });
  const auto closed = coordinator.inspect_count_in();
  LMDJ_CHECK(!closed.error && closed.start_receipt->effective_frame == s && closed.cancel_receipt);
  LMDJ_CHECK(closed.cancel_receipt->result == audio::ScheduledPatternResult::applied);
  LMDJ_CHECK(closed.cancel_receipt->epoch == 2 && closed.cancel_receipt->origin_frame == s);
  LMDJ_CHECK(closed.cancel_receipt->effective_frame == stop_frame && !closed.cancel_receipt->playing);
  LMDJ_CHECK(!coordinator.inspect().playing && !coordinator.inspect().recording && f.port.scheduled_quiescent());
  const auto reopened = reader.load(f.bundle);
  LMDJ_CHECK(reopened.has_value() && reopened.value().revision == 1);
  auto expected = f.initial;
  expected.revision = 1;
  expected.patterns.at(foundation::PatternId{pattern}).events = {{{0, 1}, 0, 960, 90}};
  LMDJ_CHECK(reopened.value() == expected);
  LMDJ_CHECK(!journals.read_active(f.bundle).has_value());
  coordinator.request_shutdown();
  wait_for([&] { tick(); return coordinator.shutdown_complete(); });
}

void exceptional_direct_stop_preserves_failure_and_owner_loss_recovery() {
  Fixture f;
  f.storage->arm(true);
  LMDJ_CHECK(f.controller->request_count_in(f.schedule()) == facade::PatternTransportSubmit::accepted);
  f.port.render(1); f.tick();
  const auto s = *f.controller->inspect_count_in().count_in->start_frame;
  f.port.render(s - f.port.engine.telemetry().rendered_frames + 1);
  wait_for([&] { f.tick(); return f.storage->is_entered(); });
  // The legacy port cannot name this real queued publication. Native must
  // refuse the ordinary cutoff, proving e2 remains UNSENT before owner loss.
  cooker::RuntimeSnapshot pending_snapshot{foundation::ProjectId{project}, foundation::PatternId{pattern},
      1, 120, 1, domain::kPpq, domain::kBarTicks4x4, {}, {}};
  auto pending_view = audio::PreparedPatternView::from_snapshot(pending_snapshot);
  LMDJ_CHECK(pending_view.has_value());
  const auto current_generation = f.port.pattern_generation();
  const auto queued = f.port.engine.publish_pattern_view(std::move(pending_view.value()));
  LMDJ_CHECK(queued.result == audio::PatternPublishResult::accepted);
  LMDJ_CHECK(queued.generation != current_generation &&
      queued.activation_frame > f.port.engine.telemetry().rendered_frames);
  const auto observation = f.port.engine.pattern_transport_observation();
  LMDJ_CHECK(observation && !observation->pending_switches[0] && observation->pending_switches[1] &&
      observation->pending_switches[1]->generation == queued.generation &&
      observation->pending_switches[1]->pattern_id == foundation::PatternId{pattern} &&
      observation->pending_switches[1]->activation_frame == queued.activation_frame);
  LMDJ_CHECK(f.port.ordinary_submit_calls == 0);
  const facade::ScheduledPatternTransportCancel cancel{
      f.request(3, 2, facade::PatternTransportIntent::play_stop), f.schedule().frame_epoch, 1};
  LMDJ_CHECK(f.controller->cancel_count_in(cancel) == facade::PatternTransportSubmit::accepted);
  LMDJ_CHECK(f.port.ordinary_submit_calls == 1 &&
      f.port.ordinary_submit_result == audio::PatternTransportSubmit::identity_mismatch);
  LMDJ_CHECK(!f.port.engine.inspect_pattern_transport_receipt(7, 2));
  LMDJ_CHECK(!f.port.engine.inspect_scheduled_pattern_record(7, 1)->cancel_receipt);
  LMDJ_CHECK(f.port.pattern_generation() == current_generation);
  // Deliberate exceptional invalidation after a proven unadmitted real e2.
  f.port.engine.stop();
  f.tick();
  const auto invalidated = f.controller->inspect_count_in();
  LMDJ_CHECK(invalidated.start_receipt->result == audio::ScheduledPatternResult::applied);
  LMDJ_CHECK(*invalidated.start_receipt->effective_frame == s);
  LMDJ_CHECK(invalidated.cancel_receipt->result == audio::ScheduledPatternResult::refused);
  LMDJ_CHECK(!invalidated.cancel_receipt->effective_frame && !invalidated.cancel_receipt->origin_frame);
  LMDJ_CHECK(invalidated.error && invalidated.error->details.at("reason") == "scheduled_record_owner_invalidated");
  const auto work = f.controller->inspect_io().ticket;
  LMDJ_CHECK(work && !f.controller->shutdown_complete());
  f.controller->request_shutdown();
  LMDJ_CHECK(f.controller->inspect_io().ticket == work);
  f.storage->release();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  project_io::SequenceJournal journal(f.storage->inner);
  const auto retained = journal.read_active(f.bundle);
  LMDJ_CHECK(retained.has_value() && retained.value().state == project_io::SequenceSessionState::owner_lost);
  LMDJ_CHECK(retained.value().admission && retained.value().admission->admission_fence);
  LMDJ_CHECK(retained.value().admission->admission_fence->effective_frame == s);
  LMDJ_CHECK(!retained.value().admission->cutoff_fence);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  LMDJ_CHECK(f.controller->inspect_count_in().error);
}

void exceptional_owner_ack_requires_real_disposition_and_each_consumer() {
  Fixture f;
  // Bind one actual shared history registry to both Store and the production
  // worker, after the pristine original worker has really stopped.
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  f.controller.reset();
  auto history = std::make_shared<project_io::AuthoringHistory>();
  project_io::ProjectStore history_store(f.storage->inner, history);
  LMDJ_CHECK(history_store.open_authoring_history(f.bundle, uuid(50)).has_value());
  f.controller = facade::detail::PatternTransportControllerInternalFactory::make(f.port,
      {f.bundle, foundation::SequenceSessionId{uuid(1)}, foundation::ProjectId{project}, foundation::PatternId{pattern}, 7},
      f.storage, history, {}, &f.port);
  wait_for([&] { return f.controller->inspect_io().ready; });
  const auto history_view = [&] {
    const auto result = history_store.inspect_authoring_history(f.bundle);
    LMDJ_CHECK(result.has_value());
    const auto& s = result.value();
    return std::tuple{s.session_id, s.revision, s.undo_count, s.redo_count,
        s.undo_label, s.redo_label, s.disabled_reason};
  };
  const auto original_history = history_view();
  f.start();
  const auto press = f.input(20, 1, true);
  f.port.render(1); f.native_complete(press.first, press.second);
  wait_for([&] { f.tick(); return f.controller->inspect_input(press.first)->complete; });
  LMDJ_CHECK(f.controller->inspect_input(press.first)->retained);
  LMDJ_CHECK(f.controller->inspect_input(press.first)->native_result->disposition ==
      audio::PatternInputDisposition::muted_no_voice);
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(!f.port.engine.revoke_pattern_input_holds_quiescent(7));
  f.port.engine.stop();
  f.controller->request_shutdown();
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  wait_for([&] { f.tick(); return f.controller->inspect_input_owner().disposed; });
  const auto disposed = f.controller->inspect_input_owner();
  LMDJ_CHECK(disposed.invalidated && disposed.pending && !disposed.acknowledged);
  LMDJ_CHECK(disposed.held_correlations == 1);
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  // Facade consumption alone cannot spend the Native completion or physical
  // hold. Its separate owner lookup still retains the exact correlation.
  LMDJ_CHECK(f.controller->consume_input(press.first));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().retained_completions == 1);
  LMDJ_CHECK(f.port.engine.consume_pattern_input_completion(7, f.schedule().frame_epoch, press.second.sequence));
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(!f.port.engine.revoke_pattern_input_holds_quiescent(8));
  LMDJ_CHECK(f.port.engine.revoke_pattern_input_holds_quiescent(7));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(8));
  LMDJ_CHECK(f.controller->inspect_input_owner().held_correlations == 1);
  LMDJ_CHECK(f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(f.controller->inspect_input_owner().acknowledged);
  LMDJ_CHECK(f.controller->inspect_input_owner().held_correlations == 0);
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.controller->inspect().phase == facade::PatternTransportPhase::error);
  LMDJ_CHECK(f.controller->inspect().error->details.at("reason") == "pattern_transport_owner_invalidated");
  project_io::SequenceJournal journal(f.storage->inner);
  const auto prefix = journal.read_active(f.bundle);
  LMDJ_CHECK(prefix.has_value() && prefix.value().state == project_io::SequenceSessionState::owner_lost);
  LMDJ_CHECK(prefix.value().admission && !prefix.value().admission->cutoff_fence);
  LMDJ_CHECK(prefix.value().admission->candidates.size() == 1);
  LMDJ_CHECK(prefix.value().admission->candidates[0].press_sequence == press.second.sequence);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  // Journal availability is separate from the shared authoring history.
  // Owner loss preserves every history field while the retained active prefix
  // continues to block public Undo/Redo through the established Store gate.
  const auto raw_history = [&] {
    auto guard = history->acquire();
    const auto s = history->status(f.bundle);
    return std::tuple{s.session_id, s.revision, s.undo_count, s.redo_count,
        s.undo_label, s.redo_label, s.disabled_reason};
  }();
  LMDJ_CHECK(raw_history == original_history);
  auto unavailable_history = original_history;
  std::get<6>(unavailable_history) = "sequence_session_active";
  LMDJ_CHECK(history_view() == unavailable_history);
}

void exceptional_owner_ack_preserves_queued_invalidated_release() {
  Fixture f;
  f.start();
  const auto press = f.input(20, 1, true);
  f.port.render(1); f.native_complete(press.first, press.second); f.input_settled(press.first, press.second);
  const auto release = f.input(21, 1, false, press.second.sequence);
  f.port.engine.stop(); // Actual queued Release invalidation, never a fabricated release.
  f.native_complete(release.first, release.second);
  const auto native = f.port.engine.inspect_pattern_input_completion(7, f.schedule().frame_epoch, release.second.sequence);
  LMDJ_CHECK(native && native->disposition == audio::PatternInputDisposition::invalidated_before_consume);
  LMDJ_CHECK(native->held_press_sequence == press.second.sequence);
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->inspect_input_owner().disposed; });
  LMDJ_CHECK(f.controller->inspect_input(release.first)->complete);
  LMDJ_CHECK(f.controller->inspect_input(release.first)->error);
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  // Native revocation cannot overwrite the queued operation's consumer cell.
  LMDJ_CHECK(f.port.engine.revoke_pattern_input_holds_quiescent(7));
  LMDJ_CHECK(f.port.engine.inspect_pattern_input_completion(7, f.schedule().frame_epoch, release.second.sequence));
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(f.port.engine.consume_pattern_input_completion(7, f.schedule().frame_epoch, release.second.sequence));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7)); // Facade consumer still owns its ticket.
  LMDJ_CHECK(f.controller->consume_input(release.first));
  LMDJ_CHECK(!f.controller->consume_input(release.first));
  LMDJ_CHECK(f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.controller->inspect().error);
  project_io::SequenceJournal journal(f.storage->inner);
  const auto prefix = journal.read_active(f.bundle);
  LMDJ_CHECK(prefix.has_value() && prefix.value().state == project_io::SequenceSessionState::owner_lost);
  LMDJ_CHECK(prefix.value().admission && !prefix.value().admission->cutoff_fence);
  LMDJ_CHECK(prefix.value().admission->candidates.size() == 1); // No invented Release candidate.
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
}

void never_recorded_owner_disposition_uses_actual_input_and_no_journal() {
  Fixture f;
  const auto press = f.input(20, 1, true);
  f.port.render(1); f.native_complete(press.first, press.second);
  wait_for([&] { f.tick(); return f.controller->inspect_input(press.first)->complete; });
  LMDJ_CHECK(!f.controller->inspect_input(press.first)->retained);
  LMDJ_CHECK((press.second.authority == audio::PatternInputAuthority{}));
  f.controller->request_shutdown();
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(7));
  f.port.engine.stop();
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(7));
  LMDJ_CHECK(f.port.engine.consume_pattern_input_completion(7, f.schedule().frame_epoch, press.second.sequence));
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(7)); // Facade ticket is still consumer-owned.
  LMDJ_CHECK(f.controller->consume_input(press.first));
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(7)); // Future Native hold remains.
  LMDJ_CHECK(f.port.engine.revoke_pattern_input_holds_quiescent(7));
  const auto writes = f.storage->writes.load();
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(8));
  LMDJ_CHECK(f.controller->request_input_owner_disposition(7));
  const auto work = f.controller->inspect_io().ticket;
  LMDJ_CHECK(work && work->runtime_generation == 7 && work->transport_epoch == 0);
  LMDJ_CHECK(work->command_id == press.first.command_id);
  LMDJ_CHECK(f.controller->request_input_owner_disposition(7));
  LMDJ_CHECK(f.controller->inspect_io().ticket == work);
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  wait_for([&] { f.tick(); return f.controller->inspect_input_owner().disposed; });
  LMDJ_CHECK(f.controller->inspect_input_owner().held_correlations == 1);
  LMDJ_CHECK(f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.controller->inspect().phase == facade::PatternTransportPhase::error);
  LMDJ_CHECK(f.controller->inspect().error->details.at("reason") == "pattern_input_owner_revoked");
  LMDJ_CHECK(f.storage->writes == writes);
  project_io::SequenceJournal journal(f.storage->inner);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
}

void real_record_off_close_keeps_physical_owner_until_exceptional_disposition() {
  Fixture f;
  f.start();
  const auto start = f.controller->inspect_count_in().start_receipt;
  const auto press = f.input(20, 1, true);
  f.port.render(1); f.native_complete(press.first, press.second); f.input_settled(press.first, press.second);
  const auto second = f.input(21, 2, true);
  f.port.render(1); f.native_complete(second.first, second.second); f.input_settled(second.first, second.second);
  f.port.render(24'000);
  const auto record_off = f.request(3, 2, facade::PatternTransportIntent::record);
  LMDJ_CHECK(f.controller->request(record_off) == facade::PatternTransportSubmit::accepted);
  f.port.render(1);
  const auto real_f = f.port.inspect(7, 2);
  LMDJ_CHECK(real_f && real_f->epoch == 2 && real_f->playing);
  LMDJ_CHECK(real_f->origin_frame == *start->origin_frame);
  f.settled();
  LMDJ_CHECK(!f.controller->inspect().recording && f.controller->inspect().playing);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.controller->inspect_input_owner().held_correlations == 2);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 2);
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(7));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(!f.port.engine.revoke_pattern_input_holds_quiescent(7));
  project_io::ProjectStore reader(f.storage->inner);
  const auto committed = reader.load(f.bundle);
  LMDJ_CHECK(committed.has_value() && committed.value().revision == 1);
  project_io::SequenceJournal journal(f.storage->inner);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
  const auto queued_release = f.input(22, 2, false, second.second.sequence);
  f.port.engine.stop(); // Explicit exceptional Native invalidation after the real close.
  f.native_complete(queued_release.first, queued_release.second);
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->inspect_input(queued_release.first)->complete; });
  LMDJ_CHECK(f.controller->inspect_input(queued_release.first)->native_result->disposition ==
      audio::PatternInputDisposition::invalidated_before_consume);
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(7));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(f.port.engine.consume_pattern_input_completion(7, f.schedule().frame_epoch, queued_release.second.sequence));
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(7));
  LMDJ_CHECK(f.controller->consume_input(queued_release.first));
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(7)); // Native future hold remains.
  LMDJ_CHECK(f.port.engine.revoke_pattern_input_holds_quiescent(7));
  LMDJ_CHECK(!f.controller->request_input_owner_disposition(8));
  LMDJ_CHECK(f.controller->request_input_owner_disposition(7));
  const auto owner_work = f.controller->inspect_io().ticket;
  LMDJ_CHECK(owner_work && owner_work->transport_epoch == real_f->epoch);
  LMDJ_CHECK(owner_work->command_id == record_off.command_id);
  LMDJ_CHECK(f.controller->request_input_owner_disposition(7));
  LMDJ_CHECK(f.controller->inspect_io().ticket == owner_work);
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  wait_for([&] { f.tick(); return f.controller->inspect_input_owner().disposed; });
  LMDJ_CHECK(f.controller->acknowledge_input_owner(7));
  LMDJ_CHECK(!f.controller->acknowledge_input_owner(7));
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.controller->inspect().phase == facade::PatternTransportPhase::error);
  LMDJ_CHECK(f.controller->inspect().transport_epoch == real_f->epoch);
  LMDJ_CHECK(f.controller->inspect().origin_frame == real_f->origin_frame);
  const auto after_start = f.controller->inspect_count_in().start_receipt;
  LMDJ_CHECK(after_start && start);
  LMDJ_CHECK(std::tie(after_start->runtime_generation, after_start->frame_epoch, after_start->serial,
      after_start->epoch, after_start->pattern_generation, after_start->pattern_id, after_start->result,
      after_start->effective_frame, after_start->origin_frame, after_start->playing) ==
      std::tie(start->runtime_generation, start->frame_epoch, start->serial, start->epoch,
      start->pattern_generation, start->pattern_id, start->result, start->effective_frame,
      start->origin_frame, start->playing));
  LMDJ_CHECK(reader.load(f.bundle).value() == committed.value());
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
}

void mixed_age_expiry_survives_real_durable_completion_and_fresh_cell_reuse() {
  Fixture f;
  f.start();
  const auto start = f.controller->inspect_count_in().start_receipt;
  LMDJ_CHECK(start && start->origin_frame && start->effective_frame);
  const auto frame_epoch = f.port.engine.telemetry().start_epoch;
  using Input = std::pair<facade::PatternTransportInputTicket, audio::PatternInputAdmission>;
  const auto reserve_unheld = [&](unsigned id, std::uint8_t slot) -> Input {
    const facade::PatternTransportInputRequest request{foundation::CommandId{uuid(id)}, 7,
        frame_epoch, f.port.engine.telemetry().rendered_frames, {0, slot}, true, 90, 0, false};
    const auto ticket = f.controller->reserve_input(request);
    LMDJ_CHECK(ticket.has_value());
    LMDJ_CHECK(f.controller->reserve_input(request).value() == ticket.value());
    auto foreign = request;
    ++foreign.runtime_frame;
    LMDJ_CHECK(!f.controller->reserve_input(foreign).has_value());
    const auto admitted = f.port.engine.enqueue_pattern_input({7, frame_epoch, slot, 90,
        false, 0, false, cooker::ResolvedPlayback{0, 128, domain::TriggerMode::loop_gate, 1.0F, true}});
    LMDJ_CHECK(admitted.result == audio::PatternInputSubmit::accepted);
    LMDJ_CHECK(admitted.authority.recording && admitted.authority.transport_epoch == start->epoch &&
        admitted.authority.schedule_serial == start->serial);
    LMDJ_CHECK(f.controller->bind_input(ticket.value(), admitted));
    f.port.render(1);
    const auto native = f.port.engine.inspect_pattern_input_completion(7, frame_epoch, admitted.sequence);
    LMDJ_CHECK(native && native->runtime_frame == request.runtime_frame && native->held_press_sequence == 0);
    LMDJ_CHECK(native->disposition == audio::PatternInputDisposition::muted_no_voice);
    LMDJ_CHECK(native->runtime_frame >= *start->origin_frame && native->runtime_frame - *start->origin_frame < 25);
    f.native_complete(ticket.value(), admitted);
    LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
    return {ticket.value(), admitted};
  };
  const auto complete_without_consuming = [&](const Input& input, bool expected_expired) {
    wait_for([&] {
      f.tick();
      const auto status = f.controller->inspect_input(input.first);
      return status && status->complete;
    });
    const auto status = f.controller->inspect_input(input.first);
    LMDJ_CHECK(status && status->complete && status->durable_settled && status->retained && !status->error);
    LMDJ_CHECK(status->native_result && status->native_result->sequence == input.second.sequence);
    LMDJ_CHECK(status->native_result->authority == input.second.authority);
    // complete=true disables inspect_input's elapsed-clock fallback: this is
    // the stored expiry result, while both real consumer obligations remain.
    lmdj::test::check(status->expired == expected_expired,
        "mixed_age_expiry_survives_real_durable_completion_and_fresh_cell_reuse: completed ticket keeps its own stored expiry");
    LMDJ_CHECK(f.port.engine.inspect_pattern_input_completion(7, frame_epoch, input.second.sequence));
  };
  const auto consume = [&](const Input& input) {
    LMDJ_CHECK(f.port.engine.consume_pattern_input_completion(7, frame_epoch, input.second.sequence));
    LMDJ_CHECK(!f.port.engine.inspect_pattern_input_completion(7, frame_epoch, input.second.sequence));
    LMDJ_CHECK(f.controller->consume_input(input.first));
    LMDJ_CHECK(!f.controller->inspect_input(input.first));
    LMDJ_CHECK(!f.controller->consume_input(input.first));
  };

  f.storage->arm(false);
  const auto first = reserve_unheld(70, 1);
  wait_for([&] { f.tick(); return f.storage->is_entered(); });
  const auto work = f.controller->inspect_io().ticket;
  LMDJ_CHECK(work);
  std::this_thread::sleep_for(facade::kPatternTransportInputDeadline + std::chrono::milliseconds{1});
  // The first ticket is overdue. Reserve the younger one before the next
  // Control drive, so the due scan must preserve its different original start.
  const auto second = reserve_unheld(71, 2);
  f.tick();
  LMDJ_CHECK(f.controller->inspect_io().ticket == work);
  const auto old = f.controller->inspect_input(first.first);
  const auto young = f.controller->inspect_input(second.first);
  LMDJ_CHECK(old && old->expired && !old->complete);
  LMDJ_CHECK(young && !young->expired && !young->complete);
  LMDJ_CHECK(!f.controller->consume_input(first.first) && !f.controller->consume_input(second.first));
  std::this_thread::sleep_for(facade::kPatternTransportInputDeadline + std::chrono::milliseconds{1});
  f.tick();
  LMDJ_CHECK(f.controller->inspect_io().ticket == work);
  LMDJ_CHECK(f.controller->inspect_input(first.first)->expired);
  LMDJ_CHECK(f.controller->inspect_input(second.first)->expired);
  LMDJ_CHECK(!f.controller->inspect_input(first.first)->complete && !f.controller->inspect_input(second.first)->complete);
  f.storage->release();
  complete_without_consuming(first, true);
  complete_without_consuming(second, true);
  consume(first);
  consume(second);
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 0);
  LMDJ_CHECK(f.controller->inspect_ingress().ordinary_pending == 0);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  wait_for([&] { f.tick(); return !f.controller->inspect_io().ticket; });

  // Both old cells have been consumed. The next real input reuses the first
  // ordinary slot with a fresh deadline and must not inherit stored expiry.
  const auto fresh_started = std::chrono::steady_clock::now();
  const auto fresh = reserve_unheld(72, 3);
  LMDJ_CHECK(fresh.first != first.first && fresh.first != second.first);
  wait_for([&] {
    f.tick();
    const auto status = f.controller->inspect_input(fresh.first);
    return status && status->complete;
  });
  LMDJ_CHECK(std::chrono::steady_clock::now() - fresh_started < facade::kPatternTransportInputDeadline);
  complete_without_consuming(fresh, false);
  consume(fresh);
  wait_for([&] { f.tick(); return !f.controller->inspect_io().ticket; });
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 0);

  // Reuse again with actual IO held: a stale earlier hint may scan early,
  // but an empty/rebuilt hint must not hide this cell's later stored expiry.
  f.storage->arm(false);
  const auto reused = reserve_unheld(73, 4);
  LMDJ_CHECK(reused.first != fresh.first && reused.first != first.first);
  wait_for([&] { f.tick(); return f.storage->is_entered(); });
  const auto reused_work = f.controller->inspect_io().ticket;
  LMDJ_CHECK(reused_work);
  std::this_thread::sleep_for(facade::kPatternTransportInputDeadline + std::chrono::milliseconds{1});
  f.tick();
  LMDJ_CHECK(f.controller->inspect_io().ticket == reused_work);
  LMDJ_CHECK(f.controller->inspect_input(reused.first)->expired && !f.controller->inspect_input(reused.first)->complete);
  LMDJ_CHECK(!f.controller->consume_input(reused.first));
  f.storage->release();
  complete_without_consuming(reused, true);
  consume(reused);
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 0);
  LMDJ_CHECK(f.controller->inspect_ingress().ordinary_pending == 0);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().retained_completions == 0);

  const auto stop = f.request(3, 2, facade::PatternTransportIntent::play_stop);
  LMDJ_CHECK(f.controller->request(stop) == facade::PatternTransportSubmit::accepted);
  f.port.render(1);
  const auto real_f = f.port.inspect(7, 2);
  LMDJ_CHECK(real_f && !real_f->playing && real_f->origin_frame == *start->origin_frame);
  LMDJ_CHECK(real_f->effective_frame >= f.port.engine.telemetry().rendered_frames - 1);
  f.settled();
  LMDJ_CHECK(!f.controller->inspect().playing && !f.controller->inspect().recording);
  LMDJ_CHECK(f.controller->inspect().transport_epoch == real_f->epoch);
  LMDJ_CHECK(f.controller->inspect().origin_frame == real_f->origin_frame);
  LMDJ_CHECK(!f.port.inspect(7, 2)); // Facade acknowledged the actual Native F.
  project_io::ProjectStore reader(f.storage->inner);
  const auto reopened = reader.load(f.bundle);
  LMDJ_CHECK(reopened.has_value());
  auto expected = f.initial;
  expected.revision = 1;
  expected.patterns.at(foundation::PatternId{pattern}).events = {
      {{0, 1}, 0, domain::kSixteenthTicks, 90}, {{0, 2}, 0, domain::kSixteenthTicks, 90},
      {{0, 3}, 0, domain::kSixteenthTicks, 90}, {{0, 4}, 0, domain::kSixteenthTicks, 90}};
  LMDJ_CHECK(reopened.value() == expected); // All four exact events and complete Project Truth.
  project_io::SequenceJournal journal(f.storage->inner);
  LMDJ_CHECK(!journal.read_active(f.bundle).has_value());
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(!f.controller->inspect_io().ticket && !f.controller->inspect_io().completion);
  LMDJ_CHECK(f.storage->worker != std::this_thread::get_id());
  LMDJ_CHECK(f.storage->writers == f.storage->leases_destroyed);
}
void public_input_ticket_identity_survives_real_consumption_and_occupied_reuse() {
  Fixture f;
  f.start();
  const auto start = f.controller->inspect_count_in().start_receipt;
  LMDJ_CHECK(start && start->origin_frame && start->effective_frame);
  LMDJ_CHECK(start->result == audio::ScheduledPatternResult::applied);
  LMDJ_CHECK(start->origin_frame == start->effective_frame);
  const auto origin = *start->origin_frame;
  const auto frame_epoch = f.port.engine.telemetry().start_epoch;
  LMDJ_CHECK(f.port.engine.telemetry().rendered_frames == origin + 1);
  using Input = std::pair<facade::PatternTransportInputTicket, audio::PatternInputAdmission>;
  const auto native_identity = [](const audio::PatternInputCompletion& c) {
    return std::tuple{c.runtime_generation, c.frame_epoch, c.sequence,
        c.held_press_sequence, c.acceptance_ordinal, c.runtime_frame, c.slot,
        c.authority, c.disposition};
  };
  const auto status_identity = [&](const facade::PatternTransportInputStatus& s) {
    LMDJ_CHECK(s.admission && s.native_result && !s.error);
    return std::tuple{s.ticket, s.admission->result, s.admission->sequence,
        s.admission->acceptance_ordinal, s.admission->authority,
        native_identity(*s.native_result), s.durable_settled, s.retained,
        s.complete, s.expired};
  };
  const auto ingress_identity = [](const facade::PatternTransportIngressStatus& s) {
    return std::tuple{s.ordinary_pending, s.held_release_metadata, s.retained_tickets};
  };
  const auto native_profile_identity = [](const audio::PatternInputProfileStatus& s) {
    return std::tuple{s.enabled, s.runtime_generation, s.capacity, s.physical_capacity,
        s.ordinary_pending, s.held_release_reservations, s.retained_completions};
  };
  const auto io_identity = [](const facade::PatternTransportExecutorStatus& s) {
    LMDJ_CHECK(!s.startup_error);
    return std::tuple{s.ready, s.shutdown_requested, s.stopped, s.ticket, s.completion};
  };
  const auto wait_complete = [&](const Input& input) {
    wait_for([&] {
      f.tick();
      const auto state = f.controller->inspect_input(input.first);
      return state && state->complete;
    });
    const auto state = f.controller->inspect_input(input.first);
    LMDJ_CHECK(state && state->ticket == input.first && state->complete &&
        state->durable_settled && state->retained && !state->error);
    LMDJ_CHECK(state->admission && state->admission->result == audio::PatternInputSubmit::accepted &&
        state->admission->sequence == input.second.sequence &&
        state->admission->acceptance_ordinal == input.second.acceptance_ordinal &&
        state->admission->authority == input.second.authority);
    const auto native = f.port.engine.inspect_pattern_input_completion(7, frame_epoch, input.second.sequence);
    LMDJ_CHECK(native && state->native_result);
    LMDJ_CHECK(native_identity(*state->native_result) == native_identity(*native));
    wait_for([&] {
      f.tick();
      const auto io = f.controller->inspect_io();
      return io.ready && !io.ticket && !io.completion;
    });
  };
  const auto press = [&](unsigned id, std::uint8_t slot, std::uint64_t expected_frame) -> Input {
    LMDJ_CHECK(f.port.engine.telemetry().rendered_frames == expected_frame);
    const auto input = f.input(id, slot, true);
    LMDJ_CHECK(input.second.authority.recording && input.second.authority.transport_epoch == start->epoch &&
        input.second.authority.schedule_serial == start->serial);
    f.port.render(1);
    const auto native = f.port.engine.inspect_pattern_input_completion(7, frame_epoch, input.second.sequence);
    LMDJ_CHECK(native && native->runtime_generation == 7 && native->frame_epoch == frame_epoch &&
        native->sequence == input.second.sequence && native->acceptance_ordinal == input.second.acceptance_ordinal &&
        native->authority == input.second.authority && native->runtime_frame == expected_frame &&
        native->slot == slot && native->held_press_sequence == 0 &&
        native->disposition == audio::PatternInputDisposition::muted_no_voice);
    f.native_complete(input.first, input.second);
    return input;
  };
  const auto assert_rejected_without_effect = [&](const Input& real,
      const facade::PatternTransportInputTicket& foreign, const char* kind) {
    const auto before = f.controller->inspect_input(real.first);
    const auto native_before = f.port.engine.inspect_pattern_input_completion(7, frame_epoch, real.second.sequence);
    LMDJ_CHECK(before && native_before && before->complete && before->durable_settled && before->retained);
    const auto status_before = status_identity(*before);
    const auto profile_before = native_profile_identity(f.port.engine.pattern_input_profile_status());
    const auto ingress_before = ingress_identity(f.controller->inspect_ingress());
    const auto io_before = f.controller->inspect_io();
    LMDJ_CHECK(io_before.ready && !io_before.ticket && !io_before.completion);
    const auto io_state_before = io_identity(io_before);
    const auto writes_before = f.storage->writes.load();
    const auto acknowledgments_before = std::tuple{f.port.ordinary_ack_calls, f.port.scheduled_ack_calls};
    const auto expression = std::string{"public_input_ticket_identity_survives_real_consumption_and_occupied_reuse: "} + kind;
    lmdj::test::check(!f.controller->inspect_input(foreign), expression + " inspect stays absent");
    lmdj::test::check(!f.controller->bind_input(foreign, real.second), expression + " cannot bind a legitimate actual admission");
    lmdj::test::check(!f.controller->consume_input(foreign), expression + " cannot consume a legitimate completed ticket");
    const auto after = f.controller->inspect_input(real.first);
    const auto native_after = f.port.engine.inspect_pattern_input_completion(7, frame_epoch, real.second.sequence);
    LMDJ_CHECK(after && native_after);
    lmdj::test::check(status_identity(*after) == status_before, expression + " preserves the complete legitimate status");
    lmdj::test::check(native_identity(*native_after) == native_identity(*native_before),
        expression + " preserves the actual Native consumer evidence");
    LMDJ_CHECK(native_profile_identity(f.port.engine.pattern_input_profile_status()) == profile_before);
    LMDJ_CHECK(ingress_identity(f.controller->inspect_ingress()) == ingress_before);
    LMDJ_CHECK(io_identity(f.controller->inspect_io()) == io_state_before);
    LMDJ_CHECK(f.storage->writes.load() == writes_before);
    LMDJ_CHECK((std::tuple{f.port.ordinary_ack_calls, f.port.scheduled_ack_calls} == acknowledgments_before));
  };
  const auto assert_foreign_fields = [&](const Input& real) {
    auto generation = real.first;
    ++generation.runtime_generation;
    assert_rejected_without_effect(real, generation, "foreign runtime_generation");
    auto command = real.first;
    command.command_id = foundation::CommandId{uuid(999)};
    LMDJ_CHECK(command.command_id != real.first.command_id);
    assert_rejected_without_effect(real, command, "foreign command_id");
    auto value = real.first;
    ++value.ticket;
    LMDJ_CHECK(value.ticket && value.ticket != real.first.ticket);
    assert_rejected_without_effect(real, value, "foreign ticket value");
  };

  const auto a = press(80, 1, origin + 1);
  const auto b = press(81, 2, origin + 2);
  wait_complete(a);
  wait_complete(b);
  const auto state_a = f.controller->inspect_input(a.first);
  const auto state_b = f.controller->inspect_input(b.first);
  LMDJ_CHECK(state_a && state_b);
  const auto identity_a = status_identity(*state_a);
  const auto identity_b = status_identity(*state_b);
  LMDJ_CHECK(status_identity(*f.controller->inspect_input(a.first)) == identity_a);
  LMDJ_CHECK(status_identity(*f.controller->inspect_input(a.first)) == identity_a);
  LMDJ_CHECK(status_identity(*f.controller->inspect_input(b.first)) == identity_b);
  LMDJ_CHECK(status_identity(*f.controller->inspect_input(b.first)) == identity_b);
  LMDJ_CHECK(status_identity(*f.controller->inspect_input(a.first)) == identity_a);
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 2 &&
      f.controller->inspect_ingress().held_release_metadata == 2);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().retained_completions == 2 &&
      f.port.engine.pattern_input_profile_status().held_release_reservations == 2);
  assert_foreign_fields(a);
  LMDJ_CHECK(status_identity(*f.controller->inspect_input(b.first)) == identity_b);
  f.input_settled(a.first, a.second);
  LMDJ_CHECK(!f.controller->inspect_input(a.first));
  LMDJ_CHECK(!f.port.engine.inspect_pattern_input_completion(7, frame_epoch, a.second.sequence));
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 1 &&
      f.controller->inspect_ingress().held_release_metadata == 2);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().retained_completions == 1 &&
      f.port.engine.pattern_input_profile_status().held_release_reservations == 2);

  // B stays occupied. C is a genuine fresh input after A's ordinary cell was
  // consumed; no private index or fabricated Native/owner result is observed.
  const auto c = press(82, 3, origin + 3);
  LMDJ_CHECK(c.first != a.first && c.first != b.first);
  wait_complete(c);
  LMDJ_CHECK(status_identity(*f.controller->inspect_input(b.first)) == identity_b);
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 2 &&
      f.controller->inspect_ingress().held_release_metadata == 3);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().retained_completions == 2 &&
      f.port.engine.pattern_input_profile_status().held_release_reservations == 3);
  assert_rejected_without_effect(c, a.first, "consumed A while fresh C is occupied");
  assert_foreign_fields(c);
  LMDJ_CHECK(status_identity(*f.controller->inspect_input(b.first)) == identity_b);
  f.input_settled(b.first, b.second);
  f.input_settled(c.first, c.second);
  LMDJ_CHECK(!f.controller->inspect_input(b.first) && !f.controller->inspect_input(c.first));
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 0 &&
      f.controller->inspect_ingress().ordinary_pending == 0 &&
      f.controller->inspect_ingress().held_release_metadata == 3);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().retained_completions == 0 &&
      f.port.engine.pattern_input_profile_status().held_release_reservations == 3);

  // Each real release is 24003 frames after its own actual press. At the
  // fixture's 120 BPM / 48 kHz this is an independent 960-tick duration,
  // rather than the unreleased/default 240-tick tail.
  f.port.render(24'000);
  const std::array<Input, 3> presses{a, b, c};
  for (std::size_t n = 0; n != presses.size(); ++n) {
    const auto slot = static_cast<std::uint8_t>(n + 1);
    const auto expected_frame = origin + 24'004 + n;
    LMDJ_CHECK(f.port.engine.telemetry().rendered_frames == expected_frame);
    const auto release = f.input(static_cast<unsigned>(90 + n), slot, false, presses[n].second.sequence);
    LMDJ_CHECK(release.second.authority.recording && release.second.authority.transport_epoch == start->epoch &&
        release.second.authority.schedule_serial == start->serial);
    f.port.render(1);
    const auto native = f.port.engine.inspect_pattern_input_completion(7, frame_epoch, release.second.sequence);
    LMDJ_CHECK(native && native->runtime_generation == 7 && native->frame_epoch == frame_epoch &&
        native->sequence == release.second.sequence && native->acceptance_ordinal == release.second.acceptance_ordinal &&
        native->authority == release.second.authority && native->slot == slot &&
        native->held_press_sequence == presses[n].second.sequence && native->runtime_frame == expected_frame &&
        native->disposition == audio::PatternInputDisposition::release_no_voice);
    f.native_complete(release.first, release.second);
    wait_complete(release);
    f.input_settled(release.first, release.second);
    LMDJ_CHECK(!f.controller->inspect_input(release.first));
    LMDJ_CHECK(!f.port.engine.inspect_pattern_input_completion(7, frame_epoch, release.second.sequence));
    LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == presses.size() - n - 1);
    LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == presses.size() - n - 1);
  }
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 0 &&
      f.controller->inspect_ingress().ordinary_pending == 0 &&
      f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().ordinary_pending == 0 &&
      f.port.engine.pattern_input_profile_status().retained_completions == 0 &&
      f.port.engine.pattern_input_profile_status().held_release_reservations == 0);

  const auto stop = f.request(3, 2, facade::PatternTransportIntent::play_stop);
  const auto expected_f = f.port.engine.telemetry().rendered_frames;
  LMDJ_CHECK(f.controller->request(stop) == facade::PatternTransportSubmit::accepted);
  LMDJ_CHECK(!f.port.inspect(7, 2));
  f.port.render(1);
  const auto real_f = f.port.inspect(7, 2);
  LMDJ_CHECK(real_f && real_f->runtime_generation == 7 && real_f->epoch == 2 &&
      !real_f->playing && real_f->origin_frame == origin && real_f->effective_frame == expected_f);
  f.settled();
  const auto closed = f.controller->inspect();
  LMDJ_CHECK(closed.phase == facade::PatternTransportPhase::idle && !closed.error &&
      !closed.recording && !closed.playing && closed.transport_epoch == real_f->epoch &&
      closed.origin_frame == real_f->origin_frame);
  LMDJ_CHECK(!f.port.inspect(7, 2)); // Actual Native F acknowledged after durable close.
  const auto scheduled = f.controller->inspect_count_in();
  LMDJ_CHECK(scheduled.start_receipt && scheduled.cancel_receipt && !scheduled.error);
  LMDJ_CHECK(scheduled.start_receipt->result == audio::ScheduledPatternResult::applied &&
      scheduled.start_receipt->origin_frame == origin && scheduled.start_receipt->effective_frame == origin);
  LMDJ_CHECK(scheduled.cancel_receipt->result == audio::ScheduledPatternResult::applied &&
      scheduled.cancel_receipt->epoch == real_f->epoch && scheduled.cancel_receipt->origin_frame == origin &&
      scheduled.cancel_receipt->effective_frame == expected_f && !scheduled.cancel_receipt->playing);
  LMDJ_CHECK(f.port.scheduled_quiescent());
  project_io::ProjectStore reader(f.storage->inner);
  const auto reopened = reader.load(f.bundle);
  LMDJ_CHECK(reopened.has_value());
  auto expected = f.initial;
  expected.revision = 1;
  expected.patterns.at(foundation::PatternId{pattern}).events = {
      {{0, 1}, 0, 960, 90}, {{0, 2}, 0, 960, 90}, {{0, 3}, 0, 960, 90}};
  lmdj::test::check(reopened.value() == expected,
      "public_input_ticket_identity_survives_real_consumption_and_occupied_reuse: three actual held performances keep independent complete Truth and real durations");
  project_io::SequenceJournal journal(f.storage->inner);
  const auto no_active = journal.read_active(f.bundle);
  LMDJ_CHECK(!no_active.has_value());
  LMDJ_CHECK(no_active.error().code == foundation::ErrorCode::not_found);
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(!f.controller->inspect_io().ticket && !f.controller->inspect_io().completion);
  LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 0 &&
      f.controller->inspect_ingress().ordinary_pending == 0 &&
      f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().ordinary_pending == 0 &&
      f.port.engine.pattern_input_profile_status().retained_completions == 0 &&
      f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
  LMDJ_CHECK(f.storage->worker != std::this_thread::get_id());
  LMDJ_CHECK(f.storage->writers == f.storage->leases_destroyed);
}
void live_pad_gating_preserves_recorded_press_and_release() {
  // Project playback is unmuted. These two real control states silence A02
  // independently of the existing Project-muted input journey above.
  for (const auto gates : {audio::PadGatesState{2, 0}, audio::PadGatesState{0, 1}}) {
    Fixture f;
    LMDJ_CHECK(f.port.engine.enqueue_pad_gates(gates.muted_mask, gates.solo_mask) ==
        audio::FxEnqueueResult::accepted);
    f.port.render(1);
    const auto applied = f.port.engine.pad_gates_status();
    LMDJ_CHECK(applied.applied.state.muted_mask == gates.muted_mask &&
        applied.applied.state.solo_mask == gates.solo_mask &&
        applied.applied.sequence == applied.accepted_sequence &&
        applied.applied.epoch == f.port.engine.telemetry().start_epoch);
    f.start();
    const auto frame_epoch = f.port.engine.telemetry().start_epoch;
    const auto voices_before = f.port.engine.telemetry().started_voices;
    const auto press = f.input(10, 1, true, 0, false);
    f.port.render(1);
    const auto native = f.port.engine.inspect_pattern_input_completion(
        7, frame_epoch, press.second.sequence);
    LMDJ_CHECK(native && native->disposition == audio::PatternInputDisposition::muted_no_voice);
    LMDJ_CHECK(f.port.engine.telemetry().started_voices == voices_before);
    f.native_complete(press.first, press.second);
    f.input_settled(press.first, press.second);
    LMDJ_CHECK(!f.controller->inspect_input(press.first));
    LMDJ_CHECK(!f.port.engine.inspect_pattern_input_completion(7, frame_epoch, press.second.sequence));
    LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
    LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);

    f.port.render(24'000);
    f.storage->arm(false);
    const auto release = f.input(11, 1, false, press.second.sequence, false);
    f.port.render(1);
    const auto native_release = f.port.engine.inspect_pattern_input_completion(
        7, frame_epoch, release.second.sequence);
    LMDJ_CHECK(native_release && native_release->disposition == audio::PatternInputDisposition::release_no_voice);
    f.native_complete(release.first, release.second);
    wait_for([&] { f.tick(); return f.storage->is_entered(); });
    LMDJ_CHECK(!f.controller->inspect_input(release.first)->complete);
    LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
    LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::record)) ==
        facade::PatternTransportSubmit::accepted);
    f.port.render(1); f.tick();
    LMDJ_CHECK(f.controller->inspect().playing);
    f.storage->release();
    f.input_settled(release.first, release.second);
    f.settled();
    LMDJ_CHECK(!f.controller->inspect().recording && !f.controller->inspect().error);
    LMDJ_CHECK(!f.controller->inspect_input(release.first));
    LMDJ_CHECK(!f.port.engine.inspect_pattern_input_completion(7, frame_epoch, release.second.sequence));
    LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
    LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);

    project_io::ProjectStore reader(f.storage->inner);
    const auto reopened = reader.load(f.bundle);
    LMDJ_CHECK(reopened.has_value());
    auto expected = f.initial;
    expected.revision = 1;
    expected.patterns.at(foundation::PatternId{pattern}).events = {{{0, 1}, 0, 960, 90}};
    LMDJ_CHECK(reopened.value() == expected);
    project_io::SequenceJournal journal(f.storage->inner);
    const auto no_active = journal.read_active(f.bundle);
    LMDJ_CHECK(!no_active.has_value() && no_active.error().code == foundation::ErrorCode::not_found);
    LMDJ_CHECK(f.controller->request(f.request(4, 3, facade::PatternTransportIntent::play_stop)) ==
        facade::PatternTransportSubmit::accepted);
    f.port.render(1); f.settled();
    LMDJ_CHECK(!f.controller->inspect().playing && !f.controller->inspect().error);
    LMDJ_CHECK(f.port.engine.enqueue_pad_gates(0, 0) == audio::FxEnqueueResult::accepted);
    f.port.render(128);
    LMDJ_CHECK(f.port.engine.telemetry().started_voices == voices_before);
    LMDJ_CHECK(f.port.scheduled_quiescent());
    f.controller->request_shutdown();
    wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
    LMDJ_CHECK(!f.controller->inspect_io().ticket && !f.controller->inspect_io().completion);
    LMDJ_CHECK(f.controller->inspect_ingress().retained_tickets == 0);
    LMDJ_CHECK(f.port.engine.pattern_input_profile_status().retained_completions == 0);
    LMDJ_CHECK(f.storage->worker != std::this_thread::get_id());
    LMDJ_CHECK(f.storage->writers == f.storage->leases_destroyed);
  }
}
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
std::atomic<unsigned> admission_sync_failures{};
std::atomic<bool> refuse_admission_sync{};
foundation::Result<void> fail_admission_sync(project_io::testing::FaultPoint point,
                                            const std::filesystem::path&) {
  if (point == project_io::testing::FaultPoint::active_journal_sync &&
      refuse_admission_sync.load(std::memory_order_acquire)) {
    ++admission_sync_failures;
    return foundation::Result<void>::failure({foundation::ErrorCode::io_error,
        "injected write-complete but sync-failed admission"});
  }
  return foundation::Result<void>::success();
}
struct AdmissionSyncFault {
  AdmissionSyncFault() {
    admission_sync_failures = 0;
    refuse_admission_sync = true;
    project_io::testing::set_fault_hook(fail_admission_sync);
  }
  ~AdmissionSyncFault() {
    refuse_admission_sync = false;
    project_io::testing::set_fault_hook(nullptr);
  }
};
void readable_admission_after_failed_sync_is_not_durable_completion() {
  Fixture f;
  f.start();
  AdmissionSyncFault fault;
  const auto press = f.input(10, 1, true);
  f.port.render(1); f.native_complete(press.first, press.second);
  wait_for([&] {
    f.tick();
    const auto input = f.controller->inspect_input(press.first);
    return input->complete || admission_sync_failures.load() >= 4;
  });
  const auto pending = f.controller->inspect_input(press.first);
  // Native wrote the candidate and failure closure, but every actual sync
  // failed. Readable exact bytes cannot release either durable consumer.
  LMDJ_CHECK(pending && !pending->complete && !pending->durable_settled && !pending->retained);
  LMDJ_CHECK(pending->native_result && pending->error);
  LMDJ_CHECK(admission_sync_failures.load() >= 4);
  LMDJ_CHECK(!f.controller->consume_input(press.first));
  LMDJ_CHECK(f.controller->inspect_io().ticket.has_value());
  project_io::SequenceJournal journal(f.storage->inner);
  const auto readable = journal.read_active(f.bundle);
  LMDJ_CHECK(readable.has_value() && readable.value().admission);
  LMDJ_CHECK(readable.value().admission->candidates.size() == 1);
  LMDJ_CHECK(readable.value().admission->closure &&
      readable.value().admission->closure->reason == project_io::SequenceAdmissionCloseReason::storage_failure);
  const auto original_native = *pending->native_result;
  refuse_admission_sync = false;
  wait_for([&] {
    f.tick();
    return f.controller->inspect_input(press.first)->complete;
  });
  const auto durable = f.controller->inspect_input(press.first);
  LMDJ_CHECK(durable->durable_settled && durable->retained && !durable->error);
  LMDJ_CHECK(durable->native_result.has_value());
  const auto& final_native = *durable->native_result;
  LMDJ_CHECK(final_native.runtime_generation == original_native.runtime_generation &&
      final_native.frame_epoch == original_native.frame_epoch &&
      final_native.sequence == original_native.sequence &&
      final_native.held_press_sequence == original_native.held_press_sequence &&
      final_native.acceptance_ordinal == original_native.acceptance_ordinal &&
      final_native.runtime_frame == original_native.runtime_frame &&
      final_native.slot == original_native.slot &&
      final_native.authority == original_native.authority &&
      final_native.disposition == original_native.disposition);
  f.input_settled(press.first, press.second);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
  f.port.render(24'000);
  const auto release = f.input(11, 1, false, press.second.sequence);
  f.port.render(1); f.native_complete(release.first, release.second);
  // The closed prefix cannot admit Release. Its original ticket must wait for
  // a real cutoff to settle the recording hold, even though Native is done.
  LMDJ_CHECK(!f.controller->inspect_input(release.first)->complete);
  LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::play_stop)) ==
      facade::PatternTransportSubmit::accepted);
  f.port.render(1);
  f.input_settled(release.first, release.second);
  f.settled();
  LMDJ_CHECK(!f.controller->inspect().playing && !f.controller->inspect().recording);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  const auto absent = journal.read_active(f.bundle);
  LMDJ_CHECK(!absent.has_value() && absent.error().code == foundation::ErrorCode::not_found);
  project_io::ProjectStore reader(f.storage->inner);
  auto expected = f.initial;
  expected.revision = 1;
  // Storage failure sealed the prefix before Release; only that exact prefix
  // is committed. The later real Release still settles its physical owners.
  expected.patterns.at(foundation::PatternId{pattern}).events = {{{0, 1}, 0, 240, 90}};
  LMDJ_CHECK(reader.load(f.bundle).value() == expected);
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.storage->writers == f.storage->leases_destroyed);
}
void readable_cutoff_after_failed_sync_keeps_its_original_work() {
  Fixture f;
  f.start();
  // Opening completion can still own its asynchronous projection. Do not
  // mistake that older work cell for the Stop whose durability is under test.
  wait_for([&] {
    f.tick();
    const auto io = f.controller->inspect_io();
    return io.ready && !io.ticket && !io.completion;
  });
  AdmissionSyncFault fault;
  LMDJ_CHECK(f.controller->request(f.request(3, 2, facade::PatternTransportIntent::play_stop)) ==
      facade::PatternTransportSubmit::accepted);
  const auto cutoff_frame = f.port.engine.telemetry().rendered_frames;
  f.port.render(1);
  wait_for([&] {
    f.tick();
    const auto io = f.controller->inspect_io();
    return io.ticket && io.ticket->command_id == foundation::CommandId{uuid(3)} &&
        io.ticket->transport_epoch == 2;
  });
  const auto work = f.controller->inspect_io().ticket;
  LMDJ_CHECK(work && work->runtime_generation == 7);
  wait_for([&] {
    f.tick();
    return f.controller->inspect_io().ticket != work || admission_sync_failures.load() >= 3;
  });
  LMDJ_CHECK(f.controller->inspect_io().ticket == work);
  LMDJ_CHECK(admission_sync_failures.load() >= 3);
  const auto count = f.controller->inspect_count_in();
  LMDJ_CHECK(count.cancel_receipt && count.cancel_receipt->effective_frame == cutoff_frame);
  LMDJ_CHECK(!f.controller->inspect().playing);
  project_io::SequenceJournal journal(f.storage->inner);
  const auto readback = journal.read_active(f.bundle);
  LMDJ_CHECK(readback.has_value() && readback.value().admission &&
      readback.value().admission->cutoff_fence &&
      readback.value().admission->cutoff_fence->effective_frame == cutoff_frame);
  refuse_admission_sync = false;
  f.settled();
  LMDJ_CHECK(!f.controller->inspect().recording && !f.controller->inspect().playing);
  const auto absent = journal.read_active(f.bundle);
  LMDJ_CHECK(!absent.has_value() && absent.error().code == foundation::ErrorCode::not_found);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.storage->writers == f.storage->leases_destroyed);
}
void readable_owner_loss_after_failed_sync_keeps_resource_debt() {
  Fixture f;
  f.start();
  const auto press = f.input(10, 1, true);
  f.port.render(1); f.native_complete(press.first, press.second);
  f.input_settled(press.first, press.second);
  f.port.engine.stop();
  AdmissionSyncFault fault;
  f.controller->request_shutdown();
  wait_for([&] {
    f.tick();
    return f.controller->shutdown_complete() || admission_sync_failures.load() >= 3;
  });
  LMDJ_CHECK(!f.controller->shutdown_complete());
  LMDJ_CHECK(f.controller->inspect_io().ticket.has_value());
  LMDJ_CHECK(!f.controller->inspect_input_owner().disposed);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 1);
  project_io::SequenceJournal journal(f.storage->inner);
  const auto readback = journal.read_active(f.bundle);
  LMDJ_CHECK(readback.has_value() && readback.value().state == project_io::SequenceSessionState::owner_lost);
  const auto path = f.bundle / "recovery/active/sequence.jsonl";
  const auto prefix = f.storage->inner->read_complete(path);
  LMDJ_CHECK(prefix.has_value());
  const auto failures = admission_sync_failures.load();
  wait_for([&] { f.tick(); return admission_sync_failures.load() >= failures + 3; });
  LMDJ_CHECK(!f.controller->shutdown_complete());
  LMDJ_CHECK(f.storage->inner->read_complete(path).value() == prefix.value());
  refuse_admission_sync = false;
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.controller->inspect_input_owner().disposed);
  LMDJ_CHECK(f.controller->inspect_ingress().held_release_metadata == 0);
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 1);
  project_io::ProjectStore reader(f.storage->inner);
  LMDJ_CHECK(reader.load(f.bundle).value() == f.initial);
  facade::ApplicationConfig config{};
  config.workspace_root = f.root;
  config.storage_platform = f.storage->inner;
  config.performance_replay_controller = facade::make_unavailable_performance_replay_controller();
  facade::Application application{std::move(config)};
  const auto recovery = application.list_sequence_recovery({f.bundle});
  LMDJ_CHECK(recovery.has_value() && recovery.value().size() == 1 && recovery.value()[0].reason == "owner_lost");
  LMDJ_CHECK(application.apply_sequence_recovery({f.bundle, foundation::SequenceSessionId{uuid(1)}, {}}).has_value());
  auto expected = f.initial;
  expected.revision = 1;
  expected.patterns.at(foundation::PatternId{pattern}).events = {{{0, 1}, 0, 240, 90}};
  LMDJ_CHECK(reader.load(f.bundle).value() == expected);
  const auto absent = journal.read_active(f.bundle);
  LMDJ_CHECK(!absent.has_value() && absent.error().code == foundation::ErrorCode::not_found);
  LMDJ_CHECK(f.port.engine.revoke_pattern_input_holds_quiescent(7));
  LMDJ_CHECK(f.port.engine.pattern_input_profile_status().held_release_reservations == 0);
  LMDJ_CHECK(f.storage->writers == f.storage->leases_destroyed);
}
// These direct worker component reductions complement the Controller journeys
// above. All owner creation, execute, reconciliation and destruction stay on
// one thread. They do not assert an Executor/Controller scheduling journey.
struct DirectDurabilityOwner {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-direct-owner-durability-" + std::to_string(::getpid()) + "-" +
       std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path bundle = root / "project.lmdj";
  std::shared_ptr<Storage> storage = std::make_shared<Storage>();
  Port port;
  foundation::SequenceSessionId session{uuid(1)};
  domain::ProjectState initial = std::move(domain::create_project(foundation::ProjectId{project}, 120).value());
  project_io::ProjectStore store{storage};
  project_io::SequenceJournal journal{storage};
  std::unique_ptr<facade::detail::PatternTransportIoOwner> owner;
  std::optional<project_io::SequenceAdmissionFence> opening;
  std::uint64_t next_step{1};

  facade::PatternTransportWorkRequest request(nlohmann::json payload,
      unsigned command = 2, std::uint64_t epoch = 1) {
    return {{7, epoch, foundation::CommandId{uuid(command)}, next_step++}, payload.dump()};
  }
  explicit DirectDurabilityOwner() {
    initial.patterns.emplace(foundation::PatternId{pattern},
        domain::Pattern{foundation::PatternId{pattern}, 1, {}});
    LMDJ_CHECK(store.create(bundle, initial).has_value());
    storage->observe = true;
    owner = std::make_unique<facade::detail::PatternTransportIoOwner>(
        facade::PatternTransportControllerConfig{bundle, session,
            foundation::ProjectId{project}, foundation::PatternId{pattern}, 7}, storage, nullptr);
    LMDJ_CHECK(port.submit({7, 1, port.pattern_generation(),
        audio::PatternTransportAction::start, {}}) == audio::PatternTransportSubmit::accepted);
    port.render(1);
    const auto native = port.inspect(7, 1);
    LMDJ_CHECK(native && native->playing);
    opening = project_io::SequenceAdmissionFence{project_io::SequenceFenceKind::admission,
        foundation::CommandId{uuid(2)}, native->epoch, native->effective_frame,
        native->origin_frame, native->pattern_id, native->pattern_generation,
        native->bpm, native->playing, {}, project_io::SequenceSwitchOutcome::none, {}};
    const auto open = request({{"op", "open"}, {"pattern", pattern},
        {"generation", native->pattern_generation}, {"revision", 0},
        {"started", facade::detail::transport_clock_stamp(std::chrono::steady_clock::now())},
        {"fence", facade::detail::encode_transport_fence(*opening)}});
    LMDJ_CHECK(owner->execute(open).outcome == facade::PatternTransportWorkOutcome::success);
    LMDJ_CHECK(read().admission->admission_fence == opening);
    LMDJ_CHECK(port.acknowledge(7, 1));
    unchanged_truth();
  }
  ~DirectDurabilityOwner() {
    owner.reset();
    std::error_code ignored;
    std::filesystem::remove_all(root, ignored);
  }
  std::filesystem::path path() const { return bundle / "recovery/active/sequence.jsonl"; }
  std::vector<std::byte> bytes() const {
    const auto result = storage->inner->read_complete(path());
    LMDJ_CHECK(result.has_value());
    return result.value();
  }
  project_io::ActiveSequenceJournal read() {
    const auto result = journal.read_active(bundle);
    LMDJ_CHECK(result.has_value() && result.value().admission);
    return result.value();
  }
  void unchanged_truth() {
    const auto truth = store.load(bundle);
    LMDJ_CHECK(truth.has_value() && truth.value() == initial);
    LMDJ_CHECK(storage->writers == storage->leases_destroyed);
  }
  struct Input {
    facade::PatternTransportWorkRequest work;
    project_io::SequenceAdmissionCandidate candidate;
    audio::PatternInputCompletion native;
  };
  Input input(bool pressed, std::uint64_t correlation = 0) {
    const auto frame = port.engine.telemetry().rendered_frames;
    const auto frame_epoch = port.engine.telemetry().start_epoch;
    const auto velocity = static_cast<std::uint8_t>(pressed ? 90 : 0);
    const auto admitted = port.engine.enqueue_pattern_input({7, frame_epoch, 1, velocity,
        !pressed, correlation, true,
        cooker::ResolvedPlayback{0, 128, domain::TriggerMode::loop_gate, 1.0F, true}});
    LMDJ_CHECK(admitted.result == audio::PatternInputSubmit::accepted);
    port.render(1);
    const auto native = port.engine.inspect_pattern_input_completion(7, frame_epoch, admitted.sequence);
    LMDJ_CHECK(native && native->sequence == admitted.sequence &&
        native->acceptance_ordinal == admitted.acceptance_ordinal && native->runtime_frame == frame);
    const project_io::SequenceAdmissionCandidate candidate{admitted.acceptance_ordinal + 9,
        frame, {0, 1}, pressed ? project_io::SequenceCandidateKind::press
                             : project_io::SequenceCandidateKind::release,
        velocity, pressed ? admitted.sequence : correlation};
    return {request({{"op", "admit"}, {"candidate", {
        {"watermark", candidate.watermark}, {"frame", candidate.runtime_frame},
        {"bank", 0}, {"pad", 1}, {"pressed", pressed}, {"velocity", velocity},
        {"correlation", candidate.press_sequence}}}}), candidate, *native};
  }
  void unchanged_native(const Input& input) {
    const auto current = port.engine.inspect_pattern_input_completion(
        input.native.runtime_generation, input.native.frame_epoch, input.native.sequence);
    LMDJ_CHECK(current && current->runtime_generation == input.native.runtime_generation &&
        current->frame_epoch == input.native.frame_epoch && current->sequence == input.native.sequence &&
        current->held_press_sequence == input.native.held_press_sequence &&
        current->acceptance_ordinal == input.native.acceptance_ordinal &&
        current->runtime_frame == input.native.runtime_frame && current->slot == input.native.slot &&
        current->authority == input.native.authority && current->disposition == input.native.disposition);
  }
  void consume_native(const Input& input) {
    unchanged_native(input);
    LMDJ_CHECK(port.engine.consume_pattern_input_completion(7, input.native.frame_epoch, input.native.sequence));
    LMDJ_CHECK(!port.engine.consume_pattern_input_completion(7, input.native.frame_epoch, input.native.sequence));
  }
  std::pair<Input, Input> recorded_pair() {
    auto press = input(true);
    const auto retained_press = owner->execute(press.work);
    LMDJ_CHECK(retained_press.outcome == facade::PatternTransportWorkOutcome::success &&
        nlohmann::json::parse(retained_press.payload).at("retained") == true);
    consume_native(press);
    port.render(5'999); // The two real input request frames are 6000 apart.
    auto release = input(false, press.native.sequence);
    const auto retained_release = owner->execute(release.work);
    LMDJ_CHECK(retained_release.outcome == facade::PatternTransportWorkOutcome::success &&
        nlohmann::json::parse(retained_release.payload).at("retained") == true);
    consume_native(release);
    LMDJ_CHECK(port.engine.pattern_input_profile_status().held_release_reservations == 0);
    unchanged_truth();
    return {std::move(press), std::move(release)};
  }
  void finish(const std::vector<domain::PatternEvent>& events) {
    LMDJ_CHECK(port.submit({7, 2, port.pattern_generation(),
        audio::PatternTransportAction::stop, {}}) == audio::PatternTransportSubmit::accepted);
    port.render(1);
    const auto native = port.inspect(7, 2);
    LMDJ_CHECK(native && !native->playing && native->effective_frame > native->origin_frame);
    const project_io::SequenceAdmissionFence cutoff{project_io::SequenceFenceKind::cutoff,
        foundation::CommandId{uuid(3)}, native->epoch, native->effective_frame,
        native->origin_frame, native->pattern_id, native->pattern_generation,
        native->bpm, native->playing, {}, project_io::SequenceSwitchOutcome::none, {}};
    const auto cutoff_work = request({{"op", "cutoff"},
        {"fence", facade::detail::encode_transport_fence(cutoff)}}, 3, 2);
    LMDJ_CHECK(owner->execute(cutoff_work).outcome == facade::PatternTransportWorkOutcome::success);
    const auto closed = read();
    LMDJ_CHECK(closed.admission->admission_fence == opening && closed.admission->cutoff_fence == cutoff);
    const auto close_work = request({{"op", "close"}, {"switched", false}}, 3, 2);
    LMDJ_CHECK(owner->execute(close_work).outcome == facade::PatternTransportWorkOutcome::success);
    auto expected = initial;
    if (!events.empty()) expected.revision = 1;
    expected.patterns.at(foundation::PatternId{pattern}).events = events;
    LMDJ_CHECK(store.load(bundle).value() == expected);
    const auto absent = journal.read_active(bundle);
    LMDJ_CHECK(!absent.has_value() && absent.error().code == foundation::ErrorCode::not_found);
    // Settled-close reconciliation verifies the exact retained flush identity;
    // execute is not reissued after the successful operation removed its file.
    LMDJ_CHECK(owner->reconcile(close_work).outcome == facade::PatternTransportWorkOutcome::success);
    LMDJ_CHECK(store.load(bundle).value() == expected);
    const auto still_absent = journal.read_active(bundle);
    LMDJ_CHECK(!still_absent.has_value() && still_absent.error().code == foundation::ErrorCode::not_found);
    LMDJ_CHECK(port.acknowledge(7, 2) && port.ordinary_ack_calls == 2 && port.ordinary_submit_calls == 2);
    LMDJ_CHECK(port.engine.pattern_input_profile_status().retained_completions == 0);
    LMDJ_CHECK(port.engine.pattern_input_profile_status().held_release_reservations == 0);
    LMDJ_CHECK(storage->writers == storage->leases_destroyed);
  }
};

// One optional pre-write failure excludes only the original candidate. Every
// later sync still reaches the real native append path after write_all, so a
// readable closure/overlay/receipt never serves as invented durability proof.
struct DirectOwnerSyncFault {
  inline static DirectOwnerSyncFault* active{};
  bool reject_first_write{};
  bool refuse_sync{true};
  unsigned rejected_writes{}, failed_syncs{}, sync_calls{};
  explicit DirectOwnerSyncFault(bool reject_candidate = false)
      : reject_first_write(reject_candidate) {
    LMDJ_CHECK(active == nullptr);
    active = this;
    project_io::testing::set_fault_hook(inject);
  }
  ~DirectOwnerSyncFault() {
    project_io::testing::set_fault_hook(nullptr);
    active = nullptr;
  }
  static foundation::Result<void> inject(project_io::testing::FaultPoint point,
                                          const std::filesystem::path& path) {
    if (!active || path.filename() != "sequence.jsonl") return foundation::Result<void>::success();
    if (point == project_io::testing::FaultPoint::sequence_journal_write && active->reject_first_write) {
      active->reject_first_write = false;
      ++active->rejected_writes;
      return foundation::Result<void>::failure({foundation::ErrorCode::io_error,
          "injected original candidate failure before write"});
    }
    if (point == project_io::testing::FaultPoint::active_journal_sync) {
      ++active->sync_calls;
      if (active->refuse_sync) {
        ++active->failed_syncs;
        return foundation::Result<void>::failure({foundation::ErrorCode::io_error,
            "injected direct owner write-complete but sync-failed admission"});
      }
    }
    return foundation::Result<void>::success();
  }
};

void transferred_candidate_replay_requires_real_durable_reconciliation() {
  DirectDurabilityOwner f;
  const auto inputs = f.recorded_pair();
  const std::vector<domain::PatternEvent> events{{{0, 1}, 0, 240, 90}};
  const auto identity = f.read().admission->preparation.identity;
  // Real conversion and Journal append form the historical receipt. This is
  // the worker's idempotent replay defense, not a Controller resubmission or
  // a claim that the single occupied work cell can advance other input.
  const auto transfer = facade::detail::commit_admission_transfer(f.journal, f.bundle, f.session,
      identity, foundation::CommandId{uuid(90)}, inputs.second.candidate.watermark, false);
  LMDJ_CHECK(transfer.has_value() && transfer.value().recoverable_tail == events);
  const auto transferred = f.read();
  LMDJ_CHECK(transferred.admission->candidates.empty() && transferred.admission->transfers.size() == 1);
  LMDJ_CHECK(transferred.admission->transfers.front() == transfer.value());
  LMDJ_CHECK(transfer.value().candidate_receipts == std::vector<project_io::SequenceCandidateReceipt>({
      project_io::sequence_admission_candidate_receipt(inputs.first.candidate),
      project_io::sequence_admission_candidate_receipt(inputs.second.candidate)}));
  DirectOwnerSyncFault fault;
  const auto unknown = f.owner->execute(inputs.first.work);
  LMDJ_CHECK(unknown.outcome == facade::PatternTransportWorkOutcome::unknown && unknown.error &&
      unknown.error->code == foundation::ErrorCode::io_error);
  LMDJ_CHECK(unknown.error->details.at("closure_unresolved") == true);
  LMDJ_CHECK(fault.failed_syncs == 2); // Historical candidate sync, then real failure closure sync.
  const auto readback = f.read();
  auto expected_readback = transferred;
  expected_readback.admission->closure = project_io::SequenceAdmissionClosure{
      inputs.second.candidate.watermark, project_io::SequenceAdmissionCloseReason::storage_failure};
  LMDJ_CHECK(readback == expected_readback && readback.pending_events == events);
  const auto prefix = f.bytes();
  const auto failures = fault.failed_syncs;
  LMDJ_CHECK(f.owner->reconcile(inputs.first.work).outcome == facade::PatternTransportWorkOutcome::unknown);
  LMDJ_CHECK(fault.failed_syncs == failures + 1 && f.bytes() == prefix && f.read() == readback);
  f.unchanged_truth();
  fault.refuse_sync = false;
  const auto syncs = fault.sync_calls;
  const auto durable = f.owner->reconcile(inputs.first.work);
  LMDJ_CHECK(durable.outcome == facade::PatternTransportWorkOutcome::success &&
      nlohmann::json::parse(durable.payload).at("retained") == true);
  LMDJ_CHECK(fault.sync_calls == syncs + 1 && f.bytes() == prefix && f.read() == readback);
  f.unchanged_truth();
  f.finish(events);
}

void absent_candidate_refusal_requires_its_real_failure_closure_sync() {
  DirectDurabilityOwner f;
  const auto input = f.input(true);
  const auto before = f.read();
  DirectOwnerSyncFault fault(true);
  const auto unknown = f.owner->execute(input.work);
  LMDJ_CHECK(unknown.outcome == facade::PatternTransportWorkOutcome::unknown && unknown.error &&
      unknown.error->code == foundation::ErrorCode::io_error);
  LMDJ_CHECK(fault.rejected_writes == 1 && fault.failed_syncs == 1);
  LMDJ_CHECK(unknown.error->details.at("closure_unresolved") == true);
  const auto readback = f.read();
  auto expected_readback = before;
  expected_readback.admission->closure = project_io::SequenceAdmissionClosure{
      std::nullopt, project_io::SequenceAdmissionCloseReason::storage_failure};
  LMDJ_CHECK(readback == expected_readback && readback.admission->candidates.empty() &&
      readback.admission->transfers.empty());
  const auto prefix = f.bytes();
  LMDJ_CHECK(f.owner->reconcile(input.work).outcome == facade::PatternTransportWorkOutcome::unknown);
  LMDJ_CHECK(fault.failed_syncs == 2 && f.bytes() == prefix && f.read() == readback);
  f.unchanged_native(input);
  f.unchanged_truth();
  fault.refuse_sync = false;
  const auto syncs = fault.sync_calls;
  const auto refused = f.owner->reconcile(input.work);
  LMDJ_CHECK(refused.outcome == facade::PatternTransportWorkOutcome::refused && refused.error);
  LMDJ_CHECK(refused.error->details.at("reconciled") == true &&
      refused.error->details.at("retryable") == false);
  LMDJ_CHECK(fault.sync_calls == syncs + 1 && f.bytes() == prefix && f.read() == readback);
  f.unchanged_truth();
  f.consume_native(input);
  const auto release = f.input(false, input.native.sequence);
  const auto live_only = f.owner->execute(release.work);
  LMDJ_CHECK(live_only.outcome == facade::PatternTransportWorkOutcome::success &&
      nlohmann::json::parse(live_only.payload).at("retained") == false);
  f.consume_native(release);
  LMDJ_CHECK(f.bytes() == prefix && f.read() == readback);
  f.finish({});
}

void readable_overlay_generation_requires_real_durable_reconciliation() {
  DirectDurabilityOwner f;
  const auto inputs = f.recorded_pair();
  static_cast<void>(inputs);
  const std::vector<domain::PatternEvent> events{{{0, 1}, 0, 240, 90}};
  const auto projected = facade::detail::project_admission_overlay(f.read(), false);
  LMDJ_CHECK(projected.has_value() && projected.value() && *projected.value() == events);
  auto sample = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{48'000, 1,
      std::vector<std::int16_t>(128, 1000)});
  cooker::RuntimeSnapshot snapshot{foundation::ProjectId{project}, foundation::PatternId{pattern}, 1,
      120, 1, domain::kPpq, domain::kBarTicks4x4, {}, {}};
  snapshot.pads.emplace_back(domain::PadSlotId{0, 1},
      foundation::ArtifactRef{std::string(64, 'a'), "audio/wav", 256}, sample,
      cooker::ResolvedPlayback{0, 128, domain::TriggerMode::loop_gate, 1.0F, false});
  auto view = audio::PreparedPatternView::from_snapshot_with_overlay(snapshot, *projected.value());
  LMDJ_CHECK(view.has_value());
  const auto publication = f.port.engine.publish_pattern_view(std::move(view.value()));
  LMDJ_CHECK(publication.result == audio::PatternPublishResult::accepted);
  const auto frame = f.port.engine.telemetry().rendered_frames;
  LMDJ_CHECK(publication.activation_frame >= frame);
  f.port.render(publication.activation_frame - frame + 1);
  LMDJ_CHECK(f.port.pattern_generation() == publication.generation);
  const auto work = f.request({{"op", "overlay"}, {"generation", publication.generation}});
  const auto before = f.read();
  const auto before_bytes = f.bytes();
  DirectOwnerSyncFault fault;
  const auto unknown = f.owner->execute(work);
  LMDJ_CHECK(unknown.outcome == facade::PatternTransportWorkOutcome::unknown && unknown.error &&
      unknown.error->code == foundation::ErrorCode::io_error);
  LMDJ_CHECK(fault.failed_syncs == 1);
  const auto readback = f.read();
  auto expected_readback = before;
  expected_readback.admission->published_generation = publication.generation;
  LMDJ_CHECK(readback == expected_readback && f.bytes().size() > before_bytes.size());
  const auto prefix = f.bytes();
  LMDJ_CHECK(f.owner->reconcile(work).outcome == facade::PatternTransportWorkOutcome::unknown);
  LMDJ_CHECK(fault.failed_syncs == 2 && f.bytes() == prefix && f.read() == readback);
  f.unchanged_truth();
  fault.refuse_sync = false;
  const auto syncs = fault.sync_calls;
  LMDJ_CHECK(f.owner->reconcile(work).outcome == facade::PatternTransportWorkOutcome::success);
  LMDJ_CHECK(fault.sync_calls == syncs + 1 && f.bytes() == prefix && f.read() == readback);
  f.unchanged_truth();
  f.finish(events);
}

#endif
}  // namespace
namespace {
struct Case {
  const char* label;
  void (*run)();
};
struct Shard {
  std::string_view name;
  std::string_view group;
  std::span<const Case> cases;
};
// Each shard is one CTest registration with its own component budget. The
// deadline shards spend most of their time in real sleeps past the production
// steady-clock deadlines (1 s input, 5 s opening), which the controller reads
// directly, so no shard may grow to hold two of those families (#2238).
constexpr std::array kJourneyCases{
    Case{"winning_cancel_has_no_storage_or_truth_effect", winning_cancel_has_no_storage_or_truth_effect},
    Case{"refused_before_start_settles_native_without_storage_work", refused_before_start_settles_native_without_storage_work},
    Case{"completed_opening_retains_the_count_in_lineage_until_a_later_real_cutoff", completed_opening_retains_the_count_in_lineage_until_a_later_real_cutoff},
    Case{"held_begin_retains_actual_start_and_stop", held_begin_retains_actual_start_and_stop},
    Case{"silent_press_ticket_consumption_preserves_release_and_actual_duration", silent_press_ticket_consumption_preserves_release_and_actual_duration},
    Case{"independent_metadata_partitions_keep_reserved_release_available", independent_metadata_partitions_keep_reserved_release_available},
    Case{"toggle_stopped_press_consumption_preserves_both_real_releases", toggle_stopped_press_consumption_preserves_both_real_releases},
    Case{"post_open_owner_invalidation_preserves_prefix_until_real_recovery", post_open_owner_invalidation_preserves_prefix_until_real_recovery},
    Case{"shutdown_preserves_only_owned_live_releases_until_acknowledged", shutdown_preserves_only_owned_live_releases_until_acknowledged},
    Case{"pre_start_press_and_post_start_release_stay_live_only", pre_start_press_and_post_start_release_stay_live_only},
    Case{"two_bars_at_40_bpm_do_not_spend_the_opening_budget_before_s", two_bars_at_40_bpm_do_not_spend_the_opening_budget_before_s},
    Case{"exceptional_direct_stop_preserves_failure_and_owner_loss_recovery", exceptional_direct_stop_preserves_failure_and_owner_loss_recovery},
    Case{"exceptional_owner_ack_requires_real_disposition_and_each_consumer", exceptional_owner_ack_requires_real_disposition_and_each_consumer},
    Case{"exceptional_owner_ack_preserves_queued_invalidated_release", exceptional_owner_ack_preserves_queued_invalidated_release},
    Case{"never_recorded_owner_disposition_uses_actual_input_and_no_journal", never_recorded_owner_disposition_uses_actual_input_and_no_journal},
    Case{"real_record_off_close_keeps_physical_owner_until_exceptional_disposition", real_record_off_close_keeps_physical_owner_until_exceptional_disposition},
};
constexpr std::array kInputExpiryCases{
    Case{"expired_press_keeps_its_exact_work_and_future_release", expired_press_keeps_its_exact_work_and_future_release},
    Case{"mixed_age_expiry_survives_real_durable_completion_and_fresh_cell_reuse", mixed_age_expiry_survives_real_durable_completion_and_fresh_cell_reuse},
};
constexpr std::array kOpeningExpiryCases{
    Case{"opening_expiry_retains_e1_and_uses_a_real_stop", opening_expiry_retains_e1_and_uses_a_real_stop},
};
constexpr std::array kOpeningReconciliationCases{
    Case{"known_durable_opening_survives_held_delivery_and_late_exact_reconciliation_default",
         [] { known_durable_opening_survives_held_delivery_and_late_exact_reconciliation(); }},
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
    Case{"known_durable_opening_survives_held_delivery_and_late_exact_reconciliation_true",
         [] { known_durable_opening_survives_held_delivery_and_late_exact_reconciliation(true); }},
#endif
};
constexpr std::array kIngressCases{
    Case{"public_input_ticket_identity_survives_real_consumption_and_occupied_reuse", public_input_ticket_identity_survives_real_consumption_and_occupied_reuse},
    Case{"live_pad_gating_preserves_recorded_press_and_release", live_pad_gating_preserves_recorded_press_and_release},
};
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
constexpr std::array kDurabilityCases{
    Case{"readable_admission_after_failed_sync_is_not_durable_completion", readable_admission_after_failed_sync_is_not_durable_completion},
    Case{"readable_cutoff_after_failed_sync_keeps_its_original_work", readable_cutoff_after_failed_sync_keeps_its_original_work},
    Case{"readable_owner_loss_after_failed_sync_keeps_resource_debt", readable_owner_loss_after_failed_sync_keeps_resource_debt},
    Case{"transferred_candidate_replay_requires_real_durable_reconciliation", transferred_candidate_replay_requires_real_durable_reconciliation},
    Case{"absent_candidate_refusal_requires_its_real_failure_closure_sync", absent_candidate_refusal_requires_its_real_failure_closure_sync},
    Case{"readable_overlay_generation_requires_real_durable_reconciliation", readable_overlay_generation_requires_real_durable_reconciliation},
};
#endif
// The first shard is the journey family --stress repeats; the rest run once.
constexpr std::array kShards{
    Shard{"journeys", "repeat", kJourneyCases},
    Shard{"input-expiry", "tail", kInputExpiryCases},
    Shard{"opening-expiry", "tail", kOpeningExpiryCases},
    Shard{"opening-reconciliation", "tail", kOpeningReconciliationCases},
    Shard{"ingress", "tail", kIngressCases},
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    Shard{"durability", "tail", kDurabilityCases},
#endif
};
void emit_boundary(const char* phase, const char* label, std::string_view group,
                   unsigned round, std::size_t slot) {
  std::cerr << "S6_CASE phase=" << phase << " label=" << label << " group=" << group
            << " round=" << round << " slot=" << slot << '\n' << std::flush;
}
std::size_t run(const Shard& shard, unsigned round) {
  std::size_t slot{};
  for (const auto& entry : shard.cases) {
    ++slot;
    emit_boundary("BEGIN", entry.label, shard.group, round, slot);
    entry.run();
    emit_boundary("END", entry.label, shard.group, round, slot);
  }
  return shard.cases.size();
}
// --stress repeats the journey family kStressRounds times, then runs every
// other shard once. One round builds its own engine, controller and temporary
// Project, so rounds share no state and run in parallel child processes. Run
// in sequence they cost ~185 s Release and over 1200 s TSan, mostly in the
// 1024-input metadata journey, and pushed both batch stress jobs past their
// limits (#2261). The deadline shards still run here, one at a time, after
// every round has passed, so their real 1 s / 5 s waits compete with no worker.
constexpr unsigned kStressRounds = 64;
struct Rounds { unsigned first; unsigned last; };
constexpr std::string_view kRoundsFlag{"--stress-rounds="};
std::optional<Rounds> parse_rounds(std::string_view text) {
  const auto dash = text.find('-');
  if (dash == std::string_view::npos) return std::nullopt;
  try {
    const auto first = std::stoul(std::string{text.substr(0, dash)});
    const auto last = std::stoul(std::string{text.substr(dash + 1)});
    if (first < 1 || first > last || last > kStressRounds) return std::nullopt;
    return Rounds{static_cast<unsigned>(first), static_cast<unsigned>(last)};
  } catch (const std::exception&) {
    return std::nullopt;
  }
}
std::size_t run_rounds(Rounds rounds) {
  std::size_t executed{};
  for (unsigned round = rounds.first; round <= rounds.last; ++round)
    executed += run(kShards.front(), round);
  return executed;
}
// A worker keeps two threads runnable: wait_for spins on its predicate while
// the Pattern transport executor does the durable work it waits on. Under
// ASan a lone round on the M1 already spends about 1 s of the 3 s settle
// deadline on each of the metadata journey's 512th and 1024th settles, and
// eight ASan workers (sixteen spinning or working threads on four performance
// and four efficiency cores) pushed one past it (run 39107252620). Instrumented
// builds therefore give each worker two hardware threads. The deadline, all
// 64 rounds and every case are unchanged; only fewer rounds overlap.
#if defined(__SANITIZE_ADDRESS__) || defined(__SANITIZE_THREAD__)
constexpr unsigned kThreadsPerWorker = 2;
#elif defined(__has_feature)
#if __has_feature(address_sanitizer) || __has_feature(thread_sanitizer)
constexpr unsigned kThreadsPerWorker = 2;
#else
constexpr unsigned kThreadsPerWorker = 1;
#endif
#else
constexpr unsigned kThreadsPerWorker = 1;
#endif
// Every round must run and pass in some worker: a worker that exits nonzero,
// is signalled or cannot be started fails the whole registration.
bool run_rounds_in_workers() {
  // No more workers than rounds, so every worker's slice is non-empty and the
  // slices partition 1..kStressRounds exactly.
  const auto workers = std::min(
      std::clamp(std::thread::hardware_concurrency() / kThreadsPerWorker, 1U, 8U), kStressRounds);
  std::vector<std::pair<Rounds, pid_t>> children;
  bool passed = true;
  for (unsigned worker = 0; worker != workers; ++worker) {
    const Rounds rounds{worker * kStressRounds / workers + 1,
                        (worker + 1) * kStressRounds / workers};
    try {
      children.emplace_back(rounds, lmdj::test::process::spawn(
          {std::string{kRoundsFlag} + std::to_string(rounds.first) + "-" + std::to_string(rounds.last)}));
    } catch (const std::exception& error) {
      std::cerr << "stress rounds " << rounds.first << '-' << rounds.last
                << " could not start: " << error.what() << '\n';
      passed = false;
      break;  // The verdict is already failed: start no more, reap the rest.
    }
  }
  for (const auto& [rounds, child] : children) {
    int status{};
    pid_t reaped{};
    do { reaped = ::waitpid(child, &status, 0); } while (reaped == -1 && errno == EINTR);
    if (reaped != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
      std::cerr << "stress rounds " << rounds.first << '-' << rounds.last << " failed: "
                << (reaped != child ? "not reaped"
                    : WIFSIGNALED(status) ? "signal " + std::to_string(WTERMSIG(status))
                    : "exit " + std::to_string(WEXITSTATUS(status))) << '\n';
      passed = false;
    }
  }
  return passed;
}
}  // namespace

int main(int argc, char** argv) {
  lmdj::test::process::initialize(argv[0]);
  const auto selected = argc == 2 ? std::string_view{argv[1]} : std::string_view{};
  if (selected == "--list-shards") {
    std::size_t total{};
    for (const auto& shard : kShards) {
      std::cout << shard.name << ' ' << shard.cases.size() << '\n';
      total += shard.cases.size();
    }
    std::cout << "all " << total << '\n';
    return 0;
  }
  // Internal worker mode for --stress only: it runs a slice of the journey
  // rounds and none of the other shards. It is deliberately absent from the
  // usage text, and the Facade sharding gate rejects any CTest registration
  // that uses it.
  if (selected.starts_with(kRoundsFlag)) {
    const auto rounds = parse_rounds(selected.substr(kRoundsFlag.size()));
    if (!rounds) {
      std::cerr << "invalid --stress-rounds range\n";
      return 2;
    }
    const auto executed = run_rounds(*rounds);
    LMDJ_CHECK(executed == (rounds->last - rounds->first + 1) * kShards.front().cases.size());
    return 0;
  }
  const std::string_view prefix{"--shard="};
  const bool stress = selected == "--stress";
  if (argc > 2 || (argc == 2 && !stress && !selected.starts_with(prefix))) {
    std::cerr << "usage: lmdj_pattern_count_in_tests [--list-shards|--shard=<name>|--stress]\n";
    return 2;
  }
  const auto shard_name = selected.starts_with(prefix) ? selected.substr(prefix.size()) : std::string_view{};
  std::size_t executed{};
  if (stress) {
    if (!run_rounds_in_workers()) return 1;
    executed += kStressRounds * kShards.front().cases.size();
  }
  for (const auto& shard : kShards) {
    if (!shard_name.empty() && shard.name != shard_name) continue;
    const bool repeated = shard.group == "repeat";
    if (stress && repeated) continue;
    executed += run(shard, repeated ? 1U : 0U);
  }
  if (executed == 0) {
    std::cerr << "unknown pattern count-in shard\n";
    return 2;
  }
  std::cout << "Facade scheduled transport held-IO journeys: " << executed << " cases passed\n";
}
