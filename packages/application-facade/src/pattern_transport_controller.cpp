#include "pattern_transport_controller.hpp"

#include <cstddef>
#include <lmdj/domain/project.hpp>
#include <utility>

namespace lmdj::facade::detail {
namespace {

project_io::SequenceSwitchOutcome switch_outcome(
    audio::PatternCutoffDecision decision) {
  using audio::PatternCutoffDecision;
  using project_io::SequenceSwitchOutcome;
  switch (decision) {
    case PatternCutoffDecision::applied_before_cutoff:
      return SequenceSwitchOutcome::applied_before_cutoff;
    case PatternCutoffDecision::canceled_at_cutoff:
      return SequenceSwitchOutcome::canceled_at_cutoff;
    default:
      return SequenceSwitchOutcome::none;
  }
}

foundation::CommandId derive_command(
    const foundation::CommandId& command, std::size_t offset, char tag) {
  auto value = command.value();
  const auto dash = value.rfind('-');
  if (dash != std::string::npos && dash + 1 + offset < value.size()) {
    auto& digit = value[dash + 1 + offset];
    digit = digit == tag ? (tag == 'f' ? 'e' : 'f') : tag;
  }
  return foundation::CommandId{value};
}

}  // namespace

PatternTransportCoordinator::PatternTransportCoordinator(
    PatternTransportAudioPort& audio, project_io::SequenceJournal& journals,
    project_io::ProjectStore& store, std::filesystem::path bundle,
    foundation::SequenceSessionId session, foundation::ProjectId project,
    foundation::PatternId pattern, std::uint64_t runtime_generation)
    : audio_(audio), owner_(journals, std::move(bundle), session), store_(store),
      session_(session), project_(std::move(project)),
      pattern_(std::move(pattern)), runtime_generation_(runtime_generation),
      last_pattern_generation_(audio.pattern_generation()) {}

audio::PatternTransportAction PatternTransportCoordinator::audio_action(
    PatternTransportIntent intent) const {
  if (intent == PatternTransportIntent::play_stop) {
    return playing_ ? audio::PatternTransportAction::stop
                    : audio::PatternTransportAction::start;
  }
  // Playing Record and Record-off both fence so origin is unchanged.
  if (playing_) return audio::PatternTransportAction::fence;
  return audio::PatternTransportAction::start;
}

project_io::SequenceAdmissionFence PatternTransportCoordinator::fence_from(
    const audio::PatternTransportReceipt& receipt,
    project_io::SequenceFenceKind kind,
    const foundation::CommandId& command_id) const {
  return {kind, command_id, receipt.epoch, receipt.effective_frame,
          receipt.origin_frame, receipt.pattern_id, receipt.pattern_generation,
          receipt.bpm, receipt.playing,
          receipt.switch_authority
              ? std::optional<project_io::SequencePublicationAuthority>{{
                    receipt.switch_authority->pattern_id,
                    receipt.switch_authority->generation,
                    receipt.switch_authority->activation_frame}}
              : std::nullopt,
          switch_outcome(receipt.switch_decision), receipt.switch_applied_frame};
}

PatternTransportSubmit PatternTransportCoordinator::request(
    const PatternTransportRequest& request) {
  if (request.runtime_generation != runtime_generation_ ||
      !domain::is_valid_uuid(request.command_id.value())) {
    return PatternTransportSubmit::stale;
  }
  if (request.session != session_ || request.project_id != project_) {
    return PatternTransportSubmit::invalid;
  }
  if (pending_) {
    return *pending_ == request ? PatternTransportSubmit::replayed
                                : PatternTransportSubmit::busy;
  }
  if (const auto found = retained_.find(request.command_id);
      found != retained_.end()) {
    return found->second == request ? PatternTransportSubmit::replayed
                                    : PatternTransportSubmit::invalid;
  }
  if (phase_ != PatternTransportPhase::idle) return PatternTransportSubmit::busy;

  const auto opens_journal =
      request.intent == PatternTransportIntent::record && !recording_;
  if (opens_journal) {
    project_io::SequenceAdmissionPreparation preparation{
        {request.command_id, runtime_generation_, request.expected_epoch},
        project_, pattern_, audio_.pattern_generation(), 10};
    const auto prepared = owner_.prepare(preparation);
    if (!prepared.has_value()) {
      error_ = prepared.error();
      return PatternTransportSubmit::refused;
    }
  }

  audio::PatternTransportCommand command{
      runtime_generation_, request.expected_epoch, last_pattern_generation_,
      audio_action(request.intent), {}};
  if (playing_) command.pending_switch = audio_.pending_switch();
  if (!command.pending_switch) {
    command.expected_pattern_generation = audio_.pattern_generation();
  }
  const auto submitted = audio_.submit(command);
  if (submitted != audio::PatternTransportSubmit::accepted) {
    error_ = foundation::Error{foundation::ErrorCode::invalid_argument,
                               "Pattern transport audio submit refused"};
    return PatternTransportSubmit::refused;
  }
  pending_ = request;
  phase_ = PatternTransportPhase::awaiting_audio;
  return PatternTransportSubmit::accepted;
}

PatternTransportStatus PatternTransportCoordinator::inspect() const {
  return {playing_, recording_, phase_, runtime_generation_,
          pending_ ? pending_->expected_epoch
                   : (last_ ? last_->expected_epoch : 0),
          origin_frame_,
          pending_ ? std::optional{pending_->command_id}
                   : (last_ ? std::optional{last_->command_id} : std::nullopt),
          error_};
}

foundation::Result<void> PatternTransportCoordinator::apply_receipt(
    const audio::PatternTransportReceipt& receipt,
    const PatternTransportRequest& request) {
  const auto closing = recording_ &&
      (request.intent == PatternTransportIntent::play_stop ||
       (request.intent == PatternTransportIntent::record && playing_));
  const auto opening = request.intent == PatternTransportIntent::record &&
      !recording_;
  bool retained_switch = false;
  if (opening) {
    const auto activated = owner_.activate(fence_from(
        receipt, project_io::SequenceFenceKind::admission, request.command_id));
    if (!activated.has_value()) return activated;
    recording_ = true;
  }
  if (closing) {
    if (receipt.switch_decision ==
        audio::PatternCutoffDecision::applied_before_cutoff) {
      if (!receipt.switch_authority || !receipt.switch_applied_frame) {
        return foundation::Result<void>::failure(
            {foundation::ErrorCode::invalid_argument,
             "Pattern transport applied switch is missing authority"});
      }
      const project_io::SequencePublicationAuthority authority{
          receipt.switch_authority->pattern_id,
          receipt.switch_authority->generation, *receipt.switch_applied_frame};
      const auto retained = owner_.retain_switch(authority);
      if (!retained.has_value()) return retained;
      retained_switch = true;
    }
    const auto cut = owner_.cutoff(fence_from(
        receipt, project_io::SequenceFenceKind::cutoff, request.command_id));
    if (!cut.has_value()) return cut;
  }
  playing_ = receipt.playing;
  origin_frame_ = receipt.origin_frame;
  last_pattern_generation_ = receipt.pattern_generation;
  if (!audio_.acknowledge(receipt.runtime_generation, receipt.epoch)) {
    return foundation::Result<void>::failure(
        {foundation::ErrorCode::invalid_argument,
         "Pattern transport receipt was not acknowledged"});
  }
  if (closing) {
    // The flag is bound only after the cutoff fence and acknowledgment, so an
    // early return can never leave it set for a receipt that was not applied.
    close_applied_switch_ = retained_switch;
    close_pending_ = true;
    return finish_close();
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> PatternTransportCoordinator::finish_close() {
  if (pending_) {
    const auto source = owner_.drain_source_prefix(
        store_, pending_->command_id, derive_command(pending_->command_id, 0, 'f'));
    if (!source.has_value()) return source;
  }
  const auto reconciled = owner_.reconcile_switch(store_);
  if (!reconciled.has_value()) return reconciled;
  if (pending_) {
    const auto target = owner_.drain_target_segment(
        store_, derive_command(pending_->command_id, 1, 'a'),
        derive_command(pending_->command_id, 2, 'b'),
        derive_command(pending_->command_id, 3, 'c'));
    if (!target.has_value()) return target;
  }
  const auto closed = owner_.close_requested();
  if (!closed.has_value()) return closed;
  // A close without an applied switch settles the admission with a terminal
  // transfer once closure is durable; the applied-switch close is unchanged.
  if (pending_ && !close_applied_switch_) {
    const auto terminal = owner_.drain(
        derive_command(pending_->command_id, 4, 'd'), 0, true);
    if (!terminal.has_value()) {
      return foundation::Result<void>::failure(terminal.error());
    }
  }
  recording_ = false;
  close_pending_ = false;
  close_applied_switch_ = false;
  return foundation::Result<void>::success();
}

foundation::Result<PatternAdmissionAdmit> PatternTransportCoordinator::admit(
    const project_io::SequenceAdmissionCandidate& candidate) {
  if (!recording_) {
    return foundation::Result<PatternAdmissionAdmit>::failure(
        {foundation::ErrorCode::invalid_argument,
         "Pattern transport admission requires recording"});
  }
  // Once the cutoff receipt is applied the candidate set is frozen: input
  // landing while the close is unresolved stays live-only, so the settlement
  // drain always sees the same retained prefix.
  if (close_pending_) {
    return foundation::Result<PatternAdmissionAdmit>::success(
        PatternAdmissionAdmit::live_only);
  }
  return owner_.admit(candidate);
}

foundation::Result<void> PatternTransportCoordinator::continue_operation() {
  if (close_pending_ && pending_) {
    const auto closed = finish_close();
    if (!closed.has_value()) {
      error_ = closed.error();
      phase_ = PatternTransportPhase::flushing;
      return closed;
    }
    error_.reset();
    retained_.insert_or_assign(pending_->command_id, *pending_);
    last_ = pending_;
    pending_.reset();
    phase_ = PatternTransportPhase::idle;
    return foundation::Result<void>::success();
  }
  if (!pending_ || phase_ != PatternTransportPhase::awaiting_audio) {
    return foundation::Result<void>::success();
  }
  const auto receipt = audio_.inspect(
      pending_->runtime_generation, pending_->expected_epoch);
  if (!receipt.has_value()) return foundation::Result<void>::success();
  const auto applied = apply_receipt(*receipt, *pending_);
  if (!applied.has_value()) {
    error_ = applied.error();
    phase_ = close_pending_ ? PatternTransportPhase::flushing
                            : PatternTransportPhase::awaiting_audio;
    return applied;
  }
  retained_.insert_or_assign(pending_->command_id, *pending_);
  last_ = pending_;
  pending_.reset();
  phase_ = PatternTransportPhase::idle;
  return foundation::Result<void>::success();
}

}  // namespace lmdj::facade::detail
