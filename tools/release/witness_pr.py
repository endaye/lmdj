"""Independent witness branch/PR journey; never a new candidate target.

Trusted gates must authenticate the actual completed CandidateWitnessTask,
original source/receipt/history and Task command evidence, plus current request
authority and protection. Review and merged-source gates retain the complete
EvidencePullRequest contract; an API merge or specification is not proof.
"""
import re

from .batch_reference import digest, positive, sha
from .candidate_pr_sequence import CandidatePrSequence
from .evidence_branch import PublicationBranch
from .evidence_pr import EvidencePullRequest, require
from .github_api import GitHubClient, valid_witness_pr_document
from .model import canonical_sha256


def validate_spec(spec):
    require(type(spec) is dict and set(spec) == {"operation_id", "request_sha256", "repository_id", "actor_id",
        "base_revision", "head_sha", "tree_sha", "product_build", "target_revision", "source_sha",
        "witness_receipt_sha256", "task_binding_sha256", "task_evidence_sha256", "witness"},
        "witness scope fields are invalid")
    require(all(digest(spec[k]) for k in ("operation_id", "request_sha256", "witness_receipt_sha256",
                                         "task_binding_sha256", "task_evidence_sha256"))
        and all(sha(spec[k]) for k in ("base_revision", "head_sha", "tree_sha", "target_revision", "source_sha"))
        and all(positive(spec[k]) for k in ("repository_id", "actor_id"))
        and type(spec["product_build"]) is str
        and re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.0", spec["product_build"]),
        "witness scope identities are invalid")
    require(spec["operation_id"] == canonical_sha256({"request":spec["request_sha256"], "step":"candidate-witness"}),
            "witness operation differs from the original request")
    require(spec["head_sha"] not in (spec["base_revision"], spec["target_revision"], spec["source_sha"])
            and spec["source_sha"] not in (spec["base_revision"], spec["target_revision"]),
            "witness Task must be distinct from the source and candidate")
    witness = spec["witness"]
    require(type(witness) is dict and set(witness) == {"path", "bytes", "sha256"}
            and witness["path"] == f"apps/architecture-portal/versioned_provenance/version-{spec['product_build']}-squash-witness.json"
            and type(witness["bytes"]) is int and 0 < witness["bytes"] <= 64 * 1024 * 1024
            and digest(witness["sha256"]), "witness artifact identity is invalid")


def pr_document(spec):
    validate_spec(spec)
    build, witness = spec["product_build"], spec["witness"]
    document = {"title":f"docs(release): record {build} squash witness",
        "body":("## Candidate squash witness\n\n"
            f"Product Build: `{build}`\n\nCandidate target (unchanged): `{spec['target_revision']}`\n\n"
            f"Retained source: `{spec['source_sha']}`\n\nWitness: `{witness['path']}`\n\n"
            f"Witness bytes: {witness['bytes']}\n\nWitness SHA-256: `{witness['sha256']}`\n\n"
            f"Verified witness receipt: `{spec['witness_receipt_sha256']}`\n\n"
            f"Independent Task binding: `{spec['task_binding_sha256']}`\n\n"
            f"Task verification evidence: `{spec['task_evidence_sha256']}`\n\n"
            "Required Task commands (the authority gate must confirm recorded exit 0):\n\n"
            "- `scripts/docs-site.sh check`\n- `python3 tests/build/ci_change_scope_test.py`\n- `git diff --cached --check`\n\n"
            "Adds only the exact officially generated and verified witness. Retains the original "
            "candidate target and immutable snapshot. The actual witness squash and bytes must be "
            "verified after merge. No complete-CI pass, releasable intent, tag, Release, deployment "
            "or promotion is claimed.\n\n"
            "Version impact: none\n\nReason: witness evidence only; no new allocation or snapshot rewrite.\n\n"
            f"Documentation impact: required\n\nAffected portal pages: /versions/{build}/\n\n"
            f"<!-- lmdj-release-witness-pr.v1 {canonical_sha256(spec)} -->\n"),
        "head":"docs/release-witness-" + spec["operation_id"], "base":"main",
        "draft":False, "maintainer_can_modify":False}
    require(valid_witness_pr_document(document), "generated witness document is outside the transport bounds")
    return document


class WitnessPullRequest(EvidencePullRequest):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)


class WitnessBranch(PublicationBranch):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)

    def __init__(self, root, repository, *, token, authorize):
        super().__init__(root, repository, token=token, authorize=authorize)
        self.api = GitHubClient(token=token).witness_pr_request


class WitnessPrSequence(CandidatePrSequence):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)
    _branch_type, _pr_type = WitnessBranch, WitnessPullRequest
    _state_file = "witness-pr-sequence.json"
    _schema = "lmdj.witness-pr-sequence.v1"
