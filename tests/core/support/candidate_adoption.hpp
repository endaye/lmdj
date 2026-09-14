#pragma once
#include <lmdj/domain/command_handler.hpp>
#include "tests/core/support/test.hpp"

namespace lmdj::test::candidate {
using namespace domain;
using namespace foundation;
inline std::string uuid(unsigned n) {
  const auto suffix = std::to_string(n);
  return "20000000-0000-4000-8000-" + std::string(12 - suffix.size(), '0') + suffix;
}
inline ArtifactRef source_artifact() { return {std::string(64, 'a'), "audio/wav", 54}; }
inline AssetLineage lineage(const ArtifactRef& source = source_artifact()) {
  return {AssetArtifactLineageSource{source.sha256, 1},
      CapabilityAdoptionLineageDerivation{
          {"sample.slice.v1", "lmdj.capability.v2", "1.0.0"},
          {"local.sample.slice", "1.0.0", std::string(64, 'b')}, std::nullopt,
          std::string(64, 'c'), AttemptId{"first"}, AssetId{uuid(2)},
          {std::string(64, 'd'), "application/json", 100}, {1, 3, 48000}}};
}
inline ProjectState project() {
  auto state = create_project(ProjectId{uuid(1)}, 120).value();
  state.revision = 1;
  state.assets.emplace(AssetId{uuid(2)}, Asset{AssetId{uuid(2)}, source_artifact(), std::nullopt});
  state.banks[0][0].asset_id = AssetId{uuid(2)};
  state.banks[0][0].playback.gain_millidb = -100;
  return state;
}
inline AdoptCandidates command() {
  return {{CommandId{uuid(3)}, 1}, ProjectId{uuid(1)}, AssetId{uuid(2)}, source_artifact(),
      {{{0, 0}, {AssetId{uuid(4)}, {std::string(64, 'e'), "audio/wav", 48}, lineage()}},
       {{2, 3}, {AssetId{uuid(5)}, {std::string(64, 'e'), "audio/wav", 48}, lineage()}}}};
}
} // namespace lmdj::test::candidate
