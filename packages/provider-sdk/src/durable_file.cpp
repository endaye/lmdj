#include "durable_file.hpp"

#include <cerrno>
#include <cstddef>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <string>
#include <system_error>
#include <utility>

#include <nlohmann/json.hpp>

namespace lmdj::provider::detail {
namespace {

using foundation::Error;
using foundation::ErrorCode;

Error io_error(
    std::string message,
    const std::filesystem::path& path,
    const std::error_code& system_error = {}) {
  auto details = nlohmann::json{{"path", path.generic_string()}};
  if (system_error) {
    details["system_error"] = system_error.message();
  }
  return Error{
      ErrorCode::io_error,
      std::move(message),
      std::move(details),
  };
}

std::error_code last_system_error() {
  return {errno, std::system_category()};
}

class UniqueFd {
 public:
  explicit UniqueFd(int descriptor) : descriptor_(descriptor) {}
  UniqueFd(const UniqueFd&) = delete;
  UniqueFd& operator=(const UniqueFd&) = delete;
  UniqueFd(UniqueFd&& other) noexcept : descriptor_(other.descriptor_) {
    other.descriptor_ = -1;
  }
  UniqueFd& operator=(UniqueFd&& other) noexcept {
    if (this != &other) {
      close();
      descriptor_ = other.descriptor_;
      other.descriptor_ = -1;
    }
    return *this;
  }
  ~UniqueFd() { close(); }

  int get() const { return descriptor_; }

 private:
  void close() {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }
  int descriptor_ = -1;
};

void remove_quietly(const std::filesystem::path& path) {
  std::error_code error;
  std::filesystem::remove(path, error);
}

}  // namespace

foundation::Result<void> sync_descriptor(
    int descriptor,
    const std::filesystem::path& path) {
  while (::fsync(descriptor) != 0) {
    if (errno == EINTR) {
      continue;
    }
    return foundation::Result<void>::failure(
        io_error("storage bytes could not be flushed", path, last_system_error()));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> sync_directory(
    const std::filesystem::path& path) {
  UniqueFd directory{::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC)};
  if (directory.get() < 0) {
    return foundation::Result<void>::failure(
        io_error(
            "storage directory could not be opened",
            path,
            last_system_error()));
  }
  return sync_descriptor(directory.get(), path);
}

foundation::Result<void> write_bytes_durable(
    const std::filesystem::path& path,
    std::string_view bytes) {
  UniqueFd file{::open(
      path.c_str(),
      O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
      S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH)};
  if (file.get() < 0) {
    return foundation::Result<void>::failure(
        io_error("temporary file could not be opened", path, last_system_error()));
  }
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto written = ::write(
        file.get(), bytes.data() + offset, bytes.size() - offset);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      const auto error = last_system_error();
      remove_quietly(path);
      return foundation::Result<void>::failure(
          io_error("temporary file could not be written", path, error));
    }
    if (written == 0) {
      remove_quietly(path);
      return foundation::Result<void>::failure(
          io_error("temporary file could not be written", path));
    }
    offset += static_cast<std::size_t>(written);
  }
  const auto synced = sync_descriptor(file.get(), path);
  if (!synced.has_value()) {
    remove_quietly(path);
    return synced;
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> publish_new_link(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path,
    foundation::ErrorCode existing_code) {
  std::error_code publish_error;
#ifdef __EMSCRIPTEN__
  // The caller holds the cross-runtime workspace lock. OPFS supports file
  // moves, not hard links; inspect before moving so terminal identity remains
  // immutable under that same lock.
  if (std::filesystem::exists(final_path, publish_error)) {
    publish_error = std::make_error_code(std::errc::file_exists);
  } else if (!publish_error) {
    std::filesystem::rename(temp_path, final_path, publish_error);
  }
#else
  std::filesystem::create_hard_link(temp_path, final_path, publish_error);
#endif
  if (publish_error) {
    remove_quietly(temp_path);
    std::error_code final_status_error;
    const auto final_status =
        std::filesystem::symlink_status(final_path, final_status_error);
    if (!final_status_error &&
        final_status.type() != std::filesystem::file_type::not_found) {
      return foundation::Result<void>::failure(
          Error{
              existing_code,
              "destination already exists",
              {{"path", final_path.generic_string()}},
          });
    }
    return foundation::Result<void>::failure(
        io_error(
            "temporary file could not be published",
            final_path,
            publish_error));
  }
  const auto synced = sync_directory(final_path.parent_path());
  if (!synced.has_value()) {
    remove_quietly(final_path);
    remove_quietly(temp_path);
    return synced;
  }
  remove_quietly(temp_path);
  return foundation::Result<void>::success();
}

foundation::Result<void> publish_replace(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path) {
  std::error_code rename_error;
  std::filesystem::rename(temp_path, final_path, rename_error);
  if (rename_error) {
    remove_quietly(temp_path);
    return foundation::Result<void>::failure(
        io_error(
            "output artifact could not be published",
            final_path,
            rename_error));
  }
  const auto synced = sync_directory(final_path.parent_path());
  if (!synced.has_value()) {
    remove_quietly(final_path);
    return synced;
  }
  return foundation::Result<void>::success();
}

}  // namespace lmdj::provider::detail
