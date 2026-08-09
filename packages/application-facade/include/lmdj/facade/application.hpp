#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::facade {

struct ApplicationConfig {
  std::filesystem::path workspace_root;
  std::shared_ptr<provider::Registry> providers;
  provider::ProviderPolicy provider_policy;
  provider::TimestampSource timestamp_source;
};

struct RuntimeSnapshotRequest {
  std::filesystem::path project_path;
  foundation::PatternId pattern_id;
  std::optional<audio::RuntimePreparationLimits> limits = std::nullopt;
};

struct InitialProjectRequest {
  std::filesystem::path project_path;
  foundation::ProjectId project_id;
  std::uint16_t bpm;
  domain::Pattern initial_pattern;
};

class RuntimeProjectWriterLease final {
 public:
  ~RuntimeProjectWriterLease();
  RuntimeProjectWriterLease(RuntimeProjectWriterLease&&) noexcept;
  RuntimeProjectWriterLease& operator=(
      RuntimeProjectWriterLease&&) noexcept;

  RuntimeProjectWriterLease(const RuntimeProjectWriterLease&) = delete;
  RuntimeProjectWriterLease& operator=(
      const RuntimeProjectWriterLease&) = delete;

 private:
  struct Impl;
  explicit RuntimeProjectWriterLease(std::unique_ptr<Impl> impl);

  std::unique_ptr<Impl> impl_;
  friend class Application;
};

struct ArtifactBytesImportRequest {
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  foundation::AssetId asset_id;
  std::string media_type;
  std::span<const std::byte> bytes;
};

struct ProjectBundleImportBeginRequest {
  std::string import_token;
  std::uint64_t index_bytes;
  std::string index_sha256;
};

struct LocalProjectSummary {
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t revision;
  std::uint16_t bpm;
  std::size_t asset_count;
  std::size_t assigned_pad_count;
  std::string bundle_digest;
  friend bool operator==(const LocalProjectSummary&, const LocalProjectSummary&) =
      default;
};

struct ProjectBundleImportSession {
  std::string token;
  std::uint64_t expected_index_bytes;
};

struct ProjectBundleImportIdentity {
  foundation::ProjectId project_id;
  std::string bundle_digest;
  std::uint32_t entry_count;
};

class Application {
 public:
  explicit Application(ApplicationConfig config);
  ~Application();

  Application(const Application&) = delete;
  Application& operator=(const Application&) = delete;
  Application(Application&&) noexcept;
  Application& operator=(Application&&) noexcept;

  nlohmann::json command(const nlohmann::json& request);
  nlohmann::json query(const nlohmann::json& request) const;
  foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
  prepare_runtime_snapshot(const RuntimeSnapshotRequest& request);
  foundation::Result<RuntimeProjectWriterLease> acquire_project_writer(
      const std::filesystem::path& project_path);
  foundation::Result<domain::ProjectState> create_initial_project(
      const InitialProjectRequest& request);
  foundation::Result<domain::AppliedCommand> import_artifact_bytes(
      const ArtifactBytesImportRequest& request);
  foundation::Result<std::vector<LocalProjectSummary>> list_local_projects();
  foundation::Result<ProjectBundleImportSession>
  begin_project_bundle_import(
      const ProjectBundleImportBeginRequest& request);
  foundation::Result<std::optional<ProjectBundleImportIdentity>>
  append_project_bundle_index(
      std::string_view token,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<void> append_project_bundle_entry(
      std::string_view token,
      std::uint32_t entry_index,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<LocalProjectSummary> commit_project_bundle_import(
      std::string_view token);
  foundation::Result<void> abort_project_bundle_import(
      std::string_view token);
  foundation::Result<void> append_realtime_take_events(
      const std::filesystem::path& project_path,
      foundation::TakeId take_id,
      std::span<const domain::RawTakeEvent> events);
  foundation::Result<std::filesystem::path> seal_realtime_take(
      const std::filesystem::path& project_path,
      foundation::TakeId take_id,
      std::string_view reason);

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::facade
