#include <lmdj/domain/project.hpp>

#include <algorithm>
#include <array>
#include <charconv>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>
#include <variant>

#include <lmdj/foundation/soundset_manifest.hpp>

namespace lmdj::domain {
namespace {

bool is_lower_hex(char value) noexcept {
  return (value >= '0' && value <= '9') ||
         (value >= 'a' && value <= 'f');
}

foundation::Result<PerformanceEvent> invalid_performance_event(
    std::string_view message) {
  return foundation::Result<PerformanceEvent>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

foundation::Result<void> invalid_performance(std::string_view message) {
  return foundation::Result<void>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

foundation::Result<void> invalid_asset_lineage(std::string_view message) {
  return foundation::Result<void>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

foundation::Result<AssetLineage> invalid_asset_lineage_value(
    std::string_view message) {
  return foundation::Result<AssetLineage>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

bool exact_object_keys(
    const nlohmann::json& input,
    std::initializer_list<std::string_view> keys) {
  if (!input.is_object() || input.size() != keys.size()) {
    return false;
  }
  return std::ranges::all_of(
      keys,
      [&input](std::string_view key) {
        return input.contains(key);
      });
}

std::optional<std::uint64_t> unsigned_value(
    const nlohmann::json& input) noexcept {
  try {
    if (input.is_number_unsigned()) {
      return input.get<std::uint64_t>();
    }
    if (input.is_number_integer()) {
      const auto value = input.get<std::int64_t>();
      if (value >= 0) {
        return static_cast<std::uint64_t>(value);
      }
    }
  } catch (const std::exception&) {
  }
  return std::nullopt;
}

std::optional<std::uint64_t> bounded_unsigned(
    const nlohmann::json& input,
    std::uint64_t maximum) noexcept {
  const auto value = unsigned_value(input);
  if (!value.has_value() || *value > maximum) {
    return std::nullopt;
  }
  return value;
}

bool valid_fx(PerformanceFx fx) noexcept {
  return static_cast<std::uint8_t>(fx) < kFxCount;
}

// A durable input sequence is the canonical decimal string of a uint64 from
// 1: no sign, no leading zero, no fraction, nothing after the last digit.
std::optional<std::uint64_t> parse_input_sequence(
    const nlohmann::json& input) noexcept {
  if (!input.is_string()) {
    return std::nullopt;
  }
  const auto& text = input.get_ref<const std::string&>();
  if (text.empty() || text.size() > 20 || text.front() == '0' ||
      !std::ranges::all_of(text, [](char c) {
        return c >= '0' && c <= '9';
      })) {
    return std::nullopt;
  }
  if (text.size() == 20 && text > "18446744073709551615") {
    return std::nullopt;
  }
  std::uint64_t value = 0;
  const auto* last = text.data() + text.size();
  const auto parsed =
      std::from_chars(text.data(), last, value);
  if (parsed.ec != std::errc{} || parsed.ptr != last) {
    return std::nullopt;
  }
  return value;
}

bool valid_filter_type(PerformanceFilterType type) noexcept {
  switch (type) {
    case PerformanceFilterType::lp:
    case PerformanceFilterType::hp:
    case PerformanceFilterType::bp:
      return true;
  }
  return false;
}

bool valid_filter_phase(PerformanceFilterPhase phase) noexcept {
  switch (phase) {
    case PerformanceFilterPhase::engage:
    case PerformanceFilterPhase::move:
    case PerformanceFilterPhase::release:
      return true;
  }
  return false;
}

std::optional<PerformanceFilterType> filter_type_from_string(
    std::string_view value) noexcept {
  if (value == "lp") {
    return PerformanceFilterType::lp;
  }
  if (value == "hp") {
    return PerformanceFilterType::hp;
  }
  if (value == "bp") {
    return PerformanceFilterType::bp;
  }
  return std::nullopt;
}

std::string_view filter_type_string(PerformanceFilterType type) noexcept {
  switch (type) {
    case PerformanceFilterType::lp:
      return "lp";
    case PerformanceFilterType::hp:
      return "hp";
    case PerformanceFilterType::bp:
      return "bp";
  }
  return "lp";
}

std::optional<PerformanceFilterPhase> filter_phase_from_string(
    std::string_view value) noexcept {
  if (value == "engage") {
    return PerformanceFilterPhase::engage;
  }
  if (value == "move") {
    return PerformanceFilterPhase::move;
  }
  if (value == "release") {
    return PerformanceFilterPhase::release;
  }
  return std::nullopt;
}

std::string_view filter_phase_string(PerformanceFilterPhase phase) noexcept {
  switch (phase) {
    case PerformanceFilterPhase::engage:
      return "engage";
    case PerformanceFilterPhase::move:
      return "move";
    case PerformanceFilterPhase::release:
      return "release";
  }
  return "engage";
}

// Live slot masks are uint64 bit sets in the Domain; the wire carries
// ascending, duplicate-free integer arrays (slot 0 = A01, 63 = D16).
std::optional<std::uint64_t> slot_mask_from_json(
    const nlohmann::json& input) noexcept {
  if (!input.is_array()) {
    return std::nullopt;
  }
  std::uint64_t mask = 0;
  std::uint64_t previous = 0;
  bool first = true;
  for (const auto& encoded : input) {
    const auto slot = bounded_unsigned(encoded, kPerformancePadSlotMax);
    if (!slot.has_value() || (!first && *slot <= previous)) {
      return std::nullopt;
    }
    mask |= std::uint64_t{1} << *slot;
    previous = *slot;
    first = false;
  }
  return mask;
}

nlohmann::json slot_mask_json(std::uint64_t mask) {
  auto encoded = nlohmann::json::array();
  for (std::uint8_t slot = 0; slot < kPerformancePadSlotCount; ++slot) {
    if ((mask & (std::uint64_t{1} << slot)) != 0) {
      encoded.push_back(slot);
    }
  }
  return encoded;
}

bool valid_sha256(std::string_view value) noexcept {
  if (value.size() != 64) {
    return false;
  }
  return std::ranges::all_of(value, is_lower_hex);
}

// The Sound Set Contract pins `set_version` to the same three-part SemVer
// pattern the Project Schema uses, so a Lineage that survives the Schema also
// survives the domain and vice versa.
bool valid_soundset_semver(std::string_view value) noexcept {
  std::size_t index = 0;
  for (int part = 0; part < 3; ++part) {
    if (part > 0) {
      if (index >= value.size() || value[index] != '.') {
        return false;
      }
      ++index;
    }
    const std::size_t start = index;
    while (index < value.size() && value[index] >= '0' && value[index] <= '9') {
      ++index;
    }
    const std::size_t digits = index - start;
    if (digits == 0 || (digits > 1 && value[start] == '0')) {
      return false;
    }
  }
  return index == value.size();
}

std::optional<std::size_t> utf8_code_point_count(
    std::string_view value) noexcept {
  std::size_t count = 0;
  for (std::size_t index = 0; index < value.size();) {
    const auto first = static_cast<unsigned char>(value[index]);
    std::size_t length = 0;
    std::uint32_t code_point = 0;
    if (first <= 0x7fU) {
      length = 1;
      code_point = first;
    } else if ((first & 0xe0U) == 0xc0U) {
      length = 2;
      code_point = first & 0x1fU;
    } else if ((first & 0xf0U) == 0xe0U) {
      length = 3;
      code_point = first & 0x0fU;
    } else if ((first & 0xf8U) == 0xf0U) {
      length = 4;
      code_point = first & 0x07U;
    } else {
      return std::nullopt;
    }
    if (index + length > value.size()) {
      return std::nullopt;
    }
    for (std::size_t offset = 1; offset < length; ++offset) {
      const auto continuation =
          static_cast<unsigned char>(value[index + offset]);
      if ((continuation & 0xc0U) != 0x80U) {
        return std::nullopt;
      }
      code_point = (code_point << 6U) | (continuation & 0x3fU);
    }
    const bool overlong =
        (length == 2 && code_point < 0x80U) ||
        (length == 3 && code_point < 0x800U) ||
        (length == 4 && code_point < 0x10000U);
    if (overlong || code_point > 0x10ffffU ||
        (code_point >= 0xd800U && code_point <= 0xdfffU)) {
      return std::nullopt;
    }
    index += length;
    ++count;
  }
  return count;
}

}  // namespace

foundation::Result<ProjectState> create_project(
    foundation::ProjectId id,
    std::uint16_t bpm) {
  if (!is_valid_uuid(id.value())) {
    return foundation::Result<ProjectState>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "project id must be a lowercase UUID",
        });
  }
  if (bpm < 40 || bpm > 240) {
    return foundation::Result<ProjectState>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "project BPM must be between 40 and 240",
            {{"bpm", bpm}},
        });
  }

  // Built in the caller's return slot, so the new Project is never also a
  // local in this frame (#1771).
  auto created = foundation::Result<ProjectState>::emplace_success(
      ProjectContract::v5,
      std::move(id),
      std::uint64_t{0},
      bpm,
      true,
      std::uint8_t{50});
  auto& state = created.value();
  for (std::uint8_t bank = 0; bank < state.banks.size(); ++bank) {
    for (std::uint8_t pad = 0; pad < state.banks.at(bank).size(); ++pad) {
      state.banks.at(bank).at(pad) =
          PadSlot{PadSlotId{bank, pad}, std::nullopt, PadPlayback{}};
    }
  }
  return created;
}

bool is_valid_uuid(std::string_view value) noexcept {
  if (value.size() != 36 || value[8] != '-' || value[13] != '-' ||
      value[18] != '-' || value[23] != '-') {
    return false;
  }
  for (std::size_t index = 0; index < value.size(); ++index) {
    if (index == 8 || index == 13 || index == 18 || index == 23) {
      continue;
    }
    if (!is_lower_hex(value[index])) {
      return false;
    }
  }
  return value[14] >= '1' && value[14] <= '5' &&
         (value[19] == '8' || value[19] == '9' ||
          value[19] == 'a' || value[19] == 'b');
}

bool is_valid_slot(PadSlotId slot) noexcept {
  return slot.bank < 4 && slot.pad < 16;
}

namespace {

bool in_range(
    std::int32_t value, std::int32_t low, std::int32_t high) noexcept {
  return value >= low && value <= high;
}

bool is_valid_eq_kind(EqBandKind kind) noexcept {
  switch (kind) {
    case EqBandKind::shelf:
    case EqBandKind::cut:
      return true;
  }
  return false;
}

bool is_valid_eq_shelf(
    const std::optional<PadEqShelf>& band,
    std::int32_t freq_min,
    std::int32_t freq_max) noexcept {
  return !band.has_value() ||
         (is_valid_eq_kind(band->kind) &&
          in_range(band->freq_hz, freq_min, freq_max) &&
          in_range(
              band->gain_millidb, kPadEqGainMillidbMin, kPadEqGainMillidbMax));
}

bool is_valid_tone_playback(const PadPlayback& playback) noexcept {
  const auto& mid = playback.eq.mid;
  return in_range(playback.attack_ms, 0, kPadAttackMsMax) &&
         in_range(playback.release_ms, 0, kPadReleaseMsMax) &&
         in_range(playback.tone, kPadToneMin, kPadToneMax) &&
         is_valid_eq_shelf(
             playback.eq.low, kPadEqLowFreqHzMin, kPadEqLowFreqHzMax) &&
         is_valid_eq_shelf(
             playback.eq.high, kPadEqHighFreqHzMin, kPadEqHighFreqHzMax) &&
         (!mid.has_value() ||
          (in_range(mid->freq_hz, kPadEqMidFreqHzMin, kPadEqMidFreqHzMax) &&
           in_range(
               mid->gain_millidb, kPadEqGainMillidbMin, kPadEqGainMillidbMax) &&
           in_range(mid->q_milli, kPadEqMidQMilliMin, kPadEqMidQMilliMax)));
}

}  // namespace

bool is_valid_playback(const PadPlayback& playback) noexcept {
  if (!is_valid_tone_playback(playback)) {
    return false;
  }
  switch (playback.trigger_mode) {
    case TriggerMode::one_shot:
    case TriggerMode::gate:
    case TriggerMode::loop_gate:
    case TriggerMode::loop_toggle:
      break;
    default:
      return false;
  }
  switch (playback.loop_mode) {
    case LoopMode::forward:
    case LoopMode::ping_pong:
      break;
    default:
      return false;
  }
  if (playback.gain_millidb < -60000 || playback.gain_millidb > 6000 ||
      playback.pitch_cents < kPadPitchCentsMin ||
      playback.pitch_cents > kPadPitchCentsMax ||
      playback.pan < kPadPanMin || playback.pan > kPadPanMax) {
    return false;
  }
  if (playback.trim_end_frame.has_value() &&
      *playback.trim_end_frame <= playback.trim_start_frame) {
    return false;
  }
  const auto loop_start =
      playback.loop_start_frame.value_or(playback.trim_start_frame);
  if (loop_start < playback.trim_start_frame ||
      (playback.trim_end_frame.has_value() &&
       loop_start >= *playback.trim_end_frame)) {
    return false;
  }
  // A ping-pong loop has no seam to blend; a forward loop blends at most half
  // of itself, so a pass always keeps an unblended remainder.
  if (playback.loop_mode == LoopMode::ping_pong &&
      playback.loop_crossfade_frames != 0) {
    return false;
  }
  return !playback.trim_end_frame.has_value() ||
         playback.loop_crossfade_frames <=
             (*playback.trim_end_frame - loop_start) / 2;
}

bool is_valid_playback_for_source(
    const PadPlayback& playback,
    std::uint64_t source_frames) noexcept {
  if (!is_valid_playback(playback)) {
    return false;
  }
  const auto end = playback.trim_end_frame.value_or(source_frames);
  if (playback.trim_start_frame >= end || end > source_frames) {
    return false;
  }
  const auto loop_start =
      playback.loop_start_frame.value_or(playback.trim_start_frame);
  return loop_start < end &&
         playback.loop_crossfade_frames <= (end - loop_start) / 2;
}

std::optional<Asset> resolve_slot_asset(
    const ProjectState& state,
    PadSlotId slot) {
  if (!is_valid_slot(slot)) {
    return std::nullopt;
  }
  const auto& asset_id = state.banks.at(slot.bank).at(slot.pad).asset_id;
  if (!asset_id.has_value()) {
    return std::nullopt;
  }
  const auto asset = state.assets.find(*asset_id);
  if (asset == state.assets.end()) {
    return std::nullopt;
  }
  return asset->second;
}

std::uint8_t pad_colour_index(AssetCategory category) noexcept {
  return static_cast<std::uint8_t>(category);
}

std::optional<AssetCategory> soundset_role_category(
    std::string_view role) noexcept {
  if (role == "kick" || role == "snare" || role == "clap" ||
      role == "hat_closed" || role == "hat_open" || role == "perc" ||
      role == "cymbal") {
    return AssetCategory::drums;
  }
  if (role == "bass") {
    return AssetCategory::bass;
  }
  if (role == "melody" || role == "chord") {
    return AssetCategory::melodic;
  }
  if (role == "vocal") {
    return AssetCategory::vocal;
  }
  if (role == "fx") {
    return AssetCategory::texture;
  }
  return std::nullopt;
}

std::optional<AssetCategory> stem_label_category(
    std::string_view label) noexcept {
  if (label == "drums") {
    return AssetCategory::drums;
  }
  if (label == "bass") {
    return AssetCategory::bass;
  }
  if (label == "vocals") {
    return AssetCategory::vocal;
  }
  return std::nullopt;
}

std::optional<std::uint8_t> effective_pad_colour(
    const ProjectState& state,
    PadSlotId slot) {
  if (!is_valid_slot(slot)) {
    return std::nullopt;
  }
  const auto& pad = state.banks.at(slot.bank).at(slot.pad);
  if (pad.colour.has_value()) {
    return pad.colour;
  }
  if (!pad.asset_id.has_value()) {
    return std::nullopt;
  }
  const auto asset = state.assets.find(*pad.asset_id);
  if (asset == state.assets.end() || !asset->second.category.has_value()) {
    return std::nullopt;
  }
  return pad_colour_index(*asset->second.category);
}

std::uint32_t pattern_length_ticks(std::uint8_t bars) noexcept {
  return static_cast<std::uint32_t>(bars) * kBarTicks4x4;
}

std::uint32_t quantize_onset_tick(
    std::uint64_t raw_tick,
    std::uint32_t loop_length_ticks,
    bool quantize_enabled,
    std::uint8_t swing_percent) noexcept {
  if (loop_length_ticks == 0) {
    return 0;
  }
  const auto loop_tick = static_cast<std::uint32_t>(
      raw_tick % loop_length_ticks);
  if (!quantize_enabled) {
    return loop_tick;
  }

  const auto grid_index =
      (loop_tick + (kSixteenthTicks / 2U) - 1U) / kSixteenthTicks;
  auto quantized = (grid_index * kSixteenthTicks) % loop_length_ticks;
  if (quantized == 0 || (grid_index % 2U) == 0U) {
    return quantized;
  }

  const auto bounded_swing = std::clamp(
      swing_percent, kSwingPercentMin, kSwingPercentMax);
  const auto pair_start = (grid_index - 1U) * kSixteenthTicks;
  quantized = pair_start +
              ((2U * kSixteenthTicks * bounded_swing + 50U) / 100U);
  return quantized % loop_length_ticks;
}

std::uint32_t normalize_duration_tick(
    std::uint64_t raw_attack_tick,
    std::uint64_t raw_release_tick,
    std::uint32_t onset_tick,
    std::uint32_t loop_length_ticks) noexcept {
  if (loop_length_ticks == 0 || onset_tick >= loop_length_ticks) {
    return 0;
  }
  const auto remainder = loop_length_ticks - onset_tick;
  const auto raw_duration = raw_release_tick > raw_attack_tick
                                ? raw_release_tick - raw_attack_tick
                                : 1U;
  return static_cast<std::uint32_t>(
      std::clamp<std::uint64_t>(raw_duration, 1U, remainder));
}

std::vector<PatternEvent> merge_pattern_events(
    const std::vector<PatternEvent>& stored,
    const std::vector<PatternEvent>& incoming) {
  using EventKey = std::tuple<std::uint8_t, std::uint8_t, std::uint32_t>;
  std::map<EventKey, PatternEvent> by_key;
  const auto insert_or_replace = [&by_key](const PatternEvent& event) {
    by_key.insert_or_assign(
        EventKey{event.slot.bank, event.slot.pad, event.onset_tick}, event);
  };
  for (const auto& event : stored) {
    insert_or_replace(event);
  }
  for (const auto& event : incoming) {
    insert_or_replace(event);
  }

  std::vector<PatternEvent> merged;
  merged.reserve(by_key.size());
  for (const auto& [key, event] : by_key) {
    (void)key;
    merged.push_back(event);
  }
  std::ranges::sort(
      merged,
      {},
      [](const PatternEvent& event) {
        return std::tuple{
            event.onset_tick,
            event.slot.bank,
            event.slot.pad,
            event.duration_tick,
            event.velocity,
        };
      });
  return merged;
}

foundation::Result<void> validate_pattern_slots(
    const ProjectState& state) {
  std::set<foundation::PatternId> occupied;
  for (const auto& pattern_id : state.pattern_slots) {
    if (!pattern_id.has_value()) {
      continue;
    }
    if (!is_valid_uuid(pattern_id->value()) ||
        !state.patterns.contains(*pattern_id)) {
      return foundation::Result<void>::failure(
          foundation::Error{
              foundation::ErrorCode::invalid_argument,
              "Pattern slot references an invalid or missing Pattern",
          });
    }
    if (!occupied.insert(*pattern_id).second) {
      return foundation::Result<void>::failure(
          foundation::Error{
              foundation::ErrorCode::invalid_argument,
              "Pattern occupies more than one Pattern slot",
          });
    }
  }
  return foundation::Result<void>::success();
}

PerformanceEventKind performance_event_kind(
    const PerformanceEvent& event) noexcept {
  return static_cast<PerformanceEventKind>(event.payload.index());
}

std::uint64_t performance_event_tick(
    const PerformanceEvent& event) noexcept {
  return std::visit(
      [](const auto& payload) -> std::uint64_t {
        using Event = std::decay_t<decltype(payload)>;
        if constexpr (std::is_same_v<Event, PadHitPerformanceEvent>) {
          return payload.onset_tick;
        } else if constexpr (
            std::is_same_v<Event, PatternLaunchPerformanceEvent>) {
          return payload.effective_tick;
        } else {
          return payload.tick;
        }
      },
      event.payload);
}

std::uint8_t performance_event_fx_or_slot(
    const PerformanceEvent& event) noexcept {
  return std::visit(
      [](const auto& payload) -> std::uint8_t {
        using Event = std::decay_t<decltype(payload)>;
        if constexpr (std::is_same_v<Event, PadHitPerformanceEvent>) {
          return payload.slot;
        } else if constexpr (
            std::is_same_v<Event, PatternLaunchPerformanceEvent>) {
          return payload.pattern_slot;
        } else if constexpr (
            std::is_same_v<Event, FxEngagePerformanceEvent> ||
            std::is_same_v<Event, FxMovePerformanceEvent> ||
            std::is_same_v<Event, FxReleasePerformanceEvent>) {
          return static_cast<std::uint8_t>(payload.fx);
        } else {
          return 0;
        }
      },
      event.payload);
}

PerformanceEventProfile performance_event_profile(
    const Performance& performance) noexcept {
  return performance.initial_live_state.has_value()
             ? PerformanceEventProfile::header_input_sequence
             : PerformanceEventProfile::legacy;
}

std::vector<PerformanceEvent> canonical_performance_events(
    const std::vector<PerformanceEvent>& events) {
  auto ordered = events;
  std::ranges::stable_sort(
      ordered,
      {},
      [](const PerformanceEvent& event) {
        return std::tuple{
            performance_event_tick(event),
            static_cast<std::uint8_t>(performance_event_kind(event)),
            performance_event_fx_or_slot(event),
        };
      });
  return ordered;
}

std::vector<PerformanceEvent> canonical_performance_events(
    const std::vector<PerformanceEvent>& events,
    PerformanceEventProfile profile) {
  if (profile == PerformanceEventProfile::legacy) {
    return canonical_performance_events(events);
  }
  auto ordered = events;
  // The headered profile orders by musical time, then by Core reception
  // order within one tick; sequence uniqueness is validated separately.
  std::ranges::stable_sort(
      ordered,
      {},
      [](const PerformanceEvent& event) {
        return std::pair{
            performance_event_tick(event),
            event.input_sequence.value_or(0),
        };
      });
  return ordered;
}

namespace {

foundation::Result<void> validate_performance_events_with_seed(
    const std::vector<PerformanceEvent>& events,
    const PerformanceInitialLiveState* seed) {
  std::array<bool, kFxCount> engaged{};
  bool independent_filter_active = false;
  bool hold_enabled = false;
  if (seed != nullptr) {
    // The header seeds the state machine: an engaged or frozen control is
    // active at the fence, so a recorded move or release can pair with it
    // without an in-stream engage. HOLD seeds the hold state the same way.
    hold_enabled = seed->hold;
    for (std::size_t index = 0; index < seed->other_fx.size(); ++index) {
      const auto& gate = seed->other_fx.at(index);
      if (gate.engaged || gate.frozen) {
        engaged.at(index + 1) = true;
      }
    }
    if (const auto* legacy =
            std::get_if<LegacyFilterLiveState>(&seed->filter)) {
      engaged.at(0) = legacy->engaged || legacy->frozen;
    } else {
      const auto& independent = std::get<IndependentFilterLiveState>(
          seed->filter);
      independent_filter_active = independent.engaged || independent.frozen;
    }
  }
  for (const auto& event : events) {
    if ((seed != nullptr) != event.input_sequence.has_value()) {
      return invalid_performance(
          seed != nullptr
              ? "headered performance event is missing its input sequence"
              : "legacy performance event must not carry an input sequence");
    }
    const auto valid = std::visit(
        [&engaged, &hold_enabled, &independent_filter_active, seed](
            const auto& payload) -> foundation::Result<void> {
          using Event = std::decay_t<decltype(payload)>;
          if constexpr (std::is_same_v<Event, PadHitPerformanceEvent>) {
            if (payload.slot > kPerformancePadSlotMax ||
                payload.duration_tick == 0 || payload.velocity == 0 ||
                payload.velocity > 127) {
              return invalid_performance("pad_hit event is invalid");
            }
          } else if constexpr (
              std::is_same_v<Event, PatternLaunchPerformanceEvent>) {
            if (payload.pattern_slot < kPatternSlotMin ||
                payload.pattern_slot > kPatternSlotMax) {
              return invalid_performance(
                  "pattern_launch event is invalid");
            }
          } else if constexpr (
              std::is_same_v<Event, FxEngagePerformanceEvent>) {
            if (!valid_fx(payload.fx) || payload.value < kFxValueMin ||
                payload.value > kFxValueMax) {
              return invalid_performance("fx_engage event is invalid");
            }
            auto& active = engaged.at(static_cast<std::uint8_t>(payload.fx));
            if (active) {
              return invalid_performance(
                  "fx_engage requires a disengaged effect");
            }
            active = true;
            // The single Filter stage: a legacy Filter engage takes over
            // from an independent gesture, releasing that active state.
            if (payload.fx == PerformanceFx::filter) {
              independent_filter_active = false;
            }
          } else if constexpr (
              std::is_same_v<Event, FxMovePerformanceEvent>) {
            if (!valid_fx(payload.fx) || payload.value < kFxValueMin ||
                payload.value > kFxValueMax) {
              return invalid_performance("fx_move event is invalid");
            }
            if (!engaged.at(static_cast<std::uint8_t>(payload.fx))) {
              return invalid_performance(
                  "fx_move requires a matching open fx_engage");
            }
          } else if constexpr (
              std::is_same_v<Event, FxReleasePerformanceEvent>) {
            if (!valid_fx(payload.fx)) {
              return invalid_performance("fx_release event is invalid");
            }
            auto& active = engaged.at(static_cast<std::uint8_t>(payload.fx));
            if (!active) {
              return invalid_performance(
                  "fx_release requires a matching open fx_engage");
            }
            active = false;
          } else if constexpr (
              std::is_same_v<Event, HoldOnPerformanceEvent>) {
            if (hold_enabled) {
              return invalid_performance(
                  "hold_on requires HOLD to be off");
            }
            hold_enabled = true;
          } else if constexpr (
              std::is_same_v<Event, HoldOffPerformanceEvent>) {
            if (!hold_enabled) {
              return invalid_performance(
                  "hold_off requires HOLD to be on");
            }
            hold_enabled = false;
          } else if constexpr (
              std::is_same_v<Event, FilterChangePerformanceEvent>) {
            if (seed == nullptr) {
              return invalid_performance(
                  "filter_change requires the headered recording profile");
            }
            if (!valid_filter_phase(payload.phase) ||
                !valid_filter_type(payload.type) ||
                payload.cutoff_hz < kFilterCutoffHzMin ||
                payload.cutoff_hz > kFilterCutoffHzMax ||
                payload.resonance_milli > kFilterResonanceMilliMax) {
              return invalid_performance("filter_change event is invalid");
            }
            switch (payload.phase) {
              case PerformanceFilterPhase::engage:
                if (independent_filter_active) {
                  return invalid_performance(
                      "filter_change engage requires a disengaged "
                      "independent Filter");
                }
                // An independent engage atomically takes the single Filter
                // stage, clearing any legacy Filter engagement.
                engaged.at(0) = false;
                independent_filter_active = true;
                break;
              case PerformanceFilterPhase::move:
              case PerformanceFilterPhase::release:
                if (!independent_filter_active) {
                  return invalid_performance(
                      "filter_change requires a matching active independent "
                      "Filter gesture");
                }
                if (payload.phase == PerformanceFilterPhase::release) {
                  independent_filter_active = false;
                }
                break;
            }
          } else {
            if (seed == nullptr) {
              return invalid_performance(
                  "pad_gates_set requires the headered recording profile");
            }
          }
          return foundation::Result<void>::success();
        },
        event.payload);
    if (!valid.has_value()) {
      return valid;
    }
  }
  return foundation::Result<void>::success();
}

}  // namespace

foundation::Result<void> validate_performance_events(
    const std::vector<PerformanceEvent>& events) {
  return validate_performance_events_with_seed(
      canonical_performance_events(events), nullptr);
}

foundation::Result<void> validate_performance_events(
    const std::vector<PerformanceEvent>& events,
    const PerformanceInitialLiveState& seed) {
  return validate_performance_events_with_seed(
      canonical_performance_events(
          events, PerformanceEventProfile::header_input_sequence),
      &seed);
}

namespace {

foundation::Result<void> validate_initial_live_state(
    const PerformanceInitialLiveState& state) {
  const auto frozen_requires_hold = [&state](bool frozen) {
    return !frozen || state.hold;
  };
  if (const auto* legacy =
          std::get_if<LegacyFilterLiveState>(&state.filter)) {
    if (legacy->value > kFxValueMax ||
        !frozen_requires_hold(legacy->frozen)) {
      return invalid_performance(
          "performance initial live Filter state is invalid");
    }
  } else {
    const auto& independent =
        std::get<IndependentFilterLiveState>(state.filter);
    if (!valid_filter_type(independent.type) ||
        independent.cutoff_hz < kFilterCutoffHzMin ||
        independent.cutoff_hz > kFilterCutoffHzMax ||
        independent.resonance_milli > kFilterResonanceMilliMax ||
        !frozen_requires_hold(independent.frozen)) {
      return invalid_performance(
          "performance initial live Filter state is invalid");
    }
  }
  for (const auto& gate : state.other_fx) {
    if (gate.value > kFxValueMax || !frozen_requires_hold(gate.frozen)) {
      return invalid_performance(
          "performance initial live FX state is invalid");
    }
  }
  // The masks are uint64 bit sets, so 0-63 uniqueness and ascending wire
  // order hold by construction; only the parse boundary can violate them.
  return foundation::Result<void>::success();
}

}  // namespace

foundation::Result<void> validate_performance(
    const Performance& performance) {
  if (!is_valid_uuid(performance.id.value())) {
    return invalid_performance(
        "performance id must be a lowercase UUID");
  }
  const auto name_length = utf8_code_point_count(performance.name);
  if (!name_length.has_value() || *name_length == 0 ||
      *name_length > kPerformanceNameMax) {
    return invalid_performance(
        "performance name must contain 1 to 64 UTF-8 code points");
  }
  if (performance.created_bpm < 40 || performance.created_bpm > 240) {
    return invalid_performance(
        "performance created BPM must be between 40 and 240");
  }
  if (performance.recording_artifact.has_value() &&
      (!valid_sha256(performance.recording_artifact->sha256) ||
       performance.recording_artifact->media_type.empty())) {
    return invalid_performance(
        "performance recording artifact is invalid");
  }
  const auto profile = performance_event_profile(performance);
  if (profile == PerformanceEventProfile::header_input_sequence) {
    const auto valid_state =
        validate_initial_live_state(*performance.initial_live_state);
    if (!valid_state.has_value()) {
      return valid_state;
    }
    // Sequence numbers are unique within one Performance; gaps are legal
    // (releases, cancelled reservations and other internal admissions need
    // not become durable events).
    std::set<std::uint64_t> sequences;
    for (const auto& event : performance.events) {
      if (!event.input_sequence.has_value() ||
          !sequences.insert(*event.input_sequence).second) {
        return invalid_performance(
            "headered performance events must carry unique input sequences");
      }
    }
  }
  if (performance.events !=
      canonical_performance_events(performance.events, profile)) {
    return invalid_performance(
        "performance events must use canonical ordering");
  }
  if (profile == PerformanceEventProfile::header_input_sequence) {
    return validate_performance_events(
        performance.events, *performance.initial_live_state);
  }
  return validate_performance_events(performance.events);
}

AssetLineageSourceKind asset_lineage_source_kind(
    const AssetLineage& lineage) noexcept {
  return std::holds_alternative<SoundSetLineageSource>(lineage.source)
             ? AssetLineageSourceKind::soundset
             : AssetLineageSourceKind::asset_artifact;
}

AssetLineageDerivationKind asset_lineage_derivation_kind(
    const AssetLineage& lineage) noexcept {
  if (std::holds_alternative<CapabilityAdoptionLineageDerivation>(lineage.derivation)) {
    return AssetLineageDerivationKind::capability_adoption;
  }
  return std::holds_alternative<SoundSetInstallLineageDerivation>(
             lineage.derivation)
             ? AssetLineageDerivationKind::soundset_install
             : AssetLineageDerivationKind::resample;
}

foundation::Result<void> validate_asset_lineage(
    const AssetLineage& lineage) {
  if (const auto* artifact_source =
          std::get_if<AssetArtifactLineageSource>(&lineage.source);
      artifact_source != nullptr) {
    if (!valid_sha256(artifact_source->artifact_sha256)) {
      return invalid_asset_lineage(
          "asset Lineage source digest must be lowercase SHA-256");
    }
  } else {
    const auto& soundset = std::get<SoundSetLineageSource>(lineage.source);
    if (!is_valid_uuid(soundset.set_id)) {
      return invalid_asset_lineage(
          "asset Lineage Sound Set id must be a lowercase UUID");
    }
    if (!valid_soundset_semver(soundset.set_version)) {
      return invalid_asset_lineage(
          "asset Lineage Sound Set version must be SemVer");
    }
    if (!valid_sha256(soundset.manifest_sha256) ||
        !valid_sha256(soundset.artifact_sha256)) {
      return invalid_asset_lineage(
          "asset Lineage source digest must be lowercase SHA-256");
    }
    if (soundset.slot_index >= foundation::kSoundSetSlotCount) {
      return invalid_asset_lineage(
          "asset Lineage Sound Set slot index is out of range");
    }
  }
  if (const auto* resample =
          std::get_if<ResampleLineageDerivation>(&lineage.derivation);
      resample != nullptr) {
    if (!is_valid_uuid(resample->performance_id.value())) {
      return invalid_asset_lineage(
          "asset Lineage Performance id must be a lowercase UUID");
    }
    if (resample->range.start_frame >= resample->range.end_frame) {
      return invalid_asset_lineage(
          "asset Lineage frame range must be non-empty and increasing");
    }
  }
  if (const auto* adoption =
          std::get_if<CapabilityAdoptionLineageDerivation>(&lineage.derivation)) {
    constexpr std::uint64_t maximum = 9007199254740991ULL;
    const auto* source = std::get_if<AssetArtifactLineageSource>(&lineage.source);
    const auto valid_identity = [](const ImplementationLineageIdentity& value) {
      return !value.id.empty() && !value.version.empty() &&
             valid_sha256(value.artifact_sha256);
    };
    // Attempt IDs come from SDK evidence, whose identifiers are not UUID-only.
    const auto& attempt_id = adoption->attempt_id.value();
    const bool valid_attempt = !attempt_id.empty() && attempt_id.size() <= 128 &&
        std::all_of(attempt_id.begin(), attempt_id.end(), [](unsigned char c) {
          return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                 (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
        });
    if (source == nullptr ||
        adoption->capability.id != "sample.slice.v1" ||
        adoption->capability.contract != "lmdj.capability.v2" ||
        !valid_soundset_semver(adoption->capability.version) ||
        !valid_identity(adoption->provider) ||
        !valid_soundset_semver(adoption->provider.version) ||
        (adoption->model_identity && !valid_identity(*adoption->model_identity)) ||
        !valid_sha256(adoption->parameters_sha256) ||
        !valid_attempt ||
        !is_valid_uuid(adoption->source_asset_id.value()) ||
        !valid_sha256(adoption->output_artifact.sha256) ||
        adoption->output_artifact.media_type != "application/json" ||
        adoption->output_artifact.byte_length == 0 ||
        adoption->output_artifact.byte_length > 262144 ||
        adoption->recipe.start_frame >= adoption->recipe.end_frame ||
        adoption->recipe.end_frame > maximum ||
        (adoption->recipe.frame_rate != 44100 && adoption->recipe.frame_rate != 48000)) {
      return invalid_asset_lineage("capability adoption evidence is invalid");
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<AssetLineage> asset_lineage_from_json(
    const nlohmann::json& input) {
  try {
    if (!exact_object_keys(input, {"source", "derivation"})) {
      return invalid_asset_lineage_value(
          "asset Lineage must contain exact source and derivation objects");
    }
    const auto& source = input.at("source");
    const auto& derivation = input.at("derivation");
    if (!source.is_object() || !source.contains("kind") ||
        !source.at("kind").is_string() || !derivation.is_object() ||
        !derivation.contains("kind") || !derivation.at("kind").is_string()) {
      return invalid_asset_lineage_value(
          "asset Lineage must declare a supported source and derivation kind");
    }
    const auto source_kind = source.at("kind").get<std::string>();
    const auto derivation_kind = derivation.at("kind").get<std::string>();
    AssetLineageSource parsed_source;
    if (source_kind == "asset_artifact") {
      if (!exact_object_keys(
              source,
              {"kind", "artifact_sha256", "project_revision"}) ||
          !source.at("artifact_sha256").is_string()) {
        return invalid_asset_lineage_value(
            "asset Lineage source shape or value is invalid");
      }
      const auto project_revision =
          unsigned_value(source.at("project_revision"));
      if (!project_revision.has_value()) {
        return invalid_asset_lineage_value(
            "asset Lineage integer value is invalid");
      }
      parsed_source = AssetArtifactLineageSource{
          source.at("artifact_sha256").get<std::string>(),
          *project_revision,
      };
    } else if (source_kind == "soundset") {
      if (!exact_object_keys(
              source,
              {"kind",
               "set_id",
               "set_version",
               "manifest_sha256",
               "slot_index",
               "artifact_sha256"}) ||
          !source.at("set_id").is_string() ||
          !source.at("set_version").is_string() ||
          !source.at("manifest_sha256").is_string() ||
          !source.at("artifact_sha256").is_string()) {
        return invalid_asset_lineage_value(
            "asset Lineage source shape or value is invalid");
      }
      const auto slot_index = bounded_unsigned(
          source.at("slot_index"),
          static_cast<std::uint64_t>(foundation::kSoundSetSlotCount) - 1);
      if (!slot_index.has_value()) {
        return invalid_asset_lineage_value(
            "asset Lineage integer value is invalid");
      }
      parsed_source = SoundSetLineageSource{
          source.at("set_id").get<std::string>(),
          source.at("set_version").get<std::string>(),
          source.at("manifest_sha256").get<std::string>(),
          static_cast<std::uint8_t>(*slot_index),
          source.at("artifact_sha256").get<std::string>(),
      };
    } else {
      return invalid_asset_lineage_value(
          "asset Lineage source shape or value is invalid");
    }
    AssetLineageDerivation parsed_derivation{
        SoundSetInstallLineageDerivation{}};
    if (derivation_kind == "resample") {
      if (!exact_object_keys(
              derivation,
              {"kind", "range", "performance_id"}) ||
          !derivation.at("performance_id").is_string()) {
        return invalid_asset_lineage_value(
            "asset Lineage derivation shape or value is invalid");
      }
      const auto& range = derivation.at("range");
      if (!exact_object_keys(range, {"start_frame", "end_frame"})) {
        return invalid_asset_lineage_value(
            "asset Lineage range shape is invalid");
      }
      const auto start_frame = unsigned_value(range.at("start_frame"));
      const auto end_frame = unsigned_value(range.at("end_frame"));
      if (!start_frame.has_value() || !end_frame.has_value()) {
        return invalid_asset_lineage_value(
            "asset Lineage integer value is invalid");
      }
      parsed_derivation = ResampleLineageDerivation{
          {*start_frame, *end_frame},
          PerformanceId{derivation.at("performance_id").get<std::string>()},
      };
    } else if (derivation_kind == "capability_adoption") {
      const auto& capability = derivation.at("capability");
      const auto& output = derivation.at("output_artifact");
      const auto& recipe = derivation.at("recipe");
      if (!exact_object_keys(derivation,
              {"kind", "capability", "provider", "model_identity",
               "parameters_sha256", "attempt_id", "source_asset_id",
               "output_artifact", "recipe"}) ||
          !exact_object_keys(capability, {"id", "contract", "version"}) ||
          !exact_object_keys(output, {"sha256", "media_type", "byte_length"}) ||
          !exact_object_keys(recipe, {"kind", "start_frame", "end_frame", "frame_rate"}) ||
          recipe.at("kind") != "slice_interval_v1") {
        return invalid_asset_lineage_value("capability adoption shape is invalid");
      }
      const auto identity = [](const nlohmann::json& value) {
        if (!exact_object_keys(value, {"id", "version", "artifact_sha256"})) {
          throw std::invalid_argument("identity shape is invalid");
        }
        return ImplementationLineageIdentity{
            value.at("id").get<std::string>(), value.at("version").get<std::string>(),
            value.at("artifact_sha256").get<std::string>()};
      };
      const auto start = unsigned_value(recipe.at("start_frame"));
      const auto end = unsigned_value(recipe.at("end_frame"));
      const auto rate = bounded_unsigned(recipe.at("frame_rate"), 48000);
      const auto length = unsigned_value(output.at("byte_length"));
      if (!start || !end || !rate || !length) {
        return invalid_asset_lineage_value("capability adoption integer is invalid");
      }
      std::optional<ImplementationLineageIdentity> model;
      if (!derivation.at("model_identity").is_null()) {
        model = identity(derivation.at("model_identity"));
      }
      parsed_derivation = CapabilityAdoptionLineageDerivation{
          {capability.at("id").get<std::string>(),
           capability.at("contract").get<std::string>(),
           capability.at("version").get<std::string>()},
          identity(derivation.at("provider")), std::move(model),
          derivation.at("parameters_sha256").get<std::string>(),
          foundation::AttemptId{derivation.at("attempt_id").get<std::string>()},
          foundation::AssetId{derivation.at("source_asset_id").get<std::string>()},
          {output.at("sha256").get<std::string>(),
           output.at("media_type").get<std::string>(), *length},
          {*start, *end, static_cast<std::uint32_t>(*rate)}};
    } else if (derivation_kind == "soundset_install") {
      if (!exact_object_keys(derivation, {"kind"})) {
        return invalid_asset_lineage_value(
            "asset Lineage derivation shape or value is invalid");
      }
      parsed_derivation = SoundSetInstallLineageDerivation{};
    } else {
      return invalid_asset_lineage_value(
          "asset Lineage derivation shape or value is invalid");
    }
    AssetLineage lineage{
        std::move(parsed_source),
        std::move(parsed_derivation),
    };
    const auto valid = validate_asset_lineage(lineage);
    if (!valid.has_value()) {
      return foundation::Result<AssetLineage>::failure(valid.error());
    }
    return foundation::Result<AssetLineage>::success(std::move(lineage));
  } catch (const std::exception&) {
    return invalid_asset_lineage_value(
        "asset Lineage shape or value is invalid");
  }
}

nlohmann::json asset_lineage_json(const AssetLineage& lineage) {
  nlohmann::json source;
  if (const auto* artifact_source =
          std::get_if<AssetArtifactLineageSource>(&lineage.source);
      artifact_source != nullptr) {
    source = {
        {"kind", "asset_artifact"},
        {"artifact_sha256", artifact_source->artifact_sha256},
        {"project_revision", artifact_source->project_revision},
    };
  } else {
    const auto& soundset = std::get<SoundSetLineageSource>(lineage.source);
    source = {
        {"kind", "soundset"},
        {"set_id", soundset.set_id},
        {"set_version", soundset.set_version},
        {"manifest_sha256", soundset.manifest_sha256},
        {"slot_index", soundset.slot_index},
        {"artifact_sha256", soundset.artifact_sha256},
    };
  }
  nlohmann::json derivation;
  if (const auto* resample =
          std::get_if<ResampleLineageDerivation>(&lineage.derivation);
      resample != nullptr) {
    derivation = {
        {"kind", "resample"},
        {"range",
         {{"start_frame", resample->range.start_frame},
          {"end_frame", resample->range.end_frame}}},
        {"performance_id", resample->performance_id.value()},
    };
  } else if (const auto* adoption =
                 std::get_if<CapabilityAdoptionLineageDerivation>(&lineage.derivation)) {
    const auto identity = [](const ImplementationLineageIdentity& value) {
      return nlohmann::json{{"id", value.id}, {"version", value.version},
                            {"artifact_sha256", value.artifact_sha256}};
    };
    derivation = {
        {"kind", "capability_adoption"},
        {"capability", {{"id", adoption->capability.id},
                        {"contract", adoption->capability.contract},
                        {"version", adoption->capability.version}}},
        {"provider", identity(adoption->provider)},
        {"model_identity", adoption->model_identity
                               ? identity(*adoption->model_identity) : nlohmann::json(nullptr)},
        {"parameters_sha256", adoption->parameters_sha256},
        {"attempt_id", adoption->attempt_id.value()},
        {"source_asset_id", adoption->source_asset_id.value()},
        {"output_artifact", {{"sha256", adoption->output_artifact.sha256},
                            {"media_type", adoption->output_artifact.media_type},
                            {"byte_length", adoption->output_artifact.byte_length}}},
        {"recipe", {{"kind", "slice_interval_v1"},
                    {"start_frame", adoption->recipe.start_frame},
                    {"end_frame", adoption->recipe.end_frame},
                    {"frame_rate", adoption->recipe.frame_rate}}}};
  } else {
    derivation = nlohmann::json::object({{"kind", "soundset_install"}});
  }
  return {
      {"source", std::move(source)},
      {"derivation", std::move(derivation)},
  };
}

foundation::Result<PerformanceEvent> performance_event_from_json(
    const nlohmann::json& input) {
  try {
    if (!input.is_object() || !input.contains("kind") ||
        !input.at("kind").is_string()) {
      return invalid_performance_event(
          "performance event must declare a supported kind");
    }
    const auto kind = input.at("kind").get<std::string>();
    // The legacy kinds gain one optional trailing key in the headered
    // profile; every other field set is exact, as before.
    const auto optional_sequence =
        [&input]() -> std::optional<std::optional<std::uint64_t>> {
      if (!input.contains("input_sequence")) {
        return std::optional<std::optional<std::uint64_t>>{
            std::in_place, std::nullopt};
      }
      const auto parsed = parse_input_sequence(input.at("input_sequence"));
      if (!parsed.has_value()) {
        return std::nullopt;
      }
      return std::optional<std::optional<std::uint64_t>>{
          std::in_place, *parsed};
    };
    if (kind == "pad_hit" &&
        (exact_object_keys(
             input,
             {"kind", "slot", "onset_tick", "duration_tick", "velocity"}) ||
         exact_object_keys(
             input,
             {"kind", "slot", "onset_tick", "duration_tick", "velocity",
              "input_sequence"}))) {
      const auto slot = bounded_unsigned(
          input.at("slot"), kPerformancePadSlotMax);
      const auto onset_tick = unsigned_value(input.at("onset_tick"));
      const auto duration_tick = unsigned_value(input.at("duration_tick"));
      const auto velocity = bounded_unsigned(input.at("velocity"), 127);
      const auto sequence = optional_sequence();
      if (slot.has_value() && onset_tick.has_value() &&
          duration_tick.has_value() && *duration_tick > 0 &&
          velocity.has_value() && *velocity > 0 && sequence.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{
                PadHitPerformanceEvent{
                    static_cast<std::uint8_t>(*slot),
                    *onset_tick,
                    *duration_tick,
                    static_cast<std::uint8_t>(*velocity),
                },
                *sequence,
            });
      }
    } else if (
        kind == "pattern_launch" &&
        (exact_object_keys(
             input, {"kind", "pattern_slot", "effective_tick"}) ||
         exact_object_keys(
             input,
             {"kind", "pattern_slot", "effective_tick", "input_sequence"}))) {
      const auto slot = bounded_unsigned(
          input.at("pattern_slot"), kPatternSlotMax);
      const auto tick = unsigned_value(input.at("effective_tick"));
      const auto sequence = optional_sequence();
      if (slot.has_value() && tick.has_value() && sequence.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{
                PatternLaunchPerformanceEvent{
                    static_cast<std::uint8_t>(*slot), *tick},
                *sequence,
            });
      }
    } else if (
        (kind == "fx_engage" || kind == "fx_move") &&
        (exact_object_keys(input, {"kind", "fx", "value", "tick"}) ||
         exact_object_keys(
             input, {"kind", "fx", "value", "tick", "input_sequence"}))) {
      const auto fx = bounded_unsigned(input.at("fx"), kFxCount - 1);
      const auto value = bounded_unsigned(input.at("value"), kFxValueMax);
      const auto tick = unsigned_value(input.at("tick"));
      const auto sequence = optional_sequence();
      if (fx.has_value() && value.has_value() && tick.has_value() &&
          sequence.has_value()) {
        const auto typed_fx = static_cast<PerformanceFx>(*fx);
        if (kind == "fx_engage") {
          return foundation::Result<PerformanceEvent>::success(
              PerformanceEvent{
                  FxEngagePerformanceEvent{
                      typed_fx, static_cast<std::uint16_t>(*value), *tick},
                  *sequence,
              });
        }
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{
                FxMovePerformanceEvent{
                    typed_fx, static_cast<std::uint16_t>(*value), *tick},
                *sequence,
            });
      }
    } else if (
        kind == "fx_release" &&
        (exact_object_keys(input, {"kind", "fx", "tick"}) ||
         exact_object_keys(
             input, {"kind", "fx", "tick", "input_sequence"}))) {
      const auto fx = bounded_unsigned(input.at("fx"), kFxCount - 1);
      const auto tick = unsigned_value(input.at("tick"));
      const auto sequence = optional_sequence();
      if (fx.has_value() && tick.has_value() && sequence.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{
                FxReleasePerformanceEvent{
                    static_cast<PerformanceFx>(*fx), *tick},
                *sequence,
            });
      }
    } else if (
        (kind == "hold_on" || kind == "hold_off") &&
        (exact_object_keys(input, {"kind", "tick"}) ||
         exact_object_keys(input, {"kind", "tick", "input_sequence"}))) {
      const auto tick = unsigned_value(input.at("tick"));
      const auto sequence = optional_sequence();
      if (tick.has_value() && sequence.has_value()) {
        if (kind == "hold_on") {
          return foundation::Result<PerformanceEvent>::success(
              PerformanceEvent{HoldOnPerformanceEvent{*tick}, *sequence});
        }
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{HoldOffPerformanceEvent{*tick}, *sequence});
      }
    } else if (
        kind == "filter_change" &&
        exact_object_keys(
            input,
            {"kind", "tick", "input_sequence", "phase", "type", "cutoff_hz",
             "resonance_milli"})) {
      const auto tick = unsigned_value(input.at("tick"));
      const auto sequence = parse_input_sequence(input.at("input_sequence"));
      const auto cutoff =
          bounded_unsigned(input.at("cutoff_hz"), kFilterCutoffHzMax);
      const auto resonance = bounded_unsigned(
          input.at("resonance_milli"), kFilterResonanceMilliMax);
      const auto type = input.at("type").is_string()
                            ? filter_type_from_string(
                                  input.at("type").get<std::string>())
                            : std::nullopt;
      const auto phase = input.at("phase").is_string()
                             ? filter_phase_from_string(
                                   input.at("phase").get<std::string>())
                             : std::nullopt;
      if (tick.has_value() && sequence.has_value() && cutoff.has_value() &&
          *cutoff >= kFilterCutoffHzMin && resonance.has_value() &&
          type.has_value() && phase.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{
                FilterChangePerformanceEvent{
                    *phase,
                    *type,
                    static_cast<std::uint16_t>(*cutoff),
                    static_cast<std::uint16_t>(*resonance),
                    *tick,
                },
                *sequence,
            });
      }
    } else if (
        kind == "pad_gates_set" &&
        exact_object_keys(
            input,
            {"kind", "tick", "input_sequence", "muted_slots",
             "solo_slots"})) {
      const auto tick = unsigned_value(input.at("tick"));
      const auto sequence = parse_input_sequence(input.at("input_sequence"));
      const auto muted = slot_mask_from_json(input.at("muted_slots"));
      const auto solo = slot_mask_from_json(input.at("solo_slots"));
      if (tick.has_value() && sequence.has_value() && muted.has_value() &&
          solo.has_value()) {
        return foundation::Result<PerformanceEvent>::success(
            PerformanceEvent{
                PadGatesSetPerformanceEvent{*muted, *solo, *tick},
                *sequence,
            });
      }
    }
  } catch (const std::exception&) {
  }
  return invalid_performance_event(
      "performance event shape or value is invalid");
}

nlohmann::json performance_event_json(const PerformanceEvent& event) {
  auto encoded = std::visit(
      [](const auto& payload) -> nlohmann::json {
        using Event = std::decay_t<decltype(payload)>;
        if constexpr (std::is_same_v<Event, PadHitPerformanceEvent>) {
          return {
              {"duration_tick", payload.duration_tick},
              {"kind", "pad_hit"},
              {"onset_tick", payload.onset_tick},
              {"slot", payload.slot},
              {"velocity", payload.velocity},
          };
        } else if constexpr (
            std::is_same_v<Event, PatternLaunchPerformanceEvent>) {
          return {
              {"effective_tick", payload.effective_tick},
              {"kind", "pattern_launch"},
              {"pattern_slot", payload.pattern_slot},
          };
        } else if constexpr (
            std::is_same_v<Event, FxEngagePerformanceEvent>) {
          return {
              {"fx", static_cast<std::uint8_t>(payload.fx)},
              {"kind", "fx_engage"},
              {"tick", payload.tick},
              {"value", payload.value},
          };
        } else if constexpr (
            std::is_same_v<Event, FxMovePerformanceEvent>) {
          return {
              {"fx", static_cast<std::uint8_t>(payload.fx)},
              {"kind", "fx_move"},
              {"tick", payload.tick},
              {"value", payload.value},
          };
        } else if constexpr (
            std::is_same_v<Event, FxReleasePerformanceEvent>) {
          return {
              {"fx", static_cast<std::uint8_t>(payload.fx)},
              {"kind", "fx_release"},
              {"tick", payload.tick},
          };
        } else if constexpr (
            std::is_same_v<Event, HoldOnPerformanceEvent>) {
          return {{"kind", "hold_on"}, {"tick", payload.tick}};
        } else if constexpr (
            std::is_same_v<Event, HoldOffPerformanceEvent>) {
          return {{"kind", "hold_off"}, {"tick", payload.tick}};
        } else if constexpr (
            std::is_same_v<Event, FilterChangePerformanceEvent>) {
          return {
              {"cutoff_hz", payload.cutoff_hz},
              {"kind", "filter_change"},
              {"phase", filter_phase_string(payload.phase)},
              {"resonance_milli", payload.resonance_milli},
              {"tick", payload.tick},
              {"type", filter_type_string(payload.type)},
          };
        } else {
          return {
              {"kind", "pad_gates_set"},
              {"muted_slots", slot_mask_json(payload.muted_mask)},
              {"solo_slots", slot_mask_json(payload.solo_mask)},
              {"tick", payload.tick},
          };
        }
      },
      event.payload);
  if (event.input_sequence.has_value()) {
    encoded["input_sequence"] = std::to_string(*event.input_sequence);
  } else {
    encoded.erase("input_sequence");
  }
  return encoded;
}

namespace {

constexpr std::array<std::string_view, kFxCount - 1> kLiveGateFxNames{
    "delay", "reverb", "stutter", "gate", "reverse", "crush", "cutter"};

foundation::Result<PerformanceInitialLiveState> invalid_initial_live_state(
    std::string_view message) {
  return foundation::Result<PerformanceInitialLiveState>::failure(
      foundation::Error{
          foundation::ErrorCode::invalid_argument,
          std::string(message),
      });
}

foundation::Result<PerformanceFxGateState> gate_state_from_json(
    const nlohmann::json& input) {
  if (!exact_object_keys(input, {"engaged", "frozen", "value"}) ||
      !input.at("engaged").is_boolean() || !input.at("frozen").is_boolean()) {
    return foundation::Result<PerformanceFxGateState>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "live FX gate state shape is invalid",
        });
  }
  const auto value = bounded_unsigned(input.at("value"), kFxValueMax);
  if (!value.has_value()) {
    return foundation::Result<PerformanceFxGateState>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_argument,
            "live FX gate state shape is invalid",
        });
  }
  return foundation::Result<PerformanceFxGateState>::success(
      PerformanceFxGateState{
          input.at("engaged").get<bool>(),
          input.at("frozen").get<bool>(),
          static_cast<std::uint16_t>(*value),
      });
}

nlohmann::json gate_state_json(const PerformanceFxGateState& state) {
  return {
      {"engaged", state.engaged},
      {"frozen", state.frozen},
      {"value", state.value},
  };
}

}  // namespace

foundation::Result<PerformanceInitialLiveState>
performance_initial_live_state_from_json(const nlohmann::json& input) {
  try {
    if (!exact_object_keys(
            input, {"hold", "filter", "other_fx", "muted_slots",
                    "solo_slots"}) ||
        !input.at("hold").is_boolean()) {
      return invalid_initial_live_state(
          "performance initial live state shape is invalid");
    }
    PerformanceInitialLiveState state;
    state.hold = input.at("hold").get<bool>();
    const auto& filter = input.at("filter");
    if (!filter.is_object() || !filter.contains("mode") ||
        !filter.at("mode").is_string()) {
      return invalid_initial_live_state(
          "performance initial live Filter shape is invalid");
    }
    const auto mode = filter.at("mode").get<std::string>();
    if (mode == "legacy") {
      if (!exact_object_keys(
              filter, {"mode", "engaged", "frozen", "value"}) ||
          !filter.at("engaged").is_boolean() ||
          !filter.at("frozen").is_boolean()) {
        return invalid_initial_live_state(
            "performance initial live Filter shape is invalid");
      }
      const auto value = bounded_unsigned(filter.at("value"), kFxValueMax);
      if (!value.has_value()) {
        return invalid_initial_live_state(
            "performance initial live Filter shape is invalid");
      }
      state.filter = LegacyFilterLiveState{
          filter.at("engaged").get<bool>(),
          filter.at("frozen").get<bool>(),
          static_cast<std::uint16_t>(*value),
      };
    } else if (mode == "independent") {
      if (!exact_object_keys(
              filter,
              {"mode", "engaged", "frozen", "type", "cutoff_hz",
               "resonance_milli"}) ||
          !filter.at("engaged").is_boolean() ||
          !filter.at("frozen").is_boolean() ||
          !filter.at("type").is_string()) {
        return invalid_initial_live_state(
            "performance initial live Filter shape is invalid");
      }
      const auto type =
          filter_type_from_string(filter.at("type").get<std::string>());
      const auto cutoff =
          bounded_unsigned(filter.at("cutoff_hz"), kFilterCutoffHzMax);
      const auto resonance = bounded_unsigned(
          filter.at("resonance_milli"), kFilterResonanceMilliMax);
      if (!type.has_value() || !cutoff.has_value() ||
          *cutoff < kFilterCutoffHzMin || !resonance.has_value()) {
        return invalid_initial_live_state(
            "performance initial live Filter shape is invalid");
      }
      state.filter = IndependentFilterLiveState{
          filter.at("engaged").get<bool>(),
          filter.at("frozen").get<bool>(),
          *type,
          static_cast<std::uint16_t>(*cutoff),
          static_cast<std::uint16_t>(*resonance),
      };
    } else {
      return invalid_initial_live_state(
          "performance initial live Filter shape is invalid");
    }
    const auto& other_fx = input.at("other_fx");
    if (!other_fx.is_object() || other_fx.size() != kLiveGateFxNames.size()) {
      return invalid_initial_live_state(
          "performance initial live state other_fx is invalid");
    }
    for (std::size_t index = 0; index < kLiveGateFxNames.size(); ++index) {
      const auto name = std::string{kLiveGateFxNames.at(index)};
      if (!other_fx.contains(name)) {
        return invalid_initial_live_state(
            "performance initial live state other_fx is invalid");
      }
      auto gate = gate_state_from_json(other_fx.at(name));
      if (!gate.has_value()) {
        return foundation::Result<PerformanceInitialLiveState>::failure(
            gate.error());
      }
      state.other_fx.at(index) = gate.value();
    }
    const auto muted = slot_mask_from_json(input.at("muted_slots"));
    const auto solo = slot_mask_from_json(input.at("solo_slots"));
    if (!muted.has_value() || !solo.has_value()) {
      return invalid_initial_live_state(
          "performance initial live state slot masks are invalid");
    }
    state.muted_mask = *muted;
    state.solo_mask = *solo;
    return foundation::Result<PerformanceInitialLiveState>::success(
        std::move(state));
  } catch (const std::exception&) {
    return invalid_initial_live_state(
        "performance initial live state shape is invalid");
  }
}

nlohmann::json performance_initial_live_state_json(
    const PerformanceInitialLiveState& state) {
  nlohmann::json filter;
  if (const auto* legacy =
          std::get_if<LegacyFilterLiveState>(&state.filter)) {
    filter = {
        {"engaged", legacy->engaged},
        {"frozen", legacy->frozen},
        {"mode", "legacy"},
        {"value", legacy->value},
    };
  } else {
    const auto& independent =
        std::get<IndependentFilterLiveState>(state.filter);
    filter = {
        {"cutoff_hz", independent.cutoff_hz},
        {"engaged", independent.engaged},
        {"frozen", independent.frozen},
        {"mode", "independent"},
        {"resonance_milli", independent.resonance_milli},
        {"type", filter_type_string(independent.type)},
    };
  }
  auto other_fx = nlohmann::json::object();
  for (std::size_t index = 0; index < kLiveGateFxNames.size(); ++index) {
    other_fx[std::string{kLiveGateFxNames.at(index)}] =
        gate_state_json(state.other_fx.at(index));
  }
  return {
      {"filter", std::move(filter)},
      {"hold", state.hold},
      {"muted_slots", slot_mask_json(state.muted_mask)},
      {"other_fx", std::move(other_fx)},
      {"solo_slots", slot_mask_json(state.solo_mask)},
  };
}

}  // namespace lmdj::domain
