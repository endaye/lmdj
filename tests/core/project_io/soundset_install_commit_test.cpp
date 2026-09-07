// S11-D8: installing a Sound Set is one atomic Project mutation. N Assets and
// N Pad assignments settle as exactly one revision behind one manifest
// replacement, a fault anywhere before that replacement leaves every Project
// Truth projection untouched — including the multi-blob `assets/` directory —
// and a replayed command id returns the stored receipt without republishing.
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_store.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/legacy_project.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::AssetLineage;
using lmdj::domain::CommandMeta;
using lmdj::domain::PadPlayback;
using lmdj::domain::PadSlotId;
using lmdj::domain::ProjectContract;
using lmdj::domain::SoundSetInstallLineageDerivation;
using lmdj::domain::SoundSetLineageSource;
using lmdj::domain::TriggerMode;
using lmdj::domain::UpdatePadPlayback;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ProjectId;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::testing::FaultPoint;
using lmdj::test::downgrade_checkpoint_zero_to_v3;

constexpr std::uint8_t kBank = 2;
constexpr const char* kSetId = "30000000-0000-4000-8000-000000000009";
constexpr const char* kSetVersion = "1.2.0";

FaultPoint injected_point = FaultPoint::sample_after_event_preparation;
int injected_calls = 0;

lmdj::foundation::Result<void> inject_fault(
    FaultPoint point,
    const std::filesystem::path& path) {
  if (point != injected_point) {
    return lmdj::foundation::Result<void>::success();
  }
  ++injected_calls;
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected atomic Sound Set install fault",
          {{"path", path.generic_string()}},
      });
}

class FaultGuard {
 public:
  explicit FaultGuard(FaultPoint point) {
    injected_point = point;
    injected_calls = 0;
    lmdj::project_io::testing::set_fault_hook(inject_fault);
  }

  ~FaultGuard() { lmdj::project_io::testing::set_fault_hook(nullptr); }

  FaultGuard(const FaultGuard&) = delete;
  FaultGuard& operator=(const FaultGuard&) = delete;
};

class TempDirectory {
 public:
  explicit TempDirectory(std::string_view label) {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-soundset-install-" + std::string{label} + "-" +
             std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  LMDJ_CHECK(static_cast<bool>(stream));
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

std::string test_uuid(std::string_view seed) {
  std::uint64_t hash = 1469598103934665603ULL;
  for (const unsigned char character : seed) {
    hash ^= character;
    hash *= 1099511628211ULL;
  }
  constexpr std::string_view digits = "0123456789abcdef";
  std::string suffix(12, '0');
  for (std::size_t index = suffix.size(); index > 0; --index) {
    suffix.at(index - 1) = digits.at(hash & 0x0fU);
    hash >>= 4U;
  }
  return "00000000-0000-4000-8000-" + suffix;
}

std::vector<std::byte> slot_bytes(std::uint8_t slot) {
  std::vector<std::byte> bytes{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'}};
  for (std::uint8_t offset = 0; offset < 4; ++offset) {
    bytes.push_back(std::byte{static_cast<unsigned char>(slot + offset)});
  }
  return bytes;
}

std::string digest_of(const std::vector<std::byte>& bytes) {
  picosha2::hash256_one_by_one hasher;
  const auto* begin = reinterpret_cast<const unsigned char*>(bytes.data());
  hasher.process(begin, begin + bytes.size());
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

lmdj::domain::ProjectState new_v4_project() {
  // create_project already declares lmdj.project.v4; the assertion keeps this
  // fixture honest if that ever stops being true.
  auto project =
      lmdj::domain::create_project(ProjectId{test_uuid("project")}, 120);
  LMDJ_CHECK(project.has_value());
  LMDJ_CHECK(project.value().contract == ProjectContract::v4);
  return project.value();
}

struct InstallFixture {
  std::vector<std::vector<std::byte>> payloads;
  ProjectStore::SoundSetInstallRequest request;
};

// Three occupied Set slots mapped by S11-D11 identity onto pads 0, 1 and 5.
InstallFixture install_fixture(
    std::string_view command_seed,
    std::uint64_t expected_revision) {
  InstallFixture fixture{
      {},
      ProjectStore::SoundSetInstallRequest{
          CommandMeta{CommandId{test_uuid(command_seed)}, expected_revision},
          {},
      },
  };
  constexpr std::array<std::uint8_t, 3> slots{0, 1, 5};
  fixture.payloads.reserve(slots.size());
  for (const auto slot : slots) {
    fixture.payloads.push_back(slot_bytes(slot));
  }
  for (std::size_t index = 0; index < slots.size(); ++index) {
    const auto slot = slots.at(index);
    fixture.request.slots.push_back(
        ProjectStore::SoundSetInstallSlotRequest{
            PadSlotId{kBank, slot},
            AssetId{test_uuid("asset-" + std::to_string(slot))},
            "audio/wav",
            fixture.payloads.at(index),
            AssetLineage{
                SoundSetLineageSource{
                    kSetId,
                    kSetVersion,
                    std::string(64, 'e'),
                    slot,
                    digest_of(fixture.payloads.at(index)),
                },
                SoundSetInstallLineageDerivation{},
            },
        });
  }
  return fixture;
}

std::size_t directory_entry_count(const std::filesystem::path& path) {
  std::size_t count = 0;
  for (const auto& entry : std::filesystem::directory_iterator(path)) {
    (void)entry;
    ++count;
  }
  return count;
}

void test_install_commits_every_asset_and_pad_in_exactly_one_revision() {
  TempDirectory temp("one-revision");
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_v4_project()).has_value());
  auto fixture = install_fixture("install-command", 0);

  const auto installed = store.install_soundset(bundle, fixture.request);
  LMDJ_CHECK(installed.has_value());
  LMDJ_CHECK(!installed.value().replayed);
  LMDJ_CHECK(installed.value().state.revision == 1);
  LMDJ_CHECK(installed.value().event.at("revision") == 1);
  LMDJ_CHECK(installed.value().event.at("type") == "soundset.installed");

  // Exactly one revision: one transaction, one checkpoint, three blobs.
  LMDJ_CHECK(directory_entry_count(bundle / "history/transactions") == 1);
  LMDJ_CHECK(std::filesystem::exists(bundle / "history/checkpoints/1.json"));
  LMDJ_CHECK(!std::filesystem::exists(bundle / "history/checkpoints/2.json"));
  LMDJ_CHECK(directory_entry_count(bundle / "assets") == 3);
  LMDJ_CHECK(
      nlohmann::json::parse(read_bytes(bundle / "manifest.json"))
          .at("head_revision") == 1);

  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value().revision == 1);
  LMDJ_CHECK(reopened.value().assets.size() == 3);
  LMDJ_CHECK(reopened.value().contract == ProjectContract::v4);
  for (const auto& slot : fixture.request.slots) {
    const auto& pad = reopened.value().banks.at(kBank).at(slot.slot.pad);
    LMDJ_CHECK(pad.asset_id == slot.asset_id);
    const auto& asset = reopened.value().assets.at(slot.asset_id);
    LMDJ_CHECK(asset.lineage.has_value());
    const auto& source =
        std::get<SoundSetLineageSource>(asset.lineage->source);
    LMDJ_CHECK(source.set_id == kSetId);
    LMDJ_CHECK(source.set_version == kSetVersion);
    LMDJ_CHECK(source.slot_index == slot.slot.pad);
    LMDJ_CHECK(source.artifact_sha256 == asset.artifact.sha256);
    LMDJ_CHECK(std::holds_alternative<SoundSetInstallLineageDerivation>(
        asset.lineage->derivation));
    LMDJ_CHECK(std::filesystem::exists(
        bundle / "assets" / (asset.artifact.sha256 + ".wav")));
  }
  // S11-D12: pads under an empty Set slot are untouched.
  LMDJ_CHECK(!reopened.value().banks.at(kBank).at(2).asset_id.has_value());
}

void test_replayed_command_id_returns_the_stored_receipt() {
  TempDirectory temp("replay");
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_v4_project()).has_value());
  auto fixture = install_fixture("install-command", 0);
  const auto installed = store.install_soundset(bundle, fixture.request);
  LMDJ_CHECK(installed.has_value());
  const auto manifest_after_commit = read_bytes(bundle / "manifest.json");

  const auto replayed = store.install_soundset(bundle, fixture.request);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().event == installed.value().event);
  LMDJ_CHECK(replayed.value().state.revision == 1);
  LMDJ_CHECK(read_bytes(bundle / "manifest.json") == manifest_after_commit);
  LMDJ_CHECK(directory_entry_count(bundle / "history/transactions") == 1);
  LMDJ_CHECK(directory_entry_count(bundle / "assets") == 3);

  // The same command id bound to a different install is an identity collision.
  auto changed = install_fixture("install-command", 0);
  changed.request.slots.pop_back();
  const auto collision = store.install_soundset(bundle, changed.request);
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(bundle / "manifest.json") == manifest_after_commit);

  // A fresh command id at the committed revision still commits normally.
  auto second = install_fixture("second-install", 1);
  second.request.slots.erase(
      second.request.slots.begin(), second.request.slots.begin() + 2);
  second.request.slots.front().slot = PadSlotId{kBank, 9};
  second.request.slots.front().asset_id = AssetId{test_uuid("asset-9")};
  std::get<SoundSetLineageSource>(second.request.slots.front().lineage.source)
      .slot_index = 9;
  const auto again = store.install_soundset(bundle, second.request);
  LMDJ_CHECK(again.has_value());
  LMDJ_CHECK(again.value().state.revision == 2);
}

void test_faults_before_publication_preserve_every_project_truth_projection() {
  constexpr std::array fault_points{
      FaultPoint::sample_after_event_preparation,
      FaultPoint::sample_after_artifact_creation,
      FaultPoint::sample_after_manifest_preparation,
  };
  for (const auto point : fault_points) {
    TempDirectory temp("atomic");
    const auto bundle = temp.path() / "project.lmdj";
    ProjectStore store;
    LMDJ_CHECK(store.create(bundle, new_v4_project()).has_value());
    const auto original_manifest = read_bytes(bundle / "manifest.json");
    const auto original = store.load(bundle);
    LMDJ_CHECK(original.has_value());
    auto fixture = install_fixture("install-command", 0);

    lmdj::foundation::Result<lmdj::domain::AppliedCommand> result =
        lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
            lmdj::foundation::Error{
                ErrorCode::internal_error,
                "Sound Set install fault operation did not run",
            });
    {
      FaultGuard guard(point);
      result = store.install_soundset(bundle, fixture.request);
      LMDJ_CHECK(injected_calls == 1);
    }

    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::io_error);
    LMDJ_CHECK(read_bytes(bundle / "manifest.json") == original_manifest);
    const auto reopened = store.load(bundle);
    LMDJ_CHECK(reopened.has_value());
    LMDJ_CHECK(reopened.value() == original.value());
    LMDJ_CHECK(reopened.value().revision == 0);
    LMDJ_CHECK(reopened.value().assets.empty());
    for (const auto& slot : fixture.request.slots) {
      LMDJ_CHECK(
          !reopened.value().banks.at(kBank).at(slot.slot.pad).asset_id
               .has_value());
    }
    // Every published blob is rolled back, not just the first: a single-slot
    // rollback ledger would leave two orphans here.
    LMDJ_CHECK(std::filesystem::is_empty(bundle / "assets"));
    LMDJ_CHECK(
        !std::filesystem::exists(bundle / "history/checkpoints/1.json"));
    LMDJ_CHECK(std::filesystem::is_empty(bundle / "history/transactions"));
  }
}

void test_install_refuses_before_it_changes_anything() {
  TempDirectory temp("refusals");
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_v4_project()).has_value());
  const auto original_manifest = read_bytes(bundle / "manifest.json");

  ProjectStore::SoundSetInstallRequest empty{
      CommandMeta{CommandId{test_uuid("empty-install")}, 0}, {}};
  LMDJ_CHECK(!store.install_soundset(bundle, empty).has_value());

  auto bad_slot = install_fixture("bad-slot", 0);
  bad_slot.request.slots.front().slot = PadSlotId{4, 0};
  LMDJ_CHECK(!store.install_soundset(bundle, bad_slot.request).has_value());

  auto bad_media = install_fixture("bad-media", 0);
  bad_media.request.slots.front().media_type.clear();
  LMDJ_CHECK(!store.install_soundset(bundle, bad_media.request).has_value());

  auto bad_lineage = install_fixture("bad-lineage", 0);
  std::get<SoundSetLineageSource>(
      bad_lineage.request.slots.front().lineage.source)
      .set_version = "1.2";
  LMDJ_CHECK(!store.install_soundset(bundle, bad_lineage.request).has_value());

  // S11-D9 pins the Lineage digest to the Asset it describes.
  auto wrong_digest = install_fixture("wrong-digest", 0);
  std::get<SoundSetLineageSource>(
      wrong_digest.request.slots.at(1).lineage.source)
      .artifact_sha256 = std::string(64, '9');
  LMDJ_CHECK(!store.install_soundset(bundle, wrong_digest.request).has_value());

  // The generic artifact safety boundary refuses before any hashing or lease.
  const std::vector<std::byte> oversize(
      65U * 1024U * 1024U, std::byte{'x'});
  auto too_large = install_fixture("too-large", 0);
  too_large.request.slots.front().bytes = oversize;
  const auto refused_size = store.install_soundset(bundle, too_large.request);
  LMDJ_CHECK(!refused_size.has_value());
  LMDJ_CHECK(refused_size.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      refused_size.error().details.contains("maximum_byte_length"));

  auto stale = install_fixture("stale-install", 7);
  const auto conflicted = store.install_soundset(bundle, stale.request);
  LMDJ_CHECK(!conflicted.has_value());
  LMDJ_CHECK(conflicted.error().code == ErrorCode::revision_conflict);

  LMDJ_CHECK(read_bytes(bundle / "manifest.json") == original_manifest);
  LMDJ_CHECK(std::filesystem::is_empty(bundle / "assets"));
  LMDJ_CHECK(std::filesystem::is_empty(bundle / "history/transactions"));

  // A v3 Project has no Lineage carrier at all, so the install fails closed.
  // The fixture has to be downgraded on disk: a Project this Build creates
  // declares v4 and installs without a promoting command first.
  TempDirectory legacy_temp("legacy");
  const auto legacy_bundle = legacy_temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(legacy_bundle, new_v4_project()).has_value());
  downgrade_checkpoint_zero_to_v3(legacy_bundle);
  const auto legacy_opened = store.load(legacy_bundle);
  LMDJ_CHECK(legacy_opened.has_value());
  LMDJ_CHECK(legacy_opened.value().contract == ProjectContract::v3);
  auto legacy = install_fixture("legacy-install", 0);
  const auto refused = store.install_soundset(legacy_bundle, legacy.request);
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(std::filesystem::is_empty(legacy_bundle / "assets"));
}

void test_a_promoted_v3_project_still_reopens_after_an_install() {
  // Installing a Sound Set is a v4-only command, and a Project promoted to v4
  // by an earlier persist still has a v3 checkpoint zero. Reopening it replays
  // that install, so the replay has to start at the Contract level the head
  // checkpoint declares rather than at checkpoint zero's.
  TempDirectory temp("promoted-reopen");
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_v4_project()).has_value());
  downgrade_checkpoint_zero_to_v3(bundle);
  const auto opened = store.load(bundle);
  LMDJ_CHECK(opened.has_value());
  LMDJ_CHECK(opened.value().contract == ProjectContract::v3);

  const auto promoted = store.execute(
      bundle,
      UpdatePadPlayback{
          CommandMeta{CommandId{test_uuid("promote-before-install")}, 0},
          PadSlotId{3, 3},
          PadPlayback{4, 12, TriggerMode::gate, 6000, true},
      });
  LMDJ_CHECK(promoted.has_value());
  LMDJ_CHECK(promoted.value().state.contract == ProjectContract::v4);

  auto fixture = install_fixture("promoted-install", 1);
  const auto installed = store.install_soundset(bundle, fixture.request);
  LMDJ_CHECK(installed.has_value());
  LMDJ_CHECK(installed.value().state.revision == 2);

  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value() == installed.value().state);
  LMDJ_CHECK(reopened.value().contract == ProjectContract::v4);
  for (const auto& slot : fixture.request.slots) {
    LMDJ_CHECK(
        reopened.value().banks.at(kBank).at(slot.slot.pad).asset_id ==
        slot.asset_id);
  }
}

}  // namespace

int main() {
  try {
    test_install_commits_every_asset_and_pad_in_exactly_one_revision();
    test_replayed_command_id_returns_the_stored_receipt();
    test_faults_before_publication_preserve_every_project_truth_projection();
    test_install_refuses_before_it_changes_anything();
    test_a_promoted_v3_project_still_reopens_after_an_install();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "soundset install commit tests: PASS\n";
  return 0;
}
