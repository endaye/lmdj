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
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/project_io/take_journal.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CreatePattern;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::RawTake;
using lmdj::domain::RawTakeEvent;
using lmdj::domain::RecordTake;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::TakeId;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::TakeJournal;
using lmdj::project_io::testing::FaultPoint;

enum class Boundary {
  before_manifest_commit,
  after_manifest_commit,
  active_journal,
  sealed_candidate,
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
    FaultCase{
        FaultPoint::active_journal_sync,
        "active_journal_sync",
        Boundary::active_journal,
    },
    FaultCase{
        FaultPoint::active_journal_remove,
        "active_journal_remove",
        Boundary::after_manifest_commit,
    },
    FaultCase{
        FaultPoint::active_directory_sync,
        "active_directory_sync",
        Boundary::after_manifest_commit,
    },
    FaultCase{
        FaultPoint::sealed_directory_sync,
        "sealed_directory_sync",
        Boundary::sealed_candidate,
    },
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
      {PatternEvent{PadSlotId{0, 0}, 0, 100}},
  };
}

RawTake take(std::string_view id) {
  return RawTake{
      TakeId{test_uuid(id)},
      48000,
      {
          RawTakeEvent{PadSlotId{0, 0}, 100, 96},
          RawTakeEvent{PadSlotId{0, 1}, 200, 110},
      },
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

void begin_take(
    TakeJournal& journal,
    const std::filesystem::path& bundle,
    const RawTake& recorded) {
  LMDJ_CHECK(
      journal.begin(
                 bundle,
                 recorded.id,
                 0,
                 recorded.sample_rate)
          .has_value());
}

void append_take(
    TakeJournal& journal,
    const std::filesystem::path& bundle,
    const RawTake& recorded) {
  for (const auto& event : recorded.events) {
    LMDJ_CHECK(journal.append(bundle, recorded.id, event).has_value());
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
    LMDJ_CHECK(store.create(bundle, new_project()).has_value());
    const auto original_manifest = read_bytes(bundle / "manifest.json");
    const auto original = store.load(bundle);
    LMDJ_CHECK(original.has_value());
    const std::array sample{
        std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
        std::byte{0x01}, std::byte{0x02}, std::byte{0x03}, std::byte{0x04},
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

void test_crash_after_sample_manifest_publication_recovers_new_truth() {
  TempDirectory temp("sample-post-publication");
  const auto bundle = temp.path() / "project.lmdj";
  ProjectStore store;
  LMDJ_CHECK(store.create(bundle, new_project()).has_value());
  const std::array sample{
      std::byte{'R'}, std::byte{'I'}, std::byte{'F'}, std::byte{'F'},
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
            AssetId{test_uuid("sample-post-publication-asset")},
            "audio/wav",
            sample,
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
  LMDJ_CHECK(recovered.value().banks.at(3).at(15).asset_id.has_value());
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

void test_take_cleanup_faults_leave_replayable_obligation() {
  for (const auto& fault : kCases) {
    if (fault.boundary != Boundary::after_manifest_commit) {
      continue;
    }
    TempDirectory temp(fault.name);
    const auto bundle = temp.path() / "project.lmdj";
    auto platform = lmdj::project_io::make_default_project_storage_platform();
    ProjectStore store{platform};
    TakeJournal journal{platform};
    LMDJ_CHECK(store.create(bundle, new_project()).has_value());
    const auto recorded = take("cleanup-take");
    begin_take(journal, bundle, recorded);
    append_take(journal, bundle, recorded);
    const auto command = Command{RecordTake{
        meta("record", 0),
        recorded,
        pattern("record-pattern"),
    }};
    const auto active =
        bundle / "recovery/active" / (recorded.id.value() + ".jsonl");

    lmdj::foundation::Result<lmdj::domain::AppliedCommand> result =
        lmdj::foundation::Result<lmdj::domain::AppliedCommand>::failure(
            lmdj::foundation::Error{
                ErrorCode::internal_error,
                "fault operation did not run",
            });
    {
      FaultGuard guard(fault.point);
      result = store.execute(bundle, command);
      LMDJ_CHECK(injected_point_calls == 1);
    }

    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::io_error);
    LMDJ_CHECK(manifest_revision(bundle) == 1);
    ProjectStore restarted;
    const auto loaded = restarted.load(bundle);
    LMDJ_CHECK(loaded.has_value());
    LMDJ_CHECK(loaded.value().revision == 1);
    LMDJ_CHECK(loaded.value().takes.contains(recorded.id));
    const auto transaction =
        bundle / "history/transactions" /
        ("1-" + meta("record", 0).command_id.value() + ".json");
    LMDJ_CHECK(
        nlohmann::json::parse(read_bytes(transaction))
            .at("cleanup_take_id") == recorded.id.value());
    if (fault.point == FaultPoint::active_journal_remove) {
      LMDJ_CHECK(std::filesystem::is_regular_file(active));
    } else {
      LMDJ_CHECK(!std::filesystem::exists(active));
    }

    const auto replayed = restarted.execute(bundle, command);
    LMDJ_CHECK(replayed.has_value());
    LMDJ_CHECK(replayed.value().replayed);
    LMDJ_CHECK(replayed.value().state.revision == 1);
    LMDJ_CHECK(!std::filesystem::exists(active));
  }

  for (const auto& fault : kCases) {
    if (fault.boundary != Boundary::active_journal &&
        fault.boundary != Boundary::sealed_candidate) {
      continue;
    }
    TempDirectory temp(fault.name);
    const auto bundle = temp.path() / "project.lmdj";
    auto platform = lmdj::project_io::make_default_project_storage_platform();
    ProjectStore store{platform};
    TakeJournal journal{platform};
    LMDJ_CHECK(store.create(bundle, new_project()).has_value());
    const auto recorded = take("journal-take");
    begin_take(journal, bundle, recorded);

    if (fault.boundary == Boundary::active_journal) {
      lmdj::foundation::Result<void> appended =
          lmdj::foundation::Result<void>::success();
      {
        FaultGuard guard(fault.point);
        appended =
            journal.append(bundle, recorded.id, recorded.events.front());
        LMDJ_CHECK(injected_point_calls == 1);
      }
      LMDJ_CHECK(!appended.has_value());
      LMDJ_CHECK(appended.error().code == ErrorCode::io_error);
      const auto active = journal.read_active_journal(bundle, recorded.id);
      LMDJ_CHECK(active.has_value());
      LMDJ_CHECK(active.value().expected_revision == 0);
      LMDJ_CHECK(journal.list_recoverable(bundle).value().empty());
    } else {
      append_take(journal, bundle, recorded);
      lmdj::foundation::Result<std::filesystem::path> sealed =
          lmdj::foundation::Result<std::filesystem::path>::failure(
              lmdj::foundation::Error{
                  ErrorCode::internal_error,
                  "fault operation did not run",
              });
      {
        FaultGuard guard(fault.point);
        sealed = journal.seal(bundle, recorded.id, "interrupted");
        LMDJ_CHECK(injected_point_calls == 1);
      }
      LMDJ_CHECK(!sealed.has_value());
      LMDJ_CHECK(sealed.error().code == ErrorCode::io_error);
      LMDJ_CHECK(journal.read_active(bundle, recorded.id).has_value());
      const auto candidates = journal.list_recoverable(bundle);
      LMDJ_CHECK(candidates.has_value());
      LMDJ_CHECK(candidates.value().size() == 1);
      LMDJ_CHECK(candidates.value().front().take == recorded);
    }

    const auto loaded = ProjectStore{}.load(bundle);
    LMDJ_CHECK(loaded.has_value());
    LMDJ_CHECK(loaded.value().revision == 0);
  }
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
}

}  // namespace

int main() {
  try {
    test_publish_faults_preserve_previous_project_truth();
    test_atomic_sample_import_faults_preserve_every_project_truth_projection();
    test_sample_staging_scavenger_is_generated_name_age_and_count_bounded();
    test_crash_after_sample_manifest_publication_recovers_new_truth();
    test_restart_classifies_committed_and_uncommitted_files();
    test_take_cleanup_faults_leave_replayable_obligation();
    test_every_fault_point_is_observed_exactly_once();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project io fault matrix tests: PASS\n";
  return 0;
}
