#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <type_traits>
#include <vector>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::audio {

inline constexpr std::uint16_t kMasterFxValueMaximum = 1'000;
inline constexpr std::array<domain::PerformanceFx, 8> kFxChainOrder{
    domain::PerformanceFx::filter,
    domain::PerformanceFx::delay,
    domain::PerformanceFx::reverb,
    domain::PerformanceFx::stutter,
    domain::PerformanceFx::gate,
    domain::PerformanceFx::reverse,
    domain::PerformanceFx::crush,
    domain::PerformanceFx::cutter,
};

constexpr std::uint32_t master_fx_bar_frames(
    std::uint32_t sample_rate, std::uint16_t bpm) noexcept {
  return bpm == 0
             ? 0
             : static_cast<std::uint32_t>(
                   (static_cast<std::uint64_t>(sample_rate) * 240U) / bpm);
}

constexpr std::uint32_t master_fx_stutter_divisor(
    std::uint16_t value) noexcept {
  constexpr std::array<std::uint32_t, 6> divisors{2, 4, 8, 16, 32, 64};
  const auto bounded = value > kMasterFxValueMaximum
                           ? kMasterFxValueMaximum
                           : value;
  return divisors[(static_cast<std::uint32_t>(bounded) * 5U) /
                  kMasterFxValueMaximum];
}

constexpr std::uint32_t master_fx_cutter_divisor(
    std::uint16_t value) noexcept {
  constexpr std::array<std::uint32_t, 7> divisors{1, 2, 4, 8, 16, 32, 64};
  const auto bounded = value > kMasterFxValueMaximum
                           ? kMasterFxValueMaximum
                           : value;
  return divisors[(static_cast<std::uint32_t>(bounded) * 6U) /
                  kMasterFxValueMaximum];
}

constexpr std::uint32_t master_fx_stutter_frames(
    std::uint32_t sample_rate,
    std::uint16_t bpm,
    std::uint16_t value) noexcept {
  return master_fx_bar_frames(sample_rate, bpm) /
         master_fx_stutter_divisor(value);
}

constexpr std::uint32_t master_fx_cutter_frames(
    std::uint32_t sample_rate,
    std::uint16_t bpm,
    std::uint16_t value) noexcept {
  return master_fx_bar_frames(sample_rate, bpm) /
         master_fx_cutter_divisor(value);
}

constexpr std::uint32_t master_fx_delay_frames(
    std::uint32_t sample_rate,
    std::uint16_t bpm,
    std::uint16_t value) noexcept {
  const auto bounded = value > kMasterFxValueMaximum
                           ? kMasterFxValueMaximum
                           : value;
  const auto divisor = 1U +
      (static_cast<std::uint32_t>(bounded) * 15U) /
          kMasterFxValueMaximum;
  return master_fx_bar_frames(sample_rate, bpm) / divisor;
}

namespace detail {

class MasterFxPeriodAccumulator final {
 public:
  void configure(
      std::uint32_t sample_rate,
      std::uint16_t bpm,
      std::uint32_t division) noexcept {
    denominator_ = static_cast<std::uint64_t>(sample_rate) * 240U;
    phase_numerator_ = 0;
    set_rate(bpm, division);
  }

  void set_rate(std::uint16_t bpm, std::uint32_t division) noexcept {
    rate_numerator_ = static_cast<std::uint64_t>(bpm) * division;
  }

  std::uint32_t next_frames() noexcept {
    if (denominator_ == 0 || rate_numerator_ == 0) {
      return 0;
    }
    const auto remaining = denominator_ - phase_numerator_;
    const auto frames =
        (remaining + rate_numerator_ - 1U) / rate_numerator_;
    phase_numerator_ += frames * rate_numerator_ - denominator_;
    return static_cast<std::uint32_t>(frames);
  }

  bool advance_frame() noexcept {
    phase_numerator_ += rate_numerator_;
    if (phase_numerator_ < denominator_) {
      return false;
    }
    phase_numerator_ -= denominator_;
    return true;
  }

  std::uint64_t phase_numerator() const noexcept {
    return phase_numerator_;
  }

  std::uint64_t denominator() const noexcept { return denominator_; }

 private:
  std::uint64_t denominator_ = 0;
  std::uint64_t rate_numerator_ = 0;
  std::uint64_t phase_numerator_ = 0;
};

}  // namespace detail

enum class FxGestureKind : std::uint8_t {
  engage,
  move,
  release,
  hold_on,
  hold_off,
};

struct FxGesture {
  FxGestureKind kind;
  domain::PerformanceFx fx;
  std::uint16_t value;
};
static_assert(std::is_trivially_copyable_v<FxGesture>);

enum class FxEnqueueResult : std::uint8_t {
  accepted,
  invalid_fx,
  invalid_value,
  invalid_bpm,
  not_prepared,
  not_running,
  queue_full,
};

struct MasterFxTelemetry {
  std::uint64_t enqueued_gestures;
  std::uint64_t dequeued_gestures;
  std::uint64_t queued_gestures;
  std::uint64_t queue_drops;
  std::uint64_t processed_frames;
  std::uint64_t enqueued_tempo_updates;
  std::uint64_t applied_tempo_updates;
  std::uint16_t current_bpm;
};

struct MasterFxPreparation {
  std::uint32_t sample_rate;
  std::uint16_t bpm;
};

class MasterFxChain final {
 public:
  foundation::Result<void> prepare(MasterFxPreparation preparation);
  void reset() noexcept;
  bool set_bpm(std::uint16_t bpm) noexcept;
  bool apply_gesture(FxGesture gesture) noexcept;
  void process(float* left, float* right, std::size_t frames) noexcept;
  bool prepared() const noexcept { return prepared_; }
  std::uint16_t bpm() const noexcept { return bpm_; }

 private:
  struct EffectState {
    std::uint16_t value = 0;
    bool engaged = false;
    bool frozen = false;
  };

  bool active(domain::PerformanceFx fx) const noexcept;
  std::uint16_t value(domain::PerformanceFx fx) const noexcept;
  void reset_effect(domain::PerformanceFx fx) noexcept;
  void process_filter(float* left, float* right, std::size_t frames) noexcept;
  void process_delay(float* left, float* right, std::size_t frames) noexcept;
  void process_reverb(float* left, float* right, std::size_t frames) noexcept;
  void process_stutter(float* left, float* right, std::size_t frames) noexcept;
  void process_gate(float* left, float* right, std::size_t frames) noexcept;
  void process_reverse(float* left, float* right, std::size_t frames) noexcept;
  void process_crush(float* left, float* right, std::size_t frames) noexcept;
  void process_cutter(float* left, float* right, std::size_t frames) noexcept;

  std::array<EffectState, kFxChainOrder.size()> effects_{};
  bool hold_ = false;
  bool prepared_ = false;
  std::uint32_t sample_rate_ = 0;
  std::uint16_t bpm_ = 0;

  float filter_low_left_ = 0.0F;
  float filter_low_right_ = 0.0F;
  float filter_band_left_ = 0.0F;
  float filter_band_right_ = 0.0F;

  std::vector<float> delay_left_;
  std::vector<float> delay_right_;
  std::vector<float> delay_play_left_;
  std::vector<float> delay_play_right_;
  std::size_t delay_cursor_ = 0;
  std::size_t delay_play_frames_ = 0;
  detail::MasterFxPeriodAccumulator delay_period_;
  std::uint32_t delay_period_division_ = 0;

  std::vector<float> reverb_left_;
  std::vector<float> reverb_right_;
  std::size_t reverb_cursor_ = 0;
  std::size_t reverb_valid_frames_ = 0;

  std::vector<float> stutter_left_;
  std::vector<float> stutter_right_;
  std::size_t stutter_cursor_ = 0;
  bool stutter_captured_ = false;
  std::size_t stutter_capture_frames_ = 0;
  detail::MasterFxPeriodAccumulator stutter_period_;
  std::uint32_t stutter_period_division_ = 0;

  std::vector<float> reverse_left_;
  std::vector<float> reverse_right_;
  std::vector<float> reverse_play_left_;
  std::vector<float> reverse_play_right_;
  std::size_t reverse_cursor_ = 0;
  std::size_t reverse_play_frames_ = 0;

  std::uint32_t crush_phase_ = 0;
  float crush_left_ = 0.0F;
  float crush_right_ = 0.0F;
  detail::MasterFxPeriodAccumulator cutter_period_;
  std::uint32_t cutter_period_division_ = 0;
};

}  // namespace lmdj::audio
