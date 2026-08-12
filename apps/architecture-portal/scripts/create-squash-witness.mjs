import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createSquashWitness} from './lib/snapshot-provenance.mjs';

const [version, introducingRevision] = process.argv.slice(2);
if (!/^\d+\.\d+\.\d+\.\d+$/.test(version ?? '') || !/^[0-9a-f]{40}$/.test(introducingRevision ?? '')) {
  console.error('usage: node scripts/create-squash-witness.mjs PRODUCT_BUILD INTRODUCING_REVISION');
  process.exit(64);
}

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const metadata = JSON.parse(await readFile(
  path.join(portalRoot, 'versioned_metadata', `version-${version}.json`),
  'utf8',
));
const witness = await createSquashWitness({repoRoot, metadata, introducingRevision});
const output = path.join(portalRoot, 'versioned_provenance', `version-${version}-squash-witness.json`);
await mkdir(path.dirname(output), {recursive: true});
await writeFile(output, `${JSON.stringify(witness, null, 2)}\n`, {flag: 'wx'});
console.log(`portal squash witness: ${path.relative(repoRoot, output)}`);
