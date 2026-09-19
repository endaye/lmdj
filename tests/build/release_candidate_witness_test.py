#!/usr/bin/env python3
"""Real cut journal and official witness bytes; not full Portal or live review."""
from base64 import b64decode, b64encode
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_fixture_interpreter as interpreter
import release_candidate_cut_test as cut_fixture
import release_candidate_source_test as source_fixture
from tools.release.candidate_witness import CandidateWitnessRun, CandidateWitnessError
from tools.release.candidate_source import CandidateSourceError
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import RequestJournal

# The actual snapshot producer is not under test here. Its narrow fixture emits
# the identity/raw-commit fields required by the UNCHANGED official witness
# generator/verifier below, not a complete Portal snapshot. Existing Node
# provenance tests and the full candidate Portal journey are companion proofs.
SNAPSHOT = '''import base64, datetime, json, pathlib, subprocess, sys
build = sys.argv[1]
git = lambda *args: subprocess.check_output(["git", *args])
revision = git("rev-parse", "HEAD").decode().strip()
raw = git("cat-file", "commit", revision)
epoch = int(git("show", "-s", "--format=%ct", revision))
metadata = dict(schema_version=2, product_build=build, revision=revision,
    channel="canary", frozen_at_utc="2026-09-13T00:00:00.000Z",
    source_commit=dict(tree=git("rev-parse", "HEAD^{tree}").decode().strip(),
        raw_base64=base64.b64encode(raw).decode(),
        committed_at_utc=datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")))
pathlib.Path(f"apps/architecture-portal/versioned_metadata/version-{build}.json").write_text(json.dumps(metadata)+"\\n")
pathlib.Path("apps/architecture-portal/versions.json").write_text(json.dumps([build])+"\\n")
'''
SCRIPT = '''set -eu
case "$1" in
version) python3 scripts/fixture-snapshot.py "$2" ;;
resume-version) test -s "apps/architecture-portal/versioned_metadata/version-$2.json" ;;
witness)
  printf 'generate\\n' >> .fixture-witness-calls
  node apps/docs-site/scripts/create-squash-witness.mjs "$2" "$3"
  test ! -f .fixture-fail-generation || exit 23
  ;;
verify-witness)
  printf 'verify\\n' >> .fixture-witness-calls
  node apps/docs-site/scripts/verify-squash-witness.mjs "$2" "$3"
  if test -f .fixture-malformed-output; then printf 'unexpected'; fi
  if test -f .fixture-overflow-output; then printf '%9000s' ''; fi
  ;;
*) exit 64 ;;
esac
'''


class WitnessFixture(source_fixture.SourceFixture):
    def _prepare_seed(self):
        material = cut_fixture.snapshot_fixture.fixture_module.material_fixture.MaterialTest
        commit = material.commit
        def seeded_commit(fixture):
            for name in ("create-squash-witness.mjs", "verify-squash-witness.mjs",
                         "lib/snapshot-provenance.mjs", "lib/repo-facts.mjs"):
                relative = Path("apps/docs-site/scripts") / name
                (fixture.root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, fixture.root / relative)
            canonical = fixture.root / "apps/architecture-portal/versioned_provenance"
            canonical.mkdir(parents=True)
            (canonical / ".gitkeep").touch()
            (fixture.root / "apps/docs-site/versioned_provenance").symlink_to("../architecture-portal/versioned_provenance")
            (fixture.root / "scripts/fixture-snapshot.py").write_text(SNAPSHOT)
            return commit(fixture)
        with patch.object(material, "commit", seeded_commit), patch.object(cut_fixture, "SCRIPT", SCRIPT):
            super()._prepare_seed()

    def setUp(self):
        super().setUp()
        self.merged = self.commit_tree(self.cut_receipt["tree"], self.fixture.base)
        self.main = self.merged
        self.auth_calls = []
        self.witness = self.new_runner()
        self.witness_name = f"apps/architecture-portal/versioned_provenance/version-{self.source['product_build']}-squash-witness.json"
        self.artifact = self.root / self.witness_name

    def new_runner(self, **changes):
        settings = dict(authorize=self.auth_calls.append, observe_main=lambda: self.main,
                        path=interpreter.fixture_path())
        settings.update(changes)
        return CandidateWitnessRun(self.verifier, **settings)

    def run_witness(self, **changes):
        inputs = dict(request=self.request, source=self.source, cut=self.cut_receipt,
                      frozen=self.fixture.frozen, merge_revision=self.merged)
        inputs.update(changes)
        return self.witness.run(**inputs)

    def state(self):
        return json.loads((self.journal / "witness-state.json").read_bytes())["state"]

    def witness_calls(self):
        filename = self.root / ".fixture-witness-calls"
        return filename.read_text().splitlines() if filename.exists() else []

    def crash_after(self, name):
        child = os.fork()
        if child == 0:
            if name in ("generation", "verification"):
                method = "_execute" if name == "generation" else "_execute_capture"
                original = getattr(self.witness.executor, method)
                def crash(*args, **kwargs):
                    original(*args, **kwargs)
                    os._exit(27)
                setattr(self.witness.executor, method, crash)
            else:
                original = RequestJournal._write
                def crash(journal, filename, raw):
                    original(journal, filename, raw)
                    if filename == "witness-operation.json":
                        os._exit(27)
                patch.object(RequestJournal, "_write", crash).start()
            self.run_witness()
            os._exit(99)
        _, child_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(child_status), 27)


class WitnessLifecycleTest(WitnessFixture):
    def test_actual_emitted_receipt_survives_cold_resume_and_later_main(self):
        index = Path(self.tool.git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
        before = self.tool.git("show-ref"), index.read_bytes()
        first = self.run_witness()
        row = self.state()["commands"][-1]
        raw = b64decode(row["output"])
        self.assertEqual(first["receipt"], json.loads(raw))
        self.assertEqual(row["result"], [0, sha256(raw).hexdigest(), len(raw)])
        self.assertEqual(first["receipt"]["witness"], {"path":self.witness_name,
            "bytes":self.artifact.stat().st_size, "sha256":sha256(self.artifact.read_bytes()).hexdigest()})
        self.main = self.commit_tree(self.changed_tree(self.merged, "docs/plans/later.md", b"later"), self.merged)
        self.witness = self.new_runner()
        second = self.run_witness()
        self.assertEqual(first["receipt"], second["receipt"])
        self.assertNotEqual(first["command_history_sha256"], second["command_history_sha256"])
        self.assertEqual(self.witness_calls(), ["generate", "verify", "verify"])
        self.assertEqual((self.tool.git("show-ref"), index.read_bytes()), before)
        self.assertEqual(self.tool.revision("HEAD"), self.cut_receipt["commit"])
        self.assertEqual(self.tool.git("status", "--porcelain"), ("?? " + self.witness_name + "\n").encode())

    def test_unknown_generation_after_process_death_is_verified_not_repeated(self):
        self.crash_after("generation")
        self.assertIsNone(self.state()["commands"][0]["result"])
        original = self.artifact.read_bytes()
        self.witness = self.new_runner()
        self.assertEqual(self.run_witness()["status"], "witness-verified")
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.assertEqual(self.artifact.read_bytes(), original)
        self.assertIsNone(self.state()["commands"][0]["result"])

    def test_nonzero_generation_is_preserved_and_only_verification_resumes(self):
        (self.root / ".fixture-fail-generation").touch()
        with self.assertRaisesRegex(CandidateWitnessError, "witness exited 23"):
            self.run_witness()
        self.witness = self.new_runner()
        self.run_witness()
        self.assertEqual(self.state()["commands"][0]["result"][0], 23)
        self.assertEqual(self.witness_calls(), ["generate", "verify"])

    def test_process_death_after_verifier_requires_new_actual_verification(self):
        self.crash_after("verification")
        self.assertIsNone(self.state()["commands"][-1]["result"])
        self.assertEqual(self.state()["confirmed"], 0)
        self.witness = self.new_runner()
        result = self.run_witness()
        self.assertEqual(result["status"], "witness-verified")
        self.assertEqual(self.witness_calls(), ["generate", "verify", "verify"])
        self.assertIsNone(self.state()["commands"][1]["result"])


class WitnessStateTest(WitnessFixture):
    def test_enrollment_death_does_not_reenroll_or_generate(self):
        self.crash_after("enrollment")
        with self.assertRaisesRegex(CandidateWitnessError, "state disappeared"):
            self.run_witness()
        self.assertEqual(self.witness_calls(), [])
        self.assertFalse(self.artifact.exists())

    def test_missing_state_after_success_is_not_recreated(self):
        self.run_witness()
        (self.journal / "witness-state.json").unlink()
        with self.assertRaisesRegex(CandidateWitnessError, "state disappeared"):
            self.run_witness()
        self.assertEqual(self.witness_calls(), ["generate", "verify"])

    def test_rebound_emitted_output_is_rejected_before_execution(self):
        self.run_witness()
        state = self.state()
        state["commands"][-1]["result"][1] = "a" * 64
        with RequestJournal(self.journal) as journal:
            self.witness._save(journal, state)
        with self.assertRaisesRegex(CandidateWitnessError, "output binding changed"):
            self.run_witness()
        self.assertEqual(self.witness_calls(), ["generate", "verify"])

    def test_budget_exhaustion_never_generates_again(self):
        self.witness = self.new_runner(verification_limit=1)
        self.run_witness()
        with self.assertRaisesRegex(CandidateWitnessError, "budget exhausted"):
            self.run_witness()
        self.assertEqual(self.witness_calls(), ["generate", "verify"])


class WitnessBoundaryTest(WitnessFixture):
    def test_authority_loss_after_child_cannot_confirm_output(self):
        original = self.witness.executor._execute_capture
        def lose(*args, **kwargs):
            result = original(*args, **kwargs)
            self.witness.authorize = lambda _: (_ for _ in ()).throw(ValueError("fixture-secret"))
            return result
        with patch.object(self.witness.executor, "_execute_capture", side_effect=lose):
            with self.assertRaisesRegex(CandidateWitnessError, "authority") as caught:
                self.run_witness()
        self.assertNotIn("fixture-secret", str(caught.exception))
        self.assertEqual(self.state()["confirmed"], 0)
        self.assertEqual(self.state()["commands"][-1]["result"][0], 0)
        self.witness = self.new_runner()
        self.run_witness()
        self.assertEqual(self.witness_calls(), ["generate", "verify", "verify"])

    def test_confirmed_artifact_drift_is_preserved_without_execution(self):
        self.run_witness()
        changed = self.artifact.read_bytes() + b"\n"
        self.artifact.write_bytes(changed)
        with self.assertRaisesRegex(CandidateWitnessError, "artifact identity changed"):
            self.run_witness()
        self.assertEqual(self.artifact.read_bytes(), changed)
        self.assertEqual(self.witness_calls(), ["generate", "verify"])

    def test_unrelated_dirty_source_refuses_before_enrollment(self):
        (self.root / "products/lmdj/version.json").write_bytes(b"dirty")
        with self.assertRaises(CandidateWitnessError):
            self.run_witness()
        self.assertFalse((self.journal / "witness-operation.json").exists())
        self.assertEqual(self.witness_calls(), [])

    def test_source_lock_seam_rejects_alien_and_closed_journals(self):
        arguments = dict(request=self.request, source=self.source, cut=self.cut_receipt,
            frozen=self.fixture.frozen, main_revision=self.merged, merge_revision=self.merged)
        with RequestJournal(self.fixture.container / "alien") as journal:
            with self.assertRaisesRegex(CandidateSourceError, "active source writer"):
                self.verifier.verify_locked(journal, **arguments)
        with self.tool._locked(self.journal.parent) as journal:
            self.assertEqual(self.verifier.verify_locked(journal, **arguments)["merge_sha"], self.merged)
        with self.assertRaisesRegex(CandidateSourceError, "active source writer"):
            self.verifier.verify_locked(journal, **arguments)

    def test_unrelated_untracked_file_is_preserved_before_enrollment(self):
        (self.root / "unrelated").write_bytes(b"keep")
        with self.assertRaisesRegex(CandidateWitnessError, "unrelated untracked"):
            self.run_witness()
        self.assertEqual((self.root / "unrelated").read_bytes(), b"keep")
        self.assertFalse((self.journal / "witness-operation.json").exists())
        self.assertEqual(self.witness_calls(), [])

    def test_changed_durable_cut_binding_invalidates_in_lock_proof(self):
        execute = self.witness.executor._execute
        def change(journal, *args):
            result = execute(journal, *args)
            binding = json.loads((self.journal / "cut-binding.json").read_bytes())
            binding["snapshot_state_sha256"] = "f" * 64
            journal._write("cut-binding.json", canonical_json(binding))
            return result
        with patch.object(self.witness.executor, "_execute", side_effect=change):
            with self.assertRaisesRegex(CandidateWitnessError, "source evidence changed"):
                self.run_witness()
        self.assertEqual(self.witness_calls(), ["generate"])
        self.assertEqual(self.state()["confirmed"], 0)
        self.assertEqual(self.state()["commands"][0]["result"][0], 0)

    def test_main_loses_squash_ancestry_before_command_and_cannot_generate(self):
        observed = iter([self.merged, self.fixture.base])
        self.witness.observe_main = lambda: next(observed)
        with self.assertRaises(CandidateWitnessError):
            self.run_witness()
        self.assertEqual(self.witness_calls(), [])
        self.assertFalse(self.artifact.exists())


class WitnessOutputTest(WitnessFixture):
    def test_malformed_actual_command_output_is_not_a_receipt(self):
        (self.root / ".fixture-malformed-output").touch()
        with self.assertRaises(CandidateWitnessError):
            self.run_witness()
        self.assertEqual(self.state()["confirmed"], 0)
        self.assertEqual(self.state()["commands"][-1]["result"][0], 0)
        self.assertIsNone(self.state()["commands"][-1]["output"])
        self.assertEqual(self.witness_calls(), ["generate", "verify"])

    def test_oversized_actual_command_output_is_not_truncated_into_success(self):
        (self.root / ".fixture-overflow-output").touch()
        with self.assertRaisesRegex(CandidateWitnessError, "output exceeded"):
            self.run_witness()
        row = self.state()["commands"][-1]
        self.assertEqual(row["result"][0], 0)
        self.assertGreater(row["result"][2], 9000)
        self.assertEqual(self.state()["confirmed"], 0)
        self.assertIsNone(row["output"])

    def test_authority_loss_after_intent_prevents_generation_and_replay(self):
        write = RequestJournal._write
        def lose(journal, name, raw):
            write(journal, name, raw)
            if name == "witness-state.json":
                self.witness.authorize = lambda _: (_ for _ in ()).throw(ValueError("fixture-secret"))
        with patch.object(RequestJournal, "_write", lose):
            with self.assertRaisesRegex(CandidateWitnessError, "authority"):
                self.run_witness()
        self.assertEqual(self.witness_calls(), [])
        self.assertIsNone(self.state()["commands"][0]["result"])
        self.witness = self.new_runner()
        with self.assertRaisesRegex(CandidateWitnessError, "verify-witness exited 1"):
            self.run_witness()
        self.assertEqual(self.witness_calls(), ["verify"])
        self.assertFalse(self.artifact.exists())

    def test_existing_official_artifact_is_adopted_without_generation(self):
        with self.tool._locked(self.journal.parent) as journal:
            vector = ("bash", "scripts/docs-site.sh", "witness", self.source["product_build"], self.merged)
            self.assertEqual(self.witness.executor._execute(journal, vector, 30)[0], 0)
        original = self.artifact.read_bytes()
        self.run_witness()
        self.assertFalse(self.state()["generate"])
        self.assertEqual(len(self.state()["commands"]), 1)
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.assertEqual(self.artifact.read_bytes(), original)


class WitnessSchemaTest(unittest.TestCase):
    """Narrow state parser contracts; no candidate/execution acceptance claim."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lmdj-witness-schema-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # _state is a pure journal decoder apart from fixed command vectors.
        self.reader = object.__new__(CandidateWitnessRun)
        self.reader.limit = 3
        self.scope = {"verification_limit":3, "product_build":"1.0.99.0", "merge_revision":"a" * 40}
        self.state = {"schema":"lmdj.candidate-witness-run.v1", "scope":deepcopy(self.scope),
            "generate":True, "commands":[{"arguments":self.reader._vector(self.scope, True),
                                          "result":None, "output":None}], "confirmed":0}

    def install(self, journal, marker=None, state=None):
        journal._write("witness-operation.json", canonical_json(self.scope if marker is None else marker))
        self.reader._save(journal, self.state if state is None else state)

    def test_marker_numeric_type_change_is_not_the_same_scope(self):
        with RequestJournal(self.root / "state") as journal:
            self.install(journal)
            self.assertEqual(self.reader._state(journal, self.scope), self.state)
            self.install(journal, marker=dict(self.scope, verification_limit=3.0))
            before = (self.root / "state/witness-operation.json").read_bytes()
            with self.assertRaisesRegex(CandidateWitnessError, "enrollment changed"):
                self.reader._state(journal, self.scope)
            self.assertEqual((self.root / "state/witness-operation.json").read_bytes(), before)

    def test_state_numeric_type_change_is_not_the_same_scope(self):
        state = deepcopy(self.state)
        state["scope"]["verification_limit"] = 3.0
        with RequestJournal(self.root / "state") as journal:
            self.install(journal, state=state)
            before = (self.root / "state/witness-state.json").read_bytes()
            with self.assertRaisesRegex(CandidateWitnessError, "state schema, scope or digest"):
                self.reader._state(journal, self.scope)
            self.assertEqual((self.root / "state/witness-state.json").read_bytes(), before)

    def test_emitted_byte_count_requires_integer_not_equal_float(self):
        receipt = {"schema":"lmdj.snapshot-witness-check.v1", "status":"verified-by-retained-source",
            "product_build":"1.0.99.0", "source_revision":"a" * 40,
            "introducing_revision":"b" * 40, "source_tree":"c" * 40,
            "metadata":{"path":"metadata", "bytes":12, "sha256":"d" * 64},
            "witness":{"path":"witness", "bytes":12, "sha256":"e" * 64}}
        def row(value):
            raw = canonical_json(value)
            return {"result":[0, sha256(raw).hexdigest(), len(raw)], "output":b64encode(raw).decode()}
        self.assertEqual(self.reader._decode(row(receipt)), receipt)
        for name in ("metadata", "witness"):
            with self.subTest(name=name):
                changed = deepcopy(receipt)
                changed[name]["bytes"] = 12.0
                with self.assertRaisesRegex(CandidateWitnessError, "artifact identity is invalid"):
                    self.reader._decode(row(changed))

    def test_scope_budget_reserves_all_future_output_and_repeated_vectors(self):
        self.reader._check_scope_budget(self.scope)
        for key in ("path", "product_build"):
            with self.subTest(key=key):
                changed = dict(self.scope, **{key:"x" * 40000})
                self.assertLess(len(canonical_json(changed)), 65536)
                with self.assertRaisesRegex(CandidateWitnessError, "command-history budget"):
                    self.reader._check_scope_budget(changed)


if __name__ == "__main__":
    unittest.main()
