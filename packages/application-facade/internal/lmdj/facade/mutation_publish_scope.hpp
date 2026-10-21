#pragma once

#include <memory>

namespace lmdj::facade::detail {

struct MutationPublishToken {
  void* context = nullptr;
  bool (*claim)(void* context) noexcept = nullptr;
  void (*commit)(void* context) noexcept = nullptr;
  void (*abort)(void* context) noexcept = nullptr;
  bool (*force_failure)(void* context) noexcept = nullptr;
};

class MutationPublishScope final {
 public:
  explicit MutationPublishScope(const MutationPublishToken& token);
  ~MutationPublishScope();

  MutationPublishScope(const MutationPublishScope&) = delete;
  MutationPublishScope& operator=(const MutationPublishScope&) = delete;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

// Observe an accepted manifest claim without replacing the Host's existing
// publication/cancellation token. No claim on a first failed attempt proves
// that attempt never reached manifest publication; a claim does not prove
// success or failure, including when the platform lost a response after write.
class MutationPublishObservation final {
 public:
  MutationPublishObservation();
  ~MutationPublishObservation();
  bool claimed() const noexcept;
  MutationPublishObservation(const MutationPublishObservation&) = delete;
  MutationPublishObservation& operator=(const MutationPublishObservation&) = delete;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::facade::detail
