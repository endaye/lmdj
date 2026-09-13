"""Read-only full-batch candidate evidence and recorded published provenance.

Controller artifacts attest that the trusted producer durably claimed this
request. This consumer does NOT replay the latest Issue Journal. No Runtime,
write API, target Python or historical Python is invoked.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

from .self_test_protocol import protocol as self_test  # one trusted CI module identity
from .github_api import CI_SCOPE_LANES
from .batch_reference import (SCHEMA, MAX_DOCUMENT, EXECUTOR_EVENTS, BatchEvidenceError,
                              require, positive, sha, parse_reference)
import batch_evidence_validation as shared
import incremental_batch as batch
import test_scope

WORKFLOW = ".github/workflows/self-test-report.yml"
CONTROLLER = "Incremental batch controller"
MAX_BYTES = MAX_DOCUMENT
POLICY_FILES = ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json")



def equal(left, right):
    # Python equality conflates True with 1; evidence identity never does.
    return self_test.canonical_json(left) == self_test.canonical_json(right)



class BatchEvidenceConsumer:
    """Only api_get(path, raw=False) is injected; configuration is trusted policy.

Repository/workflow IDs and producer_revision come from reviewed release
policy. They must never be taken from the candidate reference itself.
git_root is an existing complete checkout; reads never fetch or execute source.
"""
    def __init__(self, *, api_get, git_root, repository, repository_id, workflow_id, producer_revision, now=None):
        require(repository == "endaye/lmdj" and positive(repository_id) and positive(workflow_id)
                and sha(producer_revision), "trusted consumer source configuration is invalid")
        self.api_get, self.root = api_get, Path(git_root)
        self.repository, self.repository_id, self.workflow_id = repository, repository_id, workflow_id
        self.producer_revision = producer_revision
        self._fixed_now = now
        require(isinstance(self.now, datetime) and self.now.tzinfo is not None, "evidence verification clock is not timezone-aware")

    @property
    def now(self):
        return self._fixed_now if self._fixed_now is not None else datetime.now(timezone.utc)

    def get(self, suffix, *, raw=False):
        try:
            return self.api_get(f"/repos/{self.repository}{suffix}", raw=raw)
        except Exception:
            raise BatchEvidenceError("external-error", "read-only GitHub evidence request failed; external state remains unknown") from None

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE=os.devnull,
                   GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", LC_ALL="C")
        result = subprocess.run(["git", "--no-replace-objects", "-C", str(self.root), *args],
                                env=env, capture_output=True, timeout=60)
        require(result.returncode == 0, "complete local Git provenance cannot be verified", "unverifiable")
        return result.stdout

    def ancestor(self, revision):
        require(sha(revision), "Git identity is not an exact SHA")
        require(self.git("cat-file", "-t", revision).strip() == b"commit", "Git identity is not a commit")
        self.git("merge-base", "--is-ancestor", revision, self.main)

    def pages(self, suffix, key):
        rows, expected, ids = [], None, set()
        for page in range(1, 101):
            document = self.get(f"{suffix}?per_page=100&page={page}")
            require(isinstance(document, dict) and type(document.get("total_count")) is int
                    and 0 <= document["total_count"] <= 10000 and isinstance(document.get(key), list), "GitHub inventory is malformed", "external-error")
            require(expected is None or expected == document["total_count"], "GitHub inventory changed during pagination", "external-error")
            expected = document["total_count"]
            items = document[key]
            require(len(items) <= 100, "GitHub page exceeds its declared size", "external-error")
            for row in items:
                require(isinstance(row, dict) and positive(row.get("id")) and row["id"] not in ids, "GitHub inventory has duplicate or invalid identities", "external-error")
                ids.add(row["id"])
            rows.extend(items)
            require(len(rows) <= expected, "GitHub inventory exceeds its declared total", "external-error")
            if len(rows) == expected:
                return rows
            require(len(items) == 100, "GitHub inventory ended before its declared total", "external-error")
        raise BatchEvidenceError("external-error", "GitHub inventory exceeded pagination budget")

    def run(self, run_id, control, *, expected_event=None, published=False):
        require(positive(run_id), "run ID is invalid")
        latest = None if published else self.get(f"/actions/runs/{run_id}")
        run = self.get(f"/actions/runs/{run_id}/attempts/1")
        for row in ((run,) if published else (latest, run)):
            require(isinstance(row, dict) and type(row.get("id")) is int and row["id"] == run_id
                    and type(row.get("run_attempt")) is int and row["run_attempt"] == 1
                    and type(row.get("workflow_id")) is int and row["workflow_id"] == self.workflow_id
                    and row.get("path") == WORKFLOW and row.get("head_sha") == control
                    and row.get("head_branch") == "main" and isinstance(row.get("event"), str) and row["event"] in EXECUTOR_EVENTS
                    and (expected_event is None or row["event"] == expected_event)
                    and row.get("status") == "completed", "run is not a terminal first-attempt trusted main batch")
            for field in ("repository", "head_repository"):
                repo = row.get(field)
                require(isinstance(repo, dict) and type(repo.get("id")) is int and repo["id"] == self.repository_id
                        and repo.get("full_name") == self.repository, "run repository identity conflicts")
        require(published or latest.get("conclusion") == run.get("conclusion"), "latest and exact-attempt run views disagree")
        self.ancestor(control)
        self.git("merge-base", "--is-ancestor", self.producer_revision, control)
        if published:
            # Only the outer release audit may authorize this mode, and only
            # for PUBLISHED. Immutable tag/signature/assets/v3 marker remain
            # mandatory there; this is provenance, not fresh coverage proof.
            return run, []
        jobs = self.pages(f"/actions/runs/{run_id}/attempts/1/jobs", "jobs")
        require(all(type(j.get("run_id")) is int and j["run_id"] == run_id and type(j.get("run_attempt")) is int
                    and j["run_attempt"] == 1 and j.get("head_sha") == control and j.get("status") == "completed" for j in jobs),
                "job inventory has another run/control/attempt or nonterminal work")
        controllers = [j for j in jobs if j.get("name") == CONTROLLER]
        require(len(controllers) == 1 and controllers[0].get("conclusion") == "success"
                and isinstance(controllers[0].get("started_at"), str) and controllers[0]["started_at"],
                "durable-claim attestation has no successful started controller")
        return run, jobs

    def artifact(self, run, name, filenames, *, retention=None):
        matches = [a for a in self.pages(f"/actions/runs/{run['id']}/artifacts", "artifacts") if a.get("name") == name]
        require(bool(matches), "required original controller or verdict artifact is absent", "unverifiable")
        require(len(matches) == 1, "artifact name is ambiguous")
        item = matches[0]
        require(type(item.get("expired")) is bool, "artifact expiry metadata is invalid")
        try:
            expires = datetime.strptime(item["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, KeyError, TypeError):
            raise BatchEvidenceError("conflict", "artifact retention timestamp is invalid") from None
        require(not item["expired"] and expires > self.now, "original controller or verdict artifact expired", "unverifiable")
        origin = item.get("workflow_run")
        require(isinstance(origin, dict) and all(type(origin.get(k)) is int and origin[k] == v for k, v in {
            "id": run["id"], "repository_id": self.repository_id, "head_repository_id": self.repository_id}.items())
                and origin.get("head_sha") == run["head_sha"] and origin.get("head_branch") == "main",
                "artifact repository/run/control identity conflicts")
        require(type(item.get("size_in_bytes")) is int and 0 < item["size_in_bytes"] <= MAX_BYTES * len(filenames), "artifact size exceeds evidence budget")
        raw = self.get(f"/actions/artifacts/{item['id']}/zip", raw=True)
        require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES * len(filenames), "download size exceeds evidence budget")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            require(len(members) == len(filenames) and {m.filename for m in members} == set(filenames), "artifact ZIP entries are not closed")
            require(all(not m.is_dir() and m.file_size <= MAX_BYTES and (m.external_attr >> 16) & 0o170000 != 0o120000 for m in members), "unsafe or oversized ZIP entry")
            documents = {}
            for member in members:
                require(member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "compression does not support bounded decoding")
                with archive.open(member) as stream:
                    payload = stream.read(MAX_BYTES + 1)
                require(len(payload) <= MAX_BYTES, "decoded artifact member exceeds evidence budget")
                documents[member.filename] = json.loads(payload, object_pairs_hook=test_scope.change_scope.reject_duplicates,
                    parse_constant=lambda _: require(False, "nonfinite artifact JSON"))
        require(expires > self.now, "original controller or verdict artifact expired", "unverifiable")
        if retention is not None:retention.append(expires)
        return documents

    def snapshot(self, run, expected_digest, *, retention=None):
        result = self.artifact(run, f"batch-controller-{run['id']}-1", ("result.json",),retention=retention)["result.json"]
        require(isinstance(result, dict) and set(result) == {"schema", "action", "reason", "request", "executor", "state"}
                and result["schema"] == "lmdj.ci-batch-runtime.v1" and self_test.digest_of(result) == expected_digest,
                "controller attestation schema or digest conflicts")
        require(equal(result["executor"], {"run_id": run["id"], "attempt": 1}) and isinstance(result["state"], dict), "controller attestation has another executor")
        state = result["state"]
        require(set(state) == set(batch.new_state("schema-check")) and state["schema"] == batch.SCHEMA
                and isinstance(state["epoch"], str) and bool(state["epoch"])
                and type(state["generation"]) is int and state["generation"] > 0,
                "controller attestation state schema or epoch is invalid")
        return result

    def verify(self, reference, *, run_id, target_revision):
        return self.verify_run(reference, run_id=run_id, target_revision=target_revision)[0]

    def verify_run(self, reference, *, run_id, target_revision, published=False):
        """Return (verdict, authenticated executor); published returns no verdict.

        Published provenance alone grants no release authority. Its caller must
        still prove the immutable tag, signer, Release, assets and v3 marker.
        """
        try:
            return self._verify(reference, run_id=run_id, target_revision=target_revision, published=published)
        except BatchEvidenceError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, zipfile.BadZipFile, RuntimeError):
            raise BatchEvidenceError("conflict", "retained batch evidence is malformed or contradicts independently recomputed full coverage") from None
        except (OSError, subprocess.SubprocessError):
            raise BatchEvidenceError("external-error", "local read-only provenance could not complete") from None

    def _verify(self, reference, *, run_id, target_revision, published=False):
        ref = parse_reference(reference)
        request = ref["request"]
        require(sha(target_revision) and request["target"] == target_revision, "candidate target differs from frozen request")
        require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false", "shallow Git cannot prove source history", "unverifiable")
        main = self.get("/branches/main")
        require(isinstance(main, dict) and main.get("name") == "main" and main.get("protected") is True
                and isinstance(main.get("commit"), dict) and sha(main["commit"].get("sha")), "authority is not exact protected main")
        self.main = main["commit"]["sha"]
        self.ancestor(self.main)
        self.ancestor(self.producer_revision)
        self.ancestor(target_revision)
        if request["base"] is not None:
            self.ancestor(request["base"])
            self.git("merge-base", "--is-ancestor", request["base"], target_revision)
        workflow = self.get("/actions/workflows/self-test-report.yml")
        require(isinstance(workflow, dict) and type(workflow.get("id")) is int and workflow["id"] == self.workflow_id
                and workflow.get("path") == WORKFLOW, "stable workflow source is not independently authenticated")
        origin, _ = self.run(request["origin_run"]["run_id"], request["control"], published=published)
        executor, jobs = self.run(run_id, ref["executor_control_revision"], expected_event=ref["executor_event"], published=published)
        require(executor.get("conclusion") == "success", "executor run is not successful full-candidate evidence")
        if published:
            return None, deepcopy(executor)
        for path in shared.EXECUTION_SOURCES:
            for revision in (request["control"], executor["head_sha"]):
                require(self.git("cat-file", "-t", f"{revision}:{path}").strip() == b"blob", "execution source is not a Git blob")
            require(self.git("show", f"{request['control']}:{path}") == self.git("show", f"{executor['head_sha']}:{path}"), "frozen and actual executor workflow sources are incompatible")
        def policy_at(revision):
            return test_scope.parse_policy(*(json.loads(self.git("show", f"{revision}:scripts/ci/{name}"),
                object_pairs_hook=test_scope.change_scope.reject_duplicates) for name in POLICY_FILES))
        policy = policy_at(request["control"])
        require(policy.digest == policy_at(self.main).digest == policy_at(executor["head_sha"]).digest == request["policy"], "old or mismatched scope policy cannot certify a new candidate")
        batch._request(policy, request)
        # Complete current inventory is also pinned against canonical scope lanes.
        require(set(policy.suite_ids) == CI_SCOPE_LANES | {"core_tsan_stress", "core_release_stress"}, "policy is not the complete sixteen-suite inventory")
        require(request["selection"]["kind"] == "full" and set(request["selection"]["suites"]) == set(policy.suite_ids), "focused or none selection cannot certify a candidate")
        # Per-verification state: all contributing artifacts must remain live
        # through the final verdict, not merely their individual downloads.
        retention = []
        first = self.snapshot(origin, ref["origin_record_digest"],retention=retention)
        require(first["action"] in {"execute", "waiting"} and equal(first["state"].get("requests", {}).get(request["id"]), request), "origin attestation does not retain the original request")
        if first["action"] == "waiting":
            require(request["kind"] in {"candidate", "node"} and isinstance(first["state"]["queue"], list)
                    and first["state"]["queue"].count(request["id"]) == 1, "origin waiting attestation has no uniquely queued explicit request")
        else:
            require(equal(first["request"], request) and equal(first["state"]["active"], {
                "request_id": request["id"], "executor_run": request["origin_run"], "claim": request["origin_run"]}),
                "origin execution attestation has no matching admission claim")
        admitted = self.snapshot(executor, ref["admission_record_digest"],retention=retention)
        require(first["state"]["epoch"] == admitted["state"]["epoch"], "origin and admission attestation epochs differ")
        require(admitted["action"] == "execute" and equal(admitted["request"], request)
                and equal(admitted["state"].get("requests", {}).get(request["id"]), request)
                and equal(admitted["state"].get("active"), {"request_id": request["id"], "executor_run": {"run_id": run_id, "attempt": 1}, "claim": {"run_id": run_id, "attempt": 1}}),
                "controller record is not this executor's durable-claim admission attestation")
        producers = [j for j in jobs if j.get("name") == shared.PRODUCER_JOB]
        require(len(producers) == 1 and producers[0].get("conclusion") == "success" and shared.producer_uploaded(producers[0]), "full verdict lacks successful authenticated judge and upload")
        visibility = [s for s in producers[0]["steps"] if isinstance(s, dict) and s.get("name") == "Keep failed selected work visible"]
        require(len(visibility) == 1 and visibility[0].get("status") == "completed"
                and visibility[0].get("conclusion") == "skipped", "full candidate producer visibility step is not terminal skipped")
        bundle = self.artifact(executor, f"batch-verdict-{target_revision}-{run_id}-1", ("verdict.json", "execution.json", "needs.json"),retention=retention)
        checked, _ = shared.validate_bundle(bundle, request, executor, policy)
        execution = bundle["execution.json"]
        require(equal(execution["identity"], checked["identity"]) and equal(execution["selection"], checked["selection"])
                and all(type(v) is bool for k in ("suites", "lanes") for v in execution[k].values()),
                "execution projection types differ from independently resolved identity and selection")
        shared.validate_job_observations(checked, producers[0], jobs)
        require(checked["status"] == "passed" and checked["evidence_digest"] == ref["evidence_digest"], "full candidate verdict is not the referenced passed evidence")
        now = self.now
        require(len(retention) == 3 and all(expires > now for expires in retention),
                "original controller or verdict artifact expired before complete verification", "unverifiable")
        return deepcopy(checked), deepcopy(executor)
