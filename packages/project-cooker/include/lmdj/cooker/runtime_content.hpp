#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/cooker/runtime_content_types.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::cooker {

inline constexpr std::string_view kRuntimeContentContract =
    "lmdj.runtime-content.v1";
inline constexpr std::string_view kRuntimeContentContractVersion = "1.0.0";
inline constexpr std::string_view kRuntimePcmMediaType =
    "application/vnd.lmdj.runtime-pcm16le";

struct EncodedRuntimeContent {
  RuntimeContentIdentity identity;
  std::vector<std::byte> bytes;
};

foundation::Result<EncodedRuntimeContent> encode_runtime_content(
    const RuntimeSnapshot& snapshot,
    const RuntimeContentLimits& limits);

// Runs the same complete validator as decode, without allocating PCM or
// count-sized tables. The input must remain immutable for the whole call.
foundation::Result<RuntimeContentFootprint> inspect_runtime_content(
    std::span<const std::byte> bytes,
    const RuntimeContentIdentity& expected,
    const RuntimeContentLimits& limits);

// Control-side only. The input must remain valid and immutable for the call;
// the returned Snapshot owns its data. No Engine publication occurs here.
foundation::Result<std::shared_ptr<const RuntimeSnapshot>>
decode_runtime_content(
    std::span<const std::byte> bytes,
    const RuntimeContentIdentity& expected,
    const RuntimeContentLimits& limits);

}  // namespace lmdj::cooker
