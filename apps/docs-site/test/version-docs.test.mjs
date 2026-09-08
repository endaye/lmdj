import assert from 'node:assert/strict';
import test from 'node:test';
import * as versionDocs from '../scripts/lib/version-docs.mjs';

const {freezeVersion} = versionDocs;

const facts = {
  product: {id: 'lmdj', version: '1.0.13.0'},
  channel: 'canary',
  assembly_lock_sha256: 'lock-sha',
  modules: [], hosts: [], providers: [], contracts: [],
};
const revision = 'abcdef1234567890abcdef1234567890abcdef12';

function fixture(overrides = {}) {
  return {
    portalRoot: '/portal',
    repoRoot: '/repo',
    requestedVersion: '1.0.13.0',
    revision,
    facts,
    getGitStatus: async () => '',
    getHeadRevision: async () => revision,
    readVersions: async () => [],
    run: async () => {},
    writeMetadata: async () => {},
    freezeAssets: async () => [],
    createMetadata: async () => ({schema_version: 2, product_build: '1.0.13.0'}),
    now: () => new Date('2026-08-04T00:00:00.000Z'),
    ...overrides,
  };
}

test('freeze rejects syntax mismatch, dirty worktree, and existing version', async () => {
  await assert.rejects(() => freezeVersion(fixture({requestedVersion: '1.0.13'})), /four-part Product Build/);
  await assert.rejects(() => freezeVersion(fixture({requestedVersion: '1.0.12.0'})), /does not match 1.0.13.0/);
  await assert.rejects(() => freezeVersion(fixture({channel: 'preview'})), /channel must be canary, dev, beta, or stable/);
  await assert.rejects(() => freezeVersion(fixture({getHeadRevision: async () => '1'.repeat(40)})), /source revision must equal HEAD/);
  await assert.rejects(() => freezeVersion(fixture({getGitStatus: async () => ' M docs/page.mdx'})), /clean worktree/);
  await assert.rejects(() => freezeVersion(fixture({readVersions: async () => ['1.0.13.0']})), /already exists/);
});

test('freeze runs both gates around Docusaurus and writes exact metadata', async () => {
  const commands = [];
  const lifecycle = [];
  let metadata;
  await freezeVersion(fixture({
    run: async (command, args) => { commands.push([command, args]); lifecycle.push(args[1] ?? args[0]); },
    freezeAssets: async (options) => { lifecycle.push('freeze-assets'); assert.equal(options.version, '1.0.13.0'); },
    createMetadata: async (options) => {
      lifecycle.push('create-metadata');
      assert.equal(options.revision, revision);
      assert.deepEqual(options.facts, facts);
      return {schema_version: 2, product_build: '1.0.13.0', revision};
    },
    writeMetadata: async (_version, value) => { lifecycle.push('write-metadata'); metadata = value; },
  }));
  assert.deepEqual(commands, [
    ['npm', ['run', 'check:current']],
    ['npm', ['run', 'docusaurus', '--', 'docs:version', '1.0.13.0']],
    ['npm', ['run', 'check']],
  ]);
  assert.deepEqual(lifecycle, [
    'check:current', 'docusaurus', 'freeze-assets', 'create-metadata', 'write-metadata', 'check',
  ]);
  assert.deepEqual(metadata, {schema_version: 2, product_build: '1.0.13.0', revision});
});

test('freeze stops before generation and metadata when current preflight fails', async () => {
  const commands = [];
  let metadataWritten = false;
  let assetsFrozen = false;
  await assert.rejects(() => freezeVersion(fixture({
    run: async (command, args) => {
      commands.push([command, args]);
      throw new Error('current portal validation failed');
    },
    writeMetadata: async () => { metadataWritten = true; },
    freezeAssets: async () => { assetsFrozen = true; },
  })), /current portal validation failed/);
  assert.deepEqual(commands, [['npm', ['run', 'check:current']]]);
  assert.equal(metadataWritten, false);
  assert.equal(assetsFrozen, false);
});

test('freeze does not write metadata when versioned diagram freezing fails', async () => {
  const commands = [];
  let metadataWritten = false;
  await assert.rejects(() => freezeVersion(fixture({
    run: async (command, args) => commands.push([command, args]),
    freezeAssets: async () => { throw new Error('missing diagram asset'); },
    writeMetadata: async () => { metadataWritten = true; },
  })), /missing diagram asset/);
  assert.deepEqual(commands, [
    ['npm', ['run', 'check:current']],
    ['npm', ['run', 'docusaurus', '--', 'docs:version', '1.0.13.0']],
  ]);
  assert.equal(metadataWritten, false);
});

test('package scripts separate current preflight from release snapshot validation', async () => {
  const manifest = (await import('../package.json', {with: {type: 'json'}})).default;
  assert.equal(
    manifest.scripts['check:current'],
    'npm test && npm run validate:docs && npm run validate:diagrams && npm run facts && npm run typecheck && npm run build && npm run check:build',
  );
  assert.doesNotMatch(manifest.scripts['check:current'], /check:release-docs/);
  assert.match(manifest.scripts.check, /npm run check:release-docs/);
});

test('release documentation requires an immutable snapshot matching repository truth', () => {
  const validateReleaseSnapshot = versionDocs.validateReleaseSnapshot;
  assert.equal(typeof validateReleaseSnapshot, 'function');

  assert.deepEqual(validateReleaseSnapshot({
    facts,
    versions: [],
    metadata: null,
    snapshotExists: false,
  }), [
    'Product Build 1.0.13.0 is missing from versions.json',
    'Product Build 1.0.13.0 snapshot source is missing',
    'Product Build 1.0.13.0 metadata is missing',
  ]);

  assert.deepEqual(validateReleaseSnapshot({
    facts,
    versions: ['1.0.13.0'],
    snapshotExists: true,
    metadata: {
      ...facts,
      product_build: '1.0.13.0',
      channel: 'dev',
      revision: 'abcdef1234567890abcdef1234567890abcdef12',
      frozen_at_utc: '2026-08-04T00:00:00.000Z',
    },
  }), []);
});

test('release documentation rejects identity drift and invalid freeze evidence', () => {
  const errors = versionDocs.validateReleaseSnapshot({
    facts,
    versions: ['1.0.13.0'],
    snapshotExists: true,
    metadata: {
      ...facts,
      product_build: '1.0.12.0',
      product: {id: 'lmdj', version: '1.0.12.0'},
      assembly_lock_sha256: 'stale-lock',
      channel: 'preview',
      revision: 'short',
      frozen_at_utc: 'not-a-date',
    },
  });
  assert.deepEqual(errors, [
    'snapshot product_build does not match 1.0.13.0',
    'snapshot product identity does not match repository truth',
    'snapshot Assembly Lock does not match repository truth',
    'snapshot channel must be canary, dev, beta, or stable',
    'snapshot revision must be a full Git SHA',
    'snapshot frozen_at_utc must be an ISO timestamp',
  ]);
});
