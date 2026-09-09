#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>

namespace lmdj::project_io {

inline constexpr std::string_view kProjectWriterContract =
    "lmdj.project.v5";

struct SequenceFlushIdentity {
  foundation::SequenceSessionId session_id;
  std::uint64_t flush_seq{};
  foundation::CommandId command_id;
  foundation::PatternId pattern_id;

  bool operator==(const SequenceFlushIdentity&) const = default;
};

struct SequenceFlushExecution {
  SequenceFlushIdentity identity;
  domain::MergePatternEvents command;
  std::uint64_t committed_revision{};
  domain::AppliedCommand outcome;
};

struct PerformanceFlushIdentity {
  foundation::SequenceSessionId session_id;
  std::uint64_t flush_seq{};
  foundation::CommandId command_id;
  domain::PerformanceId performance_id;

  bool operator==(const PerformanceFlushIdentity&) const = default;
};

struct PerformanceMutation {
  domain::CommandMeta meta;
  domain::PerformanceId performance_id;
  std::vector<domain::PerformanceEvent> events;
};

struct CreatePerformance {
  domain::CommandMeta meta;
  domain::PerformanceId performance_id;
  std::string name;
};

struct RenamePerformance {
  domain::CommandMeta meta;
  domain::PerformanceId performance_id;
  std::string name;
};

struct DeletePerformance {
  domain::CommandMeta meta;
  domain::PerformanceId performance_id;
};

struct PerformanceMutationReceipt {
  std::uint64_t committed_revision{};

  bool operator==(const PerformanceMutationReceipt&) const = default;
};

struct PerformanceFlushExecution {
  PerformanceFlushIdentity identity;
  PerformanceMutation mutation;
  PerformanceMutationReceipt receipt;
  domain::ProjectState state;
  bool replayed{};
};

struct BeginPerformanceDraftRequest {
  domain::CommandMeta meta;
  foundation::SequenceSessionId session_id;
  domain::PerformanceId performance_id;
};

struct PerformanceLifecycleReceipt {
  domain::PerformanceId performance_id;
  std::uint64_t committed_revision{};
  bool replayed{};

  bool operator==(const PerformanceLifecycleReceipt&) const = default;
};

struct PerformanceStopReceipt {
  foundation::CommandId request_id;
  foundation::SequenceSessionId session_id;
  domain::PerformanceId performance_id;
  SequenceSessionState state{SequenceSessionState::stopped};
  std::size_t pending_event_count{};
  bool replayed{};

  bool operator==(const PerformanceStopReceipt&) const = default;
};

struct CommandExecution {
  domain::Command command;
  domain::AppliedCommand outcome;
};

class PerformanceOwnerLock final {
 public:
  ~PerformanceOwnerLock();
  PerformanceOwnerLock(PerformanceOwnerLock&&) noexcept;
  PerformanceOwnerLock& operator=(PerformanceOwnerLock&&) noexcept;

  PerformanceOwnerLock(const PerformanceOwnerLock&) = delete;
  PerformanceOwnerLock& operator=(const PerformanceOwnerLock&) = delete;

 private:
  struct Impl;
  explicit PerformanceOwnerLock(std::unique_ptr<Impl> impl);

  std::unique_ptr<Impl> impl_;
  friend class ProjectStore;
};

struct ImportArtifactExecution {
  domain::ImportAsset command;
  domain::AppliedCommand outcome;
};

class ProjectStore {
 public:
  ProjectStore();
  explicit ProjectStore(std::shared_ptr<ProjectStoragePlatform> platform);

  struct ImportArtifactRequest {
    domain::CommandMeta meta;
    foundation::AssetId asset_id;
    std::filesystem::path source;
    std::string media_type;
  };

  struct ImportArtifactBytesRequest {
    domain::CommandMeta meta;
    foundation::AssetId asset_id;
    std::string media_type;
    std::span<const std::byte> bytes;
  };

  struct ImportAssignSampleBytesRequest {
    domain::CommandMeta meta;
    domain::PadSlotId slot;
    foundation::AssetId asset_id;
    std::string media_type;
    std::span<const std::byte> bytes;
    std::optional<foundation::SequenceSessionId> sequence_session_id;
    std::optional<domain::AssetLineage> lineage;

    ImportAssignSampleBytesRequest(
        domain::CommandMeta meta_value,
        domain::PadSlotId slot_value,
        foundation::AssetId asset_id_value,
        std::string media_type_value,
        std::span<const std::byte> bytes_value,
        std::optional<foundation::SequenceSessionId> sequence_session_id_value =
            std::nullopt,
        std::optional<domain::AssetLineage> lineage_value = std::nullopt)
        : meta(std::move(meta_value)),
          slot(slot_value),
          asset_id(std::move(asset_id_value)),
          media_type(std::move(media_type_value)),
          bytes(bytes_value),
          sequence_session_id(std::move(sequence_session_id_value)),
          lineage(std::move(lineage_value)) {}
  };

  // S11-D8: one atomic install. Every slot's bytes are already validated by
  // the caller; the store publishes the blobs, writes the Assets and the Pad
  // assignments, and settles one manifest, so the whole set lands or none of
  // it does.
  struct SoundSetInstallSlotRequest {
    domain::PadSlotId slot;
    foundation::AssetId asset_id;
    std::string media_type;
    std::span<const std::byte> bytes;
    domain::AssetLineage lineage;
  };

  struct SoundSetInstallRequest {
    domain::CommandMeta meta;
    std::vector<SoundSetInstallSlotRequest> slots;
  };

  foundation::Result<void> create(
      const std::filesystem::path& bundle,
      const domain::ProjectState& initial);
  foundation::Result<domain::ProjectState> load(
      const std::filesystem::path& bundle) const;
  // Reads only committed authoring state under the owner lease. Unlike load,
  // this never recovers interrupted writes or scavenges unpublished files.
  foundation::Result<domain::ProjectState> inspect_committed(
      const std::filesystem::path& bundle) const;
  foundation::Result<domain::AppliedCommand> execute(
      const std::filesystem::path& bundle,
      const domain::Command& command);
  foundation::Result<domain::AppliedCommand> execute(
      const std::filesystem::path& bundle,
      const domain::UpdatePadPlayback& command);
  foundation::Result<domain::AppliedCommand> execute(
      const std::filesystem::path& bundle,
      const domain::ResetPadPlayback& command);
  foundation::Result<CommandExecution> execute_with_identity(
      const std::filesystem::path& bundle,
      const domain::Command& command);
  foundation::Result<domain::AppliedCommand> import_artifact(
      const std::filesystem::path& bundle,
      const ImportArtifactRequest& request);
  foundation::Result<domain::AppliedCommand> import_artifact_bytes(
      const std::filesystem::path& bundle,
      const ImportArtifactBytesRequest& request);
  foundation::Result<domain::AppliedCommand> import_assign_sample_bytes(
      const std::filesystem::path& bundle,
      const ImportAssignSampleBytesRequest& request);
  foundation::Result<domain::AppliedCommand> install_soundset(
      const std::filesystem::path& bundle,
      const SoundSetInstallRequest& request);
  foundation::Result<ImportArtifactExecution>
  import_artifact_with_identity(
      const std::filesystem::path& bundle,
      const ImportArtifactRequest& request);
  foundation::Result<SequenceFlushExecution> execute_sequence_flush(
      const std::filesystem::path& bundle,
      const SequenceFlushIdentity& identity);
  foundation::Result<std::optional<SequenceFlushExecution>>
  replay_sequence_flush(
      const std::filesystem::path& bundle,
      const SequenceFlushIdentity& identity);
  foundation::Result<std::optional<SequenceFlushExecution>>
  replay_sequence_flush(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id,
      const foundation::CommandId& command_id);
  foundation::Result<std::vector<SequenceRecoveryCandidate>>
  reconcile_sequence_recovery(const std::filesystem::path& bundle);
  foundation::Result<PerformanceFlushExecution> execute_performance_flush(
      const std::filesystem::path& bundle,
      const PerformanceFlushIdentity& identity);
  foundation::Result<std::optional<PerformanceFlushExecution>>
  replay_performance_flush(
      const std::filesystem::path& bundle,
      const PerformanceFlushIdentity& identity);
  foundation::Result<std::optional<PerformanceFlushExecution>>
  replay_performance_flush(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id,
      const foundation::CommandId& command_id);
  foundation::Result<domain::AppliedCommand> create_performance(
      const std::filesystem::path& bundle,
      const CreatePerformance& command);
  foundation::Result<domain::AppliedCommand> rename_performance(
      const std::filesystem::path& bundle,
      const RenamePerformance& command);
  foundation::Result<domain::AppliedCommand> delete_performance(
      const std::filesystem::path& bundle,
      const DeletePerformance& command);
  foundation::Result<PerformanceLifecycleReceipt> begin_performance_draft(
      const std::filesystem::path& bundle,
      const BeginPerformanceDraftRequest& request);
  foundation::Result<PerformanceLifecycleReceipt> begin_performance_draft(
      const std::filesystem::path& bundle,
      const domain::CommandMeta& meta,
      const foundation::SequenceSessionId& session_id,
      const domain::PerformanceId& performance_id);
  foundation::Result<std::unique_ptr<PerformanceOwnerLock>>
  acquire_performance_owner_lock(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id);
  foundation::Result<PerformanceStopReceipt> stop_performance_session(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id,
      const foundation::CommandId& request_id);
  foundation::Result<PerformanceLifecycleReceipt> save_performance_draft(
      const std::filesystem::path& bundle,
      const domain::CommandMeta& meta,
      const domain::PerformanceId& performance_id,
      std::string name,
      std::optional<foundation::ArtifactRef> artifact);
  foundation::Result<PerformanceLifecycleReceipt> discard_performance_draft(
      const std::filesystem::path& bundle,
      const domain::CommandMeta& meta,
      const domain::PerformanceId& performance_id);
  foundation::Result<PerformanceLifecycleReceipt> apply_performance_recovery(
      const std::filesystem::path& bundle,
      const domain::CommandMeta& meta,
      const foundation::SequenceSessionId& session_id);
  foundation::Result<PerformanceStopReceipt> discard_performance_recovery(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id,
      const foundation::CommandId& request_id);
  foundation::Result<PerformanceLifecycleReceipt> bind_performance_recording(
      const std::filesystem::path& bundle,
      const domain::CommandMeta& meta,
      const domain::PerformanceId& performance_id,
      const foundation::ArtifactRef& artifact);
  foundation::Result<CommandExecution> execute_performance_rebase(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id,
      const domain::UpdateSequenceSettings& command);
  foundation::Result<std::vector<PerformanceRecoveryCandidate>>
  reconcile_performance_recovery(const std::filesystem::path& bundle);
  foundation::Result<std::vector<PerformanceRecoveryCandidate>>
  list_performance_recovery(const std::filesystem::path& bundle) const;
  foundation::Result<SequenceCaptureDisarmResult> disarm_sequence_capture(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id,
      domain::PadSlotId slot);
  // Read only committed ownership and bytes under one writer lease. Does not
  // recover authoring transactions or scavenge staging.
  foundation::Result<std::vector<std::byte>> read_asset_artifact(
      const std::filesystem::path& bundle,
      const foundation::ProjectId& project_id,
      const foundation::AssetId& asset_id,
      const foundation::ArtifactRef& artifact) const;

  foundation::Result<std::vector<std::byte>> read_artifact(
      const std::filesystem::path& bundle,
      const foundation::ArtifactRef& artifact) const;

 private:
  struct PerformanceOwnerLocks;

  foundation::Result<void> hold_performance_owner_lock(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id);
  void release_performance_owner_lock(
      const std::filesystem::path& bundle) noexcept;

  std::shared_ptr<ProjectStoragePlatform> platform_;
  std::shared_ptr<PerformanceOwnerLocks> performance_owner_locks_;
};

}  // namespace lmdj::project_io
