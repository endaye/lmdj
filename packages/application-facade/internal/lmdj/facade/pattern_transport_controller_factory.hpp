#pragma once

#include <memory>

#include <lmdj/facade/pattern_transport_controller.hpp>

namespace lmdj::project_io {
class ProjectStoragePlatform;
}

namespace lmdj::facade::detail {

// Construction access for facade-internal callers that own a storage platform
// instance (Application). The controller's Journal/Store then share that
// instance's writer-lease registry instead of a fresh default one; nullptr
// selects the default platform. The bundle lock is per open file description,
// so a controller on a different instance than the Host's held writer lease
// fails its first admission write with `project_busy`.
class PatternTransportControllerInternalFactory {
 public:
  static std::unique_ptr<PatternTransportController> make(
      lmdj::facade::PatternTransportAudioPort& audio,
      PatternTransportControllerConfig config,
      std::shared_ptr<project_io::ProjectStoragePlatform> platform);
};

}  // namespace lmdj::facade::detail
