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
#include <thread>
#include <utility>

#include <lmdj/foundation/json.hpp>

#if defined(__EMSCRIPTEN__)
#include <pthread.h>

#include <emscripten/emscripten.h>
#include <emscripten/proxying.h>
#include <emscripten/threading.h>

#include <lmdj/audio/web/realtime_audio_worklet.hpp>
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
using lmdj::audio::RuntimeTriggerOutcomeEvent;
using lmdj::audio::web::RealtimeAudioWorklet;
using lmdj::audio::web::RealtimeAudioWorkletFatal;
using lmdj::audio::web::RealtimeAudioWorkletGate;
using lmdj::audio::web::RealtimeAudioWorkletHooks;
using lmdj::audio::web::RealtimeAudioWorkletStart;
using lmdj::audio::web::RealtimeAudioWorkletState;
using lmdj::facade::Application;
using lmdj::facade::ApplicationConfig;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;
using lmdj::web_host::ControlRuntime;
using lmdj::web_host::detail::BridgeHooks;
using lmdj::web_host::detail::ControlBridge;
using lmdj::web_host::detail::ControlRuntimeAudioAccess;
using lmdj::web_host::detail::AudioQuiescenceCoordinator;

em_proxying_queue* web_proxy_queue = nullptr;
pthread_t web_control_thread{};
std::unique_ptr<ControlRuntime> web_runtime;
std::unique_ptr<ControlBridge> web_bridge_owner;
std::atomic<ControlBridge*> web_bridge{nullptr};
std::unique_ptr<RealtimeAudioWorklet> web_audio_owner;
std::atomic<RealtimeAudioWorklet*> web_audio{nullptr};
enum class AudioFailureCommitState : std::uint32_t {
  idle,
  reserving,
  pending,
  committed,
};
std::atomic<AudioFailureCommitState> web_audio_control_failure_state{
    AudioFailureCommitState::idle};
std::atomic<RealtimeAudioWorkletFatal> web_audio_control_failure_code{
    RealtimeAudioWorkletFatal::none};

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
struct OutcomeDiagnostic {
  std::atomic<std::uint32_t> state{0};
  std::array<RuntimeTriggerOutcomeEvent, 64> events{};
  std::size_t count = 0;
};

OutcomeDiagnostic outcome_diagnostic;
std::array<char, lmdj::web_host::detail::kBridgeMaximumEnvelopeBytes + 1>
    diagnostic_poll_buffer{};
#endif

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

lmdj::foundation::Result<void> await_audio_quiescent(
    void* context, std::uint32_t timeout_ms) noexcept {
  return static_cast<RealtimeAudioWorklet*>(context)->await_quiescent(
      timeout_ms);
}

lmdj::foundation::Result<void> begin_audio_rendering(
    void* context) noexcept {
  return static_cast<RealtimeAudioWorklet*>(context)->begin_rendering();
}

bool audio_ready(void* context) noexcept {
  return static_cast<RealtimeAudioWorklet*>(context)->ready();
}

std::uint64_t acknowledged_audio_generation(void* context) noexcept {
  return static_cast<RealtimeAudioWorklet*>(context)
      ->acknowledged_generation();
}

bool schedule_audio_control_failure(
    RealtimeAudioWorkletFatal fatal) noexcept;

void install_audio_coordinator(void*) noexcept {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr || web_runtime == nullptr) {
    if (adapter != nullptr) {
      adapter->complete_control_install(false);
    }
    return;
  }
  const auto installed = ControlRuntimeAudioAccess::install(
      *web_runtime,
      AudioQuiescenceCoordinator{
          adapter,
          &await_audio_quiescent,
          &begin_audio_rendering,
          &audio_ready,
          &acknowledged_audio_generation,
      });
  adapter->complete_control_install(installed.has_value());
  if (adapter->fatal() ==
      RealtimeAudioWorkletFatal::coordinator_install_failed) {
    static_cast<void>(schedule_audio_control_failure(
        RealtimeAudioWorkletFatal::coordinator_install_failed));
  }
}

const char* audio_failure_reason(RealtimeAudioWorkletFatal fatal) noexcept {
  switch (fatal) {
    case RealtimeAudioWorkletFatal::unsupported_sample_rate:
    case RealtimeAudioWorkletFatal::unsupported_render_quantum:
      return "unsupported_web_runtime";
    case RealtimeAudioWorkletFatal::worklet_thread_start_failed:
      return "worklet_thread_start_failed";
    case RealtimeAudioWorkletFatal::processor_create_failed:
      return "processor_create_failed";
    case RealtimeAudioWorkletFatal::node_create_failed:
      return "node_create_failed";
    case RealtimeAudioWorkletFatal::coordinator_install_failed:
      return "coordinator_install_failed";
    case RealtimeAudioWorkletFatal::bootstrap_timeout:
      return "bootstrap_timeout";
    default:
      return "audio_bootstrap_failed";
  }
}

void fail_audio_on_control(void*) noexcept {
  const auto fatal =
      web_audio_control_failure_code.load(std::memory_order_acquire);
  if (web_runtime != nullptr) {
    web_runtime->fail_and_seal(audio_failure_reason(fatal));
  }
  web_audio_control_failure_state.store(
      AudioFailureCommitState::committed,
      std::memory_order_release);
}

bool schedule_audio_control_failure(
    RealtimeAudioWorkletFatal fatal) noexcept {
  auto expected = AudioFailureCommitState::idle;
  if (!web_audio_control_failure_state.compare_exchange_strong(
          expected,
          AudioFailureCommitState::reserving,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    while (expected == AudioFailureCommitState::reserving) {
      std::this_thread::yield();
      expected = web_audio_control_failure_state.load(
          std::memory_order_acquire);
    }
    return expected == AudioFailureCommitState::pending ||
           expected == AudioFailureCommitState::committed;
  }
  web_audio_control_failure_code.store(fatal, std::memory_order_release);
  if (on_control(nullptr)) {
    fail_audio_on_control(nullptr);
    return true;
  }
  web_audio_control_failure_state.store(
      AudioFailureCommitState::pending,
      std::memory_order_release);
  if (web_proxy_queue != nullptr &&
      emscripten_proxy_async(
          web_proxy_queue,
          web_control_thread,
          &fail_audio_on_control,
          nullptr) != 0) {
    return true;
  }
  web_audio_control_failure_state.store(
      AudioFailureCommitState::idle,
      std::memory_order_release);
  return false;
}

bool schedule_audio_install(void*) noexcept {
  return web_proxy_queue != nullptr &&
         emscripten_proxy_async(
             web_proxy_queue,
             web_control_thread,
             &install_audio_coordinator,
             nullptr) != 0;
}

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
void fail_processor_error_on_control(void*) noexcept {
  if (web_runtime != nullptr) {
    auto* adapter = web_audio.load(std::memory_order_acquire);
    if (adapter != nullptr) {
      static_cast<void>(adapter->await_quiescent(1'000));
    }
    web_runtime->engine().stop();
    web_runtime->fail_and_seal("processor_error");
  }
}

void drain_outcomes_on_control(void*) noexcept {
  if (web_runtime == nullptr) {
    outcome_diagnostic.count = 0;
    outcome_diagnostic.state.store(3, std::memory_order_release);
    return;
  }
  const auto outcomes = web_runtime->drain_outcomes();
  outcome_diagnostic.count =
      std::min(outcomes.size(), outcome_diagnostic.events.size());
  std::copy_n(
      outcomes.begin(),
      outcome_diagnostic.count,
      outcome_diagnostic.events.begin());
  outcome_diagnostic.state.store(2, std::memory_order_release);
}
#endif

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

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_start(
    std::int32_t audio_context_handle) {
  if (!emscripten_is_main_browser_thread()) {
    return -1;
  }
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr) {
    return static_cast<int>(RealtimeAudioWorkletStart::unpublished);
  }
  const auto result = adapter->start_on_browser_main(audio_context_handle);
  if (result == RealtimeAudioWorkletStart::unsupported_sample_rate ||
      result == RealtimeAudioWorkletStart::unsupported_render_quantum) {
    if (!schedule_audio_control_failure(adapter->fatal())) {
      return static_cast<int>(RealtimeAudioWorkletStart::fatal);
    }
  }
  return static_cast<int>(result);
}

EMSCRIPTEN_KEEPALIVE std::int32_t lmdj_web_audio_state() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr
             ? -2
             : static_cast<std::int32_t>(adapter->state());
}

EMSCRIPTEN_KEEPALIVE std::int32_t lmdj_web_audio_fatal() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr
             ? static_cast<std::int32_t>(
                   RealtimeAudioWorkletFatal::invalid_audio_context)
             : static_cast<std::int32_t>(adapter->fatal());
}

EMSCRIPTEN_KEEPALIVE std::int32_t lmdj_web_audio_observed_sample_rate() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr ? 0 : adapter->observed_sample_rate();
}

EMSCRIPTEN_KEEPALIVE std::int32_t lmdj_web_audio_observed_render_quantum() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr ? 0 : adapter->observed_render_quantum();
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_control_failure_committed() {
  return web_audio_control_failure_state.load(std::memory_order_acquire) ==
                 AudioFailureCommitState::committed
             ? 1
             : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_commit_failure() {
  if (!emscripten_is_main_browser_thread()) {
    return 0;
  }
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr) {
    return 0;
  }
  const auto fatal = adapter->fatal();
  switch (fatal) {
    case RealtimeAudioWorkletFatal::wrong_browser_thread:
    case RealtimeAudioWorkletFatal::unsupported_sample_rate:
    case RealtimeAudioWorkletFatal::unsupported_render_quantum:
    case RealtimeAudioWorkletFatal::worklet_thread_start_failed:
    case RealtimeAudioWorkletFatal::processor_create_failed:
    case RealtimeAudioWorkletFatal::node_create_failed:
    case RealtimeAudioWorkletFatal::coordinator_install_failed:
    case RealtimeAudioWorkletFatal::bootstrap_timeout:
      return schedule_audio_control_failure(fatal) ? 1 : 0;
    default:
      return 0;
  }
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_bootstrap_timeout() {
  if (!emscripten_is_main_browser_thread()) {
    return 0;
  }
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr) {
    return 0;
  }
  adapter->latch_bootstrap_timeout();
  return schedule_audio_control_failure(adapter->fatal()) ? 1 : 0;
}

#if defined(LMDJ_WEB_AUDIO_CONFORMANCE)
EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_observed_frames() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr ? 0 : adapter->observed_frames();
}

EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_render_calls() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr ? 0 : adapter->render_calls();
}

EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_output_energy() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr ? 0 : adapter->output_energy_microunits();
}

EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_ack_generation() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr
             ? 0
             : static_cast<std::uint32_t>(
                   adapter->acknowledged_generation());
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_gate_closed() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter != nullptr && adapter->callback_gate_closed() ? 1 : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_in_flight() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter != nullptr && adapter->callback_in_flight() ? 1 : 0;
}

EMSCRIPTEN_KEEPALIVE std::int32_t lmdj_web_audio_test_gate_state() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr
             ? static_cast<std::int32_t>(RealtimeAudioWorkletGate::terminal)
             : static_cast<std::int32_t>(adapter->gate_state());
}

EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_start_calls() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr ? 0 : adapter->start_calls();
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_validate_configuration(
    std::int32_t sample_rate, std::int32_t render_quantum) {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr) {
    return static_cast<int>(RealtimeAudioWorkletStart::unpublished);
  }
  const auto result = adapter->validate_configuration_for_conformance(
      sample_rate, render_quantum);
  if ((result == RealtimeAudioWorkletStart::unsupported_sample_rate ||
       result == RealtimeAudioWorkletStart::unsupported_render_quantum) &&
      !schedule_audio_control_failure(adapter->fatal())) {
    return static_cast<int>(RealtimeAudioWorkletStart::fatal);
  }
  return static_cast<int>(result);
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_bootstrap_failure(
    std::int32_t fatal_code) {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr || !emscripten_is_main_browser_thread()) {
    return 0;
  }
  return adapter->latch_bootstrap_fatal_for_conformance(
             static_cast<RealtimeAudioWorkletFatal>(fatal_code))
             ? 1
             : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_invalid_shape(
    std::int32_t frames) {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter != nullptr &&
                 adapter->invoke_invalid_shape_for_conformance(frames)
             ? 1
             : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_generation_matches(
    std::uint32_t expected_generation) {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter != nullptr &&
                 adapter->generation_matches_for_conformance(
                     expected_generation)
             ? 1
             : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_processor_error() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr || web_proxy_queue == nullptr) {
    return 0;
  }
  adapter->latch_processor_error();
  return emscripten_proxy_async(
             web_proxy_queue,
             web_control_thread,
             &fail_processor_error_on_control,
             nullptr) != 0
             ? 1
             : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_request_outcomes() {
  if (web_proxy_queue == nullptr) {
    return 0;
  }
  std::uint32_t expected = 0;
  if (!outcome_diagnostic.state.compare_exchange_strong(
          expected,
          1,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    return 0;
  }
  if (emscripten_proxy_async(
          web_proxy_queue,
          web_control_thread,
          &drain_outcomes_on_control,
          nullptr) == 0) {
    outcome_diagnostic.state.store(0, std::memory_order_release);
    return 0;
  }
  return 1;
}

EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_outcome_state() {
  return outcome_diagnostic.state.load(std::memory_order_acquire);
}

EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_outcome_count() {
  return outcome_diagnostic.state.load(std::memory_order_acquire) == 2
             ? static_cast<std::uint32_t>(outcome_diagnostic.count)
             : 0;
}

EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_outcome_sequence(
    std::uint32_t index) {
  return outcome_diagnostic.state.load(std::memory_order_acquire) == 2 &&
                 index < outcome_diagnostic.count
             ? static_cast<std::uint32_t>(
                   outcome_diagnostic.events[index].sequence)
             : 0;
}

EMSCRIPTEN_KEEPALIVE std::uint32_t lmdj_web_audio_test_outcome_code(
    std::uint32_t index) {
  return outcome_diagnostic.state.load(std::memory_order_acquire) == 2 &&
                 index < outcome_diagnostic.count
             ? static_cast<std::uint32_t>(
                   outcome_diagnostic.events[index].outcome)
             : UINT32_MAX;
}

EMSCRIPTEN_KEEPALIVE double lmdj_web_audio_test_outcome_frame(
    std::uint32_t index) {
  return outcome_diagnostic.state.load(std::memory_order_acquire) == 2 &&
                 index < outcome_diagnostic.count
             ? static_cast<double>(
                   outcome_diagnostic.events[index].runtime_frame)
             : -1.0;
}

EMSCRIPTEN_KEEPALIVE void lmdj_web_audio_test_clear_outcomes() {
  outcome_diagnostic.count = 0;
  outcome_diagnostic.state.store(0, std::memory_order_release);
}

EMSCRIPTEN_KEEPALIVE const char* lmdj_web_audio_test_poll() {
  std::size_t required = 0;
  const auto status = lmdj_web_host_poll(
      reinterpret_cast<std::byte*>(diagnostic_poll_buffer.data()),
      diagnostic_poll_buffer.size() - 1,
      &required);
  if (status != static_cast<int>(
                    lmdj::web_host::detail::BridgePollStatus::message) ||
      required >= diagnostic_poll_buffer.size()) {
    return nullptr;
  }
  diagnostic_poll_buffer[required] = '\0';
  return diagnostic_poll_buffer.data();
}
#endif

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
  web_audio_owner = std::make_unique<RealtimeAudioWorklet>(
      web_runtime->engine(),
      RealtimeAudioWorkletHooks{
          web_runtime.get(),
          &schedule_audio_install,
      });
  web_audio.store(web_audio_owner.get(), std::memory_order_release);
  web_bridge_owner = std::make_unique<ControlBridge>(
      *web_runtime,
      BridgeHooks{nullptr, schedule_control, on_control});
  web_bridge.store(web_bridge_owner.get(), std::memory_order_release);
  emscripten_exit_with_live_runtime();
  return 0;
}
#endif
