#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/facade/pattern_transport_ports.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::facade {

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
};

struct PatternTransportControllerConfig {
  std::filesystem::path bundle;
  foundation::SequenceSessionId session;
  foundation::ProjectId project;
  foundation::PatternId pattern;
  std::uint64_t runtime_generation{};
};

// Host-consumable Pattern transport controller: the public ownership wrapper
// around the internal coordinator. The Facade compilation unit constructs and
// self-owns the Sequence Journal and Project Store the coordinator needs, so
// the public signature carries only ports/foundation/audio/std types and a
// Host never names a Project I/O type or parses a Project bundle.
//
// All three operations are short serialized-control-lane steps.
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

 private:
  struct Impl;
  explicit PatternTransportController(std::unique_ptr<Impl> impl);

  std::unique_ptr<Impl> impl_;

  friend std::unique_ptr<PatternTransportController>
  make_pattern_transport_controller(PatternTransportAudioPort&,
                                    PatternTransportControllerConfig);
};

// `audio` must outlive the returned controller. The controller owns its
// Journal/Store with the same default storage platform the Application uses
// when the Host supplies none.
std::unique_ptr<PatternTransportController> make_pattern_transport_controller(
    PatternTransportAudioPort& audio, PatternTransportControllerConfig config);

}  // namespace lmdj::facade
