#include "keyboard.hpp"

namespace lmdj::cardputer {

std::optional<Key> map_physical_key(PhysicalKey key) noexcept {
  switch (key) {
    case PhysicalKey::a: return Key::pad_a;
    case PhysicalKey::s: return Key::pad_s;
    case PhysicalKey::d: return Key::pad_d;
    case PhysicalKey::f: return Key::pad_f;
    case PhysicalKey::space: return Key::play_stop;
    case PhysicalKey::m: return Key::mute;
    case PhysicalKey::minus: return Key::volume_down;
    case PhysicalKey::equal: return Key::volume_up;
    case PhysicalKey::enter: return Key::confirm_receive;
    case PhysicalKey::escape: return Key::cancel_receive;
    case PhysicalKey::unknown: return std::nullopt;
  }
  return std::nullopt;
}

}  // namespace lmdj::cardputer
