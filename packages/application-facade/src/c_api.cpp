#include <lmdj/facade/c_api.h>

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>
#include <lmdj/facade/assembly_loader.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>

#if defined(LMDJ_C_API_TESTING)
#include "testing_hooks.hpp"
#endif

struct lmdj_engine {
  std::uint64_t sequence;
};

#if defined(LMDJ_C_API_TESTING)
namespace lmdj::facade::testing {
namespace {

std::atomic<InvokeGate*> active_invoke_gate{nullptr};

}  // namespace

void set_invoke_gate(InvokeGate* gate) noexcept {
  active_invoke_gate.store(gate, std::memory_order_release);
}

void block_invoke_if_selected(lmdj_engine* engine) noexcept {
  auto* gate = active_invoke_gate.load(std::memory_order_acquire);
  if (gate == nullptr || gate->engine != engine) {
    return;
  }
  gate->entered.store(true, std::memory_order_release);
  gate->entered.notify_all();
  gate->release.wait(false, std::memory_order_acquire);
}

}  // namespace lmdj::facade::testing
#endif

namespace {

constexpr std::size_t kMaximumConfigBytes = 64U * 1024U;
constexpr std::size_t kMaximumRequestBytes = 16U * 1024U * 1024U;

struct EngineState {
  explicit EngineState(std::shared_ptr<lmdj::facade::Application> value)
      : application(std::move(value)) {}

  std::mutex serial;
  std::shared_ptr<lmdj::facade::Application> application;
};

std::mutex engines_mutex;
std::unordered_map<lmdj_engine*, std::shared_ptr<EngineState>> live_engines;
std::vector<std::unique_ptr<lmdj_engine>> tombstone_shells;
std::uint64_t engine_sequence = 0;

std::optional<std::string_view> bounded_c_string(
    const char* value,
    std::size_t maximum) {
  if (value == nullptr) {
    return std::nullopt;
  }
  const auto length = ::strnlen(value, maximum + 1U);
  if (length > maximum) {
    return std::nullopt;
  }
  return std::string_view(value, length);
}

nlohmann::json internal_error_envelope() {
  return {
      {"ok", false},
      {"error",
       {
           {"code", "INTERNAL_ERROR"},
           {"message", "unexpected C ABI failure"},
           {"details", nlohmann::json::object()},
       }},
  };
}

int copy_string(const std::string& value, char** output) {
  auto* allocation =
      static_cast<char*>(std::malloc(value.size() + 1U));
  if (allocation == nullptr) {
    return LMDJ_STATUS_ALLOCATION_FAILURE;
  }
  std::memcpy(allocation, value.data(), value.size());
  allocation[value.size()] = '\0';
  *output = allocation;
  return LMDJ_STATUS_OK;
}

struct EngineGuard {
  std::shared_ptr<EngineState> state;
  std::unique_lock<std::mutex> serial;
};

std::optional<EngineGuard> acquire_engine(lmdj_engine* engine) {
  std::shared_ptr<EngineState> state;
  {
    std::lock_guard registry_lock(engines_mutex);
    const auto found = live_engines.find(engine);
    if (found == live_engines.end()) {
      return std::nullopt;
    }
    state = found->second;
  }
  std::unique_lock serial_lock(state->serial);
  if (!state->application) {
    return std::nullopt;
  }
  return EngineGuard{
      std::move(state),
      std::move(serial_lock),
  };
}

template <typename Invoke>
int invoke_application(
    lmdj_engine* engine,
    const char* request_json,
    char** out_response_json,
    Invoke invoke) noexcept {
  if (out_response_json != nullptr) {
    *out_response_json = nullptr;
  }
  if (engine == nullptr || request_json == nullptr ||
      out_response_json == nullptr) {
    return LMDJ_STATUS_INVALID_ARGUMENT;
  }
  try {
    auto guard = acquire_engine(engine);
    if (!guard.has_value()) {
      return LMDJ_STATUS_INVALID_HANDLE;
    }
#if defined(LMDJ_C_API_TESTING)
    lmdj::facade::testing::block_invoke_if_selected(engine);
#endif
    const auto bytes =
        bounded_c_string(request_json, kMaximumRequestBytes);
    if (!bytes.has_value() || !lmdj::foundation::valid_utf8(*bytes)) {
      return LMDJ_STATUS_INVALID_ARGUMENT;
    }
    auto request = lmdj::foundation::parse_bounded_json(*bytes);
    if (!request.has_value() || !request->is_object()) {
      return LMDJ_STATUS_INVALID_ARGUMENT;
    }
    nlohmann::json response;
    try {
      response = invoke(*guard->state->application, *request);
    } catch (...) {
      response = internal_error_envelope();
    }
    return copy_string(response.dump(), out_response_json);
  } catch (const std::bad_alloc&) {
    return LMDJ_STATUS_ALLOCATION_FAILURE;
  } catch (...) {
    try {
      return copy_string(
          internal_error_envelope().dump(), out_response_json);
    } catch (...) {
      return LMDJ_STATUS_ALLOCATION_FAILURE;
    }
  }
}

}  // namespace

extern "C" {

int lmdj_engine_create(
    const char* config_json,
    lmdj_engine** out_engine,
    char** out_error_json) {
  if (out_engine != nullptr) {
    *out_engine = nullptr;
  }
  if (out_error_json != nullptr) {
    *out_error_json = nullptr;
  }
  if (config_json == nullptr || out_engine == nullptr ||
      out_error_json == nullptr) {
    return LMDJ_STATUS_INVALID_ARGUMENT;
  }
  try {
    const auto bytes =
        bounded_c_string(config_json, kMaximumConfigBytes);
    if (!bytes.has_value() || !lmdj::foundation::valid_utf8(*bytes)) {
      return LMDJ_STATUS_INVALID_ARGUMENT;
    }
    auto config = lmdj::foundation::parse_bounded_json(*bytes);
    if (!config.has_value() || !config->is_object() ||
        config->empty() || config->size() > 2 ||
        !config->contains("workspace_root") ||
        !config->at("workspace_root").is_string() ||
        (config->size() == 2 && !config->contains("assembly_path")) ||
        (config->contains("assembly_path") &&
         !config->at("assembly_path").is_string())) {
      return LMDJ_STATUS_INVALID_ARGUMENT;
    }
    const auto workspace_value =
        config->at("workspace_root").get<std::string>();
    if (!lmdj::foundation::valid_utf8(workspace_value) ||
        workspace_value.find('\0') != std::string::npos) {
      return LMDJ_STATUS_INVALID_ARGUMENT;
    }
    const auto workspace_root =
        std::filesystem::path(workspace_value);
    if (!workspace_root.is_absolute() ||
        workspace_root.lexically_normal() != workspace_root) {
      return LMDJ_STATUS_INVALID_ARGUMENT;
    }
    auto providers = std::make_shared<lmdj::provider::Registry>();
    lmdj::provider::ProviderPolicy provider_policy;
    if (config->contains("assembly_path")) {
      const auto assembly_value =
          config->at("assembly_path").get<std::string>();
      if (!lmdj::foundation::valid_utf8(assembly_value) ||
          assembly_value.find('\0') != std::string::npos) {
        return LMDJ_STATUS_INVALID_ARGUMENT;
      }
      const auto assembly_path =
          std::filesystem::path(assembly_value);
      if (!assembly_path.is_absolute() ||
          assembly_path.lexically_normal() != assembly_path) {
        return LMDJ_STATUS_INVALID_ARGUMENT;
      }
      auto loaded =
          lmdj::facade::load_installed_assembly(assembly_path);
      if (!loaded.has_value()) {
        return LMDJ_STATUS_INVALID_ARGUMENT;
      }
      providers = std::move(loaded.value().providers);
      provider_policy = std::move(loaded.value().provider_policy);
    }
    auto application = std::make_shared<lmdj::facade::Application>(
        lmdj::facade::ApplicationConfig{
            workspace_root,
            std::move(providers),
            std::move(provider_policy),
            {},
        });
    auto state = std::make_shared<EngineState>(std::move(application));
    auto shell = std::make_unique<lmdj_engine>();
    std::lock_guard lock(engines_mutex);
    shell->sequence = ++engine_sequence;
    auto* handle = shell.get();
    tombstone_shells.push_back(std::move(shell));
    live_engines.emplace(handle, std::move(state));
    *out_engine = handle;
    return LMDJ_STATUS_OK;
  } catch (const std::bad_alloc&) {
    return LMDJ_STATUS_ALLOCATION_FAILURE;
  } catch (...) {
    try {
      return copy_string(
          internal_error_envelope().dump(), out_error_json);
    } catch (...) {
      return LMDJ_STATUS_ALLOCATION_FAILURE;
    }
  }
}

int lmdj_engine_command(
    lmdj_engine* engine,
    const char* request_json,
    char** out_response_json) {
  return invoke_application(
      engine,
      request_json,
      out_response_json,
      [](lmdj::facade::Application& application,
         const nlohmann::json& request) {
        return application.command(request);
      });
}

int lmdj_engine_query(
    lmdj_engine* engine,
    const char* request_json,
    char** out_response_json) {
  return invoke_application(
      engine,
      request_json,
      out_response_json,
      [](lmdj::facade::Application& application,
         const nlohmann::json& request) {
        return application.query(request);
      });
}

void lmdj_string_free(char* value) {
  std::free(value);
}

void lmdj_engine_free(lmdj_engine* engine) {
  if (engine == nullptr) {
    return;
  }
  try {
    std::shared_ptr<EngineState> state;
    {
      std::lock_guard registry_lock(engines_mutex);
      const auto found = live_engines.find(engine);
      if (found == live_engines.end()) {
        return;
      }
      state = found->second;
      live_engines.erase(found);
    }
    std::unique_lock serial_lock(state->serial);
    state->application.reset();
  } catch (...) {
  }
}

}  // extern "C"
