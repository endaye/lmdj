import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {constants as fsConstants} from 'node:fs';
import {
  copyFile, lstat, mkdir, mkdtemp, readFile, rm,
} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {promisify} from 'node:util';
import {readRepoFacts} from './repo-facts.mjs';

const execFileAsync = promisify(execFile);
const SHA_PATTERN = /^[0-9a-f]{40}$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+\.\d+$/;
const DIAGRAM_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const DIAGRAM_IDS = Object.freeze([
  'application-facade', 'audio-runtime', 'authoring-domain', 'foundation',
  'lmdj-core', 'lmdj-product', 'project-cooker', 'project-io', 'provider-sdk',
]);

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  }
  return value;
}

function canonicalJson(value) {
  return `${JSON.stringify(canonicalize(value))}\n`;
}

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function validateVersion(version) {
  if (!VERSION_PATTERN.test(version)) throw new Error('snapshot version must be a four-part Product Build');
}

function validateRevision(revision) {
  if (!SHA_PATTERN.test(revision)) throw new Error('snapshot revision must be a full Git SHA');
  if (/^0+$/.test(revision)) throw new Error('snapshot revision cannot be all-zero');
}

export function validateRelativePath(relative) {
  if (typeof relative !== 'string' || !relative || relative.includes('\0') || relative.includes('\\') || path.posix.isAbsolute(relative)) {
    throw new Error(`invalid repository-relative path ${JSON.stringify(relative)}`);
  }
  const normalized = path.posix.normalize(relative);
  if (normalized !== relative || normalized === '..' || normalized.startsWith('../') || relative.split('/').includes('.')) {
    throw new Error(`invalid repository-relative path ${JSON.stringify(relative)}`);
  }
  return relative;
}

function safeJoin(root, relative) {
  validateRelativePath(relative);
  const resolvedRoot = path.resolve(root);
  const resolved = path.resolve(resolvedRoot, ...relative.split('/'));
  if (resolved !== resolvedRoot && !resolved.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error(`path escapes root: ${relative}`);
  }
  return resolved;
}

async function execGit(repoRoot, args, {buffer = false, allowFailure = false} = {}) {
  try {
    return await execFileAsync('git', args, {
      cwd: repoRoot,
      encoding: buffer ? 'buffer' : 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    });
  } catch (error) {
    if (allowFailure) return null;
    throw error;
  }
}

async function gitCommitExists(repoRoot, revision) {
  validateRevision(revision);
  return Boolean(await execGit(repoRoot, ['cat-file', '-e', `${revision}^{commit}`], {allowFailure: true}));
}

async function gitBlob(repoRoot, revision, relative) {
  validateRevision(revision);
  validateRelativePath(relative);
  const result = await execGit(repoRoot, ['cat-file', 'blob', `${revision}:${relative}`], {buffer: true});
  return Buffer.from(result.stdout);
}

async function gitCommitEvidence(repoRoot, revision) {
  validateRevision(revision);
  if (!await gitCommitExists(repoRoot, revision)) throw new Error(`snapshot revision ${revision} does not exist`);
  const raw = Buffer.from((await execGit(repoRoot, ['cat-file', 'commit', revision], {buffer: true})).stdout);
  const authenticated = createHash('sha1')
    .update(Buffer.from(`commit ${raw.length}\0`))
    .update(raw)
    .digest('hex');
  if (authenticated !== revision) throw new Error('raw commit bytes do not authenticate the snapshot revision');
  const committedAt = (await execGit(repoRoot, ['show', '-s', '--format=%cI', revision])).stdout.trim();
  const tree = (await execGit(repoRoot, ['rev-parse', `${revision}^{tree}`])).stdout.trim();
  return {
    raw_base64: raw.toString('base64'),
    committed_at_utc: new Date(committedAt).toISOString(),
    tree,
  };
}

function authenticateRecordedCommit(revision, sourceCommit) {
  validateRevision(revision);
  if (!sourceCommit || typeof sourceCommit !== 'object' || Array.isArray(sourceCommit)) {
    throw new Error('source commit evidence must be an object');
  }
  if (!sameJson(Object.keys(sourceCommit).sort(), ['committed_at_utc', 'raw_base64', 'tree'])) {
    throw new Error('source commit evidence fields are invalid');
  }
  const encoded = sourceCommit.raw_base64;
  if (typeof encoded !== 'string' || encoded.length === 0 || encoded.length % 4 !== 0 ||
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) {
    throw new Error('source commit raw_base64 is not canonical base64');
  }
  const raw = Buffer.from(encoded, 'base64');
  if (raw.toString('base64') !== encoded) throw new Error('source commit raw_base64 is not canonical base64');
  const authenticated = createHash('sha1')
    .update(Buffer.from(`commit ${raw.length}\0`))
    .update(raw)
    .digest('hex');
  if (authenticated !== revision) throw new Error('raw commit bytes do not authenticate the snapshot revision');

  const separator = raw.indexOf(Buffer.from('\n\n'));
  if (separator <= 0) throw new Error('raw commit headers are malformed');
  const headerBytes = raw.subarray(0, separator);
  const headers = headerBytes.toString('utf8');
  if (!Buffer.from(headers, 'utf8').equals(headerBytes) || headers.includes('\r')) {
    throw new Error('raw commit headers are malformed');
  }
  const lines = headers.split('\n');
  const treeLines = lines.filter((line) => line.startsWith('tree '));
  const committerLines = lines.filter((line) => line.startsWith('committer '));
  if (treeLines.length !== 1 || committerLines.length !== 1) throw new Error('raw commit headers are malformed');
  const treeMatch = /^tree ([0-9a-f]{40})$/.exec(treeLines[0]);
  const committerMatch = /^committer .+ ([0-9]+) ([+-])(\d{2})(\d{2})$/.exec(committerLines[0]);
  if (!treeMatch || !committerMatch) throw new Error('raw commit headers are malformed');
  const timezoneHours = Number(committerMatch[3]);
  const timezoneMinutes = Number(committerMatch[4]);
  const epochSeconds = Number(committerMatch[1]);
  if (timezoneHours > 23 || timezoneMinutes > 59 || !Number.isSafeInteger(epochSeconds)) {
    throw new Error('raw commit committer header is malformed');
  }
  const committedAt = new Date(epochSeconds * 1000);
  if (Number.isNaN(committedAt.valueOf())) throw new Error('raw commit committer header is malformed');
  if (treeMatch[1] !== sourceCommit.tree) throw new Error('raw commit tree does not match recorded source commit tree');
  if (committedAt.toISOString() !== sourceCommit.committed_at_utc) {
    throw new Error('raw commit committer time does not match recorded source commit time');
  }
  return {tree: treeMatch[1], committedAt};
}

async function worktreeEvidence(root, relative, label) {
  const file = safeJoin(root, relative);
  const info = await lstat(file).catch(() => null);
  if (!info) throw new Error(`${label} is missing: ${relative}`);
  if (info.isSymbolicLink()) throw new Error(`${label} cannot be a symlink: ${relative}`);
  if (!info.isFile()) throw new Error(`${label} must be a regular file: ${relative}`);
  const bytes = await readFile(file);
  return {path: relative, bytes: bytes.length, sha256: sha256(bytes)};
}

async function revisionEvidence(repoRoot, revision, relative) {
  const bytes = await gitBlob(repoRoot, revision, relative);
  return {path: relative, bytes: bytes.length, sha256: sha256(bytes)};
}

function manifestSha(files) {
  return sha256(Buffer.from(canonicalJson(files)));
}

async function listRevisionPaths(repoRoot, revision) {
  const stdout = Buffer.from((await execGit(repoRoot, ['ls-tree', '-r', '-z', '--name-only', revision], {buffer: true})).stdout);
  return stdout.toString('utf8').split('\0').filter(Boolean).map(validateRelativePath).sort();
}

function isProjectionPath(relative) {
  if (relative.startsWith('apps/architecture-portal/docs/') && relative.endsWith('.mdx')) return true;
  if (relative === 'apps/architecture-portal/sidebars.ts' || relative === 'apps/architecture-portal/docusaurus.config.ts') return true;
  if (relative.startsWith('apps/architecture-portal/src/components/')) return true;
  if (relative.startsWith('apps/architecture-portal/diagrams/')) return true;
  if (relative.startsWith('apps/architecture-portal/static/diagrams/')) return true;
  if (relative.startsWith('products/lmdj/')) return true;
  if (/^(?:packages|apps)\/[^/]+\/module\.json$/.test(relative)) return true;
  if (relative.startsWith('providers/')) return true;
  if (relative.startsWith('contracts/') && relative.endsWith('.schema.json')) return true;
  return false;
}

async function projectionManifest(repoRoot, revision, requestedPaths) {
  const paths = requestedPaths
    ? [...requestedPaths].map(validateRelativePath).sort()
    : (await listRevisionPaths(repoRoot, revision)).filter(isProjectionPath);
  if (new Set(paths).size !== paths.length) throw new Error('source projection contains duplicate paths');
  const files = [];
  for (const relative of paths) files.push(await revisionEvidence(repoRoot, revision, relative));
  return {sha256: manifestSha(files), files};
}

function validateDiagramIds(diagramIds) {
  const ids = [...diagramIds];
  for (const id of ids) {
    if (!DIAGRAM_PATTERN.test(id)) throw new Error(`invalid diagram id ${id}`);
  }
  if (new Set(ids).size !== ids.length) throw new Error('duplicate diagram id');
  return ids.sort();
}

export async function freezeDiagramAssets({portalRoot, version, diagramIds = DIAGRAM_IDS}) {
  validateVersion(version);
  const ids = validateDiagramIds(diagramIds);
  const pending = [];
  for (const id of ids) {
    for (const extension of ['html', 'svg']) {
      const sourcePath = `static/diagrams/${id}.${extension}`;
      const versionedPath = `static/versions/${version}/diagrams/${id}.${extension}`;
      const source = await worktreeEvidence(portalRoot, sourcePath, 'diagram asset').catch((error) => {
        if (/ is missing:/.test(error.message)) throw new Error(`missing diagram asset: ${sourcePath}`);
        throw error;
      });
      const target = safeJoin(portalRoot, versionedPath);
      if (await lstat(target).catch(() => null)) throw new Error(`versioned diagram asset already exists: ${versionedPath}`);
      pending.push({source, sourcePath, versionedPath, target});
    }
  }
  for (const item of pending) {
    await mkdir(path.dirname(item.target), {recursive: true});
    await copyFile(safeJoin(portalRoot, item.sourcePath), item.target, fsConstants.COPYFILE_EXCL);
  }
  return pending.map(({source, sourcePath, versionedPath}) => ({
    id: path.posix.basename(sourcePath, path.posix.extname(sourcePath)),
    format: path.posix.extname(sourcePath).slice(1),
    source_path: sourcePath,
    versioned_path: versionedPath,
    bytes: source.bytes,
    sha256: source.sha256,
  }));
}

async function sourceDocumentPaths(repoRoot, revision) {
  return (await listRevisionPaths(repoRoot, revision))
    .filter((relative) => relative.startsWith('apps/architecture-portal/docs/') && relative.endsWith('.mdx'));
}

function snapshotDocumentPath(sourcePath, version) {
  const prefix = 'apps/architecture-portal/docs/';
  if (!sourcePath.startsWith(prefix)) throw new Error(`invalid source document path ${sourcePath}`);
  return `versioned_docs/version-${version}/${sourcePath.slice(prefix.length)}`;
}

export async function createSnapshotMetadata({
  repoRoot,
  portalRoot,
  version,
  channel,
  revision,
  facts,
  now = () => new Date(),
  expectedDocCount = 34,
  diagramIds = DIAGRAM_IDS,
  projectionPaths,
}) {
  validateVersion(version);
  const sourceCommit = await gitCommitEvidence(repoRoot, revision);
  const projection = await projectionManifest(repoRoot, revision, projectionPaths);
  const sourcePaths = await sourceDocumentPaths(repoRoot, revision);
  if (sourcePaths.length !== expectedDocCount) {
    throw new Error(`expected ${expectedDocCount} source documents, found ${sourcePaths.length}`);
  }
  const sourceDocuments = [];
  for (const sourcePath of sourcePaths) {
    const source = await revisionEvidence(repoRoot, revision, sourcePath);
    const snapshotPath = snapshotDocumentPath(sourcePath, version);
    const snapshot = await worktreeEvidence(portalRoot, snapshotPath, 'snapshot document');
    if (source.bytes !== snapshot.bytes || source.sha256 !== snapshot.sha256) {
      throw new Error(`snapshot document differs from source: ${snapshotPath}`);
    }
    sourceDocuments.push({
      source_path: sourcePath,
      snapshot_path: snapshotPath,
      bytes: source.bytes,
      sha256: source.sha256,
    });
  }
  const sourceSidebar = await revisionEvidence(repoRoot, revision, 'apps/architecture-portal/sidebars.ts');
  const snapshotSidebar = await worktreeEvidence(
    portalRoot,
    `versioned_sidebars/version-${version}-sidebars.json`,
    'snapshot sidebar',
  );
  const ids = validateDiagramIds(diagramIds);
  const assets = [];
  for (const id of ids) {
    for (const extension of ['html', 'svg']) {
      const sourcePath = `apps/architecture-portal/static/diagrams/${id}.${extension}`;
      const versionedPath = `static/versions/${version}/diagrams/${id}.${extension}`;
      const source = await revisionEvidence(repoRoot, revision, sourcePath);
      const versioned = await worktreeEvidence(portalRoot, versionedPath, 'versioned diagram asset');
      if (source.bytes !== versioned.bytes || source.sha256 !== versioned.sha256) {
        throw new Error(`versioned diagram differs from source: ${versionedPath}`);
      }
      assets.push({id, format: extension, source_path: sourcePath, versioned_path: versionedPath, bytes: source.bytes, sha256: source.sha256});
    }
  }
  if (facts.product?.version !== version || facts.revision !== revision || facts.channel !== channel) {
    throw new Error('snapshot facts do not match version, revision, and channel');
  }
  const frozenAt = now().toISOString();
  if (new Date(sourceCommit.committed_at_utc) > new Date(frozenAt)) {
    throw new Error('snapshot freeze time precedes source commit time');
  }
  return {
    ...facts,
    schema_version: 2,
    product_build: version,
    revision,
    source_commit: sourceCommit,
    source_projection: projection,
    source_documents: sourceDocuments,
    source_sidebar: sourceSidebar,
    snapshot_sidebar: snapshotSidebar,
    diagrams: {
      ids,
      asset_base: `/versions/${version}/diagrams`,
      assets,
    },
    frozen_at_utc: frozenAt,
  };
}

export async function readRepoFactsAtRevision({repoRoot, revision, treeRevision = revision, channel}) {
  validateRevision(revision);
  validateRevision(treeRevision);
  if (!await gitCommitExists(repoRoot, treeRevision)) throw new Error(`snapshot tree revision ${treeRevision} does not exist`);
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'portal-source-tree-'));
  try {
    const archive = path.join(temporary, 'source.tar');
    const extracted = path.join(temporary, 'source');
    await mkdir(extracted);
    await execGit(repoRoot, ['archive', '--format=tar', `--output=${archive}`, treeRevision]);
    await execFileAsync('tar', ['-xf', archive, '-C', extracted], {maxBuffer: 64 * 1024 * 1024});
    return await readRepoFacts({repoRoot: extracted, revision, channel});
  } finally {
    await rm(temporary, {recursive: true, force: true});
  }
}

function generatedBoundary(metadata) {
  const version = metadata.product_build;
  return [
    ...metadata.source_documents.map((entry) => `apps/architecture-portal/${entry.snapshot_path}`),
    `apps/architecture-portal/${metadata.snapshot_sidebar.path}`,
    ...metadata.diagrams.assets.map((entry) => `apps/architecture-portal/${entry.versioned_path}`),
    `apps/architecture-portal/versioned_metadata/version-${version}.json`,
    'apps/architecture-portal/versions.json',
  ].sort();
}

function immutablePaths(metadata) {
  return generatedBoundary(metadata).filter((relative) => relative !== 'apps/architecture-portal/versions.json');
}

async function resolveCurrentIntroducingCommit(repoRoot, headRevision, metadataPath) {
  validateRevision(headRevision);
  validateRelativePath(metadataPath);
  const headType = await execGit(repoRoot, ['cat-file', '-t', `${headRevision}:${metadataPath}`], {allowFailure: true});
  if (headType?.stdout.trim() !== 'blob') throw new Error('snapshot metadata path is absent at HEAD');

  const output = (await execGit(repoRoot, [
    'log', '--topo-order', '--format=%H', '--diff-filter=A', headRevision, '--', metadataPath,
  ])).stdout.trim();
  const candidates = output.split('\n').filter(Boolean);
  if (candidates.length === 0) throw new Error('snapshot metadata has no introducing commit');

  const introducing = candidates[0];
  if (!await execGit(repoRoot, ['merge-base', '--is-ancestor', introducing, headRevision], {allowFailure: true})) {
    throw new Error('snapshot introducing commit is not an ancestor of HEAD');
  }
  const introducingType = await execGit(repoRoot, ['cat-file', '-t', `${introducing}:${metadataPath}`], {allowFailure: true});
  if (introducingType?.stdout.trim() !== 'blob') throw new Error('snapshot introducing commit does not contain metadata');

  const ancestry = (await execGit(repoRoot, ['rev-list', '--parents', '-n', '1', introducing])).stdout.trim().split(/\s+/);
  if (ancestry.length !== 2) throw new Error('snapshot introducing commit must have exactly one parent');
  const parentType = await execGit(repoRoot, ['cat-file', '-t', `${ancestry[1]}:${metadataPath}`], {allowFailure: true});
  if (parentType) throw new Error('snapshot introducing commit parent already contains metadata');

  const deletion = (await execGit(repoRoot, [
    'log', '--format=%H', '--diff-filter=D', `${introducing}..${headRevision}`, '--', metadataPath,
  ])).stdout.trim();
  if (deletion) throw new Error('snapshot metadata lifecycle is not continuous through HEAD');
  return {introducing, parent: ancestry[1]};
}

async function dirtyPaths(repoRoot) {
  const stdout = (await execGit(repoRoot, ['status', '--porcelain=v1', '--untracked-files=all'])).stdout;
  return stdout.split('\n').filter(Boolean).map((line) => validateRelativePath(line.slice(3))).sort();
}

async function verifyEvidenceAtRevision(repoRoot, revision, expected, label, errors) {
  try {
    const actual = await revisionEvidence(repoRoot, revision, expected.path);
    if (!sameJson(actual, expected)) errors.push(`${label} hash or size does not match recorded source`);
  } catch (error) {
    errors.push(`${label} cannot be read from source revision: ${error.message}`);
  }
}

async function verifyEvidenceInWorktree(root, expected, label, errors) {
  try {
    const actual = await worktreeEvidence(root, expected.path, label);
    if (!sameJson(actual, {path: expected.path, bytes: expected.bytes, sha256: expected.sha256})) {
      errors.push(`${label} hash or size does not match metadata`);
    }
  } catch (error) {
    errors.push(error.message);
  }
}

function parseTimestamp(value, label, errors) {
  if (typeof value !== 'string') {
    errors.push(`${label} must be an ISO timestamp`);
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.valueOf()) || date.toISOString() !== value) {
    errors.push(`${label} must be an ISO timestamp`);
    return null;
  }
  return date;
}

export async function verifySnapshotProvenance({
  repoRoot,
  portalRoot,
  metadata,
  headRevision,
  expectedDocCount = 34,
  diagramIds = DIAGRAM_IDS,
  projectionPaths,
  readFactsAtRevision: factsReader = readRepoFactsAtRevision,
}) {
  const errors = [];
  if (metadata?.schema_version !== 2) return ['snapshot metadata schema_version must be 2'];
  const version = metadata.product_build;
  try { validateVersion(version); } catch (error) { return [error.message]; }
  try { validateRevision(headRevision); } catch (error) { return [error.message]; }
  try { validateRevision(metadata.revision); } catch (error) { return [error.message]; }

  const metadataPath = `apps/architecture-portal/versioned_metadata/version-${version}.json`;
  const postcommit = headRevision !== metadata.revision;
  let introducing;
  let parent;
  if (postcommit) {
    try {
      ({introducing, parent} = await resolveCurrentIntroducingCommit(repoRoot, headRevision, metadataPath));
    } catch (error) {
      errors.push(`snapshot introducing commit cannot be resolved: ${error.message}`);
      return errors;
    }
  }

  const sourceObjectExists = await gitCommitExists(repoRoot, metadata.revision);
  if (!sourceObjectExists && !postcommit) return [`snapshot revision ${metadata.revision} does not exist`];

  let recordedCommit;
  try {
    recordedCommit = authenticateRecordedCommit(metadata.revision, metadata.source_commit);
  } catch (error) {
    errors.push(sourceObjectExists ? error.message : `snapshot revision ${metadata.revision} does not exist and ${error.message}`);
    return errors;
  }
  if (sourceObjectExists) {
    try {
      const actualCommit = await gitCommitEvidence(repoRoot, metadata.revision);
      if (!sameJson(actualCommit, metadata.source_commit)) errors.push('raw commit bytes or source commit evidence do not match revision');
    } catch (error) {
      errors.push(error.message);
    }
  }
  const contentRevision = sourceObjectExists ? metadata.revision : introducing;

  const expectedIds = validateDiagramIds(diagramIds);
  if (!sameJson(metadata.diagrams?.ids, expectedIds)) errors.push('diagram id inventory does not match expected validated IDs');
  if (metadata.diagrams?.asset_base !== `/versions/${version}/diagrams`) errors.push('diagram asset base is invalid');
  if (!Array.isArray(metadata.source_documents) || metadata.source_documents.length !== expectedDocCount) {
    errors.push(`snapshot metadata must contain ${expectedDocCount} source documents`);
  }
  try {
    const expectedSources = await sourceDocumentPaths(repoRoot, contentRevision);
    const expectedInventory = expectedSources.map((sourcePath) => ({
      source_path: sourcePath,
      snapshot_path: snapshotDocumentPath(sourcePath, version),
    }));
    const actualInventory = (metadata.source_documents ?? []).map(({source_path, snapshot_path}) => ({source_path, snapshot_path}));
    if (!sameJson(actualInventory, expectedInventory)) errors.push('source document inventory does not match source revision');
  } catch (error) {
    errors.push(`source document inventory cannot be verified: ${error.message}`);
  }
  if (metadata.source_sidebar?.path !== 'apps/architecture-portal/sidebars.ts' ||
      metadata.snapshot_sidebar?.path !== `versioned_sidebars/version-${version}-sidebars.json`) {
    errors.push('source and snapshot sidebar inventory is invalid');
  }
  const expectedAssets = expectedIds.flatMap((id) => ['html', 'svg'].map((format) => ({
    id,
    format,
    source_path: `apps/architecture-portal/static/diagrams/${id}.${format}`,
    versioned_path: `static/versions/${version}/diagrams/${id}.${format}`,
  })));
  const actualAssets = (metadata.diagrams?.assets ?? []).map(({id, format, source_path, versioned_path}) => ({
    id, format, source_path, versioned_path,
  }));
  if (!sameJson(actualAssets, expectedAssets)) errors.push('diagram asset inventory does not match validated IDs');

  if (metadata.source_projection?.files) {
    try {
      const expectedProjectionPaths = projectionPaths
        ? [...projectionPaths].map(validateRelativePath).sort()
        : (await listRevisionPaths(repoRoot, contentRevision)).filter(isProjectionPath);
      const recordedProjectionPaths = metadata.source_projection.files.map((entry) => entry.path);
      if (!sameJson(recordedProjectionPaths, expectedProjectionPaths)) errors.push('source projection inventory is incomplete or unexpected');
      const actualProjection = await projectionManifest(
        repoRoot,
        contentRevision,
        metadata.source_projection.files.map((entry) => entry.path),
      );
      if (!sameJson(actualProjection, metadata.source_projection)) errors.push('source projection manifest does not match source revision');
    } catch (error) {
      errors.push(`source projection cannot be verified: ${error.message}`);
    }
  } else {
    errors.push('source projection manifest is missing');
  }

  for (const document of metadata.source_documents ?? []) {
    await verifyEvidenceAtRevision(repoRoot, contentRevision, {
      path: document.source_path, bytes: document.bytes, sha256: document.sha256,
    }, `source document ${document.source_path}`, errors);
    await verifyEvidenceInWorktree(portalRoot, {
      path: document.snapshot_path, bytes: document.bytes, sha256: document.sha256,
    }, `snapshot document ${document.snapshot_path}`, errors);
  }
  if (metadata.source_sidebar) await verifyEvidenceAtRevision(repoRoot, contentRevision, metadata.source_sidebar, 'source sidebar', errors);
  else errors.push('source sidebar evidence is missing');
  if (metadata.snapshot_sidebar) await verifyEvidenceInWorktree(portalRoot, metadata.snapshot_sidebar, 'snapshot sidebar', errors);
  else errors.push('snapshot sidebar evidence is missing');
  for (const asset of metadata.diagrams?.assets ?? []) {
    await verifyEvidenceAtRevision(repoRoot, contentRevision, {
      path: asset.source_path, bytes: asset.bytes, sha256: asset.sha256,
    }, `source diagram ${asset.source_path}`, errors);
    await verifyEvidenceInWorktree(portalRoot, {
      path: asset.versioned_path, bytes: asset.bytes, sha256: asset.sha256,
    }, `diagram asset ${asset.versioned_path}`, errors);
  }
  if ((metadata.diagrams?.assets?.length ?? 0) !== expectedIds.length * 2) {
    errors.push(`snapshot metadata must contain ${expectedIds.length * 2} diagram assets`);
  }

  try {
    const rebuiltFacts = await factsReader({
      repoRoot,
      revision: metadata.revision,
      treeRevision: contentRevision,
      channel: metadata.channel,
    });
    for (const field of ['product', 'channel', 'revision', 'assembly_lock_sha256', 'modules', 'hosts', 'providers', 'contracts']) {
      if (!sameJson(metadata[field], rebuiltFacts[field])) errors.push(`snapshot ${field} does not match source-rebuilt facts`);
    }
  } catch (error) {
    errors.push(`snapshot facts cannot be rebuilt from source revision: ${error.message}`);
  }

  try {
    const versions = JSON.parse(await readFile(path.join(portalRoot, 'versions.json'), 'utf8'));
    if (versions.filter((entry) => entry === version).length !== 1) errors.push(`Product Build ${version} must appear exactly once in versions.json`);
  } catch (error) {
    errors.push(`versions.json cannot be read: ${error.message}`);
  }

  const sourceTime = recordedCommit.committedAt;
  const freezeTime = parseTimestamp(metadata.frozen_at_utc, 'snapshot frozen_at_utc', errors);
  if (sourceTime && freezeTime && sourceTime > freezeTime) errors.push('snapshot timestamp order must satisfy source <= freeze');

  if (headRevision === metadata.revision) {
    try {
      const actualDirty = await dirtyPaths(repoRoot);
      const expectedDirty = generatedBoundary(metadata);
      if (!sameJson(actualDirty, expectedDirty)) errors.push('precommit dirty paths must equal the exact generated snapshot boundary');
    } catch (error) {
      errors.push(`precommit generated boundary cannot be verified: ${error.message}`);
    }
    return errors;
  }

  const immutableHistory = (await execGit(repoRoot, [
    'log', '--full-history', '--format=%H', `${introducing}..${headRevision}`, '--', ...immutablePaths(metadata),
  ])).stdout.trim();
  if (immutableHistory) {
    errors.push('generated immutable snapshot paths changed after introducing commit');
  }
  try {
    const immutable = new Set(immutablePaths(metadata));
    for (const dirty of await dirtyPaths(repoRoot)) {
      if (immutable.has(dirty)) errors.push(`immutable snapshot path is dirty in the working tree: ${dirty}`);
    }
  } catch (error) {
    errors.push(`immutable working-tree state cannot be verified: ${error.message}`);
  }
  const introducingTimeText = (await execGit(repoRoot, ['show', '-s', '--format=%cI', introducing])).stdout.trim();
  const introducingTime = new Date(introducingTimeText);
  if (freezeTime && (Number.isNaN(introducingTime.valueOf()) || freezeTime > introducingTime)) {
    errors.push('snapshot timestamp order must satisfy freeze <= introducing');
  }
  if (parent !== metadata.revision) {
    try {
      const introducingProjection = await projectionManifest(
        repoRoot,
        introducing,
        metadata.source_projection.files.map((entry) => entry.path),
      );
      if (!sameJson(introducingProjection, metadata.source_projection)) {
        errors.push('source projection is neither direct-parent nor squash-equivalent');
      }
    } catch {
      errors.push('source projection is neither direct-parent nor squash-equivalent');
    }
  }
  return errors;
}
