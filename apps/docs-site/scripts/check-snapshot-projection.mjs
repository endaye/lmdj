import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

import {projectionManifest} from './lib/snapshot-provenance.mjs';
import {requireRevision, resolveChangedFiles} from './lib/changed-files.mjs';

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

async function checkAtRevision(repoRoot, headSha, addedFiles, {allowMissing = true} = {}) {
  return checkSnapshotProjection({
    addedFiles,
    readMetadata: async (file) => {
      const exists = await execFileAsync('git', ['cat-file', '-e', `${headSha}:${file}`], {cwd: repoRoot})
        .then(() => true, () => false);
      if (!exists) {
        if (!allowMissing) throw new Error('an introduced metadata blob is unavailable');
        return null;
      }
      const {stdout} = await execFileAsync('git', ['show', `${headSha}:${file}`], {
        cwd: repoRoot,
        maxBuffer: 64 * 1024 * 1024,
      });
      return JSON.parse(stdout);
    },
    readProjection: (paths) => projectionManifest(repoRoot, headSha, paths),
  });
}

// main-interval is selected by the authenticated batch caller, not PR input.
// Local refs prove Git topology only; GitHub source/claim authority belongs to
// that caller. Never substitute the newest target for an introducing tree.
export async function checkRevisionProjection({repoRoot, mode = 'own-tree', baseSha = '', headSha = 'HEAD', addedFiles = []}) {
  try {
    if (!['own-tree', 'main-interval'].includes(mode)) throw new Error('unknown snapshot comparison mode');
    if (mode === 'own-tree') {
      const files = addedFiles.length ? addedFiles : await resolveChangedFiles(repoRoot, {baseSha, headSha, diffFilter: 'A'});
      return {errors: await checkAtRevision(repoRoot, headSha, files), checked: new Set(files.filter((file) => METADATA_PATTERN.test(file))).size};
    }
    if (addedFiles.length) throw new Error('main interval cannot accept an added-file override');
    requireRevision(baseSha, 'base'); requireRevision(headSha, 'head');
    const git = async (...args) => (await execFileAsync('git', args, {cwd: repoRoot, maxBuffer: 64 * 1024 * 1024})).stdout.trim();
    if (await git('rev-parse', '--is-shallow-repository') !== 'false') throw new Error('main history is shallow');
    for (const revision of [baseSha, headSha]) {
      if (await git('cat-file', '-t', revision) !== 'commit') throw new Error('revision is not an available commit');
    }
    const mainHistory = (await git('rev-list', '--first-parent', 'refs/remotes/origin/main')).split('\n');
    if (!mainHistory.includes(headSha)) throw new Error('target is outside main first-parent history');
    const history = (await git('rev-list', '--first-parent', headSha)).split('\n');
    const baseIndex = history.indexOf(baseSha);
    if (baseIndex < 0) throw new Error('base is outside target first-parent history');
    const revisions = history.slice(0, baseIndex).reverse();
    const errors = [];
    let checked = 0;
    for (const revision of revisions) {
      // Diff against the first parent, not the endpoint net diff. This also
      // sees introductions subsequently deleted, renamed, reverted or fixed.
      const {stdout} = await execFileAsync('git', ['diff', '--no-renames', '--name-only', '-z', '--diff-filter=A', `${revision}^1`, revision], {cwd: repoRoot});
      const files = stdout.split('\0').filter((file) => METADATA_PATTERN.test(file));
      checked += files.length;
      errors.push(...(await checkAtRevision(repoRoot, revision, files, {allowMissing: false})).map((error) =>
        `why: introducing commit ${revision}: ${error.split('; re-run ')[0]}; remedy: investigate this exact introduction and repair provenance through its authorized workflow; never rewrite a frozen snapshot to match later mutable pages`));
    }
    return {errors, checked};
  } catch (error) {
    throw new Error(`why: snapshot comparison cannot be established (${error.message.replace(/\s+/g, ' ')}); remedy: supply a supported mode and exact authenticated main range with complete Git history; do not skip projection validation`);
  }
}

async function main() {
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
  const mode = process.env.PORTAL_SNAPSHOT_MODE || 'own-tree';
  let result;
  try {
    result = await checkRevisionProjection({repoRoot, mode,
      baseSha: process.env.PORTAL_BASE_SHA ?? '', headSha: process.env.PORTAL_HEAD_SHA || 'HEAD',
      addedFiles: (process.env.PORTAL_ADDED_FILES ?? '').split(/\r?\n/).filter(Boolean)});
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
    return;
  }
  const {errors, checked} = result;

  if (errors.length) {
    console.error(errors.join('\n'));
    process.exitCode = 1;
  } else {
    console.log(mode === 'main-interval' && checked === 0
      ? 'portal snapshot projection: no snapshot introductions in interval; complete candidate provenance remains the full Portal check'
      : `portal snapshot projection: valid (${checked} introductions checked)`);
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) await main();
