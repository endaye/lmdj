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

// Resolves a Pad's playback, including its voice DSP block, for a source of
// `source_rate` Hz holding `source_frames` frames, exactly as cook() does but
// without reading PCM. Hosts that only hold WAV metadata use it to preview.
foundation::Result<ResolvedPlayback> resolve_pad_playback(
    const domain::PadPlayback& playback,
    std::uint32_t source_rate,
    std::uint64_t source_frames);

foundation::Result<std::shared_ptr<const RuntimeSnapshot>> cook(
    const domain::ProjectState& project,
    foundation::PatternId pattern_id,
    ArtifactResolver resolve);

}  // namespace lmdj::cooker
