#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>
#include <lmdj/project_io/storage_platform.hpp>

namespace lmdj::project_io {

inline constexpr std::string_view kProjectBundleConditionResourceLimit =
    "resource_limit";

struct LocalProjectSummary {
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t revision;
  std::uint16_t bpm;
  std::size_t asset_count;
  std::size_t assigned_pad_count;
  std::string bundle_digest;
  friend bool operator==(const LocalProjectSummary&, const LocalProjectSummary&) =
      default;
};

struct BundleImportSession {
  std::string token;
  std::uint64_t expected_index_bytes;
};

struct BundleImportIdentity {
  foundation::ProjectId project_id;
  std::string bundle_digest;
  std::uint32_t entry_count;
};

class ProjectBundleTransfer final {
 public:
  explicit ProjectBundleTransfer(
      std::shared_ptr<ProjectStoragePlatform> platform);
  ~ProjectBundleTransfer();

  ProjectBundleTransfer(const ProjectBundleTransfer&) = delete;
  ProjectBundleTransfer& operator=(const ProjectBundleTransfer&) = delete;
  ProjectBundleTransfer(ProjectBundleTransfer&&) = delete;
  ProjectBundleTransfer& operator=(ProjectBundleTransfer&&) = delete;

  foundation::Result<std::vector<LocalProjectSummary>> list_local_projects(
      const std::filesystem::path& workspace_root) const;
  foundation::Result<BundleImportSession> begin(
      const std::filesystem::path& workspace_root,
      std::string token,
      std::uint64_t index_bytes,
      std::string index_sha256);
  foundation::Result<std::optional<BundleImportIdentity>> append_index(
      std::string_view token,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<void> append_entry(
      std::string_view token,
      std::uint32_t entry_index,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<LocalProjectSummary> commit(std::string_view token);
  foundation::Result<void> abort(std::string_view token);
  foundation::Result<void> cleanup_incomplete(
      const std::filesystem::path& workspace_root);

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::project_io
