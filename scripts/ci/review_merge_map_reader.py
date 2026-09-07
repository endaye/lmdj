"""Actions/contents-only authenticated advice for GitInputs; never calls PR APIs."""
from __future__ import annotations

import base64
import io
import json
import zipfile

import change_scope
import review_merge_map as mapping
import test_scope


class MergeMapReader:
    def __init__(self, repository, repository_id, workflow_id, git_inputs, api_get, download_artifact):
        self.repository, self.repository_id, self.workflow_id = repository, repository_id, workflow_id
        self.inputs, self.get, self.download = git_inputs, api_get, download_artifact
        self.diagnostics = []

    def _pages(self, path, key):
        items, total = [], None
        for page in range(1, 101):
            response = self.get(path + f"?per_page=100&page={page}")
            mapping.require(isinstance(response, dict) and isinstance(response.get(key), list), "API inventory is unavailable")
            count = response.get("total_count")
            mapping.require(type(count) is int and count >= 0 and (total is None or total == count), "API inventory changed or lacks total count")
            total = count
            items.extend(response[key])
            if len(response[key]) < 100:
                mapping.require(len(items) == total and len({item["id"] for item in items}) == total,
                                "API inventory is truncated or contains duplicate identities")
                return items
        mapping.require(False, "API inventory exceeded bounded pagination")

    def _document(self, artifact):
        payload = self.download(artifact["id"])
        mapping.require(isinstance(payload, bytes) and len(payload) <= 8_000_000, "mapping archive exceeds bounded input")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            mapping.require(archive.namelist() == ["map.json"] and archive.getinfo("map.json").file_size <= 8_000_000,
                            "mapping archive members or expanded size are invalid")
            return mapping.validate_map(json.loads(archive.read("map.json"), object_pairs_hook=change_scope.reject_duplicates))

    def _authenticate(self, artifact, commit):
        document = self._document(artifact)
        mapping.require(document["repository"] == self.repository and document["repository_id"] == self.repository_id
                        and document["workflow_id"] == self.workflow_id and document["merge_sha"] == commit["sha"],
                        "mapping identity differs from repository/workflow/interval commit")
        run_id, attempt = document["run_id"], document["run_attempt"]
        expected_name = f"pr-review-merge-map-{commit['sha']}-{run_id}-{attempt}"
        mapping.require(artifact.get("name") == expected_name and artifact.get("expired") is False
                        and artifact.get("workflow_run", {}).get("id") == run_id,
                        "artifact name, expiry or producing run is not authenticated")
        run = self.get(f"/repos/{self.repository}/actions/runs/{run_id}/attempts/{attempt}")
        mapping.require(run.get("id") == run_id and run.get("run_attempt") == attempt
                        and run.get("workflow_id") == self.workflow_id and run.get("path") == ".github/workflows/pr-review.yml"
                        and run.get("repository", {}).get("id") == self.repository_id
                        and run.get("repository", {}).get("full_name") == self.repository
                        and run.get("event") == "pull_request" and run.get("status") == "completed"
                        and run.get("conclusion") == "success", "mapping run is not the exact successful trusted workflow attempt")
        # Closed pull_request runs can retain the PR head, not the squash SHA.
        # Associations can be empty after merge; neither fact is PR absence.
        mapping.require(run.get("head_sha") in {document["head_sha"], document["merge_sha"]}, "mapping run head is unrelated")
        associated = run.get("pull_requests")
        mapping.require(isinstance(associated, list) and (not associated or any(
            p.get("number") == document["pr_number"] and p.get("head", {}).get("sha") == document["head_sha"]
            for p in associated)), "nonempty mapping association names another PR")
        jobs = self._pages(f"/repos/{self.repository}/actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs")
        def job(name, conclusion):
            matches = [j for j in jobs if j.get("name") == name]
            mapping.require(len(matches) == 1 and matches[0].get("run_id") == run_id
                            and matches[0].get("run_attempt") == attempt and matches[0].get("status") == "completed"
                            and matches[0].get("conclusion") == conclusion, "mapping job identity or terminal conclusion differs")
            return matches[0]
        def step(job, name, conclusion):
            matches = [s for s in job.get("steps", []) if s.get("name") == name]
            mapping.require(len(matches) == 1 and matches[0].get("conclusion") == conclusion, "mapping-only step receipt is missing")
        step(job("Resolve review target", "success"), "Resolve the Pull Request head", "skipped")
        job("Review fallback", "skipped")
        publisher = job("Publish review and scope", "success")
        step(publisher, "Map merged PR without another AI call", "success")
        step(publisher, "Publish exact-head review and scope", "skipped")
        main_history = self.inputs._git("rev-list", "--first-parent", self.inputs.main).decode().splitlines()
        mapping.require(document["control_sha"] in main_history and document["merge_sha"] in main_history,
                        "mapping control or merge is not verified main first-parent history")
        source = self.get(f"/repos/{self.repository}/contents/.github/workflows/pr-review.yml?ref={run['head_sha']}")
        mapping.require(source.get("encoding") == "base64", "actual run workflow source is unavailable")
        workflow = base64.b64decode(source["content"].replace("\n", ""), validate=True)
        mapping.require(workflow == self.inputs._git("show", document["control_sha"] + ":.github/workflows/pr-review.yml"),
                        "actual run workflow differs from trusted main control")
        mapping.require(document["changed_paths"] == commit["paths"], "mapping paths differ from actual first-parent delta")
        labels = set()
        current = self.inputs.policy_at(self.inputs.control_sha)
        for item in document["scope_records"]:
            record = item["record"]
            policy = self.inputs.policy_at(record["control_sha"])
            test_scope.validate_record(record, policy, {key: record[key] for key in test_scope.IDENTITY_KEYS})
            # Preserve historical policy closure as explicit suite labels; the
            # current floor cannot discard a formerly required consumer.
            labels.update(record["ai_labels"])
            if record["effective"]["kind"] == "full" or not set(record["effective"]["suites"]) <= set(current.suite_ids):
                labels.add("test:full")
            else:
                labels.update("test:" + suite for suite in record["effective"]["suites"])
        return document["complete"], labels

    def __call__(self, interval):
        self.diagnostics = []
        labels, complete = set(), True
        try:
            # Recompute the caller's interval too: no PR/model supplied path
            # inventory can impersonate GitInputs' complete first-parent union.
            actual = test_scope.collect_interval(self.inputs.repository, interval["base_sha"], interval["target_sha"])
            mapping.require(actual == interval, "advice interval differs from actual Git history")
            artifacts = self._pages(f"/repos/{self.repository}/actions/artifacts", "artifacts")
            for commit in actual["commits"]:
                matches = [a for a in artifacts if a.get("name", "").startswith(f"pr-review-merge-map-{commit['sha']}-")]
                if not matches:
                    complete = False
                    self.diagnostics.append("why: commit mapping is missing; remedy: use full until authenticated evidence is available")
                for artifact in matches:
                    try:
                        valid, additions = self._authenticate(artifact, commit)
                        complete = complete and valid
                        labels.update(additions)
                        if not valid:
                            self.diagnostics.append("why: mapping reports incomplete evidence; remedy: preserve full fallback")
                    except Exception:
                        complete = False
                        self.diagnostics.append("why: mapping cannot be authenticated; remedy: preserve full fallback and reconcile receipts")
        except Exception:
            complete = False
            self.diagnostics.append("why: mapping inventory or Git history unavailable; remedy: use full and restore authenticated read access")
        return {"complete": complete, "labels": sorted(labels)}
