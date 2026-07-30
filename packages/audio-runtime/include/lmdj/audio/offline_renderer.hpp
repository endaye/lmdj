#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>

#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::audio {

struct OfflineRenderRequest {
  std::shared_ptr<const cooker::RuntimeSnapshot> snapshot;
  std::filesystem::path output_path;
};

struct OfflineRenderResult {
  foundation::ArtifactRef artifact;
  std::uint64_t frame_count;
  std::uint32_t sample_rate;
  std::uint16_t channels;
};

foundation::Result<OfflineRenderResult> render_offline(
    const OfflineRenderRequest& request);

}  // namespace lmdj::audio
