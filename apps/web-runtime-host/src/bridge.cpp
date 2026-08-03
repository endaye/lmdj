#include "control_runtime.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <span>
#include <string>
#include <string_view>
#include <utility>

#include <lmdj/foundation/json.hpp>

#if defined(__EMSCRIPTEN__)
#include <pthread.h>

#include <emscripten/emscripten.h>
#include <emscripten/proxying.h>

#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>
#endif

namespace lmdj::web_host::detail {
namespace {

using Json = nlohmann::json;

constexpr std::size_t kBridgeRequestSlotCount = 16;

enum class RequestState : std::uint8_t {
  free,
  writing,
  queued,
  processing,
  awaiting_response,
  response_consumed,
};

enum class MessageState : std::uint8_t { free, reserved, ready };

bool exact_keys(
    const Json& value,
    std::initializer_list<std::string_view> keys) {
  if (!value.is_object() || value.size() != keys.size()) {
    return false;
  }
  return std::all_of(keys.begin(), keys.end(), [&value](const auto key) {
    return value.contains(std::string(key));
  });
}

bool valid_request_id(const Json& value) {
  if (!value.is_string()) {
    return false;
  }
  const auto& id = value.get_ref<const std::string&>();
  if (id.size() != 36) {
    return false;
  }
  for (std::size_t index = 0; index < id.size(); ++index) {
    if (index == 8 || index == 13 || index == 18 || index == 23) {
      if (id[index] != '-') {
        return false;
      }
      continue;
    }
    const auto character = id[index];
    if (!((character >= '0' && character <= '9') ||
          (character >= 'a' && character <= 'f'))) {
      return false;
    }
  }
  return true;
}

Json bridge_protocol_error() {
  return {
      {"ok", false},
      {"error",
       {
           {"code", "HOST_PROTOCOL_MISMATCH"},
           {"message", "host protocol request is invalid"},
           {"details", Json::object()},
       }},
  };
}

bool supported_operation(std::string_view operation) {
  static constexpr std::array<std::string_view, 15> operations{
      "host.status",
      "project.create",
      "project.open",
      "project.inspect",
      "asset.import",
      "pad.assign",
      "snapshot.reload",
      "audio.activate",
      "audio.suspend",
      "trigger",
      "take.begin",
      "take.stop",
      "take.commit",
      "take.recoverable.list",
      "host.close",
  };
  return std::find(operations.begin(), operations.end(), operation) !=
         operations.end();
}

}  // namespace

struct ControlBridge::Impl {
  struct RequestSlot;

  struct MessageSlot {
    std::atomic<MessageState> state{MessageState::free};
    std::array<std::byte, kBridgeMaximumEnvelopeBytes> bytes{};
    std::size_t size = 0;
    std::uint64_t sequence = 0;
    RequestSlot* origin = nullptr;
    bool releases_request = false;
  };

  struct RequestSlot {
    Impl* owner = nullptr;
    std::atomic<RequestState> state{RequestState::free};
    std::array<std::byte, kBridgeMaximumEnvelopeBytes> envelope{};
    std::array<std::byte, kBridgeMaximumSidecarBytes> sidecar{};
    std::size_t envelope_size = 0;
    std::size_t sidecar_size = 0;
    std::string request_id;
    bool has_request_id = false;
  };

  struct ProcessReservations {
    MessageSlot* response = nullptr;
    MessageSlot* notification = nullptr;
  };

  Impl(ControlRuntime& owned_runtime, BridgeHooks owned_hooks)
      : runtime(owned_runtime), hooks(owned_hooks) {
    for (auto& request : requests) {
      request.owner = this;
    }
  }

  static void process_thunk(void* argument) noexcept {
    auto& request = *static_cast<RequestSlot*>(argument);
    request.owner->process(request);
  }

  static void fail_thunk(void* argument) noexcept {
    static_cast<Impl*>(argument)->fail_control();
  }

  static void release_thunk(void* argument) noexcept {
    auto& request = *static_cast<RequestSlot*>(argument);
    request.owner->release_consumed_request(request);
  }

  bool publish_internal_fallback_noexcept(
      RequestSlot& request, MessageSlot& message) noexcept {
    static constexpr std::string_view prefix =
        R"({"error":{"code":"INTERNAL_ERROR","details":{},"message":"unexpected Web Host failure"},"ok":false,"protocol_version":1,"request_id":")";
    static constexpr std::string_view suffix = R"("})";
    if (!request.has_request_id || request.request_id.size() != 36 ||
        message.state.load(std::memory_order_acquire) !=
            MessageState::reserved) {
      return false;
    }
    const auto total =
        prefix.size() + request.request_id.size() + suffix.size();
    std::memcpy(message.bytes.data(), prefix.data(), prefix.size());
    std::memcpy(
        message.bytes.data() + prefix.size(),
        request.request_id.data(),
        request.request_id.size());
    std::memcpy(
        message.bytes.data() + prefix.size() + request.request_id.size(),
        suffix.data(),
        suffix.size());
    message.size = total;
    message.origin = &request;
    message.releases_request = true;
    request.state.store(
        RequestState::awaiting_response, std::memory_order_release);
    message.state.store(MessageState::ready, std::memory_order_release);
    return true;
  }

  MessageSlot* reserve_message() noexcept {
    for (auto& message : messages) {
      auto expected = MessageState::free;
      if (message.state.compare_exchange_strong(
              expected,
              MessageState::reserved,
              std::memory_order_acq_rel,
              std::memory_order_acquire)) {
        message.size = 0;
        message.sequence =
            next_message_sequence.fetch_add(1, std::memory_order_relaxed);
        message.origin = nullptr;
        message.releases_request = false;
        return &message;
      }
    }
    return nullptr;
  }

  bool publish_message(
      MessageSlot& message,
      const Json& value,
      RequestSlot* origin,
      bool releases_request) noexcept {
    try {
      const auto encoded = foundation::canonical_json(value);
      if (encoded.size() > message.bytes.size()) {
        fail_control();
        return false;
      }
      std::memcpy(message.bytes.data(), encoded.data(), encoded.size());
      message.size = encoded.size();
      message.origin = origin;
      message.releases_request = releases_request;
      message.state.store(MessageState::ready, std::memory_order_release);
      return true;
    } catch (...) {
      fail_control();
      return false;
    }
  }

  void release_request(RequestSlot& request) noexcept {
    {
      std::lock_guard lock(request_id_mutex);
      request.request_id.clear();
      request.has_request_id = false;
    }
    request.envelope_size = 0;
    request.sidecar_size = 0;
    request.state.store(RequestState::free, std::memory_order_release);
  }

  void release_consumed_request(RequestSlot& request) noexcept {
    if (hooks.on_control == nullptr ||
        !hooks.on_control(hooks.context)) {
      failed.store(true, std::memory_order_release);
      return;
    }
    if (request.state.load(std::memory_order_acquire) !=
        RequestState::response_consumed) {
      fail_control();
      return;
    }
    release_request(request);
  }

  void fail_control() noexcept {
    failed.store(true, std::memory_order_release);
    runtime.fail_and_seal("bridge_failure");
  }

  bool duplicate(const RequestSlot& current, std::string_view id) const {
    std::lock_guard lock(request_id_mutex);
    for (const auto& candidate : requests) {
      if (&candidate == &current || !candidate.has_request_id) {
        continue;
      }
      if (candidate.state.load(std::memory_order_acquire) !=
              RequestState::free &&
          candidate.request_id == id) {
        return true;
      }
    }
    return false;
  }

  void retain_request_id(RequestSlot& request, std::string id) {
    std::lock_guard lock(request_id_mutex);
    request.request_id = std::move(id);
    request.has_request_id = true;
  }

  void process(RequestSlot& request) noexcept {
    ProcessReservations reservations;
    try {
      process_throwing(request, reservations);
    } catch (...) {
      if (reservations.notification != nullptr &&
          reservations.notification->state.load(std::memory_order_acquire) ==
              MessageState::reserved) {
        reservations.notification->state.store(
            MessageState::free, std::memory_order_release);
      }
      fail_control();
      if (reservations.response != nullptr &&
          publish_internal_fallback_noexcept(
              request, *reservations.response)) {
        return;
      }
      if (reservations.response != nullptr &&
          reservations.response->state.load(std::memory_order_acquire) ==
              MessageState::reserved) {
        reservations.response->state.store(
            MessageState::free, std::memory_order_release);
      }
      const auto state = request.state.load(std::memory_order_acquire);
      if (state != RequestState::free &&
          state != RequestState::awaiting_response &&
          state != RequestState::response_consumed) {
        release_request(request);
      }
    }
  }

  void process_throwing(
      RequestSlot& request, ProcessReservations& reservations) {
    auto expected = RequestState::queued;
    if (!request.state.compare_exchange_strong(
            expected,
            RequestState::processing,
            std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      fail_control();
      return;
    }
    if (failed.load(std::memory_order_acquire) ||
        hooks.on_control == nullptr || !hooks.on_control(hooks.context)) {
      release_request(request);
      fail_control();
      return;
    }

    auto* response_slot = reserve_message();
    reservations.response = response_slot;
    if (response_slot == nullptr) {
      release_request(request);
      fail_control();
      return;
    }

    const auto* first =
        reinterpret_cast<const char*>(request.envelope.data());
    const std::string_view bytes(first, request.envelope_size);
    const auto parsed = foundation::valid_utf8(bytes)
                            ? foundation::parse_bounded_json(bytes)
                            : std::nullopt;
    if (!parsed.has_value() || !parsed->is_object() ||
        !parsed->contains("request_id") ||
        !valid_request_id(parsed->at("request_id"))) {
      response_slot->state.store(MessageState::free, std::memory_order_release);
      release_request(request);
      fail_control();
      return;
    }

    retain_request_id(
        request, parsed->at("request_id").get<std::string>());
    Json response;
    std::string operation;
    MessageSlot* notification_slot = nullptr;
    Json notification = nullptr;
    const bool valid_envelope =
        exact_keys(
            *parsed,
            {"protocol_version", "request_id", "operation", "payload"}) &&
        parsed->at("protocol_version").is_number_integer() &&
        parsed->at("protocol_version") == 1 &&
        parsed->at("operation").is_string() &&
        parsed->at("payload").is_object();
    if (!valid_envelope ||
        duplicate(request, request.request_id)) {
      response = bridge_protocol_error();
    } else {
      operation = parsed->at("operation").get<std::string>();
      if (!supported_operation(operation)) {
        response = bridge_protocol_error();
      } else {
        if (operation == "project.open" ||
            operation == "snapshot.reload") {
          notification_slot = reserve_message();
          reservations.notification = notification_slot;
          if (notification_slot == nullptr) {
            response_slot->state.store(
                MessageState::free, std::memory_order_release);
            release_request(request);
            fail_control();
            return;
          }
        }
        response = runtime.dispatch(
            operation,
            parsed->at("payload"),
            std::span<const std::byte>(
                request.sidecar.data(), request.sidecar_size));
        if (notification_slot != nullptr) {
          const auto has_result =
              response.value("ok", false) &&
              response.contains("result") &&
              response.at("result").is_object();
          const auto published =
              has_result &&
              response.at("result").value("runtime_ready", false) &&
              response.at("result").contains("generation") &&
              response.at("result").at("generation").is_number_unsigned();
          const auto rejected =
              has_result &&
              response.at("result").contains("runtime_ready") &&
              response.at("result").at("runtime_ready") == false &&
              response.at("result").contains("snapshot_error") &&
              response.at("result").at("snapshot_error").is_object();
          if (!published && !rejected) {
            notification_slot->state.store(
                MessageState::free, std::memory_order_release);
            notification_slot = nullptr;
            reservations.notification = nullptr;
          } else {
            notification = Json{
                {"protocol_version", 1},
                {"event",
                 published ? "snapshot.published" : "snapshot.rejected"},
                {"payload",
                 published
                     ? Json{{"generation",
                             response.at("result").at("generation")}}
                     : Json{{"error",
                             response.at("result").at("snapshot_error")}}},
            };
          }
        }
      }
    }

    Json bridge_response{
        {"protocol_version", 1},
        {"request_id", request.request_id},
        {"ok", response.at("ok")},
    };
    if (response.at("ok").get<bool>()) {
      bridge_response["result"] = response.at("result");
    } else {
      bridge_response["error"] = response.at("error");
    }
#if !defined(__EMSCRIPTEN__)
    if (hooks.before_response_serialization != nullptr) {
      hooks.before_response_serialization(hooks.context);
    }
#endif
    request.state.store(
        RequestState::awaiting_response, std::memory_order_release);
    if (!publish_message(*response_slot, bridge_response, &request, true)) {
      if (notification_slot != nullptr) {
        notification_slot->state.store(
            MessageState::free, std::memory_order_release);
      }
      reservations.notification = nullptr;
      if (!publish_internal_fallback_noexcept(request, *response_slot)) {
        response_slot->state.store(
            MessageState::free, std::memory_order_release);
        release_request(request);
      }
      return;
    }
    if (notification_slot != nullptr &&
        !publish_message(
            *notification_slot, notification, nullptr, false)) {
      notification_slot->state.store(
          MessageState::free, std::memory_order_release);
      reservations.notification = nullptr;
      return;
    }
  }

  ControlRuntime& runtime;
  BridgeHooks hooks;
  std::array<RequestSlot, kBridgeRequestSlotCount> requests{};
  std::array<MessageSlot, kBridgeMessageSlotCount> messages{};
  mutable std::mutex request_id_mutex;
  std::atomic<std::uint64_t> next_message_sequence{1};
  std::atomic<bool> failed{false};
};

ControlBridge::ControlBridge(ControlRuntime& runtime, BridgeHooks hooks)
    : impl_(std::make_shared<Impl>(runtime, hooks)) {}

BridgeSubmitStatus ControlBridge::submit(
    std::span<const std::byte> envelope,
    std::span<const std::byte> sidecar) noexcept {
  if (envelope.size() > kBridgeMaximumEnvelopeBytes) {
    return BridgeSubmitStatus::envelope_too_large;
  }
  if (sidecar.size() > kBridgeMaximumSidecarBytes) {
    return BridgeSubmitStatus::sidecar_too_large;
  }
  if (impl_->failed.load(std::memory_order_acquire)) {
    return BridgeSubmitStatus::queue_full;
  }
  ControlBridge::Impl::RequestSlot* selected = nullptr;
  for (auto& request : impl_->requests) {
    auto expected = RequestState::free;
    if (request.state.compare_exchange_strong(
            expected,
            RequestState::writing,
            std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      selected = &request;
      break;
    }
  }
  if (selected == nullptr) {
    impl_->failed.store(true, std::memory_order_release);
    if (impl_->hooks.schedule != nullptr) {
      impl_->hooks.schedule(
          impl_->hooks.context,
          &ControlBridge::Impl::fail_thunk,
          impl_.get());
    }
    return BridgeSubmitStatus::queue_full;
  }
  std::copy(envelope.begin(), envelope.end(), selected->envelope.begin());
  std::copy(sidecar.begin(), sidecar.end(), selected->sidecar.begin());
  selected->envelope_size = envelope.size();
  selected->sidecar_size = sidecar.size();
  selected->state.store(RequestState::queued, std::memory_order_release);
  if (impl_->hooks.schedule == nullptr ||
      !impl_->hooks.schedule(
          impl_->hooks.context,
          &ControlBridge::Impl::process_thunk,
          selected)) {
    impl_->release_request(*selected);
    impl_->failed.store(true, std::memory_order_release);
    return BridgeSubmitStatus::proxy_failed;
  }
  return BridgeSubmitStatus::accepted;
}

BridgePollStatus ControlBridge::poll(
    std::span<std::byte> output,
    std::size_t& required) noexcept {
  ControlBridge::Impl::MessageSlot* selected = nullptr;
  auto selected_sequence = std::numeric_limits<std::uint64_t>::max();
  for (auto& message : impl_->messages) {
    if (message.state.load(std::memory_order_acquire) ==
            MessageState::ready &&
        message.sequence < selected_sequence) {
      selected = &message;
      selected_sequence = message.sequence;
    }
  }
  if (selected == nullptr) {
    required = 0;
    return impl_->failed.load(std::memory_order_acquire)
               ? BridgePollStatus::failed
               : BridgePollStatus::empty;
  }
  required = selected->size;
  if (output.size() < selected->size) {
    return BridgePollStatus::output_too_small;
  }
  std::copy_n(selected->bytes.begin(), selected->size, output.begin());
  auto* origin = selected->origin;
  const auto releases_request = selected->releases_request;
  selected->state.store(MessageState::free, std::memory_order_release);
  if (releases_request && origin != nullptr) {
    auto expected = RequestState::awaiting_response;
    if (!origin->state.compare_exchange_strong(
            expected,
            RequestState::response_consumed,
            std::memory_order_acq_rel,
            std::memory_order_acquire) ||
        impl_->hooks.schedule == nullptr ||
        !impl_->hooks.schedule(
            impl_->hooks.context,
            &ControlBridge::Impl::release_thunk,
            origin)) {
      impl_->failed.store(true, std::memory_order_release);
    }
  }
  return BridgePollStatus::message;
}

bool ControlBridge::failed() const noexcept {
  return impl_->failed.load(std::memory_order_acquire);
}

}  // namespace lmdj::web_host::detail

#if defined(__EMSCRIPTEN__)
namespace {

using lmdj::audio::RuntimePreparationLimits;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;
using lmdj::web_host::ControlRuntime;
using lmdj::web_host::detail::BridgeHooks;
using lmdj::web_host::detail::ControlBridge;

em_proxying_queue* web_proxy_queue = nullptr;
pthread_t web_control_thread{};
std::unique_ptr<ControlRuntime> web_runtime;
std::unique_ptr<ControlBridge> web_bridge_owner;
std::atomic<ControlBridge*> web_bridge{nullptr};

bool schedule_control(
    void*,
    void (*function)(void*) noexcept,
    void* argument) noexcept {
  return emscripten_proxy_async(
             web_proxy_queue,
             web_control_thread,
             function,
             argument) != 0;
}

bool on_control(void*) noexcept {
  return pthread_equal(pthread_self(), web_control_thread) != 0;
}

}  // namespace

extern "C" {

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_submit(
    const std::byte* envelope,
    std::size_t envelope_size,
    const std::byte* sidecar,
    std::size_t sidecar_size) {
  if ((envelope == nullptr && envelope_size != 0) ||
      (sidecar == nullptr && sidecar_size != 0)) {
    return -1;
  }
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  if (bridge == nullptr) {
    return -1;
  }
  return static_cast<int>(bridge->submit(
      std::span<const std::byte>(envelope, envelope_size),
      std::span<const std::byte>(sidecar, sidecar_size)));
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_poll(
    std::byte* output,
    std::size_t output_size,
    std::size_t* required) {
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  if (bridge == nullptr || required == nullptr ||
      (output == nullptr && output_size != 0)) {
    return -1;
  }
  return static_cast<int>(bridge->poll(
      std::span<std::byte>(output, output_size), *required));
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_failed() {
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  return bridge != nullptr && bridge->failed() ? 1 : 0;
}

}  // extern "C"

int main() {
  web_control_thread = pthread_self();
  web_proxy_queue = em_proxying_queue_create();
  if (web_proxy_queue == nullptr) {
    return 1;
  }
  const auto workspace =
      std::filesystem::path("/lmdj-workspace").lexically_normal();
  auto created = ControlRuntime::create(
      workspace,
      Application(ApplicationConfig{
          workspace,
          std::make_shared<Registry>(),
          ProviderPolicy{},
          {},
      }),
      RuntimePreparationLimits{
          1'048'576,
          240'000,
          67'108'864,
          134'217'728,
      });
  if (!created.has_value()) {
    return 1;
  }
  web_runtime = std::move(created.value());
  web_bridge_owner = std::make_unique<ControlBridge>(
      *web_runtime,
      BridgeHooks{nullptr, schedule_control, on_control});
  web_bridge.store(web_bridge_owner.get(), std::memory_order_release);
  emscripten_exit_with_live_runtime();
  return 0;
}
#endif
