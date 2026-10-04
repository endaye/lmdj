#pragma once
#include <cstdint>
inline std::uint32_t esp_random() { static std::uint32_t sequence = 1; return sequence++; }
