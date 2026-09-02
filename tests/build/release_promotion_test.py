#!/usr/bin/env python3
"""Contract tests for Channel promotion: policy, ledger, evidence, planner, audit, CLI."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release import audit as audit_module  # noqa: E402
from tools.release import cli  # noqa: E402
from tools.release.deployment_evidence import verify_deployment_run  # noqa: E402
from tools.release.github_api import BranchProjection, WorkflowRunProjection  # noqa: E402
from tools.release.model import (  # noqa: E402
    STABLE_PROMOTION_QUESTION,
    ReleaseModelError,
    load_ledger_document,
    load_policy,
)
from tools.release.promotion import (  # noqa: E402
    LEDGER_PATH,
    PromotionError,
    apply_promotion,
    parse_deployment_run_arguments,
    plan_promotion,
)

TAG = "lmdj-v1.0.41.0"
IDENTITY = "1.0.41.0"
TARGET = "98ffec723cc88ecaacc733c4682d17df9a014bfc"
RUNTIME_RUN = 33628917537
CREATOR_RUN = 33632230550
RUNTIME_WORKFLOW = ".github/workflows/deploy-web-runtime-host.yml"
CREATOR_WORKFLOW = ".github/workflows/deploy-creator-web.yml"
EVIDENCE_DOC = "docs/release-evidence/2026-09-02-lmdj-1.0.41.0-canary-release-intent.md"
NOW = datetime(2026, 9, 2, 13, 0, 0, tzinfo=timezone.utc)


def _entry(**overrides) -> dict:
    entry = {
        "tag": TAG, "kind": "product", "identity": IDENTITY, "target_revision": TARGET,
        "channel": "canary", "disposition": "published", "profile": "web-hosts",
        "snapshot": IDENTITY, "merged_main_run_id": 33600030770,
        "evidence_paths": [EVIDENCE_DOC],
    }
    entry.update(overrides)
    return entry


def _promotion(**overrides) -> dict:
    record = {
        "channel": "dev", "promoted_at": "2026-09-02T13:00:00Z",
        "evidence_paths": ["docs/release-evidence/2026-09-02-lmdj-1.0.41.0-promotion-dev.md"],
        "deployment_runs": [
            {"host": "runtime", "run_id": RUNTIME_RUN, "evidence_sha256": "a" * 64},
            {"host": "creator", "run_id": CREATOR_RUN, "evidence_sha256": "b" * 64},
        ],
        "attestation": "verified",
    }
    record.update(overrides)
    return record


def _ledger(*entries: dict) -> dict:
    return {"schema": "lmdj.release-intents.v1", "entries": list(entries), "historical_exceptions": []}


def _evidence_document(host: str, run_id: int, **overrides) -> dict:
    prefix = "lmdj.web-runtime-host" if host == "runtime" else "lmdj.creator-web"
    passed = {"status": "passed"}
    document = {
        "contract": f"{prefix}.deployment-evidence.v2", "tag": TAG, "git_revision": TARGET,
        "product_build": IDENTITY, "channel": "canary",
        "github_actions": {"run_id": str(run_id)},
        "immutable": {"http": dict(passed), "browser": dict(passed)},
        "production": {"http": dict(passed), "browser": dict(passed), "url": "https://x"},
    }
    document.update(overrides)
    return document


class FakeGitHub:
    """Serves runs by ID and one evidence.json per run; every knob is a plain attribute."""

    def __init__(self) -> None:
        self.runs: dict[int, WorkflowRunProjection] = {
            RUNTIME_RUN: WorkflowRunProjection(
                RUNTIME_RUN, "workflow_dispatch", "e" * 40, "main", RUNTIME_WORKFLOW, "completed", "success",
            ),
            CREATOR_RUN: WorkflowRunProjection(
                CREATOR_RUN, "workflow_dispatch", "f" * 40, "main", CREATOR_WORKFLOW, "completed", "success",
            ),
        }
        self.evidence: dict[int, bytes] = {
            RUNTIME_RUN: json.dumps(_evidence_document("runtime", RUNTIME_RUN)).encode(),
            CREATOR_RUN: json.dumps(_evidence_document("creator", CREATOR_RUN)).encode(),
        }
        self.artifact_error: Exception | None = None
        self.run_error: Exception | None = None

    def get_run(self, repository: str, run_id: int) -> WorkflowRunProjection:
        if self.run_error is not None:
            raise self.run_error
        if run_id not in self.runs:
            raise RuntimeError("GitHub API returned 404 Not Found")
        return self.runs[run_id]

    def get_run_artifact_member(self, repository, run_id, artifact_name, member, *, size_cap) -> bytes:
        if self.artifact_error is not None:
            raise self.artifact_error
        expected = "runtime-host-deployment-evidence" if run_id == RUNTIME_RUN else "creator-host-deployment-evidence"
        if artifact_name != expected or member != "evidence.json":
            raise RuntimeError("retained run artifact is absent")
        return self.evidence[run_id]


class PromotionPolicyAndLedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(ROOT / "tools/release/policy.json")
        cls.document = json.loads((ROOT / "tools/release/policy.json").read_text(encoding="utf-8"))

    def _load(self, document: dict):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_policy(path)

    def test_policy_exposes_a_closed_promotion_section(self) -> None:
        self.assertEqual(self.policy.promotion.max_channel, "dev")
        self.assertEqual(self.policy.promotion.required_hosts("web-hosts"), ("runtime", "creator"))
        self.assertEqual(self.policy.promotion.required_hosts("web-runtime-host"), ("runtime",))
        self.assertEqual(self.policy.promotion.required_hosts("core-package"), ())
        self.assertEqual(self.policy.promotion.hosts["runtime"].workflow_path, RUNTIME_WORKFLOW)
        self.assertEqual(self.policy.promotion.hosts["creator"].workflow_path, CREATOR_WORKFLOW)

    def test_policy_rejects_missing_unknown_or_unmapped_promotion_fields(self) -> None:
        document = copy.deepcopy(self.document)
        del document["promotion"]
        with self.assertRaisesRegex(ReleaseModelError, "missing fields: promotion"):
            self._load(document)
        document = copy.deepcopy(self.document)
        document["promotion"]["max_channel"] = "nightly"
        with self.assertRaisesRegex(ReleaseModelError, "max_channel"):
            self._load(document)
        document = copy.deepcopy(self.document)
        document["promotion"]["deployment_evidence"]["web-hosts"] = ["runtime", "mystery"]
        with self.assertRaisesRegex(ReleaseModelError, "unknown host"):
            self._load(document)
        document = copy.deepcopy(self.document)
        del document["promotion"]["deployment_evidence"]["core-package"]
        with self.assertRaisesRegex(ReleaseModelError, "deployment_evidence"):
            self._load(document)
        document = copy.deepcopy(self.document)
        document["promotion"]["hosts"]["runtime"]["workflow_path"] = "scripts/deploy.sh"
        with self.assertRaisesRegex(ReleaseModelError, "workflow_path"):
            self._load(document)

    def test_ledger_accepts_a_forward_dev_promotion_and_reports_the_current_channel(self) -> None:
        ledger = load_ledger_document(_ledger(_entry(promotions=[_promotion()])), self.policy)
        intent = ledger.intent_for_tag(TAG)
        self.assertEqual(intent.channel, "canary")
        self.assertEqual(intent.current_channel, "dev")
        self.assertEqual(len(intent.promotions), 1)
        self.assertEqual(intent.promotions[0].deployment_runs[1].run_id, CREATOR_RUN)
        plain = load_ledger_document(_ledger(_entry()), self.policy).intent_for_tag(TAG)
        self.assertEqual(plain.current_channel, "canary")
        self.assertEqual(plain.promotions, ())

    def test_ledger_rejects_promotions_off_a_published_product(self) -> None:
        for disposition in ("allocated", "releasable", "abandoned", "superseded-unreleased"):
            with self.assertRaisesRegex(ReleaseModelError, "only a published Product"):
                load_ledger_document(
                    _ledger(_entry(disposition=disposition, promotions=[_promotion()])), self.policy,
                )
        module = {
            "tag": "module/application-facade/v9.9.9", "kind": "module",
            "identity": "application-facade@9.9.9", "target_revision": TARGET,
            "disposition": "published", "profile": "source-only",
            "evidence_paths": [EVIDENCE_DOC], "promotions": [_promotion()],
        }
        with self.assertRaisesRegex(ReleaseModelError, "non-Product ledger entry"):
            load_ledger_document(_ledger(module), self.policy)

    def test_ledger_rejects_backward_skipped_over_max_and_stable_promotions(self) -> None:
        with self.assertRaisesRegex(ReleaseModelError, "strictly forward"):
            load_ledger_document(_ledger(_entry(promotions=[_promotion(channel="canary")])), self.policy)
        with self.assertRaisesRegex(ReleaseModelError, "exceeds the policy max_channel dev"):
            load_ledger_document(
                _ledger(_entry(promotions=[_promotion(channel="beta", attestation="manual-attested")])),
                self.policy,
            )
        with self.assertRaisesRegex(ReleaseModelError, STABLE_PROMOTION_QUESTION.replace(".", r"\.")):
            load_ledger_document(_ledger(_entry(promotions=[_promotion(channel="stable")])), self.policy)
        with self.assertRaisesRegex(ReleaseModelError, "strictly forward"):
            load_ledger_document(
                _ledger(_entry(promotions=[_promotion(), _promotion()])), self.policy,
            )
        with self.assertRaisesRegex(ReleaseModelError, "must not be empty"):
            load_ledger_document(_ledger(_entry(promotions=[])), self.policy)

    def test_ledger_requires_exact_profile_hosts_attestation_and_scalars(self) -> None:
        record = _promotion(deployment_runs=[_promotion()["deployment_runs"][0]])
        with self.assertRaisesRegex(ReleaseModelError, "exactly the profile hosts in order: runtime, creator"):
            load_ledger_document(_ledger(_entry(promotions=[record])), self.policy)
        swapped = _promotion(deployment_runs=list(reversed(_promotion()["deployment_runs"])))
        with self.assertRaisesRegex(ReleaseModelError, "exactly the profile hosts in order"):
            load_ledger_document(_ledger(_entry(promotions=[swapped])), self.policy)
        with self.assertRaisesRegex(ReleaseModelError, "attested as verified"):
            load_ledger_document(
                _ledger(_entry(promotions=[_promotion(attestation="manual-attested")])), self.policy,
            )
        bad_digest = _promotion()
        bad_digest["deployment_runs"][0]["evidence_sha256"] = "XYZ"
        with self.assertRaisesRegex(ReleaseModelError, "lowercase SHA-256"):
            load_ledger_document(_ledger(_entry(promotions=[bad_digest])), self.policy)
        with self.assertRaisesRegex(ReleaseModelError, "exact UTC timestamp"):
            load_ledger_document(
                _ledger(_entry(promotions=[_promotion(promoted_at="2026-09-02 13:00")])), self.policy,
            )
        with self.assertRaisesRegex(ReleaseModelError, "unexpected fields"):
            load_ledger_document(
                _ledger(_entry(promotions=[_promotion(operator="me")])), self.policy,
            )
        core = _entry(profile="core-package", promotions=[_promotion(deployment_runs=[])])
        self.assertEqual(
            load_ledger_document(_ledger(core), self.policy).intent_for_tag(TAG).current_channel, "dev",
        )


class DeploymentEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(ROOT / "tools/release/policy.json")
        self.github = FakeGitHub()

    def _verify(self, host: str = "runtime", run_id: int = RUNTIME_RUN, **overrides):
        arguments = {
            "repository": self.policy.repository, "branch": self.policy.branch, "host": host,
            "host_policy": self.policy.promotion.hosts[host], "tag": TAG,
            "target_revision": TARGET, "identity": IDENTITY, "run_id": run_id,
        }
        arguments.update(overrides)
        return verify_deployment_run(self.github, **arguments)

    def test_matching_evidence_is_ok_and_carries_the_payload_digest(self) -> None:
        result = self._verify()
        self.assertEqual(result.code, "ok", result.message)
        self.assertEqual(result.evidence_sha256, hashlib.sha256(self.github.evidence[RUNTIME_RUN]).hexdigest())
        creator = self._verify(host="creator", run_id=CREATOR_RUN)
        self.assertEqual(creator.code, "ok", creator.message)

    def test_run_identity_mismatches_fail_closed(self) -> None:
        base = self.github.runs[RUNTIME_RUN]
        cases = {
            "different workflow": WorkflowRunProjection(
                RUNTIME_RUN, base.event, base.head_sha, base.head_branch, CREATOR_WORKFLOW, base.status, base.conclusion,
            ),
            "not a manual": WorkflowRunProjection(
                RUNTIME_RUN, "push", base.head_sha, base.head_branch, base.path, base.status, base.conclusion,
            ),
            "not dispatched from main": WorkflowRunProjection(
                RUNTIME_RUN, base.event, base.head_sha, "feat/x", base.path, base.status, base.conclusion,
            ),
            "did not complete successfully": WorkflowRunProjection(
                RUNTIME_RUN, base.event, base.head_sha, base.head_branch, base.path, "completed", "failure",
            ),
        }
        for expected, run in cases.items():
            with self.subTest(expected):
                self.github.runs[RUNTIME_RUN] = run
                result = self._verify()
                self.assertEqual(result.code, "conflict")
                self.assertIn(expected, result.message)
        del self.github.runs[RUNTIME_RUN]
        self.assertEqual(self._verify().code, "missing")
        self.github.runs[RUNTIME_RUN] = base
        self.github.run_error = RuntimeError("connection reset")
        self.assertEqual(self._verify().code, "external-error")

    def test_evidence_document_mismatches_fail_closed(self) -> None:
        cases = {
            "foreign contract": {"contract": "lmdj.other.v1"},
            "different tag": {"tag": "lmdj-v1.0.40.0"},
            "different target revision": {"git_revision": "0" * 40},
            "different Product Build": {"product_build": "1.0.40.0"},
            "does not name its own run": {"github_actions": {"run_id": "1"}},
            "immutable browser check did not pass": {
                "immutable": {"http": {"status": "passed"}, "browser": {"status": "failed"}},
            },
            "production http check did not pass": {
                "production": {"http": {"status": "skipped"}, "browser": {"status": "passed"}},
            },
            "has no production verification": {"production": None},
        }
        for expected, overrides in cases.items():
            with self.subTest(expected):
                self.github.evidence[RUNTIME_RUN] = json.dumps(
                    _evidence_document("runtime", RUNTIME_RUN, **overrides),
                ).encode()
                result = self._verify()
                self.assertEqual(result.code, "conflict", result.message)
                self.assertIn(expected, result.message)
        self.github.evidence[RUNTIME_RUN] = b"not json"
        self.assertEqual(self._verify().code, "conflict")
        self.github.artifact_error = RuntimeError("retained run artifact has expired")
        self.assertEqual(self._verify().code, "unverifiable")
        self.github.artifact_error = RuntimeError("retained run artifact is ambiguous")
        self.assertEqual(self._verify().code, "conflict")
        self.github.artifact_error = RuntimeError("socket timeout")
        self.assertEqual(self._verify().code, "external-error")


class PromotionPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(ROOT / "tools/release/policy.json")
        self.github = FakeGitHub()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "t@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "t"], check=True)
        self._write_ledger(_entry())
        (self.root / EVIDENCE_DOC).parent.mkdir(parents=True, exist_ok=True)
        (self.root / EVIDENCE_DOC).write_text("# intent\n", encoding="utf-8")
        self.acceptance = "docs/quality/2026-09-02-acceptance.md"
        (self.root / self.acceptance).parent.mkdir(parents=True, exist_ok=True)
        (self.root / self.acceptance).write_text("# accepted\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "seed"], check=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_ledger(self, *entries: dict) -> None:
        lines = ",\n".join("    " + json.dumps(entry, separators=(",", ":")) for entry in entries)
        text = (
            '{\n  "schema": "lmdj.release-intents.v1",\n  "entries": [\n'
            f"{lines}\n  ],\n  \"historical_exceptions\": []\n}}\n"
        )
        path = self.root / LEDGER_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _context(self):
        document = json.loads((self.root / LEDGER_PATH).read_text(encoding="utf-8"))
        return SimpleNamespace(
            policy=self.policy, ledger=load_ledger_document(document, self.policy),
            github=self.github, repo_root=self.root,
        )

    def _plan(self, channel: str = "dev", runs=None, evidence=()):
        runs = {"runtime": RUNTIME_RUN, "creator": CREATOR_RUN} if runs is None else runs
        return plan_promotion(
            self._context(), tag=TAG, channel=channel, deployment_runs=runs,
            evidence_paths=list(evidence), now=NOW,
        )

    def test_plan_verifies_every_profile_host_and_names_the_evidence_document(self) -> None:
        plan = self._plan()
        self.assertEqual((plan.from_channel, plan.to_channel, plan.attestation), ("canary", "dev", "verified"))
        self.assertEqual([run.host for run in plan.deployment_runs], ["runtime", "creator"])
        self.assertEqual(
            plan.deployment_runs[0].evidence_sha256,
            hashlib.sha256(self.github.evidence[RUNTIME_RUN]).hexdigest(),
        )
        self.assertEqual(plan.evidence_document, "docs/release-evidence/2026-09-02-lmdj-1.0.41.0-promotion-dev.md")
        self.assertEqual(plan.evidence_paths, (plan.evidence_document,))
        self.assertEqual(plan.promoted_at, "2026-09-02T13:00:00Z")

    def test_plan_refuses_every_gate_violation_with_its_own_reason(self) -> None:
        with self.assertRaisesRegex(PromotionError, "requires deployment evidence for: creator"):
            self._plan(runs={"runtime": RUNTIME_RUN})
        with self.assertRaisesRegex(PromotionError, "no deployment host named: mystery"):
            self._plan(runs={"runtime": RUNTIME_RUN, "creator": CREATOR_RUN, "mystery": 1})
        with self.assertRaisesRegex(PromotionError, STABLE_PROMOTION_QUESTION.replace(".", r"\.")):
            self._plan(channel="stable")
        with self.assertRaisesRegex(PromotionError, "max_channel is dev"):
            self._plan(channel="beta", evidence=[self.acceptance])
        with self.assertRaisesRegex(PromotionError, "already canary"):
            self._plan(channel="canary")
        with self.assertRaisesRegex(PromotionError, "unknown channel"):
            self._plan(channel="nightly")
        self.github.evidence[CREATOR_RUN] = json.dumps(
            _evidence_document("creator", CREATOR_RUN, product_build="1.0.40.0"),
        ).encode()
        with self.assertRaisesRegex(PromotionError, r"\[conflict\] creator .*different Product Build"):
            self._plan()
        self.github = FakeGitHub()
        with self.assertRaisesRegex(PromotionError, "not a tracked file"):
            self._plan(evidence=["docs/quality/missing.md"])
        with self.assertRaisesRegex(PromotionError, "must live under"):
            self._plan(evidence=["README.md"])
        self._write_ledger(_entry(disposition="releasable"))
        with self.assertRaisesRegex(PromotionError, "only a published Product"):
            self._plan()
        self._write_ledger(_entry(tag="lmdj-v1.0.40.0", identity="1.0.40.0"))
        with self.assertRaisesRegex(PromotionError, "not authorized by the intent ledger"):
            self._plan()

    def test_apply_rewrites_exactly_one_ledger_line_and_writes_the_document(self) -> None:
        before = (self.root / LEDGER_PATH).read_text(encoding="utf-8").split("\n")
        plan = self._plan()
        result = apply_promotion(self.root, plan, self.policy)
        after = (self.root / LEDGER_PATH).read_text(encoding="utf-8").split("\n")
        self.assertEqual(len(before), len(after))
        changed = [index for index, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertIn('"promotions":[{"channel":"dev"', after[changed[0]])
        self.assertTrue(after[changed[0]].startswith("    {"))
        reloaded = self._context().ledger.intent_for_tag(TAG)
        self.assertEqual(reloaded.current_channel, "dev")
        self.assertEqual(reloaded.channel, "canary")
        self.assertEqual(reloaded.promotions[0].deployment_runs[1].run_id, CREATOR_RUN)
        document = (self.root / result.evidence_document).read_text(encoding="utf-8")
        self.assertIn("`canary` to `dev`", document)
        self.assertIn(str(RUNTIME_RUN), document)
        self.assertIn(plan.deployment_runs[1].evidence_sha256, document)
        self.assertIn(STABLE_PROMOTION_QUESTION, document)
        with self.assertRaisesRegex(PromotionError, "already dev"):
            self._plan()

    def test_apply_rolls_back_both_writes_when_the_result_cannot_load(self) -> None:
        plan = self._plan()
        broken = load_policy(ROOT / "tools/release/policy.json")
        # A policy whose max_channel excludes the promotion makes the rewritten
        # ledger unloadable; apply must then leave no trace of either write.
        document = json.loads((ROOT / "tools/release/policy.json").read_text(encoding="utf-8"))
        document["promotion"]["max_channel"] = "canary"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            broken = load_policy(path)
        original = (self.root / LEDGER_PATH).read_text(encoding="utf-8")
        with self.assertRaises(ReleaseModelError):
            apply_promotion(self.root, plan, broken)
        self.assertEqual((self.root / LEDGER_PATH).read_text(encoding="utf-8"), original)
        self.assertFalse((self.root / plan.evidence_document).exists())

    def test_parse_deployment_run_arguments(self) -> None:
        self.assertEqual(
            parse_deployment_run_arguments([f"runtime={RUNTIME_RUN}", f"creator={CREATOR_RUN}"]),
            {"runtime": RUNTIME_RUN, "creator": CREATOR_RUN},
        )
        with self.assertRaisesRegex(PromotionError, "HOST=RUN_ID"):
            parse_deployment_run_arguments(["runtime"])
        with self.assertRaisesRegex(PromotionError, "HOST=RUN_ID"):
            parse_deployment_run_arguments(["runtime=0"])
        with self.assertRaisesRegex(PromotionError, "more than once"):
            parse_deployment_run_arguments(["runtime=1", "runtime=2"])


class PromotionAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(ROOT / "tools/release/policy.json")
        self.github = FakeGitHub()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "t@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "t"], check=True)
        self.promotion_doc = _promotion()["evidence_paths"][0]
        (self.root / self.promotion_doc).parent.mkdir(parents=True, exist_ok=True)
        (self.root / self.promotion_doc).write_text("# promotion\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "seed"], check=True)
        self.intent = load_ledger_document(
            _ledger(_entry(promotions=[_promotion()])), self.policy,
        ).intent_for_tag(TAG)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _problem(self):
        context = SimpleNamespace(policy=self.policy, github=self.github, repo_root=self.root)
        return audit_module._promotion_problem(context, self.intent)

    def test_a_promotion_backed_by_live_successful_runs_has_no_problem(self) -> None:
        self.assertIsNone(self._problem())

    def test_absent_failed_and_unavailable_runs_are_reported_by_code(self) -> None:
        del self.github.runs[CREATOR_RUN]
        finding = self._problem()
        self.assertEqual(finding.code, "missing")
        self.assertIn("absent creator deployment run", finding.message)
        self.github = FakeGitHub()
        base = self.github.runs[RUNTIME_RUN]
        self.github.runs[RUNTIME_RUN] = WorkflowRunProjection(
            RUNTIME_RUN, base.event, base.head_sha, base.head_branch, base.path, "completed", "cancelled",
        )
        finding = self._problem()
        self.assertEqual(finding.code, "conflict")
        self.assertIn("runtime deployment run that does not satisfy policy", finding.message)
        self.github = FakeGitHub()
        self.github.run_error = RuntimeError("connection reset")
        self.assertEqual(self._problem().code, "external-error")

    def test_untracked_promotion_evidence_is_unverifiable(self) -> None:
        (self.root / self.promotion_doc).unlink()
        finding = self._problem()
        self.assertEqual(finding.code, "unverifiable")
        self.assertIn("tracked evidence is unavailable", finding.message)


class AuthoritySchemaDivergenceTest(unittest.TestCase):
    """A branch parser that cannot read main's documents is a conflict, not an outage."""

    def test_remote_audit_names_a_policy_schema_divergence_as_conflict(self) -> None:
        policy = load_policy(ROOT / "tools/release/policy.json")
        ledger = load_ledger_document(_ledger(_entry()), policy)
        main_sha = "9" * 40

        @contextmanager
        def detached_worktree(revision):
            yield ROOT

        def authority_reader(root):
            raise ReleaseModelError("policy is missing fields: promotion")

        context = SimpleNamespace(
            policy=policy, ledger=ledger, repo_root=ROOT,
            git=SimpleNamespace(
                fetch_authority=lambda repository, branch: None,
                main_revision=lambda: main_sha,
                detached_worktree=detached_worktree,
            ),
            github=SimpleNamespace(get_branch=lambda repository, branch: BranchProjection("main", True, main_sha)),
            authority_reader=authority_reader,
            authority_context_builder=lambda root, policy, ledger: None,
        )
        report = audit_module.audit(context, remote=True, tag=TAG)
        self.assertEqual([finding.code for finding in report.findings], ["conflict"])
        message = report.findings[0].message
        self.assertIn("does not satisfy this checkout's closed policy or ledger schema", message)
        self.assertIn("land the schema change on main first", message)
        self.assertIn("missing fields: promotion", message)
        self.assertNotIn("external-error", {finding.code for finding in report.findings})


class PromotionCliTest(unittest.TestCase):
    def test_promote_arguments_parse(self) -> None:
        options = cli.parse_arguments([
            "--repo-root", str(ROOT), "promote", TAG, "dev",
            "--deployment-run", f"runtime={RUNTIME_RUN}",
            "--deployment-run", f"creator={CREATOR_RUN}",
            "--evidence", "docs/quality/x.md",
        ])
        self.assertEqual(options.command, "promote")
        self.assertEqual((options.tag, options.channel), (TAG, "dev"))
        self.assertEqual(options.deployment_run, [f"runtime={RUNTIME_RUN}", f"creator={CREATOR_RUN}"])
        self.assertEqual(options.evidence, ["docs/quality/x.md"])
        with self.assertRaises(SystemExit):
            cli.parse_arguments(["--repo-root", str(ROOT), "promote", TAG])


if __name__ == "__main__":
    unittest.main()
