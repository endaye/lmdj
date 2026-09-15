"""One carrier for the driver's `promotion` step: reviewed dev-promotion PR.

`plan_promotion` validates the dev transition and `apply_promotion` writes the
ledger record plus the evidence document; the reviewed docs PR is the same
witness transport the intent and changelog carriers use. This carrier owns the
commit on canonical `main` (two declared paths only), verifies the committed
ledger records the promotion, and maps the PR sequence to driver observations.
Observation allocates and executes nothing.
"""

from copy import deepcopy
from pathlib import Path

from .intent import _LEDGER_RELATIVE
from .model import canonical_sha256
from .orchestration_driver import Observation


class PromotionStepError(ValueError):
    pass


def _fail(reason):
    raise PromotionStepError(
        f"why: promotion step {reason}; remedy: restore the published release "
        "state and the reviewed promotion without rewriting history or "
        "reopening a merged pull request")


def promotion_operation_id(request_sha256):
    return canonical_sha256({"request": request_sha256, "step": "promotion"})


def evidence_document_relative(spec):
    validate_spec(spec)
    return (f"docs/release-evidence/{spec['tag']}-{spec['to_channel']}"
            "-promotion.md")


_SPEC_KEYS = {"operation_id", "request_sha256", "repository_id", "actor_id",
              "base_revision", "head_sha", "tree_sha", "tag",
              "target_revision", "to_channel", "from_channel",
              "deployment_runs_sha256", "attestation_sha256"}


def validate_spec(spec):
    if type(spec) is not dict or set(spec) != _SPEC_KEYS:
        _fail("scope fields are invalid")
    digests = ("operation_id", "request_sha256", "deployment_runs_sha256",
               "attestation_sha256")
    if not all(isinstance(spec[k], str)
               and __import__("re").fullmatch(r"[0-9a-f]{64}", spec[k])
               for k in digests):
        _fail("scope digests are invalid")
    if spec["operation_id"] != promotion_operation_id(spec["request_sha256"]):
        _fail("operation differs from the original request")
    if not all(isinstance(spec[k], str)
               and __import__("re").fullmatch(r"[0-9a-f]{40}", spec[k])
               for k in ("base_revision", "head_sha", "tree_sha",
                         "target_revision")):
        _fail("scope revisions are invalid")
    if len({spec["base_revision"], spec["head_sha"]}) != 2:
        _fail("base and head identities must be distinct")
    if type(spec["tag"]) is not str or not spec["tag"].startswith("lmdj-v"):
        _fail("tag is invalid")
    if (type(spec["from_channel"]) is not str or not spec["from_channel"]
            or type(spec["to_channel"]) is not str or not spec["to_channel"]
            or spec["from_channel"] == spec["to_channel"]):
        _fail("promotion channels are invalid")
    if type(spec["repository_id"]) is not int or spec["repository_id"] <= 0 \
            or type(spec["actor_id"]) is not int or spec["actor_id"] <= 0:
        _fail("numeric scope identities are invalid")


def pr_document(spec):
    validate_spec(spec)
    document = {"title": f"docs(release): record {spec['tag']} {spec['to_channel']} promotion",
                "body": ("## Reviewed channel promotion\n\n"
                         f"Tag: `{spec['tag']}`\n\n"
                         f"Channel: `{spec['from_channel']}` -> `{spec['to_channel']}`\n\n"
                         f"Candidate target (unchanged): `{spec['target_revision']}`\n\n"
                         f"Deployment runs attestation: `{spec['deployment_runs_sha256']}`\n\n"
                         "Records the reviewed dev promotion in the release-intents "
                         "ledger and adds its evidence document. The target revision, "
                         "snapshot and release evidence stay exactly as published. No "
                         "tag, Release, deployment or publication is claimed by this "
                         "pull request.\n\n"
                         "Version impact: none\n\n"
                         "Reason: release-operation documentation and ledger evidence only.\n\n"
                         "Documentation impact: required\n\n"
                         "Affected portal pages: /versions/"
                         + spec["tag"].removeprefix("lmdj-v") + "/\n\n"
                         f"<!-- lmdj-release-promotion-pr.v1 {canonical_sha256(spec)} -->\n"),
                "head": "docs/release-witness-" + spec["operation_id"], "base": "main",
                "draft": False, "maintainer_can_modify": False}
    if len(document["body"]) > 20000:
        _fail("generated document exceeds the transport bound")
    return document


def _promotion_matches_spec(record, spec):
    """The recorded promotion must be exactly the reviewed frozen one."""
    return (record.get("channel") == spec["to_channel"]
            and record.get("attestation") == "verified"
            and canonical_sha256({"runs": record.get("deployment_runs")})
            == spec["deployment_runs_sha256"])


def _promotion_recorded(rows, spec):
    """True when exactly one row for this tag records this exact promotion."""
    matches = [row for row in rows if row.get("tag") == spec["tag"]]
    if len(matches) != 1:
        _fail("the ledger does not carry exactly one row for this tag")
    promotions = matches[0].get("promotions")
    if not isinstance(promotions, list):
        return False
    return any(isinstance(p, dict) and _promotion_matches_spec(p, spec)
               for p in promotions)


class PromotionCommit:
    """Create the promotion docs commit on an owned worktree at canonical main."""

    def __init__(self, root, repository_root, *, spec, plan, main_tip,
                 author_name, author_email):
        """plan: the trusted PromotionPlan from plan_promotion (frozen input).

        main_tip: zero-argument callable returning the canonical repository's
        current main tip; trusted composition binds the real repository.
        """
        validate_spec(spec)
        if not callable(main_tip):
            _fail("requires the trusted canonical main reader")
        self.root = Path(root).absolute()
        if self.root.resolve() != self.root:
            _fail("worktree root contains a symlink")
        self.repository_root = Path(repository_root).absolute()
        self.spec = deepcopy(spec)
        self.plan = plan
        self.main_tip = main_tip
        self.author = dict(author_name=author_name, author_email=author_email)
        self._workspace = None

    def _git(self, *args):
        from .publication_workspace import PublicationWorkspace, PublicationWorkspaceError
        if self._workspace is None:
            self._workspace = PublicationWorkspace(self.root)
        try:
            return self._workspace.git(*args)
        except PublicationWorkspaceError as error:
            raise PromotionStepError(f"worktree Git is unavailable: {error}") from None

    def _repository_git(self, *args):
        from .publication_workspace import PublicationWorkspace, PublicationWorkspaceError
        repository = PublicationWorkspace(self.repository_root)
        try:
            return repository.git(*args)
        except PublicationWorkspaceError as error:
            raise PromotionStepError(f"repository Git is unavailable: {error}") from None

    def _declared_path(self, path):
        return path in (str(_LEDGER_RELATIVE), evidence_document_relative(self.spec))

    def _stage_declared(self):
        raw = self._git("ls-files", "-m", "-o", "--exclude-standard", "-z")
        changed = [name for name in raw.decode(errors="replace").split("\0") if name]
        unexpected = [name for name in changed if not self._declared_path(name)]
        if unexpected:
            _fail("worktree carries files outside the declared promotion paths: "
                  + unexpected[0])
        for name in changed:
            if not (self.root / name).exists():
                _fail("declared promotion path was deleted from the worktree: " + name)
            self._git("add", "--", name)

    def _apply_plan(self):
        from .promotion import apply_promotion
        apply_promotion(self.root, self.plan, self._policy())

    def _policy(self):
        from .model import load_policy
        return load_policy(self.root / "tools/release/policy.json")

    def _completed(self):
        head = self._git("rev-parse", "HEAD").decode().strip()
        if head == self.spec["base_revision"]:
            return None
        self._git("merge-base", "--is-ancestor", self.spec["base_revision"], head)
        if self._git("status", "--porcelain").strip():
            _fail("existing worktree has uncommitted changes")
        raw = self._git("show", "HEAD:" + str(_LEDGER_RELATIVE)).decode("utf-8")
        import json
        rows = json.loads(raw).get("entries")
        if not isinstance(rows, list) or not _promotion_recorded(rows, self.spec):
            _fail("the committed ledger does not record this promotion")
        self._git("cat-file", "-e",
                  "HEAD:" + evidence_document_relative(self.spec))
        return head

    def completed_head(self):
        if not self.root.exists():
            return None
        return self._completed()

    def commit(self, *, before_write):
        """Create the single promotion docs commit; returns (head_sha, tree_sha).

        `main_tip()` is a zero-argument callable bound by trusted composition
        to the canonical repository's current main tip; the worktree base must
        equal it before any write.
        """
        if not callable(before_write) or not callable(self.main_tip):
            _fail("requires the driver's durable write guard and the main reader")
        main_tip = self.main_tip()
        if main_tip != self.spec["base_revision"]:
            _fail("base revision is not the current canonical main tip; "
                  "re-spec the operation against the merged main")
        if self.root.exists():
            completed = self._completed()
            if completed is not None:
                tree = self._git("rev-parse", "HEAD^{tree}").decode().strip()
                return completed, tree
        before_write()
        if not self.root.exists():
            self._repository_git("worktree", "add", "--detach", str(self.root),
                                 self.spec["base_revision"])
        head = self._git("rev-parse", "HEAD").decode().strip()
        if head != self.spec["base_revision"]:
            _fail("worktree is not at the recorded canonical main tip")
        self._apply_plan()
        self._stage_declared()
        before_write()
        self._git("-c", "user.name=" + self.author["author_name"],
                  "-c", "user.email=" + self.author["author_email"],
                  "commit", "-m",
                  f"docs(release): record {self.spec['tag']} {self.spec['to_channel']} promotion")
        head = self._git("rev-parse", "HEAD").decode().strip()
        tree = self._git("rev-parse", "HEAD^{tree}").decode().strip()
        return head, tree
