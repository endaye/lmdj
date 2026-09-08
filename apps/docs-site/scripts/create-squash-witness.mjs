import {execFile as execFileCallback} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {promisify} from 'node:util';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createSquashWitness, resolveIntroducingRevision} from './lib/snapshot-provenance.mjs';

const execFile = promisify(execFileCallback);

const [version, explicitRevision] = process.argv.slice(2);
if (!/^\d+\.\d+\.\d+\.\d+$/.test(version ?? '') ||
    (explicitRevision !== undefined && !/^[0-9a-f]{40}$/.test(explicitRevision))) {
  console.error('usage: node scripts/create-squash-witness.mjs PRODUCT_BUILD [INTRODUCING_REVISION]');
  process.exit(64);
}

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const metadata = JSON.parse(await readFile(
  path.join(portalRoot, 'versioned_metadata', `version-${version}.json`),
  'utf8',
));
// The introducing revision is the squash commit that carried the snapshot onto
// main, which is exactly what the verifier resolves for itself before it
// reports the witness missing. Deriving it here keeps the remedy a one-argument
// command; an explicitly supplied revision still wins and is validated as before.
let introducingRevision = explicitRevision;
if (introducingRevision === undefined) {
  const headRevision = (await execFile('git', ['rev-parse', 'HEAD'], {cwd: repoRoot})).stdout.trim();
  try {
    introducingRevision = await resolveIntroducingRevision({repoRoot, version, headRevision});
  } catch (error) {
    console.error(`cannot derive INTRODUCING_REVISION: ${error.message}`);
    console.error('usage: node scripts/create-squash-witness.mjs PRODUCT_BUILD [INTRODUCING_REVISION]');
    process.exit(64);
  }
}
const witness = await createSquashWitness({repoRoot, metadata, introducingRevision});
const output = path.join(portalRoot, 'versioned_provenance', `version-${version}-squash-witness.json`);
await mkdir(path.dirname(output), {recursive: true});
try {
  await writeFile(output, `${JSON.stringify(witness, null, 2)}\n`, {flag: 'wx'});
} catch (error) {
  if (error?.code !== 'EEXIST') throw error;
  console.error(`portal squash witness already exists: ${path.relative(repoRoot, output)}`);
  process.exitCode = 1;
}
if (process.exitCode !== 1) console.log(`portal squash witness: ${path.relative(repoRoot, output)}`);
