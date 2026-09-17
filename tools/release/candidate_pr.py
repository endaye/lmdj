"""Durable candidate PR child, not candidate-step or release completion.

Trusted authority must bind the original request, completed cut Task evidence,
live source/protection and reservation competition. Review includes current-head
findings and conversations. Merged verification must bind the actual squash via
CandidateSourceVerifier and retain historical review evidence; witness remains
a subsequent Task. No head SHA is called a candidate target before squash.
"""
import re

from .batch_reference import digest, positive, sha
from .evidence_pr import EvidencePullRequest, require
from .github_api import valid_candidate_pr_document
from .model import canonical_sha256


def validate_spec(spec):
    require(type(spec) is dict and set(spec) == {"operation_id", "request_sha256", "repository_id", "actor_id",
        "base_revision", "head_sha", "tree_sha", "product_build", "source_sha", "cut_binding_sha256",
        "snapshot_sha256", "task_evidence_sha256"}, "candidate scope fields are invalid")
    require(all(digest(spec[k]) for k in ("operation_id", "request_sha256", "cut_binding_sha256",
                                         "snapshot_sha256", "task_evidence_sha256"))
        and all(sha(spec[k]) for k in ("base_revision", "head_sha", "tree_sha", "source_sha"))
        and all(positive(spec[k]) for k in ("repository_id", "actor_id"))
        and type(spec["product_build"]) is str
        and re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.0", spec["product_build"]),
        "candidate scope identities are invalid")
    require(spec["operation_id"] == canonical_sha256({"request":spec["request_sha256"], "step":"candidate"}),
            "candidate operation differs from the original request")
    require(len({spec["base_revision"], spec["head_sha"], spec["source_sha"]}) == 3,
            "candidate source, base and cut identities must be distinct")


def pr_document(spec):
    validate_spec(spec)
    build = spec["product_build"]
    document = {"title": f"chore(release): allocate {build} candidate",
        "body": ("## Candidate allocation\n\n"
            f"Product Build: `{build}`\n\nOriginal base: `{spec['base_revision']}`\n\n"
            f"Private snapshot source: `{spec['source_sha']}`\n\nCut binding: `{spec['cut_binding_sha256']}`\n\n"
            f"Frozen snapshot: `{spec['snapshot_sha256']}`\n\nTask verification evidence: `{spec['task_evidence_sha256']}`\n\n"
            "Required Task commands (the authority gate must confirm recorded exit 0):\n\n"
            "- `scripts/docs-site.sh check`\n- `python3 tests/build/ci_change_scope_test.py`\n- `git diff --cached --check`\n\n"
            "Allocates only the frozen candidate and its canary documentation snapshot. "
            "The actual protected-main squash SHA must be verified before selecting a candidate target. "
            "Retain the private source for the subsequent official witness Task. "
            "No complete-CI pass, releasable intent, tag, Release, deployment or promotion is claimed.\n\n"
            "Version impact: Product Build allocation\n\nReason: reserve a new BUILD with PATCH 0; no product fixes included.\n\n"
            "Documentation impact: required\n\nAffected portal pages: /operations/version-and-release/\n\n"
            f"Immutable canary snapshot: `/versions/{build}/`\n\n"
            f"<!-- lmdj-release-candidate-pr.v1 {canonical_sha256(spec)} -->\n"),
        "head": "feat/release-candidate-" + spec["operation_id"], "base":"main",
        "draft":False, "maintainer_can_modify":False}
    require(valid_candidate_pr_document(document), "generated candidate document is outside the transport bounds")
    return document


class CandidatePullRequest(EvidencePullRequest):
    """Use only with GitHubClient.candidate_pr_request and trusted gates."""
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)
