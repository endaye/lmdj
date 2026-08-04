import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {mkdtemp, mkdir, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
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

async function writeRenderedPage(root, route, body) {
  const relative = route.replace(/^\/+|\/+$/g, '');
  const file = !route.endsWith('/') && path.extname(relative)
    ? path.join(root, relative)
    : path.join(root, relative, 'index.html');
  await mkdir(path.dirname(file), {recursive: true});
  await writeFile(file, `<!doctype html><html><body>${body}</body></html>`);
}

test('build checker parses rendered current and versioned home cards in their active version scope', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'portal-build-scope-'));
  try {
    await writeRenderedPage(root, '/', '<a class="section-card" href="/product/positioning/">Product</a> Product Build 1.0.13.0 abcdef1');
    await writeRenderedPage(root, '/product/positioning/', 'Product');
    await writeRenderedPage(root, '/versions/1.0.13.0/', '<a class="section-card" href="/versions/1.0.13.0/product/positioning/">Product</a>');
    await writeRenderedPage(root, '/versions/1.0.13.0/product/positioning/', 'Product');

    const errors = await checkBuild({
      buildRoot: root,
      requiredRoutes: ['/'],
      expectedIdentity: {productBuild: '1.0.13.0', revision: 'abcdef1'},
      versionSchemas: {'1.0.13.0': 1},
    });
    assert.deepEqual(errors, []);
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});

test('build checker rejects rendered home cards that escape current or versioned scope and mutable schema-2 diagrams', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'portal-build-escape-'));
  try {
    await writeRenderedPage(root, '/', '<a class="section-card" href="/versions/1.0.14.0/product/positioning/">Product</a> Product Build 1.0.14.0 abcdef1');
    await writeRenderedPage(root, '/versions/1.0.14.0/product/positioning/', 'Product');
    await writeRenderedPage(root, '/versions/1.0.14.0/', '<a class="section-card" href="/product/positioning/">Product</a><iframe src="/diagrams/lmdj-product.html"></iframe>');
    await writeRenderedPage(root, '/product/positioning/', 'Product');
    await writeRenderedPage(root, '/diagrams/lmdj-product.html', 'Diagram');

    const errors = await checkBuild({
      buildRoot: root,
      requiredRoutes: ['/'],
      expectedIdentity: {productBuild: '1.0.14.0', revision: 'abcdef1'},
      versionSchemas: {'1.0.14.0': 2},
    });
    assert.deepEqual(errors, [
      'current home section card escapes current scope: /versions/1.0.14.0/product/positioning/',
      'version 1.0.14.0 home section card escapes version scope: /product/positioning/',
      'schema-2 version 1.0.14.0 uses mutable diagram /diagrams/lmdj-product.html from /versions/1.0.14.0/index.html',
    ]);
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});

test('build checker requires the rendered homepage for every metadata version', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'portal-build-version-home-'));
  try {
    await writeRenderedPage(root, '/', 'Product Build 1.0.14.0 abcdef1');
    const errors = await checkBuild({
      buildRoot: root,
      requiredRoutes: ['/'],
      expectedIdentity: {productBuild: '1.0.14.0', revision: 'abcdef1'},
      versionSchemas: {'1.0.14.0': 2},
    });
    assert.deepEqual(errors, ['missing rendered version home /versions/1.0.14.0/']);
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});
