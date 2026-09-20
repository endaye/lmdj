#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <vector>

#include <lmdj/domain/project.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

namespace lmdj::facade::detail {

// Builds one immutable receipt from durable input only. Does not enqueue live
// input, consult Project settings, or mutate a journal. The worker owner writes
// the returned receipt and reconciles that same identity on an unknown response.
foundation::Result<project_io::SequenceAdmissionTransfer> build_admission_transfer(
    const project_io::ActiveSequenceJournal& journal,
    foundation::CommandId transfer_id, std::uint64_t last_watermark, bool terminal);
foundation::Result<project_io::SequenceAdmissionTransfer> commit_admission_transfer(
    project_io::SequenceJournal& journals, const std::filesystem::path& bundle,
    foundation::SequenceSessionId session,
    const project_io::SequenceAdmissionIdentity& identity,
    foundation::CommandId transfer_id, std::uint64_t last_watermark, bool terminal);

// Projects the events an open admission would contribute if it ended now,
// through the same conversion `build_admission_transfer` commits. Pure: it
// reads the durable journal, mutates nothing, advances no watermark and mints
// no receipt identity, so calling it cannot consume what a later close
// transfers. `std::nullopt` is an ordinary live state with nothing to show
// yet — no admission, one not yet activated or already sealed, an owner-lost
// journal, or candidates awaiting an unreconciled switch. A genuine
// authority, timing or arithmetic failure is still reported as an error.
// `std::nullopt` is never evidence that the admission is empty, complete or
// safe to close: several of those states are ones `build_admission_transfer`
// reports as an error for the same journal. A caller may use it only to
// decide there is nothing to publish right now. With `finalize` the same
// durable input is read terminally for recovery: owner-lost journals project
// too, and a held press ends after its attack tail (#1515).
foundation::Result<std::optional<std::vector<domain::PatternEvent>>>
project_admission_overlay(const project_io::ActiveSequenceJournal& journal,
                          bool finalize);

enum class PatternAdmissionAdmit : std::uint8_t { retained, live_only };

// Prepared admission owner: closed prepare/activate, post-enqueue candidates,
// deadline/capacity closure at watermark B, and conversion through
// commit_admission_transfer. Live input before the admission fence, after
// closure, or after owner loss stays live-only. A delayed cutoff may still
// drain the retained prefix once.
class PatternAdmissionOwner {
 public:
  using Clock = std::function<std::chrono::steady_clock::time_point()>;

  PatternAdmissionOwner(
      project_io::SequenceJournal& journals, std::filesystem::path bundle,
      foundation::SequenceSessionId session, Clock clock = {});

  foundation::Result<void> prepare(
      const project_io::SequenceAdmissionPreparation& preparation);
  foundation::Result<void> activate(
      const project_io::SequenceAdmissionFence& fence);
  foundation::Result<void> cutoff(
      const project_io::SequenceAdmissionFence& fence);
  foundation::Result<void> retain_switch(
      const project_io::SequencePublicationAuthority& authority);
  // Records the publication generation a live-overlay republication created
  // (#1513), so the cutoff without a switch validates against it.
  foundation::Result<void> retain_overlay_publication(std::uint64_t generation);
  foundation::Result<void> reconcile_switch(project_io::ProjectStore& store);
  foundation::Result<void> drain_source_prefix(
      project_io::ProjectStore& store, foundation::CommandId transfer_id,
      foundation::CommandId flush_id);
  foundation::Result<void> drain_target_segment(
      project_io::ProjectStore& store, foundation::CommandId transfer_id,
      foundation::CommandId flush_id, foundation::CommandId profile_id);
  foundation::Result<PatternAdmissionAdmit> admit(
      const project_io::SequenceAdmissionCandidate& candidate);
  foundation::Result<void> close(
      const project_io::SequenceAdmissionClosure& closure);
  foundation::Result<void> close_requested();
  // Settles a fully closed admission: drains the frozen prefix once, retains
  // the terminal receipt, flushes the final tail to Project Truth exactly
  // once, completes the admission and removes the settled journal. Every step
  // replays under its command identity so a failed close can retry.
  foundation::Result<void> settle_close(
      project_io::ProjectStore& store, foundation::CommandId transfer_id,
      foundation::CommandId terminal_id, foundation::CommandId flush_id);
  foundation::Result<project_io::SequenceAdmissionTransfer> drain(
      foundation::CommandId transfer_id, std::uint64_t last_watermark,
      bool terminal);

 private:
  foundation::Result<void> close_at(
      project_io::SequenceAdmissionCloseReason reason);
  bool deadline_elapsed(
      const project_io::SequenceAdmissionPreparation& preparation) const;

  project_io::SequenceJournal& journals_;
  std::filesystem::path bundle_;
  foundation::SequenceSessionId session_;
  Clock clock_;
  std::optional<std::chrono::steady_clock::time_point> prepared_at_;
  std::optional<project_io::SequenceAdmissionIdentity> identity_;
};

struct PatternOwnedPress {
  std::uint64_t raw_attack_tick{};
  std::uint32_t onset_tick{};
  std::uint8_t velocity{};
  std::optional<std::uint64_t> correlation;
};

// Synchronous, non-owning view of a caller-serialized event overlay. Callers
// supply ticks from their transport anchor; admission and durability stay with
// the journal owner. Legacy Sequence releases omit correlation intentionally.
class PatternEventReducer {
 public:
  PatternEventReducer(
      std::uint8_t bars, bool quantize_enabled, std::uint8_t swing_percent,
      std::uint64_t& generation, std::vector<domain::PatternEvent>& events,
      std::map<domain::PadSlotId, PatternOwnedPress>& pressed);

  void press(domain::PadSlotId slot, std::uint64_t raw_attack_tick,
             std::uint8_t velocity,
             std::optional<std::uint64_t> correlation = std::nullopt);
  bool release(domain::PadSlotId slot, std::uint64_t raw_release_tick,
               std::optional<std::uint64_t> correlation = std::nullopt);
  std::vector<domain::PatternEvent> recoverable_tail() const;
  void finalize_unreleased(bool clear);

 private:
  void merge_pending(domain::PatternEvent event);
  void finalize_pressed(domain::PadSlotId slot, std::uint64_t raw_release_tick,
                        bool remove_press);

  std::uint8_t bars_;
  bool quantize_enabled_;
  std::uint8_t swing_percent_;
  std::uint64_t& generation_;
  std::vector<domain::PatternEvent>& events_;
  std::map<domain::PadSlotId, PatternOwnedPress>& pressed_;
};

}  // namespace lmdj::facade::detail
