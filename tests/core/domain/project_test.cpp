#include <cstdint>
#include <exception>
#include <iostream>
#include <string>
#include <string_view>

#include <lmdj/domain/project.hpp>

#include "tests/core/support/test.hpp"

namespace {

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";

void test_uuid_validation_matches_project_contract_grammar() {
  for (const std::string_view valid : {
           "01234567-89ab-1cde-8f01-23456789abcd",
           "01234567-89ab-2cde-9f01-23456789abcd",
           "01234567-89ab-3cde-af01-23456789abcd",
           "01234567-89ab-4cde-bf01-23456789abcd",
           "01234567-89ab-5cde-8f01-23456789abcd",
       }) {
    LMDJ_CHECK(lmdj::domain::is_valid_uuid(valid));
  }

  for (const std::string_view invalid : {
           "01234567.89ab.4cde.8f01.23456789abcd",
           "01234567-89AB-4cde-8f01-23456789abcd",
           "01234567-89ab-4cde-8f01-23456789abc",
           "01234567-89ab-6cde-8f01-23456789abcd",
           "01234567-89ab-4cde-7f01-23456789abcd",
           "01234567-89ab-4cde-cf01-23456789abcd",
       }) {
    LMDJ_CHECK(!lmdj::domain::is_valid_uuid(invalid));
  }
}

void test_new_project_creates_all_64_addressable_pad_slots() {
  const auto result = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{kProjectId}, 120);

  LMDJ_CHECK(result.has_value());
  const auto& project = result.value();
  LMDJ_CHECK(project.contract == lmdj::domain::ProjectContract::v1);
  LMDJ_CHECK(project.revision == 0);
  LMDJ_CHECK(project.banks.size() == 4);

  std::uint32_t slot_count = 0;
  for (std::uint8_t bank = 0; bank < 4; ++bank) {
    LMDJ_CHECK(project.banks.at(bank).size() == 16);
    for (std::uint8_t pad = 0; pad < 16; ++pad) {
      const auto& slot = project.banks.at(bank).at(pad);
      LMDJ_CHECK((slot.id == lmdj::domain::PadSlotId{bank, pad}));
      LMDJ_CHECK(!slot.asset_id.has_value());
      LMDJ_CHECK(slot.playback == lmdj::domain::PadPlayback{});
      ++slot_count;
    }
  }
  LMDJ_CHECK(slot_count == 64);
}

void test_pad_playback_defaults_are_project_v2_contract_values() {
  const lmdj::domain::PadPlayback playback{};

  LMDJ_CHECK(playback.trim_start_frame == 0);
  LMDJ_CHECK(!playback.trim_end_frame.has_value());
  LMDJ_CHECK(playback.trigger_mode == lmdj::domain::TriggerMode::one_shot);
  LMDJ_CHECK(playback.gain_millidb == 0);
  LMDJ_CHECK(!playback.choke_enabled);
}

void test_project_factory_accepts_only_supported_bpm_range() {
  LMDJ_CHECK(
      lmdj::domain::create_project(
          lmdj::foundation::ProjectId{kProjectId}, 40)
          .has_value());
  LMDJ_CHECK(
      lmdj::domain::create_project(
          lmdj::foundation::ProjectId{kProjectId}, 240)
          .has_value());

  const auto too_slow = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{kProjectId}, 39);
  const auto too_fast = lmdj::domain::create_project(
      lmdj::foundation::ProjectId{kProjectId}, 241);

  LMDJ_CHECK(!too_slow.has_value());
  LMDJ_CHECK(
      too_slow.error().code == lmdj::foundation::ErrorCode::invalid_argument);
  LMDJ_CHECK(!too_fast.has_value());
  LMDJ_CHECK(
      too_fast.error().code == lmdj::foundation::ErrorCode::invalid_argument);
}

void test_project_factory_rejects_non_contract_project_ids() {
  for (const std::string_view invalid : {
           "00000000.0000.4000.8000.000000000001",
           "00000000-0000-4000-8000-00000000000A",
           "00000000-0000-4000-8000-00000000001",
           "00000000-0000-6000-8000-000000000001",
       }) {
    const auto result = lmdj::domain::create_project(
        lmdj::foundation::ProjectId{std::string(invalid)}, 120);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(
        result.error().code ==
        lmdj::foundation::ErrorCode::invalid_argument);
  }
}

}  // namespace

int main() {
  try {
    test_uuid_validation_matches_project_contract_grammar();
    test_new_project_creates_all_64_addressable_pad_slots();
    test_pad_playback_defaults_are_project_v2_contract_values();
    test_project_factory_accepts_only_supported_bpm_range();
    test_project_factory_rejects_non_contract_project_ids();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "domain project tests: PASS\n";
  return 0;
}
