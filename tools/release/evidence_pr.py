"""Durable exact-head evidence PR effects, composed with trusted release gates.

This internal controller neither pushes a branch nor implements its authority,
Task, review or merged-source gates. Callers must supply those real verifiers;
transport ACKs and persisted status never establish completion.
"""

from copy import deepcopy
import json
import os
import re
import uuid

from .batch_reference import digest, positive, sha
from .github_api import valid_release_pr_document
from .model import canonical_json, canonical_sha256
from .orchestration import RequestJournal, _validate_evidence
from .orchestration_driver import Observation

MAX_STATE_BYTES = 65536


class EvidencePrError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise EvidencePrError(f"why: release evidence PR {reason}; remedy: reconcile the original operation, exact head and live review/protection; never blindly repeat a write")


def validate_spec(spec):
    require(type(spec) is dict and set(spec) == {"operation_id", "request_sha256", "repository_id", "actor_id",
        "base_revision", "head_sha", "tree_sha", "tag", "target_revision", "task_evidence_sha256"}, "scope fields are invalid")
    require(all(digest(spec[k]) for k in ("operation_id", "request_sha256", "task_evidence_sha256"))
        and all(sha(spec[k]) for k in ("base_revision", "head_sha", "tree_sha", "target_revision"))
        and all(positive(spec[k]) for k in ("repository_id", "actor_id"))
        and type(spec["tag"]) is str and re.fullmatch(r"lmdj-v(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}", spec["tag"]), "scope identities are invalid")


def pr_document(spec):
    validate_spec(spec)
    build = spec["tag"].removeprefix("lmdj-v")
    document = {"title": f"docs(release): record {spec['tag']} publication",
        "body": ("## Publication evidence\n\n"
            f"Release: https://github.com/endaye/lmdj/releases/tag/{spec['tag']}\n\n"
            f"Candidate target: `{spec['target_revision']}`\n\n"
            f"Task verification evidence: `{spec['task_evidence_sha256']}`\n\n"
            "Required Task commands (the authority gate must confirm recorded exit 0):\n\n"
            "- `scripts/docs-site.sh check`\n- `python3 tests/build/ci_change_scope_test.py`\n- `git diff --cached --check`\n\n"
            "Records the verified publication and frozen changelog. No tag, Release, deployment or Channel mutation is requested.\n\n"
            "Version impact: none\n\nReason: publication evidence only; no product allocation or snapshot rewrite.\n\n"
            f"Documentation impact: required\n\nAffected portal pages: /releases/ /releases/{build}/\n\n"
            f"<!-- lmdj-release-evidence-pr.v1 {canonical_sha256(spec)} -->\n"),
        "head": "docs/release-evidence-" + spec["operation_id"], "base": "main",
        "draft": False, "maintainer_can_modify": False}
    require(valid_release_pr_document(document), "generated document is outside the transport bounds")
    return document


class EvidencePullRequest:
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)

    def __init__(self, root, *, api, authorize, review, verify_merged):
        """Trusted gates, not values obtained from PR text or a user plugin.

        authorize(spec): revalidate original request, Task commit/proof (including
        actual exit 0 for every command declared in pr_document), canonical
        source and effective protections. review(spec, pr): exact-head eligibility
        PLUS all findings/dispositions, conversations and closing relations.
        verify_merged(spec, pr, review_receipt): actual squash identity/ancestry,
        source facts and historical review proof. A preexisting external merge
        has no controller review receipt and needs independent historical proof.
        The two observation gates return Observation, never a bare boolean.
        """
        self.root, self.api = root, api
        self.authorize, self.review, self.verify_merged = authorize, review, verify_merged

    def _request(self, method, path, document=None):
        try:
            return self.api(method, path, document)
        except Exception:
            raise RuntimeError("release PR API observation unavailable") from None

    def _authorize(self, spec, *, branch=True):
        try:
            self.authorize(deepcopy(spec))
        except Exception:
            raise RuntimeError("release PR authority unavailable") from None
        repo, actor, main = (self._request("GET", path) for path in ("", "/user", "/branches/main"))
        require(type(repo) is dict and type(repo.get("id")) is int and repo["id"] == spec["repository_id"]
                and repo.get("full_name") == "endaye/lmdj", "repository identity changed")
        require(type(actor) is dict and type(actor.get("id")) is int and actor["id"] == spec["actor_id"], "authenticated actor changed")
        require(type(main) is dict and main.get("name") == "main" and main.get("protected") is True
                and type(main.get("commit")) is dict and sha(main["commit"].get("sha")), "main is not protected/readable")
        if branch:
            ref = self._request("GET", "/git/ref/heads/" + self._document(spec)["head"])
            require(type(ref) is dict and ref.get("ref") == "refs/heads/" + self._document(spec)["head"]
                and type(ref.get("object")) is dict and ref["object"].get("type") == "commit"
                and ref["object"].get("sha") == spec["head_sha"], "remote Task branch differs")

    def _pr(self, spec, number):
        row = self._request("GET", f"/pulls/{number}")
        document = self._document(spec)
        require(type(row) is dict and type(row.get("number")) is int and row["number"] == number
                and positive(row.get("id")) and row.get("html_url") == f"https://github.com/endaye/lmdj/pull/{number}"
                and type(row.get("user")) is dict and type(row["user"].get("id")) is int
                and row["user"]["id"] == spec["actor_id"]
                and row.get("title") == document["title"] and row.get("body") == document["body"]
                and row.get("draft") is False and type(row.get("merged")) is bool, "PR origin, content or state conflicts")
        for side, ref in (("head", document["head"]), ("base", "main")):
            part = row.get(side)
            require(type(part) is dict and part.get("ref") == ref and type(part.get("repo")) is dict
                    and type(part["repo"].get("id")) is int and part["repo"]["id"] == spec["repository_id"]
                    and part["repo"].get("full_name") == "endaye/lmdj", "PR repository or branch changed")
        require(row["head"].get("sha") == spec["head_sha"], "PR head changed")
        require((row["merged"] and row.get("state") == "closed" and sha(row.get("merge_commit_sha"))
                 and type(row.get("merged_at")) is str and row["merged_at"])
                or (not row["merged"] and row.get("state") == "open" and row.get("merged_at") is None),
                "PR closed without verified merge")
        return row

    def _find(self, spec):
        result, ids = [], set()
        for page in range(1, 101):
            rows = self._request("GET", f"/pulls?state=all&head=endaye:{self._document(spec)['head']}&base=main&per_page=100&page={page}")
            require(type(rows) is list and len(rows) <= 100, "PR inventory is invalid")
            for row in rows:
                require(type(row) is dict and positive(row.get("number")) and row["number"] not in ids, "PR inventory repeats or lacks identity")
                ids.add(row["number"])
                require(len(ids) <= 1, "operation has multiple PRs")
                result.append(self._pr(spec, row["number"]))
            if len(rows) < 100:
                require(len(result) <= 1, "operation has multiple PRs")
                return result[0] if result else None
        raise EvidencePrError("why: release PR inventory exceeds its read budget; remedy: reconcile the exact operation without another POST")

    @staticmethod
    def _state(journal, spec):
        journal._active()
        try:
            fd = os.open("pr-state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=journal.directory)
        except FileNotFoundError:
            try:
                marker = os.open("pr-enrolled", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=journal.directory)
            except FileExistsError:
                raise EvidencePrError("why: enrolled PR state is missing; remedy: retain the journal and reconcile the original operation without another write") from None
            try:
                os.fsync(marker)
                os.fsync(journal.directory)
            finally:
                os.close(marker)
            initial = {"schema": "lmdj.evidence-pr-state.v1", "spec": spec, "create_intent": False,
                    "number": None, "merge_intent": False, "merge_sha": None, "review_evidence": None}
            EvidencePullRequest._save(journal, initial)
            return initial
        try:
            journal._private(fd)
            try:
                marker = os.open("pr-enrolled", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=journal.directory)
            except FileNotFoundError:
                raise EvidencePrError("why: PR enrollment marker is missing; remedy: retain the original journal and reconcile its enrollment") from None
            try:
                journal._private(marker)
                require(os.fstat(marker).st_size == 0, "enrollment marker is corrupt")
            finally:
                os.close(marker)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_STATE_BYTES + 1)
            value = json.loads(raw)
            require(type(value) is dict and set(value) == {"schema", "spec", "create_intent", "number", "merge_intent", "merge_sha", "review_evidence"}
                    and value["schema"] == "lmdj.evidence-pr-state.v1" and canonical_json(value["spec"]) == canonical_json(spec)
                    and canonical_json(value) == raw and len(raw) <= MAX_STATE_BYTES
                    and type(value["create_intent"]) is bool and type(value["merge_intent"]) is bool
                    and (value["number"] is None or positive(value["number"]))
                    and (value["merge_sha"] is None or sha(value["merge_sha"]))
                    and (not value["merge_intent"] or (value["number"] is not None and value["review_evidence"] is not None))
                    and (value["merge_intent"] or value["review_evidence"] is None)
                    and (value["merge_sha"] is None or value["number"] is not None), "durable state is corrupt or rebound")
            if value["review_evidence"] is not None:
                _validate_evidence(value["review_evidence"])
            return value
        except (ValueError, UnicodeError) as error:
            if isinstance(error, EvidencePrError):
                raise
            raise EvidencePrError("why: release PR durable state is malformed; remedy: retain the corrupt state and reconcile the original operation") from None
        finally:
            os.close(fd)

    @staticmethod
    def _save(journal, state):
        journal._active()
        encoded = canonical_json(state)
        require(len(encoded) <= MAX_STATE_BYTES, "durable state exceeds its read bound")
        temporary = ".pr-pending-" + uuid.uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=journal.directory)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(fd)
            journal._active()
            os.replace(temporary, "pr-state.json", src_dir_fd=journal.directory, dst_dir_fd=journal.directory)
            os.fsync(journal.directory)
        finally:
            os.close(fd)

    @staticmethod
    def _gate(callback, spec, row, *receipts):
        try:
            result = callback(deepcopy(spec), deepcopy(row), *deepcopy(receipts))
        except Exception:
            raise RuntimeError("release PR verification unavailable") from None
        require(type(result) is Observation, "trusted gate returned an invalid observation")
        result.validate()
        return result

    def observe(self, spec, *, initialize=False):
        """GET-only far-side observation; optional private-state initialization.

        The parent may initialize before recording its own intent. Thereafter
        missing child storage is unknown, never evidence that a POST/PUT was
        not attempted. No observation creates a PR or requests its merge.
        """
        return self._observe(spec, initialize=initialize, include_merge=False)

    def observe_merge(self, spec):
        """GET-only actual merge identity, gated identically to observation.

        Consumers must not recover a candidate target by parsing the gate's
        opaque evidence reference or by treating the branch head as its squash.
        No enrollment is performed and unverified results expose no merge facts.
        """
        result = self._observe(spec, initialize=False, include_merge=True)
        return dict(result, merge=result.get("merge"))

    def _observe(self, spec, *, initialize, include_merge):
        self._validate_spec(spec)
        require(type(initialize) is bool, "initialization mode is invalid")
        spec = deepcopy(spec)
        self._document(spec)  # Deterministic local refusal must precede durable intent.
        with RequestJournal(self.root) as journal:
            try:
                self._authorize(spec, branch=False)
                try:
                    os.stat("pr-state.json", dir_fd=journal.directory, follow_symlinks=False)
                except FileNotFoundError:
                    if not initialize:
                        return {"status": "unknown", "evidence": None}
                state = self._state(journal, spec)
                if initialize:
                    self._save(journal, state)
                row = self._pr(spec, state["number"]) if state["number"] else self._find(spec)
                if row is None:
                    return {"status": "unknown" if state["create_intent"] else "absent", "evidence": None}
                if not row["merged"]:
                    return {"status": "unknown" if state["merge_intent"] else "pending", "evidence": None}
                gate = self._gate(self.verify_merged, spec, row, state["review_evidence"])
                if gate.status != "verified":
                    return {"status": gate.status, "evidence": None}
                self._authorize(spec, branch=False)
                latest = self._pr(spec, row["number"])
                require(latest["merged"] and latest["id"] == row["id"]
                        and latest["number"] == row["number"]
                        and latest["merge_commit_sha"] == row["merge_commit_sha"]
                        and state["merge_sha"] in (None, latest["merge_commit_sha"]), "merged identity changed during observation")
                journal._active()
                require(self._state(journal, spec) == state, "PR state changed during observation")
                result = {"status": "verified", "evidence": gate.evidence}
                if include_merge:
                    result["merge"] = {"id":latest["id"], "number":latest["number"],
                        "head_sha":spec["head_sha"], "merge_sha":latest["merge_commit_sha"]}
                return result
            except EvidencePrError:
                raise
            except Exception:
                return {"status": "unknown", "evidence": None}

    @staticmethod
    def _before_write(callback):
        if callback is not None:
            try:
                callback()
            except Exception:
                # Even a callback using our own error type is untrusted text.
                raise RuntimeError("release PR parent guard unavailable") from None

    def advance(self, spec, *, require_initialized=False, before_write=None):
        self._validate_spec(spec)
        require(type(require_initialized) is bool, "initialization requirement is invalid")
        require(before_write is None or callable(before_write), "final parent guard is invalid")
        spec = deepcopy(spec)
        self._document(spec)  # Both entry points preflight before any enrollment.
        with RequestJournal(self.root) as journal:
            if require_initialized:
                try:
                    os.stat("pr-state.json", dir_fd=journal.directory, follow_symlinks=False)
                except FileNotFoundError:
                    return {"status": "unknown", "evidence": None}
            state = self._state(journal, spec)
            def result(status, evidence=None):
                return {"status": status, "operation_id": spec["operation_id"], "number": state["number"],
                        "head_sha": spec["head_sha"], "merge_sha": state["merge_sha"], "evidence": evidence}
            try:
                # A merged branch may have been automatically deleted by GitHub;
                # verify the actual merged source, not continued branch existence.
                self._authorize(spec, branch=False)
                self._save(journal, state)
                row = self._pr(spec, state["number"]) if state["number"] else self._find(spec)
                if row is None:
                    if state["create_intent"]:
                        return result("unknown-create")
                    self._authorize(spec)
                    state["create_intent"] = True
                    self._save(journal, state)
                    self._authorize(spec)
                    self._before_write(before_write)
                    journal._active()
                    try:
                        self._request("POST", "/pulls", self._document(spec))
                    except Exception:
                        pass  # ACK or error is not proof; never repeat the POST.
                    row = self._find(spec)
                    if row is None:
                        return result("unknown-create")
                state["number"] = row["number"]
                self._save(journal, state)
                if not row["merged"]:
                    if state["merge_intent"]:
                        return result("unknown-merge")
                    self._authorize(spec)
                    gate = self._gate(self.review, spec, row)
                    if gate.status != "verified":
                        return result("review-" + gate.status)
                    row = self._pr(spec, state["number"])
                    if not row["merged"] and row.get("mergeable") is None:
                        return result("mergeability-pending")
                    require(not row["merged"] and row.get("mergeable") is True, "PR is not currently conflict-free")
                    self._authorize(spec)
                    # Gate is re-observed immediately before recording write intent.
                    gate = self._gate(self.review, spec, row)
                    if gate.status != "verified":
                        return result("review-" + gate.status)
                    state["merge_intent"] = True
                    state["review_evidence"] = deepcopy(gate.evidence)
                    self._save(journal, state)
                    self._authorize(spec)
                    row = self._pr(spec, state["number"])
                    require(not row["merged"] and row.get("mergeable") is True, "PR changed at the merge write boundary")
                    self._before_write(before_write)
                    journal._active()
                    try:
                        self._request("PUT", f"/pulls/{row['number']}/merge", {"sha": spec["head_sha"], "merge_method": "squash"})
                    except Exception:
                        pass
                    row = self._pr(spec, state["number"])
                    if not row["merged"]:
                        return result("unknown-merge")
                gate = self._gate(self.verify_merged, spec, row, state["review_evidence"])
                if gate.status != "verified":
                    return result("merged-source-" + gate.status)
                self._authorize(spec, branch=False)
                latest = self._pr(spec, state["number"])
                require(latest["merged"] and latest["merge_commit_sha"] == row["merge_commit_sha"], "merged identity changed")
                require(state["merge_sha"] in (None, latest["merge_commit_sha"]), "saved merge identity changed")
                state["merge_sha"] = latest["merge_commit_sha"]
                self._save(journal, state)
                return result("verified", gate.evidence)
            except EvidencePrError:
                raise
            except Exception:
                # Never serialize arbitrary GitHub, authority or verifier errors.
                return result("unavailable")
