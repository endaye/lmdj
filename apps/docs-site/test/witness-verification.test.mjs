import assert from 'node:assert/strict';
import test from 'node:test';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import {cp, mkdtemp, mkdir, readFile, realpath, rm, stat, symlink, truncate, unlink, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const exec = promisify(execFile);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const VERSION = '1.0.99.0';
const METADATA = `apps/architecture-portal/versioned_metadata/version-${VERSION}.json`;
const WITNESS = `apps/architecture-portal/versioned_provenance/version-${VERSION}-squash-witness.json`;
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const gitEnv = {PATH: process.env.PATH, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null',
  GIT_NO_REPLACE_OBJECTS: '1', GIT_NO_LAZY_FETCH: '1', GIT_ALLOW_PROTOCOL: 'file',
  GIT_OPTIONAL_LOCKS: '0', GIT_TERMINAL_PROMPT: '0', LC_ALL: 'C',
  GIT_AUTHOR_DATE: '2026-09-13T00:00:00Z', GIT_COMMITTER_DATE: '2026-09-13T00:00:00Z'};

async function git(root, ...args) {
  return (await exec('git', ['-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', ...args],
    {cwd: root, env: gitEnv, maxBuffer: 8 * 1024 * 1024})).stdout.trim();
}
async function fixture(t) {
  const root = await realpath(await mkdtemp(path.join(os.tmpdir(), 'witness-check-')));
  t.after(() => rm(root, {recursive: true, force: true}));
  for (const name of ['scripts/docs-site.sh', 'apps/docs-site/scripts/create-squash-witness.mjs',
    'apps/docs-site/scripts/verify-squash-witness.mjs', 'apps/docs-site/scripts/lib/snapshot-provenance.mjs',
    'apps/docs-site/scripts/lib/repo-facts.mjs']) {
    await mkdir(path.dirname(path.join(root, name)), {recursive: true});
    await cp(path.join(ROOT, name), path.join(root, name));
  }
  for (const name of ['versioned_metadata', 'versioned_provenance']) {
    await mkdir(path.join(root, 'apps/architecture-portal', name), {recursive: true});
    await writeFile(path.join(root, 'apps/architecture-portal', name, '.gitkeep'), '');
    await symlink(`../architecture-portal/${name}`, path.join(root, 'apps/docs-site', name));
  }
  await git(root, 'init', '--initial-branch=main');
  await git(root, 'config', 'user.name', 'Witness Fixture');
  await git(root, 'config', 'user.email', 'fixture@example.invalid');
  await writeFile(path.join(root, 'content'), 'base\n');
  await git(root, 'add', '--all');
  await git(root, 'commit', '-m', 'base');
  const base = await git(root, 'rev-parse', 'HEAD');
  await writeFile(path.join(root, 'content'), 'source\n');
  await git(root, 'commit', '-am', 'private source');
  const source = await git(root, 'rev-parse', 'HEAD');
  await git(root, 'update-ref', 'refs/lmdj/release-sources/fixture', source);
  const {stdout: rawCommit} = await exec('git', ['cat-file', 'commit', source],
    {cwd: root, env: gitEnv, encoding: 'buffer'});
  const tree = await git(root, 'rev-parse', `${source}^{tree}`);
  // The official witness producer consumes these identity/raw-commit fields.
  // This fixture is NOT a complete Portal snapshot or release acceptance.
  const metadata = {schema_version: 2, product_build: VERSION, revision: source,
    source_commit: {tree, committed_at_utc: '2026-09-13T00:00:00.000Z', raw_base64: rawCommit.toString('base64')}};
  await writeFile(path.join(root, METADATA), `${JSON.stringify(metadata, null, 2)}\n`);
  await git(root, 'add', '--all');
  const cutTree = await git(root, 'write-tree');
  const introducing = await git(root, 'commit-tree', cutTree, '-p', base, '-m', 'actual fixture squash');
  await git(root, 'update-ref', 'refs/heads/main', introducing, source);
  await exec('bash', ['scripts/docs-site.sh', 'witness', VERSION, introducing], {cwd: root, env: gitEnv});
  return {root, source, introducing, tree, raw: await readFile(path.join(root, WITNESS))};
}
async function verify(f, revision = f.introducing, extraEnv = {}) {
  return exec('bash', ['scripts/docs-site.sh', 'verify-witness', VERSION, revision],
    {cwd: f.root, env: {...gitEnv, ...extraEnv}});
}
async function rejected(f, revision) {
  await assert.rejects(verify(f, revision), error => {
    assert.equal(error.code, 1);
    assert.equal(error.stdout, '');
    assert.match(error.stderr, /why:.*remedy:/);
    return true;
  });
}

test('official witness bytes verify repeatedly without modifying Git or artifacts', async t => {
  const f = await fixture(t);
  const metadata = await readFile(path.join(f.root, METADATA));
  const before = {head: await git(f.root, 'rev-parse', 'HEAD'), refs: await git(f.root, 'show-ref'),
    index: await readFile(path.join(f.root, '.git/index')), files: await git(f.root, 'status', '--porcelain')};
  const first = JSON.parse((await verify(f)).stdout);
  assert.deepEqual(first, {schema: 'lmdj.snapshot-witness-check.v1', status: 'verified-by-retained-source',
    product_build: VERSION, source_revision: f.source, introducing_revision: f.introducing, source_tree: f.tree,
    metadata: {path: METADATA, bytes: metadata.length, sha256: digest(metadata)},
    witness: {path: WITNESS, bytes: f.raw.length, sha256: digest(f.raw)}});
  assert.deepEqual(JSON.parse((await verify(f)).stdout), first);
  assert.deepEqual(await readFile(path.join(f.root, WITNESS)), f.raw);
  assert.deepEqual(await readFile(path.join(f.root, METADATA)), metadata);
  assert.deepEqual({head: await git(f.root, 'rev-parse', 'HEAD'), refs: await git(f.root, 'show-ref'),
    index: await readFile(path.join(f.root, '.git/index')), files: await git(f.root, 'status', '--porcelain')}, before);
});

test('later same-tree commit cannot replace the explicit introduction', async t => {
  const f = await fixture(t);
  const later = await git(f.root, 'commit-tree', await git(f.root, 'rev-parse', 'HEAD^{tree}'),
    '-p', f.introducing, '-m', 'later');
  await rejected(f, later);
  assert.deepEqual(await readFile(path.join(f.root, WITNESS)), f.raw);
});

test('metadata drift refuses even when its parsed identity is unchanged', async t => {
  const f = await fixture(t);
  const filename = path.join(f.root, METADATA);
  const changed = Buffer.concat([await readFile(filename), Buffer.from('\n')]);
  await writeFile(filename, changed);
  await rejected(f);
  assert.deepEqual(await readFile(filename), changed);
});

test('missing witness is not generated by verification', async t => {
  const f = await fixture(t);
  await unlink(path.join(f.root, WITNESS));
  await rejected(f);
  await assert.rejects(readFile(path.join(f.root, WITNESS)), {code: 'ENOENT'});
});

test('corrupt witness is retained rather than repaired', async t => {
  const f = await fixture(t);
  const changed = Buffer.from('{corrupt SECRET-WITNESS}');
  await writeFile(path.join(f.root, WITNESS), changed);
  await rejected(f);
  assert.deepEqual(await readFile(path.join(f.root, WITNESS)), changed);
});

test('semantically equal witness reformatting cannot change the accepted bytes', async t => {
  const f = await fixture(t);
  const changed = Buffer.from(JSON.stringify(JSON.parse(f.raw)) + '\n');
  await writeFile(path.join(f.root, WITNESS), changed);
  await rejected(f);
  assert.deepEqual(await readFile(path.join(f.root, WITNESS)), changed);
});

test('symlink witness cannot substitute an external artifact', async t => {
  const f = await fixture(t);
  const external = path.join(f.root, 'retained-witness');
  await writeFile(external, f.raw);
  await unlink(path.join(f.root, WITNESS));
  await symlink(external, path.join(f.root, WITNESS));
  await rejected(f);
  assert.deepEqual(await readFile(external), f.raw);
});

test('oversized witness is refused without being rewritten', async t => {
  const f = await fixture(t);
  const filename = path.join(f.root, WITNESS);
  await truncate(filename, 64 * 1024 * 1024 + 1);
  const before = await stat(filename);
  await rejected(f);
  const after = await stat(filename);
  assert.equal(after.size, before.size);
  assert.equal(after.mtimeMs, before.mtimeMs);
  assert.equal(after.ctimeMs, before.ctimeMs);
});

test('fresh clone without the private source cannot claim retained-source verification', async t => {
  const f = await fixture(t);
  const clone = path.join(f.root, 'fresh-clone');
  await git(f.root, 'clone', '--no-local', '--single-branch', '--branch', 'main', f.root, clone);
  await assert.rejects(git(clone, 'cat-file', '-e', f.source));
  await writeFile(path.join(clone, WITNESS), f.raw);
  await rejected({...f, root: clone});
  await assert.rejects(git(clone, 'cat-file', '-e', f.source));
  assert.deepEqual(await readFile(path.join(clone, WITNESS)), f.raw);
});

test('inherited Git redirection cannot supply different witness proof', async t => {
  const f = await fixture(t);
  const result = await verify(f, f.introducing, {GIT_DIR: '/does-not-exist', GIT_WORK_TREE: '/does-not-exist',
    GIT_INDEX_FILE: '/does-not-exist/index', GIT_CONFIG_COUNT: '1',
    GIT_CONFIG_KEY_0: 'core.worktree', GIT_CONFIG_VALUE_0: '/SECRET-REDIRECT',
    GIT_EXTERNAL_DIFF: '/SECRET-EXECUTABLE'});
  assert.equal(JSON.parse(result.stdout).source_revision, f.source);
  assert.equal(result.stderr, '');
});

test('wrapper requires an explicit full introducing revision', async () => {
  for (const args of [[VERSION], [VERSION, 'abcd'], [VERSION, '0'.repeat(40)],
    [VERSION, 'a'.repeat(40), 'extra'], [VERSION + '\n', 'a'.repeat(40)], [VERSION, 'a'.repeat(40) + '\n']]) {
    await assert.rejects(exec('bash', ['scripts/docs-site.sh', 'verify-witness', ...args],
      {cwd: ROOT, env: gitEnv}), error => {
      assert.equal(error.code, 64);
      assert.match(error.stderr, /usage:/);
      assert.equal(error.stdout, '');
      return true;
    });
  }
});
