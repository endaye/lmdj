#pragma once

#include <filesystem>
#include <memory>

#include <nlohmann/json.hpp>

#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::facade {

struct ApplicationConfig {
  std::filesystem::path workspace_root;
  std::shared_ptr<provider::Registry> providers;
  provider::ProviderPolicy provider_policy;
  provider::TimestampSource timestamp_source;
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

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::facade
