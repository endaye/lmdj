import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import matter from 'gray-matter';
import {glob} from 'glob';
import {readRepoFacts} from './lib/repo-facts.mjs';
import {validatePageMetadata} from './lib/page-metadata.mjs';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const facts = await readRepoFacts({repoRoot, revision: 'validation', channel: 'validation'});
const activeContractIds = new Set(facts.contracts.map(({id}) => id));
const files = await glob('docs/**/*.{md,mdx}', {cwd: portalRoot, absolute: true});
const errors = [];
const declarations = {
  modules: new Map(),
  hosts: new Map(),
  providers: new Map(),
  contracts: new Map(),
};

function declare(kind, id, file, body) {
  if (typeof id !== 'string' || !id) {
    errors.push(`${path.relative(repoRoot, file)}: invalid ${kind} declaration`);
    return;
  }
  const entries = declarations[kind].get(id) ?? [];
  entries.push({file, body});
  declarations[kind].set(id, entries);
}

for (const file of files.sort()) {
  const source = await readFile(file, 'utf8');
  const {data, content: body} = matter(source);
  errors.push(...validatePageMetadata({
    file: path.relative(repoRoot, file),
    data,
    body,
    repoRoot,
    activeContractIds,
  }));
  if (data.module != null) declare('modules', data.module, file, body);
  if (data.host != null) declare('hosts', data.host, file, body);
  if (data.provider != null) declare('providers', data.provider, file, body);
  for (const id of data.providers ?? []) declare('providers', id, file, body);
  for (const id of data.contracts ?? []) declare('contracts', id, file, body);
}

for (const kind of ['modules', 'hosts', 'providers', 'contracts']) {
  const activeIds = new Set(facts[kind].map(({id}) => id));
  for (const id of activeIds) {
    const pages = declarations[kind].get(id) ?? [];
    if (pages.length !== 1) errors.push(`current truth: ${kind} ${id} must map to exactly one page, found ${pages.length}`);
    if (kind === 'modules' && pages.length === 1) {
      for (const extension of ['architecture.json']) {
        const diagram = path.join(portalRoot, 'diagrams', `${id}.${extension}`);
        if (!existsSync(diagram)) errors.push(`current truth: module ${id} missing diagram source`);
      }
      for (const extension of ['html', 'svg']) {
        const output = path.join(portalRoot, 'static/diagrams', `${id}.${extension}`);
        if (!existsSync(output)) errors.push(`current truth: module ${id} missing diagram ${extension}`);
      }
      if (!pages[0].body.includes(`diagramId="${id}"`)) {
        errors.push(`current truth: module ${id} page does not embed validated diagram id`);
      }
    }
  }
  for (const id of declarations[kind].keys()) {
    if (!activeIds.has(id)) errors.push(`current truth: ${kind} ${id} is not in Assembly Lock`);
  }
}

if (errors.length) {
  console.error(errors.sort().join('\n'));
  process.exitCode = 1;
} else {
  console.log(`portal docs: ${files.length} pages valid`);
}
