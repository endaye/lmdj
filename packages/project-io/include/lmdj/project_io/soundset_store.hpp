#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/soundset_manifest.hpp>
#include <lmdj/project_io/soundset_catalog_transport.hpp>
#include <lmdj/project_io/storage_platform.hpp>

namespace lmdj::project_io {

// A Host resource limit refusal is a Host capacity fact, not a fault in the
// Set, and the plan locks no details.reason token for it. It therefore reuses
// the repository's existing limit-refusal shape rather than minting new
// vocabulary: IO_ERROR (the code S11-D10 already gives the Catalog family)
// carrying {"resource", "observed", "limit"}, exactly as
// audio-runtime's preparation_limit() does. The Application Facade already
// allowlists that triple for public exposure, so a Host reads the refusal
// without any new Contract surface. `resource` is the Host manifest key that
// refused, one of the four SoundSetStoreLimits field names below.

// The four Host manifest limits of S11-D7. Every one of them is decided
// before an allocation or a download, and a Set that exceeds any of them never
// becomes visible.
struct SoundSetStoreLimits {
  // Bound on the canonical manifest object.
  std::uint64_t maximum_soundset_manifest_bytes = 0;
  // Bound on a single Artifact blob.
  std::uint64_t maximum_soundset_blob_bytes = 0;
  // Bound on one Set's deduplicated total: canonical manifest bytes plus the
  // byte_length of each unique Artifact hash, counted once.
  std::uint64_t maximum_soundset_unique_bytes = 0;
  // Bound on the whole staging area, including bytes an earlier interrupted
  // acquisition left behind.
  std::uint64_t maximum_soundset_staging_bytes = 0;
};

// What the Catalog declares about a Set. Catalog endpoints, cache and Set
// Store are Workspace/Host state and never enter Project Truth.
struct SoundSetCatalogEntry {
  std::string set_id;
  std::string version;
  std::string manifest_sha256;
  std::uint64_t total_bytes = 0;
  std::optional<foundation::CatalogLicenseSummary> license_summary;
};

// A Set that is published in the read-only Set Store.
struct StoredSoundSet {
  foundation::SoundSetManifest manifest;
  std::uint64_t total_bytes = 0;
};

// The Workspace read-only Set Store. It holds verified, content-addressed
// bytes; it does not decode audio, and it knows nothing about Projects, Banks
// or Pads.
class SoundSetStore final {
 public:
  SoundSetStore(
      std::filesystem::path workspace_root,
      SoundSetStoreLimits limits);
  SoundSetStore(
      std::filesystem::path workspace_root,
      SoundSetStoreLimits limits,
      std::shared_ptr<ProjectStoragePlatform> platform);
  ~SoundSetStore();

  SoundSetStore(const SoundSetStore&) = delete;
  SoundSetStore& operator=(const SoundSetStore&) = delete;
  SoundSetStore(SoundSetStore&&) = delete;
  SoundSetStore& operator=(SoundSetStore&&) = delete;

  // Fetch, verify and atomically publish the declared Set. Idempotent: a Set
  // already published is returned without touching the Catalog. Every unique
  // Artifact hash is fetched once however many slots reference it.
  foundation::Result<StoredSoundSet> acquire(
      CatalogTransport& transport,
      const SoundSetCatalogEntry& entry);

  // Published Sets, ordered by manifest sha256.
  foundation::Result<std::vector<StoredSoundSet>> list() const;

  foundation::Result<StoredSoundSet> read(
      std::string_view set_id,
      std::string_view version,
      std::string_view manifest_sha256) const;

  // Bytes of one Artifact the published manifest declares.
  foundation::Result<std::vector<std::byte>> read_artifact(
      std::string_view manifest_sha256,
      std::string_view artifact_sha256) const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::project_io
