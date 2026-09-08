#include <lmdj/audio/prepared_sample_bank.hpp>

#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <string>
#include <tuple>
#include <utility>

#include <lmdj/domain/project.hpp>

namespace lmdj::audio {
namespace {

foundation::Result<void> invalid_argument(std::string message) {
  return foundation::Result<void>::failure(foundation::Error{
      foundation::ErrorCode::invalid_argument,
      std::move(message),
  });
}

foundation::Result<PreparedSampleBank> invalid_bank(std::string message) {
  return foundation::Result<PreparedSampleBank>::failure(foundation::Error{
      foundation::ErrorCode::invalid_argument,
      std::move(message),
  });
}

foundation::Result<PreparedSampleBank> preparation_limit(
    std::string resource,
    std::uint64_t observed,
    std::uint64_t limit) {
  return foundation::Result<PreparedSampleBank>::failure(foundation::Error{
      foundation::ErrorCode::cook_failed,
      "runtime preparation limit exceeded",
      {
          {"resource", std::move(resource)},
          {"observed", observed},
          {"limit", limit},
      },
  });
}

foundation::Result<PreparedSampleBank> bank_quota_exhausted(
    std::uint8_t bank,
    std::uint64_t requested_bytes,
    std::uint64_t requested_frames,
    std::uint64_t remaining_bytes,
    std::uint64_t quota_bytes,
    const std::vector<nlohmann::json>& consumed) {
  return foundation::Result<PreparedSampleBank>::failure(foundation::Error{
      foundation::ErrorCode::bank_quota_exhausted,
      "Bank prepared-PCM quota exhausted; why: the committed selection "
      "does not fit in this Bank; remedy: shorten or remove samples in the "
      "same Bank, then retry",
      {
          {"bank", bank},
          {"requested_bytes", requested_bytes},
          {"requested_frames", requested_frames},
          {"remaining_bytes", remaining_bytes},
          {"remaining_frames", remaining_bytes / sizeof(float)},
          {"quota_bytes", quota_bytes},
          {"consumed", consumed},
      },
  });
}

foundation::Result<PreparedSampleBank> project_quota_exhausted(
    std::uint64_t requested_bytes,
    std::uint64_t requested_frames,
    std::uint64_t project_used_bytes,
    std::uint64_t project_remaining_bytes,
    std::uint64_t project_quota_bytes,
    const std::array<std::uint64_t, 4>& bank_bytes) {
  auto banks = nlohmann::json::array();
  for (std::uint8_t bank = 0; bank < bank_bytes.size(); ++bank) {
    banks.push_back({
        {"bank", bank},
        {"prepared_bytes", bank_bytes.at(bank)},
    });
  }
  return foundation::Result<PreparedSampleBank>::failure(foundation::Error{
      foundation::ErrorCode::project_quota_exhausted,
      "Project prepared-PCM quota exhausted; why: the committed selection "
      "does not fit in the current generation; remedy: shorten or remove "
      "samples in the Project, then retry",
      {
          {"requested_bytes", requested_bytes},
          {"requested_frames", requested_frames},
          {"project_used_bytes", project_used_bytes},
          {"project_remaining_bytes", project_remaining_bytes},
          {"project_quota_bytes", project_quota_bytes},
          {"banks", std::move(banks)},
      },
  });
}

std::uint8_t global_slot(domain::PadSlotId slot) noexcept {
  return static_cast<std::uint8_t>(slot.bank * 16U + slot.pad);
}

bool valid_trigger_mode(domain::TriggerMode mode) noexcept {
  switch (mode) {
    case domain::TriggerMode::one_shot:
    case domain::TriggerMode::gate:
    case domain::TriggerMode::loop_gate:
    case domain::TriggerMode::loop_toggle:
      return true;
  }
  return false;
}

bool valid_playback(
    const cooker::ResolvedPlayback& playback,
    std::size_t frame_count) noexcept {
  return playback.start_frame < playback.end_frame &&
         playback.end_frame <= frame_count &&
         valid_trigger_mode(playback.trigger_mode) &&
         std::isfinite(playback.linear_gain) && playback.linear_gain >= 0.0F;
}

foundation::Error invalid_timing(std::string message) {
  return foundation::Error{
      foundation::ErrorCode::invalid_argument,
      std::move(message),
  };
}

bool valid_bpm(std::uint16_t bpm) noexcept {
  return bpm >= 40 && bpm <= 240;
}

}  // namespace

foundation::Result<PreparedPatternView> PreparedPatternView::prepare(
    const cooker::RuntimeSnapshot& snapshot,
    std::span<const domain::PatternEvent> journal_overlay,
    bool canonical) {
  if (!domain::is_valid_uuid(snapshot.project_id.value()) ||
      !domain::is_valid_uuid(snapshot.pattern_id.value()) ||
      !valid_bpm(snapshot.bpm) || snapshot.ppq != kTransportPpq ||
      snapshot.loop_length_ticks == 0 ||
      snapshot.loop_length_ticks !=
          domain::pattern_length_ticks(snapshot.bars)) {
    return foundation::Result<PreparedPatternView>::failure(
        invalid_timing("runtime snapshot Pattern timing is invalid"));
  }

  struct PatternPadMaterial {
    PreparedSampleMaterialView view;
    cooker::ResolvedPlayback playback;
  };
  std::array<std::optional<PatternPadMaterial>, 64> materials{};
  std::vector<std::shared_ptr<const cooker::PcmSample>> material_owners;
  material_owners.reserve(snapshot.pads.size());
  for (const auto& pad : snapshot.pads) {
    const auto slot = global_slot(pad.slot);
    if (!domain::is_valid_slot(pad.slot) || materials.at(slot).has_value() ||
        !pad.sample || pad.sample->sample_rate != kTransportSampleRate ||
        (pad.sample->channels != 1 && pad.sample->channels != 2) ||
        pad.sample->interleaved.empty() ||
        pad.sample->interleaved.size() % pad.sample->channels != 0) {
      return foundation::Result<PreparedPatternView>::failure(
          invalid_timing("runtime snapshot Pattern Pad is invalid"));
    }
    const auto frame_count =
        pad.sample->interleaved.size() / pad.sample->channels;
    if (frame_count > std::numeric_limits<std::uint32_t>::max() ||
        !valid_playback(pad.playback, frame_count)) {
      return foundation::Result<PreparedPatternView>::failure(
          invalid_timing("runtime snapshot Pattern Pad material is invalid"));
    }
    if (std::none_of(material_owners.begin(), material_owners.end(),
                     [&pad](const auto& owner) {
                       return owner.get() == pad.sample.get();
                     })) {
      material_owners.push_back(pad.sample);
    }
    materials.at(slot) = PatternPadMaterial{
        PreparedSampleMaterialView{
            pad.sample->interleaved.data(),
            static_cast<std::uint32_t>(frame_count),
            pad.sample->channels,
        },
        pad.playback,
    };
  }

  std::vector<domain::PatternEvent> base;
  base.reserve(snapshot.events.size());
  for (const auto& event : snapshot.events) {
    if (canonical && !base.empty()) {
      const auto& prior = base.back();
      if (std::tie(prior.onset_tick, prior.slot.bank, prior.slot.pad) >=
          std::tie(event.onset_tick, event.slot.bank, event.slot.pad)) {
        return foundation::Result<PreparedPatternView>::failure(
            invalid_timing("runtime snapshot events are not canonical"));
      }
    }
    base.push_back(domain::PatternEvent{
        event.slot,
        event.onset_tick,
        event.duration_tick,
        event.velocity,
    });
  }
  std::vector<domain::PatternEvent> overlay{
      journal_overlay.begin(), journal_overlay.end()};
  auto merged = canonical ? std::move(base)
                          : domain::merge_pattern_events(base, overlay);

  auto loop_frames = tick_boundary_frame(
      snapshot.loop_length_ticks, snapshot.bpm, snapshot.ppq);
  auto bar_frames = tick_boundary_frame(
      domain::kBarTicks4x4, snapshot.bpm, snapshot.ppq);
  if (!loop_frames.has_value() || !bar_frames.has_value() ||
      loop_frames.value() == 0 || bar_frames.value() == 0) {
    return foundation::Result<PreparedPatternView>::failure(
        invalid_timing("runtime snapshot Pattern frame bounds overflowed"));
  }

  std::vector<PreparedPatternEvent> prepared;
  prepared.reserve(merged.size());
  for (const auto& event : merged) {
    if (!domain::is_valid_slot(event.slot) || event.velocity < 1 ||
        event.velocity > 127 ||
        !materials.at(global_slot(event.slot)).has_value() ||
        event.onset_tick >= snapshot.loop_length_ticks ||
        event.duration_tick < 1 ||
        event.duration_tick >
            snapshot.loop_length_ticks - event.onset_tick) {
      return foundation::Result<PreparedPatternView>::failure(
          invalid_timing("runtime snapshot Pattern event is invalid"));
    }
    auto start = tick_boundary_frame(
        event.onset_tick, snapshot.bpm, snapshot.ppq);
    auto release = tick_boundary_frame(
        static_cast<std::uint64_t>(event.onset_tick) +
            event.duration_tick,
        snapshot.bpm,
        snapshot.ppq);
    if (!start.has_value() || !release.has_value() ||
        start.value() >= loop_frames.value() ||
        release.value() <= start.value() ||
        release.value() > loop_frames.value()) {
      return foundation::Result<PreparedPatternView>::failure(
          invalid_timing("runtime snapshot Pattern event frame is invalid"));
    }
    const auto& material = *materials.at(global_slot(event.slot));
    prepared.push_back(PreparedPatternEvent{
        event.slot,
        event.onset_tick,
        event.duration_tick,
        event.velocity,
        start.value(),
        release.value(),
        material.view,
        material.playback,
    });
  }
  return foundation::Result<PreparedPatternView>::success(
      PreparedPatternView{
          snapshot.project_id,
          snapshot.pattern_id,
          snapshot.project_revision,
          snapshot.bpm,
          snapshot.ppq,
          snapshot.loop_length_ticks,
          loop_frames.value(),
          bar_frames.value(),
          std::move(prepared),
          std::move(material_owners),
          !journal_overlay.empty(),
      });
}

foundation::Result<PreparedPatternView>
PreparedPatternView::from_canonical_snapshot(
    const cooker::RuntimeSnapshot& snapshot) {
  return prepare(snapshot, {}, true);
}

foundation::Result<std::uint64_t> tick_numerator_at(
    const TransportAnchor& anchor,
    std::uint64_t runtime_frame) noexcept {
  if (!valid_bpm(anchor.bpm) || runtime_frame < anchor.runtime_frame) {
    return foundation::Result<std::uint64_t>::failure(
        invalid_timing("transport anchor or frame is invalid"));
  }
  const auto delta = runtime_frame - anchor.runtime_frame;
  const auto numerator = integrate_tick_numerator(
      anchor.tick_numerator, delta, anchor.bpm);
  if (!numerator.has_value()) {
    return foundation::Result<std::uint64_t>::failure(
        invalid_timing("transport tick numerator overflowed"));
  }
  return foundation::Result<std::uint64_t>::success(numerator.value());
}

foundation::Result<std::uint64_t> raw_tick_at(
    const TransportAnchor& anchor,
    std::uint64_t runtime_frame) noexcept {
  auto numerator = tick_numerator_at(anchor, runtime_frame);
  if (!numerator.has_value()) {
    return foundation::Result<std::uint64_t>::failure(numerator.error());
  }
  return foundation::Result<std::uint64_t>::success(
      whole_tick(numerator.value()));
}

foundation::Result<TransportAnchor> freeze_transport_bpm(
    const TransportAnchor& anchor,
    std::uint64_t runtime_frame,
    std::uint16_t new_bpm) noexcept {
  if (!valid_bpm(new_bpm)) {
    return foundation::Result<TransportAnchor>::failure(
        invalid_timing("transport BPM is outside the supported range"));
  }
  auto numerator = tick_numerator_at(anchor, runtime_frame);
  if (!numerator.has_value()) {
    return foundation::Result<TransportAnchor>::failure(numerator.error());
  }
  return foundation::Result<TransportAnchor>::success(
      TransportAnchor{runtime_frame, numerator.value(), new_bpm});
}

foundation::Result<std::uint64_t> tick_boundary_frame(
    std::uint64_t tick,
    std::uint16_t bpm,
    std::uint32_t ppq) noexcept {
  if (!valid_bpm(bpm) || ppq != kTransportPpq) {
    return foundation::Result<std::uint64_t>::failure(
        invalid_timing("tick boundary timing is invalid"));
  }
  constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
  if (tick != 0 && tick > maximum / kTickDenominator) {
    return foundation::Result<std::uint64_t>::failure(
        invalid_timing("tick boundary numerator overflowed"));
  }
  const auto numerator = tick * kTickDenominator;
  const auto rate = static_cast<std::uint64_t>(bpm) * ppq;
  return foundation::Result<std::uint64_t>::success(
      numerator / rate + (numerator % rate == 0 ? 0U : 1U));
}

PreparedPatternView::PreparedPatternView(
    foundation::ProjectId project_id,
    foundation::PatternId pattern_id,
    std::uint64_t project_revision,
    std::uint16_t bpm,
    std::uint32_t ppq,
    std::uint32_t loop_length_ticks,
    std::uint64_t loop_frames,
    std::uint64_t bar_frames,
    std::vector<PreparedPatternEvent> events,
    std::vector<std::shared_ptr<const cooker::PcmSample>> material_owners,
    bool has_overlay)
    : project_id_(std::move(project_id)),
      pattern_id_(std::move(pattern_id)),
      project_revision_(project_revision),
      bpm_(bpm),
      ppq_(ppq),
      loop_length_ticks_(loop_length_ticks),
      loop_frames_(loop_frames),
      bar_frames_(bar_frames),
      events_(std::move(events)),
      material_owners_(std::move(material_owners)),
      has_overlay_(has_overlay) {}

foundation::Result<PreparedPatternView> PreparedPatternView::from_snapshot(
    const cooker::RuntimeSnapshot& snapshot) {
  return prepare(snapshot, {});
}

foundation::Result<PreparedPatternView>
PreparedPatternView::from_snapshot_with_overlay(
    const cooker::RuntimeSnapshot& snapshot,
    std::span<const domain::PatternEvent> journal_overlay) {
  return prepare(snapshot, journal_overlay);
}

const foundation::ProjectId& PreparedPatternView::project_id() const noexcept {
  return project_id_;
}

const foundation::PatternId& PreparedPatternView::pattern_id() const noexcept {
  return pattern_id_;
}

std::uint64_t PreparedPatternView::project_revision() const noexcept {
  return project_revision_;
}

std::uint16_t PreparedPatternView::bpm() const noexcept { return bpm_; }
std::uint32_t PreparedPatternView::ppq() const noexcept { return ppq_; }

std::uint32_t PreparedPatternView::loop_length_ticks() const noexcept {
  return loop_length_ticks_;
}

std::uint64_t PreparedPatternView::loop_frames() const noexcept {
  return loop_frames_;
}

std::uint64_t PreparedPatternView::bar_frames() const noexcept {
  return bar_frames_;
}

const std::vector<PreparedPatternEvent>& PreparedPatternView::events()
    const noexcept {
  return events_;
}

bool PreparedPatternView::has_overlay() const noexcept {
  return has_overlay_;
}

PreparedSampleBank::PreparedSampleBank(foundation::ProjectId project_id,
                                       std::uint64_t project_revision)
    : project_id_(std::move(project_id)), project_revision_(project_revision) {}

foundation::Result<PreparedSampleBank> PreparedSampleBank::from_snapshot(
    const cooker::RuntimeSnapshot& snapshot) {
  constexpr auto unbounded = std::numeric_limits<std::uint64_t>::max();
  return from_snapshot(
      snapshot,
      RuntimePreparationLimits{
          unbounded,
          unbounded,
          unbounded,
          unbounded,
      });
}

foundation::Result<PreparedSampleBank> PreparedSampleBank::from_snapshot(
    const cooker::RuntimeSnapshot& snapshot,
    const RuntimePreparationLimits& limits) {
  if (!domain::is_valid_uuid(snapshot.project_id.value())) {
    return invalid_bank("runtime snapshot Project ID is invalid");
  }
  std::uint8_t previous_slot = 0;
  bool has_previous_slot = false;
  std::array<std::uint64_t, 4> prospective_bank_bytes{};
  std::array<std::vector<nlohmann::json>, 4> consumed{};
  std::uint64_t prospective_generation_bytes = 0;
  for (const auto& pad : snapshot.pads) {
    if (!domain::is_valid_slot(pad.slot) || pad.sample == nullptr) {
      return invalid_bank("runtime snapshot Pad is invalid");
    }
    const auto slot = global_slot(pad.slot);
    if (has_previous_slot && slot <= previous_slot) {
      return invalid_bank("runtime snapshot Pads are not unique and ordered");
    }
    if (!limits.allows_artifact_bytes(pad.artifact.byte_length)) {
      return preparation_limit(
          "artifact_bytes",
          pad.artifact.byte_length,
          limits.maximum_artifact_bytes);
    }
    const auto& source = *pad.sample;
    if (source.sample_rate != 48'000 ||
        (source.channels != 1 && source.channels != 2) ||
        source.interleaved.empty() ||
        source.interleaved.size() % source.channels != 0) {
      return invalid_bank("runtime snapshot PCM shape is invalid");
    }
    const auto frames = static_cast<std::uint64_t>(
        source.interleaved.size() / source.channels);
    if (!valid_playback(pad.playback, static_cast<std::size_t>(frames))) {
      return invalid_bank("runtime snapshot Pad playback is invalid");
    }
    const auto sample_bytes = checked_mono_float_bytes(frames);
    if (!sample_bytes.has_value()) {
      return invalid_bank("runtime snapshot PCM byte length overflowed");
    }
    const auto assessment = assess_runtime_quota(
        prospective_bank_bytes.at(pad.slot.bank),
        prospective_generation_bytes,
        sample_bytes.value(),
        limits);
    if (!assessment.has_value()) {
      return invalid_bank("runtime snapshot quota ledger is invalid");
    }
    if (assessment->constraint == RuntimeQuotaConstraint::user_bank) {
      return bank_quota_exhausted(
          pad.slot.bank,
          sample_bytes.value(),
          frames,
          assessment->user_bank_remaining_bytes,
          limits.maximum_user_bank_bytes,
          consumed.at(pad.slot.bank));
    }
    if (assessment->constraint == RuntimeQuotaConstraint::generation) {
      return project_quota_exhausted(
          sample_bytes.value(),
          frames,
          prospective_generation_bytes,
          assessment->generation_remaining_bytes,
          limits.maximum_generation_bytes,
          prospective_bank_bytes);
    }
    prospective_bank_bytes.at(pad.slot.bank) += sample_bytes.value();
    prospective_generation_bytes += sample_bytes.value();
    consumed.at(pad.slot.bank).push_back({
        {"pad", pad.slot.pad},
        {"prepared_bytes", sample_bytes.value()},
        {"prepared_frames", frames},
    });
    previous_slot = slot;
    has_previous_slot = true;
  }

  PreparedSampleBank bank(snapshot.project_id, snapshot.project_revision);
  for (const auto& pad : snapshot.pads) {
    const auto slot = global_slot(pad.slot);
    const auto& source = *pad.sample;
    std::vector<float> mono;
    mono.reserve(source.interleaved.size() / source.channels);
    if (source.channels == 1) {
      for (const auto value : source.interleaved) {
        mono.push_back(prepared_pcm16_to_float(value));
      }
    } else {
      for (std::size_t index = 0; index < source.interleaved.size();
           index += 2) {
        mono.push_back(
            (prepared_pcm16_to_float(source.interleaved.at(index)) +
             prepared_pcm16_to_float(source.interleaved.at(index + 1))) *
            0.5F);
      }
    }
    const auto assigned = bank.set_sample(slot, mono, pad.playback);
    if (!assigned.has_value()) {
      return invalid_bank(assigned.error().message);
    }
  }
  return foundation::Result<PreparedSampleBank>::success(std::move(bank));
}

PreparedSampleBank PreparedSampleBank::empty(foundation::ProjectId project_id,
                                             std::uint64_t project_revision) {
  return PreparedSampleBank(std::move(project_id), project_revision);
}

foundation::Result<void> PreparedSampleBank::set_sample(
    std::uint8_t slot, std::span<const float> mono_pcm) {
  if (mono_pcm.size() > std::numeric_limits<std::uint32_t>::max()) {
    return invalid_argument("prepared Sample Bank playback is invalid");
  }
  return set_sample(
      slot,
      mono_pcm,
      cooker::ResolvedPlayback{
          0,
          static_cast<std::uint32_t>(mono_pcm.size()),
          domain::TriggerMode::one_shot,
          1.0F,
          false,
      });
}

foundation::Result<void> PreparedSampleBank::set_sample(
    std::uint8_t slot,
    std::span<const float> mono_pcm,
    cooker::ResolvedPlayback playback) {
  if (slot >= samples_.size() || mono_pcm.empty() ||
      (availability_mask_ & (std::uint64_t{1} << slot)) != 0 ||
      !std::all_of(mono_pcm.begin(), mono_pcm.end(),
                   [](float value) { return std::isfinite(value); })) {
    return invalid_argument("prepared Sample Bank input is invalid");
  }
  if (!valid_playback(playback, mono_pcm.size())) {
    return invalid_argument("prepared Sample Bank playback is invalid");
  }
  const auto sample_bytes = checked_mono_float_bytes(mono_pcm.size());
  if (!sample_bytes.has_value()) {
    return invalid_argument("prepared Sample Bank byte length overflowed");
  }
  const auto prospective = checked_runtime_byte_sum(
      decoded_pcm_bytes_, sample_bytes.value());
  if (!prospective.has_value()) {
    return invalid_argument("prepared Sample Bank byte length overflowed");
  }
  samples_.at(slot).assign(mono_pcm.begin(), mono_pcm.end());
  playbacks_.at(slot) = playback;
  availability_mask_ |= std::uint64_t{1} << slot;
  decoded_pcm_bytes_ = prospective.value();
  return foundation::Result<void>::success();
}

const foundation::ProjectId& PreparedSampleBank::project_id() const noexcept {
  return project_id_;
}

std::uint64_t PreparedSampleBank::project_revision() const noexcept {
  return project_revision_;
}

std::uint64_t PreparedSampleBank::availability_mask() const noexcept {
  return availability_mask_;
}

std::size_t PreparedSampleBank::sample_count() const noexcept {
  return static_cast<std::size_t>(std::popcount(availability_mask_));
}

std::uint64_t PreparedSampleBank::decoded_pcm_bytes() const noexcept {
  return decoded_pcm_bytes_;
}

const std::vector<float>& PreparedSampleBank::sample(
    std::uint8_t slot) const noexcept {
  return samples_[slot];
}

const cooker::ResolvedPlayback& PreparedSampleBank::playback(
    std::uint8_t slot) const noexcept {
  return playbacks_[slot];
}

}  // namespace lmdj::audio
