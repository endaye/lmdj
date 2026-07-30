#pragma once

#include <cstddef>
#include <functional>
#include <memory>
#include <vector>

#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::cooker {

using ArtifactResolver = std::function<
    foundation::Result<std::vector<std::byte>>(
        const foundation::ArtifactRef&)>;

foundation::Result<std::shared_ptr<const RuntimeSnapshot>> cook(
    const domain::ProjectState& project,
    foundation::PatternId pattern_id,
    ArtifactResolver resolve);

}  // namespace lmdj::cooker
