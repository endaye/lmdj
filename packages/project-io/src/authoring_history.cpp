#include <lmdj/project_io/authoring_history.hpp>

#include <utility>

namespace lmdj::project_io {
namespace {
bool matches(const AuthoringHistory::State& history,
             const domain::ProjectState& state, const std::string& fingerprint) {
  return history.project_id == state.id && history.revision == state.revision &&
      history.fingerprint == fingerprint;
}
foundation::Error unavailable(const std::string& reason) {
  return {foundation::ErrorCode::invalid_argument,
          "Undo or Redo is unavailable in this authoring session",
          {{"reason", reason}, {"remedy", "inspect authoring history before retrying"}}};
}
void retain(std::set<std::string>& refs, const std::vector<AuthoringHistory::Entry>& entries) {
  for (const auto& entry : entries) {
    for (const auto& [id, change] : entry.delta.assets) {
      (void)id;
      if (change.before) refs.insert(change.before->artifact.sha256);
      if (change.after) refs.insert(change.after->artifact.sha256);
    }
    for (const auto& [id, change] : entry.delta.performances) {
      (void)id;
      if (change.before && change.before->recording_artifact) refs.insert(change.before->recording_artifact->sha256);
      if (change.after && change.after->recording_artifact) refs.insert(change.after->recording_artifact->sha256);
    }
  }
}
}  // namespace

std::unique_lock<std::recursive_mutex> AuthoringHistory::acquire() const {
  return std::unique_lock<std::recursive_mutex>{mutex_};
}

void AuthoringHistory::start(const std::filesystem::path& bundle, std::string session_id,
                             const domain::ProjectState& state, std::string fingerprint) {
  auto guard = acquire();
  auto next = std::make_shared<State>(State{bundle.lexically_normal(), std::move(session_id),
      state.id, state.revision, std::move(fingerprint), {}, {}, {}, std::nullopt, {}});
  state_ = std::move(next);
  pending_before_.reset(); pending_after_.reset();
}
void AuthoringHistory::close() {
  auto guard = acquire();
  state_.reset(); pending_before_.reset(); pending_after_.reset();
}
void AuthoringHistory::invalidate(const std::filesystem::path& bundle, std::string reason) {
  auto guard = acquire();
  if (!state_ || state_->bundle != bundle.lexically_normal()) return;
  state_->undo.clear(); state_->redo.clear(); state_->displaced_redo.clear(); state_->displaced_oldest.reset();
  state_->disabled_reason = std::move(reason);
  pending_before_.reset(); pending_after_.reset();
}
void AuthoringHistory::reconcile(const std::filesystem::path& bundle,
                                const domain::ProjectState& state,
                                const std::string& fingerprint) {
  auto guard = acquire();
  if (!state_ || state_->bundle != bundle.lexically_normal()) return;
  if (pending_after_) {
    if (matches(*pending_after_, state, fingerprint)) state_ = pending_after_;
    else if (pending_before_ && matches(*pending_before_, state, fingerprint)) state_ = pending_before_;
    else { invalidate(bundle, "authoring_history_invalidated"); return; }
    pending_before_.reset(); pending_after_.reset();
  }
  if (!matches(*state_, state, fingerprint)) invalidate(bundle, "authoring_history_invalidated");
}
AuthoringHistoryStatus AuthoringHistory::status(const std::filesystem::path& bundle) const {
  auto guard = acquire();
  if (!state_ || state_->bundle != bundle.lexically_normal())
    return {{}, 0, 0, 0, {}, {}, "authoring_history_not_open"};
  return {state_->session_id, state_->revision, state_->undo.size(), state_->redo.size(),
      state_->undo.empty() ? "" : state_->undo.back().label,
      state_->redo.empty() ? "" : state_->redo.back().label,
      pending_after_ ? "authoring_history_result_unknown" : state_->disabled_reason};
}
foundation::Result<domain::AuthoringDelta> AuthoringHistory::selected(
    const std::filesystem::path& bundle, const std::string& session_id, bool redo) const {
  auto guard = acquire();
  using Result = foundation::Result<domain::AuthoringDelta>;
  const auto current = status(bundle);
  if (!current.disabled_reason.empty()) return Result::failure(unavailable(current.disabled_reason));
  if (current.session_id != session_id) return Result::failure(unavailable("authoring_history_session_mismatch"));
  const auto& entries = redo ? state_->redo : state_->undo;
  if (entries.empty()) return Result::failure(unavailable("authoring_history_empty"));
  return Result::success(redo ? entries.back().delta : domain::reverse_authoring_delta(entries.back().delta));
}
foundation::Result<AuthoringHistory::Publication> AuthoringHistory::prepare(
    const std::filesystem::path& bundle,
    const domain::ProjectState& before, const domain::ProjectState& after,
    const std::string& before_fingerprint, std::string after_fingerprint,
    std::string label, std::string group, std::optional<bool> redo) {
  auto guard = acquire();
  using Result = foundation::Result<Publication>;
  reconcile(bundle, before, before_fingerprint);
  if (!state_ || state_->bundle != bundle.lexically_normal() || !state_->disabled_reason.empty()) {
    if (redo) return Result::failure(unavailable("authoring_history_invalidated"));
    return Result::success(Publication{});
  }
  auto delta = domain::authoring_difference(before, after);
  if (!delta.has_value()) return Result::failure(delta.error());
  auto next = std::make_shared<State>(*state_);
  next->revision = after.revision;
  next->fingerprint = std::move(after_fingerprint);
  if (redo.has_value()) {
    auto& from = *redo ? next->redo : next->undo;
    auto& to = *redo ? next->undo : next->redo;
    if (from.empty()) return Result::failure(unavailable("authoring_history_empty"));
    const auto expected = *redo ? from.back().delta : domain::reverse_authoring_delta(from.back().delta);
    if (delta.value() != expected) return Result::failure(unavailable("authoring_history_conflict"));
    from.back().group.clear();
    to.push_back(std::move(from.back())); from.pop_back();
    next->displaced_redo.clear();
    next->displaced_oldest.reset();
  } else if (!delta.value().empty()) {
    const bool merge = !group.empty() && !next->undo.empty() && next->undo.back().group == group;
    if (merge) {
      auto combined = domain::compose_authoring_deltas(next->undo.back().delta, delta.value());
      if (!combined.has_value()) return Result::failure(combined.error());
      if (combined.value().empty()) {
        next->undo.pop_back(); next->redo = std::move(next->displaced_redo);
        if (next->displaced_oldest) {
          next->undo.insert(next->undo.begin(), std::move(*next->displaced_oldest));
          next->displaced_oldest.reset();
        }
      } else next->undo.back().delta = std::move(combined.value());
    } else {
      next->displaced_redo.clear();
      next->displaced_oldest.reset();
      if (!next->undo.empty()) next->undo.back().group.clear();
      if (!group.empty()) next->displaced_redo = std::move(next->redo);
      next->redo.clear();
      next->undo.push_back({std::move(delta.value()), std::move(label), std::move(group)});
      if (next->undo.size() > kMaximumActions) {
        if (!next->undo.back().group.empty()) next->displaced_oldest = std::move(next->undo.front());
        next->undo.erase(next->undo.begin());
      }
    }
  }
  return Result::success(Publication{this, state_, std::move(next)});
}
void AuthoringHistory::seal_group(const std::filesystem::path& bundle) {
  auto guard = acquire();
  if (!state_ || state_->bundle != bundle.lexically_normal() || pending_after_) return;
  if (!state_->undo.empty()) state_->undo.back().group.clear();
  state_->displaced_redo.clear();
  state_->displaced_oldest.reset();
}
std::set<std::string> AuthoringHistory::retained_artifacts(const std::filesystem::path& bundle) const {
  auto guard = acquire();
  std::set<std::string> refs;
  for (const auto& state : {state_, pending_before_, pending_after_}) {
    if (!state || state->bundle != bundle.lexically_normal()) continue;
    retain(refs, state->undo); retain(refs, state->redo); retain(refs, state->displaced_redo);
    if (state->displaced_oldest) retain(refs, {*state->displaced_oldest});
  }
  return refs;
}
AuthoringHistory::Publication::Publication(AuthoringHistory* owner,
    std::shared_ptr<State> before, std::shared_ptr<State> after)
    : owner_(owner), before_(std::move(before)), after_(std::move(after)) {}
void AuthoringHistory::Publication::begin() noexcept {
  if (!owner_) return;
  owner_->pending_before_ = before_; owner_->pending_after_ = after_;
}
void AuthoringHistory::Publication::confirm() noexcept {
  if (!owner_) return;
  owner_->state_ = after_;
  owner_->pending_before_.reset(); owner_->pending_after_.reset();
}
}  // namespace lmdj::project_io
