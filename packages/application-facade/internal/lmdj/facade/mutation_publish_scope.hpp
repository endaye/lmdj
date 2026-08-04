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

}  // namespace lmdj::facade::detail
