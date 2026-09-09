#include <algorithm>
#include <array>
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
#include "tests/core/provider/byte_fixture.hpp"

namespace {

using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AttemptId;
using lmdj::foundation::ErrorCode;
using lmdj::provider::ArtifactBinding;
using lmdj::provider::AttemptResult;
using lmdj::provider::AttemptStore;
using lmdj::provider::CapabilityRequest;
using lmdj::provider::ModelIdentity;
using lmdj::provider::Provider;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::ProviderRegistration;
using lmdj::provider::Registry;

constexpr std::string_view kCapability = "proof.candidate.v2";
constexpr std::string_view kContract = "lmdj.capability.v2";
constexpr std::string_view kSchemaVersion = "2.0.0";
constexpr std::string_view kMultiPortCapability = "proof.multi-port.v2";
constexpr std::string_view kEmptySha256 =
    "e3b0c44298fc1c149afbf4c8996fb924"
    "27ae41e4649b934ca495991b7852b855";
using ExactProviderRun = AttemptResult (Provider::*)(
    lmdj::provider::ProviderRunContext);
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
  return byte_fixture::opaque(ProviderRegistration{
      std::move(implementation),
      "1.0.0",
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
   {}, {} });
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
          ArtifactBinding{
              "inputs",
              ArtifactRef{
                  "85638a90a2b6d1e2f6be9814c961764f8a1be74871b15d9b05bc1c4017fd38b1",
                  "audio/wav",
                  12,
              },
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

void select_capability(
    AttemptStore& store,
    const Registry& registry,
    std::string capability,
    std::string provider_id) {
  const auto selected = store.set_provider_selection(
      std::move(capability), std::move(provider_id), registry);
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
           {"api_version", 3},
           {"contract", "lmdj.module.v1"},
           {"dependencies", {{"foundation", "0.4.0"}}},
           {"module", "provider-sdk"},
           {"version", "2.1.0"},
       }));
  for (const auto& manifest : {success, failure}) {
    LMDJ_CHECK(manifest.size() == 5);
    LMDJ_CHECK(manifest.at("api_version") == 3);
    LMDJ_CHECK(manifest.at("contract") == "lmdj.module.v1");
    LMDJ_CHECK(
        (manifest.at("dependencies") ==
         nlohmann::json{{"provider-sdk", "2.1.0"}}));
    LMDJ_CHECK(manifest.at("version") == "2.0.1");
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
    LMDJ_CHECK(descriptor->version == "2.0.1");
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
      AttemptId{"attempt-success"}, valid_request(), registry, byte_fixture::options());
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
  LMDJ_CHECK(candidate.outputs.front().port == "candidate");
  LMDJ_CHECK(candidate.outputs.front().artifact.sha256 == kEmptySha256);
  LMDJ_CHECK(
      candidate.outputs.front().artifact.media_type ==
      "application/x-lmdj-proof");
  LMDJ_CHECK(candidate.outputs.front().artifact.byte_length == 0);
  const auto expected_provenance = nlohmann::json{
      {"capability", kCapability},
      {"contract", kContract},
      {"model_identity", nullptr},
      {"provider",
       {
           {"artifact_sha256", provider_sha256},
           {"id", "local.proof.success"},
           {"version", "2.0.1"},
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
  LMDJ_CHECK(attempt.at("format") == "terminal-attempt-v2");
  LMDJ_CHECK(!attempt.contains("contract"));
  LMDJ_CHECK(attempt.at("status") == "succeeded");
  LMDJ_CHECK(attempt.at("candidate_ids") ==
             nlohmann::json::array({"attempt-success"}));
  LMDJ_CHECK(attempt.at("artifacts").size() == 2);
  LMDJ_CHECK(attempt.at("provider").at("id") == "local.proof.success");
  LMDJ_CHECK(attempt.at("provider").at("version") == "2.0.1");
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

void test_structured_model_identity_is_preserved_in_attempt_provenance() {
  const auto model = ModelIdentity{
      "proof.model",
      "weights-v1",
      std::string(64, 'b'),
  };
  auto registration =
      lmdj::providers::local_proof_success_registration();
  registration.model_identity = model;
  Registry registry;
  LMDJ_CHECK(registry.add(std::move(registration)).has_value());
  const auto descriptors = registry.list();
  LMDJ_CHECK(descriptors.size() == 1);
  LMDJ_CHECK(descriptors.front().model_identity == model);

  TempDirectory temp;
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.success");
  const auto executed = store.execute(
      AttemptId{"attempt-model-identity"}, valid_request(), registry, byte_fixture::options());
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().candidate.has_value());
  const auto model_json = nlohmann::json{
      {"id", model.id},
      {"version", model.version},
      {"artifact_sha256", model.artifact_sha256},
  };
  LMDJ_CHECK(
      executed.value().candidate->provenance.at("model_identity") ==
      model_json);

  const auto inspected =
      store.inspect(AttemptId{"attempt-model-identity"});
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().provider.model_identity == model);
  const auto persisted = read_json(
      temp.path() /
      ".lmdj-workspace/attempts/attempt-model-identity.json");
  LMDJ_CHECK(
      persisted.at("provider").at("model_identity") == model_json);
}

void test_failure_provider_records_typed_terminal_attempt() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.failure");

  const auto executed = store.execute(
      AttemptId{"attempt-failure"}, valid_request(), registry, byte_fixture::options());
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

  AttemptResult run(lmdj::provider::ProviderRunContext context) override {
    const auto attempt_id = context.attempt_id;
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

  AttemptResult run(lmdj::provider::ProviderRunContext context) override {
    const auto attempt_id = context.attempt_id;
    auto output = context.output;
    const auto candidate = lmdj::provider::Candidate{
        lmdj::foundation::CandidateId{
            "candidate-" + attempt_id.value()},
        {
            ArtifactBinding{
                "candidate",
                ArtifactRef{
                    std::string(kEmptySha256),
                    "application/x-lmdj-proof",
                    0,
                },
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
        const auto sink_result = output("candidate", {}, "");
        if (sink_result.has_value()) {
          auto minted = candidate;
          minted.outputs = {{"candidate", sink_result.value()}};
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

class MultiPortProvider final : public Provider {
 public:
  enum class Mode {
    success,
    missing_required_output,
    secondary_overflow,
    unknown_sink_port,
    unknown_candidate_port,
    candidate_port_mismatch,
    duplicate_mint,
    empty_candidate,
  };

  std::string id() const override { return "local.proof.multi-port"; }

  std::vector<std::string> capabilities() const override {
    return {std::string(kMultiPortCapability)};
  }

  AttemptResult run(lmdj::provider::ProviderRunContext context) override {
    const auto attempt_id = context.attempt_id;
    auto output = context.output;
    ++run_count;
    if (mode == Mode::empty_candidate) {
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

    const std::array primary_bytes{std::byte{0x01}};
    const auto primary = output(
        "primary", primary_bytes, "application/x-lmdj-proof");
    LMDJ_CHECK(primary.has_value());

    if (mode == Mode::unknown_sink_port) {
      const auto unknown = output(
          "unknown", primary_bytes, "application/x-lmdj-proof");
      unknown_sink_rejected = !unknown.has_value();
      return AttemptResult{
          std::move(attempt_id),
          std::nullopt,
          lmdj::foundation::Error{
              ErrorCode::provider_failed,
              "unknown sink port rejected",
          },
      };
    }

    if (mode == Mode::duplicate_mint) {
      const auto duplicate = output(
          "secondary", primary_bytes, "application/x-lmdj-proof");
      duplicate_mint_rejected = !duplicate.has_value();
      return AttemptResult{
          std::move(attempt_id),
          std::nullopt,
          lmdj::foundation::Error{
              ErrorCode::provider_failed,
              "duplicate mint rejected",
          },
      };
    }

    if (mode == Mode::missing_required_output) {
      return AttemptResult{
          attempt_id,
          lmdj::provider::Candidate{
              lmdj::foundation::CandidateId{attempt_id.value()},
              {{"primary", primary.value()}},
              nlohmann::json::object(),
          },
          std::nullopt,
      };
    }

    if (mode == Mode::unknown_candidate_port) {
      return AttemptResult{
          attempt_id,
          lmdj::provider::Candidate{
              lmdj::foundation::CandidateId{attempt_id.value()},
              {{"unknown", primary.value()}},
              nlohmann::json::object(),
          },
          std::nullopt,
      };
    }

    if (mode == Mode::candidate_port_mismatch) {
      return AttemptResult{
          attempt_id,
          lmdj::provider::Candidate{
              lmdj::foundation::CandidateId{attempt_id.value()},
              {{"secondary", primary.value()}},
              nlohmann::json::object(),
          },
          std::nullopt,
      };
    }

    const std::array secondary_bytes{std::byte{0x02}};
    const auto secondary = output(
        "secondary", secondary_bytes, "application/x-lmdj-proof");
    LMDJ_CHECK(secondary.has_value());
    auto outputs = std::vector<ArtifactBinding>{
        {"secondary", secondary.value()},
        {"primary", primary.value()},
    };
    if (mode == Mode::secondary_overflow) {
      const std::array overflow_bytes{std::byte{0x03}};
      const auto overflow = output(
          "secondary", overflow_bytes, "application/x-lmdj-proof");
      LMDJ_CHECK(overflow.has_value());
      outputs.push_back({"secondary", overflow.value()});
    }
    return AttemptResult{
        attempt_id,
        lmdj::provider::Candidate{
            lmdj::foundation::CandidateId{attempt_id.value()},
            std::move(outputs),
            nlohmann::json::object(),
        },
        std::nullopt,
    };
  }

  Mode mode = Mode::success;
  int run_count = 0;
  bool unknown_sink_rejected = false;
  bool duplicate_mint_rejected = false;
};

std::vector<lmdj::provider::ArtifactPortDescriptor> multi_input_ports() {
  return {
      {
          "source",
          {"application/x-lmdj-proof"},
          "lmdj.artifact.proof-source.v1",
          "1.0.0",
          true,
          1,
      },
      {
          "reference",
          {"application/x-lmdj-proof"},
          "lmdj.artifact.proof-reference.v1",
          "1.0.0",
          true,
          1,
      },
  };
}

std::vector<lmdj::provider::ArtifactPortDescriptor> multi_output_ports(
    bool required = true) {
  return {
      {
          "primary",
          {"application/x-lmdj-proof"},
          "lmdj.artifact.proof-primary.v1",
          "1.0.0",
          required,
          1,
      },
      {
          "secondary",
          {"application/x-lmdj-proof"},
          "lmdj.artifact.proof-secondary.v1",
          "1.0.0",
          required,
          1,
      },
  };
}

ProviderRegistration multi_port_registration(
    const std::shared_ptr<MultiPortProvider>& implementation,
    std::vector<lmdj::provider::ArtifactPortDescriptor> input_ports,
    std::vector<lmdj::provider::ArtifactPortDescriptor> output_ports) {
  return byte_fixture::opaque(ProviderRegistration{
      implementation,
      "1.0.0",
      std::string(64, 'f'),
      std::nullopt,
      {
          lmdj::provider::CapabilityDescriptor{
              std::string(kMultiPortCapability),
              "2.0.0",
              std::move(input_ports),
              std::move(output_ports),
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
              16,
          },
      },
   {}, {} });
}

CapabilityRequest multi_port_request() {
  return CapabilityRequest{
      std::string(kMultiPortCapability),
      {
          ArtifactBinding{
              "reference",
              ArtifactRef{
                  "3b64db95cb55c763391c707108489ae18b4112d783300de38e033b4c98c3deaf",
                  "application/x-lmdj-proof",
                  2,
              },
          },
          ArtifactBinding{
              "source",
              ArtifactRef{
                  "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
                  "application/x-lmdj-proof",
                  1,
              },
          },
      },
      nlohmann::json::object(),
      "public",
      "test",
      "local",
      {"proof.execute"},
  };
}

Registry multi_port_registry(
    const std::shared_ptr<MultiPortProvider>& implementation,
    bool outputs_required = true) {
  Registry registry;
  LMDJ_CHECK(
      registry
          .add(multi_port_registration(
              implementation,
              multi_input_ports(),
              multi_output_ports(outputs_required)))
          .has_value());
  return registry;
}

void check_provider_failure(const AttemptResult& result) {
  LMDJ_CHECK(!result.candidate.has_value());
  LMDJ_CHECK(result.error.has_value());
  LMDJ_CHECK(result.error->code == ErrorCode::provider_failed);
}

void test_v2_registry_rejects_empty_output_descriptors() {
  auto provider = std::make_shared<MultiPortProvider>();
  Registry registry;
  const auto added = registry.add(multi_port_registration(
      provider, multi_input_ports(), {}));
  LMDJ_CHECK(!added.has_value());
  LMDJ_CHECK(added.error().code == ErrorCode::invalid_argument);
}

void test_v2_registry_rejects_duplicate_port_names() {
  // The Capability Schema cannot express this rule: `uniqueItems` only rejects
  // identical port objects, so two ports sharing a name but differing
  // elsewhere satisfy the Schema. `valid_ports()` is its only enforcer.
  auto ports = multi_input_ports();
  ports[1].name = ports[0].name;
  LMDJ_CHECK(ports[0].schema_id != ports[1].schema_id);

  auto provider = std::make_shared<MultiPortProvider>();
  Registry registry;
  const auto added = registry.add(multi_port_registration(
      provider, ports, multi_output_ports()));
  LMDJ_CHECK(!added.has_value());
  LMDJ_CHECK(added.error().code == ErrorCode::invalid_argument);
}

void test_v2_registry_rejects_non_lowercase_port_names() {
  auto ports = multi_input_ports();
  ports[0].name = "Source";

  auto provider = std::make_shared<MultiPortProvider>();
  Registry registry;
  const auto added = registry.add(multi_port_registration(
      provider, ports, multi_output_ports()));
  LMDJ_CHECK(!added.has_value());
  LMDJ_CHECK(added.error().code == ErrorCode::invalid_argument);
}

void test_v2_request_bindings_fail_closed_before_provider_execution() {
  TempDirectory temp;
  auto provider = std::make_shared<MultiPortProvider>();
  const auto registry = multi_port_registry(provider);
  auto store = store_at(temp.path());
  select_capability(
      store,
      registry,
      std::string(kMultiPortCapability),
      provider->id());

  auto missing_required = multi_port_request();
  missing_required.inputs.erase(missing_required.inputs.begin());
  const auto missing = store.execute(
      AttemptId{"attempt-v2-missing-input"}, missing_required, registry, byte_fixture::options());
  LMDJ_CHECK(missing.has_value());
  LMDJ_CHECK(missing.value().error.has_value());
  LMDJ_CHECK(missing.value().error->code == ErrorCode::invalid_argument);

  auto unknown_port = multi_port_request();
  unknown_port.inputs.front().port = "unknown";
  const auto unknown = store.execute(
      AttemptId{"attempt-v2-unknown-input"}, unknown_port, registry, byte_fixture::options());
  LMDJ_CHECK(unknown.has_value());
  LMDJ_CHECK(unknown.value().error.has_value());
  LMDJ_CHECK(unknown.value().error->code == ErrorCode::invalid_argument);

  auto duplicate_artifact = multi_port_request();
  duplicate_artifact.inputs.front().artifact =
      duplicate_artifact.inputs.back().artifact;
  const auto duplicate = store.execute(
      AttemptId{"attempt-v2-duplicate-input"}, duplicate_artifact, registry, byte_fixture::options());
  LMDJ_CHECK(duplicate.has_value());
  LMDJ_CHECK(duplicate.value().error.has_value());
  LMDJ_CHECK(duplicate.value().error->code == ErrorCode::invalid_argument);

  auto secondary_overflow = multi_port_request();
  secondary_overflow.inputs.push_back(ArtifactBinding{
      "reference",
      ArtifactRef{
          std::string(64, 'c'),
          "application/x-lmdj-proof",
          3,
      },
  });
  const auto overflow = store.execute(
      AttemptId{"attempt-v2-input-overflow"}, secondary_overflow, registry, byte_fixture::options());
  LMDJ_CHECK(overflow.has_value());
  LMDJ_CHECK(overflow.value().error.has_value());
  LMDJ_CHECK(overflow.value().error->code == ErrorCode::invalid_argument);
  LMDJ_CHECK(provider->run_count == 0);
}

void test_v2_output_bindings_are_validated_per_port() {
  TempDirectory temp;
  auto provider = std::make_shared<MultiPortProvider>();
  const auto registry = multi_port_registry(provider);
  auto store = store_at(temp.path());
  select_capability(
      store,
      registry,
      std::string(kMultiPortCapability),
      provider->id());

  provider->mode = MultiPortProvider::Mode::success;
  const auto success = store.execute(
      AttemptId{"attempt-v2-success"}, multi_port_request(), registry, byte_fixture::options());
  LMDJ_CHECK(success.has_value());
  LMDJ_CHECK(success.value().candidate.has_value());
  LMDJ_CHECK(success.value().candidate->outputs.size() == 2);
  LMDJ_CHECK(success.value().candidate->outputs.at(0).port == "secondary");
  LMDJ_CHECK(success.value().candidate->outputs.at(1).port == "primary");
  const auto persisted = read_json(
      temp.path() / ".lmdj-workspace/attempts/attempt-v2-success.json");
  LMDJ_CHECK(persisted.at("format") == "terminal-attempt-v2");
  LMDJ_CHECK(
      persisted.at("capability").at("contract") == "lmdj.capability.v2");
  LMDJ_CHECK(
      persisted.at("request").at("inputs").at(0).at("port") ==
      "reference");
  LMDJ_CHECK(
      persisted.at("request").at("inputs").at(1).at("port") == "source");
  LMDJ_CHECK(persisted.at("minted_outputs").at(0).at("port") == "primary");
  LMDJ_CHECK(
      persisted.at("minted_outputs").at(1).at("port") == "secondary");
  LMDJ_CHECK(
      persisted.at("candidate_outputs") == persisted.at("minted_outputs"));

  const std::vector invalid_modes{
      MultiPortProvider::Mode::missing_required_output,
      MultiPortProvider::Mode::secondary_overflow,
      MultiPortProvider::Mode::unknown_candidate_port,
      MultiPortProvider::Mode::candidate_port_mismatch,
  };
  for (std::size_t index = 0; index < invalid_modes.size(); ++index) {
    provider->mode = invalid_modes.at(index);
    const auto attempt_id =
        "attempt-v2-invalid-output-" + std::to_string(index);
    const auto result = store.execute(
        AttemptId{attempt_id}, multi_port_request(), registry, byte_fixture::options());
    LMDJ_CHECK(result.has_value());
    check_provider_failure(result.value());
    LMDJ_CHECK(!std::filesystem::exists(
        temp.path() / ".lmdj-workspace/attempts" / attempt_id));
  }

  provider->mode = MultiPortProvider::Mode::unknown_sink_port;
  const auto unknown_sink = store.execute(
      AttemptId{"attempt-v2-unknown-sink"}, multi_port_request(), registry, byte_fixture::options());
  LMDJ_CHECK(unknown_sink.has_value());
  check_provider_failure(unknown_sink.value());
  LMDJ_CHECK(provider->unknown_sink_rejected);
  LMDJ_CHECK(!std::filesystem::exists(
      temp.path() /
      ".lmdj-workspace/attempts/attempt-v2-unknown-sink"));

  provider->mode = MultiPortProvider::Mode::duplicate_mint;
  const auto duplicate_mint = store.execute(
      AttemptId{"attempt-v2-duplicate-mint"}, multi_port_request(), registry, byte_fixture::options());
  LMDJ_CHECK(duplicate_mint.has_value());
  check_provider_failure(duplicate_mint.value());
  LMDJ_CHECK(provider->duplicate_mint_rejected);
  LMDJ_CHECK(!std::filesystem::exists(
      temp.path() /
      ".lmdj-workspace/attempts/attempt-v2-duplicate-mint"));
}

void test_v2_all_optional_outputs_allow_empty_candidate() {
  TempDirectory temp;
  auto provider = std::make_shared<MultiPortProvider>();
  provider->mode = MultiPortProvider::Mode::empty_candidate;
  const auto registry = multi_port_registry(provider, false);
  auto store = store_at(temp.path());
  select_capability(
      store,
      registry,
      std::string(kMultiPortCapability),
      provider->id());
  const auto result = store.execute(
      AttemptId{"attempt-v2-empty"}, multi_port_request(), registry, byte_fixture::options());
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value().candidate.has_value());
  LMDJ_CHECK(result.value().candidate->outputs.empty());
  const auto persisted = read_json(
      temp.path() / ".lmdj-workspace/attempts/attempt-v2-empty.json");
  LMDJ_CHECK(persisted.at("minted_outputs").empty());
  LMDJ_CHECK(persisted.at("candidate_outputs").empty());
}

void test_v2_input_order_is_canonical_in_attempt_evidence() {
  TempDirectory temp;
  auto provider = std::make_shared<MultiPortProvider>();
  const auto registry = multi_port_registry(provider);
  auto store = store_at(temp.path());
  select_capability(
      store,
      registry,
      std::string(kMultiPortCapability),
      provider->id());

  auto reversed = multi_port_request();
  auto descriptor_order = multi_port_request();
  std::reverse(descriptor_order.inputs.begin(), descriptor_order.inputs.end());
  const auto first = store.execute(
      AttemptId{"attempt-v2-order-a"}, reversed, registry, byte_fixture::options());
  const auto second = store.execute(
      AttemptId{"attempt-v2-order-b"}, descriptor_order, registry, byte_fixture::options());
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(second.has_value());
  const auto first_json = read_json(
      temp.path() / ".lmdj-workspace/attempts/attempt-v2-order-a.json");
  const auto second_json = read_json(
      temp.path() / ".lmdj-workspace/attempts/attempt-v2-order-b.json");
  LMDJ_CHECK(
      first_json.at("request").at("inputs") ==
      second_json.at("request").at("inputs"));
  LMDJ_CHECK(
      first_json.at("candidate_outputs") ==
      second_json.at("candidate_outputs"));
}

void test_v2_inspection_preserves_and_rejects_v1_attempt_files() {
  TempDirectory temp;
  const auto attempts = temp.path() / ".lmdj-workspace/attempts";
  std::filesystem::create_directories(attempts);
  const auto legacy_path = attempts / "attempt-v1.json";
  const auto legacy = nlohmann::json{
      {"capability", {{"contract", "lmdj.capability.v1"}}},
      {"format", "terminal-attempt"},
  };
  {
    std::ofstream stream(legacy_path, std::ios::binary | std::ios::trunc);
    stream << lmdj::foundation::canonical_json(legacy) << '\n';
  }
  const auto original = read_bytes(legacy_path);
  auto store = store_at(temp.path());
  const auto inspected = store.inspect(AttemptId{"attempt-v1"});
  LMDJ_CHECK(!inspected.has_value());
  LMDJ_CHECK(inspected.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(legacy_path) == original);
}

void test_v2_inspection_rejects_binding_compatibility_shorthands() {
  TempDirectory temp;
  auto registry = proof_registry();
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.success");
  const auto result = store.execute(
      AttemptId{"attempt-v2-extra-binding-key"},
      valid_request(),
      registry, byte_fixture::options());
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value().candidate.has_value());

  const auto path =
      temp.path() /
      ".lmdj-workspace/attempts/attempt-v2-extra-binding-key.json";
  auto encoded = read_json(path);
  encoded["candidate_outputs"][0]["compatibility"] = "forbidden";
  {
    std::ofstream stream(path, std::ios::binary | std::ios::trunc);
    stream << lmdj::foundation::canonical_json(encoded) << '\n';
  }
  const auto inspected =
      store.inspect(AttemptId{"attempt-v2-extra-binding-key"});
  LMDJ_CHECK(!inspected.has_value());
  LMDJ_CHECK(inspected.error().code == ErrorCode::invalid_argument);
}

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
        AttemptId{attempt_id}, valid_request(), registry, byte_fixture::options());
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
      AttemptId{"attempt-invalid-region"}, invalid_region, registry, byte_fixture::options());
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
      registry, byte_fixture::options());
  LMDJ_CHECK(missing_permission_result.has_value());
  LMDJ_CHECK(missing_permission_result.value().error.has_value());
  LMDJ_CHECK(
      missing_permission_result.value().error->code ==
      ErrorCode::permission_denied);
  LMDJ_CHECK(counting->run_count == 0);

  auto invalid_platform = valid_request();
  invalid_platform.platform = "unsupported";
  const auto platform_result = store.execute(
      AttemptId{"attempt-invalid-platform"}, invalid_platform, registry, byte_fixture::options());
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
      registry, byte_fixture::options());
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
      registry, byte_fixture::options());
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
      registry, byte_fixture::options());
  LMDJ_CHECK(permission_result.has_value());
  LMDJ_CHECK(permission_result.value().error.has_value());
  LMDJ_CHECK(
      permission_result.value().error->code == ErrorCode::permission_denied);
  LMDJ_CHECK(counting->run_count == 0);

  auto duplicate_input = valid_request();
  duplicate_input.inputs.push_back(duplicate_input.inputs.front());
  const auto duplicate_result = store.execute(
      AttemptId{"attempt-duplicate-input"}, duplicate_input, registry, byte_fixture::options());
  LMDJ_CHECK(duplicate_result.has_value());
  LMDJ_CHECK(duplicate_result.value().error.has_value());
  LMDJ_CHECK(
      duplicate_result.value().error->code == ErrorCode::invalid_argument);
  LMDJ_CHECK(counting->run_count == 0);

  auto malformed_input = valid_request();
  malformed_input.inputs.front().artifact.sha256 = "../project";
  const auto malformed_result = store.execute(
      AttemptId{"attempt-malformed-input"}, malformed_input, registry, byte_fixture::options());
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
      AttemptId{"attempt-once"}, valid_request(), registry, byte_fixture::options());
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(counting->run_count == 1);
  const auto before = read_bytes(
      temp.path() / ".lmdj-workspace/attempts/attempt-once.json");
  const auto duplicate = store.execute(
      AttemptId{"attempt-once"}, valid_request(), registry, byte_fixture::options());
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
        AttemptId{unsafe_id}, valid_request(), registry, byte_fixture::options());
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
      AttemptId{"attempt-deterministic-a"}, valid_request(), registry, byte_fixture::options());
  const auto second = store.execute(
      AttemptId{"attempt-deterministic-b"}, valid_request(), registry, byte_fixture::options());
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
    test_structured_model_identity_is_preserved_in_attempt_provenance();
    test_failure_provider_records_typed_terminal_attempt();
    test_untrusted_provider_outcomes_are_rejected_as_typed_failures();
    test_policy_and_invalid_requests_fail_closed_before_provider_execution();
    test_duplicate_attempt_and_registration_inputs_are_rejected();
    test_provenance_is_deterministic_across_attempts();
    test_v2_registry_rejects_empty_output_descriptors();
    test_v2_registry_rejects_duplicate_port_names();
    test_v2_registry_rejects_non_lowercase_port_names();
    test_v2_request_bindings_fail_closed_before_provider_execution();
    test_v2_output_bindings_are_validated_per_port();
    test_v2_all_optional_outputs_allow_empty_candidate();
    test_v2_input_order_is_canonical_in_attempt_evidence();
    test_v2_inspection_preserves_and_rejects_v1_attempt_files();
    test_v2_inspection_rejects_binding_compatibility_shorthands();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "provider conformance tests: PASS\n";
  return 0;
}
