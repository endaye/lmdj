import path from 'node:path';
import {fileURLToPath} from 'node:url';

import {resolveChangedFiles} from './lib/changed-files.mjs';

export function checkDocumentationImpact({body, changedFiles}) {
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
    if (!currentPortalChanged) errors.push('documentation impact is required but no current portal page changed — update the affected pages under apps/docs-site/docs/ in this PR, or declare "Documentation impact: none" with a reason if no portal truth changes');
  } else if (currentPortalChanged) {
    errors.push('documentation impact is none but current portal pages changed — either declare "Documentation impact: required" with "Affected portal pages:" routes, or drop the apps/docs-site/docs/ edits from this PR');
  }
  return errors;
}

async function main() {
  const body = process.env.PORTAL_PR_BODY ?? '';
  let changedFiles = (process.env.PORTAL_CHANGED_FILES ?? '').split(/\r?\n/).filter(Boolean);
  if (!changedFiles.length) {
    const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
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
  const errors = checkDocumentationImpact({body, changedFiles});
  if (errors.length) {
    console.error(errors.join('\n'));
    process.exitCode = 1;
  } else {
    console.log('portal documentation impact: valid');
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) await main();
