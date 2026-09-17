#include "apps/cardputer-host/main/keyboard_scanner.hpp"
#include "tests/core/support/test.hpp"
#include <lmdj/cooker/runtime_content.hpp>

#include <algorithm>
#include <array>
#include <cstdio>
#include <deque>
#include <memory>
#include <string_view>
#include <vector>

namespace {
using namespace lmdj;
using namespace lmdj::cardputer;
std::deque<std::uint8_t> fifo;

int read_register(FakeDevice* device, std::uint8_t address, std::uint8_t* value) {
  if (address == 0x03) *value = static_cast<std::uint8_t>(fifo.size());
  else if (address == 0x04) {
    *value = fifo.empty() ? 0 : fifo.front();
    if (!fifo.empty()) fifo.pop_front();
  } else *value = device->registers[address];
  return ESP_OK;
}

struct Audio final : AudioSession {
  Render callback{};
  void* context{};
  bool start(Render render, void* owner, std::uint8_t, bool) noexcept override {
    callback = render; context = owner; return true;
  }
  AudioStopResult stop_and_join() noexcept override {
    callback = nullptr; context = nullptr; return {true, true};
  }
  void set_output(std::uint8_t, bool) noexcept override {}
  bool healthy() const noexcept override { return true; }
  bool pump() {
    std::array<float, 256> left{}, right{};
    if (callback) callback(context, left.data(), right.data(), 256);
    return std::any_of(left.begin(), left.end(), [](float value) { return value != 0; });
  }
};

facade::RuntimeConfig config() {
  return {{1'048'576, 262'144, 65'536, 64, 1024}, 16'777'216, 65'536,
          128, 100, 10'000};
}

void load_and_start(RuntimeHost& host) {
  auto pcm = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
      48'000, 1, std::vector<std::int16_t>(4096, 16384)});
  cooker::RuntimeSnapshot snapshot{
      foundation::ProjectId{"00000000-0000-4000-8000-000000000001"},
      foundation::PatternId{"00000000-0000-4000-8000-000000000002"},
      1, 120, 1, 960, 3840, {}, {}};
  for (std::uint8_t pad = 0; pad != 4; ++pad) {
    snapshot.pads.push_back({{2, pad}, {}, pcm,
        {0, 4096, domain::TriggerMode::one_shot, 1.0F, false}});
  }
  auto encoded = cooker::encode_runtime_content(snapshot, config().content_limits);
  LMDJ_CHECK(encoded.has_value());
  LMDJ_CHECK(host.begin_receive() == HostResult::ok);
  LMDJ_CHECK(host.load_received(encoded.value().bytes, encoded.value().identity) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
}

void inject(Tca8418Scanner& scanner, InputController& input, std::uint8_t byte) {
  fifo.push_back(byte);
  scanner.poll(input);
  LMDJ_CHECK(fifo.empty());
}

void pad_edges(std::size_t pad) {
  // Independent controller bytes for ADV A/S/D/F. TI SCPS215G section
  // 8.6.2.4: bit 7 is PRESS, not RELEASE. No PhysicalKeyEvent injection.
  constexpr std::array<std::uint8_t, 4> presses{0x8d, 0x91, 0x97, 0x9b};
  constexpr std::array<std::uint8_t, 4> releases{0x0d, 0x11, 0x17, 0x1b};
  constexpr std::array keys{PhysicalKey::a, PhysicalKey::s, PhysicalKey::d, PhysicalKey::f};
  Audio audio;
  RuntimeHost host(config(), {4}, audio);
  load_and_start(host);
  Display display;
  InputController input(host, display);
  Tca8418Scanner scanner(8, 9);
  LMDJ_CHECK(scanner.install());
  LMDJ_CHECK(!audio.pump());

  inject(scanner, input, presses[pad]);
  LMDJ_CHECK(input.held(keys[pad]));
  input.poll();
  LMDJ_CHECK(audio.pump());
  input.poll();
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 1);
  LMDJ_CHECK(host.read_status().last_receipt_outcome == facade::RuntimeCommandOutcome::voice_started);
  inject(scanner, input, presses[pad]);
  LMDJ_CHECK(input.pending() == 0); // held repeat is not another press

  inject(scanner, input, releases[pad]);
  LMDJ_CHECK(!input.held(keys[pad]));
  input.poll();
  (void)audio.pump();
  input.poll();
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 2);
  inject(scanner, input, presses[pad]);
  input.poll();
  (void)audio.pump();
  input.poll();
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 3);
}

void command_edges() {
  Audio audio;
  RuntimeHost host(config(), {4}, audio);
  Display display;
  InputController input(host, display);
  Tca8418Scanner scanner(8, 9);
  LMDJ_CHECK(scanner.install());
  inject(scanner, input, 0xb0); // M press
  input.poll();
  LMDJ_CHECK(host.read_status().muted);
  inject(scanner, input, 0x30); // M release must not toggle
  input.poll();
  LMDJ_CHECK(host.read_status().muted);
  inject(scanner, input, 0xb0);
  input.poll();
  LMDJ_CHECK(!host.read_status().muted);
}
}

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  fake_i2c::read_register = read_register;
  try {
    const std::string_view scenario = argv[1];
    if (scenario == "a") pad_edges(0);
    else if (scenario == "s") pad_edges(1);
    else if (scenario == "d") pad_edges(2);
    else if (scenario == "f") pad_edges(3);
    else if (scenario == "command") command_edges();
    else return 2;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "why: hardware key-event polarity did not reach the expected Host/Core state: %s; remedy: decode KEA[7]=1 as press and preserve release/repeat semantics\n", error.what());
    return 1;
  }
}
