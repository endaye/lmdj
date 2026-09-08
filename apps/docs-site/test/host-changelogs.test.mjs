import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtemp, mkdir, readFile, rm, symlink, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import {evaluate} from '@mdx-js/mdx';
import * as jsxRuntime from 'react/jsx-runtime';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import matter from 'gray-matter';
import {canonical, parseChangelog, projectChangelogs, renderChangelog} from '../scripts/lib/host-changelogs.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const seal = (value) => ({...value, digest: createHash('sha256').update(canonical(value)).digest('hex')});
const rawEntry = (changes = {}) => ({schema: 'lmdj.host-changelog-entry.v1', host: 'creator-web',
  version: '8.2.1', prepared_date: '2026-09-09', base_sha: 'a'.repeat(40), target_sha: 'b'.repeat(40),
  input_digest: 'c'.repeat(64), assessment_digest: 'd'.repeat(64), impact: 'patch',
  rationale: '修复 shared Core <script>{throw 1}</script> 😀', references: ['b'.repeat(40)],
  dependency_effects: ['Shared Core → both Hosts'],
  changes: [{kind: 'fixed', text: '文字 & <Component /> {process.env.SECRET}', references: ['b'.repeat(40)]}],
  ...changes});
const log = (entry) => `# changelog\n\n## ${entry.version}\n\n<!-- lmdj-host-changelog:v1 ${Buffer.from(canonical(entry)).toString('base64')} -->\n`;
const bad = /why: Host changelog .*; remedy:/;

test('Python preparation bytes including non-ASCII and supplementary characters are consumed exactly', () => {
  const script = `import json, sys\nfrom tools.canary import preparation as p, records as r\nentry = r.seal(json.loads(sys.stdin.read()))\nprint(p._changelog(None, entry), end='')`;
  const source = execFileSync('python3', ['-c', script], {cwd: repoRoot,
    env: {...process.env, PYTHONPATH: path.join(repoRoot, 'scripts/ci')},
    input: JSON.stringify(rawEntry()), encoding: 'utf8'});
  assert.deepEqual(parseChangelog(source, 'creator-web', '8.2.1'), [seal(rawEntry())]);
});

test('newest entries render first without rewriting or inventing omitted changes', () => {
  const old = seal(rawEntry()), next = seal(rawEntry({version: '8.3.0', impact: 'minor'}));
  const entries = parseChangelog(log(old) + log(next), 'creator-web', '8.3.0');
  assert.deepEqual(entries.map((entry) => entry.version), ['8.3.0', '8.2.1']);
  const page = renderChangelog({id: 'creator-web', title: 'Creator', manifestVersion: '8.3.0', entries, hasSource: true});
  assert.ok(page.indexOf('## 8.3.0') < page.indexOf('## 8.2.1'));
  assert.ok(!page.includes('reverted feature'));
  assert.match(page, /Shared Core &#8594; both Hosts/);
  assert.match(page, new RegExp(`https://github.com/endaye/lmdj/commit/${'b'.repeat(40)}`));
});

test('prepared records render text rather than executable MDX and cannot claim receipt states', () => {
  const page = renderChangelog({id: 'creator-web', title: 'Creator', manifestVersion: '8.2.1', entries: [seal(rawEntry())], hasSource: true});
  assert.ok(!page.includes('<script>') && !page.includes('<Component') && !page.includes('{process.env'));
  assert.match(page, /&#60;script&#62;/);
  assert.match(page, /State: \*\*prepared\*\*/);
  assert.match(page, /Publication \/ deployment \/ promotion: \*\*未接入认证回执，状态未知\*\*/);
});

test('empty and populated generated pages compile as MDX without evaluating model prose', async () => {
  for (const entries of [[], [seal(rawEntry())]]) {
    const page = renderChangelog({id: 'creator-web', title: 'Creator', manifestVersion: '8.2.1', entries, hasSource: entries.length > 0});
    const {default: Page} = await evaluate(matter(page).content, jsxRuntime);
    const html = renderToStaticMarkup(createElement(Page));
    assert.ok(!html.includes('<script') && !html.includes('<Component'));
    if (entries.length) {
      assert.ok(html.includes('&lt;script&gt;{throw 1}&lt;/script&gt;'));
      assert.ok(html.includes('{process.env.SECRET}'));
    }
  }
});

for (const [name, mutate] of Object.entries({
  'foreign Host': (entry) => { entry.host = 'web-runtime-host'; },
  'foreign schema': (entry) => { entry.schema = 'other'; },
  'future version': (entry) => { entry.version = '9.0.0'; },
  'invalid version': (entry) => { entry.version = '08.2.1'; },
  'nonexistent date': (entry) => { entry.prepared_date = '2026-02-30'; },
  'zero year': (entry) => { entry.prepared_date = '0000-01-01'; },
  'missing change': (entry) => { entry.changes = []; },
  'unknown field claiming deployment': (entry) => { entry.deployed = 'yes'; },
  'invented commit URL': (entry) => { entry.references = ['https://invalid.test/']; },
  'duplicate reference': (entry) => { entry.references.push(entry.references[0]); },
  'unknown change kind': (entry) => { entry.changes[0].kind = 'deployed'; },
  'major impact': (entry) => { entry.impact = 'major'; },
  'oversized rationale': (entry) => { entry.rationale = 'a'.repeat(4001); },
})) {
  test(`rejects ${name} even with a recomputed integrity digest`, () => {
    const entry = rawEntry(); mutate(entry);
    assert.throws(() => parseChangelog(log(seal(entry)), 'creator-web', '8.2.1'), bad);
  });
}

test('digest tampering fails before presentation', () => {
  const entry = seal(rawEntry()); entry.rationale = 'tampered';
  assert.throws(() => parseChangelog(log(entry), 'creator-web', '8.2.1'), /entry digest differs; remedy:/);
});

test('rejects duplicate headings and machine records, noncanonical and truncated encodings', () => {
  const entry = seal(rawEntry()), valid = log(entry);
  for (const source of [valid + valid, valid.replace('## 8.2.1', '## 8.2.0'),
    valid.replace('## 8.2.1', '## 8.2.1\n\n## unrelated section'),
    valid + valid.slice(valid.indexOf('<!--')), valid.replace(' -->', ''),
    valid.replace('v1 ', 'v2 '), valid.replace('v1 ', 'v1 !'),
    valid.replace(Buffer.from(canonical(entry)).toString('base64'), Buffer.from(JSON.stringify(entry)).toString('base64'))]) {
    assert.throws(() => parseChangelog(source, 'creator-web', '8.2.1'), bad);
  }
});

test('legacy prose is not interpreted as a structured release or executable content', () => {
  assert.deepEqual(parseChangelog('# legacy\n<script>evil</script>\n## 7.0.0\nPublished!', 'creator-web', '8.2.1'), []);
});

test('machine entries cannot move backwards in append order', () => {
  const source = log(seal(rawEntry({version: '8.3.0'}))) + log(seal(rawEntry()));
  assert.throws(() => parseChangelog(source, 'creator-web', '8.3.0'), /not append-ordered; remedy:/);
});

async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'lmdj-host-changelog-test-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  for (const [host, version] of [['creator-web', '8.2.1'], ['web-runtime-host', '2.9.0']]) {
    await mkdir(path.join(root, 'apps', host), {recursive: true});
    await writeFile(path.join(root, 'apps', host, 'module.json'), JSON.stringify({contract: 'lmdj.module.v1', module: host, version}));
  }
  await mkdir(path.join(root, 'apps/docs-site/docs/operations'), {recursive: true});
  return root;
}

test('independent manifest versions and absent logs generate honest empty pages and pass read-only check', async (t) => {
  const root = await fixture(t);
  const pages = await projectChangelogs(root, {check: false});
  assert.match(pages[0].content, /manifest version: `8.2.1`/);
  assert.match(pages[1].content, /manifest version: `2.9.0`/);
  assert.ok(pages.every(({content}) => content.includes('暂无结构化 prepared 记录')));
  assert.deepEqual(await projectChangelogs(root), pages);
});

test('stale check does not write; explicit regeneration changes only current affected Host page', async (t) => {
  const root = await fixture(t);
  const pages = await projectChangelogs(root, {check: false});
  const snapshot = path.join(root, 'apps/docs-site/versioned_docs/version-9.8.7.6');
  await mkdir(snapshot, {recursive: true});
  await writeFile(path.join(snapshot, 'creator-changelog.mdx'), pages[0].content);
  await writeFile(path.join(root, 'apps/creator-web/CHANGELOG.md'), log(seal(rawEntry())));
  await assert.rejects(projectChangelogs(root), /projection is stale.*; remedy:/);
  assert.equal(await readFile(pages[0].file, 'utf8'), pages[0].content);
  const generated = await projectChangelogs(root, {check: false});
  assert.notEqual(generated[0].content, pages[0].content);
  assert.equal(generated[1].content, pages[1].content);
  assert.equal(await readFile(path.join(snapshot, 'creator-changelog.mdx'), 'utf8'), pages[0].content);
  assert.deepEqual(await projectChangelogs(root), generated);
});

test('existing symlink log is not mistaken for missing history', async (t) => {
  const root = await fixture(t);
  await symlink('module.json', path.join(root, 'apps/creator-web/CHANGELOG.md'));
  await assert.rejects(projectChangelogs(root, {check: false}), /source is not a bounded regular file.*; remedy:/);
});

test('invalid second Host prevents any generated-page writes', async (t) => {
  const root = await fixture(t);
  const pages = await projectChangelogs(root, {check: false});
  await writeFile(path.join(root, 'apps/creator-web/CHANGELOG.md'), log(seal(rawEntry())));
  await writeFile(path.join(root, 'apps/web-runtime-host/CHANGELOG.md'), 'lmdj-host-changelog:broken');
  await assert.rejects(projectChangelogs(root, {check: false}), bad);
  assert.equal(await readFile(pages[0].file, 'utf8'), pages[0].content);
});

test('a null manifest reports its identity failure with a remedy', async (t) => {
  const root = await fixture(t);
  await writeFile(path.join(root, 'apps/creator-web/module.json'), 'null');
  await assert.rejects(projectChangelogs(root), /manifest Host identity differs; remedy:/);
});
