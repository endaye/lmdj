"""Compose canonical metadata in scratch storage; NOT a Product allocation.

Callers own authenticated assessment/main, cut selection and occupancy. An
explicit proposed number is an input, never a claim that number is available.
Only installed, control-bound generator code executes; candidate Git is data.
No caller files, refs, snapshots, releases or deployment state are written.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import types
import uuid

from . import preparation as p, records as r

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'lmdj.canary-metadata-proposal.v1'
GENERATORS = ('scripts/version.py', 'tools/web-runtime/generate_runtime_identity.py',
              'apps/docs-site/scripts/lib/host-changelogs.mjs')
PAGES = ('apps/docs-site/docs/operations/creator-changelog.mdx',
         'apps/docs-site/docs/operations/runtime-changelog.mdx')
PRODUCT = ('products/lmdj/version.json', 'products/lmdj/assembly.json',
           'products/lmdj/assembly.lock.json', 'products/lmdj/src/compiled_assembly.cpp',
           'products/lmdj/generated/web-runtime-identity.json',
           'products/lmdj/generated/web-runtime-identity.mjs')
HOST_OUTPUTS = tuple(f'apps/{host}/{name}' for host in p.a.HOSTS
                     for name in ('module.json', 'CHANGELOG.md'))
OUTPUTS = frozenset((*PRODUCT, *HOST_OUTPUTS, *PAGES))
MAX_SOURCE_BYTES = 16 * 1024 * 1024


def source_path(path):
    """Canonical generator data inventory, not an executable source inventory."""
    return (path.startswith('products/lmdj/') or path.startswith('providers/')
            or path.startswith('contracts/') and path.endswith('.schema.json')
            or path.startswith(('packages/', 'apps/')) and path.endswith('/module.json')
            or path in HOST_OUTPUTS or path in PAGES
            or path in ('tools/web-runtime/emscripten.lock.json', 'tools/web-runtime/runtime-identity.json'))


def _tree(inputs, revision):
    rows = {}
    source_bytes = 0
    for row in inputs._git('ls-tree', '-r', '-l', '-z', revision).split(b'\0'):
        if not row:
            continue
        meta, raw_path = row.split(b'\t', 1)
        path = raw_path.decode('utf-8')
        if not source_path(path):
            continue
        p.a.planning.test_scope._paths([path])
        mode, kind, oid, size = meta.decode('ascii').split()
        r.require(kind == 'blob' and mode in ('100644', '100755'),
                  'canonical generator input is not a regular Git blob')
        r.require(int(size) <= r.MAX_BYTES, 'canonical source blob exceeds scratch budget')
        source_bytes += int(size) + 2048  # Includes per-file tar framing budget.
        r.require(source_bytes <= MAX_SOURCE_BYTES, 'canonical source inventory exceeds scratch budget')
        rows[path] = (mode, oid)
    r.require(rows, 'canonical source inventory is empty')
    return rows


def _materialize(inputs, target, root):
    modes = _tree(inputs, target)
    raw = inputs._git('archive', '--format=tar', target, '--', *sorted(modes))
    r.require(len(raw) <= MAX_SOURCE_BYTES, 'canonical source inventory exceeds scratch budget')
    before = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for item in archive:
            if item.isdir():
                continue
            r.require(item.isfile() and item.name in modes and item.name not in before
                      and item.size <= r.MAX_BYTES, 'archive source differs from exact regular-file inventory')
            content = archive.extractfile(item).read()
            blob = b'blob ' + str(len(content)).encode('ascii') + b'\0' + content
            r.require(hashlib.sha1(blob).hexdigest() == modes[item.name][1],
                      'archived bytes differ from pinned Git blob',
                      'remove archive content substitution before preparing this candidate')
            destination = root / item.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            destination.chmod(0o755 if modes[item.name][0] == '100755' else 0o644)
            before[item.name] = (modes[item.name][0], content)
    r.require(set(before) == set(modes), 'canonical archive omitted required source data')
    return before


@contextmanager
def _generator(relative, raw):
    # Fresh globals avoid changing the installed version tool's REPO_ROOT or
    # sharing it across concurrent proposals. No candidate Python is imported.
    name = '_lmdj_metadata_' + uuid.uuid4().hex
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / relative)
    sys.modules[name] = module
    try:
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        yield module
    finally:
        del sys.modules[name]


def _pages(root, check):
    code = ('import {pathToFileURL} from "node:url"; '
            'const m=await import(pathToFileURL(process.argv[1])); '
            'await m.projectChangelogs(process.argv[2], {check:process.argv[3]==="check"});')
    try:
        subprocess.run(['node', '--input-type=module', '-e', code, str(ROOT / GENERATORS[2]),
                        str(root), 'check' if check else 'write'], check=True,
                       capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        raise r.CanaryError('why: canonical changelog projection did not complete; remedy: restore the trusted Node generator and complete source inputs') from None


def _build(value):
    r.require(isinstance(value, str) and len(value) <= 128 and re.fullmatch(
        r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}', value), 'proposed Product Build is not four-part identity')
    return tuple(int(part) for part in value.split('.'))


def _pinned_revision(inputs, target):
    # The canonical verifier's filesystem root is scratch data, not a checkout.
    # Preserve its Git existence check against the source's exact pinned commit,
    # never a synthetic scratch commit or the caller's mutable HEAD.
    revision = inputs._git('rev-parse', '--verify', target + '^{commit}').decode().strip()
    r.require(revision == target, 'canonical verification revision differs from pinned target')
    return revision


def prepare_metadata(repository, *, context, history, proposed_build, allocation_date):
    """Return canonical edit witnesses, with snapshot/occupancy still required.

The caller decides whether a Product proposal is needed (never for a docs-only
cut). Both Hosts may remain unchanged for a Product-only code change. This API
neither chooses that event policy nor consumes a proposed number permanently.
"""
    host_proposal = p.prepare_hosts(repository, context=context, history=history,
                                    allocation_date=allocation_date)
    inputs = p.a.planning.batch_controller.GitInputs(repository, context['control_sha'], lambda: context['target_sha'])
    proposed = _build(proposed_build)
    trusted = {}
    try:
        for relative in GENERATORS:
            pinned = p._blob(inputs, context['control_sha'], relative)
            installed = (ROOT / relative).read_bytes()
            r.require(pinned == installed, 'installed canonical generator differs from assessment control',
                      'use reviewed matching control code and recollect the assessment')
            trusted[relative] = installed
        with tempfile.TemporaryDirectory(prefix='lmdj-metadata-proposal-') as directory:
            root = Path(directory)
            before = _materialize(inputs, context['target_sha'], root)
            with _generator(GENERATORS[0], trusted[GENERATORS[0]]) as version, \
                    _generator(GENERATORS[1], trusted[GENERATORS[1]]) as runtime:
                version.REPO_ROOT = root
                version._git_revision = lambda: _pinned_revision(inputs, context['target_sha'])
                version_file, assembly_file, lock_file = (root / name for name in PRODUCT[:3])
                current = version.load_version(version_file)
                r.require(proposed[:2] == (current.milestone, current.minor)
                          and proposed[2] > current.build and proposed[3] == 0,
                          'proposal must increase BUILD on the same product line with PATCH zero')
                version.verify(version_file, assembly_file, lock_file)
                runtime.write_or_check(root, check=True)
                _pages(root, True)
                for edit in host_proposal['edits']:
                    path = root / edit['path']
                    old = before.get(edit['path'])
                    r.require((hashlib.sha256(old[1]).hexdigest() if old else None) == edit['before_sha256']
                              and (len(old[1]) if old else None) == edit['before_length'], 'Host edit preimage differs')
                    path.write_text(edit['content'], encoding='utf-8')
                product = r.decode(version_file.read_bytes())
                product.update(dict(zip(('milestone', 'minor', 'build', 'patch'), proposed)))
                version_file.write_text(json.dumps(product, indent=2) + '\n')
                assembly = r.decode(assembly_file.read_bytes())
                assembly['product']['version'] = proposed_build
                hosts = {host['id']: host['version'] for host in host_proposal['hosts']}
                for host in assembly['hosts']:
                    if host['id'] in hosts:
                        host['version'] = hosts[host['id']]
                assembly_file.write_text(json.dumps(assembly, indent=2) + '\n')
                version.generate_lock(version_file, assembly_file, lock_file)
                runtime.write_or_check(root, check=False)
                _pages(root, False)
                version.verify(version_file, assembly_file, lock_file)
                runtime.write_or_check(root, check=True)
                _pages(root, True)
            edits = []
            after_paths = set()
            for path in root.rglob('*'):
                r.require(not path.is_symlink(), 'canonical generator produced a symlink')
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                after_paths.add(relative)
                content = path.read_bytes()
                mode = '100755' if path.stat().st_mode & 0o111 else '100644'
                old = before.get(relative)
                if old == (mode, content):
                    continue
                r.require(relative in OUTPUTS and len(content) <= r.MAX_BYTES,
                          'canonical generator changed an undeclared or oversized output')
                edits.append({'path': relative, 'before_mode': old[0] if old else None, 'after_mode': mode,
                              'before_sha256': hashlib.sha256(old[1]).hexdigest() if old else None,
                              'before_length': len(old[1]) if old else None,
                              'after_sha256': hashlib.sha256(content).hexdigest(),
                              'after_length': len(content), 'content': content.decode('utf-8')})
            r.require(set(before) <= after_paths, 'canonical generator deleted a source input')
        result = r.seal({'schema': SCHEMA, 'admission_evidence': False, 'state': 'metadata-proposed',
                        'target_sha': context['target_sha'], 'control_sha': context['control_sha'],
                        'input_digest': context['digest'], 'host_proposal_digest': host_proposal['digest'],
                        'proposed_build': proposed_build, 'allocation_date': allocation_date,
                        'hosts': deepcopy(host_proposal['hosts']),
                        'generator_digests': {name: hashlib.sha256(raw).hexdigest() for name, raw in trusted.items()},
                        'edits': sorted(edits, key=lambda edit: edit['path']),
                        'remaining_obligations': ['authenticated-assessment-and-main', 'allocation-needed',
                            'five-axis-occupancy-and-fenced-three-attempt-cut', 'immutable-portal-snapshot',
                            'reviewed-version-pr', 'post-squash-coverage-and-witness',
                            'exact-candidate-test-and-artifact-acceptance']})
        r.require(len(r.canonical(result)) <= r.MAX_BYTES, 'complete metadata proposal exceeds record budget')
        return result
    except r.CanaryError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, tarfile.TarError,
            subprocess.SubprocessError, p.a.planning.incremental_batch.BatchError):
        raise r.CanaryError('why: canonical metadata generation or verification failed; remedy: restore complete pinned data and matching trusted generators; no proposal is admitted') from None
