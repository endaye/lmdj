#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/audio/runtime_preparation_limits.hpp>

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
using lmdj::audio::RuntimePreparationLimits;
using lmdj::audio::TriggerEvent;
using lmdj::cooker::PcmSample;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::ResolvedPad;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::PadSlotId;
using lmdj::domain::TriggerMode;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";

constexpr RuntimePreparationLimits kWebLimits{
    1'048'576,
    240'000,
    67'108'864,
    134'217'728,
};

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
              ResolvedPlayback{0, 5, TriggerMode::one_shot, 1.0F, false},
          },
          ResolvedPad{
              PadSlotId{3, 15},
              artifact('b', 8),
              pcm(48'000, 2, {32'767, -32'768, 16'384, 16'384}),
              ResolvedPlayback{0, 2, TriggerMode::one_shot, 1.0F, false},
          },
      },
      {},
  };
}

RuntimeSnapshot large_shared_snapshot(bool one_extra_frame) {
  auto shared = pcm(
      48'000,
      1,
      std::vector<std::int16_t>(262'144, 0));
  auto larger = one_extra_frame
                    ? pcm(
                          48'000,
                          1,
                          std::vector<std::int16_t>(262'145, 0))
                    : shared;
  std::vector<ResolvedPad> pads;
  pads.reserve(64);
  for (std::uint8_t slot = 0; slot < 64; ++slot) {
    pads.push_back(
        ResolvedPad{
            PadSlotId{
                static_cast<std::uint8_t>(slot / 16U),
                static_cast<std::uint8_t>(slot % 16U),
            },
            artifact('c', 1),
            one_extra_frame && slot == 63 ? larger : shared,
            ResolvedPlayback{
                0,
                static_cast<std::uint32_t>(
                    one_extra_frame && slot == 63 ? 262'145 : 262'144),
                TriggerMode::one_shot,
                1.0F,
                false,
            },
        });
  }
  return RuntimeSnapshot{
      ProjectId{kProjectId},
      8,
      120,
      1,
      std::move(pads),
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

void validates_resolved_playback_before_storing_fixed_values() {
  const std::array<float, 4> sample{0.25F, 0.5F, 0.75F, 1.0F};
  auto accepted = PreparedSampleBank::empty(ProjectId{kProjectId}, 9);
  LMDJ_CHECK(
      accepted
          .set_sample(
              0,
              sample,
              ResolvedPlayback{
                  1, 3, TriggerMode::loop_gate, 0.5F, false})
          .has_value());

  const std::array invalid{
      ResolvedPlayback{1, 1, TriggerMode::one_shot, 1.0F, false},
      ResolvedPlayback{0, 5, TriggerMode::one_shot, 1.0F, false},
      ResolvedPlayback{
          0,
          4,
          TriggerMode::one_shot,
          std::numeric_limits<float>::quiet_NaN(),
          false},
      ResolvedPlayback{0, 4, TriggerMode::one_shot, -0.5F, false},
      ResolvedPlayback{
          0,
          4,
          static_cast<TriggerMode>(255),
          1.0F,
          false},
  };
  for (std::uint8_t slot = 1; slot <= invalid.size(); ++slot) {
    auto bank = PreparedSampleBank::empty(ProjectId{kProjectId}, 9);
    const auto rejected = bank.set_sample(slot, sample, invalid.at(slot - 1));
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  }

  for (std::size_t mutation = 0; mutation < 3; ++mutation) {
    auto snapshot = valid_snapshot();
    if (mutation == 0) {
      snapshot.pads.at(0).playback.end_frame = 6;
    } else if (mutation == 1) {
      snapshot.pads.at(0).playback.start_frame = 5;
    } else {
      snapshot.pads.at(0).playback.linear_gain =
          std::numeric_limits<float>::infinity();
    }
    const auto rejected = PreparedSampleBank::from_snapshot(snapshot);
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_argument);
  }
}

void accepts_exact_web_limits_and_rejects_boundary_plus_one() {
  LMDJ_CHECK(kWebLimits.allows_artifact_bytes(1'048'576));
  LMDJ_CHECK(!kWebLimits.allows_artifact_bytes(1'048'577));
  LMDJ_CHECK(kWebLimits.allows_decoded_frames_per_pad(240'000));
  LMDJ_CHECK(!kWebLimits.allows_decoded_frames_per_pad(240'001));
  LMDJ_CHECK(kWebLimits.allows_prepared_bank_bytes(67'108'864));
  LMDJ_CHECK(!kWebLimits.allows_prepared_bank_bytes(67'108'865));
  LMDJ_CHECK(kWebLimits.allows_live_bank_bytes(134'217'728));
  LMDJ_CHECK(!kWebLimits.allows_live_bank_bytes(134'217'729));
  const auto live_boundary = lmdj::audio::checked_runtime_byte_sum(
      67'108'864, 67'108'864);
  const auto live_plus_one = lmdj::audio::checked_runtime_byte_sum(
      67'108'864, 67'108'865);
  LMDJ_CHECK(live_boundary.has_value());
  LMDJ_CHECK(live_plus_one.has_value());
  LMDJ_CHECK(kWebLimits.allows_live_bank_bytes(live_boundary.value()));
  LMDJ_CHECK(!kWebLimits.allows_live_bank_bytes(live_plus_one.value()));

  const auto largest_frame_count =
      std::numeric_limits<std::uint64_t>::max() / sizeof(float);
  const auto largest_pcm =
      lmdj::audio::checked_mono_float_bytes(largest_frame_count);
  LMDJ_CHECK(largest_pcm.has_value());
  LMDJ_CHECK(
      largest_pcm.value() == largest_frame_count * sizeof(float));
  LMDJ_CHECK(
      !lmdj::audio::checked_mono_float_bytes(largest_frame_count + 1U)
           .has_value());
  LMDJ_CHECK(
      !lmdj::audio::checked_runtime_byte_sum(
           std::numeric_limits<std::uint64_t>::max(), 1U)
           .has_value());
}

void bounded_preparation_rejects_before_allocation_and_retains_prior_bank() {
  auto prior = PreparedSampleBank::empty(ProjectId{kProjectId}, 6);
  const std::array<float, 1> prior_pcm{0.25F};
  LMDJ_CHECK(prior.set_sample(0, prior_pcm).has_value());
  RealtimeEngine engine;
  LMDJ_CHECK(engine.publish_sample_bank(std::move(prior)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  const auto check_prior = [&engine]() {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{9, 0, 127}) ==
               EnqueueResult::accepted);
    std::array<float, 1> left{};
    std::array<float, 1> right{};
    engine.render(left.data(), right.data(), 1);
    LMDJ_CHECK(left.at(0) == 0.25F);
    LMDJ_CHECK(right.at(0) == 0.25F);
  };

  const auto snapshot = valid_snapshot();
  const RuntimePreparationLimits exact{
      1'048'576,
      5,
      28,
      28,
  };
  const auto prepared = PreparedSampleBank::from_snapshot(snapshot, exact);
  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value().decoded_pcm_bytes() == 28);
  check_prior();

  struct Rejection {
    RuntimePreparationLimits limits;
    std::string_view resource;
    std::uint64_t observed;
    std::uint64_t limit;
  };
  const std::array rejections{
      Rejection{
          RuntimePreparationLimits{1'048'576, 4, 28, 28},
          "decoded_frames_per_pad",
          5,
          4,
      },
      Rejection{
          RuntimePreparationLimits{1'048'576, 5, 27, 28},
          "prepared_bank_bytes",
          28,
          27,
      },
      Rejection{
          RuntimePreparationLimits{1'048'576, 5, 28, 27},
          "live_bank_bytes",
          28,
          27,
      },
  };
  for (const auto& rejection : rejections) {
    const auto rejected =
        PreparedSampleBank::from_snapshot(snapshot, rejection.limits);
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(rejected.error().code == ErrorCode::cook_failed);
    LMDJ_CHECK(
        rejected.error().details.at("resource") == rejection.resource);
    LMDJ_CHECK(
        rejected.error().details.at("observed") == rejection.observed);
    LMDJ_CHECK(rejected.error().details.at("limit") == rejection.limit);
    check_prior();
  }

  const auto exact_large = large_shared_snapshot(false);
  const auto exact_large_rejected_by_later_live_limit =
      PreparedSampleBank::from_snapshot(
          exact_large,
          RuntimePreparationLimits{
              1'048'576,
              262'144,
              67'108'864,
              67'108'863,
          });
  LMDJ_CHECK(!exact_large_rejected_by_later_live_limit.has_value());
  LMDJ_CHECK(
      exact_large_rejected_by_later_live_limit.error().details.at(
          "resource") == "live_bank_bytes");
  LMDJ_CHECK(
      exact_large_rejected_by_later_live_limit.error().details.at(
          "observed") == 67'108'864);
  check_prior();

  const auto first_representable_overage = large_shared_snapshot(true);
  const auto large_rejected_before_float_allocation =
      PreparedSampleBank::from_snapshot(
          first_representable_overage,
          RuntimePreparationLimits{
              1'048'576,
              262'145,
              67'108'864,
              134'217'728,
          });
  LMDJ_CHECK(!large_rejected_before_float_allocation.has_value());
  LMDJ_CHECK(
      large_rejected_before_float_allocation.error().details.at(
          "resource") == "prepared_bank_bytes");
  LMDJ_CHECK(
      large_rejected_before_float_allocation.error().details.at(
          "observed") == 67'108'868);
  check_prior();
}

}  // namespace

int main() {
  prepares_all_snapshot_slots_and_metadata();
  renders_exact_mono_and_stereo_pcm16_conversion();
  rejects_invalid_snapshot_sample_shapes_before_publication();
  validates_control_thread_float_sample_builder();
  validates_resolved_playback_before_storing_fixed_values();
  accepts_exact_web_limits_and_rejects_boundary_plus_one();
  bounded_preparation_rejects_before_allocation_and_retains_prior_bank();
}
