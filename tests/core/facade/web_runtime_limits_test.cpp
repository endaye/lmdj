// The Web Runtime resource-limit journey. It generates three real WAVs at
// the artifact and decoded-frame boundaries, which was 44% of the original
// binary's cost by itself, so it carries its own budget.

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
      std::nullopt,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
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

void test_web_runtime_limits_keep_oversized_projects_inspectable_and_prior_bank() {
  TempDirectory temp;
  Application application(config(temp.path()));

  auto prior = PreparedSampleBank::empty(ProjectId{std::string(kProjectId)}, 9);
  const std::array<float, 2> prior_pcm{0.5F, 0.5F};
  LMDJ_CHECK(prior.set_sample(0, prior_pcm).has_value());
  RealtimeEngine engine;
  LMDJ_CHECK(engine.publish_sample_bank(std::move(prior)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  const auto check_prior = [&engine]() {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{99, 0, 127}) ==
               EnqueueResult::accepted);
    std::array<float, 2> left{};
    std::array<float, 2> right{};
    engine.render(left.data(), right.data(), 2);
    // F6 ramp: attack 0/96 on the first frame, then attack 1/96 times the
    // boundary fade 1/96 on the second frame of the 2-frame sample.
    constexpr float kRampScale =
        1.0F / static_cast<float>(lmdj::audio::kRealtimeRampFrames);
    const auto second_frame =
        0.5F * ((1.0F * kRampScale) * (1.0F * kRampScale));
    LMDJ_CHECK(left.at(0) == 0.0F);
    LMDJ_CHECK(left.at(1) == second_frame);
    LMDJ_CHECK(right == left);
  };
  const auto check_limit = [&check_prior](
                               const auto& rejected,
                               std::string_view resource,
                               std::uint64_t observed,
                               std::uint64_t limit) {
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::cook_failed);
    LMDJ_CHECK(rejected.error().details.at("resource") == resource);
    LMDJ_CHECK(rejected.error().details.at("observed") == observed);
    LMDJ_CHECK(rejected.error().details.at("limit") == limit);
    check_prior();
  };
  const auto check_quota = [&check_prior](
                               const auto& rejected,
                               ErrorCode code,
                               std::uint64_t requested,
                               std::uint64_t remaining) {
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == code);
    LMDJ_CHECK(rejected.error().details.at("requested_bytes") == requested);
    if (code == ErrorCode::bank_quota_exhausted) {
      LMDJ_CHECK(rejected.error().details.at("remaining_bytes") == remaining);
    } else {
      LMDJ_CHECK(
          rejected.error().details.at("project_remaining_bytes") ==
          remaining);
    }
    check_prior();
  };

  constexpr std::uint32_t kArtifactBoundaryFrames =
      (1'048'576U - 44U) / 2U;
  auto artifact_boundary = mono_pcm16_wav(kArtifactBoundaryFrames);
  LMDJ_CHECK(artifact_boundary.size() == 1'048'576);
  const auto artifact_project = temp.path() / "artifact-boundary.lmdj";
  const auto artifact_pattern = uuid(403);
  create_single_asset_project(
      application,
      artifact_project,
      artifact_boundary,
      400,
      uuid(404),
      artifact_pattern);
  const RuntimePreparationLimits artifact_limits{
      1'048'576,
      static_cast<std::uint64_t>(kArtifactBoundaryFrames) * sizeof(float),
      static_cast<std::uint64_t>(kArtifactBoundaryFrames) * sizeof(float),
      static_cast<std::uint64_t>(kArtifactBoundaryFrames) * sizeof(float),
  };
  const auto exact_artifact = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{
          artifact_project,
          PatternId{artifact_pattern},
          artifact_limits,
      });
  LMDJ_CHECK(exact_artifact.has_value());

  artifact_boundary.push_back(std::byte{0});
  LMDJ_CHECK(artifact_boundary.size() == 1'048'577);
  const auto oversized_project = temp.path() / "artifact-oversized.lmdj";
  const auto oversized_pattern = uuid(413);
  create_single_asset_project(
      application,
      oversized_project,
      artifact_boundary,
      410,
      uuid(414),
      oversized_pattern);
  const auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", oversized_project.generic_string()},
      });
  check_success(inspected, 3);
  LMDJ_CHECK(
      inspected.at("result")
              .at("project")
              .at("assets")
              .at(uuid(414))
              .at("artifact")
              .at("byte_length") == 1'048'577);
  check_limit(
      application.prepare_runtime_snapshot(
          RuntimeSnapshotRequest{
              oversized_project,
              PatternId{oversized_pattern},
              artifact_limits,
          }),
      "artifact_bytes",
      1'048'577,
      1'048'576);

  auto decoded_boundary = mono_pcm16_wav(240'000);
  const auto decoded_project = temp.path() / "decoded-boundary.lmdj";
  const auto decoded_pattern = uuid(423);
  create_single_asset_project(
      application,
      decoded_project,
      decoded_boundary,
      420,
      uuid(424),
      decoded_pattern);
  const RuntimePreparationLimits decoded_limits{
      1'048'576,
      960'004,
      960'004,
      0,
  };
  const auto exact_decoded = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{
          decoded_project,
          PatternId{decoded_pattern},
          decoded_limits,
      });
  LMDJ_CHECK(exact_decoded.has_value());

  const auto decoded_plus_one = mono_pcm16_wav(240'001);
  const auto decoded_oversized_project =
      temp.path() / "decoded-oversized.lmdj";
  const auto decoded_oversized_pattern = uuid(433);
  create_single_asset_project(
      application,
      decoded_oversized_project,
      decoded_plus_one,
      430,
      uuid(434),
      decoded_oversized_pattern);
  check_success(
      application.query(
          {
              {"operation", "project.inspect"},
              {"project_path", decoded_oversized_project.generic_string()},
          }),
      3);
  const auto no_per_pad_cap = application.prepare_runtime_snapshot(
      RuntimeSnapshotRequest{
          decoded_oversized_project,
          PatternId{decoded_oversized_pattern},
          decoded_limits,
      });
  LMDJ_CHECK(no_per_pad_cap.has_value());

  check_quota(
      application.prepare_runtime_snapshot(
          RuntimeSnapshotRequest{
              decoded_project,
              PatternId{decoded_pattern},
              RuntimePreparationLimits{
                  1'048'576,
                  959'999,
                  960'000,
                  0,
              },
          }),
      ErrorCode::bank_quota_exhausted,
      960'000,
      959'999);
  check_quota(
      application.prepare_runtime_snapshot(
          RuntimeSnapshotRequest{
              decoded_project,
              PatternId{decoded_pattern},
              RuntimePreparationLimits{
                  1'048'576,
                  960'000,
                  959'999,
                  0,
              },
          }),
      ErrorCode::project_quota_exhausted,
      960'000,
      959'999);

  const auto resident_is_not_a_generation_quota =
      application.prepare_runtime_snapshot(
          RuntimeSnapshotRequest{
              decoded_project,
              PatternId{decoded_pattern},
              RuntimePreparationLimits{
                  1'048'576,
                  960'000,
                  960'000,
                  0,
              },
          });
  LMDJ_CHECK(resident_is_not_a_generation_quota.has_value());
}

}  // namespace

int main() {
  try {
    test_web_runtime_limits_keep_oversized_projects_inspectable_and_prior_bank();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "application facade web runtime limit tests: PASS\n";
  return 0;
}
