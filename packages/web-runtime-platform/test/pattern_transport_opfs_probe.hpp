#pragma once

#include <atomic>
#include <lmdj/facade/pattern_transport_ports.hpp>

namespace lmdj::web_runtime::test {
inline constexpr auto kTransportProbeBytes = "retained OPFS transport completion";
std::unique_ptr<facade::PatternTransportWorkOwner> make_transport_opfs_probe_owner(
    std::atomic<std::uint32_t>& reached, std::atomic<std::uint32_t>& release);
}  // namespace lmdj::web_runtime::test
