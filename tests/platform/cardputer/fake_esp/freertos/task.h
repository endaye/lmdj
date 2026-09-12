#pragma once
#include <cstddef>
std::size_t uxTaskGetStackHighWaterMark(void*);
inline int xPortGetCoreID() { return 1; }
namespace fake_task { inline void (*delay_hook)(){}; }
inline void vTaskDelay(int) { if (fake_task::delay_hook) fake_task::delay_hook(); }
