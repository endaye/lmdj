#pragma once

#include <array>
#include <chrono>
#include <filesystem>
#include <stdexcept>
#include <string_view>
#include <lmdj/provider/attempt_store.hpp>

namespace byte_fixture {
inline auto opaque(lmdj::provider::ProviderRegistration registration) {
  for (const auto& capability : registration.capabilities) {
    for (const auto& port : capability.output_artifacts) {
      registration.output_validation.push_back({capability.id, port.name,
          [](const auto&, auto, const auto& binding, auto bytes, auto) {
            using namespace lmdj::foundation;
            return binding.artifact.byte_length == bytes.size()
                ? Result<void>::success()
                : Result<void>::failure({ErrorCode::invalid_argument, "opaque length mismatch"});
          }, 0});
    }
  }
  return registration;
}

inline lmdj::provider::ExecutionOptions options() {
  return {
      [](const lmdj::foundation::ArtifactRef& reference) {
        using Buffer = std::shared_ptr<const std::vector<std::byte>>;
        using lmdj::foundation::Result;
        static const std::array<std::pair<std::string_view, std::string_view>, 3> fixtures{{
            {"fixture-data", "85638a90a2b6d1e2f6be9814c961764f8a1be74871b15d9b05bc1c4017fd38b1"},
            {"a", "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"},
            {"bb", "3b64db95cb55c763391c707108489ae18b4112d783300de38e033b4c98c3deaf"},
        }};
        for (const auto& [payload, digest] : fixtures) {
          if (reference.sha256 == digest) {
            auto bytes = std::make_shared<std::vector<std::byte>>();
            for (const unsigned char value : payload) bytes->push_back(std::byte{value});
            return Result<Buffer>::success(std::move(bytes));
          }
        }
        return Result<Buffer>::failure({lmdj::foundation::ErrorCode::not_found,
                                       "fixture owner has no matching bytes"});
      }, 16777216, 262144, std::make_shared<lmdj::provider::StagingBudget>(67108864)};
}
}  // namespace byte_fixture
