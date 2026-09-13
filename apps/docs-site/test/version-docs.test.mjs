import assert from 'node:assert/strict';
import test from 'node:test';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
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

function resumeFixture(overrides = {}) {
  const metadata = {...facts, schema_version: 2, product_build: facts.product.version,
    revision, frozen_at_utc: '2026-08-04T00:00:00.000Z'};
  return {portalRoot: '/portal', repoRoot: '/repo', requestedVersion: facts.product.version,
    revision, channel: 'canary', facts, getHeadRevision: async () => revision,
    readMetadata: async () => JSON.stringify(metadata), readVersions: async () => [facts.product.version],
    readSourceVersions: async () => [], verifyProvenance: async () => [], run: async () => {},
    ...overrides};
}

test('resume only runs the full check between two provenance validations', async () => {
  const calls = [];
  const result = await versionDocs.resumeVersion(resumeFixture({
    verifyProvenance: async () => { calls.push('verify'); return []; },
    run: async (command, args) => { calls.push([command, args]); },
  }));
  assert.deepEqual(calls, ['verify', ['npm', ['run', 'check']], 'verify']);
  assert.deepEqual(result, {status: 'snapshot-verified', product_build: facts.product.version,
    revision, channel: 'canary'});
});

test('resume refuses a different source HEAD before running checks', async () => {
  await assert.rejects(versionDocs.resumeVersion(resumeFixture({
    getHeadRevision: async () => 'b'.repeat(40), run: async () => assert.fail('must not run'),
  })), /HEAD differs/);
});

test('resume refuses an original-channel mismatch', async () => {
  await assert.rejects(versionDocs.resumeVersion(resumeFixture({channel: 'dev',
    run: async () => assert.fail('must not run'),
  })), /source SHA or channel differs/);
});

test('resume refuses legacy metadata without provenance', async () => {
  await assert.rejects(versionDocs.resumeVersion(resumeFixture({
    readMetadata: async () => JSON.stringify({schema_version: 1}),
    run: async () => assert.fail('must not run'),
  })), /schema 2/);
});

test('resume refuses changed historical versions inventory', async () => {
  await assert.rejects(versionDocs.resumeVersion(resumeFixture({
    readSourceVersions: async () => ['1.0.12.0'], run: async () => assert.fail('must not run'),
  })), /versions inventory differs/);
});

test('resume preserves failed gate and does not claim completion', async () => {
  let checks = 0;
  await assert.rejects(versionDocs.resumeVersion(resumeFixture({
    verifyProvenance: async () => { checks++; return []; },
    run: async () => { throw new Error('fixture gate failure'); },
  })), /fixture gate failure/);
  assert.equal(checks, 1);
});

test('resume refuses metadata mutation by a successful child', async () => {
  const options = resumeFixture();
  const raw = await options.readMetadata();
  let current = raw;
  await assert.rejects(versionDocs.resumeVersion({...options,
    readMetadata: async () => current, run: async () => { current += '\n'; },
  }), /metadata changed/);
  assert.equal(current, raw + '\n');
});

test('resume revalidates provenance after a successful child', async () => {
  let after = false;
  await assert.rejects(versionDocs.resumeVersion(resumeFixture({
    run: async () => { after = true; },
    verifyProvenance: async () => after ? ['fixture snapshot drift'] : [],
  })), /fixture snapshot drift/);
});

test('stable resume entrypoint requires all three bound arguments', async () => {
  const script = fileURLToPath(new URL('../../../scripts/docs-site.sh', import.meta.url));
  await assert.rejects(promisify(execFile)('bash', [script, 'resume-version', '1.0.13.0', 'canary']),
    (error) => error.code === 64 && /resume-version PRODUCT_BUILD CHANNEL SOURCE_SHA/.test(error.stderr));
});

test('stable resume entrypoint forwards original SHA to the concrete verifier', async () => {
  const script = fileURLToPath(new URL('../../../scripts/docs-site.sh', import.meta.url));
  await assert.rejects(promisify(execFile)('bash', [script, 'resume-version', '1.0.13.0', 'canary', 'not-a-sha']),
    (error) => error.code === 1 && /requires the original full source SHA/.test(error.stderr));
});
