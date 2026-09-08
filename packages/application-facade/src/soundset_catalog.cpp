#include <lmdj/facade/application.hpp>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <map>
#include <mutex>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <picosha2.h>

namespace lmdj::facade {
namespace {

using foundation::Error;
using foundation::ErrorCode;

Error unavailable(std::string message) {
  return Error{
      ErrorCode::io_error,
      std::move(message),
      {{"reason",
        std::string{project_io::kSoundSetReasonCatalogUnavailable}}},
  };
}

Error content_mismatch(std::string message) {
  return Error{
      ErrorCode::io_error,
      std::move(message),
      {{"reason", std::string{project_io::kSoundSetReasonContentMismatch}}},
  };
}

Error invalid_argument(std::string message) {
  return Error{ErrorCode::invalid_argument, std::move(message)};
}

bool lowercase_sha256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(value.begin(), value.end(), [](char character) {
           return (character >= '0' && character <= '9') ||
                  (character >= 'a' && character <= 'f');
         });
}

std::string digest_of(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto *begin = reinterpret_cast<const unsigned char *>(bytes.data());
    hasher.process(begin, begin + bytes.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

int kind_key(project_io::CatalogObjectKind kind) {
  return kind == project_io::CatalogObjectKind::manifest ? 0 : 1;
}

std::string_view kind_name(project_io::CatalogObjectKind kind) {
  return kind == project_io::CatalogObjectKind::manifest ? "manifest" : "blob";
}

std::optional<project_io::CatalogObjectKind> parse_kind(
    std::string_view object_kind) {
  // Exactly the two locked kinds. There is no third kind to redirect to, and
  // the Catalog index is not one of them.
  if (object_kind == "manifest") {
    return project_io::CatalogObjectKind::manifest;
  }
  if (object_kind == "blob") {
    return project_io::CatalogObjectKind::blob;
  }
  return std::nullopt;
}

// The Catalog whose objects the Host resolves. It serves the bytes the Host
// supplied, records the addresses it was asked for and could not serve, and
// keeps the hash check that makes a supplied byte trustworthy. It resolves
// nothing itself: there is no endpoint, path, URL or archive here.
class SuppliedCatalog final : public project_io::CatalogTransport,
                              public SoundSetCatalogSource,
                              public SuppliedSoundSetCatalog {
public:
  SuppliedCatalog(
      std::uint64_t maximum_staged_bytes,
      std::size_t maximum_staged_objects)
      : maximum_staged_bytes_(maximum_staged_bytes),
        maximum_staged_objects_(maximum_staged_objects) {}

  foundation::Result<std::vector<std::byte>> read_object(
      const project_io::CatalogObjectRef &object,
      std::uint64_t maximum_bytes) override {
    using Result = foundation::Result<std::vector<std::byte>>;
    // The address is the whole request. A caller that cannot spell one has not
    // named an object this transport could ever resolve.
    if (!lowercase_sha256(object.sha256)) {
      return Result::failure(
          unavailable("Catalog object name is not a lowercase sha256"));
    }
    const std::lock_guard<std::mutex> guard(mutex_);
    const auto found =
        staged_.find(StagedKey{kind_key(object.kind), object.sha256});
    if (found == staged_.end()) {
      // Not a fault: the Host has not resolved this address yet. Record it so
      // the Host knows exactly what to ask its Catalog for, and fail the way
      // an unreachable Catalog fails.
      const auto already = std::any_of(
          pending_.begin(),
          pending_.end(),
          [&object](const PendingObject &candidate) {
            return candidate.object_kind == kind_name(object.kind) &&
                   candidate.sha256 == object.sha256;
          });
      if (!already && pending_.size() < maximum_staged_objects_) {
        pending_.push_back(
            PendingObject{std::string{kind_name(object.kind)}, object.sha256});
      }
      return Result::failure(
          unavailable("Catalog object has not been supplied"));
    }
    if (found->second.size() > maximum_bytes) {
      return Result::failure(
          unavailable("Catalog object exceeds the requested bound"));
    }
    // The address is the hash: prove that what the Host supplied is what Core
    // asked for. A Catalog that answered with other bytes is a content
    // mismatch, and re-asking would only produce the same bytes, so the
    // address is deliberately not recorded as pending.
    if (digest_of(found->second) != object.sha256) {
      return Result::failure(
          content_mismatch("Catalog object does not hash to its own address"));
    }
    return Result::success(found->second);
  }

  foundation::Result<std::vector<std::byte>> read_index(
      std::uint64_t maximum_bytes) override {
    using Result = foundation::Result<std::vector<std::byte>>;
    const std::lock_guard<std::mutex> guard(mutex_);
    if (!index_staged_) {
      index_pending_ = true;
      return Result::failure(
          unavailable("Catalog index has not been supplied"));
    }
    if (index_.size() > maximum_bytes) {
      return Result::failure(
          unavailable("Catalog index exceeds the requested bound"));
    }
    return Result::success(index_);
  }

  foundation::Result<bool> supply(
      std::string_view object_kind,
      std::string_view sha256,
      std::uint64_t offset,
      std::uint64_t byte_length,
      std::span<const std::byte> bytes) override {
    using Result = foundation::Result<bool>;
    const auto kind = parse_kind(object_kind);
    if (!kind.has_value()) {
      return Result::failure(
          invalid_argument("object_kind must be manifest or blob"));
    }
    if (!lowercase_sha256(sha256)) {
      return Result::failure(
          invalid_argument("sha256 must be 64 lowercase hex characters"));
    }
    const auto incoming = static_cast<std::uint64_t>(bytes.size());
    if (offset > byte_length || incoming > byte_length - offset) {
      return Result::failure(
          invalid_argument("Catalog object chunk runs past its byte_length"));
    }
    const std::lock_guard<std::mutex> guard(mutex_);
    if (byte_length > maximum_staged_bytes_) {
      return Result::failure(
          unavailable("Catalog object is larger than Host staging"));
    }
    const StagedKey key{kind_key(*kind), std::string{sha256}};
    if (offset == 0) {
      // A new object always starts a fresh run, so an abandoned partial can
      // never be appended to and read as whole.
      partial_key_ = key;
      partial_byte_length_ = byte_length;
      partial_.clear();
    } else if (
        !partial_key_.has_value() || *partial_key_ != key ||
        partial_byte_length_ != byte_length ||
        static_cast<std::uint64_t>(partial_.size()) != offset) {
      return Result::failure(
          invalid_argument("Catalog object chunk is out of order"));
    }
    partial_.insert(partial_.end(), bytes.begin(), bytes.end());
    if (static_cast<std::uint64_t>(partial_.size()) != byte_length) {
      return Result::success(false);
    }
    const auto existing = staged_.find(key);
    const auto replaced =
        existing == staged_.end()
            ? std::uint64_t{0}
            : static_cast<std::uint64_t>(existing->second.size());
    if (existing == staged_.end() &&
        staged_.size() >= maximum_staged_objects_) {
      discard_partial();
      return Result::failure(
          unavailable("Catalog staging holds too many objects"));
    }
    if (staged_bytes_ - replaced + byte_length > maximum_staged_bytes_) {
      discard_partial();
      return Result::failure(unavailable("Catalog staging is full"));
    }
    staged_bytes_ = staged_bytes_ - replaced + byte_length;
    staged_[key] = std::move(partial_);
    discard_partial();
    const auto name = kind_name(*kind);
    std::erase_if(pending_, [name, sha256](const PendingObject &candidate) {
      return candidate.object_kind == name && candidate.sha256 == sha256;
    });
    return Result::success(true);
  }

  foundation::Result<void> supply_index(
      std::span<const std::byte> bytes) override {
    using Result = foundation::Result<void>;
    if (static_cast<std::uint64_t>(bytes.size()) > maximum_staged_bytes_) {
      return Result::failure(
          unavailable("Catalog index is larger than staging"));
    }
    const std::lock_guard<std::mutex> guard(mutex_);
    index_.assign(bytes.begin(), bytes.end());
    index_staged_ = true;
    index_pending_ = false;
    return Result::success();
  }

  void forget_index() override {
    const std::lock_guard<std::mutex> guard(mutex_);
    index_.clear();
    index_staged_ = false;
  }

  PendingReads drain_pending() override {
    const std::lock_guard<std::mutex> guard(mutex_);
    PendingReads reads;
    reads.index = index_pending_;
    reads.objects = std::move(pending_);
    pending_.clear();
    index_pending_ = false;
    return reads;
  }

  void clear_staged() override {
    const std::lock_guard<std::mutex> guard(mutex_);
    staged_.clear();
    staged_bytes_ = 0;
    discard_partial();
  }

private:
  using StagedKey = std::pair<int, std::string>;

  void discard_partial() {
    partial_key_.reset();
    partial_byte_length_ = 0;
    partial_.clear();
  }

  std::mutex mutex_;
  std::uint64_t maximum_staged_bytes_;
  std::size_t maximum_staged_objects_;
  std::uint64_t staged_bytes_ = 0;
  std::map<StagedKey, std::vector<std::byte>> staged_;
  std::vector<std::byte> index_;
  bool index_staged_ = false;
  bool index_pending_ = false;
  std::vector<PendingObject> pending_;
  // The single object still arriving, if any.
  std::optional<StagedKey> partial_key_;
  std::uint64_t partial_byte_length_ = 0;
  std::vector<std::byte> partial_;
};

}  // namespace

SuppliedSoundSetCatalogHandle make_supplied_soundset_catalog(
    std::uint64_t maximum_staged_bytes,
    std::size_t maximum_staged_objects) {
  auto catalog = std::make_shared<SuppliedCatalog>(
      maximum_staged_bytes, maximum_staged_objects);
  return SuppliedSoundSetCatalogHandle{catalog, catalog, catalog};
}

}  // namespace lmdj::facade
