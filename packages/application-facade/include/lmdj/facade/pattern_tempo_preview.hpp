#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>

#include <lmdj/domain/commands.hpp>
#include <lmdj/facade/pattern_tempo_gateway.hpp>

namespace lmdj::facade {

// Nonzero Core-issued IDs are scoped to one Application lifetime. Zero starts
// a new preview turn; it never addresses an existing one. Hosts must also fence
// their Application/session lifetime before delivering an asynchronous request.
struct PatternTempoSourceRequest {
  std::filesystem::path project_path;
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t expected_revision{};
  PatternTempoAuthority authority;
};

struct PatternTempoPreviewIdentity {
  std::uint64_t source_id{};
  std::uint64_t preview_id{};
};

struct PatternTempoPreviewRequest {
  PatternTempoPreviewIdentity identity;
  std::uint16_t bpm{};
};

struct PatternTempoPreviewCommit {
  PatternTempoPreviewIdentity identity;
  domain::CommandMeta meta;
};

enum class PatternTempoPreviewPhase : std::uint8_t {
  ready,
  preview_pending,
  preview_refused,
  previewing,
  cancelling,
  cancelled,
  commit_unknown,
  committed_pending,
  committed,
  source_lost,
};

struct PatternTempoPreviewStatus {
  PatternTempoPreviewIdentity identity;
  PatternTempoPreviewPhase phase{PatternTempoPreviewPhase::ready};
  std::uint16_t committed_bpm{};
  std::uint16_t preview_bpm{};
  // Last known committed Truth and the retained audio source can have different
  // revisions while a durable save waits for actual same-BPM adoption.
  std::uint64_t project_revision{};
  std::uint64_t source_revision{};
  // Generation being awaited, otherwise the actual source generation. A
  // retired, unapplied publication is not a current source. `applied` can name
  // the real predecessor while pending; no anchor is predicted or rounded.
  std::uint64_t publication_generation{};
  std::optional<foundation::CommandId> command_id;
  std::optional<std::uint64_t> committed_revision;
  std::optional<audio::PatternTempoObservation> applied;
  std::optional<foundation::Error> failure;
};

}  // namespace lmdj::facade
