#!/usr/bin/env python3
"""Explicit, retained full-Portal candidate rehearsal, never a real release.

Run outside the recursive npm/CTest suites. Uses only newly created fixture
repositories and local Git transport; no signing, GitHub or deployment calls.
"""
import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import version
from tools.release.candidate_material import CandidateBuildMaterial
from tools.release.candidate_workspace import CandidateSourceWorkspace
from tools.release.candidate_snapshot import CandidateSnapshotRun
from tools.release.candidate_cut import CandidateCutWorkspace
from tools.release.candidate_checks import CandidateTaskChecks
from tools.release.candidate_source import CandidateSourceVerifier
from tools.release.candidate_witness import CandidateWitnessRun
from tools.release.candidate_witness_task import CandidateWitnessTask
from tools.release.witness_checks import WitnessTaskChecks
from tools.release.model import canonical_json, canonical_sha256, load_policy
from tools.release import evidence_branch
from tools.release.candidate_transition import CandidateTransition
from tools.release.github_api import GitHubClient, HttpResponse
from tools.release.orchestration import RequestJournal
from tools.release.orchestration_driver import Observation, ReleaseDriver
from tools.release.orchestration_policy import load_orchestration_policy


def managed_journey(*, evidence, repository, local, source, checked_cut, frozen, request,
                    checks, policy, tool_path, dependencies, record, git, command, retained_output):
    """Actual parent/commands/content; only GitHub/review and transport are fake."""
    remote = evidence / "github-fixture.git"
    command(["git", "init", "--bare", str(remote)])
    # This is a newly cloned, private fixture, not the user's checkout/main.
    git(repository, "checkout", "-B", "main", request["base_revision"])
    git(repository, "push", str(remote), "HEAD:refs/heads/main")
    rows, mutations, pushes = {}, [], []
    main_revision = request["base_revision"]
    witness_root = evidence / "witness-task"
    parent_root, candidate_root = evidence / "driver", evidence / "candidate-transition"
    timestamp = int(time.time())

    def save_api():
        # Model actual platform-side effects separately from controller state.
        raw = canonical_json(dict(main=main_revision, rows=rows, mutations=mutations, pushes=pushes))
        with (evidence / "api-state.json").open("wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    def http(method, url, headers, body):
        nonlocal main_revision
        suffix = url.removeprefix("/repos/endaye/lmdj")
        document = None if body is None else json.loads(body)
        repo, code = dict(id=12, full_name="endaye/lmdj"), 200
        if method == "GET":
            if suffix == "":
                value = repo
            elif suffix == "/user":
                value = dict(id=request["actor_id"])
            elif suffix == "/branches/main":
                value = dict(name="main", protected=True, commit=dict(sha=main_revision))
            elif suffix.startswith("/git/ref/heads/"):
                ref = "refs/" + suffix.removeprefix("/git/ref/")
                oid = git(remote, "rev-parse", ref)[1].decode().strip()
                value = dict(ref=ref, object=dict(type="commit", sha=oid))
            elif suffix.startswith("/pulls?"):
                head = parse_qs(urlsplit(suffix).query)["head"][0].removeprefix("endaye:")
                value = [dict(number=row["number"]) for row in rows.values() if row["head"]["ref"] == head]
            elif suffix.startswith("/pulls/"):
                value = rows[int(suffix.rsplit("/", 1)[1])]
            else:
                raise AssertionError("unexpected fixture GET")
        elif method == "POST":
            assert suffix == "/pulls" and len(rows) < 2
            number = 101 + len(rows)
            oid = git(remote, "rev-parse", "refs/heads/" + document["head"])[1].decode().strip()
            rows[number] = dict(id=number + 1000, number=number,
                html_url=f"https://github.com/endaye/lmdj/pull/{number}", user=dict(id=request["actor_id"]),
                title=document["title"], body=document["body"], state="open", draft=False, merged=False,
                merged_at=None, merge_commit_sha=None, mergeable=True,
                head=dict(ref=document["head"], sha=oid, repo=repo),
                base=dict(ref="main", sha=main_revision, repo=repo))
            value, code = {}, 201  # Deliberately not an authoritative ACK.
        elif method == "PUT":
            assert suffix.endswith("/merge")
            row = rows[int(suffix.split("/")[2])]
            assert not row["merged"] and document == dict(sha=row["head"]["sha"], merge_method="squash")
            assert git(repository, "rev-parse", "HEAD")[1].decode().strip() == main_revision
            assert git(remote, "rev-parse", "refs/heads/" + row["head"]["ref"])[1].decode().strip() == document["sha"]
            git(repository, "merge", "--squash", document["sha"])
            git(repository, "-c", "commit.gpgsign=false", "commit", "-m", "fixture reviewed squash: " + row["title"])
            main_revision = git(repository, "rev-parse", "HEAD")[1].decode().strip()
            git(repository, "push", str(remote), "HEAD:refs/heads/main")
            row.update(merged=True, state="closed", merged_at="2026-09-14T00:00:00Z", merge_commit_sha=main_revision)
            value = {}
        else:
            raise AssertionError("unexpected fixture method")
        if method != "GET":
            mutations.append(dict(method=method, route=suffix, document_sha256=canonical_sha256(document)))
            save_api()
            record({"stage":"fixture-api-effect", "method":method, "route":suffix,
                    "main":main_revision, "github_exercised":False})
        return HttpResponse(code, {"Content-Type":"application/json"}, canonical_json(value))

    def review(kind, spec, row):
        assert row["head"]["sha"] == spec["head_sha"] and row["user"]["id"] == request["actor_id"]
        return Observation("verified", dict(sha256=canonical_sha256(dict(kind=kind, head=spec["head_sha"])),
            reference="fixture-review:" + kind))

    def reviewed_merge(kind, spec, row, receipt):
        assert row["merged"] and receipt == review(kind, spec, row).evidence
        return Observation("verified", dict(sha256=canonical_sha256(dict(kind=kind, id=row["id"],
            merge=row["merge_commit_sha"], review=receipt)), reference="fixture-historical-review:" + kind))

    def authorize(incoming):
        assert incoming == request
        assert policy.digest == request["policy_digest"]

    class StopBeforeCompleteTests:
        def authenticate(self, incoming, selected):
            assert selected == policy
            authorize(incoming)

        def observe(self, state, operation):
            assert operation["step"] == "verification", "managed candidate leaked into the opaque backend"
            return Observation("pending")

        def execute(self, state, operation):
            raise AssertionError("rehearsal must not dispatch or execute another release step")

    client = GitHubClient(token="fixture-only-no-credential", http_transport=http)
    def new_driver():
        candidate = CandidateTransition(candidate_root, checks=checks, request=request, source=source,
            checked_cut=checked_cut, frozen=frozen, repository_id=12, client=client,
            token="fixture-only-no-credential", authorize=authorize, observe_main=lambda: main_revision,
            review=review, verify_merged=reviewed_merge, witness_root=witness_root,
            author_name="Candidate Rehearsal", author_email="fixture@example.invalid", timestamp=timestamp)
        return ReleaseDriver(parent_root, policy, StopBeforeCompleteTests(), candidate=candidate), candidate

    real_run = subprocess.run
    def transport(vector, **kwargs):
        if len(vector) < 2 or not vector[1].startswith("--git-dir="):
            return real_run(vector, **kwargs)
        assert kwargs["env"]["GIT_ALLOW_PROTOCOL"] == "https"
        assert "fixture-only-no-credential" not in " ".join(vector)
        assert "init" in vector or remote.as_uri() in vector
        actual = dict(kwargs, env=dict(kwargs["env"]))
        actual["env"].update(GIT_ALLOW_PROTOCOL="file", GIT_CONFIG_COUNT="0")
        actual["env"].pop("GIT_CONFIG_VALUE_0")
        if "push" in vector:
            assert "--force-with-lease=" + vector[-1].split(":", 1)[1] + ":" in vector
            pushes.append(vector[-1])
            save_api()
            record({"stage":"fixture-branch-push", "refspec":vector[-1], "canonical_remote_exercised":False})
        return real_run(vector, **actual)

    index = Path(local.git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    original_head, original_index = local.revision("HEAD"), index.read_bytes()
    with patch.object(evidence_branch, "REMOTE", remote.as_uri()), patch.object(subprocess, "run", transport), \
            patch("tools.release.task_verification.tempfile.TemporaryFile", retained_output):
        driver, candidate = new_driver()
        first = driver.run(request)
        assert (first.status, first.step, first.verified_steps) == ("pending", "verification", ("candidate",))
        record({"stage":"managed-candidate", "driver_status":first.status, "driver_step":first.step})
        def output_history():
            return {str(name):(name.stat().st_size, sha256(name.read_bytes()).hexdigest())
                    for name in (evidence / "logs").glob("executed-*.log")}
        spools = output_history()
        # Actual producer histories, not synthetic reconstructed command facts.
        source_journal = index.parent / local.JOURNAL_NAME
        task_journal = Path(candidate.task.git("rev-parse", "--absolute-git-dir").decode().strip()) / candidate.task.JOURNAL_NAME
        histories = [candidate_root / CandidateTransition.STATE,
            candidate_root / "workspace/candidate-task-workspace.json", source_journal / "witness-state.json",
            task_journal / "binding.json", task_journal / WitnessTaskChecks.STATE]
        before = {str(name):name.read_bytes() for name in histories}
        for name, raw in before.items():
            record({"stage":"managed-history", "path":name, "sha256":sha256(raw).hexdigest(),
                    "bytes":len(raw), "state":json.loads(raw)})
        driver, candidate = new_driver()
        assert driver.resume(request["id"]) == first
        with RequestJournal(parent_root) as journal:
            driver_state = journal.read(request["id"])
        receipt = candidate.verified_candidate(driver_state, driver_state["transitions"][0])
        assert all(Path(name).read_bytes() == raw for name, raw in before.items()), "cold recovery changed command/state evidence"
        assert output_history() == spools, "cold parent recovery executed or changed a command spool"
        assert [row["method"] for row in mutations] == ["POST", "PUT", "POST", "PUT"] and len(pushes) == 2
        assert receipt["target_revision"] == rows[101]["merge_commit_sha"]
        assert receipt["witness_revision"] == rows[102]["merge_commit_sha"] == main_revision
        assert receipt["target_revision"] != receipt["witness_revision"]
        record({"stage":"managed-cold-resume", "candidate":receipt, "driver":driver_state,
                "api_mutations":mutations, "branch_pushes":pushes, "github_review_exercised":False})
    assert local.revision("HEAD") == original_head and index.read_bytes() == original_index
    assert local.revision(checked_cut["cut"]["source_retention_ref"]) == source["commit"]
    far = evidence / "fresh-clone"
    command(["git", "clone", "--no-local", "--single-branch", "--branch", "main", str(remote), str(far)])
    assert git(far, "cat-file", "-e", source["commit"], expected=None)[0] != 0
    witness = receipt["witness"]
    raw = (far / witness["path"]).read_bytes()
    assert len(raw) == witness["bytes"] and sha256(raw).hexdigest() == witness["sha256"]
    assert raw == (local.root / witness["path"]).read_bytes()
    shutil.copytree(dependencies, far / "apps/docs-site/node_modules", symlinks=True)
    command(["bash", "scripts/docs-site.sh", "check"], cwd=far)
    assert not git(far, "status", "--porcelain")[1].strip()
    assert git(far, "cat-file", "-e", source["commit"], expected=None)[0] != 0
    record({"stage":"complete", "scope":"managed candidate/actual Portal/owned install/two local PR squashes/cold recovery/source-absent clone; fake GitHub and review only",
            "candidate":receipt, "product_build":receipt["product_build"], "remote_release_or_deployment":False})


def main():
    if not __debug__:
        raise RuntimeError("rehearsal assertions must be enabled; do not run Python with -O")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--tool-path", required=True)
    parser.add_argument("--managed-candidate", action="store_true",
                        help="exercise the actual post-cut parent, owned install and driver with a local GitHub fixture")
    args = parser.parse_args()
    evidence = args.evidence_root.resolve()
    evidence.mkdir(mode=0o700)  # Existing runs are never overwritten or resumed.
    logs = evidence / "logs"
    logs.mkdir(mode=0o700)
    isolated_home = evidence / "tool-home"
    isolated_home.mkdir(mode=0o700)
    env = {"PATH":args.tool_path, "LC_ALL":"C", "GIT_CONFIG_NOSYSTEM":"1",
           "GIT_CONFIG_GLOBAL":os.devnull, "GIT_NO_LAZY_FETCH":"1", "GIT_ALLOW_PROTOCOL":"file",
           "GIT_NO_REPLACE_OBJECTS":"1", "GIT_GRAFT_FILE":os.devnull,
           "GIT_TERMINAL_PROMPT":"0", "GIT_LFS_SKIP_SMUDGE":"1",
           "HOME":str(isolated_home), "NPM_CONFIG_USERCONFIG":os.devnull, "PYTHONNOUSERSITE":"1"}
    sequence = 0
    events = []
    def record(event):
        events.append(event)
        with (evidence / "events.jsonl").open("ab") as stream:
            stream.write(canonical_json(event))
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(event), flush=True)

    def command(vector, cwd=ROOT, *, expected=0):
        nonlocal sequence
        sequence += 1
        filename = logs / f"{sequence:03d}.log"
        diagnostics = logs / f"{sequence:03d}.stderr.log"
        record({"command":vector, "cwd":str(cwd), "log":str(filename), "stderr_log":str(diagnostics), "status":"started"})
        with filename.open("xb") as output, diagnostics.open("xb") as errors:
            result = subprocess.run(vector, cwd=cwd, env=env, stdout=output, stderr=errors, timeout=900)
            for stream in (output, errors):
                stream.flush()
                os.fsync(stream.fileno())
        raw = filename.read_bytes()
        error_raw = diagnostics.read_bytes()
        record({"status":"finished", "exit_code":result.returncode, "log":str(filename),
                "bytes":len(raw), "sha256":sha256(raw).hexdigest(), "stderr_log":str(diagnostics),
                "stderr_bytes":len(error_raw), "stderr_sha256":sha256(error_raw).hexdigest()})
        if expected is not None:
            assert result.returncode == expected, f"command failed; retain and inspect {filename}"
        return result.returncode, raw

    def git(repo, *args, expected=0):
        return command(["git", "-c", "core.hooksPath=" + os.devnull, "-c", "core.symlinks=true",
                        "-C", str(repo), *args], expected=expected)

    base = git(ROOT, "rev-parse", "HEAD")[1].decode().strip()
    record({"control_revision":base, "harness_sha256":sha256(Path(__file__).read_bytes()).hexdigest()})
    controllers = ("tools/release/candidate_snapshot.py", "tools/release/candidate_cut.py",
                         "tools/release/candidate_checks.py",
                         "tools/release/candidate_source.py", "tools/release/candidate_witness.py",
                         "tools/release/task_verification.py", "tools/release/candidate_witness_task.py",
                         "tools/release/witness_checks.py",
                         "tools/release/publication_workspace.py")
    if args.managed_candidate:
        controllers += ("tools/release/candidate_transition.py", "tools/release/candidate_task_workspace.py",
            "tools/release/orchestration_driver.py", "tools/release/candidate_pr_sequence.py",
            "tools/release/evidence_pr.py", "tools/release/evidence_branch.py", "tools/release/witness_source.py",
            "tools/release/witness_pr.py", "tools/release/candidate_pr.py", "tools/release/candidate_branch.py")
    record({"managed_candidate":args.managed_candidate,
            "controller_sha256": {name:sha256((ROOT / name).read_bytes()).hexdigest() for name in controllers}})
    dependencies = ROOT / "apps/docs-site/node_modules"
    assert dependencies.is_dir(), "install this control worktree's locked Node dependencies first"
    repository = evidence / "repository"
    command(["git", "clone", "--shared", "--no-checkout", str(ROOT), str(repository)])
    git(repository, "config", "user.name", "Candidate Rehearsal")
    git(repository, "config", "user.email", "fixture@example.invalid")
    request = {"id":"candidate-portal-journey", "repository":"example/candidate-rehearsal", "actor_id":123,
               "authority_ref":"thread:fixture-only", "policy_digest":"a" * 64,
               "control_revision":base, "base_revision":base, "mode":"new", "requested_tag":None}
    policy = load_orchestration_policy(ROOT / "tools/release/orchestration-policy.json", load_policy(ROOT / "tools/release/policy.json"))
    if args.managed_candidate:
        request.update(repository="endaye/lmdj", policy_digest=policy.digest)
    material = CandidateBuildMaterial(repository, evidence / "reservations")
    material.reservations.enroll(request["repository"])
    frozen = material.inputs.freeze(base)
    operation = canonical_sha256({"request":canonical_sha256(request), "step":"candidate"})
    branch = "feat/release-candidate-" + operation
    worktree = evidence / "candidate"
    git(repository, "worktree", "add", "-b", branch, str(worktree), base)
    shutil.copytree(dependencies, worktree / "apps/docs-site/node_modules", symlinks=True)
    local = CandidateSourceWorkspace(worktree, material)
    def verify_source(root):
        current = version.load_version(root / "products/lmdj/version.json")
        assembly_path = root / "products/lmdj/assembly.json"
        assembly = version._verify_assembly(current, assembly_path)
        version._verify_lock(current, assembly_path, assembly, root / "products/lmdj/assembly.lock.json", repo_root=root)
    source = local.prepare_source(request=request, frozen=frozen, main_revision=base,
        author_name="Candidate Rehearsal", author_email="fixture@example.invalid", timestamp=int(time.time()), verify=verify_source)
    record({"stage":"source", "receipt":source})
    def authorize(scope):
        assert scope["request"] == request, "fixture request drift"
        material.inputs.verify(frozen, base)
    runner = CandidateSnapshotRun(local, authorize=authorize, path=args.tool_path)

    # Test-only output capture changes the backing file, not the concrete child,
    # environment, lock inheritance, timeout, exit code or output digest logic.
    @contextmanager
    def retained_output(*unused, **kwargs):
        output = tempfile.NamedTemporaryFile(mode="w+b", prefix="executed-", suffix=".log", dir=logs, delete=False)
        record({"executed_output":output.name, "status":"started"})
        try:
            yield output
        finally:
            output.flush()
            os.fsync(output.fileno())
            output.close()
    with patch("tools.release.task_verification.tempfile.TemporaryFile", retained_output):
        snapshot = runner.run(request, source)
        record({"stage":"snapshot", "receipt":snapshot})
        cut_workspace = CandidateCutWorkspace(runner)
        def authorize_cut_checks(scope):
            assert scope["source"]["request_sha256"] == canonical_sha256(request), "fixture cut request drift"
            assert scope["control_revision"] == base and scope["path"] == args.tool_path
            material.inputs.verify(frozen, base)
        def new_cut_checks():
            return CandidateTaskChecks(cut_workspace, control_revision=base,
                authorize=authorize_cut_checks, path=args.tool_path)
        cut_arguments = dict(request=request, source=source,
            snapshot_sha256=snapshot["sha256"], author_name="Candidate Rehearsal",
            author_email="fixture@example.invalid", timestamp=int(time.time()))
        checked_cut = new_cut_checks().prepare(**cut_arguments)
        cut = checked_cut["cut"]
        record({"stage":"cut", "receipt":cut})
        cut_journal = Path(local.git("rev-parse", "--absolute-git-dir").decode().strip()) / local.JOURNAL_NAME
        cut_checks_raw = (cut_journal / CandidateTaskChecks.STATE).read_bytes()
        cut_checks_state = json.loads(cut_checks_raw)
        assert canonical_json(cut_checks_state) == cut_checks_raw
        assert [row["phase"] for row in cut_checks_state["commands"]] == ["staged"] * 3 + ["committed"] * 3
        assert all(row["status"] == "verified" and row["result"][0] == 0 for row in cut_checks_state["commands"])
        assert checked_cut["checks"]["sha256"] == sha256(cut_checks_raw).hexdigest()
        for row in cut_checks_state["commands"]:
            record({"stage":"cut-" + row["phase"], "command":row["arguments"], "result":row["result"]})
        record({"stage":"cut-task-checks", "receipt":checked_cut["checks"], "state":cut_checks_state})
        output_count = sum("executed_output" in event for event in events)
        cut_workspace = CandidateCutWorkspace(CandidateSnapshotRun(local, authorize=authorize, path=args.tool_path))
        cold_cut = new_cut_checks().prepare(**cut_arguments)
        assert cold_cut == checked_cut, "cold cut changed commit or command evidence"
        assert sum("executed_output" in event for event in events) == output_count, "cold cut replayed checks"
        assert (cut_journal / CandidateTaskChecks.STATE).read_bytes() == cut_checks_raw, "cold cut rewrote command history"
        record({"stage":"cut-cold-resume", "receipt":cold_cut["cut"], "checks":cold_cut["checks"]})

    if args.managed_candidate:
        managed_journey(evidence=evidence, repository=repository, local=local, source=source,
            checked_cut=checked_cut, frozen=frozen, request=request, checks=new_cut_checks(), policy=policy,
            tool_path=args.tool_path, dependencies=dependencies, record=record, git=git,
            command=command, retained_output=retained_output)
        return

    # --no-local forbids alternates/hardlink shortcuts: this clone must genuinely
    # lack the non-ancestor internal source object and its private retention ref.
    far = evidence / "fresh-clone"
    command(["git", "clone", "--no-local", "--single-branch", "--branch", branch, str(repository), str(far)])
    assert git(far, "cat-file", "-e", source["commit"], expected=None)[0] != 0, "fresh clone unexpectedly holds source object"
    git(far, "config", "user.name", "Candidate Rehearsal")
    git(far, "config", "user.email", "fixture@example.invalid")
    git(far, "checkout", "-b", "main", base)
    git(far, "merge", "--squash", cut["commit"])
    git(far, "-c", "commit.gpgsign=false", "commit", "-m", "chore(release): fixture candidate squash")
    introducing = git(far, "rev-parse", "HEAD")[1].decode().strip()
    shutil.copytree(dependencies, far / "apps/docs-site/node_modules", symlinks=True)
    witness = f"apps/architecture-portal/versioned_provenance/version-{cut['product_build']}-squash-witness.json"
    # The producer needs both source and introducing objects. Transfer only the
    # introducing commit back to the retained-source repository; never hydrate
    # the source object into the far-side consumer merely to make it pass.
    git(repository, "fetch", "--no-tags", str(far), introducing)
    witness_arguments = dict(request=request, source=source, cut=cut, frozen=frozen, merge_revision=introducing)
    index_path = Path(local.git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    before = (local.git("rev-parse", "HEAD"), local.git("show-ref"), index_path.read_bytes())
    with patch("tools.release.task_verification.tempfile.TemporaryFile", retained_output):
        first = CandidateWitnessRun(CandidateSourceVerifier(cut_workspace), authorize=authorize,
            observe_main=lambda: introducing, path=args.tool_path).run(**witness_arguments)
        record({"stage":"witness-verified", "receipt":first})
        resumed = CandidateWitnessRun(CandidateSourceVerifier(cut_workspace), authorize=authorize,
            observe_main=lambda: introducing, path=args.tool_path).run(**witness_arguments)
        record({"stage":"witness-cold-resume", "receipt":resumed})
    assert first["receipt"] == resumed["receipt"], "cold resume changed witness identity"
    assert first["command_history_sha256"] != resumed["command_history_sha256"], "cold resume omitted actual verification"
    assert before == (local.git("rev-parse", "HEAD"), local.git("show-ref"), index_path.read_bytes()), "witness runner changed source Git state"
    journal = index_path.parent / local.JOURNAL_NAME
    witness_state = json.loads((journal / "witness-state.json").read_bytes())["state"]
    assert [row["arguments"][2] for row in witness_state["commands"]] == ["witness", "verify-witness", "verify-witness"]
    assert witness_state["confirmed"] == 3 and all(row["result"][0] == 0 for row in witness_state["commands"])
    witness_raw = (worktree / witness).read_bytes()
    assert resumed["receipt"]["witness"] == {"path":witness, "bytes":len(witness_raw), "sha256":sha256(witness_raw).hexdigest()}
    witness_operation = canonical_sha256({"request":canonical_sha256(request), "step":"candidate-witness"})
    witness_branch = "docs/release-witness-" + witness_operation
    witness_root = evidence / "witness-task"
    git(far, "worktree", "add", "-b", witness_branch, str(witness_root), introducing)
    shutil.copytree(dependencies, witness_root / "apps/docs-site/node_modules", symlinks=True)
    def new_task():
        return CandidateWitnessTask(witness_root, CandidateWitnessRun(CandidateSourceVerifier(cut_workspace),
            authorize=authorize, observe_main=lambda: introducing, path=args.tool_path))
    task = new_task()
    def authorize_checks(scope):
        assert scope["binding"]["request_sha256"] == canonical_sha256(request), "fixture Task request drift"
        assert scope["control_revision"] == base and scope["path"] == args.tool_path
        material.inputs.verify(frozen, base)
    def new_checks():
        return WitnessTaskChecks(task, control_revision=base, authorize=authorize_checks, path=args.tool_path)
    task_arguments = dict(receipt=resumed, base_revision=introducing, **witness_arguments,
        author_name="Candidate Rehearsal", author_email="fixture@example.invalid",
        timestamp=int(time.time()))
    with patch("tools.release.task_verification.tempfile.TemporaryFile", retained_output):
        checked = new_checks().prepare(**task_arguments)
        task_receipt = checked["task"]
        record({"stage":"witness-task", "receipt":task_receipt})
        task_journal = Path(task.git("rev-parse", "--absolute-git-dir").decode().strip()) / task.JOURNAL_NAME
        checks_raw = (task_journal / WitnessTaskChecks.STATE).read_bytes()
        checks_state = json.loads(checks_raw)
        assert canonical_json(checks_state) == checks_raw
        assert [row["phase"] for row in checks_state["commands"]] == ["staged"] * 3 + ["committed"] * 3
        assert all(row["status"] == "verified" and row["result"][0] == 0 for row in checks_state["commands"])
        assert checked["checks"]["sha256"] == sha256(checks_raw).hexdigest()
        record({"stage":"witness-task-checks", "receipt":checked["checks"], "state":checks_state})
        output_count = sum("executed_output" in event for event in events)
        task = new_task()
        cold = new_checks().prepare(**task_arguments)
        record({"stage":"witness-task-cold-resume", "receipt":cold["task"], "checks":cold["checks"]})
        assert sum("executed_output" in event for event in events) == output_count, "cold Task replayed checks"
        assert (task_journal / WitnessTaskChecks.STATE).read_bytes() == checks_raw, "cold Task rewrote command history"
    assert checked == cold, "cold Task resume changed its bound commit or actual command evidence"
    assert before == (local.git("rev-parse", "HEAD"), local.git("show-ref"), index_path.read_bytes()), "Task changed original candidate Git state"
    assert task.git("cat-file", "blob", task_receipt["commit"] + ":" + witness) == witness_raw
    assert not task.git("status", "--porcelain").strip(), "completed witness Task is dirty"
    git(far, "merge", "--squash", task_receipt["commit"])
    git(far, "-c", "commit.gpgsign=false", "commit", "-m", "docs(release): fixture reviewed witness squash")
    witness_merged = git(far, "rev-parse", "HEAD")[1].decode().strip()
    assert (far / witness).read_bytes() == witness_raw, "witness squash changed transferred bytes"
    record({"stage":"witness-transfer", "bytes":len(witness_raw), "sha256":sha256(witness_raw).hexdigest(),
            "task_commit":task_receipt["commit"], "squash_commit":witness_merged, "github_review_exercised":False})
    command(["bash", "scripts/docs-site.sh", "check"], cwd=far)
    assert not git(far, "status", "--porcelain")[1].strip(), "fresh-clone final worktree is dirty"
    assert git(far, "cat-file", "-e", source["commit"], expected=None)[0] != 0, "verification unexpectedly hydrated source into main object store"
    record({"stage":"complete", "scope":"local source/cut/squash/witness/Task/cold recovery/fresh-clone Portal only; no GitHub review",
            "base":base, "source":source["commit"], "cut":cut["commit"], "introducing":introducing,
            "product_build":cut["product_build"], "witness":witness,
            "remote_release_or_deployment":False})


if __name__ == "__main__":
    main()
