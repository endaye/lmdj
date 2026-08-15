#pragma once

#include <cstddef>
#include <functional>
#include <vector>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::analysis {

// Prototype-only bridge: the Capability Contract delivers ArtifactRef inputs
// without bytes and the SDK has no input-bytes resolver yet (open issue in
// docs/architecture/2026-08-01-provider-multi-port-contract-decision.md), so
// the bench Host injects byte access at composition time.
using ArtifactByteResolver =
    std::function<foundation::Result<std::vector<std::byte>>(
        const foundation::ArtifactRef&)>;

}  // namespace lmdj::analysis
