#pragma once

#include <filesystem>
#include <string>

#include <lmdj/domain/command_handler.hpp>

namespace lmdj::project_io {

class ProjectStore {
 public:
  struct ImportArtifactRequest {
    domain::CommandMeta meta;
    foundation::AssetId asset_id;
    std::filesystem::path source;
    std::string media_type;
  };

  foundation::Result<void> create(
      const std::filesystem::path& bundle,
      const domain::ProjectState& initial);
  foundation::Result<domain::ProjectState> load(
      const std::filesystem::path& bundle) const;
  foundation::Result<domain::AppliedCommand> execute(
      const std::filesystem::path& bundle,
      const domain::Command& command);
  foundation::Result<domain::AppliedCommand> import_artifact(
      const std::filesystem::path& bundle,
      const ImportArtifactRequest& request);
};

}  // namespace lmdj::project_io
