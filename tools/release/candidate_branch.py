"""Create-only transport for a verified candidate cut, not a private source.

Trusted authorize must verify original authority, the complete cut Task/source
proof, reservation competition and protected-main policy. The spec is the same
closed candidate identity consumed by CandidatePullRequest. A branch receipt
is not PR review, candidate target, witness, CI or release completion.
"""
from .candidate_pr import pr_document, validate_spec
from .evidence_branch import PublicationBranch
from .github_api import GitHubClient


class CandidateBranch(PublicationBranch):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)

    def __init__(self, root, repository, *, token, authorize):
        super().__init__(root, repository, token=token, authorize=authorize)
        self.api = GitHubClient(token=token).candidate_pr_request
