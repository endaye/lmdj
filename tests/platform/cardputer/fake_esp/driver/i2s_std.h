#pragma once
#include "i2c_master.h"
using i2s_chan_handle_t = int*;
struct i2s_event_data_t { void* dma_buf; std::size_t size; };
using FakeCallback = bool (*)(i2s_chan_handle_t, i2s_event_data_t*, void*);
struct i2s_event_callbacks_t { FakeCallback on_sent{}, on_send_q_ovf{}; };
struct i2s_chan_config_t { unsigned dma_desc_num{}, dma_frame_num{}; bool auto_clear_after_cb{}; };
struct i2s_std_config_t {
  int clk_cfg{}, slot_cfg{};
  struct { int mclk{}, bclk{}, ws{}, dout{}, din{}; } gpio_cfg;
};
struct i2s_chan_info_t { unsigned total_dma_buf_size{}; };
inline constexpr int I2S_GPIO_UNUSED = -1;
#define I2S_CHANNEL_DEFAULT_CONFIG(...) i2s_chan_config_t{}
#define I2S_STD_CLK_DEFAULT_CONFIG(...) 0
#define I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(...) 0
inline int i2s_new_channel(const i2s_chan_config_t* c, int** out, void*) {
  *out = new int(static_cast<int>(c->dma_desc_num * c->dma_frame_num * 4)); return ESP_OK;
}
inline int i2s_channel_init_std_mode(int*, const i2s_std_config_t*) { return ESP_OK; }
inline int i2s_channel_get_info(int* c, i2s_chan_info_t* info) {
  info->total_dma_buf_size = static_cast<unsigned>(*c); return ESP_OK;
}
inline int i2s_channel_register_event_callback(int*, const i2s_event_callbacks_t*, void*) { return ESP_OK; }
inline int i2s_channel_enable(int*) { return ESP_OK; }
inline int i2s_channel_disable(int*) { return ESP_OK; }
inline int i2s_del_channel(int* c) { delete c; return ESP_OK; }
inline int i2s_channel_write(int*, const void*, std::size_t, std::size_t*, int) { return -1; }
