#include <lmdj/facade/assembly_loader.hpp>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>
#include <lmdj/provider/registry.hpp>
#include "tests/core/support/test.hpp"

namespace {

using lmdj::facade::CompiledAssemblyCatalog;
using lmdj::facade::CompiledComponent;
using lmdj::facade::CompiledProvider;
using lmdj::foundation::AttemptId;
using lmdj::provider::ArtifactSink;
using lmdj::provider::AttemptResult;
using lmdj::provider::CapabilityDescriptor;
using lmdj::provider::CapabilityRequest;
using lmdj::provider::ModelIdentity;
using lmdj::provider::Provider;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::ProviderRegistration;

class TemporaryDirectory {
 public:
  TemporaryDirectory() {
    const auto root = std::filesystem::temp_directory_path();
    for (int attempt = 0; attempt < 100; ++attempt) {
      path_ = root / (
          "lmdj-assembly-loader-" + std::to_string(std::rand()) + "-" +
          std::to_string(attempt));
      std::error_code error;
      if (std::filesystem::create_directory(path_, error)) {
        return;
      }
    }
    throw std::runtime_error("unable to create temporary directory");
  }

  ~TemporaryDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

class ProofProvider final : public Provider {
 public:
  explicit ProofProvider(std::string provider_id)
      : provider_id_(std::move(provider_id)) {}

  std::string id() const override { return provider_id_; }

  std::vector<std::string> capabilities() const override {
    return {"proof.candidate.v2"};
  }

  AttemptResult run(
      AttemptId attempt_id,
      const CapabilityRequest&,
      ArtifactSink) override {
    return AttemptResult{
        std::move(attempt_id),
        std::nullopt,
        lmdj::foundation::Error{
            lmdj::foundation::ErrorCode::provider_failed,
            "not executed by assembly loader tests",
        },
    };
  }

 private:
  std::string provider_id_;
};

CapabilityDescriptor proof_capability() {
  return CapabilityDescriptor{
      "proof.candidate.v2",
      "2.0.0",
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
  };
}

ProviderRegistration registration(
    std::string id,
    std::optional<ModelIdentity> model_identity = std::nullopt) {
  return ProviderRegistration{
      std::make_shared<ProofProvider>(std::move(id)),
      "1.0.1",
      std::string(64, 'a'),
      std::move(model_identity),
      {proof_capability()},
  };
}

std::optional<ModelIdentity> declared_model_identity(
    const nlohmann::json& provider) {
  const auto& model = provider.at("model_identity");
  if (model.is_null()) {
    return std::nullopt;
  }
  return ModelIdentity{
      model.at("id").get<std::string>(),
      model.at("version").get<std::string>(),
      model.at("artifact_sha256").get<std::string>(),
  };
}

std::vector<CompiledComponent> components(
    const nlohmann::json& assembly,
    const char* field) {
  std::vector<CompiledComponent> values;
  for (const auto& component : assembly.at(field)) {
    values.push_back(CompiledComponent{
        component.at("id").get<std::string>(),
        component.at("version").get<std::string>(),
    });
  }
  return values;
}

CompiledAssemblyCatalog catalog(const nlohmann::json& assembly) {
  const auto success_model =
      declared_model_identity(assembly.at("providers").at(0));
  const auto failure_model =
      declared_model_identity(assembly.at("providers").at(1));
  return CompiledAssemblyCatalog{
      "lmdj",
      "1.0.12.0",
      "17cc4b06a4e074448a6cdfb3177f4564134197a45eb5affc6b8697909b934ae4",
      components(assembly, "modules"),
      components(assembly, "hosts"),
      components(assembly, "contracts"),
      {
          CompiledProvider{
              "local.proof.success",
              "1.0.1",
              [success_model] {
                return registration(
                    "local.proof.success", success_model);
              },
              success_model,
          },
          CompiledProvider{
              "local.proof.failure",
              "1.0.1",
              [failure_model] {
                return registration(
                    "local.proof.failure", failure_model);
              },
              failure_model,
          },
      },
  };
}

nlohmann::json read_json(const std::filesystem::path& path) {
  std::ifstream input(path);
  LMDJ_CHECK(input.good());
  nlohmann::json value;
  input >> value;
  return value;
}

void write_json(
    const std::filesystem::path& path,
    const nlohmann::json& value) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  LMDJ_CHECK(output.good());
  output << value.dump(2) << '\n';
  LMDJ_CHECK(output.good());
}

void success_and_filtering() {
  const auto assembly_path =
      std::filesystem::absolute("products/lmdj/assembly.json");
  const auto schema_path = std::filesystem::absolute(
      "contracts/assembly/lmdj.assembly.v2.schema.json");
  const auto assembly = read_json(assembly_path);
  const auto compiled = catalog(assembly);

  auto loaded =
      lmdj::facade::load_assembly(assembly_path, schema_path, compiled);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value().providers->list().size() == 2);
  LMDJ_CHECK(loaded.value().provider_policy.allowed_regions ==
             std::vector<std::string>{"local"});
  LMDJ_CHECK(
      loaded.value().provider_policy.allowed_data_classifications ==
      std::vector<std::string>{"public"});
  LMDJ_CHECK(
      loaded.value().provider_policy.granted_permissions ==
      std::vector<std::string>{"proof.execute"});

  TemporaryDirectory temp;
  auto alternate_policy = assembly;
  alternate_policy["provider_policy"]["allowed_regions"] =
      nlohmann::json::array({"edge"});
  const auto alternate_policy_path = temp.path() / "alternate-policy.json";
  write_json(alternate_policy_path, alternate_policy);
  loaded = lmdj::facade::load_assembly(
      alternate_policy_path, schema_path, compiled);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(
      loaded.value().provider_policy.allowed_regions ==
      std::vector<std::string>{"edge"});

  auto filtered = assembly;
  filtered["providers"].erase(filtered["providers"].begin() + 1);
  const auto filtered_path = temp.path() / "filtered.json";
  write_json(filtered_path, filtered);
  loaded =
      lmdj::facade::load_assembly(filtered_path, schema_path, compiled);
  LMDJ_CHECK(loaded.has_value());
  const auto providers = loaded.value().providers->list();
  LMDJ_CHECK(providers.size() == 1);
  LMDJ_CHECK(providers.front().id == "local.proof.success");
}

void rejects_invalid_and_unavailable_components() {
  const auto assembly_path =
      std::filesystem::absolute("products/lmdj/assembly.json");
  const auto schema_path = std::filesystem::absolute(
      "contracts/assembly/lmdj.assembly.v2.schema.json");
  const auto assembly = read_json(assembly_path);
  const auto compiled = catalog(assembly);
  TemporaryDirectory temp;

  const auto expect_failure = [&](nlohmann::json value, const char* name) {
    const auto path = temp.path() / (std::string(name) + ".json");
    write_json(path, value);
    const auto loaded =
        lmdj::facade::load_assembly(path, schema_path, compiled);
    LMDJ_CHECK(!loaded.has_value());
    LMDJ_CHECK(
        loaded.error().code ==
        lmdj::foundation::ErrorCode::invalid_argument);
  };

  auto value = assembly;
  value["unknown"] = true;
  expect_failure(value, "additional-property");

  value = assembly;
  value["product"]["version"] = "1.0.7.0";
  expect_failure(value, "product-version");

  value = assembly;
  value["modules"][0]["id"] = "unknown-module";
  expect_failure(value, "unknown-module");

  value = assembly;
  value["contracts"].erase(value["contracts"].begin());
  expect_failure(value, "missing-contract");

  value = assembly;
  value["providers"][0]["id"] = "unknown.provider";
  expect_failure(value, "unknown-provider");

  value = assembly;
  value["providers"][0]["capabilities"][0]["version"] = "1.0.0";
  expect_failure(value, "capability-version");

  auto model_assembly = assembly;
  model_assembly["providers"][0]["model_identity"] = {
      {"id", "proof.model"},
      {"version", "weights-v1"},
      {"artifact_sha256", std::string(64, 'b')},
  };
  const auto model_catalog = catalog(model_assembly);
  const auto model_path = temp.path() / "model.json";
  write_json(model_path, model_assembly);
  auto model_loaded = lmdj::facade::load_assembly(
      model_path, schema_path, model_catalog);
  LMDJ_CHECK(model_loaded.has_value());

  model_assembly["providers"][0]["model_identity"]["version"] =
      "weights-v2";
  const auto mismatched_model_path =
      temp.path() / "mismatched-model-version.json";
  write_json(mismatched_model_path, model_assembly);
  model_loaded = lmdj::facade::load_assembly(
      mismatched_model_path, schema_path, model_catalog);
  LMDJ_CHECK(!model_loaded.has_value());

  model_assembly["providers"][0]["model_identity"]["version"] =
      "weights-v1";
  model_assembly["providers"][0]["model_identity"]["artifact_sha256"] =
      std::string(64, 'c');
  const auto mismatched_model_artifact_path =
      temp.path() / "mismatched-model-artifact.json";
  write_json(mismatched_model_artifact_path, model_assembly);
  model_loaded = lmdj::facade::load_assembly(
      mismatched_model_artifact_path, schema_path, model_catalog);
  LMDJ_CHECK(!model_loaded.has_value());

  auto mismatched_registration_catalog = model_catalog;
  auto mismatched_registration_model =
      *mismatched_registration_catalog.providers[0].model_identity;
  mismatched_registration_model.version = "weights-v2";
  mismatched_registration_catalog.providers[0].factory =
      [mismatched_registration_model] {
        return registration(
            "local.proof.success", mismatched_registration_model);
      };
  model_loaded = lmdj::facade::load_assembly(
      model_path, schema_path, mismatched_registration_catalog);
  LMDJ_CHECK(!model_loaded.has_value());

  mismatched_registration_model.version = "weights-v1";
  mismatched_registration_model.artifact_sha256 = std::string(64, 'c');
  mismatched_registration_catalog.providers[0].factory =
      [mismatched_registration_model] {
        return registration(
            "local.proof.success", mismatched_registration_model);
      };
  model_loaded = lmdj::facade::load_assembly(
      model_path, schema_path, mismatched_registration_catalog);
  LMDJ_CHECK(!model_loaded.has_value());

  value = assembly;
  value["provider_policy"]["allowed_regions"] =
      nlohmann::json::array({"local", "local"});
  expect_failure(value, "duplicate-policy-region");

  const auto missing_schema = lmdj::facade::load_assembly(
      assembly_path,
      temp.path() / "missing-schema.json",
      compiled);
  LMDJ_CHECK(!missing_schema.has_value());

  auto altered_schema = read_json(schema_path);
  altered_schema["title"] = "Altered Assembly Schema";
  const auto altered_schema_path = temp.path() / "altered-schema.json";
  write_json(altered_schema_path, altered_schema);
  const auto altered = lmdj::facade::load_assembly(
      assembly_path,
      altered_schema_path,
      compiled);
  LMDJ_CHECK(!altered.has_value());
}

}  // namespace

int main() {
  success_and_filtering();
  rejects_invalid_and_unavailable_components();
  return 0;
}
