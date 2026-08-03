import path from 'node:path';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {execFile, spawn} from 'node:child_process';
import {promisify} from 'node:util';
import {readRepoFacts} from './repo-facts.mjs';

const execFileAsync = promisify(execFile);

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
  const facts = options.facts ?? await readRepoFacts({
    repoRoot,
    revision,
    channel: process.env.PORTAL_CHANNEL || 'canary',
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

  await run('npm', ['run', 'check']);
  await run('npm', ['run', 'docusaurus', '--', 'docs:version', requestedVersion]);
  await writeMetadata(requestedVersion, {
    ...facts,
    product_build: requestedVersion,
    revision,
    frozen_at_utc: now().toISOString(),
  });
  await run('npm', ['run', 'check']);
}
