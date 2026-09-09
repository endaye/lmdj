#include <functional>
#pragma once
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <span>
#include <string>
#include <vector>

#include <lmdj/facade/application.hpp>
#include <lmdj/facade/assembly_loader.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include "tests/core/support/test.hpp"

namespace {
using Json = nlohmann::json;
using namespace lmdj::foundation;
using namespace lmdj::project_io;
constexpr auto project_id = "00000000-0000-4000-8000-000000000001";
constexpr auto asset_id = "00000000-0000-4000-8000-000000000002";
constexpr auto other_id = "00000000-0000-4000-8000-000000000099";

inline std::string read(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  LMDJ_CHECK(file.good());
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
inline void write(const std::filesystem::path& path, const std::string& bytes) {
  std::ofstream file(path, std::ios::binary);
  file.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  LMDJ_CHECK(file.good());
}
inline void little(std::string& out, std::uint32_t value, unsigned width) {
  for (unsigned i = 0; i < width; ++i) out.push_back(static_cast<char>((value >> (8 * i)) & 255));
}
inline std::string wav() {
  const std::vector<int> samples{0, 5000, 0, 8000, 0};
  std::string out = "RIFF";
  little(out, 36 + samples.size() * 2, 4); out += "WAVEfmt ";
  little(out, 16, 4); little(out, 1, 2); little(out, 1, 2);
  little(out, 48000, 4); little(out, 96000, 4); little(out, 2, 2); little(out, 16, 2);
  out += "data"; little(out, samples.size() * 2, 4);
  for (int value : samples) little(out, static_cast<std::uint16_t>(value), 2);
  return out;
}
inline void ok(const Json& response) {
  if (!response.at("ok").get<bool>()) throw std::runtime_error(response.dump());
}
inline void error(const Json& response, std::string_view code) {
  if (response.at("ok") != false) throw std::runtime_error("expected " + std::string(code) + ", got " + response.dump());
  if (response.at("error").at("code") != code) throw std::runtime_error("expected " + std::string(code) + ", got " + response.dump());
}

// Observe actual owner I/O without replacing the native storage behavior.
class ObservedStorage final : public ProjectStoragePlatform {
 public:
  std::shared_ptr<ProjectStoragePlatform> inner = make_default_project_storage_platform();
  std::filesystem::path owner;
  std::size_t owner_leases = 0;
  mutable std::size_t owner_reads = 0;
  std::size_t writes = 0;
  std::function<void(const std::filesystem::path&, bool)> replace_hook;
  std::function<void(const std::filesystem::path&)> acquire_hook;
  std::function<bool(const std::filesystem::path&)> fail_replace;
  std::function<bool(const std::filesystem::path&)> fail_create;
  std::function<void(const std::filesystem::path&)> read_hook;
  Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override {
    if (p == owner) ++owner_leases;
    if (acquire_hook) acquire_hook(p);
    return inner->acquire_writer(p);
  }
  Result<void> ensure_directory(const std::filesystem::path& p) override { ++writes; return inner->ensure_directory(p); }
  Result<bool> exists(const std::filesystem::path& p) const override { return inner->exists(p); }
  Result<bool> directory_exists(const std::filesystem::path& p) const override { return inner->directory_exists(p); }
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override { return inner->byte_length(p); }
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override {
    if (read_hook) read_hook(p);
    if (p.generic_string().starts_with(owner.generic_string() + "/")) ++owner_reads;
    return inner->read_complete(p);
  }
  Result<void> create_immutable(const std::filesystem::path& p, std::span<const std::byte> b) override {
    ++writes;
    if (fail_create && fail_create(p)) return Result<void>::failure(Error{ErrorCode::io_error, "injected immutable write failure"});
    return inner->create_immutable(p, b);
  }
  Result<void> replace_complete(const std::filesystem::path& p, std::span<const std::byte> b) override {
    ++writes;
    if (fail_replace && fail_replace(p)) return Result<void>::failure(Error{ErrorCode::io_error, "injected replacement failure"});
    if (replace_hook) replace_hook(p, false);
    auto result = inner->replace_complete(p, b);
    if (result.has_value() && replace_hook) replace_hook(p, true);
    return result;
  }
  Result<void> append_durable(const std::filesystem::path& p, std::uint64_t n, std::span<const std::byte> b) override { ++writes; return inner->append_durable(p, n, b); }
  Result<void> remove(const std::filesystem::path& p) override { ++writes; return inner->remove(p); }
  Result<void> remove_tree(const std::filesystem::path& p) override { ++writes; return inner->remove_tree(p); }
  Result<void> publish_directory_if_absent(const std::filesystem::path& a, const std::filesystem::path& b) override { ++writes; return inner->publish_directory_if_absent(a, b); }
  Result<std::vector<std::string>> list_names(const std::filesystem::path& p) const override { return inner->list_names(p); }
  Result<std::vector<std::string>> list_directories(const std::filesystem::path& p) const override { return inner->list_directories(p); }
  Result<void> validate_managed_tree(const std::filesystem::path& p) const override { return inner->validate_managed_tree(p); }
};

struct Fixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-facade-owner-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path project = root / "source.lmdj";
  std::shared_ptr<ObservedStorage> storage = std::make_shared<ObservedStorage>();
  std::unique_ptr<lmdj::facade::Application> app;
  Json source;
  std::optional<lmdj::audio::RuntimePreparationLimits> limits;
  explicit Fixture(const std::string& audio = wav()) {
    std::filesystem::create_directories(root);
    storage->owner = project;
    restart();
    ok(app->command({{"operation", "project.create"}, {"project_path", project.generic_string()},
                     {"project_id", project_id}, {"bpm", 120}}));
    const auto& bytes = audio;
    const auto imported = app->import_artifact_bytes({project,
        {CommandId{"00000000-0000-4000-8000-000000000003"}, 0}, AssetId{asset_id}, "audio/wav",
        std::as_bytes(std::span{bytes.data(), bytes.size()})});
    LMDJ_CHECK(imported.has_value());
    const auto inspected = app->query({{"operation", "project.inspect"}, {"project_path", project.generic_string()}});
    ok(inspected);
    source = inspected.at("result").at("project").at("assets").at(asset_id).at("artifact");
    select();
  }
  ~Fixture() { app.reset(); std::error_code e; std::filesystem::remove_all(root, e); }
  void restart() {
    app.reset();
    const auto loaded = lmdj::facade::load_installed_assembly(std::filesystem::absolute("products/lmdj/assembly.json"));
    LMDJ_CHECK(loaded.has_value());
    lmdj::facade::ApplicationConfig config{};
    config.workspace_root = root;
    config.providers = loaded.value().providers;
    config.provider_policy = loaded.value().provider_policy;
    config.storage_platform = storage;
    config.runtime_preparation_limits = limits;
    config.performance_replay_controller = lmdj::facade::make_unavailable_performance_replay_controller();
    app = std::make_unique<lmdj::facade::Application>(std::move(config));
  }
  void select() { ok(app->command({{"operation", "provider.select"}, {"capability", "sample.slice.v1"}, {"provider_id", "local.sample.slice"}})); }
  void grant() { ok(app->command({{"operation", "provider.permissions.configure"}, {"granted_permissions", Json::array({"sample.slice.execute"})}})); }
  Json request(std::string id = "owned") const {
    return {{"operation", "provider.run"}, {"attempt_id", id}, {"capability", "sample.slice.v1"},
            {"inputs", Json::array({{{"port", "source_audio"}, {"artifact", source}}})},
            {"input_owners", Json::array({{{"port", "source_audio"}, {"occurrence", 0},
                {"project_path", project.generic_string()}, {"project_id", project_id}, {"asset_id", asset_id}}})},
            {"parameters", {{"refractory_frames", 1}}}, {"data_classification", "public"},
            {"platform", "test"}, {"region", "local"}, {"required_permissions", Json::array({"sample.slice.execute"})}};
  }
  Json inspect(std::string id = "owned") const {
    const auto response = app->query({{"operation", "attempt.inspect"}, {"attempt_id", id}});
    ok(response); return response.at("result");
  }
  auto snapshot() const {
    std::map<std::string, std::string> files;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(project)) {
      if (entry.is_regular_file()) files.emplace(entry.path().generic_string(), read(entry.path()));
    }
    return files;
  }
  auto blob() const { return project / "assets" / (source.at("sha256").get<std::string>() + ".wav"); }
};

inline Json job_request(const Fixture& f, std::string attempt = "first") {
  return {{"operation", "candidate.job.run"}, {"job_id", "slice"}, {"attempt_id", attempt},
      {"project_path", f.project.generic_string()}, {"project_id", project_id}, {"asset_id", asset_id},
      {"expected_revision", 1}, {"parameters", {{"refractory_frames", 1}}},
      {"data_classification", "public"}, {"platform", "test"}, {"region", "local"},
      {"required_permissions", Json::array({"sample.slice.execute"})}};
}
inline Json job(Fixture& f) {
  const auto response = f.app->query({{"operation", "candidate.job.inspect"}, {"job_id", "slice"}});
  ok(response); return response.at("result");
}

} // namespace
