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
    "lmdj.project.v3";

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

struct CommandExecution {
  domain::Command command;
  domain::AppliedCommand outcome;
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

    ImportAssignSampleBytesRequest(
        domain::CommandMeta meta_value,
        domain::PadSlotId slot_value,
        foundation::AssetId asset_id_value,
        std::string media_type_value,
        std::span<const std::byte> bytes_value,
        std::optional<foundation::SequenceSessionId> sequence_session_id_value =
            std::nullopt)
        : meta(std::move(meta_value)),
          slot(slot_value),
          asset_id(std::move(asset_id_value)),
          media_type(std::move(media_type_value)),
          bytes(bytes_value),
          sequence_session_id(std::move(sequence_session_id_value)) {}
  };

  foundation::Result<void> create(
      const std::filesystem::path& bundle,
      const domain::ProjectState& initial);
  foundation::Result<domain::ProjectState> load(
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
  foundation::Result<SequenceCaptureDisarmResult> disarm_sequence_capture(
      const std::filesystem::path& bundle,
      const foundation::SequenceSessionId& session_id,
      domain::PadSlotId slot);
  foundation::Result<std::vector<std::byte>> read_artifact(
      const std::filesystem::path& bundle,
      const foundation::ArtifactRef& artifact) const;

 private:
  std::shared_ptr<ProjectStoragePlatform> platform_;
};

}  // namespace lmdj::project_io
