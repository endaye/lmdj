#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/foundation/error.hpp>

namespace lmdj::project_io {

// Stable details.reason tokens a Catalog read may carry. Both are locked by
// the Stage 11 design; neither adds a public lmdj.error.v1 code.
inline constexpr std::string_view kSoundSetReasonContentMismatch =
    "soundset_content_mismatch";
inline constexpr std::string_view kSoundSetReasonCatalogUnavailable =
    "catalog_unavailable";

// Sound Set v1 is a logical package, never an archive: a canonical manifest
// object plus the content-addressed Artifact blobs it references.
enum class CatalogObjectKind {
  manifest,
  blob,
};

// The complete address of a Catalog object. There is no path, URL, entry name
// or archive member here, so no adapter can be asked to unpack one.
struct CatalogObjectRef {
  CatalogObjectKind kind = CatalogObjectKind::manifest;
  std::string sha256;
};

// The Catalog boundary Core depends on. A local directory and a Host-side
// network endpoint are two implementations of this one interface; Core ships
// only the local one, so `packages/` gains no network dependency.
class CatalogTransport {
 public:
  CatalogTransport() = default;
  virtual ~CatalogTransport() = default;

  CatalogTransport(const CatalogTransport&) = delete;
  CatalogTransport& operator=(const CatalogTransport&) = delete;
  CatalogTransport(CatalogTransport&&) = delete;
  CatalogTransport& operator=(CatalogTransport&&) = delete;

  // The first of the two reads: the canonical Sound Set manifest object.
  foundation::Result<std::vector<std::byte>> read_manifest_object(
      std::string_view sha256,
      std::uint64_t maximum_bytes) {
    return read_object(
        CatalogObjectRef{CatalogObjectKind::manifest, std::string{sha256}},
        maximum_bytes);
  }

  // The second: a content-addressed Artifact blob.
  foundation::Result<std::vector<std::byte>> read_blob_object(
      std::string_view sha256,
      std::uint64_t maximum_bytes) {
    return read_object(
        CatalogObjectRef{CatalogObjectKind::blob, std::string{sha256}},
        maximum_bytes);
  }

  // Resolve one immutable object addressed only by {object_kind, sha256}, and
  // never produce more than maximum_bytes. An implementation that cannot
  // resolve the object fails with IO_ERROR and reason catalog_unavailable; one
  // that resolved bytes which do not hash to the requested sha256 fails with
  // IO_ERROR and reason soundset_content_mismatch.
  //
  // A transport reports "larger than my bound" as catalog_unavailable, because
  // it cannot know what the bound means to its caller. The Set Store therefore
  // asks for one byte more than the limit it is enforcing, so that an object
  // sitting exactly one byte over is returned and refused as a named resource
  // limit. An object further over than that is refused here instead, and is
  // indistinguishable from an unresolvable one -- both fail closed, and
  // neither ever allocates more than one byte past the limit.
  virtual foundation::Result<std::vector<std::byte>> read_object(
      const CatalogObjectRef& object,
      std::uint64_t maximum_bytes) = 0;
};

// The local directory adapter: the only adapter Core ships. It maps a
// validated lowercase sha256 to a single basename under `root`, opens it
// root-relative without following symbolic links, refuses anything that is not
// a regular file, reads within the caller's bound, and re-verifies the hash of
// what it read.
std::shared_ptr<CatalogTransport> make_local_directory_catalog_transport(
    std::filesystem::path root);

}  // namespace lmdj::project_io
