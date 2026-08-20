// Runtime invariant harness for Snapshot publication accounting.
//
// Track 3 Task 3 of docs/superpowers/plans/2026-08-19-lmdj-runtime-invariant-harness.md.
//
// The engine's own tests assert specific telemetry values in specific
// scenarios. What only a sequence can show is whether the counters stay
// mutually consistent across arbitrary interleavings of publication,
// rendering, and rejection -- in particular that a rejected publication leaves
// the accounting exactly as it was, which is the observable half of "the
// previous Bank keeps serving".
//
// Deliberately out of scope: checking that the live Bank's project revision
// equals the last accepted Snapshot's. RealtimeEngine exposes only counters;
// the live Bank's identity sits behind `friend class RealtimeEngine`, so that
// check needs either a new accessor or a gated test hook, and growing
// production surface for a test is the wrong trade. Recorded as a follow-up in
// the plan instead.

#include <array>
#include <cstdint>
#include <exception>
#include <iostream>
#include <span>
#include <string>
#include <vector>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/foundation/ids.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::BankTelemetry;
using lmdj::audio::EnqueueResult;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::TriggerEvent;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";

PreparedSampleBank bank_at(std::uint64_t revision) {
  static constexpr std::array<float, 1> kSample{0.25F};
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, revision);
  LMDJ_CHECK(bank.set_sample(0, std::span<const float>(kSample)).has_value());
  return bank;
}

// ---------------------------------------------------------------------------
// The harness
// ---------------------------------------------------------------------------

// Tracks the counters across a sequence so each step can be checked against
// the previous one. A single snapshot of BankTelemetry cannot express a
// monotonicity or conservation claim; only successive observations can.
class PublicationLedger {
 public:
  explicit PublicationLedger(const RealtimeEngine& engine)
      : previous_(engine.bank_telemetry()) {}

  // Relations that must hold at every observation, plus the ones that relate
  // this observation to the previous one.
  void observe(
      const RealtimeEngine& engine,
      bool publication_was_accepted) {
    const auto current = engine.bank_telemetry();

    // Relation 1: nothing is applied that was not accepted.
    record(
        current.applied_publications <= current.accepted_publications,
        "applied publications exceeded accepted publications");

    // Relation 2: conservation. Pending is exactly the accepted work the
    // render thread has not applied yet.
    record(
        current.pending_publications ==
            current.accepted_publications - current.applied_publications,
        "pending publications do not equal accepted minus applied");

    // Relation 3: the live generation never moves backwards.
    record(
        current.current_generation >= previous_.current_generation,
        "current generation moved backwards");

    // Relation 4: a rejected publication changes no accounting at all. This
    // is the observable form of "the previous Bank remains current".
    if (!publication_was_accepted) {
      record(
          current.accepted_publications == previous_.accepted_publications,
          "a rejected publication changed the accepted count");
      record(
          current.current_generation == previous_.current_generation,
          "a rejected publication moved the live generation");
      record(
          current.pending_publications == previous_.pending_publications,
          "a rejected publication changed the pending count");
    }

    // Relation 5: applied and accepted never decrease.
    record(
        current.applied_publications >= previous_.applied_publications &&
            current.accepted_publications >= previous_.accepted_publications,
        "a publication counter decreased");

    // Relation 6: a reclaimed Bank was retired first, so reclaimed can never
    // exceed the number of applications that displaced a Bank.
    record(
        current.reclaimed_banks <= current.applied_publications,
        "more Banks were reclaimed than were ever applied");

    previous_ = current;
  }

  const std::vector<std::string>& violations() const { return violations_; }

 private:
  void record(bool holds, std::string relation) {
    if (!holds) {
      violations_.push_back(std::move(relation));
    }
  }

  BankTelemetry previous_;
  std::vector<std::string> violations_;
};

void check_no_violations(const PublicationLedger& ledger) {
  for (const auto& violation : ledger.violations()) {
    std::cerr << "publication violation: " << violation << '\n';
  }
  LMDJ_CHECK(ledger.violations().empty());
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// The accounting stays consistent across a publish/render sequence, including
// the quiescent publish that applies directly and the running publish that
// defers to the render thread.
void test_publication_accounting_holds_across_a_sequence() {
  RealtimeEngine engine;
  PublicationLedger ledger(engine);
  std::array<float, 1> left{};
  std::array<float, 1> right{};

  // Quiescent publish applies immediately, so nothing is ever pending.
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(1)) == PublishResult::accepted);
  ledger.observe(engine, true);
  LMDJ_CHECK(engine.bank_telemetry().pending_publications == 0);

  LMDJ_CHECK(engine.start().has_value());

  // Running publishes defer, so each one is pending until a render applies it.
  for (std::uint64_t revision = 2; revision <= 4; ++revision) {
    LMDJ_CHECK(
        engine.publish_sample_bank(bank_at(revision)) ==
        PublishResult::accepted);
    ledger.observe(engine, true);
    LMDJ_CHECK(engine.bank_telemetry().pending_publications == 1);

    engine.render(left.data(), right.data(), 1);
    ledger.observe(engine, true);
    LMDJ_CHECK(engine.bank_telemetry().pending_publications == 0);

    LMDJ_CHECK(engine.reclaim_retired_banks() <= 1);
    ledger.observe(engine, true);
  }

  check_no_violations(ledger);
}

// A publication refused because trigger events are still queued must leave the
// accounting untouched. This is the rejection path a Host sees most often.
void test_events_pending_rejection_changes_no_accounting() {
  RealtimeEngine engine;
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(1)) == PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  PublicationLedger ledger(engine);

  // A queued trigger makes the next publication unsafe.
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) == EnqueueResult::accepted);
  const auto refused = engine.publish_sample_bank(bank_at(2));
  LMDJ_CHECK(refused == PublishResult::events_pending);
  ledger.observe(engine, false);

  // Draining the queue makes it safe again, and the accounting resumes.
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  ledger.observe(engine, true);
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(2)) == PublishResult::accepted);
  ledger.observe(engine, true);

  check_no_violations(ledger);
}

// Exhausting the Bank slots must also leave the accounting untouched, and must
// increment only the dedicated rejection counter.
void test_bank_slot_exhaustion_changes_no_accounting() {
  static_assert(lmdj::audio::kRealtimeBankCapacity == 4);

  RealtimeEngine engine;
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(1)) == PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  PublicationLedger ledger(engine);

  // One slot is current; fill the rest without rendering so they stay pending.
  std::uint64_t revision = 2;
  auto result = PublishResult::accepted;
  while (result == PublishResult::accepted) {
    result = engine.publish_sample_bank(bank_at(revision));
    ledger.observe(engine, result == PublishResult::accepted);
    ++revision;
  }

  // The first refusal is slot exhaustion, not an event or queue condition,
  // because nothing was enqueued and the publish queue is at least as large
  // as the slot array.
  LMDJ_CHECK(result == PublishResult::bank_slots_full);

  const auto telemetry = engine.bank_telemetry();
  LMDJ_CHECK(telemetry.bank_slot_rejections == 1);
  LMDJ_CHECK(telemetry.publish_queue_drops == 0);

  // Rendering applies the pending Banks and the accounting stays consistent
  // all the way back to quiescence.
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  while (engine.bank_telemetry().pending_publications != 0) {
    engine.render(left.data(), right.data(), 1);
    ledger.observe(engine, true);
  }

  check_no_violations(ledger);
}

// The harness must fail on a real violation, or the passing cases prove
// nothing. The relations are checked against a fabricated observation pair
// rather than by corrupting the engine, since the engine offers no way to make
// its counters lie.
void test_harness_detects_inconsistent_observations() {
  // A ledger that has observed a live generation cannot accept a lower one,
  // and cannot accept a rejection that moved the counters.
  RealtimeEngine engine;
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(1)) == PublishResult::accepted);

  PublicationLedger ledger(engine);

  // Claim the accepted publication below was rejected. Relation 4 must catch
  // the contradiction, because a rejection cannot have raised the counters.
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(2)) == PublishResult::accepted);
  ledger.observe(engine, false);

  LMDJ_CHECK(!ledger.violations().empty());
}

}  // namespace

int main() {
  try {
    test_publication_accounting_holds_across_a_sequence();
    test_events_pending_rejection_changes_no_accounting();
    test_bank_slot_exhaustion_changes_no_accounting();
    test_harness_detects_inconsistent_observations();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "snapshot publication invariant tests: PASS\n";
  return 0;
}
