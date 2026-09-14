#include "display.hpp"

#include <algorithm>
#include <cstring>

namespace lmdj::cardputer {

std::string_view phase_label(facade::RuntimePhase phase) noexcept {
  switch (phase) {
    case facade::RuntimePhase::empty: return "empty";
    case facade::RuntimePhase::ready: return "ready";
    case facade::RuntimePhase::running: return "running";
    case facade::RuntimePhase::draining: return "draining";
    case facade::RuntimePhase::stopped: return "stopped";
  }
  return "unknown";
}

std::string_view error_label(HostResult result) noexcept {
  switch (result) {
    case HostResult::ok: return "ok";
    case HostResult::accepted: return "accepted";
    case HostResult::wrong_state: return "wrong state; follow displayed action";
    case HostResult::unsupported_content: return "unsupported content; retry";
    case HostResult::audio_error: return "audio error; stop and retry";
    case HostResult::core_error: return "runtime error; retry";
    case HostResult::input_overflow: return "input overflow; release all keys";
  }
  return "unknown error";
}

void Display::present(const HostStatus& status,
                      const std::array<bool, 4>& pad_active) noexcept {
  frame_.status = status;
  frame_.pad_active = pad_active;
  frame_.phase_label.fill('\0');
  frame_.error_label.fill('\0');
  const auto phase = phase_label(status.phase);
  const auto error = error_label(status.error);
  std::copy_n(phase.begin(), std::min(phase.size(), frame_.phase_label.size() - 1),
              frame_.phase_label.begin());
  std::copy_n(error.begin(), std::min(error.size(), frame_.error_label.size() - 1),
              frame_.error_label.begin());
}

}  // namespace lmdj::cardputer
