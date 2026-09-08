#!/usr/bin/env python3
"""Private local operation journal; not a deployment evidence Contract.

All callers on an operator host must select the same root. This file lock does
not serialize other machines or dashboard operators. An unfinished journal is
never automatically cleared: a separate reconciliation procedure must establish
remote receipts before another operation can begin.
"""
import fcntl
import json
import os
from pathlib import Path
import stat
import uuid

from cloudflare_api import TARGETS

MAX_RECORD = 65536
MAX_JOURNAL = 16 * 1024 * 1024
TERMINAL = frozenset({'passed', 'recovered', 'disabled-first-publication',
                      'failed-before-publication'})


class StoreError(RuntimeError):
    def __init__(self, why):
        super().__init__(f'why: {why}; remedy: preserve the journal and reconcile this target before retrying')


class RunStore:
    def __init__(self, root: Path, worker: str):
        if worker not in TARGETS.values():
            raise StoreError('unconfigured Worker')
        self.root = Path(root)
        self.worker = worker
        self._lock = None
        self._journal = None
        self._active = None
        self._rows = []
        self._poisoned = False

    @staticmethod
    def _open(path):
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            os.close(fd)
            raise StoreError('journal or lock is not a private regular file')
        return fd

    def __enter__(self):
        try:
            self.root.mkdir(mode=0o700, exist_ok=True)
            info = self.root.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
                raise StoreError('journal root is not a private directory')
            self._lock = self._open(self.root / f'{self.worker}.lock')
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._journal = self._open(self.root / f'{self.worker}.jsonl')
            # Persist both the files and the root directory entry before an
            # intent. Sync the parent even if another target just created root.
            for path in (self.root, self.root.parent):
                directory = os.open(path, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            size = os.fstat(self._journal).st_size
            if size > MAX_JOURNAL:
                raise StoreError('journal exceeds its bounded size')
            chunks = []
            total = 0
            while True:
                chunk = os.read(self._journal, min(65536, MAX_JOURNAL + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_JOURNAL:
                    raise StoreError('journal exceeds its bounded size')
            raw = b''.join(chunks)
            if raw and not raw.endswith(b'\n'):
                raise StoreError('journal has an incomplete final record')
            self._rows = []
            current = None
            for line in raw.splitlines():
                if len(line) > MAX_RECORD:
                    raise StoreError('journal record exceeds its bounded size')
                row = json.loads(line)
                if (not isinstance(row, dict) or set(row) != {'sequence', 'run_id', 'worker', 'data'}
                        or type(row['sequence']) is not int or row['sequence'] != len(self._rows) + 1
                        or row['worker'] != self.worker or not isinstance(row['data'], dict)
                        or not isinstance(row['data'].get('event'), str)
                        or row['data'].get('worker', self.worker) != self.worker):
                    raise StoreError('journal record identity is invalid')
                if not isinstance(row['run_id'], str) or str(uuid.UUID(row['run_id'])) != row['run_id']:
                    raise StoreError('journal run identity is invalid')
                event = row['data']['event']
                if event == 'run-started':
                    if current is not None:
                        raise StoreError('journal starts a run before completing the prior run')
                    current = row['run_id']
                elif current != row['run_id']:
                    raise StoreError('journal event has no matching active run')
                if event == 'run-finished':
                    if (not self._rows or self._rows[-1]['data']['event'] not in TERMINAL
                            or row['data'].get('outcome') != self._rows[-1]['data']['event']):
                        raise StoreError('journal completion lacks a terminal observation')
                    current = None
                self._rows.append(row)
            # Do not adopt an unfinished operation as this process's operation.
            return self
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.__exit__(None, None, None)
            raise StoreError('journal unavailable, locked, or malformed') from None
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        for name in ('_journal', '_lock'):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)
        self._active = None

    def records(self):
        return json.loads(json.dumps(self._rows))

    def _append(self, data):
        if self._journal is None or self._active is None or self._poisoned:
            raise StoreError('no usable active journal')
        row = {'sequence': len(self._rows) + 1, 'run_id': self._active,
               'worker': self.worker, 'data': data}
        try:
            raw = (json.dumps(row, allow_nan=False, separators=(',', ':')) + '\n').encode()
        except (ValueError, TypeError):
            # Like capacity rejection, this precedes all I/O. The pending run
            # remains intact; only uncertain durability poisons the descriptor.
            raise StoreError('observation is not finite JSON data') from None
        if len(raw) > MAX_RECORD or os.fstat(self._journal).st_size + len(raw) > MAX_JOURNAL:
            raise StoreError('journal capacity exhausted')
        try:
            os.lseek(self._journal, 0, os.SEEK_END)
            view = memoryview(raw)
            while view:
                written = os.write(self._journal, view)
                if written <= 0:
                    raise OSError('short journal write')
                view = view[written:]
            os.fsync(self._journal)
        except OSError:
            self._poisoned = True
            raise StoreError('journal durability failed') from None
        self._rows.append(json.loads(raw))

    def start(self, operation):
        if self._active is not None or (self._rows and self._rows[-1]['data']['event'] != 'run-finished'):
            raise StoreError('prior operation is unfinished or uncertain')
        if operation not in {'candidate', 'promote', 'recover'}:
            raise StoreError('unsupported operation')
        self._active = str(uuid.uuid4())
        self._append({'event': 'run-started', 'operation': operation})
        return self._active

    def observe(self, data):
        if (not isinstance(data, dict) or not isinstance(data.get('event'), str)
                or data['event'].startswith('run-')
                or data.get('worker', self.worker) != self.worker):
            raise StoreError('observation identity is invalid')
        self._append(data)

    def finish(self):
        if not self._rows or self._rows[-1]['data']['event'] not in TERMINAL:
            raise StoreError('operation has no confirmed terminal observation')
        self._append({'event': 'run-finished', 'outcome': self._rows[-1]['data']['event']})
        self._active = None
