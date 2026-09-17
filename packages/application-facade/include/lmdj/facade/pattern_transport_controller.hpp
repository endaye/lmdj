#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/pattern_transport_ports.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::facade {

namespace detail {
class PatternTransportControllerInternalFactory;
}

// Host-facing audio port for the Pattern transport coordinator (#1230). The
// Host implements it over its own engine; every method names only Audio
// Runtime, Foundation and std types, so a Host never spells a Project I/O
// type to drive transport.
//
// Threading: these are serialized-control-lane calls, the same owner as the
// engine's submit/inspect/acknowledge (realtime_engine.hpp "These three
// methods share the serialized control owner"). The port is not thread-safe
// beyond that lane and is never called from the audio thread.
class PatternTransportAudioPort {
 public:
  virtual ~PatternTransportAudioPort() = default;
  virtual audio::PatternTransportSubmit submit(
      const audio::PatternTransportCommand& command) = 0;
  virtual std::optional<audio::PatternTransportReceipt> inspect(
      std::uint64_t generation, std::uint64_t epoch) const = 0;
  virtual bool acknowledge(std::uint64_t generation, std::uint64_t epoch) = 0;
  virtual std::uint64_t pattern_generation() const = 0;
  virtual std::optional<audio::PatternReplacementAuthority> pending_switch()
      const = 0;
  // The engine's current Pattern identity on the same control lane.
  // `std::nullopt` means no retarget information: the engine has no current
  // Pattern or the port does not know it, and the coordinator keeps its
  // vendored binding. A concrete id lets the coordinator re-anchor its
  // binding when it opens a new journal after an applied switch (#1403).
  virtual std::optional<foundation::PatternId> current_pattern() const {
    return std::nullopt;
  }
};

struct PatternTransportControllerConfig {
  std::filesystem::path bundle;
  foundation::SequenceSessionId session;
  foundation::ProjectId project;
  foundation::PatternId pattern;
  std::uint64_t runtime_generation{};
};

// Public mirror of the internal admission verdict: `retained` means the
// candidate is durably appended to the prepared admission; `live_only` means
// it stays live input only (pre-fence, closed, or owner-lost recording) and
// nothing was persisted.
enum class PatternAdmissionAdmit : std::uint8_t { retained, live_only };

// One post-enqueue live-input observation offered to the recording admission.
// The Host stamps it where enqueue success is known; it is enqueue
// eligibility, never proof of audible acceptance. Field meanings map one to
// one onto the internal admission candidate:
//
//   watermark       Host-side monotone input watermark, allocated after
//                   enqueue acceptance; orders candidates for drain.
//   runtime_frame   Engine rendered_frames sampled at that point.
//   slot            Pad Slot the gesture hit.
//   pressed         true for the press, false for its release.
//   velocity        Press velocity; unused on release.
//   correlation     Press ownership identity. It must always carry a value: a
//                   press names its own identity (its watermark), a release
//                   repeats the owned press's value to close it. A release
//                   whose correlation matches no owned press closes nothing
//                   and never fabricates a press; the conversion checkpoint
//                   dereferences the stored correlation unconditionally, so a
//                   valueless press would be undefined behaviour downstream.
struct PatternTransportCandidate {
  std::uint64_t watermark{};
  std::uint64_t runtime_frame{};
  domain::PadSlotId slot;
  bool pressed{};
  std::uint8_t velocity{};
  std::uint64_t correlation{};
  bool operator==(const PatternTransportCandidate&) const = default;
};

// Host-consumable Pattern transport controller: the public ownership wrapper
// around the internal coordinator. The Facade compilation unit constructs and
// self-owns the Sequence Journal and Project Store the coordinator needs, so
// the public signature carries only ports/foundation/audio/std types and a
// Host never names a Project I/O type or parses a Project bundle.
//
// All four operations are short serialized-control-lane steps.
// `request` resolves the toggle once and reserves the command/epoch without
// waiting for audio or IO; `continue_operation` is the reentrant continuation
// step that inspects an already-published receipt and settles durable effects,
// returning success immediately when no receipt exists yet. The Host drives
// continuations on its own control lane (for example beside its existing
// service pump); a continuation must never move to an executor worker thread.
// One controller serves one runtime/session/Pattern binding; a stale runtime
// generation is rejected per request.
class PatternTransportController {
 public:
  ~PatternTransportController();
  PatternTransportController(PatternTransportController&&) noexcept;
  PatternTransportController& operator=(
      PatternTransportController&&) noexcept;
  PatternTransportController(const PatternTransportController&) = delete;
  PatternTransportController& operator=(const PatternTransportController&) =
      delete;

  PatternTransportSubmit request(const PatternTransportRequest& request);
  PatternTransportStatus inspect() const;
  foundation::Result<void> continue_operation();
  // Offers one post-enqueue candidate to the recording admission. Fails while
  // no recording is open on this controller's session; succeeds with
  // `live_only` when the candidate falls outside the acknowledged
  // admission/cutoff interval. Same control-lane serialization as `request`.
  foundation::Result<PatternAdmissionAdmit> admit(
      const PatternTransportCandidate& candidate);

 private:
  struct Impl;
  explicit PatternTransportController(std::unique_ptr<Impl> impl);

  std::unique_ptr<Impl> impl_;

  friend std::unique_ptr<PatternTransportController>
  make_pattern_transport_controller(PatternTransportAudioPort&,
                                    PatternTransportControllerConfig);
  friend class detail::PatternTransportControllerInternalFactory;
};

// `audio` must outlive the returned controller. The controller owns its
// Journal/Store with the same default storage platform the Application uses
// when the Host supplies none.
std::unique_ptr<PatternTransportController> make_pattern_transport_controller(
    PatternTransportAudioPort& audio, PatternTransportControllerConfig config);

}  // namespace lmdj::facade
