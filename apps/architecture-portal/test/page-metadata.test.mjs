import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import matter from 'gray-matter';
import {readFile} from 'node:fs/promises';
import {validatePageMetadata} from '../scripts/lib/page-metadata.mjs';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');

async function validateFixture(name) {
  const file = path.join(portalRoot, 'test/fixtures', name);
  const source = await readFile(file, 'utf8');
  const {data, content: body} = matter(source);
  return validatePageMetadata({
    file,
    data,
    body,
    repoRoot,
    activeContractIds: new Set(['lmdj.project.v1']),
  });
}

test('valid current page metadata passes', async () => {
  assert.deepEqual(await validateFixture('valid-page.md'), []);
});

test('retired contract language is isolated to history', async () => {
  assert.deepEqual(await validateFixture('retired-page.md'), []);
});

test('retired contract language is rejected from current pages', async () => {
  const errors = await validateFixture('invalid-current-page.md');
  assert.match(errors.join('\n'), /retired Contract leaked into current documentation/);
  assert.match(errors.join('\n'), /retired Contract ID lmdj\.capability\.v1/);
});
