import path from 'node:path';
import {access, readdir, readFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {readRepoFacts} from './lib/repo-facts.mjs';
import {validateReleaseSnapshot, validateSnapshotRetention} from './lib/version-docs.mjs';
import {verifySnapshotProvenance} from './lib/snapshot-provenance.mjs';

const execFileAsync = promisify(execFile);
const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const {stdout} = await execFileAsync('git', ['rev-parse', 'HEAD'], {cwd: repoRoot});
const facts = await readRepoFacts({repoRoot, revision: stdout.trim(), channel: 'canary'});
const productBuild = facts.product.version;
const versions = JSON.parse(await readFile(path.join(portalRoot, 'versions.json'), 'utf8'));
const metadataPath = path.join(portalRoot, 'versioned_metadata', `version-${productBuild}.json`);
const metadata = await readFile(metadataPath, 'utf8').then(JSON.parse, (error) => {
  if (error.code === 'ENOENT') return null;
  throw error;
});
const snapshotPath = path.join(portalRoot, 'versioned_docs', `version-${productBuild}`, 'overview', 'index.mdx');
const snapshotExists = await access(snapshotPath).then(() => true, () => false);
async function inventoryBuilds(relative, pattern) {
  const names = await readdir(path.join(portalRoot, relative)).catch((error) => {
    if (error.code === 'ENOENT') return [];
    throw error;
  });
  return names.flatMap((name) => name.match(pattern)?.slice(1, 2) ?? []);
}

// A witness is created after the introducing merge, so the newest snapshot
// may lack one; the witness inventory is only checked for orphans.
const inventories = {
  versioned_docs: {builds: await inventoryBuilds('versioned_docs', /^version-(.+)$/), required: true},
  versioned_sidebars: {builds: await inventoryBuilds('versioned_sidebars', /^version-(.+)-sidebars\.json$/), required: true},
  versioned_metadata: {builds: await inventoryBuilds('versioned_metadata', /^version-(.+)\.json$/), required: true},
  versioned_provenance: {builds: await inventoryBuilds('versioned_provenance', /^version-(.+)-squash-witness\.json$/), required: false},
  'static/versions': {builds: await inventoryBuilds('static/versions', /^(.+)$/), required: true},
};
let errors = [
  ...validateReleaseSnapshot({facts, versions, metadata, snapshotExists}),
  ...validateSnapshotRetention({productBuild, versions, inventories}),
];
if (!errors.length && metadata?.schema_version === 2) {
  errors = await verifySnapshotProvenance({
    repoRoot,
    portalRoot,
    metadata,
    headRevision: stdout.trim(),
  });
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`portal release docs: Product Build ${productBuild} snapshot matches repository truth`);
}
