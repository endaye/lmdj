// Stage 11 Task 4: the install quota rehearsal.
//
// S11-D8 forbids reusing S11-D7's deduplicated download accounting as the
// prepared-PCM budget: an install is charged per target Pad, so one Artifact
// on two Pads is two residencies. The Fixture Foundry Set is built for exactly
// this — its slot 12 declares slot 0's Artifact — so a per-hash charge and a
// per-Pad charge differ by one slot's worth of prepared PCM and a limit set
// between them tells them apart.
//
// Both quotas are decided through the existing `assess_runtime_quota`
// binding-constraint rule before any Project mutation, and
// `occupied_pad_policy` is not a way around either of them.
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>
#include <lmdj/foundation/json.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::RuntimePreparationLimits;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::facade::InitialProjectRequest;
using lmdj::facade::SoundSetCatalogSource;
using lmdj::domain::Pattern;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::project_io::CatalogTransport;

constexpr std::string_view kFoundrySetId =
    "11111111-1111-4111-8111-111111111111";
constexpr std::string_view kFoundryManifest =
    "33175f66912a9add3e4e551d19d85072adcd1f0331fcc9fed80ab0bc18dd9111";
constexpr std::string_view kAttributionSetId =
    "22222222-2222-4222-8222-222222222222";
constexpr std::string_view kAttributionManifest =
    "ae578e4f6a383994fb15fd984d7906e346ee7bcb6d7add763c8da9317a313bb4";
constexpr std::string_view kSetVersion = "1.0.0";

// Every fixture blob prepares to 2880 frames of 48 kHz mono-equivalent float
// PCM, so one Pad costs 2880 * sizeof(float) bytes. The Foundry Set occupies
// eleven Pads across ten unique Artifacts: eleven charges under S11-D8, ten if
// anything ever deduplicated them.
constexpr std::uint64_t kPadPreparedBytes = 2880U * 4U;
constexpr std::uint64_t kFoundryPads = 11U;
constexpr std::uint64_t kFoundryUniqueArtifacts = 10U;
constexpr std::uint64_t kFoundryPreparedBytes =
    kFoundryPads * kPadPreparedBytes;
constexpr std::uint64_t kAttributionPreparedBytes = 4U * kPadPreparedBytes;
constexpr std::uint64_t kSpaciousBytes = 1U << 30U;

class TempDirectory {
 public:
  explicit TempDirectory(std::string_view label) {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-soundset-quota-" + std::string{label} + "-" +
             std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }

  TempDirectory(const TempDirectory&) = delete;
  TempDirectory& operator=(const TempDirectory&) = delete;

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::string read_text(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  LMDJ_CHECK(static_cast<bool>(stream));
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

std::filesystem::path flatten_fixture_corpus(const TempDirectory& temp) {
  const auto root = temp.path() / "catalog-objects";
  std::filesystem::create_directories(root);
  for (const auto* kind : {"manifest", "blob"}) {
    const std::filesystem::path source =
        std::filesystem::path("tests/fixtures/soundset") / kind;
    LMDJ_CHECK(std::filesystem::is_directory(source));
    for (const auto& entry : std::filesystem::directory_iterator(source)) {
      if (!entry.is_regular_file()) {
        continue;
      }
      std::filesystem::copy_file(
          entry.path(),
          root / entry.path().filename(),
          std::filesystem::copy_options::overwrite_existing);
    }
  }
  return root;
}

class FixtureCatalogSource final : public SoundSetCatalogSource {
 public:
  explicit FixtureCatalogSource() {
    bytes_ = read_text("tests/fixtures/soundset/catalog/index.json");
  }

  lmdj::foundation::Result<std::vector<std::byte>> read_index(
      std::uint64_t maximum_bytes) override {
    if (bytes_.size() > maximum_bytes) {
      return lmdj::foundation::Result<std::vector<std::byte>>::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::io_error,
              "fixture Catalog index exceeds the requested bound",
              {{"reason", "catalog_unavailable"}},
          });
    }
    std::vector<std::byte> copy(bytes_.size());
    for (std::size_t index = 0; index < bytes_.size(); ++index) {
      copy[index] = static_cast<std::byte>(bytes_[index]);
    }
    return lmdj::foundation::Result<std::vector<std::byte>>::success(
        std::move(copy));
  }

 private:
  std::string bytes_;
};

ApplicationConfig config(
    const std::filesystem::path& root,
    std::shared_ptr<CatalogTransport> transport,
    RuntimePreparationLimits limits) {
  return ApplicationConfig{
      root,
      nullptr,
      {},
      {},
      limits,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
      lmdj::facade::make_unavailable_performance_replay_controller(),
      nullptr,
      std::move(transport),
      std::make_shared<FixtureCatalogSource>(),
      std::nullopt,
  };
}

RuntimePreparationLimits limits(
    std::uint64_t bank_bytes,
    std::uint64_t generation_bytes) {
  return RuntimePreparationLimits{
      1U << 20U,
      bank_bytes,
      generation_bytes,
      kSpaciousBytes,
  };
}

std::string uuid(std::uint32_t ordinal) {
  auto value = std::string("00000000-0000-4000-8000-000000000000");
  constexpr std::string_view digits = "0123456789abcdef";
  for (std::size_t index = value.size(); index > value.size() - 8; --index) {
    value.at(index - 1) = digits.at(ordinal & 0x0fU);
    ordinal >>= 4U;
  }
  return value;
}

// A Facade-created Project is `lmdj.project.v5` from its first persist, so a
// Sound Set installs into it with no intervening command. This is the path a
// first-run user takes.
std::filesystem::path create_project(
    Application& application,
    const std::filesystem::path& root,
    std::uint32_t ordinal) {
  const auto project = root / ("project-" + std::to_string(ordinal) + ".lmdj");
  const PatternId pattern_id{uuid(ordinal + 1)};
  LMDJ_CHECK(application
                 .create_initial_project(InitialProjectRequest{
                     project,
                     ProjectId{uuid(ordinal)},
                     120,
                     Pattern{pattern_id, 1, {}},
                 })
                 .has_value());
  return project;
}

nlohmann::json inspect_project(
    const Application& application,
    const std::filesystem::path& project) {
  const auto response = application.query({
      {"operation", "project.inspect"},
      {"project_path", project.generic_string()},
  });
  LMDJ_CHECK(response.at("ok").get<bool>());
  return response.at("result").at("project");
}

nlohmann::json install_request(
    const std::filesystem::path& project,
    std::string_view command_id,
    std::uint64_t expected_revision,
    std::uint8_t bank,
    std::string_view set_id,
    std::string_view manifest_sha256) {
  return {
      {"operation", "soundset.install"},
      {"project_path", project.generic_string()},
      {"command_id", command_id},
      {"expected_revision", expected_revision},
      {"bank_id", bank},
      {"set_id", set_id},
      {"version", kSetVersion},
      {"manifest_sha256", manifest_sha256},
  };
}

void publish_fixture_sets(Application& application) {
  const auto listing =
      application.query({{"operation", "soundset.catalog.list"}});
  LMDJ_CHECK(listing.at("ok").get<bool>());
  LMDJ_CHECK(listing.at("result").at("sets").size() == 3);
}

// A duplicate Artifact on two Pads is two residencies, so the eleven-Pad
// Foundry install costs eleven charges. A limit above ten charges and below
// eleven admits a per-hash charge and refuses a per-Pad one.
void test_a_duplicate_artifact_on_two_pads_is_charged_twice() {
  TempDirectory temp("duplicate-charge");
  const auto objects = flatten_fixture_corpus(temp);
  static_assert(
      kFoundryUniqueArtifacts * kPadPreparedBytes < kFoundryPreparedBytes,
      "the duplicate charge must be observable in the limit");
  const auto dedup_would_fit =
      kFoundryUniqueArtifacts * kPadPreparedBytes + kPadPreparedBytes / 2U;

  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(objects),
      limits(dedup_would_fit, kSpaciousBytes)));
  publish_fixture_sets(application);
  const auto project = create_project(application, temp.path(), 0x400);
  const auto before = inspect_project(application, project);

  const auto refused = application.command(install_request(
      project,
      uuid(0x410),
      before.at("revision").get<std::uint64_t>(),
      1,
      kFoundrySetId,
      kFoundryManifest));
  LMDJ_CHECK(!refused.at("ok").get<bool>());
  LMDJ_CHECK(refused.at("error").at("code") == "BANK_QUOTA_EXHAUSTED");
  const auto& details = refused.at("error").at("details");
  LMDJ_CHECK(details.at("bank") == 1);
  LMDJ_CHECK(details.at("requested_bytes") == kFoundryPreparedBytes);
  LMDJ_CHECK(details.at("requested_frames") == kFoundryPads * 2880U);
  LMDJ_CHECK(details.at("quota_bytes") == dedup_would_fit);
  // Nothing was installed, so the target Bank reports no residency yet.
  LMDJ_CHECK(details.at("consumed").empty());
  LMDJ_CHECK(inspect_project(application, project) == before);

  // The same install fits a Bank quota of exactly the eleven charges, which
  // pins the accounting rather than only its direction.
  Application exact(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(objects),
      limits(kFoundryPreparedBytes, kSpaciousBytes)));
  const auto installed = exact.command(install_request(
      project,
      uuid(0x420),
      before.at("revision").get<std::uint64_t>(),
      1,
      kFoundrySetId,
      kFoundryManifest));
  LMDJ_CHECK(installed.at("ok").get<bool>());
  LMDJ_CHECK(installed.at("result").at("installed").size() == kFoundryPads);
}

// The generation ledger is the whole Project, and its refusal is the existing
// PROJECT_QUOTA_EXHAUSTED with its existing details. Zero change either way.
void test_the_generation_quota_refuses_with_zero_change() {
  TempDirectory temp("generation-quota");
  const auto objects = flatten_fixture_corpus(temp);
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(objects),
      limits(kSpaciousBytes, kFoundryPreparedBytes - 1U)));
  publish_fixture_sets(application);
  const auto project = create_project(application, temp.path(), 0x500);
  const auto before = inspect_project(application, project);

  const auto refused = application.command(install_request(
      project,
      uuid(0x510),
      before.at("revision").get<std::uint64_t>(),
      0,
      kFoundrySetId,
      kFoundryManifest));
  LMDJ_CHECK(!refused.at("ok").get<bool>());
  LMDJ_CHECK(refused.at("error").at("code") == "PROJECT_QUOTA_EXHAUSTED");
  const auto& details = refused.at("error").at("details");
  LMDJ_CHECK(details.at("requested_bytes") == kFoundryPreparedBytes);
  LMDJ_CHECK(details.at("project_used_bytes") == 0);
  LMDJ_CHECK(
      details.at("project_quota_bytes") == kFoundryPreparedBytes - 1U);
  LMDJ_CHECK(details.at("banks").size() == 4);
  LMDJ_CHECK(inspect_project(application, project) == before);
}

// #465 Q2: the policy decides which Pads are written, never whether the write
// fits. `keep` leaves the colliding Pads' Assets in the Bank ledger and
// `replace` puts its own in their place; with this Bank quota neither fits.
void test_occupied_pad_policy_never_bypasses_quota() {
  TempDirectory temp("policy-quota");
  const auto objects = flatten_fixture_corpus(temp);
  {
    Application spacious(config(
        temp.path(),
        lmdj::project_io::make_local_directory_catalog_transport(objects),
        limits(kSpaciousBytes, kSpaciousBytes)));
    publish_fixture_sets(spacious);
    const auto project = create_project(spacious, temp.path(), 0x600);
    const auto seeded = spacious.command(install_request(
        project,
        uuid(0x610),
        inspect_project(spacious, project)
            .at("revision")
            .get<std::uint64_t>(),
        3,
        kAttributionSetId,
        kAttributionManifest));
    LMDJ_CHECK(seeded.at("ok").get<bool>());
  }

  const auto project = temp.path() / "project-1536.lmdj";
  // `keep` writes the Foundry Set's seven free Pads on top of the Attribution
  // Kit's four, and `replace` writes all eleven of its own: both land on
  // eleven Pads' worth of prepared PCM.
  static_assert(
      kAttributionPreparedBytes + 7U * kPadPreparedBytes ==
          kFoundryPreparedBytes,
      "keep and replace must cost the same here for the test to be about "
      "the policy rather than about the arithmetic");
  Application tight(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(objects),
      limits(kFoundryPreparedBytes - 1U, kSpaciousBytes)));
  const auto before = inspect_project(tight, project);

  for (const auto* policy : {"keep", "replace"}) {
    auto request = install_request(
        project,
        uuid(policy[0] == 'k' ? 0x620 : 0x630),
        before.at("revision").get<std::uint64_t>(),
        3,
        kFoundrySetId,
        kFoundryManifest);
    request["occupied_pad_policy"] = policy;
    const auto refused = tight.command(request);
    LMDJ_CHECK(!refused.at("ok").get<bool>());
    LMDJ_CHECK(refused.at("error").at("code") == "BANK_QUOTA_EXHAUSTED");
    LMDJ_CHECK(inspect_project(tight, project) == before);
  }

  // The refusal is the quota, not the policy: the same two requests succeed
  // once the Bank quota admits eleven Pads.
  Application admitted(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(objects),
      limits(kFoundryPreparedBytes, kSpaciousBytes)));
  auto keep = install_request(
      project,
      uuid(0x640),
      before.at("revision").get<std::uint64_t>(),
      3,
      kFoundrySetId,
      kFoundryManifest);
  keep["occupied_pad_policy"] = "keep";
  const auto kept = admitted.command(keep);
  LMDJ_CHECK(kept.at("ok").get<bool>());
  LMDJ_CHECK(kept.at("result").at("installed").size() == 7);
}

}  // namespace

int main() {
  try {
    test_a_duplicate_artifact_on_two_pads_is_charged_twice();
    test_the_generation_quota_refuses_with_zero_change();
    test_occupied_pad_policy_never_bypasses_quota();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
