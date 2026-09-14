#pragma once

#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/facade/pattern_transport_ports.hpp>
#include <lmdj/project_io/sequence_journal.hpp>

#include "pattern_admission_controller.hpp"

namespace lmdj::facade::detail {

class PatternTransportAudioPort {
 public:
  virtual ~PatternTransportAudioPort() = default;
  virtual audio::PatternTransportSubmit submit(
      const audio::PatternTransportCommand& command) = 0;
  virtual std::optional<audio::PatternTransportReceipt> inspect(
      std::uint64_t generation, std::uint64_t epoch) const = 0;
  virtual bool acknowledge(std::uint64_t generation, std::uint64_t epoch) = 0;
  virtual std::uint64_t pattern_generation() const = 0;
};

class PatternTransportCoordinator {
 public:
  PatternTransportCoordinator(
      PatternTransportAudioPort& audio, project_io::SequenceJournal& journals,
      std::filesystem::path bundle, foundation::SequenceSessionId session,
      foundation::ProjectId project, foundation::PatternId pattern,
      std::uint64_t runtime_generation);

  PatternTransportSubmit request(const PatternTransportRequest& request);
  PatternTransportStatus inspect() const;
  foundation::Result<void> continue_operation();

 private:
  audio::PatternTransportAction audio_action(
      PatternTransportIntent intent) const;
  project_io::SequenceAdmissionFence fence_from(
      const audio::PatternTransportReceipt& receipt,
      project_io::SequenceFenceKind kind,
      const foundation::CommandId& command_id) const;
  foundation::Result<void> apply_receipt(
      const audio::PatternTransportReceipt& receipt,
      const PatternTransportRequest& request);

  PatternTransportAudioPort& audio_;
  PatternAdmissionOwner owner_;
  foundation::SequenceSessionId session_;
  foundation::ProjectId project_;
  foundation::PatternId pattern_;
  std::uint64_t runtime_generation_;
  bool playing_{};
  bool recording_{};
  std::uint64_t origin_frame_{};
  std::optional<PatternTransportRequest> pending_;
  std::optional<PatternTransportRequest> last_;
  std::map<foundation::CommandId, PatternTransportRequest> retained_;
  PatternTransportPhase phase_{PatternTransportPhase::idle};
  std::optional<foundation::Error> error_;
};

}  // namespace lmdj::facade::detail
