#include <lmdj/web_runtime/control_runtime.hpp>
#include <lmdj/web_runtime/manifest_gate.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <new>
#include <span>
#include <string>
#include <string_view>
#include <thread>
#include <utility>

#include <lmdj/foundation/json.hpp>
#include <lmdj/facade/mutation_publish_scope.hpp>

#if defined(__EMSCRIPTEN__)
#include <pthread.h>

#include <emscripten/emscripten.h>
#include <emscripten/proxying.h>
#include <emscripten/threading.h>

#include <lmdj/audio/web/realtime_audio_worklet.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>
#endif

#if defined(__EMSCRIPTEN__) && defined(LMDJ_WEB_AUDIO_CONFORMANCE)
namespace {
struct ConformanceOutcomeMirror {
  std::atomic<std::uint32_t> state{0};
  std::array<lmdj::audio::RuntimeTriggerOutcomeEvent, 64> events{};
  std::size_t count = 0;
};

ConformanceOutcomeMirror conformance_outcome_mirror;
std::atomic<bool> conformance_outcome_mirror_writer_pending{false};
std::atomic<bool> conformance_outcome_mirror_writer_release{false};
std::atomic<bool> conformance_outcome_mirror_writer_timed_out{false};

struct ConformanceOutcomeWriterRequest {
  std::uint32_t sequence = 0;
  std::uint32_t outcome = 0;
  std::uint32_t runtime_frame = 0;
};

enum class ConformanceOutcomeMirrorRead : std::uint8_t {
  unavailable,
  writing,
  consumed,
};

ConformanceOutcomeMirrorRead consume_conformance_outcome_mirror(
    std::span<lmdj::audio::RuntimeTriggerOutcomeEvent> destination,
    std::size_t& count) noexcept {
  std::uint32_t expected = 2;
  if (!conformance_outcome_mirror.state.compare_exchange_strong(
          expected,
          1,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    return expected == 1 ? ConformanceOutcomeMirrorRead::writing
                         : ConformanceOutcomeMirrorRead::unavailable;
  }
  count = std::min(
      conformance_outcome_mirror.count, destination.size());
  std::copy_n(
      conformance_outcome_mirror.events.begin(), count, destination.begin());
  conformance_outcome_mirror.count = 0;
  conformance_outcome_mirror.state.store(0, std::memory_order_release);
  return ConformanceOutcomeMirrorRead::consumed;
}

void mirror_conformance_outcomes(
    std::span<const lmdj::audio::RuntimeTriggerOutcomeEvent> outcomes)
    noexcept {
  std::uint32_t expected = 0;
  if (!conformance_outcome_mirror.state.compare_exchange_strong(
          expected,
          1,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    return;
  }
  conformance_outcome_mirror.count = std::min(
      outcomes.size(), conformance_outcome_mirror.events.size());
  std::copy_n(
      outcomes.begin(),
      conformance_outcome_mirror.count,
      conformance_outcome_mirror.events.begin());
  conformance_outcome_mirror.state.store(2, std::memory_order_release);
}
}  // namespace
#endif

namespace lmdj::web_runtime::detail {
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

enum class PublicationState : std::uint8_t {
  open,
  cancelled,
  publish_claimed,
  committed,
  aborted,
};

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

Json bridge_timeout_error() {
  return {
      {"ok", false},
      {"error",
       {
           {"code", "HOST_TIMEOUT"},
           {"message", "host request timed out"},
           {"details", Json::object()},
       }},
  };
}

std::chrono::milliseconds operation_deadline(std::string_view operation) {
  if (operation == "host.close") {
    return std::chrono::seconds(10);
  }
  if (operation == "host.status" || operation == "audio.activate" ||
      operation == "audio.suspend" || operation == "trigger") {
    return std::chrono::seconds(1);
  }
  return std::chrono::seconds(30);
}

bool supported_operation(std::string_view operation) {
  static constexpr std::array<std::string_view, 21> operations{
      "host.status",
      "project.create",
      "project.open",
      "project.inspect",
      "project.list",
      "project.import.begin",
      "project.import.index",
      "project.import.entry",
      "project.import.commit",
      "project.import.abort",
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
    std::chrono::steady_clock::time_point submitted_at{};
    std::chrono::steady_clock::time_point deadline{};
    std::optional<std::chrono::steady_clock::time_point> caller_deadline;
    std::string request_id;
    bool has_request_id = false;
    std::atomic<PublicationState> publication{PublicationState::open};
  };

  struct DeadlineProof {
    mutable std::mutex request_id_mutex;
    std::string request_id;
    std::atomic<std::uint8_t> gate{0};
    std::atomic<bool> force_publication_error{false};
    std::atomic<bool> released{false};
    std::atomic<bool> entered_facade{false};
    std::atomic<bool> claim_attempted{false};
    std::atomic<bool> claim_started_open{false};
    std::atomic<PublicationState> publication{PublicationState::open};
    std::atomic<std::uint8_t> cancel_observation{0};
    std::atomic<std::uint8_t> cancel_calls{0};
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

  static void service_realtime_thunk(void* argument) noexcept {
    static_cast<Impl*>(argument)->service_realtime();
  }

  static bool claim_publication(void* context) noexcept {
    auto& request = *static_cast<RequestSlot*>(context);
    request.owner->mark_claim_attempted(request);
    request.owner->wait_for_deadline_proof(request, 3);
    auto state = request.publication.load(std::memory_order_acquire);
    if (state == PublicationState::committed ||
        state == PublicationState::aborted ||
        state == PublicationState::publish_claimed) {
      return true;
    }
    if (state == PublicationState::cancelled ||
        std::chrono::steady_clock::now() >= request.deadline) {
      auto expected = PublicationState::open;
      request.publication.compare_exchange_strong(
          expected,
          PublicationState::cancelled,
          std::memory_order_acq_rel,
          std::memory_order_acquire);
      request.publication.notify_all();
      request.owner->mark_publication(request, PublicationState::cancelled);
      return false;
    }
    auto expected = PublicationState::open;
    if (request.publication.compare_exchange_strong(
            expected,
            PublicationState::publish_claimed,
            std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      request.owner->mark_publication(
          request, PublicationState::publish_claimed);
      request.owner->wait_for_deadline_proof(request, 2);
      return true;
    }
    return expected == PublicationState::publish_claimed ||
           expected == PublicationState::committed ||
           expected == PublicationState::aborted;
  }

  static void commit_publication(void* context) noexcept {
    auto& request = *static_cast<RequestSlot*>(context);
    auto expected = PublicationState::publish_claimed;
    if (request.publication.compare_exchange_strong(
        expected,
        PublicationState::committed,
        std::memory_order_acq_rel,
        std::memory_order_acquire)) {
      request.owner->mark_publication(request, PublicationState::committed);
    }
  }

  static void abort_publication(void* context) noexcept {
    auto& request = *static_cast<RequestSlot*>(context);
    auto expected = PublicationState::publish_claimed;
    if (request.publication.compare_exchange_strong(
        expected,
        PublicationState::aborted,
        std::memory_order_acq_rel,
        std::memory_order_acquire)) {
      request.owner->mark_publication(request, PublicationState::aborted);
    }
  }

  static bool force_publication_failure(void* context) noexcept {
    auto& request = *static_cast<RequestSlot*>(context);
    return request.owner->proof_matches(request) &&
           request.owner->deadline_proof.force_publication_error.load(
               std::memory_order_acquire);
  }

  bool proof_matches(const RequestSlot& request) const noexcept {
    if (deadline_proof.gate.load(std::memory_order_acquire) == 0) {
      return false;
    }
    std::lock_guard lock(deadline_proof.request_id_mutex);
    return request.has_request_id &&
           deadline_proof.request_id == request.request_id;
  }

  bool proof_matches(std::string_view request_id) const noexcept {
    if (deadline_proof.gate.load(std::memory_order_acquire) == 0) {
      return false;
    }
    std::lock_guard lock(deadline_proof.request_id_mutex);
    return deadline_proof.request_id == request_id;
  }

  void record_deadline_cancel(
      std::string_view request_id, BridgeCancelStatus status) noexcept {
    if (!proof_matches(request_id)) {
      return;
    }
    deadline_proof.cancel_observation.store(
        status == BridgeCancelStatus::publish_claimed
            ? 1
            : status == BridgeCancelStatus::cancelled ? 2 : 3,
        std::memory_order_release);
    auto calls = deadline_proof.cancel_calls.load(std::memory_order_acquire);
    while (calls != std::numeric_limits<std::uint8_t>::max() &&
           !deadline_proof.cancel_calls.compare_exchange_weak(
               calls,
               static_cast<std::uint8_t>(calls + 1),
               std::memory_order_acq_rel,
               std::memory_order_acquire)) {
    }
  }

  void mark_entered_facade(const RequestSlot& request) noexcept {
    if (proof_matches(request)) {
      deadline_proof.entered_facade.store(true, std::memory_order_release);
    }
  }

  void mark_claim_attempted(const RequestSlot& request) noexcept {
    if (proof_matches(request)) {
      deadline_proof.claim_started_open.store(
          request.publication.load(std::memory_order_acquire) ==
              PublicationState::open,
          std::memory_order_relaxed);
      deadline_proof.claim_attempted.store(true, std::memory_order_release);
    }
  }

  void mark_publication(
      const RequestSlot& request, PublicationState state) noexcept {
    if (proof_matches(request)) {
      deadline_proof.publication.store(state, std::memory_order_release);
    }
  }

  void wait_for_deadline_proof(
      const RequestSlot& request, std::uint8_t gate) noexcept {
    if (!proof_matches(request) ||
        deadline_proof.gate.load(std::memory_order_acquire) != gate) {
      return;
    }
    while (!deadline_proof.released.load(std::memory_order_acquire)) {
      deadline_proof.released.wait(false, std::memory_order_acquire);
    }
  }

  void wait_for_responsive_cancellation_proof(
      RequestSlot& request) noexcept {
    if (!proof_matches(request) ||
        deadline_proof.gate.load(std::memory_order_acquire) != 1) {
      return;
    }
    auto publication = request.publication.load(std::memory_order_acquire);
    while (publication == PublicationState::open) {
      request.publication.wait(
          PublicationState::open, std::memory_order_acquire);
      publication = request.publication.load(std::memory_order_acquire);
    }
  }

  void service_realtime() noexcept {
    struct Completion {
      Impl& owner;
      ~Completion() { owner.complete_realtime_service(); }
    } completion{*this};

    realtime_service_requested.store(false, std::memory_order_release);
    if (hooks.on_control == nullptr || !hooks.on_control(hooks.context)) {
      fail_control();
      return;
    }
    MessageSlot* message = nullptr;
    try {
      static_cast<void>(runtime.drain_capture());
#if !defined(__EMSCRIPTEN__)
      if (hooks.after_capture_drain != nullptr) {
        hooks.after_capture_drain(hooks.context);
      }
#endif
      if (!runtime.validate_realtime_health()) {
        fail_control();
        return;
      }
      message = reserve_message();
      if (message == nullptr) {
        return;
      }
      if (runtime.failed()) {
        message->state.store(MessageState::free, std::memory_order_release);
        fail_control();
        return;
      }
      const auto outcomes = runtime.drain_outcomes();
#if !defined(__EMSCRIPTEN__)
      if (hooks.after_outcome_drain != nullptr) {
        hooks.after_outcome_drain(hooks.context);
      }
#endif
      if (!runtime.validate_realtime_health()) {
        message->state.store(MessageState::free, std::memory_order_release);
        fail_control();
        return;
      }
      if (runtime.failed()) {
        message->state.store(MessageState::free, std::memory_order_release);
        fail_control();
        return;
      }
      if (outcomes.empty()) {
        message->state.store(MessageState::free, std::memory_order_release);
      } else {
#if defined(__EMSCRIPTEN__) && defined(LMDJ_WEB_AUDIO_CONFORMANCE)
        mirror_conformance_outcomes(outcomes);
#endif
        auto events = Json::array();
        for (const auto& outcome : outcomes) {
          events.push_back({
              {"sequence", outcome.sequence},
              {"outcome",
               outcome.outcome == audio::RuntimeTriggerOutcome::voice_started
                   ? "voice_started"
                   : "voice_capacity"},
              {"runtime_frame", outcome.runtime_frame},
          });
        }
        if (!publish_message(
                *message,
                Json{
                    {"protocol_version", 1},
                    {"event", "runtime.trigger_outcomes"},
                    {"payload", {{"events", std::move(events)}}},
                },
                nullptr,
                false)) {
          message->state.store(MessageState::free, std::memory_order_release);
        }
      }
    } catch (...) {
      if (message != nullptr) {
        message->state.store(MessageState::free, std::memory_order_release);
      }
      fail_control();
    }
  }

  void complete_realtime_service() noexcept {
    realtime_service_scheduled.store(false, std::memory_order_release);
    if (realtime_service_enabled.load(std::memory_order_acquire) &&
        realtime_service_requested.load(std::memory_order_acquire)) {
      schedule_realtime_service();
    }
  }

  void request_realtime_service() noexcept {
    if (!realtime_service_enabled.load(std::memory_order_acquire) ||
        failed.load(std::memory_order_acquire)) {
      return;
    }
    realtime_service_requested.store(true, std::memory_order_release);
    schedule_realtime_service();
  }

  void schedule_realtime_service() noexcept {
    if (failed.load(std::memory_order_acquire)) {
      return;
    }
    auto expected = false;
    if (!realtime_service_scheduled.compare_exchange_strong(
            expected,
            true,
            std::memory_order_acq_rel,
            std::memory_order_acquire)) {
      return;
    }
    if (hooks.schedule == nullptr ||
        !hooks.schedule(
            hooks.context, &service_realtime_thunk, this)) {
      realtime_service_requested.store(false, std::memory_order_release);
      realtime_service_scheduled.store(false, std::memory_order_release);
      failed.store(true, std::memory_order_release);
    }
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
    request.publication.store(
        PublicationState::open, std::memory_order_release);
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
    realtime_service_enabled.store(false, std::memory_order_release);
    realtime_service_requested.store(false, std::memory_order_release);
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
    bool terminal_after_response = false;
    bool has_deadline = false;
    std::chrono::steady_clock::time_point deadline{};
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
        deadline = request.submitted_at + operation_deadline(operation);
        if (request.caller_deadline.has_value()) {
          deadline = std::min(deadline, *request.caller_deadline);
        }
        request.deadline = deadline;
        has_deadline = true;
        if (request.publication.load(std::memory_order_acquire) ==
                PublicationState::cancelled ||
            std::chrono::steady_clock::now() >= deadline) {
          request.publication.store(
              PublicationState::cancelled, std::memory_order_release);
          runtime.fail_and_seal("request_timeout");
          response = bridge_timeout_error();
          terminal_after_response = true;
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
          const auto runtime_was_failed = runtime.failed();
          const facade::detail::MutationPublishScope publish_scope({
              &request,
              &claim_publication,
              &commit_publication,
              &abort_publication,
              &force_publication_failure,
          });
          mark_entered_facade(request);
          wait_for_responsive_cancellation_proof(request);
          if (request.publication.load(std::memory_order_acquire) ==
              PublicationState::cancelled) {
            response = bridge_timeout_error();
          } else {
            response = runtime.dispatch(
                operation,
                parsed->at("payload"),
                std::span<const std::byte>(
                    request.sidecar.data(), request.sidecar_size),
                request.submitted_at);
            if (!runtime_was_failed && runtime.failed()) {
              terminal_after_response = true;
            }
            realtime_service_enabled.store(
                runtime.engine().telemetry().state ==
                    audio::RealtimeState::running,
                std::memory_order_release);
          }
        }
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

#if !defined(__EMSCRIPTEN__)
    if (hooks.before_response_serialization != nullptr) {
      hooks.before_response_serialization(hooks.context);
    }
#endif
    auto publication = request.publication.load(std::memory_order_acquire);
    if (has_deadline && publication == PublicationState::open &&
        std::chrono::steady_clock::now() >= deadline) {
      auto expected = PublicationState::open;
      request.publication.compare_exchange_strong(
          expected,
          PublicationState::cancelled,
          std::memory_order_acq_rel,
          std::memory_order_acquire);
      publication = request.publication.load(std::memory_order_acquire);
    }
    if (has_deadline && publication == PublicationState::cancelled) {
      mark_publication(request, PublicationState::cancelled);
      request.publication.notify_all();
      runtime.fail_and_seal("request_timeout");
      response = bridge_timeout_error();
      terminal_after_response = true;
      if (notification_slot != nullptr) {
        notification_slot->state.store(
            MessageState::free, std::memory_order_release);
        notification_slot = nullptr;
        reservations.notification = nullptr;
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
    if (terminal_after_response) {
      fail_control();
    }
  }

  ControlRuntime& runtime;
  BridgeHooks hooks;
  std::array<RequestSlot, kBridgeRequestSlotCount> requests{};
  std::array<MessageSlot, kBridgeMessageSlotCount> messages{};
  DeadlineProof deadline_proof;
  mutable std::mutex request_id_mutex;
  std::atomic<std::uint64_t> next_message_sequence{1};
  std::atomic<bool> realtime_service_enabled{false};
  std::atomic<bool> realtime_service_requested{false};
  std::atomic<bool> realtime_service_scheduled{false};
  std::atomic<bool> failed{false};
};

ControlBridge::ControlBridge(ControlRuntime& runtime, BridgeHooks hooks)
    : impl_(std::make_shared<Impl>(runtime, hooks)) {}

BridgeSubmitStatus ControlBridge::submit(
    std::span<const std::byte> envelope,
    std::span<const std::byte> sidecar,
    std::optional<std::chrono::steady_clock::time_point> caller_deadline)
    noexcept {
  const auto submitted_at = std::chrono::steady_clock::now();
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
  selected->submitted_at = submitted_at;
  selected->caller_deadline = caller_deadline;
  selected->publication.store(
      PublicationState::open, std::memory_order_release);
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

BridgeCancelStatus ControlBridge::cancel(
    std::string_view request_id) noexcept {
  try {
    if (!valid_request_id(Json(request_id))) {
      return BridgeCancelStatus::not_found;
    }
  } catch (...) {
    return BridgeCancelStatus::not_found;
  }
  std::lock_guard lock(impl_->request_id_mutex);
  for (auto& request : impl_->requests) {
    if (request.state.load(std::memory_order_acquire) == RequestState::free) {
      continue;
    }
    bool matches = request.has_request_id && request.request_id == request_id;
    if (!matches && !request.has_request_id) {
      try {
        const auto* first = reinterpret_cast<const char*>(
            request.envelope.data());
        const std::string_view bytes(first, request.envelope_size);
        const auto parsed = foundation::valid_utf8(bytes)
                                ? foundation::parse_bounded_json(bytes)
                                : std::nullopt;
        matches = parsed.has_value() && parsed->is_object() &&
                  parsed->contains("request_id") &&
                  parsed->at("request_id").is_string() &&
                  parsed->at("request_id").get_ref<const std::string&>() ==
                      request_id;
      } catch (...) {
        matches = false;
      }
    }
    if (!matches) {
      continue;
    }
    auto expected = PublicationState::open;
    if (request.publication.compare_exchange_strong(
            expected,
            PublicationState::cancelled,
            std::memory_order_acq_rel,
            std::memory_order_acquire) ||
        expected == PublicationState::cancelled) {
      impl_->mark_publication(request, PublicationState::cancelled);
      request.publication.notify_all();
      impl_->record_deadline_cancel(
          request_id, BridgeCancelStatus::cancelled);
      return BridgeCancelStatus::cancelled;
    }
    impl_->record_deadline_cancel(
        request_id, BridgeCancelStatus::publish_claimed);
    return BridgeCancelStatus::publish_claimed;
  }
  impl_->record_deadline_cancel(request_id, BridgeCancelStatus::not_found);
  return BridgeCancelStatus::not_found;
}

bool ControlBridge::configure_deadline_proof(
    std::string_view request_id,
    std::uint8_t gate,
    bool force_publication_error) noexcept {
  try {
    if (!valid_request_id(Json(request_id)) || gate < 1 || gate > 3) {
      return false;
    }
    impl_->deadline_proof.gate.store(0, std::memory_order_release);
    {
      std::lock_guard lock(impl_->deadline_proof.request_id_mutex);
      impl_->deadline_proof.request_id = request_id;
    }
    impl_->deadline_proof.force_publication_error.store(
        force_publication_error, std::memory_order_release);
    impl_->deadline_proof.released.store(false, std::memory_order_release);
    impl_->deadline_proof.entered_facade.store(false, std::memory_order_release);
    impl_->deadline_proof.claim_attempted.store(false, std::memory_order_release);
    impl_->deadline_proof.claim_started_open.store(
        false, std::memory_order_release);
    impl_->deadline_proof.publication.store(
        PublicationState::open, std::memory_order_release);
    impl_->deadline_proof.cancel_observation.store(
        0, std::memory_order_release);
    impl_->deadline_proof.cancel_calls.store(0, std::memory_order_release);
    impl_->deadline_proof.gate.store(gate, std::memory_order_release);
    return true;
  } catch (...) {
    return false;
  }
}

bool ControlBridge::release_deadline_proof() noexcept {
  if (impl_->deadline_proof.gate.load(std::memory_order_acquire) == 0) {
    return false;
  }
  impl_->deadline_proof.released.store(true, std::memory_order_release);
  impl_->deadline_proof.released.notify_all();
  return true;
}

int ControlBridge::deadline_proof_state(
    std::string_view request_id) const noexcept {
  try {
    {
      std::lock_guard lock(impl_->deadline_proof.request_id_mutex);
      if (impl_->deadline_proof.request_id != request_id) {
        return -1;
      }
    }
    auto state = static_cast<int>(
        impl_->deadline_proof.publication.load(std::memory_order_acquire));
    if (impl_->deadline_proof.entered_facade.load(std::memory_order_acquire)) {
      state |= 1 << 8;
    }
    if (impl_->deadline_proof.claim_attempted.load(std::memory_order_acquire)) {
      state |= 1 << 9;
    }
    if (impl_->deadline_proof.claim_started_open.load(
            std::memory_order_acquire)) {
      state |= 1 << 10;
    }
    state |= static_cast<int>(
                 impl_->deadline_proof.gate.load(std::memory_order_acquire))
             << 12;
    state |= static_cast<int>(
                 impl_->deadline_proof.cancel_observation.load(
                     std::memory_order_acquire))
             << 16;
    state |= static_cast<int>(
                 impl_->deadline_proof.cancel_calls.load(
                     std::memory_order_acquire))
             << 20;
    return state;
  } catch (...) {
    return -1;
  }
}

bool ControlBridge::terminal_release_ready() const noexcept {
  for (const auto& request : impl_->requests) {
    if (request.state.load(std::memory_order_acquire) ==
        RequestState::processing) {
      return false;
    }
  }
  return true;
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
    impl_->request_realtime_service();
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
  impl_->request_realtime_service();
  return BridgePollStatus::message;
}

bool ControlBridge::failed() const noexcept {
  return impl_->failed.load(std::memory_order_acquire);
}

}  // namespace lmdj::web_runtime::detail

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
using lmdj::web_runtime::ControlRuntime;
using lmdj::web_runtime::ManifestExpectation;
using lmdj::web_runtime::ManifestGate;
using lmdj::web_runtime::ManifestGateStatus;
using lmdj::web_runtime::detail::BridgeHooks;
using lmdj::web_runtime::detail::BridgePollStatus;
using lmdj::web_runtime::detail::ControlBridge;
using lmdj::web_runtime::detail::ControlRuntimeAudioAccess;
using lmdj::web_runtime::detail::AudioQuiescenceCoordinator;

em_proxying_queue* web_proxy_queue = nullptr;
pthread_t web_control_thread{};
ManifestGate web_manifest_gate;
constexpr std::array<ManifestExpectation::ComponentIdentity, 2>
    web_allowed_hosts{{
        {LMDJ_WEB_CREATOR_DISTRIBUTION_CONTRACT,
         LMDJ_WEB_CREATOR_HOST_ID,
         LMDJ_WEB_CREATOR_HOST_VERSION},
        {LMDJ_WEB_DIAGNOSTIC_DISTRIBUTION_CONTRACT,
         LMDJ_WEB_DIAGNOSTIC_HOST_ID,
         LMDJ_WEB_DIAGNOSTIC_HOST_VERSION},
    }};
std::unique_ptr<ControlRuntime> web_runtime;
std::unique_ptr<ControlBridge> web_bridge_owner;
std::atomic<ControlBridge*> web_bridge{nullptr};
std::array<char, 36> web_terminal_token{};
enum class TerminalReleaseState : std::uint8_t {
  unset,
  writing,
  ready,
  authorized,
  completed_not_released,
  completed_released,
  consumed,
};
std::atomic<TerminalReleaseState> web_terminal_release_state{
    TerminalReleaseState::unset};
std::atomic<bool> web_manifest_terminal_failure{false};
std::atomic<bool> web_manifest_cleanup_reserved{false};
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
std::array<char, lmdj::web_runtime::detail::kBridgeMaximumEnvelopeBytes + 1>
    diagnostic_poll_buffer{};

struct QuiescenceTimeoutDiagnostic {
  std::atomic<std::uint32_t> state{0};
  std::atomic<std::uint32_t> timeout_ms{0};
  std::string serialized_result;
};

QuiescenceTimeoutDiagnostic quiescence_timeout_diagnostic;
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

void fail_manifest_on_control(void*) noexcept {
  if (web_runtime != nullptr) {
    web_runtime->engine().stop();
    web_runtime->fail_and_seal("manifest_protocol_mismatch");
  }
}

void terminal_manifest_failure() noexcept {
  web_manifest_terminal_failure.store(true, std::memory_order_release);
  bool expected = false;
  if (!web_manifest_cleanup_reserved.compare_exchange_strong(
          expected,
          true,
          std::memory_order_acq_rel,
          std::memory_order_acquire) ||
      web_runtime == nullptr) {
    return;
  }
  if (on_control(nullptr)) {
    fail_manifest_on_control(nullptr);
    return;
  }
  if (web_proxy_queue != nullptr) {
    static_cast<void>(emscripten_proxy_async(
        web_proxy_queue,
        web_control_thread,
        &fail_manifest_on_control,
        nullptr));
  }
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
void run_quiescence_timeout_on_control(void*) noexcept {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr) {
    quiescence_timeout_diagnostic.serialized_result =
        R"({"completed":false,"reason":"adapter_unavailable"})";
    quiescence_timeout_diagnostic.state.store(2, std::memory_order_release);
    return;
  }
  const auto timeout_ms =
      quiescence_timeout_diagnostic.timeout_ms.load(std::memory_order_acquire);
  const auto started_at = std::chrono::steady_clock::now();
  const auto result = adapter->await_quiescent(timeout_ms);
  const auto elapsed_ms = std::chrono::duration<double, std::milli>(
                              std::chrono::steady_clock::now() - started_at)
                              .count();
  nlohmann::json serialized{
      {"completed", true},
      {"elapsed_ms", elapsed_ms},
      {"has_value", result.has_value()},
  };
  if (!result.has_value()) {
    serialized["error"] = {
        {"code", lmdj::foundation::error_code_name(result.error().code)},
        {"message", result.error().message},
    };
  }
  quiescence_timeout_diagnostic.serialized_result = serialized.dump();
  quiescence_timeout_diagnostic.state.store(2, std::memory_order_release);
}

void fail_processor_error_on_control(void*) noexcept {
  if (web_runtime != nullptr) {
    auto* adapter = web_audio.load(std::memory_order_acquire);
    if (adapter != nullptr) {
      static_cast<void>(adapter->await_quiescent(1'000));
    }
    web_runtime->engine().stop();
    web_runtime->fail_and_seal("processor_error");
    web_audio_control_failure_state.store(
        AudioFailureCommitState::committed,
        std::memory_order_release);
    return;
  }
  web_audio_control_failure_state.store(
      AudioFailureCommitState::idle,
      std::memory_order_release);
}

void write_conformance_outcome_on_control(void* context) noexcept {
  std::unique_ptr<ConformanceOutcomeWriterRequest> request{
      static_cast<ConformanceOutcomeWriterRequest*>(context)};
  std::uint32_t expected = 0;
  if (!conformance_outcome_mirror.state.compare_exchange_strong(
          expected,
          1,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    conformance_outcome_mirror_writer_pending.store(
        false, std::memory_order_release);
    return;
  }
  conformance_outcome_mirror.count = 1;
  conformance_outcome_mirror.events[0] = RuntimeTriggerOutcomeEvent{
      request->sequence,
      static_cast<lmdj::audio::RuntimeTriggerOutcome>(request->outcome),
      static_cast<std::uint64_t>(request->runtime_frame),
  };

  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds{5};
  while (!conformance_outcome_mirror_writer_release.load(
             std::memory_order_acquire) &&
         std::chrono::steady_clock::now() < deadline) {
    std::this_thread::yield();
  }
  if (conformance_outcome_mirror_writer_release.load(
          std::memory_order_acquire)) {
    conformance_outcome_mirror.state.store(2, std::memory_order_release);
  } else {
    conformance_outcome_mirror.count = 0;
    conformance_outcome_mirror_writer_timed_out.store(
        true, std::memory_order_release);
    conformance_outcome_mirror.state.store(0, std::memory_order_release);
  }
  conformance_outcome_mirror_writer_pending.store(
      false, std::memory_order_release);
}

void drain_outcomes_on_control(void*) noexcept {
  if (web_runtime == nullptr) {
    outcome_diagnostic.count = 0;
    outcome_diagnostic.state.store(3, std::memory_order_release);
    return;
  }
  const auto mirrored = consume_conformance_outcome_mirror(
      outcome_diagnostic.events, outcome_diagnostic.count);
  if (mirrored == ConformanceOutcomeMirrorRead::consumed) {
    outcome_diagnostic.state.store(2, std::memory_order_release);
    return;
  }
  if (mirrored == ConformanceOutcomeMirrorRead::writing) {
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

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_initialize_manifest(
    const std::byte* canonical_bytes,
    std::size_t canonical_size,
    const char* expected_sha256,
    std::size_t expected_sha256_size) {
  if ((canonical_bytes == nullptr && canonical_size != 0) ||
      (expected_sha256 == nullptr && expected_sha256_size != 0)) {
    terminal_manifest_failure();
    return -1;
  }
  const auto status = web_manifest_gate.initialize(
      std::span<const std::byte>(canonical_bytes, canonical_size),
      std::string_view(expected_sha256, expected_sha256_size),
      ManifestExpectation{
          LMDJ_WEB_PRODUCT_BUILD,
          LMDJ_WEB_PLATFORM_VERSION,
          web_allowed_hosts,
          1,
      });
  if (status != ManifestGateStatus::accepted) {
    terminal_manifest_failure();
    return -1;
  }
  return 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_submit(
    const std::byte* envelope,
    std::size_t envelope_size,
    const std::byte* sidecar,
    std::size_t sidecar_size,
    double caller_deadline_at_ms) {
  if (web_manifest_terminal_failure.load(std::memory_order_acquire)) {
    return 1;
  }
  if ((envelope == nullptr && envelope_size != 0) ||
      (sidecar == nullptr && sidecar_size != 0)) {
    return -1;
  }
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  if (bridge == nullptr || !std::isfinite(caller_deadline_at_ms) ||
      caller_deadline_at_ms < 0.0) {
    return -1;
  }
  const auto native_entry = std::chrono::steady_clock::now();
  const auto remaining_ms =
      std::max(0.0, caller_deadline_at_ms - emscripten_get_now());
  const auto caller_cutoff =
      native_entry +
      std::chrono::duration_cast<std::chrono::steady_clock::duration>(
          std::chrono::duration<double, std::milli>(remaining_ms));
  return static_cast<int>(bridge->submit(
      std::span<const std::byte>(envelope, envelope_size),
      std::span<const std::byte>(sidecar, sidecar_size),
      caller_cutoff));
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_cancel_request(
    const char* request_id,
    std::size_t request_id_size) {
  if (request_id == nullptr || request_id_size != 36) {
    return static_cast<int>(
        lmdj::web_runtime::detail::BridgeCancelStatus::not_found);
  }
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  if (bridge == nullptr) {
    return static_cast<int>(
        lmdj::web_runtime::detail::BridgeCancelStatus::not_found);
  }
  return static_cast<int>(bridge->cancel(
      std::string_view(request_id, request_id_size)));
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_deadline_proof_configure(
    const char* request_id,
    std::size_t request_id_size,
    std::uint8_t gate,
    int force_publication_error) {
  if (request_id == nullptr || request_id_size != 36) {
    return 0;
  }
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  return bridge != nullptr && bridge->configure_deadline_proof(
                                  std::string_view(request_id, request_id_size),
                                  gate,
                                  force_publication_error != 0)
             ? 1
             : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_deadline_proof_release() {
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  return bridge != nullptr && bridge->release_deadline_proof() ? 1 : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_deadline_proof_state(
    const char* request_id,
    std::size_t request_id_size) {
  if (request_id == nullptr || request_id_size != 36) {
    return -1;
  }
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  return bridge == nullptr
             ? -1
             : bridge->deadline_proof_state(
                   std::string_view(request_id, request_id_size));
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_set_terminal_token(
    const char* token,
    std::size_t token_size) {
  if (token == nullptr || token_size != web_terminal_token.size()) {
    return -1;
  }
  auto expected = TerminalReleaseState::unset;
  if (web_terminal_release_state.compare_exchange_strong(
          expected,
          TerminalReleaseState::writing,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    std::copy_n(token, token_size, web_terminal_token.begin());
    web_terminal_release_state.store(
        TerminalReleaseState::ready, std::memory_order_release);
    return 0;
  }
  while (expected == TerminalReleaseState::writing) {
    expected = web_terminal_release_state.load(std::memory_order_acquire);
  }
  return expected == TerminalReleaseState::ready &&
                 std::equal(
                     web_terminal_token.begin(),
                     web_terminal_token.end(),
                     token)
             ? 0
             : -1;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_authorize_terminal_release(
    const char* token,
    std::size_t token_size) {
  if (!on_control(nullptr) || token == nullptr ||
      token_size != web_terminal_token.size()) {
    return 0;
  }
  const auto state =
      web_terminal_release_state.load(std::memory_order_acquire);
  if (state != TerminalReleaseState::ready) return 0;
  if (!std::equal(
          web_terminal_token.begin(), web_terminal_token.end(), token)) {
    return 0;
  }
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  if (bridge != nullptr && !bridge->terminal_release_ready()) return 2;
  auto expected = TerminalReleaseState::ready;
  return web_terminal_release_state.compare_exchange_strong(
             expected,
             TerminalReleaseState::authorized,
             std::memory_order_acq_rel,
             std::memory_order_acquire)
             ? 1
             : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_complete_terminal_release(
    const char* token,
    std::size_t token_size,
    int released) {
  if (!on_control(nullptr) || token == nullptr ||
      token_size != web_terminal_token.size() ||
      (released != 0 && released != 1) ||
      web_terminal_release_state.load(std::memory_order_acquire) !=
          TerminalReleaseState::authorized ||
      !std::equal(
          web_terminal_token.begin(), web_terminal_token.end(), token)) {
    return 0;
  }
  auto expected = TerminalReleaseState::authorized;
  return web_terminal_release_state.compare_exchange_strong(
             expected,
             released == 1
                 ? TerminalReleaseState::completed_released
                 : TerminalReleaseState::completed_not_released,
             std::memory_order_acq_rel,
             std::memory_order_acquire)
             ? 1
             : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_consume_terminal_release(
    const char* token,
    std::size_t token_size) {
  if (!emscripten_is_main_browser_thread() || token == nullptr ||
      token_size != web_terminal_token.size()) {
    return -1;
  }
  auto expected =
      web_terminal_release_state.load(std::memory_order_acquire);
  if (expected != TerminalReleaseState::completed_not_released &&
      expected != TerminalReleaseState::completed_released) {
    return -1;
  }
  if (!std::equal(
          web_terminal_token.begin(), web_terminal_token.end(), token)) {
    return -1;
  }
  const auto released = expected == TerminalReleaseState::completed_released;
  return web_terminal_release_state.compare_exchange_strong(
             expected,
             TerminalReleaseState::consumed,
             std::memory_order_acq_rel,
             std::memory_order_acquire)
             ? (released ? 1 : 0)
             : -1;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_poll(
    std::byte* output,
    std::size_t output_size,
    std::size_t* required) {
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  if (web_manifest_terminal_failure.load(std::memory_order_acquire)) {
    return static_cast<int>(BridgePollStatus::output_too_small);
  }
  if (bridge == nullptr || required == nullptr ||
      (output == nullptr && output_size != 0)) {
    return -1;
  }
  return static_cast<int>(bridge->poll(
      std::span<std::byte>(output, output_size), *required));
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_host_failed() {
  if (web_manifest_terminal_failure.load(std::memory_order_acquire)) {
    return 1;
  }
  auto* bridge = web_bridge.load(std::memory_order_acquire);
  return bridge != nullptr && bridge->failed() ? 1 : 0;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_start(
    std::int32_t audio_context_handle) {
  if (!emscripten_is_main_browser_thread()) {
    return -1;
  }
  if (web_manifest_terminal_failure.load(std::memory_order_acquire)) {
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

EMSCRIPTEN_KEEPALIVE std::int32_t lmdj_web_audio_gate_state() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter == nullptr
             ? static_cast<std::int32_t>(RealtimeAudioWorkletGate::terminal)
             : static_cast<std::int32_t>(adapter->gate_state());
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_in_flight() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  return adapter != nullptr && adapter->callback_in_flight() ? 1 : 0;
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

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_quiescence_timeout(
    std::uint32_t timeout_ms) {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr || web_proxy_queue == nullptr) {
    return 0;
  }
  std::uint32_t expected = 0;
  if (!quiescence_timeout_diagnostic.state.compare_exchange_strong(
          expected,
          1,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    return 0;
  }
  quiescence_timeout_diagnostic.timeout_ms.store(
      timeout_ms, std::memory_order_release);
  if (!adapter->mark_callback_in_flight_for_conformance() ||
      emscripten_proxy_async(
          web_proxy_queue,
          web_control_thread,
          &run_quiescence_timeout_on_control,
          nullptr) == 0) {
    quiescence_timeout_diagnostic.state.store(0, std::memory_order_release);
    return 0;
  }
  return 1;
}

EMSCRIPTEN_KEEPALIVE const char*
lmdj_web_audio_test_quiescence_timeout_result() {
  return quiescence_timeout_diagnostic.state.load(std::memory_order_acquire) ==
                 2
             ? quiescence_timeout_diagnostic.serialized_result.c_str()
             : nullptr;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_processor_error() {
  auto* adapter = web_audio.load(std::memory_order_acquire);
  if (adapter == nullptr || web_proxy_queue == nullptr) {
    return 0;
  }
  auto expected = AudioFailureCommitState::idle;
  if (!web_audio_control_failure_state.compare_exchange_strong(
          expected,
          AudioFailureCommitState::pending,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    return 0;
  }
  adapter->latch_processor_error();
  if (emscripten_proxy_async(
          web_proxy_queue,
          web_control_thread,
          &fail_processor_error_on_control,
          nullptr) != 0) {
    return 1;
  }
  web_audio_control_failure_state.store(
      AudioFailureCommitState::idle,
      std::memory_order_release);
  return 0;
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
  if (consume_conformance_outcome_mirror(
          outcome_diagnostic.events,
          outcome_diagnostic.count) ==
      ConformanceOutcomeMirrorRead::consumed) {
    outcome_diagnostic.state.store(2, std::memory_order_release);
    return 1;
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

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_queue_outcome_mirror_write(
    std::uint32_t sequence,
    std::uint32_t outcome,
    std::uint32_t runtime_frame) {
  if (outcome > 1 || web_proxy_queue == nullptr ||
      conformance_outcome_mirror.state.load(std::memory_order_acquire) != 0) {
    return 0;
  }
  bool expected = false;
  if (!conformance_outcome_mirror_writer_pending.compare_exchange_strong(
          expected,
          true,
          std::memory_order_acq_rel,
          std::memory_order_acquire)) {
    return 0;
  }
  conformance_outcome_mirror_writer_release.store(
      false, std::memory_order_release);
  conformance_outcome_mirror_writer_timed_out.store(
      false, std::memory_order_release);
  auto* request = new (std::nothrow) ConformanceOutcomeWriterRequest{
      sequence, outcome, runtime_frame};
  if (request == nullptr ||
      emscripten_proxy_async(
          web_proxy_queue,
          web_control_thread,
          &write_conformance_outcome_on_control,
          request) == 0) {
    delete request;
    conformance_outcome_mirror_writer_pending.store(
        false, std::memory_order_release);
    return 0;
  }
  return 1;
}

EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_release_outcome_mirror_write() {
  if (!conformance_outcome_mirror_writer_pending.load(
          std::memory_order_acquire)) {
    return 0;
  }
  conformance_outcome_mirror_writer_release.store(
      true, std::memory_order_release);
  return 1;
}

EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_web_audio_test_outcome_mirror_state() {
  return conformance_outcome_mirror.state.load(std::memory_order_acquire);
}

EMSCRIPTEN_KEEPALIVE std::uint32_t
lmdj_web_audio_test_outcome_mirror_writer_timed_out() {
  return conformance_outcome_mirror_writer_timed_out.load(
             std::memory_order_acquire)
             ? 1
             : 0;
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
                    lmdj::web_runtime::detail::BridgePollStatus::message) ||
      required >= diagnostic_poll_buffer.size()) {
    return nullptr;
  }
  diagnostic_poll_buffer[required] = '\0';
  return diagnostic_poll_buffer.data();
}
#endif

}  // extern "C"

int main() {
  if (!web_manifest_gate.begin_runtime()) {
    return 2;
  }
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
