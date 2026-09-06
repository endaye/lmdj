#include <lmdj/foundation/soundset_manifest.hpp>

#include <algorithm>
#include <cctype>
#include <initializer_list>
#include <regex>
#include <string_view>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/json.hpp>

namespace lmdj::foundation {
namespace {

constexpr std::string_view kReasonManifest = "soundset_manifest_invalid";
constexpr std::string_view kReasonSlot = "soundset_slot_invalid";
constexpr std::string_view kReasonLicense = "soundset_license_ineligible";

const std::regex kUuid{
    "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    std::regex::optimize};
const std::regex kSemver{
    "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
    std::regex::optimize};
const std::regex kSha256{"^[0-9a-f]{64}$", std::regex::optimize};

Error fail(
    ErrorCode code,
    std::string_view reason,
    std::string message) {
  return Error{
      code,
      std::string(message),
      {{"reason", reason}},
  };
}

Error manifest_invalid(std::string message) {
  return fail(ErrorCode::invalid_argument, kReasonManifest, std::move(message));
}

Error slot_invalid(std::string message) {
  return fail(ErrorCode::invalid_argument, kReasonSlot, std::move(message));
}

Error license_ineligible(std::string message) {
  return fail(ErrorCode::permission_denied, kReasonLicense, std::move(message));
}

bool exact_object_keys(
    const nlohmann::json& input,
    std::initializer_list<std::string_view> keys) {
  if (!input.is_object() || input.size() != keys.size()) {
    return false;
  }
  return std::all_of(keys.begin(), keys.end(), [&input](std::string_view key) {
    return input.contains(key);
  });
}

bool has_only_keys(
    const nlohmann::json& input,
    std::initializer_list<std::string_view> required,
    std::initializer_list<std::string_view> optional) {
  if (!input.is_object()) {
    return false;
  }
  for (const auto& key : required) {
    if (!input.contains(key)) {
      return false;
    }
  }
  for (auto iterator = input.begin(); iterator != input.end(); ++iterator) {
    const auto& key = iterator.key();
    const bool allowed =
        std::any_of(
            required.begin(),
            required.end(),
            [&key](std::string_view candidate) { return candidate == key; }) ||
        std::any_of(
            optional.begin(),
            optional.end(),
            [&key](std::string_view candidate) { return candidate == key; });
    if (!allowed) {
      return false;
    }
  }
  return true;
}

bool is_nonempty_string(const nlohmann::json& value) {
  return value.is_string() && !value.get_ref<const std::string&>().empty();
}

bool is_string(const nlohmann::json& value) {
  return value.is_string();
}

std::optional<int> optional_bpm(const nlohmann::json& object, const char* key) {
  if (!object.contains(key)) {
    return std::nullopt;
  }
  const auto& value = object[key];
  if (!value.is_number_integer()) {
    return std::nullopt;
  }
  const auto bpm = value.get<int>();
  if (bpm < 40 || bpm > 240) {
    return std::nullopt;
  }
  return bpm;
}

bool known_role(std::string_view role) {
  return std::any_of(
      kSoundSetRoles.begin(),
      kSoundSetRoles.end(),
      [role](std::string_view allowed) { return allowed == role; });
}

Result<ArtifactRef> parse_artifact(const nlohmann::json& input) {
  if (!exact_object_keys(input, {"sha256", "media_type", "byte_length"})) {
    return Result<ArtifactRef>::failure(
        manifest_invalid("artifact ref keys must be sha256, media_type, byte_length"));
  }
  if (!input["sha256"].is_string() ||
      !std::regex_match(
          input["sha256"].get_ref<const std::string&>(), kSha256)) {
    return Result<ArtifactRef>::failure(
        manifest_invalid("artifact sha256 must be 64 lowercase hex characters"));
  }
  if (!is_nonempty_string(input["media_type"])) {
    return Result<ArtifactRef>::failure(
        manifest_invalid("artifact media_type must be a non-empty string"));
  }
  if (!input["byte_length"].is_number_unsigned() ||
      input["byte_length"].get<std::uint64_t>() < 1U) {
    return Result<ArtifactRef>::failure(
        manifest_invalid("artifact byte_length must be a positive integer"));
  }
  return Result<ArtifactRef>::success(
      ArtifactRef{
          input["sha256"].get<std::string>(),
          input["media_type"].get<std::string>(),
          input["byte_length"].get<std::uint64_t>(),
      });
}

Result<SoundSetLicense> parse_license(const nlohmann::json& input) {
  if (!exact_object_keys(
          input, {"spdx_id", "rights_holder", "copyright", "attribution"})) {
    return Result<SoundSetLicense>::failure(
        manifest_invalid(
            "license must contain exactly spdx_id, rights_holder, copyright, attribution"));
  }
  if (!is_nonempty_string(input["spdx_id"]) ||
      !is_nonempty_string(input["rights_holder"]) ||
      !is_nonempty_string(input["copyright"]) ||
      !is_string(input["attribution"])) {
    return Result<SoundSetLicense>::failure(
        manifest_invalid(
            "license.spdx_id, rights_holder and copyright must be non-empty strings"));
  }
  return Result<SoundSetLicense>::success(
      SoundSetLicense{
          input["spdx_id"].get<std::string>(),
          input["rights_holder"].get<std::string>(),
          input["copyright"].get<std::string>(),
          input["attribution"].get<std::string>(),
      });
}

Result<SoundSetSlot> parse_slot(const nlohmann::json& input) {
  if (!input.is_object() || !input.contains("slot") ||
      !input["slot"].is_number_integer()) {
    return Result<SoundSetSlot>::failure(
        slot_invalid("each slot object must contain an integer slot index"));
  }
  const auto index = input["slot"].get<int>();
  if (index < 0 || index >= kSoundSetSlotCount) {
    return Result<SoundSetSlot>::failure(
        slot_invalid("slot index must be in 0..15"));
  }
  if (exact_object_keys(input, {"slot"})) {
    return Result<SoundSetSlot>::success(SoundSetSlot{index, std::nullopt});
  }
  if (!has_only_keys(
          input,
          {"slot", "role", "name", "artifact"},
          {"bpm", "key"})) {
    return Result<SoundSetSlot>::failure(
        manifest_invalid("occupied slot has unknown or missing keys"));
  }
  if (!is_nonempty_string(input["role"]) ||
      !is_nonempty_string(input["name"])) {
    return Result<SoundSetSlot>::failure(
        slot_invalid("occupied slot role and name must be non-empty strings"));
  }
  const auto role = input["role"].get<std::string>();
  if (!known_role(role)) {
    return Result<SoundSetSlot>::failure(
        slot_invalid("occupied slot role is not in the v1 closed enum"));
  }
  if (input.contains("key") && !is_nonempty_string(input["key"])) {
    return Result<SoundSetSlot>::failure(
        manifest_invalid("occupied slot key must be a non-empty string when present"));
  }
  std::optional<int> bpm;
  if (input.contains("bpm")) {
    bpm = optional_bpm(input, "bpm");
    if (!bpm.has_value()) {
      return Result<SoundSetSlot>::failure(
          manifest_invalid("occupied slot bpm must be an integer in 40..240"));
    }
  }
  auto artifact = parse_artifact(input["artifact"]);
  if (!artifact.has_value()) {
    return Result<SoundSetSlot>::failure(artifact.error());
  }
  std::optional<std::string> key;
  if (input.contains("key")) {
    key = input["key"].get<std::string>();
  }
  return Result<SoundSetSlot>::success(
      SoundSetSlot{
          index,
          SoundSetOccupiedSlot{
              std::move(role),
              input["name"].get<std::string>(),
              std::move(artifact.value()),
              bpm,
              std::move(key),
          },
      });
}

bool spdx_allowed(std::string_view spdx_id) {
  return std::any_of(
      kSoundSetSpdxAllowlist.begin(),
      kSoundSetSpdxAllowlist.end(),
      [spdx_id](std::string_view allowed) { return allowed == spdx_id; });
}

}  // namespace

Result<SoundSetManifest> parse_soundset_manifest(std::string_view bytes) {
  if (!valid_utf8(bytes)) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("sound set object must be well-formed UTF-8"));
  }
  const auto parsed = parse_bounded_json(bytes);
  if (!parsed.has_value() || !parsed->is_object()) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("sound set object must be bounded JSON object"));
  }
  const auto canonical = canonical_json(*parsed);
  if (std::string_view(canonical) != bytes) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid(
            "sound set object must equal canonical_json bytes with no trailing newline"));
  }
  if (!has_only_keys(
          *parsed,
          {"contract",
           "set_id",
           "version",
           "name",
           "publisher",
           "license",
           "slots"},
          {"description", "bpm", "key"})) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("sound set root has unknown or missing keys"));
  }
  if (!parsed->at("contract").is_string() ||
      parsed->at("contract").get<std::string>() != kSoundSetContract) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("contract must be lmdj.soundset.v1"));
  }
  if (!parsed->at("set_id").is_string() ||
      !std::regex_match(
          parsed->at("set_id").get_ref<const std::string&>(), kUuid)) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("set_id must be a lowercase UUID"));
  }
  if (!parsed->at("version").is_string() ||
      !std::regex_match(
          parsed->at("version").get_ref<const std::string&>(), kSemver)) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("version must be a SemVer string"));
  }
  if (!is_nonempty_string(parsed->at("name")) ||
      !is_nonempty_string(parsed->at("publisher"))) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("name and publisher must be non-empty strings"));
  }
  if (parsed->contains("description") &&
      !is_nonempty_string(parsed->at("description"))) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("description must be a non-empty string when present"));
  }
  if (parsed->contains("key") && !is_nonempty_string(parsed->at("key"))) {
    return Result<SoundSetManifest>::failure(
        manifest_invalid("set key must be a non-empty string when present"));
  }
  std::optional<int> bpm;
  if (parsed->contains("bpm")) {
    bpm = optional_bpm(*parsed, "bpm");
    if (!bpm.has_value()) {
      return Result<SoundSetManifest>::failure(
          manifest_invalid("set bpm must be an integer in 40..240"));
    }
  }
  auto license = parse_license(parsed->at("license"));
  if (!license.has_value()) {
    return Result<SoundSetManifest>::failure(license.error());
  }
  if (!parsed->at("slots").is_array() ||
      parsed->at("slots").size() !=
          static_cast<std::size_t>(kSoundSetSlotCount)) {
    return Result<SoundSetManifest>::failure(
        slot_invalid("slots must contain exactly 16 entries"));
  }
  SoundSetManifest manifest;
  manifest.set_id = parsed->at("set_id").get<std::string>();
  manifest.version = parsed->at("version").get<std::string>();
  manifest.name = parsed->at("name").get<std::string>();
  manifest.publisher = parsed->at("publisher").get<std::string>();
  if (parsed->contains("description")) {
    manifest.description = parsed->at("description").get<std::string>();
  }
  manifest.bpm = bpm;
  if (parsed->contains("key")) {
    manifest.key = parsed->at("key").get<std::string>();
  }
  manifest.license = std::move(license.value());
  manifest.canonical_bytes = canonical;

  std::array<bool, kSoundSetSlotCount> seen{};
  for (const auto& entry : parsed->at("slots")) {
    auto slot = parse_slot(entry);
    if (!slot.has_value()) {
      return Result<SoundSetManifest>::failure(slot.error());
    }
    const auto index = slot.value().index;
    if (seen[static_cast<std::size_t>(index)]) {
      return Result<SoundSetManifest>::failure(
          slot_invalid("each slot index 0..15 must appear exactly once"));
    }
    seen[static_cast<std::size_t>(index)] = true;
    manifest.slots[static_cast<std::size_t>(index)] = std::move(slot.value());
  }
  return Result<SoundSetManifest>::success(std::move(manifest));
}

Result<void> check_soundset_eligibility(
    const SoundSetManifest& manifest,
    const std::optional<CatalogLicenseSummary>& catalog_summary) {
  if (!spdx_allowed(manifest.license.spdx_id)) {
    return Result<void>::failure(
        license_ineligible("spdx_id is not on the v1 Sound Set allowlist"));
  }
  if (manifest.license.spdx_id == "CC-BY-4.0" &&
      manifest.license.attribution.empty()) {
    return Result<void>::failure(
        license_ineligible("CC-BY-4.0 requires a non-empty attribution string"));
  }
  if (catalog_summary.has_value()) {
    if (catalog_summary->spdx_id != manifest.license.spdx_id ||
        catalog_summary->rights_holder != manifest.license.rights_holder) {
      return Result<void>::failure(
          license_ineligible(
              "catalog license_summary must equal manifest spdx_id and rights_holder"));
    }
  }
  return Result<void>::success();
}

}  // namespace lmdj::foundation
