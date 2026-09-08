#include <lmdj/cooker/runtime_content.hpp>

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <new>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <picosha2.h>

#if __has_include(<lmdj/project_io/project_store.hpp>) || \
    __has_include(<lmdj/provider/registry.hpp>)
#error "why: runtime content consumer sees Project IO or Provider SDK; remedy: keep the codec on the narrow Cooker dependency closure"
#endif

#include "tests/core/support/test.hpp"

namespace {

using namespace lmdj;
using cooker::EncodedRuntimeContent;
using cooker::PcmSample;
using cooker::RuntimeContentIdentity;
using cooker::RuntimeContentLimits;
using cooker::RuntimeSnapshot;
using Bytes = std::vector<std::byte>;
constexpr RuntimeContentLimits kLimits{1'048'576, 262'144, 65'536, 64, 1024};
thread_local std::size_t fail_allocation_at = 0;
thread_local std::size_t rejected_allocations = 0;

void* allocate(std::size_t count) {
  if (fail_allocation_at != 0 && count >= fail_allocation_at) {
    ++rejected_allocations;
    throw std::bad_alloc{};
  }
  if (auto* memory = std::malloc(count == 0 ? 1 : count)) {
    return memory;
  }
  throw std::bad_alloc{};
}

RuntimeSnapshot fixture() {
  const auto sample = std::make_shared<const lmdj::cooker::PcmSample>(
      lmdj::cooker::PcmSample{48'000, 1, {-32'768, -1, 0, 32'767}});
  return RuntimeSnapshot{
      lmdj::foundation::ProjectId{"00000000-0000-4000-8000-000000000001"},
      lmdj::foundation::PatternId{"00000000-0000-4000-8000-000000000010"},
      7, 120, 1, 960, 3840,
      {{{0, 1}, {}, sample, {0, 4, lmdj::domain::TriggerMode::gate, 1.0F, false}},
       {{2, 3}, {}, sample,
        {1, 4, lmdj::domain::TriggerMode::loop_toggle, 0.5F, true}}},
      {{{0, 1}, 120, 240, 100, sample}},
  };
}

EncodedRuntimeContent encode(const RuntimeSnapshot& snapshot) {
  auto encoded = cooker::encode_runtime_content(snapshot, kLimits);
  test::check(encoded.has_value(), encoded.has_value() ? "encoded" : encoded.error().message);
  return std::move(encoded.value());
}

RuntimeContentIdentity identity(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* first = reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(first, first + bytes.size());
  }
  hasher.finish();
  return {picosha2::get_hash_hex_string(hasher), bytes.size()};
}

Bytes fixed_bytes() {
  std::ifstream input(std::string{LMDJ_SOURCE_DIR} +
                      "/tests/fixtures/contracts/runtime-content-v1.hex");
  LMDJ_CHECK(input.is_open());
  std::string token;
  Bytes bytes;
  while (input >> token) {
    LMDJ_CHECK(token.size() % 2 == 0);
    for (std::size_t index = 0; index < token.size(); index += 2) {
      bytes.push_back(static_cast<std::byte>(std::stoul(token.substr(index, 2), nullptr, 16)));
    }
  }
  LMDJ_CHECK(bytes.size() == 248);
  return bytes;
}

void write_integer(Bytes& bytes, std::size_t offset, std::uint64_t value,
                   std::size_t width) {
  for (std::size_t index = 0; index < width; ++index) {
    bytes.at(offset + index) = static_cast<std::byte>((value >> (index * 8)) & 255U);
  }
}

void expect_decode_error(const Bytes& bytes, std::string_view condition,
                         const RuntimeContentLimits& limits = kLimits) {
  const auto decoded = cooker::decode_runtime_content(bytes, identity(bytes), limits);
  LMDJ_CHECK(!decoded.has_value());
  LMDJ_CHECK(decoded.error().code == foundation::ErrorCode::invalid_argument);
  test::check(decoded.error().details.at("runtime_content_condition") == condition,
              std::string{"expected condition "} + std::string{condition} +
                  ", got " + decoded.error().message);
  LMDJ_CHECK(decoded.error().message.find("why:") != std::string::npos);
  LMDJ_CHECK(decoded.error().message.find("remedy:") != std::string::npos);
}

void expect_encode_error(const RuntimeSnapshot& snapshot,
                         std::string_view condition,
                         const RuntimeContentLimits& limits = kLimits) {
  const auto encoded = cooker::encode_runtime_content(snapshot, limits);
  LMDJ_CHECK(!encoded.has_value());
  test::check(encoded.error().details.at("runtime_content_condition") == condition,
              std::string{"expected condition "} + std::string{condition} +
                  ", got " + encoded.error().message);
}

void canonical_vector_and_owned_round_trip() {
  const auto snapshot = fixture();
  const auto encoded = cooker::encode_runtime_content(snapshot, kLimits);
  LMDJ_CHECK(encoded.has_value());
  LMDJ_CHECK(encoded.value().identity.byte_length == 248);
  LMDJ_CHECK(encoded.value().bytes == fixed_bytes());
  LMDJ_CHECK(encoded.value().identity.sha256 ==
             "5e441b59ea4a75e3a1a91f0ea10cb8e893a8b542f5923545e1d89596d8e65705");
  const auto decoded = lmdj::cooker::decode_runtime_content(
      encoded.value().bytes, encoded.value().identity, kLimits);
  LMDJ_CHECK(decoded.has_value());
  LMDJ_CHECK(decoded.value()->project_id == snapshot.project_id);
  LMDJ_CHECK(decoded.value()->pattern_id == snapshot.pattern_id);
  LMDJ_CHECK(decoded.value()->project_revision == 7);
  LMDJ_CHECK(decoded.value()->bpm == 120 && decoded.value()->bars == 1);
  LMDJ_CHECK(decoded.value()->ppq == 960 && decoded.value()->loop_length_ticks == 3840);
  LMDJ_CHECK(decoded.value()->pads.size() == 2);
  LMDJ_CHECK(decoded.value()->pads.at(0).sample ==
             decoded.value()->pads.at(1).sample);
  LMDJ_CHECK(decoded.value()->events.at(0).sample ==
             decoded.value()->pads.at(0).sample);
  LMDJ_CHECK(decoded.value()->pads.at(0).sample->interleaved ==
             snapshot.pads.at(0).sample->interleaved);
  LMDJ_CHECK(decoded.value()->pads.at(1).playback.start_frame == 1);
  LMDJ_CHECK(decoded.value()->pads.at(1).playback.end_frame == 4);
  LMDJ_CHECK(decoded.value()->pads.at(1).playback.linear_gain == 0.5F);
  LMDJ_CHECK(decoded.value()->pads.at(1).playback.muted);
  LMDJ_CHECK(decoded.value()->pads.at(1).playback.trigger_mode ==
             domain::TriggerMode::loop_toggle);
  const auto& event = decoded.value()->events.at(0);
  LMDJ_CHECK((event.slot == domain::PadSlotId{0, 1}));
  LMDJ_CHECK(event.onset_tick == 120 && event.duration_tick == 240 && event.velocity == 100);
  const auto& artifact = decoded.value()->pads.at(0).artifact;
  LMDJ_CHECK(artifact.sha256 ==
             "6efad44c91c9cb32ec10f5fc58f6c442ea871bf8f31e7212fbd30a0cf0dfe79d");
  LMDJ_CHECK(artifact.byte_length == 20);
  LMDJ_CHECK(artifact.media_type == cooker::kRuntimePcmMediaType);
  LMDJ_CHECK(encode(*decoded.value()).bytes == encoded.value().bytes);
  LMDJ_CHECK(encode(snapshot).identity == encoded.value().identity);
  auto input = encoded.value().bytes;
  const auto owned = cooker::decode_runtime_content(input, identity(input), kLimits);
  input.assign(input.size(), std::byte{0});
  LMDJ_CHECK(owned.value()->pads.at(0).sample->interleaved ==
             snapshot.pads.at(0).sample->interleaved);
}

void sample_interpretation_and_canonical_order() {
  auto snapshot = fixture();
  snapshot.pads.at(1).sample = std::make_shared<const PcmSample>(*snapshot.pads.at(0).sample);
  snapshot.events.at(0).sample = std::make_shared<const PcmSample>(*snapshot.pads.at(0).sample);
  LMDJ_CHECK(encode(snapshot).bytes == fixed_bytes());

  auto stereo = std::make_shared<PcmSample>(*snapshot.pads.at(1).sample);
  stereo->channels = 2;
  snapshot.pads.at(1).sample = stereo;
  snapshot.pads.at(1).playback.end_frame = 2;
  auto encoded = encode(snapshot);
  const auto decoded = cooker::decode_runtime_content(encoded.bytes, encoded.identity, kLimits);
  LMDJ_CHECK(decoded.has_value());
  LMDJ_CHECK(decoded.value()->pads.at(1).sample->channels == 2);
  LMDJ_CHECK(decoded.value()->pads.at(0).sample != decoded.value()->pads.at(1).sample);
  LMDJ_CHECK(decoded.value()->pads.at(0).artifact.sha256 != decoded.value()->pads.at(1).artifact.sha256);
  LMDJ_CHECK(decoded.value()->pads.at(1).sample->interleaved == stereo->interleaved);
  LMDJ_CHECK(encode(*decoded.value()).bytes == encoded.bytes);

  for (const auto mode : {domain::TriggerMode::one_shot, domain::TriggerMode::gate,
                          domain::TriggerMode::loop_gate, domain::TriggerMode::loop_toggle}) {
    snapshot.pads.at(0).playback.trigger_mode = mode;
    encoded = encode(snapshot);
    const auto read = cooker::decode_runtime_content(encoded.bytes, encoded.identity, kLimits);
    LMDJ_CHECK(read.value()->pads.at(0).playback.trigger_mode == mode);
  }
  snapshot.project_revision = std::numeric_limits<std::uint64_t>::max();
  snapshot.events.push_back({{2, 3}, 1440, 240, 127, stereo});
  for (const auto bars : {1, 2, 4, 8}) {
    snapshot.bars = static_cast<std::uint8_t>(bars);
    snapshot.bpm = bars == 1 ? 40 : 240;
    snapshot.loop_length_ticks = static_cast<std::uint32_t>(bars) * 3840;
    encoded = encode(snapshot);
    const auto read = cooker::decode_runtime_content(encoded.bytes, encoded.identity, kLimits);
    LMDJ_CHECK(read.value()->events.size() == 2);
    LMDJ_CHECK(read.value()->project_revision == snapshot.project_revision);
    LMDJ_CHECK(encode(*read.value()).bytes == encoded.bytes);
  }
  snapshot.pads.clear();
  snapshot.events.clear();
  const RuntimeContentLimits empty_limits{136, 0, 0, 0, 0};
  const auto empty = cooker::encode_runtime_content(snapshot, empty_limits);
  LMDJ_CHECK(empty.has_value());
  const auto read_empty = cooker::decode_runtime_content(empty.value().bytes,
                                                        empty.value().identity, empty_limits);
  LMDJ_CHECK(read_empty.has_value());
  LMDJ_CHECK(read_empty.value()->pads.empty() && read_empty.value()->events.empty());
}

void malformed_wire_fields_fail_individually() {
  struct Case { std::size_t offset; std::uint64_t value; std::size_t width; const char* condition; };
  for (const auto& item : std::array{
           Case{0, 0, 1, "magic"}, Case{8, 2, 2, "version"},
           Case{10, 1, 2, "version"}, Case{12, 1, 2, "version"},
           Case{14, 1, 2, "reserved"}, Case{16, 249, 8, "length"},
           Case{24, 15, 8, "capabilities"}, Case{24, 0, 8, "capabilities"},
           Case{32, 'z', 1, "source"}, Case{68, 'z', 1, "source"},
           Case{112, 39, 2, "timing"}, Case{112, 241, 2, "timing"},
           Case{114, 3, 1, "timing"}, Case{115, 1, 1, "reserved"},
           Case{116, 480, 4, "timing"}, Case{120, 1, 4, "timing"},
           Case{124, 65, 4, "counts"}, Case{132, 3, 4, "counts"},
           Case{128, 1025, 4, "event_limit"}, Case{136, 4, 1, "slot"},
           Case{137, 16, 1, "slot"}, Case{138, 4, 1, "playback"},
           Case{139, 2, 1, "playback"}, Case{140, 1, 4, "reference"},
           Case{144, 4, 4, "playback"}, Case{148, 5, 4, "playback"},
           Case{152, 0x7fc00000U, 4, "playback"},
           Case{152, 0x7f800000U, 4, "playback"},
           Case{152, 0xbf800000U, 4, "playback"},
           Case{152, 0x80000000U, 4, "playback"},
           Case{152, 0x40400000U, 4, "playback"},
           Case{156, 0, 2, "pad_order"}, Case{176, 4, 1, "slot"},
           Case{177, 9, 1, "reference"}, Case{178, 0, 1, "event"},
           Case{178, 128, 1, "event"}, Case{179, 1, 1, "reserved"},
           Case{180, 3840, 4, "event"}, Case{184, 0, 4, "event"},
           Case{184, 3840, 4, "event"}, Case{188, 19, 8, "length"},
           Case{188, std::numeric_limits<std::uint64_t>::max(), 8, "length"},
           Case{196, 0, 1, "sample_identity"}, Case{228, 44100, 4, "pcm"},
           Case{232, 0, 2, "pcm"}, Case{232, 3, 2, "pcm"},
           Case{234, 1, 2, "reserved"}, Case{236, 0, 4, "pcm"},
           Case{236, 65'537, 4, "frame_limit"}, Case{247, 0, 1, "sample_identity"}}) {
    auto bytes = fixed_bytes();
    write_integer(bytes, item.offset, item.value, item.width);
    expect_decode_error(bytes, item.condition);
  }
  auto bytes = fixed_bytes();
  bytes.push_back(std::byte{0});
  write_integer(bytes, 16, bytes.size(), 8);
  expect_decode_error(bytes, "length");
  for (std::size_t length = 0; length < 248; ++length) {
    bytes = fixed_bytes();
    bytes.resize(length);
    if (length >= 24) write_integer(bytes, 16, length, 8);
    expect_decode_error(bytes, "length");
  }
  bytes = fixed_bytes();
  auto wrong = identity(bytes);
  wrong.sha256.front() = '0';
  const auto bad_digest = cooker::decode_runtime_content(bytes, wrong, kLimits);
  LMDJ_CHECK(!bad_digest.has_value());
  LMDJ_CHECK(bad_digest.error().details.at("runtime_content_condition") == "identity");
  wrong = identity(bytes);
  ++wrong.byte_length;
  const auto bad_length = cooker::decode_runtime_content(bytes, wrong, kLimits);
  LMDJ_CHECK(!bad_length.has_value());
  LMDJ_CHECK(bad_length.error().details.at("runtime_content_condition") == "length");
}

void encoder_rejects_invalid_sources() {
  const auto rejected = [](auto mutation, std::string_view condition) {
    auto snapshot = fixture();
    mutation(snapshot);
    expect_encode_error(snapshot, condition);
  };
  rejected([](auto& s) { s.project_id = foundation::ProjectId{"invalid"}; }, "source");
  rejected([](auto& s) { s.pattern_id = foundation::PatternId{"invalid"}; }, "source");
  rejected([](auto& s) { s.bpm = 0; }, "timing");
  rejected([](auto& s) { s.bars = 3; }, "timing");
  rejected([](auto& s) { s.ppq = 480; }, "timing");
  rejected([](auto& s) { s.loop_length_ticks = 0; }, "timing");
  rejected([](auto& s) { std::swap(s.pads[0], s.pads[1]); }, "pad_order");
  rejected([](auto& s) { s.pads[1].slot = s.pads[0].slot; }, "pad_order");
  rejected([](auto& s) { s.pads[0].slot.bank = 4; }, "slot");
  rejected([](auto& s) { s.pads[0].sample.reset(); }, "pcm");
  rejected([](auto& s) { s.pads[0].playback.start_frame = 4; }, "playback");
  rejected([](auto& s) { s.pads[0].playback.end_frame = 5; }, "playback");
  rejected([](auto& s) {
    s.pads[0].playback.trigger_mode = static_cast<domain::TriggerMode>(255);
  }, "playback");
  for (const auto gain : {-1.0F, -0.0F, 3.0F,
                          std::numeric_limits<float>::infinity(),
                          std::numeric_limits<float>::quiet_NaN()}) {
    rejected([gain](auto& s) { s.pads[0].playback.linear_gain = gain; }, "playback");
  }
  const auto rejected_pcm = [&](auto mutation) {
    rejected([&](auto& s) {
      auto sample = std::make_shared<PcmSample>(*s.pads[0].sample);
      mutation(*sample);
      s.pads[0].sample = sample;
    }, "pcm");
  };
  rejected_pcm([](auto& s) { s.sample_rate = 44100; });
  rejected_pcm([](auto& s) { s.channels = 0; });
  rejected_pcm([](auto& s) { s.channels = 3; });
  rejected_pcm([](auto& s) { s.interleaved.clear(); });
  rejected_pcm([](auto& s) { s.channels = 2; s.interleaved.pop_back(); });
  rejected([](auto& s) { s.events[0].velocity = 0; }, "event");
  rejected([](auto& s) { s.events[0].velocity = 128; }, "event");
  rejected([](auto& s) { s.events[0].onset_tick = 3840; }, "event");
  rejected([](auto& s) { s.events[0].duration_tick = 0; }, "event");
  rejected([](auto& s) { s.events[0].duration_tick = 3840; }, "event");
  rejected([](auto& s) { s.events[0].slot = {1, 0}; }, "reference");
  rejected([](auto& s) { s.events[0].sample.reset(); }, "reference");
  for (const auto field : {0, 1, 2}) {
    rejected([field](auto& s) {
      auto sample = std::make_shared<PcmSample>(*s.events[0].sample);
      if (field == 0) sample->sample_rate = 44100;
      if (field == 1) sample->channels = 2;
      if (field == 2) sample->interleaved[0] = 1;
      s.events[0].sample = sample;
    }, "reference");
  }
  rejected([](auto& s) { s.events.push_back(s.events[0]); }, "event_order");
  auto many_pads = fixture();
  while (many_pads.pads.size() <= 64) many_pads.pads.push_back(many_pads.pads[0]);
  expect_encode_error(many_pads, "counts");
}

void budgets_are_exact_and_arithmetic_does_not_wrap() {
  const auto snapshot = fixture();
  const auto bytes = fixed_bytes();
  const RuntimeContentLimits exact{248, 8, 4, 2, 1};
  LMDJ_CHECK(cooker::encode_runtime_content(snapshot, exact).has_value());
  LMDJ_CHECK(cooker::decode_runtime_content(bytes, identity(bytes), exact).has_value());
  for (const auto field : {0, 1, 2, 3, 4}) {
    auto limit = exact;
    const char* condition = "";
    if (field == 0) { --limit.maximum_encoded_bytes; condition = "encoded_limit"; }
    if (field == 1) { --limit.maximum_pcm_bytes; condition = "pcm_limit"; }
    if (field == 2) { --limit.maximum_sample_frames; condition = "frame_limit"; }
    if (field == 3) { --limit.maximum_pads; condition = "pad_limit"; }
    if (field == 4) { --limit.maximum_events; condition = "event_limit"; }
    expect_encode_error(snapshot, condition, limit);
    expect_decode_error(bytes, condition, limit);
  }
  auto limit = exact;
  limit.maximum_encoded_bytes = 135;
  expect_encode_error(snapshot, "encoded_limit", limit);
  LMDJ_CHECK(!cooker::encode_runtime_content(snapshot, RuntimeContentLimits{}).has_value());
  expect_decode_error(bytes, "encoded_limit", RuntimeContentLimits{});

  auto two_samples = fixture();
  auto second = std::make_shared<PcmSample>(*two_samples.pads[1].sample);
  second->interleaved[1] = 8;
  two_samples.pads[1].sample = second;
  const auto two = encode(two_samples);
  limit = kLimits;
  limit.maximum_pcm_bytes = 8;  // Each sample fits, their unique sum does not.
  expect_encode_error(two_samples, "pcm_limit", limit);
  expect_decode_error(two.bytes, "pcm_limit", limit);

  auto bad = bytes;
  limit = kLimits;
  limit.maximum_sample_frames = std::numeric_limits<std::uint32_t>::max();
  limit.maximum_pcm_bytes = std::numeric_limits<std::uint64_t>::max();
  write_integer(bad, 232, 2, 2);
  // Narrow 32-bit multiplication would turn frames * channels * 2 into 8,
  // incorrectly matching the retained body's eight PCM bytes.
  write_integer(bad, 236, 0x40000002U, 4);
  expect_decode_error(bad, "length", limit);
  bad = bytes;
  limit.maximum_events = std::numeric_limits<std::uint32_t>::max();
  write_integer(bad, 128, std::numeric_limits<std::uint32_t>::max(), 4);
  expect_decode_error(bad, "length", limit);
}

void noncanonical_sample_and_event_tables_are_rejected() {
  auto snapshot = fixture();
  auto second = std::make_shared<PcmSample>(*snapshot.pads[1].sample);
  second->interleaved[1] = 8;
  snapshot.pads[1].sample = second;
  const auto two_samples = encode(snapshot);
  LMDJ_CHECK(two_samples.bytes.size() == 308);
  auto bad = two_samples.bytes;
  write_integer(bad, 140, 1, 4);
  expect_decode_error(bad, "sample_order");
  bad = two_samples.bytes;
  write_integer(bad, 160, 0, 4);
  expect_decode_error(bad, "reference");
  bad = two_samples.bytes;
  std::copy_n(two_samples.bytes.begin() + 188, 60, bad.begin() + 248);
  expect_decode_error(bad, "duplicate_sample");

  snapshot = fixture();
  snapshot.events.push_back({{0, 1}, 480, 240, 127, snapshot.pads[0].sample});
  const auto two_events = encode(snapshot);
  bad = two_events.bytes;
  write_integer(bad, 192, 120, 4);
  expect_decode_error(bad, "event_order");
  write_integer(bad, 192, 119, 4);
  expect_decode_error(bad, "event_order");
}

template <typename Operation>
auto without_large_allocations(Operation operation) {
  struct Guard {
    Guard() { rejected_allocations = 0; fail_allocation_at = 50'000; }
    ~Guard() { fail_allocation_at = 0; }
  } guard;
  return operation();
}

void complete_validation_precedes_pcm_allocation() {
  auto snapshot = fixture();
  snapshot.pads[0].sample = std::make_shared<const PcmSample>(
      PcmSample{48'000, 1, std::vector<std::int16_t>(30'000, 123)});
  snapshot.pads[0].playback.end_frame = 30'000;
  snapshot.events[0].sample = snapshot.pads[0].sample;
  const auto encoded = encode(snapshot);
  auto corrupt = encoded.bytes;
  corrupt.back() ^= std::byte{1};
  const auto corrupt_identity = identity(corrupt);
  const auto refused = without_large_allocations([&] {
    return cooker::decode_runtime_content(corrupt, corrupt_identity, kLimits);
  });
  LMDJ_CHECK(!refused.has_value());
  test::check(refused.error().details.contains("runtime_content_condition"),
              refused.error().message);
  LMDJ_CHECK(refused.error().details.at("runtime_content_condition") == "sample_identity");
  LMDJ_CHECK(rejected_allocations == 0);

  // Positive control: the valid candidate really reaches a large PCM allocation.
  const auto allocation_failure = without_large_allocations([&] {
    return cooker::decode_runtime_content(encoded.bytes, encoded.identity, kLimits);
  });
  LMDJ_CHECK(!allocation_failure.has_value());
  LMDJ_CHECK(allocation_failure.error().code == foundation::ErrorCode::internal_error);
  LMDJ_CHECK(rejected_allocations == 1);
  const auto encode_failure = without_large_allocations([&] {
    return cooker::encode_runtime_content(snapshot, kLimits);
  });
  LMDJ_CHECK(!encode_failure.has_value());
  LMDJ_CHECK(encode_failure.error().code == foundation::ErrorCode::internal_error);
  LMDJ_CHECK(rejected_allocations == 1);
  LMDJ_CHECK(cooker::decode_runtime_content(encoded.bytes, encoded.identity, kLimits).has_value());
}

}  // namespace

void* operator new(std::size_t count) { return allocate(count); }
void* operator new[](std::size_t count) { return allocate(count); }
void operator delete(void* pointer) noexcept { std::free(pointer); }
void operator delete[](void* pointer) noexcept { std::free(pointer); }
void operator delete(void* pointer, std::size_t) noexcept { std::free(pointer); }
void operator delete[](void* pointer, std::size_t) noexcept { std::free(pointer); }

int main(int argc, char** argv) {
  if (argc == 2 && std::string_view(argv[1]) == "--emit-fixture") {
    constexpr std::string_view digits = "0123456789abcdef";
    for (const auto byte : encode(fixture()).bytes) {
      const auto value = std::to_integer<unsigned int>(byte);
      std::cout << digits[value >> 4] << digits[value & 15];
    }
    std::cout << '\n';
    return 0;
  }
  LMDJ_CHECK(argc == 1);
  canonical_vector_and_owned_round_trip();
  sample_interpretation_and_canonical_order();
  malformed_wire_fields_fail_individually();
  encoder_rejects_invalid_sources();
  budgets_are_exact_and_arithmetic_does_not_wrap();
  noncanonical_sample_and_event_tables_are_rejected();
  complete_validation_precedes_pcm_allocation();
  return 0;
}
