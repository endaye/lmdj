#pragma once

#include <cstddef>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string_view>
#include <vector>

#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/storage_platform.hpp>

namespace lmdj::project_io {

class WorkspaceCacheStore {
 public:
  explicit WorkspaceCacheStore(std::filesystem::path root);
  WorkspaceCacheStore(
      std::filesystem::path root,
      std::shared_ptr<ProjectStoragePlatform> platform);

  foundation::Result<std::optional<std::vector<std::byte>>> read(
      std::string_view key) const;
  foundation::Result<void> write(
      std::string_view key,
      std::span<const std::byte> bytes);
  foundation::Result<void> remove(std::string_view key);

 private:
  std::filesystem::path root_;
  std::shared_ptr<ProjectStoragePlatform> platform_;
};

}  // namespace lmdj::project_io
