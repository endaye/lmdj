#include "manifest_gate.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <string>

#include <lmdj/foundation/json.hpp>
#include <picosha2.h>


namespace lmdj::web_host {
namespace {

using Json = nlohmann::json;

bool exact_keys(
    const Json& value,
    std::initializer_list<std::string_view> keys) {
  if (!value.is_object() || value.size() != keys.size()) {
    return false;
  }
  return std::all_of(keys.begin(), keys.end(), [&value](const auto key) {
    return value.contains(std::string(key));
  });
}

bool lowercase_sha256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(value.begin(), value.end(), [](const char character) {
           return (character >= '0' && character <= '9') ||
                  (character >= 'a' && character <= 'f');
         });
}

bool valid_manifest_shape(const Json& value, ManifestExpectation expected) {
  if (!exact_keys(
          value,
          {
              "assets",
              "distribution_contract",
              "emscripten",
              "heap_bytes",
              "host_version",
              "manifest_version",
              "product_build",
              "protocol_version",
              "resource_limits",
          })) {
    return false;
  }
  if (!value.at("distribution_contract").is_string() ||
      value.at("distribution_contract") !=
          "lmdj.web-runtime-host.distribution.v1" ||
      !value.at("manifest_version").is_number_unsigned() ||
      value.at("manifest_version") != 1 ||
      !value.at("product_build").is_string() ||
      value.at("product_build") != expected.product_build ||
      !value.at("host_version").is_string() ||
      value.at("host_version") != expected.host_version ||
      !value.at("protocol_version").is_number_unsigned() ||
      value.at("protocol_version") != expected.protocol_version ||
      !value.at("heap_bytes").is_number_unsigned() ||
      value.at("heap_bytes") != 536'870'912 ||
      !value.at("assets").is_array()) {
    return false;
  }
  const auto& limits = value.at("resource_limits");
  if (!exact_keys(
          limits,
          {
              "decoded_float_pcm_bytes_per_bank",
              "decoded_float_pcm_bytes_total",
              "decoded_frames_per_pad",
              "imported_wav_bytes",
          }) ||
      !limits.at("imported_wav_bytes").is_number_unsigned() ||
      limits.at("imported_wav_bytes") != 1'048'576 ||
      !limits.at("decoded_frames_per_pad").is_number_unsigned() ||
      limits.at("decoded_frames_per_pad") != 240'000 ||
      !limits.at("decoded_float_pcm_bytes_per_bank").is_number_unsigned() ||
      limits.at("decoded_float_pcm_bytes_per_bank") != 67'108'864 ||
      !limits.at("decoded_float_pcm_bytes_total").is_number_unsigned() ||
      limits.at("decoded_float_pcm_bytes_total") != 134'217'728) {
    return false;
  }
  const auto& emscripten = value.at("emscripten");
  if (!exact_keys(
          emscripten,
          {
              "emcc_version",
              "emscripten_releases_revision",
              "emsdk_revision",
              "emsdk_tag",
          })) {
    return false;
  }
  if (emscripten.at("emsdk_tag") != "6.0.5" ||
      emscripten.at("emsdk_revision") !=
          "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190" ||
      emscripten.at("emscripten_releases_revision") !=
          "dbd755b5da399329c2576f6e3dfa7f419f5d8409" ||
      emscripten.at("emcc_version") !=
          "emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) "
          "6.0.5 (1db513782be24469589d7cb8a1f1834e9a33f271)") {
    return false;
  }
  struct ExpectedAsset {
    std::string_view prefix;
    std::string_view suffix;
    std::string_view role;
  };
  static constexpr std::array<ExpectedAsset, 9> expected_assets{{
      {"assets/diagnostic-project.", ".mjs", "host_module"},
      {"assets/input-adapters.", ".mjs", "host_module"},
      {"assets/main.", ".mjs", "host_main"},
      {"assets/preflight.", ".mjs", "host_module"},
      {"assets/protocol.", ".mjs", "host_module"},
      {"assets/runtime.", ".js", "runtime_script"},
      {"assets/runtime.", ".wasm", "runtime_wasm"},
      {"assets/state-machine.", ".mjs", "host_module"},
      {"assets/styles.", ".css", "host_style"},
  }};
  const auto& assets = value.at("assets");
  if (assets.size() != expected_assets.size()) {
    return false;
  }
  for (std::size_t index = 0; index < assets.size(); ++index) {
    const auto& asset = assets.at(index);
    const auto expected_asset = expected_assets.at(index);
    if (!exact_keys(asset, {"bytes", "path", "role", "sha256"}) ||
        !asset.at("path").is_string() ||
        !asset.at("bytes").is_number_unsigned() ||
        asset.at("bytes").get<std::uint64_t>() == 0 ||
        !asset.at("role").is_string() ||
        !asset.at("sha256").is_string() ||
        !lowercase_sha256(asset.at("sha256").get_ref<const std::string&>())) {
      return false;
    }
    const auto& path = asset.at("path").get_ref<const std::string&>();
    const auto& digest = asset.at("sha256").get_ref<const std::string&>();
    if (asset.at("role") != expected_asset.role ||
        path != std::string(expected_asset.prefix) + digest +
                    std::string(expected_asset.suffix)) {
      return false;
    }
  }
  return true;
}

}  // namespace

ManifestGateStatus ManifestGate::initialize(
    std::span<const std::byte> canonical_bytes,
    std::string_view expected_sha256,
    ManifestExpectation expected) noexcept {
  std::lock_guard lock(mutex_);
  if (phase_ != Phase::awaiting_manifest) {
    phase_ = Phase::rejected;
    return ManifestGateStatus::protocol_mismatch;
  }
  phase_ = Phase::rejected;
  if (canonical_bytes.empty() ||
      canonical_bytes.size() > kHostManifestMaximumBytes ||
      !lowercase_sha256(expected_sha256)) {
    return ManifestGateStatus::protocol_mismatch;
  }
  try {
    const std::string_view bytes(
        reinterpret_cast<const char*>(canonical_bytes.data()),
        canonical_bytes.size());
    if (!foundation::valid_utf8(bytes)) {
      return ManifestGateStatus::protocol_mismatch;
    }
    const auto parsed = foundation::parse_bounded_json(bytes);
    if (!parsed.has_value() || foundation::canonical_json(*parsed) != bytes ||
        !valid_manifest_shape(*parsed, expected)) {
      return ManifestGateStatus::protocol_mismatch;
    }
    const auto digest = picosha2::hash256_hex_string(bytes.begin(), bytes.end());
    if (digest != expected_sha256) {
      return ManifestGateStatus::protocol_mismatch;
    }
    phase_ = Phase::accepted;
    return ManifestGateStatus::accepted;
  } catch (...) {
    return ManifestGateStatus::protocol_mismatch;
  }
}

bool ManifestGate::begin_runtime() noexcept {
  std::lock_guard lock(mutex_);
  if (phase_ != Phase::accepted) {
    phase_ = Phase::rejected;
    return false;
  }
  phase_ = Phase::running;
  return true;
}

bool ManifestGate::ready() const noexcept {
  std::lock_guard lock(mutex_);
  return phase_ == Phase::accepted || phase_ == Phase::running;
}

}  // namespace lmdj::web_host
