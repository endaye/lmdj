#include <array>
#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <iterator>
#include <map>
#include <string>
#include <string_view>
#include <utility>

#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>

#include <nlohmann/json.hpp>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_store.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CreatePattern;
using lmdj::domain::Asset;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::RawTake;
using lmdj::domain::RawTakeEvent;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::project_io::ProjectStore;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-project-io-test-" + std::to_string(nonce));
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

void write_bytes(const std::filesystem::path& path, std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  if (!stream) {
    throw std::runtime_error("failed to write test fixture");
  }
}

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("failed to read test file");
  }
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

nlohmann::json read_json(const std::filesystem::path& path) {
  return nlohmann::json::parse(read_bytes(path));
}

std::size_t regular_file_count(const std::filesystem::path& directory) {
  std::size_t count = 0;
  for (const auto& entry : std::filesystem::directory_iterator(directory)) {
    if (entry.is_regular_file()) {
      ++count;
    }
  }
  return count;
}

std::map<std::string, std::string> managed_bundle_snapshot(
    const std::filesystem::path& bundle) {
  std::map<std::string, std::string> snapshot;
  const std::array roots{
      bundle / "manifest.json",
      bundle / "assets",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
  };
  for (const auto& root : roots) {
    if (std::filesystem::is_regular_file(root)) {
      snapshot.emplace(
          std::filesystem::relative(root, bundle).generic_string(),
          read_bytes(root));
      continue;
    }
    for (const auto& entry :
         std::filesystem::recursive_directory_iterator(root)) {
      if (entry.is_regular_file()) {
        snapshot.emplace(
            std::filesystem::relative(entry.path(), bundle).generic_string(),
            read_bytes(entry.path()));
      }
    }
  }
  return snapshot;
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

lmdj::domain::ProjectState new_project() {
  const auto result =
      lmdj::domain::create_project(ProjectId{test_uuid("project-1")}, 120);
  LMDJ_CHECK(result.has_value());
  return result.value();
}

CommandMeta meta(std::string id, std::uint64_t revision) {
  return CommandMeta{CommandId{test_uuid(id)}, revision};
}

CreatePattern create_pattern(
    std::string command_id,
    std::uint64_t revision,
    std::string pattern_id,
    std::uint32_t step = 0) {
  return CreatePattern{
      meta(std::move(command_id), revision),
      Pattern{
          PatternId{test_uuid(pattern_id)},
          1,
          {PatternEvent{PadSlotId{0, 0}, step, 100}},
      },
  };
}

Pattern decode_pattern(const nlohmann::json& input) {
  Pattern pattern{
      PatternId{input.at("id").get<std::string>()},
      input.at("bars").get<std::uint8_t>(),
      {},
  };
  for (const auto& encoded : input.at("events")) {
    const auto& slot = encoded.at("slot");
    pattern.events.push_back(
        PatternEvent{
            PadSlotId{
                slot.at("bank").get<std::uint8_t>(),
                slot.at("pad").get<std::uint8_t>(),
            },
            encoded.at("step").get<std::uint32_t>(),
            encoded.at("velocity").get<std::uint8_t>(),
        });
  }
  return pattern;
}

Command decode_create_pattern(const nlohmann::json& input) {
  LMDJ_CHECK(input.at("type") == "CreatePattern");
  const auto& encoded_meta = input.at("meta");
  return Command{CreatePattern{
      CommandMeta{
          CommandId{encoded_meta.at("command_id").get<std::string>()},
          encoded_meta.at("expected_revision").get<std::uint64_t>(),
      },
      decode_pattern(input.at("pattern")),
  }};
}

void test_canonical_checkpoint_round_trip_and_bundle_shape() {
  TempDirectory temp;
  const auto first_bundle = temp.path() / "beat-proof.lmdj";
  const auto second_bundle = temp.path() / "round-trip.lmdj";
  const auto source = temp.path() / "source.wav";
  write_bytes(source, "RIFF-contract-test");
  const auto described =
      lmdj::foundation::describe_artifact(source, "audio/wav");
  LMDJ_CHECK(described.has_value());
  auto initial = new_project();
  const auto asset_id = AssetId{test_uuid("asset-1")};
  const auto take_id = lmdj::foundation::TakeId{test_uuid("take-1")};
  const auto pattern_id = PatternId{test_uuid("pattern-1")};
  initial.assets.emplace(
      asset_id, Asset{asset_id, described.value()});
  initial.banks.at(0).at(0).asset_id = asset_id;
  initial.takes.emplace(
      take_id,
      RawTake{
          take_id,
          48000,
          {RawTakeEvent{PadSlotId{0, 0}, 1234, 100}},
      });
  initial.patterns.emplace(
      pattern_id,
      Pattern{
          pattern_id,
          1,
          {PatternEvent{PadSlotId{0, 0}, 0, 100}},
      });
  ProjectStore store;

  const auto created = store.create(first_bundle, initial);
  LMDJ_CHECK(created.has_value());
  LMDJ_CHECK(std::filesystem::is_regular_file(first_bundle / "manifest.json"));
  LMDJ_CHECK(std::filesystem::is_regular_file(
      first_bundle / "history/checkpoints/0.json"));
  LMDJ_CHECK(std::filesystem::is_directory(first_bundle / "assets"));
  LMDJ_CHECK(std::filesystem::is_directory(
      first_bundle / "history/transactions"));
  LMDJ_CHECK(std::filesystem::is_directory(
      first_bundle / "recovery/active"));
  LMDJ_CHECK(std::filesystem::is_directory(
      first_bundle / "recovery/sealed"));
  const auto checkpoint_path =
      first_bundle / "history/checkpoints/0.json";
  const auto checkpoint_bytes = read_bytes(checkpoint_path);
  const auto checkpoint = nlohmann::json::parse(checkpoint_bytes);
  LMDJ_CHECK(
      checkpoint_bytes ==
      lmdj::foundation::canonical_json(checkpoint) + "\n");
  LMDJ_CHECK(checkpoint.size() == 8);
  LMDJ_CHECK(checkpoint.at("contract") == "lmdj.project.v1");
  LMDJ_CHECK(
      checkpoint.at("project_id") == initial.id.value());
  LMDJ_CHECK(!checkpoint.contains("id"));
  LMDJ_CHECK(checkpoint.at("banks").is_array());
  LMDJ_CHECK(checkpoint.at("banks").size() == 4);
  for (std::size_t bank = 0; bank < 4; ++bank) {
    const auto& encoded_bank = checkpoint.at("banks").at(bank);
    LMDJ_CHECK(encoded_bank.size() == 2);
    LMDJ_CHECK(encoded_bank.at("bank") == bank);
    LMDJ_CHECK(encoded_bank.at("pads").size() == 16);
    for (std::size_t pad = 0; pad < 16; ++pad) {
      const auto& encoded_pad = encoded_bank.at("pads").at(pad);
      LMDJ_CHECK(encoded_pad.size() == 2);
      LMDJ_CHECK(encoded_pad.at("pad") == pad);
      LMDJ_CHECK(!encoded_pad.contains("id"));
    }
  }
  LMDJ_CHECK(checkpoint.at("assets").is_object());
  LMDJ_CHECK(checkpoint.at("takes").is_object());
  LMDJ_CHECK(checkpoint.at("patterns").is_object());
  const auto& encoded_asset =
      checkpoint.at("assets").at(asset_id.value());
  LMDJ_CHECK(encoded_asset.size() == 1);
  LMDJ_CHECK(!encoded_asset.contains("id"));
  const auto& encoded_take =
      checkpoint.at("takes").at(take_id.value());
  LMDJ_CHECK(encoded_take.size() == 2);
  LMDJ_CHECK(!encoded_take.contains("id"));
  const auto& encoded_pattern =
      checkpoint.at("patterns").at(pattern_id.value());
  LMDJ_CHECK(encoded_pattern.size() == 2);
  LMDJ_CHECK(!encoded_pattern.contains("id"));

  write_bytes(
      first_bundle / "assets" /
          (described.value().sha256 + ".wav"),
      read_bytes(source));

  const auto loaded = store.load(first_bundle);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value() == initial);
  LMDJ_CHECK(store.create(second_bundle, loaded.value()).has_value());
  LMDJ_CHECK(
      read_bytes(first_bundle / "history/checkpoints/0.json") ==
      read_bytes(second_bundle / "history/checkpoints/0.json"));
}

void test_persisted_checkpoints_reject_non_contract_shapes() {
  TempDirectory temp;
  ProjectStore store;
  const auto seed_bundle = temp.path() / "seed.lmdj";
  LMDJ_CHECK(store.create(seed_bundle, new_project()).has_value());
  const auto valid =
      read_json(seed_bundle / "history/checkpoints/0.json");

  auto old_private = nlohmann::json{
      {"assets", nlohmann::json::array()},
      {"banks", nlohmann::json::array()},
      {"bpm", 120},
      {"id", test_uuid("project-1")},
      {"patterns", nlohmann::json::array()},
      {"revision", 0},
      {"takes", nlohmann::json::array()},
  };
  for (std::size_t bank = 0; bank < 4; ++bank) {
    auto pads = nlohmann::json::array();
    for (std::size_t pad = 0; pad < 16; ++pad) {
      pads.push_back(
          {
              {"asset_id", nullptr},
              {"id", {{"bank", bank}, {"pad", pad}}},
          });
    }
    old_private.at("banks").push_back(std::move(pads));
  }
  auto missing_contract = valid;
  missing_contract.erase("contract");
  auto wrong_contract = valid;
  wrong_contract["contract"] = "lmdj.project.v2";
  auto invalid_uuid = valid;
  invalid_uuid["project_id"] =
      "00000000-0000-4000-8000-00000000000A";
  auto wrong_sample_rate = valid;
  wrong_sample_rate["takes"][test_uuid("take-1")] = {
      {"events", nlohmann::json::array()},
      {"sample_rate", 44100},
  };
  auto extra_property = valid;
  extra_property["unexpected"] = true;
  const std::array invalid_checkpoints{
      old_private,
      missing_contract,
      wrong_contract,
      invalid_uuid,
      wrong_sample_rate,
      extra_property,
  };

  std::size_t index = 0;
  for (const auto& invalid : invalid_checkpoints) {
    const auto bundle =
        temp.path() /
        ("invalid-" + std::to_string(index++) + ".lmdj");
    LMDJ_CHECK(store.create(bundle, new_project()).has_value());
    write_bytes(
        bundle / "history/checkpoints/0.json",
        lmdj::foundation::canonical_json(invalid) + "\n");
    const auto rejected = store.load(bundle);
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  }
}

void test_create_removes_exact_stale_checkpoint_temp() {
  TempDirectory temp;
  const auto bundle = temp.path() / "stale-checkpoint.lmdj";
  const auto checkpoint_directory =
      bundle / "history/checkpoints";
  std::filesystem::create_directories(checkpoint_directory);
  const auto exact_temp =
      checkpoint_directory / "0.json.tmp.create";
  const auto near_temp =
      checkpoint_directory / "0.json.tmp.create.keep";
  write_bytes(exact_temp, "stale-checkpoint-temp");
  write_bytes(near_temp, "must-survive");
  ProjectStore store;

  const auto created = store.create(bundle, new_project());

  LMDJ_CHECK(created.has_value());
  LMDJ_CHECK(!std::filesystem::exists(exact_temp));
  LMDJ_CHECK(std::filesystem::is_regular_file(near_temp));
  LMDJ_CHECK(read_bytes(near_temp) == "must-survive");
  const auto loaded = store.load(bundle);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value() == new_project());
}

void test_create_resumes_manifest_after_valid_checkpoint_publish() {
  TempDirectory temp;
  ProjectStore store;
  const auto initial = new_project();
  const auto seed = temp.path() / "seed.lmdj";
  LMDJ_CHECK(store.create(seed, initial).has_value());
  const auto checkpoint_bytes =
      read_bytes(seed / "history/checkpoints/0.json");

  const auto bundle = temp.path() / "resume.lmdj";
  std::filesystem::create_directories(
      bundle / "history/checkpoints");
  const auto checkpoint =
      bundle / "history/checkpoints/0.json";
  const auto exact_manifest_temp =
      bundle / "manifest.json.tmp.create";
  const auto near_manifest_temp =
      bundle / "manifest.json.tmp.create.keep";
  write_bytes(checkpoint, checkpoint_bytes);
  write_bytes(exact_manifest_temp, "stale-manifest-temp");
  write_bytes(near_manifest_temp, "must-survive");

  const auto resumed = store.create(bundle, initial);

  LMDJ_CHECK(resumed.has_value());
  LMDJ_CHECK(read_bytes(checkpoint) == checkpoint_bytes);
  LMDJ_CHECK(!std::filesystem::exists(exact_manifest_temp));
  LMDJ_CHECK(std::filesystem::is_regular_file(near_manifest_temp));
  LMDJ_CHECK(read_bytes(near_manifest_temp) == "must-survive");
  LMDJ_CHECK(std::filesystem::is_regular_file(
      bundle / "manifest.json"));
  const auto loaded = store.load(bundle);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value() == initial);
}

void test_create_rejects_mismatched_existing_initial_checkpoint() {
  TempDirectory temp;
  ProjectStore store;
  auto different = lmdj::domain::create_project(
      ProjectId{test_uuid("different-project")}, 121);
  LMDJ_CHECK(different.has_value());
  const auto seed = temp.path() / "different.lmdj";
  LMDJ_CHECK(store.create(seed, different.value()).has_value());
  const auto different_bytes =
      read_bytes(seed / "history/checkpoints/0.json");

  const auto bundle = temp.path() / "mismatch.lmdj";
  std::filesystem::create_directories(
      bundle / "history/checkpoints");
  const auto checkpoint =
      bundle / "history/checkpoints/0.json";
  write_bytes(checkpoint, different_bytes);

  const auto rejected = store.create(bundle, new_project());

  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(!std::filesystem::exists(bundle / "manifest.json"));
  LMDJ_CHECK(read_bytes(checkpoint) == different_bytes);
}

void test_committed_transactions_replay_to_manifest_head() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  LMDJ_CHECK(
      store.execute(
               bundle,
               Command{create_pattern("command-1", 0, "pattern-1", 1)})
          .has_value());
  LMDJ_CHECK(
      store.execute(
               bundle,
               Command{create_pattern("command-2", 1, "pattern-2", 2)})
          .has_value());

  const auto manifest = read_json(bundle / "manifest.json");
  LMDJ_CHECK(manifest.at("head_revision") == 2);
  LMDJ_CHECK(
      manifest.at("head_checkpoint") == "history/checkpoints/2.json");
  LMDJ_CHECK(manifest.at("transactions").size() == 2);

  auto replayed = new_project();
  for (const auto& relative : manifest.at("transactions")) {
    const auto transaction = read_json(
        bundle / relative.get<std::filesystem::path>());
    const auto applied = lmdj::domain::apply(
        replayed, decode_create_pattern(transaction.at("command")), {});
    LMDJ_CHECK(applied.has_value());
    LMDJ_CHECK(
        applied.value().state.revision ==
        transaction.at("revision").get<std::uint64_t>());
    replayed = applied.value().state;
  }

  const auto loaded = store.load(bundle);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(replayed == loaded.value());
  LMDJ_CHECK(loaded.value().revision == 2);
}

void test_imported_assets_are_content_addressed_and_deduplicated() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  const auto source = temp.path() / "kick.wav";
  write_bytes(source, "RIFF-test-wave-bytes");
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  const auto first = store.import_artifact(
      bundle,
      ProjectStore::ImportArtifactRequest{
          meta("import-1", 0),
          AssetId{test_uuid("asset-1")},
          source,
          "audio/wav",
      });
  const auto second = store.import_artifact(
      bundle,
      ProjectStore::ImportArtifactRequest{
          meta("import-2", 1),
          AssetId{test_uuid("asset-2")},
          source,
          "audio/wav",
      });

  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(second.has_value());
  LMDJ_CHECK(regular_file_count(bundle / "assets") == 1);
  const auto& artifact =
      second.value().state.assets.at(
          AssetId{test_uuid("asset-2")}).artifact;
  const auto stored = bundle / "assets" / (artifact.sha256 + ".wav");
  LMDJ_CHECK(std::filesystem::is_regular_file(stored));
  LMDJ_CHECK(read_bytes(stored) == read_bytes(source));
  LMDJ_CHECK(
      first.value().state.assets.at(
          AssetId{test_uuid("asset-1")}).artifact ==
      artifact);
}

void test_import_rejects_invalid_command_before_receipt_and_source_io() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  const auto source = temp.path() / "source.wav";
  const auto missing_source = temp.path() / "missing.wav";
  write_bytes(source, "RIFF-existing-receipt");
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  constexpr std::string_view valid_receipt_id =
      "00000000-0000-4000-8000-00000000000a";
  const auto imported = store.import_artifact(
      bundle,
      ProjectStore::ImportArtifactRequest{
          CommandMeta{CommandId{std::string(valid_receipt_id)}, 0},
          AssetId{test_uuid("asset-existing")},
          source,
          "audio/wav",
      });
  LMDJ_CHECK(imported.has_value());
  const auto before = managed_bundle_snapshot(bundle);
  const std::array invalid_ids{
      std::string{"not-a-uuid"},
      std::string{"foo.tmp.bar"},
      std::string{"00000000-0000-4000-8000-00000000000A"},
      std::string{"00000000-0000-6000-8000-000000000001"},
  };

  for (const auto& invalid_id : invalid_ids) {
    const auto rejected = store.import_artifact(
        bundle,
        ProjectStore::ImportArtifactRequest{
            CommandMeta{CommandId{invalid_id}, 1},
            AssetId{test_uuid("asset-invalid-command")},
            missing_source,
            "audio/wav",
        });
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
    LMDJ_CHECK(managed_bundle_snapshot(bundle) == before);
  }
}

void test_import_rejects_invalid_asset_before_source_io() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  const auto missing_source = temp.path() / "missing.wav";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto before = managed_bundle_snapshot(bundle);

  const auto rejected = store.import_artifact(
      bundle,
      ProjectStore::ImportArtifactRequest{
          meta("import-invalid-asset", 0),
          AssetId{"asset.invalid"},
          missing_source,
          "audio/wav",
      });

  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(managed_bundle_snapshot(bundle) == before);
}

void test_import_rejects_empty_media_type_before_source_io() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  const auto missing_source = temp.path() / "missing.wav";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto before = managed_bundle_snapshot(bundle);

  const auto rejected = store.import_artifact(
      bundle,
      ProjectStore::ImportArtifactRequest{
          meta("import-empty-media", 0),
          AssetId{test_uuid("asset-empty-media")},
          missing_source,
          "",
      });

  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(managed_bundle_snapshot(bundle) == before);
}

void test_write_failure_preserves_previous_manifest_and_recovers_orphans() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  LMDJ_CHECK(
      store.execute(
               bundle,
               Command{create_pattern("command-1", 0, "pattern-1")})
          .has_value());
  const auto manifest_before = read_bytes(bundle / "manifest.json");

  const auto manifest_temp_blocker =
      bundle /
      ("manifest.json.tmp." + test_uuid("command-fail"));
  std::filesystem::create_directory(manifest_temp_blocker);
  const auto failed = store.execute(
      bundle,
      Command{create_pattern("command-fail", 1, "pattern-fail")});

  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(read_bytes(bundle / "manifest.json") == manifest_before);
  const auto survived = store.load(bundle);
  LMDJ_CHECK(survived.has_value());
  LMDJ_CHECK(survived.value().revision == 1);
  LMDJ_CHECK(!survived.value().patterns.contains(
      PatternId{test_uuid("pattern-fail")}));

  std::filesystem::remove(manifest_temp_blocker);
  const auto next = store.execute(
      bundle,
      Command{create_pattern("command-2", 1, "pattern-2")});
  LMDJ_CHECK(next.has_value());
  LMDJ_CHECK(next.value().state.revision == 2);
  LMDJ_CHECK(!std::filesystem::exists(
      bundle /
      ("history/transactions/2-" + test_uuid("command-fail") + ".json")));
  LMDJ_CHECK(std::filesystem::is_regular_file(
      bundle /
      ("history/transactions/2-" + test_uuid("command-2") + ".json")));
}

void test_duplicate_command_replays_after_reopen_without_new_files() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  const auto command =
      Command{create_pattern("command-1", 0, "pattern-1")};
  ProjectStore first_store;
  LMDJ_CHECK(first_store.create(bundle, new_project()).has_value());
  const auto first = first_store.execute(bundle, command);
  LMDJ_CHECK(first.has_value());
  const auto transaction_count =
      regular_file_count(bundle / "history/transactions");

  ProjectStore reopened_store;
  const auto replay = reopened_store.execute(bundle, command);

  LMDJ_CHECK(replay.has_value());
  LMDJ_CHECK(replay.value().replayed);
  LMDJ_CHECK(replay.value().state.revision == 1);
  LMDJ_CHECK(
      regular_file_count(bundle / "history/transactions") ==
      transaction_count);
}

void test_non_uuid_command_ids_are_rejected_before_publishing() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto manifest_before = read_bytes(bundle / "manifest.json");
  const std::array invalid_ids{
      std::string{"not-a-uuid"},
      std::string{"foo.tmp.bar"},
      std::string{"00000000-0000-4000-8000-00000000000A"},
      std::string{"00000000-0000-6000-8000-000000000001"},
  };

  for (const auto& invalid_id : invalid_ids) {
    auto command = create_pattern("valid-command", 0, "pattern-1");
    command.meta.command_id = CommandId{invalid_id};
    const auto rejected = store.execute(bundle, Command{command});
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
    LMDJ_CHECK(read_bytes(bundle / "manifest.json") == manifest_before);
    LMDJ_CHECK(
        regular_file_count(bundle / "history/transactions") == 0);
  }
}

void test_recovery_removes_only_exact_uuid_temp_grammars() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  const auto exact_checkpoint =
      bundle / "history/checkpoints/99.json.tmp";
  const auto near_checkpoint =
      bundle / "history/checkpoints/checkpoint-99.json.tmp";
  const auto exact_transaction =
      bundle / "history/transactions" /
      ("99-" + test_uuid("orphan-command") + ".json.tmp");
  const auto near_transaction =
      bundle / "history/transactions/transaction-99-foo.tmp.bar.json.tmp";
  const auto exact_manifest =
      bundle / ("manifest.json.tmp." + test_uuid("orphan-command"));
  const auto near_manifest =
      bundle / "manifest.json.tmp.foo.tmp.bar";
  const auto sha256 = std::string(64, 'a');
  const auto exact_asset =
      bundle / "assets" /
      (sha256 + ".wav.tmp." + test_uuid("orphan-command"));
  const auto near_asset =
      bundle / "assets" / (sha256 + ".wav.tmp.foo.tmp.bar");
  const std::array exact_paths{
      exact_checkpoint,
      exact_transaction,
      exact_manifest,
      exact_asset,
  };
  const std::array near_paths{
      near_checkpoint,
      near_transaction,
      near_manifest,
      near_asset,
  };
  for (const auto& path : exact_paths) {
    write_bytes(path, "exact-orphan");
  }
  for (const auto& path : near_paths) {
    write_bytes(path, "must-survive");
  }

  const auto committed = store.execute(
      bundle,
      Command{create_pattern("command-1", 0, "pattern-1")});

  LMDJ_CHECK(committed.has_value());
  for (const auto& path : exact_paths) {
    LMDJ_CHECK(!std::filesystem::exists(path));
  }
  for (const auto& path : near_paths) {
    LMDJ_CHECK(std::filesystem::is_regular_file(path));
    LMDJ_CHECK(read_bytes(path) == "must-survive");
  }
}

void test_public_commands_reject_unsafe_ids_before_publishing() {
  TempDirectory temp;
  ProjectStore store;

  const auto pattern_bundle = temp.path() / "pattern.lmdj";
  LMDJ_CHECK(store.create(pattern_bundle, new_project()).has_value());
  const auto pattern_manifest = read_bytes(pattern_bundle / "manifest.json");
  auto unsafe_pattern_command =
      create_pattern("pattern-command", 0, "safe-pattern");
  unsafe_pattern_command.pattern.id = PatternId{"nested/pattern"};
  const auto unsafe_pattern =
      store.execute(pattern_bundle, Command{unsafe_pattern_command});
  LMDJ_CHECK(!unsafe_pattern.has_value());
  LMDJ_CHECK(unsafe_pattern.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      read_bytes(pattern_bundle / "manifest.json") == pattern_manifest);
  LMDJ_CHECK(
      regular_file_count(pattern_bundle / "history/transactions") == 0);
  const auto pattern_reopen = store.load(pattern_bundle);
  LMDJ_CHECK(pattern_reopen.has_value());
  LMDJ_CHECK(pattern_reopen.value().revision == 0);

  const auto take_bundle = temp.path() / "take.lmdj";
  LMDJ_CHECK(store.create(take_bundle, new_project()).has_value());
  const auto take_manifest = read_bytes(take_bundle / "manifest.json");
  const auto unsafe_take = store.execute(
      take_bundle,
      Command{lmdj::domain::RecordTake{
          meta("take-command", 0),
          {
              lmdj::foundation::TakeId{"nested/take"},
              48000,
              {{PadSlotId{0, 0}, 123, 100}},
          },
          {
              PatternId{test_uuid("safe-pattern")},
              1,
              {{PadSlotId{0, 0}, 0, 100}},
          },
      }});
  LMDJ_CHECK(!unsafe_take.has_value());
  LMDJ_CHECK(unsafe_take.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(take_bundle / "manifest.json") == take_manifest);
  LMDJ_CHECK(
      regular_file_count(take_bundle / "history/transactions") == 0);
  const auto take_reopen = store.load(take_bundle);
  LMDJ_CHECK(take_reopen.has_value());
  LMDJ_CHECK(take_reopen.value().revision == 0);

  const auto asset_bundle = temp.path() / "asset.lmdj";
  const auto source = temp.path() / "source.wav";
  write_bytes(source, "unsafe-id-source");
  LMDJ_CHECK(store.create(asset_bundle, new_project()).has_value());
  const auto asset_manifest = read_bytes(asset_bundle / "manifest.json");
  const auto unsafe_asset = store.import_artifact(
      asset_bundle,
      ProjectStore::ImportArtifactRequest{
          meta("asset-command", 0),
          AssetId{"nested/asset"},
          source,
          "audio/wav",
      });
  LMDJ_CHECK(!unsafe_asset.has_value());
  LMDJ_CHECK(unsafe_asset.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(read_bytes(asset_bundle / "manifest.json") == asset_manifest);
  LMDJ_CHECK(regular_file_count(asset_bundle / "assets") == 0);
  LMDJ_CHECK(
      regular_file_count(asset_bundle / "history/transactions") == 0);
  const auto asset_reopen = store.load(asset_bundle);
  LMDJ_CHECK(asset_reopen.has_value());
  LMDJ_CHECK(asset_reopen.value().revision == 0);
}

void test_symlinked_managed_directory_is_rejected_before_recovery() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  const auto external = temp.path() / "external-assets";
  std::filesystem::create_directory(external);
  const auto external_file =
      external /
      (std::string(64, 'a') + ".wav");
  write_bytes(external_file, "must-survive");
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto manifest_before = read_bytes(bundle / "manifest.json");

  std::filesystem::remove(bundle / "assets");
  std::filesystem::create_directory_symlink(external, bundle / "assets");
  const auto result = store.execute(
      bundle,
      Command{create_pattern("command-1", 0, "pattern-1")});

  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(std::filesystem::is_regular_file(external_file));
  LMDJ_CHECK(read_bytes(external_file) == "must-survive");
  LMDJ_CHECK(read_bytes(bundle / "manifest.json") == manifest_before);
  LMDJ_CHECK(
      regular_file_count(bundle / "history/transactions") == 0);
}

void test_independent_advisory_lock_blocks_execute_until_release() {
  using namespace std::chrono_literals;
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  const int lock_fd =
      ::open((bundle / ".lock").c_str(), O_RDWR | O_CLOEXEC);
  LMDJ_CHECK(lock_fd >= 0);
  LMDJ_CHECK(::flock(lock_fd, LOCK_EX) == 0);

  auto pending = std::async(
      std::launch::async,
      [&store, &bundle]() {
        return store.execute(
            bundle,
            Command{create_pattern("command-locked", 0, "pattern-locked")});
      });
  LMDJ_CHECK(pending.wait_for(150ms) == std::future_status::timeout);
  LMDJ_CHECK(read_json(bundle / "manifest.json").at("head_revision") == 0);

  LMDJ_CHECK(::flock(lock_fd, LOCK_UN) == 0);
  LMDJ_CHECK(::close(lock_fd) == 0);
  const auto committed = pending.get();
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().state.revision == 1);
  LMDJ_CHECK(
      read_json(bundle / "manifest.json").at("head_revision") == 1);
}

}  // namespace

int main() {
  try {
    test_canonical_checkpoint_round_trip_and_bundle_shape();
    test_persisted_checkpoints_reject_non_contract_shapes();
    test_create_removes_exact_stale_checkpoint_temp();
    test_create_resumes_manifest_after_valid_checkpoint_publish();
    test_create_rejects_mismatched_existing_initial_checkpoint();
    test_committed_transactions_replay_to_manifest_head();
    test_imported_assets_are_content_addressed_and_deduplicated();
    test_import_rejects_invalid_command_before_receipt_and_source_io();
    test_import_rejects_invalid_asset_before_source_io();
    test_import_rejects_empty_media_type_before_source_io();
    test_write_failure_preserves_previous_manifest_and_recovers_orphans();
    test_duplicate_command_replays_after_reopen_without_new_files();
    test_non_uuid_command_ids_are_rejected_before_publishing();
    test_recovery_removes_only_exact_uuid_temp_grammars();
    test_public_commands_reject_unsafe_ids_before_publishing();
    test_symlinked_managed_directory_is_rejected_before_recovery();
    test_independent_advisory_lock_blocks_execute_until_release();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project store tests: PASS\n";
  return 0;
}
