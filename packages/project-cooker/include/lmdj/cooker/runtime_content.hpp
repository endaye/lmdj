#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::cooker {

inline constexpr std::string_view kRuntimeContentContract =
    "lmdj.runtime-content.v1";
inline constexpr std::string_view kRuntimeContentContractVersion = "1.0.0";
inline constexpr std::string_view kRuntimePcmMediaType =
    "application/vnd.lmdj.runtime-pcm16le";

struct RuntimeContentIdentity {
  std::string sha256;
  std::uint64_t byte_length{};

  bool operator==(const RuntimeContentIdentity&) const = default;
};

// Caller-owned codec allowances, not an Engine/FX/device memory budget. Zero
// is never unlimited. Bytes count unique decoded PCM, not a per-Pad expansion.
struct RuntimeContentLimits {
  std::uint64_t maximum_encoded_bytes{};
  std::uint64_t maximum_pcm_bytes{};
  std::uint32_t maximum_sample_frames{};
  std::uint32_t maximum_pads{};
  std::uint32_t maximum_events{};
};

struct EncodedRuntimeContent {
  RuntimeContentIdentity identity;
  std::vector<std::byte> bytes;
};

foundation::Result<EncodedRuntimeContent> encode_runtime_content(
    const RuntimeSnapshot& snapshot,
    const RuntimeContentLimits& limits);

// Control-side only. The input must remain valid and immutable for the call;
// the returned Snapshot owns its data. No Engine publication occurs here.
foundation::Result<std::shared_ptr<const RuntimeSnapshot>>
decode_runtime_content(
    std::span<const std::byte> bytes,
    const RuntimeContentIdentity& expected,
    const RuntimeContentLimits& limits);

}  // namespace lmdj::cooker
