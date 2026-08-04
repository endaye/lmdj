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
  if (!value.at("manifest_version").is_number_unsigned() ||
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
  for (const auto key : {
           "emcc_version",
           "emscripten_releases_revision",
           "emsdk_revision",
           "emsdk_tag",
       }) {
    if (!emscripten.at(key).is_string() ||
        emscripten.at(key).get_ref<const std::string&>().empty()) {
      return false;
    }
  }
  for (const auto& asset : value.at("assets")) {
    if (!exact_keys(asset, {"bytes", "path", "role", "sha256"}) ||
        !asset.at("path").is_string() ||
        !asset.at("bytes").is_number_unsigned() ||
        !asset.at("role").is_string() ||
        !asset.at("sha256").is_string() ||
        !lowercase_sha256(asset.at("sha256").get_ref<const std::string&>())) {
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
