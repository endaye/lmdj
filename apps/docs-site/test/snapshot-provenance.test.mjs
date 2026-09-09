import assert from 'node:assert/strict';
import test from 'node:test';
import {promisify} from 'node:util';
import {execFile} from 'node:child_process';
import {mkdtemp, mkdir, readFile, rm, symlink, writeFile, cp, rename} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {glob} from 'glob';
import {
  createSquashWitness,
  createSnapshotMetadata,
  freezeDiagramAssets,
  projectionManifest,
  readRepoFactsAtRevision,
  resolveIntroducingRevision,
  verifySnapshotProvenance,
  SOURCE_DOCUMENT_COUNT,
} from '../scripts/lib/snapshot-provenance.mjs';
import {checkSnapshotProjection} from '../scripts/check-snapshot-projection.mjs';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');

test('current page inventory agrees with the independent snapshot completeness pin', async () => {
  const pages = await glob('**/*.mdx', {cwd: path.join(REPO_ROOT, 'apps/docs-site/docs')});
  assert.equal(pages.length, SOURCE_DOCUMENT_COUNT,
    'why: current pages would fail the snapshot completeness gate; remedy: reconcile the page inventory and SOURCE_DOCUMENT_COUNT in the same Task');
});

const execFileAsync = promisify(execFile);
const VERSION = '1.0.14.0';
const DIAGRAMS = ['lmdj-core', 'lmdj-product'];
const SOURCE_DATE = '2026-08-04T00:00:00Z';
const FREEZE_DATE = '2026-08-04T00:01:00.000Z';
const INTRO_DATE = '2026-08-04T00:02:00Z';
const PROJECTION_PATHS = [
  'apps/architecture-portal/docs/core/overview.mdx',
  'apps/architecture-portal/docs/overview/index.mdx',
  'apps/architecture-portal/sidebars.ts',
  'apps/architecture-portal/static/diagrams/lmdj-core.html',
  'apps/architecture-portal/static/diagrams/lmdj-core.svg',
  'apps/architecture-portal/static/diagrams/lmdj-product.html',
  'apps/architecture-portal/static/diagrams/lmdj-product.svg',
  'facts-source.json',
];
const facts = {
  schema_version: 1,
  product: {id: 'lmdj', version: VERSION},
  channel: 'canary',
  revision: '',
  assembly_lock_sha256: 'lock-sha',
  modules: [], hosts: [], providers: [], contracts: [],
};

async function git(root, args, options = {}) {
  return execFileAsync('git', args, {
    cwd: root,
    env: {...process.env, ...(options.env ?? {})},
    encoding: options.encoding ?? 'utf8',
    maxBuffer: 16 * 1024 * 1024,
  });
}

async function put(root, relative, body) {
  const file = path.join(root, relative);
  await mkdir(path.dirname(file), {recursive: true});
  await writeFile(file, body);
}

async function commit(root, message, date) {
  await git(root, ['add', '--all']);
  await git(root, ['-c', 'commit.gpgsign=false', 'commit', '-m', message], {
    env: {GIT_AUTHOR_DATE: date, GIT_COMMITTER_DATE: date},
  });
  return (await git(root, ['rev-parse', 'HEAD'])).stdout.trim();
}

async function initializeFixture() {
  const repoRoot = await mkdtemp(path.join(os.tmpdir(), 'portal-provenance-'));
  const portalRoot = path.join(repoRoot, 'apps/architecture-portal');
  await git(repoRoot, ['init', '-b', 'main']);
  await git(repoRoot, ['config', 'user.email', 'portal@example.test']);
  await git(repoRoot, ['config', 'user.name', 'Portal Test']);
  await put(repoRoot, '.gitkeep', 'base\n');
  const base = await commit(repoRoot, 'base', '2026-08-03T23:59:00Z');
  await put(repoRoot, 'apps/architecture-portal/docs/overview/index.mdx', 'overview\n');
  await put(repoRoot, 'apps/architecture-portal/docs/core/overview.mdx', 'core\n');
  await put(repoRoot, 'apps/architecture-portal/sidebars.ts', 'export default {};\n');
  for (const id of DIAGRAMS) {
    await put(repoRoot, `apps/architecture-portal/static/diagrams/${id}.html`, `<html>${id}</html>\n`);
    await put(repoRoot, `apps/architecture-portal/static/diagrams/${id}.svg`, `<svg>${id}</svg>\n`);
  }
  await put(repoRoot, 'facts-source.json', '{"product":"1.0.14.0"}\n');
  const revision = await commit(repoRoot, 'source', SOURCE_DATE);
  return {repoRoot, portalRoot, base, revision};
}

async function generateWorkingSnapshot(fixture) {
  const {repoRoot, portalRoot, revision} = fixture;
  for (const relative of ['overview/index.mdx', 'core/overview.mdx']) {
    const source = path.join(portalRoot, 'docs', relative);
    const target = path.join(portalRoot, `versioned_docs/version-${VERSION}`, relative);
    await mkdir(path.dirname(target), {recursive: true});
    await cp(source, target);
  }
  await put(repoRoot, `apps/architecture-portal/versioned_sidebars/version-${VERSION}-sidebars.json`, '{}\n');
  await put(repoRoot, 'apps/architecture-portal/versions.json', `[\n  "${VERSION}"\n]\n`);
  await freezeDiagramAssets({portalRoot, version: VERSION, diagramIds: DIAGRAMS});
  const metadata = await createSnapshotMetadata({
    repoRoot,
    portalRoot,
    version: VERSION,
    channel: 'canary',
    revision,
    facts: {...facts, revision},
    now: () => new Date(FREEZE_DATE),
    expectedDocCount: 2,
    diagramIds: DIAGRAMS,
    projectionPaths: fixture.projectionPaths ?? PROJECTION_PATHS,
  });
  await put(repoRoot, `apps/architecture-portal/versioned_metadata/version-${VERSION}.json`, `${JSON.stringify(metadata, null, 2)}\n`);
  return metadata;
}

async function writeSquashWitness(fixture, metadata, introducingRevision) {
  const witness = await createSquashWitness({
    repoRoot: fixture.repoRoot,
    metadata,
    introducingRevision,
  });
  await put(fixture.repoRoot, `apps/architecture-portal/versioned_provenance/version-${metadata.product_build}-squash-witness.json`, `${JSON.stringify(witness, null, 2)}\n`);
  return witness;
}

async function copyWitnessEntrypoint(fixture) {
  for (const relative of [
    'scripts/create-squash-witness.mjs',
    'scripts/lib/snapshot-provenance.mjs',
    'scripts/lib/repo-facts.mjs',
  ]) {
    const destination = path.join(fixture.portalRoot, relative);
    await mkdir(path.dirname(destination), {recursive: true});
    await cp(path.join(REPO_ROOT, 'apps/docs-site', relative), destination);
  }
}

function runWitnessEntrypoint(fixture, introducingRevision) {
  return execFileAsync('node', [
    path.join(fixture.portalRoot, 'scripts/create-squash-witness.mjs'),
    VERSION,
    introducingRevision,
  ], {cwd: fixture.repoRoot, encoding: 'utf8'});
}

function verifierOptions(fixture, metadata, headRevision) {
  return {
    repoRoot: fixture.repoRoot,
    portalRoot: fixture.portalRoot,
    metadata,
    headRevision,
    expectedDocCount: 2,
    diagramIds: DIAGRAMS,
    projectionPaths: PROJECTION_PATHS,
    readFactsAtRevision: async ({repoRoot, revision, treeRevision = revision, channel}) => {
      const source = JSON.parse((await git(repoRoot, ['show', `${treeRevision}:facts-source.json`])).stdout);
      return {...facts, product: {...facts.product, version: source.product}, revision, channel};
    },
  };
}

const METADATA_PATH = `apps/architecture-portal/versioned_metadata/version-${VERSION}.json`;

test('new snapshots authenticate renamed source while retaining stable archive paths', async () => {
  const fixture = await initializeFixture();
  try {
    const oldRoot = fixture.portalRoot;
    const newRoot = path.join(fixture.repoRoot, 'apps/docs-site');
    await mkdir(path.join(newRoot, 'static'), {recursive: true});
    for (const item of ['docs', 'sidebars.ts', 'static/diagrams']) {
      await rename(path.join(oldRoot, item), path.join(newRoot, item));
    }
    for (const item of ['versioned_docs', 'versioned_metadata', 'versioned_sidebars']) {
      await mkdir(path.join(oldRoot, item), {recursive: true});
      await symlink(`../architecture-portal/${item}`, path.join(newRoot, item));
    }
    await mkdir(path.join(oldRoot, 'static/versions'), {recursive: true});
    await symlink('../../architecture-portal/static/versions', path.join(newRoot, 'static/versions'));
    await put(fixture.repoRoot, 'apps/architecture-portal/versions.json', '[]\n');
    await symlink('../architecture-portal/versions.json', path.join(newRoot, 'versions.json'));
    fixture.portalRoot = newRoot;
    fixture.projectionPaths = PROJECTION_PATHS.map((entry) => entry.replace('apps/architecture-portal/', 'apps/docs-site/'));
    fixture.revision = await commit(fixture.repoRoot, 'rename source', SOURCE_DATE);
    const metadata = await generateWorkingSnapshot(fixture);
    assert.equal(metadata.source_sidebar.path, 'apps/docs-site/sidebars.ts');
    const options = {...verifierOptions(fixture, metadata, fixture.revision), projectionPaths: fixture.projectionPaths};
    assert.deepEqual(await verifySnapshotProvenance(options), [], 'new snapshots must validate at the exact precommit archive boundary');
    const head = await commit(fixture.repoRoot, 'freeze renamed source', INTRO_DATE);
    assert.deepEqual(await verifySnapshotProvenance({...options, headRevision: head}), []);
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('renamed active site verifies unchanged legacy snapshot provenance', async () => {
  const fixture = await initializeFixture();
  try {
    const metadata = await generateWorkingSnapshot(fixture);
    await commit(fixture.repoRoot, 'freeze', INTRO_DATE);
    const newRoot = path.join(fixture.repoRoot, 'apps/docs-site');
    await mkdir(path.join(newRoot, 'static'), {recursive: true});
    for (const item of ['docs', 'sidebars.ts', 'static/diagrams']) {
      await rename(path.join(fixture.portalRoot, item), path.join(newRoot, item));
    }
    for (const item of ['versioned_docs', 'versioned_metadata', 'versioned_sidebars', 'versions.json']) {
      await symlink(`../architecture-portal/${item}`, path.join(newRoot, item));
    }
    await symlink('../../architecture-portal/static/versions', path.join(newRoot, 'static/versions'));
    const head = await commit(fixture.repoRoot, 'rename active docs site', '2026-08-04T00:03:00Z');
    assert.deepEqual(await verifySnapshotProvenance({
      ...verifierOptions(fixture, metadata, head), portalRoot: newRoot,
    }), [], 'renaming active source must not invalidate unchanged authenticated snapshots');
    const projection = await projectionManifest(fixture.repoRoot, head);
    assert.ok(projection.files.some((entry) => entry.path === 'apps/docs-site/docs/core/overview.mdx'));
    await writeFile(path.join(newRoot, `versioned_docs/version-${VERSION}/core/overview.mdx`), 'tampered\n');
    assert.ok((await verifySnapshotProvenance({
      ...verifierOptions(fixture, metadata, head), portalRoot: newRoot,
    })).some((error) => error.includes('hash or size')), 'archive aliases must not bypass content verification');
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

async function squashOnto(fixture, headRevision, baseRevision) {
  const tree = (await git(fixture.repoRoot, ['rev-parse', `${headRevision}^{tree}`])).stdout.trim();
  const squash = (await git(fixture.repoRoot, [
    'commit-tree', tree, '-p', baseRevision, '-m', 'squash merge',
  ], {env: {GIT_AUTHOR_DATE: INTRO_DATE, GIT_COMMITTER_DATE: INTRO_DATE}})).stdout.trim();
  await git(fixture.repoRoot, ['update-ref', 'refs/heads/main', squash]);
  await git(fixture.repoRoot, ['reset', '--hard', squash]);
  return squash;
}

function preMergeProjectionGate(fixture, metadata, headRevision) {
  return checkSnapshotProjection({
    addedFiles: [METADATA_PATH],
    readMetadata: async () => metadata,
    readProjection: (paths) => projectionManifest(fixture.repoRoot, headRevision, paths),
  });
}

// Issue #296: every gate that authorizes a merge runs on the pre-merge head,
// while the provenance invariant is decided on the squash GitHub creates. A
// snapshot frozen mid-branch is accepted on the branch by the direct-parent
// rule and can only be accepted on main by projection equality, so the two
// verdicts disagree by construction. These two tests are the contract that
// the pre-merge gate returns the verdict the squash will produce.
test('a snapshot frozen before later edits fails the pre-merge gate exactly as the squash will', async () => {
  const fixture = await initializeFixture();
  try {
    const metadata = await generateWorkingSnapshot(fixture);
    await put(fixture.repoRoot, 'apps/architecture-portal/docs/overview/index.mdx', 'post-freeze overview\n');
    const branchTip = await commit(fixture.repoRoot, 'snapshot plus later edits', INTRO_DATE);

    const preMerge = await preMergeProjectionGate(fixture, metadata, branchTip);
    assert.equal(preMerge.length, 1, preMerge.join('\n'));
    assert.match(preMerge[0], /does not match this change's own tree/);
    assert.match(preMerge[0], new RegExp(`scripts/architecture-portal\\.sh version ${VERSION}`));

    const squash = await squashOnto(fixture, branchTip, fixture.base);
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(fixture, metadata, squash))).join('\n'),
      /source projection is neither direct-parent nor squash-equivalent/,
    );
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('a snapshot frozen at the branch tip passes the pre-merge gate and the squash it produces', async () => {
  const fixture = await initializeFixture();
  try {
    await put(fixture.repoRoot, 'apps/architecture-portal/docs/overview/index.mdx', 'current docs move on\n');
    fixture.revision = await commit(fixture.repoRoot, 'current docs move on', '2026-08-04T00:00:30Z');
    const metadata = await generateWorkingSnapshot(fixture);
    const branchTip = await commit(fixture.repoRoot, 'freeze at the branch tip', INTRO_DATE);

    assert.deepEqual(await preMergeProjectionGate(fixture, metadata, branchTip), []);

    const squash = await squashOnto(fixture, branchTip, fixture.base);
    assert.deepEqual(await verifySnapshotProvenance(verifierOptions(fixture, metadata, squash)), []);
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('source-tree archive reads committed bytes without running content filters', async () => {
  // A checkout that skipped the Git LFS smudge holds pointers and no objects, and
  // an audit checkout holds no credentials to download them with. Rebuilding facts
  // must still succeed, so the archive has to bypass the required filter.
  const home = await mkdtemp(path.join(os.tmpdir(), 'portal-filter-config-'));
  const configPath = path.join(home, 'gitconfig');
  await writeFile(configPath, [
    '[filter "lfs"]',
    '\tclean = cat',
    '\tsmudge = false',
    '\tprocess = ',
    '\trequired = true',
    '',
  ].join('\n'), 'utf8');
  const previousGlobal = process.env.GIT_CONFIG_GLOBAL;
  const previousSystem = process.env.GIT_CONFIG_SYSTEM;
  process.env.GIT_CONFIG_GLOBAL = configPath;
  process.env.GIT_CONFIG_SYSTEM = '/dev/null';
  try {
    const revision = (await git(REPO_ROOT, ['rev-parse', 'HEAD'])).stdout.trim();
    const rebuilt = await readRepoFactsAtRevision({repoRoot: REPO_ROOT, revision, channel: 'canary'});
    assert.equal(rebuilt.product.id, 'lmdj');
    assert.equal(rebuilt.revision, revision);
  } finally {
    if (previousGlobal === undefined) delete process.env.GIT_CONFIG_GLOBAL;
    else process.env.GIT_CONFIG_GLOBAL = previousGlobal;
    if (previousSystem === undefined) delete process.env.GIT_CONFIG_SYSTEM;
    else process.env.GIT_CONFIG_SYSTEM = previousSystem;
    await rm(home, {recursive: true, force: true});
  }
});

test('diagram freeze copies the exact validated inventory and rejects unsafe inputs', async () => {
  const fixture = await initializeFixture();
  try {
    const assets = await freezeDiagramAssets({portalRoot: fixture.portalRoot, version: VERSION, diagramIds: DIAGRAMS});
    assert.equal(assets.length, 4);
    assert.deepEqual(assets.map((asset) => asset.versioned_path), [
      `static/versions/${VERSION}/diagrams/lmdj-core.html`,
      `static/versions/${VERSION}/diagrams/lmdj-core.svg`,
      `static/versions/${VERSION}/diagrams/lmdj-product.html`,
      `static/versions/${VERSION}/diagrams/lmdj-product.svg`,
    ]);
    await assert.rejects(
      () => freezeDiagramAssets({portalRoot: fixture.portalRoot, version: VERSION, diagramIds: ['lmdj-core', 'lmdj-core']}),
      /duplicate diagram id/,
    );
    await assert.rejects(
      () => freezeDiagramAssets({portalRoot: fixture.portalRoot, version: VERSION, diagramIds: ['../escape']}),
      /invalid diagram id/,
    );
    await assert.rejects(
      () => freezeDiagramAssets({portalRoot: fixture.portalRoot, version: VERSION, diagramIds: ['missing']}),
      /missing diagram asset/,
    );
    await rm(path.join(fixture.portalRoot, `static/versions/${VERSION}`), {recursive: true, force: true});
    await rm(path.join(fixture.portalRoot, 'static/diagrams/lmdj-core.svg'));
    await symlink('lmdj-product.svg', path.join(fixture.portalRoot, 'static/diagrams/lmdj-core.svg'));
    await assert.rejects(
      () => freezeDiagramAssets({portalRoot: fixture.portalRoot, version: VERSION, diagramIds: ['lmdj-core']}),
      /cannot be a symlink/,
    );
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('schema-2 provenance validates precommit, direct-parent introduction, and future HEAD', async () => {
  const fixture = await initializeFixture();
  try {
    const metadata = await generateWorkingSnapshot(fixture);
    assert.equal(metadata.schema_version, 2);
    assert.equal(metadata.source_documents.length, 2);
    assert.equal(metadata.diagrams.ids.length, 2);
    assert.equal(metadata.diagrams.assets.length, 4);
    assert.equal((await verifySnapshotProvenance(verifierOptions(fixture, metadata, fixture.revision))).length, 0);

    const introducing = await commit(fixture.repoRoot, 'snapshot', INTRO_DATE);
    assert.equal((await verifySnapshotProvenance(verifierOptions(fixture, metadata, introducing))).length, 0);
    await put(fixture.repoRoot, 'unrelated.txt', 'future\n');
    const future = await commit(fixture.repoRoot, 'future', '2026-08-04T00:03:00Z');
    assert.equal((await verifySnapshotProvenance(verifierOptions(fixture, metadata, future))).length, 0);
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('schema-2 provenance accepts an unmodified snapshot through a merge parent', async () => {
  const fixture = await initializeFixture();
  try {
    const metadata = await generateWorkingSnapshot(fixture);
    const introducing = await commit(fixture.repoRoot, 'snapshot', INTRO_DATE);

    await git(fixture.repoRoot, ['checkout', '-b', 'feature', fixture.revision]);
    await put(fixture.repoRoot, 'feature.txt', 'feature\n');
    await commit(fixture.repoRoot, 'feature', '2026-08-04T00:03:00Z');
    await git(fixture.repoRoot, [
      '-c', 'commit.gpgsign=false', 'merge', '--no-ff', introducing,
      '-m', 'merge snapshot parent',
    ], {
      env: {
        GIT_AUTHOR_DATE: '2026-08-04T00:04:00Z',
        GIT_COMMITTER_DATE: '2026-08-04T00:04:00Z',
      },
    });
    const merged = (await git(fixture.repoRoot, ['rev-parse', 'HEAD'])).stdout.trim();

    assert.deepEqual(
      await verifySnapshotProvenance(verifierOptions(fixture, metadata, merged)),
      [],
    );
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('schema-2 provenance rejects fake revisions, commit-byte tampering, and snapshot drift', async () => {
  const fixture = await initializeFixture();
  try {
    const metadata = await generateWorkingSnapshot(fixture);
    const introducing = await commit(fixture.repoRoot, 'snapshot', INTRO_DATE);

    const allZero = structuredClone(metadata);
    allZero.revision = '0'.repeat(40);
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, allZero, introducing))).join('\n'), /revision.*all-zero|does not exist/);

    const nonexistent = structuredClone(metadata);
    nonexistent.revision = 'f'.repeat(40);
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, nonexistent, introducing))).join('\n'), /does not exist/);

    const rawTamper = structuredClone(metadata);
    rawTamper.source_commit.raw_base64 = Buffer.from('not a git commit').toString('base64');
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, rawTamper, introducing))).join('\n'), /raw commit bytes/);

    await writeFile(path.join(fixture.portalRoot, `versioned_docs/version-${VERSION}/overview/index.mdx`), 'tampered\n');
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, metadata, introducing))).join('\n'), /snapshot document.*hash/);
    await git(fixture.repoRoot, ['restore', '.']);
    await writeFile(path.join(fixture.portalRoot, `versioned_sidebars/version-${VERSION}-sidebars.json`), 'tampered\n');
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, metadata, introducing))).join('\n'), /snapshot sidebar.*hash/);
    await git(fixture.repoRoot, ['restore', '.']);
    await writeFile(path.join(fixture.portalRoot, `static/versions/${VERSION}/diagrams/lmdj-core.svg`), 'tampered\n');
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, metadata, introducing))).join('\n'), /diagram asset.*hash/);
    await git(fixture.repoRoot, ['restore', '.']);
    const metadataTamper = {...metadata, unverified_extra_field: true};
    await writeFile(
      path.join(fixture.portalRoot, `versioned_metadata/version-${VERSION}.json`),
      `${JSON.stringify(metadataTamper, null, 2)}\n`,
    );
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(fixture, metadataTamper, introducing))).join('\n'),
      /immutable snapshot path is dirty in the working tree/,
    );
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  }
  return value;
}

function manifestSha(files) {
  return createHash('sha256').update(`${JSON.stringify(canonicalize(files))}\n`).digest('hex');
}

test('schema-2 provenance rejects duplicate inventories, reduced projections, extra dirty paths, and bad timestamps', async () => {
  const fixture = await initializeFixture();
  try {
    const metadata = await generateWorkingSnapshot(fixture);

    const duplicateDocs = structuredClone(metadata);
    duplicateDocs.source_documents[0] = structuredClone(duplicateDocs.source_documents[1]);
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, duplicateDocs, fixture.revision))).join('\n'), /source document inventory/);

    const duplicateAssets = structuredClone(metadata);
    duplicateAssets.diagrams.assets[0] = structuredClone(duplicateAssets.diagrams.assets[1]);
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, duplicateAssets, fixture.revision))).join('\n'), /diagram asset inventory/);

    const reducedProjection = structuredClone(metadata);
    reducedProjection.source_projection.files.shift();
    reducedProjection.source_projection.sha256 = manifestSha(reducedProjection.source_projection.files);
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, reducedProjection, fixture.revision))).join('\n'), /source projection inventory/);

    await put(fixture.repoRoot, 'unexpected-dirty.txt', 'not generated\n');
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, metadata, fixture.revision))).join('\n'), /exact generated snapshot boundary/);
    await rm(path.join(fixture.repoRoot, 'unexpected-dirty.txt'));

    const beforeSource = structuredClone(metadata);
    beforeSource.frozen_at_utc = '2026-08-03T23:59:59.000Z';
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, beforeSource, fixture.revision))).join('\n'), /source <= freeze/);

    const introducing = await commit(fixture.repoRoot, 'snapshot', INTRO_DATE);
    const afterIntroduction = structuredClone(metadata);
    afterIntroduction.frozen_at_utc = '2026-08-04T00:03:00.000Z';
    assert.match((await verifySnapshotProvenance(verifierOptions(fixture, afterIntroduction, introducing))).join('\n'), /freeze <= introducing/);
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('schema-2 provenance accepts a fresh-clone squash without the source object and rejects divergent evidence', async () => {
  const fixture = await initializeFixture();
  let cloneParent;
  try {
    await put(fixture.repoRoot, 'source-private-parent.txt', 'not reachable from the squash parent\n');
    fixture.revision = await commit(fixture.repoRoot, 'final source with private parent', '2026-08-04T00:00:30Z');
    const source = fixture.revision;
    const metadata = await generateWorkingSnapshot(fixture);
    const directIntroduction = await commit(fixture.repoRoot, 'direct snapshot', INTRO_DATE);
    const introductionTree = (await git(fixture.repoRoot, ['rev-parse', `${directIntroduction}^{tree}`])).stdout.trim();
    const squashIntroduction = (await git(fixture.repoRoot, ['commit-tree', introductionTree, '-p', fixture.base, '-m', 'squash source and snapshot'], {
      env: {GIT_AUTHOR_DATE: INTRO_DATE, GIT_COMMITTER_DATE: INTRO_DATE},
    })).stdout.trim();
    await git(fixture.repoRoot, ['update-ref', 'refs/heads/main', squashIntroduction]);
    await git(fixture.repoRoot, ['reset', '--hard', squashIntroduction]);
    assert.equal((await verifySnapshotProvenance(verifierOptions(fixture, metadata, squashIntroduction))).length, 0);

    cloneParent = await mkdtemp(path.join(os.tmpdir(), 'portal-squash-clone-'));
    const cloneRoot = path.join(cloneParent, 'repo');
    await git(fixture.repoRoot, ['clone', '--no-local', '--single-branch', '--branch', 'main', fixture.repoRoot, cloneRoot]);
    await assert.rejects(() => git(cloneRoot, ['cat-file', '-e', `${source}^{commit}`]));
    const clonedFixture = {
      repoRoot: cloneRoot,
      portalRoot: path.join(cloneRoot, 'apps/architecture-portal'),
    };
    const clonedMetadata = JSON.parse(await readFile(
      path.join(clonedFixture.portalRoot, `versioned_metadata/version-${VERSION}.json`),
      'utf8',
    ));
    assert.equal((await verifySnapshotProvenance(verifierOptions(clonedFixture, clonedMetadata, squashIntroduction))).length, 0);

    const projectionTamper = structuredClone(clonedMetadata);
    projectionTamper.source_projection.files[0].sha256 = '0'.repeat(64);
    projectionTamper.source_projection.sha256 = manifestSha(projectionTamper.source_projection.files);
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, projectionTamper, squashIntroduction))).join('\n'),
      /source projection manifest does not match source revision/,
    );

    const factsTamper = structuredClone(clonedMetadata);
    factsTamper.hosts = [{id: 'divergent'}];
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, factsTamper, squashIntroduction))).join('\n'),
      /snapshot hosts does not match source-rebuilt facts/,
    );

    const documentTamper = structuredClone(clonedMetadata);
    documentTamper.source_documents[0].sha256 = '0'.repeat(64);
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, documentTamper, squashIntroduction))).join('\n'),
      /source document .* hash or size does not match recorded source/,
    );

    const sidebarTamper = structuredClone(clonedMetadata);
    sidebarTamper.source_sidebar.sha256 = '0'.repeat(64);
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, sidebarTamper, squashIntroduction))).join('\n'),
      /source sidebar hash or size does not match recorded source/,
    );

    const diagramTamper = structuredClone(clonedMetadata);
    diagramTamper.diagrams.assets[0].sha256 = '0'.repeat(64);
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, diagramTamper, squashIntroduction))).join('\n'),
      /source diagram .* hash or size does not match recorded source/,
    );

    const invalidBase64 = structuredClone(clonedMetadata);
    invalidBase64.source_commit.raw_base64 = '%%%';
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, invalidBase64, squashIntroduction))).join('\n'),
      /source commit raw_base64 is not canonical base64/,
    );

    const rawTamper = structuredClone(clonedMetadata);
    rawTamper.source_commit.raw_base64 = Buffer.concat([
      Buffer.from(rawTamper.source_commit.raw_base64, 'base64'),
      Buffer.from('tamper'),
    ]).toString('base64');
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, rawTamper, squashIntroduction))).join('\n'),
      /raw commit bytes do not authenticate the snapshot revision/,
    );

    const treeTamper = structuredClone(clonedMetadata);
    treeTamper.source_commit.tree = '0'.repeat(40);
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, treeTamper, squashIntroduction))).join('\n'),
      /raw commit tree does not match recorded source commit tree/,
    );

    const timeTamper = structuredClone(clonedMetadata);
    timeTamper.source_commit.committed_at_utc = '2026-08-04T00:00:01.000Z';
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, timeTamper, squashIntroduction))).join('\n'),
      /raw commit committer time does not match recorded source commit time/,
    );

    await git(fixture.repoRoot, ['checkout', '--detach', fixture.base]);
    await git(fixture.repoRoot, ['checkout', directIntroduction, '--', 'apps/architecture-portal', 'facts-source.json']);
    await writeFile(path.join(fixture.portalRoot, 'docs/overview/index.mdx'), 'divergent\n');
    const badIntro = await commit(fixture.repoRoot, 'divergent squash introduction', INTRO_DATE);
    await git(fixture.repoRoot, ['update-ref', 'refs/heads/main', badIntro]);
    await git(fixture.repoRoot, ['reset', '--hard', badIntro]);
    const unavailable = (await verifySnapshotProvenance(verifierOptions(fixture, metadata, badIntro))).join('\n');
    assert.match(unavailable, /source projection is neither direct-parent nor squash-equivalent/);
    // The failure must name the exact remedy with both arguments filled in:
    // an operator reading it should not have to work out either one.
    assert.match(
      unavailable,
      new RegExp(`run: scripts/architecture-portal\\.sh witness ${VERSION} ${badIntro}`),
    );
  } finally {
    if (cloneParent) await rm(cloneParent, {recursive: true, force: true});
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('schema-2 provenance authenticates a divergent squash through a source-tree witness', async () => {
  const fixture = await initializeFixture();
  let cloneParent;
  try {
    await put(fixture.repoRoot, 'source-private-parent.txt', 'not reachable from the squash parent\n');
    fixture.revision = await commit(fixture.repoRoot, 'final source with private parent', '2026-08-04T00:00:30Z');
    const source = fixture.revision;
    const metadata = await generateWorkingSnapshot(fixture);
    await put(fixture.repoRoot, 'apps/architecture-portal/docs/overview/index.mdx', 'post-freeze current overview\n');
    await put(fixture.repoRoot, 'post-freeze-evidence.txt', 'not part of the frozen projection\n');
    const directIntroduction = await commit(fixture.repoRoot, 'snapshot plus current edits', INTRO_DATE);
    const introductionTree = (await git(fixture.repoRoot, ['rev-parse', `${directIntroduction}^{tree}`])).stdout.trim();
    const squashIntroduction = (await git(fixture.repoRoot, ['commit-tree', introductionTree, '-p', fixture.base, '-m', 'divergent squash introduction'], {
      env: {GIT_AUTHOR_DATE: INTRO_DATE, GIT_COMMITTER_DATE: INTRO_DATE},
    })).stdout.trim();
    await git(fixture.repoRoot, ['update-ref', 'refs/heads/main', squashIntroduction]);
    await git(fixture.repoRoot, ['reset', '--hard', squashIntroduction]);
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(fixture, metadata, squashIntroduction))).join('\n'),
      /source projection is neither direct-parent nor squash-equivalent/,
    );

    const witness = await writeSquashWitness(fixture, metadata, squashIntroduction);
    const corrected = await commit(fixture.repoRoot, 'add authenticated squash witness', '2026-08-04T00:03:00Z');
    assert.equal((await verifySnapshotProvenance(verifierOptions(fixture, metadata, corrected))).length, 0);

    cloneParent = await mkdtemp(path.join(os.tmpdir(), 'portal-witness-clone-'));
    const cloneRoot = path.join(cloneParent, 'repo');
    await git(fixture.repoRoot, ['clone', '--no-local', '--single-branch', '--branch', 'main', fixture.repoRoot, cloneRoot]);
    await git(cloneRoot, ['config', 'user.email', 'portal@example.test']);
    await git(cloneRoot, ['config', 'user.name', 'Portal Test']);
    await assert.rejects(() => git(cloneRoot, ['cat-file', '-e', `${source}^{commit}`]));
    const clonedFixture = {
      repoRoot: cloneRoot,
      portalRoot: path.join(cloneRoot, 'apps/architecture-portal'),
    };
    const clonedMetadata = JSON.parse(await readFile(
      path.join(clonedFixture.portalRoot, `versioned_metadata/version-${VERSION}.json`),
      'utf8',
    ));
    assert.equal((await verifySnapshotProvenance(verifierOptions(clonedFixture, clonedMetadata, corrected))).length, 0);

    const tampered = structuredClone(witness);
    const blobEntry = tampered.entries.find((entry) => entry.source_base64);
    assert.ok(blobEntry);
    blobEntry.source_base64 = Buffer.from('tampered\n').toString('base64');
    await put(clonedFixture.repoRoot, `apps/architecture-portal/versioned_provenance/version-${VERSION}-squash-witness.json`, `${JSON.stringify(tampered, null, 2)}\n`);
    const tamperedHead = await commit(clonedFixture.repoRoot, 'tamper squash witness', '2026-08-04T00:04:00Z');
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(clonedFixture, clonedMetadata, tamperedHead))).join('\n'),
      /squash witness does not reconstruct the authenticated source tree/,
    );
  } finally {
    if (cloneParent) await rm(cloneParent, {recursive: true, force: true});
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('schema-2 provenance resolves the latest continuous lifecycle after delete and corrective re-add', async () => {
  const fixture = await initializeFixture();
  try {
    const metadata = await generateWorkingSnapshot(fixture);
    const firstIntroduction = await commit(fixture.repoRoot, 'invalid snapshot introduction', INTRO_DATE);
    const generatedPaths = [
      `apps/architecture-portal/versioned_docs/version-${VERSION}`,
      `apps/architecture-portal/versioned_sidebars/version-${VERSION}-sidebars.json`,
      'apps/architecture-portal/versions.json',
      `apps/architecture-portal/static/versions/${VERSION}`,
      `apps/architecture-portal/versioned_metadata/version-${VERSION}.json`,
    ];

    await git(fixture.repoRoot, ['rm', '-r', '--', ...generatedPaths]);
    await commit(fixture.repoRoot, 'remove invalid snapshot', '2026-08-04T00:03:00Z');
    await git(fixture.repoRoot, ['checkout', firstIntroduction, '--', ...generatedPaths]);
    const correctiveIntroduction = await commit(fixture.repoRoot, 'restore corrected snapshot', '2026-08-04T00:04:00Z');

    assert.equal((await verifySnapshotProvenance(verifierOptions(fixture, metadata, correctiveIntroduction))).length, 0);

    const restoredDocument = `apps/architecture-portal/versioned_docs/version-${VERSION}/overview/index.mdx`;
    await put(fixture.repoRoot, restoredDocument, 'temporary drift\n');
    await commit(fixture.repoRoot, 'temporarily change immutable snapshot', '2026-08-04T00:05:00Z');
    await git(fixture.repoRoot, ['checkout', correctiveIntroduction, '--', restoredDocument]);
    const restoredBytes = await commit(fixture.repoRoot, 'restore immutable snapshot bytes', '2026-08-04T00:06:00Z');
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(fixture, metadata, restoredBytes))).join('\n'),
      /generated immutable snapshot paths changed after introducing commit/,
    );

    await git(fixture.repoRoot, ['rm', '--', `apps/architecture-portal/versioned_metadata/version-${VERSION}.json`]);
    const metadataAbsent = await commit(fixture.repoRoot, 'remove current metadata', '2026-08-04T00:07:00Z');
    assert.match(
      (await verifySnapshotProvenance(verifierOptions(fixture, metadata, metadataAbsent))).join('\n'),
      /snapshot metadata path is absent at HEAD/,
    );
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('witness entrypoint preserves an existing witness and names its collision', async () => {
  const fixture = await initializeFixture();
  try {
    await generateWorkingSnapshot(fixture);
    const introduction = await commit(fixture.repoRoot, 'snapshot introduction', INTRO_DATE);
    await copyWitnessEntrypoint(fixture);
    const output = path.join(
      fixture.portalRoot,
      `versioned_provenance/version-${VERSION}-squash-witness.json`,
    );

    await runWitnessEntrypoint(fixture, introduction);
    const firstBytes = await readFile(output);

    await assert.rejects(
      runWitnessEntrypoint(fixture, introduction),
      (error) => {
        assert.match(
          error.stderr,
          new RegExp(
            `squash witness already exists: apps/architecture-portal/versioned_provenance/version-${VERSION}-squash-witness\\.json`,
          ),
        );
        return true;
      },
    );
    assert.deepEqual(await readFile(output), firstBytes);
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});

test('the squash witness remedy derives its introducing revision from HEAD', async () => {
  const fixture = await initializeFixture();
  try {
    const metadata = await generateWorkingSnapshot(fixture);
    await put(fixture.repoRoot, 'apps/architecture-portal/docs/overview/index.mdx', 'post-freeze current overview\n');
    const introduction = await commit(fixture.repoRoot, 'snapshot plus current edits', INTRO_DATE);
    await git(fixture.repoRoot, ['update-ref', 'refs/heads/main', introduction]);

    // The verifier resolves this revision for itself before reporting the
    // witness missing, so the remedy must not demand it from the operator.
    const derived = await resolveIntroducingRevision({
      repoRoot: fixture.repoRoot,
      version: VERSION,
      headRevision: introduction,
    });
    assert.equal(derived, introduction);

    // Deriving and passing the revision must produce the same witness bytes.
    const [explicitWitness, derivedWitness] = await Promise.all([
      createSquashWitness({repoRoot: fixture.repoRoot, metadata, introducingRevision: introduction}),
      createSquashWitness({repoRoot: fixture.repoRoot, metadata, introducingRevision: derived}),
    ]);
    assert.deepEqual(derivedWitness, explicitWitness);

    // Derivation is fail-closed: with the metadata gone from HEAD there is no
    // introducing revision to infer, and the remedy must refuse rather than guess.
    await git(fixture.repoRoot, ['rm', '--', `apps/architecture-portal/versioned_metadata/version-${VERSION}.json`]);
    const metadataAbsent = await commit(fixture.repoRoot, 'remove current metadata', '2026-08-04T00:07:00Z');
    await assert.rejects(
      resolveIntroducingRevision({
        repoRoot: fixture.repoRoot,
        version: VERSION,
        headRevision: metadataAbsent,
      }),
      /snapshot metadata path is absent at HEAD/,
    );
  } finally {
    await rm(fixture.repoRoot, {recursive: true, force: true});
  }
});
