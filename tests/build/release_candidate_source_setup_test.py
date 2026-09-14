#!/usr/bin/env python3
"""Actual Git/catalogue/child executor; install script is a declared fixture."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_candidate_material_test as fixture
from tools.release.candidate import CATALOG
from tools.release.candidate_source_setup import CandidateSourceSetup, CandidateSourceSetupError
from tools.release.candidate_workspace import CandidateSourceWorkspace
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import JournalError, RequestJournal


class SetupFixture(unittest.TestCase):
    install_exit = ''
    install_wait = ''

    @classmethod
    def setUpClass(cls):
        fixture.MaterialTest.setUpClass()
        cls.addClassCleanup(fixture.MaterialTest.doClassCleanups)

    def setUp(self):
        self.fixture = fixture.MaterialTest()
        self.addCleanup(self.fixture.doCleanups)
        original = fixture.MaterialTest.commit
        def seed(material):
            (material.root / 'scripts').mkdir(exist_ok=True)
            (material.root / 'scripts/docs-site.sh').write_text(
                'set -eu\ntest "$1" = install\nprintf "install\\n" >> .fixture-install-calls\n' + self.install_wait +
                'printf "actual fixture install output\\n"\n' + self.install_exit)
            (material.root / '.gitignore').write_text('.fixture-*\n')
            return original(material)
        with patch.object(fixture.MaterialTest, 'commit', seed):
            self.fixture.setUp()
        self.request = deepcopy(self.fixture.request)
        self.request['control_revision'] = self.fixture.base
        self.main = self.fixture.base
        self.destination = self.fixture.container / 'candidate-source'
        self.journal = self.fixture.container / 'setup'
        self.local = CandidateSourceWorkspace(self.destination, self.fixture.tool)
        self.authorized = []
        self.setup = self.new_setup()

    def new_setup(self, **changes):
        args = dict(repository_root=self.fixture.root, request=self.request,
            authorize=self.authorized.append, observe_main=lambda: self.main, path=os.environ['PATH'])
        args.update(changes)
        return CandidateSourceSetup(self.journal, self.local, **args)

    def enroll(self):
        return self.setup.observe(initialize=True)

    def prepare(self):
        return self.setup.prepare(before_write=lambda: None)

    def state(self):
        return json.loads((self.journal / self.setup.STATE).read_bytes())

    def calls(self):
        name = self.destination / '.fixture-install-calls'
        return name.read_text().splitlines() if name.exists() else []

    def catalogue(self):
        return (self.fixture.state / CATALOG).read_bytes()


class ReservationReaderTest(SetupFixture):
    def test_absence_does_not_allocate_or_change_catalogue(self):
        before = self.catalogue()
        self.assertIsNone(self.fixture.tool.reservations.observe(self.request, self.fixture.frozen, self.main))
        self.assertEqual(self.catalogue(), before)

    def test_actual_reservation_is_read_without_generation_or_mutation(self):
        expected = self.fixture.tool.reservations.reserve(self.request, self.fixture.frozen, self.main)
        before = self.catalogue()
        self.assertEqual(self.fixture.tool.reservations.observe(self.request, self.fixture.frozen, self.main), expected)
        self.assertEqual(self.catalogue(), before)

    def test_missing_catalogue_is_not_recreated(self):
        (self.fixture.state / CATALOG).unlink()
        with self.assertRaisesRegex(fixture.JournalError, 'catalogue is missing'):
            self.fixture.tool.reservations.observe(self.request, self.fixture.frozen, self.main)
        self.assertFalse((self.fixture.state / CATALOG).exists())


class SetupLifecycleTest(SetupFixture):
    def test_passive_absence_creates_no_worktree_or_reservation(self):
        before = self.catalogue(), self.fixture.git('show-ref')
        self.assertEqual(self.setup.observe(), dict(status='absent', evidence=None))
        self.assertEqual((self.catalogue(), self.fixture.git('show-ref')), before)
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.journal / self.setup.MARKER).exists())

    def test_prepare_cannot_enroll_after_parent_intent(self):
        with self.assertRaisesRegex(CandidateSourceSetupError, 'enrolled before parent intent'):
            self.prepare()
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.journal / self.setup.MARKER).exists())

    def test_owned_install_and_cold_receipt_feed_actual_source_producer(self):
        self.assertEqual(self.enroll()['status'], 'pending')
        result = self.prepare()
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['frozen'], self.fixture.frozen)
        self.assertEqual(self.local.revision('HEAD'), self.fixture.base)
        self.assertEqual(self.calls(), ['install'])
        row = self.state()['install']
        raw = b'actual fixture install output\n'
        self.assertEqual(row, dict(arguments=['bash','scripts/docs-site.sh','install'], status='verified',
                                  result=[0,sha256(raw).hexdigest(),len(raw)]))
        before = (self.journal / self.setup.STATE).read_bytes(), self.catalogue()
        self.setup = self.new_setup()
        self.assertEqual(self.setup.observe(), result)
        self.assertEqual(self.prepare(), result)
        self.assertEqual(((self.journal / self.setup.STATE).read_bytes(), self.catalogue()), before)
        self.assertEqual(self.calls(), ['install'])
        verified = []
        def verify_source(root):
            current = fixture.version.load_version(root / 'products/lmdj/version.json')
            assembly_path = root / 'products/lmdj/assembly.json'
            assembly = fixture.version._verify_assembly(current, assembly_path)
            fixture.version._verify_lock(current, assembly_path, assembly,
                root / 'products/lmdj/assembly.lock.json', repo_root=root)
            verified.append(str(current))
        source = self.local.prepare_source(request=self.request, frozen=result['frozen'], main_revision=self.main,
            author_name='Fixture', author_email='fixture@example.invalid', timestamp=2100000000, verify=verify_source)
        self.assertTrue(verified)
        self.assertEqual(source['product_build'], result['reservation']['version'])
        self.assertEqual(self.local.revision('HEAD'), source['commit'])
        self.assertEqual(self.setup.observe(), result)  # Historical install, not new source proof.
        self.assertEqual(self.calls(), ['install'])

    def test_actual_death_after_reservation_recovers_without_allocating_again(self):
        self.enroll()
        child = os.fork()
        if child == 0:
            original = self.fixture.tool.reservations.reserve
            def reserve(*args):
                original(*args)
                os._exit(41)
            self.fixture.tool.reservations.reserve = reserve
            self.prepare()
            os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 41)
        before = self.catalogue()
        self.setup = self.new_setup()
        self.assertEqual(self.setup.observe()['status'], 'pending')
        self.assertEqual(self.prepare()['status'], 'verified')
        self.assertEqual(self.catalogue(), before)
        self.assertEqual(self.calls(), ['install'])

    def test_actual_death_after_checkout_recovers_original_registration(self):
        self.enroll()
        child = os.fork()
        if child == 0:
            original = self.setup.repository.git
            def git(*args, **kwargs):
                value = original(*args, **kwargs)
                if 'worktree' in args and 'add' in args:
                    os._exit(42)
                return value
            self.setup.repository.git = git
            self.prepare()
            os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 42)
        registration = self.fixture.git('worktree', 'list', '--porcelain')
        self.setup = self.new_setup()
        self.assertEqual(self.prepare()['status'], 'verified')
        self.assertEqual(self.fixture.git('worktree', 'list', '--porcelain'), registration)
        self.assertEqual(self.calls(), ['install'])

    def test_actual_death_after_install_never_replays_unknown_command(self):
        self.enroll()
        child = os.fork()
        if child == 0:
            original = self.setup.executor._execute
            def execute(*args, **kwargs):
                original(*args, **kwargs)
                os._exit(43)
            self.setup.executor._execute = execute
            self.prepare()
            os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 43)
        self.assertEqual(self.calls(), ['install'])
        self.assertEqual(self.state()['install']['status'], 'started')
        self.setup = self.new_setup()
        self.assertEqual(self.setup.observe()['status'], 'unknown')
        self.assertEqual(self.prepare()['status'], 'unknown')
        self.assertEqual(self.calls(), ['install'])


class SetupBoundaryTest(SetupFixture):
    def test_late_build_raise_then_revert_stops_before_checkout(self):
        self.enroll()
        changed = []
        def advance(_):
            if self.state()['reservation'] is not None and not changed:
                before = self.catalogue()
                version_file = self.fixture.root / 'products/lmdj/version.json'
                original = version_file.read_bytes()
                version = json.loads(original)
                version['build'] += 2
                version_file.write_bytes(canonical_json(version))
                self.fixture.git('add', 'products/lmdj/version.json')
                self.fixture.git('commit', '-m', 'raise allocated build history')
                version_file.write_bytes(original)
                self.fixture.git('add', 'products/lmdj/version.json')
                self.fixture.git('commit', '-m', 'restore original version bytes')
                self.main = self.fixture.git('rev-parse', 'HEAD')
                changed.append(before)
        self.setup.authorize = advance
        with self.assertRaises(CandidateSourceSetupError):
            self.prepare()
        self.assertEqual(len(changed), 1)
        self.assertEqual(self.catalogue(), changed[0])
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.calls(), [])

    def test_catalogue_loss_after_install_blocks_cached_success(self):
        self.enroll()
        self.prepare()
        before = (self.journal / self.setup.STATE).read_bytes()
        def remove(_):
            (self.fixture.state / CATALOG).unlink()
        self.setup.authorize = remove
        with self.assertRaises(CandidateSourceSetupError):
            self.setup.observe()
        self.assertEqual((self.journal / self.setup.STATE).read_bytes(), before)
        self.assertEqual(self.calls(), ['install'])

    def test_numeric_type_change_cannot_rebind_original_scope(self):
        self.enroll()
        state = self.state()
        state['scope']['request']['actor_id'] = float(self.request['actor_id'])
        raw = canonical_json(state)
        (self.journal / self.setup.STATE).write_bytes(raw)
        with self.assertRaisesRegex(CandidateSourceSetupError, 'rebound'):
            self.setup.observe()
        self.assertEqual((self.journal / self.setup.STATE).read_bytes(), raw)
        self.assertFalse(self.destination.exists())

    def test_catalogue_loss_at_creation_guard_stops_before_checkout(self):
        self.enroll()
        removed = []
        def remove(_):
            if self.state()['reservation'] is not None and not removed:
                (self.fixture.state / CATALOG).unlink()
                removed.append(True)
        self.setup.authorize = remove
        with self.assertRaises(CandidateSourceSetupError):
            self.prepare()
        self.assertEqual(removed, [True])
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.fixture.state / CATALOG).exists())

    def test_actual_death_before_checkout_does_not_replay_create_intent(self):
        self.enroll()
        child = os.fork()
        if child == 0:
            original = self.setup.repository.git
            def git(*args, **kwargs):
                if 'worktree' in args and 'add' in args:
                    os._exit(44)
                return original(*args, **kwargs)
            self.setup.repository.git = git
            self.prepare()
            os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 44)
        self.assertTrue(self.state()['create_intent'])
        self.setup = self.new_setup()
        self.assertEqual(self.setup.observe()['status'], 'unknown')
        self.assertEqual(self.prepare()['status'], 'unknown')
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.calls(), [])

    def test_unowned_path_is_not_overwritten_or_adopted(self):
        self.destination.mkdir()
        retained = self.destination / 'keep'
        retained.write_bytes(b'owner data')
        with self.assertRaisesRegex(CandidateSourceSetupError, 'already exists'):
            self.enroll()
        self.assertEqual(retained.read_bytes(), b'owner data')
        self.assertFalse((self.journal / self.setup.MARKER).exists())

    def test_lost_enrolled_history_is_not_recreated(self):
        self.enroll()
        (self.journal / self.setup.STATE).unlink()
        with self.assertRaisesRegex(CandidateSourceSetupError, 'history is missing'):
            self.enroll()
        self.assertFalse((self.journal / self.setup.STATE).exists())
        self.assertFalse(self.destination.exists())

    def test_late_callback_cannot_delete_then_recreate_history(self):
        self.enroll()
        def erase(_):
            (self.journal / self.setup.STATE).unlink()
        self.setup.authorize = erase
        with self.assertRaises(CandidateSourceSetupError):
            self.prepare()
        self.assertFalse((self.journal / self.setup.STATE).exists())
        self.assertFalse(self.destination.exists())

    def test_authority_exception_has_no_secret_traceback(self):
        def fail(_):
            raise RuntimeError('PRIVATE-AUTHORITY-DETAIL')
        self.setup.authorize = fail
        try:
            self.enroll()
        except CandidateSourceSetupError:
            rendered = traceback.format_exc()
        else:
            self.fail('authority failure must refuse')
        self.assertNotIn('PRIVATE-AUTHORITY-DETAIL', rendered)
        self.assertFalse(self.destination.exists())

    def test_same_request_id_cannot_change_scope(self):
        self.enroll()
        changed = dict(self.request, authority_ref='thread:another-grant')
        other = self.new_setup(request=changed)
        with self.assertRaisesRegex(CandidateSourceSetupError, 'rebound'):
            other.observe()
        self.assertFalse(self.destination.exists())

    def test_live_product_change_stops_before_reservation_and_checkout(self):
        self.enroll()
        before = self.catalogue()
        (self.fixture.root / 'products/lmdj/changed.txt').write_text('changed')
        self.fixture.git('add', 'products/lmdj/changed.txt')
        self.fixture.git('commit', '-m', 'product change')
        self.main = self.fixture.git('rev-parse', 'HEAD')
        with self.assertRaises(CandidateSourceSetupError):
            self.prepare()
        self.assertEqual(self.catalogue(), before)
        self.assertFalse(self.destination.exists())


class SetupInstallFailureTest(SetupFixture):
    install_exit = 'exit 23\n'

    def test_nonzero_install_preserves_result_and_never_replays(self):
        self.enroll()
        with self.assertRaisesRegex(CandidateSourceSetupError, 'installation exited 23'):
            self.prepare()
        self.assertEqual(self.calls(), ['install'])
        row = self.state()['install']
        self.assertEqual(row['status'], 'finished')
        self.assertEqual(row['result'][0], 23)
        before = (self.journal / self.setup.STATE).read_bytes()
        self.setup = self.new_setup()
        self.assertEqual(self.setup.observe()['status'], 'conflict')
        self.assertEqual(self.prepare()['status'], 'conflict')
        self.assertEqual((self.journal / self.setup.STATE).read_bytes(), before)
        self.assertEqual(self.calls(), ['install'])


class SetupOrphanTest(SetupFixture):
    install_wait = ('touch .fixture-install-started\n'
                    'while test ! -e .fixture-install-release; do sleep 0.05; done\n'
                    'touch .fixture-install-finished\n')

    def test_live_orphan_installer_retains_both_original_writers(self):
        self.enroll()
        child = os.fork()
        if child == 0:
            self.prepare()
            os._exit(99)
        reaped = False
        release = self.destination / '.fixture-install-release'
        try:
            deadline = time.monotonic() + 30
            while not (self.destination / '.fixture-install-started').exists():
                self.assertLess(time.monotonic(), deadline, 'actual installer never reached its retained-lock probe')
                time.sleep(0.05)
            gitdir = self.local.git('rev-parse', '--absolute-git-dir').decode().strip()
            os.kill(child, signal.SIGKILL)
            _, status = os.waitpid(child, 0)
            reaped = True
            self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGKILL)
            for directory in (self.journal, Path(gitdir) / self.local.JOURNAL_NAME):
                with self.assertRaisesRegex(JournalError, 'another writer'):
                    with RequestJournal(directory):
                        pass
            release.touch()
            deadline = time.monotonic() + 10
            while True:
                try:
                    with RequestJournal(self.journal), RequestJournal(Path(gitdir) / self.local.JOURNAL_NAME):
                        break
                except JournalError:
                    self.assertLess(time.monotonic(), deadline, 'released installer retained its writers')
                    time.sleep(0.05)
            self.assertTrue((self.destination / '.fixture-install-finished').is_file())
            self.setup = self.new_setup()
            self.assertEqual(self.prepare()['status'], 'unknown')
            self.assertEqual(self.calls(), ['install'])
        finally:
            if self.destination.exists():
                release.touch()
            if not reaped:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)


if __name__ == '__main__':
    unittest.main()
