#include <array>
#include <chrono>
#include <cstddef>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
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
using lmdj::project_io::ProjectStoragePlatform;
using lmdj::project_io::ProjectWriterLease;

lmdj::foundation::Result<void> fail_manifest_publish(
    lmdj::project_io::testing::FaultPoint point,
    const std::filesystem::path& path) {
  if (point != lmdj::project_io::testing::FaultPoint::manifest_publish) {
    return lmdj::foundation::Result<void>::success();
  }
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected manifest publication failure",
          {{"path", path.generic_string()}},
      });
}

class ProjectStoreFaultGuard {
 public:
  ProjectStoreFaultGuard() {
    lmdj::project_io::testing::set_fault_hook(fail_manifest_publish);
  }

  ~ProjectStoreFaultGuard() {
    lmdj::project_io::testing::set_fault_hook(nullptr);
  }

  ProjectStoreFaultGuard(const ProjectStoreFaultGuard&) = delete;
  ProjectStoreFaultGuard& operator=(const ProjectStoreFaultGuard&) = delete;
};

class MemoryWriterLease final : public ProjectWriterLease {};

class MemoryStoragePlatform final : public ProjectStoragePlatform {
 public:
  lmdj::foundation::Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(
      const std::filesystem::path&) override {
    ++writer_acquisitions;
    return lmdj::foundation::Result<std::unique_ptr<ProjectWriterLease>>::success(
        std::make_unique<MemoryWriterLease>());
  }

  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    auto current = path.lexically_normal();
    while (!current.empty()) {
      directories_.insert(key(current));
      const auto parent = current.parent_path();
      if (parent == current) {
        break;
      }
      current = parent;
    }
    return lmdj::foundation::Result<void>::success();
  }

  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    return lmdj::foundation::Result<bool>::success(
        files_.contains(key(path)) || directories_.contains(key(path)));
  }

  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    const auto found = files_.find(key(path));
    if (found == files_.end()) {
      return lmdj::foundation::Result<std::uint64_t>::failure(error(path));
    }
    return lmdj::foundation::Result<std::uint64_t>::success(
        found->second.size());
  }

  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    const auto found = files_.find(key(path));
    if (found == files_.end()) {
      return lmdj::foundation::Result<std::vector<std::byte>>::failure(
          error(path));
    }
    return lmdj::foundation::Result<std::vector<std::byte>>::success(
        found->second);
  }

  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> input) override {
    const auto normalized = key(path);
    if (fail_next_asset_create &&
        path.parent_path().filename() == "assets") {
      fail_next_asset_create = false;
      return lmdj::foundation::Result<void>::failure(error(path));
    }
    if (files_.contains(normalized) || directories_.contains(normalized)) {
      auto collision = error(path);
      collision.details["storage_condition"] = "already_exists";
      return lmdj::foundation::Result<void>::failure(std::move(collision));
    }
    files_[normalized] = {input.begin(), input.end()};
    operation_log.push_back("create_immutable:" + normalized);
    return lmdj::foundation::Result<void>::success();
  }

  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> input) override {
    files_[key(path)] = {input.begin(), input.end()};
    operation_log.push_back(
        "replace_complete:" + path.lexically_normal().generic_string());
    return lmdj::foundation::Result<void>::success();
  }

  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> input) override {
    const auto found = files_.find(key(path));
    if (found == files_.end()) {
      return lmdj::foundation::Result<void>::failure(error(path));
    }
    if (valid_prefix_length > found->second.size()) {
      return lmdj::foundation::Result<void>::failure(error(path));
    }
    found->second.resize(static_cast<std::size_t>(valid_prefix_length));
    found->second.insert(found->second.end(), input.begin(), input.end());
    return lmdj::foundation::Result<void>::success();
  }

  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    files_.erase(key(path));
    return lmdj::foundation::Result<void>::success();
  }

  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    if (!directories_.contains(key(path))) {
      return lmdj::foundation::Result<std::vector<std::string>>::failure(
          error(path));
    }
    std::vector<std::string> names;
    const auto collect = [&path, &names](const std::string& encoded) {
      const auto candidate = std::filesystem::path{encoded};
      if (candidate.parent_path() == path.lexically_normal()) {
        names.push_back(candidate.filename().string());
      }
    };
    for (const auto& [encoded, ignored] : files_) {
      (void)ignored;
      collect(encoded);
    }
    std::sort(
        names.begin(),
        names.end(),
        [](const std::string& left, const std::string& right) {
          return std::lexicographical_compare(
              left.begin(),
              left.end(),
              right.begin(),
              right.end(),
              [](unsigned char left_byte, unsigned char right_byte) {
                return left_byte < right_byte;
              });
        });
    names.erase(std::unique(names.begin(), names.end()), names.end());
    return lmdj::foundation::Result<std::vector<std::string>>::success(
        std::move(names));
  }

  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path&) const override {
    return lmdj::foundation::Result<void>::success();
  }

  std::vector<std::string> operation_log;
  std::size_t writer_acquisitions = 0;
  bool fail_next_asset_create = false;

 private:
  static std::string key(const std::filesystem::path& path) {
    return path.lexically_normal().generic_string();
  }

  static lmdj::foundation::Error error(
      const std::filesystem::path& path) {
    return {
        ErrorCode::io_error,
        "in-memory storage operation failed",
        {{"path", path.generic_string()}},
    };
  }

  std::set<std::string> directories_;
  std::map<std::string, std::vector<std::byte>> files_;
};

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

void test_common_transactions_use_semantic_storage_obligations() {
  const auto bundle = std::filesystem::path{"memory/project.lmdj"};
  auto platform = std::make_shared<MemoryStoragePlatform>();
  ProjectStore store{platform};

  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  LMDJ_CHECK(
      platform->ensure_directory(bundle / "ignored-directory").has_value());
  const std::vector<std::string> root_file_names{"manifest.json"};
  LMDJ_CHECK(platform->list_names(bundle).value() == root_file_names);
  platform->operation_log.clear();
  const auto executed = store.execute(
      bundle,
      Command{create_pattern("semantic-command", 0, "semantic-pattern")});
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().state.revision == 1);
  LMDJ_CHECK(platform->writer_acquisitions >= 2);

  const auto transaction =
      bundle / "history/transactions" /
      ("1-" + test_uuid("semantic-command") + ".json");
  const auto checkpoint = bundle / "history/checkpoints/1.json";
  const std::vector<std::string> expected_operations{
      "create_immutable:" + transaction.generic_string(),
      "create_immutable:" + checkpoint.generic_string(),
      "replace_complete:" + (bundle / "manifest.json").generic_string(),
  };
  LMDJ_CHECK(platform->operation_log == expected_operations);
}

void test_default_store_remains_copy_list_initializable() {
  ProjectStore store = {};
  (void)store;
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
  const auto opaque = std::string{"0123456789abcdef0123456789abcdef"};
  const auto exact_temp =
      checkpoint_directory / ("0.json.tmp." + opaque);
  const auto near_temp =
      checkpoint_directory / ("0.json.tmp." + opaque + ".keep");
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
  const auto opaque = std::string{"0123456789abcdef0123456789abcdef"};
  const auto exact_manifest_temp =
      bundle / ("manifest.json.tmp." + opaque);
  const auto near_manifest_temp =
      bundle / ("manifest.json.tmp." + opaque + ".keep");
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

void test_byte_backed_import_publishes_immutable_artifact_without_staging() {
  const auto bundle = std::filesystem::path{"memory/bytes.lmdj"};
  auto platform = std::make_shared<MemoryStoragePlatform>();
  ProjectStore store{platform};
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  platform->operation_log.clear();

  std::array bytes{
      std::byte{'R'},
      std::byte{'I'},
      std::byte{'F'},
      std::byte{'F'},
      std::byte{0x00},
      std::byte{0x01},
  };
  const auto asset_id = AssetId{test_uuid("byte-backed-asset")};
  const ProjectStore::ImportArtifactBytesRequest request{
      meta("byte-backed-command", 0),
      asset_id,
      "audio/wav",
      bytes,
  };

  const auto imported = store.import_artifact_bytes(bundle, request);

  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(imported.value().state.revision == 1);
  const auto& artifact =
      imported.value().state.assets.at(asset_id).artifact;
  LMDJ_CHECK(artifact.byte_length == bytes.size());
  const auto artifact_path =
      bundle / "assets" / (artifact.sha256 + ".wav");
  const auto transaction =
      bundle / "history/transactions" /
      ("1-" + request.meta.command_id.value() + ".json");
  const std::vector<std::string> expected_operations{
      "create_immutable:" + artifact_path.generic_string(),
      "create_immutable:" + transaction.generic_string(),
      "create_immutable:" +
          (bundle / "history/checkpoints/1.json").generic_string(),
      "replace_complete:" + (bundle / "manifest.json").generic_string(),
  };
  LMDJ_CHECK(platform->operation_log == expected_operations);
  const auto expected_bytes =
      std::vector<std::byte>(bytes.begin(), bytes.end());
  bytes.back() = std::byte{0x02};
  const auto stored = store.read_artifact(bundle, artifact);
  LMDJ_CHECK(stored.has_value());
  LMDJ_CHECK(stored.value() == expected_bytes);
  bytes.back() = std::byte{0x01};

  platform->operation_log.clear();
  const auto replayed = store.import_artifact_bytes(bundle, request);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state.revision == 1);
  LMDJ_CHECK(platform->operation_log.empty());

  const std::array changed_identity_requests{
      ProjectStore::ImportArtifactBytesRequest{
          CommandMeta{request.meta.command_id, 1},
          request.asset_id,
          request.media_type,
          bytes,
      },
      ProjectStore::ImportArtifactBytesRequest{
          request.meta,
          AssetId{test_uuid("byte-backed-changed-asset")},
          request.media_type,
          bytes,
      },
      ProjectStore::ImportArtifactBytesRequest{
          request.meta,
          request.asset_id,
          "application/octet-stream",
          bytes,
      },
  };
  for (const auto& changed_identity : changed_identity_requests) {
    const auto rejected_identity =
        store.import_artifact_bytes(bundle, changed_identity);
    LMDJ_CHECK(!rejected_identity.has_value());
    LMDJ_CHECK(
        rejected_identity.error().code == ErrorCode::invalid_argument);
    LMDJ_CHECK(platform->operation_log.empty());
  }

  auto changed_bytes = bytes;
  changed_bytes.back() = std::byte{0x02};
  const auto rejected = store.import_artifact_bytes(
      bundle,
      ProjectStore::ImportArtifactBytesRequest{
          request.meta,
          request.asset_id,
          request.media_type,
          changed_bytes,
      });
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(platform->operation_log.empty());

  auto unpublished_bytes = bytes;
  unpublished_bytes.front() = std::byte{'X'};
  platform->fail_next_asset_create = true;
  const auto write_failed = store.import_artifact_bytes(
      bundle,
      ProjectStore::ImportArtifactBytesRequest{
          meta("byte-backed-write-failure", 1),
          AssetId{test_uuid("byte-backed-write-failure-asset")},
          "audio/wav",
          unpublished_bytes,
      });
  LMDJ_CHECK(!write_failed.has_value());
  LMDJ_CHECK(write_failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(platform->operation_log.empty());
  const auto after_write_failure = store.load(bundle);
  LMDJ_CHECK(after_write_failure.has_value());
  LMDJ_CHECK(after_write_failure.value().revision == 1);

  const auto duplicate_content = store.import_artifact_bytes(
      bundle,
      ProjectStore::ImportArtifactBytesRequest{
          meta("byte-backed-deduplicated-command", 1),
          AssetId{test_uuid("byte-backed-deduplicated-asset")},
          "audio/wav",
          bytes,
      });
  LMDJ_CHECK(duplicate_content.has_value());
  LMDJ_CHECK(duplicate_content.value().state.revision == 2);
  LMDJ_CHECK(
      std::none_of(
          platform->operation_log.begin(),
          platform->operation_log.end(),
          [&artifact_path](const std::string& operation) {
            return operation ==
                   "create_immutable:" + artifact_path.generic_string();
          }));
}

void test_duplicate_command_ids_require_complete_persisted_identity() {
  TempDirectory temp;
  const auto bundle = temp.path() / "replay-identity.lmdj";
  const auto source = temp.path() / "source-a.wav";
  const auto changed_source = temp.path() / "source-b.wav";
  write_bytes(source, "source-a");
  write_bytes(changed_source, "source-b");
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  const lmdj::domain::AssignPad assigned{
      meta("identity-pad", 0),
      PadSlotId{0, 0},
      std::nullopt,
  };
  auto applied = store.execute(bundle, Command{assigned});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(!applied.value().replayed);
  applied = store.execute(bundle, Command{assigned});
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(applied.value().replayed);

  auto changed_pad_revision = assigned;
  changed_pad_revision.meta.expected_revision = 1;
  auto rejected =
      store.execute(bundle, Command{changed_pad_revision});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);

  auto changed_slot = assigned;
  changed_slot.slot = PadSlotId{0, 1};
  rejected = store.execute(bundle, Command{changed_slot});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);

  auto changed_assignment = assigned;
  changed_assignment.asset_id =
      AssetId{test_uuid("different-assignment")};
  rejected = store.execute(bundle, Command{changed_assignment});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);

  rejected = store.execute(
      bundle,
      Command{create_pattern(
          "identity-pad", 0, "cross-type-pattern")});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);

  const ProjectStore::ImportArtifactRequest import_request{
      meta("identity-import", 1),
      AssetId{test_uuid("identity-asset")},
      source,
      "audio/wav",
  };
  auto imported = store.import_artifact(bundle, import_request);
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(!imported.value().replayed);
  imported = store.import_artifact(bundle, import_request);
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(imported.value().replayed);

  auto changed_import_revision = import_request;
  changed_import_revision.meta.expected_revision = 2;
  imported = store.import_artifact(bundle, changed_import_revision);
  LMDJ_CHECK(!imported.has_value());
  LMDJ_CHECK(imported.error().code == ErrorCode::invalid_argument);

  auto changed_asset = import_request;
  changed_asset.asset_id = AssetId{test_uuid("changed-asset")};
  imported = store.import_artifact(bundle, changed_asset);
  LMDJ_CHECK(!imported.has_value());
  LMDJ_CHECK(imported.error().code == ErrorCode::invalid_argument);

  auto changed_bytes = import_request;
  changed_bytes.source = changed_source;
  imported = store.import_artifact(bundle, changed_bytes);
  LMDJ_CHECK(!imported.has_value());
  LMDJ_CHECK(imported.error().code == ErrorCode::invalid_argument);

  auto changed_media = import_request;
  changed_media.media_type = "application/octet-stream";
  imported = store.import_artifact(bundle, changed_media);
  LMDJ_CHECK(!imported.has_value());
  LMDJ_CHECK(imported.error().code == ErrorCode::invalid_argument);

  auto cross_type_import = import_request;
  cross_type_import.meta = assigned.meta;
  imported = store.import_artifact(bundle, cross_type_import);
  LMDJ_CHECK(!imported.has_value());
  LMDJ_CHECK(imported.error().code == ErrorCode::invalid_argument);

  auto import_id_as_pad = assigned;
  import_id_as_pad.meta = import_request.meta;
  rejected = store.execute(bundle, Command{import_id_as_pad});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);

  auto missing_source = import_request;
  missing_source.source = temp.path() / "no-longer-present.wav";
  imported = store.import_artifact(bundle, missing_source);
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(imported.value().replayed);
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

  lmdj::foundation::Result<lmdj::domain::AppliedCommand> failed =
      lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "test command did not run",
          });
  {
    ProjectStoreFaultGuard guard;
    failed = store.execute(
        bundle,
        Command{create_pattern("command-fail", 1, "pattern-fail")});
  }

  LMDJ_CHECK(!failed.has_value());
  LMDJ_CHECK(failed.error().code == ErrorCode::io_error);
  LMDJ_CHECK(read_bytes(bundle / "manifest.json") == manifest_before);
  const auto survived = store.load(bundle);
  LMDJ_CHECK(survived.has_value());
  LMDJ_CHECK(survived.value().revision == 1);
  LMDJ_CHECK(!survived.value().patterns.contains(
      PatternId{test_uuid("pattern-fail")}));

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

void test_recovery_removes_only_exact_opaque_temp_grammars() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  const auto opaque = std::string{"0123456789abcdef0123456789abcdef"};
  const auto exact_checkpoint =
      bundle / "history/checkpoints" / ("99.json.tmp." + opaque);
  const auto near_checkpoint =
      bundle / "history/checkpoints" /
      ("checkpoint-99.json.tmp." + opaque);
  const auto exact_transaction =
      bundle / "history/transactions" /
      ("99-" + test_uuid("orphan-command") + ".json.tmp." + opaque);
  const auto near_transaction =
      bundle / "history/transactions" /
      ("transaction-99-" + test_uuid("orphan-command") + ".json.tmp." +
       opaque);
  const auto exact_manifest =
      bundle / ("manifest.json.tmp." + opaque);
  const auto near_manifest =
      bundle / ("manifest.json.tmp." + opaque + ".keep");
  const auto sha256 = std::string(64, 'a');
  const auto exact_asset =
      bundle / "assets" /
      (sha256 + ".wav.tmp." + opaque);
  const auto near_asset =
      bundle / "assets" / (sha256 + ".wav.tmp." + opaque + ".keep");
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

void test_json_reads_reject_excessive_nesting() {
  // This locks in that a deeply nested document is refused rather than
  // accepted. It does not isolate the depth guard: with the guard disabled the
  // document is still refused, by checkpoint contract validation, because
  // nlohmann 3.12.0 parses and destroys iteratively and therefore does not
  // crash on depth. The guard itself is proven in tests/core/foundation.
  //
  // Symlink handling is not asserted here: read_json() goes through the storage
  // platform, so O_NOFOLLOW belongs to the platform implementation rather than
  // to this module. A symlink already in the bundle is refused by the recursive
  // symlink scan that runs before any read.
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  LMDJ_CHECK(store.load(bundle).has_value());

  const auto checkpoint = bundle / "history/checkpoints/0.json";
  std::string deep = R"({"contract":"lmdj.project.checkpoint.v1","nested":)";
  deep.append(200000, '[');
  deep.append(200000, ']');
  deep.push_back('}');
  write_bytes(checkpoint, deep);
  const auto nested = store.load(bundle);
  LMDJ_CHECK(!nested.has_value());
  LMDJ_CHECK(nested.error().code == ErrorCode::invalid_project);
}

void test_independent_platform_reports_busy_until_release() {
  TempDirectory temp;
  const auto bundle = temp.path() / "beat-proof.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  auto holder_platform =
      lmdj::project_io::make_default_project_storage_platform();
  auto held = holder_platform->acquire_writer(bundle);
  LMDJ_CHECK(held.has_value());
  auto competing_platform =
      lmdj::project_io::make_default_project_storage_platform();
  ProjectStore competing_store{competing_platform};
  const auto busy = competing_store.execute(
      bundle,
      Command{create_pattern("command-locked", 0, "pattern-locked")});
  LMDJ_CHECK(!busy.has_value());
  LMDJ_CHECK(busy.error().code == ErrorCode::io_error);
  LMDJ_CHECK(busy.error().details.at("storage_condition") == "project_busy");
  LMDJ_CHECK(read_json(bundle / "manifest.json").at("head_revision") == 0);

  held.value().reset();
  const auto committed = competing_store.execute(
      bundle,
      Command{create_pattern("command-locked", 0, "pattern-locked")});
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().state.revision == 1);
  LMDJ_CHECK(
      read_json(bundle / "manifest.json").at("head_revision") == 1);
}

void test_artifact_reads_are_bounded_symlink_safe_and_integrity_verified() {
  TempDirectory temp;
  const auto bundle = temp.path() / "artifact-read.lmdj";
  const auto source = temp.path() / "source.wav";
  const std::string source_bytes = "project-owned-artifact";
  write_bytes(source, source_bytes);

  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto imported = store.import_artifact(
      bundle,
      ProjectStore::ImportArtifactRequest{
          meta("artifact-read-command", 0),
          AssetId{test_uuid("artifact-read-asset")},
          source,
          "audio/wav",
      });
  LMDJ_CHECK(imported.has_value());
  const auto& artifact =
      imported.value().state.assets.begin()->second.artifact;

  const auto bytes = store.read_artifact(bundle, artifact);
  LMDJ_CHECK(bytes.has_value());
  LMDJ_CHECK(
      std::string(
          reinterpret_cast<const char*>(bytes.value().data()),
          bytes.value().size()) == source_bytes);

  auto wrong_length = artifact;
  ++wrong_length.byte_length;
  const auto length_result =
      store.read_artifact(bundle, wrong_length);
  LMDJ_CHECK(!length_result.has_value());
  LMDJ_CHECK(length_result.error().code == ErrorCode::cook_failed);

  auto oversized = artifact;
  oversized.byte_length = 64U * 1024U * 1024U + 1U;
  const auto oversized_result =
      store.read_artifact(bundle, oversized);
  LMDJ_CHECK(!oversized_result.has_value());
  LMDJ_CHECK(oversized_result.error().code == ErrorCode::invalid_argument);

  const auto fabricated_sha = std::string(64, 'a');
  const auto fabricated_blob =
      bundle / "assets" / (fabricated_sha + ".wav");
  write_bytes(fabricated_blob, source_bytes);
  auto wrong_hash = artifact;
  wrong_hash.sha256 = fabricated_sha;
  const auto hash_result = store.read_artifact(bundle, wrong_hash);
  LMDJ_CHECK(!hash_result.has_value());
  LMDJ_CHECK(hash_result.error().code == ErrorCode::cook_failed);
  std::filesystem::remove(fabricated_blob);

  const auto blob =
      bundle / "assets" / (artifact.sha256 + ".wav");
  const auto external = temp.path() / "external.wav";
  write_bytes(external, source_bytes);
  std::filesystem::remove(blob);
  std::filesystem::create_symlink(external, blob);
  const auto symlink_result = store.read_artifact(bundle, artifact);
  LMDJ_CHECK(!symlink_result.has_value());
  LMDJ_CHECK(symlink_result.error().code == ErrorCode::invalid_project);
}

void test_artifact_read_rejects_symlinked_intermediate_directory() {
  TempDirectory temp;
  const auto real_root = temp.path() / "real";
  std::filesystem::create_directory(real_root);
  const auto bundle = real_root / "artifact-read.lmdj";
  const auto source = temp.path() / "source.wav";
  write_bytes(source, "stable-dirfd-artifact");

  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto imported = store.import_artifact(
      bundle,
      ProjectStore::ImportArtifactRequest{
          meta("stable-dirfd-command", 0),
          AssetId{test_uuid("stable-dirfd-asset")},
          source,
          "audio/wav",
      });
  LMDJ_CHECK(imported.has_value());
  const auto artifact =
      imported.value().state.assets.begin()->second.artifact;

  const auto alias = temp.path() / "alias";
  std::filesystem::create_directory_symlink(real_root, alias);
  const auto aliased_bundle = alias / bundle.filename();
  const auto read = store.read_artifact(aliased_bundle, artifact);
  LMDJ_CHECK(!read.has_value());
  LMDJ_CHECK(read.error().code == ErrorCode::invalid_project);
}

}  // namespace

int main() {
  try {
    test_common_transactions_use_semantic_storage_obligations();
    test_default_store_remains_copy_list_initializable();
    test_canonical_checkpoint_round_trip_and_bundle_shape();
    test_persisted_checkpoints_reject_non_contract_shapes();
    test_create_removes_exact_stale_checkpoint_temp();
    test_create_resumes_manifest_after_valid_checkpoint_publish();
    test_create_rejects_mismatched_existing_initial_checkpoint();
    test_committed_transactions_replay_to_manifest_head();
    test_imported_assets_are_content_addressed_and_deduplicated();
    test_byte_backed_import_publishes_immutable_artifact_without_staging();
    test_duplicate_command_ids_require_complete_persisted_identity();
    test_import_rejects_invalid_command_before_receipt_and_source_io();
    test_import_rejects_invalid_asset_before_source_io();
    test_import_rejects_empty_media_type_before_source_io();
    test_write_failure_preserves_previous_manifest_and_recovers_orphans();
    test_duplicate_command_replays_after_reopen_without_new_files();
    test_non_uuid_command_ids_are_rejected_before_publishing();
    test_recovery_removes_only_exact_opaque_temp_grammars();
    test_public_commands_reject_unsafe_ids_before_publishing();
    test_symlinked_managed_directory_is_rejected_before_recovery();
    test_json_reads_reject_excessive_nesting();
    test_independent_platform_reports_busy_until_release();
    test_artifact_reads_are_bounded_symlink_safe_and_integrity_verified();
    test_artifact_read_rejects_symlinked_intermediate_directory();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project store tests: PASS\n";
  return 0;
}
