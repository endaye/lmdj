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

function fixture(overrides = {}) {
  return {
    portalRoot: '/portal',
    repoRoot: '/repo',
    requestedVersion: '1.0.13.0',
    revision: 'abcdef123456',
    facts,
    getGitStatus: async () => '',
    readVersions: async () => [],
    run: async () => {},
    writeMetadata: async () => {},
    now: () => new Date('2026-08-04T00:00:00.000Z'),
    ...overrides,
  };
}

test('freeze rejects syntax mismatch, dirty worktree, and existing version', async () => {
  await assert.rejects(() => freezeVersion(fixture({requestedVersion: '1.0.13'})), /four-part Product Build/);
  await assert.rejects(() => freezeVersion(fixture({requestedVersion: '1.0.12.0'})), /does not match 1.0.13.0/);
  await assert.rejects(() => freezeVersion(fixture({channel: 'preview'})), /channel must be canary, dev, beta, or stable/);
  await assert.rejects(() => freezeVersion(fixture({getGitStatus: async () => ' M docs/page.mdx'})), /clean worktree/);
  await assert.rejects(() => freezeVersion(fixture({readVersions: async () => ['1.0.13.0']})), /already exists/);
});

test('freeze runs both gates around Docusaurus and writes exact metadata', async () => {
  const commands = [];
  let metadata;
  await freezeVersion(fixture({
    run: async (command, args) => commands.push([command, args]),
    writeMetadata: async (_version, value) => { metadata = value; },
  }));
  assert.deepEqual(commands, [
    ['npm', ['run', 'check:current']],
    ['npm', ['run', 'docusaurus', '--', 'docs:version', '1.0.13.0']],
    ['npm', ['run', 'check']],
  ]);
  assert.deepEqual(metadata, {
    ...facts,
    product_build: '1.0.13.0',
    revision: 'abcdef123456',
    frozen_at_utc: '2026-08-04T00:00:00.000Z',
  });
});

test('freeze stops before generation and metadata when current preflight fails', async () => {
  const commands = [];
  let metadataWritten = false;
  await assert.rejects(() => freezeVersion(fixture({
    run: async (command, args) => {
      commands.push([command, args]);
      throw new Error('current portal validation failed');
    },
    writeMetadata: async () => { metadataWritten = true; },
  })), /current portal validation failed/);
  assert.deepEqual(commands, [['npm', ['run', 'check:current']]]);
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
