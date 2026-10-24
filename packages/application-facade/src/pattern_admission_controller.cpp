#include "pattern_admission_controller.hpp"
#include "pattern_transport_io_owner.hpp"
#include "pattern_opening_test_seam.hpp"

#include <chrono>
#include <utility>
#include <algorithm>
#include <limits>
#include <lmdj/audio/prepared_sample_bank.hpp>

namespace lmdj::facade::detail {
namespace {
using Transfer = project_io::SequenceAdmissionTransfer;
using TransferResult = foundation::Result<Transfer>;

foundation::Error conversion_failure(const char* reason) {
  return {foundation::ErrorCode::invalid_argument,
      "Pattern admission conversion is unresolved",
      {{"reason", reason}, {"journal_retained", true}}};
}
TransferResult conversion_error(const char* reason) {
  return TransferResult::failure(conversion_failure(reason));
}
foundation::Result<void> owner_error(const char* reason) {
  return foundation::Result<void>::failure(conversion_error(reason).error());
}
std::optional<project_io::SequencePublicationAuthority> pending_applied_switch(
    const project_io::SequenceAdmissionState& admission) {
  if (!admission.applied_switches.empty() &&
      admission.applied_switches.back().generation > admission.segment_generation) {
    return admission.applied_switches.back();
  }
  if (admission.cutoff_fence &&
      admission.cutoff_fence->switch_outcome ==
          project_io::SequenceSwitchOutcome::applied_before_cutoff &&
      admission.cutoff_fence->switch_authority &&
      admission.cutoff_fence->switch_applied_frame &&
      admission.cutoff_fence->switch_authority->generation >
          admission.segment_generation) {
    return project_io::SequencePublicationAuthority{
        admission.cutoff_fence->switch_authority->pattern_id,
        admission.cutoff_fence->switch_authority->generation,
        *admission.cutoff_fence->switch_applied_frame};
  }
  return std::nullopt;
}
std::optional<std::uint64_t> last_retained_watermark(
    const project_io::SequenceAdmissionState& admission) {
  if (!admission.candidates.empty()) return admission.candidates.back().watermark;
  for (auto it = admission.transfers.rbegin(); it != admission.transfers.rend();
       ++it) {
    if (!it->terminal) return it->last_watermark;
  }
  return std::nullopt;
}

// Conversion authority for one durable admission: the publication segment its
// candidates convert against, a later retained switch they must not cross, and
// the checkpoint the previous transfer left behind. Shared so a retained
// transfer and a live projection can never resolve a different segment.
//
// Precondition for both helpers below: `journal.admission` holds a value. Each
// caller establishes it before calling, and both live in this anonymous
// namespace, so the dereference is not guarded again here.
struct AdmissionSegment {
  project_io::SequencePublicationAuthority segment;
  std::optional<project_io::SequencePublicationAuthority> pending;
  project_io::SequenceAdmissionCheckpoint checkpoint;
};

foundation::Result<AdmissionSegment> resolve_admission_segment(
    const project_io::ActiveSequenceJournal& journal) {
  using namespace project_io;
  using Resolved = foundation::Result<AdmissionSegment>;
  const auto& admission = *journal.admission;
  // owner_lost is accepted: the recovery surface resolves the same durable
  // segment the live owner would have (#1515). A live owner reaches this
  // code only in active/switching; nothing else can commit a transfer.
  if (!admission.admission_fence || admission.completed ||
      (!admission.transfers.empty() && admission.transfers.back().terminal) ||
      (journal.state != SequenceSessionState::active &&
       journal.state != SequenceSessionState::switching &&
       journal.state != SequenceSessionState::owner_lost)) {
    return Resolved::failure(conversion_failure("admission_fence_unresolved"));
  }
  const auto& fence = *admission.admission_fence;
  SequencePublicationAuthority segment{
      admission.preparation.pattern_id, admission.preparation.publication_generation,
      fence.effective_frame};
  std::optional<SequencePublicationAuthority> pending;
  for (const auto& authority : admission.applied_switches) {
    if (authority.generation == admission.segment_generation) segment = authority;
    if (authority.generation > admission.segment_generation) pending = authority;
  }
  if (admission.cutoff_fence && admission.cutoff_fence->switch_outcome ==
          SequenceSwitchOutcome::applied_before_cutoff) {
    const auto& cutoff = *admission.cutoff_fence;
    if (!cutoff.switch_authority || !cutoff.switch_applied_frame) {
      return Resolved::failure(conversion_failure("switch_authority_missing"));
    }
    const SequencePublicationAuthority authority{cutoff.switch_authority->pattern_id,
        cutoff.switch_authority->generation, *cutoff.switch_applied_frame};
    if (authority.generation == admission.segment_generation) segment = authority;
    if (authority.generation > admission.segment_generation) pending = authority;
  }
  if (segment.generation != admission.segment_generation ||
      segment.pattern_id != journal.pattern_id) {
    return Resolved::failure(conversion_failure("segment_authority_missing"));
  }
  SequenceAdmissionCheckpoint checkpoint{
      segment.pattern_id, segment.generation, segment.frame, {}};
  if (!admission.transfers.empty() &&
      admission.transfers.back().checkpoint.publication_generation == segment.generation) {
    checkpoint = admission.transfers.back().checkpoint;
  }
  return Resolved::success(
      AdmissionSegment{segment, pending, std::move(checkpoint)});
}

// The single candidate-to-event conversion. Pure: it reads the journal and
// mutates nothing, so the retained transfer and the live projection cannot
// compute different overlays from the same durable state.
struct AdmissionConversion {
  std::vector<domain::PatternEvent> events;
  std::map<domain::PadSlotId, PatternOwnedPress> pressed;
  std::vector<project_io::SequenceCandidateReceipt> receipts;
  std::uint64_t last_runtime_frame{};
  bool changed{};
};

foundation::Result<AdmissionConversion> convert_admission_candidates(
    const project_io::ActiveSequenceJournal& journal,
    const AdmissionSegment& resolved,
    std::span<const project_io::SequenceAdmissionCandidate> candidates) {
  using namespace project_io;
  using Converted = foundation::Result<AdmissionConversion>;
  const auto& admission = *journal.admission;
  const auto& fence = *admission.admission_fence;
  const auto& segment = resolved.segment;
  const auto& pending = resolved.pending;
  AdmissionConversion state{journal.pending_events, {}, {},
      resolved.checkpoint.last_runtime_frame, false};
  for (const auto& press : resolved.checkpoint.owned_presses) {
    state.pressed.emplace(press.slot, PatternOwnedPress{
        press.raw_attack_tick, press.onset_tick, press.velocity, press.press_sequence});
  }
  std::uint64_t overlay_generation = 0;
  std::optional<std::uint64_t> previous_frame;
  for (const auto& candidate : candidates) {
    state.receipts.push_back(sequence_admission_candidate_receipt(candidate));
    if (previous_frame && candidate.runtime_frame < *previous_frame) {
      return Converted::failure(conversion_failure("candidate_frame_regressed"));
    }
    previous_frame = candidate.runtime_frame;
    // Target-side candidates await the ordinary journal switch at its retained
    // audio boundary. They must not disappear as an excluded source prefix.
    if (pending && candidate.runtime_frame >= pending->frame) {
      return Converted::failure(
          conversion_failure("switch_prefix_requires_reconciliation"));
    }
    if (candidate.runtime_frame < segment.frame ||
        (admission.cutoff_fence &&
         candidate.runtime_frame >= admission.cutoff_fence->effective_frame)) continue;
    if (candidate.runtime_frame < state.last_runtime_frame) {
      return Converted::failure(conversion_failure("candidate_frame_regressed"));
    }
    const SequenceAdmissionTimingProfile* profile = nullptr;
    for (const auto& item : admission.timing_profiles) {
      if (item.first_watermark <= candidate.watermark &&
          item.publication_generation == segment.generation) profile = &item;
    }
    audio::TransportAnchor anchor{fence.origin_frame, 0, fence.bpm};
    if (profile) {
      anchor = {profile->runtime_frame, profile->tick_numerator, profile->bpm};
    } else if (segment.generation != admission.preparation.publication_generation) {
      if (!admission.cutoff_fence) {
        return Converted::failure(
            conversion_failure("segment_timing_profile_missing"));
      }
      anchor = {segment.frame, 0, admission.cutoff_fence->bpm};
    }
    const auto ticks = audio::raw_tick_at(anchor, candidate.runtime_frame);
    if (!ticks.has_value()) return Converted::failure(ticks.error());
    PatternEventReducer reducer{journal.bars,
        profile ? profile->quantize_enabled : admission.preparation.quantize_enabled,
        profile ? profile->swing_percent : admission.preparation.swing_percent,
        overlay_generation, state.events, state.pressed};
    if (candidate.kind == SequenceCandidateKind::press) {
      reducer.press(candidate.slot, ticks.value(), candidate.velocity, candidate.press_sequence);
    } else if (!reducer.release(candidate.slot, ticks.value(), candidate.press_sequence)) {
      continue;  // Pre-admission or superseded live press: never invent a journal press.
    }
    state.changed = true;
    state.last_runtime_frame = candidate.runtime_frame;
  }
  return Converted::success(std::move(state));
}
}  // namespace

foundation::Result<project_io::SequenceAdmissionTransfer> build_admission_transfer(
    const project_io::ActiveSequenceJournal& journal,
    foundation::CommandId transfer_id, std::uint64_t last_watermark, bool terminal) {
  using namespace project_io;
  if (!domain::is_valid_uuid(transfer_id.value()) || !journal.admission) {
    return conversion_error("admission_identity_missing");
  }
  const auto& admission = *journal.admission;
  for (const auto& retained : admission.transfers) {
    if (retained.transfer_id == transfer_id) {
      if (retained.terminal != terminal || retained.last_watermark != last_watermark) {
        return conversion_error("transfer_identity_collision");
      }
      return TransferResult::success(retained);
    }
  }
  auto resolved = resolve_admission_segment(journal);
  if (!resolved.has_value()) return TransferResult::failure(resolved.error());
  const auto& pending = resolved.value().pending;
  auto checkpoint = resolved.value().checkpoint;
  const auto previous_checkpoint = checkpoint;
  Transfer result{transfer_id, terminal, 0, 0, sequence_admission_candidates_sha256({}),
      {}, journal.pattern_id, journal.expected_revision, {},
      journal.pending_events, checkpoint};
  if (terminal) {
    if (last_watermark != 0 || !admission.closure || !admission.cutoff_fence ||
        !admission.candidates.empty() || pending ||
        admission.cutoff_fence->pattern_id != journal.pattern_id ||
        checkpoint.last_runtime_frame > admission.cutoff_fence->effective_frame) {
      return conversion_error("terminal_authority_unresolved");
    }
    auto converted = convert_admission_candidates(journal, resolved.value(), {});
    if (!converted.has_value()) return TransferResult::failure(converted.error());
    std::uint64_t overlay_generation = 0;
    PatternEventReducer reducer{journal.bars, false, 50,
        overlay_generation, converted.value().events, converted.value().pressed};
    reducer.finalize_unreleased(true);
    result.recoverable_tail = std::move(converted.value().events);
    result.checkpoint.owned_presses.clear();
    result.checkpoint.last_runtime_frame = admission.cutoff_fence->effective_frame;
    return TransferResult::success(std::move(result));
  }
  if (admission.candidates.empty() ||
      admission.candidates.size() > kSequenceAdmissionMaxCandidates ||
      (admission.closure && !admission.cutoff_fence)) {
    return conversion_error("candidate_prefix_unresolved");
  }
  const auto end = std::ranges::find(admission.candidates, last_watermark,
                                    &SequenceAdmissionCandidate::watermark);
  if (end == admission.candidates.end()) return conversion_error("candidate_prefix_missing");
  const auto count = static_cast<std::size_t>(end - admission.candidates.begin()) + 1;
  const auto prefix = std::span<const SequenceAdmissionCandidate>{admission.candidates}.first(count);
  result.first_watermark = prefix.front().watermark;
  result.last_watermark = last_watermark;
  result.candidates_sha256 = sequence_admission_candidates_sha256(prefix);
  auto converted = convert_admission_candidates(journal, resolved.value(), prefix);
  if (!converted.has_value()) return TransferResult::failure(converted.error());
  result.candidate_receipts = std::move(converted.value().receipts);
  if (converted.value().changed) {
    if (journal.last_input_sequence == std::numeric_limits<std::uint64_t>::max()) {
      return conversion_error("journal_input_sequence_exhausted");
    }
    result.journal_input_sequence = journal.last_input_sequence.value_or(0) + 1;
    std::uint64_t overlay_generation = 0;
    PatternEventReducer reducer{journal.bars, false, 50,
        overlay_generation, converted.value().events, converted.value().pressed};
    result.recoverable_tail = reducer.recoverable_tail();
    checkpoint.last_runtime_frame = converted.value().last_runtime_frame;
    checkpoint.owned_presses.clear();
    for (const auto& [slot, press] : converted.value().pressed) {
      checkpoint.owned_presses.push_back({slot, *press.correlation,
          press.raw_attack_tick, press.onset_tick, press.velocity});
    }
    result.checkpoint = std::move(checkpoint);
  } else {
    result.checkpoint = previous_checkpoint;
  }
  return TransferResult::success(std::move(result));
}

foundation::Result<std::optional<std::vector<domain::PatternEvent>>>
project_admission_overlay(const project_io::ActiveSequenceJournal& journal,
                          bool finalize) {
  using namespace project_io;
  using Projection =
      foundation::Result<std::optional<std::vector<domain::PatternEvent>>>;
  // States a live recording passes through that simply have nothing to show:
  // no admission at all, one not yet activated, already sealed, or more
  // candidates than the bounded admission admits. None of these is a
  // conversion failure and none may poison a coordinator. An owner-lost
  // journal is empty for the LIVE projection (no coordinator drives it), but
  // with `finalize` the recovery surface reads the same durable input: the
  // owner is gone, no cutoff will ever arrive, and the take ends where the
  // last durably retained candidate left it (#1515).
  if (!journal.admission) return Projection::success(std::nullopt);
  const auto& admission = *journal.admission;
  const bool live_state = journal.state == SequenceSessionState::active ||
                          journal.state == SequenceSessionState::switching;
  if (!admission.admission_fence || admission.completed ||
      (!admission.transfers.empty() && admission.transfers.back().terminal) ||
      (finalize
           ? (!live_state && journal.state != SequenceSessionState::owner_lost)
           : !live_state) ||
      admission.candidates.size() > kSequenceAdmissionMaxCandidates) {
    return Projection::success(std::nullopt);
  }
  auto resolved = resolve_admission_segment(journal);
  if (!resolved.has_value()) return Projection::failure(resolved.error());
  // A candidate at or after a retained switch awaits the ordinary journal
  // switch at its audio boundary. The *entire* overlay is withheld until that
  // reconciles, not merely the crossing candidate: the transfer builder fails
  // the whole call on the same durable shape, so converting the earlier prefix
  // here would publish events no transfer would commit. Nothing already
  // audible is lost - the prefix was projected on an earlier step, before the
  // crossing candidate landed. This is a live state, not a conversion
  // failure.
  if (resolved.value().pending) {
    for (const auto& candidate : admission.candidates) {
      if (candidate.runtime_frame >= resolved.value().pending->frame) {
        // Live: withhold the whole overlay until the switch reconciles - the
        // prefix was projected on an earlier step. Finalize (recovery): the
        // owner that would reconcile the switch is gone, so this shape can
        // never convert; fail so recovery refuses and keeps the journal
        // instead of silently dropping the retained candidates (#1515).
        if (finalize) {
          return Projection::failure(
              conversion_failure("switch_prefix_requires_reconciliation"));
        }
        return Projection::success(std::nullopt);
      }
    }
  }
  auto converted =
      convert_admission_candidates(journal, resolved.value(), admission.candidates);
  if (!converted.has_value()) return Projection::failure(converted.error());
  std::uint64_t overlay_generation = 0;
  PatternEventReducer reducer{journal.bars, false, 50,
      overlay_generation, converted.value().events, converted.value().pressed};
  if (finalize) {
    // The recovery take is terminal: a held press has no future release, so
    // it ends after its attack tail exactly like a terminal transfer does.
    reducer.finalize_unreleased(true);
  }
  return Projection::success(reducer.recoverable_tail());
}

foundation::Result<project_io::SequenceAdmissionTransfer> commit_admission_transfer(
    project_io::SequenceJournal& journals, const std::filesystem::path& bundle,
    foundation::SequenceSessionId session,
    const project_io::SequenceAdmissionIdentity& identity,
    foundation::CommandId transfer_id, std::uint64_t last_watermark, bool terminal) {
  const auto journal = journals.read_active(bundle);
  if (!journal.has_value()) return TransferResult::failure(journal.error());
  if (journal.value().session_id != session || !journal.value().admission ||
      journal.value().admission->preparation.identity != identity) {
    return conversion_error("admission_identity_mismatch");
  }
  auto transfer = build_admission_transfer(journal.value(), transfer_id, last_watermark, terminal);
  if (!transfer.has_value()) return transfer;
  const auto durable = journals.transfer_admission_prefix(bundle, session, identity, transfer.value());
  if (!durable.has_value()) return TransferResult::failure(durable.error());
  return transfer;
}

PatternAdmissionOwner::PatternAdmissionOwner(
    project_io::SequenceJournal& journals, std::filesystem::path bundle,
    foundation::SequenceSessionId session, Clock clock)
    : journals_(journals), bundle_(std::move(bundle)), session_(std::move(session)),
      clock_(clock ? std::move(clock)
                   : Clock{[] { return std::chrono::steady_clock::now(); }}) {}

foundation::Result<void> PatternAdmissionOwner::prepare(
    const project_io::SequenceAdmissionPreparation& preparation) {
  // Capture the first invocation before durable IO, including an unknown
  // response whose exact retry must not restart this opening's budget.
  return prepare(preparation, clock_());
}

foundation::Result<void> PatternAdmissionOwner::activate(
    const project_io::SequenceAdmissionFence& fence,
    PatternTransportOpeningCommit* commit) {
  if (!identity_) return owner_error("admission_identity_missing");
  if (fence.kind != project_io::SequenceFenceKind::admission) {
    return owner_error("admission_fence_unresolved");
  }
  const auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission ||
      journal.value().admission->preparation.identity != *identity_) {
    return owner_error("admission_identity_mismatch");
  }
  const auto& admission = *journal.value().admission;
  if (admission.admission_fence && *admission.admission_fence != fence) {
    // Preserve the journal's exact immutable collision validation.
    return journals_.retain_admission_fence(bundle_, session_, *identity_, fence);
  }
  if (opening_failure_) return expire_opening();
  const auto earlier = opening_completed_at(fence);
  // A readable fence can be an append whose sync failed. It supplies identity,
  // not durability or evidence of opening before this deadline.
  if (!earlier && deadline_elapsed(admission.preparation)) return expire_opening();
  // The synchronous/null-context path retains its injected Clock. Production
  // supplies preallocated typed evidence and never calls that callback while
  // holding the shared publication guard.
  auto pending = commit ? commit->pending_owner :
      std::make_shared<PatternAdmissionOpeningEvidence>(
          PatternAdmissionOpeningEvidence{fence, {}});
  std::shared_ptr<const PatternAdmissionOpeningEvidence> sealed = pending;
  const auto durable = journals_.retain_admission_fence(bundle_, session_, *identity_, fence);
  if (!durable.has_value()) return durable;
  bool late = false;
  if (commit) {
    {
      std::lock_guard lock(commit->publication.guard);
      // This is the logical opening point, after the actual durable API's
      // positive result. Capture, deadline check, local evidence and full
      // request publication all share this one short critical section.
      const auto completed_at = earlier ? *earlier : std::chrono::steady_clock::now();
      late = prepared_at_ && completed_at - *prepared_at_ >= opening_timeout_;
      if (!late) {
        if (!earlier) {
          pending->completed_at = completed_at;
          opening_evidence_.swap(sealed);
        }
        commit->pending_transport->completed_at = completed_at;
#if defined(LMDJ_PATTERN_OPENING_TESTING) && LMDJ_PATTERN_OPENING_TESTING
        if (!earlier) testing::pause_opening_before_publication(completed_at);
#endif
        commit->publication.successful.swap(commit->sealed_transport);
      }
    }
  } else if (!earlier) {
    const auto completed_at = clock_();
    late = prepared_at_ && completed_at - *prepared_at_ >= opening_timeout_;
    if (!late) {
      pending->completed_at = completed_at;
      opening_evidence_.swap(sealed);
    }
  }
  // Error construction, closure I/O and destruction of swapped-out shared
  // evidence all occur outside the guard. Late success never publishes open.
  if (late) return expire_opening();
  return foundation::Result<void>::success();
}

std::optional<std::chrono::steady_clock::time_point>
PatternAdmissionOwner::opening_completed_at(
    const project_io::SequenceAdmissionFence& fence) const {
  if (opening_failure_ || !opening_evidence_ || opening_evidence_->fence != fence ||
      !prepared_at_ || opening_evidence_->completed_at - *prepared_at_ >= opening_timeout_)
    return std::nullopt;
  return opening_evidence_->completed_at;
}

foundation::Result<void> PatternAdmissionOwner::expire_opening() {
  if (!opening_failure_) opening_failure_ = owner_error("admission_opening_deadline_elapsed").error();
  const auto closed = close_at(project_io::SequenceAdmissionCloseReason::deadline);
  if (!closed.has_value()) {
    auto error = closed.error();
    error.details["opening_deadline_elapsed"] = true;
    error.details["closure_unresolved"] = true;
    return foundation::Result<void>::failure(std::move(error));
  }
  return foundation::Result<void>::failure(*opening_failure_);
}

foundation::Result<void> PatternAdmissionOwner::prepare(
    const project_io::SequenceAdmissionPreparation& preparation,
    std::chrono::steady_clock::time_point started_at) {
  const bool same_identity = identity_ && *identity_ == preparation.identity;
  const bool same_attempt = preparation_attempt_identity_ &&
      *preparation_attempt_identity_ == preparation.identity;
  if (!same_attempt || !preparation_attempt_started_at_) {
    preparation_attempt_identity_ = preparation.identity;
    preparation_attempt_started_at_ = started_at;
  } else {
    preparation_attempt_started_at_ = std::min(*preparation_attempt_started_at_, started_at);
  }
  if (same_identity && prepared_at_)
    preparation_attempt_started_at_ = std::min(*preparation_attempt_started_at_, *prepared_at_);
  const auto prepared = journals_.prepare_admission(bundle_, session_, preparation);
  if (!prepared.has_value()) return prepared;
  if (!same_identity) {
    opening_evidence_.reset();
    opening_failure_.reset();
  }
  identity_ = preparation.identity;
  settled_close_.reset();
  prepared_at_ = preparation_attempt_started_at_;
  opening_timeout_ = std::chrono::milliseconds{preparation.fence_timeout_ms};
  return foundation::Result<void>::success();
}

foundation::Result<void> PatternAdmissionOwner::cutoff(
    const project_io::SequenceAdmissionFence& fence) {
  if (!identity_) return owner_error("admission_identity_missing");
  if (fence.kind != project_io::SequenceFenceKind::cutoff) {
    return owner_error("admission_fence_unresolved");
  }
  return journals_.retain_admission_fence(bundle_, session_, *identity_, fence);
}

foundation::Result<void> PatternAdmissionOwner::retain_switch(
    const project_io::SequencePublicationAuthority& authority) {
  if (!identity_) return owner_error("admission_identity_missing");
  return journals_.retain_admission_switch(
      bundle_, session_, *identity_, authority);
}

foundation::Result<void> PatternAdmissionOwner::retain_overlay_publication(
    std::uint64_t generation) {
  if (!identity_) return owner_error("admission_identity_missing");
  return journals_.retain_admission_overlay(
      bundle_, session_, *identity_, generation);
}

foundation::Result<void> PatternAdmissionOwner::reconcile_switch(
    project_io::ProjectStore& store) {
  if (!identity_) return owner_error("admission_identity_missing");
  const auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission ||
      journal.value().admission->preparation.identity != *identity_) {
    return owner_error("admission_identity_mismatch");
  }
  const auto pending = pending_applied_switch(*journal.value().admission);
  if (!pending) return foundation::Result<void>::success();
  const auto project = store.load(bundle_);
  if (!project.has_value()) {
    return foundation::Result<void>::failure(project.error());
  }
  if (project.value().id != journal.value().admission->preparation.project_id ||
      project.value().revision != journal.value().expected_revision) {
    // A successful settings rebase advances this Journal too. An interrupted
    // rebase is unresolved authority, not permission to bind a newer Project.
    return owner_error("segment_project_authority_changed");
  }
  const auto found = project.value().patterns.find(pending->pattern_id);
  if (found == project.value().patterns.end()) {
    return owner_error("segment_authority_missing");
  }
  return journals_.switch_pattern(
      bundle_, session_, pending->pattern_id, found->second.bars,
      project_io::sequence_pattern_fingerprint(found->second),
      journal.value().expected_revision);
}

foundation::Result<void> PatternAdmissionOwner::continue_segment(
    project_io::ProjectStore& store,
    const project_io::SequencePublicationAuthority& authority,
    std::uint16_t bpm, std::uint64_t tick_numerator, foundation::CommandId transfer_id,
    foundation::CommandId flush_id, foundation::CommandId profile_id) {
  if (!identity_) return owner_error("admission_identity_missing");
  auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) return foundation::Result<void>::failure(journal.error());
  if (journal.value().session_id != session_ || !journal.value().admission ||
      journal.value().admission->preparation.identity != *identity_)
    return owner_error("admission_identity_mismatch");
  const auto& admission = *journal.value().admission;
  // A historical exact retry finishes durability without re-entering an old
  // Pattern, deriving a new frontier, or touching its already committed Truth.
  for (const auto& profile : admission.timing_profiles) {
    if (profile.command_id != profile_id) continue;
    if (profile.pattern_id != authority.pattern_id ||
        profile.publication_generation != authority.generation ||
        profile.runtime_frame != authority.frame || profile.tick_numerator != tick_numerator ||
        profile.bpm != bpm || std::ranges::find(admission.applied_switches, authority) ==
            admission.applied_switches.end())
      return owner_error("segment_work_identity_collision");
    return journals_.retain_admission_timing_profile(bundle_, session_, *identity_, profile);
  }
  if (journal.value().state != project_io::SequenceSessionState::active ||
      !admission.admission_fence || admission.cutoff_fence || admission.closure ||
      admission.completed || bpm < 40 || bpm > 240)
    return owner_error("segment_requires_active_admission");
  // Upper control owns ordering. Once post-S input was accepted using the
  // source clock we cannot repair it by retroactively inserting a profile.
  if (std::ranges::any_of(admission.candidates, [&](const auto& candidate) {
        return candidate.runtime_frame >= authority.frame;
      }) || (!admission.transfers.empty() &&
        admission.transfers.back().checkpoint.publication_generation != authority.generation &&
        admission.transfers.back().checkpoint.last_runtime_frame >= authority.frame))
    return owner_error("segment_requires_parked_target_input");
  const auto truth = store.load(bundle_);
  if (!truth.has_value()) return foundation::Result<void>::failure(truth.error());
  if (truth.value().id != admission.preparation.project_id ||
      !truth.value().patterns.contains(authority.pattern_id))
    return owner_error("segment_project_authority_changed");
  if (truth.value().revision != journal.value().expected_revision) {
    bool exact_committed_flush = false;
    for (const auto& flush : journal.value().flushes) {
      if (flush.completed || flush.pattern_id != journal.value().pattern_id) continue;
      const auto replay = store.replay_sequence_flush(bundle_,
          {session_, flush.flush_seq, flush.command_id, flush.pattern_id});
      if (!replay.has_value()) return foundation::Result<void>::failure(replay.error());
      if (replay.value() && replay.value()->committed_revision == truth.value().revision &&
          replay.value()->command.meta.expected_revision == flush.expected_revision &&
          replay.value()->command.events == flush.canonical_events) {
        exact_committed_flush = true;
        break;
      }
    }
    if (!exact_committed_flush) return owner_error("segment_project_authority_changed");
  }
  // An interrupted exact source flush can already have advanced Truth. Its
  // original durable receipt must finish through execute_sequence_flush;
  // reconcile_switch then checks the resulting revision again. A different
  // mutation cannot borrow that receipt to rebase this recording.
  auto result = retain_switch(authority);
  if (!result.has_value()) return result;
  // Exact retain_switch also syncs a readable partial switch record before
  // reconcile_switch may observe that it has already advanced the segment.
  result = drain_source_prefix(store, transfer_id, flush_id);
  if (!result.has_value()) return result;
  result = reconcile_switch(store);
  if (!result.has_value()) return result;
  journal = journals_.read_active(bundle_);
  if (!journal.has_value()) return foundation::Result<void>::failure(journal.error());
  if (journal.value().session_id != session_ || !journal.value().admission ||
      journal.value().admission->preparation.identity != *identity_)
    return owner_error("admission_identity_mismatch");
  const auto& current = *journal.value().admission;
  if (journal.value().pattern_id != authority.pattern_id ||
      current.segment_generation != authority.generation)
    return owner_error("segment_authority_mismatch");
  auto first = current.preparation.first_watermark;
  if (!current.transfers.empty()) {
    const auto last = current.transfers.back().last_watermark;
    if (last == std::numeric_limits<std::uint64_t>::max())
      return owner_error("segment_watermark_exhausted");
    first = std::max(first, last + 1);
  }
  if (!current.timing_profiles.empty())
    first = std::max(first, current.timing_profiles.back().first_watermark);
  const auto quantize = current.timing_profiles.empty()
      ? current.preparation.quantize_enabled : current.timing_profiles.back().quantize_enabled;
  const auto swing = current.timing_profiles.empty()
      ? current.preparation.swing_percent : current.timing_profiles.back().swing_percent;
  return journals_.retain_admission_timing_profile(bundle_, session_, *identity_,
      {profile_id, first, authority.pattern_id, authority.generation,
       journal.value().expected_revision, authority.frame, tick_numerator, bpm, quantize, swing});
}

foundation::Result<void> PatternAdmissionOwner::drain_source_prefix(
    project_io::ProjectStore& store, foundation::CommandId transfer_id,
    foundation::CommandId flush_id) {
  if (!identity_) return owner_error("admission_identity_missing");
  auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission ||
      journal.value().admission->preparation.identity != *identity_) {
    return owner_error("admission_identity_mismatch");
  }
  const auto pending = pending_applied_switch(*journal.value().admission);
  if (!pending) return foundation::Result<void>::success();
  for (const auto& flush : journal.value().flushes) {
    if (flush.completed || flush.pattern_id != journal.value().pattern_id) continue;
    const auto executed = store.execute_sequence_flush(
        bundle_, {session_, flush.flush_seq, flush.command_id, flush.pattern_id});
    if (!executed.has_value()) {
      return foundation::Result<void>::failure(executed.error());
    }
  }
  journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission ||
      journal.value().admission->preparation.identity != *identity_) {
    return owner_error("admission_identity_mismatch");
  }
  std::optional<std::uint64_t> last_watermark;
  for (const auto& candidate : journal.value().admission->candidates) {
    if (candidate.runtime_frame < pending->frame) {
      last_watermark = candidate.watermark;
    }
  }
  if (last_watermark) {
    const auto transfer = drain(transfer_id, *last_watermark, false);
    if (!transfer.has_value()) {
      return foundation::Result<void>::failure(transfer.error());
    }
  }
  // A prior checkpoint can consume every source candidate while retaining its
  // tail. An excluded new prefix likewise need not advance the input sequence.
  // Flush the fresh durable tail, not only a newly created transfer's output.
  journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission ||
      journal.value().admission->preparation.identity != *identity_) {
    return owner_error("admission_identity_mismatch");
  }
  if (journal.value().pending_events.empty())
    return foundation::Result<void>::success();
  const auto flush = journals_.append_flush(
      bundle_, session_, flush_id, journal.value().pattern_id,
      journal.value().expected_revision, journal.value().pending_events);
  if (!flush.has_value()) {
    return foundation::Result<void>::failure(flush.error());
  }
  const auto executed = store.execute_sequence_flush(
      bundle_, {session_, flush.value().flush_seq, flush_id,
                journal.value().pattern_id});
  if (!executed.has_value()) {
    return foundation::Result<void>::failure(executed.error());
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> PatternAdmissionOwner::drain_target_segment(
    project_io::ProjectStore& store, foundation::CommandId transfer_id,
    foundation::CommandId flush_id, foundation::CommandId profile_id) {
  if (!identity_) return owner_error("admission_identity_missing");
  auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission) {
    return owner_error("admission_identity_mismatch");
  }
  if (pending_applied_switch(*journal.value().admission)) {
    return owner_error("switch_prefix_requires_reconciliation");
  }
  for (const auto& flush : journal.value().flushes) {
    if (flush.completed || flush.pattern_id != journal.value().pattern_id) continue;
    const auto executed = store.execute_sequence_flush(
        bundle_, {session_, flush.flush_seq, flush.command_id, flush.pattern_id});
    if (!executed.has_value()) {
      return foundation::Result<void>::failure(executed.error());
    }
  }
  journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission) {
    return owner_error("admission_identity_mismatch");
  }
  const auto& admission = *journal.value().admission;
  if (admission.candidates.empty()) return foundation::Result<void>::success();
  (void)profile_id;
  const auto last_watermark = admission.candidates.back().watermark;
  const auto transfer = drain(transfer_id, last_watermark, false);
  if (!transfer.has_value()) {
    return foundation::Result<void>::failure(transfer.error());
  }
  if (!transfer.value().journal_input_sequence) {
    return foundation::Result<void>::success();
  }
  journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  const auto flush = journals_.append_flush(
      bundle_, session_, flush_id, journal.value().pattern_id,
      journal.value().expected_revision, transfer.value().recoverable_tail);
  if (!flush.has_value()) {
    return foundation::Result<void>::failure(flush.error());
  }
  const auto executed = store.execute_sequence_flush(
      bundle_, {session_, flush.value().flush_seq, flush_id,
                journal.value().pattern_id});
  if (!executed.has_value()) {
    return foundation::Result<void>::failure(executed.error());
  }
  return foundation::Result<void>::success();
}

bool PatternAdmissionOwner::deadline_elapsed(
    const project_io::SequenceAdmissionPreparation& preparation) const {
  if (!prepared_at_) return false;
  const auto elapsed = clock_() - *prepared_at_;
  return elapsed >= std::chrono::milliseconds{preparation.fence_timeout_ms};
}

foundation::Result<void> PatternAdmissionOwner::close_at(
    project_io::SequenceAdmissionCloseReason reason) {
  const auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission) {
    return owner_error("admission_identity_mismatch");
  }
  const auto& admission = *journal.value().admission;
  // Exact closure replay also finishes a prior unknown sync response; readable
  // closure bytes alone cannot retire the retained failure operation.
  if (admission.closure) return close(*admission.closure);
  return close({last_retained_watermark(admission), reason});
}

foundation::Result<PatternAdmissionAdmit> PatternAdmissionOwner::admit(
    const project_io::SequenceAdmissionCandidate& candidate) {
  if (!identity_) {
    return foundation::Result<PatternAdmissionAdmit>::failure(
        conversion_error("admission_identity_missing").error());
  }
  const auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<PatternAdmissionAdmit>::failure(journal.error());
  }
  return admit(candidate, journal.value());
}

foundation::Result<PatternAdmissionAdmit> PatternAdmissionOwner::admit(
    const project_io::SequenceAdmissionCandidate& candidate,
    const project_io::ActiveSequenceJournal& journal) {
  if (!identity_) {
    return foundation::Result<PatternAdmissionAdmit>::failure(
        conversion_error("admission_identity_missing").error());
  }
  if (journal.session_id != session_ || !journal.admission) {
    return foundation::Result<PatternAdmissionAdmit>::failure(
        conversion_error("admission_identity_mismatch").error());
  }
  const auto& admission = *journal.admission;
  if (journal.state == project_io::SequenceSessionState::owner_lost ||
      journal.state == project_io::SequenceSessionState::abandoned ||
      admission.completed) {
    return foundation::Result<PatternAdmissionAdmit>::success(
        PatternAdmissionAdmit::live_only);
  }
  if (admission.closure) {
    return foundation::Result<PatternAdmissionAdmit>::success(
        PatternAdmissionAdmit::live_only);
  }
  const bool known_opening = admission.admission_fence &&
      opening_completed_at(*admission.admission_fence).has_value();
  if (!known_opening && deadline_elapsed(admission.preparation)) {
    const auto closed =
        close_at(project_io::SequenceAdmissionCloseReason::deadline);
    if (!closed.has_value()) {
      return foundation::Result<PatternAdmissionAdmit>::failure(closed.error());
    }
    return foundation::Result<PatternAdmissionAdmit>::success(
        PatternAdmissionAdmit::live_only);
  }
  if (!known_opening ||
      candidate.runtime_frame < admission.admission_fence->effective_frame) {
    return foundation::Result<PatternAdmissionAdmit>::success(
        PatternAdmissionAdmit::live_only);
  }
  const auto durable = journals_.append_admission_candidate(
      bundle_, session_, *identity_, candidate);
  if (!durable.has_value()) {
    auto error = durable.error();
    error.details["uncertain_suffix_watermark"] = candidate.watermark;
    const auto closed = close_at(
        project_io::SequenceAdmissionCloseReason::storage_failure);
    if (!closed.has_value()) {
      error.details["closure_unresolved"] = true;
      error.details["closure_error"] = closed.error().message;
    }
    const auto after = journals_.read_active(bundle_);
    if (after.has_value() && after.value().admission) {
      const auto prefix = last_retained_watermark(*after.value().admission);
      if (prefix) error.details["last_retained_watermark"] = *prefix;
      if (after.value().admission->closure &&
          after.value().admission->closure->last_retained_watermark) {
        error.details["last_retained_watermark"] =
            *after.value().admission->closure->last_retained_watermark;
      }
    }
    return foundation::Result<PatternAdmissionAdmit>::failure(std::move(error));
  }
  return foundation::Result<PatternAdmissionAdmit>::success(
      PatternAdmissionAdmit::retained);
}

foundation::Result<void> PatternAdmissionOwner::checkpoint_prefix(foundation::CommandId transfer_id) {
  const auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) return foundation::Result<void>::failure(journal.error());
  if (!journal.value().admission || journal.value().session_id != session_)
    return owner_error("admission_identity_mismatch");
  const auto& candidates = journal.value().admission->candidates;
  if (candidates.empty()) return foundation::Result<void>::success();
  const auto transferred = drain(std::move(transfer_id), candidates.back().watermark, false);
  return transferred.has_value() ? foundation::Result<void>::success()
                                 : foundation::Result<void>::failure(transferred.error());
}

foundation::Result<void> PatternAdmissionOwner::close(
    const project_io::SequenceAdmissionClosure& closure) {
  if (!identity_) return owner_error("admission_identity_missing");
  return journals_.close_admission(bundle_, session_, *identity_, closure);
}

foundation::Result<void> PatternAdmissionOwner::close_requested() {
  return close_at(project_io::SequenceAdmissionCloseReason::requested);
}

foundation::Result<void> PatternAdmissionOwner::settle_close(
    project_io::ProjectStore& store, foundation::CommandId transfer_id,
    foundation::CommandId terminal_id, foundation::CommandId flush_id) {
  if (!identity_) return owner_error("admission_identity_missing");
  auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission) {
    return owner_error("admission_identity_mismatch");
  }
  if (!journal.value().admission->candidates.empty()) {
    const auto transfer = drain(
        transfer_id, journal.value().admission->candidates.back().watermark,
        false);
    if (!transfer.has_value()) {
      return foundation::Result<void>::failure(transfer.error());
    }
  }
  const auto terminal = drain(terminal_id, 0, true);
  if (!terminal.has_value()) {
    return foundation::Result<void>::failure(terminal.error());
  }
  // The terminal receipt re-exposes the finalized tail as pending events;
  // flush it to Project Truth exactly once before completion.
  if (!terminal.value().recoverable_tail.empty()) {
    journal = journals_.read_active(bundle_);
    if (!journal.has_value()) {
      return foundation::Result<void>::failure(journal.error());
    }
    if (journal.value().session_id != session_) {
      return owner_error("admission_identity_mismatch");
    }
    const auto flush = journals_.append_flush(
        bundle_, session_, flush_id, journal.value().pattern_id,
        journal.value().expected_revision, terminal.value().recoverable_tail);
    if (!flush.has_value()) {
      return foundation::Result<void>::failure(flush.error());
    }
    const auto executed = store.execute_sequence_flush(
        bundle_, {session_, flush.value().flush_seq, flush_id,
                  journal.value().pattern_id});
    if (!executed.has_value()) {
      return foundation::Result<void>::failure(executed.error());
    }
  }
  const auto completed =
      journals_.complete_admission(bundle_, session_, *identity_);
  if (!completed.has_value()) return completed;
  // This proof precedes removal and survives its unknown response. Project
  // Truth and terminal admission were durably settled under these exact IDs.
  settled_close_ = std::pair{terminal_id, flush_id};
  return journals_.remove_active_if_complete(bundle_, session_);
}

bool PatternAdmissionOwner::has_settled_close(const foundation::CommandId& terminal_id,
                                              const foundation::CommandId& flush_id) const {
  return settled_close_ && settled_close_->first == terminal_id && settled_close_->second == flush_id;
}

foundation::Result<project_io::SequenceAdmissionTransfer>
PatternAdmissionOwner::drain(
    foundation::CommandId transfer_id, std::uint64_t last_watermark, bool terminal) {
  if (!identity_) return conversion_error("admission_identity_missing");
  const auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) return TransferResult::failure(journal.error());
  if (journal.value().state == project_io::SequenceSessionState::owner_lost ||
      journal.value().state == project_io::SequenceSessionState::abandoned) {
    return conversion_error("admission_fence_unresolved");
  }
  return commit_admission_transfer(
      journals_, bundle_, session_, *identity_, transfer_id, last_watermark,
      terminal);
}

PatternEventReducer::PatternEventReducer(
    std::uint8_t bars, bool quantize_enabled, std::uint8_t swing_percent,
    std::uint64_t& generation, std::vector<domain::PatternEvent>& events,
    std::map<domain::PadSlotId, PatternOwnedPress>& pressed)
    : bars_(bars), quantize_enabled_(quantize_enabled),
      swing_percent_(swing_percent), generation_(generation), events_(events),
      pressed_(pressed) {}

void PatternEventReducer::merge_pending(domain::PatternEvent event) {
  auto merged = domain::merge_pattern_events(events_, {std::move(event)});
  if (merged != events_) {
    events_ = std::move(merged);
    ++generation_;
  }
}

void PatternEventReducer::finalize_pressed(
    domain::PadSlotId slot, std::uint64_t raw_release_tick, bool remove_press) {
  const auto found = pressed_.find(slot);
  if (found == pressed_.end()) {
    return;
  }
  merge_pending(domain::PatternEvent{
      slot, found->second.onset_tick,
      domain::normalize_duration_tick(
          found->second.raw_attack_tick, raw_release_tick,
          found->second.onset_tick, domain::pattern_length_ticks(bars_)),
      found->second.velocity});
  if (remove_press) {
    pressed_.erase(found);
  }
}

void PatternEventReducer::press(
    domain::PadSlotId slot, std::uint64_t raw_attack_tick, std::uint8_t velocity,
    std::optional<std::uint64_t> correlation) {
  finalize_pressed(slot, raw_attack_tick, true);
  pressed_.insert_or_assign(slot, PatternOwnedPress{
      raw_attack_tick,
      domain::quantize_onset_tick(raw_attack_tick,
          domain::pattern_length_ticks(bars_), quantize_enabled_, swing_percent_),
      velocity, correlation});
}

bool PatternEventReducer::release(
    domain::PadSlotId slot, std::uint64_t raw_release_tick,
    std::optional<std::uint64_t> correlation) {
  const auto found = pressed_.find(slot);
  if (found == pressed_.end() ||
      (correlation.has_value() && found->second.correlation != correlation)) {
    return false;
  }
  finalize_pressed(slot, raw_release_tick, true);
  return true;
}

std::vector<domain::PatternEvent> PatternEventReducer::recoverable_tail() const {
  auto result = events_;
  const auto loop_length = domain::pattern_length_ticks(bars_);
  for (const auto& [slot, press] : pressed_) {
    result = domain::merge_pattern_events(result, {domain::PatternEvent{
        slot, press.onset_tick,
        domain::normalize_duration_tick(
            press.raw_attack_tick, press.raw_attack_tick + domain::kSixteenthTicks,
            press.onset_tick, loop_length),
        press.velocity}});
  }
  return result;
}

void PatternEventReducer::finalize_unreleased(bool clear) {
  std::vector<domain::PadSlotId> slots;
  slots.reserve(pressed_.size());
  for (const auto& [slot, press] : pressed_) {
    (void)press;
    slots.push_back(slot);
  }
  for (const auto slot : slots) {
    const auto attack = pressed_.at(slot).raw_attack_tick;
    finalize_pressed(slot, attack + domain::kSixteenthTicks, clear);
  }
}

}  // namespace lmdj::facade::detail
