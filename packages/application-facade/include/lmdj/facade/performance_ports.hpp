#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <lmdj/audio/master_fx.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::facade {

class PerformanceClock {
public:
  virtual ~PerformanceClock() = default;
  // Authoritative musical time: 3840 ticks/bar in 4/4. Values are monotone
  // non-decreasing. A successful admission consumes exactly one read.
  virtual void anchor(std::uint16_t bpm, std::uint64_t at_tick) = 0;
  virtual foundation::Result<std::uint64_t> read_tick() = 0;
};

class PerformanceInputSequencer {
public:
  virtual ~PerformanceInputSequencer() = default;
  // Authoritative admission order. A successful admission consumes exactly
  // one sequence and replayed receipts consume none.
  virtual void seed(std::uint64_t last_input_sequence) = 0;
  virtual foundation::Result<std::uint64_t> next() = 0;
};

struct PatternLaunchReservation {
  std::uint64_t target_tick{};
  bool claimed{};
};

enum class PatternLaunchOutcomeKind : std::uint8_t {
  applied,
  cancelled,
  failed,
};

struct PatternLaunchOutcome {
  foundation::SequenceSessionId session_id;
  foundation::CommandId request_id;
  std::uint8_t pattern_slot{};
  std::uint64_t effective_tick{};
  PatternLaunchOutcomeKind kind{PatternLaunchOutcomeKind::failed};
};

class PatternLaunchAcknowledger {
public:
  virtual ~PatternLaunchAcknowledger() = default;
  // Core Runtime owns musical-boundary ordering and exactly-once outcomes.
  // The resolved material is immutable Core truth; Hosts never resolve slots.
  // `earliest_target_tick` is the Performance clock's lower bound in the
  // journal's tick domain; wherever the global Pattern transport is playing,
  // the reserved audio boundary itself comes from the transport's own Bar
  // grid (#1974), and the returned `target_tick` reports that boundary back
  // in the journal domain. `resolved_pattern == nullptr` is a journal-only
  // launch and keeps the Performance clock boundary.
  virtual foundation::Result<PatternLaunchReservation>
  reserve(const foundation::SequenceSessionId &session_id,
          const foundation::CommandId &request_id, std::uint8_t pattern_slot,
          std::uint64_t earliest_target_tick,
          std::shared_ptr<const cooker::RuntimeSnapshot> resolved_pattern) = 0;
  virtual std::vector<PatternLaunchOutcome>
  peek(const foundation::SequenceSessionId &session_id) = 0;
  virtual foundation::Result<void>
  commit(const foundation::SequenceSessionId &session_id,
         const foundation::CommandId &request_id) = 0;
  virtual void
  cancel(const foundation::SequenceSessionId &session_id) noexcept = 0;
};

// Live application of an admitted Performance FX or HOLD gesture to the
// running master bus (P10-D7: live and Replay drive the same DSP). Core owns
// the translation, so no Host decides FX chain order, value scale or
// coalescing. The sink is absent when no engine is attached; admission then
// journals the event and changes no audio.
class PerformanceGestureSink {
public:
  virtual ~PerformanceGestureSink() = default;
  virtual foundation::Result<void> apply_gesture(audio::FxGesture gesture) = 0;
};

// ---------------------------------------------------------------------------
// D0/P1 typed live-control admission port. The sole-producer engine adapter
// implements it; a Host only echoes the Core-issued epoch and generations.
// Everything here runs on the control thread; render gains no entry point.
// ---------------------------------------------------------------------------

// One typed intent of `performance.live.control` / the new-profile recording
// route. Single-parameter intents are derived against the Core accepted
// state, so a Host never supplies a full state, tick, frame or sequence.
struct PerformanceLiveControlIntent {
  enum class Kind : std::uint8_t {
    filter_parameter,  // engage/move one typed parameter
    filter_release,    // release the independent Filter gesture
    fx_parameter,      // engage/move one of the eight chain FX (filter here
                       // is the legacy scalar, original semantics)
    fx_release,
    pad_mute,
    pad_solo,
    clear_pad_gates,
    hold_on,
    hold_off,
  };
  enum class FilterParameter : std::uint8_t { type, cutoff_hz, resonance_milli };

  Kind kind{Kind::hold_on};
  domain::PerformanceFilterPhase phase{domain::PerformanceFilterPhase::engage};
  FilterParameter parameter{FilterParameter::cutoff_hz};
  std::uint32_t value{};  // typed unit per parameter; fx value is 0..1000
  domain::PerformanceFx fx{domain::PerformanceFx::filter};
  std::uint8_t slot{};    // pad_mute/pad_solo
  bool enabled{};         // pad_mute/pad_solo
  // move/release only: the Core-issued runtime gesture generation the Host
  // echoes from status/begin mapping; engages never carry one.
  std::optional<std::string> gesture_generation;
};

// The complete live-control state in the durable header's shape, plus the
// Core runtime gesture generation of every engaged binding (by PerformanceFx
// ordinal). Generations are live identities: never durable, never
// Host-interpreted, and a frozen-only (HOLD) control has none.
struct PerformanceLiveControlState {
  domain::PerformanceInitialLiveState state;
  std::array<std::optional<std::string>, 8> runtime_generations{};

  bool operator==(const PerformanceLiveControlState&) const = default;
};

struct PerformanceLiveControlSnapshot {
  PerformanceLiveControlState accepted;
  PerformanceLiveControlState applied;
  // Core control sequences; applied counts queue positions the audio thread
  // has drained, not enqueue counters.
  std::uint64_t accepted_control_sequence{};
  std::uint64_t applied_control_sequence{};
  std::uint64_t engine_start_epoch{};

  bool operator==(const PerformanceLiveControlSnapshot&) const = default;
};

// A held queue cell plus the full derived outcome of one admission. Produced
// by reserve (zero state change), consumed exactly once by publish or cancel.
struct PerformanceLiveControlReservation {
  // The engine message to publish; exactly one member is engaged.
  std::optional<audio::FxGesture> fx_gesture;
  std::optional<audio::FilterGesture> filter_gesture;
  std::optional<audio::PadGatesState> pad_gates;
  // The accepted state the admission produces.
  PerformanceLiveControlState resulting_state;
  // Set by reserve for engages: the new Core runtime generation.
  std::optional<std::string> assigned_generation;
  // Control sequence this admission will occupy once published.
  std::uint64_t control_sequence{};
  // Opaque adapter hold; released by publish/cancel.
  std::shared_ptr<void> hold;

  bool operator==(const PerformanceLiveControlReservation&) const = delete;
};

enum class PerformanceFenceReadiness : std::uint8_t {
  pending,
  ready,
  // The applied state at the fence position does not match the captured
  // header, or the epoch changed underneath the fence: recovery-required.
  diverged,
};

struct PerformanceControlFence {
  // The queue position the fence occupies; every earlier accepted control is
  // inside the captured header.
  std::uint64_t position{};
  std::uint64_t engine_start_epoch{};
  PerformanceLiveControlState header;

  bool operator==(const PerformanceControlFence&) const = default;
};

class PerformanceLiveControlSink {
 public:
  virtual ~PerformanceLiveControlSink() = default;

  // The current Core-issued epoch; nullopt when no verified Project target is
  // bound or the binding was invalidated (close/replacement/engine restart).
  virtual std::optional<std::string> current_control_epoch() = 0;
  // The Project UUID the current epoch is bound to.
  virtual std::optional<std::string> bound_control_project() = 0;
  // Binds a Core-verified Project identity and returns its epoch. Idempotent
  // while the same UUID and engine start_epoch hold; a different UUID or an
  // observed engine restart issues a fresh epoch. Never rebinding on
  // same-Project Bank/Pattern/revision preparation.
  virtual foundation::Result<std::string> bind_control_target(
      std::string project_uuid) = 0;
  virtual void invalidate_control_target() = 0;

  virtual PerformanceLiveControlSnapshot live_control_snapshot() = 0;

  // Validates epoch, shape, range and the runtime generation binding against
  // the accepted state, derives the full resulting state and holds one
  // bounded queue cell. No accepted state, counter or audio changes.
  virtual foundation::Result<PerformanceLiveControlReservation>
  reserve_live_control(const std::string& control_epoch,
                       const PerformanceLiveControlIntent& intent) = 0;
  // Re-reserves a cell for the frozen translation of a known-failed prepared
  // admission: identical engine messages and derived state, no re-derivation,
  // no second tick/sequence. Only the Facade kernel's exact-retry window
  // calls this.
  virtual foundation::Result<PerformanceLiveControlReservation>
  reserve_live_control_republish(
      const std::string& control_epoch,
      std::optional<audio::FxGesture> fx_gesture,
      std::optional<audio::FilterGesture> filter_gesture,
      std::optional<audio::PadGatesState> pad_gates,
      PerformanceLiveControlState resulting_state,
      std::optional<std::string> assigned_generation) = 0;
  // Publishes the held cell; on success the accepted shadow and the control
  // sequence advance. A known engine refusal (e.g. not_running) is a failure
  // with no shadow change.
  virtual foundation::Result<void> publish_live_control(
      PerformanceLiveControlReservation reservation) = 0;
  // Releases the held cell without publishing (known journal failure).
  virtual void cancel_live_control(
      PerformanceLiveControlReservation reservation) noexcept = 0;

  // The record begin fence: captures the accepted state as the recording
  // header and returns the queue position proving it. Fails (queue_full)
  // before any Facade-side draft exists.
  virtual foundation::Result<PerformanceControlFence> begin_fence(
      const std::string& control_epoch) = 0;
  // pending until the audio thread drains the fence position; ready only when
  // the state at exactly that position equals the header field-wise and the
  // epoch still holds; diverged otherwise (never a latest-value guess).
  virtual PerformanceFenceReadiness fence_readiness(
      const PerformanceControlFence& fence) = 0;
};

}  // namespace lmdj::facade
