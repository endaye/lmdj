import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
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
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`portal docs: ${files.length} pages valid`);
}
