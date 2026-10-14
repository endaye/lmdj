#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <optional>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/scheduled_pattern_transport.hpp>
#include <lmdj/facade/pattern_transport_ports.hpp>
#include <lmdj/domain/project.hpp>

namespace lmdj::facade {

// Companion capability: the legacy audio port's layout and vtable are frozen.
// All calls run on the serialized control owner, never the I/O thread.
class ScheduledPatternTransportAudioPort {
 public:
  virtual ~ScheduledPatternTransportAudioPort() = default;
  virtual audio::ScheduledPatternSubmit submit_scheduled(
      const audio::ScheduledPatternRecordRequest&) = 0;
  virtual std::optional<audio::ScheduledPatternRecordStatus> inspect_scheduled(
      std::uint64_t generation, std::uint64_t serial) const = 0;
  virtual audio::ScheduledPatternSubmit cancel_scheduled(
      const audio::ScheduledPatternCancelRequest&) = 0;
  virtual bool acknowledge_scheduled(std::uint64_t generation,
      std::uint64_t serial, std::uint64_t epoch) = 0;
  virtual bool scheduled_quiescent() const = 0;
};

struct ScheduledPatternTransportRequest {
  PatternTransportRequest transport;
  std::uint64_t frame_epoch{};
  std::uint64_t schedule_serial{};
  std::uint8_t bars{};
  bool operator==(const ScheduledPatternTransportRequest&) const = default;
};
struct ScheduledPatternTransportCancel {
  PatternTransportRequest transport;
  std::uint64_t frame_epoch{};
  std::uint64_t schedule_serial{};
  bool operator==(const ScheduledPatternTransportCancel&) const = default;
};
struct ScheduledPatternTransportStatus {
  std::optional<ScheduledPatternTransportRequest> request;
  std::optional<audio::ScheduledPatternRecordStatus> count_in;
  std::optional<audio::ScheduledPatternRecordReceipt> start_receipt;
  std::optional<audio::ScheduledPatternRecordReceipt> cancel_receipt;
  bool opening_pending{};
  bool opening_complete{};
  std::optional<foundation::Error> error;
};

inline constexpr std::size_t kPatternTransportIngressCapacity = audio::kRealtimeQueueCapacity;
inline constexpr auto kPatternTransportInputDeadline = std::chrono::seconds{1};
inline constexpr auto kScheduledPatternOpeningDeadline = std::chrono::seconds{5};

struct PatternTransportInputRequest {
  foundation::CommandId command_id;
  std::uint64_t runtime_generation{};
  std::uint64_t frame_epoch{};
  std::uint64_t runtime_frame{};
  domain::PadSlotId slot;
  bool pressed{};
  std::uint8_t velocity{};
  // A release names the actual native sequence of its held press.
  std::uint64_t correlation{};
  bool held{true};
  bool operator==(const PatternTransportInputRequest&) const = default;
};
struct PatternTransportInputTicket {
  std::uint64_t runtime_generation{};
  foundation::CommandId command_id;
  std::uint64_t ticket{};
  bool operator==(const PatternTransportInputTicket&) const = default;
};
struct PatternTransportInputStatus {
  PatternTransportInputTicket ticket;
  std::optional<audio::PatternInputAdmission> admission;
  std::optional<audio::PatternInputCompletion> native_result;
  bool durable_settled{};
  bool retained{};
  bool complete{};
  bool expired{};
  std::optional<foundation::Error> error;
};
struct PatternTransportIngressStatus {
  std::size_t ordinary_pending{};
  std::size_t held_release_metadata{};
  std::size_t retained_tickets{};
};
}  // namespace lmdj::facade
