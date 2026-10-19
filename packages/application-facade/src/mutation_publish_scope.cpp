#include <lmdj/facade/mutation_publish_scope.hpp>

#include "../../project-io/src/publish_token.hpp"

namespace lmdj::facade::detail {

struct MutationPublishScope::Impl {
  explicit Impl(const MutationPublishToken& facade_token)
      : token{
            facade_token.context,
            facade_token.claim,
            facade_token.commit,
            facade_token.abort,
            facade_token.force_failure,
        },
        scope(token) {}

  project_io::detail::PublishToken token;
  project_io::detail::PublishTokenScope scope;
};

MutationPublishScope::MutationPublishScope(
    const MutationPublishToken& token)
    : impl_(std::make_unique<Impl>(token)) {}

MutationPublishScope::~MutationPublishScope() = default;

struct MutationPublishObservation::Impl {
  const project_io::detail::PublishToken* previous = project_io::detail::active_publish_token;
  bool claimed{};
  static bool claim(void* context) noexcept {
    auto& self = *static_cast<Impl*>(context);
    if (self.previous && self.previous->claim && !self.previous->claim(self.previous->context)) return false;
    self.claimed = true;
    return true;
  }
  static void commit(void* context) noexcept {
    auto& self = *static_cast<Impl*>(context);
    if (self.previous && self.previous->commit) self.previous->commit(self.previous->context);
  }
  static void abort(void* context) noexcept {
    auto& self = *static_cast<Impl*>(context);
    if (self.previous && self.previous->abort) self.previous->abort(self.previous->context);
  }
  static bool force_failure(void* context) noexcept {
    auto& self = *static_cast<Impl*>(context);
    return self.previous && self.previous->force_failure && self.previous->force_failure(self.previous->context);
  }
  project_io::detail::PublishToken token{this, claim, commit, abort, force_failure};
  project_io::detail::PublishTokenScope scope{token};
};

MutationPublishObservation::MutationPublishObservation() : impl_(std::make_unique<Impl>()) {}
MutationPublishObservation::~MutationPublishObservation() = default;
bool MutationPublishObservation::claimed() const noexcept { return impl_->claimed; }

}  // namespace lmdj::facade::detail
