#pragma once

#include <functional>
#include <memory>

#include <lmdj/facade/pattern_transport_controller.hpp>

namespace lmdj::project_io {
class ProjectStoragePlatform;
class AuthoringHistory;
}

namespace lmdj::facade::detail {

// Construction access for facade-internal callers that own a storage platform
// instance (Application). The controller's Journal/Store then share that
// instance's writer-lease registry instead of a fresh default one; nullptr
// selects the default platform. The bundle lock is per open file description,
// so a controller on a different instance than the Host's held writer lease
// fails its first admission write with `project_busy`. `on_destroy` runs at
// controller destruction; the vending owner uses it to retire the session's
// ownership registration, so a destroyed controller no longer shields its
// journal from owner-loss reconciliation.
class PatternTransportControllerInternalFactory {
 public:
  // Observes the stable pimpl, so moving its public wrapper cannot leave the
  // Application's control-owner registry pointing at a moved-from object.
  static std::function<bool()> tempo_conflict_observer(const PatternTransportController&);
  static std::unique_ptr<PatternTransportController> make(
      lmdj::facade::PatternTransportAudioPort& audio,
      PatternTransportControllerConfig config,
      std::shared_ptr<project_io::ProjectStoragePlatform> platform,
      std::shared_ptr<project_io::AuthoringHistory> history = {},
      std::function<void()> on_destroy = {},
      ScheduledPatternTransportAudioPort* scheduled = nullptr,
      std::function<bool()> can_request = {});
};

}  // namespace lmdj::facade::detail
