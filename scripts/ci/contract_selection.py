#!/usr/bin/env python3
"""Conservative CI-contract selection shared by PR and local quick runs."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

import change_scope

ROOT = Path(__file__).resolve().parents[2]
OWN_TEST = "tests/build/ci_contract_selection_test.py"
OWN_SOURCE = "scripts/ci/contract_selection.py"
# Audited readers of the preflight module, command table and public shell entry.
# This is intentionally small. Unmapped control changes still run everything.
PREFLIGHT_SOURCES = {
    "scripts/ci/local_preflight.py", "scripts/ci/local_lanes.json", "scripts/local-ci.sh",
}
PREFLIGHT_TESTS = {
    "tests/build/ci_local_preflight_test.py",
    "tests/build/ci_change_scope_test.py",
    "tests/build/ci_workflow_topology_test.py",
    "tests/build/ci_build_acceleration_test.py",
    "tests/build/ci_issue_done_skill_test.py",
    "tests/build/ci_scope_policy_consumer_parity_test.py",
    "tests/build/ci_scope_policy_differential_test.py",
    "tests/build/ci_toolchain_pin_test.py",
    "tests/build/ci_classification_inputs_test.py",
}


def references(path):
    """Literal Python reads/imports, excluding comments and docstrings.

    This detects drift in the audited group; it is not general dependency
    inference. Unknown changed modules never earn a focused plan from this scan.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr)
                  and isinstance(node.body[0].value, ast.Constant)
                  and isinstance(node.body[0].value.value, str)}
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            values.append(node.value)
        elif isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.append(node.module)
    return "\n".join(values)


def new_consumers(root):
    known = PREFLIGHT_SOURCES | PREFLIGHT_TESTS | {OWN_SOURCE, OWN_TEST}
    needles = {Path(path).stem if path.endswith(".py") else Path(path).name
               for path in PREFLIGHT_SOURCES | PREFLIGHT_TESTS}
    pattern = re.compile(r"(?<![\w])(?:" + "|".join(map(re.escape, sorted(needles))) + r")(?![\w])")
    paths = [*root.joinpath("scripts/ci").rglob("*.py"),
             *root.joinpath("tests/build").glob("ci_*_test.py")]
    return sorted(str(path.relative_to(root)) for path in paths
                  if str(path.relative_to(root)) not in known and pattern.search(references(path)))


def select(root, paths, *, profile="quick"):
    root = Path(root)
    if profile not in {"quick", "full"}:
        raise ValueError("why: unknown contract profile; remedy: choose quick or full")
    inventory = sorted(str(path.relative_to(root)) for path in root.joinpath("tests/build").glob("ci_*_test.py"))
    if not inventory or OWN_TEST not in inventory:
        raise ValueError("why: CI test inventory is incomplete; remedy: restore the complete source checkout")

    def full(reason):
        return {"profile": profile, "mode": "full", "tests": inventory, "seam": True, "reason": reason}

    if profile == "full":
        return full("explicit full request")
    policy = change_scope.load_policy(root / "scripts/ci/scope_policy.json")
    selected = {OWN_TEST}
    for path in paths:
        change_scope._validate_path(path)
        if path in PREFLIGHT_SOURCES | PREFLIGHT_TESTS:
            selected.update(PREFLIGHT_TESTS)
            continue
        lanes, full_reasons = change_scope.path_classification(policy, path)
        if lanes and not full_reasons and "ci_contract" not in lanes:
            continue
        return full(f"unmapped CI dependency: {path}")
    try:
        consumers = new_consumers(root)
    except (OSError, SyntaxError, UnicodeError):
        return full("consumer inventory could not be inspected")
    if consumers:
        return full("unmapped preflight consumers: " + ", ".join(consumers))
    if not selected <= set(inventory):
        return full("audited contract inventory changed")
    return {"profile": profile, "mode": "focused", "tests": sorted(selected), "seam": False,
            "reason": "audited preflight module and its consumers; other paths belong to other lanes"}


def changed_paths(root, base, head=None):
    def git(*args):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
        if result.returncode:
            raise ValueError("why: changed Git inputs are unavailable; remedy: fetch the complete base and head")
        return result.stdout
    if head is not None:
        base = git("merge-base", base, head).decode().strip()
    data = git("diff", "--name-only", "--no-renames", "-z", base, *([head] if head else []))
    if head is None:
        data += git("ls-files", "--others", "--exclude-standard", "-z")
    return sorted(set(value.decode("utf-8") for value in data.split(b"\0") if value))


def run_tests(root, paths):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.discover(str(root / "tests/build"), pattern=Path(path).name)
                               for path in paths)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head")
    parser.add_argument("--profile", choices=("quick", "full"), default="quick")
    parser.add_argument("--execute", choices=("none", "tests", "all"), default="none")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        plan = select(ROOT, changed_paths(ROOT, args.base, args.head), profile=args.profile)
        print(json.dumps(plan, indent=2), flush=True)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as output:
                output.write("seam=" + str(plan["seam"]).lower() + "\n")
        if args.execute != "none":
            os.chdir(ROOT)
            if run_tests(ROOT, plan["tests"]):
                return 1
        if args.execute == "all" and plan["seam"]:
            return subprocess.run(["bash", "scripts/ci/pr-agent/integration-test.sh"], check=False).returncode
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f"CI contract selection failed closed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
