#include "input_controller.hpp"

namespace lmdj::cardputer {

bool InputController::is_pad(PhysicalKey key) const noexcept {
  return key == PhysicalKey::a || key == PhysicalKey::s ||
         key == PhysicalKey::d || key == PhysicalKey::f;
}

bool InputController::held(PhysicalKey key) const noexcept {
  return key != PhysicalKey::unknown && held_[index(key)];
}

bool InputController::enqueue(PhysicalKeyEvent event) noexcept {
  const auto mapped = map_physical_key(event.key);
  if (!mapped) return false;
  const auto key_index = index(event.key);
  if (event.pressed && (event.repeat || held_[key_index])) return true;
  if (!event.pressed && !held_[key_index]) return true;
  if (count_ == queue_.size()) {
    overflow_ = true;
    return false;
  }
  queue_[tail_] = event;
  tail_ = (tail_ + 1) % queue_.size();
  ++count_;
  held_[key_index] = event.pressed;
  return true;
}

void InputController::clear_queue() noexcept {
  head_ = tail_ = count_ = 0;
}

void InputController::retry_front(PhysicalKeyEvent event) noexcept {
  head_ = (head_ + queue_.size() - 1) % queue_.size();
  queue_[head_] = event;
  ++count_;
}

void InputController::refresh() noexcept {
  display_.present(host_.read_status(), active_);
}

void InputController::poll() noexcept {
  host_.poll();
  if (overflow_) {
    clear_queue();
    held_.fill(false);
    active_.fill(false);
    overflow_ = false;
    (void)host_.handle_key({Key::overflow, true});
    refresh();
    return;
  }

  // Bound executor work to the number of commands present at entry. A queue
  // full result is retained at the front for the caller's next poll.
  const auto limit = count_;
  for (std::size_t processed = 0; processed < limit && count_ != 0; ++processed) {
    const auto event = queue_[head_];
    head_ = (head_ + 1) % queue_.size();
    --count_;
    const auto mapped = map_physical_key(event.key);
    if (!mapped) continue;
    // Command keys are edge-triggered actions. Their release is only a
    // physical bookkeeping event; forwarding it would execute the command a
    // second time (for example, Enter release would re-enter receive mode and
    // can clear an already armed Host).
    if (!is_pad(event.key) && !event.pressed) continue;
    const auto result = host_.handle_key({*mapped, event.pressed});
    const auto status = host_.read_status();
    if (result == HostResult::core_error &&
        status.core_result == facade::RuntimeResult::queue_full) {
      retry_front(event);
      break;
    }
    if (is_pad(event.key) && result == HostResult::accepted) {
      active_[index(event.key)] = event.pressed;
    } else if (result != HostResult::accepted && result != HostResult::ok) {
      held_[index(event.key)] = false;
    }
  }
  refresh();
}

}  // namespace lmdj::cardputer
