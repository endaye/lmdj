#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

#include <lmdj/domain/project.hpp>
#include <lmdj/project_io/sequence_admission.hpp>
#include <lmdj/project_io/storage_platform.hpp>

namespace lmdj::project_io {

enum class SessionKind : std::uint8_t {
  sequence,
  performance,
};

enum class SequenceSessionState : std::uint8_t {
  active,
  switching,
  stopped,
  recovery_required,
  owner_lost,
  abandoned,
};

struct SequenceFlushRecord {
  std::uint64_t flush_seq{};
  foundation::CommandId command_id;
  foundation::PatternId pattern_id;
  std::uint64_t expected_revision{};
  // Immutable canonical payload bound to command_id and flush identity.
  std::vector<domain::PatternEvent> canonical_events;
  // Effective uncommitted subset used only for recovery/reconciliation.
  std::vector<domain::PatternEvent> recovery_events;
  bool completed{};
  SessionKind kind{SessionKind::sequence};

  bool operator==(const SequenceFlushRecord&) const = default;
};

struct SequenceCaptureCommit {
  foundation::CommandId command_id;
  foundation::AssetId asset_id;
  domain::PadSlotId slot;
  foundation::ArtifactRef artifact;
  std::uint64_t expected_revision{};

  bool operator==(const SequenceCaptureCommit&) const = default;
};

struct ActiveSequenceJournal {
  foundation::SequenceSessionId session_id;
  foundation::PatternId pattern_id;
  std::uint8_t bars{};
  std::string pattern_fingerprint;
  std::uint64_t expected_revision{};
  std::uint64_t next_flush_seq{};
  SequenceSessionState state{SequenceSessionState::active};
  std::vector<SequenceFlushRecord> flushes;
  std::optional<domain::PadSlotId> armed_capture_slot;
  std::optional<SequenceCaptureCommit> capture_commit;
  std::uint64_t next_tail_seq{};
  std::optional<std::uint64_t> last_input_sequence;
  std::vector<domain::PatternEvent> pending_events;
  SessionKind kind{SessionKind::sequence};
  std::optional<SequenceAdmissionState> admission{};

  bool operator==(const ActiveSequenceJournal&) const = default;
};

struct SequenceRecoveryCandidate {
  ActiveSequenceJournal journal;
  std::string reason;
  std::filesystem::path path;

  bool operator==(const SequenceRecoveryCandidate&) const = default;
};

struct SequenceCaptureDisarmResult {
  bool reconciled_commit{};
  std::uint64_t expected_revision{};

  bool operator==(const SequenceCaptureDisarmResult&) const = default;
};

struct PerformanceFlushRecord {
  std::uint64_t flush_seq{};
  foundation::CommandId command_id;
  domain::PerformanceId performance_id;
  std::uint64_t expected_revision{};
  std::vector<domain::PerformanceEvent> canonical_events;
  bool completed{};
  SessionKind kind{SessionKind::performance};

  bool operator==(const PerformanceFlushRecord&) const = default;
};

struct PerformanceRebaseRecord {
  foundation::CommandId command_id;
  std::string command_fingerprint;
  std::uint64_t from_revision{};
  std::uint64_t to_revision{};
  std::optional<std::uint16_t> bpm_anchor;
  bool completed{};

  bool operator==(const PerformanceRebaseRecord&) const = default;
};

struct PerformanceRebasePrepare {
  foundation::CommandId command_id;
  std::string command_fingerprint;
  std::uint64_t from_revision{};
  std::uint64_t to_revision{};

  bool operator==(const PerformanceRebasePrepare&) const = default;
};

struct PerformanceRebaseComplete {
  foundation::CommandId command_id;
  std::uint64_t committed_revision{};
  std::optional<std::uint16_t> bpm_anchor;

  bool operator==(const PerformanceRebaseComplete&) const = default;
};

struct PerformanceOpenPadTransient {
  PerformanceOpenPadTransient() = default;
  PerformanceOpenPadTransient(
      std::string gesture_id_value,
      std::uint8_t slot_value,
      std::uint64_t onset_tick_value,
      std::uint8_t velocity_value,
      std::optional<std::uint64_t> input_sequence_value = std::nullopt)
      : gesture_id(std::move(gesture_id_value)),
        slot(slot_value),
        onset_tick(onset_tick_value),
        velocity(velocity_value),
        input_sequence(input_sequence_value) {}

  std::string gesture_id;
  std::uint8_t slot{};
  std::uint64_t onset_tick{};
  std::uint8_t velocity{};
  // The original press's durable input sequence (headered profile only);
  // owner-loss closure reuses it for the completed PadHit.
  std::optional<std::uint64_t> input_sequence;

  bool operator==(const PerformanceOpenPadTransient&) const = default;
};

struct PerformanceOpenFxTransient {
  domain::PerformanceFx fx{domain::PerformanceFx::filter};
  std::string gesture_id;
  std::uint16_t effective_value{};
  std::optional<std::uint16_t> pending_value;

  bool operator==(const PerformanceOpenFxTransient&) const = default;
};

// Headered profile only: the logical recording gesture of an engaged
// independent Filter. A frozen-only Filter is live state, never an open
// gesture; a legacy-mode engaged Filter stays in `open_fx`, so a checkpoint
// never carries two Filter bindings.
struct PerformanceOpenFilterTransient {
  std::string gesture_id;
  domain::PerformanceFilterType type{domain::PerformanceFilterType::lp};
  std::uint16_t cutoff_hz{domain::kFilterCutoffHzMax};
  std::uint16_t resonance_milli{};

  bool operator==(const PerformanceOpenFilterTransient&) const = default;
};

struct PerformanceTransientCheckpoint {
  PerformanceTransientCheckpoint() = default;
  PerformanceTransientCheckpoint(
      std::vector<PerformanceOpenPadTransient> open_pads_value,
      std::vector<PerformanceOpenFxTransient> open_fx_value,
      bool hold_value,
      std::uint64_t last_accepted_tick_value,
      std::optional<PerformanceOpenFilterTransient> open_filter_value =
          std::nullopt,
      std::optional<domain::PerformanceInitialLiveState> live_state_value =
          std::nullopt)
      : open_pads(std::move(open_pads_value)),
        open_fx(std::move(open_fx_value)),
        hold(hold_value),
        last_accepted_tick(last_accepted_tick_value),
        open_filter(std::move(open_filter_value)),
        live_state(std::move(live_state_value)) {}

  std::vector<PerformanceOpenPadTransient> open_pads;
  std::vector<PerformanceOpenFxTransient> open_fx;
  bool hold{};
  std::uint64_t last_accepted_tick{};
  // Headered profile extensions: the current independent-Filter gesture and
  // the complete current live control state, so durable recovery never has
  // to reconstruct it from the begin header after later changes.
  std::optional<PerformanceOpenFilterTransient> open_filter;
  std::optional<domain::PerformanceInitialLiveState> live_state;

  bool operator==(const PerformanceTransientCheckpoint&) const = default;
};

struct PerformanceLaunchAck {
  foundation::CommandId request_id;
  std::uint8_t pattern_slot{};
  std::uint64_t effective_tick{};

  bool operator==(const PerformanceLaunchAck&) const = default;
};

// The headered profile's durable admission ledger (lmdj.project.v5 5.4.1):
// per session at most one pending plus the most recent completed admission.
// `expected_recording_sequence` is Core-issued; a receipt binds the original
// request id, the raw-request SHA-256, the frozen tick and input sequence,
// the phase/result and the durable events' sequence list.
enum class PerformanceAdmissionPhase : std::uint8_t {
  prepared,
  completed,
};

enum class PerformanceAdmissionResult : std::uint8_t {
  not_published,
  published,
  no_audio,
};

struct PerformanceAdmissionBinding {
  domain::PerformanceFx fx{domain::PerformanceFx::filter};
  // The logical recording gesture id; runtime generations are never durable.
  std::string recording_gesture_id;

  bool operator==(const PerformanceAdmissionBinding&) const = default;
};

struct PerformanceAdmissionReceipt {
  foundation::CommandId request_id{""};
  std::uint64_t expected_recording_sequence{};
  std::string request_fingerprint;
  std::uint64_t accepted_tick{};
  std::uint64_t input_sequence{};
  PerformanceAdmissionPhase phase{PerformanceAdmissionPhase::prepared};
  PerformanceAdmissionResult result{
      PerformanceAdmissionResult::not_published};
  std::vector<std::uint64_t> event_input_sequences;
  std::optional<PerformanceAdmissionBinding> binding_result;

  bool operator==(const PerformanceAdmissionReceipt&) const = default;
};

struct PerformanceAdmissionLedger {
  std::uint64_t next_recording_sequence{};
  std::optional<PerformanceAdmissionReceipt> pending;
  std::optional<PerformanceAdmissionReceipt> completed;

  bool operator==(const PerformanceAdmissionLedger&) const = default;
};

struct PerformanceTransientClosurePreview {
  std::vector<domain::PerformanceEvent> canonical_events;
  std::size_t appended_event_count{};
  std::uint64_t closure_tick{};

  bool operator==(const PerformanceTransientClosurePreview&) const = default;
};

struct ActivePerformanceJournal {
  foundation::SequenceSessionId session_id;
  domain::PerformanceId performance_id;
  std::string performance_fingerprint;
  std::uint64_t expected_revision{};
  std::uint64_t next_flush_seq{};
  SequenceSessionState state{SequenceSessionState::active};
  std::vector<PerformanceFlushRecord> flushes;
  std::uint64_t next_tail_seq{};
  std::optional<std::uint64_t> last_input_sequence;
  std::vector<domain::PerformanceEvent> pending_events;
  SessionKind kind{SessionKind::performance};
  std::optional<foundation::CommandId> begin_command_id;
  std::optional<foundation::CommandId> stop_request_id;
  std::vector<PerformanceRebaseRecord> rebases;
  std::optional<PerformanceTransientCheckpoint> transient_checkpoint;
  std::optional<PerformanceLaunchAck> last_launch_ack;
  // Headered recording profile (lmdj.project.v5 5.4.1): the immutable begin
  // header and the bounded durable admission ledger. Both are present exactly
  // in the new profile; a legacy v1 Journal never gains them.
  std::optional<domain::PerformanceInitialLiveState> initial_live_state;
  std::optional<PerformanceAdmissionLedger> admission_ledger;

  bool operator==(const ActivePerformanceJournal&) const = default;
};

struct PerformanceRecoveryCandidate {
  ActivePerformanceJournal journal;
  std::string reason;
  std::filesystem::path path;

  bool operator==(const PerformanceRecoveryCandidate&) const = default;
};

using SequenceCaptureTruthInspector = std::function<foundation::Result<
    std::optional<std::uint64_t>>(const SequenceCaptureCommit&)>;

// Returns lowercase SHA-256 of the exact SR-D22 canonical JSON preimage.
std::string sequence_pattern_fingerprint(const domain::Pattern& pattern);
SequenceCandidateReceipt sequence_admission_candidate_receipt(
    const SequenceAdmissionCandidate& candidate);
std::string sequence_admission_candidates_sha256(
    std::span<const SequenceAdmissionCandidate> candidates);
std::string performance_fingerprint(const domain::Performance& performance);
foundation::Result<PerformanceTransientClosurePreview>
preview_performance_owner_loss(const ActivePerformanceJournal& journal);

// The reattach read of the durable admission window: the original identity
// (session, expected sequence, request id) plus the raw-request fingerprint.
enum class PerformanceAdmissionLookupStatus : std::uint8_t {
  exact,          // window hit with the original payload; receipt returned
  collision,      // window hit with a different payload
  retry_expired,  // expected sequence is older than the retained window
  out_of_order,   // expected sequence is newer than the next admission
  occupied,       // the pending slot belongs to another admission identity
  fresh,          // expected sequence is next and no pending occupies it
  unavailable,    // legacy profile: no durable ledger exists
};

struct PerformanceAdmissionLookup {
  PerformanceAdmissionLookupStatus status{};
  std::optional<PerformanceAdmissionReceipt> receipt;

  bool operator==(const PerformanceAdmissionLookup&) const = default;
};

PerformanceAdmissionLookup lookup_performance_admission(
    const ActivePerformanceJournal& journal,
    const foundation::CommandId& request_id,
    std::uint64_t expected_recording_sequence,
    std::string_view request_fingerprint);

class SequenceJournal {
 public:
  SequenceJournal();
  explicit SequenceJournal(std::shared_ptr<ProjectStoragePlatform> platform);

  foundation::Result<void> prepare_admission(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionPreparation& preparation);
  foundation::Result<void> append_admission_candidate(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionIdentity& identity,
      const SequenceAdmissionCandidate& candidate);
  foundation::Result<void> retain_admission_fence(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionIdentity& identity,
      const SequenceAdmissionFence& fence);
  foundation::Result<void> retain_admission_switch(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionIdentity& identity,
      const SequencePublicationAuthority& authority);
  // Records a same-Pattern live-overlay publication generation (#1513). One
  // durable append per published overlay; the cutoff without a switch then
  // validates against the latest recorded generation.
  foundation::Result<void> retain_admission_overlay(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionIdentity& identity, std::uint64_t publication_generation);
  foundation::Result<void> retain_admission_timing_profile(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionIdentity& identity,
      const SequenceAdmissionTimingProfile& profile);
  foundation::Result<void> close_admission(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionIdentity& identity,
      const SequenceAdmissionClosure& closure);
  foundation::Result<void> transfer_admission_prefix(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionIdentity& identity,
      const SequenceAdmissionTransfer& transfer);
  foundation::Result<void> complete_admission(
      const std::filesystem::path& bundle, foundation::SequenceSessionId session,
      const SequenceAdmissionIdentity& identity);

  foundation::Result<void> begin(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::PatternId pattern_id,
      std::uint8_t bars,
      std::string pattern_fingerprint,
      std::uint64_t expected_revision,
      std::optional<domain::PadSlotId> armed_capture_slot = std::nullopt);
  foundation::Result<ActiveSequenceJournal> read_active(
      const std::filesystem::path& bundle) const;
  foundation::Result<void> append_tail(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::PatternId pattern_id,
      std::uint64_t expected_revision,
      std::uint64_t input_sequence,
      std::span<const domain::PatternEvent> events);
  foundation::Result<SequenceFlushRecord> append_flush(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::CommandId command_id,
      foundation::PatternId pattern_id,
      std::uint64_t expected_revision,
      std::span<const domain::PatternEvent> events);
  foundation::Result<void> complete_flush(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::uint64_t flush_seq,
      std::uint64_t committed_revision,
      std::string pattern_fingerprint);
  foundation::Result<void> set_state(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      SequenceSessionState state);
  foundation::Result<void> rebase(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::uint64_t expected_revision);
  foundation::Result<void> prepare_armed_capture(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::CommandId command_id,
      foundation::AssetId asset_id,
      domain::PadSlotId slot,
      foundation::ArtifactRef artifact,
      std::uint64_t expected_revision);
  foundation::Result<void> complete_armed_capture(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::CommandId command_id,
      domain::PadSlotId slot,
      std::uint64_t committed_revision);
  foundation::Result<void> disarm_capture(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      domain::PadSlotId slot);
  foundation::Result<SequenceCaptureDisarmResult> resolve_capture_disarm(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      domain::PadSlotId slot,
      const SequenceCaptureTruthInspector& inspect_truth);
  foundation::Result<void> switch_pattern(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::PatternId pattern_id,
      std::uint8_t bars,
      std::string pattern_fingerprint,
      std::uint64_t expected_revision);
  foundation::Result<std::filesystem::path> seal(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::string reason);
  foundation::Result<std::vector<SequenceRecoveryCandidate>> list_recoverable(
      const std::filesystem::path& bundle) const;
  foundation::Result<void> remove_active_if_complete(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id);

  foundation::Result<void> begin_performance(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      domain::PerformanceId performance_id,
      std::string performance_fingerprint,
      std::uint64_t expected_revision,
      std::optional<domain::PerformanceInitialLiveState> initial_live_state =
          std::nullopt,
      std::optional<PerformanceTransientCheckpoint> initial_checkpoint =
          std::nullopt);
  foundation::Result<ActivePerformanceJournal> read_active_performance(
      const std::filesystem::path& bundle) const;
  foundation::Result<void> append_performance_tail(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      domain::PerformanceId performance_id,
      std::uint64_t expected_revision,
      std::uint64_t input_sequence,
      std::span<const domain::PerformanceEvent> events,
      std::optional<PerformanceTransientCheckpoint> transient_checkpoint =
          std::nullopt,
      std::optional<PerformanceLaunchAck> last_launch_ack = std::nullopt,
      std::optional<PerformanceAdmissionReceipt> pending_receipt =
          std::nullopt);
  // Writes the headered profile's `admission_complete` metadata record: it
  // matches the unique pending identity and fingerprint, advances
  // `next_recording_sequence` by one and allocates no musical sequence.
  foundation::Result<void> complete_performance_admission(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      const PerformanceAdmissionReceipt& receipt);
  foundation::Result<void> close_performance_transients_for_owner_loss(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id);
  foundation::Result<PerformanceFlushRecord> append_performance_flush(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::CommandId command_id,
      domain::PerformanceId performance_id,
      std::uint64_t expected_revision,
      std::span<const domain::PerformanceEvent> events);
  foundation::Result<void> complete_performance_flush(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::uint64_t flush_seq,
      std::uint64_t committed_revision,
      std::string performance_fingerprint);
  foundation::Result<std::filesystem::path> seal_performance(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::string reason);
  foundation::Result<std::vector<PerformanceRecoveryCandidate>>
  list_performance_recoverable(
      const std::filesystem::path& bundle) const;
  foundation::Result<void> remove_active_performance_if_complete(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id);

 private:
  friend class ProjectStore;

  foundation::Result<void> begin_performance_draft_locked(
      const std::filesystem::path& bundle,
      foundation::CommandId command_id,
      foundation::SequenceSessionId session_id,
      domain::PerformanceId performance_id,
      std::string performance_fingerprint,
      std::uint64_t from_revision,
      std::optional<domain::PerformanceInitialLiveState> initial_live_state =
          std::nullopt,
      std::optional<PerformanceTransientCheckpoint> initial_checkpoint =
          std::nullopt);
  foundation::Result<void> complete_performance_begin_locked(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::uint64_t committed_revision,
      std::string performance_fingerprint);
  foundation::Result<void> stop_performance_locked(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::CommandId request_id);
  foundation::Result<void> prepare_performance_rebase_locked(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      PerformanceRebaseRecord record);
  foundation::Result<void> complete_performance_rebase_locked(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::CommandId command_id,
      std::uint64_t committed_revision,
      std::optional<std::uint16_t> bpm_anchor,
      std::string performance_fingerprint);
  foundation::Result<void> remove_active_performance_locked(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      bool require_stopped);
  foundation::Result<void> append_performance_tail_internal(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      domain::PerformanceId performance_id,
      std::uint64_t expected_revision,
      std::uint64_t input_sequence,
      std::span<const domain::PerformanceEvent> events,
      std::optional<PerformanceTransientCheckpoint> transient_checkpoint,
      std::optional<PerformanceLaunchAck> last_launch_ack,
      std::optional<PerformanceAdmissionReceipt> pending_receipt,
      bool allow_ledger_carryover);
  foundation::Result<void> restore_stopped_performance_locked(
      const std::filesystem::path& bundle,
      const PerformanceRecoveryCandidate& candidate,
      std::uint64_t expected_revision,
      std::string performance_fingerprint,
      foundation::CommandId request_id);

  std::shared_ptr<ProjectStoragePlatform> platform_;
};

}  // namespace lmdj::project_io
