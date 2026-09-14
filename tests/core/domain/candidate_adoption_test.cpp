#include <iostream>
#include "tests/core/support/candidate_adoption.hpp"

namespace {
using namespace lmdj::test::candidate;
void atomic_success() {
  auto state = project();
  state.contract = ProjectContract::v4;
  const auto original = state;
  const auto cmd = command();
  const auto result = apply(state, cmd, {});
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(state == original);
  LMDJ_CHECK(result.value().state.revision == 2);
  LMDJ_CHECK(result.value().state.contract == ProjectContract::v5);
  LMDJ_CHECK(result.value().event.at("type") == "candidate.adopted");
  auto expected = state;
  expected.contract = ProjectContract::v5;
  expected.revision = 2;
  for (const auto& assignment : cmd.assignments) {
    expected.assets.emplace(assignment.asset.id, assignment.asset);
    auto& pad = expected.banks[assignment.slot.bank][assignment.slot.pad];
    pad.asset_id = assignment.asset.id;
    pad.playback = PadPlayback{};
  }
  LMDJ_CHECK(result.value().state == expected);
}
template<class Change> void refused(Change change) {
  const auto state = project();
  auto cmd = command();
  change(cmd);
  const auto result = apply(state, cmd, {});
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(state == project());
}
void source_freshness() {
  auto state = project();
  auto cmd = command();
  state.revision = 9;
  LMDJ_CHECK(!apply(state, cmd, {}).has_value());
  cmd.meta.expected_revision = 9;
  const auto result = apply(state, cmd, {});
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(std::get<AssetArtifactLineageSource>(result.value().state.assets.at(AssetId{uuid(4)}).lineage->source).project_revision == 1);
  for (int field = 0; field != 3; ++field) {
    auto changed = state;
    auto& artifact = changed.assets.at(cmd.source_asset_id).artifact;
    if (field == 0) artifact.sha256 = std::string(64, 'f');
    if (field == 1) ++artifact.byte_length;
    if (field == 2) artifact.media_type = "audio/other";
    const auto failure = apply(changed, cmd, {});
    LMDJ_CHECK(!failure.has_value());
    LMDJ_CHECK(failure.error().code == ErrorCode::revision_conflict);
    LMDJ_CHECK(failure.error().details.at("reason") == "candidate_source_changed");
  }
  state.assets.clear();
  const auto absent = apply(state, cmd, {});
  LMDJ_CHECK(!absent.has_value());
  LMDJ_CHECK(absent.error().details.at("reason") == "source_asset_missing");
}
}
int main() {
  try {
    atomic_success();
    source_freshness();
    refused([](auto& c) { c.assignments.clear(); });
    refused([](auto& c) { c.assignments.back().slot = c.assignments.front().slot; });
    refused([](auto& c) { c.assignments.back().slot.bank = 4; });
    refused([](auto& c) { c.assignments.back().asset.id = c.assignments.front().asset.id; });
    refused([](auto& c) { c.assignments.back().asset.id = c.source_asset_id; });
    refused([](auto& c) { c.project_id = ProjectId{uuid(99)}; });
    refused([](auto& c) { c.assignments.back().asset.lineage.reset(); });
    refused([](auto& c) { std::get<CapabilityAdoptionLineageDerivation>(c.assignments.back().asset.lineage->derivation).attempt_id = AttemptId{"other"}; });
    refused([](auto& c) { std::get<AssetArtifactLineageSource>(c.assignments.back().asset.lineage->source).project_revision = 2; });
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
  std::cout << "candidate adoption domain: PASS\n";
}
