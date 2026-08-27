// Failure-contract tests for the Application Facade.
//
// Split out of application_test.cpp deliberately. That binary already spent
// 15.97s of its 30s component budget on `main` before these landed, and these
// tests are filesystem-heavy - sixteen import sessions, repeated Application
// construction - which took it over the limit on CI. Two binaries carry two
// budgets; one binary carrying thirty tests decides its own fate on whichever
// runner it lands on.
//
// Everything here asserts a published failure contract - error code, public
// message, published details - rather than that a line executed.

#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>

#include "packages/application-facade/src/testing_hooks.hpp"

#include "tests/core/support/test.hpp"

namespace {

using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::facade::InitialProjectRequest;
using lmdj::facade::SampleImportBeginRequest;
using lmdj::facade::SampleInspectRequest;
using lmdj::facade::SampleResetRequest;
using lmdj::facade::SampleUpdateRequest;
using lmdj::domain::CommandMeta;
using lmdj::domain::PadPlayback;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::TriggerMode;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;
using lmdj::audio::RuntimePreparationLimits;

// Matches the Stage 8 Web limits application_test.cpp uses, so both binaries
// exercise the same bounded runtime the Creator ships against.
constexpr RuntimePreparationLimits kStage8WebLimits{
    1'048'576,
    240'000,
    67'108'864,
    134'217'728,
};

std::vector<std::byte> file_bytes(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("fixture is unreadable: " + path.string());
  const std::vector<char> raw(
      (std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  std::vector<std::byte> bytes(raw.size());
  for (std::size_t index = 0; index < raw.size(); ++index) {
    bytes[index] = static_cast<std::byte>(raw[index]);
  }
  return bytes;
}

nlohmann::json slot(std::uint32_t bank, std::uint32_t pad) {
  return {{"bank", bank}, {"pad", pad}};
}

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-facade-test-" + std::to_string(nonce));
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

std::string uuid(std::uint32_t suffix) {
  auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" +
         std::string(12 - tail.size(), '0') + tail;
}

std::shared_ptr<Registry> proof_registry() {
  auto registry = std::make_shared<Registry>();
  LMDJ_CHECK(
      registry->add(
          lmdj::providers::local_proof_success_registration()).has_value());
  LMDJ_CHECK(
      registry->add(
          lmdj::providers::local_proof_failure_registration()).has_value());
  return registry;
}

ApplicationConfig config(
    const std::filesystem::path& root,
    std::shared_ptr<Registry> registry = proof_registry()) {
  return ApplicationConfig{
      root,
      std::move(registry),
      ProviderPolicy{
          {"local"},
          {"public"},
          {"proof.execute"},
      },
      [] {
        return std::string("2026-07-31T00:00:00.000Z");
      },
  };
}

ApplicationConfig sample_config(
    const std::filesystem::path& root,
    RuntimePreparationLimits limits = kStage8WebLimits) {
  auto value = config(root);
  value.runtime_preparation_limits = limits;
  return value;
}


enum class StorageOp {
  ensure_directory,
  validate_managed_tree,
  acquire_writer,
  exists,
  list_names,
  directory_exists,
  list_directories,
};

class OperationFailurePlatform final
    : public lmdj::project_io::ProjectStoragePlatform {
 public:
  explicit OperationFailurePlatform(
      std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner)
      : inner_(std::move(inner)) {}

  void arm(StorageOp op) {
    op_ = op;
    armed_ = true;
    fired_ = false;
  }
  bool fired() const noexcept { return fired_; }

  lmdj::foundation::Result<std::unique_ptr<lmdj::project_io::ProjectWriterLease>>
  acquire_writer(const std::filesystem::path& path) override {
    if (take(StorageOp::acquire_writer)) {
      return lmdj::foundation::Result<
          std::unique_ptr<lmdj::project_io::ProjectWriterLease>>::
          failure(injected());
    }
    return inner_->acquire_writer(path);
  }

  lmdj::foundation::Result<void> ensure_directory(
      const std::filesystem::path& path) override {
    if (take(StorageOp::ensure_directory)) {
      return lmdj::foundation::Result<void>::failure(injected());
    }
    return inner_->ensure_directory(path);
  }

  lmdj::foundation::Result<void> validate_managed_tree(
      const std::filesystem::path& path) const override {
    if (take(StorageOp::validate_managed_tree)) {
      return lmdj::foundation::Result<void>::failure(injected());
    }
    return inner_->validate_managed_tree(path);
  }

  lmdj::foundation::Result<bool> exists(
      const std::filesystem::path& path) const override {
    if (take(StorageOp::exists)) {
      return lmdj::foundation::Result<bool>::failure(injected());
    }
    return inner_->exists(path);
  }

  lmdj::foundation::Result<std::vector<std::string>> list_names(
      const std::filesystem::path& path) const override {
    if (take(StorageOp::list_names)) {
      return lmdj::foundation::Result<std::vector<std::string>>::failure(
          injected());
    }
    return inner_->list_names(path);
  }

  lmdj::foundation::Result<std::uint64_t> byte_length(
      const std::filesystem::path& path) const override {
    return inner_->byte_length(path);
  }
  lmdj::foundation::Result<std::vector<std::byte>> read_complete(
      const std::filesystem::path& path) const override {
    return inner_->read_complete(path);
  }
  lmdj::foundation::Result<void> create_immutable(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner_->create_immutable(path, bytes);
  }
  lmdj::foundation::Result<void> replace_complete(
      const std::filesystem::path& path,
      std::span<const std::byte> bytes) override {
    return inner_->replace_complete(path, bytes);
  }
  lmdj::foundation::Result<void> append_durable(
      const std::filesystem::path& path,
      std::uint64_t offset,
      std::span<const std::byte> bytes) override {
    return inner_->append_durable(path, offset, bytes);
  }
  lmdj::foundation::Result<void> remove(
      const std::filesystem::path& path) override {
    return inner_->remove(path);
  }
  lmdj::foundation::Result<std::vector<std::string>> list_directories(
      const std::filesystem::path& path) const override {
    if (take(StorageOp::list_directories)) {
      return lmdj::foundation::Result<std::vector<std::string>>::failure(
          injected());
    }
    return inner_->list_directories(path);
  }
  lmdj::foundation::Result<void> remove_tree(
      const std::filesystem::path& path) override {
    return inner_->remove_tree(path);
  }
  lmdj::foundation::Result<void> publish_directory_if_absent(
      const std::filesystem::path& from,
      const std::filesystem::path& to) override {
    return inner_->publish_directory_if_absent(from, to);
  }
  lmdj::foundation::Result<bool> directory_exists(
      const std::filesystem::path& path) const override {
    if (take(StorageOp::directory_exists)) {
      return lmdj::foundation::Result<bool>::failure(injected());
    }
    return inner_->directory_exists(path);
  }

 private:
  bool take(StorageOp op) const {
    if (!armed_ || op_ != op) return false;
    armed_ = false;
    fired_ = true;
    return true;
  }
  static lmdj::foundation::Error injected() {
    return lmdj::foundation::Error{
        ErrorCode::io_error,
        "injected storage operation failure",
    };
  }

  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> inner_;
  mutable StorageOp op_ = StorageOp::ensure_directory;
  mutable bool armed_ = false;
  mutable bool fired_ = false;
};

struct ApiEntryFault {
  static void throw_once(void*) {
    throw std::runtime_error("injected Host API fault");
  }
};

void arm_api_entry_fault(lmdj::facade::testing::ApiEntryHook& hook) {
  hook.context = nullptr;
  hook.invoke = &ApiEntryFault::throw_once;
  lmdj::facade::testing::set_api_entry_hook(&hook);
}

void test_initial_pattern_rejections_are_exact_and_write_nothing() {
  TempDirectory temp;
  Application application(config(temp.path()));

  struct Case {
    std::string_view label;
    Pattern pattern;
    std::string_view message;
  };

  const PatternId good_id{uuid(700)};
  const std::vector<Case> cases{
      {
          "uppercase uuid is not a lowercase uuid",
          Pattern{PatternId{"00000000-0000-4000-8000-00000000070A"}, 1, {}},
          "pattern id must be a lowercase UUID",
      },
      {
          "empty pattern id",
          Pattern{PatternId{""}, 1, {}},
          "pattern id must be a lowercase UUID",
      },
      {
          "bars 0 is outside the permitted set",
          Pattern{good_id, 0, {}},
          "pattern bars must be one of 1, 2, 4, or 8",
      },
      {
          "bars 3 is outside the permitted set",
          Pattern{good_id, 3, {}},
          "pattern bars must be one of 1, 2, 4, or 8",
      },
      {
          "bars 16 is outside the permitted set",
          Pattern{good_id, 16, {}},
          "pattern bars must be one of 1, 2, 4, or 8",
      },
      {
          "velocity 0 is below the permitted range",
          Pattern{good_id, 1, {{PadSlotId{0, 0}, 0, 240, 0}}},
          "pattern event is invalid",
      },
      {
          "velocity 128 is above the permitted range",
          Pattern{good_id, 1, {{PadSlotId{0, 0}, 0, 240, 128}}},
          "pattern event is invalid",
      },
      {
          "onset tick equals the one-bar limit",
          Pattern{good_id, 1, {{PadSlotId{0, 0}, 3'840, 1, 100}}},
          "pattern event is invalid",
      },
      {
          "onset tick equals the two-bar limit",
          Pattern{good_id, 2, {{PadSlotId{0, 0}, 7'680, 1, 100}}},
          "pattern event is invalid",
      },
      {
          "slot is outside the pad grid",
          Pattern{good_id, 1, {{PadSlotId{99, 0}, 0, 240, 100}}},
          "pattern event is invalid",
      },
      {
          "a later event is invalid while the first is valid",
          Pattern{
              good_id,
              1,
              {{PadSlotId{0, 0}, 0, 240, 100},
               {PadSlotId{0, 1}, 0, 240, 200}},
          },
          "pattern event is invalid",
      },
  };

  for (const auto& item : cases) {
    const auto project =
        temp.path() / (std::string(item.label.substr(0, 12)) + ".lmdj");
    const auto rejected = application.create_initial_project(
        InitialProjectRequest{
            project,
            ProjectId{uuid(701)},
            120,
            item.pattern,
        });
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
    LMDJ_CHECK(rejected.error().message == item.message);
    // A refused request is not a partial one: nothing may reach the disk.
    LMDJ_CHECK(!std::filesystem::exists(project));
  }

  // The boundary values the rejections sit against must still be accepted, so
  // the matrix above cannot pass by refusing everything.
  const std::vector<std::uint8_t> accepted_bars{1, 2, 4, 8};
  for (const auto bars : accepted_bars) {
    const auto project =
        temp.path() /
        ("accepted-" + std::to_string(static_cast<unsigned>(bars)) + ".lmdj");
    const auto created = application.create_initial_project(
        InitialProjectRequest{
            project,
            ProjectId{uuid(710U + bars)},
            120,
            Pattern{
                PatternId{uuid(720U + bars)},
                bars,
                {{PadSlotId{0, 0},
                  static_cast<std::uint32_t>(bars) *
                          lmdj::domain::kBarTicks4x4 -
                      1U,
                  1,
                  127},
                 {PadSlotId{0, 0}, 0, 1, 1}},
            },
        });
    LMDJ_CHECK(created.has_value());
    LMDJ_CHECK(created.value().revision == 0);
  }
}

void test_every_trigger_mode_round_trips_through_the_json_surface() {
  TempDirectory temp;
  const auto project = temp.path() / "trigger-modes.lmdj";
  Application application(sample_config(temp.path()));
  const auto created = application.create_initial_project(
      InitialProjectRequest{
          project,
          ProjectId{uuid(760)},
          120,
          Pattern{PatternId{uuid(761)}, 1, {}},
      });
  LMDJ_CHECK(created.has_value());

  // Every mode the domain defines, including the two the serializer would
  // otherwise never be asked to name.
  const std::vector<std::pair<TriggerMode, std::string_view>> modes{
      {TriggerMode::one_shot, "one_shot"},
      {TriggerMode::gate, "gate"},
      {TriggerMode::loop_gate, "loop_gate"},
      {TriggerMode::loop_toggle, "loop_toggle"},
  };

  // update_sample_pad requires a Sample on the Pad, so land one first.
  const auto source = file_bytes("tests/fixtures/audio/mono-44100.wav");
  const auto token = uuid(764);
  const auto begun = application.begin_sample_import(
      SampleImportBeginRequest{
          token,
          project,
          CommandMeta{CommandId{uuid(765)}, 0},
          PadSlotId{0, 0},
          AssetId{uuid(766)},
          source.size(),
      });
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(application
                 .append_sample_import(
                     token,
                     0,
                     std::span<const std::byte>{source.data(), source.size()},
                     true)
                 .has_value());
  const auto committed = application.commit_sample_import(token);
  LMDJ_CHECK(committed.has_value());

  std::uint64_t revision = committed.value().committed_revision;
  std::uint32_t command = 770;
  for (const auto& [mode, name] : modes) {
    const auto updated = application.update_sample_pad(
        SampleUpdateRequest{
            project,
            CommandMeta{CommandId{uuid(command)}, revision},
            PadSlotId{0, 0},
            PadPlayback{0, std::nullopt, mode, 0, false},
        });
    LMDJ_CHECK(updated.has_value());
    revision = updated.value().committed_revision;
    command += 1;

    // Typed surface and JSON surface must agree on the same stored mode.
    const auto inspected =
        application.inspect_sample(SampleInspectRequest{project, {0, 0}});
    LMDJ_CHECK(inspected.has_value());
    LMDJ_CHECK(inspected.value().playback.trigger_mode == mode);

    const auto json = application.query(
        {
            {"operation", "sample.inspect"},
            {"project_path", project.generic_string()},
            {"slot", slot(0, 0)},
        });
    LMDJ_CHECK(json.at("ok") == true);
    LMDJ_CHECK(
        json.at("result").at("playback").at("trigger_mode") == name);
  }
}

void test_every_public_entry_converts_an_unexpected_throw_to_its_envelope() {
  TempDirectory temp;
  const auto project = temp.path() / "entry-faults.lmdj";
  Application application(sample_config(temp.path()));
  LMDJ_CHECK(application
                 .create_initial_project(InitialProjectRequest{
                     project,
                     ProjectId{uuid(780)},
                     120,
                     Pattern{PatternId{uuid(781)}, 1, {}},
                 })
                 .has_value());

  lmdj::facade::testing::ApiEntryHook hook{};

  // Typed entries: the contract is a failed Result carrying internal_error and
  // the exact public message, never an escaping exception.
  const auto check_typed = [&](std::string_view label, auto&& call) {
    arm_api_entry_fault(hook);
    const auto result = call();
    LMDJ_CHECK(!result.has_value());
    if (result.error().code != ErrorCode::internal_error) {
      throw std::runtime_error(
          std::string("entry did not report internal_error: ") +
          std::string(label));
    }
    if (result.error().message !=
        "unexpected Application Facade Host API failure") {
      throw std::runtime_error(
          std::string("entry reported the wrong public message: ") +
          std::string(label));
    }
  };

  check_typed("create_initial_project", [&] {
    return application.create_initial_project(InitialProjectRequest{
        temp.path() / "second.lmdj",
        ProjectId{uuid(782)},
        120,
        Pattern{PatternId{uuid(783)}, 1, {}},
    });
  });
  check_typed("list_local_projects", [&] {
    return application.list_local_projects();
  });
  check_typed("inspect_sample", [&] {
    return application.inspect_sample(SampleInspectRequest{project, {0, 0}});
  });
  check_typed("begin_sample_import", [&] {
    return application.begin_sample_import(SampleImportBeginRequest{
        uuid(784),
        project,
        CommandMeta{CommandId{uuid(785)}, 0},
        PadSlotId{0, 0},
        AssetId{uuid(786)},
        16,
    });
  });
  check_typed("commit_sample_import", [&] {
    return application.commit_sample_import(uuid(784));
  });
  check_typed("update_sample_pad", [&] {
    return application.update_sample_pad(SampleUpdateRequest{
        project,
        CommandMeta{CommandId{uuid(787)}, 0},
        PadSlotId{0, 0},
        PadPlayback{},
    });
  });
  check_typed("reset_sample_pad", [&] {
    return application.reset_sample_pad(SampleResetRequest{
        project,
        CommandMeta{CommandId{uuid(788)}, 0},
        PadSlotId{0, 0},
    });
  });
  check_typed("acquire_project_writer", [&] {
    return application.acquire_project_writer(project);
  });
  const lmdj::foundation::SequenceSessionId sequence_session{uuid(789)};
  const lmdj::foundation::PatternId sequence_pattern{uuid(781)};
  check_typed("begin_sequence", [&] {
    return application.begin_sequence(
        {project, sequence_session, sequence_pattern, 0, 0});
  });
  check_typed("record_sequence_event", [&] {
    return application.record_sequence_event(
        {project, sequence_session, {{0, 0}, 100, 0, 1, true}});
  });
  check_typed("flush_sequence", [&] {
    return application.flush_sequence(
        {project, sequence_session, CommandId{uuid(790)}, 0});
  });
  check_typed("stop_sequence", [&] {
    return application.stop_sequence(
        {project, sequence_session, CommandId{uuid(791)}, 0});
  });
  check_typed("request_sequence_switch", [&] {
    return application.request_sequence_switch(
        {project, sequence_session, lmdj::foundation::PatternId{uuid(792)}});
  });
  check_typed("query_sequence_status", [&] {
    return application.query_sequence_status({project});
  });
  check_typed("list_sequence_recovery", [&] {
    return application.list_sequence_recovery({project});
  });
  check_typed("apply_sequence_recovery", [&] {
    return application.apply_sequence_recovery(
        {project, sequence_session, std::nullopt});
  });
  check_typed("discard_sequence_recovery", [&] {
    return application.discard_sequence_recovery(
        {project, sequence_session, std::nullopt});
  });

  // JSON entries answer with the envelope form of the same failure, so a Host
  // reading JSON sees a well-formed refusal rather than a truncated response.
  const auto check_json = [&](std::string_view label, auto&& call) {
    arm_api_entry_fault(hook);
    const auto envelope = call();
    LMDJ_CHECK(envelope.at("ok") == false);
    if (envelope.at("error").at("code") != "INTERNAL_ERROR") {
      throw std::runtime_error(
          std::string("JSON entry did not report INTERNAL_ERROR: ") +
          std::string(label));
    }
    LMDJ_CHECK(
        envelope.at("error").at("message") == "unexpected application failure");
  };

  check_json("command", [&] {
    return application.command({
        {"operation", "project.inspect"},
        {"project_path", project.generic_string()},
    });
  });
  check_json("query", [&] {
    return application.query({
        {"operation", "project.inspect"},
        {"project_path", project.generic_string()},
    });
  });

  // The hook is one-shot: after every armed call above fired, an unarmed call
  // must behave normally. Without this the suite could pass while leaving the
  // facade permanently faulted for later tests.
  const auto healthy = application.query({
      {"operation", "project.inspect"},
      {"project_path", project.generic_string()},
  });
  LMDJ_CHECK(healthy.at("ok") == true);
  lmdj::facade::testing::set_api_entry_hook(nullptr);
}

void test_sample_import_publishes_its_limit_and_storage_refusals() {
  TempDirectory temp;
  const auto project = temp.path() / "import-failures.lmdj";

  auto failing = std::make_shared<OperationFailurePlatform>(
      lmdj::project_io::make_default_project_storage_platform());
  auto configured = sample_config(temp.path());
  configured.storage_platform = failing;
  Application application(std::move(configured));

  LMDJ_CHECK(application
                 .create_initial_project(InitialProjectRequest{
                     project,
                     ProjectId{uuid(800)},
                     120,
                     Pattern{PatternId{uuid(801)}, 1, {}},
                 })
                 .has_value());

  const auto begin = [&](std::uint32_t seed) {
    return application.begin_sample_import(SampleImportBeginRequest{
        uuid(seed),
        project,
        CommandMeta{CommandId{uuid(seed + 100)}, 0},
        PadSlotId{0, 0},
        AssetId{uuid(seed + 200)},
        16,
    });
  };

  // Storage refusals: each seam reports io_error with the message naming the
  // stage that failed, so an operator can tell which step refused.
  const std::vector<std::pair<StorageOp, std::string_view>> seams{
      {StorageOp::ensure_directory, "Sample staging could not be created"},
      {StorageOp::validate_managed_tree, "Sample staging tree is invalid"},
      {StorageOp::acquire_writer,
       "Sample staging writer could not be acquired"},
      {StorageOp::exists, "Sample staging could not be inspected"},
  };
  std::uint32_t seed = 810;
  for (const auto& [op, message] : seams) {
    failing->arm(op);
    const auto refused = begin(seed);
    seed += 10;
    LMDJ_CHECK(failing->fired());
    LMDJ_CHECK(!refused.has_value());
    LMDJ_CHECK(refused.error().code == ErrorCode::io_error);
    if (refused.error().message != message) {
      throw std::runtime_error(
          "storage refusal reported the wrong stage: " +
          refused.error().message);
    }
  }

  // The session limit is a published resource bound: it must name the
  // resource, what was observed, and the limit, so a Host can explain itself.
  std::vector<std::string> tokens;
  for (std::uint32_t index = 0; index < 16U; ++index) {
    const auto opened = begin(900 + index);
    LMDJ_CHECK(opened.has_value());
    tokens.push_back(uuid(900 + index));
  }
  const auto over_limit = begin(950);
  LMDJ_CHECK(!over_limit.has_value());
  LMDJ_CHECK(over_limit.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      over_limit.error().message == "Sample import session limit reached");
  LMDJ_CHECK(
      over_limit.error().details.at("resource") == "sample_import_sessions");
  LMDJ_CHECK(over_limit.error().details.at("limit") == 16);
  LMDJ_CHECK(over_limit.error().details.at("observed") == 17);

  // Releasing one session must make room again: the limit is a live count,
  // not a one-way latch.
  LMDJ_CHECK(application.abort_sample_import(tokens.front()).has_value());
  const auto after_release = begin(960);
  LMDJ_CHECK(after_release.has_value());
}

void test_startup_refuses_a_workspace_whose_staging_cannot_be_read() {
  TempDirectory temp;

  const auto construct_with = [&](StorageOp op) {
    auto failing = std::make_shared<OperationFailurePlatform>(
        lmdj::project_io::make_default_project_storage_platform());
    auto configured = sample_config(temp.path());
    configured.storage_platform = failing;
    failing->arm(op);
    bool threw = false;
    try {
      Application application(std::move(configured));
    } catch (const std::exception&) {
      threw = true;
    }
    return std::pair{threw, failing->fired()};
  };

  // The staging root cannot be inspected.
  const auto inspect_failed = construct_with(StorageOp::directory_exists);
  LMDJ_CHECK(inspect_failed.second);
  LMDJ_CHECK(inspect_failed.first);

  // A staging root that exists but cannot be listed is equally unaccounted
  // for, so it must refuse too rather than silently proceed.
  {
    auto seeding = std::make_shared<OperationFailurePlatform>(
        lmdj::project_io::make_default_project_storage_platform());
    auto configured = sample_config(temp.path());
    configured.storage_platform = seeding;
    Application application(std::move(configured));
    const auto project = temp.path() / "staging-seed.lmdj";
    LMDJ_CHECK(application
                   .create_initial_project(InitialProjectRequest{
                       project,
                       ProjectId{uuid(820)},
                       120,
                       Pattern{PatternId{uuid(821)}, 1, {}},
                   })
                   .has_value());
    LMDJ_CHECK(application
                   .begin_sample_import(SampleImportBeginRequest{
                       uuid(822),
                       project,
                       CommandMeta{CommandId{uuid(823)}, 0},
                       PadSlotId{0, 0},
                       AssetId{uuid(824)},
                       16,
                   })
                   .has_value());
  }
  const auto list_failed = construct_with(StorageOp::list_directories);
  LMDJ_CHECK(list_failed.second);
  LMDJ_CHECK(list_failed.first);

  // With storage healthy the same workspace constructs and cleans normally,
  // so the refusals above cannot be an artefact of the seeded staging.
  auto healthy = std::make_shared<OperationFailurePlatform>(
      lmdj::project_io::make_default_project_storage_platform());
  auto configured = sample_config(temp.path());
  configured.storage_platform = healthy;
  Application application(std::move(configured));
  LMDJ_CHECK(!healthy->fired());
}

}  // namespace

int main() {
  try {
    test_initial_pattern_rejections_are_exact_and_write_nothing();
    test_every_trigger_mode_round_trips_through_the_json_surface();
    test_every_public_entry_converts_an_unexpected_throw_to_its_envelope();
    test_sample_import_publishes_its_limit_and_storage_refusals();
    test_startup_refuses_a_workspace_whose_staging_cannot_be_read();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "application facade failure contract tests: PASS\n";
  return 0;
}
