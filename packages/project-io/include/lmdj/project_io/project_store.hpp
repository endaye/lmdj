#pragma once

#include <cstddef>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/project_io/storage_platform.hpp>

namespace lmdj::project_io {

struct RecordTakeReplayIdentity {
  domain::CommandMeta meta;
  foundation::TakeId take_id;
  domain::Pattern pattern;
};

struct RecordTakeReplay {
  domain::RecordTake command;
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
  foundation::Result<std::optional<RecordTakeReplay>> replay_record_take(
      const std::filesystem::path& bundle,
      const RecordTakeReplayIdentity& identity);
  foundation::Result<std::vector<std::byte>> read_artifact(
      const std::filesystem::path& bundle,
      const foundation::ArtifactRef& artifact) const;

 private:
  std::shared_ptr<ProjectStoragePlatform> platform_;
};

}  // namespace lmdj::project_io
