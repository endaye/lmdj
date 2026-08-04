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

}  // namespace lmdj::facade::detail
