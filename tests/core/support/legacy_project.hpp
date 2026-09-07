#pragma once

#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>

#include <nlohmann/json.hpp>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/json.hpp>

#include "tests/core/support/test.hpp"

namespace lmdj::test {

// Rewrite a checkpoint this Build wrote into the lmdj.project.v3 shape a
// previous Build would have written: v3 carries neither Pattern Slots nor
// Performances, and its Assets have no Lineage.
//
// Every Project this Build creates and persists is lmdj.project.v4, so a test
// that means to exercise a v3 Project has to produce one deliberately. Setting
// `contract` on the in-memory state before `ProjectStore::create` does not do
// it — the store writes v4 regardless — and a fixture built that way goes on
// passing while silently testing v4.
inline nlohmann::json v3_checkpoint(nlohmann::json checkpoint) {
  LMDJ_CHECK(checkpoint.at("contract") == "lmdj.project.v4");
  checkpoint["contract"] = "lmdj.project.v3";
  checkpoint.erase("pattern_slots");
  checkpoint.erase("performances");
  for (auto& asset : checkpoint.at("assets")) {
    asset.erase("lineage");
  }
  return checkpoint;
}

// Downgrade a Project Bundle's checkpoint zero in place, so the Bundle on disk
// is a real v3 Project. Callers should assert the reopened Contract level so
// the fixture cannot quietly stop being v3.
inline void downgrade_checkpoint_zero_to_v3(
    const std::filesystem::path& bundle) {
  const auto path = bundle / "history/checkpoints/0.json";
  nlohmann::json checkpoint;
  {
    std::ifstream input(path, std::ios::binary);
    LMDJ_CHECK(static_cast<bool>(input));
    checkpoint = nlohmann::json::parse(
        std::string{
            std::istreambuf_iterator<char>{input},
            std::istreambuf_iterator<char>{}});
  }
  const auto encoded =
      foundation::canonical_json(v3_checkpoint(std::move(checkpoint))) + "\n";
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  LMDJ_CHECK(static_cast<bool>(output));
  output.write(encoded.data(), static_cast<std::streamsize>(encoded.size()));
  LMDJ_CHECK(static_cast<bool>(output));
}

// Turn a Bundle this Build just created into a v3 Project on disk and prove it
// reopens as v3, so a fixture cannot quietly stop being v3 the way one does
// when it only sets the in-memory Contract before ProjectStore::create.
template <typename Store>
void make_v3_bundle_on_disk(
    Store& store,
    const std::filesystem::path& bundle) {
  downgrade_checkpoint_zero_to_v3(bundle);
  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value().contract == domain::ProjectContract::v3);
}

}  // namespace lmdj::test
