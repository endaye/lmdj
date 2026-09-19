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


if __name__ == '__main__':
    unittest.main()
