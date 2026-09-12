#include "apps/cardputer-host/main/screen_view.hpp"
#include "tests/core/support/test.hpp"

#include <algorithm>
#include <cstdio>
#include <limits>
#include <string>
#include <string_view>

namespace {
using namespace lmdj::cardputer;
using lmdj::facade::RuntimePhase;
constexpr ScreenIdentity identity{"test-build", "test-host", "abcdef1234567890"};
std::string_view row(const ScreenView& view, std::size_t index) {
  return view.lines[index].data();
}

void empty_has_next_action() {
  const auto view = make_screen_view({}, {}, identity);
  LMDJ_CHECK(row(view, 0) == "LMDJ  empty");
  LMDJ_CHECK(row(view, 6) == "CONTENT NONE");
  LMDJ_CHECK(row(view, 11) == "CONNECT COMPUTER; ENTER TO RECEIVE");
  LMDJ_CHECK(row(view, 8) == "BUILD test-build");
  LMDJ_CHECK(row(view, 9) == "HOST test-host");
  LMDJ_CHECK(row(view, 10) == "SOURCE abcdef123456");
}

void lifecycle_and_receipt_view() {
  DisplayFrame frame;
  frame.status.pad_count = 4;
  frame.status.content_bytes = 96808;
  frame.status.content_sha256.fill('b');
  frame.pad_active = {true, false, true, false};
  for (const auto phase : {RuntimePhase::ready, RuntimePhase::running,
                          RuntimePhase::draining, RuntimePhase::stopped}) {
    frame.status.phase = phase;
    const auto view = make_screen_view(frame, {}, identity);
    LMDJ_CHECK(row(view, 0) == std::string("LMDJ  ") + std::string(phase_label(phase)));
    LMDJ_CHECK(view.lines[3][11] == '*');
    LMDJ_CHECK(view.lines[3][15] == '.');
    LMDJ_CHECK(view.lines[3][19] == '*');
    LMDJ_CHECK(view.lines[3][23] == '.');
    LMDJ_CHECK(row(view, 6) == "CONTENT bbbbbbbbbbbb");
    LMDJ_CHECK(row(view, 7) == "BYTES 96808");
    LMDJ_CHECK(row(view, 14) == "ENTER STOPS AND CLEARS THIS CONTENT");
    if (phase == RuntimePhase::draining) LMDJ_CHECK(row(view, 1) == "PATTERN DRAINING");
  }
}

void transfer_failure_and_progress() {
  DisplayFrame frame;
  frame.status.armed = true;
  auto view = make_screen_view(frame, {true, true, 128, false}, identity);
  LMDJ_CHECK(row(view, 0) == "LMDJ  RECEIVING");
  LMDJ_CHECK(row(view, 5) == "RECEIVED BYTES 128");
  view = make_screen_view(frame, {true, false, 128, true}, identity);
  LMDJ_CHECK(row(view, 0) == "LMDJ  ERROR");
  LMDJ_CHECK(row(view, 12) == "ENTER TO ARM; RESEND FROM COMPUTER");
  LMDJ_CHECK(row(view, 6) == "CONTENT NONE");
}

void text_is_bounded() {
  DisplayFrame frame;
  frame.status.error = HostResult::input_overflow;
  frame.status.content_bytes = std::numeric_limits<std::uint64_t>::max();
  frame.status.content_sha256.fill('f');
  const std::string oversized(200, 'x');
  const auto view = make_screen_view(frame, {}, {oversized, oversized, oversized});
  for (const auto& text : view.lines) LMDJ_CHECK(text.back() == '\0');
  LMDJ_CHECK(row(view, 8).size() == ScreenView::columns);
  LMDJ_CHECK(row(view, 7) == "BYTES 18446744073709551615");
  LMDJ_CHECK(row(view, 12) == "RELEASE KEYS; ENTER TO RETRY");
}
}

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  try {
    const std::string_view name = argv[1];
    if (name == "empty") empty_has_next_action();
    else if (name == "lifecycle") lifecycle_and_receipt_view();
    else if (name == "transfer") transfer_failure_and_progress();
    else if (name == "bounds") text_is_bounded();
    else return 2;
  } catch (const std::exception& error) {
    return std::fprintf(stderr, "%s\n", error.what()), 1;
  }
  return 0;
}
