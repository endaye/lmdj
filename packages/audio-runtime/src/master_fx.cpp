#include <lmdj/audio/master_fx.hpp>

#include <algorithm>
#include <cmath>
#include <string>
#include <utility>

namespace lmdj::audio {
namespace {

constexpr std::size_t effect_index(domain::PerformanceFx fx) noexcept {
  return static_cast<std::size_t>(fx);
}

constexpr bool valid_fx(domain::PerformanceFx fx) noexcept {
  return effect_index(fx) < kFxChainOrder.size() &&
         kFxChainOrder[effect_index(fx)] == fx;
}

foundation::Result<void> invalid_preparation(std::string message) {
  return foundation::Result<void>::failure(foundation::Error{
      foundation::ErrorCode::invalid_argument, std::move(message)});
}

float quantize(float sample, std::uint32_t levels) noexcept {
  return std::round(sample * static_cast<float>(levels)) /
         static_cast<float>(levels);
}

std::uint32_t delay_division(std::uint16_t value) noexcept {
  return 1U + (static_cast<std::uint32_t>(value) * 15U) /
                  kMasterFxValueMaximum;
}

}  // namespace

foundation::Result<void> MasterFxChain::prepare(
    MasterFxPreparation preparation) {
  if (preparation.sample_rate == 0) {
    return invalid_preparation("Master FX sample rate must be nonzero");
  }
  if (preparation.bpm < 40 || preparation.bpm > 240) {
    return invalid_preparation("Master FX BPM must be between 40 and 240");
  }

  const auto bar_frames = master_fx_bar_frames(preparation.sample_rate, 40);
  if (bar_frames == 0) {
    return invalid_preparation("Master FX bar length must be nonzero");
  }
  sample_rate_ = preparation.sample_rate;
  bpm_ = preparation.bpm;
  delay_left_.assign(bar_frames, 0.0F);
  delay_right_.assign(bar_frames, 0.0F);
  delay_play_left_.assign(bar_frames, 0.0F);
  delay_play_right_.assign(bar_frames, 0.0F);
  const auto reverb_frames =
      std::max<std::size_t>(1, preparation.sample_rate / 20U);
  reverb_left_.assign(reverb_frames, 0.0F);
  reverb_right_.assign(reverb_frames, 0.0F);
  stutter_left_.assign(bar_frames, 0.0F);
  stutter_right_.assign(bar_frames, 0.0F);
  reverse_left_.assign(bar_frames, 0.0F);
  reverse_right_.assign(bar_frames, 0.0F);
  reverse_play_left_.assign(bar_frames, 0.0F);
  reverse_play_right_.assign(bar_frames, 0.0F);
  prepared_ = true;
  reset();
  return foundation::Result<void>::success();
}

void MasterFxChain::reset() noexcept {
  effects_.fill(EffectState{});
  hold_ = false;
  filter_low_left_ = 0.0F;
  filter_low_right_ = 0.0F;
  filter_band_left_ = 0.0F;
  filter_band_right_ = 0.0F;
  delay_cursor_ = 0;
  delay_play_frames_ = 0;
  delay_period_division_ = 0;
  reverb_cursor_ = 0;
  reverb_valid_frames_ = 0;
  stutter_cursor_ = 0;
  stutter_captured_ = false;
  stutter_capture_frames_ = 0;
  stutter_period_division_ = 0;
  reverse_cursor_ = 0;
  reverse_play_frames_ = 0;
  crush_phase_ = 0;
  crush_left_ = 0.0F;
  crush_right_ = 0.0F;
  cutter_period_division_ = 0;
  std::fill(delay_left_.begin(), delay_left_.end(), 0.0F);
  std::fill(delay_right_.begin(), delay_right_.end(), 0.0F);
  std::fill(delay_play_left_.begin(), delay_play_left_.end(), 0.0F);
  std::fill(delay_play_right_.begin(), delay_play_right_.end(), 0.0F);
  std::fill(reverb_left_.begin(), reverb_left_.end(), 0.0F);
  std::fill(reverb_right_.begin(), reverb_right_.end(), 0.0F);
  std::fill(stutter_left_.begin(), stutter_left_.end(), 0.0F);
  std::fill(stutter_right_.begin(), stutter_right_.end(), 0.0F);
  std::fill(reverse_left_.begin(), reverse_left_.end(), 0.0F);
  std::fill(reverse_right_.begin(), reverse_right_.end(), 0.0F);
  std::fill(reverse_play_left_.begin(), reverse_play_left_.end(), 0.0F);
  std::fill(reverse_play_right_.begin(), reverse_play_right_.end(), 0.0F);
}

bool MasterFxChain::set_bpm(std::uint16_t bpm) noexcept {
  if (!prepared_ || bpm < 40 || bpm > 240) {
    return false;
  }
  bpm_ = bpm;
  if (delay_period_division_ != 0) {
    delay_period_.set_rate(bpm_, delay_period_division_);
  }
  if (stutter_period_division_ != 0) {
    stutter_period_.set_rate(bpm_, stutter_period_division_);
  }
  if (cutter_period_division_ != 0) {
    cutter_period_.set_rate(bpm_, cutter_period_division_);
  }
  return true;
}

bool MasterFxChain::active(domain::PerformanceFx fx) const noexcept {
  const auto& state = effects_[effect_index(fx)];
  return state.engaged || state.frozen;
}

std::uint16_t MasterFxChain::value(domain::PerformanceFx fx) const noexcept {
  return effects_[effect_index(fx)].value;
}

void MasterFxChain::reset_effect(domain::PerformanceFx fx) noexcept {
  switch (fx) {
    case domain::PerformanceFx::filter:
      filter_low_left_ = 0.0F;
      filter_low_right_ = 0.0F;
      filter_band_left_ = 0.0F;
      filter_band_right_ = 0.0F;
      return;
    case domain::PerformanceFx::delay:
      delay_cursor_ = 0;
      delay_play_frames_ = 0;
      delay_period_division_ = 0;
      return;
    case domain::PerformanceFx::reverb:
      reverb_cursor_ = 0;
      reverb_valid_frames_ = 0;
      return;
    case domain::PerformanceFx::stutter:
      stutter_cursor_ = 0;
      stutter_captured_ = false;
      stutter_capture_frames_ = 0;
      stutter_period_division_ = 0;
      return;
    case domain::PerformanceFx::gate:
      return;
    case domain::PerformanceFx::reverse:
      reverse_cursor_ = 0;
      reverse_play_frames_ = 0;
      return;
    case domain::PerformanceFx::crush:
      crush_phase_ = 0;
      crush_left_ = 0.0F;
      crush_right_ = 0.0F;
      return;
    case domain::PerformanceFx::cutter:
      cutter_period_division_ = 0;
      return;
  }
}

bool MasterFxChain::apply_gesture(FxGesture gesture) noexcept {
  switch (gesture.kind) {
    case FxGestureKind::hold_on:
      hold_ = true;
      return true;
    case FxGestureKind::hold_off:
      hold_ = false;
      for (auto& effect : effects_) {
        effect.frozen = false;
      }
      return true;
    case FxGestureKind::engage:
    case FxGestureKind::move:
    case FxGestureKind::release:
      break;
  }
  if (!valid_fx(gesture.fx) || gesture.value > kMasterFxValueMaximum) {
    return false;
  }

  auto& effect = effects_[effect_index(gesture.fx)];
  if (gesture.kind == FxGestureKind::release) {
    const auto was_active = effect.engaged || effect.frozen;
    effect.engaged = false;
    effect.frozen = hold_ && was_active;
    if (!effect.frozen) {
      effect.value = 0;
    }
    return true;
  }

  effect.value = gesture.value;
  if (gesture.kind == FxGestureKind::engage) {
    effect.engaged = true;
    effect.frozen = false;
    reset_effect(gesture.fx);
  }
  return true;
}

void MasterFxChain::process(
    float* left, float* right, std::size_t frames) noexcept {
  if (!prepared_ || left == nullptr || right == nullptr || frames == 0) {
    return;
  }
  auto has_processing_effect = false;
  for (std::size_t index = 0; index < effects_.size(); ++index) {
    const auto& effect = effects_[index];
    if (!(effect.engaged || effect.frozen)) {
      continue;
    }
    if (kFxChainOrder[index] == domain::PerformanceFx::filter &&
        effect.value == 500) {
      continue;
    }
    has_processing_effect = true;
    break;
  }
  if (!has_processing_effect) {
    return;
  }
  process_filter(left, right, frames);
  process_delay(left, right, frames);
  process_reverb(left, right, frames);
  process_stutter(left, right, frames);
  process_gate(left, right, frames);
  process_reverse(left, right, frames);
  process_crush(left, right, frames);
  process_cutter(left, right, frames);
  for (std::size_t frame = 0; frame < frames; ++frame) {
    left[frame] = std::clamp(left[frame], -1.0F, 1.0F);
    right[frame] = std::clamp(right[frame], -1.0F, 1.0F);
  }
}

void MasterFxChain::process_filter(
    float* left, float* right, std::size_t frames) noexcept {
  if (!active(domain::PerformanceFx::filter)) {
    return;
  }
  const auto setting = value(domain::PerformanceFx::filter);
  if (setting == 500) {
    return;
  }
  const auto depth = static_cast<float>(
      setting > 500 ? setting - 500 : 500 - setting) / 500.0F;
  const auto low_pass = setting < 500;
  const auto coefficient = low_pass
                               ? 0.04F + (1.0F - depth) * 0.25F
                               : 0.02F + depth * 0.25F;
  const auto damping = 0.35F + (1.0F - depth) * 0.35F;
  const auto filter = [coefficient, damping, depth, low_pass](
                          float input,
                          float& low,
                          float& band) noexcept {
    low += coefficient * band;
    const auto high = input - low - damping * band;
    band += coefficient * high;
    const auto selected = low_pass ? low : high;
    return input + (selected - input) * depth;
  };
  for (std::size_t frame = 0; frame < frames; ++frame) {
    left[frame] =
        filter(left[frame], filter_low_left_, filter_band_left_);
    right[frame] =
        filter(right[frame], filter_low_right_, filter_band_right_);
  }
}

void MasterFxChain::process_delay(
    float* left, float* right, std::size_t frames) noexcept {
  if (!active(domain::PerformanceFx::delay)) {
    return;
  }
  const auto setting = value(domain::PerformanceFx::delay);
  const auto division = delay_division(setting);
  if (delay_period_division_ == 0) {
    delay_period_.configure(sample_rate_, bpm_, division);
    delay_period_division_ = division;
  } else if (delay_period_division_ != division) {
    delay_period_.set_rate(bpm_, division);
    delay_period_division_ = division;
  }
  const auto wet = static_cast<float>(setting) / kMasterFxValueMaximum;
  for (std::size_t frame = 0; frame < frames; ++frame) {
    const auto input_left = left[frame];
    const auto input_right = right[frame];
    auto delayed_left = 0.0F;
    auto delayed_right = 0.0F;
    if (delay_play_frames_ != 0) {
      const auto play_cursor = std::min(
          delay_play_frames_ - 1U,
          static_cast<std::size_t>(
              delay_period_.phase_numerator() * delay_play_frames_ /
              delay_period_.denominator()));
      delayed_left = delay_play_left_[play_cursor];
      delayed_right = delay_play_right_[play_cursor];
    }
    delay_left_[delay_cursor_] = input_left + delayed_right * 0.35F;
    delay_right_[delay_cursor_] = input_right + delayed_left * 0.35F;
    left[frame] = input_left * (1.0F - wet) + delayed_left * wet;
    right[frame] = input_right * (1.0F - wet) + delayed_right * wet;
    ++delay_cursor_;
    if (delay_period_.advance_frame()) {
      delay_left_.swap(delay_play_left_);
      delay_right_.swap(delay_play_right_);
      delay_play_frames_ = delay_cursor_;
      delay_cursor_ = 0;
    }
  }
}

void MasterFxChain::process_reverb(
    float* left, float* right, std::size_t frames) noexcept {
  if (!active(domain::PerformanceFx::reverb)) {
    return;
  }
  const auto wet = static_cast<float>(value(domain::PerformanceFx::reverb)) /
                   kMasterFxValueMaximum;
  for (std::size_t frame = 0; frame < frames; ++frame) {
    const auto input_left = left[frame];
    const auto input_right = right[frame];
    const auto valid = reverb_cursor_ < reverb_valid_frames_;
    const auto reflected_left = valid ? reverb_left_[reverb_cursor_] : 0.0F;
    const auto reflected_right =
        valid ? reverb_right_[reverb_cursor_] : 0.0F;
    reverb_left_[reverb_cursor_] = input_left + reflected_right * 0.62F;
    reverb_right_[reverb_cursor_] = input_right + reflected_left * 0.62F;
    reverb_valid_frames_ =
        std::max(reverb_valid_frames_, reverb_cursor_ + 1U);
    left[frame] = input_left * (1.0F - wet * 0.65F) + reflected_left * wet;
    right[frame] = input_right * (1.0F - wet * 0.65F) + reflected_right * wet;
    reverb_cursor_ = (reverb_cursor_ + 1U) % reverb_left_.size();
  }
}

void MasterFxChain::process_stutter(
    float* left, float* right, std::size_t frames) noexcept {
  if (!active(domain::PerformanceFx::stutter)) {
    return;
  }
  const auto division =
      master_fx_stutter_divisor(value(domain::PerformanceFx::stutter));
  if (stutter_period_division_ == 0) {
    stutter_period_.configure(sample_rate_, bpm_, division);
    stutter_period_division_ = division;
  } else if (stutter_period_division_ != division) {
    stutter_period_.set_rate(bpm_, division);
    stutter_period_division_ = division;
  }
  for (std::size_t frame = 0; frame < frames; ++frame) {
    if (!stutter_captured_) {
      stutter_left_[stutter_cursor_] = left[frame];
      stutter_right_[stutter_cursor_] = right[frame];
    } else {
      const auto captured_cursor =
          stutter_cursor_ % stutter_capture_frames_;
      left[frame] = stutter_left_[captured_cursor];
      right[frame] = stutter_right_[captured_cursor];
    }
    ++stutter_cursor_;
    if (stutter_period_.advance_frame()) {
      if (!stutter_captured_) {
        stutter_captured_ = true;
        stutter_capture_frames_ = stutter_cursor_;
      }
      stutter_cursor_ = 0;
    }
  }
}

void MasterFxChain::process_gate(
    float* left, float* right, std::size_t frames) noexcept {
  if (!active(domain::PerformanceFx::gate)) {
    return;
  }
  const auto threshold =
      static_cast<float>(value(domain::PerformanceFx::gate)) * 0.0007F;
  for (std::size_t frame = 0; frame < frames; ++frame) {
    if (std::abs(left[frame]) < threshold) {
      left[frame] = 0.0F;
    }
    if (std::abs(right[frame]) < threshold) {
      right[frame] = 0.0F;
    }
  }
}

void MasterFxChain::process_reverse(
    float* left, float* right, std::size_t frames) noexcept {
  if (!active(domain::PerformanceFx::reverse)) {
    return;
  }
  const auto setting = value(domain::PerformanceFx::reverse);
  const auto divisor = 8U + (static_cast<std::uint32_t>(setting) * 56U) /
                                 kMasterFxValueMaximum;
  const auto segment = std::max<std::size_t>(
      1, master_fx_bar_frames(sample_rate_, bpm_) / divisor);
  reverse_cursor_ %= segment;
  for (std::size_t frame = 0; frame < frames; ++frame) {
    reverse_left_[reverse_cursor_] = left[frame];
    reverse_right_[reverse_cursor_] = right[frame];
    if (reverse_play_frames_ != 0) {
      const auto reversed =
          reverse_play_frames_ -
          (reverse_cursor_ % reverse_play_frames_) - 1U;
      left[frame] = reverse_play_left_[reversed];
      right[frame] = reverse_play_right_[reversed];
    }
    ++reverse_cursor_;
    if (reverse_cursor_ == segment) {
      reverse_cursor_ = 0;
      reverse_left_.swap(reverse_play_left_);
      reverse_right_.swap(reverse_play_right_);
      reverse_play_frames_ = segment;
    }
  }
}

void MasterFxChain::process_crush(
    float* left, float* right, std::size_t frames) noexcept {
  if (!active(domain::PerformanceFx::crush)) {
    return;
  }
  const auto setting = value(domain::PerformanceFx::crush);
  const auto hold_frames = 1U +
      (static_cast<std::uint32_t>(setting) * 31U) / kMasterFxValueMaximum;
  const auto bits = 16U -
      (static_cast<std::uint32_t>(setting) * 12U) / kMasterFxValueMaximum;
  const auto levels = (1U << (bits - 1U)) - 1U;
  for (std::size_t frame = 0; frame < frames; ++frame) {
    if (crush_phase_ == 0) {
      crush_left_ = quantize(left[frame], levels);
      crush_right_ = quantize(right[frame], levels);
    }
    left[frame] = crush_left_;
    right[frame] = crush_right_;
    crush_phase_ = (crush_phase_ + 1U) % hold_frames;
  }
}

void MasterFxChain::process_cutter(
    float* left, float* right, std::size_t frames) noexcept {
  if (!active(domain::PerformanceFx::cutter)) {
    return;
  }
  const auto division =
      master_fx_cutter_divisor(value(domain::PerformanceFx::cutter));
  if (cutter_period_division_ == 0) {
    cutter_period_.configure(sample_rate_, bpm_, division);
    cutter_period_division_ = division;
  } else if (cutter_period_division_ != division) {
    cutter_period_.set_rate(bpm_, division);
    cutter_period_division_ = division;
  }
  for (std::size_t frame = 0; frame < frames; ++frame) {
    if (cutter_period_.phase_numerator() >=
        cutter_period_.denominator() / 2U) {
      left[frame] = 0.0F;
      right[frame] = 0.0F;
    }
    static_cast<void>(cutter_period_.advance_frame());
  }
}

}  // namespace lmdj::audio
