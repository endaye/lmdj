// Concurrent runtime invariant for Snapshot publication accounting.
//
// Completes Task 3 of docs/superpowers/plans/2026-08-19-lmdj-runtime-invariant-harness.md:
// the stress-tier case. It also settles what that plan left open about
// PublishResult::publish_queue_full -- see finding G5 on the second test: the
// path is unreachable while the Bank and publish-queue capacities are equal, so
// the rollback branch behind it is dead code rather than something a test could
// have been covering all along.
//
// Why a second file rather than a case in the component-tier harness: that one
// is deterministic and single-threaded, and a concurrent test is a different
// risk class. Keeping them apart means a flake here never casts doubt on the
// deterministic relations, and the component tier stays usable as a fast gate.
//
// The invariant under test is a conservation law: every publication is
// accounted for exactly once, in exactly one bucket, no matter how the two
// threads interleave.

#include <array>
#include <atomic>
#include <cstdint>
#include <exception>
#include <iostream>
#include <span>
#include <thread>
#include <vector>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/foundation/ids.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";
constexpr std::uint64_t kPublications = 2'000;

PreparedSampleBank bank_at(std::uint64_t revision) {
  static constexpr std::array<float, 1> kSample{0.25F};
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, revision);
  LMDJ_CHECK(bank.set_sample(0, std::span<const float>(kSample)).has_value());
  return bank;
}

struct Outcomes {
  std::uint64_t accepted = 0;
  std::uint64_t events_pending = 0;
  std::uint64_t bank_slots_full = 0;
  std::uint64_t publish_queue_full = 0;
  std::uint64_t reclaimed = 0;
};

// One control thread publishing against one render thread applying, which is
// exactly the producer/consumer pair the engine's hand-off invariant is written
// for. Publication and reclamation both belong to the control thread; render
// belongs to the audio thread.
Outcomes race_publication_against_render(RealtimeEngine& engine) {
  std::atomic<bool> rendering{true};
  std::thread audio_thread([&engine, &rendering]() {
    std::array<float, 1> left{};
    std::array<float, 1> right{};
    while (rendering.load(std::memory_order_acquire)) {
      engine.render(left.data(), right.data(), 1);
    }
    // Drain whatever the producer left pending so the final state is quiescent.
    for (int drain = 0; drain < 64; ++drain) {
      engine.render(left.data(), right.data(), 1);
    }
  });

  Outcomes outcomes;
  for (std::uint64_t revision = 2; revision < 2 + kPublications; ++revision) {
    switch (engine.publish_sample_bank(bank_at(revision))) {
      case PublishResult::accepted:
        ++outcomes.accepted;
        break;
      case PublishResult::events_pending:
        ++outcomes.events_pending;
        break;
      case PublishResult::bank_slots_full:
        ++outcomes.bank_slots_full;
        break;
      case PublishResult::publish_queue_full:
        ++outcomes.publish_queue_full;
        break;
    }
    // Reclaiming frees slots, which is what lets the publish queue rather than
    // the slot array become the binding constraint.
    outcomes.reclaimed += engine.reclaim_retired_banks();
  }

  rendering.store(false, std::memory_order_release);
  audio_thread.join();

  // Reclaim on the control thread until quiescent, as a Host would.
  for (int pass = 0; pass < 64; ++pass) {
    outcomes.reclaimed += engine.reclaim_retired_banks();
  }
  return outcomes;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void test_publication_accounting_is_conserved_under_concurrency() {
  RealtimeEngine engine;
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(1)) == PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  const auto outcomes = race_publication_against_render(engine);
  const auto telemetry = engine.bank_telemetry();

  // Relation 1: the engine counted exactly the publications the producer saw
  // accepted, plus the one before start().
  LMDJ_CHECK(telemetry.accepted_publications == outcomes.accepted + 1);

  // Relation 2: every rejection landed in its own bucket and nowhere else. A
  // rejected publication that had incremented `accepted` would break this, and
  // so would one that incremented the wrong rejection counter.
  LMDJ_CHECK(telemetry.bank_slot_rejections == outcomes.bank_slots_full);
  LMDJ_CHECK(telemetry.publish_queue_drops == outcomes.publish_queue_full);

  // Relation 3: no trigger was ever enqueued, so the events_pending path must
  // never have been taken. This keeps the run focused on the two capacity
  // rejections.
  LMDJ_CHECK(outcomes.events_pending == 0);

  // Relation 4: conservation. Every accepted publication is either applied or
  // still pending, never lost and never double counted.
  LMDJ_CHECK(
      telemetry.applied_publications + telemetry.pending_publications ==
      telemetry.accepted_publications);

  // Relation 5: the render thread drained to quiescence, so nothing is pending
  // and the live generation reflects real work.
  LMDJ_CHECK(telemetry.pending_publications == 0);
  LMDJ_CHECK(telemetry.applied_publications == telemetry.accepted_publications);
  LMDJ_CHECK(telemetry.current_generation > 0);

  // Relation 6: a reclaimed Bank was retired by an application first.
  LMDJ_CHECK(telemetry.reclaimed_banks <= telemetry.applied_publications);
  LMDJ_CHECK(telemetry.reclaimed_banks == outcomes.reclaimed);

  // The producer must have made real progress, or the run proved nothing.
  LMDJ_CHECK(outcomes.accepted > 0);

  // Report the shape of the run. Which capacity wall is hit, if any, is
  // scheduling-dependent, so nothing here asserts on it -- see finding G5 below
  // for why publish_queue_full in particular can never appear.
  std::cout << "  accepted=" << outcomes.accepted
            << " slots_full=" << outcomes.bank_slots_full
            << " queue_full=" << outcomes.publish_queue_full
            << " reclaimed=" << outcomes.reclaimed << '\n';
}

// Finding G5, pinned rather than asserted away.
//
// `PublishResult::publish_queue_full` is **unreachable while the two capacities
// are equal**, so the rollback branch behind it is dead code today. The
// argument is short enough to check by hand:
//
//   * A queue entry exists for exactly each publication that is `pending` and
//     not yet applied, and `try_pop` precedes the `pending` decrement, so
//     queue_entries <= pending_publications at all times.
//   * Each pending publication owns a distinct slot in `BankState::pending`.
//   * `try_push` is reached only after `find_if` located a slot in
//     `BankState::empty`.
//
// For `try_push` to fail, the queue must already hold
// kRealtimePublishQueueCapacity == 4 entries, which requires 4 slots in
// `pending`; but reaching the push at all requires a 5th slot in `empty`. With
// kRealtimeBankCapacity == 4 that is a contradiction, so `bank_slots_full`
// always binds first.
//
// This test pins the consequence: across a heavy race, `publish_queue_drops`
// stays 0 and `bank_slots_full` is the only capacity rejection. If either
// capacity ever changes so the branch becomes live, this turns red and points
// whoever changed it at the now-reachable rollback.
void test_publish_queue_full_is_unreachable_at_equal_capacities() {
  static_assert(
      lmdj::audio::kRealtimeBankCapacity ==
      lmdj::audio::kRealtimePublishQueueCapacity,
      "the unreachability argument below depends on the capacities being equal");

  RealtimeEngine engine;
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(1)) == PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  const auto first = race_publication_against_render(engine);
  const auto after_first = engine.bank_telemetry();
  LMDJ_CHECK(first.accepted > 0);
  LMDJ_CHECK(first.publish_queue_full == 0);
  LMDJ_CHECK(after_first.publish_queue_drops == 0);

  // A second round on the same engine, to rule out the weaker reading that the
  // queue simply never filled because the engine was fresh. If a slot had been
  // leaked by any path, the second round would accept strictly less and reject
  // far more; instead the accounting continues exactly.
  const auto second = race_publication_against_render(engine);
  const auto after_second = engine.bank_telemetry();

  LMDJ_CHECK(second.accepted > 0);
  LMDJ_CHECK(second.publish_queue_full == 0);
  LMDJ_CHECK(after_second.publish_queue_drops == 0);
  LMDJ_CHECK(
      after_second.accepted_publications ==
      after_first.accepted_publications + second.accepted);
  LMDJ_CHECK(
      after_second.applied_publications ==
      after_second.accepted_publications);
  LMDJ_CHECK(after_second.pending_publications == 0);
  LMDJ_CHECK(
      after_second.bank_slot_rejections ==
      after_first.bank_slot_rejections + second.bank_slots_full);

  // Whether a capacity wall is hit at all is scheduling-dependent here, so this
  // test does not require it -- an assertion on that would be exactly the flake
  // this file exists to avoid. The claim is not vacuous nonetheless: the
  // component-tier `test_bank_slot_exhaustion_changes_no_accounting`
  // deterministically drives the engine into a capacity wall and shows it is
  // always `bank_slots_full` with `publish_queue_drops == 0`. This test adds
  // that the same holds under a real race.

  // And the engine still publishes afterwards, the practical form of "no slot
  // was lost across either round".
  for (int pass = 0; pass < 8; ++pass) {
    engine.reclaim_retired_banks();
  }
  std::array<float, 1> left{};
  std::array<float, 1> right{};
  engine.render(left.data(), right.data(), 1);
  LMDJ_CHECK(
      engine.publish_sample_bank(bank_at(999'999)) ==
      PublishResult::accepted);
}

}  // namespace

int main() {
  try {
    test_publication_accounting_is_conserved_under_concurrency();
    test_publish_queue_full_is_unreachable_at_equal_capacities();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "snapshot publication stress invariant tests: PASS\n";
  return 0;
}
