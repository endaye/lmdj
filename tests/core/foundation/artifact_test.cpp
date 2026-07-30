#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <type_traits>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>
#include <lmdj/foundation/json.hpp>

#include "tests/core/support/test.hpp"

namespace {

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-foundation-test-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

void writes_text(const std::filesystem::path& path, std::string_view text) {
  std::ofstream stream(path, std::ios::binary);
  stream.write(text.data(), static_cast<std::streamsize>(text.size()));
  if (!stream) {
    throw std::runtime_error("failed to write test fixture");
  }
}

void test_describe_artifact_streams_sha256() {
  TempDirectory temp;
  const auto artifact_path = temp.path() / "abc.bin";
  writes_text(artifact_path, "abc");

  auto described =
      lmdj::foundation::describe_artifact(
          artifact_path, "application/octet-stream");

  LMDJ_CHECK(described.has_value());
  LMDJ_CHECK(
      described.value().sha256 ==
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  LMDJ_CHECK(described.value().media_type == "application/octet-stream");
  LMDJ_CHECK(described.value().byte_length == 3);
}

void test_describe_artifact_rejects_non_files() {
  TempDirectory temp;

  const auto missing =
      lmdj::foundation::describe_artifact(
          temp.path() / "missing.bin", "application/octet-stream");
  LMDJ_CHECK(!missing.has_value());
  LMDJ_CHECK(
      missing.error().code == lmdj::foundation::ErrorCode::not_found);

  const auto directory =
      lmdj::foundation::describe_artifact(
          temp.path(), "application/octet-stream");
  LMDJ_CHECK(!directory.has_value());
  LMDJ_CHECK(
      directory.error().code == lmdj::foundation::ErrorCode::not_found);
}

void test_canonical_json_recursively_sorts_keys() {
  const nlohmann::json value = {
      {"z", 1},
      {"a", {{"y", 2}, {"b", 3}}},
      {"list", {{{"z", 4}, {"a", 5}}}},
  };

  LMDJ_CHECK(
      lmdj::foundation::canonical_json(value) ==
      R"({"a":{"b":3,"y":2},"list":[{"a":5,"z":4}],"z":1})");
}

void test_artifact_ref_round_trips_through_json() {
  const lmdj::foundation::ArtifactRef original{
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      "application/octet-stream",
      3,
  };

  const nlohmann::json encoded = original;
  LMDJ_CHECK(
      lmdj::foundation::canonical_json(encoded) ==
      R"({"byte_length":3,"media_type":"application/octet-stream","sha256":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"})");

  const auto decoded = encoded.get<lmdj::foundation::ArtifactRef>();
  LMDJ_CHECK(decoded == original);
}

void test_public_error_codes_have_stable_names() {
  using lmdj::foundation::ErrorCode;
  const std::array expected{
      std::pair{ErrorCode::invalid_argument, "INVALID_ARGUMENT"},
      std::pair{ErrorCode::not_found, "NOT_FOUND"},
      std::pair{ErrorCode::revision_conflict, "REVISION_CONFLICT"},
      std::pair{ErrorCode::duplicate_id, "DUPLICATE_ID"},
      std::pair{ErrorCode::unsupported_audio, "UNSUPPORTED_AUDIO"},
      std::pair{ErrorCode::missing_asset, "MISSING_ASSET"},
      std::pair{ErrorCode::invalid_project, "INVALID_PROJECT"},
      std::pair{ErrorCode::cook_failed, "COOK_FAILED"},
      std::pair{ErrorCode::provider_not_found, "PROVIDER_NOT_FOUND"},
      std::pair{ErrorCode::provider_failed, "PROVIDER_FAILED"},
      std::pair{ErrorCode::permission_denied, "PERMISSION_DENIED"},
      std::pair{ErrorCode::io_error, "IO_ERROR"},
      std::pair{ErrorCode::internal_error, "INTERNAL_ERROR"},
  };

  for (const auto& [code, name] : expected) {
    LMDJ_CHECK(lmdj::foundation::error_code_name(code) == name);
  }
}

void test_void_result_preserves_typed_failure() {
  auto success = lmdj::foundation::Result<void>::success();
  LMDJ_CHECK(success.has_value());

  auto failure = lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          lmdj::foundation::ErrorCode::invalid_argument,
          "invalid proof input",
      });
  LMDJ_CHECK(!failure.has_value());
  LMDJ_CHECK(
      failure.error().code ==
      lmdj::foundation::ErrorCode::invalid_argument);
}

void test_ids_are_strong_types() {
  static_assert(
      !std::is_same_v<
          lmdj::foundation::ProjectId,
          lmdj::foundation::AssetId>);
  static_assert(
      !std::is_convertible_v<
          lmdj::foundation::ProjectId,
          lmdj::foundation::AssetId>);

  const lmdj::foundation::ProjectId project_id{
      "00000000-0000-4000-8000-000000000001"};
  LMDJ_CHECK(
      project_id.value() ==
      "00000000-0000-4000-8000-000000000001");
}

}  // namespace

int main() {
  try {
    test_describe_artifact_streams_sha256();
    test_describe_artifact_rejects_non_files();
    test_canonical_json_recursively_sorts_keys();
    test_artifact_ref_round_trips_through_json();
    test_public_error_codes_have_stable_names();
    test_void_result_preserves_typed_failure();
    test_ids_are_strong_types();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "foundation artifact tests: PASS\n";
  return 0;
}
