#include "lcd_display.hpp"

#ifdef ESP_PLATFORM
#include <algorithm>
#include <array>
#include <atomic>
#include <exception>

// IDF's C hardware headers contain anonymous register structs. Keep the
// exception at the vendor includes; project code retains -Wpedantic -Werror.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wpedantic"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_vendor.h"
#pragma GCC diagnostic pop

namespace lmdj::cardputer {
namespace {
// Five column, seven row monochrome glyphs. Lowercase is displayed uppercase;
// unknown input uses a visible question mark rather than indexing past a font.
constexpr std::array<std::array<std::uint8_t, 5>, 36> glyphs{{
  {{0x3e,0x51,0x49,0x45,0x3e}},{{0,0x42,0x7f,0x40,0}},
  {{0x42,0x61,0x51,0x49,0x46}},{{0x21,0x41,0x45,0x4b,0x31}},
  {{0x18,0x14,0x12,0x7f,0x10}},{{0x27,0x45,0x45,0x45,0x39}},
  {{0x3c,0x4a,0x49,0x49,0x30}},{{1,0x71,9,5,3}},
  {{0x36,0x49,0x49,0x49,0x36}},{{6,0x49,0x49,0x29,0x1e}},
  {{0x7e,0x11,0x11,0x11,0x7e}},{{0x7f,0x49,0x49,0x49,0x36}},
  {{0x3e,0x41,0x41,0x41,0x22}},{{0x7f,0x41,0x41,0x22,0x1c}},
  {{0x7f,0x49,0x49,0x49,0x41}},{{0x7f,9,9,9,1}},
  {{0x3e,0x41,0x49,0x49,0x7a}},{{0x7f,8,8,8,0x7f}},
  {{0,0x41,0x7f,0x41,0}},{{0x20,0x40,0x41,0x3f,1}},
  {{0x7f,8,0x14,0x22,0x41}},{{0x7f,0x40,0x40,0x40,0x40}},
  {{0x7f,2,0x0c,2,0x7f}},{{0x7f,4,8,0x10,0x7f}},
  {{0x3e,0x41,0x41,0x41,0x3e}},{{0x7f,9,9,9,6}},
  {{0x3e,0x41,0x51,0x21,0x5e}},{{0x7f,9,0x19,0x29,0x46}},
  {{0x46,0x49,0x49,0x49,0x31}},{{1,1,0x7f,1,1}},
  {{0x3f,0x40,0x40,0x40,0x3f}},{{0x1f,0x20,0x40,0x20,0x1f}},
  {{0x3f,0x40,0x38,0x40,0x3f}},{{0x63,0x14,8,0x14,0x63}},
  {{7,8,0x70,8,7}},{{0x61,0x51,0x49,0x45,0x43}},
}};

std::array<std::uint8_t, 5> glyph(char c) noexcept {
  if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
  if (c >= '0' && c <= '9') return glyphs[static_cast<std::size_t>(c - '0')];
  if (c >= 'A' && c <= 'Z') return glyphs[10 + static_cast<std::size_t>(c - 'A')];
  switch (c) {
    case '\0': case ' ': return {};
    case ':': return {0,0x36,0x36,0,0};
    case ';': return {0,0x56,0x36,0,0};
    case '.': return {0,0x60,0x60,0,0};
    case '-': return {8,8,8,8,8};
    case '/': return {0x20,0x10,8,4,2};
    case '=': return {0x14,0x14,0x14,0x14,0x14};
    case '*': return {0x14,8,0x3e,8,0x14};
    default: return {2,1,0x51,9,6};
  }
}
}  // namespace

struct LcdDisplay::Impl {
  static constexpr int width = 240, height = 135, stripe_rows = 9;
  explicit Impl(LcdConfiguration supplied) : config(supplied) {}
  LcdConfiguration config;
  esp_lcd_panel_io_handle_t io{};
  esp_lcd_panel_handle_t panel{};
  std::uint16_t* pixels{};
  std::atomic<bool> busy{};
  static_assert(std::atomic<bool>::is_always_lock_free);
  ScreenView snapshot;
  std::uint64_t next_frame_ms{};
  int y{};
  bool bus_owned{}, backlight_configured{}, installed{}, failed{}, have_frame{};

  static bool completed(esp_lcd_panel_io_handle_t,
                        esp_lcd_panel_io_event_data_t*, void* context) noexcept {
    static_cast<Impl*>(context)->busy.store(false, std::memory_order_release);
    return false;
  }

  ~Impl() {
    // Hide a stale success/playing frame when the adapter is no longer live.
    if (backlight_configured)
      (void)gpio_set_level(static_cast<gpio_num_t>(config.backlight), 0);
    // IO deletion waits for queued transactions and their callback before the
    // context or DMA memory is reclaimed. Failed cleanup cannot free live DMA.
    if (panel && esp_lcd_panel_del(panel) != ESP_OK) std::terminate();
    if (io && esp_lcd_panel_io_del(io) != ESP_OK) std::terminate();
    if (pixels) heap_caps_free(pixels);
    if (bus_owned && spi_bus_free(static_cast<spi_host_device_t>(config.spi_host)) != ESP_OK)
      std::terminate();
  }

  void rasterize() noexcept {
    std::fill_n(pixels, width * stripe_rows, std::uint16_t{});
    for (int dy = 0; dy < stripe_rows && y + dy < height; ++dy) {
      const auto row = static_cast<std::size_t>((y + dy) / 8);
      const int bit = (y + dy) % 8;
      if (row >= ScreenView::rows || bit >= 7) continue;
      for (std::size_t cell = 0; cell < ScreenView::columns; ++cell) {
        const auto columns = glyph(snapshot.lines[row][cell]);
        for (std::size_t x = 0; x < columns.size(); ++x)
          if ((columns[x] & (1U << bit)) != 0)
            pixels[static_cast<std::size_t>(dy * width) + cell * 6 + x] = 0xffff;
      }
    }
  }
};

LcdDisplay::LcdDisplay(LcdConfiguration config) : impl_(std::make_unique<Impl>(config)) {}
LcdDisplay::~LcdDisplay() = default;

bool LcdDisplay::install() noexcept {
  auto& s = *impl_;
  if (s.installed) return true;
  if (s.failed) return false;
  s.failed = true; // Partial setup is cleaned by destruction; no double install.
  const auto& c = s.config;
  if (c.backlight < 0 || c.backlight >= 64 || c.frequency_hz <= 0) return false;
  gpio_config_t backlight{};
  backlight.pin_bit_mask = std::uint64_t{1} << c.backlight;
  backlight.mode = GPIO_MODE_OUTPUT;
  if (gpio_config(&backlight) != ESP_OK) return false;
  s.backlight_configured = true;
  if (gpio_set_level(static_cast<gpio_num_t>(c.backlight), 0) != ESP_OK) return false;
  spi_bus_config_t bus{};
  bus.mosi_io_num = c.mosi;
  bus.miso_io_num = -1;
  bus.sclk_io_num = c.clock;
  bus.quadwp_io_num = -1;
  bus.quadhd_io_num = -1;
  bus.max_transfer_sz = Impl::width * Impl::stripe_rows * 2;
  const auto spi = static_cast<spi_host_device_t>(c.spi_host);
  if (spi_bus_initialize(spi, &bus, SPI_DMA_CH_AUTO) != ESP_OK) return false;
  s.bus_owned = true;
  esp_lcd_panel_io_spi_config_t io{};
  io.cs_gpio_num = static_cast<gpio_num_t>(c.chip_select);
  io.dc_gpio_num = static_cast<gpio_num_t>(c.data_command);
  io.pclk_hz = c.frequency_hz;
  io.trans_queue_depth = 1;
  io.lcd_cmd_bits = 8;
  io.lcd_param_bits = 8;
  io.on_color_trans_done = Impl::completed;
  io.user_ctx = &s;
  if (esp_lcd_new_panel_io_spi(spi, &io, &s.io) != ESP_OK) return false;
  esp_lcd_panel_dev_config_t device{};
  device.reset_gpio_num = static_cast<gpio_num_t>(c.reset);
  device.bits_per_pixel = 16;
  device.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB;
  if (esp_lcd_new_panel_st7789(s.io, &device, &s.panel) != ESP_OK ||
      esp_lcd_panel_reset(s.panel) != ESP_OK || esp_lcd_panel_init(s.panel) != ESP_OK ||
      esp_lcd_panel_swap_xy(s.panel, c.swap_xy) != ESP_OK ||
      esp_lcd_panel_mirror(s.panel, c.mirror_x, c.mirror_y) != ESP_OK ||
      esp_lcd_panel_set_gap(s.panel, c.gap_x, c.gap_y) != ESP_OK ||
      esp_lcd_panel_invert_color(s.panel, c.invert) != ESP_OK ||
      esp_lcd_panel_disp_on_off(s.panel, true) != ESP_OK) return false;
  s.pixels = static_cast<std::uint16_t*>(heap_caps_malloc(
      Impl::width * Impl::stripe_rows * sizeof(std::uint16_t), MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL));
  if (!s.pixels) return false;
  s.installed = true;
  s.failed = false;
  return true;
}

bool LcdDisplay::poll(const ScreenView& view, std::uint64_t now_ms) noexcept {
  auto& s = *impl_;
  if (!s.installed || s.failed) return false;
  if (s.busy.load(std::memory_order_acquire)) return true;
  if (s.y == Impl::height) {
    // Turn the light on only after the first complete initialized frame.
    if (gpio_set_level(static_cast<gpio_num_t>(s.config.backlight), 1) != ESP_OK) {
      s.failed = true;
      return false;
    }
    s.y = 0;
    s.have_frame = true;
    s.next_frame_ms = now_ms + 50;
  }
  if (s.y == 0) {
    if (s.have_frame && (now_ms < s.next_frame_ms || view == s.snapshot)) return true;
    s.snapshot = view;
  }
  s.rasterize();
  s.busy.store(true, std::memory_order_release);
  if (esp_lcd_panel_draw_bitmap(s.panel, 0, s.y, Impl::width,
          std::min(s.y + Impl::stripe_rows, Impl::height), s.pixels) != ESP_OK) {
    s.failed = true;
    return false;
  }
  s.y += Impl::stripe_rows;
  return true;
}
}  // namespace lmdj::cardputer
#endif
