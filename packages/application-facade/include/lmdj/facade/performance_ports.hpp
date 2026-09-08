#pragma once

#include <cstdint>
#include <memory>
#include <vector>

#include <lmdj/audio/master_fx.hpp>
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

}  // namespace lmdj::facade
