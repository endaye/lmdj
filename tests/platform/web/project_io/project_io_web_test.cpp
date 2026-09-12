#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

#include <emscripten.h>
#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/foundation/soundset_manifest.hpp>
#include <lmdj/project_io/project_bundle_transfer.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/soundset_catalog_transport.hpp>
#include <lmdj/project_io/soundset_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/workspace_cache.hpp>

// Fixture reporting only; every transition below uses SequenceJournal's public API.
#include "../../../../packages/project-io/src/sequence_admission_codec.hpp"

namespace lmdj::project_io {
std::shared_ptr<ProjectStoragePlatform> make_web_project_storage_platform();
std::shared_ptr<ProjectStoragePlatform>
make_web_project_storage_platform_for_test(bool mounted);
}

extern "C" int lmdj_opfs_append_flush_count();
extern "C" int lmdj_opfs_immutable_write_count();
extern "C" int lmdj_opfs_publication_max_chunk_bytes();

namespace {

using lmdj::foundation::Result;

std::unique_ptr<lmdj::project_io::ProjectWriterLease> held_lease;

void report_progress(const char* stage) {
  MAIN_THREAD_EM_ASM({ window.lmdjProjectIoWebProgress = UTF8ToString($0); },
                     stage);
}

void require(bool condition, std::string message) {
  if (!condition) throw std::runtime_error(std::move(message));
}

template <typename T>
T value(Result<T> result, const char* operation) {
  if (!result.has_value()) throw std::runtime_error(operation);
  return std::move(result.value());
}

void success(Result<void> result, const char* operation) {
  if (!result.has_value()) throw std::runtime_error(operation);
}

std::span<const std::byte> bytes(const std::string& input) {
  return {reinterpret_cast<const std::byte*>(input.data()), input.size()};
}

std::string text(const std::vector<std::byte>& input) {
  return {reinterpret_cast<const char*>(input.data()), input.size()};
}

using IntentInventory = std::vector<std::pair<std::string, std::string>>;

IntentInventory storage_intent_inventory(
    const lmdj::project_io::ProjectStoragePlatform& platform) {
  const auto root = std::filesystem::path{
      "/lmdj-workspace/.lmdj-host/storage-intents"};
  if (!value(platform.directory_exists(root), "storage intent root exists")) {
    return {};
  }
  IntentInventory inventory;
  const auto directories =
      value(platform.list_directories(root), "storage intent directories");
  for (const auto& directory : directories) {
    inventory.emplace_back(directory + "/", "");
    const auto scope = root / directory;
    const auto names = value(
        platform.list_names(scope), "storage intent names");
    for (const auto& name : names) {
      inventory.emplace_back(
          directory + "/" + name,
          text(value(
              platform.read_complete(scope / name),
              "storage intent content")));
    }
  }
  return inventory;
}

template <typename T>
nlohmann::json mutation_result(const Result<T>& result) {
  if (result.has_value()) {
    return {{"status", "succeeded"}, {"errorCode", ""},
            {"storageCondition", ""}};
  }
  return {
      {"status", "failed"},
      {"errorCode", lmdj::foundation::error_code_name(result.error().code)},
      {"storageCondition",
       result.error().details.value("storage_condition", "")},
  };
}

std::string uuid(std::string_view suffix) {
  return "00000000-0000-4000-8000-" + std::string(12 - suffix.size(), '0') +
         std::string{suffix};
}

std::string query(std::string_view name) {
  std::array<char, 192> output{};
  MAIN_THREAD_EM_ASM({
    const value = new URL(window.location.href).searchParams.get(UTF8ToString($0)) ?? "";
    stringToUTF8(value, $1, $2);
  }, name.data(), output.data(), output.size());
  return output.data();
}

constexpr std::string_view kSampleBytes = "RIFF-web-sample";

std::filesystem::path sample_staging_root() {
  return "/lmdj-workspace/.lmdj-host/sample-staging";
}

std::filesystem::path workspace_cache_root() {
  return "/lmdj-workspace/.lmdj-host/workspace-cache";
}

std::string cache_key(std::string_view bundle, std::string_view suffix) {
  return "sample-editor.v1/" + std::string{bundle} + "-" +
         std::string{suffix} + ".bin";
}

nlohmann::json pad_playback_json(const lmdj::domain::PadSlot& pad) {
  require(
      pad.playback.trigger_mode == lmdj::domain::TriggerMode::one_shot,
      "Sample Pad trigger mode changed");
  return {
      {"trimStartFrame", pad.playback.trim_start_frame},
      {"trimEndFrame",
       pad.playback.trim_end_frame.has_value()
           ? nlohmann::json(*pad.playback.trim_end_frame)
           : nlohmann::json(nullptr)},
      {"triggerMode", "one_shot"},
      {"gainMillidb", pad.playback.gain_millidb},
      {"muted", pad.playback.muted},
  };
}

nlohmann::json prepare_sample_cache(
    const std::shared_ptr<lmdj::project_io::ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle) {
  using namespace lmdj;
  project_io::ProjectStore store{platform};
  auto initial = value(
      domain::create_project(foundation::ProjectId{uuid("19")}, 120),
      "Sample Web Project create state");
  require(
      initial.contract == domain::ProjectContract::v5,
      "Sample Web Project did not start as v5");
  success(store.create(bundle, initial), "Sample Web Project create");

  const auto staging_root = sample_staging_root();
  const auto old_staging = staging_root / uuid("20");
  success(platform->ensure_directory(staging_root), "Sample staging root");
  auto staging_lease = value(
      platform->acquire_writer(old_staging), "old Sample staging lease");
  success(platform->remove_tree(old_staging), "old Sample staging cleanup");
  success(platform->ensure_directory(old_staging), "old Sample staging seed");
  const auto marker = nlohmann::json{
      {"contract", "lmdj.sample-staging.v1"},
      {"created_unix_seconds", 0},
      {"state", "incomplete"},
      {"token", uuid("20")},
  }.dump() + "\n";
  success(
      platform->create_immutable(old_staging / "state.json", bytes(marker)),
      "old Sample staging marker");
  success(
      platform->create_immutable(
          old_staging / "payload.wav", bytes("old-orphan")),
      "old Sample staging payload");
  staging_lease.reset();

  return {
      {"revision", initial.revision},
      {"contract", "lmdj.project.v5"},
      {"oldStagingPresent",
       value(
           platform->directory_exists(old_staging),
           "old Sample staging presence")},
      {"stagingDirectories",
       value(platform->list_directories(staging_root), "Sample staging list")},
  };
}

nlohmann::json mutate_sample_cache(
    const std::shared_ptr<lmdj::project_io::ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    std::string_view bundle_name) {
  using namespace lmdj;
  project_io::ProjectStore store{platform};
  const auto current = value(store.load(bundle), "Sample Web Project load");
  const foundation::AssetId asset_id{uuid("22")};
  const std::string sample_bytes{kSampleBytes};
  const auto request = project_io::ProjectStore::ImportAssignSampleBytesRequest{
      domain::CommandMeta{foundation::CommandId{uuid("21")}, current.revision},
      domain::PadSlotId{2, 7},
      asset_id,
      "audio/wav",
      bytes(sample_bytes),
  };
  const auto imported = value(
      store.import_assign_sample_bytes(bundle, request),
      "Sample Web Project import and assign");
  require(!imported.replayed, "first Sample import was replayed");
  require(
      imported.state.contract == domain::ProjectContract::v5 &&
          imported.state.revision == 1,
      "Sample import did not commit one v5 revision");
  const auto replayed = value(
      store.import_assign_sample_bytes(bundle, request),
      "Sample Web Project exact replay");
  require(
      replayed.replayed && replayed.state == imported.state,
      "Sample import exact replay changed Project Truth");

  const auto& pad = imported.state.banks.at(2).at(7);
  require(pad.asset_id == asset_id, "Sample Pad assignment changed");
  const auto& artifact = imported.state.assets.at(asset_id).artifact;
  const auto artifact_bytes = value(
      store.read_artifact(bundle, artifact), "Sample Artifact read");

  const auto staging_root = sample_staging_root();
  const auto old_staging = staging_root / uuid("20");
  const auto completed_staging = staging_root / uuid("21");
  const auto staging_directories = value(
      platform->list_directories(staging_root), "Sample staging inventory");

  const auto cache_root = workspace_cache_root();
  const auto latest_key = cache_key(bundle_name, "latest");
  const auto corrupt_key = cache_key(bundle_name, "corrupt");
  project_io::WorkspaceCacheStore cache{cache_root, platform};
  success(cache.write(latest_key, bytes("cache-first")), "cache first write");
  const auto cache_first = value(cache.read(latest_key), "cache first read");
  require(cache_first.has_value(), "cache first value is missing");
  success(cache.write(latest_key, bytes("cache-latest")), "cache replacement");
  const auto cache_latest = value(cache.read(latest_key), "cache latest read");
  require(cache_latest.has_value(), "cache latest value is missing");

  success(cache.write(corrupt_key, bytes("cache-valid")), "cache corrupt seed");
  auto cache_lease = value(
      platform->acquire_writer(cache_root), "cache corruption lease");
  success(
      platform->replace_complete(
          cache_root / corrupt_key, bytes("corrupt-cache-entry")),
      "cache corruption");
  cache_lease.reset();
  const auto corrupt = value(cache.read(corrupt_key), "corrupt cache read");

  return {
      {"revision", imported.state.revision},
      {"contract", "lmdj.project.v5"},
      {"replayed", replayed.replayed},
      {"padAssetId", pad.asset_id->value()},
      {"padPlayback", pad_playback_json(pad)},
      {"assetCount", imported.state.assets.size()},
      {"artifactSha256", artifact.sha256},
      {"artifactByteLength", artifact.byte_length},
      {"artifactBytes", text(artifact_bytes)},
      {"oldStagingPresent",
       value(
           platform->directory_exists(old_staging),
           "old Sample staging after import")},
      {"completedStagingPresent",
       value(
           platform->directory_exists(completed_staging),
           "completed Sample staging after import")},
      {"stagingDirectories", staging_directories},
      {"cacheFirst", text(*cache_first)},
      {"cacheLatest", text(*cache_latest)},
      {"corruptCacheMiss", !corrupt.has_value()},
      {"corruptCachePresent",
       value(
           platform->exists(cache_root / corrupt_key),
           "corrupt cache cleanup")},
  };
}

nlohmann::json reopen_sample_cache(
    const std::shared_ptr<lmdj::project_io::ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    std::string_view bundle_name) {
  using namespace lmdj;
  project_io::ProjectStore store{platform};
  const auto reopened = value(store.load(bundle), "Sample Web Project reopen");
  require(
      reopened.contract == domain::ProjectContract::v5 &&
          reopened.revision == 1,
      "reopened Sample Project changed revision or contract");
  const foundation::AssetId asset_id{uuid("22")};
  const auto& pad = reopened.banks.at(2).at(7);
  require(pad.asset_id == asset_id, "reopened Sample Pad assignment changed");
  const auto& artifact = reopened.assets.at(asset_id).artifact;
  const auto artifact_bytes = value(
      store.read_artifact(bundle, artifact), "reopened Sample Artifact read");

  const auto staging_root = sample_staging_root();
  const auto old_staging = staging_root / uuid("20");
  const auto completed_staging = staging_root / uuid("21");
  const auto staging_directories = value(
      platform->list_directories(staging_root),
      "reopened Sample staging inventory");
  const auto cache_root = workspace_cache_root();
  const auto latest_key = cache_key(bundle_name, "latest");
  const auto corrupt_key = cache_key(bundle_name, "corrupt");
  project_io::WorkspaceCacheStore cache{cache_root, platform};
  const auto cache_latest = value(cache.read(latest_key), "reopened cache read");
  require(cache_latest.has_value(), "reopened cache value is missing");
  const auto corrupt = value(cache.read(corrupt_key), "reopened corrupt cache read");

  return {
      {"revision", reopened.revision},
      {"contract", "lmdj.project.v5"},
      {"padAssetId", pad.asset_id->value()},
      {"padPlayback", pad_playback_json(pad)},
      {"assetCount", reopened.assets.size()},
      {"artifactSha256", artifact.sha256},
      {"artifactByteLength", artifact.byte_length},
      {"artifactBytes", text(artifact_bytes)},
      {"oldStagingPresent",
       value(
           platform->directory_exists(old_staging),
           "old Sample staging after reopen")},
      {"completedStagingPresent",
       value(
           platform->directory_exists(completed_staging),
           "completed Sample staging after reopen")},
      {"stagingDirectories", staging_directories},
      {"cacheLatest", text(*cache_latest)},
      {"corruptCacheMiss", !corrupt.has_value()},
      {"corruptCachePresent",
       value(
           platform->exists(cache_root / corrupt_key),
           "reopened corrupt cache cleanup")},
  };
}

std::optional<nlohmann::json> run_sample_cache_action() {
  const auto action = query("action");
  if (action != "prepare_sample_cache" &&
      action != "mutate_sample_cache" &&
      action != "reopen_sample_cache") {
    return std::nullopt;
  }
  const auto requested_bundle = query("bundle");
  require(!requested_bundle.empty(), "Sample/cache bundle is missing");
  const auto bundle = std::filesystem::path{"/lmdj-workspace"} /
                      (requested_bundle + ".lmdj");
  auto platform = lmdj::project_io::make_web_project_storage_platform();
  require(platform != nullptr, "Web platform factory returned null");
  if (action == "prepare_sample_cache") {
    return nlohmann::json{
        {"complete", true},
        {"result", prepare_sample_cache(platform, bundle)},
    };
  }
  if (action == "mutate_sample_cache") {
    return nlohmann::json{
        {"complete", true},
        {"result", mutate_sample_cache(platform, bundle, requested_bundle)},
    };
  }
  return nlohmann::json{
      {"complete", true},
      {"result", reopen_sample_cache(platform, bundle, requested_bundle)},
  };
}

// #902: the Workspace Sound Set Store publishing onto OPFS. The native Set
// Store tests prove Core's download, verification and eligibility; nothing
// exercised the atomic publication step on the Web storage platform, where a
// directory publish is a bounded copy under a writer lease held on the
// destination rather than a rename.
constexpr std::string_view kSoundSetId = "10000000-0000-4000-8000-000000000001";
constexpr std::string_view kSoundSetVersion = "1.0.0";

std::string sha256_hex(std::string_view input) {
  picosha2::hash256_one_by_one hasher;
  if (!input.empty()) {
    const auto* begin = reinterpret_cast<const unsigned char*>(input.data());
    hasher.process(begin, begin + input.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

// Runs in the fixture's proxied main Worker after C++ has returned success.
// This is lost response AFTER durability, not interruption inside access.flush().
EM_ASYNC_JS(void, admission_response_barrier, (const char* encoded), {
  await LmdjOpfsTest.markFault(UTF8ToString(encoded));
  await new Promise(() => {});
});

nlohmann::json admission_events(
    const std::vector<lmdj::domain::PatternEvent>& events) {
  auto result = nlohmann::json::array();
  for (const auto& event : events) {
    result.push_back(lmdj::project_io::admission_codec::encode(event));
  }
  return result;
}

nlohmann::json admission_summary(
    const lmdj::project_io::ActiveSequenceJournal& journal) {
  using lmdj::project_io::admission_codec::encode;
  auto flushes = nlohmann::json::array();
  for (const auto& f : journal.flushes) {
    flushes.push_back({{"flush_seq", f.flush_seq},
        {"command_id", f.command_id.value()}, {"pattern_id", f.pattern_id.value()},
        {"expected_revision", f.expected_revision}, {"completed", f.completed},
        {"canonical_events", admission_events(f.canonical_events)},
        {"recovery_events", admission_events(f.recovery_events)}});
  }
  return {{"session_id", journal.session_id.value()},
      {"pattern_id", journal.pattern_id.value()}, {"bars", journal.bars},
      {"pattern_fingerprint", journal.pattern_fingerprint},
      {"expected_revision", journal.expected_revision},
      {"state", static_cast<unsigned>(journal.state)},
      {"next_tail_seq", journal.next_tail_seq}, {"next_flush_seq", journal.next_flush_seq},
      {"last_input_sequence", journal.last_input_sequence
          ? nlohmann::json(*journal.last_input_sequence) : nlohmann::json(nullptr)},
      {"pending_events", admission_events(journal.pending_events)},
      {"flushes", flushes},
      {"admission", journal.admission ? encode(*journal.admission) : nlohmann::json(nullptr)}};
}

std::optional<nlohmann::json> run_admission_action() {
  if (query("action") != "admission") return std::nullopt;
  using namespace lmdj;
  using namespace project_io;
  const auto name = query("bundle");
  require(!name.empty(), "admission bundle missing");
  const auto bundle = std::filesystem::path{"/lmdj-workspace"} / (name + ".lmdj");
  const auto path = bundle / "recovery/active/sequence.jsonl";
  const auto step = query("step");
  const bool target = query("target") == "1";
  auto platform = make_web_project_storage_platform();
  ProjectStore store{platform};
  SequenceJournal journal{platform};
  const foundation::ProjectId project{uuid("301")};
  const foundation::SequenceSessionId session{uuid("302")};
  const domain::Pattern source_pattern{foundation::PatternId{uuid("303")}, 1, {}};
  const domain::Pattern target_pattern{foundation::PatternId{uuid("304")}, 1, {}};
  SequenceAdmissionPreparation preparation{
      {foundation::CommandId{uuid("305")}, 7, 11}, project, source_pattern.id, 21, 10};
  if (query("limit") == "2") preparation.candidate_limit = 2;
  const auto& identity = preparation.identity;
  const SequenceAdmissionCandidate press{target ? 12U : 10U, target ? 1600U : 1000U,
      {0, 0}, SequenceCandidateKind::press, 100, target ? 72U : 71U};
  auto release = press;
  ++release.watermark;
  release.runtime_frame += 100;
  release.kind = SequenceCandidateKind::release;
  release.velocity = 0;
  const auto& pattern = target ? target_pattern : source_pattern;
  const std::vector<domain::PatternEvent> source_tail{
      {{0, 1}, 0, 120, 90}, {{0, 0}, 240, 120, 100}};
  const std::vector<domain::PatternEvent> target_tail{{{0, 0}, 0, 120, 100}};
  const auto& tail = target ? target_tail : source_tail;
  SequenceAdmissionFence fence{SequenceFenceKind::admission,
      foundation::CommandId{uuid("306")}, 11, 900, 0, source_pattern.id, 21,
      120, true, std::nullopt, SequenceSwitchOutcome::none, std::nullopt};
  if (step == "cutoff") {
    fence.kind = SequenceFenceKind::cutoff;
    fence.command_id = foundation::CommandId{uuid("307")};
    fence.transport_epoch = 12;
    fence.effective_frame = 2000;
    fence.pattern_id = pattern.id;
    fence.publication_generation = target ? 22 : 21;
    fence.origin_frame = target ? 1500 : 0;
  }
  const auto candidates = nlohmann::json::array({admission_codec::encode(press),
                                                 admission_codec::encode(release)});
  SequenceAdmissionTransfer transfer{
      foundation::CommandId{uuid(target ? "309" : "308")}, false,
      press.watermark, release.watermark,
      sha256_hex(foundation::canonical_json(candidates)),
      {{press.watermark, sha256_hex(foundation::canonical_json(candidates[0]))},
       {release.watermark, sha256_hex(foundation::canonical_json(candidates[1]))}},
      pattern.id, target ? 1U : 0U, target ? 3U : 2U, tail,
      {pattern.id, target ? 22U : 21U, release.runtime_frame, {}}};
  if (step == "terminal") {
    transfer.transfer_id = foundation::CommandId{uuid("310")};
    transfer.terminal = true;
    transfer.first_watermark = transfer.last_watermark = 0;
    transfer.candidates_sha256 = sha256_hex("[]");
    transfer.candidate_receipts.clear();
    transfer.journal_input_sequence.reset();
    transfer.checkpoint.last_runtime_frame = 2000;
  }
  if (step == "prepare") {
    auto state = value(domain::create_project(project, 120), "admission Project state");
    state.patterns.emplace(source_pattern.id, source_pattern);
    state.patterns.emplace(target_pattern.id, target_pattern);
    success(store.create(bundle, state), "admission Project create");
    success(journal.begin(bundle, session, source_pattern.id, 1,
        sequence_pattern_fingerprint(source_pattern), 0), "admission begin");
    if (query("seed") == "tail") {
      const std::vector<domain::PatternEvent> seed{source_tail.front()};
      success(journal.append_tail(bundle, session, source_pattern.id, 0, 1, seed),
              "admission preexisting canonical tail");
    }
  }

  // Fixture-local prewrite injection delegates to the existing storage-condition
  // fault helper. The real adapter still maps the thrown DOMException; no write
  // or durable success is synthesized. No production target links this wrapper.
  const bool inject = query("inject") == "1";
  if (inject) {
    EM_ASM({
      LmdjOpfsTest.admissionOriginalAppend = LmdjOpfs.appendDurable;
      LmdjOpfs.appendDurable = async function(...args) {
        const destination = this.canonicalPath(this.parts(args[0], args[1]));
        const point = await LmdjOpfsTest.faultForDestination(destination);
        await LmdjOpfsTest.throwStorageConditionFault(point);
        return LmdjOpfsTest.admissionOriginalAppend.apply(this, args);
      };
    });
  }
  const bool listing = step == "list" || step == "read-invalid-sealed";
  const auto before = listing ? std::vector<std::byte>{}
      : value(platform->read_complete(path), "admission before bytes");
  const int flush_before = lmdj_opfs_append_flush_count();
  auto mutation = Result<void>::success();
  report_progress(("admission-api-enter:" + step).c_str());
  if (step == "prepare") mutation = journal.prepare_admission(bundle, session, preparation);
  else if (step == "candidate" || step == "release") {
    mutation = journal.append_admission_candidate(bundle, session, identity,
        step == "candidate" ? press : release);
  } else if (step == "fence" || step == "cutoff") {
    mutation = journal.retain_admission_fence(bundle, session, identity, fence);
  } else if (step == "transfer" || step == "terminal") {
    mutation = journal.transfer_admission_prefix(bundle, session, identity, transfer);
  } else if (step == "close") {
    mutation = journal.close_admission(bundle, session, identity,
        {release.watermark, SequenceAdmissionCloseReason::requested});
  } else if (step == "boundary") {
    mutation = journal.retain_admission_switch(bundle, session, identity,
        {target_pattern.id, 22, 1500});
  } else if (step == "flush") {
    const foundation::CommandId command{uuid(target ? "312" : "311")};
    const auto flush = value(journal.append_flush(bundle, session, command,
        pattern.id, target ? 1U : 0U, tail), "admission append canonical flush");
    (void)value(store.execute_sequence_flush(bundle,
        {session, flush.flush_seq, command, pattern.id}), "admission commit canonical flush");
  } else if (step == "switch") {
    mutation = journal.switch_pattern(bundle, session, target_pattern.id, 1,
        sequence_pattern_fingerprint(target_pattern), 1);
  } else if (step == "complete") mutation = journal.complete_admission(bundle, session, identity);
  else if (step == "seal") {
    (void)value(journal.seal(bundle, session, "owner_lost"), "admission seal owner loss");
  } else if (step != "inspect" && !listing && step != "read-invalid") {
    throw std::runtime_error("unknown admission fixture step");
  }
  report_progress(("admission-api-returned:" + step).c_str());
  if (inject) {
    EM_ASM({
      LmdjOpfs.appendDurable = LmdjOpfsTest.admissionOriginalAppend;
      delete LmdjOpfsTest.admissionOriginalAppend;
    });
  }
  const int flush_after = lmdj_opfs_append_flush_count();
  nlohmann::json result{{"mutation", mutation_result(mutation)},
      {"flushBefore", flush_before}, {"flushAfter", flush_after}};
  if (step == "seal" || listing) {
    report_progress("admission-list-enter");
    const auto listed = journal.list_recoverable(bundle);
    report_progress("admission-list-returned");
    result["read"] = mutation_result(listed);
    require(listed.has_value() || step == "read-invalid-sealed", "admission recovery list failed");
    result["recoveries"] = nlohmann::json::array();
    if (listed.has_value()) for (const auto& recovery : listed.value()) {
      result["recoveries"].push_back({{"path", recovery.path.generic_string()},
          {"reason", recovery.reason}, {"journal", admission_summary(recovery.journal)}});
    }
  } else {
    const auto after = value(platform->read_complete(path), "admission after bytes");
    result["bytesUnchanged"] = before == after;
    result["journalSha256"] = sha256_hex(text(after));
    report_progress("admission-read-active-enter");
    const auto active = journal.read_active(bundle);
    report_progress("admission-read-active-returned");
    result["read"] = mutation_result(active);
    if (active.has_value()) result["journal"] = admission_summary(active.value());
    if (query("pause") == "1") {
      require(mutation.has_value() && active.has_value() && flush_after > flush_before,
              "response-loss barrier requires successful durable append and observed flush");
      const auto content = text(after);
      const auto previous_line = content.rfind('\n', content.size() - 2);
      const auto record = nlohmann::json::parse(content.substr(previous_line + 1));
      const auto marker = nlohmann::json{{"barrier", "admission-after-durable-before-response"},
          {"bundle", bundle.generic_string()}, {"step", step},
          {"session_id", session.value()}, {"identity", admission_codec::encode(identity)},
          {"record", record}, {"journalSha256", result["journalSha256"]},
          {"flushBefore", flush_before}, {"flushAfter", flush_after}}.dump();
      admission_response_barrier(marker.c_str());
    }
  }
  if (step == "flush" || step == "inspect") {
    const auto truth = value(store.inspect_committed(bundle), "admission committed truth");
    result["truth"] = {{"project_id", truth.id.value()}, {"revision", truth.revision},
        {"source_events", admission_events(truth.patterns.at(source_pattern.id).events)},
        {"target_events", admission_events(truth.patterns.at(target_pattern.id).events)}};
  }
  return nlohmann::json{{"complete", true}, {"result", result}};
}

// One occupied slot, the same canonical shape the native Set Store test
// builds, so a Web refusal cannot be blamed on a differently shaped manifest.
std::string soundset_manifest_bytes(const std::string& payload) {
  auto manifest = nlohmann::json::object();
  manifest["contract"] = "lmdj.soundset.v1";
  manifest["set_id"] = std::string{kSoundSetId};
  manifest["version"] = std::string{kSoundSetVersion};
  manifest["name"] = "Web Kit";
  manifest["publisher"] = "LMDJ";
  manifest["license"] = nlohmann::json{
      {"spdx_id", "CC-BY-4.0"},
      {"rights_holder", "Alice"},
      {"copyright", "Copyright 2026 Alice"},
      {"attribution", "Alice"},
  };
  auto slots = nlohmann::json::array();
  for (int index = 0; index < 16; ++index) {
    if (index != 0) {
      slots.push_back(nlohmann::json{{"slot", index}});
      continue;
    }
    slots.push_back(nlohmann::json{
        {"slot", index},
        {"role", "kick"},
        {"name", "Slot 0"},
        {"artifact",
         nlohmann::json{
             {"sha256", sha256_hex(payload)},
             {"media_type", "audio/wav"},
             {"byte_length", payload.size()},
         }},
    });
  }
  manifest["slots"] = std::move(slots);
  return lmdj::foundation::canonical_json(manifest);
}

// Serves exactly the objects it was given. There is no network here: this
// proof is about the storage half, so the Catalog half is a lookup table.
class WebCatalogTransport final : public lmdj::project_io::CatalogTransport {
 public:
  void publish(std::string object) {
    objects_.emplace(sha256_hex(object), std::move(object));
  }

  int reads() const { return reads_; }

  lmdj::foundation::Result<std::vector<std::byte>> read_object(
      const lmdj::project_io::CatalogObjectRef& object,
      std::uint64_t maximum_bytes) override {
    using ObjectResult = lmdj::foundation::Result<std::vector<std::byte>>;
    ++reads_;
    const auto found = objects_.find(object.sha256);
    // The refusal shape soundset_catalog_transport.hpp locks: an object that
    // cannot be resolved and one that is over the bound are the same fact.
    const auto unavailable = [](std::string message) {
      return ObjectResult::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::io_error,
              std::move(message),
              {{"reason",
                std::string{
                    lmdj::project_io::kSoundSetReasonCatalogUnavailable}}}});
    };
    if (found == objects_.end()) {
      return unavailable("web catalog fixture has no such object");
    }
    if (found->second.size() > maximum_bytes) {
      return unavailable("web catalog fixture object exceeds the bound");
    }
    const auto* begin =
        reinterpret_cast<const std::byte*>(found->second.data());
    return ObjectResult::success(
        std::vector<std::byte>{begin, begin + found->second.size()});
  }

 private:
  std::map<std::string, std::string> objects_;
  int reads_ = 0;
};

nlohmann::json soundset_store_publish(
    const std::shared_ptr<lmdj::project_io::ProjectStoragePlatform>& platform) {
  using namespace lmdj;
  const std::string payload = "RIFF-web-soundset-blob";
  const auto manifest = soundset_manifest_bytes(payload);
  const auto manifest_sha256 = sha256_hex(manifest);
  const auto blob_sha256 = sha256_hex(payload);
  WebCatalogTransport transport;
  transport.publish(manifest);
  transport.publish(payload);

  const auto workspace = std::filesystem::path{"/lmdj-workspace"};
  const auto sets_root = workspace / ".lmdj-host" / "soundsets";
  const auto staging_root = workspace / ".lmdj-host" / "soundset-staging";
  // A publication that ran to the end owns its own cleanup: the pending
  // intent that hides a half-built destination from enumeration must be gone.
  const auto publication_intent = workspace / ".lmdj-host" / "storage-intents" /
      sha256_hex(sets_root.generic_string() + "/" + manifest_sha256) /
      "directory-publication.json";
  project_io::SoundSetStore store{
      workspace,
      project_io::SoundSetStoreLimits{
          .maximum_soundset_manifest_bytes = 1u << 20,
          .maximum_soundset_blob_bytes = 1u << 20,
          .maximum_soundset_unique_bytes = 1u << 20,
          .maximum_soundset_staging_bytes = 1u << 22,
      },
      platform};
  const project_io::SoundSetCatalogEntry entry{
      std::string{kSoundSetId},
      std::string{kSoundSetVersion},
      manifest_sha256,
      manifest.size() + payload.size(),
      foundation::CatalogLicenseSummary{"CC-BY-4.0", "Alice"},
  };

  const auto acquired = store.acquire(transport, entry);
  const auto reads_after_acquire = transport.reads();
  const auto again = store.acquire(transport, entry);
  const auto reads_after_second = transport.reads();
  const auto listed = store.list();
  const auto artifact = store.read_artifact(manifest_sha256, blob_sha256);
  const auto staging_present =
      value(platform->directory_exists(staging_root), "staging root presence");

  return {
      {"acquire", mutation_result(acquired)},
      {"acquireTotalBytes",
       acquired.has_value() ? nlohmann::json(acquired.value().total_bytes)
                            : nlohmann::json(nullptr)},
      {"secondAcquire", mutation_result(again)},
      // A published Set answers from the store: the Catalog is untouched.
      {"catalogReadsAfterAcquire", reads_after_acquire},
      {"catalogReadsAfterSecondAcquire", reads_after_second},
      {"publishedSets",
       value(platform->directory_exists(sets_root), "Set Store root presence")
           ? nlohmann::json(
                 value(platform->list_directories(sets_root),
                       "Set Store inventory"))
           : nlohmann::json::array()},
      {"expectedManifestSha256", manifest_sha256},
      {"listedCount",
       listed.has_value() ? listed.value().size() : std::size_t{0}},
      {"listedSetId",
       listed.has_value() && !listed.value().empty()
           ? nlohmann::json(listed.value().front().manifest.set_id)
           : nlohmann::json(nullptr)},
      {"artifactBytes",
       artifact.has_value() ? nlohmann::json(text(artifact.value()))
                            : nlohmann::json(nullptr)},
      {"publicationIntentPresent",
       value(platform->exists(publication_intent), "publication intent")},
      {"stagingRootPresent", staging_present},
      {"stagingDirectories",
       staging_present
           ? nlohmann::json(
                 value(platform->list_directories(staging_root),
                       "staging inventory"))
           : nlohmann::json::array()},
  };
}

// The precondition `publish_directory_if_absent` declares, stated as a
// refusal: a lease on a covering ancestor is not a lease on the destination.
// Without this, the `lease.projectPath !== destinationPath` guard could be
// deleted and every suite would still pass, because every real call site
// happens to lease the exact destination.
nlohmann::json publication_lease_scope(
    const std::shared_ptr<lmdj::project_io::ProjectStoragePlatform>& platform) {
  const auto root =
      std::filesystem::path{"/lmdj-workspace/.lmdj-host/publication-scope"};
  const auto staging = root / "staging";
  const auto destination = root / "published";
  success(platform->ensure_directory(staging), "publication scope staging");
  auto ancestor = value(
      platform->acquire_writer(root), "publication scope ancestor lease");
  success(
      platform->create_immutable(staging / "payload.bin", bytes("scoped")),
      "publication scope payload");
  const auto refused =
      platform->publish_directory_if_absent(staging, destination);
  const bool destination_after = value(
      platform->directory_exists(destination),
      "publication scope destination after refusal");
  ancestor.reset();

  auto exact = value(
      platform->acquire_writer(destination), "publication scope exact lease");
  const auto admitted =
      platform->publish_directory_if_absent(staging, destination);
  exact.reset();
  return {
      {"ancestorLease", mutation_result(refused)},
      {"destinationAfterRefusal", destination_after},
      // The refusal must leave the staged bytes untouched, so the same
      // publication under the right lease is a real success and not a
      // republication of whatever the refused attempt left behind.
      {"exactLease", mutation_result(admitted)},
      {"stagingAfterPublish",
       value(
           platform->directory_exists(staging),
           "publication scope staging after publish")},
      {"publishedBytes",
       admitted.has_value()
           ? nlohmann::json(text(value(
                 platform->read_complete(destination / "payload.bin"),
                 "publication scope published payload")))
           : nlohmann::json(nullptr)},
  };
}

// A Project Bundle import driven end to end against real OPFS. Every other
// Project Bundle test runs on the native platform, so the commit's last step
// -- an OPFS directory publication under a writer lease on the destination --
// had no coverage at all, and "the commit acknowledged but no Project landed"
// was a claim about this platform that no run in the repository could answer.
// The report records what the Workspace actually holds after the receipt,
// rather than trusting the receipt.
void collect_bundle_entries(
    const lmdj::project_io::ProjectStoragePlatform& platform,
    const std::filesystem::path& root,
    const std::string& prefix,
    std::vector<std::pair<std::string, std::vector<std::byte>>>& out) {
  for (const auto& name :
       value(platform.list_names(root), "bundle fixture names")) {
    out.emplace_back(
        prefix + name,
        value(platform.read_complete(root / name), "bundle fixture bytes"));
  }
  for (const auto& directory :
       value(platform.list_directories(root), "bundle fixture directories")) {
    collect_bundle_entries(
        platform, root / directory, prefix + directory + "/", out);
  }
}

nlohmann::json project_bundle_import(
    const std::shared_ptr<lmdj::project_io::ProjectStoragePlatform>& platform,
    bool transfer_phase) {
  using namespace lmdj;
  const std::filesystem::path workspace{"/lmdj-workspace"};
  const auto project_id = uuid("977");
  const auto pattern_id = uuid("978");
  const auto import_token = uuid("979");
  const auto fixture_root = workspace / ".lmdj-host/import-fixture";
  const auto source = fixture_root / (project_id + ".lmdj");
  const auto projects_root = workspace / "projects";
  const auto destination = projects_root / (project_id + ".lmdj");

  project_io::ProjectBundleTransfer transfer{platform};
  std::optional<Result<project_io::LocalProjectSummary>> committed;
  if (transfer_phase) {
    project_io::ProjectStore store{platform};
    auto initial = value(
        domain::create_project(foundation::ProjectId{project_id}, 120),
        "bundle fixture Project state");
    success(store.create(source, initial), "bundle fixture Project create");
    const domain::CreatePattern create_pattern{
        domain::CommandMeta{foundation::CommandId{uuid("980")}, 0},
        domain::Pattern{foundation::PatternId{pattern_id}, 1, {}},
    };
    require(
        store.execute(source, domain::Command{create_pattern}).has_value(),
        "bundle fixture Pattern create");

    std::vector<std::pair<std::string, std::vector<std::byte>>> entries;
    collect_bundle_entries(*platform, source, "", entries);
    std::sort(
        entries.begin(),
        entries.end(),
        [](const auto& left, const auto& right) {
          return std::lexicographical_compare(
              left.first.begin(),
              left.first.end(),
              right.first.begin(),
              right.first.end(),
              [](char l, char r) {
                return static_cast<unsigned char>(l) <
                       static_cast<unsigned char>(r);
              });
        });
    const auto entry_text = [&](std::string_view relative) {
      const auto found = std::find_if(
          entries.begin(),
          entries.end(),
          [&](const auto& item) { return item.first == relative; });
      require(found != entries.end(), "bundle fixture entry is missing");
      return text(found->second);
    };
    const auto manifest = nlohmann::json::parse(entry_text("manifest.json"));
    const auto head = nlohmann::json::parse(
        entry_text(manifest.at("head_checkpoint").get<std::string>()));

    auto encoded_entries = nlohmann::json::array();
    std::uint64_t offset = 0;
    for (const auto& item : entries) {
      encoded_entries.push_back({
          {"bytes", item.second.size()},
          {"offset", offset},
          {"path", item.first},
          {"sha256", sha256_hex(text(item.second))},
      });
      offset += item.second.size();
    }
    nlohmann::json index{
        {"bundle_digest", std::string(64, '0')},
        {"compression", "none"},
        {"contract", "lmdj.project-bundle.v1"},
        {"contract_version", "1.2.0"},
        {"entries", std::move(encoded_entries)},
        {"project_contract", head.at("contract").get<std::string>()},
        {"project_id", project_id},
        {"uncompressed_bytes", offset},
    };
    auto digest_source = index;
    digest_source.erase("bundle_digest");
    index["bundle_digest"] =
        sha256_hex(foundation::canonical_json(digest_source));
    const auto encoded_index = foundation::canonical_json(index);

    const auto begun = transfer.begin(
        workspace,
        import_token,
        encoded_index.size(),
        sha256_hex(encoded_index));
    require(begun.has_value(), "Project Bundle import did not begin");
    const auto identity =
        transfer.append_index(import_token, 0, bytes(encoded_index), true);
    require(
        identity.has_value() && identity.value().has_value(),
        "Project Bundle index was not accepted");
    for (std::size_t entry_index = 0; entry_index < entries.size();
         ++entry_index) {
      const auto& payload = entries.at(entry_index).second;
      const auto appended = transfer.append_entry(
          import_token,
          static_cast<std::uint32_t>(entry_index),
          0,
          std::span<const std::byte>{payload.data(), payload.size()},
          true);
      require(appended.has_value(), "Project Bundle entry was not accepted");
    }
    committed = transfer.commit(import_token);
  }

  const bool projects_root_present = value(
      platform->directory_exists(projects_root), "Project root presence");
  const auto listed = transfer.list_local_projects(workspace);
  // The shape `project.open` takes: a writer lease on the published Project
  // path, then a load through the Project Store.
  auto reopen_lease = platform->acquire_writer(destination);
  project_io::ProjectStore reopen_store{platform};
  const auto reopened = reopen_store.load(destination);
  if (reopen_lease.has_value()) {
    reopen_lease.value().reset();
  }
  return {
      {"commit",
       committed.has_value()
           ? mutation_result(*committed)
           : nlohmann::json{{"status", "skipped"}, {"errorCode", ""},
                            {"storageCondition", ""}}},
      {"commitProjectId",
       committed.has_value() && committed->has_value()
           ? nlohmann::json(committed->value().project_id.value())
           : nlohmann::json(nullptr)},
      {"workspaceDirectories",
       value(platform->list_directories(workspace), "Workspace inventory")},
      {"projectsRootPresent", projects_root_present},
      {"projectsRootDirectories",
       projects_root_present
           ? nlohmann::json(value(
                 platform->list_directories(projects_root),
                 "Project root inventory"))
           : nlohmann::json::array()},
      {"destinationPresent",
       value(platform->directory_exists(destination), "destination presence")},
      {"destinationManifestPresent",
       value(
           platform->exists(destination / "manifest.json"),
           "destination manifest presence")},
      {"stagingPresent",
       value(
           platform->directory_exists(
               workspace / ".lmdj-host/import-staging" / import_token),
           "import staging presence")},
      {"listLocalProjects", mutation_result(listed)},
      {"listedProjectIds",
       [&]() {
         auto ids = nlohmann::json::array();
         if (listed.has_value()) {
           for (const auto& summary : listed.value()) {
             ids.push_back(summary.project_id.value());
           }
         }
         return ids;
       }()},
      {"reopenLease", mutation_result(reopen_lease)},
      {"reopen", mutation_result(reopened)},
      {"reopenProjectId",
       reopened.has_value() ? nlohmann::json(reopened.value().id.value())
                            : nlohmann::json(nullptr)},
      {"reopenPatternCount",
       reopened.has_value() ? nlohmann::json(reopened.value().patterns.size())
                            : nlohmann::json(nullptr)},
      {"storageIntents", storage_intent_inventory(*platform)},
  };
}

std::optional<nlohmann::json> run_soundset_store_action() {
  if (query("action") == "project_bundle_import") {
    auto platform = lmdj::project_io::make_web_project_storage_platform();
    require(platform != nullptr, "Web platform factory returned null");
    return nlohmann::json{
        {"complete", true},
        {"result", project_bundle_import(platform, query("phase") != "reopen")},
    };
  }
  if (query("action") == "publication_lease_scope") {
    auto platform = lmdj::project_io::make_web_project_storage_platform();
    require(platform != nullptr, "Web platform factory returned null");
    return nlohmann::json{
        {"complete", true},
        {"result", publication_lease_scope(platform)},
    };
  }
  if (query("action") != "soundset_store_publish") {
    return std::nullopt;
  }
  auto platform = lmdj::project_io::make_web_project_storage_platform();
  require(platform != nullptr, "Web platform factory returned null");
  return nlohmann::json{
      {"complete", true},
      {"result", soundset_store_publish(platform)},
  };
}

nlohmann::json run_suite() {
  using namespace lmdj;
  auto platform = project_io::make_web_project_storage_platform();
  require(platform != nullptr, "Web platform factory returned null");
  auto unavailable =
      project_io::make_web_project_storage_platform_for_test(false);
  require(unavailable != nullptr, "mount failure returned null platform");
  const auto require_mount_error = [](const auto& result, std::string operation) {
    require(
        !result.has_value() &&
            result.error().code == foundation::ErrorCode::io_error,
        "mount failure did not return typed storage error for " + operation);
  };
  const auto unavailable_path =
      std::filesystem::path{"/lmdj-workspace/unavailable"};
  require_mount_error(
      unavailable->acquire_writer(unavailable_path), "writer acquisition");
  require_mount_error(
      unavailable->ensure_directory(unavailable_path), "directory creation");
  require_mount_error(unavailable->exists(unavailable_path), "existence check");
  require_mount_error(
      unavailable->directory_exists(unavailable_path),
      "directory existence check");
  require_mount_error(
      unavailable->byte_length(unavailable_path), "length query");
  require_mount_error(
      unavailable->read_complete(unavailable_path), "complete read");
  require_mount_error(
      unavailable->create_immutable(unavailable_path, bytes("x")),
      "immutable creation");
  require_mount_error(
      unavailable->replace_complete(unavailable_path, bytes("x")),
      "complete replacement");
  require_mount_error(
      unavailable->append_durable(unavailable_path, 0, bytes("x")),
      "durable append");
  require_mount_error(unavailable->remove(unavailable_path), "removal");
  require_mount_error(
      unavailable->list_names(unavailable_path), "directory iteration");
  require_mount_error(
      unavailable->list_directories(unavailable_path),
      "directory iteration");
  require_mount_error(
      unavailable->remove_tree(unavailable_path), "recursive removal");
  require_mount_error(
      unavailable->publish_directory_if_absent(
          unavailable_path, unavailable_path / "published"),
      "atomic directory publish");
  require_mount_error(
      unavailable->validate_managed_tree(unavailable_path), "tree validation");

  const auto action = query("action");
  const auto requested_bundle = query("bundle");
  if (!action.empty()) {
    require(!requested_bundle.empty(), "fault bundle is missing");
    const auto fault_bundle = std::filesystem::path{"/lmdj-workspace"} /
        (requested_bundle + ".lmdj");
    if (action == "hold_lease") {
      auto acquired = platform->acquire_writer(fault_bundle);
      if (!acquired.has_value()) {
        return {
            {"complete", true},
            {"result",
             {{"lease", "failed"},
              {"errorCode", foundation::error_code_name(acquired.error().code)},
              {"storageCondition",
               acquired.error().details.value("storage_condition", "")}}},
        };
      }
      held_lease = std::move(acquired.value());
      return {{"complete", true}, {"result", {{"lease", "held"}}}};
    }

    if (action == "append_without_lease") {
      const auto append_path = fault_bundle / "append.bin";
      success(
          platform->ensure_directory(fault_bundle),
          "unleased append directory");
      auto seed_lease = value(
          platform->acquire_writer(fault_bundle), "unleased append seed lease");
      success(
          platform->create_immutable(append_path, bytes("seed")),
          "unleased append seed");
      seed_lease.reset();

      const auto appended =
          platform->append_durable(append_path, 4, bytes("mutated"));
      const auto post_call = value(
          platform->read_complete(append_path), "unleased append post-call read");
      return {
          {"complete", true},
          {"result",
           {{"append", appended.has_value() ? "succeeded" : "failed"},
            {"errorCode",
             appended.has_value()
                 ? ""
                 : foundation::error_code_name(appended.error().code)},
            {"storageCondition",
             appended.has_value()
                 ? ""
                 : appended.error().details.value("storage_condition", "")},
            {"length", post_call.size()},
            {"content", text(post_call)}}},
      };
    }

    if (action == "distinct_platform_mutation_ownership") {
      const auto existing_path = fault_bundle / "existing.bin";
      const auto absent_path = fault_bundle / "absent.bin";
      const auto publication_source = fault_bundle / "publication-source";
      const auto publication_destination = fault_bundle / "published";
      success(
          platform->ensure_directory(fault_bundle),
          "distinct platform ownership directory");
      auto owner_lease = value(
          platform->acquire_writer(fault_bundle),
          "distinct platform owner lease");
      success(platform->remove(existing_path), "ownership existing cleanup");
      success(platform->remove(absent_path), "ownership absent cleanup");
      success(
          platform->create_immutable(existing_path, bytes("seed")),
          "ownership existing seed");
      success(
          platform->ensure_directory(publication_source),
          "ownership publication source");
      success(
          platform->create_immutable(
              publication_source / "payload.bin", bytes("publication")),
          "ownership publication payload");
      auto publication_owner_lease = value(
          platform->acquire_writer(publication_destination),
          "ownership publication destination lease");

      const auto intent_inventory_before = storage_intent_inventory(*platform);
      const auto distinct_platform =
          project_io::make_web_project_storage_platform();
      const auto competing_acquisition =
          distinct_platform->acquire_writer(fault_bundle);
      const auto append = distinct_platform->append_durable(
          existing_path, 4, bytes("-append-bypass"));
      const auto after_append = value(
          platform->read_complete(existing_path),
          "ownership existing after append");
      const auto replace = distinct_platform->replace_complete(
          existing_path, bytes("replace-bypass"));
      const auto after_replace = value(
          platform->read_complete(existing_path),
          "ownership existing after replace");
      const auto create = distinct_platform->create_immutable(
          absent_path, bytes("create-bypass"));
      const auto existing_create = distinct_platform->create_immutable(
          existing_path, bytes("existing-bypass"));
      const auto publish = distinct_platform->publish_directory_if_absent(
          publication_source, publication_destination);
      const bool absent_after_create = !value(
          platform->exists(absent_path), "ownership absent after create");
      const bool publication_source_after = value(
          platform->directory_exists(publication_source),
          "ownership publication source after publish");
      const bool publication_destination_after = value(
          platform->directory_exists(publication_destination),
          "ownership publication destination after publish");
      const auto intent_inventory_after = storage_intent_inventory(*platform);

      const auto before_owner_mutation = value(
          platform->read_complete(existing_path),
          "ownership existing before owner mutation");
      success(
          platform->append_durable(
              existing_path, before_owner_mutation.size(), bytes("-owner")),
          "ownership owner append");
      const auto owner_content = text(value(
          platform->read_complete(existing_path),
          "ownership existing after owner mutation"));
      owner_lease.reset();
      auto post_release_lease = value(
          distinct_platform->acquire_writer(fault_bundle),
          "ownership distinct acquisition after release");
      post_release_lease.reset();

      return {
          {"complete", true},
          {"result",
           {{"acquisition", mutation_result(competing_acquisition)},
            {"append", mutation_result(append)},
            {"replace", mutation_result(replace)},
            {"create", mutation_result(create)},
            {"existingCreate", mutation_result(existing_create)},
            {"publish", mutation_result(publish)},
            {"afterAppend",
             {{"length", after_append.size()},
              {"content", text(after_append)}}},
            {"afterReplace",
             {{"length", after_replace.size()},
              {"content", text(after_replace)}}},
            {"absentAfterCreate", absent_after_create},
            {"publicationSourceAfter", publication_source_after},
            {"publicationDestinationAfter", publication_destination_after},
            {"intentEntriesBefore", intent_inventory_before.size()},
            {"intentEntriesAfter", intent_inventory_after.size()},
            {"intentInventoryUnchanged",
             intent_inventory_before == intent_inventory_after},
            {"ownerContent", owner_content},
            {"postReleaseAcquisition", "pass"}}},
      };
    }

    const auto replacement_path = fault_bundle / "replacement.bin";
    const auto immutable_path = fault_bundle / "immutable.bin";
    const auto publication_source =
        std::filesystem::path{"/lmdj-workspace/.lmdj-host/publication-fixtures"} /
        requested_bundle;
    const auto scenario = query("scenario");
    if (action == "storage_condition_failure") {
      success(
          platform->ensure_directory(fault_bundle),
          "storage condition directory");
      auto lease = value(
          platform->acquire_writer(fault_bundle), "storage condition lease");
      const auto write =
          platform->replace_complete(replacement_path, bytes("condition"));
      if (write.has_value()) {
        return {
            {"complete", true},
            {"result", {{"storage", "unexpected-success"}}},
        };
      }
      return {
          {"complete", true},
          {"result",
           {{"storage", "failed"},
            {"errorCode", foundation::error_code_name(write.error().code)},
            {"storageCondition",
             write.error().details.value("storage_condition", "")}}},
      };
    }
    if (action == "publish_publication") {
      auto lease = value(
          platform->acquire_writer(fault_bundle),
          "publication destination lease");
      success(
          platform->publish_directory_if_absent(
              publication_source, fault_bundle),
          "publication fault write");
      return {
          {"complete", true},
          {"result",
           {{"state", "published"},
            {"maxChunkBytes", lmdj_opfs_publication_max_chunk_bytes()}}},
      };
    }
    if (action == "publish_publication_failure") {
      auto lease = value(
          platform->acquire_writer(fault_bundle),
          "publication failure destination lease");
      const auto publish = platform->publish_directory_if_absent(
          publication_source, fault_bundle);
      if (publish.has_value()) {
        return {
            {"complete", true},
            {"result", {{"publish", "unexpected-success"}}},
        };
      }
      return {
          {"complete", true},
          {"result",
           {{"publish", "failed"},
            {"errorCode",
             foundation::error_code_name(publish.error().code)}}},
      };
    }
    if (action == "acquire_after_intent") {
      auto acquire = platform->acquire_writer(fault_bundle);
      if (!acquire.has_value()) {
        return {
            {"complete", true},
            {"result",
             {{"acquire", "failed"},
              {"errorCode",
               foundation::error_code_name(acquire.error().code)}}},
        };
      }
      auto lease = std::move(acquire.value());
      return {
          {"complete", true},
          {"result",
           {{"acquire", "ok"},
            {"content", text(value(
                 platform->read_complete(replacement_path),
                 "recovered replacement content"))}}},
      };
    }
    if (action == "inspect_publication" ||
        action == "recover_publication" ||
        action == "recover_and_publish") {
      std::unique_ptr<project_io::ProjectWriterLease> lease;
      if (action != "inspect_publication") {
        lease = value(
            platform->acquire_writer(fault_bundle),
            "publication recovery lease");
        if (action == "recover_and_publish" &&
            !value(
                platform->directory_exists(fault_bundle),
                "publication retry destination")) {
          success(
              platform->publish_directory_if_absent(
                  publication_source, fault_bundle),
              "publication retry");
        }
      }
      const auto workspace = std::filesystem::path{"/lmdj-workspace"};
      const auto names = value(
          platform->list_directories(workspace),
          "publication inventory");
      const bool visible =
          std::find(
              names.begin(), names.end(), fault_bundle.filename().string()) !=
          names.end();
      const bool physical = value(
          platform->directory_exists(fault_bundle),
          "publication physical destination");
      bool complete = false;
      if (physical) {
        const auto payload = fault_bundle / "nested/payload.bin";
        complete = value(
            platform->exists(payload), "publication payload exists");
        if (complete) {
          const auto length = value(
              platform->byte_length(payload), "publication payload length");
          complete = length == 1048593U;
        }
      }
      return {
          {"complete", true},
          {"result",
           {{"visible", visible},
            {"physical", physical},
            {"complete", complete},
            {"source", value(
                 platform->directory_exists(publication_source),
                 "publication source")}}},
      };
    }
    if (action == "prepare_replacement") {
      success(platform->ensure_directory(fault_bundle), "replacement directory");
      auto lease = value(
          platform->acquire_writer(fault_bundle), "replacement prepare lease");
      success(platform->remove(replacement_path), "replacement cleanup");
      if (scenario == "existing") {
        success(platform->replace_complete(replacement_path, bytes("old")),
                "existing replacement seed");
      } else {
        require(scenario == "absent", "replacement scenario is invalid");
      }
      return {{"complete", true}, {"result", {{"state", scenario}}}};
    }
    if (action == "replace") {
      auto lease = value(
          platform->acquire_writer(fault_bundle), "replacement fault lease");
      success(platform->replace_complete(replacement_path, bytes("new")),
              "replacement fault write");
      return {{"complete", true}, {"result", {{"state", "new"}}}};
    }
    if (action == "reopen_replacement" || action == "recover") {
      auto acquired = platform->acquire_writer(fault_bundle);
      if (!acquired.has_value()) {
        return {
            {"complete", true},
            {"result",
             {{"recovery", "failed"},
              {"errorCode", foundation::error_code_name(acquired.error().code)},
              {"storageCondition",
               acquired.error().details.value("storage_condition", "")}}},
        };
      }
      if (action == "recover") {
        return {{"complete", true}, {"result", {{"recovery", "pass"}}}};
      }
      const bool present = value(
          platform->exists(replacement_path), "replacement reopen exists");
      const std::string state = present
          ? text(value(
                platform->read_complete(replacement_path),
                "replacement reopen read"))
          : "absent";
      return {{"complete", true}, {"result", {{"state", state}}}};
    }
    if (action == "prepare_immutable") {
      success(platform->ensure_directory(fault_bundle), "immutable directory");
      auto lease = value(
          platform->acquire_writer(fault_bundle), "immutable prepare lease");
      success(platform->remove(immutable_path), "immutable cleanup");
      return {{"complete", true}, {"result", {{"state", "absent"}}}};
    }
    if (action == "create_immutable_fault") {
      auto lease = value(
          platform->acquire_writer(fault_bundle), "immutable fault lease");
      success(
          platform->create_immutable(
              immutable_path, bytes("immutable-partial")),
          "immutable fault write");
      return {{"complete", true}, {"result", {{"state", "created"}}}};
    }
    if (action == "reopen_immutable") {
      auto lease = value(
          platform->acquire_writer(fault_bundle), "immutable recovery lease");
      require(
          !value(platform->exists(immutable_path), "immutable recovery exists"),
          "partial immutable survived recovery");
      success(
          platform->create_immutable(
              immutable_path, bytes("immutable-retry")),
          "immutable retry");
      return {
          {"complete", true},
          {"result",
           {{"state",
             text(value(
                 platform->read_complete(immutable_path),
                 "immutable retry read"))}}},
      };
    }

    project_io::ProjectStore fault_store{platform};
    if (action == "prepare") {
      const auto present = value(platform->exists(fault_bundle / "manifest.json"), "fault exists");
      if (!present) {
        auto initial = value(domain::create_project(
            foundation::ProjectId{uuid("11")}, 120), "fault create state");
        success(fault_store.create(fault_bundle, initial), "fault prepare");
      }
    } else if (action == "advance") {
      const auto current = value(fault_store.load(fault_bundle), "fault advance load");
      domain::CreatePattern command{
          domain::CommandMeta{foundation::CommandId{uuid("12")}, current.revision},
          domain::Pattern{foundation::PatternId{uuid("13")}, 1,
                          {domain::PatternEvent{
                              domain::PadSlotId{0, 0},
                              0,
                              domain::kSixteenthTicks,
                              100}}}};
      (void)value(fault_store.execute(fault_bundle, domain::Command{command}),
                  "fault advance execute");
    } else if (action == "reopen") {
      auto recovery_lease = value(
          platform->acquire_writer(fault_bundle), "fault recovery lease");
      recovery_lease.reset();
    } else {
      throw std::runtime_error("unknown fault action");
    }
    const auto reopened = value(fault_store.load(fault_bundle), "fault common reopen");
    return {{"complete", true}, {"result", {{"revision", reopened.revision},
                                             {"bundle", requested_bundle}}}};
  }

  const auto sequence = std::chrono::steady_clock::now().time_since_epoch().count();
  const auto bundle = std::filesystem::path{"/lmdj-workspace"} /
      ("parity-" + std::to_string(sequence) + ".lmdj");

  report_progress("lease-parity-start");
  auto outer_lease = value(platform->acquire_writer(bundle), "outer lease");
  auto nested_lease = value(
      platform->acquire_writer(bundle / ".." / bundle.filename()),
      "equivalent nested lease");
  const auto distinct_platform =
      project_io::make_web_project_storage_platform();
  const auto competing_same_page = distinct_platform->acquire_writer(bundle);
  require(
      !competing_same_page.has_value() &&
          competing_same_page.error().details.value("storage_condition", "") ==
              project_io::kStorageConditionProjectBusy,
      "distinct platform inherited a same-page writer lease");
  outer_lease.reset();
  const auto competing_while_nested =
      distinct_platform->acquire_writer(bundle);
  require(
      !competing_while_nested.has_value() &&
          competing_while_nested.error().details.value(
              "storage_condition", "") ==
              project_io::kStorageConditionProjectBusy,
      "outer release dropped the nested writer reference");
  nested_lease.reset();
  auto distinct_lease = value(
      distinct_platform->acquire_writer(bundle),
      "distinct platform acquisition after final release");
  distinct_lease.reset();
  report_progress("lease-parity-complete");

  report_progress("project-store-start");
  project_io::ProjectStore store{platform};
  auto initial = value(domain::create_project(
      foundation::ProjectId{uuid("1")}, 120), "create project state");
  success(store.create(bundle, initial), "ProjectStore create");
  report_progress("project-store-created");
  const auto loaded = value(store.load(bundle), "ProjectStore initial load");
  require(loaded == initial, "ProjectStore initial parity");
  report_progress("project-store-loaded");

  report_progress("project-store-complete");

  report_progress("sequence-journal-start");
  project_io::SequenceJournal journal{platform};
  const foundation::SequenceSessionId session_id{uuid("4")};
  const foundation::PatternId recorded_pattern_id{uuid("5")};
  success(
      journal.begin(
          bundle,
          session_id,
          recorded_pattern_id,
          1,
          std::string(64, 'a'),
          0),
      "SequenceJournal begin");
  const std::array events{
      domain::PatternEvent{domain::PadSlotId{0, 0}, 240, 120, 101},
  };
  const auto first_flush = value(
      journal.append_flush(
          bundle,
          session_id,
          foundation::CommandId{uuid("6")},
          recorded_pattern_id,
          0,
          events),
      "SequenceJournal append");
  require(first_flush.flush_seq == 0, "SequenceJournal flush sequence");
  const auto active = value(journal.read_active(bundle), "SequenceJournal read");
  require(active.flushes.size() == 1 &&
              active.flushes.front().canonical_events ==
                  std::vector<domain::PatternEvent>(events.begin(), events.end()),
          "SequenceJournal parity");
  report_progress("sequence-journal-initial-complete");

  // The Web storage adapter is invoked on the Host's single Control thread.
  // Exercise distinct Web journal owners without nesting Asyncify-backed OPFS
  // calls in child pthreads, which is not a production call shape.
  report_progress("multi-owner-append-start");
  project_io::SequenceJournal second_owner{platform};
  project_io::SequenceJournal third_owner{platform};
  const std::array second_events{
      domain::PatternEvent{domain::PadSlotId{0, 0}, 240, 120, 101},
      domain::PatternEvent{domain::PadSlotId{0, 1}, 480, 120, 90},
  };
  const std::array third_events{
      domain::PatternEvent{domain::PadSlotId{0, 0}, 240, 120, 101},
      domain::PatternEvent{domain::PadSlotId{0, 1}, 480, 120, 90},
      domain::PatternEvent{domain::PadSlotId{0, 2}, 720, 120, 91},
  };
  success(
      second_owner.append_tail(
          bundle,
          session_id,
          recorded_pattern_id,
          0,
          1,
          second_events),
      "second-owner SequenceJournal tail");
  value(
      second_owner.append_flush(
          bundle,
          session_id,
          foundation::CommandId{uuid("7")},
          recorded_pattern_id,
          0,
          second_events),
      "second-owner SequenceJournal append");
  success(
      third_owner.append_tail(
          bundle,
          session_id,
          recorded_pattern_id,
          0,
          2,
          third_events),
      "third-owner SequenceJournal tail");
  value(
      third_owner.append_flush(
          bundle,
          session_id,
          foundation::CommandId{uuid("8")},
          recorded_pattern_id,
          0,
          third_events),
      "third-owner SequenceJournal append");
  require(
      value(journal.read_active(bundle), "multi-owner read").flushes.size() == 3,
      "multi-owner append lost acknowledgement");
  report_progress("multi-owner-append-complete");

  const auto contract = bundle / "contract";
  auto contract_lease = value(
      platform->acquire_writer(bundle), "contract writer lease");
  success(platform->ensure_directory(contract), "contract directory");
  require(
      value(platform->directory_exists(contract), "existing directory probe"),
      "existing directory was not recognized");
  require(
      !value(
          platform->directory_exists(contract / "missing"),
          "missing directory probe"),
      "missing directory was recognized");
  success(platform->remove(contract / "missing.bin"), "missing remove");
  success(platform->remove(contract / "missing.bin"), "idempotent missing remove");
  const auto bridge_file = contract / "bridge-visible.bin";
  const int immutable_writes = lmdj_opfs_immutable_write_count();
  success(platform->create_immutable(bridge_file, bytes("bridge")), "bridge coherence seed");
  require(
      !value(platform->directory_exists(bridge_file), "regular file probe"),
      "regular file was recognized as a directory");
  require(
      lmdj_opfs_immutable_write_count() >= immutable_writes + 3,
      "immutable creation did not loop over short writes");
  std::ifstream mounted_read{bridge_file, std::ios::binary};
  require(std::string{std::istreambuf_iterator<char>{mounted_read}, {}} == "bridge",
          "platform write is not visible through WasmFS mount");
  const auto mounted_file = contract / "mount-visible.bin";
  {
    std::ofstream mounted_write{mounted_file, std::ios::binary | std::ios::trunc};
    mounted_write << "mount";
    require(mounted_write.good(), "WasmFS mount write failed");
  }
  require(text(value(platform->read_complete(mounted_file), "mount coherence read")) == "mount",
          "WasmFS write is not visible through platform bridge");
  const auto append_path = contract / "append.bin";
  success(platform->create_immutable(append_path, bytes("abc")), "append seed");
  int flushes = lmdj_opfs_append_flush_count();
  success(platform->append_durable(append_path, 3, bytes("d")), "clean append");
  require(lmdj_opfs_append_flush_count() == flushes + 1, "clean append flush count");
  flushes += 1;
  require(text(value(platform->read_complete(append_path), "read clean")) == "abcd",
          "clean-prefix append");
  success(platform->append_durable(append_path, 2, bytes("XY")), "torn repair");
  require(lmdj_opfs_append_flush_count() == flushes + 1, "repair flush count");
  flushes += 1;
  require(text(value(platform->read_complete(append_path), "read repaired")) == "abXY",
          "torn-tail repair");
  const std::array<std::byte, 3> binary{std::byte{0}, std::byte{0xff}, std::byte{10}};
  success(platform->append_durable(append_path, 4, binary), "binary append");
  require(lmdj_opfs_append_flush_count() == flushes + 1, "binary flush count");
  flushes += 1;
  const auto before_oversized = value(platform->read_complete(append_path), "pre oversized");
  require(!platform->append_durable(append_path, 999, bytes("bad")).has_value(),
          "oversized prefix accepted");
  require(lmdj_opfs_append_flush_count() == flushes, "oversized prefix flushed");
  require(value(platform->read_complete(append_path), "post oversized") == before_oversized,
          "oversized prefix mutated file");
  report_progress("storage-contract-append-complete");

  const auto replacement = contract / "replacement.bin";
  success(platform->replace_complete(replacement, bytes("old")), "old replacement");
  success(platform->replace_complete(replacement, bytes("new")), "new replacement");
  require(text(value(platform->read_complete(replacement), "replacement read")) == "new",
          "complete replacement");

  success(platform->create_immutable(contract / "z", bytes("")), "sort z");
  success(platform->create_immutable(contract / "a", bytes("")), "sort a");
  success(platform->create_immutable(contract / "\xc3\xa9", bytes("")), "sort utf8");
  const auto names = value(platform->list_names(contract), "sorted iteration");
  const auto a = std::find(names.begin(), names.end(), "a");
  const auto z = std::find(names.begin(), names.end(), "z");
  const auto accented = std::find(names.begin(), names.end(), "\xc3\xa9");
  require(a < z && z < accented, "unsigned UTF-8 sorting");

  const auto staging = contract / "staging-directory";
  const auto published = contract / "published-directory";
  success(platform->ensure_directory(staging / "nested"), "staging directory");
  success(
      platform->create_immutable(staging / "nested/payload.bin", bytes("complete")),
      "staging payload");
  auto publication_lease = value(
      platform->acquire_writer(published),
      "published destination lease");
  const auto publish =
      platform->publish_directory_if_absent(staging, published);
  std::string directory_transfer;
  if (!publish.has_value()) {
    throw std::runtime_error("directory publish failed");
  } else {
    require(!value(platform->directory_exists(staging), "staging moved"),
            "staging remained visible after publish");
    require(value(platform->directory_exists(published), "published exists"),
            "published directory is missing");
    require(
        text(value(
            platform->read_complete(published / "nested/payload.bin"),
            "published payload")) == "complete",
        "published payload changed");
    const auto directory_names =
        value(platform->list_directories(contract), "directory listing");
    require(
        std::find(directory_names.begin(), directory_names.end(),
                  "published-directory") != directory_names.end(),
        "published directory was not listed");
    const auto collision_staging = contract / "collision-staging";
    success(platform->ensure_directory(collision_staging), "collision staging");
    const auto collision = platform->publish_directory_if_absent(
        collision_staging, published);
    require(
        !collision.has_value() &&
            collision.error().details.value("storage_condition", "") ==
                project_io::kStorageConditionAlreadyExists,
        "directory publish overwrote an existing destination");
    success(platform->remove_tree(published), "recursive published removal");
    success(platform->remove_tree(published), "idempotent recursive removal");
    success(
        platform->remove_tree(collision_staging),
        "collision staging removal");
    directory_transfer = "pass";
  }
  report_progress("directory-publication-complete");
  publication_lease.reset();

  contract_lease.reset();

  report_progress("common-suite-complete");
  return {
      {"complete", true},
      {"result", {
          {"projectStore", "pass"}, {"sequenceJournal", "pass"},
          {"replay", "pass"}, {"recovery", "pass"},
          {"appendContracts", "pass"}, {"lease", "pass"},
          {"mountFailure", "pass"}, {"idempotentRemove", "pass"},
          {"immutableShortWrites", "pass"},
          {"directoryTransfer", directory_transfer},
          {"directoryBarrier", "absent"},
          {"replacementFaultPoints", {"before_write", "during_write", "before_close",
                                        "after_close", "before_cleanup"}},
          {"publicationFaultPoints",
           {"before_intent_write", "during_intent_write",
            "after_pending_intent", "during_directory_copy",
            "after_directory_copy", "during_directory_verify",
            "before_commit_close", "after_commit_close",
            "before_source_cleanup", "before_intent_cleanup"}}
      }}
  };
}

}  // namespace

int main() {
  nlohmann::json report;
  try {
    report_progress("native-suite-start");
    auto action = run_admission_action();
    if (!action.has_value()) {
      action = run_soundset_store_action();
    }
    if (!action.has_value()) {
      action = run_sample_cache_action();
    }
    report = action.has_value() ? std::move(*action) : run_suite();
    report_progress("native-report-ready");
  } catch (const std::exception& error) {
    report = {{"complete", true}, {"result", {{"error", error.what()}}}};
  }
  const std::string encoded = report.dump();
  report_progress("terminal-publication-start");
  MAIN_THREAD_EM_ASM({ window.lmdjProjectIoWeb = JSON.parse(UTF8ToString($0)); },
                     encoded.c_str());
  emscripten_exit_with_live_runtime();
  return 0;
}
