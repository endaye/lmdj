#include "pattern_transport_controller.hpp"

#include <cstddef>
#include <array>
#include <limits>
#include <algorithm>
#include <picosha2.h>
#include "pattern_transport_io_owner.hpp"
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

bool empty_legacy_prefix(const project_io::ActiveSequenceJournal& journal) {
  return !journal.last_input_sequence && journal.next_tail_seq == 0 &&
      journal.pending_events.empty() && journal.next_flush_seq == 0 &&
      journal.flushes.empty() && !journal.armed_capture_slot &&
      !journal.capture_commit;
}

// Admission authority/identity validation failures are deterministic: the same
// retained receipt can never apply on a retry. Anything else (journal IO,
// internal errors) may be transient and keeps its bounded retry phase.
bool terminal(const foundation::Error& error) {
  return error.code == foundation::ErrorCode::invalid_argument;
}

}  // namespace

struct PatternTransportCoordinator::Async {
  using Json = nlohmann::json;
  using Void = foundation::Result<void>;
  struct Input {
    PatternTransportInputRequest request;
    PatternTransportInputStatus status;
    std::chrono::steady_clock::time_point started;
    bool submitted{};
    bool release_partition{};
    bool waiting_cutoff{};
  };
  struct Hold {
    std::uint64_t sequence{};
    domain::PadSlotId slot;
    bool recorded{};
    bool metadata{true};
    bool release_reserved{};
    std::uint64_t ticket{};
    bool release_consumed{};
  };
  struct Switch {
    PatternTransportSwitchStatus status;
    PatternTransportRequest recording;
    foundation::CommandId command;
  };
  Async(PatternTransportAudioPort& port, PatternTransportExecutor& worker,
        PatternTransportControllerConfig binding,
        ScheduledPatternTransportAudioPort* capability,
        std::shared_ptr<PatternTransportOpeningPublication> opening)
      : audio(port), executor(worker), config(std::move(binding)), scheduled(capability),
        opening_publication(std::move(opening)) {}

  static foundation::Error busy(const char* reason = "pattern_transport_io_pending") {
    return {foundation::ErrorCode::io_error, "Pattern transport effect is pending",
        {{"reason", reason}, {"pending", true}, {"remedy", "inspect the original retained ticket"}}};
  }
  static bool valid(const PatternTransportRequest& r, const PatternTransportControllerConfig& c) {
    return r.runtime_generation == c.runtime_generation && r.session == c.session &&
        r.project_id == c.project && r.expected_epoch != 0 && domain::is_valid_uuid(r.command_id.value());
  }
  static bool same_publication(const audio::PatternReplacementAuthority& a,
                               const audio::PatternReplacementAuthority& b) {
    return a.generation == b.generation && a.pattern_id == b.pattern_id &&
        a.activation_frame == b.activation_frame;
  }
  Switch* find_switch(const PatternTransportSwitchTicket& ticket) {
    for (auto& s : switches) if (s && s->status.ticket == ticket) return &*s;
    return nullptr;
  }
  const Switch* find_switch(const PatternTransportSwitchTicket& ticket) const {
    for (const auto& s : switches) if (s && s->status.ticket == ticket) return &*s;
    return nullptr;
  }
  Switch* switch_work() {
    if (!work_request || work_kind != "segment") return nullptr;
    for (auto& s : switches)
      if (s && s->command == work_request->identity.command_id) return &*s;
    return nullptr;
  }
  bool unsettled_switches() const {
    for (const auto& s : switches)
      if (s && !s->status.durable_settled && !s->status.owner_disposed) return true;
    return false;
  }
  static void refresh_switch(Switch& s) {
    const auto& native = s.status.native_result;
    if (native && native->disposition == audio::PatternPublicationDisposition::cancelled)
      s.status.durable_settled = true; // Actual final absence has no segment.
    s.status.complete = native && native->disposition != audio::PatternPublicationDisposition::pending &&
        (s.status.durable_settled || s.status.owner_disposed);
  }
  foundation::Result<PatternTransportSwitchTicket> reserve_switch(
      const PatternTransportSwitchRequest& request) {
    using Result = foundation::Result<PatternTransportSwitchTicket>;
    if (request.runtime_generation != config.runtime_generation ||
        !domain::is_valid_uuid(request.pattern_id.value()))
      return Result::failure({foundation::ErrorCode::invalid_argument, "Stale Pattern switch reservation"});
    if (!recording || !recording_request || !durable_pattern || shutdown || owner_invalidated ||
        pending || closing || phase != PatternTransportPhase::idle || error || work_request ||
        executor.inspect().ticket || legacy_candidate || legacy_result || next_switch_ticket == UINT64_MAX)
      return Result::failure(busy("recording_switch_preparation_pending"));
    if (std::ranges::all_of(switches, [](const auto& s) { return s.has_value(); }))
      return Result::failure(busy("recording_switch_capacity"));
    if (request.pattern_id == *durable_pattern && !unsettled_switches())
      return Result::failure({foundation::ErrorCode::invalid_argument,
          "Current Pattern selection has no recording switch",
          {{"reason", "recording_switch_current_pattern"}}});
    for (const auto& s : switches) if (s && !s->status.durable_settled) {
      if (!s->status.publication || request.pattern_id == *durable_pattern ||
          request.pattern_id == s->status.pattern_id)
        return Result::failure(busy("recording_switch_material_pending"));
    }
    // Withdrawal belongs to the existing overlay owner. A claimed overlay
    // remains busy until its actual application/Journal record settles.
    if (unlanded_overlay) {
      const auto queued = audio.pending_switch();
      if (!queued || queued->generation != unlanded_overlay || !audio.cancel_overlay(*queued))
        return Result::failure(busy("recording_switch_overlay_pending"));
      unlanded_overlay = published_projection = 0;
    }
    for (auto& cell : switches) if (!cell) {
      const auto serial = next_switch_ticket + 1;
      const auto preimage = "recording-pattern-switch:" + recording_request->command_id.value() + ":" +
          std::to_string(config.runtime_generation) + ":" +
          std::to_string(recording_request->expected_epoch) + ":" + std::to_string(serial);
      auto digest = picosha2::hash256_hex_string(preimage);
      digest[12] = '4'; digest[16] = '8';
      const foundation::CommandId command{digest.substr(0,8) + "-" + digest.substr(8,4) + "-" +
          digest.substr(12,4) + "-" + digest.substr(16,4) + "-" + digest.substr(20,12)};
      const PatternTransportSwitchTicket ticket{config.runtime_generation, serial};
      cell.emplace(Switch{{ticket, request.pattern_id, {}, {}, 0, false, false, false, {}},
                          *recording_request, command});
      next_switch_ticket = serial;
      return Result::success(ticket);
    }
    return Result::failure(busy("recording_switch_capacity"));
  }
  bool bind_switch(const PatternTransportSwitchTicket& ticket,
      const audio::PatternReplacementAuthority& authority, std::uint16_t bpm) {
    auto* s = find_switch(ticket);
    if (!s || authority.pattern_id != s->status.pattern_id || !authority.generation || bpm < 40 || bpm > 240)
      return false;
    if (s->status.publication)
      return same_publication(*s->status.publication, authority) && s->status.bpm == bpm;
    auto previous = durable_generation;
    for (const auto& other : switches) if (other && other->status.publication)
      previous = std::max(previous, other->status.publication->generation);
    if (authority.generation <= previous || shutdown || owner_invalidated) return false;
    s->status.publication = authority;
    s->status.bpm = bpm;
    return true;
  }
  bool complete_switch(const PatternTransportSwitchTicket& ticket,
      const audio::PatternPublicationObservation& observation) {
    auto* s = find_switch(ticket);
    if (!s || !s->status.publication || !same_publication(*s->status.publication, observation.authority))
      return false;
    if (observation.disposition != audio::PatternPublicationDisposition::pending &&
        observation.disposition != audio::PatternPublicationDisposition::applied &&
        observation.disposition != audio::PatternPublicationDisposition::cancelled) return false;
    const bool applied = observation.disposition == audio::PatternPublicationDisposition::applied;
    if (applied != observation.applied_frame.has_value() ||
        (applied && *observation.applied_frame < observation.authority.activation_frame)) return false;
    if (s->status.native_result &&
        s->status.native_result->disposition != audio::PatternPublicationDisposition::pending)
      return s->status.native_result->disposition == observation.disposition &&
          s->status.native_result->applied_frame == observation.applied_frame;
    s->status.native_result = observation;
    if (applied && observation.authority.generation > observed_switch_generation) {
      observed_switch_generation = observation.authority.generation;
      switch_origin = observation.applied_frame;
      origin = *switch_origin;
    }
    refresh_switch(*s);
    return true;
  }
  bool consume_switch(const PatternTransportSwitchTicket& ticket) {
    for (auto& s : switches) if (s && s->status.ticket == ticket && s->status.complete) {
      s.reset();
      return true;
    }
    return false;
  }
  bool abandon_switch(const PatternTransportSwitchTicket& ticket) {
    for (auto& s : switches) if (s && s->status.ticket == ticket && !s->status.publication) {
      s.reset();
      return true;
    }
    return false;
  }
  bool switch_blocks_input(std::uint64_t frame) const {
    const Switch* first = nullptr;
    for (const auto& s : switches) if (s && !s->status.durable_settled && !s->status.owner_disposed &&
        (!first || s->status.ticket.ticket < first->status.ticket.ticket)) first = &*s;
    if (!first) return false;
    if (!first->status.publication) return true;
    const auto boundary = first->status.native_result && first->status.native_result->applied_frame
        ? *first->status.native_result->applied_frame : first->status.publication->activation_frame;
    return frame >= boundary;
  }
  void drive_switches() {
    if (work_request || owner_invalidated || switch_failure) return;
    Switch* first = nullptr;
    for (auto& s : switches) if (s && !s->status.durable_settled &&
        (!first || s->status.ticket.ticket < first->status.ticket.ticket)) first = &*s;
    if (!first || !first->status.native_result ||
        first->status.native_result->disposition != audio::PatternPublicationDisposition::applied) return;
    const auto frame = *first->status.native_result->applied_frame;
    if (close_cutoff && frame >= close_cutoff->effective_frame) {
      first->status.error = foundation::Error{foundation::ErrorCode::invalid_argument,
          "Applied Pattern switch conflicts with the actual cutoff"};
      switch_failure = error = first->status.error;
      phase = PatternTransportPhase::error;
      return;
    }
    for (const auto& input : inputs) if (input && !input->status.durable_settled &&
        !input->waiting_cutoff && input->request.runtime_frame < frame) return;
    if (legacy_candidate && !legacy_result && legacy_candidate->runtime_frame < frame) return;
    auto request = first->recording;
    request.command_id = first->command;
    work({{"op", "segment"}, {"recording", first->recording.command_id.value()},
        {"pattern", first->status.pattern_id.value()}, {"generation", first->status.publication->generation},
        {"frame", frame}, {"bpm", first->status.bpm}}, request);
  }
  void drive_legacy_input() {
    if (!legacy_candidate || legacy_result || work_request) return;
    if (owner_invalidated && switch_failure) {
      legacy_result = foundation::Result<PatternAdmissionAdmit>::failure(*switch_failure);
      return;
    }
    const auto& c = *legacy_candidate;
    if (close_cutoff && c.runtime_frame >= close_cutoff->effective_frame) {
      legacy_result = foundation::Result<PatternAdmissionAdmit>::success(PatternAdmissionAdmit::live_only);
      return;
    }
    if (!recording || switch_blocks_input(c.runtime_frame)) return;
    work({{"op", "admit"}, {"candidate", {
        {"watermark", c.watermark}, {"frame", c.runtime_frame},
        {"bank", c.slot.bank}, {"pad", c.slot.pad},
        {"pressed", c.kind == project_io::SequenceCandidateKind::press},
        {"velocity", c.velocity}, {"correlation", c.press_sequence}}}}, *recording_request);
  }
  bool retains(const foundation::CommandId& id) const {
    return (pending && pending->command_id == id) || retained.contains(id) ||
        (count.request && count.request->transport.command_id == id) ||
        (cancel && cancel->transport.command_id == id);
  }
  PatternTransportStatus inspect() const {
    return {playing, recording, phase, config.runtime_generation,
        pending ? pending->expected_epoch : last_epoch, origin,
        pending ? std::optional{pending->command_id} : last_command, error};
  }
  bool active_schedule() const {
    return count.request && !schedule_settled;
  }
  PatternTransportSubmit request(const PatternTransportRequest& r) {
    if (r.runtime_generation != config.runtime_generation || !domain::is_valid_uuid(r.command_id.value()))
      return PatternTransportSubmit::stale;
    if (r.session != config.session || r.project_id != config.project) return PatternTransportSubmit::invalid;
    if (shutdown && failed_preparation && failed_preparation->request.command_id == r.command_id)
      return failed_preparation->request == r ? PatternTransportSubmit::replayed
                                              : PatternTransportSubmit::invalid;
    if (shutdown || phase == PatternTransportPhase::error) return PatternTransportSubmit::refused;
    if (const auto found = retained.find(r.command_id); found != retained.end())
      return found->second == r ? PatternTransportSubmit::replayed : PatternTransportSubmit::invalid;
    if (active_schedule()) {
      return cancel_request({r, count.request->frame_epoch, count.request->schedule_serial});
    }
    if (pending) {
      if (*pending != r) return PatternTransportSubmit::busy;
      // Replaying an admission is not evidence that its retained I/O error
      // was resolved. Keep it until the real readback/retry completes.
      return PatternTransportSubmit::replayed;
    }
    if (r.expected_epoch <= last_epoch) return PatternTransportSubmit::stale;
    if (!recording && audio.supports_receipt_bound_opening()) {
      const auto observation = audio.observe_transport();
      if (!observation || !observation->current_pattern || !observation->current_generation)
        return PatternTransportSubmit::busy;
    }
    if (recording) {
      // Capture an actual cutoff immediately. I/O and input drain follow it;
      // Stop stays serviceable even while an append owns the worker cell.
      if (!submit_audio(r, r.intent == PatternTransportIntent::play_stop
              ? audio::PatternTransportAction::stop : audio::PatternTransportAction::fence))
        return audio_submit_result == audio::PatternTransportSubmit::busy
            ? PatternTransportSubmit::busy : PatternTransportSubmit::refused;
      pending = r;
      // A prior recording's F is not this request's cutoff authority. Wait
      // for the newly accepted Native request's actual receipt before I/O.
      close_cutoff.reset();
      cutoff_done = false;
      closing = true;
      phase = PatternTransportPhase::awaiting_audio;
      return PatternTransportSubmit::accepted;
    }
    error.reset();
    pending = r;
    if (r.intent == PatternTransportIntent::record) {
      prepare_started = std::chrono::steady_clock::now();
      // This admission owns a new opening clock, including its prepare work.
      // A retained earlier count-in ticket keeps its receipts, but cannot
      // supply the deadline or opening disposition for an ordinary Record.
      opening_started = prepare_started;
      opening_done = false;
      opening_failed = false;
      switch_origin.reset();
      observed_switch_generation = 0;
      // An asynchronous prepare can span a real Pattern Apply even when no
      // publication was pending at admission. Capability ports always bind
      // the durable opening to their actual receipt, never prior telemetry.
      receipt_bound = audio.supports_receipt_bound_opening();
      phase = PatternTransportPhase::preparing;
      prepare_needed = true;
    } else {
      if (!submit_audio(r, playing ? audio::PatternTransportAction::stop
                                  : audio::PatternTransportAction::start)) {
        pending.reset();
        return audio_submit_result == audio::PatternTransportSubmit::busy
            ? PatternTransportSubmit::busy : PatternTransportSubmit::refused;
      }
      phase = PatternTransportPhase::awaiting_audio;
    }
    return PatternTransportSubmit::accepted;
  }
  PatternTransportSubmit count_request(const ScheduledPatternTransportRequest& r) {
    if (!scheduled) return PatternTransportSubmit::refused;
    if (!valid(r.transport, config) || r.transport.intent != PatternTransportIntent::record ||
        !r.frame_epoch || !r.schedule_serial || r.schedule_serial > audio::kScheduledPatternSerialMaximum ||
        (r.bars != 1 && r.bars != 2)) return PatternTransportSubmit::invalid;
    if (count.request && count.request->transport.command_id == r.transport.command_id)
      return *count.request == r ? PatternTransportSubmit::replayed : PatternTransportSubmit::invalid;
    if (shutdown || playing || recording || pending || active_schedule()) return PatternTransportSubmit::busy;
    if (r.transport.expected_epoch <= last_epoch) return PatternTransportSubmit::stale;
    const auto target = audio.current_pattern().value_or(config.pattern);
    const audio::ScheduledPatternRecordRequest native{config.runtime_generation,
        r.frame_epoch, r.transport.expected_epoch, r.schedule_serial,
        audio.pattern_generation(), target, r.bars};
    const auto verdict = scheduled->submit_scheduled(native);
    if (verdict != audio::ScheduledPatternSubmit::accepted)
      return verdict == audio::ScheduledPatternSubmit::busy ? PatternTransportSubmit::busy
                                                            : PatternTransportSubmit::refused;
    // No Store, Journal, writer lease or even Project load before actual S.
    count = {};
    count.request = r;
    scheduled_pattern = native.pattern_id;
    scheduled_generation = native.expected_pattern_generation;
    cancel.reset();
    schedule_settled = false;
    start_acknowledged = false;
    cancel_acknowledged = false;
    opening_started.reset();
    opening_done = false;
    opening_failed = false;
    shutdown_recording_cutoff = false;
    owner_invalidated = owner_disposed = false;
    switch_origin.reset();
    observed_switch_generation = 0;
    owner_failure.reset();
    error.reset();
    close_cutoff.reset();
    phase = PatternTransportPhase::awaiting_audio;
    return PatternTransportSubmit::accepted;
  }
  PatternTransportSubmit cancel_request(const ScheduledPatternTransportCancel& r) {
    if (!scheduled || !count.request) return PatternTransportSubmit::refused;
    if (cancel) return *cancel == r ? PatternTransportSubmit::replayed : PatternTransportSubmit::busy;
    if (!valid(r.transport, config) || r.frame_epoch != count.request->frame_epoch ||
        r.schedule_serial != count.request->schedule_serial ||
        r.transport.expected_epoch <= count.request->transport.expected_epoch)
      return PatternTransportSubmit::invalid;
    if (schedule_settled) return PatternTransportSubmit::stale;
    const auto verdict = scheduled->cancel_scheduled({config.runtime_generation,
        r.frame_epoch, r.schedule_serial, r.transport.expected_epoch});
    if (verdict != audio::ScheduledPatternSubmit::accepted &&
        verdict != audio::ScheduledPatternSubmit::start_won)
      return verdict == audio::ScheduledPatternSubmit::busy ? PatternTransportSubmit::busy
                                                            : PatternTransportSubmit::refused;
    cancel = r;
    // start_won is not cancellation success: drive retains e1 and submits an
    // ordinary e2 cutoff, whether opening I/O is still held or has completed.
    cancel_lost = verdict == audio::ScheduledPatternSubmit::start_won;
    // An already Applied S owns an ordinary e2 cutoff. Submit it in this
    // short control turn so the next actual callback can establish F even
    // when a held append prevents the worker from making progress.
    if (cancel_lost) drive_schedule();
    return PatternTransportSubmit::accepted;
  }
  bool submit_audio(const PatternTransportRequest& r, audio::PatternTransportAction action) {
    audio::PatternTransportCommand command{config.runtime_generation, r.expected_epoch,
        audio.pattern_generation(), action, {}};
    // A legacy port can retain an already Applied switch authority through
    // pending_switch(). Preserve that fallback until the port advertises its
    // coherent receipt-bound observation capability.
    const auto observation = audio.supports_receipt_bound_opening()
        ? audio.observe_transport() : std::nullopt;
    if (observation) {
      command.expected_pattern_generation = observation->current_generation;
      command.pending_switch = observation->pending_switches[1]
          ? observation->pending_switches[1] : observation->pending_switches[0];
      command.pending_switch_predecessor = observation->pending_switches[1]
          ? observation->pending_switches[0] : std::nullopt;
      if (observation->outstanding_cancellation) {
        if (command.pending_switch) command.pending_switch_predecessor = observation->outstanding_cancellation;
        else command.pending_switch = observation->outstanding_cancellation;
      }
    } else if (playing) {
      command.pending_switch = audio.pending_switch();
      // An already Applied named authority must fence against the generation
      // of the actual acknowledged predecessor, never against itself.
      if (command.pending_switch && acknowledged_pattern_generation &&
          command.pending_switch->generation == command.expected_pattern_generation)
        command.expected_pattern_generation = acknowledged_pattern_generation;
    }
    if (command.pending_switch && unlanded_overlay &&
        command.pending_switch->generation == unlanded_overlay) {
      if (!audio.cancel_overlay(*command.pending_switch)) {
        audio_submit_result = audio::PatternTransportSubmit::busy;
        return false;
      }
      withdrawn_overlay = command.pending_switch;
      unlanded_overlay = 0;
      published_projection = 0;
      deferred_audio = true;
      deferred_action = action;
      deferred_attempts = 0;
      audio_submit_result = audio::PatternTransportSubmit::accepted;
      return true;
    }
    audio_submit_result = audio.submit(command);
    // Preserve the original bounded typed-observation refresh when a real
    // render boundary advances either of the two immutable publications.
    for (unsigned retry = 0; observation &&
         audio_submit_result == audio::PatternTransportSubmit::identity_mismatch && retry != 2; ++retry) {
      const auto refreshed = audio.observe_transport();
      if (!refreshed || !refreshed->current_pattern || !refreshed->current_generation) break;
      command.expected_pattern_generation = refreshed->current_generation;
      command.pending_switch = refreshed->pending_switches[1]
          ? refreshed->pending_switches[1] : refreshed->pending_switches[0];
      command.pending_switch_predecessor = refreshed->pending_switches[1]
          ? refreshed->pending_switches[0] : std::nullopt;
      if (refreshed->outstanding_cancellation) {
        if (command.pending_switch) command.pending_switch_predecessor = refreshed->outstanding_cancellation;
        else command.pending_switch = refreshed->outstanding_cancellation;
      }
      audio_submit_result = audio.submit(command);
    }
    if (audio_submit_result != audio::PatternTransportSubmit::accepted &&
        audio_submit_result != audio::PatternTransportSubmit::busy)
      error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern transport audio submit refused"};
    return audio_submit_result == audio::PatternTransportSubmit::accepted;
  }
  project_io::SequenceAdmissionFence fence(const audio::PatternTransportReceipt& r,
      const PatternTransportRequest& request, project_io::SequenceFenceKind kind) const {
    return {kind, request.command_id, r.epoch, r.effective_frame, r.origin_frame,
        r.pattern_id, r.pattern_generation, r.bpm, r.playing,
        r.switch_authority ? std::optional<project_io::SequencePublicationAuthority>{{
            r.switch_authority->pattern_id, r.switch_authority->generation,
            r.switch_authority->activation_frame}} : std::nullopt,
        switch_outcome(r.switch_decision), r.switch_applied_frame};
  }
  Json opening(const PatternTransportRequest& request, const foundation::PatternId& target,
               std::uint64_t generation, const char* operation,
               std::chrono::steady_clock::time_point started) const {
    return {{"op", operation}, {"pattern", target.value()}, {"generation", generation},
        {"revision", request.expected_revision ? Json(*request.expected_revision) : Json(nullptr)},
        {"started", transport_clock_stamp(started)}};
  }
  bool work(Json payload, const PatternTransportRequest& request,
            std::uint64_t input_ticket = 0) {
    if (work_request) return false;
    if (next_step == UINT64_MAX) {
      error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern work identity exhausted"};
      phase = PatternTransportPhase::error;
      return false;
    }
    PatternTransportWorkRequest w{{config.runtime_generation, request.expected_epoch,
        request.command_id, next_step + 1}, payload.dump()};
    const auto verdict = executor.submit(w);
    if (verdict != PatternTransportWorkSubmit::accepted) return false;
    ++next_step;
    work_kind = payload.at("op").get<std::string>();
    work_input = input_ticket;
    work_request = std::move(w);
    return true;
  }
  bool work_owner_disposition() {
    if (work_request || !input_owner_identity || next_step == UINT64_MAX) return false;
    auto identity = *input_owner_identity;
    identity.step = next_step + 1;
    PatternTransportWorkRequest request{identity, R"({"op":"owner_lost"})"};
    if (executor.submit_owner_disposition(request) != PatternTransportWorkSubmit::accepted) return false;
    ++next_step;
    work_kind = "owner_lost";
    work_input = 0;
    work_request = std::move(request);
    return true;
  }
  void finish_request() {
    if (!pending) return;
    retained.insert_or_assign(pending->command_id, *pending);
    last_epoch = pending->expected_epoch;
    last_command = pending->command_id;
    pending.reset();
    receipt.reset();
    closing = false;
    prepare_needed = false;
    phase = error ? PatternTransportPhase::error : PatternTransportPhase::idle;
  }
  void retire_failed_preparation() {
    if (!shutdown || !failed_preparation || !pending ||
        *pending != failed_preparation->request || !prepared || work_request || receipt ||
        recording || active_schedule()) return;
    // Known preparation and an actual Native not_running refusal have no S/F
    // or opening ACK. Retain that original failure; the same worker must still
    // confirm absence or durably dispose its real prepared Journal.
    owner_invalidated = true;
    owner_disposed = false;
    owner_failure = failed_preparation->error;
    error = owner_failure;
    playing = false;
    opening_failed = true;
    prepared = false;
    finish_request();
  }
  void expire_inputs() {
    const auto now = std::chrono::steady_clock::now();
    if (!earliest_unexpired_input_started ||
        now - *earliest_unexpired_input_started < kPatternTransportInputDeadline) return;
    earliest_unexpired_input_started.reset();
    for (auto& cell : inputs) {
      if (!cell || cell->status.complete || cell->status.expired) continue;
      if (now - cell->started >= kPatternTransportInputDeadline)
        cell->status.expired = true;
      else if (!earliest_unexpired_input_started || cell->started < *earliest_unexpired_input_started)
        earliest_unexpired_input_started = cell->started;
    }
  }
  Input* find(const PatternTransportInputTicket& ticket) {
    if (last_input_index < inputs.size()) {
      auto& cell = inputs[last_input_index];
      if (cell && cell->status.ticket == ticket) return &*cell;
    }
    for (std::size_t n = 0; n != inputs.size(); ++n) {
      auto& cell = inputs[n];
      if (cell && cell->status.ticket == ticket) {
        last_input_index = n;
        return &*cell;
      }
    }
    return nullptr;
  }
  const Input* find(const PatternTransportInputTicket& ticket) const {
    if (last_input_index < inputs.size()) {
      const auto& cell = inputs[last_input_index];
      if (cell && cell->status.ticket == ticket) return &*cell;
    }
    for (const auto& cell : inputs) if (cell && cell->status.ticket == ticket) return &*cell;
    return nullptr;
  }
  Hold* hold(std::uint64_t sequence) {
    for (auto& h : holds) if (h && h->sequence == sequence) return &*h;
    return nullptr;
  }
  void settle_input(Input& input, bool retained_candidate) {
    if (!input.request.pressed && !retained_candidate) {
      if (const auto* h = hold(input.request.correlation); h && h->recorded && h->metadata) {
        // A native-only/live-only release cannot settle an existing recording
        // hold. Keep this ticket until a real durable cutoff/owner disposition
        // has reconciled that hold's prefix, even if its native result exists.
        input.waiting_cutoff = true;
        return;
      }
    }
    input.status.durable_settled = true;
    input.status.retained = retained_candidate;
    input.status.complete = input.status.native_result.has_value();
    if (input.request.pressed && input.request.held && input.status.admission) {
      if (auto* h = hold(input.status.admission->sequence)) {
        h->recorded = retained_candidate;
        if (!retained_candidate) h->metadata = false;
      }
    } else if (!input.request.pressed) {
      // Exact release settlement spends only its recorded metadata obligation;
      // native escrow is owned and consumed separately by the native adapter.
      if (auto* h = hold(input.request.correlation); h && retained_candidate) h->metadata = false;
    }
    if (retained_candidate) { projection_dirty = true; ++projection_revision; }
  }
  bool poll_work(bool* opening_guard_busy = nullptr) {
    if (!work_request) return true;
    const auto observed = executor.inspect();
    if (!observed.completion) return false;
    const auto& done = *observed.completion;
    const auto original_input = work_input;
    if (done.outcome == PatternTransportWorkOutcome::success &&
        (work_kind == "open" || work_kind == "activate") && opening_publication) {
      const auto decision = opening_guard_decision();
      if (decision == OpeningGuardDecision::busy) {
        if (opening_guard_busy) *opening_guard_busy = true;
        return false;  // Retain the exact completion/cell; no ACK or UI change.
      }
      if (decision != OpeningGuardDecision::in_time) {
        error = foundation::Error{foundation::ErrorCode::internal_error,
            "Pattern opening completion lacks its exact guarded durable evidence"};
        return false;
      }
      // Still holding the original work identity: clear only a pure timer
      // failure, before consume can make its full request unavailable.
      reconcile_opening_timer(decision);
    }
    if (done.outcome == PatternTransportWorkOutcome::unknown) {
      // Unknown write effects retain the one cell. Expiry never frees it.
      error = done.error;
      if (auto* s = switch_work()) s->status.error = done.error;
      reconciliation_attempted = executor.reconcile(work_request->identity);
      if (work_input) for (auto& i : inputs) if (i && i->status.ticket.ticket == work_input)
        i->status.error = done.error;
      return false;
    }
    if (done.outcome == PatternTransportWorkOutcome::refused) {
      error = done.error;
      if (done.error && done.error->details.value("retryable", false)) {
        // Readback has proved a known prefix; the original effect identities
        // may now retry. This is not a timeout-triggered execute replay.
        const auto original = *work_request;
        executor.consume(original.identity);
        work_request.reset();
        work_kind.clear();
        work_input = 0;
        reconciliation_attempted = false;
        if (original.identity.transport_epoch == 0) work_owner_disposition();
        else if (closed_owner_disposition && closed_owner_request)
          work(Json::parse(original.payload), *closed_owner_request);
        else work(Json::parse(original.payload), PatternTransportRequest{config.session, config.project,
            original.identity.command_id, config.runtime_generation, original.identity.transport_epoch,
            PatternTransportIntent::record, {}}, original_input);
        return false;
      }
      if (work_input) {
        for (auto& i : inputs) if (i && i->status.ticket.ticket == work_input) {
          i->status.error = done.error;
          settle_input(*i, false);
        }
      } else if (work_kind == "open" && active_schedule()) count.error = done.error;
      if (auto* s = switch_work()) {
        switch_failure = done.error.value_or(foundation::Error{
            foundation::ErrorCode::invalid_argument, "Pattern segment was refused"});
        s->status.error = switch_failure;
        if (recorded_serial) count.error = switch_failure;
      }
      // Failed actual opening still needs a real Stop; no successful cancel.
      if (work_kind == "open") {
        opening_failed = true;
        // This exact final refusal is consumed below. Unknown/retryable
        // effects retain their cell above and cannot clear pending opening.
        if (active_schedule()) count.opening_pending = false;
        if (!active_schedule()) phase = PatternTransportPhase::error;
      }
      else if (!work_input) {
        if (work_kind == "prepare" || work_kind == "preflight") {
          if (pending) {
            retained.insert_or_assign(pending->command_id, *pending);
            last_command = pending->command_id;
            last_epoch = pending->expected_epoch;
            pending.reset();
          }
          prepare_needed = false;
          phase = PatternTransportPhase::idle;
        } else phase = PatternTransportPhase::error;
      }
      if (work_kind == "admit" && !work_input && legacy_candidate)
        legacy_result = foundation::Result<PatternAdmissionAdmit>::failure(*done.error);
      if (work_kind == "owner_lost") owner_disposition_refused = true;
    } else {
      error.reset();
      const auto payload = Json::parse(done.payload);
      if (work_kind == "owner_lost") {
        owner_disposed = true;
        // This actual worker completion follows consumption of the original
        // opening cell, including a refused opening. It closes pending work;
        // it never invents opening_complete, F, or a successful take.
        count.opening_pending = false;
        recording = false;
        schedule_settled = true;
        pending.reset();
        for (auto& h : holds) if (h) {
          h->metadata = false;
          if (h->release_consumed) h.reset();
        }
        for (auto& i : inputs) if (i && i->waiting_cutoff) {
          i->waiting_cutoff = false;
          settle_input(*i, false);
        }
        error = owner_failure;
        phase = PatternTransportPhase::error;
        for (auto& s : switches) if (s && !s->status.durable_settled) {
          s->status.owner_disposed = true;
          s->status.error = owner_failure;
          refresh_switch(*s);
        }
      } else if (work_kind == "prepare" || work_kind == "preflight") {
        prepared = true;
        prepared_revision = payload.at("revision").get<std::uint64_t>();
        prepare_needed = false;
      } else if (work_kind == "open") {
        const auto original = Json::parse(work_request->payload);
        durable_pattern = foundation::PatternId{original.at("fence").at("pattern").get<std::string>()};
        durable_generation = original.at("fence").at("generation").get<std::uint64_t>();
        opening_done = true;
        if (active_schedule()) {
          count.opening_pending = false;
          count.opening_complete = true;
          recording = true;
          recording_request = count.request->transport;
        }
        else {
          recorded_epoch = pending->expected_epoch;
          recorded_serial = 0;
          recording_request = *pending;
          if (receipt && !audio.acknowledge(config.runtime_generation, receipt->epoch)) {
            error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern receipt acknowledgment failed"};
            phase = PatternTransportPhase::error;
          } else {
            if (receipt) acknowledged_pattern_generation = receipt->pattern_generation;
            recording = true;
            finish_request();
          }
        }
        if (recording) { projection_dirty = true; ++projection_revision; }
      } else if (work_kind == "activate") {
        const auto original = Json::parse(work_request->payload);
        durable_pattern = foundation::PatternId{original.at("fence").at("pattern").get<std::string>()};
        durable_generation = original.at("fence").at("generation").get<std::uint64_t>();
        recording = true;
        projection_dirty = true;
        ++projection_revision;
        if (receipt && !audio.acknowledge(config.runtime_generation, receipt->epoch)) {
          error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern receipt acknowledgment failed"};
          phase = PatternTransportPhase::error;
        } else {
          if (receipt) acknowledged_pattern_generation = receipt->pattern_generation;
          finish_request();
        }
      } else if (work_kind == "segment") {
        if (auto* s = switch_work()) {
          s->status.durable_settled = true;
          s->status.error.reset();
          durable_pattern = s->status.pattern_id;
          durable_generation = s->status.publication->generation;
          refresh_switch(*s);
          // Every recorded hold still owning metadata is in the departed
          // source: post-S press authoring was parked behind this exact ACK.
          for (auto& h : holds) if (h && h->recorded) {
            h->metadata = false;
            if (h->release_consumed) h.reset();
          }
          for (auto& i : inputs) if (i && i->waiting_cutoff) {
            i->waiting_cutoff = false;
            settle_input(*i, false);
          }
          projection_available = false;
          projection_dirty = true;
          ++projection_revision;
          projection_offset = 0;
          projection_chunks.clear();
          projection_chunk_pattern.reset();
          published_projection = unlanded_overlay = 0;
        }
      } else if (work_kind == "admit") {
        if (!work_input && legacy_candidate) {
          legacy_result = foundation::Result<PatternAdmissionAdmit>::success(payload.at("retained").get<bool>() ? PatternAdmissionAdmit::retained : PatternAdmissionAdmit::live_only);
          if (payload.at("retained").get<bool>()) {
            projection_dirty = true;
            ++projection_revision;
          }
        }
        for (auto& i : inputs) if (i && i->status.ticket.ticket == work_input) {
          i->status.error.reset();
          settle_input(*i, payload.at("retained").get<bool>());
        }
      } else if (work_kind == "cutoff") {
        cutoff_done = true;
        phase = PatternTransportPhase::flushing;
      } else if (work_kind == "close") {
        // Retain the exact real request/F pair whose close actually completed.
        // A later physical-owner disposition may use this whole identity;
        // it never combines the recording's CommandId with another epoch.
        if (pending && close_cutoff) {
          closed_owner_request = *pending;
          closed_owner_cutoff = *close_cutoff;
        }
        recording = false;
        for (auto& h : holds) if (h) {
          h->metadata = false;
          if (h->release_consumed) h.reset();
        }
        for (auto& i : inputs) if (i && i->waiting_cutoff) {
          i->waiting_cutoff = false;
          settle_input(*i, false);
        }
        cutoff_done = false;
        closing = false;
        // Content generations span the controller lifetime, including a
        // later recording on a different Pattern with identical events.
        projection_available = false;
        projection_dirty = false;
        projection_offset = 0;
        projection_chunks.clear();
        unlanded_overlay = published_projection = 0;
        finish_request();
        schedule_settled = true;
      } else if (work_kind == "project") {
        if (!payload.at("projection").is_null()) {
          const auto& p = payload.at("projection");
          const auto pattern = foundation::PatternId{p.at("pattern").get<std::string>()};
          const auto offset = payload.at("offset").get<std::size_t>();
          if (offset == 0) { projection_chunks.clear(); projection_chunk_pattern = pattern; }
          if (offset != projection_chunks.size() || projection_chunk_pattern != pattern) {
            error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern projection chunk lineage changed"};
            phase = PatternTransportPhase::error;
          } else {
            for (const auto& e : p.at("events")) projection_chunks.emplace_back(
                domain::PadSlotId{e.at("bank").get<std::uint8_t>(), e.at("pad").get<std::uint8_t>()},
                e.at("tick").get<std::uint32_t>(), e.at("duration").get<std::uint32_t>(),
                e.at("velocity").get<std::uint8_t>());
            projection_offset = payload.at("next_offset").get<std::size_t>();
            if (payload.at("done").get<bool>()) {
              if (!projection || projection->pattern_id != pattern || projection->events != projection_chunks) {
                const auto generation = projection ? projection->generation + 1 : (projection_chunks.empty() ? 0 : 1);
                projection = PatternTransportOverlayProjection{pattern, generation, std::move(projection_chunks)};
              }
              projection_offset = 0;
              projection_available = true;
              projection_dirty = projection_revision != projecting_revision;
            }
          }
        } else { projection_offset = 0; projection_dirty = false; projection_available = false; }
      } else if (work_kind == "overlay") unlanded_overlay = 0;
    }
    executor.consume(work_request->identity);
    work_request.reset();
    work_kind.clear();
    work_input = 0;
    reconciliation_attempted = false;
    if (owner_invalidated) error = owner_failure;
    else if (done.outcome == PatternTransportWorkOutcome::success && !opening_failed && phase != PatternTransportPhase::error)
      error.reset();
    return true;
  }
  bool acquire_receipt() {
    if (!pending || receipt || prepare_needed || deferred_audio) return receipt.has_value();
    const auto seen = audio.inspect(config.runtime_generation, pending->expected_epoch);
    if (!seen) return false;
    receipt = seen;
    if (withdrawn_overlay && receipt->switch_authority &&
        receipt->switch_authority->generation == withdrawn_overlay->generation &&
        receipt->switch_decision == audio::PatternCutoffDecision::canceled_at_cutoff) {
      receipt->switch_authority.reset();
      receipt->switch_decision = audio::PatternCutoffDecision::none;
    }
    withdrawn_overlay.reset();
    playing = seen->playing;
    origin = seen->origin_frame;
    if (closing) {
      close_cutoff = receipt;
      // Preserve the entire real F receipt before native e2 acknowledgment can
      // consume its ordinary cell through the scheduled companion capability.
      if (!audio.acknowledge(config.runtime_generation, seen->epoch)) {
        error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern cutoff acknowledgment failed"};
        phase = PatternTransportPhase::error;
      } else acknowledged_pattern_generation = seen->pattern_generation;
    }
    return true;
  }
  bool drive_schedule(bool opening_guard_busy_this_drive = false) {
    if (!active_schedule()) return true;
    const auto native = scheduled->inspect_scheduled(config.runtime_generation, count.request->schedule_serial);
    if (!native) return true;
    if (native->runtime_generation != config.runtime_generation ||
        native->frame_epoch != count.request->frame_epoch || native->serial != count.request->schedule_serial)
      return false;
    if (native->start_receipt) {
      const auto& r = *native->start_receipt;
      if (r.runtime_generation != config.runtime_generation || r.frame_epoch != count.request->frame_epoch ||
          r.serial != count.request->schedule_serial || r.epoch != count.request->transport.expected_epoch ||
          r.pattern_id != scheduled_pattern || r.pattern_generation != scheduled_generation)
        return false;
      count.start_receipt = r;
    }
    if (native->cancel_receipt) {
      const auto& r = *native->cancel_receipt;
      if (!cancel || r.runtime_generation != config.runtime_generation || r.frame_epoch != cancel->frame_epoch ||
          r.serial != cancel->schedule_serial || r.epoch != cancel->transport.expected_epoch ||
          r.pattern_id != scheduled_pattern || r.pattern_generation != scheduled_generation) return false;
      count.cancel_receipt = r;
      if (r.result == audio::ScheduledPatternResult::refused && !r.effective_frame && !r.origin_frame &&
          count.start_receipt && count.start_receipt->result == audio::ScheduledPatternResult::applied) {
        owner_invalidated = true;
        playing = false;
        count.error = foundation::Error{foundation::ErrorCode::invalid_argument,
            shutdown_recording_cutoff && opening_done
                ? "Pattern recording owner was invalidated without a real cutoff"
                : "Scheduled Record owner was invalidated without a real cutoff",
            {{"reason", shutdown_recording_cutoff && opening_done
                ? "pattern_transport_owner_invalidated" : "scheduled_record_owner_invalidated"},
             {"journal_retained", true},
             {"remedy", "drain the owner and recover its retained admission"}}};
        owner_failure = count.error;
        error = count.error;
        phase = PatternTransportPhase::error;
        if (pending && *pending == cancel->transport && deferred_audio &&
            !receipt && !close_cutoff) {
          // Native refused the original UNSENT e2. Retire only its local
          // deferred cutoff, keeping e1 as the authoring epoch and retaining
          // both original requests/receipts and their owner-loss evidence.
          // finish_request() would incorrectly spend this refused e2.
          pending.reset();
          closing = false;
          deferred_audio = false;
          deferred_attempts = 0;
          withdrawn_overlay.reset();
        }
      }
    }
    count.count_in = *native;
    if (count.start_receipt && count.start_receipt->result == audio::ScheduledPatternResult::refused) {
      count.error = foundation::Error{foundation::ErrorCode::invalid_argument, "Scheduled Record was refused by native audio"};
      error = count.error;
      phase = PatternTransportPhase::error;
      count.opening_pending = false;
      if (!start_acknowledged) start_acknowledged = scheduled->acknowledge_scheduled(
          config.runtime_generation, count.request->schedule_serial, count.request->transport.expected_epoch);
      if (cancel && count.cancel_receipt && !cancel_acknowledged)
        cancel_acknowledged = scheduled->acknowledge_scheduled(config.runtime_generation,
            count.request->schedule_serial, cancel->transport.expected_epoch);
      if (start_acknowledged && (!cancel || cancel_acknowledged)) {
        schedule_settled = true;
        retained.insert_or_assign(count.request->transport.command_id, count.request->transport);
        if (cancel) retained.insert_or_assign(cancel->transport.command_id, cancel->transport);
        last_epoch = cancel ? cancel->transport.expected_epoch : count.request->transport.expected_epoch;
        last_command = cancel ? cancel->transport.command_id : count.request->transport.command_id;
      }
      return false;
    }
    if (count.start_receipt && count.start_receipt->result == audio::ScheduledPatternResult::cancelled) {
      if (!start_acknowledged) start_acknowledged = scheduled->acknowledge_scheduled(
          config.runtime_generation, count.request->schedule_serial, count.request->transport.expected_epoch);
      if (cancel && count.cancel_receipt && !cancel_acknowledged)
        cancel_acknowledged = scheduled->acknowledge_scheduled(config.runtime_generation,
            count.request->schedule_serial, cancel->transport.expected_epoch);
      if (start_acknowledged && (!cancel || cancel_acknowledged)) {
        schedule_settled = true;
        retained.insert_or_assign(count.request->transport.command_id, count.request->transport);
        if (cancel) retained.insert_or_assign(cancel->transport.command_id, cancel->transport);
        last_epoch = cancel ? cancel->transport.expected_epoch : count.request->transport.expected_epoch;
        last_command = cancel ? cancel->transport.command_id : count.request->transport.command_id;
        phase = PatternTransportPhase::idle;
      }
      return true;
    }
    if (!count.start_receipt || count.start_receipt->result != audio::ScheduledPatternResult::applied)
      return true;
    const auto& started = *count.start_receipt;
    if (!started.effective_frame || !started.origin_frame || !native->start_frame ||
        *started.effective_frame != *native->start_frame || *started.origin_frame != *native->start_frame) {
      error = foundation::Error{foundation::ErrorCode::invalid_argument, "Scheduled Record missing exact S fence"};
      count.error = error;
      return false;
    }
    if (!owner_invalidated) playing = true;
    origin = switch_origin.value_or(*started.origin_frame);
    if (!opening_started) {
      closed_owner_request.reset();
      closed_owner_cutoff.reset();
      opening_started = std::chrono::steady_clock::now();
      count.opening_pending = true;
      recorded_epoch = started.epoch;
      recorded_serial = started.serial;
    }
    const auto opening_decision = opening_guard_decision();
    const bool allow_synthetic_cutoff = !opening_guard_busy_this_drive &&
        opening_decision != OpeningGuardDecision::busy;
    reconcile_opening_timer(opening_decision);
    if (opening_failed && !cancel && !owner_invalidated && allow_synthetic_cutoff) {
      auto cutoff = count.request->transport;
      cutoff.command_id = derive_command(cutoff.command_id, 5, 'e');
      if (cutoff.expected_epoch != UINT64_MAX) {
        ++cutoff.expected_epoch;
        cutoff.intent = PatternTransportIntent::play_stop;
        cancel_request({cutoff, count.request->frame_epoch, count.request->schedule_serial});
      }
    }
    // Opening completion does not end the recording's native lineage: a
    // later Record-off or Stop must still register its genuine second intent.
    if (!start_acknowledged && cancel) start_acknowledged = scheduled->acknowledge_scheduled(
        config.runtime_generation, started.serial, started.epoch);
    if (cancel && count.cancel_receipt && !cancel_acknowledged) {
      const bool actual_cutoff = count.cancel_receipt->result == audio::ScheduledPatternResult::applied;
      if (!actual_cutoff || acquire_receipt())
        cancel_acknowledged = scheduled->acknowledge_scheduled(config.runtime_generation,
            started.serial, cancel->transport.expected_epoch);
    }
    if (close_cutoff) { playing = close_cutoff->playing; origin = close_cutoff->origin_frame; }
    // Submit e2 before waiting for held opening/append. Its real receipt F is
    // independently retained; authoring settlement waits for ordered ingress.
    if (!owner_invalidated && (cancel || (opening_failed && allow_synthetic_cutoff)) && !pending) {
      auto cutoff = cancel ? cancel->transport : count.request->transport;
      if (!cancel) {
        cutoff.command_id = derive_command(cutoff.command_id, 5, 'e');
        if (cutoff.expected_epoch == UINT64_MAX) return false;
        ++cutoff.expected_epoch;
        cutoff.intent = PatternTransportIntent::play_stop;
      }
      if (submit_audio(cutoff, cutoff.intent == PatternTransportIntent::play_stop
          ? audio::PatternTransportAction::stop : audio::PatternTransportAction::fence)) {
        pending = cutoff;
        closing = true;
        phase = PatternTransportPhase::awaiting_audio;
      }
    }
    if (!opening_done && !opening_failed && !work_request) {
      auto payload = opening(count.request->transport, started.pattern_id, started.pattern_generation,
          "open", *opening_started);
      const project_io::SequenceAdmissionFence f{project_io::SequenceFenceKind::admission,
          count.request->transport.command_id, started.epoch, *started.effective_frame,
          *started.origin_frame, started.pattern_id, started.pattern_generation, native->bpm, true,
          {}, project_io::SequenceSwitchOutcome::none, {}};
      payload["fence"] = encode_transport_fence(f);
      work(std::move(payload), count.request->transport);
    }
    if (opening_started && !opening_done && !opening_failed && allow_synthetic_cutoff &&
        opening_decision == OpeningGuardDecision::expired) {
      count.error = foundation::Error{foundation::ErrorCode::io_error,
          "Scheduled Record opening exceeded its original five-second deadline",
          {{"reason", "pattern_transport_opening_expired"}}};
      opening_failed = true;
    }
    if (opening_done && !cancel && !pending) {
      retained.insert_or_assign(count.request->transport.command_id, count.request->transport);
      last_epoch = count.request->transport.expected_epoch;
      last_command = count.request->transport.command_id;
      phase = PatternTransportPhase::idle;
    }
    return true;
  }
  bool has_ingress() const {
    for (const auto& i : inputs) if (i && !i->status.durable_settled && !i->waiting_cutoff) return true;
    return false;
  }
  enum class OpeningGuardDecision { busy, in_time, pending, expired };
  OpeningGuardDecision opening_guard_decision() const {
    if (!opening_publication) {
      // Legacy/direct test construction has no worker proof companion. Keep
      // its original fail-closed timer; production factories supply a guard.
      return opening_started && std::chrono::steady_clock::now() - *opening_started >=
          kScheduledPatternOpeningDeadline ? OpeningGuardDecision::expired : OpeningGuardDecision::pending;
    }
    std::unique_lock lock(opening_publication->guard, std::try_to_lock);
    if (!lock.owns_lock()) return OpeningGuardDecision::busy;
    const auto& known = opening_publication->successful;
    if (known && work_request && (work_kind == "open" || work_kind == "activate") &&
        known->request == *work_request &&
        (!opening_started || known->completed_at - *opening_started < kScheduledPatternOpeningDeadline))
      return OpeningGuardDecision::in_time;
    // No later clock read may turn this guarded pending decision into expiry.
    // Both the owner and control use the same fixed production steady clock.
    if (opening_started && std::chrono::steady_clock::now() - *opening_started >=
        kScheduledPatternOpeningDeadline) return OpeningGuardDecision::expired;
    return OpeningGuardDecision::pending;
  }
  void reconcile_opening_timer(OpeningGuardDecision decision) {
    // An observer timeout is provisional until a real second intent exists.
    // It cannot replace earlier exact worker evidence, nor revoke a real e2.
    if (!opening_failed || cancel || closing || owner_invalidated || !count.error ||
        count.error->details.value("reason", std::string{}) != "pattern_transport_opening_expired" ||
        decision != OpeningGuardDecision::in_time) return;
    opening_failed = false;
    count.error.reset();
    if (error && error->details.value("reason", std::string{}) == "pattern_transport_opening_expired")
      error.reset();
  }
  bool has_unacknowledged_inputs() const {
    for (const auto& s : switches) if (s) return true;
    if (legacy_candidate || legacy_result) return true;
    for (const auto& i : inputs) if (i) return true;
    // A real native owner-loss disposition settles the authoring owner only;
    // its independent native holds still belong to the native teardown path.
    if (!owner_invalidated || !owner_disposed)
      for (const auto& h : holds) if (h) return true;
    return false;
  }
  void drive_inputs() {
    if (work_request) return;
    Input* first = nullptr;
    for (auto& i : inputs) if (i && i->status.admission && !i->status.durable_settled && !i->waiting_cutoff &&
        (!first || i->status.admission->acceptance_ordinal < first->status.admission->acceptance_ordinal))
      first = &*i;
    if (!first || !first->status.native_result) return;
    auto& i = *first;
    const auto disposition = i.status.native_result->disposition;
    const bool native_failed = disposition == audio::PatternInputDisposition::voice_capacity ||
        disposition == audio::PatternInputDisposition::invalidated_before_consume;
    if (native_failed) {
      i.status.error = foundation::Error{foundation::ErrorCode::invalid_argument,
          "Accepted Pattern input failed at native consumption"};
      if (!i.request.pressed) {
        if (auto* h = hold(i.request.correlation); h && h->recorded && h->metadata) {
          i.waiting_cutoff = true;
          return;
        }
      }
      settle_input(i, false);
      return;
    }
    if (owner_invalidated && switch_failure) {
      settle_input(i, false);
      return;
    }
    bool eligible = recorded_serial
        ? i.status.admission->authority.recording &&
          i.status.admission->authority.transport_epoch == recorded_epoch &&
          i.status.admission->authority.schedule_serial == recorded_serial
        : recording_request && i.request.runtime_frame >= ordinary_start_frame;
    if (!i.request.pressed) {
      const auto* h = hold(i.request.correlation);
      eligible = h && h->recorded && h->metadata;
    }
    if (eligible && opening_failed && !opening_done) {
      i.status.error = count.error ? count.error : error;
      settle_input(i, false);
      return;
    }
    if (!eligible || (close_cutoff && i.request.runtime_frame >= close_cutoff->effective_frame)) {
      settle_input(i, false);
      return;
    }
    if (!recording || (active_schedule() && !opening_done)) return;
    if (switch_blocks_input(i.request.runtime_frame)) return;
    const auto& native = *i.status.admission;
    const auto request = count.request && recorded_serial ? count.request->transport
        : recording_request.value();
    Json payload{{"op", "admit"}, {"candidate", {
        {"watermark", native.acceptance_ordinal + 9}, {"frame", i.request.runtime_frame},
        {"bank", i.request.slot.bank}, {"pad", i.request.slot.pad},
        {"pressed", i.request.pressed}, {"velocity", i.request.velocity},
        {"correlation", i.request.pressed ? native.sequence : i.request.correlation}}}};
    if (native.acceptance_ordinal > UINT64_MAX - 9) {
      i.status.error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern input watermark exhausted"};
      settle_input(i, false);
      return;
    }
    i.submitted = work(std::move(payload), request, i.status.ticket.ticket);
  }
  Void drive() {
    const bool parked_error = phase == PatternTransportPhase::error;
    expire_inputs();
    bool opening_guard_busy = false;
    // Consume an already delivered opening before consulting its timer. A
    // held delivery uses the exact private durability companion below; neither
    // path postpones acquisition of genuine Native e1/e2 receipts.
    if (work_request && (work_kind == "open" || work_kind == "activate")) poll_work(&opening_guard_busy);
    // Native receipts must be acquired even when the worker is stalled.
    if (!drive_schedule(opening_guard_busy)) {
      if (!count.error) count.error = foundation::Error{foundation::ErrorCode::invalid_argument,
          "Scheduled Pattern receipt identity did not match its retained request",
          {{"reason", "scheduled_pattern_receipt_identity_mismatch"}}};
      error = count.error;
      phase = PatternTransportPhase::error;
    }
    if (pending && deferred_audio) {
      audio::PatternTransportCommand command{config.runtime_generation, pending->expected_epoch,
          audio.pattern_generation(), deferred_action, withdrawn_overlay};
      auto submitted = audio.submit(command);
      if (submitted == audio::PatternTransportSubmit::identity_mismatch) {
        command.pending_switch.reset();
        submitted = audio.submit(command);
      }
      if (submitted == audio::PatternTransportSubmit::identity_mismatch && ++deferred_attempts < 64)
        return Void::success();
      deferred_audio = false;
      deferred_attempts = 0;
      if (submitted != audio::PatternTransportSubmit::accepted) {
        withdrawn_overlay.reset();
        // A real stop can invalidate the retained scheduled intent during
        // this submit turn. Copy that Native refusal before ordinary cleanup
        // and never replace an established terminal owner-loss failure.
        if (submitted == audio::PatternTransportSubmit::not_running && active_schedule() && cancel) {
          const auto stopped = scheduled->inspect_scheduled(config.runtime_generation, cancel->schedule_serial);
          if (stopped && stopped->cancel_receipt &&
              stopped->cancel_receipt->result == audio::ScheduledPatternResult::refused &&
              !stopped->cancel_receipt->effective_frame && !stopped->cancel_receipt->origin_frame)
            drive_schedule(opening_guard_busy);
        }
        pending.reset();
        closing = false;
        if (owner_invalidated) {
          error = owner_failure;
          phase = PatternTransportPhase::error;
        } else {
          error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern transport audio submit refused"};
          phase = PatternTransportPhase::idle;
        }
        return Void::failure(*error);
      }
    }
    acquire_receipt();
    if (!poll_work(&opening_guard_busy)) return Void::success();
    if (shutdown && switch_failure) {
      owner_invalidated = true;
      owner_failure = switch_failure;
      error = switch_failure;
      phase = PatternTransportPhase::error;
    }
    if (executor.inspect().startup_error) {
      error = executor.inspect().startup_error;
      phase = PatternTransportPhase::error;
      return Void::failure(*error);
    }
    if (prepare_needed && pending && !work_request) {
      const auto observation = receipt_bound ? audio.observe_transport() : std::nullopt;
      if (receipt_bound && (!observation || !observation->current_pattern ||
          !observation->current_generation)) return Void::success();
      const auto target = observation ? *observation->current_pattern
          : audio.current_pattern().value_or(config.pattern);
      const auto generation = observation ? observation->current_generation
          : audio.pattern_generation();
      auto payload = opening(*pending, target, generation,
          receipt_bound ? "preflight" : "prepare", prepare_started);
      if (observation) {
        payload["targets"] = Json::array();
        for (const auto& authority : observation->pending_switches)
          if (authority) payload["targets"].push_back(authority->pattern_id.value());
      }
      work(std::move(payload), *pending);
      return Void::success();
    }
    retire_failed_preparation();
    if (prepared && pending && !receipt && phase == PatternTransportPhase::preparing) {
      if (submit_audio(*pending, playing ? audio::PatternTransportAction::fence
                                       : audio::PatternTransportAction::start)) {
        prepared = false;
        recording_request = *pending;
        phase = PatternTransportPhase::awaiting_audio;
      } else if (audio_submit_result != audio::PatternTransportSubmit::busy) {
        phase = PatternTransportPhase::error;
        if (audio_submit_result == audio::PatternTransportSubmit::not_running &&
            pending->intent == PatternTransportIntent::record && !recording &&
            !active_schedule() && error) {
          failed_preparation = FailedPreparation{*pending, *error};
          retire_failed_preparation();
        }
      }
      return Void::success();
    }
    if (!shutdown && phase == PatternTransportPhase::error && !active_schedule() && !owner_invalidated)
      return !parked_error && error ? Void::failure(*error) : Void::success();
    if (receipt && pending && !closing && !work_request) {
      if (pending->intent == PatternTransportIntent::record) {
        closed_owner_request.reset();
        closed_owner_cutoff.reset();
        recorded_epoch = pending->expected_epoch;
        recorded_serial = 0;
        ordinary_start_frame = receipt->effective_frame;
        // Keep old F through the closed/preparing interval for late input.
        // This genuine new start now owns the active recording boundary.
        close_cutoff.reset();
        cutoff_done = false;
        auto f = fence(*receipt, *pending, project_io::SequenceFenceKind::admission);
        if (receipt_bound) {
          f.switch_authority.reset();
          f.switch_outcome = project_io::SequenceSwitchOutcome::none;
          f.switch_applied_frame.reset();
          auto payload = opening(*pending, receipt->pattern_id, receipt->pattern_generation, "open", prepare_started);
          payload["revision"] = prepared_revision;
          payload["fence"] = encode_transport_fence(f);
          work(std::move(payload), *pending);
        } else work({{"op", "activate"}, {"fence", encode_transport_fence(f)}}, *pending);
      } else {
        if (!audio.acknowledge(config.runtime_generation, receipt->epoch)) {
          error = foundation::Error{foundation::ErrorCode::invalid_argument, "Pattern receipt acknowledgment failed"};
          phase = PatternTransportPhase::error;
          return Void::failure(*error);
        }
        acknowledged_pattern_generation = receipt->pattern_generation;
        finish_request();
      }
      return Void::success();
    }
    drive_legacy_input();
    drive_inputs();
    drive_switches();
    if (closing && pending && close_cutoff && !work_request && !has_ingress() &&
        (!legacy_candidate || legacy_result) && !unsettled_switches()) {
      if (opening_failed && !opening_done) {
        // A refused opening has no admitted prefix. Preserve failed e1 and
        // actual native e2, and leave any uncertain journal for owner recovery.
        if (active_schedule()) count.error = error ? error : count.error;
        finish_request();
        schedule_settled = true;
      } else if (!cutoff_done) {
        work({{"op", "cutoff"}, {"fence", encode_transport_fence(fence(*close_cutoff,
            *pending, project_io::SequenceFenceKind::cutoff))},
            {"overlay", unlanded_overlay && close_cutoff->pattern_generation == unlanded_overlay
                ? unlanded_overlay : 0}}, *pending);
      } else work({{"op", "close"}, {"switched", close_cutoff->switch_decision ==
          audio::PatternCutoffDecision::applied_before_cutoff}}, *pending);
    }
    if (!pending && recording && !work_request && !has_ingress() && !owner_invalidated) publish();
    if (shutdown && owner_invalidated && !owner_disposed && !work_request && !has_ingress()) {
      if (resource_owner_disposition) {
        if (!owner_disposition_refused) work_owner_disposition();
      } else if (closed_owner_disposition) {
        if (!owner_disposition_refused) work({{"op", "owner_lost"}}, *closed_owner_request);
      } else if (failed_preparation) {
        if (!owner_disposition_refused) work({{"op", "owner_lost"}}, failed_preparation->request);
      } else if (recording_request || count.request)
        work({{"op", "owner_lost"}}, recording_request ? *recording_request : count.request->transport);
    }
    if (shutdown && !work_request && !pending && !has_ingress() && !has_unacknowledged_inputs() &&
        (!owner_invalidated || owner_disposed)) executor.request_shutdown();
    return error ? Void::failure(*error) : Void::success();
  }
  Void publish() {
    if (!recording || closing || pending || owner_invalidated || unsettled_switches() ||
        (active_schedule() && !opening_done)) return Void::success();
    if (unlanded_overlay) {
      const auto queued = audio.pending_switch();
      if (queued && queued->generation == unlanded_overlay) return Void::success();
      if (audio.pattern_generation() == unlanded_overlay && !work_request)
        work({{"op", "overlay"}, {"generation", unlanded_overlay}}, *recording_request);
      else unlanded_overlay = 0;
      return Void::success();
    }
    if (projection_dirty && !work_request) {
      if (projection_offset == 0) projecting_revision = projection_revision;
      work({{"op", "project"}, {"offset", projection_offset}}, *recording_request);
      return Void::success();
    }
    if (!projection_available || !projection || projection->generation == published_projection || audio.pending_switch()) return Void::success();
    if (refused_projection != projection->generation) {
      refused_projection = projection->generation;
      overlay_refusals = 0;
      settled_refusal = false;
      transient_retry_spent = false;
    }
    if (settled_refusal) {
      if (!refusal_transient || transient_retry_spent) return Void::success();
      transient_retry_spent = true;
      settled_refusal = false;
      overlay_refusals = 0;
    }
    const auto pub = audio.publish_overlay(projection->pattern_id, projection->events);
    if (pub.has_value()) {
      published_projection = projection->generation;
      unlanded_overlay = pub.value().generation;
      overlay_refusals = 0;
      settled_refusal = false;
    } else if (++overlay_refusals >= 3) {
      settled_refusal = true;
      refusal_transient = pub.error().code == foundation::ErrorCode::bank_quota_exhausted;
    }
    return Void::success();
  }
  foundation::Result<PatternTransportInputTicket> reserve(const PatternTransportInputRequest& r) {
    using Result = foundation::Result<PatternTransportInputTicket>;
    if (r.runtime_generation != config.runtime_generation || !r.frame_epoch ||
        !domain::is_valid_uuid(r.command_id.value()) || r.slot.bank >= 4 || r.slot.pad >= 16 ||
        (!r.pressed && (!r.correlation || r.velocity != 0)) ||
        (r.pressed && (!r.velocity || r.velocity > 127)))
      return Result::failure({foundation::ErrorCode::invalid_argument, "Invalid Pattern input reservation"});
    for (const auto& i : inputs) if (i && i->request.command_id == r.command_id)
      return i->request == r ? Result::success(i->status.ticket)
          : Result::failure({foundation::ErrorCode::invalid_argument, "Pattern input replay changed payload"});
    if (owner_acknowledged || (shutdown && r.pressed))
      return Result::failure({foundation::ErrorCode::invalid_argument, "Pattern input owner is shutting down"});
    const bool release = !r.pressed;
    Hold* h = release ? hold(r.correlation) : nullptr;
    if (release && (!h || h->slot != r.slot || h->release_reserved))
      return Result::failure({foundation::ErrorCode::invalid_argument, "Pattern input release has no matching reserved hold"});
    if (next_ticket == UINT64_MAX) return Result::failure({foundation::ErrorCode::invalid_argument, "Pattern input tickets exhausted"});
    std::optional<std::size_t> cell;
    const auto begin = release ? kPatternTransportIngressCapacity : 0;
    const auto end = release ? inputs.size() : kPatternTransportIngressCapacity;
    for (auto n = begin; n != end; ++n) if (!inputs[n]) { cell = n; break; }
    std::optional<std::size_t> hold_cell;
    if (r.pressed && r.held) for (std::size_t n = 0; n != holds.size(); ++n)
      if (!holds[n]) { hold_cell = n; break; }
    if (!cell || (r.pressed && r.held && !hold_cell)) return Result::failure(busy("pattern_transport_metadata_full"));
    const PatternTransportInputTicket ticket{config.runtime_generation, r.command_id, ++next_ticket};
    inputs[*cell] = Input{r, PatternTransportInputStatus{ticket, {}, {}, false, false, false, false, {}},
        std::chrono::steady_clock::now(), false, release, false};
    const auto started = inputs[*cell]->started;
    if (!earliest_unexpired_input_started || started < *earliest_unexpired_input_started)
      earliest_unexpired_input_started = started;
    if (hold_cell) holds[*hold_cell] = Hold{0, r.slot, false, true, false, ticket.ticket, false};
    if (h) h->release_reserved = true;
    return Result::success(ticket);
  }
  bool bind(const PatternTransportInputTicket& ticket, const audio::PatternInputAdmission& admission) {
    auto* i = find(ticket);
    if (!i || admission.result != audio::PatternInputSubmit::accepted || !admission.sequence ||
        !admission.acceptance_ordinal) return false;
    if (i->status.admission) return i->status.admission->sequence == admission.sequence &&
        i->status.admission->acceptance_ordinal == admission.acceptance_ordinal &&
        i->status.admission->authority == admission.authority;
    for (const auto& cell : inputs) if (cell && cell->status.admission &&
        (cell->status.admission->sequence == admission.sequence ||
         cell->status.admission->acceptance_ordinal == admission.acceptance_ordinal)) return false;
    i->status.admission = admission;
    if (i->request.pressed && i->request.held) {
      for (auto& h : holds) if (h && !h->sequence && h->ticket == ticket.ticket) {
        h->sequence = admission.sequence;
        if (!input_owner_identity)
          input_owner_identity = PatternTransportWorkIdentity{config.runtime_generation, 0,
              ticket.command_id, 0}; // Actual accepted input identity, no recording authority.
        break;
      }
    }
    return true;
  }
  bool complete(const audio::PatternInputCompletion& result) {
    for (auto& i : inputs) if (i && i->status.admission && i->status.admission->sequence == result.sequence) {
      if (result.runtime_generation != config.runtime_generation || result.frame_epoch != i->request.frame_epoch ||
          result.acceptance_ordinal != i->status.admission->acceptance_ordinal ||
          result.authority != i->status.admission->authority ||
          result.slot != i->request.slot.bank * 16 + i->request.slot.pad ||
          (!i->request.pressed && result.held_press_sequence != i->request.correlation)) return false;
      if (i->status.native_result) return i->status.native_result->disposition == result.disposition &&
          i->status.native_result->runtime_frame == result.runtime_frame;
      i->status.native_result = result;
      return true;
    }
    return false;
  }
  bool consume(const PatternTransportInputTicket& ticket) {
    for (auto& i : inputs) if (i && i->status.ticket == ticket) {
      if (!i->status.complete || !i->status.durable_settled) return false;
      if (!i->request.pressed) for (auto& h : holds)
        if (h && h->sequence == i->request.correlation) {
          h->release_consumed = true;
          if (!h->metadata) h.reset();
          break;
        }
      // A consumed held press leaves its correlation/release credit intact.
      i.reset();
      return true;
    }
    return false;
  }
  bool abandon(const PatternTransportInputTicket& ticket) {
    for (auto& i : inputs) if (i && i->status.ticket == ticket) {
      if (i->status.admission) return false;
      if (i->request.pressed && i->request.held) {
        for (auto& h : holds) if (h && !h->sequence && h->ticket == ticket.ticket) { h.reset(); break; }
      } else if (auto* h = hold(i->request.correlation)) h->release_reserved = false;
      i.reset();
      return true;
    }
    return false;
  }
  PatternTransportIngressStatus ingress() const {
    PatternTransportIngressStatus result;
    for (const auto& i : inputs) if (i) {
      ++result.retained_tickets;
      if (!i->release_partition && !i->status.durable_settled) ++result.ordinary_pending;
    }
    for (const auto& h : holds) if (h && h->metadata) ++result.held_release_metadata;
    return result;
  }
  PatternTransportInputOwnerStatus input_owner() const {
    PatternTransportInputOwnerStatus result{config.runtime_generation,
        owner_invalidated, owner_disposed, owner_acknowledged,
        work_request.has_value() || pending.has_value() || legacy_candidate.has_value() ||
            legacy_result.has_value() || executor.inspect().ticket.has_value() ||
            active_schedule() || (owner_invalidated && !owner_disposed), 0};
    for (const auto& s : switches) if (s) result.pending = true;
    for (const auto& i : inputs) if (i) result.pending = true;
    for (const auto& h : holds) if (h) ++result.held_correlations;
    return result;
  }
  bool request_owner_disposition(std::uint64_t generation) {
    if (!generation || generation != config.runtime_generation || owner_acknowledged ||
        !shutdown || !scheduled || !scheduled->scheduled_quiescent()) return false;
    if ((resource_owner_disposition || closed_owner_disposition) && (owner_disposed ||
        (work_request && work_kind == "owner_lost"))) return true; // Exact pending/settled replay.
    const bool actually_closed = closed_owner_request && closed_owner_cutoff &&
        closed_owner_request->runtime_generation == config.runtime_generation &&
        closed_owner_request->expected_epoch == closed_owner_cutoff->epoch &&
        closed_owner_cutoff->runtime_generation == config.runtime_generation &&
        !recording && !closing && !count.opening_pending;
    // Recorded/opening owners use their retained real transport disposition.
    // This path has no transport authority and must never create one.
    if ((!actually_closed && (recording_request || recorded_epoch || opening_started ||
            (count.start_receipt && count.start_receipt->result == audio::ScheduledPatternResult::applied))) ||
        prepared || prepare_needed || pending || active_schedule() || work_request || executor.inspect().ticket ||
        legacy_candidate || legacy_result) return false;
    bool known_hold = false;
    for (const auto& i : inputs) if (i) return false;
    for (const auto& h : holds) if (h) {
      if (!h->sequence || (!actually_closed && h->recorded) || h->metadata || h->release_reserved) return false;
      known_hold = true;
    }
    if (!known_hold) return false;
    if (actually_closed) {
      if (!work({{"op", "owner_lost"}}, *closed_owner_request)) return false;
      closed_owner_disposition = true;
    } else {
      if (!input_owner_identity || !work_owner_disposition()) return false;
      resource_owner_disposition = true;
    }
    owner_disposition_refused = false;
    owner_invalidated = true;
    playing = false;
    owner_failure = foundation::Error{foundation::ErrorCode::invalid_argument,
        "Pattern input owner was explicitly revoked after authoring settlement",
        {{"reason", "pattern_input_owner_revoked"}, {"journal_retained", false}}};
    error = owner_failure;
    phase = PatternTransportPhase::error;
    return true;
  }
  bool acknowledge_owner(std::uint64_t generation) {
    if (!generation || generation != config.runtime_generation || owner_acknowledged ||
        !shutdown || !owner_invalidated || !owner_disposed || !owner_failure ||
        phase != PatternTransportPhase::error || input_owner().pending ||
        !scheduled || !scheduled->scheduled_quiescent()) return false;
    for (const auto& h : holds) if (h && (!h->sequence || h->metadata ||
        (h->release_reserved && !h->release_consumed))) return false;
    // No accepted input or Release is consumed here. Only the independent
    // future correlation remains, after both real owners and consumers settled.
    for (auto& h : holds) h.reset();
    owner_acknowledged = true;
    return true;
  }

  PatternTransportAudioPort& audio;
  PatternTransportExecutor& executor;
  PatternTransportControllerConfig config;
  ScheduledPatternTransportAudioPort* scheduled{};
  std::shared_ptr<PatternTransportOpeningPublication> opening_publication;
  ScheduledPatternTransportStatus count;
  std::optional<foundation::PatternId> scheduled_pattern;
  std::uint64_t scheduled_generation{};
  std::optional<ScheduledPatternTransportCancel> cancel;
  bool schedule_settled{true}, cancel_lost{}, start_acknowledged{}, cancel_acknowledged{};
  bool opening_done{}, opening_failed{}, shutdown{}, owner_invalidated{}, owner_disposed{};
  bool shutdown_recording_cutoff{};
  bool owner_acknowledged{};
  bool resource_owner_disposition{}, closed_owner_disposition{}, owner_disposition_refused{};
  std::optional<PatternTransportWorkIdentity> input_owner_identity;
  std::optional<std::chrono::steady_clock::time_point> opening_started;
  std::chrono::steady_clock::time_point prepare_started;
  bool playing{}, recording{}, closing{}, prepare_needed{}, prepared{}, cutoff_done{}, receipt_bound{};
  std::uint64_t origin{}, last_epoch{}, next_step{}, next_ticket{}, prepared_revision{};
  std::uint64_t acknowledged_pattern_generation{};
  std::uint64_t recorded_epoch{}, recorded_serial{}, ordinary_start_frame{}, unlanded_overlay{}, published_projection{};
  std::optional<foundation::CommandId> last_command;
  std::optional<foundation::Error> error;
  std::optional<foundation::Error> owner_failure;
  std::array<std::optional<Switch>, kPatternTransportSwitchCapacity> switches;
  std::uint64_t next_switch_ticket{}, durable_generation{}, observed_switch_generation{};
  std::optional<foundation::PatternId> durable_pattern;
  std::optional<std::uint64_t> switch_origin;
  std::optional<foundation::Error> switch_failure;
  struct FailedPreparation {
    PatternTransportRequest request;
    foundation::Error error;
  };
  std::optional<FailedPreparation> failed_preparation;
  audio::PatternTransportSubmit audio_submit_result{audio::PatternTransportSubmit::accepted};
  PatternTransportPhase phase{PatternTransportPhase::idle};
  std::optional<PatternTransportRequest> pending, recording_request;
  std::optional<PatternTransportRequest> closed_owner_request;
  std::optional<audio::PatternTransportReceipt> closed_owner_cutoff;
  std::map<foundation::CommandId, PatternTransportRequest> retained;
  std::optional<audio::PatternTransportReceipt> receipt, close_cutoff;
  std::optional<audio::PatternReplacementAuthority> withdrawn_overlay;
  bool deferred_audio{};
  unsigned deferred_attempts{}, overlay_refusals{};
  audio::PatternTransportAction deferred_action{};
  std::uint64_t refused_projection{};
  bool settled_refusal{}, refusal_transient{}, transient_retry_spent{};
  std::optional<PatternTransportWorkRequest> work_request;
  std::string work_kind;
  std::uint64_t work_input{};
  bool reconciliation_attempted{};
  std::array<std::optional<Input>, 2 * kPatternTransportIngressCapacity> inputs;
  // Advisory slot only: every hit revalidates the complete ticket on serialized control.
  std::size_t last_input_index{2 * kPatternTransportIngressCapacity};
  // A removed or completed cell may leave an earlier hint; it only causes an extra scan.
  std::optional<std::chrono::steady_clock::time_point> earliest_unexpired_input_started;
  std::array<std::optional<Hold>, kPatternTransportIngressCapacity> holds;
  std::optional<PatternTransportOverlayProjection> projection;
  bool projection_available{};
  bool projection_dirty{};
  std::uint64_t projection_revision{}, projecting_revision{};
  std::size_t projection_offset{};
  std::optional<foundation::PatternId> projection_chunk_pattern;
  std::vector<domain::PatternEvent> projection_chunks;
  std::optional<project_io::SequenceAdmissionCandidate> legacy_candidate;
  std::optional<foundation::Result<PatternAdmissionAdmit>> legacy_result;
};

PatternTransportCoordinator::PatternTransportCoordinator(PatternTransportAudioPort& audio,
    PatternTransportExecutor& executor, PatternTransportControllerConfig config,
    ScheduledPatternTransportAudioPort* scheduled,
    std::shared_ptr<PatternTransportOpeningPublication> opening)
    : async_(std::make_unique<Async>(audio, executor, config, scheduled, std::move(opening))), audio_(audio),
      bundle_(config.bundle), session_(config.session), project_(config.project),
      pattern_(config.pattern), runtime_generation_(config.runtime_generation) {}
PatternTransportCoordinator::~PatternTransportCoordinator() = default;
PatternTransportSubmit PatternTransportCoordinator::request_count_in(const ScheduledPatternTransportRequest& r) {
  return async_ ? async_->count_request(r) : PatternTransportSubmit::refused;
}
ScheduledPatternTransportStatus PatternTransportCoordinator::inspect_count_in() const {
  return async_ ? async_->count : ScheduledPatternTransportStatus{};
}
PatternTransportSubmit PatternTransportCoordinator::cancel_count_in(const ScheduledPatternTransportCancel& r) {
  return async_ ? async_->cancel_request(r) : PatternTransportSubmit::refused;
}
foundation::Result<PatternTransportInputTicket> PatternTransportCoordinator::reserve_input(const PatternTransportInputRequest& r) {
  return async_ ? async_->reserve(r) : foundation::Result<PatternTransportInputTicket>::failure(
      {foundation::ErrorCode::unsupported_audio, "Pattern input tickets require the production I/O owner"});
}
bool PatternTransportCoordinator::bind_input(const PatternTransportInputTicket& t, const audio::PatternInputAdmission& a) {
  return async_ && async_->bind(t, a);
}
bool PatternTransportCoordinator::complete_input(const audio::PatternInputCompletion& c) { return async_ && async_->complete(c); }
std::optional<PatternTransportInputStatus> PatternTransportCoordinator::inspect_input(const PatternTransportInputTicket& t) const {
  if (async_) if (const auto* i = async_->find(t)) {
    auto status = i->status;
    status.expired = status.expired || (!status.complete &&
        std::chrono::steady_clock::now() - i->started >= kPatternTransportInputDeadline);
    return status;
  }
  return std::nullopt;
}
bool PatternTransportCoordinator::consume_input(const PatternTransportInputTicket& t) { return async_ && async_->consume(t); }
bool PatternTransportCoordinator::abandon_input(const PatternTransportInputTicket& t) { return async_ && async_->abandon(t); }
PatternTransportIngressStatus PatternTransportCoordinator::inspect_ingress() const { return async_ ? async_->ingress() : PatternTransportIngressStatus{}; }
PatternTransportInputOwnerStatus PatternTransportCoordinator::inspect_input_owner() const {
  return async_ ? async_->input_owner() : PatternTransportInputOwnerStatus{};
}
bool PatternTransportCoordinator::acknowledge_input_owner(std::uint64_t generation) {
  return async_ && async_->acknowledge_owner(generation);
}
bool PatternTransportCoordinator::request_input_owner_disposition(std::uint64_t generation) {
  return async_ && async_->request_owner_disposition(generation);
}
void PatternTransportCoordinator::request_shutdown() {
  if (!async_ || async_->shutdown) return;
  if (async_->switch_failure) {
    // A failed segment cannot manufacture a terminal F or success. Its actual
    // worker disposition must remain reachable while Native pins are held;
    // the Host separately stops/revokes Native and consumes real outcomes.
    async_->owner_invalidated = true;
    async_->owner_failure = async_->switch_failure;
    async_->error = async_->switch_failure;
  }
  if (!async_->pending && (async_->active_schedule() || async_->playing || async_->recording)) {
    auto request = async_->active_schedule() ? async_->count.request->transport
        : async_->recording_request.value_or(PatternTransportRequest{async_->config.session,
            async_->config.project, foundation::CommandId{"00000000-0000-4000-8000-000000000001"},
            async_->config.runtime_generation, async_->last_epoch, PatternTransportIntent::play_stop, {}});
    request.command_id = derive_command(request.command_id, 7, 'e');
    request.expected_epoch = std::max(request.expected_epoch, async_->last_epoch);
    if (request.expected_epoch != UINT64_MAX) {
      ++request.expected_epoch;
      request.intent = PatternTransportIntent::play_stop;
      // Only this newly accepted shutdown intent changes the owner-loss
      // classification. Preserve an earlier explicit cancel's full failure.
      const bool recording_shutdown = async_->active_schedule() && async_->opening_done &&
          !async_->cancel && !async_->owner_invalidated;
      if (recording_shutdown) async_->shutdown_recording_cutoff = true;
      if (async_->request(request) != PatternTransportSubmit::accepted && recording_shutdown)
        async_->shutdown_recording_cutoff = false;
    }
  }
  if (!async_->owner_invalidated && !async_->pending && async_->recording_request && !async_->closed_owner_request &&
      (async_->audio_submit_result == audio::PatternTransportSubmit::not_running ||
       async_->audio_submit_result == audio::PatternTransportSubmit::disabled ||
       async_->audio_submit_result == audio::PatternTransportSubmit::stale_generation)) {
    // Native owner loss after opening has no F receipt. Explicitly dispose the
    // authoring owner on its thread and preserve its prefix for recovery.
    async_->owner_invalidated = true;
    async_->playing = false;
    async_->owner_failure = foundation::Error{foundation::ErrorCode::invalid_argument,
        "Pattern recording owner was invalidated without a real cutoff",
        {{"reason", "pattern_transport_owner_invalidated"}, {"journal_retained", true}}};
    if (async_->recorded_serial) async_->count.error = async_->owner_failure;
    async_->error = async_->owner_failure;
    async_->phase = PatternTransportPhase::error;
  }
  async_->shutdown = true;
}
bool PatternTransportCoordinator::shutdown_complete() const { return !async_ || async_->executor.inspect().stopped; }
PatternTransportExecutorStatus PatternTransportCoordinator::inspect_io() const { return async_ ? async_->executor.inspect() : PatternTransportExecutorStatus{}; }

foundation::Result<PatternTransportSwitchTicket> PatternTransportCoordinator::reserve_pattern_switch(
    const PatternTransportSwitchRequest& r) {
  if (async_) return async_->reserve_switch(r);
  return foundation::Result<PatternTransportSwitchTicket>::failure(
      {foundation::ErrorCode::unsupported_audio, "Recording switch reservations require the I/O controller"});
}
bool PatternTransportCoordinator::bind_pattern_switch(const PatternTransportSwitchTicket& t,
    const audio::PatternReplacementAuthority& a, std::uint16_t bpm) {
  return async_ && async_->bind_switch(t, a, bpm);
}
bool PatternTransportCoordinator::complete_pattern_switch(const PatternTransportSwitchTicket& t,
    const audio::PatternPublicationObservation& o) {
  return async_ && async_->complete_switch(t, o);
}
std::optional<PatternTransportSwitchStatus> PatternTransportCoordinator::inspect_pattern_switch(
    const PatternTransportSwitchTicket& t) const {
  const auto* s = async_ ? async_->find_switch(t) : nullptr;
  return s ? std::optional{s->status} : std::nullopt;
}
bool PatternTransportCoordinator::consume_pattern_switch(const PatternTransportSwitchTicket& t) {
  return async_ && async_->consume_switch(t);
}
bool PatternTransportCoordinator::abandon_pattern_switch(const PatternTransportSwitchTicket& t) {
  return async_ && async_->abandon_switch(t);
}

PatternTransportCoordinator::PatternTransportCoordinator(
    PatternTransportAudioPort& audio, project_io::SequenceJournal& journals,
    project_io::ProjectStore& store, std::filesystem::path bundle,
    foundation::SequenceSessionId session, foundation::ProjectId project,
    foundation::PatternId pattern, std::uint64_t runtime_generation,
    PatternAdmissionOwner::Clock clock)
    : audio_(audio), journals_(&journals), bundle_(bundle),
      clock_(clock ? std::move(clock) : PatternAdmissionOwner::Clock{
          [] { return std::chrono::steady_clock::now(); }}),
      owner_(std::make_unique<PatternAdmissionOwner>(journals, bundle, session, clock_)), store_(&store),
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

bool PatternTransportCoordinator::retains_command_id(
    const foundation::CommandId& command_id) const {
  if (async_) return async_->retains(command_id);
  return (pending_ && pending_->command_id == command_id) ||
         retained_.contains(command_id);
}

PatternTransportSubmit PatternTransportCoordinator::request(
    const PatternTransportRequest& request) {
  if (async_) return async_->request(request);
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
  const bool observed_control = !recording_ &&
      audio_.supports_receipt_bound_opening();
  std::optional<audio::PatternTransportObservation> observation;
  if (observed_control) {
    observation = audio_.observe_transport();
    if (!observation || !observation->current_pattern ||
        observation->current_generation == 0)
      return PatternTransportSubmit::busy;
  }
  const bool pending_publication = observation &&
      (observation->pending_switches[0] || observation->pending_switches[1] ||
       observation->outstanding_cancellation);
  const bool receipt_opening = opens_journal && pending_publication;
  std::optional<ReceiptBoundOpening> opening;
  if (receipt_opening) {
    const auto started = clock_();
    const auto loaded = store_->load(bundle_);
    if (!loaded.has_value()) {
      error_ = loaded.error();
      return PatternTransportSubmit::refused;
    }
    if (request.expected_revision &&
        *request.expected_revision != loaded.value().revision) {
      error_ = foundation::Error{foundation::ErrorCode::revision_conflict,
          "Pattern transport record expected a different Project revision"};
      return PatternTransportSubmit::refused;
    }
    const auto performance = journals_->read_active_performance(bundle_);
    if (performance.has_value() ||
        performance.error().code != foundation::ErrorCode::not_found) {
      error_ = performance.has_value()
          ? foundation::Error{foundation::ErrorCode::invalid_argument,
              "Pattern transport Record conflicts with an active Performance owner"}
          : performance.error();
      return PatternTransportSubmit::refused;
    }
    const auto current_pattern = loaded.value().patterns.find(*observation->current_pattern);
    if (current_pattern == loaded.value().patterns.end()) {
      error_ = foundation::Error{foundation::ErrorCode::not_found,
          "Pattern transport record target Pattern is missing"};
      return PatternTransportSubmit::refused;
    }
    const auto active = journals_->read_active(bundle_);
    if (active.has_value()) {
      if (active.value().session_id != session_ ||
          active.value().pattern_id != *observation->current_pattern ||
          active.value().state != project_io::SequenceSessionState::active ||
          active.value().admission || !empty_legacy_prefix(active.value()) ||
          active.value().expected_revision != loaded.value().revision ||
          active.value().bars != current_pattern->second.bars ||
          active.value().pattern_fingerprint !=
              project_io::sequence_pattern_fingerprint(current_pattern->second)) {
        error_ = foundation::Error{foundation::ErrorCode::invalid_argument,
            "Pattern transport Record conflicts with an existing journal owner or target"};
        return PatternTransportSubmit::refused;
      }
      // A prebegun journal is already bound; a different pending identity
      // requires its settlement owner, never a silent new admission target.
      for (const auto& authority : observation->pending_switches) {
        if (authority && authority->pattern_id != active.value().pattern_id) {
          error_ = foundation::Error{foundation::ErrorCode::invalid_argument,
              "Pattern transport existing journal cannot cross an opening switch"};
          return PatternTransportSubmit::refused;
        }
      }
    } else if (active.error().code != foundation::ErrorCode::not_found) {
      error_ = active.error();
      return PatternTransportSubmit::refused;
    }
    for (const auto& authority : observation->pending_switches) {
      if (authority && !loaded.value().patterns.contains(authority->pattern_id)) {
        error_ = foundation::Error{foundation::ErrorCode::not_found,
            "Pattern transport pending Record target Pattern is missing"};
        return PatternTransportSubmit::refused;
      }
    }
    opening = ReceiptBoundOpening{loaded.value().revision, started};
  }
  if (opens_journal && !receipt_opening) {
    // The binding is vendored at construction, but the engine's current
    // Pattern can move behind the coordinator: a switch publication applying
    // at the Bar boundary while the transport keeps playing. Re-anchor the
    // binding on the engine's current identity before the journal and the
    // admission preparation name the stale one, or the admission fence (which
    // names the receipt's Pattern) fails authority validation deterministically
    // (#1403). A port reporting no current Pattern keeps the vendored binding,
    // and an active journal never retargets: the switch-spanning close
    // machinery (retain_switch/reconcile_switch/drain) owns that settlement.
    if (const auto current = observation
            ? observation->current_pattern : audio_.current_pattern();
        current.has_value() && *current != pattern_) {
      pattern_ = *current;
    }
    // The journal is Facade-owned: a Record request lazily begins it when no
    // active journal exists, while playback alone never creates one.
    const auto active = journals_->read_active(bundle_);
    if (!active.has_value()) {
      if (active.error().code != foundation::ErrorCode::not_found) {
        error_ = active.error();
        return PatternTransportSubmit::refused;
      }
      const auto loaded = store_->load(bundle_);
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
      const auto begun = journals_->begin(
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
        project_, pattern_, observation ? observation->current_generation
                                       : audio_.pattern_generation(), 10};
    const auto prepared = owner_->prepare(preparation);
    if (!prepared.has_value()) {
      error_ = prepared.error();
      return PatternTransportSubmit::refused;
    }
  }

  audio::PatternTransportCommand command{
      runtime_generation_, request.expected_epoch, last_pattern_generation_,
      audio_action(request.intent), {}};
  const auto apply_observation = [&](const audio::PatternTransportObservation& state) {
    command.expected_pattern_generation = state.current_generation;
    command.pending_switch = state.pending_switches[1]
        ? state.pending_switches[1] : state.pending_switches[0];
    command.pending_switch_predecessor = state.pending_switches[1]
        ? state.pending_switches[0] : std::nullopt;
    if (state.outstanding_cancellation) {
      if (command.pending_switch)
        command.pending_switch_predecessor = state.outstanding_cancellation;
      else command.pending_switch = state.outstanding_cancellation;
    }
  };
  // A typed observation already binds current and both exact authorities.
  // Legacy ports read current before pending so an outside republication can
  // advance beyond the last receipt without making a named successor stale.
  const auto current_generation = observation
      ? observation->current_generation : audio_.pattern_generation();
  if (observation) apply_observation(*observation);
  else if (playing_) command.pending_switch = audio_.pending_switch();
  if (!command.pending_switch && !observation) {
    command.expected_pattern_generation = audio_.pattern_generation();
  } else if (!observation && command.pending_switch &&
             unlanded_overlay_generation_ == 0 &&
             command.pending_switch->generation != current_generation) {
    // A named successor fences against the Pattern that plays now. A Host
    // republication outside this coordinator (a Record-off completion) can
    // have advanced it past the last receipt, and the engine refuses a
    // command whose expected generation is neither current nor the
    // acknowledged predecessor of an applied switch (#1958).
    command.expected_pattern_generation = current_generation;
  } else if (command.pending_switch && unlanded_overlay_generation_ != 0 &&
             command.pending_switch->generation ==
                 unlanded_overlay_generation_) {
    // The pending successor is this coordinator's own overlay, still queued
    // for its bar — identified by the generation of the publish receipt both
    // sides remember, never by the Pattern identity (a retarget can rebind
    // pattern_ while the marker lives). A transport command cannot fence
    // across an unlanded publication it would have to name as applied
    // authority, and refusing it would refuse Record-off for up to a Bar after
    // every input. Withdraw the overlay instead: it is not durable until it
    // lands, the close commits the same retained input, and an engagement
    // that keeps recording republishes it on the next idle tick (#1513).
    if (!withdraw_unlanded_overlay(*command.pending_switch)) {
      // The render thread already reached its apply point; the boundary is
      // imminent and the next attempt names it as applied.
      return PatternTransportSubmit::busy;
    }
    // A withdrawn publication the render thread had already claimed stays
    // outstanding until its next quantum retires it, and the engine refuses a
    // command while any unnamed publication is outstanding. The command is
    // accepted now and submitted from the cadence once it has retired — one
    // render quantum, not a Bar.
    pending_ = request;
    phase_ = PatternTransportPhase::awaiting_audio;
    deferred_submit_ = true;
    return PatternTransportSubmit::accepted;
  }
  auto submitted = audio_.submit(command);
  // Only a live typed observation is refreshable, and only identity races.
  // At most two outstanding publications can advance while this serialized
  // control operation admits its command. No authority guard is weakened.
  for (unsigned retry = 0; observation &&
       submitted == audio::PatternTransportSubmit::identity_mismatch && retry != 2;
       ++retry) {
    const auto refreshed = audio_.observe_transport();
    if (!refreshed || !refreshed->current_pattern ||
        refreshed->current_generation == 0) break;
    apply_observation(*refreshed);
    submitted = audio_.submit(command);
  }
  if (submitted != audio::PatternTransportSubmit::accepted) {
    error_ = foundation::Error{foundation::ErrorCode::invalid_argument,
                               "Pattern transport audio submit refused"};
    return PatternTransportSubmit::refused;
  }
  receipt_bound_opening_ = opening;
  if (observation) error_.reset();
  pending_ = request;
  phase_ = PatternTransportPhase::awaiting_audio;
  return PatternTransportSubmit::accepted;
}

PatternTransportStatus PatternTransportCoordinator::inspect() const {
  if (async_) return async_->inspect();
  return {playing_, recording_, phase_, runtime_generation_,
          pending_ ? pending_->expected_epoch
                   : (last_ ? last_->expected_epoch : 0),
          origin_frame_,
          pending_ ? std::optional{pending_->command_id}
                   : (last_ ? std::optional{last_->command_id} : std::nullopt),
          error_};
}

foundation::Result<void> PatternTransportCoordinator::prepare_receipt_bound_opening(
    const audio::PatternTransportReceipt& receipt,
    const PatternTransportRequest& request) {
  const auto& opening = *receipt_bound_opening_;
  const auto loaded = store_->load(bundle_);
  if (!loaded.has_value()) return foundation::Result<void>::failure(loaded.error());
  if (loaded.value().revision != opening.revision ||
      (request.expected_revision && *request.expected_revision != opening.revision))
    return foundation::Result<void>::failure({foundation::ErrorCode::revision_conflict,
        "Accepted Pattern Record cutoff has a different Project revision"});
  const auto found = loaded.value().patterns.find(receipt.pattern_id);
  if (found == loaded.value().patterns.end())
    return foundation::Result<void>::failure({foundation::ErrorCode::not_found,
        "Accepted Pattern Record cutoff target is missing"});
  const auto fingerprint = project_io::sequence_pattern_fingerprint(found->second);
  const auto active = journals_->read_active(bundle_);
  if (active.has_value()) {
    if (active.value().session_id != session_ ||
        active.value().pattern_id != receipt.pattern_id ||
        active.value().expected_revision != opening.revision ||
        active.value().pattern_fingerprint != fingerprint ||
        active.value().bars != found->second.bars ||
        !empty_legacy_prefix(active.value()) ||
        active.value().state != project_io::SequenceSessionState::active)
      return foundation::Result<void>::failure({foundation::ErrorCode::invalid_argument,
          "Accepted Pattern Record cutoff conflicts with an existing journal owner or target"});
  } else {
    if (active.error().code != foundation::ErrorCode::not_found)
      return foundation::Result<void>::failure(active.error());
    const auto begun = journals_->begin(bundle_, session_, receipt.pattern_id,
        found->second.bars, fingerprint, opening.revision);
    if (!begun.has_value()) return begun;
  }
  const project_io::SequenceAdmissionPreparation preparation{
      {request.command_id, runtime_generation_, request.expected_epoch},
      project_, receipt.pattern_id, receipt.pattern_generation, 10};
  const auto prepared = owner_->prepare(preparation, opening.started_at);
  if (!prepared.has_value()) return prepared;
  pattern_ = receipt.pattern_id;
  return foundation::Result<void>::success();
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
    if (receipt_bound_opening_) {
      const auto prepared = prepare_receipt_bound_opening(receipt, request);
      if (!prepared.has_value()) return prepared;
    }
    auto fence = fence_from(
        receipt, project_io::SequenceFenceKind::admission, request.command_id);
    if (receipt_bound_opening_) {
      // These outcomes preceded this new admission; they remain exact in the
      // native receipt, not a fictitious switch within its Journal timeline.
      fence.switch_authority.reset();
      fence.switch_outcome = project_io::SequenceSwitchOutcome::none;
      fence.switch_applied_frame.reset();
    }
    const auto activated = owner_->activate(fence);
    if (!activated.has_value()) return activated;
    if (!receipt_bound_opening_) recording_ = true;
  }
  if (closing) {
    // The render boundary can land our overlay before the next idle control
    // tick records it. Once a close is pending that tick cannot run; retain
    // the exact generation the closing receipt proves applied before cutoff.
    // Keep the marker on IO failure so the same unacknowledged receipt retries
    // the idempotent record, never substituting a merely queued publication.
    if (unlanded_overlay_generation_ != 0 &&
        receipt.pattern_generation == unlanded_overlay_generation_ &&
        receipt.switch_decision == audio::PatternCutoffDecision::none) {
      const auto recorded = owner_->retain_overlay_publication(
          unlanded_overlay_generation_);
      if (!recorded.has_value()) return recorded;
      published_generation_ = unlanded_overlay_generation_;
      unlanded_overlay_generation_ = 0;
    }
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
      const auto retained = owner_->retain_switch(authority);
      if (!retained.has_value()) return retained;
      retained_switch = true;
    }
    const auto cut = owner_->cutoff(fence_from(
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
  if (opening && receipt_bound_opening_) recording_ = true;
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
    const auto source = owner_->drain_source_prefix(
        *store_, pending_->command_id, derive_command(pending_->command_id, 0, 'f'));
    if (!source.has_value()) return source;
  }
  const auto reconciled = owner_->reconcile_switch(*store_);
  if (!reconciled.has_value()) return reconciled;
  if (pending_ && close_applied_switch_) {
    const auto target = owner_->drain_target_segment(
        *store_, derive_command(pending_->command_id, 1, 'a'),
        derive_command(pending_->command_id, 2, 'b'),
        derive_command(pending_->command_id, 3, 'c'));
    if (!target.has_value()) return target;
  }
  const auto closed = owner_->close_requested();
  if (!closed.has_value()) return closed;
  // A close without an applied switch settles the admission: the frozen prefix
  // is drained once, the terminal receipt seals it, its tail is committed to
  // Project Truth exactly once, and the settled journal is removed.
  if (pending_ && !close_applied_switch_) {
    const auto settled = owner_->settle_close(
        *store_, derive_command(pending_->command_id, 1, 'a'),
        derive_command(pending_->command_id, 4, 'd'),
        derive_command(pending_->command_id, 2, 'b'));
    if (!settled.has_value()) return settled;
  }
  store_->seal_authoring_history_group(bundle_);
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
  if (async_) {
    // An already accepted candidate owns its terminal result even after a real
    // cutoff/close. Neither closing nor recording=false may relabel it.
    if (async_->legacy_candidate) {
      if (*async_->legacy_candidate != candidate)
        return foundation::Result<PatternAdmissionAdmit>::failure(Async::busy("pattern_transport_metadata_full"));
      if (async_->legacy_result) {
        const auto result = *async_->legacy_result;
        async_->legacy_candidate.reset();
        async_->legacy_result.reset();
        return result;
      }
      return foundation::Result<PatternAdmissionAdmit>::failure(Async::busy());
    }
    if (!async_->recording) return foundation::Result<PatternAdmissionAdmit>::failure(
        {foundation::ErrorCode::invalid_argument, "Pattern transport admission requires recording"});
    if (async_->closing) return foundation::Result<PatternAdmissionAdmit>::success(PatternAdmissionAdmit::live_only);
    // The legacy DTO has no native sequence authority. Hosts migrating I/O must
    // poll this exact candidate; opt-in Hosts use reserve/bind/complete instead.
    if (!async_->legacy_candidate) {
      async_->legacy_candidate = candidate;
      async_->legacy_result.reset();
      async_->drive_legacy_input();
    } else if (*async_->legacy_candidate != candidate) {
      return foundation::Result<PatternAdmissionAdmit>::failure(Async::busy("pattern_transport_metadata_full"));
    }
    if (async_->legacy_result) {
      const auto result = *async_->legacy_result;
      async_->legacy_candidate.reset();
      async_->legacy_result.reset();
      return result;
    }
    return foundation::Result<PatternAdmissionAdmit>::failure(Async::busy());
  }
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
  const auto admitted = owner_->admit(candidate);
  if (admitted.has_value() &&
      admitted.value() == PatternAdmissionAdmit::retained) {
    // Durable input may change the projection; the control cadence publishes
    // it (never inline on the trigger path), with a fresh retry budget.
    overlay_publication_pending_ = true;
  }
  return admitted;
}

foundation::Result<void> PatternTransportCoordinator::publish_overlay() {
  if (async_) return async_->publish();
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
  // While this coordinator's own overlay is still queued for its Bar, the
  // tick has nothing to do until the boundary, and the port alone can say so.
  // This cadence runs on every realtime service tick of the control lane:
  // answering from the journal here cost two journal reads per tick for up to
  // a Bar after every input, and the lane's requests timed out behind them.
  if (unlanded_overlay_generation_ != 0) {
    const auto pending_now = audio_.pending_switch();
    if (pending_now.has_value() &&
        pending_now->generation == unlanded_overlay_generation_) {
      return foundation::Result<void>::success();
    }
  }
  // A journal that has retained a switch and awaits reconciliation is in the
  // switching state; the journal would refuse the overlay record for a state
  // it considers ordinary, so hold the publication until reconciliation
  // re-anchors the projection (#1513).
  {
    const auto journal = journals_->read_active(bundle_);
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
      const auto recorded = owner_->retain_overlay_publication(
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

// Cadence ticks a deferred command may wait for the withdrawn slot to leave
// the engine's outstanding set. Naming that slot succeeds on the first tick
// while it is still pending, and an unnamed submit succeeds on the first tick
// after it retires; a mismatch across this many ticks is a real conflict.
constexpr unsigned kDeferredSubmitAttempts = 64;

bool PatternTransportCoordinator::withdraw_unlanded_overlay(
    const audio::PatternReplacementAuthority& authority) {
  if (!audio_.cancel_overlay(authority)) return false;
  // Nothing was recorded for it: the journal names an overlay only once it
  // lands. Forget its content generation so the same projection is published
  // again if the engagement keeps recording.
  unlanded_overlay_generation_ = 0;
  published_projection_generation_ = 0;
  overlay_publication_pending_ = true;
  withdrawn_overlay_ = authority;
  return true;
}

foundation::Result<std::optional<PatternTransportOverlayProjection>>
PatternTransportCoordinator::project_overlay() {
  if (async_) {
    if (async_->owner_invalidated || async_->unsettled_switches())
      return foundation::Result<std::optional<PatternTransportOverlayProjection>>::success(std::nullopt);
    if (async_->recording && !async_->closing && async_->projection_dirty && !async_->work_request)
      {
        if (async_->projection_offset == 0) async_->projecting_revision = async_->projection_revision;
        async_->work({{"op", "project"}, {"offset", async_->projection_offset}}, *async_->recording_request);
      }
    if (async_->recording && !async_->closing && async_->projection_dirty)
      return foundation::Result<std::optional<PatternTransportOverlayProjection>>::failure(Async::busy());
    return foundation::Result<std::optional<PatternTransportOverlayProjection>>::success(
        async_->recording && !async_->closing && async_->projection_available ? async_->projection : std::nullopt);
  }
  using Projection =
      foundation::Result<std::optional<PatternTransportOverlayProjection>>;
  // Once the cutoff receipt is applied the candidate set is frozen and the
  // close owns the next publication, so an overlay here could only race it.
  if (!recording_ || close_pending_) return Projection::success(std::nullopt);
  const auto journal = journals_->read_active(bundle_);
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
  if (async_) return async_->drive();
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
  if (deferred_submit_) {
    // The withdrawn overlay's slot stays outstanding audio-side until its
    // activation frame. Name it, so the engine accepts the command and cancels
    // the slot at this command's cutoff; once it has retired, submit unnamed.
    audio::PatternTransportCommand command{
        runtime_generation_, pending_->expected_epoch, last_pattern_generation_,
        audio_action(pending_->intent), {}};
    command.expected_pattern_generation = audio_.pattern_generation();
    auto submitted = audio::PatternTransportSubmit::identity_mismatch;
    if (withdrawn_overlay_) {
      command.pending_switch = withdrawn_overlay_;
      submitted = audio_.submit(command);
    }
    if (submitted == audio::PatternTransportSubmit::identity_mismatch) {
      command.pending_switch.reset();
      withdrawn_overlay_.reset();
      submitted = audio_.submit(command);
    }
    if (submitted == audio::PatternTransportSubmit::identity_mismatch &&
        ++deferred_attempts_ < kDeferredSubmitAttempts) {
      return foundation::Result<void>::success();
    }
    deferred_submit_ = false;
    deferred_attempts_ = 0;
    if (submitted != audio::PatternTransportSubmit::accepted) {
      // A mismatch that outlasts the retry budget is a real unnamed successor,
      // not the withdrawn slot retiring; it is refused like an immediate submit.
      // Nothing withdrawn may outlive the refused command and be matched
      // against a later command's receipt. An accepted command keeps it until
      // its own receipt, which is where the named slot is recognised.
      withdrawn_overlay_.reset();
      error_ = foundation::Error{foundation::ErrorCode::invalid_argument,
                                 "Pattern transport audio submit refused"};
      pending_.reset();
      phase_ = PatternTransportPhase::idle;
      return foundation::Result<void>::failure(*error_);
    }
    return foundation::Result<void>::success();
  }
  const auto receipt = audio_.inspect(
      pending_->runtime_generation, pending_->expected_epoch);
  if (!receipt.has_value()) return foundation::Result<void>::success();
  auto effective = *receipt;
  if (withdrawn_overlay_ && effective.switch_authority &&
      effective.switch_authority->generation == withdrawn_overlay_->generation &&
      effective.switch_decision ==
          audio::PatternCutoffDecision::canceled_at_cutoff) {
    // The named slot was this coordinator's own withdrawn overlay: it never
    // applied and was never recorded, so the fence names no switch.
    effective.switch_authority.reset();
    effective.switch_decision = audio::PatternCutoffDecision::none;
  }
  withdrawn_overlay_.reset();
  const auto applied = apply_receipt(effective, *pending_);
  if (!applied.has_value()) {
    error_ = applied.error();
    // A deterministic authority/identity failure (for example a Pattern that
    // changed behind the engagement) never resolves by re-reading the same
    // retained receipt; park the engagement in the error phase instead of
    // looping awaiting_audio forever. Recovery is a Project reopen, where the
    // owner-loss recovery surface lists the unresolved journal.
    const bool opening_conflict = receipt_bound_opening_ &&
        (applied.error().code == foundation::ErrorCode::revision_conflict ||
         applied.error().code == foundation::ErrorCode::not_found);
    phase_ = (terminal(applied.error()) || opening_conflict)
                 ? PatternTransportPhase::error
                 : (close_pending_ ? PatternTransportPhase::flushing
                                   : PatternTransportPhase::awaiting_audio);
    return applied;
  }
  if (receipt_bound_opening_) error_.reset();
  receipt_bound_opening_.reset();
  retained_.insert_or_assign(pending_->command_id, *pending_);
  last_ = pending_;
  pending_.reset();
  phase_ = PatternTransportPhase::idle;
  return foundation::Result<void>::success();
}

}  // namespace lmdj::facade::detail
