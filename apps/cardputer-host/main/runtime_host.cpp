#include "runtime_host.hpp"

#include <algorithm>
#include <exception>
#include <limits>

namespace lmdj::cardputer {
using facade::RuntimePhase;
using facade::RuntimeResult;

RuntimeHost::RuntimeHost(facade::RuntimeConfig config, HostProfile profile,
                         AudioSession& audio)
    : runtime_(config), profile_(profile), audio_(audio),
      pending_pad_commands_(config.maximum_pending_commands, 0xff) {}

RuntimeHost::~RuntimeHost() {
  (void)shutdown();
  // A failed join is not permission to free a live callback's context.
  if (audio_owned_) std::terminate();
}

HostResult RuntimeHost::fail(HostResult error) noexcept {
  status_.error = error;
  return error;
}

void RuntimeHost::render(void* context, float* left, float* right,
                         std::uint32_t frames) noexcept {
  static_cast<RuntimeHost*>(context)->runtime_.render(left, right, frames);
}

void RuntimeHost::collect_receipts() noexcept {
  std::array<facade::RuntimeReceipt, 16> receipts;
  std::size_t count;
  do {
    count = runtime_.poll(receipts);
    for (std::size_t i = 0; i < count; ++i) {
      if (receipts[i].epoch != epoch_) continue;
      status_.last_receipt_sequence = receipts[i].sequence;
      status_.last_receipt_outcome = receipts[i].outcome;
      // poll returns accepted commands in sequence order and returns their
      // credits. The same serialized owner records each submit before it can
      // poll, so even a receipt published during submit retains its metadata.
      auto& command = pending_pad_commands_[receipts[i].sequence % pending_pad_commands_.size()];
      if (command != 0xff) {
        status_.pad_active[command & 3U] = (command & 4U) != 0 &&
            receipts[i].outcome == facade::RuntimeCommandOutcome::voice_started;
        command = 0xff;
      }
    }
  } while (count == receipts.size());
}

void RuntimeHost::poll() noexcept {
  collect_receipts();
  if (audio_owned_ && !audio_.healthy()) {
    (void)stop();
    (void)fail(HostResult::audio_error);
  }
}

HostResult RuntimeHost::start() noexcept {
  if (audio_owned_ || status_.armed) return fail(HostResult::wrong_state);
  status_.core_result = runtime_.start(epoch_);
  if (status_.core_result != RuntimeResult::ok) return fail(HostResult::core_error);
  sequence_ = 0;
  std::fill(pending_pad_commands_.begin(), pending_pad_commands_.end(), 0xff);
  status_.pad_active = {};
  status_.last_receipt_sequence = 0;
  status_.last_receipt_outcome = {};
  audio_owned_ = true; // Including partial start failure, until joined.
  status_.physical_stopped = false;
  if (!audio_.start(render, this, status_.volume, status_.muted)) {
    (void)stop();
    return fail(HostResult::audio_error);
  }
  status_.phase = RuntimePhase::running;
  status_.error = HostResult::ok;
  return HostResult::ok;
}

HostResult RuntimeHost::stop() noexcept {
  runtime_.stop();
  collect_receipts();
  std::fill(pending_pad_commands_.begin(), pending_pad_commands_.end(), 0xff);
  status_.pad_active = {};
  if (audio_owned_ || !status_.physical_stopped) {
    status_.phase = RuntimePhase::draining;
    const auto result = audio_.stop_and_join();
    audio_owned_ = !result.quiescent;
    status_.physical_stopped = result.quiescent && result.silent;
    if (!status_.physical_stopped) return fail(HostResult::audio_error);
  }
  if (!status_.physical_stopped) return fail(HostResult::audio_error);
  status_.phase = runtime_.phase();
  return HostResult::ok;
}

void RuntimeHost::clear_content() noexcept {
  std::fill(pending_pad_commands_.begin(), pending_pad_commands_.end(), 0xff);
  status_.pad_active = {};
  status_.pads = {};
  status_.pad_count = 0;
  status_.content_sha256 = {};
  status_.content_bytes = 0;
  status_.phase = RuntimePhase::empty;
  status_.last_receipt_sequence = 0;
  status_.last_receipt_outcome = {};
}

HostResult RuntimeHost::shutdown() noexcept {
  status_.armed = false;
  const auto result = stop();
  if (audio_owned_) return result;
  status_.core_result = runtime_.unload();
  clear_content();
  return result;
}

HostResult RuntimeHost::begin_receive() noexcept {
  status_.armed = false;
  if (stop() != HostResult::ok) return HostResult::audio_error;
  status_.core_result = runtime_.unload();
  if (status_.core_result != RuntimeResult::ok) return fail(HostResult::core_error);
  clear_content();
  status_.armed = true;
  status_.error = HostResult::ok;
  return HostResult::ok;
}

HostResult RuntimeHost::cancel_receive() noexcept {
  // C1 owns and discards its receive buffer; cancelling never unloads already
  // committed content and never turns a USB disconnect into stop().
  status_.armed = false;
  return HostResult::ok;
}

HostResult RuntimeHost::load_received(std::span<const std::byte> bytes,
                                     const facade::RuntimeContentIdentity& identity) noexcept {
  if (!status_.armed || runtime_.phase() != RuntimePhase::empty)
    return fail(HostResult::wrong_state);
  status_.armed = false;
  if (profile_.maximum_pads == 0 || profile_.maximum_pads > status_.pads.size())
    return fail(HostResult::unsupported_content);
  status_.core_result = runtime_.load(bytes, identity);
  if (status_.core_result != RuntimeResult::ok) return fail(HostResult::core_error);
  const auto summary = runtime_.content_summary();
  bool supported = summary.count > 0 && summary.count <= profile_.maximum_pads;
  for (std::size_t i = 0; i < summary.count; ++i)
    supported = supported && summary.pads[i].trigger_mode == facade::RuntimeTriggerMode::one_shot;
  if (!supported) {
    (void)runtime_.unload();
    clear_content();
    return fail(HostResult::unsupported_content);
  }
  try {
    const auto published = runtime_.content_identity();
    if (!published || published->sha256.size() != status_.content_sha256.size()) {
      (void)runtime_.unload();
      clear_content();
      return fail(HostResult::core_error);
    }
    std::copy(published->sha256.begin(), published->sha256.end(), status_.content_sha256.begin());
    status_.content_bytes = published->byte_length;
  } catch (...) {
    (void)runtime_.unload();
    clear_content();
    status_.core_result = RuntimeResult::allocation_failed;
    return fail(HostResult::core_error);
  }
  status_.pad_count = summary.count;
  std::copy_n(summary.pads.begin(), summary.count, status_.pads.begin());
  status_.phase = RuntimePhase::ready; // Never expose pre-profile Core ready.
  status_.error = HostResult::ok;
  return HostResult::ok;
}

HostResult RuntimeHost::handle_key(KeyEvent event) noexcept {
  poll();
  if (event.key == Key::overflow) {
    (void)stop();
    return fail(HostResult::input_overflow);
  }
  const auto key = static_cast<std::uint8_t>(event.key);
  if (key <= static_cast<std::uint8_t>(Key::pad_f)) {
    if (status_.phase != RuntimePhase::running || key >= status_.pad_count)
      return fail(HostResult::wrong_state);
    if (sequence_ == std::numeric_limits<std::uint32_t>::max()) {
      status_.core_result = RuntimeResult::sequence_exhausted;
      return fail(HostResult::core_error);
    }
    const auto pad = status_.pads[key];
    status_.core_result = runtime_.submit({epoch_, sequence_ + 1,
        event.pressed ? facade::RuntimeCommandKind::press : facade::RuntimeCommandKind::release,
        static_cast<std::uint8_t>(pad.bank * 16 + pad.pad), 127});
    if (status_.core_result != RuntimeResult::accepted) return fail(HostResult::core_error);
    ++sequence_; // queue_full does not consume this counter.
    pending_pad_commands_[sequence_ % pending_pad_commands_.size()] =
        static_cast<std::uint8_t>(key | (event.pressed ? 4U : 0U));
    return HostResult::accepted;
  }
  if (!event.pressed) return HostResult::ok;
  switch (event.key) {
    case Key::play_stop: return status_.phase == RuntimePhase::running ? stop() : start();
    case Key::confirm_receive: return begin_receive();
    case Key::cancel_receive: return cancel_receive();
    case Key::mute: status_.muted = !status_.muted; break;
    case Key::volume_up: if (status_.volume < 10) ++status_.volume; break;
    case Key::volume_down: if (status_.volume > 0) --status_.volume; break;
    default: return fail(HostResult::wrong_state);
  }
  audio_.set_output(status_.volume, status_.muted);
  return HostResult::ok;
}

#ifdef ESP_PLATFORM
void RuntimeHost::read_resources(ResourceObservation& result) const noexcept {
  result = capture_control_resources();
  result.audio_task_stack_high_water_bytes = audio_.stopped_stack_high_water_bytes();
}
#endif

}  // namespace lmdj::cardputer

#ifdef ESP_PLATFORM
#include <atomic>
#include "resource_observation.hpp"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace lmdj::cardputer {
struct EspAudioSession::Impl {
  enum class Phase : std::uint32_t { idle, booting, running, finished };
  explicit Impl(EspAudioSessionConfig supplied)
      : config(supplied), io(supplied.io),
        driver(io, supplied.io.dma_blocks, supplied.prewarm_blocks) {}
  EspAudioSessionConfig config;
  EspAudioIo io;
  AudioDriver driver;
  PcmOutputStage output;
  AudioDiagnostics diagnostics;
  std::array<float, AudioDriver::frames_per_block> left{}, right{};
  std::array<std::int16_t, AudioDriver::frames_per_block * 2> pcm{};
  Render render{};
  void* context{};
  std::atomic<Phase> phase{Phase::idle};
  std::atomic<bool> stop_requested{}, retry_cleanup{}, failed{};
  std::atomic<std::uint32_t> settings{};
  bool silent{}; // Written before finished release; read after acquire only.
  std::optional<std::size_t> stack_high_water_bytes;
  static_assert(std::atomic<Phase>::is_always_lock_free);

  static void worker(void* argument) {
    auto& s = *static_cast<Impl*>(argument);
    (void)s.phase.load(std::memory_order_acquire); // Published callback/config.
    s.output.reset();
    if (!s.driver.start()) s.failed.store(true, std::memory_order_release);
    else {
      s.phase.store(Phase::running, std::memory_order_release);
      while (!s.stop_requested.load(std::memory_order_acquire)) {
        const auto clock = [] { return static_cast<std::uint64_t>(esp_timer_get_time()); };
        const auto trace = service_audio_block(clock,
            [&] { return s.io.wait_writable(); },
            [&] { return s.stop_requested.load(std::memory_order_acquire); },
            [&] { return s.io.reserved_eof_us(); },
            [&] { s.render(s.context, s.left.data(), s.right.data(), AudioDriver::frames_per_block); },
            [&] {
              const auto settings = s.settings.load(std::memory_order_acquire);
              return s.output.convert(s.left, s.right, s.pcm,
                  static_cast<std::uint8_t>(settings & 0xff), (settings & 0x100) != 0);
            }, [&] { return s.driver.write(s.pcm); });
        const auto recording_begin = clock();
        s.diagnostics.record(trace);
        const auto recording_end = clock();
        s.diagnostics.record_overhead(recording_begin, recording_end);
        if (trace.result == AudioBlockResult::stopped) break;
        if (trace.result != AudioBlockResult::submitted) {
          s.failed.store(true, std::memory_order_release);
          break;
        }
      }
    }
    for (;;) {
      (void)s.driver.stop();
      if (s.driver.released()) break;
      s.failed.store(true, std::memory_order_release);
      // Retain live IRQ/DMA resources. Only an explicit control-side join
      // attempt requests another cleanup; no destruction or silent retry loop.
      while (!s.retry_cleanup.exchange(false, std::memory_order_acq_rel)) vTaskDelay(1);
    }
    s.silent = s.driver.physical_stopped();
    if (!s.silent) s.failed.store(true, std::memory_order_release);
    s.stack_high_water_bytes = current_task_stack_high_water_bytes();
    s.phase.store(Phase::finished, std::memory_order_release);
    // Last access to s above. The control owner may now reclaim callback state;
    // the FreeRTOS idle task separately reclaims this task's private stack.
    vTaskDelete(nullptr);
  }

  bool wait(bool starting) const noexcept {
    const auto begin = xTaskGetTickCount();
    const auto limit = pdMS_TO_TICKS(config.handshake_timeout_ms);
    for (;;) {
      const auto current = phase.load(std::memory_order_acquire);
      if (current == Phase::finished || (starting && current == Phase::running)) return true;
      if (xTaskGetTickCount() - begin >= limit) return false;
      vTaskDelay(1);
    }
  }
};

EspAudioSession::EspAudioSession(EspAudioSessionConfig config)
    : impl_(std::make_unique<Impl>(config)) {}

EspAudioSession::~EspAudioSession() {
  if (!stop_and_join().quiescent) std::terminate();
}

bool EspAudioSession::start(Render render, void* context, std::uint8_t volume,
                             bool muted) noexcept {
  auto& s = *impl_;
  const auto previous = s.phase.load(std::memory_order_acquire);
  if (previous != Impl::Phase::idle && previous != Impl::Phase::finished) return false;
  if (!render || !context || volume > 10 || s.config.stack_bytes == 0 ||
      s.config.priority == 0 || s.config.priority >= configMAX_PRIORITIES ||
      s.config.io.audio_core < 0 || s.config.io.audio_core >= portNUM_PROCESSORS ||
      s.config.prewarm_blocks < s.config.io.dma_blocks ||
      pdMS_TO_TICKS(s.config.handshake_timeout_ms) == 0) return false;
  s.render = render; s.context = context;
  s.diagnostics.reset();
  s.stack_high_water_bytes.reset();
  s.stop_requested.store(false); s.retry_cleanup.store(false); s.failed.store(false);
  s.silent = false;
  set_output(volume, muted);
  s.phase.store(Impl::Phase::booting, std::memory_order_release);
  if (xTaskCreatePinnedToCore(Impl::worker, "lmdj-audio", s.config.stack_bytes,
          &s, s.config.priority, nullptr, s.config.io.audio_core) != pdPASS) {
    s.silent = true;
    s.failed.store(true);
    s.phase.store(Impl::Phase::finished, std::memory_order_release);
    return false;
  }
  if (!s.wait(true)) {
    s.failed.store(true);
    s.stop_requested.store(true, std::memory_order_release);
    return false;
  }
  return s.phase.load(std::memory_order_acquire) == Impl::Phase::running && !s.failed.load();
}

AudioStopResult EspAudioSession::stop_and_join() noexcept {
  auto& s = *impl_;
  if (s.phase.load(std::memory_order_acquire) == Impl::Phase::idle) return {true, true};
  s.stop_requested.store(true, std::memory_order_release);
  s.retry_cleanup.store(true, std::memory_order_release);
  if (!s.wait(false)) return {false, false};
  return {true, s.silent};
}

void EspAudioSession::set_output(std::uint8_t volume, bool muted) noexcept {
  impl_->settings.store(static_cast<std::uint32_t>(volume) | (muted ? 0x100U : 0U),
                         std::memory_order_release);
}

bool EspAudioSession::healthy() const noexcept {
  return !impl_->failed.load(std::memory_order_acquire);
}

bool EspAudioSession::read_diagnostics(AudioDiagnosticsSnapshot& result) const noexcept {
  result = {};
  if (impl_->phase.load(std::memory_order_acquire) != Impl::Phase::finished) return false;
  result = impl_->diagnostics.snapshot();
  return true;
}

std::optional<std::size_t> EspAudioSession::stopped_stack_high_water_bytes() const noexcept {
  if (impl_->phase.load(std::memory_order_acquire) != Impl::Phase::finished) return std::nullopt;
  return impl_->stack_high_water_bytes;
}
}  // namespace lmdj::cardputer
#endif
