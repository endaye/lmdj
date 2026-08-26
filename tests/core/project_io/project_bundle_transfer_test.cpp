#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_bundle_transfer.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::project_io::ProjectBundleTransfer;
using lmdj::project_io::ProjectStoragePlatform;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000101";
constexpr std::string_view kPatternId =
    "00000000-0000-4000-8000-000000000102";

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-project-bundle-transfer-test-" +
             std::to_string(nonce));
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

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" + std::string(12 - tail.size(), '0') +
         tail;
}

std::vector<std::byte> bytes(std::string_view text) {
  return {
      reinterpret_cast<const std::byte*>(text.data()),
      reinterpret_cast<const std::byte*>(text.data() + text.size()),
  };
}

std::string read_text(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  return {
      std::istreambuf_iterator<char>{stream},
      std::istreambuf_iterator<char>{},
  };
}

std::string sha256(std::span<const std::byte> input) {
  picosha2::hash256_one_by_one hasher;
  if (!input.empty()) {
    const auto* begin =
        reinterpret_cast<const unsigned char*>(input.data());
    hasher.process(begin, begin + input.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

std::string sha256(std::string_view input) {
  return sha256({
      reinterpret_cast<const std::byte*>(input.data()),
      input.size(),
  });
}

void create_project(
    const std::filesystem::path& path,
    std::string_view project_id = kProjectId,
    std::string_view pattern_id = kPatternId) {
  auto state = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{std::string{project_id}}, 120);
  LMDJ_CHECK(state.has_value());
  lmdj::project_io::ProjectStore store;
  LMDJ_CHECK(store.create(path, state.value()).has_value());
  const lmdj::domain::CreatePattern command{
      lmdj::domain::CommandMeta{
          lmdj::foundation::CommandId{uuid(103)}, 0},
      lmdj::domain::Pattern{
          lmdj::foundation::PatternId{std::string{pattern_id}}, 1, {}},
  };
  LMDJ_CHECK(
      store.execute(path, lmdj::domain::Command{command}).has_value());
}

struct TransferFixture {
  std::string index;
  std::vector<std::vector<std::byte>> entries;
  std::string digest;
};

TransferFixture build_fixture(
    const std::filesystem::path& source,
    std::string_view project_id = kProjectId) {
  struct SourceEntry {
    std::string path;
    std::vector<std::byte> data;
  };
  std::vector<SourceEntry> source_entries;
  for (const auto& entry :
       std::filesystem::recursive_directory_iterator(source)) {
    LMDJ_CHECK(!entry.is_symlink());
    if (!entry.is_regular_file()) {
      continue;
    }
    const auto relative =
        std::filesystem::relative(entry.path(), source).generic_string();
    const auto text = read_text(entry.path());
    source_entries.push_back({relative, bytes(text)});
  }
  std::sort(
      source_entries.begin(),
      source_entries.end(),
      [](const auto& left, const auto& right) {
        return std::lexicographical_compare(
            left.path.begin(),
            left.path.end(),
            right.path.begin(),
            right.path.end(),
            [](char left_byte, char right_byte) {
              return static_cast<unsigned char>(left_byte) <
                     static_cast<unsigned char>(right_byte);
            });
      });

  auto encoded_entries = nlohmann::json::array();
  std::uint64_t offset = 0;
  std::vector<std::vector<std::byte>> payloads;
  for (auto& item : source_entries) {
    encoded_entries.push_back(
        {
            {"bytes", item.data.size()},
            {"offset", offset},
            {"path", item.path},
            {"sha256", sha256(item.data)},
        });
    offset += item.data.size();
    payloads.push_back(std::move(item.data));
  }
  nlohmann::json index{
      {"bundle_digest", std::string(64, '0')},
      {"compression", "none"},
      {"contract", "lmdj.project-bundle.v1"},
      {"contract_version", "1.1.0"},
      {"entries", std::move(encoded_entries)},
      {"project_contract", "lmdj.project.v3"},
      {"project_id", project_id},
      {"uncompressed_bytes", offset},
  };
  auto digest_source = index;
  digest_source.erase("bundle_digest");
  const auto digest = sha256(lmdj::foundation::canonical_json(digest_source));
  index["bundle_digest"] = digest;
  return {
      lmdj::foundation::canonical_json(index),
      std::move(payloads),
      digest,
  };
}

std::string canonical_index(nlohmann::json index) {
  auto digest_source = index;
  digest_source.erase("bundle_digest");
  index["bundle_digest"] =
      sha256(lmdj::foundation::canonical_json(digest_source));
  return lmdj::foundation::canonical_json(index);
}

lmdj::foundation::Result<std::optional<lmdj::project_io::BundleImportIdentity>>
stage_index(
    ProjectBundleTransfer& transfer,
    const std::filesystem::path& workspace,
    const std::string& token,
    const std::string& index) {
  const auto begun = transfer.begin(
      workspace, token, index.size(), sha256(index));
  LMDJ_CHECK(begun.has_value());
  return transfer.append_index(
      token,
      0,
      std::span<const std::byte>{
          reinterpret_cast<const std::byte*>(index.data()), index.size()},
      true);
}

void append_fixture(
    ProjectBundleTransfer& transfer,
    const std::filesystem::path& workspace,
    std::string token,
    const TransferFixture& fixture) {
  auto begun = transfer.begin(
      workspace,
      token,
      fixture.index.size(),
      sha256(fixture.index));
  LMDJ_CHECK(begun.has_value());
  const auto split = std::min<std::size_t>(7, fixture.index.size());
  auto first = transfer.append_index(
      token,
      0,
      std::span<const std::byte>{
          reinterpret_cast<const std::byte*>(fixture.index.data()), split},
      split == fixture.index.size());
  LMDJ_CHECK(first.has_value());
  if (split != fixture.index.size()) {
    LMDJ_CHECK(!first.value().has_value());
    first = transfer.append_index(
        token,
        split,
        std::span<const std::byte>{
            reinterpret_cast<const std::byte*>(fixture.index.data() + split),
            fixture.index.size() - split},
        true);
    LMDJ_CHECK(first.has_value());
  }
  LMDJ_CHECK(first.value().has_value());
  LMDJ_CHECK(first.value()->bundle_digest == fixture.digest);

  for (std::size_t entry_index = 0;
       entry_index < fixture.entries.size();
       ++entry_index) {
    const auto& payload = fixture.entries.at(entry_index);
    if (payload.empty()) {
      LMDJ_CHECK(
          transfer.append_entry(token, entry_index, 0, {}, true)
              .has_value());
      continue;
    }
    std::size_t offset = 0;
    std::size_t chunk_count = 0;
    const auto chunk_bytes = (payload.size() + 1) / 2;
    while (offset < payload.size()) {
      const auto count = std::min(chunk_bytes, payload.size() - offset);
      LMDJ_CHECK(
          transfer.append_entry(
              token,
              entry_index,
              offset,
              std::span<const std::byte>{payload.data() + offset, count},
              offset + count == payload.size())
              .has_value());
      offset += count;
      ++chunk_count;
    }
    LMDJ_CHECK(chunk_count <= 2);
  }
}

class FaultPlatform final : public ProjectStoragePlatform {
 public:
  explicit FaultPlatform(std::shared_ptr<ProjectStoragePlatform> inner)
      : inner_(std::move(inner)) {}

  bool fail_next_publish = false;

  lmdj::foundation::Result<std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& path) override {
    return inner_->acquire_writer(path);
  }
  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    return inner_->ensure_directory(path);
  }
  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    return inner_->exists(path);
  }
  lmdj::foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const override {
    return inner_->directory_exists(path);
  }
  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    return inner_->byte_length(path);
  }
  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    return inner_->read_complete(path);
  }
  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> value) override {
    return inner_->create_immutable(path, value);
  }
  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> value) override {
    return inner_->replace_complete(path, value);
  }
  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t prefix,
      std::span<const std::byte> value) override {
    return inner_->append_durable(path, prefix, value);
  }
  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    return inner_->remove(path);
  }
  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    return inner_->list_names(path);
  }
  lmdj::foundation::Result<std::vector<std::string>> list_directories(
      const std::filesystem::path& path) const override {
    return inner_->list_directories(path);
  }
  lmdj::foundation::Result<void> remove_tree(
      const std::filesystem::path& path) override {
    return inner_->remove_tree(path);
  }
  lmdj::foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path& staging,
      const std::filesystem::path& destination) override {
    if (fail_next_publish) {
      fail_next_publish = false;
      return lmdj::foundation::Result<void>::failure(
          Error{ErrorCode::io_error, "injected directory publish failure"});
    }
    return inner_->publish_directory_if_absent(staging, destination);
  }
  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& path) const override {
    return inner_->validate_managed_tree(path);
  }

 private:
  std::shared_ptr<ProjectStoragePlatform> inner_;
};

void test_streamed_import_is_atomic_discoverable_and_idempotent() {
  TempDirectory temp;
  const auto workspace = temp.path() / "workspace";
  const auto source = temp.path() / "source.lmdj";
  create_project(source);
  const auto fixture = build_fixture(source);
  auto platform = lmdj::project_io::make_native_project_storage_platform(
      temp.path() / "leases");
  ProjectBundleTransfer transfer{platform};

  LMDJ_CHECK(transfer.list_local_projects(workspace).value().empty());
  const auto token = uuid(201);
  append_fixture(transfer, workspace, token, fixture);
  LMDJ_CHECK(transfer.list_local_projects(workspace).value().empty());
  const auto committed = transfer.commit(token);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().project_id.value() == kProjectId);
  LMDJ_CHECK(committed.value().pattern_id.value() == kPatternId);
  LMDJ_CHECK(committed.value().revision == 1);
  LMDJ_CHECK(committed.value().bpm == 120);
  LMDJ_CHECK(committed.value().asset_count == 0);
  LMDJ_CHECK(committed.value().assigned_pad_count == 0);
  LMDJ_CHECK(committed.value().bundle_digest == fixture.digest);

  const auto listed = transfer.list_local_projects(workspace);
  LMDJ_CHECK(listed.has_value());
  LMDJ_CHECK(listed.value().size() == 1);
  LMDJ_CHECK(listed.value().front() == committed.value());

  const auto retry_token = uuid(202);
  append_fixture(transfer, workspace, retry_token, fixture);
  const auto idempotent = transfer.commit(retry_token);
  LMDJ_CHECK(idempotent.has_value());
  LMDJ_CHECK(idempotent.value() == committed.value());
  LMDJ_CHECK(
      !platform
           ->directory_exists(
               workspace / ".lmdj-host/import-staging" / retry_token)
           .value());
}

void test_validation_abort_cleanup_collision_and_contention() {
  TempDirectory temp;
  const auto workspace = temp.path() / "workspace";
  const auto source = temp.path() / "source.lmdj";
  create_project(source);
  const auto fixture = build_fixture(source);
  const auto metadata = temp.path() / "leases";
  auto first_platform =
      lmdj::project_io::make_native_project_storage_platform(metadata);
  auto second_platform =
      lmdj::project_io::make_native_project_storage_platform(metadata);
  ProjectBundleTransfer first{first_platform};
  ProjectBundleTransfer second{second_platform};

  LMDJ_CHECK(
      !first
           .begin(
               workspace,
               "not-a-token",
               fixture.index.size(),
               sha256(fixture.index))
           .has_value());
  LMDJ_CHECK(
      !first
           .begin(
               workspace,
               uuid(210),
               4'194'305,
               sha256(fixture.index))
           .has_value());

  const auto held_token = uuid(211);
  LMDJ_CHECK(
      first
          .begin(
              workspace,
              held_token,
              fixture.index.size(),
              sha256(fixture.index))
          .has_value());
  const auto contended = second.begin(
      workspace,
      held_token,
      fixture.index.size(),
      sha256(fixture.index));
  LMDJ_CHECK(!contended.has_value());
  LMDJ_CHECK(
      contended.error().details.at("storage_condition") == "project_busy");
  LMDJ_CHECK(first.abort(held_token).has_value());

  const auto bad_offset_token = uuid(212);
  LMDJ_CHECK(
      first
          .begin(
              workspace,
              bad_offset_token,
              fixture.index.size(),
              sha256(fixture.index))
          .has_value());
  LMDJ_CHECK(
      !first
           .append_index(
               bad_offset_token,
               1,
               std::span<const std::byte>{
                   reinterpret_cast<const std::byte*>(fixture.index.data()),
                   fixture.index.size()},
               true)
           .has_value());
  LMDJ_CHECK(first.abort(bad_offset_token).has_value());

  const auto bad_hash_token = uuid(213);
  LMDJ_CHECK(
      first
          .begin(
              workspace,
              bad_hash_token,
              fixture.index.size(),
              std::string(64, '0'))
          .has_value());
  LMDJ_CHECK(
      !first
           .append_index(
               bad_hash_token,
               0,
               std::span<const std::byte>{
                   reinterpret_cast<const std::byte*>(fixture.index.data()),
                   fixture.index.size()},
               true)
           .has_value());
  LMDJ_CHECK(first.abort(bad_hash_token).has_value());

  const auto orphan = workspace / ".lmdj-host/import-staging" / uuid(214);
  LMDJ_CHECK(first_platform->ensure_directory(orphan / "nested").has_value());
  LMDJ_CHECK(first.cleanup_incomplete(workspace).has_value());
  LMDJ_CHECK(!first_platform->directory_exists(orphan).value());

  append_fixture(first, workspace, uuid(215), fixture);
  LMDJ_CHECK(first.commit(uuid(215)).has_value());
  const auto changed_source = temp.path() / "changed.lmdj";
  std::filesystem::copy(
      source,
      changed_source,
      std::filesystem::copy_options::recursive);
  std::ofstream(changed_source / "local-note.bin", std::ios::binary) << "changed";
  const auto changed_fixture = build_fixture(changed_source);
  LMDJ_CHECK(changed_fixture.digest != fixture.digest);
  append_fixture(first, workspace, uuid(216), changed_fixture);
  const auto collision = first.commit(uuid(216));
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::duplicate_id);
}

void test_index_canonicality_payload_limits_and_entry_hashes() {
  TempDirectory temp;
  const auto workspace = temp.path() / "workspace";
  const auto source = temp.path() / "source.lmdj";
  create_project(source);
  const auto fixture = build_fixture(source);
  auto platform = lmdj::project_io::make_native_project_storage_platform(
      temp.path() / "leases");
  ProjectBundleTransfer transfer{platform};

  const auto noncanonical = nlohmann::json::parse(fixture.index).dump(2);
  const auto noncanonical_token = uuid(217);
  const auto noncanonical_result = stage_index(
      transfer, workspace, noncanonical_token, noncanonical);
  LMDJ_CHECK(!noncanonical_result.has_value());
  LMDJ_CHECK(
      noncanonical_result.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(transfer.abort(noncanonical_token).has_value());

  auto oversized_entry = nlohmann::json::parse(fixture.index);
  oversized_entry["entries"][0]["bytes"] = 64U * 1024U * 1024U + 1U;
  oversized_entry["uncompressed_bytes"] = 64U * 1024U * 1024U + 1U;
  const auto oversized_entry_index = canonical_index(oversized_entry);
  const auto oversized_entry_token = uuid(218);
  const auto oversized_entry_result = stage_index(
      transfer, workspace, oversized_entry_token, oversized_entry_index);
  LMDJ_CHECK(!oversized_entry_result.has_value());
  LMDJ_CHECK(
      oversized_entry_result.error().details.at("transfer_condition") ==
      "resource_limit");
  LMDJ_CHECK(transfer.abort(oversized_entry_token).has_value());

  auto oversized_payload = nlohmann::json::parse(fixture.index);
  oversized_payload["entries"] = nlohmann::json::array();
  std::uint64_t payload_offset = 0;
  for (std::uint32_t index = 0; index < 9; ++index) {
    oversized_payload["entries"].push_back(
        {
            {"bytes", 64U * 1024U * 1024U},
            {"offset", payload_offset},
            {"path", "entry-0" + std::to_string(index) + ".bin"},
            {"sha256", std::string(64, '0')},
        });
    payload_offset += 64U * 1024U * 1024U;
  }
  oversized_payload["uncompressed_bytes"] = payload_offset;
  const auto oversized_payload_index = canonical_index(oversized_payload);
  const auto oversized_payload_token = uuid(219);
  const auto oversized_payload_result = stage_index(
      transfer, workspace, oversized_payload_token, oversized_payload_index);
  LMDJ_CHECK(!oversized_payload_result.has_value());
  LMDJ_CHECK(
      oversized_payload_result.error().details.at("transfer_condition") ==
      "resource_limit");
  LMDJ_CHECK(transfer.abort(oversized_payload_token).has_value());

  const auto corrupt_entry_token = uuid(221);
  const auto staged = stage_index(
      transfer, workspace, corrupt_entry_token, fixture.index);
  LMDJ_CHECK(staged.has_value());
  LMDJ_CHECK(staged.value().has_value());
  auto corrupted_entry = fixture.entries.front();
  LMDJ_CHECK(!corrupted_entry.empty());
  corrupted_entry.front() ^= std::byte{1};
  const auto corrupt_entry_result = transfer.append_entry(
      corrupt_entry_token,
      0,
      0,
      corrupted_entry,
      true);
  LMDJ_CHECK(!corrupt_entry_result.has_value());
  LMDJ_CHECK(corrupt_entry_result.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(transfer.abort(corrupt_entry_token).has_value());
}

void test_publish_failure_preserves_visible_projects_and_cleans_staging() {
  TempDirectory temp;
  const auto workspace = temp.path() / "workspace";
  const auto source = temp.path() / "source.lmdj";
  create_project(source);
  const auto fixture = build_fixture(source);
  auto native = lmdj::project_io::make_native_project_storage_platform(
      temp.path() / "leases");
  auto faults = std::make_shared<FaultPlatform>(native);
  ProjectBundleTransfer transfer{faults};
  const auto before = transfer.list_local_projects(workspace);
  LMDJ_CHECK(before.has_value());
  const auto token = uuid(220);
  append_fixture(transfer, workspace, token, fixture);
  faults->fail_next_publish = true;
  const auto failed = transfer.commit(token);
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(transfer.list_local_projects(workspace).value() == before.value());
  LMDJ_CHECK(
      !faults
           ->directory_exists(
               workspace / "projects" /
               (std::string{kProjectId} + ".lmdj"))
           .value());
  LMDJ_CHECK(
      !faults
           ->directory_exists(
               workspace / ".lmdj-host/import-staging" / token)
           .value());
}

}  // namespace

int main() {
  try {
    test_streamed_import_is_atomic_discoverable_and_idempotent();
    test_validation_abort_cleanup_collision_and_contention();
    test_index_canonicality_payload_limits_and_entry_hashes();
    test_publish_failure_preserves_visible_projects_and_cleans_staging();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project bundle transfer tests: PASS\n";
  return 0;
}
