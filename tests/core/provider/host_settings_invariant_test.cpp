// Runtime invariant harness for Workspace Host settings.
//
// Track 3 Task 2 of docs/superpowers/plans/2026-08-19-lmdj-runtime-invariant-harness.md.
//
// read_host_settings already re-checks byte-identity on every read, so a
// single successful read proves nothing new. What only a sequence can show is
// whether a *completed* mutation left a state the next read would reject, and
// whether the lock that serialized it survived. Those are the relations here.

#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>
#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::ErrorCode;
using lmdj::provider::AttemptStore;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;

constexpr std::string_view kCapability = "proof.candidate.v2";

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-host-settings-invariant-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  TempDirectory(const TempDirectory&) = delete;
  TempDirectory& operator=(const TempDirectory&) = delete;

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

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

// Deliberately absent: a check that every recorded capability and provider id
// is filesystem-safe. The exclusion rule strikes it -- ids are validated
// against the Registry before the write and by read_host_settings' own
// valid_file_id on every read, so restating the rule here would add no
// coverage and would drift from the production definition, which is internal
// to the SDK and cannot be reused.

// ---------------------------------------------------------------------------
// The harness
// ---------------------------------------------------------------------------

std::vector<std::string> host_settings_violations(
    const std::filesystem::path& workspace_root) {
  std::vector<std::string> violations;
  const auto workspace = workspace_root / ".lmdj-workspace";
  const auto settings_path = workspace / "host-settings.json";
  const auto lock_path = workspace / ".host-settings.lock";

  // Relation 1: the lock never survives a completed operation. A lock left
  // behind blocks every later write with "host settings are busy", and no
  // staleness, owner, or timeout recovery exists -- see finding F3.
  if (std::filesystem::exists(lock_path)) {
    violations.push_back("the host settings lock survived the sequence");
  }

  if (!std::filesystem::exists(settings_path)) {
    return violations;
  }

  const auto status = std::filesystem::symlink_status(settings_path);
  if (std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    violations.push_back("host settings is not a regular file");
    return violations;
  }

  const auto bytes = read_bytes(settings_path);
  nlohmann::json settings;
  try {
    settings = nlohmann::json::parse(bytes);
  } catch (const nlohmann::json::exception&) {
    violations.push_back("host settings is not valid JSON");
    return violations;
  }

  // Relation 2: the file is byte-identical to its canonical form with a
  // trailing newline. This is exactly what the next read enforces, so a
  // violation means a completed write produced an unreadable state.
  if (bytes != lmdj::foundation::canonical_json(settings) + "\n") {
    violations.push_back("host settings is not canonical on disk");
  }

  // Relation 3: the shape is exactly the two expected keys, and it declares
  // the private format rather than a Contract id.
  if (settings.size() != 2 || !settings.contains("format") ||
      !settings.contains("provider_selections")) {
    violations.push_back("host settings does not have exactly the two keys");
    return violations;
  }
  if (settings.at("format") != "provider-selections") {
    violations.push_back("host settings declares an unexpected format");
  }
  if (settings.contains("contract")) {
    violations.push_back("host settings must not carry a contract id");
  }
  if (!settings.at("provider_selections").is_object()) {
    violations.push_back("provider selections is not an object");
    return violations;
  }

  // Relation 4: no temporary sibling of the settings file survives.
  for (const auto& entry : std::filesystem::directory_iterator(workspace)) {
    const auto name = entry.path().filename().string();
    if (name.starts_with(".host-settings.json.tmp.")) {
      violations.push_back("a settings temporary sibling survived: " + name);
    }
  }

  return violations;
}

void check_settings_hold(const std::filesystem::path& workspace_root) {
  const auto violations = host_settings_violations(workspace_root);
  for (const auto& violation : violations) {
    std::cerr << "host settings violation: " << violation << '\n';
  }
  LMDJ_CHECK(violations.empty());
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

Registry proof_registry() {
  Registry registry;
  LMDJ_CHECK(
      registry.add(lmdj::providers::local_proof_success_registration())
          .has_value());
  LMDJ_CHECK(
      registry.add(lmdj::providers::local_proof_failure_registration())
          .has_value());
  return registry;
}

AttemptStore store_at(const std::filesystem::path& workspace_root) {
  return AttemptStore(
      workspace_root,
      ProviderPolicy{{"local"}, {"public"}, {"proof.execute"}},
      [] { return std::string("2026-08-19T12:00:00.000Z"); });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// A single selection leaves a readable, canonical file and no lock.
void test_selection_leaves_canonical_settings_and_no_lock() {
  const TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());

  LMDJ_CHECK(store
                 .set_provider_selection(
                     std::string(kCapability), "local.proof.success", registry)
                 .has_value());

  check_settings_hold(temp.path());

  const auto selected = store.selected_provider(std::string(kCapability));
  LMDJ_CHECK(selected.has_value());
  LMDJ_CHECK(selected.value() == "local.proof.success");
}

// Overwriting a selection is a read-modify-write. Only a sequence can show
// that the second write left the file readable rather than merging badly.
void test_repeated_selection_stays_canonical_and_readable() {
  const TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());

  for (const auto* provider :
       {"local.proof.success", "local.proof.failure", "local.proof.success"}) {
    LMDJ_CHECK(store
                   .set_provider_selection(
                       std::string(kCapability), provider, registry)
                   .has_value());
    check_settings_hold(temp.path());
  }

  const auto selected = store.selected_provider(std::string(kCapability));
  LMDJ_CHECK(selected.has_value());
  LMDJ_CHECK(selected.value() == "local.proof.success");
}

// A rejected selection must not leave a lock behind, and must not damage the
// selection already recorded. Failure paths are where locks leak.
void test_rejected_selection_leaves_no_lock_and_no_damage() {
  const TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());

  LMDJ_CHECK(store
                 .set_provider_selection(
                     std::string(kCapability), "local.proof.success", registry)
                 .has_value());

  // An unregistered provider is refused against the Registry.
  const auto refused = store.set_provider_selection(
      std::string(kCapability), "local.proof.absent", registry);
  LMDJ_CHECK(!refused.has_value());

  check_settings_hold(temp.path());

  const auto selected = store.selected_provider(std::string(kCapability));
  LMDJ_CHECK(selected.has_value());
  LMDJ_CHECK(selected.value() == "local.proof.success");
}

// The harness must detect real violations, or its passing cases prove nothing.
void test_harness_detects_each_corruption() {
  const auto prepare = [](const TempDirectory& temp) {
    const auto registry = proof_registry();
    auto store = store_at(temp.path());
    LMDJ_CHECK(store
                   .set_provider_selection(
                       std::string(kCapability), "local.proof.success",
                       registry)
                   .has_value());
    return temp.path() / ".lmdj-workspace";
  };

  // Pretty-printed settings are no longer byte-identical to canonical form.
  {
    const TempDirectory temp;
    const auto workspace = prepare(temp);
    const auto path = workspace / "host-settings.json";
    const auto decoded = nlohmann::json::parse(read_bytes(path));
    std::ofstream(path, std::ios::binary | std::ios::trunc)
        << decoded.dump(2) << "\n";
    LMDJ_CHECK(!host_settings_violations(temp.path()).empty());
  }

  // A missing trailing newline is equally fatal to the next read.
  {
    const TempDirectory temp;
    const auto workspace = prepare(temp);
    const auto path = workspace / "host-settings.json";
    const auto bytes = read_bytes(path);
    std::ofstream(path, std::ios::binary | std::ios::trunc)
        << bytes.substr(0, bytes.size() - 1);
    LMDJ_CHECK(!host_settings_violations(temp.path()).empty());
  }

  // A third key breaks the exact shape.
  {
    const TempDirectory temp;
    const auto workspace = prepare(temp);
    const auto path = workspace / "host-settings.json";
    auto decoded = nlohmann::json::parse(read_bytes(path));
    decoded["contract"] = "lmdj.host-settings.v1";
    std::ofstream(path, std::ios::binary | std::ios::trunc)
        << lmdj::foundation::canonical_json(decoded) << "\n";
    LMDJ_CHECK(!host_settings_violations(temp.path()).empty());
  }

  // A surviving temporary sibling means a write sequence did not finish.
  {
    const TempDirectory temp;
    const auto workspace = prepare(temp);
    std::ofstream(workspace / ".host-settings.json.tmp.1.1") << "x";
    LMDJ_CHECK(!host_settings_violations(temp.path()).empty());
  }
}

// Finding F3, pinned as an observable fact.
//
// The lock is a bare create_directory with no pid, owner, or timestamp. A
// process killed while holding it leaves the directory behind, and every
// later write fails forever with "host settings are busy". This test asserts
// the *current* behaviour so the defect cannot be lost; fixing F3 has to come
// here and change the second assertion deliberately.
void test_orphaned_lock_is_detected_and_blocks_every_write() {
  const TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());

  LMDJ_CHECK(store
                 .set_provider_selection(
                     std::string(kCapability), "local.proof.success", registry)
                 .has_value());

  // Simulate a process killed while holding the lock.
  const auto lock_path =
      temp.path() / ".lmdj-workspace/.host-settings.lock";
  std::filesystem::create_directory(lock_path);

  // The harness sees it.
  const auto violations = host_settings_violations(temp.path());
  LMDJ_CHECK(violations.size() == 1);
  LMDJ_CHECK(violations.front() == "the host settings lock survived the sequence");

  // And no write can ever succeed again: there is no staleness recovery.
  const auto blocked = store.set_provider_selection(
      std::string(kCapability), "local.proof.failure", registry);
  LMDJ_CHECK(!blocked.has_value());
  LMDJ_CHECK(blocked.error().code == ErrorCode::io_error);

  // Reads still work, so the failure is write-only and silent to a reader.
  const auto selected = store.selected_provider(std::string(kCapability));
  LMDJ_CHECK(selected.has_value());
  LMDJ_CHECK(selected.value() == "local.proof.success");
}

}  // namespace

int main() {
  try {
    test_selection_leaves_canonical_settings_and_no_lock();
    test_repeated_selection_stays_canonical_and_readable();
    test_rejected_selection_leaves_no_lock_and_no_damage();
    test_harness_detects_each_corruption();
    test_orphaned_lock_is_detected_and_blocks_every_write();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "host settings invariant tests: PASS\n";
  return 0;
}
