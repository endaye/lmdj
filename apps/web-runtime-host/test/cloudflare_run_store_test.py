#!/usr/bin/env python3
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from cloudflare_run_store import RunStore, StoreError
from cloudflare_transaction import promote, TransactionError
from cloudflare_transaction_test import FakeClient, B


class RunStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.worker = 'creator-recovery'
        self.file = self.root / f'{self.worker}.jsonl'

    def store(self):
        return RunStore(self.root, self.worker)

    def test_parent_directory_sync_failure_prevents_accepting_an_intent(self):
        root = self.root / 'new-store'
        parent = self.root.stat()
        real = os.fsync
        def fail_parent(fd):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) == (parent.st_dev, parent.st_ino):
                raise OSError('parent directory sync failed')
            return real(fd)
        with patch('cloudflare_run_store.os.fsync', side_effect=fail_parent):
            with self.assertRaises(StoreError):
                with RunStore(root, self.worker) as s:s.start('promote')
        self.assertEqual((root / f'{self.worker}.jsonl').read_bytes(), b'')
        with RunStore(root, self.worker) as s:s.start('promote')

    def test_completed_transaction_survives_reopen_and_allows_new_run(self):
        with self.store() as s:
            first = s.start('promote')
            promote(FakeClient(), candidate=B, verify=lambda *_: True, observe=s.observe)
            s.finish()
        with self.store() as s:
            self.assertEqual(s.records()[-1]['data'], {'event': 'run-finished', 'outcome': 'passed'})
            self.assertNotEqual(s.start('promote'), first)

    def test_unknown_publication_survives_reopen_and_cannot_restart(self):
        c = FakeClient(); c.unknown = True
        with self.store() as s:
            s.start('promote')
            with self.assertRaises(TransactionError):
                promote(c, candidate=B, verify=lambda *_: True, observe=s.observe)
            with self.assertRaises(StoreError): s.finish()
        with self.store() as s:
            self.assertEqual(s.records()[-1]['data']['event'], 'reconciliation-required')
            with self.assertRaises(StoreError): s.start('promote')
        self.assertEqual(c.writes, [('publish', B)])

    def test_process_exit_releases_lock_but_retains_unfinished_intent(self):
        code = "from cloudflare_run_store import RunStore; import os; from pathlib import Path\nwith RunStore(Path(__import__('sys').argv[1]),'creator-recovery') as s:\n s.start('promote')\n s.observe({'event':'publication-starting'})\n os._exit(0)"
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'tools'))
        subprocess.run([sys.executable, '-c', code, str(self.root)], env=env, check=True)
        with self.store() as s:
            with self.assertRaises(StoreError): s.start('promote')
            self.assertEqual(s.records()[-1]['data']['event'], 'publication-starting')

    def test_separate_process_cannot_take_same_target_lock(self):
        code = "from cloudflare_run_store import RunStore,StoreError; from pathlib import Path; import sys\ntry:\n with RunStore(Path(sys.argv[1]),'creator-recovery'): pass\nexcept StoreError: sys.exit(23)"
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'tools'))
        with self.store():
            result = subprocess.run([sys.executable, '-c', code, str(self.root)], env=env)
        self.assertEqual(result.returncode, 23)
        with self.store(): pass

    def test_incomplete_record_is_preserved_and_rejected(self):
        self.file.write_bytes(b'{"sequence":1'); self.file.chmod(0o600)
        with self.assertRaises(StoreError):
            with self.store(): pass
        self.assertEqual(self.file.read_bytes(), b'{"sequence":1')

    def test_wrong_target_or_sequence_in_retained_record_is_rejected(self):
        with self.store() as s:s.start('candidate')
        original = json.loads(self.file.read_text())
        for field, value in [('worker', 'lab-recovery'), ('sequence', 2), ('run_id', 'not-a-uuid'), ('run_id', None), ('run_id', 42)]:
            row = dict(original); row[field] = value
            self.file.write_text(json.dumps(row) + '\n')
            with self.assertRaises(StoreError):
                with self.store(): pass

    def test_retained_observation_cannot_name_another_worker(self):
        with self.store() as s:
            s.start('promote')
            s.observe({'event':'passed','worker':self.worker})
            s.finish()
        rows = [json.loads(line) for line in self.file.read_text().splitlines()]
        rows[1]['data']['worker'] = 'lab-recovery'
        self.file.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        with self.assertRaises(StoreError):
            with self.store(): pass

    def test_completion_without_terminal_observation_is_rejected_on_read(self):
        with self.store() as s:s.start('promote')
        row = json.loads(self.file.read_text());row['sequence'] = 2
        row['data'] = {'event': 'run-finished', 'outcome': 'passed'}
        with self.file.open('a') as f:f.write(json.dumps(row) + '\n')
        with self.assertRaises(StoreError):
            with self.store(): pass

    def test_observation_fsync_failure_prevents_cloud_mutation_and_retry(self):
        c = FakeClient()
        with self.store() as s:
            s.start('promote')
            with patch('cloudflare_run_store.os.fsync', side_effect=OSError('disk error')):
                with self.assertRaises(StoreError):
                    promote(c, candidate=B, verify=lambda *_: True, observe=s.observe)
            with self.assertRaises(StoreError):s.observe({'event':'passed'})
        self.assertEqual(c.writes, [])
        with self.store() as s:
            with self.assertRaises(StoreError):s.start('promote')

    def test_partial_write_is_completed_before_durable_observation_returns(self):
        real = os.write
        with self.store() as s:
            with patch('cloudflare_run_store.os.write', side_effect=lambda fd, data: real(fd, data[:7])):
                s.start('candidate');s.observe({'event':'passed'});s.finish()
        with self.store() as s:self.assertEqual(len(s.records()), 3)

    def test_short_reads_do_not_hide_an_unfinished_tail(self):
        with self.store() as s:
            s.start('candidate');s.observe({'event':'passed'});s.finish()
            s.start('promote')
        real = os.read
        with patch('cloudflare_run_store.os.read', side_effect=lambda fd, size: real(fd, min(size, 11))):
            with self.store() as s:
                self.assertEqual(len(s.records()), 4)
                with self.assertRaises(StoreError):s.start('promote')

    def test_symlink_journal_cannot_redirect_writes(self):
        other = self.root / 'other';other.write_text('untouched')
        self.file.symlink_to(other)
        with self.assertRaises(StoreError):
            with self.store(): pass
        self.assertEqual(other.read_text(), 'untouched')

    def test_records_are_detached_and_wrong_worker_observation_is_rejected(self):
        with self.store() as s:
            s.start('candidate')
            s.records()[0]['data']['event'] = 'run-finished'
            self.assertEqual(s.records()[0]['data']['event'], 'run-started')
            with self.assertRaises(StoreError):s.observe({'event':'passed','worker':'lab-recovery'})
            with self.assertRaises(StoreError):s.observe({'event':'run-finished'})

    def test_nonfinite_observation_has_a_store_error_without_writing(self):
        with self.store() as s:
            s.start('candidate');before = self.file.read_bytes()
            for number in (float('nan'), float('inf'), -float('inf')):
                with self.assertRaises(StoreError):
                    s.observe({'event':'verified','duration':number})
                self.assertEqual(self.file.read_bytes(), before)
        with self.store() as s:
            with self.assertRaises(StoreError):s.start('candidate')

    def test_oversize_observation_is_not_written(self):
        with self.store() as s:
            s.start('candidate');before = self.file.read_bytes()
            with self.assertRaises(StoreError):s.observe({'event':'verified','payload':'x'*65536})
            self.assertEqual(self.file.read_bytes(), before)


if __name__ == '__main__':unittest.main()
