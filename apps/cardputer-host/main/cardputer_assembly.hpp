#pragma once

#include "runtime_host.hpp"

namespace lmdj::cardputer {

// Product Assembly is the only owner of the Cardputer hardware profile and
// product identity. The Host consumes this immutable value; it does not
// choose pins, capacities, or versions itself.
struct CardputerConfiguration {
  const char* product_build{};
  const char* host_version{};
  const char* assembly_sha256{};
  facade::RuntimeConfig runtime;
  HostProfile profile;
  EspAudioSessionConfig audio;
};

CardputerConfiguration cardputer_configuration() noexcept;

}  // namespace lmdj::cardputer
