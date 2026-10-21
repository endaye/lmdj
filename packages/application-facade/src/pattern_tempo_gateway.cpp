#include <lmdj/facade/pattern_tempo_gateway.hpp>

#include <utility>

namespace lmdj::facade {
namespace {

using PublicationResult = foundation::Result<audio::PatternPublication>;

PublicationResult refused(const char* reason) {
  return PublicationResult::failure({foundation::ErrorCode::invalid_argument,
      "Pattern tempo publication was refused", {{"reason", reason}}});
}

std::optional<audio::PatternTempoObservation> current_clock(
    const audio::RealtimeEngine& engine, PatternTempoAuthority authority) {
  const auto lifecycle = engine.telemetry();
  if (authority.generation == 0 || authority.start_epoch == 0 ||
      lifecycle.state != audio::RealtimeState::running ||
      lifecycle.start_epoch != authority.start_epoch) return std::nullopt;
  const auto observation = engine.pattern_tempo_observation(authority.generation);
  if (!observation || observation->start_epoch != authority.start_epoch)
    return std::nullopt;
  return observation;
}

PublicationResult admitted(audio::PatternPublication publication) {
  using audio::PatternPublishResult;
  switch (publication.result) {
    case PatternPublishResult::accepted:
      return PublicationResult::success(publication);
    case PatternPublishResult::project_mismatch:
      return refused("tempo_publication_project_mismatch");
    case PatternPublishResult::publication_pending:
      return refused("tempo_publication_pending");
    case PatternPublishResult::pattern_slots_full:
      return refused("tempo_publication_slots_full");
    case PatternPublishResult::publish_queue_full:
      return refused("tempo_publication_queue_full");
    case PatternPublishResult::generation_exhausted:
      return refused("tempo_publication_generation_exhausted");
    case PatternPublishResult::phase_mismatch:
      return refused("tempo_publication_phase_mismatch");
  }
  return PublicationResult::failure({foundation::ErrorCode::internal_error,
      "Pattern tempo publication result is invalid"});
}

}  // namespace

PatternTempoPublicationGateway make_engine_pattern_tempo_publication_gateway(
    audio::RealtimeEngine& engine) {
  return {
      [&engine](const audio::PreparedPatternView& source, std::uint16_t bpm,
                PatternTempoAuthority authority) -> PublicationResult {
        if (!current_clock(engine, authority)) return refused("tempo_source_stale");
        auto derived = source.with_tempo(bpm);
        if (!derived.has_value()) return PublicationResult::failure(derived.error());
        static_cast<void>(engine.reclaim_retired_patterns());
        return admitted(engine.publish_pattern_tempo_transition(
            std::move(derived.value()), authority.generation));
      },
      [&engine](audio::PreparedPatternView&& committed,
                PatternTempoAuthority authority) -> PublicationResult {
        if (!current_clock(engine, authority)) return refused("tempo_source_stale");
        static_cast<void>(engine.reclaim_retired_patterns());
        return admitted(engine.publish_pattern_view_preserving_phase(
            std::move(committed), authority.generation));
      },
      [&engine](PatternTempoAuthority authority) {
        return current_clock(engine, authority);
      },
  };
}

}  // namespace lmdj::facade
