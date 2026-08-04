#include "manifest_gate.hpp"

#include <cstddef>
#include <iostream>
#include <span>
#include <string>
#include <string_view>

#include <lmdj/foundation/json.hpp>
#include <picosha2.h>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::web_host::ManifestExpectation;
using lmdj::web_host::ManifestGate;
using lmdj::web_host::ManifestGateStatus;

constexpr ManifestExpectation kExpected{
    "1.0.13.0",
    "1.0.0",
    1,
};

std::string canonical_manifest(
    std::string_view product = "1.0.13.0",
    std::string_view host = "1.0.0",
    std::uint32_t protocol = 1) {
  return lmdj::foundation::canonical_json(nlohmann::json{
      {"manifest_version", 1},
      {"product_build", product},
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
           {"emcc_version", "emcc 6.0.5"},
       }},
      {"assets", nlohmann::json::array()},
  });
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
           std::string(lmdj::web_host::kHostManifestMaximumBytes + 1, 'x'),
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
           std::pair{canonical_manifest("1.0.14.0"),
                     sha256(canonical_manifest("1.0.14.0"))},
           std::pair{canonical_manifest("1.0.13.0", "1.0.1"),
                     sha256(canonical_manifest("1.0.13.0", "1.0.1"))},
           std::pair{canonical_manifest("1.0.13.0", "1.0.0", 2),
                     sha256(canonical_manifest("1.0.13.0", "1.0.0", 2))},
       }) {
    ManifestGate gate;
    LMDJ_CHECK(
        gate.initialize(as_bytes(manifest), digest, kExpected) ==
        ManifestGateStatus::protocol_mismatch);
    LMDJ_CHECK(!gate.begin_runtime());
  }
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
    test_repeated_or_late_initialization_is_terminal_before_mutation();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "web manifest gate tests: PASS\n";
  return 0;
}
