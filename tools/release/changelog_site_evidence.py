"""Authenticate retained Git-triggered Portal evidence, not current live state.

Trusted repository/workflow IDs and minimum producer revision come from the
controller's reviewed configuration, never the artifact. No target code runs.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from .batch_reference import positive, sha, digest
from .changelog_site import LEDGER, PUBLICATIONS, project
from .model import Disposition, canonical_json, load_ledger_document

WORKFLOW = ".github/workflows/deploy-cloudflare-portal.yml"
ORIGIN = "https://docs.lmdj.workers.dev"
MAX_BYTES = 2 * 1024 * 1024


class SiteEvidenceError(ValueError):
    def __init__(self, why, code="conflict"):
        self.code = code
        super().__init__(f"why: changelog site evidence {why}; remedy: reconcile the exact reviewed publication PR and authenticated Portal deployment; do not fabricate a successful receipt")


def require(value, why, code="conflict"):
    if not value:
        raise SiteEvidenceError(why, code)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON repeats a field")
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: require(False, "JSON contains a nonfinite number"))
    except (ValueError, UnicodeError):
        raise SiteEvidenceError("JSON is malformed") from None


class ChangelogSiteEvidenceConsumer:
    def __init__(self, *, api_get, git_root, policy, repository_id, workflow_id, producer_revision, now=None):
        require(positive(repository_id) and positive(workflow_id) and sha(producer_revision), "trusted configuration is invalid")
        require(policy.repository == "endaye/lmdj" and policy.branch == "main", "repository policy is not canonical")
        self.api_get, self.root, self.policy = api_get, Path(git_root), policy
        self.repository_id, self.workflow_id, self.producer = repository_id, workflow_id, producer_revision
        self._fixed_now = now
        require(isinstance(self.now, datetime) and self.now.tzinfo is not None, "clock is not timezone-aware")

    @property
    def now(self):
        return self._fixed_now if self._fixed_now is not None else datetime.now(timezone.utc)

    def get(self, suffix, *, raw=False):
        try:
            return self.api_get("/repos/endaye/lmdj" + suffix, raw=raw)
        except Exception:
            raise SiteEvidenceError("API observation is unavailable", "unverifiable") from None

    def git(self, *args):
        env = {key: value for key, value in os.environ.items() if key in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE=os.devnull,
                   GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", LC_ALL="C")
        try:
            result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, env=env, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise SiteEvidenceError("Git provenance is unavailable", "unverifiable") from None
        require(result.returncode == 0, "Git provenance cannot be verified", "unverifiable")
        return result.stdout

    def pages(self, suffix, key):
        rows, total, seen = [], None, set()
        for page in range(1, 101):
            document = self.get(f"{suffix}?per_page=100&page={page}")
            require(type(document) is dict and type(document.get("total_count")) is int
                    and 0 <= document["total_count"] <= 10000 and type(document.get(key)) is list, "API inventory is invalid")
            require(total is None or total == document["total_count"], "API inventory changed")
            total = document["total_count"]
            items = document[key]
            require(len(items) <= 100, "API page exceeds its bound")
            for item in items:
                require(type(item) is dict and positive(item.get("id")) and item["id"] not in seen, "API inventory identities conflict")
                seen.add(item["id"])
            rows.extend(items)
            require(len(rows) <= total, "API inventory exceeds its total")
            if len(rows) == total:
                return rows
            require(len(items) == 100, "API inventory ended prematurely")
        raise SiteEvidenceError("API pagination budget exhausted", "unverifiable")

    def run(self, run_id, source):
        latest = self.get(f"/actions/runs/{run_id}")
        attempt = self.get(f"/actions/runs/{run_id}/attempts/1")
        expected = {"id": run_id, "run_attempt": 1, "workflow_id": self.workflow_id,
                    "path": WORKFLOW, "head_sha": source, "head_branch": "main", "event": "push"}
        for row in (latest, attempt):
            require(type(row) is dict and all(type(row.get(k)) is type(v) and row[k] == v for k, v in expected.items()), "run is not the exact successful first-attempt main push")
            for key in ("repository", "head_repository"):
                repo = row.get(key)
                require(type(repo) is dict and type(repo.get("id")) is int and repo["id"] == self.repository_id
                        and repo.get("full_name") == "endaye/lmdj", "run repository identity conflicts")
            require(row.get("status") in ("queued", "in_progress", "waiting", "pending", "requested", "completed"), "run status is invalid")
            require(row["status"] == "completed", "run is not yet terminal", "pending")
            require(row.get("conclusion") == "success", "run did not complete successfully")

    def main(self):
        main = self.get("/branches/main")
        require(type(main) is dict and main.get("name") == "main" and main.get("protected") is True
                and type(main.get("commit")) is dict and sha(main["commit"].get("sha")), "canonical main is not protected or readable")
        return main["commit"]["sha"]

    def verify(self, *, tag, run_id, source_revision, publication_record):
        require(positive(run_id) and sha(source_revision), "requested run or source is invalid")
        main = self.main()
        workflow = self.get("/actions/workflows/deploy-cloudflare-portal.yml")
        require(type(workflow) is dict and type(workflow.get("id")) is int and workflow["id"] == self.workflow_id
                and workflow.get("path") == WORKFLOW and workflow.get("state") == "active", "workflow identity is not trusted")
        require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false", "history is shallow", "unverifiable")
        for revision in (self.producer, source_revision, main):
            require(self.git("cat-file", "-t", revision).strip() == b"commit", "source identity is not a commit")
        self.git("merge-base", "--is-ancestor", self.producer, source_revision)
        self.git("merge-base", "--is-ancestor", source_revision, main)
        ledger = load_ledger_document(_json(self.git("cat-file", "blob", source_revision + ":" + LEDGER)), self.policy)
        publications = _json(self.git("cat-file", "blob", source_revision + ":" + PUBLICATIONS))
        intent = ledger.intent_for_tag(tag)
        require(intent is not None and intent.disposition is Disposition.PUBLISHED and intent.changelog is not None, "source lacks the published frozen intent")
        self.git("merge-base", "--is-ancestor", intent.target_revision, source_revision)
        require(type(publication_record) is dict and publication_record.get("tag") == tag, "requested publication is invalid")
        expected_pages = {"/releases/" if page["file"].endswith("/index.mdx") else "/releases/" + Path(page["file"]).stem + "/":
                          hashlib.sha256(page["content"].encode()).hexdigest() for page in project(ledger, publications)}
        records = [record for record in publications["entries"] if record["tag"] == tag]
        require(len(records) == 1 and canonical_json(records[0]) == canonical_json(publication_record), "source publication differs from the verified Release")
        self.run(run_id, source_revision)
        jobs = self.pages(f"/actions/runs/{run_id}/attempts/1/jobs", "jobs")
        require(len(jobs) == 1, "deployment job inventory is not exact")
        job = jobs[0]
        require(job.get("name") == "deploy" and type(job.get("run_id")) is int and job["run_id"] == run_id
                and type(job.get("run_attempt")) is int and job["run_attempt"] == 1 and job.get("head_sha") == source_revision
                and job.get("status") == "completed" and job.get("conclusion") == "success", "deployment job did not succeed for the exact attempt")
        steps = job.get("steps")
        require(type(steps) is list and all(type(step) is dict for step in steps), "deployment steps are unavailable")
        for name in ("Build and verify the Git source", "Verify version Preview and publish the same version", "Retain deployment and recovery observations"):
            matches = [step for step in steps if step.get("name") == name]
            require(len(matches) == 1 and matches[0].get("status") == "completed" and matches[0].get("conclusion") == "success", "required deployment step did not pass")
        artifacts = self.pages(f"/actions/runs/{run_id}/artifacts", "artifacts")
        matches = [item for item in artifacts if item.get("name") == "cloudflare-portal-" + source_revision]
        require(len(matches) == 1, "artifact is absent or ambiguous", "unverifiable")
        artifact = matches[0]
        require(artifact.get("expired") is False, "artifact expired", "unverifiable")
        try:
            expires = datetime.strptime(artifact["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            raise SiteEvidenceError("artifact expiry is invalid") from None
        require(expires > self.now, "artifact retention elapsed", "unverifiable")
        origin = artifact.get("workflow_run")
        require(type(origin) is dict and all(type(origin.get(k)) is int and origin[k] == v for k, v in {
            "id": run_id, "repository_id": self.repository_id, "head_repository_id": self.repository_id}.items())
                and origin.get("head_sha") == source_revision and origin.get("head_branch") == "main", "artifact origin conflicts")
        require(type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= MAX_BYTES, "artifact is oversized")
        raw = self.get(f"/actions/artifacts/{artifact['id']}/zip", raw=True)
        require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "artifact transfer is oversized or invalid")
        require(artifact.get("digest") == "sha256:" + hashlib.sha256(raw).hexdigest(), "artifact transfer digest conflicts")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = archive.infolist()
                require(len(members) == 1 and members[0].filename == f"cloudflare-portal-{run_id}.json"
                        and not members[0].is_dir() and members[0].file_size <= MAX_BYTES
                        and (members[0].external_attr >> 16) & 0o170000 != 0o120000, "artifact member identity or size is unsafe")
                require(members[0].compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "artifact compression does not support bounded decoding")
                with archive.open(members[0]) as member:
                    payload = member.read(MAX_BYTES + 1)
                require(len(payload) <= MAX_BYTES, "artifact decoded payload is oversized")
        except (zipfile.BadZipFile, OSError, RuntimeError):
            raise SiteEvidenceError("artifact ZIP is unreadable") from None
        document = _json(payload)
        require(type(document) is dict and set(document) == {"git_revision", "worker", "status", "prior", "prior_route", "version_id", "preview", "production"}
                and document["git_revision"] == source_revision and document["worker"] == "docs" and document["status"] == "passed", "deployment did not pass for the source and Worker")
        version = document["version_id"]
        require(type(version) is str and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", version), "Worker version is invalid")
        content = {}
        for stage, url in (("preview", f"https://{version[:8]}-docs.lmdj.workers.dev"), ("production", ORIGIN)):
            section = document[stage]
            require(type(section) is dict and set(section) == {"url", "status", "changelogs"} and section["url"] == url
                    and section["status"] == "passed", "site observation is missing or belongs to another URL")
            receipt = section["changelogs"]
            require(type(receipt) is dict and set(receipt) == {"schema", "revision", "pages"}
                    and receipt["schema"] == "lmdj.release-changelog-smoke.v1" and receipt["revision"] == source_revision
                    and type(receipt["pages"]) is list, "page receipt identity is invalid")
            seen = set()
            for page in receipt["pages"]:
                require(type(page) is dict and set(page) == {"route", "url", "source_sha256", "content_sha256", "response_sha256", "response_bytes"}, "page fields are invalid")
                route = page["route"]
                require(type(route) is str and route in expected_pages and route not in seen, "page inventory is duplicate or foreign")
                seen.add(route)
                require(page["url"] == url + route and page["source_sha256"] == expected_pages[route]
                        and digest(page["content_sha256"]) and digest(page["response_sha256"])
                        and type(page["response_bytes"]) is int and 0 < page["response_bytes"] <= 8 * 1024 * 1024, "page identity, source or response conflicts")
                require(stage == "preview" or content[route] == page["content_sha256"], "Preview and production content differ")
                content[route] = page["content_sha256"]
            require(seen == set(expected_pages), "receipt omits a required release page")
        self.run(run_id, source_revision)
        self.git("merge-base", "--is-ancestor", source_revision, self.main())
        require(expires > self.now, "artifact retention elapsed", "unverifiable")
        return {"schema": "lmdj.changelog-site-evidence.v1", "run_id": run_id, "run_attempt": 1,
                "source_revision": source_revision, "tag": tag, "target_revision": intent.target_revision,
                "worker_version": version, "evidence_sha256": hashlib.sha256(payload).hexdigest(),
                "url": ORIGIN + "/releases/" + intent.identity + "/"}
