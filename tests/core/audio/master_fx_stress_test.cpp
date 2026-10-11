#include <lmdj/audio/master_fx.hpp>
#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <exception>
#include <fstream>
#include <iostream>
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
};

[[maybe_unused]] HostAccounting parse_stat_counters(
    const std::string& line, std::size_t skip) {
  HostAccounting counters;
  unsigned long long user = 0;
  unsigned long long nice = 0;
  unsigned long long system = 0;
  unsigned long long idle = 0;
  unsigned long long iowait = 0;
  unsigned long long irq = 0;
  unsigned long long softirq = 0;
  unsigned long long steal = 0;
  if (std::sscanf(line.c_str() + skip, "%llu %llu %llu %llu %llu %llu %llu %llu",
                  &user, &nice, &system, &idle, &iowait, &irq, &softirq,
                  &steal) == 8) {
    counters.irq_ticks = irq;
    counters.softirq_ticks = softirq;
    counters.steal_ticks = steal;
  }
  return counters;
}

HostAccountingSample host_accounting_sample() {
  HostAccountingSample sample;
#if defined(__linux__)
  sample.cpu = sched_getcpu();
  const std::string wanted =
      sample.cpu >= 0 ? "cpu" + std::to_string(sample.cpu) : std::string();
  std::ifstream stat("/proc/stat");
  std::string line;
  while (std::getline(stat, line)) {
    // The trailing space in the prefix makes "cpu1 " unable to match the
    // "cpu10 "/"cpu1x" lines of higher-numbered CPUs.
    if (!wanted.empty() && line.rfind(wanted + " ", 0) == 0) {
      sample.per_cpu = parse_stat_counters(line, wanted.size() + 1);
      break;
    }
  }
#endif
  return sample;
}

HostAccounting host_accounting_delta(
    const HostAccountingSample& before, const HostAccountingSample& after) {
  // Attribution is per-vCPU or nothing: it is precise only when the render
  // thread stayed on one vCPU across the ~36 us window. A mid-window
  // migration (or an unreadable CPU) cannot say which vCPU took the event,
  // so the overrun is counted, fail-closed — never excused by accounting
  // activity on a CPU the thread may not have touched.
  if (before.cpu < 0 || before.cpu != after.cpu) {
    return {};
  }
  HostAccounting delta;
  delta.steal_ticks = after.per_cpu.steal_ticks - before.per_cpu.steal_ticks;
  delta.irq_ticks = after.per_cpu.irq_ticks - before.per_cpu.irq_ticks;
  delta.softirq_ticks =
      after.per_cpu.softirq_ticks - before.per_cpu.softirq_ticks;
  return delta;
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
      const auto started = kVerifyRealtimeDeadline
                               ? current_thread_cpu_time()
                               : std::chrono::nanoseconds::zero();
      const auto host_before =
          kVerifyRealtimeDeadline ? host_accounting_sample()
                                  : HostAccountingSample{};
      engine.render(left.data(), right.data(), left.size());
      const auto elapsed = kVerifyRealtimeDeadline
                               ? current_thread_cpu_time() - started
                               : std::chrono::nanoseconds::zero();
      if (kVerifyRealtimeDeadline) {
        const auto host_after = host_accounting_sample();
        const auto observed_ns = static_cast<std::uint64_t>(elapsed.count());
        if (elapsed > kCallbackDeadline) {
          const auto attribution =
              host_accounting_delta(host_before, host_after);
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
    const auto started = verify_deadline ? current_thread_cpu_time()
                                         : std::chrono::nanoseconds::zero();
    const auto host_before =
        verify_deadline ? host_accounting_sample() : HostAccountingSample{};
    engine.render(left.data(), right.data(), left.size());
    if (verify_deadline) {
      const auto elapsed = current_thread_cpu_time() - started;
      const auto host_after = host_accounting_sample();
      const auto observed_ns = static_cast<std::uint64_t>(elapsed.count());
      worst_ns = std::max(worst_ns, observed_ns);
      total_ns += observed_ns;
      if (elapsed > kCallbackDeadline) {
        if (host_accounting_delta(host_before, host_after).total() > 0) {
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
