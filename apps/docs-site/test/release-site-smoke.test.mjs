import assert from 'node:assert/strict';
import test from 'node:test';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {evaluate} from '@mdx-js/mdx';
import * as runtime from 'react/jsx-runtime';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from 'cheerio';
import matter from 'gray-matter';
import {createServer} from 'node:http';
import {smokeReleaseChangelogs} from '../scripts/lib/release-site-smoke.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const {stdout} = await promisify(execFile)('python3', ['-c', `
import json,sys
sys.path.insert(0,'tests/build')
from release_changelog_site_test import ChangelogSiteTest
fixture=ChangelogSiteTest(); fixture.setUp()
print(json.dumps(fixture.project()))
`], {cwd: repoRoot});
const pages = JSON.parse(stdout);
const baseUrl = 'https://docs.lmdj.workers.dev';
const documents = new Map();
for (const page of pages) {
  const filename = path.basename(page.file);
  const route = filename === 'index.mdx' ? '/releases/' : '/releases/' + filename.slice(0, -4) + '/';
  const {default: Content} = await evaluate(matter(page.content).content, {...runtime});
  const $ = load(renderToStaticMarkup(runtime.jsx('div', {className: 'theme-doc-markdown', children: runtime.jsx(Content, {})})));
  for (const link of $('a').toArray()) {
    const href = $(link).attr('href');
    if (href.endsWith('.mdx')) {
      const url = new URL(href, baseUrl + '/releases/' + filename);
      $(link).attr('href', url.pathname.replace(/\.mdx$/, '').replace(/\/index$/, ''));
    }
  }
  $('h1').wrap('<header>');
  $('h2').each((index, heading) => {
    $(heading).attr('id', `heading-${index}`).append(`<a class="hash-link" href="#heading-${index}">​</a>`);
  });
  documents.set(route, $.html());
}
const response = (html, status = 200, type = 'text/html; charset=utf-8') => new Response(html, {status, headers: {'Content-Type': type}});
const fakeFetch = async (url) => response(documents.get(new URL(url).pathname));
const verify = (fetchImpl = fakeFetch, selectedPages = pages) => smokeReleaseChangelogs({baseUrl, pages: selectedPages, fetchImpl});

test('Python frozen page → rendered categories and links → HTTP receipts', async () => {
  const calls = [];
  const observed = await verify(async (url, options) => {
    calls.push([url, options]);
    return fakeFetch(url);
  });
  assert.deepEqual(observed.errors, []);
  assert.equal(observed.receipts.length, 2);
  for (const item of observed.receipts) {
    assert.match(item.source_sha256, /^[a-f0-9]{64}$/);
    assert.match(item.content_sha256, /^[a-f0-9]{64}$/);
    assert.match(item.response_sha256, /^[a-f0-9]{64}$/);
    assert.ok(item.response_bytes > 0);
  }
  assert.deepEqual(calls.map(([url]) => new URL(url).pathname), ['/releases/', '/releases/1.0.1.0/']);
  for (const [, options] of calls) {
    assert.equal(options.method, 'GET');
    assert.equal(options.redirect, 'manual');
    assert.equal(options.credentials, 'omit');
    assert.ok(options.signal instanceof AbortSignal);
  }
});

test('body change with all original digest labels retained cannot pass', async () => {
  const result = await verify(async (url) => response(documents.get(new URL(url).pathname).replace('修复 fixture', 'Invented feature')));
  assert.equal(result.errors.length, 1);
  assert.equal(result.receipts.length, 1);
});

test('each release identity and link is independently required', async () => {
  const faults = [
    ['lmdj-v1.0.1.0', 'lmdj-v1.0.2.0'], ['a'.repeat(40), 'f'.repeat(40)],
    ['2026-09-13', '2026-09-14'], ['Release ID: 123', 'Release ID: 124'],
    ['b'.repeat(64), 'e'.repeat(64)],
    ['https://github.com/endaye/lmdj/releases/tag/', 'https://github.com/other/lmdj/releases/tag/'],
    ['https://github.com/endaye/lmdj/commit/', 'https://github.com/other/lmdj/commit/'],
  ];
  for (const [before, after] of faults) {
    const result = await verify(async (url) => response(documents.get(new URL(url).pathname).replaceAll(before, after)));
    assert.ok(result.errors.length > 0, `fault ${before} must be rejected`);
  }
});

test('heading category structure cannot be replaced with the same text paragraph', async () => {
  const result = await verify(async (url) => response(documents.get(new URL(url).pathname).replaceAll('<h2>', '<p>').replaceAll('</h2>', '</p>')));
  assert.equal(result.errors.length, 1);
});

test('extra text outside a paragraph cannot evade the comparison', async () => {
  const result = await verify(async (url) => response(documents.get(new URL(url).pathname).replace('</div>', 'unreviewed claim</div>')));
  assert.equal(result.errors.length, 2);
});

test('missing or duplicate markdown containers cannot pass', async () => {
  for (const mutate of [(html) => html.replace('theme-doc-markdown', 'wrong'), (html) => html + '<div class="theme-doc-markdown"></div>']) {
    const result = await verify(async (url) => response(mutate(documents.get(new URL(url).pathname))));
    assert.equal(result.errors.length, 2);
  }
});

test('hidden or executable notes cannot pass', async () => {
  for (const extra of ['<script>0</script>', '<p hidden>hidden</p>', '<p style="display:none">hidden</p>']) {
    const result = await verify(async (url) => response(documents.get(new URL(url).pathname).replace('</div>', extra + '</div>')));
    assert.equal(result.errors.length, 2);
  }
});

test('hash-link class cannot hide an added claim or external link from comparison', async () => {
  const extra = '<a class="hash-link" href="https://evil.invalid">Unreviewed visible claim</a>';
  const result = await verify(async (url) => response(documents.get(new URL(url).pathname).replace('</div>', extra + '</div>')));
  assert.equal(result.errors.length, 2);
});

test('documentation root and ancestors cannot be explicitly hidden', async () => {
  for (const mutate of [
    (html) => html.replace('class="theme-doc-markdown"', 'class="theme-doc-markdown" hidden'),
    (html) => html.replace('<body>', '<body style="display:none">'),
    (html) => html.replace('class="theme-doc-markdown"', 'class="theme-doc-markdown" aria-hidden="true"'),
    (html) => html.replace('class="theme-doc-markdown"', 'class="theme-doc-markdown" aria-hidden="TRUE"'),
  ]) {
    const result = await verify(async (url) => response(mutate(documents.get(new URL(url).pathname))));
    assert.equal(result.errors.length, 2);
  }
});

test('heading navigation with the wrong fragment cannot be ignored', async () => {
  const result = await verify(async (url) => response(documents.get(new URL(url).pathname).replaceAll('href="#heading-0"', 'href="#different"')));
  assert.equal(result.errors.length, 1);
});

test('redirects, missing routes and non-HTML are unverified', async () => {
  for (const [status, type] of [[302, 'text/html'], [404, 'text/html'], [200, 'application/json']]) {
    const result = await verify(async (url) => response(documents.get(new URL(url).pathname), status, type));
    assert.equal(result.errors.length, 2);
    assert.deepEqual(result.receipts, []);
  }
});

test('transport exceptions never expose secret-like error text', async () => {
  const result = await verify(async () => {throw new Error('secret-transport-token');});
  assert.equal(result.errors.length, 2);
  assert.ok(!JSON.stringify(result).includes('secret-transport-token'));
});

test('oversize and malformed UTF-8 responses are unverified', async () => {
  for (const body of ['x'.repeat(8 * 1024 * 1024 + 1), new Uint8Array([255])]) {
    const result = await verify(async () => response(body));
    assert.equal(result.errors.length, 2);
  }
});

test('HTTPS origin and complete unique source inventory are required before GET', async () => {
  let calls = 0;
  const fetchImpl = async () => {calls++; throw new Error('must not fetch');};
  for (const invalid of ['http://docs.invalid', 'https://user:pass@docs.invalid', 'https://docs.invalid/path', 'https://docs.invalid/?q=x']) {
    await assert.rejects(smokeReleaseChangelogs({baseUrl: invalid, pages, fetchImpl}), /HTTPS origin/);
  }
  for (const invalid of [[], [pages[1]], [pages[0], pages[0]], [{file: '../escape', content: 'x'}]]) {
    await assert.rejects(smokeReleaseChangelogs({baseUrl, pages: invalid, fetchImpl}), /why:/);
  }
  assert.equal(calls, 0);
});

test('real HTTP response stream is read and failed-site recovery repeats only GET', async () => {
  let damaged = true;
  const methods = [];
  const server = createServer((request, reply) => {
    methods.push(request.method);
    reply.writeHead(200, {'Content-Type': 'text/html'});
    reply.end(damaged ? '<html>not deployed</html>' : documents.get(request.url));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    // Local transport fixture only: the production caller still requires HTTPS.
    const fetchImpl = (url, options) => fetch(`http://127.0.0.1:${server.address().port}${new URL(url).pathname}`, options);
    assert.equal((await verify(fetchImpl)).errors.length, 2);
    damaged = false;
    const recovered = await verify(fetchImpl);
    assert.deepEqual(recovered.errors, []);
    assert.equal(recovered.receipts.length, 2);
    assert.deepEqual(methods, ['GET', 'GET', 'GET', 'GET']);
  } finally {await new Promise((resolve) => server.close(resolve));}
});
