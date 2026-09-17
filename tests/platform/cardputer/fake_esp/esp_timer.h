#pragma once
#include <cstdint>
namespace fake_timer { inline std::int64_t now_us{}; }
inline std::int64_t esp_timer_get_time() { return fake_timer::now_us; }
