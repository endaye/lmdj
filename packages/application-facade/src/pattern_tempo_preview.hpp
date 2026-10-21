#pragma once

#include <functional>
#include <memory>
#include <mutex>

#include <lmdj/facade/pattern_tempo_preview.hpp>
#include <lmdj/project_io/project_store.hpp>

namespace lmdj::facade::detail {

// Non-audio admission shared with Facade workers and vended transport control.
// Never holds the mutex across Store, Engine, controller or user callbacks.
struct PatternTempoPreviewAdmission {
  bool blocks(const std::filesystem::path& path) const;
  bool blocks_any() const;
  void set(const std::filesystem::path& path, bool active);
 private:
  mutable std::mutex mutex_;
  std::filesystem::path path_;
  bool active_{};
};

class PatternTempoPreviewSession final {
 public:
  using Cook = std::function<foundation::Result<
      std::shared_ptr<const cooker::RuntimeSnapshot>>(const domain::ProjectState&)>;
  PatternTempoPreviewSession(std::uint64_t source_id,
      PatternTempoSourceRequest request, audio::PreparedPatternView source,
      audio::RealtimeEngine& engine,
      std::shared_ptr<project_io::ProjectStoragePlatform> platform,
      std::shared_ptr<project_io::AuthoringHistory> history,
      std::shared_ptr<PatternTempoPreviewAdmission> admission, Cook cook);
  ~PatternTempoPreviewSession();

  foundation::Result<PatternTempoPreviewStatus> preview(const PatternTempoPreviewRequest&);
  foundation::Result<PatternTempoPreviewStatus> cancel(PatternTempoPreviewIdentity);
  foundation::Result<PatternTempoPreviewStatus> commit(const PatternTempoPreviewCommit&);
  PatternTempoPreviewStatus service();
  PatternTempoPreviewStatus status() const;
  foundation::Result<audio::PreparedPatternView> retain_source() const;
  bool releasable() const;
  const PatternTempoSourceRequest& request() const { return request_; }
  bool matches(std::uint64_t source_id) const { return source_id == source_id_; }

 private:
  enum class Pending { preview, restore, adopt };
  enum class Intent { none, cancel, commit };
  foundation::Result<void> validate(PatternTempoPreviewIdentity) const;
  bool owner_lost() const;
  void clear_stopped_owned_runtime();
  void lose_source();
  void settle();
  void finish();
  void suspend(foundation::Error);
  void admit(audio::PatternPublication, Pending);
  foundation::Result<void> publish_tempo(std::uint16_t, Pending);

  std::uint64_t source_id_{};
  std::uint64_t preview_id_{};
  std::uint64_t next_preview_id_{1};
  PatternTempoSourceRequest request_;
  audio::PreparedPatternView source_;
  audio::RealtimeEngine& engine_;
  PatternTempoPublicationGateway gateway_;
  std::shared_ptr<project_io::ProjectStoragePlatform> platform_;
  std::shared_ptr<project_io::AuthoringHistory> history_;
  project_io::ProjectStore store_;
  std::shared_ptr<PatternTempoPreviewAdmission> admission_;
  Cook cook_;
  PatternTempoAuthority authority_;
  std::optional<PatternTempoAuthority> pending_authority_;
  Pending pending_kind_{Pending::preview};
  Intent intent_{Intent::none};
  PatternTempoPreviewPhase phase_{PatternTempoPreviewPhase::ready};
  std::uint16_t committed_bpm_{};
  std::uint16_t preview_bpm_{};
  std::uint64_t revision_{};
  std::optional<domain::UpdateSequenceSettings> command_;
  std::optional<std::uint64_t> committed_revision_;
  std::optional<audio::PreparedPatternView> adopting_source_;
  std::optional<foundation::Error> failure_;
  bool suspended_{};
  bool runtime_unsettled_{};
};

}  // namespace lmdj::facade::detail
