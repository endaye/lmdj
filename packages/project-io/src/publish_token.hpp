#pragma once

namespace lmdj::project_io::detail {

struct PublishToken {
  void* context = nullptr;
  bool (*claim)(void* context) noexcept = nullptr;
  void (*commit)(void* context) noexcept = nullptr;
  void (*abort)(void* context) noexcept = nullptr;
};

inline thread_local const PublishToken* active_publish_token = nullptr;

class PublishTokenScope final {
 public:
  explicit PublishTokenScope(const PublishToken& token) noexcept
      : previous_(active_publish_token) {
    active_publish_token = &token;
  }

  ~PublishTokenScope() { active_publish_token = previous_; }

  PublishTokenScope(const PublishTokenScope&) = delete;
  PublishTokenScope& operator=(const PublishTokenScope&) = delete;

 private:
  const PublishToken* previous_;
};

inline bool claim_publish() noexcept {
  return active_publish_token == nullptr ||
         active_publish_token->claim == nullptr ||
         active_publish_token->claim(active_publish_token->context);
}

inline void commit_publish() noexcept {
  if (active_publish_token != nullptr &&
      active_publish_token->commit != nullptr) {
    active_publish_token->commit(active_publish_token->context);
  }
}

inline void abort_publish() noexcept {
  if (active_publish_token != nullptr &&
      active_publish_token->abort != nullptr) {
    active_publish_token->abort(active_publish_token->context);
  }
}

}  // namespace lmdj::project_io::detail
