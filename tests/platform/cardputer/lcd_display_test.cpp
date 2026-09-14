#include "apps/cardputer-host/main/lcd_display.hpp"
#include "lcd_fake.hpp"
#include "tests/core/support/test.hpp"
#include <cstdio>
#include <string_view>

namespace {
using namespace lmdj::cardputer;
// Synthetic profile; product pin/orientation proof belongs to Assembly tests.
constexpr LcdConfiguration config{2, 1, 2, 3, 4, 5, 6, 40000000, 0, 0, true, false, true, true};
void ownership() {
  fake_lcd::reset();
  {
    LcdDisplay lcd(config);
    LMDJ_CHECK(lcd.install());
    LMDJ_CHECK(fake_lcd::light == 0);
    ScreenView view;
    view.lines[0][0] = 'A';
    LMDJ_CHECK(lcd.poll(view, 0));
    LMDJ_CHECK(fake_lcd::submits == 1);
    view.lines[0][0] = 'Z';
    for (int i = 0; i < 20; ++i) LMDJ_CHECK(lcd.poll(view, 100));
    LMDJ_CHECK(fake_lcd::submits == 1);
    LMDJ_CHECK(fake_lcd::pending != nullptr);
    // Destruction must finish this transfer before releasing its buffer.
  }
  LMDJ_CHECK(fake_lcd::completions == 1);
  LMDJ_CHECK(fake_lcd::frees == 1);
  LMDJ_CHECK(fake_lcd::buses == 0 && fake_lcd::ios == 0 && fake_lcd::panels == 0);
}
void frame() {
  fake_lcd::reset();
  LcdDisplay lcd(config);
  LMDJ_CHECK(lcd.install());
  ScreenView view;
  view.lines[0][0] = 'A';
  for (int stripe = 0; stripe < 15; ++stripe) {
    LMDJ_CHECK(lcd.poll(view, static_cast<std::uint64_t>(stripe)));
    LMDJ_CHECK(fake_lcd::light == 0);
    fake_lcd::complete();
  }
  LMDJ_CHECK(lcd.poll(view, 15));
  LMDJ_CHECK(fake_lcd::light == 1);
  LMDJ_CHECK(fake_lcd::submits == 15);
  // A's top row is .###.; the blank cell spacing and bottom seven rows stay black.
  LMDJ_CHECK(fake_lcd::screen[0] == 0 && fake_lcd::screen[1] == 0xffff);
  LMDJ_CHECK(fake_lcd::screen[4] == 0 && fake_lcd::screen[5] == 0);
  LMDJ_CHECK(fake_lcd::screen.back() == 0);
  LMDJ_CHECK(lcd.poll(view, 1000));
  LMDJ_CHECK(fake_lcd::submits == 15);
}
void failures() {
  for (const auto stage : {"gpio_config", "light_off", "bus_init", "io_new", "panel_new",
                          "panel_reset", "panel_init", "swap", "mirror", "gap", "invert",
                          "display_on", "allocate"}) {
    fake_lcd::reset();
    fake_lcd::fail = stage;
    {
      LcdDisplay lcd(config);
      LMDJ_CHECK(!lcd.install());
      const auto calls = fake_lcd::calls.size();
      LMDJ_CHECK(!lcd.install());
      LMDJ_CHECK(fake_lcd::calls.size() == calls);
    }
    LMDJ_CHECK(fake_lcd::buses == 0 && fake_lcd::ios == 0 && fake_lcd::panels == 0);
    LMDJ_CHECK(fake_lcd::allocations == 0);
  }
}
void draw_failure() {
  fake_lcd::reset();
  LcdDisplay lcd(config);
  LMDJ_CHECK(lcd.install());
  fake_lcd::fail = "draw";
  LMDJ_CHECK(!lcd.poll({}, 0));
  LMDJ_CHECK(!lcd.poll({}, 1));
  LMDJ_CHECK(fake_lcd::submits == 0);
}

void shutdown_hides_stale_state() {
  fake_lcd::reset();
  {
    LcdDisplay lcd(config);
    LMDJ_CHECK(lcd.install());
    for (int stripe = 0; stripe < 15; ++stripe) {
      LMDJ_CHECK(lcd.poll({}, static_cast<std::uint64_t>(stripe)));
      fake_lcd::complete();
    }
    LMDJ_CHECK(lcd.poll({}, 15));
    LMDJ_CHECK(fake_lcd::light == 1);
  }
  LMDJ_CHECK(fake_lcd::light == 0);
}

void frame_uses_one_snapshot() {
  fake_lcd::reset();
  LcdDisplay lcd(config);
  LMDJ_CHECK(lcd.install());
  ScreenView original;
  original.lines[10][0] = 'A';
  auto next = original;
  next.lines[10][0] = 'Z';
  LMDJ_CHECK(lcd.poll(original, 0));
  fake_lcd::complete();
  for (int stripe = 1; stripe < 15; ++stripe) {
    LMDJ_CHECK(lcd.poll(next, static_cast<std::uint64_t>(stripe)));
    fake_lcd::complete();
  }
  LMDJ_CHECK(fake_lcd::screen[80 * 240] == 0); // A, not Z from a mixed frame.
  LMDJ_CHECK(lcd.poll(next, 15));
  LMDJ_CHECK(fake_lcd::submits == 15);
  for (int stripe = 0; stripe < 15; ++stripe) {
    LMDJ_CHECK(lcd.poll(next, static_cast<std::uint64_t>(100 + stripe)));
    fake_lcd::complete();
  }
  LMDJ_CHECK(fake_lcd::screen[80 * 240] == 0xffff); // Next complete frame has Z.
}
}
int main(int argc, char** argv) {
  if (argc != 2) return 2;
  try {
    const std::string_view name = argv[1];
    if (name == "ownership") ownership();
    else if (name == "frame") frame();
    else if (name == "failures") failures();
    else if (name == "draw_failure") draw_failure();
    else if (name == "shutdown") shutdown_hides_stale_state();
    else if (name == "snapshot") frame_uses_one_snapshot();
    else return 2;
  } catch (const std::exception& error) {
    return std::fprintf(stderr, "%s\n", error.what()), 1;
  }
  return 0;
}
