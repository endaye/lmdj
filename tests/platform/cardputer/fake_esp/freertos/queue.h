#pragma once
#include "FreeRTOS.h"
using QueueHandle_t = int*;
inline QueueHandle_t xQueueCreate(unsigned, unsigned) { return new int; }
inline void vQueueDelete(QueueHandle_t q) { delete q; }
inline int xQueueSendFromISR(QueueHandle_t, const void*, BaseType_t*) { return pdTRUE; }
inline int xQueueReceive(QueueHandle_t, void*, int) { return pdFALSE; }
inline unsigned uxQueueMessagesWaiting(QueueHandle_t) { return 0; }
