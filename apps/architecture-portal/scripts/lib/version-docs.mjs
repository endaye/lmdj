import path from 'node:path';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {execFile, spawn} from 'node:child_process';
import {promisify} from 'node:util';
import {readRepoFacts} from './repo-facts.mjs';

const execFileAsync = promisify(execFile);
const RELEASE_CHANNELS = new Set(['canary', 'dev', 'beta', 'stable']);

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function isIsoTimestamp(value) {
  if (typeof value !== 'string') return false;
  const parsed = new Date(value);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString() === value;
}

export function validateReleaseSnapshot({facts, versions, metadata, snapshotExists}) {
  const productBuild = facts.product.version;
  const errors = [];
  if (!versions.includes(productBuild)) {
    errors.push(`Product Build ${productBuild} is missing from versions.json`);
  }
  if (!snapshotExists) errors.push(`Product Build ${productBuild} snapshot source is missing`);
  if (!metadata) {
    errors.push(`Product Build ${productBuild} metadata is missing`);
    return errors;
  }
  if (metadata.product_build !== productBuild) {
    errors.push(`snapshot product_build does not match ${productBuild}`);
  }
  if (!sameJson(metadata.product, facts.product)) {
    errors.push('snapshot product identity does not match repository truth');
  }
  if (metadata.assembly_lock_sha256 !== facts.assembly_lock_sha256) {
    errors.push('snapshot Assembly Lock does not match repository truth');
  }
  for (const field of ['modules', 'hosts', 'providers', 'contracts']) {
    if (!sameJson(metadata[field], facts[field])) {
      errors.push(`snapshot ${field} do not match repository truth`);
    }
  }
  if (!RELEASE_CHANNELS.has(metadata.channel)) {
    errors.push('snapshot channel must be canary, dev, beta, or stable');
  }
  if (typeof metadata.revision !== 'string' || !/^[0-9a-f]{40}$/.test(metadata.revision)) {
    errors.push('snapshot revision must be a full Git SHA');
  }
  if (!isIsoTimestamp(metadata.frozen_at_utc)) {
    errors.push('snapshot frozen_at_utc must be an ISO timestamp');
  }
  return errors;
}

async function defaultGitStatus(repoRoot) {
  const {stdout} = await execFileAsync('git', ['status', '--porcelain'], {cwd: repoRoot});
  return stdout;
}

async function defaultReadVersions(portalRoot) {
  try {
    return JSON.parse(await readFile(path.join(portalRoot, 'versions.json'), 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
}

async function defaultRun(portalRoot, command, args) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {cwd: portalRoot, stdio: 'inherit'});
    child.on('error', reject);
    child.on('exit', (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${args.join(' ')} failed (${signal ?? code})`));
    });
  });
}

async function defaultWriteMetadata(portalRoot, version, metadata) {
  const directory = path.join(portalRoot, 'versioned_metadata');
  await mkdir(directory, {recursive: true});
  await writeFile(path.join(directory, `version-${version}.json`), `${JSON.stringify(metadata, null, 2)}\n`, 'utf8');
}

export async function freezeVersion(options) {
  const {
    portalRoot,
    repoRoot,
    requestedVersion,
    revision,
    now = () => new Date(),
  } = options;
  if (!/^\d+\.\d+\.\d+\.\d+$/.test(requestedVersion)) {
    throw new Error('documentation version must be a four-part Product Build');
  }
  const channel = options.channel ?? options.facts?.channel ?? process.env.PORTAL_CHANNEL ?? 'canary';
  if (!RELEASE_CHANNELS.has(channel)) {
    throw new Error('documentation channel must be canary, dev, beta, or stable');
  }
  const facts = options.facts ?? await readRepoFacts({
    repoRoot,
    revision,
    channel,
  });
  if (requestedVersion !== facts.product.version) {
    throw new Error(`requested Product Build ${requestedVersion} does not match ${facts.product.version}`);
  }
  const getGitStatus = options.getGitStatus ?? (() => defaultGitStatus(repoRoot));
  if ((await getGitStatus()).trim()) throw new Error('version freezing requires a clean worktree');
  const readVersions = options.readVersions ?? (() => defaultReadVersions(portalRoot));
  if ((await readVersions()).includes(requestedVersion)) {
    throw new Error(`documentation version ${requestedVersion} already exists`);
  }
  const run = options.run ?? ((command, args) => defaultRun(portalRoot, command, args));
  const writeMetadata = options.writeMetadata ?? ((version, metadata) => defaultWriteMetadata(portalRoot, version, metadata));

  await run('npm', ['run', 'check:current']);
  await run('npm', ['run', 'docusaurus', '--', 'docs:version', requestedVersion]);
  await writeMetadata(requestedVersion, {
    ...facts,
    product_build: requestedVersion,
    revision,
    frozen_at_utc: now().toISOString(),
  });
  await run('npm', ['run', 'check']);
}
