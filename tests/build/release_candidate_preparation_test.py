#!/usr/bin/env python3
"""Actual composed Git/journals/commands; only Portal entrypoints are fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_fixture_interpreter as interpreter
import release_candidate_source_setup_test as setup_fixture
import release_candidate_checks_test as checks_fixture
from tools.release.candidate_preparation import CandidatePreparation, CandidatePreparationError
from tools.release.model import canonical_json
from tools.release.orchestration import RequestJournal
from tools.release.candidate_inputs import CandidateInputs
from tools.release.candidate_material import CandidateBuildMaterial
from tools.release.candidate_material_scope import P1_MATERIAL_SCOPE


SCRIPT = checks_fixture.SCRIPT.replace('case "$1" in', '''case "$1" in
install)
  printf 'install\\n' >> .fixture-install-calls
  printf 'actual install fixture\\n'
  ;;''')


class PreparationFixture(setup_fixture.SetupFixture):
    def setUp(self):
        original = setup_fixture.fixture.MaterialTest.commit
        def seed(material):
            canonical = material.root / 'apps/architecture-portal'
            canonical.mkdir(parents=True, exist_ok=True)
            (canonical / 'versions.json').write_text('[]\n')
            (canonical / 'versioned_metadata').mkdir()
            (canonical / 'versioned_metadata/.gitkeep').touch()
            alias = material.root / 'apps/docs-site'
            alias.mkdir(parents=True, exist_ok=True)
            (alias / 'versions.json').symlink_to('../architecture-portal/versions.json')
            (alias / 'versioned_metadata').symlink_to('../architecture-portal/versioned_metadata')
            (material.root / 'scripts/docs-site.sh').write_text(SCRIPT)
            owned = material.root / 'tests/build/ci_change_scope_test.py'
            owned.parent.mkdir(parents=True, exist_ok=True)
            owned.write_text("print('actual ownership fixture')\n")
            return original(material)
        with patch.object(setup_fixture.fixture.MaterialTest, 'commit', seed):
            super().setUp()
        self.parent_root = self.fixture.container / 'preparation'
        self.clock_calls = []
        self.parent = self.new_parent()

    def new_parent(self, **changes):
        def clock():
            self.clock_calls.append(True)
            return 2100000000
        args = dict(repository_root=self.fixture.root, source_root=self.destination,
            reservation_root=self.fixture.state, request=self.request, authorize=self.authorized.append,
            observe_main=lambda: self.main, path=interpreter.fixture_path(), author_name='Fixture',
            author_email='fixture@example.invalid', source_timestamp=2000000000, clock=clock)
        args.update(changes)
        return CandidatePreparation(self.parent_root, **args)

    def enroll_parent(self):
        return self.parent.observe(initialize=True)

    def prepare_parent(self):
        return self.parent.prepare(before_write=lambda: None)

    def parent_state(self):
        return json.loads((self.parent_root / self.parent.STATE).read_bytes())

    def child_journal(self):
        return Path(self.parent.local.git('rev-parse', '--absolute-git-dir').decode().strip()) / self.parent.local.JOURNAL_NAME

    def command_calls(self):
        return {name:(self.destination / name).read_bytes() for name in
                ('.fixture-install-calls', '.fixture-calls', '.fixture-check-calls')}


class PreparationJourneyTest(PreparationFixture):
    def test_actual_all_legs_then_cold_observation_preserves_every_history(self):
        before = self.catalogue()
        self.assertEqual(self.parent.observe()['status'], 'absent')
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.enroll_parent()['status'], 'pending')
        self.assertEqual(self.catalogue(), before)
        result = self.prepare_parent()
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(self.command_calls(), {'.fixture-install-calls':b'install\n',
            '.fixture-calls':b'version\nresume\n', '.fixture-check-calls':b'check\ncheck\n'})
        self.assertEqual(self.parent.local.revision('HEAD'), result['checked_cut']['cut']['commit'])
        self.assertEqual(self.parent.local.revision('HEAD^'), self.fixture.base)
        self.assertEqual(self.parent.local.revision(result['checked_cut']['cut']['source_retention_ref']), result['source']['commit'])
        child = self.child_journal()
        histories = [self.parent_root / self.parent.STATE, self.parent_root / self.parent.MARKER,
            self.parent.setup.root / self.parent.setup.STATE,
            child / 'binding.json', child / 'snapshot-state.json', child / 'cut-binding.json',
            child / self.parent.checks.STATE]
        before = [name.read_bytes() for name in histories], self.catalogue(), self.command_calls()
        self.parent = self.new_parent()
        with patch('tools.release.task_verification.PublicationTaskVerifier._execute',
                   side_effect=AssertionError('cold observation must not execute any command')):
            self.assertEqual(self.parent.observe(), result)
            self.assertEqual(self.prepare_parent(), result)
        self.assertEqual(([name.read_bytes() for name in histories], self.catalogue(), self.command_calls()), before)
        self.assertEqual(self.clock_calls, [True])


class PreparationPostMergeAuthorityTest(PreparationFixture):
    """The transition's reviewed-squash proof re-proves authority after the cut
    merged, outside any drive session, against a main that carries the cut."""

    def commit(self, tree, parent, message):
        import subprocess
        env = dict(os.environ, GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                   GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid",
                   GIT_AUTHOR_DATE="2000000000 +0000", GIT_COMMITTER_DATE="2000000000 +0000")
        return subprocess.run(["git", "-C", str(self.fixture.root), "commit-tree", tree, "-p", parent,
                               "-m", message], check=True, capture_output=True, env=env).stdout.decode().strip()

    def tree_with(self, base_tree, name, data):
        import subprocess, tempfile
        root = str(self.fixture.root)
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
            subprocess.run(["git", "-C", root, "read-tree", base_tree], check=True, env=env)
            oid = subprocess.run(["git", "-C", root, "hash-object", "-w", "--stdin"], input=data,
                                 check=True, capture_output=True, env=env).stdout.decode().strip()
            subprocess.run(["git", "-C", root, "update-index", "--add", "--cacheinfo", f"100644,{oid},{name}"],
                           check=True, env=env)
            return subprocess.run(["git", "-C", root, "write-tree"], check=True, capture_output=True,
                                  env=env).stdout.decode().strip()

    def prepared_cut(self):
        self.enroll_parent()
        return self.prepare_parent()["checked_cut"]["cut"]

    def test_merged_own_squash_passes_the_post_drive_reproof(self):
        cut = self.prepared_cut()
        squash = self.commit(cut["tree"], self.fixture.base, "squash of the candidate cut")
        self.main = squash
        self.parent = self.new_parent()
        self.parent._child_authorize({})

    def test_input_drift_before_the_squash_is_still_refused(self):
        from tools.release.candidate_inputs import CandidateInputError
        cut = self.prepared_cut()
        base_tree = self.parent.setup.repository.git("rev-parse", self.fixture.base + "^{tree}").decode().strip()
        drift = self.commit(self.tree_with(base_tree, "products/lmdj/drift.txt", b"drift"),
                            self.fixture.base, "input drift before the squash")
        squash = self.commit(self.tree_with(cut["tree"], "products/lmdj/drift.txt", b"drift"),
                             drift, "squash of the candidate cut")
        self.main = squash
        self.parent = self.new_parent()
        with self.assertRaises(CandidateInputError):
            self.parent._child_authorize({})

    def test_unmerged_drift_without_the_squash_is_refused(self):
        from tools.release.candidate_inputs import CandidateInputError
        self.prepared_cut()
        base_tree = self.parent.setup.repository.git("rev-parse", self.fixture.base + "^{tree}").decode().strip()
        self.main = self.commit(self.tree_with(base_tree, "products/lmdj/drift.txt", b"drift"),
                                self.fixture.base, "input drift, no squash")
        self.parent = self.new_parent()
        with self.assertRaises(CandidateInputError):
            self.parent._child_authorize({})


class PreparationEnrollmentTest(PreparationFixture):
    def test_same_type_authority_exception_is_private_at_initial_enrollment(self):
        def refuse(_):
            raise CandidatePreparationError('PRIVATE-AUTHORITY')
        self.parent = self.new_parent(authorize=refuse)
        try:
            self.enroll_parent()
        except CandidatePreparationError:
            rendered = traceback.format_exc()
        else:
            self.fail('authority must refuse')
        self.assertNotIn('PRIVATE-AUTHORITY', rendered)
        self.assertFalse((self.parent_root / self.parent.MARKER).exists())

    def test_prepare_never_reenrolls_missing_parent(self):
        with self.assertRaisesRegex(CandidatePreparationError, 'enroll before caller intent'):
            self.prepare_parent()
        self.assertFalse(self.destination.exists())

    def test_missing_setup_enrollment_after_parent_enrollment_is_unknown(self):
        self.enroll_parent()
        (self.parent.setup.root / self.parent.setup.MARKER).unlink()
        (self.parent.setup.root / self.parent.setup.STATE).unlink()
        self.assertEqual(self.prepare_parent()['status'], 'unknown')
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.parent.setup.root / self.parent.setup.MARKER).exists())

    def test_request_numeric_scope_change_is_not_adopted(self):
        self.enroll_parent()
        state = self.parent_state()
        state['scope']['request']['actor_id'] = float(state['scope']['request']['actor_id'])
        (self.parent_root / self.parent.STATE).write_bytes(canonical_json(state))
        with self.assertRaises(CandidatePreparationError):
            self.parent.observe()
        self.assertFalse(self.destination.exists())


class PreparationCrashTest(PreparationFixture):
    def crash_after(self, owner, name, code):
        self.enroll_parent()
        child = os.fork()
        if child == 0:
            original = getattr(owner, name)
            def die(*args, **kwargs):
                original(*args, **kwargs)
                os._exit(code)
            setattr(owner, name, die)
            self.prepare_parent()
            os._exit(99)
        _, result = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(result), code)

    def test_source_child_success_survives_parent_checkpoint_death(self):
        self.crash_after(self.parent.local, 'prepare_source', 71)
        self.assertIsNone(self.parent_state()['source'])
        commit = self.parent.local.revision('HEAD')
        catalogue = self.catalogue()
        self.parent = self.new_parent()
        self.assertEqual(self.parent.observe()['status'], 'pending')
        self.assertEqual(self.parent_state()['source']['commit'], commit)
        self.assertEqual(self.parent.local.revision('HEAD'), commit)
        self.assertEqual(self.catalogue(), catalogue)
        self.assertFalse((self.destination / '.fixture-calls').exists())
        result = self.prepare_parent()
        self.assertEqual(result['source']['commit'], commit)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(self.calls(), ['install'])

    def test_snapshot_child_success_survives_parent_checkpoint_death_without_resume(self):
        self.crash_after(self.parent.snapshot, 'run', 72)
        self.assertIsNone(self.parent_state()['snapshot'])
        journal = self.child_journal()
        history = (journal / 'snapshot-state.json').read_bytes()
        self.parent = self.new_parent()
        self.assertEqual(self.parent.observe()['status'], 'pending')
        self.assertIsNotNone(self.parent_state()['snapshot'])
        self.assertEqual(self.prepare_parent()['status'], 'verified')
        self.assertEqual((journal / 'snapshot-state.json').read_bytes(), history)
        self.assertEqual((self.destination / '.fixture-calls').read_bytes(), b'version\nresume\n')

    def test_cut_child_success_survives_parent_checkpoint_death_without_commands(self):
        self.crash_after(self.parent.checks, 'prepare', 73)
        self.assertIsNone(self.parent_state()['checked_cut'])
        history = (self.child_journal() / self.parent.checks.STATE).read_bytes()
        commit = self.parent.local.revision('HEAD')
        before = self.command_calls()
        def forbidden():
            raise AssertionError('must not select another timestamp')
        self.parent = self.new_parent(clock=forbidden)
        with patch('tools.release.task_verification.PublicationTaskVerifier._execute',
                   side_effect=AssertionError('must not rerun a completed child')):
            result = self.parent.observe()
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['checked_cut']['cut']['commit'], commit)
        self.assertEqual((self.child_journal() / self.parent.checks.STATE).read_bytes(), history)
        self.assertEqual(self.command_calls(), before)


class PreparationSourceGuardTest(PreparationFixture):
    def test_authority_lost_after_material_stops_before_first_source_file_write(self):
        self.enroll_parent()
        original = self.parent.material.prepare
        def prepare(*args, **kwargs):
            result = original(*args, **kwargs)
            def refuse(_):
                raise PermissionError('PRIVATE-AUTHORITY')
            self.parent.authorize = refuse
            return result
        self.parent.material.prepare = prepare
        with self.assertRaises(CandidatePreparationError) as caught:
            self.prepare_parent()
        self.assertNotIn('PRIVATE-AUTHORITY', str(caught.exception))
        self.assertEqual(self.parent.local.revision('HEAD'), self.fixture.base)
        self.assertEqual(self.parent.local.revision_from_index(), self.fixture.git('rev-parse', self.fixture.base + '^{tree}'))
        from tools.release.candidate_workspace import FILES
        for name in FILES:
            self.assertEqual((self.destination / name).read_bytes(), (self.fixture.root / name).read_bytes())
        self.assertFalse((self.destination / '.fixture-calls').exists())


class PreparationObserverBoundaryTest(checks_fixture.ChecksFixture):
    def test_last_observer_authority_cannot_delete_snapshot_history(self):
        result = self.prepare_checks()
        arguments = dict(request=self.request, source=self.source, frozen=self.fixture.frozen,
            main_revision=self.fixture.base, snapshot_sha256=self.receipt['sha256'],
            author_name='Fixture', author_email='fixture@example.invalid', timestamp=2000000000)
        self.assertEqual(self.checks.observe(**arguments)['checked_cut'], result)
        calls = self.check_calls(), self.commands()
        seen = []
        def remove(_):
            seen.append(True)
            if len(seen) == 2:
                (self.journal / 'snapshot-state.json').unlink()
        self.checks.authorize = remove
        with self.assertRaises(checks_fixture.CandidateChecksError):
            self.checks.observe(**arguments)
        self.assertEqual(seen, [True, True])
        self.assertFalse((self.journal / 'snapshot-state.json').exists())
        self.assertEqual((self.check_calls(), self.commands()), calls)


class CoordinatedPreparationFixture(PreparationFixture):
    def setUp(self):
        self.material_authorized = []
        inputs = CandidateInputs(ROOT, material_scope=P1_MATERIAL_SCOPE)
        frozen = inputs.freeze(inputs.git('rev-parse', 'HEAD').decode().strip())
        exporter = CandidateBuildMaterial(ROOT, Path('unused'), material_scope=P1_MATERIAL_SCOPE)
        original = setup_fixture.fixture.MaterialTest.commit
        def seed(material):
            exporter._export(frozen, material.root)
            return original(material)
        with patch.object(setup_fixture.fixture.MaterialTest, 'commit', seed):
            super().setUp()

    def new_parent(self, **changes):
        changes.setdefault('material_scope', P1_MATERIAL_SCOPE)
        changes.setdefault('authorize_material', lambda request, scope:
                           self.material_authorized.append((request, scope)))
        return super().new_parent(**changes)


class CoordinatedPreparationTest(CoordinatedPreparationFixture):
    def test_managed_carrier_scope_denial_cannot_provision_the_catalogue(self):
        from tools.release.carriers import enroll_candidate
        from tools.release.orchestration import JournalError
        from tools.release.candidate import CATALOG
        catalogue = self.fixture.state / CATALOG
        catalogue.unlink()
        def deny(request, scope):
            raise ValueError('private scope denial')
        with self.assertRaisesRegex(JournalError, 'scoped candidate material authority'):
            enroll_candidate(request=self.request, preparation_root=self.parent_root,
                repository_root=self.fixture.root, source_root=self.destination,
                reservation_root=self.fixture.state, transition_root=self.fixture.container / 'transition',
                witness_root=self.fixture.container / 'witness', repository_id=123,
                client=object(), token='fixture-unused', authorize=self.authorized.append,
                observe_main=lambda:self.main, review=lambda *args:None,
                verify_merged=lambda *args:None, clock=lambda:2100000000,
                path=interpreter.fixture_path(), author_name='Fixture',
                author_email='fixture@example.invalid', source_timestamp=2000000000,
                material_scope=P1_MATERIAL_SCOPE, authorize_material=deny)
        self.assertFalse(catalogue.exists())
        self.assertFalse(self.parent_root.exists())
        self.assertFalse(self.destination.exists())

    def test_scope_denial_precedes_freeze_enrollment_and_reservation(self):
        before = self.catalogue(), self.fixture.git('show-ref')
        def deny(request, scope):
            raise ValueError('private authority response must not escape')
        parent = self.new_parent(authorize_material=deny)
        with patch.object(parent.material.inputs, 'freeze') as freeze:
            with self.assertRaises(CandidatePreparationError) as caught:
                parent.observe(initialize=True)
            freeze.assert_not_called()
        self.assertNotIn('private authority', str(caught.exception))
        self.assertFalse(self.parent_root.exists())
        self.assertFalse(self.destination.exists())
        self.assertEqual(before, (self.catalogue(), self.fixture.git('show-ref')))

    def test_enrollment_scope_cannot_be_adopted_by_a_legacy_resume(self):
        self.assertEqual(self.enroll_parent()['status'], 'pending')
        before = self.parent_state(), self.catalogue()
        with self.assertRaisesRegex(CandidatePreparationError, 'rebound'):
            self.new_parent(material_scope=None, authorize_material=None).observe()
        self.assertEqual(before, (self.parent_state(), self.catalogue()))
        self.assertFalse(self.destination.exists())

    def test_actual_all_legs_scope_receipts_and_cold_resume_preserve_exact_22(self):
        self.assertEqual(self.enroll_parent()['status'], 'pending')
        result = self.prepare_parent()
        self.assertEqual(result['status'], 'verified')
        source, cut = result['source'], result['checked_cut']['cut']
        self.assertEqual(source['material_scope'], P1_MATERIAL_SCOPE)
        self.assertEqual(result['frozen']['material_scope'], P1_MATERIAL_SCOPE)
        self.assertEqual(set(source['files']), self.parent.local.files)
        self.assertEqual(len(source['files']), 22)
        local = self.parent.local
        self.assertEqual(local.revision(source['commit'] + '^'), self.fixture.base)
        self.assertEqual(local.revision(cut['commit'] + '^'), self.fixture.base)
        self.assertEqual(local.revision(cut['source_retention_ref']), source['commit'])
        self.assertTrue(set(source['files']) < set(cut['files']))
        for name in source['files']:
            self.assertEqual(local.git('show', source['commit'] + ':' + name),
                             local.git('show', cut['commit'] + ':' + name))
        calls, catalogue, state = self.command_calls(), self.catalogue(), self.parent_state()
        observed = self.new_parent().observe()
        self.assertEqual(observed, result)
        self.assertEqual((self.command_calls(), self.catalogue(), self.parent_state()), (calls, catalogue, state))
        self.assertTrue(self.material_authorized)
        self.assertTrue(all(request == self.request and scope == P1_MATERIAL_SCOPE
                            for request, scope in self.material_authorized))


if __name__ == '__main__':
    unittest.main()
