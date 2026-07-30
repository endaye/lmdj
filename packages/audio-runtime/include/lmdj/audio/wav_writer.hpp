#pragma once

#include <cstdint>
#include <filesystem>
#include <span>

#include <lmdj/foundation/error.hpp>

namespace lmdj::audio::detail {

foundation::Result<void> write_pcm16_stereo_wav(
    const std::filesystem::path& path,
    std::uint32_t sample_rate,
    std::span<const std::int16_t> interleaved);

}  // namespace lmdj::audio::detail
