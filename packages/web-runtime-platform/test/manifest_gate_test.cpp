#include <lmdj/web_runtime/manifest_gate.hpp>

#include <array>
#include <cstddef>
#include <iostream>
#include <span>
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

constexpr std::array<ManifestExpectation::ComponentIdentity, 2> kAllowedHosts{{
    {"lmdj.creator-web.distribution.v1", "creator-web", "1.0.5"},
    {"lmdj.web-runtime-host.distribution.v1", "web-runtime-host", "1.2.5"},
}};
constexpr ManifestExpectation kExpected{
    "1.0.16.8",
    "0.1.5",
    kAllowedHosts,
    1,
};

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
    std::string_view product = "1.0.16.8",
    std::string_view host = "1.2.5",
    std::uint32_t protocol = 1) {
  return {
      {"distribution_contract", "lmdj.web-runtime-host.distribution.v1"},
      {"manifest_version", 1},
      {"product_build", product},
      {"platform_version", "0.1.5"},
      {"host_id", "web-runtime-host"},
      {"host_version", host},
      {"protocol_version", protocol},
      {"heap_bytes", 536'870'912},
      {"resource_limits",
       {
           {"imported_wav_bytes", 1'048'576},
           {"decoded_frames_per_pad", 240'000},
           {"decoded_float_pcm_bytes_per_bank", 67'108'864},
           {"decoded_float_pcm_bytes_total", 134'217'728},
       }},
      {"emscripten",
       {
           {"emsdk_tag", "6.0.5"},
           {"emsdk_revision", "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190"},
           {"emscripten_releases_revision",
            "dbd755b5da399329c2576f6e3dfa7f419f5d8409"},
           {"emcc_version",
            "emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) "
            "6.0.5 (1db513782be24469589d7cb8a1f1834e9a33f271)"},
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
    std::string_view product = "1.0.16.8",
    std::string_view host = "1.2.5",
    std::uint32_t protocol = 1) {
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
      gate.initialize(as_bytes(manifest), sha256(manifest), kExpected) ==
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
        gate.initialize(as_bytes(manifest), sha256(manifest), kExpected) ==
        ManifestGateStatus::protocol_mismatch);
    LMDJ_CHECK(!gate.begin_runtime());
    LMDJ_CHECK(!gate.ready());
  }
}

void test_digest_and_exact_identity_mismatches_fail_closed() {
  const auto valid = canonical_manifest();
  for (const auto& [manifest, digest] : {
           std::pair{valid, std::string(64, '0')},
           std::pair{canonical_manifest("1.0.34.0"),
                     sha256(canonical_manifest("1.0.34.0"))},
           std::pair{canonical_manifest("1.0.16.8", "1.0.3"),
                     sha256(canonical_manifest("1.0.16.8", "1.0.3"))},
           std::pair{canonical_manifest("1.0.16.8", "1.2.5", 2),
                     sha256(canonical_manifest("1.0.16.8", "1.2.5", 2))},
       }) {
    ManifestGate gate;
    LMDJ_CHECK(
        gate.initialize(as_bytes(manifest), digest, kExpected) ==
        ManifestGateStatus::protocol_mismatch);
    LMDJ_CHECK(!gate.begin_runtime());
  }
}

void test_creator_contract_and_compatibility_inventory_are_bound() {
  auto creator = manifest_json();
  creator["distribution_contract"] = "lmdj.creator-web.distribution.v1";
  creator["host_id"] = "creator-web";
  creator["host_version"] = "1.0.5";
  creator["compatible_hosts"] = nlohmann::json::array({
      {{"host_id", "web-runtime-host"}, {"host_version", "1.2.5"}},
  });
  auto encoded = lmdj::foundation::canonical_json(creator);
  ManifestGate accepted;
  LMDJ_CHECK(
      accepted.initialize(as_bytes(encoded), sha256(encoded), kExpected) ==
      ManifestGateStatus::accepted);

  creator["distribution_contract"] =
      "lmdj.web-runtime-host.distribution.v1";
  check_rejected(creator);
  creator["distribution_contract"] = "lmdj.creator-web.distribution.v1";
  creator["compatible_hosts"][0]["host_version"] = "9.9.9";
  check_rejected(creator);
}

void check_rejected(nlohmann::json manifest) {
  const auto encoded = lmdj::foundation::canonical_json(manifest);
  ManifestGate gate;
  LMDJ_CHECK(
      gate.initialize(as_bytes(encoded), sha256(encoded), kExpected) ==
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
  changed["platform_version"] = "0.2.0";
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
      minimal.initialize(as_bytes(encoded), sha256(encoded), kExpected) ==
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
      maximum.initialize(as_bytes(encoded), sha256(encoded), kExpected) ==
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
        gate.initialize(as_bytes(manifest), digest, kExpected) ==
        ManifestGateStatus::accepted);
    LMDJ_CHECK(
        gate.initialize(as_bytes(manifest), digest, kExpected) ==
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
        gate.initialize(as_bytes(manifest), digest, kExpected) ==
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
