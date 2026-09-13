import {createHash} from 'node:crypto';
import {load} from 'cheerio';
import matter from 'gray-matter';
import {evaluate} from '@mdx-js/mdx';
import * as runtime from 'react/jsx-runtime';
import {renderToStaticMarkup} from 'react-dom/server';

const PREFIX = 'apps/docs-site/docs/releases/';
const LIMIT = 8 * 1024 * 1024;
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const fail = (why) => {throw new Error(`why: release changelog smoke ${why}; remedy: reconcile the reviewed publication pages and Git-triggered site deployment`);};
const normalizeText = (text) => text.replace(/\s+/gu, ' ').trim();

function routeFor(page) {
  if (!page || typeof page.content !== 'string' || typeof page.file !== 'string'
    || !/^apps\/docs-site\/docs\/releases\/(index|(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3})\.mdx$/.test(page.file)) fail('source page is invalid');
  const name = page.file.slice(PREFIX.length, -4);
  return name === 'index' ? '/releases/' : `/releases/${name}/`;
}

function contentProjection(html, sourceUrl, sourceMdx = false) {
  const $ = load(html);
  const main = $('.theme-doc-markdown');
  if (main.length !== 1) fail('page has no unique rendered documentation content');
  const concealed = (element) => $(element).is('[hidden],[style]')
    || ($(element).attr('aria-hidden') ?? '').toLowerCase() === 'true';
  if (main.add(main.parents()).toArray().some(concealed)) fail('documentation container is explicitly hidden or styled');
  const allowed = new Set(['div', 'span', 'header', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'ul', 'ol', 'li', 'a', 'code', 'strong', 'em', 'br']);
  for (const element of main.find('*').add(main).toArray()) {
    if (!allowed.has(element.tagName) || concealed(element)
      || Object.keys(element.attribs ?? {}).some((key) => /^on/i.test(key))) fail('rendered notes contain hidden or executable content');
  }
  // Ignore only Docusaurus's direct heading anchor, never arbitrary content
  // carrying the same CSS class. Its target must name its own heading.
  for (const anchor of main.find('a.hash-link').toArray()) {
    const parent = $(anchor).parent();
    let target;
    try {target = decodeURIComponent($(anchor).attr('href') ?? '');} catch {fail('heading navigation target is invalid');}
    if (!/^h[1-6]$/.test(parent[0]?.tagName ?? '') || !parent.attr('id')
      || target !== '#' + parent.attr('id') || $(anchor).text() !== '\u200b'
      || $(anchor).children().length) fail('heading navigation contains non-navigation content');
    $(anchor).remove();
  }
  const links = main.find('a').toArray().map((element) => {
    const href = $(element).attr('href');
    if (!href) fail('rendered link has no target');
    let url;
    try {url = new URL(href, sourceUrl);} catch {fail('rendered link is invalid');}
    if (url.protocol !== 'https:' || url.username || url.password) fail('rendered link is unsafe');
    if (url.origin === sourceUrl.origin) {
      // Convert reviewed source filenames to rendered routes only on the
      // expected side. A live .mdx or /index target is not route evidence.
      if (sourceMdx) url.pathname = url.pathname.replace(/\.mdx$/, '').replace(/\/index$/, '');
      url.pathname = url.pathname.replace(/\/$/, '') || '/';
    }
    return [normalizeText($(element).text()), url.href];
  });
  const blocks = main.find('h1,h2,h3,h4,h5,h6,p,li').toArray()
    .map((element) => [element.tagName, normalizeText($(element).text())]);
  return {text: normalizeText(main.text()), blocks, links};
}

export async function expectedReleaseContent(page, baseUrl) {
  const route = routeFor(page);
  const sourceUrl = new URL('/releases/' + page.file.slice(PREFIX.length), baseUrl);
  // Only call with the bounded, validated Python generator's output, never
  // arbitrary remote MDX. The source is already the Release's shared renderer.
  const {default: Content} = await evaluate(matter(page.content).content, {...runtime});
  const html = renderToStaticMarkup(runtime.jsx('div', {className: 'theme-doc-markdown', children: runtime.jsx(Content, {})}));
  return {route, projection: contentProjection(html, sourceUrl, true), sourceUrl,
    source_sha256: hash(page.content)};
}

async function readHtml(url, fetchImpl) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetchImpl(url, {method: 'GET', redirect: 'manual', credentials: 'omit',
      headers: {'Accept': 'text/html', 'Cache-Control': 'no-cache'}, signal: controller.signal});
    if (response.status !== 200 || response.redirected) fail('route is missing or redirected');
    if (!/^text\/html(?:\s*;|$)/i.test(response.headers.get('content-type') ?? '')) fail('route is not HTML');
    const reader = response.body?.getReader();
    if (!reader) fail('route has no response body');
    const chunks = [];
    let length = 0;
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > LIMIT) {await reader.cancel(); fail('route exceeds the response size limit');}
      chunks.push(value);
    }
    const bytes = Buffer.concat(chunks);
    return {html: new TextDecoder('utf-8', {fatal: true}).decode(bytes), bytes};
  } finally {clearTimeout(timer); controller.abort();}
}

export async function smokeReleaseChangelogs({baseUrl, pages, fetchImpl = fetch}) {
  let base;
  try {base = new URL(baseUrl);} catch {fail('base URL is invalid');}
  if (base.protocol !== 'https:' || base.username || base.password || base.search || base.hash
    || base.pathname !== '/') fail('base must be an HTTPS origin without credentials');
  if (!Array.isArray(pages) || pages.length === 0) fail('source inventory is empty');
  const expected = await Promise.all(pages.map((page) => expectedReleaseContent(page, base)));
  if (!expected.some((page) => page.route === '/releases/')
    || new Set(expected.map((page) => page.route)).size !== expected.length) fail('source index is absent or pages are duplicated');
  const errors = [];
  const receipts = [];
  for (const page of expected) {
    try {
      const url = new URL(page.route, base).href;
      const {html, bytes} = await readHtml(url, fetchImpl);
      // Live links resolve from the served route, not the source MDX filename.
      const actual = contentProjection(html, new URL(page.route, base));
      if (JSON.stringify(actual) !== JSON.stringify(page.projection)) fail('rendered text, categories or links differ from frozen source');
      receipts.push({route: page.route, url, source_sha256: page.source_sha256,
        content_sha256: hash(JSON.stringify(actual)), response_sha256: hash(bytes), response_bytes: bytes.length});
    } catch {
      // Do not expose network errors, request headers or arbitrary response body.
      errors.push(`why: release changelog ${page.route} is unverified; remedy: reconcile its exact reviewed content and Git-triggered deployment`);
    }
  }
  return {errors, receipts};
}
