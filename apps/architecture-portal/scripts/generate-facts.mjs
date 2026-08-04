import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {readRepoFacts} from './lib/repo-facts.mjs';
import {glob} from 'glob';

const execFileAsync = promisify(execFile);
const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');

async function currentRevision() {
  if (process.env.PORTAL_REVISION) return process.env.PORTAL_REVISION;
  const {stdout} = await execFileAsync('git', ['rev-parse', 'HEAD'], {cwd: repoRoot});
  return stdout.trim();
}

const facts = await readRepoFacts({
  repoRoot,
  revision: await currentRevision(),
  channel: process.env.PORTAL_CHANNEL || 'canary',
});
const output = path.join(portalRoot, 'src/generated/site-facts.json');
await mkdir(path.dirname(output), {recursive: true});
await writeFile(output, `${JSON.stringify(facts, null, 2)}\n`, 'utf8');
const versionFacts = {};
const metadataFiles = await glob('versioned_metadata/version-*.json', {cwd: portalRoot, absolute: true});
for (const file of metadataFiles.sort()) {
  const metadata = JSON.parse(await readFile(file, 'utf8'));
  versionFacts[metadata.product_build] = metadata;
}
await writeFile(
  path.join(portalRoot, 'src/generated/version-facts.json'),
  `${JSON.stringify(versionFacts, null, 2)}\n`,
  'utf8',
);
console.log(`portal facts: ${facts.product.version} ${facts.revision}`);
