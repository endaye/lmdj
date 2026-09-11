#pragma once
#include "driver/usb_serial_jtag.h"
inline std::int64_t esp_timer_get_time() { return static_cast<std::int64_t>(fake_usb::now_us); }
