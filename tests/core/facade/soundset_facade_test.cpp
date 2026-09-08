// Stage 11 Task 4: the locked Sound Set Facade surface.
//
// The five operations of the plan's Locked Facade Surface are
// `soundset.catalog.list`, `soundset.inspect`, `soundset.map.preview`,
// `soundset.install` and `soundset.audition`. This binary owns their
// request contract, the Catalog and Set Store behaviour behind them, S11-D3
// audio validation and the S11-D5/D8/D12 zero-Project-change guarantees.
// Quota rehearsal lives in `soundset_install_quota_test.cpp` so neither
// binary carries both budgets.
//
// Everything runs against the real fixture corpus in `tests/fixtures/soundset`
// through the real local directory `CatalogTransport`: real canonical
// manifests, real PCM16 WAV blobs, a real hash mismatch and a real 22.05 kHz
// blob. Only the Catalog *index* is a test double, because a Catalog endpoint
// is Host state by S11-D6 and Core never reaches one.
#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <optional>
#include <source_location>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/facade/application.hpp>
#include <lmdj/foundation/json.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::facade::InitialProjectRequest;
using lmdj::facade::SoundSetCatalogSource;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::project_io::CatalogObjectRef;
using lmdj::project_io::CatalogTransport;

constexpr std::string_view kFoundrySetId =
    "11111111-1111-4111-8111-111111111111";
constexpr std::string_view kFoundryManifest =
    "33175f66912a9add3e4e551d19d85072adcd1f0331fcc9fed80ab0bc18dd9111";
constexpr std::string_view kAttributionSetId =
    "22222222-2222-4222-8222-222222222222";
constexpr std::string_view kAttributionManifest =
    "ae578e4f6a383994fb15fd984d7906e346ee7bcb6d7add763c8da9317a313bb4";
constexpr std::string_view kUnsupportedSetId =
    "33333333-3333-4333-8333-333333333333";
constexpr std::string_view kUnsupportedManifest =
    "57ab3bf8e01efe6a044639a53ee2e339627e3c3ee5a53b04e387ed640df2e64c";
constexpr std::string_view kTamperedSetId =
    "44444444-4444-4444-8444-444444444444";
constexpr std::string_view kMismatchedSetId =
    "55555555-5555-4555-8555-555555555555";
constexpr std::string_view kMismatchedManifest =
    "68500bf29592c9de307d6682c1b66c957635733e01cf9aee34dfd20aa2cf8ce6";
// Foundry CC0's set-level `demo` is a standalone blob no slot references;
// its slots 0 and 12 share one Artifact and its slots 10, 11 and 13-15 are
// empty.
constexpr std::string_view kFoundryDemoArtifact =
    "644fe37aef9fcb3d645b87105461b040453523784ce115cf38fd4c539e8813a2";
constexpr std::string_view kFoundrySlotZeroArtifact =
    "10b24f4f256ba6d2dde5a63dbd797bf3b707cb533a987bed72ea2242d6546e13";
constexpr std::string_view kUnallowlistedSetId =
    "66666666-6666-4666-8666-666666666666";
constexpr std::string_view kUnattributedSetId =
    "77777777-7777-4777-8777-777777777777";
constexpr std::string_view kSetVersion = "1.0.0";

class TempDirectory {
 public:
  explicit TempDirectory(std::string_view label) {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-soundset-facade-" + std::string{label} + "-" +
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

// The local adapter maps a lowercase sha256 to one basename under one root, so
// the corpus's `manifest/` and `blob/` split flattens into a single directory
// without any collision: every name is the digest of its own bytes.
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

nlohmann::json fixture_catalog_index() {
  const auto text = read_text("tests/fixtures/soundset/catalog/index.json");
  return nlohmann::json::parse(text);
}

// The Host side of S11-D6. `bytes` is whatever the Host's Catalog endpoint
// last produced; `available` models an endpoint that cannot be reached.
class FakeCatalogSource final : public SoundSetCatalogSource {
 public:
  lmdj::foundation::Result<std::vector<std::byte>> read_index(
      std::uint64_t maximum_bytes) override {
    ++reads;
    if (!available) {
      return lmdj::foundation::Result<std::vector<std::byte>>::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::io_error,
              "fixture Catalog endpoint is unreachable",
              {{"reason", "catalog_unavailable"}},
          });
    }
    if (bytes.size() > maximum_bytes) {
      return lmdj::foundation::Result<std::vector<std::byte>>::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::io_error,
              "fixture Catalog index exceeds the requested bound",
              {{"reason", "catalog_unavailable"}},
          });
    }
    std::vector<std::byte> copy(bytes.size());
    for (std::size_t index = 0; index < bytes.size(); ++index) {
      copy[index] = static_cast<std::byte>(bytes[index]);
    }
    return lmdj::foundation::Result<std::vector<std::byte>>::success(
        std::move(copy));
  }

  void publish(const nlohmann::json& index) {
    bytes = lmdj::foundation::canonical_json(index);
  }

  std::string bytes;
  bool available = true;
  int reads = 0;
};

// A transport that resolves nothing, so a cached Set has to carry the whole
// call on its own.
class UnreachableTransport final : public CatalogTransport {
 public:
  lmdj::foundation::Result<std::vector<std::byte>> read_object(
      const CatalogObjectRef& object,
      std::uint64_t maximum_bytes) override {
    (void)object;
    (void)maximum_bytes;
    return lmdj::foundation::Result<std::vector<std::byte>>::failure(
        lmdj::foundation::Error{
            lmdj::foundation::ErrorCode::io_error,
            "fixture Catalog transport is unreachable",
            {{"reason", "catalog_unavailable"}},
        });
  }
};

ApplicationConfig config(
    const std::filesystem::path& root,
    std::shared_ptr<CatalogTransport> transport,
    std::shared_ptr<SoundSetCatalogSource> source,
    std::optional<lmdj::audio::RuntimePreparationLimits> limits =
        std::nullopt) {
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
      std::move(source),
      std::nullopt,
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

// A Facade-created Project is `lmdj.project.v4` from its first persist, so a
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

const nlohmann::json& bank_pads(
    const nlohmann::json& project,
    std::uint8_t bank) {
  return project.at("banks").at(bank).at("pads");
}

nlohmann::json catalog_list(Application& application) {
  return application.query({{"operation", "soundset.catalog.list"}});
}

nlohmann::json inspect_set(
    const Application& application,
    std::string_view set_id,
    std::string_view manifest_sha256) {
  return application.query({
      {"operation", "soundset.inspect"},
      {"set_id", set_id},
      {"version", kSetVersion},
      {"manifest_sha256", manifest_sha256},
  });
}

// S11-D5's two layers through one request shape: no `slot_index` auditions
// the set-level `demo`, a `slot_index` auditions that slot's Artifact.
nlohmann::json audition_set(
    const Application& application,
    std::string_view set_id,
    std::string_view manifest_sha256,
    std::optional<std::uint8_t> slot_index = std::nullopt) {
  nlohmann::json request{
      {"operation", "soundset.audition"},
      {"set_id", set_id},
      {"version", kSetVersion},
      {"manifest_sha256", manifest_sha256},
  };
  if (slot_index.has_value()) {
    request["slot_index"] = *slot_index;
  }
  return application.query(request);
}

nlohmann::json map_preview(
    const Application& application,
    const std::filesystem::path& project,
    std::uint8_t bank,
    std::string_view set_id,
    std::string_view manifest_sha256) {
  return application.query({
      {"operation", "soundset.map.preview"},
      {"project_path", project.generic_string()},
      {"bank_id", bank},
      {"set_id", set_id},
      {"version", kSetVersion},
      {"manifest_sha256", manifest_sha256},
  });
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

const nlohmann::json& listed_set(
    const nlohmann::json& listing,
    std::string_view set_id) {
  for (const auto& entry : listing.at("result").at("sets")) {
    if (entry.at("set_id") == set_id) {
      return entry;
    }
  }
  LMDJ_CHECK(false);
  return listing;
}

bool listing_contains(const nlohmann::json& listing, std::string_view set_id) {
  return std::ranges::any_of(
      listing.at("result").at("sets"),
      [set_id](const nlohmann::json& entry) {
        return entry.at("set_id") == set_id;
      });
}

std::string refusal_reason(
    const nlohmann::json& listing,
    std::string_view set_id) {
  for (const auto& entry : listing.at("result").at("refused")) {
    if (entry.at("set_id") == set_id) {
      return entry.at("reason").is_string()
                 ? entry.at("reason").get<std::string>()
                 : std::string{};
    }
  }
  return {};
}

// The caller's line, not this helper's: several tests assert a refusal, and a
// failure has to name which one.
void check_refusal(
    const nlohmann::json& response,
    std::string_view code,
    std::string_view reason,
    const std::source_location location = std::source_location::current()) {
  lmdj::test::check(
      !response.at("ok").get<bool>(), "response is a refusal", location);
  lmdj::test::check(
      response.at("error").at("code") == code, "refusal code", location);
  lmdj::test::check(
      response.at("error").at("details").at("reason") == reason,
      "refusal details.reason",
      location);
}

void require_registered(
    Application& application,
    std::string_view operation,
    bool command) {
  const nlohmann::json request{{"operation", operation}};
  const auto accepted =
      command ? application.command(request) : application.query(request);
  // `soundset.catalog.list` takes no field beyond `operation`, so a bare
  // request is a complete one and succeeds; the other three refuse for a
  // reason that must not be "the operation does not exist".
  if (!accepted.at("ok").get<bool>()) {
    LMDJ_CHECK(accepted.at("error").at("message") != "operation is unknown");
  }

  const auto wrong_method =
      command ? application.query(request) : application.command(request);
  LMDJ_CHECK(!wrong_method.at("ok").get<bool>());
  LMDJ_CHECK(
      wrong_method.at("error").at("message") ==
      "operation was sent to the wrong Application method");
}

void test_locked_operations_are_registered_with_exact_kinds() {
  TempDirectory temp("registration");
  Application application(config(temp.path(), nullptr, nullptr));

  require_registered(application, "soundset.catalog.list", false);
  require_registered(application, "soundset.inspect", false);
  require_registered(application, "soundset.map.preview", false);
  require_registered(application, "soundset.install", true);
  require_registered(application, "soundset.audition", false);
}

// Every Sound Set operation resolves the Set Store and the Catalog cache from
// `ApplicationConfig.workspace_root`, exactly like `provider.list`, so a
// request that names a Workspace is as invalid as any other extra field.
void test_locked_requests_reject_extra_fields() {
  TempDirectory temp("exact-keys");
  Application application(config(temp.path(), nullptr, nullptr));
  const auto workspace = temp.path().generic_string();
  const auto project = (temp.path() / "absent.lmdj").generic_string();

  const auto stray_list = application.query({
      {"operation", "soundset.catalog.list"},
      {"workspace_path", workspace},
  });
  LMDJ_CHECK(!stray_list.at("ok").get<bool>());
  LMDJ_CHECK(stray_list.at("error").at("code") == "INVALID_ARGUMENT");
  LMDJ_CHECK(
      stray_list.at("error").at("message") ==
      "soundset.catalog.list request shape is invalid");

  const auto stray_inspect = application.query({
      {"operation", "soundset.inspect"},
      {"set_id", kFoundrySetId},
      {"version", kSetVersion},
      {"manifest_sha256", kFoundryManifest},
      {"workspace_path", workspace},
  });
  LMDJ_CHECK(
      stray_inspect.at("error").at("message") ==
      "soundset.inspect request shape is invalid");

  const auto stray_preview = application.query({
      {"operation", "soundset.map.preview"},
      {"project_path", project},
      {"bank_id", 0},
      {"set_id", kFoundrySetId},
      {"version", kSetVersion},
      {"manifest_sha256", kFoundryManifest},
      {"workspace_path", workspace},
  });
  LMDJ_CHECK(
      stray_preview.at("error").at("message") ==
      "soundset.map.preview request shape is invalid");

  auto stray_install = install_request(
      project, uuid(1), 0, 0, kFoundrySetId, kFoundryManifest);
  stray_install["workspace_path"] = workspace;
  LMDJ_CHECK(
      application.command(stray_install).at("error").at("message") ==
      "soundset.install request shape is invalid");

  // A missing required field and an unknown policy value fail the same way.
  auto no_bank = install_request(
      project, uuid(2), 0, 0, kFoundrySetId, kFoundryManifest);
  no_bank.erase("bank_id");
  LMDJ_CHECK(
      application.command(no_bank).at("error").at("message") ==
      "soundset.install request shape is invalid");

  auto bad_policy = install_request(
      project, uuid(3), 0, 0, kFoundrySetId, kFoundryManifest);
  bad_policy["occupied_pad_policy"] = "overwrite";
  LMDJ_CHECK(
      application.command(bad_policy).at("error").at("message") ==
      "occupied_pad_policy must be keep or replace");

  // The audition is Workspace-level for the same reason the other two
  // Workspace operations are, so it refuses a Workspace field, and its
  // `slot_index` is the only field it accepts beyond the Set identity.
  const auto stray_audition = application.query({
      {"operation", "soundset.audition"},
      {"set_id", kFoundrySetId},
      {"version", kSetVersion},
      {"manifest_sha256", kFoundryManifest},
      {"workspace_path", workspace},
  });
  LMDJ_CHECK(
      stray_audition.at("error").at("message") ==
      "soundset.audition request shape is invalid");

  auto audition_with_project = nlohmann::json{
      {"operation", "soundset.audition"},
      {"project_path", project},
      {"set_id", kFoundrySetId},
      {"version", kSetVersion},
      {"manifest_sha256", kFoundryManifest},
  };
  LMDJ_CHECK(
      application.query(audition_with_project).at("error").at("message") ==
      "soundset.audition request shape is invalid");

  const auto out_of_range = audition_set(
      application, kFoundrySetId, kFoundryManifest, 16);
  LMDJ_CHECK(!out_of_range.at("ok").get<bool>());
  LMDJ_CHECK(out_of_range.at("error").at("code") == "INVALID_ARGUMENT");
  LMDJ_CHECK(
      out_of_range.at("error").at("message") == "slot_index is out of range");
}

// #465 Q1 case 3: one eligibility for listing, preview, download and install.
// A Set the Catalog offers but whose manifest or bytes fail closed never
// reaches the Set Store, and the Catalog's other entries are unaffected.
void test_catalog_list_publishes_only_eligible_sets() {
  TempDirectory temp("catalog-list");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));

  const auto listing = catalog_list(application);
  LMDJ_CHECK(listing.at("ok").get<bool>());
  LMDJ_CHECK(listing.at("result").at("catalog_available").get<bool>());
  LMDJ_CHECK(listing.at("result").at("sets").size() == 3);

  LMDJ_CHECK(listing_contains(listing, kFoundrySetId));
  LMDJ_CHECK(listing_contains(listing, kAttributionSetId));
  // A Set whose audio is not S8-D6 is still a well-formed, eligible package;
  // S11-D3 is decided at inspect, preview and install, not at download.
  LMDJ_CHECK(listing_contains(listing, kUnsupportedSetId));

  LMDJ_CHECK(!listing_contains(listing, kTamperedSetId));
  LMDJ_CHECK(!listing_contains(listing, kMismatchedSetId));
  LMDJ_CHECK(!listing_contains(listing, kUnallowlistedSetId));
  LMDJ_CHECK(!listing_contains(listing, kUnattributedSetId));

  LMDJ_CHECK(
      refusal_reason(listing, kTamperedSetId) == "soundset_content_mismatch");
  LMDJ_CHECK(
      refusal_reason(listing, kMismatchedSetId) ==
      "soundset_license_ineligible");
  LMDJ_CHECK(
      refusal_reason(listing, kUnallowlistedSetId) ==
      "soundset_license_ineligible");
  LMDJ_CHECK(
      refusal_reason(listing, kUnattributedSetId) ==
      "soundset_license_ineligible");

  // The CC-BY-4.0 attribution string is the authoritative credit a Host shows
  // on listing, so it comes from the verified manifest, not the summary.
  const auto& attribution = listed_set(listing, kAttributionSetId);
  LMDJ_CHECK(
      attribution.at("license").at("attribution") ==
      "Fixture Attribution Kit by Bea Waveform (CC BY 4.0)");
  LMDJ_CHECK(attribution.at("license").at("spdx_id") == "CC-BY-4.0");
  LMDJ_CHECK(attribution.at("total_bytes") == 34788);
  LMDJ_CHECK(attribution.at("has_demo").get<bool>());

  const auto& foundry = listed_set(listing, kFoundrySetId);
  LMDJ_CHECK(foundry.at("manifest_sha256") == kFoundryManifest);
  LMDJ_CHECK(foundry.at("occupied_slots").size() == 11);
  LMDJ_CHECK(foundry.at("bpm") == 120);
  LMDJ_CHECK(foundry.at("key") == "Am");
}

// S11-D7: an unreachable Catalog is not fatal. Every published Set stays
// listable and inspectable, and its eligibility is decided by the cached
// manifest alone (#465 Q1 case 5).
void test_cached_sets_survive_an_unreachable_catalog() {
  TempDirectory temp("offline");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  auto transport = lmdj::project_io::make_local_directory_catalog_transport(
      flatten_fixture_corpus(temp));
  {
    Application online(config(temp.path(), transport, source));
    LMDJ_CHECK(catalog_list(online).at("ok").get<bool>());
  }

  auto offline_source = std::make_shared<FakeCatalogSource>();
  offline_source->available = false;
  Application offline(config(
      temp.path(),
      std::make_shared<UnreachableTransport>(),
      offline_source));

  const auto listing = catalog_list(offline);
  LMDJ_CHECK(listing.at("ok").get<bool>());
  LMDJ_CHECK(!listing.at("result").at("catalog_available").get<bool>());
  LMDJ_CHECK(listing.at("result").at("sets").size() == 3);
  LMDJ_CHECK(listing_contains(listing, kFoundrySetId));
  LMDJ_CHECK(offline_source->reads > 0);

  const auto inspected =
      inspect_set(offline, kFoundrySetId, kFoundryManifest);
  LMDJ_CHECK(inspected.at("ok").get<bool>());
  LMDJ_CHECK(inspected.at("result").at("slots").size() == 16);
}

// #465 Q1 case 3: a `license_summary` that no longer matches the verified
// manifest makes the Set ineligible wherever it is used, and the reachable
// Catalog is what makes that mismatch observable.
void test_catalog_summary_mismatch_is_ineligible_at_inspect() {
  TempDirectory temp("summary-mismatch");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());
  LMDJ_CHECK(
      inspect_set(application, kFoundrySetId, kFoundryManifest)
          .at("ok")
          .get<bool>());

  auto index = fixture_catalog_index();
  for (auto& entry : index.at("entries")) {
    if (entry.at("set_id") == kFoundrySetId) {
      entry.at("license_summary").at("rights_holder") = "Impostor Records";
    }
  }
  source->publish(index);

  check_refusal(
      inspect_set(application, kFoundrySetId, kFoundryManifest),
      "PERMISSION_DENIED",
      "soundset_license_ineligible");
  // One eligibility for every use, the audition included: a Set the Catalog
  // now disagrees with is not auditionable either.
  check_refusal(
      audition_set(application, kFoundrySetId, kFoundryManifest),
      "PERMISSION_DENIED",
      "soundset_license_ineligible");
  // The Set does not silently vanish from the listing: it is named among the
  // refusals with the reason that made it ineligible.
  const auto listing = catalog_list(application);
  LMDJ_CHECK(!listing_contains(listing, kFoundrySetId));
  LMDJ_CHECK(
      refusal_reason(listing, kFoundrySetId) == "soundset_license_ineligible");
}

// S11-D3: the project-cooker WAV reader decides Sound Set audio, and the
// Facade attaches the locked reason. Inspect, preview and install all refuse,
// and no Project changes on any of the three paths.
void test_unsupported_audio_is_refused_with_zero_project_change() {
  TempDirectory temp("unsupported-audio");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());
  const auto project = create_project(application, temp.path(), 0x100);
  const auto before = inspect_project(application, project);

  const auto inspected =
      inspect_set(application, kUnsupportedSetId, kUnsupportedManifest);
  check_refusal(inspected, "UNSUPPORTED_AUDIO", "soundset_audio_unsupported");
  LMDJ_CHECK(inspected.at("error").at("details").at("slot_index") == 0);

  const auto previewed = map_preview(
      application, project, 0, kUnsupportedSetId, kUnsupportedManifest);
  check_refusal(previewed, "UNSUPPORTED_AUDIO", "soundset_audio_unsupported");

  const auto installed = application.command(install_request(
      project,
      uuid(0x110),
      before.at("revision").get<std::uint64_t>(),
      0,
      kUnsupportedSetId,
      kUnsupportedManifest));
  check_refusal(installed, "UNSUPPORTED_AUDIO", "soundset_audio_unsupported");

  LMDJ_CHECK(inspect_project(application, project) == before);
}

// The Set's audio is a property of the Set, not of the write set. A policy
// that happens to write none of the offending Pads — or none at all — must not
// admit a Set that inspect refuses.
void test_a_policy_cannot_narrow_the_audio_decision() {
  TempDirectory temp("policy-audio");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());
  const auto project = create_project(application, temp.path(), 0x800);

  // Occupy the three Pads the Unsupported Audio Kit proposes, using a Set
  // whose own audio is fine.
  const auto seeded = application.command(install_request(
      project,
      uuid(0x810),
      inspect_project(application, project)
          .at("revision")
          .get<std::uint64_t>(),
      1,
      kAttributionSetId,
      kAttributionManifest));
  LMDJ_CHECK(seeded.at("ok").get<bool>());
  const auto before = inspect_project(application, project);

  // Slots 0 and 1 of the Unsupported Audio Kit are not S8-D6 and slot 2 is.
  // Under `keep` every proposed Pad collides, so the write set is empty and a
  // write-set-shaped audio check would see nothing to refuse.
  for (const auto* policy : {"keep", "replace"}) {
    auto request = install_request(
        project,
        uuid(policy[0] == 'k' ? 0x820 : 0x830),
        before.at("revision").get<std::uint64_t>(),
        1,
        kUnsupportedSetId,
        kUnsupportedManifest);
    request["occupied_pad_policy"] = policy;
    check_refusal(
        application.command(request),
        "UNSUPPORTED_AUDIO",
        "soundset_audio_unsupported");
    LMDJ_CHECK(inspect_project(application, project) == before);
  }
}

// A Catalog index that is not `lmdj.soundset-catalog.v1` is no usable index:
// the listing stays available on the Set Store alone and publishes nothing
// new. Each case below is the Contract's own rule, one at a time.
void test_a_malformed_catalog_index_publishes_nothing() {
  TempDirectory temp("bad-index");
  auto source = std::make_shared<FakeCatalogSource>();
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));

  const auto mutate = [](auto&& change) {
    auto index = fixture_catalog_index();
    change(index);
    return index;
  };
  const std::vector<nlohmann::json> rejected{
      mutate([](nlohmann::json& index) {
        index["contract"] = "lmdj.soundset-catalog.v2";
      }),
      mutate([](nlohmann::json& index) { index["extra"] = true; }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0)["extra"] = true;
      }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0).erase("license_summary");
      }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0)["roles_summary"].push_back("triangle");
      }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0)["roles_summary"].push_back("kick");
      }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0)["version"] = "1.0";
      }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0)["manifest_sha256"] =
            "33175F66912A9ADD3E4E551D19D85072ADCD1F0331FCC9FED80AB0BC18DD9111";
      }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0)["total_bytes"] = 0;
      }),
      mutate([](nlohmann::json& index) { index["entries"].at(0)["bpm"] = 12; }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0)["bpm"] = "fast";
      }),
      mutate([](nlohmann::json& index) { index["entries"].at(0)["key"] = 7; }),
      mutate([](nlohmann::json& index) {
        const auto first = index["entries"].at(0);
        index["entries"].push_back(first);
      }),
      mutate([](nlohmann::json& index) {
        index["entries"].at(0)["license_summary"]["rights_holder"] = "";
      }),
  };
  for (const auto& index : rejected) {
    source->publish(index);
    const auto listing = catalog_list(application);
    LMDJ_CHECK(listing.at("ok").get<bool>());
    LMDJ_CHECK(!listing.at("result").at("catalog_available").get<bool>());
    LMDJ_CHECK(listing.at("result").at("sets").empty());
  }

  // The unmodified fixture index is the control: the same call publishes.
  source->publish(fixture_catalog_index());
  const auto listing = catalog_list(application);
  LMDJ_CHECK(listing.at("result").at("catalog_available").get<bool>());
  LMDJ_CHECK(listing.at("result").at("sets").size() == 3);
}

// S11-D7 again, but with the Catalog index readable and the object transport
// failing: a cached Set is still listed and installable, and the entries that
// could not be acquired are named rather than silently absent.
void test_a_failing_transport_leaves_cached_sets_usable() {
  TempDirectory temp("failing-transport");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  {
    Application online(config(
        temp.path(),
        lmdj::project_io::make_local_directory_catalog_transport(
            flatten_fixture_corpus(temp)),
        source));
    LMDJ_CHECK(catalog_list(online).at("ok").get<bool>());
  }

  Application offline(config(
      temp.path(), std::make_shared<UnreachableTransport>(), source));
  const auto listing = catalog_list(offline);
  LMDJ_CHECK(listing.at("ok").get<bool>());
  // The index was read, so the Catalog is available even though not one
  // object could be resolved through it.
  LMDJ_CHECK(listing.at("result").at("catalog_available").get<bool>());
  LMDJ_CHECK(listing.at("result").at("sets").size() == 3);
  LMDJ_CHECK(listing_contains(listing, kFoundrySetId));
  // The four Sets that never reached the Set Store are refused for the
  // transport's reason now, not for their own faults.
  LMDJ_CHECK(listing.at("result").at("refused").size() == 4);
  LMDJ_CHECK(
      refusal_reason(listing, kTamperedSetId) == "catalog_unavailable");

  const auto project = create_project(offline, temp.path(), 0x900);
  const auto installed = offline.command(install_request(
      project,
      uuid(0x910),
      inspect_project(offline, project).at("revision").get<std::uint64_t>(),
      0,
      kFoundrySetId,
      kFoundryManifest));
  LMDJ_CHECK(installed.at("ok").get<bool>());
  LMDJ_CHECK(installed.at("result").at("installed").size() == 11);
}

// S11-D5 and S11-D11: the preview is the pure index-identity map, it reports
// the revision it read, and it changes nothing.
void test_map_preview_is_index_identity_and_changes_nothing() {
  TempDirectory temp("map-preview");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());
  const auto project = create_project(application, temp.path(), 0x200);
  const auto before = inspect_project(application, project);

  const auto previewed =
      map_preview(application, project, 1, kFoundrySetId, kFoundryManifest);
  LMDJ_CHECK(previewed.at("ok").get<bool>());
  LMDJ_CHECK(
      previewed.at("project_revision") == before.at("revision"));
  const auto& result = previewed.at("result");
  LMDJ_CHECK(result.at("bank_id") == 1);
  LMDJ_CHECK(result.at("proposed").size() == 11);
  // Slot index identity: occupied Set slot i proposes target Pad i.
  for (const auto& proposed : result.at("proposed")) {
    LMDJ_CHECK(proposed.at("slot_index") == proposed.at("pad"));
  }
  LMDJ_CHECK(result.at("proposed").at(10).at("slot_index") == 12);
  // An empty Bank collides with nothing, and every empty Set slot is kept.
  LMDJ_CHECK(result.at("collisions").empty());
  LMDJ_CHECK(
      result.at("kept") == nlohmann::json::array({10, 11, 13, 14, 15}));

  // Same input, same output, still no Project change.
  LMDJ_CHECK(
      map_preview(application, project, 1, kFoundrySetId, kFoundryManifest) ==
      previewed);
  LMDJ_CHECK(inspect_project(application, project) == before);
}

// #465 Q2 and S11-D8: an occupied collision without a policy is refused with
// the complete collisions list and zero Project change; `keep` writes only the
// free Pads and `replace` writes every proposed Pad. S11-D12: an empty Set slot
// never clears an occupied Pad under either policy.
void test_install_policies_write_the_three_write_sets() {
  TempDirectory temp("install-policies");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());
  const auto project = create_project(application, temp.path(), 0x300);

  // The Attribution Kit occupies Pads 0..3 of an empty Bank, so this install
  // needs no policy at all.
  const auto empty_revision =
      inspect_project(application, project).at("revision").get<std::uint64_t>();
  const auto seeded = application.command(install_request(
      project,
      uuid(0x310),
      empty_revision,
      2,
      kAttributionSetId,
      kAttributionManifest));
  LMDJ_CHECK(seeded.at("ok").get<bool>());
  LMDJ_CHECK(seeded.at("result").at("installed").size() == 4);
  LMDJ_CHECK(seeded.at("project_revision") == empty_revision + 1);

  const auto after_seed = inspect_project(application, project);
  const auto seed_revision = after_seed.at("revision").get<std::uint64_t>();
  const auto& seed_bank = bank_pads(after_seed, 2);
  const auto seeded_asset_id = seed_bank.at(0).at("asset_id").get<std::string>();
  const auto& lineage =
      after_seed.at("assets").at(seeded_asset_id).at("lineage");
  LMDJ_CHECK(lineage.at("source").at("kind") == "soundset");
  LMDJ_CHECK(lineage.at("source").at("set_id") == kAttributionSetId);
  LMDJ_CHECK(lineage.at("source").at("set_version") == kSetVersion);
  LMDJ_CHECK(lineage.at("source").at("manifest_sha256") == kAttributionManifest);
  LMDJ_CHECK(lineage.at("source").at("slot_index") == 0);
  LMDJ_CHECK(
      lineage.at("source").at("artifact_sha256") ==
      "e51f446a04207989eea06f7206befd4306362d8a9bcd34b5638100062e2af29c");
  LMDJ_CHECK(lineage.at("derivation").at("kind") == "soundset_install");

  // Write set one: the Foundry Set collides on Pads 0..3, and an omitted
  // policy is refused with the whole list and zero change.
  const auto conflicted = application.command(install_request(
      project, uuid(0x320), seed_revision, 2, kFoundrySetId, kFoundryManifest));
  check_refusal(conflicted, "INVALID_ARGUMENT", "soundset_occupied_conflict");
  LMDJ_CHECK(
      conflicted.at("error").at("details").at("collisions") ==
      nlohmann::json::array({0, 1, 2, 3}));
  LMDJ_CHECK(inspect_project(application, project) == after_seed);

  // Write set two: `keep` writes only the non-colliding proposed Pads.
  auto keep = install_request(
      project, uuid(0x330), seed_revision, 2, kFoundrySetId, kFoundryManifest);
  keep["occupied_pad_policy"] = "keep";
  const auto kept = application.command(keep);
  LMDJ_CHECK(kept.at("ok").get<bool>());
  auto kept_pads = std::vector<int>{};
  for (const auto& entry : kept.at("result").at("installed")) {
    kept_pads.push_back(entry.at("pad").get<int>());
  }
  LMDJ_CHECK(kept_pads == std::vector<int>({4, 5, 6, 7, 8, 9, 12}));

  const auto after_keep = inspect_project(application, project);
  const auto& keep_bank = bank_pads(after_keep, 2);
  for (int pad = 0; pad < 4; ++pad) {
    LMDJ_CHECK(
        keep_bank.at(pad).at("asset_id") == seed_bank.at(pad).at("asset_id"));
  }
  for (const auto pad : {10, 11, 13, 14, 15}) {
    LMDJ_CHECK(keep_bank.at(pad).at("asset_id").is_null());
  }
  LMDJ_CHECK(after_keep.at("assets").size() == 11);

  // Write set three: `replace` writes every proposed Pad, including the
  // colliding ones, and still leaves the Set's empty slots alone.
  auto replace = install_request(
      project,
      uuid(0x340),
      after_keep.at("revision").get<std::uint64_t>(),
      2,
      kFoundrySetId,
      kFoundryManifest);
  replace["occupied_pad_policy"] = "replace";
  const auto replaced = application.command(replace);
  LMDJ_CHECK(replaced.at("ok").get<bool>());
  LMDJ_CHECK(replaced.at("result").at("installed").size() == 11);

  const auto after_replace = inspect_project(application, project);
  const auto& replaced_bank = bank_pads(after_replace, 2);
  for (int pad = 0; pad < 4; ++pad) {
    LMDJ_CHECK(
        replaced_bank.at(pad).at("asset_id") !=
        seed_bank.at(pad).at("asset_id"));
  }
  for (const auto pad : {10, 11, 13, 14, 15}) {
    LMDJ_CHECK(replaced_bank.at(pad).at("asset_id").is_null());
  }
  // S8-D5: a replaced Asset is not deleted, so all three write sets' Assets
  // are still Project Truth.
  LMDJ_CHECK(after_replace.at("assets").size() == 22);

  // A replayed command id returns the stored receipt and publishes nothing.
  const auto replayed = application.command(replace);
  LMDJ_CHECK(replayed.at("ok").get<bool>());
  LMDJ_CHECK(replayed.at("result").at("replayed").get<bool>());
  LMDJ_CHECK(inspect_project(application, project) == after_replace);

  // `keep` on a Bank whose every proposed Pad is occupied writes nothing and
  // succeeds: there is no command to commit, so the revision stands.
  auto empty_keep = install_request(
      project,
      uuid(0x350),
      after_replace.at("revision").get<std::uint64_t>(),
      2,
      kAttributionSetId,
      kAttributionManifest);
  empty_keep["occupied_pad_policy"] = "keep";
  const auto nothing = application.command(empty_keep);
  LMDJ_CHECK(nothing.at("ok").get<bool>());
  LMDJ_CHECK(nothing.at("result").at("installed").empty());
  LMDJ_CHECK(nothing.at("project_revision") == after_replace.at("revision"));
  LMDJ_CHECK(inspect_project(application, project) == after_replace);
}

// The Catalog every v1 Host actually wires: no injected collaborator at all,
// just the Workspace's own `.lmdj-host/soundset-catalog/` directory. This is
// the whole path a native Host, the C ABI and the Web Host take today, so it
// is the one that has to work offline end to end.
// S11-D5: the two audition layers are reachable, and neither is a Project
// change. The set-level `demo` and a slot's own Artifact answer through one
// operation, and Foundry CC0's slot 12 reusing slot 0's Artifact makes the
// audition source content-addressed rather than slot-addressed.
// #799. The typed `audition_soundset` is what a Runtime Host calls to obtain
// the bytes themselves; the JSON operation reports their geometry. The defect
// this catches is the two disagreeing -- a Host playing audio whose shape the
// envelope misdescribes, which no per-surface test can see because each is
// self-consistent. Both go through one resolve/gate/decode path so they cannot
// drift, and this pins that they answer about the same audio.
void test_typed_audition_audio_matches_the_reported_geometry() {
  TempDirectory temp("audition-typed");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());

  const auto frames_of =
      [](const lmdj::facade::SoundSetAuditionAudio& audio) {
        return static_cast<std::uint64_t>(
            audio.prepared->interleaved.size() / audio.prepared->channels);
      };

  // Layer one, the set-level demo: already at the Runtime rate.
  const auto demo_envelope =
      audition_set(application, kFoundrySetId, kFoundryManifest);
  LMDJ_CHECK(demo_envelope.at("ok").get<bool>());
  const auto demo = application.audition_soundset(
      lmdj::facade::SoundSetAuditionRequest{
          std::string{kFoundrySetId}, std::string{kSetVersion},
          std::string{kFoundryManifest}, std::nullopt});
  LMDJ_CHECK(demo.has_value());
  LMDJ_CHECK(demo.value().prepared != nullptr);
  LMDJ_CHECK(demo.value().prepared->sample_rate == 48'000);
  LMDJ_CHECK(demo.value().artifact.sha256 == kFoundryDemoArtifact);
  // The bytes carry exactly the geometry the envelope reports.
  LMDJ_CHECK(
      demo.value().sample_rate ==
      demo_envelope.at("result").at("audio").at("sample_rate")
          .get<std::uint32_t>());
  LMDJ_CHECK(
      demo.value().source_frames ==
      demo_envelope.at("result").at("audio").at("source_frames")
          .get<std::uint64_t>());
  LMDJ_CHECK(
      frames_of(demo.value()) ==
      demo_envelope.at("result").at("audio").at("prepared_frames")
          .get<std::uint64_t>());

  // Layer two, a slot whose Artifact is 44.1 kHz: the typed path must hand back
  // the *resampled* PCM, not the source, or a Host would publish 2'646 frames
  // of 44.1 kHz audio into a 48 kHz engine and play it sharp.
  const auto slot_envelope =
      audition_set(application, kFoundrySetId, kFoundryManifest, 0);
  LMDJ_CHECK(slot_envelope.at("ok").get<bool>());
  const auto slot_zero = application.audition_soundset(
      lmdj::facade::SoundSetAuditionRequest{
          std::string{kFoundrySetId}, std::string{kSetVersion},
          std::string{kFoundryManifest}, std::optional<std::uint8_t>{0}});
  LMDJ_CHECK(slot_zero.has_value());
  LMDJ_CHECK(slot_zero.value().prepared->sample_rate == 48'000);
  LMDJ_CHECK(slot_zero.value().sample_rate == 44'100);
  LMDJ_CHECK(slot_zero.value().source_frames == 2'646);
  LMDJ_CHECK(frames_of(slot_zero.value()) == 2'880);
  LMDJ_CHECK(
      frames_of(slot_zero.value()) ==
      slot_envelope.at("result").at("audio").at("prepared_frames")
          .get<std::uint64_t>());
  LMDJ_CHECK(slot_zero.value().artifact.sha256 == kFoundrySlotZeroArtifact);

  // The typed path refuses what the JSON operation refuses, with the same
  // code: S11-D12's empty slot is the author's silence, and auditions widen no
  // error vocabulary.
  const auto empty_slot = application.audition_soundset(
      lmdj::facade::SoundSetAuditionRequest{
          std::string{kFoundrySetId}, std::string{kSetVersion},
          std::string{kFoundryManifest}, std::optional<std::uint8_t>{10}});
  LMDJ_CHECK(!empty_slot.has_value());
  LMDJ_CHECK(
      empty_slot.error().code == lmdj::foundation::ErrorCode::missing_asset);
  LMDJ_CHECK(empty_slot.error().details.empty());
  // That refusal is also what pins slot addressing: an implementation ignoring
  // `slot_index` would answer slot 10 with slot 0's audio instead of refusing.
  //
  // What this does not distinguish: two *occupied* slots carrying different
  // Artifacts are never compared here, so a mapping that transposed two
  // occupied indices would pass. Foundry CC0's slot 12 deliberately reuses
  // slot 0's Artifact, so the fixture cannot express that case; catching it
  // needs a Set whose occupied slots all differ.
}

void test_audition_reaches_both_s11_d5_layers() {
  TempDirectory temp("audition");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());

  const auto project = create_project(application, temp.path(), 900);
  const auto before = inspect_project(application, project);

  // Layer one: the set-level demo, a standalone 48 kHz stereo blob that no
  // slot references.
  const auto demo = audition_set(application, kFoundrySetId, kFoundryManifest);
  LMDJ_CHECK(demo.at("ok").get<bool>());
  const auto& played = demo.at("result");
  LMDJ_CHECK(played.at("set_id") == kFoundrySetId);
  LMDJ_CHECK(played.at("version") == kSetVersion);
  LMDJ_CHECK(played.at("manifest_sha256") == kFoundryManifest);
  LMDJ_CHECK(played.at("slot_index").is_null());
  LMDJ_CHECK(played.at("artifact").at("sha256") == kFoundryDemoArtifact);
  LMDJ_CHECK(played.at("artifact").at("byte_length") == 46124);
  LMDJ_CHECK(played.at("audio").at("sample_rate") == 48'000);
  LMDJ_CHECK(played.at("audio").at("channels") == 2);
  LMDJ_CHECK(played.at("audio").at("source_frames") == 11'520);
  LMDJ_CHECK(played.at("audio").at("prepared_frames") == 11'520);
  LMDJ_CHECK(played.at("audio").at("prepared_bytes") == 46'080);
  // A query with respect to Project Truth carries no revision at all.
  LMDJ_CHECK(demo.at("project_revision").is_null());

  // Layer two: one slot's own Artifact, resampled to the 48 kHz Runtime rate
  // by the same preparation the ordinary preview path uses.
  const auto slot_zero =
      audition_set(application, kFoundrySetId, kFoundryManifest, 0);
  LMDJ_CHECK(slot_zero.at("ok").get<bool>());
  LMDJ_CHECK(slot_zero.at("result").at("slot_index") == 0);
  LMDJ_CHECK(
      slot_zero.at("result").at("artifact").at("sha256") ==
      kFoundrySlotZeroArtifact);
  LMDJ_CHECK(slot_zero.at("result").at("audio").at("sample_rate") == 44'100);
  LMDJ_CHECK(slot_zero.at("result").at("audio").at("channels") == 1);
  LMDJ_CHECK(slot_zero.at("result").at("audio").at("source_frames") == 2'646);
  LMDJ_CHECK(slot_zero.at("result").at("audio").at("prepared_frames") == 2'880);
  LMDJ_CHECK(
      slot_zero.at("result").at("audio").at("prepared_bytes") == 11'520);

  // Slot 12 reuses slot 0's Artifact, so the two auditions resolve the same
  // bytes under different slot indices.
  const auto slot_twelve =
      audition_set(application, kFoundrySetId, kFoundryManifest, 12);
  LMDJ_CHECK(slot_twelve.at("ok").get<bool>());
  LMDJ_CHECK(slot_twelve.at("result").at("slot_index") == 12);
  LMDJ_CHECK(
      slot_twelve.at("result").at("artifact") ==
      slot_zero.at("result").at("artifact"));
  LMDJ_CHECK(
      slot_twelve.at("result").at("audio") ==
      slot_zero.at("result").at("audio"));

  // S11-D12: an empty slot is the author's silence, not a playable source.
  // The refusal is an existing public code carrying no reason token, because
  // the locked Sound Set error vocabulary does not grow for this.
  const auto empty_slot =
      audition_set(application, kFoundrySetId, kFoundryManifest, 10);
  LMDJ_CHECK(!empty_slot.at("ok").get<bool>());
  LMDJ_CHECK(empty_slot.at("error").at("code") == "MISSING_ASSET");
  LMDJ_CHECK(empty_slot.at("error").at("message") == "Sound Set slot is empty");
  LMDJ_CHECK(empty_slot.at("error").at("details") == nlohmann::json::object());

  // Neither the successful auditions nor the refusal touched the Project.
  LMDJ_CHECK(inspect_project(application, project) == before);
}

// A Set that declares no `demo` has no set-level layer to play, and that is a
// property of the manifest rather than of the request. The Mismatched Summary
// Kit's manifest is eligible on its own terms, so correcting the Catalog
// summary the test elsewhere corrupts admits an eligible, S8-D6-valid Set
// that carries no demo.
void test_audition_refuses_a_set_that_declares_no_demo() {
  TempDirectory temp("audition-no-demo");
  auto source = std::make_shared<FakeCatalogSource>();
  auto index = fixture_catalog_index();
  for (auto& entry : index.at("entries")) {
    if (entry.at("set_id") == kMismatchedSetId) {
      entry.at("license_summary").at("rights_holder") = "Bea Waveform";
    }
  }
  source->publish(index);
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  const auto listing = catalog_list(application);
  LMDJ_CHECK(listing.at("ok").get<bool>());
  LMDJ_CHECK(listing_contains(listing, kMismatchedSetId));
  LMDJ_CHECK(!listed_set(listing, kMismatchedSetId).at("has_demo").get<bool>());

  // Its two occupied slots audition, so the refusal below is about the demo
  // and not about the Set.
  LMDJ_CHECK(
      audition_set(application, kMismatchedSetId, kMismatchedManifest, 0)
          .at("ok")
          .get<bool>());

  const auto absent =
      audition_set(application, kMismatchedSetId, kMismatchedManifest);
  LMDJ_CHECK(!absent.at("ok").get<bool>());
  LMDJ_CHECK(absent.at("error").at("code") == "MISSING_ASSET");
  LMDJ_CHECK(
      absent.at("error").at("message") == "Sound Set declares no demo");
  LMDJ_CHECK(absent.at("error").at("details") == nlohmann::json::object());
}

// S11-D3 belongs to the Set, not to the slot: a Set carrying one blob that is
// not S8-D6 is unauditionable through every slot, including the legal one,
// and the audio decision is reached before the audition source is looked up.
// The Unsupported Audio Kit declares no demo, so a demo request answers with
// the audio refusal rather than with the missing-source one.
void test_audition_refuses_a_set_whose_audio_is_not_s8_d6() {
  TempDirectory temp("audition-unsupported");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());

  for (const std::optional<std::uint8_t> slot :
       {std::optional<std::uint8_t>{0}, std::optional<std::uint8_t>{2},
        std::optional<std::uint8_t>{5}, std::optional<std::uint8_t>{}}) {
    check_refusal(
        audition_set(
            application, kUnsupportedSetId, kUnsupportedManifest, slot),
        "UNSUPPORTED_AUDIO",
        "soundset_audio_unsupported");
  }

  // A Set the Store never held is NOT_FOUND, not an audition of nothing.
  const auto unknown = audition_set(
      application, kUnsupportedSetId, std::string(64, 'b'), 0);
  LMDJ_CHECK(!unknown.at("ok").get<bool>());
  LMDJ_CHECK(unknown.at("error").at("code") == "NOT_FOUND");
}

void test_the_workspace_local_catalog_serves_a_host_with_no_injection() {
  TempDirectory temp("workspace-catalog");
  const auto catalog = temp.path() / ".lmdj-host" / "soundset-catalog";
  std::filesystem::create_directories(catalog / "objects");
  for (const auto* kind : {"manifest", "blob"}) {
    const std::filesystem::path source =
        std::filesystem::path("tests/fixtures/soundset") / kind;
    for (const auto& entry : std::filesystem::directory_iterator(source)) {
      std::filesystem::copy_file(
          entry.path(),
          catalog / "objects" / entry.path().filename(),
          std::filesystem::copy_options::overwrite_existing);
    }
  }
  std::filesystem::copy_file(
      "tests/fixtures/soundset/catalog/index.json",
      catalog / "index.json",
      std::filesystem::copy_options::overwrite_existing);

  auto wired = lmdj::facade::make_workspace_soundset_catalog(temp.path());
  Application application(config(
      temp.path(), std::move(wired.transport), std::move(wired.source)));

  const auto listing = catalog_list(application);
  LMDJ_CHECK(listing.at("ok").get<bool>());
  LMDJ_CHECK(listing.at("result").at("catalog_available").get<bool>());
  LMDJ_CHECK(listing_contains(listing, kFoundrySetId));

  LMDJ_CHECK(
      inspect_set(application, kFoundrySetId, kFoundryManifest)
          .at("ok")
          .get<bool>());

  const auto project = create_project(application, temp.path(), 0xa00);
  const auto installed = application.command(install_request(
      project,
      uuid(0xa10),
      inspect_project(application, project)
          .at("revision")
          .get<std::uint64_t>(),
      0,
      kFoundrySetId,
      kFoundryManifest));
  LMDJ_CHECK(installed.at("ok").get<bool>());
  LMDJ_CHECK(installed.at("result").at("installed").size() == 11);

  // A Workspace with no Catalog at all reads as an unreachable Catalog, not
  // as a failure.
  TempDirectory bare("workspace-catalog-absent");
  auto absent = lmdj::facade::make_workspace_soundset_catalog(bare.path());
  Application empty(config(
      bare.path(), std::move(absent.transport), std::move(absent.source)));
  const auto bare_listing = catalog_list(empty);
  LMDJ_CHECK(bare_listing.at("ok").get<bool>());
  LMDJ_CHECK(!bare_listing.at("result").at("catalog_available").get<bool>());
  LMDJ_CHECK(bare_listing.at("result").at("sets").empty());
}

// An Artifact the published manifest declares whose stored bytes are gone is a
// corrupted Set Store copy, and the locked table has exactly one reason for
// that whether the blob is absent or altered.
void test_a_missing_stored_artifact_is_a_content_mismatch() {
  TempDirectory temp("store-corruption");
  auto source = std::make_shared<FakeCatalogSource>();
  source->publish(fixture_catalog_index());
  Application application(config(
      temp.path(),
      lmdj::project_io::make_local_directory_catalog_transport(
          flatten_fixture_corpus(temp)),
      source));
  LMDJ_CHECK(catalog_list(application).at("ok").get<bool>());

  const auto stored_set = temp.path() / ".lmdj-host" / "soundsets" /
                          std::string{kFoundryManifest};
  LMDJ_CHECK(std::filesystem::is_directory(stored_set));
  const auto blob =
      stored_set /
      "10b24f4f256ba6d2dde5a63dbd797bf3b707cb533a987bed72ea2242d6546e13";
  LMDJ_CHECK(std::filesystem::remove(blob));

  check_refusal(
      inspect_set(application, kFoundrySetId, kFoundryManifest),
      "IO_ERROR",
      "soundset_content_mismatch");
}

}  // namespace

int main() {
  try {
    test_locked_operations_are_registered_with_exact_kinds();
    test_locked_requests_reject_extra_fields();
    test_catalog_list_publishes_only_eligible_sets();
    test_cached_sets_survive_an_unreachable_catalog();
    test_catalog_summary_mismatch_is_ineligible_at_inspect();
    test_unsupported_audio_is_refused_with_zero_project_change();
    test_a_policy_cannot_narrow_the_audio_decision();
    test_a_malformed_catalog_index_publishes_nothing();
    test_a_failing_transport_leaves_cached_sets_usable();
    test_map_preview_is_index_identity_and_changes_nothing();
    test_install_policies_write_the_three_write_sets();
    test_audition_reaches_both_s11_d5_layers();
    test_typed_audition_audio_matches_the_reported_geometry();
    test_audition_refuses_a_set_that_declares_no_demo();
    test_audition_refuses_a_set_whose_audio_is_not_s8_d6();
    test_the_workspace_local_catalog_serves_a_host_with_no_injection();
    test_a_missing_stored_artifact_is_a_content_mismatch();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
