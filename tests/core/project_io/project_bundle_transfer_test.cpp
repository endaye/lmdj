#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
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
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "packages/project-io/src/publish_token.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;
using lmdj::project_io::ProjectBundleTransfer;
using lmdj::project_io::ProjectStoragePlatform;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::SequenceJournal;

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

  // Read the Contract level the Store actually persisted rather than naming
  // one here. A hardcoded level silently stops describing the Project when the
  // writer moves, which is how #784 shipped.
  const auto entry_text = [&](std::string_view relative) {
    const auto found = std::find_if(
        source_entries.begin(),
        source_entries.end(),
        [&](const auto& item) { return item.path == relative; });
    LMDJ_CHECK(found != source_entries.end());
    return std::string{
        reinterpret_cast<const char*>(found->data.data()),
        found->data.size()};
  };
  const auto manifest = nlohmann::json::parse(entry_text("manifest.json"));
  const auto head_checkpoint =
      manifest.at("head_checkpoint").get<std::string>();
  const auto head = nlohmann::json::parse(entry_text(head_checkpoint));
  const auto project_contract = head.at("contract").get<std::string>();

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
      {"contract_version", "2.0.0"},
      {"entries", std::move(encoded_entries)},
      {"project_contract", project_contract},
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
  bool staged_writes_exceed_quota = false;
  std::function<void(const std::filesystem::path&)> on_read;

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
    if (on_read) {
      on_read(path);
    }
    return inner_->read_complete(path);
  }
  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> value) override {
    if (staged_writes_exceed_quota &&
        path.generic_string().find("/import-staging/") != std::string::npos) {
      return lmdj::foundation::Result<void>::failure(
          Error{
              ErrorCode::io_error,
              "injected quota exhaustion",
              {{"storage_condition", "quota_exceeded"}},
          });
    }
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

void test_unreadable_local_copy_is_named_not_blamed_on_the_bundle() {
  TempDirectory temp;
  const auto workspace = temp.path() / "workspace";
  const auto source = temp.path() / "source.lmdj";
  create_project(source);
  const auto fixture = build_fixture(source);
  auto platform =
      lmdj::project_io::make_native_project_storage_platform(
          temp.path() / "leases");
  ProjectBundleTransfer transfer{platform};

  // A copy of this Project ID already exists locally, and it is damaged:
  // the Store refuses to load it for reasons that have nothing to do with
  // the staged bundle.
  const auto destination =
      workspace / "projects" / (std::string{kProjectId} + ".lmdj");
  LMDJ_CHECK(platform->ensure_directory(destination).has_value());
  LMDJ_CHECK(
      platform
          ->create_immutable(
              destination / "manifest.json",
              std::span<const std::byte>{})
          .has_value());

  append_fixture(transfer, workspace, uuid(220), fixture);
  const auto refused = transfer.commit(uuid(220));
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(refused.error().details.at("local_copy") == true);
  LMDJ_CHECK(
      !platform
           ->directory_exists(
               workspace / ".lmdj-host/import-staging" / uuid(220))
           .value());
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

constexpr std::string_view kSourceId = "00000000-0000-4000-8000-000000000301";
constexpr std::string_view kCopyId = "00000000-0000-4000-8000-000000000302";
constexpr std::string_view kSourcePatternId =
    "00000000-0000-4000-8000-000000000303";
constexpr std::string_view kPadAssetId =
    "00000000-0000-4000-8000-000000000304";
constexpr std::string_view kResampleAssetId =
    "00000000-0000-4000-8000-000000000305";
constexpr std::string_view kPerformanceId =
    "00000000-0000-4000-8000-000000000306";
constexpr std::string_view kSessionId =
    "00000000-0000-4000-8000-000000000307";

void write_text(const std::filesystem::path& path, std::string_view text) {
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  stream << text;
}

ArtifactRef artifact(std::string_view content) {
  const auto data = bytes(content);
  picosha2::hash256_one_by_one hasher;
  const auto* begin = reinterpret_cast<const unsigned char*>(data.data());
  hasher.process(begin, begin + data.size());
  hasher.finish();
  return ArtifactRef{
      picosha2::get_hash_hex_string(hasher), "audio/wav", data.size()};
}

constexpr std::string_view kPadAudio = "pad-audio-bytes";
constexpr std::string_view kResampleAudio = "resampled-audio-bytes";
constexpr std::string_view kRecordingAudio = "performance-recording-bytes";

std::filesystem::path project_path(
    const std::filesystem::path& workspace,
    std::string_view project_id) {
  return workspace / "projects" / (std::string{project_id} + ".lmdj");
}

std::filesystem::path staging_path(
    const std::filesystem::path& workspace,
    std::string_view project_id) {
  return workspace / ".lmdj-host/import-staging" /
         ("duplicate-" + std::string{project_id});
}

lmdj::domain::CommandMeta meta(std::uint32_t command, std::uint64_t revision) {
  return lmdj::domain::CommandMeta{
      lmdj::foundation::CommandId{uuid(command)}, revision};
}

// A source whose committed Truth holds a Pad Asset, a resampled Asset with
// lineage into a Performance recording, the recording itself and one
// transaction of history beyond its initial checkpoint.
void create_source(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& workspace) {
  const auto bundle = project_path(workspace, kSourceId);
  std::filesystem::create_directories(bundle / "assets");
  const auto pad = artifact(kPadAudio);
  const auto resampled = artifact(kResampleAudio);
  const auto recording = artifact(kRecordingAudio);
  write_text(bundle / "assets" / (pad.sha256 + ".wav"), kPadAudio);
  write_text(bundle / "assets" / (resampled.sha256 + ".wav"), kResampleAudio);
  write_text(bundle / "assets" / (recording.sha256 + ".wav"), kRecordingAudio);

  auto state = lmdj::domain::create_project(
      ProjectId{std::string{kSourceId}}, 126);
  LMDJ_CHECK(state.has_value());
  auto initial = state.value();
  const lmdj::domain::PerformanceId performance_id{
      std::string{kPerformanceId}};
  initial.performances.emplace(
      performance_id,
      lmdj::domain::Performance{
          performance_id, "Take", 126, 4, recording, {}});
  initial.assets.emplace(
      AssetId{std::string{kPadAssetId}},
      lmdj::domain::Asset{AssetId{std::string{kPadAssetId}}, pad, {}});
  initial.assets.emplace(
      AssetId{std::string{kResampleAssetId}},
      lmdj::domain::Asset{
          AssetId{std::string{kResampleAssetId}},
          resampled,
          lmdj::domain::AssetLineage{
              lmdj::domain::AssetArtifactLineageSource{recording.sha256, 5},
              lmdj::domain::ResampleLineageDerivation{{0, 8}, performance_id},
          }});
  initial.banks[0][0].asset_id = AssetId{std::string{kPadAssetId}};
  initial.banks[1][3].asset_id = AssetId{std::string{kResampleAssetId}};
  ProjectStore store{platform};
  const auto created = store.create(bundle, initial);
  LMDJ_CHECK(created.has_value());
  const lmdj::domain::CreatePattern pattern{
      meta(310, 0),
      lmdj::domain::Pattern{PatternId{std::string{kSourcePatternId}}, 1, {}},
  };
  LMDJ_CHECK(
      store.execute(bundle, lmdj::domain::Command{pattern}).has_value());
}

struct Fixture {
  TempDirectory temp;
  std::filesystem::path workspace = temp.path() / "workspace";
  std::filesystem::path leases = temp.path() / "leases";
  std::shared_ptr<ProjectStoragePlatform> platform =
      lmdj::project_io::make_native_project_storage_platform(leases);

  Fixture() { create_source(platform, workspace); }

  lmdj::domain::ProjectState load(std::string_view project_id) const {
    ProjectStore store{platform};
    auto loaded = store.load(project_path(workspace, project_id));
    LMDJ_CHECK(loaded.has_value());
    return loaded.value();
  }

  bool published(std::string_view project_id) const {
    return std::filesystem::exists(project_path(workspace, project_id));
  }

  bool staged(std::string_view project_id) const {
    return std::filesystem::exists(staging_path(workspace, project_id));
  }
};

lmdj::foundation::Result<lmdj::project_io::LocalProjectSummary> duplicate(
    ProjectBundleTransfer& transfer,
    const std::filesystem::path& workspace,
    std::string_view source = kSourceId,
    std::string_view copy = kCopyId) {
  return transfer.duplicate(
      workspace, ProjectId{std::string{source}}, ProjectId{std::string{copy}});
}

void test_copy_holds_the_same_truth_under_a_new_identity() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  const auto source = f.load(kSourceId);
  const auto copied = duplicate(transfer, f.workspace);
  LMDJ_CHECK(copied.has_value());
  LMDJ_CHECK(copied.value().project_id.value() == kCopyId);
  LMDJ_CHECK(copied.value().revision == 0);

  auto expected = source;
  expected.id = ProjectId{std::string{kCopyId}};
  expected.revision = 0;
  LMDJ_CHECK(f.load(kCopyId) == expected);
}

void test_copy_carries_every_referenced_artifact_byte_for_byte() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  LMDJ_CHECK(duplicate(transfer, f.workspace).has_value());
  for (const auto content : {kPadAudio, kResampleAudio, kRecordingAudio}) {
    const auto name = artifact(content).sha256 + ".wav";
    LMDJ_CHECK(
        read_text(project_path(f.workspace, kCopyId) / "assets" / name) ==
        content);
  }
}

void test_copy_starts_a_fresh_history() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  LMDJ_CHECK(duplicate(transfer, f.workspace).has_value());
  const auto copy = project_path(f.workspace, kCopyId);
  LMDJ_CHECK(std::filesystem::is_empty(copy / "history/transactions"));
  LMDJ_CHECK(
      std::filesystem::exists(copy / "history/checkpoints/0.json"));
  LMDJ_CHECK(
      !std::filesystem::exists(copy / "history/checkpoints/1.json"));
}

void test_library_lists_both_projects_and_the_copy_summary() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  const auto copied = duplicate(transfer, f.workspace);
  LMDJ_CHECK(copied.has_value());
  const auto listed = transfer.list_local_projects(f.workspace);
  LMDJ_CHECK(listed.has_value());
  LMDJ_CHECK(listed.value().size() == 2);
  LMDJ_CHECK(listed.value().at(0).project_id.value() == kSourceId);
  LMDJ_CHECK(listed.value().at(1) == copied.value());
}

void test_editing_either_project_never_changes_the_other() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  LMDJ_CHECK(duplicate(transfer, f.workspace).has_value());
  const auto source_before = f.load(kSourceId);
  const auto copy_before = f.load(kCopyId);
  ProjectStore store{f.platform};

  const lmdj::domain::AssignPad clear_copy{meta(320, 0), {0, 0}, std::nullopt};
  LMDJ_CHECK(store
                 .execute(
                     project_path(f.workspace, kCopyId),
                     lmdj::domain::Command{clear_copy})
                 .has_value());
  LMDJ_CHECK(f.load(kSourceId) == source_before);

  const lmdj::domain::AssignPad clear_source{
      meta(321, source_before.revision), {1, 3}, std::nullopt};
  LMDJ_CHECK(store
                 .execute(
                     project_path(f.workspace, kSourceId),
                     lmdj::domain::Command{clear_source})
                 .has_value());
  auto copy_after = f.load(kCopyId);
  LMDJ_CHECK(copy_after.banks[1][3].asset_id == copy_before.banks[1][3].asset_id);
  LMDJ_CHECK(!copy_after.banks[0][0].asset_id.has_value());
}

void test_copy_reopens_in_a_new_process_and_accepts_commands() {
  Fixture f;
  {
    ProjectBundleTransfer transfer{f.platform};
    LMDJ_CHECK(duplicate(transfer, f.workspace).has_value());
  }
  auto reopened_platform =
      lmdj::project_io::make_native_project_storage_platform(f.leases);
  ProjectStore reopened{reopened_platform};
  const auto copy = project_path(f.workspace, kCopyId);
  const auto loaded = reopened.load(copy);
  LMDJ_CHECK(loaded.has_value());
  const lmdj::domain::CreatePattern pattern{
      meta(330, 0),
      lmdj::domain::Pattern{PatternId{uuid(331)}, 2, {}},
  };
  const auto executed =
      reopened.execute(copy, lmdj::domain::Command{pattern});
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().state.revision == 1);
}

void test_source_owned_by_another_process_is_refused_as_busy() {
  Fixture f;
  auto other = lmdj::project_io::make_native_project_storage_platform(f.leases);
  auto held = other->acquire_writer(project_path(f.workspace, kSourceId));
  LMDJ_CHECK(held.has_value());
  ProjectBundleTransfer transfer{f.platform};
  const auto refused = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(
      refused.error().details.at("storage_condition") == "project_busy");
  LMDJ_CHECK(!f.published(kCopyId));
  LMDJ_CHECK(!f.staged(kCopyId));
}

void test_active_sequence_journal_is_refused_before_staging() {
  Fixture f;
  const auto source = f.load(kSourceId);
  const auto& pattern = source.patterns.begin()->second;
  SequenceJournal journal{f.platform};
  LMDJ_CHECK(journal
                 .begin(
                     project_path(f.workspace, kSourceId),
                     SequenceSessionId{std::string{kSessionId}},
                     pattern.id,
                     pattern.bars,
                     lmdj::project_io::sequence_pattern_fingerprint(pattern),
                     source.revision)
                 .has_value());
  ProjectBundleTransfer transfer{f.platform};
  const auto refused = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().details.at("reason") == "sequence_session_active");
  LMDJ_CHECK(!f.published(kCopyId));
  LMDJ_CHECK(!f.staged(kCopyId));
}

void test_active_performance_journal_is_refused_before_staging() {
  Fixture f;
  const auto source = f.load(kSourceId);
  const auto& performance = source.performances.begin()->second;
  SequenceJournal journal{f.platform};
  LMDJ_CHECK(journal
                 .begin_performance(
                     project_path(f.workspace, kSourceId),
                     SequenceSessionId{std::string{kSessionId}},
                     performance.id,
                     lmdj::project_io::performance_fingerprint(performance),
                     source.revision)
                 .has_value());
  ProjectBundleTransfer transfer{f.platform};
  const auto refused = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(
      refused.error().details.at("reason") == "performance_session_active");
  LMDJ_CHECK(!f.published(kCopyId));
  LMDJ_CHECK(!f.staged(kCopyId));
}

void test_existing_destination_is_refused_and_left_untouched() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  LMDJ_CHECK(duplicate(transfer, f.workspace).has_value());
  const auto manifest =
      read_text(project_path(f.workspace, kCopyId) / "manifest.json");
  const auto refused = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().code == ErrorCode::duplicate_id);
  LMDJ_CHECK(
      read_text(project_path(f.workspace, kCopyId) / "manifest.json") ==
      manifest);
}

void test_invalid_identities_are_refused() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  const auto same = duplicate(transfer, f.workspace, kSourceId, kSourceId);
  LMDJ_CHECK(!same.has_value());
  LMDJ_CHECK(same.error().code == ErrorCode::invalid_argument);
  const auto malformed = duplicate(transfer, f.workspace, kSourceId, "copy");
  LMDJ_CHECK(!malformed.has_value());
  LMDJ_CHECK(malformed.error().code == ErrorCode::invalid_argument);
  const auto relative = transfer.duplicate(
      "workspace",
      ProjectId{std::string{kSourceId}},
      ProjectId{std::string{kCopyId}});
  LMDJ_CHECK(!relative.has_value());
  LMDJ_CHECK(relative.error().code == ErrorCode::invalid_argument);
}

void test_missing_source_is_not_found() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  const auto missing = duplicate(transfer, f.workspace, uuid(340), kCopyId);
  LMDJ_CHECK(!missing.has_value());
  LMDJ_CHECK(missing.error().code == ErrorCode::not_found);
  LMDJ_CHECK(!f.published(kCopyId));
}

void test_corrupt_source_artifact_fails_without_publishing() {
  Fixture f;
  write_text(
      project_path(f.workspace, kSourceId) / "assets" /
          (artifact(kRecordingAudio).sha256 + ".wav"),
      "performance-recording-byteX");
  ProjectBundleTransfer transfer{f.platform};
  const auto failed = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(!f.published(kCopyId));
  LMDJ_CHECK(!f.staged(kCopyId));
}

void test_source_stays_owned_while_its_artifacts_are_read() {
  Fixture f;
  auto faults = std::make_shared<FaultPlatform>(f.platform);
  auto other = lmdj::project_io::make_native_project_storage_platform(f.leases);
  const auto source = project_path(f.workspace, kSourceId);
  int contended = 0;
  int busy = 0;
  faults->on_read = [&](const std::filesystem::path& path) {
    if (path.parent_path() != source / "assets") {
      return;
    }
    ++contended;
    const auto attempt = other->acquire_writer(source);
    if (!attempt.has_value() &&
        attempt.error().details.value("storage_condition", std::string{}) ==
            "project_busy") {
      ++busy;
    }
  };
  ProjectBundleTransfer transfer{faults};
  LMDJ_CHECK(duplicate(transfer, f.workspace).has_value());
  LMDJ_CHECK(contended == 3);
  LMDJ_CHECK(busy == contended);
}

void test_directory_publication_failure_leaves_no_copy() {
  Fixture f;
  auto faults = std::make_shared<FaultPlatform>(f.platform);
  faults->fail_next_publish = true;
  ProjectBundleTransfer transfer{faults};
  const auto failed = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(!f.published(kCopyId));
  LMDJ_CHECK(!f.staged(kCopyId));
}

void test_quota_exhaustion_keeps_its_storage_condition() {
  Fixture f;
  auto faults = std::make_shared<FaultPlatform>(f.platform);
  faults->staged_writes_exceed_quota = true;
  ProjectBundleTransfer transfer{faults};
  const auto failed = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(
      failed.error().details.at("storage_condition") == "quota_exceeded");
  LMDJ_CHECK(!f.published(kCopyId));
  LMDJ_CHECK(!f.staged(kCopyId));
}

struct RecordingToken {
  bool refuse_claim = false;
  bool force_failure = false;
  int claims = 0;
  int commits = 0;
  int aborts = 0;

  lmdj::project_io::detail::PublishToken token() {
    return {
        this,
        [](void* self) noexcept {
          auto& recorder = *static_cast<RecordingToken*>(self);
          ++recorder.claims;
          return !recorder.refuse_claim;
        },
        [](void* self) noexcept {
          ++static_cast<RecordingToken*>(self)->commits;
        },
        [](void* self) noexcept {
          ++static_cast<RecordingToken*>(self)->aborts;
        },
        [](void* self) noexcept {
          return static_cast<RecordingToken*>(self)->force_failure;
        },
    };
  }
};

void test_success_claims_and_commits_exactly_one_publication() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  RecordingToken recorder;
  const auto token = recorder.token();
  const lmdj::project_io::detail::PublishTokenScope scope{token};
  LMDJ_CHECK(duplicate(transfer, f.workspace).has_value());
  LMDJ_CHECK(recorder.claims == 1);
  LMDJ_CHECK(recorder.commits == 1);
  LMDJ_CHECK(recorder.aborts == 0);
}

void test_cancelled_publication_leaves_no_copy() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  RecordingToken recorder;
  recorder.refuse_claim = true;
  const auto token = recorder.token();
  const lmdj::project_io::detail::PublishTokenScope scope{token};
  const auto cancelled = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!cancelled.has_value());
  LMDJ_CHECK(cancelled.error().code == ErrorCode::internal_error);
  LMDJ_CHECK(recorder.commits == 0);
  LMDJ_CHECK(!f.published(kCopyId));
  LMDJ_CHECK(!f.staged(kCopyId));
}

void test_forced_publication_failure_aborts_and_leaves_no_copy() {
  Fixture f;
  ProjectBundleTransfer transfer{f.platform};
  RecordingToken recorder;
  recorder.force_failure = true;
  const auto token = recorder.token();
  const lmdj::project_io::detail::PublishTokenScope scope{token};
  const auto failed = duplicate(transfer, f.workspace);
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(recorder.aborts == 1);
  LMDJ_CHECK(!f.published(kCopyId));
  LMDJ_CHECK(!f.staged(kCopyId));
}

void test_interrupted_staging_is_recovered() {
  Fixture f;
  const auto residue = staging_path(f.workspace, kCopyId) / "project.lmdj";
  std::filesystem::create_directories(residue / "assets");
  write_text(residue / "assets/partial.wav", "partial");
  ProjectBundleTransfer transfer{f.platform};
  LMDJ_CHECK(duplicate(transfer, f.workspace).has_value());
  LMDJ_CHECK(!f.staged(kCopyId));
  LMDJ_CHECK(
      !std::filesystem::exists(
          project_path(f.workspace, kCopyId) / "assets/partial.wav"));

  std::filesystem::create_directories(residue);
  LMDJ_CHECK(transfer.cleanup_incomplete(f.workspace).has_value());
  LMDJ_CHECK(!f.staged(kCopyId));
}


}  // namespace

int main() {
  try {
    test_streamed_import_is_atomic_discoverable_and_idempotent();
    test_validation_abort_cleanup_collision_and_contention();
    test_unreadable_local_copy_is_named_not_blamed_on_the_bundle();
    test_index_canonicality_payload_limits_and_entry_hashes();
    test_publish_failure_preserves_visible_projects_and_cleans_staging();
    test_copy_holds_the_same_truth_under_a_new_identity();
    test_copy_carries_every_referenced_artifact_byte_for_byte();
    test_copy_starts_a_fresh_history();
    test_library_lists_both_projects_and_the_copy_summary();
    test_editing_either_project_never_changes_the_other();
    test_copy_reopens_in_a_new_process_and_accepts_commands();
    test_source_owned_by_another_process_is_refused_as_busy();
    test_active_sequence_journal_is_refused_before_staging();
    test_active_performance_journal_is_refused_before_staging();
    test_existing_destination_is_refused_and_left_untouched();
    test_invalid_identities_are_refused();
    test_missing_source_is_not_found();
    test_corrupt_source_artifact_fails_without_publishing();
    test_source_stays_owned_while_its_artifacts_are_read();
    test_directory_publication_failure_leaves_no_copy();
    test_quota_exhaustion_keeps_its_storage_condition();
    test_success_claims_and_commits_exactly_one_publication();
    test_cancelled_publication_leaves_no_copy();
    test_forced_publication_failure_aborts_and_leaves_no_copy();
    test_interrupted_staging_is_recovered();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project bundle transfer tests: PASS\n";
  return 0;
}
