#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

#include <emscripten.h>
#include <nlohmann/json.hpp>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/project_io/take_journal.hpp>
#include <lmdj/project_io/workspace_cache.hpp>

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
      initial.contract == domain::ProjectContract::v1,
      "Sample Web Project did not start as v1");
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
      {"contract", "lmdj.project.v1"},
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
      imported.state.contract == domain::ProjectContract::v2 &&
          imported.state.revision == 1,
      "Sample import did not commit one v2 revision");
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
      {"contract", "lmdj.project.v2"},
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
      reopened.contract == domain::ProjectContract::v2 &&
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
      {"contract", "lmdj.project.v2"},
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
      return {{"complete", true}, {"result", {{"state", "published"}}}};
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
                          {domain::PatternEvent{domain::PadSlotId{0, 0}, 0, 100}}}};
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

  project_io::ProjectStore store{platform};
  auto initial = value(domain::create_project(
      foundation::ProjectId{uuid("1")}, 120), "create project state");
  success(store.create(bundle, initial), "ProjectStore create");
  const auto loaded = value(store.load(bundle), "ProjectStore initial load");
  require(loaded == initial, "ProjectStore initial parity");

  domain::CreatePattern command{
      domain::CommandMeta{foundation::CommandId{uuid("2")}, 0},
      domain::Pattern{
          foundation::PatternId{uuid("3")}, 1,
          {domain::PatternEvent{domain::PadSlotId{0, 0}, 0, 100}}}};
  const auto applied = value(store.execute(bundle, domain::Command{command}),
                             "ProjectStore execute");
  require(applied.state.revision == 1, "ProjectStore transaction revision");
  require(value(store.load(bundle), "ProjectStore replay load").revision == 1,
          "ProjectStore replay revision");

  project_io::TakeJournal journal{platform};
  const foundation::TakeId take_id{uuid("4")};
  success(journal.begin(bundle, take_id, 1, 48000), "TakeJournal begin");
  success(journal.append(
      bundle, take_id, domain::RawTakeEvent{domain::PadSlotId{0, 0}, 12, 101}),
      "TakeJournal append");
  const auto active = value(journal.read_active(bundle, take_id), "TakeJournal read");
  require(active.events.size() == 1 && active.events.front().frame_offset == 12,
          "TakeJournal parity");

  // The Web storage adapter is invoked on the Host's single Control thread;
  // native stress tests own true multi-threaded TakeJournal coverage. Exercise
  // distinct Web Journal owners without nesting Asyncify-backed OPFS calls in
  // child pthreads, which is not a production call shape.
  report_progress("multi-owner-append-start");
  project_io::TakeJournal second_owner{platform};
  project_io::TakeJournal third_owner{platform};
  success(second_owner.append(
      bundle, take_id,
      domain::RawTakeEvent{domain::PadSlotId{0, 1}, 20, 90}),
      "second-owner TakeJournal append");
  success(third_owner.append(
      bundle, take_id,
      domain::RawTakeEvent{domain::PadSlotId{0, 2}, 20, 91}),
      "third-owner TakeJournal append");
  require(
      value(journal.read_active(bundle, take_id), "multi-owner read")
              .events.size() == 3,
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
  const std::string large_payload(1048593U, 'x');
  success(
      platform->create_immutable(
          staging / "nested/large.bin", bytes(large_payload)),
      "large staging payload");
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
    require(
        value(
            platform->byte_length(published / "nested/large.bin"),
            "published large payload") == large_payload.size(),
        "published large payload changed");
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
  publication_lease.reset();

  contract_lease.reset();

  report_progress("common-suite-complete");
  return {
      {"complete", true},
      {"result", {
          {"projectStore", "pass"}, {"takeJournal", "pass"},
          {"replay", "pass"}, {"recovery", "pass"},
          {"appendContracts", "pass"}, {"lease", "pass"},
          {"mountFailure", "pass"}, {"idempotentRemove", "pass"},
          {"immutableShortWrites", "pass"},
          {"directoryTransfer", directory_transfer},
          {"directoryBarrier", "absent"},
          {"publicationMaxChunkBytes",
           lmdj_opfs_publication_max_chunk_bytes()},
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
    auto sample_cache = run_sample_cache_action();
    report = sample_cache.has_value() ? std::move(*sample_cache) : run_suite();
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
