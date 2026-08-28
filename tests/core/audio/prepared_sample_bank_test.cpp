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
using lmdj::audio::PreparedPatternView;
using lmdj::audio::TransportAnchor;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RuntimePreparationLimits;
using lmdj::audio::TriggerEvent;
using lmdj::cooker::PcmSample;
using lmdj::cooker::ResolvedPlayback;
using lmdj::cooker::ResolvedPad;
using lmdj::cooker::RuntimeSnapshot;
using lmdj::domain::PadSlotId;
using lmdj::domain::PatternEvent;
using lmdj::domain::TriggerMode;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::ProjectId;

constexpr auto kProjectId = "00000000-0000-4000-8000-000000000001";

constexpr RuntimePreparationLimits kWebLimits{
    1'048'576,
    67'108'864,
    134'217'728,
    268'435'456,
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
      lmdj::foundation::PatternId{
          "30000000-0000-4000-8000-000000000001"},
      7,
      120,
      1,
      lmdj::domain::kPpq,
      lmdj::domain::kBarTicks4x4,
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

RuntimeSnapshot snapshot_with_frame_counts(
    const std::vector<std::pair<PadSlotId, std::uint32_t>>& specifications) {
  std::vector<ResolvedPad> pads;
  pads.reserve(specifications.size());
  for (const auto& [slot, frames] : specifications) {
    pads.push_back(ResolvedPad{
        slot,
        artifact('d', 1),
        pcm(
            48'000,
            1,
            std::vector<std::int16_t>(frames, 0)),
        ResolvedPlayback{
            0,
            frames,
            TriggerMode::one_shot,
            1.0F,
            false,
        },
    });
  }
  return RuntimeSnapshot{
      ProjectId{kProjectId},
      lmdj::foundation::PatternId{
          "30000000-0000-4000-8000-000000000001"},
      10,
      120,
      1,
      lmdj::domain::kPpq,
      lmdj::domain::kBarTicks4x4,
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
  constexpr float kRampScale =
      1.0F / static_cast<float>(lmdj::audio::kRealtimeRampFrames);
  const auto ramp_part = [](std::uint32_t frames) {
    return static_cast<float>(frames) * kRampScale;
  };
  auto prepared = PreparedSampleBank::from_snapshot(valid_snapshot());
  LMDJ_CHECK(prepared.has_value());
  RealtimeEngine engine;
  LMDJ_CHECK(engine.publish_sample_bank(std::move(prepared.value())) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  constexpr auto positive_half = 16'384.0F / 32'767.0F;
  // F6 ramp: each frame carries the attack ramp times the non-looping
  // boundary fade (the mono selection is 5 frames long, the stereo one 2).
  const std::array<float, 5> expected_mono{
      0.0F,
      -0.5F * (ramp_part(1) * ramp_part(4)),
      0.0F,
      positive_half * (ramp_part(3) * ramp_part(2)),
      1.0F * (ramp_part(4) * ramp_part(1))};
  LMDJ_CHECK(engine.enqueue(TriggerEvent{1, 0, 127}) ==
             EnqueueResult::accepted);
  std::array<float, 5> left{};
  std::array<float, 5> right{};
  engine.render(left.data(), right.data(), 5);
  LMDJ_CHECK(left == expected_mono);
  LMDJ_CHECK(right == expected_mono);

  const std::array<float, 2> expected_stereo{
      0.0F, positive_half * (ramp_part(1) * ramp_part(1))};
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
  LMDJ_CHECK(kWebLimits.allows_user_bank_bytes(67'108'864));
  LMDJ_CHECK(!kWebLimits.allows_user_bank_bytes(67'108'865));
  LMDJ_CHECK(kWebLimits.allows_generation_bytes(134'217'728));
  LMDJ_CHECK(!kWebLimits.allows_generation_bytes(134'217'729));
  LMDJ_CHECK(kWebLimits.allows_resident_bytes(268'435'456));
  LMDJ_CHECK(!kWebLimits.allows_resident_bytes(268'435'457));

  const auto allowed = lmdj::audio::assess_runtime_quota(
      0, 0, 67'108'864, kWebLimits);
  LMDJ_CHECK(allowed.has_value());
  LMDJ_CHECK(
      allowed->constraint == lmdj::audio::RuntimeQuotaConstraint::none);
  const auto bank_bound = lmdj::audio::assess_runtime_quota(
      0, 0, 67'108'868, kWebLimits);
  LMDJ_CHECK(bank_bound.has_value());
  LMDJ_CHECK(
      bank_bound->constraint ==
      lmdj::audio::RuntimeQuotaConstraint::user_bank);
  const auto generation_bound = lmdj::audio::assess_runtime_quota(
      0, 134'217'724, 8, kWebLimits);
  LMDJ_CHECK(generation_bound.has_value());
  LMDJ_CHECK(
      generation_bound->constraint ==
      lmdj::audio::RuntimeQuotaConstraint::generation);
  const RuntimePreparationLimits tied_limits{1'048'576, 20, 20, 40};
  const auto tie = lmdj::audio::assess_runtime_quota(
      0, 0, 24, tied_limits);
  LMDJ_CHECK(tie.has_value());
  LMDJ_CHECK(
      tie->constraint == lmdj::audio::RuntimeQuotaConstraint::user_bank);
  LMDJ_CHECK(
      !lmdj::audio::assess_runtime_quota(21, 0, 1, tied_limits)
           .has_value());

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

void prepares_immutable_pattern_overlay_and_integer_timing() {
  auto snapshot = valid_snapshot();
  snapshot.events.push_back(lmdj::cooker::ResolvedEvent{
      PadSlotId{0, 0}, 0, 240, 64, snapshot.pads.at(0).sample});
  const std::array overlay{
      PatternEvent{PadSlotId{0, 0}, 0, 480, 127},
      PatternEvent{PadSlotId{3, 15}, 240, 240, 96},
  };

  auto prepared =
      PreparedPatternView::from_snapshot_with_overlay(snapshot, overlay);
  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value().project_id() == snapshot.project_id);
  LMDJ_CHECK(prepared.value().pattern_id() == snapshot.pattern_id);
  LMDJ_CHECK(prepared.value().ppq() == 960);
  LMDJ_CHECK(prepared.value().loop_length_ticks() == 3'840);
  LMDJ_CHECK(prepared.value().loop_frames() == 96'000);
  LMDJ_CHECK(prepared.value().bar_frames() == 96'000);
  LMDJ_CHECK(prepared.value().has_overlay());
  LMDJ_CHECK(prepared.value().events().size() == 2);
  LMDJ_CHECK(prepared.value().events().at(0).velocity == 127);
  LMDJ_CHECK(prepared.value().events().at(0).duration_tick == 480);
  LMDJ_CHECK(prepared.value().events().at(1).start_frame == 6'000);
  LMDJ_CHECK(snapshot.events.size() == 1);
  LMDJ_CHECK(snapshot.events.front().velocity == 64);
  LMDJ_CHECK(snapshot.events.front().duration_tick == 240);

  const TransportAnchor anchor{0, 0, 192};
  LMDJ_CHECK(lmdj::audio::raw_tick_at(anchor, 62).value() == 3);
  LMDJ_CHECK(lmdj::audio::raw_tick_at(anchor, 63).value() == 4);
  LMDJ_CHECK(
      lmdj::audio::tick_boundary_frame(4, 192).value() == 63);
  const auto frozen = lmdj::audio::freeze_transport_bpm(
      TransportAnchor{0, 0, 123}, 17, 97);
  LMDJ_CHECK(frozen.has_value());
  LMDJ_CHECK(frozen.value() == (TransportAnchor{17, 2'007'360, 97}));
  LMDJ_CHECK(
      lmdj::audio::tick_numerator_at(frozen.value(), 48).value() ==
      4'894'080);
}

void bounded_preparation_rejects_before_allocation_and_retains_prior_bank() {
  auto prior = PreparedSampleBank::empty(ProjectId{kProjectId}, 6);
  const std::array<float, 2> prior_pcm{0.25F, 0.25F};
  LMDJ_CHECK(prior.set_sample(0, prior_pcm).has_value());
  RealtimeEngine engine;
  LMDJ_CHECK(engine.publish_sample_bank(std::move(prior)) ==
             PublishResult::accepted);
  LMDJ_CHECK(engine.start().has_value());

  const auto check_prior = [&engine]() {
    LMDJ_CHECK(engine.enqueue(TriggerEvent{9, 0, 127}) ==
               EnqueueResult::accepted);
    std::array<float, 2> left{};
    std::array<float, 2> right{};
    engine.render(left.data(), right.data(), 2);
    // F6 ramp: attack 0/96 on the first frame, then attack 1/96 times the
    // boundary fade 1/96 on the second frame of the 2-frame sample.
    constexpr float kRampScale =
        1.0F / static_cast<float>(lmdj::audio::kRealtimeRampFrames);
    LMDJ_CHECK(left.at(0) == 0.0F);
    LMDJ_CHECK(
        left.at(1) == 0.25F * ((1.0F * kRampScale) * (1.0F * kRampScale)));
    LMDJ_CHECK(right == left);
  };

  const auto snapshot = valid_snapshot();
  const RuntimePreparationLimits exact{
      1'048'576,
      20,
      28,
      56,
  };
  const auto prepared = PreparedSampleBank::from_snapshot(snapshot, exact);
  LMDJ_CHECK(prepared.has_value());
  LMDJ_CHECK(prepared.value().decoded_pcm_bytes() == 28);
  check_prior();

  const auto bank_rejected = PreparedSampleBank::from_snapshot(
      snapshot,
      RuntimePreparationLimits{1'048'576, 19, 28, 56});
  LMDJ_CHECK(!bank_rejected.has_value());
  LMDJ_CHECK(
      bank_rejected.error().code == ErrorCode::bank_quota_exhausted);
  LMDJ_CHECK(bank_rejected.error().details.at("bank") == 0);
  LMDJ_CHECK(bank_rejected.error().details.at("requested_bytes") == 20);
  LMDJ_CHECK(bank_rejected.error().details.at("remaining_bytes") == 19);
  LMDJ_CHECK(bank_rejected.error().details.at("quota_bytes") == 19);
  LMDJ_CHECK(bank_rejected.error().details.at("consumed").empty());
  LMDJ_CHECK(
      bank_rejected.error().message.find("why:") != std::string::npos);
  LMDJ_CHECK(
      bank_rejected.error().message.find("remedy:") != std::string::npos);
  check_prior();

  const auto project_rejected = PreparedSampleBank::from_snapshot(
      snapshot,
      RuntimePreparationLimits{1'048'576, 20, 27, 56});
  LMDJ_CHECK(!project_rejected.has_value());
  LMDJ_CHECK(
      project_rejected.error().code ==
      ErrorCode::project_quota_exhausted);
  LMDJ_CHECK(project_rejected.error().details.at("requested_bytes") == 8);
  LMDJ_CHECK(
      project_rejected.error().details.at("project_used_bytes") == 20);
  LMDJ_CHECK(
      project_rejected.error().details.at("project_remaining_bytes") == 7);
  LMDJ_CHECK(
      project_rejected.error().details.at("project_quota_bytes") == 27);
  LMDJ_CHECK(project_rejected.error().details.at("banks").size() == 4);
  LMDJ_CHECK(
      project_rejected.error().message.find("why:") != std::string::npos);
  LMDJ_CHECK(
      project_rejected.error().message.find("remedy:") != std::string::npos);
  check_prior();

  const auto tie_rejected = PreparedSampleBank::from_snapshot(
      snapshot,
      RuntimePreparationLimits{1'048'576, 19, 19, 38});
  LMDJ_CHECK(!tie_rejected.has_value());
  LMDJ_CHECK(
      tie_rejected.error().code == ErrorCode::bank_quota_exhausted);
  check_prior();

  const auto resident_is_not_a_generation_quota =
      PreparedSampleBank::from_snapshot(
          snapshot,
          RuntimePreparationLimits{1'048'576, 20, 28, 0});
  LMDJ_CHECK(resident_is_not_a_generation_quota.has_value());
  check_prior();

  const auto artifact_rejected = PreparedSampleBank::from_snapshot(
      snapshot,
      RuntimePreparationLimits{9, 20, 28, 56});
  LMDJ_CHECK(!artifact_rejected.has_value());
  LMDJ_CHECK(artifact_rejected.error().code == ErrorCode::cook_failed);
  LMDJ_CHECK(
      artifact_rejected.error().details.at("resource") ==
      "artifact_bytes");
  check_prior();
}

void admits_decided_boundaries_and_rejects_one_mono_frame_over() {
  for (std::uint8_t bank = 0; bank < 4; ++bank) {
    const auto exact_bank = snapshot_with_frame_counts(
        {{PadSlotId{bank, 0}, 16'777'216}});
    const auto prepared =
        PreparedSampleBank::from_snapshot(exact_bank, kWebLimits);
    LMDJ_CHECK(prepared.has_value());
    LMDJ_CHECK(prepared.value().decoded_pcm_bytes() == 67'108'864);

    const auto bank_plus_one = snapshot_with_frame_counts(
        {{PadSlotId{bank, 0}, 16'777'217}});
    const auto rejected =
        PreparedSampleBank::from_snapshot(bank_plus_one, kWebLimits);
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(
        rejected.error().code == ErrorCode::bank_quota_exhausted);
    LMDJ_CHECK(rejected.error().details.at("bank") == bank);
    LMDJ_CHECK(rejected.error().details.at("requested_bytes") == 67'108'868);
    LMDJ_CHECK(rejected.error().details.at("remaining_bytes") == 67'108'864);
  }

  LMDJ_CHECK(kWebLimits.allows_resident_bytes(268'435'456));
  LMDJ_CHECK(!kWebLimits.allows_resident_bytes(268'435'460));

  {
    const auto exact_generation = snapshot_with_frame_counts({
        {PadSlotId{0, 0}, 16'777'216},
        {PadSlotId{1, 0}, 16'777'216},
    });
    const auto prepared =
        PreparedSampleBank::from_snapshot(exact_generation, kWebLimits);
    LMDJ_CHECK(prepared.has_value());
    LMDJ_CHECK(prepared.value().decoded_pcm_bytes() == 134'217'728);
  }

  {
    const auto generation_plus_one = snapshot_with_frame_counts({
        {PadSlotId{0, 0}, 16'777'216},
        {PadSlotId{1, 0}, 16'777'216},
        {PadSlotId{2, 0}, 1},
    });
    const auto rejected =
        PreparedSampleBank::from_snapshot(generation_plus_one, kWebLimits);
    LMDJ_CHECK(!rejected.has_value());
    LMDJ_CHECK(
        rejected.error().code == ErrorCode::project_quota_exhausted);
    LMDJ_CHECK(rejected.error().details.at("requested_bytes") == 4);
    LMDJ_CHECK(
        rejected.error().details.at("project_remaining_bytes") == 0);
  }
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
  admits_decided_boundaries_and_rejects_one_mono_frame_over();
  prepares_immutable_pattern_overlay_and_integer_timing();
}
