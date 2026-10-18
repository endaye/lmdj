#include "pattern_transport_io_owner.hpp"

#include <stdexcept>
#include <picosha2.h>
#include <utility>

#if defined(LMDJ_PATTERN_TRANSPORT_TESTING) && LMDJ_PATTERN_TRANSPORT_TESTING
#include <atomic>
#include <lmdj/facade/pattern_transport_io_testing.hpp>
namespace lmdj::facade::testing {
namespace { std::atomic<const PatternTransportIoWorkHook*> work_hook{nullptr}; }
void install_pattern_transport_io_work_hook_for_testing(
    const PatternTransportIoWorkHook* hook) noexcept {
  work_hook.store(hook, std::memory_order_release);
}
}  // namespace lmdj::facade::testing
#endif

namespace lmdj::facade::detail {
namespace {
using Json = nlohmann::json;
using Result = foundation::Result<Json>;
foundation::CommandId derived(const foundation::CommandId& command,
                              std::size_t offset, char tag) {
  auto value = command.value();
  const auto dash = value.rfind('-');
  if (dash != std::string::npos && dash + 1 + offset < value.size()) {
    auto& digit = value[dash + 1 + offset];
    digit = digit == tag ? (tag == 'f' ? 'e' : 'f') : tag;
  }
  return foundation::CommandId{value};
}
foundation::CommandId checkpoint_id(const PatternTransportWorkIdentity& identity, std::uint64_t watermark) {
  const auto preimage = "pattern-admission-checkpoint:" + identity.command_id.value() + ":" +
      std::to_string(identity.runtime_generation) + ":" + std::to_string(identity.transport_epoch) + ":" +
      std::to_string(watermark);
  auto digest = picosha2::hash256_hex_string(preimage);
  digest[12] = '4'; digest[16] = '8';
  return foundation::CommandId{digest.substr(0,8) + "-" + digest.substr(8,4) + "-" + digest.substr(12,4) +
      "-" + digest.substr(16,4) + "-" + digest.substr(20,12)};
}
bool empty_prefix(const project_io::ActiveSequenceJournal& journal) {
  return !journal.last_input_sequence && !journal.next_tail_seq &&
      journal.pending_events.empty() && !journal.next_flush_seq &&
      journal.flushes.empty() && !journal.armed_capture_slot && !journal.capture_commit;
}
project_io::SequenceAdmissionFence decode_fence(const Json& j) {
  project_io::SequenceAdmissionFence fence{
      static_cast<project_io::SequenceFenceKind>(j.at("kind").get<unsigned>()),
      foundation::CommandId{j.at("command").get<std::string>()},
      j.at("epoch").get<std::uint64_t>(), j.at("frame").get<std::uint64_t>(),
      j.at("origin").get<std::uint64_t>(),
      foundation::PatternId{j.at("pattern").get<std::string>()},
      j.at("generation").get<std::uint64_t>(), j.at("bpm").get<std::uint16_t>(),
      j.at("playing").get<bool>(), {},
      static_cast<project_io::SequenceSwitchOutcome>(j.at("switch_outcome").get<unsigned>()), {}};
  if (!j.at("switch").is_null()) {
    const auto& s = j.at("switch");
    fence.switch_authority = project_io::SequencePublicationAuthority{
        foundation::PatternId{s.at("pattern").get<std::string>()},
        s.at("generation").get<std::uint64_t>(), s.at("frame").get<std::uint64_t>()};
  }
  if (!j.at("switch_frame").is_null())
    fence.switch_applied_frame = j.at("switch_frame").get<std::uint64_t>();
  return fence;
}
}  // namespace

std::int64_t transport_clock_stamp(std::chrono::steady_clock::time_point time) {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(time.time_since_epoch()).count();
}
Json encode_transport_fence(const project_io::SequenceAdmissionFence& f) {
  Json j{{"kind", static_cast<unsigned>(f.kind)}, {"command", f.command_id.value()},
      {"epoch", f.transport_epoch}, {"frame", f.effective_frame},
      {"origin", f.origin_frame}, {"pattern", f.pattern_id.value()},
      {"generation", f.publication_generation}, {"bpm", f.bpm},
      {"playing", f.playing}, {"switch_outcome", static_cast<unsigned>(f.switch_outcome)},
      {"switch", nullptr}, {"switch_frame", nullptr}};
  if (f.switch_authority) j["switch"] = {{"pattern", f.switch_authority->pattern_id.value()},
      {"generation", f.switch_authority->generation}, {"frame", f.switch_authority->frame}};
  if (f.switch_applied_frame) j["switch_frame"] = *f.switch_applied_frame;
  return j;
}

PatternTransportIoOwner::PatternTransportIoOwner(PatternTransportControllerConfig config,
    std::shared_ptr<project_io::ProjectStoragePlatform> platform,
    std::shared_ptr<project_io::AuthoringHistory> history,
    std::shared_ptr<PatternTransportOpeningPublication> opening)
    : config_(std::move(config)), journals_(platform),
      store_(std::move(platform), std::move(history)),
      owner_(journals_, config_.bundle, config_.session), opening_(std::move(opening)) {}

PatternTransportWorkCompletion PatternTransportIoOwner::execute(
    const PatternTransportWorkRequest& request) {
#if defined(LMDJ_PATTERN_TRANSPORT_TESTING) && LMDJ_PATTERN_TRANSPORT_TESTING
  const auto* hook = testing::work_hook.load(std::memory_order_acquire);
  if (hook && hook->before_execute) hook->before_execute(hook->context, request);
  try {
#endif
  const auto result = perform(request, Json::parse(request.payload));
  if (!result.has_value()) {
    // A storage failure can have durable effects. Keep its exact work cell;
    // callers may not treat an exception or unreadable readback as absence.
    const auto uncertain = result.error().code == foundation::ErrorCode::io_error ||
        result.error().code == foundation::ErrorCode::internal_error;
    if (uncertain) uncertain_error_ = result.error();
    const PatternTransportWorkCompletion completion{
        uncertain ? PatternTransportWorkOutcome::unknown
                  : PatternTransportWorkOutcome::refused, {}, result.error()};
#if defined(LMDJ_PATTERN_TRANSPORT_TESTING) && LMDJ_PATTERN_TRANSPORT_TESTING
    if (hook && hook->after_execute) hook->after_execute(hook->context, request, &completion);
#endif
    return completion;
  }
  const PatternTransportWorkCompletion completion{
      PatternTransportWorkOutcome::success, result.value().dump(), {}};
#if defined(LMDJ_PATTERN_TRANSPORT_TESTING) && LMDJ_PATTERN_TRANSPORT_TESTING
  if (hook && hook->after_execute) hook->after_execute(hook->context, request, &completion);
#endif
  return completion;
#if defined(LMDJ_PATTERN_TRANSPORT_TESTING) && LMDJ_PATTERN_TRANSPORT_TESTING
  } catch (...) {
    if (hook && hook->after_execute) hook->after_execute(hook->context, request, nullptr);
    throw;
  }
#endif
}


PatternTransportWorkCompletion PatternTransportIoOwner::reconcile(const PatternTransportWorkRequest& request) {
  const auto j = Json::parse(request.payload);
  const auto op = j.at("op").get<std::string>();
  const auto replay_original = [&] {
    // Readable bytes after an unknown sync response cannot prove durability.
    // The same actual owner replays the exact immutable work through the real
    // durable writer, retaining its original clock and any earlier success.
    const auto result = perform(request, j);
    if (result.has_value())
      return PatternTransportWorkCompletion{PatternTransportWorkOutcome::success, result.value().dump(), {}};
    const bool uncertain = result.error().code == foundation::ErrorCode::io_error ||
        result.error().code == foundation::ErrorCode::internal_error;
    if (uncertain) uncertain_error_ = result.error();
    return PatternTransportWorkCompletion{uncertain ? PatternTransportWorkOutcome::unknown : PatternTransportWorkOutcome::refused,
        {}, result.error()};
  };
  // The coordinator keeps unknown segment work in the executor's single cell
  // until its exact positive replay. Later cutoff/close cannot overtake it and
  // remove the Journal. After consumption stale reconcile/steps are rejected
  // by the executor; this private owner is not a historical cross-close API.
  if (op == "prepare" || op == "open" || op == "activate" || op == "segment")
    return replay_original();
  const auto journal = journals_.read_active(config_.bundle);
  auto unknown = [&](foundation::Error error) {
    return PatternTransportWorkCompletion{PatternTransportWorkOutcome::unknown, {}, std::move(error)};
  };
  auto absent = [&](bool retryable) {
    auto error = uncertain_error_.value_or(foundation::Error{foundation::ErrorCode::io_error,
        "Pattern transport effect requires reconciliation"});
    error.details["reconciled"] = true;
    error.details["retryable"] = retryable;
    return PatternTransportWorkCompletion{PatternTransportWorkOutcome::refused, {}, std::move(error)};
  };
  auto success = [](Json payload = Json::object()) {
    return PatternTransportWorkCompletion{PatternTransportWorkOutcome::success, payload.dump(), {}};
  };
  if (!journal.has_value()) {
    if (journal.error().code != foundation::ErrorCode::not_found) return unknown(journal.error());
    if (op == "owner_lost") return success();
    if (op == "prepare" || op == "preflight" || op == "open") return absent(true);
    // A settled close removes its journal only after Truth commits. Verify the
    // original replay identity as well; absence alone is never close success.
    if (op == "close") {
      if (owner_.has_settled_close(derived(request.identity.command_id, 4, 'd'),
                                  derived(request.identity.command_id, 2, 'b'))) {
        const auto truth = store_.load(config_.bundle);
        if (!truth.has_value()) return unknown(truth.error());
        store_.seal_authoring_history_group(config_.bundle);
        return success();
      }
      const auto replay = store_.replay_sequence_flush(config_.bundle, config_.session,
          derived(request.identity.command_id, 2, 'b'));
      if (replay.has_value() && replay.value()) return success();
      if (replay.has_value()) return unknown({foundation::ErrorCode::io_error, "Missing exact close flush replay identity"});
      return unknown(replay.error());
    }
    return unknown(journal.error());
  }
  if (journal.value().session_id != config_.session)
    return unknown({foundation::ErrorCode::invalid_argument, "Pattern reconciliation owner changed"});
  const auto& admission = journal.value().admission;
  if (op == "preflight") return absent(true);
  if (op == "owner_lost") {
    if (journal.value().state == project_io::SequenceSessionState::owner_lost) return replay_original();
    return absent(true);
  }
  if (!admission) return unknown({foundation::ErrorCode::invalid_argument, "Pattern reconciliation lost admission"});
  if (op == "admit") {
    const auto& c = j.at("candidate");
    const project_io::SequenceAdmissionCandidate expected{
        c.at("watermark").get<std::uint64_t>(), c.at("frame").get<std::uint64_t>(),
        {c.at("bank").get<std::uint8_t>(), c.at("pad").get<std::uint8_t>()},
        c.at("pressed").get<bool>() ? project_io::SequenceCandidateKind::press : project_io::SequenceCandidateKind::release,
        c.at("velocity").get<std::uint8_t>(), c.at("correlation").get<std::uint64_t>()};
    const auto retain_exact = [&] {
      // Candidate/transfer bytes can survive a failed sync together with a
      // failed storage-error closure. Exact replay rereads under the writer
      // lease and syncs the existing prefix without appending duplicate input.
      const auto durable = journals_.append_admission_candidate(config_.bundle,
          config_.session, admission->preparation.identity, expected);
      return durable.has_value() ? success({{"retained", true}}) : unknown(durable.error());
    };
    for (const auto& candidate : admission->candidates) if (candidate.watermark == expected.watermark) {
      if (candidate != expected) return unknown({foundation::ErrorCode::invalid_argument, "Pattern candidate readback payload changed"});
      return retain_exact();
    }
    for (const auto& transfer : admission->transfers) for (const auto& receipt : transfer.candidate_receipts)
      if (receipt.watermark == expected.watermark) {
        if (receipt != project_io::sequence_admission_candidate_receipt(expected))
          return unknown({foundation::ErrorCode::invalid_argument, "Pattern transferred readback payload changed"});
        return retain_exact();
      }
    // A failure closure also needs an actual durable replay before its exact
    // absence can retire the original work cell as a final refusal.
    if (admission->closure) {
      const auto durable = journals_.close_admission(config_.bundle, config_.session,
          admission->preparation.identity, *admission->closure);
      return durable.has_value() ? absent(false) : unknown(durable.error());
    }
    return absent(true);
  }
  if (op == "cutoff") {
    // Replay the whole original cutoff, including its overlay/switch
    // companions, through their exact durable APIs before retiring the cell.
    if (admission->cutoff_fence && *admission->cutoff_fence == decode_fence(j.at("fence"))) return replay_original();
    return absent(true);
  }
  if (op == "overlay") {
    if (admission->published_generation == j.at("generation").get<std::uint64_t>()) return replay_original();
    return absent(true);
  }
  // A known partial close retries with its original transfer/flush identities.
  if (op == "close" || op == "project") return absent(true);
  return unknown(uncertain_error_.value());
}

Result PatternTransportIoOwner::perform(const PatternTransportWorkRequest& request,
                                        const Json& j) {
  const auto& op = j.at("op").get_ref<const std::string&>();
  const auto fail = [](const foundation::Result<void>& r) {
    return Result::failure(r.error());
  };
  std::optional<project_io::SequenceAdmissionFence> opening_fence;
  std::optional<PatternTransportOpeningCommit> opening_commit;
  if (op == "open" || op == "activate") {
    opening_fence = decode_fence(j.at("fence"));
    if (opening_) opening_commit.emplace(*opening_, request, *opening_fence);
  }
  if (op == "prepare" || op == "open" || op == "preflight") {
    const auto pattern = foundation::PatternId{j.at("pattern").get<std::string>()};
    const auto loaded = store_.load(config_.bundle);
    if (!loaded.has_value()) return Result::failure(loaded.error());
    if (loaded.value().id != config_.project)
      return Result::failure({foundation::ErrorCode::invalid_argument, "Pattern Record Project owner changed"});
    if (!j.at("revision").is_null() &&
        loaded.value().revision != j.at("revision").get<std::uint64_t>())
      return Result::failure({foundation::ErrorCode::revision_conflict,
          "Pattern Record expected a different Project revision"});
    const auto performance = journals_.read_active_performance(config_.bundle);
    if (performance.has_value())
      return Result::failure({foundation::ErrorCode::invalid_argument,
          "Pattern Record conflicts with an active Performance owner"});
    if (performance.error().code != foundation::ErrorCode::not_found)
      return Result::failure(performance.error());
    const auto found = loaded.value().patterns.find(pattern);
    if (found == loaded.value().patterns.end())
      return Result::failure({foundation::ErrorCode::not_found, "Pattern Record target is missing"});
    if (j.contains("targets")) for (const auto& target : j.at("targets"))
      if (!loaded.value().patterns.contains(foundation::PatternId{target.get<std::string>()}))
        return Result::failure({foundation::ErrorCode::not_found, "Pending Pattern Record target is missing"});
    const auto fingerprint = project_io::sequence_pattern_fingerprint(found->second);
    const auto active = journals_.read_active(config_.bundle);
    if (active.has_value()) {
      if (active.value().session_id != config_.session || active.value().pattern_id != pattern ||
          active.value().state != project_io::SequenceSessionState::active ||
          active.value().expected_revision != loaded.value().revision ||
          active.value().pattern_fingerprint != fingerprint || active.value().bars != found->second.bars ||
          (op == "preflight" && active.value().admission) ||
          !empty_prefix(active.value()) || (active.value().admission &&
          active.value().admission->preparation.identity.operation_id != request.identity.command_id))
        return Result::failure({foundation::ErrorCode::invalid_argument,
            "Pattern Record conflicts with an existing journal owner or target"});
      if (op == "preflight" && j.contains("targets")) for (const auto& target : j.at("targets"))
        if (target.get<std::string>() != active.value().pattern_id.value())
          return Result::failure({foundation::ErrorCode::invalid_argument, "Existing Pattern journal cannot cross an opening switch"});
    } else {
      if (active.error().code != foundation::ErrorCode::not_found) return Result::failure(active.error());
      if (op == "preflight") return Result::success(Json{{"revision", loaded.value().revision}});
      const auto begun = journals_.begin(config_.bundle, config_.session, pattern,
          found->second.bars, fingerprint, loaded.value().revision);
      if (!begun.has_value()) return fail(begun);
    }
    if (op == "preflight") return Result::success(Json{{"revision", loaded.value().revision}});
    project_io::SequenceAdmissionPreparation preparation{
        {request.identity.command_id, request.identity.runtime_generation, request.identity.transport_epoch},
        config_.project, pattern, j.at("generation").get<std::uint64_t>(), 10};
    const auto started = std::chrono::steady_clock::time_point{
        std::chrono::duration_cast<std::chrono::steady_clock::duration>(
            std::chrono::nanoseconds{j.at("started").get<std::int64_t>()})};
    const auto prepared = owner_.prepare(preparation, started);
    if (!prepared.has_value()) return fail(prepared);
    if (op == "open") {
      const auto activated = owner_.activate(*opening_fence,
          opening_commit ? &*opening_commit : nullptr);
      if (!activated.has_value()) return fail(activated);
    }
    return Result::success(Json{{"revision", loaded.value().revision}});
  }
  if (op == "activate") {
    const auto r = owner_.activate(*opening_fence,
        opening_commit ? &*opening_commit : nullptr);
    return r.has_value() ? Result::success(Json::object()) : fail(r);
  }
  if (op == "segment") {
    const auto active = journals_.read_active(config_.bundle);
    if (!active.has_value()) return Result::failure(active.error());
    const project_io::SequenceAdmissionIdentity identity{
        foundation::CommandId{j.at("recording").get<std::string>()},
        request.identity.runtime_generation, request.identity.transport_epoch};
    if (active.value().session_id != config_.session || !active.value().admission ||
        active.value().admission->preparation.identity != identity ||
        active.value().admission->preparation.project_id != config_.project ||
        request.identity.runtime_generation != config_.runtime_generation)
      return Result::failure({foundation::ErrorCode::invalid_argument,
          "Pattern segment recording owner changed"});
    // Reconstruct only the exact durable admission after a worker restart.
    // This duplicate uses the real writer; readable state is not a sync ACK.
    auto r = owner_.prepare(active.value().admission->preparation);
    if (!r.has_value()) return fail(r);
    const project_io::SequencePublicationAuthority authority{
        foundation::PatternId{j.at("pattern").get<std::string>()},
        j.at("generation").get<std::uint64_t>(), j.at("frame").get<std::uint64_t>()};
    const auto id = request.identity.command_id;
    r = owner_.continue_segment(store_, authority, j.at("bpm").get<std::uint16_t>(),
        id, derived(id, 0, 'f'), derived(id, 1, 'a'));
    return r.has_value() ? Result::success(Json::object()) : fail(r);
  }
  if (op == "admit") {
    const auto& c = j.at("candidate");
    const project_io::SequenceAdmissionCandidate candidate{
        c.at("watermark").get<std::uint64_t>(), c.at("frame").get<std::uint64_t>(),
        {c.at("bank").get<std::uint8_t>(), c.at("pad").get<std::uint8_t>()},
        c.at("pressed").get<bool>() ? project_io::SequenceCandidateKind::press
                                    : project_io::SequenceCandidateKind::release,
        c.at("velocity").get<std::uint8_t>(), c.at("correlation").get<std::uint64_t>()};
    // N ordinary ingress and N reserved releases must not enlarge the
    // existing persisted window. Transfer a real prefix before its last slot
    // would close it; the original correlated checkpoint survives this drain.
    auto active = journals_.read_active(config_.bundle);
    if (!active.has_value()) return Result::failure(active.error());
    if (active.value().admission && !active.value().admission->closure) {
      const auto& a = *active.value().admission;
      if (a.candidates.size() >= a.preparation.candidate_limit / 2 && !a.candidates.empty()) {
        const auto transferred = owner_.checkpoint_prefix(checkpoint_id(request.identity, a.candidates.back().watermark));
        if (!transferred.has_value()) return fail(transferred);
        // A real transfer changed candidates and their correlation checkpoint.
        // Reuse only the freshly checked journal for this operation's prechecks.
        active = journals_.read_active(config_.bundle);
        if (!active.has_value()) return Result::failure(active.error());
      }
    }
    const auto r = owner_.admit(candidate, active.value());
    if (!r.has_value()) return Result::failure(r.error());
    return Result::success(Json{{"retained", r.value() == PatternAdmissionAdmit::retained}});
  }
  if (op == "cutoff") {
    const auto fence = decode_fence(j.at("fence"));
    if (j.value("overlay", std::uint64_t{}) != 0) {
      const auto r = owner_.retain_overlay_publication(j.at("overlay").get<std::uint64_t>());
      if (!r.has_value()) return fail(r);
    }
    if (fence.switch_outcome == project_io::SequenceSwitchOutcome::applied_before_cutoff) {
      if (!fence.switch_authority || !fence.switch_applied_frame)
        return Result::failure({foundation::ErrorCode::invalid_argument, "Pattern cutoff is missing switch authority"});
      auto authority = *fence.switch_authority;
      authority.frame = *fence.switch_applied_frame;
      const auto r = owner_.retain_switch(authority);
      if (!r.has_value()) return fail(r);
    }
    const auto r = owner_.cutoff(fence);
    return r.has_value() ? Result::success(Json::object()) : fail(r);
  }
  if (op == "close") {
    const auto id = request.identity.command_id;
    if (owner_.has_settled_close(derived(id, 4, 'd'), derived(id, 2, 'b'))) {
      const auto removed = journals_.remove_active_if_complete(config_.bundle, config_.session);
      if (!removed.has_value()) return fail(removed);
      store_.seal_authoring_history_group(config_.bundle);
      return Result::success(Json::object());
    }
    auto r = owner_.drain_source_prefix(store_, id, derived(id, 0, 'f'));
    if (!r.has_value()) return fail(r);
    r = owner_.reconcile_switch(store_);
    if (!r.has_value()) return fail(r);
    if (j.at("switched").get<bool>()) {
      r = owner_.drain_target_segment(store_, derived(id, 1, 'a'), derived(id, 2, 'b'), derived(id, 3, 'c'));
      if (!r.has_value()) return fail(r);
    }
    r = owner_.close_requested();
    if (!r.has_value()) return fail(r);
    if (!j.at("switched").get<bool>()) {
      r = owner_.settle_close(store_, derived(id, 1, 'a'), derived(id, 4, 'd'), derived(id, 2, 'b'));
      if (!r.has_value()) return fail(r);
    }
    store_.seal_authoring_history_group(config_.bundle);
    return Result::success(Json::object());
  }
  if (op == "owner_lost") {
    const auto active = journals_.read_active(config_.bundle);
    if (!active.has_value()) {
      if (active.error().code == foundation::ErrorCode::not_found) return Result::success(Json::object());
      return Result::failure(active.error());
    }
    if (active.value().session_id != config_.session)
      return Result::failure({foundation::ErrorCode::invalid_argument, "Pattern owner-loss disposition conflicts with another owner"});
    const auto r = journals_.set_state(config_.bundle, config_.session, project_io::SequenceSessionState::owner_lost);
    return r.has_value() ? Result::success(Json::object()) : fail(r);
  }
  if (op == "overlay") {
    const auto r = owner_.retain_overlay_publication(j.at("generation").get<std::uint64_t>());
    return r.has_value() ? Result::success(Json::object()) : fail(r);
  }
  if (op == "project") {
    const auto offset = j.value("offset", std::size_t{});
    if (offset == 0) {
      projection_pattern_.reset();
      projection_events_.clear();
      const auto journal = journals_.read_active(config_.bundle);
      if (!journal.has_value()) {
        if (journal.error().code == foundation::ErrorCode::not_found)
          return Result::success(Json{{"projection", nullptr}, {"done", true}});
        return Result::failure(journal.error());
      }
      if (journal.value().session_id != config_.session ||
          journal.value().state == project_io::SequenceSessionState::switching)
        return Result::success(Json{{"projection", nullptr}, {"done", true}});
      const auto r = project_admission_overlay(journal.value(), false);
      if (!r.has_value()) return Result::failure(r.error());
      if (!r.value()) return Result::success(Json{{"projection", nullptr}, {"done", true}});
      projection_pattern_ = journal.value().pattern_id;
      projection_events_ = *r.value();
    }
    if (!projection_pattern_ || offset > projection_events_.size())
      return Result::failure({foundation::ErrorCode::invalid_argument, "Stale Pattern projection chunk"});
    // Fixed scalar/event metadata chunks, never a Project or PCM work payload.
    // A worker-owned immutable projection survives between chunks; it cannot
    // change lineage when candidates arrive on later control turns.
    const auto end = std::min(projection_events_.size(), offset + std::size_t{512});
    Json events = Json::array();
    for (auto n = offset; n != end; ++n) {
      const auto& e = projection_events_[n];
      events.push_back({{"bank", e.slot.bank}, {"pad", e.slot.pad},
          {"tick", e.onset_tick}, {"duration", e.duration_tick}, {"velocity", e.velocity}});
    }
    return Result::success(Json{{"projection", {{"pattern", projection_pattern_->value()}, {"events", events}}},
        {"offset", offset}, {"next_offset", end}, {"done", end == projection_events_.size()}});
  }
  return Result::failure({foundation::ErrorCode::invalid_argument, "Unknown Pattern transport work operation"});
}
}  // namespace lmdj::facade::detail
