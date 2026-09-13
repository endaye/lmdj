import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {lstat, mkdir, readFile, readdir, rename, writeFile, unlink} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

const run = promisify(execFile);
const prefix = 'apps/docs-site/docs/releases/';
const fail = (why) => {throw new Error(`why: release changelog ${why}; remedy: reconcile frozen history and regenerate the index`);};
async function info(file) {
  try {return await lstat(file);} catch (error) {if (error.code === 'ENOENT') return null; throw error;}
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
  // Preflight every frozen page before any mutation. Reruns retain complete,
  // byte-identical pages. A crash within a write can leave a truncated page or
  // index temporary file: fail closed for reconciliation, not automatic recovery.
  if (!check) {
    if (!directoryInfo) await mkdir(directory);
    for (const [target, content, replaceIndex] of missing) {
      if (!replaceIndex) await writeFile(target, content, {flag: 'wx'});
      else {
        const temporary = path.join(directory, `.index-${randomUUID()}`);
        try {
          await writeFile(temporary, content, {flag: 'wx'});
          await rename(temporary, target);
        } finally {
          await unlink(temporary).catch((error) => {if (error.code !== 'ENOENT') throw error;});
        }
      }
    }
  }
  return pages;
}
