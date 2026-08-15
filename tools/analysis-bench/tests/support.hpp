#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
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

inline std::vector<std::byte> make_wav_bytes(
    const std::vector<std::int16_t>& samples,
    std::uint32_t sample_rate = 48000) {
  const std::uint32_t data_size =
      static_cast<std::uint32_t>(samples.size() * 2);
  std::vector<std::byte> bytes(44 + data_size);
  auto* p = reinterpret_cast<char*>(bytes.data());
  std::memcpy(p, "RIFF", 4);
  const std::uint32_t riff_size = 36 + data_size;
  std::memcpy(p + 4, &riff_size, 4);
  std::memcpy(p + 8, "WAVEfmt ", 8);
  const std::uint32_t fmt_size = 16;
  std::memcpy(p + 16, &fmt_size, 4);
  const std::uint16_t format = 1;
  const std::uint16_t channels = 1;
  const std::uint32_t byte_rate = sample_rate * 2;
  const std::uint16_t block_align = 2;
  const std::uint16_t bits = 16;
  std::memcpy(p + 20, &format, 2);
  std::memcpy(p + 22, &channels, 2);
  std::memcpy(p + 24, &sample_rate, 4);
  std::memcpy(p + 28, &byte_rate, 4);
  std::memcpy(p + 32, &block_align, 2);
  std::memcpy(p + 34, &bits, 2);
  std::memcpy(p + 36, "data", 4);
  std::memcpy(p + 40, &data_size, 4);
  std::memcpy(p + 44, samples.data(), data_size);
  return bytes;
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
