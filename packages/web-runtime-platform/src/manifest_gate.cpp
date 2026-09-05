#include <lmdj/web_runtime/manifest_gate.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <set>
#include <string>

#include <lmdj/foundation/json.hpp>
#include <picosha2.h>


namespace lmdj::web_runtime {
namespace {

using Json = nlohmann::json;
constexpr std::uint64_t kMaximumSafeJsonInteger = 9'007'199'254'740'991ULL;

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

bool safe_identity(std::string_view value) {
  return !value.empty() && value.size() <= 64U &&
         std::all_of(
             value.begin(), value.end(), [](unsigned char character) {
               return std::isalnum(character) != 0 || character == '.' ||
                      character == '_' || character == '-';
             });
}

bool safe_asset_path(std::string_view path, std::string_view digest) {
  if (path.size() < 8U || path.size() > 255U ||
      !path.starts_with("assets/") || path.back() == '/' ||
      path.find("//") != std::string_view::npos ||
      path.find("/../") != std::string_view::npos ||
      path.find("/./") != std::string_view::npos ||
      path.find('\\') != std::string_view::npos) {
    return false;
  }
  if (!std::all_of(
          path.begin(), path.end(), [](unsigned char character) {
            return std::isalnum(character) != 0 || character == '/' ||
                   character == '.' || character == '_' || character == '-';
          })) {
    return false;
  }
  const auto marker = "." + std::string{digest} + ".";
  const auto marker_at = path.find(marker);
  return marker_at != std::string_view::npos &&
         marker_at > std::string_view{"assets/"}.size() &&
         marker_at + marker.size() < path.size() &&
         path.find(marker, marker_at + 1U) == std::string_view::npos;
}

bool valid_compatible_hosts(
    const Json& value,
    std::span<const ManifestExpectation::ComponentIdentity> allowed_hosts,
    std::string_view current_host) {
  if (!value.is_array() || value.empty() || value.size() > 64U) {
    return false;
  }
  std::set<std::pair<std::string, std::string>> identities;
  return std::all_of(value.begin(), value.end(), [&](const auto& item) {
    if (!exact_keys(item, {"host_id", "host_version"}) ||
        !item.at("host_id").is_string() ||
        !item.at("host_version").is_string()) {
      return false;
    }
    const auto& id =
        item.at("host_id").template get_ref<const std::string&>();
    const auto& version =
        item.at("host_version").template get_ref<const std::string&>();
    return id != current_host && safe_identity(id) && safe_identity(version) &&
           identities.emplace(id, version).second &&
           std::any_of(
               allowed_hosts.begin(), allowed_hosts.end(),
               [&](const auto& allowed) {
                 return allowed.id == id && allowed.version == version;
               });
  });
}

bool valid_manifest_shape(const Json& value, ManifestExpectation expected) {
  const auto has_compatible_hosts = value.contains("compatible_hosts");
  const auto exact_root = has_compatible_hosts
      ? exact_keys(
            value,
            {"assets", "compatible_hosts", "distribution_contract",
             "emscripten", "heap_bytes", "host_id", "host_version",
             "manifest_version", "platform_version", "product_build",
             "protocol_version", "resource_limits"})
      : exact_keys(
            value,
            {"assets", "distribution_contract", "emscripten", "heap_bytes",
             "host_id", "host_version", "manifest_version",
             "platform_version", "product_build", "protocol_version",
             "resource_limits"});
  if (!exact_root) {
    return false;
  }
  if (!value.at("distribution_contract").is_string() ||
      !value.at("manifest_version").is_number_unsigned() ||
      value.at("manifest_version") != 1 ||
      !value.at("product_build").is_string() ||
      value.at("product_build") != expected.product_build ||
      !value.at("platform_version").is_string() ||
      value.at("platform_version") != expected.platform_version ||
      !value.at("host_id").is_string() ||
      !value.at("host_version").is_string() ||
      !value.at("protocol_version").is_number_unsigned() ||
      value.at("protocol_version") != expected.protocol_version ||
      !value.at("heap_bytes").is_number_unsigned() ||
      value.at("heap_bytes") != 536'870'912 ||
      !value.at("assets").is_array()) {
    return false;
  }
  const auto& host_id = value.at("host_id").get_ref<const std::string&>();
  const auto& host_version =
      value.at("host_version").get_ref<const std::string&>();
  const auto& distribution_contract =
      value.at("distribution_contract").get_ref<const std::string&>();
  if (!safe_identity(host_id) || !safe_identity(host_version) ||
      !safe_identity(distribution_contract) ||
      expected.allowed_hosts.empty() || expected.allowed_hosts.size() > 64U ||
      !std::any_of(
          expected.allowed_hosts.begin(),
          expected.allowed_hosts.end(),
          [&](const auto& allowed) {
            return allowed.distribution_contract == distribution_contract &&
                   allowed.id == host_id && allowed.version == host_version;
          })) {
    return false;
  }
  if (has_compatible_hosts &&
      !valid_compatible_hosts(
          value.at("compatible_hosts"), expected.allowed_hosts, host_id)) {
    return false;
  }
  const auto& limits = value.at("resource_limits");
  if (!exact_keys(
          limits,
          {
              "decoded_float_pcm_bytes_per_bank",
              "decoded_float_pcm_bytes_resident",
              "decoded_float_pcm_bytes_total",
              "imported_wav_bytes",
              "ingest_channels",
              "ingest_decoded_frames",
              "ingest_source_bytes",
              "perform_recording_frames",
              "perform_recording_queue_batches",
          }) ||
      !limits.at("perform_recording_frames").is_number_unsigned() ||
      limits.at("perform_recording_frames") != 86'400'000 ||
      !limits.at("perform_recording_queue_batches").is_number_unsigned() ||
      limits.at("perform_recording_queue_batches") != 32 ||
      !limits.at("imported_wav_bytes").is_number_unsigned() ||
      limits.at("imported_wav_bytes") != 68'157'440 ||
      !limits.at("decoded_float_pcm_bytes_per_bank").is_number_unsigned() ||
      limits.at("decoded_float_pcm_bytes_per_bank") != 67'108'864 ||
      !limits.at("decoded_float_pcm_bytes_total").is_number_unsigned() ||
      limits.at("decoded_float_pcm_bytes_total") != 134'217'728 ||
      !limits.at("decoded_float_pcm_bytes_resident").is_number_unsigned() ||
      limits.at("decoded_float_pcm_bytes_resident") != 268'435'456 ||
      !limits.at("ingest_source_bytes").is_number_unsigned() ||
      limits.at("ingest_source_bytes") != 104'857'600 ||
      !limits.at("ingest_decoded_frames").is_number_unsigned() ||
      limits.at("ingest_decoded_frames") != 43'200'000 ||
      !limits.at("ingest_channels").is_number_unsigned() ||
      limits.at("ingest_channels") != 2) {
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
  const auto& assets = value.at("assets");
  if (assets.empty() || assets.size() > 64U) {
    return false;
  }
  std::set<std::string> paths;
  std::size_t runtime_scripts = 0;
  std::size_t runtime_wasm = 0;
  std::size_t perform_master_taps = 0;
  for (const auto& asset : assets) {
    if (!exact_keys(asset, {"bytes", "path", "role", "sha256"}) ||
        !asset.at("path").is_string() ||
        !asset.at("bytes").is_number_unsigned() ||
        asset.at("bytes").get<std::uint64_t>() == 0 ||
        asset.at("bytes").get<std::uint64_t>() > kMaximumSafeJsonInteger ||
        !asset.at("role").is_string() ||
        !asset.at("sha256").is_string() ||
        !lowercase_sha256(asset.at("sha256").get_ref<const std::string&>())) {
      return false;
    }
    const auto& path = asset.at("path").get_ref<const std::string&>();
    const auto& digest = asset.at("sha256").get_ref<const std::string&>();
    const auto& role = asset.at("role").get_ref<const std::string&>();
    if (!safe_identity(role) || !safe_asset_path(path, digest) ||
        !paths.insert(path).second) {
      return false;
    }
    runtime_scripts += role == "runtime_script" ? 1U : 0U;
    runtime_wasm += role == "runtime_wasm" ? 1U : 0U;
    perform_master_taps += role == "perform_master_tap_worklet" ? 1U : 0U;
  }
  // Stage 10: the Creator distribution (the manifest that declares
  // compatible_hosts) ships exactly one platform-owned Perform master-tap
  // processor; the Web Runtime Host distribution ships none. A duplicate or a
  // stray entry is an inventory defect, not a tolerated default.
  const auto expected_taps = has_compatible_hosts ? 1U : 0U;
  return runtime_scripts == 1U && runtime_wasm == 1U &&
         perform_master_taps == expected_taps;
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

}  // namespace lmdj::web_runtime
