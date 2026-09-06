#!/usr/bin/env python3
"""The manifest asset-role vocabulary is one set, spelled in three places.

`.agents/pitfalls/manifest-role-validator-sync.md` records the failure twice
(#354, then #711): a packager learns a new asset role, the deployment
validator does not, and every suite passes -- the mismatch surfaces only when
the staged Draft fails the deployment smoke. The three copies are

* the Runtime packager, `apps/web-runtime-host/tools/package.py`;
* the Creator packager, `apps/creator-web/tools/package.py`;
* the validator, `apps/web-runtime-host/tools/deployment_smoke.py`
  (`ALLOWED_ASSET_ROLES`, `SINGLETON_ASSET_ROLES`), plus the smoke test's
  fixture layout, which is a fourth copy in all but name.

This gate compares them without the shared-constant refactor the entry once
thought was a prerequisite. Both packagers hand every role to
`write_hashed_asset(...)` as a string literal, so the set a packager can emit
is decidable from the source text alone: collect those literals, and the
comparison is a set difference. The gate reads repository text only and
depends on no build output.

Why the comparison runs in both directions: a role the packagers emit and the
validator lacks is the outage this exists to prevent; a role the validator
allows and nobody emits is a rename or a typo waiting to become the same
outage from the other side.
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PACKAGER = REPO_ROOT / "apps/web-runtime-host/tools/package.py"
CREATOR_PACKAGER = REPO_ROOT / "apps/creator-web/tools/package.py"
VALIDATOR = REPO_ROOT / "apps/web-runtime-host/tools/deployment_smoke.py"
# Both smoke tests lay out their own manifest, each a further copy of the
# vocabulary: the Runtime's under `ASSET_LAYOUT`, the Creator's under `ASSETS`.
SMOKE_FIXTURES = (
    (REPO_ROOT / "apps/web-runtime-host/test/deployment_smoke_test.py", "ASSET_LAYOUT"),
    (REPO_ROOT / "apps/creator-web/test/deployment_smoke_test.py", "ASSETS"),
)

# The one function every manifest asset entry passes through, in both
# packagers. Its fifth positional (or keyword) argument is the role.
EMITTER = "write_hashed_asset"
ROLE_POSITION = 4


class Undecidable(AssertionError):
    """A role reached the emitter as something other than a string literal."""


def _callee_name(call: ast.Call) -> str | None:
    callee = call.func
    return callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)


def _role_argument(call: ast.Call, position: int) -> ast.expr | None:
    role_node: ast.expr | None = None
    if len(call.args) > position:
        role_node = call.args[position]
    for keyword in call.keywords:
        if keyword.arg == "role":
            role_node = keyword.value
    return role_node


def emitters(tree: ast.AST) -> dict[str, int]:
    """`{function name: role position}` for the emitter and every wrapper of it.

    The Runtime packager defines a nested `write_module(source, stem, role,
    ...)` that forwards its own `role` parameter to `write_hashed_asset`. A
    role literal at a `write_module` call site is as much a manifest role as
    one at the emitter itself, so the gate follows one level of forwarding:
    any function whose named parameter is what reaches the emitter's role
    slot is itself an emitter, at that parameter's position.
    """
    found = {EMITTER: ROLE_POSITION}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = [a.arg for a in node.args.args]
        for call in ast.walk(node):
            if not isinstance(call, ast.Call) or _callee_name(call) != EMITTER:
                continue
            role_node = _role_argument(call, ROLE_POSITION)
            if isinstance(role_node, ast.Name) and role_node.id in params:
                found[node.name] = params.index(role_node.id)
    return found


def emitted_roles(source: str, *, origin: str) -> set[str]:
    """Every role a packager can put in a manifest, read from its source.

    Raises `Undecidable` if any call hands an emitter a computed role: the
    gate cannot see through a variable, and a role it cannot see is a role it
    cannot compare, which is the blind spot the ledger entry describes. A
    wrapper forwarding its own parameter is not "computed" -- its call sites
    are read instead (see `emitters`).
    """
    tree = ast.parse(source, filename=origin)
    positions = emitters(tree)
    roles: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node)
        if name not in positions:
            continue
        role_node = _role_argument(node, positions[name])
        # Inside a wrapper, the emitter is handed the wrapper's own parameter;
        # that call is accounted for at the wrapper's call sites.
        if isinstance(role_node, ast.Name) and name == EMITTER and any(
            role_node.id in [a.arg for a in fn.args.args]
            for fn in ast.walk(tree)
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(c is node for c in ast.walk(fn))
        ):
            continue
        if role_node is None:
            raise Undecidable(
                f"why: {origin}:{node.lineno} calls {name} without a role the gate "
                f"can read; remedy: pass the role as a string literal"
            )
        if not (isinstance(role_node, ast.Constant) and isinstance(role_node.value, str)):
            raise Undecidable(
                f"why: {origin}:{node.lineno} passes {name} a computed role, which "
                f"this gate cannot compare against the validator; remedy: pass the role "
                f"as a string literal, or extend this gate to follow the value"
            )
        roles.add(role_node.value)
    if not roles:
        raise Undecidable(
            f"why: no {EMITTER} call with a literal role was found in {origin}, so the "
            f"packager's vocabulary could not be read; remedy: keep asset entries going "
            f"through {EMITTER}, or update EMITTER here if it was renamed"
        )
    return roles


def fixture_roles(source: str, variable: str, *, origin: str = "fixture") -> set[str]:
    """The roles a smoke test's asset-layout fixture lays out."""
    tree = ast.parse(source, filename=origin)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == variable for t in node.targets):
            continue
        roles = set()
        for element in getattr(node.value, "elts", []):
            elts = getattr(element, "elts", [])
            if len(elts) < 3 or not (
                isinstance(elts[2], ast.Constant) and isinstance(elts[2].value, str)
            ):
                raise Undecidable(
                    f"why: an entry of {variable} in {origin}:{getattr(element, 'lineno', '?')} "
                    f"has no literal role in its third position, so this gate cannot "
                    f"tell which roles the fixture lays out; remedy: keep the entries "
                    f"as (stem, suffix, role) with a literal role, or extend this gate"
                )
            roles.add(elts[2].value)
        if not roles:
            raise Undecidable(
                f"why: {variable} in {origin} is empty, and an empty set trivially "
                f"satisfies the comparison -- the gate would pass while reading "
                f"nothing; remedy: keep the fixture populated, or update "
                f"SMOKE_FIXTURES if the layout moved"
            )
        return roles
    raise AssertionError(
        f"why: {variable} was not found in {origin}, so that fixture's vocabulary "
        f"could not be compared and the gate would pass while looking at nothing; "
        f"remedy: keep the tuple-of-tuples fixture under that name, or update "
        f"SMOKE_FIXTURES here"
    )


def validator_sets() -> tuple[frozenset[str], frozenset[str]]:
    sys.path.insert(0, str(VALIDATOR.parent))
    try:
        import deployment_smoke  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    return deployment_smoke.ALLOWED_ASSET_ROLES, deployment_smoke.SINGLETON_ASSET_ROLES


class ManifestRoleParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = emitted_roles(RUNTIME_PACKAGER.read_text(encoding="utf-8"), origin="runtime packager")
        cls.creator = emitted_roles(CREATOR_PACKAGER.read_text(encoding="utf-8"), origin="creator packager")
        cls.allowed, cls.singleton = validator_sets()

    def test_no_packager_emits_a_role_the_validator_does_not_know(self) -> None:
        for name, roles in (("runtime", self.runtime), ("creator", self.creator)):
            with self.subTest(packager=name):
                unknown = sorted(roles - self.allowed)
                self.assertEqual(
                    unknown, [],
                    msg=(f"why: the {name} packager emits {unknown}, which "
                         f"deployment_smoke.ALLOWED_ASSET_ROLES does not contain, so every "
                         f"Build from that packager passes every suite and fails the "
                         f"deployment smoke on the staged Draft (#354, #711); remedy: add the "
                         f"role to ALLOWED_ASSET_ROLES (and SINGLETON_ASSET_ROLES if exactly "
                         f"one is required) in the same change"),
                )

    def test_the_validator_allows_no_role_that_nobody_emits(self) -> None:
        dead = sorted(self.allowed - (self.runtime | self.creator))
        self.assertEqual(
            dead, [],
            msg=(f"why: ALLOWED_ASSET_ROLES contains {dead}, which neither packager "
                 f"emits -- a rename or a typo on one side, and the next Build to use "
                 f"the other spelling fails the smoke; remedy: drop the role from the "
                 f"validator or emit it from a packager"),
        )

    def test_singletons_are_a_subset_of_the_allowed_roles(self) -> None:
        extra = sorted(self.singleton - self.allowed)
        self.assertEqual(
            extra, [],
            msg=(f"why: {extra} is required exactly once but is not an allowed "
                 f"role, so the validator demands a role it would also reject and "
                 f"no manifest can satisfy it; remedy: add it to "
                 f"ALLOWED_ASSET_ROLES or drop it from SINGLETON_ASSET_ROLES"),
        )

    def test_every_smoke_fixture_lays_out_only_known_roles(self) -> None:
        for path, variable in SMOKE_FIXTURES:
            with self.subTest(fixture=path.name, variable=variable):
                roles = fixture_roles(
                    path.read_text(encoding="utf-8"), variable, origin=str(path)
                )
                stray = sorted(roles - self.allowed)
                self.assertEqual(
                    stray, [],
                    msg=(f"why: {path.name}'s {variable} lays out {stray}, which the "
                         f"validator it exercises does not allow, so the smoke test "
                         f"would be asserting on a layout the validator rejects; "
                         f"remedy: keep the fixture within ALLOWED_ASSET_ROLES"),
                )


class RoutingTest(unittest.TestCase):
    """The five exact rules are the only reason this gate runs on its subjects.

    Prefix rules send the packagers, the validator and the fixtures to
    `web_runtime_host` / `creator` / `portal`. Without the exact rules adding
    `ci_contract`, a change to any of them would not run this file, and the
    exit recorded in the ledger entry would be enforced by nothing. The
    document-under-test gate does not cover this: it scans `docs/`,
    `.agents/` and `.claude/`, not `apps/`.
    """

    SUBJECTS = (
        "apps/web-runtime-host/tools/package.py",
        "apps/creator-web/tools/package.py",
        "apps/web-runtime-host/tools/deployment_smoke.py",
        "apps/web-runtime-host/test/deployment_smoke_test.py",
        "apps/creator-web/test/deployment_smoke_test.py",
    )

    def test_every_subject_selects_the_lane_this_gate_runs_in(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "scripts/ci"))
        try:
            import change_scope  # noqa: PLC0415
        finally:
            sys.path.pop(0)
        policy = json.loads(
            (REPO_ROOT / "scripts/ci/scope_policy.json").read_text(encoding="utf-8")
        )
        for path in self.SUBJECTS:
            with self.subTest(path=path):
                lanes, _ = change_scope.path_classification(policy, path)
                self.assertIn(
                    "ci_contract", lanes,
                    msg=(f"why: {path} is what this gate compares, and without an "
                         f"exact scope_policy.json rule adding ci_contract a change "
                         f"to it routes only to its own lanes -- the gate would not "
                         f"run on the change it guards, which is the shape of "
                         f"document-under-test-lane-routing; remedy: keep the exact "
                         f"rule for this path"),
                )


class GateSelfTest(unittest.TestCase):
    """The gate must see what it claims to see, on shapes it has not met."""

    def test_it_reads_positional_and_keyword_roles(self) -> None:
        source = (
            'a = write_hashed_asset(root, "x", ".js", b"", "host_main")\n'
            'b = write_hashed_asset(root, "y", ".js", b"", role="runtime_wasm")\n'
        )
        self.assertEqual(emitted_roles(source, origin="t"), {"host_main", "runtime_wasm"})

    def test_a_wrapper_forwarding_its_role_parameter_is_followed(self) -> None:
        """The Runtime packager's `write_module` shape."""
        source = (
            "def write_module(source, stem, role):\n"
            '    return write_hashed_asset(root, stem, ".mjs", b"", role)\n'
            'a = write_module(p, "x", "platform_module")\n'
            'b = write_module(p, "y", role="host_module")\n'
        )
        self.assertEqual(emitted_roles(source, origin="t"), {"platform_module", "host_module"})

    def test_a_computed_role_is_refused_rather_than_skipped(self) -> None:
        source = 'a = write_hashed_asset(root, "x", ".js", b"", ROLE)\n'
        with self.assertRaises(Undecidable):
            emitted_roles(source, origin="t")

    def test_a_missing_emitter_is_refused_rather_than_read_as_empty(self) -> None:
        with self.assertRaises(Undecidable):
            emitted_roles("x = 1\n", origin="t")

    def test_an_empty_fixture_is_refused_rather_than_read_as_clean(self) -> None:
        with self.assertRaises(Undecidable):
            fixture_roles("ASSETS = ()\n", "ASSETS", origin="t")

    def test_a_fixture_entry_without_a_literal_role_is_refused(self) -> None:
        with self.assertRaises(Undecidable):
            fixture_roles('ASSETS = (("main", ".mjs", ROLE),)\n', "ASSETS", origin="t")

    def test_a_well_formed_fixture_is_read(self) -> None:
        self.assertEqual(
            fixture_roles('ASSETS = (("main", ".mjs", "host_main"),)\n', "ASSETS", origin="t"),
            {"host_main"},
        )

    def test_an_unknown_role_would_be_reported(self) -> None:
        """The #354 shape: a packager gains a role the validator lacks."""
        source = 'a = write_hashed_asset(root, "x", ".js", b"", "brand_new_role")\n'
        allowed, _ = validator_sets()
        self.assertEqual(sorted(emitted_roles(source, origin="t") - allowed), ["brand_new_role"])


if __name__ == "__main__":
    unittest.main()
