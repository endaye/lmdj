#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>

#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::facade {

inline constexpr std::size_t kPatternTransportWorkPayloadBytes = 64 * 1024;

struct PatternTransportWorkIdentity {
  std::uint64_t runtime_generation{};
  std::uint64_t transport_epoch{};
  foundation::CommandId command_id;
  // Monotone across the lifetime of this executor, including consumed tickets.
  std::uint64_t step{};
  bool operator==(const PatternTransportWorkIdentity&) const = default;
};
struct PatternTransportWorkRequest {
  PatternTransportWorkIdentity identity;
  // Immutable, bounded control metadata. The owning coordinator supplies and
  // validates its encoding; Project objects and PCM are never carried here.
  std::string payload;
  bool operator==(const PatternTransportWorkRequest&) const = default;
};
enum class PatternTransportWorkOutcome : std::uint8_t { success, refused, unknown };
struct PatternTransportWorkCompletion {
  PatternTransportWorkOutcome outcome{};
  std::string payload;
  std::optional<foundation::Error> error;
};
enum class PatternTransportWorkSubmit : std::uint8_t {
  accepted, replayed, busy, invalid, stale, unavailable
};
class PatternTransportWorkOwner {
 public:
  virtual ~PatternTransportWorkOwner() = default;
  virtual PatternTransportWorkCompletion execute(const PatternTransportWorkRequest&) = 0;
};
struct PatternTransportExecutorStatus {
  bool ready{};
  bool shutdown_requested{};
  bool stopped{};
  std::optional<PatternTransportWorkIdentity> ticket;
  std::shared_ptr<const PatternTransportWorkCompletion> completion;
  std::optional<foundation::Error> startup_error;
};

// One retained work cell; no audio-thread use. Construction/execute/destruction
// of the work owner all run on the same dedicated thread. Factories must create
// their storage/lease owners there, not capture an existing mutable Application
// or a lease from another thread. Submit and inspect never call the owner or
// wait for IO; execute runs outside the executor mutex.
//
// The coordinator must durably reconcile effects before consuming a ticket.
// Timeout is only absence of a completion; it never cancels or repeats work.
// After consumption, a stale step is refused rather than executed again.
// request_shutdown is nonblocking and drains accepted work. Lifecycle callers
// poll stopped before destroying the executor; the destructor joins as a final
// lifetime safeguard: never destroy on audio, or on control while !stopped.
class PatternTransportExecutor final {
 public:
  using Factory = std::function<std::unique_ptr<PatternTransportWorkOwner>()>;
  PatternTransportExecutor(std::uint64_t runtime_generation, Factory factory);
  ~PatternTransportExecutor();
  PatternTransportExecutor(const PatternTransportExecutor&) = delete;
  PatternTransportExecutor& operator=(const PatternTransportExecutor&) = delete;
  PatternTransportWorkSubmit submit(const PatternTransportWorkRequest& request);
  PatternTransportExecutorStatus inspect() const;
  bool consume(const PatternTransportWorkIdentity& identity);
  void request_shutdown();
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

enum class PatternTransportIntent : std::uint8_t { play_stop, record };
enum class PatternTransportPhase : std::uint8_t {
  idle, preparing, awaiting_audio, flushing, reconciling, error
};
enum class PatternTransportSubmit : std::uint8_t {
  accepted, replayed, busy, invalid, stale, refused
};
struct PatternTransportRequest {
  foundation::SequenceSessionId session;
  foundation::ProjectId project_id;
  foundation::CommandId command_id;
  std::uint64_t runtime_generation{};
  std::uint64_t expected_epoch{};
  PatternTransportIntent intent{};
  std::optional<std::uint64_t> expected_revision;
  bool operator==(const PatternTransportRequest&) const = default;
};
struct PatternTransportStatus {
  bool playing{};
  bool recording{};
  PatternTransportPhase phase{PatternTransportPhase::idle};
  std::uint64_t runtime_generation{};
  std::uint64_t transport_epoch{};
  std::uint64_t origin_frame{};
  std::optional<foundation::CommandId> command_id;
  std::optional<foundation::Error> error;
};

}  // namespace lmdj::facade
