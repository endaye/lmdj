import {load} from 'cheerio';

export const SMOKE_ROUTES = [
  '/', '/product/positioning/', '/core/overview/', '/hosts/overview/', '/providers/overview/',
  '/contracts/overview/', '/assembly/lmdj/', '/platform/native-audio/',
  '/operations/testing-and-proof/', '/history/legacy-patch-architecture/',
  '/core/modules/foundation/', '/core/modules/authoring-domain/', '/core/modules/project-io/',
  '/core/modules/project-cooker/', '/core/modules/audio-runtime/', '/core/modules/provider-sdk/',
  '/core/modules/application-facade/',
];

async function mapLimit(values, limit, worker) {
  const results = new Array(values.length);
  let cursor = 0;
  async function consume() {
    while (cursor < values.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await worker(values[index], index);
    }
  }
  await Promise.all(Array.from({length: Math.min(limit, values.length)}, consume));
  return results;
}

function isVisibleSource(body) {
  const trimmed = body.trimStart().toLowerCase();
  return trimmed.startsWith('&lt;!doctype') || /^<pre[^>]*>\s*&lt;!doctype/i.test(trimmed);
}

async function fetchText(fetchImpl, url) {
  try {
    const response = await fetchImpl(url, {redirect: 'follow'});
    return {
      status: response.status,
      type: response.headers.get('content-type') ?? '',
      body: await response.text(),
    };
  } catch (error) {
    return {error: error.message};
  }
}

function referencedAssets(body, pageUrl, origin) {
  const $ = load(body);
  const assets = new Set();
  for (const element of $('[href], [src]').toArray()) {
    for (const attribute of ['href', 'src']) {
      const value = $(element).attr(attribute);
      if (!value || value.startsWith('#') || /^(mailto|tel|javascript|data):/i.test(value)) continue;
      let url;
      try { url = new URL(value, pageUrl); } catch { continue; }
      if (url.origin !== origin) continue;
      if (/^\/(assets|img|diagrams)\//.test(url.pathname) || /\.(css|js|mjs|svg|png|jpe?g|webp|ico|woff2?|html)$/i.test(url.pathname)) {
        assets.add(url.pathname);
      }
    }
  }
  return assets;
}

export async function smokePortal({baseUrl, productBuild, revision, fetchImpl = fetch, routes}) {
  let base;
  try { base = new URL(baseUrl); } catch { return ['base URL is invalid']; }
  if (base.protocol !== 'https:') return ['base URL must use HTTPS'];
  const routeList = routes ?? [...SMOKE_ROUTES, `/versions/${productBuild}/`];
  const errors = [];
  const documents = new Map();
  const responses = await mapLimit(routeList, 4, async (route) => [route, await fetchText(fetchImpl, new URL(route, base).href)]);

  for (const [route, response] of responses) {
    if (response.error) {
      errors.push(`${route} request failed: ${response.error}`);
      continue;
    }
    if (response.status < 200 || response.status >= 300) errors.push(`${route} returned HTTP ${response.status}`);
    if (!response.type.toLowerCase().startsWith('text/html')) errors.push(`${route} returned content-type ${response.type || '<missing>'}`);
    if (isVisibleSource(response.body)) errors.push(`${route} rendered escaped HTML source`);
    documents.set(route, response.body);
  }

  const home = documents.get('/') ?? '';
  if (!load(home).text().replace(/\s+/g, ' ').includes(`Product Build ${productBuild}`)) {
    errors.push(`/ did not render Product Build ${productBuild}`);
  }
  if (!load(home).text().includes(revision)) errors.push(`/ did not render revision ${revision}`);

  const snapshotRoute = `/versions/${productBuild}/`;
  if (routeList.includes(snapshotRoute) && documents.has(snapshotRoute)) {
    const snapshotText = load(documents.get(snapshotRoute)).text().replace(/\s+/g, ' ');
    if (!snapshotText.includes(`Product Build ${productBuild}`)) {
      errors.push(`${snapshotRoute} did not render Product Build ${productBuild}`);
    }
    if (!snapshotText.includes(`正式快照 ${productBuild}`)) {
      errors.push(`${snapshotRoute} did not render its formal snapshot identity`);
    }
  }

  const assets = new Set();
  for (const [route, body] of documents) {
    const pageUrl = new URL(route, base);
    for (const asset of referencedAssets(body, pageUrl, base.origin)) assets.add(asset);
  }
  const assetResponses = await mapLimit([...assets].sort(), 4, async (asset) => [asset, await fetchText(fetchImpl, new URL(asset, base).href)]);
  for (const [asset, response] of assetResponses) {
    if (response.error) errors.push(`${asset} request failed: ${response.error}`);
    else if (response.status < 200 || response.status >= 300) errors.push(`${asset} returned HTTP ${response.status}`);
    else if (asset.endsWith('.html') && !response.type.toLowerCase().startsWith('text/html')) {
      errors.push(`${asset} returned content-type ${response.type || '<missing>'}`);
    }
  }
  return errors;
}
