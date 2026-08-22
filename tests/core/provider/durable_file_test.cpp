#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>

#include <lmdj/foundation/error.hpp>

#include "packages/provider-sdk/src/durable_file.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::ErrorCode;
using lmdj::provider::detail::publish_new_link;
using lmdj::provider::detail::publish_replace;
using lmdj::provider::detail::sync_descriptor;
using lmdj::provider::detail::sync_directory;
using lmdj::provider::detail::write_bytes_durable;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-durable-file-test-" + std::to_string(nonce));
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

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

void test_sync_descriptor_rejects_invalid_fd() {
  const auto result =
      sync_descriptor(-1, "packages/provider-sdk/src/durable_file.cpp");
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      result.error().details.at("path") ==
      "packages/provider-sdk/src/durable_file.cpp");
}

void test_sync_directory_rejects_missing_path() {
  TempDirectory temp;
  const auto missing = temp.path() / "missing";
  const auto result = sync_directory(missing);
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::io_error);
}

void test_write_bytes_durable_round_trips_and_rejects_existing() {
  TempDirectory temp;
  const auto path = temp.path() / "evidence.bin";
  const auto first = write_bytes_durable(path, "attempt-bytes");
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(read_bytes(path) == "attempt-bytes");
  const auto second = write_bytes_durable(path, "other");
  LMDJ_CHECK(!second.has_value());
  LMDJ_CHECK(second.error().code == ErrorCode::io_error);
  LMDJ_CHECK(read_bytes(path) == "attempt-bytes");
}

void test_publish_new_link_syncs_then_removes_temp() {
  TempDirectory temp;
  const auto staged = temp.path() / ".record.json.tmp";
  const auto final_path = temp.path() / "record.json";
  LMDJ_CHECK(write_bytes_durable(staged, "{\"ok\":true}\n").has_value());
  LMDJ_CHECK(
      publish_new_link(
          staged, final_path, ErrorCode::duplicate_id)
          .has_value());
  LMDJ_CHECK(read_bytes(final_path) == "{\"ok\":true}\n");
  LMDJ_CHECK(!std::filesystem::exists(staged));
}

void test_publish_new_link_conflict_uses_existing_code() {
  TempDirectory temp;
  const auto staged = temp.path() / ".record.json.tmp";
  const auto final_path = temp.path() / "record.json";
  LMDJ_CHECK(write_bytes_durable(staged, "left\n").has_value());
  LMDJ_CHECK(write_bytes_durable(final_path, "right\n").has_value());
  const auto published = publish_new_link(
      staged, final_path, ErrorCode::duplicate_id);
  LMDJ_CHECK(!published.has_value());
  LMDJ_CHECK(published.error().code == ErrorCode::duplicate_id);
  LMDJ_CHECK(!std::filesystem::exists(staged));
  LMDJ_CHECK(read_bytes(final_path) == "right\n");
}

void test_publish_replace_replaces_and_removes_temp() {
  TempDirectory temp;
  const auto staged = temp.path() / ".artifact.tmp";
  const auto final_path = temp.path() / "deadbeef";
  LMDJ_CHECK(write_bytes_durable(final_path, "old").has_value());
  LMDJ_CHECK(write_bytes_durable(staged, "new-bytes").has_value());
  LMDJ_CHECK(publish_replace(staged, final_path).has_value());
  LMDJ_CHECK(read_bytes(final_path) == "new-bytes");
  LMDJ_CHECK(!std::filesystem::exists(staged));
}

void test_durable_publish_unpublishable_target_leaves_no_final_or_temp() {
  TempDirectory temp;
  const auto persist_staged = temp.path() / ".record.json.tmp";
  const auto persist_final = temp.path() / "missing-persist" / "record.json";
  LMDJ_CHECK(write_bytes_durable(persist_staged, "{\"ok\":true}\n").has_value());
  const auto persisted = publish_new_link(
      persist_staged, persist_final, ErrorCode::duplicate_id);
  LMDJ_CHECK(!persisted.has_value());
  LMDJ_CHECK(persisted.error().code == ErrorCode::io_error);
  LMDJ_CHECK(!std::filesystem::exists(persist_staged));
  LMDJ_CHECK(!std::filesystem::exists(persist_final));

  const auto mint_staged = temp.path() / ".artifact.tmp";
  const auto mint_final = temp.path() / "missing-mint" / "deadbeef";
  LMDJ_CHECK(write_bytes_durable(mint_staged, "mint-bytes").has_value());
  const auto minted = publish_replace(mint_staged, mint_final);
  LMDJ_CHECK(!minted.has_value());
  LMDJ_CHECK(minted.error().code == ErrorCode::io_error);
  LMDJ_CHECK(!std::filesystem::exists(mint_staged));
  LMDJ_CHECK(!std::filesystem::exists(mint_final));
}

}  // namespace

int main() {
  try {
    test_sync_descriptor_rejects_invalid_fd();
    test_sync_directory_rejects_missing_path();
    test_write_bytes_durable_round_trips_and_rejects_existing();
    test_publish_new_link_syncs_then_removes_temp();
    test_publish_new_link_conflict_uses_existing_code();
    test_publish_replace_replaces_and_removes_temp();
    test_durable_publish_unpublishable_target_leaves_no_final_or_temp();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "provider durable file tests: PASS\n";
  return 0;
}
