#pragma once

namespace lmdj::audio::testing {

struct PatternClaimHook {
  void* context;
  void (*invoke)(void*) noexcept;
};

void set_pattern_claim_hook(PatternClaimHook* hook) noexcept;
void invoke_pattern_claim_hook() noexcept;

}  // namespace lmdj::audio::testing
