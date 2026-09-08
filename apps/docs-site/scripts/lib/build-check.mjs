import path from 'node:path';
import {access, readFile} from 'node:fs/promises';
import {glob} from 'glob';
import {load} from 'cheerio';

function routeForFile(buildRoot, file) {
  const relative = path.relative(buildRoot, file).split(path.sep).join('/');
  if (relative === 'index.html') return '/';
  if (relative.endsWith('/index.html')) return `/${relative.slice(0, -'index.html'.length)}`;
  return `/${relative}`;
}

function routeCandidates(buildRoot, pathname) {
  const relative = decodeURIComponent(pathname).replace(/^\/+/, '');
  if (!relative || pathname.endsWith('/')) return [path.join(buildRoot, relative, 'index.html')];
  if (path.extname(relative)) return [path.join(buildRoot, relative)];
  return [
    path.join(buildRoot, relative),
    path.join(buildRoot, `${relative}.html`),
    path.join(buildRoot, relative, 'index.html'),
  ];
}

async function existsAny(files) {
  for (const file of files) {
    if (await access(file).then(() => true, () => false)) return true;
  }
  return false;
}

function internalPath(value, pageRoute) {
  if (!value || value.startsWith('#') || /^(mailto|tel|javascript|data):/i.test(value)) return null;
  let url;
  try {
    url = new URL(value, `https://lmdj.netlify.app${pageRoute}`);
  } catch {
    return null;
  }
  if (url.origin !== 'https://lmdj.netlify.app') return null;
  return url.pathname;
}

export async function checkBuild({buildRoot, requiredRoutes, expectedIdentity, versionSchemas = {}}) {
  const errors = [];
  const files = await glob('**/*.html', {cwd: buildRoot, absolute: true});
  const pages = new Map(files.map((file) => [routeForFile(buildRoot, file), file]));

  for (const route of requiredRoutes) {
    if (!await existsAny(routeCandidates(buildRoot, route))) errors.push(`missing route ${route}`);
  }

  const broken = new Set();
  for (const [route, file] of [...pages].sort(([left], [right]) => left.localeCompare(right))) {
    const html = await readFile(file, 'utf8');
    const $ = load(html);
    const from = `/${path.relative(buildRoot, file).split(path.sep).join('/')}`;
    const visibleDirective = $('body').text().match(/:::(warning|note|tip|danger|info)\b/i)?.[0];
    if (visibleDirective) broken.add(`visible MDX directive ${visibleDirective} in ${from}`);
    for (const element of $('[href], [src]').toArray()) {
      for (const attribute of ['href', 'src']) {
        const pathname = internalPath($(element).attr(attribute), route);
        if (pathname && !await existsAny(routeCandidates(buildRoot, pathname))) {
          broken.add(`broken internal link ${pathname} from ${from}`);
        }
      }
    }
  }
  errors.push(...[...broken].sort());

  const scopeErrors = [];
  const inspectCards = async (route, label, expectedPrefix) => {
    const file = pages.get(route);
    if (!file) return;
    const $ = load(await readFile(file, 'utf8'));
    for (const card of $('a.section-card[href]').toArray()) {
      const pathname = internalPath($(card).attr('href'), route);
      if (!pathname) continue;
      const escaped = expectedPrefix === '/'
        ? pathname.startsWith('/versions/')
        : !pathname.startsWith(expectedPrefix);
      if (escaped) scopeErrors.push(`${label} section card escapes ${expectedPrefix === '/' ? 'current' : 'version'} scope: ${pathname}`);
    }
  };
  await inspectCards('/', 'current home', '/');
  for (const version of Object.keys(versionSchemas).sort()) {
    const prefix = `/versions/${version}/`;
    if (!pages.has(prefix)) scopeErrors.push(`missing rendered version home ${prefix}`);
    else await inspectCards(prefix, `version ${version} home`, prefix);
  }
  for (const [version, schema] of Object.entries(versionSchemas).sort()) {
    if (schema !== 2) continue;
    const prefix = `/versions/${version}/`;
    for (const [route, file] of [...pages].sort(([left], [right]) => left.localeCompare(right))) {
      if (!route.startsWith(prefix)) continue;
      const $ = load(await readFile(file, 'utf8'));
      const from = `/${path.relative(buildRoot, file).split(path.sep).join('/')}`;
      for (const element of $('[href], [src]').toArray()) {
        for (const attribute of ['href', 'src']) {
          const pathname = internalPath($(element).attr(attribute), route);
          if (pathname?.startsWith('/diagrams/')) {
            scopeErrors.push(`schema-2 version ${version} uses mutable diagram ${pathname} from ${from}`);
          }
        }
      }
    }
  }
  errors.push(...scopeErrors);

  const indexFile = pages.get('/');
  if (indexFile) {
    const indexText = load(await readFile(indexFile, 'utf8')).text().replace(/\s+/g, ' ');
    if (!indexText.includes(`Product Build ${expectedIdentity.productBuild}`)) {
      errors.push(`index identity does not contain Product Build ${expectedIdentity.productBuild}`);
    } else if (!indexText.includes(expectedIdentity.revision)) {
      errors.push(`index identity does not contain revision ${expectedIdentity.revision}`);
    }
  }
  return errors;
}
