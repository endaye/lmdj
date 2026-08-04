import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const executable = path.join(portalRoot, 'node_modules/.bin/netlify-build');
const args = [
  '--repositoryRoot', repoRoot,
  '--cwd', repoRoot,
  '--config', path.join(repoRoot, 'netlify.toml'),
  '--offline',
];

const code = await new Promise((resolve, reject) => {
  const child = spawn(executable, args, {cwd: portalRoot, stdio: 'inherit'});
  child.on('error', reject);
  child.on('exit', (exitCode, signal) => {
    if (signal) reject(new Error(`netlify build terminated by ${signal}`));
    else resolve(exitCode ?? 1);
  });
});
process.exitCode = code;
