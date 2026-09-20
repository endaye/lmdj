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

// Admission authority/identity validation failures are deterministic: the same
// retained receipt can never apply on a retry. Anything else (journal IO,
// internal errors) may be transient and keeps its bounded retry phase.
bool terminal(const foundation::Error& error) {
  return error.code == foundation::ErrorCode::invalid_argument;
}

}  // namespace

PatternTransportCoordinator::PatternTransportCoordinator(
    PatternTransportAudioPort& audio, project_io::SequenceJournal& journals,
    project_io::ProjectStore& store, std::filesystem::path bundle,
    foundation::SequenceSessionId session, foundation::ProjectId project,
    foundation::PatternId pattern, std::uint64_t runtime_generation)
    : audio_(audio), journals_(journals), bundle_(bundle),
      owner_(journals, bundle, session), store_(store),
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
          receipt.origin_frame, receipt.pattern_id,
          receipt.pattern_generation,
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
  // A deterministic receipt failure poisons the engagement: the unacknowledged
  // receipt stays retained audio-side, so no later command can succeed. Refuse
  // honestly (the Host surfaces error_) instead of reporting a transient busy.
  if (phase_ == PatternTransportPhase::error) {
    return PatternTransportSubmit::refused;
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
    // The binding is vendored at construction, but the engine's current
    // Pattern can move behind the coordinator: a switch publication applying
    // at the Bar boundary while the transport keeps playing. Re-anchor the
    // binding on the engine's current identity before the journal and the
    // admission preparation name the stale one, or the admission fence (which
    // names the receipt's Pattern) fails authority validation deterministically
    // (#1403). A port reporting no current Pattern keeps the vendored binding,
    // and an active journal never retargets: the switch-spanning close
    // machinery (retain_switch/reconcile_switch/drain) owns that settlement.
    if (const auto current = audio_.current_pattern();
        current.has_value() && *current != pattern_) {
      pattern_ = *current;
    }
    // The journal is Facade-owned: a Record request lazily begins it when no
    // active journal exists, while playback alone never creates one.
    const auto active = journals_.read_active(bundle_);
    if (!active.has_value()) {
      if (active.error().code != foundation::ErrorCode::not_found) {
        error_ = active.error();
        return PatternTransportSubmit::refused;
      }
      const auto loaded = store_.load(bundle_);
      if (!loaded.has_value()) {
        error_ = loaded.error();
        return PatternTransportSubmit::refused;
      }
      if (request.expected_revision &&
          *request.expected_revision != loaded.value().revision) {
        error_ = foundation::Error{
            foundation::ErrorCode::revision_conflict,
            "Pattern transport record expected a different Project revision"};
        return PatternTransportSubmit::refused;
      }
      const auto found = loaded.value().patterns.find(pattern_);
      if (found == loaded.value().patterns.end()) {
        error_ = foundation::Error{
            foundation::ErrorCode::not_found,
            "Pattern transport record target Pattern is missing"};
        return PatternTransportSubmit::refused;
      }
      const auto begun = journals_.begin(
          bundle_, session_, pattern_, found->second.bars,
          project_io::sequence_pattern_fingerprint(found->second),
          loaded.value().revision);
      if (!begun.has_value()) {
        error_ = begun.error();
        return PatternTransportSubmit::refused;
      }
    }
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
  } else if (unlanded_overlay_generation_ != 0 &&
             command.pending_switch->generation ==
                 unlanded_overlay_generation_) {
    // The pending successor is this coordinator's own overlay, still queued
    // for its bar — identified by the generation of the publish receipt both
    // sides remember, never by the Pattern identity (a retarget can rebind
    // pattern_ while the marker lives). A transport command cannot fence
    // across an unlanded publication it would have to name as applied
    // authority; report busy and let the control cadence retry after the
    // boundary, which is also the audible deadline (#1513).
    return PatternTransportSubmit::busy;
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
  if (pending_ && close_applied_switch_) {
    const auto target = owner_.drain_target_segment(
        store_, derive_command(pending_->command_id, 1, 'a'),
        derive_command(pending_->command_id, 2, 'b'),
        derive_command(pending_->command_id, 3, 'c'));
    if (!target.has_value()) return target;
  }
  const auto closed = owner_.close_requested();
  if (!closed.has_value()) return closed;
  // A close without an applied switch settles the admission: the frozen prefix
  // is drained once, the terminal receipt seals it, its tail is committed to
  // Project Truth exactly once, and the settled journal is removed.
  if (pending_ && !close_applied_switch_) {
    const auto settled = owner_.settle_close(
        store_, derive_command(pending_->command_id, 1, 'a'),
        derive_command(pending_->command_id, 4, 'd'),
        derive_command(pending_->command_id, 2, 'b'));
    if (!settled.has_value()) return settled;
  }
  recording_ = false;
  close_pending_ = false;
  close_applied_switch_ = false;
  // The closed recording's overlay authority is spent: a later Record in the
  // same engagement must not mistake an unrelated successor for its own
  // overlay in the expected-generation check (#1513).
  published_generation_ = 0;
  published_projection_generation_ = 0;
  unlanded_overlay_generation_ = 0;
  overlay_publication_pending_ = false;
  refused_projection_generation_ = 0;
  settled_refused_projection_ = 0;
  overlay_refusals_ = 0;
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
  const auto admitted = owner_.admit(candidate);
  if (admitted.has_value() &&
      admitted.value() == PatternAdmissionAdmit::retained) {
    // Durable input may change the projection; the control cadence publishes
    // it (never inline on the trigger path), with a fresh retry budget.
    overlay_publication_pending_ = true;
  }
  return admitted;
}

foundation::Result<void> PatternTransportCoordinator::publish_overlay() {
  // The close owns the next publication once the cutoff is in flight, and a
  // closed engagement has nothing live to publish.
  if (!recording_ || close_pending_) {
    overlay_publication_pending_ = false;
    return foundation::Result<void>::success();
  }
  if (!overlay_publication_pending_) {
    if (settled_refused_projection_ != 0) {
      // Re-arm a settled refusal when the projection content has moved on,
      // or when the refusal was transient (a pool/quota class code): the
      // capability may have recovered for the same content. A permanent
      // refusal (an unwired seam) stays settled — new content re-arms it.
      const bool transient = settled_refusal_transient_ && !transient_retry_spent_;
      const auto retry_check = project_overlay();
      if (!retry_check.has_value()) {
        return foundation::Result<void>::failure(retry_check.error());
      }
      const auto moved_on = retry_check.value().has_value() &&
          retry_check.value()->generation != settled_refused_projection_;
      if (moved_on || transient) {
        overlay_publication_pending_ = true;
        overlay_refusals_ = 0;
        settled_refused_projection_ = 0;
        // A transient refusal re-arms exactly once per settle: the retry
        // window below (three attempts) is the recovery chance, and a second
        // settle for the same content is permanent — a still-full pool then
        // waits for content change rather than retrying every tick.
        transient_retry_spent_ = transient;
      } else {
        return foundation::Result<void>::success();
      }
    } else {
      return foundation::Result<void>::success();
    }
  }
  // A journal that has retained a switch and awaits reconciliation is in the
  // switching state; the journal would refuse the overlay record for a state
  // it considers ordinary, so hold the publication until reconciliation
  // re-anchors the projection (#1513).
  {
    const auto journal = journals_.read_active(bundle_);
    if (!journal.has_value()) {
      if (journal.error().code != foundation::ErrorCode::not_found) {
        return foundation::Result<void>::failure(journal.error());
      }
      // An absent journal while the recording is open is transient (a
      // settlement racing the close); keep the request and re-read next tick.
      return foundation::Result<void>::success();
    }
    // No admission yet (the fence is not established) is transient too: the
    // durable input behind the pending flag is still outstanding. The
    // switching state holds until reconciliation re-anchors the projection.
    if (!journal.value().admission.has_value() ||
        journal.value().state == project_io::SequenceSessionState::switching) {
      return foundation::Result<void>::success();
    }
  }
  const auto projected = project_overlay();
  if (!projected.has_value()) {
    return foundation::Result<void>::failure(projected.error());
  }
  if (!projected.value().has_value()) {
    // An absent projection is not "nothing to publish": the same read returns
    // absent for a journal still switching or an admission without its fence,
    // and the durable input behind the pending flag is still outstanding.
    // Keep the request; the next cadence re-reads.
    return foundation::Result<void>::success();
  }
  const auto& overlay = *projected.value();
  // An unlanded overlay owns this tick: wait for its Bar boundary before
  // doing anything else. One overlay can be audible per Bar, which is also
  // the coalescing the 4-slot pool needs (#1513 O4). Landing is proven by
  // BOTH the recorded generation becoming current and no pending successor
  // remaining: the generation counter is shared monotone, so either fact
  // alone could be advanced by an unrelated publication.
  if (unlanded_overlay_generation_ != 0) {
    // The port is the publisher: while it still reports this exact generation
    // as pending, the overlay has not landed. Once it stops reporting it, the
    // engine's shared counter decides: reached (>=) means applied — a later
    // publication on top does not un-apply it — and is recorded as the
    // authority the cutoff will name; never reached means superseded or
    // cancelled, the switch machinery owns that reconciliation, and the
    // marker is dropped without a record (#1513).
    const auto pending_now = audio_.pending_switch();
    // Match on the generation the publish receipt named — the coordinator's
    // pattern_ binding can move under a Record retarget while this overlay is
    // still queued, and the port's remembered authority already guarantees
    // the Pattern identity of that generation.
    const auto still_queued = pending_now.has_value() &&
        pending_now->generation == unlanded_overlay_generation_;
    if (still_queued) {
      return foundation::Result<void>::success();
    }
    if (audio_.pattern_generation() == unlanded_overlay_generation_) {
      // Equality is the landing proof: the shared counter is monotone across
      // all publications, so only this overlay becoming current can produce
      // it at the first tick past its boundary. Anything past it without
      // equality means a newer boundary superseded or cancelled the overlay
      // before it applied, the switch machinery owns that reconciliation,
      // and nothing is recorded. While the transport holds the engine, an
      // outside publication cannot advance the counter past this generation
      // (the engine refuses it; pinned by the superseded-overlay scenario),
      // so the equality window cannot be missed by a competing publication.
      const auto recorded = owner_.retain_overlay_publication(
          unlanded_overlay_generation_);
      // On a transient journal failure the marker SURVIVES this return, so
      // the next tick retries the retain for the same landed generation —
      // the record is idempotent under exact replay.
      if (!recorded.has_value()) return recorded;
      published_generation_ = unlanded_overlay_generation_;
    }
    unlanded_overlay_generation_ = 0;
  }
  // A pending switch owns the next boundary; an overlay published now could
  // not apply across it, and the engine would refuse a second unnamed
  // successor anyway.
  if (audio_.pending_switch().has_value()) {
    return foundation::Result<void>::success();
  }
  if (overlay.generation == 0 ||
      overlay.generation == published_projection_generation_) {
    overlay_publication_pending_ = false;
    return foundation::Result<void>::success();
  }
  const auto published = audio_.publish_overlay(
      overlay.pattern_id, overlay.events);
  if (!published.has_value()) {
    // Refusal is a capability fact (pool full, seam unwired). Retry the SAME
    // content on the next cadence tick, bounded per content: after a few
    // refusals of the same projection generation the request settles, so an
    // unwired Host costs a handful of ticks per content change, not one per
    // tick forever, while a Host that recovers is retried for the current
    // content (#1513).
    if (refused_projection_generation_ != overlay.generation) {
      refused_projection_generation_ = overlay.generation;
      overlay_refusals_ = 0;
    }
    ++overlay_refusals_;
    if (overlay_refusals_ >= 3) {
      // Settle the per-tick retry. A quota-class refusal (the 4-slot pool
      // momentarily full) is transient and re-arms on a later tick; an
      // unwired seam is permanent and stays settled until content changes.
      overlay_publication_pending_ = false;
      settled_refused_projection_ = overlay.generation;
      settled_refusal_transient_ =
          published.error().code == foundation::ErrorCode::bank_quota_exhausted &&
          !transient_retry_spent_;
    }
    return foundation::Result<void>::success();
  }
  overlay_refusals_ = 0;
  refused_projection_generation_ = 0;
  settled_refused_projection_ = 0;
  published_projection_generation_ = overlay.generation;
  unlanded_overlay_generation_ = published.value().generation;
  return foundation::Result<void>::success();
}

foundation::Result<std::optional<PatternTransportOverlayProjection>>
PatternTransportCoordinator::project_overlay() {
  using Projection =
      foundation::Result<std::optional<PatternTransportOverlayProjection>>;
  // Once the cutoff receipt is applied the candidate set is frozen and the
  // close owns the next publication, so an overlay here could only race it.
  if (!recording_ || close_pending_) return Projection::success(std::nullopt);
  const auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    if (journal.error().code == foundation::ErrorCode::not_found) {
      return Projection::success(std::nullopt);
    }
    return Projection::failure(journal.error());
  }
  if (journal.value().session_id != session_) {
    return Projection::success(std::nullopt);
  }
  auto projected = project_admission_overlay(journal.value(), false);
  if (!projected.has_value()) return Projection::failure(projected.error());
  if (!projected.value().has_value()) return Projection::success(std::nullopt);
  // The journal's Pattern is the one the conversion validated its segment
  // against, and the one the switch machinery re-anchors; publishing the
  // overlay against anything else would sound it on the wrong Pattern. It is
  // part of the projected content: a reconciled switch can carry identical
  // events onto a different Pattern, and a generation that ignored the
  // identity would leave a de-duplicating Host publishing the old one.
  if (projected_ != *projected.value() ||
      projected_pattern_ != journal.value().pattern_id) {
    const auto had_content = !projected_.empty();
    projected_ = std::move(*projected.value());
    projected_pattern_ = journal.value().pattern_id;
    // Advance whenever there is something to publish, and also when an overlay
    // that was published has become empty: a Host that de-duplicates on the
    // generation has to be told to drop it, not left holding stale content.
    // The one case that spends nothing is the first empty projection of a
    // recording that has contributed nothing yet.
    if (!projected_.empty() || had_content) ++projection_generation_;
  }
  return Projection::success(PatternTransportOverlayProjection{
      journal.value().pattern_id, projection_generation_, projected_});
}

foundation::Result<void> PatternTransportCoordinator::continue_operation() {
  if (close_pending_ && pending_) {
    const auto closed = finish_close();
    if (!closed.has_value()) {
      error_ = closed.error();
      phase_ = terminal(closed.error()) ? PatternTransportPhase::error
                                        : PatternTransportPhase::flushing;
      return closed;
    }
    error_.reset();
    retained_.insert_or_assign(pending_->command_id, *pending_);
    last_ = pending_;
    pending_.reset();
    phase_ = PatternTransportPhase::idle;
    return foundation::Result<void>::success();
  }
  if (!pending_ && overlay_publication_pending_) {
    // The overlay publication shares this cadence with the close machinery
    // (#1513). It runs only when no request is in flight and the phase is
    // idle, so it can never interleave with an awaiting-audio transition.
    if (phase_ == PatternTransportPhase::idle) {
      const auto published = publish_overlay();
      if (!published.has_value()) return published;
    }
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
    // A deterministic authority/identity failure (for example a Pattern that
    // changed behind the engagement) never resolves by re-reading the same
    // retained receipt; park the engagement in the error phase instead of
    // looping awaiting_audio forever. Recovery is a Project reopen, where the
    // owner-loss recovery surface lists the unresolved journal.
    phase_ = terminal(applied.error())
                 ? PatternTransportPhase::error
                 : (close_pending_ ? PatternTransportPhase::flushing
                                   : PatternTransportPhase::awaiting_audio);
    return applied;
  }
  retained_.insert_or_assign(pending_->command_id, *pending_);
  last_ = pending_;
  pending_.reset();
  phase_ = PatternTransportPhase::idle;
  return foundation::Result<void>::success();
}

}  // namespace lmdj::facade::detail
