#include <lmdj/facade/pattern_transport_controller.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <source_location>
#include <string_view>
#include <exception>
#include <span>
#include <thread>
#include <vector>
#include "packages/application-facade/internal/lmdj/facade/pattern_transport_controller_factory.hpp"
#include "tests/core/support/test.hpp"
namespace {
using namespace lmdj;
constexpr auto project = "00000000-0000-4000-8000-000000000004";
constexpr auto pattern = "00000000-0000-4000-8000-000000000002";
std::string uuid(std::uint64_t value) {
  const auto tail = std::to_string(value);
  return "00000000-0000-4000-8000-" + std::string(12-tail.size(),'0') + tail;
}
template<class P> void wait_for(P predicate, std::source_location where = std::source_location::current()) {
  const auto until = std::chrono::steady_clock::now() + std::chrono::seconds{3};
  while (!predicate()) {
    if (std::chrono::steady_clock::now() >= until)
      throw std::runtime_error(std::string(where.file_name())+":"+std::to_string(where.line())+": wait timed out");
    std::this_thread::yield();
  }
}
struct Storage final : project_io::ProjectStoragePlatform,
                       project_io::ProjectJournalLayoutValidator,
                       project_io::ProjectStorageTextReader {
  std::shared_ptr<project_io::ProjectStoragePlatform> inner{project_io::make_default_project_storage_platform()};
  mutable std::mutex mutex;
  std::condition_variable cv;
  bool hold_begin{}, hold_append{}, entered{}, released{};
  std::string hold_kind;
  std::string fail_kind;
  bool fail_after{};
  bool failed{};
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
  void arm_kind(std::string kind) { std::lock_guard lock(mutex); hold_kind = std::move(kind); hold_append = true; entered = released = false; }
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
    const auto text = bytes.empty() ? std::string{} : std::string(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    if (p.filename() == "sequence.jsonl" && !hold_kind.empty() && text.find("\"kind\":\"" + hold_kind + "\"") != std::string::npos) gate(false);
    const bool fail = !fail_kind.empty() && text.find("\"kind\":\"" + fail_kind + "\"") != std::string::npos;
    if (fail) { fail_kind.clear(); failed = true; }
    const auto error = [] { return foundation::Result<void>::failure(
        {foundation::ErrorCode::io_error,"injected switch append failure"}); };
    if (fail && !fail_after) return error();
    const auto result = inner->append_durable(p, prefix, bytes);
    return fail && result.has_value() ? error() : result;
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
  std::shared_ptr<const cooker::PcmSample> sample;
  unsigned overlay_calls{};
  bool allow_overlay{};
  unsigned ordinary_ack_calls{}, scheduled_ack_calls{}, ordinary_submit_calls{};
  std::optional<audio::PatternTransportSubmit> ordinary_submit_result;
  explicit Port(std::uint16_t bpm = 120) {
    LMDJ_CHECK(engine.enable_pattern_transport(7).has_value());
    LMDJ_CHECK(engine.enable_scheduled_pattern_record(7).has_value());
    LMDJ_CHECK(engine.enable_pattern_input_profile(7).has_value());
    sample = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(128, 1000)});
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
  std::optional<audio::PatternReplacementAuthority> pending_switch() const override {
    const auto o = engine.pattern_transport_observation();
    return o ? (o->pending_switches[1] ? o->pending_switches[1] : o->pending_switches[0]) : std::nullopt;
  }
  bool supports_receipt_bound_opening() const override { return true; }
  std::optional<audio::PatternTransportObservation> observe_transport() const override { return engine.pattern_transport_observation(); }
  bool cancel_overlay(const audio::PatternReplacementAuthority& a) override { return engine.cancel_pattern_publication(a); }
  audio::PreparedPatternView view(foundation::PatternId id, std::span<const domain::PatternEvent> events = {}, std::uint64_t revision = 1) {
    cooker::RuntimeSnapshot snapshot{foundation::ProjectId{project}, id, revision, 120, 1,
        domain::kPpq, domain::kBarTicks4x4, {}, {}};
    for (std::uint8_t pad = 0; pad != 4; ++pad)
      snapshot.pads.emplace_back(domain::PadSlotId{0,pad}, foundation::ArtifactRef{std::string(64,'a'), "audio/wav",256},
          sample, cooker::ResolvedPlayback{0,128,domain::TriggerMode::loop_gate,1.0F,false});
    for (const auto& e : events)
      snapshot.events.push_back({e.slot,e.onset_tick,e.duration_tick,e.velocity,sample});
    auto prepared = audio::PreparedPatternView::from_snapshot(snapshot);
    LMDJ_CHECK(prepared.has_value());
    return std::move(prepared.value());
  }
  foundation::Result<audio::PatternPublication> publish_overlay(const foundation::PatternId& id,
      std::span<const domain::PatternEvent> events) override {
    ++overlay_calls;
    if (!allow_overlay) return foundation::Result<audio::PatternPublication>::failure(
        {foundation::ErrorCode::unsupported_audio,"test overlay disabled"});
    const auto result = engine.publish_pattern_view(view(id,events));
    if (result.result != audio::PatternPublishResult::accepted)
      return foundation::Result<audio::PatternPublication>::failure({foundation::ErrorCode::invalid_argument,"overlay refused"});
    return foundation::Result<audio::PatternPublication>::success(result);
  }
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
      ("lmdj-switch-control-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path bundle = root / "project.lmdj";
  std::shared_ptr<Storage> storage = std::make_shared<Storage>();
  Port port;
  foundation::PatternId a{pattern}, b{uuid(9)}, c{uuid(10)}, d{uuid(11)};
  std::unique_ptr<facade::PatternTransportController> controller;
  struct Publication {
    facade::PatternTransportSwitchTicket ticket;
    audio::RetainedPatternPublication native;
  };
  Fixture() {
    auto initial = domain::create_project(foundation::ProjectId{project},120).value();
    for (const auto& id : {a,b,c,d}) initial.patterns.emplace(id, domain::Pattern{id,1,{}});
    LMDJ_CHECK(project_io::ProjectStore{storage}.create(bundle,initial).has_value());
    storage->observe = true;
    controller = facade::detail::PatternTransportControllerInternalFactory::make(port,
        {bundle,foundation::SequenceSessionId{uuid(1)},foundation::ProjectId{project},a,7},storage,{}, {},&port);
    wait_for([&] { return controller->inspect_io().ready; });
  }
  ~Fixture() {
    storage->release();
    controller.reset();
    std::error_code ignored;
    std::filesystem::remove_all(root,ignored);
  }
  void tick() { static_cast<void>(controller->continue_operation()); }
  facade::PatternTransportRequest request(unsigned id, std::uint64_t epoch,
                                           facade::PatternTransportIntent intent) {
    return {foundation::SequenceSessionId{uuid(1)},foundation::ProjectId{project},
        foundation::CommandId{uuid(id)},7,epoch,intent,{}};
  }
  void start(bool count_in = false) {
    if (count_in) {
      LMDJ_CHECK(controller->request_count_in({request(2,1,facade::PatternTransportIntent::record),
          port.engine.telemetry().start_epoch,1,1}) == facade::PatternTransportSubmit::accepted);
      port.render(1); tick();
      const auto armed = controller->inspect_count_in();
      LMDJ_CHECK(armed.count_in && armed.count_in->start_frame);
      until(*armed.count_in->start_frame + 1);
    } else {
      LMDJ_CHECK(controller->request(request(2,1,facade::PatternTransportIntent::record)) == facade::PatternTransportSubmit::accepted);
      wait_for([&] { tick(); return controller->inspect().phase == facade::PatternTransportPhase::awaiting_audio; });
      port.render(1);
    }
    wait_for([&] { tick(); return controller->inspect().recording; });
    idle();
  }
  void until(std::uint64_t frame) {
    LMDJ_CHECK(port.engine.telemetry().rendered_frames <= frame);
    port.render(frame - port.engine.telemetry().rendered_frames);
  }
  void idle() { wait_for([&] { tick(); return !controller->inspect_io().ticket; }); }
  Publication publish(foundation::PatternId target,
                      std::optional<audio::PatternReplacementAuthority> replacement = {}) {
    std::optional<facade::PatternTransportSwitchTicket> ticket;
    wait_for([&] {
      tick();
      const auto result = controller->reserve_pattern_switch({7,target});
      if (result.has_value()) ticket = result.value();
      return ticket.has_value();
    });
    const auto truth = project_io::ProjectStore{storage->inner}.load(bundle);
    LMDJ_CHECK(truth.has_value());
    auto native = port.engine.publish_retained_pattern_switch_view(
        port.view(target,truth.value().patterns.at(target).events,truth.value().revision),audio::PatternSwitchSnap::beat,replacement);
    LMDJ_CHECK(native.publication.result == audio::PatternPublishResult::accepted && native.lease);
    LMDJ_CHECK(controller->bind_pattern_switch(*ticket,
        {native.publication.generation,target,native.publication.activation_frame},120));
    LMDJ_CHECK(!controller->abandon_pattern_switch(*ticket));
    return {*ticket,std::move(native)};
  }
  void observe(Publication& p) {
    const auto o = port.engine.observe_pattern_publication(p.native.lease);
    LMDJ_CHECK(o && controller->complete_pattern_switch(p.ticket,*o));
  }
  void applied(Publication& p) {
    until(p.native.publication.activation_frame + 1);
    observe(p);
    const auto status = controller->inspect_pattern_switch(p.ticket);
    LMDJ_CHECK(status && status->native_result && status->native_result->applied_frame);
  }
  void settled(Publication& p) {
    wait_for([&] { tick(); const auto s = controller->inspect_pattern_switch(p.ticket); return s && s->complete; });
    const auto s = controller->inspect_pattern_switch(p.ticket);
    if (s->error) std::cerr << s->error->message << ' ' << s->error->details.dump() << '\n';
    LMDJ_CHECK(s->durable_settled && !s->owner_disposed && !s->error);
  }
  void retire(Publication& p) {
    LMDJ_CHECK(controller->inspect_pattern_switch(p.ticket)->complete);
    p.native.lease.reset();
    LMDJ_CHECK(controller->consume_pattern_switch(p.ticket));
    LMDJ_CHECK(!controller->consume_pattern_switch(p.ticket));
    LMDJ_CHECK(!controller->inspect_pattern_switch(p.ticket));
    static_cast<void>(port.engine.reclaim_retired_patterns());
  }
  struct Input {
    facade::PatternTransportInputTicket ticket;
    audio::PatternInputAdmission native;
    std::uint64_t frame;
  };
  Input input(unsigned id,std::uint8_t pad,bool pressed,std::uint64_t correlation=0,bool held=true,domain::TriggerMode mode=domain::TriggerMode::loop_gate) {
    const auto frame = port.engine.telemetry().rendered_frames;
    const facade::PatternTransportInputRequest request{foundation::CommandId{uuid(id)},7,
        port.engine.telemetry().start_epoch,frame,{0,pad},pressed,
        static_cast<std::uint8_t>(pressed?90:0),correlation,held};
    const auto ticket = controller->reserve_input(request);
    LMDJ_CHECK(ticket.has_value());
    const auto native = port.engine.enqueue_pattern_input({7,request.frame_epoch,pad,request.velocity,
        !pressed,correlation,held,cooker::ResolvedPlayback{0,128,mode,1.0F,false}});
    LMDJ_CHECK(native.result == audio::PatternInputSubmit::accepted);
    LMDJ_CHECK(controller->bind_input(ticket.value(),native));
    return {ticket.value(),native,frame};
  }
  void consumed_native(const Input& i) {
    const auto result = port.engine.inspect_pattern_input_completion(7,port.engine.telemetry().start_epoch,i.native.sequence);
    LMDJ_CHECK(result && controller->complete_input(*result));
  }
  void settled_input(const Input& i,bool retained=true) {
    wait_for([&] { tick(); const auto s=controller->inspect_input(i.ticket); return s && s->complete; });
    const auto s=controller->inspect_input(i.ticket);
    if (s->error) std::cerr << s->error->message << ' ' << s->error->details.dump() << '\n';
    LMDJ_CHECK(s->durable_settled && s->retained==retained && !s->error);
    LMDJ_CHECK(port.engine.consume_pattern_input_completion(7,port.engine.telemetry().start_epoch,i.native.sequence));
    LMDJ_CHECK(controller->consume_input(i.ticket));
  }
  domain::ProjectState truth() { return project_io::ProjectStore{storage->inner}.load(bundle).value(); }
  void stop() {
    LMDJ_CHECK(controller->request(request(3,2,facade::PatternTransportIntent::play_stop)) == facade::PatternTransportSubmit::accepted);
    port.render(1);
    wait_for([&] { tick(); return controller->inspect().phase == facade::PatternTransportPhase::idle; });
    LMDJ_CHECK(!controller->inspect().recording && !controller->inspect().playing);
    LMDJ_CHECK(!project_io::SequenceJournal{storage->inner}.read_active(bundle).has_value());
  }
};

void post_s_input_waits_for_actual_boundary_and_source_commit() {
  Fixture f; f.start();
  const auto origin = f.controller->inspect().origin_frame;
  f.until(origin+6000);
  const auto press_a=f.input(10,1,true);
  f.port.render(1); f.consumed_native(press_a); f.settled_input(press_a);
  auto b=f.publish(f.b);
  const auto s=b.native.publication.activation_frame;
  f.until(s+6000); // Native B applied; deliberately delay its control observation.
  LMDJ_CHECK(f.port.engine.current_pattern_id()==f.b);
  const auto press_b=f.input(11,2,true);
  f.port.render(1); f.consumed_native(press_b);
  f.tick();
  LMDJ_CHECK(!f.controller->inspect_io().ticket);
  LMDJ_CHECK(!f.controller->inspect_input(press_b.ticket)->durable_settled);
  LMDJ_CHECK(!f.controller->project_overlay().value());
  f.observe(b); f.settled(b);
  LMDJ_CHECK(f.truth().patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},240,240,90}}));
  f.settled_input(press_b);
  const auto release_a=f.input(12,1,false,press_a.native.sequence);
  f.port.render(1); f.consumed_native(release_a); f.settled_input(release_a,false);
  f.until(s+12000);
  const auto release_b=f.input(13,2,false,press_b.native.sequence);
  f.port.render(1); f.consumed_native(release_b); f.settled_input(release_b);
  f.retire(b);
  f.stop();
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==2);
  LMDJ_CHECK(truth.patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},240,240,90}}));
  LMDJ_CHECK(truth.patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},240,240,90}}));
  f.controller.reset();
  const auto reopened=project_io::ProjectStore{f.storage->inner}.load(f.bundle);
  LMDJ_CHECK(reopened.has_value() && reopened.value()==truth);
}

void returning_a_cooks_its_acknowledged_notes_and_restarts_its_clock() {
  Fixture f; f.start();
  const auto origin=f.controller->inspect().origin_frame;
  f.until(origin+6000);
  const auto pa=f.input(10,1,true);
  f.port.render(1); f.consumed_native(pa); f.settled_input(pa);
  auto b=f.publish(f.b);
  const auto stale=f.controller->reserve_pattern_switch({7,f.a});
  LMDJ_CHECK(!stale.has_value() && stale.error().details.at("reason")=="recording_switch_material_pending");
  f.applied(b); f.settled(b);
  const auto source=f.truth();
  LMDJ_CHECK(source.revision==1 && source.patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},240,240,90}}));
  const auto sb=*f.controller->inspect_pattern_switch(b.ticket)->native_result->applied_frame;
  const auto ra=f.input(11,1,false,pa.native.sequence);
  f.port.render(1); f.consumed_native(ra); f.settled_input(ra,false);
  f.port.render(audio::kRealtimeRampFrames); // Logical release precedes its real declick tail.
  LMDJ_CHECK(f.port.engine.telemetry().active_voices==0);
  f.until(sb+6000);
  const auto pb=f.input(12,2,true);
  f.port.render(1); f.consumed_native(pb); f.settled_input(pb);
  f.until(sb+12000);
  const auto rb=f.input(13,2,false,pb.native.sequence);
  f.port.render(1); f.consumed_native(rb); f.settled_input(rb);
  f.retire(b);
  auto a=f.publish(f.a);
  f.applied(a); f.settled(a);
  const auto sa=*f.controller->inspect_pattern_switch(a.ticket)->native_result->applied_frame;
  LMDJ_CHECK(f.controller->inspect().origin_frame==sa && f.controller->inspect().recording);
  LMDJ_CHECK(f.truth().patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},240,240,90}}));
  // Before any later commit/reload, the newly cooked A view plays its own
  // acknowledged old note on the new clock. Neither Truth assertion alone
  // nor final close could prove this audible scheduling transition.
  const auto voices=f.port.engine.telemetry().started_voices;
  f.until(sa+6001);
  LMDJ_CHECK(f.port.engine.telemetry().started_voices==voices+1);
  LMDJ_CHECK(f.port.engine.telemetry().active_voices==1);
  f.until(sa+18000);
  const auto again=f.input(14,3,true);
  f.port.render(1); f.consumed_native(again); f.settled_input(again);
  const auto released=f.input(15,3,false,again.native.sequence);
  f.port.render(1); f.consumed_native(released); f.settled_input(released);
  f.retire(a); f.stop();
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==3);
  LMDJ_CHECK(truth.patterns.at(f.a).events==std::vector<domain::PatternEvent>({
      {{0,1},240,240,90},{{0,3},720,1,90}}));
  LMDJ_CHECK(truth.patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},240,240,90}}));
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}

void two_native_facts_survive_held_io_and_prompt_count_in_stop() {
  Fixture f; f.start(true);
  const auto original=f.controller->inspect_count_in();
  const auto s0=f.controller->inspect().origin_frame;
  f.until(s0+6000);
  const auto pa=f.input(10,1,true);
  f.port.render(1); f.consumed_native(pa); f.settled_input(pa);
  auto b=f.publish(f.b);
  f.port.render(1); // Native claims B before its future boundary.
  const auto claimed=f.port.engine.observe_pattern_publication(b.native.lease);
  LMDJ_CHECK(claimed && claimed->disposition==audio::PatternPublicationDisposition::pending);
  auto c=f.publish(f.c,claimed->authority);
  const auto generations=f.port.engine.pattern_telemetry().accepted_publications;
  const auto third=f.controller->reserve_pattern_switch({7,f.d});
  LMDJ_CHECK(!third.has_value() && third.error().details.at("reason")=="recording_switch_capacity");
  LMDJ_CHECK(f.port.engine.pattern_telemetry().accepted_publications==generations);
  f.storage->arm_kind("admission-switch");
  f.applied(b); f.tick();
  wait_for([&] { return f.storage->is_entered(); });
  const auto sb=*f.controller->inspect_pattern_switch(b.ticket)->native_result->applied_frame;
  LMDJ_CHECK(c.native.publication.activation_frame>sb+6001);
  f.until(sb+6000);
  const auto pb=f.input(11,2,true);
  f.port.render(1); f.consumed_native(pb); f.tick();
  LMDJ_CHECK(!f.controller->inspect_input(pb.ticket)->durable_settled);
  const auto overlay_calls=f.port.overlay_calls;
  f.applied(c); f.tick();
  const auto sc=*f.controller->inspect_pattern_switch(c.ticket)->native_result->applied_frame;
  LMDJ_CHECK(f.port.engine.current_pattern_id()==f.c);
  LMDJ_CHECK(f.controller->inspect().origin_frame==sc);
  LMDJ_CHECK(f.controller->inspect().transport_epoch==1);
  const auto current=f.controller->inspect_count_in();
  LMDJ_CHECK(current.start_receipt && original.start_receipt);
  LMDJ_CHECK(current.start_receipt->pattern_id==f.a && current.start_receipt->origin_frame==s0);
  LMDJ_CHECK(current.start_receipt->pattern_generation==original.start_receipt->pattern_generation);
  const auto ra=f.input(12,1,false,pa.native.sequence);
  f.port.render(1); f.consumed_native(ra); f.tick();
  const auto rb=f.input(13,2,false,pb.native.sequence);
  f.port.render(1); f.consumed_native(rb); f.tick();
  f.port.render(audio::kRealtimeRampFrames); // Logical release precedes its real declick tail.
  LMDJ_CHECK(f.port.engine.telemetry().active_voices==0);
  LMDJ_CHECK(!f.controller->inspect_input(ra.ticket)->complete);
  LMDJ_CHECK(!f.controller->inspect_input(rb.ticket)->complete);
  LMDJ_CHECK(f.controller->request(f.request(3,2,facade::PatternTransportIntent::play_stop))==facade::PatternTransportSubmit::accepted);
  f.port.render(1);
  const auto cutoff=f.port.engine.inspect_pattern_transport_receipt(7,2);
  LMDJ_CHECK(cutoff && !cutoff->playing && cutoff->pattern_id==f.c && cutoff->origin_frame==sc);
  f.tick();
  LMDJ_CHECK(f.storage->is_entered() && !f.controller->inspect().playing);
  LMDJ_CHECK(!f.controller->inspect_pattern_switch(b.ticket)->durable_settled);
  LMDJ_CHECK(!f.controller->inspect_pattern_switch(c.ticket)->durable_settled);
  LMDJ_CHECK(f.port.overlay_calls==overlay_calls);
  f.storage->release();
  f.settled(b);
  LMDJ_CHECK(f.truth().patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},240,240,90}}));
  f.settled_input(pb);
  f.settled(c);
  f.settled_input(ra,false); f.settled_input(rb,false);
  f.retire(b); f.retire(c);
  wait_for([&] { f.tick(); return f.controller->inspect().phase==facade::PatternTransportPhase::idle; });
  LMDJ_CHECK(!f.controller->inspect().playing && !f.controller->inspect().recording);
  const auto final=f.controller->inspect_count_in();
  LMDJ_CHECK(final.start_receipt->pattern_id==f.a && final.start_receipt->origin_frame==s0);
  LMDJ_CHECK(final.cancel_receipt && final.cancel_receipt->pattern_id==f.a && !final.error);
  LMDJ_CHECK(!project_io::SequenceJournal{f.storage->inner}.read_active(f.bundle).has_value());
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==2 && truth.patterns.at(f.c).events.empty());
  LMDJ_CHECK(truth.patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},240,240,90}}));
  LMDJ_CHECK(truth.patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},240,240,90}}));
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}

void record_off_commits_the_actual_final_pattern_and_keeps_playback() {
  Fixture f; f.start();
  auto b=f.publish(f.b); f.applied(b); f.settled(b);
  const auto sb=*f.controller->inspect_pattern_switch(b.ticket)->native_result->applied_frame;
  f.until(sb+6000);
  const auto p=f.input(10,2,true);
  f.port.render(1); f.consumed_native(p); f.settled_input(p);
  f.retire(b);
  LMDJ_CHECK(f.controller->request(f.request(3,2,facade::PatternTransportIntent::record))==facade::PatternTransportSubmit::accepted);
  f.port.render(1);
  const auto cutoff=f.port.engine.inspect_pattern_transport_receipt(7,2);
  LMDJ_CHECK(cutoff && cutoff->playing && cutoff->pattern_id==f.b && cutoff->origin_frame==sb);
  wait_for([&] { f.tick(); return !f.controller->inspect().recording; });
  LMDJ_CHECK(f.controller->inspect().playing && !f.controller->inspect().error);
  LMDJ_CHECK(!project_io::SequenceJournal{f.storage->inner}.read_active(f.bundle).has_value());
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==1 && truth.patterns.at(f.a).events.empty());
  LMDJ_CHECK(truth.patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},240,240,90}}));
  const auto release=f.input(11,2,false,p.native.sequence);
  f.port.render(1); f.consumed_native(release); f.settled_input(release,false);
  f.port.render(audio::kRealtimeRampFrames);
  LMDJ_CHECK(f.port.engine.telemetry().active_voices==0);
  LMDJ_CHECK(f.truth()==truth);
  LMDJ_CHECK(f.controller->request(f.request(4,3,facade::PatternTransportIntent::play_stop))==facade::PatternTransportSubmit::accepted);
  f.port.render(1);
  wait_for([&] { f.tick(); return f.controller->inspect().phase==facade::PatternTransportPhase::idle; });
  LMDJ_CHECK(!f.controller->inspect().playing && !f.controller->inspect().recording);
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}

void switch_at_actual_f_is_cancelled_without_target_authoring() {
  Fixture f; f.start();
  const auto origin=f.controller->inspect().origin_frame;
  f.until(origin+6000);
  const auto p=f.input(10,1,true);
  f.port.render(1); f.consumed_native(p); f.settled_input(p);
  auto b=f.publish(f.b);
  f.until(b.native.publication.activation_frame);
  LMDJ_CHECK(f.port.engine.current_pattern_id()==f.a);
  LMDJ_CHECK(f.controller->request(f.request(3,2,facade::PatternTransportIntent::play_stop))==facade::PatternTransportSubmit::accepted);
  f.port.render(1);
  const auto cutoff=f.port.engine.inspect_pattern_transport_receipt(7,2);
  LMDJ_CHECK(cutoff && cutoff->effective_frame==b.native.publication.activation_frame);
  LMDJ_CHECK(cutoff->switch_decision==audio::PatternCutoffDecision::canceled_at_cutoff);
  LMDJ_CHECK(cutoff->pattern_id==f.a && !cutoff->playing);
  f.observe(b);
  const auto cancelled=f.controller->inspect_pattern_switch(b.ticket);
  LMDJ_CHECK(cancelled->complete && cancelled->durable_settled && !cancelled->error);
  LMDJ_CHECK(cancelled->native_result->disposition==audio::PatternPublicationDisposition::cancelled);
  f.retire(b);
  const auto release=f.input(11,1,false,p.native.sequence);
  f.port.render(1); f.consumed_native(release); f.settled_input(release,false);
  wait_for([&] { f.tick(); return f.controller->inspect().phase==facade::PatternTransportPhase::idle; });
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==1 && truth.patterns.at(f.b).events.empty());
  LMDJ_CHECK(truth.patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},240,240,90}}));
  LMDJ_CHECK(f.port.engine.current_pattern_id()==f.a);
  LMDJ_CHECK(!project_io::SequenceJournal{f.storage->inner}.read_active(f.bundle).has_value());
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}

void lost_profile_reply_keeps_the_original_control_cell_and_live_opening() {
  Fixture f; f.start();
  const auto origin=f.controller->inspect().origin_frame;
  f.until(origin+6000);
  const auto pa=f.input(10,1,true);
  f.port.render(1); f.consumed_native(pa); f.settled_input(pa);
  auto b=f.publish(f.b);
  f.storage->fail_kind="admission-profile"; f.storage->fail_after=true;
  f.applied(b); f.tick();
  const auto original=f.controller->inspect_io().ticket;
  LMDJ_CHECK(original);
  wait_for([&] { f.tick(); return f.controller->inspect_pattern_switch(b.ticket)->error.has_value(); });
  LMDJ_CHECK(f.controller->inspect_io().ticket==original);
  LMDJ_CHECK(!f.controller->inspect_pattern_switch(b.ticket)->durable_settled);
  const auto journal=project_io::SequenceJournal{f.storage->inner}.read_active(f.bundle);
  LMDJ_CHECK(journal.has_value() && journal.value().admission->timing_profiles.size()==1);
  f.until(b.native.publication.activation_frame+6000);
  const auto pb=f.input(11,2,true);
  f.port.render(1); f.consumed_native(pb);
  LMDJ_CHECK(!f.controller->inspect_input(pb.ticket)->durable_settled);
  f.settled(b); f.settled_input(pb);
  const auto ra=f.input(12,1,false,pa.native.sequence);
  f.port.render(1); f.consumed_native(ra); f.settled_input(ra,false);
  const auto rb=f.input(13,2,false,pb.native.sequence);
  f.port.render(1); f.consumed_native(rb); f.settled_input(rb);
  f.retire(b); f.stop();
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==2);
  LMDJ_CHECK(truth.patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},240,240,90}}));
  LMDJ_CHECK(truth.patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},240,1,90}}));
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}

void failed_switch_disposes_io_before_native_pin_quiescence() {
  Fixture f; f.start();
  const auto origin=f.controller->inspect().origin_frame;
  f.until(origin+6000);
  const auto p=f.input(10,1,true);
  f.port.render(1); f.consumed_native(p); f.settled_input(p);
  auto b=f.publish(f.b);
  f.applied(b); // No control drive yet, so its I/O work has not started.
  auto external=std::make_shared<Storage>();
  external->inner=f.storage->inner;
  external->fail_kind="rebase";
  const auto changed=project_io::ProjectStore{external}.execute(f.bundle,domain::Command{
      domain::UpdateSequenceSettings{{foundation::CommandId{uuid(600)},0},130,{},{}}});
  LMDJ_CHECK(!changed.has_value() && external->failed);
  const auto before=f.truth();
  LMDJ_CHECK(before.revision==1);
  wait_for([&] { f.tick(); return f.controller->inspect().phase==facade::PatternTransportPhase::error; });
  const auto failed=f.controller->inspect_pattern_switch(b.ticket);
  LMDJ_CHECK(failed->error && !failed->complete && !failed->durable_settled);
  f.port.engine.stop();
  LMDJ_CHECK(f.port.engine.revoke_pattern_input_holds_quiescent(7));
  LMDJ_CHECK(!f.port.engine.scheduled_pattern_record_quiescent()); // Real B lease pin remains.
  f.controller->request_shutdown();
  wait_for([&] { f.tick(); return f.controller->inspect_input_owner().disposed; });
  const auto disposed=f.controller->inspect_pattern_switch(b.ticket);
  LMDJ_CHECK(disposed->owner_disposed && disposed->complete && disposed->error && !disposed->durable_settled);
  LMDJ_CHECK(!f.port.engine.scheduled_pattern_record_quiescent());
  const auto retained=project_io::SequenceJournal{f.storage->inner}.read_active(f.bundle);
  LMDJ_CHECK(retained.has_value() && retained.value().state==project_io::SequenceSessionState::owner_lost);
  LMDJ_CHECK(f.truth()==before);
  f.retire(b);
  LMDJ_CHECK(f.port.engine.scheduled_pattern_record_quiescent());
  LMDJ_CHECK(f.controller->acknowledge_input_owner(7));
  wait_for([&] { f.tick(); return f.controller->shutdown_complete(); });
  LMDJ_CHECK(f.controller->inspect().error && !f.controller->inspect().recording);
  LMDJ_CHECK(!f.port.engine.inspect_pattern_transport_receipt(7,2)); // No fabricated F.
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==before);
}

void reservation_identity_and_final_observations_are_exact() {
  Fixture f;
  LMDJ_CHECK(!f.controller->reserve_pattern_switch({7,f.b}).has_value());
  f.start();
  LMDJ_CHECK(!f.controller->reserve_pattern_switch({8,f.b}).has_value());
  LMDJ_CHECK(!f.controller->reserve_pattern_switch({7,f.a}).has_value());
  const auto before=f.port.engine.pattern_telemetry().accepted_publications;
  const auto reservation=f.controller->reserve_pattern_switch({7,f.b});
  LMDJ_CHECK(reservation.has_value());
  LMDJ_CHECK(!f.controller->inspect_pattern_switch(reservation.value())->publication);
  LMDJ_CHECK(!f.controller->consume_pattern_switch(reservation.value()));
  LMDJ_CHECK(f.controller->abandon_pattern_switch(reservation.value()));
  LMDJ_CHECK(!f.controller->abandon_pattern_switch(reservation.value()));
  LMDJ_CHECK(f.port.engine.pattern_telemetry().accepted_publications==before);
  auto b=f.publish(f.b);
  const auto real=f.port.engine.observe_pattern_publication(b.native.lease);
  LMDJ_CHECK(real);
  auto bad=*real;
  ++bad.authority.generation;
  LMDJ_CHECK(!f.controller->complete_pattern_switch(b.ticket,bad));
  bad=*real; bad.disposition=static_cast<audio::PatternPublicationDisposition>(99);
  LMDJ_CHECK(!f.controller->complete_pattern_switch(b.ticket,bad));
  bad=*real; bad.disposition=audio::PatternPublicationDisposition::applied;
  LMDJ_CHECK(!f.controller->complete_pattern_switch(b.ticket,bad)); // Missing actual S.
  LMDJ_CHECK(f.controller->complete_pattern_switch(b.ticket,*real));
  LMDJ_CHECK(f.controller->bind_pattern_switch(b.ticket,real->authority,120));
  LMDJ_CHECK(!f.controller->bind_pattern_switch(b.ticket,real->authority,121));
  f.applied(b); f.settled(b);
  const auto final=f.port.engine.observe_pattern_publication(b.native.lease);
  LMDJ_CHECK(final && f.controller->complete_pattern_switch(b.ticket,*final));
  LMDJ_CHECK(!f.controller->complete_pattern_switch(b.ticket,*real)); // Cannot regress to Pending.
  f.retire(b);
  LMDJ_CHECK(!f.controller->bind_pattern_switch(b.ticket,final->authority,120));
  LMDJ_CHECK(!f.controller->complete_pattern_switch(b.ticket,*final));
  f.stop();
  LMDJ_CHECK(f.truth().revision==0);
}

void actual_late_apply_drains_the_prefix_between_queued_and_actual_s() {
#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING
  Fixture f; f.start();
  const auto origin=f.controller->inspect().origin_frame;
  auto b=f.publish(f.b);
  LMDJ_CHECK(b.native.publication.activation_frame==origin+24000);
  // The existing Native test seam changes only the callback clock while no
  // callback is running. C1 itself still publishes the real actual S.
  f.port.engine.set_rendered_frames_quiescent_for_testing(30000);
  const auto pa=f.input(10,1,true);
  f.port.engine.set_rendered_frames_quiescent_for_testing(32000);
  f.port.render(1); f.consumed_native(pa);
  const auto late=f.port.engine.observe_pattern_publication(b.native.lease);
  LMDJ_CHECK(late && late->applied_frame==32000 && late->authority.activation_frame<32000);
  f.tick();
  LMDJ_CHECK(!f.controller->inspect_io().ticket); // Queued lower bound parks it until actual fact.
  f.observe(b);
  f.settled_input(pa); // Original 30000 is SOURCE, despite being after the queued frame.
  f.settled(b);
  LMDJ_CHECK(f.controller->inspect().origin_frame==32000);
  LMDJ_CHECK(f.truth().patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},1199,240,90}}));
  const auto ra=f.input(11,1,false,pa.native.sequence);
  f.port.render(1); f.consumed_native(ra); f.settled_input(ra,false);
  f.until(38000);
  const auto pb=f.input(12,2,true);
  f.port.render(1); f.consumed_native(pb); f.settled_input(pb);
  const auto rb=f.input(13,2,false,pb.native.sequence);
  f.port.render(1); f.consumed_native(rb); f.settled_input(rb);
  f.retire(b); f.stop();
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==2);
  LMDJ_CHECK(truth.patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},1199,240,90}}));
  LMDJ_CHECK(truth.patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},240,1,90}}));
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
#endif
}


void input_at_s_belongs_to_target_at_tick_zero() {
  Fixture f; f.start();
  auto b=f.publish(f.b);
  const auto sb=b.native.publication.activation_frame;
  f.until(sb);
  const auto press=f.input(10,2,true);
  LMDJ_CHECK(press.frame==sb);
  f.port.render(1); f.consumed_native(press);
  f.tick();
  LMDJ_CHECK(!f.controller->inspect_io().ticket);
  f.observe(b); f.settled(b); f.settled_input(press);
  f.until(sb+6000);
  const auto release=f.input(11,2,false,press.native.sequence);
  f.port.render(1); f.consumed_native(release); f.settled_input(release);
  f.retire(b); f.stop();
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==1 && truth.patterns.at(f.a).events.empty());
  LMDJ_CHECK(truth.patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},0,240,90}}));
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}

void legacy_metadata_waits_for_segment_and_is_not_overtaken_by_close() {
  Fixture f; f.start();
  auto b=f.publish(f.b); f.applied(b);
  const auto sb=*f.controller->inspect_pattern_switch(b.ticket)->native_result->applied_frame;
  f.until(sb+6000);
  // Compatibility DTO has no Native sequence authority; this case proves
  // its existing metadata/I/O contract, not an enqueue or audible outcome.
  const facade::PatternTransportCandidate candidate{10,sb+6000,{0,2},true,90,72};
  const auto waiting=f.controller->admit(candidate);
  LMDJ_CHECK(!waiting.has_value() && waiting.error().details.at("pending")==true);
  LMDJ_CHECK(!f.controller->inspect_io().ticket);
  f.port.render(1); // Original candidate is strictly before the actual F.
  LMDJ_CHECK(f.controller->request(f.request(3,2,facade::PatternTransportIntent::play_stop))==facade::PatternTransportSubmit::accepted);
  f.port.render(1);
  const auto cutoff=f.port.engine.inspect_pattern_transport_receipt(7,2);
  LMDJ_CHECK(cutoff && candidate.runtime_frame<cutoff->effective_frame);
  bool retained=false;
  wait_for([&] {
    f.tick(); const auto result=f.controller->admit(candidate);
    if (result.has_value()) { retained=result.value()==facade::PatternAdmissionAdmit::retained; return true; }
    LMDJ_CHECK(result.error().details.value("pending",false)); return false;
  });
  LMDJ_CHECK(retained);
  f.settled(b); f.retire(b);
  wait_for([&] { f.tick(); return f.controller->inspect().phase==facade::PatternTransportPhase::idle; });
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==1 && truth.patterns.at(f.a).events.empty());
  LMDJ_CHECK(truth.patterns.at(f.b).events==std::vector<domain::PatternEvent>({{{0,2},240,240,90}}));
  LMDJ_CHECK(!project_io::SequenceJournal{f.storage->inner}.read_active(f.bundle).has_value());
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}

void own_unlanded_overlay_is_withdrawn_and_old_projection_stays_blocked() {
  Fixture f; f.start(); f.port.allow_overlay=true;
  const auto origin=f.controller->inspect().origin_frame;
  f.until(origin+6000);
  const auto input=f.input(10,1,true,0,false,domain::TriggerMode::one_shot);
  f.port.render(128); f.consumed_native(input); f.settled_input(input);
  wait_for([&] { f.tick(); return f.port.engine.pattern_telemetry().pending_generation!=0; });
  const auto overlay=f.port.pending_switch();
  LMDJ_CHECK(overlay && overlay->pattern_id==f.a);
  f.port.allow_overlay=false;
  auto b=f.publish(f.b);
  LMDJ_CHECK(b.native.publication.activation_frame<overlay->activation_frame);
  const auto calls=f.port.overlay_calls;
  for (unsigned i=0;i!=4;++i) f.tick();
  LMDJ_CHECK(f.port.overlay_calls==calls);
  LMDJ_CHECK(!f.controller->project_overlay().value());
  f.applied(b); f.settled(b);
  LMDJ_CHECK(f.port.engine.current_pattern_id()==f.b);
  f.retire(b); f.stop();
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==1 && truth.patterns.at(f.b).events.empty());
  LMDJ_CHECK(truth.patterns.at(f.a).events==std::vector<domain::PatternEvent>({{{0,1},240,240,90}}));
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}

class AudioDriver {
 public:
  explicit AudioDriver(Port& port) : port_(port), thread_([this] { run(); }) {}
  ~AudioDriver() {
    { std::lock_guard lock(mutex_); stopping_=true; cv_.notify_all(); }
    thread_.join();
  }
  void advance(std::uint64_t target) {
    std::lock_guard lock(mutex_);
    LMDJ_CHECK(!requested_ && !running_);
    requested_=target; done_=false; cv_.notify_all();
  }
  void wait() {
    std::unique_lock lock(mutex_);
    cv_.wait(lock,[&] { return done_; });
    if (error_) std::rethrow_exception(error_);
  }
 private:
  void run() {
    for (;;) {
      std::uint64_t target{};
      {
        std::unique_lock lock(mutex_);
        cv_.wait(lock,[&] { return stopping_ || requested_; });
        if (stopping_) return;
        target=*requested_; requested_.reset(); running_=true;
      }
      try {
        // A bounded callback request, never wall-clock-driven musical time.
        while (port_.engine.telemetry().rendered_frames<target) {
          const auto remaining=target-port_.engine.telemetry().rendered_frames;
          port_.render(std::min<std::uint64_t>(128,remaining));
        }
      } catch (...) { error_=std::current_exception(); }
      {
        std::lock_guard lock(mutex_);
        running_=false; done_=true; cv_.notify_all();
      }
    }
  }
  Port& port_;
  std::mutex mutex_;
  std::condition_variable cv_;
  std::optional<std::uint64_t> requested_;
  bool running_{},done_{true},stopping_{};
  std::exception_ptr error_;
  std::thread thread_;
};

void concurrent_audio_control_and_io_keep_every_segment_and_note() {
  Fixture f; f.start();
  std::vector<domain::PatternEvent> expected_a,expected_b;
  {
    AudioDriver audio{f.port};
    for (unsigned i=0;i!=48;++i) {
      audio.advance(f.port.engine.telemetry().rendered_frames+128*(i+1)); audio.wait();
      const auto current=f.port.engine.current_pattern_id();
      LMDJ_CHECK(current);
      const auto origin=f.controller->inspect().origin_frame;
      const auto input=f.input(100+i,1,true,0,false,domain::TriggerMode::one_shot);
      const auto onset=static_cast<std::uint32_t>((input.frame-origin)/25);
      (*current==f.a ? expected_a : expected_b).push_back({{0,1},onset,240,90});
      audio.advance(input.frame+128); audio.wait();
      f.consumed_native(input); f.settled_input(input);
      auto next=f.publish(*current==f.a ? f.b : f.a);
      // The actual callback thread publishes its S while serialized control
      // observes it and the real dedicated I/O owner settles that same fact.
      audio.advance(next.native.publication.activation_frame+2048);
      wait_for([&] {
        f.observe(next); f.tick();
        return f.controller->inspect_pattern_switch(next.ticket)->durable_settled;
      });
      const auto status=f.controller->inspect_pattern_switch(next.ticket);
      LMDJ_CHECK(status->complete && status->native_result->applied_frame && !status->error);
      LMDJ_CHECK(f.controller->inspect().origin_frame==*status->native_result->applied_frame);
      f.retire(next); // Reclaim is concurrent with any remaining callback borrow.
      audio.wait();
    }
  }
  const auto by_onset=[](const auto& a,const auto& b) { return a.onset_tick<b.onset_tick; };
  std::ranges::sort(expected_a,by_onset); std::ranges::sort(expected_b,by_onset);
  f.stop();
  const auto truth=f.truth();
  LMDJ_CHECK(truth.revision==48 && expected_a.size()==24 && expected_b.size()==24);
  LMDJ_CHECK(truth.patterns.at(f.a).events==expected_a);
  LMDJ_CHECK(truth.patterns.at(f.b).events==expected_b);
  LMDJ_CHECK(truth.patterns.at(f.c).events.empty() && truth.patterns.at(f.d).events.empty());
  f.controller.reset();
  LMDJ_CHECK(project_io::ProjectStore{f.storage->inner}.load(f.bundle).value()==truth);
}
} // namespace
int main(int argc,char** argv) {
  try {
    if (argc==2 && std::string_view{argv[1]}=="--stress") {
      concurrent_audio_control_and_io_keep_every_segment_and_note();
      std::cout << "recording switch control stress: PASS (48 segments)\n";
      return 0;
    }
    LMDJ_CHECK(argc==1);
    post_s_input_waits_for_actual_boundary_and_source_commit();
    returning_a_cooks_its_acknowledged_notes_and_restarts_its_clock();
    two_native_facts_survive_held_io_and_prompt_count_in_stop();
    record_off_commits_the_actual_final_pattern_and_keeps_playback();
    switch_at_actual_f_is_cancelled_without_target_authoring();
    lost_profile_reply_keeps_the_original_control_cell_and_live_opening();
    failed_switch_disposes_io_before_native_pin_quiescence();
    reservation_identity_and_final_observations_are_exact();
    actual_late_apply_drains_the_prefix_between_queued_and_actual_s();
    input_at_s_belongs_to_target_at_tick_zero();
    legacy_metadata_waits_for_segment_and_is_not_overtaken_by_close();
    own_unlanded_overlay_is_withdrawn_and_old_projection_stays_blocked();
    std::cout << "recording switch control tests: PASS\n";
  } catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
