#include <lmdj/web_runtime/control_runtime.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/provider/registry.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <deque>
#include <filesystem>
#include <iostream>
#include <memory>
#include <span>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using Json = nlohmann::json;
using foundation::Result;
using web_runtime::ControlRuntime;
constexpr audio::RuntimePreparationLimits limits{68'157'440, 67'108'864, 134'217'728, 268'435'456};
constexpr auto artifact_sha = "9545d7cb33070fd89c29147fb1ae68f58e098a9c4f14b83800f90739b9d364f8";
std::string uuid(unsigned value) {
  const auto digits = std::to_string(value);
  return "90000000-0000-4000-8000-" + std::string(12 - digits.size(), '0') + digits;
}
template <typename T> T take(Result<T> result) {
  if (!result.has_value()) throw std::runtime_error(result.error().message + result.error().details.dump());
  return std::move(result.value());
}
Json result(Json response) {
  if (!response.value("ok", false)) throw std::runtime_error(response.dump());
  return std::move(response.at("result"));
}
std::vector<std::byte> wav() {
  std::vector<std::byte> out;
  const auto text = [&](std::string_view s) { for (char c : s) out.push_back(static_cast<std::byte>(c)); };
  const auto u16 = [&](std::uint16_t n) { out.push_back(static_cast<std::byte>(n & 255)); out.push_back(static_cast<std::byte>(n >> 8)); };
  const auto u32 = [&](std::uint32_t n) { u16(static_cast<std::uint16_t>(n)); u16(static_cast<std::uint16_t>(n >> 16)); };
  text("RIFF"); u32(996); text("WAVEfmt "); u32(16); u16(1); u16(1);
  u32(48'000); u32(96'000); u16(2); u16(16); text("data"); u32(960);
  for (unsigned n = 0; n < 480; ++n) u16(10'000);
  return out;
}
class Platform final : public project_io::ProjectStoragePlatform {
 public:
  std::shared_ptr<project_io::ProjectStoragePlatform> inner = project_io::make_default_project_storage_platform();
  std::atomic<std::uint64_t> writes{};
  std::atomic<bool> lose_manifest_response{};
  std::atomic<unsigned> lost_responses{};
  Result<std::unique_ptr<project_io::ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override { return inner->acquire_writer(p); }
  Result<void> ensure_directory(const std::filesystem::path& p) override { return inner->ensure_directory(p); }
  Result<bool> exists(const std::filesystem::path& p) const override { return inner->exists(p); }
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override { return inner->byte_length(p); }
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override { return inner->read_complete(p); }
  Result<void> create_immutable(const std::filesystem::path& p, std::span<const std::byte> b) override { ++writes; return inner->create_immutable(p, b); }
  Result<void> replace_complete(const std::filesystem::path& p, std::span<const std::byte> b) override {
    ++writes; auto saved = inner->replace_complete(p, b);
    if (saved.has_value() && p.filename() == "manifest.json" && lose_manifest_response.exchange(false)) {
      ++lost_responses;
      return Result<void>::failure({foundation::ErrorCode::io_error, "lost response after real manifest publication"});
    }
    return saved;
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

struct Fixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-web-tempo-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path bundle = root / "projects" / (uuid(1) + ".lmdj");
  std::shared_ptr<Platform> platform = std::make_shared<Platform>();
  std::unique_ptr<ControlRuntime> runtime;
  std::unique_ptr<domain::ProjectState> baseline;
  std::uint64_t baseline_undo{}, origin{};
  unsigned next_rpc{1'000};
  unsigned next_command{5'000};
  std::uint64_t next_input{1};
  bool count_in_output{};
  std::atomic<bool> render_enabled{}, render_active{}, render_running{}, physically_joined{true};
  std::atomic<std::uint64_t> thread_callbacks{};
  std::jthread audio_thread;
  bool fail_quiescence{};
  unsigned drain_requests{}, quiescence_calls{};
  static Result<void> begin_audio(void*) noexcept { return Result<void>::success(); }
  static Result<void> quiescent(void* p, std::uint32_t) noexcept {
    auto& f = *static_cast<Fixture*>(p); ++f.quiescence_calls;
    if (f.fail_quiescence)
      return Result<void>::failure({foundation::ErrorCode::internal_error, "operational observer failed"});
    f.join_audio();
    return Result<void>::success();
  }
  static void request_drain(void* p) noexcept {
    auto& f = *static_cast<Fixture*>(p); ++f.drain_requests;
    f.render_running = false; // Request is deliberately not a join receipt.
  }
  static bool joined(void* p) noexcept { return static_cast<Fixture*>(p)->physically_joined.load(); }
  static bool ready(void*) noexcept { return true; }
  static std::uint64_t acknowledge(void* p) noexcept {
    auto& f = *static_cast<Fixture*>(p);
    if (!f.audio_thread.joinable() && f.engine().telemetry().state == audio::RealtimeState::running) f.render(128);
    return f.engine().bank_telemetry().current_generation;
  }
  explicit Fixture(bool physical = false, bool playing = true, bool scheduled = false,
      bool looped = false) : count_in_output(scheduled) {
    std::filesystem::create_directories(root);
    facade::ApplicationConfig c{}; c.workspace_root = root; c.providers = std::make_shared<provider::Registry>();
    c.storage_platform = platform; c.runtime_preparation_limits = limits;
    runtime = take(ControlRuntime::create(root, std::move(c), limits));
    Json events = Json::array();
    for (unsigned tick = 0; tick < 3840; tick += 960)
      events.push_back({{"slot", {{"bank", 0}, {"pad", 0}}}, {"onset_tick", tick}, {"duration_tick", 1}, {"velocity", 127}});
    call("project.create", {{"project_id", uuid(1)}, {"bpm", 120},
        {"initial_pattern", {{"pattern_id", uuid(2)}, {"bars", 1}, {"events", events}}}, {"pattern_transport", true}});
    if (scheduled) {
      LMDJ_CHECK(call("pattern.transport.count-in.capabilities", {{"negotiate", true}}).at("negotiated") == true);
      LMDJ_CHECK(web_runtime::detail::ControlRuntimeCountInOutputAccess::install(
          *runtime, {this, ready}).has_value());
    }
    const auto bytes = wav();
    result(runtime->dispatch("asset.import", {{"command_id", uuid(10)}, {"expected_revision", 0},
        {"asset_id", uuid(11)}, {"media_type", "audio/wav"},
        {"sidecar", {{"sidecar_bytes", bytes.size()}, {"sidecar_sha256", artifact_sha}}}}, bytes));
    call("pad.assign", {{"command_id", uuid(12)}, {"expected_revision", 1},
        {"slot", {{"bank", 0}, {"pad", 0}}}, {"asset_id", uuid(11)}});
    if (looped) {
      auto playback = call("sample.inspect", {{"slot", {{"bank", 0}, {"pad", 0}}}}).at("playback");
      playback["trigger_mode"] = "loop_gate"; playback["loop_start_frame"] = 0;
      playback["trim_end_frame"] = 480; playback["attack_ms"] = 0; playback["release_ms"] = 0;
      call("sample.update_pad", {{"command_id", command()}, {"expected_revision", 2},
          {"slot", {{"bank", 0}, {"pad", 0}}}, {"playback", playback}});
    }
    call("snapshot.reload", {{"pattern_id", uuid(2)}});
    baseline = std::make_unique<domain::ProjectState>(truth());
    LMDJ_CHECK(baseline->revision == (looped ? 3 : 2)); artifact();
    baseline_undo = history().at("undo_count");
    const auto installed = web_runtime::detail::ControlRuntimeAudioAccess::install(
        *runtime, {this, quiescent, begin_audio, ready, acknowledge});
    LMDJ_CHECK(installed.has_value());
    if (physical) LMDJ_CHECK(web_runtime::detail::ControlRuntimePhysicalAudioAccess::install(
        *runtime, {this, request_drain, joined}).has_value());
    call("audio.activate", Json::object());
    if (playing) transport(true);
    origin = call("pattern.transport.inspect", {{"session_id", uuid(20)}}).at("origin_frame");
  }
  ~Fixture() {
    join_audio();
    if (runtime) { engine().stop(); runtime.reset(); } // Manual renderer is quiescent here.
    std::error_code ignored; std::filesystem::remove_all(root, ignored);
  }
  audio::RealtimeEngine& engine() { return runtime->engine(); }
  std::string command() { return uuid(next_command++); }
  void start_audio() {
    LMDJ_CHECK(!audio_thread.joinable());
    physically_joined = false; render_running = true; render_enabled = true;
    audio_thread = std::jthread([this] {
      std::array<float, 128> l{}, r{};
      while (render_running) {
        if (render_enabled) {
          render_active = true;
          if (render_enabled && render_running) {
            engine().render(l.data(), r.data(), 128); ++thread_callbacks;
            // Lifecycle/race cases have no frame-count oracle. Keep this
            // independent producer bounded enough for its real consumer.
            std::this_thread::sleep_for(std::chrono::microseconds{50});
          }
          render_active = false;
        }
        std::this_thread::yield();
      }
    });
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{2};
    while (thread_callbacks == 0) { LMDJ_CHECK(std::chrono::steady_clock::now() < deadline); std::this_thread::yield(); }
  }
  void pause_audio() {
    render_enabled = false;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{2};
    while (render_active) { LMDJ_CHECK(std::chrono::steady_clock::now() < deadline); std::this_thread::yield(); }
  }
  void join_audio() noexcept {
    render_running = false;
    if (audio_thread.joinable()) audio_thread.join();
    physically_joined = true;
  }
  Json call(std::string_view op, Json payload) {
    const auto budget = op == "host.close" ? std::chrono::seconds{10} :
        (op == "audio.activate" || op == "audio.suspend" || op == "pattern.tempo.preview.set" ||
         op == "pattern.tempo.preview.cancel" || op == "pattern.tempo.preview.status")
        ? std::chrono::seconds{1} : std::chrono::seconds{30};
    const ControlRuntime::AbsoluteRequestDeadline deadline{std::chrono::steady_clock::now() + budget};
    const auto original_rpc = uuid(next_rpc++);
    auto response = runtime->dispatch(op, payload, {}, deadline, original_rpc);
    const auto watchdog = std::chrono::steady_clock::now() + std::chrono::seconds{2};
    while (!response.value("ok", false) && runtime->owns_pending_pattern_rpc(original_rpc, op)) {
      LMDJ_CHECK(std::chrono::steady_clock::now() < watchdog);
      runtime->service_pattern_transport();
      // Actual original-owner continuation, before mutation. Never replace
      // command/RPC identities or infer rollback from the normalized error.
      response = runtime->dispatch(op, payload, {}, deadline, original_rpc);
      std::this_thread::sleep_for(std::chrono::milliseconds{1});
    }
    if (!response.value("ok", false)) throw std::runtime_error(std::string(op) + ": " + response.dump());
    return result(std::move(response));
  }
  domain::ProjectState truth() const { return take(project_io::ProjectStore(platform).inspect_committed(bundle)); }
  Json history() { return call("history.inspect", Json::object()); }
  void artifact() const {
    const auto state = truth(); const auto& ref = state.assets.at(foundation::AssetId{uuid(11)}).artifact;
    LMDJ_CHECK(ref.sha256 == artifact_sha && ref.byte_length == 1004);
    LMDJ_CHECK(take(project_io::ProjectStore(platform).read_artifact(bundle, ref)) == wav());
  }
  void render(std::uint64_t frames) {
    LMDJ_CHECK(!audio_thread.joinable() || (!render_enabled && !render_active));
    std::array<float, 128> l{}, r{};
    while (frames) {
      const auto n = static_cast<std::uint32_t>(std::min<std::uint64_t>(128, frames));
      engine().render(l.data(), r.data(), n); frames -= n;
      if (count_in_output) {
        audio::CountInCueBatch cues;
        if (engine().take_count_in_cue_batch_audio(cues))
          LMDJ_CHECK(engine().acknowledge_count_in_cue_batch_audio(cues.batch_id));
      }
    }
  }
  void until(std::uint64_t frame) {
    LMDJ_CHECK(engine().telemetry().rendered_frames <= frame);
    render(frame - engine().telemetry().rendered_frames);
  }
  void onset(std::uint64_t relative, std::uint64_t count) {
    until(origin + relative); LMDJ_CHECK(engine().telemetry().started_voices == count);
    float l{}, r{}; engine().render(&l, &r, 1);
    LMDJ_CHECK(engine().telemetry().started_voices == count + 1 && l == 0 && r == 0);
    engine().render(&l, &r, 1); LMDJ_CHECK(l > 0 && l == r);
  }
  void transport(bool playing) {
    auto status = call("pattern.transport.inspect", {{"session_id", uuid(20)}});
    const auto epoch = status.at("transport_epoch").get<std::uint64_t>() + 1;
    call("pattern.transport.request", {{"session_id", uuid(20)}, {"project_id", uuid(1)},
        {"command_id", uuid(30 + static_cast<unsigned>(epoch))}, {"expected_epoch", epoch},
        {"intent", "play_stop"}, {"expected_revision", truth().revision}});
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    for (;;) {
      runtime->service_pattern_transport();
      status = call("pattern.transport.inspect", {{"session_id", uuid(20)}});
      if (status.at("playing") == playing && status.at("phase") == "idle") return;
      LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
      // The actual I/O worker owns its wait. Render only when audio owns a
      // receipt, rather than letting wall-clock I/O alter the frame oracle.
      if (status.at("phase") == "awaiting_audio" || engine().pattern_telemetry().pending_generation != 0) render(128);
      std::this_thread::sleep_for(std::chrono::milliseconds{1});
    }
  }
  Json begin(std::uint64_t revision = 2, const std::string& pattern = uuid(2)) {
    return call("pattern.tempo.preview.begin", {{"project_id", uuid(1)}, {"pattern_id", pattern}, {"expected_revision", revision}});
  }
  Json transport_status() { return call("pattern.transport.inspect", {{"session_id", uuid(20)}}); }
  void record(bool recording) {
    const auto epoch = transport_status().at("transport_epoch").get<std::uint64_t>() + 1;
    call("pattern.transport.request", {{"session_id", uuid(20)}, {"project_id", uuid(1)},
        {"command_id", command()}, {"expected_epoch", epoch}, {"intent", "record"}, {"expected_revision", truth().revision}});
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    for (;;) {
      runtime->service_pattern_transport(); const auto status = transport_status();
      LMDJ_CHECK(status.at("error").is_null());
      if (status.at("recording") == recording && status.at("phase") == "idle" &&
          status.at("publication_pending") == false && engine().pattern_telemetry().pending_generation == 0) return;
      LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
      const auto pending = engine().pattern_telemetry();
      if (pending.pending_generation) until(std::max(engine().telemetry().rendered_frames, pending.pending_activation_frame) + 1);
      else if (status.at("phase") == "awaiting_audio") render(128);
      std::this_thread::sleep_for(std::chrono::milliseconds{1});
    }
  }
  Json input(bool release = false, Json press = nullptr) {
    const auto capability = call("pattern.transport.count-in.capabilities", {{"negotiate", false}});
    return call("pattern.transport.input.request", {{"command_id", command()},
        {"runtime_generation", capability.at("runtime_generation")}, {"frame_epoch", capability.at("frame_epoch")},
        {"input_serial", std::to_string(next_input++)}, {"slot", 0}, {"velocity", release ? 0 : 100},
        {"kind", release ? "release" : "press"}, {"held", true}, {"held_press_sequence", std::move(press)}});
  }
  Json settle_input(const Json& input) {
    auto payload = input.at("ticket"); payload["consume"] = false;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    Json status;
    do {
      runtime->service_pattern_transport(); status = call("pattern.transport.input.inspect", payload);
      if (status.at("complete") == true) break;
      LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
      std::this_thread::sleep_for(std::chrono::milliseconds{1});
    } while (true);
    LMDJ_CHECK(status.at("error").is_null() && status.at("durable_settled") == true);
    payload["consume"] = true; LMDJ_CHECK(call("pattern.transport.input.inspect", payload) == status);
    return status;
  }
  Json inspect(const Json& ticket) { return call("pattern.tempo.preview.status", {{"ticket", ticket}}); }
  Json settle(const Json& ticket) {
    for (unsigned n = 0; n < 16; ++n) {
      render(128); runtime->service_pattern_transport(); auto state = inspect(ticket);
      if (state.at("phase") == "cancelled" || state.at("phase") == "committed") return state;
    }
    throw std::runtime_error("tempo did not actually settle");
  }
  void reopen(const domain::ProjectState& expected) {
    LMDJ_CHECK(!audio_thread.joinable());
    engine().stop(); runtime.reset();
    facade::ApplicationConfig c{}; c.workspace_root = root;
    c.providers = std::make_shared<provider::Registry>(); c.storage_platform = platform;
    runtime = take(ControlRuntime::create(root, std::move(c), limits));
    call("project.open", {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"pattern_transport", true}});
    LMDJ_CHECK(truth() == expected && history().at("undo_count") == 0); artifact();
  }
};

// Only the proxy scheduling is test-owned. Encoding, registration, dispatch,
// response ownership, failed admission and retained allowlist are production.
struct BridgeHarness {
  using Bridge = web_runtime::detail::ControlBridge;
  struct Task { void (*function)(void*) noexcept; void* argument; };
  Fixture& f;
  std::deque<Task> tasks;
  bool on_control{};
  std::unique_ptr<Bridge> bridge;
  explicit BridgeHarness(Fixture& fixture) : f(fixture), bridge(std::make_unique<Bridge>(
      *f.runtime, web_runtime::detail::BridgeHooks{this, schedule, is_control, nullptr, nullptr, nullptr})) {}
  static bool schedule(void* p, void (*function)(void*) noexcept, void* argument) noexcept {
    static_cast<BridgeHarness*>(p)->tasks.push_back({function, argument}); return true;
  }
  static bool is_control(void* p) noexcept { return static_cast<BridgeHarness*>(p)->on_control; }
  void pump() {
    LMDJ_CHECK(!tasks.empty()); auto task = tasks.front(); tasks.pop_front();
    const auto previous = std::exchange(on_control, true); task.function(task.argument); on_control = previous;
  }
  std::vector<std::byte> envelope(std::string_view id, std::string_view op, const Json& payload) {
    const auto text = Json{{"protocol_version", 1}, {"request_id", id}, {"operation", op}, {"payload", payload}}.dump();
    const auto* first = reinterpret_cast<const std::byte*>(text.data()); return {first, first + text.size()};
  }
  Json send(std::string_view op, const Json& payload,
      std::optional<std::chrono::steady_clock::time_point> deadline = {}) {
    const auto id = uuid(f.next_rpc++); const auto bytes = envelope(id, op, payload);
    LMDJ_CHECK(bridge->submit(bytes, {}, deadline) == web_runtime::detail::BridgeSubmitStatus::accepted);
    const auto watchdog = std::chrono::steady_clock::now() + std::chrono::seconds{2};
    for (;;) {
      if (!tasks.empty()) pump();
      std::array<std::byte, web_runtime::detail::kBridgeMaximumEnvelopeBytes> output{};
      std::size_t size{};
      const auto state = bridge->poll(output, size);
      if (state == web_runtime::detail::BridgePollStatus::message) {
        const auto* first = reinterpret_cast<const char*>(output.data());
        auto message = Json::parse(first, first + size);
        if (message.value("request_id", std::string{}) == id) {
          // Pay the real original response-consumer release thunk too.
          for (unsigned n = 0; !tasks.empty() && n < 32; ++n) pump();
          return message;
        }
      }
      LMDJ_CHECK(std::chrono::steady_clock::now() < watchdog);
      std::this_thread::yield();
    }
  }
  Json call(std::string_view op, const Json& payload) { return result(send(op, payload)); }
  void denied(std::string_view op, const Json& payload) {
    const auto bytes = envelope(uuid(f.next_rpc++), op, payload);
    LMDJ_CHECK(bridge->submit(bytes, {}) == web_runtime::detail::BridgeSubmitStatus::queue_full);
  }
};

void actual_cancel_save_exact_retry_undo_reopen() {
  Fixture f; const auto writes = f.platform->writes.load();
  auto state = f.begin(); const auto first = state.at("ticket");
  f.until(f.origin + 12'001);
  state = f.call("pattern.tempo.preview.set", {{"ticket", first}, {"bpm", 240}});
  LMDJ_CHECK(state.at("phase") == "preview_pending");
  LMDJ_CHECK(f.truth() == *f.baseline && f.history().at("undo_count") == f.baseline_undo);
  f.onset(18'001, 1); f.inspect(first);
  f.until(f.origin + 20'000);
  f.call("pattern.tempo.preview.cancel", {{"ticket", first}});
  f.onset(40'001, 2);
  LMDJ_CHECK(f.inspect(first).at("phase") == "cancelled");
  LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes && f.history().at("undo_count") == f.baseline_undo);
  const auto second = f.begin().at("ticket");
  LMDJ_CHECK(second.at("preview_token") != first.at("preview_token"));
  f.until(f.origin + 50'000);
  f.call("pattern.tempo.preview.set", {{"ticket", second}, {"bpm", 240}});
  f.onset(57'001, 3); f.inspect(second);
  f.until(f.origin + 60'000);
  const Json commit{{"ticket", second}, {"command_id", uuid(200)}};
  state = f.call("pattern.tempo.preview.commit", commit);
  LMDJ_CHECK(state.at("committed_revision") == 3 && state.at("source_revision") == 2);
  auto expected = *f.baseline; expected.bpm = 240; expected.revision = 3;
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == f.baseline_undo + 1);
  f.onset(69'001, 4);
  LMDJ_CHECK(f.inspect(second).at("phase") == "committed");
  const auto saved_writes = f.platform->writes.load();
  LMDJ_CHECK(f.call("pattern.tempo.preview.commit", commit).at("committed_revision") == 3);
  LMDJ_CHECK(f.call("pattern.tempo.preview.cancel", {{"ticket", second}}).at("committed_revision") == 3);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == saved_writes);
  // Valid idempotent activation publishes no Pattern. Retain B2's exact
  // adopted revision before this unrelated action releases its binding.
  LMDJ_CHECK(f.call("audio.activate", Json::object()).at("changed") == false);
  const auto third = f.begin(3).at("ticket");
  f.call("pattern.tempo.preview.set", {{"ticket", third}, {"bpm", 180}});
  f.render(128); f.inspect(third);
  f.call("pattern.tempo.preview.cancel", {{"ticket", third}}); f.settle(third);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == saved_writes);
  f.transport(false);
  const auto session = f.history().at("session_id");
  f.call("history.undo", {{"session_id", session}, {"command_id", uuid(201)}, {"expected_revision", 3}});
  expected.bpm = 120; expected.revision = 4;
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == f.baseline_undo && f.history().at("redo_count") == 1);
  f.artifact();
  f.engine().stop(); f.runtime.reset(); // Manual callback owner is quiescent.
  facade::ApplicationConfig c{}; c.workspace_root = f.root; c.providers = std::make_shared<provider::Registry>(); c.storage_platform = f.platform;
  auto reopened = take(ControlRuntime::create(f.root, std::move(c), limits));
  result(reopened->dispatch("project.open", {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"pattern_transport", true}}, {}));
  LMDJ_CHECK(f.truth() == expected); f.artifact();
  LMDJ_CHECK(result(reopened->dispatch("history.inspect", Json::object(), {})).at("undo_count") == 0);
}

void non_bpm_truth_revision_can_begin_and_preview_without_restarting() {
  Fixture f;
  f.call("sequence.settings.update", {{"command_id", uuid(300)}, {"expected_revision", 2}, {"session_id", nullptr},
      {"bpm", nullptr}, {"quantize_enabled", false}, {"swing_percent", nullptr}});
  auto expected = *f.baseline; expected.quantize_enabled = false; expected.revision = 3;
  LMDJ_CHECK(f.truth() == expected);
  const auto writes = f.platform->writes.load(); const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  const auto ready = f.begin(3); // Must not fail merely because no Pattern was republished.
  LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs);
  LMDJ_CHECK(ready.at("ticket").at("source_id") == ready.at("applied").at("pattern_generation"));
  const auto ticket = ready.at("ticket");
  f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
  for (unsigned n = 0; n < 16; ++n) {
    f.render(128); f.runtime->service_pattern_transport();
    if (f.inspect(ticket).at("phase") == "previewing") break;
  }
  const auto applied = f.inspect(ticket);
  LMDJ_CHECK(applied.at("phase") == "previewing" && applied.at("applied").at("anchor").at("bpm") == 240);
  const auto& anchor = applied.at("applied").at("anchor");
  const auto anchor_frame = std::stoull(anchor.at("frame").get<std::string>());
  LMDJ_CHECK(std::stoull(anchor.at("tick_numerator").get<std::string>()) ==
      (anchor_frame - f.origin) * 120 * 960); // Independent no-restart oracle.
  f.call("pattern.tempo.preview.cancel", {{"ticket", ticket}}); f.settle(ticket);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
}

void cancel_before_first_set_rejects_a_late_old_set() {
  Fixture f; const auto ready = f.begin(); const auto ticket = ready.at("ticket");
  const auto writes = f.platform->writes.load(); const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  LMDJ_CHECK(f.call("pattern.tempo.preview.cancel", {{"ticket", ticket}}).at("phase") == "cancelled");
  const auto late = f.runtime->dispatch("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}}, {});
  LMDJ_CHECK(!late.value("ok", false));
  LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes && f.engine().pattern_telemetry().accepted_publications == pubs);
}

void cancelling_applied_source_adoption_never_issues_the_cancelled_audible_set() {
  Fixture f;
  f.call("sequence.settings.update", {{"command_id", uuid(310)}, {"expected_revision", 2}, {"session_id", nullptr},
      {"bpm", nullptr}, {"quantize_enabled", false}, {"swing_percent", nullptr}});
  const auto expected = f.truth(); const auto writes = f.platform->writes.load();
  const auto ticket = f.begin(3).at("ticket");
  const auto pending = f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
  LMDJ_CHECK(pending.at("phase") == "source_pending" && pending.at("preview_id") == "0");
  const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  f.render(128); // Native adopted metadata; Control has not serviced it.
  const auto cancelled = f.call("pattern.tempo.preview.cancel", {{"ticket", ticket}});
  LMDJ_CHECK(cancelled.at("phase") == "cancelled" && cancelled.at("preview_id") == "0");
  LMDJ_CHECK(cancelled.at("applied").at("anchor").at("bpm") == 120 && cancelled.at("source_revision") == 3);
  f.render(256); f.runtime->service_pattern_transport();
  LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
}

void early_commit_during_source_adoption_is_known_refusal_then_exact_save() {
  Fixture f;
  f.call("sequence.settings.update", {{"command_id", uuid(320)}, {"expected_revision", 2}, {"session_id", nullptr},
      {"bpm", nullptr}, {"quantize_enabled", false}, {"swing_percent", nullptr}});
  auto expected = f.truth(); const auto writes = f.platform->writes.load(); const auto undo = f.history().at("undo_count");
  const auto ticket = f.begin(3).at("ticket");
  f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
  const Json command{{"ticket", ticket}, {"command_id", uuid(321)}};
  const auto refused = f.runtime->dispatch("pattern.tempo.preview.commit", command, {});
  LMDJ_CHECK(!refused.value("ok", false) && refused.at("error").at("details").at("tempo_commit_refused") == true);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes && f.history().at("undo_count") == undo);
  f.render(128); f.runtime->service_pattern_transport(); f.render(128); f.runtime->service_pattern_transport();
  LMDJ_CHECK(f.inspect(ticket).at("phase") == "previewing");
  LMDJ_CHECK(f.call("pattern.tempo.preview.commit", command).at("committed_revision") == 4);
  f.settle(ticket);
  expected.bpm = 240; expected.revision = 4;
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == undo.get<std::uint64_t>() + 1);
  f.artifact();
}

void bridge_published_response_loss_keeps_exact_save_then_undo_and_reopen() {
  Fixture f; BridgeHarness h(f);
  const auto ticket = h.call("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", 2}}).at("ticket");
  h.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
  f.render(128);
  LMDJ_CHECK(h.call("pattern.tempo.preview.status", {{"ticket", ticket}}).at("phase") == "previewing");
  f.platform->lose_manifest_response = true;
  const Json command{{"ticket", ticket}, {"command_id", uuid(400)}};
  const auto unknown = h.call("pattern.tempo.preview.commit", command);
  LMDJ_CHECK(f.platform->lost_responses == 1 && unknown.at("phase") == "commit_unknown");
  LMDJ_CHECK(unknown.at("command_id") == uuid(400) && unknown.at("committed_revision").is_null());
  auto expected = *f.baseline; expected.bpm = 240; expected.revision = 3;
  LMDJ_CHECK(f.truth() == expected); f.artifact();
  const auto writes = f.platform->writes.load();
  const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  const auto changed = h.call("pattern.tempo.preview.commit", {{"ticket", ticket}, {"command_id", uuid(401)}});
  LMDJ_CHECK(changed.at("phase") == "commit_unknown" && changed.at("command_id") == uuid(400));
  LMDJ_CHECK(changed.at("error").at("details").at("reason") == "tempo_commit_identity_mismatch");
  LMDJ_CHECK(!h.send("pattern.tempo.preview.cancel", {{"ticket", ticket}}).at("ok").get<bool>());
  LMDJ_CHECK(!h.send("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", 3}}).at("ok").get<bool>());
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes);
  LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs);
  LMDJ_CHECK(h.call("pattern.tempo.preview.commit", command).at("committed_revision") == 3);
  f.render(128);
  LMDJ_CHECK(h.call("pattern.tempo.preview.status", {{"ticket", ticket}}).at("phase") == "committed");
  LMDJ_CHECK(h.call("pattern.tempo.preview.commit", command).at("committed_revision") == 3);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes);
  LMDJ_CHECK(f.history().at("undo_count") == f.baseline_undo + 1); f.artifact();
  f.transport(false);
  h.call("history.undo", {{"session_id", f.history().at("session_id")},
      {"command_id", uuid(402)}, {"expected_revision", 3}});
  expected.bpm = 120; expected.revision = 4;
  LMDJ_CHECK(f.truth() == expected && f.history().at("undo_count") == f.baseline_undo && f.history().at("redo_count") == 1);
  f.artifact(); h.bridge.reset(); f.reopen(expected);
}

void wrong_ticket_never_reaches_audio_or_storage() {
  Fixture f; BridgeHarness h(f);
  const auto ticket = h.call("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", 2}}).at("ticket");
  const auto writes = f.platform->writes.load(); const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  for (const auto* key : {"preview_token", "source_id", "project_id", "pattern_id", "expected_revision"}) {
    auto wrong = ticket;
    if (std::string_view(key) == "expected_revision") wrong[key] = 3;
    else if (std::string_view(key).ends_with("_id") && std::string_view(key) != "source_id") wrong[key] = uuid(999);
    else wrong[key] = "999";
    for (const auto* operation : {"pattern.tempo.preview.set", "pattern.tempo.preview.cancel",
         "pattern.tempo.preview.commit", "pattern.tempo.preview.status"}) {
      Json payload{{"ticket", wrong}};
      if (std::string_view(operation).ends_with(".set")) payload["bpm"] = 240;
      if (std::string_view(operation).ends_with(".commit")) payload["command_id"] = uuid(410);
      const auto refused = h.send(operation, payload);
      LMDJ_CHECK(!refused.at("ok").get<bool>());
      LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes);
      LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs);
    }
  }
  LMDJ_CHECK(h.call("pattern.tempo.preview.status", {{"ticket", ticket}}).at("phase") == "ready");
  f.artifact();
}

void retire_after_actual_join(Fixture& f, BridgeHarness& h) {
  LMDJ_CHECK(f.thread_callbacks != 0 && f.drain_requests == 1 && !f.physically_joined);
  LMDJ_CHECK(f.engine().telemetry().state == audio::RealtimeState::running);
  LMDJ_CHECK(!f.runtime->pattern_transport_shutdown_complete() && !h.bridge->terminal_release_ready());
  f.join_audio();
  LMDJ_CHECK(f.physically_joined && f.engine().telemetry().state == audio::RealtimeState::running);
  const auto watchdog = std::chrono::steady_clock::now() + std::chrono::seconds{2};
  do {
    f.runtime->service_pattern_transport();
    LMDJ_CHECK(std::chrono::steady_clock::now() < watchdog);
    std::this_thread::yield();
  } while (!f.runtime->pattern_transport_shutdown_complete());
  LMDJ_CHECK(f.runtime->failed() && f.engine().telemetry().state == audio::RealtimeState::stopped);
  LMDJ_CHECK(h.bridge->terminal_release_ready());
  LMDJ_CHECK(f.quiescence_calls == 0); // Timeout/failure did not fabricate operational success.
}

void failed_bridge_retains_bound_preview_until_real_callback_join() {
  Fixture f(true); BridgeHarness h(f); f.start_audio();
  const auto ticket = h.call("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", 2}}).at("ticket");
  h.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
  const auto watchdog = std::chrono::steady_clock::now() + std::chrono::seconds{2};
  while (h.call("pattern.tempo.preview.status", {{"ticket", ticket}}).at("phase") != "previewing")
    LMDJ_CHECK(std::chrono::steady_clock::now() < watchdog);
  f.pause_audio();
  const auto writes = f.platform->writes.load();
  const auto timeout = h.send("host.status", Json::object(), std::chrono::steady_clock::now());
  LMDJ_CHECK(!timeout.at("ok").get<bool>() && timeout.at("error").at("code") == "HOST_TIMEOUT");
  LMDJ_CHECK(f.runtime->failed() && h.bridge->failed());
  LMDJ_CHECK(!f.physically_joined && f.engine().telemetry().state == audio::RealtimeState::running);
  LMDJ_CHECK(!f.runtime->pattern_transport_shutdown_complete() && !h.bridge->terminal_release_ready());
  LMDJ_CHECK(h.call("pattern.tempo.preview.status", {{"ticket", ticket}}).at("applied").at("anchor").at("bpm") == 240);
  const auto new_save = h.send("pattern.tempo.preview.commit", {{"ticket", ticket}, {"command_id", uuid(420)}});
  LMDJ_CHECK(!new_save.at("ok").get<bool>() && new_save.at("error").at("details").at("reason") == "tempo_commit_unresolved");
  h.denied("pattern.tempo.preview.begin", {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", 2}});
  h.denied("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 180}});
  h.call("pattern.tempo.preview.cancel", {{"ticket", ticket}});
  LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes); f.artifact();
  retire_after_actual_join(f, h);
  LMDJ_CHECK(h.call("pattern.tempo.preview.status", {{"ticket", ticket}}).at("phase") == "source_lost");
  LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes);
  h.bridge.reset(); f.reopen(*f.baseline);
}

void failed_bridge_can_reconcile_only_the_original_published_save() {
  Fixture f(true); BridgeHarness h(f); f.start_audio();
  const auto ticket = h.call("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", 2}}).at("ticket");
  h.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
  const auto watchdog = std::chrono::steady_clock::now() + std::chrono::seconds{2};
  while (h.call("pattern.tempo.preview.status", {{"ticket", ticket}}).at("phase") != "previewing")
    LMDJ_CHECK(std::chrono::steady_clock::now() < watchdog);
  f.pause_audio(); f.platform->lose_manifest_response = true;
  const Json original{{"ticket", ticket}, {"command_id", uuid(430)}};
  LMDJ_CHECK(h.call("pattern.tempo.preview.commit", original).at("phase") == "commit_unknown");
  auto expected = *f.baseline; expected.bpm = 240; expected.revision = 3;
  LMDJ_CHECK(f.platform->lost_responses == 1 && f.truth() == expected);
  const auto writes = f.platform->writes.load();
  h.send("host.status", Json::object(), std::chrono::steady_clock::now());
  LMDJ_CHECK(f.runtime->failed() && h.bridge->failed());
  const auto new_save = h.send("pattern.tempo.preview.commit", {{"ticket", ticket}, {"command_id", uuid(431)}});
  LMDJ_CHECK(!new_save.at("ok").get<bool>() && new_save.at("error").at("details").at("reason") == "tempo_commit_unresolved");
  const auto saved = h.call("pattern.tempo.preview.commit", original);
  LMDJ_CHECK(saved.at("command_id") == uuid(430) && saved.at("committed_revision") == 3);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
  retire_after_actual_join(f, h);
  const auto retired = h.call("pattern.tempo.preview.status", {{"ticket", ticket}});
  LMDJ_CHECK(retired.at("command_id") == uuid(430) && retired.at("committed_revision") == 3 && retired.at("phase") == "source_lost");
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes);
  h.bridge.reset(); f.reopen(expected);
}

void failed_source_pending_does_not_emit_a_late_preview_or_retire_before_join() {
  Fixture f(true); BridgeHarness h(f); f.start_audio(); f.pause_audio();
  f.call("sequence.settings.update", {{"command_id", uuid(440)}, {"expected_revision", 2}, {"session_id", nullptr},
      {"bpm", nullptr}, {"quantize_enabled", false}, {"swing_percent", nullptr}});
  const auto expected = f.truth(); const auto writes = f.platform->writes.load();
  const auto ticket = h.call("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", 3}}).at("ticket");
  LMDJ_CHECK(h.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}}).at("phase") == "source_pending");
  const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  h.send("host.status", Json::object(), std::chrono::steady_clock::now());
  LMDJ_CHECK(f.runtime->failed() && h.bridge->failed());
  const auto retained = h.call("pattern.tempo.preview.status", {{"ticket", ticket}});
  LMDJ_CHECK(retained.at("phase") == "cancelling" && retained.at("preview_id") == "0");
  LMDJ_CHECK(retained.at("applied").at("anchor").at("bpm") == 120);
  LMDJ_CHECK(f.engine().pattern_telemetry().pending_generation != 0);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes);
  retire_after_actual_join(f, h);
  const auto retired = h.call("pattern.tempo.preview.status", {{"ticket", ticket}});
  LMDJ_CHECK(retired.at("phase") == "source_lost" && retired.at("preview_id") == "0");
  LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
  h.bridge.reset(); f.reopen(expected);
}

void ordinary_suspend_and_close_cancel_before_the_real_quiescence_gate() {
  for (const auto* operation : {"audio.suspend", "host.close"}) {
   for (const bool source_only : {false, true}) {
    Fixture f(true); f.start_audio();
    if (source_only) {
      f.pause_audio();
      f.call("sequence.settings.update", {{"command_id", uuid(450)}, {"expected_revision", 2}, {"session_id", nullptr},
          {"bpm", nullptr}, {"quantize_enabled", false}, {"swing_percent", nullptr}});
    }
    const auto expected = f.truth();
    const auto ticket = f.begin(source_only ? 3 : 2).at("ticket");
    const auto pending = f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
    if (source_only) LMDJ_CHECK(pending.at("phase") == "source_pending");
    else {
      const auto watchdog = std::chrono::steady_clock::now() + std::chrono::seconds{2};
      while (f.inspect(ticket).at("phase") != "previewing")
        LMDJ_CHECK(std::chrono::steady_clock::now() < watchdog);
    }
    const auto pubs = f.engine().pattern_telemetry().accepted_publications;
    const auto writes = f.platform->writes.load();
    f.render_enabled = true;
    f.call(operation, Json::object());
    LMDJ_CHECK(f.physically_joined && !f.audio_thread.joinable());
    LMDJ_CHECK(f.engine().telemetry().state == audio::RealtimeState::stopped && !f.runtime->failed());
    LMDJ_CHECK(f.quiescence_calls == 1 && f.drain_requests == 0);
    if (source_only) LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs);
    LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
    if (std::string_view{operation} == "audio.suspend") {
      const auto retired = f.inspect(ticket);
      LMDJ_CHECK(retired.at("ticket") == ticket && retired.at("phase") == "source_lost");
      LMDJ_CHECK(retired.at("applied").is_null() && retired.at("command_id").is_null());
      LMDJ_CHECK(retired.at("committed_bpm") == 120 && retired.at("project_revision") == expected.revision);
      if (source_only) LMDJ_CHECK(retired.at("preview_id") == "0");
      LMDJ_CHECK(f.call("pattern.tempo.preview.cancel", {{"ticket", ticket}}) == retired);
      LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();

      // Resume this actual Control owner, rather than cold-reopening away the
      // stale ticket. No frame-count oracle depends on the callback thread.
      f.call("audio.activate", Json::object());
      LMDJ_CHECK(f.inspect(ticket) == retired);
      f.transport(true); f.start_audio();
      const auto fresh = f.begin(expected.revision).at("ticket");
      LMDJ_CHECK(fresh != ticket);
      const auto stale = f.runtime->dispatch("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 180}}, {});
      LMDJ_CHECK(!stale.at("ok").get<bool>() &&
          stale.at("error").at("details").at("reason") == "tempo_preview_stale");
      f.call("pattern.tempo.preview.set", {{"ticket", fresh}, {"bpm", 240}});
      const auto resumed_deadline = std::chrono::steady_clock::now() + std::chrono::seconds{2};
      while (f.inspect(fresh).at("phase") != "previewing")
        LMDJ_CHECK(std::chrono::steady_clock::now() < resumed_deadline);
      f.call("pattern.tempo.preview.cancel", {{"ticket", fresh}});
      while (f.inspect(fresh).at("phase") != "cancelled")
        LMDJ_CHECK(std::chrono::steady_clock::now() < resumed_deadline);
      LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
      f.join_audio();
    }
    f.reopen(expected);
   }
  }
}

void ordinary_suspend_retains_only_the_original_saved_receipt() {
  for (const bool lose_response : {false, true}) {
    Fixture f(true); f.start_audio();
    const auto ticket = f.begin().at("ticket");
    f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{2};
    while (f.inspect(ticket).at("phase") != "previewing")
      LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    f.pause_audio(); f.platform->lose_manifest_response = lose_response;
    const Json original{{"ticket", ticket}, {"command_id", uuid(460)}};
    const auto saving = f.call("pattern.tempo.preview.commit", original);
    if (lose_response) LMDJ_CHECK(saving.at("phase") == "commit_unknown" && f.platform->lost_responses == 1);
    auto saved = *f.baseline; saved.bpm = 240; saved.revision = 3;
    LMDJ_CHECK(f.truth() == saved); f.artifact();
    const auto writes = f.platform->writes.load();
    f.render_enabled = true;
    f.call("audio.suspend", Json::object());
    LMDJ_CHECK(f.physically_joined && !f.audio_thread.joinable());
    LMDJ_CHECK(f.engine().telemetry().state == audio::RealtimeState::stopped && !f.runtime->failed());
    const auto retired = f.inspect(ticket);
    LMDJ_CHECK(retired.at("phase") == "source_lost" && retired.at("applied").is_null());
    LMDJ_CHECK(retired.at("command_id") == uuid(460) && retired.at("committed_revision") == 3 &&
        retired.at("project_revision") == 3 && retired.at("committed_bpm") == 240);
    LMDJ_CHECK(f.call("pattern.tempo.preview.commit", original) == retired);
    LMDJ_CHECK(f.call("pattern.tempo.preview.cancel", {{"ticket", ticket}}) == retired);
    const auto refused = f.runtime->dispatch("pattern.tempo.preview.commit",
        {{"ticket", ticket}, {"command_id", uuid(461)}}, {});
    LMDJ_CHECK(!refused.at("ok").get<bool>());
    LMDJ_CHECK(f.truth() == saved && f.platform->writes == writes); f.artifact();
    f.call("audio.activate", Json::object());
    LMDJ_CHECK(f.inspect(ticket) == retired);
    f.transport(true); f.start_audio();
    const auto fresh = f.begin(3).at("ticket");
    f.call("pattern.tempo.preview.set", {{"ticket", fresh}, {"bpm", 180}});
    const auto resumed_deadline = std::chrono::steady_clock::now() + std::chrono::seconds{2};
    while (f.inspect(fresh).at("phase") != "previewing")
      LMDJ_CHECK(std::chrono::steady_clock::now() < resumed_deadline);
    f.call("pattern.tempo.preview.cancel", {{"ticket", fresh}});
    Json restored_clock;
    do {
      restored_clock = f.inspect(fresh);
      LMDJ_CHECK(std::chrono::steady_clock::now() < resumed_deadline);
    } while (restored_clock.at("phase") != "cancelled");
    LMDJ_CHECK(restored_clock.at("applied").at("anchor").at("bpm") == 240);
    LMDJ_CHECK(f.truth() == saved && f.platform->writes == writes); f.artifact();
    f.join_audio(); f.transport(false);
    const auto history = f.history();
    LMDJ_CHECK(history.at("undo_count") == f.baseline_undo + 1);
    f.call("history.undo", {{"session_id", history.at("session_id")}, {"command_id", uuid(462)}, {"expected_revision", 3}});
    auto restored = *f.baseline; restored.revision = 4;
    LMDJ_CHECK(f.truth() == restored && f.history().at("redo_count") == 1); f.artifact();
    f.reopen(restored);
  }
}

Json note(unsigned tick, unsigned velocity = 127) {
  return {{"slot", {{"bank", 0}, {"pad", 0}}}, {"onset_tick", tick}, {"duration_tick", 1}, {"velocity", velocity}};
}

Json edit(Fixture& f, const std::string& pattern, Json put) {
  return f.call("pattern.events.edit", {{"command_id", f.command()}, {"expected_revision", f.truth().revision},
      {"pattern_id", pattern}, {"remove", Json::array()}, {"put", std::move(put)}});
}

void assert_pending_source_refuses(Fixture& f, const std::string& pattern) {
  const auto expected = f.truth(); const auto writes = f.platform->writes.load();
  const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  const auto refused = f.runtime->dispatch("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", pattern}, {"expected_revision", expected.revision}}, {});
  LMDJ_CHECK(!refused.at("ok").get<bool>());
  LMDJ_CHECK(refused.at("error").at("details").at("reason") == "pattern_switch_pending");
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes);
  LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs); f.artifact();
}

// Bind after the producer under proof, without publishing a fresh Snapshot
// to hide a lost cache entry. The source revision/generation are actual ones.
void source_preview_roundtrip(Fixture& f, const std::string& pattern,
    std::optional<Json> prepared_ticket = {}) {
  const auto expected = f.truth(); const auto history = f.history(); const auto writes = f.platform->writes.load();
  const auto ready = prepared_ticket ? *prepared_ticket : f.begin(expected.revision, pattern);
  LMDJ_CHECK(ready.at("phase") == "ready");
  LMDJ_CHECK(ready.at("source_revision").get<std::uint64_t>() <= expected.revision);
  LMDJ_CHECK(ready.at("ticket").at("source_id") == std::to_string(f.engine().pattern_telemetry().current_generation));
  LMDJ_CHECK(f.engine().current_pattern_id()->value() == pattern);
  const auto ticket = ready.at("ticket");
  const auto bpm = expected.bpm == 240 ? 180 : 240;
  f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", bpm}});
  Json preview;
  for (unsigned n = 0; n < 16; ++n) {
    f.render(128); f.runtime->service_pattern_transport(); preview = f.inspect(ticket);
    if (preview.at("phase") == "previewing") break;
  }
  if (preview.at("phase") != "previewing") std::cerr << "source preview did not apply: " << preview.dump() << '\n';
  LMDJ_CHECK(preview.at("phase") == "previewing" && preview.at("applied").at("anchor").at("bpm") == bpm);
  LMDJ_CHECK(preview.at("source_revision") == expected.revision);
  const auto& before = ready.at("applied").at("anchor"); const auto& after = preview.at("applied").at("anchor");
  const auto frame = std::stoull(after.at("frame").get<std::string>());
  const auto tick = std::stoull(after.at("tick_numerator").get<std::string>());
  LMDJ_CHECK(before.at("bpm") == expected.bpm);
  LMDJ_CHECK(tick == std::stoull(before.at("tick_numerator").get<std::string>()) +
      (ready.at("applied").at("playing").get<bool>() ?
          (frame - std::stoull(before.at("frame").get<std::string>())) * expected.bpm * 960 : 0));
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
  // A real allowed ordinary Pad still renders through the same Bank.
  if (f.count_in_output) {
    const auto press = f.input(); f.render(128); const auto pressed = f.settle_input(press);
    LMDJ_CHECK(pressed.at("native_result").at("disposition") == "voice_started");
    const auto release = f.input(true, pressed.at("admission").at("sequence")); f.render(128);
    LMDJ_CHECK(f.settle_input(release).at("native_result").at("disposition") == "release_applied");
  } else {
    f.call("trigger", {{"slot", 0}, {"velocity", 100}}); f.render(128);
    f.call("trigger", {{"slot", 0}, {"kind", "release"}}); f.render(128);
  }
  const auto publications = f.engine().pattern_telemetry().accepted_publications;
  const auto forbidden = f.runtime->dispatch("sequence.settings.update", {{"command_id", f.command()},
      {"expected_revision", expected.revision}, {"session_id", nullptr}, {"bpm", 180},
      {"quantize_enabled", nullptr}, {"swing_percent", nullptr}}, {});
  LMDJ_CHECK(!forbidden.at("ok").get<bool>() && forbidden.at("error").at("details").at("reason") == "tempo_preview_active");
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes &&
      f.engine().pattern_telemetry().accepted_publications == publications);
  if (preview.at("applied").at("playing")) {
    // Independent rational quarter strictly after the current manual frame.
    constexpr std::uint64_t quarter = 960ULL * 60 * 48'000;
    const auto slope = static_cast<std::uint64_t>(bpm) * 960;
    const auto now = f.engine().telemetry().rendered_frames;
    const auto target = ((tick + (now - frame) * slope) / quarter + 1) * quarter;
    const auto onset = frame + (target - tick + slope - 1) / slope;
    f.until(onset); const auto voices = f.engine().telemetry().started_voices;
    float l{}, r{}; f.engine().render(&l, &r, 1);
    LMDJ_CHECK(f.engine().telemetry().started_voices == voices + 1);
    f.engine().render(&l, &r, 1); LMDJ_CHECK(l > 0 && r > 0);
  }
  f.call("pattern.tempo.preview.cancel", {{"ticket", ticket}}); f.settle(ticket);
  LMDJ_CHECK(f.inspect(ticket).at("applied").at("anchor").at("bpm") == expected.bpm);
  LMDJ_CHECK(f.truth() == expected && f.history() == history && f.platform->writes == writes); f.artifact();
}

void live_and_stopped_edits_retain_their_actual_source() {
  for (const bool playing : {true, false}) {
    Fixture f(false, playing); auto expected = *f.baseline;
    const auto changed = edit(f, uuid(2), Json::array({note(0, 64)}));
    LMDJ_CHECK(changed.at("publication") == (playing ? "live" : "published"));
    expected.revision = 3; expected.patterns.at(foundation::PatternId{uuid(2)}).events[0].velocity = 64;
    LMDJ_CHECK(f.truth() == expected); assert_pending_source_refuses(f, uuid(2));
    f.render(128); f.runtime->service_pattern_transport();
    source_preview_roundtrip(f, uuid(2));
    if (!playing) {
      const auto voices = f.engine().telemetry().started_voices;
      f.transport(true);
      LMDJ_CHECK(f.engine().telemetry().started_voices > voices);
      source_preview_roundtrip(f, uuid(2));
    }
  }
}

void ordinary_bpm_publication_becomes_the_preview_source() {
  Fixture f;
  f.call("sequence.settings.update", {{"command_id", f.command()}, {"expected_revision", 2}, {"session_id", nullptr},
      {"bpm", 100}, {"quantize_enabled", nullptr}, {"swing_percent", nullptr}});
  auto expected = *f.baseline; expected.bpm = 100; expected.revision = 3;
  LMDJ_CHECK(f.truth() == expected);
  const auto pending = f.engine().pattern_telemetry();
  LMDJ_CHECK(pending.pending_generation != 0);
  assert_pending_source_refuses(f, uuid(2));
  f.until(pending.pending_activation_frame + 1); f.runtime->service_pattern_transport();
  const auto ready = f.begin(3);
  LMDJ_CHECK(ready.at("source_revision") == 3 &&
      ready.at("ticket").at("source_id") == std::to_string(pending.pending_generation));
  source_preview_roundtrip(f, uuid(2), ready);
  LMDJ_CHECK(f.truth() == expected);
}

void deferred_edit_and_explicit_refused_detent_use_actual_slots() {
  Fixture f; auto expected = *f.baseline;
  for (const unsigned tick : {6U, 7U, 8U}) {
    LMDJ_CHECK(edit(f, uuid(2), Json::array({note(tick)})).at("publication") == "live");
    f.until(f.origin + tick * 25 + 1);
    expected.patterns.at(foundation::PatternId{uuid(2)}).events.emplace_back(domain::PadSlotId{0, 0}, tick, 1, 127);
    ++expected.revision;
  }
  LMDJ_CHECK(f.engine().telemetry().active_voices == 4);
  const auto source = f.engine().pattern_telemetry().current_generation;
  LMDJ_CHECK(edit(f, uuid(2), Json::array({note(9)})).at("publication") == "deferred");
  expected.patterns.at(foundation::PatternId{uuid(2)}).events.emplace_back(domain::PadSlotId{0, 0}, 9, 1, 127);
  ++expected.revision;
  auto& events = expected.patterns.at(foundation::PatternId{uuid(2)}).events;
  std::sort(events.begin(), events.end(), [](const auto& a, const auto& b) { return a.onset_tick < b.onset_tick; });
  LMDJ_CHECK(f.truth() == expected && f.engine().pattern_telemetry().current_generation == source);
  assert_pending_source_refuses(f, uuid(2));
  // The first real one-shot releases its old Pattern slot at frame480.
  f.until(f.origin + 481); f.runtime->service_pattern_transport();
  LMDJ_CHECK(f.engine().pattern_telemetry().pending_generation != 0);
  assert_pending_source_refuses(f, uuid(2));
  f.render(1); f.runtime->service_pattern_transport();
  const auto ready = f.begin(expected.revision);
  LMDJ_CHECK(ready.at("source_revision") == expected.revision &&
      ready.at("ticket").at("source_id") != std::to_string(source));
  const auto writes = f.platform->writes.load(); const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  const auto ticket = ready.at("ticket");
  const auto refused = f.runtime->dispatch("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}}, {});
  LMDJ_CHECK(!refused.at("ok").get<bool>() &&
      refused.at("error").at("details").at("reason") == "tempo_publication_slots_full");
  LMDJ_CHECK(f.inspect(ticket).at("phase") == "preview_refused");
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes &&
      f.engine().pattern_telemetry().accepted_publications == pubs);
  f.until(f.origin + 801); f.runtime->service_pattern_transport();
  LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs); // No automatic replay of the refused detent.
  source_preview_roundtrip(f, uuid(2), ready); // Explicit same-ticket retry after actual reclaim.
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
}

void cancelled_queued_switch_keeps_the_still_applied_source() {
  Fixture f;
  f.call("pattern.create", {{"command_id", f.command()}, {"expected_revision", 2}, {"pattern_id", uuid(3)}, {"bars", 1}});
  const auto expected = f.truth(); const auto writes = f.platform->writes.load();
  const auto original = f.engine().pattern_telemetry().current_generation;
  const auto queued = f.call("pattern.transport.switch", {{"pattern_id", uuid(3)}, {"request_id", f.command()}, {"snap", "beat"}});
  LMDJ_CHECK(queued.at("activation_frame").get<std::uint64_t>() > f.engine().telemetry().rendered_frames);
  assert_pending_source_refuses(f, uuid(2));
  // No callback claimed B: withdrawing it must leave the actual A source
  // available even though B was the latest accepted candidate.
  const auto cancelled = f.call("pattern.transport.switch", {{"pattern_id", uuid(2)}, {"request_id", f.command()}, {"snap", "beat"}});
  LMDJ_CHECK(cancelled.at("activation_frame").is_null());
  LMDJ_CHECK(f.engine().pattern_telemetry().current_generation == original && f.engine().pattern_telemetry().pending_generation == 0);
  const auto ready = f.begin(expected.revision);
  LMDJ_CHECK(ready.at("ticket").at("source_id") == std::to_string(original));
  LMDJ_CHECK(ready.at("source_revision") == 2);
  source_preview_roundtrip(f, uuid(2), ready);
  LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes); f.artifact();
}

void claimed_predecessor_applies_before_successor_withdrawal() {
  Fixture f;
  f.call("pattern.create", {{"command_id", f.command()}, {"expected_revision", 2}, {"pattern_id", uuid(3)}, {"bars", 1}});
  edit(f, uuid(3), Json::array({note(0), note(960), note(1920), note(2880)}));
  f.call("pattern.create", {{"command_id", f.command()}, {"expected_revision", 4}, {"pattern_id", uuid(4)}, {"bars", 1}});
  const auto expected = f.truth();
  const auto b = f.call("pattern.transport.switch", {{"pattern_id", uuid(3)}, {"request_id", f.command()}, {"snap", "beat"}});
  float l{}, r{}; f.engine().render(&l, &r, 0); // Audio claims B, without applying it.
  const auto claimed = f.engine().pattern_transport_observation();
  LMDJ_CHECK(claimed && claimed->pending_switches[0] && !claimed->pending_switches[1]);
  const auto b_generation = claimed->pending_switches[0]->generation;
  const auto c = f.call("pattern.transport.switch", {{"pattern_id", uuid(4)}, {"request_id", f.command()}, {"snap", "beat"}});
  const auto both = f.engine().pattern_transport_observation();
  LMDJ_CHECK(both && both->pending_switches[0] && both->pending_switches[1]);
  // No Host cadence runs between B's actual apply and withdrawing C. Keeping
  // only A plus the latest accepted C would lose the source under proof.
  f.until(b.at("activation_frame").get<std::uint64_t>() + 1);
  LMDJ_CHECK(f.engine().pattern_telemetry().current_generation == b_generation);
  const auto cancelled = f.call("pattern.transport.switch", {{"pattern_id", uuid(3)}, {"request_id", f.command()}, {"snap", "beat"}});
  LMDJ_CHECK(cancelled.at("activation_frame").is_null());
  const auto withdrawing = f.engine().pattern_transport_observation();
  LMDJ_CHECK(withdrawing && withdrawing->outstanding_cancellation);
  assert_pending_source_refuses(f, uuid(3));
  f.until(c.at("activation_frame").get<std::uint64_t>() + 1);
  const auto retired = f.engine().pattern_transport_observation();
  LMDJ_CHECK(retired && !retired->outstanding_cancellation && retired->current_generation == b_generation);
  const auto ready = f.begin(expected.revision, uuid(3));
  LMDJ_CHECK(ready.at("ticket").at("source_id") == std::to_string(b_generation));
  LMDJ_CHECK(ready.at("source_revision") == expected.revision);
  source_preview_roundtrip(f, uuid(3), ready);
  LMDJ_CHECK(f.truth() == expected); f.artifact();
}

void idle_pattern_io(Fixture& f) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
  do {
    f.runtime->service_pattern_transport();
    if (web_runtime::detail::ControlRuntimePatternIoAccess::idle(*f.runtime)) return;
    LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    std::this_thread::sleep_for(std::chrono::milliseconds{1});
  } while (true);
}

void recording_switch_overlay_closes_to_a_previewable_actual_source() {
  Fixture f(false, true, true, true);
  f.call("pattern.create", {{"command_id", f.command()}, {"expected_revision", 3}, {"pattern_id", uuid(3)}, {"bars", 1}});
  edit(f, uuid(3), Json::array({note(0), note(960), note(1920), note(2880)}));
  auto expected = f.truth();
  f.record(true); idle_pattern_io(f);
  const auto pubs = f.engine().pattern_telemetry().accepted_publications;
  const auto refused = f.runtime->dispatch("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", expected.revision}}, {});
  LMDJ_CHECK(!refused.at("ok").get<bool>() &&
      refused.at("error").at("details").at("reason") == "tempo_recording_active");
  LMDJ_CHECK(f.truth() == expected && f.engine().pattern_telemetry().accepted_publications == pubs);
  const auto switched = f.call("pattern.transport.switch", {{"pattern_id", uuid(3)}, {"request_id", f.command()}, {"snap", "beat"}});
  const auto boundary = switched.at("activation_frame").get<std::uint64_t>();
  f.until(boundary + 1); idle_pattern_io(f);
  LMDJ_CHECK(f.transport_status().at("recording") == true && f.engine().current_pattern_id()->value() == uuid(3));
  LMDJ_CHECK(f.truth() == expected); // The empty A segment changes no revision.
  f.until(boundary + 6'000);
  const auto press = f.input(); f.render(1); const auto pressed = f.settle_input(press);
  LMDJ_CHECK(pressed.at("native_result").at("disposition") == "voice_started" &&
      pressed.at("native_result").at("runtime_frame") == boundary + 6'000);
  f.until(boundary + 12'000);
  const auto release = f.input(true, pressed.at("admission").at("sequence")); f.render(1);
  const auto released = f.settle_input(release);
  if (released.at("native_result").at("disposition") != "release_applied")
    std::cerr << "recording release: " << released.dump() << '\n';
  LMDJ_CHECK(released.at("native_result").at("disposition") == "release_applied");
  f.record(false); idle_pattern_io(f);
  ++expected.revision;
  auto& events = expected.patterns.at(foundation::PatternId{uuid(3)}).events;
  events.emplace_back(domain::PadSlotId{0, 0}, 240, 240, 100);
  std::sort(events.begin(), events.end(), [](const auto& a, const auto& b) { return a.onset_tick < b.onset_tick; });
  LMDJ_CHECK(f.truth() == expected && f.transport_status().at("current_pattern_id") == uuid(3));
  LMDJ_CHECK(f.engine().pattern_telemetry().pending_generation == 0); f.artifact();
  const auto ready = f.begin(expected.revision, uuid(3));
  LMDJ_CHECK(ready.at("source_revision") == expected.revision);
  source_preview_roundtrip(f, uuid(3), ready);
  f.transport(false); f.reopen(expected);
}

void scheduled_count_in_receipts_close_before_previewing_the_clean_source() {
  Fixture f(false, false, true, true); auto expected = *f.baseline;
  const auto capability = f.call("pattern.transport.count-in.capabilities", {{"negotiate", false}});
  const auto publications = f.engine().pattern_telemetry().accepted_publications;
  const auto requested = f.call("pattern.transport.count-in.request", {{"session_id", uuid(20)}, {"project_id", uuid(1)},
      {"command_id", f.command()}, {"runtime_generation", capability.at("runtime_generation")},
      {"frame_epoch", capability.at("frame_epoch")}, {"schedule_serial", "1"}, {"expected_epoch", "1"},
      {"bars", 1}, {"expected_revision", nullptr}});
  const auto ticket = requested.at("ticket"); auto inspection = ticket; inspection["consume"] = false;
  f.render(128);
  const auto armed = f.call("pattern.transport.count-in.inspect", inspection);
  const auto start = armed.at("count_in").at("start_frame").get<std::uint64_t>();
  f.until(start + 1);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
  Json applied;
  do {
    applied = f.call("pattern.transport.count-in.inspect", inspection);
    if (applied.at("opening_complete") == true) break;
    LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    std::this_thread::sleep_for(std::chrono::milliseconds{1});
  } while (true);
  LMDJ_CHECK(applied.at("start_receipt").at("result") == "applied" &&
      applied.at("start_receipt").at("effective_frame") == start);
  // Scheduled arm owns the existing prepared view, not a new publication.
  LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == publications && f.truth() == expected);
  const auto refused = f.runtime->dispatch("pattern.tempo.preview.begin",
      {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", expected.revision}}, {});
  LMDJ_CHECK(!refused.at("ok").get<bool>() &&
      refused.at("error").at("details").at("reason") == "tempo_recording_active");
  f.until(start + 6'000); const auto press = f.input(); f.render(1); const auto pressed = f.settle_input(press);
  LMDJ_CHECK(pressed.at("native_result").at("disposition") == "voice_started");
  f.until(start + 12'000); const auto release = f.input(true, pressed.at("admission").at("sequence"));
  f.render(1); LMDJ_CHECK(f.settle_input(release).at("native_result").at("disposition") == "release_applied");
  auto cancel = ticket; cancel["start_command_id"] = ticket.at("command_id"); cancel["command_id"] = f.command();
  cancel["project_id"] = uuid(1); cancel["expected_epoch"] = "2"; cancel["intent"] = "play_stop";
  const auto cutoff = f.engine().telemetry().rendered_frames;
  f.call("pattern.transport.count-in.cancel", cancel); f.render(1);
  Json closed;
  do {
    closed = f.call("pattern.transport.count-in.inspect", inspection); idle_pattern_io(f);
    const auto state = f.transport_status();
    if (state.at("recording") == false && state.at("phase") == "idle" &&
        state.at("publication_pending") == false && f.engine().pattern_telemetry().pending_generation == 0) break;
    LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    const auto pending = f.engine().pattern_telemetry();
    if (pending.pending_generation) f.until(std::max(f.engine().telemetry().rendered_frames, pending.pending_activation_frame) + 1);
    else if (state.at("phase") == "awaiting_audio") f.render(128);
    std::this_thread::sleep_for(std::chrono::milliseconds{1});
  } while (true);
  closed = f.call("pattern.transport.count-in.inspect", inspection);
  LMDJ_CHECK(closed.at("start_receipt") == applied.at("start_receipt") && closed.at("error").is_null());
  LMDJ_CHECK(closed.at("cancel_receipt").at("result") == "applied" &&
      closed.at("cancel_receipt").at("effective_frame") == cutoff);
  inspection["consume"] = true; LMDJ_CHECK(f.call("pattern.transport.count-in.inspect", inspection) == closed);
  ++expected.revision; auto& events = expected.patterns.at(foundation::PatternId{uuid(2)}).events;
  events.emplace_back(domain::PadSlotId{0, 0}, 240, 240, 100);
  std::sort(events.begin(), events.end(), [](const auto& a, const auto& b) { return a.onset_tick < b.onset_tick; });
  LMDJ_CHECK(f.truth() == expected && f.transport_status().at("playing") == false); f.artifact();
  source_preview_roundtrip(f, uuid(2));
  f.transport(true); source_preview_roundtrip(f, uuid(2));
  f.transport(false); f.reopen(expected);
}

void performance_gateways_and_both_replay_restores_retain_their_source() {
  for (const bool playing : {true, false}) {
    Fixture f(false, playing);
    const auto session = uuid(6'000), performance = uuid(6'001), replay = uuid(6'002), gesture = uuid(6'003);
    f.call("pattern.slot.assign", {{"command_id", f.command()}, {"expected_revision", 2},
        {"pattern_slot", 1}, {"pattern_id", uuid(2)}});
    const auto before = f.truth();
    f.call("performance.record.begin", {{"command_id", f.command()}, {"expected_revision", before.revision},
        {"session_id", session}, {"performance_id", performance}});
    const auto recording_revision = f.truth().revision;
    LMDJ_CHECK(recording_revision == before.revision + 1); // Durable draft creation is authoring.
    f.call("performance.record.event", {{"session_id", session}, {"event_id", f.command()},
        {"event", {{"kind", "pad_press"}, {"gesture_id", gesture}, {"slot", 0}, {"velocity", 127}}}});
    f.render(2'400);
    f.call("performance.record.event", {{"session_id", session}, {"event_id", f.command()},
        {"event", {{"kind", "pad_release"}, {"gesture_id", gesture}, {"slot", 0}}}});
    const auto generation = f.engine().pattern_telemetry().current_generation;
    f.call("performance.record.launch-request", {{"session_id", session}, {"request_id", f.command()}, {"pattern_slot", 1}});
    const auto launch = f.engine().pattern_telemetry();
    LMDJ_CHECK(launch.pending_generation != 0 && launch.pending_generation != generation);
    f.until(std::max(f.engine().telemetry().rendered_frames, launch.pending_activation_frame) + 1);
    static_cast<void>(f.runtime->service_performance());
    LMDJ_CHECK(f.engine().pattern_telemetry().current_generation == launch.pending_generation);
    f.render(4'800);
    const auto tail = f.command();
    f.call("performance.record.event", {{"session_id", session}, {"event_id", f.command()},
        {"event", {{"kind", "pad_press"}, {"gesture_id", tail}, {"slot", 0}, {"velocity", 100}}}});
    f.render(128);
    f.call("performance.record.event", {{"session_id", session}, {"event_id", f.command()},
        {"event", {{"kind", "pad_release"}, {"gesture_id", tail}, {"slot", 0}}}});
    f.call("performance.record.stop", {{"session_id", session}, {"request_id", f.command()}});
    const auto stopped_revision = f.truth().revision;
    LMDJ_CHECK(stopped_revision == before.revision + 1);
    f.call("performance.save", {{"command_id", f.command()}, {"expected_revision", stopped_revision},
        {"performance_id", performance}, {"name", "Tempo source gateways"}, {"recording_artifact", nullptr}});
    const auto expected = f.truth();
    LMDJ_CHECK(expected.revision == stopped_revision + 1 && expected.patterns == before.patterns &&
        expected.assets == before.assets && expected.banks == before.banks);
    const auto ready = f.begin(expected.revision);
    LMDJ_CHECK(ready.at("source_revision") == recording_revision &&
        ready.at("ticket").at("source_id") == std::to_string(launch.pending_generation));
    source_preview_roundtrip(f, uuid(2), ready); // Composed normal publication + metadata-only adoption.
    f.call("performance.replay.begin", {{"replay_id", replay}, {"performance_id", performance}});
    f.render(128); static_cast<void>(f.runtime->service_performance());
    LMDJ_CHECK(f.call("performance.replay.status", {{"replay_id", replay}}).at("state") == "playing");
    const auto replay_generation = f.engine().pattern_telemetry().current_generation;
    // The replay's launch occurs after its real Pad hold. Its immediate view
    // is a different actual Native generation, not the old selected source.
    for (unsigned n = 0; n < 1024 && f.engine().pattern_telemetry().current_generation == replay_generation; ++n) {
      f.render(128); static_cast<void>(f.runtime->service_performance());
    }
    LMDJ_CHECK(f.engine().pattern_telemetry().current_generation != replay_generation);
    const auto pubs = f.engine().pattern_telemetry().accepted_publications;
    const auto refused = f.runtime->dispatch("pattern.tempo.preview.begin",
        {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", expected.revision}}, {});
    LMDJ_CHECK(!refused.at("ok").get<bool>() &&
        refused.at("error").at("details").at("reason") == "tempo_replay_active");
    LMDJ_CHECK(f.truth() == expected && f.engine().pattern_telemetry().accepted_publications == pubs);
    f.call("performance.replay.stop", {{"replay_id", replay}, {"request_id", f.command()}});
    for (unsigned n = 0; n < 64; ++n) {
      f.render(128); static_cast<void>(f.runtime->service_performance());
      if (f.call("performance.replay.status", {{"replay_id", replay}}).at("state") != "playing") break;
    }
    LMDJ_CHECK(f.call("performance.replay.status", {{"replay_id", replay}}).at("state") != "playing");
    static_cast<void>(f.runtime->service_performance());
    const auto restore = f.engine().pattern_telemetry();
    LMDJ_CHECK(restore.accepted_publications > pubs);
    if (restore.pending_generation) f.until(std::max(f.engine().telemetry().rendered_frames, restore.pending_activation_frame) + 1);
    f.runtime->service_pattern_transport();
    const auto restored = f.begin(expected.revision);
    LMDJ_CHECK(restored.at("source_revision") == expected.revision &&
        restored.at("ticket").at("source_id") != ready.at("ticket").at("source_id"));
    source_preview_roundtrip(f, uuid(2), restored);
    if (!playing) { f.transport(true); source_preview_roundtrip(f, uuid(2)); }
    f.transport(false); f.reopen(expected);
  }
}

void facade_recording_and_import_admission_precedes_source_adoption(bool importing) {
    Fixture f;
    if (importing) {
      f.call("sequence.settings.update", {{"command_id", f.command()}, {"expected_revision", 2}, {"session_id", nullptr},
          {"bpm", nullptr}, {"quantize_enabled", false}, {"swing_percent", nullptr}});
      f.call("sample.import.begin", {{"import_token", uuid(6'100)}, {"command_id", f.command()},
          {"expected_revision", 3}, {"slot", {{"bank", 0}, {"pad", 0}}}, {"asset_id", uuid(6'101)}, {"byte_length", wav().size()}});
    } else {
      f.call("performance.record.begin", {{"command_id", f.command()}, {"expected_revision", 2},
          {"session_id", uuid(6'102)}, {"performance_id", uuid(6'103)}});
    }
    const auto expected = f.truth(); const auto history = f.history(); const auto writes = f.platform->writes.load();
    const auto pubs = f.engine().pattern_telemetry().accepted_publications;
    const auto response = f.runtime->dispatch("pattern.tempo.preview.begin",
        {{"project_id", uuid(1)}, {"pattern_id", uuid(2)}, {"expected_revision", expected.revision}}, {});
    if (response.at("ok").get<bool>()) {
      const auto ticket = response.at("result").at("ticket");
      const auto set = f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
      f.render(128); f.runtime->service_pattern_transport();
      std::cerr << "unprotected Facade owner: importing=" << importing << " first_set=" << set.dump()
          << " Native publication delta=" << f.engine().pattern_telemetry().accepted_publications - pubs << '\n';
    }
    LMDJ_CHECK(!response.at("ok").get<bool>());
    LMDJ_CHECK(response.at("error").at("details").at("reason") ==
        (importing ? "sample_import_pending" : "tempo_recording_active"));
    LMDJ_CHECK(f.truth() == expected && f.history() == history && f.platform->writes == writes &&
        f.engine().pattern_telemetry().accepted_publications == pubs); f.artifact();
    if (importing) f.call("sample.import.abort", {{"import_token", uuid(6'100)}});
    else {
      f.call("performance.record.event", {{"session_id", uuid(6'102)}, {"event_id", f.command()},
          {"event", {{"kind", "pad_press"}, {"gesture_id", uuid(6'104)}, {"slot", 0}, {"velocity", 127}}}});
      f.render(128);
      f.call("performance.record.event", {{"session_id", uuid(6'102)}, {"event_id", f.command()},
          {"event", {{"kind", "pad_release"}, {"gesture_id", uuid(6'104)}, {"slot", 0}}}});
      f.call("performance.record.stop", {{"session_id", uuid(6'102)}, {"request_id", f.command()}});
      f.call("performance.save", {{"command_id", f.command()}, {"expected_revision", f.truth().revision},
          {"performance_id", uuid(6'103)}, {"name", "Admission owner"}, {"recording_artifact", nullptr}});
    }
    source_preview_roundtrip(f, uuid(2));
}

void concurrent_render_retains_sources_and_makes_accepted_and_refused_progress() {
  Fixture f(true); f.start_audio();
  const auto writes = f.platform->writes.load();
  unsigned accepted{}, refused{}, cancelled{};
  for (unsigned turn = 0; turn < 64; ++turn) {
    f.pause_audio();
    const auto ticket = f.begin().at("ticket");
    const auto first = f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
    LMDJ_CHECK(first.at("phase") == "preview_pending"); ++accepted;
    // The real callback cannot have consumed this publication. This exact
    // owner must refuse a second detent rather than lose or replace it.
    const auto second = f.runtime->dispatch("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 180}}, {});
    LMDJ_CHECK(!second.at("ok").get<bool>() && second.at("error").at("details").at("reason") == "tempo_preview_pending");
    ++refused;
    const auto pubs = f.engine().pattern_telemetry().accepted_publications;
    LMDJ_CHECK(!f.runtime->dispatch("snapshot.reload", {{"pattern_id", uuid(2)}}, {}).at("ok").get<bool>());
    LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == pubs);
    f.render_enabled = true;
    const auto watchdog = std::chrono::steady_clock::now() + std::chrono::seconds{2};
    Json actual;
    do {
      f.runtime->service_pattern_transport();
      actual = f.inspect(ticket);
      f.runtime->drain_outcomes(); f.runtime->drain_voice_states();
      LMDJ_CHECK(std::chrono::steady_clock::now() < watchdog);
    } while (actual.at("phase") != "previewing");
    LMDJ_CHECK(actual.at("applied").at("anchor").at("bpm") == 240);
    f.call("pattern.tempo.preview.cancel", {{"ticket", ticket}});
    do {
      f.runtime->service_pattern_transport(); actual = f.inspect(ticket);
      f.runtime->drain_outcomes(); f.runtime->drain_voice_states();
      LMDJ_CHECK(std::chrono::steady_clock::now() < watchdog);
    } while (actual.at("phase") != "cancelled");
    LMDJ_CHECK(actual.at("applied").at("anchor").at("bpm") == 120); ++cancelled;
    // Retain the actual adopted source while audio continues to read it,
    // release the B2 binding, then begin the next turn from that exact copy.
    LMDJ_CHECK(f.call("audio.activate", Json::object()).at("changed") == false);
    LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes);
    LMDJ_CHECK(f.history().at("undo_count") == f.baseline_undo && !f.runtime->failed());
    f.artifact();
  }
  f.join_audio();
  LMDJ_CHECK(accepted == 64 && refused == 64 && cancelled == 64 && f.thread_callbacks != 0);
  LMDJ_CHECK(f.engine().pattern_telemetry().accepted_publications == 2 + 128);
  LMDJ_CHECK(f.truth() == *f.baseline && f.platform->writes == writes);
  std::cout << "real tempo render progress: " << accepted << " admitted, " << refused
      << " pending refused, " << cancelled << " actually cancelled; callbacks=" << f.thread_callbacks << '\n';
}

void concurrent_edits_publish_new_sources_between_preview_turns() {
  Fixture f(true); auto expected = *f.baseline; f.start_audio();
  unsigned applied{}, previewed{}, cancelled{};
  for (unsigned n = 0; n < 32; ++n) {
    const auto velocity = n % 2 == 0 ? 64 : 127;
    LMDJ_CHECK(edit(f, uuid(2), Json::array({note(0, velocity)})).at("publication") == "live");
    ++expected.revision;
    expected.patterns.at(foundation::PatternId{uuid(2)}).events[0].velocity = static_cast<std::uint8_t>(velocity);
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{2};
    do {
      f.runtime->service_pattern_transport();
      f.runtime->drain_outcomes(); f.runtime->drain_voice_states();
      LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    } while (f.engine().pattern_telemetry().pending_generation != 0);
    const auto ready = f.begin(expected.revision); const auto ticket = ready.at("ticket"); ++applied;
    LMDJ_CHECK(ready.at("source_revision") == expected.revision &&
        ticket.at("source_id") == std::to_string(f.engine().pattern_telemetry().current_generation));
    const auto writes = f.platform->writes.load();
    f.call("pattern.tempo.preview.set", {{"ticket", ticket}, {"bpm", 240}});
    Json status;
    do {
      f.runtime->service_pattern_transport(); status = f.inspect(ticket);
      f.runtime->drain_outcomes(); f.runtime->drain_voice_states();
      LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    } while (status.at("phase") != "previewing");
    LMDJ_CHECK(status.at("applied").at("anchor").at("bpm") == 240); ++previewed;
    f.call("pattern.tempo.preview.cancel", {{"ticket", ticket}});
    do {
      f.runtime->service_pattern_transport(); status = f.inspect(ticket);
      f.runtime->drain_outcomes(); f.runtime->drain_voice_states();
      LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    } while (status.at("phase") != "cancelled");
    LMDJ_CHECK(status.at("applied").at("anchor").at("bpm") == 120); ++cancelled;
    LMDJ_CHECK(f.truth() == expected && f.platform->writes == writes && !f.runtime->failed()); f.artifact();
  }
  f.join_audio();
  LMDJ_CHECK(applied == 32 && previewed == 32 && cancelled == 32 && f.thread_callbacks > 0);
  LMDJ_CHECK(f.history().at("undo_count") == f.baseline_undo + 32 && f.truth() == expected);
  std::cout << "real source publication progress: " << applied << " edits, " << previewed
      << " previews, " << cancelled << " restores; callbacks=" << f.thread_callbacks << '\n';
}
} // namespace
int main(int argc, char** argv) {
  try {
    const std::string group = argc == 2 ? argv[1] : "all";
    if (group == "journey" || group == "all") actual_cancel_save_exact_retry_undo_reopen();
    if (group == "source" || group == "all") {
      non_bpm_truth_revision_can_begin_and_preview_without_restarting();
      cancelling_applied_source_adoption_never_issues_the_cancelled_audible_set();
      early_commit_during_source_adoption_is_known_refusal_then_exact_save();
    }
    if (group == "identity" || group == "all") {
      cancel_before_first_set_rejects_a_late_old_set();
      wrong_ticket_never_reaches_audio_or_storage();
    }
    if (group == "recovery" || group == "all") bridge_published_response_loss_keeps_exact_save_then_undo_and_reopen();
    if (group == "terminal" || group == "all") {
      failed_bridge_retains_bound_preview_until_real_callback_join();
      failed_bridge_can_reconcile_only_the_original_published_save();
      failed_source_pending_does_not_emit_a_late_preview_or_retire_before_join();
      ordinary_suspend_and_close_cancel_before_the_real_quiescence_gate();
      ordinary_suspend_retains_only_the_original_saved_receipt();
    }
    if (group == "stress" || group == "all") concurrent_render_retains_sources_and_makes_accepted_and_refused_progress();
    if (group == "edit" || group == "all") live_and_stopped_edits_retain_their_actual_source();
    if (group == "switch" || group == "all") cancelled_queued_switch_keeps_the_still_applied_source();
    if (group == "handoff" || group == "all") claimed_predecessor_applies_before_successor_withdrawal();
    if (group == "settings" || group == "all") ordinary_bpm_publication_becomes_the_preview_source();
    if (group == "deferred" || group == "all") deferred_edit_and_explicit_refused_detent_use_actual_slots();
    if (group == "recording" || group == "all") recording_switch_overlay_closes_to_a_previewable_actual_source();
    if (group == "scheduled" || group == "all") scheduled_count_in_receipts_close_before_previewing_the_clean_source();
    if (group == "performance" || group == "all") performance_gateways_and_both_replay_restores_retain_their_source();
    if (group == "record-admission" || group == "all") facade_recording_and_import_admission_precedes_source_adoption(false);
    if (group == "import-admission" || group == "all") facade_recording_and_import_admission_precedes_source_adoption(true);
    if (group == "publication-stress" || group == "all") concurrent_edits_publish_new_sources_between_preview_turns();
    LMDJ_CHECK(group == "journey" || group == "source" || group == "identity" || group == "recovery" || group == "terminal" || group == "stress" || group == "edit" || group == "switch" || group == "handoff" || group == "settings" || group == "deferred" || group == "recording" || group == "scheduled" || group == "performance" || group == "record-admission" || group == "import-admission" || group == "publication-stress" || group == "all");
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
  return 0;
}
