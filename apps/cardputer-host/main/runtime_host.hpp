#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <vector>
#include <lmdj/facade/runtime_facade.hpp>
#ifdef ESP_PLATFORM
#include "audio_driver.hpp"
#include "audio_diagnostics.hpp"
#include "resource_observation.hpp"
#endif

namespace lmdj::cardputer {

struct AudioStopResult {
  bool quiescent{};
  bool silent{};
};

// Control-side adapter to the dedicated audio task. start never invokes Core
// control methods; it admits only one render caller after Driver prewarm.
// stop_and_join is a separate physical-output / lifetime boundary, not Core's
// stopped phase. Even failed start must permit stop_and_join to clean up.
class AudioSession {
 public:
  using Render = void (*)(void*, float*, float*, std::uint32_t) noexcept;
  virtual ~AudioSession() = default;
  virtual bool start(Render render, void* context, std::uint8_t volume,
                     bool muted) noexcept = 0;
  // Idempotent and retryable, including quiescent-but-not-silent failures.
  virtual AudioStopResult stop_and_join() noexcept = 0;
  virtual void set_output(std::uint8_t volume, bool muted) noexcept = 0;
  virtual bool healthy() const noexcept = 0;
  // Optional capability keeps existing fake/alternate sessions source
  // compatible; the ESP implementation publishes it after its finish barrier.
  virtual std::optional<std::size_t> stopped_stack_high_water_bytes() const noexcept {
    return std::nullopt;
  }
};

enum class HostResult : std::uint8_t {
  ok, accepted, wrong_state, unsupported_content, audio_error, core_error,
  input_overflow,
};
enum class Key : std::uint8_t {
  pad_a, pad_s, pad_d, pad_f, play_stop, mute, volume_up, volume_down,
  confirm_receive, cancel_receive, overflow,
};
struct KeyEvent { Key key{}; bool pressed{}; };
struct HostProfile { std::uint8_t maximum_pads{}; };
struct HostStatus {
  facade::RuntimePhase phase{facade::RuntimePhase::empty};
  HostResult error{HostResult::ok};
  facade::RuntimeResult core_result{facade::RuntimeResult::ok};
  std::array<facade::RuntimePadSummary, 4> pads{};
  std::uint8_t pad_count{};
  std::uint8_t volume{2};
  bool muted{};
  bool armed{};
  bool physical_stopped{true};
  std::array<char, 64> content_sha256{};
  std::uint64_t content_bytes{};
  // Consumed receipts, never inferred audible/active voice state.
  std::uint32_t last_receipt_sequence{};
  facade::RuntimeCommandOutcome last_receipt_outcome{};
  // Acknowledged local press until acknowledged release/stop. This does not
  // describe Pattern voices or the duration of a One Shot sample's tail.
  std::array<bool, 4> pad_active{};
};

// All methods below have one serialized executor owner. AudioSession must
// outlive this object; neither keyboard nor USB workers call the Facade.
class RuntimeHost final {
 public:
  RuntimeHost(facade::RuntimeConfig config, HostProfile profile, AudioSession& audio);
  ~RuntimeHost();
  RuntimeHost(const RuntimeHost&) = delete;
  RuntimeHost& operator=(const RuntimeHost&) = delete;
  HostResult handle_key(KeyEvent event) noexcept;
  HostResult begin_receive() noexcept;
  HostResult cancel_receive() noexcept;
  HostResult load_received(std::span<const std::byte> bytes,
                           const facade::RuntimeContentIdentity& identity) noexcept;
  HostResult shutdown() noexcept;
  void poll() noexcept;
  HostStatus read_status() const noexcept { return status_; }
#ifdef ESP_PLATFORM
  // Serialized control-owner boundary for future diagnostics extraction. The
  // sample is sequential and is not a callback/ISR operation.
  void read_resources(ResourceObservation& result) const noexcept;
#endif

 private:
  static void render(void*, float*, float*, std::uint32_t) noexcept;
  HostResult start() noexcept;
  HostResult stop() noexcept;
  HostResult fail(HostResult error) noexcept;
  void collect_receipts() noexcept;
  void clear_content() noexcept;
  facade::RuntimeFacade runtime_;
  HostProfile profile_;
  AudioSession& audio_;
  HostStatus status_;
  facade::RuntimeEpoch epoch_;
  std::uint32_t sequence_{};
  // One byte per permitted outstanding command, allocated only at setup.
  // Facade receipt credits prevent slot reuse before its receipt is polled.
  std::vector<std::uint8_t> pending_pad_commands_;
  bool audio_owned_{};
};

#ifdef ESP_PLATFORM
struct EspAudioSessionConfig {
  EspAudioConfig io;
  std::uint32_t stack_bytes{};
  std::uint32_t priority{};
  std::uint32_t prewarm_blocks{};
  std::uint32_t handshake_timeout_ms{};
};

class EspAudioSession final : public AudioSession {
 public:
  explicit EspAudioSession(EspAudioSessionConfig config);
  ~EspAudioSession() override;
  bool start(Render, void*, std::uint8_t volume, bool muted) noexcept override;
  AudioStopResult stop_and_join() noexcept override;
  void set_output(std::uint8_t volume, bool muted) noexcept override;
  bool healthy() const noexcept override;
  // Control owner only. Never reads mutable audio-owned data while running;
  // returns false until the start attempt has published its finished release.
  bool read_diagnostics(AudioDiagnosticsSnapshot&) const noexcept;
  // Same owner/barrier as diagnostics. Unavailable if no worker ran. Captured
  // before task deletion; does not establish idle-task memory reclamation.
  std::optional<std::size_t> stopped_stack_high_water_bytes() const noexcept override;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
#endif

}  // namespace lmdj::cardputer
