import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

const execFileAsync = promisify(execFile);

export function checkDocumentationImpact({body, changedFiles}) {
  const errors = [];
  const impact = body.match(/^Documentation impact:\s*(required|none)\s*$/im)?.[1]?.toLowerCase();
  const reason = body.match(/^Reason:\s*(.*)$/im)?.[1]?.trim();
  const pages = body.match(/^Affected portal pages:\s*(.*)$/im)?.[1]?.trim();
  const currentPortalChanged = changedFiles.some((file) => /^apps\/architecture-portal\/docs\/.+\.mdx?$/.test(file));

  if (!impact) return ['documentation impact must be required or none'];
  if (!reason) errors.push('documentation impact reason is empty');
  if (impact === 'required') {
    if (!pages || !pages.split(/[\s,]+/).filter(Boolean).every((route) => route.startsWith('/'))) {
      errors.push('affected portal pages must list one or more absolute routes');
    }
    if (!currentPortalChanged) errors.push('documentation impact is required but no current portal page changed');
  } else if (currentPortalChanged) {
    errors.push('documentation impact is none but current portal pages changed');
  }
  return errors;
}

async function main() {
  const body = process.env.PORTAL_PR_BODY ?? '';
  let changedFiles = (process.env.PORTAL_CHANGED_FILES ?? '').split(/\r?\n/).filter(Boolean);
  if (!changedFiles.length) {
    const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
    const {stdout} = await execFileAsync('git', ['diff', '--name-only', 'HEAD^', 'HEAD'], {cwd: repoRoot});
    changedFiles = stdout.split(/\r?\n/).filter(Boolean);
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
