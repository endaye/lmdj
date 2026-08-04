import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const wrapper = path.join(repoRoot, 'scripts/architecture-portal.sh');

test('wrapper rejects an unsupported command with usage status', () => {
  const result = spawnSync(wrapper, ['unknown'], {encoding: 'utf8'});
  assert.equal(result.status, 64);
  assert.match(result.stderr, /usage:/);
});

test('portal package is private and pins the Node and npm toolchain', async () => {
  const manifest = (await import('../package.json', {with: {type: 'json'}})).default;
  assert.equal(manifest.private, true);
  assert.equal(manifest.engines.node, '>=22.13.0');
  assert.equal(manifest.packageManager, 'npm@10.9.3');
});
