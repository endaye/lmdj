#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "display.hpp"
#include "keyboard.hpp"

namespace lmdj::cardputer {

// The queue is the only hand-off from a scanner/USB-like producer to the
// serialized Host executor. Its capacity is fixed and overflow is fail-safe:
// pending commands and local key state are discarded, then Host is stopped.
class InputController final {
 public:
  static constexpr std::size_t queue_capacity = 16;

  InputController(RuntimeHost& host, Display& display) noexcept
      : host_(host), display_(display) {}

  bool enqueue(PhysicalKeyEvent event) noexcept;
  void poll() noexcept;
  std::size_t pending() const noexcept { return count_; }
  bool held(PhysicalKey key) const noexcept;

 private:
  static constexpr std::size_t key_count =
      static_cast<std::size_t>(PhysicalKey::unknown) + 1;
  static constexpr std::size_t index(PhysicalKey key) noexcept {
    return static_cast<std::size_t>(key);
  }
  bool is_pad(PhysicalKey key) const noexcept;
  void clear_queue() noexcept;
  void retry_front(PhysicalKeyEvent event) noexcept;
  void refresh() noexcept;

  RuntimeHost& host_;
  Display& display_;
  std::array<PhysicalKeyEvent, queue_capacity> queue_{};
  std::size_t head_{};
  std::size_t tail_{};
  std::size_t count_{};
  std::array<bool, key_count> held_{};
  bool overflow_{};
};

}  // namespace lmdj::cardputer
