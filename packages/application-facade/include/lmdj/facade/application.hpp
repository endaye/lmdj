#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>

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
