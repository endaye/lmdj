#include "audio_driver.hpp"

#include <algorithm>
#include <cmath>

namespace lmdj::cardputer {

bool PcmOutputStage::convert(std::span<const float> left, std::span<const float> right,
                              std::span<std::int16_t> stereo, std::uint8_t volume,
                              bool muted) noexcept {
  const auto reject = [&]() {
    std::fill(stereo.begin(), stereo.end(), 0);
    reset();
    return false;
  };
  if (left.size() != AudioDriver::frames_per_block || right.size() != left.size() ||
      stereo.size() != 2 * left.size() || volume > 10) return reject();
  const float target = muted ? 0.0F : static_cast<float>(volume) / 10.0F;
  const float initial = gain_;
  for (std::size_t frame = 0; frame < left.size(); ++frame) {
    if (!std::isfinite(left[frame]) || !std::isfinite(right[frame])) return reject();
    const float mix = static_cast<float>(frame + 1) / static_cast<float>(left.size());
    const float gain = std::clamp(initial + (target - initial) * mix, 0.0F, 1.0F);
    stereo[2 * frame] = static_cast<std::int16_t>(std::clamp(left[frame] * gain, -1.0F, 1.0F) * 32767.0F);
    stereo[2 * frame + 1] = static_cast<std::int16_t>(std::clamp(right[frame] * gain, -1.0F, 1.0F) * 32767.0F);
  }
  gain_ = target;
  return true;
}

bool AudioDriver::fail(AudioFailure failure) noexcept {
  // Preserve the causal failure even if subsequent cleanup also fails.
  if (failure_ == AudioFailure::none) failure_ = failure;
  return false;
}

bool AudioDriver::submit(std::span<const std::int16_t> stereo) noexcept {
  std::size_t accepted = 0;
  if (!io_.write(stereo, accepted)) return fail(AudioFailure::write);
  if (accepted != stereo.size()) return fail(AudioFailure::short_write);
  return true;
}

bool AudioDriver::silence_tail() noexcept {
  for (std::uint32_t block = 0; block < dma_blocks_; ++block) {
    if (!submit(silence_)) return false;
  }
  if (!io_.drain()) return fail(AudioFailure::drain);
  return true;
}

bool AudioDriver::start() noexcept {
  if (configured_) return fail(AudioFailure::wrong_state);
  failure_ = AudioFailure::none;
  if (dma_blocks_ == 0 || prewarm_blocks_ < dma_blocks_) return fail(AudioFailure::invalid_config);
  physical_stopped_ = false;
  configured_ = true;  // configure can allocate only part of the resources.
  if (!io_.configure()) {
    fail(AudioFailure::configure);
  } else if (!io_.mute(true)) {
    fail(AudioFailure::mute);
  } else {
    enable_attempted_ = true;
    if (!io_.enable()) {
      fail(AudioFailure::enable);
    } else {
      enabled_ = true;
      bool warm = true;
      for (std::uint32_t block = dma_blocks_; block < prewarm_blocks_; ++block) {
        if (!submit(silence_)) { warm = false; break; }
      }
      if (warm && silence_tail()) {
        if (!io_.mute(false)) fail(AudioFailure::unmute);
        else { running_ = true; return true; }
      }
    }
  }
  (void)stop();
  return false;
}

bool AudioDriver::write(std::span<const std::int16_t> stereo) noexcept {
  if (!running_) return fail(AudioFailure::wrong_state);
  if (stereo.size() != silence_.size()) {
    fail(AudioFailure::invalid_config);
    (void)stop();
    return false;
  }
  if (submit(stereo)) return true;
  // No more music after a failed or partial write; the owner must also stop
  // the Facade. Quiescence failures retain the platform handles for retry.
  (void)stop();
  return false;
}

bool AudioDriver::stop() noexcept {
  running_ = false;
  if (!configured_) return failure_ == AudioFailure::none;
  bool clean = true;
  if (!io_.mute(true)) { fail(AudioFailure::mute); clean = false; }
  if (enabled_ && !silence_tail()) clean = false;
  if (enable_attempted_) {
    if (!io_.disable_and_quiesce()) return fail(AudioFailure::disable);
    enabled_ = false;
    enable_attempted_ = false;
  }
  if (!io_.release()) return fail(AudioFailure::release);
  configured_ = false;
  physical_stopped_ = clean;
  return clean && failure_ == AudioFailure::none;
}

}  // namespace lmdj::cardputer

#ifdef ESP_PLATFORM
#include <atomic>
#include <cstring>
#include <exception>
#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "esp_attr.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

namespace lmdj::cardputer {
struct EspAudioIo::Impl {
  explicit Impl(EspAudioConfig supplied) : config(supplied) {}
  struct Eof { void* buffer; std::uint32_t sequence; std::uint32_t committed; int core; std::uint64_t time_us; };
  EspAudioConfig config;
  i2c_master_bus_handle_t bus{};
  i2c_master_dev_handle_t codec{};
  i2s_chan_handle_t tx{};
  QueueHandle_t queue{};
  std::array<std::atomic<std::uint32_t>, 8> committed{};
  std::array<void*, 8> buffers{};
  std::atomic<std::uint32_t> sequence{};
  std::atomic<bool> fault{};
  std::uint32_t observed{}, submitted{}, completed{};
  Eof reserved{};
  bool writable{}, enabled{}, callbacks{};
  static_assert(std::atomic<std::uint32_t>::is_always_lock_free);
  static_assert(std::atomic<bool>::is_always_lock_free);

  bool owner() const noexcept { return xPortGetCoreID() == config.audio_core; }
  bool reservation_current() noexcept {
    // At EOF k the next descriptor starts transmitting. Our completed slot
    // starts again at EOF k + dma_blocks - 1, not at its own next EOF. Check
    // around the copy: matching bytes/generation alone can accept a copy into
    // an already transmitting buffer. This observes delivered callbacks, not
    // hardware progress while an interrupt is masked; it is no analogue proof.
    if (fault.load() || sequence.load() - reserved.sequence >= config.dma_blocks - 1) {
      fault.store(true);
      return false;
    }
    return true;
  }
  bool reg(std::uint8_t address, std::uint8_t value) noexcept {
    if (!codec) return false;
    const std::uint8_t bytes[]{address, value};
    std::uint8_t actual{};
    return i2c_master_transmit(codec, bytes, 2, 100) == ESP_OK &&
        i2c_master_transmit_receive(codec, &address, 1, &actual, 1, 100) == ESP_OK && actual == value;
  }
  static bool IRAM_ATTR sent(i2s_chan_handle_t, i2s_event_data_t* data, void* context) {
    auto& self = *static_cast<Impl*>(context);
    const auto serial = self.sequence.fetch_add(1, std::memory_order_relaxed) + 1;
    if (serial == 0) { self.fault.store(true, std::memory_order_relaxed); return false; }
    const Eof event{data->dma_buf, serial,
        self.committed[(serial - 1) % self.config.dma_blocks].load(std::memory_order_acquire),
        xPortGetCoreID(), static_cast<std::uint64_t>(esp_timer_get_time())};
    BaseType_t wake = pdFALSE;
    if (data->size != AudioDriver::frames_per_block * 4 ||
        xQueueSendFromISR(self.queue, &event, &wake) != pdTRUE)
      self.fault.store(true, std::memory_order_relaxed);
    return wake == pdTRUE;
  }
  static bool IRAM_ATTR overflow(i2s_chan_handle_t, i2s_event_data_t*, void* context) {
    static_cast<Impl*>(context)->fault.store(true, std::memory_order_relaxed);
    return false;
  }
};

EspAudioIo::EspAudioIo(EspAudioConfig config) : impl_(std::make_unique<Impl>(config)) {}
EspAudioIo::~EspAudioIo() {
  // Resource destruction is owned by the same pinned worker that allocated IRQs.
  if (impl_->tx || impl_->codec || impl_->bus || impl_->queue) std::terminate();
}

bool EspAudioIo::configure() noexcept {
  auto& s = *impl_;
  if (!s.owner() || s.tx || s.bus || s.queue || s.config.dma_blocks < 2 ||
      s.config.dma_blocks > s.committed.size()) return false;
  s.fault.store(false); s.sequence.store(0);
  s.observed = s.submitted = s.completed = 0;
  s.buffers = {}; s.writable = false;
  for (auto& value : s.committed) value.store(0);
  s.queue = xQueueCreate(s.config.dma_blocks, sizeof(Impl::Eof));
  if (!s.queue) return false;
  if (s.config.shared_bus) {
    s.bus = s.config.shared_bus;
  } else {
    i2c_master_bus_config_t bus{};
    bus.i2c_port = I2C_NUM_0;
    bus.sda_io_num = static_cast<gpio_num_t>(s.config.sda);
    bus.scl_io_num = static_cast<gpio_num_t>(s.config.scl);
    bus.clk_source = I2C_CLK_SRC_DEFAULT;
    bus.glitch_ignore_cnt = 7;
    bus.flags.enable_internal_pullup = true;
    if (i2c_new_master_bus(&bus, &s.bus) != ESP_OK) return false;
  }
  i2c_device_config_t codec{};
  codec.dev_addr_length = I2C_ADDR_BIT_LEN_7;
  codec.device_address = s.config.codec_address;
  codec.scl_speed_hz = 100000;
  if (i2c_master_bus_add_device(s.bus, &codec, &s.codec) != ESP_OK) return false;
  const std::uint8_t reset[]{0x00, 0x80};
  if (i2c_master_transmit(s.codec, reset, 2, 100) != ESP_OK) return false;
  vTaskDelay(pdMS_TO_TICKS(20));
  // ES8311 BCLK-derived clock, 48 kHz / 16-bit stereo input. Board pins and
  // analogue output level are supplied by Assembly/research configuration.
  constexpr std::uint8_t registers[][2]{{0x01,0xB5},{0x02,0x18},{0x0D,0x01},
      {0x12,0x02},{0x13,0x10},{0x32,0},{0x37,0x08},{0x09,0x0C}};
  for (const auto& pair : registers) if (!s.reg(pair[0], pair[1])) return false;
  if (!mute(true)) return false;
  i2s_chan_config_t channel = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  channel.dma_desc_num = s.config.dma_blocks;
  channel.dma_frame_num = AudioDriver::frames_per_block;
  channel.auto_clear_after_cb = true;
  if (i2s_new_channel(&channel, &s.tx, nullptr) != ESP_OK) return false;
  i2s_std_config_t mode{};
  mode.clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(48000);
  mode.slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO);
  mode.gpio_cfg.mclk = I2S_GPIO_UNUSED;
  mode.gpio_cfg.bclk = static_cast<gpio_num_t>(s.config.bclk);
  mode.gpio_cfg.ws = static_cast<gpio_num_t>(s.config.word_select);
  mode.gpio_cfg.dout = static_cast<gpio_num_t>(s.config.data_out);
  mode.gpio_cfg.din = I2S_GPIO_UNUSED;
  if (i2s_channel_init_std_mode(s.tx, &mode) != ESP_OK) return false;
  i2s_chan_info_t info{};
  if (i2s_channel_get_info(s.tx, &info) != ESP_OK ||
      info.total_dma_buf_size != s.config.dma_blocks * AudioDriver::frames_per_block * 4) return false;
  i2s_event_callbacks_t events{};
  events.on_sent = Impl::sent; events.on_send_q_ovf = Impl::overflow;
  if (i2s_channel_register_event_callback(s.tx, &events, &s) != ESP_OK) return false;
  s.callbacks = true;
  return true;
}

bool EspAudioIo::mute(bool value) noexcept {
  auto& s = *impl_;
  if (!s.owner()) return false;
  if (value) {
    const bool muted = s.reg(0x31, 0x60);
    const bool minimum = s.reg(0x32, 0);
    return muted && minimum;
  }
  // Startup calls this only after the silent DMA prewarm has reached output.
  // Keep the DAC powered down until its BCLK-derived clock is established.
  return s.reg(0x12, 0) && s.reg(0x32, s.config.codec_volume) && s.reg(0x31, 0);
}

bool EspAudioIo::enable() noexcept {
  auto& s = *impl_;
  if (!s.owner() || !s.tx || s.enabled) return false;
  s.enabled = i2s_channel_enable(s.tx) == ESP_OK;
  return s.enabled;
}

bool EspAudioIo::wait_writable() noexcept {
  auto& s = *impl_;
  if (!s.owner() || !s.enabled || s.fault.load()) return false;
  if (s.writable) return true;
  Impl::Eof event{};
  if (xQueueReceive(s.queue, &event, pdMS_TO_TICKS(30)) != pdTRUE) return false;
  if (event.sequence != s.observed + 1 || event.core != s.config.audio_core ||
      uxQueueMessagesWaiting(s.queue) != 0 || s.fault.load()) return false;
  const auto slot = (event.sequence - 1) % s.config.dma_blocks;
  if (event.sequence <= s.config.dma_blocks) s.buffers[slot] = event.buffer;
  else if (s.buffers[slot] != event.buffer || event.committed != event.sequence - s.config.dma_blocks) return false;
  s.observed = event.sequence;
  s.completed = event.committed;
  s.reserved = event;
  s.writable = true;
  return true;
}

std::uint64_t EspAudioIo::reserved_eof_us() const noexcept {
  return impl_->reserved.time_us;
}

bool EspAudioIo::write(std::span<const std::int16_t> pcm, std::size_t& accepted) noexcept {
  accepted = 0;
  auto& s = *impl_;
  if (pcm.size() != AudioDriver::frames_per_block * 2 || !wait_writable()) return false;
  if (!s.reservation_current()) { s.writable = false; return false; }
  std::size_t bytes{};
  const auto result = i2s_channel_write(s.tx, pcm.data(), pcm.size_bytes(), &bytes, 0);
  accepted = bytes / sizeof(std::int16_t);
  s.writable = false;
  if (result != ESP_OK || bytes != pcm.size_bytes() ||
      std::memcmp(s.reserved.buffer, pcm.data(), pcm.size_bytes()) != 0 ||
      !s.reservation_current()) return false;
  s.submitted = s.reserved.sequence;
  s.committed[(s.submitted - 1) % s.config.dma_blocks].store(s.submitted, std::memory_order_release);
  return true;
}

bool EspAudioIo::drain() noexcept {
  auto& s = *impl_;
  const auto target = s.submitted;
  std::array<std::int16_t, AudioDriver::frames_per_block * 2> zeros{};
  // Keep servicing each freed descriptor while waiting for the fixed last
  // submitted generation to reappear as transmitted in the callback receipt.
  while (s.completed < target) {
    if (!wait_writable()) return false;
    std::size_t accepted{};
    if (!write(zeros, accepted) || accepted != zeros.size()) return false;
  }
  return true;
}

bool EspAudioIo::disable_and_quiesce() noexcept {
  auto& s = *impl_;
  if (!s.owner()) return false;
  if (s.enabled) {
    if (i2s_channel_disable(s.tx) != ESP_OK) return false;
    s.enabled = false;
  }
  if (s.callbacks) {
    const i2s_event_callbacks_t none{};
    // Same pinned core as IRQ allocation: no user callback runs concurrently
    // with this task. Detach after stop, before freeing its queue or context.
    if (i2s_channel_register_event_callback(s.tx, &none, nullptr) != ESP_OK) return false;
    s.callbacks = false;
  }
  s.writable = false;
  return true;
}

bool EspAudioIo::release() noexcept {
  auto& s = *impl_;
  if (!s.owner() || s.enabled) return false;
  if (s.callbacks && !disable_and_quiesce()) return false;
  if (s.tx) { if (i2s_del_channel(s.tx) != ESP_OK) return false; s.tx = nullptr; }
  if (s.codec) { if (i2c_master_bus_rm_device(s.codec) != ESP_OK) return false; s.codec = nullptr; }
  if (s.bus) {
    if (!s.config.shared_bus && i2c_del_master_bus(s.bus) != ESP_OK) return false;
    s.bus = nullptr;
  }
  if (s.queue) { vQueueDelete(s.queue); s.queue = nullptr; }
  return true;
}
}  // namespace lmdj::cardputer
#endif
