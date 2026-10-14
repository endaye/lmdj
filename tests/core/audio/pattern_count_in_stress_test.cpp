#include <lmdj/audio/realtime_engine.hpp>

#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <new>
#include <thread>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using namespace lmdj::audio;
thread_local bool in_audio{};
void* allocate(std::size_t bytes) {
  if (in_audio) std::abort();
  if (auto* p = std::malloc(bytes == 0 ? 1 : bytes)) return p;
  throw std::bad_alloc{};
}
void free_allocation(void* p) noexcept {
  if (in_audio && p) std::abort();
  std::free(p);
}
template <typename Predicate> void wait_for(Predicate predicate) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
  while (!predicate()) {
    LMDJ_CHECK(std::chrono::steady_clock::now() < deadline);
    std::this_thread::yield();
  }
}
struct Fixture {
  RealtimeEngine engine;
  std::uint64_t pattern_generation{};
  explicit Fixture(std::size_t n = 32) : engine(RealtimeEngine::ReceiptBoundedVoiceStates{}, n) {
    LMDJ_CHECK(engine.enable_pattern_transport(19).has_value());
    LMDJ_CHECK(engine.enable_scheduled_pattern_record(19).has_value());
    LMDJ_CHECK(engine.enable_pattern_input_profile(19).has_value());
    auto bank = PreparedSampleBank::empty(
        foundation::ProjectId{"00000000-0000-4000-8000-000000000001"}, 1);
    std::array<float, 128> silent{};
    LMDJ_CHECK(bank.set_sample(0, silent,
        {0, 128, domain::TriggerMode::loop_toggle, 1, true}).has_value());
    LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) == PublishResult::accepted);
    cooker::RuntimeSnapshot snapshot{
        foundation::ProjectId{"00000000-0000-4000-8000-000000000001"},
        foundation::PatternId{"00000000-0000-4000-8000-000000000002"},
        1, 240, 1, domain::kPpq, domain::kBarTicks4x4, {}, {}};
    auto view = PreparedPatternView::from_snapshot(snapshot);
    LMDJ_CHECK(view.has_value());
    const auto p = engine.publish_pattern_view(std::move(view.value()));
    LMDJ_CHECK(p.result == PatternPublishResult::accepted);
    pattern_generation = p.generation;
    LMDJ_CHECK(engine.start().has_value());
  }
  ScheduledPatternRecordRequest request(std::uint64_t serial, std::uint64_t epoch) {
    return {19, 1, epoch, serial, pattern_generation,
        foundation::PatternId{"00000000-0000-4000-8000-000000000002"}, 1};
  }
  PatternInputAdmission press(bool held = true) {
    return engine.enqueue_pattern_input({19, 1, 0, 127, false, 0, held});
  }
};
// Submission races the free-running audio thread. Control reads the Pattern
// observation in a bounded number of attempts and does not wait while audio
// holds Pattern admission closed in claim_queued_pattern(); submit then
// returns the retryable `busy` before touching any state. TSan widens that
// claim window enough to cover every attempt, even on the first callback
// (#2261). Retry only `busy`: any other verdict fails at once, and the retry
// reusing this serial and epoch proves the refused attempt consumed neither.
void submit_until_admitted(Fixture& f, const ScheduledPatternRecordRequest& request) {
  wait_for([&] {
    const auto verdict = f.engine.submit_scheduled_pattern_record(request);
    LMDJ_CHECK(verdict == ScheduledPatternSubmit::accepted ||
        verdict == ScheduledPatternSubmit::busy);
    return verdict == ScheduledPatternSubmit::accepted;
  });
}

void exact_receipts_and_silent_release_escrow_under_concurrent_audio() {
  Fixture f;
  std::atomic<bool> done{};
  std::atomic<std::uint64_t> copied_markers{};
  std::thread audio([&] {
    std::array<float, 128> left{}, right{};
    while (!done.load(std::memory_order_acquire)) {
      in_audio = true;
      f.engine.render(left.data(), right.data(), left.size());
      CountInCueBatch batch{};
      if (f.engine.take_count_in_cue_batch_audio(batch)) {
        LMDJ_CHECK(batch.serial != 0 && batch.span_count <= 9);
        for (std::size_t i = 0; i < batch.span_count; ++i) {
          const auto& span = batch.spans[i];
          LMDJ_CHECK(span.begin_frame >= batch.begin_frame && span.end_frame <= batch.end_frame);
          LMDJ_CHECK(span.begin_frame < span.end_frame);
          if (span.marker && span.forced) ++copied_markers;
        }
        LMDJ_CHECK(f.engine.acknowledge_count_in_cue_batch_audio(batch.batch_id));
      }
      in_audio = false;
      for (const auto value : left) LMDJ_CHECK(std::isfinite(value) && value == 0);
      std::this_thread::yield();
    }
  });
  std::uint64_t epoch = 0, serial = 0, last_sequence = 0, last_ordinal = 0;
  std::uint64_t cancelled = 0, applied = 0;
  for (unsigned cycle = 0; cycle < 1000; ++cycle) {
    const auto e1 = ++epoch;
    submit_until_admitted(f, f.request(++serial, e1));
    const auto press = f.press();
    LMDJ_CHECK(press.result == PatternInputSubmit::accepted);
    LMDJ_CHECK(press.sequence > last_sequence && press.acceptance_ordinal > last_ordinal);
    last_sequence = press.sequence; last_ordinal = press.acceptance_ordinal;
    wait_for([&] { return f.engine.inspect_pattern_input_completion(19, 1, press.sequence).has_value(); });
    const auto completion = f.engine.inspect_pattern_input_completion(19, 1, press.sequence);
    LMDJ_CHECK(completion->disposition == PatternInputDisposition::muted_no_voice);
    LMDJ_CHECK(f.engine.consume_pattern_input_completion(19, 1, press.sequence));
    LMDJ_CHECK(f.engine.pattern_input_profile_status().held_release_reservations == 1);
    if (cycle % 10 == 0)
      wait_for([&] { return f.engine.inspect_scheduled_pattern_record(19, serial)->start_receipt.has_value(); });
    const auto e2 = ++epoch;
    const auto cancel = f.engine.cancel_scheduled_pattern_record({19, 1, serial, e2});
    LMDJ_CHECK(cancel == ScheduledPatternSubmit::accepted || cancel == ScheduledPatternSubmit::start_won);
    LMDJ_CHECK(f.engine.cancel_scheduled_pattern_record({19, 1, serial, epoch + 1}) == ScheduledPatternSubmit::busy);
    if (cancel == ScheduledPatternSubmit::start_won)
      LMDJ_CHECK(f.engine.submit_pattern_transport({19, e2, f.pattern_generation,
          PatternTransportAction::stop, {}}) == PatternTransportSubmit::accepted);
    wait_for([&] {
      const auto status = f.engine.inspect_scheduled_pattern_record(19, serial);
      return status && status->start_receipt && status->cancel_receipt;
    });
    const auto status = f.engine.inspect_scheduled_pattern_record(19, serial);
    LMDJ_CHECK(status->start_receipt->epoch == e1 && status->cancel_receipt->epoch == e2);
    if (cancel == ScheduledPatternSubmit::accepted) {
      ++cancelled;
      LMDJ_CHECK(status->start_receipt->result == ScheduledPatternResult::cancelled);
      LMDJ_CHECK(!status->start_receipt->effective_frame);
    } else {
      ++applied;
      LMDJ_CHECK(status->start_receipt->result == ScheduledPatternResult::applied);
      LMDJ_CHECK(status->start_receipt->effective_frame == status->start_frame);
      LMDJ_CHECK(status->cancel_receipt->effective_frame > status->start_receipt->effective_frame);
      LMDJ_CHECK(status->start_frame == *status->count_in_frame + 48000); // Independent 240 BPM literal.
    }
    LMDJ_CHECK(f.engine.acknowledge_scheduled_pattern_record(19, serial, e1));
    LMDJ_CHECK(f.engine.acknowledge_scheduled_pattern_record(19, serial, e2));
    const auto release = f.engine.enqueue_pattern_input({19, 1, 0, 0, true, press.sequence});
    LMDJ_CHECK(release.result == PatternInputSubmit::accepted);
    LMDJ_CHECK(release.sequence > last_sequence && release.acceptance_ordinal > last_ordinal);
    last_sequence = release.sequence; last_ordinal = release.acceptance_ordinal;
    wait_for([&] { return f.engine.inspect_pattern_input_completion(19, 1, release.sequence).has_value(); });
    const auto released = f.engine.inspect_pattern_input_completion(19, 1, release.sequence);
    LMDJ_CHECK(released->disposition == PatternInputDisposition::release_no_voice);
    LMDJ_CHECK(released->held_press_sequence == press.sequence && released->authority == press.authority);
    LMDJ_CHECK(f.engine.consume_pattern_input_completion(19, 1, release.sequence));
    LMDJ_CHECK(!f.engine.consume_pattern_input_completion(19, 1, release.sequence));
    LMDJ_CHECK(f.engine.pattern_input_profile_status().held_release_reservations == 0);
    wait_for([&] { return f.engine.scheduled_pattern_record_settled(19, 1, serial); });
    LMDJ_CHECK(!f.engine.scheduled_pattern_record_settled(20, 1, serial));
    LMDJ_CHECK(!f.engine.scheduled_pattern_record_settled(19, 2, serial));
    LMDJ_CHECK(!f.engine.scheduled_pattern_record_settled(19, 1, serial + 1));
    f.engine.reclaim_retired_patterns();
  }
  done.store(true, std::memory_order_release);
  audio.join();
  f.engine.stop();
  LMDJ_CHECK(cancelled + applied == 1000 && applied >= 100);
  LMDJ_CHECK(copied_markers.load(std::memory_order_acquire) >= applied * 4);
  LMDJ_CHECK(f.engine.pattern_input_profile_status().retained_completions == 0);
  LMDJ_CHECK(f.engine.scheduled_pattern_record_quiescent());
}
void physical_fifo_and_completion_ledger_saturate_independently_with_partial_drains() {
  constexpr std::size_t n = kRealtimeQueueCapacity;
  Fixture f(n);
  std::atomic<bool> done{};
  std::atomic<std::uint64_t> requested{}, completed{};
  std::thread audio([&] {
    std::array<float, 128> left{}, right{};
    while (!done.load(std::memory_order_acquire)) {
      if (completed.load(std::memory_order_relaxed) == requested.load(std::memory_order_acquire)) {
        std::this_thread::yield(); // Test callback gate, OUTSIDE the realtime guard.
        continue;
      }
      in_audio = true;
      f.engine.render(left.data(), right.data(), left.size());
      in_audio = false;
      completed.fetch_add(1, std::memory_order_release);
    }
  });
  const auto one_callback = [&] {
    const auto target = requested.fetch_add(1, std::memory_order_release) + 1;
    wait_for([&] { return completed.load(std::memory_order_acquire) == target; });
  };
  std::array<PatternInputAdmission, n> held{}, ordinary{}, releases{};
  for (unsigned cycle = 0; cycle < 16; ++cycle) {
    for (auto& admission : held) {
      admission = f.press();
      LMDJ_CHECK(admission.result == PatternInputSubmit::accepted);
    }
    LMDJ_CHECK(f.press().result == PatternInputSubmit::queue_full);
    one_callback();
    for (const auto admission : held) {
      const auto terminal = f.engine.inspect_pattern_input_completion(19, 1, admission.sequence);
      LMDJ_CHECK(terminal && terminal->disposition == PatternInputDisposition::muted_no_voice);
      LMDJ_CHECK(f.engine.consume_pattern_input_completion(19, 1, admission.sequence));
    }
    LMDJ_CHECK(f.engine.pattern_input_profile_status().held_release_reservations == n);
    LMDJ_CHECK(f.press().result == PatternInputSubmit::release_full);
    for (auto& admission : ordinary) {
      admission = f.press(false);
      LMDJ_CHECK(admission.result == PatternInputSubmit::accepted);
    }
    for (std::size_t i = 0; i < n; ++i) {
      releases[i] = f.engine.enqueue_pattern_input({19, 1, 0, 0, true, held[i].sequence});
      LMDJ_CHECK(releases[i].result == PatternInputSubmit::accepted);
      LMDJ_CHECK(releases[i].acceptance_ordinal > ordinary.back().acceptance_ordinal);
    }
    LMDJ_CHECK(f.engine.telemetry().queued_events == 2 * n);
    one_callback(); // The unchanged 1024-entry callback budget drains ONLY ordinary entries.
    LMDJ_CHECK(f.engine.telemetry().queued_events == n);
    LMDJ_CHECK(f.engine.pattern_input_profile_status().ordinary_pending == 0);
    LMDJ_CHECK(!f.engine.inspect_pattern_input_completion(19, 1, releases.front().sequence));
    LMDJ_CHECK(f.press(false).result == PatternInputSubmit::completion_full);
    one_callback();
    LMDJ_CHECK(f.engine.telemetry().queued_events == 0);
    LMDJ_CHECK(f.engine.pattern_input_profile_status().held_release_reservations == n);
    for (std::size_t i = 0; i < n; ++i) {
      const auto release = f.engine.inspect_pattern_input_completion(19, 1, releases[i].sequence);
      LMDJ_CHECK(release && release->held_press_sequence == held[i].sequence &&
          release->authority == held[i].authority &&
          release->disposition == PatternInputDisposition::release_no_voice);
      LMDJ_CHECK(f.engine.consume_pattern_input_completion(19, 1, releases[i].sequence));
      LMDJ_CHECK(!f.engine.consume_pattern_input_completion(19, 1, releases[i].sequence));
      LMDJ_CHECK(f.engine.consume_pattern_input_completion(19, 1, ordinary[i].sequence));
    }
    const auto status = f.engine.pattern_input_profile_status();
    LMDJ_CHECK(status.held_release_reservations == 0 && status.retained_completions == 0);
  }
  done.store(true, std::memory_order_release); audio.join();
  f.engine.stop();
  LMDJ_CHECK(f.engine.scheduled_pattern_record_quiescent());
}

}  // namespace

void* operator new(std::size_t bytes) { return allocate(bytes); }
void* operator new[](std::size_t bytes) { return allocate(bytes); }
void* operator new(std::size_t bytes, std::align_val_t alignment) {
  if (in_audio) std::abort();
  void* p{};
  const auto bound = static_cast<std::size_t>(alignment);
  if (posix_memalign(&p, bound, bytes == 0 ? bound : bytes) == 0) return p;
  throw std::bad_alloc{};
}
void* operator new[](std::size_t bytes, std::align_val_t alignment) {
  return ::operator new(bytes, alignment);
}
void operator delete(void* p) noexcept { free_allocation(p); }
void operator delete[](void* p) noexcept { free_allocation(p); }
void operator delete(void* p, std::size_t) noexcept { free_allocation(p); }
void operator delete[](void* p, std::size_t) noexcept { free_allocation(p); }
void operator delete(void* p, std::align_val_t) noexcept { free_allocation(p); }
void operator delete[](void* p, std::align_val_t) noexcept { free_allocation(p); }
void operator delete(void* p, std::size_t, std::align_val_t) noexcept { free_allocation(p); }
void operator delete[](void* p, std::size_t, std::align_val_t) noexcept { free_allocation(p); }

int main() {
  exact_receipts_and_silent_release_escrow_under_concurrent_audio();
  physical_fifo_and_completion_ledger_saturate_independently_with_partial_drains();
}
