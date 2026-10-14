#pragma once

#include <chrono>
#include <memory>
#include <mutex>

#include <lmdj/facade/pattern_transport_controller.hpp>
#include <lmdj/project_io/authoring_history.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "pattern_admission_controller.hpp"

namespace lmdj::facade::detail {

// A private worker-to-control companion, not an executor completion. The full
// retained request includes its immutable fence and original opening clock.
struct PatternTransportOpeningEvidence {
  PatternTransportWorkRequest request;
  std::chrono::steady_clock::time_point completed_at;
};
struct PatternTransportOpeningPublication {
  std::mutex guard;
  std::shared_ptr<const PatternTransportOpeningEvidence> successful;
};
// All allocations, payload copies and const aliases are prepared before the
// durable fence write. Swapped-out evidence is destroyed after guard unlock.
struct PatternTransportOpeningCommit {
  PatternTransportOpeningPublication& publication;
  std::shared_ptr<PatternTransportOpeningEvidence> pending_transport;
  std::shared_ptr<const PatternTransportOpeningEvidence> sealed_transport;
  std::shared_ptr<PatternAdmissionOpeningEvidence> pending_owner;
  PatternTransportOpeningCommit(PatternTransportOpeningPublication& destination,
      const PatternTransportWorkRequest& request,
      const project_io::SequenceAdmissionFence& fence)
      : publication(destination),
        pending_transport(std::make_shared<PatternTransportOpeningEvidence>(
            PatternTransportOpeningEvidence{request, {}})),
        sealed_transport(pending_transport),
        pending_owner(std::make_shared<PatternAdmissionOpeningEvidence>(
            PatternAdmissionOpeningEvidence{fence, {}})) {}
};

// Only immutable binding, platform identity and shared history cross into the
// factory. Store, Journal, admission owner and all leases are worker-owned.
class PatternTransportIoOwner final : public PatternTransportWorkOwner, public PatternTransportWorkReconciler {
 public:
  PatternTransportIoOwner(PatternTransportControllerConfig config,
      std::shared_ptr<project_io::ProjectStoragePlatform> platform,
      std::shared_ptr<project_io::AuthoringHistory> history,
      std::shared_ptr<PatternTransportOpeningPublication> opening = {});
  PatternTransportWorkCompletion execute(const PatternTransportWorkRequest&) override;
  PatternTransportWorkCompletion reconcile(const PatternTransportWorkRequest&) override;
 private:
  foundation::Result<nlohmann::json> perform(const PatternTransportWorkRequest&,
                                            const nlohmann::json&);
  PatternTransportControllerConfig config_;
  project_io::SequenceJournal journals_;
  project_io::ProjectStore store_;
  PatternAdmissionOwner owner_;
  std::shared_ptr<PatternTransportOpeningPublication> opening_;
  std::optional<foundation::Error> uncertain_error_;
  std::optional<foundation::PatternId> projection_pattern_;
  std::vector<domain::PatternEvent> projection_events_;
};

nlohmann::json encode_transport_fence(const project_io::SequenceAdmissionFence&);
std::int64_t transport_clock_stamp(std::chrono::steady_clock::time_point);

}  // namespace lmdj::facade::detail
