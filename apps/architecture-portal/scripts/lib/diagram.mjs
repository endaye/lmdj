import {createHash} from 'node:crypto';

const WIDTH = 1560;
const HEIGHT = 820;

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function escapeXml(value = '') {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
  })[character]);
}

function overlaps(a, b, gap = 8) {
  return a.x < b.x + b.width + gap && a.x + a.width + gap > b.x &&
    a.y < b.y + b.height + gap && a.y + a.height + gap > b.y;
}

function labelWidth(label) {
  return [...label].reduce((width, character) => width + (/[^\u0000-\u00ff]/.test(character) ? 16 : 8.5), 0);
}

export function validateDiagram(source) {
  const errors = [];
  if (source.schema_version !== 1) errors.push('schema_version must be 1');
  if (!source.meta?.title) errors.push('meta.title is required');
  const components = Array.isArray(source.components) ? source.components : [];
  const ids = new Set();
  for (const component of components) {
    if (!component.id || ids.has(component.id)) errors.push(`component id ${component.id || '<empty>'} is not unique`);
    ids.add(component.id);
    for (const key of ['x', 'y', 'width', 'height']) {
      if (!Number.isFinite(component[key])) errors.push(`component ${component.id} has invalid ${key}`);
    }
    if (Number.isFinite(component.x) && Number.isFinite(component.width) &&
        Number.isFinite(component.y) && Number.isFinite(component.height) &&
        (component.x < 0 || component.y < 76 || component.x + component.width > WIDTH || component.y + component.height > 590)) {
      errors.push(`component ${component.id} is outside the graph bounds`);
    }
    if (typeof component.label !== 'string' || labelWidth(component.label) > component.width - 28) {
      errors.push(`component ${component.id} label exceeds its width`);
    }
  }
  for (let index = 0; index < components.length; index += 1) {
    for (let other = index + 1; other < components.length; other += 1) {
      if (overlaps(components[index], components[other])) {
        errors.push(`components ${components[index].id} and ${components[other].id} overlap`);
      }
    }
  }
  for (const connection of source.connections ?? []) {
    for (const endpoint of ['from', 'to']) {
      if (!ids.has(connection[endpoint])) {
        errors.push(`connection ${connection.from} -> ${connection.to} references unknown component ${connection[endpoint]}`);
      }
    }
    if (connection.label && labelWidth(connection.label) > 260) {
      errors.push(`connection ${connection.from} -> ${connection.to} label is too long`);
    }
  }
  for (const boundary of source.boundaries ?? []) {
    if (![boundary.x, boundary.y, boundary.width, boundary.height].every(Number.isFinite) ||
        boundary.x < 0 || boundary.y < 70 || boundary.x + boundary.width > WIDTH || boundary.y + boundary.height > 600) {
      errors.push(`boundary ${boundary.id} is outside the graph bounds`);
    }
  }
  if (source.meta?.legend) {
    const legend = {x: 1260, y: 82, width: 260, height: 104};
    for (const component of components) {
      if (overlaps(component, legend, 0)) errors.push(`component ${component.id} overlaps the legend`);
    }
  }
  if ((source.cards ?? []).length > 4) errors.push('diagram supports at most four cards');
  return errors;
}

function connectionPath(from, to) {
  const startX = from.x + from.width;
  const startY = from.y + from.height / 2;
  const endX = to.x;
  const endY = to.y + to.height / 2;
  if (endX >= startX) {
    const middleX = Math.round((startX + endX) / 2);
    return `M ${startX} ${startY} H ${middleX} V ${endY} H ${endX}`;
  }
  const middleY = Math.round(Math.max(startY, endY) + 54);
  return `M ${startX} ${startY} H ${startX + 34} V ${middleY} H ${endX - 34} V ${endY} H ${endX}`;
}

function renderSvg(source, sourceSha256) {
  const byId = new Map(source.components.map((component) => [component.id, component]));
  const boundaries = (source.boundaries ?? []).map((boundary) => `
    <g class="boundary"><rect x="${boundary.x}" y="${boundary.y}" width="${boundary.width}" height="${boundary.height}" rx="22"/><text x="${boundary.x + 20}" y="${boundary.y + 30}">${escapeXml(boundary.label)}</text></g>`).join('');
  const connections = source.connections.map((connection) => {
    const from = byId.get(connection.from);
    const to = byId.get(connection.to);
    const path = connectionPath(from, to);
    const labelX = Math.round((from.x + from.width + to.x) / 2);
    const labelY = Math.round((from.y + from.height / 2 + to.y + to.height / 2) / 2) - 9;
    return `<g class="connection"><path class="edge-mask" d="${path}"/><path class="edge" d="${path}" marker-end="url(#arrow)"/>${connection.label ? `<text x="${labelX}" y="${labelY}">${escapeXml(connection.label)}</text>` : ''}</g>`;
  }).join('\n');
  const components = source.components.map((component) => `
    <g class="component kind-${escapeXml(component.kind)}">
      <rect class="node-mask" x="${component.x - 4}" y="${component.y - 4}" width="${component.width + 8}" height="${component.height + 8}" rx="18"/>
      <rect class="node" x="${component.x}" y="${component.y}" width="${component.width}" height="${component.height}" rx="14"/>
      <text class="node-title" x="${component.x + 16}" y="${component.y + 32}">${escapeXml(component.label)}</text>
      ${component.detail ? `<text class="node-detail" x="${component.x + 16}" y="${component.y + 58}">${escapeXml(component.detail)}</text>` : ''}
    </g>`).join('');
  const cards = (source.cards ?? []).map((card, index, all) => {
    const gap = 18;
    const cardWidth = Math.floor((WIDTH - 80 - gap * (all.length - 1)) / all.length);
    const x = 40 + index * (cardWidth + gap);
    return `<g class="card"><rect x="${x}" y="638" width="${cardWidth}" height="132" rx="14"/><text class="card-title" x="${x + 18}" y="670">${escapeXml(card.title)}</text><foreignObject x="${x + 18}" y="684" width="${cardWidth - 36}" height="70"><div xmlns="http://www.w3.org/1999/xhtml" class="card-body">${escapeXml(card.body)}</div></foreignObject></g>`;
  }).join('\n');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${WIDTH} ${HEIGHT}" role="img" aria-labelledby="title description" data-source-sha256="${sourceSha256}">
  <title id="title">${escapeXml(source.meta.title)}</title><desc id="description">${escapeXml(source.meta.summary)}</desc>
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>
  <style>
    :root{--bg:#f7fafb;--panel:#fff;--text:#102427;--muted:#4b6569;--line:#2b7778;--border:#b8cdcf;--boundary:#eaf4f4;--accent:#00a9a5;--mask:#f7fafb}
    @media(prefers-color-scheme:dark){:root{--bg:#071011;--panel:#102023;--text:#f1fbfb;--muted:#a7c0c3;--line:#59d8d3;--border:#29464a;--boundary:#0c1a1c;--accent:#35d5cf;--mask:#071011}}
    [data-theme=dark]{--bg:#071011;--panel:#102023;--text:#f1fbfb;--muted:#a7c0c3;--line:#59d8d3;--border:#29464a;--boundary:#0c1a1c;--accent:#35d5cf;--mask:#071011}
    [data-theme=light]{--bg:#f7fafb;--panel:#fff;--text:#102427;--muted:#4b6569;--line:#2b7778;--border:#b8cdcf;--boundary:#eaf4f4;--accent:#00a9a5;--mask:#f7fafb}
    svg{background:var(--bg);font-family:Inter,"PingFang SC",system-ui,sans-serif}.page-title{font-size:32px;font-weight:750;fill:var(--text)}.page-summary{font-size:16px;fill:var(--muted)}
    .boundary rect{fill:var(--boundary);stroke:var(--border);stroke-dasharray:7 6}.boundary text{fill:var(--muted);font-size:15px;font-weight:700}.edge-mask{fill:none;stroke:var(--mask);stroke-width:10}.edge{fill:none;stroke:var(--line);stroke-width:2.5}.connection text{fill:var(--muted);font-size:14px;text-anchor:middle}.node-mask{fill:var(--mask)}.node{fill:var(--panel);stroke:var(--border);stroke-width:2}.kind-host .node,.kind-provider .node{stroke:var(--accent)}.node-title{fill:var(--text);font-size:19px;font-weight:750}.node-detail{fill:var(--muted);font-size:14px}.card rect{fill:var(--panel);stroke:var(--border)}.card-title{fill:var(--text);font-size:17px;font-weight:750}.card-body{color:var(--muted);font-size:15px;line-height:1.45}.marker{fill:var(--line)}
  </style>
  <rect width="${WIDTH}" height="${HEIGHT}" fill="var(--bg)"/><text class="page-title" x="40" y="44">${escapeXml(source.meta.title)}</text><text class="page-summary" x="40" y="68">${escapeXml(source.meta.summary)}</text>
  ${boundaries}
  ${connections}
  ${components}
  ${cards}
</svg>\n`.replace(/[ \t]+$/gm, '');
}

function wrapStandaloneHtml(title, svg) {
  return `<!doctype html>\n<html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeXml(title)}</title><style>html,body{margin:0}body{background:#f7fafb}@media(prefers-color-scheme:dark){body{background:#071011}}body[data-theme=light]{background:#f7fafb}body[data-theme=dark]{background:#071011}main{min-width:760px}svg{display:block;width:100%;height:auto}</style></head><body><main>${svg}</main><script>const diagram=document.querySelector('svg');function applyTheme(theme){diagram.setAttribute('data-theme',theme);document.body.setAttribute('data-theme',theme)}const requested=new URLSearchParams(location.search).get('theme');if(requested==='light'||requested==='dark')applyTheme(requested);window.addEventListener('message',(event)=>{const data=event.data;if(data&&data.type==='lmdj-diagram-theme'&&(data.theme==='light'||data.theme==='dark'))applyTheme(data.theme)});</script></body></html>\n`;
}

export function renderDiagram(source) {
  const errors = validateDiagram(source);
  if (errors.length) throw new Error(`diagram validation failed:\n- ${errors.join('\n- ')}`);
  const canonical = `${canonicalJson(source)}\n`;
  const sourceSha256 = createHash('sha256').update(canonical).digest('hex');
  const svg = renderSvg(source, sourceSha256);
  return {sourceSha256, svg, html: wrapStandaloneHtml(source.meta.title, svg)};
}
