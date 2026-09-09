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
#include <variant>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/legacy_project.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CreatePattern;
using lmdj::domain::AssignPatternSlot;
using lmdj::domain::ClearPatternSlot;
using lmdj::domain::MergePatternEvents;
using lmdj::domain::MovePatternSlot;
using lmdj::domain::Asset;
using lmdj::domain::AssetLineage;
using lmdj::domain::PadPlayback;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::ProjectContract;
using lmdj::domain::PerformanceId;
using lmdj::domain::ResetPadPlayback;
using lmdj::domain::TriggerMode;
using lmdj::domain::UpdatePadPlayback;
using lmdj::domain::UpdateSequenceSettings;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::ProjectStoragePlatform;
using lmdj::project_io::ProjectWriterLease;
using lmdj::project_io::SequenceFlushIdentity;
using lmdj::project_io::SequenceJournal;
using lmdj::test::v3_checkpoint;

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

class MemoryWriterLease final : public ProjectWriterLease {
 public:
  explicit MemoryWriterLease(bool& held) : held_(held) { held_ = true; }
  ~MemoryWriterLease() override { held_ = false; }
 private:
  bool& held_;
};

class MemoryStoragePlatform final : public ProjectStoragePlatform {
 public:
  lmdj::foundation::Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(
      const std::filesystem::path&) override {
    ++writer_acquisitions;
    if (writer_held) {
      return lmdj::foundation::Result<std::unique_ptr<ProjectWriterLease>>::failure(
          {ErrorCode::io_error, "Project is busy",
           {{"storage_condition", "project_busy"}}});
    }
    return lmdj::foundation::Result<std::unique_ptr<ProjectWriterLease>>::success(
        std::make_unique<MemoryWriterLease>(writer_held));
  }

  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    ++write_calls;
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

  lmdj::foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const override {
    return lmdj::foundation::Result<bool>::success(
        directories_.contains(key(path)));
  }

  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    if (require_read_lease) LMDJ_CHECK(writer_held);
    const auto found = files_.find(key(path));
    if (found == files_.end()) {
      return lmdj::foundation::Result<std::uint64_t>::failure(error(path));
    }
    return lmdj::foundation::Result<std::uint64_t>::success(
        found->second.size());
  }

  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    if (require_read_lease) LMDJ_CHECK(writer_held);
    read_paths.push_back(path);
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
    ++write_calls;
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
    ++write_calls;
    files_[key(path)] = {input.begin(), input.end()};
    operation_log.push_back(
        "replace_complete:" + path.lexically_normal().generic_string());
    return lmdj::foundation::Result<void>::success();
  }

  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t valid_prefix_length,
      std::span<const std::byte> input) override {
    ++write_calls;
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
    ++write_calls;
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
  mutable std::vector<std::filesystem::path> read_paths;
  std::size_t writer_acquisitions = 0;
  bool fail_next_asset_create = false;
  bool writer_held = false;
  bool require_read_lease = false;
  std::size_t write_calls = 0;

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
          {PatternEvent{
              PadSlotId{0, 0},
              step * lmdj::domain::kSixteenthTicks,
              lmdj::domain::kSixteenthTicks,
              100}},
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
            encoded.contains("step")
                ? encoded.at("step").get<std::uint32_t>() * 240U
                : encoded.at("onset_tick").get<std::uint32_t>(),
            encoded.contains("duration_tick")
                ? encoded.at("duration_tick").get<std::uint32_t>()
                : 240U,
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

nlohmann::json legacy_checkpoint(
    nlohmann::json checkpoint,
    std::string_view contract) {
  LMDJ_CHECK(checkpoint.at("contract") == "lmdj.project.v5");
  LMDJ_CHECK(
      contract == "lmdj.project.v1" || contract == "lmdj.project.v2");
  auto assets = nlohmann::json::object();
  for (const auto& asset : checkpoint.at("assets")) {
    assets[asset.at("asset_id").get<std::string>()] = {
        {"artifact", asset.at("artifact")}};
  }
  auto patterns = nlohmann::json::object();
  for (const auto& pattern : checkpoint.at("patterns")) {
    auto events = nlohmann::json::array();
    for (const auto& event : pattern.at("events")) {
      events.push_back(
          {
              {"slot", event.at("slot")},
              {"step", event.at("onset_tick").get<std::uint32_t>() / 240U},
              {"velocity", event.at("velocity")},
          });
    }
    patterns[pattern.at("pattern_id").get<std::string>()] = {
        {"bars", pattern.at("bars")},
        {"events", std::move(events)},
    };
  }
  checkpoint["assets"] = std::move(assets);
  checkpoint["contract"] = contract;
  checkpoint["patterns"] = std::move(patterns);
  checkpoint["takes"] = nlohmann::json::object();
  checkpoint.erase("sequence_settings");
  checkpoint.erase("pattern_slots");
  checkpoint.erase("performances");
  if (contract == "lmdj.project.v1") {
    for (auto& bank : checkpoint["banks"]) {
      for (auto& pad : bank["pads"]) {
        pad.erase("playback");
      }
    }
  }
  return checkpoint;
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
  const auto pattern_id = PatternId{test_uuid("pattern-1")};
  initial.assets.emplace(
      asset_id, Asset{asset_id, described.value(), std::nullopt});
  initial.banks.at(0).at(0).asset_id = asset_id;
  initial.patterns.emplace(
      pattern_id,
      Pattern{
          pattern_id,
          1,
          {PatternEvent{
              PadSlotId{0, 0}, 0, lmdj::domain::kSixteenthTicks, 100}},
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
  LMDJ_CHECK(checkpoint.size() == 10);
  LMDJ_CHECK(checkpoint.at("contract") == "lmdj.project.v5");
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
      LMDJ_CHECK(encoded_pad.size() == 3);
      LMDJ_CHECK(encoded_pad.at("pad") == pad);
      LMDJ_CHECK(!encoded_pad.contains("id"));
      LMDJ_CHECK(encoded_pad.contains("playback"));
    }
  }
  LMDJ_CHECK(checkpoint.at("assets").is_array());
  LMDJ_CHECK(!checkpoint.contains("takes"));
  LMDJ_CHECK(checkpoint.at("patterns").is_array());
  LMDJ_CHECK(checkpoint.at("sequence_settings").at("quantize_enabled"));
  LMDJ_CHECK(checkpoint.at("sequence_settings").at("swing_percent") == 50);
  LMDJ_CHECK(checkpoint.at("pattern_slots").is_array());
  LMDJ_CHECK(
      checkpoint.at("pattern_slots").size() ==
      lmdj::domain::kPatternSlotCount);
  for (const auto& slot : checkpoint.at("pattern_slots")) {
    LMDJ_CHECK(slot.is_null());
  }
  LMDJ_CHECK(checkpoint.at("performances").is_array());
  LMDJ_CHECK(checkpoint.at("performances").empty());
  const auto& encoded_asset = checkpoint.at("assets").at(0);
  LMDJ_CHECK(encoded_asset.size() == 3);
  LMDJ_CHECK(encoded_asset.at("lineage").is_null());
  LMDJ_CHECK(!encoded_asset.contains("id"));
  LMDJ_CHECK(encoded_asset.at("asset_id") == asset_id.value());
  const auto& encoded_pattern = checkpoint.at("patterns").at(0);
  LMDJ_CHECK(encoded_pattern.size() == 3);
  LMDJ_CHECK(!encoded_pattern.contains("id"));
  LMDJ_CHECK(encoded_pattern.at("pattern_id") == pattern_id.value());
  LMDJ_CHECK(
      encoded_pattern.at("events").at(0).at("onset_tick") == 0);
  LMDJ_CHECK(
      encoded_pattern.at("events").at(0).at("duration_tick") == 240);

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

void test_v1_load_migrates_in_memory_and_first_mutation_writes_v4() {
  TempDirectory temp;
  const auto bundle = temp.path() / "migration.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto checkpoint_path = bundle / "history/checkpoints/0.json";
  write_bytes(
      checkpoint_path,
      lmdj::foundation::canonical_json(
          legacy_checkpoint(read_json(checkpoint_path), "lmdj.project.v1")) +
          "\n");
  const auto original_manifest = read_bytes(bundle / "manifest.json");
  const auto original_checkpoint =
      read_bytes(bundle / "history/checkpoints/0.json");

  const auto opened = store.load(bundle);
  LMDJ_CHECK(opened.has_value());
  LMDJ_CHECK(opened.value().contract == ProjectContract::v3);
  LMDJ_CHECK(opened.value().quantize_enabled);
  LMDJ_CHECK(opened.value().swing_percent == 50);
  LMDJ_CHECK(read_bytes(bundle / "manifest.json") == original_manifest);
  LMDJ_CHECK(
      read_bytes(bundle / "history/checkpoints/0.json") ==
      original_checkpoint);

  const UpdatePadPlayback command{
      meta("migrate-playback", opened.value().revision),
      PadSlotId{0, 0},
      PadPlayback{12, 144, TriggerMode::loop_toggle, -1200, true},
  };
  const auto committed = store.execute(bundle, command);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().state.contract == ProjectContract::v5);
  LMDJ_CHECK(committed.value().state.revision == opened.value().revision + 1);
  LMDJ_CHECK(
      committed.value().state.banks.at(0).at(0).playback == command.playback);

  const auto manifest = read_json(bundle / "manifest.json");
  const auto checkpoint = read_json(
      bundle / manifest.at("head_checkpoint").get<std::filesystem::path>());
  LMDJ_CHECK(checkpoint.at("contract") == "lmdj.project.v5");
  const auto& playback =
      checkpoint.at("banks").at(0).at("pads").at(0).at("playback");
  LMDJ_CHECK(playback.size() == 5);
  LMDJ_CHECK(playback.at("trim_start_frame") == 12);
  LMDJ_CHECK(playback.at("trim_end_frame") == 144);
  LMDJ_CHECK(playback.at("trigger_mode") == "loop_toggle");
  LMDJ_CHECK(playback.at("gain_millidb") == -1200);
  LMDJ_CHECK(playback.at("muted") == true);
  LMDJ_CHECK(
      read_bytes(bundle / "history/checkpoints/0.json") ==
      original_checkpoint);

  const auto replayed = store.execute(bundle, command);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state.revision == 1);

  auto changed_identity = command;
  changed_identity.meta.expected_revision = 1;
  const auto rejected_identity = store.execute(bundle, changed_identity);
  LMDJ_CHECK(!rejected_identity.has_value());
  LMDJ_CHECK(rejected_identity.error().code == ErrorCode::invalid_argument);

  auto stale = command;
  stale.meta = meta("stale-playback", 0);
  const auto conflict = store.execute(bundle, stale);
  LMDJ_CHECK(!conflict.has_value());
  LMDJ_CHECK(conflict.error().code == ErrorCode::revision_conflict);

  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value() == committed.value().state);
}

void test_v2_total_migration_discards_takes_and_is_byte_stable() {
  TempDirectory temp;
  const auto bundle = temp.path() / "v2-total-migration.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto checkpoint_path = bundle / "history/checkpoints/0.json";
  auto v2 = legacy_checkpoint(
      read_json(checkpoint_path), "lmdj.project.v2");
  const auto pattern_id = test_uuid("v2-migration-pattern");
  v2["takes"][test_uuid("discarded-take")] = {
      {"events",
       nlohmann::json::array(
           {{{"frame_offset", 42},
             {"slot", {{"bank", 0}, {"pad", 0}}},
             {"velocity", 90}}})},
      {"sample_rate", 48000},
  };
  v2["patterns"][pattern_id] = {
      {"bars", 1},
      {"events",
       nlohmann::json::array(
           {{{"slot", {{"bank", 0}, {"pad", 2}}},
             {"step", 3},
             {"velocity", 70}},
            {{"slot", {{"bank", 0}, {"pad", 1}}},
             {"step", 1},
             {"velocity", 80}},
            {{"slot", {{"bank", 0}, {"pad", 2}}},
             {"step", 3},
             {"velocity", 110}}})},
  };
  write_bytes(
      checkpoint_path, lmdj::foundation::canonical_json(v2) + "\n");
  const auto legacy_bytes = read_bytes(checkpoint_path);

  const auto migrated = store.load(bundle);
  LMDJ_CHECK(migrated.has_value());
  LMDJ_CHECK(migrated.value().contract == ProjectContract::v3);
  LMDJ_CHECK(migrated.value().quantize_enabled);
  LMDJ_CHECK(migrated.value().swing_percent == 50);
  const auto& events =
      migrated.value().patterns.at(PatternId{pattern_id}).events;
  LMDJ_CHECK(events.size() == 2);
  LMDJ_CHECK(events[0].onset_tick == 240);
  LMDJ_CHECK(events[0].duration_tick == 240);
  LMDJ_CHECK((events[0].slot == PadSlotId{0, 1}));
  LMDJ_CHECK(events[1].onset_tick == 720);
  LMDJ_CHECK(events[1].duration_tick == 240);
  LMDJ_CHECK(events[1].velocity == 110);
  LMDJ_CHECK(read_bytes(checkpoint_path) == legacy_bytes);

  const UpdateSequenceSettings command{
      meta("migrate-v2-settings", 0), {}, false, 75};
  const auto committed = store.execute(bundle, Command{command});
  LMDJ_CHECK(committed.has_value());
  const auto manifest = read_json(bundle / "manifest.json");
  const auto current_path =
      bundle / manifest.at("head_checkpoint").get<std::filesystem::path>();
  const auto first_current_bytes = read_bytes(current_path);
  const auto current = read_json(current_path);
  LMDJ_CHECK(current.at("contract") == "lmdj.project.v5");
  LMDJ_CHECK(!current.contains("takes"));
  LMDJ_CHECK(current.at("assets").is_array());
  LMDJ_CHECK(current.at("patterns").is_array());
  LMDJ_CHECK(
      current.at("patterns").at(0).at("events").at(0).at("onset_tick") == 240);
  LMDJ_CHECK(
      current.at("patterns").at(0).at("events").at(1).at("velocity") == 110);

  const auto replayed = store.execute(bundle, Command{command});
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(read_bytes(current_path) == first_current_bytes);
}

void test_tick_commands_round_trip_with_canonical_replay_identity() {
  TempDirectory temp;
  const auto bundle = temp.path() / "tick-command-round-trip.lmdj";
  auto initial = new_project();
  const auto pattern_id = PatternId{test_uuid("tick-command-pattern")};
  initial.patterns.emplace(pattern_id, Pattern{pattern_id, 1, {}});
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, initial).has_value());

  const Command command{MergePatternEvents{
      meta("tick-command-merge", 0),
      pattern_id,
      {
          {PadSlotId{1, 0}, 480, 120, 80},
          {PadSlotId{0, 1}, 0, 240, 90},
          {PadSlotId{1, 0}, 480, 300, 127},
      },
  }};
  const auto committed = store.execute(bundle, command);
  LMDJ_CHECK(committed.has_value());
  const auto& events = committed.value().state.patterns.at(pattern_id).events;
  LMDJ_CHECK(events.size() == 2);
  LMDJ_CHECK((events[0].slot == PadSlotId{0, 1}));
  LMDJ_CHECK((events[1].slot == PadSlotId{1, 0}));
  LMDJ_CHECK(events[1].duration_tick == 300);
  LMDJ_CHECK(events[1].velocity == 127);

  const auto before_replay = managed_bundle_snapshot(bundle);
  ProjectStore reopened_store;
  const auto replayed = reopened_store.execute(bundle, command);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state == committed.value().state);
  LMDJ_CHECK(managed_bundle_snapshot(bundle) == before_replay);
}

void test_sequence_flush_identity_is_durable_and_replayable_after_cleanup() {
  TempDirectory temp;
  const auto bundle = temp.path() / "sequence-flush-identity.lmdj";
  auto initial = new_project();
  const auto pattern_id = PatternId{test_uuid("sequence-flush-pattern")};
  const Pattern pattern{pattern_id, 1, {}};
  initial.patterns.emplace(pattern_id, pattern);
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, initial).has_value());
  SequenceJournal journal;
  const auto session_id = lmdj::foundation::SequenceSessionId{
      test_uuid("sequence-flush-session")};
  LMDJ_CHECK(
      journal
          .begin(
              bundle,
              session_id,
              pattern_id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              0)
          .has_value());
  const auto command_id = CommandId{test_uuid("sequence-flush-command")};
  const std::vector events{
      PatternEvent{PadSlotId{0, 0}, 0, 240, 100}};
  const auto pending = journal.append_flush(
      bundle, session_id, command_id, pattern_id, 0, events);
  LMDJ_CHECK(pending.has_value());
  const SequenceFlushIdentity identity{
      session_id, pending.value().flush_seq, command_id, pattern_id};
  const auto committed = store.execute_sequence_flush(bundle, identity);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(!committed.value().outcome.replayed);

  const auto transaction = read_json(
      bundle / "history/transactions" /
      ("1-" + command_id.value() + ".json"));
  LMDJ_CHECK(transaction.at("sequence_flush").at("session_id") ==
             session_id.value());
  LMDJ_CHECK(transaction.at("sequence_flush").at("flush_seq") == 0);
  LMDJ_CHECK(transaction.at("sequence_flush").at("command_id") ==
             command_id.value());
  LMDJ_CHECK(transaction.at("sequence_flush").at("pattern_id") ==
             pattern_id.value());
  LMDJ_CHECK(
      journal.remove_active_if_complete(bundle, session_id).has_value());

  ProjectStore restarted;
  const auto replayed = restarted.replay_sequence_flush(bundle, identity);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().has_value());
  LMDJ_CHECK(replayed.value()->outcome.replayed);
  LMDJ_CHECK(replayed.value()->outcome.state.revision == 1);
  LMDJ_CHECK(
      replayed.value()->outcome.state.patterns.at(pattern_id).events == events);
  const auto replayed_by_public_identity = restarted.replay_sequence_flush(
      bundle, session_id, command_id);
  LMDJ_CHECK(replayed_by_public_identity.has_value());
  LMDJ_CHECK(replayed_by_public_identity.value().has_value());
  LMDJ_CHECK(replayed_by_public_identity.value()->outcome.replayed);
  LMDJ_CHECK(
      replayed_by_public_identity.value()->identity == identity);
}

void test_active_sequence_journal_blocks_direct_authoring_admission() {
  TempDirectory temp;
  const auto bundle = temp.path() / "sequence-authoring-admission.lmdj";
  auto initial = new_project();
  const auto pattern_id = PatternId{test_uuid("admission-pattern")};
  const Pattern pattern{pattern_id, 1, {}};
  initial.patterns.emplace(pattern_id, pattern);
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, initial).has_value());
  SequenceJournal journal;
  const auto session_id = lmdj::foundation::SequenceSessionId{
      test_uuid("admission-session")};
  LMDJ_CHECK(
      journal
          .begin(
              bundle,
              session_id,
              pattern_id,
              pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(pattern),
              0)
          .has_value());

  const auto rejected = store.execute(
      bundle,
      Command{create_pattern(
          "admission-command", 0, "admission-second-pattern")});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      rejected.error().details.at("reason") == "sequence_session_active");
  LMDJ_CHECK(rejected.error().details.at("session_id") == session_id.value());
  LMDJ_CHECK(rejected.error().details.contains("remedy"));
  LMDJ_CHECK(store.load(bundle).value().revision == 0);
  const auto settings = store.execute(
      bundle,
      Command{UpdateSequenceSettings{
          meta("admission-settings", 0), 130, std::nullopt, std::nullopt}});
  LMDJ_CHECK(settings.has_value());
  LMDJ_CHECK(settings.value().state.revision == 1);
  const auto active = journal.read_active(bundle);
  LMDJ_CHECK(active.has_value());
  LMDJ_CHECK(active.value().expected_revision == 1);
}

void test_nonzero_revision_v1_history_opens_without_migration() {
  TempDirectory temp;
  const auto bundle = temp.path() / "historical-v1.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  LMDJ_CHECK(
      store.execute(
               bundle,
               Command{lmdj::domain::AssignPad{
                   meta("historical-v1-command", 0),
                   PadSlotId{0, 0},
                   std::nullopt,
               }})
          .has_value());

  const auto checkpoint_path = bundle / "history/checkpoints/1.json";
  auto historical = legacy_checkpoint(
      read_json(checkpoint_path), "lmdj.project.v1");
  write_bytes(
      checkpoint_path,
      lmdj::foundation::canonical_json(historical) + "\n");
  const auto initial_checkpoint = bundle / "history/checkpoints/0.json";
  write_bytes(
      initial_checkpoint,
      lmdj::foundation::canonical_json(legacy_checkpoint(
          read_json(initial_checkpoint), "lmdj.project.v1")) +
          "\n");
  const auto before = managed_bundle_snapshot(bundle);

  const auto opened = store.load(bundle);
  LMDJ_CHECK(opened.has_value());
  LMDJ_CHECK(opened.value().contract == ProjectContract::v3);
  LMDJ_CHECK(opened.value().revision == 1);
  LMDJ_CHECK(managed_bundle_snapshot(bundle) == before);
}

void test_v2_checkpoint_rejects_extra_playback_keys() {
  TempDirectory temp;
  const auto bundle = temp.path() / "v2-exact-keys.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  LMDJ_CHECK(
      store.execute(
               bundle,
               UpdatePadPlayback{
                   meta("v2-extra-key", 0),
                   PadSlotId{0, 0},
                   PadPlayback{},
               })
          .has_value());
  const auto checkpoint_path = bundle / "history/checkpoints/1.json";
  auto checkpoint = read_json(checkpoint_path);
  checkpoint["banks"][0]["pads"][0]["playback"]["unexpected"] = true;
  write_bytes(
      checkpoint_path,
      lmdj::foundation::canonical_json(checkpoint) + "\n");

  const auto rejected = store.load(bundle);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
}

void test_reset_pad_playback_persists_v2_defaults() {
  TempDirectory temp;
  const auto bundle = temp.path() / "reset-playback.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  LMDJ_CHECK(
      store.execute(
               bundle,
               UpdatePadPlayback{
                   meta("set-before-reset", 0),
                   PadSlotId{0, 3},
                   PadPlayback{4, 12, TriggerMode::gate, 6000, true},
               })
          .has_value());

  const auto reset = store.execute(
      bundle,
      ResetPadPlayback{meta("reset-playback", 1), PadSlotId{0, 3}});
  LMDJ_CHECK(reset.has_value());
  LMDJ_CHECK(reset.value().state.revision == 2);
  LMDJ_CHECK(reset.value().state.contract == ProjectContract::v5);
  LMDJ_CHECK(
      reset.value().state.banks.at(0).at(3).playback == PadPlayback{});
  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value() == reset.value().state);
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
  // A v3 body that declares v4 is missing the v4 carriers, and a v4 body that
  // declares v3 carries fields v3 has no room for. Both are refused.
  auto v3_body_declaring_v4 = v3_checkpoint(valid);
  v3_body_declaring_v4["contract"] = "lmdj.project.v4";
  auto v4_body_declaring_v3 = valid;
  v4_body_declaring_v3["contract"] = "lmdj.project.v3";
  auto invalid_uuid = valid;
  invalid_uuid["project_id"] =
      "00000000-0000-4000-8000-00000000000A";
  auto wrong_sample_rate = legacy_checkpoint(valid, "lmdj.project.v2");
  wrong_sample_rate["takes"][test_uuid("take-1")] = {
      {"events", nlohmann::json::array()},
      {"sample_rate", 44100},
  };
  auto extra_property = valid;
  extra_property["unexpected"] = true;
  const std::array invalid_checkpoints{
      old_private,
      missing_contract,
      v3_body_declaring_v4,
      v4_body_declaring_v3,
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

  const auto manifest = read_json(bundle / "manifest.json");
  const auto transaction_path =
      bundle / manifest.at("transactions").at(0).get<std::filesystem::path>();
  auto transaction = read_json(transaction_path);
  LMDJ_CHECK(transaction.at("command").at("asset").at("lineage").is_null());
  transaction.at("command").at("asset").erase("lineage");
  write_bytes(
      transaction_path,
      lmdj::foundation::canonical_json(transaction) + "\n");
  const auto legacy_replayed = store.import_artifact(
      bundle,
      ProjectStore::ImportArtifactRequest{
          meta("import-1", 0),
          AssetId{test_uuid("asset-1")},
          source,
          "audio/wav",
      });
  LMDJ_CHECK(legacy_replayed.has_value());
  LMDJ_CHECK(legacy_replayed.value().replayed);
  LMDJ_CHECK(legacy_replayed.value().state.revision == 2);
}

struct OwnedArtifactFixture {
  std::filesystem::path bundle{"memory/owner.lmdj"};
  std::shared_ptr<MemoryStoragePlatform> platform =
      std::make_shared<MemoryStoragePlatform>();
  ProjectStore store{platform};
  lmdj::domain::ProjectState project = new_project();
  AssetId asset{test_uuid("owner-asset")};
  std::vector<std::byte> bytes{std::byte{'a'}, std::byte{'b'}};
  lmdj::foundation::ArtifactRef artifact;
  OwnedArtifactFixture() {
    LMDJ_CHECK(store.create(bundle, project).has_value());
    const auto imported = store.import_artifact_bytes(bundle,
        {meta("owner-import", 0), asset, "audio/wav", bytes});
    LMDJ_CHECK(imported.has_value());
    artifact = imported.value().state.assets.at(asset).artifact;
  }
};

void test_owner_read_holds_one_lease_and_never_writes() {
  OwnedArtifactFixture f;
  const auto writes = f.platform->write_calls;
  const auto acquisitions = f.platform->writer_acquisitions;
  f.platform->require_read_lease = true;
  const auto read = f.store.read_asset_artifact(
      f.bundle, f.project.id, f.asset, f.artifact);
  LMDJ_CHECK(read.has_value());
  LMDJ_CHECK(read.value() == f.bytes);
  LMDJ_CHECK(f.platform->writer_acquisitions == acquisitions + 1);
  LMDJ_CHECK(!f.platform->writer_held);
  LMDJ_CHECK(f.platform->write_calls == writes);
}

void test_owner_read_refuses_unowned_identity(int field) {
  OwnedArtifactFixture f;
  auto project = f.project.id;
  auto asset = f.asset;
  auto artifact = f.artifact;
  if (field == 0) project = ProjectId{test_uuid("other-owner-project")};
  if (field == 1) asset = AssetId{test_uuid("other-owner-asset")};
  if (field == 2) artifact.sha256 = std::string(64, 'f');
  if (field == 3) artifact.media_type = "application/octet-stream";
  if (field == 4) ++artifact.byte_length;
  const auto writes = f.platform->write_calls;
  f.platform->read_paths.clear();
  const auto read = f.store.read_asset_artifact(f.bundle, project, asset, artifact);
  LMDJ_CHECK(std::none_of(f.platform->read_paths.begin(), f.platform->read_paths.end(),
      [](const auto& path) { return path.parent_path().filename() == "assets"; }));
  LMDJ_CHECK(!read.has_value());
  LMDJ_CHECK(read.error().code == ErrorCode::not_found);
  LMDJ_CHECK(f.platform->write_calls == writes);
}

void test_owner_read_reports_byte_mismatch(bool length) {
  OwnedArtifactFixture f;
  if (length) f.bytes.push_back(std::byte{'x'});
  else f.bytes[0] = std::byte{'x'};
  LMDJ_CHECK(f.platform->replace_complete(
      f.bundle / "assets" / (f.artifact.sha256 + ".wav"), f.bytes).has_value());
  const auto writes = f.platform->write_calls;
  const auto read = f.store.read_asset_artifact(
      f.bundle, f.project.id, f.asset, f.artifact);
  LMDJ_CHECK(!read.has_value());
  LMDJ_CHECK(read.error().details.at("storage_condition") == "artifact_mismatch");
  LMDJ_CHECK(f.platform->write_calls == writes);
}

void test_owner_read_does_not_read_unselected_audio() {
  OwnedArtifactFixture f;
  const AssetId other{test_uuid("unselected-asset")};
  auto other_bytes = f.bytes;
  other_bytes[0] = std::byte{'c'};
  const auto imported = f.store.import_artifact_bytes(f.bundle,
      {meta("unselected-import", 1), other, "audio/wav", other_bytes});
  LMDJ_CHECK(imported.has_value());
  const auto other_path = f.bundle / "assets" /
      (imported.value().state.assets.at(other).artifact.sha256 + ".wav");
  other_bytes[0] = std::byte{'d'};
  LMDJ_CHECK(f.platform->replace_complete(other_path, other_bytes).has_value());
  f.platform->read_paths.clear();
  const auto selected = f.store.read_asset_artifact(f.bundle, f.project.id, f.asset, f.artifact);
  LMDJ_CHECK(selected.has_value() && selected.value() == f.bytes);
  LMDJ_CHECK(std::find(f.platform->read_paths.begin(), f.platform->read_paths.end(), other_path) ==
      f.platform->read_paths.end());
  // Normal Project loading still validates all source Assets.
  LMDJ_CHECK(!f.store.load(f.bundle).has_value());
}

void test_owner_read_refuses_busy_project() {
  OwnedArtifactFixture f;
  auto lease = f.platform->acquire_writer(f.bundle);
  LMDJ_CHECK(lease.has_value());
  const auto read = f.store.read_asset_artifact(
      f.bundle, f.project.id, f.asset, f.artifact);
  LMDJ_CHECK(!read.has_value());
  LMDJ_CHECK(read.error().details.at("storage_condition") == "project_busy");
}

void test_owner_read_preserves_uncommitted_files() {
  OwnedArtifactFixture f;
  const auto orphan = f.bundle / "history/checkpoints/2.json";
  LMDJ_CHECK(f.platform->create_immutable(orphan, f.bytes).has_value());
  const auto writes = f.platform->write_calls;
  LMDJ_CHECK(f.store.read_asset_artifact(
      f.bundle, f.project.id, f.asset, f.artifact).has_value());
  LMDJ_CHECK(f.platform->exists(orphan).value());
  LMDJ_CHECK(f.platform->write_calls == writes);
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

void test_asset_lineage_is_refused_on_a_v3_project_on_disk() {
  // Asset Lineage has no carrier in lmdj.project.v3, so importing with
  // Lineage into a Project that declares v3 on disk still fails closed. The
  // Project has to be an explicit v3 fixture: a Project this Build creates
  // declares v4 and would accept the Lineage.
  TempDirectory temp;
  const auto bundle = temp.path() / "v3-lineage.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto checkpoint_path = bundle / "history/checkpoints/0.json";
  write_bytes(
      checkpoint_path,
      lmdj::foundation::canonical_json(
          v3_checkpoint(read_json(checkpoint_path))) +
          "\n");
  const auto opened = store.load(bundle);
  LMDJ_CHECK(opened.has_value());
  LMDJ_CHECK(opened.value().contract == ProjectContract::v3);

  std::vector<std::byte> sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
  };
  ProjectStore::ImportAssignSampleBytesRequest request{
      meta("v3-lineage-import", 0),
      PadSlotId{2, 7},
      AssetId{test_uuid("v3-lineage-asset")},
      "audio/wav",
      sample,
  };
  request.lineage = AssetLineage{
      lmdj::domain::AssetArtifactLineageSource{std::string(64, 'a'), 0},
      lmdj::domain::ResampleLineageDerivation{
          {0, 1},
          PerformanceId{"40000000-0000-4000-8000-000000000001"}},
  };
  const auto rejected = store.import_assign_sample_bytes(bundle, request);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);

  const auto unchanged = store.load(bundle);
  LMDJ_CHECK(unchanged.has_value());
  LMDJ_CHECK(unchanged.value().revision == 0);
  LMDJ_CHECK(unchanged.value().assets.empty());
  LMDJ_CHECK(unchanged.value().contract == ProjectContract::v3);
}

void test_a_v3_project_is_promoted_to_v4_on_its_first_persist() {
  // Opening a v3 Project never rewrites it, but the first ordinary write
  // persists it as v4, because every Project this Build persists is written
  // at lmdj.project.v4.
  TempDirectory temp;
  const auto bundle = temp.path() / "v3-promotion.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto checkpoint_path = bundle / "history/checkpoints/0.json";
  write_bytes(
      checkpoint_path,
      lmdj::foundation::canonical_json(
          v3_checkpoint(read_json(checkpoint_path))) +
          "\n");
  const auto v3_bytes = read_bytes(checkpoint_path);
  const auto original_manifest = read_bytes(bundle / "manifest.json");

  const auto opened = store.load(bundle);
  LMDJ_CHECK(opened.has_value());
  LMDJ_CHECK(opened.value().contract == ProjectContract::v3);
  LMDJ_CHECK(read_bytes(checkpoint_path) == v3_bytes);
  LMDJ_CHECK(read_bytes(bundle / "manifest.json") == original_manifest);

  const auto committed = store.execute(
      bundle,
      UpdatePadPlayback{
          meta("promote-on-write", 0),
          PadSlotId{0, 0},
          PadPlayback{12, 144, TriggerMode::loop_toggle, -1200, true},
      });
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().state.contract == ProjectContract::v5);

  const auto manifest = read_json(bundle / "manifest.json");
  const auto head = read_json(
      bundle / manifest.at("head_checkpoint").get<std::filesystem::path>());
  LMDJ_CHECK(head.at("contract") == "lmdj.project.v5");
  LMDJ_CHECK(head.at("pattern_slots").is_array());
  LMDJ_CHECK(head.at("performances").is_array());
  // Checkpoint zero is still the v3 bytes the Project arrived with.
  LMDJ_CHECK(read_bytes(checkpoint_path) == v3_bytes);

  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value().contract == ProjectContract::v5);
  LMDJ_CHECK(reopened.value() == committed.value().state);
}

void test_import_assign_sample_bytes_commits_one_revision_and_replays_exactly() {
  TempDirectory temp;
  const auto bundle = temp.path() / "sample-import.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  std::vector<std::byte> sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
      std::byte{0x10}, std::byte{0x20}, std::byte{0x30}, std::byte{0x40},
  };
  const auto request = ProjectStore::ImportAssignSampleBytesRequest{
      meta("sample-import", 0),
      PadSlotId{2, 7},
      AssetId{test_uuid("sample-asset")},
      "audio/wav",
      sample,
  };

  const auto imported = store.import_assign_sample_bytes(bundle, request);
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(!imported.value().replayed);
  LMDJ_CHECK(imported.value().state.contract == ProjectContract::v5);
  LMDJ_CHECK(imported.value().state.revision == 1);
  LMDJ_CHECK(imported.value().state.assets.size() == 1);
  LMDJ_CHECK(
      !imported.value().state.assets.at(request.asset_id).lineage.has_value());
  const auto& pad = imported.value().state.banks.at(2).at(7);
  LMDJ_CHECK(pad.asset_id == request.asset_id);
  LMDJ_CHECK(pad.playback == PadPlayback{});
  const auto artifact = imported.value().state.assets.at(request.asset_id).artifact;
  const auto expected_bytes = sample;
  sample.back() = std::byte{0xff};
  const auto stored = store.read_artifact(bundle, artifact);
  LMDJ_CHECK(stored.has_value());
  LMDJ_CHECK(stored.value() == expected_bytes);
  sample.back() = std::byte{0x40};

  const auto manifest = read_json(bundle / "manifest.json");
  const auto transaction_path =
      bundle / manifest.at("transactions").at(0).get<std::filesystem::path>();
  auto transaction = read_json(transaction_path);
  LMDJ_CHECK(transaction.at("command").at("asset").at("lineage").is_null());
  transaction.at("command").at("asset").erase("lineage");
  write_bytes(
      transaction_path,
      lmdj::foundation::canonical_json(transaction) + "\n");

  const auto replayed = store.import_assign_sample_bytes(bundle, request);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state.revision == 1);

  auto changed_slot = request;
  changed_slot.slot = PadSlotId{2, 8};
  const auto rejected_identity =
      store.import_assign_sample_bytes(bundle, changed_slot);
  LMDJ_CHECK(!rejected_identity.has_value());
  LMDJ_CHECK(rejected_identity.error().code == ErrorCode::invalid_argument);

  auto conflict = request;
  conflict.meta = meta("sample-conflict", 0);
  conflict.asset_id = AssetId{test_uuid("sample-conflict-asset")};
  const auto rejected_conflict =
      store.import_assign_sample_bytes(bundle, conflict);
  LMDJ_CHECK(!rejected_conflict.has_value());
  LMDJ_CHECK(rejected_conflict.error().code == ErrorCode::revision_conflict);
  const auto unchanged = store.load(bundle);
  LMDJ_CHECK(unchanged.has_value());
  LMDJ_CHECK(unchanged.value() == imported.value().state);
}

void test_import_assign_sample_bytes_persists_lineage_and_collides_on_change() {
  TempDirectory temp;
  const auto bundle = temp.path() / "derived-sample-import.lmdj";
  auto initial = new_project();
  initial.contract = ProjectContract::v4;
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, initial).has_value());
  const std::vector<std::byte> sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
      std::byte{0x11}, std::byte{0x22}, std::byte{0x33}, std::byte{0x44},
  };
  const AssetLineage lineage{
      lmdj::domain::AssetArtifactLineageSource{std::string(64, 'a'), 7},
      lmdj::domain::ResampleLineageDerivation{
          {10, 20},
          PerformanceId{"40000000-0000-4000-8000-000000000001"}},
  };
  const auto request = ProjectStore::ImportAssignSampleBytesRequest{
      meta("derived-sample-import", 0),
      PadSlotId{1, 4},
      AssetId{test_uuid("derived-sample-asset")},
      "audio/wav",
      sample,
      std::nullopt,
      lineage,
  };

  const auto imported = store.import_assign_sample_bytes(bundle, request);
  LMDJ_CHECK(imported.has_value());
  LMDJ_CHECK(
      imported.value().state.assets.at(request.asset_id).lineage == lineage);
  LMDJ_CHECK(
      imported.value().state.banks.at(1).at(4).asset_id == request.asset_id);
  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value().assets.at(request.asset_id).lineage == lineage);

  const auto manifest = read_json(bundle / "manifest.json");
  const auto transaction = read_json(
      bundle / manifest.at("transactions").at(0).get<std::filesystem::path>());
  LMDJ_CHECK(
      transaction.at("command").at("asset").at("lineage") ==
      lmdj::domain::asset_lineage_json(lineage));

  const auto replayed = store.import_assign_sample_bytes(bundle, request);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state.revision == 1);

  auto changed = request;
  std::get<lmdj::domain::AssetArtifactLineageSource>(
      changed.lineage->source)
      .project_revision = 8;
  const auto collision = store.import_assign_sample_bytes(bundle, changed);
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::invalid_argument);
  const auto unchanged = store.load(bundle);
  LMDJ_CHECK(unchanged.has_value());
  LMDJ_CHECK(unchanged.value() == imported.value().state);
}

void test_import_assign_sample_bytes_obeys_generic_artifact_safety_boundary() {
  auto platform = std::make_shared<MemoryStoragePlatform>();
  ProjectStore store{platform};
  const auto missing_bundle =
      std::filesystem::path{"/workspace/missing-project.lmdj"};
  constexpr std::size_t artifact_safety_limit = 64U * 1024U * 1024U;
  std::vector<std::byte> bytes(artifact_safety_limit + 1U, std::byte{0x2a});
  const auto import = [&](std::string_view command_label, std::size_t length) {
    return store.import_assign_sample_bytes(
        missing_bundle,
        ProjectStore::ImportAssignSampleBytesRequest{
            meta(std::string{command_label}, 0),
            PadSlotId{0, 0},
            AssetId{test_uuid(std::string{command_label} + "-asset")},
            "audio/wav",
            std::span<const std::byte>{bytes}.first(length),
        });
  };

  const auto below = import("sample-boundary-below", artifact_safety_limit - 1U);
  LMDJ_CHECK(!below.has_value());
  LMDJ_CHECK(below.error().code == ErrorCode::invalid_project);
  const auto at = import("sample-boundary-at", artifact_safety_limit);
  LMDJ_CHECK(!at.has_value());
  LMDJ_CHECK(at.error().code == ErrorCode::invalid_project);
  const auto acquisitions_before_over = platform->writer_acquisitions;

  const auto over = import("sample-boundary-over", bytes.size());
  LMDJ_CHECK(!over.has_value());
  LMDJ_CHECK(over.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(platform->writer_acquisitions == acquisitions_before_over);
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
  // Symlink handling is asserted separately by
  // test_json_reads_reject_symlinked_files: read_json() goes through the
  // storage platform, so O_NOFOLLOW belongs to the platform implementation
  // rather than to this module, and the file-level refusal surfaces as
  // invalid_project.
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

void test_json_reads_reject_symlinked_files() {
  // File-level complement of
  // test_symlinked_managed_directory_is_rejected_before_recovery and of
  // read_artifact's symlink coverage: manifest and checkpoint reads go
  // through the same storage platform read_complete(), whose native
  // implementation opens the final component with O_NOFOLLOW and maps the
  // refusal to invalid_project — the symmetry machine task C4 asked for.
  TempDirectory temp;
  const auto bundle = temp.path() / "json-symlink.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  const auto external = temp.path() / "external.json";
  write_bytes(external, "{}");

  const auto manifest = bundle / "manifest.json";
  const auto manifest_bytes = read_bytes(manifest);
  std::filesystem::remove(manifest);
  std::filesystem::create_symlink(external, manifest);
  const auto manifest_result = store.load(bundle);
  LMDJ_CHECK(!manifest_result.has_value());
  LMDJ_CHECK(manifest_result.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(read_bytes(external) == "{}");
  std::filesystem::remove(manifest);
  write_bytes(manifest, manifest_bytes);

  const auto checkpoint = bundle / "history/checkpoints/0.json";
  const auto checkpoint_bytes = read_bytes(checkpoint);
  std::filesystem::remove(checkpoint);
  std::filesystem::create_symlink(external, checkpoint);
  const auto checkpoint_result = store.load(bundle);
  LMDJ_CHECK(!checkpoint_result.has_value());
  LMDJ_CHECK(
      checkpoint_result.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(read_bytes(external) == "{}");
  std::filesystem::remove(checkpoint);
  write_bytes(checkpoint, checkpoint_bytes);

  LMDJ_CHECK(store.load(bundle).has_value());
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

void test_pattern_slots_round_trip_validate_and_preserve_command_identity() {
  TempDirectory temp;
  const auto bundle = temp.path() / "pattern-slots.lmdj";
  auto initial = new_project();
  initial.contract = ProjectContract::v4;
  const PatternId pattern1{
      "30000000-0000-4000-8000-000000000001"};
  const PatternId pattern2{
      "30000000-0000-4000-8000-000000000002"};
  initial.patterns.emplace(pattern1, Pattern{pattern1, 1, {}});
  initial.patterns.emplace(pattern2, Pattern{pattern2, 1, {}});

  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, initial).has_value());
  const auto created = store.load(bundle);
  LMDJ_CHECK(created.has_value());
  LMDJ_CHECK(created.value().pattern_slots == initial.pattern_slots);

  const Command assign{AssignPatternSlot{
      meta("pattern-slot-assign", 0), 0, pattern1}};
  const auto assigned = store.execute(bundle, assign);
  LMDJ_CHECK(assigned.has_value());
  LMDJ_CHECK(assigned.value().state.revision == 1);
  LMDJ_CHECK(assigned.value().state.pattern_slots.at(0) == pattern1);

  const auto replayed = store.execute(bundle, assign);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state.revision == 1);

  const Command collision{AssignPatternSlot{
      meta("pattern-slot-assign", 0),
      1,
      pattern2}};
  const auto rejected_collision = store.execute(bundle, collision);
  LMDJ_CHECK(!rejected_collision.has_value());
  LMDJ_CHECK(
      rejected_collision.error().code == ErrorCode::invalid_argument);

  const auto settings = store.execute(
      bundle,
      Command{UpdateSequenceSettings{
          meta("pattern-slot-settings", 1), 121, {}, {}}});
  LMDJ_CHECK(settings.has_value());
  LMDJ_CHECK(settings.value().state.contract == ProjectContract::v5);
  LMDJ_CHECK(settings.value().state.pattern_slots.at(0) == pattern1);

  const auto moved = store.execute(
      bundle,
      Command{MovePatternSlot{
          meta("pattern-slot-move", 2), 0, 2}});
  LMDJ_CHECK(moved.has_value());
  LMDJ_CHECK(moved.value().state.revision == 3);
  LMDJ_CHECK(moved.value().state.pattern_slots.at(2) == pattern1);

  const auto cleared = store.execute(
      bundle,
      Command{ClearPatternSlot{
          meta("pattern-slot-clear", 3), 2}});
  LMDJ_CHECK(cleared.has_value());
  LMDJ_CHECK(cleared.value().state.revision == 4);
  LMDJ_CHECK(!cleared.value().state.pattern_slots.at(2).has_value());

  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value() == cleared.value().state);

  const auto manifest = read_json(bundle / "manifest.json");
  std::vector<std::string> transaction_types;
  for (const auto& relative : manifest.at("transactions")) {
    transaction_types.push_back(
        read_json(bundle / relative.get<std::filesystem::path>())
            .at("command")
            .at("type")
            .get<std::string>());
  }
  LMDJ_CHECK(
      transaction_types ==
      (std::vector<std::string>{
          "AssignPatternSlot",
          "UpdateSequenceSettings",
          "MovePatternSlot",
          "ClearPatternSlot"}));

  const auto checkpoint_path =
      bundle / manifest.at("head_checkpoint").get<std::filesystem::path>();
  const auto valid_checkpoint = read_json(checkpoint_path);
  const auto invalid_slots = read_json(
      std::filesystem::path{__FILE__}
              .parent_path()
              .parent_path()
              .parent_path() /
      "fixtures/contracts/project-v4-invalid-pattern-slots.json");
  const auto write_and_reject = [&](nlohmann::json malformed) {
    write_bytes(
        checkpoint_path,
        lmdj::foundation::canonical_json(malformed) + "\n");
    const auto rejected = store.load(bundle);
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  };

  auto wrong_length = valid_checkpoint;
  wrong_length["pattern_slots"] = invalid_slots.at("wrong_length");
  write_and_reject(std::move(wrong_length));

  auto invalid_id = valid_checkpoint;
  invalid_id["pattern_slots"] = invalid_slots.at("invalid_pattern_id");
  write_and_reject(std::move(invalid_id));

  auto missing_pattern = valid_checkpoint;
  missing_pattern["pattern_slots"] = invalid_slots.at("missing_pattern");
  write_and_reject(std::move(missing_pattern));

  auto duplicate_pattern = valid_checkpoint;
  duplicate_pattern["pattern_slots"] = invalid_slots.at("duplicate_pattern");
  write_and_reject(std::move(duplicate_pattern));

  write_bytes(
      checkpoint_path,
      lmdj::foundation::canonical_json(valid_checkpoint) + "\n");
  LMDJ_CHECK(store.load(bundle).has_value());
}

void test_capability_lineage_persists_and_replay_compares_all_evidence() {
  TempDirectory temp;
  const auto bundle = temp.path() / "slice-lineage.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto encoded = nlohmann::json::parse(R"JSON(
{
  "source": {
    "kind": "asset_artifact",
    "artifact_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "project_revision": 7
  },
  "derivation": {
    "kind": "capability_adoption",
    "capability": {
      "id": "sample.slice.v1",
      "contract": "lmdj.capability.v2",
      "version": "1.0.0"
    },
    "provider": {
      "id": "local.sample.slice",
      "version": "1.0.0",
      "artifact_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    },
    "model_identity": null,
    "parameters_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "attempt_id": "10000000-0000-4000-8000-000000000001",
    "source_asset_id": "20000000-0000-4000-8000-000000000002",
    "output_artifact": {
      "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "media_type": "application/json",
      "byte_length": 128
    },
    "recipe": {
      "kind": "slice_interval_v1",
      "start_frame": 10,
      "end_frame": 100,
      "frame_rate": 48000
    }
  }
}
)JSON");
  const auto lineage = lmdj::domain::asset_lineage_from_json(encoded);
  LMDJ_CHECK(lineage.has_value());
  const std::vector<std::byte> materialized{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'}};
  ProjectStore::ImportAssignSampleBytesRequest request{
      meta("slice-lineage-import", 0), PadSlotId{0, 0},
      AssetId{test_uuid("slice-lineage-result")}, "audio/wav", materialized,
      std::nullopt, lineage.value()};
  const auto committed = store.import_assign_sample_bytes(bundle, request);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(committed.value().state.revision == 1);
  const auto reopened = store.load(bundle);
  LMDJ_CHECK(reopened.has_value());
  LMDJ_CHECK(reopened.value() == committed.value().state);
  const auto& asset = reopened.value().assets.at(request.asset_id);
  LMDJ_CHECK(asset.lineage == lineage.value());
  LMDJ_CHECK(asset.artifact.sha256 !=
             std::get<lmdj::domain::AssetArtifactLineageSource>(lineage.value().source).artifact_sha256);
  // This is the existing internal import command receipt, not AdoptCandidates replay.
  const auto replay = store.import_assign_sample_bytes(bundle, request);
  LMDJ_CHECK(replay.has_value());
  LMDJ_CHECK(replay.value().replayed);
  LMDJ_CHECK(replay.value().state == reopened.value());
  const std::vector<std::pair<std::string, nlohmann::json>> mutations{
      {"/source/artifact_sha256", std::string(64, 'e')},
      {"/source/project_revision", 8},
      {"/derivation/capability/version", "1.1.0"},
      {"/derivation/provider/id", "another.provider"},
      {"/derivation/provider/version", "1.1.0"},
      {"/derivation/provider/artifact_sha256", std::string(64, 'e')},
      {"/derivation/model_identity", {{"id", "model"}, {"version", "1"},
                                     {"artifact_sha256", std::string(64, 'e')}}},
      {"/derivation/parameters_sha256", std::string(64, 'e')},
      {"/derivation/attempt_id", test_uuid("another-attempt")},
      {"/derivation/source_asset_id", test_uuid("another-source")},
      {"/derivation/output_artifact/sha256", std::string(64, 'e')},
      {"/derivation/output_artifact/byte_length", 129},
      {"/derivation/recipe/start_frame", 11},
      {"/derivation/recipe/end_frame", 101},
      {"/derivation/recipe/frame_rate", 44100},
  };
  for (const auto& [path, value] : mutations) {
    auto changed_json = encoded;
    changed_json[nlohmann::json::json_pointer{path}] = value;
    auto changed = request;
    const auto parsed = lmdj::domain::asset_lineage_from_json(changed_json);
    LMDJ_CHECK(parsed.has_value());
    changed.lineage = parsed.value();
    const auto collision = store.import_assign_sample_bytes(bundle, changed);
    LMDJ_CHECK(!collision.has_value());
    LMDJ_CHECK(collision.error().code == ErrorCode::invalid_argument);
    LMDJ_CHECK(store.load(bundle).value() == reopened.value());
  }
  const auto manifest = read_json(bundle / "manifest.json");
  const auto head_path = bundle / manifest.at("head_checkpoint").get<std::string>();
  auto head = read_json(head_path);
  LMDJ_CHECK(head["assets"][0]["lineage"] == encoded);
  head["contract"] = "lmdj.project.v4";
  write_bytes(head_path, head.dump());
  LMDJ_CHECK(!store.load(bundle).has_value());
}

void test_v4_lineage_migration_retains_old_variant_evidence() {
  for (bool soundset : {false, true}) {
    TempDirectory temp;
    const auto bundle = temp.path() / "legacy-lineage.lmdj";
    ProjectStore store;
    LMDJ_CHECK(store.create(bundle, new_project()).has_value());
    const auto zero_path = bundle / "history/checkpoints/0.json";
    auto zero = read_json(zero_path);
    zero["contract"] = "lmdj.project.v4";
    write_bytes(zero_path, zero.dump());
    LMDJ_CHECK(store.load(bundle).value().contract == ProjectContract::v4);
    AssetLineage lineage{
        lmdj::domain::AssetArtifactLineageSource{std::string(64, 'a'), 7},
        lmdj::domain::ResampleLineageDerivation{
            {10, 20}, PerformanceId{test_uuid("legacy-performance")}}};
    if (soundset) {
      lineage.source = lmdj::domain::SoundSetLineageSource{
          test_uuid("legacy-set"), "1.2.0", std::string(64, 'b'), 5, std::string(64, 'c')};
      lineage.derivation = lmdj::domain::SoundSetInstallLineageDerivation{};
    }
    const std::vector<std::byte> sample{std::byte{0x01}};
    const ProjectStore::ImportAssignSampleBytesRequest request{
        meta("legacy-lineage", 0), PadSlotId{0, 0}, AssetId{test_uuid("legacy-result")},
        "audio/wav", sample, std::nullopt, lineage};
    const auto saved = store.import_assign_sample_bytes(bundle, request);
    LMDJ_CHECK(saved.has_value());
    LMDJ_CHECK(saved.value().state.contract == ProjectContract::v5);
    const auto reopened = store.load(bundle);
    LMDJ_CHECK(reopened.has_value());
    LMDJ_CHECK(reopened.value() == saved.value().state);
    LMDJ_CHECK(reopened.value().assets.at(request.asset_id).lineage == lineage);
    LMDJ_CHECK(store.import_assign_sample_bytes(bundle, request).value().replayed);
    // A real persisted v4 Asset already has lineage before migration starts.
    const auto manifest = read_json(bundle / "manifest.json");
    const auto head_path = bundle / manifest.at("head_checkpoint").get<std::string>();
    auto head = read_json(head_path);
    head["contract"] = "lmdj.project.v4";
    const auto old_bytes = head.dump();
    write_bytes(head_path, old_bytes);
    const auto old = store.load(bundle);
    LMDJ_CHECK(old.has_value());
    LMDJ_CHECK(old.value().contract == ProjectContract::v4);
    LMDJ_CHECK(old.value().assets.at(request.asset_id).lineage == lineage);
    LMDJ_CHECK(read_bytes(head_path) == old_bytes);
    const auto migrated = store.execute(bundle, Command{UpdateSequenceSettings{
        meta("promote-v4-lineage", 1), {}, false, 75}});
    LMDJ_CHECK(migrated.has_value());
    LMDJ_CHECK(migrated.value().state.contract == ProjectContract::v5);
    LMDJ_CHECK(migrated.value().state.assets.at(request.asset_id).lineage == lineage);
    LMDJ_CHECK(store.load(bundle).value() == migrated.value().state);
  }
}

}  // namespace

int main() {
  try {
    test_capability_lineage_persists_and_replay_compares_all_evidence();
    test_v4_lineage_migration_retains_old_variant_evidence();
    test_common_transactions_use_semantic_storage_obligations();
    test_default_store_remains_copy_list_initializable();
    test_canonical_checkpoint_round_trip_and_bundle_shape();
    test_v1_load_migrates_in_memory_and_first_mutation_writes_v4();
    test_v2_total_migration_discards_takes_and_is_byte_stable();
    test_tick_commands_round_trip_with_canonical_replay_identity();
    test_sequence_flush_identity_is_durable_and_replayable_after_cleanup();
    test_active_sequence_journal_blocks_direct_authoring_admission();
    test_nonzero_revision_v1_history_opens_without_migration();
    test_v2_checkpoint_rejects_extra_playback_keys();
    test_reset_pad_playback_persists_v2_defaults();
    test_persisted_checkpoints_reject_non_contract_shapes();
    test_create_removes_exact_stale_checkpoint_temp();
    test_create_resumes_manifest_after_valid_checkpoint_publish();
    test_create_rejects_mismatched_existing_initial_checkpoint();
    test_committed_transactions_replay_to_manifest_head();
    test_imported_assets_are_content_addressed_and_deduplicated();
    test_owner_read_holds_one_lease_and_never_writes();
    for (int field = 0; field < 5; ++field) test_owner_read_refuses_unowned_identity(field);
    test_owner_read_reports_byte_mismatch(false);
    test_owner_read_reports_byte_mismatch(true);
    test_owner_read_does_not_read_unselected_audio();
    test_owner_read_refuses_busy_project();
    test_owner_read_preserves_uncommitted_files();
    test_byte_backed_import_publishes_immutable_artifact_without_staging();
    test_import_assign_sample_bytes_commits_one_revision_and_replays_exactly();
    test_asset_lineage_is_refused_on_a_v3_project_on_disk();
    test_a_v3_project_is_promoted_to_v4_on_its_first_persist();
    test_import_assign_sample_bytes_persists_lineage_and_collides_on_change();
    test_import_assign_sample_bytes_obeys_generic_artifact_safety_boundary();
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
    test_json_reads_reject_symlinked_files();
    test_independent_platform_reports_busy_until_release();
    test_artifact_reads_are_bounded_symlink_safe_and_integrity_verified();
    test_artifact_read_rejects_symlinked_intermediate_directory();
    test_pattern_slots_round_trip_validate_and_preserve_command_identity();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project store tests: PASS\n";
  return 0;
}
