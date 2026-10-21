#include "pattern_tempo_preview.hpp"

#include <lmdj/facade/mutation_publish_scope.hpp>

#include <limits>
#include <utility>

namespace lmdj::facade::detail {
namespace {
using foundation::Error;
using foundation::ErrorCode;
using foundation::Result;
using StatusResult = Result<PatternTempoPreviewStatus>;

Error refused(const char* reason) {
  return {ErrorCode::invalid_argument, "Pattern tempo preview was refused", {{"reason", reason}}};
}

bool terminal(PatternTempoPreviewPhase phase) {
  return phase == PatternTempoPreviewPhase::ready ||
      phase == PatternTempoPreviewPhase::cancelled ||
      phase == PatternTempoPreviewPhase::committed ||
      phase == PatternTempoPreviewPhase::source_lost;
}
}  // namespace

bool PatternTempoPreviewAdmission::blocks(const std::filesystem::path& path) const {
  std::lock_guard lock(mutex_);
  return active_ && path_ == path;
}

bool PatternTempoPreviewAdmission::blocks_any() const {
  std::lock_guard lock(mutex_);
  return active_;
}

void PatternTempoPreviewAdmission::set(const std::filesystem::path& path, bool active) {
  std::lock_guard lock(mutex_);
  path_ = path;
  active_ = active;
}

PatternTempoPreviewSession::PatternTempoPreviewSession(std::uint64_t source_id,
    PatternTempoSourceRequest request, audio::PreparedPatternView source,
    audio::RealtimeEngine& engine,
    std::shared_ptr<project_io::ProjectStoragePlatform> platform,
    std::shared_ptr<project_io::AuthoringHistory> history,
    std::shared_ptr<PatternTempoPreviewAdmission> admission, Cook cook)
    : source_id_(source_id), request_(std::move(request)), source_(std::move(source)),
      engine_(engine), gateway_(make_engine_pattern_tempo_publication_gateway(engine)),
      platform_(std::move(platform)), history_(std::move(history)), store_(platform_, history_),
      admission_(std::move(admission)),
      cook_(std::move(cook)), authority_(request_.authority),
      committed_bpm_(source_.bpm()), preview_bpm_(source_.bpm()),
      revision_(request_.expected_revision) {}

PatternTempoPreviewSession::~PatternTempoPreviewSession() {
  // Host-established render quiescence is required for this terminal fallback,
  // exactly as for Native stop/clear. Stop itself is not a callback gate.
  // Clear only our still-owned publication; a replaced owner is untouched.
  // Clearing its derived snapshot prevents a later Engine start reviving preview.
  if (runtime_unsettled_ && engine_.telemetry().start_epoch == authority_.start_epoch) {
    const auto current = engine_.pattern_transport_observation();
    bool foreign = !current || (current->current_generation != authority_.generation &&
        (!pending_authority_ || current->current_generation != pending_authority_->generation));
    if (current) for (const auto& pending : current->pending_switches) {
      if (pending && (!pending_authority_ || pending->generation != pending_authority_->generation))
        foreign = true;
    }
    if (!foreign) {
      engine_.stop();
      static_cast<void>(engine_.clear_pattern_view());
    }
  }
  admission_->set(request_.project_path, false);
}

void PatternTempoPreviewSession::clear_stopped_owned_runtime() {
  if (!runtime_unsettled_ || engine_.telemetry().state != audio::RealtimeState::stopped ||
      engine_.telemetry().start_epoch != authority_.start_epoch) return;
  const auto current = engine_.pattern_transport_observation();
  if (!current || (current->current_generation != authority_.generation &&
      (!pending_authority_ || current->current_generation != pending_authority_->generation))) return;
  for (const auto& pending : current->pending_switches)
    if (pending && (!pending_authority_ || pending->generation != pending_authority_->generation)) return;
  static_cast<void>(engine_.clear_pattern_view());
  runtime_unsettled_ = false;
}

Result<void> PatternTempoPreviewSession::validate(PatternTempoPreviewIdentity id) const {
  if (id.source_id != source_id_ || id.preview_id == 0 || id.preview_id != preview_id_)
    return Result<void>::failure(refused("tempo_preview_stale"));
  if (phase_ == PatternTempoPreviewPhase::source_lost || owner_lost())
    return Result<void>::failure(refused("tempo_source_stale"));
  return Result<void>::success();
}

bool PatternTempoPreviewSession::owner_lost() const {
  const auto life = engine_.telemetry();
  if (life.start_epoch != authority_.start_epoch || life.state != audio::RealtimeState::running)
    return true;
  const auto current = engine_.pattern_transport_observation();
  // A bounded unavailable read is not proof of owner loss.
  if (!current) return false;
  if (current->current_generation == authority_.generation ||
      (pending_authority_ && current->current_generation == pending_authority_->generation)) return false;
  for (const auto& pending : current->pending_switches)
    if (pending && pending_authority_ && pending->generation == pending_authority_->generation) return false;
  return true;
}

void PatternTempoPreviewSession::lose_source() {
  clear_stopped_owned_runtime();
  phase_ = PatternTempoPreviewPhase::source_lost;
  pending_authority_.reset();
  adopting_source_.reset();
  admission_->set(request_.project_path, command_ && !committed_revision_);
  // Retain the command and actual durable receipt, including UNKNOWN, even
  // when its audio owner is gone. Never manufacture a cancelled commit.
}

void PatternTempoPreviewSession::admit(audio::PatternPublication publication, Pending kind) {
  pending_authority_ = PatternTempoAuthority{authority_.start_epoch, publication.generation};
  pending_kind_ = kind;
  failure_.reset();
  suspended_ = false;
  runtime_unsettled_ = true;
  admission_->set(request_.project_path, true);
}

Result<void> PatternTempoPreviewSession::publish_tempo(std::uint16_t bpm, Pending kind) {
  auto published = gateway_.publish(source_, bpm, authority_);
  if (!published.has_value()) return Result<void>::failure(published.error());
  admit(published.value(), kind);
  return Result<void>::success();
}

PatternTempoPreviewStatus PatternTempoPreviewSession::status() const {
  return {{source_id_, preview_id_}, phase_, committed_bpm_, preview_bpm_, revision_,
      source_.project_revision(),
      pending_authority_ ? pending_authority_->generation : authority_.generation,
      command_ ? std::optional{command_->meta.command_id} : std::nullopt,
      committed_revision_, gateway_.observe(authority_), failure_};
}

StatusResult PatternTempoPreviewSession::preview(const PatternTempoPreviewRequest& r) {
  if (r.identity.source_id != source_id_ || r.bpm < 40 || r.bpm > 240)
    return StatusResult::failure(refused("tempo_preview_invalid"));
  if (owner_lost() || phase_ == PatternTempoPreviewPhase::source_lost)
    return StatusResult::failure(refused("tempo_source_stale"));
  if (r.identity.preview_id == 0) {
    if (!terminal(phase_) || phase_ == PatternTempoPreviewPhase::source_lost)
      return StatusResult::failure(refused("tempo_preview_active"));
    if (next_preview_id_ == std::numeric_limits<std::uint64_t>::max())
      return StatusResult::failure(refused("tempo_preview_id_exhausted"));
  } else {
    auto valid = validate(r.identity);
    if (!valid.has_value()) return StatusResult::failure(valid.error());
    if (intent_ != Intent::none || terminal(phase_))
      return StatusResult::failure(refused("tempo_preview_settling"));
  }
  if (pending_authority_) return StatusResult::failure(refused("tempo_preview_pending"));
  // Heap return slot avoids adding a ProjectState-sized frame to Web control.
  const auto truth = std::unique_ptr<Result<domain::ProjectState>>(
      new Result<domain::ProjectState>(store_.inspect_committed(request_.project_path)));
  if (!truth->has_value()) return StatusResult::failure(truth->error());
  if (truth->value().id != request_.project_id || truth->value().revision != source_.project_revision())
    return StatusResult::failure(refused("tempo_truth_changed"));

  const bool starting = r.identity.preview_id == 0;
  if (r.bpm == committed_bpm_) {
    if (starting) {
      preview_id_ = next_preview_id_++;
      preview_bpm_ = r.bpm;
      command_.reset();
      committed_revision_.reset();
      failure_.reset();
      phase_ = PatternTempoPreviewPhase::cancelled;
      return StatusResult::success(status());
    }
    return cancel(r.identity);
  }
  auto published = publish_tempo(r.bpm, Pending::preview);
  if (!published.has_value()) return StatusResult::failure(published.error());
  if (starting) {
    preview_id_ = next_preview_id_++;
    command_.reset();
    committed_revision_.reset();
  }
  intent_ = Intent::none;
  preview_bpm_ = r.bpm;
  phase_ = PatternTempoPreviewPhase::preview_pending;
  return StatusResult::success(status());
}

void PatternTempoPreviewSession::suspend(Error error) {
  failure_ = std::move(error);
  suspended_ = true;
}

void PatternTempoPreviewSession::finish() {
  phase_ = intent_ == Intent::commit ? PatternTempoPreviewPhase::committed
                                    : PatternTempoPreviewPhase::cancelled;
  admission_->set(request_.project_path, false);
  failure_.reset();
  suspended_ = false;
  runtime_unsettled_ = false;
}

void PatternTempoPreviewSession::settle() {
  if (pending_authority_ || suspended_ || intent_ == Intent::none ||
      (intent_ == Intent::commit && !committed_revision_)) return;
  const auto truth = std::unique_ptr<Result<domain::ProjectState>>(
      new Result<domain::ProjectState>(store_.inspect_committed(request_.project_path)));
  if (!truth->has_value()) { suspend(truth->error()); return; }
  if (truth->value().id != request_.project_id ||
      !truth->value().patterns.contains(request_.pattern_id)) {
    suspend(refused("tempo_truth_changed"));
    return;
  }
  committed_bpm_ = truth->value().bpm;
  revision_ = truth->value().revision;
  const auto actual = gateway_.observe(authority_);
  if (!actual) { suspend(refused("tempo_clock_unavailable")); return; }
  if (actual->anchor.bpm != committed_bpm_) {
    auto restored = publish_tempo(committed_bpm_, Pending::restore);
    if (!restored.has_value()) suspend(restored.error());
    return;
  }
  if (source_.project_revision() != truth->value().revision) {
    auto snapshot = cook_(truth->value());
    if (!snapshot.has_value()) { suspend(snapshot.error()); return; }
    auto prepared = audio::PreparedPatternView::from_snapshot(*snapshot.value());
    if (!prepared.has_value()) { suspend(prepared.error()); return; }
    adopting_source_ = std::move(prepared.value());
    auto clone = adopting_source_->with_tempo(committed_bpm_);
    if (!clone.has_value()) { suspend(clone.error()); return; }
    auto adopted = gateway_.adopt(std::move(clone.value()), authority_);
    if (!adopted.has_value()) { suspend(adopted.error()); return; }
    revision_ = truth->value().revision;
    admit(adopted.value(), Pending::adopt);
    return;
  }
  revision_ = truth->value().revision;
  finish();
}

PatternTempoPreviewStatus PatternTempoPreviewSession::service() {
  if (owner_lost()) { lose_source(); return status(); }
  if (terminal(phase_)) return status();
  if (pending_authority_ && gateway_.observe(*pending_authority_)) {
    authority_ = *pending_authority_;
    pending_authority_.reset();
    if (pending_kind_ == Pending::adopt) {
      source_ = std::move(*adopting_source_);
      adopting_source_.reset();
    }
    if (intent_ == Intent::none) phase_ = PatternTempoPreviewPhase::previewing;
  }
  if (pending_authority_) {
    const auto ownership = engine_.pattern_transport_observation();
    if (ownership && ownership->current_generation == authority_.generation) {
      bool retained = ownership->outstanding_cancellation &&
          ownership->outstanding_cancellation->generation == pending_authority_->generation;
      for (const auto& pending : ownership->pending_switches)
        retained |= pending && pending->generation == pending_authority_->generation;
      if (!retained) {
        // This exact admitted publication is absent from current, both pending
        // owners and the retained cancellation cell. A bounded unavailable read
        // never enters here. Do not wait forever or silently repeat a detent.
        pending_authority_.reset();
        adopting_source_.reset();
        if (intent_ == Intent::none) {
          phase_ = PatternTempoPreviewPhase::preview_refused;
          suspend(refused("tempo_publication_unapplied"));
        }
      }
    }
  }
  settle();
  return status();
}

StatusResult PatternTempoPreviewSession::cancel(PatternTempoPreviewIdentity id) {
  auto valid = validate(id);
  if (!valid.has_value()) return StatusResult::failure(valid.error());
  if (command_) {
    if (!committed_revision_) return StatusResult::failure(refused("tempo_commit_unresolved"));
    return StatusResult::success(service());
  }
  if (terminal(phase_)) return StatusResult::success(status());
  intent_ = Intent::cancel;
  phase_ = PatternTempoPreviewPhase::cancelling;
  suspended_ = false;
  failure_.reset();
  return StatusResult::success(service());
}

StatusResult PatternTempoPreviewSession::commit(const PatternTempoPreviewCommit& r) {
  if (r.identity.source_id != source_id_ || r.identity.preview_id == 0 ||
      r.identity.preview_id != preview_id_)
    return StatusResult::failure(refused("tempo_preview_stale"));
  if (!command_) {
    auto valid = validate(r.identity);
    if (!valid.has_value()) return StatusResult::failure(valid.error());
  }
  if (!domain::is_valid_uuid(r.meta.command_id.value()))
    return StatusResult::failure(refused("tempo_commit_invalid"));
  if (command_) {
    if (command_->meta.command_id != r.meta.command_id ||
        command_->meta.expected_revision != r.meta.expected_revision)
      return StatusResult::failure(refused("tempo_commit_identity_mismatch"));
    if (committed_revision_) {
      suspended_ = false;
      failure_.reset();
      return StatusResult::success(service());
    }
  } else {
    if (terminal(phase_) || intent_ != Intent::none)
      return StatusResult::failure(refused("tempo_preview_settling"));
    if (r.meta.expected_revision != source_.project_revision())
      return StatusResult::failure(refused("tempo_truth_changed"));
  }

  const bool first_attempt = !command_;
  const auto preflight_failure = [&](Error error) -> StatusResult {
    if (first_attempt) return StatusResult::failure(std::move(error));
    suspend(std::move(error));
    return StatusResult::success(status());
  };
  // Preserve the Store's lock order. This exact platform shares its genuine
  // bundle custody with nested Store reads/writes on this same control realm.
  auto history_guard = history_->acquire();
  auto lease = platform_->acquire_writer(request_.project_path);
  if (!lease.has_value()) return preflight_failure(lease.error());
  const auto truth = std::unique_ptr<Result<domain::ProjectState>>(
      new Result<domain::ProjectState>(store_.inspect_committed(request_.project_path)));
  if (!truth->has_value()) return preflight_failure(truth->error());
  if (truth->value().id != request_.project_id)
    return preflight_failure(refused("tempo_source_stale"));
  revision_ = truth->value().revision;
  committed_bpm_ = truth->value().bpm;
  if (first_attempt && (revision_ != r.meta.expected_revision ||
      !truth->value().patterns.contains(request_.pattern_id)))
    return preflight_failure(refused("tempo_truth_changed"));

  const auto previous_phase = phase_;
  const auto previous_failure = failure_;
  const auto previous_suspended = suspended_;
  MutationPublishObservation publication;
  if (first_attempt) {
    command_ = domain::UpdateSequenceSettings{r.meta, preview_bpm_, std::nullopt, std::nullopt};
    store_.seal_authoring_history_group(request_.project_path);
  }
  intent_ = Intent::commit;
  phase_ = PatternTempoPreviewPhase::commit_unknown;
  const auto failed_attempt = [&](Error error) -> StatusResult {
    if (first_attempt && !publication.claimed()) {
      command_.reset();
      intent_ = Intent::none;
      phase_ = previous_phase;
      failure_ = previous_failure;
      suspended_ = previous_suspended;
      return StatusResult::failure(std::move(error));
    }
    suspend(std::move(error));
    return StatusResult::success(status());
  };
  // Only producer evidence before a first manifest claim proves refusal.
  // Claimed or previously unknown attempts retain their exact command; an
  // error code or an abort callback is never evidence of rollback.
  std::unique_ptr<Result<project_io::CommandExecution>> saved;
  try {
    saved.reset(new Result<project_io::CommandExecution>(store_.execute_with_identity(
        request_.project_path, domain::Command{*command_})));
  } catch (...) {
    return failed_attempt({ErrorCode::internal_error, "Pattern tempo durable save failed unexpectedly"});
  }
  if (!saved->has_value()) return failed_attempt(saved->error());
  committed_revision_ = saved->value().outcome.event.at("revision").get<std::uint64_t>();
  store_.seal_authoring_history_group(request_.project_path);
  committed_bpm_ = saved->value().outcome.state.bpm;
  revision_ = saved->value().outcome.state.revision;
  failure_.reset();
  if (phase_ == PatternTempoPreviewPhase::source_lost || owner_lost()) {
    lose_source();
    return StatusResult::success(status());
  }
  phase_ = PatternTempoPreviewPhase::committed_pending;
  suspended_ = false;
  failure_.reset();
  return StatusResult::success(service());
}

bool PatternTempoPreviewSession::releasable() const {
  return terminal(phase_) && !(command_ && !committed_revision_);
}

Result<audio::PreparedPatternView> PatternTempoPreviewSession::retain_source() const {
  if (!releasable() || owner_lost() || !gateway_.observe(authority_))
    return Result<audio::PreparedPatternView>::failure(refused("tempo_source_unsettled"));
  return source_.with_tempo(source_.bpm());
}

}  // namespace lmdj::facade::detail
