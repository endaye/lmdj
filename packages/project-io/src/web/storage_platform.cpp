#include <lmdj/project_io/storage_platform.hpp>

#include <atomic>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <mutex>
#include <new>
#include <optional>
#include <pthread.h>
#include <string>

#include <emscripten.h>
#include <emscripten/wasmfs.h>

namespace lmdj::project_io {
namespace {

extern "C" {
int lmdj_opfs_acquire_writer(const char*, int, int, void*, int, int);
int lmdj_opfs_release_writer(int, const void*, int);
void lmdj_opfs_drain_writers();
int lmdj_opfs_ensure_directory(const char*, int);
int lmdj_opfs_exists(const char*, int);
int lmdj_opfs_directory_exists(const char*, int);
double lmdj_opfs_byte_length(const char*, int);
int lmdj_opfs_read_complete(const char*, int, void**, int*);
int lmdj_opfs_create_immutable(const char*, int, const void*, int, int);
int lmdj_opfs_replace_complete(const char*, int, const void*, int, int);
int lmdj_opfs_append_durable(
    const char*, int, double, const void*, int, int);
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
int lmdj_opfs_create_immutable_test(
    const char*, int, const void*, int, int);
int lmdj_opfs_replace_complete_test(
    const char*, int, const void*, int, int);
int lmdj_opfs_append_durable_test(
    const char*, int, double, const void*, int, int);
int lmdj_opfs_publish_directory_if_absent_test(
    const char*, int, const char*, int, int);
#endif
int lmdj_opfs_remove(const char*, int);
int lmdj_opfs_list_names(const char*, int, char**, int*);
int lmdj_opfs_list_directories(const char*, int, char**, int*);
int lmdj_opfs_remove_tree(const char*, int);
int lmdj_opfs_publish_directory_if_absent(
    const char*, int, const char*, int, int);
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
  } else if (status == -5) {
    error.details["storage_condition"] = kStorageConditionInvalidState;
  } else if (status == -6) {
    error.details["storage_condition"] = kStorageConditionQuotaExceeded;
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

// Plain fixed-width shared-Wasm words, not the private layout of std::atomic.
// JS owns one memory reference after actual physical acquisition; the C++ state
// owns another. A remote last release can destroy the C++ state without freeing
// memory still read by the physical-owner realm's pending drain.
constexpr std::uint32_t kWriterSealed = 0x80000000U;
constexpr std::uint32_t kWriterReferenceMask = kWriterSealed - 1;
enum WriterWord : std::size_t {
  memory_references, lease_gate, remote_references, cleanup_debt,
  acquisition_generation, terminally_sealed, physically_closed,
  physical_count_pointer, writer_word_count,
};
static_assert(sizeof(std::uint32_t) == 4);
static_assert(sizeof(void*) == 4);
static_assert(std::atomic_ref<std::uint32_t>::is_always_lock_free);
static_assert(std::atomic_ref<std::uint32_t>::required_alignment <=
              alignof(std::uint32_t));
alignas(std::atomic_ref<std::uint32_t>::required_alignment)
std::uint32_t physical_writer_count{};

std::atomic_ref<std::uint32_t> word(std::uint32_t* block, WriterWord index) {
  return std::atomic_ref<std::uint32_t>{block[index]};
}

struct WebWriterState {
  WebWriterState(std::string path, int platform)
      : project_path(std::move(path)), platform_identity(platform),
        physical_owner(pthread_self()),
        block(static_cast<std::uint32_t*>(
            std::calloc(writer_word_count, sizeof(std::uint32_t)))) {
    if (!block) throw std::bad_alloc{};
    static std::atomic<std::uint32_t> next_generation{1};
    auto generation = next_generation.load();
    for (;;) {
      if (generation == std::numeric_limits<std::uint32_t>::max()) {
        std::free(block);
        throw std::bad_alloc{};  // Never recycle a live acquisition generation.
      }
      if (next_generation.compare_exchange_weak(generation, generation + 1))
        break;
    }
    block[memory_references] = 1;
    block[lease_gate] = 1;  // The acquiring owner's reserved genuine lease.
    block[acquisition_generation] = generation;
    block[physical_count_pointer] = static_cast<std::uint32_t>(
        reinterpret_cast<std::uintptr_t>(&physical_writer_count));
  }
  ~WebWriterState() {
    if (word(block, memory_references).fetch_sub(1) == 1) std::free(block);
  }
  WebWriterState(const WebWriterState&) = delete;
  WebWriterState& operator=(const WebWriterState&) = delete;

  bool pin(bool remote) {
    // Reserve remote custody before total admission: a terminal seal racing
    // this CAS must see the prospective borrower and cannot close underneath it.
    if (remote) word(block, remote_references).fetch_add(1);
    auto gate = word(block, lease_gate).load();
    while (!(gate & kWriterSealed) &&
           (gate & kWriterReferenceMask) != 0 &&
           (gate & kWriterReferenceMask) != kWriterReferenceMask) {
      if (word(block, lease_gate).compare_exchange_weak(gate, gate + 1))
        return true;
    }
    if (remote) word(block, remote_references).fetch_sub(1);
    return false;
  }

  void unpin(bool remote) {
    auto gate = word(block, lease_gate).load();
    for (;;) {
      const auto references = gate & kWriterReferenceMask;
      if (!references) {
        word(block, cleanup_debt).store(1);
        return;  // Unknown custody must not become an invented release.
      }
      const auto next = (gate & kWriterSealed) |
          (references == 1 ? kWriterSealed : references - 1);
      if (word(block, lease_gate).compare_exchange_weak(gate, next)) break;
    }
    // Publish zero remote debt only after the exact local authorization is gone
    // and its total pin is retired. No owner callback or proxy is involved.
    if (remote) word(block, remote_references).fetch_sub(1);
  }

  const std::string project_path;
  const int platform_identity;
  const pthread_t physical_owner;
  std::uint32_t* const block;
  std::atomic<bool> acquired{};
};

// Match the CURRENT import boundary: original C++ lexical normalization first,
// then JS separator/component handling. In particular bundle/../bundle remains
// the same lease, as the existing real OPFS parity journey requires.
std::optional<std::string> writer_path(const std::filesystem::path& input) {
  auto path = web_path(input);
  for (auto& character : path) if (character == '\\') character = '/';
  std::vector<std::string> parts;
  std::size_t offset = 0;
  while (offset <= path.size()) {
    const auto end = path.find('/', offset);
    const auto part = path.substr(offset, end == std::string::npos
        ? std::string::npos : end - offset);
    if (part == "..") return std::nullopt;
    if (!part.empty() && part != ".") parts.push_back(part);
    if (end == std::string::npos) break;
    offset = end + 1;
  }
  if (!parts.empty() && parts.front() == "lmdj-workspace")
    parts.erase(parts.begin());
  std::string canonical{"/lmdj-workspace/"};
  for (const auto& part : parts) {
    if (canonical.back() != '/') canonical += '/';
    canonical += part;
  }
  return canonical;
}

class WebWriterLease final : public ProjectWriterLease {
 public:
  WebWriterLease(std::shared_ptr<WebWriterState> state, bool remote)
      : state_(std::move(state)), realm_(pthread_self()), remote_(remote) {}
  ~WebWriterLease() override {
    const auto generation = state_->block[acquisition_generation];
    if (!word(state_->block, physically_closed).load()) {
      if (!pthread_equal(realm_, pthread_self())) {
        // An integer token belongs to its creation realm. Retain the genuine
        // cleanup debt instead of releasing an unrelated same-numbered token.
        word(state_->block, cleanup_debt).store(1);
        return;
      }
      if (identity_ > 0 && !lmdj_opfs_release_writer(
              identity_, state_->block, generation)) {
        word(state_->block, cleanup_debt).store(1);
        return;
      }
    }
    state_->unpin(remote_);
    // Only this realm's physical states may drain. Remote destruction never
    // waits for its owner's event loop, even during an ordinary pthread join.
    if (pthread_equal(realm_, pthread_self())) lmdj_opfs_drain_writers();
  }
  void set_identity(int identity) { identity_ = identity; }
  WebWriterLease(const WebWriterLease&) = delete;
  WebWriterLease& operator=(const WebWriterLease&) = delete;

 private:
  std::shared_ptr<WebWriterState> state_;
  const pthread_t realm_;
  const bool remote_;
  int identity_{};
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
    const auto path = writer_path(project_path);
    if (!path) return failure<std::unique_ptr<ProjectWriterLease>>(
        -5, "writer path validation");
    std::shared_ptr<WebWriterState> state;
    bool initial = false;
    {
      std::lock_guard lock(writer_mutex_);
      const auto found = writers_.find(*path);
      if (found != writers_.end()) state = found->second.lock();
    }
    if (!state) {
      // Allocation/destruction and all JS/OPFS calls stay outside map locks.
      auto fresh = std::make_shared<WebWriterState>(*path, platform_identity_);
      {
        std::lock_guard lock(writer_mutex_);
        const auto found = writers_.find(*path);
        if (found != writers_.end()) state = found->second.lock();
        if (!state) {
          state = fresh;
          writers_[*path] = state;
          initial = true;
        }
      }
    }
    const bool remote = !pthread_equal(state->physical_owner, pthread_self());
    if (!initial && (!state->acquired.load() || !state->pin(remote))) {
      // An acquiring contender cannot borrow unpublished recovery or block the
      // event loop that must finish that acquisition. Preserve actual busy.
      return failure<std::unique_ptr<ProjectWriterLease>>(
          -3, "writer acquisition pending or retiring");
    }
    std::unique_ptr<WebWriterLease> lease{
        new (std::nothrow) WebWriterLease(state, remote)};
    if (!lease) {
      state->unpin(remote);
      return failure<std::unique_ptr<ProjectWriterLease>>(
          -1, "writer lease allocation");
    }
    const int identity = lmdj_opfs_acquire_writer(
        path->data(), path->size(), platform_identity_, state->block,
        state->block[acquisition_generation], initial ? 0 : 1);
    if (identity < 0) return failure<std::unique_ptr<ProjectWriterLease>>(
        identity, "writer acquisition");
    lease->set_identity(identity);
    if (initial) state->acquired.store(true);
    return foundation::Result<std::unique_ptr<ProjectWriterLease>>::success(
        std::move(lease));
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
        path.data(), path.size(), static_cast<double>(prefix), bytes.data(),
        bytes.size(), platform_identity_);
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
        destination_path.size(),
        platform_identity_);
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
  using ByteCall = int (*)(const char*, int, const void*, int, int);
  using ListCall = int (*)(const char*, int, char**, int*);

  bool mounted_;
  int platform_identity_;
  std::mutex writer_mutex_;
  std::map<std::string, std::weak_ptr<WebWriterState>> writers_;

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

  foundation::Result<void> call_bytes(
      const std::filesystem::path& input, std::span<const std::byte> bytes,
      ByteCall call, std::string_view operation) const {
    const auto path = web_path(input);
    const int status = call(
        path.data(), path.size(), bytes.data(), bytes.size(),
        platform_identity_);
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

extern "C" EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_project_io_physical_writer_count() {
  return std::atomic_ref<std::uint32_t>{physical_writer_count}.load();
}

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
