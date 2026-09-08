// Concurrent runtime invariant for Snapshot publication accounting.
//
// Completes Task 3 of docs/plans/2026-08-19-lmdj-runtime-invariant-harness.md:
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
// Excluded from the `coverage` test preset in CMakePresets.json, alongside
// audio.realtime_spsc_stress and for the same reason. The render loop below
// busy-spins with no yield, which is the point -- it maximises the interleavings
// the hand-off invariant has to survive -- but under the parallel coverage run
// it starves whichever test is nearest its tier budget. It did exactly that to
// facade.application, at 30s with no sanitizer multiplier to absorb the
// contention. Coverage does not need a concurrency run; the stress tier has its
// own lanes.
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
using lmdj::audio::PreparedPatternView;
using lmdj::audio::PatternPublishResult;
using lmdj::audio::PatternReplacementAuthority;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::foundation::ProjectId;
using lmdj::foundation::PatternId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";
constexpr std::uint64_t kPublications = 2'000;

// Observers never touch Pattern slots or call control methods. Their lifetime
// spans publication, callback claim/apply and control-thread reclamation.
class ConcurrentObservers {
 public:
  explicit ConcurrentObservers(RealtimeEngine& engine) {
    for (auto& reader : readers_) {
      reader = std::thread([this, &engine] {
        do {
          const auto pattern = engine.pattern_telemetry();
          LMDJ_CHECK(pattern.pending_publications <= 2);
          if (pattern.pending_generation == 0) {
            LMDJ_CHECK(pattern.pending_activation_frame == 0);
          }
          const auto runtime = engine.telemetry();
          LMDJ_CHECK(runtime.active_voices <= lmdj::audio::kRealtimeVoiceCapacity);
          static_cast<void>(engine.bank_telemetry());
          static_cast<void>(engine.capture_telemetry());
          static_cast<void>(engine.trigger_outcome_telemetry());
          static_cast<void>(engine.voice_state_telemetry());
          static_cast<void>(engine.master_fx_telemetry());
        } while (!stop_.load(std::memory_order_acquire));
      });
    }
  }
  ~ConcurrentObservers() {
    stop_.store(true, std::memory_order_release);
    for (auto& reader : readers_) {
      reader.join();
    }
  }

 private:
  std::atomic<bool> stop_{false};
  std::array<std::thread, 4> readers_;
};

PreparedSampleBank bank_at(std::uint64_t revision) {
  static constexpr std::array<float, 1> kSample{0.25F};
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, revision);
  LMDJ_CHECK(bank.set_sample(0, std::span<const float>(kSample)).has_value());
  return bank;
}

PreparedPatternView pattern_at(std::uint64_t revision) {
  const auto pattern_id = revision % 2 == 0
                              ? "30000000-0000-4000-8000-000000000001"
                              : "30000000-0000-4000-8000-000000000002";
  auto prepared = PreparedPatternView::from_snapshot(
      lmdj::cooker::RuntimeSnapshot{
          ProjectId{kProjectId},
          PatternId{pattern_id},
          revision,
          240,
          1,
          lmdj::domain::kPpq,
          lmdj::domain::kBarTicks4x4,
          {},
          {},
      });
  LMDJ_CHECK(prepared.has_value());
  return std::move(prepared.value());
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
  ConcurrentObservers observers{engine};
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

// Finding G5, resolved by Issue #205 and pinned rather than asserted away.
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
// Issue #205 deliberately keeps the complete rollback as defence against a
// future capacity divergence; it does not change realtime headroom merely to
// exercise an error path. This test pins the current consequence: across a
// heavy race, `publish_queue_drops` stays 0 and `bank_slots_full` is the only
// capacity rejection. If either capacity ever changes so the branch becomes
// live, this turns red and points whoever changed it at the now-reachable
// rollback.
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

void test_pattern_publication_switches_are_conserved_under_concurrency() {
  constexpr std::uint64_t kPatternPublications = 40;
  RealtimeEngine engine;
  const auto initial = engine.publish_pattern_view(pattern_at(1));
  LMDJ_CHECK(initial.result == PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  // A rejected past-frame request consumes an allocation without an accepted
  // publication. Make the generation/count distinction deterministic before
  // exercising the same concurrent publication and final-state journey.
  std::array<float, 128> warmup_left{}, warmup_right{};
  engine.render(warmup_left.data(), warmup_right.data(), 128);
  const auto rejected = engine.publish_pattern_view(pattern_at(2), 0);
  LMDJ_CHECK(rejected.result == PatternPublishResult::publish_queue_full);
  ConcurrentObservers observers{engine};

  std::atomic<bool> rendering{true};
  std::thread audio_thread([&] {
    std::array<float, 128> left{};
    std::array<float, 128> right{};
    while (rendering.load(std::memory_order_acquire)) {
      engine.render(
          left.data(),
          right.data(),
          static_cast<std::uint32_t>(left.size()));
    }
  });

  std::uint64_t accepted = 1;
  auto last_accepted_generation = initial.generation;
  for (std::uint64_t revision = 2;
       revision <= kPatternPublications;
       ++revision) {
    while (engine.pattern_telemetry().pending_generation != 0) {
      engine.reclaim_retired_patterns();
      std::this_thread::yield();
    }
    engine.reclaim_retired_patterns();
    auto publication = engine.publish_pattern_view(pattern_at(revision));
    LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
    ++accepted;
    last_accepted_generation = publication.generation;
  }
  while (engine.pattern_telemetry().pending_generation != 0) {
    engine.reclaim_retired_patterns();
    std::this_thread::yield();
  }
  rendering.store(false, std::memory_order_release);
  audio_thread.join();
  engine.reclaim_retired_patterns();

  const auto telemetry = engine.pattern_telemetry();
  LMDJ_CHECK(telemetry.accepted_publications == accepted);
  LMDJ_CHECK(telemetry.applied_publications == accepted);
  LMDJ_CHECK(telemetry.pending_generation == 0);
  LMDJ_CHECK(last_accepted_generation > accepted);
  LMDJ_CHECK(telemetry.current_generation == last_accepted_generation);
  LMDJ_CHECK(telemetry.publication_rejections == 1);
  LMDJ_CHECK(telemetry.superseded_publications == 0);
  LMDJ_CHECK(engine.current_pattern_id() ==
             PatternId{"30000000-0000-4000-8000-000000000001"});
}

void test_same_boundary_pattern_supersession_is_conserved_under_concurrency() {
  constexpr std::uint64_t kSupersedingPublications = 2'000;
  constexpr std::uint64_t kDistantBoundary = 1'000'000'000'000ULL;
  RealtimeEngine engine;
  const auto initial = engine.publish_pattern_view(pattern_at(2));
  LMDJ_CHECK(initial.result == PatternPublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());
  ConcurrentObservers observers{engine};

  std::atomic<bool> rendering{true};
  std::thread audio_thread([&] {
    std::array<float, 128> left{};
    std::array<float, 128> right{};
    while (rendering.load(std::memory_order_acquire)) {
      engine.render(
          left.data(), right.data(), static_cast<std::uint32_t>(left.size()));
    }
    for (int drain = 0; drain < 64; ++drain) {
      engine.render(left.data(), right.data(), 128);
    }
  });

  std::uint64_t accepted = 1;
  std::uint64_t slots_full = 0;
  std::uint64_t canceled = 0;
  for (std::uint64_t revision = 2;
       revision < 2 + kSupersedingPublications;) {
    engine.reclaim_retired_patterns();
    auto publication = engine.publish_pattern_view(
        pattern_at(revision * 2), kDistantBoundary);
    if (publication.result == PatternPublishResult::pattern_slots_full) {
      ++slots_full;
      std::this_thread::yield();
      continue;
    }
    LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
    LMDJ_CHECK(publication.activation_frame == kDistantBoundary);
    ++accepted;
    if (revision % 7 == 0) {
      const auto authority = PatternReplacementAuthority{
          publication.generation,
          PatternId{"30000000-0000-4000-8000-000000000001"},
          publication.activation_frame};
      if (engine.cancel_pattern_publication(authority)) {
        ++canceled;
      }
    }
    ++revision;
  }

  rendering.store(false, std::memory_order_release);
  audio_thread.join();
  const auto telemetry = engine.pattern_telemetry();
  std::cerr << "  pattern accepted=" << telemetry.accepted_publications
            << " applied=" << telemetry.applied_publications
            << " superseded=" << telemetry.superseded_publications
            << " canceled=" << telemetry.canceled_publications
            << " pending=" << telemetry.pending_publications
            << '\n';
  LMDJ_CHECK(telemetry.current_generation == initial.generation);
  LMDJ_CHECK(telemetry.pending_generation != 0);
  LMDJ_CHECK(telemetry.applied_publications == 1);
  LMDJ_CHECK(
      telemetry.accepted_publications ==
      telemetry.applied_publications + telemetry.superseded_publications +
          telemetry.canceled_publications + telemetry.pending_publications);
  LMDJ_CHECK(telemetry.accepted_publications == accepted);
  LMDJ_CHECK(telemetry.publication_rejections == slots_full);
  LMDJ_CHECK(telemetry.superseded_publications > 0);
  LMDJ_CHECK(telemetry.canceled_publications == canceled);
  LMDJ_CHECK(telemetry.canceled_publications > 0);
}

void test_observers_remain_valid_across_quiescent_writer_handoffs() {
  RealtimeEngine engine;
  ConcurrentObservers observers{engine};
  for (std::uint64_t epoch = 1; epoch <= 100; ++epoch) {
    LMDJ_CHECK(engine.start().has_value());
    std::thread audio([&] {
      std::array<float, 2> left{}, right{};
      engine.render(left.data(), right.data(), 2);
    });
    audio.join();
    engine.stop();
    const auto final = engine.telemetry();
    LMDJ_CHECK(final.start_epoch == epoch);
    LMDJ_CHECK(final.rendered_frames == 2);
    LMDJ_CHECK(final.callback_count == 1);
  }
}

}  // namespace

int main() {
  try {
    test_publication_accounting_is_conserved_under_concurrency();
    test_publish_queue_full_is_unreachable_at_equal_capacities();
    test_pattern_publication_switches_are_conserved_under_concurrency();
    test_same_boundary_pattern_supersession_is_conserved_under_concurrency();
    test_observers_remain_valid_across_quiescent_writer_handoffs();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "snapshot publication stress invariant tests: PASS\n";
  return 0;
}
