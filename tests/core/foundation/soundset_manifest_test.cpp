#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/foundation/soundset_manifest.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::canonical_json;
using lmdj::foundation::CatalogLicenseSummary;
using lmdj::foundation::check_soundset_eligibility;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::parse_soundset_manifest;
using lmdj::foundation::SoundSetManifest;
using Json = nlohmann::json;

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  LMDJ_CHECK(stream.good());
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

std::string valid_fixture_bytes() {
  return read_bytes(
      std::filesystem::path{LMDJ_SOURCE_DIR} / "tests" / "fixtures" /
      "contracts" / "soundset-v1-valid.json");
}

Json valid_object() {
  return Json::parse(valid_fixture_bytes());
}

std::string dump(const Json& value) {
  return canonical_json(value);
}

void expect_parse_fail(
    std::string_view bytes,
    ErrorCode code,
    std::string_view reason) {
  const auto parsed = parse_soundset_manifest(bytes);
  LMDJ_CHECK(!parsed.has_value());
  LMDJ_CHECK(parsed.error().code == code);
  LMDJ_CHECK(parsed.error().details.at("reason") == reason);
}

void expect_eligibility_fail(
    const SoundSetManifest& manifest,
    const std::optional<CatalogLicenseSummary>& summary,
    std::string_view reason) {
  const auto checked = check_soundset_eligibility(manifest, summary);
  LMDJ_CHECK(!checked.has_value());
  LMDJ_CHECK(checked.error().code == ErrorCode::permission_denied);
  LMDJ_CHECK(checked.error().details.at("reason") == reason);
}

void test_valid_fixture_is_canonical_and_parses() {
  const auto bytes = valid_fixture_bytes();
  LMDJ_CHECK(!bytes.empty());
  LMDJ_CHECK(bytes.back() != '\n');
  const auto parsed = parse_soundset_manifest(bytes);
  LMDJ_CHECK(parsed.has_value());
  LMDJ_CHECK(parsed.value().canonical_bytes == bytes);
  LMDJ_CHECK(parsed.value().canonical_bytes == dump(valid_object()));
  LMDJ_CHECK(parsed.value().set_id == "10000000-0000-4000-8000-000000000001");
  LMDJ_CHECK(parsed.value().license.spdx_id == "CC-BY-4.0");
  LMDJ_CHECK(parsed.value().slots[0].occupied.has_value());
  LMDJ_CHECK(parsed.value().slots[0].occupied->role == "kick");
  LMDJ_CHECK(!parsed.value().slots[1].occupied.has_value());
  LMDJ_CHECK(check_soundset_eligibility(parsed.value()).has_value());
}

void test_non_canonical_json_is_rejected() {
  const auto bytes = valid_fixture_bytes();
  expect_parse_fail(
      std::string("\xef\xbb\xbf") + bytes,
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");
  expect_parse_fail(
      bytes + "\n",
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto reordered = bytes;
  const auto name = std::string(R"("name":"Kit A")");
  const auto publisher = std::string(R"("publisher":"LMDJ")");
  const auto name_at = reordered.find(name);
  const auto publisher_at = reordered.find(publisher);
  LMDJ_CHECK(name_at != std::string::npos);
  LMDJ_CHECK(publisher_at != std::string::npos);
  LMDJ_CHECK(name_at < publisher_at);
  reordered.replace(name_at, name.size(), publisher);
  reordered.replace(
      publisher_at - name.size() + publisher.size(),
      publisher.size(),
      name);
  LMDJ_CHECK(reordered != bytes);
  LMDJ_CHECK(Json::parse(reordered) == valid_object());
  expect_parse_fail(
      reordered, ErrorCode::invalid_argument, "soundset_manifest_invalid");

  auto duplicate_key = bytes;
  duplicate_key.insert(
      duplicate_key.find(name), R"("name":"Other",)");
  expect_parse_fail(
      duplicate_key, ErrorCode::invalid_argument, "soundset_manifest_invalid");

  auto non_canonical_number = bytes;
  const auto length = std::string(R"("byte_length":44)");
  const auto length_at = non_canonical_number.find(length);
  LMDJ_CHECK(length_at != std::string::npos);
  non_canonical_number.replace(length_at, length.size(), R"("byte_length":4.4e1)");
  expect_parse_fail(
      non_canonical_number,
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");
}

void test_slot_layout_faults_use_slot_invalid() {
  auto fifteen = valid_object();
  fifteen["slots"].erase(fifteen["slots"].begin() + 15);
  expect_parse_fail(
      dump(fifteen), ErrorCode::invalid_argument, "soundset_slot_invalid");

  auto seventeen = valid_object();
  seventeen["slots"].push_back(Json{{"slot", 0}});
  expect_parse_fail(
      dump(seventeen), ErrorCode::invalid_argument, "soundset_slot_invalid");

  auto duplicate = valid_object();
  duplicate["slots"][1] = Json{{"slot", 0}};
  expect_parse_fail(
      dump(duplicate), ErrorCode::invalid_argument, "soundset_slot_invalid");

  auto unknown_role = valid_object();
  unknown_role["slots"][0]["role"] = "cowbell";
  expect_parse_fail(
      dump(unknown_role), ErrorCode::invalid_argument, "soundset_slot_invalid");
}

void test_out_of_range_integers_are_rejected_not_narrowed() {
  // nlohmann stores an integer that exceeds `int` as `number_unsigned` or
  // `number_integer` and `get<int>()` narrows it by wraparound instead of
  // throwing, so a value 2^32 away from a legal one lands back inside the
  // guarded range: 4294967296 reads as slot 0 and 4294967311 as slot 15.
  // Canonical bytes keep the original digits, so such a manifest also passes
  // the byte-equality gate — two distinct manifests would claim one layout.
  auto wrapped_to_zero = valid_object();
  wrapped_to_zero["slots"][0]["slot"] = 4294967296LL;
  expect_parse_fail(
      dump(wrapped_to_zero),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");

  auto wrapped_to_fifteen = valid_object();
  wrapped_to_fifteen["slots"][15]["slot"] = 4294967311LL;
  expect_parse_fail(
      dump(wrapped_to_fifteen),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");

  auto negative_wrapped = valid_object();
  negative_wrapped["slots"][0]["slot"] = -4294967296LL;
  expect_parse_fail(
      dump(negative_wrapped),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");

  auto above_int_max = valid_object();
  above_int_max["slots"][0]["slot"] = 3000000000LL;
  expect_parse_fail(
      dump(above_int_max),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");

  // 4294967416 narrows to 120, which sits inside the 40..240 tempo range.
  auto slot_bpm = valid_object();
  slot_bpm["slots"][0]["bpm"] = 4294967416LL;
  expect_parse_fail(
      dump(slot_bpm),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto set_bpm = valid_object();
  set_bpm["bpm"] = 4294967416LL;
  expect_parse_fail(
      dump(set_bpm),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");
}

void test_artifact_and_unknown_key_faults_use_manifest_invalid() {
  auto uppercase = valid_object();
  uppercase["slots"][0]["artifact"]["sha256"] = std::string(64, 'A');
  expect_parse_fail(
      dump(uppercase), ErrorCode::invalid_argument, "soundset_manifest_invalid");

  auto unknown_key = valid_object();
  unknown_key["unexpected"] = true;
  expect_parse_fail(
      dump(unknown_key),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto missing_license = valid_object();
  missing_license.erase("license");
  expect_parse_fail(
      dump(missing_license),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto empty_holder = valid_object();
  empty_holder["license"]["rights_holder"] = "";
  expect_parse_fail(
      dump(empty_holder),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");
}

void test_every_root_refusal_is_reachable() {
  expect_parse_fail(
      "[]", ErrorCode::invalid_argument, "soundset_manifest_invalid");
  expect_parse_fail(
      "{", ErrorCode::invalid_argument, "soundset_manifest_invalid");
  expect_parse_fail(
      std::string("{\"contract\":\"\xff\"}"),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto wrong_contract = valid_object();
  wrong_contract["contract"] = "lmdj.soundset.v2";
  expect_parse_fail(
      dump(wrong_contract),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto contract_not_string = valid_object();
  contract_not_string["contract"] = 1;
  expect_parse_fail(
      dump(contract_not_string),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto uppercase_set_id = valid_object();
  uppercase_set_id["set_id"] =
      uppercase_set_id["set_id"].get<std::string>().substr(0, 8) +
      "-AAAA-4aaa-8aaa-aaaaaaaaaaaa";
  expect_parse_fail(
      dump(uppercase_set_id),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto set_id_not_string = valid_object();
  set_id_not_string["set_id"] = 1;
  expect_parse_fail(
      dump(set_id_not_string),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto version_not_semver = valid_object();
  version_not_semver["version"] = "1.0";
  expect_parse_fail(
      dump(version_not_semver),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto version_not_string = valid_object();
  version_not_string["version"] = 1;
  expect_parse_fail(
      dump(version_not_string),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto empty_name = valid_object();
  empty_name["name"] = "";
  expect_parse_fail(
      dump(empty_name), ErrorCode::invalid_argument, "soundset_manifest_invalid");

  auto empty_publisher = valid_object();
  empty_publisher["publisher"] = "";
  expect_parse_fail(
      dump(empty_publisher),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto empty_description = valid_object();
  empty_description["description"] = "";
  expect_parse_fail(
      dump(empty_description),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto description_not_string = valid_object();
  description_not_string["description"] = 1;
  expect_parse_fail(
      dump(description_not_string),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto empty_key = valid_object();
  empty_key["key"] = "";
  expect_parse_fail(
      dump(empty_key), ErrorCode::invalid_argument, "soundset_manifest_invalid");

  auto bpm_not_integer = valid_object();
  bpm_not_integer["bpm"] = "120";
  expect_parse_fail(
      dump(bpm_not_integer),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto bpm_below_range = valid_object();
  bpm_below_range["bpm"] = 39;
  expect_parse_fail(
      dump(bpm_below_range),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto slots_not_array = valid_object();
  slots_not_array["slots"] = "sixteen";
  expect_parse_fail(
      dump(slots_not_array),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");
}

void test_optional_root_and_slot_fields_round_trip() {
  auto complete = valid_object();
  complete["description"] = "Night kit";
  complete["bpm"] = 120;
  complete["key"] = "Am";
  complete["slots"][0]["bpm"] = 90;
  complete["slots"][0]["key"] = "C";
  const auto bytes = dump(complete);
  const auto parsed = parse_soundset_manifest(bytes);
  LMDJ_CHECK(parsed.has_value());
  const auto& manifest = parsed.value();
  LMDJ_CHECK(manifest.description.value() == "Night kit");
  LMDJ_CHECK(manifest.bpm.value() == 120);
  LMDJ_CHECK(manifest.key.value() == "Am");
  LMDJ_CHECK(manifest.canonical_bytes == bytes);
  const auto& occupied = manifest.slots.at(0).occupied;
  LMDJ_CHECK(occupied.has_value());
  LMDJ_CHECK(occupied->bpm.value() == 90);
  LMDJ_CHECK(occupied->key.value() == "C");
}

void test_every_license_artifact_and_slot_refusal_is_reachable() {
  auto license_extra_key = valid_object();
  license_extra_key["license"]["extra"] = true;
  expect_parse_fail(
      dump(license_extra_key),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto empty_spdx = valid_object();
  empty_spdx["license"]["spdx_id"] = "";
  expect_parse_fail(
      dump(empty_spdx), ErrorCode::invalid_argument, "soundset_manifest_invalid");

  auto empty_copyright = valid_object();
  empty_copyright["license"]["copyright"] = "";
  expect_parse_fail(
      dump(empty_copyright),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto attribution_not_string = valid_object();
  attribution_not_string["license"]["attribution"] = 1;
  expect_parse_fail(
      dump(attribution_not_string),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto artifact_extra_key = valid_object();
  artifact_extra_key["slots"][0]["artifact"]["extra"] = true;
  expect_parse_fail(
      dump(artifact_extra_key),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto sha_not_string = valid_object();
  sha_not_string["slots"][0]["artifact"]["sha256"] = 1;
  expect_parse_fail(
      dump(sha_not_string),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto empty_media_type = valid_object();
  empty_media_type["slots"][0]["artifact"]["media_type"] = "";
  expect_parse_fail(
      dump(empty_media_type),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto zero_byte_length = valid_object();
  zero_byte_length["slots"][0]["artifact"]["byte_length"] = 0;
  expect_parse_fail(
      dump(zero_byte_length),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto negative_byte_length = valid_object();
  negative_byte_length["slots"][0]["artifact"]["byte_length"] = -1;
  expect_parse_fail(
      dump(negative_byte_length),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto slot_not_object = valid_object();
  slot_not_object["slots"][0] = 0;
  expect_parse_fail(
      dump(slot_not_object),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");

  auto slot_missing_index = valid_object();
  slot_missing_index["slots"][0].erase("slot");
  expect_parse_fail(
      dump(slot_missing_index),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");

  auto slot_unknown_key = valid_object();
  slot_unknown_key["slots"][0]["extra"] = true;
  expect_parse_fail(
      dump(slot_unknown_key),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto empty_slot_name = valid_object();
  empty_slot_name["slots"][0]["name"] = "";
  expect_parse_fail(
      dump(empty_slot_name),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");

  auto slot_role_not_string = valid_object();
  slot_role_not_string["slots"][0]["role"] = 1;
  expect_parse_fail(
      dump(slot_role_not_string),
      ErrorCode::invalid_argument,
      "soundset_slot_invalid");

  auto empty_slot_key = valid_object();
  empty_slot_key["slots"][0]["key"] = "";
  expect_parse_fail(
      dump(empty_slot_key),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");

  auto slot_bpm_above_range = valid_object();
  slot_bpm_above_range["slots"][0]["bpm"] = 241;
  expect_parse_fail(
      dump(slot_bpm_above_range),
      ErrorCode::invalid_argument,
      "soundset_manifest_invalid");
}

void test_eligibility_is_not_schema() {
  auto unknown_spdx = valid_object();
  unknown_spdx["license"]["spdx_id"] = "MIT";
  const auto parsed_unknown =
      parse_soundset_manifest(dump(unknown_spdx));
  LMDJ_CHECK(parsed_unknown.has_value());
  expect_eligibility_fail(
      parsed_unknown.value(), std::nullopt, "soundset_license_ineligible");

  auto empty_by = valid_object();
  empty_by["license"]["attribution"] = "";
  const auto parsed_empty_by = parse_soundset_manifest(dump(empty_by));
  LMDJ_CHECK(parsed_empty_by.has_value());
  expect_eligibility_fail(
      parsed_empty_by.value(), std::nullopt, "soundset_license_ineligible");

  auto cc0 = valid_object();
  cc0["license"]["spdx_id"] = "CC0-1.0";
  cc0["license"]["attribution"] = "";
  const auto parsed_cc0 = parse_soundset_manifest(dump(cc0));
  LMDJ_CHECK(parsed_cc0.has_value());
  LMDJ_CHECK(check_soundset_eligibility(parsed_cc0.value()).has_value());

  const auto parsed = parse_soundset_manifest(valid_fixture_bytes());
  LMDJ_CHECK(parsed.has_value());
  expect_eligibility_fail(
      parsed.value(),
      CatalogLicenseSummary{"CC0-1.0", "Alice"},
      "soundset_license_ineligible");
  LMDJ_CHECK(
      check_soundset_eligibility(
          parsed.value(), CatalogLicenseSummary{"CC-BY-4.0", "Alice"})
          .has_value());
}

}  // namespace

int main() {
  try {
    test_valid_fixture_is_canonical_and_parses();
    test_non_canonical_json_is_rejected();
    test_slot_layout_faults_use_slot_invalid();
    test_out_of_range_integers_are_rejected_not_narrowed();
    test_artifact_and_unknown_key_faults_use_manifest_invalid();
    test_every_root_refusal_is_reachable();
    test_optional_root_and_slot_fields_round_trip();
    test_every_license_artifact_and_slot_refusal_is_reachable();
    test_eligibility_is_not_schema();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "foundation soundset manifest tests: PASS\n";
  return 0;
}
