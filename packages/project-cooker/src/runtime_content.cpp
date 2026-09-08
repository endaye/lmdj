#include <lmdj/cooker/runtime_content.hpp>

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <limits>
#include <tuple>
#include <utility>

#include <picosha2.h>

namespace lmdj::cooker {
namespace {

using foundation::Error;
using foundation::ErrorCode;
using foundation::Result;
using Digest = std::array<unsigned char, 32>;
constexpr std::size_t kHeaderBytes = 136;
constexpr std::size_t kPadBytes = 20;
constexpr std::size_t kEventBytes = 12;
constexpr std::size_t kSampleHeaderBytes = 12;
constexpr std::uint64_t kRequiredCapabilities = 7;
constexpr std::string_view kMagic = "LMDJRC01";
static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);
static_assert(std::numeric_limits<std::int16_t>::min() == -32'768);

struct InvalidContent {
  const char* condition;
  const char* why;
};

void require(bool valid, const char* condition, const char* why) {
  if (!valid) {
    throw InvalidContent{condition, why};
  }
}

Error content_error(InvalidContent error) {
  return Error{
      ErrorCode::invalid_argument,
      std::string("why: ") + error.why +
          "; remedy: supply canonical supported runtime content within the caller limits",
      {{"runtime_content_condition", error.condition}},
  };
}

Error construction_error() {
  return Error{
      ErrorCode::internal_error,
      "why: runtime content construction failed; remedy: retry with available resources and never publish a partial result",
  };
}

std::uint64_t add(std::uint64_t left, std::uint64_t right) {
  require(right <= std::numeric_limits<std::uint64_t>::max() - left,
          "overflow", "runtime content byte count overflows");
  return left + right;
}

std::uint64_t multiply(std::uint64_t left, std::uint64_t right) {
  require(right == 0 || left <= std::numeric_limits<std::uint64_t>::max() / right,
          "overflow", "runtime content byte product overflows");
  return left * right;
}

std::size_t size(std::uint64_t value) {
  require(value <= std::numeric_limits<std::size_t>::max(),
          "overflow", "runtime content length exceeds addressable memory");
  return static_cast<std::size_t>(value);
}

void hash_bytes(picosha2::hash256_one_by_one& hasher,
                std::span<const std::byte> bytes) {
  // picosha2 buffers an entire process() range before reducing it. Bound each
  // range so integrity checking cannot allocate another content-sized buffer.
  while (!bytes.empty()) {
    const auto count = std::min<std::size_t>(bytes.size(), 512);
    const auto* data = reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(data, data + count);
    bytes = bytes.subspan(count);
  }
}

Digest finish_hash(picosha2::hash256_one_by_one& hasher) {
  hasher.finish();
  Digest result{};
  hasher.get_hash_bytes(result.begin(), result.end());
  return result;
}

Digest hash(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  hash_bytes(hasher, bytes);
  return finish_hash(hasher);
}

std::string hex(const Digest& digest) {
  return picosha2::bytes_to_hex_string(digest.begin(), digest.end());
}

class Reader {
 public:
  explicit Reader(std::span<const std::byte> bytes) : bytes_(bytes) {}

  std::span<const std::byte> take(std::uint64_t length) {
    require(length <= bytes_.size(), "length", "runtime content is truncated");
    const auto result = bytes_.first(size(length));
    bytes_ = bytes_.subspan(size(length));
    return result;
  }

  std::uint64_t integer(std::size_t width) {
    const auto bytes = take(width);
    std::uint64_t value = 0;
    for (std::size_t index = 0; index < width; ++index) {
      value |= std::to_integer<std::uint64_t>(bytes[index]) << (index * 8);
    }
    return value;
  }

  std::string text(std::size_t length) {
    const auto bytes = take(length);
    return {reinterpret_cast<const char*>(bytes.data()), bytes.size()};
  }

  bool empty() const noexcept { return bytes_.empty(); }

 private:
  std::span<const std::byte> bytes_;
};

void append(std::vector<std::byte>& bytes, std::uint64_t value,
            std::size_t width) {
  for (std::size_t index = 0; index < width; ++index) {
    bytes.push_back(static_cast<std::byte>((value >> (index * 8)) & 0xffU));
  }
}

void append_text(std::vector<std::byte>& bytes, std::string_view value) {
  for (const auto character : value) {
    bytes.push_back(static_cast<std::byte>(character));
  }
}

void validate_pattern(const RuntimeSnapshot& snapshot) {
  require(domain::is_valid_uuid(snapshot.project_id.value()) &&
              domain::is_valid_uuid(snapshot.pattern_id.value()),
          "source", "runtime content source identity is invalid");
  require(snapshot.bpm >= 40 && snapshot.bpm <= 240 &&
              (snapshot.bars == 1 || snapshot.bars == 2 ||
               snapshot.bars == 4 || snapshot.bars == 8) &&
              snapshot.ppq == 960 &&
              snapshot.loop_length_ticks ==
                  static_cast<std::uint32_t>(snapshot.bars) * 4U * 960U,
          "timing", "runtime content Pattern timing is invalid");
}

void validate_counts(std::uint64_t pads, std::uint64_t events,
                     std::uint64_t samples, const RuntimeContentLimits& limits) {
  require(pads <= 64 && samples <= pads &&
              events <= std::numeric_limits<std::uint32_t>::max(),
          "counts", "runtime content table counts are invalid");
  require(pads <= limits.maximum_pads, "pad_limit",
          "runtime content exceeds the Pad allowance");
  require(events <= limits.maximum_events, "event_limit",
          "runtime content exceeds the event allowance");
}

std::uint32_t mode_number(domain::TriggerMode mode) {
  switch (mode) {
    case domain::TriggerMode::one_shot: return 0;
    case domain::TriggerMode::gate: return 1;
    case domain::TriggerMode::loop_gate: return 2;
    case domain::TriggerMode::loop_toggle: return 3;
  }
  throw InvalidContent{"playback", "runtime content trigger mode is unsupported"};
}

domain::TriggerMode read_mode(std::uint64_t mode) {
  constexpr std::array modes{
      domain::TriggerMode::one_shot, domain::TriggerMode::gate,
      domain::TriggerMode::loop_gate, domain::TriggerMode::loop_toggle};
  require(mode < modes.size(), "playback",
          "runtime content trigger mode is unsupported");
  return modes[static_cast<std::size_t>(mode)];
}

std::size_t slot_number(domain::PadSlotId slot) {
  require(domain::is_valid_slot(slot), "slot", "runtime content Pad Slot is invalid");
  return static_cast<std::size_t>(slot.bank) * 16 + slot.pad;
}

void validate_playback(const ResolvedPlayback& playback, std::uint32_t frames) {
  (void)mode_number(playback.trigger_mode);
  require(playback.start_frame < playback.end_frame &&
              playback.end_frame <= frames && std::isfinite(playback.linear_gain) &&
              !std::signbit(playback.linear_gain) && playback.linear_gain <= 2.0F,
          "playback", "runtime content playback range or gain is invalid");
}

auto event_key(const ResolvedEvent& event) {
  return std::tuple{event.onset_tick, event.slot.bank, event.slot.pad};
}

void validate_event(const ResolvedEvent& event, std::uint32_t loop_ticks) {
  (void)slot_number(event.slot);
  require(event.velocity >= 1 && event.velocity <= 127 &&
              event.onset_tick < loop_ticks && event.duration_tick > 0 &&
              event.duration_tick <= loop_ticks - event.onset_tick,
          "event", "runtime content event timing or velocity is invalid");
}

std::uint32_t validate_sample(const PcmSample& sample,
                              const RuntimeContentLimits& limits) {
  require(sample.sample_rate == 48'000 &&
              (sample.channels == 1 || sample.channels == 2) &&
              !sample.interleaved.empty() &&
              sample.interleaved.size() % sample.channels == 0,
          "pcm", "runtime content requires complete 48 kHz mono/stereo PCM16 frames");
  const auto frames = sample.interleaved.size() / sample.channels;
  require(frames <= std::numeric_limits<std::uint32_t>::max() &&
              frames <= limits.maximum_sample_frames,
          "frame_limit", "runtime content exceeds the sample frame allowance");
  return static_cast<std::uint32_t>(frames);
}

std::array<unsigned char, kSampleHeaderBytes> sample_header(
    const PcmSample& sample) {
  const auto frames = sample.interleaved.size() / sample.channels;
  return {0x80, 0xbb, 0, 0, static_cast<unsigned char>(sample.channels), 0, 0, 0,
          static_cast<unsigned char>(frames & 0xffU),
          static_cast<unsigned char>((frames >> 8) & 0xffU),
          static_cast<unsigned char>((frames >> 16) & 0xffU),
          static_cast<unsigned char>((frames >> 24) & 0xffU)};
}

Digest sample_hash(const PcmSample& sample) {
  picosha2::hash256_one_by_one hasher;
  const auto header = sample_header(sample);
  hasher.process(header.begin(), header.end());
  // A fixed small hash workspace; do not duplicate the entire PCM buffer.
  std::array<unsigned char, 512> chunk{};
  std::size_t used = 0;
  for (const auto pcm : sample.interleaved) {
    const auto word = static_cast<std::uint16_t>(pcm);
    chunk[used++] = static_cast<unsigned char>(word & 0xffU);
    chunk[used++] = static_cast<unsigned char>(word >> 8);
    if (used == chunk.size()) {
      hasher.process(chunk.begin(), chunk.end());
      used = 0;
    }
  }
  hasher.process(chunk.begin(), chunk.begin() + static_cast<std::ptrdiff_t>(used));
  return finish_hash(hasher);
}

struct EncodedSample {
  const PcmSample* pcm{};
  Digest digest{};
  std::uint64_t body_bytes{};
};

EncodedRuntimeContent encode(const RuntimeSnapshot& snapshot,
                             const RuntimeContentLimits& limits) {
  validate_pattern(snapshot);
  validate_counts(snapshot.pads.size(), snapshot.events.size(), 0, limits);
  std::array<EncodedSample, 64> samples{};
  std::array<std::uint32_t, 64> pad_sample{};
  std::array<const ResolvedPad*, 64> by_slot{};
  std::uint32_t sample_count = 0;
  std::uint64_t pcm_bytes = 0;
  auto encoded_bytes = add(kHeaderBytes, add(multiply(snapshot.pads.size(), kPadBytes),
                                            multiply(snapshot.events.size(), kEventBytes)));
  require(encoded_bytes <= limits.maximum_encoded_bytes, "encoded_limit",
          "runtime content tables exceed the encoded byte allowance");
  std::size_t prior_slot = 0;
  for (std::size_t index = 0; index < snapshot.pads.size(); ++index) {
    const auto& pad = snapshot.pads[index];
    const auto slot = slot_number(pad.slot);
    require(index == 0 || slot > prior_slot, "pad_order",
            "runtime content Pads are duplicated or not canonically ordered");
    prior_slot = slot;
    require(pad.sample != nullptr, "pcm", "runtime content Pad has no PCM");
    const auto frames = validate_sample(*pad.sample, limits);
    validate_playback(pad.playback, frames);
    const auto sample_bytes = multiply(pad.sample->interleaved.size(), 2);
    require(sample_bytes <= limits.maximum_pcm_bytes, "pcm_limit",
            "runtime content sample exceeds the decoded PCM allowance");
    const auto digest = sample_hash(*pad.sample);
    const auto body_bytes = add(kSampleHeaderBytes, sample_bytes);
    std::uint32_t sample_index = 0;
    while (sample_index < sample_count &&
           (samples[sample_index].digest != digest ||
            samples[sample_index].body_bytes != body_bytes)) {
      ++sample_index;
    }
    if (sample_index == sample_count) {
      pcm_bytes = add(pcm_bytes, sample_bytes);
      require(pcm_bytes <= limits.maximum_pcm_bytes, "pcm_limit",
              "runtime content exceeds the total unique decoded PCM allowance");
      encoded_bytes = add(encoded_bytes, add(40, body_bytes));
      require(encoded_bytes <= limits.maximum_encoded_bytes, "encoded_limit",
              "runtime content samples exceed the encoded byte allowance");
      samples[sample_count++] = {pad.sample.get(), digest, body_bytes};
    }
    pad_sample[index] = sample_index;
    by_slot[slot] = &pad;
  }
  for (std::size_t index = 0; index < snapshot.events.size(); ++index) {
    const auto& event = snapshot.events[index];
    validate_event(event, snapshot.loop_length_ticks);
    require(index == 0 || event_key(snapshot.events[index - 1]) < event_key(event),
            "event_order", "runtime content events are duplicated or not canonically ordered");
    const auto* pad = by_slot[slot_number(event.slot)];
    require(pad != nullptr, "reference", "runtime content event references an absent Pad");
    require(event.sample != nullptr &&
                (event.sample == pad->sample ||
                 (event.sample->sample_rate == pad->sample->sample_rate &&
                  event.sample->channels == pad->sample->channels &&
                  event.sample->interleaved == pad->sample->interleaved)),
            "reference", "runtime content event PCM disagrees with its Pad");
  }

  std::vector<std::byte> bytes;
  bytes.reserve(size(encoded_bytes));
  append_text(bytes, kMagic);
  append(bytes, 1, 2); append(bytes, 0, 2); append(bytes, 0, 2); append(bytes, 0, 2);
  append(bytes, encoded_bytes, 8); append(bytes, kRequiredCapabilities, 8);
  append_text(bytes, snapshot.project_id.value());
  append_text(bytes, snapshot.pattern_id.value());
  append(bytes, snapshot.project_revision, 8);
  append(bytes, snapshot.bpm, 2); append(bytes, snapshot.bars, 1); append(bytes, 0, 1);
  append(bytes, snapshot.ppq, 4); append(bytes, snapshot.loop_length_ticks, 4);
  append(bytes, snapshot.pads.size(), 4); append(bytes, snapshot.events.size(), 4);
  append(bytes, sample_count, 4);
  for (std::size_t index = 0; index < snapshot.pads.size(); ++index) {
    const auto& pad = snapshot.pads[index];
    append(bytes, pad.slot.bank, 1); append(bytes, pad.slot.pad, 1);
    append(bytes, mode_number(pad.playback.trigger_mode), 1);
    append(bytes, pad.playback.muted ? 1 : 0, 1);
    append(bytes, pad_sample[index], 4);
    append(bytes, pad.playback.start_frame, 4); append(bytes, pad.playback.end_frame, 4);
    append(bytes, std::bit_cast<std::uint32_t>(pad.playback.linear_gain), 4);
  }
  for (const auto& event : snapshot.events) {
    append(bytes, event.slot.bank, 1); append(bytes, event.slot.pad, 1);
    append(bytes, event.velocity, 1); append(bytes, 0, 1);
    append(bytes, event.onset_tick, 4); append(bytes, event.duration_tick, 4);
  }
  for (std::uint32_t index = 0; index < sample_count; ++index) {
    const auto& sample = samples[index];
    append(bytes, sample.body_bytes, 8);
    for (const auto byte : sample.digest) {
      bytes.push_back(static_cast<std::byte>(byte));
    }
    for (const auto byte : sample_header(*sample.pcm)) {
      bytes.push_back(static_cast<std::byte>(byte));
    }
    for (const auto pcm : sample.pcm->interleaved) {
      append(bytes, static_cast<std::uint16_t>(pcm), 2);
    }
  }
  return {{hex(hash(bytes)), encoded_bytes}, std::move(bytes)};
}

struct ParsedPad {
  domain::PadSlotId slot{};
  std::uint32_t sample_index{};
  ResolvedPlayback playback{};
};

struct ParsedSample {
  Digest digest{};
  std::uint64_t body_bytes{};
  std::uint32_t frames{};
  std::uint16_t channels{};
  std::span<const std::byte> pcm;
};

std::shared_ptr<const RuntimeSnapshot> decode(
    std::span<const std::byte> bytes, const RuntimeContentIdentity& expected,
    const RuntimeContentLimits& limits) {
  require(bytes.size() <= limits.maximum_encoded_bytes, "encoded_limit",
          "runtime content input exceeds the encoded byte allowance");
  require(bytes.size() >= kHeaderBytes && bytes.size() == expected.byte_length,
          "length", "runtime content length differs from the complete identity");
  require(expected.sha256 == hex(hash(bytes)), "identity",
          "runtime content digest differs from the complete identity");
  Reader input(bytes);
  require(input.text(8) == kMagic, "magic", "runtime content magic is unsupported");
  const auto major = input.integer(2);
  const auto minor = input.integer(2);
  const auto patch = input.integer(2);
  require(major == 1 && minor == 0 && patch == 0, "version",
          "runtime content Contract version is unsupported");
  require(input.integer(2) == 0, "reserved", "runtime content reserved header is nonzero");
  require(input.integer(8) == bytes.size(), "length", "runtime content header length is false");
  require(input.integer(8) == kRequiredCapabilities, "capabilities",
          "runtime content required capabilities are unsupported or incomplete");
  RuntimeSnapshot snapshot{
      foundation::ProjectId{input.text(36)},
      foundation::PatternId{input.text(36)},
      0, 0, 0, 0, 0, {}, {}};
  snapshot.project_revision = input.integer(8);
  snapshot.bpm = static_cast<std::uint16_t>(input.integer(2));
  snapshot.bars = static_cast<std::uint8_t>(input.integer(1));
  require(input.integer(1) == 0, "reserved", "runtime content timing reserved field is nonzero");
  snapshot.ppq = static_cast<std::uint32_t>(input.integer(4));
  snapshot.loop_length_ticks = static_cast<std::uint32_t>(input.integer(4));
  validate_pattern(snapshot);
  const auto pad_count = static_cast<std::uint32_t>(input.integer(4));
  const auto event_count = static_cast<std::uint32_t>(input.integer(4));
  const auto sample_count = static_cast<std::uint32_t>(input.integer(4));
  validate_counts(pad_count, event_count, sample_count, limits);
  // Slice both tables before using their counts; no count-driven allocation.
  Reader pad_input(input.take(multiply(pad_count, kPadBytes)));
  const auto event_bytes = input.take(multiply(event_count, kEventBytes));
  std::array<ParsedPad, 64> pads{};
  std::array<int, 64> by_slot{};
  by_slot.fill(-1);
  std::array<bool, 64> used_samples{};
  std::uint32_t next_sample = 0;
  std::size_t prior_slot = 0;
  for (std::uint32_t index = 0; index < pad_count; ++index) {
    auto& pad = pads[index];
    pad.slot = {static_cast<std::uint8_t>(pad_input.integer(1)),
                static_cast<std::uint8_t>(pad_input.integer(1))};
    const auto slot = slot_number(pad.slot);
    require(index == 0 || slot > prior_slot, "pad_order",
            "runtime content Pads are duplicated or not canonically ordered");
    prior_slot = slot;
    pad.playback.trigger_mode = read_mode(pad_input.integer(1));
    const auto muted = pad_input.integer(1);
    require(muted <= 1, "playback", "runtime content mute value is invalid");
    pad.playback.muted = muted != 0;
    pad.sample_index = static_cast<std::uint32_t>(pad_input.integer(4));
    require(pad.sample_index < sample_count, "reference",
            "runtime content Pad references an absent sample");
    if (!used_samples[pad.sample_index]) {
      require(pad.sample_index == next_sample, "sample_order",
              "runtime content samples are not ordered by first Pad use");
      used_samples[pad.sample_index] = true;
      ++next_sample;
    }
    pad.playback.start_frame = static_cast<std::uint32_t>(pad_input.integer(4));
    pad.playback.end_frame = static_cast<std::uint32_t>(pad_input.integer(4));
    pad.playback.linear_gain = std::bit_cast<float>(
        static_cast<std::uint32_t>(pad_input.integer(4)));
    by_slot[slot] = static_cast<int>(index);
  }
  require(next_sample == sample_count, "reference", "runtime content has unused samples");

  Reader events(event_bytes);
  ResolvedEvent previous{};
  for (std::uint32_t index = 0; index < event_count; ++index) {
    ResolvedEvent event{};
    event.slot = {static_cast<std::uint8_t>(events.integer(1)),
                  static_cast<std::uint8_t>(events.integer(1))};
    event.velocity = static_cast<std::uint8_t>(events.integer(1));
    require(events.integer(1) == 0, "reserved", "runtime content event reserved field is nonzero");
    event.onset_tick = static_cast<std::uint32_t>(events.integer(4));
    event.duration_tick = static_cast<std::uint32_t>(events.integer(4));
    validate_event(event, snapshot.loop_length_ticks);
    require(index == 0 || event_key(previous) < event_key(event), "event_order",
            "runtime content events are duplicated or not canonically ordered");
    require(by_slot[slot_number(event.slot)] >= 0, "reference",
            "runtime content event references an absent Pad");
    previous = event;
  }

  std::array<ParsedSample, 64> samples{};
  std::uint64_t total_pcm = 0;
  for (std::uint32_t index = 0; index < sample_count; ++index) {
    auto& sample = samples[index];
    sample.body_bytes = input.integer(8);
    const auto digest_bytes = input.take(32);
    std::transform(digest_bytes.begin(), digest_bytes.end(), sample.digest.begin(),
                   [](std::byte byte) { return std::to_integer<unsigned char>(byte); });
    const auto body_bytes = input.take(sample.body_bytes);
    Reader body(body_bytes);
    const auto rate = body.integer(4);
    sample.channels = static_cast<std::uint16_t>(body.integer(2));
    require(body.integer(2) == 0, "reserved", "runtime content PCM reserved field is nonzero");
    sample.frames = static_cast<std::uint32_t>(body.integer(4));
    require(rate == 48'000 && (sample.channels == 1 || sample.channels == 2) &&
                sample.frames > 0,
            "pcm", "runtime content requires complete 48 kHz mono/stereo PCM16 frames");
    require(sample.frames <= limits.maximum_sample_frames, "frame_limit",
            "runtime content exceeds the sample frame allowance");
    const auto pcm_bytes = multiply(sample.frames, multiply(sample.channels, 2));
    require(sample.body_bytes == add(kSampleHeaderBytes, pcm_bytes), "length",
            "runtime content PCM body length disagrees with its shape");
    total_pcm = add(total_pcm, pcm_bytes);
    require(total_pcm <= limits.maximum_pcm_bytes, "pcm_limit",
            "runtime content exceeds the total unique decoded PCM allowance");
    require(hash(body_bytes) == sample.digest, "sample_identity",
            "runtime content sample body digest is false");
    for (std::uint32_t prior = 0; prior < index; ++prior) {
      require(samples[prior].digest != sample.digest ||
                  samples[prior].body_bytes != sample.body_bytes,
              "duplicate_sample", "runtime content sample table is not deduplicated");
    }
    sample.pcm = body.take(pcm_bytes);
  }
  require(input.empty(), "length", "runtime content has trailing bytes");
  for (std::uint32_t index = 0; index < pad_count; ++index) {
    validate_playback(pads[index].playback, samples[pads[index].sample_index].frames);
  }

  // No PCM allocation occurs until the complete candidate passed all checks.
  std::array<std::shared_ptr<const PcmSample>, 64> owners{};
  for (std::uint32_t index = 0; index < sample_count; ++index) {
    const auto& sample = samples[index];
    std::vector<std::int16_t> pcm;
    pcm.reserve(sample.pcm.size() / 2);
    Reader words(sample.pcm);
    while (!words.empty()) {
      pcm.push_back(std::bit_cast<std::int16_t>(
          static_cast<std::uint16_t>(words.integer(2))));
    }
    owners[index] = std::make_shared<const PcmSample>(
        PcmSample{48'000, sample.channels, std::move(pcm)});
  }
  snapshot.pads.reserve(pad_count);
  for (std::uint32_t index = 0; index < pad_count; ++index) {
    const auto& pad = pads[index];
    const auto& sample = samples[pad.sample_index];
    snapshot.pads.push_back({
        pad.slot, {hex(sample.digest), std::string(kRuntimePcmMediaType), sample.body_bytes},
        owners[pad.sample_index], pad.playback});
  }
  snapshot.events.reserve(event_count);
  Reader decoded_events(event_bytes);
  for (std::uint32_t index = 0; index < event_count; ++index) {
    ResolvedEvent event{};
    event.slot = {static_cast<std::uint8_t>(decoded_events.integer(1)),
                  static_cast<std::uint8_t>(decoded_events.integer(1))};
    event.velocity = static_cast<std::uint8_t>(decoded_events.integer(1));
    (void)decoded_events.integer(1);
    event.onset_tick = static_cast<std::uint32_t>(decoded_events.integer(4));
    event.duration_tick = static_cast<std::uint32_t>(decoded_events.integer(4));
    event.sample = snapshot.pads[static_cast<std::size_t>(by_slot[slot_number(event.slot)])].sample;
    snapshot.events.push_back(std::move(event));
  }
  return std::make_shared<const RuntimeSnapshot>(std::move(snapshot));
}

}  // namespace

Result<EncodedRuntimeContent> encode_runtime_content(
    const RuntimeSnapshot& snapshot, const RuntimeContentLimits& limits) {
  try {
    return Result<EncodedRuntimeContent>::success(encode(snapshot, limits));
  } catch (InvalidContent error) {
    return Result<EncodedRuntimeContent>::failure(content_error(error));
  } catch (...) {
    return Result<EncodedRuntimeContent>::failure(construction_error());
  }
}

Result<std::shared_ptr<const RuntimeSnapshot>> decode_runtime_content(
    std::span<const std::byte> bytes, const RuntimeContentIdentity& expected,
    const RuntimeContentLimits& limits) {
  try {
    return Result<std::shared_ptr<const RuntimeSnapshot>>::success(
        decode(bytes, expected, limits));
  } catch (InvalidContent error) {
    return Result<std::shared_ptr<const RuntimeSnapshot>>::failure(content_error(error));
  } catch (...) {
    return Result<std::shared_ptr<const RuntimeSnapshot>>::failure(construction_error());
  }
}

}  // namespace lmdj::cooker
