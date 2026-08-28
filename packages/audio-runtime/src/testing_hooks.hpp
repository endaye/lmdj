#pragma once

#if defined(LMDJ_AUDIO_RUNTIME_TESTING) && LMDJ_AUDIO_RUNTIME_TESTING

#include <atomic>

namespace lmdj::audio {
namespace testing {

struct PatternClaimHook {
  void* context;
  void (*invoke)(void*) noexcept;
};
static_assert(std::atomic<PatternClaimHook*>::is_always_lock_free);

void set_pattern_claim_hook(PatternClaimHook* hook) noexcept;
void invoke_pattern_claim_hook() noexcept;

}  // namespace testing

}  // namespace lmdj::audio

#endif
