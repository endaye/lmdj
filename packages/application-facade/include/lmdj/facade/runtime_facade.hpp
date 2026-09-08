#pragma once

#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <optional>
#include <span>

#include <lmdj/cooker/runtime_content_types.hpp>

namespace lmdj::facade {

using RuntimeContentIdentity = cooker::RuntimeContentIdentity;
using RuntimeContentLimits = cooker::RuntimeContentLimits;

class RuntimeEpoch final {
 public:
  RuntimeEpoch() = default;
  bool operator==(const RuntimeEpoch&) const = default;
 private:
  friend class RuntimeFacade;
  std::shared_ptr<const std::uint32_t> token_;
};

enum class RuntimePhase : std::uint8_t { empty, ready, running, draining, stopped };
enum class RuntimeResult : std::uint8_t {
  ok, accepted, wrong_state, invalid_config, invalid_content, budget_exceeded,
  allocation_failed, preparation_failed, epoch_exhausted, stale_epoch,
  sequence_exhausted, duplicate_sequence, out_of_order, invalid_command,
  queue_full, draining,
};
enum class RuntimeCommandKind : std::uint8_t { press, release, stop_slot, stop_all };
enum class RuntimeCommandOutcome : std::uint8_t {
  applied, voice_started, voice_capacity, cancelled,
};

struct RuntimeConfig {
  RuntimeContentLimits content_limits;
  // Modelled preparation peak plus reserve; not an allocator-enforced heap
  // cap. Platform acceptance must measure the reserve and actual peak.
  std::uint64_t maximum_admitted_bytes{};
  // Explicit allowance for allocator bookkeeping, platform stacks and Host
  // resources. This is supplied/measured by the Host, not inferred from sizeof.
  std::uint64_t platform_reserve_bytes{};
  std::uint32_t maximum_pending_commands{128};
  std::uint32_t maximum_epoch{std::numeric_limits<std::uint32_t>::max()};
  std::uint32_t maximum_sequence{std::numeric_limits<std::uint32_t>::max()};
};

struct RuntimeBudget {
  std::uint64_t fixed_bytes{};
  std::uint64_t encoded_bytes{};
  std::uint64_t pcm_bytes{};
  std::uint64_t prepared_float_bytes{};
  std::uint64_t metadata_bytes{};
  std::uint64_t preparation_workspace_bytes{};
  std::uint64_t platform_reserve_bytes{};
  std::uint64_t admitted_bytes{};
};

struct RuntimeCommand {
  RuntimeEpoch epoch;
  std::uint32_t sequence{};
  RuntimeCommandKind kind{};
  std::uint8_t slot{};
  std::uint8_t velocity{127};
};

struct RuntimeReceipt {
  RuntimeEpoch epoch;
  std::uint32_t sequence{};
  RuntimeCommandOutcome outcome{};
};

// One serialized control caller for everything except render. render admits
// exactly one callback at a time, and never allocates/frees/locks. Destroy only
// after the Host has stopped calling render; stop() drains already admitted
// callbacks but cannot extend the lifetime of an object a Host has destroyed.
class RuntimeFacade final {
 public:
  explicit RuntimeFacade(RuntimeConfig config);
  ~RuntimeFacade();
  RuntimeFacade(const RuntimeFacade&) = delete;
  RuntimeFacade& operator=(const RuntimeFacade&) = delete;

  // Both bytes and identity remain valid/immutable for this entire control
  // call. Success owns all playback data; the caller may then release input.
  RuntimeResult load(std::span<const std::byte> bytes,
                     const RuntimeContentIdentity& identity) noexcept;
  RuntimeResult start(RuntimeEpoch& epoch) noexcept;
  // accepted is admission only. poll returns consumed or cancelled receipts;
  // an applied command need not produce an audible voice (e.g. muted/release).
  RuntimeResult submit(const RuntimeCommand& command) noexcept;
  std::size_t poll(std::span<RuntimeReceipt> receipts) noexcept;
  void request_stop() noexcept;
  RuntimeResult finish_stop() noexcept;
  void stop() noexcept;
  RuntimeResult unload() noexcept;
  void reset() noexcept;
  RuntimePhase phase() const noexcept;
  RuntimeBudget budget() const noexcept;
  // Control-side owned copy of the published complete identity; empty before
  // a successful load and after unload/reset. Copying may allocate.
  std::optional<RuntimeContentIdentity> content_identity() const;
  void render(float* left, float* right, std::uint32_t frames) noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::facade
