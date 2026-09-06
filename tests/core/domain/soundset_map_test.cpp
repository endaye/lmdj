// S11-D11 / #465 Q2: the Sound Set mapping is a pure function whose v1 table
// is slot-index identity. Role, BPM and Key are preview metadata only, so a
// duplicate role must never permute a slot, and S11-D12 forbids an empty Set
// slot from proposing anything at all.
#include <algorithm>
#include <array>
#include <cstdint>
#include <exception>
#include <iostream>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <lmdj/domain/commands.hpp>
#include <lmdj/foundation/soundset_manifest.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::PadSlot;
using lmdj::domain::SoundSetMapping;
using lmdj::domain::SoundSetProposedPad;
using lmdj::domain::map_soundset;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::SoundSetManifest;
using lmdj::foundation::SoundSetOccupiedSlot;

using BankPads = std::array<PadSlot, lmdj::domain::kPatternSlotCount>;

std::string digest(char fill) { return std::string(64, fill); }

ArtifactRef artifact(char fill, std::uint64_t byte_length) {
  return ArtifactRef{digest(fill), "audio/wav", byte_length};
}

// A Set that occupies 0, 1, 2 and 5 and leaves every other slot empty. Slots
// 1 and 2 share the `snare` role on purpose: the identity table must ignore it.
SoundSetManifest manifest_with_duplicate_roles() {
  SoundSetManifest manifest;
  manifest.set_id = "30000000-0000-4000-8000-000000000009";
  manifest.version = "1.2.0";
  manifest.name = "Duplicate Roles";
  manifest.publisher = "Test Publisher";
  manifest.license = {"CC0-1.0", "Holder", "Copyright 2026 Holder", ""};
  for (int index = 0; index < lmdj::foundation::kSoundSetSlotCount; ++index) {
    manifest.slots.at(static_cast<std::size_t>(index)).index = index;
  }
  const std::array<std::pair<int, std::pair<const char*, char>>, 4> occupied{{
      {0, {"kick", 'a'}},
      {1, {"snare", 'b'}},
      {2, {"snare", 'c'}},
      {5, {"kick", 'd'}},
  }};
  for (const auto& [index, description] : occupied) {
    auto& slot = manifest.slots.at(static_cast<std::size_t>(index));
    slot.index = index;
    slot.occupied = SoundSetOccupiedSlot{
        description.first,
        std::string{"slot-"} + std::to_string(index),
        artifact(description.second, 44 + static_cast<std::uint64_t>(index)),
        std::nullopt,
        std::nullopt,
    };
  }
  return manifest;
}

BankPads empty_bank() {
  BankPads pads{};
  for (std::size_t index = 0; index < pads.size(); ++index) {
    pads.at(index).id = {0, static_cast<std::uint8_t>(index)};
  }
  return pads;
}

BankPads bank_occupying(const std::vector<std::uint8_t>& occupied_pads) {
  auto pads = empty_bank();
  for (const auto pad : occupied_pads) {
    pads.at(pad).asset_id =
        AssetId{"20000000-0000-4000-8000-00000000000" + std::to_string(pad % 10)};
  }
  return pads;
}

std::vector<std::uint8_t> proposed_pads(const SoundSetMapping& mapping) {
  std::vector<std::uint8_t> pads;
  for (const auto& proposed : mapping.proposed) {
    pads.push_back(proposed.pad);
  }
  return pads;
}

void test_mapping_is_slot_index_identity() {
  const auto manifest = manifest_with_duplicate_roles();
  const auto mapping = map_soundset(manifest, empty_bank());
  LMDJ_CHECK(proposed_pads(mapping) == std::vector<std::uint8_t>({0, 1, 2, 5}));
  for (const auto& proposed : mapping.proposed) {
    LMDJ_CHECK(proposed.pad == proposed.slot_index);
    LMDJ_CHECK(
        proposed.artifact ==
        manifest.slots.at(proposed.slot_index).occupied->artifact);
  }
  LMDJ_CHECK(mapping.collisions.empty());
}

void test_duplicate_roles_do_not_permute_slots() {
  const auto manifest = manifest_with_duplicate_roles();
  const auto mapping = map_soundset(manifest, empty_bank());
  // Slots 1 and 2 are both `snare`; slot 1 must still reach pad 1.
  LMDJ_CHECK(mapping.proposed.at(1).pad == 1);
  LMDJ_CHECK(mapping.proposed.at(1).artifact.sha256 == digest('b'));
  LMDJ_CHECK(mapping.proposed.at(2).pad == 2);
  LMDJ_CHECK(mapping.proposed.at(2).artifact.sha256 == digest('c'));
  // Slots 0 and 5 are both `kick` and stay 25 pads apart in role terms.
  LMDJ_CHECK(mapping.proposed.at(0).artifact.sha256 == digest('a'));
  LMDJ_CHECK(mapping.proposed.at(3).pad == 5);
  LMDJ_CHECK(mapping.proposed.at(3).artifact.sha256 == digest('d'));
}

void test_empty_set_slots_are_kept_whether_or_not_the_pad_is_occupied() {
  const auto manifest = manifest_with_duplicate_roles();
  const auto mapping = map_soundset(manifest, bank_occupying({3, 7}));
  const std::vector<std::uint8_t> expected_kept{
      3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};
  LMDJ_CHECK(mapping.kept == expected_kept);
  // An occupied Pad under an empty Set slot is kept, never a collision and
  // never a proposal: S11-D12 says an empty slot is not a wipe instruction.
  const auto proposed = proposed_pads(mapping);
  for (const auto pad : {std::uint8_t{3}, std::uint8_t{7}}) {
    LMDJ_CHECK(
        std::ranges::find(mapping.collisions, pad) == mapping.collisions.end());
    LMDJ_CHECK(std::ranges::find(proposed, pad) == proposed.end());
  }
}

void test_collisions_name_every_occupied_proposed_pad_in_slot_order() {
  const auto manifest = manifest_with_duplicate_roles();
  const auto mapping = map_soundset(manifest, bank_occupying({1, 3, 5}));
  // Pad 3 is occupied but its Set slot is empty, so it is not a collision.
  LMDJ_CHECK(mapping.collisions == std::vector<std::uint8_t>({1, 5}));
  LMDJ_CHECK(proposed_pads(mapping) == std::vector<std::uint8_t>({0, 1, 2, 5}));
}

void test_mapping_is_deterministic() {
  const auto manifest = manifest_with_duplicate_roles();
  const auto pads = bank_occupying({0, 2, 15});
  const auto first = map_soundset(manifest, pads);
  const auto second = map_soundset(manifest, pads);
  LMDJ_CHECK(first == second);
  // Reading the same Set against the same occupancy a third time through a
  // copy of the inputs must not drift either.
  const auto manifest_copy = manifest;
  const auto pads_copy = pads;
  LMDJ_CHECK(map_soundset(manifest_copy, pads_copy) == first);
}

void test_a_fully_empty_set_proposes_nothing() {
  SoundSetManifest manifest;
  manifest.set_id = "30000000-0000-4000-8000-00000000000a";
  manifest.version = "1.0.0";
  for (int index = 0; index < lmdj::foundation::kSoundSetSlotCount; ++index) {
    manifest.slots.at(static_cast<std::size_t>(index)).index = index;
  }
  const auto mapping = map_soundset(manifest, bank_occupying({0, 1, 2}));
  LMDJ_CHECK(mapping.proposed.empty());
  LMDJ_CHECK(mapping.collisions.empty());
  LMDJ_CHECK(mapping.kept.size() == lmdj::domain::kPatternSlotCount);
}

}  // namespace

int main() {
  try {
    test_mapping_is_slot_index_identity();
    test_duplicate_roles_do_not_permute_slots();
    test_empty_set_slots_are_kept_whether_or_not_the_pad_is_occupied();
    test_collisions_name_every_occupied_proposed_pad_in_slot_order();
    test_mapping_is_deterministic();
    test_a_fully_empty_set_proposes_nothing();
  } catch (const std::exception& error) {
    std::cerr << "soundset map test failed: " << error.what() << "\n";
    return 1;
  }
  std::cout << "soundset map tests passed\n";
  return 0;
}
