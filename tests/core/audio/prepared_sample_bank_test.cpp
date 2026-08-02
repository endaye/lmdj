#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::audio::EnqueueResult;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::TriggerEvent;
using lmdj::cooker::PcmSample;
using lmdj::cooker::ResolvedPad;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::PadSlotId;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";

ArtifactRef artifact(char digit, std::uint64_t byte_length) {
  return ArtifactRef{std::string(64, digit), "audio/wav", byte_length};
}

std::shared_ptr<const PcmSample> pcm(std::uint32_t sample_rate,
                                     std::uint16_t channels,
                                     std::vector<std::int16_t> samples) {
  return std::make_shared<const PcmSample>(
      PcmSample{sample_rate, channels, std::move(samples)});
}

RuntimeSnapshot valid_snapshot() {
  return RuntimeSnapshot{
      ProjectId{kProjectId},
      7,
      120,
      1,
      {
          ResolvedPad{
              PadSlotId{0, 0},
              artifact('a', 10),
              pcm(48'000, 1, {-32'768, -16'384, 0, 16'384, 32'767}),
          },
          ResolvedPad{
              PadSlotId{3, 15},
              artifact('b', 8),
              pcm(48'000, 2, {32'767, -32'768, 16'384, 16'384}),
          },
      },
      {},
  };
}

void prepares_all_snapshot_slots_and_metadata() {
  const auto snapshot = valid_snapshot();

  const auto prepared = PreparedSampleBank::from_snapshot(snapshot);

  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value().project_id() == ProjectId{kProjectId});
  LMDJ_CHECK(prepared.value().project_revision() == 7);
  LMDJ_CHECK(prepared.value().sample_count() == 2);
  LMDJ_CHECK(prepared.value().availability_mask() ==
             ((std::uint64_t{1} << 0U) | (std::uint64_t{1} << 63U)));
}

void renders_exact_mono_and_stereo_pcm16_conversion() {
  auto prepared = PreparedSampleBank::from_snapshot(valid_snapshot());
  LMDJ_CHECK(prepared.has_value());
  RealtimeEngine engine;
  LMDJ_CHECK(engine.publish_sample_bank(std::move(prepared.value())) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  constexpr auto positive_half = 16'384.0F / 32'767.0F;
  const std::array<float, 5> expected_mono{
      -1.0F, -0.5F, 0.0F, positive_half, 1.0F};
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 5> left{};
  std::array<float, 5> right{};
  engine.render(left.data(), right.data(), 5);
  LMDJ_CHECK(left == expected_mono);
  LMDJ_CHECK(right == expected_mono);

  const std::array<float, 2> expected_stereo{0.0F, positive_half};
  LMDJ_CHECK(engine.enqueue(TriggerEvent{2, 63, 127}) ==
             EnqueueResult::accepted);
  engine.render(left.data(), right.data(), 2);
  for (std::size_t frame = 0; frame < expected_stereo.size(); ++frame) {
    LMDJ_CHECK(left.at(frame) == expected_stereo.at(frame));
    LMDJ_CHECK(right.at(frame) == expected_stereo.at(frame));
  }
}

void rejects_invalid_snapshot_sample_shapes_before_publication() {
  auto duplicate = valid_snapshot();
  duplicate.pads.push_back(duplicate.pads.front());
  auto wrong_rate = valid_snapshot();
  wrong_rate.pads.at(0).sample = pcm(44'100, 1, {1});
  auto wrong_channels = valid_snapshot();
  wrong_channels.pads.at(0).sample = pcm(48'000, 3, {1, 2, 3});
  auto empty = valid_snapshot();
  empty.pads.at(0).sample = pcm(48'000, 1, {});
  auto incomplete_stereo = valid_snapshot();
  incomplete_stereo.pads.at(1).sample = pcm(48'000, 2, {1, 2, 3});

  for (const auto* candidate : {
           &duplicate,
           &wrong_rate,
           &wrong_channels,
           &empty,
           &incomplete_stereo,
       }) {
    const auto rejected = PreparedSampleBank::from_snapshot(*candidate);
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  }
}

void validates_control_thread_float_sample_builder() {
  auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, 9);
  const std::array<float, 2> sample{0.25F, -0.5F};
  const std::array<float, 1> nan{std::numeric_limits<float>::quiet_NaN()};
  const std::span<const float> no_samples;

  LMDJ_CHECK(bank.set_sample(0, sample).has_value());
  LMDJ_CHECK(!bank.set_sample(0, sample).has_value());
  LMDJ_CHECK(!bank.set_sample(64, sample).has_value());
  LMDJ_CHECK(!bank.set_sample(1, no_samples).has_value());
  LMDJ_CHECK(!bank.set_sample(1, nan).has_value());
  for (std::uint8_t slot = 1; slot < 64; ++slot) {
    LMDJ_CHECK(bank.set_sample(slot, sample).has_value());
  }
  LMDJ_CHECK(bank.sample_count() == 64);
  LMDJ_CHECK(bank.availability_mask() ==
             std::numeric_limits<std::uint64_t>::max());
}

}  // namespace

int main() {
  prepares_all_snapshot_slots_and_metadata();
  renders_exact_mono_and_stereo_pcm16_conversion();
  rejects_invalid_snapshot_sample_shapes_before_publication();
  validates_control_thread_float_sample_builder();
}
