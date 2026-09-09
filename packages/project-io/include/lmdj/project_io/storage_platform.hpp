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
inline constexpr std::string_view kStorageConditionAtomicPublishUnsupported =
    "atomic_publish_unsupported";
inline constexpr std::string_view kStorageConditionQuotaExceeded =
    "quota_exceeded";
inline constexpr std::string_view kStorageConditionInvalidState =
    "invalid_state";

inline constexpr std::string_view kStorageConditionArtifactMismatch =
    "artifact_mismatch";

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
  // Returns unsigned-byte-sorted direct child names for directories only.
  virtual foundation::Result<std::vector<std::string>> list_directories(
      const std::filesystem::path&) const {
    return foundation::Result<std::vector<std::string>>::failure(
        foundation::Error{
            foundation::ErrorCode::internal_error,
            "storage directory listing is not implemented",
        });
  }
  virtual foundation::Result<void> remove_tree(
      const std::filesystem::path&) {
    return foundation::Result<void>::failure(
        foundation::Error{
            foundation::ErrorCode::internal_error,
            "recursive storage removal is not implemented",
        });
  }
  // Publishes a staged directory at a destination that must not already
  // exist. The caller must hold a writer lease on the *destination path
  // itself* -- a lease on a covering ancestor does not satisfy this -- and
  // must have acquired it before it decided the destination was absent: a
  // platform that cannot rename atomically publishes by copy, and that lease
  // is both what excludes other writers from the half-built destination and
  // what recovers an interrupted publication -- recovery runs when the lease
  // is acquired, so a caller that inspects the destination first sees the
  // leftovers instead of the recovered state. A platform that renames
  // atomically ignores the lease, so the requirement is invisible on native
  // and fails closed on the Web.
  virtual foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path&,
      const std::filesystem::path&) {
    return foundation::Result<void>::failure(
        foundation::Error{
            foundation::ErrorCode::internal_error,
            "atomic storage directory publication is not implemented",
            {{"storage_condition",
              std::string{kStorageConditionAtomicPublishUnsupported}}},
        });
  }
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
