import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {projectReleaseChangelogs} from './lib/release-changelogs.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
try {
  if (process.argv.length !== 3 || !['--write', '--check'].includes(process.argv[2])) {
    throw new Error('why: explicit release changelog mode required; remedy: use --write or --check');
  }
  const pages = await projectReleaseChangelogs(repoRoot, {check: process.argv[2] === '--check'});
  console.log(`Release changelogs: ${pages.length} pages ${process.argv[2] === '--check' ? 'valid' : 'generated'}`);
} catch {
  console.error('why: release changelog projection failed; remedy: inspect frozen publication records and run the read-only Python projector for details');
  process.exitCode = 1;
}
