import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {glob} from 'glob';
import {renderDiagram} from './lib/diagram.mjs';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const files = await glob('diagrams/*.architecture.json', {cwd: portalRoot, absolute: true});
const outputRoot = path.join(portalRoot, 'static/diagrams');
await mkdir(outputRoot, {recursive: true});

for (const file of files.sort()) {
  const source = JSON.parse(await readFile(file, 'utf8'));
  const name = path.basename(file, '.architecture.json');
  const rendered = renderDiagram(source);
  await writeFile(path.join(outputRoot, `${name}.svg`), rendered.svg, 'utf8');
  await writeFile(path.join(outputRoot, `${name}.html`), rendered.html, 'utf8');
  console.log(`portal diagram: ${name} ${rendered.sourceSha256}`);
}
