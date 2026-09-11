#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include <lmdj/domain/project.hpp>

namespace lmdj::project_io {

inline constexpr std::size_t kSequenceAdmissionMaxCandidates = 1024;
inline constexpr std::size_t kSequenceAdmissionCandidateBytes = 1024 * 1024;
inline constexpr std::size_t kSequenceAdmissionTransferBytes = 1024 * 1024;
inline constexpr std::size_t kSequenceAdmissionControlBytes = 64 * 1024;
inline constexpr std::uint32_t kSequenceAdmissionFenceTimeoutMs = 5000;

enum class SequenceCandidateKind : std::uint8_t { press, release };
enum class SequenceFenceKind : std::uint8_t { admission, cutoff };
enum class SequenceSwitchOutcome : std::uint8_t {
  none, applied_before_cutoff, canceled_at_cutoff
};
enum class SequenceAdmissionCloseReason : std::uint8_t {
  requested, capacity, deadline, storage_failure, owner_lost
};

struct SequenceAdmissionIdentity {
  foundation::CommandId operation_id;
  std::uint64_t runtime_generation{};
  std::uint64_t transport_epoch{};
  bool operator==(const SequenceAdmissionIdentity&) const = default;
};
struct SequenceAdmissionPreparation {
  SequenceAdmissionIdentity identity;
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t publication_generation{};
  std::uint64_t first_watermark{};
  std::uint32_t candidate_limit{kSequenceAdmissionMaxCandidates};
  std::uint32_t candidate_byte_limit{kSequenceAdmissionCandidateBytes};
  std::uint32_t fence_timeout_ms{kSequenceAdmissionFenceTimeoutMs};
  bool operator==(const SequenceAdmissionPreparation&) const = default;
};
struct SequenceAdmissionCandidate {
  // Receipt preimage: canonical JSON of these six named fields; slot is an
  // object {bank,pad}, kind is the numeric enum value. Candidate-byte limits
  // count the sum of these encoded objects, excluding envelopes/array brackets.
  std::uint64_t watermark{};
  std::uint64_t runtime_frame{};
  domain::PadSlotId slot;
  SequenceCandidateKind kind{};
  std::uint8_t velocity{};
  std::uint64_t press_sequence{};
  bool operator==(const SequenceAdmissionCandidate&) const = default;
};
struct SequencePublicationAuthority {
  foundation::PatternId pattern_id;
  std::uint64_t generation{};
  std::uint64_t frame{};
  bool operator==(const SequencePublicationAuthority&) const = default;
};
struct SequenceAdmissionFence {
  SequenceFenceKind kind{};
  foundation::CommandId command_id;
  std::uint64_t transport_epoch{};
  std::uint64_t effective_frame{};
  std::uint64_t origin_frame{};
  foundation::PatternId pattern_id;
  std::uint64_t publication_generation{};
  std::uint16_t bpm{};
  bool playing{};
  std::optional<SequencePublicationAuthority> switch_authority;
  SequenceSwitchOutcome switch_outcome{};
  std::optional<std::uint64_t> switch_applied_frame;
  bool operator==(const SequenceAdmissionFence&) const = default;
};
struct SequenceAdmissionClosure {
  std::optional<std::uint64_t> last_retained_watermark;
  SequenceAdmissionCloseReason reason{};
  bool operator==(const SequenceAdmissionClosure&) const = default;
};
struct SequenceOwnedPress {
  domain::PadSlotId slot;
  std::uint64_t press_sequence{};
  std::uint64_t raw_attack_tick{};
  std::uint32_t onset_tick{};
  std::uint8_t velocity{};
  bool operator==(const SequenceOwnedPress&) const = default;
};
struct SequenceAdmissionCheckpoint {
  foundation::PatternId pattern_id;
  std::uint64_t last_runtime_frame{};
  std::vector<SequenceOwnedPress> owned_presses;
  bool operator==(const SequenceAdmissionCheckpoint&) const = default;
};
struct SequenceCandidateReceipt {
  std::uint64_t watermark{};
  std::string payload_sha256;
  bool operator==(const SequenceCandidateReceipt&) const = default;
};
struct SequenceAdmissionTransfer {
  foundation::CommandId transfer_id;
  bool terminal{};
  // Ordinary transfers bind a nonempty prefix. Terminal transfers require
  // zero bounds, empty receipts and SHA-256 of [], and preserve input sequence.
  std::uint64_t first_watermark{};
  std::uint64_t last_watermark{};
  std::string candidates_sha256;
  std::vector<SequenceCandidateReceipt> candidate_receipts;
  foundation::PatternId pattern_id;
  std::uint64_t expected_revision{};
  std::optional<std::uint64_t> journal_input_sequence;
  std::vector<domain::PatternEvent> recoverable_tail;
  SequenceAdmissionCheckpoint checkpoint;
  bool operator==(const SequenceAdmissionTransfer&) const = default;
};
struct SequenceAdmissionState {
  SequenceAdmissionPreparation preparation;
  std::vector<SequenceAdmissionCandidate> candidates;
  std::optional<SequenceAdmissionFence> admission_fence;
  std::optional<SequenceAdmissionFence> cutoff_fence;
  std::optional<SequenceAdmissionClosure> closure;
  std::vector<SequenceAdmissionTransfer> transfers;
  bool completed{};
  bool operator==(const SequenceAdmissionState&) const = default;
};

}  // namespace lmdj::project_io
