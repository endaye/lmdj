#pragma once

#include <cmath>
#include <complex>
#include <cstddef>
#include <numbers>
#include <utility>
#include <vector>

namespace lmdj::analysis {

// In-place iterative radix-2 FFT. values.size() must be a power of two.
inline void fft(std::vector<std::complex<float>>& values) {
  const std::size_t n = values.size();
  for (std::size_t i = 1, j = 0; i < n; ++i) {
    std::size_t bit = n >> 1U;
    for (; (j & bit) != 0U; bit >>= 1U) {
      j ^= bit;
    }
    j ^= bit;
    if (i < j) {
      std::swap(values[i], values[j]);
    }
  }
  for (std::size_t length = 2; length <= n; length <<= 1U) {
    const float angle =
        -2.0F * std::numbers::pi_v<float> / static_cast<float>(length);
    const std::complex<float> step(std::cos(angle), std::sin(angle));
    for (std::size_t i = 0; i < n; i += length) {
      std::complex<float> factor(1.0F, 0.0F);
      for (std::size_t j = 0; j < length / 2; ++j) {
        const auto even = values[i + j];
        const auto odd = values[i + j + length / 2] * factor;
        values[i + j] = even + odd;
        values[i + j + length / 2] = even - odd;
        factor *= step;
      }
    }
  }
}

}  // namespace lmdj::analysis
