#pragma once

#include <filesystem>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include <lmdj/domain/authoring_delta.hpp>

namespace lmdj::project_io {

struct AuthoringHistoryStatus {
  std::string session_id;
  std::uint64_t revision{};
  std::size_t undo_count{};
  std::size_t redo_count{};
  std::string undo_label;
  std::string redo_label;
  std::string disabled_reason;
};

// Facade-owned, shared with every Store used by that Facade (including its
// transport controller). Nothing here is written into Project Truth or export.
// Stores lock this before their writer lease and keep the lock through I/O.
class AuthoringHistory final {
 public:
  static constexpr std::size_t kMaximumActions = 100;
  struct Entry {
    domain::AuthoringDelta delta;
    std::string label;
    std::string group;
  };
  struct State {
    std::filesystem::path bundle;
    std::string session_id;
    foundation::ProjectId project_id;
    std::uint64_t revision{};
    std::string fingerprint;
    std::vector<Entry> undo;
    std::vector<Entry> redo;
    // Retained until a multi-commit action closes: cancelling a Performance
    // draft back to its original content must not consume the old Redo branch.
    std::vector<Entry> displaced_redo;
    std::optional<Entry> displaced_oldest;
    std::string disabled_reason;
  };

  class Publication final {
   public:
    Publication() = default;
    Publication(AuthoringHistory* owner, std::shared_ptr<State> before,
                std::shared_ptr<State> after);
    void begin() noexcept;
    void confirm() noexcept;
   private:
    AuthoringHistory* owner_{};
    std::shared_ptr<State> before_;
    std::shared_ptr<State> after_;
  };

  std::unique_lock<std::recursive_mutex> acquire() const;
  void start(const std::filesystem::path& bundle, std::string session_id,
             const domain::ProjectState& state, std::string fingerprint);
  void close();
  void invalidate(const std::filesystem::path& bundle, std::string reason);
  void reconcile(const std::filesystem::path& bundle,
                 const domain::ProjectState& state, const std::string& fingerprint);
  AuthoringHistoryStatus status(const std::filesystem::path& bundle) const;
  foundation::Result<domain::AuthoringDelta> selected(
      const std::filesystem::path& bundle, const std::string& session_id,
      bool redo) const;
  foundation::Result<Publication> prepare(
      const std::filesystem::path& bundle,
      const domain::ProjectState& before, const domain::ProjectState& after,
      const std::string& before_fingerprint, std::string after_fingerprint,
      std::string label, std::string group, std::optional<bool> redo = std::nullopt);
  void seal_group(const std::filesystem::path& bundle);
  std::set<std::string> retained_artifacts(const std::filesystem::path& bundle) const;

 private:
  mutable std::recursive_mutex mutex_;
  std::shared_ptr<State> state_;
  std::shared_ptr<State> pending_before_;
  std::shared_ptr<State> pending_after_;
};
}  // namespace lmdj::project_io
