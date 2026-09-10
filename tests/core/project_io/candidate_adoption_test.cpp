#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <picosha2.h>
#include <lmdj/project_io/project_store.hpp>
#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/candidate_adoption.hpp"
#if defined(__unix__) || defined(__APPLE__)
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace {
using namespace lmdj::test::candidate;
using namespace lmdj::project_io;
using namespace lmdj::project_io::testing;
using Json = nlohmann::json;
std::string read(const std::filesystem::path& p) {
  std::ifstream f(p, std::ios::binary);
  return {std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>()};
}
std::string digest(const std::vector<std::byte>& b) {
  const std::string bytes(reinterpret_cast<const char*>(b.data()), b.size());
  return picosha2::hash256_hex_string(bytes);
}
struct Fixture {
  std::filesystem::path root = std::filesystem::temp_directory_path() /
      ("lmdj-adopt-io-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".lmdj");
  ProjectStore store;
  std::vector<std::byte> source{std::byte{1}, std::byte{2}, std::byte{3}};
  std::vector<std::vector<std::byte>> payloads{{std::byte{1}}, {std::byte{2}, std::byte{3}}};
  ProjectStore::CandidateAdoptionRequest request{{CommandId{uuid(3)}, 1},
      ProjectId{uuid(1)}, AssetId{uuid(2)}, {digest(source), "audio/wav", source.size()}, {}};
  ProjectState before = create_project(ProjectId{uuid(1)}, 120).value();
  Fixture(std::string media_type = "audio/wav", std::size_t source_bytes = 3) {
    source.resize(source_bytes, std::byte{1});
    request.source_artifact = {digest(source), media_type, source.size()};
    LMDJ_CHECK(store.create(root, create_project(ProjectId{uuid(1)}, 120).value()).has_value());
    const auto imported = store.import_artifact_bytes(root,
        {{CommandId{uuid(6)}, 0}, AssetId{uuid(2)}, media_type, source});
    LMDJ_CHECK(imported.has_value());
    before = imported.value().state;
    for (std::size_t i = 0; i < payloads.size(); ++i)
      request.slots.push_back({{static_cast<std::uint8_t>(i), static_cast<std::uint8_t>(i)},
          AssetId{uuid(4 + static_cast<unsigned>(i))}, "audio/wav", payloads[i], lineage(request.source_artifact)});
  }
  ~Fixture() { set_fault_hook(nullptr); std::error_code ec; std::filesystem::remove_all(root, ec); }
  void unchanged() {
    const auto loaded = store.load(root);
    if (!loaded.has_value()) throw std::runtime_error(loaded.error().message);
    LMDJ_CHECK(loaded.value() == before);
    LMDJ_CHECK(std::distance(std::filesystem::directory_iterator(root / "assets"), {}) == 1);
  }
  ProjectState adopt() {
    const auto result = store.adopt_candidates(root, request);
    if (!result.has_value()) throw std::runtime_error(result.error().message);
    LMDJ_CHECK(result.value().state.revision == 2);
    LMDJ_CHECK(result.value().event.at("type") == "candidate.adopted");
    return result.value().state;
  }
  void verify(const ProjectState& expected) {
    const auto reopened = store.load(root);
    if (!reopened.has_value()) throw std::runtime_error(reopened.error().message);
    LMDJ_CHECK(reopened.value() == expected);
    LMDJ_CHECK(reopened.value().assets.at(request.source_asset_id) == before.assets.at(request.source_asset_id));
    for (std::size_t i = 0; i < request.slots.size(); ++i) {
      const auto& slot = request.slots[i];
      LMDJ_CHECK(reopened.value().banks[slot.slot.bank][slot.slot.pad].asset_id == slot.asset_id);
      const auto& asset = reopened.value().assets.at(slot.asset_id);
      LMDJ_CHECK(asset.lineage == slot.lineage);
      LMDJ_CHECK(asset.artifact == (ArtifactRef{digest(payloads[i]), "audio/wav", payloads[i].size()}));
      const auto bytes = store.read_artifact(root, asset.artifact);
      LMDJ_CHECK(bytes.has_value());
      LMDJ_CHECK(bytes.value() == payloads[i]);
    }
  }
};
FaultPoint point;
int calls = 0;
#if defined(__unix__) || defined(__APPLE__)
bool crash = false;
#endif
Result<void> inject(FaultPoint observed, const std::filesystem::path&) {
  if (observed != point) return Result<void>::success();
  ++calls;
#if defined(__unix__) || defined(__APPLE__)
  if (crash) _exit(71);
#endif
  return Result<void>::failure(Error{ErrorCode::io_error, "adoption fault"});
}
void unsupported_source_is_atomic() {
  for (const bool oversized : {false, true}) {
    Fixture f(oversized ? "audio/wav" : "application/octet-stream",
        oversized ? 16777217U : 3U);
    const auto result = f.store.adopt_candidates(f.root, f.request);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::invalid_argument);
    f.unchanged();
  }
}
void success_and_explicit_repeat() {
  Fixture f;
  const auto state = f.adopt();
  f.verify(state);
  auto old = f.store.adopt_candidates(f.root, f.request);
  LMDJ_CHECK(!old.has_value());
  LMDJ_CHECK(old.error().code == ErrorCode::revision_conflict);
  f.request.meta.expected_revision = 2;
  const auto collision = f.store.adopt_candidates(f.root, f.request);
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::invalid_argument);
  f.request.meta.command_id = CommandId{uuid(7)};
  for (std::size_t i = 0; i < f.request.slots.size(); ++i)
    f.request.slots[i].asset_id = AssetId{uuid(8 + static_cast<unsigned>(i))};
  const auto again = f.store.adopt_candidates(f.root, f.request);
  LMDJ_CHECK(again.has_value());
  LMDJ_CHECK(again.value().state.revision == 3);
  f.verify(again.value().state);
}
void writer_source_checks() {
  for (int field = 0; field < 5; ++field) {
    Fixture f;
    if (field == 0) f.request.project_id = ProjectId{uuid(99)};
    if (field == 1) f.request.source_asset_id = AssetId{uuid(99)};
    if (field == 2) f.request.source_artifact.sha256 = std::string(64, 'f');
    if (field == 3) ++f.request.source_artifact.byte_length;
    if (field == 4) f.request.source_artifact.media_type = "audio/other";
    const auto result = f.store.adopt_candidates(f.root, f.request);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == (field == 1 ? ErrorCode::not_found : ErrorCode::revision_conflict));
    f.unchanged();
  }
}
void failures() {
  for (auto fail : {FaultPoint::artifact_temp_sync, FaultPoint::artifact_publish,
      FaultPoint::transaction_temp_sync, FaultPoint::transaction_publish,
      FaultPoint::checkpoint_temp_sync, FaultPoint::checkpoint_publish,
      FaultPoint::manifest_temp_sync, FaultPoint::manifest_publish,
      FaultPoint::sample_after_event_preparation, FaultPoint::sample_after_artifact_creation,
      FaultPoint::sample_after_manifest_preparation}) {
    Fixture f;
    point = fail; calls = 0; set_fault_hook(inject);
    const auto result = f.store.adopt_candidates(f.root, f.request);
    set_fault_hook(nullptr);
    LMDJ_CHECK(calls >= 1);
    LMDJ_CHECK(!result.has_value());
    f.unchanged();
    f.verify(f.adopt());
  }
}
void crash_recovery() {
#if defined(__unix__) || defined(__APPLE__)
  std::size_t completed = 0;
  for (auto fail : {FaultPoint::sample_after_artifact_creation,
      FaultPoint::sample_after_manifest_preparation, FaultPoint::sample_after_manifest_publication}) {
    Fixture f;
    const auto child = fork();
    LMDJ_CHECK(child >= 0);
    if (child == 0) {
      point = fail; crash = true; set_fault_hook(inject);
      (void)f.store.adopt_candidates(f.root, f.request);
      _exit(72);
    }
    int status = 0;
    LMDJ_CHECK(waitpid(child, &status, 0) == child);
    LMDJ_CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 71);
    if (fail == FaultPoint::sample_after_manifest_publication) {
      const auto loaded = f.store.load(f.root);
      LMDJ_CHECK(loaded.has_value());
      LMDJ_CHECK(loaded.value().revision == 2);
      f.verify(loaded.value());
      const auto repeat = f.store.adopt_candidates(f.root, f.request);
      LMDJ_CHECK(!repeat.has_value());
      LMDJ_CHECK(repeat.error().code == ErrorCode::revision_conflict);
    } else {
      // Recovery replays only committed history and removes unpublished history.
      const auto loaded = f.store.load(f.root);
      LMDJ_CHECK(loaded.has_value());
      LMDJ_CHECK(loaded.value() == f.before);
      f.verify(f.adopt());
    }
    ++completed;
  }
  std::cout << "candidate adoption crash recovery: " << completed << " crash points PASS\n";
#else
  std::cout << "candidate adoption crash recovery: SKIP (requires POSIX fork)\n";
#endif
}
void legacy_promotion_and_model_evidence() {
  Fixture f;
  for (const auto& entry : std::filesystem::directory_iterator(f.root / "history/checkpoints")) {
    auto checkpoint = Json::parse(read(entry.path()));
    checkpoint["contract"] = "lmdj.project.v4";
    std::ofstream out(entry.path()); out << checkpoint.dump();
  }
  const auto legacy = f.store.load(f.root);
  LMDJ_CHECK(legacy.has_value() && legacy.value().contract == ProjectContract::v4);
  for (auto& slot : f.request.slots)
    std::get<CapabilityAdoptionLineageDerivation>(slot.lineage.derivation).model_identity =
        ImplementationLineageIdentity{"test-model", "2.3.4", std::string(64, 'e')};
  const auto adopted = f.adopt();
  LMDJ_CHECK(adopted.contract == ProjectContract::v5);
  f.verify(adopted);
}

void tampered_identity_rejected() {
  for (const auto* field : {"project_id", "source_asset_id", "source_artifact", "extra_source_field"}) {
    Fixture f;
    f.adopt();
    for (const auto& entry : std::filesystem::directory_iterator(f.root / "history/transactions")) {
      auto encoded = Json::parse(read(entry.path()));
      if (encoded.at("command").at("type") != "AdoptCandidates") continue;
      if (std::string(field) == "source_artifact") encoded["command"][field]["byte_length"] = 99;
      else if (std::string(field) == "extra_source_field") encoded["command"]["source_artifact"]["extra"] = true;
      else encoded["command"][field] = uuid(99);
      std::ofstream out(entry.path()); out << encoded.dump();
    }
    LMDJ_CHECK(!f.store.load(f.root).has_value());
  }
}
}
int main() {
  try { unsupported_source_is_atomic(); success_and_explicit_repeat(); writer_source_checks(); failures(); crash_recovery(); legacy_promotion_and_model_evidence(); tampered_identity_rejected(); }
  catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
  std::cout << "candidate adoption ProjectIO: PASS\n";
}
