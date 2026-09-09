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
#include <lmdj/providers/local_sample_slice/validation.hpp>
#include "tests/core/support/test.hpp"

namespace {
using Json = nlohmann::json;
using namespace lmdj::foundation;
using namespace lmdj::project_io;
constexpr auto project_id = "00000000-0000-4000-8000-000000000001";
constexpr auto asset_id = "00000000-0000-4000-8000-000000000002";
constexpr auto other_id = "00000000-0000-4000-8000-000000000099";

std::string read(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  LMDJ_CHECK(file.good());
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
void write(const std::filesystem::path& path, const std::string& bytes) {
  std::ofstream file(path, std::ios::binary);
  file.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  LMDJ_CHECK(file.good());
}
void little(std::string& out, std::uint32_t value, unsigned width) {
  for (unsigned i = 0; i < width; ++i) out.push_back(static_cast<char>((value >> (8 * i)) & 255));
}
std::string wav() {
  const std::vector<int> samples{0, 5000, 0, 8000, 0};
  std::string out = "RIFF";
  little(out, 36 + samples.size() * 2, 4); out += "WAVEfmt ";
  little(out, 16, 4); little(out, 1, 2); little(out, 1, 2);
  little(out, 48000, 4); little(out, 96000, 4); little(out, 2, 2); little(out, 16, 2);
  out += "data"; little(out, samples.size() * 2, 4);
  for (int value : samples) little(out, static_cast<std::uint16_t>(value), 2);
  return out;
}
void ok(const Json& response) {
  if (!response.at("ok").get<bool>()) throw std::runtime_error(response.dump());
}
void error(const Json& response, std::string_view code) {
  if (response.at("ok") != false) throw std::runtime_error("expected " + std::string(code) + ", got " + response.dump());
  LMDJ_CHECK(response.at("error").at("code") == code);
}

// Observe actual owner I/O without replacing the native storage behavior.
class ObservedStorage final : public ProjectStoragePlatform {
 public:
  std::shared_ptr<ProjectStoragePlatform> inner = make_default_project_storage_platform();
  std::filesystem::path owner;
  std::size_t owner_leases = 0;
  mutable std::size_t owner_reads = 0;
  std::size_t writes = 0;
  Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override {
    if (p == owner) ++owner_leases;
    return inner->acquire_writer(p);
  }
  Result<void> ensure_directory(const std::filesystem::path& p) override { ++writes; return inner->ensure_directory(p); }
  Result<bool> exists(const std::filesystem::path& p) const override { return inner->exists(p); }
  Result<bool> directory_exists(const std::filesystem::path& p) const override { return inner->directory_exists(p); }
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override { return inner->byte_length(p); }
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override {
    if (p.generic_string().starts_with(owner.generic_string() + "/")) ++owner_reads;
    return inner->read_complete(p);
  }
  Result<void> create_immutable(const std::filesystem::path& p, std::span<const std::byte> b) override { ++writes; return inner->create_immutable(p, b); }
  Result<void> replace_complete(const std::filesystem::path& p, std::span<const std::byte> b) override { ++writes; return inner->replace_complete(p, b); }
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
  Fixture() {
    std::filesystem::create_directories(root);
    storage->owner = project;
    restart();
    ok(app->command({{"operation", "project.create"}, {"project_path", project.generic_string()},
                     {"project_id", project_id}, {"bpm", 120}}));
    const auto bytes = wav();
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

void success_and_restart() {
  Fixture f; f.grant();
  const auto before = f.snapshot();
  const auto result = f.app->command(f.request()); ok(result);
  LMDJ_CHECK(f.snapshot() == before);
  const auto terminal = f.inspect();
  LMDJ_CHECK(terminal.at("status") == "succeeded");
  LMDJ_CHECK(terminal.at("request").at("inputs") == f.request().at("inputs"));
  LMDJ_CHECK(terminal.dump().find(f.project.generic_string()) == std::string::npos);
  LMDJ_CHECK(terminal.at("candidate_outputs") == result.at("result").at("outputs"));
  const auto& outputs = terminal.at("candidate_outputs");
  LMDJ_CHECK(outputs.size() == 1 && outputs[0].at("port") == "slice_points");
  const auto output = outputs[0].at("artifact").get<ArtifactRef>();
  const auto path = f.root / ".lmdj-workspace/attempts/owned/artifacts" / output.sha256;
  LMDJ_CHECK(describe_artifact(path, "application/json").value() == output);
  const auto encoded = read(path);
  LMDJ_CHECK(encoded == canonical_json({{"contract", "lmdj.slice-points.v1"},
      {"source_sha256", f.source.at("sha256")}, {"frame_rate", 48000},
      {"points", Json::array({{{"frame", 1}}, {{"frame", 3}}})}}));
  LMDJ_CHECK(lmdj::providers::sample_slice::validate_slice_points(
      std::as_bytes(std::span{encoded.data(), encoded.size()}), f.source.get<ArtifactRef>(), 48000, 5).has_value());
  // Reconfiguration must retain both selection and already published Attempts.
  f.grant(); LMDJ_CHECK(f.inspect() == terminal);
  ok(f.app->command(f.request("second")));
  f.restart(); LMDJ_CHECK(f.inspect() == terminal); LMDJ_CHECK(f.snapshot() == before);
  error(f.app->command(f.request("after-restart")), "PERMISSION_DENIED");
  LMDJ_CHECK(f.inspect("after-restart").at("status") == "failed");
}

void execution_refusal(std::string_view mode) {
  Fixture f;
  auto request = f.request();
  if (mode != "permission") f.grant();
  std::string code = "NOT_FOUND", reason = "input_artifact_unavailable";
  bool no_read = false;
  std::unique_ptr<ProjectWriterLease> lease;
  if (mode == "permission") { code = "PERMISSION_DENIED"; reason.clear(); no_read = true; }
  if (mode == "missing-owner") { request.erase("input_owners"); no_read = true; }
  if (mode == "project") request["input_owners"][0]["project_id"] = other_id;
  if (mode == "asset") request["input_owners"][0]["asset_id"] = other_id;
  if (mode == "reference") request["inputs"][0]["artifact"]["sha256"] = std::string(64, 'a');
  if (mode == "missing-file") std::filesystem::remove(f.blob());
  if (mode == "hash" || mode == "length") {
    auto bytes = read(f.blob()); if (mode == "hash") bytes.back() ^= 1; else bytes.push_back('x');
    write(f.blob(), bytes); code = "IO_ERROR"; reason = "input_artifact_mismatch";
  }
  if (mode == "busy") {
    auto holder = make_default_project_storage_platform();
    auto acquired = holder->acquire_writer(f.project); LMDJ_CHECK(acquired.has_value());
    lease = std::move(acquired.value());
  }
  if (mode == "budget") {
    request["inputs"][0]["artifact"]["byte_length"] = 16777217;
    code = "INVALID_ARGUMENT"; reason = "input_artifact_too_large"; no_read = true;
  }
  if (mode == "binding") {
    request["inputs"][0]["port"] = "other"; request["input_owners"][0]["port"] = "other";
    code = "INVALID_ARGUMENT"; reason = "input_binding_invalid"; no_read = true;
  }
  const auto before = f.snapshot();
  f.storage->owner_leases = 0; f.storage->owner_reads = 0;
  const auto writes = f.storage->writes;
  const auto response = f.app->command(request);
  if (response.at("ok") != false) throw std::runtime_error("refusal " + std::string(mode) + ": " + response.dump());
  error(response, code);
  if (!reason.empty()) LMDJ_CHECK(response.at("error").at("details").at("reason") == reason);
  LMDJ_CHECK(response.dump().find(f.project.generic_string()) == std::string::npos);
  LMDJ_CHECK(f.storage->writes == writes);
  if (no_read) LMDJ_CHECK(f.storage->owner_leases == 0 && f.storage->owner_reads == 0);
  LMDJ_CHECK(f.snapshot() == before);
  const auto terminal = f.inspect();
  LMDJ_CHECK(terminal.at("status") == "failed");
  LMDJ_CHECK(terminal.at("minted_outputs").empty() && terminal.at("candidate_outputs").empty());
  lease.reset(); f.restart(); LMDJ_CHECK(f.inspect() == terminal); LMDJ_CHECK(f.snapshot() == before);
}

void malformed_owner(unsigned mode) {
  Fixture f; f.grant(); auto request = f.request();
  auto& owner = request["input_owners"][0];
  if (mode == 0) owner["occurrence"] = 1;
  if (mode == 1) owner["port"] = "unbound";
  if (mode == 2) owner["extra"] = true;
  if (mode == 3) owner["project_id"] = "invalid";
  if (mode == 4) owner["project_path"] = "relative.lmdj";
  if (mode == 5) request["input_owners"] = Json::array();
  if (mode == 6) request["input_owners"].push_back(owner);
  f.storage->owner_leases = 0; f.storage->owner_reads = 0;
  const auto before = f.snapshot();
  error(f.app->command(request), "INVALID_ARGUMENT");
  LMDJ_CHECK(f.storage->owner_leases == 0 && f.storage->owner_reads == 0);
  LMDJ_CHECK(f.snapshot() == before);
  f.restart();
  error(f.app->query({{"operation", "attempt.inspect"}, {"attempt_id", "owned"}}), "NOT_FOUND");
}

void permission_shape(unsigned mode) {
  Fixture f; f.grant();
  Json request{{"operation", "provider.permissions.configure"}, {"granted_permissions", Json::array()}};
  if (mode == 0) request["granted_permissions"] = {"unknown.permission"};
  if (mode == 1) request["granted_permissions"] = {"sample.slice.execute", "sample.slice.execute"};
  if (mode == 2) request["extra"] = true;
  if (mode == 3) request["granted_permissions"] = 42;
  error(f.app->command(request), "INVALID_ARGUMENT");
  ok(f.app->command(f.request())); // invalid configuration is atomic
}
void explicit_revocation() {
  Fixture f; f.grant();
  ok(f.app->command({{"operation", "provider.permissions.configure"}, {"granted_permissions", Json::array()}}));
  error(f.app->command(f.request()), "PERMISSION_DENIED");
}
}  // namespace
int main() {
  try {
    success_and_restart();
    for (auto mode : {"permission", "missing-owner", "project", "asset", "reference", "missing-file", "hash", "length", "busy", "budget", "binding"}) execution_refusal(mode);
    for (unsigned mode = 0; mode < 7; ++mode) malformed_owner(mode);
    for (unsigned mode = 0; mode < 4; ++mode) permission_shape(mode);
    explicit_revocation();
    std::cout << "facade owner resolution: PASS\n";
  } catch (const std::exception& failure) { std::cerr << failure.what() << '\n'; return 1; }
}
