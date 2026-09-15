"""Intent carrier part 2: the reviewed docs PR and the driver protocol.

`IntentBranch`/`IntentPullRequest` reuse the witness transport (closed
`docs/release-witness-*` routes) with intent-specific validators and
document; `IntentPrSequence` reuses the existing candidate PR sequence
state machine unchanged. `IntentCarrier` composes the owned docs commit
and the sequence behind the driver's observe/advance contract.
"""

from copy import deepcopy
import re

from .candidate_pr_sequence import CandidatePrSequence
from .evidence_branch import PublicationBranch
from .github_api import GitHubClient
from .intent import (
    IntentCommit,
    IntentError,
    _fail,
    intent_operation_id,
    pr_document,
    validate_spec,
)
from .orchestration_driver import Observation
from .witness_pr import WitnessPullRequest


class IntentBranch(PublicationBranch):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)

    def __init__(self, root, repository, *, token, authorize):
        super().__init__(root, repository, token=token, authorize=authorize)
        self.api = GitHubClient(token=token).witness_pr_request


class IntentPullRequest(WitnessPullRequest):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)


class IntentPrSequence(CandidatePrSequence):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)
    _branch_type, _pr_type = IntentBranch, IntentPullRequest
    _state_file = "intent-pr-sequence.json"
    _schema = "lmdj.intent-pr-sequence.v1"


class IntentCarrier:
    def __init__(self, *, commit, sequence):
        """commit: the owned IntentCommit; sequence: the IntentPrSequence."""
        if type(commit) is not IntentCommit or type(sequence) is not IntentPrSequence:
            _fail("requires the concrete intent commit and intent PR sequence")
        self.commit, self.sequence = commit, sequence
        self._spec = None

    def _spec_for(self, head_sha, tree_sha):
        spec = deepcopy(self.commit.spec)
        return dict(spec, head_sha=head_sha, tree_sha=tree_sha)

    def _recovered_spec(self):
        """Rebuild the PR spec from the durable commit, on every observation.

        A commit that moved (repaired or recreated worktree) must be picked up
        rather than driven against a stale head; a worktree that fails content
        verification raises and the driver reports it as unknown.
        """
        if not self.commit.root.exists():
            return None
        head = self.commit.completed_head()
        if head is None:
            return None
        tree = self.commit._git("rev-parse", "HEAD^{tree}").decode().strip()
        return self._spec_for(head, tree)

    def _verified_evidence(self, merge):
        """A verified merge must expose a real digest; never fabricate one."""
        evidence = merge.get("evidence")
        digest = evidence.get("sha256") if isinstance(evidence, dict) else None
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            _fail("verified merge exposes no evidence digest")
        number = merge.get("merge", {}).get("number", "?")
        return {"sha256": digest, "reference": "intent-pr:" + str(number)}

    def observe(self, state, operation):
        recovered = self._recovered_spec()
        if recovered is not None:
            self._spec = recovered
        if self._spec is None:
            return Observation("pending")
        result = self.sequence.observe(self._spec, initialize=False)
        if result["status"] == "merged":
            merge = self.sequence.pr.observe_merge(self._spec)
            if merge.get("status") != "verified":
                return Observation("unknown")
            return Observation("verified", self._verified_evidence(merge))
        if result["status"] in ("absent", "pending"):
            return Observation("pending")
        return Observation("unknown" if result["status"] == "unknown" else "conflict")

    def advance(self, state, operation, *, before_write):
        if not callable(before_write):
            _fail("requires the driver's durable write guard")
        head, tree = self.commit.commit(before_write=before_write)
        self._spec = self._spec_for(head, tree)
        result = self.sequence.advance(self._spec, before_write=before_write)
        if result["status"] == "merged":
            merge = self.sequence.pr.observe_merge(self._spec)
            if merge.get("status") != "verified":
                return Observation("unknown")
            return Observation("verified", self._verified_evidence(merge))
        if result["status"] in ("absent", "pending"):
            return Observation("pending")
        return Observation("unknown" if result["status"] == "unknown" else "conflict")
