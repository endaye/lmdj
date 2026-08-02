#pragma once

#include <filesystem>
#include <memory>
#include <span>
#include <string_view>

#include <nlohmann/json.hpp>

#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/domain/project.hpp>
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
