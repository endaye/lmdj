#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

#include <lmdj/domain/project.hpp>
#include <lmdj/project_io/storage_platform.hpp>

namespace lmdj::project_io {

enum class SequenceSessionState : std::uint8_t {
  active,
  switching,
  stopped,
  owner_lost,
  abandoned,
};

struct SequenceFlushRecord {
  std::uint64_t flush_seq{};
  foundation::CommandId command_id;
  foundation::PatternId pattern_id;
  std::uint64_t expected_revision{};
  std::vector<domain::PatternEvent> canonical_events;
  bool completed{};

  bool operator==(const SequenceFlushRecord&) const = default;
};

struct ActiveSequenceJournal {
  foundation::SequenceSessionId session_id;
  foundation::PatternId pattern_id;
  std::uint8_t bars{};
  std::string pattern_fingerprint;
  std::uint64_t expected_revision{};
  std::uint64_t next_flush_seq{};
  SequenceSessionState state{SequenceSessionState::active};
  std::vector<SequenceFlushRecord> flushes;
  std::optional<domain::PadSlotId> armed_capture_slot;

  bool operator==(const ActiveSequenceJournal&) const = default;
};

struct SequenceRecoveryCandidate {
  ActiveSequenceJournal journal;
  std::string reason;
  std::filesystem::path path;

  bool operator==(const SequenceRecoveryCandidate&) const = default;
};

// Returns lowercase SHA-256 of the exact SR-D22 canonical JSON preimage.
std::string sequence_pattern_fingerprint(const domain::Pattern& pattern);

class SequenceJournal {
 public:
  SequenceJournal();
  explicit SequenceJournal(std::shared_ptr<ProjectStoragePlatform> platform);

  foundation::Result<void> begin(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::PatternId pattern_id,
      std::uint8_t bars,
      std::string pattern_fingerprint,
      std::uint64_t expected_revision,
      std::optional<domain::PadSlotId> armed_capture_slot = std::nullopt);
  foundation::Result<ActiveSequenceJournal> read_active(
      const std::filesystem::path& bundle) const;
  foundation::Result<SequenceFlushRecord> append_flush(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::CommandId command_id,
      foundation::PatternId pattern_id,
      std::uint64_t expected_revision,
      std::span<const domain::PatternEvent> events);
  foundation::Result<void> complete_flush(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::uint64_t flush_seq,
      std::uint64_t committed_revision,
      std::string pattern_fingerprint);
  foundation::Result<void> set_state(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      SequenceSessionState state);
  foundation::Result<void> rebase(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::uint64_t expected_revision);
  foundation::Result<void> complete_armed_capture(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      domain::PadSlotId slot,
      std::uint64_t committed_revision);
  foundation::Result<void> disarm_capture(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      domain::PadSlotId slot);
  foundation::Result<void> switch_pattern(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      foundation::PatternId pattern_id,
      std::uint8_t bars,
      std::string pattern_fingerprint,
      std::uint64_t expected_revision);
  foundation::Result<std::filesystem::path> seal(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id,
      std::string reason);
  foundation::Result<std::vector<SequenceRecoveryCandidate>> list_recoverable(
      const std::filesystem::path& bundle) const;
  foundation::Result<void> remove_active_if_complete(
      const std::filesystem::path& bundle,
      foundation::SequenceSessionId session_id);

 private:
  std::shared_ptr<ProjectStoragePlatform> platform_;
};

}  // namespace lmdj::project_io
