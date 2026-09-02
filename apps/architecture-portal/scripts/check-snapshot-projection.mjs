import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

import {projectionManifest} from './lib/snapshot-provenance.mjs';
import {resolveChangedFiles} from './lib/changed-files.mjs';

const execFileAsync = promisify(execFile);

const METADATA_PATTERN =
  /^apps\/architecture-portal\/versioned_metadata\/version-(\d+\.\d+\.\d+\.\d+)\.json$/;

function remedy(version, detail) {
  return `${detail}; re-run scripts/architecture-portal.sh version ${version} CHANNEL ` +
    'at the branch tip so the snapshot projects the tree that will be squashed';
}

/**
 * Decide, from the merge target's own tree alone, whether a snapshot this
 * change introduces will still be provable after it lands.
 *
 * A squash merge never keeps the branch commit a snapshot records as its
 * revision, so on `main` the snapshot can only be accepted by its recorded
 * source projection matching the introducing commit's tree. That introducing
 * commit is the squash, whose tree is this change's own tree, so the same
 * comparison is decidable here — before the merge, with an identical verdict.
 *
 * Only snapshots this change introduces are its subject. A divergence in an
 * already landed snapshot may be authorized by a squash witness, and a witness
 * names the introducing commit, so it can only be written after the squash
 * exists — which is exactly why a snapshot introduced here cannot have one and
 * must instead project the tree it ships with.
 */
export async function checkSnapshotProjection({addedFiles, readMetadata, readProjection}) {
  const errors = [];
  const metadataFiles = [...new Set(addedFiles)]
    .filter((file) => METADATA_PATTERN.test(file))
    .sort();
  for (const file of metadataFiles) {
    const version = file.match(METADATA_PATTERN)[1];
    let metadata;
    try {
      metadata = await readMetadata(file);
    } catch (error) {
      errors.push(`${file}: snapshot metadata cannot be read from the merge target: ${error.message}`);
      continue;
    }
    // A change that removes a snapshot leaves nothing to project; the landed
    // inventory is the release audit's subject, not this gate's.
    if (metadata === null) continue;
    const recorded = metadata?.source_projection;
    if (!recorded || !Array.isArray(recorded.files) ||
        recorded.files.some((entry) => typeof entry?.path !== 'string')) {
      errors.push(`${file}: snapshot metadata carries no source projection to verify`);
      continue;
    }
    let actual;
    try {
      actual = await readProjection(recorded.files.map((entry) => entry.path));
    } catch (error) {
      errors.push(remedy(
        version,
        `${file}: a projected path is absent from this change's own tree (${error.message})`,
      ));
      continue;
    }
    if (JSON.stringify(actual) !== JSON.stringify(recorded)) {
      errors.push(remedy(
        version,
        `${file}: the recorded source projection does not match this change's own tree`,
      ));
    }
  }
  return errors;
}

async function main() {
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
  const baseSha = process.env.PORTAL_BASE_SHA ?? '';
  const headSha = process.env.PORTAL_HEAD_SHA || 'HEAD';
  let addedFiles = (process.env.PORTAL_ADDED_FILES ?? '').split(/\r?\n/).filter(Boolean);
  if (!addedFiles.length) {
    try {
      addedFiles = await resolveChangedFiles(repoRoot, {baseSha, headSha, diffFilter: 'A'});
    } catch (error) {
      console.error(`the added-file range cannot be measured: ${error.message}`);
      process.exitCode = 1;
      return;
    }
  }

  const errors = await checkSnapshotProjection({
    addedFiles,
    readMetadata: async (file) => {
      const exists = await execFileAsync('git', ['cat-file', '-e', `${headSha}:${file}`], {cwd: repoRoot})
        .then(() => true, () => false);
      if (!exists) return null;
      const {stdout} = await execFileAsync('git', ['show', `${headSha}:${file}`], {
        cwd: repoRoot,
        maxBuffer: 64 * 1024 * 1024,
      });
      return JSON.parse(stdout);
    },
    readProjection: (paths) => projectionManifest(repoRoot, headSha, paths),
  });

  if (errors.length) {
    console.error(errors.join('\n'));
    process.exitCode = 1;
  } else {
    console.log('portal snapshot projection: valid');
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) await main();
