#pragma once
#include "FreeRTOS.h"
#include <cstring>
#include <deque>
#include <vector>
struct FakeQueue { unsigned capacity, item_size; std::deque<std::vector<unsigned char>> items; };
using QueueHandle_t = FakeQueue*;
inline QueueHandle_t xQueueCreate(unsigned count, unsigned size) { return new FakeQueue{count, size, {}}; }
inline void vQueueDelete(QueueHandle_t q) { delete q; }
inline int xQueueSendFromISR(QueueHandle_t q, const void* item, BaseType_t*) {
  if (q->items.size() == q->capacity) return pdFALSE;
  const auto* bytes = static_cast<const unsigned char*>(item);
  q->items.emplace_back(bytes, bytes + q->item_size); return pdTRUE;
}
inline int xQueueReceive(QueueHandle_t q, void* item, int) {
  if (q->items.empty()) return pdFALSE;
  std::memcpy(item, q->items.front().data(), q->item_size);
  q->items.pop_front(); return pdTRUE;
}
inline unsigned uxQueueMessagesWaiting(QueueHandle_t q) { return static_cast<unsigned>(q->items.size()); }
