#!/usr/bin/env python3
"""Contract tests for the pinned, immutable PR-Agent review boundary.

The pure tests exercise authentication, coverage and budget admission without a
network.  The integration tests run the pinned PR-Agent reviewer and stock
LiteLLMAIHandler against LiteLLM's actual ``acompletion`` seam; only that seam
is replaced, so a green test cannot come from replacing the reviewer itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import shutil


_MODULE_IMPORT_T0 = time.monotonic()

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import pr_agent_review as adapter

_MODULE_IMPORT_SECONDS = time.monotonic() - _MODULE_IMPORT_T0


FIXTURES = ROOT / "tests/fixtures/ci/pr-agent"
SOURCE_ROOT = Path(os.environ.get("PR_AGENT_TEST_SOURCE_ROOT", "/tmp/lmdj-pr-agent-packaging/upstream-53072488"))
STOCK_TOKENIZER_CACHE_KEY = "fb374d419588a4632f3f557e76b4b70aebbca790"
STOCK_TOKENIZER_ASSET_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
STOCK_TOKENIZER_ASSET_BYTES = 3613922


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signed_input(mutator=None):
    document = json.loads((FIXTURES / "complete-input.json").read_text(encoding="utf-8"))
    if mutator:
        mutator(document)
    unsigned = copy.deepcopy(document)
    unsigned.pop("input_sha256", None)
    document["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
    return document


def refresh_diff_identity(document):
    diff_bytes = document["diff"]["text"].encode("utf-8")
    document["diff"]["byte_length"] = len(diff_bytes)
    document["diff"]["sha256"] = hashlib.sha256(diff_bytes).hexdigest()


def add_rename_second_hunk(document):
    base_bytes = (
        b"def value():\n    return 1\nline 3\nline 4\nline 5\n"
        b"line 6\nline 7\nline 8\nline 9\nline 10\n"
    )
    head_bytes = (
        b"def value():\n    return 2\n    # changed\nline 3\nline 4\n"
        b"line 5\nline 6\nline 7\nline 8\nline 9\nline 10\ntail\n"
    )
    second_hunk = "@@ -10,0 +12 @@\n+tail\n"
    document["diff"]["text"] = document["diff"]["text"].replace(
        "diff --git a/src/example.py b/src/example.py\n",
        "diff --git a/src/old-example.py b/src/example.py\n"
        "similarity index 80%\n"
        "rename from src/old-example.py\n"
        "rename to src/example.py\n",
        1,
    ).replace(
        "--- a/src/example.py\n", "--- a/src/old-example.py\n", 1,
    ).replace("\ndiff --git a/obsolete.txt", second_hunk + "\ndiff --git a/obsolete.txt", 1)
    file = document["files"][0]
    file["old_path"] = "src/old-example.py"
    file["change_kind"] = "renamed"
    file["base"] = blob(base_bytes)
    file["head"] = blob(head_bytes)
    file["patch"] += second_hunk
    file["patch_sha256"] = hashlib.sha256(file["patch"].encode("utf-8")).hexdigest()
    file["hunks"].append({
        "id": "src-example-h2",
        "patch": second_hunk,
        "patch_sha256": hashlib.sha256(second_hunk.encode("utf-8")).hexdigest(),
        "right_lines": [{
            "line": 12,
            "text": "tail",
            "sha256": hashlib.sha256(b"tail").hexdigest(),
        }],
    })
    refresh_diff_identity(document)


def blob(data: bytes, encoding="utf-8"):
    return {
        "object_id": hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_length": len(data),
        "data_b64": base64.b64encode(data).decode("ascii"),
        "encoding": encoding,
    }


def _git_fixture_run(root, *args):
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("the real-Git fixture requires git on PATH")
    # Git receives only this explicit allowlist.  In particular, no inherited
    # config-count/parameter channel or repository locator can cross the seam.
    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "LANG": "C",
    }
    options = [
        "-c", "core.hooksPath=/dev/null",
        "-c", "commit.gpgSign=false",
        "-c", "commit.template=",
        "-c", "core.attributesFile=/dev/null",
        "-c", "diff.external=",
        "-c", "diff.textconv=",
        "-c", "color.ui=false",
    ]
    return subprocess.run(
        [git_executable, *options, *args], cwd=root, capture_output=True, check=True,
        env=environment, timeout=10,
    )


def _git_fixture_blob(root, revision, path, expected):
    object_id = _git_fixture_run(root, "rev-parse", f"{revision}:{path}").stdout.decode().strip()
    data = _git_fixture_run(root, "cat-file", "blob", object_id).stdout
    assert data == expected, (path, revision, data, expected)
    return blob(data), {"object_id": object_id, "data": data}


def _committed_git_document(before, action, records, *, find_renames=False):
    """Build an authenticated input from committed Git objects and hand facts."""
    with tempfile.TemporaryDirectory(prefix="t4-space-header-git-") as temporary:
        root = Path(temporary)
        _git_fixture_run(root, "init", "--template=/dev/null", "-q")
        _git_fixture_run(root, "config", "user.email", "fixture@example.invalid")
        _git_fixture_run(root, "config", "user.name", "Fixture")
        (root / "README").write_bytes(b"fixture\n")
        for relative, data in before.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        _git_fixture_run(root, "add", "--all")
        _git_fixture_run(root, "commit", "-qm", "base")
        base_sha = _git_fixture_run(root, "rev-parse", "HEAD").stdout.decode().strip()
        action(root)
        _git_fixture_run(root, "add", "--all")
        _git_fixture_run(root, "commit", "-qm", "head")
        head_sha = _git_fixture_run(root, "rev-parse", "HEAD").stdout.decode().strip()
        (root / "control").write_bytes(b"control\n")
        _git_fixture_run(root, "add", "control")
        _git_fixture_run(root, "commit", "-qm", "control")
        control_sha = _git_fixture_run(root, "rev-parse", "HEAD").stdout.decode().strip()
        diff_args = [
            "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--full-index",
            "--src-prefix=a/", "--dst-prefix=b/", "--line-prefix=",
            "--diff-algorithm=myers", "--no-indent-heuristic",
        ]
        diff_args.append("--find-renames=20%" if find_renames else "--no-renames")
        diff_args.extend([base_sha, head_sha, "--"])
        raw = _git_fixture_run(root, *diff_args).stdout
        diff_text = raw.decode("utf-8")
        document = json.loads((FIXTURES / "complete-input.json").read_text(encoding="utf-8"))
        document["identity"].update({
            "base_sha": base_sha,
            "head_sha": head_sha,
            "control_sha": control_sha,
            "run_id": "t4-space-header-r2-git-fixture",
        })
        document["diff"] = {
            "text": diff_text,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_length": len(raw),
        }
        files = []
        facts = []
        for record in records:
            path = record["path"]
            old_path = record.get("old_path")
            base_info = None
            head_info = None
            if record.get("base") is not None:
                base_info, base_fact = _git_fixture_blob(
                    root, base_sha, old_path if old_path is not None else path, record["base"],
                )
            else:
                base_fact = None
            if record.get("head") is not None:
                head_info, head_fact = _git_fixture_blob(root, head_sha, path, record["head"])
            else:
                head_fact = None
            hunks = []
            for hunk in record["hunks"]:
                patch_fragment = hunk["patch"]
                right_lines = [
                    {"line": line, "text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
                    for line, text in hunk["right_lines"]
                ]
                hunks.append({
                    "id": hunk["id"],
                    "patch": patch_fragment,
                    "patch_sha256": hashlib.sha256(patch_fragment.encode("utf-8")).hexdigest(),
                    "right_lines": right_lines,
                })
            patch = "".join(hunk["patch"] for hunk in record["hunks"])
            files.append({
                "path": path,
                "old_path": old_path,
                "change_kind": record["change_kind"],
                "patch": patch,
                "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
                "base": base_info,
                "head": head_info,
                "hunks": hunks,
            })
            facts.append({"path": path, "base": base_fact, "head": head_fact})
        document["files"] = files
        unsigned = copy.deepcopy(document)
        unsigned.pop("input_sha256", None)
        document["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        return raw, document, facts


class FakeCompletion(dict):
    """Mapping-shaped LiteLLM response with the SDK response logging method."""

    def dict(self):
        return dict(self)


_UNSET_USAGE = object()


def model_identity(actual="fixture-deepseek-served", version=None):
    return {
        "requested": "fixture-deepseek-model",
        "actual": actual,
        "response_version": version,
        "pricing_revision": "fixture-price-v1",
    }


def test_config_document(enabled=("deepseek",), *, per_pr=1.0, backoff=0):
    providers = {}
    for provider in adapter.SUPPORTED_PROVIDERS:
        if provider not in enabled:
            providers[provider] = {
                "enabled": False,
                "endpoint": None,
                "model": None,
                "priced_response_model": None,
                "credential_ref": None,
                "pricing_revision": None,
                "input_price_usd_per_token": None,
                "output_price_usd_per_token": None,
                "pricing_verified": False,
                "context_token_limit": None,
                "fixed_request_charge_usd": None,
                "billable_categories": None,
            }
        else:
            credential_provider = {"deepseek": "DEEPSEEK", "glm": "ZAI", "xai": "XAI", "kimi": "KIMI"}[provider]
            providers[provider] = {
                "enabled": True,
                "endpoint": f"https://{provider}.invalid.example/v1",
                "model": f"fixture-{provider}-model",
                "priced_response_model": f"fixture-{provider}-served",
                "credential_ref": f"PR_AGENT_{credential_provider}_API_KEY",
                "pricing_revision": "fixture-price-v1",
                "input_price_usd_per_token": 0.000001,
                "output_price_usd_per_token": 0.000001,
                "pricing_verified": True,
                "context_token_limit": 16_384,
                "fixed_request_charge_usd": 0.0,
                "billable_categories": list(adapter.BOUNDED_BILLABLE_CATEGORIES),
            }
    return {
        "schema": adapter.CONFIG_SCHEMA,
        "provider_order": list(adapter.SUPPORTED_PROVIDERS),
        "budget": {
            "approval_id": "fixture-approval",
            "timezone": "Asia/Shanghai",
            "monthly_usd": 20.0,
            "pilot_usd": 20.0,
            "per_pr_usd": per_pr,
            "max_requests": 8,
            "max_requests_per_provider": 2,
            "request_timeout_seconds": 60,
            "backoff_seconds": backoff,
            "engine_deadline_seconds": 600,
            "output_token_cap": 50,
        },
        "providers": providers,
    }


def test_config(enabled=("deepseek",), *, per_pr=1.0, backoff=0):
    return adapter._safe_config(test_config_document(enabled, per_pr=per_pr, backoff=backoff))


def bound_source(source_root: Path, destination: Path) -> Path:
    shutil.copytree(source_root, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "scripts/ci/pr_agent_review.py", destination / "pr_agent_review.py")
    shutil.copy2(ROOT / "scripts/ci/pr-agent/config.toml", destination / "config.toml")
    shutil.copy2(ROOT / "scripts/ci/pr-agent/requirements.lock", destination / "requirements.lock")
    stock_tokenizer_asset = destination / "tokenizer-cache" / STOCK_TOKENIZER_CACHE_KEY
    if not stock_tokenizer_asset.is_file():
        stock_tokenizer_asset.parent.mkdir()
        litellm_spec = importlib.util.find_spec("litellm")
        packaged_asset = (
            Path(litellm_spec.origin).parent / "litellm_core_utils" / "tokenizers" / STOCK_TOKENIZER_CACHE_KEY
            if litellm_spec is not None and litellm_spec.origin is not None else None
        )
        if packaged_asset is not None and packaged_asset.is_file():
            shutil.copy2(packaged_asset, stock_tokenizer_asset)
        else:
            stock_tokenizer_asset.write_bytes(b"fixture-only-stock-tokenizer-asset")
    digest = adapter._source_tree_sha256(destination)
    adapter_identity = adapter._file_identity(destination / "pr_agent_review.py")
    config_identity = adapter._file_identity(destination / "config.toml")
    lock_identity = adapter._file_identity(destination / "requirements.lock")
    stock_tokenizer_identity = adapter._file_identity(stock_tokenizer_asset)
    (destination / "IDENTITY").write_text(
        "schema=lmdj.pr-agent-bundle.v1\n"
        f"source_commit={adapter.UPSTREAM_COMMIT}\n"
        f"source_version={adapter.UPSTREAM_VERSION}\n"
        f"source_tree_sha256={digest}\n"
        f"adapter_sha256={adapter_identity['sha256']}\n"
        f"default_config_sha256={config_identity['sha256']}\n"
        f"requirements_lock_sha256={lock_identity['sha256']}\n"
        f"stock_tokenizer_asset_sha256={stock_tokenizer_identity['sha256']}\n",
        encoding="utf-8",
    )
    files = {}
    for name, relative in {
        "manifest": "IDENTITY", "adapter": "pr_agent_review.py",
        "default_config": "config.toml", "requirements_lock": "requirements.lock",
        "stock_tokenizer_asset": f"tokenizer-cache/{STOCK_TOKENIZER_CACHE_KEY}",
    }.items():
        identity = adapter._file_identity(destination / relative)
        files[name] = {"path": relative, **identity}
    (destination / "DEPLOYMENT_IDENTITY.json").write_text(json.dumps({
        "schema": adapter.DEPLOYMENT_SCHEMA,
        "archive": {"sha256": hashlib.sha256(b"fixture-archive").hexdigest(), "byte_length": 15},
        "files": files,
    }, sort_keys=True) + "\n", encoding="utf-8")
    # This is an installation fixture, not a writable checkout. Normalize only
    # the copied fixture before a test deliberately tampers with it; never
    # modify original source files or relax the real loader's mode checks.
    for path in (destination, *destination.rglob("*")):
        if path.is_symlink():
            raise AssertionError("unexpected symlink in controlled source fixture")
        path.chmod(0o755 if path.is_dir() else 0o644)
    return destination


class InputAndPolicyTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FIXTURES / "complete-input.json").read_text(encoding="utf-8"))
        self.authenticated = adapter.authenticate_input(self.document)

    def test_contradictory_reasoning_usage_is_not_priceable(self):
        response = FakeCompletion({
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 96,
                "total_tokens": 196,
                "completion_tokens_details": {"reasoning_tokens": 4000},
            },
        })
        self.assertIsNone(adapter._usage_from_response(response))

    def test_optional_reasoning_usage_is_strict_and_typed_usage_is_supported(self):
        class TypedDetails:
            reasoning_tokens = 40

        class TypedUsage:
            prompt_tokens = 100
            completion_tokens = 96
            total_tokens = 196
            completion_tokens_details = TypedDetails()

        class TypedResponse:
            usage = TypedUsage()

        self.assertEqual(adapter._usage_from_response(TypedResponse()), {
            "prompt_tokens": 100, "completion_tokens": 96, "total_tokens": 196,
        })
        for reasoning_tokens in (True, -1, 97, "40"):
            with self.subTest(reasoning_tokens=reasoning_tokens):
                response = FakeCompletion({
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 96,
                        "total_tokens": 196,
                        "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
                    },
                })
                self.assertIsNone(adapter._usage_from_response(response))

    def test_fixture_authenticates_and_prompt_contains_full_base_head_and_deleted_content(self):
        prompt = adapter.render_prompt_input(self.authenticated)
        self.assertTrue(self.authenticated["input_complete"])
        self.assertEqual(len(adapter.expected_coverage(self.authenticated)), 2)
        self.assertIn("return 1", prompt)
        self.assertIn("return 2", prompt)
        self.assertIn("removed content", prompt)
        self.assertIn("LMDJ-HUNK path=obsolete.txt id=obsolete-h1", prompt)
        coverage = adapter._make_coverage(self.authenticated, provider="deepseek", model=model_identity(), prompt=prompt, usage=None)
        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["expected_hunks"], coverage["observed_hunks"])
        self.assertEqual(set(coverage), adapter.COVERAGE_KEYS)
        self.assertNotIn("coverage_sha256", coverage)
        self.assertTrue(all(set(segment) == adapter.SEGMENT_KEYS for segment in coverage["expected_hunks"]))
        adapter._validate_coverage_receipt(coverage)

    def test_marker_and_content_without_hunk_bytes_is_incomplete_coverage(self):
        markers = "\n".join(
            f"LMDJ-HUNK path={hunk['path']} id={hunk['id']} sha256={hunk['patch']['sha256']}"
            for hunk in adapter.expected_coverage(self.authenticated)
        )
        content = "\n".join(
            block
            for file in self.authenticated["files"]
            for block in (
                adapter._content_block("BASE", file["path"], file["base_bytes"], file["base_encoding"], file["base_blob"]),
                adapter._content_block("HEAD", file["path"], file["head_bytes"], file["head_encoding"], file["head_blob"]),
            )
        )
        coverage = adapter._make_coverage(self.authenticated, provider="deepseek", model=model_identity(),
                                          prompt=markers + "\n" + content, usage=None)
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["observed_hunks"], [])

    def test_digest_mismatch_is_rejected(self):
        tampered = copy.deepcopy(self.document)
        tampered["diff"]["text"] += "forged"
        with self.assertRaisesRegex(adapter.EngineError, "input authentication digest"):
            adapter.authenticate_input(tampered)

    def test_real_git_space_headers_authenticate_every_text_change_kind(self):
        cases = [
            (
                "added-directory-and-trailing-space",
                {},
                lambda root: ((root / "dir with space" / "trailing ").parent.mkdir(parents=True), (root / "dir with space" / "trailing ").write_bytes(b"added")),
                [{
                    "path": "dir with space/trailing ", "change_kind": "added", "head": b"added",
                    "hunks": [{
                        "id": "added-trailing-h1",
                        "patch": "@@ -0,0 +1 @@\n+added\n\\ No newline at end of file\n",
                        "right_lines": [(1, "added")],
                    }],
                }],
            ),
            (
                "modified-directory-space",
                {"dir with space/modified file.txt": b"old\n"},
                lambda root: (root / "dir with space/modified file.txt").write_bytes(b"new\n"),
                [{
                    "path": "dir with space/modified file.txt", "change_kind": "modified",
                    "base": b"old\n", "head": b"new\n",
                    "hunks": [{"id": "modified-space-h1", "patch": "@@ -1 +1 @@\n-old\n+new\n", "right_lines": [(1, "new")]}],
                }],
            ),
            (
                "modified-crlf-no-final-newline",
                {"dir with space/crlf file.txt": b"old\r\nline\r\n"},
                lambda root: (root / "dir with space/crlf file.txt").write_bytes(b"new\r\nline"),
                [{
                    "path": "dir with space/crlf file.txt", "change_kind": "modified",
                    "base": b"old\r\nline\r\n", "head": b"new\r\nline",
                    "hunks": [{
                        "id": "modified-crlf-h1",
                        "patch": "@@ -1,2 +1,2 @@\n-old\r\n-line\r\n+new\r\n+line\n\\ No newline at end of file\n",
                        "right_lines": [(1, "new"), (2, "line")],
                    }],
                }],
            ),
            (
                "deleted-directory-space",
                {"dir with space/deleted file.txt": b"deleted\n"},
                lambda root: (root / "dir with space/deleted file.txt").unlink(),
                [{
                    "path": "dir with space/deleted file.txt", "change_kind": "deleted", "base": b"deleted\n",
                    "hunks": [{"id": "deleted-space-h1", "patch": "@@ -1 +0,0 @@\n-deleted\n", "right_lines": []}],
                }],
            ),
            (
                "edited-rename-old-space-new-plain",
                {"old space/old file.txt": b"keep\nold\n"},
                lambda root: (_git_fixture_run(root, "mv", "old space/old file.txt", "new-file.txt"), (root / "new-file.txt").write_bytes(b"keep\nnew\n")),
                [{
                    "path": "new-file.txt", "old_path": "old space/old file.txt", "change_kind": "renamed",
                    "base": b"keep\nold\n", "head": b"keep\nnew\n",
                    "hunks": [{"id": "rename-old-space-h1", "patch": "@@ -1,2 +1,2 @@\n keep\n-old\n+new\n", "right_lines": [(2, "new")]}],
                }],
            ),
            (
                "edited-rename-old-plain-new-space",
                {"old-file.txt": b"keep\nold\n"},
                lambda root: ((root / "new space").mkdir(parents=True), _git_fixture_run(root, "mv", "old-file.txt", "new space/new file.txt"), (root / "new space/new file.txt").write_bytes(b"keep\nnew\n")),
                [{
                    "path": "new space/new file.txt", "old_path": "old-file.txt", "change_kind": "renamed",
                    "base": b"keep\nold\n", "head": b"keep\nnew\n",
                    "hunks": [{"id": "rename-new-space-h1", "patch": "@@ -1,2 +1,2 @@\n keep\n-old\n+new\n", "right_lines": [(2, "new")]}],
                }],
            ),
            (
                "pure-rename-spaces",
                {"pure old/pure file.txt": b"unchanged\n"},
                lambda root: ((root / "pure new").mkdir(parents=True), _git_fixture_run(root, "mv", "pure old/pure file.txt", "pure new/pure file.txt")),
                [{
                    "path": "pure new/pure file.txt", "old_path": "pure old/pure file.txt", "change_kind": "renamed",
                    "base": b"unchanged\n", "head": b"unchanged\n",
                    "hunks": [{
                        "id": "pure-rename-h1",
                        "patch": "rename from pure old/pure file.txt\nrename to pure new/pure file.txt\n",
                        "right_lines": [],
                    }],
                }],
            ),
        ]
        for name, before, action, records in cases:
            with self.subTest(name=name):
                raw, document, facts = _committed_git_document(
                    before, action, records, find_renames=records[0]["change_kind"] == "renamed",
                )
                self.assertEqual(raw, document["diff"]["text"].encode("utf-8"))
                self.assertEqual(len(set(document["identity"][key] for key in ("base_sha", "head_sha", "control_sha"))), 3)
                for file, fact in zip(document["files"], facts, strict=True):
                    if fact["base"] is not None:
                        self.assertEqual(file["base"]["object_id"], fact["base"]["object_id"])
                        self.assertEqual(base64.b64decode(file["base"]["data_b64"]), fact["base"]["data"])
                    if fact["head"] is not None:
                        self.assertEqual(file["head"]["object_id"], fact["head"]["object_id"])
                        self.assertEqual(base64.b64decode(file["head"]["data_b64"]), fact["head"]["data"])
                authenticated = adapter.authenticate_input(document)
                self.assertTrue(authenticated["input_complete"])
                path = records[0]["path"]
                if records[0]["change_kind"] != "renamed" or records[0]["path"] != "pure new/pure file.txt":
                    if records[0]["change_kind"] == "deleted":
                        self.assertIn(b"+++ /dev/null\n", raw)
                    else:
                        suffix = "\t\n" if " " in path else "\n"
                        self.assertIn(f"+++ b/{path}{suffix}".encode("utf-8"), raw)

    def test_real_git_fixture_isolated_from_poisoned_environment(self):
        poisoned = {
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "core.autocrlf",
            "GIT_CONFIG_VALUE_0": "true",
            "GIT_CONFIG_KEY_1": "core.eol",
            "GIT_CONFIG_VALUE_1": "crlf",
            "GIT_CONFIG_PARAMETERS": "'core.autocrlf'='true'",
            "GIT_DIR": "/tmp/poisoned-git-dir",
            "GIT_WORK_TREE": "/tmp/poisoned-git-work-tree",
            "GIT_INDEX_FILE": "/tmp/poisoned-git-index",
            "GIT_OBJECT_DIRECTORY": "/tmp/poisoned-git-objects",
            "GIT_COMMON_DIR": "/tmp/poisoned-git-common",
            "GIT_CEILING_DIRECTORIES": "/tmp/poisoned-git-ceiling",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/poisoned-git-alternates",
            "GIT_NAMESPACE": "poisoned-namespace",
        }
        with mock.patch.dict(os.environ, poisoned, clear=False):
            self.test_real_git_space_headers_authenticate_every_text_change_kind()

    def test_header_grammar_preserves_legacy_form_and_rejects_suffixes_and_duplicates(self):
        path = "dir with space/example.py"

        def space_document(*, old_header=None, new_header=None, old_extra="", new_extra=""):
            document = copy.deepcopy(self.document)
            original = document["diff"]["text"]
            updated = original.replace(
                "diff --git a/src/example.py b/src/example.py",
                f"diff --git a/{path} b/{path}",
                1,
            )
            old_label = f"--- a/{path}" if old_header is None else old_header
            new_label = f"+++ b/{path}" if new_header is None else new_header
            updated = updated.replace("--- a/src/example.py", old_label, 1)
            updated = updated.replace("+++ b/src/example.py", new_label, 1)
            if old_extra:
                updated = updated.replace(old_label, old_label + old_extra, 1)
            if new_extra:
                updated = updated.replace(new_label, new_label + new_extra, 1)
            document["files"][0]["path"] = path
            document["diff"]["text"] = updated
            refresh_diff_identity(document)
            unsigned = copy.deepcopy(document)
            unsigned.pop("input_sha256", None)
            document["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
            return document

        def no_space_document(*, old_header=None, new_header=None):
            document = copy.deepcopy(self.document)
            updated = document["diff"]["text"]
            if old_header is not None:
                updated = updated.replace("--- a/src/example.py", old_header, 1)
            if new_header is not None:
                updated = updated.replace("+++ b/src/example.py", new_header, 1)
            document["diff"]["text"] = updated
            refresh_diff_identity(document)
            unsigned = copy.deepcopy(document)
            unsigned.pop("input_sha256", None)
            document["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
            return document

        legacy = space_document()
        self.assertEqual(adapter.authenticate_input(legacy)["files"][0]["path"], path)
        native_old = space_document(old_header=f"--- a/{path}\t")
        self.assertEqual(adapter.authenticate_input(native_old)["files"][0]["path"], path)
        native = space_document(new_header=f"+++ b/{path}\t")
        self.assertEqual(adapter.authenticate_input(native)["files"][0]["path"], path)
        for name, document in (
            ("duplicate-old", space_document(old_extra=f"\n--- a/{path}")),
            ("duplicate-new", space_document(new_extra=f"\n+++ b/{path}")),
            ("contradictory-old", space_document(old_header="--- a/other.py")),
            ("contradictory-new", space_document(new_header="+++ b/other.py")),
            ("missing-old", space_document(old_header="")),
            ("missing-new", space_document(new_header="")),
            ("wrong-side-old", space_document(old_header=f"--- b/{path}")),
            ("wrong-side-new", space_document(new_header=f"+++ a/{path}")),
            ("two-tabs", space_document(new_header=f"+++ b/{path}\t\t")),
            ("appended-text", space_document(new_header=f"+++ b/{path}\t timestamp")),
            ("wrong-prefix", space_document(new_header=f"+++ c/{path}")),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
                adapter.authenticate_input(document)

        no_space = copy.deepcopy(self.document)
        no_space["diff"]["text"] = no_space["diff"]["text"].replace("+++ b/src/example.py", "+++ b/src/example.py\t", 1)
        refresh_diff_identity(no_space)
        unsigned = copy.deepcopy(no_space)
        unsigned.pop("input_sha256", None)
        no_space["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        with self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
            adapter.authenticate_input(no_space)
        no_space_old = copy.deepcopy(self.document)
        no_space_old["diff"]["text"] = no_space_old["diff"]["text"].replace("--- a/src/example.py", "--- a/src/example.py\t", 1)
        refresh_diff_identity(no_space_old)
        unsigned = copy.deepcopy(no_space_old)
        unsigned.pop("input_sha256", None)
        no_space_old["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        with self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
            adapter.authenticate_input(no_space_old)

        no_space_baseline = no_space_document()
        self.assertEqual(adapter.authenticate_input(no_space_baseline)["files"][0]["path"], "src/example.py")
        for separator in ("\r", "\v", "\f", "\x85", "\u2028", "\u2029"):
            for side, prefix in (("old", "--- a/"), ("new", "+++ b/")):
                for delimiter in ("", "\t"):
                    with self.subTest(no_space_separator=repr(separator), side=side, delimiter=repr(delimiter)):
                        kwargs = {f"{side}_header": f"{prefix}src/example.py{delimiter}{separator}"}
                        document = no_space_document(**kwargs)
                        with self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
                            adapter.authenticate_input(document)

        for separator in ("\r", "\v", "\f", "\x85", "\u2028", "\u2029"):
            for side, prefix in (("old", "--- a/"), ("new", "+++ b/")):
                for delimiter in ("", "\t"):
                    with self.subTest(separator=repr(separator), side=side, delimiter=repr(delimiter)):
                        kwargs = {f"{side}_header": f"{prefix}{path}{delimiter}{separator}"}
                        document = space_document(**kwargs)
                        with self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
                            adapter.authenticate_input(document)

    def test_payload_header_decoys_cannot_satisfy_real_metadata(self):
        document = copy.deepcopy(self.document)
        base = b"def value():\n-- a/src/example.py\n"
        head = b"def value():\n++ b/src/example.py\n    return 2\n    # changed\n"
        patch = "@@ -1,2 +1,4 @@\n def value():\n--- a/src/example.py\n+++ b/src/example.py\n+    return 2\n+    # changed\n"
        file = document["files"][0]
        file.update(
            base=blob(base),
            head=blob(head),
            patch=patch,
            patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),
            hunks=[{
                "id": "src-example-h1",
                "patch": patch,
                "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
                "right_lines": [
                    {"line": 2, "text": "++ b/src/example.py", "sha256": hashlib.sha256(b"++ b/src/example.py").hexdigest()},
                    {"line": 3, "text": "    return 2", "sha256": hashlib.sha256(b"    return 2").hexdigest()},
                    {"line": 4, "text": "    # changed", "sha256": hashlib.sha256(b"    # changed").hexdigest()},
                ],
            }],
        )
        first = document["diff"]["text"].index("diff --git a/src/example.py")
        second = document["diff"]["text"].index("\ndiff --git a/obsolete.txt")
        section = document["diff"]["text"][first:second]
        hunk_start = section.index("@@")
        document["diff"]["text"] = document["diff"]["text"][:first] + section[:hunk_start] + patch + document["diff"]["text"][second:]
        refresh_diff_identity(document)
        unsigned = copy.deepcopy(document)
        unsigned.pop("input_sha256", None)
        document["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        authenticated = adapter.authenticate_input(document)
        self.assertTrue(authenticated["input_complete"])
        self.assertEqual(authenticated["files"][0]["base_bytes"], base)
        self.assertEqual(authenticated["files"][0]["head_bytes"], head)
        self.assertEqual(document["files"][0]["hunks"][0]["right_lines"][0]["text"], "++ b/src/example.py")

        mutated = copy.deepcopy(document)
        first = mutated["diff"]["text"].index("diff --git a/src/example.py")
        second = mutated["diff"]["text"].index("\ndiff --git a/obsolete.txt")
        section = mutated["diff"]["text"][first:second]
        section = section.replace("--- a/src/example.py", "--- a/unrelated-old.py", 1)
        section = section.replace("+++ b/src/example.py", "+++ b/unrelated-new.py", 1)
        mutated["diff"]["text"] = mutated["diff"]["text"][:first] + section + mutated["diff"]["text"][second:]
        refresh_diff_identity(mutated)
        unsigned = copy.deepcopy(mutated)
        unsigned.pop("input_sha256", None)
        mutated["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        with self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
            adapter.authenticate_input(mutated)

    def test_trusted_collector_witness_consumes_space_path_and_rejects_retained_mismatch(self):
        import review_pipeline as pipeline
        import review_scope

        path = "dir with space/example.py"
        document = copy.deepcopy(self.document)
        document["files"][0]["path"] = path
        document["diff"]["text"] = document["diff"]["text"].replace(
            "diff --git a/src/example.py b/src/example.py",
            f"diff --git a/{path} b/{path}",
            1,
        ).replace("--- a/src/example.py", f"--- a/{path}", 1).replace(
            "+++ b/src/example.py", f"+++ b/{path}\t", 1,
        )
        refresh_diff_identity(document)
        unsigned = copy.deepcopy(document)
        unsigned.pop("input_sha256", None)
        document["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
        with tempfile.TemporaryDirectory(prefix="t4-space-header-witness-") as temporary:
            directory = Path(temporary)
            retained = directory / "t2-input.json"
            retained.write_text(json.dumps(document), encoding="utf-8")
            with mock.patch.dict(os.environ, {"T2_INPUT_JSON": str(retained)}):
                witness = pipeline.trusted_collector(directory)
                self.assertEqual(witness["schema"], review_scope.COLLECTOR_SCHEMA)
                self.assertEqual(witness["expected_hunks"][0]["path"], path)
                mismatched = copy.deepcopy(document)
                mismatched["diff"]["text"] = mismatched["diff"]["text"].replace(
                    f"+++ b/{path}\t", "+++ b/wrong.py", 1,
                )
                refresh_diff_identity(mismatched)
                unsigned = copy.deepcopy(mismatched)
                unsigned.pop("input_sha256", None)
                mismatched["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
                retained.write_text(json.dumps(mismatched), encoding="utf-8")
                with self.assertRaisesRegex(review_scope.ReviewScopeError, "collector input failed"):
                    pipeline.trusted_collector(directory)

    def test_diff_partition_accepts_multi_file_multi_hunk_rename_and_deletion(self):
        authenticated = adapter.authenticate_input(signed_input(add_rename_second_hunk))
        self.assertEqual([file["change_kind"] for file in authenticated["files"]], ["renamed", "deleted"])
        self.assertEqual([hunk["id"] for hunk in authenticated["files"][0]["hunks"]], [
            "src-example-h1", "src-example-h2",
        ])
        self.assertEqual(len(adapter.expected_coverage(authenticated)), 3)

        def mismatched_old_patch_path(document):
            add_rename_second_hunk(document)
            document["diff"]["text"] = document["diff"]["text"].replace(
                "--- a/src/old-example.py\n", "--- a/src/example.py\n", 1,
            )
            refresh_diff_identity(document)

        with self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
            adapter.authenticate_input(signed_input(mismatched_old_patch_path))

    def test_diff_partition_rejects_extra_or_omitted_files_and_hunks(self):
        def extra_file(document):
            document["diff"]["text"] += (
                "\ndiff --git a/unlisted.py b/unlisted.py\n"
                "new file mode 100644\n--- /dev/null\n+++ b/unlisted.py\n"
                "@@ -0,0 +1 @@\n+unlisted\n"
            )
            refresh_diff_identity(document)

        def omitted_file(document):
            document["files"].pop()

        def extra_hunk(document):
            unlisted_hunk = "@@ -10,0 +11 @@\n+unlisted\n"
            document["diff"]["text"] = document["diff"]["text"].replace(
                "\ndiff --git a/obsolete.txt", unlisted_hunk + "\ndiff --git a/obsolete.txt", 1,
            )
            refresh_diff_identity(document)

        def omitted_hunk(document):
            add_rename_second_hunk(document)
            second = document["files"][0]["hunks"].pop()
            document["files"][0]["patch"] = document["files"][0]["patch"].removesuffix(second["patch"])
            document["files"][0]["patch_sha256"] = hashlib.sha256(
                document["files"][0]["patch"].encode("utf-8")
            ).hexdigest()

        for name, mutator in (
            ("extra-file", extra_file), ("omitted-file", omitted_file),
            ("extra-hunk", extra_hunk), ("omitted-hunk", omitted_hunk),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
                adapter.authenticate_input(signed_input(mutator))

    def test_diff_partition_rejects_duplicate_and_overlapping_fragments(self):
        def duplicate(document):
            duplicate_hunk = copy.deepcopy(document["files"][0]["hunks"][0])
            duplicate_hunk["id"] = "src-example-duplicate"
            document["files"][0]["hunks"].append(duplicate_hunk)

        def append_hunk(document, patch, hunk_id, line):
            document["diff"]["text"] = document["diff"]["text"].replace(
                "\ndiff --git a/obsolete.txt", patch + "\ndiff --git a/obsolete.txt", 1,
            )
            file = document["files"][0]
            file["patch"] += patch
            file["patch_sha256"] = hashlib.sha256(file["patch"].encode()).hexdigest()
            file["hunks"].append({
                "id": hunk_id,
                "patch": patch,
                "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
                "right_lines": [{
                    "line": line, "text": "tail", "sha256": hashlib.sha256(b"tail").hexdigest(),
                }],
            })
            refresh_diff_identity(document)

        def old_overlap(document):
            append_hunk(document, "@@ -2 +4 @@\n-    return 1\n+tail\n", "old-overlap", 4)

        def new_overlap(document):
            append_hunk(document, "@@ -3,0 +3 @@\n+tail\n", "new-overlap", 3)

        for name, mutator in (
            ("duplicate", duplicate), ("old-overlap", old_overlap), ("new-overlap", new_overlap),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(adapter.EngineError, "exactly partitioned"):
                adapter.authenticate_input(signed_input(mutator))

    def test_diff_partition_accepts_no_newline_markers_after_removed_and_added_lines(self):
        def no_newline(document):
            patch = (
                "@@ -1 +1 @@\n-old\n\\ No newline at end of file\n"
                "+new\n\\ No newline at end of file\n"
            )
            first_section, second_section = document["diff"]["text"].split(
                "\ndiff --git a/obsolete.txt", 1,
            )
            metadata = first_section.split("@@", 1)[0]
            document["diff"]["text"] = metadata + patch + "\ndiff --git a/obsolete.txt" + second_section
            file = document["files"][0]
            file["patch"] = patch
            file["patch_sha256"] = hashlib.sha256(patch.encode()).hexdigest()
            file["base"] = blob(b"old")
            file["head"] = blob(b"new")
            file["hunks"] = [{
                "id": "src-example-h1", "patch": patch,
                "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
                "right_lines": [{
                    "line": 1, "text": "new", "sha256": hashlib.sha256(b"new").hexdigest(),
                }],
            }]
            refresh_diff_identity(document)

        authenticated = adapter.authenticate_input(signed_input(no_newline))
        self.assertEqual(authenticated["files"][0]["hunks"][0]["right_lines"], [1])

    def test_binary_diff_record_remains_explicit_and_authenticated(self):
        def add_binary(document):
            patch = "Binary files a/image.bin and b/image.bin differ\n"
            document["diff"]["text"] += (
                "\ndiff --git a/image.bin b/image.bin\n"
                "index 1111111..2222222 100644\n" + patch
            )
            document["files"].append({
                "path": "image.bin", "old_path": None, "change_kind": "binary",
                "patch": patch, "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
                "base": blob(b"old-binary", "binary"), "head": blob(b"new-binary", "binary"),
                "hunks": [{
                    "id": "image-binary", "patch": patch,
                    "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(), "right_lines": [],
                }],
            })
            refresh_diff_identity(document)

        authenticated = adapter.authenticate_input(signed_input(add_binary))
        self.assertEqual(authenticated["files"][-1]["change_kind"], "binary")
        self.assertEqual(authenticated["files"][-1]["hunks"][0]["right_lines"], [])

    def test_blob_object_id_and_closed_metadata_are_verified(self):
        def malformed_id(document):
            document["files"][0]["base"]["object_id"] = "not-a-git-object"

        with self.assertRaisesRegex(adapter.EngineError, "Git blob object ID"):
            adapter.authenticate_input(signed_input(malformed_id))

        def mismatched_id(document):
            document["files"][0]["base"]["object_id"] = "0" * 40

        with self.assertRaisesRegex(adapter.EngineError, "object ID, hash or length"):
            adapter.authenticate_input(signed_input(mismatched_id))

        def mismatched_length(document):
            document["files"][0]["head"]["byte_length"] += 1

        with self.assertRaisesRegex(adapter.EngineError, "object ID, hash or length"):
            adapter.authenticate_input(signed_input(mismatched_length))

        def extra_blob_key(document):
            document["files"][0]["base"]["untrusted"] = True

        with self.assertRaisesRegex(adapter.EngineError, "invalid blob record"):
            adapter.authenticate_input(signed_input(extra_blob_key))

    def test_coverage_closed_schema_and_complete_equality_are_enforced(self):
        coverage = adapter._make_coverage(
            self.authenticated, provider="deepseek", model=model_identity(),
            prompt=adapter.render_prompt_input(self.authenticated), usage=None,
        )
        for mutation in (
            lambda value: value.pop("usage"),
            lambda value: value.update(extra=True),
        ):
            invalid = copy.deepcopy(coverage)
            mutation(invalid)
            with self.assertRaisesRegex(adapter.EngineError, "closed schema"):
                adapter._validate_coverage_receipt(invalid)
        invalid = copy.deepcopy(coverage)
        invalid["observed_hunks"] = invalid["observed_hunks"][:-1]
        with self.assertRaisesRegex(adapter.EngineError, "exactly cover"):
            adapter._validate_coverage_receipt(invalid)
        invalid = copy.deepcopy(coverage)
        invalid["expected_hunks"][0]["patch"]["extra"] = True
        with self.assertRaisesRegex(adapter.EngineError, "patch identity"):
            adapter._validate_coverage_receipt(invalid)

    def test_changed_file_without_both_immutable_blobs_is_rejected(self):
        def remove_head(document):
            document["files"][0]["head"] = None

        with self.assertRaisesRegex(adapter.EngineError, "missing base or head bytes"):
            adapter.authenticate_input(signed_input(remove_head))

    def test_added_file_without_head_bytes_is_rejected(self):
        def add_missing_head(document):
            file = document["files"][0]
            file["change_kind"] = "added"
            file["base"] = None
            file["head"] = None

        with self.assertRaisesRegex(adapter.EngineError, "missing head bytes"):
            adapter.authenticate_input(signed_input(add_missing_head))

    def test_unreadable_content_is_visible_but_never_complete(self):
        def add_unreadable(document):
            marker = "@@ -0,0 +0,0 @@\n"
            document["diff"]["text"] += "\ndiff --git a/secret.bin b/secret.bin\n" + marker
            refresh_diff_identity(document)
            document["files"].append({
                "path": "secret.bin",
                "old_path": None,
                "change_kind": "unreadable",
                "patch": marker,
                "patch_sha256": hashlib.sha256(marker.encode()).hexdigest(),
                "base": None,
                "head": None,
                "hunks": [{
                    "id": "secret-marker",
                    "patch": marker,
                    "patch_sha256": hashlib.sha256(marker.encode()).hexdigest(),
                    "right_lines": [],
                }],
            })

        authenticated = adapter.authenticate_input(signed_input(add_unreadable))
        self.assertFalse(authenticated["input_complete"])
        coverage = adapter._make_coverage(authenticated, provider="deepseek", model=model_identity(),
                                          prompt=adapter.render_prompt_input(authenticated), usage=None)
        self.assertFalse(coverage["complete"])
        self.assertIn("secret.bin", {hunk["path"] for hunk in coverage["expected_hunks"]})

    def test_native_yaml_fixtures_bypass_lfs_and_hash_as_plain_git_bytes(self):
        for relative in (
            "tests/fixtures/ci/pr-agent/valid-native-review.yaml",
            "tests/fixtures/ci/pr-agent/clean-native-review.yaml",
        ):
            with self.subTest(path=relative):
                data = (ROOT / relative).read_bytes()
                self.assertTrue(data.startswith(b"review:\n"))
                self.assertNotIn(b"git-lfs.github.com/spec", data)
                attributes = subprocess.run(
                    ["git", "check-attr", "filter", "diff", "merge", "text", "--", relative],
                    cwd=ROOT, text=True, capture_output=True, check=True,
                ).stdout
                for expected in ("filter: unspecified", "diff: unspecified", "merge: unspecified", "text: set"):
                    self.assertIn(
                        expected, attributes,
                        "why: a semantic PR-Agent YAML fixture is still selected for LFS; "
                        "remedy: keep the exact-path !filter !diff !merge text exception",
                    )
                stored_oid = subprocess.run(
                    ["git", "hash-object", f"--path={relative}", "--stdin"],
                    cwd=ROOT, input=data, capture_output=True, check=True,
                ).stdout.decode().strip()
                self.assertEqual(
                    stored_oid, blob(data)["object_id"],
                    "why: Git clean filtering would replace semantic YAML with another object; "
                    "remedy: store this exact tiny fixture as ordinary Git text",
                )

    def test_oversized_diff_is_rejected_before_engine_import(self):
        def enlarge(document):
            document["diff"]["text"] = "x" * (adapter.MAX_INPUT_BYTES + 1)

        with self.assertRaisesRegex(adapter.EngineError, "diff is oversized"):
            adapter.authenticate_input(signed_input(enlarge))

    def test_wrong_side_and_outside_diff_findings_are_rejected(self):
        for path, start, end, reason in (
            ("src/example.py", 1, 1, "changed RIGHT-side line"),
            ("not-changed.py", 2, 2, "outside the changed path"),
            ("src/example.py", 3, 2, "changed RIGHT-side line"),
        ):
            with self.subTest(path=path, start=start, end=end), self.assertRaisesRegex(adapter.EngineError, reason):
                adapter._validate_native_mapping({"review": {
                    "general_comments": "Reviewed.", "key_issues_to_review": [{
                        "relevant_file": path, "issue_header": "Bug", "issue_content": "bad",
                        "start_line": start, "end_line": end,
                    }]}}, self.authenticated)

    def test_yaml_block_scalar_path_anchors_to_the_exact_inventory(self):
        mapped = adapter._validate_native_mapping({"review": {
            "general_comments": "Reviewed.", "key_issues_to_review": [{
                "relevant_file": "src/example.py\n", "issue_header": "Bug", "issue_content": "anchored",
                "start_line": 2, "end_line": 3,
            }]}}, self.authenticated)
        self.assertEqual(mapped["findings"], [{"path": "src/example.py", "line": 2, "body": "Bug: anchored"}])

    def test_exact_git_path_keeps_surrounding_whitespace(self):
        authenticated = copy.deepcopy(self.authenticated)
        authenticated["files"][0]["path"] = " spaced.py "
        mapped = adapter._validate_native_mapping({"review": {
            "general_comments": "Reviewed.", "key_issues_to_review": [{
                "relevant_file": " spaced.py ", "issue_header": "Bug", "issue_content": "anchored",
                "start_line": 2, "end_line": 3,
            }]}}, authenticated)
        self.assertEqual(mapped["findings"][0]["path"], " spaced.py ")

    def test_malformed_finding_fields_are_still_rejected(self):
        for finding in (
            {"relevant_file": 7, "issue_header": "Bug", "issue_content": "x", "start_line": 2, "end_line": 2},
            {"relevant_file": "src/example.py", "issue_header": "Bug", "issue_content": "", "start_line": 2, "end_line": 2},
            {"relevant_file": "src/example.py", "issue_header": "Bug", "issue_content": "x", "start_line": "2", "end_line": 2},
        ):
            with self.subTest(finding=finding), self.assertRaisesRegex(adapter.EngineError, "invalid typed fields"):
                adapter._validate_native_mapping({"review": {"general_comments": "s", "key_issues_to_review": [finding]}},
                                                 self.authenticated)
        duplicate = {"relevant_file": "src/example.py", "issue_header": "Bug", "issue_content": "x", "start_line": 2, "end_line": 2}
        with self.assertRaisesRegex(adapter.EngineError, "duplicated"):
            adapter._validate_native_mapping({"review": {"general_comments": "s", "key_issues_to_review": [duplicate, dict(duplicate)]}},
                                             self.authenticated)

    def test_prompt_lists_the_changed_right_side_lines_of_every_hunk(self):
        prompt = adapter.render_prompt_input(self.authenticated)
        for file in self.authenticated["files"]:
            for hunk in file["hunks"]:
                header = f"BEGIN HUNK RIGHT-SIDE LINES path={file['path']} id={hunk['id']}"
                self.assertIn(header, prompt)
                block = prompt.split(header, 1)[1].split("END HUNK RIGHT-SIDE LINES", 1)[0]
                listed = [int(line.split(":", 1)[0]) for line in block.splitlines()[1:] if line.strip()]
                self.assertEqual(listed, hunk["right_lines"])
        # Coverage still sees the exact hunk bytes and content blocks.
        coverage = adapter._make_coverage(self.authenticated, provider="deepseek", model=model_identity(), prompt=prompt, usage=None)
        self.assertTrue(coverage["complete"])

    def test_trusted_owner_is_root_or_the_current_account(self):
        self.assertTrue(adapter._trusted_owner(0))
        self.assertTrue(adapter._trusted_owner(os.getuid()))
        self.assertFalse(adapter._trusted_owner(os.getuid() + 1_000_003))

    def test_witness_cli_prints_the_trusted_configuration_or_a_bounded_error(self):
        witness = {"schema": adapter.WITNESS_SCHEMA, "provider_order": ["deepseek"], "providers": {}, "engine": {"name": "pr-agent"}}
        with mock.patch.object(adapter, "describe_engine", return_value=witness), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(adapter._main(["--witness", "--config", "/x/runtime.toml"]), 0)
        self.assertEqual(json.loads(out.getvalue()), witness)
        with mock.patch.object(adapter, "describe_engine", side_effect=adapter.EngineError("engine_unavailable", "bounded")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(adapter._main(["--witness"]), 2)
        self.assertEqual(json.loads(out.getvalue())["error_class"], "engine_unavailable")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            adapter._main([])

    def test_describe_engine_binds_config_and_installed_identity(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with tempfile.TemporaryDirectory() as directory:
            source = bound_source(SOURCE_ROOT, Path(directory) / "source")
            config_path = source / "runtime.toml"
            config_path.write_text((ROOT / "scripts/ci/pr-agent/runtime.toml").read_text(encoding="utf-8"), encoding="utf-8")
            config_path.chmod(0o644)
            with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source), \
                    mock.patch.object(adapter, "TRUSTED_CONFIG_ROOT", source):
                try:
                    witness = adapter.describe_engine(config_path=config_path, source_root=source,
                                                      engine_cwd=Path(directory) / "engine")
                except adapter.EngineError as exc:
                    self.skipTest(f"pinned dependencies unavailable in this interpreter: {exc.safe_message}")
            config_identity = adapter._file_identity(config_path)
            adapter_identity = adapter._file_identity(source / "pr_agent_review.py")
        self.assertEqual(witness["schema"], adapter.WITNESS_SCHEMA)
        self.assertEqual(witness["provider_order"], ["deepseek"])
        self.assertTrue(witness["providers"]["deepseek"]["enabled"])
        self.assertEqual(witness["providers"]["deepseek"]["model"], "deepseek/deepseek-flash")
        self.assertEqual(witness["engine"]["name"], "pr-agent")
        self.assertEqual(witness["engine"]["source_commit"], adapter.UPSTREAM_COMMIT)
        self.assertEqual(witness["engine"]["runtime_config"], config_identity)
        self.assertEqual(witness["engine"]["bundle"]["adapter_sha256"], adapter_identity["sha256"])

    def test_missing_native_findings_list_is_not_a_clean_review_without_yaml_dependency(self):
        with self.assertRaisesRegex(adapter.EngineError, "missing its findings list"):
            adapter._validate_native_mapping({"review": {"general_comments": "clean"}}, self.authenticated)

    def test_semantically_empty_and_unknown_native_fields_are_rejected(self):
        with self.assertRaisesRegex(adapter.EngineError, "model-supplied summary"):
            adapter._validate_native_mapping({"review": {"key_issues_to_review": []}}, self.authenticated)
        with self.assertRaisesRegex(adapter.EngineError, "unsupported fields"):
            adapter._validate_native_mapping({"review": {
                "general_comments": "clean", "key_issues_to_review": [], "ignored": "x",
            }}, self.authenticated)

    def test_refused_repair_verdict_keeps_the_validated_review(self):
        """One unusable recheck verdict must not void the head's review."""
        request = {"comment_id": 70, "thread_id": "T70", "original_head": "a" * 40,
                   "path": "src/example.py", "original_line": 2, "body": "Return value must be two.",
                   "original_content": "def value():\n    return 1\n",
                   "fix_diff": "@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2\n",
                   "conversation": [{"id": 70, "author_id": 20, "body": "Return value must be two.",
                                     "updated_at": "2026-09-14T00:00:00Z"}]}
        authenticated = adapter.authenticate_input(
            signed_input(lambda document: document.update(repair_request=request)))
        verdict = {"comment_id": 70, "verdict": "resolved",
                   "reason": "The return literal is now two, as the original finding required.",
                   # The exact observed defect: the quote is a substring of the
                   # original content, but it does not cover the finding anchor.
                   "original_quote": "def value():", "current_quote": "    return 2",
                   "start_line": 2, "end_line": 2}
        native = {"review": {"general_comments": "Reviewed.", "key_issues_to_review": [],
                             "repair_recheck": verdict}}
        # The verdict validator itself stays strict for the publication paths.
        with self.assertRaisesRegex(adapter.EngineError,
                                    "original source quote does not cover the finding anchor"):
            adapter.validate_repair_verdicts(native, authenticated)
        self.assertEqual(adapter._validate_native_mapping(native, authenticated),
                         {"summary": "Reviewed.", "findings": []})
        # Ordinary review rules are not relaxed by that tolerance.
        with self.assertRaisesRegex(adapter.EngineError, "model-supplied summary"):
            adapter._validate_native_mapping({"review": {"key_issues_to_review": [], "repair_recheck": verdict}},
                                             authenticated)

    def test_malformed_authenticated_repair_context_still_fails_closed(self):
        """The verdict tolerance must not swallow an input-invalid refusal."""
        request = {"comment_id": 70, "thread_id": "T70", "original_head": "a" * 40,
                   "path": "src/example.py", "original_line": 2, "body": "Return value must be two.",
                   "original_content": "def value():\n    return 1\n",
                   # The authenticated context, not the model: no hunk header parses.
                   "fix_diff": "@@ malformed @@\n def value():\n",
                   "conversation": [{"id": 70, "author_id": 20, "body": "Return value must be two.",
                                     "updated_at": "2026-09-14T00:00:00Z"}]}
        authenticated = adapter.authenticate_input(
            signed_input(lambda document: document.update(repair_request=request)))
        verdict = {"comment_id": 70, "verdict": "resolved",
                   "reason": "The return literal is now two, as the original finding required.",
                   "original_quote": "    return 1", "current_quote": "    return 2",
                   "start_line": 2, "end_line": 2}
        native = {"review": {"general_comments": "Reviewed.", "key_issues_to_review": [],
                             "repair_recheck": verdict}}
        with self.assertRaisesRegex(adapter.EngineError, "malformed hunk header"):
            adapter._validate_native_mapping(native, authenticated)

    def test_actual_repository_config_is_valid_and_inactive_before_engine_import(self):
        source_bytes = (ROOT / "scripts/ci/pr-agent/config.toml").read_bytes()
        # The real loader consumes protected installation bytes, never a
        # checkout's ambient group-writable mode. Preserve the exact repository
        # bytes while giving this positive fixture that required boundary.
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.toml"
            config_path.write_bytes(source_bytes)
            config_path.chmod(0o444)
            with mock.patch.object(adapter, "TRUSTED_CONFIG_ROOT", config_path.parent), \
                    mock.patch.object(adapter, "_import_upstream") as import_upstream:
                config = adapter.load_trusted_config(config_path)
                self.assertFalse(any(provider["enabled"] for provider in config["providers"].values()))
                with self.assertRaisesRegex(adapter.EngineError, "no provider has trusted activation"):
                    adapter.run_engine(
                        FIXTURES / "complete-input.json", config_path=config_path,
                        source_root=Path(directory) / "unused", engine_cwd=Path(directory) / "unused-engine",
                        ledger_path=Path(directory) / "unused-ledger.jsonl",
                    )
                import_upstream.assert_not_called()

    def test_group_or_world_writable_config_is_rejected_without_repair(self):
        source_bytes = (ROOT / "scripts/ci/pr-agent/config.toml").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.toml"
            config_path.write_bytes(source_bytes)
            for mode in (0o664, 0o646):
                with self.subTest(mode=oct(mode)):
                    config_path.chmod(mode)
                    with mock.patch.object(adapter, "TRUSTED_CONFIG_ROOT", config_path.parent):
                        with self.assertRaisesRegex(adapter.EngineError, "not owned and protected"):
                            adapter.load_trusted_config(config_path)
                    self.assertEqual(config_path.stat().st_mode & 0o777, mode)
                    self.assertEqual(config_path.read_bytes(), source_bytes)

    def test_trusted_config_ignores_legacy_funding_attestation_and_rejects_counting_or_unbounded_keys(self):
        config = test_config()
        self.assertEqual(config["providers"]["deepseek"]["litellm_provider"] if "litellm_provider" in config["providers"]["deepseek"] else "deepseek", "deepseek")
        for legacy_value in (False, True):
            legacy = test_config_document()
            legacy["providers"]["deepseek"].update(
                funding_ref="legacy-funding-v1", funding_verified=legacy_value,
            )
            self.assertEqual(adapter._safe_config(legacy), config)
        disabled = test_config_document(enabled=())
        for provider in adapter.SUPPORTED_PROVIDERS:
            disabled["providers"][provider].update(
                funding_ref="legacy-funding-v1", funding_verified=True,
            )
        normalized_disabled = adapter._safe_config(disabled)
        self.assertEqual(
            {provider for provider, entry in normalized_disabled["providers"].items() if entry["enabled"]},
            set(),
        )
        self.assertEqual(
            normalized_disabled["providers"]["deepseek"],
            {"provider_id": "deepseek", "enabled": False},
        )

    def test_legacy_funding_attestation_cannot_waive_retained_activation_guards(self):
        cases = (
            ("pricing verification", "pricing_verified", False, "enabled provider lacks"),
            ("empty model", "model", "", "model or credential"),
            ("empty pricing identity", "pricing_revision", "", "pricing identity"),
            ("unapproved credential", "credential_ref", "GITHUB_TOKEN", "model or credential"),
            ("negative input price", "input_price_usd_per_token", -0.000001, "pricing is negative"),
        )
        for legacy in (False, True):
            for label, key, value, message in cases:
                with self.subTest(legacy=legacy, case=label):
                    invalid = test_config_document()
                    if legacy:
                        invalid["providers"]["deepseek"].update(
                            funding_ref="legacy-funding-v1", funding_verified=True,
                        )
                    invalid["providers"]["deepseek"][key] = value
                    with self.assertRaisesRegex(adapter.EngineError, message):
                        adapter._safe_config(invalid)
        for obsolete_key, value in (("tokenizer_id", "arbitrary"), ("tokenizer_verified", True)):
            invalid = test_config_document()
            invalid["providers"]["deepseek"][obsolete_key] = value
            with self.assertRaisesRegex(adapter.EngineError, "provider configuration is invalid"):
                adapter._safe_config(invalid)
        invalid = test_config_document()
        invalid["budget"]["input_token_cap"] = 100_000
        with self.assertRaisesRegex(adapter.EngineError, "obsolete or unknown"):
            adapter._safe_config(invalid)
        invalid = test_config_document()
        invalid["providers"]["deepseek"]["billable_categories"].append("search")
        with self.assertRaisesRegex(adapter.EngineError, "unknown or unbounded"):
            adapter._safe_config(invalid)
        invalid = test_config_document()
        invalid["providers"]["deepseek"]["context_token_limit"] = 50
        with self.assertRaisesRegex(adapter.EngineError, "context token limit"):
            adapter._safe_config(invalid)

    def test_trusted_config_enforces_approved_dollar_caps_and_order(self):
        config = test_config_document()
        for key, value in (("monthly_usd", 20.01), ("pilot_usd", 20.01), ("per_pr_usd", 1.01)):
            invalid_budget = {**config["budget"], key: value}
            with self.assertRaisesRegex(adapter.EngineError, "dollar budget"):
                adapter._safe_config({"schema": adapter.CONFIG_SCHEMA, "budget": invalid_budget,
                                      "providers": config["providers"], "provider_order": config["provider_order"]})
        invalid_budget = {**config["budget"], "monthly_usd": 0.5, "pilot_usd": 0.6}
        with self.assertRaisesRegex(adapter.EngineError, "dollar budget"):
            adapter._safe_config({"schema": adapter.CONFIG_SCHEMA, "budget": invalid_budget,
                                  "providers": config["providers"], "provider_order": config["provider_order"]})

    def test_ledger_shares_the_per_pr_cap_across_provider_fallback(self):
        config = test_config(per_pr=0.00025)["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            kwargs = dict(approval_id="fixture-approval", attempt_id="run:1", model="fixture-model",
                          priced_response_model="fixture-served-model",
                          input_price=0.000001, output_price=0.000001, context_token_limit=100,
                          output_token_cap=50, fixed_request_charge=0.0,
                          billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                          max_requests=8, max_provider_requests=2,
                          per_pr_usd=0.00025, monthly_usd=20.0, pilot_usd=20.0,
                          price_revision="fixture-price-v1")
            ledger.admit(request_id="run:1:deepseek:1", provider="deepseek", **kwargs)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "request cost budget exhausted"):
                ledger.admit(request_id="run:1:glm:1", provider="glm", **kwargs)

    def test_uncertain_reservation_is_retained(self):
        config = test_config(per_pr=0.0002)["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            reservation = ledger.admit(
                approval_id="fixture-approval", attempt_id="run:2", request_id="run:2:deepseek:1",
                provider="deepseek", model="fixture-model", priced_response_model="fixture-served-model",
                input_price=0.000001, output_price=0.000001,
                context_token_limit=100, output_token_cap=50, fixed_request_charge=0.0,
                billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                max_requests=8, max_provider_requests=2,
                per_pr_usd=0.0002, monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")
            ledger.reconcile(reservation, status="uncertain", actual_amount=None, usage=None)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "request cost budget exhausted"):
                ledger.admit(
                    approval_id="fixture-approval", attempt_id="run:2", request_id="run:2:glm:1",
                    provider="glm", model="fixture-model", priced_response_model="fixture-served-model",
                    input_price=0.000001, output_price=0.000001,
                    context_token_limit=100, output_token_cap=50, fixed_request_charge=0.0,
                    billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                    max_requests=8, max_provider_requests=2,
                    per_pr_usd=0.0002, monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")

    def test_ledger_rejects_corrupt_record_before_budget_calculation(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            path.write_text(json.dumps({"schema": adapter.LEDGER_SCHEMA, "request_id": "truncated"}) + "\n", encoding="utf-8")
            ledger = adapter.Ledger(path, config)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "invalid record"):
                ledger.admit(
                    approval_id="fixture-approval", attempt_id="run:3", request_id="run:3:deepseek:1",
                    provider="deepseek", model="fixture-model", priced_response_model="fixture-served-model",
                    input_price=0.000001,
                    output_price=0.000001, context_token_limit=100, output_token_cap=50,
                    fixed_request_charge=0.0,
                    billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                    max_requests=8, max_provider_requests=2, per_pr_usd=1.0,
                    monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")

    def test_ledger_rejects_nonfinite_record_amount(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            ledger = adapter.Ledger(path, config)
            ledger.admit(
                approval_id="fixture-approval", attempt_id="run:4", request_id="run:4:deepseek:1",
                provider="deepseek", model="fixture-model", priced_response_model="fixture-served-model",
                input_price=0.001, output_price=0.0, context_token_limit=100, output_token_cap=50,
                fixed_request_charge=0.0,
                billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                max_requests=8, max_provider_requests=2, per_pr_usd=1.0,
                monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1",
            )
            finite = ledger._records()
            self.assertEqual(finite["run:4:deepseek:1"]["reserved_amount_usd"], 0.1)
            record = json.loads(path.read_text(encoding="utf-8"))
            record["reserved_amount_usd"] = float("nan")
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(adapter.AdmissionDenied, "invalid record"):
                ledger._records()

    def test_ledger_amounts_round_up_conservatively(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            reservation = ledger.admit(
                approval_id="fixture-approval", attempt_id="run:5", request_id="run:5:deepseek:1",
                provider="deepseek", model="fixture-model", priced_response_model="fixture-served-model",
                input_price=0.0000000000001,
                output_price=0.0000000000001, context_token_limit=2, output_token_cap=1,
                fixed_request_charge=0.0000000000011,
                billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                max_requests=8, max_provider_requests=2, per_pr_usd=1.0,
                monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")
            self.assertEqual(reservation["reserved_amount_usd"], 0.000000000002)
            ledger.reconcile(reservation, status="reconciled", actual_amount=0.0000000000001,
                             usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            record = json.loads(Path(directory, "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(record["actual_amount_usd"], 0.000000000001)

    def test_ledger_uses_larger_reconciled_usage_for_future_admission(self):
        config = test_config(per_pr=0.0004)["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            reservation = ledger.admit(
                approval_id="fixture-approval", attempt_id="run:6", request_id="run:6:deepseek:1",
                provider="deepseek", model="fixture-model", priced_response_model="fixture-served-model",
                input_price=0.000001,
                output_price=0.000001, context_token_limit=100, output_token_cap=50,
                fixed_request_charge=0.0,
                billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                max_requests=8, max_provider_requests=2, per_pr_usd=0.0004,
                monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")
            ledger.reconcile(reservation, status="reconciled", actual_amount=0.0003,
                             usage={"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300})
            with self.assertRaisesRegex(adapter.AdmissionDenied, "request cost budget exhausted"):
                ledger.admit(
                    approval_id="fixture-approval", attempt_id="run:6", request_id="run:6:deepseek:2",
                    provider="deepseek", model="fixture-model", priced_response_model="fixture-served-model",
                    input_price=0.000001,
                    output_price=0.000001, context_token_limit=100, output_token_cap=50,
                    fixed_request_charge=0.0,
                    billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                    max_requests=8, max_provider_requests=2, per_pr_usd=0.0004,
                    monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")

    def test_ledger_rejects_nonfinite_admission_price(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "pricing is invalid"):
                ledger.admit(
                    approval_id="fixture-approval", attempt_id="run:7", request_id="run:7:deepseek:1",
                    provider="deepseek", model="fixture-model", priced_response_model="fixture-served-model",
                    input_price=float("nan"),
                    output_price=0.000001, context_token_limit=100, output_token_cap=50,
                    fixed_request_charge=0.0,
                    billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                    max_requests=8, max_provider_requests=2, per_pr_usd=1.0,
                    monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")

    def test_ledger_rejects_duplicate_reservation_and_mismatched_finalization(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            kwargs = dict(approval_id="fixture-approval", attempt_id="run:duplicate", model="fixture-model",
                          priced_response_model="fixture-served-model",
                          input_price=0.000001, output_price=0.000001, context_token_limit=100,
                          output_token_cap=50, fixed_request_charge=0.0,
                          billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                          max_requests=8, max_provider_requests=2,
                          per_pr_usd=1.0, monthly_usd=20.0, pilot_usd=20.0,
                          price_revision="fixture-price-v1")
            reservation = ledger.admit(request_id="run:duplicate:deepseek:1", provider="deepseek", **kwargs)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "duplicate request admission"):
                ledger.admit(request_id="run:duplicate:deepseek:1", provider="deepseek", **kwargs)
            mismatched = {**reservation, "effective_model": "other-model"}
            with self.assertRaisesRegex(adapter.AdmissionDenied, "reservation identity"):
                ledger.reconcile(mismatched, status="uncertain", actual_amount=None, usage=None)
            ledger.reconcile(reservation, status="uncertain", actual_amount=None, usage=None)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "already finalized"):
                ledger.reconcile(reservation, status="uncertain", actual_amount=None, usage=None)

    def test_ledger_rejects_unknown_usage_instead_of_refunding_reservation(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            reservation = ledger.admit(
                approval_id="fixture-approval", attempt_id="run:unknown", request_id="run:unknown:deepseek:1",
                provider="deepseek", model="fixture-model", priced_response_model="fixture-served-model",
                input_price=0.000001, output_price=0.000001,
                context_token_limit=100, output_token_cap=50, fixed_request_charge=0.0,
                billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES),
                max_requests=8, max_provider_requests=2,
                per_pr_usd=1.0, monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")
            with self.assertRaisesRegex(adapter.AdmissionDenied, "validated usage"):
                ledger.reconcile(reservation, status="reconciled", actual_amount=0.0,
                                 usage={"prompt_tokens": "unknown", "completion_tokens": 0, "total_tokens": 0})
            self.assertEqual(len(ledger._records()), 1)

    def test_request_count_cap_is_per_attempt_not_global(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            kwargs = dict(approval_id="fixture-approval", model="fixture-model",
                          priced_response_model="fixture-served-model", input_price=0.000001,
                          output_price=0.000001, context_token_limit=2, output_token_cap=1,
                          fixed_request_charge=0.0,
                          billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES), max_requests=2,
                          max_provider_requests=2, per_pr_usd=1.0, monthly_usd=20.0, pilot_usd=20.0,
                          price_revision="fixture-price-v1", provider="deepseek")
            ledger.admit(attempt_id="run:a", request_id="run:a:deepseek:1", **kwargs)
            ledger.admit(attempt_id="run:a", request_id="run:a:deepseek:2", **kwargs)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "request count"):
                ledger.admit(attempt_id="run:a", request_id="run:a:deepseek:3", **kwargs)
            ledger.admit(attempt_id="run:b", request_id="run:b:deepseek:1", **kwargs)

    def test_engine_cwd_inside_worktree_dot_git_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").write_text("gitdir: /nowhere\n", encoding="utf-8")
            with self.assertRaisesRegex(adapter.EngineError, "must not be inside a repository"):
                with adapter._isolated_environment(root, "__never_read__", "__never_read__"):
                    pass

    def test_engine_cwd_symlink_into_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "sub").mkdir(parents=True)
            (repo / ".git").write_text("gitdir: /nowhere\n", encoding="utf-8")
            link = root / "engine"
            link.symlink_to(repo / "sub", target_is_directory=True)
            with self.assertRaisesRegex(adapter.EngineError, "symlink"):
                with adapter._isolated_environment(link, "__never_read__", "__never_read__"):
                    pass

    def test_unapproved_credential_reference_is_rejected(self):
        invalid = test_config_document()
        invalid["providers"]["deepseek"]["credential_ref"] = "GITHUB_TOKEN"
        with self.assertRaisesRegex(adapter.EngineError, "model or credential"):
            adapter._safe_config(invalid)

    def test_upstream_import_does_not_leave_source_path_in_process_path(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with tempfile.TemporaryDirectory() as directory:
            source = bound_source(SOURCE_ROOT, Path(directory) / "source")
            with adapter._isolated_environment(Path(directory) / "engine", "__never_read__", "__never_read__"):
                try:
                    with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                        adapter._import_upstream(source)
                except adapter.EngineError as exc:
                    self.assertEqual(exc.error_class, "engine_unavailable")
            remaining = {
                str(Path(entry).resolve())
                for entry in sys.path
                if isinstance(entry, str) and entry
            }
            self.assertNotIn(str(source.resolve()), remaining)

    def test_upstream_import_rejects_unbound_source(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with self.assertRaisesRegex(adapter.EngineError, "immutable engine installation"):
            adapter._import_upstream(SOURCE_ROOT)

    def test_upstream_import_rejects_recomputed_manifest_after_source_forgery(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with tempfile.TemporaryDirectory() as directory:
            source = bound_source(SOURCE_ROOT, Path(directory) / "source")
            target = source / "pr_agent" / "algo" / "types.py"
            target.write_text(target.read_text(encoding="utf-8") + "\n# forged\n", encoding="utf-8")
            manifest = source / "IDENTITY"
            identity = dict(line.split("=", 1) for line in manifest.read_text().splitlines())
            identity["source_tree_sha256"] = adapter._source_tree_sha256(source)
            manifest.write_text("".join(f"{key}={value}\n" for key, value in identity.items()), encoding="utf-8")
            deployment = json.loads((source / "DEPLOYMENT_IDENTITY.json").read_text(encoding="utf-8"))
            deployment["files"]["manifest"].update(adapter._file_identity(manifest))
            (source / "DEPLOYMENT_IDENTITY.json").write_text(json.dumps(deployment), encoding="utf-8")
            with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                with self.assertRaisesRegex(adapter.EngineError, "source identity is missing"):
                    adapter._import_upstream(source)

    def test_upstream_import_rejects_deployed_adapter_config_or_tokenizer_byte_forgery(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        for relative in ("pr_agent_review.py", "config.toml", f"tokenizer-cache/{STOCK_TOKENIZER_CACHE_KEY}"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                source = bound_source(SOURCE_ROOT, Path(directory) / "source")
                target = source / relative
                target.write_text(target.read_text(encoding="utf-8") + "\n# forged\n", encoding="utf-8")
                with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                    with self.assertRaisesRegex(adapter.EngineError, "deployed engine file"):
                        adapter._import_upstream(source)

    def test_upstream_import_rejects_missing_or_forged_deployment_identity(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with tempfile.TemporaryDirectory() as directory:
            source = bound_source(SOURCE_ROOT, Path(directory) / "source")
            deployment_path = source / "DEPLOYMENT_IDENTITY.json"
            original = deployment_path.read_text(encoding="utf-8")
            deployment_path.unlink()
            with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                with self.assertRaisesRegex(adapter.EngineError, "deployment identity"):
                    adapter._import_upstream(source)
            deployment_path.write_text(original, encoding="utf-8")
            forged = json.loads(original)
            forged["files"]["default_config"]["sha256"] = "0" * 64
            deployment_path.write_text(json.dumps(forged), encoding="utf-8")
            deployment_path.chmod(0o644)
            with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                with self.assertRaisesRegex(adapter.EngineError, "does not match trusted identity"):
                    adapter._import_upstream(source)

    def test_upstream_import_rejects_supplied_bytecode(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with tempfile.TemporaryDirectory() as directory:
            source = bound_source(SOURCE_ROOT, Path(directory) / "source")
            cache = source / "pr_agent" / "__pycache__"
            cache.mkdir(mode=0o755)
            bytecode = cache / "forged.cpython-312.pyc"
            bytecode.write_bytes(b"not verified")
            bytecode.chmod(0o644)
            with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                with self.assertRaisesRegex(adapter.EngineError, "unverified bytecode"):
                    adapter._import_upstream(source)


class RealHandlerIntegrationTests(unittest.TestCase):
    """Run in a Python 3.12 environment containing the locked PR-Agent deps."""

    _network_blocked: list[str] = []
    _network_guard_installed = False

    def setUp(self):
        if os.environ.get("PR_AGENT_RUN_INTEGRATION") != "1":
            self.skipTest(
                "actual PR-Agent seam is an explicit bundle-lane proof; set "
                "PR_AGENT_RUN_INTEGRATION=1 with PR_AGENT_TEST_PYTHON and "
                "PR_AGENT_TEST_SOURCE_ROOT to run it"
            )
        if not type(self)._network_guard_installed:
            type(self)._network_blocked = []

            def deny_network(event, args):
                if event in {
                    "socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg",
                }:
                    type(self)._network_blocked.append(event)
                    raise RuntimeError("real-handler integration denies outbound network")

            sys.addaudithook(deny_network)
            type(self)._network_guard_installed = True
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.fail(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source_root = bound_source(SOURCE_ROOT, self.root / "source")
        stock_tokenizer = self.source_root / "tokenizer-cache" / STOCK_TOKENIZER_CACHE_KEY
        self.assertEqual(adapter._file_identity(stock_tokenizer), {
            "sha256": STOCK_TOKENIZER_ASSET_SHA256,
            "byte_length": STOCK_TOKENIZER_ASSET_BYTES,
        }, "the actual-handler lane must use the real pinned stock o200k_base asset")
        self.trusted_engine_root = mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", self.source_root)
        self.trusted_engine_root.start()
        self.addCleanup(self.trusted_engine_root.stop)
        self.input_path = self.root / "input.json"
        self.input_path.write_text(json.dumps(json.loads((FIXTURES / "complete-input.json").read_text()), indent=2), encoding="utf-8")
        self.config_path = self.root / "config.toml"
        self.config_path.write_text(
            "schema = \"lmdj.pr-agent-config.v1\"\nprovider_order = [\"deepseek\"]\n\n"
            "[budget]\napproval_id = \"fixture-approval\"\ntimezone = \"Asia/Shanghai\"\nmonthly_usd = 20.0\n"
            "pilot_usd = 20.0\nper_pr_usd = 1.0\nmax_requests = 8\nmax_requests_per_provider = 2\n"
            "request_timeout_seconds = 7\nbackoff_seconds = 0\nengine_deadline_seconds = 600\n"
            "output_token_cap = 50\n\n[providers.deepseek]\n"
            "enabled = true\nendpoint = \"https://deepseek.invalid.example/v1\"\nmodel = \"fixture-deepseek-model\"\n"
            "priced_response_model = \"fixture-deepseek-served\"\ncontext_token_limit = 16384\n"
            "credential_ref = \"PR_AGENT_DEEPSEEK_API_KEY\"\npricing_revision = \"fixture-price-v1\"\n"
            "input_price_usd_per_token = 0.000001\noutput_price_usd_per_token = 0.000001\n"
            "fixed_request_charge_usd = 0.0\nbillable_categories = [\"input_tokens\", \"output_tokens\", \"fixed_request\"]\n"
            "pricing_verified = true\n\n"
            "[providers.glm]\nenabled = false\n\n[providers.xai]\nenabled = false\n\n"
            "[providers.kimi]\nenabled = false\n",
            encoding="utf-8",
        )
        # This is an installation fixture, not a writable checkout. Keep the
        # generated runtime configuration protected under permissive umasks so
        # the actual loader exercises its normal trust boundary.
        self.config_path.chmod(0o644)

    def run_with_fake(self, fake, *, reset_stock_tokenizer=False):
        hostile = self.root / "engine"
        hostile.mkdir()
        (hostile / "pyproject.toml").write_text("not = [valid", encoding="utf-8")
        (hostile / ".pr_agent.toml").write_text("PR_AGENT_TEST_KEY = 'must not be read'", encoding="utf-8")
        ledger = self.root / "ledger.jsonl"
        with adapter._isolated_environment(hostile, "__never_read__", "__never_read__"):
            upstream = adapter._import_upstream(self.source_root)
        if reset_stock_tokenizer:
            token_encoder = sys.modules["pr_agent.algo.token_handler"].TokenEncoder
            token_encoder._encoder_instance = None
            token_encoder._model = None
        async def fake_with_raw_observer(**kwargs):
            """Explicitly mock the raw-observer boundary for seam-only tests."""
            response = await fake(**kwargs)
            context = adapter._REQUEST_CONTEXT.get()
            if context is not None and kwargs.get("model") != "fixture-glm-model":
                context["raw_observation_count"] = 1
                context["raw_usage"] = adapter._usage_from_response(response)
                context["raw_usage_invalid"] = context["raw_usage"] is None
            return response

        upstream["litellm_ai_handler"].acompletion = fake_with_raw_observer
        with mock.patch.object(adapter, "_import_upstream", return_value=upstream), \
                mock.patch.object(adapter, "TRUSTED_CONFIG_ROOT", self.root), \
                mock.patch.dict(os.environ, {"PR_AGENT_DEEPSEEK_API_KEY": "fixture-secret", "PR_AGENT_ZAI_API_KEY": "fixture-zai-secret", "GITHUB_TOKEN": "must-not-leak",
                                              "PR_AGENT_CONFIG_BRANCH": "must-not-read", "DYNACONF_CONFIG__MODEL": "must-not-read",
                                              "OPENAI_API_KEY": "must-not-read"}, clear=False):
            return adapter.run_engine(self.input_path, config_path=self.config_path, source_root=self.source_root,
                                      engine_cwd=hostile, ledger_path=ledger), upstream, ledger

    def run_with_wire_transport(self, response_factory):
        """Run the real handler while replacing only LiteLLM's HTTP transports."""
        hostile = self.root / "engine"
        hostile.mkdir(exist_ok=True)
        (hostile / "pyproject.toml").write_text("not = [valid", encoding="utf-8")
        (hostile / ".pr_agent.toml").write_text("PR_AGENT_TEST_KEY = 'must not be read'", encoding="utf-8")
        ledger = self.root / "wire-ledger.jsonl"
        with adapter._isolated_environment(hostile, "__never_read__", "__never_read__"):
            upstream = adapter._import_upstream(self.source_root)
        httpx = upstream["litellm_ai_handler"].httpx
        from litellm.llms.custom_httpx.aiohttp_transport import LiteLLMAiohttpTransport

        async def fake_transport(_transport, request):
            return await response_factory(httpx, request)

        with mock.patch.object(httpx.AsyncHTTPTransport, "handle_async_request", fake_transport), \
                mock.patch.object(LiteLLMAiohttpTransport, "handle_async_request", fake_transport), \
                mock.patch.object(adapter, "_import_upstream", return_value=upstream), \
                mock.patch.object(adapter, "TRUSTED_CONFIG_ROOT", self.root), \
                mock.patch.dict(os.environ, {
                    "PR_AGENT_DEEPSEEK_API_KEY": "fixture-secret",
                    "GITHUB_TOKEN": "must-not-leak",
                    "PR_AGENT_CONFIG_BRANCH": "must-not-read",
                    "DYNACONF_CONFIG__MODEL": "must-not-read",
                    "OPENAI_API_KEY": "must-not-read",
                }, clear=False):
            result = adapter.run_engine(
                self.input_path, config_path=self.config_path, source_root=self.source_root,
                engine_cwd=hostile, ledger_path=ledger,
            )
        self.assertEqual(type(self)._network_blocked, [])
        return result, upstream, ledger

    def configure_flash_fixture(self, *, context_limit=32_768):
        config = self.config_path.read_text()
        config = re.sub(r"output_token_cap = \d+", "output_token_cap = 4096", config)
        config = config.replace("endpoint = \"https://deepseek.invalid.example/v1\"", "endpoint = \"https://api.deepseek.com\"")
        config = config.replace("model = \"fixture-deepseek-model\"", "model = \"deepseek/deepseek-flash\"")
        config = config.replace("priced_response_model = \"fixture-deepseek-served\"", "priced_response_model = \"deepseek-flash\"")
        config = re.sub(r"context_token_limit = \d+", f"context_token_limit = {context_limit}", config)
        self.config_path.write_text(
            config,
            encoding="utf-8",
        )
        self.config_path.chmod(0o644)

    async def assert_flash_wire(self, httpx, request):
        body = json.loads((await request.aread()).decode("utf-8"))
        self.assertEqual(request.method, "POST")
        self.assertEqual(str(request.url), "https://api.deepseek.com/chat/completions")
        self.assertEqual(body["model"], "deepseek-flash")
        self.assertEqual(body["max_tokens"], 4096)
        self.assertNotIn("max_completion_tokens", body)
        # DeepSeek V4 thinks by default; the engine asks for plain output.
        self.assertEqual(body["thinking"], {"type": "disabled"})
        for forbidden in ("reasoning_effort", "tools", "tool_choice", "web_search_options", "service_tier"):
            self.assertNotIn(forbidden, body)
        self.assertEqual(request.headers["authorization"], "Bearer fixture-secret")
        return body

    async def flash_response(self, httpx, request, *, usage=_UNSET_USAGE, content=None, finish_reason="stop"):
        await self.assert_flash_wire(httpx, request)
        if usage is _UNSET_USAGE:
            usage = {
                "prompt_tokens": 100, "completion_tokens": 4096, "total_tokens": 4196,
                "completion_tokens_details": {"reasoning_tokens": 4000},
            }
        if content is None:
            content = (FIXTURES / "valid-native-review.yaml").read_text(encoding="utf-8")
        payload = {
            "id": "wire-synthetic", "object": "chat.completion", "created": 0,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "finish_reason": finish_reason,
                         "message": {"role": "assistant", "content": content,
                                     "reasoning_content": "Synthetic reasoning"}}],
        }
        if usage is not None:
            payload["usage"] = usage
        return httpx.Response(200, request=request, json=payload)

    def test_flash_real_handler_disables_thinking_on_the_wire_and_prices_full_usage(self):
        self.configure_flash_fixture()
        wire_calls = []

        async def response_factory(httpx, request):
            wire_calls.append(request)
            return await self.flash_response(httpx, request)

        result, _upstream, ledger = self.run_with_wire_transport(response_factory)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["selected_attempt"], 0)
        attempt = result["attempts"][0]
        self.assertEqual(len(wire_calls), 1)
        self.assertEqual(attempt["usage"]["num_ai_calls"], len(wire_calls))
        self.assertTrue(attempt["coverage"]["complete"])
        self.assertEqual(attempt["coverage"]["input_sha256"], result["input_sha256"])
        self.assertEqual(attempt["model"], {
            "requested": "deepseek/deepseek-flash", "actual": "deepseek-flash",
            "response_version": None, "pricing_revision": "fixture-price-v1",
        })
        self.assertEqual(attempt["usage"]["prompt_tokens"], 100)
        self.assertEqual(attempt["usage"]["completion_tokens"], 4096)
        self.assertEqual(attempt["usage"]["total_tokens"], 4196)
        request_timeout = wire_calls[0].extensions.get("timeout")
        self.assertIsNotNone(request_timeout)
        if isinstance(request_timeout, dict):
            self.assertLessEqual(max(request_timeout.values()), 7)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "reconciled"])
        self.assertEqual(records[0]["request_id"], records[-1]["request_id"])
        self.assertEqual(records[0]["provider"], "deepseek")
        self.assertEqual(records[0]["effective_model"], "deepseek/deepseek-flash")
        self.assertEqual(records[0]["reservation_basis"]["output_token_cap"], 4096)
        self.assertEqual(records[0]["reserved_amount_usd"], 0.036864)
        self.assertEqual(records[-1]["actual_amount_usd"], 0.004196)
        self.assertEqual(records[-1]["usage"], {
            "prompt_tokens": 100, "completion_tokens": 4096, "total_tokens": 4196,
        })
        self.assertNotIn("fixture-secret", ledger.read_text(encoding="utf-8"))
        self.assertNotIn("fixture-secret", json.dumps(result))

    def test_flash_real_handler_contradictory_reasoning_retains_unknown_reservation(self):
        self.configure_flash_fixture()
        wire_calls = []

        async def response_factory(httpx, request):
            wire_calls.append(request)
            return await self.flash_response(
                httpx, request,
                usage={
                    "prompt_tokens": 100, "completion_tokens": 96, "total_tokens": 196,
                    "completion_tokens_details": {"reasoning_tokens": 4000},
                },
            )

        result, _upstream, ledger = self.run_with_wire_transport(
            response_factory
        )
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "invalid_output")
        self.assertEqual(len(wire_calls), 1)
        self.assertEqual(result["attempts"][0]["usage"]["num_ai_calls"], len(wire_calls))
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
        self.assertIsNone(records[-1]["actual_amount_usd"])
        self.assertIsNone(records[-1]["usage"])

    def test_flash_real_handler_length_stop_with_empty_output_never_fabricates_clean_review(self):
        self.configure_flash_fixture()
        wire_calls = []

        async def response_factory(httpx, request):
            wire_calls.append(request)
            return await self.flash_response(httpx, request, content="", finish_reason="length")

        result, _upstream, ledger = self.run_with_wire_transport(response_factory)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertIsNone(result["review"] if "review" in result else None)
        self.assertNotIn("clean review", json.dumps(result).casefold())
        self.assertEqual(len(wire_calls), 1)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "reconciled"])
        self.assertEqual(records[-1]["actual_amount_usd"], 0.004196)
        self.assertEqual(records[-1]["usage"], {
            "prompt_tokens": 100, "completion_tokens": 4096, "total_tokens": 4196,
        })

    def test_flash_real_handler_missing_or_invalid_usage_retains_unknown_reservation(self):
        self.configure_flash_fixture()
        cases = {
            "absent-usage": None,
            "absent-prompt": {"completion_tokens": 4096, "total_tokens": 4096},
            "absent-completion": {"prompt_tokens": 100, "total_tokens": 100},
            "null-prompt": {"prompt_tokens": None, "completion_tokens": 4096, "total_tokens": 4196},
            "null-completion": {"prompt_tokens": 100, "completion_tokens": None, "total_tokens": 100},
            "bool-prompt": {"prompt_tokens": True, "completion_tokens": 4096, "total_tokens": 4197},
            "bool-completion": {"prompt_tokens": 100, "completion_tokens": False, "total_tokens": 100},
            "string-prompt": {"prompt_tokens": "100", "completion_tokens": 4096, "total_tokens": 4196},
            "string-completion": {"prompt_tokens": 100, "completion_tokens": "4096", "total_tokens": 4196},
            "contradictory-total": {"prompt_tokens": 100, "completion_tokens": 4096, "total_tokens": 4195},
        }
        for label, usage in cases.items():
            with self.subTest(case=label, usage=usage):
                wire_calls = []

                async def response_factory(httpx, request):
                    wire_calls.append(request)
                    return await self.flash_response(httpx, request, usage=usage)

                result, _upstream, ledger = self.run_with_wire_transport(response_factory)
                self.assertEqual(result["status"], "not-reviewed")
                self.assertEqual(len(wire_calls), 1)
                records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
                self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
                self.assertIsNone(records[-1]["actual_amount_usd"])
                self.assertIsNone(records[-1]["usage"])
                shutil.rmtree(self.root / "engine")
                ledger.unlink()

    def test_flash_raw_observation_is_not_stale_across_requests_and_guard_is_restored(self):
        self.configure_flash_fixture()
        first_calls = []

        async def first_response(httpx, request):
            first_calls.append(request)
            return await self.flash_response(httpx, request)

        first_result, _upstream, first_ledger = self.run_with_wire_transport(first_response)
        self.assertEqual(first_result["status"], "reviewed")
        self.assertEqual(len(first_calls), 1)
        from litellm.llms.deepseek.chat.transformation import DeepSeekChatConfig

        self.assertNotIn("transform_response", DeepSeekChatConfig.__dict__)
        first_ledger.unlink()

        second_calls = []

        async def second_response(httpx, request):
            second_calls.append(request)
            return await self.flash_response(httpx, request, usage=None)

        second_result, _upstream, second_ledger = self.run_with_wire_transport(second_response)
        self.assertEqual(second_result["status"], "not-reviewed")
        self.assertEqual(second_result["attempts"][0]["error_class"], "invalid_output")
        self.assertEqual(len(second_calls), 1)
        records = [json.loads(line) for line in second_ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
        self.assertIsNone(records[-1]["actual_amount_usd"])
        self.assertIsNone(records[-1]["usage"])
        self.assertNotIn("transform_response", DeepSeekChatConfig.__dict__)

    def test_flash_real_handler_output_and_context_breaches_reconcile_and_hold_future_admission(self):
        cases = {
            "output": (32_768, {"prompt_tokens": 100, "completion_tokens": 4097, "total_tokens": 4197}, 0.004197),
            "context": (8_192, {"prompt_tokens": 4097, "completion_tokens": 4096, "total_tokens": 8193}, 0.008193),
        }
        for kind, (context_limit, usage, expected_actual) in cases.items():
            with self.subTest(kind=kind):
                self.configure_flash_fixture(context_limit=context_limit)
                wire_calls = []

                async def response_factory(httpx, request):
                    wire_calls.append(request)
                    return await self.flash_response(httpx, request, usage=usage)

                result, _upstream, ledger_path = self.run_with_wire_transport(response_factory)
                self.assertEqual(result["status"], "not-reviewed")
                self.assertEqual(result["attempts"][0]["error_class"], "invalid_parameter")
                self.assertEqual(len(wire_calls), 1)
                records = [json.loads(line) for line in ledger_path.read_text().splitlines()]
                self.assertEqual([record["status"] for record in records], ["reserved", "reconciled"])
                self.assertTrue(records[-1]["envelope_breach"])
                self.assertAlmostEqual(records[-1]["actual_amount_usd"], expected_actual, places=9)
                self.assert_envelope_held(ledger_path, records, kind)
                shutil.rmtree(self.root / "engine")
                ledger_path.unlink()

    def test_flash_real_handler_known_breach_survives_invalid_accounting_and_parser_paths(self):
        cases = {
            "output-reasoning-invalid": {
                "context_limit": 32_768,
                "usage": {
                    "prompt_tokens": 100, "completion_tokens": 4097, "total_tokens": 4197,
                    "completion_tokens_details": {"reasoning_tokens": 5000},
                },
            },
            "output-normalized-disagreement": {
                "context_limit": 32_768,
                "usage": {"prompt_tokens": 100, "completion_tokens": 4097},
            },
            "context-normalized-disagreement": {
                "context_limit": 8_192,
                "usage": {"prompt_tokens": 4097, "completion_tokens": 4096},
            },
            "output-parser-failure": {
                "context_limit": 32_768,
                "usage": {"prompt_tokens": 100, "completion_tokens": 4097, "total_tokens": 4197},
                "malformed_choices": True,
            },
            "output-partial-invalid-prompt": {
                "context_limit": 32_768,
                "usage": {"prompt_tokens": "invalid", "completion_tokens": 4097, "total_tokens": "invalid"},
            },
            "context-partial-invalid-completion": {
                "context_limit": 8_192,
                "usage": {"prompt_tokens": 8193, "completion_tokens": "invalid", "total_tokens": "invalid"},
            },
            "context-two-counts-disagreeing-total": {
                "context_limit": 8_192,
                "usage": {"prompt_tokens": 4097, "completion_tokens": 4096, "total_tokens": 1},
            },
        }
        for label, case in cases.items():
            with self.subTest(case=label):
                ledger_path = self.root / "wire-ledger.jsonl"
                try:
                    self.configure_flash_fixture(context_limit=case["context_limit"])
                    wire_calls = []

                    async def response_factory(httpx, request):
                        wire_calls.append(request)
                        response = await self.flash_response(httpx, request, usage=case["usage"])
                        if case.get("malformed_choices"):
                            payload = response.json()
                            payload["choices"] = []
                            response = httpx.Response(200, request=request, json=payload)
                        return response

                    result, _upstream, ledger_path = self.run_with_wire_transport(response_factory)
                    self.assertEqual(result["status"], "not-reviewed")
                    self.assertEqual(result["attempts"][0]["error_class"], "invalid_parameter")
                    self.assertEqual(len(wire_calls), 1)
                    records = [json.loads(line) for line in ledger_path.read_text().splitlines()]
                    self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
                    final = records[-1]
                    self.assertTrue(final["envelope_breach"])
                    self.assertEqual(final["reserved_amount_usd"], records[0]["reserved_amount_usd"])
                    self.assertIsNone(final["actual_amount_usd"])
                    self.assertIsNone(final["usage"])
                    self.assert_envelope_held(ledger_path, records, label)
                finally:
                    if (self.root / "engine").exists():
                        shutil.rmtree(self.root / "engine")
                    if ledger_path.exists():
                        ledger_path.unlink()

    def test_flash_real_handler_transport_timeout_is_one_call_with_uncertain_reservation(self):
        self.configure_flash_fixture()
        wire_calls = []

        async def response_factory(httpx, request):
            wire_calls.append(request)
            await self.assert_flash_wire(httpx, request)
            raise httpx.ReadTimeout("transport timed out fixture", request=request)

        result, _upstream, ledger = self.run_with_wire_transport(response_factory)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "timeout")
        self.assertEqual(len(wire_calls), 1)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
        self.assertIsNone(records[-1]["actual_amount_usd"])
        self.assertIsNone(records[-1]["usage"])

    def test_flash_real_handler_transient_http_failure_uses_one_supported_retry(self):
        self.configure_flash_fixture()
        wire_calls = []

        async def response_factory(httpx, request):
            wire_calls.append(request)
            if len(wire_calls) == 1:
                await request.aread()
                return httpx.Response(503, request=request, json={"error": {"message": "temporary fixture"}})
            return await self.flash_response(httpx, request)

        result, _upstream, ledger = self.run_with_wire_transport(response_factory)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(len(wire_calls), 2)
        self.assertEqual(result["attempts"][0]["usage"]["num_ai_calls"], 2)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain", "reserved", "reconciled"])
        self.assertEqual(len({record["request_id"] for record in records}), 2)

    def test_flash_real_handler_permanent_http_error_retains_unknown_reservation(self):
        self.configure_flash_fixture()
        wire_calls = []

        async def response_factory(httpx, request):
            wire_calls.append(request)
            await request.aread()
            return httpx.Response(400, request=request, json={"error": {"message": "permanent fixture"}})

        result, _upstream, ledger = self.run_with_wire_transport(response_factory)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(len(wire_calls), 1)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
        self.assertIsNone(records[-1]["actual_amount_usd"])
        self.assertIsNone(records[-1]["usage"])

    @staticmethod
    def with_glm_fallback(config: str) -> str:
        glm = (
            "[providers.glm]\nenabled = true\nendpoint = \"https://glm.invalid.example/v1\"\n"
            "model = \"fixture-glm-model\"\npriced_response_model = \"fixture-glm-served\"\n"
            "context_token_limit = 16384\ncredential_ref = \"PR_AGENT_ZAI_API_KEY\"\n"
            "pricing_revision = \"fixture-price-v1\"\ninput_price_usd_per_token = 0.000001\n"
            "output_price_usd_per_token = 0.000001\nfixed_request_charge_usd = 0.0\n"
            "billable_categories = [\"input_tokens\", \"output_tokens\", \"fixed_request\"]\n"
            "pricing_verified = true"
        )
        return config.replace(
            'provider_order = ["deepseek"]', 'provider_order = ["deepseek", "glm"]',
        ).replace("[providers.glm]\nenabled = false", glm)

    def assert_envelope_held(self, ledger_path: Path, records: list[dict], label: str) -> None:
        basis = records[0]["reservation_basis"]
        ledger = adapter.Ledger(ledger_path, test_config()["budget"])
        before = ledger_path.read_text(encoding="utf-8")
        with self.assertRaisesRegex(adapter.AdmissionDenied, "held for operator review"):
            ledger.admit(
                approval_id="fixture-approval", attempt_id=f"future-{label}",
                request_id=f"future-{label}:deepseek:1", provider="deepseek",
                model=records[0]["effective_model"], priced_response_model=basis["priced_response_model"],
                input_price=basis["input_price_usd_per_token"],
                output_price=basis["output_price_usd_per_token"],
                context_token_limit=basis["context_token_limit"], output_token_cap=basis["output_token_cap"],
                fixed_request_charge=basis["fixed_request_charge_usd"],
                billable_categories=basis["billable_categories"], max_requests=8,
                max_provider_requests=2, per_pr_usd=1.0, monthly_usd=20.0,
                pilot_usd=20.0, price_revision=records[0]["price_revision"],
            )
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), before)

    def test_stock_reviewer_receives_every_authenticated_segment_and_captures_native_output(self):
        calls = []
        response_text = (FIXTURES / "valid-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            self.assertEqual(os.environ.get("DEEPSEEK_API_KEY"), "fixture-secret")
            for name in ("GITHUB_TOKEN", "PR_AGENT_CONFIG_BRANCH", "DYNACONF_CONFIG__MODEL", "OPENAI_API_KEY"):
                self.assertIsNone(os.environ.get(name), name)
            return FakeCompletion({"model": "fixture-deepseek-served", "model_version": "fixture-version-1",
                                   "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})

        result, upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["selected_attempt"], 0)
        attempt = result["attempts"][0]
        self.assertTrue(attempt["coverage"]["complete"])
        self.assertEqual(attempt["engine"]["source_commit"], adapter.UPSTREAM_COMMIT)
        self.assertEqual(attempt["model"], model_identity(version="fixture-version-1"))
        self.assertEqual(attempt["coverage"]["model"], attempt["model"])
        self.assertEqual(attempt["engine"]["bundle"]["adapter_sha256"], adapter._file_identity(Path(adapter.__file__))["sha256"])
        self.assertEqual(attempt["engine"]["runtime_config"], adapter._file_identity(self.config_path))
        self.assertEqual(attempt["review"]["findings"][0]["path"], "src/example.py")
        self.assertEqual(len(calls), 1, "why: one complete prompt is the pilot contract; remedy: disable hidden chunk/retry paths")
        self.assertEqual(attempt["coverage"]["input_sha256"], result["input_sha256"])
        self.assertEqual(calls[0]["max_tokens"], 50)
        self.assertGreater(calls[0]["timeout"], 0)
        self.assertLessEqual(calls[0]["timeout"], 7)
        self.assertEqual(calls[0]["num_retries"], 0)
        self.assertEqual(calls[0]["max_retries"], 0)
        prompt = "\n".join(str(item.get("content", "")) for item in calls[0]["messages"])
        self.assertIn("nonempty review.general_comments summary", prompt)
        system_prompt = next(item["content"] for item in calls[0]["messages"] if item["role"] == "system")
        example = system_prompt.split("Example output:\n", 1)[1].split("Write your own summary", 1)[0]
        self.assertNotIn("```", example)
        # Validate the example actually sent through the real PRReviewer and
        # LiteLLM handler. The upstream example asks for fields our consumer
        # rejects even when their feature flags are disabled.
        example_native = adapter._strict_native_yaml(upstream, example)
        self.assertEqual(set(example_native["review"]), {"general_comments", "key_issues_to_review"})
        self.assertNotIn("relevant_tests", system_prompt)
        self.assertNotIn("security_concerns", system_prompt)
        for expected in ("return 1", "return 2", "removed content", "src-example-h1", "obsolete-h1"):
            self.assertIn(expected, prompt)
        self.assertNotIn("must-not-leak", prompt)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({record["status"] for record in records}, {"reserved", "reconciled"})
        self.assertEqual(records[0]["reserved_amount_usd"], 0.016434)
        self.assertEqual(records[0]["reservation_basis"], {
            "context_token_limit": 16384,
            "output_token_cap": 50,
            "input_price_usd_per_token": 0.000001,
            "output_price_usd_per_token": 0.000001,
            "fixed_request_charge_usd": 0.0,
            "billable_categories": list(adapter.BOUNDED_BILLABLE_CATEGORIES),
            "priced_response_model": "fixture-deepseek-served",
        })
        self.assertNotIn("fixture-secret", ledger.read_text(encoding="utf-8"))
        self.assertEqual(
            list(self.source_root.rglob("*.pyc")), [],
            "why: the trusted source must not acquire unverified bytecode during import; "
            "remedy: keep PYTHONDONTWRITEBYTECODE enabled for the engine boundary",
        )

    def test_repair_context_crosses_real_handler_and_verdict_resolves_selected_thread(self):
        from ci_review_recheck_test import Platform, native_fixture
        api = Platform()
        self.addCleanup(api.history.source.tearDown)
        request = api.collect()
        self.input_path.write_text(json.dumps(api.document), encoding="utf-8")
        calls = []

        async def completion(**kwargs):
            calls.append(kwargs)
            prompt = "\n".join(m["content"] for m in kwargs["messages"])
            self.assertIn(adapter.repair_prompt_block(request), prompt)
            self.assertIn("An author saying fixed/done", prompt)
            self.assertIsNone(os.environ.get("GITHUB_TOKEN"))
            # Return the quote syntax actually shown at the real handler seam,
            # rather than bypassing YAML formatting with a JSON response.
            quote_example = prompt.split("Source quote encoding example:\n", 1)[1].split("End source quote example.", 1)[0]
            expected = native_fixture()["review"]["repair_recheck"]
            response_yaml = ("review:\n  general_comments: The changed return value is two.\n"
                             "  key_issues_to_review: []\n  repair_recheck:\n"
                             "    comment_id: 70\n    verdict: resolved\n"
                             + "    reason: " + json.dumps(expected["reason"]) + "\n"
                             + "    start_line: 2\n    end_line: 2\n" + quote_example)
            return FakeCompletion({"model": "fixture-deepseek-served", "model_version": "fixture-version-1",
                                   "choices": [{"message": {"content": response_yaml}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})

        result, _, ledger = self.run_with_fake(completion)
        self.assertEqual(result["status"], "reviewed", result)
        attempt = result["attempts"][result["selected_attempt"]]
        self.assertTrue(attempt["coverage"]["complete"])
        self.assertEqual(attempt["native_review"], native_fixture())
        self.assertTrue(api.publish(attempt["native_review"])["resolved"])
        self.assertEqual(api.writes, ["reply", "resolveReviewThread"])
        self.assertEqual(len(calls), 1)
        self.assertEqual([json.loads(line)["status"] for line in ledger.read_text().splitlines()], ["reserved", "reconciled"])

    def test_push_batch_crosses_real_handler_once_and_resolves_each_thread(self):
        from ci_review_recheck_test import BatchPlatform
        api = BatchPlatform()
        self.addCleanup(api.history.source.tearDown)
        requests, _ = api.collect_batch()
        self.input_path.write_text(json.dumps(api.document), encoding="utf-8")
        calls = []

        async def completion(**kwargs):
            import yaml
            calls.append(kwargs)
            prompt = "\n".join(m["content"] for m in kwargs["messages"])
            for request in requests:
                self.assertIn(adapter.repair_prompt_block(request), prompt)
            self.assertIn("repair_rechecks, a YAML list", prompt)
            self.assertIsNone(os.environ.get("GITHUB_TOKEN"))
            numbered = json.loads(prompt.split("BEGIN LMDJ REPAIR CURRENT SOURCE\n", 1)[1].split("\nEND LMDJ REPAIR CURRENT SOURCE", 1)[0])
            quoted = next(row for row in numbered["lines"] if row["text"] == "    return 2")
            native = api.native()
            for verdict in native["review"]["repair_rechecks"]:
                verdict.update(current_quote=quoted["text"], start_line=quoted["line"], end_line=quoted["line"])
            return FakeCompletion({"model": "fixture-deepseek-served",
                "choices": [{"message": {"content": yaml.safe_dump(native, default_style='"')}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})

        result, _, ledger = self.run_with_fake(completion)
        self.assertEqual(result["status"], "reviewed", result)
        attempt = result["attempts"][result["selected_attempt"]]
        self.assertTrue(attempt["coverage"]["complete"])
        receipt = api.publish_batch(attempt["native_review"])
        self.assertEqual(len(receipt["receipts"]), 2)
        self.assertEqual(api.states, {"T70": True, "T71": True})
        self.assertEqual(len(calls), 1)
        self.assertEqual([json.loads(line)["status"] for line in ledger.read_text().splitlines()], ["reserved", "reconciled"])

    def test_stock_reviewer_without_funding_uses_only_the_review_post(self):
        """The actual stock handler must reach review transport without balance work."""
        response_text = (FIXTURES / "valid-native-review.yaml").read_text(encoding="utf-8")
        wire_calls = []

        async def response_factory(httpx, request):
            wire_calls.append(request.method)
            self.assertEqual(request.method, "POST")
            return httpx.Response(200, request=request, json={
                "id": "wire-synthetic", "object": "chat.completion", "created": 0,
                "model": "fixture-deepseek-served",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": response_text}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            })

        result, _upstream, ledger = self.run_with_wire_transport(response_factory)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(wire_calls, ["POST"])
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "reconciled"])

    def test_stock_reviewer_starts_from_pinned_cache_with_empty_ambient_cache_and_no_http(self):
        calls = []
        tokenizer_http_calls = []
        ambient_cache = self.root / "empty-ambient-tokenizer-cache"
        ambient_cache.mkdir()
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        def forbidden_get(url, *args, **kwargs):
            tokenizer_http_calls.append(str(url))
            raise AssertionError("stock tokenizer attempted runtime HTTP")

        with mock.patch.dict(os.environ, {"TIKTOKEN_CACHE_DIR": str(ambient_cache)}, clear=False), \
                mock.patch("requests.get", side_effect=forbidden_get):
            result, _upstream, _ledger = self.run_with_fake(
                fake_acompletion, reset_stock_tokenizer=True,
            )
            self.assertEqual(os.environ["TIKTOKEN_CACHE_DIR"], str(ambient_cache))
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(tokenizer_http_calls, [])
        self.assertEqual(list(ambient_cache.iterdir()), [])
        self.assertEqual(sys.modules["pr_agent.algo.token_handler"].TokenEncoder._encoder_instance.name, "o200k_base")

    def test_non_deepseek_fallback_keeps_stock_handler_and_normalized_ledger_accounting(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        self.config_path.write_text(self.with_glm_fallback(self.config_path.read_text()))
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            if kwargs["model"] == "fixture-deepseek-model":
                raise RuntimeError("503 temporary fixture")
            return FakeCompletion({
                "model": "fixture-glm-served",
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["selected_attempt"], 1)
        self.assertEqual([call["model"] for call in calls], [
            "fixture-deepseek-model", "fixture-deepseek-model", "fixture-glm-model",
        ])
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["status"] for record in records], [
            "reserved", "uncertain", "reserved", "uncertain", "reserved", "reconciled",
        ])
        self.assertEqual(records[-1]["provider"], "glm")
        self.assertEqual(records[-1]["usage"], {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    def test_nonstop_or_missing_finish_reason_rejects_parseable_actual_output_without_retry(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        for finish_reason in ("length", "content_filter", None):
            with self.subTest(finish_reason=finish_reason):
                calls = []
                choice = {"message": {"content": response_text}}
                if finish_reason is not None:
                    choice["finish_reason"] = finish_reason

                async def fake_acompletion(**kwargs):
                    calls.append(kwargs)
                    return FakeCompletion({
                        "model": "fixture-deepseek-served",
                        "choices": [choice],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    })

                result, _upstream, ledger = self.run_with_fake(fake_acompletion)
                self.assertEqual(result["status"], "not-reviewed")
                self.assertEqual(result["attempts"][0]["error_class"], "invalid_output")
                self.assertEqual(result["attempts"][0]["usage"]["prompt_tokens"], 10)
                self.assertIn(f"finish_reason={finish_reason or 'unknown'}", result["attempts"][0]["error"])
                self.assertEqual(len(calls), 1)
                self.assertEqual(
                    {json.loads(line)["status"] for line in ledger.read_text().splitlines()},
                    {"reserved", "reconciled"},
                )
                shutil.rmtree(self.root / "engine")
                ledger.unlink()

    def test_missing_or_invalid_usage_rejects_parseable_actual_output_and_retains_reservation(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        for usage in (None, {"prompt_tokens": "unknown", "completion_tokens": 5, "total_tokens": 5}):
            with self.subTest(usage=usage):
                calls = []

                async def fake_acompletion(**kwargs):
                    calls.append(kwargs)
                    response = FakeCompletion({
                        "model": "fixture-deepseek-served",
                        "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                        "_hidden_params": {"additional_headers": {
                            "llm_provider-x-litellm-response-cost": "0.25",
                        }},
                    })
                    if usage is not None:
                        response["usage"] = usage
                    return response

                result, _upstream, ledger = self.run_with_fake(fake_acompletion)
                self.assertEqual(result["status"], "not-reviewed")
                self.assertEqual(result["attempts"][0]["error_class"], "invalid_output")
                self.assertFalse(result["attempts"][0]["coverage"]["complete"])
                self.assertEqual(len(calls), 1)
                records = [json.loads(line) for line in ledger.read_text().splitlines()]
                self.assertEqual({record["status"] for record in records}, {"reserved", "uncertain"})
                final = next(record for record in records if record["status"] == "uncertain")
                self.assertEqual(final["reserved_amount_usd"], 0.016434)
                self.assertIsNone(final["actual_amount_usd"])
                self.assertIsNone(final["usage"])
                shutil.rmtree(self.root / "engine")
                ledger.unlink()

    def test_litellm_estimated_charge_headers_cannot_override_priced_usage(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        estimates = (0, "0.000001", "0.25", "not-a-number")
        for estimate in estimates:
            with self.subTest(estimate=estimate):
                calls = []

                async def fake_acompletion(**kwargs):
                    calls.append(kwargs)
                    return FakeCompletion({
                        "model": "fixture-deepseek-served",
                        "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                        "_hidden_params": {"additional_headers": {
                            "llm_provider-x-litellm-response-cost": estimate,
                        }},
                    })

                result, _upstream, ledger = self.run_with_fake(fake_acompletion)
                self.assertEqual(result["status"], "reviewed")
                self.assertEqual(len(calls), 1)
                records = [json.loads(line) for line in ledger.read_text().splitlines()]
                self.assertEqual([record["status"] for record in records], ["reserved", "reconciled"])
                self.assertEqual(records[-1]["actual_amount_usd"], 0.000015)
                self.assertFalse(records[-1]["envelope_breach"])
                shutil.rmtree(self.root / "engine")
                ledger.unlink()

    def test_response_model_alias_mismatch_is_retained_and_fails_closed(self):
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "unexpected-served-model", "model_version": "provider-v9",
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "unsupported_model")
        self.assertEqual(result["attempts"][0]["model"], model_identity("unexpected-served-model", "provider-v9"))
        self.assertEqual(result["attempts"][0]["usage"]["prompt_tokens"], 10)
        self.assertEqual(result["attempts"][0]["usage"]["completion_tokens"], 5)
        self.assertEqual(len(calls), 1)
        records = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual({record["status"] for record in records}, {"reserved", "uncertain"})
        final = next(record for record in records if record["status"] == "uncertain")
        self.assertIsNone(final["actual_amount_usd"])
        self.assertIsNone(final["usage"])

    def test_missing_response_model_identity_fails_closed_without_retry(self):
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "unsupported_model")
        self.assertIsNone(result["attempts"][0]["model"]["actual"])
        self.assertEqual(result["attempts"][0]["usage"]["prompt_tokens"], 10)
        self.assertEqual(result["attempts"][0]["usage"]["completion_tokens"], 5)
        self.assertEqual(len(calls), 1)
        records = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual({record["status"] for record in records}, {"reserved", "uncertain"})
        final = next(record for record in records if record["status"] == "uncertain")
        self.assertIsNone(final["actual_amount_usd"])
        self.assertIsNone(final["usage"])

    def test_malformed_model_and_version_finalize_one_uncertain_ledger_record(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        malformed = (7, "", "x" * 201)
        for field in ("model", "model_version"):
            for value in malformed:
                with self.subTest(field=field, value_type=type(value).__name__, value_length=len(value) if isinstance(value, str) else None):
                    calls = []

                    async def fake_acompletion(**kwargs):
                        calls.append(kwargs)
                        response = {
                            "model": "fixture-deepseek-served", "model_version": "fixture-version-1",
                            "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                        }
                        response[field] = value
                        return FakeCompletion(response)

                    result, _upstream, ledger = self.run_with_fake(fake_acompletion)
                    attempt = result["attempts"][0]
                    self.assertEqual(result["status"], "not-reviewed")
                    self.assertEqual(attempt["error_class"], "unsupported_model")
                    self.assertEqual(attempt["usage"]["prompt_tokens"], 10)
                    self.assertEqual(attempt["usage"]["completion_tokens"], 5)
                    self.assertEqual(len(calls), 1)
                    if field == "model":
                        self.assertIsNone(attempt["model"]["actual"])
                        self.assertEqual(attempt["model"]["response_version"], "fixture-version-1")
                    else:
                        self.assertEqual(attempt["model"]["actual"], "fixture-deepseek-served")
                        self.assertIsNone(attempt["model"]["response_version"])
                    records = [json.loads(line) for line in ledger.read_text().splitlines()]
                    self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
                    self.assertEqual(records[-1]["reserved_amount_usd"], 0.016434)
                    self.assertIsNone(records[-1]["actual_amount_usd"])
                    self.assertIsNone(records[-1]["usage"])
                    shutil.rmtree(self.root / "engine")
                    ledger.unlink()

    def test_affordable_context_above_100000_admits_without_supplier_counting(self):
        self.config_path.write_text(self.config_path.read_text().replace("context_token_limit = 16384", "context_token_limit = 200000"))
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(len(calls), 1)
        records = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(records[0]["reserved_amount_usd"], 0.20005)
        self.assertNotIn("input_token_cap", records[0]["reservation_basis"])

    def test_unaffordable_full_context_reservation_rejects_before_dispatch(self):
        self.config_path.write_text(self.config_path.read_text().replace("context_token_limit = 16384", "context_token_limit = 2000000"))
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            raise AssertionError("unaffordable request reached LiteLLM")

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "budget_exhausted")
        self.assertEqual(calls, [])
        self.assertFalse(ledger.exists())
        shutil.rmtree(self.root / "engine")

        self.config_path.write_text(self.config_path.read_text().replace("context_token_limit = 2000000", "context_token_limit = 200000"))

        async def context_rejection(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("400 context length exceeded fixture")

        result, _upstream, ledger = self.run_with_fake(context_rejection)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "invalid_parameter")
        self.assertEqual(len(calls), 1)
        records = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])

    def test_overall_deadline_bounds_the_actual_request_timeout(self):
        self.config_path.write_text(self.config_path.read_text().replace("engine_deadline_seconds = 600", "engine_deadline_seconds = 1"))
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, _ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertGreater(calls[0]["timeout"], 0)
        self.assertLessEqual(calls[0]["timeout"], 1)

    def test_total_deadline_rejects_success_after_synchronous_parse_or_cleanup(self):
        self.config_path.write_text(
            self.config_path.read_text().replace("engine_deadline_seconds = 600", "engine_deadline_seconds = 1")
        )
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**_kwargs):
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        for phase in ("parse", "cleanup"):
            with self.subTest(phase=phase):
                completed = []
                if phase == "parse":
                    original = adapter._strict_native_yaml

                    def delayed(*args, **kwargs):
                        time.sleep(1.2)
                        value = original(*args, **kwargs)
                        completed.append("parse")
                        return value

                    delay_patch = mock.patch.object(adapter, "_strict_native_yaml", side_effect=delayed)
                else:
                    original = adapter._restore_admission

                    def delayed(*args, **kwargs):
                        original(*args, **kwargs)
                        time.sleep(1.2)
                        completed.append("cleanup")

                    delay_patch = mock.patch.object(adapter, "_restore_admission", side_effect=delayed)

                started = time.monotonic()
                with delay_patch:
                    result, _upstream, ledger = self.run_with_fake(fake_acompletion)
                elapsed = time.monotonic() - started
                completed_at_return = list(completed)
                time.sleep(0.2)
                self.assertLess(elapsed, 3.5)
                self.assertGreaterEqual(result["elapsed_ms"], 1000)
                self.assertEqual(result["status"], "not-reviewed")
                self.assertEqual(result["error_class"], "deadline_exceeded")
                self.assertEqual(result["attempts"][0]["error_class"], "deadline_exceeded")
                self.assertEqual(result["attempts"][0]["usage"]["num_ai_calls"], 1)
                self.assertEqual(result["attempts"][0]["usage"]["prompt_tokens"], 10)
                self.assertEqual(result["attempts"][0]["coverage"]["usage"], result["attempts"][0]["usage"])
                self.assertEqual(completed, [phase])
                self.assertEqual(completed, completed_at_return, "deadline work continued after return")
                self.assertEqual(
                    [json.loads(line)["status"] for line in ledger.read_text().splitlines()],
                    ["reserved", "reconciled"],
                )
                shutil.rmtree(self.root / "engine")
                ledger.unlink()

    def test_semantically_empty_and_unknown_native_actual_outputs_fail(self):
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": "review:\n  key_issues_to_review: []\n"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, _ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "invalid_output")
        self.assertEqual(len(calls), 1)

    def test_unknown_native_field_actual_output_fails_closed(self):
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": (
                    "review:\n  general_comments: clean\n  key_issues_to_review: []\n"
                    "  ignored_payload: not-supported\n"
                )}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, _ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "invalid_output")
        self.assertEqual(len(calls), 1)

    def test_actual_yaml_boundary_rejects_missing_findings_and_oversized_raw_output(self):
        hostile = self.root / "engine"
        hostile.mkdir()
        with adapter._isolated_environment(hostile, "__never_read__", "__never_read__"):
            upstream = adapter._import_upstream(self.source_root)
        with self.assertRaisesRegex(adapter.EngineError, "missing its findings list"):
            adapter._strict_native_yaml(upstream, "review:\n  general_comments: clean\n")
        with self.assertRaisesRegex(adapter.EngineError, "empty or oversized"):
            adapter._strict_native_yaml(upstream, "x" * (adapter.MAX_NATIVE_OUTPUT_BYTES + 1))

    def test_single_fenced_yaml_reaches_actual_handler_review(self):
        async def fake_acompletion(**kwargs):
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": (
                    "```yaml\nreview:\n  general_comments: |-\n"
                    "    Checked error handling: caller state is preserved.\n"
                    "  key_issues_to_review: []\n```\n"
                )}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed", result["attempts"][0]["error"])
        attempt = result["attempts"][0]
        self.assertEqual(attempt["review"], {
            "summary": "Checked error handling: caller state is preserved.", "findings": [],
        })
        self.assertTrue(attempt["coverage"]["complete"])
        self.assertEqual(attempt["usage"]["num_ai_calls"], 1)
        self.assertEqual([json.loads(line)["status"] for line in ledger.read_text().splitlines()],
                         ["reserved", "reconciled"])

    def test_yaml_envelope_does_not_hide_invalid_documents(self):
        hostile = self.root / "engine"
        hostile.mkdir()
        with adapter._isolated_environment(hostile, "__never_read__", "__never_read__"):
            upstream = adapter._import_upstream(self.source_root)
        valid = "review:\n  general_comments: clean\n  key_issues_to_review: []\n"
        cases = [
            "prose\n```yaml\n" + valid + "```",
            "```yaml\n" + valid + "```\nprose",
            "```yaml\n" + valid + "```\n```yaml\n" + valid + "```",
            "```yaml\n" + valid,
            "```yaml\nreview:\n  general_comments: one\n  general_comments: two\n  key_issues_to_review: []\n```",
            "```yaml\nreview: &r\n  general_comments: clean\n  key_issues_to_review: []\n```",
            "```yaml\n" + valid + "  extra_field: forbidden\n```",
        ]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(adapter.EngineError):
                adapter._strict_native_yaml(upstream, text)

    def test_yaml_syntax_diagnostic_has_location_and_no_model_text(self):
        text = "review:\n  general_comments: secret-marker: invalid\n  key_issues_to_review: []\n"
        with self.assertRaises(adapter.EngineError) as raised:
            adapter._strict_native_yaml({}, text)
        self.assertIn("line=2", raised.exception.safe_message)
        self.assertIn("sha256=" + hashlib.sha256(text.encode()).hexdigest(), raised.exception.safe_message)
        self.assertNotIn("secret-marker", raised.exception.safe_message)

    def test_oversized_raw_prediction_fails_at_the_actual_handler_boundary(self):
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": "x" * (adapter.MAX_NATIVE_OUTPUT_BYTES + 1)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        result, _upstream, _ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "invalid_output")
        self.assertEqual(len(calls), 1)

    def test_provider_envelope_breaches_preserve_liability_stop_fallback_and_hold_future_admission(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        base_config = self.config_path.read_text()
        cases = {
            "output": ({"prompt_tokens": 10, "completion_tokens": 51, "total_tokens": 61}, 0.000061),
            "context": ({"prompt_tokens": 16_384, "completion_tokens": 1, "total_tokens": 16_385}, 0.016385),
        }
        for kind, (usage, expected_actual) in cases.items():
            with self.subTest(kind=kind):
                calls = []
                self.config_path.write_text(self.with_glm_fallback(base_config))

                async def fake_acompletion(**kwargs):
                    calls.append(kwargs)
                    response = FakeCompletion({
                        "model": "fixture-deepseek-served",
                        "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                        "usage": usage,
                    })
                    return response

                result, _upstream, ledger_path = self.run_with_fake(fake_acompletion)
                self.assertEqual(result["status"], "not-reviewed")
                self.assertEqual(result["attempts"][0]["error_class"], "invalid_parameter")
                self.assertEqual(len(result["attempts"]), 1, "an envelope breach must suppress provider fallback")
                self.assertEqual(len(calls), 1)
                records = [json.loads(line) for line in ledger_path.read_text().splitlines()]
                self.assertEqual([record["status"] for record in records], ["reserved", "reconciled"])
                self.assertTrue(records[-1]["envelope_breach"])
                self.assertEqual(records[-1]["actual_amount_usd"], expected_actual)
                self.assert_envelope_held(ledger_path, records, kind)
                shutil.rmtree(self.root / "engine")
                ledger_path.unlink()

    def test_over_cap_usage_with_wrong_model_retains_observation_and_durable_hold(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        self.config_path.write_text(self.with_glm_fallback(self.config_path.read_text()))
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "wrong-served-model",
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 51, "total_tokens": 61},
            })

        result, _upstream, ledger_path = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "unsupported_model")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["attempts"][0]["usage"]["completion_tokens"], 51)
        records = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
        final = records[-1]
        self.assertTrue(final["envelope_breach"])
        self.assertIsNone(final["actual_amount_usd"])
        self.assertIsNone(final["usage"])
        self.assert_envelope_held(ledger_path, records, "wrong-model")

    def test_arbitrarily_large_valid_usage_finalizes_uncertain_breach_without_fallback(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        self.config_path.write_text(self.with_glm_fallback(self.config_path.read_text()))
        calls = []
        huge = 10 ** 400

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            return FakeCompletion({
                "model": "fixture-deepseek-served",
                "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": huge, "completion_tokens": 1, "total_tokens": huge + 1},
            })

        result, _upstream, ledger_path = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "invalid_parameter")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["attempts"][0]["usage"]["prompt_tokens"], huge)
        records = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
        self.assertTrue(records[-1]["envelope_breach"])
        self.assertIsNone(records[-1]["actual_amount_usd"])
        self.assertIsNone(records[-1]["usage"])
        self.assert_envelope_held(ledger_path, records, "huge")

    def test_usage_breaches_precede_missing_or_malformed_model_identity(self):
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")
        self.config_path.write_text(self.with_glm_fallback(self.config_path.read_text()))
        cases = {
            "missing-context": (None, {"prompt_tokens": 16_384, "completion_tokens": 1, "total_tokens": 16_385}),
            "malformed-output": (7, {"prompt_tokens": 10, "completion_tokens": 51, "total_tokens": 61}),
        }
        for name, (response_model, usage) in cases.items():
            with self.subTest(name=name):
                calls = []

                async def fake_acompletion(**kwargs):
                    calls.append(kwargs)
                    response = {
                        "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                        "usage": usage,
                    }
                    if response_model is not None:
                        response["model"] = response_model
                    return FakeCompletion(response)

                result, _upstream, ledger_path = self.run_with_fake(fake_acompletion)
                self.assertEqual(result["status"], "not-reviewed")
                self.assertEqual(result["attempts"][0]["error_class"], "unsupported_model")
                self.assertEqual(len(result["attempts"]), 1)
                self.assertEqual(len(calls), 1)
                records = [json.loads(line) for line in ledger_path.read_text().splitlines()]
                self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])
                self.assertTrue(records[-1]["envelope_breach"])
                self.assertIsNone(records[-1]["actual_amount_usd"])
                self.assertIsNone(records[-1]["usage"])
                self.assert_envelope_held(ledger_path, records, name)
                shutil.rmtree(self.root / "engine")
                ledger_path.unlink()

    def test_price_revision_cannot_change_its_durable_reservation_basis(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", test_config()["budget"])
            common = dict(
                approval_id="fixture-approval", provider="deepseek", model="fixture-model",
                priced_response_model="fixture-served-model",
                input_price=0.000001, output_price=0.000001, output_token_cap=50,
                fixed_request_charge=0.0,
                billable_categories=list(adapter.BOUNDED_BILLABLE_CATEGORIES), max_requests=8,
                max_provider_requests=2, per_pr_usd=1.0, monthly_usd=20.0,
                pilot_usd=20.0, price_revision="fixture-price-v1",
            )
            ledger.admit(attempt_id="basis-a", request_id="basis-a:deepseek:1",
                         context_token_limit=100, **common)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "reservation basis"):
                ledger.admit(attempt_id="basis-b", request_id="basis-b:deepseek:1",
                             context_token_limit=101, **common)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "reservation basis"):
                ledger.admit(
                    attempt_id="basis-c", request_id="basis-c:deepseek:1", context_token_limit=100,
                    **{**common, "priced_response_model": "fixture-other-served-model"},
                )

    def test_configured_request_timeout_cancels_the_actual_seam_without_late_work(self):
        self.config_path.write_text(self.config_path.read_text().replace("request_timeout_seconds = 7", "request_timeout_seconds = 1"))
        calls = []
        cancelled = []

        async def fake_acompletion(**kwargs):
            calls.append({"called_at": time.monotonic(), "kwargs": kwargs})
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
            raise AssertionError("cancelled request resumed as late untracked work")

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        returned_at = time.monotonic()
        calls_at_return = list(calls)
        time.sleep(0.2)
        self.assertLess(returned_at - calls[0]["called_at"], 3)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "timeout")
        self.assertEqual(len(calls), 1)
        self.assertEqual(cancelled, [True])
        self.assertEqual(calls, calls_at_return, "cancelled request continued work after the engine returned")
        self.assertEqual({json.loads(line)["status"] for line in ledger.read_text().splitlines()}, {"reserved", "uncertain"})

    def test_authentication_failure_is_not_retried_by_the_stock_decorator(self):
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("401 unauthorized fixture")

        result, _upstream, _ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "authentication_error")
        self.assertEqual(len(calls), 1, "why: authentication errors cannot improve on replay; remedy: advance or stop")

    def test_transient_failure_uses_one_stock_retry_and_two_ledger_admissions(self):
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("503 temporary network fixture")
            return FakeCompletion({"model": "fixture-deepseek-served",
                                   "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["attempts"][0]["usage"]["num_ai_calls"], 2)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 4)
        self.assertEqual({record["request_id"] for record in records},
                         {"t2-fixture-run:1:deepseek:1", "t2-fixture-run:1:deepseek:2"})
        reservations = [record for record in records if record["status"] == "reserved"]
        self.assertEqual([record["reserved_amount_usd"] for record in reservations], [0.016434, 0.016434])
        self.assertEqual([record["status"] for record in records],
                         ["reserved", "uncertain", "reserved", "reconciled"])

    def test_total_deadline_cancels_stock_backoff_without_late_second_dispatch(self):
        self.config_path.write_text(
            self.config_path.read_text()
            .replace("backoff_seconds = 0", "backoff_seconds = 5")
            .replace("engine_deadline_seconds = 600", "engine_deadline_seconds = 1")
        )
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append({"called_at": time.monotonic(), "timeout": kwargs["timeout"]})
            raise RuntimeError("503 temporary network fixture")

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        returned_at = time.monotonic()
        calls_at_return = list(calls)
        time.sleep(0.2)
        self.assertLess(
            returned_at - calls[0]["called_at"], 3,
            "why: stock retry backoff escaped the one-second engine deadline; "
            "remedy: keep the complete provider attempt in the total cancellation scope",
        )
        self.assertLess(result["elapsed_ms"], 2000)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["error_class"], "deadline_exceeded")
        self.assertEqual(result["attempts"][0]["error_class"], "deadline_exceeded")
        self.assertEqual(result["attempts"][0]["usage"]["num_ai_calls"], 1)
        self.assertIsNone(result["attempts"][0]["usage"]["prompt_tokens"])
        self.assertEqual(result["attempts"][0]["coverage"]["usage"], result["attempts"][0]["usage"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls, calls_at_return, "cancelled backoff continued work after the engine returned")
        records = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "uncertain"])

    def test_rate_limit_failure_uses_one_bounded_retry(self):
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("429 rate limit fixture")
            return FakeCompletion({"model": "fixture-deepseek-served",
                                   "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        result, _upstream, _ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(len(calls), 2)

    def test_timeout_failure_has_one_actual_seam_call_and_retains_uncertain_reservation(self):
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise TimeoutError("timed out fixture")
            return FakeCompletion({"model": "fixture-deepseek-served",
                                   "choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "timeout")
        self.assertEqual(len(calls), 1, "why: timeout is not retryable by the approved design; remedy: retain the uncertain reservation and advance or stop")
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({record["status"] for record in records}, {"reserved", "uncertain"})


CHILD_PROGRESS_TIMEOUT_SECONDS = 120
CHILD_TOTAL_CEILING_SECONDS = 1200


def run_child_with_watchdog(command, *, cwd, env):
    """Run the integration child, killing it on no test progress, not on slowness.

    The child's unittest transcript is streamed line by line (-u keeps the
    pipe flushed); every received line is test activity and resets the
    progress timer.  Returns (completed_process, stalled, hit_ceiling).
    """
    import threading

    process = subprocess.Popen(
        command, cwd=cwd, env=env, text=True, bufsize=1,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    activity = threading.Event()

    def drain(stream, sink):
        for line in stream:
            sink.append(line)
            activity.set()

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    readers = [
        threading.Thread(target=drain, args=(process.stdout, stdout_lines), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, stderr_lines), daemon=True),
    ]
    for reader in readers:
        reader.start()
    stalled = False
    hit_ceiling = False
    deadline = time.monotonic() + CHILD_PROGRESS_TIMEOUT_SECONDS
    ceiling = time.monotonic() + CHILD_TOTAL_CEILING_SECONDS
    while process.poll() is None:
        now = time.monotonic()
        if now >= ceiling:
            hit_ceiling = True
            break
        if now >= deadline:
            stalled = True
            break
        # One-second quantum so a silently finished child is reaped promptly;
        # any transcript line re-arms the progress timer.
        activity.wait(timeout=1.0)
        if activity.is_set():
            activity.clear()
            deadline = time.monotonic() + CHILD_PROGRESS_TIMEOUT_SECONDS
    if stalled or hit_ceiling:
        process.kill()
    process.wait()
    for reader in readers:
        reader.join(timeout=5)
    completed = subprocess.CompletedProcess(
        command, process.returncode, "".join(stdout_lines), "".join(stderr_lines),
    )
    return completed, stalled, hit_ceiling


class IntegrationProxyTests(unittest.TestCase):
    def test_litellm_import_uses_bundled_cost_map_without_metadata_http(self):
        """The pinned engine import must not fetch mutable LiteLLM metadata."""
        if os.environ.get("PR_AGENT_RUN_INTEGRATION") != "1":
            self.skipTest(
                "bundled LiteLLM map proof is an explicit pinned-runtime lane; set "
                "PR_AGENT_RUN_INTEGRATION=1 with PR_AGENT_TEST_PYTHON and "
                "PR_AGENT_TEST_SOURCE_ROOT to run it"
            )
        runtime_value = os.environ.get("PR_AGENT_TEST_PYTHON")
        source_value = os.environ.get("PR_AGENT_TEST_SOURCE_ROOT")
        if not runtime_value or not source_value:
            self.fail(
                "why: bundled LiteLLM map proof lacks its pinned runtime/source; "
                "remedy: provide PR_AGENT_TEST_PYTHON and PR_AGENT_TEST_SOURCE_ROOT"
            )
        runtime = Path(runtime_value)
        source_root = Path(source_value)
        if not runtime.is_file() or not (source_root / "IDENTITY").is_file():
            self.fail(
                "why: bundled LiteLLM map proof inputs are unavailable; "
                "remedy: run the pinned integration preparation first"
            )
        probe = r'''
import importlib.metadata
import json
import os
import sys
from pathlib import Path

import httpx

calls = []
def forbidden_get(url, *args, **kwargs):
    calls.append({"url": url, "timeout": kwargs.get("timeout")})
    raise AssertionError("LiteLLM attempted mutable model metadata HTTP")

httpx.get = forbidden_get
os.environ.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)
sys.path.insert(0, sys.argv[1])
import pr_agent_review as adapter

source_root = Path(sys.argv[2])
adapter.TRUSTED_ENGINE_ROOT = source_root
upstream = adapter._import_upstream(source_root)
litellm = upstream["litellm_ai_handler"].litellm
from litellm.litellm_core_utils.get_model_cost_map import get_model_cost_map_source_info

info = get_model_cost_map_source_info()
assert importlib.metadata.version("litellm") == "1.100.0"
assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "true"
assert calls == [], calls
assert info["source"] == "local", info
assert info["is_env_forced"] is True, info
assert info["url"] is None, info
assert len(litellm.model_cost) > 0
print(json.dumps({"calls": calls, "source": info, "model_cost_entries": len(litellm.model_cost)}))
'''
        environment = dict(os.environ)
        environment.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)
        completed = subprocess.run(
            [str(runtime), "-c", probe, str(ROOT / "scripts/ci"), str(source_root)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(
            completed.returncode,
            0,
            "why: the trusted engine import must select its bundled LiteLLM map "
            "without metadata HTTP; remedy: force the local-map boundary before "
            f"the first LiteLLM import\nstdout={completed.stdout}\nstderr={completed.stderr}",
        )

    def test_watchdog_allows_a_slow_but_progressing_child(self):
        child = (
            "import sys, time\n"
            "for tick in range(10):\n"
            "    print(f'test_tick_{tick} ... ok', file=sys.stderr, flush=True)\n"
            "    time.sleep(0.2)\n"
        )
        with mock.patch.multiple(
            __name__, CHILD_PROGRESS_TIMEOUT_SECONDS=1.0, CHILD_TOTAL_CEILING_SECONDS=30.0,
        ):
            completed, stalled, hit_ceiling = run_child_with_watchdog(
                [sys.executable, "-u", "-c", child], cwd=ROOT, env=dict(os.environ),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(stalled, "a progressing child must never be stalled")
        self.assertFalse(hit_ceiling)
        self.assertIn("test_tick_9 ... ok", completed.stderr)

    def test_watchdog_kills_a_hung_child_and_names_the_test_in_flight(self):
        child = (
            "import sys, time\n"
            "print('test_started ... ', file=sys.stderr, flush=True)\n"
            "time.sleep(30)\n"
        )
        with mock.patch.multiple(
            __name__, CHILD_PROGRESS_TIMEOUT_SECONDS=0.5, CHILD_TOTAL_CEILING_SECONDS=30.0,
        ):
            started = time.monotonic()
            completed, stalled, hit_ceiling = run_child_with_watchdog(
                [sys.executable, "-u", "-c", child], cwd=ROOT, env=dict(os.environ),
            )
            elapsed = time.monotonic() - started
        self.assertTrue(stalled)
        self.assertFalse(hit_ceiling)
        self.assertLess(elapsed, 10, "the hung child must be killed near the progress timeout")
        self.assertIn("test_started", completed.stderr)
        self.assertNotEqual(completed.returncode, 0)

    def test_watchdog_total_ceiling_stops_a_forever_progressing_child(self):
        child = (
            "import sys, time\n"
            "while True:\n"
            "    print('progress', file=sys.stderr, flush=True)\n"
            "    time.sleep(0.1)\n"
        )
        with mock.patch.multiple(
            __name__, CHILD_PROGRESS_TIMEOUT_SECONDS=30.0, CHILD_TOTAL_CEILING_SECONDS=1.0,
        ):
            started = time.monotonic()
            completed, stalled, hit_ceiling = run_child_with_watchdog(
                [sys.executable, "-u", "-c", child], cwd=ROOT, env=dict(os.environ),
            )
            elapsed = time.monotonic() - started
        self.assertFalse(stalled, "progress means never stalled")
        self.assertTrue(hit_ceiling)
        self.assertLess(elapsed, 10, "the ceiling kill must land near the ceiling")

    def test_real_handler_suite_runs_in_pinned_python_environment(self):
        if os.environ.get("PR_AGENT_RUN_INTEGRATION") != "1":
            self.skipTest(
                "actual PR-Agent seam is an explicit bundle-lane proof; set "
                "PR_AGENT_RUN_INTEGRATION=1 with PR_AGENT_TEST_PYTHON and "
                "PR_AGENT_TEST_SOURCE_ROOT to run it"
            )
        runtime_value = os.environ.get("PR_AGENT_TEST_PYTHON")
        source_value = os.environ.get("PR_AGENT_TEST_SOURCE_ROOT")
        if not runtime_value or not source_value:
            self.fail(
                "why: integration proof was explicitly enabled without its pinned runtime and source; "
                "remedy: provide PR_AGENT_TEST_PYTHON and an identity-bound PR_AGENT_TEST_SOURCE_ROOT"
            )
        runtime = Path(runtime_value)
        source_root = Path(source_value)
        if not runtime.is_file() or not source_root.is_dir():
            self.fail(
                "why: the explicitly selected pinned integration inputs are unavailable; "
                "remedy: prepare the locked Python runtime and identity-bound bundle source before this lane"
            )
        if not (source_root / "IDENTITY").is_file():
            self.fail(
                "why: the explicitly selected integration source has no bundle identity; "
                "remedy: use the preparation command to create the pinned source manifest"
            )
        environment = dict(os.environ)
        environment["PR_AGENT_RUN_INTEGRATION"] = "1"
        environment["PR_AGENT_TEST_SOURCE_ROOT"] = str(source_root)
        # The defect this run guards is a HUNG child (e.g. a network-guard
        # violation looping), not a slow one: the suite's work is legitimate
        # and host contention scales it (measured 38.5s idle on an M-series
        # Mac, >120s on a contended shared runner, #1389).  A total wall cap
        # cannot tell the two apart, so the instrument is a no-progress
        # watchdog on the child's streamed test transcript (-u keeps the pipe
        # line-flushed): 120s without any test activity kills the child and
        # the transcript names the test in flight.  A generous total ceiling
        # stays as the guard against a child that emits progress forever.
        command = [str(runtime), "-u", str(Path(__file__)), "--integration-child"]
        completed, stalled, ceiling = run_child_with_watchdog(command, cwd=ROOT, env=environment)
        if stalled:
            self.fail(
                "why: the integration child made no test progress for "
                f"{CHILD_PROGRESS_TIMEOUT_SECONDS} seconds and was killed as hung; the partial "
                "transcript below names the test in flight when the watchdog fired, and the "
                "child's timing trace attributes import versus suite time; remedy: "
                "investigate the named test for a hang — a slow but progressing "
                "run is not a failure and must not change this watchdog\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
        if ceiling:
            self.fail(
                "why: the integration child emitted progress past the "
                f"{CHILD_TOTAL_CEILING_SECONDS}-second total ceiling and was killed; the partial "
                "transcript below shows the unbounded phase; remedy: attribute the "
                "overrun to a phase before changing the ceiling, the work, or the host\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


def run_suite(integration_child=False):
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(RealHandlerIntegrationTests if integration_child else InputAndPolicyTests))
    if not integration_child:
        suite.addTests(loader.loadTestsFromTestCase(IntegrationProxyTests))
    return unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    integration_child = "--integration-child" in sys.argv
    suite_t0 = time.monotonic()
    failed = not run_suite(integration_child).wasSuccessful()
    print(
        f"timing schema=lmdj.ci-pr-agent-phase-timing.v1 "
        f"role={'integration-child' if integration_child else 'parent'} "
        f"module_import_seconds={_MODULE_IMPORT_SECONDS:.3f} "
        f"suite_seconds={time.monotonic() - suite_t0:.3f}",
        file=sys.stderr,
    )
    raise SystemExit(1 if failed else 0)
