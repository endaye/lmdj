#include "pattern_admission_controller.hpp"

#include <chrono>
#include <utility>
#include <algorithm>
#include <limits>
#include <lmdj/audio/prepared_sample_bank.hpp>

namespace lmdj::facade::detail {
namespace {
using Transfer = project_io::SequenceAdmissionTransfer;
using TransferResult = foundation::Result<Transfer>;

TransferResult conversion_error(const char* reason) {
  return TransferResult::failure({foundation::ErrorCode::invalid_argument,
      "Pattern admission conversion is unresolved",
      {{"reason", reason}, {"journal_retained", true}}});
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
  if (!admission.admission_fence || admission.completed ||
      (!admission.transfers.empty() && admission.transfers.back().terminal) ||
      (journal.state != SequenceSessionState::active &&
       journal.state != SequenceSessionState::switching)) {
    return conversion_error("admission_fence_unresolved");
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
      return conversion_error("switch_authority_missing");
    }
    const SequencePublicationAuthority authority{cutoff.switch_authority->pattern_id,
        cutoff.switch_authority->generation, *cutoff.switch_applied_frame};
    if (authority.generation == admission.segment_generation) segment = authority;
    if (authority.generation > admission.segment_generation) pending = authority;
  }
  if (segment.generation != admission.segment_generation ||
      segment.pattern_id != journal.pattern_id) {
    return conversion_error("segment_authority_missing");
  }
  SequenceAdmissionCheckpoint checkpoint{
      segment.pattern_id, segment.generation, segment.frame, {}};
  if (!admission.transfers.empty() &&
      admission.transfers.back().checkpoint.publication_generation == segment.generation) {
    checkpoint = admission.transfers.back().checkpoint;
  }
  const auto previous_checkpoint = checkpoint;
  auto events = journal.pending_events;
  std::map<domain::PadSlotId, PatternOwnedPress> pressed;
  for (const auto& press : checkpoint.owned_presses) {
    pressed.emplace(press.slot, PatternOwnedPress{
        press.raw_attack_tick, press.onset_tick, press.velocity, press.press_sequence});
  }
  std::uint64_t overlay_generation = 0;
  Transfer result{transfer_id, terminal, 0, 0, sequence_admission_candidates_sha256({}),
      {}, journal.pattern_id, journal.expected_revision, {}, events, checkpoint};
  if (terminal) {
    if (last_watermark != 0 || !admission.closure || !admission.cutoff_fence ||
        !admission.candidates.empty() || pending ||
        admission.cutoff_fence->pattern_id != journal.pattern_id ||
        checkpoint.last_runtime_frame > admission.cutoff_fence->effective_frame) {
      return conversion_error("terminal_authority_unresolved");
    }
    PatternEventReducer reducer{journal.bars, false, 50,
        overlay_generation, events, pressed};
    reducer.finalize_unreleased(true);
    result.recoverable_tail = std::move(events);
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
  bool changed = false;
  std::optional<std::uint64_t> previous_frame;
  for (const auto& candidate : prefix) {
    result.candidate_receipts.push_back(sequence_admission_candidate_receipt(candidate));
    if (previous_frame && candidate.runtime_frame < *previous_frame) {
      return conversion_error("candidate_frame_regressed");
    }
    previous_frame = candidate.runtime_frame;
    // Target-side candidates await the ordinary journal switch at its retained
    // audio boundary. They must not disappear as an excluded source prefix.
    if (pending && candidate.runtime_frame >= pending->frame) {
      return conversion_error("switch_prefix_requires_reconciliation");
    }
    if (candidate.runtime_frame < segment.frame ||
        (admission.cutoff_fence &&
         candidate.runtime_frame >= admission.cutoff_fence->effective_frame)) continue;
    if (candidate.runtime_frame < checkpoint.last_runtime_frame) {
      return conversion_error("candidate_frame_regressed");
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
        return conversion_error("segment_timing_profile_missing");
      }
      anchor = {segment.frame, 0, admission.cutoff_fence->bpm};
    }
    const auto ticks = audio::raw_tick_at(anchor, candidate.runtime_frame);
    if (!ticks.has_value()) return TransferResult::failure(ticks.error());
    PatternEventReducer reducer{journal.bars,
        profile ? profile->quantize_enabled : admission.preparation.quantize_enabled,
        profile ? profile->swing_percent : admission.preparation.swing_percent,
        overlay_generation, events, pressed};
    if (candidate.kind == SequenceCandidateKind::press) {
      reducer.press(candidate.slot, ticks.value(), candidate.velocity, candidate.press_sequence);
    } else if (!reducer.release(candidate.slot, ticks.value(), candidate.press_sequence)) {
      continue;  // Pre-admission or superseded live press: never invent a journal press.
    }
    changed = true;
    checkpoint.last_runtime_frame = candidate.runtime_frame;
  }
  if (changed) {
    if (journal.last_input_sequence == std::numeric_limits<std::uint64_t>::max()) {
      return conversion_error("journal_input_sequence_exhausted");
    }
    result.journal_input_sequence = journal.last_input_sequence.value_or(0) + 1;
    PatternEventReducer reducer{journal.bars, false, 50,
        overlay_generation, events, pressed};
    result.recoverable_tail = reducer.recoverable_tail();
    checkpoint.owned_presses.clear();
    for (const auto& [slot, press] : pressed) {
      checkpoint.owned_presses.push_back({slot, *press.correlation,
          press.raw_attack_tick, press.onset_tick, press.velocity});
    }
    result.checkpoint = std::move(checkpoint);
  } else {
    result.checkpoint = previous_checkpoint;
  }
  return TransferResult::success(std::move(result));
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
  const auto prepared = journals_.prepare_admission(bundle_, session_, preparation);
  if (!prepared.has_value()) return prepared;
  identity_ = preparation.identity;
  prepared_at_ = clock_();
  return foundation::Result<void>::success();
}

foundation::Result<void> PatternAdmissionOwner::activate(
    const project_io::SequenceAdmissionFence& fence) {
  if (!identity_) return owner_error("admission_identity_missing");
  if (fence.kind != project_io::SequenceFenceKind::admission) {
    return owner_error("admission_fence_unresolved");
  }
  return journals_.retain_admission_fence(bundle_, session_, *identity_, fence);
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

foundation::Result<void> PatternAdmissionOwner::reconcile_switch(
    project_io::ProjectStore& store) {
  if (!identity_) return owner_error("admission_identity_missing");
  const auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission) {
    return owner_error("admission_identity_mismatch");
  }
  const auto pending = pending_applied_switch(*journal.value().admission);
  if (!pending) return foundation::Result<void>::success();
  const auto project = store.load(bundle_);
  if (!project.has_value()) {
    return foundation::Result<void>::failure(project.error());
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

foundation::Result<void> PatternAdmissionOwner::drain_source_prefix(
    project_io::ProjectStore& store, foundation::CommandId transfer_id,
    foundation::CommandId flush_id) {
  if (!identity_) return owner_error("admission_identity_missing");
  auto journal = journals_.read_active(bundle_);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  if (journal.value().session_id != session_ || !journal.value().admission) {
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
  if (journal.value().session_id != session_ || !journal.value().admission) {
    return owner_error("admission_identity_mismatch");
  }
  std::optional<std::uint64_t> last_watermark;
  for (const auto& candidate : journal.value().admission->candidates) {
    if (candidate.runtime_frame < pending->frame) {
      last_watermark = candidate.watermark;
    }
  }
  if (!last_watermark) return foundation::Result<void>::success();
  const auto transfer = drain(transfer_id, *last_watermark, false);
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
  if (admission.closure) return foundation::Result<void>::success();
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
  if (journal.value().session_id != session_ || !journal.value().admission) {
    return foundation::Result<PatternAdmissionAdmit>::failure(
        conversion_error("admission_identity_mismatch").error());
  }
  const auto& admission = *journal.value().admission;
  if (journal.value().state == project_io::SequenceSessionState::owner_lost ||
      journal.value().state == project_io::SequenceSessionState::abandoned ||
      admission.completed) {
    return foundation::Result<PatternAdmissionAdmit>::success(
        PatternAdmissionAdmit::live_only);
  }
  if (admission.closure) {
    return foundation::Result<PatternAdmissionAdmit>::success(
        PatternAdmissionAdmit::live_only);
  }
  if (deadline_elapsed(admission.preparation)) {
    const auto closed =
        close_at(project_io::SequenceAdmissionCloseReason::deadline);
    if (!closed.has_value()) {
      return foundation::Result<PatternAdmissionAdmit>::failure(closed.error());
    }
    return foundation::Result<PatternAdmissionAdmit>::success(
        PatternAdmissionAdmit::live_only);
  }
  if (!admission.admission_fence ||
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

foundation::Result<void> PatternAdmissionOwner::close(
    const project_io::SequenceAdmissionClosure& closure) {
  if (!identity_) return owner_error("admission_identity_missing");
  return journals_.close_admission(bundle_, session_, *identity_, closure);
}

foundation::Result<void> PatternAdmissionOwner::close_requested() {
  return close_at(project_io::SequenceAdmissionCloseReason::requested);
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
