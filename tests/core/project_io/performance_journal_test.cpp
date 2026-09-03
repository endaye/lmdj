#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::PadHitPerformanceEvent;
using lmdj::domain::Performance;
using lmdj::domain::PerformanceEvent;
using lmdj::domain::PerformanceId;
using lmdj::domain::ProjectContract;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ProjectId;
using lmdj::foundation::SequenceSessionId;
using lmdj::project_io::CreatePerformance;
using lmdj::project_io::DeletePerformance;
using lmdj::project_io::PerformanceFlushIdentity;
using lmdj::project_io::PerformanceOpenPadTransient;
using lmdj::project_io::PerformanceTransientCheckpoint;
using lmdj::project_io::ProjectStore;
using lmdj::project_io::RenamePerformance;
using lmdj::project_io::SequenceJournal;
using lmdj::project_io::SessionKind;
using lmdj::project_io::testing::FaultPoint;

constexpr std::string_view kProjectId =
    "00000000-0000-4000-8000-000000000001";
constexpr std::string_view kPerformanceId =
    "10000000-0000-4000-8000-000000000001";
constexpr std::string_view kSessionId =
    "20000000-0000-4000-8000-000000000001";
constexpr std::string_view kCommandId =
    "30000000-0000-4000-8000-000000000001";
constexpr std::string_view kSecondCommandId =
    "30000000-0000-4000-8000-000000000002";
constexpr std::string_view kThirdCommandId =
    "30000000-0000-4000-8000-000000000003";

class TempDirectory {
 public:
  explicit TempDirectory(std::string_view label) {
    const auto nonce = std::chrono::steady_clock::now()
                           .time_since_epoch()
                           .count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-performance-journal-" + std::string(label) + "-" +
             std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
  }

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

PerformanceEvent pad_hit(std::uint8_t slot, std::uint64_t tick) {
  return PerformanceEvent{PadHitPerformanceEvent{slot, tick, 120, 100}};
}

Performance empty_performance() {
  return {
      PerformanceId{std::string{kPerformanceId}},
      "Live set",
      120,
      0,
      std::nullopt,
      {},
  };
}

lmdj::domain::ProjectState project_with_performance() {
  auto created = lmdj::domain::create_project(
      ProjectId{std::string{kProjectId}}, 120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  state.contract = ProjectContract::v4;
  auto performance = empty_performance();
  state.performances.emplace(performance.id, performance);
  return state;
}

std::filesystem::path create_bundle(
    TempDirectory& temp,
    ProjectStore& store) {
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, project_with_performance()).has_value());
  return bundle;
}

std::filesystem::path create_empty_v3_bundle(
    TempDirectory& temp,
    ProjectStore& store) {
  auto created = lmdj::domain::create_project(
      ProjectId{std::string{kProjectId}}, 120);
  LMDJ_CHECK(created.has_value());
  auto state = std::move(created.value());
  state.contract = ProjectContract::v3;
  const auto bundle = temp.path() / "project.lmdj";
  LMDJ_CHECK(store.create(bundle, state).has_value());
  return bundle;
}

std::string read_text(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  return {
      std::istreambuf_iterator<char>{stream},
      std::istreambuf_iterator<char>{},
  };
}

std::string sha256(std::string_view bytes) {
  picosha2::hash256_one_by_one hasher;
  hasher.process(bytes.begin(), bytes.end());
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

std::string checked_line(nlohmann::json payload) {
  const auto canonical = lmdj::foundation::canonical_json(payload);
  return lmdj::foundation::canonical_json(
             {{"checksum", sha256(canonical)},
              {"payload", std::move(payload)}}) +
         "\n";
}

void write_text(const std::filesystem::path& path, std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

void append_text(const std::filesystem::path& path, std::string_view bytes) {
  std::ofstream stream(path, std::ios::binary | std::ios::app);
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

FaultPoint selected_fault = FaultPoint::sequence_journal_write;

lmdj::foundation::Result<void> fail_selected(
    FaultPoint point,
    const std::filesystem::path& path) {
  if (point != selected_fault) {
    return lmdj::foundation::Result<void>::success();
  }
  return lmdj::foundation::Result<void>::failure(lmdj::foundation::Error{
      ErrorCode::io_error,
      "injected Performance fault",
      {{"path", path.generic_string()}},
  });
}

class FaultGuard {
 public:
  explicit FaultGuard(FaultPoint point) {
    selected_fault = point;
    lmdj::project_io::testing::set_fault_hook(fail_selected);
  }

  ~FaultGuard() {
    lmdj::project_io::testing::set_fault_hook(nullptr);
  }

 private:
  FaultGuard(const FaultGuard&) = delete;
  FaultGuard& operator=(const FaultGuard&) = delete;
};

void test_performance_transient_checkpoint_round_trips_empty_tail_transition() {
  TempDirectory temp("transient-checkpoint");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};

  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const auto begun = journal.read_active_performance(bundle);
  LMDJ_CHECK(begun.has_value());
  LMDJ_CHECK(begun.value().transient_checkpoint.has_value());
  LMDJ_CHECK(
      begun.value().transient_checkpoint == PerformanceTransientCheckpoint{});

  const PerformanceTransientCheckpoint pressed{
      {PerformanceOpenPadTransient{
          std::string{kCommandId}, 5, 42, 100}},
      {},
      false,
      42,
  };
  const std::vector<PerformanceEvent> no_canonical_events;
  LMDJ_CHECK(
      journal
          .append_performance_tail(
              bundle,
              session_id,
              performance.id,
              0,
              1,
              no_canonical_events,
              pressed)
          .has_value());
  const auto restored = journal.read_active_performance(bundle);
  LMDJ_CHECK(restored.has_value());
  LMDJ_CHECK(restored.value().pending_events.empty());
  LMDJ_CHECK(restored.value().last_input_sequence == 1);
  LMDJ_CHECK(restored.value().transient_checkpoint == pressed);
}

void test_post_write_tail_failure_is_reported_as_ambiguous_and_retained() {
  TempDirectory temp("transient-ambiguous");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const std::vector events{pad_hit(2, 42)};
  lmdj::foundation::Result<void> appended =
      lmdj::foundation::Result<void>::success();
  {
    FaultGuard fault(FaultPoint::active_journal_sync);
    appended = journal.append_performance_tail(
        bundle,
        session_id,
        performance.id,
        0,
        1,
        events,
        PerformanceTransientCheckpoint{{}, {}, false, 42});
  }
  LMDJ_CHECK(!appended.has_value());
  LMDJ_CHECK(
      appended.error().details.at("reason") ==
      "performance_tail_outcome_unknown");
  const auto retained = journal.read_active_performance(bundle);
  LMDJ_CHECK(retained.has_value());
  LMDJ_CHECK(retained.value().pending_events == events);
  LMDJ_CHECK(retained.value().last_input_sequence == 1);
  LMDJ_CHECK(retained.value().transient_checkpoint.has_value());
  LMDJ_CHECK(
      retained.value().transient_checkpoint->last_accepted_tick == 42);
}

void test_performance_seal_replays_stable_candidate_without_suffix() {
  TempDirectory temp("stable-seal");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const std::vector events{pad_hit(2, 42)};
  LMDJ_CHECK(
      journal
          .append_performance_tail(
              bundle,
              session_id,
              performance.id,
              0,
              1,
              events,
              PerformanceTransientCheckpoint{{}, {}, false, 42})
          .has_value());
  const auto active_path = bundle / "recovery/active/performance.jsonl";
  const auto active_bytes = read_text(active_path);
  const auto sealed = journal.seal_performance(
      bundle, session_id, "owner_lost");
  LMDJ_CHECK(sealed.has_value());
  LMDJ_CHECK(
      sealed.value().filename() ==
      std::string{kSessionId} + "-performance-owner_lost.json");

  write_text(active_path, active_bytes);
  const auto replayed = journal.seal_performance(
      bundle, session_id, "owner_lost");
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value() == sealed.value());
  LMDJ_CHECK(!std::filesystem::exists(active_path));
  LMDJ_CHECK(journal.list_performance_recoverable(bundle).value().size() == 1);

  write_text(active_path, active_bytes);
  const auto conflict = journal.seal_performance(
      bundle, session_id, "different_reason");
  LMDJ_CHECK(!conflict.has_value());
  LMDJ_CHECK(
      conflict.error().details.at("reason") ==
      "performance_recovery_candidate_conflict");
  LMDJ_CHECK(std::filesystem::exists(active_path));
  LMDJ_CHECK(std::filesystem::exists(sealed.value()));
  LMDJ_CHECK(journal.list_performance_recoverable(bundle).value().size() == 1);
}

void test_owner_loss_closes_fx_chain_then_hold_at_one_tick() {
  TempDirectory temp("transient-fx-hold");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const std::vector<PerformanceEvent> events{
      PerformanceEvent{lmdj::domain::FxEngagePerformanceEvent{
          lmdj::domain::PerformanceFx::filter, 500, 10}},
      PerformanceEvent{lmdj::domain::FxMovePerformanceEvent{
          lmdj::domain::PerformanceFx::filter, 600, 20}},
      PerformanceEvent{lmdj::domain::FxEngagePerformanceEvent{
          lmdj::domain::PerformanceFx::reverse, 800, 30}},
      PerformanceEvent{lmdj::domain::HoldOnPerformanceEvent{40}},
  };
  const PerformanceTransientCheckpoint checkpoint{
      {},
      {lmdj::project_io::PerformanceOpenFxTransient{
           lmdj::domain::PerformanceFx::filter,
           "50000000-0000-4000-8000-000000000001",
           500,
           600},
       lmdj::project_io::PerformanceOpenFxTransient{
           lmdj::domain::PerformanceFx::reverse,
           "50000000-0000-4000-8000-000000000002",
           800,
           std::nullopt}},
      true,
      40,
  };
  LMDJ_CHECK(
      journal
          .append_performance_tail(
              bundle,
              session_id,
              performance.id,
              0,
              1,
              events,
              checkpoint)
          .has_value());
  const auto preview = lmdj::project_io::preview_performance_owner_loss(
      journal.read_active_performance(bundle).value());
  LMDJ_CHECK(preview.has_value());
  LMDJ_CHECK(preview.value().appended_event_count == 3);
  LMDJ_CHECK(preview.value().closure_tick == 41);
  LMDJ_CHECK(preview.value().canonical_events.size() == 7);
  const auto &filter_release =
      std::get<lmdj::domain::FxReleasePerformanceEvent>(
          preview.value().canonical_events.at(4).payload);
  const auto &reverse_release =
      std::get<lmdj::domain::FxReleasePerformanceEvent>(
          preview.value().canonical_events.at(5).payload);
  LMDJ_CHECK(filter_release.fx == lmdj::domain::PerformanceFx::filter);
  LMDJ_CHECK(reverse_release.fx == lmdj::domain::PerformanceFx::reverse);
  LMDJ_CHECK(
      std::get<lmdj::domain::HoldOffPerformanceEvent>(
          preview.value().canonical_events.at(6).payload)
          .tick == 41);

  LMDJ_CHECK(
      journal
          .close_performance_transients_for_owner_loss(bundle, session_id)
          .has_value());
  const auto closed = journal.read_active_performance(bundle);
  LMDJ_CHECK(closed.has_value());
  LMDJ_CHECK(closed.value().pending_events ==
             preview.value().canonical_events);
  LMDJ_CHECK(closed.value().last_input_sequence == 2);
  LMDJ_CHECK(closed.value().transient_checkpoint.has_value());
  LMDJ_CHECK((closed.value().transient_checkpoint ==
              PerformanceTransientCheckpoint{{}, {}, false, 41}));
  LMDJ_CHECK(
      journal
          .close_performance_transients_for_owner_loss(bundle, session_id)
          .has_value());
  LMDJ_CHECK(
      journal.read_active_performance(bundle).value().next_tail_seq == 2);
}

void test_legacy_and_malformed_checkpoint_streams_fail_closed() {
  TempDirectory temp("checkpoint-validation");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto active_path = bundle / "recovery/active/performance.jsonl";
  const auto performance = empty_performance();
  const auto legacy_begin = nlohmann::json{
      {"contract", "lmdj.performance.journal.v1"},
      {"expected_revision", 0},
      {"kind", "begin"},
      {"performance_fingerprint",
       lmdj::project_io::performance_fingerprint(performance)},
      {"performance_id", kPerformanceId},
      {"session_id", kSessionId},
  };
  write_text(active_path, checked_line(legacy_begin));
  const auto active_legacy = journal.read_active_performance(bundle);
  LMDJ_CHECK(!active_legacy.has_value());
  LMDJ_CHECK(active_legacy.error().code == ErrorCode::invalid_project);
  append_text(
      active_path,
      checked_line({
          {"kind", "stop"},
          {"request_id", kCommandId},
      }));
  const auto stopped_legacy = journal.read_active_performance(bundle);
  LMDJ_CHECK(stopped_legacy.has_value());
  LMDJ_CHECK(stopped_legacy.value().transient_checkpoint.has_value());
  LMDJ_CHECK(
      stopped_legacy.value().transient_checkpoint->open_pads.empty());

  auto malformed_begin = legacy_begin;
  malformed_begin["transient_checkpoint"] = {
      {"hold", false},
      {"last_accepted_tick", 0},
      {"open_fx", nlohmann::json::array()},
      {"open_pads",
       nlohmann::json::array({
           {{"gesture_id", kCommandId},
            {"onset_tick", 0},
            {"slot", 300},
            {"velocity", 1}},
       })},
  };
  write_text(active_path, checked_line(std::move(malformed_begin)));
  const auto malformed = journal.read_active_performance(bundle);
  LMDJ_CHECK(!malformed.has_value());
  LMDJ_CHECK(
      malformed.error().details.at("reason") ==
      "performance_transient_checkpoint_invalid");
}

void test_owner_loss_refuses_tick_and_input_sequence_overflow() {
  {
    TempDirectory temp("closure-tick-overflow");
    ProjectStore store;
    const auto bundle = create_bundle(temp, store);
    SequenceJournal journal;
    const auto performance = empty_performance();
    const auto session_id = SequenceSessionId{std::string{kSessionId}};
    LMDJ_CHECK(
        journal
            .begin_performance(
                bundle,
                session_id,
                performance.id,
                lmdj::project_io::performance_fingerprint(performance),
                0)
            .has_value());
    const auto maximum = std::numeric_limits<std::uint64_t>::max();
    const std::vector<PerformanceEvent> events{
        PerformanceEvent{lmdj::domain::HoldOnPerformanceEvent{maximum}}};
    LMDJ_CHECK(
        journal
            .append_performance_tail(
                bundle,
                session_id,
                performance.id,
                0,
                1,
                events,
                PerformanceTransientCheckpoint{{}, {}, true, maximum})
            .has_value());
    const auto preview = lmdj::project_io::preview_performance_owner_loss(
        journal.read_active_performance(bundle).value());
    LMDJ_CHECK(!preview.has_value());
    LMDJ_CHECK(preview.error().details.at("reason") ==
               "performance_tick_overflow");
  }
  {
    TempDirectory temp("closure-sequence-overflow");
    ProjectStore store;
    const auto bundle = create_bundle(temp, store);
    SequenceJournal journal;
    const auto performance = empty_performance();
    const auto session_id = SequenceSessionId{std::string{kSessionId}};
    LMDJ_CHECK(
        journal
            .begin_performance(
                bundle,
                session_id,
                performance.id,
                lmdj::project_io::performance_fingerprint(performance),
                0)
            .has_value());
    const std::vector<PerformanceEvent> no_events;
    LMDJ_CHECK(
        journal
            .append_performance_tail(
                bundle,
                session_id,
                performance.id,
                0,
                std::numeric_limits<std::uint64_t>::max(),
                no_events,
                PerformanceTransientCheckpoint{
                    {PerformanceOpenPadTransient{
                        std::string{kCommandId}, 0, 0, 100}},
                    {},
                    false,
                    0})
            .has_value());
    const auto closed =
        journal.close_performance_transients_for_owner_loss(
            bundle, session_id);
    LMDJ_CHECK(!closed.has_value());
    LMDJ_CHECK(closed.error().details.at("reason") ==
               "performance_input_sequence_overflow");
  }
}

void test_performance_flush_is_durable_before_mutation_and_replays() {
  TempDirectory temp("flush");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto command_id = CommandId{std::string{kCommandId}};
  const std::vector events{pad_hit(1, 480)};

  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  LMDJ_CHECK(
      journal
          .append_performance_tail(
              bundle, session_id, performance.id, 0, 1, events)
          .has_value());
  const auto flush = journal.append_performance_flush(
      bundle, session_id, command_id, performance.id, 0, events);
  LMDJ_CHECK(flush.has_value());
  LMDJ_CHECK(flush.value().kind == SessionKind::performance);
  LMDJ_CHECK(flush.value().flush_seq == 0);
  LMDJ_CHECK(flush.value().canonical_events == events);
  LMDJ_CHECK(
      read_text(bundle / "recovery/active/performance.jsonl")
          .find(std::string{kCommandId}) != std::string::npos);
  LMDJ_CHECK(store.load(bundle).value().revision == 0);
  LMDJ_CHECK(
      store.load(bundle).value().performances.at(performance.id).events.empty());

  const PerformanceFlushIdentity identity{
      session_id,
      flush.value().flush_seq,
      command_id,
      performance.id,
  };
  const auto retained = journal.remove_active_performance_if_complete(
      bundle, session_id);
  LMDJ_CHECK(!retained.has_value());
  LMDJ_CHECK(retained.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(
      std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));

  const auto committed = store.execute_performance_flush(bundle, identity);
  LMDJ_CHECK(committed.has_value());
  LMDJ_CHECK(!committed.value().replayed);
  LMDJ_CHECK(committed.value().receipt.committed_revision == 1);
  LMDJ_CHECK(committed.value().state.contract == ProjectContract::v4);
  LMDJ_CHECK(
      committed.value().state.performances.at(performance.id).events == events);

  const auto replayed = store.execute_performance_flush(bundle, identity);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().receipt == committed.value().receipt);
  LMDJ_CHECK(replayed.value().state.revision == 1);

  const std::vector second_events{pad_hit(2, 960)};
  const auto second_flush = journal.append_performance_flush(
      bundle,
      session_id,
      CommandId{std::string{kSecondCommandId}},
      performance.id,
      1,
      second_events);
  LMDJ_CHECK(second_flush.has_value());
  const auto still_retained = journal.remove_active_performance_if_complete(
      bundle, session_id);
  LMDJ_CHECK(!still_retained.has_value());
  LMDJ_CHECK(
      std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
  const auto second_committed = store.execute_performance_flush(
      bundle,
      {session_id,
       second_flush.value().flush_seq,
       CommandId{std::string{kSecondCommandId}},
       performance.id});
  LMDJ_CHECK(second_committed.has_value());
  LMDJ_CHECK(second_committed.value().state.revision == 2);

  LMDJ_CHECK(
      journal.remove_active_performance_if_complete(bundle, session_id)
          .has_value());
  LMDJ_CHECK(
      !std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
}

void test_performance_begin_append_complete_seal_and_recover_listing() {
  TempDirectory temp("seal");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const std::vector events{pad_hit(2, 960)};

  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const auto flush = journal.append_performance_flush(
      bundle,
      session_id,
      CommandId{std::string{kCommandId}},
      performance.id,
      0,
      events);
  LMDJ_CHECK(flush.has_value());
  const auto sealed = journal.seal_performance(
      bundle, session_id, "owner_lost");
  LMDJ_CHECK(sealed.has_value());
  LMDJ_CHECK(std::filesystem::exists(sealed.value()));
  LMDJ_CHECK(
      !std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));

  const auto candidates = journal.list_performance_recoverable(bundle);
  LMDJ_CHECK(candidates.has_value());
  LMDJ_CHECK(candidates.value().size() == 1);
  LMDJ_CHECK(candidates.value().front().journal.kind ==
             SessionKind::performance);
  LMDJ_CHECK(candidates.value().front().journal.flushes.size() == 1);
  LMDJ_CHECK(candidates.value().front().journal.flushes.front().canonical_events ==
             events);
  LMDJ_CHECK(candidates.value().front().reason == "owner_lost");
}

void test_outstanding_performance_flush_blocks_tail_and_remains_recoverable() {
  TempDirectory temp("flush-blocks-tail");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const std::vector flush_events{pad_hit(1, 480)};

  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const auto flush = journal.append_performance_flush(
      bundle,
      session_id,
      CommandId{std::string{kCommandId}},
      performance.id,
      0,
      flush_events);
  LMDJ_CHECK(flush.has_value());

  const auto newer_tail = journal.append_performance_tail(
      bundle,
      session_id,
      performance.id,
      0,
      2,
      std::vector{pad_hit(2, 960)});
  LMDJ_CHECK(!newer_tail.has_value());
  LMDJ_CHECK(newer_tail.error().code == ErrorCode::invalid_argument);
  const auto invisible = store.replay_performance_flush(
      bundle,
      {session_id,
       flush.value().flush_seq,
       CommandId{std::string{kCommandId}},
       performance.id});
  LMDJ_CHECK(invisible.has_value());
  LMDJ_CHECK(!invisible.value().has_value());

  const auto reconciled = store.reconcile_performance_recovery(bundle);
  LMDJ_CHECK(reconciled.has_value());
  LMDJ_CHECK(reconciled.value().size() == 1);
  LMDJ_CHECK(
      !std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
  const auto& candidate = reconciled.value().front();
  LMDJ_CHECK(candidate.reason == "owner_lost");
  LMDJ_CHECK(candidate.journal.pending_events.empty());
  LMDJ_CHECK(candidate.journal.flushes.size() == 1);
  LMDJ_CHECK(!candidate.journal.flushes.front().completed);
  LMDJ_CHECK(
      candidate.journal.flushes.front().canonical_events == flush_events);
  LMDJ_CHECK(std::filesystem::exists(candidate.path));

  const auto listed_again = journal.list_performance_recoverable(bundle);
  LMDJ_CHECK(listed_again.has_value());
  LMDJ_CHECK(listed_again.value().size() == 1);
  LMDJ_CHECK(listed_again.value().front().path == candidate.path);
  LMDJ_CHECK(
      listed_again.value().front().journal.flushes.front().canonical_events ==
      flush_events);
}

void test_invalid_performance_event_bounds_never_mutate_journal_bytes() {
  const std::vector<PerformanceEvent> invalid_events{
      PerformanceEvent{PadHitPerformanceEvent{64, 0, 1, 1}},
      PerformanceEvent{PadHitPerformanceEvent{0, 0, 0, 1}},
      PerformanceEvent{PadHitPerformanceEvent{0, 0, 1, 0}},
      PerformanceEvent{PadHitPerformanceEvent{0, 0, 1, 128}},
      PerformanceEvent{
          lmdj::domain::PatternLaunchPerformanceEvent{16, 0}},
      PerformanceEvent{lmdj::domain::FxEngagePerformanceEvent{
          static_cast<lmdj::domain::PerformanceFx>(8), 0, 0}},
      PerformanceEvent{lmdj::domain::FxEngagePerformanceEvent{
          lmdj::domain::PerformanceFx::filter, 1'001, 0}},
      PerformanceEvent{lmdj::domain::FxMovePerformanceEvent{
          static_cast<lmdj::domain::PerformanceFx>(8), 0, 0}},
      PerformanceEvent{lmdj::domain::FxMovePerformanceEvent{
          lmdj::domain::PerformanceFx::filter, 1'001, 0}},
      PerformanceEvent{lmdj::domain::FxReleasePerformanceEvent{
          static_cast<lmdj::domain::PerformanceFx>(8), 0}},
  };

  for (std::size_t index = 0; index < invalid_events.size(); ++index) {
    for (const bool flush : {false, true}) {
      TempDirectory temp(
          "invalid-event-" + std::to_string(index) +
          (flush ? "-flush" : "-tail"));
      ProjectStore store;
      const auto bundle = create_bundle(temp, store);
      SequenceJournal journal;
      const auto performance = empty_performance();
      const auto session_id = SequenceSessionId{std::string{kSessionId}};
      LMDJ_CHECK(
          journal
              .begin_performance(
                  bundle,
                  session_id,
                  performance.id,
                  lmdj::project_io::performance_fingerprint(performance),
                  0)
              .has_value());
      const auto journal_path =
          bundle / "recovery/active/performance.jsonl";
      const auto before = read_text(journal_path);
      if (flush) {
        const auto rejected = journal.append_performance_flush(
            bundle,
            session_id,
            CommandId{std::string{kCommandId}},
            performance.id,
            0,
            std::vector{invalid_events.at(index)});
        LMDJ_CHECK(!rejected.has_value());
        LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
      } else {
        const auto rejected = journal.append_performance_tail(
            bundle,
            session_id,
            performance.id,
            0,
            1,
            std::vector{invalid_events.at(index)});
        LMDJ_CHECK(!rejected.has_value());
        LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
      }
      LMDJ_CHECK(read_text(journal_path) == before);
      LMDJ_CHECK(journal.read_active_performance(bundle).has_value());
    }
  }
}

void test_structurally_valid_stateful_events_are_admitted_independently() {
  const std::vector<PerformanceEvent> events{
      PerformanceEvent{PadHitPerformanceEvent{63, 1, 1, 127}},
      PerformanceEvent{
          lmdj::domain::PatternLaunchPerformanceEvent{15, 2}},
      PerformanceEvent{lmdj::domain::FxEngagePerformanceEvent{
          lmdj::domain::PerformanceFx::cutter, 1'000, 3}},
      PerformanceEvent{lmdj::domain::FxMovePerformanceEvent{
          lmdj::domain::PerformanceFx::filter, 0, 4}},
      PerformanceEvent{lmdj::domain::FxReleasePerformanceEvent{
          lmdj::domain::PerformanceFx::cutter, 5}},
      PerformanceEvent{lmdj::domain::HoldOnPerformanceEvent{6}},
      PerformanceEvent{lmdj::domain::HoldOffPerformanceEvent{7}},
  };
  for (const bool flush : {false, true}) {
    TempDirectory temp(flush ? "structural-flush" : "structural-tail");
    ProjectStore store;
    const auto bundle = create_bundle(temp, store);
    SequenceJournal journal;
    const auto performance = empty_performance();
    const auto session_id = SequenceSessionId{std::string{kSessionId}};
    LMDJ_CHECK(
        journal
            .begin_performance(
                bundle,
                session_id,
                performance.id,
                lmdj::project_io::performance_fingerprint(performance),
                0)
            .has_value());
    if (flush) {
      const auto appended = journal.append_performance_flush(
          bundle,
          session_id,
          CommandId{std::string{kCommandId}},
          performance.id,
          0,
          events);
      LMDJ_CHECK(appended.has_value());
      LMDJ_CHECK(appended.value().canonical_events == events);
    } else {
      LMDJ_CHECK(
          journal
              .append_performance_tail(
                  bundle, session_id, performance.id, 0, 1, events)
              .has_value());
      LMDJ_CHECK(
          journal.read_active_performance(bundle).value().pending_events ==
          events);
    }
  }
}

void test_empty_v3_project_creates_performance_then_begins_recording() {
  TempDirectory temp("v3-create-begin");
  ProjectStore store;
  const auto bundle = create_empty_v3_bundle(temp, store);
  const auto performance_id = PerformanceId{std::string{kPerformanceId}};
  const CreatePerformance command{
      {CommandId{std::string{kCommandId}}, 0},
      performance_id,
      "Untitled performance",
  };

  const auto migrated = store.create_performance(bundle, command);
  LMDJ_CHECK(migrated.has_value());
  LMDJ_CHECK(!migrated.value().replayed);
  LMDJ_CHECK(migrated.value().state.contract == ProjectContract::v4);
  LMDJ_CHECK(migrated.value().state.revision == 1);
  const auto& created =
      migrated.value().state.performances.at(performance_id);
  LMDJ_CHECK(created.name == "Untitled performance");
  LMDJ_CHECK(created.created_bpm == 120);
  LMDJ_CHECK(created.events.empty());

  const auto replayed = store.create_performance(bundle, command);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state.revision == 1);
  LMDJ_CHECK(replayed.value().event == migrated.value().event);

  SequenceJournal journal;
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance_id,
              lmdj::project_io::performance_fingerprint(created),
              1)
          .has_value());
  LMDJ_CHECK(
      journal.read_active_performance(bundle).value().performance_id ==
      performance_id);
}

void test_performance_crud_is_revision_bound_and_idempotent() {
  TempDirectory temp("performance-crud");
  ProjectStore store;
  const auto bundle = create_empty_v3_bundle(temp, store);
  const auto performance_id = PerformanceId{std::string{kPerformanceId}};
  const CreatePerformance create{
      {CommandId{std::string{kCommandId}}, 0},
      performance_id,
      "Untitled performance",
  };
  LMDJ_CHECK(store.create_performance(bundle, create).has_value());

  const auto manifest_before_conflict = read_text(bundle / "manifest.json");
  const auto stale = store.rename_performance(
      bundle,
      RenamePerformance{
          {CommandId{std::string{kSecondCommandId}}, 0},
          performance_id,
          "First take",
      });
  LMDJ_CHECK(!stale.has_value());
  LMDJ_CHECK(stale.error().code == ErrorCode::revision_conflict);
  LMDJ_CHECK(read_text(bundle / "manifest.json") == manifest_before_conflict);

  const RenamePerformance rename{
      {CommandId{std::string{kSecondCommandId}}, 1},
      performance_id,
      "First take",
  };
  const auto renamed = store.rename_performance(bundle, rename);
  LMDJ_CHECK(renamed.has_value());
  LMDJ_CHECK(!renamed.value().replayed);
  LMDJ_CHECK(renamed.value().state.revision == 2);
  LMDJ_CHECK(
      renamed.value().state.performances.at(performance_id).name ==
      "First take");

  ProjectStore restarted;
  const auto replayed_rename = restarted.rename_performance(bundle, rename);
  LMDJ_CHECK(replayed_rename.has_value());
  LMDJ_CHECK(replayed_rename.value().replayed);
  LMDJ_CHECK(replayed_rename.value().state.revision == 2);
  LMDJ_CHECK(replayed_rename.value().event == renamed.value().event);

  const auto collided = restarted.rename_performance(
      bundle,
      RenamePerformance{
          rename.meta,
          performance_id,
          "Different identity",
      });
  LMDJ_CHECK(!collided.has_value());
  LMDJ_CHECK(collided.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(restarted.load(bundle).value().revision == 2);

  const DeletePerformance remove{
      {CommandId{std::string{kThirdCommandId}}, 2},
      performance_id,
  };
  const auto removed = restarted.delete_performance(bundle, remove);
  LMDJ_CHECK(removed.has_value());
  LMDJ_CHECK(!removed.value().replayed);
  LMDJ_CHECK(removed.value().state.revision == 3);
  LMDJ_CHECK(!removed.value().state.performances.contains(performance_id));

  ProjectStore reloaded;
  const auto replayed_remove = reloaded.delete_performance(bundle, remove);
  LMDJ_CHECK(replayed_remove.has_value());
  LMDJ_CHECK(replayed_remove.value().replayed);
  LMDJ_CHECK(replayed_remove.value().state.revision == 3);
  LMDJ_CHECK(replayed_remove.value().event == removed.value().event);
  LMDJ_CHECK(!reloaded.load(bundle).value().performances.contains(
      performance_id));
}

void test_performance_create_recovers_each_persistence_fault() {
  for (const auto fault : {
           FaultPoint::sequence_transaction_write,
           FaultPoint::sequence_checkpoint_write,
           FaultPoint::sequence_manifest_publish,
       }) {
    TempDirectory temp("performance-create-fault");
    ProjectStore store;
    const auto bundle = create_empty_v3_bundle(temp, store);
    const CreatePerformance command{
        {CommandId{std::string{kCommandId}}, 0},
        PerformanceId{std::string{kPerformanceId}},
        "Untitled performance",
    };
    {
      FaultGuard injected(fault);
      const auto interrupted = store.create_performance(bundle, command);
      LMDJ_CHECK(!interrupted.has_value());
      LMDJ_CHECK(interrupted.error().code == ErrorCode::io_error);
    }
    const auto unchanged = store.load(bundle);
    LMDJ_CHECK(unchanged.has_value());
    LMDJ_CHECK(unchanged.value().revision == 0);
    LMDJ_CHECK(unchanged.value().performances.empty());

    const auto retried = store.create_performance(bundle, command);
    LMDJ_CHECK(retried.has_value());
    LMDJ_CHECK(!retried.value().replayed);
    LMDJ_CHECK(retried.value().state.revision == 1);
    LMDJ_CHECK(retried.value().state.performances.size() == 1);
  }
}

void test_visible_receipt_replays_after_journal_completion_failure() {
  TempDirectory temp("receipt-replay");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto command_id = CommandId{std::string{kCommandId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const auto flush = journal.append_performance_flush(
      bundle, session_id, command_id, performance.id, 0,
      std::vector{pad_hit(1, 480)});
  LMDJ_CHECK(flush.has_value());
  const PerformanceFlushIdentity identity{
      session_id, flush.value().flush_seq, command_id, performance.id};

  {
    FaultGuard fault(FaultPoint::sequence_journal_write);
    const auto interrupted = store.execute_performance_flush(bundle, identity);
    LMDJ_CHECK(!interrupted.has_value());
    LMDJ_CHECK(interrupted.error().code == ErrorCode::io_error);
  }
  LMDJ_CHECK(store.load(bundle).value().revision == 1);
  LMDJ_CHECK(!journal.read_active_performance(bundle)
                  .value()
                  .flushes.front()
                  .completed);

  ProjectStore restarted;
  const auto replayed = restarted.execute_performance_flush(bundle, identity);
  LMDJ_CHECK(replayed.has_value());
  LMDJ_CHECK(replayed.value().replayed);
  LMDJ_CHECK(replayed.value().state.revision == 1);
  LMDJ_CHECK(journal.read_active_performance(bundle)
                 .value()
                 .flushes.front()
                 .completed);
}

void test_performance_recovery_fails_closed_after_target_deletion() {
  TempDirectory temp("deleted");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto command_id = CommandId{std::string{kCommandId}};

  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const auto flush = journal.append_performance_flush(
      bundle, session_id, command_id, performance.id, 0,
      std::vector{pad_hit(3, 1440)});
  LMDJ_CHECK(flush.has_value());

  const auto checkpoint = bundle / "history/checkpoints/0.json";
  auto document = nlohmann::json::parse(read_text(checkpoint));
  document["performances"] = nlohmann::json::array();
  {
    std::ofstream stream(checkpoint, std::ios::binary | std::ios::trunc);
    const auto bytes = lmdj::foundation::canonical_json(document) + "\n";
    stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  }

  const auto rejected = store.execute_performance_flush(
      bundle,
      {session_id, flush.value().flush_seq, command_id, performance.id});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(rejected.error().details.at("reason") ==
             "performance_recovery_target_incompatible");
  LMDJ_CHECK(rejected.error().details.at("recovery_retained") == true);
  LMDJ_CHECK(
      std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
}

void test_performance_recovery_fails_closed_after_fingerprint_change() {
  TempDirectory temp("changed");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto performance = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto command_id = CommandId{std::string{kCommandId}};

  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              performance.id,
              lmdj::project_io::performance_fingerprint(performance),
              0)
          .has_value());
  const auto flush = journal.append_performance_flush(
      bundle, session_id, command_id, performance.id, 0,
      std::vector{pad_hit(3, 1440)});
  LMDJ_CHECK(flush.has_value());

  const auto checkpoint = bundle / "history/checkpoints/0.json";
  auto document = nlohmann::json::parse(read_text(checkpoint));
  document.at("performances").at(0)["name"] = "Changed elsewhere";
  {
    std::ofstream stream(checkpoint, std::ios::binary | std::ios::trunc);
    const auto bytes = lmdj::foundation::canonical_json(document) + "\n";
    stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  }

  const auto rejected = store.execute_performance_flush(
      bundle,
      {session_id, flush.value().flush_seq, command_id, performance.id});
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(rejected.error().details.at("reason") ==
             "performance_recovery_target_incompatible");
  LMDJ_CHECK(rejected.error().details.at("recovery_retained") == true);
  LMDJ_CHECK(
      std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
}

void test_performance_fingerprint_includes_recording_revision() {
  const auto original = empty_performance();
  auto changed = original;
  changed.recording_revision = 1;
  LMDJ_CHECK(
      lmdj::project_io::performance_fingerprint(original) !=
      lmdj::project_io::performance_fingerprint(changed));
}

void test_unknown_recovery_contract_is_retained_and_rejected() {
  TempDirectory temp("unknown-contract");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  const auto path = bundle / "recovery/sealed/future.json";
  write_text(
      path,
      checked_line({
          {"contract", "lmdj.recording.recovery.v999"},
          {"journal", nlohmann::json::object()},
          {"reason", "future"},
      }));

  SequenceJournal journal;
  const auto candidates = journal.list_performance_recoverable(bundle);
  LMDJ_CHECK(!candidates.has_value());
  LMDJ_CHECK(candidates.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(candidates.error().details.at("recovery_retained") == true);
  LMDJ_CHECK(std::filesystem::exists(path));
}

void test_incomplete_performance_flush_cannot_have_a_successor() {
  TempDirectory temp("incomplete-predecessor");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto live = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              live.id,
              lmdj::project_io::performance_fingerprint(live),
              0)
          .has_value());
  LMDJ_CHECK(
      journal
          .append_performance_flush(
              bundle,
              session_id,
              CommandId{std::string{kCommandId}},
              live.id,
              0,
              std::vector{pad_hit(0, 0)})
          .has_value());
  append_text(
      bundle / "recovery/active/performance.jsonl",
      checked_line({
          {"command_id", kSecondCommandId},
          {"events",
           nlohmann::json::array(
               {lmdj::domain::performance_event_json(pad_hit(1, 480))})},
          {"expected_revision", 0},
          {"flush_seq", 1},
          {"kind", "flush"},
          {"performance_id", kPerformanceId},
      }));

  const auto rejected = journal.read_active_performance(bundle);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(rejected.error().details.at("journal_retained") == true);
  LMDJ_CHECK(
      std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
}

void test_invalid_performance_completion_revision_is_retained() {
  TempDirectory temp("invalid-completion");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto live = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              live.id,
              lmdj::project_io::performance_fingerprint(live),
              0)
          .has_value());
  LMDJ_CHECK(
      journal
          .append_performance_flush(
              bundle,
              session_id,
              CommandId{std::string{kCommandId}},
              live.id,
              0,
              std::vector{pad_hit(0, 0)})
          .has_value());
  append_text(
      bundle / "recovery/active/performance.jsonl",
      checked_line({
          {"committed_revision", 9},
          {"flush_seq", 0},
          {"kind", "complete"},
          {"performance_fingerprint", std::string(64, '0')},
      }));

  const auto rejected = journal.read_active_performance(bundle);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(rejected.error().details.at("journal_retained") == true);
  LMDJ_CHECK(
      std::filesystem::exists(bundle / "recovery/active/performance.jsonl"));
}

void test_repeated_performance_command_rejects_changed_identity_and_payload() {
  TempDirectory temp("command-collision");
  ProjectStore store;
  const auto bundle = create_bundle(temp, store);
  SequenceJournal journal;
  const auto live = empty_performance();
  const auto session_id = SequenceSessionId{std::string{kSessionId}};
  const auto command_id = CommandId{std::string{kCommandId}};
  LMDJ_CHECK(
      journal
          .begin_performance(
              bundle,
              session_id,
              live.id,
              lmdj::project_io::performance_fingerprint(live),
              0)
          .has_value());
  const auto flush = journal.append_performance_flush(
      bundle, session_id, command_id, live.id, 0,
      std::vector{pad_hit(0, 0)});
  LMDJ_CHECK(flush.has_value());

  const auto changed_payload = journal.append_performance_flush(
      bundle, session_id, command_id, live.id, 0,
      std::vector{pad_hit(1, 480)});
  LMDJ_CHECK(!changed_payload.has_value());
  LMDJ_CHECK(changed_payload.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(changed_payload.error().details.at("reason") ==
             "performance_command_conflict");

  const auto changed_identity = store.execute_performance_flush(
      bundle,
      {session_id, flush.value().flush_seq + 1, command_id, live.id});
  LMDJ_CHECK(!changed_identity.has_value());
  LMDJ_CHECK(changed_identity.error().code == ErrorCode::invalid_argument);
  LMDJ_CHECK(changed_identity.error().details.at("reason") ==
             "performance_command_conflict");

  LMDJ_CHECK(
      store
          .execute_performance_flush(
              bundle,
              {session_id,
               flush.value().flush_seq,
               command_id,
               live.id})
          .has_value());
  append_text(
      bundle / "recovery/active/performance.jsonl",
      checked_line({
          {"command_id", kCommandId},
          {"events",
           nlohmann::json::array(
               {lmdj::domain::performance_event_json(pad_hit(1, 480))})},
          {"expected_revision", 1},
          {"flush_seq", 1},
          {"kind", "flush"},
          {"performance_id", kPerformanceId},
      }));
  const auto duplicate_record = journal.read_active_performance(bundle);
  LMDJ_CHECK(!duplicate_record.has_value());
  LMDJ_CHECK(duplicate_record.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(duplicate_record.error().details.at("journal_retained") == true);
}

}  // namespace

int main() {
  try {
    test_performance_transient_checkpoint_round_trips_empty_tail_transition();
    test_post_write_tail_failure_is_reported_as_ambiguous_and_retained();
    test_performance_seal_replays_stable_candidate_without_suffix();
    test_owner_loss_closes_fx_chain_then_hold_at_one_tick();
    test_legacy_and_malformed_checkpoint_streams_fail_closed();
    test_owner_loss_refuses_tick_and_input_sequence_overflow();
    test_performance_flush_is_durable_before_mutation_and_replays();
    test_performance_begin_append_complete_seal_and_recover_listing();
    test_outstanding_performance_flush_blocks_tail_and_remains_recoverable();
    test_invalid_performance_event_bounds_never_mutate_journal_bytes();
    test_structurally_valid_stateful_events_are_admitted_independently();
    test_empty_v3_project_creates_performance_then_begins_recording();
    test_performance_crud_is_revision_bound_and_idempotent();
    test_performance_create_recovers_each_persistence_fault();
    test_visible_receipt_replays_after_journal_completion_failure();
    test_performance_recovery_fails_closed_after_target_deletion();
    test_performance_recovery_fails_closed_after_fingerprint_change();
    test_performance_fingerprint_includes_recording_revision();
    test_unknown_recovery_contract_is_retained_and_rejected();
    test_incomplete_performance_flush_cannot_have_a_successor();
    test_invalid_performance_completion_revision_is_retained();
    test_repeated_performance_command_rejects_changed_identity_and_payload();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
