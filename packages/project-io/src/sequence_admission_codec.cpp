#include "sequence_admission_codec.hpp"

#include <algorithm>
#include <array>
#include <limits>
#include <set>
#include <stdexcept>
#include <type_traits>
#include <lmdj/foundation/json.hpp>
#include <picosha2.h>

namespace lmdj::project_io::admission_codec {
namespace {
using Json = nlohmann::json;

void require(bool valid, const char* message) {
  if (!valid) throw std::runtime_error(message);
}
template <typename T> struct Optional : std::false_type {};
template <typename T> struct Optional<std::optional<T>> : std::true_type {};
template <typename T> struct Vector : std::false_type {};
template <typename T> struct Vector<std::vector<T>> : std::true_type {};

template <typename T> Json value_json(const T& value) {
  if constexpr (Optional<T>::value) {
    return value ? value_json(*value) : Json(nullptr);
  } else if constexpr (Vector<T>::value) {
    auto out = Json::array();
    for (const auto& item : value) out.push_back(value_json(item));
    return out;
  } else if constexpr (std::is_enum_v<T>) {
    return static_cast<std::uint8_t>(value);
  } else if constexpr (requires { encode(value); }) {
    return encode(value);
  } else {
    return Json(value);
  }
}

template <typename T> T decode(const Json& input) {
  if constexpr (std::is_same_v<T, bool>) {
    require(input.is_boolean(), "admission boolean is invalid");
    return input.get<bool>();
  } else if constexpr (std::is_integral_v<T>) {
    require(input.is_number_unsigned() ||
                (input.is_number_integer() && input.get<std::int64_t>() >= 0),
            "admission integer must be unsigned");
    const auto n = input.get<std::uint64_t>();
    require(n <= std::numeric_limits<T>::max(), "admission integer overflow");
    return static_cast<T>(n);
  } else if constexpr (std::is_enum_v<T>) {
    return static_cast<T>(decode<std::uint8_t>(input));
  } else if constexpr (Optional<T>::value) {
    if (input.is_null()) return std::nullopt;
    return decode<typename T::value_type>(input);
  } else if constexpr (Vector<T>::value) {
    require(input.is_array(), "admission array is invalid");
    T out;
    for (const auto& item : input) out.push_back(decode<typename T::value_type>(item));
    return out;
  } else {
    return input.get<T>();
  }
}

template <> domain::PadSlotId decode<domain::PadSlotId>(const Json& input) {
  require(input.is_object() && input.size() == 2, "invalid domain::PadSlotId shape");
  return {decode<std::uint8_t>(input.at("bank")),
          decode<std::uint8_t>(input.at("pad"))};
}

template <> domain::PatternEvent decode<domain::PatternEvent>(const Json& input) {
  require(input.is_object() && input.size() == 4, "invalid domain::PatternEvent shape");
  return {decode<domain::PadSlotId>(input.at("slot")),
          decode<std::uint32_t>(input.at("onset_tick")),
          decode<std::uint32_t>(input.at("duration_tick")),
          decode<std::uint8_t>(input.at("velocity"))};
}

template <> SequenceAdmissionIdentity decode<SequenceAdmissionIdentity>(const Json& input) {
  require(input.is_object() && input.size() == 3, "invalid SequenceAdmissionIdentity shape");
  return {decode<foundation::CommandId>(input.at("operation_id")),
          decode<std::uint64_t>(input.at("runtime_generation")),
          decode<std::uint64_t>(input.at("transport_epoch"))};
}

template <> SequenceAdmissionPreparation decode<SequenceAdmissionPreparation>(const Json& input) {
  require(input.is_object() && input.size() == 10, "invalid SequenceAdmissionPreparation shape");
  return {decode<SequenceAdmissionIdentity>(input.at("identity")),
          decode<foundation::ProjectId>(input.at("project_id")),
          decode<foundation::PatternId>(input.at("pattern_id")),
          decode<std::uint64_t>(input.at("publication_generation")),
          decode<std::uint64_t>(input.at("first_watermark")),
          decode<std::uint32_t>(input.at("candidate_limit")),
          decode<std::uint32_t>(input.at("candidate_byte_limit")),
          decode<std::uint32_t>(input.at("fence_timeout_ms")),
          decode<bool>(input.at("quantize_enabled")),
          decode<std::uint8_t>(input.at("swing_percent"))};
}

template <> SequenceAdmissionCandidate decode<SequenceAdmissionCandidate>(const Json& input) {
  require(input.is_object() && input.size() == 6, "invalid SequenceAdmissionCandidate shape");
  return {decode<std::uint64_t>(input.at("watermark")),
          decode<std::uint64_t>(input.at("runtime_frame")),
          decode<domain::PadSlotId>(input.at("slot")),
          decode<SequenceCandidateKind>(input.at("kind")),
          decode<std::uint8_t>(input.at("velocity")),
          decode<std::uint64_t>(input.at("press_sequence"))};
}

template <> SequencePublicationAuthority decode<SequencePublicationAuthority>(const Json& input) {
  require(input.is_object() && input.size() == 3, "invalid SequencePublicationAuthority shape");
  return {decode<foundation::PatternId>(input.at("pattern_id")),
          decode<std::uint64_t>(input.at("generation")),
          decode<std::uint64_t>(input.at("frame"))};
}

template <> SequenceAdmissionFence decode<SequenceAdmissionFence>(const Json& input) {
  require(input.is_object() && input.size() == 12, "invalid SequenceAdmissionFence shape");
  return {decode<SequenceFenceKind>(input.at("kind")),
          decode<foundation::CommandId>(input.at("command_id")),
          decode<std::uint64_t>(input.at("transport_epoch")),
          decode<std::uint64_t>(input.at("effective_frame")),
          decode<std::uint64_t>(input.at("origin_frame")),
          decode<foundation::PatternId>(input.at("pattern_id")),
          decode<std::uint64_t>(input.at("publication_generation")),
          decode<std::uint16_t>(input.at("bpm")),
          decode<bool>(input.at("playing")),
          decode<std::optional<SequencePublicationAuthority>>(input.at("switch_authority")),
          decode<SequenceSwitchOutcome>(input.at("switch_outcome")),
          decode<std::optional<std::uint64_t>>(input.at("switch_applied_frame"))};
}

template <> SequenceAdmissionClosure decode<SequenceAdmissionClosure>(const Json& input) {
  require(input.is_object() && input.size() == 2, "invalid SequenceAdmissionClosure shape");
  return {decode<std::optional<std::uint64_t>>(input.at("last_retained_watermark")),
          decode<SequenceAdmissionCloseReason>(input.at("reason"))};
}

template <> SequenceOwnedPress decode<SequenceOwnedPress>(const Json& input) {
  require(input.is_object() && input.size() == 5, "invalid SequenceOwnedPress shape");
  return {decode<domain::PadSlotId>(input.at("slot")),
          decode<std::uint64_t>(input.at("press_sequence")),
          decode<std::uint64_t>(input.at("raw_attack_tick")),
          decode<std::uint32_t>(input.at("onset_tick")),
          decode<std::uint8_t>(input.at("velocity"))};
}

template <> SequenceAdmissionCheckpoint decode<SequenceAdmissionCheckpoint>(const Json& input) {
  require(input.is_object() && input.size() == 4, "invalid SequenceAdmissionCheckpoint shape");
  return {decode<foundation::PatternId>(input.at("pattern_id")),
          decode<std::uint64_t>(input.at("publication_generation")),
          decode<std::uint64_t>(input.at("last_runtime_frame")),
          decode<std::vector<SequenceOwnedPress>>(input.at("owned_presses"))};
}

template <> SequenceCandidateReceipt decode<SequenceCandidateReceipt>(const Json& input) {
  require(input.is_object() && input.size() == 2, "invalid SequenceCandidateReceipt shape");
  return {decode<std::uint64_t>(input.at("watermark")),
          decode<std::string>(input.at("payload_sha256"))};
}

template <> SequenceAdmissionTransfer decode<SequenceAdmissionTransfer>(const Json& input) {
  require(input.is_object() && input.size() == 11, "invalid SequenceAdmissionTransfer shape");
  return {decode<foundation::CommandId>(input.at("transfer_id")),
          decode<bool>(input.at("terminal")),
          decode<std::uint64_t>(input.at("first_watermark")),
          decode<std::uint64_t>(input.at("last_watermark")),
          decode<std::string>(input.at("candidates_sha256")),
          decode<std::vector<SequenceCandidateReceipt>>(input.at("candidate_receipts")),
          decode<foundation::PatternId>(input.at("pattern_id")),
          decode<std::uint64_t>(input.at("expected_revision")),
          decode<std::optional<std::uint64_t>>(input.at("journal_input_sequence")),
          decode<std::vector<domain::PatternEvent>>(input.at("recoverable_tail")),
          decode<SequenceAdmissionCheckpoint>(input.at("checkpoint"))};
}

template <> SequenceAdmissionTimingProfile decode<SequenceAdmissionTimingProfile>(const Json& input) {
  require(input.is_object() && input.size() == 10, "invalid SequenceAdmissionTimingProfile shape");
  return {decode<foundation::CommandId>(input.at("command_id")),
          decode<std::uint64_t>(input.at("first_watermark")),
          decode<foundation::PatternId>(input.at("pattern_id")),
          decode<std::uint64_t>(input.at("publication_generation")),
          decode<std::uint64_t>(input.at("expected_revision")),
          decode<std::uint64_t>(input.at("runtime_frame")),
          decode<std::uint64_t>(input.at("tick_numerator")),
          decode<std::uint16_t>(input.at("bpm")),
          decode<bool>(input.at("quantize_enabled")),
          decode<std::uint8_t>(input.at("swing_percent"))};
}

template <> SequenceAdmissionState decode<SequenceAdmissionState>(const Json& input) {
  require(input.is_object() && input.size() == 10, "invalid SequenceAdmissionState shape");
  return {decode<SequenceAdmissionPreparation>(input.at("preparation")),
          decode<std::vector<SequenceAdmissionCandidate>>(input.at("candidates")),
          decode<std::optional<SequenceAdmissionFence>>(input.at("admission_fence")),
          decode<std::optional<SequenceAdmissionFence>>(input.at("cutoff_fence")),
          decode<std::optional<SequenceAdmissionClosure>>(input.at("closure")),
          decode<std::vector<SequenceAdmissionTransfer>>(input.at("transfers")),
          decode<std::vector<SequencePublicationAuthority>>(input.at("applied_switches")),
          decode<std::uint64_t>(input.at("segment_generation")),
          decode<bool>(input.at("completed")),
          decode<std::vector<SequenceAdmissionTimingProfile>>(input.at("timing_profiles"))};
}
}  // namespace

Json encode(const domain::PadSlotId& value) {
  return {{"bank", value_json(value.bank)},
          {"pad", value_json(value.pad)}};
}

Json encode(const domain::PatternEvent& value) {
  return {{"slot", value_json(value.slot)},
          {"onset_tick", value_json(value.onset_tick)},
          {"duration_tick", value_json(value.duration_tick)},
          {"velocity", value_json(value.velocity)}};
}

Json encode(const SequenceAdmissionIdentity& value) {
  return {{"operation_id", value_json(value.operation_id)},
          {"runtime_generation", value_json(value.runtime_generation)},
          {"transport_epoch", value_json(value.transport_epoch)}};
}

Json encode(const SequenceAdmissionPreparation& value) {
  return {{"identity", value_json(value.identity)},
          {"project_id", value_json(value.project_id)},
          {"pattern_id", value_json(value.pattern_id)},
          {"publication_generation", value_json(value.publication_generation)},
          {"first_watermark", value_json(value.first_watermark)},
          {"candidate_limit", value_json(value.candidate_limit)},
          {"candidate_byte_limit", value_json(value.candidate_byte_limit)},
          {"fence_timeout_ms", value_json(value.fence_timeout_ms)},
          {"quantize_enabled", value.quantize_enabled},
          {"swing_percent", value.swing_percent}};
}

Json encode(const SequenceAdmissionCandidate& value) {
  return {{"watermark", value_json(value.watermark)},
          {"runtime_frame", value_json(value.runtime_frame)},
          {"slot", value_json(value.slot)},
          {"kind", value_json(value.kind)},
          {"velocity", value_json(value.velocity)},
          {"press_sequence", value_json(value.press_sequence)}};
}

Json encode(const SequencePublicationAuthority& value) {
  return {{"pattern_id", value_json(value.pattern_id)},
          {"generation", value_json(value.generation)},
          {"frame", value_json(value.frame)}};
}

Json encode(const SequenceAdmissionFence& value) {
  return {{"kind", value_json(value.kind)},
          {"command_id", value_json(value.command_id)},
          {"transport_epoch", value_json(value.transport_epoch)},
          {"effective_frame", value_json(value.effective_frame)},
          {"origin_frame", value_json(value.origin_frame)},
          {"pattern_id", value_json(value.pattern_id)},
          {"publication_generation", value_json(value.publication_generation)},
          {"bpm", value_json(value.bpm)},
          {"playing", value_json(value.playing)},
          {"switch_authority", value_json(value.switch_authority)},
          {"switch_outcome", value_json(value.switch_outcome)},
          {"switch_applied_frame", value_json(value.switch_applied_frame)}};
}

Json encode(const SequenceAdmissionClosure& value) {
  return {{"last_retained_watermark", value_json(value.last_retained_watermark)},
          {"reason", value_json(value.reason)}};
}

Json encode(const SequenceOwnedPress& value) {
  return {{"slot", value_json(value.slot)},
          {"press_sequence", value_json(value.press_sequence)},
          {"raw_attack_tick", value_json(value.raw_attack_tick)},
          {"onset_tick", value_json(value.onset_tick)},
          {"velocity", value_json(value.velocity)}};
}

Json encode(const SequenceAdmissionCheckpoint& value) {
  return {{"pattern_id", value_json(value.pattern_id)},
          {"publication_generation", value_json(value.publication_generation)},
          {"last_runtime_frame", value_json(value.last_runtime_frame)},
          {"owned_presses", value_json(value.owned_presses)}};
}

Json encode(const SequenceCandidateReceipt& value) {
  return {{"watermark", value_json(value.watermark)},
          {"payload_sha256", value_json(value.payload_sha256)}};
}

Json encode(const SequenceAdmissionTransfer& value) {
  return {{"transfer_id", value_json(value.transfer_id)},
          {"terminal", value_json(value.terminal)},
          {"first_watermark", value_json(value.first_watermark)},
          {"last_watermark", value_json(value.last_watermark)},
          {"candidates_sha256", value_json(value.candidates_sha256)},
          {"candidate_receipts", value_json(value.candidate_receipts)},
          {"pattern_id", value_json(value.pattern_id)},
          {"expected_revision", value_json(value.expected_revision)},
          {"journal_input_sequence", value_json(value.journal_input_sequence)},
          {"recoverable_tail", value_json(value.recoverable_tail)},
          {"checkpoint", value_json(value.checkpoint)}};
}

Json encode(const SequenceAdmissionTimingProfile& value) {
  return {{"command_id", value.command_id.value()},
          {"first_watermark", value.first_watermark},
          {"pattern_id", value.pattern_id.value()},
          {"publication_generation", value.publication_generation},
          {"expected_revision", value.expected_revision},
          {"runtime_frame", value.runtime_frame},
          {"tick_numerator", value.tick_numerator},
          {"bpm", value.bpm},
          {"quantize_enabled", value.quantize_enabled},
          {"swing_percent", value.swing_percent}};
}

Json encode(const SequenceAdmissionState& value) {
  return {{"preparation", value_json(value.preparation)},
          {"candidates", value_json(value.candidates)},
          {"admission_fence", value_json(value.admission_fence)},
          {"cutoff_fence", value_json(value.cutoff_fence)},
          {"closure", value_json(value.closure)},
          {"transfers", value_json(value.transfers)},
          {"applied_switches", value_json(value.applied_switches)},
          {"segment_generation", value_json(value.segment_generation)},
          {"completed", value_json(value.completed)},
          {"timing_profiles", value_json(value.timing_profiles)}};
}


namespace {
std::string digest(const Json& value) {
  const auto bytes = foundation::canonical_json(value);
  return picosha2::hash256_hex_string(bytes);
}
bool hash_valid(const std::string& hash) {
  return hash.size() == 64 && std::ranges::all_of(hash, [](char c) {
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
  });
}
template <typename T> void uuid(const T& id) {
  require(domain::is_valid_uuid(id.value()), "invalid admission UUID");
}
void identity_valid(const SequenceAdmissionIdentity& identity) {
  uuid(identity.operation_id);
  require(identity.runtime_generation && identity.transport_epoch,
          "admission generation and epoch must be nonzero");
}
void preparation_valid(const SequenceAdmissionPreparation& p) {
  identity_valid(p.identity);
  uuid(p.project_id);
  uuid(p.pattern_id);
  require(p.publication_generation && p.candidate_limit &&
              p.candidate_limit <= kSequenceAdmissionMaxCandidates &&
              p.candidate_byte_limit &&
              p.candidate_byte_limit <= kSequenceAdmissionCandidateBytes &&
              p.fence_timeout_ms &&
              p.fence_timeout_ms <= kSequenceAdmissionFenceTimeoutMs &&
              p.swing_percent >= domain::kSwingPercentMin &&
              p.swing_percent <= domain::kSwingPercentMax,
          "admission preparation limits are invalid");
}
void candidate_valid(const SequenceAdmissionCandidate& c) {
  require(domain::is_valid_slot(c.slot), "invalid admission slot");
  require((c.kind == SequenceCandidateKind::press && c.velocity >= 1 &&
           c.velocity <= 127) ||
              (c.kind == SequenceCandidateKind::release && c.velocity == 0),
          "invalid admission candidate kind or velocity");
}
void fence_valid(const SequenceAdmissionFence& f,
                 const SequenceAdmissionPreparation& p) {
  uuid(f.command_id);
  uuid(f.pattern_id);
  require(f.publication_generation && f.origin_frame <= f.effective_frame &&
              f.bpm >= 40 && f.bpm <= 240, "invalid admission fence metadata");
  require((f.kind == SequenceFenceKind::admission &&
           f.transport_epoch == p.identity.transport_epoch &&
           f.pattern_id == p.pattern_id &&
           f.publication_generation == p.publication_generation) ||
              (f.kind == SequenceFenceKind::cutoff &&
               f.transport_epoch > p.identity.transport_epoch),
          "invalid admission fence authority");
  if (f.switch_outcome == SequenceSwitchOutcome::none) {
    require(!f.switch_authority && !f.switch_applied_frame,
            "unexpected switch evidence");
  } else {
    require(f.switch_authority.has_value(), "missing switch authority");
    uuid(f.switch_authority->pattern_id);
    require(f.switch_authority->generation != 0, "invalid switch generation");
    if (f.switch_outcome == SequenceSwitchOutcome::applied_before_cutoff) {
      require(f.switch_applied_frame &&
                  *f.switch_applied_frame < f.effective_frame &&
                  f.pattern_id == f.switch_authority->pattern_id &&
                  f.publication_generation == f.switch_authority->generation,
              "invalid applied switch evidence");
    } else {
      require(f.switch_outcome == SequenceSwitchOutcome::canceled_at_cutoff &&
                  !f.switch_applied_frame, "invalid canceled switch evidence");
    }
  }
}
void fences_valid(const SequenceAdmissionState& s) {
  if (s.admission_fence) {
    require(s.admission_fence->kind == SequenceFenceKind::admission,
            "incorrect admission slot");
    fence_valid(*s.admission_fence, s.preparation);
  }
  if (s.cutoff_fence) {
    require(s.cutoff_fence->kind == SequenceFenceKind::cutoff,
            "incorrect cutoff slot");
    fence_valid(*s.cutoff_fence, s.preparation);
  }
  if (s.admission_fence && s.cutoff_fence) {
    require(s.cutoff_fence->effective_frame >= s.admission_fence->effective_frame &&
                s.cutoff_fence->command_id != s.admission_fence->command_id,
            "fence ordering or command collision");
  }
}
std::optional<std::uint64_t> last_watermark(const SequenceAdmissionState& s) {
  if (!s.candidates.empty()) return s.candidates.back().watermark;
  for (auto it = s.transfers.rbegin(); it != s.transfers.rend(); ++it) {
    if (!it->terminal) return it->last_watermark;
  }
  return std::nullopt;
}
void closure_valid(const SequenceAdmissionClosure& c, const SequenceAdmissionState& s) {
  require(static_cast<unsigned>(c.reason) <=
              static_cast<unsigned>(SequenceAdmissionCloseReason::owner_lost) &&
              c.last_retained_watermark == last_watermark(s),
          "invalid admission closure watermark or reason");
}
std::size_t candidate_bytes(const SequenceAdmissionState& s) {
  std::size_t size = 0;
  for (const auto& c : s.candidates) size += foundation::canonical_json(encode(c)).size();
  return size;
}
void checkpoint_valid(const SequenceAdmissionCheckpoint& checkpoint,
                      const foundation::PatternId& pattern, std::uint32_t length) {
  uuid(checkpoint.pattern_id);
  require(checkpoint.pattern_id == pattern && checkpoint.publication_generation &&
              checkpoint.owned_presses.size() <= 64,
          "invalid admission checkpoint Pattern or size");
  std::array<bool, 64> slots{};
  for (const auto& press : checkpoint.owned_presses) {
    require(domain::is_valid_slot(press.slot) && press.velocity >= 1 &&
                press.velocity <= 127 && press.onset_tick < length,
            "invalid owned press");
    auto& occupied = slots[press.slot.bank * 16U + press.slot.pad];
    require(!occupied, "duplicate owned slot");
    occupied = true;
  }
}
void tail_valid(const SequenceAdmissionTransfer& t, std::uint32_t length) {
  uuid(t.transfer_id);
  uuid(t.pattern_id);
  require(domain::merge_pattern_events({}, t.recoverable_tail) == t.recoverable_tail,
          "admission tail is not canonical");
  for (const auto& e : t.recoverable_tail) {
    require(domain::is_valid_slot(e.slot) && e.velocity >= 1 && e.velocity <= 127 &&
                e.onset_tick < length && e.duration_tick >= 1 &&
                e.duration_tick <= length - e.onset_tick,
            "invalid admission tail event");
  }
  checkpoint_valid(t.checkpoint, t.pattern_id, length);
}
bool terminal_retained(const SequenceAdmissionState& s) {
  return !s.transfers.empty() && s.transfers.back().terminal;
}
std::optional<SequencePublicationAuthority> cutoff_switch(const SequenceAdmissionState& s) {
  if (!s.cutoff_fence ||
      s.cutoff_fence->switch_outcome != SequenceSwitchOutcome::applied_before_cutoff) return {};
  return SequencePublicationAuthority{s.cutoff_fence->switch_authority->pattern_id,
      s.cutoff_fence->switch_authority->generation, *s.cutoff_fence->switch_applied_frame};
}
SequencePublicationAuthority segment(const SequenceAdmissionState& s, std::uint64_t generation) {
  if (generation == s.preparation.publication_generation) {
    return {s.preparation.pattern_id, generation,
            s.admission_fence ? s.admission_fence->effective_frame : 0};
  }
  for (const auto& a : s.applied_switches) if (a.generation == generation) return a;
  const auto cutoff = cutoff_switch(s);
  require(cutoff && cutoff->generation == generation,
          "journal segment lacks applied authority");
  return *cutoff;
}
SequencePublicationAuthority segment(const SequenceAdmissionState& s) {
  return segment(s, s.segment_generation);
}
std::optional<SequencePublicationAuthority> pending_switch(const SequenceAdmissionState& s) {
  if (!s.applied_switches.empty() &&
      s.applied_switches.back().generation > s.segment_generation) return s.applied_switches.back();
  const auto cutoff = cutoff_switch(s);
  if (cutoff && cutoff->generation > s.segment_generation) return cutoff;
  return {};
}
void switches_valid(const SequenceAdmissionState& s) {
  auto previous = SequencePublicationAuthority{s.preparation.pattern_id,
      s.preparation.publication_generation, s.admission_fence ? s.admission_fence->effective_frame : 0};
  std::size_t pending = 0;
  for (const auto& a : s.applied_switches) {
    uuid(a.pattern_id);
    require(a.generation > previous.generation && a.frame >= previous.frame &&
                a.pattern_id != previous.pattern_id, "applied switch history regressed");
    if (a.generation > s.segment_generation) ++pending;
    previous = a;
  }
  require(pending <= 1, "multiple unreconciled applied switches");
  (void)segment(s); // Validates the persisted reconciled generation as well.
  if (!s.cutoff_fence) return;
  const auto& f = *s.cutoff_fence;
  const auto cutoff = cutoff_switch(s);
  for (const auto& a : s.applied_switches) {
    require(a.frame < f.effective_frame, "ordinary applied switch is at or after cutoff");
    if (f.switch_authority && a.generation == f.switch_authority->generation) {
      require(cutoff && a == *cutoff, "ordinary switch conflicts with cutoff decision");
    }
  }
  if (cutoff) {
    require(cutoff->generation >= previous.generation && cutoff->frame >= previous.frame,
            "cutoff applied authority regressed");
    if (cutoff->generation == previous.generation) {
      require(cutoff->pattern_id == previous.pattern_id &&
                  (s.applied_switches.empty() || *cutoff == previous),
              "cutoff applied authority collision");
    } else {
      require(pending == 0, "cutoff adds a second unreconciled switch");
    }
  } else {
    require(f.pattern_id == previous.pattern_id && f.publication_generation == previous.generation,
            "cutoff does not match last applied publication");
  }
}
void profiles_valid(const SequenceAdmissionState& s, std::uint64_t revision) {
  std::set<std::string> commands;
  const SequenceAdmissionTimingProfile* previous = nullptr;
  for (const auto& p : s.timing_profiles) {
    uuid(p.command_id);
    uuid(p.pattern_id);
    const auto authority = segment(s, p.publication_generation);
    require(s.admission_fence && commands.insert(p.command_id.value()).second &&
                authority.pattern_id == p.pattern_id &&
                p.publication_generation <= s.segment_generation &&
                p.first_watermark >= s.preparation.first_watermark &&
                p.expected_revision <= revision && p.runtime_frame >= authority.frame &&
                p.bpm >= 40 && p.bpm <= 240 &&
                p.swing_percent >= domain::kSwingPercentMin &&
                p.swing_percent <= domain::kSwingPercentMax,
            "invalid admission timing authority");
    if (previous) {
      require(p.first_watermark >= previous->first_watermark &&
                  p.publication_generation >= previous->publication_generation &&
                  p.expected_revision >= previous->expected_revision &&
                  p.runtime_frame >= previous->runtime_frame,
              "admission timing history regressed");
    }
    // Recheck the temporal boundary when opening a sealed snapshot too. Only
    // earlier input constrains this anchor; later transfers (and the terminal
    // cutoff, whose watermark is zero) must not invalidate historical settings.
    for (const auto& candidate : s.candidates) {
      if (candidate.watermark < p.first_watermark) {
        require(candidate.runtime_frame <= p.runtime_frame,
                "admission timing profile predates earlier candidate");
      }
    }
    for (const auto& transfer : s.transfers) {
      if (!transfer.terminal && transfer.last_watermark < p.first_watermark) {
        require(transfer.checkpoint.last_runtime_frame <= p.runtime_frame,
                "admission timing profile predates earlier transfer");
      }
    }
    previous = &p;
  }
}
SequenceAdmissionCheckpoint checkpoint(
    const SequenceAdmissionState& s, const foundation::PatternId& current_pattern) {
  const auto current = segment(s);
  require(current.pattern_id == current_pattern, "checkpoint segment Pattern mismatch");
  if (!s.transfers.empty() &&
      s.transfers.back().checkpoint.publication_generation == current.generation) {
    return s.transfers.back().checkpoint;
  }
  return {current_pattern, current.generation, current.frame, {}};
}
void record_bound(const Json& record) {
  const auto kind = record.at("kind").get<std::string>();
  const auto limit = kind == "admission-transfer" ? kSequenceAdmissionTransferBytes
                                                  : kSequenceAdmissionControlBytes;
  constexpr std::size_t envelope_bytes = 91; // checksum envelope and newline
  require(foundation::canonical_json(record).size() <= limit - envelope_bytes,
          "admission record exceeds reserved bytes");
  const auto& data = record.at("data");
  if (kind == "admission-transfer") {
    require(data.at("candidate_receipts").is_array() &&
                data.at("candidate_receipts").size() <= kSequenceAdmissionMaxCandidates &&
                data.at("checkpoint").at("owned_presses").is_array() &&
                data.at("checkpoint").at("owned_presses").size() <= 64,
            "admission transfer array exceeds bounds");
  }
}
}  // namespace

bool blocks_flush(const ActiveSequenceJournal& journal) {
  if (!journal.admission || journal.admission->completed) return false;
  const auto& s = *journal.admission;
  if (!s.admission_fence) return true;
  if (s.candidates.empty()) return false;
  // A durable ordinary or S<F applied boundary permits source finalization
  // while target-side candidates remain. No current-status clock is consulted.
  const auto boundary = pending_switch(s);
  return !(boundary &&
           std::ranges::all_of(s.candidates, [&](const auto& c) {
             return c.runtime_frame >= boundary->frame;
           }));
}
bool blocks_switch(const ActiveSequenceJournal& journal,
                   const foundation::PatternId& target) {
  if (!journal.admission || journal.admission->completed) return false;
  const auto boundary = pending_switch(*journal.admission);
  return blocks_flush(journal) || !journal.pending_events.empty() ||
         !journal.admission->admission_fence || !boundary || boundary->pattern_id != target;
}
void reconcile_switch(ActiveSequenceJournal& journal) {
  if (!journal.admission || journal.admission->completed) return;
  const auto boundary = pending_switch(*journal.admission);
  require(boundary.has_value(), "switch lacks durable applied authority");
  journal.admission->segment_generation = boundary->generation;
}

void preflight(std::string_view bytes) {
  // This SAX pass builds no arrays. Each bounded subtree has a token-byte
  // budget; the exact canonical byte budget is checked again before decoding.
  // Historical transfers are bounded individually, not as an entire session.
  class Bounds final : public nlohmann::json_sax<Json> {
   public:
    std::string payload_kind;
    std::set<std::string> payload_keys;
    struct Frame {
      bool array;
      std::string name;
      std::string key;
      std::size_t count{};
      std::size_t maximum{std::numeric_limits<std::size_t>::max()};
      std::size_t start{};
      std::size_t budget{std::numeric_limits<std::size_t>::max()};
    };
    bool null() override { return scalar(4); }
    bool boolean(bool value) override { return scalar(value ? 4 : 5); }
    bool number_integer(number_integer_t n) override { return scalar(std::to_string(n).size()); }
    bool number_unsigned(number_unsigned_t n) override { return scalar(std::to_string(n).size()); }
    bool number_float(number_float_t, const string_t& raw) override { return scalar(raw.size()); }
    bool string(string_t& value) override {
      if (frames.size() == 2 && frames.back().name == "payload" &&
          frames.back().key == "kind") payload_kind = value;
      return scalar(value.size() + 2);
    }
    bool binary(binary_t&) override { return false; }
    bool key(string_t& value) override {
      if (frames.empty()) return false;
      if (frames.size() == 1 && value != "checksum" && value != "payload") return false;
      if (frames.size() == 2 && frames.back().name == "payload") {
        if (!payload_keys.insert(value).second) return false;
      }
      frames.back().key = value;
      return charge(value.size() + 3);
    }
    bool start_object(std::size_t) override { return start(false); }
    bool end_object() override { return end(); }
    bool start_array(std::size_t) override { return start(true); }
    bool end_array() override { return end(); }
    bool parse_error(std::size_t, const std::string&,
                     const nlohmann::detail::exception&) override { return false; }
   private:
    std::vector<Frame> frames;
    std::size_t total{};
    bool charge(std::size_t bytes_count) {
      if (bytes_count > std::numeric_limits<std::size_t>::max() - total) return false;
      total += bytes_count;
      for (const auto& f : frames) if (total - f.start > f.budget) return false;
      return true;
    }
    bool item() {
      if (frames.empty() || !frames.back().array) return true;
      auto& f = frames.back();
      return ++f.count <= f.maximum;
    }
    bool scalar(std::size_t n) { return item() && charge(n); }
    bool start(bool array) {
      if (frames.size() >= static_cast<std::size_t>(foundation::kMaximumJsonContainerDepth) || !item()) return false;
      const auto name = frames.empty() ? std::string{} :
          (frames.back().array ? frames.back().name : frames.back().key);
      Frame frame{array, name, {}};
      frame.start = total;
      // Unknown fields inherit a finite budget too. Only actual session/history
      // containers are exempt; spelling an arbitrary array "transfers" is not
      // enough to obtain an unbounded allocation.
      frame.budget = kSequenceAdmissionControlBytes;
      if (frames.empty() || (frames.size() == 1 && name == "payload") ||
          (frames.size() == 2 && name == "journal") ||
          (frames.size() == 3 && frames.back().name == "journal" && name == "admission") ||
          (array && frames.size() == 4 && frames.back().name == "admission" &&
           (name == "transfers" || name == "applied_switches" || name == "timing_profiles")) ||
          (array && frames.size() == 3 && frames.back().name == "journal" &&
           (name == "flushes" || name == "pending_events" || name == "rebases")) ||
          (array && name == "events" &&
           ((frames.size() == 2 && frames.back().name == "payload") ||
            frames.back().name == "flushes")) ||
          (array && name == "recovery_events" && frames.back().name == "flushes") ||
          (!array && name == "flushes" && frames.back().array)) {
        frame.budget = std::numeric_limits<std::size_t>::max();
      }
      if (array && (frames.empty() || name == "payload" || name == "journal" ||
                    name == "admission" || name == "checksum")) return false;
      if (name == "data" || (name == "transfers" && !array)) frame.budget = kSequenceAdmissionTransferBytes;
      if (name == "recoverable_tail" && array) frame.budget = kSequenceAdmissionTransferBytes;
      if (name == "candidates" || name == "candidate_receipts") {
        frame.budget = kSequenceAdmissionCandidateBytes;
        if (array) frame.maximum = kSequenceAdmissionMaxCandidates;
      }
      if (name == "owned_presses" && array) frame.maximum = 64;
      if (name == "preparation" || name == "admission_fence" ||
          name == "cutoff_fence" || name == "closure") frame.budget = kSequenceAdmissionControlBytes;
      frames.push_back(std::move(frame));
      return charge(1);
    }
    bool end() {
      if (frames.empty() || !charge(1)) return false;
      frames.pop_back();
      return true;
    }
  } bounds;
  require(Json::sax_parse(bytes, &bounds), "admission JSON exceeds bounds or is malformed");
  // The streaming pass discovers kind without relying on member ordering. This
  // whole-envelope check still runs BEFORE the caller constructs a JSON DOM,
  // so even fields recognized in another grammar cannot evade record limits.
  if (bounds.payload_kind.starts_with("admission-")) {
    const auto limit = bounds.payload_kind == "admission-transfer"
        ? kSequenceAdmissionTransferBytes : kSequenceAdmissionControlBytes;
    require(bytes.size() <= limit && bounds.payload_keys ==
                std::set<std::string>{"data", "identity", "kind", "session_id"},
            "admission envelope exceeds bounds or has unknown fields");
  } else if (bounds.payload_keys.contains("journal")) {
    require(bounds.payload_keys == std::set<std::string>{"contract", "journal", "reason"},
            "recovery envelope has unknown fields");
  }
}

bool apply(ActiveSequenceJournal& journal, const Json& record,
           std::size_t* replay_candidate_bytes) {
  record_bound(record);
  require(record.is_object() && record.size() == 4, "invalid admission record shape");
  const auto session = decode<foundation::SequenceSessionId>(record.at("session_id"));
  uuid(session);
  require(session == journal.session_id, "admission session mismatch");
  const auto identity = decode<SequenceAdmissionIdentity>(record.at("identity"));
  identity_valid(identity);
  const auto kind = record.at("kind").get<std::string>();
  const auto& data = record.at("data");
  if (kind == "admission-prepare") {
    const auto p = decode<SequenceAdmissionPreparation>(data);
    preparation_valid(p);
    require(identity == p.identity, "preparation identity mismatch");
    if (journal.admission) {
      require(journal.admission->preparation == p, "conflicting admission preparation");
      return false;
    }
    require(journal.state == SequenceSessionState::active && p.pattern_id == journal.pattern_id,
            "preparation does not match active Pattern");
    journal.admission = SequenceAdmissionState{p, {}, {}, {}, {}, {}, {}, p.publication_generation, false};
    return true;
  }
  require(journal.admission.has_value(), "admission is not prepared");
  auto& s = *journal.admission;
  require(s.preparation.identity == identity, "admission generation or operation mismatch");
  if (kind == "admission-profile") {
    const auto p = decode<SequenceAdmissionTimingProfile>(data);
    for (const auto& existing : s.timing_profiles) {
      if (existing.command_id == p.command_id) {
        require(existing == p, "immutable timing profile collision");
        return false;
      }
    }
    const auto previous = last_watermark(s);
    require(!s.completed && !s.closure && !terminal_retained(s) &&
                s.admission_fence && !pending_switch(s) &&
                (journal.state == SequenceSessionState::active ||
                 journal.state == SequenceSessionState::switching) &&
                p.pattern_id == journal.pattern_id &&
                p.publication_generation == s.segment_generation &&
                p.expected_revision == journal.expected_revision &&
                p.runtime_frame >= checkpoint(s, journal.pattern_id).last_runtime_frame &&
                (!previous || p.first_watermark > *previous),
            "timing profile lacks current authority or rewrites retained input");
    s.timing_profiles.push_back(p);
    profiles_valid(s, journal.expected_revision);
    return true;
  }
  if (kind == "admission-candidate") {
    const auto c = decode<SequenceAdmissionCandidate>(data);
    candidate_valid(c);
    const auto existing = std::ranges::lower_bound(
        s.candidates, c.watermark, {}, &SequenceAdmissionCandidate::watermark);
    if (existing != s.candidates.end() && existing->watermark == c.watermark) {
      require(*existing == c, "candidate watermark payload collision");
      return false;
    }
    for (const auto& transfer : s.transfers) {
      for (const auto& receipt : transfer.candidate_receipts) {
        if (receipt.watermark == c.watermark) {
          require(receipt.payload_sha256 == digest(encode(c)), "consumed candidate collision");
          return false;
        }
      }
    }
    require(!s.completed && !s.closure && !terminal_retained(s) &&
                (journal.state == SequenceSessionState::active ||
                 journal.state == SequenceSessionState::switching), "admission is closed");
    const auto previous = last_watermark(s);
    require(c.watermark >= s.preparation.first_watermark &&
                (!previous || c.watermark > *previous), "candidate watermark is not increasing");
    const auto size = (replay_candidate_bytes ? *replay_candidate_bytes : candidate_bytes(s)) +
        foundation::canonical_json(encode(c)).size();
    require(s.candidates.size() < s.preparation.candidate_limit &&
                size <= s.preparation.candidate_byte_limit, "admission capacity exhausted");
    s.candidates.push_back(c);
    if (replay_candidate_bytes) *replay_candidate_bytes = size;
    // Capacity closure is part of this candidate's durable transition: there is
    // no second append or crash window between occupying the final slot and B.
    if (s.candidates.size() == s.preparation.candidate_limit ||
        size == s.preparation.candidate_byte_limit) {
      s.closure = SequenceAdmissionClosure{c.watermark, SequenceAdmissionCloseReason::capacity};
    }
    return true;
  }
  if (kind == "admission-switch") {
    const auto authority = decode<SequencePublicationAuthority>(data);
    uuid(authority.pattern_id);
    for (const auto& previous : s.applied_switches) {
      if (previous.generation == authority.generation) {
        require(previous == authority, "immutable applied switch collision");
        return false;
      }
    }
    require(!s.completed && !terminal_retained(s) && s.admission_fence &&
                (journal.state == SequenceSessionState::active ||
                 journal.state == SequenceSessionState::switching),
            "applied switch lacks active admission");
    const auto pending = pending_switch(s);
    // A matching S<F receipt may already supply this same boundary; it is not
    // a second switch. Any other unresolved boundary must reconcile first.
    require(!pending || ((s.applied_switches.empty() ||
                s.applied_switches.back().generation <= s.segment_generation) &&
                *pending == authority), "another applied switch is unresolved");
    const auto current = segment(s);
    require(authority.generation > current.generation &&
                authority.frame >= checkpoint(s, journal.pattern_id).last_runtime_frame,
            "applied switch generation or frame regressed");
    if (s.cutoff_fence) {
      const auto cutoff = cutoff_switch(s);
      require(cutoff && *cutoff == authority, "applied switch conflicts with retained cutoff");
    }
    s.applied_switches.push_back(authority);
    switches_valid(s);
    return true;
  }
  if (kind == "admission-fence") {
    const auto f = decode<SequenceAdmissionFence>(data);
    fence_valid(f, s.preparation);
    auto& slot = f.kind == SequenceFenceKind::admission ? s.admission_fence : s.cutoff_fence;
    if (slot) {
      require(*slot == f, "immutable fence collision");
      return false;
    }
    require(!s.completed, "admission is complete");
    slot = f;
    fences_valid(s);
    switches_valid(s);
    return true;
  }
  if (kind == "admission-close") {
    const auto closure = decode<SequenceAdmissionClosure>(data);
    if (s.closure) {
      require(*s.closure == closure, "immutable admission closure collision");
      return false;
    }
    require(!s.completed, "admission is complete");
    closure_valid(closure, s);
    s.closure = closure;
    return true;
  }
  if (kind == "admission-transfer") {
    const auto t = decode<SequenceAdmissionTransfer>(data);
    for (const auto& existing : s.transfers) {
      if (existing.transfer_id == t.transfer_id) {
        require(existing == t, "immutable transfer collision");
        return false;
      }
    }
    require(!s.completed && !terminal_retained(s) && s.admission_fence &&
                (journal.state == SequenceSessionState::active ||
                 journal.state == SequenceSessionState::switching),
            "transfer lacks active admission authority");
    require(t.pattern_id == journal.pattern_id && t.expected_revision == journal.expected_revision,
            "transfer Pattern or revision mismatch");
    tail_valid(t, domain::pattern_length_ticks(journal.bars));
    const auto previous_checkpoint = checkpoint(s, journal.pattern_id);
    require(t.checkpoint.publication_generation == previous_checkpoint.publication_generation &&
                t.checkpoint.last_runtime_frame >= previous_checkpoint.last_runtime_frame,
            "checkpoint frame regressed");
    std::size_t consumed = 0;
    if (t.terminal) {
      require(s.cutoff_fence && s.closure && s.candidates.empty() && !pending_switch(s) &&
                  t.first_watermark == 0 && t.last_watermark == 0 &&
                  t.candidate_receipts.empty() && t.candidates_sha256 == digest(Json::array()) &&
                  t.checkpoint.owned_presses.empty() && !t.journal_input_sequence &&
                  t.pattern_id == s.cutoff_fence->pattern_id,
              "invalid terminal transfer");
    } else {
      consumed = t.candidate_receipts.size();
      require(consumed && consumed <= s.candidates.size() &&
                  t.first_watermark == s.candidates.front().watermark &&
                  t.last_watermark == s.candidates[consumed - 1].watermark,
              "transfer is not an outstanding prefix");
      auto candidates = Json::array();
      for (std::size_t i = 0; i < consumed; ++i) {
        const auto encoded = encode(s.candidates[i]);
        require(t.candidate_receipts[i].watermark == s.candidates[i].watermark &&
                    t.candidate_receipts[i].payload_sha256 == digest(encoded),
                "candidate receipt mismatch");
        candidates.push_back(encoded);
      }
      require(t.candidates_sha256 == digest(candidates), "candidate prefix checksum mismatch");
      if (s.closure) require(s.cutoff_fence.has_value(), "terminal drain lacks cutoff authority");
      if (!t.journal_input_sequence) {
        require(t.recoverable_tail == journal.pending_events && t.checkpoint == previous_checkpoint,
                "excluded prefix changed tail or ownership");
      }
    }
    if (t.journal_input_sequence) {
      require(!journal.last_input_sequence || *t.journal_input_sequence > *journal.last_input_sequence,
              "journal input sequence did not advance");
      require(journal.next_tail_seq != std::numeric_limits<std::uint64_t>::max(),
              "journal tail sequence overflow");
      journal.last_input_sequence = t.journal_input_sequence;
      ++journal.next_tail_seq;
    }
    journal.pending_events = t.recoverable_tail;
    s.transfers.push_back(t);
    if (replay_candidate_bytes) {
      for (std::size_t i = 0; i < consumed; ++i) {
        *replay_candidate_bytes -= foundation::canonical_json(encode(s.candidates[i])).size();
      }
    }
    s.candidates.erase(s.candidates.begin(), s.candidates.begin() + static_cast<std::ptrdiff_t>(consumed));
    return true;
  }
  require(kind == "admission-complete" && data.is_null(), "unknown admission record");
  if (s.completed) return false;
  require(s.admission_fence && s.cutoff_fence && s.closure && s.candidates.empty() && !pending_switch(s) &&
              terminal_retained(s) && s.transfers.back().checkpoint.owned_presses.empty() &&
              journal.pending_events.empty() &&
              std::ranges::all_of(journal.flushes, [](const auto& f) { return f.completed; }),
          "admission still has unresolved work");
  s.completed = true;
  return true;
}

SequenceAdmissionState snapshot(const Json& input, const ActiveSequenceJournal& journal) {
  // Bound every outstanding collection and individual historical transfer before
  // constructing typed arrays. History itself follows the existing journal life.
  require(input.at("candidates").is_array() &&
              input.at("candidates").size() <= kSequenceAdmissionMaxCandidates,
          "snapshot candidate count exceeds bounds");
  require(input.at("transfers").is_array(), "invalid transfer history");
  for (const auto& t : input.at("transfers")) {
    record_bound({{"kind", "admission-transfer"}, {"data", t},
                  {"session_id", journal.session_id.value()},
                  {"identity", input.at("preparation").at("identity")}});
  }
  auto s = decode<SequenceAdmissionState>(input);
  preparation_valid(s.preparation);
  fences_valid(s);
  switches_valid(s);
  profiles_valid(s, journal.expected_revision);
  // Completed admission is historical evidence: later ordinary journal switches
  // do not rewrite its retained segment or immutable receipts.
  if (!s.completed) {
    require(segment(s).pattern_id == journal.pattern_id, "snapshot segment Pattern mismatch");
  }
  std::optional<std::uint64_t> previous;
  std::set<std::string> transfers;
  bool terminal = false;
  std::uint64_t previous_generation = s.preparation.publication_generation;
  for (const auto& t : s.transfers) {
    require(!terminal && transfers.insert(t.transfer_id.value()).second,
            "duplicate or post-terminal transfer history");
    tail_valid(t, domain::pattern_length_ticks(8));
    const auto authority = segment(s, t.checkpoint.publication_generation);
    require(t.checkpoint.publication_generation >= previous_generation &&
                t.checkpoint.publication_generation <= s.segment_generation &&
                authority.pattern_id == t.pattern_id &&
                t.checkpoint.last_runtime_frame >= authority.frame,
            "snapshot transfer segment is invalid");
    previous_generation = t.checkpoint.publication_generation;
    require(hash_valid(t.candidates_sha256), "invalid prefix digest");
    if (t.terminal) {
      require(t.first_watermark == 0 && t.last_watermark == 0 &&
                  t.candidate_receipts.empty() && t.candidates_sha256 == digest(Json::array()) &&
                  !t.journal_input_sequence && t.checkpoint.owned_presses.empty() &&
                  s.admission_fence && s.cutoff_fence && s.closure && s.candidates.empty() && !pending_switch(s) &&
                  t.pattern_id == s.cutoff_fence->pattern_id,
              "invalid terminal snapshot");
      terminal = true;
    } else {
      require(!t.candidate_receipts.empty() &&
                  t.first_watermark == t.candidate_receipts.front().watermark &&
                  t.last_watermark == t.candidate_receipts.back().watermark,
              "invalid snapshot prefix");
      for (const auto& receipt : t.candidate_receipts) {
        require(receipt.watermark >= s.preparation.first_watermark &&
                    (!previous || receipt.watermark > *previous) && hash_valid(receipt.payload_sha256),
                "invalid historical candidate receipt");
        previous = receipt.watermark;
      }
    }
  }
  for (const auto& c : s.candidates) {
    candidate_valid(c);
    require(c.watermark >= s.preparation.first_watermark &&
                (!previous || c.watermark > *previous), "invalid snapshot watermark");
    previous = c.watermark;
  }
  const auto size = candidate_bytes(s);
  require(s.candidates.size() <= s.preparation.candidate_limit &&
              size <= s.preparation.candidate_byte_limit, "snapshot candidate capacity exceeded");
  if (s.candidates.size() == s.preparation.candidate_limit || size == s.preparation.candidate_byte_limit) {
    require(s.closure.has_value(), "full snapshot lacks closure");
  }
  if (s.closure) closure_valid(*s.closure, s);
  if (!s.transfers.empty()) require(s.admission_fence.has_value(), "transfer history lacks authority");
  if (s.completed) {
    // Completion checked the ordinary journal at its own record boundary.
    // A sealed snapshot may also contain later ordinary tails or flushes;
    // those do not invalidate the retained terminal admission evidence.
    require(terminal, "completed snapshot lacks terminal evidence");
  }
  return s;
}
}  // namespace lmdj::project_io::admission_codec
