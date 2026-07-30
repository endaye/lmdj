#pragma once

#include <cstddef>
#include <memory>
#include <span>

#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::cooker {

foundation::Result<std::shared_ptr<const PcmSample>> decode_wav(
    std::span<const std::byte> bytes);

}  // namespace lmdj::cooker
