import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {lstat, mkdir, mkdtemp, open, readFile, readdir, rename, writeFile, unlink, rmdir} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';

const run = promisify(execFile);
const prefix = 'apps/docs-site/docs/releases/';
const installer = fileURLToPath(new URL('../../../../tools/release/install_changelog_page.py', import.meta.url));
const fail = (why) => {throw new Error(`why: release changelog ${why}; remedy: reconcile frozen history and regenerate the index`);};
async function info(file) {
  try {return await lstat(file);} catch (error) {if (error.code === 'ENOENT') return null; throw error;}
}

async function sync(file) {
  const handle = await open(file, 'r');
  try {await handle.sync();} finally {await handle.close();}
}

async function safeDirectory(directory) {
  const observed = await info(directory);
  if (observed && (!observed.isDirectory() || observed.isSymbolicLink())) fail('staging directory is unsafe');
  if (!observed) {
    await mkdir(directory, {mode: 0o700});
    await sync(path.dirname(directory));
  }
}

export async function projectReleaseChangelogs(repoRoot, {check = true} = {}) {
  // Python is the one renderer/validator shared with signed Release operations.
  // No network, Git mutations or model calls are performed by this projection.
  const {stdout} = await run('python3', ['-m', 'tools.release.changelog_site', '--repo-root', repoRoot],
    {cwd: repoRoot, maxBuffer: 8 * 1024 * 1024});
  const {pages} = JSON.parse(stdout);
  return applyReleasePages(repoRoot, pages, {check});
}

export async function applyReleasePages(repoRoot, pages, {check = true} = {}) {
  if (!Array.isArray(pages) || pages.length === 0) fail('page inventory is empty');
  const expected = new Map();
  for (const page of pages) {
    if (!page || typeof page.file !== 'string' || typeof page.content !== 'string'
      || !/^apps\/docs-site\/docs\/releases\/(index|(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3})\.mdx$/.test(page.file)
      || expected.has(page.file)) fail('page identity is invalid or duplicated');
    expected.set(page.file, page.content);
  }
  if (!expected.has(prefix + 'index.mdx')) fail('index is missing');
  for (const relative of ['apps', 'apps/docs-site', 'apps/docs-site/docs']) {
    const parent = await info(path.join(repoRoot, relative));
    if (!parent?.isDirectory() || parent.isSymbolicLink()) fail('parent directory is unsafe');
  }
  const directory = path.join(repoRoot, prefix);
  const directoryInfo = await info(directory);
  if (directoryInfo && (!directoryInfo.isDirectory() || directoryInfo.isSymbolicLink())) fail('directory is unsafe');
  const actual = directoryInfo ? await readdir(directory) : [];
  if (actual.some((name) => !expected.has(prefix + name))) fail('historical page would be removed or an unknown file exists');
  const missing = [];
  for (const [file, content] of expected) {
    const target = path.join(repoRoot, file);
    const observed = await info(target);
    if (observed && (!observed.isFile() || observed.isSymbolicLink() || observed.nlink !== 1)) fail('page is unsafe');
    const existing = observed ? await readFile(target) : null;
    if (existing === null || !existing.equals(Buffer.from(content, 'utf8'))) {
      if (check) fail('projection is stale; run npm run release-changelogs');
      if (existing !== null && file !== prefix + 'index.mdx') fail('frozen version page would be overwritten');
      missing.push([target, content, existing !== null]);
    }
  }
  // All sources are preflighted before writes. Interrupted staging stays under
  // ignored build/release, never in the immutable page inventory. Install whole
  // pages create-only, persist every page, then replace the mutable index last.
  if (!check) {
    await safeDirectory(directory);
    let stagingRoot;
    if (missing.length) {
      for (const relative of ['build', 'build/release', 'build/release/changelog-pages']) {
        await safeDirectory(path.join(repoRoot, relative));
      }
      stagingRoot = path.join(repoRoot, 'build/release/changelog-pages');
      if ((await lstat(stagingRoot)).dev !== (await lstat(directory)).dev) fail('staging and pages are on different filesystems');
    }
    const index = path.join(directory, 'index.mdx');
    const ordered = [...missing.filter(([target]) => target !== index), ...missing.filter(([target]) => target === index)];
    // On resume even already-installed pages must acquire their durability
    // barrier before an index can reference them.
    for (const [file] of expected) {
      if (file !== prefix + 'index.mdx' && await info(path.join(repoRoot, file))) await sync(path.join(repoRoot, file));
    }
    await sync(directory);
    for (const [target, content, replaceIndex] of ordered) {
      const staging = await mkdtemp(path.join(stagingRoot, 'page-'));
      const temporary = path.join(staging, 'page');
      await sync(stagingRoot);
      try {
        await writeFile(temporary, content, {flag: 'wx', mode: 0o600});
        await sync(temporary);
        await sync(staging);
        if (!replaceIndex) {
          const digest = createHash('sha256').update(content, 'utf8').digest('hex');
          await run('python3', [installer, temporary, target, digest]);
        } else {
          await rename(temporary, target);
          await sync(directory);
          await sync(staging);
        }
      } finally {
        await unlink(temporary).catch((error) => {if (error.code !== 'ENOENT') throw error;});
        await rmdir(staging);
        await sync(stagingRoot);
      }
    }
    await sync(index);
    await sync(directory);
  }
  return pages;
}
