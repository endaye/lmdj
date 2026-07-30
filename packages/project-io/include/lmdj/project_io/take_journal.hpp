#pragma once

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include <lmdj/domain/project.hpp>

namespace lmdj::project_io {

struct ActiveTakeJournal {
  domain::RawTake take;
  std::uint64_t expected_revision;

  bool operator==(const ActiveTakeJournal&) const = default;
};

struct RecoveryCandidate {
  domain::RawTake take;
  std::uint64_t expected_revision;
  std::string reason;
  std::filesystem::path path;

  bool operator==(const RecoveryCandidate&) const = default;
};

class TakeJournal {
 public:
  foundation::Result<void> begin(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id,
      std::uint64_t expected_revision,
      std::uint32_t sample_rate);
  foundation::Result<void> append(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id,
      const domain::RawTakeEvent& event);
  foundation::Result<domain::RawTake> read_active(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id) const;
  foundation::Result<ActiveTakeJournal> read_active_journal(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id) const;
  foundation::Result<std::filesystem::path> seal(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id,
      std::string reason);
  foundation::Result<std::vector<RecoveryCandidate>> list_recoverable(
      const std::filesystem::path& bundle) const;
};

}  // namespace lmdj::project_io
