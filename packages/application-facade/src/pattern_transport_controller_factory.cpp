#include <lmdj/facade/pattern_transport_controller.hpp>

#include <utility>

#include <lmdj/facade/pattern_transport_controller_factory.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "pattern_transport_controller.hpp"

namespace lmdj::facade {
namespace {

// Forwards the Host-facing public port onto the internal coordinator port.
// The two stay distinct so the public header never names a Project I/O type;
// this bridge is the only place both are visible.
class AudioPortBridge final : public detail::PatternTransportAudioPort {
 public:
  explicit AudioPortBridge(lmdj::facade::PatternTransportAudioPort& port)
      : port_(port) {}

  audio::PatternTransportSubmit submit(
      const audio::PatternTransportCommand& command) override {
    return port_.submit(command);
  }
  std::optional<audio::PatternTransportReceipt> inspect(
      std::uint64_t generation, std::uint64_t epoch) const override {
    return port_.inspect(generation, epoch);
  }
  bool acknowledge(std::uint64_t generation, std::uint64_t epoch) override {
    return port_.acknowledge(generation, epoch);
  }
  std::uint64_t pattern_generation() const override {
    return port_.pattern_generation();
  }
  std::optional<audio::PatternReplacementAuthority> pending_switch()
      const override {
    return port_.pending_switch();
  }

 private:
  lmdj::facade::PatternTransportAudioPort& port_;
};

}  // namespace

struct PatternTransportController::Impl {
  Impl(PatternTransportAudioPort& audio, PatternTransportControllerConfig config,
       std::shared_ptr<project_io::ProjectStoragePlatform> platform,
       std::function<void()> on_destroy)
      : bridge(audio),
        // A null platform default-constructs inside both collaborators, which
        // is exactly the free-function behavior; a caller-owned instance makes
        // the writer-lease registry shared.
        journals(platform),
        store(std::move(platform)),
        coordinator(bridge, journals, store, std::move(config.bundle),
                    config.session, std::move(config.project),
                    std::move(config.pattern), config.runtime_generation),
        on_destroy(std::move(on_destroy)) {}
  ~Impl() {
    // The callback contract is infallible (mutex + map erase); an exception
    // here must still never escape a destructor.
    try {
      if (on_destroy) {
        on_destroy();
      }
    } catch (...) {
    }
  }

  // Declaration order is ownership order: the coordinator references the
  // bridge, journals and store, so all three outlive it within the Impl.
  AudioPortBridge bridge;
  project_io::SequenceJournal journals;
  project_io::ProjectStore store;
  detail::PatternTransportCoordinator coordinator;
  std::function<void()> on_destroy;
};

PatternTransportController::PatternTransportController(
    std::unique_ptr<Impl> impl)
    : impl_(std::move(impl)) {}
PatternTransportController::~PatternTransportController() = default;
PatternTransportController::PatternTransportController(
    PatternTransportController&&) noexcept = default;
PatternTransportController& PatternTransportController::operator=(
    PatternTransportController&&) noexcept = default;

PatternTransportSubmit PatternTransportController::request(
    const PatternTransportRequest& request) {
  return impl_->coordinator.request(request);
}

PatternTransportStatus PatternTransportController::inspect() const {
  return impl_->coordinator.inspect();
}

foundation::Result<void> PatternTransportController::continue_operation() {
  return impl_->coordinator.continue_operation();
}

foundation::Result<PatternAdmissionAdmit> PatternTransportController::admit(
    const PatternTransportCandidate& candidate) {
  const project_io::SequenceAdmissionCandidate internal{
      candidate.watermark, candidate.runtime_frame, candidate.slot,
      candidate.pressed ? project_io::SequenceCandidateKind::press
                        : project_io::SequenceCandidateKind::release,
      candidate.velocity, candidate.correlation};
  const auto admitted = impl_->coordinator.admit(internal);
  if (!admitted.has_value()) {
    return foundation::Result<PatternAdmissionAdmit>::failure(
        admitted.error());
  }
  return foundation::Result<PatternAdmissionAdmit>::success(
      admitted.value() == detail::PatternAdmissionAdmit::retained
          ? PatternAdmissionAdmit::retained
          : PatternAdmissionAdmit::live_only);
}

std::unique_ptr<PatternTransportController>
detail::PatternTransportControllerInternalFactory::make(
    lmdj::facade::PatternTransportAudioPort& audio,
    PatternTransportControllerConfig config,
    std::shared_ptr<project_io::ProjectStoragePlatform> platform,
    std::function<void()> on_destroy) {
  return std::unique_ptr<PatternTransportController>(
      new PatternTransportController(
          std::unique_ptr<PatternTransportController::Impl>(
              new PatternTransportController::Impl(
                  audio, std::move(config), std::move(platform),
                  std::move(on_destroy)))));
}

std::unique_ptr<PatternTransportController> make_pattern_transport_controller(
    PatternTransportAudioPort& audio, PatternTransportControllerConfig config) {
  return detail::PatternTransportControllerInternalFactory::make(
      audio, std::move(config), nullptr);
}

}  // namespace lmdj::facade
