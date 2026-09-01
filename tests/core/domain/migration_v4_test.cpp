#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/domain/project.hpp>

#include "tests/core/support/test.hpp"

namespace {

using Json = nlohmann::json;

Json load_fixture(std::string_view name) {
  const auto path = std::filesystem::path{LMDJ_SOURCE_DIR} /
                    "tests" / "fixtures" / "contracts" / name;
  std::ifstream stream(path);
  LMDJ_CHECK(stream.good());
  return Json::parse(stream);
}

void test_v3_to_v4_adds_empty_pattern_slots_and_performances() {
  const auto expected = load_fixture("project-v3-to-v4-migration.json");
  auto source = expected;
  source["contract"] = "lmdj.project.v3";
  source.erase("performances");
  source.erase("pattern_slots");
  for (auto& asset : source.at("assets")) {
    asset.erase("lineage");
  }
  const auto source_before = source;

  const auto result = lmdj::domain::migrate_project_v3_to_v4(source);

  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value() == expected);
  LMDJ_CHECK(source == source_before);
  LMDJ_CHECK(result.value().at("contract") == "lmdj.project.v4");
  LMDJ_CHECK(result.value().at("performances") == Json::array());
  LMDJ_CHECK(result.value().at("pattern_slots") ==
             Json::array({nullptr, nullptr, nullptr, nullptr,
                          nullptr, nullptr, nullptr, nullptr,
                          nullptr, nullptr, nullptr, nullptr,
                          nullptr, nullptr, nullptr, nullptr}));
  for (auto iterator = source.begin(); iterator != source.end(); ++iterator) {
    if (iterator.key() == "contract") {
      continue;
    }
    if (iterator.key() == "assets") {
      for (std::size_t index = 0; index < iterator.value().size(); ++index) {
        auto expected_asset = iterator.value().at(index);
        expected_asset["lineage"] = nullptr;
        LMDJ_CHECK(
            result.value().at("assets").at(index) == expected_asset);
      }
      continue;
    }
    LMDJ_CHECK(result.value().at(iterator.key()).dump() == iterator.value().dump());
  }
}

void test_v3_declared_asset_with_lineage_is_rejected() {
  auto source = load_fixture("project-v3-to-v4-migration.json");
  source["contract"] = "lmdj.project.v3";
  source.erase("performances");
  source.erase("pattern_slots");

  const auto result = lmdj::domain::migrate_project_v3_to_v4(source);

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(
      result.error().code ==
      lmdj::foundation::ErrorCode::invalid_project);
}

void test_v3_declared_document_with_performances_is_rejected() {
  auto source = load_fixture("project-v3-to-v4-migration.json");
  source["contract"] = "lmdj.project.v3";
  source.erase("pattern_slots");

  const auto result = lmdj::domain::migrate_project_v3_to_v4(source);

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(
      result.error().code ==
      lmdj::foundation::ErrorCode::invalid_project);
}

void test_v3_declared_document_with_pattern_slots_is_rejected() {
  auto source = load_fixture("project-v3-to-v4-migration.json");
  source["contract"] = "lmdj.project.v3";
  source.erase("performances");

  const auto result = lmdj::domain::migrate_project_v3_to_v4(source);

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(
      result.error().code ==
      lmdj::foundation::ErrorCode::invalid_project);
}

void test_migration_edge_accepts_only_v3_declared_documents() {
  auto source = load_fixture("project-v3-to-v4-migration.json");
  source.erase("performances");
  source.erase("pattern_slots");

  const auto result = lmdj::domain::migrate_project_v3_to_v4(source);

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(
      result.error().code ==
      lmdj::foundation::ErrorCode::invalid_project);
}

void test_migration_rejects_malformed_contract_declarations() {
  const std::vector<Json> malformed{
      nullptr,
      Json::array(),
      Json::object(),
      {{"contract", 3}},
  };
  for (const auto& source : malformed) {
    const auto result = lmdj::domain::migrate_project_v3_to_v4(source);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(
        result.error().code ==
        lmdj::foundation::ErrorCode::invalid_project);
  }
}

}  // namespace

int main() {
  try {
    test_v3_to_v4_adds_empty_pattern_slots_and_performances();
    test_v3_declared_document_with_performances_is_rejected();
    test_v3_declared_document_with_pattern_slots_is_rejected();
    test_v3_declared_asset_with_lineage_is_rejected();
    test_migration_edge_accepts_only_v3_declared_documents();
    test_migration_rejects_malformed_contract_declarations();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "domain v4 migration tests: PASS\n";
  return 0;
}
