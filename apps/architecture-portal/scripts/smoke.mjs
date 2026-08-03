import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {readRepoFacts} from './lib/repo-facts.mjs';
import {smokePortal} from './lib/smoke.mjs';

const baseUrl = process.argv[2];
if (!baseUrl || process.argv.length !== 3) {
  console.error('usage: node scripts/smoke.mjs BASE_URL');
  process.exit(64);
}
const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const execFileAsync = promisify(execFile);
const revision = process.env.PORTAL_REVISION || (await execFileAsync('git', ['rev-parse', 'HEAD'], {cwd: repoRoot})).stdout.trim();
const facts = await readRepoFacts({repoRoot, revision, channel: 'production'});
const errors = await smokePortal({
  baseUrl,
  productBuild: facts.product.version,
  revision: revision.slice(0, 12),
});
if (errors.length) {
  for (const error of errors.sort()) console.error(`portal smoke error: ${error}`);
  process.exitCode = 1;
} else {
  console.log(`portal smoke: ${baseUrl} serves ${facts.product.version} ${revision.slice(0, 12)}`);
}
