#pragma once

#include <cstdint>
#include <stdexcept>

namespace lmdj::test {

class DeterministicRng {
 public:
  explicit DeterministicRng(std::uint64_t seed)
      : seed_(seed),
        state_(seed == 0 ? kZeroSeedState : seed) {}

  std::uint64_t next_u64() {
    state_ ^= state_ >> 12U;
    state_ ^= state_ << 25U;
    state_ ^= state_ >> 27U;
    return state_ * kMultiplier;
  }

  std::uint64_t bounded(std::uint64_t upper_exclusive) {
    if (upper_exclusive == 0) {
      throw std::invalid_argument(
          "DeterministicRng bounded range must be nonzero");
    }
    return next_u64() % upper_exclusive;
  }

  std::uint64_t seed() const noexcept { return seed_; }

 private:
  // xorshift64* requires nonzero state; seed 0 maps to this fixed state.
  static constexpr std::uint64_t kZeroSeedState =
      0x9e3779b97f4a7c15ULL;
  static constexpr std::uint64_t kMultiplier =
      2685821657736338717ULL;

  std::uint64_t seed_;
  std::uint64_t state_;
};

}  // namespace lmdj::test
