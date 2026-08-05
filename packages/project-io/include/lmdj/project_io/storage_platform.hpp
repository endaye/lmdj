#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/foundation/error.hpp>

namespace lmdj::project_io {

inline constexpr std::string_view kStorageConditionProjectBusy =
    "project_busy";
inline constexpr std::string_view kStorageConditionAlreadyExists =
    "already_exists";

class ProjectWriterLease {
 public:
  virtual ~ProjectWriterLease() = default;
};

class ProjectStoragePlatform {
 public:
  virtual ~ProjectStoragePlatform() = default;

  virtual foundation::Result<std::unique_ptr<ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& project_path) = 0;
  virtual foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) = 0;
  virtual foundation::Result<bool> exists(
      const std::filesystem::path& path) const = 0;
  virtual foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const = 0;
  virtual foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const = 0;
  virtual foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) = 0;
  virtual foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) = 0;
  virtual foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> bytes) = 0;
  virtual foundation::Result<void> remove(
      const std::filesystem::path& path) = 0;
  // Returns unsigned-byte-sorted direct child names for regular files only.
  virtual foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const = 0;
  virtual foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const {
    const auto names = list_names(path);
    if (!names.has_value()) {
      return foundation::Result<bool>::failure(names.error());
    }
    return foundation::Result<bool>::success(true);
  }
  virtual foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& root) const = 0;
};

std::shared_ptr<ProjectStoragePlatform>
make_default_project_storage_platform();

std::shared_ptr<ProjectStoragePlatform>
make_native_project_storage_platform(
    const std::filesystem::path& metadata_root);

}  // namespace lmdj::project_io
