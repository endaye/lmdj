#include <lmdj/web_runtime/manifest_gate.hpp>

#include <array>
#include <cstddef>
#include <fstream>
#include <iostream>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <lmdj/foundation/json.hpp>
#include <picosha2.h>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::web_runtime::ManifestExpectation;
using lmdj::web_runtime::ManifestGate;
using lmdj::web_runtime::ManifestGateStatus;

#if !defined(LMDJ_WEB_RUNTIME_IDENTITY_PATH)
#error "Web Runtime identity fixture path is required"
#endif

const nlohmann::json& runtime_identity() {
  static const auto identity = [] {
    std::ifstream input(LMDJ_WEB_RUNTIME_IDENTITY_PATH);
    if (!input) {
      throw std::runtime_error("generated Web Runtime identity is unavailable");
    }
    const auto parsed = lmdj::foundation::parse_bounded_json(input);
    if (!parsed.has_value()) {
      throw std::runtime_error("generated Web Runtime identity is invalid");
    }
    return *parsed;
  }();
  return identity;
}

const nlohmann::json& host_identity(std::string_view id) {
  return runtime_identity().at("hosts").at(id);
}

ManifestExpectation expected() {
  static const std::array identities{
      ManifestExpectation::ComponentIdentity{
          host_identity("creator-web").at("distribution_contract")
              .get_ref<const std::string&>(),
          host_identity("creator-web").at("id").get_ref<const std::string&>(),
          host_identity("creator-web").at("version")
              .get_ref<const std::string&>()},
      ManifestExpectation::ComponentIdentity{
          host_identity("web-runtime-host").at("distribution_contract")
              .get_ref<const std::string&>(),
          host_identity("web-runtime-host").at("id")
              .get_ref<const std::string&>(),
          host_identity("web-runtime-host").at("version")
              .get_ref<const std::string&>()},
  };
  const auto& identity = runtime_identity();
  return {
      identity.at("product_build").get_ref<const std::string&>(),
      identity.at("platform").at("version").get_ref<const std::string&>(),
      identities,
      identity.at("protocol_version").get<std::uint32_t>(),
  };
}

std::string repeated(char value) {
  return std::string(64, value);
}

nlohmann::json asset(
    std::string_view stem,
    char digest_character,
    std::string_view suffix,
    std::string_view role) {
  const auto digest = repeated(digest_character);
  return {
      {"path", "assets/" + std::string(stem) + "." + digest + std::string(suffix)},
      {"bytes", static_cast<int>(digest_character)},
      {"sha256", digest},
      {"role", role},
  };
}

nlohmann::json manifest_json(
    std::string_view product = {},
    std::string_view host = {},
    std::uint32_t protocol = 0) {
  const auto& identity = runtime_identity();
  const auto& runtime_host = host_identity("web-runtime-host");
  if (product.empty()) {
    product = identity.at("product_build").get_ref<const std::string&>();
  }
  if (host.empty()) {
    host = runtime_host.at("version").get_ref<const std::string&>();
  }
  if (protocol == 0) {
    protocol = identity.at("protocol_version").get<std::uint32_t>();
  }
  const auto& emscripten = identity.at("emscripten");
  return {
      {"distribution_contract", runtime_host.at("distribution_contract")},
      {"manifest_version", 1},
      {"product_build", product},
      {"platform_version", identity.at("platform").at("version")},
      {"host_id", runtime_host.at("id")},
      {"host_version", host},
      {"protocol_version", protocol},
      {"heap_bytes", identity.at("heap_bytes")},
      {"resource_limits", identity.at("resource_limits")},
      {"emscripten",
       {
           {"emsdk_tag", emscripten.at("emsdk_tag")},
           {"emsdk_revision", emscripten.at("emsdk_revision")},
           {"emscripten_releases_revision",
            emscripten.at("emscripten_releases_revision")},
           {"emcc_version", emscripten.at("emcc_version")},
       }},
      {"assets",
       nlohmann::json::array({
           asset("diagnostic-project", '0', ".mjs", "host_module"),
           asset("input-adapters", '1', ".mjs", "host_module"),
           asset("main", '2', ".mjs", "host_main"),
           asset("preflight", '3', ".mjs", "host_module"),
           asset("protocol", '4', ".mjs", "host_module"),
           asset("runtime", '5', ".js", "runtime_script"),
           asset("runtime", '6', ".wasm", "runtime_wasm"),
           asset("state-machine", '7', ".mjs", "host_module"),
           asset("styles", '8', ".css", "host_style"),
       })},
  };
}

std::string canonical_manifest(
    std::string_view product = {},
    std::string_view host = {},
    std::uint32_t protocol = 0) {
  return lmdj::foundation::canonical_json(
      manifest_json(product, host, protocol));
}

std::string sha256(std::string_view bytes) {
  return picosha2::hash256_hex_string(bytes.begin(), bytes.end());
}

std::span<const std::byte> as_bytes(std::string_view value) {
  return {
      reinterpret_cast<const std::byte*>(value.data()),
      value.size(),
  };
}

void check_rejected(nlohmann::json manifest);

void test_accepts_once_before_runtime_creation() {
  ManifestGate gate;
  const auto manifest = canonical_manifest();
  LMDJ_CHECK(
      gate.initialize(as_bytes(manifest), sha256(manifest), expected()) ==
      ManifestGateStatus::accepted);
  LMDJ_CHECK(gate.begin_runtime());
  LMDJ_CHECK(gate.ready());
}

void test_missing_malformed_oversized_and_noncanonical_fail_closed() {
  for (const auto& manifest : {
           std::string{},
           std::string{"{"},
           std::string{" "} + canonical_manifest(),
           std::string(lmdj::web_runtime::kHostManifestMaximumBytes + 1, 'x'),
       }) {
    ManifestGate gate;
    LMDJ_CHECK(
        gate.initialize(as_bytes(manifest), sha256(manifest), expected()) ==
        ManifestGateStatus::protocol_mismatch);
    LMDJ_CHECK(!gate.begin_runtime());
    LMDJ_CHECK(!gate.ready());
  }
}

void test_digest_and_exact_identity_mismatches_fail_closed() {
  const auto valid = canonical_manifest();
  const auto configuration = expected();
  const auto runtime_host_version = host_identity("web-runtime-host")
                                        .at("version")
                                        .get_ref<const std::string&>();
  for (const auto& [manifest, digest] : {
           std::pair{valid, std::string(64, '0')},
           // A synthetic, never-allocated Product Build: any manifest naming
           // a build other than the expected one is a mismatch.
           std::pair{canonical_manifest("999.0.0.0"),
                     sha256(canonical_manifest("999.0.0.0"))},
           std::pair{canonical_manifest(configuration.product_build, "1.0.3"),
                     sha256(canonical_manifest(
                         configuration.product_build, "1.0.3"))},
           std::pair{canonical_manifest(
                         configuration.product_build,
                         runtime_host_version,
                         configuration.protocol_version + 1),
                     sha256(canonical_manifest(
                         configuration.product_build,
                         runtime_host_version,
                         configuration.protocol_version + 1))},
       }) {
    ManifestGate gate;
    LMDJ_CHECK(
        gate.initialize(as_bytes(manifest), digest, expected()) ==
        ManifestGateStatus::protocol_mismatch);
    LMDJ_CHECK(!gate.begin_runtime());
  }
}

void test_creator_contract_and_compatibility_inventory_are_bound() {
  auto creator = manifest_json();
  const auto& creator_host = host_identity("creator-web");
  const auto& runtime_host = host_identity("web-runtime-host");
  creator["distribution_contract"] = creator_host.at("distribution_contract");
  creator["host_id"] = creator_host.at("id");
  creator["host_version"] = creator_host.at("version");
  creator["compatible_hosts"] = nlohmann::json::array({
      {{"host_id", runtime_host.at("id")},
       {"host_version", runtime_host.at("version")}},
  });
  auto encoded = lmdj::foundation::canonical_json(creator);
  ManifestGate accepted;
  LMDJ_CHECK(
      accepted.initialize(as_bytes(encoded), sha256(encoded), expected()) ==
      ManifestGateStatus::accepted);

  creator["distribution_contract"] = runtime_host.at("distribution_contract");
  check_rejected(creator);
  creator["distribution_contract"] = creator_host.at("distribution_contract");
  creator["compatible_hosts"][0]["host_version"] = "9.9.9";
  check_rejected(creator);
}

void check_rejected(nlohmann::json manifest) {
  const auto encoded = lmdj::foundation::canonical_json(manifest);
  ManifestGate gate;
  LMDJ_CHECK(
      gate.initialize(as_bytes(encoded), sha256(encoded), expected()) ==
      ManifestGateStatus::protocol_mismatch);
  LMDJ_CHECK(!gate.begin_runtime());
  LMDJ_CHECK(!gate.ready());
}

void test_every_identity_schema_and_inventory_drift_fails_closed() {
  std::vector<nlohmann::json> invalid;

  auto changed = manifest_json();
  changed["unexpected"] = true;
  invalid.push_back(changed);
  changed = manifest_json();
  changed["distribution_contract"] = "other";
  invalid.push_back(changed);
  changed = manifest_json();
  changed["manifest_version"] = 2;
  invalid.push_back(changed);
  changed = manifest_json();
  changed["platform_version"] = "9.9.9";
  invalid.push_back(changed);
  changed = manifest_json();
  changed["host_id"] = "creator-web";
  invalid.push_back(changed);
  changed = manifest_json();
  changed["heap_bytes"] = 1;
  invalid.push_back(changed);
  changed = manifest_json();
  changed["resource_limits"]["imported_wav_bytes"] = 1;
  invalid.push_back(changed);
  changed = manifest_json();
  changed["emscripten"]["emsdk_tag"] = "latest";
  invalid.push_back(changed);
  changed = manifest_json();
  changed["emscripten"]["emsdk_revision"] = repeated('a');
  invalid.push_back(changed);
  changed = manifest_json();
  changed["emscripten"]["emscripten_releases_revision"] = repeated('b');
  invalid.push_back(changed);
  changed = manifest_json();
  changed["emscripten"]["emcc_version"] = "emcc 6.0.5";
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"] = nlohmann::json::array();
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"].erase(changed["assets"].begin() + 5);
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"].push_back(changed["assets"].front());
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"][1]["path"] = changed["assets"][0]["path"];
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"][0]["path"] = "assets/../escape.js";
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"][0]["bytes"] = 0;
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"][0]["bytes"] = 9'007'199'254'740'992ULL;
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"][0]["sha256"] = repeated('f');
  invalid.push_back(changed);
  changed = manifest_json();
  changed["assets"][0]["extra"] = true;
  invalid.push_back(changed);

  for (auto& manifest : invalid) {
    check_rejected(std::move(manifest));
  }
}

void test_generic_bounded_inventory_accepts_host_owned_assets() {
  auto manifest = manifest_json();
  manifest["assets"] = nlohmann::json::array({
      asset("runtime", '5', ".js", "runtime_script"),
      asset("runtime", '6', ".wasm", "runtime_wasm"),
  });
  auto encoded = lmdj::foundation::canonical_json(manifest);
  ManifestGate minimal;
  LMDJ_CHECK(
      minimal.initialize(as_bytes(encoded), sha256(encoded), expected()) ==
      ManifestGateStatus::accepted);

  for (std::size_t index = 0; index < 62; ++index) {
    manifest["assets"].push_back(
        asset(
            "module-" + std::to_string(index),
            'a',
            ".mjs",
            "host_module"));
  }
  encoded = lmdj::foundation::canonical_json(manifest);
  ManifestGate maximum;
  LMDJ_CHECK(
      maximum.initialize(as_bytes(encoded), sha256(encoded), expected()) ==
      ManifestGateStatus::accepted);

  manifest["assets"].push_back(
      asset("overflow", 'b', ".mjs", "host_module"));
  check_rejected(std::move(manifest));
}

void test_repeated_or_late_initialization_is_terminal_before_mutation() {
  const auto manifest = canonical_manifest();
  const auto digest = sha256(manifest);
  {
    ManifestGate gate;
    LMDJ_CHECK(
        gate.initialize(as_bytes(manifest), digest, expected()) ==
        ManifestGateStatus::accepted);
    LMDJ_CHECK(
        gate.initialize(as_bytes(manifest), digest, expected()) ==
        ManifestGateStatus::protocol_mismatch);
    int mutation_calls = 0;
    if (gate.begin_runtime()) {
      ++mutation_calls;
    }
    LMDJ_CHECK(mutation_calls == 0);
  }
  {
    ManifestGate gate;
    LMDJ_CHECK(!gate.begin_runtime());
    LMDJ_CHECK(
        gate.initialize(as_bytes(manifest), digest, expected()) ==
        ManifestGateStatus::protocol_mismatch);
    LMDJ_CHECK(!gate.begin_runtime());
  }
}

}  // namespace

int main() {
  try {
    test_accepts_once_before_runtime_creation();
    test_missing_malformed_oversized_and_noncanonical_fail_closed();
    test_digest_and_exact_identity_mismatches_fail_closed();
    test_every_identity_schema_and_inventory_drift_fails_closed();
    test_generic_bounded_inventory_accepts_host_owned_assets();
    test_creator_contract_and_compatibility_inventory_are_bound();
    test_repeated_or_late_initialization_is_terminal_before_mutation();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "web manifest gate tests: PASS\n";
  return 0;
}
