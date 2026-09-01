#include <algorithm>
#include <array>
#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <set>
#include <string>
#include <string_view>

#include <nlohmann/json.hpp>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CreatePattern;
using lmdj::domain::AssetLineage;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::PerformanceId;
using lmdj::domain::ProjectContract;
using lmdj::domain::UpdateSequenceSettings;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::SequenceJournal;
using lmdj::project_io::SequenceSessionState;
using lmdj::project_io::testing::FaultPoint;

enum class Boundary {
  before_manifest_commit,
};

struct FaultCase {
  FaultPoint point;
  std::string_view name;
  Boundary boundary;
};

constexpr std::array kCases{
    FaultCase{
        FaultPoint::artifact_temp_sync,
        "artifact_temp_sync",
        Boundary::before_manifest_commit,
    },
    FaultCase{
        FaultPoint::artifact_publish,
        "artifact_publish",
        Boundary::before_manifest_commit,
    },
    FaultCase{
        FaultPoint::transaction_temp_sync,
        "transaction_temp_sync",
        Boundary::before_manifest_commit,
    },
    FaultCase{
        FaultPoint::transaction_publish,
        "transaction_publish",
        Boundary::before_manifest_commit,
    },
    FaultCase{
        FaultPoint::checkpoint_temp_sync,
        "checkpoint_temp_sync",
        Boundary::before_manifest_commit,
    },
    FaultCase{
        FaultPoint::checkpoint_publish,
        "checkpoint_publish",
        Boundary::before_manifest_commit,
    },
    FaultCase{
        FaultPoint::manifest_temp_sync,
        "manifest_temp_sync",
        Boundary::before_manifest_commit,
    },
    FaultCase{
        FaultPoint::manifest_publish,
        "manifest_publish",
        Boundary::before_manifest_commit,
    },
};

constexpr std::array kSequenceFlushCases{
    FaultPoint::sequence_journal_write,
    FaultPoint::sequence_transaction_write,
    FaultPoint::sequence_checkpoint_write,
    FaultPoint::sequence_manifest_publish,
    FaultPoint::sequence_receipt_reload,
    FaultPoint::sequence_journal_completion,
    FaultPoint::sequence_journal_deletion,
};

constexpr std::size_t point_index(FaultPoint point) {
  return static_cast<std::size_t>(point);
}

std::array<int, kCases.size()> matrix_observations{};
FaultPoint injected_point = FaultPoint::artifact_temp_sync;
int injected_point_calls = 0;
std::filesystem::path injected_residue_path;
FaultPoint sample_fault_point = FaultPoint::sample_after_staging;
int sample_fault_calls = 0;

bool lowercase_hex(std::string_view value) {
  return std::all_of(
      value.begin(),
      value.end(),
      [](unsigned char character) {
        return (character >= '0' && character <= '9') ||
               (character >= 'a' && character <= 'f');
      });
}

bool opaque_sibling_for(
    const std::filesystem::path& sibling,
    const std::filesystem::path& destination) {
  const auto sibling_name = sibling.filename().string();
  const auto prefix = destination.filename().string() + ".tmp.";
  return sibling.parent_path() == destination.parent_path() &&
         sibling_name.starts_with(prefix) &&
         sibling_name.size() == prefix.size() + 32 &&
         lowercase_hex(std::string_view{sibling_name}.substr(prefix.size()));
}

std::filesystem::path crash_residue_path(
    FaultPoint point,
    const std::filesystem::path& callback_path) {
  if (point == FaultPoint::artifact_temp_sync ||
      point == FaultPoint::transaction_temp_sync ||
      point == FaultPoint::checkpoint_temp_sync ||
      point == FaultPoint::manifest_temp_sync) {
    return callback_path;
  }
  for (const auto& entry :
       std::filesystem::directory_iterator(callback_path.parent_path())) {
    if (opaque_sibling_for(entry.path(), callback_path)) {
      return entry.path();
    }
  }
  return {};
}

lmdj::foundation::Result<void> inject_selected_fault(
    FaultPoint point,
    const std::filesystem::path& path) {
  if (point != injected_point) {
    return lmdj::foundation::Result<void>::success();
  }
  ++injected_point_calls;
  ++matrix_observations.at(point_index(point));
  injected_residue_path = crash_residue_path(point, path);
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected persistence fault",
          {
              {"fault_point", std::string{kCases.at(point_index(point)).name}},
              {"path", path.generic_string()},
          },
      });
}

class FaultGuard {
 public:
  explicit FaultGuard(FaultPoint point) {
    injected_point = point;
    injected_point_calls = 0;
    injected_residue_path.clear();
    lmdj::project_io::testing::set_fault_hook(inject_selected_fault);
  }

  ~FaultGuard() {
    lmdj::project_io::testing::set_fault_hook(nullptr);
  }

  FaultGuard(const FaultGuard&) = delete;
  FaultGuard& operator=(const FaultGuard&) = delete;
};

lmdj::foundation::Result<void> inject_sample_fault(
    FaultPoint point,
    const std::filesystem::path& path) {
  if (point != sample_fault_point) {
    return lmdj::foundation::Result<void>::success();
  }
  ++sample_fault_calls;
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected atomic Sample mutation fault",
          {{"path", path.generic_string()}},
      });
}

class SampleFaultGuard {
 public:
  explicit SampleFaultGuard(FaultPoint point) {
    sample_fault_point = point;
    sample_fault_calls = 0;
    lmdj::project_io::testing::set_fault_hook(inject_sample_fault);
  }

  ~SampleFaultGuard() {
    lmdj::project_io::testing::set_fault_hook(nullptr);
  }

  SampleFaultGuard(const SampleFaultGuard&) = delete;
  SampleFaultGuard& operator=(const SampleFaultGuard&) = delete;
};

class TempDirectory {
 public:
  explicit TempDirectory(std::string_view label) {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-fault-matrix-" + std::string{label} + "-" +
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

void write_bytes(const std::filesystem::path& path, std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  LMDJ_CHECK(static_cast<bool>(stream));
}

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

lmdj::domain::ProjectState new_project() {
  const auto project =
      lmdj::domain::create_project(ProjectId{test_uuid("project")}, 120);
  LMDJ_CHECK(project.has_value());
  return project.value();
}

CommandMeta meta(std::string_view id, std::uint64_t revision) {
  return CommandMeta{CommandId{test_uuid(id)}, revision};
}

Pattern pattern(std::string_view id) {
  return Pattern{
      PatternId{test_uuid(id)},
      1,
      {PatternEvent{
          PadSlotId{0, 0}, 0, lmdj::domain::kSixteenthTicks, 100}},
  };
}

std::uint64_t manifest_revision(const std::filesystem::path& bundle) {
  return nlohmann::json::parse(read_bytes(bundle / "manifest.json"))
      .at("head_revision")
      .get<std::uint64_t>();
}

void check_no_uncommitted_revision_one(
    const std::filesystem::path& bundle) {
  for (const auto& entry :
       std::filesystem::recursive_directory_iterator(bundle)) {
    if (!entry.is_regular_file()) {
      continue;
    }
    const auto relative =
        std::filesystem::relative(entry.path(), bundle).generic_string();
    if (relative.find(".tmp") != std::string::npos) {
      throw std::runtime_error(
          "uncommitted temporary file remained after restart: " + relative);
    }
    LMDJ_CHECK(!relative.starts_with("history/checkpoints/1."));
    LMDJ_CHECK(!relative.starts_with("history/transactions/1-"));
  }
}

void test_publish_faults_preserve_previous_project_truth() {
  for (const auto& fault : kCases) {
    if (fault.boundary != Boundary::before_manifest_commit) {
      continue;
    }
    TempDirectory temp(fault.name);
    const auto bundle = temp.path() / "project.lmdj";
    auto platform = lmdj::project_io::make_default_project_storage_platform();
    ProjectStore store{platform};
    LMDJ_CHECK(store.create(bundle, new_project()).has_value());

    lmdj::foundation::Result<lmdj::domain::AppliedCommand> result =
        lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
            lmdj::foundation::Error{
                ErrorCode::internal_error,
                "fault operation did not run",
            });
    {
      FaultGuard guard(fault.point);
      if (fault.point == FaultPoint::artifact_temp_sync ||
          fault.point == FaultPoint::artifact_publish) {
        const auto source = temp.path() / "source.wav";
        write_bytes(source, "RIFF-fault-matrix");
        result = store.import_artifact(
            bundle,
            ProjectStore::ImportArtifactRequest{
                meta("import", 0),
                AssetId{test_uuid("asset")},
                source,
                "audio/wav",
            });
      } else {
        result = store.execute(
            bundle,
            Command{CreatePattern{
                meta("pattern-command", 0),
                pattern("pattern"),
            }});
      }
      LMDJ_CHECK(injected_point_calls == 1);
    }

    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::io_error);
    LMDJ_CHECK(manifest_revision(bundle) == 0);
    LMDJ_CHECK(!injected_residue_path.empty());
    LMDJ_CHECK(!std::filesystem::exists(injected_residue_path));
    write_bytes(injected_residue_path, "seeded-exact-crash-residue");
    LMDJ_CHECK(std::filesystem::is_regular_file(injected_residue_path));

    ProjectStore restarted;
    const auto loaded = restarted.load(bundle);
    LMDJ_CHECK(loaded.has_value());
    LMDJ_CHECK(loaded.value().revision == 0);
    LMDJ_CHECK(loaded.value().patterns.empty());
    LMDJ_CHECK(loaded.value().assets.empty());
    LMDJ_CHECK(!std::filesystem::exists(injected_residue_path));
    const auto recovery_probe = restarted.execute(
        bundle,
        Command{CreatePattern{
            meta("recovery-probe", 99),
            pattern("recovery-probe-pattern"),
        }});
    LMDJ_CHECK(!recovery_probe.has_value());
    LMDJ_CHECK(
        recovery_probe.error().code == ErrorCode::revision_conflict);
    LMDJ_CHECK(manifest_revision(bundle) == 0);
    LMDJ_CHECK(!std::filesystem::exists(injected_residue_path));
    check_no_uncommitted_revision_one(bundle);
  }
}

void test_atomic_sample_import_faults_preserve_every_project_truth_projection() {
  constexpr std::array fault_points{
      FaultPoint::sample_after_staging,
      FaultPoint::sample_after_event_preparation,
      FaultPoint::sample_after_artifact_creation,
      FaultPoint::sample_after_manifest_preparation,
  };
  for (const auto point : fault_points) {
    TempDirectory temp("sample-atomic");
    const auto bundle = temp.path() / "project.lmdj";
    ProjectStore store;
    auto initial = new_project();
    initial.contract = ProjectContract::v4;
    LMDJ_CHECK(store.create(bundle, initial).has_value());
    const auto original_manifest = read_bytes(bundle / "manifest.json");
    const auto original = store.load(bundle);
    LMDJ_CHECK(original.has_value());
    const std::array sample{
        std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
        std::byte{0x01}, std::byte{0x02}, std::byte{0x03}, std::byte{0x04},
    };
    const AssetLineage lineage{
        {std::string(64, 'a'), 7},
        {{10, 20},
         PerformanceId{"40000000-0000-4000-8000-000000000001"}},
    };

    lmdj::foundation::Result<lmdj::domain::AppliedCommand> result =
        lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
            lmdj::foundation::Error{
                ErrorCode::internal_error,
                "Sample fault operation did not run",
            });
    {
      SampleFaultGuard guard(point);
      result = store.import_assign_sample_bytes(
          bundle,
          ProjectStore::ImportAssignSampleBytesRequest{
              meta("sample-command", 0),
              PadSlotId{1, 4},
              AssetId{test_uuid("sample-asset")},
              "audio/wav",
              sample,
              std::nullopt,
              lineage,
          });
      LMDJ_CHECK(sample_fault_calls == 1);
    }

    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::io_error);
    LMDJ_CHECK(read_bytes(bundle / "manifest.json") == original_manifest);
    const auto reopened = store.load(bundle);
    LMDJ_CHECK(reopened.has_value());
    LMDJ_CHECK(reopened.value() == original.value());
    LMDJ_CHECK(reopened.value().revision == 0);
    LMDJ_CHECK(reopened.value().assets.empty());
    LMDJ_CHECK(
        !reopened.value().banks.at(1).at(4).asset_id.has_value());
    LMDJ_CHECK(std::filesystem::is_empty(bundle / "assets"));
    LMDJ_CHECK(
        !std::filesystem::exists(bundle / "history/checkpoints/1.json"));
    LMDJ_CHECK(std::filesystem::is_empty(bundle / "history/transactions"));
  }
}

void test_sample_staging_scavenger_is_generated_name_age_and_count_bounded() {
  TempDirectory temp("sample-scavenger");
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto root = temp.path() / ".lmdj-host/sample-staging";
  const auto old_token = test_uuid("old-staging");
  const auto fresh_token = test_uuid("fresh-staging");
  const auto invalid_name = std::string{"not-generated"};
  for (const auto& name : {old_token, fresh_token, invalid_name}) {
    std::filesystem::create_directories(root / name);
    write_bytes(root / name / "payload.wav", "orphan");
  }
  const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                       std::chrono::system_clock::now().time_since_epoch())
                       .count();
  write_bytes(
      root / old_token / "state.json",
      nlohmann::json{
          {"contract", "lmdj.sample-staging.v1"},
          {"created_unix_seconds", 0},
          {"state", "incomplete"},
          {"token", old_token},
      }
              .dump());
  write_bytes(
      root / fresh_token / "state.json",
      nlohmann::json{
          {"contract", "lmdj.sample-staging.v1"},
          {"created_unix_seconds", now},
          {"state", "incomplete"},
          {"token", fresh_token},
      }
              .dump());

  const auto opened = store.load(bundle);
  LMDJ_CHECK(opened.has_value());
  LMDJ_CHECK(!std::filesystem::exists(root / old_token));
  LMDJ_CHECK(std::filesystem::is_directory(root / fresh_token));
  LMDJ_CHECK(std::filesystem::is_directory(root / invalid_name));

  const auto count_limited_token = test_uuid("count-limited-staging");
  std::filesystem::create_directories(root / count_limited_token);
  write_bytes(root / count_limited_token / "payload.wav", "bounded");
  write_bytes(
      root / count_limited_token / "state.json",
      nlohmann::json{
          {"contract", "lmdj.sample-staging.v1"},
          {"created_unix_seconds", 0},
          {"state", "incomplete"},
          {"token", count_limited_token},
      }
          .dump());
  for (std::size_t index = 0; index < 64; ++index) {
    auto name = std::string{"!"} + std::to_string(index);
    name.insert(1, 3 - std::min<std::size_t>(3, name.size() - 1), '0');
    std::filesystem::create_directories(root / name);
  }

  LMDJ_CHECK(store.load(bundle).has_value());
  LMDJ_CHECK(std::filesystem::is_directory(root / count_limited_token));
}

void test_sample_import_reclaims_its_fresh_incomplete_crash_residue() {
  TempDirectory temp("sample-retry-residue");
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  const auto token = test_uuid("sample-retry-residue");
  const auto directory =
      temp.path() / ".lmdj-host/sample-staging" / token;
  std::filesystem::create_directories(directory);
  write_bytes(directory / "payload.wav", "crashed-at-staging");
  const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                       std::chrono::system_clock::now().time_since_epoch())
                       .count();
  write_bytes(
      directory / "state.json",
      nlohmann::json{
          {"contract", "lmdj.sample-staging.v1"},
          {"created_unix_seconds", now},
          {"state", "incomplete"},
          {"token", token},
      }
          .dump());

  const std::array sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
      std::byte{0x01}, std::byte{0x02}, std::byte{0x03}, std::byte{0x04},
  };
  const auto retried = store.import_assign_sample_bytes(
      bundle,
      ProjectStore::ImportAssignSampleBytesRequest{
          CommandMeta{CommandId{token}, 0},
          PadSlotId{2, 9},
          AssetId{test_uuid("sample-retry-residue-asset")},
          "audio/wav",
          sample,
      });

  LMDJ_CHECK(retried.has_value());
  LMDJ_CHECK(!std::filesystem::exists(directory));
  const auto loaded = store.load(bundle);
  LMDJ_CHECK(loaded.has_value());
  LMDJ_CHECK(loaded.value().revision == 1);
  LMDJ_CHECK(loaded.value().banks.at(2).at(9).asset_id.has_value());
}

void test_crash_after_sample_manifest_publication_recovers_new_truth() {
  TempDirectory temp("sample-post-publication");
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore store;
  auto initial = new_project();
  initial.contract = ProjectContract::v4;
  LMDJ_CHECK(store.create(bundle, initial).has_value());
  const std::array sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
  };
  const auto asset_id = AssetId{test_uuid("sample-post-publication-asset")};
  const AssetLineage lineage{
      {std::string(64, 'b'), 9},
      {{20, 40},
       PerformanceId{"40000000-0000-4000-8000-000000000002"}},
  };
  lmdj::foundation::Result<lmdj::domain::AppliedCommand> result =
      lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "post-publication Sample fault operation did not run",
          });
  {
    SampleFaultGuard guard(FaultPoint::sample_after_manifest_publication);
    result = store.import_assign_sample_bytes(
        bundle,
        ProjectStore::ImportAssignSampleBytesRequest{
            meta("sample-post-publication", 0),
            PadSlotId{3, 15},
            asset_id,
            "audio/wav",
            sample,
            std::nullopt,
            lineage,
        });
    LMDJ_CHECK(sample_fault_calls == 1);
  }
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(manifest_revision(bundle) == 1);

  ProjectStore restarted;
  const auto recovered = restarted.load(bundle);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().revision == 1);
  LMDJ_CHECK(recovered.value().assets.size() == 1);
  LMDJ_CHECK(recovered.value().assets.at(asset_id).lineage == lineage);
  LMDJ_CHECK(recovered.value().banks.at(3).at(15).asset_id == asset_id);
}

void test_armed_capture_retry_reconciles_manifest_published_journal() {
  TempDirectory temp("armed-sample-post-publication");
  const auto bundle = temp.path() / "project.lmdj";
  auto platform = lmdj::project_io::make_default_project_storage_platform();
  ProjectStore store{platform};
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());

  const auto capture_pattern = pattern("armed-capture-pattern");
  const auto created = store.execute(
      bundle,
      Command{CreatePattern{
          meta("armed-capture-pattern-command", 0), capture_pattern}});
  LMDJ_CHECK(created.has_value());
  const auto session_id = lmdj::foundation::SequenceSessionId{
      test_uuid("armed-capture-session")};
  const auto slot = PadSlotId{2, 7};
  SequenceJournal journal{platform};
  LMDJ_CHECK(
      journal
          .begin(
              bundle, session_id, capture_pattern.id, capture_pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(capture_pattern),
              1, slot)
          .has_value());

  const std::array sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
      std::byte{0x01}, std::byte{0x02}, std::byte{0x03}, std::byte{0x04},
  };
  const auto original_command = meta("armed-capture-import", 1);
  const auto original_asset = AssetId{test_uuid("armed-capture-asset")};
  lmdj::foundation::Result<lmdj::domain::AppliedCommand> interrupted =
      lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "armed Capture publication fault did not run",
          });
  {
    SampleFaultGuard guard(FaultPoint::sample_after_manifest_publication);
    interrupted = store.import_assign_sample_bytes(
        bundle,
        ProjectStore::ImportAssignSampleBytesRequest{
            original_command, slot, original_asset, "audio/wav", sample,
            session_id});
    LMDJ_CHECK(sample_fault_calls == 1);
  }
  LMDJ_CHECK(!interrupted.has_value());
  LMDJ_CHECK(interrupted.error().code == ErrorCode::io_error);
  LMDJ_CHECK(manifest_revision(bundle) == 2);
  const auto incomplete = journal.read_active(bundle);
  LMDJ_CHECK(incomplete.has_value());
  LMDJ_CHECK(incomplete.value().expected_revision == 1);
  LMDJ_CHECK(incomplete.value().armed_capture_slot == slot);
  LMDJ_CHECK(incomplete.value().capture_commit.has_value());
  LMDJ_CHECK(
      incomplete.value().capture_commit->command_id ==
      original_command.command_id);
  LMDJ_CHECK(incomplete.value().capture_commit->asset_id == original_asset);
  LMDJ_CHECK(incomplete.value().capture_commit->slot == slot);
  LMDJ_CHECK(incomplete.value().capture_commit->expected_revision == 1);

  auto conflicting_sample = sample;
  conflicting_sample.back() = std::byte{0x05};
  const auto conflicting_retry = store.import_assign_sample_bytes(
      bundle,
      ProjectStore::ImportAssignSampleBytesRequest{
          meta("armed-capture-conflicting-retry", 1), slot,
          AssetId{test_uuid("armed-capture-conflicting-retry-asset")},
          "audio/wav", conflicting_sample, session_id});
  LMDJ_CHECK(!conflicting_retry.has_value());
  LMDJ_CHECK(conflicting_retry.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      conflicting_retry.error().details.at("reason") ==
      "armed_capture_recovery_conflict");
  LMDJ_CHECK(conflicting_retry.error().details.contains("remedy"));
  LMDJ_CHECK(manifest_revision(bundle) == 2);
  const auto still_incomplete = journal.read_active(bundle);
  LMDJ_CHECK(still_incomplete.has_value());
  LMDJ_CHECK(still_incomplete.value() == incomplete.value());

  const auto retried = store.import_assign_sample_bytes(
      bundle,
      ProjectStore::ImportAssignSampleBytesRequest{
          meta("armed-capture-ui-retry", 1), slot,
          AssetId{test_uuid("armed-capture-ui-retry-asset")}, "audio/wav",
          sample, session_id});
  LMDJ_CHECK(retried.has_value());
  LMDJ_CHECK(retried.value().replayed);
  LMDJ_CHECK(retried.value().state.revision == 2);
  LMDJ_CHECK(
      retried.value().event.at("command_id") ==
      original_command.command_id.value());
  LMDJ_CHECK(
      retried.value().state.banks.at(slot.bank).at(slot.pad).asset_id ==
      original_asset);
  LMDJ_CHECK(retried.value().state.assets.size() == 1);

  const auto reconciled = journal.read_active(bundle);
  LMDJ_CHECK(reconciled.has_value());
  LMDJ_CHECK(reconciled.value().expected_revision == 2);
  LMDJ_CHECK(!reconciled.value().armed_capture_slot.has_value());

  const auto flush_command = CommandId{test_uuid("armed-capture-flush")};
  const std::array continued_events{
      PatternEvent{PadSlotId{0, 1}, 240, 120, 96}};
  const auto flush = journal.append_flush(
      bundle, session_id, flush_command, capture_pattern.id, 2,
      continued_events);
  LMDJ_CHECK(flush.has_value());
  const auto flushed = store.execute_sequence_flush(
      bundle,
      {session_id, flush.value().flush_seq, flush_command, capture_pattern.id});
  LMDJ_CHECK(flushed.has_value());
  LMDJ_CHECK(flushed.value().outcome.state.revision == 3);
  LMDJ_CHECK(
      journal.set_state(bundle, session_id, SequenceSessionState::stopped)
          .has_value());
  LMDJ_CHECK(journal.remove_active_if_complete(bundle, session_id).has_value());
}

void test_armed_capture_restart_reconciles_published_receipt_before_seal() {
  TempDirectory temp("armed-sample-restart");
  const auto bundle = temp.path() / "project.lmdj";
  auto platform = lmdj::project_io::make_default_project_storage_platform();
  ProjectStore store{platform};
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto capture_pattern = pattern("armed-restart-pattern");
  LMDJ_CHECK(
      store
          .execute(
              bundle,
              Command{CreatePattern{
                  meta("armed-restart-pattern-command", 0),
                  capture_pattern}})
          .has_value());
  const auto session_id = lmdj::foundation::SequenceSessionId{
      test_uuid("armed-restart-session")};
  const auto slot = PadSlotId{1, 6};
  SequenceJournal journal{platform};
  LMDJ_CHECK(
      journal
          .begin(
              bundle, session_id, capture_pattern.id, capture_pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(capture_pattern),
              1, slot)
          .has_value());
  const std::array sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
  };
  const auto asset_id = AssetId{test_uuid("armed-restart-asset")};
  {
    SampleFaultGuard guard(FaultPoint::sample_after_manifest_publication);
    const auto interrupted = store.import_assign_sample_bytes(
        bundle,
        ProjectStore::ImportAssignSampleBytesRequest{
            meta("armed-restart-import", 1), slot, asset_id, "audio/wav",
            sample, session_id});
    LMDJ_CHECK(!interrupted.has_value());
  }
  LMDJ_CHECK(manifest_revision(bundle) == 2);

  ProjectStore restarted{platform};
  const auto recovered = restarted.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().size() == 1);
  LMDJ_CHECK(recovered.value().front().journal.expected_revision == 2);
  LMDJ_CHECK(
      !recovered.value().front().journal.armed_capture_slot.has_value());
  LMDJ_CHECK(!recovered.value().front().journal.capture_commit.has_value());
  const auto truth = restarted.load(bundle);
  LMDJ_CHECK(truth.has_value());
  LMDJ_CHECK(truth.value().revision == 2);
  LMDJ_CHECK(truth.value().assets.size() == 1);
  LMDJ_CHECK(truth.value().banks.at(slot.bank).at(slot.pad).asset_id == asset_id);
}

void test_armed_capture_discard_aborts_prepublication_marker() {
  TempDirectory temp("armed-sample-prepublication-discard");
  const auto bundle = temp.path() / "project.lmdj";
  auto platform = lmdj::project_io::make_default_project_storage_platform();
  ProjectStore store{platform};
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto capture_pattern = pattern("armed-discard-pattern");
  LMDJ_CHECK(
      store
          .execute(
              bundle,
              Command{CreatePattern{
                  meta("armed-discard-pattern-command", 0), capture_pattern}})
          .has_value());
  const auto session_id = lmdj::foundation::SequenceSessionId{
      test_uuid("armed-discard-session")};
  const auto slot = PadSlotId{1, 7};
  SequenceJournal journal{platform};
  LMDJ_CHECK(
      journal
          .begin(
              bundle, session_id, capture_pattern.id, capture_pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(capture_pattern),
              1, slot)
          .has_value());
  const std::array sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
      std::byte{0x01}, std::byte{0x02}, std::byte{0x03}, std::byte{0x04},
  };
  {
    SampleFaultGuard guard(FaultPoint::sample_after_manifest_preparation);
    const auto interrupted = store.import_assign_sample_bytes(
        bundle,
        ProjectStore::ImportAssignSampleBytesRequest{
            meta("armed-discard-import", 1), slot,
            AssetId{test_uuid("armed-discard-asset")}, "audio/wav", sample,
            session_id});
    LMDJ_CHECK(!interrupted.has_value());
    LMDJ_CHECK(interrupted.error().code == ErrorCode::io_error);
    LMDJ_CHECK(sample_fault_calls == 1);
  }
  LMDJ_CHECK(manifest_revision(bundle) == 1);
  const auto prepared = journal.read_active(bundle);
  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value().expected_revision == 1);
  LMDJ_CHECK(prepared.value().armed_capture_slot == slot);
  LMDJ_CHECK(prepared.value().capture_commit.has_value());

  const auto settings = store.execute(
      bundle,
      Command{UpdateSequenceSettings{
          meta("armed-discard-settings", 1), 130, std::nullopt,
          std::nullopt}});
  LMDJ_CHECK(!settings.has_value());
  LMDJ_CHECK(settings.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(manifest_revision(bundle) == 1);
  const auto after_settings = journal.read_active(bundle);
  LMDJ_CHECK(after_settings.has_value());
  LMDJ_CHECK(after_settings.value() == prepared.value());
  LMDJ_CHECK(
      settings.error().details.at("reason") ==
      "armed_capture_recovery_pending");
  LMDJ_CHECK(settings.error().details.contains("remedy"));

  const auto wrong_owner = store.disarm_sequence_capture(
      bundle,
      lmdj::foundation::SequenceSessionId{
          test_uuid("armed-discard-wrong-session")},
      slot);
  LMDJ_CHECK(!wrong_owner.has_value());
  LMDJ_CHECK(wrong_owner.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      wrong_owner.error().details.at("reason") == "sequence_owner_mismatch");
  const auto wrong_slot = store.disarm_sequence_capture(
      bundle, session_id, PadSlotId{slot.bank, 6});
  LMDJ_CHECK(!wrong_slot.has_value());
  LMDJ_CHECK(wrong_slot.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      wrong_slot.error().details.at("reason") ==
      "armed_capture_target_mismatch");
  const auto still_prepared = journal.read_active(bundle);
  LMDJ_CHECK(still_prepared.has_value());
  LMDJ_CHECK(still_prepared.value() == prepared.value());

  const auto discarded = store.disarm_sequence_capture(
      bundle, session_id, slot);
  LMDJ_CHECK(discarded.has_value());
  LMDJ_CHECK(!discarded.value().reconciled_commit);
  LMDJ_CHECK(discarded.value().expected_revision == 1);
  const auto disarmed = journal.read_active(bundle);
  LMDJ_CHECK(disarmed.has_value());
  LMDJ_CHECK(disarmed.value().expected_revision == 1);
  LMDJ_CHECK(!disarmed.value().armed_capture_slot.has_value());
  LMDJ_CHECK(!disarmed.value().capture_commit.has_value());
  const auto unchanged = store.load(bundle);
  LMDJ_CHECK(unchanged.has_value());
  LMDJ_CHECK(unchanged.value().revision == 1);
  LMDJ_CHECK(unchanged.value().assets.empty());
  LMDJ_CHECK(
      !unchanged.value().banks.at(slot.bank).at(slot.pad).asset_id.has_value());

  const auto flush_command = CommandId{test_uuid("armed-discard-flush")};
  const std::array continued_events{
      PatternEvent{PadSlotId{0, 2}, 240, 120, 96}};
  const auto flush = journal.append_flush(
      bundle, session_id, flush_command, capture_pattern.id, 1,
      continued_events);
  LMDJ_CHECK(flush.has_value());
  const auto flushed = store.execute_sequence_flush(
      bundle,
      {session_id, flush.value().flush_seq, flush_command, capture_pattern.id});
  LMDJ_CHECK(flushed.has_value());
  LMDJ_CHECK(flushed.value().outcome.state.revision == 2);
  LMDJ_CHECK(
      journal.set_state(bundle, session_id, SequenceSessionState::stopped)
          .has_value());
  LMDJ_CHECK(journal.remove_active_if_complete(bundle, session_id).has_value());
}

void test_armed_capture_restart_aborts_prepublication_marker_before_seal() {
  TempDirectory temp("armed-sample-prepublication-restart");
  const auto bundle = temp.path() / "project.lmdj";
  auto platform = lmdj::project_io::make_default_project_storage_platform();
  ProjectStore store{platform};
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const auto capture_pattern = pattern("armed-abort-restart-pattern");
  LMDJ_CHECK(
      store
          .execute(
              bundle,
              Command{CreatePattern{
                  meta("armed-abort-restart-pattern-command", 0),
                  capture_pattern}})
          .has_value());
  const auto session_id = lmdj::foundation::SequenceSessionId{
      test_uuid("armed-abort-restart-session")};
  const auto slot = PadSlotId{2, 8};
  SequenceJournal journal{platform};
  LMDJ_CHECK(
      journal
          .begin(
              bundle, session_id, capture_pattern.id, capture_pattern.bars,
              lmdj::project_io::sequence_pattern_fingerprint(capture_pattern),
              1, slot)
          .has_value());
  const std::array sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
      std::byte{0x05}, std::byte{0x06}, std::byte{0x07}, std::byte{0x08},
  };
  {
    SampleFaultGuard guard(FaultPoint::sample_after_manifest_preparation);
    const auto interrupted = store.import_assign_sample_bytes(
        bundle,
        ProjectStore::ImportAssignSampleBytesRequest{
            meta("armed-abort-restart-import", 1), slot,
            AssetId{test_uuid("armed-abort-restart-asset")}, "audio/wav",
            sample, session_id});
    LMDJ_CHECK(!interrupted.has_value());
  }
  LMDJ_CHECK(manifest_revision(bundle) == 1);

  ProjectStore restarted{platform};
  const auto recovered = restarted.reconcile_sequence_recovery(bundle);
  LMDJ_CHECK(recovered.has_value());
  LMDJ_CHECK(recovered.value().size() == 1);
  LMDJ_CHECK(recovered.value().front().reason == "owner_lost");
  LMDJ_CHECK(recovered.value().front().journal.expected_revision == 1);
  LMDJ_CHECK(
      !recovered.value().front().journal.armed_capture_slot.has_value());
  LMDJ_CHECK(!recovered.value().front().journal.capture_commit.has_value());
  const auto unchanged = restarted.load(bundle);
  LMDJ_CHECK(unchanged.has_value());
  LMDJ_CHECK(unchanged.value().revision == 1);
  LMDJ_CHECK(unchanged.value().assets.empty());
  LMDJ_CHECK(
      !unchanged.value().banks.at(slot.bank).at(slot.pad).asset_id.has_value());
}

void test_restart_classifies_committed_and_uncommitted_files() {
  TempDirectory temp("symlink-boundary");
  const auto bundle = temp.path() / "project.lmdj";
  const auto external = temp.path() / "external";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  std::filesystem::create_directory(external);
  const auto sentinel = external / "sentinel.txt";
  write_bytes(sentinel, "must-survive");
  std::filesystem::remove(bundle / "assets");
  std::filesystem::create_directory_symlink(external, bundle / "assets");

  const auto rejected = store.load(bundle);

  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(read_bytes(sentinel) == "must-survive");
}

void test_every_fault_point_is_observed_exactly_once() {
  std::set<std::size_t> declared_points;
  for (const auto& fault : kCases) {
    declared_points.insert(point_index(fault.point));
  }
  LMDJ_CHECK(declared_points.size() == kCases.size());
  for (const auto observations : matrix_observations) {
    LMDJ_CHECK(observations == 1);
  }
  std::set<std::size_t> sequence_points;
  for (const auto point : kSequenceFlushCases) {
    sequence_points.insert(point_index(point));
  }
  LMDJ_CHECK(sequence_points.size() == kSequenceFlushCases.size());
  LMDJ_CHECK(
      point_index(kSequenceFlushCases.back()) + 1 ==
      point_index(FaultPoint::complete_read));
}

}  // namespace

int main() {
  try {
    test_publish_faults_preserve_previous_project_truth();
    test_atomic_sample_import_faults_preserve_every_project_truth_projection();
    test_sample_staging_scavenger_is_generated_name_age_and_count_bounded();
    test_sample_import_reclaims_its_fresh_incomplete_crash_residue();
    test_crash_after_sample_manifest_publication_recovers_new_truth();
    test_armed_capture_retry_reconciles_manifest_published_journal();
    test_armed_capture_restart_reconciles_published_receipt_before_seal();
    test_armed_capture_discard_aborts_prepublication_marker();
    test_armed_capture_restart_aborts_prepublication_marker_before_seal();
    test_restart_classifies_committed_and_uncommitted_files();
    test_every_fault_point_is_observed_exactly_once();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project io fault matrix tests: PASS\n";
  return 0;
}
