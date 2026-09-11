#pragma once

#include <cstdint>
#include <optional>

#include "runtime_host.hpp"

namespace lmdj::cardputer {

// Hardware adapters translate the Cardputer ADV scan codes into this small,
// product-owned vocabulary. No scan code or keyboard library type crosses the
// RuntimeHost boundary.
enum class PhysicalKey : std::uint8_t {
  a,
  s,
  d,
  f,
  space,
  m,
  minus,
  equal,
  enter,
  escape,
  unknown,
};

struct PhysicalKeyEvent {
  PhysicalKey key{PhysicalKey::unknown};
  bool pressed{};
  bool repeat{};
};

// The mapping is deliberately fixed to the D1-approved first slice. It is a
// pure function so a platform scanner can be tested without an ESP-IDF build.
std::optional<Key> map_physical_key(PhysicalKey key) noexcept;

}  // namespace lmdj::cardputer
