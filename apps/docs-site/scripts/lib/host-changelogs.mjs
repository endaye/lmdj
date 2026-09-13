import {createHash} from 'node:crypto';
import {lstat, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';

const MAX_BYTES = 1024 * 1024;
const MARKER = '<!-- lmdj-host-changelog:v1 ';
const HOSTS = [
  {id: 'creator-web', route: 'creator-changelog', title: 'Creator changelog'},
  {id: 'web-runtime-host', route: 'runtime-changelog', title: 'Web Runtime / Lab changelog'},
];
const ENTRY_KEYS = ['schema', 'host', 'version', 'prepared_date', 'base_sha', 'target_sha',
  'input_digest', 'assessment_digest', 'impact', 'rationale', 'references',
  'dependency_effects', 'changes', 'digest'];
const fail = (why) => { throw new Error(`why: Host changelog ${why}; remedy: reconcile canonical Host sources, then run npm run changelogs in apps/docs-site`); };
const requireValue = (condition, why) => { if (!condition) fail(why); };
const sha = (value, length) => typeof value === 'string' && new RegExp(`^[a-f0-9]{${length}}$`).test(value);
const closed = (value, keys) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join('\0') === [...keys].sort().join('\0');

// Match records.canonical: sorted ASCII schema keys and Python ensure_ascii.
// The closed entry schema contains only objects, arrays and strings, no numbers.
export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${canonical(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  requireValue(typeof value === 'string', 'contains unsupported JSON values');
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g,
    (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`);
}

function version(value) {
  requireValue(typeof value === 'string' && /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.test(value), 'version is not stable SemVer');
  return value.split('.').map(BigInt);
}

function compare(left, right) {
  const a = version(left), b = version(right);
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] > b[i] ? 1 : -1;
  }
  return 0;
}

function prose(value) {
  requireValue(typeof value === 'string' && value.trim().length > 0 && [...value.trim()].length <= 4000
    && !/[\x00-\x08\x0b-\x1f]/.test(value), 'prose is empty, oversized or contains controls');
}

function references(value) {
  requireValue(Array.isArray(value) && value.length > 0 && value.every((ref) => sha(ref, 40))
    && new Set(value).size === value.length, 'commit references are missing, duplicated or invalid');
}

function validateEntry(entry, host, currentVersion) {
  requireValue(closed(entry, ENTRY_KEYS), 'entry fields are not closed');
  requireValue(entry.schema === 'lmdj.host-changelog-entry.v1' && entry.host === host, 'entry Host or schema differs');
  requireValue(compare(entry.version, currentVersion) <= 0, 'entry version exceeds manifest version');
  requireValue(typeof entry.prepared_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(entry.prepared_date)
    && entry.prepared_date.slice(0, 4) !== '0000'
    && Number.isFinite(Date.parse(entry.prepared_date))
    && new Date(entry.prepared_date).toISOString().slice(0, 10) === entry.prepared_date, 'prepared date is invalid');
  for (const field of ['base_sha', 'target_sha']) requireValue(sha(entry[field], 40), `${field} is invalid`);
  for (const field of ['input_digest', 'assessment_digest', 'digest']) requireValue(sha(entry[field], 64), `${field} is invalid`);
  requireValue(['patch', 'minor'].includes(entry.impact), 'prepared impact requires compatibility review');
  prose(entry.rationale);
  references(entry.references);
  requireValue(Array.isArray(entry.dependency_effects) && entry.dependency_effects.length <= 30, 'dependency effects inventory is invalid');
  entry.dependency_effects.forEach(prose);
  requireValue(Array.isArray(entry.changes) && entry.changes.length > 0 && entry.changes.length <= 30, 'changes inventory is missing or oversized');
  for (const change of entry.changes) {
    requireValue(closed(change, ['kind', 'text', 'references'])
      && ['added', 'fixed', 'changed'].includes(change.kind), 'change fields or prepared kind differ');
    prose(change.text);
    references(change.references);
  }
  const {digest, ...unsigned} = entry;
  requireValue(createHash('sha256').update(canonical(unsigned)).digest('hex') === digest, 'entry digest differs');
}

export function parseChangelog(source, host, currentVersion) {
  version(currentVersion);
  requireValue(typeof source === 'string' && Buffer.byteLength(source) <= MAX_BYTES, 'source exceeds byte limit');
  const entries = [], headings = new Set();
  let heading = null;
  // Do not render legacy Markdown or provider-supplied HTML/MDX. Only machine
  // records become entries; every marker must occupy a complete source line.
  for (const line of source.split('\n')) {
    if (/^##[ \t]/.test(line)) heading = null;
    const match = /^##[ \t]+\[?([0-9]+\.[0-9]+\.[0-9]+)(?=\]|[ \t\r]|$)/.exec(line);
    if (match) {
      version(match[1]);
      requireValue(!headings.has(match[1]), 'duplicate version heading');
      headings.add(match[1]);
      heading = match[1];
    }
    if (!line.includes('lmdj-host-changelog:')) continue;
    requireValue(line.startsWith(MARKER) && line.endsWith(' -->'), 'marker is malformed or truncated');
    const encoded = line.slice(MARKER.length, -4);
    const raw = Buffer.from(encoded, 'base64');
    requireValue(raw.toString('base64') === encoded, 'marker base64 is not canonical');
    let entry;
    try { entry = JSON.parse(raw.toString('utf8')); } catch { fail('marker JSON is invalid'); }
    validateEntry(entry, host, currentVersion);
    requireValue(Buffer.from(canonical(entry)).equals(raw), 'marker JSON is not canonical');
    requireValue(entry.version === heading, 'entry version differs from heading');
    requireValue(!entries.some((prior) => prior.version === entry.version), 'duplicate machine version');
    requireValue(entries.length === 0 || compare(entries.at(-1).version, entry.version) < 0, 'machine versions are not append-ordered');
    entries.push(entry);
  }
  return entries.reverse();
}

// All model prose is text, never executable MDX, raw HTML or model URLs.
function escape(value) {
  return [...value.trim().replace(/\s+/g, ' ')].map((char) => /[\p{L}\p{N} ]/u.test(char)
    ? char : `&#${char.codePointAt(0)};`).join('');
}
const links = (refs) => refs.map((ref) => `[${ref.slice(0, 12)}](https://github.com/endaye/lmdj/commit/${ref})`).join(', ');

export function renderChangelog({id, title, manifestVersion, entries, hasSource}) {
  const sourcePath = `apps/${id}/CHANGELOG.md`;
  const lines = ['---', `title: ${title}`, 'area: operations', 'status: partial',
    'owners: [release, docs]',
    `source_paths: [apps/${id}/module.json, tools/canary/preparation.py, apps/docs-site/scripts/lib/host-changelogs.mjs${hasSource ? `, ${sourcePath}` : ''}]`,
    '---', '', '{/* Generated by npm run changelogs; do not hand-edit. */}', '',
    `Host: \`${id}\`. Source manifest version: \`${manifestVersion}\`.`, '',
    '这些是源码中的 prepared 记录，不是已发布版本列表。摘要只校验记录完整性，不证明 AI 判断正确、测试通过或远端授权。', '',
    'Publication / deployment / promotion: **未接入认证回执，状态未知**。Prepared 不等于已部署或已晋级。', '',
    '本页为静态源码投影；历史 Product 快照保留冻结时内容，不读取当前 main 的 changelog。', '',
    '[版本与发布边界](./version-and-release.mdx) · [Product release 日志](../releases/index.mdx)', ''];
  if (hasSource) lines.push(`原始日志：\`${sourcePath}\`。未结构化的历史文字不作为可验证版本记录展示。`, '');
  if (!entries.length) lines.push('暂无结构化 prepared 记录；不补造历史版本或发布日期。', '');
  for (const entry of entries) {
    lines.push(`## ${entry.version}`, '', `State: **prepared**. Prepared date: ${entry.prepared_date}.`, '',
      `Impact: ${entry.impact}. ${escape(entry.rationale)}`, '', 'Changes:', '');
    for (const change of entry.changes) lines.push(`- ${change.kind}: ${escape(change.text)} (${links(change.references)})`);
    if (entry.dependency_effects.length) lines.push('', 'Dependency effects:', '', ...entry.dependency_effects.map((effect) => `- ${escape(effect)}`));
    lines.push('', `Assessed commits: ${links(entry.references)}`, '',
      `Assessed interval: ${links([entry.base_sha])} → ${links([entry.target_sha])}`, '',
      `Input digest: \`${entry.input_digest}\``, '', `Assessment digest: \`${entry.assessment_digest}\``, '',
      `Entry digest: \`${entry.digest}\``, '');
  }
  return lines.join('\n');
}

async function readSource(file, optional = false) {
  let info;
  try { info = await lstat(file); } catch (error) {
    if (optional && error.code === 'ENOENT') return null;
    fail(`source unavailable: ${file}`);
  }
  requireValue(info.isFile() && info.size <= MAX_BYTES, `source is not a bounded regular file: ${file}`);
  let raw;
  try { raw = await readFile(file); } catch { fail(`source cannot be read: ${file}`); }
  requireValue(raw.length <= MAX_BYTES, `source exceeds byte limit: ${file}`);
  try { return new TextDecoder('utf-8', {fatal: true}).decode(raw); } catch { fail(`source is not UTF-8: ${file}`); }
}

export async function projectChangelogs(repoRoot, {check = true} = {}) {
  const projections = [];
  // Validate all sources before any write; explicit generation never updates
  // Host inputs, versioned_docs, frozen metadata or deployment records.
  for (const host of HOSTS) {
    const manifestPath = path.join(repoRoot, `apps/${host.id}/module.json`);
    let manifest;
    try { manifest = JSON.parse(await readSource(manifestPath)); } catch (error) {
      fail(`manifest unavailable or invalid: ${host.id} (${error.name})`);
    }
    requireValue(manifest !== null && typeof manifest === 'object'
      && manifest.contract === 'lmdj.module.v1' && manifest.module === host.id, 'manifest Host identity differs');
    version(manifest.version);
    const source = await readSource(path.join(repoRoot, `apps/${host.id}/CHANGELOG.md`), true);
    const entries = parseChangelog(source ?? '', host.id, manifest.version);
    projections.push({file: path.join(repoRoot, `apps/docs-site/docs/operations/${host.route}.mdx`),
      content: renderChangelog({...host, manifestVersion: manifest.version, entries, hasSource: source !== null})});
    requireValue(Buffer.byteLength(projections.at(-1).content) <= MAX_BYTES, 'projection exceeds byte limit');
  }
  for (const {file, content} of projections) {
    const existing = await readSource(file, true);
    if (check) requireValue(existing === content, `projection is stale: ${path.basename(file)}`);
    else if (existing !== content) await writeFile(file, content);
  }
  return projections;
}
