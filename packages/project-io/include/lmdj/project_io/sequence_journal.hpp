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
  std::string gesture_id;
  std::uint8_t slot{};
  std::uint64_t onset_tick{};
  std::uint8_t velocity{};

  bool operator==(const PerformanceOpenPadTransient&) const = default;
};

struct PerformanceOpenFxTransient {
  domain::PerformanceFx fx{domain::PerformanceFx::filter};
  std::string gesture_id;
  std::uint16_t effective_value{};
  std::optional<std::uint16_t> pending_value;

  bool operator==(const PerformanceOpenFxTransient&) const = default;
};

struct PerformanceTransientCheckpoint {
  std::vector<PerformanceOpenPadTransient> open_pads;
  std::vector<PerformanceOpenFxTransient> open_fx;
  bool hold{};
  std::uint64_t last_accepted_tick{};

  bool operator==(const PerformanceTransientCheckpoint&) const = default;
};

struct PerformanceLaunchAck {
  foundation::CommandId request_id;
  std::uint8_t pattern_slot{};
  std::uint64_t effective_tick{};

  bool operator==(const PerformanceLaunchAck&) const = default;
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
std::string performance_fingerprint(const domain::Performance& performance);
foundation::Result<PerformanceTransientClosurePreview>
preview_performance_owner_loss(const ActivePerformanceJournal& journal);

class SequenceJournal {
 public:
  SequenceJournal();
  explicit SequenceJournal(std::shared_ptr<ProjectStoragePlatform> platform);

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
      std::uint64_t expected_revision);
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
      std::optional<PerformanceLaunchAck> last_launch_ack = std::nullopt);
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
      std::uint64_t from_revision);
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
  foundation::Result<void> restore_stopped_performance_locked(
      const std::filesystem::path& bundle,
      const PerformanceRecoveryCandidate& candidate,
      std::uint64_t expected_revision,
      std::string performance_fingerprint,
      foundation::CommandId request_id);

  std::shared_ptr<ProjectStoragePlatform> platform_;
};

}  // namespace lmdj::project_io
