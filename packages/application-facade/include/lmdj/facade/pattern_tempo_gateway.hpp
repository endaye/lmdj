#pragma once

#include <cstdint>
#include <functional>
#include <optional>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::facade {

struct PatternTempoAuthority {
  std::uint64_t start_epoch{};
  std::uint64_t generation{};

  bool operator==(const PatternTempoAuthority&) const = default;
};

// Serialized control only, concurrent with render. A successful publication
// Result is admission, not actual apply: observe its returned generation in
// the same start epoch before claiming an effective frame or musical anchor.
// Retain the original Core-prepared source; recooking the same IDs does not
// establish the Native tempo primitive's immutable material identity.
struct PatternTempoPublicationGateway {
  using Publish = std::function<foundation::Result<audio::PatternPublication>(
      const audio::PreparedPatternView&, std::uint16_t, PatternTempoAuthority)>;
  using Adopt = std::function<foundation::Result<audio::PatternPublication>(
      audio::PreparedPatternView&&, PatternTempoAuthority)>;
  using Observe = std::function<std::optional<audio::PatternTempoObservation>(
      PatternTempoAuthority)>;

  Publish publish;
  // Later committed revision adoption uses same-BPM phase preservation; this
  // callback does not author or restore a previously committed tempo itself.
  // A refusal leaves the supplied view unconsumed.
  Adopt adopt;
  Observe observe;
};

// Engine must outlive the gateway. Destruction and every callback run on its
// serialized control owner; no callback/reclaim/source parser is added to audio.
// The caller owns preview/Project identity, authoring and terminal disposition.
PatternTempoPublicationGateway make_engine_pattern_tempo_publication_gateway(
    audio::RealtimeEngine& engine);

}  // namespace lmdj::facade
