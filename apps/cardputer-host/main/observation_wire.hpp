#pragma once

#include "audio_diagnostics.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string_view>

namespace lmdj::cardputer::observation_wire {

inline constexpr std::size_t identity_limit = 512;
inline constexpr std::size_t status_prefix_bytes = 146;
inline constexpr std::size_t diagnostics_prefix_bytes = 338;
inline constexpr std::size_t status_max_bytes = status_prefix_bytes + identity_limit;
inline constexpr std::size_t diagnostics_max_bytes = diagnostics_prefix_bytes + identity_limit;

// This is a pre-Contract-freeze codec seam. It is deliberately not included
// in the ESP component or the active transfer opcode dispatch until the
// proposed byte tables receive independent review.
struct Identity {
  std::string_view product_build;
  std::string_view host_version;
  std::string_view revision;
  std::string_view assembly_lock_sha256;
  std::string_view profile_sha256;
};

struct ExtendedStatus {
  bool content_present{};
  bool receiving{};
  std::array<std::byte, 16> boot_nonce{};
  std::uint8_t phase{};
  std::uint8_t error{};
  bool armed{};
  bool muted{};
  std::uint8_t volume{};
  std::uint8_t pad_count{};
  std::array<std::uint8_t, 8> pad_pairs{};
  std::uint64_t maximum_encoded_bytes{};
  std::uint64_t maximum_pcm_bytes{};
  std::uint32_t maximum_frames{};
  std::uint32_t maximum_pads{};
  std::uint32_t maximum_events{};
  std::uint64_t content_bytes{};
  std::array<std::byte, 32> content_sha256{};
  std::array<std::byte, 16> transfer_id{};
  std::uint64_t received_bytes{};
  std::uint64_t expected_bytes{};
  std::uint64_t observation_generation{};
  Identity identity{};
};

struct Diagnostics {
  bool start_succeeded{};
  bool quiescent{};
  bool silent{};
  bool diagnostics_available{};
  std::array<std::byte, 16> boot_nonce{};
  std::uint64_t measured_generation{};
  std::uint64_t content_bytes{};
  std::array<std::byte, 32> content_sha256{};
  std::uint32_t timing_flags{};
  std::uint64_t attempts{};
  std::uint64_t submitted{};
  std::uint64_t stopped{};
  std::uint64_t wait_failed{};
  std::uint64_t convert_failed{};
  std::uint64_t write_failed{};
  std::array<DurationSummary, 6> durations{};
  std::uint64_t recording_samples{};
  std::uint64_t recording_maximum_us{};
  std::uint64_t recording_invalid{};
  Identity identity{};
};

namespace detail {

class Writer final {
 public:
  explicit Writer(std::span<std::byte> output) : output_(output) {}

  bool byte(std::byte value) noexcept {
    if (position_ >= output_.size()) return false;
    output_[position_++] = value;
    return true;
  }

  bool u8(std::uint8_t value) noexcept { return byte(std::byte(value)); }

  bool u16(std::uint16_t value) noexcept {
    return u8(static_cast<std::uint8_t>(value & 0xffU)) &&
           u8(static_cast<std::uint8_t>((value >> 8U) & 0xffU));
  }

  bool u32(std::uint32_t value) noexcept {
    return u16(static_cast<std::uint16_t>(value & 0xffffU)) &&
           u16(static_cast<std::uint16_t>((value >> 16U) & 0xffffU));
  }

  bool u64(std::uint64_t value) noexcept {
    return u32(static_cast<std::uint32_t>(value & 0xffffffffU)) &&
           u32(static_cast<std::uint32_t>((value >> 32U) & 0xffffffffU));
  }

  bool bytes(std::span<const std::byte> values) noexcept {
    if (values.size() > output_.size() - position_) return false;
    std::copy(values.begin(), values.end(), output_.begin() +
                                               static_cast<std::ptrdiff_t>(position_));
    position_ += values.size();
    return true;
  }

  bool patch_u16(std::size_t offset, std::uint16_t value) noexcept {
    if (offset > output_.size() || output_.size() - offset < 2) return false;
    output_[offset] = std::byte(value & 0xffU);
    output_[offset + 1] = std::byte((value >> 8U) & 0xffU);
    return true;
  }

  std::size_t position() const noexcept { return position_; }

 private:
  std::span<std::byte> output_;
  std::size_t position_{};
};

inline bool nonzero(std::span<const std::byte> values) noexcept {
  return std::any_of(values.begin(), values.end(),
                     [](std::byte value) { return value != std::byte{}; });
}

inline bool all_zero(std::span<const std::byte> values) noexcept {
  return std::all_of(values.begin(), values.end(),
                     [](std::byte value) { return value == std::byte{}; });
}

inline bool json_string(Writer& writer, std::string_view value) noexcept {
  if (!writer.u8('"')) return false;
  constexpr char hex[] = "0123456789abcdef";
  for (const unsigned char character : value) {
    switch (character) {
      case '"': if (!writer.bytes({reinterpret_cast<const std::byte*>("\\\""), 2})) return false; break;
      case '\\': if (!writer.bytes({reinterpret_cast<const std::byte*>("\\\\"), 2})) return false; break;
      case '\b': if (!writer.bytes({reinterpret_cast<const std::byte*>("\\b"), 2})) return false; break;
      case '\f': if (!writer.bytes({reinterpret_cast<const std::byte*>("\\f"), 2})) return false; break;
      case '\n': if (!writer.bytes({reinterpret_cast<const std::byte*>("\\n"), 2})) return false; break;
      case '\r': if (!writer.bytes({reinterpret_cast<const std::byte*>("\\r"), 2})) return false; break;
      case '\t': if (!writer.bytes({reinterpret_cast<const std::byte*>("\\t"), 2})) return false; break;
      default:
        if (character < 0x20U) {
          const char escaped[] = {'\\', 'u', '0', '0', hex[character >> 4U],
                                  hex[character & 0x0fU]};
          if (!writer.bytes({reinterpret_cast<const std::byte*>(escaped), 6})) return false;
        } else if (!writer.byte(std::byte(character))) {
          return false;
        }
        break;
    }
  }
  return writer.u8('"');
}

inline bool identity_json(Writer& writer, const Identity& identity) noexcept {
  if (identity.product_build.empty() || identity.host_version.empty() ||
      identity.revision.empty() || identity.assembly_lock_sha256.empty() ||
      identity.profile_sha256.empty()) {
    return false;
  }
  constexpr std::array<std::string_view, 5> keys{
      "product_build", "host_version", "revision", "assembly_lock_sha256",
      "profile_sha256"};
  const std::array<std::string_view, 5> values{
      identity.product_build, identity.host_version, identity.revision,
      identity.assembly_lock_sha256, identity.profile_sha256};
  if (!writer.u8('{')) return false;
  for (std::size_t index = 0; index < keys.size(); ++index) {
    if (index != 0 && !writer.u8(',')) return false;
    if (!json_string(writer, keys[index]) || !writer.u8(':') ||
        !json_string(writer, values[index])) return false;
  }
  return writer.u8('}');
}

inline bool duration(Writer& writer, const DurationSummary& value) noexcept {
  if (!value.p999_available && value.p999_us != 0) return false;
  return writer.u64(value.samples) && writer.u64(value.invalid) &&
         writer.u64(value.maximum_us) && writer.u32(value.p999_us) &&
         writer.u8(value.p999_available ? 1 : 0) && writer.u8(0) &&
         writer.u8(0) && writer.u8(0);
}

inline std::uint16_t read_u16(std::span<const std::byte> bytes,
                              std::size_t offset) noexcept {
  return static_cast<std::uint16_t>(std::to_integer<std::uint8_t>(bytes[offset])) |
         static_cast<std::uint16_t>(
             std::to_integer<std::uint8_t>(bytes[offset + 1]) << 8U);
}

inline std::uint32_t read_u32(std::span<const std::byte> bytes,
                              std::size_t offset) noexcept {
  return static_cast<std::uint32_t>(read_u16(bytes, offset)) |
         static_cast<std::uint32_t>(read_u16(bytes, offset + 2)) << 16U;
}

inline std::uint64_t read_u64(std::span<const std::byte> bytes,
                              std::size_t offset) noexcept {
  std::uint64_t value = 0;
  for (std::size_t index = 0; index < 8; ++index)
    value |= static_cast<std::uint64_t>(
                 std::to_integer<std::uint8_t>(bytes[offset + index]))
             << (8U * index);
  return value;
}

inline bool zeroes(std::span<const std::byte> bytes, std::size_t offset,
                   std::size_t length) noexcept {
  return offset <= bytes.size() && length <= bytes.size() - offset &&
         all_zero(bytes.subspan(offset, length));
}

inline bool expected_identity(std::span<const std::byte> bytes,
                              std::size_t offset, std::uint16_t length,
                              const Identity& expected) noexcept {
  if (length > identity_limit || offset > bytes.size() ||
      length != bytes.size() - offset) return false;
  std::array<std::byte, identity_limit> encoded{};
  Writer writer(encoded);
  if (!identity_json(writer, expected) || writer.position() != length) return false;
  return std::equal(encoded.begin(), encoded.begin() +
                                      static_cast<std::ptrdiff_t>(length),
                    bytes.begin() + static_cast<std::ptrdiff_t>(offset));
}

}  // namespace detail

inline bool encode_extended_status(const ExtendedStatus& status,
                                   std::span<std::byte> output,
                                   std::size_t& written) noexcept {
  written = 0;
  if (output.size() < status_prefix_bytes || !detail::nonzero(status.boot_nonce) ||
      status.pad_count > 4 || status.volume > 10 ||
      (status.content_present && detail::all_zero(status.content_sha256)) ||
      (!status.content_present &&
       (status.content_bytes != 0 || !detail::all_zero(status.content_sha256))) ||
      (!status.receiving &&
       (status.received_bytes != 0 || status.expected_bytes != 0 ||
        !detail::all_zero(status.transfer_id))) ||
      (status.receiving &&
       (status.expected_bytes == 0 || status.received_bytes > status.expected_bytes ||
        !detail::nonzero(status.transfer_id)))) {
    return false;
  }
  for (std::size_t index = 0; index < status.pad_pairs.size(); index += 2) {
    const bool used = index / 2 < status.pad_count;
    if (used && (status.pad_pairs[index] >= 4 || status.pad_pairs[index + 1] >= 16))
      return false;
    if (!used && (status.pad_pairs[index] != 255 || status.pad_pairs[index + 1] != 255))
      return false;
  }

  detail::Writer writer(output);
  const std::uint8_t flags = static_cast<std::uint8_t>(
      (status.content_present ? 1U : 0U) | (status.receiving ? 2U : 0U));
  if (!writer.u16(0) || !writer.u8(1) || !writer.u8(flags) ||
      !writer.bytes(status.boot_nonce) || !writer.u8(status.phase) ||
      !writer.u8(status.error) || !writer.u8(status.armed ? 1 : 0) ||
      !writer.u8(status.muted ? 1 : 0) || !writer.u8(status.volume) ||
      !writer.u8(status.pad_count)) {
    return false;
  }
  for (const auto value : status.pad_pairs)
    if (!writer.u8(value)) return false;
  if (!writer.u16(0) || !writer.u64(status.maximum_encoded_bytes) ||
      !writer.u64(status.maximum_pcm_bytes) || !writer.u32(status.maximum_frames) ||
      !writer.u32(status.maximum_pads) || !writer.u32(status.maximum_events) ||
      !writer.u64(status.content_bytes) || !writer.bytes(status.content_sha256) ||
      !writer.bytes(status.transfer_id) || !writer.u64(status.received_bytes) ||
      !writer.u64(status.expected_bytes) || !writer.u64(status.observation_generation) ||
      !writer.u16(0)) {
    return false;
  }
  const auto identity_start = writer.position();
  if (identity_start != status_prefix_bytes || !detail::identity_json(writer, status.identity))
    return false;
  const auto identity_size = writer.position() - identity_start;
  if (identity_size > identity_limit || !writer.patch_u16(144, static_cast<std::uint16_t>(identity_size)))
    return false;
  written = writer.position();
  return written <= status_max_bytes;
}

inline bool encode_diagnostics(const Diagnostics& diagnostics,
                               std::span<std::byte> output,
                               std::size_t& written) noexcept {
  written = 0;
  if (output.size() < diagnostics_prefix_bytes || !detail::nonzero(diagnostics.boot_nonce) ||
      diagnostics.measured_generation == 0) {
    return false;
  }
  const bool no_measurement = !diagnostics.diagnostics_available;
  if ((no_measurement &&
       (diagnostics.timing_flags != 0 || diagnostics.attempts != 0 ||
        diagnostics.submitted != 0 || diagnostics.stopped != 0 ||
        diagnostics.wait_failed != 0 || diagnostics.convert_failed != 0 ||
        diagnostics.write_failed != 0 || diagnostics.recording_samples != 0 ||
        diagnostics.recording_maximum_us != 0 || diagnostics.recording_invalid != 0)) ||
      (diagnostics.diagnostics_available && diagnostics.timing_flags != 7)) {
    return false;
  }
  if (no_measurement) {
    for (const auto& value : diagnostics.durations) {
      if (value.samples != 0 || value.invalid != 0 || value.maximum_us != 0 ||
          value.p999_us != 0 || value.p999_available) return false;
    }
  }

  detail::Writer writer(output);
  const std::uint8_t flags = static_cast<std::uint8_t>(
      (diagnostics.start_succeeded ? 1U : 0U) |
      (diagnostics.quiescent ? 2U : 0U) |
      (diagnostics.silent ? 4U : 0U) |
      (diagnostics.diagnostics_available ? 8U : 0U));
  if (!writer.u16(0) || !writer.u8(1) || !writer.u8(flags) ||
      !writer.bytes(diagnostics.boot_nonce) || !writer.u64(diagnostics.measured_generation) ||
      !writer.u64(diagnostics.content_bytes) || !writer.bytes(diagnostics.content_sha256) ||
      !writer.u32(diagnostics.timing_flags) || !writer.u64(diagnostics.attempts) ||
      !writer.u64(diagnostics.submitted) || !writer.u64(diagnostics.stopped) ||
      !writer.u64(diagnostics.wait_failed) || !writer.u64(diagnostics.convert_failed) ||
      !writer.u64(diagnostics.write_failed)) {
    return false;
  }
  for (const auto& value : diagnostics.durations)
    if (!detail::duration(writer, value)) return false;
  if (!writer.u64(diagnostics.recording_samples) ||
      !writer.u64(diagnostics.recording_maximum_us) ||
      !writer.u64(diagnostics.recording_invalid) || !writer.u16(0)) {
    return false;
  }
  const auto identity_start = writer.position();
  if (identity_start != diagnostics_prefix_bytes ||
      !detail::identity_json(writer, diagnostics.identity)) return false;
  const auto identity_size = writer.position() - identity_start;
  if (identity_size > identity_limit ||
      !writer.patch_u16(336, static_cast<std::uint16_t>(identity_size))) return false;
  written = writer.position();
  return written <= diagnostics_max_bytes;
}

// Proposal-only decoders used by golden vectors. They are intentionally not
// wired into the active transfer endpoint until the independent Contract
// review freezes these formats.
inline bool validate_extended_status(std::span<const std::byte> bytes,
                                     const Identity& expected_identity) noexcept {
  if (bytes.size() < status_prefix_bytes || bytes.size() > status_max_bytes ||
      detail::read_u16(bytes, 0) != 0 ||
      std::to_integer<std::uint8_t>(bytes[2]) != 1)
    return false;
  const auto flags = std::to_integer<std::uint8_t>(bytes[3]);
  if ((flags & 0xfcU) != 0 || !detail::nonzero(bytes.subspan(4, 16))) return false;
  const auto armed = std::to_integer<std::uint8_t>(bytes[22]);
  const auto muted = std::to_integer<std::uint8_t>(bytes[23]);
  const auto volume = std::to_integer<std::uint8_t>(bytes[24]);
  const auto pad_count = std::to_integer<std::uint8_t>(bytes[25]);
  if (armed > 1 || muted > 1 || volume > 10 || pad_count > 4 ||
      !detail::zeroes(bytes, 34, 2)) return false;
  for (std::size_t index = 0; index < 8; index += 2) {
    const auto bank = std::to_integer<std::uint8_t>(bytes[26 + index]);
    const auto pad = std::to_integer<std::uint8_t>(bytes[27 + index]);
    if (index / 2 < pad_count) {
      if (bank >= 4 || pad >= 16) return false;
    } else if (bank != 255 || pad != 255) {
      return false;
    }
  }
  const auto content_present = (flags & 1U) != 0;
  const auto receiving = (flags & 2U) != 0;
  const auto content_bytes = detail::read_u64(bytes, 64);
  const auto received_bytes = detail::read_u64(bytes, 120);
  const auto expected_bytes = detail::read_u64(bytes, 128);
  const auto transfer = bytes.subspan(104, 16);
  if ((!content_present &&
       (content_bytes != 0 || !detail::all_zero(bytes.subspan(72, 32)))) ||
      (!receiving &&
       (received_bytes != 0 || expected_bytes != 0 || !detail::all_zero(transfer))) ||
      (receiving &&
       (expected_bytes == 0 || received_bytes > expected_bytes ||
        !detail::nonzero(transfer)))) return false;
  const auto identity_length = detail::read_u16(bytes, 144);
  return detail::expected_identity(bytes, 146, identity_length, expected_identity);
}

inline bool validate_diagnostics(std::span<const std::byte> bytes,
                                 const Identity& expected_identity) noexcept {
  if (bytes.size() < diagnostics_prefix_bytes || bytes.size() > diagnostics_max_bytes ||
      detail::read_u16(bytes, 0) != 0 ||
      std::to_integer<std::uint8_t>(bytes[2]) != 1 ||
      !detail::nonzero(bytes.subspan(4, 16)) || detail::read_u64(bytes, 20) == 0)
    return false;
  const auto flags = std::to_integer<std::uint8_t>(bytes[3]);
  if ((flags & 0xf0U) != 0) return false;
  const bool available = (flags & 8U) != 0;
  const auto timing_flags = detail::read_u32(bytes, 68);
  if ((available && timing_flags != 7) || (!available && timing_flags != 0)) return false;
  for (std::size_t index = 0; index < 6; ++index) {
    const auto offset = 120 + index * 32;
    const auto p999 = detail::read_u32(bytes, offset + 24);
    const auto available_percentile =
        std::to_integer<std::uint8_t>(bytes[offset + 28]);
    if (available_percentile > 1 || (!available_percentile && p999 != 0) ||
        !detail::zeroes(bytes, offset + 29, 3)) return false;
    if (!available &&
        (!detail::zeroes(bytes, offset, 28) || available_percentile != 0)) return false;
  }
  if (!available &&
      (!detail::zeroes(bytes, 72, 48) || !detail::zeroes(bytes, 312, 24)))
    return false;
  const auto identity_length = detail::read_u16(bytes, 336);
  return detail::expected_identity(bytes, 338, identity_length, expected_identity);
}

}  // namespace lmdj::cardputer::observation_wire
