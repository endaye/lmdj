import assert from 'node:assert/strict';
import test from 'node:test';
import {execFile} from 'node:child_process';
import {cp, mkdir, mkdtemp, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {promisify} from 'node:util';

import {requireRevision, resolveChangedFiles} from '../scripts/lib/changed-files.mjs';
import {checkDocumentationImpact} from '../scripts/check-doc-impact.mjs';

const execFileAsync = promisify(execFile);
const SCRIPTS_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../scripts');
const PORTAL_PAGE = 'apps/docs-site/docs/operations/git-workflow.mdx';
const BRANCH_FILE = 'docs/research/esp32.md';
const HONEST_NONE = 'Documentation impact: none\nReason: research note only, no portal truth changed';

async function git(root, args) {
  return execFileAsync('git', args, {cwd: root, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024});
}

async function put(root, relative, body) {
  const file = path.join(root, relative);
  await mkdir(path.dirname(file), {recursive: true});
  await writeFile(file, body);
}

async function commit(root, message) {
  await git(root, ['add', '--all']);
  await git(root, ['-c', 'commit.gpgsign=false', 'commit', '-m', message]);
  return (await git(root, ['rev-parse', 'HEAD'])).stdout.trim();
}

/**
 * Build the exact shape issue #531 reports: a branch that changes one
 * unrelated file, cut before a portal page landed on `main`, and never merged
 * up. `baseSha` is the base branch tip the `pull_request` event would carry,
 * which is strictly ahead of the branch's merge base.
 */
async function behindBaseFixture({alsoTouchPortal = false} = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'portal-changed-files-'));
  await git(root, ['init', '-b', 'main']);
  await git(root, ['config', 'user.email', 'portal@example.test']);
  await git(root, ['config', 'user.name', 'Portal Test']);
  await put(root, 'README.md', 'base\n');
  await put(root, 'apps/docs-site/docs/overview/index.mdx', 'overview\n');
  await commit(root, 'base');

  await git(root, ['checkout', '-b', 'docs/task']);
  await put(root, BRANCH_FILE, 'target chip selection\n');
  if (alsoTouchPortal) await put(root, PORTAL_PAGE, 'branch edit\n');
  const headSha = await commit(root, 'branch work');

  await git(root, ['checkout', 'main']);
  await put(root, PORTAL_PAGE, 'landed by another Pull Request\n');
  await put(root, 'apps/docs-site/docs/overview/index.mdx', 'overview, revised\n');
  const baseSha = await commit(root, 'unrelated portal work lands on main');

  return {root, baseSha, headSha};
}

test('a behind-base branch reports only its own files', async (t) => {
  const {root, baseSha, headSha} = await behindBaseFixture();
  t.after(() => rm(root, {recursive: true, force: true}));

  assert.deepEqual(
    await resolveChangedFiles(root, {baseSha, headSha}),
    [BRANCH_FILE],
    'the merge-base range must exclude portal pages the branch never touched',
  );

  // The two-dot range the gate used before issue #531, for contrast: it blames
  // the branch for both pages `main` changed after the branch was cut.
  const {stdout} = await git(root, ['diff', '--name-only', baseSha, headSha]);
  assert.deepEqual(stdout.split('\n').filter(Boolean).sort(), [
    'apps/docs-site/docs/operations/git-workflow.mdx',
    'apps/docs-site/docs/overview/index.mdx',
    BRANCH_FILE,
  ]);
});

test('a truthful none declaration survives base drift', async (t) => {
  const {root, baseSha, headSha} = await behindBaseFixture();
  t.after(() => rm(root, {recursive: true, force: true}));

  assert.deepEqual(
    checkDocumentationImpact({
      body: HONEST_NONE,
      changedFiles: await resolveChangedFiles(root, {baseSha, headSha}),
    }),
    [],
  );
});

test('base drift does not excuse a portal page the branch really edited', async (t) => {
  const {root, baseSha, headSha} = await behindBaseFixture({alsoTouchPortal: true});
  t.after(() => rm(root, {recursive: true, force: true}));

  const changedFiles = await resolveChangedFiles(root, {baseSha, headSha});
  assert.deepEqual(changedFiles.sort(), [PORTAL_PAGE, BRANCH_FILE].sort());
  assert.deepEqual(checkDocumentationImpact({body: HONEST_NONE, changedFiles}), [
    'documentation impact is none but current portal pages changed — either declare "Documentation impact: required" with "Affected portal pages:" routes, or drop the apps/docs-site/docs/ edits from this PR',
  ]);
});

test('an added-file range does not inherit a deletion that landed on the base', async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'portal-added-files-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  await git(root, ['init', '-b', 'main']);
  await git(root, ['config', 'user.email', 'portal@example.test']);
  await git(root, ['config', 'user.name', 'Portal Test']);
  await put(root, 'apps/architecture-portal/versioned_metadata/version-1.0.1.0.json', '{}\n');
  await commit(root, 'base');

  await git(root, ['checkout', '-b', 'feat/task']);
  await put(root, 'apps/architecture-portal/versioned_metadata/version-1.0.2.0.json', '{}\n');
  const headSha = await commit(root, 'add a snapshot');

  await git(root, ['checkout', 'main']);
  await rm(path.join(root, 'apps/architecture-portal/versioned_metadata/version-1.0.1.0.json'));
  const baseSha = await commit(root, 'remove a snapshot on main');

  assert.deepEqual(
    await resolveChangedFiles(root, {baseSha, headSha, diffFilter: 'A'}),
    ['apps/architecture-portal/versioned_metadata/version-1.0.2.0.json'],
    'only the snapshot this change introduces is the projection check\'s subject',
  );
});

test('the checker resolves the merge-base range from its two revision inputs', async (t) => {
  const {root, baseSha, headSha} = await behindBaseFixture();
  t.after(() => rm(root, {recursive: true, force: true}));
  // The checker derives the repository root from its own location, so the
  // end-to-end wiring is only exercisable with the scripts inside the fixture.
  await cp(SCRIPTS_ROOT, path.join(root, 'apps/architecture-portal/scripts'), {recursive: true});

  const completed = await execFileAsync(
    'node', ['apps/architecture-portal/scripts/check-doc-impact.mjs'],
    {
      cwd: root,
      encoding: 'utf8',
      env: {
        ...process.env,
        PORTAL_PR_BODY: HONEST_NONE,
        PORTAL_CHANGED_FILES: '',
        PORTAL_BASE_SHA: baseSha,
        PORTAL_HEAD_SHA: headSha,
      },
    },
  );
  assert.match(completed.stdout, /portal documentation impact: valid/);
});

test('a malformed revision is refused rather than measured', async (t) => {
  const {root, headSha} = await behindBaseFixture();
  t.after(() => rm(root, {recursive: true, force: true}));

  assert.throws(() => requireRevision('main', 'the base revision'), /40-character revision/);
  await assert.rejects(
    resolveChangedFiles(root, {baseSha: 'HEAD~1', headSha}),
    /40-character revision/,
  );
});
