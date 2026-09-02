import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

const execFileAsync = promisify(execFile);
const SHA_PATTERN = /^[0-9a-fA-F]{40}$/;

/**
 * Validate one revision input the Pull Request gate was handed.
 *
 * The gate's inputs come from the `pull_request` event payload by way of the
 * change-scope classifier, so a malformed revision means the caller is wired
 * wrongly rather than that the change is clean. Rejecting it is the same
 * decision the workflow step used to make with its own `[[ =~ ]]` test; the
 * check moved here so it is exercised by the test suite instead of only by a
 * production run.
 */
export function requireRevision(value, label) {
  if (typeof value !== 'string' || !SHA_PATTERN.test(value)) {
    throw new Error(`${label} must be a 40-character revision`);
  }
  return value.toLowerCase();
}

/**
 * List the files a Pull Request changes, measured from its merge base.
 *
 * `base_sha` on a `pull_request` event is the tip of the base branch at event
 * time, not the merge base. A two-dot `git diff BASE HEAD` compares those two
 * trees, so every commit that landed on the base branch after the branch was
 * cut appears in the diff in reverse: a branch that is merely behind inherits
 * unrelated files as "changed by this Pull Request". Three-dot diffs
 * `merge-base(BASE, HEAD)` against HEAD, which is the change's own contribution
 * and the same range `scripts/ci/local_preflight.py` already measures locally.
 *
 * `--name-only -z` keeps paths unquoted and unambiguous, so a path containing a
 * quote or a newline cannot be misread as two entries.
 */
export async function resolveChangedFiles(
  repoRoot, {baseSha, headSha, diffFilter} = {},
) {
  const filter = diffFilter ? [`--diff-filter=${diffFilter}`] : [];
  // Without a base revision there is no Pull Request range to measure, so the
  // caller is a local or manual run and the previous commit is the only
  // defensible base. CI always supplies both revisions.
  const range = baseSha
    ? [`${requireRevision(baseSha, 'the base revision')}...${requireRevision(headSha, 'the head revision')}`]
    : ['HEAD^', headSha || 'HEAD'];
  const {stdout} = await execFileAsync(
    'git', ['diff', '--name-only', '-z', ...filter, ...range],
    {cwd: repoRoot, maxBuffer: 64 * 1024 * 1024},
  );
  return stdout.split('\0').filter(Boolean);
}
