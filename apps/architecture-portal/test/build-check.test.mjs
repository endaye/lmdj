import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {checkBuild} from '../scripts/lib/build-check.mjs';

const fixtures = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'fixtures');

test('build checker accepts valid pretty routes, links, and identity', async () => {
  const errors = await checkBuild({
    buildRoot: path.join(fixtures, 'build-valid'),
    requiredRoutes: ['/', '/core/modules/foundation/'],
    expectedIdentity: {productBuild: '1.0.13.0', revision: 'abcdef1'},
  });
  assert.deepEqual(errors, []);
});

test('build checker reports missing routes, broken internal links, and identity drift', async () => {
  const errors = await checkBuild({
    buildRoot: path.join(fixtures, 'build-invalid'),
    requiredRoutes: ['/', '/core/modules/foundation/'],
    expectedIdentity: {productBuild: '1.0.13.0', revision: 'abcdef1'},
  });
  assert.deepEqual(errors, [
    'missing route /core/modules/foundation/',
    'broken internal link /missing/ from /index.html',
    'index identity does not contain Product Build 1.0.13.0',
  ]);
});

test('build checker rejects visible MDX container source', async () => {
  const errors = await checkBuild({
    buildRoot: path.join(fixtures, 'build-invalid-admonition'),
    requiredRoutes: ['/'],
    expectedIdentity: {productBuild: '1.0.13.0', revision: 'abcdef1'},
  });
  assert.deepEqual(errors, ['visible MDX directive :::warning in /index.html']);
});
