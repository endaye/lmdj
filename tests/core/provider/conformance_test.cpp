#include <algorithm>
#include <chrono>
#include <concepts>
#include <cstddef>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/provider.hpp>
#include <lmdj/provider/registry.hpp>
#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AttemptId;
using lmdj::foundation::ErrorCode;
using lmdj::provider::AttemptResult;
using lmdj::provider::AttemptStore;
using lmdj::provider::CapabilityRequest;
using lmdj::provider::Provider;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::ProviderRegistration;
using lmdj::provider::Registry;

constexpr std::string_view kCapability = "proof.candidate.v1";
constexpr std::string_view kContract = "lmdj.capability.v1";
constexpr std::string_view kSchemaVersion = "1.0.0";
constexpr std::string_view kEmptySha256 =
    "e3b0c44298fc1c149afbf4c8996fb924"
    "27ae41e4649b934ca495991b7852b855";
using ExactProviderRun = AttemptResult (Provider::*)(
    AttemptId,
    const CapabilityRequest&,
    lmdj::provider::ArtifactSink);
static_assert(std::same_as<decltype(&Provider::run), ExactProviderRun>);

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-provider-test-" + std::to_string(nonce));
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

nlohmann::json read_json(const std::filesystem::path& path) {
  return nlohmann::json::parse(read_bytes(path));
}

ProviderRegistration proof_registration(
    std::shared_ptr<Provider> implementation,
    std::string artifact_sha256) {
  return ProviderRegistration{
      std::move(implementation),
      "0.1.0",
      std::move(artifact_sha256),
      std::nullopt,
      {
          lmdj::provider::CapabilityDescriptor{
              std::string(kCapability),
              std::string(kSchemaVersion),
              {{
                  "inputs",
                  {"*/*"},
                  "lmdj.artifact.input.v1",
                  "1.0.0",
                  false,
                  64,
              }},
              {{
                  "candidate",
                  {"application/x-lmdj-proof"},
                  "lmdj.artifact.proof.v1",
                  "1.0.0",
                  true,
                  1,
              }},
              lmdj::provider::Determinism::deterministic,
              {},
              {"PROVIDER_FAILED"},
              lmdj::provider::ResourceRequirements{
                  lmdj::provider::ResourceClass::light,
                  16,
              },
              lmdj::provider::ExecutionPolicy{1000, 1},
              lmdj::provider::CapabilityPolicy{
                  {"public"},
                  {"local"},
                  {"proof.execute"},
              },
              {"test"},
              0,
          },
      },
  };
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

ProviderPolicy local_public_policy() {
  return ProviderPolicy{
      {"local"},
      {"public"},
      {"proof.execute"},
  };
}

CapabilityRequest valid_request() {
  return CapabilityRequest{
      std::string(kCapability),
      {
          ArtifactRef{
              "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
              "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              "audio/wav",
              12,
          },
      },
      {
          {"seed", 7},
          {"secret", "must-not-be-persisted"},
          {"reasoning", "must-not-be-persisted"},
      },
      "public",
      "test",
      "local",
      {"proof.execute"},
  };
}

AttemptStore store_at(const std::filesystem::path& workspace_root) {
  return AttemptStore(
      workspace_root,
      local_public_policy(),
      [] { return std::string("2026-07-30T12:00:00.000Z"); });
}

void select(
    AttemptStore& store,
    const Registry& registry,
    std::string provider_id) {
  const auto selected = store.set_provider_selection(
      std::string(kCapability), std::move(provider_id), registry);
  LMDJ_CHECK(selected.has_value());
}

void check_canonical_file(const std::filesystem::path& path) {
  const auto bytes = read_bytes(path);
  const auto decoded = nlohmann::json::parse(bytes);
  LMDJ_CHECK(bytes == lmdj::foundation::canonical_json(decoded) + "\n");
}

void test_module_manifests_are_exact() {
  const auto sdk = read_json("packages/provider-sdk/module.json");
  const auto success = read_json("providers/local-proof-success/module.json");
  const auto failure = read_json("providers/local-proof-failure/module.json");
  LMDJ_CHECK(
      (sdk ==
       nlohmann::json{
           {"api_version", 1},
           {"contract", "lmdj.module.v1"},
           {"dependencies", {{"foundation", "0.1.0"}}},
           {"module", "provider-sdk"},
           {"version", "0.1.0"},
       }));
  for (const auto& manifest : {success, failure}) {
    LMDJ_CHECK(manifest.size() == 5);
    LMDJ_CHECK(manifest.at("api_version") == 1);
    LMDJ_CHECK(manifest.at("contract") == "lmdj.module.v1");
    LMDJ_CHECK(
        (manifest.at("dependencies") ==
         nlohmann::json{{"provider-sdk", "0.1.0"}}));
    LMDJ_CHECK(manifest.at("version") == "0.1.0");
  }
  LMDJ_CHECK(success.at("module") == "local.proof.success");
  LMDJ_CHECK(failure.at("module") == "local.proof.failure");
}

void test_registry_lists_capabilities_and_rejects_unknown_provider() {
  const auto registry = proof_registry();
  const auto providers = registry.list();
  LMDJ_CHECK(providers.size() == 2);

  const auto success = std::find_if(
      providers.begin(), providers.end(), [](const auto& descriptor) {
        return descriptor.id == "local.proof.success";
      });
  const auto failure = std::find_if(
      providers.begin(), providers.end(), [](const auto& descriptor) {
        return descriptor.id == "local.proof.failure";
      });
  LMDJ_CHECK(success != providers.end());
  LMDJ_CHECK(failure != providers.end());
  for (const auto* descriptor : {&*success, &*failure}) {
    LMDJ_CHECK(descriptor->version == "0.1.0");
    LMDJ_CHECK(descriptor->model_identity == std::nullopt);
    LMDJ_CHECK(descriptor->capabilities.size() == 1);
    LMDJ_CHECK(descriptor->capabilities.front().id == kCapability);
    LMDJ_CHECK(
        descriptor->capabilities.front().contract_version == kSchemaVersion);
    const auto& capability = descriptor->capabilities.front();
    LMDJ_CHECK(capability.input_artifacts.size() == 1);
    LMDJ_CHECK(capability.output_artifacts.size() == 1);
    LMDJ_CHECK(
        capability.determinism ==
        lmdj::provider::Determinism::deterministic);
    LMDJ_CHECK(
        capability.error_codes ==
        std::vector<std::string>{"PROVIDER_FAILED"});
    LMDJ_CHECK(capability.max_output_bytes == 0);
    LMDJ_CHECK(capability.execution.timeout_ms == 1000);
    LMDJ_CHECK(capability.execution.max_attempts == 1);
    LMDJ_CHECK(
        capability.policy.data_classifications ==
        std::vector<std::string>{"public"});
    LMDJ_CHECK(capability.platforms == std::vector<std::string>{"test"});
    LMDJ_CHECK(
        capability.policy.regions == std::vector<std::string>{"local"});
    LMDJ_CHECK(
        capability.policy.required_permissions ==
        std::vector<std::string>{"proof.execute"});
  }

  TempDirectory temp;
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.success");
  const auto settings_path =
      temp.path() / ".lmdj-workspace/host-settings.json";
  const auto original_settings = read_bytes(settings_path);
  const auto unknown = store.set_provider_selection(
      std::string(kCapability), "remote.missing", registry);
  LMDJ_CHECK(!unknown.has_value());
  LMDJ_CHECK(unknown.error().code == ErrorCode::provider_not_found);
  LMDJ_CHECK(read_bytes(settings_path) == original_settings);

  const auto unsupported = store.set_provider_selection(
      "proof.unknown.v1", "local.proof.success", registry);
  LMDJ_CHECK(!unsupported.has_value());
  LMDJ_CHECK(unsupported.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(settings_path) == original_settings);
}

void test_success_provider_emits_scoped_empty_artifact_and_canonical_attempt() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.success");

  const auto executed = store.execute(
      AttemptId{"attempt-success"}, valid_request(), registry);
  LMDJ_CHECK(executed.has_value());
  const auto& result = executed.value();
  LMDJ_CHECK(result.attempt_id == AttemptId{"attempt-success"});
  LMDJ_CHECK(result.candidate.has_value());
  LMDJ_CHECK(!result.error.has_value());
  const auto& candidate = *result.candidate;
  const auto selected =
      registry.select("local.proof.success", std::string(kCapability));
  LMDJ_CHECK(selected.has_value());
  const auto& provider_sha256 =
      selected.value().descriptor.artifact_sha256;
  LMDJ_CHECK(candidate.id.value() == "attempt-success");
  LMDJ_CHECK(candidate.outputs.size() == 1);
  LMDJ_CHECK(candidate.outputs.front().sha256 == kEmptySha256);
  LMDJ_CHECK(candidate.outputs.front().media_type == "application/x-lmdj-proof");
  LMDJ_CHECK(candidate.outputs.front().byte_length == 0);
  const auto expected_provenance = nlohmann::json{
      {"capability", kCapability},
      {"contract", kContract},
      {"model_identity", nullptr},
      {"provider",
       {
           {"artifact_sha256", provider_sha256},
           {"id", "local.proof.success"},
           {"version", "0.1.0"},
       }},
      {"contract_version", kSchemaVersion},
  };
  LMDJ_CHECK(candidate.provenance == expected_provenance);

  const auto workspace = temp.path() / ".lmdj-workspace";
  const auto artifact_path =
      workspace / "attempts/attempt-success/artifacts" /
      std::string(kEmptySha256);
  const auto attempt_path = workspace / "attempts/attempt-success.json";
  LMDJ_CHECK(std::filesystem::is_regular_file(artifact_path));
  LMDJ_CHECK(std::filesystem::file_size(artifact_path) == 0);
  LMDJ_CHECK(std::filesystem::is_regular_file(attempt_path));
  check_canonical_file(attempt_path);

  const auto attempt = read_json(attempt_path);
  LMDJ_CHECK(attempt.at("format") == "terminal-attempt");
  LMDJ_CHECK(!attempt.contains("contract"));
  LMDJ_CHECK(attempt.at("status") == "succeeded");
  LMDJ_CHECK(attempt.at("candidate_ids") ==
             nlohmann::json::array({"attempt-success"}));
  LMDJ_CHECK(attempt.at("artifacts").size() == 2);
  LMDJ_CHECK(attempt.at("provider").at("id") == "local.proof.success");
  LMDJ_CHECK(attempt.at("provider").at("version") == "0.1.0");
  LMDJ_CHECK(
      attempt.at("provider").at("artifact_sha256") ==
      provider_sha256);
  LMDJ_CHECK(attempt.at("provider").at("model_identity").is_null());
  LMDJ_CHECK(attempt.at("error").is_null());
  LMDJ_CHECK(attempt.at("request").at("capability") == kCapability);
  LMDJ_CHECK(!attempt.at("request").contains("parameters"));
  LMDJ_CHECK(
      attempt.at("request").at("parameters_sha256") ==
      "4edc6af7bb64508f0dc12a8a9687bef8"
      "af408cd9563a7e34730ac7c096d75535");
  LMDJ_CHECK(read_bytes(attempt_path).find("must-not-be-persisted") ==
             std::string::npos);
  LMDJ_CHECK(read_bytes(attempt_path).find("\"reasoning\"") ==
             std::string::npos);

  const auto host_settings_path = workspace / "host-settings.json";
  LMDJ_CHECK(std::filesystem::is_regular_file(host_settings_path));
  check_canonical_file(host_settings_path);
  const auto host_settings = read_json(host_settings_path);
  LMDJ_CHECK(host_settings.at("format") == "provider-selections");
  LMDJ_CHECK(!host_settings.contains("contract"));
  LMDJ_CHECK(
      host_settings.at("provider_selections").at(kCapability) ==
      "local.proof.success");

  for (const auto& entry :
       std::filesystem::directory_iterator(temp.path())) {
    LMDJ_CHECK(entry.path().filename() == ".lmdj-workspace");
  }
}

void test_failure_provider_records_typed_terminal_attempt() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.failure");

  const auto executed = store.execute(
      AttemptId{"attempt-failure"}, valid_request(), registry);
  LMDJ_CHECK(executed.has_value());
  const auto& result = executed.value();
  LMDJ_CHECK(!result.candidate.has_value());
  LMDJ_CHECK(result.error.has_value());
  LMDJ_CHECK(result.error->code == ErrorCode::provider_failed);
  LMDJ_CHECK(result.error->message == "intentional proof failure");

  const auto attempt_path =
      temp.path() /
      ".lmdj-workspace/attempts/attempt-failure.json";
  check_canonical_file(attempt_path);
  const auto attempt = read_json(attempt_path);
  LMDJ_CHECK(attempt.at("status") == "failed");
  LMDJ_CHECK(attempt.at("candidate_ids").empty());
  LMDJ_CHECK(attempt.at("error").at("code") == "PROVIDER_FAILED");
  LMDJ_CHECK(
      attempt.at("error").at("message") ==
      "provider execution failed");
  LMDJ_CHECK(attempt.at("provider").at("id") == "local.proof.failure");
  LMDJ_CHECK(attempt.at("artifacts").size() == 1);
  LMDJ_CHECK(!std::filesystem::exists(
      temp.path() /
      ".lmdj-workspace/attempts/attempt-failure"));
}

class CountingProvider final : public Provider {
 public:
  std::string id() const override { return "local.proof.counting"; }

  std::vector<std::string> capabilities() const override {
    return {std::string(kCapability)};
  }

  AttemptResult run(
      AttemptId attempt_id,
      const CapabilityRequest&,
      lmdj::provider::ArtifactSink) override {
    ++run_count;
    return AttemptResult{
        std::move(attempt_id),
        std::nullopt,
        lmdj::foundation::Error{
            ErrorCode::provider_failed,
            "counting provider executed",
        },
    };
  }

  int run_count = 0;
};

class InvalidOutcomeProvider final : public Provider {
 public:
  enum class Mode {
    both,
    neither,
    wrong_attempt,
    fabricated_output,
    sink_failure,
    throws,
  };

  std::string id() const override { return "local.proof.invalid"; }

  std::vector<std::string> capabilities() const override {
    return {std::string(kCapability)};
  }

  AttemptResult run(
      AttemptId attempt_id,
      const CapabilityRequest&,
      lmdj::provider::ArtifactSink output) override {
    const auto candidate = lmdj::provider::Candidate{
        lmdj::foundation::CandidateId{
            "candidate-" + attempt_id.value()},
        {
            ArtifactRef{
                std::string(kEmptySha256),
                "application/x-lmdj-proof",
                0,
            },
        },
        nlohmann::json::object(),
    };
    switch (mode) {
      case Mode::both:
        return AttemptResult{
            std::move(attempt_id),
            candidate,
            lmdj::foundation::Error{
                ErrorCode::provider_failed,
                "provider returned both",
            },
        };
      case Mode::neither:
        return AttemptResult{
            std::move(attempt_id),
            std::nullopt,
            std::nullopt,
        };
      case Mode::wrong_attempt:
        return AttemptResult{
            AttemptId{"attempt-wrong"},
            candidate,
            std::nullopt,
        };
      case Mode::fabricated_output:
        return AttemptResult{
            std::move(attempt_id),
            candidate,
            std::nullopt,
        };
      case Mode::sink_failure: {
        const auto sink_result = output({}, "");
        if (sink_result.has_value()) {
          auto minted = candidate;
          minted.outputs = {sink_result.value()};
          return AttemptResult{
              std::move(attempt_id),
              std::move(minted),
              std::nullopt,
          };
        }
        return AttemptResult{
            std::move(attempt_id),
            candidate,
            std::nullopt,
        };
      }
      case Mode::throws:
        throw std::runtime_error("provider-secret-must-not-persist");
    }
    throw std::runtime_error("unreachable invalid provider mode");
  }

  Mode mode = Mode::both;
};

void test_untrusted_provider_outcomes_are_rejected_as_typed_failures() {
  TempDirectory temp;
  auto invalid = std::make_shared<InvalidOutcomeProvider>();
  Registry registry;
  LMDJ_CHECK(
      registry
          .add(proof_registration(
              invalid,
              "dddddddddddddddddddddddddddddddd"
              "dddddddddddddddddddddddddddddddd"))
          .has_value());
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.invalid");

  const std::vector modes{
      InvalidOutcomeProvider::Mode::both,
      InvalidOutcomeProvider::Mode::neither,
      InvalidOutcomeProvider::Mode::wrong_attempt,
      InvalidOutcomeProvider::Mode::fabricated_output,
      InvalidOutcomeProvider::Mode::sink_failure,
      InvalidOutcomeProvider::Mode::throws,
  };
  for (std::size_t index = 0; index < modes.size(); ++index) {
    invalid->mode = modes.at(index);
    const auto attempt_id =
        "attempt-invalid-outcome-" + std::to_string(index);
    const auto executed = store.execute(
        AttemptId{attempt_id}, valid_request(), registry);
    LMDJ_CHECK(executed.has_value());
    LMDJ_CHECK(!executed.value().candidate.has_value());
    LMDJ_CHECK(executed.value().error.has_value());
    LMDJ_CHECK(
        executed.value().error->code == ErrorCode::provider_failed);
    const auto path = temp.path() / ".lmdj-workspace/attempts" /
                      (attempt_id + ".json");
    check_canonical_file(path);
    const auto bytes = read_bytes(path);
    LMDJ_CHECK(bytes.find("provider-secret-must-not-persist") ==
               std::string::npos);
    LMDJ_CHECK(
        read_json(path).at("error").at("code") == "PROVIDER_FAILED");
  }
}

void test_policy_and_invalid_requests_fail_closed_before_provider_execution() {
  TempDirectory temp;
  auto counting = std::make_shared<CountingProvider>();
  Registry registry;
  LMDJ_CHECK(
      registry
          .add(proof_registration(
              counting,
              "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
              "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"))
          .has_value());
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.counting");

  auto invalid_region = valid_request();
  invalid_region.region = "remote";
  const auto region_result = store.execute(
      AttemptId{"attempt-invalid-region"}, invalid_region, registry);
  LMDJ_CHECK(region_result.has_value());
  LMDJ_CHECK(region_result.value().error.has_value());
  LMDJ_CHECK(
      region_result.value().error->code == ErrorCode::permission_denied);
  LMDJ_CHECK(counting->run_count == 0);

  auto missing_permission = valid_request();
  missing_permission.required_permissions = {};
  const auto missing_permission_result = store.execute(
      AttemptId{"attempt-missing-permission"},
      missing_permission,
      registry);
  LMDJ_CHECK(missing_permission_result.has_value());
  LMDJ_CHECK(missing_permission_result.value().error.has_value());
  LMDJ_CHECK(
      missing_permission_result.value().error->code ==
      ErrorCode::permission_denied);
  LMDJ_CHECK(counting->run_count == 0);

  auto invalid_platform = valid_request();
  invalid_platform.platform = "unsupported";
  const auto platform_result = store.execute(
      AttemptId{"attempt-invalid-platform"}, invalid_platform, registry);
  LMDJ_CHECK(platform_result.has_value());
  LMDJ_CHECK(platform_result.value().error.has_value());
  LMDJ_CHECK(
      platform_result.value().error->code == ErrorCode::permission_denied);
  LMDJ_CHECK(counting->run_count == 0);

  auto duplicate_permission = valid_request();
  duplicate_permission.required_permissions.push_back("proof.execute");
  const auto duplicate_permission_result = store.execute(
      AttemptId{"attempt-duplicate-permission"},
      duplicate_permission,
      registry);
  LMDJ_CHECK(duplicate_permission_result.has_value());
  LMDJ_CHECK(duplicate_permission_result.value().error.has_value());
  LMDJ_CHECK(
      duplicate_permission_result.value().error->code ==
      ErrorCode::invalid_argument);
  LMDJ_CHECK(counting->run_count == 0);

  auto invalid_classification = valid_request();
  invalid_classification.data_classification = "restricted";
  const auto classification_result = store.execute(
      AttemptId{"attempt-invalid-classification"},
      invalid_classification,
      registry);
  LMDJ_CHECK(classification_result.has_value());
  LMDJ_CHECK(classification_result.value().error.has_value());
  LMDJ_CHECK(
      classification_result.value().error->code ==
      ErrorCode::permission_denied);
  LMDJ_CHECK(counting->run_count == 0);

  auto invalid_permission = valid_request();
  invalid_permission.required_permissions = {"proof.admin"};
  const auto permission_result = store.execute(
      AttemptId{"attempt-invalid-permission"},
      invalid_permission,
      registry);
  LMDJ_CHECK(permission_result.has_value());
  LMDJ_CHECK(permission_result.value().error.has_value());
  LMDJ_CHECK(
      permission_result.value().error->code == ErrorCode::permission_denied);
  LMDJ_CHECK(counting->run_count == 0);

  auto duplicate_input = valid_request();
  duplicate_input.inputs.push_back(duplicate_input.inputs.front());
  const auto duplicate_result = store.execute(
      AttemptId{"attempt-duplicate-input"}, duplicate_input, registry);
  LMDJ_CHECK(duplicate_result.has_value());
  LMDJ_CHECK(duplicate_result.value().error.has_value());
  LMDJ_CHECK(
      duplicate_result.value().error->code == ErrorCode::invalid_argument);
  LMDJ_CHECK(counting->run_count == 0);

  auto malformed_input = valid_request();
  malformed_input.inputs.front().sha256 = "../project";
  const auto malformed_result = store.execute(
      AttemptId{"attempt-malformed-input"}, malformed_input, registry);
  LMDJ_CHECK(malformed_result.has_value());
  LMDJ_CHECK(malformed_result.value().error.has_value());
  LMDJ_CHECK(
      malformed_result.value().error->code == ErrorCode::invalid_argument);
  LMDJ_CHECK(counting->run_count == 0);

  for (const auto attempt_id : {
           "attempt-invalid-region",
           "attempt-invalid-classification",
           "attempt-invalid-permission",
           "attempt-missing-permission",
           "attempt-invalid-platform",
           "attempt-duplicate-permission",
           "attempt-duplicate-input",
           "attempt-malformed-input",
       }) {
    const auto path = temp.path() / ".lmdj-workspace/attempts" /
                      (std::string(attempt_id) + ".json");
    LMDJ_CHECK(std::filesystem::is_regular_file(path));
    check_canonical_file(path);
  }
}

void test_duplicate_attempt_and_registration_inputs_are_rejected() {
  TempDirectory temp;
  auto counting = std::make_shared<CountingProvider>();
  Registry registry;
  const auto valid_registration = proof_registration(
      counting,
      "cccccccccccccccccccccccccccccccc"
      "cccccccccccccccccccccccccccccccc");
  LMDJ_CHECK(registry.add(valid_registration).has_value());
  const auto duplicate_registration = registry.add(valid_registration);
  LMDJ_CHECK(!duplicate_registration.has_value());
  LMDJ_CHECK(duplicate_registration.error().code == ErrorCode::duplicate_id);

  auto store = store_at(temp.path());
  select(store, registry, "local.proof.counting");
  const auto first = store.execute(
      AttemptId{"attempt-once"}, valid_request(), registry);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(counting->run_count == 1);
  const auto before = read_bytes(
      temp.path() / ".lmdj-workspace/attempts/attempt-once.json");
  const auto duplicate = store.execute(
      AttemptId{"attempt-once"}, valid_request(), registry);
  LMDJ_CHECK(!duplicate.has_value());
  LMDJ_CHECK(duplicate.error().code == ErrorCode::duplicate_id);
  LMDJ_CHECK(counting->run_count == 1);
  LMDJ_CHECK(
      read_bytes(
          temp.path() / ".lmdj-workspace/attempts/attempt-once.json") ==
      before);

  for (const auto unsafe_id : {
           "",
           ".",
           "..",
           "../project",
           "/absolute",
           "a/b",
           "a\\b",
           "CON",
       }) {
    const auto unsafe = store.execute(
        AttemptId{unsafe_id}, valid_request(), registry);
    LMDJ_CHECK(!unsafe.has_value());
    LMDJ_CHECK(unsafe.error().code == ErrorCode::invalid_argument);
  }
}

void test_provenance_is_deterministic_across_attempts() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.success");
  const auto first = store.execute(
      AttemptId{"attempt-deterministic-a"}, valid_request(), registry);
  const auto second = store.execute(
      AttemptId{"attempt-deterministic-b"}, valid_request(), registry);
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(first.value().candidate.has_value());
  LMDJ_CHECK(second.value().candidate.has_value());
  LMDJ_CHECK(
      first.value().candidate->provenance ==
      second.value().candidate->provenance);
  LMDJ_CHECK(
      first.value().candidate->outputs ==
      second.value().candidate->outputs);
}

}  // namespace

int main() {
  try {
    test_module_manifests_are_exact();
    test_registry_lists_capabilities_and_rejects_unknown_provider();
    test_success_provider_emits_scoped_empty_artifact_and_canonical_attempt();
    test_failure_provider_records_typed_terminal_attempt();
    test_untrusted_provider_outcomes_are_rejected_as_typed_failures();
    test_policy_and_invalid_requests_fail_closed_before_provider_execution();
    test_duplicate_attempt_and_registration_inputs_are_rejected();
    test_provenance_is_deterministic_across_attempts();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "provider conformance tests: PASS\n";
  return 0;
}
