#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

#include <lmdj/foundation/error.hpp>

namespace lmdj::cooker {

foundation::Result<std::vector<std::byte>> select_pcm16_stereo_wav(
    std::span<const std::byte> source,
    std::uint64_t start_frame,
    std::uint64_t end_frame);

}  // namespace lmdj::cooker
