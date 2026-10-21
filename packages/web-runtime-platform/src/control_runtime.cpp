#include <lmdj/web_runtime/control_runtime.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <limits>
#include <map>
#include <optional>
#include <random>
#include <set>
#include <span>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

#include <picosha2.h>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/domain/commands.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/facade/performance_engine_adapter.hpp>
#include <lmdj/facade/pattern_transport_controller.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/json.hpp>

#include "testing_hooks.hpp"
#include "recording_metadata_queries.hpp"

namespace lmdj::web_runtime {
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
namespace testing {
namespace {

std::atomic<CancelPendingSwitchHook*> cancel_pending_switch_hook{nullptr};
std::atomic<SequenceSwitchPublicationHook*> sequence_switch_publication_hook{
    nullptr};

}  // namespace

void set_cancel_pending_switch_hook(CancelPendingSwitchHook* hook) noexcept {
  cancel_pending_switch_hook.store(hook, std::memory_order_release);
}

void invoke_cancel_pending_switch_hook() noexcept {
  auto* hook =
      cancel_pending_switch_hook.exchange(nullptr, std::memory_order_acq_rel);
  if (hook != nullptr && hook->invoke != nullptr) {
    hook->invoke(hook->context);
  }
}

void set_sequence_switch_publication_hook(
    SequenceSwitchPublicationHook* hook) noexcept {
  sequence_switch_publication_hook.store(hook, std::memory_order_release);
}

void invoke_sequence_switch_publication_hook() noexcept {
  auto* hook = sequence_switch_publication_hook.exchange(
      nullptr, std::memory_order_acq_rel);
  if (hook != nullptr && hook->invoke != nullptr) {
    hook->invoke(hook->context);
  }
}

}  // namespace testing
#endif
namespace {

using Json = nlohmann::json;
using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint64_t kMaximumSafeInteger = 9'007'199'254'740'991ULL;

std::string generated_uuid() {
  std::array<std::uint8_t, 16> bytes{};
  std::random_device source;
  for (auto& byte : bytes) {
    byte = static_cast<std::uint8_t>(source());
  }
  bytes[6] = static_cast<std::uint8_t>((bytes[6] & 0x0fU) | 0x40U);
  bytes[8] = static_cast<std::uint8_t>((bytes[8] & 0x3fU) | 0x80U);
  constexpr char digits[] = "0123456789abcdef";
  std::string value;
  value.reserve(36);
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    if (index == 4 || index == 6 || index == 8 || index == 10) {
      value.push_back('-');
    }
    value.push_back(digits[bytes[index] >> 4U]);
    value.push_back(digits[bytes[index] & 0x0fU]);
  }
  return value;
}

std::chrono::milliseconds operation_deadline(std::string_view operation) {
  if (operation == "host.close") {
    return std::chrono::seconds(10);
  }
  if (operation.starts_with("pattern.transport.count-in.") ||
      operation.starts_with("pattern.transport.input.") ||
      operation == "host.status" || operation == "audio.activate" ||
      operation == "audio.suspend" || operation == "trigger" ||
      operation == "sequence.record.event" ||
      operation == "sequence.record.status" ||
      operation == "sequence.recovery.list" ||
      operation == "performance.record.event" ||
      operation == "performance.fx.gesture" ||
      operation == "performance.live.control" ||
      operation == "performance.live.status" ||
      operation == "performance.record.launch-request" ||
      operation == "performance.record.status" ||
      operation == "performance.recovery.list" ||
      operation == "performance.replay.status" ||
      operation == "sample.preview.set" ||
      operation == "sample.preview.clear" || operation == "sample.stop") {
    return std::chrono::seconds(1);
  }
  return std::chrono::seconds(30);
}

class ProtocolFailure final : public std::runtime_error {
 public:
  ProtocolFailure() : std::runtime_error("invalid Host protocol request") {}
};

[[noreturn]] void protocol_failure() { throw ProtocolFailure{}; }

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

void require(bool condition) {
  if (!condition) {
    protocol_failure();
  }
}

const std::string& string_field(const Json& value, std::string_view key) {
  const auto& field = value.at(std::string(key));
  require(field.is_string());
  return field.get_ref<const std::string&>();
}

std::uint64_t nonzero_decimal_field(
    const Json& value, std::string_view key,
    std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max()) {
  const auto& text = string_field(value, key);
  require(!text.empty() && text.front() >= '1' && text.front() <= '9');
  std::uint64_t result = 0;
  for (const auto character : text) {
    require(character >= '0' && character <= '9');
    const auto digit = static_cast<std::uint64_t>(character - '0');
    require(result <= maximum / 10 &&
        (result != maximum / 10 || digit <= maximum % 10));
    result = result * 10 + digit;
  }
  return result;
}

std::uint64_t unsigned_field(
    const Json& value,
    std::string_view key,
    std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max()) {
  const auto& field = value.at(std::string(key));
  std::uint64_t result = 0;
  if (field.is_number_unsigned()) {
    result = field.get<std::uint64_t>();
  } else if (field.is_number_integer()) {
    const auto signed_result = field.get<std::int64_t>();
    require(signed_result >= 0);
    result = static_cast<std::uint64_t>(signed_result);
  } else {
    protocol_failure();
  }
  require(result <= maximum);
  return result;
}

bool bool_field(const Json& value, std::string_view key) {
  const auto& field = value.at(std::string(key));
  require(field.is_boolean());
  return field.get<bool>();
}

std::int32_t signed_field(
    const Json& value,
    std::string_view key,
    std::int32_t minimum,
    std::int32_t maximum) {
  const auto& field = value.at(std::string(key));
  require(field.is_number_integer());
  // An unsigned number above INT64_MAX would wrap in get<std::int64_t>() and
  // could land back in range, so it is refused by its own magnitude first.
  require(!field.is_number_unsigned() ||
          field.get<std::uint64_t>() <=
              static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()));
  const auto result = field.get<std::int64_t>();
  require(result >= minimum && result <= maximum);
  return static_cast<std::int32_t>(result);
}

std::string uuid_field(const Json& value, std::string_view key) {
  const auto result = string_field(value, key);
  require(domain::is_valid_uuid(result));
  return result;
}

domain::PadSlotId slot_value(const Json& value) {
  require(exact_keys(value, {"bank", "pad"}));
  return domain::PadSlotId{
      static_cast<std::uint8_t>(unsigned_field(value, "bank", 3)),
      static_cast<std::uint8_t>(unsigned_field(value, "pad", 15)),
  };
}

std::uint8_t flatten_slot(domain::PadSlotId slot) noexcept {
  return static_cast<std::uint8_t>(slot.bank * 16U + slot.pad);
}

domain::TriggerMode trigger_mode_value(const Json& value) {
  require(value.is_string());
  const auto mode = value.get<std::string_view>();
  if (mode == "one_shot") {
    return domain::TriggerMode::one_shot;
  }
  if (mode == "gate") {
    return domain::TriggerMode::gate;
  }
  if (mode == "loop_gate") {
    return domain::TriggerMode::loop_gate;
  }
  if (mode == "loop_toggle") {
    return domain::TriggerMode::loop_toggle;
  }
  protocol_failure();
}

// An EQ shelf band (lmdj.project.v5 5.2.0): exact keys, a shelf or cut kind,
// and the band's frequency range.
domain::PadEqShelf eq_shelf_value(
    const Json& value, std::int32_t minimum_hz, std::int32_t maximum_hz) {
  require(exact_keys(value, {"kind", "freq_hz", "gain_millidb"}));
  const auto& kind = string_field(value, "kind");
  require(kind == "shelf" || kind == "cut");
  return domain::PadEqShelf{
      kind == "cut" ? domain::EqBandKind::cut : domain::EqBandKind::shelf,
      signed_field(value, "freq_hz", minimum_hz, maximum_hz),
      signed_field(value, "gain_millidb", domain::kPadEqGainMillidbMin,
                   domain::kPadEqGainMillidbMax),
  };
}

// The three optional EQ bands; an absent band is bypassed.
domain::PadEq eq_value(const Json& value) {
  require(value.is_object());
  for (const auto& [key, band] : value.items()) {
    (void)band;
    require(key == "low" || key == "mid" || key == "high");
  }
  domain::PadEq eq;
  if (value.contains("low")) {
    eq.low = eq_shelf_value(value.at("low"), domain::kPadEqLowFreqHzMin,
                            domain::kPadEqLowFreqHzMax);
  }
  if (value.contains("mid")) {
    const auto& mid = value.at("mid");
    require(exact_keys(mid, {"freq_hz", "gain_millidb", "q_milli"}));
    eq.mid = domain::PadEqBell{
        signed_field(mid, "freq_hz", domain::kPadEqMidFreqHzMin,
                     domain::kPadEqMidFreqHzMax),
        signed_field(mid, "gain_millidb", domain::kPadEqGainMillidbMin,
                     domain::kPadEqGainMillidbMax),
        signed_field(mid, "q_milli", domain::kPadEqMidQMilliMin,
                     domain::kPadEqMidQMilliMax),
    };
  }
  if (value.contains("high")) {
    eq.high = eq_shelf_value(value.at("high"), domain::kPadEqHighFreqHzMin,
                             domain::kPadEqHighFreqHzMax);
  }
  return eq;
}

// The five 5.0.0 playback keys are required; a lmdj.project.v5 5.1.0 or 5.2.0
// parity key may be omitted, which means its default; an unknown key is a
// protocol failure, as before.
domain::PadPlayback playback_value(const Json& value) {
  static constexpr std::array<std::string_view, 5> base{
      "trim_start_frame", "trim_end_frame", "trigger_mode", "gain_millidb",
      "muted"};
  static constexpr std::array<std::string_view, 10> parity{
      "reverse", "pitch_cents", "pan", "loop_mode", "loop_start_frame",
      "loop_crossfade_frames", "attack_ms", "release_ms", "tone", "eq"};
  require(value.is_object());
  for (const auto key : base) {
    require(value.contains(std::string(key)));
  }
  for (const auto& [key, field] : value.items()) {
    (void)field;
    require(std::find(base.begin(), base.end(), key) != base.end() ||
            std::find(parity.begin(), parity.end(), key) != parity.end());
  }
  const auto start = unsigned_field(value, "trim_start_frame");
  std::optional<std::uint64_t> end;
  if (!value.at("trim_end_frame").is_null()) {
    end = unsigned_field(value, "trim_end_frame");
    require(*end > start);
  }
  domain::PadPlayback playback{
      start,
      end,
      trigger_mode_value(value.at("trigger_mode")),
      signed_field(value, "gain_millidb", -60'000, 6'000),
      bool_field(value, "muted"),
  };
  if (value.contains("reverse")) {
    playback.reverse = bool_field(value, "reverse");
  }
  if (value.contains("pitch_cents")) {
    playback.pitch_cents = signed_field(
        value, "pitch_cents", domain::kPadPitchCentsMin,
        domain::kPadPitchCentsMax);
  }
  if (value.contains("pan")) {
    playback.pan =
        signed_field(value, "pan", domain::kPadPanMin, domain::kPadPanMax);
  }
  if (value.contains("loop_mode")) {
    const auto& mode = string_field(value, "loop_mode");
    require(mode == "forward" || mode == "ping_pong");
    playback.loop_mode = mode == "ping_pong" ? domain::LoopMode::ping_pong
                                             : domain::LoopMode::forward;
  }
  if (value.contains("loop_start_frame") &&
      !value.at("loop_start_frame").is_null()) {
    playback.loop_start_frame = unsigned_field(value, "loop_start_frame");
  }
  if (value.contains("loop_crossfade_frames")) {
    playback.loop_crossfade_frames =
        unsigned_field(value, "loop_crossfade_frames");
  }
  if (value.contains("attack_ms")) {
    playback.attack_ms =
        signed_field(value, "attack_ms", 0, domain::kPadAttackMsMax);
  }
  if (value.contains("release_ms")) {
    playback.release_ms =
        signed_field(value, "release_ms", 0, domain::kPadReleaseMsMax);
  }
  if (value.contains("tone")) {
    playback.tone = signed_field(value, "tone", domain::kPadToneMin,
                                 domain::kPadToneMax);
  }
  if (value.contains("eq")) {
    playback.eq = eq_value(value.at("eq"));
  }
  return playback;
}

domain::Pattern pattern_value(const Json& value) {
  require(exact_keys(value, {"pattern_id", "bars", "events"}));
  const auto id = uuid_field(value, "pattern_id");
  const auto bars = unsigned_field(value, "bars", 8);
  require(bars == 1 || bars == 2 || bars == 4 || bars == 8);
  const auto& events = value.at("events");
  require(events.is_array());
  std::vector<domain::PatternEvent> parsed;
  parsed.reserve(events.size());
  for (const auto& event : events) {
    require(exact_keys(
        event, {"slot", "onset_tick", "duration_tick", "velocity"}));
    const auto loop_length = domain::pattern_length_ticks(
        static_cast<std::uint8_t>(bars));
    const auto onset = unsigned_field(event, "onset_tick", loop_length - 1U);
    const auto duration = unsigned_field(event, "duration_tick", loop_length);
    const auto velocity = unsigned_field(event, "velocity", 127);
    require(velocity != 0 && duration != 0 && duration <= loop_length - onset);
    parsed.push_back(domain::PatternEvent{
        slot_value(event.at("slot")),
        static_cast<std::uint32_t>(onset),
        static_cast<std::uint32_t>(duration),
        static_cast<std::uint8_t>(velocity),
    });
  }
  return domain::Pattern{
      foundation::PatternId{id},
      static_cast<std::uint8_t>(bars),
      std::move(parsed),
  };
}

std::uint64_t safe_unsigned_field(
    const Json& value,
    std::string_view key,
    std::uint64_t maximum = kMaximumSafeInteger) {
  return unsigned_field(value, key, maximum);
}

void validate_performance_name(const Json& value, std::string_view key) {
  const auto& name = string_field(value, key);
  require(foundation::valid_utf8(name));
  const auto code_points = std::count_if(
      name.begin(), name.end(), [](unsigned char byte) {
        return (byte & 0xc0U) != 0x80U;
      });
  require(code_points > 0 && code_points <= 64);
}

void validate_performance_artifact(const Json& value) {
  require(exact_keys(value, {"sha256", "media_type", "byte_length"}));
  const auto& sha256 = string_field(value, "sha256");
  require(
      sha256.size() == 64U &&
      std::all_of(sha256.begin(), sha256.end(), [](char character) {
        return (character >= '0' && character <= '9') ||
            (character >= 'a' && character <= 'f');
      }));
  require(string_field(value, "media_type") == "audio/wav");
  (void)safe_unsigned_field(value, "byte_length");
}

constexpr std::array<std::string_view, 8> kPerformanceFxNames{
    "filter", "delay", "reverb", "stutter",
    "gate", "reverse", "crush", "cutter"};

void validate_performance_gesture(const Json& event) {
  require(event.is_object() && event.contains("kind"));
  const auto& kind = string_field(event, "kind");
  if (kind == "pad_press") {
    require(exact_keys(
        event, {"kind", "gesture_id", "slot", "velocity"}));
    (void)uuid_field(event, "gesture_id");
    (void)safe_unsigned_field(event, "slot", 63U);
    const auto velocity = safe_unsigned_field(event, "velocity", 127U);
    require(velocity != 0U);
    return;
  }
  if (kind == "pad_release") {
    require(exact_keys(event, {"kind", "gesture_id", "slot"}));
    (void)uuid_field(event, "gesture_id");
    (void)safe_unsigned_field(event, "slot", 63U);
    return;
  }
  if (kind == "fx_engage" || kind == "fx_move") {
    require(exact_keys(
        event, {"kind", "gesture_id", "fx", "value"}));
    (void)uuid_field(event, "gesture_id");
    const auto& effect = string_field(event, "fx");
    require(std::find(kPerformanceFxNames.begin(), kPerformanceFxNames.end(),
                      effect) != kPerformanceFxNames.end());
    (void)safe_unsigned_field(event, "value", 1'000U);
    return;
  }
  if (kind == "fx_release") {
    require(exact_keys(event, {"kind", "gesture_id", "fx"}));
    (void)uuid_field(event, "gesture_id");
    const auto& effect = string_field(event, "fx");
    require(std::find(kPerformanceFxNames.begin(), kPerformanceFxNames.end(),
                      effect) != kPerformanceFxNames.end());
    return;
  }
  require(
      (kind == "hold_on" || kind == "hold_off") &&
      exact_keys(event, {"kind"}));
}

// Session-free live FX gestures (#1674): the same gesture vocabulary as a
// journaled recording event, minus the gesture identity the recording journal
// tracks. Applied to the master bus only; journaled nowhere.
void validate_performance_fx_gesture_event(const Json& event) {
  require(event.is_object() && event.contains("kind"));
  const auto& kind = string_field(event, "kind");
  if (kind == "fx_engage" || kind == "fx_move") {
    require(exact_keys(event, {"kind", "fx", "value"}));
    const auto& effect = string_field(event, "fx");
    require(std::find(kPerformanceFxNames.begin(), kPerformanceFxNames.end(),
                      effect) != kPerformanceFxNames.end());
    (void)safe_unsigned_field(event, "value", 1'000U);
    return;
  }
  if (kind == "fx_release") {
    require(exact_keys(event, {"kind", "fx"}));
    const auto& effect = string_field(event, "fx");
    require(std::find(kPerformanceFxNames.begin(), kPerformanceFxNames.end(),
                      effect) != kPerformanceFxNames.end());
    return;
  }
  require(
      (kind == "hold_on" || kind == "hold_off") &&
      exact_keys(event, {"kind"}));
}

// The Web Host's mirror of the plan's Locked Facade Surface. The three
// Workspace-level operations carry no `project_path`, so unlike a Performance
// operation the Host does not inject the retained Project into them.
void validate_provider_operation_payload(std::string_view operation, const Json& payload) {
  if (operation == "provider.list") {
    require(exact_keys(payload, {}));
  } else if (operation == "provider.select") {
    require(exact_keys(payload, {"capability", "provider_id"}));
  } else if (operation == "provider.permissions.configure") {
    require(exact_keys(payload, {"granted_permissions"}));
  } else if (operation == "attempt.inspect") {
    require(exact_keys(payload, {"attempt_id"}));
  } else {
    require(operation == "provider.run");
    require(exact_keys(payload, {"attempt_id", "capability", "inputs", "parameters",
                                "data_classification", "platform", "region", "required_permissions"}) ||
            exact_keys(payload, {"attempt_id", "capability", "inputs", "parameters",
                                "data_classification", "platform", "region", "required_permissions", "input_owners"}));
    if (payload.contains("input_owners")) {
      require(payload.at("input_owners").is_array());
      for (const auto& owner : payload.at("input_owners")) {
        // Browser callers never supply a filesystem path, even one matching
        // the current Project. Only this retained-session boundary adds it.
        require(exact_keys(owner, {"port", "occurrence", "project_id", "asset_id"}));
        (void)string_field(owner, "port");
        (void)safe_unsigned_field(owner, "occurrence");
        (void)uuid_field(owner, "project_id");
        (void)uuid_field(owner, "asset_id");
      }
    }
  }
}

void validate_candidate_operation_payload(std::string_view operation, const Json& payload) {
  const auto id = [&payload](std::string_view key) {
    const auto value = string_field(payload, key);
    require(!value.empty() && value.size() <= 128 && value != "." && value != ".." &&
      std::all_of(value.begin(), value.end(), [](unsigned char c) {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
      }));
  };
  if (operation == "candidate.audition.stop") { require(exact_keys(payload, {})); return; }
  if (operation == "candidate.job.inspect") {
    require(exact_keys(payload, {"job_id"}));
  } else if (operation == "candidate.job.cancel") {
    require(exact_keys(payload, {"job_id", "attempt_id"})); id("attempt_id");
  } else if (operation == "candidate.set.discard") {
    require(exact_keys(payload, {"job_id", "set_id"})); id("set_id");
  } else {
    if (operation == "candidate.job.run") {
      require(exact_keys(payload, {"job_id", "attempt_id", "project_id", "asset_id", "expected_revision",
        "parameters", "data_classification", "platform", "region", "required_permissions"}));
      id("attempt_id"); id("data_classification"); id("platform"); id("region");
      (void)uuid_field(payload, "asset_id");
      require(payload.at("parameters").is_object() && payload.at("required_permissions").is_array());
      std::set<std::string> permissions;
      for (const auto& permission : payload.at("required_permissions")) {
        require(permission.is_string());
        const auto value = permission.get<std::string>();
        Json wrapper{{"job_id", value}};
        validate_candidate_operation_payload("candidate.job.inspect", wrapper);
        require(permissions.insert(value).second);
      }
    } else if (operation == "candidate.audition") {
      require(exact_keys(payload, {"project_id", "expected_revision", "job_id", "set_id", "candidate_id"}));
      id("set_id"); id("candidate_id");
    } else {
      require(operation == "candidate.adopt" && exact_keys(payload,
        {"project_id", "expected_revision", "command_id", "job_id", "set_id", "selections"}));
      id("set_id"); (void)uuid_field(payload, "command_id");
      const auto& selections = payload.at("selections");
      require(selections.is_array() && !selections.empty() && selections.size() <= 64);
      std::set<std::pair<std::uint64_t, std::uint64_t>> targets;
      for (const auto& selection : selections) {
        require(exact_keys(selection, {"candidate_id", "bank", "pad"}));
        Json wrapper{{"job_id", selection.at("candidate_id")}};
        validate_candidate_operation_payload("candidate.job.inspect", wrapper);
        require(targets.emplace(safe_unsigned_field(selection, "bank", 3),
          safe_unsigned_field(selection, "pad", 15)).second);
      }
    }
    (void)uuid_field(payload, "project_id"); (void)safe_unsigned_field(payload, "expected_revision");
  }
  id("job_id");
}

void validate_soundset_operation_payload(
    std::string_view operation,
    const Json& payload) {
  const auto set_identity = [&payload]() {
    (void)uuid_field(payload, "set_id");
    const auto version = string_field(payload, "version");
    require(!version.empty() && version.size() <= 32);
    const auto manifest = string_field(payload, "manifest_sha256");
    require(
        manifest.size() == 64 &&
        std::all_of(manifest.begin(), manifest.end(), [](char value) {
          return (value >= '0' && value <= '9') ||
                 (value >= 'a' && value <= 'f');
        }));
  };
  if (operation == "soundset.catalog.list" || operation == "soundset.catalog.describe") {
    require(exact_keys(payload, {}));
  } else if (operation == "soundset.slot.acquire" || operation == "soundset.slot.install") {
    if (operation == "soundset.slot.acquire") {
      require(exact_keys(payload, {"set_id", "version", "manifest_sha256", "slot_index"}));
    } else {
      require(exact_keys(payload, {"command_id", "expected_revision", "bank_id", "set_id", "version", "manifest_sha256", "slot_index"}));
      (void)uuid_field(payload, "command_id");
      (void)safe_unsigned_field(payload, "expected_revision");
      (void)safe_unsigned_field(payload, "bank_id", 3U);
    }
    (void)safe_unsigned_field(payload, "slot_index", 15U);
    set_identity();
  } else if (operation == "soundset.audition") {
    // S11-D5's optional `slot_index` is the only field beyond the Set
    // identity: absent auditions the set-level `demo`, present auditions that
    // slot's Artifact.
    require(
        exact_keys(payload, {"set_id", "version", "manifest_sha256"}) ||
        exact_keys(
            payload, {"set_id", "version", "manifest_sha256", "slot_index"}));
    if (payload.contains("slot_index")) {
      (void)safe_unsigned_field(payload, "slot_index", 15U);
    }
    set_identity();
  } else if (operation == "soundset.audition.stop") {
    // Stopping addresses no Set: there is only ever one audition, so naming
    // which one to stop would be a field the Host could get wrong.
    require(exact_keys(payload, {}));
  } else if (operation == "soundset.inspect") {
    require(exact_keys(payload, {"set_id", "version", "manifest_sha256"}));
    set_identity();
  } else if (operation == "soundset.map.preview") {
    require(exact_keys(
        payload, {"bank_id", "set_id", "version", "manifest_sha256"}));
    (void)safe_unsigned_field(payload, "bank_id", 3U);
    set_identity();
  } else if (operation == "soundset.install") {
    require(
        exact_keys(
            payload,
            {"command_id", "expected_revision", "bank_id", "set_id",
             "version", "manifest_sha256"}) ||
        exact_keys(
            payload,
            {"command_id", "expected_revision", "bank_id", "set_id",
             "version", "manifest_sha256", "occupied_pad_policy"}));
    (void)uuid_field(payload, "command_id");
    (void)safe_unsigned_field(payload, "expected_revision");
    (void)safe_unsigned_field(payload, "bank_id", 3U);
    set_identity();
    if (payload.contains("occupied_pad_policy")) {
      const auto policy = string_field(payload, "occupied_pad_policy");
      require(policy == "keep" || policy == "replace");
    }
  } else {
    protocol_failure();
  }
}

// D0/W1: opaque Core sequences are canonical decimal strings — validated as
// text, never converted through a lossy Number/double.
void validate_opaque_sequence(const Json& value, std::string_view key) {
  const auto& text = string_field(value, key);
  require(!text.empty());
  require(text.size() == 1 || text.front() != '0');
  require(std::all_of(text.begin(), text.end(), [](char character) {
    return character >= '0' && character <= '9';
  }));
  // uint64 range without a lossy conversion: compare decimal text.
  require(text.size() < 20U ||
          (text.size() == 20U &&
           text <= "18446744073709551615"));
}

// The closed live-control intent vocabulary (D0/W1), mirrored byte-for-byte
// with the JS registry validator; the native boundary is the real oracle.
void validate_live_control_intent(const Json& intent) {
  require(intent.is_object() && intent.contains("kind"));
  const auto& kind = string_field(intent, "kind");
  if (kind == "filter_parameter") {
    const auto bound = exact_keys(
        intent, {"kind", "phase", "parameter", "value", "gesture_generation"});
    require(bound ||
            exact_keys(intent, {"kind", "phase", "parameter", "value"}));
    if (bound) {
      (void)uuid_field(intent, "gesture_generation");
    }
    const auto& phase = string_field(intent, "phase");
    require(phase == "engage" || phase == "move");
    const auto& parameter = string_field(intent, "parameter");
    if (parameter == "type") {
      const auto& type = string_field(intent, "value");
      require(type == "lp" || type == "hp" || type == "bp");
    } else if (parameter == "cutoff_hz") {
      const auto cutoff = safe_unsigned_field(intent, "value", 20'000U);
      require(cutoff >= 20U);
    } else {
      require(parameter == "resonance_milli");
      (void)safe_unsigned_field(intent, "value", 1'000U);
    }
    return;
  }
  if (kind == "filter_release") {
    require(exact_keys(intent, {"kind", "gesture_generation"}));
    (void)uuid_field(intent, "gesture_generation");
    return;
  }
  if (kind == "fx_parameter") {
    const auto bound = exact_keys(
        intent, {"kind", "phase", "fx", "value", "gesture_generation"});
    require(bound || exact_keys(intent, {"kind", "phase", "fx", "value"}));
    if (bound) {
      (void)uuid_field(intent, "gesture_generation");
    }
    const auto& phase = string_field(intent, "phase");
    require(phase == "engage" || phase == "move");
    const auto& effect = string_field(intent, "fx");
    require(std::find(kPerformanceFxNames.begin(), kPerformanceFxNames.end(),
                      effect) != kPerformanceFxNames.end());
    (void)safe_unsigned_field(intent, "value", 1'000U);
    return;
  }
  if (kind == "fx_release") {
    require(exact_keys(intent, {"kind", "fx", "gesture_generation"}));
    const auto& effect = string_field(intent, "fx");
    require(std::find(kPerformanceFxNames.begin(), kPerformanceFxNames.end(),
                      effect) != kPerformanceFxNames.end());
    (void)uuid_field(intent, "gesture_generation");
    return;
  }
  if (kind == "pad_mute" || kind == "pad_solo") {
    require(exact_keys(intent, {"kind", "slot", "enabled"}));
    (void)safe_unsigned_field(intent, "slot", 63U);
    require(intent.at("enabled").is_boolean());
    return;
  }
  require((kind == "clear_pad_gates" || kind == "hold_on" ||
           kind == "hold_off") &&
          exact_keys(intent, {"kind"}));
}

// The headered recording profile's closed event vocabulary (D0): Pad gestures
// keep their legacy keys; FX moves/releases carry the Core binding pair.
void validate_headered_performance_event(const Json& event) {
  require(event.is_object() && event.contains("kind"));
  const auto& kind = string_field(event, "kind");
  if (kind == "pad_press" || kind == "pad_release") {
    validate_performance_gesture(event);
    return;
  }
  if (kind == "fx_engage") {
    require(exact_keys(event, {"kind", "fx", "value"}));
    const auto& effect = string_field(event, "fx");
    require(std::find(kPerformanceFxNames.begin(), kPerformanceFxNames.end(),
                      effect) != kPerformanceFxNames.end());
    (void)safe_unsigned_field(event, "value", 1'000U);
    return;
  }
  if (kind == "fx_move" || kind == "fx_release") {
    if (kind == "fx_move") {
      require(exact_keys(
          event, {"kind", "fx", "value", "gesture_id", "gesture_generation"}));
      (void)safe_unsigned_field(event, "value", 1'000U);
    } else {
      require(exact_keys(
          event, {"kind", "fx", "gesture_id", "gesture_generation"}));
    }
    const auto& effect = string_field(event, "fx");
    require(std::find(kPerformanceFxNames.begin(), kPerformanceFxNames.end(),
                      effect) != kPerformanceFxNames.end());
    (void)uuid_field(event, "gesture_id");
    (void)uuid_field(event, "gesture_generation");
    return;
  }
  if (kind == "filter_parameter") {
    const auto bound = exact_keys(
        event,
        {"kind", "phase", "parameter", "value", "gesture_id",
         "gesture_generation"});
    require(bound ||
            exact_keys(event, {"kind", "phase", "parameter", "value"}));
    if (bound) {
      (void)uuid_field(event, "gesture_id");
      (void)uuid_field(event, "gesture_generation");
    }
    const auto& phase = string_field(event, "phase");
    require(phase == "engage" || phase == "move");
    const auto& parameter = string_field(event, "parameter");
    if (parameter == "type") {
      const auto& type = string_field(event, "value");
      require(type == "lp" || type == "hp" || type == "bp");
    } else if (parameter == "cutoff_hz") {
      const auto cutoff = safe_unsigned_field(event, "value", 20'000U);
      require(cutoff >= 20U);
    } else {
      require(parameter == "resonance_milli");
      (void)safe_unsigned_field(event, "value", 1'000U);
    }
    return;
  }
  if (kind == "filter_release") {
    require(exact_keys(
        event, {"kind", "gesture_id", "gesture_generation"}));
    (void)uuid_field(event, "gesture_id");
    (void)uuid_field(event, "gesture_generation");
    return;
  }
  if (kind == "pad_mute" || kind == "pad_solo") {
    require(exact_keys(event, {"kind", "slot", "enabled"}));
    (void)safe_unsigned_field(event, "slot", 63U);
    require(event.at("enabled").is_boolean());
    return;
  }
  require((kind == "clear_pad_gates" || kind == "hold_on" ||
           kind == "hold_off") &&
          exact_keys(event, {"kind"}));
}

void validate_performance_operation_payload(
    std::string_view operation,
    const Json& payload) {
  const auto command_identity = [&payload]() {
    (void)uuid_field(payload, "command_id");
    (void)safe_unsigned_field(payload, "expected_revision");
  };
  const auto pattern_slot = [&payload](std::string_view key) {
    (void)safe_unsigned_field(payload, key, 15U);
  };
  if (operation == "pattern.slot.assign") {
    require(exact_keys(
        payload,
        {"command_id", "expected_revision", "pattern_slot", "pattern_id"}));
    command_identity();
    pattern_slot("pattern_slot");
    (void)uuid_field(payload, "pattern_id");
  } else if (operation == "pattern.slot.clear") {
    require(exact_keys(
        payload, {"command_id", "expected_revision", "pattern_slot"}));
    command_identity();
    pattern_slot("pattern_slot");
  } else if (operation == "pattern.slot.move") {
    require(exact_keys(
        payload,
        {"command_id", "expected_revision", "from_slot", "to_slot"}));
    command_identity();
    pattern_slot("from_slot");
    pattern_slot("to_slot");
  } else if (
      operation == "performance.list" ||
      operation == "performance.record.status" ||
      operation == "performance.recovery.list") {
    require(exact_keys(payload, {}));
  } else if (operation == "performance.inspect") {
    require(exact_keys(payload, {"performance_id"}));
    (void)uuid_field(payload, "performance_id");
  } else if (operation == "performance.record.begin") {
    // The headered profile is selected by the extra Core-issued epoch key;
    // the legacy four-key shape is unchanged.
    if (payload.contains("control_epoch")) {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "session_id", "performance_id",
           "control_epoch"}));
      command_identity();
      (void)uuid_field(payload, "session_id");
      (void)uuid_field(payload, "performance_id");
      (void)uuid_field(payload, "control_epoch");
    } else {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "session_id", "performance_id"}));
      command_identity();
      (void)uuid_field(payload, "session_id");
      (void)uuid_field(payload, "performance_id");
    }
  } else if (operation == "performance.live.status") {
    require(exact_keys(payload, {}));
  } else if (operation == "performance.live.control") {
    require(exact_keys(
        payload,
        {"control_epoch", "command_id", "expected_control_sequence",
         "intent"}));
    (void)uuid_field(payload, "control_epoch");
    (void)uuid_field(payload, "command_id");
    validate_opaque_sequence(payload, "expected_control_sequence");
    validate_live_control_intent(payload.at("intent"));
  } else if (operation == "performance.record.event") {
    if (payload.contains("control_epoch") ||
        payload.contains("expected_recording_sequence")) {
      require(exact_keys(
          payload,
          {"session_id", "event_id", "event", "control_epoch",
           "expected_recording_sequence"}));
      (void)uuid_field(payload, "session_id");
      (void)uuid_field(payload, "event_id");
      (void)uuid_field(payload, "control_epoch");
      validate_opaque_sequence(payload, "expected_recording_sequence");
      validate_headered_performance_event(payload.at("event"));
    } else {
      require(exact_keys(payload, {"session_id", "event_id", "event"}));
      (void)uuid_field(payload, "session_id");
      (void)uuid_field(payload, "event_id");
      validate_performance_gesture(payload.at("event"));
    }
  } else if (operation == "performance.record.launch-request") {
    if (payload.contains("control_epoch") ||
        payload.contains("expected_recording_sequence")) {
      require(exact_keys(
          payload,
          {"session_id", "request_id", "pattern_slot", "control_epoch",
           "expected_recording_sequence"}));
      (void)uuid_field(payload, "session_id");
      (void)uuid_field(payload, "request_id");
      (void)uuid_field(payload, "control_epoch");
      validate_opaque_sequence(payload, "expected_recording_sequence");
      pattern_slot("pattern_slot");
    } else {
      require(exact_keys(
          payload, {"session_id", "request_id", "pattern_slot"}));
      (void)uuid_field(payload, "session_id");
      (void)uuid_field(payload, "request_id");
      pattern_slot("pattern_slot");
    }
  } else if (operation == "performance.record.flush") {
    require(exact_keys(payload, {"session_id", "command_id"}));
    (void)uuid_field(payload, "session_id");
    (void)uuid_field(payload, "command_id");
  } else if (
      operation == "performance.record.stop" ||
      operation == "performance.recovery.discard") {
    require(exact_keys(payload, {"session_id", "request_id"}));
    (void)uuid_field(payload, "session_id");
    (void)uuid_field(payload, "request_id");
  } else if (operation == "performance.save") {
    require(exact_keys(
        payload,
        {"command_id", "expected_revision", "performance_id", "name",
         "recording_artifact"}));
    command_identity();
    (void)uuid_field(payload, "performance_id");
    validate_performance_name(payload, "name");
    if (!payload.at("recording_artifact").is_null()) {
      validate_performance_artifact(payload.at("recording_artifact"));
    }
  } else if (
      operation == "performance.discard" ||
      operation == "performance.delete") {
    require(exact_keys(
        payload, {"command_id", "expected_revision", "performance_id"}));
    command_identity();
    (void)uuid_field(payload, "performance_id");
  } else if (operation == "performance.recovery.apply") {
    require(exact_keys(
        payload, {"command_id", "expected_revision", "session_id"}));
    command_identity();
    (void)uuid_field(payload, "session_id");
  } else if (operation == "performance.rename") {
    require(exact_keys(
        payload,
        {"command_id", "expected_revision", "performance_id", "name"}));
    command_identity();
    (void)uuid_field(payload, "performance_id");
    validate_performance_name(payload, "name");
  } else if (operation == "performance.recording.bind") {
    require(exact_keys(
        payload,
        {"command_id", "expected_revision", "performance_id",
         "recording_artifact"}));
    command_identity();
    (void)uuid_field(payload, "performance_id");
    validate_performance_artifact(payload.at("recording_artifact"));
  } else if (operation == "performance.replay.begin") {
    require(exact_keys(payload, {"replay_id", "performance_id"}));
    (void)uuid_field(payload, "replay_id");
    (void)uuid_field(payload, "performance_id");
  } else if (operation == "performance.replay.stop") {
    require(exact_keys(payload, {"replay_id", "request_id"}));
    (void)uuid_field(payload, "replay_id");
    (void)uuid_field(payload, "request_id");
  } else if (operation == "performance.replay.status") {
    require(exact_keys(payload, {"replay_id"}));
    (void)uuid_field(payload, "replay_id");
  } else if (operation == "performance.resample.commit") {
    require(exact_keys(
        payload,
        {"command_id", "expected_revision", "performance_id",
         "source_start_frame", "source_end_frame", "target_slot"}));
    command_identity();
    (void)uuid_field(payload, "performance_id");
    const auto start = safe_unsigned_field(payload, "source_start_frame");
    const auto end = safe_unsigned_field(payload, "source_end_frame");
    require(start < end);
    (void)slot_value(payload.at("target_slot"));
  } else {
    protocol_failure();
  }
}

Json success(Json result) {
  return {{"ok", true}, {"result", std::move(result)}};
}

Json host_error(
    std::string code,
    std::string message,
    Json details = Json::object()) {
  return {
      {"ok", false},
      {"error",
       {
           {"code", std::move(code)},
           {"message", std::move(message)},
           {"details", std::move(details)},
       }},
  };
}

Json protocol_error() {
  return host_error(
      "HOST_PROTOCOL_MISMATCH",
      "host protocol request is invalid");
}

Json state_error(std::string message = "operation is unavailable") {
  return host_error("HOST_STATE_INVALID", std::move(message));
}

Json timeout_error() {
  return host_error("HOST_TIMEOUT", "host request timed out");
}

Json internal_error(Json details = Json::object()) {
  return host_error(
      "INTERNAL_ERROR", "unexpected Web Host failure", std::move(details));
}

Json sanitize_details(const Json& value) {
  static constexpr std::array<std::string_view, 3> revision_fields{
      "actual_revision",
      "expected_revision",
      "captured_revision",
  };
  const auto sensitive_container_key = [](std::string key) {
    std::transform(
        key.begin(), key.end(), key.begin(), [](unsigned char character) {
          return static_cast<char>(std::tolower(character));
        });
    return key.find("detail") != std::string::npos ||
           key.find("path") != std::string::npos ||
           key.find("system") != std::string::npos ||
           key.find("storage") != std::string::npos ||
           key == "errno";
  };
  const auto sanitize_node = [&](const auto& self, const Json& node)
      -> std::optional<Json> {
    if (node.is_object()) {
      auto result = Json::object();
      for (auto iterator = node.begin(); iterator != node.end(); ++iterator) {
        const auto approved_revision = std::find(
            revision_fields.begin(),
            revision_fields.end(),
            std::string_view(iterator.key()));
        if (approved_revision != revision_fields.end() &&
            iterator.value().is_number_unsigned()) {
          result[iterator.key()] = iterator.value();
          continue;
        }
        if (sensitive_container_key(iterator.key()) ||
            (!iterator.value().is_object() &&
             !iterator.value().is_array())) {
          continue;
        }
        const auto nested = self(self, iterator.value());
        if (nested.has_value()) {
          result[iterator.key()] = *nested;
        }
      }
      if (!result.empty()) {
        return result;
      }
      return std::nullopt;
    }
    if (node.is_array()) {
      auto result = Json::array();
      for (const auto& item : node) {
        if (!item.is_object() && !item.is_array()) {
          continue;
        }
        const auto nested = self(self, item);
        if (nested.has_value()) {
          result.push_back(*nested);
        }
      }
      if (!result.empty()) {
        return result;
      }
      return std::nullopt;
    }
    return std::nullopt;
  };
  const auto sanitized = sanitize_node(sanitize_node, value);
  return sanitized.has_value() && sanitized->is_object()
             ? *sanitized
             : Json::object();
}

std::string safe_message(std::string_view code) {
  static const std::map<std::string_view, std::string_view> messages{
      {"INVALID_ARGUMENT", "request is invalid"},
      {"NOT_FOUND", "requested resource was not found"},
      {"REVISION_CONFLICT", "project revision conflict"},
      {"DUPLICATE_ID", "identifier already exists"},
      {"UNSUPPORTED_AUDIO", "audio input is unsupported"},
      {"MISSING_ASSET", "required asset is missing"},
      {"INVALID_PROJECT", "project data is invalid"},
      {"COOK_FAILED", "runtime snapshot preparation failed"},
      {"BANK_QUOTA_EXHAUSTED",
       "why: the selection exceeds the Sample Bank quota; remedy: shorten "
       "it, free another Pad, or target another Bank"},
      {"PROJECT_QUOTA_EXHAUSTED",
       "why: the selection exceeds the Sample Project quota; remedy: "
       "shorten it or remove prepared Samples, then retry"},
      {"PROVIDER_NOT_FOUND", "provider was not found"},
      {"PROVIDER_FAILED", "provider failed"},
      {"PERMISSION_DENIED", "operation is not permitted"},
      {"IO_ERROR", "project storage operation failed"},
      {"INTERNAL_ERROR", "unexpected Web Host failure"},
  };
  const auto found = messages.find(code);
  return std::string(
      found == messages.end() ? messages.at("INTERNAL_ERROR") : found->second);
}

Json sanitize_quota_details(std::string_view code, const Json& details) {
  if (!details.is_object()) {
    return Json::object();
  }
  const auto copy_unsigned = [&details](Json& result, std::string_view key) {
    const auto found = details.find(key);
    if (found == details.end() || !found->is_number_unsigned()) {
      return false;
    }
    result[std::string(key)] = *found;
    return true;
  };
  Json result = Json::object();
  if (code == "BANK_QUOTA_EXHAUSTED") {
    static constexpr std::array<std::string_view, 6> fields{
        "bank",
        "requested_bytes",
        "requested_frames",
        "remaining_bytes",
        "remaining_frames",
        "quota_bytes",
    };
    if (!std::all_of(fields.begin(), fields.end(), [&](auto field) {
          return copy_unsigned(result, field);
        })) {
      return Json::object();
    }
    const auto consumed = details.find("consumed");
    if (consumed == details.end() || !consumed->is_array()) {
      return Json::object();
    }
    result["consumed"] = Json::array();
    for (const auto& item : *consumed) {
      if (!item.is_object() || !item.value("pad", Json{}).is_number_unsigned() ||
          !item.value("prepared_bytes", Json{}).is_number_unsigned() ||
          !item.value("prepared_frames", Json{}).is_number_unsigned()) {
        return Json::object();
      }
      result["consumed"].push_back({
          {"pad", item.at("pad")},
          {"prepared_bytes", item.at("prepared_bytes")},
          {"prepared_frames", item.at("prepared_frames")},
      });
    }
    return result;
  }
  if (code == "PROJECT_QUOTA_EXHAUSTED") {
    static constexpr std::array<std::string_view, 5> fields{
        "requested_bytes",
        "requested_frames",
        "project_used_bytes",
        "project_remaining_bytes",
        "project_quota_bytes",
    };
    if (!std::all_of(fields.begin(), fields.end(), [&](auto field) {
          return copy_unsigned(result, field);
        })) {
      return Json::object();
    }
    const auto banks = details.find("banks");
    if (banks == details.end() || !banks->is_array()) {
      return Json::object();
    }
    result["banks"] = Json::array();
    for (const auto& item : *banks) {
      if (!item.is_object() ||
          !item.value("bank", Json{}).is_number_unsigned() ||
          !item.value("prepared_bytes", Json{}).is_number_unsigned()) {
        return Json::object();
      }
      result["banks"].push_back({
          {"bank", item.at("bank")},
          {"prepared_bytes", item.at("prepared_bytes")},
      });
    }
    return result;
  }
  return Json::object();
}

bool runtime_resource_rejection(const Json& error) {
  if (!error.is_object() || !error.contains("code") ||
      !error.at("code").is_string()) {
    return false;
  }
  const auto code = error.at("code").get<std::string_view>();
  return code == "WEB_RUNTIME_RESOURCE_LIMIT" ||
         code == "BANK_QUOTA_EXHAUSTED" ||
         code == "PROJECT_QUOTA_EXHAUSTED";
}

Json normalized_error_redacted(
    std::string code,
    const Json& details,
    std::string_view source_message) {
  const auto storage_condition =
      details.is_object() ? details.find("storage_condition") : details.end();
  const auto transfer_condition =
      details.is_object() ? details.find("transfer_condition") : details.end();
  if (code == "INVALID_PROJECT" && details.is_object() &&
      transfer_condition != details.end() &&
      transfer_condition->is_string() &&
      *transfer_condition == "resource_limit") {
    return host_error(
        "WEB_RUNTIME_RESOURCE_LIMIT",
        "Project Bundle exceeds the Web Runtime transfer limit");
  }
  if (code == "INVALID_PROJECT" && details.is_object() &&
      details.find("local_copy") != details.end()) {
    // The refusal describes a Project copy already on this device, not the
    // bundle being imported (#1438): give the UI a code it can name honestly.
    return host_error(
        "LOCAL_PROJECT_UNREADABLE",
        "the local copy of this Project could not be validated");
  }
  if (code == "BANK_QUOTA_EXHAUSTED" ||
      code == "PROJECT_QUOTA_EXHAUSTED") {
    return host_error(
        code, safe_message(code), sanitize_quota_details(code, details));
  }
  if (code == "IO_ERROR" && details.is_object() &&
      storage_condition != details.end() &&
      storage_condition->is_string() &&
      *storage_condition == "project_busy") {
    return host_error(
        "PROJECT_BUSY",
        "project is already open for writing");
  }
  if (code == "IO_ERROR" && details.is_object() &&
      storage_condition != details.end() &&
      storage_condition->is_string() &&
      *storage_condition == "atomic_publish_unsupported") {
    return host_error(
        "UNSUPPORTED_WEB_RUNTIME",
        "atomic Project directory publication is unavailable");
  }
  if (code == "IO_ERROR" && details.is_object() &&
      storage_condition != details.end() &&
      storage_condition->is_string() &&
      *storage_condition == "already_exists") {
    return host_error(
        "DUPLICATE_ID",
        "a different Project already uses this identity");
  }
  if (code == "INVALID_ARGUMENT" &&
      source_message.starts_with("Project Bundle")) {
    return host_error("INVALID_PROJECT", "Project Bundle transfer is invalid");
  }
  static constexpr std::array<std::string_view, 1> resource_names{
      "artifact_bytes",
  };
  const auto resource =
      details.is_object() ? details.find("resource") : details.end();
  const auto observed =
      details.is_object() ? details.find("observed") : details.end();
  const auto limit =
      details.is_object() ? details.find("limit") : details.end();
  const auto valid_resource =
      resource != details.end() && resource->is_string() &&
      std::find(
          resource_names.begin(),
          resource_names.end(),
          resource->get<std::string_view>()) != resource_names.end();
  if (code == "COOK_FAILED" &&
      source_message == "runtime preparation limit exceeded" &&
      valid_resource && observed != details.end() &&
      observed->is_number_unsigned() && limit != details.end() &&
      limit->is_number_unsigned()) {
    return host_error(
        "WEB_RUNTIME_RESOURCE_LIMIT",
        "runtime preparation limit exceeded",
        {
            {"resource", *resource},
            {"observed", *observed},
            {"limit", *limit},
        });
  }
  if (source_message == "capture barrier timed out") {
    return host_error("HOST_TIMEOUT", "capture barrier timed out");
  }
  return host_error(code, safe_message(code), sanitize_details(details));
}

constexpr std::size_t kRefusalDiagnosticLineCap = 2048;
constexpr std::size_t kRefusalDiagnosticMessageCap = 512;
constexpr std::size_t kRefusalDiagnosticCodeCap = 128;

std::size_t utf8_prefix_length(std::string_view text, std::size_t cap) {
  auto boundary = std::min(cap, text.size());
  while (boundary > 0 && boundary < text.size() &&
         (static_cast<unsigned char>(text[boundary]) & 0xC0) == 0x80) {
    --boundary;
  }
  return boundary;
}

std::string refusal_diagnostic_token(std::string_view value, std::size_t cap) {
  if (value.size() <= cap) {
    return std::string(value);
  }
  return std::string(value.substr(0, utf8_prefix_length(value, cap))) + "...";
}

std::string refusal_diagnostic_message(std::string_view source_message) {
  return refusal_diagnostic_token(
      source_message, kRefusalDiagnosticMessageCap);
}

Json refusal_diagnostic_details(const Json& details) {
  auto copy = Json::object();
  if (details.is_object()) {
    for (const auto& [key, value] : details.items()) {
      if (value.is_string() || value.is_number() || value.is_boolean()) {
        copy[key] = value;
      }
    }
  }
  return copy;
}

// Records the pre-sanitization reason of every normalized refusal on stderr
// (Emscripten printErr in the packaged build, so the line reaches the page
// console and the proof harness). The wire payload is untouched: this is the
// only channel that carries the Facade-authored code, message and scalar
// details. One fputs per refusal so one complete console line is forwarded.
void emit_refusal_diagnostic(
    std::string_view source_code,
    const Json& source_details,
    std::string_view source_message,
    const Json& normalized) {
  static constexpr std::string_view kPrefix = "lmdj-refusal-diagnostic ";
  auto diagnostic = Json{
      {"normalized", normalized.at("error").at("code")},
      {"source_code",
       refusal_diagnostic_token(source_code, kRefusalDiagnosticCodeCap)},
      {"source_message", refusal_diagnostic_message(source_message)},
      {"details", refusal_diagnostic_details(source_details)},
  };
  auto line = std::string(kPrefix) + diagnostic.dump();
  if (line.size() > kRefusalDiagnosticLineCap) {
    diagnostic["details"] = Json{{"truncated", true}};
    line = std::string(kPrefix) + diagnostic.dump();
    // Every remaining field is bounded by kRefusalDiagnosticCodeCap or a
    // fixed literal, so shortening the message re-establishes the cap in
    // one pass; each raw character costs at least one serialized byte.
    while (line.size() > kRefusalDiagnosticLineCap &&
           !diagnostic.at("source_message").get<std::string>().empty()) {
      const auto excess = line.size() - kRefusalDiagnosticLineCap;
      const auto& message =
          diagnostic.at("source_message").get_ref<const std::string&>();
      diagnostic["source_message"] = message.substr(
          0, message.size() - std::min(excess, message.size()));
      line = std::string(kPrefix) + diagnostic.dump();
    }
  }
  line.push_back('\n');
  std::fputs(line.c_str(), stderr);
}

Json normalized_error(
    std::string code,
    const Json& details,
    std::string_view source_message = {}) {
  auto error = normalized_error_redacted(code, details, source_message);
  emit_refusal_diagnostic(code, details, source_message, error);
  return error;
}

Json normalized_error(const Error& error) {
  return normalized_error(
      std::string(foundation::error_code_name(error.code)),
      error.details,
      error.message);
}

Json normalized_facade_error(const Json& response) {
  if (!response.is_object() || response.value("ok", true) ||
      !response.contains("error") || !response.at("error").is_object()) {
    return internal_error();
  }
  const auto& error = response.at("error");
  if (!error.contains("code") || !error.at("code").is_string() ||
      !error.contains("message") || !error.at("message").is_string() ||
      !error.contains("details")) {
    return internal_error();
  }
  return normalized_error(
      error.at("code").get<std::string>(),
      error.at("details"),
      error.at("message").get<std::string>());
}

Json normalized_facade_success(const Json& response) {
  if (!response.is_object() || response.value("ok", false) != true ||
      !response.contains("result") || !response.at("result").is_object() ||
      !response.contains("project_revision")) {
    return internal_error();
  }
  auto result = response.at("result");
  result["project_revision"] = response.at("project_revision");
  return success(std::move(result));
}

std::string sha256(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* first =
        reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(first, first + bytes.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

void require_sidecar(
    const Json& declaration,
    std::span<const std::byte> sidecar) {
  require(exact_keys(
      declaration, {"sidecar_bytes", "sidecar_sha256"}));
  const auto declared_bytes = unsigned_field(
      declaration, "sidecar_bytes", detail::kBridgeMaximumSidecarBytes);
  const auto declared_sha = string_field(declaration, "sidecar_sha256");
  require(
      declared_sha.size() == 64 &&
      std::all_of(
          declared_sha.begin(), declared_sha.end(), [](char value) {
            return (value >= '0' && value <= '9') ||
                   (value >= 'a' && value <= 'f');
          }));
  require(declared_bytes == sidecar.size());
  require(sha256(sidecar) == declared_sha);
}

Json local_project_summary(const facade::LocalProjectSummary& summary) {
  return {
      {"project_id", summary.project_id.value()},
      {"pattern_id", summary.pattern_id.value()},
      {"revision", summary.revision},
      {"bpm", summary.bpm},
      {"asset_count", summary.asset_count},
      {"assigned_pad_count", summary.assigned_pad_count},
      {"bundle_digest", summary.bundle_digest},
  };
}

std::string capture_state_name(audio::CaptureState state) {
  switch (state) {
    case audio::CaptureState::idle:
      return "idle";
    case audio::CaptureState::arm_pending:
      return "arm_pending";
    case audio::CaptureState::active:
      return "active";
    case audio::CaptureState::disarm_pending:
      return "disarm_pending";
    case audio::CaptureState::corrupted:
      return "corrupted";
  }
  return "corrupted";
}

std::string enqueue_failure_message(audio::EnqueueResult result) {
  switch (result) {
    case audio::EnqueueResult::sample_unavailable:
      return "trigger sample is unavailable";
    case audio::EnqueueResult::bank_transition:
      return "runtime Bank transition is pending";
    case audio::EnqueueResult::queue_full:
      return "trigger queue is full";
    case audio::EnqueueResult::not_running:
      return "audio runtime is not running";
    case audio::EnqueueResult::invalid_slot:
    case audio::EnqueueResult::invalid_velocity:
    case audio::EnqueueResult::accepted:
      return "trigger is invalid";
  }
  return "trigger is invalid";
}

}  // namespace

// The Host side of the Facade's public Pattern transport audio port. Every
// method stays on the serialized control thread, which is the owner the
// Engine's submit/inspect/acknowledge contract requires.
class EnginePatternTransportPort final : public facade::PatternTransportAudioPort {
 public:
  explicit EnginePatternTransportPort(audio::RealtimeEngine& engine) noexcept
      : engine_(engine) {}

  // The overlay publication capability the coordinator drives (#1513). The
  // Impl injects its prepare-and-publish closure right after construction:
  // building the prepared view needs the Runtime Snapshot, which lives on the
  // Impl, not on this engine-only adapter. Empty means the engagement has not
  // finished wiring; the coordinator treats that as an ordinary refusal and
  // retries on the next cadence tick.
  void bind_overlay_publication(
      std::function<foundation::Result<audio::PatternPublication>(
          const foundation::PatternId&, std::span<const domain::PatternEvent>)>
          publish) {
    publish_overlay_ = std::move(publish);
  }

  audio::PatternTransportSubmit submit(
      const audio::PatternTransportCommand& command) override {
    return engine_.submit_pattern_transport(command);
  }
  std::optional<audio::PatternTransportReceipt> inspect(
      std::uint64_t generation, std::uint64_t epoch) const override {
    return engine_.inspect_pattern_transport_receipt(generation, epoch);
  }
  bool acknowledge(std::uint64_t generation, std::uint64_t epoch) override {
    return engine_.acknowledge_pattern_transport_receipt(
        generation, epoch);
  }
  std::uint64_t pattern_generation() const override {
    return engine_.pattern_telemetry().current_generation;
  }
  bool supports_receipt_bound_opening() const override { return true; }
  std::optional<audio::PatternTransportObservation> observe_transport()
      const override {
    return engine_.pattern_transport_observation();
  }
  std::optional<audio::PatternReplacementAuthority> pending_switch()
      const override {
    // The remembered overlay authority is reported only while the engine
    // itself still holds that exact generation pending — telemetry's snapshot
    // can diverge from the slot's stored triple, but a pending generation the
    // engine no longer reports means the overlay was superseded or cancelled,
    // and the engine's real successor must not be masked by it. Once the
    // generation is current the overlay applied and the record is spent.
    if (queued_overlay_.has_value()) {
      const auto telemetry = engine_.pattern_telemetry();
      const auto pending_pattern = engine_.pending_pattern_id();
      // The remembered authority is reported only when the engine itself
      // still holds that exact publication — same generation AND same
      // Pattern. Anything else (applied, cancelled, superseded) spends the
      // record, and the engine's real successor must never be masked.
      if (telemetry.pending_generation == queued_overlay_->generation &&
          pending_pattern.has_value() &&
          *pending_pattern == queued_overlay_->pattern_id) {
        return *queued_overlay_;
      }
      queued_overlay_.reset();
    }
    const auto pending = engine_.pending_pattern_id();
    const auto telemetry = engine_.pattern_telemetry();
    if (!pending.has_value() || telemetry.pending_generation == 0) {
      return std::nullopt;
    }
    return audio::PatternReplacementAuthority{
        telemetry.pending_generation,
        *pending,
        telemetry.pending_activation_frame,
    };
  }
  std::optional<foundation::PatternId> current_pattern() const override {
    return engine_.current_pattern_id();
  }
  foundation::Result<audio::PatternPublication> publish_overlay(
      const foundation::PatternId& pattern,
      std::span<const domain::PatternEvent> events) override {
    if (!publish_overlay_) {
      return foundation::Result<audio::PatternPublication>::failure(
          {foundation::ErrorCode::internal_error,
           "Pattern transport overlay publication is not wired"});
    }
    const auto published = publish_overlay_(pattern, events);
    if (published.has_value()) {
      // Remember the exact authority this port published. Telemetry can
      // diverge from the slot's stored triple, and a fence naming the overlay
      // must match the slot exactly, so report the remembered triple while
      // the publication has not landed (#1513).
      queued_overlay_ = audio::PatternReplacementAuthority{
          published.value().generation, pattern,
          published.value().activation_frame};
    }
    return published;
  }
  bool cancel_overlay(
      const audio::PatternReplacementAuthority& authority) override {
    // Only the exact overlay this port published and still remembers; a
    // switch or any other publication is never withdrawn through this seam.
    if (!queued_overlay_.has_value() ||
        queued_overlay_->generation != authority.generation ||
        queued_overlay_->pattern_id != authority.pattern_id ||
        queued_overlay_->activation_frame != authority.activation_frame) {
      return false;
    }
    const auto cancelled = switch_reservation_
        ? engine_.cancel_unclaimed_pattern_publication(authority)
        : engine_.cancel_pattern_publication(authority);
    if (!cancelled) {
      return false;
    }
    queued_overlay_.reset();
    return true;
  }

  bool owns_overlay(const audio::PatternReplacementAuthority& authority) const {
    return queued_overlay_ && queued_overlay_->generation == authority.generation &&
        queued_overlay_->pattern_id == authority.pattern_id &&
        queued_overlay_->activation_frame == authority.activation_frame;
  }

  foundation::Result<facade::PatternTransportSwitchTicket> reserve_recording_switch(
      facade::PatternTransportController& controller,
      const facade::PatternTransportSwitchRequest& request) {
    // A claimed overlay retains its audio-local slot through its old boundary.
    // Canceling it and accepting a Beat successor would delay that successor
    // behind the canceled Bar. Only atomic unclaimed withdrawal is admissible
    // here. Stop keeps its separate, receipt-bound claimed cancellation path.
    struct Reset { bool& value; ~Reset() { value = false; } } reset{switch_reservation_};
    switch_reservation_ = true;
    return controller.reserve_pattern_switch(request);
  }

 private:
  audio::RealtimeEngine& engine_;
  bool switch_reservation_{};
  std::function<foundation::Result<audio::PatternPublication>(
      const foundation::PatternId&, std::span<const domain::PatternEvent>)>
      publish_overlay_;
  mutable std::optional<audio::PatternReplacementAuthority> queued_overlay_;
};

class EngineScheduledPatternTransportPort final
    : public facade::ScheduledPatternTransportAudioPort {
 public:
  explicit EngineScheduledPatternTransportPort(audio::RealtimeEngine& engine)
      noexcept : engine_(engine) {}
  audio::ScheduledPatternSubmit submit_scheduled(
      const audio::ScheduledPatternRecordRequest& request) override {
    return engine_.submit_scheduled_pattern_record(request);
  }
  std::optional<audio::ScheduledPatternRecordStatus> inspect_scheduled(
      std::uint64_t generation, std::uint64_t serial) const override {
    return engine_.inspect_scheduled_pattern_record(generation, serial);
  }
  audio::ScheduledPatternSubmit cancel_scheduled(
      const audio::ScheduledPatternCancelRequest& request) override {
    return engine_.cancel_scheduled_pattern_record(request);
  }
  bool acknowledge_scheduled(std::uint64_t generation, std::uint64_t serial,
      std::uint64_t epoch) override {
    return engine_.acknowledge_scheduled_pattern_record(generation, serial, epoch);
  }
  bool scheduled_quiescent() const override {
    return engine_.scheduled_pattern_record_quiescent();
  }
 private:
  audio::RealtimeEngine& engine_;
};

// One engaged global Pattern transport session. The Facade factory owns the
// Journal/Store behind the controller; the Host holds only the audio port it
// implements and the controller itself, and never names a Project I/O type.
// The admission candidate watermark and press/release correlation are
// Host-side input identities assigned at the existing post-enqueue point,
// never reused across engagement.
struct RetainedRecordingSwitch {
  facade::PatternTransportSwitchTicket ticket;
  audio::PatternPublicationLease lease;
};

struct TransportEngagement {
  explicit TransportEngagement(audio::RealtimeEngine& engine)
      : port(engine), scheduled_port(engine) {}

  EnginePatternTransportPort port;
  EngineScheduledPatternTransportPort scheduled_port;
  std::unique_ptr<facade::PatternTransportController> controller;
  std::array<std::optional<RetainedRecordingSwitch>,
      facade::kPatternTransportSwitchCapacity> recording_switches;
  std::optional<foundation::SequenceSessionId> session;
  // The Pattern identity the Facade controller is bound to; a cross-identity
  // republication outside the coordinator must retire the engagement first.
  std::optional<foundation::PatternId> pattern;
  std::uint64_t generation = 0;
  // The coordinator's admission preparation opens its candidate window at
  // watermark 10; the Host allocates post-enqueue watermarks from that floor,
  // monotone per engagement. The Host test pins this contract.
  std::uint64_t next_watermark = 10;
  std::map<domain::PadSlotId, std::uint64_t> owned_presses;
  std::optional<facade::PatternTransportCandidate> legacy_candidate;
  std::optional<std::string> legacy_request_id;
  bool shutdown_requested = false;
  // Set when a recording close has settled durably but the committed Pattern
  // publication is still outstanding; publication is a separate completion.
  bool publish_pending = false;
  bool count_in_ticket_consumed = true;
  bool count_in_cancel_pending = false;
};

struct RetainedPatternInput {
  Json original_request;
  facade::PatternTransportInputTicket ticket;
  std::uint64_t frame_epoch{};
  audio::PatternInputAdmission admission;
  std::optional<facade::PatternTransportInputTicket> facade_ticket;
  std::optional<audio::PatternInputCompletion> completion;
  std::chrono::steady_clock::time_point started;
  bool durable_settled{};
  bool retained{};
  bool complete{};
  std::optional<Error> error;
};
struct RetainedPatternHold {
  std::uint64_t sequence{}, generation{}, frame_epoch{};
  std::uint8_t slot{};
  bool facade_owned{}, release_submitted{};
};
struct RetainedLegacyInput {
  Json accepted_response;
  std::optional<Json> terminal_response;
  std::chrono::steady_clock::time_point deadline;
  bool observer_consumed{};
};

Json pattern_input_authority_json(const audio::PatternInputAuthority& authority) {
  return {{"recording", authority.recording},
      {"schedule_serial", authority.schedule_serial ? Json(std::to_string(authority.schedule_serial)) : Json(nullptr)},
      {"transport_epoch", authority.transport_epoch ? Json(std::to_string(authority.transport_epoch)) : Json(nullptr)}};
}
Json pattern_input_ticket_json(const RetainedPatternInput& input) {
  return {{"command_id", input.ticket.command_id.value()},
      {"runtime_generation", std::to_string(input.ticket.runtime_generation)},
      {"frame_epoch", std::to_string(input.frame_epoch)},
      {"ticket", std::to_string(input.ticket.ticket)}};
}

std::string_view pattern_transport_phase_name(
    facade::PatternTransportPhase phase) noexcept {
  switch (phase) {
    case facade::PatternTransportPhase::idle:
      return "idle";
    case facade::PatternTransportPhase::preparing:
      return "preparing";
    case facade::PatternTransportPhase::awaiting_audio:
      return "awaiting_audio";
    case facade::PatternTransportPhase::flushing:
      return "flushing";
    case facade::PatternTransportPhase::reconciling:
      return "reconciling";
    case facade::PatternTransportPhase::error:
      return "error";
  }
  return "error";
}

std::string_view pattern_transport_submit_name(
    facade::PatternTransportSubmit submit) noexcept {
  switch (submit) {
    case facade::PatternTransportSubmit::accepted:
      return "accepted";
    case facade::PatternTransportSubmit::replayed:
      return "replayed";
    case facade::PatternTransportSubmit::busy:
      return "busy";
    case facade::PatternTransportSubmit::invalid:
      return "invalid";
    case facade::PatternTransportSubmit::stale:
      return "stale";
    case facade::PatternTransportSubmit::refused:
      return "refused";
  }
  return "refused";
}

// `runtime_frame` is the Engine's rendered frame count when the status was
// read, so a Host can place a playhead relative to `origin_frame` without
// assuming the transport has just started. `current_pattern_id` and
// `pending_switch` place the Engine's Pattern selection and the Host's queued
// playing-state switch (#1958) on the same status.
Json pattern_transport_status_json(
    bool engaged,
    const facade::PatternTransportStatus& status,
    bool publication_pending,
    std::uint64_t runtime_frame,
    Json current_pattern_id,
    Json pending_switch) {
  return {
      {"engaged", engaged},
      {"playing", status.playing},
      {"recording", status.recording},
      {"phase", std::string(pattern_transport_phase_name(status.phase))},
      {"runtime_generation", status.runtime_generation},
      {"transport_epoch", status.transport_epoch},
      {"origin_frame", status.origin_frame},
      {"runtime_frame", runtime_frame},
      {"command_id",
       status.command_id.has_value() ? Json(status.command_id->value())
                                     : Json(nullptr)},
      {"publication_pending", publication_pending},
      {"error",
       status.error.has_value() ? normalized_error(*status.error).at("error")
                                : Json(nullptr)},
      {"current_pattern_id", std::move(current_pattern_id)},
      {"pending_switch", std::move(pending_switch)},
  };
}

Json safe_count_in_frame(std::uint64_t frame) {
  require(frame <= kMaximumSafeInteger);
  return frame;
}
Json optional_count_in_frame(const std::optional<std::uint64_t>& frame) {
  return frame ? safe_count_in_frame(*frame) : Json(nullptr);
}
Json pattern_input_status_json(const RetainedPatternInput& input,
    std::chrono::steady_clock::time_point now) {
  Json completion = nullptr;
  if (input.completion) {
    constexpr std::array<std::string_view, 7> dispositions{"voice_started", "voice_capacity",
        "toggle_stopped", "muted_no_voice", "release_applied", "release_no_voice",
        "invalidated_before_consume"};
    const auto& c = *input.completion;
    const auto disposition = static_cast<std::size_t>(c.disposition);
    require(disposition < dispositions.size());
    completion = {{"runtime_generation", std::to_string(c.runtime_generation)},
        {"frame_epoch", std::to_string(c.frame_epoch)}, {"sequence", std::to_string(c.sequence)},
        {"held_press_sequence", c.held_press_sequence ? Json(std::to_string(c.held_press_sequence)) : Json(nullptr)},
        {"acceptance_ordinal", std::to_string(c.acceptance_ordinal)},
        {"runtime_frame", safe_count_in_frame(c.runtime_frame)}, {"slot", c.slot},
        {"authority", pattern_input_authority_json(c.authority)},
        {"disposition", std::string(dispositions[disposition])}};
  }
  return {{"ticket", pattern_input_ticket_json(input)},
      {"admission", {{"sequence", std::to_string(input.admission.sequence)},
          {"acceptance_ordinal", std::to_string(input.admission.acceptance_ordinal)},
          {"authority", pattern_input_authority_json(input.admission.authority)}}},
      {"native_result", std::move(completion)}, {"durable_settled", input.durable_settled},
      {"retained", input.retained}, {"complete", input.complete},
      {"expired", !input.complete && now - input.started >= facade::kPatternTransportInputDeadline},
      {"error", input.error ? normalized_error(*input.error).at("error") : Json(nullptr)}};
}
Json scheduled_pattern_receipt_json(
    const std::optional<audio::ScheduledPatternRecordReceipt>& receipt) {
  if (!receipt) return nullptr;
  constexpr std::array<std::string_view, 3> results{"applied", "cancelled", "refused"};
  const auto result = static_cast<std::size_t>(receipt->result);
  require(result < results.size());
  return {
      {"runtime_generation", std::to_string(receipt->runtime_generation)},
      {"frame_epoch", std::to_string(receipt->frame_epoch)},
      {"schedule_serial", std::to_string(receipt->serial)},
      {"transport_epoch", std::to_string(receipt->epoch)},
      {"pattern_generation", std::to_string(receipt->pattern_generation)},
      {"pattern_id", receipt->pattern_id.value()},
      {"result", std::string(results[result])},
      {"effective_frame", optional_count_in_frame(receipt->effective_frame)},
      {"origin_frame", optional_count_in_frame(receipt->origin_frame)},
      {"playing", receipt->playing},
  };
}
Json scheduled_pattern_ticket_json(
    const facade::ScheduledPatternTransportRequest& request) {
  return {{"session_id", request.transport.session.value()},
      {"command_id", request.transport.command_id.value()},
      {"runtime_generation", std::to_string(request.transport.runtime_generation)},
      {"frame_epoch", std::to_string(request.frame_epoch)},
      {"schedule_serial", std::to_string(request.schedule_serial)}};
}
Json scheduled_pattern_status_json(
    const facade::ScheduledPatternTransportStatus& status) {
  Json view = nullptr;
  if (status.request) {
    const auto& request = *status.request;
    constexpr std::array<std::string_view, 10> phases{"empty", "submitted", "preparing",
        "cancel_preparing", "armed", "starting", "applied", "cancelled", "failing", "refused"};
    const auto phase = status.count_in
        ? static_cast<std::size_t>(status.count_in->phase)
        : static_cast<std::size_t>(audio::ScheduledPatternPhase::submitted);
    require(phase < phases.size() && !phases[phase].empty());
    view = {{"runtime_generation", std::to_string(request.transport.runtime_generation)},
        {"frame_epoch", std::to_string(request.frame_epoch)},
        {"schedule_serial", std::to_string(request.schedule_serial)},
        {"phase", std::string(phases[phase])}, {"bars", request.bars},
        {"bpm", status.count_in && status.count_in->bpm != 0 ? Json(status.count_in->bpm) : Json(nullptr)},
        {"bar_frames", status.count_in && status.count_in->bar_frames != 0
            ? safe_count_in_frame(status.count_in->bar_frames) : Json(nullptr)},
        {"count_in_frame", status.count_in
            ? optional_count_in_frame(status.count_in->count_in_frame) : Json(nullptr)},
        {"start_frame", status.count_in
            ? optional_count_in_frame(status.count_in->start_frame) : Json(nullptr)}};
  }
  Json error = status.error ? normalized_error(*status.error).at("error") : Json(nullptr);
  if (status.error && status.error->details.is_object()) {
    const auto& details = status.error->details;
    const auto reason = details.find("reason");
    // Only these count-in-owned deadline facts cross this status boundary.
    // Keep the generic sanitizer, safe messages and unrelated details intact.
    if (reason != details.end() && reason->is_string()) {
      const bool provisional = status.error->code == ErrorCode::io_error &&
          *reason == "pattern_transport_opening_expired";
      const bool final = status.error->code == ErrorCode::invalid_argument &&
          *reason == "admission_opening_deadline_elapsed";
      if (provisional || final) {
        error["details"]["reason"] = *reason;
        for (const auto* flag : {"closure_unresolved", "retryable"}) {
          const auto value = details.find(flag);
          if (value != details.end() && value->is_boolean() && *value == true)
            error["details"][flag] = true;
        }
      }
      const auto retained = details.find("journal_retained");
      if (final && retained != details.end() && retained->is_boolean() && *retained == true)
        error["details"]["journal_retained"] = true;
    }
  }
  return {{"ticket", status.request ? scheduled_pattern_ticket_json(*status.request) : Json(nullptr)},
      {"count_in", std::move(view)},
      {"start_receipt", scheduled_pattern_receipt_json(status.start_receipt)},
      {"cancel_receipt", scheduled_pattern_receipt_json(status.cancel_receipt)},
      {"opening_pending", status.opening_pending},
      {"opening_complete", status.opening_complete},
      {"error", std::move(error)}};
}

struct ControlRuntime::Impl {
  enum class State { core_ready, running, audio_suspended, closed, failed };

  struct SequenceSession {
    foundation::SequenceSessionId id;
    foundation::PatternId pattern_id;
    std::uint64_t next_input_sequence{1};
    std::optional<domain::PadSlotId> armed_capture_slot;
    std::uint64_t published_overlay_generation{0};
  };

  struct PendingSequenceBoundary {
    foundation::SequenceSessionId session_id;
    foundation::PatternId pattern_id;
    std::uint64_t runtime_frame;
    std::uint64_t generation;
    bool notified = false;
  };

  // A committed grid edit whose swap found every Pattern slot still held by
  // retiring views that are sounding (#1671). It waits for reclaim to free a
  // slot; any other publication since was prepared from Truth after the
  // edit, so a changed generation supersedes it.
  struct DeferredPatternEdit {
    std::string project_id;
    foundation::PatternId pattern_id;
    std::uint64_t expected_generation;
    std::uint64_t reclaimed_patterns;
    // The revision runtime_revision advanced to when the swap was deferred.
    std::optional<std::uint64_t> runtime_revision;
  };

  // Exactly one of: swapped in, deferred (neither set), or failed.
  struct EditedPatternPublication {
    std::optional<audio::PatternPublication> publication;
    std::optional<Json> error;
  };

  struct RememberedTransportSwitch {
    audio::PatternReplacementAuthority authority;
    audio::PatternSwitchSnap snap = audio::PatternSwitchSnap::bar;
  };

  // Every selected boundary is already owned by the Engine, including a
  // successor queued behind an audio-claimed predecessor. Retain exact
  // predecessor authorities across a racing Q→A handoff; obsolete triples
  // never authorize cancellation or replacement of a newer generation.
  struct PendingTransportSwitch {
    foundation::PatternId pattern_id;
    std::uint64_t activation_frame = 0;
    std::uint64_t generation = 0;
    audio::PatternSwitchSnap snap = audio::PatternSwitchSnap::bar;
    std::array<std::optional<RememberedTransportSwitch>, 2> predecessors{};
  };

  static facade::Application compose_application(
      audio::RealtimeEngine& engine,
      facade::ApplicationConfig config,
      const std::shared_ptr<std::atomic<bool>>& publication_failure,
      std::function<void()>& service) {
    auto gateway = facade::make_engine_pattern_publication_gateway(engine);
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
    auto publish = std::move(gateway.publish);
    gateway.publish =
        [publication_failure, publish = std::move(publish)](
            std::shared_ptr<const cooker::RuntimeSnapshot> snapshot,
            std::optional<std::uint64_t> activation_frame,
            std::optional<audio::PatternReplacementAuthority>
                replacement_authority) {
          if (publication_failure->exchange(false)) {
            return foundation::Result<audio::PatternPublication>::failure(
                Error{
                    ErrorCode::invalid_argument,
                    "injected Performance Pattern publication failure",
                });
          }
          return publish(
              std::move(snapshot),
              activation_frame,
              std::move(replacement_authority));
        };
#else
    static_cast<void>(publication_failure);
#endif
    auto adapter = facade::make_engine_performance_adapter(
        engine, std::move(gateway));
    config.performance_clock = std::move(adapter.clock);
    config.performance_input_sequencer = std::move(adapter.input_sequencer);
    config.pattern_launch_acknowledger =
        std::move(adapter.launch_acknowledger);
    config.performance_replay_controller =
        std::move(adapter.replay_controller);
    config.performance_gesture_sink = std::move(adapter.gesture_sink);
    // W1: the typed live-control port reaches the Facade; epoch binding and
    // stale rejection stay Core-side.
    config.performance_live_control = std::move(adapter.live_control);
    service = std::move(adapter.service);
    return facade::Application(std::move(config));
  }

  Impl(
      std::filesystem::path root,
      facade::ApplicationConfig config,
      audio::RuntimePreparationLimits owned_limits)
      : workspace_root(std::move(root)),
        limits(owned_limits),
        host_catalog(
            std::dynamic_pointer_cast<facade::SuppliedSoundSetCatalog>(
                config.soundset_catalog_transport)),
        performance_publication_failure(
            std::make_shared<std::atomic<bool>>(false)),
        performance_service(),
        application(compose_application(
            engine,
            std::move(config),
            performance_publication_failure,
            performance_service)) {}

  void service_performance_adapter() {
    if (performance_service) {
      performance_service();
    }
  }

  foundation::Result<void> service_performance() {
    service_performance_adapter();
    auto serviced = application.service_performance();
    observe_replay();
    restore_after_replay();
    return serviced;
  }

  // Follows a replay begun through this Host from its own begin/stop
  // responses and the status query; anything but `playing` ends it.
  void track_replay_response(std::string_view operation, const Json& result) {
    if (!project_id.has_value() || !result.is_object() ||
        !result.contains("replay_id") || !result.contains("state")) {
      return;
    }
    const auto state = result.value("state", std::string{});
    if (operation == "performance.replay.begin" && state == "playing") {
      active_replay = TrackedReplay{
          *project_id, result.at("replay_id").get<std::string>()};
      return;
    }
    if (active_replay.has_value() && state != "playing" &&
        result.at("replay_id") == active_replay->replay_id) {
      replay_restore = PendingReplayRestore{active_replay->project_id, std::nullopt};
      active_replay.reset();
    }
  }

  // A replay holds the Runtime only for the Project it played; another
  // Project opened meanwhile publishes its own view.
  bool replay_holds_runtime() const {
    return active_replay.has_value() && project_id == active_replay->project_id;
  }

  void observe_replay() {
    if (!active_replay.has_value()) {
      return;
    }
    if (!session_available() || project_id != active_replay->project_id) {
      // Another Project replaced the one the replay played; its open path
      // publishes that Project's own view.
      active_replay.reset();
      replay_restore.reset();
      return;
    }
    const auto status = application.query({
        {"operation", "performance.replay.status"},
        {"project_path", retained_project_path->generic_string()},
        {"replay_id", active_replay->replay_id},
    });
    if (!status.value("ok", false)) {
      // An unreadable replay cannot be holding the Runtime any longer.
      replay_restore = PendingReplayRestore{active_replay->project_id, std::nullopt};
      active_replay.reset();
      return;
    }
    track_replay_response("performance.replay.status", status.at("result"));
  }

  // Service cadence: the replay's own Pattern view is what the engine holds,
  // so the Host's selected Pattern comes back from Truth — at the next Bar
  // while the transport plays, as a Pattern switch does, otherwise at once.
  void restore_after_replay() {
    if (!replay_restore.has_value() || active_replay.has_value()) {
      return;
    }
    if (!session_available() || !pattern_id.has_value() ||
        project_id != replay_restore->project_id) {
      replay_restore.reset();
      return;
    }
    bool playing = false;
    if (transport != nullptr) {
      const auto status = transport->controller->inspect();
      if (status.recording ||
          status.phase != facade::PatternTransportPhase::idle ||
          status.error.has_value() || transport->publish_pending) {
        return;
      }
      playing = status.playing;
    }
    if (engine.pattern_telemetry().pending_generation != 0) {
      return;
    }
    const foundation::PatternId selected{*pattern_id};
    if (playing) {
      // The restore carries any deferred edit, since both come from Truth.
      deferred_pattern_edit.reset();
      static_cast<void>(engine.reclaim_retired_patterns());
      const auto reclaimed = engine.pattern_telemetry().reclaimed_patterns;
      if (replay_restore->held_at_reclaimed == reclaimed) {
        // Every slot was held and none has freed since; preparing from Truth
        // again would only be refused again.
        return;
      }
      auto pattern = prepare_project_pattern(selected);
      if (pattern.has_value()) {
        const auto result =
            engine.publish_pattern_view(std::move(pattern.value())).result;
        if (result == audio::PatternPublishResult::pattern_slots_full) {
          // A sounding retiring view holds every slot; retry once one frees.
          replay_restore->held_at_reclaimed = reclaimed;
          return;
        }
        if (result == audio::PatternPublishResult::accepted) {
          replay_restore.reset();
          return;
        }
      }
      // The Runtime no longer reflects the revision it claimed.
      runtime_revision.reset();
      replay_restore.reset();
      return;
    }
    const auto published = publish_edited_pattern(selected, false);
    if (published.error.has_value()) {
      // The Runtime no longer reflects the revision it claimed.
      runtime_revision.reset();
    }
    replay_restore.reset();
  }

  // #1801: commands take over only after the replay's own Stop has settled.
  // Audio callbacks continue independently of this serialized control turn;
  // the original request deadline bounds both neutral reset and publication.
  // Project replacement supplies a new view; transport takes the selected
  // Pattern's current Truth, never the Pattern a replay happened to launch.
  std::optional<Json> stop_replay_before_command(bool restore_pattern) {
    if (active_replay.has_value()) {
      const auto request = Json{
          {"operation", "performance.replay.stop"},
          {"project_path", retained_project_path->generic_string()},
          {"replay_id", active_replay->replay_id},
          {"request_id", generated_uuid()},
      };
      while (active_replay.has_value()) {
        if (request_cancelled()) {
          return timeout_error();
        }
        const auto response = application.command(request);
        if (!response.value("ok", false)) {
          return normalized_facade_error(response);
        }
        track_replay_response("performance.replay.stop", response.at("result"));
        if (active_replay.has_value()) {
          std::this_thread::yield();
        }
      }
    }
    if (!restore_pattern || !replay_restore.has_value()) {
      return std::nullopt;
    }
    if (!session_available() || !pattern_id.has_value() ||
        project_id != replay_restore->project_id) {
      return state_error("replay Project is unavailable for transport handoff");
    }
    while (engine.pattern_telemetry().pending_generation != 0) {
      if (request_cancelled()) {
        return timeout_error();
      }
      std::this_thread::yield();
    }
    if (request_cancelled()) {
      return timeout_error();
    }
    const auto published = publish_edited_pattern(
        foundation::PatternId{*pattern_id}, false);
    if (published.error.has_value()) {
      return Json{{"ok", false}, {"error", *published.error}};
    }
    if (!published.publication.has_value()) {
      return state_error("runtime Pattern publication is unavailable");
    }
    const auto generation = published.publication->generation;
    while (engine.pattern_telemetry().current_generation != generation) {
      if (request_cancelled()) {
        return timeout_error();
      }
      std::this_thread::yield();
    }
    replay_restore.reset();
    return std::nullopt;
  }

  std::filesystem::path project_path(std::string_view project_id) const {
    return workspace_root / "projects" /
           (std::string(project_id) + ".lmdj");
  }

  // A commit that changes no Bank, such as a grid edit or a settings change,
  // keeps a Runtime that was current before it current at the new revision.
  void keep_runtime_current(bool runtime_was_current) {
    if (!runtime_was_current) {
      return;
    }
    runtime_revision = project_revision;
    if (deferred_pattern_edit.has_value()) {
      deferred_pattern_edit->runtime_revision = runtime_revision;
    }
  }

  bool session_available() const noexcept {
    return project_id.has_value() && project_revision.has_value() &&
           retained_project_path.has_value() && writer_lease.has_value();
  }

  foundation::Result<facade::SequenceMutationResult> record_sequence_pad(
      domain::PadSlotId slot,
      std::uint8_t velocity,
      bool pressed) {
    if (!active_sequence.has_value() || !retained_project_path.has_value()) {
      return foundation::Result<facade::SequenceMutationResult>::failure(
          Error{ErrorCode::invalid_argument, "no Sequence session is active"});
    }
    const auto runtime_frame = engine.telemetry().rendered_frames;
    const auto input_sequence = active_sequence->next_input_sequence;
    auto recorded = application.record_sequence_event({
        *retained_project_path,
        active_sequence->id,
        facade::SequencePadEvent{
            slot, velocity, runtime_frame, input_sequence, pressed},
    });
    if (recorded.has_value()) {
      ++active_sequence->next_input_sequence;
    }
    return recorded;
  }

  foundation::Result<audio::PreparedPatternView> prepare_project_pattern(
      const foundation::PatternId& selected_pattern,
      std::span<const domain::PatternEvent> overlay = {}) {
    if (!retained_project_path.has_value()) {
      return foundation::Result<audio::PreparedPatternView>::failure(
          Error{ErrorCode::invalid_argument, "no Project is open"});
    }
    auto snapshot = application.prepare_runtime_snapshot({
        *retained_project_path,
        selected_pattern,
        limits,
    });
    if (!snapshot.has_value()) {
      return foundation::Result<audio::PreparedPatternView>::failure(
          snapshot.error());
    }
    auto pattern = overlay.empty()
        ? audio::PreparedPatternView::from_snapshot(*snapshot.value())
        : audio::PreparedPatternView::from_snapshot_with_overlay(
              *snapshot.value(), overlay);
    if (!pattern.has_value()) {
      return foundation::Result<audio::PreparedPatternView>::failure(
          pattern.error());
    }
    return pattern;
  }

  foundation::Result<audio::PatternPublication> publish_prepared_pattern(
      audio::PreparedPatternView&& pattern,
      std::optional<std::uint64_t> activation_frame = std::nullopt,
      std::optional<audio::PatternReplacementAuthority>
          replacement_authority = std::nullopt,
      bool immediate = false) {
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
    if (fail_next_pattern_publication) {
      fail_next_pattern_publication = false;
      return foundation::Result<audio::PatternPublication>::failure(Error{
          ErrorCode::invalid_argument,
          "injected runtime Pattern publication failure",
      });
    }
#endif
    static_cast<void>(engine.reclaim_retired_patterns());
    const auto publication = immediate
        ? engine.publish_pattern_view_immediate(std::move(pattern))
        : engine.publish_pattern_view(std::move(pattern), activation_frame,
              std::move(replacement_authority));
    if (publication.result != audio::PatternPublishResult::accepted) {
      return foundation::Result<audio::PatternPublication>::failure(Error{
          ErrorCode::invalid_argument,
          "runtime Pattern publication is unavailable",
      });
    }
    return foundation::Result<audio::PatternPublication>::success(publication);
  }

  foundation::Result<audio::PatternPublication> publish_project_pattern(
      const foundation::PatternId& selected_pattern,
      std::optional<std::uint64_t> activation_frame = std::nullopt,
      std::span<const domain::PatternEvent> overlay = {},
      std::optional<audio::PatternReplacementAuthority>
          replacement_authority = std::nullopt) {
    auto pattern = prepare_project_pattern(selected_pattern, overlay);
    if (!pattern.has_value()) {
      return foundation::Result<audio::PatternPublication>::failure(
          pattern.error());
    }
    return publish_prepared_pattern(
        std::move(pattern.value()),
        activation_frame,
        std::move(replacement_authority));
  }

  foundation::Result<audio::PatternPublication> publish_transport_pattern(
      audio::PreparedPatternView&& pattern, audio::PatternSwitchSnap snap,
      std::optional<audio::PatternReplacementAuthority> authority,
      std::optional<facade::PatternTransportSwitchTicket> recording_ticket = {}) {
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
    if (std::exchange(fail_next_pattern_publication, false)) {
      return foundation::Result<audio::PatternPublication>::failure(Error{
          ErrorCode::invalid_argument, "injected runtime Pattern publication failure"});
    }
#endif
    static_cast<void>(engine.reclaim_retired_patterns());
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
    testing::invoke_sequence_switch_publication_hook();
#endif
    if (recording_ticket) {
      if (!transport) return foundation::Result<audio::PatternPublication>::failure(
          Error{ErrorCode::internal_error, "Recording switch owner is absent"});
      auto cell = std::find_if(transport->recording_switches.begin(),
          transport->recording_switches.end(), [](const auto& c) { return !c; });
      if (cell == transport->recording_switches.end())
        return foundation::Result<audio::PatternPublication>::failure(Error{
            ErrorCode::invalid_argument, "Recording switch capacity is retained",
            {{"reason", "recording_switch_capacity"}}});
      const auto target = pattern.pattern_id();
      const auto bpm = pattern.bpm();
      auto retained = engine.publish_retained_pattern_switch_view(
          std::move(pattern), snap, std::move(authority));
      if (retained.publication.result != audio::PatternPublishResult::accepted)
        return foundation::Result<audio::PatternPublication>::failure(Error{
            ErrorCode::invalid_argument, "runtime Pattern publication is unavailable"});
      cell->emplace(RetainedRecordingSwitch{*recording_ticket, std::move(retained.lease)});
      if (!transport->controller->bind_pattern_switch(*recording_ticket,
              {retained.publication.generation, target, retained.publication.activation_frame}, bpm)) {
        // A broken internal binding cannot spend an accepted Native lease or
        // remove its unbound input barrier. Preserve both for failed disposal.
        trigger_admission = false;
        request_terminal_audio_retirement(true);
        state = State::failed;
        return foundation::Result<audio::PatternPublication>::failure(Error{
            ErrorCode::internal_error, "Accepted recording switch binding failed",
            {{"reason", "recording_switch_binding_failed"}, {"retained", true}}});
      }
      return foundation::Result<audio::PatternPublication>::success(retained.publication);
    }
    const auto publication = engine.publish_pattern_switch_view(
        std::move(pattern), snap, std::move(authority));
    if (publication.result != audio::PatternPublishResult::accepted) {
      return foundation::Result<audio::PatternPublication>::failure(Error{
          ErrorCode::invalid_argument, "runtime Pattern publication is unavailable"});
    }
    return foundation::Result<audio::PatternPublication>::success(publication);
  }

  // A grid edit changes only the current Pattern's events, so its view is
  // republished without a Bank. While the transport plays, the view swaps in
  // place: same origin, so playback neither restarts nor waits for a bar,
  // voices keep sounding and the cursor resumes at the first event not yet
  // scheduled. While stopped nothing plays, so it applies immediately and
  // leaves no pending publication to refuse the next Play. Each swap takes a
  // fresh Pattern slot; when every slot is held, the swap is deferred until
  // reclaim frees one, which only the transport service cadence can retry.
  EditedPatternPublication publish_edited_pattern(
      const foundation::PatternId& selected_pattern, bool playing) {
    deferred_pattern_edit.reset();
    auto pattern = prepare_project_pattern(selected_pattern);
    if (!pattern.has_value()) {
      return {std::nullopt, normalized_error(pattern.error()).at("error")};
    }
    static_cast<void>(engine.reclaim_retired_patterns());
    const auto telemetry = engine.pattern_telemetry();
    bool injected_rejection = false;
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
    // Stands in for an engine rejection other than full slots.
    injected_rejection = std::exchange(fail_next_pattern_publication, false);
#endif
    const auto publication = injected_rejection
        ? audio::PatternPublication{
              audio::PatternPublishResult::publish_queue_full, 0, 0}
        : playing
        ? engine.publish_pattern_view_preserving_phase(
              std::move(pattern.value()), telemetry.current_generation)
        : engine.publish_pattern_view_immediate(std::move(pattern.value()));
    if (publication.result == audio::PatternPublishResult::accepted) {
      return {publication, std::nullopt};
    }
    if (publication.result == audio::PatternPublishResult::pattern_slots_full &&
        transport != nullptr && project_id.has_value()) {
      deferred_pattern_edit = DeferredPatternEdit{
          *project_id, selected_pattern, telemetry.current_generation,
          telemetry.reclaimed_patterns, std::nullopt};
      return {std::nullopt, std::nullopt};
    }
    return {std::nullopt, host_error("HOST_STATE_INVALID",
        "runtime Pattern publication is unavailable",
        {{"reason", "pattern_publication_unavailable"}}).at("error")};
  }

  // Service cadence. Waits while the transport owns the next publication
  // and drops a deferral that another publication has superseded.
  void retry_deferred_pattern_edit() {
    // A replay holds the Pattern view; its end restores the selected one.
    if (!deferred_pattern_edit.has_value() || replay_holds_runtime()) {
      return;
    }
    const auto deferred = *deferred_pattern_edit;
    const auto telemetry = engine.pattern_telemetry();
    const auto current = engine.current_pattern_id();
    if (!session_available() || project_id != deferred.project_id ||
        pattern_id != deferred.pattern_id.value() || !current.has_value() ||
        *current != deferred.pattern_id ||
        telemetry.current_generation != deferred.expected_generation ||
        telemetry.pending_generation != 0) {
      deferred_pattern_edit.reset();
      return;
    }
    bool playing = false;
    if (transport != nullptr) {
      const auto status = transport->controller->inspect();
      if (status.recording ||
          status.phase != facade::PatternTransportPhase::idle ||
          status.error.has_value() || transport->publish_pending) {
        return;
      }
      playing = status.playing;
    }
    static_cast<void>(engine.reclaim_retired_patterns());
    if (engine.pattern_telemetry().reclaimed_patterns ==
        deferred.reclaimed_patterns) {
      return;
    }
    const auto published = publish_edited_pattern(deferred.pattern_id, playing);
    if (deferred_pattern_edit.has_value()) {
      deferred_pattern_edit->runtime_revision = deferred.runtime_revision;
    } else if (published.error.has_value() &&
               runtime_revision == deferred.runtime_revision) {
      // The Runtime no longer reflects the revision it claimed.
      runtime_revision.reset();
    }
  }

  std::optional<audio::PatternReplacementAuthority>
  pending_pattern_authority() const {
    const auto telemetry = engine.pattern_telemetry();
    const auto pending_pattern = engine.pending_pattern_id();
    if (telemetry.pending_generation == 0 || !pending_pattern.has_value()) {
      return std::nullopt;
    }
    return audio::PatternReplacementAuthority{
        telemetry.pending_generation,
        *pending_pattern,
        telemetry.pending_activation_frame,
    };
  }

  static audio::PatternReplacementAuthority replacement_authority(
      const PendingSequenceBoundary& boundary) {
    return audio::PatternReplacementAuthority{
        boundary.generation,
        boundary.pattern_id,
        boundary.runtime_frame,
    };
  }

  bool cancel_pending_switch(
      const audio::PatternReplacementAuthority& authority) {
    const auto telemetry = engine.pattern_telemetry();
    if (telemetry.current_generation == authority.generation) {
      return false;
    }
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
    testing::invoke_cancel_pending_switch_hook();
#endif
    const auto pending = pending_pattern_authority();
    if (!pending.has_value()) {
      // Exact replay after an earlier successful cancellation.
      return engine.pattern_telemetry().current_generation !=
          authority.generation;
    }
    if (pending->generation != authority.generation ||
        pending->pattern_id != authority.pattern_id ||
        pending->activation_frame != authority.activation_frame) {
      return false;
    }
    return engine.cancel_pattern_publication(authority);
  }

  foundation::Result<std::optional<audio::PatternPublication>>
  publish_pending_sequence_overlay(bool force = false) {
    if (!active_sequence.has_value() || !retained_project_path.has_value()) {
      return foundation::Result<std::optional<audio::PatternPublication>>::failure(
          Error{ErrorCode::invalid_argument, "no Sequence session is active"});
    }
    auto overlay = application.query_sequence_overlay({
        *retained_project_path,
        active_sequence->id,
    });
    if (!overlay.has_value()) {
      return foundation::Result<std::optional<audio::PatternPublication>>::failure(
          overlay.error());
    }
    if (!force && overlay.value().generation ==
        active_sequence->published_overlay_generation) {
      return foundation::Result<std::optional<audio::PatternPublication>>::success(
          std::nullopt);
    }
    if (pending_sequence_boundary.has_value()) {
      return foundation::Result<std::optional<audio::PatternPublication>>::success(
          std::nullopt);
    }
    auto published = publish_project_pattern(
        overlay.value().pattern_id,
        std::nullopt,
        overlay.value().events);
    if (!published.has_value()) {
      return foundation::Result<std::optional<audio::PatternPublication>>::failure(
          published.error());
    }
    active_sequence->published_overlay_generation = overlay.value().generation;
    return foundation::Result<std::optional<audio::PatternPublication>>::success(
        published.value());
  }

  foundation::Result<facade::SequenceMutationResult> stop_active_sequence() {
    if (!active_sequence.has_value() || !retained_project_path.has_value()) {
      return foundation::Result<facade::SequenceMutationResult>::failure(
          Error{ErrorCode::invalid_argument, "no Sequence session is active"});
    }
    const auto session_id = active_sequence->id;
    const auto pattern_id = active_sequence->pattern_id;
    auto stopped = application.stop_sequence({
        *retained_project_path,
        session_id,
        foundation::CommandId{generated_uuid()},
        engine.telemetry().rendered_frames,
    });
    if (!stopped.has_value()) {
      return stopped;
    }
    if (stopped.value().committed_revision.has_value()) {
      project_revision = *stopped.value().committed_revision;
      const auto authority = pending_sequence_boundary.has_value()
          ? std::optional<audio::PatternReplacementAuthority>{
                replacement_authority(*pending_sequence_boundary)}
          : std::nullopt;
      if (authority.has_value() && !cancel_pending_switch(*authority)) {
        stop_and_clear_pattern_noexcept();
        return foundation::Result<facade::SequenceMutationResult>::failure(
            Error{
                ErrorCode::invalid_argument,
                "runtime Pattern switch crossed the Stop boundary",
            });
      }
      auto published = publish_project_pattern(
          pattern_id,
          std::nullopt,
          {},
          std::nullopt);
      if (!published.has_value()) {
        return foundation::Result<facade::SequenceMutationResult>::failure(
            published.error());
      }
    }
    active_sequence.reset();
    pending_sequence_boundary.reset();
    return stopped;
  }

  // Enables the engine-side Pattern transport port while the Engine is
  // quiescent. Called on every successful Project create/open so a later
  // opt-in request never has to stop audio to arm the port.
  void enable_pattern_transport_quiescent() noexcept {
    if (engine.telemetry().state != audio::RealtimeState::stopped) {
      return;
    }
    if (has_pattern_input_owners()) return;
    if (next_transport_generation == 0 ||
        next_transport_generation == std::numeric_limits<std::uint64_t>::max()) {
      count_in_input_enabled = false;
      return;
    }
    if (engine.enable_pattern_transport(next_transport_generation)
            .has_value()) {
      enabled_transport_generation = next_transport_generation;
      ++next_transport_generation;
      count_in_input_enabled = false;
      if (count_in_input_negotiated &&
          engine.enable_scheduled_pattern_record(enabled_transport_generation)
              .has_value() &&
          engine.enable_pattern_input_profile(enabled_transport_generation)
              .has_value()) {
        count_in_input_enabled = true;
        initialize_pattern_input_ledger();
      }
    } else {
      count_in_input_enabled = false;
    }
  }

  bool has_pattern_input_owners() const noexcept {
    return std::any_of(pattern_inputs.begin(), pattern_inputs.end(), [](const auto& i) { return i.has_value(); }) ||
        std::any_of(pattern_holds.begin(), pattern_holds.end(), [](const auto& h) { return h.has_value(); });
  }
  void initialize_pattern_input_ledger() {
    const auto native = engine.pattern_input_profile_status();
    if (!native.enabled || has_pattern_input_owners()) return;
    if (input_ledger_generation != native.runtime_generation) {
      input_acceptance_floor = 0;
      input_ledger_generation = native.runtime_generation;
    }
    pattern_inputs.resize(2 * native.capacity);
    pattern_holds.resize(native.capacity);
  }
  void service_pattern_inputs() {
    for (auto& cell : pattern_inputs) {
      if (!cell) continue;
      auto& input = *cell;
      if (!input.completion) {
        const auto completion = engine.inspect_pattern_input_completion(
            input.ticket.runtime_generation, input.frame_epoch, input.admission.sequence);
        if (!completion) continue;
        input.completion = completion;
        if (input.facade_ticket && (!transport ||
            !transport->controller->complete_input(*completion))) {
          input.error = Error{ErrorCode::internal_error, "Pattern input completion owner mismatch"};
          continue; // Accepted resources stay retained on this failure.
        }
      }
      if (input.facade_ticket) {
        const auto status = transport->controller->inspect_input(*input.facade_ticket);
        if (!status) continue;
        input.durable_settled = status->durable_settled;
        input.retained = status->retained;
        input.complete = status->complete;
        input.error = status->error;
      } else {
        // This input was accepted before a real session engaged, or releases
        // that original owner. It never invents a Journal/controller binding.
        input.durable_settled = true;
        input.complete = true;
        if (input.completion->disposition == audio::PatternInputDisposition::voice_capacity ||
            input.completion->disposition == audio::PatternInputDisposition::invalidated_before_consume)
          input.error = Error{ErrorCode::invalid_argument, "Accepted live input failed at native consumption"};
      }
    }
  }

  bool acknowledge_pattern_input_owner_quiescent(std::uint64_t generation) {
    service_terminal_audio_retirement();
    auto native = engine.pattern_input_profile_status();
    if (!generation || generation != input_ledger_generation ||
        input_owner_acknowledged_generation == generation || !native.enabled ||
        native.runtime_generation != generation ||
        engine.telemetry().state != audio::RealtimeState::stopped) return false;
    bool needs_resource_disposition = false;
    if (transport) {
      auto& engagement = *transport;
      if (engagement.generation != generation || engagement.publish_pending) return false;
      if (!engagement.shutdown_requested) {
        engagement.controller->request_shutdown();
        engagement.shutdown_requested = true;
        if (!engagement.count_in_ticket_consumed) engagement.count_in_cancel_pending = true;
      }
      static_cast<void>(transport_continuation_step());
      const auto owner = engagement.controller->inspect_input_owner();
      if (!owner.invalidated) {
        if (state != State::failed || owner.pending) return false;
        needs_resource_disposition = true;
      }
      // Actual failed authoring ownership remains observable after resources
      // settle. This never enters the ordinary successful lifecycle barrier.
      trigger_admission = false;
      state = State::failed;
      if (owner.runtime_generation != generation || (owner.invalidated && !owner.disposed) || owner.pending ||
          owner.acknowledged || engagement.legacy_candidate) return false;
    } else if (state != State::failed) return false;
    service_pattern_inputs();
    if (has_recording_switches() || !legacy_inputs.empty() || std::any_of(pattern_inputs.begin(), pattern_inputs.end(),
        [](const auto& i) { return i.has_value(); })) return false;
    std::size_t physical_holds = 0, facade_holds = 0;
    const auto epoch = engine.telemetry().start_epoch;
    for (const auto& h : pattern_holds) if (h) {
      if (h->generation != generation || h->frame_epoch != epoch || h->release_submitted) return false;
      ++physical_holds;
      facade_holds += h->facade_owned;
    }
    if (transport && transport->controller->inspect_input_owner().held_correlations != facade_holds)
      return false;
    native = engine.pattern_input_profile_status();
    if (native.ordinary_pending || native.retained_completions ||
        (input_owner_revoked_generation != generation && native.held_release_reservations != physical_holds))
      return false;
    if (input_owner_revoked_generation != generation) {
      // A terminal operational Result remains failed even after real callback
      // retirement. Only the separate physical fence authorizes revocation;
      // stopped telemetry, silence and a timeout are not that proof.
      const auto drained = physical_audio
          ? physical_audio->physically_quiescent(physical_audio->context)
          : coordinator && coordinator->await_quiescent(
                coordinator->context, 1).has_value();
      if (!drained || terminal_native_stop_pending ||
          engine.telemetry().state != audio::RealtimeState::stopped ||
          !engine.revoke_pattern_input_holds_quiescent(generation)) return false;
      input_owner_revoked_generation = generation; // Actual Native operation receipt.
    }
    native = engine.pattern_input_profile_status();
    if (engine.telemetry().state != audio::RealtimeState::stopped ||
        native.runtime_generation != generation || native.ordinary_pending ||
        native.held_release_reservations || native.retained_completions ||
        !engine.scheduled_pattern_record_quiescent()) return false;
    if (transport && needs_resource_disposition) {
      if (facade_holds == 0) {
        // These holds belonged to the live-only Host before this controller
        // engaged. Its later session never acquires their correlation or a
        // fictional Journal. Actual worker retirement proves it owns no work.
        if (!transport->controller->shutdown_complete()) return false;
      } else {
        // The same I/O owner proves absence/disposition after Native revocation:
        // either the actual live-only input identity or its retained whole real
        // closing request/F, never an invented recording or closing authority.
        static_cast<void>(transport->controller->request_input_owner_disposition(generation));
        return false;
      }
    }
    if (transport && !needs_resource_disposition &&
        !transport->controller->acknowledge_input_owner(generation)) return false;
    for (auto& h : pattern_holds) h.reset();
    input_owner_acknowledged_generation = generation;
    return true;
  }

  Json request_pattern_input(const Json& payload) {
    const auto command = uuid_field(payload, "command_id");
    const auto generation = nonzero_decimal_field(payload, "runtime_generation");
    const auto epoch = nonzero_decimal_field(payload, "frame_epoch");
    const auto serial = nonzero_decimal_field(payload, "input_serial");
    const auto slot = safe_unsigned_field(payload, "slot", 63);
    const auto velocity = safe_unsigned_field(payload, "velocity", 127);
    const auto kind = string_field(payload, "kind");
    const auto held = bool_field(payload, "held");
    require(kind == "press" || kind == "release");
    const bool release = kind == "release";
    require(release ? velocity == 0 && held : velocity != 0 && payload.at("held_press_sequence").is_null());
    const auto correlation = release ? nonzero_decimal_field(payload, "held_press_sequence") : 0;
    // Exact replay is resolved before current-state admission: an interruption
    // does not erase an accepted operation or authorize a second enqueue.
    for (const auto& cell : pattern_inputs) if (cell &&
        (cell->ticket.command_id.value() == command || cell->ticket.ticket == serial)) {
      if (cell->original_request != payload) return state_error("Pattern input replay changed its identity or payload");
      service_pattern_inputs();
      return success({{"ticket", pattern_input_ticket_json(*cell)},
          {"status", pattern_input_status_json(*cell, clock_now())}});
    }
    const bool retained_release = release && state == State::failed;
    if (!count_in_input_enabled || (state != State::running && !retained_release) ||
        (!trigger_admission && !retained_release) ||
        active_sequence || generation != enabled_transport_generation ||
        epoch != engine.telemetry().start_epoch || generation != input_ledger_generation)
      return state_error("Pattern input profile is unavailable or stale");
    if (serial <= input_acceptance_floor || input_acceptance_floor == UINT64_MAX)
      return state_error("Pattern input serial is stale, consumed or exhausted");
    auto future_releases = static_cast<std::uint64_t>(std::count_if(pattern_holds.begin(), pattern_holds.end(),
        [](const auto& h) { return h && !h->release_submitted; }));
    if (release && future_releases) --future_releases;
    else if (!release && held) ++future_releases;
    if (serial > UINT64_MAX - future_releases)
      return state_error("Pattern input serial cannot preserve existing physical release identities");
    const auto n = pattern_holds.size();
    std::optional<std::size_t> index, hold_index;
    if (release) {
      for (std::size_t h = 0; h < n; ++h) if (pattern_holds[h] &&
          pattern_holds[h]->sequence == correlation && pattern_holds[h]->generation == generation &&
          pattern_holds[h]->frame_epoch == epoch && pattern_holds[h]->slot == slot &&
          !pattern_holds[h]->release_submitted) { hold_index = h; index = n + h; break; }
      if (!index || pattern_inputs[*index]) return state_error("Pattern release has no matching physical hold");
    } else {
      for (std::size_t i = 0; i < n; ++i) if (!pattern_inputs[i]) { index = i; break; }
      if (held) for (std::size_t h = 0; h < n; ++h) if (!pattern_holds[h]) { hold_index = h; break; }
      if (!index || (held && !hold_index)) return state_error("Pattern input retained metadata is full");
    }
    const bool facade_owned = release ? pattern_holds[*hold_index]->facade_owned : transport != nullptr;
    std::optional<facade::PatternTransportInputTicket> reserved;
    const auto frame = engine.telemetry().rendered_frames;
    require(frame <= kMaximumSafeInteger);
    if (facade_owned) {
      if (!transport) return state_error("Pattern input lost its original Facade owner");
      const auto result = transport->controller->reserve_input({foundation::CommandId{command},
          generation, epoch, frame, {static_cast<std::uint8_t>(slot / 16), static_cast<std::uint8_t>(slot % 16)},
          !release, static_cast<std::uint8_t>(velocity), correlation, held});
      if (!result.has_value()) return normalized_error(result.error());
      reserved = result.value();
    }
    // Host ticket and future release storage is allocated before acceptance;
    // native enqueue itself reserves its physical FIFO/completion/hold credits.
    const auto original_started = request_deadline.value_or(
        clock_now() + facade::kPatternTransportInputDeadline) - facade::kPatternTransportInputDeadline;
    pattern_inputs[*index].emplace(RetainedPatternInput{payload,
        {generation, foundation::CommandId{command}, serial}, epoch, {}, reserved, {}, original_started,
        false, false, false, {}});
    if (!release && held) pattern_holds[*hold_index] = RetainedPatternHold{0, generation, epoch,
        static_cast<std::uint8_t>(slot), facade_owned, false};
    const auto admission = engine.enqueue_pattern_input({generation, epoch, static_cast<std::uint8_t>(slot),
        static_cast<std::uint8_t>(velocity), release, correlation, held, {}});
    if (admission.result != audio::PatternInputSubmit::accepted) {
      if (reserved) static_cast<void>(transport->controller->abandon_input(*reserved));
      pattern_inputs[*index].reset();
      if (!release && held) pattern_holds[*hold_index].reset();
      return state_error("Pattern input Native admission refused");
    }
    input_acceptance_floor = serial; // Refused pre-enqueue operations do not advance it.
    auto& input = *pattern_inputs[*index];
    input.admission = admission;
    if (hold_index) {
      if (release) pattern_holds[*hold_index]->release_submitted = true;
      else pattern_holds[*hold_index]->sequence = admission.sequence;
    }
    if (reserved && !transport->controller->bind_input(*reserved, admission))
      input.error = Error{ErrorCode::internal_error, "Accepted Pattern input metadata binding failed"};
    service_pattern_inputs();
    return success({{"ticket", pattern_input_ticket_json(input)},
        {"status", pattern_input_status_json(input, clock_now())}});
  }

  Json inspect_pattern_input(const Json& payload) {
    const auto command = uuid_field(payload, "command_id");
    const auto generation = nonzero_decimal_field(payload, "runtime_generation");
    const auto epoch = nonzero_decimal_field(payload, "frame_epoch");
    const auto serial = nonzero_decimal_field(payload, "ticket");
    const auto consume = bool_field(payload, "consume");
    service_pattern_inputs();
    if (transport) static_cast<void>(transport_continuation_step());
    service_pattern_inputs();
    for (auto& cell : pattern_inputs) if (cell && cell->ticket.ticket == serial &&
        cell->ticket.command_id.value() == command && cell->ticket.runtime_generation == generation &&
        cell->frame_epoch == epoch) {
      auto result = pattern_input_status_json(*cell, clock_now());
      if (consume) {
        if (!cell->complete || !cell->durable_settled || !cell->completion)
          return state_error("Pattern input evidence is still pending");
        if (cell->facade_ticket && !transport->controller->consume_input(*cell->facade_ticket))
          return state_error("Pattern input Facade consumption refused");
        if (!engine.consume_pattern_input_completion(generation, epoch, cell->admission.sequence))
          throw std::logic_error("Pattern input Native consumption refused after reconciliation");
        if (cell->original_request.at("kind") == "release") {
          const auto press = cell->completion->held_press_sequence;
          for (auto& h : pattern_holds) if (h && h->sequence == press) { h.reset(); break; }
        }
        cell.reset(); // A press leaves its independent future release intact.
      }
      return success(std::move(result));
    }
    return state_error("Pattern input ticket is stale or consumed");
  }

  // Engages the global transport session on first use. Returns nullptr when
  // the session cannot own the transport (no open Project, no armed
  // generation, or another session owns the engagement).
  TransportEngagement* ensure_transport_engaged(
      const foundation::SequenceSessionId& session_id) {
    if (transport != nullptr) {
      return transport->session == session_id ? transport.get() : nullptr;
    }
    if (!session_available() || !pattern_id.has_value() ||
        enabled_transport_generation == 0) {
      return nullptr;
    }
    auto engagement = std::make_unique<TransportEngagement>(engine);
    engagement->session = session_id;
    engagement->generation = enabled_transport_generation;
    engagement->pattern = foundation::PatternId{*pattern_id};
    // Wire the coordinator's overlay publication capability to this Impl's
    // prepare-and-publish path (#1513). `this` is stable for the engagement's
    // lifetime: the engagement is owned by the Impl and both die together.
    engagement->port.bind_overlay_publication(
        [this](const foundation::PatternId& selected,
               std::span<const domain::PatternEvent> events) {
          return publish_project_pattern(
              selected, std::nullopt, events);
        });
    const facade::PatternTransportControllerConfig config{
            *retained_project_path,
            session_id,
            foundation::ProjectId{*project_id},
            foundation::PatternId{*pattern_id},
            enabled_transport_generation,
        };
    engagement->controller = count_in_input_enabled
        ? application.make_pattern_transport_controller(
            engagement->port, engagement->scheduled_port, config)
        : application.make_pattern_transport_controller(engagement->port, config);
    transport = std::move(engagement);
    return transport.get();
  }

  // Routes an accepted live input into the transport admission journal at the
  // existing post-enqueue point. The enqueue outcome is already decided; a
  // journaling failure is reported to the caller exactly like the legacy
  // post-enqueue append failure, and an unknown enqueue never reaches here.
  foundation::Result<void> admit_transport_pad(
      domain::PadSlotId slot,
      std::uint8_t velocity,
      bool pressed, Json accepted_response) {
    auto& engagement = *transport;
    if (engagement.legacy_candidate) {
      return foundation::Result<void>::failure(Error{ErrorCode::io_error,
          "An original Pattern input is still pending",
          {{"pending", true}, {"reason", "pattern_transport_metadata_full"}}});
    }
    const auto watermark = engagement.next_watermark;
    auto correlation = watermark;
    if (pressed) {
      // Native already accepted the physical press. Pending or failed I/O
      // cannot erase its original correlation/held ownership.
      engagement.owned_presses[slot] = watermark;
    } else if (const auto found = engagement.owned_presses.find(slot);
               found != engagement.owned_presses.end()) {
      correlation = found->second;
    }
    const facade::PatternTransportCandidate candidate{
        watermark,
        engine.telemetry().rendered_frames,
        slot,
        pressed,
        velocity,
        correlation,
    };
    engagement.legacy_candidate = candidate;
    const auto original_id = current_rpc_request_id.value_or(generated_uuid());
    engagement.legacy_request_id = original_id;
    legacy_inputs.emplace(original_id, RetainedLegacyInput{std::move(accepted_response), {},
        *request_deadline, false});
    const auto result = resume_legacy_transport_pad();
    if (!result.has_value() && result.error().details.value("pending", false)) {
      auto error = result.error();
      error.details["legacy_ticket"] = original_id;
      return foundation::Result<void>::failure(std::move(error));
    }
    legacy_inputs.erase(original_id);
    return result;
  }

  foundation::Result<void> resume_legacy_transport_pad() {
    auto& engagement = *transport;
    if (!engagement.legacy_candidate) return foundation::Result<void>::success();
    const auto candidate = *engagement.legacy_candidate;
    const auto admitted = engagement.controller->admit(candidate);
    if (!admitted.has_value()) {
      if (!admitted.error().details.value("pending", false)) {
        // A terminal refusal still retires this original watermark once.
        ++engagement.next_watermark;
        engagement.legacy_candidate.reset();
        if (engagement.legacy_request_id) {
          auto& original = legacy_inputs.at(*engagement.legacy_request_id);
          original.terminal_response = normalized_error(admitted.error());
          if (original.observer_consumed) legacy_inputs.erase(*engagement.legacy_request_id);
          engagement.legacy_request_id.reset();
        }
      }
      return foundation::Result<void>::failure(admitted.error());
    }
    if (candidate.pressed) engagement.owned_presses[candidate.slot] = candidate.correlation;
    else engagement.owned_presses.erase(candidate.slot);
    ++engagement.next_watermark;
    engagement.legacy_candidate.reset();
    if (engagement.legacy_request_id) {
      auto& original = legacy_inputs.at(*engagement.legacy_request_id);
      original.terminal_response = original.accepted_response;
      if (original.observer_consumed) legacy_inputs.erase(*engagement.legacy_request_id);
      engagement.legacy_request_id.reset();
    }
    return foundation::Result<void>::success();
  }

  // One bounded continuation step: drives the controller once, then, when a
  // recording close has just settled durably, arms the separate publication
  // completion. Never waits for an audio receipt or a long IO job.
  foundation::Result<void> transport_continuation_step() {
    observe_recording_switches();
    service_pattern_inputs();
    auto& engagement = *transport;
    if (engagement.publish_pending) {
      const auto inspected = application.query({
          {"operation", "project.inspect"},
          {"project_path", retained_project_path->generic_string()},
      });
      if (inspected.value("ok", false)) {
        project_revision =
            inspected.at("project_revision").get<std::uint64_t>();
      }
      // A count-in/input inspection can finish close without an ordinary
      // selection poll. F has settled every switch: use the actual terminal
      // Native Pattern, never cached selection or original count-in e1/e2.
      const auto current = engine.current_pattern_id();
      if (!current) return foundation::Result<void>::failure(
          Error{ErrorCode::io_error, "Terminal Pattern is not observed"});
      retarget_transport_selection(*current);
      auto pattern = prepare_project_pattern(*current);
      if (!pattern.has_value()) return foundation::Result<void>::failure(pattern.error());
      // A stopped transport must not retain a Bar-delayed close view that
      // blocks the next Play. Record-off while playing keeps its old policy.
      auto published = publish_prepared_pattern(std::move(pattern.value()), {}, {},
          !engagement.controller->inspect().playing);
      if (!published.has_value()) {
        // Keep the completion outstanding so the next step retries the same
        // publication; the journal settlement it follows is already durable.
        return foundation::Result<void>::failure(published.error());
      }
      engagement.publish_pending = false;
      return foundation::Result<void>::success();
    }
    const auto was_recording = engagement.controller->inspect().recording;
    auto stepped = engagement.controller->continue_operation();
    observe_recording_switches();
    if (engagement.legacy_candidate) static_cast<void>(resume_legacy_transport_pad());
    if (!stepped.has_value()) {
      return stepped;
    }
    const auto after = engagement.controller->inspect();
    if (was_recording && !after.recording &&
        after.phase == facade::PatternTransportPhase::idle &&
        !after.error.has_value()) {
      engagement.publish_pending = true;
    }
    return foundation::Result<void>::success();
  }

  static audio::PatternReplacementAuthority transport_switch_authority(
      const PendingTransportSwitch& record) {
    return {record.generation, record.pattern_id, record.activation_frame};
  }

  static bool same_switch_authority(
      const audio::PatternReplacementAuthority& a,
      const audio::PatternReplacementAuthority& b) {
    return a.generation == b.generation && a.pattern_id == b.pattern_id &&
        a.activation_frame == b.activation_frame;
  }

  bool has_recording_switches() const {
    return transport && std::any_of(transport->recording_switches.begin(),
        transport->recording_switches.end(), [](const auto& cell) { return cell.has_value(); });
  }

  // Every actual S survives the latest-only selection record through the
  // worker ACK. In particular B is still observable after audio applies C in
  // the same callback. No Engine or lease crosses the I/O boundary.
  void observe_recording_switches() {
    if (!transport) return;
    auto& engagement = *transport;
    for (auto& cell : engagement.recording_switches) {
      if (!cell) continue;
      auto status = engagement.controller->inspect_pattern_switch(cell->ticket);
      if (!status) continue; // Unexpected owner loss never frees an accepted pin.
      if (!status->complete && status->publication) {
        const auto observed = engine.observe_pattern_publication(cell->lease);
        if (!observed) continue;
        if (!engagement.controller->complete_pattern_switch(cell->ticket, *observed)) {
          trigger_admission = false;
          request_terminal_audio_retirement(true);
          state = State::failed;
          continue;
        }
        status = engagement.controller->inspect_pattern_switch(cell->ticket);
      }
      if (status && status->complete) {
        // Resource completion includes actual Native final fate plus durable
        // ACK or real failed owner disposition; it does not mean take success.
        cell->lease = {};
        if (engagement.controller->consume_pattern_switch(cell->ticket)) cell.reset();
      }
    }
  }

  static bool authority_pending(const audio::PatternTransportObservation& state,
      const audio::PatternReplacementAuthority& authority) {
    return std::any_of(state.pending_switches.begin(), state.pending_switches.end(),
        [&](const auto& pending) {
          return pending && same_switch_authority(*pending, authority);
        });
  }

  bool owns_transport_switch(const audio::PatternReplacementAuthority& authority) const {
    if (transport) for (const auto& cell : transport->recording_switches) if (cell) {
      const auto status = transport->controller->inspect_pattern_switch(cell->ticket);
      if (status && status->publication && same_switch_authority(*status->publication, authority))
        return true;
    }
    if (!pending_transport_switch) return false;
    const auto& record = *pending_transport_switch;
    if (same_switch_authority(authority, transport_switch_authority(record))) return true;
    return std::any_of(record.predecessors.begin(), record.predecessors.end(),
        [&](const auto& predecessor) {
          return predecessor && same_switch_authority(authority, predecessor->authority);
        });
  }

  Json current_pattern_id_json() const {
    const auto current = engine.current_pattern_id();
    return current.has_value() ? Json(current->value()) : Json(nullptr);
  }

  Json pending_transport_switch_json() const {
    if (!pending_transport_switch) return nullptr;
    return {{"pattern_id", pending_transport_switch->pattern_id.value()},
        {"activation_frame", pending_transport_switch->activation_frame}};
  }

  bool foreign_pattern_publication_pending(bool allow_recording_overlay = false) const {
    if (deferred_pattern_edit) return true;
    const auto state = engine.pattern_transport_observation();
    if (!state || state->outstanding_cancellation) return true;
    return std::any_of(state->pending_switches.begin(), state->pending_switches.end(),
        [&](const auto& pending) { return pending && !owns_transport_switch(*pending) &&
            !(allow_recording_overlay && transport && transport->port.owns_overlay(*pending)); });
  }

  void retarget_transport_selection(const foundation::PatternId& applied) {
    pattern_id = applied.value();
    if (transport != nullptr) transport->pattern = applied;
  }

  // Follow the exact current generation, including B becoming current while
  // C remains queued. Publication and both apply points belong to native
  // audio; observing here never secretly publishes a cadence-dependent C.
  void observe_transport_switch() {
    observe_recording_switches();
    if (!pending_transport_switch) return;
    const auto state = engine.pattern_transport_observation();
    if (!state) return; // Bounded read raced audio; retain authorities and retry.
    const auto& record = *pending_transport_switch;
    if (state->current_pattern) retarget_transport_selection(*state->current_pattern);
    if (state->current_generation == record.generation ||
        !authority_pending(*state, transport_switch_authority(record))) {
      pending_transport_switch.reset();
    }
  }

  bool transport_switch_pending() {
    observe_transport_switch();
    return pending_transport_switch.has_value();
  }

  // A press of the currently playing Pattern withdraws every still-live
  // authority in this Host's chain, including B audio-owned and C in Q.
  bool withdraw_transport_switch() {
    if (!pending_transport_switch) return true;
    const auto state = engine.pattern_transport_observation();
    if (!state) return false;
    auto& record = *pending_transport_switch;
    if (authority_pending(*state, transport_switch_authority(record)) &&
        !engine.cancel_pattern_publication(transport_switch_authority(record))) return false;
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
    testing::invoke_cancel_pending_switch_hook();
#endif
    for (const auto& predecessor : record.predecessors) {
      if (predecessor && authority_pending(*state, predecessor->authority) &&
          !engine.cancel_pattern_publication(predecessor->authority)) {
        record = PendingTransportSwitch{predecessor->authority.pattern_id,
            predecessor->authority.activation_frame, predecessor->authority.generation,
            predecessor->snap, {}};
        return false;
      }
    }
    pending_transport_switch.reset();
    return true;
  }

  // The lifecycle barrier shared by Suspend, Project replacement and Close:
  // acknowledged Pattern Stop, admission closure and journal settlement must
  // complete before the lifecycle effect. A receipt that never arrives or a
  // settlement refusal is an unknown closure and fails the caller rather than
  // claiming a clean replacement.
  foundation::Result<void> transport_shutdown_barrier(bool retire = true) {
    service_pattern_inputs();
    if (transport == nullptr && has_pattern_input_owners()) {
      return foundation::Result<void>::failure(Error{ErrorCode::io_error,
          "Accepted Pattern inputs or physical holds are still owned",
          {{"pending", true}, {"reason", "pattern_transport_input_owners_pending"}}});
    }
    if (transport == nullptr) {
      return foundation::Result<void>::success();
    }
    auto& engagement = *transport;
    if (retire && !engagement.shutdown_requested) {
      // The Facade submits a genuine Stop/cancel and drains its sole I/O
      // owner. This call never joins; later short turns observe stopped.
      engagement.controller->request_shutdown();
      engagement.shutdown_requested = true;
      if (!engagement.count_in_ticket_consumed)
        engagement.count_in_cancel_pending = true;
    }
    const auto stepped = transport_continuation_step();
    const auto status = engagement.controller->inspect();
    if (status.error) return foundation::Result<void>::failure(*status.error);
    if (!stepped.has_value() && !stepped.error().details.value("pending", false)) return stepped;
    const auto ingress = engagement.controller->inspect_ingress();
    if (status.phase != facade::PatternTransportPhase::idle || status.recording ||
        engagement.publish_pending || engagement.legacy_candidate ||
        has_pattern_input_owners() || has_recording_switches() ||
        ingress.ordinary_pending || ingress.held_release_metadata || ingress.retained_tickets ||
        (retire && (!engagement.controller->shutdown_complete() ||
            !engagement.count_in_ticket_consumed))) {
      return foundation::Result<void>::failure(Error{ErrorCode::io_error,
          "Pattern transport shutdown is pending",
          {{"pending", true}, {"reason", "pattern_transport_shutdown_pending"}}});
    }
    return foundation::Result<void>::success();
  }

  std::chrono::steady_clock::time_point clock_now() const noexcept {
    return clock.has_value() ? clock->now(clock->context)
                             : std::chrono::steady_clock::now();
  }

  void abort_tracked_sample_import(const Json& payload) noexcept {
    std::string token;
    try {
      if (!payload.is_object() || !payload.contains("import_token") ||
          !payload.at("import_token").is_string()) {
        return;
      }
      token = payload.at("import_token").get<std::string>();
    } catch (...) {
      return;
    }
    if (!sample_import_tokens.contains(token)) {
      return;
    }
    try {
      static_cast<void>(application.abort_sample_import(token));
    } catch (...) {
    }
    sample_import_tokens.erase(token);
    sample_import_slots.erase(token);
  }

  bool request_cancelled() const noexcept {
    return request_deadline.has_value() &&
           clock_now() >= *request_deadline;
  }

  bool publication_settlement_owned() const noexcept {
    return request_publication_settlement_owned != nullptr &&
           request_publication_settlement_owned(
               request_publication_context);
  }

  std::uint32_t remaining_request_budget_ms() const noexcept {
    if (!request_deadline.has_value()) {
      return 0;
    }
    const auto now = clock_now();
    if (now >= *request_deadline) {
      return 0;
    }
    const auto remaining = *request_deadline - now;
    auto rounded = std::chrono::duration_cast<std::chrono::milliseconds>(
        remaining);
    if (rounded < remaining) {
      rounded += std::chrono::milliseconds(1);
    }
    return static_cast<std::uint32_t>(std::min<std::int64_t>(
        rounded.count(),
        std::numeric_limits<std::uint32_t>::max()));
  }

  std::uint32_t legacy_retirement_budget_ms() const noexcept {
    const auto deadline = terminal_origin_deadline.has_value()
        ? terminal_origin_deadline : request_deadline;
    // The existing standalone legacy cleanup turn has a one-ms receipt
    // budget. A cleared dispatch deadline never replaces a retained origin.
    if (!deadline.has_value()) return 1;
    const auto now = clock_now();
    if (now >= *deadline) return 0;
    const auto remaining = *deadline - now;
    auto rounded = std::chrono::duration_cast<std::chrono::milliseconds>(remaining);
    if (rounded < remaining) rounded += std::chrono::milliseconds(1);
    return static_cast<std::uint32_t>(std::min<std::int64_t>(
        rounded.count(), std::numeric_limits<std::uint32_t>::max()));
  }

  Json status() const {
    const auto bank = engine.bank_telemetry();
    const auto acknowledged_generation =
        coordinator.has_value() &&
                coordinator->acknowledged_generation != nullptr
            ? coordinator->acknowledged_generation(coordinator->context)
            : 0;
    const auto audio_running =
        engine.telemetry().state == audio::RealtimeState::running;
    const auto generation_visible =
        runtime_ready && project_id.has_value() &&
        runtime_bank_project_id == project_id &&
        bank.accepted_publications != 0;
    return success({
        {"state", state_name()},
        {"project_id",
         project_id.has_value() ? Json(*project_id) : Json(nullptr)},
        {"project_revision",
         project_revision.has_value() ? Json(*project_revision)
                                      : Json(nullptr)},
        {"pattern_id",
         pattern_id.has_value() ? Json(*pattern_id) : Json(nullptr)},
        {"runtime_ready", runtime_ready},
        {"control_generation",
         generation_visible ? Json(bank.accepted_publications)
                            : Json(nullptr)},
        {"acknowledged_generation",
         generation_visible && acknowledged_generation != 0
             ? Json(acknowledged_generation)
             : Json(nullptr)},
        {"limits",
         {
             {"maximum_artifact_bytes", limits.maximum_artifact_bytes},
             {"maximum_user_bank_bytes", limits.maximum_user_bank_bytes},
             {"maximum_generation_bytes", limits.maximum_generation_bytes},
             {"maximum_resident_bytes", limits.maximum_resident_bytes},
         }},
        {"audio_state", audio_running ? "running" : "stopped"},
        {"capture_state",
         capture_state_name(engine.capture_telemetry().state)},
        {"pattern_transport",
         transport != nullptr
             ? pattern_transport_status_json(
                   true,
                   transport->controller->inspect(),
                   transport->publish_pending,
                   engine.telemetry().rendered_frames,
                   current_pattern_id_json(),
                   pending_transport_switch_json())
             : Json(nullptr)},
    });
  }

  std::string state_name() const {
    switch (state) {
      case State::core_ready:
        return "core-ready";
      case State::running:
        return "running";
      case State::audio_suspended:
        return "audio-suspended";
      case State::closed:
        return "closed";
      case State::failed:
        return "failed";
    }
    return "failed";
  }

  Json facade_command(Json request) {
    const auto response = application.command(request);
    if (!response.value("ok", false)) {
      return normalized_facade_error(response);
    }
    return normalized_facade_success(response);
  }

  Json facade_query(Json request) {
    const auto response = application.query(request);
    if (!response.value("ok", false)) {
      return normalized_facade_error(response);
    }
    return normalized_facade_success(response);
  }

  foundation::Result<cooker::ResolvedPlayback> resolve_preview_playback(
      const facade::SampleInspectResult& inspected,
      const domain::PadPlayback& playback) {
    // One resolution for cooking and previewing, so a preview plays exactly
    // what a cooked Pad would, voice DSP block included.
    return facade::resolve_sample_preview_playback(inspected, playback);
  }

  // #799. Publish the audition PCM the Facade decoded into the engine's
  // reserved audition pool and start a voice on it. Best effort by design: see
  // the call site for why a failure here is not an error on a query.
  //
  // Returns whether a voice was actually started, so the call site can say so.
  // Every `false` below is a real silence, and the two that a caller meets in
  // practice are the last two: the pool holds two Banks and nothing in this
  // Host reclaims them, and `enqueue_control` refuses every audition while the
  // engine is stopped -- which is the whole life of a Host that has published
  // a snapshot but never run `audio.activate`.
  [[nodiscard]] bool play_audition(const Json& payload) {
    facade::SoundSetAuditionRequest request{
        payload.at("set_id").get<std::string>(),
        payload.at("version").get<std::string>(),
        payload.at("manifest_sha256").get<std::string>(),
        std::nullopt,
    };
    if (payload.contains("slot_index")) {
      request.slot_index = static_cast<std::uint8_t>(
          payload.at("slot_index").get<std::uint64_t>());
    }
    const auto audio = application.audition_soundset(request);
    if (!audio.has_value()) {
      // The Facade already refused this request through the envelope the
      // caller is about to receive; there is nothing further to report.
      //
      // Unreachable from the call site rather than merely unlikely: the same
      // `audition_soundset` answered the JSON query a few lines above it, and
      // this branch is only reached when that answer was `ok`. Kept as the
      // contract check it is, and deliberately not counted as covered.
      return false;
    }
    return publish_audition_pcm(audio.value().prepared);
  }

  [[nodiscard]] bool publish_audition_pcm(const std::shared_ptr<const cooker::PcmSample>& prepared) {
    if (!prepared) return false;
    const auto& source = *prepared;
    if ((source.channels != 1 && source.channels != 2) || source.interleaved.empty() ||
        source.interleaved.size() % source.channels != 0) {
      // Also unreachable through the Facade: `prepared_audition` refuses this
      // exact shape with `cook_failed` before it can return success.
      return false;
    }
    // Down-mix to the mono float the Bank stores, exactly as
    // `PreparedSampleBank::from_snapshot` does for a Project Pad.
    std::vector<float> mono;
    mono.reserve(source.interleaved.size() / source.channels);
    for (std::size_t frame = 0; frame < source.interleaved.size();
         frame += source.channels) {
      if (source.channels == 1) {
        mono.push_back(audio::prepared_pcm16_to_float(
            source.interleaved[frame]));
      } else {
        mono.push_back(
            (audio::prepared_pcm16_to_float(source.interleaved[frame]) +
             audio::prepared_pcm16_to_float(source.interleaved[frame + 1])) *
            0.5F);
      }
    }
    auto bank = audio::PreparedSampleBank::empty(
        audio::kAuditionBankProjectId(),
        audio::kAuditionBankProjectRevision);
    if (!bank.set_sample(audio::kAuditionSampleSlot, mono).has_value()) {
      // Unreachable for the same reason: `mono` is non-empty because `source`
      // was, slot 0 is in range and unset on a fresh Bank, and a sample decoded
      // from PCM16 is finite.
      return false;
    }
    if (engine.publish_audition_bank(std::move(bank)) !=
        audio::PublishResult::accepted) {
      // Both audition slots are still draining an earlier preview. Dropping
      // this one is the honest outcome: the alternative is overwriting bytes a
      // voice is still reading, which is the defect this pool exists to avoid.
      return false;
    }
    // Not discarded. A stopped engine refuses every control event, so this is
    // the branch that makes an audition silent in a Host that never activated
    // audio -- exactly the case the caller cannot see from the geometry.
    return engine.enqueue_control(audio::PadControlEvent{
               0, 0, 127, audio::PadControlKind::audition_start, {}}) ==
           audio::EnqueueResult::accepted;
  }

  std::optional<Json> enqueue_sample_control(
      audio::PadControlKind kind,
      domain::PadSlotId slot,
      cooker::ResolvedPlayback playback = {}) {
    const bool retained_release = state == State::failed && kind == audio::PadControlKind::release &&
        transport && transport->owned_presses.contains(slot);
    if ((state != State::running && !retained_release) || (!trigger_admission && !retained_release) || !runtime_ready ||
        runtime_bank_project_id != project_id) {
      return state_error("runtime control is unavailable");
    }
    const auto enqueued = engine.enqueue_control(audio::PadControlEvent{
        0,
        flatten_slot(slot),
        0,
        kind,
        playback,
    });
    if (enqueued != audio::EnqueueResult::accepted) {
      return state_error(enqueue_failure_message(enqueued));
    }
    return std::nullopt;
  }

  std::optional<Json> prepare_sample_mutation_controls(
      domain::PadSlotId slot,
      bool stop_voice) {
    if (state != State::running) {
      return std::nullopt;
    }
    if (stop_voice) {
      // During a replay only the Pad's live voice stops; the replay's and its
      // Pattern's voices keep sounding.
      const auto stopped = enqueue_sample_control(
          replay_holds_runtime() ? audio::PadControlKind::stop_slot_live
                                 : audio::PadControlKind::stop_slot,
          slot);
      if (stopped.has_value()) {
        return stopped;
      }
    }
    return enqueue_sample_control(audio::PadControlKind::preview_clear, slot);
  }

  struct SnapshotResult {
    bool published = false;
    bool resource_rejected = false;
    std::optional<std::uint64_t> generation;
    Json error = nullptr;
  };

  std::optional<Json> await_bank_acknowledgement(
      std::uint64_t expected_generation) noexcept {
    if (engine.telemetry().state != audio::RealtimeState::running) {
      return std::nullopt;
    }
    if (!coordinator.has_value() ||
        coordinator->acknowledged_generation == nullptr ||
        !request_deadline.has_value()) {
      trigger_admission = false;
      seal_all_noexcept();
      state = State::failed;
      return internal_error();
    }
    auto acknowledged = coordinator->acknowledged_generation(
        coordinator->context);
    while (acknowledged < expected_generation &&
           clock_now() < *request_deadline) {
      std::this_thread::yield();
      acknowledged = coordinator->acknowledged_generation(
          coordinator->context);
    }
    if (acknowledged == expected_generation) {
      return std::nullopt;
    }
    const auto timed_out = request_cancelled();
    trigger_admission = false;
    seal_all_noexcept();
    state = State::failed;
    return timed_out ? timeout_error() : internal_error();
  }

  foundation::Result<void> release_runtime_banks() {
    for (std::size_t slot = 0; slot < audio::kRealtimeSampleSlots; ++slot) {
      const auto cleared =
          engine.clear_sample(static_cast<std::uint8_t>(slot));
      if (!cleared.has_value()) {
        return cleared;
      }
    }
    const auto reclaimed = engine.reclaim_retired_bank_telemetry();
    if (reclaimed.decoded_pcm_bytes > reserved_live_bytes) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::internal_error,
          "runtime Bank reservation underflow",
      });
    }
    reserved_live_bytes -= reclaimed.decoded_pcm_bytes;
    if (reserved_live_bytes != 0) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::internal_error,
          "runtime Bank resources remain reserved",
      });
    }
    runtime_ready = false;
    runtime_bank_project_id.reset();
    runtime_revision.reset();
    return foundation::Result<void>::success();
  }

  SnapshotResult prepare_and_publish(
      std::string_view selected_pattern,
      bool preserve_saved_truth = false, bool force_pattern = false,
      bool immediate_pattern = false,
      bool wait_for_control_drain = false) {
    const auto reclaimed = engine.reclaim_retired_bank_telemetry();
    if (reclaimed.decoded_pcm_bytes > reserved_live_bytes) {
      throw std::logic_error("runtime Bank reservation underflow");
    }
    reserved_live_bytes -= reclaimed.decoded_pcm_bytes;

    const auto preparation_headroom =
        limits.maximum_resident_bytes >= limits.maximum_generation_bytes
            ? limits.maximum_resident_bytes - limits.maximum_generation_bytes
            : 0;
    if (limits.maximum_resident_bytes < limits.maximum_generation_bytes ||
        reserved_live_bytes > preparation_headroom) {
      const auto observed = audio::checked_runtime_byte_sum(
          reserved_live_bytes, limits.maximum_generation_bytes);
      auto error = host_error(
          "WEB_RUNTIME_RESOURCE_LIMIT",
          "why: live and retiring prepared PCM leaves no bounded room for "
          "one generation cook; remedy: wait for retirement and retry",
          {
              {"resource", "resident_pcm_bytes"},
              {"observed",
               observed.value_or(std::numeric_limits<std::uint64_t>::max())},
              {"limit", limits.maximum_resident_bytes},
          });
      return SnapshotResult{false, true, std::nullopt, error.at("error")};
    }

    auto prepared = application.prepare_runtime_snapshot(
        facade::RuntimeSnapshotRequest{
            *retained_project_path,
            foundation::PatternId{std::string(selected_pattern)},
            limits,
        });
    if (!prepared.has_value()) {
      auto error = normalized_error(prepared.error());
      return SnapshotResult{
          false,
          runtime_resource_rejection(error.at("error")),
          std::nullopt,
          error.at("error"),
      };
    }
    const auto& snapshot = *prepared.value();
    if (!project_id.has_value() ||
        snapshot.project_id.value() != *project_id) {
      auto error = host_error(
          "INVALID_PROJECT", "project identity does not match selector");
      return SnapshotResult{false, false, std::nullopt, error.at("error")};
    }

    std::uint64_t candidate_bytes = 0;
    for (const auto& pad : snapshot.pads) {
      if (pad.sample == nullptr || pad.sample->channels == 0 ||
          pad.sample->interleaved.size() % pad.sample->channels != 0) {
        auto error = host_error(
            "INVALID_PROJECT", "runtime snapshot PCM is invalid");
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
      const auto frames = static_cast<std::uint64_t>(
          pad.sample->interleaved.size() / pad.sample->channels);
      const auto bytes = audio::checked_mono_float_bytes(frames);
      if (!bytes.has_value()) {
        auto error = host_error(
            "INVALID_PROJECT", "runtime snapshot PCM is invalid");
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
      const auto total =
          audio::checked_runtime_byte_sum(candidate_bytes, *bytes);
      if (!total.has_value()) {
        auto error = host_error(
            "INVALID_PROJECT", "runtime snapshot PCM is invalid");
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
      candidate_bytes = *total;
    }
    const auto aggregate =
        audio::checked_runtime_byte_sum(reserved_live_bytes, candidate_bytes);
    if (!aggregate.has_value() ||
        !limits.allows_resident_bytes(*aggregate)) {
      const auto observed = aggregate.value_or(
          std::numeric_limits<std::uint64_t>::max());
      auto error = host_error(
          "WEB_RUNTIME_RESOURCE_LIMIT",
          "why: live and retiring generations exceed the runtime residency "
          "quota; remedy: wait for retirement and retry publication",
          {
              {"resource", "resident_pcm_bytes"},
              {"observed", observed},
              {"limit", limits.maximum_resident_bytes},
          });
      return SnapshotResult{false, true, std::nullopt, error.at("error")};
    }

    // Application admission already applies the Bank and generation quotas.
    // Publication repeats those immutable Snapshot checks and keeps residency
    // as a separate aggregate bound across live and retired generations.
    const auto publication_limits = audio::RuntimePreparationLimits{
        limits.maximum_artifact_bytes,
        limits.maximum_user_bank_bytes,
        limits.maximum_generation_bytes,
        limits.maximum_resident_bytes,
    };
    auto bank = audio::PreparedSampleBank::from_snapshot(
        snapshot, publication_limits);
    if (!bank.has_value()) {
      auto error = normalized_error(bank.error());
      return SnapshotResult{
          false,
          runtime_resource_rejection(error.at("error")),
          std::nullopt,
          error.at("error"),
      };
    }
    const auto current_pattern = engine.current_pattern_id();
    // A replay holds the Pattern view; the Bank, which replay voices never
    // read, still publishes so live Pads and previews hear Truth.
    const auto publish_pattern = !replay_holds_runtime() && (force_pattern ||
        engine.telemetry().state == audio::RealtimeState::stopped ||
        !current_pattern.has_value() ||
        current_pattern->value() != selected_pattern);
    std::optional<audio::PreparedPatternView> pattern;
    if (publish_pattern) {
      auto prepared_pattern =
          audio::PreparedPatternView::from_snapshot(snapshot);
      if (!prepared_pattern.has_value()) {
        auto error = normalized_error(prepared_pattern.error());
        return SnapshotResult{
            false, false, std::nullopt, error.at("error")};
      }
      pattern.emplace(std::move(prepared_pattern.value()));
    }
    if (preserve_saved_truth ? request_cancelled() : cancel_if_expired()) {
      auto error = timeout_error();
      return SnapshotResult{false, false, std::nullopt, error.at("error")};
    }
    if (pattern.has_value() &&
        engine.telemetry().state == audio::RealtimeState::stopped) {
      const auto cleared = engine.clear_pattern_view();
      if (!cleared.has_value()) {
        auto error = normalized_error(cleared.error());
        return SnapshotResult{
            false, false, std::nullopt, error.at("error")};
      }
      static_cast<void>(engine.reclaim_retired_patterns());
    }
    auto publication = engine.publish_sample_bank(std::move(bank.value()));
    // This refusal precedes consuming the Bank or reserving its generation.
    // ASSIGN opts in to waiting for its stop/preview controls to drain; other
    // callers keep their original single publication attempt. Retain this one
    // prepared Bank rather than recooking or resending Truth.
    while (wait_for_control_drain &&
           publication == audio::PublishResult::events_pending) {
      if (request_cancelled()) {
        if (!preserve_saved_truth) {
          static_cast<void>(cancel_if_expired());
        }
        auto error = timeout_error();
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
      // Bound repeated control observation while no callback drains the queue.
      auto retry_delay = std::chrono::steady_clock::duration{
          std::chrono::milliseconds(1)};
      if (request_deadline.has_value()) {
        retry_delay = std::min(
            retry_delay,
            std::max(std::chrono::steady_clock::duration::zero(),
                     *request_deadline - clock_now()));
      }
      std::this_thread::sleep_for(retry_delay);
      if (request_cancelled()) {
        if (!preserve_saved_truth) {
          static_cast<void>(cancel_if_expired());
        }
        auto error = timeout_error();
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
      publication = engine.publish_sample_bank(std::move(bank.value()));
    }
    if (publication != audio::PublishResult::accepted) {
      auto error = state_error("runtime Bank publication is unavailable");
      return SnapshotResult{false, false, std::nullopt, error.at("error")};
    }
    if (pattern.has_value()) {
      const auto pattern_publication =
          immediate_pattern
              ? engine.publish_pattern_view_immediate(std::move(*pattern))
              : engine.publish_pattern_view(std::move(*pattern));
      if (pattern_publication.result !=
          audio::PatternPublishResult::accepted) {
        auto error = state_error("runtime Pattern publication is unavailable");
        return SnapshotResult{false, false, std::nullopt, error.at("error")};
      }
    }
    reserved_live_bytes = *aggregate;
    runtime_ready = true;
    runtime_bank_project_id = project_id;
    runtime_revision = snapshot.project_revision;
    pattern_id = std::string(selected_pattern);
    project_revision = snapshot.project_revision;
    const auto generation = engine.bank_telemetry().accepted_publications;
    return SnapshotResult{true, false, generation, nullptr};
  }

  Json open_result(
      std::string_view selected_pattern,
      const SnapshotResult& snapshot) const {
    return success({
        {"project_id", *project_id},
        {"project_revision", *project_revision},
        {"pattern_id", std::string(selected_pattern)},
        {"runtime_ready", snapshot.published},
        {"generation",
         snapshot.generation.has_value() ? Json(*snapshot.generation)
                                         : Json(nullptr)},
        {"snapshot_error", snapshot.error},
    });
  }

  Json retry_result(
      std::string_view selected_pattern,
      const SnapshotResult& snapshot) const {
    return success({
        {"project_id", *project_id},
        {"project_revision", *project_revision},
        {"pattern_id", std::string(selected_pattern)},
        {"runtime_ready", snapshot.published},
        {"generation",
         snapshot.generation.has_value() ? Json(*snapshot.generation)
                                         : Json(nullptr)},
        {"snapshot_error", snapshot.error},
        {"runtime_revision",
         runtime_revision.has_value() ? Json(*runtime_revision)
                                      : Json(nullptr)},
    });
  }

  Json sample_mutation_result(
      const facade::SampleMutationResult& mutation,
      domain::PadSlotId slot,
      bool wait_for_control_drain = false) {
    const auto inspected = application.inspect_sample(
        facade::SampleInspectRequest{*retained_project_path, slot});
    if (inspected.has_value()) {
      project_revision = inspected.value().project_revision;
    } else {
      project_revision = mutation.committed_revision;
    }
    SnapshotResult snapshot;
    if (mutation.runtime_prepare_required) {
      if (request_cancelled()) {
        const auto timeout = timeout_error();
        snapshot.error = timeout.at("error");
        if (state == State::running) {
          trigger_admission = false;
          seal_all_noexcept();
          state = State::failed;
        }
      } else {
        snapshot = prepare_and_publish(
            *pattern_id, true, false, false, wait_for_control_drain);
        if (!snapshot.published && state == State::running &&
            snapshot.error.is_object() &&
            snapshot.error.value("code", std::string{}) == "HOST_TIMEOUT") {
          trigger_admission = false;
          seal_all_noexcept();
          state = State::failed;
        }
        if (snapshot.published && snapshot.generation.has_value()) {
          if (const auto acknowledgement =
                  await_bank_acknowledgement(*snapshot.generation);
              acknowledgement.has_value()) {
            snapshot.published = false;
            snapshot.error = acknowledgement->at("error");
          }
        }
      }
    }
    Json result{
        {"committed_revision", mutation.committed_revision},
        {"runtime_revision",
         runtime_revision.has_value() ? Json(*runtime_revision)
                                      : Json(nullptr)},
        {"runtime_published", snapshot.published},
    };
    if (!snapshot.error.is_null()) {
      result["snapshot_error"] = snapshot.error;
    }
    return success(std::move(result));
  }

  void request_terminal_audio_retirement(bool clear_pattern = false) noexcept {
    trigger_admission = false;
    terminal_pattern_clear_pending |= clear_pattern;
    if (!terminal_audio_retirement_requested) {
      terminal_audio_retirement_requested = true;
      terminal_origin_deadline = request_deadline;
      terminal_native_stop_pending = true;
      if (physical_audio) {
        physical_audio->request_terminal_drain(physical_audio->context);
      }
    }
  }

  void service_terminal_audio_retirement() noexcept {
    if (!terminal_audio_retirement_requested) return;
    if (physical_audio) {
      if (!physical_audio->physically_quiescent(physical_audio->context)) return;
    } else {
      // Legacy Hosts retain their existing coordinator contract: after their
      // real Native stop, a successful operational quiescence receipt can
      // retire that stop. Neither stopped telemetry alone nor a failed Result
      // pays this debt. A configured physical producer never uses this path.
      if (!terminal_legacy_quiescent) {
        if (engine.telemetry().state != audio::RealtimeState::stopped ||
            !coordinator) return;
        const auto budget = legacy_retirement_budget_ms();
        if (budget == 0 || !coordinator->await_quiescent(
                coordinator->context, std::min(budget, 1U)).has_value()) return;
      }
      terminal_legacy_quiescent = true;
      terminal_native_stop_pending = false;
    }
    if (terminal_native_stop_pending) {
      // Exactly one real Native stop follows admitted callback last use.
      // It does not turn the failed lifecycle request into success or consume
      // a Native/input/count-in caller acknowledgment.
      engine.stop();
      terminal_native_stop_pending = false;
    }
    if (terminal_pattern_clear_pending) {
      const auto cleared = engine.clear_pattern_view();
      if (cleared.has_value()) {
        static_cast<void>(engine.reclaim_retired_patterns());
        terminal_pattern_clear_pending = false;
      }
    }
  }

  foundation::Result<void> failed_audio_retirement(Error error) noexcept {
    if (!terminal_audio_failure) terminal_audio_failure = error;
    request_terminal_audio_retirement();
    service_terminal_audio_retirement();
    return foundation::Result<void>::failure(std::move(error));
  }

  foundation::Result<void> quiesce_and_stop_audio() noexcept {
    trigger_admission = false;
    if (!coordinator.has_value() ||
        coordinator->await_quiescent == nullptr) {
      return failed_audio_retirement(Error{
          ErrorCode::internal_error,
          "audio quiescence is unavailable",
      });
    }
    const auto timeout_ms = remaining_request_budget_ms();
    if (timeout_ms == 0) {
      return failed_audio_retirement(Error{
          ErrorCode::internal_error,
          "request deadline expired before audio quiescence",
      });
    }
    // Only a successful operational Result establishes the ordinary paused
    // transition. Failure may still have a live callback after both original
    // budgets; preserve that failure and defer Native stop behind its fence.
    const auto quiescent = coordinator->await_quiescent(
        coordinator->context, timeout_ms);
    if (!quiescent.has_value()) {
      return failed_audio_retirement(quiescent.error());
    }
    // This is a genuine operational receipt for this activation, even if
    // the caller subsequently expires. Reuse it during that activation's
    // failure cleanup; beginning a successor invalidates it below.
    if (!physical_audio) terminal_legacy_quiescent = true;
    engine.stop();
    return quiescent;
  }

  void stop_and_clear_pattern_noexcept() noexcept {
    if (terminal_audio_retirement_requested) {
      // A first legacy publication-cleanup failure still owns the original
      // operational quiescence call. Acquire its real successful receipt
      // before stopping; an earlier failed Result or a configured physical
      // producer must continue to use the separate retirement fence.
      if (!physical_audio && !terminal_audio_failure &&
          engine.telemetry().state == audio::RealtimeState::running &&
          coordinator && coordinator->await_quiescent != nullptr) {
        const auto budget = legacy_retirement_budget_ms();
        if (budget != 0) {
          const auto quiescent = coordinator->await_quiescent(
              coordinator->context, budget);
          if (quiescent.has_value()) {
            engine.stop();
            terminal_legacy_quiescent = true;
            terminal_native_stop_pending = false;
          } else {
            terminal_audio_failure = quiescent.error();
          }
        }
      }
      request_terminal_audio_retirement(true);
      service_terminal_audio_retirement();
      return;
    }
    if (engine.telemetry().state == audio::RealtimeState::running) {
      if (!coordinator.has_value() ||
          coordinator->await_quiescent == nullptr) {
        return;
      }
      // This cleanup retains its original budget. A failed observer cannot
      // authorize stop, clear or reclaim while a real callback still borrows.
      const auto timeout_ms = legacy_retirement_budget_ms();
      if (timeout_ms == 0) {
        request_terminal_audio_retirement(true);
        return;
      }
      const auto quiescent = coordinator->await_quiescent(
          coordinator->context, timeout_ms);
      if (!quiescent.has_value()) {
        if (!terminal_audio_failure) terminal_audio_failure = quiescent.error();
        request_terminal_audio_retirement(true);
        service_terminal_audio_retirement();
        return;
      }
      if (!physical_audio) terminal_legacy_quiescent = true;
      engine.stop();
    }
    static_cast<void>(engine.clear_pattern_view());
    static_cast<void>(engine.reclaim_retired_patterns());
  }

  foundation::Result<void> abort_imports() {
    std::optional<Error> first_failure;
    for (auto current = import_tokens.begin(); current != import_tokens.end();) {
      const auto aborted = application.abort_project_bundle_import(*current);
      if (aborted.has_value()) {
        current = import_tokens.erase(current);
        continue;
      }
      if (!first_failure.has_value()) {
        first_failure = aborted.error();
      }
      ++current;
    }
    for (auto current = sample_import_tokens.begin();
         current != sample_import_tokens.end();) {
      const auto aborted = application.abort_sample_import(*current);
      sample_import_slots.erase(*current);
      if (aborted.has_value()) {
        current = sample_import_tokens.erase(current);
        continue;
      }
      if (!first_failure.has_value()) {
        first_failure = aborted.error();
      }
      ++current;
    }
    if (first_failure.has_value()) {
      return foundation::Result<void>::failure(*first_failure);
    }
    return foundation::Result<void>::success();
  }

  void seal_all_noexcept() noexcept {
    // Seal audio admission even when retained Pattern owners prevent generic
    // authoring cleanup. Their actual worker/input/caller gates remain live.
    // An unconfigured stopped Host cannot have admitted a producer through
    // audio.activate. It has no operational/physical audio retirement debt.
    // Installed producers and any already-requested debt keep their gates.
    if (coordinator || physical_audio || terminal_audio_retirement_requested ||
        engine.telemetry().state != audio::RealtimeState::stopped) {
      request_terminal_audio_retirement();
      service_terminal_audio_retirement();
    }
    try {
      static_cast<void>(abort_imports());
    } catch (...) {
    }
    // Failed observers close new admission, but the Pattern controller's
    // sole worker, exact legacy candidate and physical release escrow still
    // own their real effects. A generic legacy seal cannot abandon them.
    if (transport || has_pattern_input_owners() || !legacy_inputs.empty()) return;
    bool clean_pattern_published = true;
    if (active_sequence.has_value()) {
      try {
        // The journal overlay is Runtime-only. Seal the failed owner by
        // replacing any queued or active overlay with committed Project Truth
        // at the normal Bar boundary before abandoning the Facade session.
        clean_pattern_published =
            publish_project_pattern(active_sequence->pattern_id).has_value();
      } catch (...) {
        clean_pattern_published = false;
      }
    }
    if (!clean_pattern_published) {
      stop_and_clear_pattern_noexcept();
    }
    application.abandon_sequence_sessions();
    active_sequence.reset();
    pending_sequence_boundary.reset();
  }

  bool cancel_if_expired() noexcept {
    if (!request_cancelled() || publication_settlement_owned()) {
      return false;
    }
    trigger_admission = false;
    seal_all_noexcept();
    state = State::failed;
    return true;
  }

  std::filesystem::path workspace_root;
  audio::RuntimePreparationLimits limits;
  // The browser side of the Web Host's `CatalogTransport`, when the Host wired
  // one. Held so the three Host-local Catalog operations can stage bytes and
  // read back the addresses Core asked for; it is the same object the
  // Application holds as its transport and its index source.
  std::shared_ptr<facade::SuppliedSoundSetCatalog> host_catalog;
  audio::RealtimeEngine engine;
  std::shared_ptr<std::atomic<bool>> performance_publication_failure;
  std::function<void()> performance_service;
  facade::Application application;
  detail::RecordingMetadataQueries recording_metadata;
  State state = State::core_ready;
  std::optional<facade::RuntimeProjectWriterLease> writer_lease;
  std::optional<std::filesystem::path> retained_project_path;
  std::optional<std::string> project_id;
  std::optional<std::uint64_t> project_revision;
  std::optional<std::string> pattern_id;
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
  bool fail_next_pattern_publication = false;
#endif
  std::optional<std::uint16_t> project_bpm;
  std::optional<std::string> runtime_bank_project_id;
  std::optional<std::uint64_t> runtime_revision;
  std::optional<DeferredPatternEdit> deferred_pattern_edit;
  std::optional<PendingTransportSwitch> pending_transport_switch;
  // #1789: a Performance replay plays the revision it resolved at begin.
  // While one runs, authoring still commits to Truth, but no Pattern view
  // publishes over the replay's; the selected Pattern is restored from Truth
  // once it ends.
  struct TrackedReplay {
    std::string project_id;
    std::string replay_id;
  };
  std::optional<TrackedReplay> active_replay;
  // The Project whose selected Pattern a replay's end restores.
  struct PendingReplayRestore {
    std::string project_id;
    // The reclaim count when a playing restore last found every slot held.
    std::optional<std::uint64_t> held_at_reclaimed;
  };
  std::optional<PendingReplayRestore> replay_restore;
  std::optional<SequenceSession> active_sequence;
  std::optional<PendingSequenceBoundary> pending_sequence_boundary;
  // Global Pattern transport engagement; present once a session has opted in
  // through pattern.transport.request, absent again after Project replacement
  // or Close. While present, direct legacy Sequence writes are rejected.
  std::unique_ptr<TransportEngagement> transport;
  bool transport_opted_in = false;
  bool count_in_input_negotiated = false;
  bool count_in_input_enabled = false;
  std::vector<std::optional<RetainedPatternInput>> pattern_inputs;
  std::vector<std::optional<RetainedPatternHold>> pattern_holds;
  std::uint64_t input_acceptance_floor = 0;
  std::uint64_t input_ledger_generation = 0;
  std::uint64_t input_owner_revoked_generation = 0;
  std::uint64_t input_owner_acknowledged_generation = 0;
  std::map<std::string, RetainedLegacyInput> legacy_inputs;
  std::optional<std::string> current_rpc_request_id;
  std::optional<std::pair<std::string, std::string>> pending_dispatch_rpc;
  std::optional<std::string> pending_recording_metadata_rpc;
  std::uint64_t next_count_in_serial = 1;
  std::uint64_t next_transport_generation = 1;
  std::uint64_t enabled_transport_generation = 0;
  std::optional<detail::AudioQuiescenceCoordinator> coordinator;
  std::optional<detail::CountInOutputCapability> count_in_output;
  std::optional<detail::AudioPhysicalQuiescenceCapability> physical_audio;
  bool terminal_audio_retirement_requested = false;
  std::optional<std::chrono::steady_clock::time_point> terminal_origin_deadline;
  bool terminal_legacy_quiescent = false;
  bool terminal_native_stop_pending = false;
  bool terminal_pattern_clear_pending = false;
  std::optional<Error> terminal_audio_failure;
  std::optional<detail::ControlRuntimeClock> clock;
  std::set<std::string> import_tokens;
  std::set<std::string> sample_import_tokens;
  std::map<std::string, domain::PadSlotId> sample_import_slots;
  std::uint64_t reserved_live_bytes = 0;
  std::uint64_t next_trigger_sequence = 1;
  bool runtime_ready = false;
  bool trigger_admission = false;
  std::optional<std::chrono::steady_clock::time_point> request_deadline;
  void* request_publication_context = nullptr;
  bool (*request_publication_settlement_owned)(void* context) noexcept =
      nullptr;
};

ControlRuntime::ControlRuntime(std::shared_ptr<Impl> impl) noexcept
    : impl_(std::move(impl)) {}

Json ControlRuntime::dispatch(std::string_view operation, const Json& payload,
    std::span<const std::byte> sidecar, AbsoluteRequestDeadline deadline,
    std::string_view original_request_id) {
  struct Reset {
    std::optional<std::string>& identity;
    ~Reset() { identity.reset(); }
  } reset{impl_->current_rpc_request_id};
  impl_->current_rpc_request_id = std::string(original_request_id);
  return dispatch(operation, payload, sidecar, deadline);
}

std::optional<Json> ControlRuntime::inspect_legacy_trigger(std::string_view id, bool consume) {
  service_pattern_transport();
  const auto found = impl_->legacy_inputs.find(std::string(id));
  if (found == impl_->legacy_inputs.end()) return std::nullopt;
  auto& retained = found->second;
  if (impl_->clock_now() >= retained.deadline) {
    if (consume) {
      retained.observer_consumed = true;
      if (retained.terminal_response) impl_->legacy_inputs.erase(found);
    }
    return timeout_error();
  }
  if (!retained.terminal_response) return std::nullopt;
  auto response = *retained.terminal_response;
  if (consume) impl_->legacy_inputs.erase(found);
  return response;
}

bool ControlRuntime::owns_pending_pattern_rpc(
    std::string_view id, std::string_view operation) const {
  if (operation == "trigger") {
    const auto found = impl_->legacy_inputs.find(std::string{id});
    // An expired observer may be consumed while its original accepted I/O
    // effect is still retained. A reused RPC identity cannot acquire it.
    return found != impl_->legacy_inputs.end() && !found->second.observer_consumed;
  }
  return impl_->pending_dispatch_rpc &&
      impl_->pending_dispatch_rpc->first == id &&
      impl_->pending_dispatch_rpc->second == operation;
}

bool ControlRuntime::owns_pending_recording_metadata(std::string_view id) const {
  return impl_->pending_recording_metadata_rpc == id && impl_->recording_metadata.contains(id);
}

std::optional<Json> ControlRuntime::inspect_recording_metadata(
    std::string_view id, bool consume, bool cancel) {
  const auto result = impl_->recording_metadata.inspect(id, consume, cancel);
  if (!result) return std::nullopt;
  if (!result->has_value()) {
    auto response = normalized_error(result->error());
    const auto& error = result->error();
    // This operation's closed refusal vocabulary is safe to publish. Keep
    // the generic redactor and every older operation unchanged; no paths or
    // arbitrary provider/platform text cross this read-only boundary.
    if (error.code == ErrorCode::cook_failed && error.details.is_object() &&
        error.details.contains("storage_condition") &&
        error.details.at("storage_condition") == "artifact_mismatch")
      response["error"]["details"]["storage_condition"] = "artifact_mismatch";
    if (error.code == ErrorCode::io_error && error.details.is_object() &&
        error.details.contains("reason") && error.details.at("reason") == "bounded_read_unavailable")
      response["error"]["details"]["reason"] = "bounded_read_unavailable";
    return response;
  }
  const auto* metadata = std::get_if<facade::PerformanceRecordingMetadata>(&result->value());
  if (!metadata) return state_error("recording metadata query was retired");
  Json audio = nullptr, audio_error = nullptr;
  if (metadata->audio.has_value()) {
    const auto& value = metadata->audio.value();
    audio = {{"sample_rate", value.sample_rate}, {"channels", value.channels},
             {"source_frames", value.source_frames}};
  } else audio_error = normalized_error(metadata->audio.error()).at("error");
  return success({{"project_id", metadata->project_id.value()},
      {"performance_id", metadata->performance_id.value()},
      {"project_revision", metadata->project_revision},
      {"recording_revision", metadata->recording_revision},
      {"recording_artifact", metadata->artifact},
      {"audio_metadata", std::move(audio)}, {"audio_error", std::move(audio_error)}});
}

void ControlRuntime::service_recording_metadata() {
  impl_->recording_metadata.service();
}

bool ControlRuntime::recording_metadata_workers_stopped() const noexcept {
  return impl_->recording_metadata.workers_stopped();
}

bool ControlRuntime::recording_metadata_pending() const noexcept {
  return impl_->recording_metadata.pending();
}

foundation::Result<std::unique_ptr<ControlRuntime>> ControlRuntime::create(
    std::filesystem::path workspace_root,
    facade::ApplicationConfig application_config,
    audio::RuntimePreparationLimits limits) {
  if (!workspace_root.is_absolute() ||
      workspace_root.lexically_normal() != workspace_root ||
      application_config.workspace_root != workspace_root) {
    return foundation::Result<std::unique_ptr<ControlRuntime>>::failure(
        Error{ErrorCode::invalid_argument, "workspace root is invalid"});
  }
  try {
    return foundation::Result<std::unique_ptr<ControlRuntime>>::success(
        std::unique_ptr<ControlRuntime>(new ControlRuntime(
            std::make_shared<Impl>(
                std::move(workspace_root),
                std::move(application_config),
                limits))));
  } catch (...) {
    return foundation::Result<std::unique_ptr<ControlRuntime>>::failure(
        Error{ErrorCode::internal_error, "Web Host allocation failed"});
  }
}

Json ControlRuntime::dispatch(
    std::string_view operation,
    const Json& payload,
    std::span<const std::byte> sidecar) {
  return dispatch(
      operation, payload, sidecar, impl_->clock_now());
}

Json ControlRuntime::dispatch(
    std::string_view operation,
    const Json& payload,
    std::span<const std::byte> sidecar,
    std::chrono::steady_clock::time_point submitted_at) {
  return dispatch(
      operation,
      payload,
      sidecar,
      AbsoluteRequestDeadline{submitted_at + operation_deadline(operation)});
}

Json ControlRuntime::dispatch(
    std::string_view operation,
    const Json& payload,
    std::span<const std::byte> sidecar,
    AbsoluteRequestDeadline deadline) {
  struct DeadlineReset final {
    std::optional<std::chrono::steady_clock::time_point>& value;
    void*& publication_context;
    bool (*&publication_settlement_owned)(void*) noexcept;
    ~DeadlineReset() {
      value.reset();
      publication_context = nullptr;
      publication_settlement_owned = nullptr;
    }
  } reset{
      impl_->request_deadline,
      impl_->request_publication_context,
      impl_->request_publication_settlement_owned};
  impl_->request_deadline = deadline.value;
  impl_->request_publication_context = deadline.publication_context;
  impl_->request_publication_settlement_owned =
      deadline.publication_settlement_owned;
  impl_->pending_dispatch_rpc.reset();
  impl_->pending_recording_metadata_rpc.reset();
  const auto transport_error = [&](const Error& error) {
    if (impl_->current_rpc_request_id && error.details.is_object() &&
        error.details.value("pending", false) &&
        error.details.value("reason", std::string{}).starts_with("pattern_transport_")) {
      impl_->pending_dispatch_rpc = std::pair{
          *impl_->current_rpc_request_id, std::string(operation)};
    }
    return normalized_error(error);
  };
  try {
    impl_->recording_metadata.service();
    const bool retained_owner_operation =
        operation == "pattern.transport.input.inspect" ||
        operation == "pattern.transport.input.request" ||
        operation == "pattern.transport.count-in.inspect" ||
        operation == "pattern.transport.count-in.cancel" ||
        operation == "pattern.transport.inspect" ||
        (operation == "trigger" && payload.is_object() &&
         payload.contains("kind") && payload.at("kind").is_string() &&
         payload.at("kind") == "release" && impl_->transport &&
         payload.contains("slot") && payload.at("slot").is_number_integer() &&
         payload.at("slot") >= 0 && payload.at("slot") < 64 &&
         impl_->transport->owned_presses.contains(domain::PadSlotId{
             static_cast<std::uint8_t>(payload.at("slot").get<std::uint64_t>() / 16),
             static_cast<std::uint8_t>(payload.at("slot").get<std::uint64_t>() % 16)}));
    if ((impl_->state == Impl::State::failed && !retained_owner_operation) ||
        impl_->state == Impl::State::closed) {
      return state_error();
    }
    if (impl_->cancel_if_expired()) {
      return timeout_error();
    }
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
    if (operation == "__testing.fail-next-pattern-publication") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      impl_->fail_next_pattern_publication = true;
      impl_->performance_publication_failure->store(true);
      return success({{"armed", true}});
    }
#endif
    if (operation == "performance.recording.metadata") {
      require(sidecar.empty());
      require(exact_keys(payload, {"project_id", "performance_id", "expected_revision", "recording_artifact"}));
      const auto project = uuid_field(payload, "project_id");
      const auto performance = uuid_field(payload, "performance_id");
      const auto revision = safe_unsigned_field(payload, "expected_revision");
      validate_performance_artifact(payload.at("recording_artifact"));
      if (!impl_->session_available() || project != *impl_->project_id ||
          !impl_->current_rpc_request_id || impl_->current_rpc_request_id->empty())
        return state_error("recording metadata owner is unavailable");
      const auto artifact = payload.at("recording_artifact").get<foundation::ArtifactRef>();
      const auto started = impl_->recording_metadata.start(*impl_->current_rpc_request_id,
          {*impl_->retained_project_path, foundation::ProjectId{project},
           domain::PerformanceId{performance}, revision, artifact},
          impl_->application.make_performance_recording_metadata_reader());
      using Start = detail::RecordingMetadataQueries::Start;
      if (started == Start::full) return host_error("WEB_RUNTIME_RESOURCE_LIMIT",
          "recording metadata query capacity is retained",
          {{"resource", "recording_metadata_queries"}, {"limit", detail::RecordingMetadataQueries::capacity}});
      if (started == Start::duplicate) return state_error("recording metadata request identity is retained");
      if (started == Start::worker_failed) return internal_error();
      impl_->pending_recording_metadata_rpc = *impl_->current_rpc_request_id;
      return state_error("recording metadata query is pending");
    }
    static const std::map<std::string_view, bool> performance_operations{
        {"pattern.slot.assign", false},
        {"pattern.slot.clear", false},
        {"pattern.slot.move", false},
        {"performance.list", true},
        {"performance.inspect", true},
        {"performance.record.begin", false},
        {"performance.record.event", false},
        {"performance.live.control", false},
        {"performance.live.status", true},
        {"performance.record.launch-request", false},
        {"performance.record.flush", false},
        {"performance.record.stop", false},
        {"performance.record.status", true},
        {"performance.save", false},
        {"performance.discard", false},
        {"performance.recovery.list", true},
        {"performance.recovery.apply", false},
        {"performance.recovery.discard", false},
        {"performance.rename", false},
        {"performance.delete", false},
        {"performance.recording.bind", false},
        {"performance.replay.begin", false},
        {"performance.replay.stop", false},
        {"performance.replay.status", true},
        {"performance.resample.commit", false},
    };
    // The browser half of the Web Host's `CatalogTransport`. These three are
    // Host-local plumbing, not Facade operations: they never reach
    // `Application`, they carry no Project and no revision, and they exist only
    // so the browser side can `fetch` the two locked object kinds from the
    // Host-configured Catalog endpoint and hand the bytes to Core. Core keeps
    // every Contract, hash and eligibility decision.
    if (operation == "soundset.catalog.supply" ||
        operation == "soundset.catalog.index" ||
        operation == "soundset.catalog.pending") {
      if (impl_->host_catalog == nullptr) {
        return state_error("Host Catalog transport is unavailable");
      }
      if (operation == "soundset.catalog.pending") {
        require(exact_keys(payload, {}));
        require(sidecar.empty());
        const auto reads = impl_->host_catalog->drain_pending();
        auto objects = Json::array();
        for (const auto& object : reads.objects) {
          objects.push_back({
              {"object_kind", object.object_kind},
              {"sha256", object.sha256},
          });
        }
        return success({{"index", reads.index}, {"objects", std::move(objects)}});
      }
      if (operation == "soundset.catalog.index") {
        require(exact_keys(payload, {"available"}));
        // The index read opens a listing pass, and supplied objects live for
        // exactly one pass: Core publishes what it accepted into the Workspace
        // Set Store, and the crossing buffer owns nothing after that. Without
        // this the two Host bounds would be lifetime totals rather than
        // high-water marks, and a long session would quietly stop being able
        // to acquire anything.
        impl_->host_catalog->clear_staged();
        if (!bool_field(payload, "available")) {
          require(sidecar.empty());
          impl_->host_catalog->forget_index();
          return success({{"staged", false}});
        }
        const auto staged = impl_->host_catalog->supply_index(sidecar);
        if (!staged.has_value()) {
          return normalized_error(staged.error());
        }
        return success({{"staged", true}});
      }
      // `soundset.catalog.supply` carries the locked address plus the framing
      // one object needs to cross more than one bridge message. There is no
      // path, name, URL or archive member here, so a browser side that
      // resolved something other than `{object_kind, sha256}` has no way to
      // say so.
      require(
          exact_keys(
              payload, {"object_kind", "sha256", "offset", "byte_length"}));
      const auto object_kind = string_field(payload, "object_kind");
      const auto sha256 = string_field(payload, "sha256");
      const auto offset = unsigned_field(payload, "offset");
      const auto byte_length = unsigned_field(payload, "byte_length");
      const auto staged = impl_->host_catalog->supply(
          object_kind, sha256, offset, byte_length, sidecar);
      if (!staged.has_value()) {
        return normalized_error(staged.error());
      }
      return success({{"staged", staged.value()}});
    }
    static const std::map<std::string_view, bool> candidate_operations{
        {"candidate.job.run", false}, {"candidate.job.inspect", true},
        {"candidate.job.cancel", false}, {"candidate.set.discard", false},
        {"candidate.adopt", false}, {"candidate.audition", true},
        {"candidate.audition.stop", true},
    };
    if (const auto found = candidate_operations.find(operation); found != candidate_operations.end()) {
      require(sidecar.empty());
      validate_candidate_operation_payload(operation, payload);
      if (operation == "candidate.audition.stop") {
        if (impl_->runtime_ready) {
          const auto stopped = impl_->engine.enqueue_control(audio::PadControlEvent{
            0, 0, 0, audio::PadControlKind::audition_stop, {}});
          if (stopped != audio::EnqueueResult::accepted &&
              impl_->engine.telemetry().state != audio::RealtimeState::stopped) return state_error();
        }
        return success({{"accepted", true}});
      }
      auto request = payload;
      request["operation"] = operation;
      if (payload.contains("project_id")) {
        if (!impl_->session_available()) return state_error();
        if (payload.at("project_id") != *impl_->project_id) {
          return normalized_error(Error{ErrorCode::revision_conflict, "Candidate belongs to another Project"});
        }
        request["project_path"] = impl_->retained_project_path->generic_string();
      }
      impl_->service_performance_adapter();
      if (operation == "candidate.audition") {
        const auto audio = impl_->application.audition_candidate(facade::CandidateAuditionRequest{
          *impl_->retained_project_path, foundation::ProjectId{*impl_->project_id},
          payload.at("expected_revision").get<std::uint64_t>(), payload.at("job_id").get<std::string>(),
          payload.at("set_id").get<std::string>(), payload.at("candidate_id").get<std::string>()});
        if (!audio.has_value()) return normalized_error(audio.error());
        const auto& value = audio.value();
        return success({{"job_id", payload.at("job_id")}, {"set_id", payload.at("set_id")},
          {"candidate_id", payload.at("candidate_id")}, {"artifact", value.artifact},
          {"sample_rate", value.sample_rate}, {"channels", value.channels}, {"source_frames", value.source_frames},
          {"project_revision", payload.at("expected_revision")},
          {"played", impl_->runtime_ready && impl_->publish_audition_pcm(value.prepared)}});
      }
      auto response = found->second ? impl_->application.query(request) : impl_->application.command(request);
      if (!response.value("ok", false)) return normalized_facade_error(response);
      if (response.at("project_revision").is_number_unsigned())
        impl_->project_revision = response.at("project_revision").get<std::uint64_t>();
      // The Web projection preserves Facade identities, never filesystem authority.
      // Only the Host owns these retained paths; the browser cannot round-trip them.
      if (operation != "candidate.adopt") {
        for (auto& entry : response.at("result").at("history"))
          entry.at("intent").at("source").erase("project_path");
        for (auto& set : response.at("result").at("sets"))
          set.at("source").erase("project_path");
      }
      return normalized_facade_success(response);
    }
    static const std::map<std::string_view, bool> provider_operations{
        {"provider.list", true}, {"provider.select", false},
        {"provider.run", false}, {"provider.permissions.configure", false},
        {"attempt.inspect", true},
    };
    if (const auto found = provider_operations.find(operation);
        found != provider_operations.end()) {
      require(sidecar.empty());
      validate_provider_operation_payload(operation, payload);
      auto request = payload;
      request["operation"] = operation;
      if (request.contains("input_owners") && !request.at("input_owners").empty()) {
        if (!impl_->session_available()) return state_error();
        for (auto& owner : request.at("input_owners")) {
          owner["project_path"] = impl_->retained_project_path->generic_string();
        }
      }
      impl_->service_performance_adapter();
      const auto response = found->second
          ? impl_->application.query(request) : impl_->application.command(request);
      if (!response.value("ok", false)) {
        auto normalized = normalized_facade_error(response);
        const auto& failure = response.at("error");
        const auto& details = failure.at("details");
        if (details.is_object()) {
          const auto reason = details.value("reason", Json{});
          const auto code = failure.at("code");
          if ((code == "NOT_FOUND" && reason == "input_artifact_unavailable") ||
              (code == "IO_ERROR" && reason == "input_artifact_mismatch") ||
              (code == "INVALID_ARGUMENT" &&
               (reason == "input_binding_invalid" || reason == "input_artifact_too_large"))) {
            normalized["error"]["details"]["reason"] = reason;
          }
          if (operation == "provider.run" &&
              details.value("attempt_id", Json{}) == request.at("attempt_id")) {
            normalized["error"]["details"]["attempt_id"] = request.at("attempt_id");
          }
        }
        return normalized;
      }
      return normalized_facade_success(response);
    }

    // The value is `is_query`, read only by the Facade forwarding at the end
    // of this block. Membership is load-bearing for every entry -- it gates
    // `require(sidecar.empty())` and the payload validation -- but the value
    // is inert for an operation answered before the forwarding is reached.
    // `soundset.audition.stop` is the one such entry: it returns below without
    // consulting this bool, so neither `true` nor `false` describes it. Read
    // `true` here as "not a command", never as "the Facade serves it" -- it
    // does not, which is why the operation is deliberately absent from the
    // Native Host's `kSoundSetOperations` and from core-mcp.
    static const std::map<std::string_view, bool> soundset_operations{
        {"soundset.audition", true},
        {"soundset.audition.stop", true},
        {"soundset.catalog.list", true},
        {"soundset.catalog.describe", true},
        {"soundset.slot.acquire", true},
        {"soundset.slot.install", false},
        {"soundset.inspect", true},
        {"soundset.map.preview", true},
        {"soundset.install", false},
    };
    if (const auto found = soundset_operations.find(operation);
        found != soundset_operations.end()) {
      require(sidecar.empty());
      validate_soundset_operation_payload(operation, payload);
      // S11-D6: the Set Store and the Catalog cache resolve from the
      // Workspace, so browsing, inspecting and auditioning a Set needs no
      // open Project — the `provider.list` precedent the Locked Facade
      // Surface names. Only the two Project-scoped operations require, and
      // learn, a Project.
      // #799. Stopping touches only this Host's engine -- no Set, no Facade,
      // no Project -- so it is answered here in full, the way
      // `sample.preview.clear` is. It is idempotent: stopping when nothing is
      // auditioning succeeds, which is what keeps it inside the locked error
      // vocabulary, because there is no "nothing to stop" condition to name.
      if (operation == "soundset.audition.stop") {
        if (impl_->runtime_ready) {
          static_cast<void>(impl_->engine.enqueue_control(
              audio::PadControlEvent{
                  0, 0, 0, audio::PadControlKind::audition_stop, {}}));
        }
        return success({{"accepted", true}});
      }

      const bool project_scoped = operation == "soundset.map.preview" ||
                                  operation == "soundset.install" ||
                                  operation == "soundset.slot.install";
      if (project_scoped && !impl_->session_available()) {
        return state_error();
      }
      impl_->service_performance_adapter();
      auto request = payload;
      require(request.is_object());
      request["operation"] = operation;
      if (project_scoped) {
        request["project_path"] =
            impl_->retained_project_path->generic_string();
      }
      const auto response = found->second
          ? impl_->application.query(request)
          : impl_->application.command(request);
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      if (response.at("project_revision").is_number_unsigned()) {
        impl_->project_revision =
            response.at("project_revision").get<std::uint64_t>();
      }
      // #799. The Facade has answered with the geometry; this Host owns an
      // engine, so it also plays the bytes. The Facade resolved, gated and
      // decoded them -- this never reads the Set Store, which is what keeps
      // audition inside "Hosts use only the Application Facade".
      //
      // Failing to play is deliberately not an error: the metadata answer is
      // already correct and useful, a Host with no running runtime is a normal
      // state rather than a refusal, and reporting a playback failure through
      // a query's envelope would need vocabulary the Stage has frozen.
      //
      // It is still reported. `played` says whether a voice started, on the
      // successful result beside the geometry, so "it played" and "it silently
      // did not" stop being the same answer. It is not a refusal and adds no
      // `lmdj.error.v1` code and no `details.reason` token: a query that
      // answers what happened is the shape the frozen vocabulary leaves open.
      // Only the fact is reported, never which branch produced it -- a reason
      // vocabulary here would be the very thing the Stage froze.
      if (operation == "soundset.audition") {
        const bool played =
            impl_->runtime_ready && impl_->play_audition(payload);
        auto normalized = normalized_facade_success(response);
        if (normalized.value("ok", false)) {
          normalized.at("result")["played"] = played;
        }
        return normalized;
      }
      return normalized_facade_success(response);
    }
    if (operation == "performance.fx.gesture") {
      require(sidecar.empty());
      require(exact_keys(payload, {"event"}));
      validate_performance_fx_gesture_event(payload.at("event"));
      auto request = payload;
      request["operation"] = operation;
      const auto response = impl_->application.command(request);
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      return normalized_facade_success(response);
    }
      if (const auto found = performance_operations.find(operation);
          found != performance_operations.end()) {
        require(sidecar.empty());
        validate_performance_operation_payload(operation, payload);
        if (!impl_->session_available()) {
          return state_error();
        }
        // A replay begins by publishing its own Pattern view, which the
        // engine refuses over the publication a queued switch holds; refuse
        // before any Facade command runs.
        if (operation == "performance.replay.begin" &&
            impl_->transport_switch_pending()) {
          return host_error(
              "HOST_STATE_INVALID",
              "Performance replay cannot begin while a Pattern switch is "
              "queued on the transport; retry after it lands",
              {{"reason", "pattern_switch_pending"}});
        }
      // Runtime progress is observed before both command and query dispatch.
      // Only commands cross Application's explicit durable-service boundary;
      // queries remain disk-read-only.
      impl_->service_performance_adapter();
      auto request = payload;
      require(request.is_object());
      request["operation"] = operation;
      request["project_path"] =
          impl_->retained_project_path->generic_string();
      const auto response = found->second
          ? impl_->application.query(request)
          : impl_->application.command(request);
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      if (response.at("project_revision").is_number_unsigned()) {
        impl_->project_revision =
            response.at("project_revision").get<std::uint64_t>();
      }
      if (operation.starts_with("performance.replay.")) {
        impl_->track_replay_response(operation, response.at("result"));
      }
      return normalized_facade_success(response);
    }
    if (operation == "host.status") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      return impl_->status();
    }
    if (operation == "project.list") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      const auto listed = impl_->application.list_local_projects();
      if (!listed.has_value()) {
        return normalized_error(listed.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      auto projects = Json::array();
      for (const auto& summary : listed.value()) {
        projects.push_back(local_project_summary(summary));
      }
      return success({{"projects", std::move(projects)}});
    }
    if (operation == "project.import.begin") {
      require(exact_keys(
          payload, {"import_token", "index_bytes", "index_sha256"}));
      require(sidecar.empty());
      const auto token = uuid_field(payload, "import_token");
      const auto index_bytes = unsigned_field(
          payload, "index_bytes", 4'194'304);
      require(index_bytes != 0);
      const auto index_sha256 = string_field(payload, "index_sha256");
      require(
          index_sha256.size() == 64 &&
          std::all_of(
              index_sha256.begin(), index_sha256.end(), [](char value) {
                return (value >= '0' && value <= '9') ||
                       (value >= 'a' && value <= 'f');
              }));
      const auto begun = impl_->application.begin_project_bundle_import(
          facade::ProjectBundleImportBeginRequest{
              token, index_bytes, index_sha256});
      if (!begun.has_value()) {
        return normalized_error(begun.error());
      }
      impl_->import_tokens.insert(token);
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({
          {"import_token", begun.value().token},
          {"expected_index_bytes", begun.value().expected_index_bytes},
      });
    }
    if (operation == "project.import.index") {
      require(exact_keys(
          payload, {"import_token", "offset", "final", "sidecar"}));
      const auto token = uuid_field(payload, "import_token");
      const auto offset = unsigned_field(payload, "offset");
      const auto final = bool_field(payload, "final");
      require_sidecar(payload.at("sidecar"), sidecar);
      const auto appended = impl_->application.append_project_bundle_index(
          token, offset, sidecar, final);
      if (!appended.has_value()) {
        return normalized_error(appended.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (!appended.value().has_value()) {
        return success({
            {"received_index_bytes", offset + sidecar.size()},
            {"final", false},
        });
      }
      const auto& identity = *appended.value();
      return success({
          {"project_id", identity.project_id.value()},
          {"bundle_digest", identity.bundle_digest},
          {"entry_count", identity.entry_count},
      });
    }
    if (operation == "project.import.entry") {
      require(exact_keys(
          payload,
          {"import_token", "entry_index", "offset", "final", "sidecar"}));
      const auto token = uuid_field(payload, "import_token");
      const auto entry_index = unsigned_field(payload, "entry_index", 4'095);
      const auto offset = unsigned_field(payload, "offset");
      const auto final = bool_field(payload, "final");
      require_sidecar(payload.at("sidecar"), sidecar);
      const auto appended = impl_->application.append_project_bundle_entry(
          token,
          static_cast<std::uint32_t>(entry_index),
          offset,
          sidecar,
          final);
      if (!appended.has_value()) {
        return normalized_error(appended.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({
          {"entry_index", entry_index},
          {"received_entry_bytes", offset + sidecar.size()},
          {"final", final},
      });
    }
    if (operation == "project.import.commit") {
      require(exact_keys(payload, {"import_token"}));
      require(sidecar.empty());
      const auto token = uuid_field(payload, "import_token");
      const auto committed =
          impl_->application.commit_project_bundle_import(token);
      impl_->import_tokens.erase(token);
      if (!committed.has_value()) {
        return normalized_error(committed.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success(local_project_summary(committed.value()));
    }
    if (operation == "project.import.abort") {
      require(exact_keys(payload, {"import_token"}));
      require(sidecar.empty());
      const auto token = uuid_field(payload, "import_token");
      const auto aborted =
          impl_->application.abort_project_bundle_import(token);
      impl_->import_tokens.erase(token);
      if (!aborted.has_value()) {
        return normalized_error(aborted.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({{"aborted", true}});
    }
    if (operation == "project.create") {
      require(
          exact_keys(payload, {"project_id", "bpm", "initial_pattern"}) ||
          exact_keys(
              payload,
              {"project_id", "bpm", "initial_pattern", "pattern_transport"}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::running ||
          impl_->active_sequence.has_value() ||
          !impl_->sample_import_tokens.empty()) {
        return state_error();
      }
      const auto project_id = uuid_field(payload, "project_id");
      const auto bpm = unsigned_field(payload, "bpm", 240);
      require(bpm >= 40);
      auto initial_pattern = pattern_value(payload.at("initial_pattern"));
      const bool transport_opted_in = payload.contains("pattern_transport") &&
          bool_field(payload, "pattern_transport");
      if (const auto stopped = impl_->stop_replay_before_command(false)) {
        return *stopped;
      }
      // Project replacement enters the shutdown barrier: an unknown
      // transport closure prevents a clean replacement claim.
      const auto create_barrier = impl_->transport_shutdown_barrier();
      if (!create_barrier.has_value()) {
        return transport_error(create_barrier.error());
      }
      impl_->transport.reset();
      // Pattern transport stays disabled — and Pattern event scheduling
      // untouched — until a session opts in at this quiescent point.
      impl_->transport_opted_in = transport_opted_in;
      if (impl_->transport_opted_in) {
        impl_->enable_pattern_transport_quiescent();
      }
      const auto initial_pattern_id = initial_pattern.id.value();
      const auto path = impl_->project_path(project_id);
      auto lease = impl_->application.acquire_project_writer(path);
      if (!lease.has_value()) {
        return normalized_error(lease.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      auto created = impl_->application.create_initial_project(
          facade::InitialProjectRequest{
              path,
              foundation::ProjectId{project_id},
              static_cast<std::uint16_t>(bpm),
              std::move(initial_pattern),
          });
      if (!created.has_value()) {
        return normalized_error(created.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      impl_->recording_metadata.retire();
      impl_->writer_lease.emplace(std::move(lease.value()));
      impl_->retained_project_path = path;
      impl_->project_id = project_id;
      const auto history = impl_->application.command({
          {"operation", "history.open"}, {"project_path", path.generic_string()},
          {"session_id", generated_uuid()}});
      if (!history.value("ok", false)) return normalized_facade_error(history);
      impl_->project_revision = std::uint64_t{0};
      impl_->pattern_id = initial_pattern_id;
      impl_->project_bpm = static_cast<std::uint16_t>(bpm);
      impl_->runtime_ready = false;
      impl_->runtime_revision.reset();
      impl_->trigger_admission = false;
      impl_->state = Impl::State::core_ready;
      return success({
          {"project_id", project_id},
          {"project_revision", std::uint64_t{0}},
          {"initial_pattern_id", initial_pattern_id},
          {"runtime_ready", false},
      });
    }
    if (operation == "project.duplicate") {
      // Copies a local Project under a new identity. The open Project, its
      // writer lease and the Runtime are untouched; the caller opens the copy.
      // A Project owned by another tab is refused as PROJECT_BUSY, and a
      // refusal, failure or cancellation publishes nothing.
      require(exact_keys(payload, {"source_project_id", "project_id"}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::running ||
          impl_->active_sequence.has_value() ||
          !impl_->sample_import_tokens.empty()) {
        return state_error();
      }
      const auto source_project_id = uuid_field(payload, "source_project_id");
      const auto project_id = uuid_field(payload, "project_id");
      const auto duplicated = impl_->application.duplicate_project(
          facade::ProjectDuplicateRequest{
              foundation::ProjectId{source_project_id},
              foundation::ProjectId{project_id},
          });
      if (!duplicated.has_value()) {
        // The generic sanitizer drops the Facade's scalar `reason`, which
        // would leave an unfinished recording indistinguishable from a
        // malformed request.
        const auto& details = duplicated.error().details;
        const auto reason = details.is_object()
                                ? details.value("reason", std::string{})
                                : std::string{};
        if (reason == "sequence_session_active" ||
            reason == "performance_session_active") {
          return state_error("source Project has an unfinished recording");
        }
        return normalized_error(duplicated.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success(local_project_summary(duplicated.value()));
    }
    if (operation == "project.open") {
      require(
          exact_keys(payload, {"project_id", "pattern_id"}) ||
          exact_keys(
              payload, {"project_id", "pattern_id", "pattern_transport"}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::running ||
          impl_->active_sequence.has_value() ||
          !impl_->sample_import_tokens.empty()) {
        return state_error();
      }
      const auto selected_id = uuid_field(payload, "project_id");
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      const bool transport_opted_in = payload.contains("pattern_transport") &&
          bool_field(payload, "pattern_transport");
      if (const auto stopped = impl_->stop_replay_before_command(false)) {
        return *stopped;
      }
      // Project replacement enters the shutdown barrier: an unknown
      // transport closure prevents a clean replacement claim.
      const auto open_barrier = impl_->transport_shutdown_barrier();
      if (!open_barrier.has_value()) {
        return transport_error(open_barrier.error());
      }
      impl_->transport.reset();
      // Pattern transport stays disabled — and Pattern event scheduling
      // untouched — until a session opts in at this quiescent point.
      impl_->transport_opted_in = transport_opted_in;
      if (impl_->transport_opted_in) {
        impl_->enable_pattern_transport_quiescent();
      }
      const auto path = impl_->project_path(selected_id);
      auto lease = impl_->application.acquire_project_writer(path);
      if (!lease.has_value()) {
        return normalized_error(lease.error());
      }
      const auto inspected = impl_->application.query(
          {{"operation", "project.inspect"},
           {"project_path", path.generic_string()}});
      if (!inspected.value("ok", false)) {
        return normalized_facade_error(inspected);
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto& inspected_project =
          inspected.at("result").at("project");
      if (inspected_project.value("project_id", std::string{}) !=
          selected_id) {
        return host_error(
            "INVALID_PROJECT", "project identity does not match selector");
      }
      const auto switched =
          !impl_->runtime_bank_project_id.has_value() ||
          *impl_->runtime_bank_project_id != selected_id;
      impl_->recording_metadata.retire();
      impl_->writer_lease.emplace(std::move(lease.value()));
      impl_->retained_project_path = path;
      impl_->project_id = selected_id;
      const auto history = impl_->application.command({
          {"operation", "history.open"}, {"project_path", path.generic_string()},
          {"session_id", generated_uuid()}});
      if (!history.value("ok", false)) return normalized_facade_error(history);
      impl_->project_revision =
          inspected.at("project_revision").get<std::uint64_t>();
      impl_->pattern_id = selected_pattern;
      impl_->project_bpm =
          inspected_project.at("bpm").get<std::uint16_t>();
      if (switched) {
        impl_->runtime_ready = false;
        impl_->runtime_revision.reset();
      }
      impl_->state = Impl::State::core_ready;
      const auto snapshot = impl_->prepare_and_publish(selected_pattern);
      if (!snapshot.published) {
        impl_->runtime_ready = false;
        if (!snapshot.resource_rejected) {
          return {{"ok", false}, {"error", snapshot.error}};
        }
        return impl_->open_result(selected_pattern, snapshot);
      }
      return impl_->open_result(selected_pattern, snapshot);
    }
    if (operation == "history.inspect" || operation == "history.undo" || operation == "history.redo") {
      const bool inspect = operation == "history.inspect";
      require(inspect ? exact_keys(payload, {}) :
          exact_keys(payload, {"session_id", "command_id", "expected_revision"}));
      require(sidecar.empty());
      if (!impl_->session_available()) return state_error();
      auto status = impl_->application.query({{"operation", "history.inspect"},
          {"project_path", impl_->retained_project_path->generic_string()}});
      if (!status.value("ok", false)) return normalized_facade_error(status);
      auto& history = status["result"];
      // General history can remove the selected Pattern. The current Host's
      // cross-identity publication contract requires stopped Pattern playback;
      // Undo must never stop or settle a transport on the user's behalf.
      if (impl_->transport != nullptr) {
        const auto transport = impl_->transport->controller->inspect();
        if (transport.playing || transport.recording ||
            transport.phase != facade::PatternTransportPhase::idle ||
            transport.error.has_value() || impl_->transport->publish_pending) {
          history["disabled_reason"] = transport.recording ? "sequence_session_active" : "pattern_transport_busy";
          history["can_undo"] = false;
          history["can_redo"] = false;
        }
      }
      if (inspect) return success(history);
      if (!history.at("disabled_reason").get<std::string>().empty()) return host_error("HOST_STATE_INVALID",
          "Undo/Redo is unavailable until the current authoring operation settles",
          {{"reason", history.at("disabled_reason")}});
      if (impl_->cancel_if_expired()) return timeout_error();
      if (impl_->transport) {
        const auto retired = impl_->transport_shutdown_barrier();
        if (!retired.has_value()) return transport_error(retired.error());
        impl_->transport.reset();
      }
      auto response = impl_->application.command({{"operation", operation},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", uuid_field(payload, "session_id")},
          {"command_id", uuid_field(payload, "command_id")},
          {"expected_revision", unsigned_field(payload, "expected_revision")}});
      if (!response.value("ok", false)) return normalized_facade_error(response);
      impl_->project_revision = response.at("project_revision").get<std::uint64_t>();
      const auto inspected = impl_->application.query({{"operation", "project.inspect"},
          {"project_path", impl_->retained_project_path->generic_string()}});
      Impl::SnapshotResult snapshot;
      if (!inspected.value("ok", false)) {
        snapshot.error = normalized_facade_error(inspected).at("error");
      } else {
        const auto& project = inspected.at("result").at("project");
        impl_->project_bpm = project.at("bpm").get<std::uint16_t>();
        const auto& patterns = project.at("patterns");
        if (!patterns.contains(*impl_->pattern_id) && !patterns.empty()) {
          impl_->pattern_id = patterns.begin().key();
          impl_->transport.reset();
        }
        snapshot = impl_->prepare_and_publish(*impl_->pattern_id, true, true);
        if (snapshot.published && snapshot.generation.has_value()) {
          if (const auto acknowledgement = impl_->await_bank_acknowledgement(*snapshot.generation);
              acknowledgement.has_value()) {
            snapshot.published = false;
            snapshot.error = acknowledgement->at("error");
          }
        }
      }
      Json result{{"committed_revision", *impl_->project_revision},
          {"runtime_revision", impl_->runtime_revision.has_value() ? Json(*impl_->runtime_revision) : Json(nullptr)},
          {"runtime_published", snapshot.published}};
      if (!snapshot.error.is_null()) result["snapshot_error"] = snapshot.error;
      return success(std::move(result));
    }
    if (operation == "pattern.create") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "pattern_id", "bars"}));
      require(sidecar.empty());
      if (!impl_->session_available() || impl_->active_sequence.has_value()) {
        return state_error();
      }
      auto response = impl_->application.command({
          {"operation", "pattern.create"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"command_id", uuid_field(payload, "command_id")},
          {"expected_revision", unsigned_field(payload, "expected_revision")},
          {"pattern_id", uuid_field(payload, "pattern_id")},
          {"bars", unsigned_field(payload, "bars", 8)},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->project_revision =
          response.at("project_revision").get<std::uint64_t>();
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      return success(std::move(result));
    }
    if (operation == "pattern.events.edit") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "pattern_id", "remove", "put"}));
      require(sidecar.empty());
      if (!impl_->session_available() || impl_->active_sequence.has_value()) {
        return state_error();
      }
      const auto edited_pattern = uuid_field(payload, "pattern_id");
      bool playing = false;
      if (impl_->transport != nullptr) {
        // Recording keeps the admission fence it retained, and a transport
        // command in flight owns the next publication; refuse before commit.
        const auto transport = impl_->transport->controller->inspect();
        if (transport.recording) {
          return host_error("HOST_STATE_INVALID",
              "Pattern events cannot change during Pattern transport recording",
              {{"reason", "sequence_session_active"}});
        }
        if (transport.phase != facade::PatternTransportPhase::idle ||
            transport.error.has_value() || impl_->transport->publish_pending) {
          return host_error("HOST_STATE_INVALID",
              "Pattern events can change once the Pattern transport settles",
              {{"reason", "pattern_transport_busy"}});
        }
        playing = transport.playing;
        // A queued playing-state switch owns the engine's next publication;
        // the live republish this edit would make cannot supersede it.
        if (playing && impl_->transport_switch_pending()) {
          return host_error(
              "HOST_STATE_INVALID",
              "Pattern events cannot change while a Pattern switch is "
              "queued on the transport; retry after it lands",
              {{"reason", "pattern_switch_pending"}});
        }
      }
      // A scheduled publication (a BPM change, an Undo, a Pad edit or a
      // reload) was prepared before this edit. An in-place swap cannot
      // supersede it, and a view of another Pattern would apply stale at its
      // boundary; refuse those before commit, as for a transport command. A
      // stopped edit of the current Pattern publishes immediately, which
      // supersedes or follows it.
      const auto edits_current = impl_->pattern_id == edited_pattern;
      const auto pending_pattern = impl_->engine.pending_pattern_id();
      if (impl_->engine.pattern_telemetry().pending_generation != 0 &&
          (edits_current ? playing
                         : pending_pattern.has_value() &&
                               pending_pattern->value() == edited_pattern)) {
        return host_error("HOST_STATE_INVALID",
            "Pattern events can change once the pending Pattern publication applies",
            {{"reason", "pattern_publication_pending"}});
      }
      // A grid edit changes no Bank: a Runtime current before it stays
      // current once the edited view is in place.
      const auto runtime_was_current = impl_->project_revision.has_value() &&
          impl_->runtime_revision == impl_->project_revision;
      if (impl_->cancel_if_expired()) return timeout_error();
      auto response = impl_->application.command({
          {"operation", "pattern.events.edit"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"command_id", uuid_field(payload, "command_id")},
          {"expected_revision", unsigned_field(payload, "expected_revision")},
          {"pattern_id", edited_pattern},
          {"remove", payload.at("remove")},
          {"put", payload.at("put")},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->project_revision =
          response.at("project_revision").get<std::uint64_t>();
      Json result{{"committed_revision", *impl_->project_revision},
                  {"project_revision", *impl_->project_revision},
                  {"pattern_id", edited_pattern},
                  {"replayed", response.at("result").at("replayed")}};
      const auto advance_runtime_revision = [&] {
        impl_->keep_runtime_current(runtime_was_current);
      };
      // The Runtime holds only its current Pattern; another Pattern is
      // prepared from Truth whenever it is selected.
      if (!edits_current) {
        advance_runtime_revision();
        result["publication"] = "none";
        return success(std::move(result));
      }
      result["pattern_publication"] = nullptr;
      if (impl_->replay_holds_runtime()) {
        // The replay holds the Runtime; its end restores this Truth.
        advance_runtime_revision();
        result["publication"] = "deferred";
        return success(std::move(result));
      }
      const auto published = impl_->publish_edited_pattern(
          foundation::PatternId{edited_pattern}, playing);
      if (published.publication.has_value()) {
        advance_runtime_revision();
        result["publication"] = playing ? "live" : "published";
        result["pattern_publication"] = {
            {"generation", published.publication->generation},
            {"activation_frame", published.publication->activation_frame},
        };
      } else if (!published.error.has_value()) {
        // Swaps by itself once a sounding retiring view frees its slot.
        advance_runtime_revision();
        result["publication"] = "deferred";
      } else {
        // The edit is committed; only its Runtime view failed to swap.
        result["publication"] = "failed";
        result["snapshot_error"] = *published.error;
      }
      return success(std::move(result));
    }
    if (operation == "pattern.resize" || operation == "pattern.double" ||
        operation == "pattern.copy") {
      // Pattern length and copy (#1823): one checked commit each.
      const auto copying = operation == "pattern.copy";
      if (operation == "pattern.resize") {
        require(exact_keys(
            payload, {"command_id", "expected_revision", "pattern_id", "bars"}));
      } else if (copying) {
        require(exact_keys(
            payload,
            {"command_id", "expected_revision", "source_pattern_id",
             "pattern_id"}));
      } else {
        require(exact_keys(
            payload, {"command_id", "expected_revision", "pattern_id"}));
      }
      require(sidecar.empty());
      if (!impl_->session_available() || impl_->active_sequence.has_value()) {
        return state_error();
      }
      Json request{
          {"operation", std::string(operation)},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"command_id", uuid_field(payload, "command_id")},
          {"expected_revision", unsigned_field(payload, "expected_revision")},
          {"pattern_id", uuid_field(payload, "pattern_id")},
      };
      if (copying) {
        request["source_pattern_id"] = uuid_field(payload, "source_pattern_id");
      } else if (operation == "pattern.resize") {
        request["bars"] = unsigned_field(payload, "bars", 8);
      }
      const auto changed_pattern = request.at("pattern_id").get<std::string>();
      if (impl_->transport != nullptr) {
        // The decision makes all three unavailable while playing, as a
        // playing length change would move the loop point under the
        // playhead; recording keeps its admission fence and a transport
        // command in flight owns the next publication. Refuse before commit.
        const auto transport = impl_->transport->controller->inspect();
        if (transport.recording) {
          return host_error("HOST_STATE_INVALID",
              "Patterns cannot change length or be copied during Pattern transport recording",
              {{"reason", "sequence_session_active"}});
        }
        if (transport.phase != facade::PatternTransportPhase::idle ||
            transport.error.has_value() || impl_->transport->publish_pending) {
          return host_error("HOST_STATE_INVALID",
              "Patterns can change length or be copied once the Pattern transport settles",
              {{"reason", "pattern_transport_busy"}});
        }
        if (transport.playing) {
          return host_error("HOST_STATE_INVALID",
              "Patterns can change length or be copied once the Pattern transport stops",
              {{"reason", "pattern_transport_playing"}});
        }
      }
      // A copy is a new Pattern and leaves its source unchanged.
      const auto changes_current =
          !copying && impl_->pattern_id == changed_pattern;
      // A scheduled view of the changed, not current, Pattern was prepared
      // before this commit and would apply stale at its boundary, as for a
      // grid edit. The current Pattern publishes immediately, which
      // supersedes or follows a scheduled view.
      const auto pending_pattern = impl_->engine.pending_pattern_id();
      if (!copying && !changes_current &&
          impl_->engine.pattern_telemetry().pending_generation != 0 &&
          pending_pattern.has_value() &&
          pending_pattern->value() == changed_pattern) {
        return host_error("HOST_STATE_INVALID",
            "Patterns can change length once the pending Pattern publication applies",
            {{"reason", "pattern_publication_pending"}});
      }
      // None of them changes a Bank: a Runtime current before the commit
      // stays current once the changed view, if any, is in place.
      const auto runtime_was_current = impl_->project_revision.has_value() &&
          impl_->runtime_revision == impl_->project_revision;
      if (impl_->cancel_if_expired()) return timeout_error();
      auto response = impl_->application.command(request);
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->project_revision =
          response.at("project_revision").get<std::uint64_t>();
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      // The Runtime holds only its current Pattern; another Pattern, or a
      // copy, is prepared from Truth whenever it is selected.
      if (!changes_current) {
        impl_->keep_runtime_current(runtime_was_current);
        result["publication"] = "none";
        return success(std::move(result));
      }
      result["pattern_publication"] = nullptr;
      if (impl_->replay_holds_runtime()) {
        // The replay holds the Runtime; its end restores this Truth.
        impl_->keep_runtime_current(runtime_was_current);
        result["publication"] = "deferred";
        return success(std::move(result));
      }
      // Stopped: the new length applies now, so the next Play loops at it.
      const auto published = impl_->publish_edited_pattern(
          foundation::PatternId{changed_pattern}, false);
      if (published.publication.has_value()) {
        impl_->keep_runtime_current(runtime_was_current);
        result["publication"] = "published";
        result["pattern_publication"] = {
            {"generation", published.publication->generation},
            {"activation_frame", published.publication->activation_frame},
        };
      } else if (!published.error.has_value()) {
        // Swaps by itself once a sounding retiring view frees its slot.
        impl_->keep_runtime_current(runtime_was_current);
        result["publication"] = "deferred";
      } else {
        // The change is committed; only its Runtime view failed to swap.
        result["publication"] = "failed";
        result["snapshot_error"] = *published.error;
      }
      return success(std::move(result));
    }
    if (operation == "pad.colour.set") {
      require(exact_keys(
          payload, {"command_id", "expected_revision", "slot", "colour"}));
      require(sidecar.empty());
      const auto selected_slot = slot_value(payload.at("slot"));
      if (!payload.at("colour").is_null()) {
        (void)unsigned_field(
            payload, "colour", std::numeric_limits<std::uint8_t>::max());
      }
      if (!impl_->session_available() || impl_->active_sequence.has_value()) {
        return state_error();
      }
      if (impl_->transport != nullptr) {
        // A Pad colour changes no audio, so playback admits it. Recording
        // keeps the admission fence it retained, and a settling transport
        // owns the next commit; refuse those before commit, as for every
        // other non-Sequence authoring edit.
        const auto transport = impl_->transport->controller->inspect();
        if (transport.recording) {
          return host_error("HOST_STATE_INVALID",
              "Pad colours cannot change during Pattern transport recording",
              {{"reason", "sequence_session_active"}});
        }
        if (transport.phase != facade::PatternTransportPhase::idle ||
            transport.error.has_value() || impl_->transport->publish_pending) {
          return host_error("HOST_STATE_INVALID",
              "Pad colours can change once the Pattern transport settles",
              {{"reason", "pattern_transport_busy"}});
        }
      }
      // A colour changes no Bank and no Pattern: a Runtime current before it
      // stays current, and nothing is prepared or published.
      const auto runtime_was_current = impl_->project_revision.has_value() &&
          impl_->runtime_revision == impl_->project_revision;
      if (impl_->cancel_if_expired()) return timeout_error();
      auto response = impl_->application.command({
          {"operation", "pad.colour.set"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"command_id", uuid_field(payload, "command_id")},
          {"expected_revision", unsigned_field(payload, "expected_revision")},
          {"slot", {{"bank", selected_slot.bank}, {"pad", selected_slot.pad}}},
          {"colour", payload.at("colour")},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->project_revision =
          response.at("project_revision").get<std::uint64_t>();
      impl_->keep_runtime_current(runtime_was_current);
      return success({{"committed_revision", *impl_->project_revision},
                      {"project_revision", *impl_->project_revision},
                      {"replayed", response.at("result").at("replayed")},
                      {"publication", "none"}});
    }
    if (operation == "project.inspect") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto response = impl_->facade_query(
          {{"operation", "project.inspect"},
           {"project_path", impl_->retained_project_path->generic_string()}});
      if (response.value("ok", false)) {
        impl_->project_revision =
            response.at("result").at("project_revision")
                .get<std::uint64_t>();
      }
      return response;
    }
    if (operation == "sample.inspect") {
      require(exact_keys(payload, {"slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_slot = slot_value(payload.at("slot"));
      auto response = impl_->facade_query(
          {{"operation", "sample.inspect"},
           {"project_path", impl_->retained_project_path->generic_string()},
           {"slot", payload.at("slot")}});
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (response.value("ok", false)) {
        impl_->project_revision =
            response.at("result").at("project_revision")
                .get<std::uint64_t>();
      }
      static_cast<void>(selected_slot);
      return response;
    }
    if (operation == "sample.quota") {
      require(exact_keys(payload, {"slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      static_cast<void>(slot_value(payload.at("slot")));
      auto response = impl_->facade_query(
          {{"operation", "sample.quota"},
           {"project_path", impl_->retained_project_path->generic_string()},
           {"slot", payload.at("slot")}});
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (response.value("ok", false)) {
        impl_->project_revision =
            response.at("result").at("project_revision")
                .get<std::uint64_t>();
      }
      return response;
    }
    if (operation == "sample.waveform") {
      require(exact_keys(payload, {"slot", "window"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      static_cast<void>(slot_value(payload.at("slot")));
      const auto& window = payload.at("window");
      require(exact_keys(
          window, {"start_frame", "end_frame", "bucket_count"}));
      const auto start = unsigned_field(window, "start_frame");
      const auto end = unsigned_field(window, "end_frame");
      const auto buckets = unsigned_field(window, "bucket_count", 512);
      require(start < end && buckets != 0);
      auto response = impl_->facade_query(
          {{"operation", "sample.waveform"},
           {"project_path", impl_->retained_project_path->generic_string()},
           {"slot", payload.at("slot")},
           {"window", window}});
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (response.value("ok", false)) {
        impl_->project_revision =
            response.at("result").at("project_revision")
                .get<std::uint64_t>();
      }
      return response;
    }
    if (operation == "sample.import.begin") {
      require(
          exact_keys(
              payload,
              {"import_token", "command_id", "expected_revision", "slot",
               "asset_id", "byte_length"}) ||
          exact_keys(
              payload,
              {"import_token", "command_id", "expected_revision",
               "sequence_session_id", "slot", "asset_id", "byte_length"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto token = uuid_field(payload, "import_token");
      const auto command_id = uuid_field(payload, "command_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto selected_slot = slot_value(payload.at("slot"));
      const auto asset_id = uuid_field(payload, "asset_id");
      const auto sequence_session_id = payload.contains("sequence_session_id")
          ? std::optional<foundation::SequenceSessionId>{
                foundation::SequenceSessionId{
                    uuid_field(payload, "sequence_session_id")}}
          : std::nullopt;
      const auto byte_length = unsigned_field(
          payload, "byte_length", impl_->limits.maximum_artifact_bytes);
      require(byte_length != 0);
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto begun = impl_->application.begin_sample_import(
          facade::SampleImportBeginRequest{
              token,
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, expected_revision},
              selected_slot,
              foundation::AssetId{asset_id},
              byte_length,
              sequence_session_id,
          });
      if (!begun.has_value()) {
        return normalized_error(begun.error());
      }
      impl_->sample_import_tokens.insert(token);
      impl_->sample_import_slots[token] = selected_slot;
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({
          {"token", begun.value().token},
          {"expected_bytes", begun.value().expected_bytes},
      });
    }
    if (operation == "sample.import.chunk") {
      if (!exact_keys(
              payload,
              {"import_token", "offset", "final", "sidecar"})) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      const auto token = uuid_field(payload, "import_token");
      if (!impl_->session_available() ||
          !impl_->sample_import_tokens.contains(token)) {
        return state_error();
      }
      std::uint64_t offset = 0;
      bool final = false;
      try {
        offset = unsigned_field(payload, "offset");
        final = bool_field(payload, "final");
        require_sidecar(payload.at("sidecar"), sidecar);
        require(
            offset <= std::numeric_limits<std::uint64_t>::max() -
                          sidecar.size());
      } catch (const ProtocolFailure&) {
        impl_->abort_tracked_sample_import(payload);
        throw;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto appended = impl_->application.append_sample_import(
          token, offset, sidecar, final);
      if (!appended.has_value()) {
        impl_->sample_import_tokens.erase(token);
        impl_->sample_import_slots.erase(token);
        return normalized_error(appended.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({
          {"received_bytes", offset + sidecar.size()},
          {"final", final},
      });
    }
    if (operation == "sample.import.commit") {
      if (!exact_keys(payload, {"import_token"})) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      if (!sidecar.empty()) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto token = uuid_field(payload, "import_token");
      const auto found = impl_->sample_import_slots.find(token);
      if (!impl_->sample_import_tokens.contains(token) ||
          found == impl_->sample_import_slots.end()) {
        return normalized_error(Error{
            ErrorCode::invalid_argument,
            "Sample import token is not active",
        });
      }
      const auto selected_slot = found->second;
      if (const auto control =
              impl_->prepare_sample_mutation_controls(selected_slot, true);
          control.has_value()) {
        static_cast<void>(impl_->application.abort_sample_import(token));
        impl_->sample_import_tokens.erase(token);
        impl_->sample_import_slots.erase(token);
        return *control;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto committed = impl_->application.commit_sample_import(token);
      impl_->sample_import_tokens.erase(token);
      impl_->sample_import_slots.erase(token);
      if (!committed.has_value()) {
        return normalized_error(committed.error());
      }
      return impl_->sample_mutation_result(committed.value(), selected_slot);
    }
    if (operation == "sample.import.abort") {
      if (!exact_keys(payload, {"import_token"})) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      if (!sidecar.empty()) {
        impl_->abort_tracked_sample_import(payload);
        protocol_failure();
      }
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto token = uuid_field(payload, "import_token");
      const auto aborted = impl_->application.abort_sample_import(token);
      impl_->sample_import_tokens.erase(token);
      impl_->sample_import_slots.erase(token);
      if (!aborted.has_value()) {
        return normalized_error(aborted.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      return success({{"aborted", true}});
    }
    if (operation == "sample.update_pad") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "slot", "playback"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto command_id = uuid_field(payload, "command_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto selected_slot = slot_value(payload.at("slot"));
      const auto playback = playback_value(payload.at("playback"));
      if (const auto control = impl_->prepare_sample_mutation_controls(
              selected_slot, playback.muted);
          control.has_value()) {
        return *control;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto updated = impl_->application.update_sample_pad(
          facade::SampleUpdateRequest{
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, expected_revision},
              selected_slot,
              playback,
          });
      if (!updated.has_value()) {
        return normalized_error(updated.error());
      }
      return impl_->sample_mutation_result(updated.value(), selected_slot);
    }
    if (operation == "sample.reset_pad") {
      require(exact_keys(
          payload, {"command_id", "expected_revision", "slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto command_id = uuid_field(payload, "command_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto selected_slot = slot_value(payload.at("slot"));
      if (const auto control =
              impl_->prepare_sample_mutation_controls(selected_slot, true);
          control.has_value()) {
        return *control;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto reset = impl_->application.reset_sample_pad(
          facade::SampleResetRequest{
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, expected_revision},
              selected_slot,
          });
      if (!reset.has_value()) {
        return normalized_error(reset.error());
      }
      return impl_->sample_mutation_result(reset.value(), selected_slot);
    }
    if (operation == "pad.delete") {
      require(exact_keys(
          payload, {"command_id", "expected_revision", "slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto command_id = uuid_field(payload, "command_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto selected_slot = slot_value(payload.at("slot"));
      if (const auto control =
              impl_->prepare_sample_mutation_controls(selected_slot, true);
          control.has_value()) {
        return *control;
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto deleted = impl_->application.delete_sample_pad(
          facade::SampleDeleteRequest{
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, expected_revision},
              selected_slot,
          });
      if (!deleted.has_value()) {
        return normalized_error(deleted.error());
      }
      // An exact replay has no cancellation receipt for newer imports.
      for (const auto& token : deleted.value().cancelled_import_tokens) {
        impl_->sample_import_tokens.erase(token);
        impl_->sample_import_slots.erase(token);
      }
      return impl_->sample_mutation_result(deleted.value(), selected_slot);
    }
    if (operation == "sample.preview.set") {
      require(exact_keys(payload, {"slot", "playback"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_slot = slot_value(payload.at("slot"));
      const auto playback = playback_value(payload.at("playback"));
      const auto inspected = impl_->application.inspect_sample(
          facade::SampleInspectRequest{
              *impl_->retained_project_path, selected_slot});
      if (!inspected.has_value()) {
        return normalized_error(inspected.error());
      }
      if (!impl_->runtime_revision.has_value() ||
          !impl_->runtime_bank_project_id.has_value() ||
          impl_->runtime_bank_project_id != impl_->project_id ||
          inspected.value().project_revision != *impl_->runtime_revision) {
        return state_error("runtime Bank is not current");
      }
      const auto resolved =
          impl_->resolve_preview_playback(inspected.value(), playback);
      if (!resolved.has_value()) {
        return normalized_error(resolved.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (const auto control = impl_->enqueue_sample_control(
              audio::PadControlKind::preview_set,
              selected_slot,
              resolved.value());
          control.has_value()) {
        return *control;
      }
      return success({{"accepted", true}});
    }
    if (operation == "sample.preview.clear") {
      require(exact_keys(payload, {"slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_slot = slot_value(payload.at("slot"));
      if (const auto control = impl_->enqueue_sample_control(
              audio::PadControlKind::preview_clear, selected_slot);
          control.has_value()) {
        return *control;
      }
      return success({{"accepted", true}});
    }
    if (operation == "sample.stop") {
      require(exact_keys(payload, {}) || exact_keys(payload, {"slot"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto stop_all = payload.empty();
      const auto selected_slot =
          stop_all ? domain::PadSlotId{0, 0}
                   : slot_value(payload.at("slot"));
      if (const auto control = impl_->enqueue_sample_control(
              stop_all ? audio::PadControlKind::stop_all
                       : audio::PadControlKind::stop_slot,
              selected_slot);
          control.has_value()) {
        return *control;
      }
      return success({
          {"accepted", true},
          {"scope", stop_all ? "all" : "slot"},
      });
    }
    if (operation == "asset.import") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "asset_id", "media_type",
           "sidecar"}));
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto command_id = uuid_field(payload, "command_id");
      const auto revision = unsigned_field(payload, "expected_revision");
      const auto asset_id = uuid_field(payload, "asset_id");
      const auto media_type = string_field(payload, "media_type");
      require(!media_type.empty());
      const auto& declaration = payload.at("sidecar");
      require(exact_keys(
          declaration, {"sidecar_bytes", "sidecar_sha256"}));
      const auto declared_bytes =
          unsigned_field(declaration, "sidecar_bytes");
      const auto declared_sha = string_field(declaration, "sidecar_sha256");
      require(declared_sha.size() == 64 &&
              std::all_of(
                  declared_sha.begin(), declared_sha.end(), [](char value) {
                    return (value >= '0' && value <= '9') ||
                           (value >= 'a' && value <= 'f');
                  }));
      require(declared_bytes == sidecar.size());
      require(sha256(sidecar) == declared_sha);
      if (!impl_->limits.allows_artifact_bytes(sidecar.size())) {
        return host_error(
            "WEB_RUNTIME_RESOURCE_LIMIT",
            "runtime preparation limit exceeded",
            {
                {"resource", "artifact_bytes"},
                {"observed", sidecar.size()},
                {"limit", impl_->limits.maximum_artifact_bytes},
            });
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      auto imported = impl_->application.import_artifact_bytes(
          facade::ArtifactBytesImportRequest{
              *impl_->retained_project_path,
              domain::CommandMeta{
                  foundation::CommandId{command_id}, revision},
              foundation::AssetId{asset_id},
              media_type,
              sidecar,
          });
      if (!imported.has_value()) {
        return normalized_error(imported.error());
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto& applied = imported.value();
      const auto found =
          applied.state.assets.find(foundation::AssetId{asset_id});
      if (found == applied.state.assets.end()) {
        throw std::logic_error("imported Asset is absent from Project state");
      }
      impl_->project_revision = applied.state.revision;
      return success({
          {"asset_id", asset_id},
          {"artifact", found->second.artifact},
          {"committed_revision",
           applied.event.at("revision").get<std::uint64_t>()},
          {"replayed", applied.replayed},
          {"project_revision", applied.state.revision},
      });
    }
    if (operation == "pad.assign") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "slot", "asset_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      uuid_field(payload, "command_id");
      unsigned_field(payload, "expected_revision");
      const auto selected_slot = slot_value(payload.at("slot"));
      if (!payload.at("asset_id").is_null()) {
        uuid_field(payload, "asset_id");
      }
      auto request = payload;
      request["operation"] = "pad.assign";
      request["project_path"] =
          impl_->retained_project_path->generic_string();
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      auto response = impl_->facade_command(std::move(request));
      if (!response.value("ok", false)) {
        return impl_->cancel_if_expired() ? timeout_error() : response;
      }
      auto& result = response.at("result");
      impl_->project_revision =
          result.at("project_revision").get<std::uint64_t>();
      // Admission and the durable identity precede stopping the destination:
      // a stale, missing-Asset or owner refusal must leave live sound alone.
      if (!impl_->request_cancelled()) {
        if (const auto control =
                impl_->prepare_sample_mutation_controls(selected_slot, true);
            control.has_value()) {
          result["runtime_revision"] =
              impl_->runtime_revision.has_value()
                  ? Json(*impl_->runtime_revision) : Json(nullptr);
          result["runtime_published"] = false;
          result["snapshot_error"] = control->at("error");
          return response;
        }
      }
      // A known commit is never converted to a generic cancellation. Publish
      // current Truth, including an identity replay after a later authoring
      // command, and preserve the existing Sample deadline/ACK outcome.
      const auto publication = impl_->sample_mutation_result(
          facade::SampleMutationResult{
              result.at("committed_revision").get<std::uint64_t>(), true},
          selected_slot, true);
      result.update(publication.at("result"));
      result["project_revision"] = *impl_->project_revision;
      return response;
    }
    if (operation == "snapshot.reload") {
      require(exact_keys(payload, {"pattern_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      // A cross-identity republication outside the coordinator would strand
      // the engagement's Pattern binding (its next receipt would fail the
      // journal's fence authority deterministically). Coordinate instead:
      // Refuse while playing, settle otherwise, then proceed. A stopped
      // selection keeps the same engine generation and epoch: preserve its
      // controller/ledger too. The next Record re-anchors through the port's
      // current Pattern; retiring only the controller would erase the epoch
      // authority returned to its Host without resetting the running engine.
      if (impl_->transport != nullptr &&
          foundation::PatternId{selected_pattern} !=
              *impl_->transport->pattern) {
        const auto engaged = impl_->transport->controller->inspect();
        if (engaged.playing) {
          return state_error(
              "the playing Pattern transport session owns Pattern selection; "
              "stop playback before reloading another Pattern");
        }
        if (engaged.recording ||
            engaged.phase != facade::PatternTransportPhase::idle ||
            impl_->transport->publish_pending) {
          const auto barrier = impl_->transport_shutdown_barrier(false);
          if (!barrier.has_value()) {
            return normalized_error(barrier.error());
          }
        }
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      // Running audio does not imply a playing opted-in Pattern transport.
      // A stopped selection must apply on the next callback, otherwise a
      // queued B can survive a return to the still-current A and make Play
      // start the wrong Pattern. Legacy playback retains its Bar publication.
      const auto transport_status = impl_->transport != nullptr
          ? std::optional{impl_->transport->controller->inspect()}
          : std::nullopt;
      const bool immediate_pattern = impl_->transport_opted_in &&
          (!transport_status.has_value() ||
           (!transport_status->playing && !transport_status->recording &&
            transport_status->phase == facade::PatternTransportPhase::idle));
      const auto snapshot = impl_->prepare_and_publish(
          selected_pattern, false, false, immediate_pattern);
      if (!snapshot.published) {
        return {{"ok", false}, {"error", snapshot.error}};
      }
      if (impl_->transport != nullptr) {
        impl_->transport->pattern = foundation::PatternId{selected_pattern};
      }
      if (const auto acknowledgement =
              impl_->await_bank_acknowledgement(*snapshot.generation);
          acknowledgement.has_value()) {
        return *acknowledgement;
      }
      return impl_->open_result(selected_pattern, snapshot);
    }
    if (operation == "snapshot.retry") {
      require(exact_keys(payload, {"pattern_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      if (selected_pattern != *impl_->pattern_id) {
        return state_error("retry Pattern is not current");
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto snapshot = impl_->prepare_and_publish(selected_pattern);
      if (snapshot.published) {
        if (const auto acknowledgement =
                impl_->await_bank_acknowledgement(*snapshot.generation);
            acknowledgement.has_value()) {
          return *acknowledgement;
        }
      }
      return impl_->retry_result(selected_pattern, snapshot);
    }
    if (operation == "audio.activate") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (!impl_->session_available() || !impl_->runtime_ready ||
          !impl_->project_bpm.has_value() ||
          !impl_->runtime_bank_project_id.has_value() ||
          *impl_->runtime_bank_project_id != *impl_->project_id) {
        return state_error();
      }
      if (impl_->state == Impl::State::running) {
        return success({
            {"state", "running"},
            {"changed", false},
            {"generation",
             impl_->engine.bank_telemetry().accepted_publications},
        });
      }
      if (!impl_->coordinator.has_value() ||
          impl_->coordinator->ready == nullptr ||
          !impl_->coordinator->ready(impl_->coordinator->context)) {
        return state_error("audio output is not ready");
      }
      if (impl_->state != Impl::State::core_ready &&
          impl_->state != Impl::State::audio_suspended) {
        return state_error();
      }
      if (impl_->terminal_audio_retirement_requested) {
        return state_error("failed audio retirement cannot be reactivated");
      }
      const auto bank = impl_->engine.bank_telemetry();
      const auto expected_generation = bank.accepted_publications;
      if (expected_generation == 0 ||
          bank.current_generation != expected_generation ||
          bank.pending_publications != 0) {
        return state_error("runtime Bank is not current");
      }
      // Each rollback names its branch so a sealed activation is
      // diagnosable from the SDK's bounded error details (#2345).
      const auto rollback = [this](std::string_view reason) {
        impl_->trigger_admission = false;
        static_cast<void>(impl_->quiesce_and_stop_audio());
        fail_and_seal("audio_activation_failed");
        return internal_error({{"reason", std::string(reason)}});
      };
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      // An Engine stop wipes the transport generation and any wedged
      // reservation; an opted-in session re-arms the port on every activation
      // while the Engine is quiescent. A surviving engagement from before the
      // stop is stale and retires here.
      if (impl_->transport != nullptr) {
        // Retire the original actual-generation owner before asking Native
        // to enable a successor. Enabling first would overwrite its evidence.
        const auto retired = impl_->transport_shutdown_barrier();
        if (!retired.has_value()) return normalized_error(retired.error());
        impl_->transport.reset();
      }
      if (impl_->transport_opted_in) {
        if (impl_->has_pattern_input_owners())
          return normalized_error(Error{ErrorCode::io_error, "Previous Pattern input owners are pending",
              {{"pending", true}, {"reason", "pattern_transport_input_owners_pending"}}});
        impl_->enable_pattern_transport_quiescent();
        if (impl_->count_in_input_negotiated &&
            !impl_->count_in_input_enabled) {
          return rollback("audio_activation_count_in_not_enabled");
        }
      }
      const auto prepared_fx =
          impl_->engine.prepare_master_fx(*impl_->project_bpm);
      if (!prepared_fx.has_value()) {
        return rollback("audio_activation_master_fx_failed");
      }
      impl_->terminal_legacy_quiescent = false;
      const auto started = impl_->engine.start();
      if (!started.has_value()) {
        return rollback("audio_activation_engine_start_failed");
      }
      if (impl_->coordinator->begin_rendering == nullptr) {
        return rollback("audio_activation_begin_unavailable");
      }
      const auto begun = impl_->coordinator->begin_rendering(
          impl_->coordinator->context);
      if (impl_->request_cancelled()) {
        if (!begun.has_value()) {
          impl_->engine.stop();
        }
        fail_and_seal("audio_activation_timeout");
        return timeout_error();
      }
      if (!begun.has_value()) {
        const auto failed = rollback("audio_activation_begin_refused");
        return impl_->request_cancelled() ? timeout_error() : failed;
      }
      const auto deadline = *impl_->request_deadline;
      auto acknowledged = impl_->coordinator->acknowledged_generation(
          impl_->coordinator->context);
      while (acknowledged < expected_generation &&
             impl_->clock_now() < deadline) {
        std::this_thread::yield();
        acknowledged = impl_->coordinator->acknowledged_generation(
            impl_->coordinator->context);
      }
      if (acknowledged != expected_generation) {
        const auto timed_out = impl_->request_cancelled();
        if (timed_out) {
          fail_and_seal("audio_activation_timeout");
          return timeout_error();
        }
        const auto failed = rollback(
            "audio_activation_generation_mismatch");
        return impl_->request_cancelled() ? timeout_error() : failed;
      }
      if (impl_->request_cancelled()) {
        fail_and_seal("audio_activation_timeout");
        return timeout_error();
      }
      impl_->state = Impl::State::running;
      impl_->trigger_admission = true;
      return success({
          {"state", "running"},
          {"changed", true},
          {"generation", expected_generation},
      });
    }
    if (operation == "trigger") {
      require(sidecar.empty());
      if (impl_->count_in_input_enabled)
        return state_error("Negotiated Pattern input requires its companion identity");
      // Exactly the existing Bridge RPC pool bound, reserved before Native
      // acceptance. Expired observers keep their accepted candidate until its
      // actual durable result reconciles; this never enlarges the pool.
      if (impl_->legacy_inputs.size() >= 16)
        return state_error("Retained legacy Pattern input metadata is full");
      if (impl_->transport && impl_->transport->legacy_candidate)
        return normalized_error(Error{ErrorCode::io_error, "An original input is still pending",
            {{"pending", true}, {"reason", "pattern_transport_metadata_full"}}});
      if (exact_keys(payload, {"slot", "kind"})) {
        const auto selected_slot = unsigned_field(payload, "slot", 63);
        require(string_field(payload, "kind") == "release");
        const auto structured_slot = domain::PadSlotId{
            static_cast<std::uint8_t>(selected_slot / 16U),
            static_cast<std::uint8_t>(selected_slot % 16U),
        };
        if (const auto control = impl_->enqueue_sample_control(
                audio::PadControlKind::release, structured_slot);
            control.has_value()) {
          return *control;
        }
        if (impl_->active_sequence.has_value()) {
          const auto recorded = impl_->record_sequence_pad(
              structured_slot, 0, false);
          if (!recorded.has_value()) {
            return normalized_error(recorded.error());
          }
          const auto published = impl_->publish_pending_sequence_overlay();
          if (!published.has_value()) {
            fail_and_seal("sequence_overlay_publication_failed");
            return normalized_error(published.error());
          }
        }
        if (impl_->transport != nullptr &&
            impl_->transport->controller->inspect().recording) {
          const auto admitted =
              impl_->admit_transport_pad(structured_slot, 0, false, success({{"accepted", true}}));
          if (!admitted.has_value()) {
            return normalized_error(admitted.error());
          }
        }
        return success({{"accepted", true}});
      }
      require(exact_keys(payload, {"slot", "velocity"}));
      const auto selected_slot = unsigned_field(payload, "slot", 63);
      const auto velocity = unsigned_field(payload, "velocity", 127);
      require(velocity != 0);
      if (impl_->state != Impl::State::running ||
          !impl_->trigger_admission || !impl_->runtime_ready ||
          impl_->runtime_bank_project_id != impl_->project_id) {
        return state_error();
      }
      const auto sequence = impl_->next_trigger_sequence;
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto enqueued = impl_->engine.enqueue_control(
          audio::PadControlEvent{
              sequence,
              static_cast<std::uint8_t>(selected_slot),
              static_cast<std::uint8_t>(velocity),
              audio::PadControlKind::press,
              {},
          });
      if (enqueued != audio::EnqueueResult::accepted) {
        return state_error(enqueue_failure_message(enqueued));
      }
      ++impl_->next_trigger_sequence;
      if (impl_->active_sequence.has_value()) {
        const auto recorded = impl_->record_sequence_pad(
            domain::PadSlotId{
                static_cast<std::uint8_t>(selected_slot / 16U),
                static_cast<std::uint8_t>(selected_slot % 16U),
            },
            static_cast<std::uint8_t>(velocity),
            true);
        if (!recorded.has_value()) {
          return normalized_error(recorded.error());
        }
        const auto published = impl_->publish_pending_sequence_overlay();
        if (!published.has_value()) {
          fail_and_seal("sequence_overlay_publication_failed");
          return normalized_error(published.error());
        }
      }
      if (impl_->transport != nullptr &&
          impl_->transport->controller->inspect().recording) {
        const auto admitted = impl_->admit_transport_pad(
            domain::PadSlotId{
                static_cast<std::uint8_t>(selected_slot / 16U),
                static_cast<std::uint8_t>(selected_slot % 16U),
            },
            static_cast<std::uint8_t>(velocity),
            true, success({{"sequence", sequence}, {"status", "enqueued"}}));
        if (!admitted.has_value()) {
          return normalized_error(admitted.error());
        }
      }
      return success(
          {{"sequence", sequence}, {"status", "enqueued"}});
    }
    if (operation == "pattern.transport.input.request") {
      require(exact_keys(payload, {"command_id", "runtime_generation", "frame_epoch", "input_serial",
          "slot", "velocity", "kind", "held", "held_press_sequence"}) && sidecar.empty());
      return impl_->request_pattern_input(payload);
    }
    if (operation == "pattern.transport.input.inspect") {
      require(exact_keys(payload, {"command_id", "runtime_generation", "frame_epoch", "ticket", "consume"}) &&
          sidecar.empty());
      return impl_->inspect_pattern_input(payload);
    }
    if (operation == "pattern.transport.count-in.capabilities") {
      require(exact_keys(payload, {"negotiate"}) && sidecar.empty());
      const auto negotiate = bool_field(payload, "negotiate");
      if (negotiate && !impl_->count_in_input_negotiated) {
        if (impl_->engine.telemetry().state != audio::RealtimeState::stopped ||
            impl_->transport != nullptr || impl_->active_sequence.has_value()) {
          return state_error("Pattern input profile requires quiescent activation");
        }
        impl_->count_in_input_negotiated = true;
        if (impl_->transport_opted_in && impl_->enabled_transport_generation != 0) {
          const auto generation = impl_->enabled_transport_generation;
          const auto scheduled = impl_->engine.enable_scheduled_pattern_record(generation);
          const auto inputs = scheduled.has_value()
              ? impl_->engine.enable_pattern_input_profile(generation)
              : foundation::Result<void>::failure(scheduled.error());
          if (!inputs.has_value()) {
            impl_->count_in_input_negotiated = false;
            return normalized_error(inputs.error());
          }
          impl_->count_in_input_enabled = true;
          impl_->initialize_pattern_input_ledger();
        }
      }
      const auto frame_epoch = impl_->engine.telemetry().start_epoch;
      const auto output_ready = impl_->count_in_output &&
          impl_->count_in_output->available(impl_->count_in_output->context);
      return success({{"supported", true},
          {"negotiated", impl_->count_in_input_negotiated},
          {"output_ready", output_ready},
          {"runtime_generation", impl_->enabled_transport_generation != 0
              ? Json(std::to_string(impl_->enabled_transport_generation)) : Json(nullptr)},
          {"frame_epoch", frame_epoch != 0 ? Json(std::to_string(frame_epoch)) : Json(nullptr)},
          {"next_serial", impl_->next_count_in_serial != 0
              ? Json(std::to_string(impl_->next_count_in_serial)) : Json(nullptr)},
          {"input_capacity", impl_->count_in_input_enabled
              ? impl_->engine.pattern_input_profile_status().capacity : audio::kRealtimeQueueCapacity}});
    }
    if (operation == "pattern.transport.count-in.request") {
      require(exact_keys(payload, {"session_id", "project_id", "command_id",
          "runtime_generation", "frame_epoch", "schedule_serial", "expected_epoch",
          "bars", "expected_revision"}) && sidecar.empty());
      const auto session = uuid_field(payload, "session_id");
      const auto project = uuid_field(payload, "project_id");
      const auto command = uuid_field(payload, "command_id");
      const auto generation = nonzero_decimal_field(payload, "runtime_generation");
      const auto frame_epoch = nonzero_decimal_field(payload, "frame_epoch");
      const auto serial = nonzero_decimal_field(payload, "schedule_serial",
          audio::kScheduledPatternSerialMaximum);
      const auto epoch = nonzero_decimal_field(payload, "expected_epoch");
      const auto bars = safe_unsigned_field(payload, "bars", 2);
      require(bars == 1 || bars == 2);
      std::optional<std::uint64_t> revision;
      if (!payload.at("expected_revision").is_null())
        revision = safe_unsigned_field(payload, "expected_revision");
      if (impl_->state != Impl::State::running || !impl_->session_available() ||
          !impl_->count_in_input_enabled || !impl_->transport_opted_in ||
          impl_->active_sequence.has_value() || !impl_->count_in_output ||
          !impl_->count_in_output->available(impl_->count_in_output->context)) {
        return state_error("Native count-in is unavailable for this generation");
      }
      if (project != *impl_->project_id || generation != impl_->enabled_transport_generation ||
          frame_epoch != impl_->engine.telemetry().start_epoch) {
        return state_error("Count-in request belongs to a stale Project or frame epoch");
      }
      if (const auto stopped = impl_->stop_replay_before_command(true)) return *stopped;
      auto* engagement = impl_->ensure_transport_engaged(foundation::SequenceSessionId{session});
      if (engagement == nullptr) return state_error("Pattern transport session is unavailable");
      const auto before = engagement->controller->inspect_count_in();
      const auto replay = before.request &&
          before.request->transport.command_id.value() == command;
      if (!replay && (!engagement->count_in_ticket_consumed ||
          impl_->next_count_in_serial == 0 || serial < impl_->next_count_in_serial)) {
        return state_error("A retained count-in ticket must settle and be consumed first");
      }
      if (impl_->engine.pattern_telemetry().pending_generation != 0 && !replay)
        return state_error("A Pattern publication is pending");
      const facade::ScheduledPatternTransportRequest request{
          {*engagement->session, foundation::ProjectId{project}, foundation::CommandId{command},
              generation, epoch, facade::PatternTransportIntent::record, revision},
          frame_epoch, serial, static_cast<std::uint8_t>(bars)};
      const auto submitted = engagement->controller->request_count_in(request);
      if (submitted != facade::PatternTransportSubmit::accepted &&
          submitted != facade::PatternTransportSubmit::replayed)
        return state_error("Count-in request is busy, stale or refused");
      if (submitted == facade::PatternTransportSubmit::accepted) {
        impl_->next_count_in_serial = serial == audio::kScheduledPatternSerialMaximum ? 0 : serial + 1;
        engagement->count_in_ticket_consumed = false;
        engagement->count_in_cancel_pending = false;
      }
      return success({{"submit", std::string(pattern_transport_submit_name(submitted))},
          {"ticket", scheduled_pattern_ticket_json(request)},
          {"status", scheduled_pattern_status_json(engagement->controller->inspect_count_in())}});
    }
    if (operation == "pattern.transport.count-in.inspect" ||
        operation == "pattern.transport.count-in.cancel") {
      const auto cancel = operation == "pattern.transport.count-in.cancel";
      require((cancel
          ? exact_keys(payload, {"session_id", "project_id", "command_id", "start_command_id",
              "runtime_generation", "frame_epoch", "schedule_serial", "expected_epoch", "intent"})
          : exact_keys(payload, {"session_id", "command_id", "runtime_generation",
              "frame_epoch", "schedule_serial", "consume"})) && sidecar.empty());
      const auto session = uuid_field(payload, "session_id");
      const auto command = uuid_field(payload, cancel ? "start_command_id" : "command_id");
      const auto generation = nonzero_decimal_field(payload, "runtime_generation");
      const auto frame_epoch = nonzero_decimal_field(payload, "frame_epoch");
      const auto serial = nonzero_decimal_field(payload, "schedule_serial",
          audio::kScheduledPatternSerialMaximum);
      if (!impl_->transport || impl_->transport->count_in_ticket_consumed ||
          impl_->transport->session->value() != session ||
          impl_->transport->generation != generation)
        return state_error("Count-in ticket is stale or consumed");
      auto& engagement = *impl_->transport;
      const auto before = engagement.controller->inspect_count_in();
      if (!before.request || before.request->transport.command_id.value() != command ||
          before.request->frame_epoch != frame_epoch || before.request->schedule_serial != serial)
        return state_error("Count-in ticket identity does not match");
      if (cancel) {
        const auto project = uuid_field(payload, "project_id");
        const auto cancel_command = uuid_field(payload, "command_id");
        const auto epoch = nonzero_decimal_field(payload, "expected_epoch");
        const auto intent = string_field(payload, "intent");
        require(intent == "record" || intent == "play_stop");
        if (project != before.request->transport.project_id.value())
          return state_error("Count-in cancellation belongs to another Project");
        const facade::ScheduledPatternTransportCancel request{
            {before.request->transport.session, foundation::ProjectId{project},
                foundation::CommandId{cancel_command}, generation, epoch,
                intent == "record" ? facade::PatternTransportIntent::record
                                   : facade::PatternTransportIntent::play_stop,
                before.request->transport.expected_revision}, frame_epoch, serial};
        const auto submitted = engagement.controller->cancel_count_in(request);
        if (submitted != facade::PatternTransportSubmit::accepted &&
            submitted != facade::PatternTransportSubmit::replayed)
          return state_error("Count-in cancellation is busy, stale or refused");
        engagement.count_in_cancel_pending = true;
        return success({{"submit", std::string(pattern_transport_submit_name(submitted))},
            {"ticket", scheduled_pattern_ticket_json(*before.request)},
            {"status", scheduled_pattern_status_json(engagement.controller->inspect_count_in())}});
      }
      const auto consume = bool_field(payload, "consume");
      if (impl_->state == Impl::State::running)
        static_cast<void>(impl_->transport_continuation_step());
      const auto status = engagement.controller->inspect_count_in();
      const auto result = scheduled_pattern_status_json(status);
      if (consume) {
        const auto ordinary = engagement.controller->inspect();
        const auto native_terminal = status.start_receipt &&
            (status.start_receipt->result != audio::ScheduledPatternResult::applied ||
             (status.cancel_receipt &&
              status.cancel_receipt->result == audio::ScheduledPatternResult::applied &&
              status.cancel_receipt->effective_frame && status.opening_complete &&
              !ordinary.recording && ordinary.phase == facade::PatternTransportPhase::idle &&
              !ordinary.error && !engagement.publish_pending));
        const auto owner = engagement.controller->inspect_input_owner();
        const auto native = impl_->engine.pattern_input_profile_status();
        // Caller acknowledgment of failed evidence is independent of physical
        // owner acknowledgment. Return the original e1/e2/error unchanged only
        // after both actual owners and every input consumer have settled.
        const auto failed_resource_terminal = impl_->state == Impl::State::failed &&
            engagement.shutdown_requested && status.start_receipt && status.cancel_receipt &&
            status.error && ordinary.error && ordinary.phase == facade::PatternTransportPhase::error &&
            owner.runtime_generation == generation && owner.invalidated && owner.disposed &&
            owner.acknowledged && !owner.pending && !owner.held_correlations &&
            impl_->input_owner_revoked_generation == generation &&
            impl_->input_owner_acknowledged_generation == generation &&
            impl_->engine.telemetry().state == audio::RealtimeState::stopped &&
            impl_->engine.telemetry().start_epoch == frame_epoch && native.enabled &&
            native.runtime_generation == generation && !native.ordinary_pending &&
            !native.held_release_reservations && !native.retained_completions &&
            impl_->engine.scheduled_pattern_record_quiescent() &&
            !impl_->has_pattern_input_owners() && impl_->legacy_inputs.empty() &&
            !engagement.legacy_candidate && !engagement.publish_pending;
        const auto io = engagement.controller->inspect_io();
        const auto ingress = engagement.controller->inspect_ingress();
        // A known final opening refusal has no admitted take. Its original S
        // and actual Stop F can be acknowledged once after every real owner
        // has settled, while its error and recovery journal remain unchanged.
        // Unknown closure effects retain their I/O cell and never enter here.
        const auto known_opening_failure_terminal = impl_->state == Impl::State::running &&
            status.request && status.count_in && status.start_receipt && status.cancel_receipt &&
            status.error && ordinary.error && !status.opening_pending && !status.opening_complete &&
            status.error->code == ErrorCode::invalid_argument && ordinary.error->code == ErrorCode::invalid_argument &&
            status.error->details.value("reason", std::string{}) == "admission_opening_deadline_elapsed" &&
            ordinary.error->details.value("reason", std::string{}) == "admission_opening_deadline_elapsed" &&
            status.error->details.value("journal_retained", false) &&
            ordinary.error->details.value("journal_retained", false) &&
            !status.error->details.value("closure_unresolved", false) &&
            !status.error->details.value("retryable", false) &&
            !ordinary.error->details.value("closure_unresolved", false) &&
            !ordinary.error->details.value("retryable", false) &&
            status.start_receipt->runtime_generation == generation && status.start_receipt->frame_epoch == frame_epoch &&
            status.start_receipt->serial == serial &&
            status.start_receipt->epoch == status.request->transport.expected_epoch &&
            status.start_receipt->result == audio::ScheduledPatternResult::applied && status.start_receipt->playing &&
            status.start_receipt->effective_frame && status.start_receipt->origin_frame &&
            status.start_receipt->effective_frame == status.start_receipt->origin_frame &&
            status.cancel_receipt->runtime_generation == generation && status.cancel_receipt->frame_epoch == frame_epoch &&
            status.cancel_receipt->serial == serial && status.cancel_receipt->epoch > status.start_receipt->epoch &&
            status.cancel_receipt->pattern_id == status.start_receipt->pattern_id &&
            status.cancel_receipt->pattern_generation == status.start_receipt->pattern_generation &&
            status.cancel_receipt->result == audio::ScheduledPatternResult::applied && !status.cancel_receipt->playing &&
            status.cancel_receipt->effective_frame && status.cancel_receipt->origin_frame &&
            *status.cancel_receipt->effective_frame > *status.start_receipt->effective_frame &&
            status.cancel_receipt->origin_frame == status.start_receipt->origin_frame &&
            status.count_in->runtime_generation == generation && status.count_in->frame_epoch == frame_epoch &&
            status.count_in->serial == serial && status.count_in->start_frame == status.start_receipt->effective_frame &&
            ordinary.phase == facade::PatternTransportPhase::error && !ordinary.recording && !ordinary.playing &&
            !io.ticket && !io.completion && !io.startup_error && (io.ready || io.stopped) &&
            owner.runtime_generation == generation && !owner.invalidated && !owner.disposed && !owner.acknowledged &&
            !owner.pending && !owner.held_correlations &&
            !ingress.ordinary_pending && !ingress.held_release_metadata && !ingress.retained_tickets &&
            impl_->engine.telemetry().start_epoch == frame_epoch && native.enabled &&
            native.runtime_generation == generation && !native.ordinary_pending &&
            !native.held_release_reservations && !native.retained_completions &&
            impl_->engine.scheduled_pattern_record_settled(generation, frame_epoch, serial) &&
            !impl_->has_pattern_input_owners() && impl_->legacy_inputs.empty() &&
            !engagement.legacy_candidate && engagement.owned_presses.empty() && !engagement.publish_pending &&
            !impl_->pending_transport_switch && impl_->engine.pattern_telemetry().pending_generation == 0;
        if ((!native_terminal && !failed_resource_terminal && !known_opening_failure_terminal) || status.opening_pending ||
            (engagement.count_in_cancel_pending && !status.cancel_receipt))
          return state_error("Count-in evidence is still pending");
        engagement.count_in_ticket_consumed = true;
      }
      return success(result);
    }
    if (operation == "pattern.transport.request") {
      require(exact_keys(
          payload,
          {"session_id", "project_id", "command_id", "expected_epoch",
           "intent", "expected_revision"}));
      require(sidecar.empty());
      if (impl_->state != Impl::State::running ||
          !impl_->session_available() || !impl_->pattern_id.has_value() ||
          !impl_->transport_opted_in ||
          impl_->active_sequence.has_value()) {
        return state_error(
            "Pattern transport was not negotiated for this Project session");
      }
      const auto session_id = uuid_field(payload, "session_id");
      const auto request_project = uuid_field(payload, "project_id");
      const auto command_id = uuid_field(payload, "command_id");
      const auto expected_epoch = unsigned_field(payload, "expected_epoch");
      require(expected_epoch != 0);
      const auto intent_text = string_field(payload, "intent");
      require(intent_text == "play_stop" || intent_text == "record");
      const auto intent =
          intent_text == "record" ? facade::PatternTransportIntent::record
                                  : facade::PatternTransportIntent::play_stop;
      std::optional<std::uint64_t> expected_revision;
      if (!payload.at("expected_revision").is_null()) {
        expected_revision = unsigned_field(payload, "expected_revision");
      }
      if (request_project != *impl_->project_id) {
        return normalized_error(Error{
            ErrorCode::revision_conflict,
            "Pattern transport request belongs to another Project"});
      }
      if (const auto stopped = impl_->stop_replay_before_command(true)) {
        return *stopped;
      }
      auto* engagement =
          impl_->ensure_transport_engaged(
              foundation::SequenceSessionId{session_id});
      if (engagement == nullptr) {
        return state_error("Pattern transport session is unavailable");
      }
      const facade::PatternTransportRequest request{
          *engagement->session,
          foundation::ProjectId{*impl_->project_id},
          foundation::CommandId{command_id},
          engagement->generation,
          expected_epoch,
          intent,
          expected_revision,
      };
      // A pending Pattern publication that no playing engagement fences is not
      // yet current; a transport command submitted against it is refused by
      // the Engine only after the Facade would have durably prepared the
      // admission, which no retry can reuse once the publication applies.
      // Refuse retriably until it applies; a playing engagement names the
      // pending switch in its fence and keeps the designed path. A retained
      // identity instead reaches the Facade's complete replay validation;
      // the lookup itself grants no request or admission authority.
      if (impl_->engine.pattern_telemetry().pending_generation != 0 &&
          !engagement->controller->inspect().playing &&
          !engagement->controller->retains_command_id(request.command_id)) {
        return state_error("a Pattern publication is pending");
      }
      // Begin still waits for a queued switch to land before opening a new
      // admission. An existing recording's Record-off, like Stop, must reach
      // its real Native cutoff promptly and settle/cancel the retained S.
      // A retained command instead reaches complete Core replay validation;
      // this identity lookup grants no authority to a changed payload.
      if (intent == facade::PatternTransportIntent::record &&
          !engagement->controller->inspect().recording &&
          engagement->controller->inspect().playing &&
          !engagement->controller->retains_command_id(request.command_id) &&
          impl_->transport_switch_pending()) {
        return host_error(
            "HOST_STATE_INVALID",
            "Record cannot begin while a Pattern switch is queued on the "
            "transport; retry after it lands",
            {{"reason", "pattern_switch_pending"}});
      }
      const auto submitted = engagement->controller->request(request);
      switch (submitted) {
        case facade::PatternTransportSubmit::accepted:
        case facade::PatternTransportSubmit::replayed:
          break;
        case facade::PatternTransportSubmit::busy:
          return state_error("a Pattern transport operation is pending");
        case facade::PatternTransportSubmit::invalid:
        case facade::PatternTransportSubmit::stale:
          return normalized_error(Error{
              ErrorCode::invalid_argument,
              "Pattern transport request identity is invalid or stale"});
        case facade::PatternTransportSubmit::refused: {
          const auto status = engagement->controller->inspect();
          if (status.error.has_value()) {
            return normalized_error(*status.error);
          }
          return state_error("Pattern transport request is refused");
        }
      }
      // Ordinary Stop/Record-off during a retained schedule is also its e2
      // intent. Consumption must wait for that actual receipt and closure.
      const auto scheduled = engagement->controller->inspect_count_in();
      if (!engagement->count_in_ticket_consumed && scheduled.request &&
          request.expected_epoch > scheduled.request->transport.expected_epoch)
        engagement->count_in_cancel_pending = true;
      // The pending ticket returns through the ordinary serializer here; the
      // tail is released and later inspect/service turns reenter the
      // coordinator for short epoch-checked continuation steps.
      return success({
          {"session_id", session_id},
          {"command_id", command_id},
          {"submit", std::string(pattern_transport_submit_name(submitted))},
          {"status",
           pattern_transport_status_json(
               true,
               engagement->controller->inspect(),
               engagement->publish_pending,
               impl_->engine.telemetry().rendered_frames,
               impl_->current_pattern_id_json(),
               impl_->pending_transport_switch_json())},
      });
    }
    if (operation == "pattern.transport.inspect") {
      require(exact_keys(payload, {"session_id"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      if (impl_->state == Impl::State::running) {
        // Settle the queued playing-state switch before reporting it.
        impl_->observe_transport_switch();
      }
      if (impl_->transport == nullptr ||
          impl_->transport->session->value() != session_id) {
        return success(pattern_transport_status_json(
            false,
            {},
            false,
            impl_->engine.telemetry().rendered_frames,
            impl_->current_pattern_id_json(),
            impl_->pending_transport_switch_json()));
      }
      if (impl_->state == Impl::State::running) {
        // One short continuation step per inspection turn.
        static_cast<void>(impl_->transport_continuation_step());
      }
      const auto pattern_state = impl_->engine.pattern_transport_observation();
      return success(pattern_transport_status_json(
          true,
          impl_->transport->controller->inspect(),
          // Withdrawal clears pending_switch before audio retires its slot.
          // Add only that observed fence to the transport's own completion.
          impl_->transport->publish_pending ||
              (pattern_state && pattern_state->outstanding_cancellation),
          impl_->engine.telemetry().rendered_frames,
          impl_->current_pattern_id_json(),
          impl_->pending_transport_switch_json()));
    }
    if (operation == "pattern.transport.switch") {
      require(exact_keys(payload, {"pattern_id", "request_id"}) ||
          exact_keys(payload, {"pattern_id", "request_id", "snap"}));
      require(sidecar.empty());
      auto snap = audio::PatternSwitchSnap::bar;
      if (payload.contains("snap")) {
        require(payload.at("snap").is_string());
        const auto value = payload.at("snap").get<std::string>();
        require(value == "beat" || value == "bar" || value == "pattern_end");
        snap = value == "beat" ? audio::PatternSwitchSnap::beat
            : value == "pattern_end" ? audio::PatternSwitchSnap::pattern_end
                                    : audio::PatternSwitchSnap::bar;
      }
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      uuid_field(payload, "request_id");
      if (impl_->state != Impl::State::running ||
          !impl_->session_available()) {
        return state_error();
      }
      if (impl_->transport == nullptr) {
        return host_error(
            "HOST_STATE_INVALID",
            "Pattern transport switch needs an engaged Pattern transport",
            {{"reason", "pattern_transport_unavailable"}});
      }
      const auto status = impl_->transport->controller->inspect();
      if (status.phase != facade::PatternTransportPhase::idle ||
          status.error.has_value() || impl_->transport->publish_pending) {
        return host_error(
            "HOST_STATE_INVALID",
            "Pattern transport can switch Patterns once the current "
            "operation settles",
            {{"reason", "pattern_transport_busy"}});
      }
      if (!status.playing) {
        return host_error(
            "HOST_STATE_INVALID",
            "Pattern transport switch needs a playing transport; select "
            "another Pattern with snapshot.reload while stopped",
            {{"reason", "pattern_transport_not_playing"}});
      }
      if (impl_->replay_holds_runtime()) {
        return host_error(
            "HOST_STATE_INVALID",
            "a Performance replay holds the Runtime; switch Patterns after "
            "it ends",
            {{"reason", "performance_replay_active"}});
      }
      // Settle the previous switch first: an applied one retargets this
      // Host's selection and a cancelled one spends its record. Native
      // audio already carries both a claimed predecessor and its successor.
      impl_->observe_transport_switch();
      // Another scheduled publication (a tempo republication, a deferred
      // edit) owns the Engine's next publication; refuse as the sibling
      // authoring operations do instead of racing it.
      if (impl_->foreign_pattern_publication_pending(status.recording)) {
        return host_error(
            "HOST_STATE_INVALID",
            "a scheduled Pattern publication must land before switching "
            "Patterns; retry after it lands",
            {{"reason", "pattern_publication_pending"}});
      }
      const auto target = foundation::PatternId{selected_pattern};
      const auto current = impl_->engine.current_pattern_id();
      if (current.has_value() && *current == target) {
        // The pressed Pattern already plays; any queued switch to another
        // one is withdrawn.
        const auto withdrawn = impl_->withdraw_transport_switch();
        impl_->observe_transport_switch();
        if (impl_->pending_transport_switch.has_value()) {
          return host_error(
              "HOST_STATE_INVALID",
              "the queued Pattern switch reached its boundary",
              {{"reason", "pattern_switch_apply_point"}});
        }
        const auto now_current = impl_->engine.current_pattern_id();
        if (withdrawn && now_current.has_value() && *now_current == target) {
          return success({
              {"pattern_id", selected_pattern},
              {"activation_frame", nullptr},
          });
        }
        // The previous switch landed while this request was served, so the
        // pressed Pattern no longer plays; continue as an ordinary switch
        // back to it.
      }
      if (impl_->pending_transport_switch.has_value() &&
          target == impl_->pending_transport_switch->pattern_id) {
        // An exact repeat of the queued target changes nothing.
        return success({
            {"pattern_id", selected_pattern},
            {"activation_frame",
             impl_->pending_transport_switch->activation_frame},
        });
      }
      const auto observed = impl_->engine.pattern_transport_observation();
      if (!observed) return state_error("Pattern transport observation raced audio; retry");
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
      testing::invoke_cancel_pending_switch_hook();
#endif
      if (impl_->pending_transport_switch) {
        const auto& record = *impl_->pending_transport_switch;
        // Pressing the audio-owned predecessor withdraws only its unclaimed
        // successor. If the handoff won, this is a new switch behind it.
        for (const auto& predecessor : record.predecessors) {
          if (predecessor && predecessor->authority.pattern_id == target &&
              Impl::authority_pending(*observed, predecessor->authority) &&
              impl_->engine.cancel_unclaimed_pattern_publication(
                  Impl::transport_switch_authority(record))) {
            const auto retained = *predecessor;
            impl_->pending_transport_switch = Impl::PendingTransportSwitch{
                target, retained.authority.activation_frame,
                retained.authority.generation, retained.snap, {}};
            return success({{"pattern_id", selected_pattern},
                {"activation_frame", retained.authority.activation_frame}});
          }
        }
      }
      std::optional<facade::PatternTransportSwitchTicket> recording_ticket;
      if (status.recording) {
        const auto reserved = impl_->transport->port.reserve_recording_switch(
            *impl_->transport->controller, {impl_->transport->generation, target});
        if (!reserved.has_value()) {
          const auto reason = reserved.error().details.find("reason");
          // These are producer-owned, public busy reasons. Keep the generic
          // storage sanitizer unchanged and never forward arbitrary details.
          if (reason != reserved.error().details.end() && reason->is_string() &&
              (*reason == "recording_switch_preparation_pending" ||
               *reason == "recording_switch_capacity" ||
               *reason == "recording_switch_material_pending" ||
               *reason == "recording_switch_overlay_pending"))
            return host_error("HOST_STATE_INVALID", "Recording Pattern switch is pending",
                {{"reason", *reason}, {"pending", true}});
          return normalized_error(reserved.error());
        }
        recording_ticket = reserved.value();
      }
      // Reservation, synchronous Facade preparation, Native publication and
      // bind are one control turn. No service continuation enters between them.
      auto pattern = impl_->prepare_project_pattern(target);
      if (!pattern.has_value()) {
        if (recording_ticket)
          static_cast<void>(impl_->transport->controller->abandon_pattern_switch(*recording_ticket));
        return normalized_error(pattern.error());
      }
      std::optional<audio::PatternReplacementAuthority> authority;
      std::array<std::optional<Impl::RememberedTransportSwitch>, 2> predecessors{};
      if (impl_->pending_transport_switch) {
        const auto& record = *impl_->pending_transport_switch;
        authority = Impl::transport_switch_authority(record);
        predecessors[0] = Impl::RememberedTransportSwitch{*authority, record.snap};
        // Keep the possible B/C handoff authorities until a strong native
        // observation identifies which is still live. Both remain exact.
        if (observed->pending_switches[0] &&
            !Impl::same_switch_authority(*observed->pending_switches[0], *authority)) {
          for (const auto& previous : record.predecessors) {
            if (previous && Impl::same_switch_authority(previous->authority,
                    *observed->pending_switches[0])) predecessors[1] = previous;
          }
        }
      }
      auto published = impl_->publish_transport_pattern(
          std::move(pattern.value()), snap, authority, recording_ticket);
      if (!published.has_value()) {
        // A pre-effect refusal abandons the reservation. An unexpected failed
        // binding already retained a real Native lease and must keep its owner.
        const auto accepted = recording_ticket && std::any_of(
            impl_->transport->recording_switches.begin(), impl_->transport->recording_switches.end(),
            [&](const auto& cell) { return cell && cell->ticket == *recording_ticket; });
        if (recording_ticket && !accepted)
          static_cast<void>(impl_->transport->controller->abandon_pattern_switch(*recording_ticket));
        return normalized_error(published.error());
      }
      impl_->pending_transport_switch = Impl::PendingTransportSwitch{
          target, published.value().activation_frame, published.value().generation,
          snap, std::move(predecessors)};
      impl_->observe_transport_switch();
      return success({
          {"pattern_id", selected_pattern},
          {"activation_frame", published.value().activation_frame},
      });
    }
    if (operation == "sequence.record.begin") {
      require(
          exact_keys(
              payload, {"session_id", "pattern_id", "expected_revision"}) ||
          exact_keys(
              payload,
              {"session_id", "pattern_id", "expected_revision",
               "armed_capture_slot"}));
      require(sidecar.empty());
      if (impl_->state != Impl::State::running ||
          !impl_->session_available() || impl_->active_sequence.has_value() ||
          !impl_->project_bpm.has_value()) {
        return state_error();
      }
      // A global-enabled session rejects conflicting direct legacy writes:
      // the transport coordinator is the single journal owner.
      if (impl_->transport != nullptr) {
        return state_error(
            "a global Pattern transport session owns Sequence recording");
      }
      const auto session_id = uuid_field(payload, "session_id");
      const auto selected_pattern = uuid_field(payload, "pattern_id");
      const auto expected_revision =
          unsigned_field(payload, "expected_revision");
      const auto armed_capture_slot =
          !payload.contains("armed_capture_slot") ||
                  payload.at("armed_capture_slot").is_null()
              ? std::optional<domain::PadSlotId>{}
              : std::optional<domain::PadSlotId>{
                    slot_value(payload.at("armed_capture_slot"))};
      const auto runtime_frame =
          impl_->engine.current_pattern_origin_frame();
      if (!runtime_frame.has_value()) {
        return state_error("runtime Pattern clock is unavailable");
      }
      auto response = impl_->application.command({
          {"operation", "sequence.record.begin"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", session_id},
          {"pattern_id", selected_pattern},
          {"expected_revision", expected_revision},
          {"runtime_frame", *runtime_frame},
          {"armed_capture_slot",
           armed_capture_slot.has_value()
               ? nlohmann::json{
                     {"bank", armed_capture_slot->bank},
                     {"pad", armed_capture_slot->pad}}
               : nlohmann::json(nullptr)},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->active_sequence = Impl::SequenceSession{
          foundation::SequenceSessionId{session_id},
          foundation::PatternId{selected_pattern},
          1,
          armed_capture_slot,
      };
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      result["transport_anchor"] = {
          {"runtime_frame", *runtime_frame},
          {"tick_numerator", 0},
          {"bpm", *impl_->project_bpm},
      };
      return success(std::move(result));
    }
    if (operation == "sequence.capture.disarm") {
      require(exact_keys(payload, {"session_id", "slot"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      const auto selected_slot = slot_value(payload.at("slot"));
      require(
          impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() == session_id);
      const auto disarmed = impl_->application.disarm_sequence_capture(
          facade::SequenceCaptureDisarmRequest{
              *impl_->retained_project_path,
              foundation::SequenceSessionId{session_id},
              selected_slot,
          });
      if (!disarmed.has_value()) {
        return normalized_error(disarmed.error());
      }
      impl_->active_sequence->armed_capture_slot.reset();
      return success({{"disarmed", true}});
    }
    if (operation == "sequence.settings.update") {
      require(exact_keys(
          payload,
          {"command_id", "expected_revision", "session_id", "bpm",
           "quantize_enabled", "swing_percent"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      const auto session_id = payload.at("session_id").is_null()
          ? std::optional<std::string>{}
          : std::optional<std::string>{uuid_field(payload, "session_id")};
      if ((impl_->active_sequence.has_value() &&
           (!session_id.has_value() ||
            impl_->active_sequence->id.value() != *session_id)) ||
          (!impl_->active_sequence.has_value() && session_id.has_value())) {
        return state_error();
      }
      // Transport-recorded input keeps the timing authority its admission
      // fence retained; a settings write mid-recording would contradict it.
      if (impl_->transport != nullptr &&
          impl_->transport->controller->inspect().recording) {
        return state_error(
            "Sequence settings cannot change during Pattern transport "
            "recording");
      }
      // A queued playing-state switch owns the engine's next publication; a
      // tempo change would republish the current Pattern over it and seal
      // this Host on the engine's refusal. Swing and Quantize publish
      // nothing and stay allowed.
      if (!payload.at("bpm").is_null() &&
          impl_->transport_switch_pending()) {
        return host_error(
            "HOST_STATE_INVALID",
            "Sequence tempo cannot change while a Pattern switch is queued "
            "on the transport; retry after it lands",
            {{"reason", "pattern_switch_pending"}});
      }
      const auto runtime_frame = impl_->engine.telemetry().rendered_frames;
      // Settings change no Bank: a Runtime current before them stays current.
      const auto runtime_was_current = impl_->project_revision.has_value() &&
          impl_->runtime_revision == impl_->project_revision;
      auto response = impl_->application.command({
          {"operation", "sequence.settings.update"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"command_id", uuid_field(payload, "command_id")},
          {"expected_revision", unsigned_field(payload, "expected_revision")},
          {"session_id", session_id.has_value()
                             ? nlohmann::json(*session_id)
                             : nlohmann::json(nullptr)},
          {"runtime_frame", runtime_frame},
          {"bpm", payload.at("bpm")},
          {"quantize_enabled", payload.at("quantize_enabled")},
          {"swing_percent", payload.at("swing_percent")},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      impl_->project_revision =
          response.at("project_revision").get<std::uint64_t>();
      impl_->project_bpm =
          response.at("result").at("bpm").get<std::uint16_t>();
      nlohmann::json publication = nullptr;
      if (!payload.at("bpm").is_null()) {
        std::optional<audio::PatternPublication> pattern_publication;
        if (impl_->active_sequence.has_value()) {
          auto published = impl_->publish_pending_sequence_overlay(true);
          if (!published.has_value()) {
            fail_and_seal("sequence_settings_publication_failed");
            return normalized_error(published.error());
          }
          pattern_publication = published.value();
        } else if (!impl_->replay_holds_runtime()) {
          // A replay keeps its own tempo; its end restores this Truth.
          auto published = impl_->publish_project_pattern(
              foundation::PatternId{*impl_->pattern_id});
          if (!published.has_value()) {
            fail_and_seal("sequence_settings_publication_failed");
            return normalized_error(published.error());
          }
          pattern_publication = published.value();
        }
        if (pattern_publication.has_value()) {
          publication = {
              {"generation", pattern_publication->generation},
              {"activation_frame", pattern_publication->activation_frame},
          };
        }
      }
      impl_->keep_runtime_current(runtime_was_current);
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      result["pattern_publication"] = std::move(publication);
      return success(std::move(result));
    }
    if (operation == "sequence.record.event") {
      require(exact_keys(payload, {"session_id", "event"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      require(
          impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() == session_id);
      const auto& event = payload.at("event");
      require(exact_keys(event, {"slot", "velocity", "pressed"}));
      const auto selected_slot = slot_value(event.at("slot"));
      const auto velocity = unsigned_field(event, "velocity", 127);
      const auto pressed = bool_field(event, "pressed");
      require((pressed && velocity != 0) || (!pressed && velocity == 0));
      const auto runtime_frame = impl_->engine.telemetry().rendered_frames;
      const auto input_sequence =
          impl_->active_sequence->next_input_sequence;
      auto response = impl_->application.command({
          {"operation", "sequence.record.event"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", session_id},
          {"event",
           {
               {"slot", event.at("slot")},
               {"velocity", velocity},
               {"runtime_frame", runtime_frame},
               {"input_sequence", input_sequence},
               {"pressed", pressed},
           }},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      ++impl_->active_sequence->next_input_sequence;
      const auto published = impl_->publish_pending_sequence_overlay();
      if (!published.has_value()) {
        fail_and_seal("sequence_overlay_publication_failed");
        return normalized_error(published.error());
      }
      auto result = response.at("result");
      result["project_revision"] = response.at("project_revision");
      result["runtime_frame"] = runtime_frame;
      result["input_sequence"] = input_sequence;
      static_cast<void>(selected_slot);
      return success(std::move(result));
    }
    if (operation == "sequence.record.flush" ||
        operation == "sequence.record.stop") {
      require(exact_keys(payload, {"session_id", "command_id"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      const auto command_id = uuid_field(payload, "command_id");
      if (impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() != session_id) {
        return state_error();
      }
      const auto runtime_frame = impl_->engine.telemetry().rendered_frames;
      std::optional<foundation::PatternId> recorded_pattern;
      if (impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() == session_id) {
        recorded_pattern = impl_->active_sequence->pattern_id;
      }
      auto response = impl_->application.command({
          {"operation", std::string(operation)},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", session_id},
          {"command_id", command_id},
          {"runtime_frame", runtime_frame},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      if (response.at("project_revision").is_number_unsigned()) {
        impl_->project_revision =
            response.at("project_revision").get<std::uint64_t>();
      }
      Json pattern_publication = nullptr;
      auto result = response.at("result");
      if (result.contains("committed_pattern_id") &&
          result.at("committed_pattern_id").is_string()) {
        recorded_pattern = foundation::PatternId{
            result.at("committed_pattern_id").get<std::string>()};
      }
      result.erase("committed_pattern_id");
      if (operation == "sequence.record.stop" &&
          impl_->active_sequence.has_value() &&
          impl_->active_sequence->id.value() == session_id) {
        // Facade commit is already terminal even when publication fails. Drop
        // the transient owner now so an exact command replay can recover the
        // clean publication from its durable flush identity.
        impl_->active_sequence.reset();
      }
      if (recorded_pattern.has_value() &&
          (operation == "sequence.record.stop" ||
           !impl_->pending_sequence_boundary.has_value()) &&
          result.at("committed_revision").is_number_unsigned()) {
        const auto authority = impl_->pending_sequence_boundary.has_value()
            ? std::optional<audio::PatternReplacementAuthority>{
                  Impl::replacement_authority(
                      *impl_->pending_sequence_boundary)}
            : std::nullopt;
        if (operation == "sequence.record.stop" && authority.has_value() &&
            !impl_->cancel_pending_switch(*authority)) {
          // Audio already crossed the exact cancellation linearization point.
          // Facade Stop is durable, so clear Runtime fail-closed and leave the
          // receipt replayable instead of allowing the target to remain live.
          impl_->stop_and_clear_pattern_noexcept();
          return normalized_error(Error{
              ErrorCode::invalid_argument,
              "runtime Pattern switch crossed the Stop boundary",
          });
        }
        auto published = impl_->publish_project_pattern(
            *recorded_pattern,
            operation != "sequence.record.stop" && authority.has_value()
                ? std::optional<std::uint64_t>{authority->activation_frame}
                : std::nullopt,
            {},
            operation == "sequence.record.stop" ? std::nullopt : authority);
        if (!published.has_value()) {
          return normalized_error(published.error());
        }
        pattern_publication = {
            {"generation", published.value().generation},
            {"activation_frame", published.value().activation_frame},
        };
      }
      if (operation == "sequence.record.flush" &&
          impl_->active_sequence.has_value() &&
          result.at("pattern_id").is_string()) {
        impl_->active_sequence->pattern_id = foundation::PatternId{
            result.at("pattern_id").get<std::string>()};
        impl_->pattern_id = impl_->active_sequence->pattern_id.value();
        if (result.at("state") != "switching") {
          impl_->pending_sequence_boundary.reset();
        }
      }
      if (operation == "sequence.record.stop") {
        impl_->pending_sequence_boundary.reset();
      }
      result["project_revision"] = response.at("project_revision");
      result["runtime_frame"] = runtime_frame;
      result["pattern_publication"] = std::move(pattern_publication);
      return success(std::move(result));
    }
    if (operation == "sequence.record.switch-request") {
      require(exact_keys(payload, {"session_id", "next_pattern_id"}));
      require(sidecar.empty());
      const auto session_id = uuid_field(payload, "session_id");
      const auto next_pattern_id = uuid_field(payload, "next_pattern_id");
      if (!impl_->active_sequence.has_value() ||
          impl_->active_sequence->id.value() != session_id) {
        return state_error();
      }
      auto pattern = impl_->prepare_project_pattern(
          foundation::PatternId{next_pattern_id});
      if (!pattern.has_value()) {
        return normalized_error(pattern.error());
      }
      const auto runtime_frame = impl_->engine.telemetry().rendered_frames;
      auto response = impl_->application.command({
          {"operation", "sequence.record.switch-request"},
          {"project_path", impl_->retained_project_path->generic_string()},
          {"session_id", session_id},
          {"next_pattern_id", next_pattern_id},
          {"runtime_frame", runtime_frame},
      });
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      auto effective_runtime_frame =
          response.at("result").at("effective_runtime_frame")
              .get<std::uint64_t>();
#if defined(LMDJ_WEB_RUNTIME_TESTING) && LMDJ_WEB_RUNTIME_TESTING
      testing::invoke_sequence_switch_publication_hook();
#endif
      const auto publication_frame =
          impl_->engine.telemetry().rendered_frames;
      if (publication_frame > effective_runtime_frame) {
        response = impl_->application.command({
            {"operation", "sequence.record.switch-request"},
            {"project_path", impl_->retained_project_path->generic_string()},
            {"session_id", session_id},
            {"next_pattern_id", next_pattern_id},
            {"runtime_frame", publication_frame},
        });
        if (!response.value("ok", false)) {
          fail_and_seal("sequence_switch_rebase_failed");
          return normalized_facade_error(response);
        }
        effective_runtime_frame =
            response.at("result").at("effective_runtime_frame")
                .get<std::uint64_t>();
      }
      const auto replacement_authority = impl_->pending_pattern_authority();
      auto published = impl_->publish_prepared_pattern(
          std::move(pattern.value()),
          effective_runtime_frame,
          replacement_authority);
      if (!published.has_value()) {
        fail_and_seal("sequence_switch_publication_failed");
        return normalized_error(published.error());
      }
      auto result = response.at("result");
      if (effective_runtime_frame != published.value().activation_frame) {
        fail_and_seal("sequence_switch_clock_mismatch");
        return internal_error();
      }
      impl_->pending_sequence_boundary = Impl::PendingSequenceBoundary{
          foundation::SequenceSessionId{session_id},
          foundation::PatternId{next_pattern_id},
          published.value().activation_frame,
          published.value().generation,
      };
      result["project_revision"] = response.at("project_revision");
      result["pattern_publication"] = {
          {"generation", published.value().generation},
          {"activation_frame", published.value().activation_frame},
      };
      return success(std::move(result));
    }
    if (operation == "sequence.record.status" ||
        operation == "sequence.recovery.list") {
      require(
          exact_keys(payload, {}) || exact_keys(payload, {"project_id"}));
      require(sidecar.empty());
      std::filesystem::path path;
      if (payload.empty()) {
        if (!impl_->retained_project_path.has_value()) {
          return state_error();
        }
        path = *impl_->retained_project_path;
      } else {
        path = impl_->project_path(uuid_field(payload, "project_id"));
      }
      return impl_->facade_query({
          {"operation", std::string(operation)},
          {"project_path", path.generic_string()},
      });
    }
    if (operation == "sequence.recovery.apply") {
      require(exact_keys(
          payload, {"session_id", "destination_pattern_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      uuid_field(payload, "session_id");
      if (!payload.at("destination_pattern_id").is_null()) {
        uuid_field(payload, "destination_pattern_id");
      }
      auto request = payload;
      request["operation"] = "sequence.recovery.apply";
      request["project_path"] =
          impl_->retained_project_path->generic_string();
      auto response = impl_->application.command(request);
      if (!response.value("ok", false)) {
        return normalized_facade_error(response);
      }
      if (response.at("project_revision").is_number_unsigned()) {
        impl_->project_revision =
            response.at("project_revision").get<std::uint64_t>();
      }
      return normalized_facade_success(response);
    }
    if (operation == "sequence.recovery.discard") {
      require(exact_keys(payload, {"session_id"}));
      require(sidecar.empty());
      if (!impl_->session_available()) {
        return state_error();
      }
      auto request = payload;
      request["operation"] = "sequence.recovery.discard";
      request["project_path"] =
          impl_->retained_project_path->generic_string();
      return impl_->facade_command(std::move(request));
    }
    if (operation == "audio.suspend") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      if (impl_->state == Impl::State::audio_suspended) {
        return success({
            {"state", "audio-suspended"},
            {"changed", false},
            {"stopped_sequence_id", nullptr},
        });
      }
      if (impl_->state != Impl::State::running) {
        return state_error();
      }
      if (!impl_->coordinator.has_value() ||
          impl_->coordinator->await_quiescent == nullptr) {
        impl_->seal_all_noexcept();
        impl_->state = Impl::State::failed;
        impl_->trigger_admission = false;
        return state_error("audio quiescence is unavailable");
      }
      std::optional<std::string> stopped_sequence;
      std::optional<Error> sequence_failure;
      if (impl_->active_sequence.has_value()) {
        stopped_sequence = impl_->active_sequence->id.value();
        const auto stopped = impl_->stop_active_sequence();
        if (!stopped.has_value()) {
          sequence_failure = stopped.error();
        }
      }
      // Explicit Suspend enters the shutdown barrier while audio still runs:
      // acknowledged Pattern Stop, admission closure and journal settlement
      // precede the lifecycle effect.
      bool transport_settled_recording = false;
      if (impl_->transport != nullptr) {
        transport_settled_recording =
            impl_->transport->controller->inspect().recording ||
            impl_->transport->publish_pending;
      }
      const auto barrier = impl_->transport_shutdown_barrier();
      if (!barrier.has_value()) {
        if (barrier.error().details.value("pending", false))
          return transport_error(barrier.error());
        sequence_failure = barrier.error();
      } else {
        // A pre-engagement input owns the same lifecycle barrier even though
        // no Creator supplied a session/controller. Settled workers retire
        // only after their true stopped acknowledgment.
        impl_->transport.reset();
      }
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      const auto had_pending_pattern =
          impl_->engine.pending_pattern_id().has_value();
      const auto cleanup = impl_->quiesce_and_stop_audio();
      if (impl_->cancel_if_expired()) {
        return timeout_error();
      }
      if (!sequence_failure.has_value() && cleanup.has_value() &&
          (stopped_sequence.has_value() || had_pending_pattern ||
           transport_settled_recording) &&
          impl_->pattern_id.has_value()) {
        const auto refreshed =
            impl_->prepare_and_publish(*impl_->pattern_id, true);
        if (!refreshed.published) {
          sequence_failure = Error{
              ErrorCode::internal_error,
              "stopped Sequence Pattern could not be published",
          };
        }
      }
      if (sequence_failure.has_value() || !cleanup.has_value()) {
        const auto failure = sequence_failure.has_value()
                                 ? *sequence_failure
                                 : cleanup.error();
        fail_and_seal("audio_suspend_failed");
        return normalized_error(failure);
      }
      impl_->state = Impl::State::audio_suspended;
      return success({
          {"state", "audio-suspended"},
          {"changed", true},
          {"stopped_sequence_id",
           stopped_sequence.has_value() ? Json(*stopped_sequence)
                                        : Json(nullptr)},
      });
    }
    if (operation == "host.close") {
      require(exact_keys(payload, {}));
      require(sidecar.empty());
      impl_->recording_metadata.retire();
      std::optional<std::string> stopped_sequence;
      std::optional<Error> close_failure;
      bool close_timed_out = false;
      const auto observe_timeout = [&] {
        if (!impl_->request_cancelled()) {
          return;
        }
        close_timed_out = true;
        impl_->trigger_admission = false;
        impl_->seal_all_noexcept();
        impl_->state = Impl::State::failed;
      };
      if (impl_->state == Impl::State::running) {
        if (!impl_->coordinator.has_value() ||
            impl_->coordinator->await_quiescent == nullptr) {
          impl_->seal_all_noexcept();
          impl_->state = Impl::State::failed;
          return state_error("audio quiescence is unavailable");
        }
        if (impl_->active_sequence.has_value()) {
          stopped_sequence = impl_->active_sequence->id.value();
          const auto stopped = impl_->stop_active_sequence();
          if (!stopped.has_value()) {
            close_failure = stopped.error();
          }
        }
        // Disposal enters the same shutdown barrier as Suspend: the Pattern
        // transport journal settles before the lifecycle effect, and an
        // unknown closure fails the close instead of claiming it clean.
        const auto barrier = impl_->transport_shutdown_barrier();
        if (!barrier.has_value()) {
          if (barrier.error().details.value("pending", false))
            return transport_error(barrier.error());
          close_failure = barrier.error();
        }
        observe_timeout();
        if (close_timed_out) {
          return timeout_error();
        }
        const auto cleanup = impl_->quiesce_and_stop_audio();
        if (!cleanup.has_value()) {
          // Bank release is also a quiescent mutation. Do not run it merely
          // because the operational observer returned, or overwrite a prior
          // genuine sequence failure with a later cleanup error.
          const auto failure = close_failure ? *close_failure : cleanup.error();
          fail_and_seal("host_close_failed");
          return normalized_error(failure);
        }
      }
      const auto imports_released = impl_->abort_imports();
      if (!imports_released.has_value() && !close_failure.has_value()) {
        close_failure = imports_released.error();
      }
      observe_timeout();
      const auto released = impl_->release_runtime_banks();
      observe_timeout();
      if (close_timed_out) {
        return timeout_error();
      }
      if (!released.has_value()) {
        fail_and_seal("host_close_bank_release_failed");
        return normalized_error(released.error());
      }
      if (close_failure.has_value()) {
        fail_and_seal("host_close_failed");
        return normalized_error(*close_failure);
      }
      const auto final_barrier = impl_->transport_shutdown_barrier();
      if (!final_barrier.has_value()) return transport_error(final_barrier.error());
      impl_->trigger_admission = false;
      impl_->state = Impl::State::closed;
      (void)impl_->application.command({{"operation", "history.close"}});
      impl_->writer_lease.reset();
      // The barrier has already settled or failed the engagement by this
      // point; a closed Host reports no transport state.
      impl_->transport.reset();
      return success({
          {"state", "closed"},
          {"stopped_sequence_id",
           stopped_sequence.has_value() ? Json(*stopped_sequence)
                                        : Json(nullptr)},
      });
    }
    return protocol_error();
  } catch (const ProtocolFailure&) {
    return protocol_error();
  } catch (...) {
    fail_and_seal("unexpected_exception");
    return internal_error({{"reason", "unexpected_exception"}});
  }
}

std::vector<audio::RuntimeTriggerOutcomeEvent>
ControlRuntime::drain_outcomes() {
  if (!validate_realtime_health()) {
    return {};
  }
  std::vector<audio::RuntimeTriggerOutcomeEvent> result;
  result.reserve(64);
  std::array<audio::RuntimeTriggerOutcomeEvent, 64> batch{};
  const auto count = impl_->engine.drain_trigger_outcomes(batch);
  if (count > batch.size()) {
    fail_and_seal("trigger_outcome_batch_overflow");
    return {};
  }
  for (std::size_t index = 0; index < count; ++index) {
    // The negotiated profile uses its retained total completion channel.
    // Unnegotiated Hosts retain the exact old outcome stream and schema.
    if (!impl_->count_in_input_enabled) result.push_back(batch[index]);
  }
  if (!validate_realtime_health()) {
    return {};
  }
  return result;
}

std::optional<SequenceBarBoundaryEvent>
ControlRuntime::drain_sequence_bar_boundary() {
  if (!impl_->pending_sequence_boundary.has_value()) {
    return std::nullopt;
  }
  const auto telemetry = impl_->engine.pattern_telemetry();
  auto& pending = *impl_->pending_sequence_boundary;
  if (pending.notified) {
    return std::nullopt;
  }
  if (telemetry.current_generation != pending.generation ||
      impl_->engine.telemetry().rendered_frames < pending.runtime_frame) {
    return std::nullopt;
  }
  SequenceBarBoundaryEvent result{
      pending.session_id.value(),
      pending.pattern_id.value(),
      pending.runtime_frame,
      pending.generation,
  };
  pending.notified = true;
  return result;
}

void ControlRuntime::service_pattern_transport() noexcept {
  try {
    if (impl_->state == Impl::State::closed) {
      return;
    }
    impl_->service_terminal_audio_retirement();
    // An audio interruption retires the engagement but not a deferral.
    impl_->service_pattern_inputs();
    if (impl_->state == Impl::State::failed &&
        impl_->engine.telemetry().state == audio::RealtimeState::stopped) {
      // The controller's real I/O worker also belongs to an unnegotiated
      // legacy Play engagement. Its shutdown intent cannot depend on a
      // negotiated Pattern input generation or spend any physical/caller ACK.
      if (impl_->transport && !impl_->transport->shutdown_requested) {
        auto& engagement = *impl_->transport;
        engagement.controller->request_shutdown();
        engagement.shutdown_requested = true;
        if (!engagement.count_in_ticket_consumed)
          engagement.count_in_cancel_pending = true;
      }
      static_cast<void>(impl_->acknowledge_pattern_input_owner_quiescent(impl_->input_ledger_generation));
    }
    impl_->retry_deferred_pattern_edit();
    // The queued playing-state switch follows native apply on the same
    // cadence; native audio already owns any claimed-safe successor.
    impl_->observe_transport_switch();
    if (impl_->transport == nullptr) {
      return;
    }
    const auto status = impl_->transport->controller->inspect();
    // An open recording keeps the cadence alive even while idle: the
    // coordinator publishes the pending overlay from continue_operation
    // (#1513), and its own pending flag makes the steady-state call O(1).
    const auto ingress = impl_->transport->controller->inspect_ingress();
    if (status.phase == facade::PatternTransportPhase::idle &&
        !impl_->transport->publish_pending && !status.recording &&
        !impl_->transport->legacy_candidate && !impl_->transport->shutdown_requested &&
        !impl_->has_recording_switches() &&
        ingress.ordinary_pending == 0 && ingress.retained_tickets == 0) {
      return;
    }
    // A continuation failure is retained on the coordinator and surfaced
    // through pattern.transport.inspect; it is not render- or bridge-fatal.
    static_cast<void>(impl_->transport_continuation_step());
  } catch (...) {
  }
}

bool ControlRuntime::pattern_transport_pending() const noexcept {
  if (impl_->terminal_native_stop_pending ||
      impl_->terminal_pattern_clear_pending) return true;
  if (!impl_->legacy_inputs.empty()) return true;
  if (impl_->has_pattern_input_owners()) return true;
  if (impl_->transport == nullptr) {
    return false;
  }
  return !impl_->transport->count_in_ticket_consumed ||
         impl_->has_recording_switches() ||
         impl_->transport->publish_pending ||
         impl_->transport->legacy_candidate.has_value() ||
         (impl_->transport->shutdown_requested && !impl_->transport->controller->shutdown_complete()) ||
         impl_->transport->controller->inspect_ingress().retained_tickets != 0 ||
         impl_->transport->controller->inspect().phase !=
             facade::PatternTransportPhase::idle;
}

bool ControlRuntime::pattern_transport_shutdown_complete() const noexcept {
  if (impl_->terminal_native_stop_pending || impl_->terminal_pattern_clear_pending ||
      (impl_->terminal_audio_retirement_requested &&
       (impl_->physical_audio ? !impl_->physical_audio->physically_quiescent(
           impl_->physical_audio->context) : !impl_->terminal_legacy_quiescent))) return false;
  if (impl_->engine.telemetry().state != audio::RealtimeState::stopped ||
      impl_->has_pattern_input_owners() || !impl_->legacy_inputs.empty()) return false;
  const auto input = impl_->engine.pattern_input_profile_status();
  if (input.ordinary_pending || input.held_release_reservations || input.retained_completions ||
      !impl_->engine.scheduled_pattern_record_quiescent()) return false;
  if (!impl_->transport) return true;
  const auto& engagement = *impl_->transport;
  const auto ingress = engagement.controller->inspect_ingress();
  const auto owner = engagement.controller->inspect_input_owner();
  return engagement.controller->shutdown_complete() && engagement.count_in_ticket_consumed &&
      !impl_->has_recording_switches() &&
      !engagement.legacy_candidate &&
      !engagement.publish_pending && !ingress.ordinary_pending &&
      !ingress.held_release_metadata && !ingress.retained_tickets && !owner.held_correlations &&
      (!owner.invalidated || (owner.disposed && !owner.pending &&
          (!input.enabled || owner.acknowledged)));
}

bool ControlRuntime::acknowledge_pattern_input_owner_quiescent(std::uint64_t generation) noexcept {
  try { return impl_->acknowledge_pattern_input_owner_quiescent(generation); }
  catch (...) { return false; }
}

std::vector<audio::RuntimeVoiceStateEvent>
ControlRuntime::drain_voice_states() {
  if (!validate_realtime_health()) {
    return {};
  }
  std::vector<audio::RuntimeVoiceStateEvent> result;
  result.reserve(64);
  std::array<audio::RuntimeVoiceStateEvent, 64> batch{};
  const auto count = impl_->engine.drain_voice_states(batch);
  if (count > batch.size()) {
    fail_and_seal("voice_state_batch_overflow");
    return {};
  }
  for (std::size_t index = 0; index < count; ++index) {
    result.push_back(batch[index]);
  }
  if (!validate_realtime_health()) {
    return {};
  }
  return result;
}

foundation::Result<void> ControlRuntime::drain_capture() {
  if (!validate_realtime_health()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "realtime capture health check failed",
    });
  }
  std::array<audio::CapturedTriggerEvent, 64> discarded{};
  while (impl_->engine.drain_capture(discarded) != 0) {
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> ControlRuntime::service_performance() {
  try {
    return impl_->service_performance();
  } catch (...) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::internal_error,
        "Web Performance service failed unexpectedly",
    });
  }
}

bool ControlRuntime::validate_realtime_health() noexcept {
  if (impl_->state == Impl::State::failed) {
    return false;
  }
  const auto capture = impl_->engine.capture_telemetry();
  if (capture.capture_drops != 0 ||
      capture.state == audio::CaptureState::corrupted) {
    fail_and_seal("capture_drop");
    return false;
  }
  if (impl_->engine.trigger_outcome_telemetry().runtime_outcome_drops != 0) {
    fail_and_seal("trigger_outcome_drop");
    return false;
  }
  const auto voice_state = impl_->engine.voice_state_telemetry();
  if (voice_state.voice_state_drops != 0 ||
      voice_state.state == audio::RuntimeVoiceStateStreamState::corrupted) {
    fail_and_seal("voice_state_drop");
    return false;
  }
  return true;
}

void ControlRuntime::fail_and_seal(std::string_view) noexcept {
  impl_->recording_metadata.retire();
  if (impl_->state == Impl::State::closed) return;
  impl_->trigger_admission = false;
  impl_->seal_all_noexcept();
  impl_->state = Impl::State::failed;
}

void ControlRuntime::fail_and_seal(
    std::string_view cause, AbsoluteRequestDeadline original_deadline) noexcept {
  const auto ambient_deadline = impl_->request_deadline;
  impl_->request_deadline = original_deadline.value;
  fail_and_seal(cause);
  impl_->request_deadline = ambient_deadline;
}

bool ControlRuntime::failed() const noexcept {
  return impl_->state == Impl::State::failed;
}

audio::RealtimeEngine& ControlRuntime::engine() noexcept {
  return impl_->engine;
}

#if !defined(__EMSCRIPTEN__)
namespace detail {
nlohmann::json normalize_error_for_testing(const foundation::Error& error) {
  return normalized_error(error);
}
}  // namespace detail
#endif

foundation::Result<void> detail::ControlRuntimeAudioAccess::install(
    ControlRuntime& runtime,
    AudioQuiescenceCoordinator coordinator) noexcept {
  if (coordinator.context == nullptr ||
      coordinator.await_quiescent == nullptr ||
      coordinator.begin_rendering == nullptr || coordinator.ready == nullptr ||
      coordinator.acknowledged_generation == nullptr) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "audio quiescence coordinator is invalid",
    });
  }
  if (runtime.impl_->state == ControlRuntime::Impl::State::closed ||
      runtime.impl_->state == ControlRuntime::Impl::State::failed) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "audio quiescence coordinator cannot be installed",
    });
  }
  runtime.impl_->coordinator = coordinator;
  if (runtime.impl_->physical_audio &&
      runtime.impl_->physical_audio->context != coordinator.context) {
    runtime.impl_->physical_audio.reset();
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> detail::ControlRuntimeCountInOutputAccess::install(
    ControlRuntime& runtime, CountInOutputCapability capability) noexcept {
  if (capability.context == nullptr || capability.available == nullptr ||
      runtime.impl_->state == ControlRuntime::Impl::State::closed ||
      runtime.impl_->state == ControlRuntime::Impl::State::failed) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument, "native count-in output capability is invalid"});
  }
  runtime.impl_->count_in_output = capability;
  return foundation::Result<void>::success();
}

foundation::Result<void> detail::ControlRuntimePhysicalAudioAccess::install(
    ControlRuntime& runtime,
    AudioPhysicalQuiescenceCapability capability) noexcept {
  if (capability.context == nullptr ||
      capability.request_terminal_drain == nullptr ||
      capability.physically_quiescent == nullptr ||
      runtime.impl_->terminal_audio_retirement_requested ||
      runtime.impl_->state == ControlRuntime::Impl::State::running ||
      runtime.impl_->state == ControlRuntime::Impl::State::closed ||
      runtime.impl_->state == ControlRuntime::Impl::State::failed ||
      (runtime.impl_->coordinator &&
       runtime.impl_->coordinator->context != capability.context) ||
      (runtime.impl_->physical_audio &&
       runtime.impl_->physical_audio->context != capability.context)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "physical audio capability is invalid or belongs to another adapter",
    });
  }
  runtime.impl_->physical_audio = capability;
  return foundation::Result<void>::success();
}

foundation::Result<void> detail::ControlRuntimeClockAccess::install(
    ControlRuntime& runtime,
    ControlRuntimeClock clock) noexcept {
  if (clock.context == nullptr || clock.now == nullptr) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Control Runtime clock is invalid",
    });
  }
  if (runtime.impl_->state == ControlRuntime::Impl::State::closed ||
      runtime.impl_->state == ControlRuntime::Impl::State::failed) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Control Runtime clock cannot be installed",
    });
  }
  runtime.impl_->clock = clock;
  return foundation::Result<void>::success();
}

bool detail::ControlRuntimePatternIoAccess::idle(
    const ControlRuntime& runtime) noexcept {
  try {
    if (!runtime.impl_->transport || !runtime.impl_->transport->controller)
      return true;
    const auto status = runtime.impl_->transport->controller->inspect_io();
    return !status.ticket &&
           (status.ready || status.stopped || status.startup_error.has_value());
  } catch (...) {
    return false;
  }
}

bool detail::ControlRuntimePatternIoAccess::stopped(
    const ControlRuntime& runtime) noexcept {
  try {
    // No engagement is not evidence that an admitted worker has stopped.
    return runtime.impl_->transport && runtime.impl_->transport->controller &&
        runtime.impl_->transport->controller->inspect_io().stopped;
  } catch (...) {
    return false;
  }
}

detail::ControlRuntimeSnapshotTruth
detail::ControlRuntimeSnapshotAccess::read(
    const ControlRuntime& runtime) noexcept {
  return {
      runtime.impl_->project_revision,
      runtime.impl_->runtime_revision,
  };
}

}  // namespace lmdj::web_runtime
