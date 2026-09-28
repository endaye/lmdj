import {execFile} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {promisify} from 'node:util';

import {requireRevision, resolveChangedFiles} from './lib/changed-files.mjs';

const execFileAsync = promisify(execFile);

// The files a candidate cut writes: regenerated Product identity plus the
// immutable snapshot. Current pages derive every identity from the manifests,
// so a cut that touches nothing else has no current page to edit.
const CUT_IDENTITY_FILE = /^products\/lmdj\/(?:version\.json|assembly(?:\.lock)?\.json|src\/compiled_assembly\.cpp|generated\/web-runtime-identity\.(?:json|mjs))$/;
const PRODUCT_BUILD = /^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}$/;

function isCandidateCut(changedFiles, productBuild) {
  if (!PRODUCT_BUILD.test(productBuild ?? '')) return false;
  const build = productBuild.replaceAll('.', '\\.');
  // Only this Build's snapshot: a path of any other Build is not part of its cut.
  const snapshotFile = new RegExp(`^apps/architecture-portal/(?:versions\\.json$|versioned_(?:docs|sidebars|metadata|provenance)/version-${build}[./-]|static/versions/${build}/)`);
  const metadata = `apps/architecture-portal/versioned_metadata/version-${productBuild}.json`;
  return changedFiles.includes(metadata)
    && changedFiles.includes('products/lmdj/version.json')
    && changedFiles.every((file) => CUT_IDENTITY_FILE.test(file) || snapshotFile.test(file));
}

export function checkDocumentationImpact({body, changedFiles, productBuild}) {
  const errors = [];
  const impact = body.match(/^Documentation impact:\s*(required|none)\s*$/im)?.[1]?.toLowerCase();
  const reason = body.match(/^Reason:\s*(.*)$/im)?.[1]?.trim();
  const pages = body.match(/^Affected portal pages:\s*(.*)$/im)?.[1]?.trim();
  const currentPortalChanged = changedFiles.some((file) => /^apps\/docs-site\/docs\/.+\.mdx?$/.test(file));
  const productIdentityChanged = changedFiles.some((file) =>
    /^products\/lmdj\/(?:version\.json|assembly(?:\.lock)?\.json|CMakeLists\.txt|src\/)/.test(file));

  if (!impact) return ['documentation impact must be required or none — the PR body needs a line reading exactly "Documentation impact: required" or "Documentation impact: none" (prose belongs on a separate "Reason:" line); after editing the body, re-trigger with a new pull_request event (close/reopen or a new push) — a rerun reuses the stale event payload'];
  if (!reason) errors.push('documentation impact reason is empty — add a "Reason: <why this impact level is correct>" line to the PR body');
  if (productIdentityChanged && impact !== 'required') {
    errors.push('Product Build or Assembly changes require documentation impact: required — declare "Documentation impact: required", list "Affected portal pages:" routes, and update the current portal pages plus the immutable snapshot obligation in the same Task');
  }
  if (impact === 'required') {
    if (!pages || !pages.split(/[\s,]+/).filter(Boolean).every((route) => route.startsWith('/'))) {
      errors.push('affected portal pages must list one or more absolute routes — add an "Affected portal pages:" line whose entries each start with "/" (space- or comma-separated)');
    }
    if (!currentPortalChanged && !isCandidateCut(changedFiles, productBuild)) errors.push('documentation impact is required but no current portal page changed — update the affected pages under apps/docs-site/docs/ in this PR, or declare "Documentation impact: none" with a reason if no portal truth changes');
  } else if (currentPortalChanged) {
    errors.push('documentation impact is none but current portal pages changed — either declare "Documentation impact: required" with "Affected portal pages:" routes, or drop the apps/docs-site/docs/ edits from this PR');
  }
  return errors;
}

/**
 * The Product Build a change's head names, read from the same revision the
 * changed-file range ends at. Without a head revision the caller is a local
 * run measuring its own tree, so the working tree is that head.
 */
export async function readProductBuild(repoRoot, {headSha} = {}) {
  try {
    const text = headSha
      ? (await execFileAsync('git', ['show', `${requireRevision(headSha, 'the head revision')}:products/lmdj/version.json`],
        {cwd: repoRoot, encoding: 'utf8'})).stdout
      : await readFile(path.join(repoRoot, 'products/lmdj/version.json'), 'utf8');
    const version = JSON.parse(text);
    const parts = [version.milestone, version.minor, version.build, version.patch];
    return parts.every((part) => Number.isInteger(part) && part >= 0) ? parts.join('.') : undefined;
  } catch {
    return undefined;
  }
}

async function main() {
  const body = process.env.PORTAL_PR_BODY ?? '';
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
  let changedFiles = (process.env.PORTAL_CHANGED_FILES ?? '').split(/\r?\n/).filter(Boolean);
  if (!changedFiles.length) {
    try {
      changedFiles = await resolveChangedFiles(repoRoot, {
        baseSha: process.env.PORTAL_BASE_SHA,
        headSha: process.env.PORTAL_HEAD_SHA,
      });
    } catch (error) {
      console.error(`the changed-file range cannot be measured: ${error.message}`);
      process.exitCode = 1;
      return;
    }
  }
  const errors = checkDocumentationImpact({body, changedFiles, productBuild: await readProductBuild(repoRoot, {headSha: process.env.PORTAL_HEAD_SHA})});
  if (errors.length) {
    console.error(errors.join('\n'));
    process.exitCode = 1;
  } else {
    console.log('portal documentation impact: valid');
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) await main();
