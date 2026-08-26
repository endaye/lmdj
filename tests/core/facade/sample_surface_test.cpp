// Sample surface behaviour, split out of application_test.cpp so each
// binary carries its own timeout budget instead of sharing one.

// The scaffolding below is shared by the three facade test binaries and
// each exercises a subset of it; the unused-helper diagnostics are turned
// off for these targets in CMakeLists.txt for exactly that reason.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/cooker/sample_analysis.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/project_io/workspace_cache.hpp>
#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>

#include "packages/application-facade/src/testing_hooks.hpp"

#include "tests/core/support/test.hpp"

namespace {

using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::facade::ArtifactBytesImportRequest;
using lmdj::facade::InitialProjectRequest;
using lmdj::facade::RuntimeProjectWriterLease;
using lmdj::facade::RuntimeSnapshotRequest;
using lmdj::facade::SampleImportBeginRequest;
using lmdj::facade::SampleInspectRequest;
using lmdj::facade::SampleResetRequest;
using lmdj::facade::SampleUpdateRequest;
using lmdj::facade::SampleWaveformRequest;
using lmdj::audio::EnqueueResult;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RuntimePreparationLimits;
using lmdj::audio::TriggerEvent;
using lmdj::domain::CommandMeta;
using lmdj::domain::PadPlayback;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::TriggerMode;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kKickAssetId =
    "00000000-0000-4000-8000-000000000101";
constexpr std::string_view kSnareAssetId =
    "00000000-0000-4000-8000-000000000102";
constexpr std::string_view kPatternId =
    "00000000-0000-4000-8000-000000000010";
constexpr std::string_view kCapability = "proof.candidate.v2";
constexpr std::string_view kGoldenSha =
    "d276060107ab2479126c4f66919b799593a852fe624720f03e7be3b70bcfe867";
constexpr RuntimePreparationLimits kStage8WebLimits{
    1'048'576,
    240'000,
    67'108'864,
    134'217'728,
};
constexpr std::string_view kMono44100Sha =
    "ab8779402a0adb665d30c1a67a150d2543e2a4a2c2e694cf947ba6dc5c17a792";

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-facade-test-" + std::to_string(nonce));
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

// A storage platform that fails one named operation on demand. The facade
// takes its storage platform through ApplicationConfig, so every storage
// failure path below is reachable without a hook in production source: the
// injected platform *is* the seam. Each armed failure is one-shot, so a test
// can prove a specific refusal without disturbing the calls around it.

enum class SampleCleanupFailureTarget {
  payload,
  marker,
};

class SampleCleanupFailurePlatform final
    : public lmdj::project_io::ProjectStoragePlatform {
 public:
  explicit SampleCleanupFailurePlatform(
      std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner)
      : inner_(std::move(inner)) {}

  void arm(SampleCleanupFailureTarget target, std::string token) {
    target_ = target;
    token_ = std::move(token);
    armed_ = true;
    triggered_ = false;
    triggered_with_writer_lease_ = false;
    candidate_validation_seen_ = false;
    staging_validation_without_writer_ = false;
  }

  bool triggered() const noexcept { return triggered_; }
  bool triggered_with_writer_lease() const noexcept {
    return triggered_with_writer_lease_;
  }
  bool candidate_validation_was_lease_ordered() const noexcept {
    return candidate_validation_seen_ &&
           !staging_validation_without_writer_;
  }

  lmdj::foundation::Result<
      std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& path) override {
    auto acquired = inner_->acquire_writer(path);
    if (!acquired.has_value()) {
      return acquired;
    }
    if (path.parent_path().filename() != "sample-import-staging") {
      return acquired;
    }
    staging_writer_active_ = true;
    return lmdj::foundation::Result<
        std::unique_ptr<lmdj::project_io::ProjectWriterLease>>::success(
        std::make_unique<ObservedWriterLease>(
            std::move(acquired.value()), &staging_writer_active_));
  }

  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    return inner_->ensure_directory(path);
  }

  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    return inner_->exists(path);
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
      std::span<const std::byte> bytes) override {
    return inner_->create_immutable(path, bytes);
  }

  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner_->replace_complete(path, bytes);
  }

  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> bytes) override {
    return inner_->append_durable(path, valid_prefix_length, bytes);
  }

  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    const auto suffix = target_ == SampleCleanupFailureTarget::payload
                            ? ".wav"
                            : ".json";
    if (armed_ &&
        path.parent_path().filename() == "sample-import-staging" &&
        path.filename() == token_ + suffix) {
      return fail_once();
    }
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
    if (armed_ &&
        path.parent_path().filename() == "sample-import-staging" &&
        path.filename() == token_) {
      const auto child =
          path / (target_ == SampleCleanupFailureTarget::payload
                      ? "payload.wav"
                      : "state.json");
      const auto partially_removed = inner_->remove(child);
      if (!partially_removed.has_value()) {
        return partially_removed;
      }
      triggered_with_writer_lease_ = staging_writer_active_;
      return fail_once();
    }
    return inner_->remove_tree(path);
  }

  lmdj::foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path& source,
      const std::filesystem::path& destination) override {
    return inner_->publish_directory_if_absent(source, destination);
  }

  lmdj::foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const override {
    return inner_->directory_exists(path);
  }

  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& root) const override {
    if (armed_ && root.filename() == "sample-import-staging" &&
        !staging_writer_active_) {
      staging_validation_without_writer_ = true;
    }
    if (armed_ &&
        root.parent_path().filename() == "sample-import-staging") {
      candidate_validation_seen_ = true;
      if (!staging_writer_active_) {
        staging_validation_without_writer_ = true;
      }
    }
    return inner_->validate_managed_tree(root);
  }

 private:
  class ObservedWriterLease final
      : public lmdj::project_io::ProjectWriterLease {
   public:
    ObservedWriterLease(
        std::unique_ptr<lmdj::project_io::ProjectWriterLease> inner,
        bool* active)
        : inner_(std::move(inner)), active_(active) {}

    ~ObservedWriterLease() override {
      inner_.reset();
      *active_ = false;
    }

   private:
    std::unique_ptr<lmdj::project_io::ProjectWriterLease> inner_;
    bool* active_;
  };

  lmdj::foundation::Result<void> fail_once() {
    armed_ = false;
    triggered_ = true;
    return lmdj::foundation::Result<void>::failure(
        lmdj::foundation::Error{
            ErrorCode::io_error,
            "injected Sample staging cleanup failure",
        });
  }

  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner_;
  SampleCleanupFailureTarget target_ = SampleCleanupFailureTarget::payload;
  std::string token_;
  bool armed_ = false;
  bool triggered_ = false;
  bool staging_writer_active_ = false;
  bool triggered_with_writer_lease_ = false;
  mutable bool candidate_validation_seen_ = false;
  mutable bool staging_validation_without_writer_ = false;
};

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" +
         std::string(12 - tail.size(), '0') + tail;
}

std::shared_ptr<Registry> proof_registry() {
  auto registry = std::make_shared<Registry>();
  LMDJ_CHECK(
      registry->add(
          lmdj::providers::local_proof_success_registration()).has_value());
  LMDJ_CHECK(
      registry->add(
          lmdj::providers::local_proof_failure_registration()).has_value());
  return registry;
}

ApplicationConfig config(
    const std::filesystem::path& root,
    std::shared_ptr<Registry> registry = proof_registry()) {
  return ApplicationConfig{
      root,
      std::move(registry),
      ProviderPolicy{
          {"local"},
          {"public"},
          {"proof.execute"},
      },
      [] {
        return std::string("2026-07-31T00:00:00.000Z");
      },
  };
}

ApplicationConfig sample_config(
    const std::filesystem::path& root,
    RuntimePreparationLimits limits = kStage8WebLimits) {
  auto value = config(root);
  value.runtime_preparation_limits = limits;
  return value;
}

nlohmann::json slot(std::uint32_t bank, std::uint32_t pad) {
  return {{"bank", bank}, {"pad", pad}};
}

void check_exact_keys(
    const nlohmann::json& object,
    std::initializer_list<std::string_view> keys) {
  LMDJ_CHECK(object.is_object());
  LMDJ_CHECK(object.size() == keys.size());
  for (const auto key : keys) {
    LMDJ_CHECK(object.contains(std::string(key)));
  }
}

void check_success(
    const nlohmann::json& response,
    const nlohmann::json& revision) {
  check_exact_keys(response, {"ok", "result", "project_revision"});
  LMDJ_CHECK(response.at("ok") == true);
  LMDJ_CHECK(response.at("result").is_object());
  LMDJ_CHECK(response.at("project_revision") == revision);
}

void check_error(
    const nlohmann::json& response,
    std::string_view code) {
  check_exact_keys(response, {"ok", "error"});
  LMDJ_CHECK(response.at("ok") == false);
  check_exact_keys(
      response.at("error"), {"code", "message", "details"});
  LMDJ_CHECK(response.at("error").at("code") == code);
}

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("test file could not be opened");
  }
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

std::vector<std::byte> byte_vector(std::string_view value) {
  return {
      reinterpret_cast<const std::byte*>(value.data()),
      reinterpret_cast<const std::byte*>(value.data() + value.size()),
  };
}

std::vector<std::byte> file_bytes(const std::filesystem::path& path) {
  return byte_vector(read_bytes(path));
}

void write_bytes(
    const std::filesystem::path& path,
    std::string_view bytes);

std::string hash_text(
    const std::filesystem::path& scratch,
    std::string_view name,
    std::string_view value) {
  const auto path = scratch / std::string{name};
  write_bytes(path, value);
  const auto described =
      lmdj::foundation::describe_artifact(path, "application/octet-stream");
  LMDJ_CHECK(described.has_value());
  std::filesystem::remove(path);
  return described.value().sha256;
}

struct FacadeBundleFixture {
  std::string index;
  std::vector<std::vector<std::byte>> entries;
  std::string digest;
};

FacadeBundleFixture facade_bundle_fixture(
    const std::filesystem::path& project,
    const std::filesystem::path& scratch,
    std::string declared_project_id) {
  struct Entry {
    std::string path;
    std::vector<std::byte> bytes;
    std::string digest;
  };
  std::vector<Entry> entries;
  for (const auto& item :
       std::filesystem::recursive_directory_iterator(project)) {
    LMDJ_CHECK(!item.is_symlink());
    if (!item.is_regular_file()) {
      continue;
    }
    const auto relative =
        std::filesystem::relative(item.path(), project).generic_string();
    const auto content = read_bytes(item.path());
    const auto described = lmdj::foundation::describe_artifact(
        item.path(), "application/octet-stream");
    LMDJ_CHECK(described.has_value());
    entries.push_back(
        {relative, byte_vector(content), described.value().sha256});
  }
  std::sort(
      entries.begin(),
      entries.end(),
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
  std::vector<std::vector<std::byte>> payloads;
  std::uint64_t offset = 0;
  for (auto& entry : entries) {
    encoded_entries.push_back(
        {
            {"bytes", entry.bytes.size()},
            {"offset", offset},
            {"path", entry.path},
            {"sha256", entry.digest},
        });
    offset += entry.bytes.size();
    payloads.push_back(std::move(entry.bytes));
  }
  nlohmann::json index{
      {"compression", "none"},
      {"contract", "lmdj.project-bundle.v1"},
      {"contract_version", "1.0.0"},
      {"entries", std::move(encoded_entries)},
      {"project_contract", "lmdj.project.v1"},
      {"project_id", std::move(declared_project_id)},
      {"uncompressed_bytes", offset},
  };
  const auto digest_source = lmdj::foundation::canonical_json(index);
  const auto digest = hash_text(scratch, "bundle-digest.bin", digest_source);
  index["bundle_digest"] = digest;
  return {
      lmdj::foundation::canonical_json(index),
      std::move(payloads),
      digest,
  };
}

void stream_facade_bundle(
    Application& application,
    const std::string& token,
    const FacadeBundleFixture& fixture) {
  const auto index_bytes = byte_vector(fixture.index);
  const auto split = std::min<std::size_t>(11, index_bytes.size());
  auto indexed = application.append_project_bundle_index(
      token,
      0,
      std::span<const std::byte>{index_bytes.data(), split},
      split == index_bytes.size());
  LMDJ_CHECK(indexed.has_value());
  if (split != index_bytes.size()) {
    LMDJ_CHECK(!indexed.value().has_value());
    indexed = application.append_project_bundle_index(
        token,
        split,
        std::span<const std::byte>{
            index_bytes.data() + split, index_bytes.size() - split},
        true);
    LMDJ_CHECK(indexed.has_value());
  }
  LMDJ_CHECK(indexed.value().has_value());
  LMDJ_CHECK(indexed.value()->bundle_digest == fixture.digest);
  for (std::size_t entry_index = 0;
       entry_index < fixture.entries.size();
       ++entry_index) {
    const auto& entry = fixture.entries.at(entry_index);
    LMDJ_CHECK(
        application.append_project_bundle_entry(
            token,
            static_cast<std::uint32_t>(entry_index),
            0,
            entry,
            true)
            .has_value());
  }
}

void write_bytes(
    const std::filesystem::path& path,
    std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  if (!stream) {
    throw std::runtime_error("test file could not be written");
  }
}

void write_u16(
    std::vector<std::byte>& bytes,
    std::size_t offset,
    std::uint16_t value) {
  bytes.at(offset) = static_cast<std::byte>(value & 0xffU);
  bytes.at(offset + 1) = static_cast<std::byte>(value >> 8U);
}

void write_u32(
    std::vector<std::byte>& bytes,
    std::size_t offset,
    std::uint32_t value) {
  for (std::size_t index = 0; index < 4; ++index) {
    bytes.at(offset + index) =
        static_cast<std::byte>(value >> (index * 8U));
  }
}

void write_tag(
    std::vector<std::byte>& bytes,
    std::size_t offset,
    std::string_view tag) {
  LMDJ_CHECK(tag.size() == 4);
  for (std::size_t index = 0; index < tag.size(); ++index) {
    bytes.at(offset + index) =
        static_cast<std::byte>(static_cast<unsigned char>(tag.at(index)));
  }
}

std::vector<std::byte> mono_pcm16_wav(
    std::uint32_t frames,
    std::uint32_t sample_rate = 48'000) {
  const auto data_bytes = frames * 2U;
  std::vector<std::byte> bytes(44U + data_bytes);
  write_tag(bytes, 0, "RIFF");
  write_u32(bytes, 4, 36U + data_bytes);
  write_tag(bytes, 8, "WAVE");
  write_tag(bytes, 12, "fmt ");
  write_u32(bytes, 16, 16);
  write_u16(bytes, 20, 1);
  write_u16(bytes, 22, 1);
  write_u32(bytes, 24, sample_rate);
  write_u32(bytes, 28, sample_rate * 2U);
  write_u16(bytes, 32, 2);
  write_u16(bytes, 34, 16);
  write_tag(bytes, 36, "data");
  write_u32(bytes, 40, data_bytes);
  return bytes;
}

nlohmann::json create_request(const std::filesystem::path& project) {
  return {
      {"operation", "project.create"},
      {"project_path", project.generic_string()},
      {"project_id", kProjectId},
      {"bpm", 120},
  };
}


nlohmann::json import_request(
    const std::filesystem::path& project,
    std::uint32_t command_suffix,
    std::string_view asset_id,
    const std::filesystem::path& source,
    std::uint64_t revision) {
  return {
      {"operation", "asset.import"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(command_suffix)},
      {"expected_revision", revision},
      {"asset_id", asset_id},
      {"source_path", source.generic_string()},
      {"media_type", "audio/wav"},
  };
}

nlohmann::json assign_request(
    const std::filesystem::path& project,
    std::uint32_t command_suffix,
    std::uint32_t pad,
    std::string_view asset_id,
    std::uint64_t revision) {
  return {
      {"operation", "pad.assign"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(command_suffix)},
      {"expected_revision", revision},
      {"slot", slot(0, pad)},
      {"asset_id", asset_id},
  };
}

void create_single_asset_project(
    Application& application,
    const std::filesystem::path& project,
    std::span<const std::byte> bytes,
    std::uint32_t command_base,
    std::string asset_id,
    std::string pattern_id) {
  const auto created = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{std::string{kProjectId}},
          120,
          Pattern{
              PatternId{pattern_id},
              1,
              {{PadSlotId{0, 0}, 0, 240, 127}},
          },
      });
  LMDJ_CHECK(created.has_value());
  const auto imported = application.import_artifact_bytes(
      ArtifactBytesImportRequest{
          project,
          CommandMeta{CommandId{uuid(command_base)}, 0},
          AssetId{asset_id},
          "audio/wav",
          bytes,
      });
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(imported.value().state.revision == 1);
  check_success(
      application.command(
          assign_request(
              project,
              command_base + 1U,
              0,
              asset_id,
              1)),
      2);

  check_success(
      application.command(
          assign_request(
              project, command_base + 3U, 0, asset_id, 2)),
      3);
}

void check_peak_bucket(
    const lmdj::cooker::PeakBucket& bucket,
    std::uint64_t start,
    std::uint64_t end,
    std::uint16_t peak) {
  LMDJ_CHECK(bucket.start_frame == start);
  LMDJ_CHECK(bucket.end_frame == end);
  LMDJ_CHECK(bucket.peak_magnitude == peak);
}

void check_same_peak_buckets(
    const std::vector<lmdj::cooker::PeakBucket>& left,
    const std::vector<lmdj::cooker::PeakBucket>& right) {
  LMDJ_CHECK(left.size() == right.size());
  for (std::size_t index = 0; index < left.size(); ++index) {
    check_peak_bucket(
        left.at(index),
        right.at(index).start_frame,
        right.at(index).end_frame,
        right.at(index).peak_magnitude);
  }
}

class SampleProjectionHookGuard {
 public:
  explicit SampleProjectionHookGuard(
      lmdj::facade::testing::SampleProjectionHook* hook) {
    lmdj::facade::testing::set_sample_projection_hook(hook);
  }

  ~SampleProjectionHookGuard() {
    lmdj::facade::testing::set_sample_projection_hook(nullptr);
  }
};

struct SampleBusyHookContext {
  Application* competitor;
  std::filesystem::path project;
  std::optional<RuntimeProjectWriterLease> lease;
};

void acquire_sample_writer(void* opaque) noexcept {
  auto& context = *static_cast<SampleBusyHookContext*>(opaque);
  auto acquired = context.competitor->acquire_project_writer(context.project);
  if (acquired.has_value()) {
    context.lease.emplace(std::move(acquired.value()));
  }
}

template <typename Operation>
void check_sample_artifact_busy_error(
    Application& competitor,
    const std::filesystem::path& project,
    Operation operation) {
  SampleBusyHookContext context{&competitor, project, std::nullopt};
  lmdj::facade::testing::SampleProjectionHook hook{
      &context,
      acquire_sample_writer,
  };
  SampleProjectionHookGuard guard(&hook);
  const auto result = operation();
  LMDJ_CHECK(context.lease.has_value());
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::io_error);
  LMDJ_CHECK((
      result.error().details ==
      nlohmann::json{{"storage_condition", "project_busy"}}));
  LMDJ_CHECK(
      result.error().message.find(project.generic_string()) ==
      std::string::npos);
  context.lease.reset();
}




struct SampleCleanupFailureObservation {
  bool cleanup_failed;
  bool genuine_partial_residue;
  bool repeated_failure_fail_closed;
  bool repeated_residue_retryable;
  bool fresh_scavenger_recovered;
  bool token_reusable_after_recovery;
};

SampleCleanupFailureObservation observe_sample_cleanup_failure(
    SampleCleanupFailureTarget target,
    std::uint32_t suffix) {
  TempDirectory temp;
  const auto project = temp.path() / "sample-cleanup-failure.lmdj";
  const auto token = uuid(suffix);
  const auto source = file_bytes("tests/fixtures/audio/mono-44100.wav");
  const auto staging_root =
      temp.path() / ".lmdj-host/sample-import-staging";
  const auto staging_directory = staging_root / token;
  const auto marker = staging_directory / "state.json";
  const auto payload = staging_directory / "payload.wav";
  const auto legacy_marker = staging_root / (token + ".json");
  const auto legacy_payload = staging_root / (token + ".wav");
  auto native_platform =
      lmdj::project_io::make_native_project_storage_platform(
          temp.path() / "leases");
  auto platform =
      std::make_shared<SampleCleanupFailurePlatform>(native_platform);
  auto configuration = sample_config(temp.path());
  configuration.storage_platform = platform;
  auto recovery_configuration = sample_config(temp.path());
  recovery_configuration.storage_platform = native_platform;
  const SampleImportBeginRequest begin{
      token,
      project,
      {CommandId{uuid(suffix + 1U)}, 0},
      {0, 0},
      AssetId{uuid(suffix + 2U)},
      source.size(),
  };

  bool cleanup_failed = false;
  {
    Application application(configuration);
    check_success(application.command(create_request(project)), 0);
    LMDJ_CHECK(application.begin_sample_import(begin).has_value());
    LMDJ_CHECK(
        application.append_sample_import(
            token,
            0,
            std::span<const std::byte>{source}.first(8),
            false)
            .has_value());
    platform->arm(target, token);
    const auto aborted = application.abort_sample_import(token);
    cleanup_failed = !aborted.has_value() &&
                     aborted.error().code == ErrorCode::io_error &&
                     platform->triggered();
    LMDJ_CHECK(
        !application
             .append_sample_import(
                 token,
                 8,
                 std::span<const std::byte>{source}.subspan(8),
                 true)
             .has_value());
  }

  const auto marker_remained = std::filesystem::is_regular_file(marker);
  const auto payload_remained = std::filesystem::is_regular_file(payload);
  const auto genuine_partial_residue =
      target == SampleCleanupFailureTarget::payload
          ? marker_remained && !payload_remained
          : !marker_remained && payload_remained;

  platform->arm(target, token);
  bool repeated_failure_fail_closed = false;
  try {
    Application repeated_cleanup(configuration);
  } catch (const std::runtime_error&) {
    repeated_failure_fail_closed =
        platform->triggered() &&
        platform->triggered_with_writer_lease() &&
        platform->candidate_validation_was_lease_ordered();
  }
  const auto repeated_residue_retryable =
      std::filesystem::is_directory(staging_directory) &&
      (std::filesystem::is_regular_file(marker) ||
       std::filesystem::is_regular_file(payload));

  bool token_reusable_after_recovery = false;
  {
    Application recovered(recovery_configuration);
    const auto reused = recovered.begin_sample_import(begin);
    token_reusable_after_recovery = reused.has_value();
    if (reused.has_value()) {
      LMDJ_CHECK(recovered.abort_sample_import(token).has_value());
    }
  }
  const auto fresh_scavenger_recovered =
      !std::filesystem::exists(staging_directory) &&
      !std::filesystem::exists(legacy_marker) &&
      !std::filesystem::exists(legacy_payload);
  return {
      cleanup_failed,
      genuine_partial_residue,
      repeated_failure_fail_closed,
      repeated_residue_retryable,
      fresh_scavenger_recovered,
      token_reusable_after_recovery,
  };
}






struct SampleMutationHookContext {
  Application* application;
  std::filesystem::path project;
  const std::vector<std::byte>* replacement;
  bool completed = false;
};

void replace_sample_after_projection_load(void* opaque) noexcept {
  auto& context = *static_cast<SampleMutationHookContext*>(opaque);
  const auto imported = context.application->import_artifact_bytes(
      {context.project,
       {CommandId{uuid(650)}, 3},
       AssetId{uuid(651)},
       "audio/wav",
       *context.replacement});
  if (!imported.has_value()) {
    return;
  }
  const auto assigned = context.application->command(
      assign_request(context.project, 652, 0, uuid(651), 4));
  context.completed =
      assigned.is_object() && assigned.value("ok", false) &&
      assigned.value("project_revision", 0U) == 5;
}









// Every rejection `validate_initial_pattern` can produce, asserted by the
// contract it publishes rather than by the lines it executes: each case names
// the exact ErrorCode and public message a Host will see, and each proves the
// refusal happened before any Project file was written.

// Trigger mode must survive a full write-then-read round trip through the JSON
// surface. The four modes are a public contract: a Host writes one name and
// must read the identical name back, so a silent fallback in either the parser
// or the serializer is a contract break, not a cosmetic defect.

// Every public Application entry wraps its implementation in a catch-all whose
// job is to convert an unexpected exception into the documented failure
// envelope instead of letting it cross the Host boundary. That contract has
// never been exercised: an escaping exception would be undefined behaviour for
// the C ABI and a crash for a Host, so each entry is armed with one throw and
// required to answer with internal_error rather than propagate.

// Two failure classes the Sample import path publishes but never proved: a
// resource limit reached by ordinary use, and storage refusals at each seam.
// Both are contract surfaces - a Host branches on the code and shows the
// message - so each case asserts the exact code, message and details rather
// than that the call merely failed.

// Startup refuses to continue when it cannot account for leftover Sample
// staging. That refusal is a safety property - a Host must not run against a
// workspace whose staging state is unknown - and it is expressed as a thrown
// construction failure, so the only way to observe it is to fail the storage
// calls it makes.

void test_typed_sample_surface_is_atomic_bounded_and_cache_backed() {
  TempDirectory temp;
  const auto project = temp.path() / "typed-sample.lmdj";
  const auto source = file_bytes("tests/fixtures/audio/mono-44100.wav");
  const PatternId pattern_id{uuid(580)};
  Application application(sample_config(temp.path()));
  const auto created = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{uuid(581)},
          120,
          Pattern{
              pattern_id,
              1,
              {{PadSlotId{0, 0}, 0, 240, 127}},
          },
      });
  LMDJ_CHECK(created.has_value());
  const auto manifest_before = read_bytes(project / "manifest.json");

  const auto empty =
      application.inspect_sample(SampleInspectRequest{project, {0, 0}});
  LMDJ_CHECK(empty.has_value());
  LMDJ_CHECK(empty.value().project_revision == 0);
  LMDJ_CHECK((empty.value().slot == PadSlotId{0, 0}));
  LMDJ_CHECK(!empty.value().asset_id.has_value());
  LMDJ_CHECK(empty.value().playback == PadPlayback{});
  LMDJ_CHECK(!empty.value().metadata.has_value());
  LMDJ_CHECK(!empty.value().waveform_cache_identity.has_value());
  LMDJ_CHECK(read_bytes(project / "manifest.json") == manifest_before);

  const auto unavailable_waveform = application.query_sample_waveform(
      SampleWaveformRequest{project, {0, 0}, {0, 1, 1}});
  LMDJ_CHECK(!unavailable_waveform.has_value());
  LMDJ_CHECK(
      unavailable_waveform.error().code == ErrorCode::missing_asset);
  LMDJ_CHECK(read_bytes(project / "manifest.json") == manifest_before);

  const auto malformed_token = uuid(582);
  const auto begun = application.begin_sample_import(
      SampleImportBeginRequest{
          malformed_token,
          project,
          CommandMeta{CommandId{uuid(583)}, 0},
          PadSlotId{0, 0},
          AssetId{uuid(584)},
          source.size(),
      });
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().token == malformed_token);
  LMDJ_CHECK(begun.value().expected_bytes == source.size());
  const auto split = source.size() / 2U;
  LMDJ_CHECK(
      application.append_sample_import(
          malformed_token,
          0,
          std::span<const std::byte>{source.data(), split},
          false)
          .has_value());
  const auto wrong_offset = application.append_sample_import(
      malformed_token,
      split + 1U,
      std::span<const std::byte>{source.data() + split,
                                 source.size() - split},
      true);
  LMDJ_CHECK(!wrong_offset.has_value());
  LMDJ_CHECK(wrong_offset.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      !std::filesystem::exists(
          temp.path() / ".lmdj-host/sample-import-staging" /
          malformed_token));
  LMDJ_CHECK(
      !application
           .append_sample_import(
               malformed_token,
               split,
               std::span<const std::byte>{source.data() + split,
                                          source.size() - split},
               true)
           .has_value());
  LMDJ_CHECK(
      !application
           .begin_sample_import(
               {malformed_token,
                project,
                {CommandId{uuid(583)}, 0},
                {0, 0},
                AssetId{uuid(584)},
                source.size()})
           .has_value());

  const auto short_final_token = uuid(570);
  LMDJ_CHECK(
      application.begin_sample_import(
          {short_final_token,
           project,
           {CommandId{uuid(571)}, 0},
           {0, 0},
           AssetId{uuid(572)},
           source.size()})
          .has_value());
  const auto short_final = application.append_sample_import(
      short_final_token,
      0,
      std::span<const std::byte>{source.data(), split},
      true);
  LMDJ_CHECK(!short_final.has_value());
  LMDJ_CHECK(short_final.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      !std::filesystem::exists(
          temp.path() / ".lmdj-host/sample-import-staging" /
          short_final_token));

  const auto token = uuid(589);
  LMDJ_CHECK(
      application.begin_sample_import(
          {token,
           project,
           {CommandId{uuid(583)}, 0},
           {0, 0},
           AssetId{uuid(584)},
           source.size()})
          .has_value());
  LMDJ_CHECK(
      application.append_sample_import(token, 0, source, true).has_value());
  const auto committed = application.commit_sample_import(token);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().committed_revision == 1);
  LMDJ_CHECK(committed.value().runtime_prepare_required);

  const auto inspected =
      application.inspect_sample(SampleInspectRequest{project, {0, 0}});
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().project_revision == 1);
  LMDJ_CHECK(inspected.value().asset_id == AssetId{uuid(584)});
  LMDJ_CHECK(inspected.value().playback == PadPlayback{});
  LMDJ_CHECK(inspected.value().metadata.has_value());
  LMDJ_CHECK(inspected.value().metadata->sample_rate == 44'100);
  LMDJ_CHECK(inspected.value().metadata->channels == 1);
  LMDJ_CHECK(inspected.value().metadata->source_frames == 8);
  const auto cache_identity =
      std::string(kMono44100Sha) + "/1/max-abs-mirror/1";
  LMDJ_CHECK(
      inspected.value().waveform_cache_identity == cache_identity);

  const auto waveform_cache_identity =
      std::string(kMono44100Sha) + "/1/max-abs-mirror/2";
  const auto cache_path = temp.path() / ".lmdj-host/workspace-cache" /
                          waveform_cache_identity;
  LMDJ_CHECK(!std::filesystem::exists(cache_path));
  const auto first_waveform = application.query_sample_waveform(
      SampleWaveformRequest{project, {0, 0}, {0, 8, 4}});
  LMDJ_CHECK(first_waveform.has_value());
  LMDJ_CHECK(first_waveform.value().algorithm_version == 1);
  LMDJ_CHECK(first_waveform.value().buckets.size() == 4);
  check_peak_bucket(first_waveform.value().buckets.at(0), 0, 2, 32'768);
  check_peak_bucket(first_waveform.value().buckets.at(1), 2, 4, 8'192);
  check_peak_bucket(first_waveform.value().buckets.at(2), 4, 6, 4'096);
  check_peak_bucket(first_waveform.value().buckets.at(3), 6, 8, 0);
  LMDJ_CHECK(std::filesystem::is_regular_file(cache_path));
  const auto cached_bytes = read_bytes(cache_path);
  LMDJ_CHECK(cached_bytes.find(project.generic_string()) == std::string::npos);
  LMDJ_CHECK(cached_bytes.find(token) == std::string::npos);
  LMDJ_CHECK(cached_bytes.find(uuid(584)) == std::string::npos);
  const auto second_waveform = application.query_sample_waveform(
      SampleWaveformRequest{project, {0, 0}, {0, 8, 4}});
  LMDJ_CHECK(second_waveform.has_value());
  check_same_peak_buckets(
      second_waveform.value().buckets, first_waveform.value().buckets);
  LMDJ_CHECK(read_bytes(cache_path) == cached_bytes);

  write_bytes(cache_path, "corrupt-cache-record");
  const auto rebuilt = application.query_sample_waveform(
      SampleWaveformRequest{project, {0, 0}, {0, 8, 4}});
  LMDJ_CHECK(rebuilt.has_value());
  check_same_peak_buckets(
      rebuilt.value().buckets, first_waveform.value().buckets);
  LMDJ_CHECK(read_bytes(cache_path) != "corrupt-cache-record");

  lmdj::project_io::WorkspaceCacheStore cache(
      temp.path() / ".lmdj-host/workspace-cache");
  const std::string mismatched_payload = "{}";
  LMDJ_CHECK(
      cache.write(
               waveform_cache_identity,
               std::as_bytes(std::span<const char>{
                   mismatched_payload.data(), mismatched_payload.size()}))
          .has_value());
  const auto mismatched_record = read_bytes(cache_path);
  const auto mismatch_rebuilt = application.query_sample_waveform(
      SampleWaveformRequest{project, {0, 0}, {0, 8, 4}});
  LMDJ_CHECK(mismatch_rebuilt.has_value());
  check_same_peak_buckets(
      mismatch_rebuilt.value().buckets, first_waveform.value().buckets);
  LMDJ_CHECK(read_bytes(cache_path) != mismatched_record);

  const auto manifest_before_cache_failure =
      read_bytes(project / "manifest.json");
  std::filesystem::remove_all(
      temp.path() / ".lmdj-host/workspace-cache");
  write_bytes(
      temp.path() / ".lmdj-host/workspace-cache",
      "cache-root-is-unavailable");
  const auto degraded = application.query_sample_waveform(
      SampleWaveformRequest{project, {0, 0}, {0, 8, 4}});
  LMDJ_CHECK(degraded.has_value());
  check_same_peak_buckets(
      degraded.value().buckets, first_waveform.value().buckets);
  LMDJ_CHECK(
      read_bytes(project / "manifest.json") ==
      manifest_before_cache_failure);

  const PadPlayback playback{
      1,
      7,
      TriggerMode::loop_gate,
      -1'200,
      false,
  };
  const SampleUpdateRequest update{
      project,
      CommandMeta{CommandId{uuid(585)}, 1},
      PadSlotId{0, 0},
      playback,
  };
  const auto updated = application.update_sample_pad(update);
  LMDJ_CHECK(updated.has_value());
  LMDJ_CHECK(updated.value().committed_revision == 2);
  LMDJ_CHECK(updated.value().runtime_prepare_required);
  const auto replayed = application.update_sample_pad(update);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().committed_revision == 2);

  const auto conflict = application.update_sample_pad(
      SampleUpdateRequest{
          project,
          CommandMeta{CommandId{uuid(586)}, 1},
          PadSlotId{0, 0},
          playback,
      });
  LMDJ_CHECK(!conflict.has_value());
  LMDJ_CHECK(conflict.error().code == ErrorCode::revision_conflict);
  const auto invalid_selection = application.update_sample_pad(
      SampleUpdateRequest{
          project,
          CommandMeta{CommandId{uuid(587)}, 2},
          PadSlotId{0, 0},
          PadPlayback{0, 9, TriggerMode::one_shot, 0, false},
      });
  LMDJ_CHECK(!invalid_selection.has_value());
  LMDJ_CHECK(invalid_selection.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      application.inspect_sample({project, {0, 0}})
          .value()
          .project_revision == 2);

  const auto reset = application.reset_sample_pad(
      SampleResetRequest{
          project,
          CommandMeta{CommandId{uuid(588)}, 2},
          PadSlotId{0, 0},
      });
  LMDJ_CHECK(reset.has_value());
  LMDJ_CHECK(reset.value().committed_revision == 3);
  LMDJ_CHECK(reset.value().runtime_prepare_required);
  LMDJ_CHECK(
      application.inspect_sample({project, {0, 0}}).value().playback ==
      PadPlayback{});

  const auto failed_prepare = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{
          project,
          pattern_id,
          RuntimePreparationLimits{1'048'576, 240'000, 1, 1},
      });
  LMDJ_CHECK(!failed_prepare.has_value());
  LMDJ_CHECK(failed_prepare.error().code == ErrorCode::cook_failed);
  LMDJ_CHECK(
      application.inspect_sample({project, {0, 0}})
          .value()
          .project_revision == 3);

  std::filesystem::remove(
      project / "assets" / (std::string(kMono44100Sha) + ".wav"));
  const auto missing =
      application.inspect_sample(SampleInspectRequest{project, {0, 0}});
  LMDJ_CHECK(!missing.has_value());
  LMDJ_CHECK(missing.error().code == ErrorCode::missing_asset);
}

void test_typed_sample_surface_rejects_invalid_boundary_values() {
  TempDirectory temp;
  Application application(sample_config(temp.path()));
  const auto invalid = [](const auto& result) {
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
  };

  invalid(application.inspect_sample(
      SampleInspectRequest{"relative-project.lmdj", {0, 0}}));
  invalid(application.query_sample_waveform(
      SampleWaveformRequest{
          temp.path() / "missing-project.lmdj",
          {0, 0},
          {0, 1, 0},
      }));
  invalid(application.append_sample_import(
      "not-a-uuid", 0, std::span<const std::byte>{}, false));
  invalid(application.commit_sample_import("not-a-uuid"));
  invalid(application.abort_sample_import("not-a-uuid"));
  invalid(application.update_sample_pad(
      SampleUpdateRequest{
          "relative-project.lmdj",
          CommandMeta{CommandId{uuid(589)}, 0},
          {0, 0},
          {},
      }));
  invalid(application.reset_sample_pad(
      SampleResetRequest{
          "relative-project.lmdj",
          CommandMeta{CommandId{uuid(590)}, 0},
          {0, 0},
      }));
}

void test_sample_import_abort_scavenge_replace_and_manifest_admission() {
  TempDirectory temp;
  const auto project = temp.path() / "sample-lifecycle.lmdj";
  const auto source = file_bytes("tests/fixtures/audio/mono-44100.wav");
  const auto oversized = file_bytes(
      "tests/fixtures/audio/mono-44100-over-web-frame-limit.wav");
  const auto staging_root =
      temp.path() / ".lmdj-host/sample-import-staging";
  const auto staging_directory = [&](std::string_view token) {
    return staging_root / std::string{token};
  };
  const auto marker_path = [&](std::string_view token) {
    return staging_directory(token) / "state.json";
  };
  const auto payload_path = [&](std::string_view token) {
    return staging_directory(token) / "payload.wav";
  };
  const auto write_marker = [&](std::string_view token,
                                std::uint64_t created_unix_seconds) {
    std::filesystem::create_directories(staging_directory(token));
    write_bytes(
        marker_path(token),
        nlohmann::json{
            {"contract", "lmdj.sample-import-staging.v1"},
            {"created_unix_seconds", created_unix_seconds},
            {"state", "incomplete"},
            {"token", token},
        }
            .dump());
  };
  check_success(
      Application(sample_config(temp.path())).command(create_request(project)),
      0);

  const auto aborted_token = uuid(590);
  {
    Application application(sample_config(temp.path()));
    LMDJ_CHECK(
        application.begin_sample_import(
            {aborted_token,
             project,
             {CommandId{uuid(591)}, 0},
             {0, 0},
             AssetId{uuid(592)},
             source.size()})
            .has_value());
    LMDJ_CHECK(
        application.append_sample_import(
            aborted_token,
            0,
            std::span<const std::byte>{source}.first(source.size() / 2U),
            false)
            .has_value());
    LMDJ_CHECK(std::filesystem::is_regular_file(
        payload_path(aborted_token)));
    LMDJ_CHECK(application.abort_sample_import(aborted_token).has_value());
    LMDJ_CHECK(!std::filesystem::exists(staging_directory(aborted_token)));
    LMDJ_CHECK(
        !application.begin_sample_import(
             {aborted_token,
              project,
              {CommandId{uuid(591)}, 0},
              {0, 0},
              AssetId{uuid(592)},
              source.size()})
             .has_value());
  }

  const auto abandoned_token = uuid(593);
  {
    Application abandoned(sample_config(temp.path()));
    LMDJ_CHECK(
        abandoned.begin_sample_import(
            {abandoned_token,
             project,
             {CommandId{uuid(594)}, 0},
             {0, 0},
             AssetId{uuid(595)},
             source.size()})
            .has_value());
    LMDJ_CHECK(
        abandoned.append_sample_import(
            abandoned_token,
            0,
            std::span<const std::byte>{source}.first(8),
            false)
            .has_value());
  }
  LMDJ_CHECK(std::filesystem::is_regular_file(
      payload_path(abandoned_token)));
  Application fresh_scavenger(sample_config(temp.path()));
  LMDJ_CHECK(std::filesystem::is_regular_file(
      payload_path(abandoned_token)));
  write_marker(abandoned_token, 0);
  Application application(sample_config(temp.path()));
  LMDJ_CHECK(!std::filesystem::exists(staging_directory(abandoned_token)));

  const auto count_candidate = uuid(609);
  write_marker(count_candidate, 0);
  write_bytes(payload_path(count_candidate), "orphan");
  for (std::size_t index = 0; index < 64; ++index) {
    auto name = std::string{"!"} + std::to_string(index);
    name.insert(1, 3 - std::min<std::size_t>(3, name.size() - 1), '0');
    std::filesystem::create_directories(staging_root / name);
  }
  Application count_scavenger(sample_config(temp.path()));
  LMDJ_CHECK(!std::filesystem::exists(staging_directory(count_candidate)));

  const auto corrupt_marker_token = uuid(697);
  std::filesystem::create_directories(
      staging_directory(corrupt_marker_token));
  write_bytes(marker_path(corrupt_marker_token), "{");
  write_bytes(payload_path(corrupt_marker_token), "orphan");
  const auto incomplete_marker_token = uuid(698);
  std::filesystem::create_directories(
      staging_directory(incomplete_marker_token));
  write_bytes(
      marker_path(incomplete_marker_token),
      nlohmann::json{
          {"contract", "lmdj.sample-import-staging.v1"},
          {"token", incomplete_marker_token},
      }
          .dump());
  write_bytes(payload_path(incomplete_marker_token), "orphan");
  const auto malformed_payload_token = uuid(699);
  const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                       std::chrono::system_clock::now().time_since_epoch())
                       .count();
  LMDJ_CHECK(now >= 0);
  write_marker(
      malformed_payload_token, static_cast<std::uint64_t>(now));
  std::filesystem::create_directories(
      payload_path(malformed_payload_token));
  Application malformed_scavenger(sample_config(temp.path()));
  LMDJ_CHECK(
      !std::filesystem::exists(staging_directory(corrupt_marker_token)));
  LMDJ_CHECK(
      !std::filesystem::exists(staging_directory(incomplete_marker_token)));
  LMDJ_CHECK(
      !std::filesystem::exists(staging_directory(malformed_payload_token)));

  const auto incomplete_token = uuid(606);
  LMDJ_CHECK(
      application.begin_sample_import(
          {incomplete_token,
           project,
           {CommandId{uuid(607)}, 0},
           {0, 0},
           AssetId{uuid(608)},
           source.size()})
          .has_value());
  LMDJ_CHECK(
      application.append_sample_import(
          incomplete_token,
          0,
          std::span<const std::byte>{source}.first(8),
          false)
          .has_value());
  const auto incomplete =
      application.commit_sample_import(incomplete_token);
  LMDJ_CHECK(!incomplete.has_value());
  LMDJ_CHECK(incomplete.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!std::filesystem::exists(staging_directory(incomplete_token)));
  LMDJ_CHECK(
      application.inspect_sample({project, {0, 0}})
          .value()
          .project_revision == 0);

  const auto import = [&](std::string token,
                          std::string command,
                          std::string asset,
                          std::uint64_t revision,
                          std::span<const std::byte> bytes) {
    LMDJ_CHECK(
        application.begin_sample_import(
            {token,
             project,
             {CommandId{command}, revision},
             {0, 0},
             AssetId{asset},
             bytes.size()})
            .has_value());
    LMDJ_CHECK(
        application.append_sample_import(token, 0, bytes, true).has_value());
    return application.commit_sample_import(token);
  };

  const auto first =
      import(uuid(596), uuid(597), uuid(598), 0, source);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(first.value().committed_revision == 1);
  const auto updated = application.update_sample_pad(
      {project,
       {CommandId{uuid(599)}, 1},
       {0, 0},
       PadPlayback{1, 7, TriggerMode::gate, -600, true}});
  LMDJ_CHECK(updated.has_value());
  const auto replaced =
      import(uuid(600), uuid(601), uuid(602), 2, source);
  LMDJ_CHECK(replaced.has_value());
  LMDJ_CHECK(replaced.value().committed_revision == 3);
  const auto replacement = application.inspect_sample({project, {0, 0}});
  LMDJ_CHECK(replacement.has_value());
  LMDJ_CHECK(replacement.value().asset_id == AssetId{uuid(602)});
  LMDJ_CHECK(replacement.value().playback == PadPlayback{});

  const auto revision_before_rejection = replacement.value().project_revision;
  const auto over_limit =
      import(uuid(603), uuid(604), uuid(605), 3, oversized);
  LMDJ_CHECK(!over_limit.has_value());
  LMDJ_CHECK(over_limit.error().code == ErrorCode::unsupported_audio);
  LMDJ_CHECK((
      over_limit.error().details ==
      nlohmann::json{
          {"resource", "decoded_frames_per_pad"},
          {"observed", 240'001},
          {"limit", 240'000},
      }));
  LMDJ_CHECK(
      application.inspect_sample({project, {0, 0}})
          .value()
          .project_revision == revision_before_rejection);
  LMDJ_CHECK(!std::filesystem::exists(staging_directory(uuid(603))));
}

void test_sample_cleanup_half_failures_leave_one_retryable_unit() {
  const auto payload = observe_sample_cleanup_failure(
      SampleCleanupFailureTarget::payload, 680);
  const auto marker = observe_sample_cleanup_failure(
      SampleCleanupFailureTarget::marker, 690);
  const auto valid = [](const SampleCleanupFailureObservation& observed) {
    return observed.cleanup_failed &&
           observed.genuine_partial_residue &&
           observed.repeated_failure_fail_closed &&
           observed.repeated_residue_retryable &&
           observed.fresh_scavenger_recovered &&
           observed.token_reusable_after_recovery;
  };
  if (!valid(payload) || !valid(marker)) {
    throw std::runtime_error(
        "Sample cleanup retryability failed: payload=" +
        std::to_string(valid(payload)) +
        " marker=" + std::to_string(valid(marker)));
  }
}

void test_sample_source_frame_limit_is_not_reapplied_after_resampling() {
  TempDirectory temp;
  const auto project = temp.path() / "sample-source-frame-boundary.lmdj";
  const PatternId pattern_id{uuid(610)};
  Application application(sample_config(temp.path()));
  const auto created = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{uuid(611)},
          120,
          Pattern{
              pattern_id,
              1,
              {{PadSlotId{0, 0}, 0, 240, 127}},
          },
      });
  LMDJ_CHECK(created.has_value());

  const auto source = mono_pcm16_wav(220'501, 44'100);
  const auto token = uuid(612);
  LMDJ_CHECK(
      application.begin_sample_import(
          {token,
           project,
           {CommandId{uuid(613)}, 0},
           {0, 0},
           AssetId{uuid(614)},
           source.size()})
          .has_value());
  LMDJ_CHECK(
      application.append_sample_import(token, 0, source, true).has_value());
  const auto imported = application.commit_sample_import(token);
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(imported.value().committed_revision == 1);

  const auto prepared = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{project, pattern_id, kStage8WebLimits});
  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value()->pads.size() == 1);
  const auto& sample = *prepared.value()->pads.at(0).sample;
  LMDJ_CHECK(sample.sample_rate == 48'000);
  LMDJ_CHECK(sample.interleaved.size() / sample.channels == 240'002);
}

void test_sample_delayed_replays_report_original_committed_revision() {
  TempDirectory temp;
  const auto project = temp.path() / "sample-delayed-replay.lmdj";
  const auto source = file_bytes("tests/fixtures/audio/mono-44100.wav");
  Application application(sample_config(temp.path()));
  LMDJ_CHECK(
      application
          .create_initial_project(
              {project,
               ProjectId{uuid(620)},
               120,
               Pattern{PatternId{uuid(621)}, 1, {}}})
          .has_value());

  const auto import_command = CommandId{uuid(622)};
  const auto import_asset = AssetId{uuid(623)};
  const auto import_once = [&](std::string token) {
    LMDJ_CHECK(
        application.begin_sample_import(
            {token,
             project,
             {import_command, 0},
             {0, 0},
             import_asset,
             source.size()})
            .has_value());
    LMDJ_CHECK(
        application.append_sample_import(token, 0, source, true).has_value());
    return application.commit_sample_import(token);
  };
  const auto imported = import_once(uuid(624));
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(imported.value().committed_revision == 1);

  const auto advance_after_import = application.update_sample_pad(
      {project,
       {CommandId{uuid(625)}, 1},
       {0, 0},
       PadPlayback{1, 7, TriggerMode::gate, -300, false}});
  LMDJ_CHECK(advance_after_import.has_value());
  LMDJ_CHECK(advance_after_import.value().committed_revision == 2);
  const auto replayed_import = import_once(uuid(626));
  LMDJ_CHECK(replayed_import.has_value());
  LMDJ_CHECK(replayed_import.value().committed_revision == 1);

  const SampleUpdateRequest update{
      project,
      {CommandId{uuid(627)}, 2},
      {0, 0},
      PadPlayback{2, 6, TriggerMode::loop_gate, -600, true},
  };
  const auto updated = application.update_sample_pad(update);
  LMDJ_CHECK(updated.has_value());
  LMDJ_CHECK(updated.value().committed_revision == 3);
  const auto advance_after_update = application.reset_sample_pad(
      {project, {CommandId{uuid(628)}, 3}, {0, 0}});
  LMDJ_CHECK(advance_after_update.has_value());
  LMDJ_CHECK(advance_after_update.value().committed_revision == 4);
  const auto replayed_update = application.update_sample_pad(update);
  LMDJ_CHECK(replayed_update.has_value());
  LMDJ_CHECK(replayed_update.value().committed_revision == 3);

  const SampleResetRequest reset{
      project,
      {CommandId{uuid(629)}, 4},
      {0, 0},
  };
  const auto reset_result = application.reset_sample_pad(reset);
  LMDJ_CHECK(reset_result.has_value());
  LMDJ_CHECK(reset_result.value().committed_revision == 5);
  const auto advance_after_reset = application.update_sample_pad(
      {project,
       {CommandId{uuid(630)}, 5},
       {0, 0},
       PadPlayback{1, 7, TriggerMode::loop_toggle, 0, false}});
  LMDJ_CHECK(advance_after_reset.has_value());
  LMDJ_CHECK(advance_after_reset.value().committed_revision == 6);
  const auto replayed_reset = application.reset_sample_pad(reset);
  LMDJ_CHECK(replayed_reset.has_value());
  LMDJ_CHECK(replayed_reset.value().committed_revision == 5);
}

void test_sample_json_delayed_replays_report_current_project_revision() {
  TempDirectory temp;
  const auto project = temp.path() / "sample-json-delayed-replay.lmdj";
  const auto source = file_bytes("tests/fixtures/audio/mono-44100.wav");
  Application application(sample_config(temp.path()));
  LMDJ_CHECK(
      application
          .create_initial_project(
              {project,
               ProjectId{uuid(720)},
               120,
               Pattern{PatternId{uuid(721)}, 1, {}}})
          .has_value());

  const auto import_once = [&](std::string token) {
    check_success(
        application.command(
            {
                {"operation", "sample.import.begin"},
                {"import_token", token},
                {"project_path", project.generic_string()},
                {"command_id", uuid(722)},
                {"expected_revision", 0},
                {"slot", slot(0, 0)},
                {"asset_id", uuid(723)},
                {"byte_length", source.size()},
            }),
        nullptr);
    LMDJ_CHECK(
        application.append_sample_import(token, 0, source, true).has_value());
    return application.command(
        {
            {"operation", "sample.import.commit"},
            {"import_token", token},
        });
  };
  const auto imported = import_once(uuid(724));
  check_success(imported, 1);
  LMDJ_CHECK(imported.at("result").at("committed_revision") == 1);

  const auto advance_import = application.command(
      {
          {"operation", "sample.update_pad"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(725)},
          {"expected_revision", 1},
          {"slot", slot(0, 0)},
          {"playback",
           {{"trim_start_frame", 1},
            {"trim_end_frame", 7},
            {"trigger_mode", "gate"},
            {"gain_millidb", -300},
            {"muted", false}}},
      });
  check_success(advance_import, 2);
  const auto replayed_import = import_once(uuid(726));
  LMDJ_CHECK(replayed_import.at("ok") == true);
  LMDJ_CHECK(
      replayed_import.at("result").at("committed_revision") == 1);

  const nlohmann::json update{
      {"operation", "sample.update_pad"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(727)},
      {"expected_revision", 2},
      {"slot", slot(0, 0)},
      {"playback",
       {{"trim_start_frame", 2},
        {"trim_end_frame", 6},
        {"trigger_mode", "loop_gate"},
        {"gain_millidb", -600},
        {"muted", true}}},
  };
  check_success(application.command(update), 3);
  check_success(
      application.command(
          {
              {"operation", "sample.reset_pad"},
              {"project_path", project.generic_string()},
              {"command_id", uuid(728)},
              {"expected_revision", 3},
              {"slot", slot(0, 0)},
          }),
      4);
  const auto replayed_update = application.command(update);
  LMDJ_CHECK(replayed_update.at("ok") == true);
  LMDJ_CHECK(
      replayed_update.at("result").at("committed_revision") == 3);

  const nlohmann::json reset{
      {"operation", "sample.reset_pad"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(729)},
      {"expected_revision", 4},
      {"slot", slot(0, 0)},
  };
  check_success(application.command(reset), 5);
  check_success(
      application.command(
          {
              {"operation", "sample.update_pad"},
              {"project_path", project.generic_string()},
              {"command_id", uuid(730)},
              {"expected_revision", 5},
              {"slot", slot(0, 0)},
              {"playback",
               {{"trim_start_frame", 1},
                {"trim_end_frame", 7},
                {"trigger_mode", "loop_toggle"},
                {"gain_millidb", 0},
                {"muted", false}}},
          }),
      6);
  const auto replayed_reset = application.command(reset);
  LMDJ_CHECK(replayed_reset.at("ok") == true);
  LMDJ_CHECK(
      replayed_reset.at("result").at("committed_revision") == 5);

  const auto import_revision =
      replayed_import.at("project_revision").get<std::uint64_t>();
  const auto update_revision =
      replayed_update.at("project_revision").get<std::uint64_t>();
  const auto reset_revision =
      replayed_reset.at("project_revision").get<std::uint64_t>();
  if (import_revision != 2 || update_revision != 4 || reset_revision != 6) {
    throw std::runtime_error(
        "Sample JSON replay revisions are stale: import=" +
        std::to_string(import_revision) +
        " update=" + std::to_string(update_revision) +
        " reset=" + std::to_string(reset_revision));
  }
}

void test_sample_artifact_busy_errors_remain_storage_errors() {
  TempDirectory temp;
  const auto project = temp.path() / "sample-artifact-busy.lmdj";
  const auto source = file_bytes("tests/fixtures/audio/mono-44100.wav");
  Application application(sample_config(temp.path()));
  Application competitor(sample_config(temp.path()));
  create_single_asset_project(
      application, project, source, 640, uuid(644), uuid(645));

  check_sample_artifact_busy_error(
      competitor,
      project,
      [&] { return application.inspect_sample({project, {0, 0}}); });
  check_sample_artifact_busy_error(
      competitor,
      project,
      [&] {
        return application.query_sample_waveform(
            {project, {0, 0}, {0, 8, 4}});
      });
  check_sample_artifact_busy_error(
      competitor,
      project,
      [&] {
        return application.update_sample_pad(
            {project,
             {CommandId{uuid(646)}, 3},
             {0, 0},
             PadPlayback{1, 7, TriggerMode::gate, 0, false}});
      });
  LMDJ_CHECK(
      application.inspect_sample({project, {0, 0}})
          .value()
          .project_revision == 3);
}

void test_sample_waveform_json_uses_one_authoritative_projection() {
  TempDirectory temp;
  const auto project = temp.path() / "sample-waveform-projection.lmdj";
  const auto source = file_bytes("tests/fixtures/audio/mono-44100.wav");
  const auto replacement = mono_pcm16_wav(8);
  Application application(sample_config(temp.path()));
  create_single_asset_project(
      application, project, source, 660, uuid(664), uuid(665));

  SampleMutationHookContext context{
      &application,
      project,
      &replacement,
  };
  lmdj::facade::testing::SampleProjectionHook hook{
      &context,
      replace_sample_after_projection_load,
  };
  SampleProjectionHookGuard guard(&hook);
  const auto waveform = application.query(
      {
          {"operation", "sample.waveform"},
          {"project_path", project.generic_string()},
          {"slot", {{"bank", 0}, {"pad", 0}}},
          {"window",
           {{"start_frame", 0}, {"end_frame", 8}, {"bucket_count", 4}}},
      });
  LMDJ_CHECK(context.completed);
  check_success(waveform, 3);
  LMDJ_CHECK(
      waveform.at("result")
          .at("buckets")
          .at(0)
          .at("peak_magnitude") == 32'768);
  LMDJ_CHECK(
      application.inspect_sample({project, {0, 0}})
          .value()
          .project_revision == 5);
}

void test_sample_waveform_cache_uses_cooker_full_level_bucket_width() {
  TempDirectory temp;
  const auto project = temp.path() / "sample-waveform-cache-level.lmdj";
  const auto source = mono_pcm16_wav(5);
  Application application(sample_config(temp.path()));
  create_single_asset_project(
      application, project, source, 670, uuid(674), uuid(675));
  const auto inspected = application.inspect_sample({project, {0, 0}});
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().waveform_cache_identity.has_value());
  const auto artifact_sha =
      inspected.value().waveform_cache_identity->substr(0, 64);

  const auto partial = application.query_sample_waveform(
      {project, {0, 0}, {0, 4, 1}});
  LMDJ_CHECK(partial.has_value());
  LMDJ_CHECK(partial.value().buckets.size() == 1);
  check_peak_bucket(partial.value().buckets.at(0), 0, 4, 0);

  lmdj::project_io::WorkspaceCacheStore cache(
      temp.path() / ".lmdj-host/workspace-cache");
  const auto exact_key =
      artifact_sha + "/1/max-abs-mirror/3";
  const auto wrong_key =
      artifact_sha + "/1/max-abs-mirror/4";
  const auto cached = cache.read(exact_key);
  LMDJ_CHECK(cached.has_value());
  LMDJ_CHECK(cached.value().has_value());
  LMDJ_CHECK(!cache.read(wrong_key).value().has_value());
  const auto cached_text = std::string_view{
      reinterpret_cast<const char*>(cached.value()->data()),
      cached.value()->size()};
  const auto cached_json = nlohmann::json::parse(cached_text);
  LMDJ_CHECK(cached_json.at("frames_per_bucket") == 3);
  LMDJ_CHECK(cached_json.at("bucket_count") == 2);
  LMDJ_CHECK(cached_json.at("buckets").at(0).at("start_frame") == 0);
  LMDJ_CHECK(cached_json.at("buckets").at(0).at("end_frame") == 3);
  LMDJ_CHECK(cached_json.at("buckets").at(1).at("start_frame") == 3);
  LMDJ_CHECK(cached_json.at("buckets").at(1).at("end_frame") == 5);

  const auto misaligned_text = nlohmann::json{
      {"contract", "lmdj.sample-waveform-cache.v1"},
      {"metadata",
       {{"sample_rate", 48'000}, {"channels", 1}, {"source_frames", 5}}},
      {"algorithm_version", 1},
      {"fold", "max-abs-mirror"},
      {"frames_per_bucket", 3},
      {"bucket_count", 2},
      {"buckets",
       nlohmann::json::array(
           {{{"start_frame", 0}, {"end_frame", 2}, {"peak_magnitude", 0}},
            {{"start_frame", 2}, {"end_frame", 5}, {"peak_magnitude", 0}}})},
  }.dump();
  const auto misaligned_bytes = std::as_bytes(std::span<const char>{
      misaligned_text.data(), misaligned_text.size()});
  LMDJ_CHECK(cache.write(exact_key, misaligned_bytes).has_value());
  const auto repaired = application.query_sample_waveform(
      {project, {0, 0}, {0, 4, 1}});
  LMDJ_CHECK(repaired.has_value());
  check_peak_bucket(repaired.value().buckets.at(0), 0, 4, 0);
  const auto repaired_cache = cache.read(exact_key);
  LMDJ_CHECK(repaired_cache.has_value());
  LMDJ_CHECK(repaired_cache.value().has_value());
  LMDJ_CHECK(repaired_cache.value()->size() != misaligned_bytes.size() ||
             !std::equal(
                 repaired_cache.value()->begin(),
                 repaired_cache.value()->end(),
                 misaligned_bytes.begin(),
                 misaligned_bytes.end()));
}

}  // namespace

int main() {
  try {
    test_typed_sample_surface_is_atomic_bounded_and_cache_backed();
    test_typed_sample_surface_rejects_invalid_boundary_values();
    test_sample_import_abort_scavenge_replace_and_manifest_admission();
    test_sample_cleanup_half_failures_leave_one_retryable_unit();
    test_sample_source_frame_limit_is_not_reapplied_after_resampling();
    test_sample_delayed_replays_report_original_committed_revision();
    test_sample_json_delayed_replays_report_current_project_revision();
    test_sample_artifact_busy_errors_remain_storage_errors();
    test_sample_waveform_json_uses_one_authoritative_projection();
    test_sample_waveform_cache_uses_cooker_full_level_bucket_width();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "application facade sample surface tests: PASS\n";
  return 0;
}
