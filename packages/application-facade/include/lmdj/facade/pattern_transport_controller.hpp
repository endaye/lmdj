#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <vector>

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
  // Publish a live overlay for the open recording's Pattern (#1513). The
  // coordinator decides when; the Host performs it, because building the
  // prepared view needs a Runtime Snapshot from the Application. Returns the
  // engine's publication receipt, or a failure whose code names the refusal
  // (publish_queue_full when a publication is already queued for the next
  // boundary). The default refusal keeps Hosts that predate this seam
  // building-free; the coordinator simply never publishes through them.
  virtual foundation::Result<audio::PatternPublication> publish_overlay(
      const foundation::PatternId& pattern,
      std::span<const domain::PatternEvent> events) {
    (void)pattern;
    (void)events;
    return foundation::Result<audio::PatternPublication>::failure(
        {foundation::ErrorCode::unsupported_audio,
         "Pattern transport overlay publication is not implemented by this host"});
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

// What an open recording would contribute to its Pattern if it ended now, for
// a Host to publish as a pending overlay so the pass just played is audible on
// the next one (#1513). `pattern_id` is the Pattern the events belong to — the
// one the admission validated its segment against, which the switch machinery
// re-anchors — and a Host must publish against it, not against its own binding.
// `generation` advances only when `events` changes, so a Host that publishes on
// a new generation publishes once per change.
struct PatternTransportOverlay {
  foundation::PatternId pattern_id;
  std::uint64_t generation{};
  std::vector<domain::PatternEvent> events;
  bool operator==(const PatternTransportOverlay&) const = default;
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
  // Projects the open recording's pending overlay. Same control-lane
  // serialization as `request`. It is a pure read of durable state: it mutates
  // no journal and advances no watermark, so however often a Host publishes an
  // overlay, the transfer the close commits is the same one and the commit
  // stays exactly once. `std::nullopt` means there is nothing to publish now —
  // no open recording, a frozen close, or a candidate prefix still awaiting
  // switch reconciliation — and is never a failure of the recording.
  foundation::Result<std::optional<PatternTransportOverlay>> project_overlay();
  // Publishes the open recording's pending overlay through the Host's
  // `publish_overlay` capability and records the publication generation it
  // created in the admission journal (#1513). Driven by the control cadence
  // (`continue_operation` covers it); never call it inline on a Pad trigger.
  // Publishing never drains input, advances no watermark and commits nothing,
  // so the exactly-once argument of the projection carries over: the transfer
  // a close commits is unchanged by any number of overlay publications.
  foundation::Result<void> publish_overlay();

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
