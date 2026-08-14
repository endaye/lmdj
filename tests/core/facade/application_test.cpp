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
using lmdj::domain::RawTakeEvent;
using lmdj::domain::TriggerMode;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::TakeId;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kKickAssetId =
    "00000000-0000-4000-8000-000000000101";
constexpr std::string_view kSnareAssetId =
    "00000000-0000-4000-8000-000000000102";
constexpr std::string_view kTakeId =
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
           {"version", "1.4.0"},
           {"api_version", 2},
           {"dependencies",
            {
                {"foundation", "0.2.0"},
                {"authoring-domain", "0.2.0"},
                {"project-io", "0.6.0"},
                {"project-cooker", "0.3.0"},
                {"audio-runtime", "0.5.0"},
                {"provider-sdk", "1.1.1"},
            }},
       }));
  LMDJ_CHECK(project_io.at("module") == "project-io");
  LMDJ_CHECK(project_io.at("version") == "0.6.0");
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
  check_success(application.command(create_request(project)), 0);
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

  const TakeId take_id{uuid(command_base + 2U)};
  check_success(
      application.command(
          {
              {"operation", "take.begin"},
              {"project_path", project.generic_string()},
              {"take_id", take_id.value()},
              {"expected_revision", 2},
              {"sample_rate", 48000},
          }),
      2);
  const std::array events{
      RawTakeEvent{PadSlotId{0, 0}, 0, 127},
  };
  LMDJ_CHECK(
      application.append_realtime_take_events(project, take_id, events)
          .has_value());
  check_success(
      application.command(
          {
              {"operation", "take.commit"},
              {"project_path", project.generic_string()},
              {"command_id", uuid(command_base + 3U)},
              {"expected_revision", 2},
              {"take_id", take_id.value()},
              {"pattern",
               {
                   {"pattern_id", pattern_id},
                   {"bars", 1},
                   {"events",
                    nlohmann::json::array(
                        {{{"slot", slot(0, 0)},
                          {"step", 0},
                          {"velocity", 127}}})},
               }},
          }),
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
              {{PadSlotId{0, 0}, 0, 127}},
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
              {{PadSlotId{0, 0}, 0, 127}},
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

nlohmann::json pattern_json() {
  return {
      {"pattern_id", kPatternId},
      {"bars", 1},
      {"events",
       nlohmann::json::array(
           {
               {{"slot", slot(0, 0)}, {"step", 0}, {"velocity", 127}},
               {{"slot", slot(0, 1)}, {"step", 4}, {"velocity", 127}},
               {{"slot", slot(0, 0)}, {"step", 8}, {"velocity", 127}},
               {{"slot", slot(0, 1)}, {"step", 12}, {"velocity", 127}},
           })},
  };
}

void create_golden_project(
    Application& application,
    const std::filesystem::path& project) {
  auto response = application.command(create_request(project));
  check_success(response, 0);

  response = application.command(import_request(
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
      {
          {"operation", "take.begin"},
          {"project_path", project.generic_string()},
          {"take_id", kTakeId},
          {"expected_revision", 4},
          {"sample_rate", 48000},
      });
  check_success(response, 4);
  for (const auto& [pad, frame] :
       std::vector<std::pair<std::uint32_t, std::uint64_t>>{
           {0, 0},
           {1, 24'000},
           {0, 48'000},
           {1, 72'000},
       }) {
    response = application.command(
        {
            {"operation", "take.append"},
            {"project_path", project.generic_string()},
            {"take_id", kTakeId},
            {"event",
             {
                 {"slot", slot(0, pad)},
                 {"frame_offset", frame},
                 {"velocity", 127},
             }},
        });
    check_success(response, 4);
  }

  response = application.command(
      {
          {"operation", "take.commit"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(5)},
          {"expected_revision", 4},
          {"take_id", kTakeId},
          {"pattern", pattern_json()},
      });
  check_success(response, 5);
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
          "takes",
          "patterns",
      });
  LMDJ_CHECK(projected.at("contract") == "lmdj.project.v1");
  LMDJ_CHECK(projected.at("revision") == 5);
  LMDJ_CHECK(
      projected.at("takes").at(kTakeId).at("events").size() == 4);

  response = application.query(
      {
          {"operation", "take.recoverable.list"},
          {"project_path", project.generic_string()},
      });
  check_success(response, 5);
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

void test_typed_realtime_host_api_prepares_and_persists_take_batches() {
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

  const auto capture_project = temp.path() / "typed-capture.lmdj";
  check_success(
      application.command(create_request(capture_project)), 0);
  const TakeId capture_take{uuid(202)};
  check_success(
      application.command(
          {
              {"operation", "take.begin"},
              {"project_path", capture_project.generic_string()},
              {"take_id", capture_take.value()},
              {"expected_revision", 0},
              {"sample_rate", 48000},
          }),
      0);
  const std::vector<RawTakeEvent> events{
      RawTakeEvent{PadSlotId{0, 0}, 0, 127},
      RawTakeEvent{PadSlotId{1, 2}, 128, 96},
      RawTakeEvent{PadSlotId{3, 15}, 256, 64},
  };

  const auto appended = application.append_realtime_take_events(
      capture_project, capture_take, events);

  LMDJ_CHECK(appended.has_value());
  const auto committed = application.command(
      {
          {"operation", "take.commit"},
          {"project_path", capture_project.generic_string()},
          {"command_id", uuid(203)},
          {"expected_revision", 0},
          {"take_id", capture_take.value()},
          {"pattern",
           {
               {"pattern_id", uuid(204)},
               {"bars", 1},
               {"events",
                nlohmann::json::array(
                    {
                        {{"slot", slot(0, 0)},
                         {"step", 0},
                         {"velocity", 127}},
                        {{"slot", slot(1, 2)},
                         {"step", 1},
                         {"velocity", 96}},
                        {{"slot", slot(3, 15)},
                         {"step", 2},
                         {"velocity", 64}},
                    })},
           }},
      });
  check_success(committed, 1);
  const auto captured = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", capture_project.generic_string()},
      });
  check_success(captured, 1);
  const auto& persisted = captured.at("result")
                              .at("project")
                              .at("takes")
                              .at(capture_take.value())
                              .at("events");
  LMDJ_CHECK(persisted.size() == events.size());
  LMDJ_CHECK(persisted.at(0).at("frame_offset") == 0);
  LMDJ_CHECK(persisted.at(1).at("frame_offset") == 128);
  LMDJ_CHECK(persisted.at(2).at("frame_offset") == 256);

  const auto recovery_project = temp.path() / "typed-recovery.lmdj";
  check_success(application.command(create_request(recovery_project)), 0);
  const TakeId recovery_take{uuid(205)};
  check_success(
      application.command(
          {
              {"operation", "take.begin"},
              {"project_path", recovery_project.generic_string()},
              {"take_id", recovery_take.value()},
              {"expected_revision", 0},
              {"sample_rate", 48000},
          }),
      0);
  LMDJ_CHECK(
      application.append_realtime_take_events(
                     recovery_project,
                     recovery_take,
                     std::span<const RawTakeEvent>{events}.first(1))
          .has_value());
  const auto invalid_reason = application.seal_realtime_take(
      recovery_project, recovery_take, "revision_conflict");
  LMDJ_CHECK(!invalid_reason.has_value());
  LMDJ_CHECK(
      invalid_reason.error().code ==
      lmdj::foundation::ErrorCode::invalid_argument);
  const auto sealed = application.seal_realtime_take(
      recovery_project, recovery_take, "capture_incomplete");
  LMDJ_CHECK(sealed.has_value());
  const auto candidates = application.query(
      {
          {"operation", "take.recoverable.list"},
          {"project_path", recovery_project.generic_string()},
      });
  check_success(candidates, 0);
  LMDJ_CHECK(candidates.at("result").at("candidates").size() == 1);
  LMDJ_CHECK(
      candidates.at("result")
              .at("candidates")
              .at(0)
              .at("reason") == "capture_incomplete");
  LMDJ_CHECK(
      candidates.at("result")
              .at("candidates")
              .at(0)
              .at("events")
              .size() == 1);
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
              {{PadSlotId{0, 0}, 0, 0}},
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

    const auto invalid_append = application.append_realtime_take_events(
        project,
        TakeId{"not-a-uuid"},
        std::span<const RawTakeEvent>{});
    LMDJ_CHECK(!invalid_append.has_value());
    LMDJ_CHECK(invalid_append.error().code == ErrorCode::invalid_argument);

    check_success(
        application.command(
            {
                {"operation", "take.begin"},
                {"project_path", project.generic_string()},
                {"take_id", uuid(302)},
                {"expected_revision", 1},
                {"sample_rate", 48000},
            }),
        1);

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

void test_web_runtime_limits_keep_oversized_projects_inspectable_and_prior_bank() {
  TempDirectory temp;
  Application application(config(temp.path()));

  auto prior = PreparedSampleBank::empty(ProjectId{std::string(kProjectId)}, 9);
  const std::array<float, 1> prior_pcm{0.5F};
  LMDJ_CHECK(prior.set_sample(0, prior_pcm).has_value());
  RealtimeEngine engine;
  LMDJ_CHECK(engine.publish_sample_bank(std::move(prior)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  const auto check_prior = [&engine]() {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{99, 0, 127}) ==
               EnqueueResult::accepted);
    std::array<float, 1> left{};
    std::array<float, 1> right{};
    engine.render(left.data(), right.data(), 1);
    LMDJ_CHECK(left.at(0) == 0.5F);
    LMDJ_CHECK(right.at(0) == 0.5F);
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
      kArtifactBoundaryFrames,
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
      240'000,
      960'000,
      960'000,
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
  check_limit(
      application.prepare_runtime_snapshot(
          RuntimeSnapshotRequest{
              decoded_oversized_project,
              PatternId{decoded_oversized_pattern},
              decoded_limits,
          }),
      "decoded_frames_per_pad",
      240'001,
      240'000);

  check_limit(
      application.prepare_runtime_snapshot(
          RuntimeSnapshotRequest{
              decoded_project,
              PatternId{decoded_pattern},
              RuntimePreparationLimits{
                  1'048'576,
                  240'000,
                  959'999,
                  960'000,
              },
          }),
      "prepared_bank_bytes",
      960'000,
      959'999);
  check_limit(
      application.prepare_runtime_snapshot(
          RuntimeSnapshotRequest{
              decoded_project,
              PatternId{decoded_pattern},
              RuntimePreparationLimits{
                  1'048'576,
                  240'000,
                  960'000,
                  959'999,
              },
          }),
      "live_bank_bytes",
      960'000,
      959'999);
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

void test_take_commit_uses_captured_revision_and_replays_after_cleanup() {
  TempDirectory temp;
  const auto project = temp.path() / "captured-revision.lmdj";
  Application application(config(temp.path()));
  check_success(application.command(create_request(project)), 0);
  check_success(
      application.command(import_request(
          project,
          41,
          kKickAssetId,
          std::filesystem::absolute("tests/fixtures/audio/kick.wav"),
          0)),
      1);
  check_success(
      application.command(
          assign_request(project, 42, 0, kKickAssetId, 1)),
      2);

  check_success(
      application.command(
          {
              {"operation", "take.begin"},
              {"project_path", project.generic_string()},
              {"take_id", kTakeId},
              {"expected_revision", 2},
              {"sample_rate", 48000},
          }),
      2);
  check_success(
      application.command(
          {
              {"operation", "take.append"},
              {"project_path", project.generic_string()},
              {"take_id", kTakeId},
              {"event",
               {
                   {"slot", slot(0, 0)},
                   {"frame_offset", 0},
                   {"velocity", 127},
               }},
          }),
      2);
  check_success(
      application.command(
          assign_request(project, 43, 1, kKickAssetId, 2)),
      3);

  const auto conflicted = application.command(
      {
          {"operation", "take.commit"},
          {"project_path", project.generic_string()},
          {"command_id", uuid(44)},
          {"expected_revision", 3},
          {"take_id", kTakeId},
          {"pattern",
           {
               {"pattern_id", kPatternId},
               {"bars", 1},
               {"events",
                nlohmann::json::array(
                    {{{"slot", slot(0, 0)},
                      {"step", 0},
                      {"velocity", 127}}})},
           }},
      });
  check_error(conflicted, "REVISION_CONFLICT");
  auto inspected = application.query(
      {
          {"operation", "project.inspect"},
          {"project_path", project.generic_string()},
      });
  check_success(inspected, 3);
  LMDJ_CHECK(inspected.at("result").at("project").at("takes").empty());
  const auto recoverable = application.query(
      {
          {"operation", "take.recoverable.list"},
          {"project_path", project.generic_string()},
      });
  check_success(recoverable, 3);
  LMDJ_CHECK(recoverable.at("result").at("candidates").size() == 1);
  LMDJ_CHECK(
      recoverable.at("result")
          .at("candidates")
          .at(0)
          .at("expected_revision") == 2);

  const auto replay_project = temp.path() / "replay.lmdj";
  create_golden_project(application, replay_project);
  const auto replay_request = nlohmann::json{
      {"operation", "take.commit"},
      {"project_path", replay_project.generic_string()},
      {"command_id", uuid(5)},
      {"expected_revision", 4},
      {"take_id", kTakeId},
      {"pattern", pattern_json()},
  };
  auto replayed = application.command(replay_request);
  check_success(replayed, 5);
  LMDJ_CHECK(replayed.at("result").at("committed_revision") == 5);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);

  check_success(
      application.command(
          assign_request(replay_project, 45, 2, kKickAssetId, 5)),
      6);
  Application fresh(config(temp.path()));
  replayed = fresh.command(replay_request);
  check_success(replayed, 6);
  LMDJ_CHECK(replayed.at("result").at("committed_revision") == 5);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);

  auto cross_operation = replay_request;
  cross_operation["command_id"] = uuid(3);
  cross_operation["expected_revision"] = 2;
  check_error(
      fresh.command(cross_operation), "INVALID_ARGUMENT");

  auto changed_revision = replay_request;
  changed_revision["expected_revision"] = 5;
  check_error(
      fresh.command(changed_revision), "INVALID_ARGUMENT");

  auto changed_take = replay_request;
  changed_take["take_id"] = uuid(299);
  check_error(fresh.command(changed_take), "INVALID_ARGUMENT");

  auto changed_pattern_id = replay_request;
  changed_pattern_id["pattern"]["pattern_id"] = uuid(99);
  check_error(
      fresh.command(changed_pattern_id), "INVALID_ARGUMENT");

  auto changed_pattern_bars = replay_request;
  changed_pattern_bars["pattern"]["bars"] = 2;
  check_error(
      fresh.command(changed_pattern_bars), "INVALID_ARGUMENT");

  auto changed_pattern_event = replay_request;
  changed_pattern_event["pattern"]["events"][0]["velocity"] = 126;
  check_error(
      fresh.command(changed_pattern_event), "INVALID_ARGUMENT");

  replayed = fresh.command(replay_request);
  check_success(replayed, 6);
  LMDJ_CHECK(replayed.at("result").at("take_id") == kTakeId);
  LMDJ_CHECK(replayed.at("result").at("pattern_id") == kPatternId);
  LMDJ_CHECK(replayed.at("result").at("committed_revision") == 5);
  LMDJ_CHECK(replayed.at("result").at("replayed") == true);
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
      "take.begin",
      "take.append",
      "take.commit",
      "render.offline",
      "provider.select",
      "provider.run",
  };
  const std::vector<std::string> queries{
      "project.inspect",
      "take.recoverable.list",
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
          {"operation", "take.begin"},
          {"project_path", project.generic_string()},
          {"take_id", kTakeId},
          {"expected_revision", 1},
          {"sample_rate", 48000},
      });
  check_error(stale_begin, "REVISION_CONFLICT");
  LMDJ_CHECK(!std::filesystem::exists(
      project / "recovery/active" /
      (std::string(kTakeId) + ".jsonl")));
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
    test_render_rejects_symlinked_parent_and_never_reuses_crash_residue();
    test_render_recooks_after_restart_and_publishes_golden_atomically();
    test_typed_realtime_host_api_prepares_and_persists_take_batches();
    test_typed_initial_project_creation_persists_one_pattern_at_revision_zero();
    test_byte_import_and_opaque_writer_lease_share_one_storage_platform();
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
    test_web_runtime_limits_keep_oversized_projects_inspectable_and_prior_bank();
    test_take_commit_uses_captured_revision_and_replays_after_cleanup();
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
