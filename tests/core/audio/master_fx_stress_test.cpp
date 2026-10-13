#include <lmdj/audio/master_fx.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <exception>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string_view>
#include <string>
#include <thread>
#include <vector>

#if defined(__linux__)
#include <sched.h>
#endif

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::FxEnqueueResult;
using lmdj::audio::FxGesture;
using lmdj::audio::FxGestureKind;
using lmdj::audio::RealtimeEngine;

#ifndef LMDJ_MASTER_FX_VERIFY_REALTIME_DEADLINE
#error "Master FX stress timing policy must be selected by CMake"
#endif

constexpr bool kVerifyRealtimeDeadline =
    LMDJ_MASTER_FX_VERIFY_REALTIME_DEADLINE != 0;

#ifndef LMDJ_MASTER_FX_VERIFY_OPTIMIZED_DEADLINE
#error "Master FX stress timing policy must be selected by CMake"
#endif

// #1667's every-stage scenario is timed only in an optimized build, the build
// the nightly Release stress gate runs (owner decision 2026-10-02). At -O0 its
// four filter stages per voice leave the callback just under the deadline on
// a performance core and past it on an efficiency core, which measures the
// unoptimized code rather than the shipped kernel.
constexpr bool kVerifyOptimizedDeadline =
    LMDJ_MASTER_FX_VERIFY_OPTIMIZED_DEADLINE != 0;

std::chrono::nanoseconds current_thread_cpu_time() {
  timespec observed{};
  LMDJ_CHECK(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &observed) == 0);
  return std::chrono::seconds(observed.tv_sec) +
         std::chrono::nanoseconds(observed.tv_nsec);
}

// #666: both self-hosted hosts are KVM guests whose kernels have
// CONFIG_PARAVIRT_TIME_ACCOUNTING and CONFIG_IRQ_TIME_ACCOUNTING off, so
// CLOCK_THREAD_CPUTIME_ID bills hypervisor steal and hardirq time to
// whatever thread was running. The deadline gate therefore samples the host
// accounting counters around every render window and attributes an overrun
// whose window coincides with stolen or interrupt time instead of counting
// it against the callback. The gate stays exactly zero *unattributed*
// overruns — the property the test exists to defend.
struct HostAccounting {
  std::uint64_t steal_ticks = 0;
  std::uint64_t irq_ticks = 0;
  std::uint64_t softirq_ticks = 0;

  std::uint64_t total() const {
    return steal_ticks + irq_ticks + softirq_ticks;
  }
};

struct HostAccountingSample {
  int cpu = -1;
  HostAccounting per_cpu;
  bool valid = false;
};

bool parse_stat_counters(
    std::string_view line, std::size_t skip, HostAccounting& counters) {
  if (skip > line.size()) {
    return false;
  }
  // /proc/stat has eight required fields and up to two guest fields. Parse
  // complete unsigned tokens: scanf would accept negative or partial values.
  std::array<std::uint64_t, 10> fields{};
  std::size_t count = 0;
  auto remaining = line.substr(skip);
  while (true) {
    const auto first = remaining.find_first_not_of(" \t");
    if (first == std::string_view::npos) {
      break;
    }
    remaining.remove_prefix(first);
    if (count == fields.size()) {
      return false;
    }
    const auto end = remaining.find_first_of(" \t");
    const auto token = remaining.substr(0, end);
    const auto parsed = std::from_chars(
        token.data(), token.data() + token.size(), fields[count]);
    if (parsed.ec != std::errc{} || parsed.ptr != token.data() + token.size()) {
      return false;
    }
    ++count;
    remaining.remove_prefix(token.size());
  }
  if (count < 8) {
    return false;
  }
  counters = {fields[7], fields[5], fields[6]};
  return true;
}

HostAccountingSample read_host_accounting(std::istream& stat, int cpu) {
  HostAccountingSample sample;
  sample.cpu = cpu;
  if (cpu < 0) {
    return sample;
  }
  const auto wanted = "cpu" + std::to_string(cpu) + " ";
  std::string line;
  while (std::getline(stat, line)) {
    // Exact prefix: cpu1 cannot borrow the counters of cpu10 or cpu1x.
    if (line.rfind(wanted, 0) == 0) {
      sample.valid = !stat.bad() &&
                     parse_stat_counters(line, wanted.size(), sample.per_cpu);
      break;
    }
  }
  return sample;
}

HostAccountingSample host_accounting_sample() {
#if defined(__linux__)
  const auto cpu = sched_getcpu();
  std::ifstream stat("/proc/stat");
  return read_host_accounting(stat, cpu);
#else
  return {};
#endif
}

HostAccounting host_accounting_delta(
    const HostAccountingSample& before, const HostAccountingSample& after) {
  // Equal endpoint CPUs cannot prove no migration occurred in between.
  // Preserve the existing per-vCPU predicate, but reject the entire window
  // on missing evidence or any decreasing counter before unsigned arithmetic.
  if (before.cpu < 0 || before.cpu != after.cpu ||
      !before.valid || !after.valid ||
      after.per_cpu.steal_ticks < before.per_cpu.steal_ticks ||
      after.per_cpu.irq_ticks < before.per_cpu.irq_ticks ||
      after.per_cpu.softirq_ticks < before.per_cpu.softirq_ticks) {
    return {};
  }
  HostAccounting delta;
  delta.steal_ticks = after.per_cpu.steal_ticks - before.per_cpu.steal_ticks;
  delta.irq_ticks = after.per_cpu.irq_ticks - before.per_cpu.irq_ticks;
  delta.softirq_ticks =
      after.per_cpu.softirq_ticks - before.per_cpu.softirq_ticks;
  return delta;
}

struct RenderMeasurement {
  std::chrono::nanoseconds elapsed{};
  HostAccountingSample host_before;
  HostAccountingSample host_after;

  bool exceeds(std::chrono::nanoseconds deadline) const {
    return elapsed > deadline;
  }
};

template <typename Render, typename Clock, typename Sample>
RenderMeasurement measure_render(
    bool verify_deadline, Render render, Clock clock, Sample sample) {
  if (!verify_deadline) {
    render();
    return {};
  }
  const auto host_before = sample();
  const auto started = clock();
  render();
  const auto elapsed = clock() - started;
  const auto host_after = sample();
  return {elapsed, host_before, host_after};
}

RenderMeasurement scripted_render(
    std::chrono::nanoseconds render_cost,
    std::chrono::nanoseconds after_sample_cost,
    HostAccountingSample before = {}, HostAccountingSample after = {}) {
  std::chrono::nanoseconds cpu{};
  unsigned samples = 0;
  return measure_render(
      true, [&] { cpu += render_cost; }, [&] { return cpu; }, [&] {
        if (samples++ == 0) {
          cpu += std::chrono::nanoseconds{3'000'000};
          return before;
        }
        cpu += after_sample_cost;
        return after;
      });
}

void sampler_work_is_outside_render_clock() {
  // The oracle is a scripted CPU timeline, not agreement between two copies
  // of the measurement code: only the render advances it by 50,000 ns.
  const auto before_only = scripted_render(
      std::chrono::nanoseconds{50'000}, std::chrono::nanoseconds{0});
  if (before_only.elapsed.count() != 50'000) {
    std::cerr << "why: before sampler entered render clock; expected 50000 ns, "
              << "observed " << before_only.elapsed.count()
              << " ns; remedy: sample host before CPU start.\n";
  }
  LMDJ_CHECK(before_only.elapsed.count() == 50'000);
  const auto both_samplers = scripted_render(
      std::chrono::nanoseconds{50'000}, std::chrono::nanoseconds{7'000'000});
  if (both_samplers.elapsed.count() != 50'000) {
    std::cerr << "why: after sampler entered render clock; expected 50000 ns, "
              << "observed " << both_samplers.elapsed.count()
              << " ns; remedy: end CPU clock before sampling host.\n";
  }
  LMDJ_CHECK(both_samplers.elapsed.count() == 50'000);
}

HostAccountingSample scripted_stat(std::string_view text, int cpu = 1) {
  std::istringstream stat{std::string(text)};
  return read_host_accounting(stat, cpu);
}

void render_deadline_and_accounting_are_strict() {
  constexpr auto deadline = std::chrono::nanoseconds{2'666'666};
  const auto zero = scripted_stat("cpu1 0 0 0 0 0 0 0 0\n");
  LMDJ_CHECK(zero.valid);
  LMDJ_CHECK(zero.per_cpu.total() == 0);
  const auto nonzero = scripted_stat("cpu1 1 2 3 4 5 6 7 8 9 10\n");
  LMDJ_CHECK(nonzero.valid);
  LMDJ_CHECK(nonzero.per_cpu.irq_ticks == 6);
  LMDJ_CHECK(nonzero.per_cpu.softirq_ticks == 7);
  LMDJ_CHECK(nonzero.per_cpu.steal_ticks == 8);

  // Slow sampling cannot excuse real render work. Both boundaries and the
  // production loops use the same measurement and strict greater-than test.
  const auto overrun = scripted_render(
      deadline + std::chrono::nanoseconds{1},
      std::chrono::nanoseconds{7'000'000}, zero, zero);
  LMDJ_CHECK(overrun.elapsed.count() == 2'666'667);
  const auto unattributed = overrun.exceeds(deadline) &&
      host_accounting_delta(overrun.host_before, overrun.host_after).total() == 0;
  LMDJ_CHECK(static_cast<unsigned>(unattributed) == 1);
  const auto boundary = scripted_render(
      deadline, std::chrono::nanoseconds{7'000'000}, zero, zero);
  LMDJ_CHECK(boundary.elapsed.count() == 2'666'666);
  LMDJ_CHECK(!boundary.exceeds(deadline));

  const auto check_unattributed = [&](HostAccountingSample before,
                                     HostAccountingSample after,
                                     std::string_view fact) {
    const auto measured = scripted_render(
        deadline + std::chrono::nanoseconds{1},
        std::chrono::nanoseconds{7'000'000}, before, after);
    LMDJ_CHECK(measured.exceeds(deadline));
    const auto delta = host_accounting_delta(
        measured.host_before, measured.host_after);
    lmdj::test::check(delta.steal_ticks == 0 && delta.irq_ticks == 0 &&
                          delta.softirq_ticks == 0,
                      std::string("why: ") + std::string(fact) +
                          " attributed an invalid window; remedy: validate "
                          "both samples and every counter before subtraction");
  };

  // An unopened file exercises actual failed stream reading with a known CPU,
  // not an injected validity flag. A zero after-value must not wrap unsigned.
  std::ifstream unreadable;
  const auto failed_read = read_host_accounting(unreadable, 1);
  LMDJ_CHECK(failed_read.cpu == 1);
  LMDJ_CHECK(!failed_read.valid);
  check_unattributed(nonzero, failed_read, "invalid-after false-wrap");
  check_unattributed(failed_read, nonzero, "invalid-before positive counters");

  const std::array<std::string_view, 7> malformed{
      "cpu1 0 0 0 0 0 0 0\n", "cpu1 0 0 0 0 0 0 0 x\n",
      "cpu1 0 0 0 0 0 -1 0 0\n", "cpu1 0 0 0 0 0 0 0 1x\n",
      "cpu1 0 0 0 0 0 0 0 18446744073709551616\n",
      "cpu1 0 0 0 0 0 0 0 0 invalid\n",
      "cpu1 0 0 0 0 0 0 0 0 0 0 0\n"};
  for (const auto text : malformed) {
    const auto invalid = scripted_stat(text);
    LMDJ_CHECK(!invalid.valid);
    check_unattributed(nonzero, invalid, text);
    check_unattributed(invalid, nonzero, text);
  }
  const auto missing = scripted_stat("cpu10 0 0 0 0 0 6 7 8\n");
  LMDJ_CHECK(!missing.valid);
  check_unattributed(nonzero, missing, "missing exact CPU line");
  const auto exact = scripted_stat(
      "cpu10 0 0 0 0 0 6 7 8\ncpu1 0 0 0 0 0 0 0 0\n");
  LMDJ_CHECK(exact.valid);
  LMDJ_CHECK(exact.per_cpu.total() == 0);
  check_unattributed(zero, exact, "cpu1/cpu10 distinction");
  const auto unknown = scripted_stat("cpu1 0 0 0 0 0 6 7 8\n", -1);
  LMDJ_CHECK(!unknown.valid);
  check_unattributed(unknown, nonzero, "unknown before CPU");
  check_unattributed(nonzero, unknown, "unknown after CPU");
  const auto other_cpu = scripted_stat("cpu2 0 0 0 0 0 9 10 11\n", 2);
  LMDJ_CHECK(other_cpu.valid);
  check_unattributed(nonzero, other_cpu, "mismatched CPU");

  // Each accounted field decreases separately while the other fields rise:
  // rejection must cover the whole window, not just clamp one subtraction.
  for (const auto text : {"cpu1 0 0 0 0 0 5 9 10\n",
                          "cpu1 0 0 0 0 0 8 6 10\n",
                          "cpu1 0 0 0 0 0 8 9 7\n"}) {
    const auto decreased = scripted_stat(text);
    LMDJ_CHECK(decreased.valid);
    check_unattributed(nonzero, decreased, text);
  }
  for (const auto text : {"cpu1 0 0 0 0 0 1 0 0\n",
                          "cpu1 0 0 0 0 0 0 1 0\n",
                          "cpu1 0 0 0 0 0 0 0 1\n"}) {
    const auto positive = scripted_stat(text);
    LMDJ_CHECK(positive.valid);
    const auto measured = scripted_render(
        deadline + std::chrono::nanoseconds{1},
        std::chrono::nanoseconds{7'000'000}, zero, positive);
    LMDJ_CHECK(measured.exceeds(deadline));
    LMDJ_CHECK(host_accounting_delta(
                   measured.host_before, measured.host_after).total() == 1);
  }
}

void all_eight_effects_sustain_maximum_gesture_rate_without_underruns() {
  constexpr std::uint32_t kFramesPerQuantum = 128;
  constexpr std::uint32_t kSimulatedSeconds = 10;
  constexpr std::uint32_t kQuanta =
      (48'000U * kSimulatedSeconds) / kFramesPerQuantum;
  // One source of truth: the render loop enforces this and the failure message
  // reports it, so the two can never disagree.
  constexpr auto kCallbackDeadline = std::chrono::nanoseconds{
      1'000'000'000ULL * kFramesPerQuantum / 48'000U};
  RealtimeEngine engine;
  std::vector<float> sample(
      static_cast<std::size_t>(kQuanta) * kFramesPerQuantum, 0.0F);
  for (std::size_t frame = 0; frame < sample.size(); ++frame) {
    sample[frame] =
        static_cast<float>(static_cast<std::int32_t>(frame % 127U) - 63) /
        96.0F;
  }
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(173).has_value());
  LMDJ_CHECK(engine.start().has_value());

  std::atomic<bool> render_failed{false};
  std::atomic<bool> heard_processed_voice{false};
  // Unattributed overruns: the gate, still exactly zero. An overrun whose
  // window coincides with host steal/IRQ accounting (#666) is attributed and
  // reported instead of counted.
  std::atomic<std::uint64_t> callback_overruns{0};
  std::atomic<std::uint64_t> callback_overruns_attributed{0};
  std::atomic<std::uint64_t> attributed_steal_ticks{0};
  std::atomic<std::uint64_t> attributed_irq_ticks{0};
  std::atomic<std::uint64_t> attributed_softirq_ticks{0};
  // Retained so a failure reports how far past the deadline the callback went.
  // The assertion below stays exactly zero overruns; these only make the
  // failure legible, because "!= 0" alone cannot separate a real-time defect
  // from a degraded host.
  std::atomic<std::uint64_t> callback_total_ns{0};
  std::atomic<std::uint64_t> callback_max_ns{0};
  std::atomic<std::uint32_t> control_ready_quanta{0};
  std::atomic<std::uint32_t> rendered_quanta{0};
  std::atomic<std::uint32_t> active_voice_quanta{0};
  std::uint64_t accepted = 0;

  for (const auto fx : lmdj::audio::kFxChainOrder) {
    LMDJ_CHECK(engine.enqueue_fx_gesture(
                   FxGesture{FxGestureKind::engage, fx, 1'000}) ==
               FxEnqueueResult::accepted);
    ++accepted;
  }
  LMDJ_CHECK(
      engine.enqueue(lmdj::audio::TriggerEvent{1, 0, 127}) ==
      lmdj::audio::EnqueueResult::accepted);

  std::thread renderer([&] {
    std::array<float, kFramesPerQuantum> left{};
    std::array<float, kFramesPerQuantum> right{};
    for (std::uint32_t quantum = 0; quantum < kQuanta; ++quantum) {
      while (control_ready_quanta.load(std::memory_order_acquire) <= quantum) {
        std::this_thread::yield();
      }
      // A shared CI runner may deschedule this thread for longer than an audio
      // quantum, so the production timing gate uses thread CPU time. On a KVM
      // guest without CONFIG_PARAVIRT_TIME_ACCOUNTING /
      // CONFIG_IRQ_TIME_ACCOUNTING that clock also bills hypervisor and
      // interrupt time to this thread (#666), so the gate samples the host
      // accounting counters around the window and attributes such overruns
      // instead of counting them. Sanitizer builds retain this concurrent
      // stress path for safety checks but cannot represent production
      // callback timing because every memory access is instrumented.
      const auto measurement = measure_render(
          kVerifyRealtimeDeadline,
          [&] { engine.render(left.data(), right.data(), left.size()); },
          current_thread_cpu_time, host_accounting_sample);
      const auto elapsed = measurement.elapsed;
      if (kVerifyRealtimeDeadline) {
        const auto observed_ns = static_cast<std::uint64_t>(elapsed.count());
        if (measurement.exceeds(kCallbackDeadline)) {
          const auto attribution =
              host_accounting_delta(measurement.host_before, measurement.host_after);
          if (attribution.total() > 0) {
            callback_overruns_attributed.fetch_add(
                1, std::memory_order_relaxed);
            attributed_steal_ticks.fetch_add(
                attribution.steal_ticks, std::memory_order_relaxed);
            attributed_irq_ticks.fetch_add(
                attribution.irq_ticks, std::memory_order_relaxed);
            attributed_softirq_ticks.fetch_add(
                attribution.softirq_ticks, std::memory_order_relaxed);
          } else {
            callback_overruns.fetch_add(1, std::memory_order_relaxed);
          }
        }
        callback_total_ns.fetch_add(observed_ns, std::memory_order_relaxed);
        auto previous = callback_max_ns.load(std::memory_order_relaxed);
        while (observed_ns > previous &&
               !callback_max_ns.compare_exchange_weak(
                   previous, observed_ns, std::memory_order_relaxed)) {
        }
      }
      for (std::size_t frame = 0; frame < left.size(); ++frame) {
        if (!std::isfinite(left[frame]) || !std::isfinite(right[frame])) {
          render_failed.store(true, std::memory_order_release);
        }
        if (std::abs(left[frame]) > 0.00001F ||
            std::abs(right[frame]) > 0.00001F) {
          heard_processed_voice.store(true, std::memory_order_relaxed);
        }
      }
      const auto realtime = engine.telemetry();
      if (realtime.active_voices == 1 ||
          (quantum + 1U == kQuanta && realtime.completed_voices == 1)) {
        active_voice_quanta.fetch_add(1, std::memory_order_relaxed);
      }
      rendered_quanta.store(quantum + 1U, std::memory_order_release);
    }
  });

  auto enqueue = [&](FxGesture gesture) {
    auto result = FxEnqueueResult::queue_full;
    while (result == FxEnqueueResult::queue_full) {
      result = engine.enqueue_fx_gesture(gesture);
      if (result == FxEnqueueResult::queue_full) {
        std::this_thread::yield();
      }
    }
    LMDJ_CHECK(result == FxEnqueueResult::accepted);
    ++accepted;
  };

  for (std::uint32_t round = 0; round < kQuanta; ++round) {
    for (std::size_t index = 0; index < lmdj::audio::kFxChainOrder.size();
         ++index) {
      const auto fx = lmdj::audio::kFxChainOrder[index];
      enqueue(FxGesture{
          FxGestureKind::move,
          fx,
          static_cast<std::uint16_t>((round * 17U + index) % 1'001U)});
    }
    control_ready_quanta.store(round + 1U, std::memory_order_release);
    while (rendered_quanta.load(std::memory_order_acquire) <= round) {
      std::this_thread::yield();
    }
  }
  renderer.join();
  engine.stop();

  const auto fx = engine.master_fx_telemetry();
  const auto realtime = engine.telemetry();
  LMDJ_CHECK(!render_failed.load(std::memory_order_acquire));
  LMDJ_CHECK(heard_processed_voice.load(std::memory_order_relaxed));
  if (kVerifyRealtimeDeadline &&
      callback_overruns.load(std::memory_order_relaxed) != 0) {
    const auto kDeadlineNs =
        static_cast<std::uint64_t>(kCallbackDeadline.count());
    const auto overruns = callback_overruns.load(std::memory_order_relaxed);
    const auto attributed =
        callback_overruns_attributed.load(std::memory_order_relaxed);
    const auto max_ns = callback_max_ns.load(std::memory_order_relaxed);
    const auto mean_ns =
        callback_total_ns.load(std::memory_order_relaxed) / kQuanta;
    std::cerr
        << "why: the master FX render thread missed its real-time deadline "
           "with no host accounting attribution. "
        << overruns << " of " << kQuanta << " callbacks exceeded "
        << kDeadlineNs << " ns of thread CPU time while no steal/IRQ/softirq "
           "counter advanced on the render thread's vCPU inside the window; "
           "mean "
        << mean_ns << " ns, worst " << max_ns << " ns ("
        << (max_ns / (kDeadlineNs / 100)) << "% of the deadline). A further "
        << attributed
        << " overruns coincided with host accounting events (steal "
        << attributed_steal_ticks.load(std::memory_order_relaxed)
        << " ticks, irq "
        << attributed_irq_ticks.load(std::memory_order_relaxed)
        << ", softirq "
        << attributed_softirq_ticks.load(std::memory_order_relaxed)
        << ") and were attributed, not counted (#666).\n"
        << "remedy: this budget is not marginal — a healthy host renders this "
           "quantum in tens of microseconds, so an unattributed worst case "
           "near or past the deadline means the FX callback path regressed. "
           "Compare the mean above against a run on an uncontended host "
           "before changing the test; never raise the deadline to make this "
           "pass. The attributed count exists because a KVM guest without "
           "CONFIG_PARAVIRT_TIME_ACCOUNTING/CONFIG_IRQ_TIME_ACCOUNTING bills "
           "hypervisor and interrupt time to the running thread; investigate "
           "if it climbs without the unattributed count moving, since a real "
           "regression can coincide with a host accounting event.\n";
  }
  if (kVerifyRealtimeDeadline &&
      callback_overruns_attributed.load(std::memory_order_relaxed) != 0) {
    std::cerr
        << "note: "
        << callback_overruns_attributed.load(std::memory_order_relaxed)
        << " of " << kQuanta
        << " callbacks exceeded the deadline inside a window where host "
           "steal/IRQ/softirq counters advanced and were attributed, not "
           "counted (#666; steal "
        << attributed_steal_ticks.load(std::memory_order_relaxed)
        << " ticks, irq "
        << attributed_irq_ticks.load(std::memory_order_relaxed)
        << ", softirq "
        << attributed_softirq_ticks.load(std::memory_order_relaxed)
        << ").\n";
  }
  LMDJ_CHECK(callback_overruns.load(std::memory_order_relaxed) == 0);
  LMDJ_CHECK(active_voice_quanta.load(std::memory_order_relaxed) == kQuanta);
  LMDJ_CHECK(fx.enqueued_gestures == accepted);
  LMDJ_CHECK(fx.dequeued_gestures == accepted);
  LMDJ_CHECK(fx.queued_gestures == 0);
  LMDJ_CHECK(fx.processed_frames == realtime.rendered_frames);
  LMDJ_CHECK(fx.processed_frames >= kFramesPerQuantum);
  LMDJ_CHECK(realtime.started_voices == 1);
  LMDJ_CHECK(realtime.completed_voices == 1);
}

// The Sample parity worst case (decision 2026-09-30): every voice slot runs the
// shared kernel with every #1666 stage on while all eight master FX run at
// maximum; with tone_stages, every #1667 stage too. All 128 triggers land in
// one callback, so kernel preparation is inside the measured window. The gate
// is the same deadline and the same zero unattributed overruns; it is never
// raised to make this pass.
void run_full_kernel_voice_pool(bool tone_stages, bool verify_deadline) {
  using lmdj::audio::EnqueueResult;
  using lmdj::audio::PadControlEvent;
  using lmdj::audio::PadControlKind;
  using lmdj::audio::PreparedSampleBank;
  using lmdj::audio::PublishResult;
  using lmdj::cooker::ResolvedPlayback;
  using lmdj::cooker::ResolvedVoiceDsp;
  constexpr std::uint32_t kFramesPerQuantum = 128;
  constexpr std::uint32_t kSimulatedSeconds = 5;
  constexpr std::uint32_t kQuanta =
      (48'000U * kSimulatedSeconds) / kFramesPerQuantum;
  constexpr auto kCallbackDeadline = std::chrono::nanoseconds{
      1'000'000'000ULL * kFramesPerQuantum / 48'000U};
  constexpr std::uint32_t kSampleFrames = 24'000;
  constexpr std::uint8_t kSlots = 64;

  std::vector<float> sample(kSampleFrames);
  for (std::size_t frame = 0; frame < sample.size(); ++frame) {
    sample[frame] = 0.004F * std::sin(static_cast<float>(frame) * 0.013F);
  }
  auto bank = PreparedSampleBank::empty(
      lmdj::foundation::ProjectId{"00000000-0000-4000-8000-000000000001"}, 1);
  for (std::uint8_t slot = 0; slot < kSlots; ++slot) {
    LMDJ_CHECK(bank.set_sample(slot, sample).has_value());
  }
  RealtimeEngine engine;
  LMDJ_CHECK(engine.publish_sample_bank(std::move(bank)) == PublishResult::accepted);
  LMDJ_CHECK(engine.prepare_master_fx(173).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (const auto fx : lmdj::audio::kFxChainOrder) {
    LMDJ_CHECK(engine.enqueue_fx_gesture(
                   FxGesture{FxGestureKind::engage, fx, 1'000}) ==
               FxEnqueueResult::accepted);
  }
  for (std::uint8_t slot = 0; slot < kSlots; ++slot) {
    ResolvedPlayback playback{0, kSampleFrames, lmdj::domain::TriggerMode::loop_gate,
                              1.0F, false};
    const bool ping_pong = slot % 2 == 1;
    playback.dsp = ResolvedVoiceDsp{
        kSampleFrames / 4,
        ping_pong ? 0U : kSampleFrames / 8,
        static_cast<std::int16_t>(-1100 + slot * 37),
        static_cast<std::int8_t>(slot % 3 == 0 ? -60 : 45),
        static_cast<std::uint8_t>(
            (slot % 4 < 2 ? ResolvedVoiceDsp::kReverse : 0) |
            (ping_pong ? ResolvedVoiceDsp::kPingPong : 0))};
    if (tone_stages) {
      // A long attack and release, a tone and all three EQ bands, so every
      // voice runs four filter stages (the decision's worst case). Every
      // fourth slot drags both shelves to cuts.
      auto& dsp = playback.dsp;
      dsp.attack_frames = 4'800;
      dsp.release_frames = 9'600;
      dsp.tone = static_cast<std::int8_t>(slot % 2 == 0 ? -60 : 60);
      const bool cuts = slot % 4 == 3;
      dsp.eq_flags = static_cast<std::uint8_t>(
          ResolvedVoiceDsp::kEqLow | ResolvedVoiceDsp::kEqMid |
          ResolvedVoiceDsp::kEqHigh |
          (cuts ? ResolvedVoiceDsp::kEqLowCut | ResolvedVoiceDsp::kEqHighCut
                : 0));
      dsp.eq_low_freq_hz = 120;
      dsp.eq_low_gain_millidb = 6'000;
      dsp.eq_mid_freq_hz = 1'500;
      dsp.eq_mid_gain_millidb = -9'000;
      dsp.eq_mid_q_milli = 3'000;
      dsp.eq_high_freq_hz = 8'000;
      dsp.eq_high_gain_millidb = 4'000;
    }
    LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                   slot, slot, 0, PadControlKind::preview_set, playback}) ==
               EnqueueResult::accepted);
    for (std::uint8_t press = 0; press < 2; ++press) {
      LMDJ_CHECK(engine.enqueue_control(PadControlEvent{
                     1'000U + slot * 2U + press, slot, 127,
                     PadControlKind::press, ResolvedPlayback{}}) ==
                 EnqueueResult::accepted);
    }
  }

  std::uint64_t overruns = 0;
  std::uint64_t attributed = 0;
  std::uint64_t worst_ns = 0;
  std::uint64_t total_ns = 0;
  std::uint32_t full_pool_quanta = 0;
  bool finite = true;
  std::array<float, kFramesPerQuantum> left{};
  std::array<float, kFramesPerQuantum> right{};
  for (std::uint32_t quantum = 0; quantum < kQuanta; ++quantum) {
    const auto measurement = measure_render(
        verify_deadline,
        [&] { engine.render(left.data(), right.data(), left.size()); },
        current_thread_cpu_time, host_accounting_sample);
    if (verify_deadline) {
      const auto elapsed = measurement.elapsed;
      const auto observed_ns = static_cast<std::uint64_t>(elapsed.count());
      worst_ns = std::max(worst_ns, observed_ns);
      total_ns += observed_ns;
      if (measurement.exceeds(kCallbackDeadline)) {
        if (host_accounting_delta(measurement.host_before, measurement.host_after).total() > 0) {
          ++attributed;
        } else {
          ++overruns;
        }
      }
    }
    for (std::size_t frame = 0; frame < left.size(); ++frame) {
      finite = finite && std::isfinite(left[frame]) && std::isfinite(right[frame]);
    }
    if (engine.telemetry().active_voices == 128) {
      ++full_pool_quanta;
    }
  }
  engine.stop();
  if (overruns != 0) {
    std::cerr << "why: " << overruns << " of " << kQuanta
              << " callbacks with 128 kernel voices"
              << (tone_stages ? " running every tone stage" : "")
              << " and all eight FX exceeded "
              << kCallbackDeadline.count()
              << " ns of thread CPU time with no host accounting attribution; "
                 "mean "
              << total_ns / kQuanta << " ns, worst " << worst_ns << " ns ("
              << attributed << " further overruns were attributed, #666).\n"
              << "remedy: the voice DSP kernel or its trigger-time preparation "
                 "regressed; profile the kernel path and never raise the "
                 "deadline to make this pass.\n";
  }
  LMDJ_CHECK(finite);
  LMDJ_CHECK(overruns == 0);
  LMDJ_CHECK(engine.telemetry().started_voices == 128);
  LMDJ_CHECK(full_pool_quanta == kQuanta);
}

void full_voice_pool_with_every_kernel_stage_holds_the_deadline() {
  run_full_kernel_voice_pool(false, kVerifyRealtimeDeadline);
}

void full_voice_pool_with_every_tone_stage_holds_the_deadline() {
  run_full_kernel_voice_pool(true, kVerifyOptimizedDeadline);
}

using lmdj::audio::FilterGesture;
using lmdj::audio::FilterMode;
using lmdj::audio::FilterPhase;
using lmdj::audio::FilterType;

void typed_filter_queue_full_rejects_without_touching_accepted_state() {
  RealtimeEngine engine;
  LMDJ_CHECK(engine.prepare_master_fx(173).has_value());
  LMDJ_CHECK(engine.start().has_value());

  // No render is draining: the bounded queue fills deterministically.
  for (std::uint32_t index = 0; index < lmdj::audio::kRealtimeQueueCapacity;
       ++index) {
    LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                   FilterPhase::engage,
                   {FilterType::low_pass,
                    20U + index % 19'981U,
                    static_cast<std::uint16_t>(index % 1'001U)}}) ==
               FxEnqueueResult::accepted);
  }
  const auto status_full = engine.filter_control_status();
  LMDJ_CHECK(status_full.accepted_sequence ==
             lmdj::audio::kRealtimeQueueCapacity);
  LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                 FilterPhase::engage, {FilterType::low_pass, 800, 0}}) ==
             FxEnqueueResult::queue_full);
  // The rejection consumes no sequence and leaves the accepted shadow alone.
  LMDJ_CHECK(engine.filter_control_status().accepted_sequence ==
             lmdj::audio::kRealtimeQueueCapacity);
  LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                 FilterPhase::engage, {FilterType::low_pass, 10, 0}}) ==
             FxEnqueueResult::invalid_value);
  LMDJ_CHECK(engine.filter_control_status().accepted_sequence ==
             lmdj::audio::kRealtimeQueueCapacity);
  const auto fx_full = engine.master_fx_telemetry();
  LMDJ_CHECK(fx_full.queued_gestures == lmdj::audio::kRealtimeQueueCapacity);
  LMDJ_CHECK(fx_full.queue_drops == 1);

  // One callback drains the full queue; applied catches up with accepted.
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  engine.render(left.data(), right.data(), left.size());
  const auto status = engine.filter_control_status();
  LMDJ_CHECK(status.applied.sequence == status.accepted_sequence);
  LMDJ_CHECK(status.applied.state.mode == FilterMode::independent);
  LMDJ_CHECK(status.applied.state.engaged);
  const auto last = lmdj::audio::kRealtimeQueueCapacity - 1;
  LMDJ_CHECK(status.applied.state.parameters.cutoff_hz ==
             20U + last % 19'981U);
  LMDJ_CHECK(status.applied.state.parameters.resonance_milli ==
             static_cast<std::uint16_t>(last % 1'001U));
  const auto fx = engine.master_fx_telemetry();
  LMDJ_CHECK(fx.enqueued_filter_controls ==
             lmdj::audio::kRealtimeQueueCapacity);
  LMDJ_CHECK(fx.dequeued_filter_controls ==
             lmdj::audio::kRealtimeQueueCapacity);
  LMDJ_CHECK(fx.queued_gestures == 0);
  engine.stop();
}

// Parameter churn under concurrent render. The real-time deadline ownership
// stays with the two scenarios above (unchanged budgets); this test fixes
// finiteness, bounded-queue rejection and accepted/applied conservation, so
// it runs identically in unoptimized and sanitizer builds.
void independent_filter_churn_stays_finite_bounded_and_coherent() {
  constexpr std::uint32_t kFramesPerQuantum = 128;
  constexpr std::uint32_t kQuanta = 750;
  RealtimeEngine engine;
  std::vector<float> sample(4'096, 0.0F);
  for (std::size_t frame = 0; frame < sample.size(); ++frame) {
    sample[frame] =
        static_cast<float>(static_cast<std::int32_t>(frame % 89U) - 44) /
        96.0F;
  }
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.prepare_master_fx(173).has_value());
  LMDJ_CHECK(engine.start().has_value());
  LMDJ_CHECK(
      engine.enqueue(lmdj::audio::TriggerEvent{1, 0, 127}) ==
      lmdj::audio::EnqueueResult::accepted);

  std::atomic<bool> render_failed{false};
  std::atomic<std::uint32_t> rendered_quanta{0};
  // Pause handshake makes the queue-full burst deterministic: the renderer
  // acknowledges it is between callbacks before the control thread floods
  // the bounded queue, so rejection cannot depend on scheduling luck.
  std::atomic<bool> pause_rendering{false};
  std::atomic<bool> render_paused{false};
  // Bounded renderer lead: quantum k may render only once the control thread
  // has entered round k. The renderer can therefore never exit before the
  // round-100 handshake — reaching it, it must pass through this spin and
  // ACK the pause instead of leaving the control thread waiting forever.
  std::atomic<std::uint32_t> control_round{0};
  std::thread renderer([&] {
    std::array<float, kFramesPerQuantum> left{};
    std::array<float, kFramesPerQuantum> right{};
    for (std::uint32_t quantum = 0; quantum < kQuanta; ++quantum) {
      while (pause_rendering.load(std::memory_order_acquire) ||
             control_round.load(std::memory_order_acquire) <= quantum) {
        if (pause_rendering.load(std::memory_order_acquire)) {
          render_paused.store(true, std::memory_order_release);
        }
        std::this_thread::yield();
      }
      engine.render(left.data(), right.data(), left.size());
      for (std::size_t frame = 0; frame < left.size(); ++frame) {
        if (!std::isfinite(left[frame]) || !std::isfinite(right[frame])) {
          render_failed.store(true, std::memory_order_release);
        }
      }
      rendered_quanta.store(quantum + 1U, std::memory_order_release);
    }
  });

  std::uint64_t accepted_typed = 0;
  std::uint64_t accepted_legacy = 0;
  std::uint64_t rejected_full = 0;
  std::uint32_t lcg = 0x12345678U;
  const auto next = [&lcg] {
    lcg = lcg * 1'664'525U + 1'013'904'223U;
    return lcg >> 8;
  };
  const auto typed_control = [&]() -> FilterGesture {
    const auto value = next();
    const auto type = static_cast<FilterType>(value % 3U);
    const auto cutoff = 20U + (value / 3U) % 19'981U;
    const auto resonance =
        static_cast<std::uint16_t>((value / 77U) % 1'001U);
    const auto phase = value % 11U == 0 ? FilterPhase::engage
                       : value % 13U == 0 ? FilterPhase::release
                                          : FilterPhase::move;
    return FilterGesture{phase, {type, cutoff, resonance}};
  };
  const auto enqueue_typed = [&](const FilterGesture& gesture) {
    const auto result = engine.enqueue_filter_gesture(gesture);
    if (result == FxEnqueueResult::queue_full) {
      ++rejected_full;
      return;
    }
    LMDJ_CHECK(result == FxEnqueueResult::accepted);
    ++accepted_typed;
  };
  const auto enqueue_legacy = [&](FxGestureKind kind, std::uint16_t value) {
    const auto result = engine.enqueue_fx_gesture(FxGesture{
        kind, lmdj::domain::PerformanceFx::filter, value});
    if (result == FxEnqueueResult::queue_full) {
      ++rejected_full;
      return;
    }
    LMDJ_CHECK(result == FxEnqueueResult::accepted);
    ++accepted_legacy;
  };

  for (std::uint32_t round = 0; round < kQuanta; ++round) {
    // Publish the entered round before any enqueue: the renderer may lead by
    // at most this round, so it is always alive to answer the pause below.
    control_round.store(round + 1U, std::memory_order_release);
    enqueue_typed(typed_control());
    if (round % 37U == 0) {
      enqueue_typed(FilterGesture{
          FilterPhase::engage,
          {FilterType::band_pass, 20U + next() % 19'981U, 500}});
    }
    if (round % 53U == 0) {
      enqueue_legacy(FxGestureKind::hold_on, 0);
      enqueue_typed(typed_control());
      enqueue_legacy(FxGestureKind::hold_off, 0);
    }
    if (round % 61U == 0) {
      // Legacy takeover and release interleaved with typed controls.
      enqueue_legacy(FxGestureKind::engage,
                     static_cast<std::uint16_t>(next() % 1'001U));
      enqueue_typed(typed_control());
      enqueue_legacy(FxGestureKind::release, 0);
    }
    if (round == 100) {
      // Deterministic flood: with the renderer paused between callbacks, the
      // queue's free space is at most its capacity, so an 1,100-control burst
      // must reject at least 76 controls.
      pause_rendering.store(true, std::memory_order_release);
      while (!render_paused.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      for (std::uint32_t burst = 0; burst < 1'100; ++burst) {
        enqueue_typed(typed_control());
      }
      pause_rendering.store(false, std::memory_order_release);
      render_paused.store(false, std::memory_order_release);
    }
    while (rendered_quanta.load(std::memory_order_acquire) <= round) {
      std::this_thread::yield();
    }
  }
  renderer.join();

  // Drain whatever the pacing left queued, then compare the coherent final
  // Filter state BEFORE stop(): stop() resets both halves to the epoch's
  // neutral state, so a post-stop comparison cannot testify about the
  // pre-stop tuple.
  std::array<float, kFramesPerQuantum> left{};
  std::array<float, kFramesPerQuantum> right{};
  for (std::uint32_t quantum = 0;
       quantum < lmdj::audio::kRealtimeQueueCapacity / kFramesPerQuantum + 1 &&
       engine.master_fx_telemetry().queued_gestures != 0;
       ++quantum) {
    engine.render(left.data(), right.data(), left.size());
  }
  LMDJ_CHECK(engine.master_fx_telemetry().queued_gestures == 0);
  const auto status = engine.filter_control_status();
  LMDJ_CHECK(status.applied.sequence == status.accepted_sequence);
  LMDJ_CHECK(status.applied.state.mode == status.accepted.mode);
  LMDJ_CHECK(status.applied.state.engaged == status.accepted.engaged);
  LMDJ_CHECK(status.applied.state.frozen == status.accepted.frozen);
  LMDJ_CHECK(status.applied.state.hold == status.accepted.hold);
  LMDJ_CHECK(status.applied.state.legacy_value == status.accepted.legacy_value);
  LMDJ_CHECK(status.applied.state.parameters.type ==
             status.accepted.parameters.type);
  LMDJ_CHECK(status.applied.state.parameters.cutoff_hz ==
             status.accepted.parameters.cutoff_hz);
  LMDJ_CHECK(status.applied.state.parameters.resonance_milli ==
             status.accepted.parameters.resonance_milli);
  engine.stop();

  const auto fx = engine.master_fx_telemetry();
  LMDJ_CHECK(!render_failed.load(std::memory_order_acquire));
  // The paused burst rejects exactly the burst minus the free space, and the
  // free space is at most the queue capacity: at least 76 rejections.
  LMDJ_CHECK(rejected_full >= 76);
  LMDJ_CHECK(accepted_typed > 0);
  LMDJ_CHECK(fx.enqueued_filter_controls == accepted_typed);
  LMDJ_CHECK(fx.dequeued_filter_controls == accepted_typed);
  LMDJ_CHECK(fx.queued_gestures == 0);
  // stop() is documented to return both halves to the epoch-stamped neutral
  // state; pin that this teardown actually happened.
  const auto stopped = engine.filter_control_status();
  LMDJ_CHECK(stopped.accepted_sequence == 0);
  LMDJ_CHECK(stopped.applied.sequence == 0);
  LMDJ_CHECK(stopped.applied.epoch == engine.telemetry().start_epoch);
  LMDJ_CHECK(stopped.applied.state.mode == FilterMode::independent);
  LMDJ_CHECK(!stopped.applied.state.engaged &&
             !stopped.applied.state.frozen);
  LMDJ_CHECK(stopped.applied.state.parameters.type == FilterType::low_pass);
  LMDJ_CHECK(stopped.applied.state.parameters.cutoff_hz == 20'000);
  LMDJ_CHECK(stopped.applied.state.parameters.resonance_milli == 0);
}

void filter_ack_epoch_distinguishes_engine_restarts() {
  RealtimeEngine engine;
  LMDJ_CHECK(engine.prepare_master_fx(173).has_value());
  LMDJ_CHECK(engine.start().has_value());
  const auto first_epoch = engine.telemetry().start_epoch;
  LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                 FilterPhase::engage, {FilterType::high_pass, 4'000, 500}}) ==
             FxEnqueueResult::accepted);
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  engine.render(left.data(), right.data(), left.size());
  const auto first = engine.filter_control_status();
  LMDJ_CHECK(first.applied.sequence == 1);
  LMDJ_CHECK(first.applied.epoch == first_epoch);
  LMDJ_CHECK(first.applied.state.engaged);
  LMDJ_CHECK(first.applied.state.parameters.type == FilterType::high_pass);
  LMDJ_CHECK(first.applied.state.parameters.cutoff_hz == 4'000);

  engine.stop();
  LMDJ_CHECK(engine.start().has_value());
  const auto second_epoch = engine.telemetry().start_epoch;
  LMDJ_CHECK(second_epoch == first_epoch + 1);
  // The new epoch starts independent OFF with the approved defaults; the old
  // epoch's applied state cannot masquerade as current.
  const auto restarted = engine.filter_control_status();
  LMDJ_CHECK(restarted.accepted_sequence == 0);
  LMDJ_CHECK(restarted.applied.sequence == 0);
  LMDJ_CHECK(restarted.applied.epoch == second_epoch);
  LMDJ_CHECK(restarted.applied.state.mode == FilterMode::independent);
  LMDJ_CHECK(!restarted.applied.state.engaged);
  LMDJ_CHECK(!restarted.applied.state.frozen);
  LMDJ_CHECK(restarted.applied.state.parameters.type ==
             FilterType::low_pass);
  LMDJ_CHECK(restarted.applied.state.parameters.cutoff_hz == 20'000);
  LMDJ_CHECK(restarted.applied.state.parameters.resonance_milli == 0);

  LMDJ_CHECK(engine.enqueue_filter_gesture(FilterGesture{
                 FilterPhase::engage, {FilterType::low_pass, 100, 1'000}}) ==
             FxEnqueueResult::accepted);
  engine.render(left.data(), right.data(), left.size());
  const auto second = engine.filter_control_status();
  LMDJ_CHECK(second.applied.sequence == 1);
  LMDJ_CHECK(second.applied.epoch == second_epoch);
  LMDJ_CHECK(second.applied.state.parameters.type == FilterType::low_pass);
  LMDJ_CHECK(second.applied.state.parameters.cutoff_hz == 100);
  LMDJ_CHECK(second.applied.state.parameters.resonance_milli == 1'000);
  engine.stop();
}

}  // namespace

int main() {
  try {
    sampler_work_is_outside_render_clock();
    render_deadline_and_accounting_are_strict();
    all_eight_effects_sustain_maximum_gesture_rate_without_underruns();
    full_voice_pool_with_every_kernel_stage_holds_the_deadline();
    full_voice_pool_with_every_tone_stage_holds_the_deadline();
    typed_filter_queue_full_rejects_without_touching_accepted_state();
    independent_filter_churn_stays_finite_bounded_and_coherent();
    filter_ack_epoch_distinguishes_engine_restarts();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
