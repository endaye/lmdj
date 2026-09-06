// Local directory Catalog adapter: the only adapter Core ships. It resolves
// {object_kind, sha256} to a single basename under a configured root, opens it
// without following symbolic links, refuses anything that is not a regular
// file, reads within a byte bound, and re-verifies the hash of what it read.
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

#include <picosha2.h>

#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/soundset_catalog_transport.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::ErrorCode;
using lmdj::project_io::CatalogObjectKind;
using lmdj::project_io::CatalogObjectRef;
using lmdj::project_io::make_local_directory_catalog_transport;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-soundset-local-adapter-test-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  TempDirectory(const TempDirectory&) = delete;
  TempDirectory& operator=(const TempDirectory&) = delete;

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::string sha256_hex(std::string_view bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* begin = reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(begin, begin + bytes.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

void write_file(const std::filesystem::path& path, std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

std::string text_of(const std::vector<std::byte>& bytes) {
  return {
      reinterpret_cast<const char*>(bytes.data()),
      bytes.size(),
  };
}

std::string reason_of(const lmdj::foundation::Error& error) {
  if (!error.details.is_object() || !error.details.contains("reason")) {
    return {};
  }
  return error.details.at("reason").get<std::string>();
}

// The adapter never accepts a path: only a validated lowercase sha256 that it
// maps to one basename under its own root.
void test_object_names_that_are_not_a_lowercase_sha256_are_refused() {
  TempDirectory root;
  auto transport = make_local_directory_catalog_transport(root.path());

  const std::string payload = "kick";
  const auto digest = sha256_hex(payload);
  write_file(root.path() / digest, payload);

  const std::vector<std::string> refused{
      "",
      "/",
      "..",
      "../" + digest,
      digest + "/",
      std::string{"/"} + digest,
      "subdir/" + digest,
      digest.substr(0, 63),
      digest + "0",
      // Uppercase hex is a second spelling of one object: refuse it rather
      // than let two names address the same content.
      std::string(63, 'a') + "F",
      std::string(64, 'z'),
  };
  for (const auto& name : refused) {
    const auto object = transport->read_object(
        CatalogObjectRef{CatalogObjectKind::blob, name}, 1024);
    LMDJ_CHECK(!object.has_value());
    LMDJ_CHECK(object.error().code == ErrorCode::io_error);
    LMDJ_CHECK(reason_of(object.error()) == "catalog_unavailable");
  }

  const auto accepted = transport->read_blob_object(digest, 1024);
  LMDJ_CHECK(accepted.has_value());
  LMDJ_CHECK(text_of(accepted.value()) == payload);
}

// Both reads resolve the same way; neither takes an archive, a path or a URL.
void test_both_reads_resolve_by_object_kind_and_hash() {
  TempDirectory root;
  auto transport = make_local_directory_catalog_transport(root.path());

  const std::string manifest = "{\"contract\":\"lmdj.soundset.v1\"}";
  const std::string blob = "RIFF....WAVE";
  write_file(root.path() / sha256_hex(manifest), manifest);
  write_file(root.path() / sha256_hex(blob), blob);

  const auto read_manifest =
      transport->read_manifest_object(sha256_hex(manifest), 4096);
  LMDJ_CHECK(read_manifest.has_value());
  LMDJ_CHECK(text_of(read_manifest.value()) == manifest);

  const auto read_blob = transport->read_blob_object(sha256_hex(blob), 4096);
  LMDJ_CHECK(read_blob.has_value());
  LMDJ_CHECK(text_of(read_blob.value()) == blob);
}

void test_symbolic_link_and_non_regular_file_are_refused() {
  TempDirectory root;
  TempDirectory outside;
  auto transport = make_local_directory_catalog_transport(root.path());

  const std::string escaped = "escaped";
  const auto escaped_digest = sha256_hex(escaped);
  write_file(outside.path() / "target", escaped);
  std::error_code link_error;
  std::filesystem::create_symlink(
      outside.path() / "target", root.path() / escaped_digest, link_error);
  LMDJ_CHECK(!link_error);

  const auto followed = transport->read_blob_object(escaped_digest, 1024);
  LMDJ_CHECK(!followed.has_value());
  LMDJ_CHECK(followed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(reason_of(followed.error()) == "catalog_unavailable");

  // A directory named like a valid object is not a readable object either.
  const auto directory_digest = sha256_hex("directory");
  std::filesystem::create_directories(root.path() / directory_digest);
  const auto directory = transport->read_blob_object(directory_digest, 1024);
  LMDJ_CHECK(!directory.has_value());
  LMDJ_CHECK(directory.error().code == ErrorCode::io_error);
  LMDJ_CHECK(reason_of(directory.error()) == "catalog_unavailable");

  // A root that is itself a symbolic link is refused before any child open.
  TempDirectory link_parent;
  const auto linked_root = link_parent.path() / "root";
  std::filesystem::create_directory_symlink(
      root.path(), linked_root, link_error);
  LMDJ_CHECK(!link_error);
  auto linked = make_local_directory_catalog_transport(linked_root);
  const auto through_link = linked->read_blob_object(escaped_digest, 1024);
  LMDJ_CHECK(!through_link.has_value());
  LMDJ_CHECK(reason_of(through_link.error()) == "catalog_unavailable");
}

void test_missing_object_is_catalog_unavailable() {
  TempDirectory root;
  auto transport = make_local_directory_catalog_transport(root.path());
  const auto absent = transport->read_blob_object(sha256_hex("absent"), 1024);
  LMDJ_CHECK(!absent.has_value());
  LMDJ_CHECK(absent.error().code == ErrorCode::io_error);
  LMDJ_CHECK(reason_of(absent.error()) == "catalog_unavailable");
}

// The bound is checked against the file's own size before any allocation, so
// an oversized object never becomes a buffer.
void test_read_is_bounded_before_allocation() {
  TempDirectory root;
  auto transport = make_local_directory_catalog_transport(root.path());
  const std::string payload(4096, 'k');
  const auto digest = sha256_hex(payload);
  write_file(root.path() / digest, payload);

  const auto exact = transport->read_blob_object(digest, payload.size());
  LMDJ_CHECK(exact.has_value());
  LMDJ_CHECK(exact.value().size() == payload.size());

  const auto over = transport->read_blob_object(digest, payload.size() - 1);
  LMDJ_CHECK(!over.has_value());
  LMDJ_CHECK(over.error().code == ErrorCode::io_error);
  LMDJ_CHECK(reason_of(over.error()) == "catalog_unavailable");
}

// The adapter re-verifies what it opened: the bytes must hash to the name they
// were requested under, or the object is a content mismatch, not a miss.
void test_opened_bytes_must_match_the_requested_hash() {
  TempDirectory root;
  auto transport = make_local_directory_catalog_transport(root.path());
  const std::string payload = "snare";
  const auto digest = sha256_hex(payload);
  write_file(root.path() / digest, "snarf");

  const auto tampered = transport->read_blob_object(digest, 1024);
  LMDJ_CHECK(!tampered.has_value());
  LMDJ_CHECK(tampered.error().code == ErrorCode::io_error);
  LMDJ_CHECK(reason_of(tampered.error()) == "soundset_content_mismatch");
}

void test_adapter_root_must_be_a_normalized_absolute_directory() {
  TempDirectory root;
  const std::string payload = "hat";
  const auto digest = sha256_hex(payload);
  write_file(root.path() / digest, payload);

  auto relative = make_local_directory_catalog_transport("catalog");
  LMDJ_CHECK(!relative->read_blob_object(digest, 1024).has_value());

  auto dotted =
      make_local_directory_catalog_transport(root.path() / ".." / "catalog");
  LMDJ_CHECK(!dotted->read_blob_object(digest, 1024).has_value());

  auto missing = make_local_directory_catalog_transport(root.path() / "absent");
  const auto absent = missing->read_blob_object(digest, 1024);
  LMDJ_CHECK(!absent.has_value());
  LMDJ_CHECK(reason_of(absent.error()) == "catalog_unavailable");
}

}  // namespace

int main() {
  try {
    test_object_names_that_are_not_a_lowercase_sha256_are_refused();
    test_both_reads_resolve_by_object_kind_and_hash();
    test_symbolic_link_and_non_regular_file_are_refused();
    test_missing_object_is_catalog_unavailable();
    test_read_is_bounded_before_allocation();
    test_opened_bytes_must_match_the_requested_hash();
    test_adapter_root_must_be_a_normalized_absolute_directory();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "sound set local catalog adapter tests: PASS\n";
  return 0;
}
