#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string_view>

#include <lmdj/cooker/sample_analysis.hpp>

namespace lmdj::cooker {

// Metadata-only RIFF/WAVE PCM16 inspection. Feed contiguous bytes in order;
// no input view or PCM/unknown-chunk payload is retained. Successful parsing
// allocates no heap memory, independently of recording length or chunk count.
// Empty feeds are no-ops; errors (including premature finish) are sticky.
// Only finish after the complete input returns metadata. This proves format,
// never Artifact integrity, owner authority or capture completeness.
class WavMetadataInspector final {
 public:
  explicit WavMetadataInspector(std::uint64_t byte_length);
  foundation::Result<void> feed(std::span<const std::byte> bytes);
  foundation::Result<WavMetadata> finish();

 private:
  enum class Stage { riff, chunk_header, format, payload, padding };
  void reject(std::string_view message);
  void end_payload();

  const std::uint64_t byte_length_;
  std::uint64_t received_bytes_{};
  std::uint64_t payload_remaining_{};
  std::uint64_t data_bytes_{};
  std::array<std::byte, 16> header_{};
  std::size_t header_bytes_{};
  std::uint32_t sample_rate_{}, byte_rate_{};
  std::uint16_t audio_format_{}, channels_{}, block_align_{}, bits_per_sample_{};
  bool have_fmt_{}, have_data_{}, needs_padding_{};
  Stage stage_{Stage::riff};
  std::optional<foundation::Error> error_;
};

}  // namespace lmdj::cooker
