import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtemp, mkdir, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';

import {checkSnapshotProjection, checkRevisionProjection} from '../scripts/check-snapshot-projection.mjs';
import {projectionManifest} from '../scripts/lib/snapshot-provenance.mjs';

const METADATA = 'apps/architecture-portal/versioned_metadata/version-1.0.31.0.json';

function projection(files) {
  return {sha256: files.map((file) => file.sha256).join('-'), files};
}

const RECORDED = projection([
  {path: 'apps/architecture-portal/docs/hosts/native-host.mdx', bytes: 3, sha256: 'aaa'},
  {path: 'products/lmdj/assembly.json', bytes: 5, sha256: 'bbb'},
]);

function readMetadata(metadata) {
  return async () => metadata;
}

test('a change that introduces no snapshot metadata is not this gate\'s subject', async () => {
  const errors = await checkSnapshotProjection({
    addedFiles: ['scripts/core.sh', 'apps/architecture-portal/docs/hosts/native-host.mdx'],
    readMetadata: async () => assert.fail('no metadata should be read'),
    readProjection: async () => assert.fail('no projection should be computed'),
  });
  assert.deepEqual(errors, []);
});

test('a snapshot whose projection matches the merge target passes', async () => {
  const errors = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: readMetadata({source_projection: RECORDED}),
    readProjection: async (paths) => {
      assert.deepEqual(paths, RECORDED.files.map((file) => file.path));
      return RECORDED;
    },
  });
  assert.deepEqual(errors, []);
});

test('a projected file changed after the snapshot was taken fails with its remedy', async () => {
  // The #282 shape: the snapshot is taken mid-branch, then the branch keeps
  // moving. On main the squash is the introducing commit, so the recorded
  // projection is compared against exactly this tree and no longer matches.
  const moved = projection([
    {...RECORDED.files[0], sha256: 'ccc'},
    RECORDED.files[1],
  ]);
  const errors = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: readMetadata({source_projection: RECORDED}),
    readProjection: async () => moved,
  });
  assert.equal(errors.length, 1);
  assert.match(errors[0], /does not match this change's own tree/);
  assert.match(errors[0], /scripts\/architecture-portal\.sh version 1\.0\.31\.0/);
});

test('a projected path renamed out of the tree fails with its remedy', async () => {
  const errors = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: readMetadata({source_projection: RECORDED}),
    readProjection: async () => {
      throw new Error('path does not exist in revision');
    },
  });
  assert.equal(errors.length, 1);
  assert.match(errors[0], /absent from this change's own tree/);
  assert.match(errors[0], /scripts\/architecture-portal\.sh version 1\.0\.31\.0/);
});

test('metadata without a usable projection fails closed instead of passing empty', async () => {
  for (const metadata of [{}, {source_projection: {}}, {source_projection: {files: [{}]}}]) {
    const errors = await checkSnapshotProjection({
      addedFiles: [METADATA],
      readMetadata: readMetadata(metadata),
      readProjection: async () => assert.fail('no projection should be computed'),
    });
    assert.equal(errors.length, 1);
    assert.match(errors[0], /carries no source projection/);
  }
});

test('an unreadable snapshot is reported, and a removed one is not this gate\'s subject', async () => {
  const unreadable = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: async () => {
      throw new Error('unexpected end of JSON input');
    },
    readProjection: async () => assert.fail('no projection should be computed'),
  });
  assert.equal(unreadable.length, 1);
  assert.match(unreadable[0], /cannot be read from the merge target/);

  const removed = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: async () => null,
    readProjection: async () => assert.fail('no projection should be computed'),
  });
  assert.deepEqual(removed, []);
});

test('every changed snapshot is reported once, in path order', async () => {
  const second = 'apps/architecture-portal/versioned_metadata/version-1.0.30.0.json';
  const errors = await checkSnapshotProjection({
    addedFiles: [METADATA, second, METADATA],
    readMetadata: readMetadata({source_projection: RECORDED}),
    readProjection: async () => projection([]),
  });
  assert.equal(errors.length, 2);
  assert.match(errors[0], /version-1\.0\.30\.0\.json/);
  assert.match(errors[1], /version-1\.0\.31\.0\.json/);
});

async function history(t) {
  const root = await mkdtemp(path.join(tmpdir(), 'portal-projection-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  const git = (...args) => execFileSync('git', args, {cwd: root, encoding: 'utf8'}).trim();
  git('init', '-q');
  git('config', 'user.email', 'fixture@example.test');
  git('config', 'user.name', 'fixture');
  const write = async (file, text) => {
    await mkdir(path.dirname(path.join(root, file)), {recursive: true});
    await writeFile(path.join(root, file), text);
  };
  const commit = (message) => { git('add', '.'); git('commit', '-qm', message); return git('rev-parse', 'HEAD'); };
  await write('source.txt', 'initial');
  const base = commit('base');
  const snapshot = async (version, bad = false) => {
    const recorded = await projectionManifest(root, git('rev-parse', 'HEAD'), ['source.txt']);
    if (bad) recorded.sha256 = '0'.repeat(64);
    await write(`apps/architecture-portal/versioned_metadata/version-${version}.json`, JSON.stringify({source_projection: recorded}));
    return commit('snapshot ' + version);
  };
  const check = (headSha = git('rev-parse', 'HEAD'), extra = {}) => {
    git('update-ref', 'refs/remotes/origin/main', headSha);
    return checkRevisionProjection({repoRoot: root, mode: 'main-interval', baseSha: base, headSha, ...extra});
  };
  return {root, git, write, commit, base, snapshot, check};
}

test('main interval checks both introducing trees before later mutable edits', async (t) => {
  const h = await history(t);
  await h.snapshot('1.0.1.0');
  await h.write('source.txt', 'second'); h.commit('mutable change');
  await h.snapshot('1.0.2.0');
  await h.write('source.txt', 'third'); h.commit('later mutable change');
  assert.deepEqual((await h.check()).errors, []);
  assert.equal((await h.check()).checked, 2);
});

test('a bad introducing projection cannot be washed away by a later repair', async (t) => {
  const h = await history(t);
  await h.snapshot('1.0.1.0', true);
  await h.snapshot('1.0.1.0');
  const result = await h.check();
  assert.equal(result.checked, 1);
  assert.equal(result.errors.length, 1);
  assert.match(result.errors[0], /projection does not match/);
});

test('deleting an introduced snapshot does not hide its bad introduction', async (t) => {
  const h = await history(t);
  await h.snapshot('1.0.1.0', true);
  h.git('rm', METADATA.replace('1.0.31.0', '1.0.1.0')); h.commit('delete');
  assert.equal((await h.check()).errors.length, 1);
});

test('default PR mode still rejects a mid-branch snapshot followed by mutable edits', async (t) => {
  const h = await history(t);
  await h.snapshot('1.0.1.0');
  await h.write('source.txt', 'later'); h.commit('change after freeze');
  const result = await h.check(undefined, {mode: undefined});
  assert.equal(result.errors.length, 1);
  assert.match(result.errors[0], /this change's own tree/);
});

test('explicit empty main candidate interval is not a fabricated previous-commit delta', async (t) => {
  const h = await history(t);
  const head = await h.snapshot('1.0.1.0', true);
  const result = await h.check(head, {baseSha: head});
  assert.deepEqual(result, {errors: [], checked: 0});
  // The workflow must still run complete Portal/current-Build provenance;
  // this interval-only result never claims candidate validation.
});

test('unknown mode and malformed or unavailable exact references reject', async (t) => {
  const h = await history(t);
  for (const extra of [{mode: 'skip'}, {headSha: 'HEAD'}, {baseSha: ''}, {headSha: 'f'.repeat(40)}]) {
    await assert.rejects(() => h.check(undefined, extra), /why:.*remedy:/);
  }
});

test('main interval rejects a side-branch base and a head outside main first-parent history', async (t) => {
  const h = await history(t);
  await h.write('source.txt', 'side'); const side = h.commit('side');
  h.git('checkout', '-q', '--detach', h.base);
  await h.write('source.txt', 'main'); const main = h.commit('main');
  await assert.rejects(() => h.check(main, {baseSha: side}), /why:.*remedy:/);
  h.git('update-ref', 'refs/remotes/origin/main', main);
  await assert.rejects(() => checkRevisionProjection({repoRoot: h.root, mode: 'main-interval', baseSha: h.base, headSha: side}), /why:.*remedy:/);
});

test('shallow history fails closed even for an empty interval', async (t) => {
  const h = await history(t);
  const clone = await mkdtemp(path.join(tmpdir(), 'portal-shallow-'));
  t.after(() => rm(clone, {recursive: true, force: true}));
  h.git('clone', '-q', '--depth=1', 'file://' + h.root, clone);
  await assert.rejects(() => checkRevisionProjection({repoRoot: clone, mode: 'main-interval', baseSha: h.base, headSha: h.base}), /why:.*remedy:/);
});

test('an introduced metadata object missing from local Git cannot silently skip validation', async (t) => {
  const h = await history(t);
  const head = await h.snapshot('1.0.1.0');
  const blob = h.git('rev-parse', `${head}:apps/architecture-portal/versioned_metadata/version-1.0.1.0.json`);
  // This disposable repository has loose objects and no alternates/promisor.
  // Remove only the exact fixture blob, not its commit/tree or any real data.
  await rm(path.join(h.root, '.git', 'objects', blob.slice(0, 2), blob.slice(2)));
  const result = await h.check(head);
  assert.equal(result.checked, 1);
  assert.equal(result.errors.length, 1);
  assert.match(result.errors[0], /why:.*metadata.*unavailable.*remedy:/);
});
