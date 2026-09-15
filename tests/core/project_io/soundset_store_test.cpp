// Workspace Set Store: fetch a Sound Set through an injected CatalogTransport,
// verify every byte it declares, and publish it atomically into a read-only
// store. Nothing here decodes audio; S8-D6 validation is the Facade's job.
#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/foundation/soundset_manifest.hpp>
#include <lmdj/project_io/soundset_catalog_transport.hpp>
#include <lmdj/project_io/soundset_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::CatalogLicenseSummary;
using lmdj::foundation::Error;
using lmdj::foundation::ErrorCode;
using lmdj::project_io::CatalogObjectKind;
using lmdj::project_io::CatalogObjectRef;
using lmdj::project_io::CatalogTransport;
using lmdj::project_io::ProjectStoragePlatform;
using lmdj::project_io::SoundSetCatalogEntry;
using lmdj::project_io::SoundSetStore;
using lmdj::project_io::SoundSetStoreLimits;

constexpr std::string_view kSetId = "10000000-0000-4000-8000-000000000001";
constexpr std::string_view kVersion = "1.0.0";

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-soundset-store-test-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  TempDirectory(const TempDirectory&) = delete;
  TempDirectory& operator=(const TempDirectory&) = delete;

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::string sha256_hex(std::string_view bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* begin = reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(begin, begin + bytes.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

std::string text_of(const std::vector<std::byte>& bytes) {
  return {reinterpret_cast<const char*>(bytes.data()), bytes.size()};
}

std::string reason_of(const Error& error) {
  if (!error.details.is_object() || !error.details.contains("reason")) {
    return {};
  }
  return error.details.at("reason").get<std::string>();
}

// A Host limit refusal names the Host manifest key that refused, what was
// observed and what it allows -- the triple the Facade already forwards.
std::string refused_resource(const Error& error) {
  if (error.code != ErrorCode::io_error || !error.details.is_object() ||
      !error.details.contains("resource") ||
      !error.details.contains("observed") ||
      !error.details.contains("limit")) {
    return {};
  }
  // A limit refusal is not one of the locked reason conditions.
  if (error.details.contains("reason")) {
    return {};
  }
  return error.details.at("resource").get<std::string>();
}

std::uint64_t refused_observed(const Error& error) {
  return error.details.at("observed").get<std::uint64_t>();
}

std::uint64_t refused_limit(const Error& error) {
  return error.details.at("limit").get<std::uint64_t>();
}

// An occupied slot's declared Artifact, plus the bytes the Catalog will serve.
struct SlotSpec {
  int index = 0;
  std::string role = "kick";
  std::string payload;
};

std::string manifest_bytes(
    const std::vector<SlotSpec>& occupied,
    std::string_view spdx = "CC-BY-4.0",
    std::string_view attribution = "Alice") {
  auto manifest = nlohmann::json::object();
  manifest["contract"] = "lmdj.soundset.v1";
  manifest["set_id"] = std::string{kSetId};
  manifest["version"] = std::string{kVersion};
  manifest["name"] = "Kit A";
  manifest["publisher"] = "LMDJ";
  manifest["license"] = nlohmann::json{
      {"spdx_id", std::string{spdx}},
      {"rights_holder", "Alice"},
      {"copyright", "Copyright 2026 Alice"},
      {"attribution", std::string{attribution}},
  };
  auto slots = nlohmann::json::array();
  for (int index = 0; index < 16; ++index) {
    const auto found = std::find_if(
        occupied.begin(),
        occupied.end(),
        [index](const SlotSpec& slot) { return slot.index == index; });
    if (found == occupied.end()) {
      slots.push_back(nlohmann::json{{"slot", index}});
      continue;
    }
    slots.push_back(nlohmann::json{
        {"slot", index},
        {"role", found->role},
        {"name", "Slot " + std::to_string(index)},
        {"artifact",
         nlohmann::json{
             {"sha256", sha256_hex(found->payload)},
             {"media_type", "audio/wav"},
             {"byte_length", found->payload.size()},
         }},
    });
  }
  manifest["slots"] = std::move(slots);
  return lmdj::foundation::canonical_json(manifest);
}

// The same manifest carrying the S11-D5 set-level demo Artifact. `demo_bytes`
// is what the Catalog will serve for it; `declared_length` overrides the
// declared byte_length so a demo can be made to contradict itself.
std::string manifest_bytes_with_demo(
    const std::vector<SlotSpec>& occupied,
    const std::string& demo_bytes,
    std::optional<std::uint64_t> declared_length = std::nullopt) {
  auto manifest = nlohmann::json::parse(manifest_bytes(occupied));
  manifest["demo"] = nlohmann::json{
      {"sha256", sha256_hex(demo_bytes)},
      {"media_type", "audio/wav"},
      {"byte_length", declared_length.value_or(demo_bytes.size())},
  };
  return lmdj::foundation::canonical_json(manifest);
}

// Two slots that name one sha256 with different byte_lengths. Task 1's parser
// validates each Artifact ref in isolation, so only the store can catch this.
std::string manifest_with_contradictory_artifact(
    const std::string& payload,
    std::uint64_t second_byte_length) {
  auto manifest = nlohmann::json::parse(
      manifest_bytes({{0, "kick", payload}, {5, "perc", payload}}));
  manifest["slots"][5]["artifact"]["byte_length"] = second_byte_length;
  return lmdj::foundation::canonical_json(manifest);
}

// Serves exactly the objects it is given, and counts every resolution so a
// test can prove a repeated Artifact hash is fetched once.
class FakeCatalogTransport final : public CatalogTransport {
 public:
  void publish(std::string bytes) {
    objects_.emplace(sha256_hex(bytes), std::move(bytes));
  }

  void publish_as(std::string name, std::string bytes) {
    objects_.insert_or_assign(std::move(name), std::move(bytes));
  }

  void fail_everything() { unreachable_ = true; }

  int reads(std::string_view sha256) const {
    const auto found = reads_.find(std::string{sha256});
    return found == reads_.end() ? 0 : found->second;
  }

  int total_reads() const {
    int total = 0;
    for (const auto& entry : reads_) {
      total += entry.second;
    }
    return total;
  }

  lmdj::foundation::Result<std::vector<std::byte>> read_object(
      const CatalogObjectRef& object,
      std::uint64_t maximum_bytes) override {
    using Result = lmdj::foundation::Result<std::vector<std::byte>>;
    ++reads_[object.sha256];
    ++kinds_[object.sha256 + (object.kind == CatalogObjectKind::manifest
                                  ? ":manifest"
                                  : ":blob")];
    if (unreachable_) {
      return Result::failure(
          Error{ErrorCode::io_error, "fake catalog is unreachable"});
    }
    const auto found = objects_.find(object.sha256);
    if (found == objects_.end()) {
      return Result::failure(
          Error{ErrorCode::not_found, "fake catalog has no such object"});
    }
    if (found->second.size() > maximum_bytes) {
      return Result::failure(
          Error{ErrorCode::io_error, "fake catalog object exceeds the bound"});
    }
    const auto* begin =
        reinterpret_cast<const std::byte*>(found->second.data());
    return Result::success(
        std::vector<std::byte>{begin, begin + found->second.size()});
  }

  int reads_of_kind(std::string_view sha256, std::string_view kind) const {
    const auto found = kinds_.find(std::string{sha256} + std::string{kind});
    return found == kinds_.end() ? 0 : found->second;
  }

 private:
  std::map<std::string, std::string> objects_;
  std::map<std::string, int> reads_;
  std::map<std::string, int> kinds_;
  bool unreachable_ = false;
};

SoundSetStoreLimits generous_limits() {
  return SoundSetStoreLimits{
      .maximum_soundset_manifest_bytes = 1u << 20,
      .maximum_soundset_blob_bytes = 1u << 20,
      .maximum_soundset_unique_bytes = 1u << 20,
      .maximum_soundset_staging_bytes = 1u << 22,
  };
}

std::shared_ptr<ProjectStoragePlatform> platform_for(
    const std::filesystem::path& workspace) {
  return lmdj::project_io::make_native_project_storage_platform(
      workspace / ".lmdj-host" / "leases");
}

SoundSetCatalogEntry entry_for(
    const std::string& manifest,
    std::uint64_t total_bytes,
    std::optional<CatalogLicenseSummary> summary =
        CatalogLicenseSummary{"CC-BY-4.0", "Alice"}) {
  return SoundSetCatalogEntry{
      std::string{kSetId},
      std::string{kVersion},
      sha256_hex(manifest),
      total_bytes,
      std::move(summary),
  };
}

std::uint64_t declared_total(
    const std::string& manifest,
    const std::vector<std::string>& unique_payloads) {
  std::uint64_t total = manifest.size();
  for (const auto& payload : unique_payloads) {
    total += payload.size();
  }
  return total;
}

// A verified Set becomes readable as one unit, and its blobs are the same
// bytes the Catalog served.
void test_acquire_publishes_a_verified_set() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const std::string snare(96, 's');
  const auto manifest =
      manifest_bytes({{0, "kick", kick}, {1, "snare", snare}});
  transport.publish(manifest);
  transport.publish(kick);
  transport.publish(snare);

  SoundSetStore store(
      workspace.path(), generous_limits(), platform_for(workspace.path()));
  const auto acquired = store.acquire(
      transport, entry_for(manifest, declared_total(manifest, {kick, snare})));
  LMDJ_CHECK(acquired.has_value());
  LMDJ_CHECK(acquired.value().manifest.set_id == kSetId);
  LMDJ_CHECK(acquired.value().manifest.version == kVersion);
  LMDJ_CHECK(acquired.value().manifest.canonical_bytes == manifest);
  LMDJ_CHECK(
      acquired.value().total_bytes == declared_total(manifest, {kick, snare}));

  const auto read = store.read(kSetId, kVersion, sha256_hex(manifest));
  LMDJ_CHECK(read.has_value());
  LMDJ_CHECK(read.value().manifest.canonical_bytes == manifest);

  const auto blob =
      store.read_artifact(sha256_hex(manifest), sha256_hex(kick));
  LMDJ_CHECK(blob.has_value());
  LMDJ_CHECK(text_of(blob.value()) == kick);

  const auto listed = store.list();
  LMDJ_CHECK(listed.has_value());
  LMDJ_CHECK(listed.value().size() == 1);
  LMDJ_CHECK(listed.value().front().manifest.set_id == kSetId);

  // Re-acquiring a published Set touches the Catalog for nothing.
  const auto before = transport.total_reads();
  const auto again = store.acquire(
      transport, entry_for(manifest, declared_total(manifest, {kick, snare})));
  LMDJ_CHECK(again.has_value());
  LMDJ_CHECK(transport.total_reads() == before);
}

// One Artifact hash reused by several slots is one download and one charge.
void test_repeated_artifact_hash_is_fetched_once() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string shared(80, 'p');
  const auto manifest = manifest_bytes(
      {{0, "perc", shared}, {5, "perc", shared}, {9, "perc", shared}});
  transport.publish(manifest);
  transport.publish(shared);

  SoundSetStore store(
      workspace.path(), generous_limits(), platform_for(workspace.path()));
  const auto acquired = store.acquire(
      transport, entry_for(manifest, declared_total(manifest, {shared})));
  LMDJ_CHECK(acquired.has_value());
  LMDJ_CHECK(transport.reads(sha256_hex(shared)) == 1);
  LMDJ_CHECK(transport.reads(sha256_hex(manifest)) == 1);
  LMDJ_CHECK(
      transport.reads_of_kind(sha256_hex(manifest), ":manifest") == 1);
  LMDJ_CHECK(transport.reads_of_kind(sha256_hex(shared), ":blob") == 1);

  // total_bytes counts the shared Artifact once, not three times.
  LMDJ_CHECK(
      acquired.value().total_bytes == manifest.size() + shared.size());
}

// A refused Set leaves nothing behind anywhere under the Host directory: not
// in the Set Store, and not as staged bytes under any path.
void expect_invisible(
    const SoundSetStore& store,
    const std::filesystem::path& workspace,
    const std::string& manifest) {
  const auto read = store.read(kSetId, kVersion, sha256_hex(manifest));
  LMDJ_CHECK(!read.has_value());
  LMDJ_CHECK(read.error().code == ErrorCode::not_found);
  LMDJ_CHECK(store.list().value().empty());

  const auto host = workspace / ".lmdj-host";
  LMDJ_CHECK(
      !std::filesystem::exists(host / "soundsets" / sha256_hex(manifest)));
  // No byte of the refused Set survives anywhere under the Host directory.
  if (std::filesystem::exists(host)) {
    for (const auto& entry :
         std::filesystem::recursive_directory_iterator(host)) {
      if (!entry.is_regular_file()) {
        continue;
      }
      LMDJ_CHECK(entry.path().filename() != "manifest.json");
      LMDJ_CHECK(
          entry.path().parent_path().filename() != sha256_hex(manifest));
    }
  }
}

// S11-D7 puts the set-level demo in the same unique-blob accounting as the
// slots: it is verified before publication, and a demo whose hash duplicates a
// slot Artifact is downloaded once and charged once.
void test_set_level_demo_is_verified_and_counted_once() {
  {
    // A demo no slot references is a unique blob of its own: fetched,
    // hash- and length-verified, charged, and readable afterwards.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const std::string demo(512, 'd');
    const auto manifest = manifest_bytes_with_demo({{0, "kick", kick}}, demo);
    transport.publish(manifest);
    transport.publish(kick);
    transport.publish(demo);

    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick, demo})));
    LMDJ_CHECK(acquired.has_value());
    LMDJ_CHECK(acquired.value().manifest.demo.has_value());
    LMDJ_CHECK(acquired.value().manifest.demo->sha256 == sha256_hex(demo));
    LMDJ_CHECK(acquired.value().manifest.demo->byte_length == demo.size());
    LMDJ_CHECK(
        acquired.value().total_bytes ==
        manifest.size() + kick.size() + demo.size());
    LMDJ_CHECK(transport.reads(sha256_hex(demo)) == 1);
    LMDJ_CHECK(transport.reads_of_kind(sha256_hex(demo), ":blob") == 1);

    // The demo's bytes are readable from the published Set, which is what a
    // preview path will ask for.
    const auto blob =
        store.read_artifact(sha256_hex(manifest), sha256_hex(demo));
    LMDJ_CHECK(blob.has_value());
    LMDJ_CHECK(text_of(blob.value()) == demo);

    // A reopened Set still reports the demo and the same total.
    const auto read = store.read(kSetId, kVersion, sha256_hex(manifest));
    LMDJ_CHECK(read.has_value());
    LMDJ_CHECK(read.value().manifest.demo->sha256 == sha256_hex(demo));
    LMDJ_CHECK(read.value().total_bytes == acquired.value().total_bytes);
  }
  {
    // Downloaded once, counted once: the demo names the Artifact slot 0
    // already names, so the Set holds one blob, not two.
    //
    // On its own this block cannot distinguish "deduplicated the demo against
    // the slot" from "ignored the demo": with the hashes equal, both produce
    // one fetch and one charge. It records the rule S11-D7 states. What pins
    // the rule against a store that stops deduplicating is the differing
    // byte_length case below, which is refused only because the demo and the
    // slot are compared with each other.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const auto manifest = manifest_bytes_with_demo({{0, "kick", kick}}, kick);
    transport.publish(manifest);
    transport.publish(kick);

    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick})));
    LMDJ_CHECK(acquired.has_value());
    LMDJ_CHECK(acquired.value().manifest.demo->sha256 == sha256_hex(kick));
    // One fetch for the shared hash, and the length is added once.
    LMDJ_CHECK(transport.reads(sha256_hex(kick)) == 1);
    LMDJ_CHECK(
        acquired.value().total_bytes == manifest.size() + kick.size());
    // Charging it twice would have produced this instead.
    LMDJ_CHECK(
        acquired.value().total_bytes !=
        manifest.size() + kick.size() + kick.size());
  }
  {
    // A demo blob whose bytes do not hash to the declared sha256.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const std::string demo(512, 'd');
    const auto manifest = manifest_bytes_with_demo({{0, "kick", kick}}, demo);
    transport.publish(manifest);
    transport.publish(kick);
    transport.publish_as(sha256_hex(demo), std::string(512, 'D'));

    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick, demo})));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(acquired.error().code == ErrorCode::io_error);
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
    // The refusal has to come from checking the demo's bytes, not from an
    // earlier total mismatch: a store that never enumerated the demo would
    // refuse with the same code and reason having fetched nothing.
    LMDJ_CHECK(transport.reads(sha256_hex(demo)) == 1);
    expect_invisible(store, workspace.path(), manifest);
  }
  {
    // A demo blob served at the declared hash but the wrong length.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const std::string demo(512, 'd');
    const auto manifest =
        manifest_bytes_with_demo({{0, "kick", kick}}, demo, demo.size() + 1);
    transport.publish(manifest);
    transport.publish(kick);
    transport.publish_as(sha256_hex(demo), demo);

    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport,
        entry_for(manifest, manifest.size() + kick.size() + demo.size() + 1));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
    // Again: fetched, then refused on its length -- not refused before the
    // demo was ever considered.
    LMDJ_CHECK(transport.reads(sha256_hex(demo)) == 1);
    expect_invisible(store, workspace.path(), manifest);
  }
  {
    // A demo reusing a slot's hash must agree with it on length, for the same
    // reason two slots must: one hash is one immutable object.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const auto manifest =
        manifest_bytes_with_demo({{0, "kick", kick}}, kick, kick.size() + 1);
    transport.publish(manifest);
    transport.publish(kick);

    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, manifest.size() + kick.size()));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(acquired.error().code == ErrorCode::io_error);
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
    // Refused before a single blob left the Catalog.
    LMDJ_CHECK(transport.reads(sha256_hex(kick)) == 0);
    expect_invisible(store, workspace.path(), manifest);
  }
  {
    // The demo is bounded by the same per-blob Host limit as any Artifact.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const std::string demo(512, 'd');
    const auto manifest = manifest_bytes_with_demo({{0, "kick", kick}}, demo);
    transport.publish(manifest);
    transport.publish(kick);
    transport.publish(demo);

    auto limits = generous_limits();
    limits.maximum_soundset_blob_bytes = demo.size() - 1;
    SoundSetStore store(
        workspace.path(), limits, platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick, demo})));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(
        refused_resource(acquired.error()) == "maximum_soundset_blob_bytes");
    LMDJ_CHECK(refused_observed(acquired.error()) == demo.size());
    LMDJ_CHECK(refused_limit(acquired.error()) == demo.size() - 1);
    expect_invisible(store, workspace.path(), manifest);
  }
}

// Every declared byte is checked, and a Set that fails any check never becomes
// visible: no partial Set, no orphaned staging.
void test_content_faults_leave_staging_invisible() {
  {
    // A declared total that does not equal manifest bytes plus unique blob
    // lengths is a mismatch before a single blob is fetched.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const auto manifest = manifest_bytes({{0, "kick", kick}});
    transport.publish(manifest);
    transport.publish(kick);
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick}) + 1));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(acquired.error().code == ErrorCode::io_error);
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
    LMDJ_CHECK(transport.reads(sha256_hex(kick)) == 0);
    expect_invisible(store, workspace.path(), manifest);
  }
  {
    // A blob whose bytes do not hash to the declared Artifact sha256.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const auto manifest = manifest_bytes({{0, "kick", kick}});
    transport.publish(manifest);
    transport.publish_as(sha256_hex(kick), std::string(64, 'K'));
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick})));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(acquired.error().code == ErrorCode::io_error);
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
    expect_invisible(store, workspace.path(), manifest);
  }
  {
    // A blob of the wrong length, even before its hash is considered.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const auto manifest = manifest_bytes({{0, "kick", kick}});
    transport.publish(manifest);
    transport.publish_as(sha256_hex(kick), std::string(63, 'k'));
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick})));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
    expect_invisible(store, workspace.path(), manifest);
  }
  {
    // A manifest object whose bytes do not hash to the Catalog's identity.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const auto manifest = manifest_bytes({{0, "kick", kick}});
    const auto other = manifest_bytes({{1, "snare", kick}});
    transport.publish_as(sha256_hex(manifest), other);
    transport.publish(kick);
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick})));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
    expect_invisible(store, workspace.path(), manifest);
  }
  {
    // A manifest whose own identity contradicts the Catalog entry.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string kick(64, 'k');
    const auto manifest = manifest_bytes({{0, "kick", kick}});
    transport.publish(manifest);
    transport.publish(kick);
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    auto entry = entry_for(manifest, declared_total(manifest, {kick}));
    entry.version = "2.0.0";
    const auto acquired = store.acquire(transport, entry);
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
  }
  {
    // A manifest that is not a Sound Set at all keeps the foundation parser's
    // own reason token.
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const std::string junk = "{\"contract\":\"lmdj.soundset.v1\"}";
    transport.publish(junk);
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired =
        store.acquire(transport, entry_for(junk, junk.size()));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(acquired.error().code == ErrorCode::invalid_argument);
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_manifest_invalid");
  }
}

// Eligibility is not Schema: an unallowlisted SPDX, an empty BY attribution,
// and a Catalog summary that disagrees with the manifest all fail closed.
void test_ineligible_licences_are_refused_before_publication() {
  const std::string kick(64, 'k');
  {
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const auto manifest =
        manifest_bytes({{0, "kick", kick}}, "MIT", "Alice");
    transport.publish(manifest);
    transport.publish(kick);
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport,
        entry_for(
            manifest,
            declared_total(manifest, {kick}),
            CatalogLicenseSummary{"MIT", "Alice"}));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(acquired.error().code == ErrorCode::permission_denied);
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_license_ineligible");
    expect_invisible(store, workspace.path(), manifest);
  }
  {
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const auto manifest =
        manifest_bytes({{0, "kick", kick}}, "CC-BY-4.0", "");
    transport.publish(manifest);
    transport.publish(kick);
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport, entry_for(manifest, declared_total(manifest, {kick})));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_license_ineligible");
  }
  {
    TempDirectory workspace;
    FakeCatalogTransport transport;
    const auto manifest = manifest_bytes({{0, "kick", kick}});
    transport.publish(manifest);
    transport.publish(kick);
    SoundSetStore store(
        workspace.path(), generous_limits(), platform_for(workspace.path()));
    const auto acquired = store.acquire(
        transport,
        entry_for(
            manifest,
            declared_total(manifest, {kick}),
            CatalogLicenseSummary{"CC-BY-4.0", "Bob"}));
    LMDJ_CHECK(!acquired.has_value());
    LMDJ_CHECK(reason_of(acquired.error()) == "soundset_license_ineligible");
  }
}

// An unreachable Catalog is not fatal: it is one reason token, and every Set
// already in the store stays readable.
void test_transport_failure_is_catalog_unavailable_and_not_fatal() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  transport.publish(manifest);
  transport.publish(kick);

  SoundSetStore store(
      workspace.path(), generous_limits(), platform_for(workspace.path()));
  LMDJ_CHECK(
      store
          .acquire(
              transport, entry_for(manifest, declared_total(manifest, {kick})))
          .has_value());

  FakeCatalogTransport offline;
  offline.fail_everything();
  const std::string other(48, 'o');
  const auto other_manifest = manifest_bytes({{2, "clap", other}});
  const auto acquired = offline.read_manifest_object(
      sha256_hex(other_manifest), 1024);
  LMDJ_CHECK(!acquired.has_value());

  const auto failed = store.acquire(
      offline,
      entry_for(other_manifest, declared_total(other_manifest, {other})));
  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(reason_of(failed.error()) == "catalog_unavailable");

  // A blob that vanishes mid-acquisition is the same non-fatal condition.
  FakeCatalogTransport partial;
  partial.publish(other_manifest);
  const auto missing_blob = store.acquire(
      partial,
      entry_for(other_manifest, declared_total(other_manifest, {other})));
  LMDJ_CHECK(!missing_blob.has_value());
  LMDJ_CHECK(reason_of(missing_blob.error()) == "catalog_unavailable");

  const auto still_readable =
      store.read(kSetId, kVersion, sha256_hex(manifest));
  LMDJ_CHECK(still_readable.has_value());
  LMDJ_CHECK(still_readable.value().manifest.canonical_bytes == manifest);
  LMDJ_CHECK(store.list().value().size() == 1);
}

struct LimitCase {
  // The exact Host manifest key the refusal must name, so Task 4 inherits a
  // pinned contract rather than a message it has to parse.
  const char* resource;
  std::uint64_t observed;
  SoundSetStoreLimits exact;
  SoundSetStoreLimits over;
};

// Each of the four Host limits is allowed at exactly its value and fails
// closed one byte past it, before any allocation or download.
void test_each_host_limit_is_exact_and_fails_closed_one_byte_over() {
  const std::string kick(64, 'k');
  const std::string snare(96, 's');
  const auto manifest =
      manifest_bytes({{0, "kick", kick}, {1, "snare", snare}});
  const auto unique_bytes = declared_total(manifest, {kick, snare});
  const std::uint64_t largest_blob = snare.size();

  const std::vector<LimitCase> cases{
      {"maximum_soundset_manifest_bytes",
       manifest.size(),
       {.maximum_soundset_manifest_bytes = manifest.size(),
        .maximum_soundset_blob_bytes = 1u << 20,
        .maximum_soundset_unique_bytes = unique_bytes,
        .maximum_soundset_staging_bytes = 1u << 22},
       {.maximum_soundset_manifest_bytes = manifest.size() - 1,
        .maximum_soundset_blob_bytes = 1u << 20,
        .maximum_soundset_unique_bytes = unique_bytes,
        .maximum_soundset_staging_bytes = 1u << 22}},
      {"maximum_soundset_blob_bytes",
       largest_blob,
       {.maximum_soundset_manifest_bytes = 1u << 20,
        .maximum_soundset_blob_bytes = largest_blob,
        .maximum_soundset_unique_bytes = unique_bytes,
        .maximum_soundset_staging_bytes = 1u << 22},
       {.maximum_soundset_manifest_bytes = 1u << 20,
        .maximum_soundset_blob_bytes = largest_blob - 1,
        .maximum_soundset_unique_bytes = unique_bytes,
        .maximum_soundset_staging_bytes = 1u << 22}},
      {"maximum_soundset_unique_bytes",
       unique_bytes,
       {.maximum_soundset_manifest_bytes = 1u << 20,
        .maximum_soundset_blob_bytes = 1u << 20,
        .maximum_soundset_unique_bytes = unique_bytes,
        .maximum_soundset_staging_bytes = 1u << 22},
       {.maximum_soundset_manifest_bytes = 1u << 20,
        .maximum_soundset_blob_bytes = 1u << 20,
        .maximum_soundset_unique_bytes = unique_bytes - 1,
        .maximum_soundset_staging_bytes = 1u << 22}},
      {"maximum_soundset_staging_bytes",
       unique_bytes,
       {.maximum_soundset_manifest_bytes = 1u << 20,
        .maximum_soundset_blob_bytes = 1u << 20,
        .maximum_soundset_unique_bytes = unique_bytes,
        .maximum_soundset_staging_bytes = unique_bytes},
       {.maximum_soundset_manifest_bytes = 1u << 20,
        .maximum_soundset_blob_bytes = 1u << 20,
        .maximum_soundset_unique_bytes = unique_bytes,
        .maximum_soundset_staging_bytes = unique_bytes - 1}},
  };

  for (const auto& limit_case : cases) {
    {
      TempDirectory workspace;
      FakeCatalogTransport transport;
      transport.publish(manifest);
      transport.publish(kick);
      transport.publish(snare);
      SoundSetStore store(
          workspace.path(), limit_case.exact, platform_for(workspace.path()));
      const auto acquired =
          store.acquire(transport, entry_for(manifest, unique_bytes));
      LMDJ_CHECK(acquired.has_value());
    }
    {
      TempDirectory workspace;
      FakeCatalogTransport transport;
      transport.publish(manifest);
      transport.publish(kick);
      transport.publish(snare);
      SoundSetStore store(
          workspace.path(), limit_case.over, platform_for(workspace.path()));
      const auto acquired =
          store.acquire(transport, entry_for(manifest, unique_bytes));
      LMDJ_CHECK(!acquired.has_value());
      const auto& error = acquired.error();
      LMDJ_CHECK(error.code == ErrorCode::io_error);
      LMDJ_CHECK(refused_resource(error) == limit_case.resource);
      LMDJ_CHECK(refused_observed(error) == limit_case.observed);
      LMDJ_CHECK(refused_limit(error) == limit_case.observed - 1);
      expect_invisible(store, workspace.path(), manifest);
    }
  }
}

// The staging limit is a limit on the staging area, not on one Set: bytes an
// earlier interrupted acquisition left behind still count.
void test_staging_limit_counts_bytes_already_staged() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  const auto unique_bytes = declared_total(manifest, {kick});
  transport.publish(manifest);
  transport.publish(kick);

  const auto staging =
      workspace.path() / ".lmdj-host" / "soundset-staging" / "leftover";
  std::filesystem::create_directories(staging);
  std::ofstream{staging / "orphan", std::ios::binary} << std::string(32, 'x');

  const auto staging_limits = [unique_bytes](std::uint64_t headroom) {
    return SoundSetStoreLimits{
        .maximum_soundset_manifest_bytes = 1u << 20,
        .maximum_soundset_blob_bytes = 1u << 20,
        .maximum_soundset_unique_bytes = unique_bytes,
        .maximum_soundset_staging_bytes = unique_bytes + headroom,
    };
  };

  SoundSetStore store(
      workspace.path(), staging_limits(31), platform_for(workspace.path()));
  const auto refused =
      store.acquire(transport, entry_for(manifest, unique_bytes));
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(
      refused_resource(refused.error()) == "maximum_soundset_staging_bytes");
  LMDJ_CHECK(refused_observed(refused.error()) == unique_bytes + 32);

  // A stray file directly in the staging root counts the same way.
  std::ofstream{
      workspace.path() / ".lmdj-host" / "soundset-staging" / "stray",
      std::ios::binary}
      << std::string(8, 'y');
  SoundSetStore counted(
      workspace.path(), staging_limits(39), platform_for(workspace.path()));
  LMDJ_CHECK(
      refused_resource(
          counted.acquire(transport, entry_for(manifest, unique_bytes))
              .error()) == "maximum_soundset_staging_bytes");

  // So do bytes nested deeper than this store's own flat staging shape: an
  // uncounted byte would make the limit fail open.
  const auto nested = workspace.path() / ".lmdj-host" / "soundset-staging" /
                      "leftover" / "deeper";
  std::filesystem::create_directories(nested);
  std::ofstream{nested / "buried", std::ios::binary} << std::string(16, 'z');
  SoundSetStore deep(
      workspace.path(), staging_limits(55), platform_for(workspace.path()));
  LMDJ_CHECK(
      refused_resource(
          deep.acquire(transport, entry_for(manifest, unique_bytes)).error()) ==
      "maximum_soundset_staging_bytes");

  SoundSetStore roomier(
      workspace.path(), staging_limits(56), platform_for(workspace.path()));
  LMDJ_CHECK(roomier.acquire(transport, entry_for(manifest, unique_bytes))
                 .has_value());
}

// A retry replaces its own interrupted staging rather than being charged for
// it twice.
void test_a_retry_is_not_charged_for_its_own_interrupted_staging() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  const auto unique_bytes = declared_total(manifest, {kick});
  transport.publish(manifest);
  transport.publish(kick);

  const auto interrupted = workspace.path() / ".lmdj-host" /
                           "soundset-staging" / sha256_hex(manifest);
  std::filesystem::create_directories(interrupted);
  std::ofstream{interrupted / "manifest.json", std::ios::binary}
      << std::string(manifest.size(), 'j');

  SoundSetStore store(
      workspace.path(),
      SoundSetStoreLimits{
          .maximum_soundset_manifest_bytes = 1u << 20,
          .maximum_soundset_blob_bytes = 1u << 20,
          .maximum_soundset_unique_bytes = unique_bytes,
          .maximum_soundset_staging_bytes = unique_bytes,
      },
      platform_for(workspace.path()));
  LMDJ_CHECK(
      store.acquire(transport, entry_for(manifest, unique_bytes)).has_value());
}

void test_store_refuses_a_workspace_root_that_is_not_managed() {
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  transport.publish(manifest);
  transport.publish(kick);
  SoundSetStore store(
      "relative/workspace",
      generous_limits(),
      lmdj::project_io::make_native_project_storage_platform("/tmp"));
  const auto acquired = store.acquire(
      transport, entry_for(manifest, declared_total(manifest, {kick})));
  LMDJ_CHECK(!acquired.has_value());
  LMDJ_CHECK(acquired.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(!store.list().has_value());
  LMDJ_CHECK(!store.read(kSetId, kVersion, sha256_hex(manifest)).has_value());
}

void test_reads_of_absent_sets_and_artifacts_are_not_found() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  transport.publish(manifest);
  transport.publish(kick);
  SoundSetStore store(
      workspace.path(), generous_limits(), platform_for(workspace.path()));

  const auto empty = store.list();
  LMDJ_CHECK(empty.has_value());
  LMDJ_CHECK(empty.value().empty());
  LMDJ_CHECK(!store.read(kSetId, kVersion, sha256_hex(manifest)).has_value());

  LMDJ_CHECK(
      store
          .acquire(
              transport, entry_for(manifest, declared_total(manifest, {kick})))
          .has_value());

  // A malformed identity never reaches the filesystem.
  LMDJ_CHECK(!store.read(kSetId, kVersion, "not-a-hash").has_value());
  LMDJ_CHECK(!store.read("not-a-uuid", kVersion, sha256_hex(manifest))
                  .has_value());
  LMDJ_CHECK(!store.read(kSetId, "1.0", sha256_hex(manifest)).has_value());
  LMDJ_CHECK(
      !store.read_artifact(sha256_hex(manifest), "../escape").has_value());

  // An Artifact the published manifest does not declare is not in the Set.
  const auto stranger = store.read_artifact(
      sha256_hex(manifest), sha256_hex(std::string(8, 'z')));
  LMDJ_CHECK(!stranger.has_value());
  LMDJ_CHECK(stranger.error().code == ErrorCode::not_found);
}

// One hash is one immutable object. A manifest that gives the same sha256 two
// descriptions cannot be satisfied, and must not reach the Set Store with the
// larger declaration unchecked against maximum_soundset_blob_bytes.
void test_one_hash_with_two_descriptions_is_refused() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_with_contradictory_artifact(kick, 1u << 30);
  transport.publish(manifest);
  transport.publish(kick);

  SoundSetStore store(
      workspace.path(), generous_limits(), platform_for(workspace.path()));
  const auto acquired = store.acquire(
      transport, entry_for(manifest, manifest.size() + kick.size()));
  LMDJ_CHECK(!acquired.has_value());
  LMDJ_CHECK(acquired.error().code == ErrorCode::io_error);
  LMDJ_CHECK(reason_of(acquired.error()) == "soundset_content_mismatch");
  LMDJ_CHECK(transport.reads(sha256_hex(kick)) == 0);
  expect_invisible(store, workspace.path(), manifest);
}

// A published Set whose bytes were changed under the store says so, rather
// than silently re-downloading and then reporting a collision with the
// corruption it was trying to replace.
void test_a_corrupted_published_set_reports_the_corruption() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  transport.publish(manifest);
  transport.publish(kick);

  SoundSetStore store(
      workspace.path(), generous_limits(), platform_for(workspace.path()));
  LMDJ_CHECK(
      store
          .acquire(
              transport, entry_for(manifest, declared_total(manifest, {kick})))
          .has_value());

  const auto stored = workspace.path() / ".lmdj-host" / "soundsets" /
                      sha256_hex(manifest) / "manifest.json";
  std::filesystem::permissions(
      stored,
      std::filesystem::perms::owner_write,
      std::filesystem::perm_options::add);
  std::ofstream{stored, std::ios::binary | std::ios::trunc} << "tampered";

  const auto again = store.acquire(
      transport, entry_for(manifest, declared_total(manifest, {kick})));
  LMDJ_CHECK(!again.has_value());
  LMDJ_CHECK(reason_of(again.error()) == "soundset_content_mismatch");
  LMDJ_CHECK(!store.read(kSetId, kVersion, sha256_hex(manifest)).has_value());
  // A Set that cannot be read is not listed as one.
  LMDJ_CHECK(store.list().value().empty());
}

// Forwards every storage operation to a native platform until one named step
// is armed to fail with a quota-shaped refusal, the way a full volume reports
// it. Exists to pin what each refusal names once it crosses the Facade
// boundary as a bare code (#942).
class StepFailingPlatform final : public ProjectStoragePlatform {
 public:
  enum class Step {
    none,
    lease,
    ensure_directory,
    create_immutable,
    publish,
    list_directories,
    directory_exists,
    read_artifact_bytes,
  };

  explicit StepFailingPlatform(std::shared_ptr<ProjectStoragePlatform> inner)
      : inner_(std::move(inner)) {}

  void fail(Step step) { step_ = step; }

  lmdj::foundation::Result<
      std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& path) override {
    using Result = lmdj::foundation::Result<
        std::unique_ptr<lmdj::project_io::ProjectWriterLease>>;
    if (step_ == Step::lease) {
      return Result::failure(refusal());
    }
    return inner_->acquire_writer(path);
  }

  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    if (step_ == Step::ensure_directory) {
      return lmdj::foundation::Result<void>::failure(refusal());
    }
    return inner_->ensure_directory(path);
  }

  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    return inner_->exists(path);
  }

  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    return inner_->byte_length(path);
  }

  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    using Result = lmdj::foundation::Result<std::vector<std::byte>>;
    // The manifest read stays healthy so read_artifact reaches its own blob
    // read; only Artifact bytes carry the armed failure.
    if (step_ == Step::read_artifact_bytes &&
        path.filename() != "manifest.json") {
      return Result::failure(refusal());
    }
    return inner_->read_complete(path);
  }

  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    if (step_ == Step::create_immutable) {
      return lmdj::foundation::Result<void>::failure(refusal());
    }
    return inner_->create_immutable(path, bytes);
  }

  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner_->replace_complete(path, bytes);
  }

  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> bytes) override {
    return inner_->append_durable(path, valid_prefix_length, bytes);
  }

  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    return inner_->remove(path);
  }

  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    return inner_->list_names(path);
  }

  lmdj::foundation::Result<std::vector<std::string>> list_directories(
      const std::filesystem::path& path) const override {
    using Result = lmdj::foundation::Result<std::vector<std::string>>;
    if (step_ == Step::list_directories) {
      return Result::failure(refusal());
    }
    return inner_->list_directories(path);
  }

  lmdj::foundation::Result<void> remove_tree(
      const std::filesystem::path& path) override {
    return inner_->remove_tree(path);
  }

  lmdj::foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path& staging,
      const std::filesystem::path& destination) override {
    if (step_ == Step::publish) {
      return lmdj::foundation::Result<void>::failure(refusal());
    }
    return inner_->publish_directory_if_absent(staging, destination);
  }

  lmdj::foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const override {
    if (step_ == Step::directory_exists) {
      return lmdj::foundation::Result<bool>::failure(refusal());
    }
    return inner_->directory_exists(path);
  }

  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& root) const override {
    return inner_->validate_managed_tree(root);
  }

 private:
  // The shape a real platform produces for a full volume.
  static Error refusal() {
    return Error{
        ErrorCode::io_error,
        "injected storage failure",
        {{"storage_condition",
          std::string{lmdj::project_io::kStorageConditionQuotaExceeded}}},
    };
  }

  std::shared_ptr<ProjectStoragePlatform> inner_;
  Step step_ = Step::none;
};

// A refused storage step keeps its code and its storage_condition, names the
// step in message, and mints no Contract-locked reason.
void expect_named_storage_refusal(
    const Error& error,
    std::string_view expected_message) {
  LMDJ_CHECK(error.code == ErrorCode::io_error);
  LMDJ_CHECK(error.message == expected_message);
  LMDJ_CHECK(reason_of(error).empty());
  LMDJ_CHECK(
      error.details.is_object() &&
      error.details.value("storage_condition", std::string{}) ==
          std::string{lmdj::project_io::kStorageConditionQuotaExceeded});
}

void test_a_refused_destination_lease_names_the_step() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  transport.publish(manifest);
  transport.publish(kick);
  auto platform =
      std::make_shared<StepFailingPlatform>(platform_for(workspace.path()));
  platform->fail(StepFailingPlatform::Step::lease);

  SoundSetStore store(workspace.path(), generous_limits(), platform);
  const auto acquired = store.acquire(
      transport, entry_for(manifest, declared_total(manifest, {kick})));
  LMDJ_CHECK(!acquired.has_value());
  expect_named_storage_refusal(
      acquired.error(), "Sound Set destination could not be leased");
  expect_invisible(store, workspace.path(), manifest);
}

void test_a_refused_staging_write_names_the_step() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  transport.publish(manifest);
  transport.publish(kick);
  auto platform =
      std::make_shared<StepFailingPlatform>(platform_for(workspace.path()));
  platform->fail(StepFailingPlatform::Step::create_immutable);

  SoundSetStore store(workspace.path(), generous_limits(), platform);
  const auto acquired = store.acquire(
      transport, entry_for(manifest, declared_total(manifest, {kick})));
  LMDJ_CHECK(!acquired.has_value());
  expect_named_storage_refusal(
      acquired.error(), "Sound Set manifest could not be staged");
  expect_invisible(store, workspace.path(), manifest);
}

void test_a_refused_publication_names_the_step() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  transport.publish(manifest);
  transport.publish(kick);
  auto platform =
      std::make_shared<StepFailingPlatform>(platform_for(workspace.path()));
  platform->fail(StepFailingPlatform::Step::publish);

  SoundSetStore store(workspace.path(), generous_limits(), platform);
  const auto acquired = store.acquire(
      transport, entry_for(manifest, declared_total(manifest, {kick})));
  LMDJ_CHECK(!acquired.has_value());
  expect_named_storage_refusal(
      acquired.error(), "Sound Set could not be published");
  expect_invisible(store, workspace.path(), manifest);
}

void test_a_refused_store_listing_names_the_step() {
  TempDirectory workspace;
  std::filesystem::create_directories(
      workspace.path() / ".lmdj-host" / "soundsets");
  auto platform =
      std::make_shared<StepFailingPlatform>(platform_for(workspace.path()));
  platform->fail(StepFailingPlatform::Step::list_directories);

  SoundSetStore store(workspace.path(), generous_limits(), platform);
  const auto sets = store.list();
  LMDJ_CHECK(!sets.has_value());
  expect_named_storage_refusal(
      sets.error(), "Sound Set store could not be listed");
}

void test_a_failed_read_reports_storage_not_absence() {
  TempDirectory workspace;
  auto platform =
      std::make_shared<StepFailingPlatform>(platform_for(workspace.path()));
  platform->fail(StepFailingPlatform::Step::directory_exists);

  SoundSetStore store(workspace.path(), generous_limits(), platform);
  const auto stored = store.read(kSetId, kVersion, sha256_hex("x"));
  LMDJ_CHECK(!stored.has_value());
  expect_named_storage_refusal(
      stored.error(), "Sound Set directory could not be inspected");
}

void test_a_refused_artifact_read_names_the_step() {
  TempDirectory workspace;
  FakeCatalogTransport transport;
  const std::string kick(64, 'k');
  const auto manifest = manifest_bytes({{0, "kick", kick}});
  transport.publish(manifest);
  transport.publish(kick);
  auto platform =
      std::make_shared<StepFailingPlatform>(platform_for(workspace.path()));

  SoundSetStore store(workspace.path(), generous_limits(), platform);
  LMDJ_CHECK(
      store
          .acquire(
              transport, entry_for(manifest, declared_total(manifest, {kick})))
          .has_value());

  platform->fail(StepFailingPlatform::Step::read_artifact_bytes);
  const auto bytes =
      store.read_artifact(sha256_hex(manifest), sha256_hex(kick));
  LMDJ_CHECK(!bytes.has_value());
  expect_named_storage_refusal(
      bytes.error(), "Sound Set Artifact could not be read");
}

}  // namespace

int main() {
  try {
    test_acquire_publishes_a_verified_set();
    test_repeated_artifact_hash_is_fetched_once();
    test_content_faults_leave_staging_invisible();
    test_ineligible_licences_are_refused_before_publication();
    test_transport_failure_is_catalog_unavailable_and_not_fatal();
    test_each_host_limit_is_exact_and_fails_closed_one_byte_over();
    test_staging_limit_counts_bytes_already_staged();
    test_a_retry_is_not_charged_for_its_own_interrupted_staging();
    test_store_refuses_a_workspace_root_that_is_not_managed();
    test_reads_of_absent_sets_and_artifacts_are_not_found();
    test_one_hash_with_two_descriptions_is_refused();
    test_set_level_demo_is_verified_and_counted_once();
    test_a_corrupted_published_set_reports_the_corruption();
    test_a_refused_destination_lease_names_the_step();
    test_a_refused_staging_write_names_the_step();
    test_a_refused_publication_names_the_step();
    test_a_refused_store_listing_names_the_step();
    test_a_failed_read_reports_storage_not_absence();
    test_a_refused_artifact_read_names_the_step();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "sound set store tests: PASS\n";
  return 0;
}
