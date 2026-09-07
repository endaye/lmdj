#!/usr/bin/env python3
"""Producer/validator parity over the manifest asset-role vocabulary.

This is the gate exit of `.agents/pitfalls/manifest-role-validator-sync.md`.
Twice a manifest asset role existed in one place and not another -- once a
producer gained `product_identity` the validator had never heard of (#354),
once a role the producer gained became required for every Creator manifest,
including the already published rollback anchor the exact-tag deploy validates
(Actions run 34017836312). Both survived packaging, signing, release and every
suite, and were first observed at the deployment boundary.

The gate closes both directions mechanically:

- every role a packager can ship is in the validator's vocabulary, and every
  role the validator names is either shippable today or retained by a published
  Build whose manifest is kept here;
- no producer, validator or smoke fixture restates a role name as a literal, so
  the vocabulary cannot be forked again;
- the validator on `main` accepts the exact `host-manifest.json` of every
  published Web Host Build, with that Build's recorded Host version.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_ROOT = REPO_ROOT / "apps/web-runtime-host/tools"
FIXTURE_ROOT = (
    REPO_ROOT / "apps/web-runtime-host/test/fixtures/published-host-manifests"
)
sys.path.insert(0, str(TOOLS_ROOT))

from deployment_smoke import (  # noqa: E402
    ASSET_ROLES as ROLES,
    SmokeError,
    _validate_manifest,
)


# Every module that names a manifest asset role. `asset_roles.py` is the
# definition and is deliberately absent: it is the one place a role name may
# appear as a literal.
VOCABULARY_CONSUMERS = (
    "apps/creator-web/test/deployment_smoke_test.py",
    "apps/creator-web/tools/package.py",
    "apps/web-runtime-host/test/deployment_smoke_test.py",
    "apps/web-runtime-host/tools/deployment_smoke.py",
    "apps/web-runtime-host/tools/package.py",
)
# The packagers' only asset writers. Every call names the role of the asset it
# writes, and that argument must resolve through the shared vocabulary.
ASSET_WRITERS = ("write_hashed_asset", "write_module")
ROLE_PARAMETER = "role"
ROLE_PARAMETER_POSITION = {"write_hashed_asset": 4, "write_module": 2}
PACKAGERS = {
    "creator-web": "apps/creator-web/tools/package.py",
    "web-runtime-host": "apps/web-runtime-host/tools/package.py",
}


def walk_with_parameters(node: ast.AST, parameters: frozenset[str]):
    """Yield every node with the parameter names of the functions enclosing it."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        arguments = node.args
        parameters = parameters | {
            argument.arg
            for argument in (
                arguments.posonlyargs + arguments.args + arguments.kwonlyargs
            )
        }
    yield node, parameters
    for child in ast.iter_child_nodes(node):
        yield from walk_with_parameters(child, parameters)


def role_names() -> frozenset[str]:
    return frozenset(ROLES.ALLOWED_ASSET_ROLES)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def provenance() -> list[dict[str, object]]:
    record = load_json(FIXTURE_ROOT / "provenance.json")
    assert isinstance(record, dict)
    manifests = record["manifests"]
    assert isinstance(manifests, list)
    return manifests


def published_roles() -> frozenset[str]:
    roles: set[str] = set()
    for entry in provenance():
        manifest = load_json(FIXTURE_ROOT / str(entry["fixture"]))
        assert isinstance(manifest, dict)
        roles.update(asset["role"] for asset in manifest["assets"])
    return frozenset(roles)


class VocabularyParity(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = load_json(
            REPO_ROOT / ROLES.RUNTIME_IDENTITY_RELATIVE_PATH
        )
        self.generated_identity = load_json(
            REPO_ROOT / ROLES.GENERATED_RUNTIME_IDENTITY_RELATIVE_PATH
        )

    def producible(self, host_id: str) -> frozenset[str]:
        return ROLES.emitted_roles_from_identity(self.identity, host_id)

    def test_declared_emission_matches_the_packager_inventory(self):
        for host_id, declared in sorted(
            ROLES.EMITTED_ASSET_ROLES_BY_HOST_ID.items()
        ):
            with self.subTest(host_id=host_id):
                produced = self.producible(host_id)
                self.assertEqual(
                    declared,
                    produced,
                    "why: the asset roles declared for Host "
                    f"{host_id!r} in apps/web-runtime-host/tools/asset_roles.py "
                    f"({sorted(declared)}) are not the roles its packager can "
                    f"ship ({sorted(produced)}), which are the role values of "
                    f"hosts.{host_id}.expected_assets in "
                    f"{ROLES.RUNTIME_IDENTITY_RELATIVE_PATH} -- the inventory "
                    "the packager orders its manifest from and re-verifies "
                    "position by position. A declaration that does not match "
                    "the producer cannot gate the producer.\n"
                    "remedy: make the two agree in this same change. If the "
                    "Host really gained or lost an asset role, edit "
                    f"{ROLES.RUNTIME_IDENTITY_RELATIVE_PATH}, regenerate "
                    f"{ROLES.GENERATED_RUNTIME_IDENTITY_RELATIVE_PATH}, and "
                    "update ALLOWED_ASSET_ROLES together with the matching "
                    "*_EMITTED_ASSET_ROLES set in "
                    "apps/web-runtime-host/tools/asset_roles.py.",
                )

    def test_generated_identity_agrees_with_its_source(self):
        for host_id in sorted(ROLES.EMITTED_ASSET_ROLES_BY_HOST_ID):
            with self.subTest(host_id=host_id):
                self.assertEqual(
                    ROLES.emitted_roles_from_identity(self.identity, host_id),
                    ROLES.emitted_roles_from_identity(
                        self.generated_identity, host_id
                    ),
                    "why: the generated Runtime identity "
                    f"{ROLES.GENERATED_RUNTIME_IDENTITY_RELATIVE_PATH} names "
                    f"different asset roles for Host {host_id!r} than its "
                    f"source {ROLES.RUNTIME_IDENTITY_RELATIVE_PATH}. The "
                    "packagers read the generated file, so the source no "
                    "longer describes what ships.\n"
                    "remedy: regenerate the identity with "
                    "tools/web-runtime/generate_runtime_identity.py and commit "
                    "the result in this same change.",
                )

    def test_every_producible_role_is_in_the_validator_vocabulary(self):
        producible = frozenset().union(
            *(
                self.producible(host_id)
                for host_id in ROLES.EMITTED_ASSET_ROLES_BY_HOST_ID
            )
        )
        unknown = sorted(producible - ROLES.ALLOWED_ASSET_ROLES)
        self.assertEqual(
            unknown,
            [],
            "why: a Web Host packager can ship the manifest asset roles "
            f"{unknown}, which the shared deployment validator's "
            "ALLOWED_ASSET_ROLES does not contain, so every Build from this "
            "commit on packages, signs, releases and passes every suite and "
            "then fails apps/web-runtime-host/tools/deployment_smoke.py at the "
            "deployment boundary.\n"
            "remedy: add each role to ALLOWED_ASSET_ROLES in "
            "apps/web-runtime-host/tools/asset_roles.py in the same change "
            "that taught the packager to emit it. Add it to "
            "SINGLETON_ASSET_ROLES or to a Creator required inventory only if "
            "every already published manifest under "
            "apps/web-runtime-host/test/fixtures/published-host-manifests/ "
            "still satisfies the rule; the deploy validates the previously "
            "published Build as its rollback anchor.",
        )

    def test_every_validator_role_is_producible_or_published(self):
        producible = frozenset().union(
            *(
                self.producible(host_id)
                for host_id in ROLES.EMITTED_ASSET_ROLES_BY_HOST_ID
            )
        )
        orphans = sorted(
            ROLES.ALLOWED_ASSET_ROLES - producible - published_roles()
        )
        self.assertEqual(
            orphans,
            [],
            "why: the shared deployment validator accepts the manifest asset "
            f"roles {orphans}, which no packager can ship and no retained "
            "published manifest carries, so the vocabulary has grown a name "
            "nothing produces and the validator silently accepts a manifest no "
            "Build of this repository could have written.\n"
            "remedy: remove each role from ALLOWED_ASSET_ROLES in "
            "apps/web-runtime-host/tools/asset_roles.py, or, if a published "
            "Build really carries it, retain that Build's host-manifest.json "
            "under apps/web-runtime-host/test/fixtures/published-host-manifests/ "
            "with its provenance.json entry, which is what keeps a retired "
            "role justified.",
        )

    def test_creator_required_inventory_tracks_the_creator_packager(self):
        self.assertEqual(
            ROLES.CREATOR_CURRENT_ASSET_ROLES,
            self.producible("creator-web"),
            "why: the inventory the validator requires of a current Creator "
            f"manifest ({sorted(ROLES.CREATOR_CURRENT_ASSET_ROLES)}) is not "
            "what the Creator packager ships "
            f"({sorted(self.producible('creator-web'))}), so a Creator "
            "deployment cannot validate itself.\n"
            "remedy: keep CREATOR_CURRENT_ASSET_ROLES equal to "
            "CREATOR_WEB_EMITTED_ASSET_ROLES in "
            "apps/web-runtime-host/tools/asset_roles.py, and express any "
            "Host-version difference in CREATOR_LEGACY_ASSET_ROLES instead.",
        )

    def test_runtime_singleton_roles_are_producible(self):
        missing = sorted(
            ROLES.SINGLETON_ASSET_ROLES - self.producible("web-runtime-host")
        )
        self.assertEqual(
            missing,
            [],
            "why: the validator requires exactly one asset of each role in "
            f"SINGLETON_ASSET_ROLES, but the Runtime Host packager cannot ship "
            f"{missing}, so no Runtime Host manifest can ever satisfy the "
            "rule.\n"
            "remedy: remove each role from SINGLETON_ASSET_ROLES in "
            "apps/web-runtime-host/tools/asset_roles.py, or restore its entry "
            "in hosts.web-runtime-host.expected_assets in "
            f"{ROLES.RUNTIME_IDENTITY_RELATIVE_PATH}.",
        )


class SingleDefinition(unittest.TestCase):
    def test_no_consumer_restates_a_role_name_as_a_literal(self):
        known = role_names()
        offenders = []
        for relative in VOCABULARY_CONSUMERS:
            tree = ast.parse(
                (REPO_ROOT / relative).read_text(encoding="utf-8"), relative
            )
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value in known:
                    offenders.append(f"{relative}:{node.lineno}: {node.value!r}")
        self.assertEqual(
            offenders,
            [],
            "why: a manifest asset role is written as a string literal outside "
            "apps/web-runtime-host/tools/asset_roles.py, which is how the "
            "vocabulary forked in the first place: a producer, the validator "
            "and each smoke fixture each carried their own copy, and a change "
            "to one did not reach the others.\n"
            "remedy: replace each literal below with the matching constant "
            "from the shared vocabulary, reached as ROLES.<NAME> in the "
            "packagers or ASSET_ROLES.<NAME> through deployment_smoke:\n  "
            + "\n  ".join(offenders),
        )

    def test_every_packager_role_argument_resolves_through_the_vocabulary(self):
        offenders = []
        for host_id, relative in sorted(PACKAGERS.items()):
            tree = ast.parse(
                (REPO_ROOT / relative).read_text(encoding="utf-8"), relative
            )
            calls = 0
            for node, parameters in walk_with_parameters(tree, frozenset()):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(
                    node.func, "attr", None
                )
                if name not in ASSET_WRITERS:
                    continue
                argument = None
                for keyword in node.keywords:
                    if keyword.arg == ROLE_PARAMETER:
                        argument = keyword.value
                position = ROLE_PARAMETER_POSITION[name]
                if argument is None and len(node.args) > position:
                    argument = node.args[position]
                if argument is None:
                    continue
                calls += 1
                # A constant from the shared vocabulary, or the role parameter
                # of the enclosing helper forwarding it on. The forwarding case
                # is what `write_module` does; the value it forwards is checked
                # at its own call sites, and `write_hashed_asset` additionally
                # rejects an undeclared role at package time.
                resolved = (
                    isinstance(argument, ast.Attribute)
                    and isinstance(argument.value, ast.Name)
                    and argument.value.id == "ROLES"
                ) or (
                    isinstance(argument, ast.Name)
                    and argument.id in parameters
                )
                if not resolved:
                    offenders.append(
                        f"{relative}:{argument.lineno}: "
                        f"{ast.dump(argument)[:120]}"
                    )
            self.assertGreater(
                calls,
                0,
                f"why: no asset-writer call in {relative} was found, so this "
                "gate would pass vacuously for Host "
                f"{host_id!r} while the packager still emits roles.\n"
                "remedy: update ASSET_WRITERS and ROLE_PARAMETER_POSITION in "
                "apps/web-runtime-host/test/manifest_asset_role_parity_test.py "
                "to name the packager's current asset writers.",
            )
        self.assertEqual(
            offenders,
            [],
            "why: a packager names the role of an asset it writes with "
            "something other than a constant from the shared vocabulary, so a "
            "role can enter a published manifest without the shared "
            "vocabulary, and therefore the deployment validator, ever knowing "
            "about it.\n"
            "remedy: pass ROLES.<NAME> from "
            "apps/web-runtime-host/tools/asset_roles.py at each site below, "
            "adding the constant to that module if the role is new:\n  "
            + "\n  ".join(offenders),
        )


class PublishedRollbackAnchors(unittest.TestCase):
    """Every published Build the validator can be asked to baseline against.

    The exact-tag deploy discovers the previously published deployment with the
    same validator it uses on the candidate, so a validator that rejects an
    already published manifest stops the deploy before it starts. The corpus is
    every `lmdj-v*` Release asset that contains a Web Host `host-manifest.json`,
    which is the complete set: no earlier tag ships a Web Host archive.
    """

    def test_provenance_covers_every_retained_fixture(self):
        recorded = {str(entry["fixture"]) for entry in provenance()}
        present = {
            path.name
            for path in FIXTURE_ROOT.glob("*.json")
            if path.name != "provenance.json"
        }
        self.assertEqual(
            recorded,
            present,
            "why: a retained published manifest has no provenance entry, or a "
            "provenance entry names no file, so the corpus no longer states "
            "which immutable Release asset each rollback anchor came from.\n"
            "remedy: keep apps/web-runtime-host/test/fixtures/"
            "published-host-manifests/provenance.json listing exactly the "
            f"manifests beside it. recorded={sorted(recorded)} "
            f"present={sorted(present)}",
        )

    def test_each_fixture_is_the_published_bytes(self):
        for entry in provenance():
            with self.subTest(fixture=entry["fixture"]):
                payload = (FIXTURE_ROOT / str(entry["fixture"])).read_bytes()
                self.assertEqual(
                    hashlib.sha256(payload).hexdigest(),
                    entry["manifest_sha256"],
                    "why: the retained rollback anchor "
                    f"{entry['fixture']!r} no longer hashes to the digest "
                    "recorded for the manifest published inside "
                    f"{entry['archive']!r} (archive sha256 "
                    f"{entry['archive_sha256']}), so it has been edited and is "
                    "no longer evidence of what a published Build really "
                    "carries.\n"
                    "remedy: restore the file from that Release asset -- "
                    f"gh release download {entry['release_tag']} -p "
                    f"'{entry['archive']}' and extract dist/host-manifest.json "
                    "-- rather than editing the fixture to match the "
                    "validator.",
                )
                manifest = json.loads(payload)
                # Runtime Host manifests older than the extended schema carry
                # no host_id at all, and one era spelled it
                # `lmdj-web-runtime-host`; the validator still accepts both, so
                # the recorded identity is compared only where the manifest
                # states it.
                self.assertIn(
                    manifest.get("host_id", entry["host_id"]),
                    (entry["host_id"], f"lmdj-{entry['host_id']}"),
                    "why: the recorded Host ID of "
                    f"{entry['fixture']!r} disagrees with the manifest it "
                    "retains.\n"
                    "remedy: correct the provenance entry from the manifest, "
                    "not the other way round.",
                )
                self.assertEqual(
                    (
                        manifest["host_version"],
                        manifest["product_build"],
                    ),
                    (
                        entry["host_version"],
                        entry["product_build"],
                    ),
                    "why: the recorded identity of "
                    f"{entry['fixture']!r} disagrees with the manifest it "
                    "retains, so the anchor would be validated against the "
                    "wrong Host version.\n"
                    "remedy: correct the provenance entry from the manifest, "
                    "not the other way round.",
                )

    def test_validator_accepts_every_published_manifest(self):
        for entry in provenance():
            with self.subTest(fixture=entry["fixture"]):
                manifest = load_json(FIXTURE_ROOT / str(entry["fixture"]))
                try:
                    _validate_manifest(
                        manifest,
                        expected_product_build=str(entry["product_build"]),
                        expected_host_version=str(entry["host_version"]),
                        expected_host_id=str(entry["host_id"]),
                    )
                except SmokeError as error:
                    self.fail(
                        "why: the deployment validator on this commit rejects "
                        f"the published manifest of {entry['host_id']} "
                        f"{entry['host_version']} / Product Build "
                        f"{entry['product_build']} ({entry['release_tag']}) "
                        f"with {str(error)!r}. The exact-tag deploy discovers "
                        "the previously published deployment with this same "
                        "validator as its rollback identity, so this change "
                        "would stop the next deploy before the candidate is "
                        "ever staged -- exactly how Actions run 34017836312 "
                        "failed.\n"
                        "remedy: keep the new rule conditional on the Host "
                        "version that introduced it, the way "
                        "CREATOR_LEGACY_ASSET_ROLES keeps Creator Host 2.x on "
                        "its five-role inventory. Do not relax the validator "
                        "for current Builds, and do not edit or delete the "
                        "retained manifest to make this pass."
                    )

    def test_creator_anchors_match_their_host_major_inventory(self):
        seen = 0
        for entry in provenance():
            if entry["host_id"] != "creator-web":
                continue
            seen += 1
            manifest = load_json(FIXTURE_ROOT / str(entry["fixture"]))
            assert isinstance(manifest, dict)
            roles = frozenset(
                asset["role"] for asset in manifest["assets"]
            )
            major = int(str(entry["host_version"]).partition(".")[0])
            expected = (
                ROLES.CREATOR_CURRENT_ASSET_ROLES
                if major >= 3
                else ROLES.CREATOR_LEGACY_ASSET_ROLES
            )
            with self.subTest(fixture=entry["fixture"]):
                self.assertEqual(
                    roles,
                    expected,
                    "why: the published Creator Host "
                    f"{entry['host_version']} manifest carries the roles "
                    f"{sorted(roles)}, but the validator requires "
                    f"{sorted(expected)} of a Host {major}.x Creator "
                    "manifest, so this published Build can no longer serve as "
                    "the deploy's rollback anchor.\n"
                    "remedy: adjust the Host-major split in "
                    "CREATOR_CURRENT_ASSET_ROLES / CREATOR_LEGACY_ASSET_ROLES "
                    "in apps/web-runtime-host/tools/asset_roles.py so each "
                    "published Host major keeps the inventory it actually "
                    "shipped.",
                )
        self.assertGreaterEqual(
            seen,
            2,
            "why: fewer than two published Creator manifests are retained, so "
            "the Host-major inventory split that Actions run 34017836312 broke "
            "is no longer covered on both sides of Creator Host 3.0.0.\n"
            "remedy: retain the host-manifest.json of each published Creator "
            "Build under apps/web-runtime-host/test/fixtures/"
            "published-host-manifests/ with its provenance.json entry.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
