#pragma once

#include <lmdj/analysis/artifact_bytes.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::analysis_bench {

provider::ProviderRegistration loudness_registration(
    analysis::ArtifactByteResolver resolver);

}  // namespace lmdj::analysis_bench
