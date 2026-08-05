#include <lmdj/project_io/storage_platform.hpp>

#include <algorithm>
#include <array>
#include <cerrno>
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <unordered_map>
#include <utility>

#include <picosha2.h>

#include <dirent.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
#include "../testing_hooks.hpp"
#endif

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

Error storage_error(
    std::string message,
    const std::filesystem::path& path,
    int system_error = errno) {
  return Error{
      ErrorCode::io_error,
      std::move(message),
      {
          {"path", path.generic_string()},
          {"system_error", std::strerror(system_error)},
      },
  };
}

Error invalid_storage_path(
    std::string message,
    const std::filesystem::path& path,
    std::string detail = {}) {
  auto details = nlohmann::json{{"path", path.generic_string()}};
  if (!detail.empty()) {
    details["detail"] = std::move(detail);
  }
  return Error{
      ErrorCode::invalid_project,
      std::move(message),
      std::move(details),
  };
}

Error project_busy_error(const std::filesystem::path& path) {
  return Error{
      ErrorCode::io_error,
      "project writer is already acquired",
      {
          {"path", path.generic_string()},
          {"storage_condition", std::string{kStorageConditionProjectBusy}},
      },
  };
}

Error already_exists_error(const std::filesystem::path& path) {
  return Error{
      ErrorCode::io_error,
      "immutable storage destination already exists",
      {
          {"path", path.generic_string()},
          {"storage_condition", std::string{kStorageConditionAlreadyExists}},
          {"system_error", std::strerror(EEXIST)},
      },
  };
}

class OwnedDescriptor {
 public:
  explicit OwnedDescriptor(int descriptor = -1) : descriptor_(descriptor) {}
  OwnedDescriptor(const OwnedDescriptor&) = delete;
  OwnedDescriptor& operator=(const OwnedDescriptor&) = delete;
  OwnedDescriptor(OwnedDescriptor&& other) noexcept
      : descriptor_(std::exchange(other.descriptor_, -1)) {}
  OwnedDescriptor& operator=(OwnedDescriptor&& other) noexcept {
    if (this != &other) {
      reset();
      descriptor_ = std::exchange(other.descriptor_, -1);
    }
    return *this;
  }
  ~OwnedDescriptor() { reset(); }

  int get() const noexcept { return descriptor_; }
  int release() noexcept { return std::exchange(descriptor_, -1); }

 private:
  void reset() noexcept {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }

  int descriptor_;
};

int open_retry(const char* path, int flags) {
  int descriptor = -1;
  do {
    descriptor = ::open(path, flags);
  } while (descriptor < 0 && errno == EINTR);
  return descriptor;
}

int openat_retry(int parent_descriptor, const char* path, int flags) {
  int descriptor = -1;
  do {
    descriptor = ::openat(parent_descriptor, path, flags);
  } while (descriptor < 0 && errno == EINTR);
  return descriptor;
}

int openat_retry(
    int parent_descriptor,
    const char* path,
    int flags,
    mode_t mode) {
  int descriptor = -1;
  do {
    descriptor = ::openat(parent_descriptor, path, flags, mode);
  } while (descriptor < 0 && errno == EINTR);
  return descriptor;
}

int fstat_retry(int descriptor, struct stat* metadata) {
  int result = -1;
  do {
    result = ::fstat(descriptor, metadata);
  } while (result != 0 && errno == EINTR);
  return result;
}

int fchmod_retry(int descriptor, mode_t mode) {
  int result = -1;
  do {
    result = ::fchmod(descriptor, mode);
  } while (result != 0 && errno == EINTR);
  return result;
}

int mkdirat_retry(int parent_descriptor, const char* path, mode_t mode) {
  int result = -1;
  do {
    result = ::mkdirat(parent_descriptor, path, mode);
  } while (result != 0 && errno == EINTR);
  return result;
}

int duplicate_descriptor_retry(int descriptor) {
  int duplicated = -1;
  do {
    duplicated = ::dup(descriptor);
  } while (duplicated < 0 && errno == EINTR);
  return duplicated;
}

int ftruncate_retry(int descriptor, off_t length) {
  int result = -1;
  do {
    result = ::ftruncate(descriptor, length);
  } while (result != 0 && errno == EINTR);
  return result;
}

foundation::Result<std::filesystem::path> normalize_path(
    const std::filesystem::path& path) {
  if (path.empty()) {
    return foundation::Result<std::filesystem::path>::failure(
        invalid_storage_path("storage path is empty", path));
  }
  std::error_code absolute_error;
  auto normalized =
      std::filesystem::absolute(path, absolute_error).lexically_normal();
  if (absolute_error) {
    return foundation::Result<std::filesystem::path>::failure(
        storage_error(
            "storage path could not be normalized",
            path,
            absolute_error.value()));
  }
#if defined(__APPLE__)
  const auto relative = normalized.relative_path();
  if (!relative.empty()) {
    const auto first = *relative.begin();
    if (first == "var" || first == "tmp") {
      normalized = std::filesystem::path{"/private"} / relative;
    }
  }
#endif
  if (normalized != normalized.root_path() && normalized.filename().empty()) {
    normalized = normalized.parent_path();
  }
  return foundation::Result<std::filesystem::path>::success(
      std::move(normalized));
}

foundation::Result<OwnedDescriptor> open_directory_without_symlinks(
    const std::filesystem::path& path) {
  auto normalized_result = normalize_path(path);
  if (!normalized_result.has_value()) {
    return foundation::Result<OwnedDescriptor>::failure(
        normalized_result.error());
  }
  const auto& normalized = normalized_result.value();
  const int root = open_retry("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  if (root < 0) {
    return foundation::Result<OwnedDescriptor>::failure(
        storage_error("storage traversal root could not be opened", path));
  }
  OwnedDescriptor current(root);
  for (const auto& component : normalized.relative_path()) {
    if (component.empty() || component == ".") {
      continue;
    }
    if (component == "..") {
      return foundation::Result<OwnedDescriptor>::failure(
          invalid_storage_path(
              "storage traversal cannot contain parent components",
              path));
    }
    const int next = openat_retry(
        current.get(),
        component.c_str(),
        O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (next < 0) {
      const int open_error = errno;
      if (open_error == ELOOP || open_error == ENOTDIR) {
        return foundation::Result<OwnedDescriptor>::failure(
            invalid_storage_path(
                "storage traversal encountered a symbolic or invalid component",
                path,
                component.generic_string()));
      }
      return foundation::Result<OwnedDescriptor>::failure(
          storage_error(
              "storage directory could not be opened",
              path,
              open_error));
    }
    current = OwnedDescriptor(next);
  }
  return foundation::Result<OwnedDescriptor>::success(std::move(current));
}

struct OpenParent {
  OwnedDescriptor descriptor;
  std::filesystem::path normalized_path;
  std::string name;
};

foundation::Result<OpenParent> open_parent_without_symlinks(
    const std::filesystem::path& path) {
  auto normalized_result = normalize_path(path);
  if (!normalized_result.has_value()) {
    return foundation::Result<OpenParent>::failure(
        normalized_result.error());
  }
  auto normalized = std::move(normalized_result.value());
  const auto filename = normalized.filename();
  if (filename.empty() || filename == "." || filename == "..") {
    return foundation::Result<OpenParent>::failure(
        invalid_storage_path("storage file name is invalid", path));
  }
  auto parent = open_directory_without_symlinks(normalized.parent_path());
  if (!parent.has_value()) {
    return foundation::Result<OpenParent>::failure(parent.error());
  }
  return foundation::Result<OpenParent>::success(
      OpenParent{
          std::move(parent.value()),
          std::move(normalized),
          filename.string(),
      });
}

foundation::Result<void> write_all(
    int descriptor,
    std::span<const std::byte> bytes,
    const std::filesystem::path& path) {
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto written = ::write(
        descriptor,
        bytes.data() + offset,
        bytes.size() - offset);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      return foundation::Result<void>::failure(
          storage_error("storage bytes could not be written", path));
    }
    if (written == 0) {
      return foundation::Result<void>::failure(
          storage_error("storage write made no progress", path, EIO));
    }
    offset += static_cast<std::size_t>(written);
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> sync_descriptor(
    int descriptor,
    const std::filesystem::path& path) {
  while (::fsync(descriptor) != 0) {
    if (errno == EINTR) {
      continue;
    }
    return foundation::Result<void>::failure(
        storage_error("storage bytes could not be flushed", path));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> sync_directory_descriptor(
    int descriptor,
    const std::filesystem::path& path) {
  while (::fsync(descriptor) != 0) {
    if (errno == EINTR) {
      continue;
    }
    return foundation::Result<void>::failure(
        storage_error("storage directory could not be flushed", path));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> lock_descriptor(
    int descriptor,
    int operation,
    const std::filesystem::path& path) {
  while (::flock(descriptor, operation) != 0) {
    if (errno == EINTR) {
      continue;
    }
    return foundation::Result<void>::failure(
        storage_error("storage file lock could not be acquired", path));
  }
  return foundation::Result<void>::success();
}

int fstatat_no_follow_retry(
    int descriptor,
    const char* name,
    struct stat* metadata) {
  int result = -1;
  do {
    result = ::fstatat(
        descriptor,
        name,
        metadata,
        AT_SYMLINK_NOFOLLOW);
  } while (result != 0 && errno == EINTR);
  return result;
}

bool same_identity(const struct stat& left, const struct stat& right) {
  return left.st_dev == right.st_dev && left.st_ino == right.st_ino;
}

bool same_stable_metadata(
    const struct stat& left,
    const struct stat& right) {
#if defined(__APPLE__)
  const bool modification_time_matches =
      left.st_mtimespec.tv_sec == right.st_mtimespec.tv_sec &&
      left.st_mtimespec.tv_nsec == right.st_mtimespec.tv_nsec;
  const bool change_time_matches =
      left.st_ctimespec.tv_sec == right.st_ctimespec.tv_sec &&
      left.st_ctimespec.tv_nsec == right.st_ctimespec.tv_nsec;
#else
  const bool modification_time_matches =
      left.st_mtim.tv_sec == right.st_mtim.tv_sec &&
      left.st_mtim.tv_nsec == right.st_mtim.tv_nsec;
  const bool change_time_matches =
      left.st_ctim.tv_sec == right.st_ctim.tv_sec &&
      left.st_ctim.tv_nsec == right.st_ctim.tv_nsec;
#endif
  const bool replaced_snapshot_was_unlinked =
      left.st_nlink == 1 && right.st_nlink == 0;
  return same_identity(left, right) &&
         left.st_size == right.st_size &&
         left.st_mode == right.st_mode &&
         left.st_uid == right.st_uid &&
         left.st_gid == right.st_gid &&
         modification_time_matches &&
         (change_time_matches || replaced_snapshot_was_unlinked);
}

foundation::Result<void> verify_named_identity(
    int parent_descriptor,
    std::string_view name,
    const struct stat& expected,
    const std::filesystem::path& path) {
  struct stat observed {};
  if (fstatat_no_follow_retry(
          parent_descriptor,
          std::string{name}.c_str(),
          &observed) != 0) {
    return foundation::Result<void>::failure(
        storage_error("storage sibling identity could not be verified", path));
  }
  if (!S_ISREG(observed.st_mode) || !same_identity(observed, expected)) {
    return foundation::Result<void>::failure(
        invalid_storage_path(
            "storage sibling identity changed before publication",
            path));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> unlink_owned_sibling(
    int parent_descriptor,
    std::string_view name,
    const struct stat& expected,
    const std::filesystem::path& path) {
  const auto identity = verify_named_identity(
      parent_descriptor,
      name,
      expected,
      path);
  if (!identity.has_value()) {
    return identity;
  }
  int result = -1;
  do {
    result = ::unlinkat(parent_descriptor, std::string{name}.c_str(), 0);
  } while (result != 0 && errno == EINTR);
  if (result != 0) {
    return foundation::Result<void>::failure(
        storage_error("storage sibling could not be removed", path));
  }
  return foundation::Result<void>::success();
}

foundation::Result<std::string> opaque_identifier(
    const std::filesystem::path& path) {
  std::array<unsigned char, 16> random_bytes{};
  const int random_descriptor =
      open_retry("/dev/urandom", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (random_descriptor < 0) {
    return foundation::Result<std::string>::failure(
        storage_error("secure temporary identity source could not be opened", path));
  }
  OwnedDescriptor random(random_descriptor);
  std::size_t offset = 0;
  while (offset < random_bytes.size()) {
    const auto count = ::read(
        random.get(),
        random_bytes.data() + offset,
        random_bytes.size() - offset);
    if (count < 0) {
      if (errno == EINTR) {
        continue;
      }
      return foundation::Result<std::string>::failure(
          storage_error("secure temporary identity could not be read", path));
    }
    if (count == 0) {
      return foundation::Result<std::string>::failure(
          storage_error("secure temporary identity source ended", path, EIO));
    }
    offset += static_cast<std::size_t>(count);
  }
  constexpr std::string_view digits = "0123456789abcdef";
  std::string encoded(random_bytes.size() * 2, '0');
  for (std::size_t index = 0; index < random_bytes.size(); ++index) {
    encoded.at(index * 2) = digits.at(random_bytes.at(index) >> 4U);
    encoded.at(index * 2 + 1) = digits.at(random_bytes.at(index) & 0x0fU);
  }
  return foundation::Result<std::string>::success(std::move(encoded));
}

bool unsigned_byte_less(const std::string& left, const std::string& right) {
  return std::lexicographical_compare(
      left.begin(),
      left.end(),
      right.begin(),
      right.end(),
      [](char left_byte, char right_byte) {
        return static_cast<unsigned char>(left_byte) <
               static_cast<unsigned char>(right_byte);
      });
}

foundation::Result<void> validate_directory_contents(
    int descriptor,
    const std::filesystem::path& path) {
  const int duplicated = duplicate_descriptor_retry(descriptor);
  if (duplicated < 0) {
    return foundation::Result<void>::failure(
        storage_error("managed storage directory could not be enumerated", path));
  }
  DIR* stream = ::fdopendir(duplicated);
  if (stream == nullptr) {
    const int open_error = errno;
    ::close(duplicated);
    return foundation::Result<void>::failure(
        storage_error(
            "managed storage directory could not be enumerated",
            path,
            open_error));
  }

  while (true) {
    errno = 0;
    const auto* entry = ::readdir(stream);
    if (entry == nullptr) {
      if (errno == EINTR) {
        continue;
      }
      break;
    }
    const std::string name{entry->d_name};
    if (name == "." || name == "..") {
      continue;
    }
    const auto entry_path = path / name;
    struct stat metadata {};
    if (fstatat_no_follow_retry(
            descriptor,
            name.c_str(),
            &metadata) != 0) {
      const int stat_error = errno;
      ::closedir(stream);
      return foundation::Result<void>::failure(
          storage_error(
              "managed storage entry could not be inspected",
              entry_path,
              stat_error));
    }
    if (S_ISLNK(metadata.st_mode)) {
      ::closedir(stream);
      return foundation::Result<void>::failure(
          invalid_storage_path(
              "managed storage tree contains a symbolic link",
              entry_path));
    }
    if (S_ISDIR(metadata.st_mode)) {
      const int child_descriptor = openat_retry(
          descriptor,
          name.c_str(),
          O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
      if (child_descriptor < 0) {
        const int open_error = errno;
        ::closedir(stream);
        if (open_error == ELOOP || open_error == ENOTDIR) {
          return foundation::Result<void>::failure(
              invalid_storage_path(
                  "managed storage tree changed to a symbolic or invalid directory",
                  entry_path));
        }
        return foundation::Result<void>::failure(
            storage_error(
                "managed storage directory could not be opened",
                entry_path,
                open_error));
      }
      OwnedDescriptor child(child_descriptor);
      const auto validated =
          validate_directory_contents(child.get(), entry_path);
      if (!validated.has_value()) {
        ::closedir(stream);
        return validated;
      }
    } else if (!S_ISREG(metadata.st_mode)) {
      ::closedir(stream);
      return foundation::Result<void>::failure(
          invalid_storage_path(
              "managed storage tree contains a special file",
              entry_path));
    }
  }
  const int read_error = errno;
  if (::closedir(stream) != 0 && read_error == 0) {
    return foundation::Result<void>::failure(
        storage_error("managed storage directory could not be closed", path));
  }
  if (read_error != 0) {
    return foundation::Result<void>::failure(
        storage_error(
            "managed storage directory could not be enumerated",
            path,
            read_error));
  }
  return foundation::Result<void>::success();
}

enum class ManagedFileKind {
  generic,
  artifact,
  transaction,
  checkpoint,
  active_journal,
  sealed_recovery,
  manifest,
};

ManagedFileKind managed_file_kind(const std::filesystem::path& path) {
  const auto parent = path.parent_path();
  const auto grandparent = parent.parent_path();
  if (parent.filename() == "assets" && path.extension() == ".wav") {
    return ManagedFileKind::artifact;
  }
  if (parent.filename() == "transactions" &&
      grandparent.filename() == "history" && path.extension() == ".json") {
    return ManagedFileKind::transaction;
  }
  if (parent.filename() == "checkpoints" &&
      grandparent.filename() == "history" && path.extension() == ".json") {
    return ManagedFileKind::checkpoint;
  }
  if (parent.filename() == "active" &&
      grandparent.filename() == "recovery" && path.extension() == ".jsonl") {
    return ManagedFileKind::active_journal;
  }
  if (parent.filename() == "sealed" &&
      grandparent.filename() == "recovery" && path.extension() == ".json") {
    return ManagedFileKind::sealed_recovery;
  }
  if (path.filename() == "manifest.json") {
    return ManagedFileKind::manifest;
  }
  return ManagedFileKind::generic;
}

foundation::Result<std::string> temporary_sibling_name(
    std::string_view destination,
    const std::filesystem::path& path) {
  auto identifier = opaque_identifier(path);
  if (!identifier.has_value()) {
    return foundation::Result<std::string>::failure(identifier.error());
  }
  return foundation::Result<std::string>::success(
      std::string{destination} + ".tmp." + identifier.value());
}

#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
std::optional<testing::FaultPoint> immutable_sync_fault(
    ManagedFileKind kind) {
  switch (kind) {
    case ManagedFileKind::artifact:
      return testing::FaultPoint::artifact_temp_sync;
    case ManagedFileKind::transaction:
      return testing::FaultPoint::transaction_temp_sync;
    case ManagedFileKind::checkpoint:
      return testing::FaultPoint::checkpoint_temp_sync;
    case ManagedFileKind::active_journal:
      return testing::FaultPoint::active_journal_sync;
    default:
      return std::nullopt;
  }
}

std::optional<testing::FaultPoint> immutable_publish_fault(
    ManagedFileKind kind) {
  switch (kind) {
    case ManagedFileKind::artifact:
      return testing::FaultPoint::artifact_publish;
    case ManagedFileKind::transaction:
      return testing::FaultPoint::transaction_publish;
    case ManagedFileKind::checkpoint:
      return testing::FaultPoint::checkpoint_publish;
    default:
      return std::nullopt;
  }
}

foundation::Result<void> invoke_fault(
    const std::optional<testing::FaultPoint>& point,
    const std::filesystem::path& path) {
  return point.has_value()
             ? testing::detail::invoke_fault(*point, path)
             : foundation::Result<void>::success();
}
#endif

struct NativeWriterState {
  enum class Status { acquiring, acquired, failed };

  ~NativeWriterState() {
    if (descriptor >= 0) {
      ::flock(descriptor, LOCK_UN);
      ::close(descriptor);
    }
  }

  Status status = Status::acquiring;
  int descriptor = -1;
  std::optional<Error> error;
};

class NativeWriterLease final : public ProjectWriterLease {
 public:
  explicit NativeWriterLease(std::shared_ptr<NativeWriterState> state)
      : state_(std::move(state)) {}

 private:
  std::shared_ptr<NativeWriterState> state_;
};

std::filesystem::path default_metadata_root() {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  std::error_code test_temporary_error;
  auto test_temporary =
      std::filesystem::temp_directory_path(test_temporary_error);
  if (test_temporary_error || !test_temporary.is_absolute()) {
    test_temporary = "/tmp";
  }
  return test_temporary /
         ("lmdj-project-io-tests-" +
          std::to_string(static_cast<unsigned long>(::geteuid())) + "-" +
          std::to_string(static_cast<unsigned long>(::getpid()))) /
         "project-writer-leases";
#else
#if defined(__APPLE__)
  if (const char* home = std::getenv("HOME");
      home != nullptr && home[0] != '\0') {
    const std::filesystem::path home_path{home};
    if (home_path.is_absolute()) {
      return home_path / "Library/Application Support/LMDJ" /
             "project-writer-leases";
    }
  }
#else
  if (const char* state = std::getenv("XDG_STATE_HOME");
      state != nullptr && state[0] != '\0') {
    const std::filesystem::path state_path{state};
    if (state_path.is_absolute()) {
      return state_path / "lmdj/project-writer-leases";
    }
  }
  if (const char* home = std::getenv("HOME");
      home != nullptr && home[0] != '\0') {
    const std::filesystem::path home_path{home};
    if (home_path.is_absolute()) {
      return home_path / ".local/state/lmdj/project-writer-leases";
    }
  }
#endif
  std::error_code temporary_error;
  auto temporary = std::filesystem::temp_directory_path(temporary_error);
  if (temporary_error || !temporary.is_absolute()) {
    temporary = "/tmp";
  }
  return temporary /
         ("lmdj-" + std::to_string(static_cast<unsigned long>(::geteuid()))) /
         "project-writer-leases";
#endif
}

std::string project_lease_name(const std::filesystem::path& normalized_path) {
  return picosha2::hash256_hex_string(normalized_path.generic_string()) +
         ".lock";
}

bool path_contains(
    const std::filesystem::path& parent,
    const std::filesystem::path& candidate) {
  auto parent_component = parent.begin();
  auto candidate_component = candidate.begin();
  while (parent_component != parent.end()) {
    if (candidate_component == candidate.end() ||
        *parent_component != *candidate_component) {
      return false;
    }
    ++parent_component;
    ++candidate_component;
  }
  return true;
}

foundation::Result<int> acquire_native_descriptor(
    const std::filesystem::path& project_path,
    const std::filesystem::path& metadata_root) {
  auto directory = open_directory_without_symlinks(metadata_root);
  if (!directory.has_value()) {
    return foundation::Result<int>::failure(directory.error());
  }
  struct stat root_identity {};
  if (fstat_retry(directory.value().get(), &root_identity) != 0 ||
      !S_ISDIR(root_identity.st_mode) ||
      root_identity.st_uid != ::geteuid()) {
    return foundation::Result<int>::failure(
        invalid_storage_path(
            "project lease metadata root is not an owned directory",
            metadata_root));
  }
  if (fchmod_retry(directory.value().get(), 0700) != 0) {
    return foundation::Result<int>::failure(
        storage_error(
            "project lease metadata root could not be made private",
            metadata_root));
  }
  struct stat private_root {};
  if (fstat_retry(directory.value().get(), &private_root) != 0 ||
      !S_ISDIR(private_root.st_mode) ||
      private_root.st_uid != ::geteuid() ||
      !same_identity(private_root, root_identity) ||
      (private_root.st_mode & 0777) != 0700) {
    return foundation::Result<int>::failure(
        invalid_storage_path(
            "project lease metadata root is not private and stable",
            metadata_root));
  }
  const auto lease_name = project_lease_name(project_path);
  const auto lease_path = metadata_root / lease_name;
  const int descriptor = openat_retry(
      directory.value().get(),
      lease_name.c_str(),
      O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW,
      0600);
  if (descriptor < 0) {
    return foundation::Result<int>::failure(
        storage_error(
            "project lock file could not be opened",
            lease_path));
  }
  struct stat metadata {};
  if (fstat_retry(descriptor, &metadata) != 0 ||
      !S_ISREG(metadata.st_mode) ||
      metadata.st_uid != ::geteuid() ||
      metadata.st_nlink != 1) {
    const auto error = invalid_storage_path(
        "project lock is not an owned single-link regular file",
        lease_path);
    ::close(descriptor);
    return foundation::Result<int>::failure(error);
  }
  if (fchmod_retry(descriptor, 0600) != 0) {
    const auto error = storage_error(
        "project lock could not be made private",
        lease_path);
    ::close(descriptor);
    return foundation::Result<int>::failure(error);
  }
  struct stat private_metadata {};
  if (fstat_retry(descriptor, &private_metadata) != 0 ||
      !S_ISREG(private_metadata.st_mode) ||
      private_metadata.st_uid != ::geteuid() ||
      private_metadata.st_nlink != 1 ||
      !same_identity(private_metadata, metadata) ||
      (private_metadata.st_mode & 0777) != 0600) {
    const auto error = invalid_storage_path(
        "project lock is not a private stable regular file",
        lease_path);
    ::close(descriptor);
    return foundation::Result<int>::failure(error);
  }
  metadata = private_metadata;
  while (::flock(descriptor, LOCK_EX | LOCK_NB) != 0) {
    if (errno == EINTR) {
      continue;
    }
    if (errno == EWOULDBLOCK || errno == EAGAIN) {
      const auto error = project_busy_error(project_path);
      ::close(descriptor);
      return foundation::Result<int>::failure(error);
    }
    const auto error = storage_error(
        "project lock could not be acquired",
        lease_path);
    ::close(descriptor);
    return foundation::Result<int>::failure(error);
  }
  struct stat named_metadata {};
  if (fstatat_no_follow_retry(
          directory.value().get(),
          lease_name.c_str(),
          &named_metadata) != 0 ||
      !S_ISREG(named_metadata.st_mode) ||
      !same_identity(named_metadata, metadata)) {
    ::flock(descriptor, LOCK_UN);
    ::close(descriptor);
    return foundation::Result<int>::failure(
        invalid_storage_path(
            "project lock identity changed while acquiring",
            lease_path));
  }
  const auto synced = sync_directory_descriptor(directory.value().get(), metadata_root);
  if (!synced.has_value()) {
    ::flock(descriptor, LOCK_UN);
    ::close(descriptor);
    return foundation::Result<int>::failure(synced.error());
  }
  return foundation::Result<int>::success(descriptor);
}

foundation::Result<std::optional<mode_t>> path_mode_without_symlinks(
    const std::filesystem::path& path) {
  auto normalized_result = normalize_path(path);
  if (!normalized_result.has_value()) {
    return foundation::Result<std::optional<mode_t>>::failure(
        normalized_result.error());
  }
  const auto& normalized = normalized_result.value();
  if (normalized == normalized.root_path()) {
    return foundation::Result<std::optional<mode_t>>::success(
        std::optional<mode_t>{static_cast<mode_t>(S_IFDIR)});
  }

  const int root = open_retry("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  if (root < 0) {
    return foundation::Result<std::optional<mode_t>>::failure(
        storage_error("storage traversal root could not be opened", path));
  }
  OwnedDescriptor current(root);
  const auto relative = normalized.relative_path();
  auto component = relative.begin();
  const auto component_end = relative.end();
  if (component == component_end) {
    return foundation::Result<std::optional<mode_t>>::failure(
        invalid_storage_path("storage file name is invalid", path));
  }
  auto next_component = component;
  ++next_component;
  while (next_component != component_end) {
    const int next = openat_retry(
        current.get(),
        component->c_str(),
        O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (next < 0) {
      const int open_error = errno;
      if (open_error == ENOENT) {
        return foundation::Result<std::optional<mode_t>>::success(
            std::optional<mode_t>{});
      }
      if (open_error == ELOOP || open_error == ENOTDIR) {
        return foundation::Result<std::optional<mode_t>>::failure(
            invalid_storage_path(
                "storage traversal encountered a symbolic or invalid component",
                path,
                component->generic_string()));
      }
      return foundation::Result<std::optional<mode_t>>::failure(
          storage_error(
              "storage directory could not be opened",
              path,
              open_error));
    }
    current = OwnedDescriptor(next);
    component = next_component;
    ++next_component;
  }

  struct stat metadata {};
  if (fstatat_no_follow_retry(
          current.get(),
          component->c_str(),
          &metadata) != 0) {
    if (errno == ENOENT) {
      return foundation::Result<std::optional<mode_t>>::success(
          std::optional<mode_t>{});
    }
    return foundation::Result<std::optional<mode_t>>::failure(
        storage_error("storage path could not be inspected", path));
  }
  if (S_ISLNK(metadata.st_mode)) {
    return foundation::Result<std::optional<mode_t>>::failure(
        invalid_storage_path("storage path is a symbolic link", path));
  }
  return foundation::Result<std::optional<mode_t>>::success(
      std::optional<mode_t>{metadata.st_mode});
}

class NativeProjectStoragePlatform final : public ProjectStoragePlatform {
 public:
  explicit NativeProjectStoragePlatform(std::filesystem::path metadata_root)
      : metadata_root_(std::move(metadata_root)) {}

  foundation::Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(
      const std::filesystem::path& project_path) override {
    auto normalized = normalize_path(project_path);
    if (!normalized.has_value()) {
      return foundation::Result<std::unique_ptr<ProjectWriterLease>>::failure(
          normalized.error());
    }
    const auto key = normalized.value().generic_string();
    std::shared_ptr<NativeWriterState> state;
    {
      std::unique_lock lock(writer_mutex_);
      const auto found = writers_.find(key);
      if (found != writers_.end()) {
        state = found->second.lock();
      }
      if (state != nullptr) {
        writer_condition_.wait(
            lock,
            [&state]() {
              return state->status != NativeWriterState::Status::acquiring;
            });
        if (state->status == NativeWriterState::Status::acquired) {
          return foundation::Result<std::unique_ptr<ProjectWriterLease>>::success(
              std::make_unique<NativeWriterLease>(state));
        }
        return foundation::Result<std::unique_ptr<ProjectWriterLease>>::failure(
            *state->error);
      }
      state = std::make_shared<NativeWriterState>();
      writers_[key] = state;
    }

    auto normalized_metadata = normalize_path(metadata_root_);
    foundation::Result<int> acquired = foundation::Result<int>::failure(
        invalid_storage_path(
            "project lease metadata root is invalid",
            metadata_root_));
    if (normalized_metadata.has_value() &&
        !path_contains(normalized.value(), normalized_metadata.value())) {
      const auto ensured = ensure_directory(normalized_metadata.value());
      if (ensured.has_value()) {
        acquired = acquire_native_descriptor(
            normalized.value(),
            normalized_metadata.value());
      } else {
        acquired = foundation::Result<int>::failure(ensured.error());
      }
    }
    {
      std::lock_guard lock(writer_mutex_);
      if (acquired.has_value()) {
        state->descriptor = acquired.value();
        state->status = NativeWriterState::Status::acquired;
      } else {
        state->error = acquired.error();
        state->status = NativeWriterState::Status::failed;
        const auto found = writers_.find(key);
        if (found != writers_.end() && found->second.lock() == state) {
          writers_.erase(found);
        }
      }
    }
    writer_condition_.notify_all();
    if (!acquired.has_value()) {
      return foundation::Result<std::unique_ptr<ProjectWriterLease>>::failure(
          acquired.error());
    }
    return foundation::Result<std::unique_ptr<ProjectWriterLease>>::success(
        std::make_unique<NativeWriterLease>(std::move(state)));
  }

  foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    auto normalized_result = normalize_path(path);
    if (!normalized_result.has_value()) {
      return foundation::Result<void>::failure(normalized_result.error());
    }
    const auto& normalized = normalized_result.value();
    const int root = open_retry("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (root < 0) {
      return foundation::Result<void>::failure(
          storage_error("storage traversal root could not be opened", path));
    }
    OwnedDescriptor current(root);
    std::filesystem::path traversed{"/"};
    for (const auto& component : normalized.relative_path()) {
      if (component.empty() || component == ".") {
        continue;
      }
      traversed /= component;
      int next = openat_retry(
          current.get(),
          component.c_str(),
          O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
      if (next < 0 && errno == ENOENT) {
        if (mkdirat_retry(current.get(), component.c_str(), 0755) != 0 &&
            errno != EEXIST) {
          return foundation::Result<void>::failure(
              storage_error(
                  "storage directory could not be created",
                  traversed));
        }
        const auto synced = sync_directory_descriptor(
            current.get(), traversed.parent_path());
        if (!synced.has_value()) {
          return synced;
        }
        next = openat_retry(
            current.get(),
            component.c_str(),
            O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
      }
      if (next < 0) {
        const int open_error = errno;
        if (open_error == ELOOP || open_error == ENOTDIR) {
          return foundation::Result<void>::failure(
              invalid_storage_path(
                  "storage directory contains a symbolic or invalid component",
                  traversed));
        }
        return foundation::Result<void>::failure(
            storage_error(
                "storage directory could not be opened",
                traversed,
                open_error));
      }
      current = OwnedDescriptor(next);
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    const auto mode = path_mode_without_symlinks(path);
    if (!mode.has_value()) {
      return foundation::Result<bool>::failure(mode.error());
    }
    return foundation::Result<bool>::success(mode.value().has_value());
  }

  foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const override {
    const auto mode = path_mode_without_symlinks(path);
    if (!mode.has_value()) {
      return foundation::Result<bool>::failure(mode.error());
    }
    return foundation::Result<bool>::success(
        mode.value().has_value() && S_ISDIR(mode.value().value()));
  }

  foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    auto opened = open_regular_file(path);
    if (!opened.has_value()) {
      return foundation::Result<std::uint64_t>::failure(opened.error());
    }
    const auto& metadata = opened.value().second;
    if (metadata.st_size < 0) {
      return foundation::Result<std::uint64_t>::failure(
          storage_error("storage byte length is invalid", path));
    }
    return foundation::Result<std::uint64_t>::success(
        static_cast<std::uint64_t>(metadata.st_size));
  }

  foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    auto opened = open_regular_file(path);
    if (!opened.has_value()) {
      return foundation::Result<std::vector<std::byte>>::failure(
          opened.error());
    }
    auto descriptor = std::move(opened.value().first);
    const auto before = opened.value().second;
    if (before.st_size < 0 ||
        static_cast<std::uintmax_t>(before.st_size) >
            std::numeric_limits<std::size_t>::max()) {
      return foundation::Result<std::vector<std::byte>>::failure(
          storage_error("storage file is too large to read", path));
    }
    std::vector<std::byte> bytes(static_cast<std::size_t>(before.st_size));
    std::size_t offset = 0;
    while (offset < bytes.size()) {
      const auto count = ::pread(
          descriptor.get(),
          bytes.data() + offset,
          bytes.size() - offset,
          static_cast<off_t>(offset));
      if (count < 0) {
        if (errno == EINTR) {
          continue;
        }
        return foundation::Result<std::vector<std::byte>>::failure(
            storage_error("storage file could not be read completely", path));
      }
      if (count == 0) {
        return foundation::Result<std::vector<std::byte>>::failure(
            storage_error("storage file ended during complete read", path));
      }
      offset += static_cast<std::size_t>(count);
    }
    struct stat after {};
    if (fstat_retry(descriptor.get(), &after) != 0) {
      return foundation::Result<std::vector<std::byte>>::failure(
          storage_error("storage metadata could not be revalidated", path));
    }
    if (!S_ISREG(after.st_mode) ||
        !same_stable_metadata(before, after)) {
      return foundation::Result<std::vector<std::byte>>::failure(
          storage_error("storage file changed during complete read", path));
    }
    return foundation::Result<std::vector<std::byte>>::success(
        std::move(bytes));
  }

  foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    auto parent = open_parent_without_symlinks(path);
    if (!parent.has_value()) {
      return foundation::Result<void>::failure(parent.error());
    }
    struct stat existing {};
    if (fstatat_no_follow_retry(
            parent.value().descriptor.get(),
            parent.value().name.c_str(),
            &existing) == 0) {
      if (S_ISLNK(existing.st_mode)) {
        return foundation::Result<void>::failure(
            invalid_storage_path(
                "immutable storage destination is a symbolic link",
                path));
      }
      return foundation::Result<void>::failure(
          already_exists_error(path));
    }
    if (errno != ENOENT) {
      return foundation::Result<void>::failure(
          storage_error("immutable storage destination could not be inspected", path));
    }

#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    const auto kind = managed_file_kind(parent.value().normalized_path);
#endif
    std::string sibling;
    int descriptor = -1;
    for (std::size_t attempt = 0; attempt < 128 && descriptor < 0; ++attempt) {
      auto candidate = temporary_sibling_name(parent.value().name, path);
      if (!candidate.has_value()) {
        return foundation::Result<void>::failure(candidate.error());
      }
      sibling = std::move(candidate.value());
      descriptor = openat_retry(
          parent.value().descriptor.get(),
          sibling.c_str(),
          O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
          0600);
      if (descriptor < 0 && errno != EEXIST) {
        return foundation::Result<void>::failure(
            storage_error(
                "immutable storage sibling could not be created",
                parent.value().normalized_path.parent_path() / sibling));
      }
    }
    if (descriptor < 0) {
      return foundation::Result<void>::failure(
          storage_error("immutable storage sibling name space is exhausted", path));
    }
    const auto sibling_path =
        parent.value().normalized_path.parent_path() / sibling;
    OwnedDescriptor file(descriptor);
    struct stat owned_identity {};
    if (fstat_retry(file.get(), &owned_identity) != 0 ||
        !S_ISREG(owned_identity.st_mode)) {
      return foundation::Result<void>::failure(
          storage_error("immutable storage identity could not be captured", sibling_path));
    }
    const auto locked = lock_descriptor(file.get(), LOCK_EX, sibling_path);
    if (!locked.has_value()) {
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? locked : cleanup;
    }
    if (fchmod_retry(file.get(), 0644) != 0) {
      const auto result = foundation::Result<void>::failure(
          storage_error("immutable storage permissions could not be set", sibling_path));
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? result : cleanup;
    }
    struct stat permissioned_identity {};
    if (fstat_retry(file.get(), &permissioned_identity) != 0 ||
        !S_ISREG(permissioned_identity.st_mode) ||
        !same_identity(permissioned_identity, owned_identity)) {
      const auto result = foundation::Result<void>::failure(
          storage_error("immutable storage identity could not be captured", sibling_path));
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? result : cleanup;
    }
    auto result = write_all(file.get(), bytes, path);
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    if (result.has_value()) {
      result = invoke_fault(immutable_sync_fault(kind), sibling_path);
    }
#endif
    if (result.has_value()) {
      result = sync_descriptor(file.get(), path);
    }
    if (result.has_value()) {
      struct stat synchronized_identity {};
      if (fstat_retry(file.get(), &synchronized_identity) != 0 ||
          !S_ISREG(synchronized_identity.st_mode) ||
          !same_identity(synchronized_identity, owned_identity) ||
          synchronized_identity.st_size != static_cast<off_t>(bytes.size())) {
        result = foundation::Result<void>::failure(
            storage_error("immutable storage identity could not be verified", path));
      }
    }
    if (!result.has_value()) {
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? result : cleanup;
    }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    result = invoke_fault(immutable_publish_fault(kind), path);
    if (!result.has_value()) {
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? result : cleanup;
    }
#endif
    const auto source_identity = verify_named_identity(
        parent.value().descriptor.get(),
        sibling,
        owned_identity,
        sibling_path);
    if (!source_identity.has_value()) {
      return source_identity;
    }
    int linked = -1;
    do {
      linked = ::linkat(
          parent.value().descriptor.get(),
          sibling.c_str(),
          parent.value().descriptor.get(),
          parent.value().name.c_str(),
          0);
    } while (linked != 0 && errno == EINTR);
    if (linked != 0) {
      const int link_error = errno;
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      if (!cleanup.has_value()) {
        return cleanup;
      }
      struct stat collision {};
      if (link_error == EEXIST &&
          fstatat_no_follow_retry(
              parent.value().descriptor.get(),
              parent.value().name.c_str(),
              &collision) == 0 &&
          S_ISLNK(collision.st_mode)) {
        return foundation::Result<void>::failure(
            invalid_storage_path(
                "immutable storage destination is a symbolic link",
                path));
      }
      if (link_error == EEXIST) {
        return foundation::Result<void>::failure(
            already_exists_error(path));
      }
      return foundation::Result<void>::failure(
          storage_error(
              "immutable storage file could not be published",
              path,
              link_error));
    }
    struct stat published {};
    if (fstatat_no_follow_retry(
            parent.value().descriptor.get(),
            parent.value().name.c_str(),
            &published) != 0 ||
        !S_ISREG(published.st_mode) ||
        !same_identity(published, owned_identity)) {
      return foundation::Result<void>::failure(
          invalid_storage_path(
              "immutable storage publication identity changed",
              path));
    }
    const auto removed = unlink_owned_sibling(
        parent.value().descriptor.get(),
        sibling,
        owned_identity,
        sibling_path);
    if (!removed.has_value()) {
      return removed;
    }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    if (kind == ManagedFileKind::sealed_recovery) {
      result = testing::detail::invoke_fault(
          testing::FaultPoint::sealed_directory_sync,
          parent.value().normalized_path.parent_path());
      if (!result.has_value()) {
        return result;
      }
    }
#endif
    const int released = file.release();
    const int close_result = ::close(released);
    const auto directory_sync = sync_directory_descriptor(
        parent.value().descriptor.get(),
        parent.value().normalized_path.parent_path());
    if (!directory_sync.has_value()) {
      return directory_sync;
    }
    if (close_result != 0) {
      return foundation::Result<void>::failure(
          storage_error("immutable storage file could not be closed", path));
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    auto parent = open_parent_without_symlinks(path);
    if (!parent.has_value()) {
      return foundation::Result<void>::failure(parent.error());
    }
    struct stat destination {};
    if (fstatat_no_follow_retry(
            parent.value().descriptor.get(),
            parent.value().name.c_str(),
            &destination) == 0) {
      if (S_ISLNK(destination.st_mode)) {
        return foundation::Result<void>::failure(
            invalid_storage_path(
                "replacement destination is a symbolic link",
                path));
      }
      if (!S_ISREG(destination.st_mode)) {
        return foundation::Result<void>::failure(
            invalid_storage_path(
                "replacement destination is not a regular file",
                path));
      }
    } else if (errno != ENOENT) {
      return foundation::Result<void>::failure(
          storage_error(
              "replacement destination could not be inspected",
              path));
    }

    std::string sibling;
    int descriptor = -1;
    for (std::size_t attempt = 0; attempt < 128 && descriptor < 0; ++attempt) {
      auto candidate = temporary_sibling_name(parent.value().name, path);
      if (!candidate.has_value()) {
        return foundation::Result<void>::failure(candidate.error());
      }
      sibling = std::move(candidate.value());
      descriptor = openat_retry(
          parent.value().descriptor.get(),
          sibling.c_str(),
          O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
          0600);
      if (descriptor < 0 && errno != EEXIST) {
        return foundation::Result<void>::failure(
            storage_error("replacement sibling could not be created", path));
      }
    }
    if (descriptor < 0) {
      return foundation::Result<void>::failure(
          storage_error("replacement sibling name space is exhausted", path));
    }
    const auto sibling_path =
        parent.value().normalized_path.parent_path() / sibling;
    OwnedDescriptor file(descriptor);
    struct stat owned_identity {};
    if (fstat_retry(file.get(), &owned_identity) != 0 ||
        !S_ISREG(owned_identity.st_mode)) {
      return foundation::Result<void>::failure(
          storage_error("replacement sibling identity could not be captured", sibling_path));
    }
    const auto locked = lock_descriptor(file.get(), LOCK_EX, sibling_path);
    if (!locked.has_value()) {
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? locked : cleanup;
    }
    if (fchmod_retry(file.get(), 0644) != 0) {
      const auto result = foundation::Result<void>::failure(
          storage_error("replacement sibling permissions could not be set", sibling_path));
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? result : cleanup;
    }
    struct stat permissioned_identity {};
    if (fstat_retry(file.get(), &permissioned_identity) != 0 ||
        !S_ISREG(permissioned_identity.st_mode) ||
        !same_identity(permissioned_identity, owned_identity)) {
      const auto result = foundation::Result<void>::failure(
          storage_error("replacement sibling identity could not be captured", sibling_path));
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? result : cleanup;
    }
    auto result = write_all(file.get(), bytes, path);
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    if (result.has_value() &&
        managed_file_kind(parent.value().normalized_path) ==
            ManagedFileKind::manifest) {
      result = testing::detail::invoke_fault(
          testing::FaultPoint::manifest_temp_sync,
          sibling_path);
    }
#endif
    if (result.has_value()) {
      result = sync_descriptor(file.get(), path);
    }
    if (result.has_value()) {
      struct stat synchronized_identity {};
      if (fstat_retry(file.get(), &synchronized_identity) != 0 ||
          !S_ISREG(synchronized_identity.st_mode) ||
          !same_identity(synchronized_identity, owned_identity) ||
          synchronized_identity.st_size != static_cast<off_t>(bytes.size())) {
        result = foundation::Result<void>::failure(
            storage_error("replacement sibling identity could not be verified", path));
      }
    }
    if (!result.has_value()) {
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? result : cleanup;
    }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    if (managed_file_kind(parent.value().normalized_path) ==
        ManagedFileKind::manifest) {
      result = testing::detail::invoke_fault(
          testing::FaultPoint::manifest_publish,
          parent.value().normalized_path);
      if (!result.has_value()) {
        const auto cleanup = unlink_owned_sibling(
            parent.value().descriptor.get(),
            sibling,
            owned_identity,
            sibling_path);
        return cleanup.has_value() ? result : cleanup;
      }
    }
#endif
    const auto source_identity = verify_named_identity(
        parent.value().descriptor.get(),
        sibling,
        owned_identity,
        sibling_path);
    if (!source_identity.has_value()) {
      return source_identity;
    }
    int renamed = -1;
    do {
      renamed = ::renameat(
          parent.value().descriptor.get(),
          sibling.c_str(),
          parent.value().descriptor.get(),
          parent.value().name.c_str());
    } while (renamed != 0 && errno == EINTR);
    if (renamed != 0) {
      result = foundation::Result<void>::failure(
          storage_error("storage file could not be replaced", path));
    }
    if (!result.has_value()) {
      const auto cleanup = unlink_owned_sibling(
          parent.value().descriptor.get(),
          sibling,
          owned_identity,
          sibling_path);
      return cleanup.has_value() ? result : cleanup;
    }
    struct stat published {};
    if (fstatat_no_follow_retry(
            parent.value().descriptor.get(),
            parent.value().name.c_str(),
            &published) != 0 ||
        !S_ISREG(published.st_mode) ||
        !same_identity(published, owned_identity)) {
      return foundation::Result<void>::failure(
          invalid_storage_path(
              "replacement publication identity changed",
              path));
    }
    const int released = file.release();
    const int close_result = ::close(released);
    const auto directory_sync = sync_directory_descriptor(
        parent.value().descriptor.get(),
        parent.value().normalized_path.parent_path());
    if (!directory_sync.has_value()) {
      return directory_sync;
    }
    if (close_result != 0) {
      return foundation::Result<void>::failure(
          storage_error("replacement sibling could not be closed", path));
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> bytes) override {
    auto parent = open_parent_without_symlinks(path);
    if (!parent.has_value()) {
      return foundation::Result<void>::failure(parent.error());
    }
    const int descriptor = openat_retry(
        parent.value().descriptor.get(),
        parent.value().name.c_str(),
        O_RDWR | O_APPEND | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor < 0) {
      if (errno == ELOOP) {
        return foundation::Result<void>::failure(
            invalid_storage_path(
                "append destination is a symbolic link",
                path));
      }
      return foundation::Result<void>::failure(
          storage_error("storage file could not be opened for append", path));
    }
    OwnedDescriptor file(descriptor);
    struct stat metadata {};
    if (fstat_retry(file.get(), &metadata) != 0 ||
        !S_ISREG(metadata.st_mode)) {
      return foundation::Result<void>::failure(
          storage_error("append destination is not a regular file", path));
    }
    const auto locked = lock_descriptor(file.get(), LOCK_EX, path);
    if (!locked.has_value()) {
      return locked;
    }
    if (fstat_retry(file.get(), &metadata) != 0 ||
        !S_ISREG(metadata.st_mode)) {
      return foundation::Result<void>::failure(
          storage_error("append destination changed while locking", path));
    }
    if (metadata.st_size < 0) {
      return foundation::Result<void>::failure(
          storage_error("append destination byte length is invalid", path));
    }
    const auto current_length =
        static_cast<std::uint64_t>(metadata.st_size);
    if (valid_prefix_length > current_length) {
      return foundation::Result<void>::failure(
          storage_error(
              "append valid prefix exceeds current file length",
              path,
              EINVAL));
    }
    if (valid_prefix_length != current_length) {
      if (ftruncate_retry(
              file.get(), static_cast<off_t>(valid_prefix_length)) != 0) {
        return foundation::Result<void>::failure(
            storage_error("append destination tail could not be repaired", path));
      }
    }
    auto result = write_all(file.get(), bytes, path);
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    if (result.has_value() &&
        managed_file_kind(parent.value().normalized_path) ==
            ManagedFileKind::active_journal) {
      result = testing::detail::invoke_fault(
          testing::FaultPoint::active_journal_sync,
          parent.value().normalized_path);
    }
#endif
    if (result.has_value()) {
      result = sync_descriptor(file.get(), path);
    }
    if (!result.has_value()) {
      return result;
    }
    const int released = file.release();
    if (::close(released) != 0) {
      return foundation::Result<void>::failure(
          storage_error("appended storage file could not be closed", path));
    }
    return foundation::Result<void>::success();
  }

  foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    const auto kind = managed_file_kind(path);
    auto exists_result = exists(path);
    if (!exists_result.has_value()) {
      return foundation::Result<void>::failure(exists_result.error());
    }
    if (!exists_result.value()) {
      if (kind == ManagedFileKind::active_journal) {
        auto parent = open_parent_without_symlinks(path);
        if (!parent.has_value()) {
          return foundation::Result<void>::failure(parent.error());
        }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
        const auto intercepted = testing::detail::invoke_fault(
            testing::FaultPoint::active_directory_sync,
            parent.value().normalized_path.parent_path());
        if (!intercepted.has_value()) {
          return intercepted;
        }
#endif
        return sync_directory_descriptor(
            parent.value().descriptor.get(),
            parent.value().normalized_path.parent_path());
      }
      return foundation::Result<void>::success();
    }
    auto parent = open_parent_without_symlinks(path);
    if (!parent.has_value()) {
      return foundation::Result<void>::failure(parent.error());
    }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    if (kind == ManagedFileKind::active_journal) {
      const auto intercepted = testing::detail::invoke_fault(
          testing::FaultPoint::active_journal_remove,
          parent.value().normalized_path);
      if (!intercepted.has_value()) {
        return intercepted;
      }
    }
#endif
    int removed = -1;
    do {
      removed = ::unlinkat(
          parent.value().descriptor.get(),
          parent.value().name.c_str(),
          0);
    } while (removed != 0 && errno == EINTR);
    if (removed != 0) {
      return foundation::Result<void>::failure(
          storage_error("storage file could not be removed", path));
    }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    if (kind == ManagedFileKind::active_journal) {
      const auto intercepted = testing::detail::invoke_fault(
          testing::FaultPoint::active_directory_sync,
          parent.value().normalized_path.parent_path());
      if (!intercepted.has_value()) {
        return intercepted;
      }
    }
#endif
    return sync_directory_descriptor(
        parent.value().descriptor.get(),
        parent.value().normalized_path.parent_path());
  }

  foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    auto directory = open_directory_without_symlinks(path);
    if (!directory.has_value()) {
      return foundation::Result<std::vector<std::string>>::failure(
          directory.error());
    }
    const int duplicated =
        duplicate_descriptor_retry(directory.value().get());
    if (duplicated < 0) {
      return foundation::Result<std::vector<std::string>>::failure(
          storage_error("storage directory could not be enumerated", path));
    }
    DIR* stream = ::fdopendir(duplicated);
    if (stream == nullptr) {
      const int open_error = errno;
      ::close(duplicated);
      return foundation::Result<std::vector<std::string>>::failure(
          storage_error(
              "storage directory could not be enumerated",
              path,
              open_error));
    }
    std::vector<std::string> names;
    while (true) {
      errno = 0;
      const auto* entry = ::readdir(stream);
      if (entry == nullptr) {
        if (errno == EINTR) {
          continue;
        }
        break;
      }
      const std::string entry_name{entry->d_name};
      const std::string_view name{entry_name};
      if (name == "." || name == "..") {
        continue;
      }
      struct stat metadata {};
      if (fstatat_no_follow_retry(
              directory.value().get(),
              entry_name.c_str(),
              &metadata) != 0) {
        const int stat_error = errno;
        ::closedir(stream);
        return foundation::Result<std::vector<std::string>>::failure(
            storage_error(
                "storage directory entry could not be inspected",
                path / entry_name,
                stat_error));
      }
      if (S_ISLNK(metadata.st_mode)) {
        ::closedir(stream);
        return foundation::Result<std::vector<std::string>>::failure(
            invalid_storage_path(
                "storage directory contains a symbolic link",
                path / entry_name));
      }
      if (S_ISREG(metadata.st_mode)) {
        names.push_back(entry_name);
      }
    }
    const int read_error = errno;
    if (::closedir(stream) != 0 && read_error == 0) {
      return foundation::Result<std::vector<std::string>>::failure(
          storage_error("storage directory could not be closed", path));
    }
    if (read_error != 0) {
      return foundation::Result<std::vector<std::string>>::failure(
          storage_error(
              "storage directory could not be enumerated",
              path,
              read_error));
    }
    std::sort(names.begin(), names.end(), unsigned_byte_less);
    return foundation::Result<std::vector<std::string>>::success(
        std::move(names));
  }

  foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& root) const override {
    const auto root_exists = exists(root);
    if (!root_exists.has_value()) {
      return foundation::Result<void>::failure(root_exists.error());
    }
    if (!root_exists.value()) {
      return foundation::Result<void>::success();
    }
    const auto normalized = normalize_path(root);
    if (!normalized.has_value()) {
      return foundation::Result<void>::failure(normalized.error());
    }
    if (normalized.value() == normalized.value().root_path()) {
      auto directory = open_directory_without_symlinks(root);
      if (!directory.has_value()) {
        return foundation::Result<void>::failure(directory.error());
      }
      return validate_directory_contents(directory.value().get(), root);
    }
    auto parent = open_parent_without_symlinks(root);
    if (!parent.has_value()) {
      return foundation::Result<void>::failure(parent.error());
    }
    struct stat metadata {};
    if (fstatat_no_follow_retry(
            parent.value().descriptor.get(),
            parent.value().name.c_str(),
            &metadata) != 0) {
      return foundation::Result<void>::failure(
          storage_error("managed storage tree could not be inspected", root));
    }
    if (S_ISLNK(metadata.st_mode)) {
      return foundation::Result<void>::failure(
          invalid_storage_path(
              "managed storage tree contains a symbolic link",
              root));
    }
    if (!S_ISDIR(metadata.st_mode)) {
      return foundation::Result<void>::failure(
          invalid_storage_path(
              S_ISREG(metadata.st_mode)
                  ? "managed storage tree root is not a directory"
                  : "managed storage tree root is a special file",
              root));
    }
    auto directory = open_directory_without_symlinks(root);
    if (!directory.has_value()) {
      return foundation::Result<void>::failure(directory.error());
    }
    return validate_directory_contents(directory.value().get(), root);
  }

 private:
  using OpenedRegularFile = std::pair<OwnedDescriptor, struct stat>;

  foundation::Result<OpenedRegularFile> open_regular_file(
      const std::filesystem::path& path) const {
    auto parent = open_parent_without_symlinks(path);
    if (!parent.has_value()) {
      return foundation::Result<OpenedRegularFile>::failure(parent.error());
    }
    const int descriptor = openat_retry(
        parent.value().descriptor.get(),
        parent.value().name.c_str(),
        O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor < 0) {
      const int open_error = errno;
      if (open_error == ELOOP) {
        return foundation::Result<OpenedRegularFile>::failure(
            invalid_storage_path("storage file is a symbolic link", path));
      }
      return foundation::Result<OpenedRegularFile>::failure(
          storage_error("storage file could not be opened", path, open_error));
    }
    OwnedDescriptor file(descriptor);
    struct stat metadata {};
    if (fstat_retry(file.get(), &metadata) != 0) {
      return foundation::Result<OpenedRegularFile>::failure(
          storage_error("storage file metadata could not be read", path));
    }
    if (!S_ISREG(metadata.st_mode)) {
      return foundation::Result<OpenedRegularFile>::failure(
          storage_error("storage path is not a regular file", path, EINVAL));
    }
    const auto locked = lock_descriptor(file.get(), LOCK_SH, path);
    if (!locked.has_value()) {
      return foundation::Result<OpenedRegularFile>::failure(locked.error());
    }
    struct stat locked_metadata {};
    if (fstat_retry(file.get(), &locked_metadata) != 0 ||
        !S_ISREG(locked_metadata.st_mode) ||
        !same_identity(metadata, locked_metadata)) {
      return foundation::Result<OpenedRegularFile>::failure(
          storage_error("storage file changed while locking", path));
    }
    return foundation::Result<OpenedRegularFile>::success(
        OpenedRegularFile{std::move(file), locked_metadata});
  }

  std::filesystem::path metadata_root_;
  std::mutex writer_mutex_;
  std::condition_variable writer_condition_;
  std::unordered_map<std::string, std::weak_ptr<NativeWriterState>> writers_;
};

}  // namespace

std::shared_ptr<ProjectStoragePlatform>
make_default_project_storage_platform() {
  return std::make_shared<NativeProjectStoragePlatform>(
      default_metadata_root());
}

std::shared_ptr<ProjectStoragePlatform>
make_native_project_storage_platform(
    const std::filesystem::path& metadata_root) {
  return std::make_shared<NativeProjectStoragePlatform>(metadata_root);
}

}  // namespace lmdj::project_io
