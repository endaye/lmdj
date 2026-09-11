#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <memory>

namespace lmdj::cardputer {

// This entire interface, including destruction, has one audio-task owner.
// The Host must finish Core drain before stop(), and join that owner before
// reclaiming the Driver/Facade. No control-thread call may race these methods.
// Device pins and codec settings belong to the injected platform implementation.
class AudioIo {
 public:
  virtual ~AudioIo() = default;
  virtual bool configure() noexcept = 0;
  virtual bool mute(bool value) noexcept = 0;
  virtual bool enable() noexcept = 0;
  // Successful submission is not evidence of transmission. Report the actual
  // number of accepted samples, including short writes on a driver error.
  virtual bool write(std::span<const std::int16_t> stereo,
                     std::size_t& accepted) noexcept = 0;
  // Confirm every preceding submitted sample reached the DMA output boundary;
  // a queue-empty observation or write() return is not a drain acknowledgement.
  virtual bool drain() noexcept = 0;
  // Success means no further DMA callbacks can access Driver-owned storage.
  // Also handles a partially failed enable, without assuming it stayed disabled.
  virtual bool disable_and_quiesce() noexcept = 0;
  // Must clean partial configuration. Only called after confirmed quiescence
  // if enable was attempted. Failed release retains resources for retry.
  virtual bool release() noexcept = 0;
};

enum class AudioFailure : std::uint8_t {
  none, wrong_state, invalid_config, configure, mute, enable, write,
  short_write, drain, unmute, disable, release,
};

// Audio-owner-only output settings. A change reaches its target over one
// 256-frame block (5.333 ms at 48 kHz), independently of Project/sample gain.
class PcmOutputStage final {
 public:
  bool convert(std::span<const float> left, std::span<const float> right,
               std::span<std::int16_t> stereo, std::uint8_t volume,
               bool muted) noexcept;
  void reset() noexcept { gain_ = 0.0F; }
 private:
  float gain_{};
};

class AudioDriver final {
 public:
  static constexpr std::size_t frames_per_block = 256;
  explicit AudioDriver(AudioIo& io, std::uint32_t dma_blocks,
                       std::uint32_t prewarm_blocks = 0) noexcept
      : io_(io), dma_blocks_(dma_blocks),
        prewarm_blocks_(prewarm_blocks == 0 ? dma_blocks : prewarm_blocks) {}
  AudioDriver(const AudioDriver&) = delete;
  AudioDriver& operator=(const AudioDriver&) = delete;

  bool start() noexcept;
  bool write(std::span<const std::int16_t> stereo) noexcept;
  bool stop() noexcept;
  bool running() const noexcept { return running_; }
  bool released() const noexcept { return !configured_; }
  bool physical_stopped() const noexcept { return physical_stopped_; }
  AudioFailure failure() const noexcept { return failure_; }

 private:
  bool submit(std::span<const std::int16_t> stereo) noexcept;
  bool silence_tail() noexcept;
  bool fail(AudioFailure failure) noexcept;
  AudioIo& io_;
  const std::uint32_t dma_blocks_;
  const std::uint32_t prewarm_blocks_;
  std::array<std::int16_t, frames_per_block * 2> silence_{};
  bool configured_{};
  bool enable_attempted_{};
  bool enabled_{};
  bool running_{};
  bool physical_stopped_{true};
  AudioFailure failure_{};
};

#ifdef ESP_PLATFORM
struct EspAudioConfig {
  int sda{}, scl{}, bclk{}, word_select{}, data_out{};
  std::uint8_t codec_address{};
  std::uint8_t codec_volume{};
  std::uint32_t dma_blocks{};
  int audio_core{};
};

class EspAudioIo final : public AudioIo {
 public:
  explicit EspAudioIo(EspAudioConfig config);
  ~EspAudioIo() override;
  bool configure() noexcept override;
  bool mute(bool value) noexcept override;
  bool enable() noexcept override;
  bool write(std::span<const std::int16_t>, std::size_t&) noexcept override;
  bool drain() noexcept override;
  bool disable_and_quiesce() noexcept override;
  bool release() noexcept override;
  // Reserve the next completed DMA buffer before rendering, separating DMA
  // pacing wait from render/convert/submit CPU work. write consumes it.
  bool wait_writable() noexcept;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
#endif

}  // namespace lmdj::cardputer
