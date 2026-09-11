#include "apps/cardputer-host/main/display.hpp"
#include "apps/cardputer-host/main/input_controller.hpp"
#include "apps/cardputer-host/main/keyboard.hpp"
#include "tests/core/support/test.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include <lmdj/cooker/runtime_content.hpp>

namespace {
using namespace lmdj::cardputer;
using namespace lmdj;

struct FakeSession final : AudioSession {
  Render callback{};
  void* context{};
  bool start(Render render, void* owner, std::uint8_t, bool) noexcept override {
    callback = render;
    context = owner;
    return true;
  }
  AudioStopResult stop_and_join() noexcept override {
    callback = nullptr;
    context = nullptr;
    return {true, true};
  }
  void set_output(std::uint8_t, bool) noexcept override {}
  bool healthy() const noexcept override { return true; }
  void pump() {
    std::array<float, 256> left{}, right{};
    if (callback) callback(context, left.data(), right.data(), 256);
  }
};

lmdj::facade::RuntimeConfig config(std::uint32_t pending = 128) {
  return {{1'048'576, 262'144, 65'536, 64, 1024}, 16'777'216, 65'536,
          pending, 100, 10'000};
}

lmdj::cooker::EncodedRuntimeContent content() {
  using namespace lmdj;
  auto pcm = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
      48'000, 1, std::vector<std::int16_t>(4096, 16384)});
  cooker::RuntimeSnapshot snapshot{
      foundation::ProjectId{"00000000-0000-4000-8000-000000000001"},
      foundation::PatternId{"00000000-0000-4000-8000-000000000002"}, 1, 120,
      1, 960, 3840,
      {{{2, 7}, {}, pcm, {0, 4096, domain::TriggerMode::one_shot, 1.0F, false}}},
      {}};
  auto encoded = cooker::encode_runtime_content(snapshot, config().content_limits);
  LMDJ_CHECK(encoded.has_value());
  return std::move(encoded.value());
}

RuntimeHost make_host(FakeSession& audio, std::uint32_t pending = 128) {
  return RuntimeHost(config(pending), {4}, audio);
}

void load_and_start(RuntimeHost& host) {
  const auto encoded = content();
  LMDJ_CHECK(host.begin_receive() == HostResult::ok);
  LMDJ_CHECK(host.load_received(encoded.bytes, encoded.identity) == HostResult::ok);
  LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
}

void mapping_is_exact_and_unknown_is_rejected() {
  LMDJ_CHECK(map_physical_key(PhysicalKey::a) == Key::pad_a);
  LMDJ_CHECK(map_physical_key(PhysicalKey::s) == Key::pad_s);
  LMDJ_CHECK(map_physical_key(PhysicalKey::d) == Key::pad_d);
  LMDJ_CHECK(map_physical_key(PhysicalKey::f) == Key::pad_f);
  LMDJ_CHECK(map_physical_key(PhysicalKey::space) == Key::play_stop);
  LMDJ_CHECK(map_physical_key(PhysicalKey::m) == Key::mute);
  LMDJ_CHECK(map_physical_key(PhysicalKey::minus) == Key::volume_down);
  LMDJ_CHECK(map_physical_key(PhysicalKey::equal) == Key::volume_up);
  LMDJ_CHECK(map_physical_key(PhysicalKey::enter) == Key::confirm_receive);
  LMDJ_CHECK(map_physical_key(PhysicalKey::escape) == Key::cancel_receive);
  LMDJ_CHECK(!map_physical_key(PhysicalKey::unknown));
}

void repeat_and_out_of_order_release_do_not_duplicate() {
  FakeSession audio;
  auto host = make_host(audio);
  load_and_start(host);
  Display display;
  InputController input(host, display);
  LMDJ_CHECK(input.enqueue({PhysicalKey::a, true, false}));
  LMDJ_CHECK(input.enqueue({PhysicalKey::a, true, true}));
  LMDJ_CHECK(input.enqueue({PhysicalKey::a, false, false}));
  LMDJ_CHECK(input.enqueue({PhysicalKey::a, false, false}));
  input.poll();
  audio.pump();
  input.poll();
  LMDJ_CHECK(input.pending() == 0);
  LMDJ_CHECK(!input.held(PhysicalKey::a));
  LMDJ_CHECK(!display.frame().pad_active[0]);
  LMDJ_CHECK(host.read_status().last_receipt_sequence == 2);
}

void empty_rejects_pad_and_receive_confirm_cancel_are_stateful() {
  FakeSession audio;
  auto host = make_host(audio);
  Display display;
  InputController input(host, display);
  LMDJ_CHECK(input.enqueue({PhysicalKey::a, true, false}));
  input.poll();
  LMDJ_CHECK(display.frame().status.error == HostResult::wrong_state);
  LMDJ_CHECK(!display.frame().pad_active[0]);
  LMDJ_CHECK(input.enqueue({PhysicalKey::enter, true, false}));
  input.poll();
  LMDJ_CHECK(display.frame().status.armed);
  LMDJ_CHECK(input.enqueue({PhysicalKey::escape, true, false}));
  input.poll();
  LMDJ_CHECK(!display.frame().status.armed);
  LMDJ_CHECK(display.frame().status.phase == facade::RuntimePhase::empty);
}

void overflow_stops_and_clears_local_state() {
  FakeSession audio;
  auto host = make_host(audio);
  load_and_start(host);
  Display display;
  InputController input(host, display);
  const std::array keys{PhysicalKey::a, PhysicalKey::s, PhysicalKey::d,
                        PhysicalKey::f, PhysicalKey::space, PhysicalKey::m,
                        PhysicalKey::minus, PhysicalKey::equal};
  for (const auto key : keys) {
    LMDJ_CHECK(input.enqueue({key, true, false}));
    LMDJ_CHECK(input.enqueue({key, false, false}));
  }
  LMDJ_CHECK(!input.enqueue({PhysicalKey::a, true, false}));
  input.poll();
  LMDJ_CHECK(input.pending() == 0);
  LMDJ_CHECK(!input.held(PhysicalKey::a));
  LMDJ_CHECK(display.frame().status.error == HostResult::input_overflow);
  LMDJ_CHECK(display.frame().status.phase != facade::RuntimePhase::running);
}

void runtime_queue_full_retries_original_event() {
  FakeSession audio;
  auto host = make_host(audio, 1);
  load_and_start(host);
  Display display;
  InputController input(host, display);
  LMDJ_CHECK(input.enqueue({PhysicalKey::a, true, false}));
  LMDJ_CHECK(input.enqueue({PhysicalKey::a, false, false}));
  input.poll();
  LMDJ_CHECK(input.pending() == 1);
  audio.pump();
  input.poll();
  LMDJ_CHECK(input.pending() == 0);
  LMDJ_CHECK(!input.held(PhysicalKey::a));
}

void display_is_bounded_and_uses_actual_status() {
  FakeSession audio;
  auto host = make_host(audio);
  Display display;
  InputController input(host, display);
  input.poll();
  LMDJ_CHECK(std::string_view(display.frame().phase_label.data()) == "empty");
  LMDJ_CHECK(std::string_view(display.frame().error_label.data()) == "ok");
  LMDJ_CHECK(display.frame().status.phase == facade::RuntimePhase::empty);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const std::string scenario = argv[1];
  try {
    if (scenario == "mapping") mapping_is_exact_and_unknown_is_rejected();
    else if (scenario == "repeat_release") repeat_and_out_of_order_release_do_not_duplicate();
    else if (scenario == "empty_receive") empty_rejects_pad_and_receive_confirm_cancel_are_stateful();
    else if (scenario == "overflow") overflow_stops_and_clears_local_state();
    else if (scenario == "queue_retry") runtime_queue_full_retries_original_event();
    else if (scenario == "display") display_is_bounded_and_uses_actual_status();
    else return 2;
  } catch (const std::exception& error) {
    return std::fprintf(stderr, "%s\n", error.what()), 1;
  }
  return 0;
}
