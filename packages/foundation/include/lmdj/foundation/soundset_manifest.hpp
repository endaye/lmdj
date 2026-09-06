#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::foundation {

inline constexpr int kSoundSetSlotCount = 16;

inline constexpr std::string_view kSoundSetContract = "lmdj.soundset.v1";

inline constexpr std::array<std::string_view, 13> kSoundSetRoles{
    "kick",
    "snare",
    "clap",
    "hat_closed",
    "hat_open",
    "perc",
    "cymbal",
    "bass",
    "melody",
    "chord",
    "vocal",
    "fx",
    "other",
};

inline constexpr std::array<std::string_view, 2> kSoundSetSpdxAllowlist{
    "CC0-1.0",
    "CC-BY-4.0",
};

struct SoundSetLicense {
  std::string spdx_id;
  std::string rights_holder;
  std::string copyright;
  std::string attribution;
};

struct SoundSetOccupiedSlot {
  std::string role;
  std::string name;
  ArtifactRef artifact;
  std::optional<int> bpm;
  std::optional<std::string> key;
};

struct SoundSetSlot {
  int index = 0;
  std::optional<SoundSetOccupiedSlot> occupied;
};

struct SoundSetManifest {
  std::string set_id;
  std::string version;
  std::string name;
  std::string publisher;
  std::optional<std::string> description;
  std::optional<int> bpm;
  std::optional<std::string> key;
  SoundSetLicense license;
  std::array<SoundSetSlot, kSoundSetSlotCount> slots{};
  std::string canonical_bytes;
};

struct CatalogLicenseSummary {
  std::string spdx_id;
  std::string rights_holder;
};

// Parse a Sound Set v1 object: UTF-8 bounded JSON, exact-key structural
// validation, then byte-for-byte equality with canonical_json (no trailing
// newline). Slot-layout faults use reason soundset_slot_invalid; other
// structural faults use soundset_manifest_invalid. Does not decode audio.
Result<SoundSetManifest> parse_soundset_manifest(std::string_view bytes);

// Eligibility is not Schema. Unknown SPDX, unsatisfied BY attribution, or a
// catalog license_summary that differs from the manifest fail closed as
// PERMISSION_DENIED / soundset_license_ineligible.
Result<void> check_soundset_eligibility(
    const SoundSetManifest& manifest,
    const std::optional<CatalogLicenseSummary>& catalog_summary = std::nullopt);

}  // namespace lmdj::foundation
