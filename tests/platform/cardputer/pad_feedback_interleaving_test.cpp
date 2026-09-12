#include "apps/cardputer-host/main/runtime_host.hpp"
#include "tests/core/support/test.hpp"

#include <algorithm>
#include <cstdio>
#include <deque>
#include <string>

// Deterministic Facade boundary double, linked instead of the implementation
// in this executable only. It models ordered receipts and publication of an
// older completed render between Host's poll and its next submit. Real Core
// receipt integration is covered by platform.cardputer.input.*; this double
// does not model audio execution, timing, PCM, or electrical side effects.
namespace lmdj::facade {
struct RuntimeFacade::Impl {
  RuntimePhase phase{RuntimePhase::empty};
  RuntimeEpoch epoch;
  std::deque<RuntimeReceipt> receipts;
  RuntimeContentIdentity identity;
  std::uint32_t published{};
};
RuntimeFacade::RuntimeFacade(RuntimeConfig) : impl_(std::make_unique<Impl>()) {}
RuntimeFacade::~RuntimeFacade() = default;
RuntimeResult RuntimeFacade::load(std::span<const std::byte>, const RuntimeContentIdentity& identity) noexcept {
  impl_->identity = identity;
  impl_->phase = RuntimePhase::ready;
  return RuntimeResult::ok;
}
RuntimeResult RuntimeFacade::start(RuntimeEpoch& epoch) noexcept {
  epoch.token_ = std::make_shared<const std::uint32_t>(1);
  impl_->epoch = epoch;
  impl_->phase = RuntimePhase::running;
  return RuntimeResult::ok;
}
RuntimeResult RuntimeFacade::submit(const RuntimeCommand& command) noexcept {
  impl_->receipts.push_back({impl_->epoch, command.sequence,
      command.kind == RuntimeCommandKind::press ? RuntimeCommandOutcome::voice_started :
      RuntimeCommandOutcome::applied});
  // Render completed press 1. Commands 2/3 were queued after its queue drain,
  // before the consumed-sequence publication; their receipts are not ready.
  if (command.sequence == 3) impl_->published = 1;
  return RuntimeResult::accepted;
}
std::size_t RuntimeFacade::poll(std::span<RuntimeReceipt> output) noexcept {
  std::size_t count = 0;
  while (count < output.size() && !impl_->receipts.empty() &&
         impl_->receipts.front().sequence <= impl_->published) {
    output[count++] = impl_->receipts.front();
    impl_->receipts.pop_front();
  }
  return count;
}
void RuntimeFacade::stop() noexcept {
  impl_->receipts.clear();
  impl_->phase = RuntimePhase::stopped;
}
RuntimeResult RuntimeFacade::unload() noexcept {
  impl_->phase = RuntimePhase::empty;
  return RuntimeResult::ok;
}
RuntimePhase RuntimeFacade::phase() const noexcept { return impl_->phase; }
std::optional<RuntimeContentIdentity> RuntimeFacade::content_identity() const { return impl_->identity; }
RuntimeContentSummary RuntimeFacade::content_summary() const noexcept {
  RuntimeContentSummary result;
  result.count = 1;
  result.pads[0] = {2, 7, RuntimeTriggerMode::one_shot};
  return result;
}
void RuntimeFacade::render(float*, float*, std::uint32_t) noexcept {
  impl_->published = 3;
}
}  // namespace lmdj::facade

namespace {
struct Audio final : lmdj::cardputer::AudioSession {
  Render callback{};
  void* owner{};
  bool start(Render render, void* context, std::uint8_t, bool) noexcept override {
    callback = render; owner = context; return true;
  }
  lmdj::cardputer::AudioStopResult stop_and_join() noexcept override { return {true, true}; }
  void set_output(std::uint8_t, bool) noexcept override {}
  bool healthy() const noexcept override { return true; }
};
}

int main() {
  using namespace lmdj::cardputer;
  try {
    Audio audio;
    lmdj::facade::RuntimeConfig config;
    config.maximum_pending_commands = 3;
    RuntimeHost host(config, {4}, audio);
    LMDJ_CHECK(host.begin_receive() == HostResult::ok);
    LMDJ_CHECK(host.load_received({}, {std::string(64, 'a'), 1}) == HostResult::ok);
    LMDJ_CHECK(host.handle_key({Key::play_stop, true}) == HostResult::ok);
    LMDJ_CHECK(host.handle_key({Key::pad_a, true}) == HostResult::accepted);
    LMDJ_CHECK(host.handle_key({Key::pad_a, false}) == HostResult::accepted);
    LMDJ_CHECK(host.handle_key({Key::pad_a, true}) == HostResult::accepted);
    host.poll();
    LMDJ_CHECK(host.read_status().last_receipt_sequence == 1);
    LMDJ_CHECK(host.read_status().pad_active[0]);
    audio.callback(audio.owner, nullptr, nullptr, 0);
    host.poll();
    LMDJ_CHECK(host.read_status().last_receipt_sequence == 3);
    LMDJ_CHECK(host.read_status().pad_active[0]);
  } catch (const std::exception& error) {
    return std::fprintf(stderr, "%s\n", error.what()), 1;
  }
  return 0;
}
