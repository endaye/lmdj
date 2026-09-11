#include "apps/cardputer-host/main/audio_driver.hpp"
#include "apps/cardputer-host/main/runtime_host.hpp"
#include <lmdj/cooker/runtime_content.hpp>
#include "tests/core/support/test.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <string>
#include <limits>
#include <thread>
#include <vector>

namespace {
using namespace lmdj::cardputer;
struct FakeIo final : AudioIo {
  std::vector<std::string> calls;
  std::string fail_at;
  bool short_write{};
  bool call(const char* name) { calls.emplace_back(name); return fail_at != name; }
  bool configure() noexcept override { return call("configure"); }
  bool mute(bool on) noexcept override { return call(on ? "mute" : "unmute"); }
  bool enable() noexcept override { return call("enable"); }
  bool write(std::span<const std::int16_t> pcm, std::size_t& accepted) noexcept override {
    accepted = pcm.size() - (short_write ? 1 : 0);
    return call(std::all_of(pcm.begin(), pcm.end(), [](auto v) { return v == 0; })
                    ? "zero" : "music");
  }
  bool drain() noexcept override { return call("drain"); }
  bool disable_and_quiesce() noexcept override { return call("disable"); }
  bool release() noexcept override { return call("release"); }
};

void prewarm_must_reach_output_before_unmute() {
  FakeIo io;
  AudioDriver driver(io, 2);
  LMDJ_CHECK(driver.start());
  LMDJ_CHECK(io.calls == (std::vector<std::string>{"configure", "mute", "enable", "zero", "zero", "drain", "unmute"}));
  LMDJ_CHECK(driver.running());
  LMDJ_CHECK(driver.stop());
}

void stop_must_drain_before_quiescence_and_release() {
  FakeIo io;
  AudioDriver driver(io, 2);
  LMDJ_CHECK(driver.start());
  io.calls.clear();
  LMDJ_CHECK(driver.stop());
  LMDJ_CHECK(io.calls == (std::vector<std::string>{"mute", "zero", "zero", "drain", "disable", "release"}));
  LMDJ_CHECK(driver.released());
  LMDJ_CHECK(!driver.running());
}

void explicit_prewarm_is_not_reduced_to_ring_size() {
  FakeIo io;
  AudioDriver driver(io, 2, 5);
  LMDJ_CHECK(driver.start());
  LMDJ_CHECK(std::count(io.calls.begin(), io.calls.end(), "zero") == 5);
  const auto drained = std::find(io.calls.begin(), io.calls.end(), "drain");
  const auto unmuted = std::find(io.calls.begin(), io.calls.end(), "unmute");
  LMDJ_CHECK(drained < unmuted);
  LMDJ_CHECK(driver.stop());
  LMDJ_CHECK(driver.physical_stopped());
}

void failed_quiescence_cannot_release_callback_storage() {
  FakeIo io;
  AudioDriver driver(io, 2);
  LMDJ_CHECK(driver.start());
  io.fail_at = "disable";
  io.calls.clear();
  LMDJ_CHECK(!driver.stop());
  LMDJ_CHECK(!driver.released());
  LMDJ_CHECK(std::find(io.calls.begin(), io.calls.end(), "release") == io.calls.end());
  io.fail_at.clear();
  LMDJ_CHECK(!driver.stop()); // Historical failure is retained even after cleanup.
  LMDJ_CHECK(driver.released());
}

void partial_configuration_is_cleaned() {
  FakeIo io;
  io.fail_at = "configure";
  AudioDriver driver(io, 2);
  LMDJ_CHECK(!driver.start());
  LMDJ_CHECK(driver.failure() == AudioFailure::configure);
  LMDJ_CHECK(driver.released());
  LMDJ_CHECK(io.calls == (std::vector<std::string>{"configure", "mute", "release"}));
}

void short_music_write_stops_without_claiming_success() {
  FakeIo io;
  AudioDriver driver(io, 2);
  LMDJ_CHECK(driver.start());
  io.short_write = true;
  std::array<std::int16_t, AudioDriver::frames_per_block * 2> pcm;
  pcm.fill(1);
  LMDJ_CHECK(!driver.write(pcm));
  LMDJ_CHECK(driver.failure() == AudioFailure::short_write);
  LMDJ_CHECK(!driver.running());
  LMDJ_CHECK(driver.released());
}
void invalid_block_must_stop_music() {
  FakeIo io;
  AudioDriver driver(io, 2);
  LMDJ_CHECK(driver.start());
  LMDJ_CHECK(!driver.write({}));
  LMDJ_CHECK(!driver.running());
  LMDJ_CHECK(driver.released());
  LMDJ_CHECK(driver.failure() == AudioFailure::invalid_config);
}

void startup_failure(const char* operation, AudioFailure expected) {
  FakeIo io;
  io.fail_at = operation;
  AudioDriver driver(io, 2);
  LMDJ_CHECK(!driver.start());
  LMDJ_CHECK(driver.failure() == expected);
  LMDJ_CHECK(!driver.running());
  LMDJ_CHECK(driver.released());
  if (expected != AudioFailure::unmute) {
    LMDJ_CHECK(std::find(io.calls.begin(), io.calls.end(), "unmute") == io.calls.end());
  }
  if (expected == AudioFailure::enable) {
    const auto disable = std::find(io.calls.begin(), io.calls.end(), "disable");
    const auto release = std::find(io.calls.begin(), io.calls.end(), "release");
    LMDJ_CHECK(disable != io.calls.end() && disable < release);
  }
  io.fail_at.clear();
  LMDJ_CHECK(driver.start());
  LMDJ_CHECK(driver.failure() == AudioFailure::none);
  LMDJ_CHECK(driver.stop());
}
void mute_failure() { startup_failure("mute", AudioFailure::mute); }
void enable_failure() { startup_failure("enable", AudioFailure::enable); }
void zero_failure() { startup_failure("zero", AudioFailure::write); }
void drain_failure() { startup_failure("drain", AudioFailure::drain); }
void unmute_failure() { startup_failure("unmute", AudioFailure::unmute); }

void release_failure_retains_resources_for_retry() {
  FakeIo io;
  AudioDriver driver(io, 2);
  LMDJ_CHECK(driver.start());
  io.fail_at = "release";
  LMDJ_CHECK(!driver.stop());
  LMDJ_CHECK(!driver.released());
  LMDJ_CHECK(!driver.running());
  LMDJ_CHECK(driver.failure() == AudioFailure::release);
  io.calls.clear();
  io.fail_at.clear();
  LMDJ_CHECK(!driver.stop());
  LMDJ_CHECK(driver.released());
  LMDJ_CHECK(io.calls == (std::vector<std::string>{"mute", "release"}));
}
void pcm_gain_ramps_and_mute_reaches_zero() {
  PcmOutputStage stage;
  std::array<float, 256> left, right;
  std::array<std::int16_t, 512> pcm;
  left.fill(1); right.fill(-1);
  LMDJ_CHECK(stage.convert(left, right, pcm, 10, false));
  for (std::size_t i = 0; i < left.size(); ++i) {
    const auto expected = static_cast<std::int16_t>((static_cast<float>(i + 1) / 256.0F) * 32767.0F);
    LMDJ_CHECK(pcm[2 * i] == expected && pcm[2 * i + 1] == -expected);
  }
  LMDJ_CHECK(stage.convert(left, right, pcm, 10, true));
  for (std::size_t i = 0; i < left.size(); ++i) {
    const auto expected = static_cast<std::int16_t>((1.0F - static_cast<float>(i + 1) / 256.0F) * 32767.0F);
    LMDJ_CHECK(pcm[2 * i] == expected && pcm[2 * i + 1] == -expected);
  }
  LMDJ_CHECK(stage.convert(left, right, pcm, 10, true));
  LMDJ_CHECK(std::all_of(pcm.begin(), pcm.end(), [](auto v) { return v == 0; }));
}

void pcm_nonfinite_rejects_entire_block() {
  PcmOutputStage stage;
  std::array<float, 256> left, right;
  std::array<std::int16_t, 512> pcm;
  left.fill(1); right.fill(1);
  right.back() = std::numeric_limits<float>::quiet_NaN();
  LMDJ_CHECK(!stage.convert(left, right, pcm, 2, false));
  LMDJ_CHECK(std::all_of(pcm.begin(), pcm.end(), [](auto v) { return v == 0; }));
}

struct FakeSession final : AudioSession {
  Render callback{};
  void* context{};
  AudioStopResult stop_result{true, true};
  std::uint8_t start_volume{};
  bool start_muted{};
  bool start(Render fn, void* ctx, std::uint8_t volume, bool muted) noexcept override {
    start_volume = volume; start_muted = muted;
    callback = fn; context = ctx; return true;
  }
  AudioStopResult stop_and_join() noexcept override {
    if (stop_result.quiescent) { callback = nullptr; context = nullptr; }
    return stop_result;
  }
  std::uint8_t output_volume{};
  bool output_muted{};
  unsigned output_updates{};
  void set_output(std::uint8_t volume, bool muted) noexcept override {
    output_volume = volume;
    output_muted = muted;
    ++output_updates;
  }
  bool healthy() const noexcept override { return true; }
  void pump() {
    std::array<float, 256> left{}, right{};
    LMDJ_CHECK(callback != nullptr);
    callback(context, left.data(), right.data(), 256);
  }
};

lmdj::facade::RuntimeConfig host_config() {
  return {{1'048'576, 262'144, 65'536, 64, 1024}, 16'777'216, 65'536, 1, 100, 10'000};
}
lmdj::cooker::EncodedRuntimeContent host_content(bool one_shot = true) {
  using namespace lmdj;
  auto pcm = std::make_shared<const cooker::PcmSample>(
      cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(4096, 16384)});
  cooker::RuntimeSnapshot snapshot{
      foundation::ProjectId{"00000000-0000-4000-8000-000000000001"},
      foundation::PatternId{"00000000-0000-4000-8000-000000000002"},
      1, 120, 1, 960, 3840,
      // ResolvedPlayback stores linear gain, not decibels: unity is 1.0F.
      {{{2, 7}, {}, pcm, {0, 4096, one_shot ? domain::TriggerMode::one_shot : domain::TriggerMode::gate, 1.0F, false}}}, {}};
  auto encoded = cooker::encode_runtime_content(snapshot, host_config().content_limits);
  LMDJ_CHECK(encoded.has_value());
  return std::move(encoded.value());
}

void host_volume_is_bounded_and_forwarded() {
  FakeSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  LMDJ_CHECK(host.read_status().volume == 2);
  for (unsigned i = 0; i < 12; ++i) {
    LMDJ_CHECK(host.handle_key({Key::volume_up, true}) == HostResult::ok);
    const auto expected = std::min(3U + i, 10U);
    LMDJ_CHECK(host.read_status().volume == expected);
    LMDJ_CHECK(audio.output_volume == expected && !audio.output_muted);
  }
  for (unsigned i = 0; i < 12; ++i) {
    LMDJ_CHECK(host.handle_key({Key::volume_down, true}) == HostResult::ok);
    const auto expected = i < 10 ? 9U - i : 0U;
    LMDJ_CHECK(host.read_status().volume == expected);
    LMDJ_CHECK(audio.output_volume == expected && !audio.output_muted);
  }
}

void host_mute_preserves_volume() {
  FakeSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  LMDJ_CHECK(host.handle_key({Key::mute, true}) == HostResult::ok);
  LMDJ_CHECK(host.read_status().muted && host.read_status().volume == 2);
  LMDJ_CHECK(audio.output_muted && audio.output_volume == 2);
  LMDJ_CHECK(host.handle_key({Key::volume_up, true}) == HostResult::ok);
  LMDJ_CHECK(host.read_status().muted && host.read_status().volume == 3);
  LMDJ_CHECK(audio.output_muted && audio.output_volume == 3);
  LMDJ_CHECK(host.handle_key({Key::mute, true}) == HostResult::ok);
  LMDJ_CHECK(!host.read_status().muted && host.read_status().volume == 3);
  LMDJ_CHECK(!audio.output_muted && audio.output_volume == 3);
}

void host_output_key_release_does_not_repeat_action() {
  FakeSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  for (const auto key : {Key::mute, Key::volume_up, Key::volume_down}) {
    LMDJ_CHECK(host.handle_key({key, false}) == HostResult::ok);
    LMDJ_CHECK(host.read_status().volume == 2 && !host.read_status().muted);
    LMDJ_CHECK(audio.output_updates == 0);
  }
}

void host_start_and_restart_receive_current_output_settings() {
  FakeSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  const auto content = host_content();
  LMDJ_CHECK(host.begin_receive() == HostResult::ok);
  LMDJ_CHECK(host.load_received(content.bytes, content.identity) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::volume_up, true}) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::mute, true}) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
  LMDJ_CHECK(audio.callback != nullptr && audio.start_volume == 3 && audio.start_muted);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
  LMDJ_CHECK(audio.callback == nullptr && host.read_status().physical_stopped);
  LMDJ_CHECK(host.handle_key({Key::volume_down, true}) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::mute, true}) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
  LMDJ_CHECK(audio.callback != nullptr && audio.start_volume == 2 && !audio.start_muted);
}

void host_maps_canonical_slot_and_retries_without_sequence_loss() {
  FakeSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  auto content = host_content();
  LMDJ_CHECK(host.begin_receive() == HostResult::ok);
  LMDJ_CHECK(host.load_received(content.bytes, content.identity) == HostResult::ok);
  LMDJ_CHECK(host.read_status().pads[0].bank == 2 && host.read_status().pads[0].pad == 7);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::pad_a, true}) == HostResult::accepted);
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 0);
  LMDJ_CHECK(host.handle_key({Key::pad_a, false}) == HostResult::core_error);
  LMDJ_CHECK(host.read_status().core_result == lmdj::facade::RuntimeResult::queue_full);
  audio.pump();
  host.poll();
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 1);
  LMDJ_CHECK(host.read_status().last_receipt_outcome == lmdj::facade::RuntimeCommandOutcome::voice_started);
  LMDJ_CHECK(host.handle_key({Key::pad_a, false}) == HostResult::accepted);
  audio.pump();
  host.poll();
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 2);
  LMDJ_CHECK(host.shutdown() == HostResult::ok);
  LMDJ_CHECK(audio.callback == nullptr);
}

void host_rejects_unsupported_profile_before_ready() {
  FakeSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  auto content = host_content(false);
  LMDJ_CHECK(host.begin_receive() == HostResult::ok);
  LMDJ_CHECK(host.load_received(content.bytes, content.identity) == HostResult::unsupported_content);
  const auto status = host.read_status();
  LMDJ_CHECK(status.phase == lmdj::facade::RuntimePhase::empty);
  LMDJ_CHECK(status.content_bytes == 0 && status.pad_count == 0 && !status.armed);
  LMDJ_CHECK(audio.callback == nullptr);
}

void host_cannot_arm_until_physical_stop_acknowledged() {
  FakeSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  auto content = host_content();
  LMDJ_CHECK(host.begin_receive() == HostResult::ok);
  LMDJ_CHECK(host.load_received(content.bytes, content.identity) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
  audio.stop_result = {true, false};
  LMDJ_CHECK(host.begin_receive() == HostResult::audio_error);
  LMDJ_CHECK(!host.read_status().armed && !host.read_status().physical_stopped);
  LMDJ_CHECK(host.read_status().phase == lmdj::facade::RuntimePhase::draining);
  audio.stop_result = {true, true};
  LMDJ_CHECK(host.begin_receive() == HostResult::ok);
  LMDJ_CHECK(host.read_status().armed && host.read_status().physical_stopped);
  LMDJ_CHECK(host.read_status().content_bytes == 0);
}

// A real, independent render caller exercises the Host/Facade lifetime seam.
// The simulated device waits between blocks: this is not an I2S deadline test,
// and does not reproduce FreeRTOS deletion, DMA drain or codec side effects.
struct ThreadedSession final : AudioSession {
  std::jthread worker;
  std::mutex mutex;
  std::condition_variable changed;
  std::atomic<bool> fault{};
  std::uint64_t sounding_blocks{}; // Protected by mutex, including observations.
  std::uint32_t joins{}; // Serialized control owner only.

  ~ThreadedSession() override { (void)stop_and_join(); }
  bool start(Render callback, void* context, std::uint8_t, bool) noexcept override {
    if (worker.joinable()) return false;
    fault.store(false);
    try {
      worker = std::jthread([this, callback, context](std::stop_token stop) {
        std::array<float, AudioDriver::frames_per_block> left{}, right{};
        while (!stop.stop_requested() && !fault.load()) {
          callback(context, left.data(), right.data(), AudioDriver::frames_per_block);
          const bool sounding = std::any_of(left.begin(), left.end(), [](float value) { return value != 0; });
          std::unique_lock lock(mutex);
          if (sounding) ++sounding_blocks;
          changed.notify_all();
          changed.wait_for(lock, std::chrono::microseconds(100), [&] {
            return stop.stop_requested() || fault.load();
          });
        }
      });
      return true;
    } catch (...) { return false; }
  }
  AudioStopResult stop_and_join() noexcept override {
    if (worker.joinable()) {
      worker.request_stop();
      changed.notify_all();
      worker.join();
      ++joins;
    }
    return {true, true}; // Simulated sink only, not a physical-silence claim.
  }
  bool healthy() const noexcept override { return !fault.load(); }
  void set_output(std::uint8_t, bool) noexcept override {}
  std::uint64_t sound_count() {
    std::lock_guard lock(mutex);
    return sounding_blocks;
  }
  bool await_sound_after(std::uint64_t previous) {
    std::unique_lock lock(mutex);
    return changed.wait_for(lock, std::chrono::seconds(2), [&] { return sounding_blocks > previous; });
  }
};

void load_and_play(RuntimeHost& host, ThreadedSession& audio,
                   const lmdj::cooker::EncodedRuntimeContent& content) {
  using namespace lmdj::facade;
  LMDJ_CHECK(host.begin_receive() == HostResult::ok);
  const auto empty = host.read_status();
  LMDJ_CHECK(empty.phase == RuntimePhase::empty && empty.armed && empty.physical_stopped);
  LMDJ_CHECK(empty.content_bytes == 0 && empty.pad_count == 0);
  LMDJ_CHECK(empty.content_sha256 == (std::array<char, 64>{}));
  LMDJ_CHECK(host.load_received(content.bytes, content.identity) == HostResult::ok);
  const auto ready = host.read_status();
  LMDJ_CHECK(ready.phase == RuntimePhase::ready && !ready.armed);
  LMDJ_CHECK(ready.content_bytes == content.identity.byte_length);
  LMDJ_CHECK(std::string(ready.content_sha256.begin(), ready.content_sha256.end()) == content.identity.sha256);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
  LMDJ_CHECK(host.read_status().phase == RuntimePhase::running);
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 0);
  const auto previous = audio.sound_count();
  LMDJ_CHECK(host.handle_key({Key::pad_a, true}) == HostResult::accepted);
  LMDJ_CHECK(audio.await_sound_after(previous));
  host.poll();
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 1);
  LMDJ_CHECK(host.read_status().last_receipt_outcome == RuntimeCommandOutcome::voice_started);
}

void threaded_stop_reload_retains_no_old_callback() {
  using namespace lmdj::facade;
  ThreadedSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  const auto content = host_content();
  load_and_play(host, audio, content);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
  LMDJ_CHECK(host.read_status().phase == RuntimePhase::stopped);
  LMDJ_CHECK(host.read_status().physical_stopped);
  LMDJ_CHECK(!audio.worker.joinable() && audio.joins == 1);
  load_and_play(host, audio, content);
  LMDJ_CHECK(host.shutdown() == HostResult::ok);
  LMDJ_CHECK(host.read_status().phase == RuntimePhase::empty);
  LMDJ_CHECK(host.read_status().content_bytes == 0 && host.read_status().pad_count == 0);
  LMDJ_CHECK(!audio.worker.joinable() && audio.joins == 2);
}

void threaded_output_failure_is_joined_before_reload() {
  ThreadedSession audio;
  RuntimeHost host(host_config(), {4}, audio);
  const auto content = host_content();
  load_and_play(host, audio, content);
  audio.fault.store(true);
  audio.changed.notify_all();
  host.poll();
  LMDJ_CHECK(host.read_status().error == HostResult::audio_error);
  LMDJ_CHECK(host.read_status().physical_stopped);
  LMDJ_CHECK(!audio.worker.joinable() && audio.joins == 1);
  load_and_play(host, audio, content);
  LMDJ_CHECK(host.shutdown() == HostResult::ok);
  LMDJ_CHECK(!audio.worker.joinable() && audio.joins == 2);
}

void threaded_destruction_joins_render_before_free() {
  ThreadedSession audio;
  const auto content = host_content();
  {
    RuntimeHost host(host_config(), {4}, audio);
    load_and_play(host, audio, content);
    LMDJ_CHECK(audio.worker.joinable());
  }
  LMDJ_CHECK(!audio.worker.joinable() && audio.joins == 1);
}

void threaded_stop_reload_stress() {
  // Fixed journey count, with condition-variable waits rather than busy spins.
  // Each repetition asserts both sides of stop, unload, reload and shutdown.
  for (unsigned iteration = 0; iteration < 256; ++iteration)
    threaded_stop_reload_retains_no_old_callback();
}
}  // namespace

int main(int argc, char** argv) {
  struct Case { const char* name; void (*run)(); };
  const Case cases[]{
      {"threaded_stop_reload", threaded_stop_reload_retains_no_old_callback},
      {"threaded_output_failure", threaded_output_failure_is_joined_before_reload},
      {"threaded_destruction", threaded_destruction_joins_render_before_free},
      {"threaded_stress", threaded_stop_reload_stress},
      {"explicit_prewarm", explicit_prewarm_is_not_reduced_to_ring_size},
      {"pcm_ramp", pcm_gain_ramps_and_mute_reaches_zero},
      {"pcm_nonfinite", pcm_nonfinite_rejects_entire_block},
      {"host_mapping", host_maps_canonical_slot_and_retries_without_sequence_loss},
      {"host_volume", host_volume_is_bounded_and_forwarded},
      {"host_mute", host_mute_preserves_volume},
      {"host_output_release", host_output_key_release_does_not_repeat_action},
      {"host_start_output", host_start_and_restart_receive_current_output_settings},
      {"host_profile", host_rejects_unsupported_profile_before_ready},
      {"host_physical_stop", host_cannot_arm_until_physical_stop_acknowledged},
      {"invalid_block", invalid_block_must_stop_music},
      {"mute_failure", mute_failure},
      {"enable_failure", enable_failure},
      {"zero_failure", zero_failure},
      {"drain_failure", drain_failure},
      {"unmute_failure", unmute_failure},
      {"release_failure", release_failure_retains_resources_for_retry},
      {"prewarm", prewarm_must_reach_output_before_unmute},
      {"stop", stop_must_drain_before_quiescence_and_release},
      {"quiescence_failure", failed_quiescence_cannot_release_callback_storage},
      {"partial_configuration", partial_configuration_is_cleaned},
      {"short_write", short_music_write_stops_without_claiming_success}};
  bool selected = false;
  for (const auto& item : cases) {
    if (argc == 1 || (argc == 2 && std::string(argv[1]) == item.name)) {
      selected = true;
      item.run();
    }
  }
  LMDJ_CHECK(selected);
}
