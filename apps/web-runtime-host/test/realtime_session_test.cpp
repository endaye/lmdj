#include "control_runtime.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <memory>
#include <mutex>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/provider/registry.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::RuntimePreparationLimits;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;
using lmdj::web_host::ControlRuntime;
using lmdj::web_host::detail::BridgeHooks;
using lmdj::web_host::detail::BridgePollStatus;
using lmdj::web_host::detail::BridgeSubmitStatus;
using lmdj::web_host::detail::ControlBridge;

class TempDirectory final {
 public:
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-web-realtime-session-" +
             std::to_string(reinterpret_cast<std::uintptr_t>(this)));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  const std::filesystem::path& path() const noexcept { return path_; }

 private:
  std::filesystem::path path_;
};

std::unique_ptr<ControlRuntime> make_runtime(
    const std::filesystem::path& root) {
  auto created = ControlRuntime::create(
      root,
      Application(ApplicationConfig{
          root,
          std::make_shared<Registry>(),
          ProviderPolicy{},
          [] { return std::string("2026-08-04T00:00:00.000Z"); },
      }),
      RuntimePreparationLimits{
          1'048'576,
          240'000,
          67'108'864,
          134'217'728,
      });
  LMDJ_CHECK(created.has_value());
  return std::move(created.value());
}

class FakeProxy final {
 public:
  static bool schedule(
      void* context,
      void (*function)(void*) noexcept,
      void* argument) noexcept {
    auto& self = *static_cast<FakeProxy*>(context);
    std::lock_guard lock(self.mutex_);
    self.tasks_.push_back({function, argument});
    return true;
  }

  static bool on_control(void* context) noexcept {
    return static_cast<FakeProxy*>(context)->on_control_;
  }

  static void before_response(void*) {}

  static void after_capture_drain(void*) {}

  static void after_outcome_drain(void* context) {
    auto& self = *static_cast<FakeProxy*>(context);
    if (self.request_service_at_tail_ && self.bridge_ != nullptr) {
      self.request_service_at_tail_ = false;
      std::array<std::byte, 1> output{};
      std::size_t required = 0;
      LMDJ_CHECK(
          self.bridge_->poll(output, required) == BridgePollStatus::empty);
    }
    if (!self.inject_outcome_drop_ || self.engine_ == nullptr) {
      return;
    }
    self.inject_outcome_drop_ = false;
    std::array<float, 1> left{};
    std::array<float, 1> right{};
    self.engine_->render(left.data(), right.data(), 1);
  }

  BridgeHooks hooks() noexcept {
    return BridgeHooks{
        this,
        &schedule,
        &on_control,
        &before_response,
        &after_capture_drain,
        &after_outcome_drain,
    };
  }

  void inject_outcome_drop(lmdj::audio::RealtimeEngine& engine) {
    engine_ = &engine;
    inject_outcome_drop_ = true;
  }

  void request_service_at_tail(ControlBridge& bridge) {
    bridge_ = &bridge;
    request_service_at_tail_ = true;
  }

  bool empty() const {
    std::lock_guard lock(mutex_);
    return tasks_.empty();
  }

  void pump_one() {
    Task task{};
    {
      std::lock_guard lock(mutex_);
      LMDJ_CHECK(!tasks_.empty());
      task = tasks_.front();
      tasks_.erase(tasks_.begin());
    }
    on_control_ = true;
    task.function(task.argument);
    on_control_ = false;
  }

  void pump_all() {
    while (!empty()) {
      pump_one();
    }
  }

 private:
  struct Task {
    void (*function)(void*) noexcept = nullptr;
    void* argument = nullptr;
  };

  mutable std::mutex mutex_;
  std::vector<Task> tasks_;
  bool on_control_ = false;
  lmdj::audio::RealtimeEngine* engine_ = nullptr;
  bool inject_outcome_drop_ = false;
  ControlBridge* bridge_ = nullptr;
  bool request_service_at_tail_ = false;
};

nlohmann::json poll_message(ControlBridge& bridge) {
  std::array<std::byte, lmdj::web_host::detail::kBridgeMaximumEnvelopeBytes>
      output{};
  std::size_t required = 0;
  const auto status = bridge.poll(output, required);
  if (status != BridgePollStatus::message) {
    throw std::runtime_error(
        "expected bridge message, got status " +
        std::to_string(static_cast<int>(status)) +
        ", failed=" + std::to_string(bridge.failed()));
  }
  return nlohmann::json::parse(std::string_view(
      reinterpret_cast<const char*>(output.data()), required));
}

void enable_realtime_service(ControlBridge& bridge, FakeProxy& proxy) {
  const auto envelope = nlohmann::json{
      {"protocol_version", 1},
      {"request_id", "00000000-0000-4000-8000-000000000901"},
      {"operation", "host.status"},
      {"payload", nlohmann::json::object()},
  }.dump();
  const auto bytes = std::span<const std::byte>(
      reinterpret_cast<const std::byte*>(envelope.data()), envelope.size());
  LMDJ_CHECK(
      bridge.submit(bytes, {}) == BridgeSubmitStatus::accepted);
  proxy.pump_one();
  LMDJ_CHECK(poll_message(bridge).at("ok") == true);
  proxy.pump_one();
}

void test_outcome_control_drains_are_bounded_to_64() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  auto& engine = runtime->engine();
  const std::array<float, 256> sample{};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (std::uint64_t sequence = 1; sequence <= 65; ++sequence) {
    LMDJ_CHECK(
        engine.enqueue(lmdj::audio::TriggerEvent{sequence, 0, 127}) ==
        lmdj::audio::EnqueueResult::accepted);
  }
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  engine.render(left.data(), right.data(), 128);

  const auto first = runtime->drain_outcomes();
  const auto second = runtime->drain_outcomes();
  LMDJ_CHECK(first.size() == 64);
  LMDJ_CHECK(second.size() == 1);
  LMDJ_CHECK(first.front().sequence == 1);
  LMDJ_CHECK(first.back().sequence == 64);
  LMDJ_CHECK(second.front().sequence == 65);
}

void test_bridge_emits_only_non_empty_ordered_outcome_batches() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  auto& engine = runtime->engine();
  const std::array<float, 256> sample{};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  FakeProxy proxy;
  ControlBridge bridge(*runtime, proxy.hooks());

  std::array<std::byte, 1> empty_output{};
  std::size_t required = 99;
  LMDJ_CHECK(
      bridge.poll(empty_output, required) == BridgePollStatus::empty);
  LMDJ_CHECK(proxy.empty());

  for (std::uint64_t sequence = 1; sequence <= 65; ++sequence) {
    LMDJ_CHECK(
        engine.enqueue(lmdj::audio::TriggerEvent{sequence, 0, 127}) ==
        lmdj::audio::EnqueueResult::accepted);
  }
  std::array<float, 128> left{};
  std::array<float, 128> right{};
  engine.render(left.data(), right.data(), 128);
  enable_realtime_service(bridge, proxy);

  required = 99;
  LMDJ_CHECK(
      bridge.poll(empty_output, required) == BridgePollStatus::empty);
  LMDJ_CHECK(!proxy.empty());
  proxy.pump_one();
  const auto first = poll_message(bridge);
  LMDJ_CHECK(first.at("event") == "runtime.trigger_outcomes");
  const auto& first_events = first.at("payload").at("events");
  LMDJ_CHECK(first_events.size() == 64);
  LMDJ_CHECK(first_events.front().at("sequence") == 1);
  LMDJ_CHECK(first_events.back().at("sequence") == 64);

  required = 99;
  LMDJ_CHECK(
      bridge.poll(empty_output, required) == BridgePollStatus::empty);
  LMDJ_CHECK(!proxy.empty());
  proxy.pump_one();
  const auto second = poll_message(bridge);
  LMDJ_CHECK(second.at("event") == "runtime.trigger_outcomes");
  LMDJ_CHECK(second.at("payload").at("events").size() == 1);
  LMDJ_CHECK(
      second.at("payload").at("events").front().at("sequence") == 65);

  required = 99;
  LMDJ_CHECK(
      bridge.poll(empty_output, required) == BridgePollStatus::empty);
  LMDJ_CHECK(!proxy.empty());
  proxy.pump_one();
  required = 99;
  LMDJ_CHECK(
      bridge.poll(empty_output, required) == BridgePollStatus::empty);
}

void test_outcome_drop_is_a_terminal_bridge_signal() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  auto& engine = runtime->engine();
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  for (std::uint64_t sequence = 1;
       sequence <= lmdj::audio::kRealtimeTriggerOutcomeCapacity + 1;
       ++sequence) {
    LMDJ_CHECK(
        engine.enqueue(lmdj::audio::TriggerEvent{sequence, 0, 127}) ==
        lmdj::audio::EnqueueResult::accepted);
    std::array<float, 1> left{};
    std::array<float, 1> right{};
    engine.render(left.data(), right.data(), 1);
  }
  LMDJ_CHECK(
      engine.trigger_outcome_telemetry().runtime_outcome_drops == 1);

  FakeProxy proxy;
  ControlBridge bridge(*runtime, proxy.hooks());
  enable_realtime_service(bridge, proxy);
  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(bridge.poll(output, required) == BridgePollStatus::empty);
  proxy.pump_one();
  LMDJ_CHECK(bridge.failed());
  LMDJ_CHECK(bridge.poll(output, required) == BridgePollStatus::failed);
  const auto status = runtime->dispatch(
      "host.status", nlohmann::json::object(), {});
  LMDJ_CHECK(status.at("ok") == false);
  LMDJ_CHECK(status.at("error").at("code") == "HOST_STATE_INVALID");
}

void test_outcome_drop_racing_the_post_drain_check_is_terminal() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  auto& engine = runtime->engine();
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  FakeProxy proxy;
  ControlBridge bridge(*runtime, proxy.hooks());
  enable_realtime_service(bridge, proxy);
  proxy.pump_one();

  std::array<float, 1> left{};
  std::array<float, 1> right{};
  for (std::uint64_t sequence = 1;
       sequence <= lmdj::audio::kRealtimeTriggerOutcomeCapacity;
       ++sequence) {
    LMDJ_CHECK(
        engine.enqueue(lmdj::audio::TriggerEvent{sequence, 0, 127}) ==
        lmdj::audio::EnqueueResult::accepted);
    engine.render(left.data(), right.data(), 1);
  }
  for (std::uint64_t sequence = 4'097; sequence <= 4'161; ++sequence) {
    LMDJ_CHECK(
        engine.enqueue(lmdj::audio::TriggerEvent{sequence, 0, 127}) ==
        lmdj::audio::EnqueueResult::accepted);
  }
  proxy.inject_outcome_drop(engine);

  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(bridge.poll(output, required) == BridgePollStatus::empty);
  proxy.pump_one();
  LMDJ_CHECK(
      engine.trigger_outcome_telemetry().runtime_outcome_drops == 1);
  LMDJ_CHECK(bridge.failed());
  LMDJ_CHECK(bridge.poll(output, required) == BridgePollStatus::failed);
}

void test_ready_response_pressure_cannot_starve_realtime_service() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  auto& engine = runtime->engine();
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  FakeProxy proxy;
  ControlBridge bridge(*runtime, proxy.hooks());
  enable_realtime_service(bridge, proxy);
  proxy.pump_one();

  std::array<float, 1> left{};
  std::array<float, 1> right{};
  for (std::uint64_t sequence = 1; sequence <= 65; ++sequence) {
    LMDJ_CHECK(
        engine.enqueue(lmdj::audio::TriggerEvent{sequence, 0, 127}) ==
        lmdj::audio::EnqueueResult::accepted);
    engine.render(left.data(), right.data(), 1);
  }

  std::array<std::string, 8> request_ids{};
  for (std::uint32_t index = 1; index <= request_ids.size(); ++index) {
    const auto suffix = std::to_string(910 + index);
    const auto request_id =
        "00000000-0000-4000-8000-" +
        std::string(12 - suffix.size(), '0') + suffix;
    request_ids[index - 1] = request_id;
    const auto envelope = nlohmann::json{
        {"protocol_version", 1},
        {"request_id", request_id},
        {"operation", "host.status"},
        {"payload", nlohmann::json::object()},
    }.dump();
    const auto bytes = std::span<const std::byte>(
        reinterpret_cast<const std::byte*>(envelope.data()), envelope.size());
    LMDJ_CHECK(
        bridge.submit(bytes, {}) == BridgeSubmitStatus::accepted);
    proxy.pump_one();
  }
  for (const auto& request_id : request_ids) {
    LMDJ_CHECK(poll_message(bridge).at("request_id") == request_id);
  }
  proxy.pump_all();
  LMDJ_CHECK(
      engine.trigger_outcome_telemetry().drained_outcomes > 0);
}

void test_realtime_service_tail_request_is_not_lost() {
  TempDirectory temp;
  auto runtime = make_runtime(temp.path());
  auto& engine = runtime->engine();
  const std::array<float, 1> sample{0.1F};
  LMDJ_CHECK(engine.load_sample(0, sample).has_value());
  LMDJ_CHECK(engine.start().has_value());
  FakeProxy proxy;
  ControlBridge bridge(*runtime, proxy.hooks());
  enable_realtime_service(bridge, proxy);
  proxy.request_service_at_tail(bridge);

  std::array<std::byte, 1> output{};
  std::size_t required = 0;
  LMDJ_CHECK(bridge.poll(output, required) == BridgePollStatus::empty);
  proxy.pump_one();
  LMDJ_CHECK(!proxy.empty());
  proxy.pump_all();
  LMDJ_CHECK(!bridge.failed());
}

}  // namespace

int main() {
  try {
    test_outcome_control_drains_are_bounded_to_64();
    test_bridge_emits_only_non_empty_ordered_outcome_batches();
    test_outcome_drop_is_a_terminal_bridge_signal();
    test_outcome_drop_racing_the_post_drain_check_is_terminal();
    test_realtime_service_tail_request_is_not_lost();
    test_ready_response_pressure_cannot_starve_realtime_service();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "web realtime session tests: PASS\n";
  return 0;
}
