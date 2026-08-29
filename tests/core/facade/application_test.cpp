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
constexpr std::string_view kSequenceSessionId =
    "00000000-0000-4000-8000-000000000201";
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
      {"contract_version", "1.1.0"},
      {"entries", std::move(encoded_entries)},
      {"project_contract", "lmdj.project.v3"},
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



void create_golden_project(
    Application& application,
    const std::filesystem::path& project) {
  const auto created = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{std::string{kProjectId}},
          120,
          Pattern{
              PatternId{std::string{kPatternId}},
              1,
              {
                  {{0, 0}, 0, 240, 127},
                  {{0, 1}, 960, 240, 127},
                  {{0, 0}, 1920, 240, 127},
                  {{0, 1}, 2880, 240, 127},
              },
          },
      });
  LMDJ_CHECK(created.has_value());

  auto response = application.command(import_request(
      project,
      1,
      kKickAssetId,
      std::filesystem::absolute("tests/fixtures/audio/kick.wav"),
      0));
  check_success(response, 1);

  response = application.command(import_request(
      project,
      2,
      kSnareAssetId,
      std::filesystem::absolute("tests/fixtures/audio/snare.wav"),
      1));
  check_success(response, 2);

  response = application.command(
      assign_request(project, 3, 0, kKickAssetId, 2));
  check_success(response, 3);
  response = application.command(
      assign_request(project, 4, 1, kSnareAssetId, 3));
  check_success(response, 4);

  response = application.command(
      assign_request(project, 5, 0, kKickAssetId, 4));
  check_success(response, 5);
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

void test_module_versions_and_dependencies_are_exact() {
  const auto application = nlohmann::json::parse(
      read_bytes("packages/application-facade/module.json"));
  const auto project_io = nlohmann::json::parse(
      read_bytes("packages/project-io/module.json"));
  LMDJ_CHECK(
      (application ==
       nlohmann::json{
           {"contract", "lmdj.module.v1"},
           {"module", "application-facade"},
           {"version", "2.1.0"},
           {"api_version", 2},
           {"dependencies",
            {
                {"foundation", "0.3.0"},
                {"authoring-domain", "1.0.0"},
                {"project-io", "1.0.0"},
                {"project-cooker", "1.0.0"},
                {"audio-runtime", "2.0.0"},
                {"provider-sdk", "1.1.4"},
            }},
       }));
  LMDJ_CHECK(project_io.at("module") == "project-io");
  LMDJ_CHECK(project_io.at("version") == "1.0.0");
}

void test_all_operations_share_one_facade_and_revision_contract() {
  TempDirectory temp;
  const auto project = temp.path() / "proof-beat.lmdj";
  auto registry = proof_registry();
  Application application(config(temp.path(), registry));
  create_golden_project(application, project);

  auto response = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(response, 5);
  const auto& projected = response.at("result").at("project");
  check_exact_keys(
      projected,
      {
          "contract",
          "project_id",
          "revision",
          "bpm",
          "banks",
          "assets",
          "patterns",
          "sequence_settings",
      });
  LMDJ_CHECK(projected.at("contract") == "lmdj.project.v3");
  LMDJ_CHECK(projected.at("revision") == 5);
  LMDJ_CHECK(projected.at("patterns").at(kPatternId).at("events").size() == 4);

  response = application.query(
      {
          {"operation", "sequence.recovery.list"},
          {"project_path", project.generic_string()},
      });
  check_success(response, nullptr);
  LMDJ_CHECK(response.at("result").at("candidates").empty());

  response = application.query(
      {
          {"operation", "snapshot.cook"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
      });
  check_success(response, 5);
  check_exact_keys(
      response.at("result"),
      {"pattern_id", "event_count", "artifact_sha256s"});
  LMDJ_CHECK(response.at("result").at("event_count") == 4);
  LMDJ_CHECK(response.dump().find("snapshot_id") == std::string::npos);
  LMDJ_CHECK(
      response.at("result").at("artifact_sha256s").size() == 2);

  response = application.query({{"operation", "provider.list"}});
  check_success(response, nullptr);
  LMDJ_CHECK(response.at("result").at("providers").size() == 2);

  response = application.command(
      {
          {"operation", "provider.select"},
          {"capability", kCapability},
          {"provider_id", "local.proof.success"},
      });
  check_success(response, nullptr);
  response = application.query(
      {
          {"operation", "provider.selected"},
          {"capability", kCapability},
      });
  check_success(response, nullptr);
  LMDJ_CHECK(
      response.at("result").at("provider_id") ==
      "local.proof.success");

  response = application.command(
      {
          {"operation", "provider.run"},
          {"attempt_id", "attempt-facade-success"},
          {"capability", kCapability},
          {"inputs",
           nlohmann::json::array({
               {
                   {"port", "inputs"},
                   {"artifact",
                    {
                        {"sha256", std::string(64, 'a')},
                        {"media_type", "application/octet-stream"},
                        {"byte_length", 1},
                    }},
               },
           })},
          {"parameters", nlohmann::json::object()},
          {"data_classification", "public"},
          {"platform", "test"},
          {"region", "local"},
          {"required_permissions",
           nlohmann::json::array({"proof.execute"})},
      });
  check_success(response, nullptr);
  check_exact_keys(
      response.at("result"),
      {
          "attempt_id",
          "candidate_id",
          "outputs",
          "provenance",
      });
  const auto expected_outputs = nlohmann::json::array({
      {
          {"port", "candidate"},
          {"artifact",
           {
               {"sha256",
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
               {"media_type", "application/x-lmdj-proof"},
               {"byte_length", 0},
           }},
      },
  });
  LMDJ_CHECK(response.at("result").at("outputs") == expected_outputs);

  response = application.query(
      {
          {"operation", "attempt.inspect"},
          {"attempt_id", "attempt-facade-success"},
      });
  check_success(response, nullptr);
  LMDJ_CHECK(response.at("result").at("attempt_id") ==
             "attempt-facade-success");
  LMDJ_CHECK(response.at("result").at("status") == "succeeded");
  LMDJ_CHECK(
      response.at("result").at("request").at("inputs").at(0).at("port") ==
      "inputs");
  LMDJ_CHECK(
      response.at("result").at("minted_outputs") == expected_outputs);
  LMDJ_CHECK(
      response.at("result").at("candidate_outputs") == expected_outputs);
}

void test_project_bundle_discovery_and_import_are_typed_facade_apis() {
  TempDirectory temp;
  const auto source = temp.path() / "source.lmdj";
  const auto workspace = temp.path() / "workspace";
  Application application(config(workspace));
  const auto created = application.create_initial_project(
      InitialProjectRequest{
          source,
          ProjectId{std::string{kProjectId}},
          120,
          Pattern{PatternId{std::string{kPatternId}}, 1, {}},
      });
  LMDJ_CHECK(created.has_value());
  const auto fixture = facade_bundle_fixture(
      source, temp.path(), std::string{kProjectId});
  LMDJ_CHECK(application.list_local_projects().value().empty());

  const auto token = uuid(900);
  const auto session = application.begin_project_bundle_import(
      {
          token,
          fixture.index.size(),
          hash_text(temp.path(), "index-hash.bin", fixture.index),
      });
  LMDJ_CHECK(session.has_value());
  LMDJ_CHECK(session.value().token == token);
  LMDJ_CHECK(session.value().expected_index_bytes == fixture.index.size());
  stream_facade_bundle(application, token, fixture);
  const auto committed = application.commit_project_bundle_import(token);
  if (!committed.has_value()) {
    throw std::runtime_error(
        "bundle import commit failed: " + committed.error().message + " " +
        committed.error().details.dump());
  }
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().project_id.value() == kProjectId);
  LMDJ_CHECK(committed.value().pattern_id.value() == kPatternId);
  LMDJ_CHECK(committed.value().bundle_digest == fixture.digest);
  const auto listed = application.list_local_projects();
  LMDJ_CHECK(listed.has_value());
  LMDJ_CHECK(listed.value().size() == 1);
  LMDJ_CHECK(listed.value().front() == committed.value());

  LMDJ_CHECK(
      !application
           .begin_project_bundle_import(
               {"invalid-token", fixture.index.size(), std::string(64, '0')})
           .has_value());
  LMDJ_CHECK(
      !application
           .begin_project_bundle_import(
               {uuid(901), fixture.index.size(), std::string(64, 'A')})
           .has_value());

  const auto duplicate_token = uuid(907);
  const auto index_digest =
      hash_text(temp.path(), "duplicate-index-hash.bin", fixture.index);
  LMDJ_CHECK(
      application
          .begin_project_bundle_import(
              {duplicate_token, fixture.index.size(), index_digest})
          .has_value());
  LMDJ_CHECK(
      !application
           .begin_project_bundle_import(
               {duplicate_token, fixture.index.size(), index_digest})
           .has_value());
  LMDJ_CHECK(
      application.abort_project_bundle_import(duplicate_token).has_value());

  const std::array<std::byte, 1> one_byte{std::byte{0}};
  LMDJ_CHECK(
      !application
           .append_project_bundle_index(
               "invalid-token", 0, one_byte, true)
           .has_value());
  LMDJ_CHECK(
      !application
           .append_project_bundle_entry(
               "invalid-token", 0, 0, one_byte, true)
           .has_value());
  LMDJ_CHECK(
      !application.commit_project_bundle_import("invalid-token")
           .has_value());
  LMDJ_CHECK(
      !application.abort_project_bundle_import("invalid-token")
           .has_value());

  const auto invalid_offset_token = uuid(902);
  LMDJ_CHECK(
      application
          .begin_project_bundle_import(
              {
                  invalid_offset_token,
                  fixture.index.size(),
                  hash_text(temp.path(), "offset-hash.bin", fixture.index),
              })
          .has_value());
  const auto index_bytes = byte_vector(fixture.index);
  const auto invalid_offset = application.append_project_bundle_index(
      invalid_offset_token, 1, index_bytes, true);
  LMDJ_CHECK(!invalid_offset.has_value());
  LMDJ_CHECK(invalid_offset.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      application.abort_project_bundle_import(invalid_offset_token)
          .has_value());

  const auto early_final_token = uuid(903);
  LMDJ_CHECK(
      application
          .begin_project_bundle_import(
              {
                  early_final_token,
                  fixture.index.size(),
                  hash_text(temp.path(), "final-hash.bin", fixture.index),
              })
          .has_value());
  const auto early_final = application.append_project_bundle_index(
      early_final_token,
      0,
      std::span<const std::byte>{index_bytes.data(), 1},
      true);
  LMDJ_CHECK(!early_final.has_value());
  LMDJ_CHECK(early_final.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      application.abort_project_bundle_import(early_final_token)
          .has_value());

  const auto wrong_identity = facade_bundle_fixture(
      source, temp.path(), uuid(904));
  const auto wrong_identity_token = uuid(905);
  LMDJ_CHECK(
      application
          .begin_project_bundle_import(
              {
                  wrong_identity_token,
                  wrong_identity.index.size(),
                  hash_text(
                      temp.path(),
                      "wrong-identity-hash.bin",
                      wrong_identity.index),
              })
          .has_value());
  stream_facade_bundle(application, wrong_identity_token, wrong_identity);
  const auto rejected =
      application.commit_project_bundle_import(wrong_identity_token);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
}

void test_application_startup_cleans_incomplete_bundle_staging() {
  TempDirectory temp;
  const auto workspace = temp.path() / "workspace";
  const auto stale = workspace / ".lmdj-host" / "import-staging" /
                     uuid(906);
  std::filesystem::create_directories(stale / "project.lmdj");
  write_bytes(stale / "project.lmdj" / "partial.bin", "partial");
  LMDJ_CHECK(std::filesystem::exists(stale));

  Application application(config(workspace));

  LMDJ_CHECK(!std::filesystem::exists(stale));
}

void test_project_bundle_host_paths_fail_closed() {
  TempDirectory temp;
  const auto list_workspace = temp.path() / "list-workspace";
  std::filesystem::create_directories(list_workspace);
  Application list_application(config(list_workspace));
  std::filesystem::remove_all(list_workspace);
  write_bytes(list_workspace, "not-a-directory");
  const auto listed = list_application.list_local_projects();
  LMDJ_CHECK(!listed.has_value());

  const auto cleanup_workspace = temp.path() / "cleanup-workspace";
  std::filesystem::create_directories(cleanup_workspace);
  write_bytes(cleanup_workspace / ".lmdj-host", "not-a-directory");
  bool cleanup_failed_closed = false;
  try {
    Application cleanup_application(config(cleanup_workspace));
  } catch (const std::runtime_error&) {
    cleanup_failed_closed = true;
  }
  LMDJ_CHECK(cleanup_failed_closed);
}

void test_render_recooks_after_restart_and_publishes_golden_atomically() {
  TempDirectory temp;
  const auto project = temp.path() / "proof-beat.lmdj";
  {
    Application application(config(temp.path()));
    create_golden_project(application, project);
    const auto cooked = application.query(
        {
            {"operation", "snapshot.cook"},
            {"project_path", project.generic_string()},
            {"pattern_id", kPatternId},
        });
    check_success(cooked, 5);
  }

  const auto project_before = read_bytes(project / "manifest.json");
  const auto output = temp.path() / "beat.wav";
  Application fresh(config(temp.path()));
  auto rendered = fresh.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", output.generic_string()},
      });
  check_success(rendered, 5);
  LMDJ_CHECK(rendered.dump().find("snapshot_id") == std::string::npos);
  LMDJ_CHECK(rendered.at("result").at("artifact").at("sha256") == kGoldenSha);
  LMDJ_CHECK(rendered.at("result").at("output_path") ==
             output.generic_string());
  LMDJ_CHECK(std::filesystem::is_regular_file(output));
  LMDJ_CHECK(read_bytes(project / "manifest.json") == project_before);

  const auto output_before = read_bytes(output);
  const auto existing = fresh.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", output.generic_string()},
      });
  check_error(existing, "INVALID_ARGUMENT");
  LMDJ_CHECK(read_bytes(output) == output_before);

  const auto inside = project / "beat.wav";
  const auto rejected = fresh.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", inside.generic_string()},
      });
  check_error(rejected, "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(inside));
  for (const auto& entry :
       std::filesystem::directory_iterator(temp.path())) {
    const auto name = entry.path().filename().string();
    LMDJ_CHECK(
        name.find(".lmdj-render-") == std::string::npos);
    LMDJ_CHECK(
        name.find(".core-render-") == std::string::npos);
  }
}

void test_typed_sequence_host_api_prepares_records_and_recovers() {
  TempDirectory temp;
  const auto project = temp.path() / "typed-snapshot.lmdj";
  Application application(config(temp.path()));
  create_golden_project(application, project);
  const auto manifest_before = read_bytes(project / "manifest.json");

  const auto prepared = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{project, PatternId{std::string(kPatternId)}});

  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value()->project_revision == 5);
  LMDJ_CHECK(prepared.value()->pads.size() == 2);
  LMDJ_CHECK(prepared.value()->events.size() == 4);
  LMDJ_CHECK(read_bytes(project / "manifest.json") == manifest_before);
  const auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(inspected, 5);

  const auto invalid_path = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{
          std::filesystem::path{"relative.lmdj"},
          PatternId{std::string(kPatternId)},
      });
  LMDJ_CHECK(!invalid_path.has_value());
  LMDJ_CHECK(
      invalid_path.error().code ==
      lmdj::foundation::ErrorCode::invalid_argument);

  const auto capture_project = temp.path() / "typed-sequence.lmdj";
  create_single_asset_project(
      application, capture_project, mono_pcm16_wav(16), 200, uuid(204),
      uuid(205));
  const lmdj::foundation::SequenceSessionId session{uuid(202)};
  const auto begun = application.begin_sequence(
      {capture_project, session, PatternId{uuid(205)}, 3, 0});
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(
      begun.value().status.state == lmdj::facade::SequenceRecordState::active);
  LMDJ_CHECK(application.record_sequence_event({
      capture_project, session, {{0, 0}, 96, 0, 1, true}}).has_value());
  LMDJ_CHECK(application.record_sequence_event({
      capture_project, session, {{0, 0}, 0, 12'000, 2, false}}).has_value());
  const auto committed = application.flush_sequence(
      {capture_project, session, CommandId{uuid(207)}, 12'000});
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().committed_revision == 4);
  const auto stopped = application.stop_sequence(
      {capture_project, session, CommandId{uuid(208)}, 12'001});
  LMDJ_CHECK(stopped.has_value());
  LMDJ_CHECK(
      stopped.value().status.state == lmdj::facade::SequenceRecordState::inactive);
  const auto captured = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", capture_project.generic_string()},
      });
  check_success(captured, 4);
  const auto& persisted = captured.at("result")
                              .at("project")
                              .at("patterns")
                              .at(uuid(205))
                              .at("events");
  LMDJ_CHECK(persisted.size() == 1);
  LMDJ_CHECK(persisted.at(0).at("onset_tick") == 0);
  LMDJ_CHECK(persisted.at(0).at("duration_tick") == 480);

  const auto recovery_project = temp.path() / "typed-recovery.lmdj";
  const auto recovery_pattern = uuid(209);
  const auto recovery_session = lmdj::foundation::SequenceSessionId{uuid(210)};
  {
    Application owner(config(temp.path()));
    create_single_asset_project(
        owner, recovery_project, mono_pcm16_wav(16), 211, uuid(215),
        recovery_pattern);
    LMDJ_CHECK(owner.begin_sequence(
        {recovery_project, recovery_session, PatternId{recovery_pattern}, 3, 0})
                   .has_value());
    LMDJ_CHECK(owner.record_sequence_event({
        recovery_project, recovery_session, {{0, 0}, 80, 0, 1, true}})
                   .has_value());
  }
  const auto candidates = application.list_sequence_recovery({recovery_project});
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().reason == "owner_lost");
  LMDJ_CHECK(candidates.value().front().event_count == 1);
  const auto recovered = application.apply_sequence_recovery(
      {recovery_project, recovery_session, std::nullopt});
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().committed_revision == 4);
}

void test_typed_initial_project_creation_persists_one_pattern_at_revision_zero() {
  TempDirectory temp;
  const auto project = temp.path() / "initial-pattern.lmdj";
  Application application(config(temp.path()));
  const Pattern initial_pattern{
      PatternId{std::string(kPatternId)},
      1,
      {},
  };

  const auto created = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{std::string(kProjectId)},
          120,
          initial_pattern,
      });

  LMDJ_CHECK(created.has_value());
  LMDJ_CHECK(created.value().revision == 0);
  LMDJ_CHECK(created.value().patterns.size() == 1);
  LMDJ_CHECK(
      created.value().patterns.at(initial_pattern.id) == initial_pattern);
  const auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(inspected, 0);
  LMDJ_CHECK(
      inspected.at("result").at("project").at("project_id") ==
      kProjectId);
  LMDJ_CHECK(
      inspected.at("result")
          .at("project")
          .at("patterns")
          .at(kPatternId)
          .at("events")
          .empty());

  const auto duplicate = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{uuid(999)},
          90,
          Pattern{PatternId{uuid(998)}, 1, {}},
      });
  LMDJ_CHECK(!duplicate.has_value());
  LMDJ_CHECK(duplicate.error().code == ErrorCode::duplicate_id);
  const auto unchanged = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(unchanged, 0);
  LMDJ_CHECK(
      unchanged.at("result").at("project").at("project_id") ==
      kProjectId);

  const auto invalid_project = temp.path() / "invalid-initial.lmdj";
  const auto invalid = application.create_initial_project(
      InitialProjectRequest{
          invalid_project,
          ProjectId{uuid(997)},
          120,
          Pattern{PatternId{uuid(996)}, 3, {}},
      });
  LMDJ_CHECK(!invalid.has_value());
  LMDJ_CHECK(invalid.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!std::filesystem::exists(invalid_project));

  const auto invalid_pattern_id_project =
      temp.path() / "invalid-pattern-id.lmdj";
  const auto invalid_pattern_id = application.create_initial_project(
      InitialProjectRequest{
          invalid_pattern_id_project,
          ProjectId{uuid(995)},
          120,
          Pattern{PatternId{"INVALID"}, 1, {}},
      });
  LMDJ_CHECK(!invalid_pattern_id.has_value());
  LMDJ_CHECK(
      invalid_pattern_id.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!std::filesystem::exists(invalid_pattern_id_project));

  const auto invalid_pattern_event_project =
      temp.path() / "invalid-pattern-event.lmdj";
  const auto invalid_pattern_event = application.create_initial_project(
      InitialProjectRequest{
          invalid_pattern_event_project,
          ProjectId{uuid(994)},
          120,
          Pattern{
              PatternId{uuid(993)},
              1,
              {{PadSlotId{0, 0}, 0, 240, 0}},
          },
      });
  LMDJ_CHECK(!invalid_pattern_event.has_value());
  LMDJ_CHECK(
      invalid_pattern_event.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!std::filesystem::exists(invalid_pattern_event_project));
}

void test_byte_import_and_opaque_writer_lease_share_one_storage_platform() {
  static_assert(!std::is_copy_constructible_v<RuntimeProjectWriterLease>);
  static_assert(!std::is_copy_assignable_v<RuntimeProjectWriterLease>);
  static_assert(std::is_nothrow_move_constructible_v<
                RuntimeProjectWriterLease>);
  static_assert(std::is_nothrow_move_assignable_v<
                RuntimeProjectWriterLease>);

  TempDirectory temp;
  const auto project = temp.path() / "leased.lmdj";
  Application application(config(temp.path()));
  Application competitor(config(temp.path()));

  const auto bytes = mono_pcm16_wav(2);
  {
    auto acquired = application.acquire_project_writer(project);
    LMDJ_CHECK(acquired.has_value());
    RuntimeProjectWriterLease lease = std::move(acquired.value());

    auto nested = application.acquire_project_writer(project);
    LMDJ_CHECK(nested.has_value());
    check_success(application.command(create_request(project)), 0);
    const auto imported = application.import_artifact_bytes(
        ArtifactBytesImportRequest{
            project,
            CommandMeta{CommandId{uuid(300)}, 0},
            AssetId{uuid(301)},
            "audio/wav",
            bytes,
        });
    LMDJ_CHECK(imported.has_value());
    LMDJ_CHECK(imported.value().state.revision == 1);

    const auto invalid_import = application.import_artifact_bytes(
        ArtifactBytesImportRequest{
            project,
            CommandMeta{CommandId{uuid(303)}, 1},
            AssetId{uuid(304)},
            "",
            bytes,
        });
    LMDJ_CHECK(!invalid_import.has_value());
    LMDJ_CHECK(invalid_import.error().code == ErrorCode::invalid_argument);

    const auto invalid_begin = application.begin_sequence(
        {project,
         lmdj::foundation::SequenceSessionId{"not-a-uuid"},
         PatternId{uuid(302)},
         1,
         0});
    LMDJ_CHECK(!invalid_begin.has_value());
    LMDJ_CHECK(invalid_begin.error().code == ErrorCode::invalid_argument);

    const auto busy = competitor.acquire_project_writer(project);
    LMDJ_CHECK(!busy.has_value());
    LMDJ_CHECK(busy.error().code == ErrorCode::io_error);
    LMDJ_CHECK(
        (busy.error().details ==
         nlohmann::json{{"storage_condition", "project_busy"}}));
    LMDJ_CHECK(
        busy.error().message.find(project.generic_string()) ==
        std::string::npos);
    (void)lease;
  }

  {
    auto acquired_after_release = competitor.acquire_project_writer(project);
    LMDJ_CHECK(acquired_after_release.has_value());
  }
  const auto invalid = application.acquire_project_writer("relative.lmdj");
  LMDJ_CHECK(!invalid.has_value());
  LMDJ_CHECK(invalid.error().code == ErrorCode::invalid_argument);

  const auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(inspected, 1);
  LMDJ_CHECK(
      inspected.at("result").at("project").at("assets").contains(uuid(301)));
}

void test_render_rejects_symlinked_parent_and_never_reuses_crash_residue() {
  TempDirectory temp;
  const auto project = temp.path() / "proof-beat.lmdj";
  Application application(config(temp.path()));
  create_golden_project(application, project);

  const auto output = temp.path() / "residue.wav";
  const auto residue =
      temp.path() / "residue.wav.lmdj-render-0.tmp";
  {
    std::ofstream stream(residue, std::ios::binary);
    stream << "crash-residue-must-survive";
  }
  const auto rendered = application.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", output.generic_string()},
      });
  check_success(rendered, 5);
  LMDJ_CHECK(read_bytes(residue) == "crash-residue-must-survive");
  for (const auto& entry :
       std::filesystem::directory_iterator(temp.path())) {
    LMDJ_CHECK(
        entry.path().filename().string().find(".core-render-") ==
        std::string::npos);
  }

  const auto alias = temp.path() / "outside-looking";
  std::filesystem::create_directory_symlink(project, alias);
  const auto injected = alias / "injected.wav";
  const auto rejected = application.command(
      {
          {"operation", "render.offline"},
          {"project_path", project.generic_string()},
          {"pattern_id", kPatternId},
          {"output_path", injected.generic_string()},
      });
  check_error(rejected, "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project / "injected.wav"));
}

void test_asset_and_pad_replay_identity_is_enforced() {
  TempDirectory temp;
  const auto project = temp.path() / "command-identity.lmdj";
  const auto source = temp.path() / "source-a.wav";
  const auto changed_source = temp.path() / "source-b.wav";
  write_bytes(source, "source-a");
  write_bytes(changed_source, "source-b");
  Application application(config(temp.path()));
  check_success(application.command(create_request(project)), 0);

  const auto import = nlohmann::json{
      {"operation", "asset.import"},
      {"project_path", project.generic_string()},
      {"command_id", uuid(71)},
      {"expected_revision", 0},
      {"asset_id", kKickAssetId},
      {"source_path", source.generic_string()},
      {"media_type", "audio/wav"},
  };
  auto response = application.command(import);
  check_success(response, 1);
  LMDJ_CHECK(response.at("result").at("replayed") == false);
  response = application.command(import);
  check_success(response, 1);
  LMDJ_CHECK(response.at("result").at("asset_id") == kKickAssetId);
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  auto changed_import_revision = import;
  changed_import_revision["expected_revision"] = 1;
  check_error(
      application.command(changed_import_revision), "INVALID_ARGUMENT");
  auto changed_asset = import;
  changed_asset["asset_id"] = uuid(199);
  check_error(application.command(changed_asset), "INVALID_ARGUMENT");
  auto changed_bytes = import;
  changed_bytes["source_path"] = changed_source.generic_string();
  check_error(application.command(changed_bytes), "INVALID_ARGUMENT");
  auto changed_media = import;
  changed_media["media_type"] = "application/octet-stream";
  check_error(application.command(changed_media), "INVALID_ARGUMENT");

  auto import_id_as_pad = assign_request(
      project, 71, 0, kKickAssetId, 0);
  check_error(
      application.command(import_id_as_pad), "INVALID_ARGUMENT");

  const auto assignment =
      assign_request(project, 72, 0, kKickAssetId, 1);
  response = application.command(assignment);
  check_success(response, 2);
  LMDJ_CHECK(response.at("result").at("replayed") == false);
  response = application.command(assignment);
  check_success(response, 2);
  LMDJ_CHECK(response.at("result").at("slot") == slot(0, 0));
  LMDJ_CHECK(response.at("result").at("asset_id") == kKickAssetId);
  LMDJ_CHECK(response.at("result").at("replayed") == true);

  auto changed_pad_revision = assignment;
  changed_pad_revision["expected_revision"] = 2;
  check_error(
      application.command(changed_pad_revision), "INVALID_ARGUMENT");
  auto changed_slot = assignment;
  changed_slot["slot"] = slot(0, 1);
  check_error(application.command(changed_slot), "INVALID_ARGUMENT");
  auto changed_assignment = assignment;
  changed_assignment["asset_id"] = nullptr;
  check_error(
      application.command(changed_assignment), "INVALID_ARGUMENT");

  auto pad_id_as_import = import;
  pad_id_as_import["command_id"] = uuid(72);
  pad_id_as_import["expected_revision"] = 1;
  check_error(
      application.command(pad_id_as_import), "INVALID_ARGUMENT");

  Application fresh(config(temp.path()));
  response = fresh.command(import);
  check_success(response, 2);
  LMDJ_CHECK(response.at("result").at("asset_id") == kKickAssetId);
  LMDJ_CHECK(response.at("result").at("committed_revision") == 1);
  LMDJ_CHECK(response.at("result").at("replayed") == true);
  response = fresh.command(assignment);
  check_success(response, 2);
  LMDJ_CHECK(response.at("result").at("slot") == slot(0, 0));
  LMDJ_CHECK(response.at("result").at("asset_id") == kKickAssetId);
  LMDJ_CHECK(response.at("result").at("committed_revision") == 2);
  LMDJ_CHECK(response.at("result").at("replayed") == true);
}

void test_exact_shapes_routing_and_invalid_scalars_fail_before_mutation() {
  TempDirectory temp;
  const auto project = temp.path() / "shape.lmdj";
  Application application(config(temp.path()));

  const std::vector<std::string> commands{
      "project.create",
      "asset.import",
      "pad.assign",
      "sequence.record.begin",
      "sequence.record.event",
      "sequence.record.flush",
      "sequence.record.stop",
      "sequence.record.switch-request",
      "sequence.recovery.apply",
      "sequence.recovery.discard",
      "render.offline",
      "provider.select",
      "provider.run",
  };
  const std::vector<std::string> queries{
      "project.inspect",
      "sequence.record.status",
      "sequence.recovery.list",
      "snapshot.cook",
      "provider.list",
      "provider.selected",
      "attempt.inspect",
  };
  for (const auto& operation : commands) {
    check_error(
        application.query({{"operation", operation}}),
        "INVALID_ARGUMENT");
    check_error(
        application.command(
            {{"operation", operation}, {"unexpected", true}}),
        "INVALID_ARGUMENT");
  }
  for (const auto& operation : queries) {
    check_error(
        application.command({{"operation", operation}}),
        "INVALID_ARGUMENT");
    check_error(
        application.query(
            {{"operation", operation}, {"unexpected", true}}),
        "INVALID_ARGUMENT");
  }
  check_error(
      application.command({{"operation", "unknown"}}),
      "INVALID_ARGUMENT");
  check_error(application.command(nlohmann::json::object()), "INVALID_ARGUMENT");
  check_error(
      application.command({{"operation", 42}}),
      "INVALID_ARGUMENT");

  auto extra = create_request(project);
  extra["extra"] = true;
  check_error(application.command(extra), "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project));

  auto invalid_uuid = create_request(project);
  invalid_uuid["project_id"] = "00000000-0000-0000-0000-000000000001";
  check_error(application.command(invalid_uuid), "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project));

  auto invalid_utf8 = create_request(project);
  invalid_utf8["operation"] = std::string("\xc3\x28", 2);
  check_error(application.command(invalid_utf8), "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project));

  auto embedded_nul = create_request(project);
  embedded_nul["project_path"] =
      std::string(project.generic_string() + std::string("\0tail", 5));
  check_error(application.command(embedded_nul), "INVALID_ARGUMENT");
  LMDJ_CHECK(!std::filesystem::exists(project));

  check_success(application.command(create_request(project)), 0);
  auto fractional = import_request(
      project,
      31,
      kKickAssetId,
      std::filesystem::absolute("tests/fixtures/audio/kick.wav"),
      0);
  fractional["expected_revision"] = 0.0;
  check_error(application.command(fractional), "INVALID_ARGUMENT");
  for (const auto& invalid_revision :
       std::vector<nlohmann::json>{
           -1,
           "0",
           nlohmann::json::parse("18446744073709551616"),
       }) {
    auto invalid_integer = fractional;
    invalid_integer["expected_revision"] = invalid_revision;
    check_error(application.command(invalid_integer), "INVALID_ARGUMENT");
  }
  auto nested_extra = assign_request(
      project, 32, 0, kKickAssetId, 0);
  nested_extra["slot"]["extra"] = true;
  check_error(application.command(nested_extra), "INVALID_ARGUMENT");

  const auto stale_begin = application.command(
      {
          {"operation", "sequence.record.begin"},
          {"project_path", project.generic_string()},
          {"session_id", kSequenceSessionId},
          {"pattern_id", kPatternId},
          {"expected_revision", 1},
          {"runtime_frame", 0},
      });
  check_error(stale_begin, "REVISION_CONFLICT");
  LMDJ_CHECK(!std::filesystem::exists(
      project / "recovery/active/sequence.jsonl"));
  auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(inspected, 0);

  auto with_snapshot_id = nlohmann::json{
      {"operation", "snapshot.cook"},
      {"project_path", project.generic_string()},
      {"pattern_id", kPatternId},
      {"snapshot_id", "forbidden"},
  };
  check_error(application.query(with_snapshot_id), "INVALID_ARGUMENT");

  // A port name is not a file identifier. Names that no Capability could ever
  // declare must be rejected at the Host boundary, not accepted here and
  // rejected later as a generic artifact problem.
  for (const auto& port : {"Source", "in-put", "with.dot", "_leading", ""}) {
    auto bad_port = nlohmann::json{
        {"operation", "provider.run"},
        {"attempt_id", "attempt-port-shape"},
        {"capability", kCapability},
        {"inputs",
         nlohmann::json::array({
             {
                 {"port", port},
                 {"artifact",
                  {
                      {"sha256", std::string(64, 'a')},
                      {"media_type", "application/octet-stream"},
                      {"byte_length", 1},
                  }},
             },
         })},
        {"parameters", nlohmann::json::object()},
        {"data_classification", "public"},
        {"platform", "test"},
        {"region", "local"},
        {"required_permissions", nlohmann::json::array({"proof.execute"})},
    };
    check_error(application.command(bad_port), "INVALID_ARGUMENT");
  }
}

void test_provider_failures_are_errors_but_attempts_remain_queryable() {
  TempDirectory temp;
  Application application(config(temp.path()));
  auto selected = application.command(
      {
          {"operation", "provider.select"},
          {"capability", kCapability},
          {"provider_id", "local.proof.failure"},
      });
  check_success(selected, nullptr);
  const auto failed = application.command(
      {
          {"operation", "provider.run"},
          {"attempt_id", "attempt-facade-failure"},
          {"capability", kCapability},
          {"inputs", nlohmann::json::array()},
          {"parameters", nlohmann::json::object()},
          {"data_classification", "public"},
          {"platform", "test"},
          {"region", "local"},
          {"required_permissions",
           nlohmann::json::array({"proof.execute"})},
      });
  check_error(failed, "PROVIDER_FAILED");
  LMDJ_CHECK(
      failed.at("error").at("details").at("attempt_id") ==
      "attempt-facade-failure");

  const auto inspected = application.query(
      {
          {"operation", "attempt.inspect"},
          {"attempt_id", "attempt-facade-failure"},
      });
  check_success(inspected, nullptr);
  LMDJ_CHECK(inspected.at("result").at("status") == "failed");
  LMDJ_CHECK(
      inspected.dump().find("intentional proof failure") ==
      std::string::npos);

  Application deny_all(
      ApplicationConfig{
          temp.path() / "deny",
          proof_registry(),
          ProviderPolicy{},
          [] { return std::string("2026-07-31T00:00:00.000Z"); },
      });
  check_success(
      deny_all.command(
          {
              {"operation", "provider.select"},
              {"capability", kCapability},
              {"provider_id", "local.proof.success"},
          }),
      nullptr);
  const auto denied = deny_all.command(
      {
          {"operation", "provider.run"},
          {"attempt_id", "attempt-denied"},
          {"capability", kCapability},
          {"inputs", nlohmann::json::array()},
          {"parameters", nlohmann::json::object()},
          {"data_classification", "public"},
          {"platform", "test"},
          {"region", "local"},
          {"required_permissions",
           nlohmann::json::array({"proof.execute"})},
      });
  check_error(denied, "PERMISSION_DENIED");
}

}  // namespace

int main() {
  try {
    test_module_versions_and_dependencies_are_exact();
    test_all_operations_share_one_facade_and_revision_contract();
    test_project_bundle_discovery_and_import_are_typed_facade_apis();
    test_application_startup_cleans_incomplete_bundle_staging();
    test_project_bundle_host_paths_fail_closed();
    test_render_recooks_after_restart_and_publishes_golden_atomically();
    test_typed_sequence_host_api_prepares_records_and_recovers();
    test_typed_initial_project_creation_persists_one_pattern_at_revision_zero();
    test_byte_import_and_opaque_writer_lease_share_one_storage_platform();
    test_render_rejects_symlinked_parent_and_never_reuses_crash_residue();
    test_asset_and_pad_replay_identity_is_enforced();
    test_exact_shapes_routing_and_invalid_scalars_fail_before_mutation();
    test_provider_failures_are_errors_but_attempts_remain_queryable();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "application facade tests: PASS\n";
  return 0;
}
