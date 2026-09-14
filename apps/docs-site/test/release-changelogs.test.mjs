import assert from 'node:assert/strict';
import test, {after} from 'node:test';
import {mkdtemp, mkdir, readFile, writeFile, symlink, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {execFile, spawn} from 'node:child_process';
import {once} from 'node:events';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {compile} from '@mdx-js/mdx';
import matter from 'gray-matter';
import {applyReleasePages} from '../scripts/lib/release-changelogs.mjs';

const prefix = 'apps/docs-site/docs/releases/';
const temporaryRoots = [];
after(async () => {for (const root of temporaryRoots) await rm(root, {recursive: true, force: true});});
const pages = [
  {file: prefix + 'index.mdx', content: 'index\n'},
  {file: prefix + '1.0.1.0.mdx', content: 'frozen version\n'},
];
async function fixture() {
  const root = await mkdtemp(path.join(tmpdir(), 'lmdj-release-site-'));
  temporaryRoots.push(root);
  await mkdir(path.join(root, 'apps/docs-site/docs'), {recursive: true});
  return root;
}

test('generation, check and repeated generation preserve version bytes', async () => {
  const root = await fixture();
  await applyReleasePages(root, pages, {check: false});
  await applyReleasePages(root, pages);
  await applyReleasePages(root, pages, {check: false});
  assert.equal(await readFile(path.join(root, pages[1].file), 'utf8'), pages[1].content);
});

test('new release appends page and updates index without changing old version', async () => {
  const root = await fixture();
  await applyReleasePages(root, pages, {check: false});
  const next = [{...pages[0], content: 'new index\n'}, pages[1],
    {file: prefix + '1.0.2.0.mdx', content: 'new frozen version\n'}];
  await applyReleasePages(root, next, {check: false});
  await applyReleasePages(root, next);
  assert.equal(await readFile(path.join(root, pages[1].file), 'utf8'), pages[1].content);
});

test('changed frozen page stops before even updating the index', async () => {
  const root = await fixture();
  await applyReleasePages(root, pages, {check: false});
  await assert.rejects(applyReleasePages(root, [
    {...pages[0], content: 'new index\n'}, {...pages[1], content: 'rewritten history\n'},
  ], {check: false}), /frozen version page would be overwritten/);
  assert.equal(await readFile(path.join(root, pages[0].file), 'utf8'), pages[0].content);
});

test('removed source record cannot silently remove its existing historical page', async () => {
  const root = await fixture();
  await applyReleasePages(root, pages, {check: false});
  await assert.rejects(applyReleasePages(root, [pages[0]], {check: false}), /historical page/);
  assert.equal(await readFile(path.join(root, pages[1].file), 'utf8'), pages[1].content);
});

test('invalid UTF-8 cannot impersonate a frozen replacement character', async () => {
  const root = await fixture();
  const unicodePages = [pages[0], {...pages[1], content: 'frozen \uFFFD version\n'}];
  await applyReleasePages(root, unicodePages, {check: false});
  await applyReleasePages(root, unicodePages);
  const target = path.join(root, pages[1].file);
  const corrupted = Buffer.concat([Buffer.from('frozen '), Buffer.from([0xff]), Buffer.from(' version\n')]);
  // The decoded strings coincide, but immutable page bytes must not.
  assert.equal(corrupted.toString('utf8'), unicodePages[1].content);
  await writeFile(target, corrupted);
  await assert.rejects(applyReleasePages(root, unicodePages), /stale/);
  await assert.rejects(applyReleasePages(root, unicodePages, {check: false}), /frozen version page would be overwritten/);
  assert.deepEqual(await readFile(target), corrupted);
  assert.equal(await readFile(path.join(root, pages[0].file), 'utf8'), pages[0].content);
});

test('check-only missing output performs no write', async () => {
  const root = await fixture();
  await assert.rejects(applyReleasePages(root, pages), /stale/);
  await assert.rejects(readFile(path.join(root, pages[0].file)), {code: 'ENOENT'});
});

test('escaping and duplicate page paths fail before writes', async () => {
  const root = await fixture();
  for (const invalid of [[...pages, {...pages[1]}], [{file: '../escape', content: 'x'}]]) {
    await assert.rejects(applyReleasePages(root, invalid, {check: false}), /identity/);
  }
});

test('symlink output cannot overwrite another file', async () => {
  const root = await fixture();
  await applyReleasePages(root, [pages[0]], {check: false});
  const outside = path.join(root, 'outside');
  await writeFile(outside, 'preserve\n');
  await symlink(outside, path.join(root, pages[1].file));
  await assert.rejects(applyReleasePages(root, pages, {check: false}), /unsafe/);
  assert.equal(await readFile(outside, 'utf8'), 'preserve\n');
});

test('actual Python version projection preserves common notes and compiles as MDX', async () => {
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
  const script = `
import json, sys
sys.path.insert(0, 'tests/build')
from release_changelog_site_test import ChangelogSiteTest
from tools.release.changelog import render
fixture = ChangelogSiteTest()
fixture.setUp()
print(json.dumps({'pages': fixture.project(), 'notes': render(fixture.document)}))
`;
  const {stdout} = await promisify(execFile)('python3', ['-c', script], {cwd: repoRoot});
  const {pages: generated, notes} = JSON.parse(stdout);
  const source = matter(generated[1].content);
  assert.equal(source.data.area, 'history');
  assert.ok(source.content.includes(notes));
  const compiled = await compile(source.content);
  assert.ok(String(compiled).length > 0);
});

for (const point of ['partial-page', 'before-index', 'after-index']) {
  test(`real process death at ${point} resumes without changing history`, async () => {
    const root = await fixture();
    await applyReleasePages(root, pages, {check: false});
    const next = [{...pages[0], content: 'new index\n'}, pages[1],
      {file: prefix + '1.0.2.0.mdx', content: 'new frozen version\n'}];
    const moduleUrl = new URL('../scripts/lib/release-changelogs.mjs', import.meta.url).href;
    // Instrument real filesystem calls in an isolated child, not production hooks.
    const script = `
      import fs from 'node:fs/promises';
      import {syncBuiltinESMExports} from 'node:module';
      const pause = async () => {setInterval(() => {}, 1000); process.send('at-boundary'); await new Promise(() => {});};
      const write = fs.writeFile, rename = fs.rename;
      fs.writeFile = async (file, content, options) => {
        if (${JSON.stringify(point)} === 'partial-page' && content === 'new frozen version\\n') {
          await write(file, content.slice(0, 5), options); await pause();
        }
        return write(file, content, options);
      };
      fs.rename = async (from, to) => {
        if (${JSON.stringify(point)} === 'before-index') await pause();
        const result = await rename(from, to);
        if (${JSON.stringify(point)} === 'after-index') await pause();
        return result;
      };
      syncBuiltinESMExports();
      const {applyReleasePages} = await import(${JSON.stringify(moduleUrl)});
      await applyReleasePages(${JSON.stringify(root)}, ${JSON.stringify(next)}, {check: false});
    `;
    const child = spawn(process.execPath, ['--input-type=module', '-e', script],
      {stdio: ['ignore', 'pipe', 'pipe', 'ipc']});
    const exited = once(child, 'exit');
    let errors = '';
    child.stderr.on('data', (data) => {errors += data;});
    const timeout = setTimeout(() => child.kill('SIGKILL'), 10000);
    try {
      const boundary = await Promise.race([
        once(child, 'message').then(([message]) => message),
        exited.then(() => {throw new Error(`child exited before crash boundary: ${errors}`);}),
      ]);
      assert.equal(boundary, 'at-boundary');
      child.kill('SIGKILL');
      const [, signal] = await exited;
      assert.equal(signal, 'SIGKILL');
    } finally {clearTimeout(timeout); child.kill('SIGKILL');}
    assert.equal(await readFile(path.join(root, pages[1].file), 'utf8'), pages[1].content);
    if (point === 'partial-page') await assert.rejects(readFile(path.join(root, next[2].file)), {code: 'ENOENT'});
    else assert.equal(await readFile(path.join(root, next[2].file), 'utf8'), next[2].content);
    assert.equal(await readFile(path.join(root, pages[0].file), 'utf8'),
      point === 'after-index' ? next[0].content : pages[0].content);
    await applyReleasePages(root, next, {check: false});
    await applyReleasePages(root, next);
    for (const page of next) assert.deepEqual(await readFile(path.join(root, page.file)), Buffer.from(page.content));
  });
}
