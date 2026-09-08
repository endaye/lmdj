#include <lmdj/project_io/soundset_store.hpp>

#include <algorithm>
#include <cerrno>
#include <limits>
#include <mutex>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <picosha2.h>

#include <lmdj/project_io/soundset_catalog_transport.hpp>

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::string_view kHostDirectory = ".lmdj-host";
constexpr std::string_view kSetsDirectory = "soundsets";
constexpr std::string_view kStagingDirectory = "soundset-staging";
constexpr std::string_view kManifestName = "manifest.json";

// A staging area larger than this is not measured and not trusted; refusing is
// the fail-closed answer.
constexpr std::size_t kMaximumStagingDirectories = 4096;

Error unavailable(std::string message) {
  return Error{
      ErrorCode::io_error,
      std::move(message),
      {{"reason", std::string{kSoundSetReasonCatalogUnavailable}}},
  };
}

Error content_mismatch(std::string message) {
  return Error{
      ErrorCode::io_error,
      std::move(message),
      {{"reason", std::string{kSoundSetReasonContentMismatch}}},
  };
}

// The repository's established limit-refusal shape: the Host manifest key that
// refused, what was observed, and what it allows. The Application Facade
// already forwards this triple, so no new public vocabulary is needed.
Error resource_limit(
    std::string resource,
    std::uint64_t observed,
    std::uint64_t limit) {
  auto message = "Sound Set exceeds the Host limit " + resource;
  return Error{
      ErrorCode::io_error,
      std::move(message),
      {
          {"resource", std::move(resource)},
          {"observed", observed},
          {"limit", limit},
      },
  };
}

Error invalid_argument(std::string message) {
  return Error{ErrorCode::invalid_argument, std::move(message)};
}

Error not_found(std::string message) {
  return Error{ErrorCode::not_found, std::move(message)};
}

bool lowercase_sha256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(value.begin(), value.end(), [](char character) {
           return (character >= '0' && character <= '9') ||
                  (character >= 'a' && character <= 'f');
         });
}

// A normalized absolute directory that is neither the filesystem root nor a
// path carrying a relative segment.
bool valid_root(const std::filesystem::path& root) {
  if (root.empty() || !root.is_absolute() ||
      root.lexically_normal() != root || root == root.root_path()) {
    return false;
  }
  return std::none_of(
      root.begin(),
      root.end(),
      [](const std::filesystem::path& segment) {
        return segment == "." || segment == "..";
      });
}

std::string digest_of(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* begin = reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(begin, begin + bytes.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

std::string_view text_of(const std::vector<std::byte>& bytes) {
  return {reinterpret_cast<const char*>(bytes.data()), bytes.size()};
}

// One more byte than the limit, so the caller can tell "exactly at the limit"
// from "over it" without the transport having to know the limit's meaning. An
// object further over the bound than that is refused by the transport itself
// and is indistinguishable from an unresolvable one; both fail closed, and
// neither ever allocates more than one byte past the limit.
std::uint64_t bound_above(std::uint64_t limit) {
  if (limit == std::numeric_limits<std::uint64_t>::max()) {
    return limit;
  }
  return limit + 1;
}

std::optional<std::uint64_t> checked_sum(
    std::uint64_t current,
    std::uint64_t additional) {
  if (current > std::numeric_limits<std::uint64_t>::max() - additional) {
    return std::nullopt;
  }
  return current + additional;
}

class OwnedDescriptor {
 public:
  OwnedDescriptor() = default;
  explicit OwnedDescriptor(int descriptor) : descriptor_(descriptor) {}
  ~OwnedDescriptor() { reset(); }

  OwnedDescriptor(const OwnedDescriptor&) = delete;
  OwnedDescriptor& operator=(const OwnedDescriptor&) = delete;
  OwnedDescriptor(OwnedDescriptor&& other) noexcept
      : descriptor_(other.descriptor_) {
    other.descriptor_ = -1;
  }
  OwnedDescriptor& operator=(OwnedDescriptor&& other) noexcept {
    if (this != &other) {
      reset();
      descriptor_ = other.descriptor_;
      other.descriptor_ = -1;
    }
    return *this;
  }

  int get() const { return descriptor_; }

  void reset() {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }

 private:
  int descriptor_ = -1;
};

int open_retry(const char* path, int flags) {
  int descriptor = -1;
  do {
    descriptor = ::open(path, flags);
  } while (descriptor < 0 && errno == EINTR);
  return descriptor;
}

int openat_retry(int parent, const char* name, int flags) {
  int descriptor = -1;
  do {
    descriptor = ::openat(parent, name, flags);
  } while (descriptor < 0 && errno == EINTR);
  return descriptor;
}

int fstat_retry(int descriptor, struct stat* metadata) {
  int result = 0;
  do {
    result = ::fstat(descriptor, metadata);
  } while (result != 0 && errno == EINTR);
  return result;
}

// The local directory Catalog adapter. Every object, manifest or blob, is one
// basename under one configured root; there is no archive and no unpack step.
class LocalDirectoryCatalogTransport final : public CatalogTransport {
 public:
  explicit LocalDirectoryCatalogTransport(std::filesystem::path root)
      : root_(std::move(root)) {}

  foundation::Result<std::vector<std::byte>> read_object(
      const CatalogObjectRef& object,
      std::uint64_t maximum_bytes) override {
    using Result = foundation::Result<std::vector<std::byte>>;
    // The caller never supplies a path: only a verified lowercase sha256,
    // which cannot contain '/', '.' or '..' and has exactly one spelling.
    if (!lowercase_sha256(object.sha256)) {
      return Result::failure(
          unavailable("Catalog object name is not a lowercase sha256"));
    }
    if (!valid_root(root_)) {
      return Result::failure(
          unavailable("Catalog root is not a normalized absolute directory"));
    }
    OwnedDescriptor directory(open_retry(
        root_.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
    if (directory.get() < 0) {
      return Result::failure(
          unavailable("Catalog root could not be opened"));
    }
    OwnedDescriptor file(openat_retry(
        directory.get(),
        object.sha256.c_str(),
        O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
    if (file.get() < 0) {
      return Result::failure(
          unavailable("Catalog object could not be opened"));
    }
    struct stat metadata {};
    if (fstat_retry(file.get(), &metadata) != 0) {
      return Result::failure(
          unavailable("Catalog object could not be inspected"));
    }
    if (!S_ISREG(metadata.st_mode)) {
      return Result::failure(
          unavailable("Catalog object is not a regular file"));
    }
    const auto size = static_cast<std::uint64_t>(metadata.st_size);
    if (size > maximum_bytes) {
      return Result::failure(
          unavailable("Catalog object exceeds the requested bound"));
    }
    std::vector<std::byte> bytes(static_cast<std::size_t>(size));
    std::size_t filled = 0;
    while (filled < bytes.size()) {
      const auto read = ::read(
          file.get(),
          reinterpret_cast<char*>(bytes.data()) + filled,
          bytes.size() - filled);
      if (read < 0) {
        if (errno == EINTR) {
          continue;
        }
        return Result::failure(unavailable("Catalog object could not be read"));
      }
      if (read == 0) {
        return Result::failure(
            unavailable("Catalog object ended before its declared length"));
      }
      filled += static_cast<std::size_t>(read);
    }
    // The name is the hash: prove what was opened is what was addressed.
    if (digest_of(bytes) != object.sha256) {
      return Result::failure(
          content_mismatch("Catalog object does not hash to its own name"));
    }
    return Result::success(std::move(bytes));
  }

 private:
  std::filesystem::path root_;
};

}  // namespace

std::shared_ptr<CatalogTransport> make_local_directory_catalog_transport(
    std::filesystem::path root) {
  return std::make_shared<LocalDirectoryCatalogTransport>(std::move(root));
}

struct SoundSetStore::Impl {
  Impl(
      std::filesystem::path workspace_root,
      SoundSetStoreLimits limits,
      std::shared_ptr<ProjectStoragePlatform> platform)
      : workspace_root(std::move(workspace_root)),
        limits(limits),
        platform(
            platform != nullptr
                ? std::move(platform)
                : make_default_project_storage_platform()) {}

  std::filesystem::path sets_root() const {
    return workspace_root / kHostDirectory / kSetsDirectory;
  }

  std::filesystem::path staging_root() const {
    return workspace_root / kHostDirectory / kStagingDirectory;
  }

  foundation::Result<void> validated_workspace() const {
    if (!valid_root(workspace_root)) {
      return foundation::Result<void>::failure(
          invalid_argument(
              "Workspace root must be a normalized absolute path"));
    }
    return foundation::Result<void>::success();
  }

  // Load a published Set from its own directory. A Set that is not there, or
  // whose bytes no longer answer to their own hash, is simply not published.
  foundation::Result<StoredSoundSet> load(
      std::string_view manifest_sha256) const {
    using Result = foundation::Result<StoredSoundSet>;
    const auto directory = sets_root() / std::string{manifest_sha256};
    const auto present = platform->directory_exists(directory);
    if (!present.has_value() || !present.value()) {
      return Result::failure(not_found("Sound Set is not in the Set Store"));
    }
    const auto bytes =
        platform->read_complete(directory / std::string{kManifestName});
    if (!bytes.has_value()) {
      return Result::failure(not_found("Sound Set manifest could not be read"));
    }
    if (digest_of(bytes.value()) != manifest_sha256) {
      return Result::failure(
          content_mismatch(
              "Stored Sound Set manifest changed under the store"));
    }
    auto manifest =
        foundation::parse_soundset_manifest(text_of(bytes.value()));
    if (!manifest.has_value()) {
      return Result::failure(manifest.error());
    }
    const auto artifacts = unique_artifacts(manifest.value());
    if (!artifacts.has_value()) {
      return Result::failure(artifacts.error());
    }
    const auto total = unique_total(artifacts.value(), bytes.value().size());
    if (!total.has_value()) {
      return Result::failure(
          content_mismatch("Stored Sound Set byte total does not fit"));
    }
    return Result::success(
        StoredSoundSet{std::move(manifest.value()), total.value()});
  }

  // The set-level demo (S11-D5) first, then the occupied slots in slot order,
  // each Artifact hash counted once however many places reference it. S11-D7
  // makes the demo part of this accounting rather than a separate download, so
  // a demo that names a slot's Artifact is fetched and charged exactly once.
  // The demo comes first because the canonical manifest declares it first.
  //
  // One hash is one immutable object, so two references that declare the same
  // sha256 with a different byte_length or media_type -- two slots, or the
  // demo and a slot -- are describing something that cannot exist: refuse
  // rather than silently keep the first declaration and let the second reach
  // the Set Store unchecked.
  static foundation::Result<std::vector<foundation::ArtifactRef>>
  unique_artifacts(const foundation::SoundSetManifest& manifest) {
    using Result = foundation::Result<std::vector<foundation::ArtifactRef>>;
    std::vector<foundation::ArtifactRef> unique;
    const auto add = [&unique](const foundation::ArtifactRef& artifact) {
      const auto seen = std::find_if(
          unique.begin(),
          unique.end(),
          [&artifact](const foundation::ArtifactRef& known) {
            return known.sha256 == artifact.sha256;
          });
      if (seen == unique.end()) {
        unique.push_back(artifact);
        return true;
      }
      return *seen == artifact;
    };
    if (manifest.demo.has_value() && !add(*manifest.demo)) {
      return Result::failure(
          content_mismatch(
              "Sound Set declares one Artifact hash with two descriptions"));
    }
    for (const auto& slot : manifest.slots) {
      if (!slot.occupied.has_value()) {
        continue;
      }
      if (!add(slot.occupied->artifact)) {
        return Result::failure(
            content_mismatch(
                "Sound Set declares one Artifact hash with two descriptions"));
      }
    }
    return Result::success(std::move(unique));
  }

  // Canonical manifest bytes plus the byte_length of each unique Artifact.
  static std::optional<std::uint64_t> unique_total(
      const std::vector<foundation::ArtifactRef>& artifacts,
      std::uint64_t manifest_bytes) {
    auto total = std::optional<std::uint64_t>{manifest_bytes};
    for (const auto& artifact : artifacts) {
      total = checked_sum(*total, artifact.byte_length);
      if (!total.has_value()) {
        return std::nullopt;
      }
    }
    return total;
  }

  // Every byte the staging area currently holds, including whatever an earlier
  // interrupted acquisition left behind.
  foundation::Result<std::uint64_t> staged_bytes() const {
    using Result = foundation::Result<std::uint64_t>;
    const auto root = staging_root();
    const auto present = platform->directory_exists(root);
    if (!present.has_value() || !present.value()) {
      return Result::success(0);
    }
    // Walk the whole area, not just the flat shape this store writes: an
    // uncounted byte would make the staging limit fail open.
    std::vector<std::filesystem::path> pending{root};
    std::uint64_t total = 0;
    std::size_t visited = 0;
    while (!pending.empty()) {
      if (++visited > kMaximumStagingDirectories) {
        return Result::failure(
            unavailable("Sound Set staging area is too deep to measure"));
      }
      const auto area = pending.back();
      pending.pop_back();
      const auto names = platform->list_names(area);
      if (!names.has_value()) {
        return Result::failure(names.error());
      }
      for (const auto& entry : names.value()) {
        const auto length = platform->byte_length(area / entry);
        if (!length.has_value()) {
          return Result::failure(length.error());
        }
        const auto summed = checked_sum(total, length.value());
        if (!summed.has_value()) {
          return Result::failure(
              resource_limit(
                  "maximum_soundset_staging_bytes",
                  std::numeric_limits<std::uint64_t>::max(),
                  limits.maximum_soundset_staging_bytes));
        }
        total = summed.value();
      }
      const auto children = platform->list_directories(area);
      if (!children.has_value()) {
        return Result::failure(children.error());
      }
      for (const auto& child : children.value()) {
        pending.push_back(area / child);
      }
    }
    return Result::success(total);
  }

  std::filesystem::path workspace_root;
  SoundSetStoreLimits limits;
  std::shared_ptr<ProjectStoragePlatform> platform;
  std::mutex mutex;
};

SoundSetStore::SoundSetStore(
    std::filesystem::path workspace_root,
    SoundSetStoreLimits limits)
    : SoundSetStore(std::move(workspace_root), limits, nullptr) {}

SoundSetStore::SoundSetStore(
    std::filesystem::path workspace_root,
    SoundSetStoreLimits limits,
    std::shared_ptr<ProjectStoragePlatform> platform)
    : impl_(
          std::make_unique<Impl>(
              std::move(workspace_root), limits, std::move(platform))) {}

SoundSetStore::~SoundSetStore() = default;

foundation::Result<StoredSoundSet> SoundSetStore::acquire(
    CatalogTransport& transport,
    const SoundSetCatalogEntry& entry) {
  using Result = foundation::Result<StoredSoundSet>;
  std::lock_guard lock(impl_->mutex);
  const auto workspace = impl_->validated_workspace();
  if (!workspace.has_value()) {
    return Result::failure(workspace.error());
  }
  if (!lowercase_sha256(entry.manifest_sha256) || entry.set_id.empty() ||
      entry.version.empty()) {
    return Result::failure(
        invalid_argument("Catalog entry identity is not well formed"));
  }

  const auto destination = impl_->sets_root() / entry.manifest_sha256;
  const auto answer = [&entry](
                          const foundation::Result<StoredSoundSet>& stored) {
    if (stored.value().manifest.set_id != entry.set_id ||
        stored.value().manifest.version != entry.version) {
      return Result::failure(
          content_mismatch(
              "Stored Sound Set identity does not match the Catalog entry"));
    }
    return stored;
  };

  // A Set already in the store is the answer; the Catalog is not consulted
  // and no writer lease is taken. A published Set is immutable, so reading it
  // needs no exclusion, and taking a lease here would make one Host's routine
  // Catalog refresh refuse an installed Set to every other Host on the same
  // Workspace.
  const auto cached = impl_->load(entry.manifest_sha256);
  if (cached.has_value()) {
    return answer(cached);
  }

  // Nothing readable is published, so this acquisition may have to write.
  // Lease the destination before deciding anything else about it, exactly as
  // ProjectBundleTransfer::commit leases the Project it is about to publish.
  // A platform that cannot rename atomically publishes by copy, and the
  // destination lease is what makes that copy safe: it excludes every other
  // writer from the half-built destination, and acquiring it is what recovers
  // a publication an earlier run interrupted. That recovery has to happen
  // before the verdict below, or the leftovers of an interrupted copy would be
  // reported as a corrupted Set forever. The native platform publishes with an
  // atomic rename and does not consult the lease; taking it on both keeps one
  // publication discipline instead of two.
  auto destination_lease = impl_->platform->acquire_writer(destination);
  if (!destination_lease.has_value()) {
    return Result::failure(destination_lease.error());
  }
  const auto already_present = impl_->platform->directory_exists(destination);
  const auto published = impl_->load(entry.manifest_sha256);
  if (published.has_value()) {
    return answer(published);
  }
  // A Set whose directory is there but unreadable must say so. Re-downloading
  // it would only collide with the occupant at publication time and report the
  // collision instead of the corruption.
  if (already_present.has_value() && already_present.value()) {
    return Result::failure(published.error());
  }

  const auto manifest_bytes = transport.read_manifest_object(
      entry.manifest_sha256,
      bound_above(impl_->limits.maximum_soundset_manifest_bytes));
  if (!manifest_bytes.has_value()) {
    const auto& error = manifest_bytes.error();
    if (error.details.is_object() &&
        error.details.value("reason", std::string{}) ==
            kSoundSetReasonContentMismatch) {
      return Result::failure(error);
    }
    return Result::failure(
        unavailable("Sound Set manifest could not be read from the Catalog"));
  }
  const auto& manifest_object = manifest_bytes.value();
  if (manifest_object.size() > impl_->limits.maximum_soundset_manifest_bytes) {
    return Result::failure(
        resource_limit(
            "maximum_soundset_manifest_bytes",
            manifest_object.size(),
            impl_->limits.maximum_soundset_manifest_bytes));
  }
  if (digest_of(manifest_object) != entry.manifest_sha256) {
    return Result::failure(
        content_mismatch(
            "Sound Set manifest does not hash to the Catalog identity"));
  }
  auto parsed = foundation::parse_soundset_manifest(text_of(manifest_object));
  if (!parsed.has_value()) {
    return Result::failure(parsed.error());
  }
  auto manifest = std::move(parsed.value());
  if (manifest.set_id != entry.set_id || manifest.version != entry.version) {
    return Result::failure(
        content_mismatch(
            "Sound Set manifest identity does not match the Catalog entry"));
  }
  const auto eligible =
      foundation::check_soundset_eligibility(manifest, entry.license_summary);
  if (!eligible.has_value()) {
    return Result::failure(eligible.error());
  }

  // Every limit is decided here, before a single blob is requested.
  const auto artifacts = Impl::unique_artifacts(manifest);
  if (!artifacts.has_value()) {
    return Result::failure(artifacts.error());
  }
  for (const auto& artifact : artifacts.value()) {
    if (artifact.byte_length > impl_->limits.maximum_soundset_blob_bytes) {
      return Result::failure(
          resource_limit(
              "maximum_soundset_blob_bytes",
              artifact.byte_length,
              impl_->limits.maximum_soundset_blob_bytes));
    }
  }
  const auto total =
      Impl::unique_total(artifacts.value(), manifest_object.size());
  if (!total.has_value()) {
    return Result::failure(
        content_mismatch("Sound Set byte total does not fit"));
  }
  if (total.value() > impl_->limits.maximum_soundset_unique_bytes) {
    return Result::failure(
        resource_limit(
            "maximum_soundset_unique_bytes",
            total.value(),
            impl_->limits.maximum_soundset_unique_bytes));
  }
  if (total.value() != entry.total_bytes) {
    return Result::failure(
        content_mismatch(
            "Sound Set unique byte total does not match the Catalog entry"));
  }
  const auto staging = impl_->staging_root() / entry.manifest_sha256;
  auto lease = impl_->platform->acquire_writer(staging);
  if (!lease.has_value()) {
    return Result::failure(lease.error());
  }
  const auto discard = [&]() {
    lease.value().reset();
    (void)impl_->platform->remove_tree(staging);
  };
  // Clear this Set's own interrupted staging first: a retry is replacing those
  // bytes, not adding to them.
  (void)impl_->platform->remove_tree(staging);
  const auto staged = impl_->staged_bytes();
  if (!staged.has_value()) {
    discard();
    return Result::failure(staged.error());
  }
  const auto staging_total = checked_sum(staged.value(), total.value());
  if (!staging_total.has_value() ||
      staging_total.value() > impl_->limits.maximum_soundset_staging_bytes) {
    discard();
    return Result::failure(
        resource_limit(
            "maximum_soundset_staging_bytes",
            staging_total.value_or(std::numeric_limits<std::uint64_t>::max()),
            impl_->limits.maximum_soundset_staging_bytes));
  }
  for (const auto& directory :
       {impl_->workspace_root / kHostDirectory,
        impl_->staging_root(),
        staging}) {
    const auto ensured = impl_->platform->ensure_directory(directory);
    if (!ensured.has_value()) {
      discard();
      return Result::failure(ensured.error());
    }
  }
  const auto wrote_manifest = impl_->platform->create_immutable(
      staging / std::string{kManifestName}, manifest_object);
  if (!wrote_manifest.has_value()) {
    discard();
    return Result::failure(wrote_manifest.error());
  }
  for (const auto& artifact : artifacts.value()) {
    const auto blob = transport.read_blob_object(
        artifact.sha256, impl_->limits.maximum_soundset_blob_bytes);
    if (!blob.has_value()) {
      const auto& error = blob.error();
      discard();
      if (error.details.is_object() &&
          error.details.value("reason", std::string{}) ==
              kSoundSetReasonContentMismatch) {
        return Result::failure(error);
      }
      return Result::failure(
          unavailable("Sound Set Artifact could not be read from the Catalog"));
    }
    if (blob.value().size() != artifact.byte_length) {
      discard();
      return Result::failure(
          content_mismatch(
              "Sound Set Artifact length does not match its declaration"));
    }
    if (digest_of(blob.value()) != artifact.sha256) {
      discard();
      return Result::failure(
          content_mismatch(
              "Sound Set Artifact does not hash to its declaration"));
    }
    const auto wrote = impl_->platform->create_immutable(
        staging / artifact.sha256, blob.value());
    if (!wrote.has_value()) {
      discard();
      return Result::failure(wrote.error());
    }
  }

  const auto ensured = impl_->platform->ensure_directory(impl_->sets_root());
  if (!ensured.has_value()) {
    discard();
    return Result::failure(ensured.error());
  }
  lease.value().reset();
  const auto published_now =
      impl_->platform->publish_directory_if_absent(staging, destination);
  if (!published_now.has_value()) {
    (void)impl_->platform->remove_tree(staging);
    return Result::failure(published_now.error());
  }
  (void)impl_->platform->remove_tree(staging);
  return Result::success(StoredSoundSet{std::move(manifest), total.value()});
}

foundation::Result<std::vector<StoredSoundSet>> SoundSetStore::list() const {
  using Result = foundation::Result<std::vector<StoredSoundSet>>;
  const auto workspace = impl_->validated_workspace();
  if (!workspace.has_value()) {
    return Result::failure(workspace.error());
  }
  const auto root = impl_->sets_root();
  const auto present = impl_->platform->directory_exists(root);
  if (!present.has_value() || !present.value()) {
    return Result::success({});
  }
  const auto names = impl_->platform->list_directories(root);
  if (!names.has_value()) {
    return Result::failure(names.error());
  }
  std::vector<StoredSoundSet> sets;
  for (const auto& name : names.value()) {
    if (!lowercase_sha256(name)) {
      continue;
    }
    auto stored = impl_->load(name);
    if (!stored.has_value()) {
      continue;
    }
    sets.push_back(std::move(stored.value()));
  }
  return Result::success(std::move(sets));
}

foundation::Result<StoredSoundSet> SoundSetStore::read(
    std::string_view set_id,
    std::string_view version,
    std::string_view manifest_sha256) const {
  using Result = foundation::Result<StoredSoundSet>;
  const auto workspace = impl_->validated_workspace();
  if (!workspace.has_value()) {
    return Result::failure(workspace.error());
  }
  if (!lowercase_sha256(manifest_sha256)) {
    return Result::failure(
        invalid_argument("Sound Set manifest hash is not a lowercase sha256"));
  }
  auto stored = impl_->load(manifest_sha256);
  if (!stored.has_value()) {
    return stored;
  }
  if (stored.value().manifest.set_id != set_id ||
      stored.value().manifest.version != version) {
    return Result::failure(
        not_found("Sound Set identity is not in the Set Store"));
  }
  return stored;
}

foundation::Result<std::vector<std::byte>> SoundSetStore::read_artifact(
    std::string_view manifest_sha256,
    std::string_view artifact_sha256) const {
  using Result = foundation::Result<std::vector<std::byte>>;
  const auto workspace = impl_->validated_workspace();
  if (!workspace.has_value()) {
    return Result::failure(workspace.error());
  }
  if (!lowercase_sha256(manifest_sha256) ||
      !lowercase_sha256(artifact_sha256)) {
    return Result::failure(
        invalid_argument("Sound Set object hash is not a lowercase sha256"));
  }
  const auto stored = impl_->load(manifest_sha256);
  if (!stored.has_value()) {
    return Result::failure(stored.error());
  }
  const auto artifacts = Impl::unique_artifacts(stored.value().manifest);
  if (!artifacts.has_value()) {
    return Result::failure(artifacts.error());
  }
  const auto declared = std::find_if(
      artifacts.value().begin(),
      artifacts.value().end(),
      [artifact_sha256](const foundation::ArtifactRef& artifact) {
        return artifact.sha256 == artifact_sha256;
      });
  if (declared == artifacts.value().end()) {
    return Result::failure(
        not_found("Sound Set does not declare this Artifact"));
  }
  const auto path = impl_->sets_root() / std::string{manifest_sha256} /
                    std::string{artifact_sha256};
  auto bytes = impl_->platform->read_complete(path);
  if (!bytes.has_value()) {
    return Result::failure(bytes.error());
  }
  if (bytes.value().size() != declared->byte_length ||
      digest_of(bytes.value()) != artifact_sha256) {
    return Result::failure(
        content_mismatch("Stored Sound Set Artifact changed under the store"));
  }
  return Result::success(std::move(bytes.value()));
}

}  // namespace lmdj::project_io
