#pragma once
#include <cstddef>
std::size_t uxTaskGetStackHighWaterMark(void*);
inline int xPortGetCoreID() { return 1; }
inline void vTaskDelay(int) {}
