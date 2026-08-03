import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {freezeVersion} from './lib/version-docs.mjs';

const execFileAsync = promisify(execFile);
const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const requestedVersion = process.argv[2];
if (!requestedVersion || process.argv.length !== 3) {
  console.error('usage: node scripts/version-docs.mjs PRODUCT_BUILD');
  process.exit(64);
}
const {stdout} = await execFileAsync('git', ['rev-parse', 'HEAD'], {cwd: repoRoot});
const revision = stdout.trim();
await freezeVersion({portalRoot, repoRoot, requestedVersion, revision});
console.log(`portal version: froze ${requestedVersion} at ${revision}`);
