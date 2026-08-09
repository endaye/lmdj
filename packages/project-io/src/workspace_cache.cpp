#include <lmdj/project_io/workspace_cache.hpp>

#include <algorithm>
#include <charconv>
#include <cstdint>
#include <string>
#include <utility>

#include <picosha2.h>

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::string_view kCacheEnvelope = "lmdj.workspace-cache.v1\n";

foundation::Result<void> invalid_key() {
  return foundation::Result<void>::failure(
      Error{
          ErrorCode::invalid_argument,
          "Workspace cache key is not a generated key",
      });
}

bool valid_key(std::string_view key) {
  if (key.empty() || key.size() > 255) {
    return false;
  }
  const auto alphanumeric = [](unsigned char character) {
    return (character >= 'a' && character <= 'z') ||
           (character >= '0' && character <= '9');
  };
  if (!alphanumeric(static_cast<unsigned char>(key.front()))) {
    return false;
  }
  std::size_t segment_start = 0;
  for (std::size_t index = 0; index < key.size(); ++index) {
    const auto character = static_cast<unsigned char>(key.at(index));
    if (!(alphanumeric(character) || character == '.' || character == '_' ||
          character == '/' || character == '-')) {
      return false;
    }
    if (character != '/') {
      continue;
    }
    const auto segment = key.substr(segment_start, index - segment_start);
    if (segment.empty() || segment == "." || segment == "..") {
      return false;
    }
    segment_start = index + 1;
  }
  const auto tail = key.substr(segment_start);
  return !tail.empty() && tail != "." && tail != "..";
}

bool valid_root(const std::filesystem::path& root) {
  if (root.empty() || root.lexically_normal() != root ||
      root == root.root_path()) {
    return false;
  }
  return std::none_of(
      root.begin(),
      root.end(),
      [](const auto& segment) {
        return segment == "." || segment == "..";
      });
}

foundation::Result<void> validate_root(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& root) {
  if (!valid_root(root)) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Workspace cache root must be a normalized managed path",
        });
  }
  return platform.validate_managed_tree(root);
}

std::string digest(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* begin =
        reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(begin, begin + bytes.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

std::vector<std::byte> encode(std::span<const std::byte> bytes) {
  const auto header = std::string{kCacheEnvelope} +
                      std::to_string(bytes.size()) + "\n" + digest(bytes) +
                      "\n";
  std::vector<std::byte> encoded;
  encoded.reserve(header.size() + bytes.size());
  const auto* header_begin =
      reinterpret_cast<const std::byte*>(header.data());
  encoded.insert(encoded.end(), header_begin, header_begin + header.size());
  encoded.insert(encoded.end(), bytes.begin(), bytes.end());
  return encoded;
}

std::optional<std::vector<std::byte>> decode(
    const std::vector<std::byte>& encoded) {
  if (encoded.size() < kCacheEnvelope.size()) {
    return std::nullopt;
  }
  const auto text = std::string_view{
      reinterpret_cast<const char*>(encoded.data()), encoded.size()};
  if (!text.starts_with(kCacheEnvelope)) {
    return std::nullopt;
  }
  const auto size_begin = kCacheEnvelope.size();
  const auto size_end = text.find('\n', size_begin);
  const auto hash_end = size_end == std::string_view::npos
                            ? std::string_view::npos
                            : text.find('\n', size_end + 1);
  if (size_end == std::string_view::npos || hash_end == std::string_view::npos) {
    return std::nullopt;
  }
  std::uint64_t expected_size = 0;
  const auto size_text = text.substr(size_begin, size_end - size_begin);
  const auto parsed = std::from_chars(
      size_text.data(), size_text.data() + size_text.size(), expected_size);
  if (parsed.ec != std::errc{} ||
      parsed.ptr != size_text.data() + size_text.size()) {
    return std::nullopt;
  }
  const auto expected_hash =
      text.substr(size_end + 1, hash_end - size_end - 1);
  const auto payload_offset = hash_end + 1;
  if (expected_hash.size() != 64 ||
      expected_size != encoded.size() - payload_offset) {
    return std::nullopt;
  }
  std::vector<std::byte> payload(
      encoded.begin() + static_cast<std::ptrdiff_t>(payload_offset),
      encoded.end());
  if (digest(payload) != expected_hash) {
    return std::nullopt;
  }
  return payload;
}

foundation::Result<void> ensure_parent_directories(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& root,
    const std::filesystem::path& relative) {
  auto ensured = platform.ensure_directory(root);
  if (!ensured.has_value()) {
    return ensured;
  }
  auto current = root;
  for (const auto& segment : relative.parent_path()) {
    current /= segment;
    ensured = platform.ensure_directory(current);
    if (!ensured.has_value()) {
      return ensured;
    }
  }
  return foundation::Result<void>::success();
}

}  // namespace

WorkspaceCacheStore::WorkspaceCacheStore(std::filesystem::path root)
    : WorkspaceCacheStore(
          std::move(root), make_default_project_storage_platform()) {}

WorkspaceCacheStore::WorkspaceCacheStore(
    std::filesystem::path root,
    std::shared_ptr<ProjectStoragePlatform> platform)
    : root_(std::move(root)),
      platform_(platform != nullptr ? std::move(platform)
                                    : make_default_project_storage_platform()) {}

foundation::Result<std::optional<std::vector<std::byte>>>
WorkspaceCacheStore::read(std::string_view key) const {
  if (!valid_key(key)) {
    return foundation::Result<std::optional<std::vector<std::byte>>>::failure(
        invalid_key().error());
  }
  const auto root = validate_root(*platform_, root_);
  if (!root.has_value()) {
    return foundation::Result<std::optional<std::vector<std::byte>>>::failure(
        root.error());
  }
  const auto root_present = platform_->directory_exists(root_);
  if (!root_present.has_value()) {
    return foundation::Result<std::optional<std::vector<std::byte>>>::failure(
        root_present.error());
  }
  if (!root_present.value()) {
    return foundation::Result<std::optional<std::vector<std::byte>>>::success(
        std::nullopt);
  }
  const auto path = root_ / std::filesystem::path{key};
  const auto present = platform_->exists(path);
  if (!present.has_value()) {
    return foundation::Result<std::optional<std::vector<std::byte>>>::failure(
        present.error());
  }
  if (!present.value()) {
    return foundation::Result<std::optional<std::vector<std::byte>>>::success(
        std::nullopt);
  }
  const auto encoded = platform_->read_complete(path);
  if (!encoded.has_value()) {
    (void)platform_->remove(path);
    return foundation::Result<std::optional<std::vector<std::byte>>>::success(
        std::nullopt);
  }
  auto payload = decode(encoded.value());
  if (!payload.has_value()) {
    (void)platform_->remove(path);
    return foundation::Result<std::optional<std::vector<std::byte>>>::success(
        std::nullopt);
  }
  return foundation::Result<std::optional<std::vector<std::byte>>>::success(
      std::move(payload));
}

foundation::Result<void> WorkspaceCacheStore::write(
    std::string_view key,
    std::span<const std::byte> bytes) {
  if (!valid_key(key)) {
    return invalid_key();
  }
  auto root = validate_root(*platform_, root_);
  if (!root.has_value()) {
    return root;
  }
  const auto relative = std::filesystem::path{key};
  auto ensured = ensure_parent_directories(*platform_, root_, relative);
  if (!ensured.has_value()) {
    return ensured;
  }
  root = validate_root(*platform_, root_);
  if (!root.has_value()) {
    return root;
  }
  auto cache_lease = platform_->acquire_writer(root_);
  if (!cache_lease.has_value()) {
    return foundation::Result<void>::failure(cache_lease.error());
  }
  const auto encoded = encode(bytes);
  return platform_->replace_complete(root_ / relative, encoded);
}

foundation::Result<void> WorkspaceCacheStore::remove(std::string_view key) {
  if (!valid_key(key)) {
    return invalid_key();
  }
  const auto root = validate_root(*platform_, root_);
  if (!root.has_value()) {
    return root;
  }
  const auto root_present = platform_->directory_exists(root_);
  if (!root_present.has_value()) {
    return foundation::Result<void>::failure(root_present.error());
  }
  if (!root_present.value()) {
    return foundation::Result<void>::success();
  }
  auto cache_lease = platform_->acquire_writer(root_);
  if (!cache_lease.has_value()) {
    return foundation::Result<void>::failure(cache_lease.error());
  }
  return platform_->remove(root_ / std::filesystem::path{key});
}

}  // namespace lmdj::project_io
