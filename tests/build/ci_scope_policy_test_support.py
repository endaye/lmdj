"""Git-backed scope-policy transition fixtures shared by CI contract tests."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import copy
import json
from pathlib import Path
import subprocess
import tempfile


PRESERVING_TARGET = (
    "packages/web-runtime-platform/test/performance_master_capture.test.mjs"
)


@dataclass(frozen=True)
class PolicyTransition:
    root: Path
    base_sha: str
    head_sha: str
    base_policy: dict[str, object]
    head_policy: dict[str, object]


def _run(root: Path, *args: str) -> str:
    return subprocess.run(
        args, cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@contextmanager
def policy_transition(policy: dict[str, object], *, preserving: bool):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _run(root, "git", "init", "--quiet")
        _run(root, "git", "config", "user.email", "ci@example.invalid")
        _run(root, "git", "config", "user.name", "CI Test")

        base_policy = copy.deepcopy(policy)
        head_policy = copy.deepcopy(policy)
        existing = root / "docs/existing.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("existing\n", encoding="utf-8")
        if preserving:
            base_policy["rules"] = [
                rule for rule in base_policy["rules"]
                if rule["match"] != {
                    "kind": "exact", "value": PRESERVING_TARGET
                }
            ]
        else:
            head_policy["rules"].append({
                "match": {"kind": "exact", "value": "docs/existing.md"},
                "lanes": ["portal"],
            })

        policy_path = root / "scripts/ci/scope_policy.json"
        policy_path.parent.mkdir(parents=True)
        policy_path.write_text(
            json.dumps(base_policy, indent=2) + "\n", encoding="utf-8"
        )
        _run(root, "git", "add", "--", "docs/existing.md", str(policy_path.relative_to(root)))
        _run(root, "git", "commit", "--quiet", "-m", "base policy")
        base_sha = _run(root, "git", "rev-parse", "HEAD")

        policy_path.write_text(
            json.dumps(head_policy, indent=2) + "\n", encoding="utf-8"
        )
        paths = ["scripts/ci/scope_policy.json"]
        if preserving:
            target = root / PRESERVING_TARGET
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("// newly routed\n", encoding="utf-8")
            paths.append(PRESERVING_TARGET)
        _run(root, "git", "add", "--", *paths)
        _run(root, "git", "commit", "--quiet", "-m", "policy transition")
        head_sha = _run(root, "git", "rev-parse", "HEAD")
        yield PolicyTransition(
            root, base_sha, head_sha, base_policy, head_policy
        )
