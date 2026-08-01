#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <string>
#include <string_view>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/provider.hpp>
#include <lmdj/provider/registry.hpp>
#include <lmdj/providers/local_proof_failure/factory.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::AttemptId;
using lmdj::foundation::ErrorCode;
using lmdj::provider::AttemptStore;
using lmdj::provider::CapabilityRequest;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-attempt-isolation-test-" + std::to_string(nonce));
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

void write_bytes(const std::filesystem::path& path, std::string_view bytes) {
  std::filesystem::create_directories(path.parent_path());
  std::ofstream stream(path, std::ios::binary);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  if (!stream) {
    throw std::runtime_error("failed to write test fixture");
  }
}

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("failed to read test file");
  }
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

std::map<std::string, std::string> snapshot(
    const std::filesystem::path& root) {
  std::map<std::string, std::string> files;
  for (const auto& entry :
       std::filesystem::recursive_directory_iterator(root)) {
    if (entry.is_regular_file()) {
      files.emplace(
          std::filesystem::relative(entry.path(), root).generic_string(),
          read_bytes(entry.path()));
    }
  }
  return files;
}

std::size_t regular_file_count(const std::filesystem::path& root) {
  std::size_t count = 0;
  for (const auto& entry :
       std::filesystem::recursive_directory_iterator(root)) {
    if (entry.is_regular_file()) {
      ++count;
    }
  }
  return count;
}

void test_failing_provider_cannot_mutate_project_truth() {
  TempDirectory temp;
  const auto project = temp.path() / "beat-proof.lmdj";
  const auto workspace_root = temp.path() / "host-workspace";
  write_bytes(
      project / "manifest.json",
      "{\"contract\":\"lmdj.project.v1\",\"head_revision\":7}\n");
  write_bytes(project / "assets/immutable.wav", "immutable audio bytes");
  write_bytes(
      project / "history/checkpoints/7.json",
      "{\"project_id\":\"project-proof\",\"revision\":7}\n");
  write_bytes(
      project / "history/transactions/7-command.json",
      "{\"command_id\":\"command-proof\"}\n");

  const auto before_files = snapshot(project);
  const auto before_revision =
      nlohmann::json::parse(read_bytes(project / "manifest.json"))
          .at("head_revision")
          .get<std::uint64_t>();

  Registry registry;
  LMDJ_CHECK(
      registry
          .add(lmdj::providers::local_proof_failure_registration())
          .has_value());
  AttemptStore store(
      workspace_root,
      ProviderPolicy{{"local"}, {"public"}, {"proof.execute"}},
      [] { return std::string("2026-07-30T12:00:00.000Z"); });
  LMDJ_CHECK(
      store
          .set_provider_selection(
              "proof.candidate.v2", "local.proof.failure", registry)
          .has_value());
  const auto workspace = workspace_root / ".lmdj-workspace";
  const auto before_workspace_file_count = regular_file_count(workspace);

  const auto executed = store.execute(
      AttemptId{"attempt-isolation"},
      CapabilityRequest{
          "proof.candidate.v2",
          {},
          nlohmann::json::object(),
          "public",
          "test",
          "local",
          {"proof.execute"},
      },
      registry);
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().error.has_value());
  LMDJ_CHECK(executed.value().error->code == ErrorCode::provider_failed);

  const auto after_files = snapshot(project);
  const auto after_revision =
      nlohmann::json::parse(read_bytes(project / "manifest.json"))
          .at("head_revision")
          .get<std::uint64_t>();
  LMDJ_CHECK(after_files == before_files);
  LMDJ_CHECK(after_revision == before_revision);
  LMDJ_CHECK(
      regular_file_count(workspace) == before_workspace_file_count + 1);

  const auto attempt_path = workspace / "attempts/attempt-isolation.json";
  LMDJ_CHECK(std::filesystem::is_regular_file(attempt_path));
  const auto attempt_bytes = read_bytes(attempt_path);
  const auto attempt = nlohmann::json::parse(attempt_bytes);
  LMDJ_CHECK(
      attempt_bytes == lmdj::foundation::canonical_json(attempt) + "\n");
  LMDJ_CHECK(attempt.at("status") == "failed");
  LMDJ_CHECK(
      attempt_bytes.find(project.generic_string()) == std::string::npos);
  LMDJ_CHECK(attempt_bytes.find(".lmdj") == std::string::npos);
}

}  // namespace

int main() {
  try {
    test_failing_provider_cannot_mutate_project_truth();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "provider attempt isolation tests: PASS\n";
  return 0;
}
