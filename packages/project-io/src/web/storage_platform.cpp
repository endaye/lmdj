#include <lmdj/project_io/storage_platform.hpp>

#include <atomic>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>

#include <emscripten.h>
#include <emscripten/wasmfs.h>

namespace lmdj::project_io {
namespace {

extern "C" {
int lmdj_opfs_acquire_writer(const char*, int, int);
void lmdj_opfs_release_writer(int);
int lmdj_opfs_ensure_directory(const char*, int);
int lmdj_opfs_exists(const char*, int);
int lmdj_opfs_directory_exists(const char*, int);
double lmdj_opfs_byte_length(const char*, int);
int lmdj_opfs_read_complete(const char*, int, void**, int*);
int lmdj_opfs_create_immutable(const char*, int, const void*, int);
int lmdj_opfs_replace_complete(const char*, int, const void*, int);
int lmdj_opfs_append_durable(const char*, int, double, const void*, int);
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
int lmdj_opfs_create_immutable_test(const char*, int, const void*, int);
int lmdj_opfs_replace_complete_test(const char*, int, const void*, int);
int lmdj_opfs_append_durable_test(const char*, int, double, const void*, int);
int lmdj_opfs_publish_directory_if_absent_test(
    const char*, int, const char*, int);
#endif
int lmdj_opfs_remove(const char*, int);
int lmdj_opfs_list_names(const char*, int, char**, int*);
int lmdj_opfs_list_directories(const char*, int, char**, int*);
int lmdj_opfs_remove_tree(const char*, int);
int lmdj_opfs_publish_directory_if_absent(
    const char*, int, const char*, int);
int lmdj_opfs_validate_tree(const char*, int);
}

foundation::Error web_error(int status, std::string_view operation) {
  foundation::Error error{
      status == -2 ? foundation::ErrorCode::not_found
                   : foundation::ErrorCode::io_error,
      std::string{"Web storage "} + std::string{operation} + " failed"};
  if (status == -3) {
    error.details["storage_condition"] = kStorageConditionProjectBusy;
  } else if (status == -4) {
    error.details["storage_condition"] = kStorageConditionAlreadyExists;
  } else if (status == -8) {
    error.details["storage_condition"] =
        kStorageConditionAtomicPublishUnsupported;
  }
  return error;
}

std::string web_path(const std::filesystem::path& path) {
  return path.lexically_normal().generic_string();
}

template <typename T>
foundation::Result<T> failure(int status, std::string_view operation) {
  return foundation::Result<T>::failure(web_error(status, operation));
}

class WebWriterLease final : public ProjectWriterLease {
 public:
  explicit WebWriterLease(int identity) : identity_(identity) {}
  ~WebWriterLease() override { lmdj_opfs_release_writer(identity_); }
  WebWriterLease(const WebWriterLease&) = delete;
  WebWriterLease& operator=(const WebWriterLease&) = delete;

 private:
  int identity_;
};

class WebProjectStoragePlatform final : public ProjectStoragePlatform {
 public:
  explicit WebProjectStoragePlatform(bool mounted)
      : mounted_(mounted), platform_identity_(next_platform_identity()) {}

  foundation::Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(
      const std::filesystem::path& project_path) override {
    if (!mounted_) {
      return failure<std::unique_ptr<ProjectWriterLease>>(
          -1, "mount availability");
    }
    const auto path = web_path(project_path);
    const int identity = lmdj_opfs_acquire_writer(
        path.data(), path.size(), platform_identity_);
    if (identity < 0) {
      return failure<std::unique_ptr<ProjectWriterLease>>(identity, "writer acquisition");
    }
    return foundation::Result<std::unique_ptr<ProjectWriterLease>>::success(
        std::make_unique<WebWriterLease>(identity));
  }

  foundation::Result<void> ensure_directory(
      const std::filesystem::path& input) override {
    if (!mounted_) return mount_failure();
    return call_path(input, lmdj_opfs_ensure_directory, "directory creation");
  }

  foundation::Result<bool> exists(
      const std::filesystem::path& input) const override {
    if (!mounted_) {
      return failure<bool>(-1, "mount availability");
    }
    const auto path = web_path(input);
    const int status = lmdj_opfs_exists(path.data(), path.size());
    if (status < 0) return failure<bool>(status, "existence check");
    return foundation::Result<bool>::success(status != 0);
  }

  foundation::Result<bool> directory_exists(
      const std::filesystem::path& input) const override {
    if (!mounted_) {
      return failure<bool>(-1, "mount availability");
    }
    const auto path = web_path(input);
    const int status = lmdj_opfs_directory_exists(path.data(), path.size());
    if (status < 0) {
      return failure<bool>(status, "directory existence check");
    }
    return foundation::Result<bool>::success(status != 0);
  }

  foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& input) const override {
    if (!mounted_) return failure<std::uint64_t>(-1, "mount availability");
    const auto path = web_path(input);
    const double length = lmdj_opfs_byte_length(path.data(), path.size());
    if (length < 0.0 || length > static_cast<double>(std::numeric_limits<std::uint64_t>::max())) {
      return failure<std::uint64_t>(static_cast<int>(length), "length query");
    }
    return foundation::Result<std::uint64_t>::success(static_cast<std::uint64_t>(length));
  }

  foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& input) const override {
    if (!mounted_) {
      return failure<std::vector<std::byte>>(-1, "mount availability");
    }
    const auto path = web_path(input);
    void* data = nullptr;
    int length = 0;
    const int status = lmdj_opfs_read_complete(path.data(), path.size(), &data, &length);
    if (status < 0) return failure<std::vector<std::byte>>(status, "complete read");
    std::vector<std::byte> result(static_cast<std::size_t>(length));
    if (length > 0) std::memcpy(result.data(), data, static_cast<std::size_t>(length));
    std::free(data);
    return foundation::Result<std::vector<std::byte>>::success(std::move(result));
  }

  foundation::Result<void> create_immutable(
      const std::filesystem::path& input, std::span<const std::byte> bytes) override {
    if (!mounted_) return mount_failure();
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    return call_bytes(
        input, bytes, lmdj_opfs_create_immutable_test, "immutable creation");
#else
    return call_bytes(input, bytes, lmdj_opfs_create_immutable, "immutable creation");
#endif
  }

  foundation::Result<void> replace_complete(
      const std::filesystem::path& input, std::span<const std::byte> bytes) override {
    if (!mounted_) return mount_failure();
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    return call_bytes(input, bytes, lmdj_opfs_replace_complete_test, "complete replacement");
#else
    return call_bytes(input, bytes, lmdj_opfs_replace_complete, "complete replacement");
#endif
  }

  foundation::Result<void> append_durable(
      const std::filesystem::path& input, std::uint64_t prefix,
      std::span<const std::byte> bytes) override {
    if (!mounted_) return mount_failure();
    const auto path = web_path(input);
    const int status =
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
        lmdj_opfs_append_durable_test(
#else
        lmdj_opfs_append_durable(
#endif
        path.data(), path.size(), static_cast<double>(prefix), bytes.data(), bytes.size());
    return status < 0 ? foundation::Result<void>::failure(web_error(status, "durable append"))
                      : foundation::Result<void>::success();
  }

  foundation::Result<void> remove(const std::filesystem::path& input) override {
    if (!mounted_) return mount_failure();
    return call_path(input, lmdj_opfs_remove, "removal");
  }

  foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& input) const override {
    if (!mounted_) {
      return failure<std::vector<std::string>>(-1, "mount availability");
    }
    const auto path = web_path(input);
    char* data = nullptr;
    int length = 0;
    const int status = lmdj_opfs_list_names(path.data(), path.size(), &data, &length);
    if (status < 0) return failure<std::vector<std::string>>(status, "directory iteration");
    std::vector<std::string> names;
    const char* current = data;
    const char* end = data + length;
    while (current < end) {
      const auto size = std::strlen(current);
      names.emplace_back(current, size);
      current += size + 1;
    }
    std::free(data);
    return foundation::Result<std::vector<std::string>>::success(std::move(names));
  }

  foundation::Result<std::vector<std::string>> list_directories(
      const std::filesystem::path& input) const override {
    if (!mounted_) {
      return failure<std::vector<std::string>>(-1, "mount availability");
    }
    return list_entries(
        input, lmdj_opfs_list_directories, "directory iteration");
  }

  foundation::Result<void> remove_tree(
      const std::filesystem::path& input) override {
    if (!mounted_) return mount_failure();
    return call_path(input, lmdj_opfs_remove_tree, "recursive removal");
  }

  foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path& staging,
      const std::filesystem::path& destination) override {
    if (!mounted_) return mount_failure();
    const auto source_path = web_path(staging);
    const auto destination_path = web_path(destination);
    const int status =
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
        lmdj_opfs_publish_directory_if_absent_test(
#else
        lmdj_opfs_publish_directory_if_absent(
#endif
        source_path.data(),
        source_path.size(),
        destination_path.data(),
        destination_path.size());
    return status < 0
               ? foundation::Result<void>::failure(
                     web_error(status, "atomic directory publish"))
               : foundation::Result<void>::success();
  }

  foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& input) const override {
    if (!mounted_) return mount_failure();
    return call_path(input, lmdj_opfs_validate_tree, "tree validation");
  }

 private:
  using PathCall = int (*)(const char*, int);
  using ByteCall = int (*)(const char*, int, const void*, int);
  using ListCall = int (*)(const char*, int, char**, int*);

  bool mounted_;
  int platform_identity_;

  static int next_platform_identity() {
    static std::atomic<int> next{1};
    return next.fetch_add(1, std::memory_order_relaxed);
  }

  static foundation::Result<void> mount_failure() {
    return foundation::Result<void>::failure(
        web_error(-1, "mount availability"));
  }

  static foundation::Result<void> call_path(
      const std::filesystem::path& input, PathCall call, std::string_view operation) {
    const auto path = web_path(input);
    const int status = call(path.data(), path.size());
    return status < 0 ? foundation::Result<void>::failure(web_error(status, operation))
                      : foundation::Result<void>::success();
  }

  static foundation::Result<void> call_bytes(
      const std::filesystem::path& input, std::span<const std::byte> bytes,
      ByteCall call, std::string_view operation) {
    const auto path = web_path(input);
    const int status = call(path.data(), path.size(), bytes.data(), bytes.size());
    return status < 0 ? foundation::Result<void>::failure(web_error(status, operation))
                      : foundation::Result<void>::success();
  }

  static foundation::Result<std::vector<std::string>> list_entries(
      const std::filesystem::path& input,
      ListCall call,
      std::string_view operation) {
    const auto path = web_path(input);
    char* data = nullptr;
    int length = 0;
    const int status = call(path.data(), path.size(), &data, &length);
    if (status < 0) {
      return failure<std::vector<std::string>>(status, operation);
    }
    std::vector<std::string> names;
    const char* current = data;
    const char* end = data + length;
    while (current < end) {
      const auto size = std::strlen(current);
      names.emplace_back(current, size);
      current += size + 1;
    }
    std::free(data);
    return foundation::Result<std::vector<std::string>>::success(
        std::move(names));
  }
};

}  // namespace

std::shared_ptr<ProjectStoragePlatform> make_web_project_storage_platform() {
  static const bool mounted = [] {
    const auto backend = wasmfs_create_opfs_backend();
    return backend != nullptr &&
           wasmfs_create_directory("/lmdj-workspace", 0777, backend) == 0;
  }();
  return std::make_shared<WebProjectStoragePlatform>(mounted);
}

#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
std::shared_ptr<ProjectStoragePlatform>
make_web_project_storage_platform_for_test(bool mounted) {
  return std::make_shared<WebProjectStoragePlatform>(mounted);
}
#endif

std::shared_ptr<ProjectStoragePlatform> make_default_project_storage_platform() {
  return make_web_project_storage_platform();
}

}  // namespace lmdj::project_io
