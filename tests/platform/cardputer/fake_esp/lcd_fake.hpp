#pragma once
#include "driver/i2c_master.h"
#include <algorithm>
#include <cstdlib>
#include <string>
#include <vector>

using spi_host_device_t = int;
inline constexpr int GPIO_MODE_OUTPUT = 1, SPI_DMA_CH_AUTO = 3;
inline constexpr int LCD_RGB_ELEMENT_ORDER_RGB = 0, MALLOC_CAP_DMA = 1, MALLOC_CAP_INTERNAL = 2;
struct gpio_config_t { std::uint64_t pin_bit_mask{}; int mode{}; };
struct spi_bus_config_t { int mosi_io_num{}, miso_io_num{}, sclk_io_num{}, quadwp_io_num{}, quadhd_io_num{}, max_transfer_sz{}; };
struct FakeLcdIo;
struct FakeLcdPanel;
struct esp_lcd_panel_io_event_data_t {};
using esp_lcd_panel_io_handle_t = FakeLcdIo*;
using esp_lcd_panel_handle_t = FakeLcdPanel*;
struct esp_lcd_panel_io_spi_config_t {
  int cs_gpio_num{}, dc_gpio_num{}, pclk_hz{}, trans_queue_depth{}, lcd_cmd_bits{}, lcd_param_bits{};
  bool (*on_color_trans_done)(FakeLcdIo*, esp_lcd_panel_io_event_data_t*, void*){};
  void* user_ctx{};
};
struct esp_lcd_panel_dev_config_t { int reset_gpio_num{}, bits_per_pixel{}, rgb_ele_order{}; };
struct FakeLcdIo { esp_lcd_panel_io_spi_config_t config; };
struct FakeLcdPanel { FakeLcdIo* io; };
namespace fake_lcd {
inline std::string fail;
inline std::vector<std::string> calls;
inline int buses{}, ios{}, panels{}, allocations{}, light{}, submits{}, frees{}, completions{};
inline const std::uint16_t* pending{};
inline FakeLcdIo* pending_io{};
inline std::vector<std::uint16_t> retained;
inline std::array<std::uint16_t, 240 * 135> screen{};
inline int next_y{};
inline bool step(const char* name) { calls.emplace_back(name); return fail != name; }
inline void complete() {
  if (!pending) return;
  if (!std::equal(retained.begin(), retained.end(), pending)) std::abort();
  auto* io = pending_io;
  pending = nullptr;
  pending_io = nullptr;
  ++completions;
  io->config.on_color_trans_done(io, nullptr, io->config.user_ctx);
}
inline void reset() {
  if (pending || buses || ios || panels || allocations) std::abort();
  fail.clear(); calls.clear(); light = submits = frees = completions = next_y = 0;
  retained.clear(); screen.fill(0);
}
}
inline int gpio_config(const gpio_config_t*) { return fake_lcd::step("gpio_config") ? ESP_OK : -1; }
inline int gpio_set_level(gpio_num_t, int value) {
  if (!fake_lcd::step(value ? "light_on" : "light_off")) return -1;
  fake_lcd::light = value; return ESP_OK;
}
inline int spi_bus_initialize(spi_host_device_t, const spi_bus_config_t*, int) {
  if (!fake_lcd::step("bus_init")) return -1;
  ++fake_lcd::buses; return ESP_OK;
}
inline int spi_bus_free(spi_host_device_t) { --fake_lcd::buses; return ESP_OK; }
inline int esp_lcd_new_panel_io_spi(spi_host_device_t, const esp_lcd_panel_io_spi_config_t* config, FakeLcdIo** io) {
  if (!fake_lcd::step("io_new")) return -1;
  *io = new FakeLcdIo{*config}; ++fake_lcd::ios; return ESP_OK;
}
inline int esp_lcd_new_panel_st7789(FakeLcdIo* io, const esp_lcd_panel_dev_config_t*, FakeLcdPanel** panel) {
  if (!fake_lcd::step("panel_new")) return -1;
  *panel = new FakeLcdPanel{io}; ++fake_lcd::panels; return ESP_OK;
}
inline int esp_lcd_panel_reset(FakeLcdPanel*) { return fake_lcd::step("panel_reset") ? 0 : -1; }
inline int esp_lcd_panel_init(FakeLcdPanel*) { return fake_lcd::step("panel_init") ? 0 : -1; }
inline int esp_lcd_panel_swap_xy(FakeLcdPanel*, bool) { return fake_lcd::step("swap") ? 0 : -1; }
inline int esp_lcd_panel_mirror(FakeLcdPanel*, bool, bool) { return fake_lcd::step("mirror") ? 0 : -1; }
inline int esp_lcd_panel_set_gap(FakeLcdPanel*, int, int) { return fake_lcd::step("gap") ? 0 : -1; }
inline int esp_lcd_panel_invert_color(FakeLcdPanel*, bool) { return fake_lcd::step("invert") ? 0 : -1; }
inline int esp_lcd_panel_disp_on_off(FakeLcdPanel*, bool) { return fake_lcd::step("display_on") ? 0 : -1; }
inline int esp_lcd_panel_draw_bitmap(FakeLcdPanel* panel, int x, int y, int end_x, int end_y, const void* buffer) {
  if (!fake_lcd::step("draw")) return -1;
  if (fake_lcd::pending || x != 0 || end_x != 240 || y != fake_lcd::next_y || end_y > 135) std::abort();
  fake_lcd::next_y = end_y == 135 ? 0 : end_y;
  fake_lcd::pending = static_cast<const std::uint16_t*>(buffer);
  fake_lcd::pending_io = panel->io;
  fake_lcd::retained.assign(fake_lcd::pending, fake_lcd::pending + (end_y - y) * 240);
  std::copy(fake_lcd::retained.begin(), fake_lcd::retained.end(), fake_lcd::screen.begin() + y * 240);
  ++fake_lcd::submits; return ESP_OK;
}
inline int esp_lcd_panel_del(FakeLcdPanel* panel) { delete panel; --fake_lcd::panels; return ESP_OK; }
inline int esp_lcd_panel_io_del(FakeLcdIo* io) {
  fake_lcd::complete(); delete io; --fake_lcd::ios; return ESP_OK;
}
inline void* heap_caps_malloc(std::size_t size, int) {
  if (!fake_lcd::step("allocate")) return nullptr;
  ++fake_lcd::allocations; return std::malloc(size);
}
inline void heap_caps_free(void* memory) {
  if (fake_lcd::pending) std::abort();
  --fake_lcd::allocations; ++fake_lcd::frees; std::free(memory);
}
