#pragma once

#include <cstddef>
#include <fstream>
#include <iterator>
#include <map>
#include <string>
#include <vector>

#include <lmdj/analysis/artifact_bytes.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/provider.hpp>

namespace analysis_bench_test {

inline std::vector<std::byte> read_bytes(const std::string& path) {
  std::ifstream stream(path, std::ios::binary);
  const std::vector<char> chars{std::istreambuf_iterator<char>(stream),
                                std::istreambuf_iterator<char>()};
  const auto* first = reinterpret_cast<const std::byte*>(chars.data());
  return {first, first + chars.size()};
}

inline lmdj::analysis::ArtifactByteResolver make_resolver(
    std::map<std::string, std::vector<std::byte>> bytes_by_sha256) {
  return [bytes = std::move(bytes_by_sha256)](
             const lmdj::foundation::ArtifactRef& artifact)
             -> lmdj::foundation::Result<std::vector<std::byte>> {
    const auto found = bytes.find(artifact.sha256);
    if (found == bytes.end()) {
      return lmdj::foundation::Result<std::vector<std::byte>>::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::not_found,
              "resolver has no bytes for artifact",
              {{"sha256", artifact.sha256}},
          });
    }
    return lmdj::foundation::Result<std::vector<std::byte>>::success(
        found->second);
  };
}

struct CaptureSink {
  std::map<std::string, std::vector<std::byte>> written;

  lmdj::provider::ArtifactSink sink() {
    return [this](std::string port,
                  std::span<const std::byte> bytes,
                  std::string media_type)
               -> lmdj::foundation::Result<lmdj::foundation::ArtifactRef> {
      written[port] = {bytes.begin(), bytes.end()};
      return lmdj::foundation::Result<
          lmdj::foundation::ArtifactRef>::success(lmdj::foundation::
                                                      ArtifactRef{
                                                          "placeholder",
                                                          std::move(media_type),
                                                          bytes.size(),
                                                      });
    };
  }
};

}  // namespace analysis_bench_test
