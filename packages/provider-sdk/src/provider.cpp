#include <lmdj/provider/provider.hpp>

#include <mutex>
#include <utility>

namespace lmdj::provider {
struct StagingBudget::State {
  std::mutex mutex;
  std::uint64_t maximum;
  std::uint64_t used = 0;
  explicit State(std::uint64_t limit) : maximum(limit) {}
};

StagingBudget::StagingBudget(std::uint64_t maximum_bytes)
    : state_(std::make_shared<State>(maximum_bytes)) {}

foundation::Result<std::shared_ptr<void>> StagingBudget::reserve(
    std::uint64_t bytes) const {
  struct Reservation {
    std::shared_ptr<State> state;
    std::uint64_t amount = 0;
    explicit Reservation(std::shared_ptr<State> owner) : state(std::move(owner)) {}
    ~Reservation() {
      const std::lock_guard lock(state->mutex);
      state->used -= amount;
    }
  };
  auto lease = std::make_shared<Reservation>(state_);
  const std::lock_guard lock(state_->mutex);
  if (bytes > state_->maximum - state_->used) {
    return foundation::Result<std::shared_ptr<void>>::failure({
        foundation::ErrorCode::invalid_argument, "staging budget exhausted",
    });
  }
  lease->amount = bytes;
  state_->used += bytes;
  return foundation::Result<std::shared_ptr<void>>::success(std::move(lease));
}

std::uint64_t StagingBudget::used_bytes() const {
  const std::lock_guard lock(state_->mutex);
  return state_->used;
}

ArtifactBytes::ArtifactBytes(foundation::ArtifactRef reference,
                             std::vector<std::byte> bytes,
                             std::shared_ptr<void> lease)
    : reference_(std::move(reference)), lease_(std::move(lease)),
      bytes_(std::move(bytes)) {}
}  // namespace lmdj::provider
