import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import {glob} from 'glob';
import {renderDiagram} from './lib/diagram.mjs';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sources = await glob('diagrams/*.architecture.json', {cwd: portalRoot, absolute: true});
const errors = [];
if (sources.length !== 10) errors.push(`expected 10 diagram sources, found ${sources.length}`);

for (const file of sources.sort()) {
  const source = JSON.parse(await readFile(file, 'utf8'));
  const name = path.basename(file, '.architecture.json');
  const rendered = renderDiagram(source);
  for (const extension of ['svg', 'html']) {
    const output = path.join(portalRoot, 'static/diagrams', `${name}.${extension}`);
    const actual = await readFile(output, 'utf8').catch(() => null);
    if (actual !== rendered[extension]) errors.push(`${name}.${extension} is missing or stale`);
  }
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log('portal diagrams: 10 sources and 20 outputs valid');
}
