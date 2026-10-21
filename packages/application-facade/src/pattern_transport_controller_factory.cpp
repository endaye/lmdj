#include <lmdj/facade/pattern_transport_controller.hpp>

#include <utility>

#include <lmdj/facade/pattern_transport_controller_factory.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "pattern_transport_controller.hpp"
#include "pattern_transport_io_owner.hpp"

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
  bool supports_receipt_bound_opening() const override {
    return port_.supports_receipt_bound_opening();
  }
  std::optional<audio::PatternTransportObservation> observe_transport()
      const override {
    return port_.observe_transport();
  }
  std::optional<foundation::PatternId> current_pattern() const override {
    return port_.current_pattern();
  }
  foundation::Result<audio::PatternPublication> publish_overlay(
      const foundation::PatternId& pattern,
      std::span<const domain::PatternEvent> events) override {
    return port_.publish_overlay(pattern, events);
  }
  bool cancel_overlay(
      const audio::PatternReplacementAuthority& authority) override {
    return port_.cancel_overlay(authority);
  }

 private:
  lmdj::facade::PatternTransportAudioPort& port_;
};

}  // namespace

struct PatternTransportController::Impl {
  struct RegistryRetirement {
    std::function<void()> callback;
    ~RegistryRetirement() { try { if (callback) callback(); } catch (...) {} }
  };
  Impl(PatternTransportAudioPort& audio, PatternTransportControllerConfig config,
       std::shared_ptr<project_io::ProjectStoragePlatform> platform,
       std::shared_ptr<project_io::AuthoringHistory> history,
       std::function<void()> on_destroy,
       ScheduledPatternTransportAudioPort* scheduled, std::function<bool()> can_request)
      : retirement{std::move(on_destroy)}, can_request(std::move(can_request)), bridge(audio),
        opening(std::make_shared<detail::PatternTransportOpeningPublication>()),
        executor(config.runtime_generation,
            [config, platform = std::move(platform), history = std::move(history), opening = opening] {
              return std::make_unique<detail::PatternTransportIoOwner>(config, platform, history, opening);
            }),
        coordinator(bridge, executor, std::move(config), scheduled, opening) {}
  ~Impl() {
    executor.request_shutdown();
  }

  // Declaration order is ownership order: the coordinator references the
  // bridge and executor, so both outlive it within the Impl.
  // Retire only after the executor has destroyed its owner, including failed startup.
  RegistryRetirement retirement;
  std::shared_ptr<int> observer_lifetime = std::make_shared<int>(0);
  std::function<bool()> can_request;
  AudioPortBridge bridge;
  std::shared_ptr<detail::PatternTransportOpeningPublication> opening;
  PatternTransportExecutor executor;
  detail::PatternTransportCoordinator coordinator;

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
  if (impl_->can_request && !impl_->can_request()) return PatternTransportSubmit::busy;
  return impl_->coordinator.request(request);
}

bool PatternTransportController::retains_command_id(
    const foundation::CommandId& command_id) const {
  return impl_->coordinator.retains_command_id(command_id);
}

PatternTransportStatus PatternTransportController::inspect() const {
  return impl_->coordinator.inspect();
}

foundation::Result<void> PatternTransportController::continue_operation() {
  return impl_->coordinator.continue_operation();
}

foundation::Result<void> PatternTransportController::publish_overlay() {
  return impl_->coordinator.publish_overlay();
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

foundation::Result<std::optional<PatternTransportOverlay>>
PatternTransportController::project_overlay() {
  auto projected = impl_->coordinator.project_overlay();
  if (!projected.has_value()) {
    return foundation::Result<std::optional<PatternTransportOverlay>>::failure(
        projected.error());
  }
  if (!projected.value().has_value()) {
    return foundation::Result<std::optional<PatternTransportOverlay>>::success(
        std::nullopt);
  }
  return foundation::Result<std::optional<PatternTransportOverlay>>::success(
      PatternTransportOverlay{std::move(projected.value()->pattern_id),
                              projected.value()->generation,
                              std::move(projected.value()->events)});
}

std::unique_ptr<PatternTransportController>
detail::PatternTransportControllerInternalFactory::make(
    lmdj::facade::PatternTransportAudioPort& audio,
    PatternTransportControllerConfig config,
    std::shared_ptr<project_io::ProjectStoragePlatform> platform,
    std::shared_ptr<project_io::AuthoringHistory> history,
    std::function<void()> on_destroy,
    ScheduledPatternTransportAudioPort* scheduled,
    std::function<bool()> can_request) {
  return std::unique_ptr<PatternTransportController>(
      new PatternTransportController(
          std::unique_ptr<PatternTransportController::Impl>(
              new PatternTransportController::Impl(
                  audio, std::move(config), std::move(platform),
                  std::move(history), std::move(on_destroy), scheduled, std::move(can_request)))));
}

std::function<bool()> detail::PatternTransportControllerInternalFactory::tempo_conflict_observer(
    const PatternTransportController& controller) {
  auto* impl = controller.impl_.get();
  return [weak = std::weak_ptr<int>(impl->observer_lifetime), impl] {
    if (!weak.lock()) return false;
    const auto current = impl->coordinator.inspect();
    const auto count_in = impl->coordinator.inspect_count_in();
    return current.recording || current.phase != PatternTransportPhase::idle ||
        (count_in.request && !count_in.start_receipt && !count_in.cancel_receipt) ||
        impl->executor.inspect().ticket.has_value();
  };
}

std::unique_ptr<PatternTransportController> make_pattern_transport_controller(
    PatternTransportAudioPort& audio, PatternTransportControllerConfig config) {
  return detail::PatternTransportControllerInternalFactory::make(
      audio, std::move(config), nullptr);
}

std::unique_ptr<PatternTransportController> make_pattern_transport_controller(
    PatternTransportAudioPort& audio, ScheduledPatternTransportAudioPort& scheduled,
    PatternTransportControllerConfig config) {
  return detail::PatternTransportControllerInternalFactory::make(audio, std::move(config), nullptr, {}, {}, &scheduled);
}
PatternTransportSubmit PatternTransportController::request_count_in(const ScheduledPatternTransportRequest& r) {
  if (impl_->can_request && !impl_->can_request()) return PatternTransportSubmit::busy;
  return impl_->coordinator.request_count_in(r);
}
ScheduledPatternTransportStatus PatternTransportController::inspect_count_in() const { return impl_->coordinator.inspect_count_in(); }
PatternTransportSubmit PatternTransportController::cancel_count_in(const ScheduledPatternTransportCancel& r) { return impl_->coordinator.cancel_count_in(r); }
foundation::Result<PatternTransportInputTicket> PatternTransportController::reserve_input(const PatternTransportInputRequest& r) { return impl_->coordinator.reserve_input(r); }
bool PatternTransportController::bind_input(const PatternTransportInputTicket& t, const audio::PatternInputAdmission& a) { return impl_->coordinator.bind_input(t, a); }
bool PatternTransportController::complete_input(const audio::PatternInputCompletion& c) { return impl_->coordinator.complete_input(c); }
std::optional<PatternTransportInputStatus> PatternTransportController::inspect_input(const PatternTransportInputTicket& t) const { return impl_->coordinator.inspect_input(t); }
bool PatternTransportController::consume_input(const PatternTransportInputTicket& t) { return impl_->coordinator.consume_input(t); }
bool PatternTransportController::abandon_input(const PatternTransportInputTicket& t) { return impl_->coordinator.abandon_input(t); }
PatternTransportIngressStatus PatternTransportController::inspect_ingress() const { return impl_->coordinator.inspect_ingress(); }
PatternTransportInputOwnerStatus PatternTransportController::inspect_input_owner() const { return impl_->coordinator.inspect_input_owner(); }
bool PatternTransportController::request_input_owner_disposition(std::uint64_t generation) { return impl_->coordinator.request_input_owner_disposition(generation); }
bool PatternTransportController::acknowledge_input_owner(std::uint64_t generation) { return impl_->coordinator.acknowledge_input_owner(generation); }
void PatternTransportController::request_shutdown() { impl_->coordinator.request_shutdown(); }
bool PatternTransportController::shutdown_complete() const { return impl_->coordinator.shutdown_complete(); }
PatternTransportExecutorStatus PatternTransportController::inspect_io() const { return impl_->coordinator.inspect_io(); }
foundation::Result<PatternTransportSwitchTicket> PatternTransportController::reserve_pattern_switch(const PatternTransportSwitchRequest& r) {
  if (impl_->can_request && !impl_->can_request())
    return foundation::Result<PatternTransportSwitchTicket>::failure({
        foundation::ErrorCode::invalid_argument, "Pattern tempo preview must settle before switching",
        {{"reason", "tempo_preview_active"}}});
  return impl_->coordinator.reserve_pattern_switch(r);
}
bool PatternTransportController::bind_pattern_switch(const PatternTransportSwitchTicket& t, const audio::PatternReplacementAuthority& a, std::uint16_t bpm) { return impl_->coordinator.bind_pattern_switch(t, a, bpm); }
bool PatternTransportController::complete_pattern_switch(const PatternTransportSwitchTicket& t, const audio::PatternPublicationObservation& o) { return impl_->coordinator.complete_pattern_switch(t, o); }
std::optional<PatternTransportSwitchStatus> PatternTransportController::inspect_pattern_switch(const PatternTransportSwitchTicket& t) const { return impl_->coordinator.inspect_pattern_switch(t); }
bool PatternTransportController::consume_pattern_switch(const PatternTransportSwitchTicket& t) { return impl_->coordinator.consume_pattern_switch(t); }
bool PatternTransportController::abandon_pattern_switch(const PatternTransportSwitchTicket& t) { return impl_->coordinator.abandon_pattern_switch(t); }

}  // namespace lmdj::facade
