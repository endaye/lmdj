#include "apps/cardputer-host/main/runtime_host.hpp"
#include "lcd_fake.hpp"
#include "freertos/task.h"
#include "tests/core/support/test.hpp"
#include <algorithm>
#include <array>
#include <cstdio>
#include <string_view>

extern "C" void app_main();

namespace {
int starts{}, stops{}, destroyed{};
bool borrowed_bus_alive{}, silence_rendered{};
}

// Only the physical audio worker is substituted. The real app_main, RuntimeHost,
// scanner, USB endpoint and LCD adapter execute. This does not prove physical
// codec silence, scheduler timing, or joins of the real ESP audio worker.
namespace lmdj::cardputer {
struct EspAudioSession::Impl { i2c_master_bus_handle_t bus; };
EspAudioSession::EspAudioSession(EspAudioSessionConfig config)
    : impl_(std::make_unique<Impl>(Impl{config.io.shared_bus})) {}
EspAudioSession::~EspAudioSession() {
  borrowed_bus_alive = impl_->bus && fake_i2c::connected(impl_->bus);
  ++destroyed;
}
bool EspAudioSession::start(Render render, void* context, std::uint8_t, bool muted) noexcept {
  ++starts;
  std::array<float, 256> left, right;
  left.fill(1); right.fill(1);
  render(context, left.data(), right.data(), 256);
  silence_rendered = muted && std::all_of(left.begin(), left.end(), [](float v) { return v == 0; })
      && std::all_of(right.begin(), right.end(), [](float v) { return v == 0; });
  return true;
}
AudioStopResult EspAudioSession::stop_and_join() noexcept { ++stops; return {true, true}; }
void EspAudioSession::set_output(std::uint8_t, bool) noexcept {}
bool EspAudioSession::healthy() const noexcept { return true; }
bool EspAudioSession::read_diagnostics(AudioDiagnosticsSnapshot&) const noexcept { return false; }
std::optional<std::size_t> EspAudioSession::stopped_stack_high_water_bytes() const noexcept {
  return std::nullopt;
}
}

int main(int argc, char** argv) {
  using namespace std::literals;
  LMDJ_CHECK(argc == 2);
  const auto scenario = std::string_view(argv[1]);
  fake_lcd::reset();
  if (scenario == "install"sv) fake_lcd::fail = "gpio_config";
  else { LMDJ_CHECK(scenario == "draw"sv); fake_lcd::fail = "draw"; }
  fake_task::delay_hook = [] {
    std::fputs("why: app_main continued after injected LCD failure; remedy: exit and reclaim owners\n", stderr);
    std::abort();
  };
  app_main();
  LMDJ_CHECK(starts == 1 && silence_rendered);
  LMDJ_CHECK(stops >= 1 && destroyed == 1);
  LMDJ_CHECK(borrowed_bus_alive);
  LMDJ_CHECK(fake_i2c::created == 1 && fake_i2c::deleted == 1);
  LMDJ_CHECK(fake_lcd::buses == 0 && fake_lcd::ios == 0 && fake_lcd::panels == 0);
  LMDJ_CHECK(fake_lcd::allocations == 0 && fake_lcd::pending == nullptr);
  LMDJ_CHECK(fake_lcd::light == 0);
  LMDJ_CHECK(std::find(fake_lcd::calls.begin(), fake_lcd::calls.end(),
                       scenario == "draw"sv ? "draw" : "gpio_config") != fake_lcd::calls.end());
}
