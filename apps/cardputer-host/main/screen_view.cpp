#include "screen_view.hpp"

#include <algorithm>
#include <charconv>

namespace lmdj::cardputer {
namespace {
void line(ScreenView& view, std::size_t row, std::string_view prefix,
          std::string_view value = {}) noexcept {
  auto& target = view.lines[row];
  const auto first = std::min(prefix.size(), ScreenView::columns);
  std::copy_n(prefix.begin(), first, target.begin());
  const auto count = std::min(value.size(), ScreenView::columns - first);
  std::copy_n(value.begin(), count, target.begin() + first);
}

void number(ScreenView& view, std::size_t row, std::string_view prefix,
            std::uint64_t value) noexcept {
  std::array<char, 20> text{};
  const auto result = std::to_chars(text.data(), text.data() + text.size(), value);
  line(view, row, prefix, {text.data(), static_cast<std::size_t>(result.ptr - text.data())});
}
}  // namespace

ScreenView make_screen_view(const DisplayFrame& frame,
                            const ScreenTransfer& transfer,
                            const ScreenIdentity& identity) noexcept {
  ScreenView view;
  const auto& status = frame.status;
  const bool failed = status.error != HostResult::ok && status.error != HostResult::accepted;
  line(view, 0, "LMDJ  ", failed || transfer.failed ? "ERROR" :
       transfer.receiving ? "RECEIVING" : phase_label(status.phase));
  line(view, 1, "PATTERN ", status.phase == facade::RuntimePhase::running ? "PLAYING" :
       status.phase == facade::RuntimePhase::draining ? "DRAINING" :
       status.phase == facade::RuntimePhase::ready ? "READY" :
       status.phase == facade::RuntimePhase::empty ? "NONE" : "STOPPED");
  number(view, 2, status.muted ? "MUTED  VOL " : "VOLUME ", status.volume);
  line(view, 3, "PAD ACK  A:  S:  D:  F:");
  for (std::size_t pad = 0; pad < 4; ++pad)
    view.lines[3][11 + pad * 4] = pad >= status.pad_count ? '-' :
        frame.pad_active[pad] ? '*' : '.';
  line(view, 4, "USB SESSION ", transfer.session_active ? "ACTIVE" : "NONE");
  if (transfer.receiving) number(view, 5, "RECEIVED BYTES ", transfer.received_bytes);
  else line(view, 5, "RECEIVE ", status.armed ? "ARMED / ESC CANCEL" : "NOT ARMED");
  line(view, 6, "CONTENT ", status.content_bytes == 0 ? std::string_view{"NONE"} :
       std::string_view{status.content_sha256.data(), 12});
  number(view, 7, "BYTES ", status.content_bytes);
  line(view, 8, "BUILD ", identity.product_build);
  line(view, 9, "HOST ", identity.host_version);
  line(view, 10, "SOURCE ", identity.source_revision.substr(0, 12));
  if (transfer.failed) {
    line(view, 11, "TRANSFER FAILED");
    line(view, 12, "ENTER TO ARM; RESEND FROM COMPUTER");
  } else if (failed) {
    line(view, 11, "ERROR ", error_label(status.error));
    line(view, 12, status.error == HostResult::wrong_state && status.content_bytes != 0 ?
         "SPACE: PLAY FIRST; THEN A/S/D/F" : "RELEASE KEYS; ENTER TO RETRY");
  } else {
    line(view, 11, transfer.receiving ? "WAIT FOR TRANSFER; ESC CANCEL" : status.armed ?
         "SEND CONTENT FROM COMPUTER" : status.content_bytes == 0 ?
         "CONNECT COMPUTER; ENTER TO RECEIVE" : "SPACE: PLAY/STOP  A/S/D/F: PADS");
    line(view, 12, "M: MUTE   -/=: VOLUME");
  }
  line(view, 13, "*: PRESS ACK   .: RELEASED   -: NO PAD");
  line(view, 14, status.content_bytes != 0 ? "ENTER STOPS AND CLEARS THIS CONTENT" :
       "CONTENT IS LOST WHEN POWER IS OFF");
  line(view, 15, "FULL CONTENT ID: COMPUTER STATUS");
  return view;
}

}  // namespace lmdj::cardputer
