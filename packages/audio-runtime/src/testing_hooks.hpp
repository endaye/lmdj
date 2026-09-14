#pragma once

#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING

#include <atomic>
#include <cstddef>

namespace lmdj::audio {
namespace testing {

struct PatternClaimHook {
  void* context;
  void (*invoke)(void*) noexcept;
};
static_assert(std::atomic<PatternClaimHook*>::is_always_lock_free);

void set_pattern_claim_hook(PatternClaimHook* hook) noexcept;
void invoke_pattern_claim_hook() noexcept;
void set_pattern_apply_hook(PatternClaimHook* hook) noexcept;
void invoke_pattern_apply_hook() noexcept;

enum class RealtimeHookPoint : std::size_t {
  host_input_reserved,
  host_input_popped,
  fx_reserved,
  fx_popped,
  bank_mask_written,
  bank_applied_before_pending_release,
  before_pattern_claim,
  pattern_admission_closed,
  control_pattern_admission_retry,
  observation_read,
  capture_event_published,
  capture_idle_published,
  capture_observe_state,
  count,
};
void set_realtime_hook(RealtimeHookPoint point, PatternClaimHook* hook) noexcept;
void invoke_realtime_hook(RealtimeHookPoint point) noexcept;

}  // namespace testing

}  // namespace lmdj::audio

#endif
