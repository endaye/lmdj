"""Read-only exact-run correlation; no dispatch, retry or effect-success proof."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

from .batch_reference import positive, sha
from .dispatch_receipt import WORKFLOWS, receipt, unique
from .model import canonical_json, canonical_sha256

LIMIT = 2 * 1024 * 1024


class DispatchEvidenceError(ValueError):
    pass


def require(value, why):
    if not value:
        raise DispatchEvidenceError(f"why: dispatch correlation {why}; remedy: reconcile the original exact run and retained artifact; never infer absence, approval or retry permission")


class DispatchEvidenceConsumer:
    def __init__(self, *, api_get, git_root, repository_id, workflow, workflow_id, producer_revision, now=None):
        require(positive(repository_id) and positive(workflow_id) and workflow in WORKFLOWS
                and sha(producer_revision), "trusted configuration is invalid")
        self.api, self.root = api_get, Path(git_root)
        self.repository_id, self.workflow, self.workflow_id = repository_id, workflow, workflow_id
        self.producer = producer_revision
        self._fixed_now = now
        require(isinstance(self.now, datetime) and self.now.tzinfo is not None, "clock is invalid")

    @property
    def now(self):
        return self._fixed_now if self._fixed_now is not None else datetime.now(timezone.utc)

    def get(self, suffix, *, raw=False):
        try:
            return self.api("/repos/endaye/lmdj" + suffix, raw=raw)
        except Exception:
            raise DispatchEvidenceError("why: dispatch API is unavailable; remedy: restore read access to the original run; never redispatch on an observation failure") from None

    def git(self, *args):
        env = {k:v for k,v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE=os.devnull,
                   GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", LC_ALL="C")
        try:
            result = subprocess.run(["git", "-C", str(self.root), *args], env=env,
                                    capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise DispatchEvidenceError("why: dispatch source is unavailable; remedy: restore the original canonical Git objects without executing target code") from None
        require(result.returncode == 0, "source ancestry is unavailable or conflicts")
        return result.stdout

    def pages(self, suffix, key):
        rows, count, seen = [], None, set()
        for page in range(1, 101):
            value = self.get(f"{suffix}?per_page=100&page={page}")
            require(type(value) is dict and type(value.get("total_count")) is int
                    and 0 <= value["total_count"] <= 10000 and type(value.get(key)) is list,
                    "inventory is invalid")
            require(count is None or count == value["total_count"], "inventory count changed")
            count, items = value["total_count"], value[key]
            require(len(items) <= 100, "page is oversized")
            for row in items:
                require(type(row) is dict and positive(row.get("id")) and row["id"] not in seen,
                        "inventory identity repeats or is missing")
                seen.add(row["id"])
            rows.extend(items)
            require(len(rows) <= count, "inventory exceeds count")
            if len(rows) == count:
                return rows
            require(len(items) == 100, "inventory is truncated")
        raise DispatchEvidenceError("why: dispatch read budget exhausted; remedy: reconcile complete inventory without redispatch")

    def run(self, run_id, actor_id, control):
        expected = {"id":run_id, "run_attempt":1, "workflow_id":self.workflow_id,
                    "path":".github/workflows/"+self.workflow, "head_sha":control,
                    "head_branch":"main", "event":"workflow_dispatch"}
        for suffix in (f"/actions/runs/{run_id}", f"/actions/runs/{run_id}/attempts/1"):
            value = self.get(suffix)
            require(type(value) is dict and all(type(value.get(k)) is type(v) and value[k] == v
                    for k,v in expected.items()), "run identity differs")
            for key in ("repository", "head_repository"):
                repo = value.get(key)
                require(type(repo) is dict and type(repo.get("id")) is int and repo["id"] == self.repository_id
                        and repo.get("full_name") == "endaye/lmdj", "run repository differs")
            actor = value.get("actor")
            require(type(actor) is dict and type(actor.get("id")) is int and actor["id"] == actor_id,
                    "run actor differs")
        # Failure or still-running publication/deployment is intentionally not
        # rejected here: correlation proves origin, not the effect's outcome.
        return value

    def verify(self, *, run_id, actor_id, control_revision, inputs):
        require(type(inputs) is dict, "expected inputs are missing")
        return self._read(run_id=run_id, actor_id=actor_id, control_revision=control_revision, inputs=inputs)

    def read(self, *, run_id, actor_id, control_revision):
        """Authenticate actual inputs, including those of unrelated requests."""
        return self._read(run_id=run_id, actor_id=actor_id, control_revision=control_revision, inputs=None)

    def _read(self, *, run_id, actor_id, control_revision, inputs):
        require(positive(run_id) and positive(actor_id) and sha(control_revision), "request identity is invalid")
        main = self.get("/branches/main")
        require(type(main) is dict and main.get("name") == "main" and main.get("protected") is True
                and type(main.get("commit")) is dict and sha(main["commit"].get("sha")), "main is not protected/readable")
        main_sha = main["commit"]["sha"]
        workflow = self.get("/actions/workflows/"+self.workflow)
        require(type(workflow) is dict and type(workflow.get("id")) is int and workflow["id"] == self.workflow_id
                and workflow.get("path") == ".github/workflows/"+self.workflow and workflow.get("state") == "active",
                "workflow identity differs")
        self.run(run_id, actor_id, control_revision)
        jobs = self.pages(f"/actions/runs/{run_id}/attempts/1/jobs", "jobs")
        preflights = [j for j in jobs if j.get("name") == "preflight"]
        require(len(preflights) == 1, "preflight job is absent or ambiguous")
        job = preflights[0]
        require(type(job.get("run_id")) is int and job["run_id"] == run_id
                and type(job.get("run_attempt")) is int and job["run_attempt"] == 1
                and job.get("head_sha") == control_revision and type(job.get("steps")) is list,
                "preflight belongs to another run/attempt")
        for name in ("Record dispatch correlation", "Upload dispatch correlation"):
            matches = [s for s in job["steps"] if type(s) is dict and s.get("name") == name]
            require(len(matches) == 1 and matches[0].get("status") == "completed"
                    and matches[0].get("conclusion") == "success", "receipt producer/upload did not succeed")
        artifacts = self.pages(f"/actions/runs/{run_id}/artifacts", "artifacts")
        matches = [a for a in artifacts if a.get("name") == "release-dispatch-correlation"]
        require(len(matches) == 1, "artifact is missing or ambiguous")
        artifact = matches[0]
        require(artifact.get("expired") is False and type(artifact.get("size_in_bytes")) is int
                and 0 < artifact["size_in_bytes"] <= LIMIT, "artifact expired or exceeds size limit")
        try:
            expires = datetime.strptime(artifact["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            raise DispatchEvidenceError("why: dispatch artifact expiry is invalid; remedy: recover authentic retained evidence") from None
        require(expires > self.now, "artifact retention elapsed")
        origin = artifact.get("workflow_run")
        require(type(origin) is dict and all(type(origin.get(k)) is int and origin[k] == v for k,v in {
            "id":run_id,"repository_id":self.repository_id,"head_repository_id":self.repository_id}.items())
            and origin.get("head_sha") == control_revision and origin.get("head_branch") == "main", "artifact origin differs")
        raw = self.get(f"/actions/artifacts/{artifact['id']}/zip", raw=True)
        require(type(raw) is bytes and 0 < len(raw) <= LIMIT
                and artifact.get("digest") == "sha256:"+hashlib.sha256(raw).hexdigest(), "archive transfer differs")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = archive.infolist()
                require(len(members) == 1 and members[0].filename == "receipt.json"
                        and not members[0].is_dir() and members[0].file_size <= LIMIT
                        and (members[0].external_attr >> 16) & 0o170000 != 0o120000, "archive member is unsafe")
                require(members[0].compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "compression does not support bounded decoding")
                with archive.open(members[0]) as member:
                    payload = member.read(LIMIT + 1)
                require(len(payload) <= LIMIT, "decoded payload exceeds size limit")
            document = json.loads(payload, object_pairs_hook=unique)
            require(type(document) is dict and sha(document.get("tooling_revision")), "receipt tooling identity is invalid")
            if inputs is None:
                inputs = document.get("inputs")
            env = {"GITHUB_REPOSITORY_ID":str(self.repository_id),"GITHUB_ACTOR_ID":str(actor_id),
                "GITHUB_RUN_ID":str(run_id),"GITHUB_RUN_ATTEMPT":"1","GITHUB_EVENT_NAME":"workflow_dispatch",
                "GITHUB_REF":"refs/heads/main","GITHUB_REPOSITORY":"endaye/lmdj",
                "GITHUB_SHA":control_revision,"GITHUB_WORKFLOW_SHA":control_revision,
                "GITHUB_WORKFLOW_REF":f"endaye/lmdj/.github/workflows/{self.workflow}@refs/heads/main"}
            expected = receipt({"inputs":inputs,"ref":"main","repository":{"id":self.repository_id,
                "full_name":"endaye/lmdj"},"sender":{"id":actor_id}}, env, self.workflow, document["tooling_revision"])
            require(payload == canonical_json(expected), "receipt does not match the exact request and canonical schema")
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile) as error:
            if isinstance(error, DispatchEvidenceError):
                raise
            raise DispatchEvidenceError("why: dispatch receipt is malformed; remedy: retain the original run and obtain authentic correlation evidence") from None
        require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false", "Git history is shallow")
        for revision in (self.producer, control_revision, document["tooling_revision"], main_sha):
            require(self.git("cat-file", "-t", revision).strip() == b"commit", "source object is not a commit")
        for older, newer in ((self.producer, control_revision), (control_revision, document["tooling_revision"]),
                             (document["tooling_revision"], main_sha)):
            self.git("merge-base", "--is-ancestor", older, newer)
        self.run(run_id, actor_id, control_revision)
        require(canonical_json(self.pages(f"/actions/runs/{run_id}/artifacts", "artifacts")) == canonical_json(artifacts),
                "artifact inventory changed during observation")
        require(expires > self.now, "artifact retention elapsed")
        return {"schema":"lmdj.release-dispatch-binding.v1", "run_id":run_id,"run_attempt":1,
                "repository_id":self.repository_id,"actor_id":actor_id,
                "workflow":self.workflow,"workflow_id":self.workflow_id,"producer_revision":self.producer,
                "artifact_id":artifact["id"],"artifact_sha256":hashlib.sha256(raw).hexdigest(),
                "artifact_expires_at":artifact["expires_at"],
                "receipt_sha256":canonical_sha256(document),"inputs":dict(inputs),
                "control_revision":control_revision,"tooling_revision":document["tooling_revision"]}

    def discover(self, *, actor_id, control_revision, inputs, prior_run_ids):
        """Reconcile an unknown POST read-only. No result permits another POST.

        Scan the complete workflow inventory, including other control SHAs.
        prior_run_ids MUST be the complete API snapshot frozen in the trusted
        operation journal before its sole POST intent, not a caller's later
        reconstruction or an artifact claim. This reader does not attest when
        a snapshot was taken. Only those prior runs and API-proven other
        actors/events/refs are excluded. Unreadable candidate runs prevent
        uniqueness; empty inventory never proves that a delayed POST cannot land.
        """
        require(positive(actor_id) and sha(control_revision) and type(inputs) is dict
                and type(inputs.get("request_id")) is str and type(prior_run_ids) is list
                and all(positive(identifier) for identifier in prior_run_ids)
                and len(prior_run_ids) == len(set(prior_run_ids)), "discovery scope is invalid")
        inventory_path = "/actions/workflows/" + self.workflow + "/runs"
        def inventory():
            rows = self.pages(inventory_path, "workflow_runs")
            identities = []
            for row in rows:
                actor, repo, head_repo = row.get("actor"), row.get("repository"), row.get("head_repository")
                require(type(row.get("workflow_id")) is int and row["workflow_id"] == self.workflow_id
                        and row.get("path") == ".github/workflows/"+self.workflow
                        and type(actor) is dict and positive(actor.get("id")) and sha(row.get("head_sha"))
                        and type(row.get("event")) is str and type(row.get("head_branch")) is str,
                        "discovery run identity is incomplete")
                for candidate in (repo, head_repo):
                    require(type(candidate) is dict and positive(candidate.get("id"))
                            and candidate["id"] == self.repository_id and candidate.get("full_name") == "endaye/lmdj",
                            "discovery run repository differs")
                identities.append({"id":row["id"],"actor_id":actor["id"],"head_sha":row["head_sha"],
                                   "event":row["event"],"head_branch":row["head_branch"]})
            return sorted(identities, key=lambda row:row["id"])
        try:
            first = inventory()
            candidates, unknown = [], False
            for row in first:
                if row["id"] in prior_run_ids or row["actor_id"] != actor_id or row["event"] != "workflow_dispatch" or row["head_branch"] != "main":
                    continue
                try:
                    observed = self.read(run_id=row["id"],actor_id=actor_id,control_revision=row["head_sha"])
                except DispatchEvidenceError:
                    unknown = True
                    continue
                if observed["inputs"]["request_id"] == inputs["request_id"]:
                    candidates.append(observed)
            second = inventory()
            if first != second:
                return {"status":"unknown","binding":None}
            if len(candidates) > 1 or any(item["inputs"] != inputs or item["control_revision"] != control_revision for item in candidates):
                return {"status":"conflict","binding":None}
            if unknown or not candidates:
                return {"status":"unknown","binding":None}
            # Revalidate the unique receipt after the full scan. The caller's
            # durable single-write intent is still needed to preclude a later
            # duplicate dispatch; this is an observation, not a global lock.
            binding = self.verify(run_id=candidates[0]["run_id"], actor_id=actor_id,
                                  control_revision=control_revision, inputs=inputs)
            require(binding == candidates[0], "discovered receipt changed before binding")
            return {"status":"correlated","binding":binding}
        except DispatchEvidenceError:
            return {"status":"unknown","binding":None}
