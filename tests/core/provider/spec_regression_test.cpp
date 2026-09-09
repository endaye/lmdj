#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>
#include <lmdj/provider/registry.hpp>
#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>

#include "tests/core/support/test.hpp"
#include "tests/core/provider/byte_fixture.hpp"

#ifndef LMDJ_SUCCESS_SOURCE_PACKAGE_MANIFEST
#error "success Provider source-package manifest path is required"
#endif

#ifndef LMDJ_FAILURE_SOURCE_PACKAGE_MANIFEST
#error "failure Provider source-package manifest path is required"
#endif

namespace {

using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AttemptId;
using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::provider::ArtifactPortDescriptor;
using lmdj::provider::ArtifactBinding;
using lmdj::provider::AttemptResult;
using lmdj::provider::AttemptStatus;
using lmdj::provider::AttemptStore;
using lmdj::provider::CapabilityDescriptor;
using lmdj::provider::CapabilityPolicy;
using lmdj::provider::CapabilityRequest;
using lmdj::provider::Determinism;
using lmdj::provider::ExecutionPolicy;
using lmdj::provider::Provider;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::ProviderRegistration;
using lmdj::provider::Registry;
using lmdj::provider::ResourceClass;
using lmdj::provider::ResourceRequirements;

constexpr std::string_view kCapability = "proof.candidate.v2";
constexpr std::string_view kSuccessProviderShaPath =
    LMDJ_SUCCESS_SOURCE_PACKAGE_MANIFEST;
constexpr std::string_view kFailureProviderShaPath =
    LMDJ_FAILURE_SOURCE_PACKAGE_MANIFEST;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-provider-spec-test-" + std::to_string(nonce));
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

void write_bytes(
    const std::filesystem::path& path,
    std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  if (!stream) {
    throw std::runtime_error("failed to write test file");
  }
}

nlohmann::json read_json(const std::filesystem::path& path) {
  return nlohmann::json::parse(read_bytes(path));
}

std::set<std::string> object_keys(const nlohmann::json& object) {
  std::set<std::string> keys;
  for (auto iterator = object.begin(); iterator != object.end(); ++iterator) {
    keys.insert(iterator.key());
  }
  return keys;
}

std::set<std::string> string_set(const nlohmann::json& array) {
  std::set<std::string> values;
  for (const auto& value : array) {
    values.insert(value.get<std::string>());
  }
  return values;
}

CapabilityDescriptor proof_capability() {
  return CapabilityDescriptor{
      std::string(kCapability),
      "2.0.0",
      {
          ArtifactPortDescriptor{
              "inputs",
              {"*/*"},
              "lmdj.artifact.input.v1",
              "1.0.0",
              false,
              64,
          },
      },
      {
          ArtifactPortDescriptor{
              "candidate",
              {"application/x-lmdj-proof"},
              "lmdj.artifact.proof.v1",
              "1.0.0",
              true,
              1,
          },
      },
      Determinism::deterministic,
      {},
      {"PROVIDER_FAILED"},
      ResourceRequirements{ResourceClass::light, 16},
      ExecutionPolicy{1000, 1},
      CapabilityPolicy{{"public"}, {"local"}, {"proof.execute"}},
      {"test"},
      0,
  };
}

CapabilityDescriptor named_proof_capability(std::string id) {
  auto capability = proof_capability();
  capability.id = std::move(id);
  return capability;
}

ProviderPolicy proof_policy() {
  return ProviderPolicy{
      {"local"},
      {"public"},
      {"proof.execute"},
  };
}

CapabilityRequest proof_request() {
  return CapabilityRequest{
      std::string(kCapability),
      {},
      {
          {"reasoning", "parameter-reasoning-sentinel"},
          {"secret", "parameter-secret-sentinel"},
          {"seed", 7},
      },
      "public",
      "test",
      "local",
      {"proof.execute"},
  };
}

AttemptStore store_at(const std::filesystem::path& root) {
  return AttemptStore(
      root,
      proof_policy(),
      [] { return std::string("2026-07-30T12:00:00.000Z"); });
}

Registry proof_registry() {
  Registry registry;
  LMDJ_CHECK(
      registry
          .add(lmdj::providers::local_proof_success_registration())
          .has_value());
  LMDJ_CHECK(
      registry
          .add(lmdj::providers::local_proof_failure_registration())
          .has_value());
  return registry;
}

void assert_workspace_has_no(
    const std::filesystem::path& root,
    std::string_view sentinel) {
  for (const auto& entry :
       std::filesystem::recursive_directory_iterator(root)) {
    if (entry.is_regular_file()) {
      LMDJ_CHECK(read_bytes(entry.path()).find(sentinel) ==
                 std::string::npos);
    }
  }
}

void test_capability_discovery_matches_public_schema_shape() {
  const auto registry = proof_registry();
  const auto providers = registry.list();
  LMDJ_CHECK(providers.size() == 2);
  const auto& descriptor = providers.front().capabilities.front();
  const auto encoded =
      lmdj::provider::capability_contract_json(descriptor);
  const auto schema =
      read_json("contracts/capability/lmdj.capability.v2.schema.json");

  LMDJ_CHECK(object_keys(encoded) == string_set(schema.at("required")));
  LMDJ_CHECK(encoded.size() == schema.at("properties").size());
  LMDJ_CHECK(encoded.at("contract") == "lmdj.capability.v2");
  LMDJ_CHECK(encoded.at("capability_id") == kCapability);
  LMDJ_CHECK(encoded.at("contract_version") == "2.0.0");
  LMDJ_CHECK(encoded.at("determinism") == "deterministic");
  LMDJ_CHECK(encoded.at("progress_events").empty());
  LMDJ_CHECK(
      (encoded.at("resources") ==
       nlohmann::json{{"class", "light"}, {"memory_mib", 16}}));
  LMDJ_CHECK(
      (encoded.at("execution") ==
       nlohmann::json{{"max_attempts", 1}, {"timeout_ms", 1000}}));
  LMDJ_CHECK(
      (encoded.at("policy") ==
       nlohmann::json{
           {"data_classifications", {"public"}},
           {"regions", {"local"}},
           {"required_permissions", {"proof.execute"}},
       }));

  const auto& port = encoded.at("output_artifacts").front();
  const auto& port_schema = schema.at("$defs").at("artifact_port");
  LMDJ_CHECK(object_keys(port) == string_set(port_schema.at("required")));
  LMDJ_CHECK(port.size() == port_schema.at("properties").size());
  LMDJ_CHECK(port.at("schema_id") == "lmdj.artifact.proof.v1");
  LMDJ_CHECK(port.at("schema_version") == "1.0.0");
  LMDJ_CHECK(port.at("required") == true);
  LMDJ_CHECK(
      lmdj::foundation::canonical_json(encoded) ==
      lmdj::provider::canonical_capability_json(descriptor));
  LMDJ_CHECK(!encoded.contains("platforms"));
  LMDJ_CHECK(!encoded.contains("max_output_bytes"));
}

void test_capability_contract_encodes_supported_execution_traits() {
  struct TraitCase {
    Determinism determinism;
    ResourceClass resource_class;
    std::string_view expected_determinism;
    std::string_view expected_resource_class;
  };

  constexpr std::array cases{
      TraitCase{
          Determinism::seeded,
          ResourceClass::cpu,
          "seeded",
          "cpu",
      },
      TraitCase{
          Determinism::nondeterministic,
          ResourceClass::gpu,
          "nondeterministic",
          "gpu",
      },
      TraitCase{
          Determinism::seeded,
          ResourceClass::remote,
          "seeded",
          "remote",
      },
  };

  for (const auto& test_case : cases) {
    auto capability = proof_capability();
    capability.determinism = test_case.determinism;
    capability.resources =
        ResourceRequirements{test_case.resource_class, std::nullopt};

    const auto encoded =
        lmdj::provider::capability_contract_json(capability);

    LMDJ_CHECK(
        encoded.at("determinism") ==
        test_case.expected_determinism);
    LMDJ_CHECK((
        encoded.at("resources") ==
        nlohmann::json{
            {"class", test_case.expected_resource_class}}));
    LMDJ_CHECK(
        !encoded.at("resources").contains("memory_mib"));
  }
}

void verify_source_package(
    const std::filesystem::path& manifest_path,
    const lmdj::provider::ProviderDescriptor& descriptor,
    std::string_view expected_provider_id) {
  const auto bytes = read_bytes(manifest_path);
  const auto manifest = nlohmann::json::parse(bytes);
  LMDJ_CHECK(
      bytes == lmdj::foundation::canonical_json(manifest) + "\n");
  LMDJ_CHECK(manifest.at("format") == "provider-source-package");
  LMDJ_CHECK(manifest.at("provider_id") == expected_provider_id);
  LMDJ_CHECK(manifest.at("provider_version") == "2.0.1");
  LMDJ_CHECK(manifest.at("files").size() == 3);
  for (const auto& file : manifest.at("files")) {
    const auto source_path =
        std::filesystem::path(file.at("path").get<std::string>());
    const auto described =
        lmdj::foundation::describe_artifact(source_path, "text/plain");
    LMDJ_CHECK(described.has_value());
    LMDJ_CHECK(
        described.value().sha256 ==
        file.at("sha256").get<std::string>());
  }
  const auto described_manifest =
      lmdj::foundation::describe_artifact(
          manifest_path, "application/json");
  LMDJ_CHECK(described_manifest.has_value());
  LMDJ_CHECK(
      descriptor.artifact_sha256 ==
      described_manifest.value().sha256);
}

void test_provider_identity_is_generated_from_source_package() {
  const auto registry = proof_registry();
  const auto providers = registry.list();
  const auto success = std::find_if(
      providers.begin(), providers.end(), [](const auto& provider) {
        return provider.id == "local.proof.success";
      });
  const auto failure = std::find_if(
      providers.begin(), providers.end(), [](const auto& provider) {
        return provider.id == "local.proof.failure";
      });
  LMDJ_CHECK(success != providers.end());
  LMDJ_CHECK(failure != providers.end());
  verify_source_package(
      std::filesystem::path(kSuccessProviderShaPath),
      *success,
      "local.proof.success");
  verify_source_package(
      std::filesystem::path(kFailureProviderShaPath),
      *failure,
      "local.proof.failure");
  LMDJ_CHECK(success->artifact_sha256 != failure->artifact_sha256);
}

class LeakingProvider final : public Provider {
 public:
  enum class Mode { returned_error, thrown_error };

  std::string id() const override { return "local.proof.leaking"; }

  std::vector<std::string> capabilities() const override {
    return {std::string(kCapability)};
  }

  AttemptResult run(lmdj::provider::ProviderRunContext context) override {
    const auto attempt_id = context.attempt_id;
    if (mode == Mode::thrown_error) {
      throw std::runtime_error("thrown-secret-sentinel");
    }
    return AttemptResult{
        std::move(attempt_id),
        std::nullopt,
        Error{
            ErrorCode::provider_failed,
            "returned-secret-sentinel",
            {{"reasoning", "returned-reasoning-sentinel"}},
        },
    };
  }

  Mode mode = Mode::returned_error;
};

class SinkThenFailProvider final : public Provider {
 public:
  enum class Mode {
    returned_error,
    thrown_error,
    invalid_outcome,
  };

  std::string id() const override { return "local.proof.sink-then-fail"; }

  std::vector<std::string> capabilities() const override {
    return {std::string(kCapability)};
  }

  AttemptResult run(lmdj::provider::ProviderRunContext context) override {
    const auto attempt_id = context.attempt_id;
    auto output = context.output;
    const std::array payload{std::byte{0x2a}};
    const auto artifact =
        output("candidate", payload, "application/x-lmdj-proof");
    if (!artifact.has_value()) {
      throw std::runtime_error("test sink unexpectedly failed");
    }
    if (mode == Mode::thrown_error) {
      throw std::runtime_error("failure after sink");
    }
    const auto error = Error{
        ErrorCode::provider_failed,
        "returned failure after sink",
    };
    if (mode == Mode::returned_error) {
      return AttemptResult{
          std::move(attempt_id),
          std::nullopt,
          error,
      };
    }
    return AttemptResult{
        attempt_id,
        lmdj::provider::Candidate{
            lmdj::foundation::CandidateId{attempt_id.value()},
            {{"candidate", artifact.value()}},
            nlohmann::json::object(),
        },
        error,
    };
  }

  Mode mode = Mode::returned_error;
};

class OptionalOutputProvider final : public Provider {
 public:
  std::string id() const override { return "local.proof.optional-output"; }

  std::vector<std::string> capabilities() const override {
    return {std::string(kCapability)};
  }

  AttemptResult run(lmdj::provider::ProviderRunContext context) override {
    const auto attempt_id = context.attempt_id;
    return AttemptResult{
        attempt_id,
        lmdj::provider::Candidate{
            lmdj::foundation::CandidateId{attempt_id.value()},
            {},
            nlohmann::json::object(),
        },
        std::nullopt,
    };
  }
};

class BlockingFailureProvider final : public Provider {
 public:
  std::string id() const override { return "local.proof.blocking"; }

  std::vector<std::string> capabilities() const override {
    return {std::string(kCapability)};
  }

  AttemptResult run(lmdj::provider::ProviderRunContext context) override {
    const auto attempt_id = context.attempt_id;
    const auto call =
        run_count.fetch_add(1, std::memory_order_relaxed) + 1;
    if (call == 1) {
      std::unique_lock lock(mutex);
      first_entered = true;
      condition.notify_all();
      condition.wait(lock, [this] { return released; });
    }
    return AttemptResult{
        std::move(attempt_id),
        std::nullopt,
        Error{
            ErrorCode::provider_failed,
            "blocking proof failure",
        },
    };
  }

  void wait_until_first_entered() {
    std::unique_lock lock(mutex);
    condition.wait(lock, [this] { return first_entered; });
  }

  void release_first() {
    std::lock_guard lock(mutex);
    released = true;
    condition.notify_all();
  }

  std::atomic<int> run_count{0};

 private:
  std::mutex mutex;
  std::condition_variable condition;
  bool first_entered = false;
  bool released = false;
};

class MultiCapabilityProvider final : public Provider {
 public:
  std::string id() const override { return "local.proof.multi"; }

  std::vector<std::string> capabilities() const override {
    return {
        "proof.alpha.v1",
        "proof.beta.v1",
    };
  }

  AttemptResult run(lmdj::provider::ProviderRunContext context) override {
    const auto attempt_id = context.attempt_id;
    return AttemptResult{
        std::move(attempt_id),
        std::nullopt,
        Error{
            ErrorCode::provider_failed,
            "unused multi-capability Provider",
        },
    };
  }
};

void test_failed_provider_outputs_are_removed_before_terminal_persistence() {
  TempDirectory temp;
  auto implementation = std::make_shared<SinkThenFailProvider>();
  auto capability = proof_capability();
  capability.max_output_bytes = 1;
  Registry registry;
  LMDJ_CHECK(
      registry
          .add(byte_fixture::opaque(ProviderRegistration{
              implementation,
              "1.0.0",
              "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
              "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
              std::nullopt,
              {std::move(capability)},
           {}, {} }))
          .has_value());
  auto store = store_at(temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              std::string(kCapability),
              implementation->id(),
              registry)
          .has_value());
  auto request = proof_request();
  request.inputs = {
      ArtifactBinding{
          "inputs",
          ArtifactRef{
              "85638a90a2b6d1e2f6be9814c961764f8a1be74871b15d9b05bc1c4017fd38b1",
              "audio/wav",
              12,
          },
      },
  };

  const std::array modes{
      SinkThenFailProvider::Mode::returned_error,
      SinkThenFailProvider::Mode::thrown_error,
      SinkThenFailProvider::Mode::invalid_outcome,
  };
  for (std::size_t index = 0; index < modes.size(); ++index) {
    implementation->mode = modes.at(index);
    const auto attempt_id =
        "attempt-output-cleanup-" + std::to_string(index);
    const auto executed =
        store.execute(AttemptId{attempt_id}, request, registry, byte_fixture::options());
    LMDJ_CHECK(executed.has_value());
    LMDJ_CHECK(executed.value().error.has_value());
    LMDJ_CHECK(
        executed.value().error->code == ErrorCode::provider_failed);
    const auto inspected = store.inspect(AttemptId{attempt_id});
    LMDJ_CHECK(inspected.has_value());
    LMDJ_CHECK(inspected.value().status == AttemptStatus::failed);
    LMDJ_CHECK(
        inspected.value().artifacts ==
        std::vector<ArtifactRef>{request.inputs.front().artifact});
    LMDJ_CHECK(
        !std::filesystem::exists(
            temp.path() / ".lmdj-workspace/attempts" / attempt_id));
  }
}

void test_optional_output_candidate_succeeds_without_staging() {
  TempDirectory temp;
  auto implementation = std::make_shared<OptionalOutputProvider>();
  auto capability = proof_capability();
  capability.output_artifacts.front().required = false;
  Registry registry;
  LMDJ_CHECK(
      registry
          .add(byte_fixture::opaque(ProviderRegistration{
              implementation,
              "1.0.0",
              "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
              "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
              std::nullopt,
              {std::move(capability)},
           {}, {} }))
          .has_value());
  auto store = store_at(temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              std::string(kCapability),
              implementation->id(),
              registry)
          .has_value());

  const auto attempt_id = AttemptId{"attempt-optional-output"};
  const auto executed =
      store.execute(attempt_id, proof_request(), registry, byte_fixture::options());
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().candidate.has_value());
  LMDJ_CHECK(executed.value().candidate->outputs.empty());
  LMDJ_CHECK(!executed.value().error.has_value());

  const auto inspected = store.inspect(attempt_id);
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().status == AttemptStatus::succeeded);
  LMDJ_CHECK(inspected.value().candidate_ids.size() == 1);
  LMDJ_CHECK(
      inspected.value().candidate_ids.front().value() ==
      attempt_id.value());
  LMDJ_CHECK(inspected.value().artifacts.empty());
  LMDJ_CHECK(!inspected.value().error.has_value());

  const auto attempt_root =
      temp.path() / ".lmdj-workspace/attempts" / attempt_id.value();
  LMDJ_CHECK(std::filesystem::is_directory(attempt_root));
  LMDJ_CHECK(
      !std::filesystem::exists(attempt_root / "staging"));
  LMDJ_CHECK(
      !std::filesystem::exists(attempt_root / "artifacts"));

  const auto duplicate =
      store.execute(attempt_id, proof_request(), registry, byte_fixture::options());
  LMDJ_CHECK(!duplicate.has_value());
  LMDJ_CHECK(duplicate.error().code == ErrorCode::duplicate_id);
}

void test_attempt_id_is_reserved_before_provider_invocation() {
  for (int iteration = 0; iteration < 20; ++iteration) {
    TempDirectory temp;
    auto implementation = std::make_shared<BlockingFailureProvider>();
    Registry registry;
    LMDJ_CHECK(
        registry
            .add(byte_fixture::opaque(ProviderRegistration{
                implementation,
                "1.0.0",
                "cccccccccccccccccccccccccccccccc"
                "cccccccccccccccccccccccccccccccc",
                std::nullopt,
                {proof_capability()},
             {}, {} }))
            .has_value());
    auto first_store = store_at(temp.path());
    auto second_store = store_at(temp.path());
    LMDJ_CHECK(
        first_store
            .set_provider_selection(
                std::string(kCapability),
                implementation->id(),
                registry)
            .has_value());

    std::optional<lmdj::foundation::Result<AttemptResult>> first;
    std::optional<lmdj::foundation::Result<AttemptResult>> second;
    const auto attempt =
        AttemptId{"attempt-concurrent-" + std::to_string(iteration)};
    std::thread first_thread([&] {
      first = first_store.execute(attempt, proof_request(), registry, byte_fixture::options());
    });
    implementation->wait_until_first_entered();
    std::thread second_thread([&] {
      second = second_store.execute(attempt, proof_request(), registry, byte_fixture::options());
    });
    second_thread.join();
    implementation->release_first();
    first_thread.join();

    LMDJ_CHECK(implementation->run_count.load() == 1);
    LMDJ_CHECK(first.has_value());
    LMDJ_CHECK(first->has_value());
    LMDJ_CHECK(second.has_value());
    LMDJ_CHECK(!second->has_value());
    LMDJ_CHECK(second->error().code == ErrorCode::duplicate_id);
  }
}

void test_provider_selection_updates_are_serialized() {
  auto implementation = std::make_shared<MultiCapabilityProvider>();
  Registry registry;
  LMDJ_CHECK(
      registry
          .add(byte_fixture::opaque(ProviderRegistration{
              implementation,
              "1.0.0",
              "dddddddddddddddddddddddddddddddd"
              "dddddddddddddddddddddddddddddddd",
              std::nullopt,
              {
                  named_proof_capability("proof.alpha.v1"),
                  named_proof_capability("proof.beta.v1"),
              },
           {}, {} }))
          .has_value());

  for (int iteration = 0; iteration < 100; ++iteration) {
    TempDirectory temp;
    auto alpha_store = store_at(temp.path());
    auto beta_store = store_at(temp.path());
    std::mutex gate_mutex;
    std::condition_variable gate_condition;
    int ready = 0;
    bool start = false;
    bool alpha_succeeded = false;
    bool beta_succeeded = false;
    const auto select_concurrently = [&](std::string capability, bool& result) {
      {
        std::unique_lock lock(gate_mutex);
        ++ready;
        gate_condition.notify_all();
        gate_condition.wait(lock, [&] { return start; });
      }
      auto& store =
          capability == "proof.alpha.v1" ? alpha_store : beta_store;
      result = store
                   .set_provider_selection(
                       std::move(capability),
                       implementation->id(),
                       registry)
                   .has_value();
    };
    std::thread alpha_thread(
        select_concurrently,
        "proof.alpha.v1",
        std::ref(alpha_succeeded));
    std::thread beta_thread(
        select_concurrently,
        "proof.beta.v1",
        std::ref(beta_succeeded));
    {
      std::unique_lock lock(gate_mutex);
      gate_condition.wait(lock, [&] { return ready == 2; });
      start = true;
      gate_condition.notify_all();
    }
    alpha_thread.join();
    beta_thread.join();

    LMDJ_CHECK(alpha_succeeded);
    LMDJ_CHECK(beta_succeeded);
    const auto alpha =
        alpha_store.selected_provider("proof.alpha.v1");
    const auto beta =
        beta_store.selected_provider("proof.beta.v1");
    LMDJ_CHECK(alpha.has_value());
    LMDJ_CHECK(beta.has_value());
    LMDJ_CHECK(alpha.value() == implementation->id());
    LMDJ_CHECK(beta.value() == implementation->id());
  }

  TempDirectory persistent_lock_temp;
  auto store = store_at(persistent_lock_temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              "proof.alpha.v1",
              implementation->id(),
              registry)
          .has_value());
  const auto lock_path =
      persistent_lock_temp.path() / ".lmdj-workspace/.host-settings.lock";
  LMDJ_CHECK(std::filesystem::is_regular_file(lock_path));
  const auto continued = store.set_provider_selection(
      "proof.beta.v1", implementation->id(), registry);
  LMDJ_CHECK(continued.has_value());
}

void test_maximum_attempt_id_produces_a_valid_candidate_id() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              std::string(kCapability),
              "local.proof.success",
              registry)
          .has_value());
  const auto value = std::string(128, 'a');
  const auto executed =
      store.execute(AttemptId{value}, proof_request(), registry, byte_fixture::options());
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().candidate.has_value());
  LMDJ_CHECK(!executed.value().error.has_value());
  LMDJ_CHECK(executed.value().candidate->id.value() == value);
}

void test_provider_error_persistence_is_redacted() {
  TempDirectory temp;
  auto leaking = std::make_shared<LeakingProvider>();
  Registry registry;
  LMDJ_CHECK(
      registry
          .add(byte_fixture::opaque(ProviderRegistration{
              leaking,
              "1.0.0",
              "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
              "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              std::nullopt,
              {proof_capability()},
           {}, {} }))
          .has_value());
  auto store = store_at(temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              std::string(kCapability),
              "local.proof.leaking",
              registry)
          .has_value());

  const auto returned = store.execute(
      AttemptId{"attempt-returned-secret"},
      proof_request(),
      registry, byte_fixture::options());
  LMDJ_CHECK(returned.has_value());
  LMDJ_CHECK(returned.value().error.has_value());
  LMDJ_CHECK(
      returned.value().error->message ==
      "returned-secret-sentinel");
  auto inspected =
      store.inspect(AttemptId{"attempt-returned-secret"});
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().error.has_value());
  LMDJ_CHECK(
      inspected.value().error->message ==
      "provider execution failed");
  LMDJ_CHECK(inspected.value().error->details.empty());

  leaking->mode = LeakingProvider::Mode::thrown_error;
  const auto thrown = store.execute(
      AttemptId{"attempt-thrown-secret"},
      proof_request(),
      registry, byte_fixture::options());
  LMDJ_CHECK(thrown.has_value());
  LMDJ_CHECK(thrown.value().error.has_value());
  LMDJ_CHECK(
      thrown.value().error->message ==
      "provider execution failed");

  const auto workspace = temp.path() / ".lmdj-workspace";
  for (const auto sentinel : {
           "parameter-secret-sentinel",
           "parameter-reasoning-sentinel",
           "returned-secret-sentinel",
           "returned-reasoning-sentinel",
           "thrown-secret-sentinel",
       }) {
    assert_workspace_has_no(workspace, sentinel);
  }
}

void test_attempt_store_read_api_validates_private_terminal_formats() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              std::string(kCapability),
              "local.proof.success",
              registry)
          .has_value());
  const auto selected =
      store.selected_provider(std::string(kCapability));
  LMDJ_CHECK(selected.has_value());
  LMDJ_CHECK(selected.value() == "local.proof.success");

  const auto executed = store.execute(
      AttemptId{"attempt-inspect"}, proof_request(), registry, byte_fixture::options());
  LMDJ_CHECK(executed.has_value());
  const auto inspected = store.inspect(AttemptId{"attempt-inspect"});
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().status == AttemptStatus::succeeded);
  LMDJ_CHECK(
      inspected.value().attempt_id == AttemptId{"attempt-inspect"});
  LMDJ_CHECK(
      inspected.value().provider.id == "local.proof.success");
  LMDJ_CHECK(
      inspected.value().capability.contract ==
      "lmdj.capability.v2");
  LMDJ_CHECK(
      inspected.value().capability.version == "2.0.0");
  LMDJ_CHECK(inspected.value().candidate_ids.size() == 1);
  LMDJ_CHECK(!inspected.value().error.has_value());

  const auto workspace = temp.path() / ".lmdj-workspace";
  const auto settings =
      read_json(workspace / "host-settings.json");
  const auto attempt_path =
      workspace / "attempts/attempt-inspect.json";
  const auto attempt = read_json(attempt_path);
  LMDJ_CHECK(settings.at("format") == "provider-selections");
  LMDJ_CHECK(!settings.contains("contract"));
  LMDJ_CHECK(attempt.at("format") == "terminal-attempt-v2");
  LMDJ_CHECK(!attempt.contains("contract"));

  const auto original = read_bytes(attempt_path);
  write_bytes(attempt_path, " " + original);
  const auto noncanonical =
      store.inspect(AttemptId{"attempt-inspect"});
  LMDJ_CHECK(!noncanonical.has_value());
  LMDJ_CHECK(
      noncanonical.error().code == ErrorCode::invalid_argument);

  auto nonterminal = nlohmann::json::parse(original);
  nonterminal["status"] = "running";
  write_bytes(
      attempt_path,
      lmdj::foundation::canonical_json(nonterminal) + "\n");
  const auto rejected =
      store.inspect(AttemptId{"attempt-inspect"});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);

  auto mismatched = nlohmann::json::parse(original);
  mismatched["request"]["capability"] = "proof.other.v2";
  write_bytes(
      attempt_path,
      lmdj::foundation::canonical_json(mismatched) + "\n");
  const auto mismatched_request =
      store.inspect(AttemptId{"attempt-inspect"});
  LMDJ_CHECK(!mismatched_request.has_value());
  LMDJ_CHECK(
      mismatched_request.error().code == ErrorCode::invalid_argument);

  auto malformed_settings = settings;
  malformed_settings["provider_selections"]["../invalid"] =
      "local.proof.success";
  write_bytes(
      workspace / "host-settings.json",
      lmdj::foundation::canonical_json(malformed_settings) + "\n");
  const auto malformed_selection =
      store.selected_provider(std::string(kCapability));
  LMDJ_CHECK(!malformed_selection.has_value());
  LMDJ_CHECK(
      malformed_selection.error().code == ErrorCode::invalid_argument);

  const auto unsafe = store.inspect(AttemptId{"../project"});
  LMDJ_CHECK(!unsafe.has_value());
  LMDJ_CHECK(unsafe.error().code == ErrorCode::invalid_argument);
}

void test_parameters_are_hashed_without_workspace_staging() {
  const auto source =
      read_bytes("packages/provider-sdk/src/attempt_store.cpp");
  LMDJ_CHECK(source.find(".parameters.") == std::string::npos);
  LMDJ_CHECK(
      source.find("write_bytes(temp_path, canonical)") ==
      std::string::npos);
  LMDJ_CHECK(source.find("picosha2") != std::string::npos);
}

void test_host_settings_lock_uses_kernel_owned_nonblocking_file_lock() {
  const auto source =
      read_bytes("packages/provider-sdk/src/attempt_store.cpp");
  const auto owner_region_at = source.find("class SettingsFileLock");
  const auto lock_region_at = source.find("acquire_settings_lock(");
  const auto lock_region_end =
      source.find("reject_existing_or_symlink(", lock_region_at);
  LMDJ_CHECK(owner_region_at != std::string::npos);
  LMDJ_CHECK(lock_region_at != std::string::npos);
  LMDJ_CHECK(lock_region_end > lock_region_at);

  const auto owner_region =
      source.substr(owner_region_at, lock_region_at - owner_region_at);
  const auto lock_region =
      source.substr(lock_region_at, lock_region_end - lock_region_at);
  LMDJ_CHECK(
      owner_region.find("static_cast<void>(descriptor_)") !=
      std::string::npos);
  LMDJ_CHECK(lock_region.find("LOCK_EX | LOCK_NB") != std::string::npos);
  LMDJ_CHECK(
      lock_region.find("std::filesystem::create_directory(lock_path") ==
      std::string::npos);
  LMDJ_CHECK(
      lock_region.find("release_settings_lock") == std::string::npos);
  LMDJ_CHECK(lock_region.find("::unlink(") == std::string::npos);
  LMDJ_CHECK(
      lock_region.find("std::filesystem::remove(") == std::string::npos);
}

void test_proof_failure_result_remains_exact_but_record_is_redacted() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              std::string(kCapability),
              "local.proof.failure",
              registry)
          .has_value());
  const auto result = store.execute(
      AttemptId{"attempt-proof-failure"}, proof_request(), registry, byte_fixture::options());
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value().error.has_value());
  LMDJ_CHECK(
      result.value().error->message ==
      "intentional proof failure");
  const auto inspected =
      store.inspect(AttemptId{"attempt-proof-failure"});
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().status == AttemptStatus::failed);
  LMDJ_CHECK(inspected.value().error.has_value());
  LMDJ_CHECK(
      inspected.value().error->message ==
      "provider execution failed");
  LMDJ_CHECK(inspected.value().error->details.empty());
}

void test_evidence_writes_are_durable_and_host_settings_are_not() {
  const auto store_source =
      read_bytes("packages/provider-sdk/src/attempt_store.cpp");
  const auto durable_source =
      read_bytes("packages/provider-sdk/src/durable_file.cpp");
  LMDJ_CHECK(durable_source.find("::fsync") != std::string::npos);

  const auto write_bytes_at =
      store_source.find("foundation::Result<void> write_bytes(");
  const auto write_new_at =
      store_source.find("foundation::Result<void> write_new_atomic(");
  const auto write_replace_at =
      store_source.find("foundation::Result<void> write_replace_atomic(");
  const auto read_settings_at =
      store_source.find("foundation::Result<nlohmann::json> read_host_settings(");
  LMDJ_CHECK(write_bytes_at != std::string::npos);
  LMDJ_CHECK(write_new_at > write_bytes_at);
  LMDJ_CHECK(write_replace_at > write_new_at);
  LMDJ_CHECK(read_settings_at > write_replace_at);

  const auto write_bytes_body =
      store_source.substr(write_bytes_at, write_new_at - write_bytes_at);
  LMDJ_CHECK(write_bytes_body.find("fsync") == std::string::npos);
  LMDJ_CHECK(
      write_bytes_body.find("write_bytes_durable") == std::string::npos);

  const auto write_new_body =
      store_source.substr(write_new_at, write_replace_at - write_new_at);
  LMDJ_CHECK(
      write_new_body.find("write_bytes_durable") != std::string::npos);
  LMDJ_CHECK(
      write_new_body.find("publish_new_link") != std::string::npos);
  LMDJ_CHECK(write_new_body.find("write_bytes(") == std::string::npos);

  const auto write_replace_body = store_source.substr(
      write_replace_at, read_settings_at - write_replace_at);
  LMDJ_CHECK(write_replace_body.find("write_bytes(") != std::string::npos);
  LMDJ_CHECK(
      write_replace_body.find("write_bytes_durable") == std::string::npos);
  LMDJ_CHECK(write_replace_body.find("fsync") == std::string::npos);

  LMDJ_CHECK(
      store_source.find(
          "std::ofstream stream(\n          temp_path") ==
      std::string::npos);
  LMDJ_CHECK(
      store_source.find("publish_replace") != std::string::npos);
}

void test_successful_proof_attempt_leaves_inspectable_terminal_record() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              std::string(kCapability),
              "local.proof.success",
              registry)
          .has_value());
  const auto result = store.execute(
      AttemptId{"attempt-durable-success"}, proof_request(), registry, byte_fixture::options());
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value().candidate.has_value());
  const auto record_path =
      temp.path() / ".lmdj-workspace/attempts/attempt-durable-success.json";
  LMDJ_CHECK(std::filesystem::is_regular_file(record_path));
  const auto inspected =
      store.inspect(AttemptId{"attempt-durable-success"});
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().status == AttemptStatus::succeeded);
  LMDJ_CHECK(!inspected.value().minted_outputs.empty());
  const auto artifact_path =
      temp.path() / ".lmdj-workspace/attempts/attempt-durable-success" /
      "artifacts" / inspected.value().minted_outputs.front().artifact.sha256;
  LMDJ_CHECK(std::filesystem::is_regular_file(artifact_path));
}

}  // namespace

int main() {
  try {
    test_capability_discovery_matches_public_schema_shape();
    test_capability_contract_encodes_supported_execution_traits();
    test_provider_identity_is_generated_from_source_package();
    test_failed_provider_outputs_are_removed_before_terminal_persistence();
    test_optional_output_candidate_succeeds_without_staging();
    test_attempt_id_is_reserved_before_provider_invocation();
    test_provider_selection_updates_are_serialized();
    test_maximum_attempt_id_produces_a_valid_candidate_id();
    test_provider_error_persistence_is_redacted();
    test_attempt_store_read_api_validates_private_terminal_formats();
    test_parameters_are_hashed_without_workspace_staging();
    test_host_settings_lock_uses_kernel_owned_nonblocking_file_lock();
    test_proof_failure_result_remains_exact_but_record_is_redacted();
    test_evidence_writes_are_durable_and_host_settings_are_not();
    test_successful_proof_attempt_leaves_inspectable_terminal_record();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "provider specification regression tests: PASS\n";
  return 0;
}
