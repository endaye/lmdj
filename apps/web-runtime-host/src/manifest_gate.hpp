#pragma once

#include <cstddef>
#include <cstdint>
#include <mutex>
#include <span>
#include <string_view>


namespace lmdj::web_host {

inline constexpr std::size_t kHostManifestMaximumBytes = 65'536;

struct ManifestExpectation {
  std::string_view product_build;
  std::string_view host_version;
  std::uint32_t protocol_version;
};

enum class ManifestGateStatus : std::uint8_t {
  accepted,
  protocol_mismatch,
};

class ManifestGate final {
 public:
  ManifestGateStatus initialize(
      std::span<const std::byte> canonical_bytes,
      std::string_view expected_sha256,
      ManifestExpectation expected) noexcept;

  bool begin_runtime() noexcept;
  bool ready() const noexcept;

 private:
  enum class Phase : std::uint8_t {
    awaiting_manifest,
    accepted,
    running,
    rejected,
  };

  mutable std::mutex mutex_;
  Phase phase_ = Phase::awaiting_manifest;
};

}  // namespace lmdj::web_host
